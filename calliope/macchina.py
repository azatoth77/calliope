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
