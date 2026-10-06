"""Finestra di contesto calcolata dal setup (05/10/2026, fase 1 del rapporto «Contesto di
Calliope», docs/ricerche/2026-10-05-contesto-budget.md).

Con `llm_num_ctx: auto` (il predefinito) la finestra della voce non è più un numero scritto
per il portatile o per la DGX: all'avvio, dopo il riscaldamento, è il minimo di tre limiti.

1. **Il modello**: la lunghezza di contesto che regge (Ollama `/api/show`,
   `<architettura>.context_length`; vLLM `/v1/models`, `max_model_len`).
2. **La memoria**: con Ollama sulla stessa macchina, la memoria libera (nvidia-smi sul
   portatile; MemAvailable di /proc/meminfo sulla DGX, memoria unificata) meno
   `contesto_margine_gb`, divisa per il costo di un token della cache (dalla forma del
   modello: strati, teste KV, dimensioni, finestra degli strati «sliding»), sopra la finestra
   con cui il modello è già caricato; diviso per `contesto_conversazioni`. Con vLLM la cache
   la fissa il server all'avvio: i token che dice /metrics (`kv_cache_size_tokens`).
3. **Il tempo di rilettura**: quanta storia si rilegge in `contesto_rilettura_max_s` alla
   velocità di lettura (prefill) misurata (prefisso in cache, storia da rileggere tutta:
   dopo un cambio di conversazione o di satellite), più il prefisso e la riserva del turno.
   **Con la compressione** (fase 2, dal 05/10: calliope/compressione.py) la storia non
   cresce oltre la soglia morbida: la finestra è quella in cui la storia **alla soglia
   morbida** si rilegge in `contesto_rilettura_max_s` (prefisso + velocità × secondi, diviso
   per la soglia). Dopo una compressione si rileggono solo riassunto e ultimi turni (0,16 s
   misurati sul portatile): i secondi interi si pagano solo quando la cache va persa
   (Ollama riavviato, un'altra conversazione sullo stesso posto nella fase 3).

Arrotondato per difetto a multipli di 4096, mai sotto 8192, mai sopra il massimo del
modello. Fase 1: il tempo non porta mai la finestra sotto `contesto_ripiego` (16 384, quella
dei banchi): misurato il 05/10, 1,5 s di rilettura valgono ~14–15 k su portatile e DGX, cioè
la finestra di oggi è già al limite; senza questo pavimento la voce avrebbe perso metà della
storia, e la fase 1 non cambia il comportamento. Un dato che non si legge vale
`contesto_ripiego`, e lo si dice. Un numero in `llm_num_ctx` vince sempre (il calcolo si fa
lo stesso, per `calliope stato`).

Con Ollama `num_ctx` deve essere lo stesso in ogni richiesta allo stesso modello (voce,
scrittore dei documenti, agenti e archivio sullo stesso Ollama, prove), altrimenti Ollama
ricarica il modello: tutti lo chiedono a `finestra(cfg)`, che dopo l'avvio legge la scelta
salvata in `contesto.json` accanto a calliope.yaml.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

PASSO = 4096                 # la finestra si arrotonda a multipli di questo
MINIMO = 8192                # mai sotto
# Il costo vero di un token della cache sul portatile (05/10, gemma4 e4b, nvidia-smi da 16k a
# 128k): 17,0 KiB contro 16 KiB della formula (anche i buffer del grafo crescono)
FATTORE_KV = 1.1
BYTE_KV = 2                  # cache f16 di Ollama (con OLLAMA_KV_CACHE_TYPE=q8_0 è la metà:
#                              la stima resta prudente)
FILE = "contesto.json"
# La velocità di lettura si rimisura dopo tanti giorni (o se cambia il modello)
VELOCITA_GIORNI = 7
# Tutti i numeri del calcolo, per il registro e per `calliope stato`
_LOCALI = ("127.0.0.1", "localhost", "::1", "0.0.0.0")


@dataclass
class Budget:
    """La finestra scelta e perché."""
    finestra: int
    fonte: str                       # "auto" | "configurazione"
    motivo: str                      # "modello" | "memoria" | "tempo" | "ripiego" | "minimo"
    auto: int = 0                    # quella che il calcolo darebbe (anche con un numero scritto)
    modello: int | None = None       # (a) contesto massimo del modello
    memoria: int | None = None       # (b) token che ci stanno in memoria, per conversazione
    tempo: int | None = None         # (c) prefisso + storia rileggibile + riserva
    velocita: float | None = None    # token/s di lettura (prefill)
    prefisso: int | None = None      # token di prompt di sistema e schemi dei tool
    kv_byte_token: float | None = None
    memoria_libera_gb: float | None = None
    memoria_fonte: str | None = None
    note: list[str] = field(default_factory=list)
    quando: str = ""

    def frase(self) -> str:
        """Una riga leggibile: finestra, perché, e i tre limiti."""
        perche = {"modello": "il massimo del modello", "memoria": "la memoria",
                  "tempo": "il tempo di rilettura", "ripiego": "il valore di ripiego",
                  "minimo": "il minimo", "configurazione": "scritta in llm_num_ctx",
                  "voce": "la finestra della voce: stesso Ollama e stesso modello"}
        parti = []
        if self.modello:
            parti.append(f"modello {_n(self.modello)}")
        if self.memoria:
            libera = (f", {self.memoria_libera_gb:.1f} GB liberi".replace(".", ",")
                      if self.memoria_libera_gb is not None else "")
            parti.append(f"memoria {_n(self.memoria)}{libera}")
        if self.tempo:
            vel = f" a {_n(round(self.velocita))} token/s" if self.velocita else ""
            parti.append(f"tempo {_n(self.tempo)}{vel}")
        quale = "configurazione" if self.fonte == "configurazione" else self.motivo
        testo = f"finestra {_n(self.finestra)} token ({perche.get(quale, quale)}"
        if self.fonte == "configurazione" and self.auto:
            testo += f"; «auto» darebbe {_n(self.auto)}"
        testo += ")"
        if parti:
            testo += ": " + ", ".join(parti)
        if self.note:
            testo += ". " + "; ".join(self.note)
        return testo


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


# ─────────────────────────── la finestra in uso ───────────────────────────
def chiave(cfg) -> str:
    """Il modello della voce: backend, indirizzo e nome (la scelta salvata vale per lui)."""
    url = cfg.llm_native_url if cfg.llm_backend == "ollama" else cfg.llm_base_url
    return f"{cfg.llm_backend}|{(url or '').rstrip('/')}|{cfg.llm_model}"


def percorso(cfg) -> Path:
    forced = os.environ.get("CALLIOPE_CONTESTO")
    if forced:
        return Path(forced)
    return Path(getattr(cfg, "config_dir", None) or ".") / FILE


def leggi_salvato(cfg) -> dict | None:
    try:
        dati = json.loads(percorso(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    voce = dati.get(chiave(cfg)) if isinstance(dati, dict) else None
    return voce if isinstance(voce, dict) else None


def salva(cfg, budget: Budget, extra: dict | None = None):
    """La scelta in contesto.json, per chiave del modello (atomico; un errore non ferma)."""
    from .persistenza import scrivi_json
    p = percorso(cfg)
    try:
        dati = json.loads(p.read_text(encoding="utf-8"))
        dati = dati if isinstance(dati, dict) else {}
    except (OSError, ValueError):
        dati = {}
    dati[chiave(cfg)] = {**asdict(budget), **(extra or {})}
    try:
        scrivi_json(p, dati)
    except OSError as e:
        print(f"[CONTESTO] Non riesco a salvare {p} ({e})", flush=True)


def numero(value):
    """`llm_num_ctx` valido: un intero o «auto» (VALIDATORI di config.py)."""
    if isinstance(value, bool):
        raise ValueError("serve un numero di token o «auto»")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s == "auto":
            return "auto"
        if s.isdigit():
            return int(s)
    raise ValueError("serve un numero di token (per esempio 16384) o «auto»")


def finestra(cfg) -> int:
    """Il num_ctx da mandare adesso: il numero scritto in llm_num_ctx; con «auto» quello
    scelto all'avvio (in questo processo, o da Calliope in contesto.json per gli altri:
    prove, terminale), altrimenti contesto_ripiego."""
    v = getattr(cfg, "llm_num_ctx", None)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    scelta = getattr(cfg, "_contesto_scelto", None)
    if scelta:
        return int(scelta)
    letto = getattr(cfg, "_contesto_letto", None)
    if letto is None:
        voce = leggi_salvato(cfg) or {}
        letto = int(voce.get("finestra") or 0) if voce.get("fonte") == "auto" else 0
        try:
            cfg._contesto_letto = letto
        except AttributeError:
            pass
    return letto or int(getattr(cfg, "contesto_ripiego", 16384) or 16384)


# ─────────────────────────── i tre limiti ───────────────────────────
def kv_ollama(info: dict) -> tuple[float, float] | None:
    """(byte per token degli strati globali, byte fissi degli strati «sliding») dalla forma
    del modello (`model_info` di /api/show), con FATTORE_KV. None se mancano i dati.

    Gemma 4 (05/10): e4b 42 strati, gli ultimi 18 condividono la cache dei precedenti; dei 24
    con cache 4 sono globali (2 teste KV × 512 + 512) → 16 KiB a token; 26B-A4B 30 strati, 5
    globali → 20 KiB. Gli strati «sliding» tengono solo `sliding_window` token."""
    arch = info.get("general.architecture")
    if not arch:
        return None

    def g(k, d=None):
        return info.get(f"{arch}.{k}", d)

    strati = g("block_count")
    teste = g("attention.head_count")
    if not strati:
        return None
    kv = g("attention.head_count_kv", teste)
    emb = g("embedding_length")
    kl = g("attention.key_length") or (emb // teste if emb and teste else None)
    if not kl or not kv:
        return None
    vl = g("attention.value_length") or kl
    kls = g("attention.key_length_swa") or kl
    vls = g("attention.value_length_swa") or vl
    win = g("attention.sliding_window") or 0
    pat = g("attention.sliding_window_pattern")
    propri = max(1, int(strati) - int(g("attention.shared_kv_layers") or 0))
    globale = fissi = 0.0
    for i in range(propri):
        h = kv[i] if isinstance(kv, list) and i < len(kv) else (
            kv[-1] if isinstance(kv, list) else kv)
        if isinstance(pat, list):
            sliding = bool(win) and i < len(pat) and bool(pat[i])
        elif isinstance(pat, int) and pat > 0:
            sliding = bool(win) and (i + 1) % pat != 0
        else:
            sliding = False
        if sliding:
            fissi += h * (kls + vls) * BYTE_KV * win
        else:
            globale += h * (kl + vl) * BYTE_KV
    if globale <= 0:
        return None
    return globale * FATTORE_KV, fissi * FATTORE_KV


def contesto_ollama(info: dict) -> int | None:
    arch = info.get("general.architecture")
    v = info.get(f"{arch}.context_length") if arch else None
    return int(v) if isinstance(v, (int, float)) and v > 0 else None


_KV_TOKENS = re.compile(r'kv_cache_size_tokens="(\d+)"')
_BLOCCHI = re.compile(r'num_gpu_blocks="(\d+)"')
_BLOCCO = re.compile(r'block_size="(\d+)"')


def token_cache_vllm(metrics: str) -> int | None:
    """I token della cache di vLLM da /metrics (cache_config_info): kv_cache_size_tokens,
    o blocchi × dimensione del blocco."""
    for riga in metrics.splitlines():
        if not riga.startswith("vllm:cache_config_info"):
            continue
        m = _KV_TOKENS.search(riga)
        if m:
            return int(m.group(1))
        b, s = _BLOCCHI.search(riga), _BLOCCO.search(riga)
        if b and s:
            return int(b.group(1)) * int(s.group(1))
    return None


def memoria_libera(meminfo: str = "/proc/meminfo", smi=None) -> tuple[float, str] | None:
    """(byte liberi, fonte): nvidia-smi se dà numeri (GPU con la sua memoria), altrimenti
    MemAvailable (memoria unificata della DGX: nvidia-smi lì dice [N/A]). None se nessuno."""
    try:
        out = smi() if smi is not None else subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5).stdout
        valori = [float(x) for x in out.split() if re.fullmatch(r"\d+(\.\d+)?", x)]
        if valori:
            return valori[0] * 1024 * 1024, "nvidia-smi"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        with open(meminfo, encoding="ascii", errors="replace") as f:
            for riga in f:
                if riga.startswith("MemAvailable:"):
                    return float(riga.split()[1]) * 1024, "meminfo"
    except OSError:
        pass
    return None


def locale(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "") in _LOCALI
    except ValueError:
        return False


def compressione(cfg) -> bool:
    """La compressione della storia è accesa (contesto_riassuntore non «spento»)?"""
    return str(getattr(cfg, "contesto_riassuntore", "spento") or "spento").lower() != "spento"


def arrotonda(x: float) -> int:
    return int(x) // PASSO * PASSO


def scegli(cfg, *, modello=None, memoria=None, tempo=None, note=None) -> tuple[int, str]:
    """(finestra, motivo) dai tre limiti già calcolati. None = non letto: vale
    contesto_ripiego, il motivo diventa «ripiego» se è lui il più piccolo, e lo si dice in
    `note` (se il calcolo non l'ha già detto meglio)."""
    note = note if note is not None else []
    ripiego = int(getattr(cfg, "contesto_ripiego", 16384) or 16384)
    ORDINE = ["modello", "memoria", "tempo"]
    limiti, letti = {}, {}
    for nome, val in (("modello", modello), ("memoria", memoria), ("tempo", tempo)):
        if val is None:
            limiti[nome], letti[nome] = ripiego, False
            if not any(n.startswith(nome + ":") for n in note):
                note.append(f"{nome}: dato non letto")
        elif nome == "tempo":
            # Fase 1: il tempo non toglie storia rispetto alla finestra dei banchi
            limiti[nome], letti[nome] = max(int(val), ripiego), True
            if int(val) < ripiego:
                note.append(f"tempo: la rilettura darebbe {_n(arrotonda(val))}, resta "
                            f"{_n(ripiego)} (contesto_ripiego)")
        else:
            limiti[nome], letti[nome] = int(val), True
    # A parità di valore vince un dato letto davvero
    scelto = min(limiti, key=lambda k: (limiti[k], not letti[k], ORDINE.index(k)))
    motivo = scelto if letti[scelto] else "ripiego"
    fin = arrotonda(limiti[scelto])
    massimo = limiti["modello"]
    if fin < MINIMO:
        fin, motivo = min(MINIMO, massimo), "minimo"
    return min(fin, massimo), motivo


# ─────────────────────────── dal server ───────────────────────────
def leggi_ollama(http, cfg) -> dict:
    """Forma del modello e finestra con cui è caricato, dall'Ollama della voce."""
    out = {}
    r = http.post("/api/show", json={"model": cfg.llm_model}, timeout=10)
    r.raise_for_status()
    info = r.json().get("model_info") or {}
    out["modello"] = contesto_ollama(info)
    out["kv"] = kv_ollama(info)
    try:
        ps = http.get("/api/ps", timeout=5).json().get("models") or []
        m = next((x for x in ps if x.get("name") in (cfg.llm_model, f"{cfg.llm_model}:latest")
                  or x.get("model") == cfg.llm_model), None)
        out["caricato"] = int(m["context_length"]) if m and m.get("context_length") else None
    except Exception:  # noqa: BLE001 — /api/ps è solo un aiuto
        out["caricato"] = None
    return out


def leggi_vllm(http, cfg) -> dict:
    out = {}
    r = http.get(cfg.llm_base_url.rstrip("/") + "/models", timeout=10)
    r.raise_for_status()
    m = next((x for x in r.json().get("data", []) if x.get("id") == cfg.llm_model), None)
    out["modello"] = int(m["max_model_len"]) if m and m.get("max_model_len") else None
    radice = re.sub(r"/v1/?$", "", cfg.llm_base_url.rstrip("/"))
    try:
        out["cache"] = token_cache_vllm(http.get(radice + "/metrics", timeout=5).text)
    except Exception:  # noqa: BLE001 — llama-server e altri non hanno /metrics
        out["cache"] = None
    return out


def calcola(cfg, server: dict, *, velocita: float | None, prefisso: int | None,
            libera: tuple[float, str] | None, riserva: int) -> Budget:
    """Il calcolo, senza rete (le prove lo chiamano con dati finti)."""
    note: list[str] = []
    conv = max(1, int(getattr(cfg, "contesto_conversazioni", 1) or 1))
    margine = float(getattr(cfg, "contesto_margine_gb", 0.5) or 0) * 1e9
    massimo = server.get("modello")
    mem_tok = kv_tok = None
    libera_gb = fonte = None
    if cfg.llm_backend == "ollama":
        kv = server.get("kv")
        url = cfg.llm_native_url
        if not locale(url):
            note.append("memoria: il server del modello è su un'altra macchina")
        elif kv is None:
            note.append("memoria: forma della cache del modello non letta")
        elif libera is None:
            note.append("memoria: né nvidia-smi né /proc/meminfo")
        elif not server.get("caricato"):
            note.append("memoria: modello non caricato")
        else:
            kv_tok = kv[0]
            libera_gb, fonte = libera[0] / 1e9, libera[1]
            extra = max(0.0, libera[0] - margine) / kv[0]
            mem_tok = int((server["caricato"] + extra) / conv)
    else:
        cache = server.get("cache")
        if cache:
            mem_tok = int(cache / conv)
            fonte = "vllm"
        else:
            note.append("memoria: la cache del server non si legge (/metrics)")
    tempo = None
    if velocita and prefisso:
        rilettura = float(getattr(cfg, "contesto_rilettura_max_s", 1.5) or 1.5)
        if compressione(cfg):
            # La storia si ferma alla soglia morbida: è lei che si rilegge a cache persa
            soglia = float(getattr(cfg, "contesto_soglia_morbida", 0.75) or 0.75)
            tempo = int((prefisso + velocita * rilettura) / soglia)
        else:
            tempo = int(prefisso + velocita * rilettura + riserva)
    else:
        note.append("tempo: velocità di lettura non misurata")
    fin, motivo = scegli(cfg, modello=massimo, memoria=mem_tok, tempo=tempo, note=note)
    return Budget(finestra=fin, fonte="auto", motivo=motivo, auto=fin, modello=massimo,
                  memoria=mem_tok, tempo=tempo, velocita=velocita, prefisso=prefisso,
                  kv_byte_token=kv_tok, memoria_libera_gb=libera_gb, memoria_fonte=fonte,
                  note=note,
                  quando=datetime.datetime.now().isoformat(timespec="seconds"))


def prepara(cfg, brain, log=print, libera_fn=None) -> Budget:
    """All'avvio, dopo il riscaldamento: calcola la finestra, la applica (con «auto»; con
    Ollama una finestra diversa da quella del riscaldamento ricarica il modello: si
    riscalda di nuovo, così la prima domanda non aspetta) e la salva in contesto.json.
    Mai un'eccezione: nel peggio resta la finestra di prima, e lo si dice."""
    import httpx
    from .brain import CTX_RESERVE
    prima = finestra(cfg)
    salvato = leggi_salvato(cfg) or {}
    try:
        if cfg.llm_backend == "ollama":
            with httpx.Client(base_url=cfg.llm_native_url) as http:
                server = leggi_ollama(http, cfg)
        else:
            with httpx.Client() as http:
                server = leggi_vllm(http, cfg)
    except Exception as e:  # noqa: BLE001
        server = {}
        log(f"[CONTESTO] Dati del modello non letti ({type(e).__name__}: {e})")
    # La velocità di lettura: quella salvata (stesso modello, recente), altrimenti si misura
    velocita, prefisso = salvato.get("velocita"), getattr(brain, "prefix_tokens", None)
    fresca = False
    try:
        eta = time.time() - datetime.datetime.fromisoformat(salvato.get("misurata", "")).timestamp()
        fresca = 0 <= eta < VELOCITA_GIORNI * 86400
    except (TypeError, ValueError):
        pass
    misurata = salvato.get("misurata") if fresca else None
    if not (velocita and fresca):
        try:
            prefisso, velocita = brain.measure_prefill()
            misurata = datetime.datetime.now().isoformat(timespec="seconds")
            log(f"[CONTESTO] Velocità di lettura misurata: {_n(round(velocita))} token/s "
                f"({_n(prefisso)} token di prefisso)")
            brain.warmup()                 # il prefisso vero torna in cache
        except Exception as e:  # noqa: BLE001
            velocita = None
            log(f"[CONTESTO] Velocità di lettura non misurata ({type(e).__name__}: {e})")
    prefisso = prefisso or salvato.get("prefisso")
    if cfg.llm_backend == "ollama" and locale(cfg.llm_native_url):
        libera = (libera_fn or memoria_libera)()
    else:
        libera = None
    budget = calcola(cfg, server, velocita=velocita, prefisso=prefisso, libera=libera,
                     riserva=CTX_RESERVE)
    scritta = getattr(cfg, "llm_num_ctx", "auto")
    if isinstance(scritta, int) and not isinstance(scritta, bool):
        budget.finestra, budget.fonte = scritta, "configurazione"
    else:
        cfg._contesto_scelto = budget.finestra
        if budget.finestra != prima and cfg.llm_backend == "ollama":
            log(f"[CONTESTO] Ricarico il modello con la finestra nuova "
                f"({_n(prima)} → {_n(budget.finestra)})")
            try:
                brain.warmup()
            except Exception as e:  # noqa: BLE001 — la prima domanda la ricaricherà
                log(f"[CONTESTO] Riscaldamento non riuscito ({type(e).__name__}: {e})")
    salva(cfg, budget, {"misurata": misurata})
    log(f"[CONTESTO] {budget.frase()}")
    return budget


# ─────────────────────────── la finestra degli agenti (fase 2b) ───────────────────────────
# Con un Ollama remoto la memoria di là non si legge e Ollama prenota tutta la finestra:
# al più questa (il valore di prima, 32 768)
AGENTI_RIPIEGO = 32768


def calcola_agenti(cfg, motore: str, server: dict, stesso: bool = False) -> Budget:
    """La finestra dell'agente (05/10, fase 2b), senza rete (le prove la chiamano con dati
    finti). `server`: {"modello": contesto massimo, "cache": token della cache di vLLM}.

    - Stesso Ollama e stesso modello della voce: la finestra della voce, sempre (un num_ctx
      diverso ricaricherebbe il modello a ogni cambio, secondi persi dalla voce).
    - vLLM: il minimo tra `max_model_len` e i token della cache (/metrics) divisi per
      `agenti_contesti_paralleli`. Qui il tempo non conta: con la cache dei prefissi il lavoro
      rilegge solo l'ultimo passo, e la compressione del lavoro (contesto_lavoro.py) tiene
      corto quello che si rilegge dopo un taglio.
    - Ollama su un'altra macchina: il massimo del modello, ma al più AGENTI_RIPIEGO.
    Un numero in `agenti_num_ctx` vince (il calcolo resta, per il registro)."""
    scritta = getattr(cfg, "agenti_num_ctx", "auto")
    quando = datetime.datetime.now().isoformat(timespec="seconds")
    if stesso:
        fin = finestra(cfg)
        return Budget(finestra=fin, fonte="auto", motivo="voce", auto=fin, quando=quando)
    note: list[str] = []
    massimo = server.get("modello")
    par = max(1, int(getattr(cfg, "agenti_contesti_paralleli", 2) or 1))
    cache = server.get("cache")
    mem = int(cache / par) if cache else None
    if motore == "openai":
        if not massimo:
            note.append("modello: max_model_len non letto")
        if mem is None:
            note.append("memoria: la cache del server non si legge (/metrics)")
        cand = {k: v for k, v in (("modello", massimo), ("memoria", mem)) if v}
        if cand:
            motivo = min(cand, key=lambda k: (cand[k], k != "modello"))
            fin = arrotonda(cand[motivo])
        else:
            motivo, fin = "ripiego", AGENTI_RIPIEGO
    else:
        note.append(f"memoria del server non letta: al più {_n(AGENTI_RIPIEGO)}")
        if massimo and massimo < AGENTI_RIPIEGO:
            motivo, fin = "modello", arrotonda(massimo)
        else:
            motivo, fin = "ripiego", AGENTI_RIPIEGO
            if not massimo:
                note.append("modello: contesto massimo non letto")
    if fin < MINIMO:
        fin, motivo = MINIMO if not massimo else min(MINIMO, int(massimo)), "minimo"
    b = Budget(finestra=fin, fonte="auto", motivo=motivo, auto=fin, modello=massimo,
               memoria=mem, memoria_fonte="vllm" if mem else None, note=note, quando=quando)
    if isinstance(scritta, int) and not isinstance(scritta, bool):
        b.finestra, b.fonte = scritta, "configurazione"
    return b


def leggi_agenti(cliente, modello: str, motore: str) -> dict:
    """{"modello", "cache"} dal server dell'agente (dal thread dei lavori, mai dalla voce).
    Un dato che non si legge resta None."""
    http = getattr(cliente, "http", None)
    out: dict = {"modello": None, "cache": None}
    if http is None:
        return out
    if motore == "openai":
        try:
            r = http.get("/v1/models", timeout=5)
            m = next((x for x in r.json().get("data", []) if x.get("id") == modello), None)
            out["modello"] = int(m["max_model_len"]) if m and m.get("max_model_len") else None
        except Exception:  # noqa: BLE001
            pass
        try:
            out["cache"] = token_cache_vllm(http.get("/metrics", timeout=5).text)
        except Exception:  # noqa: BLE001 — llama-server e altri non hanno /metrics
            pass
    else:
        try:
            r = http.post("/api/show", json={"model": modello}, timeout=10)
            out["modello"] = contesto_ollama(r.json().get("model_info") or {})
        except Exception:  # noqa: BLE001
            pass
    return out


# ─────────────────────────── uso per turno ───────────────────────────
def uso(token: int | None, fin: int | None) -> dict | None:
    """{"token", "finestra", "percento"} per il registro dei turni, la console e lo schermo."""
    if not token or not fin:
        return None
    return {"token": int(token), "finestra": int(fin),
            "percento": round(100 * int(token) / int(fin))}


def riga(u: dict | None) -> str:
    if not u:
        return ""
    return f"[CONTESTO] {_n(u['token'])} token su {_n(u['finestra'])} ({u['percento']} %)"


def testo_stato(cfg) -> str | None:
    """Per `calliope stato`: la scelta dell'ultimo avvio di Calliope (contesto.json)."""
    voce = leggi_salvato(cfg)
    if not voce:
        scritta = getattr(cfg, "llm_num_ctx", "auto")
        if isinstance(scritta, int):
            return f"Contesto: finestra {_n(scritta)} token (scritta in llm_num_ctx)."
        return (f"Contesto: finestra «auto», non ancora calcolata (la calcola Calliope "
                f"all'avvio); per ora {_n(finestra(cfg))} token.")
    try:
        b = Budget(**{k: v for k, v in voce.items() if k in Budget.__dataclass_fields__})
    except TypeError:
        return None
    scritta = getattr(cfg, "llm_num_ctx", "auto")
    if isinstance(scritta, int) and b.fonte != "configurazione":
        b.auto, b.finestra, b.fonte = b.finestra, scritta, "configurazione"
    quando = b.quando.replace("T", " ") if b.quando else "?"
    return f"Contesto: {b.frase()} (all'avvio del {quando})."
