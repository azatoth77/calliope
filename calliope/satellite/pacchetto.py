"""
Il pacchetto del satellite (03/10/2026): quello che il server dà a un PC nuovo e ai satelliti
installati che sono rimasti indietro. Solo libreria standard (più `packaging`, se c'è, per
controllare i wheel).

Un file zip **deterministico** (stesso contenuto → stessi byte → stesso SHA-256) costruito al
volo dalla versione di Calliope in uso sul server:

    calliope/…                    solo i moduli che il satellite importa (chiusura degli
                                  import a partire dai suoi punti d'ingresso, letta con `ast`)
    calliope/satellite/installazione/avvio.py   l'avvio con gli aggiornamenti (stdlib)
    wakeword/modelli/*.onnx       la wake word (calliope.onnx e i due modelli generici)
    requisiti.txt                 le librerie con versioni e SHA-256 presi da uv.lock (solo
                                  quelle del satellite e, su Windows, quelle del PC), con le
                                  loro dipendenze e i marcatori
    requisiti-senza-dipendenze.txt   silero-vad: serve solo il suo file ONNX
    VERSIONE.json                 versione (impronta del contenuto), Python, uv

La **versione** è l'impronta del contenuto (i primi 12 caratteri dello SHA-256 dei file in
ordine): un aggiornamento del server che non tocca niente del satellite non ne fa partire uno
sui satelliti. uv (binario ufficiale) e Python hanno la versione fissata qui: uv verifica da sé
lo SHA-256 della distribuzione di Python che scarica.
"""

import ast
import hashlib
import io
import json
import re
import threading
import zipfile
from pathlib import Path

# ── versioni fissate (03/10/2026) ──
# uv 0.12.22 (01/10/2026): SHA-256 dei file .sha256 ufficiali della release su GitHub,
# controllati sul file scaricato (x86_64)
UV_VERSIONE = "0.12.22"
UV = {
    "x86_64": {
        "url": "https://github.com/astral-sh/uv/releases/download/0.12.22/"
               "uv-x86_64-pc-windows-msvc.zip",
        "sha256": "ea1397797a0ca15f63516dd0f49c2dde9776db9be5861cab152ebe8ad199894d"},
    "aarch64": {
        "url": "https://github.com/astral-sh/uv/releases/download/0.12.22/"
               "uv-aarch64-pc-windows-msvc.zip",
        "sha256": "6a42b919c2bb7135f07b4d1bb8e489f0eaab0bae039020573cc522d831e2d32e"},
}
# La stessa del portatile di sviluppo; uv 0.12.22 la ha per windows-x86_64 e -aarch64
PYTHON = "3.14.8"
PYTHON_TAG = "cp314"
PIATTAFORME = ("win_amd64", "win_arm64")

# Le librerie del satellite (setup/satellite/requisiti.txt) e, su Windows, quelle del PC a voce
PACCHETTI = ["numpy", "sounddevice", "onnxruntime", "websockets", "pyyaml"]
PACCHETTI_WINDOWS = ["pycaw", "comtypes", "pywin32", "psutil", "screen-brightness-control",
                     "winrt-windows-media-control"]
# Senza dipendenze (torch e torchaudio sarebbero centinaia di MB inutili)
SENZA_DIPENDENZE = ["silero-vad"]

# Da dove parte la chiusura degli import (anche quelli dentro le funzioni)
ENTRATE = ["calliope.satellite.__main__", "calliope.satellite.client",
           "calliope.satellite.esecutore", "calliope.satellite.inoltro",
           "calliope.satellite.aggiorna", "calliope.pc.windows"]
FILE_IN_PIU = ["calliope/satellite/installazione/avvio.py"]
MODELLI_WAKE = ("calliope.onnx", "melspectrogram.onnx", "embedding_model.onnx")

_DATA_ZIP = (1980, 1, 1, 0, 0, 0)


class PacchettoNonDisponibile(Exception):
    """Il pacchetto non si può fare (manca uv.lock, un modello della wake word…)."""


# ───────────────────────────── moduli ─────────────────────────────
def _file_modulo(radice: Path, mod: str) -> Path | None:
    p = radice.joinpath(*mod.split("."))
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    if p.with_suffix(".py").is_file():
        return p.with_suffix(".py")
    return None


def _import_di(path: Path, mod: str) -> set[str]:
    pkg = mod if path.name == "__init__.py" else mod.rsplit(".", 1)[0]
    out = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names if a.name.split(".")[0] == "calliope")
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = pkg.split(".")
                base = base[:len(base) - (n.level - 1)]
                b = ".".join(base + ([n.module] if n.module else []))
            else:
                b = n.module or ""
            if b.split(".")[0] != "calliope":
                continue
            out.add(b)
            out.update(f"{b}.{a.name}" for a in n.names)     # «from . import capacita»
    return out


def moduli(radice: Path, entrate=ENTRATE) -> list[str]:
    """I file .py (relativi a `radice`, con «/») dei moduli di calliope che il satellite può
    importare: la chiusura degli import a partire da `entrate`, pacchetti genitori compresi."""
    visti: dict[str, Path] = {}
    da_fare = list(entrate)
    while da_fare:
        m = da_fare.pop()
        if m in visti:
            continue
        p = _file_modulo(radice, m)
        if p is None:
            continue                     # un nome importato da un modulo, non un modulo
        visti[m] = p
        parti = m.split(".")
        da_fare.extend(".".join(parti[:i]) for i in range(1, len(parti)))
        da_fare.extend(_import_di(p, m))
    return sorted(p.relative_to(radice).as_posix() for p in visti.values())


# ───────────────────────────── requisiti da uv.lock ─────────────────────────────
def _norm(nome: str) -> str:
    return re.sub(r"[-_.]+", "-", nome).lower()


def _e(a: str | None, b: str | None) -> str | None:
    """Congiunzione di due marcatori (None = sempre)."""
    if not a:
        return b
    if not b:
        return a
    return f"({a}) and ({b})"


def _o(a: str | None, b: str | None) -> str | None:
    if a is None or b is None:
        return None
    return a if a == b else f"({a}) or ({b})"


def _wheel_va(nome_file: str, piattaforma: str, py_tag: str = PYTHON_TAG) -> bool:
    """Il wheel si installa su questa piattaforma e su questo Python? (cp314, abi3, py3)"""
    parti = nome_file[:-4].split("-")
    if len(parti) < 5:
        return False
    py, abi, plat = parti[-3], parti[-2], parti[-1]
    if not any(p in ("any", piattaforma) for p in plat.split(".")):
        return False
    if abi.endswith("t") and abi.startswith("cp"):          # free-threaded: no
        return False
    for t in py.split("."):
        if t in ("py3", py_tag) or t.startswith("py3"):
            return True
        if abi == "abi3" and t.startswith("cp3"):
            try:
                return int(t[3:]) <= int(py_tag[3:])
            except ValueError:
                return False
    return False


def _marcatore_vale(marker: str | None, piattaforma: str) -> bool:
    if not marker:
        return True
    try:
        from packaging.markers import Marker
    except ImportError:                    # senza packaging: si controlla comunque
        return True
    macchina = "AMD64" if piattaforma == "win_amd64" else "ARM64"
    ver = PYTHON.rsplit(".", 1)[0]
    return Marker(marker).evaluate({
        "sys_platform": "win32", "platform_system": "Windows", "os_name": "nt",
        "platform_machine": macchina, "python_version": ver, "python_full_version": PYTHON,
        "implementation_name": "cpython", "platform_python_implementation": "CPython",
        "extra": ""})


def requisiti(lock: Path, pacchetti=PACCHETTI, pacchetti_windows=PACCHETTI_WINDOWS,
              senza_dipendenze=SENZA_DIPENDENZE) -> tuple[str, str]:
    """(requisiti.txt, requisiti-senza-dipendenze.txt) con versioni e SHA-256 di uv.lock.
    Solo i wheel per Windows (x86-64 e ARM64) e quelli universali; ValueError se a un
    pacchetto manca il wheel per una piattaforma."""
    import tomllib
    dati = tomllib.loads(lock.read_text(encoding="utf-8"))
    per_nome = {}
    for p in dati.get("package", []):
        per_nome.setdefault(_norm(p["name"]), p)

    marcatori: dict[str, str | None] = {}

    def visita(nome: str, marker: str | None):
        n = _norm(nome)
        if n not in per_nome:
            raise ValueError(f"{nome} non è in uv.lock")
        if n in marcatori:
            nuovo = _o(marcatori[n], marker)
            if nuovo is not None and len(nuovo) > 300:
                nuovo = None                 # un ciclo di dipendenze: senza marcatore
            if nuovo == marcatori[n]:
                return
            marcatori[n] = nuovo
        else:
            marcatori[n] = marker
        for d in per_nome[n].get("dependencies", []):
            visita(d["name"], _e(marker, d.get("marker")))

    for nome in pacchetti:
        visita(nome, None)
    for nome in pacchetti_windows:
        visita(nome, "sys_platform == 'win32'")

    def righe(nomi_marcatori) -> str:
        out, mancano = [], []
        for n, marker in sorted(nomi_marcatori.items()):
            p = per_nome[n]
            wheels = [w for w in p.get("wheels", [])
                      if any(_wheel_va(w["url"].rsplit("/", 1)[1], pl) for pl in PIATTAFORME)]
            for pl in PIATTAFORME:
                if _marcatore_vale(marker, pl) and not any(
                        _wheel_va(w["url"].rsplit("/", 1)[1], pl) for w in wheels):
                    mancano.append(f"{p['name']} {p['version']} ({pl})")
            if not wheels:
                continue
            riga = f"{p['name']}=={p['version']}"
            if marker:
                riga += f" ; {marker}"
            hash_ = sorted({w["hash"] for w in wheels})
            out.append(riga + " \\\n" + " \\\n".join(f"    --hash={h}" for h in hash_))
        if mancano:
            raise ValueError("mancano i wheel per " + ", ".join(mancano))
        return "\n".join(out) + "\n"

    intesta = ("# Generato dal server di Calliope da uv.lock (calliope/satellite/pacchetto.py):"
               "\n# non modificare. Python " + PYTHON + ", solo wheel.\n")
    nodeps = {_norm(n): None for n in senza_dipendenze}
    for n in nodeps:
        if n not in per_nome:
            raise ValueError(f"{n} non è in uv.lock")
    return intesta + righe(marcatori), intesta + righe(nodeps)


# ───────────────────────────── zip ─────────────────────────────
def _zip(file: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dati in sorted(file):
            info = zipfile.ZipInfo(nome, date_time=_DATA_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3                     # uguale su Windows e su Linux
            z.writestr(info, dati, compresslevel=9)
    return buf.getvalue()


def impronta_contenuto(file: list[tuple[str, bytes]]) -> str:
    h = hashlib.sha256()
    for nome, dati in sorted(file):
        h.update(nome.encode("utf-8") + b"\0" + hashlib.sha256(dati).digest())
    return h.hexdigest()


class Pacchetto:
    def __init__(self, dati: bytes, versione: str, file: list[str]):
        self.dati = dati
        self.sha256 = hashlib.sha256(dati).hexdigest()
        self.versione = versione
        self.byte = len(dati)
        self.file = file

    def annuncio(self) -> dict:
        """Quello che il server dice ai satelliti nel benvenuto."""
        return {"versione": self.versione, "sha256": self.sha256, "byte": self.byte,
                "python": PYTHON, "percorso": "/installa/pacchetto.zip"}


def costruisci(radice: Path, cartella_wake: Path, lock: Path | None = None,
               wake_extra: tuple[str, ...] = ()) -> Pacchetto:
    """Il pacchetto dalla versione di Calliope in `radice` (la cartella che contiene
    calliope/ e uv.lock) e dai modelli della wake word in `cartella_wake`. `wake_extra`:
    altri classificatori da mettere accanto (la wake word del server se non è «Calliope»,
    04/10: il satellite la usa se c'è), solo se il file esiste."""
    radice = Path(radice)
    lock = Path(lock) if lock else radice / "uv.lock"
    if not lock.is_file():
        raise PacchettoNonDisponibile(f"manca uv.lock accanto al codice ({radice})")
    mancano = [n for n in MODELLI_WAKE if not (Path(cartella_wake) / n).is_file()]
    if mancano:
        raise PacchettoNonDisponibile(f"mancano i modelli della wake word in {cartella_wake}: "
                                      + ", ".join(mancano))
    try:
        req, nodeps = requisiti(lock)
    except ValueError as e:
        raise PacchettoNonDisponibile(str(e)) from e
    nomi = moduli(radice) + [f for f in FILE_IN_PIU if (radice / f).is_file()]
    file = [(n, (radice / n).read_bytes()) for n in dict.fromkeys(nomi)]
    extra = [n for n in wake_extra if n and n not in MODELLI_WAKE and n.endswith(".onnx")
             and (Path(cartella_wake) / n).is_file()]
    file += [(f"wakeword/modelli/{n}", (Path(cartella_wake) / n).read_bytes())
             for n in list(MODELLI_WAKE) + extra]
    file += [("requisiti.txt", req.encode("utf-8")),
             ("requisiti-senza-dipendenze.txt", nodeps.encode("utf-8"))]
    versione = impronta_contenuto(file)[:12]
    info = {"versione": versione, "python": PYTHON, "uv": UV_VERSIONE,
            "requisiti": "requisiti.txt", "senza_dipendenze": "requisiti-senza-dipendenze.txt",
            "comando": ["-m", "calliope.satellite"]}
    file.append(("VERSIONE.json", (json.dumps(info, indent=2) + "\n").encode("utf-8")))
    return Pacchetto(_zip(file), versione, sorted(n for n, _ in file))


def radice_codice() -> Path:
    """La cartella che contiene il package calliope in uso (sulla DGX la cartella della
    versione, con uv.lock accanto; sul portatile il repository)."""
    return Path(__file__).resolve().parent.parent.parent


class Distributore:
    """Il pacchetto della versione in uso, costruito una volta (in un thread all'avvio del
    server o alla prima richiesta) e tenuto in memoria (~1 MB)."""

    def __init__(self, cfg, radice: Path | None = None, log=print):
        self.cfg = cfg
        self.radice = Path(radice) if radice else radice_codice()
        self.log = log
        self._lock = threading.Lock()
        self._pacchetto: Pacchetto | None = None
        self.motivo = ""

    def cartella_wake(self) -> Path:
        wake = Path(str(getattr(self.cfg, "wake_model", "") or "wakeword/modelli/calliope.onnx"))
        return wake.parent

    def prepara_in_background(self):
        threading.Thread(target=self.pacchetto, name="pacchetto-satellite", daemon=True).start()

    def pacchetto(self) -> Pacchetto | None:
        with self._lock:
            if self._pacchetto is None and not self.motivo:
                try:
                    # Anche i classificatori delle modalità («computer.onnx»): così un
                    # satellite installato ha già la parola di una modalità scelta poi a voce
                    from ..config import MODALITA
                    wake = [Path(str(getattr(self.cfg, "wake_model", "") or "")).name]
                    wake += [Path(str(p.get("wake_model") or "")).name
                             for p in MODALITA.values()]
                    self._pacchetto = costruisci(self.radice, self.cartella_wake(),
                                                 wake_extra=tuple(dict.fromkeys(wake)))
                except PacchettoNonDisponibile as e:
                    self.motivo = str(e)
                    self.log(f"   [SATELLITE] installazione e aggiornamenti dei satelliti spenti: "
                             f"{e}")
                except (OSError, SyntaxError, UnicodeDecodeError) as e:
                    self.motivo = f"{type(e).__name__}: {e}"
                    self.log(f"   [SATELLITE] il pacchetto dei satelliti non si costruisce: "
                             f"{self.motivo}")
            return self._pacchetto

    def pronto(self) -> Pacchetto | None:
        """Il pacchetto se è già costruito, senza aspettare (il benvenuto non aspetta)."""
        return self._pacchetto

    def manifesto(self, satellite_server: str, impronta: str) -> dict | None:
        """Per installa.ps1: cosa scaricare e con quale SHA-256, e dove collegarsi dopo."""
        p = self.pacchetto()
        if p is None:
            return None
        return {"pacchetto": p.annuncio(), "python": PYTHON,
                "uv": {"versione": UV_VERSIONE, **UV},
                "satellite_server": satellite_server, "satellite_impronta": impronta}
