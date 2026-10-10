import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco delle pause e della fine del turno (07/10, calliope/pause.py: solo misura,
nessun comportamento cambiato).

- `MisuraPause`: pause interne sopra 120 ms e sotto la soglia, parlato senza il silenzio finale;
- `audio.Listener` con un microfono e un VAD finti: una frase sintetica con pause note (192 e
  320 ms misurate, 96 ms no), parlato, chiusura per silenzio e per frase lunga; la soglia di
  chiusura resta quella di sempre;
- ripresa dopo la frase (taglio probabile): voce subito dopo: `ripresa_s` e avviso; contrari:
  nessuna voce, casse occupate (`ripresa_muto`), misura fermata perché Calliope risponde, voce
  oltre i 2 s;
- «aspetta», «non ho finito», «stavo dicendo» in testa alla frase, con i contrari;
- riassunto per persona e canale (p50/p90/p95, tagli, soglia stimata tra 400 e 1300 ms, poche
  pause, tagli frequenti) e `calliope stato --turni --pause`;
- ciclo: il campo «ascolto» del registro (canale, soglia, pause, ripresa al turno dopo con la
  stessa persona, taglio probabile, fascia d'età);
- protocollo: `frase_finita` con i campi nuovi (controllati, facoltativi: satellite vecchio),
  `ripresa` dal satellite, server dei satelliti vero con un client WebSocket, satellite in
  Python che li manda e smette di misurare quando arriva la risposta, telefono riconosciuto;
- telefono: la stessa misura in `voce.js` eseguita con node (se c'è) e i campi in `telefono.js`.
"""

import io
import json
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from calliope import pause
from calliope.config import Config

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""))


def aspetta(cond, timeout=5.0):
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# ─────────────────────────── MisuraPause ───────────────────────────
def prova_misura():
    m = pause.MisuraPause(32.0)
    m.frame_voce = 1
    for s in [False] * 4 + [True] * 3 + [False] * 2 + [True] * 4 + [False] + [True] * 10:
        m.frame(s)
    verifica("MisuraPause: 128 ms sì, 96 ms no, il silenzio finale non è una pausa",
             m.pause == [128], m.pause)
    verifica("MisuraPause: parlato senza il silenzio finale", m.parlato_ms(10) == 15 * 32,
             m.parlato_ms(10))
    m = pause.MisuraPause(32.0)
    for _ in range(200):
        m.frame(True)
        m.frame(True)
        m.frame(True)
        m.frame(True)
        m.frame(False)
    verifica("MisuraPause: al più MAX_PAUSE pause per frase", len(m.pause) == pause.MAX_PAUSE)


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
                time.sleep(0.002)
        threading.Thread(target=gira, daemon=True).start()

    def abort(self):
        self._stop.set()

    close = abort


class VadFinto:
    def prob(self, frame):
        return 1.0 if np.max(np.abs(frame)) > 0.05 else 0.0

    def reset_states(self):
        pass


VOCE, SILENZIO = np.full(512, 0.3, np.float32), np.zeros(512, np.float32)


def metti(*pezzi):
    for tipo, n in pezzi:
        for _ in range(n):
            MIC.put(VOCE if tipo == "v" else SILENZIO)


def ascolta(L, pezzi, **kw):
    """La frase entra nel microfono solo quando listen ascolta (niente pre-roll a caso)."""
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("a", L.listen(**kw)), daemon=True)
    th.start()
    aspetta(lambda: L.active, 3)
    metti(*pezzi)
    th.join(10)
    return out.get("a")


def prova_listener():
    from calliope.audio import Listener
    cfg = Config()
    cfg.silence_ms, cfg.min_speech_ms, cfg.max_utterance_s = 700, 100, 30
    L = Listener(cfg, sorgente=MicFinto)
    L.model, L.vad_ripresa = VadFinto(), VadFinto()
    avvisi = []
    L.ripresa_avviso = avvisi.append
    try:
        a = ascolta(L, [("v", 10), ("s", 6), ("v", 10), ("s", 3), ("v", 5), ("s", 10),
                        ("v", 5)])
        verifica("frase con pause note: presa", a is not None)
        verifica("pause interne 192 e 320 ms (96 ms no)", L.pause_ms == [192, 320], L.pause_ms)
        verifica("parlato dalla prima all'ultima voce: 49 frame", L.parlato_ms == 49 * 32,
                 L.parlato_ms)
        verifica("chiusura per silenzio, con la soglia di sempre", L.chiusura == "silenzio")
        # Voce subito dopo: taglio probabile
        metti(("v", 6))
        r = L._ripresa_ultima
        aspetta(lambda: r.finita.is_set(), 4)
        verifica("ripresa misurata dopo la frase (0,7–2 s dalla fine della voce)",
                 L.ripresa_s() is not None and 0.65 <= L.ripresa_s() <= 2.0, L.ripresa_s())
        verifica("avviso della ripresa (il satellite lo manda al server)",
                 avvisi == [L.ripresa_s()], avvisi)

        # Contrario: nessuno parla dopo
        ascolta(L, [("v", 10)])
        r = L._ripresa_ultima
        aspetta(lambda: r.finita.is_set(), 4)
        verifica("contrario: silenzio dopo la frase, nessuna ripresa",
                 r.finita.is_set() and L.ripresa_s() is None, L.ripresa_s())

        # Contrario: le casse suonano (voce di Calliope, segnale di fine)
        L.ripresa_muto = lambda: True
        ascolta(L, [("v", 10)])
        metti(("v", 8))
        r = L._ripresa_ultima
        aspetta(lambda: r.finita.is_set(), 4)
        verifica("contrario: casse occupate, la voce non è una ripresa", L.ripresa_s() is None)
        L.ripresa_muto = None

        # Contrario: Calliope comincia a rispondere (ferma_ripresa) prima della voce
        ascolta(L, [("v", 10)])
        L.ferma_ripresa()
        metti(("v", 8))
        time.sleep(0.3)
        verifica("contrario: misura fermata dalla risposta", L.ripresa_s() is None)

        # Contrario: la voce arriva oltre i 2 s dalla fine della frase
        ascolta(L, [("v", 10)])
        time.sleep(1.5)
        metti(("v", 8))
        r = L._ripresa_ultima
        aspetta(lambda: r.finita.is_set(), 4)
        verifica("contrario: voce oltre RIPRESA_S, nessuna ripresa", L.ripresa_s() is None)

        # La frase dopo ferma l'osservazione della prima
        ascolta(L, [("v", 10)])
        prima = L._ripresa_ultima
        ascolta(L, [("v", 10)])
        verifica("listen ferma l'osservazione della frase di prima",
                 prima.finita.wait(1) and L._ripresa_ultima is not prima)

        # Frase lunga: chiusa da max_utterance_s, non dal silenzio
        cfg.max_utterance_s = 1
        ascolta(L, [("v", 40)])
        verifica("chiusura per frase lunga", L.chiusura == "lunga", L.chiusura)
        cfg.max_utterance_s = 30
        L.ferma_ripresa()
    finally:
        L.stream.abort()


# ─────────────────────────── «aspetta», «non ho finito» ───────────────────────────
def prova_segnali():
    nomi = ("Calliope", None)
    si = {"Aspetta, non ho finito": "aspetta", "Calliope, aspetta un attimo.": "aspetta",
          "Calliope aspetta": "aspetta", "Non ho finito di parlare!": "non_ho_finito",
          "ehm, non ho ancora finito": "non_ho_finito",
          "no no, stavo dicendo che domani piove": "stavo_dicendo",
          "Fammi finire": "fammi_finire", "Calliope, ma aspetta!": "aspetta"}
    for t, atteso in si.items():
        verifica(f"segnale in testa: {t!r}", pause.inizio_ripresa(t, nomi) == atteso,
                 pause.inizio_ripresa(t, nomi))
    for t in ("aspetta che arrivi la pizza", "non ho finito i compiti",
              "Dimmi se devo aspettare", "Che ore sono?", "stavo dicendolo",
              "Calliope, la tua amica aspetta.", ""):
        verifica(f"contrario, nessun segnale: {t!r}", pause.inizio_ripresa(t, nomi) is None,
                 pause.inizio_ripresa(t, nomi))


# ─────────────────────────── riassunto e stato ───────────────────────────
def turni_finti():
    out = []
    rng = np.random.default_rng(7)
    for i in range(30):          # Ada (persona di fantasia), locale: pause 150–500 ms
        p = [int(x) for x in rng.integers(150, 500, 2)]
        out.append({"inizio": f"2026-10-07T10:{i:02d}:00", "voce": {"nome": "ada"},
                    "ascolto": {"canale": "locale", "soglia_ms": 700, "pause_ms": p,
                                "parlato_ms": 1800, "chiusura": "silenzio"}})
    for i in range(20):          # Bruno al telefono: tanti tagli
        out.append({"inizio": f"2026-10-07T11:{i:02d}:00", "voce": {"nome": "bruno"},
                    "ascolto": {"canale": "telefono", "satellite": "telefono",
                                "soglia_ms": 700, "pause_ms": [300, 450],
                                "chiusura": "silenzio", "taglio_probabile": i % 4 == 0,
                                **({"inizio_ripresa": "aspetta"} if i == 3 else {})}})
    for i in range(3):           # un ospite: poche pause
        out.append({"inizio": f"2026-10-07T12:0{i}:00", "voce": {"nome": None},
                    "ascolto": {"canale": "satellite", "satellite": "cucina",
                                "soglia_ms": 700, "pause_ms": [200]}})
    # Una bambina (fascia nel registro): gruppo a parte
    out.append({"inizio": "2026-10-07T13:00:00", "voce": {"nome": "cleo"},
                "ascolto": {"canale": "locale", "soglia_ms": 700, "pause_ms": [600],
                            "fascia": "bambini", "ripresa_dopo_s": 1.1}})
    out.append({"inizio": "2026-10-07T13:01:00", "testo": "senza ascolto: turno vecchio"})
    return out


def prova_riassunto():
    r = pause.riassunto(turni_finti())
    g = {(x["persona"], x["canale"]): x for x in r["gruppi"]}
    verifica("gruppi per persona e canale (turni vecchi saltati)",
             sorted(g) == [("ada", "locale"), ("bruno", "telefono:telefono"),
                           ("cleo (bambini)", "locale"), ("ospite", "satellite:cucina")],
             sorted(g))
    ada = g[("ada", "locale")]
    pa = sorted(x for t in turni_finti()[:30] for x in t["ascolto"]["pause_ms"])
    p95 = pa[int(.95 * len(pa))]
    verifica("p50/p90/p95 delle pause di Ada", (ada["pause"]["n"], ada["pause"]["p95"])
             == (60, p95), ada["pause"])
    verifica("soglia stimata = p95 + margine, nei limiti",
             ada["soglia_stimata_ms"] == max(400, min(1300, p95 + pause.MARGINE_MS)),
             ada["soglia_stimata_ms"])
    b = g[("bruno", "telefono:telefono")]
    verifica("tagli probabili e segnali contati", (b["tagli_probabili"], b["segnali_a_parole"])
             == (5, 1), b)
    verifica("tagli frequenti: la stima sale oltre la soglia in uso (le pause sono troncate)",
             b["soglia_stimata_ms"] == 1000 and "tagli" in b["motivo"], b)
    o = g[("ospite", "satellite:cucina")]
    verifica("contrario: poche pause, nessuna stima", o["soglia_stimata_ms"] is None, o)
    verifica("riprese al turno dopo contate", g[("cleo (bambini)", "locale")]
             ["riprese_turno_dopo"] == 1)
    verifica("stima limitata a 1300 ms", pause.soglia_stimata([1250] * 30, 30, 0, 700)[0]
             == 1300)
    verifica("stima almeno 400 ms", pause.soglia_stimata([130] * 30, 30, 0, 700)[0] == 400)
    t = pause.testo(r)
    verifica("testo per il terminale: soglia in uso e stima, «non si applica»",
             "ada · locale: 30 frasi" in t and "si sceglierebbe" in t and "non si applica" in t, t)
    verifica("testo senza turni", "nessun turno" in pause.testo(pause.riassunto([])))

    cartella = tempfile.mkdtemp(prefix="calliope-pause-")
    with open(os.path.join(cartella, "turni-2026-10-07.jsonl"), "w", encoding="utf-8") as f:
        for x in turni_finti():
            f.write(json.dumps(x) + "\n")
    from calliope import stato
    vecchio = stato._config
    cfg = Config()
    cfg.turn_log_dir = cartella
    stato._config = lambda quiet: cfg
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = stato.main(["--turni", "--pause"])
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            stato.main(["--turni", "--pause", "--json", "--giorni", "1"])
        js = json.loads(buf2.getvalue()[buf2.getvalue().index("{"):])
    finally:
        stato._config = vecchio
        shutil.rmtree(cartella, ignore_errors=True)
    verifica("calliope stato --turni --pause", rc == 0 and "bruno · telefono" in buf.getvalue(),
             buf.getvalue())
    verifica("… e in JSON", len(js["gruppi"]) == 4)


# ─────────────────────────── ciclo: il campo «ascolto» ───────────────────────────
def prova_ciclo():
    from calliope.ciclo import Ciclo, Turno
    c = object.__new__(Ciclo)
    cfg = Config()
    profili = {"cleo": SimpleNamespace(nascita="2019-05-01", fascia=None)}
    c.s = SimpleNamespace(cfg=cfg, registry=SimpleNamespace(get=profili.get))
    c._fine_voce_prec, c._voce_prec = None, None
    ora = time.monotonic()
    c.listener = SimpleNamespace(started_at=ora - 3, ended_at=ora - 1.5, pause_ms=[200, 340],
                                 parlato_ms=1500, chiusura="silenzio", ripresa_s=lambda: 0.9)
    t = Turno()
    a = c._misure_ascolto(t)
    verifica("locale: canale, soglia, pause, parlato, chiusura",
             a == {"canale": "locale", "soglia_ms": 700, "chiusura": "silenzio",
                   "parlato_ms": 1500, "pause_ms": [200, 340]}, a)
    rec = {"voce": {"nome": "cleo"}, "ascolto": a}
    c._chiudi_ascolto(rec)
    verifica("taglio probabile e fascia d'età nel turno troncato",
             (a.get("ripresa_s"), a.get("taglio_probabile"), a.get("fascia"))
             == (0.9, True, "bambini"), a)
    # Il turno dopo: comincia 1,2 s dopo la fine della voce di prima, stessa persona
    c.listener = SimpleNamespace(remoto=True, canale="telefono", satellite_nome="telefono",
                                 started_at=ora - 0.3, ended_at=ora, pause_ms=None,
                                 parlato_ms=None, chiusura=None, ripresa_s=lambda: None)
    a2 = c._misure_ascolto(t)
    rec2 = {"voce": {"nome": "cleo"}, "ascolto": a2}
    c._chiudi_ascolto(rec2)
    verifica("turno dopo: ripresa_dopo_s, stessa persona; satellite vecchio senza pause",
             (a2.get("ripresa_dopo_s"), a2.get("stessa_persona"), a2["canale"],
              a2.get("satellite"), "pause_ms" in a2) == (1.2, True, "telefono", "telefono",
                                                          False), a2)
    # Contrari: frase molto dopo, frase dal barge-in
    c.listener.started_at, c.listener.ended_at = ora + 5, ora + 6
    a3 = c._misure_ascolto(t)
    verifica("contrario: 5 s dopo, nessuna ripresa al turno dopo", "ripresa_dopo_s" not in a3)
    c.listener.started_at = ora + 6.5
    t.barged = True
    a4 = c._misure_ascolto(t)
    verifica("contrario: frase che parte dal barge-in, niente ripresa (ma «seme»)",
             "ripresa_dopo_s" not in a4 and a4.get("seme") is True, a4)
    rec5 = {"voce": {"nome": None}, "ascolto": {"canale": "locale"}}
    c._chiudi_ascolto(rec5)
    verifica("ospite: niente fascia né taglio", rec5["ascolto"] == {"canale": "locale"})
    # Il ciclo intero: il campo è nel turno scritto (prova_ciclo usa il listener finto senza
    # i metodi nuovi: getattr, nessun errore)
    src = (RADICE / "calliope" / "ciclo.py").read_text(encoding="utf-8")
    verifica("ciclo: misura chiusa prima di scrivere il turno, ferma alla prima frase",
             # dal 10/10 il turno si scrive con `_scrivi_turno` (ombra degli eventi, poi TurnLog)
             "self._chiudi_ascolto(self.rec)\n            self._scrivi_turno(self.rec)" in src
             and src.count("self._fine_ripresa()") == 2)


# ─────────────────────────── protocollo e satelliti ───────────────────────────
def prova_protocollo():
    from calliope.satellite.server import Collegamento, valida_evento
    ev = valida_evento("frase_finita", {"id": 3, "fa_s": 1.0, "woke": True,
                                        "pause_ms": [150, 300.4, "x", True, -1, 99999],
                                        "parlato_ms": 1200, "chiusura": "silenzio"})
    verifica("frase_finita: pause controllate (niente testo, bool, negativi, enormi)",
             (ev["pause_ms"], ev["parlato_ms"], ev["chiusura"]) == ([150, 300], 1200,
                                                                    "silenzio"), ev)
    ev = valida_evento("frase_finita", {"id": 3, "fa_s": 1.0})
    verifica("satellite vecchio: frase_finita senza i campi nuovi",
             "pause_ms" not in ev and "chiusura" not in ev, ev)
    ev = valida_evento("frase_finita", {"id": 3, "pause_ms": "tante", "parlato_ms": "x",
                                        "chiusura": "rm -rf"})
    verifica("campi rotti scartati", set(ev) == {"id", "fa_s", "woke", "wake_score"}, ev)
    coll = Collegamento(SimpleNamespace(), {"nome": "studio"}, "h")
    verifica("canale satellite", coll.canale == "satellite")
    from calliope.schermi.telefono import PonteWs
    coll_t = Collegamento(object.__new__(PonteWs), {"nome": "telefono"}, "h")
    verifica("canale telefono (la web app passa dal ponte degli schermi)",
             coll_t.canale == "telefono")
    for i in range(30):
        coll.ripresa(i, 0.8)
    verifica("riprese: solo le ultime 20", sorted(coll.riprese) == list(range(10, 30)))


def prova_server():
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import AscoltoRemoto, ServerSatelliti
    tmp = Path(tempfile.mkdtemp(prefix="calliope-pause-srv-"))
    cfg = Config()
    cfg.config_dir, cfg.memory_db, cfg.satellite_porta = str(tmp), str(tmp / "m.db"), 0
    cfg.wake_model = str(tmp / "manca.onnx")
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=lambda *a: None).avvia()
    srv.avviato.set()
    _, tok = arch.crea_con_token("studio")
    ws = connect(f"ws://127.0.0.1:{srv.port}{P.PERCORSO_AUDIO}", compression=None)
    try:
        ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=tok, primo=False))
        while P.leggi(ws.recv(timeout=5)).get("tipo") != "benvenuto":
            pass
        ws.send(P.testo(tipo="pronto", eco=0.0))
        asc = AscoltoRemoto(srv, cfg)

        def un_ascolto(**campi):
            out = {}
            th = threading.Thread(target=lambda: out.setdefault("a", asc.listen()), daemon=True)
            th.start()
            while True:
                m = ws.recv(timeout=5)
                if isinstance(m, str) and P.leggi(m).get("tipo") == "ascolta":
                    lid = P.leggi(m)["id"]
                    break
            ws.send(P.binario(P.AUDIO, lid, b"\x00\x10" * 8000))
            ws.send(P.testo(tipo="frase_finita", id=lid, fa_s=0.6, woke=True, wake_score=0.9,
                            **campi))
            th.join(5)
            return lid, out.get("a")

        lid, a = un_ascolto(pause_ms=[180, 410], parlato_ms=2100, chiusura="silenzio")
        verifica("server vero: la frase arriva con pause, parlato e chiusura dal satellite",
                 a is not None and (asc.pause_ms, asc.parlato_ms, asc.chiusura, asc.canale,
                                    asc.satellite_nome)
                 == ([180, 410], 2100, "silenzio", "satellite", "studio"),
                 (asc.pause_ms, asc.parlato_ms, asc.chiusura, asc.canale))
        ws.send(P.testo(tipo="ripresa", id=lid, dopo_s=1.04))
        verifica("«ripresa» dal satellite: ripresa_s dell'ultima frase",
                 aspetta(lambda: asc.ripresa_s() == 1.04, 3), asc.ripresa_s())
        ws.send(P.testo(tipo="ripresa", id=lid + 50, dopo_s=0.9))
        time.sleep(0.2)
        verifica("contrario: la ripresa di un altro ascolto non vale",
                 asc.ripresa_s() == 1.04)
        ws.send(P.testo(tipo="ripresa", id="x", dopo_s="y"))
        lid2, a2 = un_ascolto()
        verifica("satellite vecchio: nessuna pausa, nessuna ripresa, la frase arriva",
                 a2 is not None and asc.pause_ms is None and asc.ripresa_s() is None,
                 (asc.pause_ms, asc.ripresa_s()))
    finally:
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass
        srv.ferma() if hasattr(srv, "ferma") else None
        shutil.rmtree(tmp, ignore_errors=True)


def prova_client():
    """Il satellite in Python: frase_finita con le misure del suo Listener, «ripresa» appena
    c'è, misura fermata quando arriva la risposta."""
    from calliope.satellite.client import Satellite
    mandati = []
    ascolti = []

    class ListenerFinto:
        started_at, woke, wake_score = 0.0, True, 0.9
        pause_ms, parlato_ms, chiusura = [210], 900, "silenzio"
        on_audio = on_speech_end = ripresa_muto = ripresa_avviso = None
        fermate = 0

        def listen(self, *a, **k):
            ascolti.append((self.ripresa_muto, self.ripresa_avviso))
            self.started_at = time.monotonic() - 1
            self.ripresa_avviso(0.95)           # come farebbe l'osservazione, dal thread
            return np.zeros(16000, np.float32)

        def ferma_ripresa(self):
            self.fermate += 1

    s = object.__new__(Satellite)
    s.listener = ListenerFinto()
    s._seed, s.wake, s._wakeup = None, None, threading.Event()
    s.traccia, s.frasi_inviate = [], 0
    s._manda = lambda **c: mandati.append(c)
    s._suona = lambda tipo: None
    s.player = SimpleNamespace(occupato=lambda: False, frase=lambda *a: None)
    s._ascolta({"id": 9})
    ff = [m for m in mandati if m["tipo"] == "frase_finita"]
    verifica("satellite: frase_finita con pause_ms, parlato_ms, chiusura",
             ff and (ff[0]["pause_ms"], ff[0]["parlato_ms"], ff[0]["chiusura"])
             == ([210], 900, "silenzio"), ff)
    verifica("satellite: «ripresa» con l'id dell'ascolto",
             {"tipo": "ripresa", "id": 9, "dopo_s": 0.95} in mandati, mandati)
    verifica("satellite: le sue casse sospendono la misura",
             ascolti and ascolti[0][0] is s.player.occupato)
    s.traccia = []
    s._comando({"tipo": "frase", "turno": 1, "id": 1, "testo": "Sono le dieci.", "rate": 22050,
                "byte": 10})
    verifica("satellite: la risposta ferma la misura della ripresa", s.listener.fermate == 1)
    from calliope.satellite.client import Riproduttore
    p = object.__new__(Riproduttore)
    p.in_corso, p.q, p._pcm_fino, p.ultima_scrittura = False, queue.Queue(), 0.0, 0.0
    verifica("casse ferme: non occupate", p.occupato() is False)
    p._pcm_fino = time.monotonic()
    verifica("segnale appena suonato: occupate", p.occupato() is True)


# ─────────────────────────── telefono ───────────────────────────
JS_PROVA = r"""
const { Ascolto } = await import(process.argv[2]);
const p = { preroll_ms: 300, vad_threshold: 0.5, silence_ms: 700, min_speech_ms: 100,
  max_utterance_s: 30, wake_threshold: 0.5, wake_consecutive: 2 };
const a = new Ascolto(p);
a.vad = { prob: async (f) => (f[0] > 0.05 ? 1 : 0), reset() {} };
const V = new Float32Array(512).fill(0.3), S = new Float32Array(512);
const seq = [];
const metti = (x, n) => { for (let i = 0; i < n; i++) seq.push(x); };
metti(V, 10); metti(S, 6); metti(V, 10); metti(S, 3); metti(V, 5); metti(S, 10); metti(V, 5);
metti(S, 30);
const pr = a.listen({ wake: false, fino: Infinity });
for (const f of seq) a.push(f);
const r = await pr;
// Rilascio (tasto «Parla» lasciato): chiusura «rilascio»
let lascia = false;
const pr2 = a.listen({ wake: false, fino: Infinity, fine: () => lascia });
for (let i = 0; i < 8; i++) a.push(V);
await new Promise((ok) => setTimeout(ok, 50));
lascia = true;
a.push(V); a.push(V);
const r2 = await pr2;
console.log(JSON.stringify({ pause: r.pause, parlato: r.parlato, chiusura: r.chiusura,
  chiusura2: r2 && r2.chiusura }));
"""


def prova_telefono():
    pag = RADICE / "calliope" / "schermi" / "pagina" / "telefono"
    tj = (pag / "telefono.js").read_text(encoding="utf-8")
    verifica("telefono.js: frase_finita con pause_ms, parlato_ms, chiusura",
             "pause_ms: r.pause || []" in tj and "parlato_ms: r.parlato" in tj
             and "chiusura: r.chiusura" in tj)
    node = shutil.which("node")
    if not node:
        print("SALTATA IN PARTE: node non c'è: la misura di voce.js non si esegue")
        return
    tmp = Path(tempfile.mkdtemp(prefix="calliope-pause-js-"))
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
        verifica("voce.js (node): stesse pause di Python, parlato, chiusura",
                 d.get("pause") == [192, 320] and d.get("parlato") == 49 * 32
                 and d.get("chiusura") == "silenzio", r.stdout + r.stderr)
        verifica("voce.js: tasto lasciato, chiusura «rilascio»", d.get("chiusura2") == "rilascio",
                 d)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


prova_misura()
prova_listener()
prova_segnali()
prova_riassunto()
prova_ciclo()
prova_protocollo()
prova_server()
prova_client()
prova_telefono()
print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
