import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della fine del turno System 1 (14/10, calliope/system1/: decisore piccolo
sull'audio, Smart Turn di Pipecat; in ombra e attiva).

- interfaccia: `Decisione`, `Sorvegliato` (decisore lento → None, occupato → None, guasto →
  None e spento dopo GUASTI_MAX errori di fila), `risposta`;
- log-mel di Whisper in numpy uguale a faster-whisper (base) e ai numeri di
  `transformers.WhisperFeatureExtractor` (misurati il 14/10), finestra degli ultimi 8 s;
- `Politica.verdetto` e la simulazione dell'ombra con un decisore finto che «sente» un segno
  nell'audio: frase completa (anticipo, ms risparmiati), frase sospesa con «e»/«in»/«poi»
  (pausa interna presa per «non finito»: nessun taglio), sospesa presa per finita (taglio),
  numeri dettati, elenco incerto, ripresa dopo una pausa lunga (taglio evitato, attesa
  inutile, oltre il tetto), «finito» ma la persona riprende, decisore guasto o lento (come
  prima), silenzio finale corto (nessuna chiusura), tetto delle sonde;
- `OmbraFineTurno` con un VAD finto: esito nel campo `ascolto`, «in_ritardo», spenta;
- `audio.Listener` in «attiva» con microfono e VAD finti: chiusura anticipata, attesa lunga
  che non taglia la frase sospesa, incerto, decisore guasto, lento e spento → silenzio fisso;
- `prepara_listener`, configurazione (modo, intervalli, calliope.yaml), catalogo, protocollo
  del satellite (`campi_esito`, `frase_finita`, PARAMETRI), ciclo (`_misure_ascolto`,
  `_chiudi_ascolto`), riassunto e riga di `calliope stato --turni`.
"""

import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from calliope.config import Config
from calliope.system1 import GUASTI_MAX, Decisione, Sorvegliato, risposta
from calliope.system1 import fine_turno as ft

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
        time.sleep(0.01)
    return cond()


# ─────────────────────────── decisore e VAD finti ───────────────────────────
# Il «segno» è l'ampiezza dei frame di voce: 0.6 = intonazione che chiude, 0.3 = sospesa,
# 0.45 = incerta. Il decisore finto guarda l'ultimo frame di voce dell'audio che riceve.
CHIUDE, SOSPESA, INCERTA = 0.6, 0.3, 0.45


class DecisoreFinto:
    nome = "finto"
    scelte = (ft.FINITO, ft.NON_FINITO)

    def __init__(self, ritardo=0.0, guasto=False):
        self.ritardo, self.guasto, self.chiamate = ritardo, guasto, 0

    def decide(self, audio) -> Decisione:
        self.chiamate += 1
        if self.guasto:
            raise RuntimeError("guasto finto")
        if self.ritardo:
            time.sleep(self.ritardo)
        x = np.asarray(audio).reshape(-1)
        n = len(x) // 512
        segno = 0.0
        for i in range(n - 1, -1, -1):
            v = float(np.max(np.abs(x[i * 512:(i + 1) * 512])))
            if v > 0.05:
                segno = v
                break
        p = {CHIUDE: 0.97, SOSPESA: 0.04, INCERTA: 0.6}.get(round(segno, 2), 0.5)
        return (Decisione(ft.FINITO, p, 1.0, p) if p >= 0.5
                else Decisione(ft.NON_FINITO, 1 - p, 1.0, p))


class VadFinto:
    def prob(self, frame):
        return 1.0 if np.max(np.abs(frame)) > 0.05 else 0.0

    def reset_states(self):
        pass


def frame(a):
    return np.full(512, a, np.float32)


def audio(*pezzi):
    """("v", n, ampiezza) o ("s", n): frame da 32 ms."""
    out = []
    for p in pezzi:
        out += [frame(p[2]) if p[0] == "v" else frame(0.0)] * p[1]
    return np.concatenate(out)


POL = ft.Politica(silence_ms=700, sonda_ms=250, soglia=0.9, soglia_attesa=0.8,
                  attesa_max_ms=1500)


def gioca(a, decide=None, pol=POL):
    dec = DecisoreFinto()
    inizio, flag = ft.silenzi(a, VadFinto(), 0.5)
    return ft.simula(a, decide or dec.decide, pol, inizio, flag)


# ─────────────────────────── interfaccia ───────────────────────────
def prova_interfaccia():
    s = Sorvegliato(DecisoreFinto(), log=lambda *_: None)
    d = s.chiedi(audio(("v", 10, CHIUDE), ("s", 8)), 2.0)
    verifica("Sorvegliato: la decisione del decisore, con i ms", d is not None
             and d.scelta == ft.FINITO and d.sicurezza > 0.9 and d.ms > 0, d)
    s.chiudi()
    lento = Sorvegliato(DecisoreFinto(ritardo=0.4), log=lambda *_: None)
    t0 = time.monotonic()
    d = lento.chiedi(audio(("v", 5, CHIUDE)), 0.05)
    verifica("decisore lento: None entro il tempo massimo (vale la regola di prima)",
             d is None and time.monotonic() - t0 < 0.3 and lento.lente == 1)
    verifica("decisore ancora occupato: la domanda nuova non parte (None)",
             lento.avvia(audio(("v", 5, CHIUDE))) is None)
    aspetta(lambda: lento._in_corso.done(), 2)
    f = lento.avvia(audio(("v", 5, CHIUDE)))
    verifica("finita la domanda di prima, la nuova parte", f is not None)
    aspetta(lambda: f.done(), 2)
    verifica("risposta(): solo da un Future finito", risposta(f) is not None
             and risposta(None) is None)
    lento.chiudi()
    log = []
    g = Sorvegliato(DecisoreFinto(guasto=True), log=log.append)
    esiti = [g.chiedi(audio(("v", 3, CHIUDE)), 1.0) for _ in range(GUASTI_MAX + 2)]
    verifica("decisore guasto: None ogni volta, spento dopo i guasti di fila (detto una volta)",
             all(e is None for e in esiti) and g.spento and g.guasti == GUASTI_MAX
             and len(log) == 1 and g.avvia(audio(("v", 3, CHIUDE))) is None, (g.guasti, log))
    g.chiudi()


# ─────────────────────────── log-mel ───────────────────────────
def prova_log_mel():
    rng = np.random.default_rng(0)
    corto = (rng.standard_normal(4000) * 0.1).astype(np.float32)
    t = np.arange(160000) / 16000
    sin10 = (0.3 * np.sin(2 * np.pi * 220 * t) * (1 + np.sin(t))).astype(np.float32)
    f = ft.log_mel(sin10)
    verifica("log-mel: forma (80, 800) in float32", f.shape == (80, 800)
             and f.dtype == np.float32, f.shape)
    # I numeri di transformers.WhisperFeatureExtractor(chunk_length=8, do_normalize=True)
    # sulla stessa sinusoide, misurati il 14/10 (transformers non è una dipendenza)
    rif = {"media": -0.08014490455389023, (10, 400): 0.3263964056968689,
           (60, 799): -0.2587625980377197, (0, 0): 1.4605014324188232}
    diff = max(abs(float(f.mean()) - rif["media"]),
               *(abs(float(f[k]) - v) for k, v in rif.items() if k != "media"))
    verifica("log-mel uguale a WhisperFeatureExtractor (ultimi 8 s, normalizzati)",
             diff < 1e-4, diff)
    p = ft.prepara(corto)
    verifica("frase corta: zeri davanti, la voce in fondo", len(p) == 128000
             and np.allclose(p[:1000], p[0]) and not np.allclose(p[-4000:], p[0]))
    lunga = np.concatenate([np.ones(16000, np.float32), sin10])
    verifica("frase lunga: contano gli ultimi 8 s", np.allclose(ft.log_mel(lunga),
                                                                ft.log_mel(sin10[-128000:])))
    try:
        from faster_whisper.feature_extractor import FeatureExtractor
    except ImportError:
        print("SALTATA IN PARTE: faster-whisper non c'è (confronto del log-mel)")
        return
    fe = FeatureExtractor(chunk_length=8)
    d = max(float(np.abs(fe(ft.prepara(x), padding=0)[:, :800] - ft.log_mel(x)).max())
            for x in (corto, sin10, (rng.standard_normal(48000) * 0.1).astype(np.float32)))
    verifica("log-mel uguale a quello di faster-whisper", d < 1e-4, d)


# ─────────────────────────── politica e ombra ───────────────────────────
def prova_politica():
    v = POL.verdetto
    verifica("verdetto: «finito» sicuro → chiudi, sotto soglia → fisso",
             v(Decisione(ft.FINITO, 0.95)) == "chiudi" and v(Decisione(ft.FINITO, 0.85))
             == "fisso")
    verifica("verdetto: «non finito» sicuro → aspetta, sotto soglia → fisso; None → fisso",
             v(Decisione(ft.NON_FINITO, 0.9)) == "aspetta" and v(Decisione(ft.NON_FINITO, 0.6))
             == "fisso" and v(None) == "fisso")
    verifica("sonda: 250 ms = 8 frame da 32 ms", POL.frame_sonda(32.0) == 8)
    verifica("frase cortissima (sotto min_parlato_ms): «finito» sicuro non chiude",
             v(Decisione(ft.FINITO, 0.99), 640) == "fisso"
             and v(Decisione(ft.FINITO, 0.99), 900) == "chiudi"
             and v(Decisione(ft.NON_FINITO, 0.9), 300) == "aspetta")
    cfg = Config()
    cfg.fine_turno_soglia, cfg.silence_ms = 0.95, 800
    p = ft.Politica.da_cfg(cfg)
    verifica("politica dalla configurazione", (p.soglia, p.silence_ms, p.sonda_ms)
             == (0.95, 800, 250), p)


def prova_ombra():
    # Frase completa: «Accendi la luce in cucina.» → chiusa prima, ms risparmiati
    s = gioca(audio(("s", 5), ("v", 30, SOSPESA), ("v", 5, CHIUDE), ("s", 25)))
    e = ft.esito(s, None, POL)
    verifica("frase completa: anticipo, 700 − 250 − ms del decisore risparmiati",
             e["esito"] == "anticipo" and e["risparmio_ms"] == 449 and e["interne"] == 0, e)
    # Sospesa con «e»/«in»/«poi» e una pausa di 400 ms, poi il seguito: non la taglia
    s = gioca(audio(("s", 5), ("v", 20, SOSPESA), ("s", 13), ("v", 10, SOSPESA),
                    ("v", 4, CHIUDE), ("s", 25)))
    e = ft.esito(s, None, POL)
    verifica("frase sospesa («accendi la luce in…» 400 ms «…cucina»): nessun taglio, una "
             "pausa interna «non finito», chiusura anticipata",
             e["esito"] == "anticipo" and e["interne"] == 1 and s["interne"][0]["p"] < 0.1, s)
    # La stessa, ma il decisore la prende per finita: avrebbe tagliato
    s = gioca(audio(("s", 5), ("v", 30, CHIUDE), ("s", 13), ("v", 10, SOSPESA),
                    ("v", 4, CHIUDE), ("s", 25)))
    e = ft.esito(s, None, POL)
    verifica("contrario: pausa interna presa per la fine → «taglio», con dove",
             e["esito"] == "taglio" and e["taglio_ms"] == 30 * 32, e)
    # Numeri dettati: «tre quattro sette… due nove uno…» tre pause di 450 ms
    s = gioca(audio(("s", 5), ("v", 8, SOSPESA), ("s", 14), ("v", 8, SOSPESA), ("s", 14),
                    ("v", 8, SOSPESA), ("s", 14), ("v", 8, CHIUDE), ("s", 25)))
    e = ft.esito(s, None, POL)
    verifica("numeri dettati: tre pause interne «non finito», nessun taglio",
             e["interne"] == 3 and e["esito"] == "anticipo", e)
    # Elenco con pause incerte (0,6): non taglia (sotto la soglia), ma neanche chiude prima
    s = gioca(audio(("s", 5), ("v", 8, INCERTA), ("s", 10), ("v", 8, INCERTA), ("s", 10),
                    ("v", 8, INCERTA), ("s", 25)))
    e = ft.esito(s, None, POL)
    verifica("elenco incerto: nessun taglio, chiusura come prima",
             e["esito"] == "come_prima" and e["interne"] == 2, e)
    # Pausa sotto la sonda: nessuna domanda
    s = gioca(audio(("s", 5), ("v", 10, CHIUDE), ("s", 5), ("v", 10, CHIUDE), ("s", 25)))
    verifica("pausa di 160 ms (sotto la sonda): nessuna domanda", s["sonde"] == 1
             and not s["interne"], s)
    # Ripresa dopo una pausa lunga: «non finito» alla chiusura
    sim = gioca(audio(("s", 5), ("v", 20, SOSPESA), ("s", 25)))
    verifica("ripresa a 1,2 s dopo «non finito»: taglio evitato (entro il tetto di 1,5 s)",
             ft.esito(sim, 1.2, POL)["esito"] == "taglio_evitato")
    e = ft.esito(sim, None, POL)
    verifica("contrario: nessuna ripresa → attesa inutile di 800 ms",
             e["esito"] == "attesa" and e["costo_ms"] == 800, e)
    verifica("contrario: ripresa a 1,8 s, oltre il tetto → attesa (il taglio resta)",
             ft.esito(sim, 1.8, POL)["esito"] == "attesa")
    sim = gioca(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25)))
    verifica("«finito» ma la persona riprende: anticipo_ripresa (il fisso ha tagliato uguale)",
             ft.esito(sim, 0.9, POL)["esito"] == "anticipo_ripresa")
    # Decisore guasto o lento: come prima
    g = Sorvegliato(DecisoreFinto(guasto=True), log=lambda *_: None)
    sim = gioca(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25)),
                decide=lambda x: g.chiedi(x, 1.0))
    verifica("decisore guasto: come prima", ft.esito(sim, None, POL)["esito"] == "come_prima")
    lento = Sorvegliato(DecisoreFinto(ritardo=0.3), log=lambda *_: None)
    sim = gioca(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25)),
                decide=lambda x: lento.chiedi(x, 0.02))
    verifica("decisore lento: come prima", ft.esito(sim, None, POL)["esito"] == "come_prima")
    g.chiudi()
    lento.chiudi()
    sim = gioca(audio(("s", 5), ("v", 30, CHIUDE), ("s", 4)))
    verifica("silenzio finale più corto della sonda: nessuna chiusura trovata",
             ft.esito(sim, None, POL)["esito"] == "nessuna", sim)
    sim = gioca(audio(("s", 5), ("v", 15, CHIUDE), ("s", 15), ("v", 20, CHIUDE), ("s", 25)))
    verifica("il nome da solo e una pausa di 480 ms (sotto min_parlato_ms): nessun taglio",
             sim["taglio_ms"] is None and len(sim["interne"]) == 1, sim)
    sim = gioca(audio(("s", 3)))
    verifica("solo silenzio: nessuna domanda", sim["sonde"] == 0)
    pezzi = [("s", 5)]
    for _ in range(40):
        pezzi += [("v", 3, SOSPESA), ("s", 10)]
    sim = gioca(audio(*pezzi, ("s", 25)))
    verifica(f"al più {ft.MAX_SONDE} domande per frase", sim["sonde"] == ft.MAX_SONDE, sim)


def prova_servizio_ombra():
    cfg = Config()
    o = ft.OmbraFineTurno(cfg, decisore=DecisoreFinto(), vad=VadFinto(), log=lambda *_: None)
    fut = o.valuta(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25)))
    a = {"canale": "locale"}
    aspetta(lambda: fut.done(), 3)
    o.chiudi(a, fut)
    f = a.get("fine_turno") or {}
    verifica("ombra: l'esito nel campo ascolto, solo numeri", f.get("modo") == "ombra"
             and f.get("esito") == "anticipo" and f.get("risparmio_ms") == 449
             and all(isinstance(v, (int, float, str, type(None))) for v in f.values()), f)
    a = {"ripresa_s": 1.1}
    fut = o.valuta(audio(("s", 5), ("v", 20, SOSPESA), ("s", 25)))
    aspetta(lambda: fut.done(), 3)
    o.chiudi(a, fut)
    verifica("ombra con la ripresa misurata: taglio evitato",
             a["fine_turno"]["esito"] == "taglio_evitato", a)
    a = {"fine_turno": {"modo": "attiva", "chiusura": "anticipata", "silenzio_ms": 288}}
    fut = o.valuta(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25)))
    aspetta(lambda: fut.done(), 3)
    o.chiudi(a, fut)
    verifica("in «attiva» l'ombra tiene anche cosa ha fatto il Listener",
             a["fine_turno"].get("attiva", {}).get("chiusura") == "anticipata", a)
    o.ferma()
    lenta = ft.OmbraFineTurno(cfg, decisore=DecisoreFinto(ritardo=0.5), vad=VadFinto(),
                              log=lambda *_: None)
    a = {}
    lenta.chiudi(a, lenta.valuta(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25))), 0.01)
    verifica("simulazione non finita quando si scrive il turno: «in_ritardo»",
             a.get("fine_turno", {}).get("esito") == "in_ritardo", a)
    lenta.ferma()
    verifica("valuta senza audio: niente", o.valuta(np.zeros(0, np.float32)) is None)
    cfg = Config()
    verifica("spenta di serie: nessun servizio", ft.load_fine_turno(cfg) is None)
    cfg.fine_turno, cfg.fine_turno_modello = "ombra", str(RADICE / "non-c-e.onnx")
    log = []
    verifica("ombra senza modello: nessun servizio, detto una volta",
             ft.load_fine_turno(cfg, log=log.append) is None and len(log) == 1
             and "silenzio fisso" in log[0], log)


# ─────────────────────────── Listener in «attiva» ───────────────────────────
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
                time.sleep(0.004)
        threading.Thread(target=gira, daemon=True).start()

    def abort(self):
        self._stop.set()

    close = abort


def ascolta(L, *pezzi):
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("a", L.listen()), daemon=True)
    th.start()
    aspetta(lambda: L.active, 3)
    for p in pezzi:
        for _ in range(p[1]):
            MIC.put(frame(p[2]) if p[0] == "v" else frame(0.0))
    th.join(15)
    while not MIC.empty():
        MIC.get_nowait()
    return out.get("a")


def prova_listener():
    from calliope.audio import Listener
    cfg = Config()
    cfg.silence_ms, cfg.min_speech_ms, cfg.max_utterance_s = 700, 100, 30
    L = Listener(cfg, sorgente=MicFinto)
    L.model, L.vad_ripresa = VadFinto(), VadFinto()
    L.misura_ripresa = False
    # Spenta: come sempre
    a = ascolta(L, ("v", 30, CHIUDE), ("s", 40))
    verifica("spenta: chiusa dal silenzio fisso, nessun esito", L.chiusura == "silenzio"
             and L.fine_turno_esito is None and a is not None)
    cfg.fine_turno = "attiva"
    dec = DecisoreFinto()
    ant = ft.prepara_listener(L, cfg, log=lambda *_: None, decisore=dec)
    verifica("prepara_listener: «attiva» con il decisore → Anticipo nel Listener",
             isinstance(L.fine_turno, ft.Anticipo) and ant is L.fine_turno)
    a = ascolta(L, ("v", 25, SOSPESA), ("v", 5, CHIUDE), ("s", 40))
    e = L.fine_turno_esito or {}
    verifica("frase completa: chiusa prima («anticipata»), sotto i 700 ms di silenzio",
             L.chiusura == "anticipata" and e.get("chiusura") == "anticipata"
             and 250 <= e.get("silenzio_ms", 0) < 700 and e.get("verdetto") == "chiudi"
             and a is not None and len(a) // 512 < 30 + 10 + 22, e)
    # Il nome da solo (640 ms di voce, «finito» sicuro): sotto min_parlato_ms non chiude prima
    ascolta(L, ("v", 20, CHIUDE), ("s", 40))
    e = L.fine_turno_esito or {}
    verifica("contrario: frase cortissima (il nome da solo) → silenzio fisso, non anticipata",
             L.chiusura == "silenzio" and e.get("verdetto") == "fisso"
             and e.get("silenzio_ms", 0) >= 700, e)
    # Sospesa: 900 ms di pausa (oltre il silenzio fisso), poi il seguito: non la taglia
    a = ascolta(L, ("v", 15, SOSPESA), ("s", 28), ("v", 10, INCERTA), ("s", 40))
    e = L.fine_turno_esito or {}
    verifica("frase sospesa con una pausa di 900 ms: «non finito» aspetta, il seguito resta "
             "nella frase", a is not None and len(a) // 512 >= 15 + 28 + 10
             and L.chiusura == "silenzio" and e.get("verdetto") == "fisso"
             and 700 <= e.get("silenzio_ms", 0) < 900, (e, None if a is None else len(a) // 512))
    verifica("la pausa lunga è una pausa interna della misura", any(p >= 800 for p in
                                                                     L.pause_ms), L.pause_ms)
    # «non finito» fino alla fine: chiude al tetto dell'attesa (1500 ms)
    ascolta(L, ("v", 15, SOSPESA), ("s", 60))
    e = L.fine_turno_esito or {}
    verifica("«non finito» e nessuno continua: chiusa al tetto dell'attesa (1500 ms)",
             e.get("chiusura") == "attesa" and 1500 <= e.get("silenzio_ms", 0) < 1600, e)
    ascolta(L, ("v", 15, INCERTA), ("s", 40))
    e = L.fine_turno_esito or {}
    verifica("incerto: silenzio fisso", e.get("chiusura") == "silenzio"
             and 700 <= e.get("silenzio_ms", 0) < 750, e)
    # Guasto: silenzio fisso
    ft.prepara_listener(L, Config(), log=lambda *_: None)
    L.fine_turno = ft.Anticipo(DecisoreFinto(guasto=True), ft.Politica.da_cfg(cfg),
                               log=lambda *_: None)
    ascolta(L, ("v", 30, CHIUDE), ("s", 40))
    verifica("decisore guasto: silenzio fisso", L.chiusura == "silenzio"
             and (L.fine_turno_esito or {}).get("silenzio_ms", 0) >= 700, L.fine_turno_esito)
    L.fine_turno = ft.Anticipo(DecisoreFinto(ritardo=2.0), ft.Politica.da_cfg(cfg),
                               log=lambda *_: None)
    ascolta(L, ("v", 30, CHIUDE), ("s", 40))
    verifica("decisore lento: silenzio fisso", L.chiusura == "silenzio"
             and (L.fine_turno_esito or {}).get("verdetto") == "fisso", L.fine_turno_esito)
    L.fine_turno.sorvegliato.chiudi()
    cfg.fine_turno = "spenta"
    verifica("prepara_listener: spenta → None", ft.prepara_listener(L, cfg) is None
             and L.fine_turno is None)
    cfg.fine_turno, cfg.fine_turno_modello = "attiva", str(RADICE / "non-c-e.onnx")
    log = []
    verifica("attiva senza modello: None (silenzio fisso) e un messaggio",
             ft.prepara_listener(L, cfg, log=log.append) is None and len(log) == 1, log)
    cfg.fine_turno = "boh"
    verifica("modo sconosciuto: spenta", ft.modo(cfg) == "spenta")
    try:
        L.stream.abort()
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────── configurazione, catalogo, protocollo ───────────────────────────
def prova_config_catalogo_protocollo():
    from calliope.config import VALIDATORI, fuori_limiti
    cfg = Config()
    verifica("configurazione: spenta di serie, sonda 250, soglie 0,9 e 0,8, tetto 1500",
             (cfg.fine_turno, cfg.fine_turno_sonda_ms, cfg.fine_turno_soglia,
              cfg.fine_turno_soglia_attesa, cfg.fine_turno_attesa_max_ms)
             == ("spenta", 250, 0.9, 0.8, 1500))
    ok = VALIDATORI["fine_turno"]("Ombra") == "ombra"
    try:
        VALIDATORI["fine_turno"]("accesa")
        ok = False
    except ValueError:
        pass
    verifica("modo: spenta|ombra|attiva, altro rifiutato", ok)
    verifica("intervalli: soglia sotto 0,5 e tetto oltre 5 s rifiutati",
             fuori_limiti("fine_turno_soglia", 0.3) is not None
             and fuori_limiti("fine_turno_attesa_max_ms", 9000) is not None
             and fuori_limiti("fine_turno_sonda_ms", 250) is None)
    yaml = (RADICE / "calliope.yaml").read_text(encoding="utf-8")
    verifica("calliope.yaml rigenerato con i campi", "fine_turno: spenta" in yaml
             and "fine_turno_attesa_max_ms: 1500" in yaml)
    from calliope.installa.catalogo import DESCRIZIONI, catalogo
    a = catalogo(cfg).get("modello_fine_turno")
    verifica("catalogo: il modello con revisione fissa, SHA-256 e dimensione",
             a is not None and "modello_fine_turno" in DESCRIZIONI
             and ft.MODELLO_REVISIONE in a.files[0].url
             and a.files[0].sha256 == ft.MODELLO_SHA256
             and a.files[0].size == ft.MODELLO_BYTE
             and Path(a.files[0].dest).as_posix() == ft.MODELLO_PREDEFINITO)
    gi = (RADICE / ".gitignore").read_text(encoding="utf-8")
    verifica(".gitignore: models/fine_turno/", "models/fine_turno/" in gi)
    # Protocollo del satellite
    from calliope.satellite import protocollo as P
    from calliope.satellite.server import valida_evento
    verifica("PARAMETRI: modo e soglie al satellite", {"fine_turno", "fine_turno_soglia",
                                                      "fine_turno_sonda_ms",
                                                      "fine_turno_soglia_attesa",
                                                      "fine_turno_attesa_max_ms"}
             <= set(P.PARAMETRI))
    ev = valida_evento("frase_finita", {"id": 1, "fa_s": 2.0, "chiusura": "anticipata",
                                        "fine_turno": {"chiusura": "anticipata",
                                                       "silenzio_ms": 288, "p": 0.97,
                                                       "ms": 31.2, "verdetto": "chiudi",
                                                       "testo": "accendi la luce"}})
    verifica("frase_finita: chiusura «anticipata» e l'esito controllato (niente altri campi)",
             ev.get("chiusura") == "anticipata" and ev.get("fine_turno")
             == {"modo": "attiva", "chiusura": "anticipata", "verdetto": "chiudi",
                 "silenzio_ms": 288, "p": 0.97, "ms": 31.2}, ev)
    ev = valida_evento("frase_finita", {"id": 1, "fine_turno": {"chiusura": "boh",
                                                                "silenzio_ms": -5}})
    verifica("contrario: esito senza una chiusura nota → niente", "fine_turno" not in ev, ev)
    ev = valida_evento("frase_finita", {"id": 1, "fine_turno": {"chiusura": "silenzio",
                                                                "silenzio_ms": 99999,
                                                                "p": float("nan")}})
    verifica("contrario: numeri fuori misura scartati", ev.get("fine_turno")
             == {"modo": "attiva", "chiusura": "silenzio"}, ev)
    from calliope import pause
    verifica("pause.campi_frase accetta la chiusura «anticipata»",
             pause.campi_frase(None, None, "anticipata") == {"chiusura": "anticipata"})
    src = (RADICE / "calliope" / "satellite" / "client.py").read_text(encoding="utf-8")
    verifica("satellite in Python: prepara il Listener dopo i parametri e manda l'esito",
             "self._fine_turno()\n        self._modalita(m, parametri=False)" in src
             and '"fine_turno": L.fine_turno_esito' in src)


# ─────────────────────────── ciclo e riassunto ───────────────────────────
def prova_ciclo_riassunto():
    from calliope.ciclo import Ciclo, Turno
    c = object.__new__(Ciclo)
    cfg = Config()
    o = ft.OmbraFineTurno(cfg, decisore=DecisoreFinto(), vad=VadFinto(), log=lambda *_: None)
    c.s = SimpleNamespace(cfg=cfg, registry=SimpleNamespace(get=lambda n: None), fine_turno=o)
    c._fine_voce_prec, c._voce_prec = None, None
    ora = time.monotonic()
    c.listener = SimpleNamespace(started_at=ora - 3, ended_at=ora - 1.5, pause_ms=[],
                                 parlato_ms=900, chiusura="anticipata",
                                 fine_turno_esito={"modo": "attiva", "chiusura": "anticipata",
                                                   "silenzio_ms": 288},
                                 ripresa_s=lambda: None)
    a = c._misure_ascolto(Turno())
    verifica("ciclo: l'esito del Listener («attiva») nel campo ascolto",
             a.get("fine_turno", {}).get("chiusura") == "anticipata", a)
    c._fine_turno_job = o.valuta(audio(("s", 5), ("v", 30, CHIUDE), ("s", 25)))
    aspetta(lambda: c._fine_turno_job.done(), 3)
    rec = {"voce": {"nome": None}, "ascolto": a}
    c._chiudi_ascolto(rec)
    f = rec["ascolto"].get("fine_turno") or {}
    verifica("ciclo: l'ombra chiusa prima di scrivere il turno, con l'attiva dentro",
             f.get("modo") == "ombra" and f.get("attiva", {}).get("chiusura") == "anticipata"
             and c._fine_turno_job is None, f)
    o.ferma()
    rec2 = {"voce": {"nome": None}, "ascolto": {"canale": "locale"}}
    c._chiudi_ascolto(rec2)
    verifica("contrario: senza simulazione nessun campo", "fine_turno" not in rec2["ascolto"])
    src = (RADICE / "calliope" / "ciclo.py").read_text(encoding="utf-8")
    verifica("ciclo: la simulazione parte quando si apre il turno, solo per la voce",
             "self._fine_turno_job = ft.valuta(audio) if ft is not None else None" in src)
    # Riassunto
    turni = [{"ascolto": {"fine_turno": x}} for x in (
        {"modo": "ombra", "esito": "anticipo", "risparmio_ms": 440, "ms_max": 30},
        {"modo": "ombra", "esito": "anticipo", "risparmio_ms": 420, "ms_max": 40},
        {"modo": "ombra", "esito": "taglio", "ms_max": 35},
        {"modo": "ombra", "esito": "attesa", "costo_ms": 800},
        {"modo": "ombra", "esito": "taglio_evitato"},
        {"modo": "ombra", "esito": "come_prima",
         "attiva": {"modo": "attiva", "chiusura": "anticipata"}})] + [{"ascolto": {}}, {}]
    r = ft.riassunto(turni)
    verifica("riassunto: frasi, esiti, risparmio, costo, attiva",
             r["frasi"] == 6 and r["esiti"]["anticipo"] == 2 and r["esiti"]["taglio"] == 1
             and r["risparmio_ms"]["totale"] == 860 and r["costo_ms"]["totale"] == 800
             and r["attiva"] == {"anticipata": 1, "attesa": 0, "frasi": 1}, r)
    t = ft.testo(r)
    verifica("testo per `calliope stato --turni`", "Fine del turno (System 1" in t
             and "avrebbe tagliato 1" in t and "tagli evitati 1" in t, t)
    verifica("testo senza misure", "nessuna frase" in ft.testo(ft.riassunto([])))
    src = (RADICE / "calliope" / "stato.py").read_text(encoding="utf-8")
    verifica("stato --turni: la riga della fine del turno", "fine_turno_s1.testo(fine_r)" in src
             and '"fine_turno": fine_r' in src)


def main():
    prova_interfaccia()
    prova_log_mel()
    prova_politica()
    prova_ombra()
    prova_servizio_ombra()
    prova_listener()
    prova_config_catalogo_protocollo()
    prova_ciclo_riassunto()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
