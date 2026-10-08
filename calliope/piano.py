"""
Il piano dei modelli per questa macchina, in sola lettura (08/10/2026, fase 2 della taratura
della macchina: docs/ricerche/2026-10-07-taratura-macchina.md, §4 e §6.1).

    python -m calliope.stato --piano [--json]

Dall'inventario (`macchina.inventario`: memoria veloce, banda, motori, modelli presenti) e dal
catalogo (`calliope/modelli.py`: dati dichiarati con fonte e data, misure nostre, banco) un
piano proposto: voce, Whisper, guardiano, rilevatore di pericolo, embedding, finestra di
contesto, agente, Piper, funzioni a richiesta, variabili di Ollama, con i motivi e le stime.
**Non applica niente**: non scrive file, non scarica, non carica modelli, non cambia la
configurazione. Le decisioni ancora aperte del documento (§0) si scrivono come opzioni.

`piano()` è una funzione pura (si prova a secco con macchine finte, `prove/prova_piano.py`).
Le regole, nell'ordine di priorità della §4.1 (una voce più in basso non toglie mai memoria a
una più in alto):

1. **riserva** del sistema (GPU dedicata 0,8 GB su Windows, 0,3 su Linux; memoria unificata
   14 GB per sistema, Calliope e servizi accanto) e `contesto_margine_gb`;
2. **voce**: il modello più bravo **provato col banco** che ci sta con Whisper sulla GPU e la
   finestra minima, e la cui prima frase «pulita» stimata (STT + 400 token di lettura + primo
   token + 25 token di generazione) sta entro 0,8 s (= 1,2 s di `latenza_avviso_s` / 1,4, il
   rapporto vero/pulita della DGX). Se nessuno passa, il più veloce che ci sta, con l'avviso;
3. **Whisper**: sulla GPU se c'è un motore (faster-whisper con CUDA su x86-64, whisper.cpp con
   CUDA su Linux aarch64), altrimenti sulla CPU con `small`;
4. **guardiano** (minori o ospiti): 8B sulla GPU → 1B sulla GPU → 1B sulla CPU → nessun
   modello, con avviso fisso: mai tolto in silenzio;
5. **rilevatore di pericolo**: e4b separato se ci sta (in parallelo), altrimenti la voce stessa
   (in serie);
6. **embedding** sulla CPU, a Calliope inattiva;
7. **finestra di contesto** oltre il minimo, fin dove il tempo di rilettura e la memoria
   rimasta lo permettono (la misura di `contesto.json` vince sulla stima);
8. **agente**: separato se c'è (vLLM) o se ci sta (≥ 25 GB e ≥ 250 GB/s), altrimenti il 26B
   della voce su un secondo posto, altrimenti remoto o niente;
9. **Piper** sulla GPU solo con posto (le soglie di `taratura_voce`), **immagini** a richiesta
   solo con 13 GB liberi, OCR, satelliti insieme.

Le velocità: misurate da noi su quella GPU quando ci sono (catalogo), altrimenti η × banda /
byte letti a token (η 0,55, o quello che le misure danno per la macchina), al più 250 token/s.
"""
from __future__ import annotations

import os
import statistics
from dataclasses import asdict, dataclass, field

from . import modelli as cat

# Riserva del sistema (§4.3) [D]
RISERVA_DEDICATA = {"windows": 0.8, "linux": 0.3}
RISERVA_UNIFICATA = 14.0
RISERVA_CPU = 4.0
# Contesto CUDA e runtime per processo su una GPU dedicata [D: e4b sul portatile 4,7 GB con
# nvidia-smi contro ~3,3 di /api/ps]; sulla memoria unificata è già nella riserva
CONTESTO_CUDA_GB = {"windows": 0.9, "linux": 0.5}
BUFFER_GB = 0.35                 # buffer di calcolo di Ollama a modello [M 05/10]
FATTORE_KV = 1.1                 # come contesto.FATTORE_KV
# Windows su memoria unificata (RTX Spark): la GPU ne vede ~80 % dopo la riserva (02/10)
QUOTA_GPU_WINDOWS_UNIFICATA = 0.8
# Soglie della voce (§4.2)
SOGLIA_PULITA_S = 0.8
N_NUOVI, N_FRASE, T_PRIMO_S = 400, 25, 0.1
RILETTURA_FREDDA_S = 4.0         # il prefisso intero a cache persa: p90 al cambio di persona
PREFISSO = 12000                 # token di prefisso [M DGX 12 425–12 631, 05–07/10]
FINESTRA_MIN = 16384
PASSO = 4096
# Agente separato (§4.6)
AGENTE_LIBERI_GB = 25.0
AGENTE_BANDA_GBS = 250.0
VLLM_UTILIZZO = 0.4              # gpu_memory_utilization dell'agente sulla DGX [M]
# Piper sulla GPU (calliope/taratura_voce.py, 07/10)
PIPER_MIN_DEDICATA_GB = 12.0
PIPER_MARGINE = {"dedicata": 2.0, "unificata": 8.0}
GUARDIANO_CTX = 2048


@dataclass
class Funzioni:
    """Cosa si vuole da Calliope su questa macchina (dalla configurazione: `da_config`)."""
    guardiano: bool = True        # minori registrabili o guardiano anche per gli ospiti
    rilevatore: bool = True
    agenti: bool = True
    agente_remoto: bool = False   # c'è un altro computer per gli agenti (dgx.yaml, agenti_url)
    immagini: bool = True
    satelliti: int = 1            # conversazioni contemporanee volute
    posti: int | None = None      # OLLAMA_NUM_PARALLEL; None = dal servizio, altrimenti 1
    rilettura_s: float = 4.0      # contesto_rilettura_max_s
    soglia_morbida: float = 0.75  # contesto_soglia_morbida (con la compressione)
    compressione: bool = True
    margine_gb: float = 0.5       # contesto_margine_gb
    oggi: dict = field(default_factory=dict)        # le scelte scritte oggi, per il confronto
    contesto: dict = field(default_factory=dict)    # contesto.json della voce, se c'è


@dataclass
class Scelta:
    ruolo: str
    scelta: str
    dove: str = ""                # GPU, CPU, vLLM, remoto
    memoria_gb: float = 0.0       # nel pool veloce (o nella RAM per la CPU)
    stima: str = ""
    stato: str = "ok"             # ok | avviso | no
    motivo: str = ""
    oggi: str | None = None       # «come oggi», o cosa c'è oggi se diverso
    fonte: str = ""


@dataclass
class Piano:
    macchina: str
    classe: str
    pool_gb: float
    riserva_gb: float
    usati_gb: float = 0.0
    liberi_gb: float = 0.0
    scelte: list[Scelta] = field(default_factory=list)
    ollama: dict = field(default_factory=dict)
    non_sostenibili: list[str] = field(default_factory=list)
    candidati: list[dict] = field(default_factory=list)
    decisioni: list[dict] = field(default_factory=list)
    avvisi: list[str] = field(default_factory=list)
    catalogo: str = cat.VERSIONE

    def scelta(self, ruolo: str) -> Scelta | None:
        return next((s for s in self.scelte if s.ruolo == ruolo), None)

    def as_json(self) -> dict:
        return asdict(self)


# Le sei decisioni aperte del documento (§0): il piano le scrive, non le prende
DECISIONI = {
    1: ("Il piano applica o propone?",
        ["il piano accettato si applica ai soli campi «auto» (proposta del documento)",
         "solo proposta: chi amministra scrive a mano calliope.locale.yaml"]),
    2: ("Quali modelli entrano come scelte automatiche oltre ai tre Gemma 4 provati?",
        ["nessuno finché non passa il banco su una macchina nostra (proposta)",
         "gemma4:12b e qwen3.5:9b come candidati da provare per 12–16 GB"]),
    3: ("Guardiano senza posto sulla GPU",
        ["llama-guard3:1b sulla CPU con avviso (proposta: costa solo ai minori)",
         "1B sulla GPU togliendo Whisper alla GPU (Whisper sulla CPU ~5 s a ogni frase)"]),
    4: ("Agente senza posto per un modello separato",
        ["la voce stessa su un secondo posto, thinking acceso, con l'arbitro (proposta)",
         "agente con gli esperti nella RAM di sistema, lento e solo di notte"]),
    5: ("Calliope sulla sola CPU",
        ["«questa macchina va bene come satellite» (proposta)",
         "Calliope ridotta (pochi tool, un livello), da misurare"]),
    6: ("Variabili di Ollama nel servizio",
        ["il piano propone il comando (sudo) e non le tocca (proposta)",
         "Calliope le scrive da sé (servirebbe sudo)"]),
}


def _gb(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def _s(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _n(x: int) -> str:
    return f"{int(x):,}".replace(",", ".")


class _Macchina:
    """I numeri della macchina che servono alle regole, dall'inventario."""

    def __init__(self, inv: dict, f: Funzioni):
        self.inv = inv
        self.os = inv.get("os") or "linux"
        self.arch = inv.get("arch") or "x86_64"
        g = inv.get("gpu") or None
        self.gpu = g if g and g.get("memoria_gb") else None
        ram = float(inv.get("ram_gb") or 0)
        motori = inv.get("motori") or {}
        self.motori = motori
        if self.gpu is None:
            self.tipo, self.pool, self.banda = "cpu", ram, cat.BANDA_RAM_GBS
            self.riserva, self.cuda_proc = RISERVA_CPU, 0.0
            self.lettura_rel, self.chiave = cat.LETTURA_REL_CPU, "cpu"
        elif g.get("unificata"):
            self.tipo, self.banda = "unificata", float(g["banda_gbs"])
            self.riserva, self.cuda_proc = RISERVA_UNIFICATA, 0.0
            self.pool = float(g["memoria_gb"])
            if self.os == "windows":
                self.pool = RISERVA_UNIFICATA + (self.pool - RISERVA_UNIFICATA) \
                    * QUOTA_GPU_WINDOWS_UNIFICATA
            self.lettura_rel, self.chiave = float(g.get("lettura_rel") or 1), g.get("chiave")
        else:
            self.tipo, self.banda = "dedicata", float(g["banda_gbs"])
            self.pool = float(g["memoria_gb"])
            self.riserva = RISERVA_DEDICATA.get(self.os, 0.3)
            self.cuda_proc = CONTESTO_CUDA_GB.get(self.os, 0.5)
            self.lettura_rel, self.chiave = float(g.get("lettura_rel") or 1), g.get("chiave")
        self.ram = ram
        self.margine = f.margine_gb
        self.disponibile = self.pool - self.riserva - self.margine
        self.usati = 0.0
        o = motori.get("ollama") or {}
        var = o.get("variabili") or {}
        try:
            letti = int(var.get("OLLAMA_NUM_PARALLEL") or 0)
        except ValueError:
            letti = 0
        self.posti_letti = letti or None
        self.posti = f.posti or letti or 1
        self.eta, self.eta_fonte = self._eta()
        self.libera_adesso, self.altri = self._altri()

    def _altri(self) -> tuple[float | None, float]:
        """(libera adesso, GB tenuti da programmi che non sono di Calliope): la memoria del
        pool meno la libera e meno i modelli di Calliope caricati (§5.1, §7.1). Sulla sola CPU
        e senza una lettura della libera: (None, 0)."""
        g = self.inv.get("gpu") or {}
        libera = g.get("libera_gb") if self.tipo != "cpu" else None
        if libera is None:
            return None, 0.0
        o = self.motori.get("ollama") or {}
        di_calliope = sum(c.get("gb") or 0 for c in o.get("caricati") or [])
        for v in self.motori.get("vllm") or []:
            di_calliope += (v.get("gpu_memory_utilization") or 0) * self.pool
        if (self.motori.get("whisper_server") or {}).get("attivo"):
            di_calliope += cat.WHISPER["cpp-gpu"].memoria_gb
        return float(libera), max(0.0, self.pool - float(libera) - di_calliope)

    @property
    def liberi_adesso(self) -> float:
        """Come `liberi`, con gli altri programmi di adesso al posto della riserva se tengono
        di più."""
        return self.liberi - max(0.0, self.altri - self.riserva)

    @property
    def liberi(self) -> float:
        return self.disponibile - self.usati

    def nome(self) -> str:
        g = self.inv.get("gpu") or {}
        pezzi = []
        if self.gpu is not None:
            pezzi.append(f"{g.get('nome')} " + (
                f"{_gb(self.pool)} GB unificati" if self.tipo == "unificata"
                else f"{_gb(self.pool)} GB") + f" ({int(self.banda)} GB/s)")
        else:
            pezzi.append("nessuna GPU")
        if self.ram:
            pezzi.append(f"{_gb(self.ram)} GB di RAM")
        pezzi.append(f"{self.inv.get('sistema') or self.os} {self.arch}")
        return ", ".join(pezzi)

    def classe(self) -> str:
        if self.tipo == "cpu":
            return "solo CPU"
        if self.tipo == "unificata":
            if self.os == "windows" and self.arch == "aarch64":
                return "Windows su ARM, memoria unificata"
            return f"memoria unificata {round(self.pool / 16) * 16 or round(self.pool)} GB"
        for n in (8, 12, 16, 24, 32, 48, 96):
            if self.pool <= n * 1.12:
                return f"GPU {n} GB"
        return f"GPU {round(self.pool)} GB"

    def _eta(self) -> tuple[float, str]:
        """η della macchina dalle misure nostre su questa GPU (§3.5), o quello di base."""
        vals = []
        for m in cat.MODELLI.values():
            mis = m.misure.get(self.chiave or "")
            if mis and mis.tps and m.motore == "ollama":
                vals.append(mis.tps * m.letti_gb / self.banda)
        if vals:
            return statistics.median(vals), "misurato su questa GPU"
        return cat.ETA, "di base (nessuna misura su questa GPU)"

    def velocita(self, m: cat.Modello) -> tuple[float, float, str]:
        """(generazione, lettura, fonte) di un modello su questa macchina."""
        mis = m.misure.get(self.chiave or "")
        tps = mis.tps if mis and mis.tps else min(cat.TETTO_TPS,
                                                   self.eta * self.banda / m.letti_gb)
        lettura = mis.lettura if mis and mis.lettura else \
            cat.LETTURA_RIF * min(2.0, cat.ATTIVI_RIF / max(0.5, m.attivi_b)) * self.lettura_rel
        fonte = "misurata" if mis and mis.tps else "stimata"
        return tps, lettura, fonte

    def memoria(self, m: cat.Modello, ctx: int, posti: int | None = None,
                gpu: bool = True) -> float:
        """Memoria di un modello caricato (§4.3): pesi, buffer, cache per i posti, contesto
        CUDA su una GPU dedicata. vLLM: il blocco prenotato all'avvio."""
        if m.motore == "vllm":
            return VLLM_UTILIZZO * self.pool
        p = posti or self.posti
        kv = (m.kv_kib * 1024 * ctx + m.kv_fissi_mib * 2**20) * FATTORE_KV * p / 1e9
        return m.pesi_gb + BUFFER_GB + kv + (self.cuda_proc if gpu else 0.0)

    def ci_sta(self, gb: float) -> bool:
        return gb <= self.liberi + 1e-9


def _whisper(mc: _Macchina) -> tuple[str | None, str]:
    """(chiave in cat.WHISPER della GPU, motivo) o (None, perché sulla CPU)."""
    if mc.gpu is None:
        return None, "nessuna GPU"
    prod = (mc.inv.get("gpu") or {}).get("produttore")
    if prod != "nvidia":
        return "cpp-gpu", "whisper.cpp (Vulkan o Metal: da verificare su questa GPU)"
    if mc.os == "linux" and mc.arch == "aarch64":
        return "cpp-gpu", "whisper.cpp con CUDA (CTranslate2 per aarch64 è solo CPU)"
    if mc.os == "windows" and mc.arch == "aarch64":
        return "cpp-gpu", "whisper.cpp con CUDA (ctranslate2 senza wheel win_arm64)"
    return "fw-gpu", "faster-whisper con CUDA"


def _arrotonda(x: float) -> int:
    return int(x) // PASSO * PASSO


def _finestra_tempo(mc: _Macchina, f: Funzioni, lettura: float, massimo: int) -> int:
    if f.compressione:
        t = (PREFISSO + lettura * f.rilettura_s) / max(0.1, f.soglia_morbida)
    else:
        t = PREFISSO + lettura * f.rilettura_s
    return max(FINESTRA_MIN, min(massimo, _arrotonda(t)))


def _oggi(f: Funzioni, ruolo: str, scelta: str) -> str | None:
    v = f.oggi.get(ruolo)
    if v is None:
        return None
    return "come oggi" if str(v) == scelta else f"oggi {v}"


def piano(inv: dict, funzioni: Funzioni | None = None) -> Piano:
    """Il piano per la macchina `inv` (macchina.inventario o una macchina finta)."""
    f = funzioni or Funzioni()
    mc = _Macchina(inv, f)
    p = Piano(macchina=mc.nome(), classe=mc.classe(), pool_gb=round(mc.pool, 2),
              riserva_gb=round(mc.riserva + mc.margine, 2))
    p.avvisi.extend(inv.get("avvisi") or [])
    dove_gpu = "CPU" if mc.tipo == "cpu" else "GPU"
    motori = mc.motori
    linux_nvidia = mc.os == "linux" and (inv.get("gpu") or {}).get("produttore") == "nvidia"

    # 1. riserva
    p.scelte.append(Scelta("riserva", "sistema e margine", mc.tipo, round(mc.riserva + mc.margine, 2),
                           motivo={"dedicata": "desktop e driver, più contesto_margine_gb",
                                   "unificata": "sistema, Calliope (Piper, CAM++, VAD, "
                                                "biblioteca) e servizi accanto",
                                   "cpu": "sistema e Calliope"}[mc.tipo]))

    # 2–3. voce e Whisper, insieme (§4.1, punto 3: il controllo è congiunto)
    wk, wmot = _whisper(mc)
    w_gpu = cat.WHISPER[wk] if wk else None
    w_cpu = cat.WHISPER["small-cpu"]
    valutate = []
    for nome in cat.SCALA_VOCE:
        m = cat.MODELLI[nome]
        tps, lettura, fonte = mc.velocita(m)
        mem = mc.memoria(m, FINESTRA_MIN, gpu=mc.tipo == "dedicata")
        con_w = w_gpu is not None and mem + w_gpu.memoria_gb <= mc.liberi
        stt = w_gpu.frase_s if con_w else w_cpu.frase_s
        pulita = stt + N_NUOVI / lettura + T_PRIMO_S + N_FRASE / tps
        valutate.append({"m": m, "tps": tps, "lettura": lettura, "fonte": fonte, "mem": mem,
                         "con_whisper": con_w, "ci_sta": mem <= mc.liberi, "pulita": pulita,
                         "fredda": PREFISSO / lettura})
    voce = next((v for v in valutate if v["con_whisper"] and v["pulita"] <= SOGLIA_PULITA_S),
                None)
    if voce is None:
        voce = next((v for v in valutate if v["ci_sta"] and v["pulita"] <= SOGLIA_PULITA_S),
                    None)
    stato_voce, motivo_voce = "ok", ""
    if voce is None:
        dentro = [v for v in valutate if v["ci_sta"]]
        voce = min(dentro, key=lambda v: v["pulita"]) if dentro else None
        stato_voce = "avviso"
        motivo_voce = (f"nessun modello provato sta entro {_s(SOGLIA_PULITA_S)} s di prima frase "
                       "pulita: il più veloce che ci sta")
    if voce is None:
        p.scelte.append(Scelta("voce", "nessuna", "remoto", stato="no",
                               motivo="nessun modello provato ci sta: questa macchina va bene "
                                      "come satellite"))
        p.decisioni.append(_decisione(5))
        _fine(p, mc, f)
        return p
    m_voce = voce["m"]
    migliori = [v["m"].nome for v in valutate[:valutate.index(voce)]]
    if not motivo_voce:
        if migliori:
            perche = []
            for v in valutate[:valutate.index(voce)]:
                if not v["ci_sta"]:
                    perche.append(f"{v['m'].nome} non ci sta ({_gb(v['mem'])} GB)")
                elif not v["con_whisper"]:
                    perche.append(f"{v['m'].nome} lascerebbe Whisper sulla CPU")
                else:
                    perche.append(f"{v['m'].nome} supera la soglia ({_s(v['pulita'])} s)")
            motivo_voce = "; ".join(perche)
        else:
            motivo_voce = "il più bravo provato col banco, entro la soglia"
    if voce["fredda"] > RILETTURA_FREDDA_S:
        p.avvisi.append(f"La rilettura a freddo del prefisso ({_n(PREFISSO)} token) costerebbe "
                        f"~{_s(voce['fredda'])} s a ogni cambio di persona o di livello.")
    mc.usati += voce["mem"]
    sv = Scelta("voce", m_voce.nome, dove_gpu, round(voce["mem"], 2),
                f"{round(voce['tps'])} token/s ({voce['fonte']}), lettura "
                f"{_n(round(voce['lettura']))} token/s, prima frase pulita ~{_s(voce['pulita'])} s",
                stato_voce, motivo_voce, _oggi(f, "voce", m_voce.nome), m_voce.banco_nota)
    p.scelte.append(sv)

    # Whisper
    if voce["con_whisper"]:
        mc.usati += w_gpu.memoria_gb
        oggi_w = f"{w_gpu.nome}, {w_gpu.motore}" + (" (server)" if w_gpu.motore == "whisper.cpp"
                                                    else "")
        sw = Scelta("whisper", oggi_w, "GPU", w_gpu.memoria_gb, f"~{_s(w_gpu.frase_s)} s a frase",
                    "ok", wmot, fonte=w_gpu.fonte)
        if w_gpu.motore == "whisper.cpp" and motori.get("whisper_server"):
            sw.oggi = "come oggi" if motori["whisper_server"].get("attivo") else \
                "oggi server non raggiungibile"
        elif f.oggi.get("whisper"):
            sw.oggi = "come oggi" if f.oggi["whisper"].startswith(w_gpu.motore) \
                else f"oggi {f.oggi['whisper']}"
    else:
        perche = wmot if w_gpu is None else "sulla GPU non ci sta accanto alla voce"
        sw = Scelta("whisper", f"{w_cpu.nome}, faster-whisper int8, beam 1", "CPU", 0.0,
                    f"~{_s(w_cpu.frase_s)} s a frase (da misurare)", "avviso",
                    f"{perche}: capisce peggio (WER attesa ~+10 punti, da misurare)",
                    fonte=w_cpu.fonte)
    p.scelte.append(sw)

    # 4. guardiano
    if f.guardiano:
        g_scelta = None
        for nome in cat.SCALA_GUARDIANO:
            m = cat.MODELLI[nome]
            mem = mc.memoria(m, GUARDIANO_CTX, gpu=mc.tipo == "dedicata")
            if mc.ci_sta(mem):
                primo = nome == cat.SCALA_GUARDIANO[0]
                g_scelta = Scelta("guardiano", nome, dove_gpu, round(mem, 2),
                                  "sulla CPU: secondi a giudizio (da misurare)"
                                  if mc.tipo == "cpu" else "",
                                  "ok" if primo and mc.tipo != "cpu" else "avviso",
                                  "i minori e gli ospiti lo vogliono" if primo else
                                  f"{cat.SCALA_GUARDIANO[0]} non ci sta: il più piccolo, qualità "
                                  "sul banco dei minori non misurata",
                                  _oggi(f, "guardiano", nome), m.banco_nota)
                mc.usati += mem
                break
        if g_scelta is None:
            uno = cat.MODELLI[cat.SCALA_GUARDIANO[-1]]
            if mc.tipo != "cpu" and mc.ram - 8 > mc.memoria(uno, GUARDIANO_CTX, gpu=False):
                g_scelta = Scelta("guardiano", uno.nome, "CPU", 0.0, "~1 s a giudizio (da "
                                  "misurare)", "avviso",
                                  "sulla GPU non ci stanno né l'8B né l'1B: i turni dei minori "
                                  "sono più lenti (avviso all'avvio)",
                                  _oggi(f, "guardiano", uno.nome), uno.banco_nota)
                p.decisioni.append(_decisione(3))
            else:
                g_scelta = Scelta("guardiano", "nessun modello", "", 0.0, "", "avviso",
                                  "non c'è posto: restano istruzioni e regole fisse, con "
                                  "avviso fisso all'avvio (mai spento in silenzio)")
        p.scelte.append(g_scelta)
    else:
        p.scelte.append(Scelta("guardiano", "spento", motivo="né minori né ospiti col guardiano "
                               "(guardiano_ospiti)", oggi=_oggi(f, "guardiano", "spento")))

    # 5. rilevatore di pericolo
    if f.guardiano and f.rilevatore:
        ril = cat.MODELLI[cat.RILEVATORE]
        if m_voce.nome == ril.nome:
            p.scelte.append(Scelta("rilevatore", f"la voce stessa ({ril.nome})", dove_gpu, 0.0,
                                   "+0,3–0,5 s sui turni dei minori", "ok",
                                   "stesso modello della voce: il giudizio si aspetta prima "
                                   "della risposta (in serie)", _oggi(f, "rilevatore", ril.nome)))
        else:
            mem = mc.memoria(ril, GUARDIANO_CTX, gpu=mc.tipo == "dedicata")
            if mc.ci_sta(mem):
                mc.usati += mem
                p.scelte.append(Scelta("rilevatore", ril.nome, dove_gpu, round(mem, 2),
                                       "0,34–0,46 s di mediana (DGX)" if mc.chiave == "GB10"
                                       else "sulla CPU: lento (da misurare)"
                                       if mc.tipo == "cpu" else "", "ok",
                                       "separato: in parallelo, nessuna attesa sui turni dei "
                                       "minori", _oggi(f, "rilevatore", ril.nome)))
            else:
                p.scelte.append(Scelta("rilevatore", f"la voce stessa ({m_voce.nome})", dove_gpu,
                                       0.0, "+0,3–0,5 s sui turni dei minori", "avviso",
                                       f"{ril.nome} separato non ci sta ({_gb(mem)} GB): in "
                                       "serie", _oggi(f, "rilevatore", m_voce.nome)))

    # 6. embedding
    emb = cat.MODELLI[cat.EMBEDDING]
    emb_mem = emb.pesi_gb if mc.tipo == "unificata" else 0.0
    mc.usati += emb_mem
    p.scelte.append(Scelta("embedding", emb.nome, "CPU", round(emb_mem, 2), "",
                           "ok", "sulla CPU, a Calliope inattiva (ollama_carico)",
                           _oggi(f, "embedding", emb.nome)))

    # 7. finestra di contesto oltre il minimo
    salvata = f.contesto or {}
    massimo = m_voce.contesto_max
    kv_tok = m_voce.kv_kib * 1024 * FATTORE_KV * mc.posti / 1e9
    tempo = _finestra_tempo(mc, f, voce["lettura"], massimo)
    fonte_ctx = "stimata dal tempo di rilettura"
    if salvata.get("finestra") and salvata.get("modello_voce") == m_voce.nome:
        tempo, fonte_ctx = int(salvata["finestra"]), \
            f"misurata all'avvio di Calliope ({salvata.get('motivo') or 'tempo'})"
    memoria_tok = FINESTRA_MIN + int(max(0.0, mc.liberi) / kv_tok) if kv_tok else massimo
    fin = min(tempo, _arrotonda(memoria_tok), massimo)
    fin = max(FINESTRA_MIN, fin) if memoria_tok >= FINESTRA_MIN else FINESTRA_MIN
    extra = kv_tok * (fin - FINESTRA_MIN)
    mc.usati += extra
    sv.memoria_gb = round(sv.memoria_gb + extra, 2)
    perche = "il tempo di rilettura" if fin == tempo else "la memoria" if fin < tempo else \
        "il massimo del modello"
    p.scelte.append(Scelta("contesto", f"{_n(fin)} token", "", round(extra, 2),
                           f"{mc.posti} " + ("posto" if mc.posti == 1 else "posti")
                           + " di Ollama",
                           "ok", f"{perche}; {fonte_ctx}",
                           _oggi(f, "contesto", f"{_n(fin)} token")))

    # 8. agente
    _agente(p, mc, f, m_voce, linux_nvidia)

    # 9. Piper, immagini, OCR, satelliti
    _piper(p, mc, f)
    _richiesta(p, mc, f, m_voce)
    if mc.tipo == "cpu":
        p.decisioni.append(_decisione(5))
        p.avvisi.append("Sulla sola CPU la lettura del prompt costa secondi a ogni turno: questa "
                        "macchina va bene come satellite (decisione 5).")
    _fine(p, mc, f)
    return p


def _agente(p: Piano, mc: _Macchina, f: Funzioni, m_voce: cat.Modello, linux_nvidia: bool):
    if not f.agenti:
        p.scelte.append(Scelta("agente", "spento", motivo="agenti_enabled è falso"))
        return
    vllm = [v for v in mc.motori.get("vllm") or [] if v.get("modelli")]
    agente_vllm = next(((v, m) for v in vllm for m in v["modelli"]
                        if m.get("id") == cat.AGENTE_VLLM), None)
    if agente_vllm is None and vllm:
        agente_vllm = (vllm[0], vllm[0]["modelli"][0])
    if agente_vllm:
        v, m = agente_vllm
        uso = v.get("gpu_memory_utilization") or VLLM_UTILIZZO
        mem = uso * mc.pool
        ok = mc.ci_sta(mem)
        mc.usati += mem
        mis = cat.misura(cat.AGENTE_VLLM, mc.chiave) if m.get("id") == cat.AGENTE_VLLM else None
        p.scelte.append(Scelta(
            "agente", f"{m.get('id')} su vLLM", "vLLM", round(mem, 2),
            (f"{round(mis.tps)} token/s (misurata), " if mis and mis.tps else "")
            + f"gpu_memory_utilization {uso}".replace(".", ",")
            + (f", cache {_n(v['cache_token'])} token" if v.get("cache_token") else ""),
            "ok" if ok else "avviso",
            "separato, già acceso: prenota la sua memoria all'avvio" if ok else
            "acceso, ma con il resto del piano la memoria non basta",
            "come oggi", cat.MODELLI[cat.AGENTE_VLLM].banco_nota
            if m.get("id") == cat.AGENTE_VLLM else ""))
        return
    ag = cat.MODELLI[cat.AGENTE_OLLAMA]
    mem = mc.memoria(ag, 32768, posti=1, gpu=mc.tipo == "dedicata")
    if mc.liberi >= max(AGENTE_LIBERI_GB, mem) and mc.banda >= AGENTE_BANDA_GBS:
        mc.usati += mem
        dove = "vLLM (NVFP4)" if linux_nvidia else "Ollama"
        p.scelte.append(Scelta("agente", f"Qwen3.6-35B-A3B su {dove}", dove, round(mem, 2),
                               "da installare", "ok", "separato: ci sta accanto alla voce, a "
                               "Whisper e al guardiano"))
        return
    if m_voce.nome == cat.SCALA_VOCE[0]:
        p.scelte.append(Scelta("agente", f"{m_voce.nome} (la voce) su un secondo posto", "GPU",
                               0.0, "thinking acceso; l'arbitro lo ferma quando qualcuno parla",
                               "avviso", "un agente separato non ci sta (Qwen3.6-35B-A3B "
                               f"{_gb(mem)} GB): più debole sul codice"))
        if mc.posti < 2:
            p.ollama.setdefault("proposte", []).append(
                "OLLAMA_NUM_PARALLEL=2: il secondo posto per l'agente (o per un secondo "
                "satellite)")
        p.decisioni.append(_decisione(4))
        return
    if f.agente_remoto:
        p.scelte.append(Scelta("agente", "su un altro computer (agenti_url, dgx.yaml)", "remoto",
                               motivo="qui non ci sta", oggi=_oggi(f, "agente", "remoto")))
        return
    p.scelte.append(Scelta("agente", "da configurare", "", 0.0, "", "avviso",
                           "su questa macchina non c'è posto per un agente; si può usare quello "
                           "di un altro computer"))


def _piper(p: Piano, mc: _Macchina, f: Funzioni):
    cuda = mc.motori.get("onnxruntime_cuda")
    nvidia = (mc.inv.get("gpu") or {}).get("produttore") == "nvidia"
    if mc.tipo == "cpu" or not nvidia:
        p.scelte.append(Scelta("piper", "CPU", "CPU", motivo="nessuna GPU NVIDIA",
                               oggi=_oggi(f, "piper", "cpu")))
        return
    if mc.tipo == "dedicata" and mc.pool < PIPER_MIN_DEDICATA_GB:
        p.scelte.append(Scelta("piper", "CPU", "CPU", motivo=f"GPU da {_gb(mc.pool)} GB: la "
                               "tengono la voce e Whisper", oggi=_oggi(f, "piper", "cpu")))
        return
    serve = cat.PIPER_GPU_GB + PIPER_MARGINE[mc.tipo]
    if mc.liberi < serve:
        p.scelte.append(Scelta("piper", "CPU", "CPU", motivo=f"dopo il piano restano "
                               f"{_gb(mc.liberi)} GB: ne servono {_gb(serve)} col margine",
                               oggi=_oggi(f, "piper", "cpu")))
        return
    mc.usati += cat.PIPER_GPU_GB
    motivo = "c'è posto; la taratura sceglie la GPU solo se è 2 volte più veloce della CPU"
    stato = "ok"
    if mc.liberi_adesso < 0:
        motivo += ("; adesso, con gli altri programmi accesi, la memoria non basta: la taratura "
                   "la proverà solo con posto")
        stato = "avviso"
    if cuda is False:
        motivo += " (serve onnxruntime con CUDA: qui non c'è)"
        stato = "avviso"
    p.scelte.append(Scelta("piper", "GPU (se la taratura conferma)", "GPU", cat.PIPER_GPU_GB,
                           "0,63 ms a carattere sulla DGX contro 3,5 sulla CPU", stato, motivo,
                           _oggi(f, "piper", "cuda")))


def _richiesta(p: Piano, mc: _Macchina, f: Funzioni, m_voce: cat.Modello):
    agente = p.scelta("agente")
    separato = agente is not None and agente.dove in ("vLLM", "Ollama", "vLLM (NVFP4)")
    p.scelte.append(Scelta("ocr", "l'agente" if separato else "la voce, a Calliope inattiva",
                           motivo="legge le immagini dell'archivio" if separato else
                           "Gemma 4 vede le immagini: a lotti, di notte"))
    if f.immagini and mc.tipo == "cpu":
        p.non_sostenibili.append("immagini: serve una GPU")
    elif f.immagini:
        if mc.liberi >= cat.IMMAGINI_GB:
            adesso = mc.liberi_adesso >= cat.IMMAGINI_GB
            p.scelte.append(Scelta(
                "immagini", "FLUX.2 [klein] 4B a richiesta", dove="GPU",
                stima=f"{_gb(cat.IMMAGINI_GB)} GB per qualche secondo",
                stato="ok" if adesso else "avviso",
                motivo=f"dopo il piano restano {_gb(mc.liberi)} GB"
                + ("" if adesso else f"; adesso, con gli altri programmi accesi, "
                   f"{_gb(max(0.0, mc.liberi_adesso))}: non adesso")))
        else:
            p.non_sostenibili.append(f"immagini: servono {_gb(cat.IMMAGINI_GB)} GB e dopo il "
                                     f"piano ne restano {_gb(max(0.0, mc.liberi))}")
    if f.satelliti > 1 and mc.posti < f.satelliti:
        p.non_sostenibili.append(f"{f.satelliti} satelliti insieme: Ollama ha {mc.posti} posto "
                                 f"per la voce (OLLAMA_NUM_PARALLEL)")
    if agente is not None and agente.scelta != "spento" and not separato \
            and not agente.scelta.startswith(m_voce.nome):
        p.non_sostenibili.append("agente locale")


def _decisione(n: int) -> dict:
    titolo, opzioni = DECISIONI[n]
    return {"numero": n, "titolo": titolo, "opzioni": opzioni}


def _fine(p: Piano, mc: _Macchina, f: Funzioni):
    """Variabili di Ollama, memoria di adesso, decisioni sempre aperte, candidati."""
    residenti = [s.scelta for s in p.scelte if s.ruolo in ("voce", "guardiano", "rilevatore")
                 and s.dove in ("GPU", "CPU") and not s.scelta.startswith(("la voce", "nessun"))]
    residenti.append(cat.EMBEDDING)
    o = (mc.motori.get("ollama") or {})
    var = o.get("variabili") or {}
    p.ollama.update(max_loaded_models=len(residenti), residenti=residenti,
                    num_parallel=mc.posti, letti=var, versione=o.get("versione"))
    try:
        letto = int(var.get("OLLAMA_MAX_LOADED_MODELS") or 0)
    except ValueError:
        letto = 0
    if letto and letto < len(residenti):
        p.ollama.setdefault("proposte", []).append(
            f"OLLAMA_MAX_LOADED_MODELS={len(residenti)} (oggi {letto})")
    elif not letto and len(residenti) > 3:
        p.ollama.setdefault("proposte", []).append(
            f"OLLAMA_MAX_LOADED_MODELS={len(residenti)} (il predefinito di Ollama è 3)")
    if p.ollama.get("proposte"):
        p.decisioni.append(_decisione(6))
    if not o:
        p.avvisi.append("Ollama non risponde su questa macchina: il piano vale una volta "
                        "installato.")
    p.usati_gb = round(mc.usati + mc.riserva + mc.margine, 2)
    p.liberi_gb = round(mc.liberi, 2)
    # La memoria di adesso (§5.1, §7.1): con quello che gira oggi accanto
    if mc.libera_adesso is not None and mc.altri > mc.riserva + 0.5:
        restano = mc.liberi_adesso
        p.avvisi.append(
            f"Adesso sono liberi {_gb(mc.libera_adesso)} GB: oltre ai modelli di Calliope, altri "
            f"programmi tengono ~{_gb(mc.altri)} GB (la riserva del piano è {_gb(mc.riserva)}). "
            + (f"Con loro accesi al piano restano {_gb(restano)} GB." if restano >= 0 else
               f"Con loro accesi il piano non ci sta (mancano {_gb(-restano)} GB)."))
    p.decisioni.insert(0, _decisione(1))
    p.decisioni.insert(1, _decisione(2))
    # Candidati da provare (decisione 2): stime, mai scelti
    for nome in cat.CANDIDATI_VOCE:
        m = cat.MODELLI[nome]
        tps, lettura, _ = mc.velocita(m)
        mem = mc.memoria(m, FINESTRA_MIN, gpu=mc.tipo == "dedicata")
        p.candidati.append({"modello": nome, "memoria_gb": round(mem, 1),
                            "token_s": round(tps), "nota": m.nota or "da provare col banco"})
    vista = set()
    p.decisioni = [d for d in p.decisioni if not (d["numero"] in vista or vista.add(d["numero"]))]


# ─────────────────────────── dalla configurazione ───────────────────────────
def da_config(cfg, inv: dict | None = None) -> Funzioni:
    """Le funzioni volute e le scelte di oggi, dalla configurazione già caricata."""
    f = Funzioni()
    f.guardiano = bool(getattr(cfg, "guardiano_enabled", True)) and bool(
        getattr(cfg, "minori_enabled", True) or getattr(cfg, "guardiano_ospiti", True))
    f.rilevatore = bool(getattr(cfg, "guardiano_pericolo", True))
    f.agenti = bool(getattr(cfg, "agenti_enabled", True))
    dgx = getattr(cfg, "agenti_config_file", "") or ""
    if dgx and not os.path.isabs(dgx):
        dgx = os.path.join(getattr(cfg, "config_dir", None) or ".", dgx)
    f.agente_remoto = bool(getattr(cfg, "agenti_url", None)) or os.path.exists(dgx)
    f.immagini = True
    f.satelliti = max(1, int(getattr(cfg, "conversazioni_parallele", 1) or 1))
    f.rilettura_s = float(getattr(cfg, "contesto_rilettura_max_s", 4.0) or 4.0)
    f.soglia_morbida = float(getattr(cfg, "contesto_soglia_morbida", 0.75) or 0.75)
    f.compressione = str(getattr(cfg, "contesto_riassuntore", "spento") or "spento").lower() \
        != "spento"
    f.margine_gb = float(getattr(cfg, "contesto_margine_gb", 0.5) or 0.5)
    oggi = {"voce": getattr(cfg, "llm_model", None),
            "guardiano": getattr(cfg, "guardiano_modello", None) if f.guardiano else "spento",
            "rilevatore": (getattr(cfg, "guardiano_pericolo_modello", None)
                           or getattr(cfg, "llm_model", None)),
            "embedding": getattr(cfg, "conversazioni_embedding", None),
            "piper": str(getattr(cfg, "tts_dispositivo", "auto"))}
    if getattr(cfg, "stt_motore", "locale") == "server":
        oggi["whisper"] = "whisper.cpp (server)"
    else:
        oggi["whisper"] = (f"faster-whisper {getattr(cfg, 'whisper_model', '')} "
                           f"{getattr(cfg, 'whisper_device', '')}")
    if oggi["piper"] == "auto":
        oggi.pop("piper")
    f.oggi = {k: v for k, v in oggi.items() if v}
    try:
        from . import contesto
        salv = contesto.leggi_salvato(cfg) or {}
        if salv.get("finestra"):
            f.contesto = {"finestra": salv["finestra"], "motivo": salv.get("motivo"),
                          "modello_voce": getattr(cfg, "llm_model", None)}
            f.oggi["contesto"] = f"{_n(salv['finestra'])} token"
    except Exception:  # noqa: BLE001 — senza contesto.json si stima
        pass
    return f


# ─────────────────────────── testo per il terminale ───────────────────────────
_SEGNO = {"ok": "✓", "avviso": "⚠", "no": "✗"}
_NOMI = {"riserva": "Riserva", "voce": "Voce", "whisper": "Whisper", "guardiano": "Guardiano",
         "rilevatore": "Rilevatore", "embedding": "Embedding", "contesto": "Contesto",
         "agente": "Agente", "piper": "Piper", "ocr": "OCR archivio", "immagini": "Immagini"}


def testo(p: Piano) -> str:
    r = [f"Macchina: {p.macchina} — classe «{p.classe}»",
         f"Piano proposto (sola lettura, catalogo del {p.catalogo}): memoria {_gb(p.usati_gb)} "
         f"GB su {_gb(p.pool_gb)}, ne restano {_gb(p.liberi_gb)}", ""]
    for s in p.scelte:
        mem = f"{_gb(s.memoria_gb)} GB" if s.memoria_gb else ""
        riga = f"{_NOMI.get(s.ruolo, s.ruolo):13}{s.scelta:44} {s.dove:6} {mem:>9}  " \
               f"{_SEGNO.get(s.stato, '')}"
        if s.oggi:
            riga += f"  [{s.oggi}]"
        r.append(riga.rstrip())
        for pezzo in (s.stima, s.motivo):
            if pezzo:
                r.append(f"{'':13}{pezzo}")
    if p.ollama:
        o = p.ollama
        r += ["", f"Ollama: {o.get('max_loaded_models')} modelli residenti "
                  f"({', '.join(o.get('residenti') or [])}), {o.get('num_parallel')} posti"
              + (f"; letti dal servizio: " + ", ".join(f"{k}={v}" for k, v in
                                                       (o.get("letti") or {}).items())
                 if o.get("letti") else "")]
        for prop in o.get("proposte") or []:
            r.append(f"  proposta (comando da terminale, sudo): {prop}")
    if p.non_sostenibili:
        r += ["", "Non sostenibile qui: " + "; ".join(p.non_sostenibili) + "."]
    if p.candidati:
        r += ["", "Da provare col banco (mai scelti da soli):"]
        r += [f"  {c['modello']:22} {_gb(c['memoria_gb'])} GB, ~{c['token_s']} token/s "
              f"stimati — {c['nota']}" for c in p.candidati]
    if p.avvisi:
        r += ["", "Avvisi:"] + [f"  - {a}" for a in p.avvisi]
    if p.decisioni:
        r += ["", "Decisioni aperte (il piano non sceglie):"]
        for d in p.decisioni:
            r.append(f"  {d['numero']}. {d['titolo']}")
            r += [f"     - {o}" for o in d["opzioni"]]
    r += ["", "Il piano non applica niente: per cambiare, calliope.locale.yaml (o «calliope "
              "stato --installa» per i modelli del catalogo)."]
    return "\n".join(r)
