"""
La frase lunga (10/10/2026, caso vero della DGX alle 17:32, satellite «studio»: una dettatura
delle regole di un gioco tagliata a 30,02 s dal tetto `max_utterance_s`, con Calliope partita
mentre la persona parlava ancora e il resto in un turno nuovo).

    python prove/prova_frase_lunga.py

- configurazione: il tetto a 120 s (il 30 di prima era la causa), intervallo ammesso; il tempo
  massimo della richiesta a whisper-server in proporzione alla frase (`tempo_massimo`), e per
  una frase normale il client com'è;
- `audio.Listener` con un microfono e un VAD finti e frame tutti diversi: al tetto la frase si
  chiude «lunga» e l'ascolto subito dopo riprende dal frame seguente, senza doppioni né buchi;
  contrario: una frase chiusa dal silenzio lascia il pre-roll com'era;
- `Ciclo._seguito_del_tetto` con un ascolto finto: pezzi uniti (inizio del primo, wake word,
  pause, parlato), nessuno che continua entro `TETTO_ATTESA_S` (la frase vale com'è, l'attesa
  rispettata), rumore continuo fermato dopo `TETTO_SEGUITI` seguiti («tagliata»), contrario:
  una frase chiusa dal silenzio non ascolta altro;
- un giro intero del ciclo (impianto di prova_ciclo): un turno solo, una richiesta al modello
  con il testo dei due pezzi, regola `frase_tetto` e campo «tetto» nel registro; contrario:
  frase normale senza regola;
- satellite finto su un server dei satelliti vero (WebSocket): il seguito chiesto con un
  ascolto nuovo e unito; nessuno che continua → «sveglia» e la frase com'è; `fa_s` oltre 120;
- il satellite in Python non suona la fine ascolto al tetto (contrario: al silenzio sì);
- il telefono: tetto di riserva 120, niente suono di fine al tetto in `telefono.js`, e `voce.js`
  (con node) che al tetto riprende dal blocco dopo, senza doppioni né buchi.
Niente modelli né rete esterna: ~6 s.
"""
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from calliope import pause  # noqa: E402
from calliope.config import Config  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""),
          flush=True)


# ─────────────────────────── configurazione e STT ───────────────────────────
def prova_config():
    from calliope import config as cmod
    cfg = Config()
    verifica("tetto della frase a 120 s (era 30: la causa del caso vero)",
             cfg.max_utterance_s == 120, cfg.max_utterance_s)
    verifica("tetto nell'intervallo ammesso (5–600)",
             cmod.LIMITI.get("max_utterance_s") == (5, 600), cmod.LIMITI.get("max_utterance_s"))
    testo = (RADICE / "calliope.yaml").read_text(encoding="utf-8")
    verifica("calliope.yaml rigenerato con il tetto nuovo", "max_utterance_s: 120" in testo)

    from calliope.stt import ServerTranscriber
    chiamate = []

    class Http:
        def post(self, url, files=None, data=None, **kw):
            chiamate.append(kw)
            return types.SimpleNamespace(raise_for_status=lambda: None,
                                         json=lambda: {"text": "ciao"})

    cfg.stt_motore, cfg.stt_url, cfg.stt_timeout_s = "server", "http://127.0.0.1:9/v1", 5.0
    s = ServerTranscriber(cfg, http=Http())
    sr = cfg.sample_rate
    tm = [s.tempo_massimo(np.zeros(int(x * sr), np.float32)) for x in (3, 15, 30, 120, 360)]
    verifica("tempo massimo: 5 s fino a 15 s di frase, poi in proporzione (30 → 10, 120 → 40)",
             tm == [5.0, 5.0, 10.0, 40.0, 120.0], tm)
    chiamate.clear()
    s.transcribe(np.zeros(3 * sr, np.float32))
    verifica("frase normale: la richiesta con il client com'è (nessun tempo in più)",
             chiamate == [{}], chiamate)
    s.transcribe(np.zeros(90 * sr, np.float32))
    t = (chiamate[-1] or {}).get("timeout")
    verifica("dettatura di 90 s: tempo massimo 30 s passato a httpx",
             t is not None and abs(t.read - 30.0) < 1e-6, t)


# ─────────────────────────── Listener con microfono finto ───────────────────────────
MIC: queue.Queue = queue.Queue()


class MicFinto:
    def __init__(self, samplerate, channels, dtype, blocksize, device, callback):
        self.cb, self.n, self._stop = callback, blocksize, threading.Event()

    def start(self):
        def gira():
            while not self._stop.is_set():
                try:
                    f = MIC.get_nowait()
                except queue.Empty:
                    f = np.zeros(self.n, np.float32)
                self.cb(f.reshape(-1, 1), self.n, None, None)
                time.sleep(0.003)
        threading.Thread(target=gira, daemon=True).start()

    def abort(self):
        self._stop.set()

    close = abort


class VadFinto:
    def prob(self, frame):
        return 1.0 if np.max(np.abs(frame)) > 0.05 else 0.0

    def reset_states(self):
        pass


def voce(i):
    """Il frame di voce numero i: un valore suo, per riconoscere doppioni e buchi."""
    return np.full(512, 0.1 + i * 1e-4, np.float32)


def numeri(audio):
    f = audio.reshape(-1, 512)[:, 0]
    return [int(round((x - 0.1) / 1e-4)) for x in f if x > 0.05]


def prova_listener():
    from calliope.audio import Listener
    cfg = Config()
    cfg.silence_ms, cfg.min_speech_ms, cfg.max_utterance_s = 300, 100, 1
    L = Listener(cfg, sorgente=MicFinto)
    L.model, L.misura_ripresa = VadFinto(), False
    try:
        pezzi, out = [], {}

        def due_ascolti():
            for _ in range(3):
                a = L.listen()
                pezzi.append((a, L.chiusura))
                if L.chiusura != "lunga":
                    break
            out["fatto"] = True
        th = threading.Thread(target=due_ascolti, daemon=True)
        th.start()
        fine = time.monotonic() + 3
        while not L.active and time.monotonic() < fine:
            time.sleep(0.01)
        for i in range(1, 51):              # 50 frame di voce di fila (1,6 s), poi silenzio
            MIC.put(voce(i))
        for _ in range(20):
            MIC.put(np.zeros(512, np.float32))
        th.join(10)
        chiusure = [c for _, c in pezzi]
        verifica("al tetto la frase si chiude «lunga», il seguito al silenzio",
                 chiusure == ["lunga", "silenzio"], chiusure)
        n = [x for a, _ in pezzi for x in numeri(a)]
        verifica("pezzi uniti: tutta la voce, in ordine, senza doppioni né buchi",
                 n == list(range(1, 51)), n)
        # Contrario: chiusa dal silenzio, il pre-roll resta quello di sempre
        L._recent.clear()
        L._recent.extend([voce(900)] * 3)
        chiamato = []
        orig = L._dopo_il_tetto
        L._dopo_il_tetto = lambda: chiamato.append(1) or orig()
        th = threading.Thread(target=lambda: out.setdefault("a", L.listen()), daemon=True)
        th.start()
        fine = time.monotonic() + 3
        while not L.active and time.monotonic() < fine:
            time.sleep(0.01)
        for i in range(1, 11):
            MIC.put(voce(i))
        for _ in range(15):
            MIC.put(np.zeros(512, np.float32))
        th.join(10)
        verifica("contrario: frase chiusa dal silenzio, nessuna preparazione del seguito",
                 L.chiusura == "silenzio" and not chiamato, (L.chiusura, chiamato))
        L._dopo_il_tetto = orig

        # Il reset della wake word lento (14/10, prova_stanza_voce sotto carico: ~50 ms, sotto
        # carico oltre i 300 ms del pre-roll): la voce che comincia appena si chiama listen()
        # aspetta in coda, nessun frame si perde. Prima la coda si apriva dopo il reset e
        # restavano solo gli ultimi 300 ms
        class WakeLenta:
            def reset(self):
                time.sleep(0.6)

            def process(self, frame):
                return 0.0
        L._recent.clear()
        out.pop("a", None)
        th = threading.Thread(target=lambda: out.setdefault("a", L.listen(WakeLenta())),
                              daemon=True)
        th.start()
        for i in range(1, 21):              # 0,64 s: sotto il tetto di 1 s
            MIC.put(voce(i))
        for _ in range(15):
            MIC.put(np.zeros(512, np.float32))
        th.join(10)
        n = numeri(out["a"]) if out.get("a") is not None else None
        verifica("reset lento della wake word: la frase detta subito arriva intera",
                 n == list(range(1, 21)), n)
    finally:
        L.stream.abort()


# ─────────────────────────── il ciclo: _seguito_del_tetto ───────────────────────────
class AscoltoFinto:
    """Restituisce i pezzi in coda: (audio, chiusura, pause, parlato, woke, punteggio), oppure
    None = nessuno parla (aspetta `wakeup` come Listener)."""

    def __init__(self, pezzi):
        self.pezzi, self.chiamate = list(pezzi), []
        self.started_at = self.ended_at = 0.0
        self.woke, self.wake_score = False, 0.0
        self.pause_ms, self.parlato_ms, self.chiusura = [], None, None
        self.on_speech_start = self.on_speech_end = None

    def listen(self, wake=None, awake_until=float("inf"), seed=None, wakeup=None):
        self.chiamate.append({"wake": wake, "resto": awake_until - time.monotonic(),
                              "wakeup": wakeup, "t": time.monotonic()})
        p = self.pezzi.pop(0) if self.pezzi else None
        if p is None:
            if wakeup is not None:
                wakeup.wait(10)
            return None
        audio, chiusura, pause_ms, parlato, woke, score = p
        self.started_at = time.monotonic() - len(audio) / 16000
        self.ended_at = time.monotonic()
        self.chiusura, self.pause_ms, self.parlato_ms = chiusura, pause_ms, parlato
        self.woke, self.wake_score = woke, score
        return audio


def ciclo_con(ascolto):
    from calliope.ciclo import Ciclo
    c = object.__new__(Ciclo)
    c.listener = ascolto
    c.s = types.SimpleNamespace(cfg=Config(), wake="RILEVATORE")
    return c


def prova_seguito():
    t = types.SimpleNamespace(guided=False)
    a1, a2 = np.full(1600, 0.2, np.float32), np.full(800, 0.3, np.float32)
    asc = AscoltoFinto([(a2, "silenzio", [300], 400, False, 0.2)])
    c = ciclo_con(asc)
    asc.started_at, asc.woke, asc.wake_score = 100.0, True, 0.9
    asc.chiusura, asc.pause_ms, asc.parlato_ms = "lunga", [200, 250], 1000
    audio, tetto = c._seguito_del_tetto(t, a1)
    verifica("tetto: il seguito ascoltato subito e unito prima di Whisper",
             len(audio) == 2400 and np.all(audio[:1600] == 0.2) and np.all(audio[1600:] == 0.3)
             and tetto == {"pezzi": 2, "tagliata": False}, (len(audio), tetto))
    ch = asc.chiamate[0]
    verifica("…con la wake word e la finestra di TETTO_ATTESA_S (una frase che continua è "
             "per Calliope)", ch["wake"] == "RILEVATORE"
             and 0 < ch["resto"] <= pause.TETTO_ATTESA_S and ch["wakeup"] is not None, ch)
    verifica("…la frase unita: inizio del primo pezzo, nome sentito, pause e parlato sommati",
             asc.started_at == 100.0 and asc.woke is True and asc.wake_score == 0.9
             and asc.pause_ms == [200, 250, 300] and asc.parlato_ms == 1400
             and asc.chiusura == "silenzio",
             (asc.started_at, asc.woke, asc.pause_ms, asc.parlato_ms))

    # Nessuno continua: dopo TETTO_ATTESA_S la frase vale com'è
    vecchio = pause.TETTO_ATTESA_S
    pause.TETTO_ATTESA_S = 0.3
    try:
        asc = AscoltoFinto([None])
        asc.chiusura, asc.started_at = "lunga", 50.0
        c = ciclo_con(asc)
        t0 = time.monotonic()
        audio, tetto = c._seguito_del_tetto(t, a1)
        dt = time.monotonic() - t0
        verifica("nessuno continua: la frase com'è, dopo l'attesa (0,3 s nella prova)",
                 len(audio) == 1600 and tetto == {"pezzi": 1, "tagliata": False}
                 and 0.25 <= dt < 2.0 and asc.started_at == 50.0, (tetto, round(dt, 2)))

        # Rumore continuo: al più TETTO_SEGUITI seguiti, poi «tagliata»
        lungo = (np.full(100, 0.1, np.float32), "lunga", [], 100, False, 0.0)
        asc = AscoltoFinto([lungo] * 10)
        asc.chiusura = "lunga"
        c = ciclo_con(asc)
        audio, tetto = c._seguito_del_tetto(t, a1)
        verifica(f"rumore continuo: al più {pause.TETTO_SEGUITI} seguiti, poi la frase vale "
                 f"com'è («tagliata»)",
                 len(asc.chiamate) == pause.TETTO_SEGUITI
                 and tetto == {"pezzi": pause.TETTO_SEGUITI + 1, "tagliata": True},
                 (len(asc.chiamate), tetto))

        # Registrazione della voce (guided): il seguito senza la wake word
        asc = AscoltoFinto([(a2, "silenzio", [], 100, False, 0.0)])
        asc.chiusura = "lunga"
        ciclo_con(asc)._seguito_del_tetto(types.SimpleNamespace(guided=True), a1)
        verifica("durante la registrazione della voce il seguito si ascolta senza wake word",
                 asc.chiamate[0]["wake"] is None)
    finally:
        pause.TETTO_ATTESA_S = vecchio

    # Contrario: frase chiusa dal silenzio
    asc = AscoltoFinto([(a2, "silenzio", [], 1, False, 0.0)])
    asc.chiusura = "silenzio"
    audio, tetto = ciclo_con(asc)._seguito_del_tetto(t, a1)
    verifica("contrario: frase chiusa dal silenzio, nessun altro ascolto",
             tetto is None and len(audio) == 1600 and not asc.chiamate)
    asc = AscoltoFinto([])
    del asc.chiusura                         # un ascolto senza misure (vecchio, finto)
    audio, tetto = ciclo_con(asc)._seguito_del_tetto(t, a1)
    verifica("contrario: ascolto senza «chiusura», come prima", tetto is None)


# ─────────────────────────── un giro intero del ciclo ───────────────────────────
def prova_giro():
    import prova_ciclo as pc
    from calliope import corsie
    from calliope.ciclo import Ciclo, Servizi
    from calliope.cortesia import Cortesia
    cfg = Config()
    cfg.speaker_id_enabled = cfg.barge_in_enabled = False
    cfg.debug_audio_dir = None
    cfg.uscita_controllo = False
    cfg.wake_word_enabled = False            # ascolta senza il nome: conta solo il tetto

    class Whisper:
        def __init__(self):
            self.audio = []

        def transcribe(self, audio):
            self.audio.append(len(audio))
            return f"Frase di {len(audio) // 16000} secondi."

    turni = []
    stt, voce_, cervello = Whisper(), pc.Voce(), pc.Cervello()
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=pc.Persone(), stt=stt, instradamento=instr,
                  cortesia=Cortesia(), turns=types.SimpleNamespace(
                      write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, biblioteca=object(), enroll_pending=False)
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    asc = AscoltoFinto([(np.zeros(16000 * 120, np.float32), "lunga", [400], 119000, False, 0),
                        (np.zeros(16000 * 20, np.float32), "silenzio", [300], 19000, False, 0),
                        (np.zeros(16000 * 3, np.float32), "silenzio", [], 2500, False, 0)])
    chi = pc.ChiParla()
    chi.current_speaker = "Dario"
    c = Ciclo(srv, corsie.Corsia("locale"), asc, voce_, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())
    c.giro()
    rec = dict(c.rec or {})
    verifica("giro: una sola trascrizione, dei due pezzi uniti (140 s)",
             stt.audio == [16000 * 140], stt.audio)
    verifica("giro: una sola richiesta al modello, con il testo intero",
             [r[0] for r in cervello.richieste] == ["Frase di 140 secondi."],
             cervello.richieste)
    verifica("giro: regola frase_tetto e «tetto» nel campo «ascolto» del registro",
             "frase_tetto" in rec.get("regole", [])
             and rec.get("ascolto", {}).get("tetto") == {"pezzi": 2, "tagliata": False}
             and rec.get("durata_s") == 140.0, str(rec)[:400])
    c.giro()
    rec = dict(c.rec or {})
    verifica("contrario: la frase dopo, normale, senza regola né «tetto»",
             "frase_tetto" not in rec.get("regole", []) and "tetto" not in rec.get("ascolto", {})
             and stt.audio[-1] == 16000 * 3, str(rec)[:300])


# ─────────────────────────── satellite finto, server vero ───────────────────────────
def prova_satellite():
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import AscoltoRemoto, ServerSatelliti, valida_evento
    verifica("frase_finita: fa_s oltre 120 s accettato (frase al tetto di 120 s)",
             valida_evento("frase_finita", {"id": 1, "fa_s": 121.5})["fa_s"] == 121.5)
    tmp = Path(tempfile.mkdtemp(prefix="calliope-frase-lunga-"))
    cfg = Config()
    cfg.config_dir, cfg.memory_db, cfg.satellite_porta = str(tmp), str(tmp / "m.db"), 0
    cfg.wake_model = str(tmp / "manca.onnx")
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=lambda *a: None).avvia()
    srv.avviato.set()
    _, tok = arch.crea_con_token("studio")
    ws = connect(f"ws://127.0.0.1:{srv.port}{P.PERCORSO_AUDIO}", compression=None)
    vecchio = pause.TETTO_ATTESA_S
    try:
        ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=tok, primo=False))
        while P.leggi(ws.recv(timeout=5)).get("tipo") != "benvenuto":
            pass
        ws.send(P.testo(tipo="pronto", eco=0.0))
        asc = AscoltoRemoto(srv, cfg)

        def attendi(tipo):
            while True:
                m = ws.recv(timeout=5)
                if isinstance(m, str) and P.leggi(m).get("tipo") == tipo:
                    return P.leggi(m)

        def frase(lid, n, chiusura):
            ws.send(P.binario(P.AUDIO, lid, b"\x00\x10" * n))
            ws.send(P.testo(tipo="frase_finita", id=lid, fa_s=121.0, woke=True,
                            wake_score=0.9, chiusura=chiusura, pause_ms=[300],
                            parlato_ms=n // 16))

        def giro_satellite(seguito: bool):
            out = {}
            c = ciclo_con(asc)
            t = types.SimpleNamespace(guided=False)

            def lato_server():
                a = asc.listen(None)
                out["r"] = c._seguito_del_tetto(t, a)
            th = threading.Thread(target=lato_server, daemon=True)
            th.start()
            m1 = attendi("ascolta")
            frase(m1["id"], 16000, "lunga")
            m2 = attendi("ascolta")
            out["m2"] = m2
            if seguito:
                frase(m2["id"], 8000, "silenzio")
            else:
                out["sveglia"] = attendi("sveglia")
                ws.send(P.testo(tipo="nessuna_frase", id=m2["id"]))
            th.join(10)
            return out

        out = giro_satellite(True)
        audio, tetto = out.get("r", (None, None))
        m2 = out["m2"]
        verifica("satellite: dopo la frase al tetto il server chiede subito il seguito, con "
                 "la finestra breve", 0 < float(m2.get("sveglia_per_s") or 0)
                 <= pause.TETTO_ATTESA_S, m2)
        verifica("satellite: il seguito unito alla frase (un turno solo)",
                 audio is not None and len(audio) == 24000
                 and tetto == {"pezzi": 2, "tagliata": False} and asc.chiusura == "silenzio",
                 (None if audio is None else len(audio), tetto))
        pause.TETTO_ATTESA_S = 0.3
        out = giro_satellite(False)
        audio, tetto = out.get("r", (None, None))
        verifica("satellite: nessuno continua → «sveglia» al satellite e la frase com'è",
                 out.get("sveglia") is not None and audio is not None and len(audio) == 16000
                 and tetto == {"pezzi": 1, "tagliata": False},
                 (out.get("sveglia"), tetto))
    finally:
        pause.TETTO_ATTESA_S = vecchio
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass
        srv.ferma() if hasattr(srv, "ferma") else None
        shutil.rmtree(tmp, ignore_errors=True)


def prova_client():
    """Il satellite in Python: al tetto niente suono di fine ascolto (la persona parla)."""
    from calliope.satellite.client import Satellite
    suoni = []

    class ListenerFinto:
        started_at, woke, wake_score = 0.0, True, 0.9
        pause_ms, parlato_ms, chiusura = [], 900, "lunga"
        on_audio = on_speech_end = ripresa_muto = ripresa_avviso = None

        def listen(self, *a, **k):
            self.started_at = time.monotonic() - 1
            return np.zeros(16000, np.float32)

        def ferma_ripresa(self):
            pass

    s = object.__new__(Satellite)
    s.listener = ListenerFinto()
    s._seed, s.wake, s._wakeup = None, None, threading.Event()
    s.traccia, s.frasi_inviate, s.ascolti = [], 0, []
    mandati = []
    s._manda = lambda **c: mandati.append(c)
    s._suona = suoni.append
    s.player = types.SimpleNamespace(occupato=lambda: False, frase=lambda *a: None)
    s._ascolta({"id": 3})
    ff = [m for m in mandati if m["tipo"] == "frase_finita"]
    verifica("satellite in Python: al tetto la frase parte, senza il suono di fine",
             suoni == [] and ff and ff[0]["chiusura"] == "lunga", (suoni, ff))
    s.listener.chiusura = "silenzio"
    s._ascolta({"id": 4})
    verifica("contrario: chiusa dal silenzio, il suono di fine come sempre", suoni == ["fine"],
             suoni)


JS_PROVA = r"""
const { Ascolto } = await import(process.argv[2]);
const p = { preroll_ms: 300, vad_threshold: 0.5, silence_ms: 300, min_speech_ms: 100,
  max_utterance_s: 1, wake_threshold: 0.5, wake_consecutive: 2 };
const a = new Ascolto(p);
a.vad = { prob: async (f) => (f[0] > 0.05 ? 1 : 0), reset() {} };
const voce = (i) => new Float32Array(512).fill(0.1 + i * 1e-4);
const numeri = (r) => r.audio.map((f) => f[0]).filter((x) => x > 0.05)
  .map((x) => Math.round((x - 0.1) / 1e-4));
// I frame arrivano uno alla volta, come dal microfono: la persona parla oltre il tetto (32
// frame) e l'ascolto dopo riparte appena il primo finisce
const dorme = () => new Promise((ok) => setTimeout(ok, 2));
let r1 = null;
const pr = a.listen({ wake: false, fino: Infinity }).then((r) => { r1 = r; });
let i = 1;
while (r1 === null && i <= 60) { a.push(voce(i++)); await dorme(); }
await pr;
const pr2 = a.listen({ wake: false, fino: Infinity });
while (i <= 50) { a.push(voce(i++)); await dorme(); }
for (let k = 0; k < 15; k++) { a.push(new Float32Array(512)); await dorme(); }
const r2 = await pr2;
console.log(JSON.stringify({ c1: r1.chiusura, c2: r2.chiusura,
  n: numeri(r1).concat(numeri(r2)) }));
"""


def prova_telefono():
    import json
    import subprocess
    pag = RADICE / "calliope" / "schermi" / "pagina" / "telefono"
    js = (pag / "telefono.js").read_text(encoding="utf-8")
    verifica("telefono: tetto di riserva 120 s, come il server", "max_utterance_s: 120," in js)
    verifica("telefono: niente suono di fine al tetto",
             'if (r.chiusura !== "lunga") { st.pensa = true; suona("fine"); }' in js)
    node = shutil.which("node")
    if not node:
        print("SALTATA IN PARTE: node non c'è: il seguito di voce.js non si esegue")
        return
    tmp = Path(tempfile.mkdtemp(prefix="calliope-frase-lunga-js-"))
    try:
        mod = tmp / "voce.mjs"
        mod.write_text((pag / "voce.js").read_text(encoding="utf-8"), encoding="utf-8")
        script = tmp / "prova.mjs"
        script.write_text(JS_PROVA, encoding="utf-8")
        r = subprocess.run([node, str(script), mod.as_uri()], capture_output=True, text=True,
                           timeout=60, encoding="utf-8")
        try:
            d = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            d = {}
        verifica("voce.js (node): al tetto «lunga», il seguito dal frame dopo, senza doppioni "
                 "né buchi", d.get("c1") == "lunga" and d.get("c2") == "silenzio"
                 and d.get("n") == list(range(1, 51)), r.stdout[-400:] + r.stderr[-400:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    prova_config()
    prova_listener()
    prova_seguito()
    prova_giro()
    prova_satellite()
    prova_client()
    prova_telefono()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
