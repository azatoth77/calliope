"""Misure per l'arbitro della memoria (14/10/2026, passo 1: docs/ricerche/2026-10-14-arbitro-memoria.md).

Da lanciare **sulla DGX**, nella cartella dei dati, con l'interprete di Calliope, **con il servizio
acceso e Calliope inattiva** (nessun turno da 10 minuti, nessun lavoro dell'agente: lo controlla
da sé, come il deploy, e si ferma se arriva un turno a metà):

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
    $V/.venv/bin/python $V/prove/manuali/misura_memoria_dgx.py stato
    $V/.venv/bin/python $V/prove/manuali/misura_memoria_dgx.py ollama [--modelli M1,M2] [--giri 3]
                                                               [--anche-tempo-reale]
    $V/.venv/bin/python $V/prove/manuali/misura_memoria_dgx.py whisper [--modello FILE] [--giri 3]
    $V/.venv/bin/python $V/prove/manuali/misura_memoria_dgx.py voce [--durante embedding|whisper]
                                                               [--giri 8]
    $V/.venv/bin/python $V/prove/manuali/misura_memoria_dgx.py vllm-sonno --livello 1|2
                                                               --conferma calliope-vllm [--tieni 10]

Comandi:
- `stato`: la memoria adesso (MemAvailable, MemFree, cache dei file; /api/ps; vLLM; nvidia-smi
  per processo se il GB10 lo dà; RSS di Calliope e di whisper-server). Non tocca niente.
- `ollama`: per ogni modello scaricamento (`keep_alive: 0`), caricamento **a freddo** (cache dei
  file del modello svuotata con `posix_fadvise(DONTNEED)`, senza sudo, se i blob si leggono;
  altrimenti «tiepido») e **a caldo**, memoria prima e dopo (delta di MemAvailable: la memoria vera,
  contro quello che dice /api/ps). Di serie solo l'embedding (sfondo); i modelli del tempo reale
  (voce, guardiano, rilevatore) solo con `--anche-tempo-reale` e una conferma da tastiera. Alla fine
  ogni modello torna com'era, con **lo stesso `num_ctx`** letto da /api/ps (un num_ctx diverso farebbe
  ricaricare il modello al turno dopo) e lo stesso keep_alive, e lo si controlla.
- `whisper`: un whisper-server **suo** (porta 8091, mai il servizio `calliope-whisper`) con il modello
  scelto (di serie large-v3, il candidato della corsia lenta, se c'è; altrimenti il turbo): pronto
  a freddo e a caldo, prima trascrizione, memoria, chiusura e memoria restituita.
- `voce`: l'effetto di un caricamento in parallelo sulla voce: prima parola e prima frase del modello
  della voce (stesso num_ctx e keep_alive, prompt breve) e una trascrizione di whisper-server,
  `--giri` volte a macchina ferma e `--giri` volte con il caricamento che parte insieme
  (`embedding`: scaricato e ricaricato; `whisper`: il whisper-server suo che parte). Il prompt di
  prova occupa un posto di Ollama: il primo turno vero dopo può rileggere il prefisso una volta.
- `vllm-sonno`: **comando separato, tocca il container dell'agente** (`calliope-vllm`). Solo con
  `--conferma calliope-vllm` e un «sì» da tastiera. Condizioni: il server deve avere la modalità sonno
  (`--enable-sleep-mode` con `VLLM_SERVER_DEV_MODE=1`: oggi `vllm.sh` non la accende, passo 4 della
  ricerca), niente in pausa, nessuna richiesta in corso o in coda (/metrics), nessun lavoro
  dell'agente, Calliope inattiva, memoria libera sufficiente. Mette a dormire al livello scelto,
  tiene `--tieni` secondi, sveglia (livello 2: pesi, `reload_weights`, cache) e prova una richiesta
  breve. **Ripristino garantito**: la sveglia parte anche su errore, Ctrl+C, SIGTERM e all'uscita;
  se non riesce stampa i comandi a mano (in fondo a questo testo).

Stampa **solo numeri** (secondi, GB, conteggi) e i nomi dei modelli: mai testi, parole del journal o
percorsi. Non scrive nella configurazione; `--json FILE` salva i numeri dove si dice.

Ripristino a mano di vLLM (se la sveglia non va a buon fine):
    curl -X POST 'http://127.0.0.1:8000/wake_up?tags=weights'
    curl -X POST http://127.0.0.1:8000/collective_rpc -H 'Content-Type: application/json' \\
         -d '{"method": "reload_weights"}'                       # solo dopo il livello 2
    curl -X POST 'http://127.0.0.1:8000/wake_up?tags=kv_cache'
    curl -s http://127.0.0.1:8000/is_sleeping                     # {"is_sleeping": false}
e come ultima risorsa il container rifatto: `$V/setup/linux/motore/vllm.sh agente rifai` (~1 minuto
con la cache di compilazione).
"""

import argparse
import atexit
import io
import json
import os
import re
import signal
import statistics
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

OLLAMA = "http://127.0.0.1:11434"
VLLM = "http://127.0.0.1:8000"
PORTA_WHISPER = 8091
GB = 1e9
# Le righe del journal che dicono «un turno» (ciclo.py): si contano, non si stampano
TURNO = re.compile(r"\[STT \d|\[STT e (risposta|mossa)|\[prima frase")
INATTIVA_MIN = 10


class Interrotta(Exception):
    """Un turno vero è arrivato a metà misura: si ripristina e ci si ferma."""


# ─────────────────────────── letture ───────────────────────────
def meminfo() -> dict:
    out = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for riga in fh:
                k, _, v = riga.partition(":")
                if k in ("MemTotal", "MemAvailable", "MemFree", "Cached", "Shmem", "Buffers"):
                    out[k] = round(int(v.split()[0]) * 1024 / GB, 2)
    except OSError:
        pass
    return out


def disponibile(attesa_s: float = 0.0) -> float | None:
    """MemAvailable in GB, dopo `attesa_s` per lasciare assestare la memoria."""
    if attesa_s:
        time.sleep(attesa_s)
    return meminfo().get("MemAvailable")


def smi_processi() -> float | None:
    """La memoria per processo di nvidia-smi (GB), se il GB10 la dà; None altrimenti."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    vals = []
    for riga in out.splitlines():
        p = [x.strip() for x in riga.split(",")]
        if len(p) == 2 and p[1].replace(".", "").isdigit():
            vals.append(float(p[1]) * 1048576 / GB)
    return round(sum(vals), 2) if vals else None


def rss_unita(unita: str) -> float | None:
    try:
        out = subprocess.run(["systemctl", "--user", "show", unita, "--property=MainPID"],
                             capture_output=True, text=True, timeout=3).stdout
        pid = int(re.search(r"MainPID=(\d+)", out).group(1))
        if pid <= 0:
            return None
        return rss_pid(pid)
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return None


def rss_pid(pid: int) -> float | None:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as fh:
            m = re.search(r"^VmRSS:\s*(\d+)", fh.read(), re.M)
        return round(int(m.group(1)) * 1024 / GB, 2) if m else None
    except (OSError, AttributeError):
        return None


def http(metodo: str, url: str, corpo=None, timeout: float = 30.0):
    """(codice, json o testo). Codice 0 se non risponde."""
    dati = None if corpo is None else json.dumps(corpo).encode()
    intestazioni = {"Content-Type": "application/json"}
    if url.startswith(VLLM) and os.environ.get("VLLM_API_KEY"):
        intestazioni["Authorization"] = "Bearer " + os.environ["VLLM_API_KEY"]
    req = urllib.request.Request(url, data=dati, method=metodo, headers=intestazioni)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — 127.0.0.1
            testo = r.read().decode("utf-8", "replace")
            codice = r.status
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, ""
    try:
        return codice, json.loads(testo)
    except ValueError:
        return codice, testo


def ollama_ps() -> dict:
    c, d = http("GET", OLLAMA + "/api/ps", timeout=5)
    if c != 200 or not isinstance(d, dict):
        return {}
    return {m.get("name") or m.get("model"): m for m in d.get("models") or []}


def _nome(m: str) -> str:
    return m if ":" in m else m + ":latest"


# ─────────────────────────── Calliope inattiva ───────────────────────────
def turni_dal(da: str) -> int | None:
    """Righe di turno nel journal di calliope da `da` (formato di journalctl --since)."""
    try:
        out = subprocess.run(["journalctl", "--user", "-u", "calliope", "--since", da, "-o", "cat",
                              "--no-pager"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return sum(1 for r in out.splitlines() if TURNO.search(r))


def lavori_vivi() -> int:
    """I lavori dell'agente in coda o in corso (lavori/in_corso.json, come il deploy)."""
    dati_dir = Path(os.environ.get("CALLIOPE_DATI") or Path.home() / "calliope")
    for p in (dati_dir / "lavori" / "in_corso.json", dati_dir / "lavori" / "in_corso.json.bak"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            continue
    else:
        return 0
    pid = d.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return 0
        except PermissionError:
            pass
    return sum(1 for r in d.get("lavori") or [] if isinstance(r, dict)
               and r.get("stato") in ("in_coda", "in_corso"))


def servizio_attivo() -> bool:
    try:
        return subprocess.run(["systemctl", "--user", "is-active", "calliope"],
                              capture_output=True, text=True, timeout=5).stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


class Guardia:
    """Controlla prima e durante: nessun turno vero, nessun lavoro dell'agente."""

    def __init__(self, minuti: int = INATTIVA_MIN, forza: bool = False):
        self.inizio = time.strftime("%Y-%m-%d %H:%M:%S")
        self.forza = forza
        n = turni_dal(f"-{minuti}min")
        self.prima = {"servizio_attivo": servizio_attivo(), "turni_ultimi_min": n,
                      "minuti": minuti, "lavori_agente": lavori_vivi()}

    def pronta(self) -> bool:
        p = self.prima
        print(f"servizio_attivo: {int(p['servizio_attivo'])}")
        print(f"turni_ultimi_{p['minuti']}_min: {p['turni_ultimi_min']}")
        print(f"lavori_agente: {p['lavori_agente']}")
        if p["turni_ultimi_min"] is None:
            print("esito: journal non leggibile, non misuro")
            return False
        if (p["turni_ultimi_min"] or p["lavori_agente"]) and not self.forza:
            print("esito: Calliope non è inattiva, non misuro (riprova più tardi)")
            return False
        return True

    def controlla(self):
        if self.forza:
            return
        n = turni_dal(self.inizio)
        if n:
            raise Interrotta(f"{n} turni durante la misura")
        if lavori_vivi():
            raise Interrotta("un lavoro dell'agente è partito")


# ─────────────────────────── statistiche ───────────────────────────
def riassunto(xs: list) -> dict:
    xs = [x for x in xs if isinstance(x, (int, float))]
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    return {"n": len(s), "mediana": round(statistics.median(s), 3),
            "p90": round(s[min(len(s) - 1, int(0.9 * len(s)))], 3),
            "min": round(s[0], 3), "max": round(s[-1], 3)}


def stampa(prefisso: str, d):
    if isinstance(d, dict):
        for k, v in d.items():
            stampa(f"{prefisso}.{k}" if prefisso else k, v)
    else:
        print(f"{prefisso}: {d}")


# ─────────────────────────── stato ───────────────────────────
def cmd_stato(_a) -> dict:
    m = meminfo()
    ps = ollama_ps()
    out = {"meminfo_gb": m,
           "ollama_ps_gb": {k: round((v.get("size") or 0) / GB, 2) for k, v in ps.items()},
           "ollama_ps_contesto": {k: v.get("context_length") for k, v in ps.items()},
           "nvidia_smi_processi_gb": smi_processi(),
           "rss_calliope_gb": rss_unita("calliope"),
           "rss_whisper_gb": rss_unita("calliope-whisper")}
    c, metr = http("GET", VLLM + "/metrics", timeout=5)
    if c == 200 and isinstance(metr, str):
        mm = re.search(r'gpu_memory_utilization="([\d.]+)"', metr)
        out["vllm_gpu_memory_utilization"] = float(mm.group(1)) if mm else None
        out["vllm_prenotata_gb"] = round(float(mm.group(1)) * m.get("MemTotal", 0), 2) \
            if mm else None
        out["vllm_richieste_in_corso"] = _metrica(metr, "vllm:num_requests_running")
    c, sl = http("GET", VLLM + "/is_sleeping", timeout=3)
    out["vllm_sonno_disponibile"] = int(c == 200)
    return out


def _metrica(testo: str, nome: str) -> float | None:
    tot, trovata = 0.0, False
    for riga in testo.splitlines():
        if riga.startswith(nome) and not riga.startswith("#"):
            try:
                tot += float(riga.rsplit(" ", 1)[1])
                trovata = True
            except (ValueError, IndexError):
                pass
    return tot if trovata else None


# ─────────────────────────── Ollama ───────────────────────────
def _blob(modello: str) -> list[str]:
    c, d = http("POST", OLLAMA + "/api/show", {"model": modello}, timeout=10)
    if c != 200 or not isinstance(d, dict):
        return []
    return re.findall(r"^FROM (/\S+)", d.get("modelfile") or "", re.M)


def fredda(percorsi: list[str]) -> int:
    """Toglie dalla cache dei file del kernel le pagine non in uso di questi file (senza sudo).
    Restituisce quanti file ci è riuscita a toccare."""
    n = 0
    for p in percorsi:
        try:
            fd = os.open(p, os.O_RDONLY)
        except OSError:
            continue
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            n += 1
        except (OSError, AttributeError):
            pass
        finally:
            os.close(fd)
    return n


def _embedding(modello: str) -> bool:
    c, d = http("POST", OLLAMA + "/api/show", {"model": modello}, timeout=10)
    return isinstance(d, dict) and "embedding" in (d.get("capabilities") or [])


def ollama_carica(modello: str, num_ctx: int | None, keep_alive) -> tuple[float, float | None]:
    """(secondi fino a /api/ps, load_duration di Ollama in s)."""
    t = time.perf_counter()
    opts = {"num_ctx": int(num_ctx)} if num_ctx else {}
    if _embedding(modello):
        c, d = http("POST", OLLAMA + "/api/embed", {"model": modello, "input": "prova",
                                                    "keep_alive": keep_alive, "options": opts},
                    timeout=600)
    else:
        c, d = http("POST", OLLAMA + "/api/generate", {"model": modello, "keep_alive": keep_alive,
                                                       "options": opts, "stream": False},
                    timeout=600)
    if c != 200:
        raise RuntimeError(f"caricamento di {modello}: HTTP {c}")
    while _nome(modello) not in ollama_ps() and time.perf_counter() - t < 600:
        time.sleep(0.1)
    ld = d.get("load_duration") if isinstance(d, dict) else None
    return time.perf_counter() - t, (ld / 1e9 if isinstance(ld, (int, float)) else None)


def ollama_scarica(modello: str) -> float:
    t = time.perf_counter()
    corpo = {"model": modello, "keep_alive": 0}
    if _embedding(modello):
        http("POST", OLLAMA + "/api/embed", {**corpo, "input": "x"}, timeout=120)
    else:
        http("POST", OLLAMA + "/api/generate", corpo, timeout=120)
    while _nome(modello) in ollama_ps() and time.perf_counter() - t < 120:
        time.sleep(0.1)
    return time.perf_counter() - t


def _keep_alive_di(voce: dict | None, predefinito):
    """Il keep_alive di adesso: «per sempre» se scade tra più di un anno."""
    if not voce:
        return predefinito
    scade = str(voce.get("expires_at") or "")
    m = re.match(r"(\d{4})-", scade)
    if m and int(m.group(1)) > time.gmtime().tm_year + 1:
        return -1
    return predefinito


def cmd_ollama(a, cfg, guardia: Guardia) -> dict:
    # keep_alive di Calliope per ogni modello del tempo reale (lo stesso o Ollama lo ricarica)
    ka_cfg = {}
    for x, ka_ in ((getattr(cfg, "guardiano_modello", ""), getattr(cfg, "guardiano_keep_alive",
                                                                   "-1m")),
                   (getattr(cfg, "guardiano_pericolo_modello", ""),
                    getattr(cfg, "guardiano_keep_alive", "-1m")),
                   (getattr(cfg, "llm_model", ""), getattr(cfg, "llm_keep_alive", "30m"))):
        if x:
            ka_cfg[_nome(x)] = ka_
    tempo_reale = set(ka_cfg)
    modelli = [m.strip() for m in (a.modelli or getattr(cfg, "conversazioni_embedding", "")
                                   or "").split(",") if m.strip()]
    rt = [m for m in modelli if _nome(m) in tempo_reale]
    if rt and not a.anche_tempo_reale:
        print(f"saltati_tempo_reale: {len(rt)} (servono --anche-tempo-reale e una conferma)")
        modelli = [m for m in modelli if m not in rt]
    if rt and a.anche_tempo_reale:
        if not sys.stdin.isatty() or input(
                f"Scarico e ricarico {len(rt)} modelli del tempo reale ({', '.join(rt)}): la voce "
                "è ferma? Scrivi «sì» per continuare: ").strip().lower() not in ("sì", "si"):
            print("esito: annullato")
            return {}
    out = {}
    for modello in modelli:
        prima = ollama_ps().get(_nome(modello))
        ctx = (prima or {}).get("context_length") or None
        ka = _keep_alive_di(prima, ka_cfg.get(_nome(modello), 0))
        # Con keep_alive 0 (l'embedding, come lo usa Calliope) Ollama lo scaricherebbe subito:
        # durante la misura resta 5 minuti, alla fine si rimette com'era
        ka_misura = "5m" if ka in (0, "0", "0s", "0m") else ka
        blob = _blob(modello)
        r = {"caricato_prima": int(prima is not None), "contesto": ctx,
             "ps_gb": round(((prima or {}).get("size") or 0) / GB, 2) or None,
             "scarica_s": [], "freddo_s": [], "freddo_load_s": [], "caldo_s": [],
             "liberati_gb": [], "occupati_gb": [], "file_freddati": 0}
        try:
            for _ in range(a.giri):
                guardia.controlla()
                if _nome(modello) not in ollama_ps():
                    ollama_carica(modello, ctx, ka_misura)
                m0 = disponibile(2)
                r["scarica_s"].append(round(ollama_scarica(modello), 3))
                m1 = disponibile(3)
                r["liberati_gb"].append(round(m1 - m0, 2))
                r["file_freddati"] = fredda(blob)
                guardia.controlla()
                s, ld = ollama_carica(modello, ctx, ka_misura)
                r["freddo_s"].append(round(s, 3))
                r["freddo_load_s"].append(round(ld, 3) if ld else None)
                m2 = disponibile(3)
                r["occupati_gb"].append(round(m1 - m2, 2))
                if r["ps_gb"] is None:
                    r["ps_gb"] = round((ollama_ps().get(_nome(modello)) or {}).get("size", 0)
                                       / GB, 2)
                ollama_scarica(modello)
                disponibile(2)
                guardia.controlla()
                s, _ = ollama_carica(modello, ctx, ka_misura)
                r["caldo_s"].append(round(s, 3))
        finally:
            # Com'era: stesso num_ctx e keep_alive, o scaricato se non c'era
            if prima is not None:
                # Con keep_alive 0 Calliope l'avrebbe già scaricato: non lo si ricarica
                if _nome(modello) not in ollama_ps() and ka_misura == ka:
                    ollama_carica(modello, ctx, ka)
                dopo = ollama_ps().get(_nome(modello)) or {}
                r["ripristinato"] = int(dopo.get("context_length") == ctx)
            else:
                ollama_scarica(modello)
                r["ripristinato"] = int(_nome(modello) not in ollama_ps())
        for k in ("scarica_s", "freddo_s", "caldo_s", "liberati_gb", "occupati_gb"):
            r[k] = riassunto(r[k])
        r["freddo_load_s"] = riassunto(r["freddo_load_s"])
        if r["ps_gb"] and r["occupati_gb"].get("mediana"):
            r["vero_su_ps"] = round(r["occupati_gb"]["mediana"] / r["ps_gb"], 3)
        out[modello] = r
    return out


# ─────────────────────────── whisper-server ───────────────────────────
def _wav(secondi: float = 2.0, sr: int = 16000) -> bytes:
    """Silenzio con un filo di rumore: basta a far lavorare l'encoder."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", (i * 7919) % 64 - 32)
                               for i in range(int(secondi * sr))))
    return buf.getvalue()


def trascrivi(url: str, wav: bytes, timeout: float = 60) -> float | None:
    """Secondi per una trascrizione (multipart verso /v1/audio/transcriptions)."""
    confine = "calliopemisura"
    corpo = (f"--{confine}\r\nContent-Disposition: form-data; name=\"file\"; "
             f"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode() + wav + \
        (f"\r\n--{confine}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\n"
         f"json\r\n--{confine}--\r\n").encode()
    req = urllib.request.Request(url.rstrip("/") + "/audio/transcriptions", data=corpo,
                                 method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={confine}"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — 127.0.0.1
            r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    return time.perf_counter() - t


def _whisper_dir() -> Path:
    return Path(os.environ.get("WHISPER_DIR") or Path.home() / "calliope-motore" / "whispercpp")


def _modello_whisper(scelto: str | None) -> Path | None:
    d = _whisper_dir() / "modelli"
    for nome in ([scelto] if scelto else ["ggml-large-v3.bin", "ggml-large-v3-turbo.bin"]):
        if nome and (d / nome).is_file():
            return d / nome
    return None


class WhisperSuo:
    """Un whisper-server avviato da qui (mai il servizio calliope-whisper), chiuso per PID."""

    def __init__(self, modello: Path, porta: int = PORTA_WHISPER):
        self.modello, self.porta = modello, porta
        self.url = f"http://127.0.0.1:{porta}"
        self.proc = None

    def avvia(self, attesa_s: float = 300) -> float | None:
        binario = _whisper_dir() / "src" / "build" / "bin" / "whisper-server"
        t = time.perf_counter()
        self.proc = subprocess.Popen(
            [str(binario), "-m", str(self.modello), "--host", "127.0.0.1", "--port",
             str(self.porta), "-l", "it", "-bs", "5", "-t", "4",
             "--inference-path", "/v1/audio/transcriptions"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        while time.perf_counter() - t < attesa_s:
            if self.proc.poll() is not None:
                return None
            if http("GET", self.url + "/", timeout=1)[0] == 200:
                return time.perf_counter() - t
            time.sleep(0.05)
        return None

    def chiudi(self) -> float:
        t = time.perf_counter()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.proc = None
        return time.perf_counter() - t


def cmd_whisper(a, guardia: Guardia) -> dict:
    mod = _modello_whisper(a.modello)
    if mod is None:
        print("esito: modello di whisper.cpp non trovato (WHISPER_DIR/modelli)")
        return {}
    if http("GET", f"http://127.0.0.1:{PORTA_WHISPER}/", timeout=1)[0]:
        print(f"esito: la porta {PORTA_WHISPER} è occupata, non misuro")
        return {}
    w = WhisperSuo(mod)
    wav = _wav()
    r = {"modello_gb": round(mod.stat().st_size / GB, 2), "pronto_freddo_s": [],
         "pronto_caldo_s": [], "prima_trascrizione_s": [], "seconda_trascrizione_s": [],
         "occupati_gb": [], "rss_gb": [], "chiusura_s": [], "restituiti_gb": []}
    try:
        for giro in range(a.giri):
            for modo in ("freddo", "caldo"):
                guardia.controlla()
                if modo == "freddo":
                    fredda([str(mod)])
                m0 = disponibile(2)
                s = w.avvia()
                if s is None:
                    print("esito: whisper-server non è partito")
                    return r
                r[f"pronto_{modo}_s"].append(round(s, 3))
                r["prima_trascrizione_s"].append(round(trascrivi(w.url + "/v1", wav) or -1, 3))
                r["seconda_trascrizione_s"].append(round(trascrivi(w.url + "/v1", wav) or -1, 3))
                m1 = disponibile(2)
                r["occupati_gb"].append(round(m0 - m1, 2))
                r["rss_gb"].append(rss_pid(w.proc.pid))
                r["chiusura_s"].append(round(w.chiudi(), 3))
                m2 = disponibile(3)
                r["restituiti_gb"].append(round(m2 - m1, 2))
    finally:
        w.chiudi()
    return {mod.name: {k: (riassunto(v) if isinstance(v, list) else v) for k, v in r.items()}}


# ─────────────────────────── effetto sulla voce ───────────────────────────
def sonda_voce(modello: str, ctx: int, ka) -> tuple[float | None, float | None]:
    """(prima parola, prima frase) del modello della voce in streaming, in secondi."""
    corpo = {"model": modello, "stream": True, "think": False, "keep_alive": ka,
             "messages": [{"role": "user", "content": "Dimmi una frase breve sul mare."}],
             "options": {"num_ctx": int(ctx), "num_predict": 40, "temperature": 0}}
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(corpo).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    primo = frase = None
    testo = ""
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — 127.0.0.1
            for riga in r:
                try:
                    pezzo = (json.loads(riga).get("message") or {}).get("content") or ""
                except ValueError:
                    continue
                if pezzo and primo is None:
                    primo = time.perf_counter() - t
                testo += pezzo
                if frase is None and re.search(r"\w.*[.!?]", testo):
                    frase = time.perf_counter() - t
    except (urllib.error.URLError, OSError, TimeoutError):
        return None, None
    return primo, frase or (time.perf_counter() - t)


def cmd_voce(a, cfg, guardia: Guardia) -> dict:
    voce = getattr(cfg, "llm_model", "")
    ps = ollama_ps()
    v = ps.get(_nome(voce))
    if v is None:
        print("esito: il modello della voce non è caricato in Ollama, non misuro")
        return {}
    ctx = v.get("context_length")
    ka = _keep_alive_di(v, getattr(cfg, "llm_keep_alive", "30m"))
    stt = (getattr(cfg, "stt_url", "") or "").replace("localhost", "127.0.0.1")
    wav = _wav(3.0)
    emb = getattr(cfg, "conversazioni_embedding", "") or ""
    mod_w = _modello_whisper(None)
    r = {"base": {"prima_parola_s": [], "prima_frase_s": [], "stt_s": []},
         "durante": {"prima_parola_s": [], "prima_frase_s": [], "stt_s": []},
         "carico_s": []}

    def misura(dove):
        guardia.controlla()
        p, f = sonda_voce(voce, ctx, ka)
        r[dove]["prima_parola_s"].append(p)
        r[dove]["prima_frase_s"].append(f)
        if stt:
            r[dove]["stt_s"].append(trascrivi(stt, wav))

    sonda_voce(voce, ctx, ka)            # il prompt di prova in cache: tutte le sonde uguali
    for _ in range(a.giri):
        misura("base")
        time.sleep(2)
    w = WhisperSuo(mod_w) if a.durante == "whisper" and mod_w else None
    try:
        for _ in range(a.giri):
            guardia.controlla()
            if a.durante == "embedding" and emb:
                ollama_scarica(emb)
                fredda(_blob(emb))
                th = threading.Thread(target=lambda: r["carico_s"].append(
                    round(ollama_carica(emb, None, "2m")[0], 3)))
            elif w is not None:
                fredda([str(mod_w)])
                th = threading.Thread(target=lambda: r["carico_s"].append(
                    round(w.avvia() or -1, 3)))
            else:
                print("esito: niente da caricare in parallelo (--durante embedding|whisper)")
                return r
            th.start()
            time.sleep(0.05)
            misura("durante")
            th.join(timeout=600)
            if w is not None:
                w.chiudi()
            time.sleep(3)
    finally:
        if w is not None:
            w.chiudi()
        if a.durante == "embedding" and emb:
            ollama_scarica(emb)              # come lo lascia Calliope: keep_alive 0
    out = {"durante": a.durante, "contesto": ctx, "carico_s": riassunto(r["carico_s"])}
    for fase in ("base", "durante"):
        out[fase] = {k: riassunto(v) for k, v in r[fase].items()}
    print("nota: il primo turno vero dopo la misura può rileggere il prefisso una volta")
    return out


# ─────────────────────────── vLLM: sonno e sveglia ───────────────────────────
class Sveglia:
    """La sveglia di vLLM garantita: su errore, Ctrl+C, SIGTERM, SIGHUP e all'uscita."""

    def __init__(self, livello: int):
        self.livello = livello
        self.dorme = False
        self.tempi: dict = {}
        self._lock = threading.Lock()
        atexit.register(self.sveglia)
        for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(s, self._segnale)

    def _segnale(self, signum, _frame):
        self.sveglia()
        print(f"esito: interrotta dal segnale {signum}, vLLM svegliato: "
              f"{int(not self.dorme)}")
        os._exit(1)

    def sveglia(self) -> bool:
        with self._lock:
            if not self.dorme:
                return True
            t = time.perf_counter()
            passi = ([("wake_up", "POST", "/wake_up", None)] if self.livello == 1 else
                     [("pesi", "POST", "/wake_up?tags=weights", None),
                      ("reload_weights", "POST", "/collective_rpc", {"method": "reload_weights"}),
                      ("cache", "POST", "/wake_up?tags=kv_cache", None)])
            for nome, metodo, via, corpo in passi:
                t1 = time.perf_counter()
                c, _ = http(metodo, VLLM + via, corpo, timeout=900)
                self.tempi[f"sveglia_{nome}_s"] = round(time.perf_counter() - t1, 3)
                self.tempi[f"sveglia_{nome}_http"] = c
            while time.perf_counter() - t < 900:
                c, d = http("GET", VLLM + "/is_sleeping", timeout=5)
                if c == 200 and isinstance(d, dict) and not d.get("is_sleeping"):
                    self.dorme = False
                    break
                time.sleep(0.2)
            self.tempi["sveglia_totale_s"] = round(time.perf_counter() - t, 3)
            if self.dorme:
                print("esito: vLLM NON si è svegliato: comandi a mano in testa a questo file "
                      "(wake_up, reload_weights, vllm.sh agente rifai)")
            return not self.dorme


def _prova_vllm() -> float | None:
    """Secondi di una richiesta breve all'agente (None se non risponde bene)."""
    c, d = http("GET", VLLM + "/v1/models", timeout=10)
    if c != 200 or not isinstance(d, dict) or not d.get("data"):
        return None
    t = time.perf_counter()
    c, _ = http("POST", VLLM + "/v1/chat/completions",
                {"model": d["data"][0]["id"], "max_tokens": 8, "temperature": 0,
                 "messages": [{"role": "user", "content": "Rispondi solo: ok"}]}, timeout=300)
    return time.perf_counter() - t if c == 200 else None


def cmd_vllm(a, guardia: Guardia) -> dict:
    if a.conferma != "calliope-vllm":
        print("esito: serve --conferma calliope-vllm (tocca il container dell'agente)")
        return {}
    c, d = http("GET", VLLM + "/is_sleeping", timeout=5)
    if c != 200:
        print("esito: modalità sonno assente (serve --enable-sleep-mode con "
              "VLLM_SERVER_DEV_MODE=1: passo 4 della ricerca), non misuro")
        sys.exit(77)
    if isinstance(d, dict) and d.get("is_sleeping"):
        print("esito: vLLM dorme già: prima lo si sveglia a mano (comandi in testa al file)")
        return {}
    c, d = http("GET", VLLM + "/is_paused", timeout=5)
    if c == 200 and isinstance(d, dict) and d.get("is_paused"):
        print("esito: vLLM è in pausa (arbitro della voce): non misuro")
        return {}
    c, metr = http("GET", VLLM + "/metrics", timeout=5)
    corso = _metrica(metr, "vllm:num_requests_running") if c == 200 else None
    coda = _metrica(metr, "vllm:num_requests_waiting") if c == 200 else None
    print(f"richieste_in_corso: {corso}")
    print(f"richieste_in_coda: {coda}")
    if corso is None or corso or coda:
        print("esito: vLLM sta lavorando (o /metrics non risponde): non misuro")
        return {}
    libera = disponibile()
    if a.livello == 1 and (libera or 0) < 10:
        print(f"esito: livello 1 con {libera} GB liberi: ne servono almeno 10 per spostare i "
              "pesi, non misuro")
        return {}
    a.tieni = max(1, min(120, a.tieni))
    if not sys.stdin.isatty() or input(
            f"Metto a dormire vLLM dell'agente (livello {a.livello}) per {a.tieni} s e lo sveglio. "
            "Scrivi «sì» per continuare: ").strip().lower() not in ("sì", "si"):
        print("esito: annullato")
        return {}
    r = {"livello": a.livello, "prova_prima_s": _prova_vllm(), "prova_prima2_s": _prova_vllm()}
    sv = Sveglia(a.livello)
    try:
        guardia.controlla()
        m0 = disponibile(2)
        t = time.perf_counter()
        sv.dorme = True                     # da qui la sveglia è dovuta, anche se il POST fallisce
        c, _ = http("POST", VLLM + f"/sleep?level={a.livello}", timeout=600)
        r["sonno_http"] = c
        while time.perf_counter() - t < 600:
            c2, d2 = http("GET", VLLM + "/is_sleeping", timeout=5)
            if c2 == 200 and isinstance(d2, dict) and d2.get("is_sleeping"):
                break
            time.sleep(0.2)
        r["sonno_s"] = round(time.perf_counter() - t, 3)
        m1 = disponibile(3)
        r["liberati_gb"] = round(m1 - m0, 2)
        fine = time.monotonic() + a.tieni
        while time.monotonic() < fine:
            guardia.controlla()             # un turno a metà: si sveglia subito
            time.sleep(1)
    except Interrotta as e:
        r["interrotta"] = str(e)
    finally:
        sv.sveglia()
    r.update(sv.tempi)
    r["ripresi_gb"] = round(m1 - disponibile(3), 2) if "liberati_gb" in r else None
    r["prova_dopo_s"] = _prova_vllm()
    r["prova_dopo2_s"] = _prova_vllm()
    r["sveglio"] = int(not sv.dorme)
    return r


# ─────────────────────────── principale ───────────────────────────
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Misure per l'arbitro della memoria (DGX).")
    ap.add_argument("comando", choices=("stato", "ollama", "whisper", "voce", "vllm-sonno"))
    ap.add_argument("--modelli", default="")
    ap.add_argument("--modello", default="")
    ap.add_argument("--giri", type=int, default=3)
    ap.add_argument("--anche-tempo-reale", action="store_true")
    ap.add_argument("--durante", default="embedding", choices=("embedding", "whisper"))
    ap.add_argument("--livello", type=int, choices=(1, 2), default=1)
    ap.add_argument("--conferma", default="")
    ap.add_argument("--tieni", type=int, default=10)
    ap.add_argument("--forza", action="store_true",
                    help="misura anche con turni o lavori recenti (solo prove a vuoto)")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    if not sys.platform.startswith("linux"):
        print("esito: va lanciato sulla DGX (Linux)")
        return 77
    if a.comando == "stato":
        out = cmd_stato(a)
    else:
        import contextlib
        from calliope.config import load_config
        with contextlib.redirect_stdout(io.StringIO()):   # niente percorsi a schermo
            cfg = load_config()
        guardia = Guardia(forza=a.forza)
        if not guardia.pronta():
            return 1
        try:
            if a.comando == "ollama":
                out = cmd_ollama(a, cfg, guardia)
            elif a.comando == "whisper":
                out = cmd_whisper(a, guardia)
            elif a.comando == "voce":
                out = cmd_voce(a, cfg, guardia)
            else:
                out = cmd_vllm(a, guardia)
        except Interrotta as e:
            print(f"esito: interrotta ({e}); i modelli sono stati rimessi com'erano")
            return 1
    stampa("", out)
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
