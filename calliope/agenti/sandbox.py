"""
La sandbox del codice: una cartella per lavoro e quattro operazioni (02/10/2026).

Gli strumenti dell'agente di codice sono solo questi: elencare, leggere e scrivere file di
testo **dentro la cartella del lavoro**, eseguire un file Python della cartella, eseguire i
test. Nessun comando di shell, nessun programma scelto dal modello, niente pip: l'unico
eseguibile è l'interprete di Python, lanciato da qui con `_avvio.py`.

Livelli di protezione, dal più forte:
1. **Percorsi** controllati qui prima di toccare il disco: solo relativi, niente «..»,
   lettere di unità, «:» (flussi alternativi NTFS), nomi riservati di Windows,
   collegamenti simbolici o junction; solo estensioni di testo (.py, .txt, .csv, .json,
   .html, .ps1…, mai .exe, .bat, .cmd, .dll, .pyd); tetti a dimensione e numero dei file.
2. **Job object** di Windows (winjob.py): il processo Python non può crearne altri
   (ActiveProcessLimit = 1), ha un tetto di memoria (`agenti_memoria_mb`), niente appunti,
   finestre di altri, desktop; muore se Calliope muore; tempo massimo (`agenti_esecuzione_s`)
   e uccisione dell'intero job. Priorità bassa: la voce non perde CPU.
3. **Interprete isolato** (`python -I -B`, l'interprete di base e non il lanciatore del venv,
   che creerebbe un secondo processo): niente PYTHON* dall'ambiente, niente cartella utente;
   ambiente ripulito (PATH con la sola cartella di Python, TEMP e HOME dentro la cartella,
   niente proxy, nessuna variabile di Calliope come CALLIOPE_HA_TOKEN).
4. **Audit hook** (`_avvio.py`): rete, processi, ctypes, winreg, sottointerpreti, lettura e
   scrittura fuori dalla cartella → PermissionError.

**Due motori** (`agenti_sandbox_motore`, 03/10/2026; misure in
docs/ricerche/2026-10-03-sandbox.md):
- **docker** (Linux, la DGX): un container usa-e-getta per ogni esecuzione, dall'immagine
  `calliope-sandbox:<hash del Dockerfile>` (setup/linux/sandbox/Dockerfile, costruita da
  `calliope motore sandbox costruisci`). `--network none` (solo loopback), `--read-only` con
  la sola cartella del lavoro montata in scrittura e `/tmp` in memoria (16 MB, noexec), utente
  non root (lo stesso uid di Calliope, così i file restano suoi), `--cap-drop ALL`,
  `no-new-privileges`, seccomp e AppArmor predefiniti di Docker, memoria (`--memory` e
  `--ulimit data`: MemoryError invece di un'uccisione), `--pids-limit`, CPU, e `timeout -s
  KILL` dentro il container (se Calliope muore il container si ferma da solo). Niente
  variabili d'ambiente dell'host. ~0,19 s in più per esecuzione. L'audit hook resta, come
  seconda linea, dentro il container;
- **processo**: il motore di prima (job object su Windows; su Linux `resource`, nice 10,
  PR_SET_PDEATHSIG e un gruppo di processi da uccidere a fine tempo; audit hook).
  Dal 03/10 vale **solo** con `agenti_sandbox_motore: processo` scritto a mano: con `auto`,
  dove Docker non c'è (Windows, Docker assente, immagine non costruita), il codice
  dell'agente non si esegue e il registro delle capacità dice il passo per avere il
  container. L'analisi di sicurezza del 03/10 ha mostrato che lxml (sempre presente, per
  python-docx) legge file e apre connessioni in C, senza passare dall'audit hook.
  Con `docker` chiesto esplicitamente e non pronto il codice non si esegue.
bubblewrap e `unshare -r` non sono un'alternativa sulla DGX: Ubuntu 24.04 limita con
AppArmor le user namespace non privilegiate (`apparmor_restrict_unprivileged_userns=1`).

**Cosa resta un rischio** (scritto anche in CLAUDE.md):
- con il motore «processo» (Windows): niente isolamento di rete per processo senza
  privilegi di amministratore; la rete è bloccata solo dall'audit hook, che la PEP 578 non
  considera un confine di sicurezza (un'estensione nativa già installata, o un difetto
  dell'interprete, potrebbero aggirarlo), e il processo gira con l'utente di Calliope;
- con il motore «docker»: il confine è il kernel condiviso (namespace, cgroup, seccomp),
  non una macchina virtuale; il container ha l'uid di Calliope, quindi un'evasione dal
  container avrebbe i suoi permessi; Docker con il gruppo `docker` vuol dire che Calliope
  stessa può fare root sull'host (vale già oggi per l'utente: il codice dell'agente non
  vede il socket di Docker);
- il codice prodotto **non si esegue mai fuori dalla sandbox**: resta nei file di
  risultato, e chi lo usa lo legge prima.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import site
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import winjob

ESTENSIONI = {".py", ".txt", ".md", ".json", ".csv", ".tsv", ".html", ".htm", ".css", ".js",
              ".ps1", ".psm1", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".xml", ".sql", ".svg",
              ".log", ".cs"}
# File di dati (03/10): Word, Excel e PDF della persona messi nella cartella come input. Il
# codice dell'agente li legge e li scrive con openpyxl e python-docx; gli strumenti di testo
# (leggi_file, scrivi_file) no
ESTENSIONI_DATI = {".docx", ".xlsx", ".pdf"}
_RISERVATI = re.compile(r"^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³]|conin\$|conout\$)(\..*)?$",
                        re.I)
_PARTE = re.compile(r"^[\w\-. ()+,=@\[\]]+$")
_AVVIO = Path(__file__).with_name("_avvio.py")
# Compilazione ed esecuzione del C# nel suo container (04/10, linguaggi.py)
_ESEGUI_CS = Path(__file__).with_name("esegui_cs.sh")
_DOCKERFILE = Path(__file__).resolve().parents[2] / "setup" / "linux" / "sandbox" / "Dockerfile"
MOTORI = ("auto", "docker", "processo")
# Dove stanno, dentro il container, la cartella del lavoro e lo script di avvio
_LAVORO_C = "/lavoro"
_AVVIO_C = "/opt/calliope/_avvio.py"
_ESEGUI_CS_C = "/opt/calliope/esegui_cs.sh"
# I test JavaScript dei giochi (05/10): node:test nel container di Node (Dockerfile.node)
_TEST_JS = Path(__file__).with_name("test_js.mjs")
_TEST_JS_C = "/opt/calliope/test_js.mjs"
# La prova di fumo della scheda (05/10): DOM finto e tocchi a caso, importata da test_js.mjs
_FUMO_JS = Path(__file__).with_name("fumo_js.mjs")
_FUMO_JS_C = "/opt/calliope/fumo_js.mjs"
_DOCKERFILE_NODE = _DOCKERFILE.with_name("Dockerfile.node")


def immagine_node() -> str | None:
    """«calliope-sandbox-node:<prime 12 cifre dello SHA-256 di Dockerfile.node>»."""
    img = immagine_predefinita(_DOCKERFILE_NODE)
    return img and img.replace("calliope-sandbox:", "calliope-sandbox-node:", 1)


def file_test_js(nomi) -> list[str]:
    """I file di test JavaScript (`*.test.js`) tra i percorsi dati."""
    return [n for n in nomi if n.endswith(".test.js")]


class ErroreSandbox(Exception):
    """Operazione rifiutata: il messaggio va all'agente così com'è."""


def _interprete() -> tuple[str, bool]:
    """(eseguibile, è l'interprete di base). Nel venv di Windows `python.exe` è un
    lanciatore che crea un secondo processo: con il limite di un processo non partirebbe."""
    base = getattr(sys, "_base_executable", None)
    if base and Path(base).is_file():
        return base, True
    return sys.executable, False


def _siti() -> list[str]:
    """Le cartelle dei pacchetti del venv (l'interprete di base non le vede da solo)."""
    out = []
    try:
        # Anche quelle aggiunte da un .pth (un venv che estende un altro venv, come quelli dei
        # worktree delle prove): sono comunque cartelle da cui il processo importa
        extra = [p for p in sys.path if Path(p).name.lower() == "site-packages"]
        for d in dict.fromkeys([*site.getsitepackages(), *extra]):
            if Path(d).is_dir() and not Path(d).resolve().is_relative_to(
                    Path(sys.base_prefix).resolve()):
                out.append(str(Path(d).resolve()))
    except Exception:  # noqa: BLE001
        pass
    return out


def immagine_predefinita(dockerfile: Path | None = None) -> str | None:
    """«calliope-sandbox:<prime 12 cifre dello SHA-256 del Dockerfile>»: lo stesso nome che
    usa setup/linux/motore/sandbox.sh. None se il Dockerfile non c'è."""
    try:
        h = hashlib.sha256(Path(dockerfile or _DOCKERFILE).read_bytes()).hexdigest()[:12]
    except OSError:
        return None
    return f"calliope-sandbox:{h}"


@dataclass
class Isolamento:
    """Il motore della sandbox scelto, con la frase per il registro delle capacità."""
    motore: str                          # "docker" | "processo"
    descrizione: str
    pronto: bool = True                  # False: docker chiesto e non pronto (niente esecuzione)
    passo: str = ""
    immagine: str | None = None
    docker: list = field(default_factory=list)

    def dettagli(self) -> dict:
        d = {"motore": self.motore, "descrizione": self.descrizione, "pronto": self.pronto}
        if self.immagine:
            d["immagine"] = self.immagine
        return d


def scegli_isolamento(richiesto: str = "auto", immagine: str | None = None,
                      docker=None, timeout: float = 5.0,
                      posix: bool | None = None) -> Isolamento:
    """Sceglie il motore. Chiama `docker image inspect` (qualche decina di ms; fino a
    `timeout` con il demone bloccato): mai dal thread della voce. `docker` è il comando
    (lista; nelle prove un docker finto, con `posix=True` anche su Windows)."""
    richiesto = (richiesto or "auto").strip().lower()
    if richiesto not in MOTORI:
        richiesto = "auto"
    processo = ("processo con job object e audit hook" if os.name == "nt"
                else "processo con limiti di risorse e audit hook")
    if richiesto == "processo":
        # Solo per scelta esplicita, con un avviso: l'audit hook non trattiene il codice
        # nativo (lxml legge file e apre connessioni in C: analisi del 03/10)
        return Isolamento("processo", processo + " (scelto in agenti_sandbox_motore: "
                          "NON isola davvero file e rete)")

    def ripiego(perche: str, passo: str) -> Isolamento:
        # Senza container il codice dell'agente non si esegue (03/10). Il motore «processo»
        # non è un confine: con lxml (dipendenza obbligatoria di python-docx) il codice
        # leggeva un file qualunque fuori dalla cartella e lo mandava in rete, perché
        # libxml2 fa I/O in C senza eventi di audit (analisi-sicurezza-agenti, difetto 1)
        return Isolamento("docker", f"nessun isolamento sicuro per il codice: {perche}", False,
                          passo, immagine)

    if not (posix if posix is not None else hasattr(os, "getuid")):
        return ripiego("su Windows niente container",
                       "Il codice degli agenti si esegue solo in un container, sul server "
                       "con Docker; chi accetta il rischio può scegliere il motore «processo» "
                       "nella configurazione.")
    immagine = immagine or immagine_predefinita()
    if not immagine:
        return ripiego("manca setup/linux/sandbox/Dockerfile", "Aggiorna Calliope.")
    cmd = list(docker) if docker else ([shutil.which("docker")] if shutil.which("docker")
                                       else [])
    if not cmd:
        return ripiego("Docker non c'è", "Per isolare il codice degli agenti in un container "
                       "installa Docker, poi: calliope motore sandbox costruisci.")
    try:
        r = subprocess.run([*cmd, "image", "inspect", "--format", "{{.Id}}", immagine],
                           capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return ripiego("Docker non risponde", "Controlla il servizio di Docker.")
    except OSError:
        return ripiego("Docker non si avvia", "Controlla l'installazione di Docker.")
    if r.returncode == 0:
        return Isolamento("docker", "container Docker usa-e-getta, senza rete e con il disco "
                          "in sola lettura", True, "", immagine, cmd)
    err = (r.stderr or "").lower()
    if "no such image" in err or "no such object" in err:
        return ripiego("manca l'immagine della sandbox",
                       "Per isolare il codice in un container: calliope motore sandbox "
                       "costruisci.")
    if "permission denied" in err:
        return ripiego("Docker non mi dà i permessi",
                       "Aggiungi l'utente di Calliope al gruppo docker (o usa Docker rootless).")
    return ripiego("Docker non risponde", "Controlla il servizio di Docker.")


def _figlio_docker():   # pragma: no cover — solo Linux
    winjob.muori_con_il_padre(9)


class Sandbox:
    def __init__(self, cartella, tempo_s: float = 30.0, memoria_mb: int = 1024,
                 max_file: int = 200_000, max_files: int = 100, max_totale: int = 5_000_000,
                 max_uscita: int = 20_000, isolamento: Isolamento | None = None,
                 cpu: float = 2.0, max_processi: int = 32, linguaggi: dict | None = None):
        self.isolamento = isolamento or Isolamento(
            "processo", "processo con job object e audit hook" if os.name == "nt"
            else "processo con limiti di risorse e audit hook")
        if not self.isolamento.pronto:
            raise ErroreSandbox(f"non posso eseguire codice: {self.isolamento.descrizione}. "
                                + self.isolamento.passo)
        self.root = Path(cartella).resolve()
        if self.isolamento.motore == "docker" and "," in str(self.root):
            raise ErroreSandbox("la cartella della sandbox non può contenere virgole")
        # Gli altri linguaggi (04/10, linguaggi.py): {nome: Isolamento} del loro container
        self.linguaggi = {k: v for k, v in (linguaggi or {}).items() if k != "python"}
        self.cpu = float(cpu)
        self.max_processi = int(max_processi)
        self._nome = None
        self.root.mkdir(parents=True, exist_ok=True)
        self.tmp = self.root / ".tmp"
        self.tmp.mkdir(exist_ok=True)
        self.tempo_s = float(tempo_s)
        self.memoria_mb = int(memoria_mb)
        self.max_file, self.max_files, self.max_totale = max_file, max_files, max_totale
        # File che l'agente legge ma non cambia (05/10): il contratto delle capacità e il runtime
        # delle estensioni. Non tornano nemmeno tra i risultati (copia_in)
        self.sola_lettura: set[str] = set()
        self.max_uscita = max_uscita
        self._job = None
        self._proc = None
        self._lock = threading.Lock()
        self.esecuzioni = 0

    # ── percorsi ──
    def percorso(self, rel, scrittura: bool = False, dati: bool = False) -> Path:
        if not isinstance(rel, str) or not rel.strip():
            raise ErroreSandbox("serve un percorso relativo, per esempio «script.py»")
        rel = rel.strip().replace("\\", "/")
        if len(rel) > 200:
            raise ErroreSandbox("percorso troppo lungo")
        if rel.startswith("/") or re.match(r"^[a-zA-Z]:", rel) or ":" in rel or "\x00" in rel:
            raise ErroreSandbox("solo percorsi relativi alla cartella del lavoro, senza «:»")
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        if not parts:
            raise ErroreSandbox("percorso vuoto")
        for p in parts:
            if p == ".." or p.startswith(".") or p.endswith((" ", ".")) or _RISERVATI.match(p) \
                    or not _PARTE.match(p) or p == "__pycache__":
                raise ErroreSandbox(f"nome non ammesso: «{p}»")
        if len(parts) > 4:
            raise ErroreSandbox("troppe cartelle annidate (al massimo 4 livelli)")
        if Path(parts[-1]).suffix.lower() in ESTENSIONI_DATI and not dati:
            raise ErroreSandbox("i file Word, Excel e PDF si leggono e si scrivono con un "
                                "programma Python (python-docx, openpyxl), non con questo "
                                "strumento")
        if Path(parts[-1]).suffix.lower() not in ESTENSIONI | ESTENSIONI_DATI:
            raise ErroreSandbox("estensione non ammessa: solo file di testo ("
                                + ", ".join(sorted(ESTENSIONI)) + ")")
        # «random.py», «ctypes.py», «socket.py» nascondono il modulo vero a chi lo importa
        # (solo i file Python e le cartelle: «Random.cs» non nasconde niente)
        top = (parts[0] if len(parts) > 1 else Path(parts[0]).stem).lower()
        if (len(parts) > 1 or Path(parts[0]).suffix.lower() == ".py") \
                and top in sys.stdlib_module_names or top in ("site", "sitecustomize", "usercustomize"):
            raise ErroreSandbox(f"«{top}» è il nome di un modulo di Python: scegli un altro nome")
        path = self.root.joinpath(*parts)
        # Nessun collegamento lungo la strada (symlink o junction verso fuori)
        cur = self.root
        for p in parts:
            cur = cur / p
            if cur.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(cur)):
                raise ErroreSandbox("i collegamenti non sono ammessi")
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ErroreSandbox("fuori dalla cartella del lavoro")
        return resolved

    def _files(self) -> list[Path]:
        out = []
        for base, dirs, names in os.walk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for n in names:
                p = Path(base) / n
                if not p.is_symlink() and p.suffix.lower() in ESTENSIONI | ESTENSIONI_DATI:
                    out.append(p)
        return sorted(out)

    def elenca(self) -> list[dict]:
        return [{"percorso": p.relative_to(self.root).as_posix(), "byte": p.stat().st_size}
                for p in self._files()]

    def leggi(self, rel, max_caratteri: int = 12_000) -> str:
        path = self.percorso(rel)
        if not path.is_file():
            raise ErroreSandbox(f"il file «{rel}» non c'è")
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_caratteri:
            return text[:max_caratteri] + f"\n[… tagliato: {len(text)} caratteri in tutto]"
        return text

    def scrivi(self, rel, contenuto) -> dict:
        if not isinstance(contenuto, str):
            raise ErroreSandbox("il contenuto deve essere testo")
        if len(contenuto) > self.max_file:
            raise ErroreSandbox(f"file troppo grande (massimo {self.max_file} caratteri)")
        path = self.percorso(rel, scrittura=True)
        if path.relative_to(self.root).as_posix() in self.sola_lettura:
            raise ErroreSandbox(f"«{rel}» è in sola lettura: leggilo, non cambiarlo")
        files = self._files()
        if path not in files and len(files) >= self.max_files:
            raise ErroreSandbox(f"troppi file (massimo {self.max_files})")
        totale = sum(p.stat().st_size for p in files if p != path) + len(contenuto.encode())
        if totale > self.max_totale:
            raise ErroreSandbox("spazio della cartella esaurito")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contenuto, encoding="utf-8", newline="\n")
        return {"ok": True, "percorso": path.relative_to(self.root).as_posix(),
                "righe": contenuto.count("\n") + 1}

    def metti(self, rel, dati: bytes) -> dict:
        """Un file della persona come input (03/10): testo o Word, Excel, PDF, in byte. Stessi
        controlli dei percorsi e degli spazi di `scrivi`."""
        if not isinstance(dati, (bytes, bytearray)):
            raise ErroreSandbox("servono i byte del file")
        path = self.percorso(rel, scrittura=True, dati=True)
        files = self._files()
        if path not in files and len(files) >= self.max_files:
            raise ErroreSandbox(f"troppi file (massimo {self.max_files})")
        totale = sum(p.stat().st_size for p in files if p != path) + len(dati)
        if totale > self.max_totale:
            raise ErroreSandbox("spazio della cartella esaurito")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(dati))
        return {"ok": True, "percorso": path.relative_to(self.root).as_posix()}

    # ── esecuzione ──
    @staticmethod
    def _argomenti(argomenti, stdin) -> tuple[list[str], str | None]:
        args = [str(a) for a in (argomenti or [])][:20]
        if any(len(a) > 500 or "\x00" in a for a in args):
            raise ErroreSandbox("argomenti non validi")
        if stdin is not None:
            stdin = str(stdin)
            if len(stdin) > 20_000 or "\x00" in stdin:
                raise ErroreSandbox("input non valido (al massimo 20 000 caratteri)")
        return args, stdin

    def esegui(self, rel, argomenti=(), stdin: str | None = None, flusso=None) -> dict:
        """Un programma della cartella: un file .py, oppure un file .cs (si compilano tutti i
        .cs della sua cartella, nel container del C#). `stdin`: testo per il programma (dopo,
        lo stdin si chiude). `flusso(tipo, testo)`: l'uscita mentre arriva, «out» o «err»
        (04/10: l'esecuzione dimostrativa sugli schermi), chiamato dai thread di lettura."""
        path = self.percorso(rel)
        if path.suffix.lower() == ".cs" and path.is_file():
            cartella = path.parent.relative_to(self.root).as_posix()
            return self.esegui_cs(cartella, argomenti, stdin, flusso)
        if path.suffix.lower() != ".py" or not path.is_file():
            raise ErroreSandbox("si eseguono solo file .py (o .cs) della cartella del lavoro")
        args, stdin = self._argomenti(argomenti, stdin)
        return self._lancia("script", path.relative_to(self.root).as_posix(), args,
                            stdin=stdin, flusso=flusso)

    def esegui_cs(self, cartella: str = "", argomenti=(), stdin: str | None = None,
                  flusso=None) -> dict:
        """Compila i file .cs di `cartella` (relativa; vuota = la principale) ed esegue il
        programma, nel container del C# (04/10). Solo con Docker: mai sull'host."""
        iso = self.linguaggi.get("csharp")
        if iso is None or not iso.pronto:
            raise ErroreSandbox("il C# qui non c'è (" + (iso.descrizione if iso else
                                                         "nessun container per il C#")
                                + "): scrivi il programma in Python")
        cart = str(cartella or "").strip().replace("\\", "/").strip("/")
        if cart in ("", "."):
            cart, base = ".", self.root
        else:
            base = self.percorso(cart + "/x.cs").parent
            cart = base.relative_to(self.root).as_posix()
        if not base.is_dir() or not any(p.suffix.lower() == ".cs" for p in base.iterdir()):
            raise ErroreSandbox("nella cartella non ci sono file .cs")
        args, stdin = self._argomenti(argomenti, stdin)
        return self._lancia("csharp", cart, args, stdin=stdin, flusso=flusso, isolamento=iso)

    def test(self, rel=None) -> dict:
        """I test della cartella: quelli Python (test_*.py) e, dal 05/10, quelli JavaScript
        (*.test.js, con la sintassi degli altri .js) nel container di Node. Con tutti e due i
        conti si sommano."""
        nomi = [p.relative_to(self.root).as_posix() for p in self._files()]
        js = file_test_js(nomi)
        if rel and str(rel).endswith(".js"):
            path = self.percorso(rel)
            if not path.is_file():
                raise ErroreSandbox(f"il file di test «{rel}» non c'è")
            return self.test_js([path.relative_to(self.root).as_posix()])
        if not rel and js and not any(Path(n).name.startswith("test") and n.endswith(".py")
                                      or n.endswith("_test.py") for n in nomi):
            return self.test_js()
        target = ""
        if rel:
            path = self.percorso(rel)
            if path.suffix.lower() != ".py" or not path.is_file():
                raise ErroreSandbox(f"il file di test «{rel}» non c'è")
            target = path.relative_to(self.root).as_posix()
        r = self._lancia("test", target, [])
        if rel or not js:
            return r
        j = self.test_js()
        e = {k: int((r.get("esito") or {}).get(k, 0)) + int((j.get("esito") or {}).get(k, 0))
             for k in ("eseguiti", "falliti", "errori", "saltati")}
        return {**r, "esito": e, "passano": bool(r.get("passano") and j.get("passano")),
                "uscita": (r.get("uscita") or "") + "\n— test JavaScript —\n"
                          + (j.get("uscita") or "")}

    def test_js(self, files=None) -> dict:
        """I test JavaScript (05/10): node:test nel container di Node, mai sull'host. La
        sintassi di tutti gli altri .js si controlla prima (senza eseguirli)."""
        iso = self.linguaggi.get("javascript")
        if iso is None or not iso.pronto:
            vuoto = {"eseguiti": 0, "falliti": 0, "errori": 1, "saltati": 0}
            return {"codice_uscita": None, "esito": vuoto, "passano": False, "secondi": 0,
                    "scaduto": False,
                    "uscita": "i test JavaScript qui non si possono eseguire: manca il container "
                              "di Node (calliope motore sandbox costruisci javascript)",
                    "errore": "manca il container di Node"}
        nomi = [p.relative_to(self.root).as_posix() for p in self._files()
                if p.suffix.lower() == ".js"]
        tutti = sorted(set(nomi) | set(files or ()))
        return self._lancia("test_js", "", tutti, isolamento=iso)

    def termina(self):
        """Ferma l'esecuzione in corso (annullo del lavoro). Non aspetta: si chiama anche dal
        thread della voce («fermalo», lavori_annulla)."""
        with self._lock:
            job, proc, nome = self._job, self._proc, self._nome
        if nome is not None:
            # Il client docker esce da solo quando il container muore: ucciderlo lascerebbe
            # il container vivo fino al suo timeout. `docker kill` in un thread suo (06/10,
            # analisi complessiva): avviare il client costa decine di ms (secondi con Docker
            # lento), e lì si aspetta anche la sua fine (niente processi zombie su Linux)
            threading.Thread(target=self._ferma_container, args=(nome,), daemon=True,
                             name="sandbox-kill").start()
        elif job is not None:
            job.termina()
        elif proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def _ambiente(self, exe: str) -> dict:
        tmp = str(self.tmp)
        env = {"TEMP": tmp, "TMP": tmp, "TMPDIR": tmp, "HOME": str(self.root),
               "USERPROFILE": str(self.root), "APPDATA": tmp, "LOCALAPPDATA": tmp,
               "PATH": str(Path(exe).parent), "NO_PROXY": "*", "no_proxy": "*",
               "PYTHONIOENCODING": "utf-8", "LANG": "it_IT.UTF-8",
               # numpy (che openpyxl importa) con un thread solo: OpenBLAS riserva memoria per
               # ogni thread e sotto il tetto del job non partiva; e la CPU resta alla voce
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        for k in ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "NUMBER_OF_PROCESSORS",
                  "PROCESSOR_ARCHITECTURE"):
            if os.environ.get(k):
                env[k] = os.environ[k]
        return env

    def _lancia(self, modo: str, target: str, args: list[str], stdin: str | None = None,
                flusso=None, isolamento: Isolamento | None = None) -> dict:
        nonce = "ESITO_" + secrets.token_hex(8)
        # Con `flusso` stdout e stderr separati (lo schermo li distingue), altrimenti insieme
        # come li legge l'agente
        kw = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE if flusso else subprocess.STDOUT, cwd=str(self.root))
        t0 = time.perf_counter()
        job = nome = None
        iso = isolamento or self.isolamento
        docker = iso.motore == "docker"
        if docker:
            # Le cartelle dei pacchetti sono quelle dell'immagine: niente siti dall'host. Il
            # C# non ha la riga di configurazione: lo stdin è tutto del programma
            conf = ("" if modo == "csharp" else nonce + "\n" if modo == "test_js" else
                    json.dumps({"nonce": nonce, "siti": [], "leggibili": []}) + "\n")
            nome = "calliope-sandbox-" + secrets.token_hex(6)
            cmd = self._comando_docker(nome, modo, target, args, isolamento=iso)
            # Il client docker non ha limiti (RLIMIT_AS lo romperebbe): i limiti sono quelli
            # del container. Muore con Calliope; il container no, ma si ferma da sé (timeout)
            if os.name != "nt":
                kw.update(start_new_session=True, preexec_fn=_figlio_docker)
            proc = subprocess.Popen(cmd, **kw)
        else:
            exe, base = _interprete()
            cmd = [exe, "-I", "-B", "-u", "-X", "utf8", str(_AVVIO), str(self.root), modo, target,
                   *args]
            siti = _siti()
            conf = json.dumps({"nonce": nonce, "siti": siti, "leggibili": siti}) + "\n"
            kw["env"] = self._ambiente(exe)
            if winjob.disponibile():
                job = winjob.JobObject(una_sola=base, memoria_mb=self.memoria_mb, ui=True)
                proc = winjob.avvia_nel_job(cmd, job, creationflags=winjob.CREATE_NO_WINDOW
                                            | winjob.BELOW_NORMAL_PRIORITY_CLASS, **kw)
            else:
                proc = subprocess.Popen(cmd, start_new_session=True,
                                        preexec_fn=self._limiti_posix, **kw)
        with self._lock:
            self._job, self._proc, self._nome = job, proc, nome
        self.esecuzioni += 1
        buf, size = [], [0]
        buf_lock = threading.Lock()

        def leggi(stream, tipo):
            import codecs
            dec = codecs.getincrementaldecoder("utf-8")("replace")
            try:
                while True:
                    # read1: quello che c'è, senza aspettare 4 KB (l'uscita in diretta)
                    chunk = stream.read1(4096) if flusso else stream.read(4096)
                    if not chunk:
                        break
                    with buf_lock:
                        if size[0] < self.max_uscita * 4:
                            buf.append(chunk)
                        size[0] += len(chunk)
                    if flusso:
                        t = dec.decode(chunk)
                        if t:
                            try:
                                flusso(tipo, t)
                            except Exception:  # noqa: BLE001 — lo schermo non ferma il programma
                                pass
            except (OSError, ValueError):
                pass
        readers = [threading.Thread(target=leggi, args=(proc.stdout, "out"), daemon=True,
                                    name="sandbox-uscita")]
        if flusso:
            readers.append(threading.Thread(target=leggi, args=(proc.stderr, "err"),
                                            daemon=True, name="sandbox-errori"))
        for r in readers:
            r.start()
        try:
            proc.stdin.write((conf + (stdin or "")).encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        scaduto = False
        try:
            proc.wait(timeout=self.tempo_s)
        except subprocess.TimeoutExpired:
            scaduto = True
            if nome is not None:
                self._ferma_container(nome)
            elif job is not None:
                job.termina()
            else:
                self._uccidi_posix(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        for r in readers:
            r.join(timeout=2)
        with self._lock:
            self._job, self._proc, self._nome = None, None, None
        if job is not None:
            job.close()
        out = b"".join(buf).decode("utf-8", "replace")
        esito = None
        lines = out.rstrip().splitlines()
        if modo in ("test", "test_js") and lines and lines[-1].startswith(nonce + " "):
            try:
                esito = json.loads(lines[-1][len(nonce) + 1:])
            except ValueError:
                esito = None
            out = "\n".join(lines[:-1])
        out = out.replace(nonce, "ESITO")
        if len(out) > self.max_uscita:
            half = self.max_uscita // 2
            out = out[:half] + f"\n[… {len(out) - self.max_uscita} caratteri omessi …]\n" \
                + out[-half:]
        res = {"codice_uscita": proc.returncode, "uscita": out,
               "secondi": round(time.perf_counter() - t0, 2), "scaduto": scaduto}
        if scaduto:
            res["errore"] = f"tempo scaduto ({self.tempo_s:.0f} s): processo fermato"
        elif docker and proc.returncode == 137:
            # SIGKILL senza tempo scaduto: il tetto di memoria del container (OOM)
            res["errore"] = (f"processo ucciso: memoria esaurita (massimo {self.memoria_mb} MB)"
                             " o troppi processi")
        elif docker and proc.returncode in (125, 126, 127):
            res["errore"] = "il container della sandbox non è partito"
        elif modo == "csharp" and "— compilazione non riuscita —" in out:
            res["errore"] = "la compilazione non è riuscita"
            res["compilazione"] = False
        if modo in ("test", "test_js"):
            res["esito"] = esito or {"eseguiti": 0, "falliti": 0, "errori": 1, "saltati": 0}
            e = res["esito"]
            res["passano"] = bool(esito) and e["eseguiti"] > 0 and not e["falliti"] \
                and not e["errori"] and not scaduto
        return res

    def _comando_docker(self, nome: str, modo: str, target: str, args: list[str],
                        isolamento: Isolamento | None = None) -> list:
        """`docker run` per un'esecuzione: un container usa-e-getta, senza rete, con il disco
        in sola lettura tranne la cartella del lavoro (vedi il docstring del modulo). `modo`
        «csharp»: l'immagine del C# ed esegui_cs.sh al posto di _avvio.py (04/10)."""
        iso = isolamento or self.isolamento
        csharp = modo == "csharp"
        node = modo == "test_js"
        mem = max(64, self.memoria_mb)
        try:
            utente = f"{os.getuid()}:{os.getgid()}"
            if os.getuid() == 0:
                utente = "65534:65534"           # mai root nel container
        except AttributeError:                   # Windows (solo le prove con docker finto)
            utente = "65534:65534"
        tmp = f"{_LAVORO_C}/.tmp"
        env = {"HOME": _LAVORO_C, "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp,
               "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8", "NO_PROXY": "*",
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        cmd = [*(iso.docker or ["docker"]), "run", "--rm", "-i", "--name", nome,
               "--label", "calliope.sandbox=1", "--pull", "never", "--log-driver", "none",
               "--network", "none", "--hostname", "sandbox", "--read-only",
               "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--user", utente,
               "--memory", f"{mem}m", "--memory-swap", f"{mem}m",
               # RLIMIT_DATA: una richiesta troppo grande dà MemoryError (all'agente serve
               # capire), il tetto del cgroup resta per tutto il resto. Non per Node (05/10):
               # V8 riserva la sua area del codice all'avvio e con il limite non parte
               *([] if node else ["--ulimit", f"data={mem * 1024 * 1024}"]),
               "--pids-limit", str(self.max_processi), "--cpus", f"{self.cpu:g}",
               "--cpu-shares", "256",          # come nice 10: la CPU alla voce
               "--mount", f"type=bind,src={self.root},dst={_LAVORO_C}",
               "--mount", (f"type=bind,src={_ESEGUI_CS},dst={_ESEGUI_CS_C},readonly" if csharp
                           else f"type=bind,src={_TEST_JS},dst={_TEST_JS_C},readonly" if node
                           else f"type=bind,src={_AVVIO},dst={_AVVIO_C},readonly"),
               *(["--mount", f"type=bind,src={_FUMO_JS},dst={_FUMO_JS_C},readonly"] if node
                 else []),
               "-w", _LAVORO_C]
        if csharp:
            env.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_gcServer="0")
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        # Il tempo massimo anche dentro: se Calliope muore il container si ferma da solo
        dentro = int(self.tempo_s) + 5
        cmd += [iso.immagine or "calliope-sandbox", "timeout", "-s", "KILL", str(dentro)]
        if csharp:
            return cmd + ["sh", _ESEGUI_CS_C, target, *args]
        if node:
            return cmd + ["node", _TEST_JS_C, *args]
        return cmd + ["python", "-I", "-B", "-u", "-X", "utf8", _AVVIO_C, _LAVORO_C, modo, target,
                      *args]

    def _ferma_container(self, nome: str, aspetta: bool = True):
        cmd = [*(self.isolamento.docker or ["docker"]), "kill", nome]
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            if aspetta:
                p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _limiti_posix(self):   # pragma: no cover — solo fuori da Windows
        import resource
        winjob.muori_con_il_padre(9)          # SIGKILL: muore con Calliope (Linux)
        try:
            os.nice(10)                       # come BELOW_NORMAL su Windows: la CPU alla voce
        except OSError:
            pass
        mem = self.memoria_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
        except (ValueError, OSError):
            pass

    @staticmethod
    def _uccidi_posix(proc):   # pragma: no cover
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()

    # ── risultati ──
    def copia_in(self, dest: Path) -> list[str]:
        """Copia i file del lavoro (solo testo, senza .tmp né __pycache__) in `dest`."""
        dest.mkdir(parents=True, exist_ok=True)
        out = []
        for p in self._files():
            rel = p.relative_to(self.root)
            if rel.as_posix() in self.sola_lettura:
                continue
            q = dest / rel
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_bytes(p.read_bytes())
            out.append(rel.as_posix())
        return out
