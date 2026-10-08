import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La web app del telefono in un browser vero (Edge o Chromium senza finestra, comandato con
il protocollo DevTools), con il microfono finto del browser (03/10/2026).

Server degli schermi e dei satelliti veri nel processo (niente Calliope: l'ascolto lo fa
`AscoltoRemoto` come nel ciclo di main.py), pagina /telefono su http://127.0.0.1 (contesto
sicuro, come il telefono in HTTPS):
- la pagina si carica senza errori e senza violazioni della CSP (onnxruntime-web con
  'wasm-unsafe-eval', niente CDN), si abbina con il codice come un satellite, scarica i
  modelli con il token e prepara VAD e wake word;
- la wake word nel browser dà gli stessi punteggi del rilevatore Python
  (calliope/wakeword.py) sulla stessa frase sintetizzata, e il VAD le stesse probabilità;
- microfono finto (`--use-file-for-fake-audio-capture`) con una frase **senza** il nome:
  in 12 s non parte un byte verso il server; **con** il nome: la frase arriva intera ad
  AscoltoRemoto con woke vero;
- «Parla» (tocco) senza wake word: la frase parte subito e il server la riceve;
- la voce: una frase mandata da UscitaRemota si riproduce con Web Audio e torna nell'elenco
  «dette per intero» (turno_finito); «Calliope, basta» detto mentre parla la ferma sul
  telefono (barge-in) e il server riceve l'interruzione;
- misure: peso della pagina e dei modelli (byte trasferiti, con gzip), tempo di
  preparazione dei modelli, CPU dell'inferenza nel browser con il microfono acceso.

Servono onnxruntime-web (python -m calliope.stato --installa telefono, in models/web), i
modelli della wake word (wakeword/modelli/) e una voce di Piper per le frasi: se mancano, o
senza Edge né Chromium, la prova si salta (esce con 77 e lo dice). Tutto in una cartella
temporanea; ~60 s.

Dove li cerca (08/10, `risorsa`): CALLIOPE_TELEFONO_MODELLI (la cartella di onnxruntime-web),
poi questa radice, la cartella da cui viene la copia dell'indice (PROVE_ORIGINE, l'hook) e il
repository principale (git --git-common-dir): così un worktree o la copia dell'hook usano i
file installati una volta sola nel principale, senza hard link né junction.
"""

import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-telefono-"))
ERRORI = []
MISURE = {}


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def _radici() -> list[Path]:
    """Dove cercare i file fuori da git: questa radice, l'origine della copia dell'indice
    (PROVE_ORIGINE) e il repository principale di ciascuna (il worktree ne è un ramo)."""
    basi = [RADICE] + ([Path(os.environ["PROVE_ORIGINE"])] if os.environ.get("PROVE_ORIGINE")
                       else [])
    out = list(basi)
    for b in basi:
        try:
            r = subprocess.run(["git", "-C", str(b), "rev-parse", "--git-common-dir"],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and r.stdout.strip():
            comune = Path(r.stdout.strip())
            if not comune.is_absolute():
                comune = b / comune
            out.append(comune.resolve().parent)
    visti = []
    for r in out:
        if r.resolve() not in visti:
            visti.append(r.resolve())
    return visti


def risorsa(rel: str, nomi: tuple[str, ...], env: str | None = None) -> Path:
    """La prima cartella `rel` (es. "models/web") che contiene tutti i `nomi`; la variabile
    d'ambiente `env`, se c'è, vince. Se non c'è da nessuna parte, quella di questa radice
    (la prova poi si salta e lo dice)."""
    if env and os.environ.get(env):
        return Path(os.environ[env])
    for r in _radici():
        if all((r / rel / n).is_file() for n in nomi):
            return r / rel
    return RADICE / rel


ORT_FILE = ("ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm")
WAKE_FILE = ("calliope.onnx", "melspectrogram.onnx", "embedding_model.onnx")
VOCI = ("it_IT-paola-medium.onnx", "it_IT-riccardo-x_low.onnx")


def cartella_web() -> Path:
    return risorsa("models/web", ORT_FILE, "CALLIOPE_TELEFONO_MODELLI")


def cartella_wake() -> Path:
    return risorsa("wakeword/modelli", WAKE_FILE)


def browser() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).is_file():
            return c
    for e in ("msedge", "chromium", "chromium-browser", "google-chrome"):
        if shutil.which(e):
            return shutil.which(e)
    return None


def porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def aspetta(cond, max_s: float, passo: float = 0.2):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


class Pagina:
    """Una scheda del browser: Runtime.evaluate (anche con await) e i messaggi della console,
    gli errori e le violazioni della CSP raccolti dall'inizio."""

    def __init__(self, exe: str, url: str, opzioni=(), profilo="profilo"):
        # Porta di DevTools scelta dal browser e chiusura dell'albero intero (cdp.py, 06/10)
        from cdp import Browser
        self.browser = Browser(exe, TMP / profilo,
                               ("--autoplay-policy=no-user-gesture-required", *opzioni))
        self.dbg = self.browser.porta
        self.proc = self.browser.proc
        try:
            ws_url = self.browser.ws_pagina()
        except RuntimeError:
            self.browser.chiudi()
            raise
        from websockets.sync.client import connect
        self.ws = connect(ws_url, max_size=2 ** 26)
        self.n = 0
        self.log: list[str] = []
        self._lock = threading.Lock()
        for m in ("Runtime.enable", "Log.enable", "Page.enable"):
            self._chiama(m)
        self._chiama("Page.navigate", {"url": url})

    def _chiama(self, metodo, params=None, timeout=60):
        with self._lock:
            self.n += 1
            n = self.n
            self.ws.send(json.dumps({"id": n, "method": metodo, "params": params or {}}))
            fine = time.monotonic() + timeout
            while True:
                m = json.loads(self.ws.recv(timeout=max(0.1, fine - time.monotonic())))
                if m.get("id") == n:
                    return m
                self._evento(m)

    def _evento(self, m):
        meto, p = m.get("method"), m.get("params", {})
        if meto == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            self.log.append("ECCEZIONE " + str(d.get("exception", {}).get("description")
                                               or d.get("text")))
        elif meto == "Runtime.consoleAPICalled" and p.get("type") in ("error", "warning"):
            self.log.append(p["type"].upper() + " " + " ".join(
                str(a.get("value", a.get("description", ""))) for a in p.get("args", [])))
        elif meto == "Log.entryAdded":
            e = p.get("entry", {})
            if e.get("level") in ("error", "warning"):
                self.log.append(f"LOG {e.get('source')} {e.get('text')}")

    def valuta(self, espressione: str, timeout=60):
        m = self._chiama("Runtime.evaluate", {"expression": espressione, "returnByValue": True,
                                              "awaitPromise": True}, timeout)
        r = m.get("result", {})
        if "exceptionDetails" in r:
            raise RuntimeError(str(r["exceptionDetails"].get("exception", {}).get("description")
                                   or r["exceptionDetails"]))
        return r.get("result", {}).get("value")

    def pompa(self, s=0.2):
        """Legge gli eventi arrivati (console, errori) senza chiamare niente."""
        try:
            self.valuta("1", timeout=10)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(s)

    def stato(self) -> dict:
        try:
            return self.valuta("window.calliopeTelefono ? window.calliopeTelefono.stato() : {}") or {}
        except Exception:  # noqa: BLE001
            return {}

    def chiudi(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass
        self.browser.chiudi()


def sintetizza(testi: list[str]) -> dict[str, np.ndarray] | None:
    """Le frasi di «chi parla» con una voce di Piper, a 16 kHz (come prova_satellite)."""
    for nome in VOCI:
        path = risorsa("voices", (nome, nome + ".json")) / nome
        if path.is_file():
            break
    else:
        return None
    from piper import PiperVoice
    voice = PiperVoice.load(str(path))
    out = {}
    for t in testi:
        pcm = b"".join(ch.audio_int16_bytes for ch in voice.synthesize(t))
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        rate = voice.config.sample_rate
        n = int(len(x) * 16000 / rate)
        out[t] = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return out


def scrivi_wav(path: Path, x: np.ndarray, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def scena(frase: np.ndarray, ripeti=4) -> np.ndarray:
    """Silenzio, frase, silenzio… (il browser ripete il file all'infinito)."""
    rumore = np.random.default_rng(1).standard_normal(16000 * 2).astype(np.float32) * 2e-4
    pezzi = []
    for _ in range(ripeti):
        pezzi += [rumore[:16000], frase, rumore]
    return np.concatenate(pezzi)


class Ambiente:
    """Server dei satelliti e degli schermi su 127.0.0.1, come dentro Calliope."""

    def __init__(self):
        from calliope.config import Config
        from calliope.satellite.archivio import ArchivioSatelliti
        from calliope.satellite.server import AscoltoRemoto, ServerSatelliti, UscitaRemota
        from calliope.schermi import ArchivioSchermi, Schermi
        from calliope.schermi.server import ServerSchermi
        cfg = Config()
        cfg.config_dir = str(TMP)
        cfg.memory_db = str(TMP / "memoria.db")
        cfg.satellite_porta = 0
        cfg.audio_modo = "satellite"
        cfg.telefono_web = str(cartella_web())
        cfg.wake_model = str(cartella_wake() / "calliope.onnx")
        self.cfg = cfg
        self.log = []
        self.srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=self.log.append)
        self.srv.avvia()
        self.srv.avviato.set()
        self.hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
        self.web = ServerSchermi(self.hub, "127.0.0.1", porta_libera(), attesa_porta_s=5).avvia()
        self.hub.server = self.web
        self.hub.satelliti = self.srv
        self.srv.schermi = self.hub
        self.hub.stanza_corrente = self.srv.stanza
        self.ascolto = AscoltoRemoto(self.srv, cfg, log=lambda m: None)
        self.uscita = UscitaRemota(self.srv)
        self.url = f"http://127.0.0.1:{self.web.port}"

    def chiudi(self):
        self.web.ferma()
        self.srv.ferma()


def ascolta_in_thread(amb, wake=True, awake_until=0.0, seed=None):
    """AscoltoRemoto.listen come nel ciclo principale, in un thread: {"audio", "woke", …}."""
    r = {}

    def corri():
        a = amb.ascolto.listen(object() if wake else None, awake_until, seed=seed,
                               wakeup=r.setdefault("sveglia", threading.Event()))
        r.update(audio=a, woke=amb.ascolto.woke, punteggio=amb.ascolto.wake_score,
                 fine=time.monotonic())
    r["sveglia"] = threading.Event()
    t = threading.Thread(target=corri, daemon=True)
    t.start()
    r["thread"] = t
    return r


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main() -> int:
    exe = browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    from calliope.schermi import telefono
    from calliope.config import Config
    c = Config()
    c.telefono_web = str(cartella_web())
    c.wake_model = str(cartella_wake() / "calliope.onnx")
    st = telefono.stato(c)
    if not all(st["ort"].values()) or not all(st["modelli"].values()):
        print("Mancano onnxruntime-web (python -m calliope.stato --installa telefono nel "
              "repository principale, o CALLIOPE_TELEFONO_MODELLI) o i modelli della wake word "
              f"(wakeword/modelli/): prova saltata. Cercati in {c.telefono_web} e "
              f"{Path(c.wake_model).parent}.")
        return SALTATA
    frasi = sintetizza(["Calliope, che ore sono?", "Che tempo fa domani a Milano?",
                        "Calliope, basta."])
    if frasi is None:
        print("Nessuna voce di Piper in voices/: prova saltata.")
        return SALTATA
    con_nome = scena(frasi["Calliope, che ore sono?"])
    senza_nome = scena(frasi["Che tempo fa domani a Milano?"])
    scrivi_wav(TMP / "con_nome.wav", con_nome)
    scrivi_wav(TMP / "senza_nome.wav", senza_nome)
    scrivi_wav(TMP / "basta.wav", scena(frasi["Calliope, basta."]))

    amb = Ambiente()
    try:
        parte_pagina(exe, amb, frasi)
    finally:
        amb.chiudi()
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nMisure: " + json.dumps(MISURE, ensure_ascii=False))
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


def abbina_pagina(amb, pagina) -> bool:
    """Dalla pagina: nome, «Chiedi il codice», codice letto e abbinato «da terminale»."""
    pagina.valuta("document.getElementById('tel-nome').value='Dario';"
                  "document.getElementById('tel-chiedi').click(); 1")
    cod = aspetta(lambda: (pagina.valuta("document.getElementById('tel-codice-cifre')"
                                         ".textContent") or "").replace(" ", ""), 10)
    comando = pagina.valuta("document.getElementById('tel-comando').textContent") or ""
    verifica("abbinamento: la pagina mostra codice e comando con --personale",
             bool(cod) and len(cod) == 6 and f"--abbina {cod}" in comando
             and "--personale Dario" in comando, comando)
    if not cod:
        return False
    res = amb.srv.archivio.abbina(cod, "telefono")
    verifica("il server vede la richiesta di schermo personale (da confermare)",
             res["ok"] and res.get("personale_chiesto") == "Dario")
    return True


def parte_pagina(exe, amb, frasi):
    # ── 1. pagina, abbinamento, modelli (microfono finto senza il nome) ──
    opz = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
           f"--use-file-for-fake-audio-capture={TMP / 'senza_nome.wav'}")
    pagina = Pagina(exe, amb.url + "/telefono/", opz, profilo="p1")
    try:
        aspetta(lambda: pagina.valuta("!!window.calliopeTelefono"), 15)
        verifica("pagina caricata (moduli, schermo.js incorporato)",
                 pagina.valuta("!!window.calliopeTelefono && !!window.calliopeSchermo") is True)
        if not abbina_pagina(amb, pagina):
            return
        t = aspetta(lambda: pagina.stato().get("collegato"), 15)
        verifica("dopo l'abbinamento la pagina si collega come satellite", bool(t))
        aspetta(lambda: pagina.stato().get("modelli") in ("pronti", "errore"), 60)
        s = pagina.stato()
        verifica("modelli scaricati con il token e pronti (VAD e wake word)",
                 s.get("modelli") == "pronti", str(s.get("erroreModelli")))
        MISURE["preparazione_modelli_s"] = round((s.get("tempoModelli") or 0) / 1000, 2)
        verifica("schede: la pagina riceve un token di schermo e si collega all'SSE",
                 aspetta(lambda: amb.hub.collegati(), 10) is not None)
        verifica("schermo del telefono nella stanza «telefono»",
                 any(x["stanza"] == "telefono" for x in amb.hub.abbinati()))
        # Peso: le risorse che la pagina ha chiesto, riscaricate qui con gzip e senza proxy
        # (un programma di sicurezza sul PC può decomprimere le risposte prima del browser:
        # «x-content-encoding-over-network: gzip», visto il 03/10), così i byte sono quelli
        # che viaggiano davvero verso il telefono
        nomi = pagina.valuta("[location.href, ...performance.getEntriesByType('resource')"
                             ".map(e => e.name)]")
        senza_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        pesi = {}
        for u in dict.fromkeys(nomi):
            if not u.startswith(amb.url) or "/eventi" in u or "/api/" in u:
                continue
            h = {"Accept-Encoding": "gzip"}
            if "/modelli/" in u:
                h["Authorization"] = "Bearer " + str(pagina.valuta(
                    "localStorage.getItem('calliope.telefono.token')"))
            with senza_proxy.open(urllib.request.Request(u, headers=h)) as r:
                pesi[u] = (len(r.read()), r.headers.get("Content-Encoding"))
        modelli = sum(n for u, (n, _) in pesi.items() if "/modelli/" in u or "/ort/" in u)
        MISURE["byte_pagina_kB"] = round((sum(n for n, _ in pesi.values()) - modelli) / 1024)
        MISURE["byte_modelli_e_ort_MB"] = round(modelli / 2 ** 20, 2)
        wasm = [(n, enc) for u, (n, enc) in pesi.items() if u.split("?")[0].endswith(".wasm")]
        verifica("WebAssembly di onnxruntime compresso (gzip) dal server",
                 bool(wasm) and wasm[0][1] == "gzip" and wasm[0][0] < 5 * 2 ** 20,
                 f"{wasm[0][0]} byte" if wasm else "non scaricato")

        # ── 2. stessi numeri del Python ──
        from calliope.wakeword import WakeWordDetector
        from calliope.vad import SileroOnnx, modello_onnx
        x = frasi["Calliope, che ore sono?"]
        x = np.concatenate([np.zeros(32000, np.float32), x, np.zeros(8000, np.float32)])
        det = WakeWordDetector(amb.cfg.wake_model)
        py = []
        for i in range(0, len(x) - 1279, 1280):
            s_ = det.process(x[i:i + 1280])
            if s_ is not None:
                py.append(s_)
        js = pagina.valuta("window.calliopeTelefono.provaWake(new Float32Array("
                           + json.dumps([round(float(v), 6) for v in x]) + "))", timeout=120)
        # Il riscaldamento usa un rumore diverso (il generatore di numpy non c'è nel
        # browser): differenze di qualche centesimo solo dove il punteggio cambia in fretta
        diff = max(abs(a - b) for a, b in zip(py, js)) if js else 1.0
        media = float(np.mean([abs(a - b) for a, b in zip(py, js)])) if js else 1.0
        sopra = lambda v: [i for i, s_ in enumerate(v) if s_ >= amb.cfg.wake_threshold]  # noqa: E731
        verifica("wake word nel browser = rilevatore Python (stessi scatti, stessi punteggi)",
                 js is not None and len(js) == len(py) and sopra(py) == sopra(js) and media < 0.01,
                 f"max Python {max(py):.3f}, browser {max(js or [0]):.3f}, differenza media "
                 f"{media:.4f}, massima {diff:.3f}")
        y = frasi["Che tempo fa domani a Milano?"]
        js2 = pagina.valuta("window.calliopeTelefono.provaWake(new Float32Array("
                            + json.dumps([round(float(v), 6) for v in y]) + "))", timeout=120)
        verifica("wake word nel browser: frase senza il nome sotto soglia",
                 js2 is not None and max(js2) < amb.cfg.wake_threshold, f"max {max(js2 or [0]):.3f}")
        vad = SileroOnnx(modello_onnx())
        pv = [vad.prob(x[i:i + 512]) for i in range(0, len(x) - 511, 512)]
        jv = pagina.valuta("window.calliopeTelefono.provaVad(new Float32Array("
                           + json.dumps([round(float(v), 6) for v in x]) + "))", timeout=120)
        dv = max(abs(a - b) for a, b in zip(pv, jv)) if jv else 1.0
        verifica("Silero VAD nel browser = Python", jv is not None and dv < 0.02,
                 f"differenza massima {dv:.4f}")

        # ── 3. microfono acceso, frase senza il nome: niente esce ──
        r = ascolta_in_thread(amb, wake=True, awake_until=0.0)
        verifica("il telefono è il satellite attivo", aspetta(
            lambda: amb.srv.attivo_pronto() is not None, 5) is not None)
        pagina.valuta("window.calliopeTelefono.impostaMic(true).then(() => 1)")
        acceso = aspetta(lambda: pagina.stato().get("mic"), 10)
        verifica("microfono acceso (finto) e wake word in ascolto", bool(acceso),
                 str(pagina.stato()))
        pagina.valuta("(() => { const m = window.calliopeTelefono.misure; m.inferenzaMs = 0; "
                      "m.inferenze = 0; m.dal = performance.now(); return 1; })()")
        t0 = time.monotonic()
        time.sleep(12)
        s = pagina.stato()
        coll = amb.srv.attivo_pronto()
        verifica("da addormentata, frase senza il nome: 0 byte verso il server",
                 s.get("inviato") == 0 and r.get("audio") is None,
                 f"inviati {s.get('inviato')}")
        MISURE["cpu_inferenza_browser_pct"] = round(100 * float(pagina.valuta(
            "(() => { const m = window.calliopeTelefono.misure; return m.inferenzaMs / "
            "(performance.now() - m.dal); })()") or 0), 1)
        MISURE["blocchi_al_secondo"] = round(float(pagina.valuta(
            "window.calliopeTelefono.misure.inferenze") or 0) / max(1, time.monotonic() - t0), 1)
        r["sveglia"].set()                         # il ciclo principale «annuncia»
        verifica("«sveglia» del server: il telefono risponde subito (nessuna frase)",
                 aspetta(lambda: r.get("fine"), 5) is not None and r.get("audio") is None)
        pagina.valuta("window.calliopeTelefono.impostaMic(false).then(() => 1)")
        if coll is not None:
            verifica("nessun audio ricevuto dal server mentre dormiva", coll.ricevuti < 2000,
                     f"{coll.ricevuti} byte (solo testo)")
    finally:
        for riga in pagina.log:
            print("   [browser] " + riga)
        csp = [r for r in pagina.log if "Content Security Policy" in r or "CSP" in r]
        verifica("nessuna violazione della CSP", not csp, "; ".join(csp)[:300])
        errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR"))]
        verifica("nessun errore JavaScript", not errori, "; ".join(errori)[:300])
        pagina.chiudi()

    # ── 4. con il nome: la frase arriva intera; poi la voce e il barge-in ──
    opz = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
           f"--use-file-for-fake-audio-capture={TMP / 'con_nome.wav'}")
    # Stesso profilo: il token è nel localStorage della pagina
    pagina = Pagina(exe, amb.url + "/telefono/", opz, profilo="p1")
    try:
        verifica("riaperta: si ricollega da sola con il token salvato",
                 aspetta(lambda: pagina.stato().get("collegato"), 15) is not None)
        aspetta(lambda: pagina.stato().get("modelli") in ("pronti", "errore"), 30)
        verifica("riaperta: i modelli vengono dalla cache del browser",
                 (pagina.stato().get("tempoModelli") or 99999) < MISURE.get(
                     "preparazione_modelli_s", 99) * 1000 + 1)
        r = ascolta_in_thread(amb, wake=True, awake_until=0.0)
        pagina.valuta("window.calliopeTelefono.impostaMic(true).then(() => 1)")
        fine = aspetta(lambda: r.get("fine"), 25)
        a = r.get("audio")
        verifica("con il nome: la frase arriva al server con woke vero",
                 fine is not None and a is not None and r.get("woke") and len(a) > 16000,
                 f"{len(a) / 16000:.1f} s, punteggio {r.get('punteggio'):.2f}"
                 if a is not None else "niente")
        # La voce di Calliope: una frase lunga, poi «Calliope, basta» (il file ripete il nome)
        frase = frasi["Che tempo fa domani a Milano?"]
        pcm = (np.tile(frase, 6) * 32767).astype("<i2").tobytes()
        voce = {}

        def veglia():
            stop = threading.Event()
            voce["stop"] = stop
            voce["seme"] = amb.ascolto.watch_for_name(object(), stop, lambda: False)
            voce["fine"] = time.monotonic()
        amb.uscita.invia(1, "Domani a Milano sole e venti deboli.", pcm, 16000)
        threading.Thread(target=veglia, daemon=True).start()
        sentita = aspetta(lambda: voce.get("fine"), 30)
        verifica("barge-in: «Calliope…» mentre parla la ferma sul telefono",
                 sentita is not None and bool(voce.get("seme")))
        ferma = pagina.valuta("window.calliopeTelefono.player.inCorso()")
        verifica("barge-in: la riproduzione sul telefono è ferma", ferma is False)
        amb.uscita.ferma(1)
        dette = amb.uscita.fine_turno()
        verifica("turno interrotto: nessuna frase detta per intero", dette == [], str(dette))
        pagina.valuta("window.calliopeTelefono.impostaMic(false).then(() => 1)")
        # Una frase breve, ascoltata fino in fondo
        corta = (frasi["Calliope, basta."][:16000] * 32767).astype("<i2").tobytes()
        amb.uscita.invia(2, "Sono le dieci.", corta, 16000)
        dette = amb.uscita.fine_turno()
        verifica("voce: la frase si riproduce e torna tra le «dette per intero»",
                 dette == ["Sono le dieci."], str(dette))
        # «Parla» senza microfono acceso: la frase parte dal tocco, senza nome
        r = ascolta_in_thread(amb, wake=True, awake_until=0.0)
        time.sleep(0.5)
        pagina.valuta("window.calliopeTelefono.tocca(); 1")
        fine = aspetta(lambda: r.get("fine"), 20)
        a = r.get("audio")
        verifica("«Parla»: la frase arriva al server (vale come il nome)",
                 fine is not None and a is not None and r.get("woke")
                 and r.get("punteggio") == 1.0,
                 f"{len(a) / 16000:.1f} s" if a is not None else "niente")
    finally:
        for riga in pagina.log:
            print("   [browser] " + riga)
        errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR"))]
        verifica("nessun errore JavaScript (seconda apertura)", not errori, "; ".join(errori)[:300])
        pagina.chiudi()


if __name__ == "__main__":
    sys.exit(main())
