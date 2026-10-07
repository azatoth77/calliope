"""Quanto costa la voce su questa macchina (07/10): sintesi per carattere e velocità di parlato.

Il taglio della prima frase (tts.primo_pezzo) ha bisogno di due numeri: quanti caratteri al
secondo dice la voce in uso e quanti secondi costa a Piper sintetizzarne uno. Dipendono dalla
voce (serena-high è 5 volte più lenta di una medium) e dalla macchina (DGX con 8 thread 3,5 ms a
carattere, portatile carico ~8 ms): non si tarano a mano, perché altri installeranno Calliope su
hardware che nessuno ha provato. Tre fonti, dalla più debole alla più forte:

1. **predefiniti prudenti** (PREDEFINITI): una macchina lenta, il primo pezzo esce più lungo;
2. **taratura all'avvio** (`Taratura.tara`, in un thread dopo il caricamento della voce, quando
   la voce è libera): una frase fissa sintetizzata tre volte (vale la più veloce); con `tts_thread: auto` e nessuna
   scelta salvata prova anche pochi numeri di thread (2, 4, 8, i core fisici) e tiene il più
   veloce;
3. **l'uso** (`Taratura.osserva`, ogni sintesi vera di almeno MIN_CARATTERI): la mediana delle
   ultime FINESTRA, scartati i valori anomali (oltre ANOMALO volte la mediana: la CPU presa da
   altro, un'altra corsia che sintetizza insieme). Vale da MIN_USO sintesi in su.

Tutto per voce e per numero di thread (cambiare i thread cambia il costo), salvato in
`voce_taratura.json` accanto a calliope.yaml (scrittura atomica, `persistenza.scrivi_json`),
così sopravvive ai riavvii. Senza `config_dir` (le prove, `Config()` nudo) resta in memoria.

**CPU o GPU** (07/10, `tts_dispositivo`): con onnxruntime-gpu e CUDA Piper può sintetizzare
sulla GPU (DGX: serena-high 0,08 s invece di 0,47 per 138 caratteri). Con «auto» la taratura
all'avvio decide secondo la macchina, e la scelta e il motivo restano nel file (`dispositivo`):
GPU solo se c'è posto dopo i modelli di Calliope (la voce e Whisper vengono prima: ricerca
docs/ricerche/2026-10-07-taratura-macchina.md, §4.1) e se è davvero più veloce, con margine
per la contesa (GPU_VANTAGGIO). Una GPU dedicata piccola (il portatile da 8 GB) non si prova
nemmeno. Le misure sulla GPU hanno la chiave «voce@cuda»."""
from __future__ import annotations

import copy
import os
import statistics
import threading
import time
from pathlib import Path

FILE = "voce_taratura.json"
PREDEFINITI = {"parlato_car_s": 15.0, "sintesi_s_car": 0.010}
MIN_USO = 30                # sintesi vere prima di fidarsi dell'uso
FINESTRA = 200              # ultime sintesi tenute per voce
MIN_CARATTERI = 20          # sotto, il costo fisso di Piper pesa troppo sul costo a carattere
ANOMALO = 4.0               # un valore oltre 4 volte (o sotto un quarto) la mediana si scarta
SALVA_OGNI_S = 30.0         # l'uso si salva al più ogni 30 s (e alla taratura)
FRASE = "Buongiorno, oggi il cielo è sereno e fuori c'è un bel sole."


def chiave(voce: str, thread) -> str:
    return f"{Path(str(voce or '?')).stem}@{thread or 'predefiniti'}"


def thread_di(voice) -> int | str | None:
    """I thread con cui la voce è stata aperta (tts.carica_voce li scrive sull'oggetto), o
    «cuda» se sintetizza sulla GPU (la chiave delle misure)."""
    if getattr(voice, "calliope_dispositivo", None) == "cuda":
        return "cuda"
    n = getattr(voice, "calliope_thread", None)
    return n if isinstance(n, int) and n > 0 else None


def core_fisici() -> int:
    try:
        import psutil
        n = psutil.cpu_count(logical=False)
        if n:
            return int(n)
    except Exception:  # noqa: BLE001 — psutil c'è solo su Windows
        pass
    return max(1, os.cpu_count() or 1)


def candidati_thread() -> list[int]:
    logici = max(1, os.cpu_count() or 1)
    return sorted({n for n in (2, 4, 8, core_fisici()) if 1 <= n <= logici}) or [1]


class Taratura:
    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._salvata = 0.0
        self.dati: dict = {"voci": {}, "thread": {}, "dispositivo": {}}
        if path is not None:
            try:
                from .persistenza import leggi_json
                d, _ = leggi_json(path)
                if isinstance(d, dict):
                    self.dati["voci"] = d.get("voci") if isinstance(d.get("voci"), dict) else {}
                    self.dati["thread"] = (d.get("thread") if isinstance(d.get("thread"), dict)
                                           else {})
                    self.dati["dispositivo"] = (d.get("dispositivo")
                                                if isinstance(d.get("dispositivo"), dict) else {})
            except Exception as e:  # noqa: BLE001 — un file rovinato: si riparte da capo
                print(f"   [TTS] Taratura della voce non letta ({e}): riparto dai predefiniti",
                      flush=True)

    # ── lettura ──
    def _voce(self, k: str) -> dict:
        v = self.dati["voci"].setdefault(k, {})
        v.setdefault("uso", {"sintesi": [], "parlato": []})
        return v

    def stima(self, voce: str, thread=None) -> dict:
        """{"parlato_car_s", "sintesi_s_car", "fonte" ("uso"/"avvio"/"predefiniti"), "n"}."""
        with self._lock:
            v = self.dati["voci"].get(chiave(voce, thread)) or {}
            uso = v.get("uso") or {}
            s, p = uso.get("sintesi") or [], uso.get("parlato") or []
            if len(s) >= MIN_USO and len(p) >= MIN_USO:
                return {"parlato_car_s": statistics.median(p),
                        "sintesi_s_car": statistics.median(s), "fonte": "uso", "n": len(s)}
            a = v.get("avvio")
            if isinstance(a, dict) and a.get("sintesi_s_car") and a.get("parlato_car_s"):
                return {"parlato_car_s": float(a["parlato_car_s"]),
                        "sintesi_s_car": float(a["sintesi_s_car"]), "fonte": "avvio",
                        "n": len(s)}
            return {**PREDEFINITI, "fonte": "predefiniti", "n": len(s)}

    def thread_scelto(self, voce: str) -> int | None:
        """Il numero di thread scelto dalla taratura per questa voce (o per un'altra: la
        macchina è la stessa)."""
        t = self.dati.get("thread") or {}
        n = t.get(Path(str(voce or "?")).stem)
        if not isinstance(n, int):
            n = next((x for x in t.values() if isinstance(x, int)), None)
        return n if isinstance(n, int) and n > 0 else None

    def dispositivo_scelto(self, voce: str) -> dict | None:
        """La scelta CPU/GPU della taratura per questa voce (o per un'altra: la macchina è la
        stessa): {"scelta", "motivo", "causa", "quando", "cpu_s_car", "cuda_s_car", "memoria"}."""
        t = self.dati.get("dispositivo") or {}
        d = t.get(Path(str(voce or "?")).stem)
        if not isinstance(d, dict):
            d = next((x for x in t.values() if isinstance(x, dict)), None)
        return d if isinstance(d, dict) and d.get("scelta") in ("cpu", "cuda") else None

    # ── scrittura ──
    def segna_dispositivo(self, voce: str, info: dict):
        with self._lock:
            self.dati.setdefault("dispositivo", {})[Path(str(voce)).stem] = {
                **info, "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.salva()

    def osserva(self, voce: str, thread, caratteri: int, sintesi_s: float, audio_s: float):
        """Una sintesi vera: aggiorna la stima dall'uso (mediana robusta) e ogni tanto salva."""
        if caratteri < MIN_CARATTERI or sintesi_s <= 0 or audio_s <= 0:
            return
        s, p = sintesi_s / caratteri, caratteri / audio_s
        with self._lock:
            uso = self._voce(chiave(voce, thread))["uso"]
            for nome, x in (("sintesi", s), ("parlato", p)):
                serie = uso.setdefault(nome, [])
                if len(serie) >= 5:
                    m = statistics.median(serie)
                    if m > 0 and not (m / ANOMALO <= x <= m * ANOMALO):
                        return          # anomalo: la sintesi intera non conta
            uso["sintesi"].append(round(s, 6))
            uso["parlato"].append(round(p, 3))
            for nome in ("sintesi", "parlato"):
                del uso[nome][:-FINESTRA]
            dovuto = time.monotonic() - self._salvata >= SALVA_OGNI_S
        if dovuto:
            self.salva()

    def segna_avvio(self, voce: str, thread, parlato_car_s: float, sintesi_s_car: float,
                    thread_misure: dict | None = None):
        with self._lock:
            v = self._voce(chiave(voce, thread))
            v["avvio"] = {"parlato_car_s": round(parlato_car_s, 3),
                          "sintesi_s_car": round(sintesi_s_car, 6),
                          "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if thread_misure:
                self.dati["thread"][Path(str(voce)).stem] = int(thread)
                v["avvio"]["thread_misure"] = thread_misure
        self.salva()

    def salva(self):
        self._salvata = time.monotonic()
        if self.path is None:
            return
        from .persistenza import scrivi_json
        with self._lock:
            dati = copy.deepcopy(self.dati)
        try:
            scrivi_json(self.path, dati)
        except OSError as e:
            print(f"   [TTS] Taratura della voce non salvata ({e})", flush=True)


# ── una per cartella della configurazione ──
_TARATURE: dict[str, Taratura] = {}
_TARATURE_LOCK = threading.Lock()


def percorso(cfg) -> Path | None:
    forzato = os.environ.get("CALLIOPE_TARATURA_VOCE")
    if forzato:
        return Path(forzato)
    base = getattr(cfg, "config_dir", None)
    return Path(base) / FILE if base else None


def per(cfg) -> Taratura:
    p = percorso(cfg)
    k = str(p) if p is not None else f"memoria:{id(cfg)}"
    with _TARATURE_LOCK:
        t = _TARATURE.get(k)
        if t is None:
            t = _TARATURE[k] = Taratura(p)
        return t


# ── la taratura all'avvio ──
def misura(sintetizza, voice, rate: int, volte: int = 3) -> tuple[float, float]:
    """(secondi di sintesi a carattere, caratteri al secondo di voce) della FRASE: la migliore
    di `volte` (la prima scalda la sessione). `sintetizza(voice, testo) → PCM int16`."""
    migliore, audio_s = float("inf"), 0.0
    for _ in range(max(1, volte)):
        t0 = time.perf_counter()
        pcm = sintetizza(voice, FRASE)
        migliore = min(migliore, time.perf_counter() - t0)
        audio_s = len(pcm) / 2 / max(1, rate)
    n = len(FRASE)
    return migliore / n, (n / audio_s if audio_s > 0 else PREDEFINITI["parlato_car_s"])


def prova_thread(voice, voice_path: str, sintetizza, rate: int,
                 candidati: list[int]) -> tuple[int, object, dict]:
    """Prova la voce con pochi numeri di thread (una sessione di onnxruntime per numero, su
    una copia della voce: quella in uso non si tocca). (migliore, sua sessione, misure)."""
    import onnxruntime
    misure, tenuta = {}, (None, None)      # una sessione sola tenuta: la migliore finora
    for n in candidati:
        o = onnxruntime.SessionOptions()
        o.intra_op_num_threads = n
        o.inter_op_num_threads = 1
        sess = onnxruntime.InferenceSession(
            str(voice_path), sess_options=o, providers=["CPUExecutionProvider"])
        prova = copy.copy(voice)
        prova.session = sess
        misure[n] = round(misura(sintetizza, prova, rate, volte=3)[0], 6)
        # A parità (entro il 5 %) meno thread: lasciano CPU al resto (i candidati crescono)
        if tenuta[0] is None or misure[n] < misure[tenuta[0]] / 1.05:
            tenuta = (n, sess)
        del prova, sess
    return tenuta[0], tenuta[1], {str(k): v for k, v in misure.items()}


# ── CPU o GPU (07/10) ──
# Memoria GPU di serena-high con CUDA, misurata sulla DGX: 1,34–1,45 GiB nel processo (contesto
# CUDA e cuDNN ~0,4, il resto l'arena di onnxruntime che cresce con le frasi lunghe)
PIPER_GPU_GB = 1.5
# GPU dedicata: sotto questa VRAM totale la GPU è della voce e di Whisper (il portatile da 8 GB
# ne ha 0,5 liberi con e4b e Whisper caricati; ricerca 2026-10-07-taratura-macchina, §2)
MIN_DEDICATA_GB = 12.0
# Quanto deve restare libero dopo Piper: su una GPU dedicata la cache della voce che cresce, un
# modello caricato dopo; su memoria unificata il sistema e i servizi accanto (la DGX ha ~21 GB
# disponibili con vLLM, Ollama e whisper.cpp caricati)
MARGINE_DEDICATA_GB = 2.0
MARGINE_UNIFICATA_GB = 8.0
# La GPU si sceglie solo se a riposo è almeno 2 volte più veloce: sotto contesa (la voce che
# genera su Ollama nello stesso momento, misura del 07/10 sulla DGX) la sintesi sulla GPU
# rallenta di 1,8 volte, e deve restare più veloce della CPU anche lì
GPU_VANTAGGIO = 2.0
DISPOSITIVI = ("auto", "cpu", "cuda")


def cuda_disponibile() -> bool:
    """onnxruntime ha il provider CUDA (onnxruntime-gpu). Non dice che le librerie di CUDA e
    cuDNN ci siano: lo dice solo una sintesi di prova (tts.carica_voce, prova_dispositivo)."""
    try:
        import onnxruntime
        return "CUDAExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:  # noqa: BLE001
        return False


def memoria_gpu() -> dict | None:
    """La memoria della prima GPU NVIDIA: {"unificata", "totale_gb", "libera_gb"}, None senza
    nvidia-smi. Sul GB10 (DGX Spark) nvidia-smi dice «[N/A]»: memoria unificata, e la libera è
    MemAvailable del sistema."""
    import subprocess
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,memory.free",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True,
                           timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    righe = (r.stdout or "").strip().splitlines()
    if r.returncode != 0 or not righe:
        return None
    valori = [x.strip() for x in righe[0].split(",")]
    try:
        tot, libera = float(valori[0]), float(valori[1])
        return {"unificata": False, "totale_gb": round(tot / 1024, 2),
                "libera_gb": round(libera / 1024, 2)}
    except (ValueError, IndexError):
        pass
    try:
        import re
        info = Path("/proc/meminfo").read_text(encoding="utf-8")
        tot = int(re.search(r"^MemTotal:\s*(\d+)", info, re.M).group(1))
        libera = int(re.search(r"^MemAvailable:\s*(\d+)", info, re.M).group(1))
        return {"unificata": True, "totale_gb": round(tot / 2**20, 2),
                "libera_gb": round(libera / 2**20, 2)}
    except (OSError, AttributeError, ValueError):
        return None


def _gb(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def posto_gpu(mem: dict | None) -> tuple[bool, str]:
    """Se Piper ci sta sulla GPU dopo i modelli di Calliope già caricati, e perché."""
    if not mem:
        return False, "nessuna GPU NVIDIA vista da nvidia-smi"
    libera, tot = float(mem.get("libera_gb") or 0), float(mem.get("totale_gb") or 0)
    if mem.get("unificata"):
        if libera - PIPER_GPU_GB < MARGINE_UNIFICATA_GB:
            return False, (f"memoria unificata con {_gb(libera)} GB liberi: ne servono "
                           f"{_gb(PIPER_GPU_GB + MARGINE_UNIFICATA_GB)} con il margine")
        return True, f"memoria unificata con {_gb(libera)} GB liberi"
    if tot < MIN_DEDICATA_GB:
        return False, f"GPU dedicata da {_gb(tot)} GB: la tengono la voce e Whisper"
    if libera - PIPER_GPU_GB < MARGINE_DEDICATA_GB:
        return False, (f"GPU dedicata con {_gb(libera)} GB liberi: ne servono "
                       f"{_gb(PIPER_GPU_GB + MARGINE_DEDICATA_GB)} con il margine")
    return True, f"GPU dedicata con {_gb(libera)} GB liberi su {_gb(tot)}"


def sessione_cuda(voice_path: str):
    """Una sessione di onnxruntime sulla GPU (provider CUDA, CPU per i nodi che restano lì).
    Le librerie di CUDA e cuDNN dei pacchetti nvidia-* di pip si caricano con preload_dlls
    (onnxruntime 1.21 e successivi): senza, la prima convoluzione fallisce con «libcudnn.so»
    mancante. Errore se il provider CUDA non si è aperto (onnxruntime ripiega sulla CPU in
    silenzio)."""
    import onnxruntime
    if hasattr(onnxruntime, "preload_dlls"):
        try:
            onnxruntime.preload_dlls()
        except Exception:  # noqa: BLE001 — se mancano, lo dice la sintesi di prova
            pass
    o = onnxruntime.SessionOptions()
    o.log_severity_level = 3        # niente avvisi sui nodi Memcpy a ogni apertura
    sess = onnxruntime.InferenceSession(
        str(voice_path), sess_options=o,
        providers=[("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"}),
                   "CPUExecutionProvider"])
    if "CUDAExecutionProvider" not in sess.get_providers():
        raise RuntimeError("provider CUDA non aperto")
    return sess


def prova_dispositivo(voice, voice_path: str, sintetizza, rate: int, cpu_s_car: float,
                      mem_fn=memoria_gpu, sessione_fn=sessione_cuda) -> tuple[str, object, dict]:
    """Taratura CPU/GPU: (scelta, sessione CUDA se scelta, info da salvare). Prima il posto
    (senza aprire niente sulla GPU), poi la misura della frase fissa sulla GPU contro quella
    sulla CPU appena fatta; GPU solo se GPU_VANTAGGIO volte più veloce."""
    mem = mem_fn()
    info = {"memoria": mem, "cpu_s_car": round(cpu_s_car, 6)}
    ok, perche = posto_gpu(mem)
    if not ok:
        return "cpu", None, {**info, "scelta": "cpu", "causa": "memoria", "motivo": perche}
    try:
        sess = sessione_fn(voice_path)
        prova = copy.copy(voice)
        prova.session = sess
        gpu_s_car = misura(sintetizza, prova, rate, volte=3)[0]
        del prova
    except Exception as e:  # noqa: BLE001 — librerie di CUDA mancanti, GPU occupata…
        return "cpu", None, {**info, "scelta": "cpu", "causa": "errore",
                             "motivo": f"GPU non usabile ({type(e).__name__}: "
                                       f"{str(e).strip()[-160:]})"}
    info["cuda_s_car"] = round(gpu_s_car, 6)
    ms = f"{gpu_s_car * 1000:.1f} ms a carattere contro {cpu_s_car * 1000:.1f}".replace(".", ",")
    if gpu_s_car * GPU_VANTAGGIO <= cpu_s_car:
        return "cuda", sess, {**info, "scelta": "cuda", "causa": "misura",
                              "motivo": f"{perche}, GPU {ms} della CPU"}
    return "cpu", None, {**info, "scelta": "cpu", "causa": "misura",
                         "motivo": f"GPU non abbastanza più veloce ({ms} della CPU)"}


def da_provare(cfg, voce: str) -> bool:
    """La taratura all'avvio prova la GPU: con «auto», onnxruntime con CUDA e nessuna scelta
    salvata, o una CPU scelta per mancanza di posto (la memoria può essersi liberata) o per un
    errore (le librerie di CUDA installate dopo, con l'extra voce-gpu). Una CPU scelta perché
    misurata più veloce resta: per riprovare si toglie `dispositivo` da voce_taratura.json."""
    scritto = str(getattr(cfg, "tts_dispositivo", "auto") or "auto").lower()
    if scritto != "auto" or not cuda_disponibile():
        return False
    s = per(cfg).dispositivo_scelto(voce)
    return s is None or (s["scelta"] == "cpu" and s.get("causa") in ("memoria", "errore"))


def dispositivo_in_uso(cfg, voce: str, controlla_posto: bool = True,
                       mem_fn=memoria_gpu) -> tuple[str, str]:
    """(«cpu» o «cuda», perché) per aprire la voce. `tts_dispositivo` scritto vince; con «auto»
    la scelta della taratura, ricontrollata all'apertura (`controlla_posto`): il posto sulla GPU
    (i modelli caricati possono essere cambiati) e l'uso (se dalle sintesi vere la GPU non è
    più veloce della CPU misurata, si torna alla CPU). Prima della taratura: CPU."""
    scritto = str(getattr(cfg, "tts_dispositivo", "auto") or "auto").lower()
    if scritto == "cpu":
        return "cpu", "scritto in tts_dispositivo"
    if not cuda_disponibile():
        return "cpu", ("tts_dispositivo: cuda, ma onnxruntime non ha CUDA" if scritto == "cuda"
                       else "onnxruntime senza CUDA")
    if scritto == "cuda":
        return "cuda", "scritto in tts_dispositivo"
    s = per(cfg).dispositivo_scelto(voce)
    if s is None:
        return "cpu", "GPU da provare alla taratura"
    if s["scelta"] != "cuda":
        return "cpu", str(s.get("motivo") or "scelta della taratura")
    if controlla_posto:
        ok, perche = posto_gpu(mem_fn())
        if not ok:
            return "cpu", f"scelta la GPU, ma ora {perche}"
        uso = per(cfg).stima(voce, "cuda")
        cpu = s.get("cpu_s_car")
        if uso["fonte"] == "uso" and cpu and uso["sintesi_s_car"] >= cpu:
            return "cpu", "dall'uso la GPU non è più veloce della CPU"
    return "cuda", str(s.get("motivo") or "scelta della taratura")


def sessione_in_uso(cfg, voce: str):
    """La chiave delle misure della voce in uso: «cuda» o i thread (per `calliope stato`)."""
    if dispositivo_in_uso(cfg, voce, controlla_posto=False)[0] == "cuda":
        return "cuda"
    return thread_in_uso(cfg, voce)


def thread_in_uso(cfg, voce: str) -> int:
    """I thread con cui si apre la voce (lo stesso criterio di tts.numero_thread): il numero
    scritto in `tts_thread`, con «auto» la scelta della taratura o 8, mai più dei processori
    logici. 0 = quelli di Piper."""
    n = getattr(cfg, "tts_thread", "auto")
    if isinstance(n, int) and not isinstance(n, bool):
        return max(0, n)
    return per(cfg).thread_scelto(voce) or min(8, os.cpu_count() or 8)


def testo_stato(cfg) -> str | None:
    """Per `calliope stato` e il registro delle capacità: la stima della voce in uso."""
    t = per(cfg)
    voce = getattr(cfg, "piper_voice", "")
    scritto = getattr(cfg, "tts_thread", "auto")
    thread = thread_in_uso(cfg, voce)
    dispositivo, motivo = dispositivo_in_uso(cfg, voce, controlla_posto=False)
    s = t.stima(voce, "cuda" if dispositivo == "cuda" else thread)
    fonte = {"uso": f"dall'uso, {s['n']} sintesi", "avvio": "dalla taratura all'avvio",
             "predefiniti": "predefiniti prudenti, non ancora tarata"}[s["fonte"]]
    if dispositivo == "cuda":
        quanti = "sulla GPU"
    elif not thread:
        quanti = "thread di Piper"
    elif isinstance(scritto, int):
        quanti = f"{thread} thread, scritti in tts_thread"
    elif t.thread_scelto(voce):
        quanti = f"{thread} thread, scelti dalla taratura"
    else:
        quanti = f"{thread} thread, da scegliere alla taratura"
    ms = f"{s['sintesi_s_car'] * 1000:.1f}".replace(".", ",")
    dove = "GPU" if dispositivo == "cuda" else "CPU"
    return (f"Voce {Path(str(voce)).stem}: sintesi {ms} ms a carattere, "
            f"{s['parlato_car_s']:.0f} caratteri al secondo ({fonte}); {quanti}; "
            f"{dove}: {motivo}.")
