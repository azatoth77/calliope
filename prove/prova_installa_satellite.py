import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dell'installazione di un satellite con un comando (03/10/2026:
calliope/satellite/pacchetto.py, web.py, aggiorna.py, installazione/avvio.py e installa.ps1).

- pacchetto: zip deterministico (stesso SHA-256 due volte), versione = impronta del contenuto
  (non cambia se cambia un modulo che il satellite non importa), moduli del satellite e
  niente prove né documenti, requisiti da uv.lock con gli SHA-256 dei wheel per Windows,
  silero-vad senza dipendenze, modello della wake word mancante, wheel ARM64 mancante;
- server dei satelliti vero su 127.0.0.1 con TLS (openssl): pagina, script, manifesto e
  pacchetto sulla stessa porta del WebSocket, che continua a funzionare; benvenuto con
  l'annuncio della versione; pagina /satellite del server degli schermi;
- curl.exe di Windows con la chiave giusta e sbagliata (deve fermarsi, codice 90);
- installa.ps1 (Windows PowerShell 5.1) con la chiave sbagliata (si ferma senza scrivere
  niente), giusta fino al pacchetto verificato, pacchetto diverso dal manifesto (si ferma);
- avvio.py prepara con un uv finto (venv vero, librerie del venv delle prove): versione
  pronta e verificata, SHA-256 sbagliato, nomi pericolosi nel pacchetto;
- avvio.py come avvio con satelliti finti: aggiornamento confermato (anche l'avvio stesso si
  aggiorna), versione nuova che non si ricollega (torna indietro e non la riprova), versione
  che cade subito;
- aggiornatore del satellite: scarica dalla porta dei satelliti con l'impronta giusta, rifiuta
  l'impronta sbagliata, non riprova una versione rifiutata, il satellite del repository non
  si aggiorna mai.

Con --vera anche l'installazione con uv e Python veri in una cartella temporanea (serve
internet la prima volta, poi la cache di uv basta): vedi prove/LEGGIMI.md.
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
# Il codice da cui si costruiscono i pacchetti: una copia ferma (sorgente_ferma), non l'albero
# di lavoro vivo
SORGENTE = RADICE
ERRORI = []


def ok(msg, cond, extra=""):
    print(f"{'ok ' if cond else 'ERR'} {msg}" + (f"  [{extra}]" if extra and not cond else ""),
          flush=True)
    if not cond:
        ERRORI.append(msg)


def aspetta(cond, timeout=10.0, passo=0.05) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(passo)
    return cond()


def modelli_finti(cartella: Path) -> Path:
    cartella.mkdir(parents=True, exist_ok=True)
    for n in ("calliope.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
        (cartella / n).write_bytes(b"modello finto " + n.encode())
    return cartella


def cfg_prova(tmp: Path, **campi):
    from calliope.config import Config
    cfg = Config()
    cfg.config_dir = str(tmp)
    cfg.memory_db = str(tmp / "memoria.db")
    cfg.satellite_porta = 0
    cfg.satellite_indirizzo = "127.0.0.1"
    cfg.wake_model = str(modelli_finti(tmp / "wake") / "calliope.onnx")
    cfg.audio_modo = "satellite"
    for k, v in campi.items():
        setattr(cfg, k, v)
    return cfg


def sorgente_ferma(dest: Path) -> Path:
    """Una copia ferma di calliope/ e uv.lock da cui costruire i pacchetti (06/10): prima si
    costruivano dall'albero di lavoro vivo, due volte, e con un altro agente che scriveva
    nella stessa cartella la prova falliva con un SyntaxError o con «pacchetto non
    deterministico». Si prende l'indice di git (quello che si sta per committare: nell'hook è
    il codice provato); fuori da git (la copia di --staged, una versione installata) la
    cartella stessa, che lì non cambia."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if not (RADICE / ".git").exists():
            raise OSError("fuori da git")
        nomi = subprocess.run(["git", "-C", str(RADICE), "ls-files", "-z", "--", "calliope",
                               "uv.lock"], capture_output=True, timeout=30, check=True).stdout
        if nomi:
            subprocess.run(["git", "-C", str(RADICE), "checkout-index", "-z", "--stdin",
                            f"--prefix={dest.as_posix()}/"], input=nomi, capture_output=True,
                           timeout=120, check=True)
            if (dest / "uv.lock").is_file() and (dest / "calliope").is_dir():
                return dest
    except (OSError, subprocess.SubprocessError):
        pass
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(RADICE / "calliope", dest / "calliope",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(RADICE / "uv.lock", dest / "uv.lock")
    return dest


# ───────────────────────────── pacchetto ─────────────────────────────
def parte_pacchetto(tmp: Path):
    from calliope.satellite import pacchetto as PK
    wake = modelli_finti(tmp / "wake")
    t0 = time.perf_counter()
    a = PK.costruisci(SORGENTE, wake)
    dt = time.perf_counter() - t0
    b = PK.costruisci(SORGENTE, wake)
    ok(f"pacchetto deterministico: stesso SHA-256 due volte ({a.byte / 1e6:.1f} MB, "
       f"{dt * 1000:.0f} ms)", a.sha256 == b.sha256 and a.versione == b.versione)
    nomi = set(a.file)
    ok("dentro: il satellite, il suo avvio, la wake word, i requisiti, VERSIONE.json",
       {"calliope/satellite/client.py", "calliope/satellite/__main__.py",
        "calliope/satellite/installazione/avvio.py", "calliope/audio.py",
        "calliope/pc/windows.py", "wakeword/modelli/calliope.onnx", "requisiti.txt",
        "requisiti-senza-dipendenze.txt", "VERSIONE.json"} <= nomi)
    ok("fuori: prove, documenti, setup, script d'installazione", not any(
        n.startswith(("prove/", "docs/", "setup/")) or n.endswith(".ps1") for n in nomi))
    with zipfile.ZipFile(__import__("io").BytesIO(a.dati)) as z:
        info = json.loads(z.read("VERSIONE.json"))
        req = z.read("requisiti.txt").decode()
        nodeps = z.read("requisiti-senza-dipendenze.txt").decode()
        date = {zi.date_time for zi in z.infolist()}
    ok("VERSIONE.json: versione e Python", info["versione"] == a.versione
       and info["python"] == PK.PYTHON)
    ok("date fisse nello zip (byte uguali su ogni server)", date == {(1980, 1, 1, 0, 0, 0)})
    lock = (SORGENTE / "uv.lock").read_text(encoding="utf-8")
    import re
    ver_numpy = re.search(r'name = "numpy"\nversion = "([^"]+)"', lock).group(1)
    ok("requisiti: versioni di uv.lock con gli SHA-256", f"numpy=={ver_numpy} \\" in req
       and "--hash=sha256:" in req and "onnxruntime==" in req and "websockets==" in req)
    ok("requisiti: dipendenze comprese (cffi di sounddevice, protobuf di onnxruntime)",
       "cffi==" in req and "protobuf==" in req)
    ok("requisiti: le librerie del PC solo su Windows (marcatore)",
       re.search(r"pywin32==\S+ ; sys_platform == 'win32'", req) is not None)
    ok("requisiti: niente torch; silero-vad a parte, senza dipendenze",
       "torch" not in req and "silero-vad==" in nodeps and "silero-vad" not in req)
    ok("requisiti: solo wheel per Windows (niente manylinux)",
       "manylinux" not in req and lock.count("manylinux") > 0)

    # La versione cambia solo se cambia qualcosa del satellite
    copia = tmp / "codice"
    shutil.copytree(SORGENTE / "calliope", copia / "calliope",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(SORGENTE / "uv.lock", copia / "uv.lock")
    base = PK.costruisci(copia, wake)
    fuori = sorted(set(str(p.relative_to(copia).as_posix())
                       for p in (copia / "calliope").rglob("*.py")) - set(PK.moduli(copia)))
    ok("ci sono moduli che il satellite non importa", bool(fuori), "")
    if fuori:
        f = copia / fuori[0]
        f.write_text(f.read_text(encoding="utf-8") + "\n# modifica\n", encoding="utf-8")
        ok(f"cambia {fuori[0]} (non del satellite): stessa versione",
           PK.costruisci(copia, wake).versione == base.versione)
    c = copia / "calliope" / "satellite" / "client.py"
    c.write_text(c.read_text(encoding="utf-8") + "\n# modifica\n", encoding="utf-8")
    ok("cambia client.py: versione nuova", PK.costruisci(copia, wake).versione != base.versione)

    vuota = tmp / "wake-vuota"
    vuota.mkdir()
    try:
        PK.costruisci(SORGENTE, vuota)
        ok("senza i modelli della wake word niente pacchetto", False)
    except PK.PacchettoNonDisponibile as e:
        ok("senza i modelli della wake word niente pacchetto, con il motivo",
           "wake word" in str(e))
    # Un lock in cui a un pacchetto manca il wheel ARM64
    finto = tmp / "uv-senza-arm.lock"
    finto.write_text(lock.replace("onnxruntime-1.30.0-cp314-cp314-win_arm64.whl",
                                  "onnxruntime-1.30.0-cp314-cp314-win_xxx.whl"), encoding="utf-8")
    try:
        PK.requisiti(finto)
        ok("un wheel win_arm64 mancante ferma il pacchetto", False)
    except ValueError as e:
        ok("un wheel win_arm64 mancante ferma il pacchetto, con il nome", "onnxruntime" in str(e)
           and "win_arm64" in str(e), str(e))
    return a


# ───────────────────────────── server ─────────────────────────────
def server_tls(tmp: Path):
    from calliope.satellite.__main__ import _openssl, certificato
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    if _openssl() is None:
        return None
    cfg = cfg_prova(tmp)
    certificato(cfg, out=lambda m: None)
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=lambda m: None).avvia()
    srv.avviato.set()
    return cfg, arch, srv


def curl(*args, timeout=20) -> tuple[int, bytes]:
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
    r = subprocess.run([str(exe), *args], capture_output=True, timeout=timeout)
    return r.returncode, r.stdout


def parte_server(tmp: Path):
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    from calliope.satellite import web
    ris = server_tls(tmp)
    if ris is None:
        print("SALTATA IN PARTE: openssl non c'è: salto server, curl e installa.ps1")
        return None
    cfg, arch, srv = ris
    ok("il pacchetto si prepara da solo all'avvio del server",
       aspetta(lambda: srv.distributore.pronto() is not None, 15), srv.distributore.motivo)
    pin = web.chiave(cfg)
    ok("chiave del certificato: sha256// e 44 caratteri", pin.startswith("sha256//")
       and len(pin) == 52)
    base = f"https://127.0.0.1:{srv.port}"
    curl_ok = sys.platform == "win32" and (Path(os.environ.get("SystemRoot", "C:\\Windows"))
                                           / "System32" / "curl.exe").is_file()
    if curl_ok:
        rc, corpo = curl("-fsSk", "--pinnedpubkey", pin, base + "/installa")
        testo = corpo.decode("utf-8", "replace")
        ok("curl con la chiave giusta: la pagina con la chiave e il comando",
           rc == 0 and pin in testo and "curl.exe -fsSk --pinnedpubkey" in testo, f"rc {rc}")
        rc, _ = curl("-fsSk", "--pinnedpubkey", "sha256//" + "A" * 43 + "=", base + "/installa")
        ok("curl con la chiave sbagliata si ferma (codice 90)", rc == 90, f"rc {rc}")
        rc, _ = curl("-fsS", base + "/installa")
        ok("senza -k e senza chiave curl non si fida (certificato senza CA)", rc == 60,
           f"rc {rc}")
        rc, corpo = curl("-fsSk", "--pinnedpubkey", pin, base + "/installa/manifesto.json")
        m = json.loads(corpo) if rc == 0 else {}
        ok("manifesto: pacchetto, Python, uv con gli SHA-256, server e impronta",
           m.get("pacchetto", {}).get("sha256") == srv.distributore.pronto().sha256
           and m.get("satellite_server") == f"wss://127.0.0.1:{srv.port}"
           and m.get("satellite_impronta") == srv.impronta
           and len(m.get("uv", {}).get("aarch64", {}).get("sha256", "")) == 64, f"rc {rc}")
        rc, corpo = curl("-fsSk", "--pinnedpubkey", pin, base + "/installa/pacchetto.zip")
        ok("pacchetto scaricato con lo SHA-256 del manifesto",
           rc == 0 and hashlib.sha256(corpo).hexdigest() == m.get("pacchetto", {}).get("sha256"))
        rc, corpo = curl("-fsSk", "--pinnedpubkey", pin, base + "/installa/installa.ps1")
        ok("installa.ps1 con il BOM UTF-8 (Windows PowerShell 5.1)",
           rc == 0 and corpo.startswith(b"\xef\xbb\xbf") and b"--pinnedpubkey" in corpo)
        rc, _ = curl("-fsSk", "--pinnedpubkey", pin, base + "/altro")
        ok("un percorso qualunque: 404", rc == 22)
    else:
        print("SALTATA IN PARTE: niente curl.exe di Windows: salto le prove con curl")

    # Il WebSocket sulla stessa porta continua a funzionare
    import ssl
    from calliope.tls_sicuro import sicuro
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Come il client vero del satellite: websockets legge da un thread suo e scrive da
    # questo, e con l'SSLSocket normale la richiesta di apertura ogni tanto non partiva; il
    # server chiudeva dopo i suoi 3 s («did not receive a valid HTTP response»: 1 volta su
    # ~5 nell'hook, 17–21 aperture su 400 in una sonda, 0 su 400 con sicuro, 03/10)
    sicuro(ctx)
    with connect(f"wss://127.0.0.1:{srv.port}" + P.PERCORSO_ABBINA, ssl=ctx,
                 compression=None) as ws:
        ws.send(P.testo(tipo="abbina", versione=P.VERSIONE, nome="pc-nuovo"))
        codice = P.leggi(ws.recv(timeout=5)).get("codice")
        ok("il WebSocket dei satelliti sulla stessa porta: codice di abbinamento",
           bool(codice))
        arch.abbina(codice or "", "studio")
        token = P.leggi(ws.recv(timeout=5)).get("token")
    with connect(f"wss://127.0.0.1:{srv.port}" + P.PERCORSO_AUDIO, ssl=ctx,
                 compression=None) as ws:
        ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=token, primo=False,
                        nome="pc-nuovo"))
        benv = P.leggi(ws.recv(timeout=5))
    agg = benv.get("aggiornamento") or {}
    ok("benvenuto: la versione del satellite con SHA-256 e dimensione",
       agg.get("versione") == srv.distributore.pronto().versione
       and agg.get("sha256") == srv.distributore.pronto().sha256 and agg.get("byte"))

    # La pagina /satellite sul server degli schermi
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    class Hub:
        pass
    hub = Hub()
    hub.cfg = cfg_prova(tmp, satellite_indirizzo="0.0.0.0", satellite_porta=8771)
    hub.cfg.config_dir = cfg.config_dir
    c = TestClient(Starlette(routes=web.rotte(hub)))
    r = c.get("/satellite", headers={"host": "192.168.1.20:8770"})
    ok("/satellite sugli schermi: comando verso la porta dei satelliti con la chiave",
       r.status_code == 200 and "https://192.168.1.20:8771" in r.text and pin in r.text
       and "default-src 'none'" in r.headers.get("content-security-policy", ""))
    hub.cfg.audio_modo = "locale"
    r = c.get("/satellite", headers={"host": "192.168.1.20:8770"})
    ok("/satellite senza satelliti: dice perché, niente comando",
       "audio_modo" in r.text and "pinnedpubkey" not in r.text)
    hub.cfg.audio_modo = "satellite"
    r = c.get("/satellite.css")
    ok("/satellite.css (niente stili in linea: CSP)", r.status_code == 200)
    righe = []
    from calliope.satellite.__main__ import nuovo_pc
    cfg_rete = cfg_prova(tmp, satellite_indirizzo="0.0.0.0", satellite_porta=8771)
    cfg_rete.config_dir = cfg.config_dir
    nuovo_pc(cfg_rete, righe.append)
    ok("--elenco: la chiave per i PC nuovi e il comando", any(pin in r for r in righe)
       and any("curl.exe" in r for r in righe), " / ".join(righe))
    return cfg, arch, srv, pin


def powershell(*args, timeout=60) -> tuple[int, str]:
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                        "Bypass", *args], capture_output=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


def parte_ps1(tmp: Path, srv, pin: str):
    if sys.platform != "win32" or shutil.which("powershell.exe") is None:
        print("SALTATA IN PARTE: niente Windows PowerShell: salto installa.ps1")
        return
    from calliope.satellite import web
    script = tmp / "installa.ps1"
    script.write_bytes(web.script_ps1())
    base = f"https://127.0.0.1:{srv.port}"
    dest = tmp / "pc-nuovo"
    t0 = time.perf_counter()
    rc, out = powershell("-File", str(script), "-Server", base, "-Chiave",
                         "sha256//" + "B" * 43 + "=", "-Cartella", str(dest),
                         "-AvvioAutomatico", "no", "-NonAvviare")
    ok("installa.ps1 con la chiave sbagliata si ferma e non installa niente",
       rc != 0 and "curl: (90)" in out and "Installazione fermata" in out
       and not (dest / "versioni").exists(), out[-300:])
    rc, out = powershell("-File", str(script), "-Server", base, "-Chiave", pin, "-Cartella",
                         str(dest), "-FinoAlPacchetto")
    ok(f"installa.ps1 con la chiave giusta: manifesto e pacchetto verificati "
       f"({time.perf_counter() - t0:.1f} s le due)", rc == 0 and "pacchetto verificato" in out,
       out[-300:])
    vero = srv.distributore.manifesto

    def manifesto_falso(*a, **kw):
        m = vero(*a, **kw)
        m["pacchetto"]["sha256"] = "0" * 64
        return m
    srv.distributore.manifesto = manifesto_falso
    rc, out = powershell("-File", str(script), "-Server", base, "-Chiave", pin, "-Cartella",
                         str(dest), "-FinoAlPacchetto")
    srv.distributore.manifesto = vero
    ok("installa.ps1: pacchetto diverso dal manifesto, si ferma",
       rc != 0 and "non corrisponde" in out, out[-300:])
    rc, out = powershell("-File", str(script), "-Server", "http://127.0.0.1:1", "-Chiave", pin)
    ok("installa.ps1: niente http in chiaro", rc != 0 and "https://" in out, out[-200:])


# ───────────────────────────── avvio.py ─────────────────────────────
def carica_avvio():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "avvio_prova", RADICE / "calliope" / "satellite" / "installazione" / "avvio.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


UV_FINTO = r'''
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["UV_FINTO_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\n")
if args[:2] == ["python", "install"]:
    sys.exit(0)
if args[0] == "venv":
    sys.exit(subprocess.call([os.environ["UV_FINTO_PY"], "-m", "venv", "--without-pip", args[-1]]))
if args[:2] == ["pip", "install"]:
    if "--offline" in args and os.environ.get("UV_FINTO_OFFLINE_NO"):
        print("error: nessuna rete (offline)", file=sys.stderr)
        sys.exit(2)
    py = Path(args[args.index("--python") + 1])
    sp = py.parent.parent / "Lib" / "site-packages"
    if not sp.is_dir():
        sp = next(py.parent.parent.glob("lib/python*/site-packages"))
    righe = [f"import site; site.addsitedir({d!r})"
             for d in os.environ["UV_FINTO_SITE"].split(os.pathsep) if d]
    (sp / "librerie_prove.pth").write_text("\n".join(righe) + "\n")
    sys.exit(0)
sys.exit(3)
'''


def parte_prepara(tmp: Path, pacchetto):
    import site
    avvio = carica_avvio()
    radice = tmp / "installazione"
    radice.mkdir()
    uv = tmp / "uv_finto.py"
    uv.write_text(UV_FINTO, encoding="utf-8")
    log = tmp / "uv.log"
    base_py = Path(getattr(sys, "_base_executable", sys.executable))
    # Le librerie del Python delle prove (anche quelle aggiunte da un .pth, come nei worktree)
    sp = [p for p in dict.fromkeys(site.getsitepackages() + sys.path)
          if p.endswith("site-packages") and Path(p).is_dir()]
    os.environ.update(UV_FINTO_LOG=str(log), UV_FINTO_PY=str(base_py),
                      UV_FINTO_SITE=os.pathsep.join(sp), UV_FINTO_OFFLINE_NO="1")
    z = tmp / "p.zip"
    z.write_bytes(pacchetto.dati)
    inst = avvio.Installazione(radice, out=lambda m: None)
    try:
        inst.prepara(z, "0" * 64, uv=[sys.executable, str(uv)])
        ok("prepara: SHA-256 sbagliato, si ferma", False)
    except avvio.Errore:
        ok("prepara: SHA-256 sbagliato, si ferma prima di estrarre",
           not (radice / "versioni").exists())
    t0 = time.perf_counter()
    try:
        vid = inst.prepara(z, pacchetto.sha256, attiva=True, uv=[sys.executable, str(uv)])
    except avvio.Errore as e:
        vid = None
        print("    ", e)
    chiamate = [json.loads(r) for r in log.read_text(encoding="utf-8").splitlines()]
    ok(f"prepara: versione pronta e verificata (import del satellite con il venv nuovo, "
       f"{time.perf_counter() - t0:.1f} s)", vid == pacchetto.versione and inst.completa(vid)
       and inst.attuale() == vid)
    ok("prepara: uv con Python fissato, venv del Python di uv, hash obbligatori, solo wheel",
       chiamate[0][:3] == ["python", "install", "3.14.8"] and "--no-registry" in chiamate[0]
       and any(c[0] == "venv" and "--managed-python" in c for c in chiamate)
       and all("--require-hashes" in c and "--only-binary" in c
               for c in chiamate if c[:2] == ["pip", "install"]))
    ok("prepara: prima dalla cache (--offline), poi dalla rete; silero-vad con --no-deps",
       [c for c in chiamate if c[:2] == ["pip", "install"]][0][2] == "--offline"
       and any("--no-deps" in c for c in chiamate))
    vid2 = inst.prepara(z, pacchetto.sha256, uv=[sys.executable, str(uv)])
    ok("prepara di nuovo la stessa versione: già pronta, niente uv",
       vid2 == vid and len(log.read_text(encoding="utf-8").splitlines()) == len(chiamate))
    # Un pacchetto con un nome che esce dalla cartella
    cattivo = tmp / "cattivo.zip"
    with zipfile.ZipFile(cattivo, "w") as zz:
        zz.writestr("VERSIONE.json", json.dumps({"versione": "abcdef123456"}))
        zz.writestr("../fuori.txt", "x")
    sha = hashlib.sha256(cattivo.read_bytes()).hexdigest()
    try:
        inst.prepara(cattivo, sha, uv=[sys.executable, str(uv)])
        ok("prepara: nomi con «..» rifiutati", False)
    except avvio.Errore:
        ok("prepara: nomi con «..» rifiutati, niente fuori dalla cartella",
           not (radice / "versioni" / "fuori.txt").exists()
           and not (radice / "versioni" / "abcdef123456").exists())


SAT_FINTO = r'''
import json, os, sys, time
from pathlib import Path
vid, radice = sys.argv[1], Path(sys.argv[2])
piano = json.loads((radice / "piano.json").read_text())
fatti = json.loads((radice / "fatti.json").read_text()) if (radice / "fatti.json").exists() else {}
n = fatti.get(vid, 0)
fatti[vid] = n + 1
(radice / "fatti.json").write_text(json.dumps(fatti))
azione = piano[vid][min(n, len(piano[vid]) - 1)]
assert os.environ["CALLIOPE_SATELLITE_VERSIONE"] == vid
if azione.startswith("aggiorna:"):
    nuova = azione.split(":")[1]
    (radice / "prova.json").write_text(json.dumps({"versione": nuova, "da": vid}))
    sys.exit(75)
if azione == "conferma":
    time.sleep(0.3)
    (radice / f"confermata-{vid}").write_text("ok")
    time.sleep(0.6)
    sys.exit(0)
if azione == "dormi":
    time.sleep(60)
if azione == "cade":
    sys.exit(1)
sys.exit(0)
'''


def installazione_finta(tmp: Path, nome: str, piano: dict):
    avvio = carica_avvio()
    radice = tmp / nome
    for vid in piano:
        d = radice / "versioni" / vid
        (d / ".venv" / "Scripts").mkdir(parents=True)
        (d / ".venv" / "bin").mkdir(parents=True)
        (d / ".venv" / "Scripts" / "python.exe").write_text("")
        (d / ".venv" / "bin" / "python").write_text("")
        (d / "VERSIONE.json").write_text(json.dumps({"versione": vid}))
    (radice / "attuale").write_text("vecchia\n")
    (radice / "avvio.py").write_text("# avvio vecchio\n")
    nuovo_avvio = radice / "versioni" / "nuova" / "calliope" / "satellite" / "installazione"
    nuovo_avvio.mkdir(parents=True)
    (nuovo_avvio / "avvio.py").write_text("# avvio nuovo\n")
    (radice / "piano.json").write_text(json.dumps(piano))
    sat = tmp / "sat_finto.py"
    sat.write_text(SAT_FINTO, encoding="utf-8")
    inst = avvio.Installazione(radice, out=lambda m: None)
    comando = lambda vid: [sys.executable, str(sat), vid, str(radice)]  # noqa: E731
    return avvio, inst, comando


def parte_avvio(tmp: Path):
    # 1. Aggiornamento riuscito: la vecchia prepara la nuova ed esce con 75; la nuova si
    #    ricollega (conferma) e poi la si chiude
    avvio, inst, cmd = installazione_finta(tmp, "a", {"vecchia": ["aggiorna:nuova", "esci"],
                                                      "nuova": ["conferma"]})
    t0 = time.perf_counter()
    rc = inst.esegui(prova_s=10, comando=cmd, attese=(0,))
    log = (inst.radice / "avvio.log").read_text(encoding="utf-8")
    ok(f"avvio: aggiornamento confermato, in uso la nuova ({time.perf_counter() - t0:.1f} s)",
       rc == 0 and inst.attuale() == "nuova" and inst.precedente() == "vecchia"
       and not (inst.radice / "prova.json").exists() and "confermata" in log, log[-300:])
    ok("avvio: dopo la conferma anche avvio.py è quello della versione nuova",
       (inst.radice / "avvio.py").read_text() == "# avvio nuovo\n")

    # 2. La versione nuova non si ricollega: dopo il tempo di prova torna alla vecchia
    avvio, inst, cmd = installazione_finta(tmp, "b", {"vecchia": ["aggiorna:nuova", "esci"],
                                                      "nuova": ["dormi"]})
    t0 = time.perf_counter()
    rc = inst.esegui(prova_s=2, comando=cmd, attese=(0,))
    dt = time.perf_counter() - t0
    log = (inst.radice / "avvio.log").read_text(encoding="utf-8")
    fatti = json.loads((inst.radice / "fatti.json").read_text())
    ok(f"avvio: versione che non si ricollega, torna alla vecchia dopo la prova ({dt:.1f} s)",
       rc == 0 and inst.attuale() == "vecchia" and fatti == {"vecchia": 2, "nuova": 1}
       and "torno a vecchia" in log and 2 <= dt < 20, log[-300:])
    from calliope.satellite.aggiorna import Installazione
    ok("avvio: la versione tornata indietro è rifiutata (non si riprova per ore)",
       Installazione(inst.radice, "vecchia").rifiutata("nuova")
       and not Installazione(inst.radice, "vecchia").rifiutata("altra"))
    ok("avvio: avvio.py resta il vecchio", (inst.radice / "avvio.py").read_text()
       == "# avvio vecchio\n")

    # 3. La versione nuova cade subito: torna indietro senza aspettare
    avvio, inst, cmd = installazione_finta(tmp, "c", {"vecchia": ["aggiorna:nuova", "esci"],
                                                      "nuova": ["cade"]})
    t0 = time.perf_counter()
    rc = inst.esegui(prova_s=30, comando=cmd, attese=(0,))
    ok(f"avvio: versione che cade prima di ricollegarsi, torna subito "
       f"({time.perf_counter() - t0:.1f} s)", rc == 0 and inst.attuale() == "vecchia"
       and time.perf_counter() - t0 < 10)

    # 4. Una caduta normale (non in prova) si riavvia
    avvio, inst, cmd = installazione_finta(tmp, "d", {"vecchia": ["cade", "esci"]})
    rc = inst.esegui(prova_s=30, comando=cmd, attese=(0,))
    ok("avvio: il satellite caduto si riavvia da solo",
       rc == 0 and json.loads((inst.radice / "fatti.json").read_text()) == {"vecchia": 2})


# ───────────────────────────── aggiornatore ─────────────────────────────
def parte_aggiornatore(tmp: Path, srv):
    from calliope.satellite.aggiorna import Aggiornatore, Installazione
    radice = tmp / "inst-agg"
    radice.mkdir()
    (radice / "avvio.py").write_text("#")
    ok("il satellite del repository non si aggiorna (niente variabili dell'avvio)",
       Installazione.da_ambiente({}) is None and Installazione.da_ambiente(
           {"CALLIOPE_SATELLITE_INSTALLAZIONE": str(tmp / "non-c-e"),
            "CALLIOPE_SATELLITE_VERSIONE": "x"}) is None)
    inst = Installazione.da_ambiente({"CALLIOPE_SATELLITE_INSTALLAZIONE": str(radice),
                                      "CALLIOPE_SATELLITE_VERSIONE": "vecchia"})
    preparati, righe = [], []

    def prepara(zip_path, sha):
        preparati.append((hashlib.sha256(Path(zip_path).read_bytes()).hexdigest(), sha))
    agg = Aggiornatore(inst, log=righe.append, prepara=prepara)
    p = srv.distributore.pronto()
    url = f"wss://127.0.0.1:{srv.port}"
    ok("aggiornatore: stessa versione, niente da fare",
       not agg.proponi({**p.annuncio(), "versione": "vecchia"}, url, srv.impronta))
    ok("aggiornatore: versione nuova, parte", agg.proponi(p.annuncio(), url, srv.impronta))
    ok("aggiornatore: scaricato dalla porta dei satelliti, SHA-256 giusto, pronto al riavvio",
       aspetta(agg.pronto.is_set, 15) and preparati == [(p.sha256, p.sha256)],
       " / ".join(righe[-2:]))
    agg2 = Aggiornatore(inst, log=righe.append, prepara=prepara)
    agg2.proponi(p.annuncio(), url, "AB:" * 31 + "AB")
    ok("aggiornatore: impronta del certificato diversa, niente download",
       aspetta(lambda: not agg2.in_corso, 10) and not agg2.pronto.is_set()
       and "non è quello abbinato" in righe[-1], righe[-1])
    ok("aggiornatore: non riprova subito la stessa versione",
       not agg2.proponi(p.annuncio(), url, srv.impronta))
    (radice / "rifiutate.json").write_text(json.dumps({p.versione: time.time()}))
    agg3 = Aggiornatore(inst, log=righe.append, prepara=prepara)
    ok("aggiornatore: versione tornata indietro da poco, non la riprova",
       not agg3.proponi(p.annuncio(), url, srv.impronta))
    (radice / "prova.json").write_text(json.dumps({"versione": "vecchia", "da": "x"}))
    ok("conferma: la versione in prova collegata scrive confermata-<versione>",
       inst.conferma(lambda m: None) and (radice / "confermata-vecchia").exists())

    # Il satellite si riavvia solo a conversazione ferma e collegato
    from calliope.satellite.client import Satellite

    class Player:
        in_corso = False
        ultima_scrittura = 0.0
    s = Satellite.__new__(Satellite)
    s.collegato, s.player, s._ultimo_audio = threading.Event(), Player(), 0.0
    s.collegato.set()
    ok("riavvio: inattivo quando nessuno parla", s.inattivo())
    s._ultimo_audio = time.monotonic()
    ok("riavvio: non mentre arriva una frase", not s.inattivo())
    s._ultimo_audio = 0.0
    s.player.in_corso = True
    ok("riavvio: non mentre parla", not s.inattivo())
    s.player.in_corso = False
    s.collegato.clear()
    ok("riavvio: non da scollegato (la versione nuova deve ricollegarsi)", not s.inattivo())


# ───────────────────────────── --vera ─────────────────────────────
def parte_vera(tmp: Path, srv, pin: str):
    """installa.ps1 completo con uv e Python veri (scaricati la prima volta), in una
    cartella temporanea; poi un aggiornamento preparato davvero (uv dalla cache)."""
    from calliope.satellite import web
    from calliope.satellite.pacchetto import Distributore
    script = tmp / "installa.ps1"
    script.write_bytes(web.script_ps1())
    dest = tmp / "pc-vero"
    t0 = time.perf_counter()
    args = ["-File", str(script), "-Server", f"https://127.0.0.1:{srv.port}", "-Chiave", pin,
            "-Cartella", str(dest), "-AvvioAutomatico", "no", "-NonAvviare"]
    uv_cache = os.environ.get("CALLIOPE_PROVA_UV")
    if uv_cache:
        args += ["-Uv", uv_cache]
    rc, out = powershell(*args, timeout=1800)
    dt = time.perf_counter() - t0
    print("\n".join("      " + r for r in out.strip().splitlines()[-12:]))
    vid = (dest / "attuale").read_text().strip() if (dest / "attuale").exists() else ""
    ok(f"installazione vera: uv, Python {srv.distributore.pronto() and '3.14.8'}, venv "
       f"verificato ({dt:.0f} s)", rc == 0 and vid == srv.distributore.pronto().versione
       and (dest / "versioni" / vid / ".venv").is_dir() and (dest / "avvia.cmd").is_file(),
       out[-400:])
    locale = (dest / "dati" / "calliope.locale.yaml").read_text(encoding="utf-8") \
        if (dest / "dati" / "calliope.locale.yaml").exists() else ""
    ok("installazione vera: calliope.locale.yaml con server e impronta",
       srv.impronta in locale and f"wss://127.0.0.1:{srv.port}" in locale)
    py = dest / "versioni" / vid / ".venv" / "Scripts" / "python.exe"
    # silero_vad non si importa (vorrebbe torch): serve solo il suo file ONNX (calliope/vad.py)
    r = subprocess.run([str(py), "-c", "import numpy, onnxruntime, sounddevice, websockets, "
                        "yaml, pywintypes, pycaw, psutil; from calliope.vad import modello_onnx;"
                        " import calliope.satellite.client; assert modello_onnx()"],
                       capture_output=True, text=True, cwd=dest / "versioni" / vid)
    ok("installazione vera: le librerie bloccate e il VAD in ONNX ci sono (niente torch)",
       r.returncode == 0, r.stderr[-300:])
    r = subprocess.run([str(py), "-m", "calliope.satellite", "--help"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       cwd=dest / "versioni" / vid)
    ok("installazione vera: python -m calliope.satellite risponde", r.returncode == 0
       and "--abbina" in r.stdout, r.stderr[-300:])
    # Aggiornamento vero: una versione nuova del server (client.py cambiato), preparata con
    # uv dalla cache (niente rete se le librerie sono le stesse)
    copia = tmp / "codice-nuovo"
    shutil.copytree(SORGENTE / "calliope", copia / "calliope",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(SORGENTE / "uv.lock", copia / "uv.lock")
    c = copia / "calliope" / "satellite" / "client.py"
    c.write_text(c.read_text(encoding="utf-8") + "\n# versione nuova\n", encoding="utf-8")
    srv.distributore = Distributore(srv.cfg, radice=copia, log=lambda m: None)
    nuovo = srv.distributore.pacchetto()
    from calliope.satellite.aggiorna import Aggiornatore, Installazione
    inst = Installazione(dest, vid)
    righe = []
    os.environ["CALLIOPE_SATELLITE_RADICE"] = str(dest)
    agg = Aggiornatore(inst, log=righe.append)
    t0 = time.perf_counter()
    agg.proponi(nuovo.annuncio(), f"wss://127.0.0.1:{srv.port}", srv.impronta)
    pronto = aspetta(agg.pronto.is_set, 900, 0.5)
    prova = json.loads((dest / "prova.json").read_text()) if (dest / "prova.json").exists() \
        else {}
    ok(f"aggiornamento vero: scaricato e preparato accanto con uv dalla cache "
       f"({time.perf_counter() - t0:.1f} s), in prova", pronto
       and prova.get("versione") == nuovo.versione and prova.get("da") == vid,
       " / ".join(righe[-2:]))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    vera = "--vera" in sys.argv
    # ignore_cleanup_errors: se una parte si rompe a metà, il database ancora aperto non deve
    # aggiungere altri traceback a quello che conta (03/10)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        global SORGENTE
        SORGENTE = sorgente_ferma(tmp / "sorgente")
        # Anche il server dei satelliti costruisce il suo pacchetto dalla copia ferma
        from calliope.satellite import pacchetto as PK
        PK.radice_codice = lambda: SORGENTE
        pacchetto = parte_pacchetto(tmp / "p")
        ris = parte_server(tmp / "s")
        try:
            if ris is not None:
                cfg, arch, srv, pin = ris
                parte_ps1(tmp / "s", srv, pin)
                parte_aggiornatore(tmp / "s", srv)
            (tmp / "r").mkdir()
            parte_prepara(tmp / "r", pacchetto)
            parte_avvio(tmp)
            if vera and ris is not None:
                parte_vera(tmp / "s", srv, pin)
        finally:
            if ris is not None:
                srv.ferma()
                arch.close()
    print(f"\n{'Tutto bene' if not ERRORI else f'{len(ERRORI)} errori'}")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
