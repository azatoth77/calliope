"""
Su che macchina gira Calliope (04/10/2026): per «su che hardware giri?», «che configurazione
hai?» (tool calliope_stato con cosa=macchina). Prima rispondeva con l'elenco delle capacità.

Solo letture locali con la libreria standard, niente programmi esterni né librerie nuove
(principio 4): su Windows il registro (winreg) e GlobalMemoryStatusEx (ctypes), su Linux
/proc e /sys (anche la GPU NVIDIA: /proc/driver/nvidia/gpus/*/information, senza
nvidia-smi). Niente dati sensibili: né indirizzi, né nomi utente, né percorsi; dei modelli
remoti solo il nome e «su un altro computer».

I dati della macchina non cambiano mentre Calliope gira: si leggono una volta (`dati`).
"""

from __future__ import annotations

import functools
import glob
import os
import platform
import re


def _leggi(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _pulisci(nome: str) -> str:
    """«Intel(R) Core(TM) Ultra 9 275HX» → «Intel Core Ultra 9 275HX»: niente marchi."""
    nome = re.sub(r"\((?:R|TM|C)\)|®|™", "", nome or "", flags=re.I)
    return re.sub(r"\s+", " ", nome).strip(" \x00")


def _reg(chiave: str, valore: str):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chiave) as k:
            return winreg.QueryValueEx(k, valore)[0]
    except (ImportError, OSError):
        return None


def _windows() -> dict:
    d: dict = {}
    marca = _pulisci(str(_reg(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemManufacturer")
                         or ""))
    prodotto = _pulisci(str(_reg(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemProductName")
                            or ""))
    if prodotto.lower() in ("system product name", "to be filled by o.e.m.", "default string"):
        prodotto = ""
    d["modello"] = (prodotto if not marca or prodotto.lower().startswith(marca.lower().split()[0])
                    else f"{marca} {prodotto}".strip())
    d["processore"] = _pulisci(str(_reg(
        r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString") or ""))
    try:
        import ctypes

        class _Mem(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _Mem()
        m.dwLength = ctypes.sizeof(_Mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            d["memoria_gb"] = m.ullTotalPhys / 2**30
    except (ImportError, AttributeError, OSError):
        pass
    # Schede video: la classe «Display» dei driver; la memoria dedicata è un QWORD
    classe = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    gpu = []
    for i in range(8):
        nome = _reg(fr"{classe}\{i:04d}", "DriverDesc")
        if not nome:
            continue
        mem = _reg(fr"{classe}\{i:04d}", "HardwareInformation.qwMemorySize")
        if isinstance(mem, bytes):
            mem = int.from_bytes(mem[:8], "little")
        gb = mem / 2**30 if isinstance(mem, int) and mem > 0 else None
        if "basic" in str(nome).lower() or "remote" in str(nome).lower():
            continue
        gpu.append((_pulisci(str(nome)), gb))
    d["gpu"] = gpu
    ver = platform.version().split(".")
    build = int(ver[2]) if len(ver) > 2 and ver[2].isdigit() else 0
    d["sistema"] = f"Windows {'11' if build >= 22000 else platform.release()}"
    return d


def _linux() -> dict:
    d: dict = {}
    prodotto = _leggi("/sys/class/dmi/id/product_name").strip()
    if not prodotto or prodotto.lower() in ("default string", "to be filled by o.e.m."):
        prodotto = _leggi("/proc/device-tree/model").strip(" \x00\n")
    # Un codice d'ordine al posto del nome (la DGX di Lenovo: «30KL0005IE», famiglia «DGX
    # Spark»): meglio la marca e la famiglia, che a voce dicono qualcosa
    famiglia = _leggi("/sys/class/dmi/id/product_family").strip()
    if (famiglia and famiglia.lower() not in ("default string", "to be filled by o.e.m.")
            and re.fullmatch(r"[A-Z0-9-]*\d[A-Z0-9-]*", prodotto or "0")):
        marca = _leggi("/sys/class/dmi/id/sys_vendor").strip()
        if marca.isupper() and len(marca) > 4:
            marca = marca.title()
        prodotto = f"{marca} {famiglia}" if marca and marca.lower() not in famiglia.lower() \
            else famiglia
    d["modello"] = _pulisci(prodotto)
    cpu = _leggi("/proc/cpuinfo")
    m = re.search(r"^model name\s*:\s*(.+)$", cpu, re.M)
    d["processore"] = _pulisci(m.group(1)) if m else ""
    m = re.search(r"^MemTotal:\s*(\d+)\s*kB", _leggi("/proc/meminfo"), re.M)
    if m:
        d["memoria_gb"] = int(m.group(1)) / 2**20
    gpu = []
    for info in sorted(glob.glob("/proc/driver/nvidia/gpus/*/information")):
        m = re.search(r"^Model:\s*(.+)$", _leggi(info), re.M)
        if m:
            gpu.append((_pulisci(m.group(1)), None))
    d["gpu"] = gpu
    rel = _leggi("/etc/os-release")
    m = re.search(r'^PRETTY_NAME="?([^"\n]+)', rel, re.M)
    d["sistema"] = m.group(1) if m else "Linux"
    return d


@functools.lru_cache(maxsize=1)
def dati() -> dict:
    """Modello del computer, processore, core, memoria, GPU, sistema e architettura."""
    try:
        d = _windows() if os.name == "nt" else _linux()
    except Exception:  # noqa: BLE001 — una lettura strana non deve far cadere il tool
        d = {}
    d["core"] = os.cpu_count() or 0
    arch = platform.machine().lower()
    d["arch"] = ("ARM" if arch in ("arm64", "aarch64") or arch.startswith("arm")
                 else "x86 a 64 bit" if arch in ("amd64", "x86_64") else arch)
    return d


def _gb(x: float) -> str:
    """La memoria come la dice chi l'ha comprata: 31,46 GB visti da Windows → «32 GB»."""
    for n in (2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 512):
        if n * 0.9 <= x <= n * 1.02:
            return f"{n} GB"
    return f"{round(x)} GB"


def _dove(url: str | None) -> str:
    """«sullo stesso computer» o «su un altro computer della rete»: mai l'indirizzo."""
    host = str(url or "").split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0].strip("[]")
    return ("sullo stesso computer" if host.lower() in ("127.0.0.1", "localhost", "::1", "")
            else "su un altro computer")


def _modello_voce(nome: str) -> str:
    """«gemma4:e4b-it-qat» → «gemma4 e4b»: il nome detto a voce, senza le sigle del file."""
    nome = re.sub(r"[-:](it|instruct|qat|q4_k_m|q8_0|nvfp4|fp8|gguf)\b", "", nome or "", flags=re.I)
    return re.sub(r"[:_]", " ", nome).strip()


def descrivi(cfg, lavori=None) -> str:
    """La frase per la voce: la macchina, poi i modelli (voce, trascrizione, agente)."""
    d = dati()
    pezzi = []
    testa = "Giro su " + (f"un {d['modello']}" if d.get("modello") else "un computer")
    if d.get("sistema"):
        testa += f" con {d['sistema']}"
    pezzi.append(testa + ".")
    hw = []
    if d.get("processore"):
        hw.append(f"un processore {d['processore']}"
                  + (f" con {d['core']} core" if d.get("core") else ""))
    elif d.get("core"):
        hw.append(f"un processore {d['arch']} con {d['core']} core")
    if d.get("memoria_gb"):
        hw.append(f"{_gb(d['memoria_gb'])} di memoria")
    gpu = [nome + (f" da {_gb(gb)}" if gb else "") for nome, gb in d.get("gpu") or ()]
    if gpu:
        hw.append(("scheda video " if len(gpu) == 1 else "schede video ")
                  + " e ".join(gpu))
    if hw:
        pezzi.append("Ha " + (", ".join(hw[:-1]) + " e " + hw[-1] if len(hw) > 1 else hw[0])
                     + ".")
    url = cfg.llm_native_url if getattr(cfg, "llm_backend", "") == "ollama" else \
        getattr(cfg, "llm_base_url", None)
    motore = "vLLM" if "vllm" in str(getattr(cfg, "llm_profilo", "") or "").lower() else \
        "Ollama" if getattr(cfg, "llm_backend", "") == "ollama" else "un server compatibile OpenAI"
    pezzi.append(f"Per parlare uso il modello {_modello_voce(cfg.llm_model)} su {motore}, "
                 f"{_dove(url)}.")
    if getattr(cfg, "stt_motore", "locale") == "server":
        pezzi.append(f"Per capire cosa dici uso Whisper su un server, {_dove(cfg.stt_url)}.")
    else:
        dev = "sulla scheda video" if str(getattr(cfg, "whisper_device", "")) == "cuda" \
            else "sul processore"
        pezzi.append(f"Per capire cosa dici uso Whisper {cfg.whisper_model} {dev}.")
    imp = getattr(lavori, "imp", None)
    if imp is not None and getattr(imp, "modello", None):
        pezzi.append(f"Per i lavori lunghi c'è l'agente {_modello_voce(imp.modello)} "
                     f"{imp.su_nome}.")
    return " ".join(pezzi)


# ─────────────────────────── inventario per il piano ───────────────────────────
# 08/10/2026, fase 1 della taratura della macchina (docs/ricerche/2026-10-07-taratura-macchina.md,
# §1.3 e §2): i numeri che decidono il piano dei modelli. Memoria veloce per pool (VRAM
# dedicata o memoria unificata), banda (dalla tabella di calliope/modelli.py: non si legge da
# nessuna parte), memoria libera adesso, motori (Ollama, vLLM, server di Whisper, CUDA per
# onnxruntime e CTranslate2) con versioni e modelli. Solo letture locali (127.0.0.1) e la
# libreria standard; ogni sonda che non risponde lascia il suo dato a None.
# Unità: GB = 10^9 byte (nvidia-smi dà MiB, /proc/meminfo kB).
_GB = 1e9
OLLAMA_LOCALE = "http://127.0.0.1:11434"
# vLLM della DGX: agente sulla 8000, voce di prova sulla 8001 (setup/linux/motore/vllm.sh)
VLLM_LOCALI = ("http://127.0.0.1:8000/v1", "http://127.0.0.1:8001/v1")
_VARIABILI_OLLAMA = ("OLLAMA_MAX_LOADED_MODELS", "OLLAMA_NUM_PARALLEL", "OLLAMA_KV_CACHE_TYPE",
                     "OLLAMA_FLASH_ATTENTION")


class Sonde:
    """Le letture della macchina vera. Le prove ne passano una finta (stessi metodi)."""

    def __init__(self):
        self.os = "windows" if os.name == "nt" else "linux"
        arch = platform.machine().lower()
        self.arch = "aarch64" if arch in ("arm64", "aarch64") else \
            "x86_64" if arch in ("amd64", "x86_64") else arch

    def base(self) -> dict:
        return dati()

    def comando(self, argv: list[str], timeout: float = 5) -> str | None:
        import subprocess
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None

    def leggi(self, path: str) -> str:
        return _leggi(path)

    def get(self, url: str, timeout: float = 1.5) -> str | None:
        """Il corpo di una GET locale, None se non risponde (anche 4xx/5xx: None)."""
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 — 127.0.0.1
                return r.read(4_000_000).decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def libera_windows(self) -> float | None:
        try:
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _Mem()
            m.dwLength = ctypes.sizeof(_Mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullAvailPhys / _GB
        except (ImportError, AttributeError, OSError):
            pass
        return None

    def librerie(self) -> dict:
        """CUDA per onnxruntime (Piper sulla GPU) e per CTranslate2 (faster-whisper)."""
        out: dict = {"onnxruntime_cuda": None, "ctranslate2_cuda": None}
        try:
            import onnxruntime
            out["onnxruntime_cuda"] = "CUDAExecutionProvider" in \
                onnxruntime.get_available_providers()
        except Exception:  # noqa: BLE001 — assente o rotta: non si sa
            pass
        try:
            import ctranslate2
            out["ctranslate2_cuda"] = int(ctranslate2.get_cuda_device_count())
        except Exception:  # noqa: BLE001
            pass
        return out


def _json(testo: str | None):
    import json
    try:
        return json.loads(testo) if testo else None
    except ValueError:
        return None


def _gpu_nvidia(s: Sonde) -> dict | None:
    """La prima GPU NVIDIA da nvidia-smi: nome, memoria totale e libera (None se [N/A]:
    memoria unificata, come il GB10 della DGX), driver."""
    out = s.comando(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
                     "--format=csv,noheader,nounits"])
    righe = [r for r in (out or "").splitlines() if r.strip()]
    if not righe:
        return None
    v = [x.strip() for x in righe[0].split(",")]

    def mib(x):
        try:
            return round(float(x) * 1048576 / _GB, 2)
        except (TypeError, ValueError):
            return None
    return {"nome": _pulisci(v[0]), "memoria_gb": mib(v[1] if len(v) > 1 else None),
            "libera_gb": mib(v[2] if len(v) > 2 else None),
            "driver": v[3] if len(v) > 3 else None, "fonte": "nvidia-smi"}


def _meminfo(s: Sonde) -> tuple[float | None, float | None]:
    testo = s.leggi("/proc/meminfo")
    tot = re.search(r"^MemTotal:\s*(\d+)", testo, re.M)
    lib = re.search(r"^MemAvailable:\s*(\d+)", testo, re.M)
    return (int(tot.group(1)) * 1024 / _GB if tot else None,
            int(lib.group(1)) * 1024 / _GB if lib else None)


def _variabili_ollama(s: Sonde) -> dict:
    """Le variabili di Ollama che contano per il piano: dal servizio systemd (Linux, sola
    lettura, senza sudo) e dall'ambiente di questo processo."""
    out = {k: os.environ[k] for k in _VARIABILI_OLLAMA if os.environ.get(k)}
    if s.os == "linux":
        for argv in (["systemctl", "show", "ollama.service", "--property=Environment"],
                     ["systemctl", "--user", "show", "ollama.service",
                      "--property=Environment"]):
            testo = s.comando(argv, timeout=2) or ""
            for k in _VARIABILI_OLLAMA:
                m = re.search(rf"\b{k}=(\S+)", testo)
                if m and k not in out:
                    out[k] = m.group(1)
    return out


def _ollama(s: Sonde, url: str) -> dict | None:
    url = url.rstrip("/")
    ver = _json(s.get(url + "/api/version"))
    if not isinstance(ver, dict):
        return None
    tags = _json(s.get(url + "/api/tags")) or {}
    ps = _json(s.get(url + "/api/ps")) or {}
    installati = [{"nome": m.get("name"), "gb": round((m.get("size") or 0) / _GB, 2)}
                  for m in tags.get("models") or [] if m.get("name")]
    caricati = []
    for m in ps.get("models") or []:
        size, vram = m.get("size") or 0, m.get("size_vram")
        caricati.append({"nome": m.get("name") or m.get("model"),
                         "gb": round(size / _GB, 2),
                         "gb_gpu": round(vram / _GB, 2) if isinstance(vram, int) else None,
                         "contesto": m.get("context_length"),
                         # Una parte sulla CPU: generazione 3–10 volte più lenta (§5.1)
                         "in_parte_cpu": isinstance(vram, int) and 0 < size and vram < size})
    return {"url": url, "versione": ver.get("version"), "installati": installati,
            "caricati": caricati, "variabili": _variabili_ollama(s)}


def _vllm(s: Sonde, url: str) -> dict | None:
    url = url.rstrip("/")
    modelli = _json(s.get(url + "/models"))
    if not isinstance(modelli, dict) or not isinstance(modelli.get("data"), list):
        return None
    radice = re.sub(r"/v1$", "", url)
    ver = _json(s.get(radice + "/version")) or {}
    metriche = s.get(radice + "/metrics") or ""
    cache = utilizzo = None
    for riga in metriche.splitlines():
        if riga.startswith("vllm:cache_config_info"):
            m = re.search(r'kv_cache_size_tokens="(\d+)"', riga)
            cache = int(m.group(1)) if m else None
            m = re.search(r'gpu_memory_utilization="([\d.]+)"', riga)
            utilizzo = float(m.group(1)) if m else None
            break
    return {"url": url, "versione": ver.get("version"),
            "modelli": [{"id": m.get("id"), "radice": m.get("root"),
                         "max_model_len": m.get("max_model_len")}
                        for m in modelli["data"] if isinstance(m, dict)],
            "cache_token": cache, "gpu_memory_utilization": utilizzo}


def _locale(url: str | None) -> bool:
    host = str(url or "").split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0].strip("[]")
    return host in ("127.0.0.1", "localhost", "::1")


def inventario(cfg=None, sonde: Sonde | None = None) -> dict:
    """La macchina per il piano (calliope/piano.py): dizionario serializzabile in JSON."""
    import datetime
    from . import modelli as cat
    s = sonde or Sonde()
    try:
        base = dict(s.base() or {})
    except Exception:  # noqa: BLE001
        base = {}
    inv: dict = {"catalogo": cat.VERSIONE,
                 "quando": datetime.datetime.now().isoformat(timespec="seconds"),
                 "modello": base.get("modello") or "",
                 "processore": base.get("processore") or "",
                 "core": base.get("core") or os.cpu_count() or 0,
                 "sistema": base.get("sistema") or "", "os": s.os, "arch": s.arch,
                 "ram_gb": round(base["memoria_gb"] * 2**30 / _GB, 2)
                 if base.get("memoria_gb") else None,
                 "ram_libera_gb": None, "avvisi": []}
    if s.os == "linux":
        tot, lib = _meminfo(s)
        inv["ram_gb"] = round(tot, 2) if tot else inv["ram_gb"]
        inv["ram_libera_gb"] = round(lib, 2) if lib else None
    else:
        lib = s.libera_windows()
        inv["ram_libera_gb"] = round(lib, 2) if lib else None
    # GPU: nvidia-smi, altrimenti il nome (e la VRAM dal registro su Windows) di `dati`
    g = _gpu_nvidia(s)
    if g is None and base.get("gpu"):
        nome, gib = base["gpu"][0]
        g = {"nome": nome, "memoria_gb": round(gib * 2**30 / _GB, 2) if gib else None,
             "libera_gb": None, "driver": None, "fonte": "registro" if gib else "nome"}
    if g:
        riga = cat.gpu_da_nome(g["nome"])
        unificata = riga.unificata or (g["fonte"] == "nvidia-smi" and g["memoria_gb"] is None)
        if unificata:
            # Memoria unificata: il pool è la RAM; la libera è quella del sistema
            g["memoria_gb"], g["libera_gb"] = inv["ram_gb"], inv["ram_libera_gb"]
        g.update(unificata=unificata, chiave=riga.chiave, banda_gbs=riga.banda_gbs,
                 banda_fonte=riga.fonte, lettura_rel=riga.lettura_rel,
                 produttore=riga.produttore)
        if riga is cat.GPU_IGNOTA:
            inv["avvisi"].append(f"GPU «{g['nome']}» non nel catalogo: banda stimata "
                                 f"{int(riga.banda_gbs)} GB/s, da misurare")
    inv["gpu"] = g
    # Motori
    motori: dict = {"ollama": None, "vllm": [], "whisper_server": None}
    urls = [OLLAMA_LOCALE]
    for u in (getattr(cfg, "llm_native_url", None), getattr(cfg, "guardiano_url", None)):
        if u and _locale(u) and u.rstrip("/") not in urls:
            urls.append(u.rstrip("/"))
    for u in urls:
        o = _ollama(s, u)
        if o:
            motori["ollama"] = o
            break
    vurls = list(VLLM_LOCALI)
    if getattr(cfg, "llm_backend", "") == "openai" and _locale(getattr(cfg, "llm_base_url", "")):
        u = cfg.llm_base_url.rstrip("/")
        vurls = [u] + [x for x in vurls if x != u]
    for u in vurls:
        v = _vllm(s, u)
        if v:
            motori["vllm"].append(v)
    if getattr(cfg, "stt_motore", "locale") == "server" and getattr(cfg, "stt_url", None):
        radice = re.sub(r"/v1/?$", "", cfg.stt_url.rstrip("/"))
        motori["whisper_server"] = {"locale": _locale(radice),
                                    "attivo": s.get(radice + "/") is not None
                                    if _locale(radice) else None}
    motori.update(s.librerie())
    inv["motori"] = motori
    for m in (motori["ollama"] or {}).get("caricati", []):
        if m.get("in_parte_cpu"):
            inv["avvisi"].append(f"{m['nome']} è in parte sulla CPU ({m['gb_gpu']} GB su "
                                 f"{m['gb']} nella GPU): genera 3–10 volte più lento")
    return inv
