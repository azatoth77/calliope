"""
Il motore del podcast e il fermo di vLLM (04/11/2026, issue #387, decisione 0035 punto 58). Niente MOSS, torch o
modelli in questo processo: solo `docker` e file.

**`MotoreMoss`** ha la stessa interfaccia della voce del riassunto (`ascolta.VocePiper`): `in_wav(testo) → wav` e
`rate`; un altro motore si mette al suo posto cambiando solo chi lo crea (principio 2). Gira in un container con
`--network none`, `--cap-drop ALL`, radice in sola lettura, pesi e codice montati in sola lettura e una sola
cartella scrivibile, che dopo la sessione si svuota: MOSS chiede `trust_remote_code`, e quel codice non deve poter
uscire né cambiare i suoi file. **Tutto ciò che viene eseguito è fissato per hash** (`setup/linux/motore/moss.sha256`,
`controlla_file`): i pesi e il loro codice, il `generation_utils.py`, l'ambiente intero (`venv/moss`, un'impronta sola
dell'albero, collegamenti compresi), l'immagine; **un file in più è un file che non torna**: un `numpy.py` accanto a
`generation_utils.py` verrebbe importato al posto di quello vero. A ogni sessione tutto meno l'hash dei pesi, che non si
eseguono e si guardano per dimensione (l'hash intero lo fa `calliope motore moss verifica`). I `.pyc` non si leggono dalla
cartella: `PYTHONPYCACHEPREFIX` nel container. Non si scarica niente a ogni avvio.

Si lancia anche da solo (`python3 podcast_motore.py verifica|elenco|pota DIR`): è ciò che usa `moss.sh`, col python3 di
sistema e senza il resto di Calliope.

**`ControlloVllm`** ferma vLLM con `docker stop` e lo riparte con `docker start`, cioè lo stesso container: argomenti,
ambiente, porte, rete, politica di riavvio e la modalità sviluppo (`VLLM_SERVER_DEV_MODE`, la pausa dell'arbitro)
non possono cambiare, a differenza di `calliope motore vllm agente ferma`, che toglie il container, e `avvia`, che
senza `PAUSA=1` la perderebbe (trappola del banco del 04/11). Il confronto prima e dopo c'è lo stesso.

**`Ripresa`** è la cintura: prima di fermare scrive un segno su disco, e lo toglie solo con vLLM di nuovo in piedi e
non in pausa. All'avvio di Calliope (`all_avvio`), anche con il podcast spento, un segno rimasto vuol dire una
sessione caduta a metà: si toglie il container di MOSS e si riparte vLLM. Un agente chiesto intanto aspetta e lo
dice (`in_ripresa`, `attendi`, usati da `agenti/servizio.py`).

Solo libreria standard.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

CONTAINER_MOSS = "calliope-moss"
CONTAINER_VLLM = "calliope-vllm"
SEGNO = "podcast_vllm_fermo.json"

# Le versioni fissate (TERZE-PARTI.md; l'elenco degli hash è in setup/linux/motore/moss.sha256)
IMMAGINE = "vllm/vllm-openai:v0.29.0"
VERSIONE_MOTORE = "moss-ttsd-46973e4-c7cd852-3cd226b"
# La frase dei riferimenti: quella del banco del 04/11. I riferimenti sono voci di Piper, mai persone reali e mai i
# campioni `reference_02_s*.wav` del progetto
TESTO_RIFERIMENTO = ("Buongiorno a tutti. Oggi il cielo è sereno e il vento soffia leggero dal mare. Nel pomeriggio "
                     "andremo in biblioteca a cercare qualche libro interessante, poi torneremo a casa per cena.")

CARICA_MAX_S = 420.0        # il banco: 132 s
GENERA_FATTORE_MAX = 4.0    # il banco: 1,25 sul tempo reale; oltre è un guasto
GENERA_MIN_S = 240.0
MEMORIA_CONTAINER = "44g"   # il banco: RSS 5,9 GB, GPU 24,7 GB
RIPARTE_MAX_S = 900.0       # vLLM: il banco 4 min 20 s, lo script aspetta 15 minuti
FERMA_S = 30                # `docker stop -t`


class Ceduto(Exception):
    """La sessione deve finire adesso: la voce o un lavoro vengono prima. `str(e)` è il motivo, mai testo."""


class Guasto(Exception):
    """Il motore non funziona: nome di un motivo, mai testo del copione."""


def _esegui(argv: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


ALBERI = ("venv/moss",)      # un'impronta sola: migliaia di file che si controllano insieme


# ─────────────────────────── vLLM ───────────────────────────
def impostazioni_di(inspect: dict) -> dict:
    """Ciò che deve restare uguale dopo il riavvio, da `docker inspect`: mai l'ora, lo stato o l'indirizzo IP."""
    cfg, host = inspect.get("Config") or {}, inspect.get("HostConfig") or {}
    return {"immagine": cfg.get("Image"), "comando": cfg.get("Cmd"), "entrypoint": cfg.get("Entrypoint"),
            "ambiente": sorted(cfg.get("Env") or ()), "utente": cfg.get("User"),
            "porte": host.get("PortBindings"), "rete": host.get("NetworkMode"),
            "reti": sorted(((inspect.get("NetworkSettings") or {}).get("Networks") or {}).keys()),
            "riavvio": (host.get("RestartPolicy") or {}).get("Name"), "montati": sorted(host.get("Binds") or ()),
            "ipc": host.get("IpcMode"), "gpu": host.get("DeviceRequests") or host.get("Runtime")}


def differenze(prima: dict | None, dopo: dict | None) -> list[str]:
    """I nomi delle impostazioni cambiate (mai i valori: nell'ambiente ci può essere una chiave)."""
    if not prima or not dopo:
        return ["container"]
    return sorted(k for k in set(prima) | set(dopo) if prima.get(k) != dopo.get(k))


class ControlloVllm:
    """Il container dell'agente. `esegui` e `chiedi` si cambiano nelle prove."""

    def __init__(self, url: str, container: str = CONTAINER_VLLM, esegui=_esegui, chiedi=None, dorme=time.sleep,
                 orologio=time.monotonic):
        self.url = str(url or "").rstrip("/")
        self.container = container
        self.esegui = esegui
        self.chiedi = chiedi or self._chiedi_http
        self.dorme = dorme
        self.orologio = orologio
        self.sparito = False       # il container non c'è più: inutile aspettarlo

    def _chiedi_http(self, percorso: str) -> dict | None:
        """GET: il JSON, {} se la risposta non è JSON, None se non risponde."""
        try:
            with urllib.request.urlopen(self.url + percorso, timeout=5) as r:  # noqa: S310 — è il nostro vLLM
                try:
                    return json.loads(r.read() or b"{}")
                except ValueError:
                    return {}
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def _inspect(self) -> dict | None:
        r = self.esegui(["docker", "inspect", self.container])
        if r.returncode != 0:
            return None
        try:
            return (json.loads(r.stdout) or [None])[0]
        except ValueError:
            return None

    def acceso(self) -> bool:
        i = self._inspect()
        return bool(i and (i.get("State") or {}).get("Running"))

    def impostazioni(self) -> dict | None:
        i = self._inspect()
        return impostazioni_di(i) if i else None

    def ferma(self) -> None:
        r = self.esegui(["docker", "stop", "-t", str(FERMA_S), self.container], timeout=FERMA_S + 60)
        if r.returncode != 0:
            raise Guasto("vllm_non_si_ferma")

    def in_piedi(self) -> bool:
        return self.chiedi("/v1/models") is not None

    def non_in_pausa(self) -> bool:
        """Senza `/is_paused` (modalità sviluppo spenta) il dato non c'è: lo dice il confronto. Con la risposta, deve
        dire falso."""
        p = self.chiedi("/is_paused")
        return p is None or not p.get("is_paused")

    def riavvia(self, tetto_s: float = RIPARTE_MAX_S) -> bool:
        """`docker start` (se è già acceso non fa niente) e l'attesa che risponda, entro `tetto_s`. Un container che non
        c'è più non si aspetta: `sparito`."""
        self.sparito = False
        try:
            r = self.esegui(["docker", "start", self.container], timeout=60)
            if r.returncode != 0 and self._inspect() is None:
                self.sparito = True
                return False
        except (OSError, subprocess.SubprocessError):
            return False
        fine = self.orologio() + tetto_s
        while self.orologio() < fine:
            if self.in_piedi():
                return True
            self.dorme(5.0)
        return False


class Ripresa:
    """Il segno su disco e l'attesa di chi ha bisogno di vLLM. Una per processo."""

    def __init__(self, cartella: Path | None, vllm: ControlloVllm | None, togli_motore=None, log=print,
                 dorme=time.sleep, orologio=time.monotonic, tetto_s: float = RIPARTE_MAX_S, pulisci=None):
        self.segno = Path(cartella) / SEGNO if cartella else None
        self.vllm = vllm
        self.togli_motore = togli_motore or togli_container
        self.pulisci = pulisci or (lambda: None)    # la cartella del container: copione e audio di una caduta
        self.log = log
        self.dorme = dorme
        self.orologio = orologio
        self.tetto_s = tetto_s
        self._fermo = threading.Event()    # vLLM è fermo per noi, o sta ripartendo
        self.ultimo_fermo_s = None
        self.ultime_differenze: list[str] = []
        self.ripartito = None
        self._lock = threading.Lock()
        self._t0 = None
        self._prima = None

    # ── per chi aspetta ──
    def in_ripresa(self) -> bool:
        return self._fermo.is_set() or (self.segno is not None and self.segno.exists())

    def attendi(self, tetto_s: float | None = None, annullato=None) -> bool:
        """Aspetta che vLLM sia di nuovo in piedi. True se è in piedi; False oltre il tetto o se chi aspetta rinuncia."""
        fine = self.orologio() + (self.tetto_s if tetto_s is None else tetto_s)
        while self.in_ripresa():
            if self.orologio() >= fine or (annullato is not None and annullato()):
                return False
            self.dorme(1.0)
        return True

    # ── la sessione ──
    def prenota(self, info: dict) -> None:
        """Da qui chi ha bisogno di vLLM aspetta: il segno su disco e `in_ripresa`, prima di fermare e prima dell'ultimo
        controllo di chi ferma. Le impostazioni di adesso, per il confronto."""
        prima = self.vllm.impostazioni()
        self._prima = prima
        self._fermo.set()
        self._scrivi({**info, "quando": time.time(), "prima": prima})

    def disdici(self) -> None:
        """Non si ferma più: niente è stato toccato."""
        self._togli_segno()
        self._fermo.clear()
        self._prima = None

    def ferma_ora(self) -> None:
        self._t0 = self.orologio()
        self.vllm.ferma()

    def ferma(self, info: dict) -> dict | None:
        """Scrive il segno e ferma vLLM. Il segno prima: se si cade fra i due, all'avvio `docker start` non fa
        niente."""
        self.prenota(info)
        self.ferma_ora()
        return self._prima

    def riparti(self) -> bool:
        """Sempre, con o senza errori: MOSS via, vLLM di nuovo in piedi, non in pausa, con le stesse impostazioni. Il segno va
        via solo se è vero; altrimenti il prossimo `controlla` riprova, e all'avvio anche. **MOSS ancora vivo: vLLM non
        parte**, non ci starebbero insieme (24,7 GB e 48). Se il container di vLLM non c'è più non si aspetta niente: si
        dice, e chi vuole un lavoro trova il guasto vero invece di aspettare 15 minuti."""
        with self._lock:
            self.ripartito = False
            try:
                self.togli_motore()
            except Exception as e:  # noqa: BLE001
                self.log(f"   [STUDIO] MOSS ancora vivo ({e}): vLLM non riparte finché non è tolto")
                return False
            prima = self._prima
            if prima is None:
                prima = self._leggi().get("prima")
            ok = self.vllm.riavvia(self.tetto_s)
            if self.vllm.sparito:
                self.ultime_differenze = ["container"]
                self.log("   [STUDIO] il container di vLLM non c'è più: `PAUSA=1 calliope motore vllm agente avvia`")
                self._togli_segno()
                self._fermo.clear()
                self._t0, self._prima = None, None
                return True
            pausa_ok = ok and self.vllm.non_in_pausa()
            self.ultime_differenze = differenze(prima, self.vllm.impostazioni()) if ok else []
            if self._t0 is not None:
                self.ultimo_fermo_s = round(self.orologio() - self._t0, 1)
            self.ripartito = bool(ok and pausa_ok)
            if self.ultime_differenze:
                self.log(f"   [STUDIO] vLLM è ripartito con impostazioni diverse: {', '.join(self.ultime_differenze)}")
            if ok and not pausa_ok:
                self.log("   [STUDIO] vLLM è ripartito ma è in pausa: `calliope motore vllm agente riprendi`")
            if not ok:
                self.log(f"   [STUDIO] vLLM non è ripartito in {self.tetto_s:.0f} s: riprovo")
                return False
            if pausa_ok:
                self._togli_segno()
                self._fermo.clear()
                self._t0, self._prima = None, None
            return pausa_ok

    def controlla(self) -> bool:
        """Un segno rimasto (una sessione caduta, un riavvio non riuscito): via MOSS, e vLLM riparte. True se non
        c'era niente da fare o è tornato tutto a posto."""
        if self.segno is None or not self.segno.exists():
            return True
        self._fermo.set()
        self.log("   [STUDIO] podcast caduto a metà: riparto vLLM")
        try:
            self.pulisci()
        except Exception:  # noqa: BLE001
            pass
        return self.riparti()

    def all_avvio(self, attesa_s: float = 60.0) -> threading.Thread | None:
        """All'avvio di Calliope, in secondo piano, fino a che non è tornato: l'avvio non aspetta quattro minuti."""
        if self.segno is None or not self.segno.exists():
            return None

        def gira():
            while not self.controlla():
                self.dorme(attesa_s)
        t = threading.Thread(target=gira, daemon=True, name="podcast-ripresa")
        t.start()
        return t

    def alla_chiusura(self) -> None:
        """Calliope si chiude durante una sessione: MOSS via e `docker start` senza aspettare. Il segno resta, e al
        prossimo avvio si controlla che sia tornato."""
        if self.segno is None or not self.segno.exists():
            return
        try:
            self.togli_motore()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.vllm.esegui(["docker", "start", self.vllm.container], timeout=30)
        except Exception:  # noqa: BLE001
            pass

    def _scrivi(self, d: dict) -> None:
        if self.segno is None:
            return
        self.segno.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.segno.with_name(self.segno.name + ".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, self.segno)

    def _leggi(self) -> dict:
        try:
            return json.loads(self.segno.read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            return {}

    def _togli_segno(self) -> None:
        try:
            self.segno.unlink()
        except (OSError, AttributeError):
            pass


# ─────────────────────────── MOSS ───────────────────────────
def togli_container(esegui=_esegui, nome: str = CONTAINER_MOSS) -> None:
    """Solo il nostro container, per il suo nome esatto. Se resta, `Guasto`: ignorarlo lascerebbe MOSS accanto a vLLM."""
    esegui(["docker", "rm", "-f", nome], timeout=60)
    if esegui(["docker", "inspect", "-f", "{{.State.Running}}", nome]).returncode == 0:
        raise Guasto("moss_non_tolto")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                return h.hexdigest()
            h.update(b)


def _file_sotto(radice: Path):
    """Tutti i file e i collegamenti simbolici sotto `radice`, in ordine, senza seguire i collegamenti. (percorso, rel)."""
    for d, nomi_d, nomi_f in os.walk(radice, followlinks=False):
        nomi_d.sort()
        for n in sorted(nomi_f + [x for x in nomi_d if os.path.islink(os.path.join(d, x))]):
            p = Path(d) / n
            yield p, p.relative_to(radice).as_posix()


def impronta_albero(radice: Path, rel: str) -> tuple[str, int]:
    """(un'impronta, quanti file) di un albero: percorsi, contenuti e destinazioni dei collegamenti. L'ora no."""
    h = hashlib.sha256()
    n = 0
    base = Path(radice) / rel
    for p, r in sorted(_file_sotto(base), key=lambda x: x[1]):
        v = ("L:" + os.readlink(p)) if p.is_symlink() else _sha(p)
        h.update(f"{r}\0{v}\n".encode())
        n += 1
    return h.hexdigest(), n


def leggi_elenco(elenco: Path) -> dict:
    """{immagine, file: {rel: (sha, byte)}, alberi: {rel: (impronta, n)}}."""
    out: dict = {"immagine": None, "file": {}, "alberi": {}}
    for riga in Path(elenco).read_text(encoding="utf-8").splitlines():
        if not riga.strip() or riga.startswith("#"):
            continue
        a, b, *resto = riga.split(None, 2)
        if a == "immagine":
            out["immagine"] = b
        elif a == "albero":
            n, rel = resto[0].split(None, 1)
            out["alberi"][rel] = (b, int(n))
        else:
            out["file"][resto[0]] = (a, int(b))
    return out


def controlla_file(radice: Path, elenco: Path, tutti: bool = False) -> list[str]:
    """Ciò che non torna con l'elenco, i nomi soltanto: un file diverso, uno che manca, **uno in più**, un collegamento
    simbolico fuori dagli alberi. Con `tutti` anche l'hash dei pesi (minuti); di serie i pesi solo per dimensione, perché non
    si eseguono."""
    radice = Path(radice)
    e = leggi_elenco(elenco)
    male = []
    for rel, (atteso, dim) in e["file"].items():
        f = radice / rel
        try:
            if f.is_symlink() or f.stat().st_size != dim:
                male.append(rel)
            elif (tutti or not rel.endswith(".safetensors")) and _sha(f) != atteso:
                male.append(rel)
        except OSError:
            male.append(rel)
    for rel, (imp, n) in e["alberi"].items():
        if impronta_albero(radice, rel) != (imp, n):
            male.append(rel)
    if radice.is_dir():
        for p, r in _file_sotto(radice):
            if not any(r.startswith(a + "/") for a in e["alberi"]) and r not in e["file"]:
                male.append(f"in più: {r}")
    return male


def pota(radice: Path) -> None:
    """Ciò che non serve e non si esegue, su una copia appena fatta: le cache di `hf` e di Python, i testi, e di
    MOSS-TTSD solo `generation_utils.py` e la licenza (i campioni di voce del progetto non restano nemmeno sul disco). Una
    regola fissa, non l'elenco: un file estraneo resta, e la verifica lo rifiuta."""
    import shutil as _sh
    radice = Path(radice)
    for d, nomi_d, _f in os.walk(radice):
        for n in list(nomi_d):
            if n in ("__pycache__", ".cache", ".git"):
                _sh.rmtree(os.path.join(d, n), ignore_errors=True)
                nomi_d.remove(n)
    for d in ("pesi/moss-ttsd", "pesi/moss-tokenizer"):
        for n in ("README.md", ".gitattributes"):
            try:
                (radice / d / n).unlink()
            except OSError:
                pass
    src = radice / "src" / "MOSS-TTSD"
    if src.is_dir():
        for p in list(src.iterdir()):
            if p.name not in ("generation_utils.py", "LICENSE"):
                _sh.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()


def scrivi_elenco(radice: Path, elenco: Path, testa: str = "", immagine: str = "") -> int:
    radice = Path(radice)
    righe = [f"# {testa}".rstrip(), "# sha256, byte, percorso; «albero»: un'impronta sola; «immagine»: l'Id di Docker."]
    if immagine:
        righe.append(f"immagine {immagine}")
    for a in ALBERI:
        imp, n = impronta_albero(radice, a)
        righe.append(f"albero {imp} {n} {a}")
    file = [(p, r) for p, r in _file_sotto(radice) if not any(r.startswith(a + "/") for a in ALBERI)]
    for p, r in sorted(file, key=lambda x: x[1]):
        righe.append(f"{_sha(p)} {p.stat().st_size} {r}")
    Path(elenco).write_text("\n".join(righe) + "\n", encoding="utf-8")
    return len(file)


def elenco_hash() -> Path:
    return Path(__file__).resolve().parents[2] / "setup" / "linux" / "motore" / "moss.sha256"


def script_lavoro() -> Path:
    return Path(__file__).resolve().parents[2] / "setup" / "linux" / "motore" / "moss_lavoro.py"


def argomenti_docker(radice: Path, lavoro: Path, script: Path, uid: int, gid: int, nome: str = CONTAINER_MOSS,
                     immagine: str = IMMAGINE, ambiente=()) -> list[str]:
    """Il comando del container. Tutto quello che conta per la sicurezza sta qui, e lo guarda una prova."""
    return ["docker", "run", "-d", "--name", nome, *[x for k in ambiente for x in ("-e", k)],
            "--network", "none", "--gpus", "all",
            "--memory", MEMORIA_CONTAINER, "--memory-swap", MEMORIA_CONTAINER, "--pids-limit", "512",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only",
            "--tmpfs", "/tmp:rw,exec,size=2g,mode=1777", "--user", f"{uid}:{gid}",
            "-e", "PYTHONPYCACHEPREFIX=/tmp/pyc", "-e", "PYTHONNOUSERSITE=1", "-e", "HOME=/tmp", "-e", "HF_HOME=/tmp/hf", "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1",
            "-e", "NUMBA_CACHE_DIR=/tmp", "-e", "MPLCONFIGDIR=/tmp", "-e", "TMPDIR=/tmp",
            "-v", f"{radice}:/pv:ro", "-v", f"{lavoro}:/lavoro", "-v", f"{script}:/moss_lavoro.py:ro",
            "--workdir", "/tmp", "--entrypoint", "/pv/venv/moss/bin/python", immagine, "/moss_lavoro.py"]


class MotoreMoss:
    """`in_wav(testo) → wav` con MOSS-TTSD in un container: le richieste e le uscite sono file nella cartella di
    lavoro. `testo` ha già i `[S1]`/`[S2]`. `seme` cambia a ogni tentativo, `cede()` può interrompere l'attesa
    sollevando `Ceduto`. Dopo `ferma` non c'è più niente: il container è usa e getta."""

    versione = VERSIONE_MOTORE

    def __init__(self, radice, lavoro, rif_a, rif_b, esegui=_esegui, cede=None, dorme=time.sleep,
                 orologio=time.monotonic, nome: str = CONTAINER_MOSS):
        self.radice = Path(radice)
        self.lavoro = Path(lavoro)
        self.rif_a, self.rif_b = Path(rif_a), Path(rif_b)
        self.esegui = esegui
        self.cede = cede or (lambda: None)
        self.dorme = dorme
        self.orologio = orologio
        self.nome = nome
        self.seme = 42
        self.rate = 0
        self.carico_s = None
        self.ultima = {}
        self.ambiente = ()          # il banco: MOSS_PROVA, sul materiale di fantasia
        self._n = 0

    def pronto_su_disco(self) -> list[str]:
        """Ciò che non torna con l'elenco fissato (vuoto: si può partire), immagine compresa. Senza elenco, tutto."""
        e = elenco_hash()
        if not e.is_file():
            return ["elenco"]
        male = controlla_file(self.radice, e)
        attesa = leggi_elenco(e)["immagine"]
        r = self.esegui(["docker", "image", "inspect", "--format", "{{.Id}}", IMMAGINE])
        if attesa and (r.returncode != 0 or r.stdout.strip() != attesa):
            male.append("immagine")
        return male

    def _vivo(self) -> bool:
        r = self.esegui(["docker", "inspect", "-f", "{{.State.Running}}", self.nome])
        return r.returncode == 0 and "true" in r.stdout

    def _interrompi_se(self) -> None:
        m = self.cede()
        if m:
            raise Ceduto(m)

    def avvia(self) -> None:
        male = self.pronto_su_disco()
        if male:
            raise Guasto("hash_diverso")
        togli_container(self.esegui, self.nome)
        shutil.rmtree(self.lavoro, ignore_errors=True)
        (self.lavoro / "richieste").mkdir(parents=True)
        (self.lavoro / "uscite").mkdir()
        shutil.copyfile(self.rif_a, self.lavoro / "rif-a.wav")
        shutil.copyfile(self.rif_b, self.lavoro / "rif-b.wav")
        (self.lavoro / "riferimenti.json").write_text(json.dumps({"testo": TESTO_RIFERIMENTO}), encoding="utf-8")
        for d in (self.lavoro, self.lavoro / "richieste", self.lavoro / "uscite"):
            os.chmod(d, 0o700)
        argv = argomenti_docker(self.radice, self.lavoro, script_lavoro(), os.getuid() if hasattr(os, "getuid") else 0,
                                os.getgid() if hasattr(os, "getgid") else 0, self.nome, ambiente=self.ambiente)
        r = self.esegui(argv, timeout=120)
        if r.returncode != 0:
            raise Guasto("container_non_parte")
        t0 = self.orologio()
        pronto = self.lavoro / "pronto.json"
        while not pronto.exists():
            self._interrompi_se()
            if self.orologio() - t0 > CARICA_MAX_S:
                raise Guasto("caricamento_troppo_lungo")
            if not self._vivo():
                raise Guasto("container_caduto")
            self.dorme(1.0)
        d = json.loads(pronto.read_text(encoding="utf-8"))
        self.rate, self.carico_s = int(d["rate"]), d.get("carico_s")

    def in_wav(self, testo: str) -> bytes:
        self._n += 1
        rid = f"{self._n:04d}"
        tmp = self.lavoro / "richieste" / f"{rid}.tmp"
        tmp.write_text(json.dumps({"id": rid, "testo": testo, "seme": int(self.seme)}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.lavoro / "richieste" / f"{rid}.json")
        wav, misura = self.lavoro / "uscite" / f"{rid}.wav", self.lavoro / "uscite" / f"{rid}.json"
        t0 = self.orologio()
        tetto = max(GENERA_MIN_S, len(testo) / 15.0 * GENERA_FATTORE_MAX)
        while not misura.exists():
            self._interrompi_se()
            if self.orologio() - t0 > tetto:
                raise Guasto("generazione_troppo_lunga")
            if not self._vivo():
                raise Guasto("container_caduto")
            self.dorme(0.5)
        self.ultima = json.loads(misura.read_text(encoding="utf-8"))
        misura.unlink()
        if self.ultima.get("errore"):
            raise Guasto("generazione_fallita")
        dati = wav.read_bytes()
        wav.unlink()
        with wave.open(_buffer(dati), "rb") as w:     # un file rotto non deve arrivare alla ritrascrizione
            w.getnframes()
        return dati

    def ferma(self) -> None:
        """Via il container subito (`rm -f`: la voce non aspetta), e via la cartella di lavoro col copione."""
        try:
            togli_container(self.esegui, self.nome)
        finally:
            shutil.rmtree(self.lavoro, ignore_errors=True)


def _buffer(dati: bytes):
    import io
    return io.BytesIO(dati)


def memoria_disponibile_mb() -> int | None:
    """MemAvailable (sulla DGX la memoria è unificata: comprende la GPU). None fuori da Linux."""
    try:
        for r in Path("/proc/meminfo").read_text().splitlines():
            if r.startswith("MemAvailable:"):
                return int(r.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


if __name__ == "__main__":
    import sys
    azione, cartella = sys.argv[1], Path(sys.argv[2]).expanduser()
    if azione == "verifica":
        no = controlla_file(cartella, elenco_hash(), tutti=True)
        for x in no:
            print("NON TORNA ", x)
        print("Non torna: il podcast non parte." if no else "Tutto come in moss.sha256.")
        sys.exit(1 if no else 0)
    if azione == "pota":
        pota(cartella)
    elif azione == "elenco":
        print(scrivi_elenco(cartella, elenco_hash(), sys.argv[3] if len(sys.argv) > 3 else "", sys.argv[4] if len(sys.argv) > 4 else ""),
              "file e", len(ALBERI), "albero")
    else:
        sys.exit(f"azione sconosciuta: {azione}")
