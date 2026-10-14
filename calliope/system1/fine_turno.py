"""
Il primo decisore System 1: **hai finito di parlare?** (14/10/2026, richiesta di Dario; scelta
del modello e misure in docs/ricerche/2026-10-14-system1-fine-turno.md).

Oggi la frase si chiude dopo `silence_ms` (700 ms) di silenzio, uguale per tutti
(`audio.Listener.listen`; pause e tagli misurati dal 07/10 in `calliope/pause.py`). Qui un
modello piccolo guarda **l'audio** della frase a pochi ms dall'inizio del silenzio e dice
«finito» o «non finito»: è Smart Turn v3.2 di Pipecat (BSD-2, ~8 M parametri, ONNX int8 da
8,7 MB, 23 lingue con l'italiano, 10–65 ms sulla CPU), che sente l'intonazione e il discorso
sospeso («accendi la luce in…») senza trascrivere niente.

Tre modi (`Config.fine_turno`):

- «spenta» (di serie): niente, nessun modello caricato.
- «ombra»: il turno si chiude come sempre; dopo la frase, in un thread suo e sul server (anche
  per le frasi dei satelliti e del telefono), `OmbraFineTurno` rigioca l'audio: un VAD suo
  ritrova le pause, a `fine_turno_sonda_ms` di ogni pausa chiede al decisore, e scrive nel
  registro dei turni (`ascolto.fine_turno`, solo numeri) cosa avrebbe deciso e quando: ms
  risparmiati, frasi che avrebbe tagliato (una pausa dentro la frase presa per la fine, o la
  persona che riprende dopo la chiusura: `OsservaRipresa`), frasi in cui avrebbe aspettato di
  più e se l'attesa avrebbe evitato un taglio. Riassunto in `calliope stato --turni`.
- «attiva»: nel `Listener` (in locale e sul satellite in Python, se ha il modello) a
  `fine_turno_sonda_ms` di silenzio la frase va al decisore senza fermare l'ascolto; «finito»
  con sicurezza ≥ `fine_turno_soglia` chiude subito (chiusura «anticipata»), «non finito» con
  sicurezza ≥ `fine_turno_soglia_attesa` sposta la soglia a `fine_turno_attesa_max_ms`; senza
  risposta in tempo, incerto, guasto o senza modello vale il silenzio fisso.

Principio 10: non è una regola sul testo. Il decisore guarda l'audio (prosodia e ritmo), cioè
ciò che il modello della voce non vede, e decide solo **quando** la frase va a Whisper, mai il
suo significato; la scelta di serie è il silenzio fisso, l'anticipo vale solo sopra una soglia
di sicurezza alta e un'attesa più lunga è limitata da un tetto. Le misure dell'ombra dicono se
e con quali soglie accenderlo.

Dipendenze: numpy e onnxruntime, già di base (principio 4). Il log-mel di Whisper che il modello
vuole è calcolato qui in numpy (lo stesso di `transformers.WhisperFeatureExtractor`, che non
serve installare: equivalenza in `prove/prova_fine_turno.py`).
"""
from __future__ import annotations

import concurrent.futures as cf
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import Decisione, Sorvegliato

FINITO, NON_FINITO = "finito", "non_finito"
SR = 16000
FINESTRA_S = 8                 # il modello guarda gli ultimi 8 s (meno: zeri davanti)
N_FFT, HOP, N_MEL = 400, 160, 80
FRAME = 512                    # i frame del VAD (32 ms)
MAX_SONDE = 24                 # domande al decisore per frase, al più (CPU limitata)

# Il modello: Smart Turn v3.2 per CPU (int8), dal repository di Pipecat su Hugging Face a una
# revisione fissa; SHA-256 e dimensione misurati il 14/10 sul file scaricato
MODELLO_NOME = "smart-turn-v3.2-cpu.onnx"
MODELLO_PREDEFINITO = f"models/fine_turno/{MODELLO_NOME}"
MODELLO_REPO = "pipecat-ai/smart-turn-v3"
MODELLO_REVISIONE = "f766f81d3cfdf7737ac64aad813d91bbfd56bf93"
MODELLO_BYTE = 8679182
MODELLO_SHA256 = "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f"

MODI = ("spenta", "ombra", "attiva")


# ─────────────────────────────── log-mel di Whisper in numpy ───────────────────────────────
def _hz_a_mel(f):
    """Scala mel di Slaney (come librosa con htk=False e Whisper)."""
    f = np.asarray(f, dtype=np.float64)
    f_sp = 200.0 / 3
    mel = f / f_sp
    min_log_hz = 1000.0
    min_log_mel = min_log_hz / f_sp
    logstep = np.log(6.4) / 27.0
    return np.where(f >= min_log_hz, min_log_mel + np.log(np.maximum(f, 1e-10) / min_log_hz)
                    / logstep, mel)


def _mel_a_hz(m):
    m = np.asarray(m, dtype=np.float64)
    f_sp = 200.0 / 3
    min_log_hz = 1000.0
    min_log_mel = min_log_hz / f_sp
    logstep = np.log(6.4) / 27.0
    return np.where(m >= min_log_mel, min_log_hz * np.exp(logstep * (m - min_log_mel)),
                    f_sp * m)


def filtri_mel(sr: int = SR, n_fft: int = N_FFT, n_mel: int = N_MEL) -> np.ndarray:
    """Il banco di filtri mel (n_mel × (n_fft/2+1)), triangoli con la normalizzazione di
    Slaney, da 0 a sr/2: lo stesso di Whisper."""
    fft_hz = np.linspace(0, sr / 2, 1 + n_fft // 2)
    mel = np.linspace(_hz_a_mel(0.0), _hz_a_mel(sr / 2), n_mel + 2)
    hz = _mel_a_hz(mel)
    fdiff = np.diff(hz)
    rampe = hz[:, None] - fft_hz[None, :]
    giu = -rampe[:-2] / fdiff[:-1, None]
    su = rampe[2:] / fdiff[1:, None]
    w = np.maximum(0, np.minimum(giu, su))
    w *= (2.0 / (hz[2:n_mel + 2] - hz[:n_mel]))[:, None]
    return w.astype(np.float32)


_FILTRI = None
_FINESTRA = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)


def prepara(audio) -> np.ndarray:
    """Gli ultimi FINESTRA_S secondi (zeri davanti se è più corta), normalizzati a media 0 e
    varianza 1 come fa `WhisperFeatureExtractor(do_normalize=True)` su quella finestra."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    n = FINESTRA_S * SR
    if len(x) > n:
        x = x[-n:]
    elif len(x) < n:
        x = np.concatenate([np.zeros(n - len(x), dtype=np.float32), x])
    x = x.astype(np.float64)
    x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)
    return x.astype(np.float32)


def log_mel(audio) -> np.ndarray:
    """(80, 800) float32: il log-mel di Whisper della finestra di 8 s (`prepara`)."""
    global _FILTRI
    if _FILTRI is None:
        _FILTRI = filtri_mel()
    x = prepara(audio)
    pad = N_FFT // 2
    x = np.pad(x, (pad, pad), mode="reflect")
    n_frame = 1 + (len(x) - N_FFT) // HOP
    quadri = np.lib.stride_tricks.as_strided(
        x, shape=(n_frame, N_FFT), strides=(x.strides[0] * HOP, x.strides[0]))
    spettro = np.abs(np.fft.rfft(quadri * _FINESTRA, axis=1)) ** 2       # (801, 201)
    # In float32 e contiguo: il prodotto in float64 sulla trasposta costava ~15 ms
    mel = _FILTRI @ np.ascontiguousarray(spettro.T, dtype=np.float32)   # (80, 801)
    lm = np.log10(np.maximum(mel, 1e-10))[:, :-1]
    lm = np.maximum(lm, lm.max() - 8.0)
    return ((lm + 4.0) / 4.0).astype(np.float32)


# ─────────────────────────────── il decisore ───────────────────────────────
class SmartTurn:
    """Smart Turn v3 (Pipecat) in onnxruntime: `decide(audio)` sulla frase fin qui (16 kHz,
    float32; contano gli ultimi 8 s). Due thread: sul portatile (14/10) il modello impiega
    50 ms con uno, 31 con due, 22 con quattro, e la CPU serve anche a Whisper e Piper; il
    log-mel in numpy ~7 ms."""

    scelte = (FINITO, NON_FINITO)

    def __init__(self, percorso, thread: int = 2):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = max(1, int(thread))
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(percorso), sess_options=opts,
                                            providers=["CPUExecutionProvider"])
        self.ingresso = self.session.get_inputs()[0].name
        self.nome = Path(str(percorso)).stem

    def prob(self, audio) -> float:
        """La probabilità che il turno sia finito (uscita sigmoide del modello)."""
        f = log_mel(audio)[None, ...]
        out = self.session.run(None, {self.ingresso: f})[0]
        return float(np.asarray(out).reshape(-1)[0])

    def decide(self, audio) -> Decisione:
        t0 = time.perf_counter()
        p = self.prob(audio)
        ms = (time.perf_counter() - t0) * 1000
        return (Decisione(FINITO, p, ms, p) if p >= 0.5
                else Decisione(NON_FINITO, 1.0 - p, ms, p))


def percorso_modello(cfg) -> Path:
    return Path(str(getattr(cfg, "fine_turno_modello", None) or MODELLO_PREDEFINITO))


def carica(cfg, log=print):
    """Il decisore della configurazione, o None (modello mancante o che non si carica: vale il
    silenzio fisso, lo si dice una volta)."""
    p = percorso_modello(cfg)
    if not p.is_file():
        log(f"   [SYSTEM1] fine del turno: manca il modello ({p}); resta il silenzio fisso. "
            f"Si scarica con: python -m calliope.stato --installa modello_fine_turno")
        return None
    try:
        return SmartTurn(p)
    except Exception as e:  # noqa: BLE001
        log(f"   [SYSTEM1] fine del turno: il modello non si carica ({type(e).__name__}: {e});"
            f" resta il silenzio fisso")
        return None


# ─────────────────────────────── la politica ───────────────────────────────
@dataclass(frozen=True)
class Politica:
    """Quando chiedere e cosa farne. `verdetto(dec)`: «chiudi», «aspetta» o «fisso»."""
    silence_ms: int = 700
    sonda_ms: int = 250
    soglia: float = 0.9              # «finito» con sicurezza ≥: chiude subito
    soglia_attesa: float = 0.8       # «non finito» con sicurezza ≥: aspetta fino al tetto
    attesa_max_ms: int = 1500
    # Sotto questo parlato non si chiude mai prima: il nome da solo («Calliope,» e una pausa
    # prima della domanda) esce «finito» anche con Piper (14/10, p 0,92), e chiuderlo lì
    # perderebbe la domanda detta mentre Calliope risponde «Sì?»
    min_parlato_ms: int = 800

    @classmethod
    def da_cfg(cls, cfg) -> "Politica":
        return cls(silence_ms=int(cfg.silence_ms),
                   sonda_ms=int(getattr(cfg, "fine_turno_sonda_ms", 250)),
                   soglia=float(getattr(cfg, "fine_turno_soglia", 0.9)),
                   soglia_attesa=float(getattr(cfg, "fine_turno_soglia_attesa", 0.8)),
                   attesa_max_ms=int(getattr(cfg, "fine_turno_attesa_max_ms", 1500)),
                   min_parlato_ms=int(getattr(cfg, "fine_turno_min_parlato_ms", 800)))

    def verdetto(self, d: Decisione | None, parlato_ms: float | None = None) -> str:
        if d is None:
            return "fisso"
        if d.scelta == FINITO and d.sicurezza >= self.soglia:
            if parlato_ms is not None and parlato_ms < self.min_parlato_ms:
                return "fisso"           # frase cortissima: il nome da solo, per esempio
            return "chiudi"
        if d.scelta == NON_FINITO and d.sicurezza >= self.soglia_attesa:
            return "aspetta"
        return "fisso"

    def frame_sonda(self, frame_ms: float) -> int:
        return max(1, math.ceil(self.sonda_ms / frame_ms))


def modo(cfg) -> str:
    m = str(getattr(cfg, "fine_turno", "spenta") or "spenta").strip().lower()
    return m if m in MODI else "spenta"


# ─────────────────────────────── «attiva»: nel Listener ───────────────────────────────
class Anticipo:
    """La fine del turno decisa mentre si ascolta (`Listener.listen`, modo «attiva»).

    A `sonda_ms` di silenzio `sonda(frames)` manda la frase al decisore senza aspettare;
    `verdetto()` restituisce «chiudi», «aspetta» o «fisso» appena c'è la risposta (None prima);
    la voce che riprende chiama `annulla()` (la risposta di prima non vale più). L'esito
    dell'ultima frase (`esito`) va nel registro dei turni."""

    def __init__(self, decisore, politica: Politica, log=print):
        self.sorvegliato = (decisore if isinstance(decisore, Sorvegliato)
                            else Sorvegliato(decisore, log))
        self.politica = politica
        self._fut: cf.Future | None = None
        self._dec: Decisione | None = None
        self._parlato_ms: float | None = None
        self.esito: dict | None = None

    def nuova_frase(self):
        self.annulla()
        self.esito = None

    def annulla(self):
        if self._fut is not None:
            self._fut.cancel()
        self._fut, self._dec = None, None

    def sonda(self, frames, parlato_ms: float | None = None):
        """La frase fin qui (lista di frame o array) al decisore: gli ultimi 8 s bastano.
        `parlato_ms`: la voce fin qui (sotto `min_parlato_ms` non si chiude prima)."""
        self._parlato_ms = parlato_ms
        n = FINESTRA_S * SR // FRAME + 1
        if isinstance(frames, list):
            audio = np.concatenate(frames[-n:]) if frames else np.zeros(0, np.float32)
        else:
            audio = np.asarray(frames, dtype=np.float32)[-FINESTRA_S * SR:]
        self._dec = None
        self._fut = self.sorvegliato.avvia(audio)

    def verdetto(self) -> str | None:
        if self._dec is None and self._fut is not None and self._fut.done():
            from . import risposta
            self._dec = risposta(self._fut)
            self._fut = None
            if self._dec is None:
                return "fisso"
        if self._dec is None:
            return None
        return self.politica.verdetto(self._dec, self._parlato_ms)

    def chiusa(self, come: str, silenzio_ms: int):
        """La frase si è chiusa: come («anticipata», «silenzio», «attesa», «lunga») e dopo
        quanti ms di silenzio. Solo numeri."""
        d = self._dec
        self.esito = {"modo": "attiva", "chiusura": come, "silenzio_ms": int(silenzio_ms),
                      "verdetto": (self.politica.verdetto(d, self._parlato_ms) if d
                                   else "fisso")}
        if d is not None:
            self.esito["p"] = round(float(d.prob if d.prob is not None else 0.0), 3)
            self.esito["ms"] = round(d.ms, 1)
        self.annulla()


CHIUSURE_ATTIVA = ("anticipata", "silenzio", "attesa", "lunga")
VERDETTI = ("chiudi", "aspetta", "fisso")


def campi_esito(d) -> dict | None:
    """L'esito della fine del turno mandato da un satellite (`frase_finita.fine_turno`): solo
    i campi noti, con tipi e limiti giusti (dati del satellite, mai istruzioni), o None."""
    if not isinstance(d, dict):
        return None
    out = {"modo": "attiva"}
    if d.get("chiusura") in CHIUSURE_ATTIVA:
        out["chiusura"] = d["chiusura"]
    if d.get("verdetto") in VERDETTI:
        out["verdetto"] = d["verdetto"]
    for k, alto in (("silenzio_ms", 10_000), ("p", 1.0), ("ms", 10_000)):
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) \
                and 0 <= v <= alto:
            out[k] = int(v) if k == "silenzio_ms" else round(float(v), 3)
    return out if "chiusura" in out else None


def prepara_listener(listener, cfg, log=print, decisore=None):
    """Mette (o toglie) l'`Anticipo` nel Listener secondo `cfg.fine_turno`: «attiva» con il
    modello presente; altrimenti None (silenzio fisso). Il decisore si carica una volta."""
    if modo(cfg) != "attiva":
        listener.fine_turno = None
        return None
    pol = Politica.da_cfg(cfg)
    vecchio = getattr(listener, "fine_turno", None)
    if isinstance(vecchio, Anticipo):
        vecchio.politica = pol
        return vecchio
    dec = decisore if decisore is not None else carica(cfg, log)
    if dec is None:
        listener.fine_turno = None
        return None
    listener.fine_turno = Anticipo(dec, pol, log)
    log(f"   [SYSTEM1] fine del turno attiva ({getattr(dec, 'nome', 'decisore')}): chiude a "
        f"{pol.sonda_ms} ms se «finito» ≥ {pol.soglia:.2f}, aspetta fino a "
        f"{pol.attesa_max_ms} ms se «non finito» ≥ {pol.soglia_attesa:.2f}")
    return listener.fine_turno


# ─────────────────────────────── «ombra»: rigiocare la frase ───────────────────────────────
def silenzi(audio, vad, soglia: float) -> tuple[int | None, list[bool]]:
    """(primo frame di voce, [silenzioso per ogni frame dopo]) con la stessa regola di
    `Listener.listen`: la frase parte a prob ≥ soglia, un frame è silenzioso sotto soglia−0,15."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    try:
        vad.reset_states()
    except Exception:  # noqa: BLE001
        pass
    inizio, flag = None, []
    for i in range(len(x) // FRAME):
        p = vad.prob(x[i * FRAME:(i + 1) * FRAME])
        if inizio is None:
            if p >= soglia:
                inizio = i
            continue
        flag.append(p < soglia - 0.15)
    return inizio, flag


def simula(audio, decide, politica: Politica, inizio: int | None, flag: list[bool],
           frame_ms: float = FRAME / SR * 1000) -> dict:
    """Cosa avrebbe deciso il decisore su questa frase, dai silenzi (`silenzi`).

    A `sonda_ms` di ogni pausa chiede a `decide(audio fin lì)` (Decisione o None). Una pausa
    che arriva a `silence_ms`, o che dura fino alla fine dell'audio, è la **chiusura**; le
    altre sono **pause interne** (la persona ha continuato). Restituisce solo numeri:
    {"sonde", "interne": [{"a_ms", "p"}], "taglio_ms" (prima pausa interna che avrebbe chiuso),
     "chiusura": {"p", "verdetto", "ms"} | None, "ms_max"}."""
    out = {"sonde": 0, "interne": [], "taglio_ms": None, "chiusura": None, "ms_max": 0.0}
    if inizio is None:
        return out
    n_sonda = politica.frame_sonda(frame_ms)
    n_chiude = max(1, math.ceil(politica.silence_ms / frame_ms))
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    i, n = 0, len(flag)
    while i < n:
        if not flag[i]:
            i += 1
            continue
        j = i
        while j < n and flag[j]:
            j += 1
        corsa = j - i
        finale = j >= n or corsa >= n_chiude
        if corsa >= n_sonda and out["sonde"] < MAX_SONDE:
            fine = (inizio + 1 + i + n_sonda) * FRAME
            d = decide(x[max(0, fine - FINESTRA_S * SR):fine])
            out["sonde"] += 1
            if d is not None:
                out["ms_max"] = max(out["ms_max"], round(d.ms, 1))
            p = None if d is None else round(float(d.prob if d.prob is not None else
                                                   (d.sicurezza if d.scelta == FINITO
                                                    else 1 - d.sicurezza)), 3)
            a_ms = int(round((i + 1) * frame_ms))   # dalla prima voce all'inizio della pausa
            if finale:
                out["chiusura"] = {"a_ms": a_ms, "p": p,
                                   "verdetto": politica.verdetto(d, a_ms),
                                   "ms": None if d is None else round(d.ms, 1)}
                break
            out["interne"].append({"a_ms": a_ms, "p": p, "pausa_ms": int(round(corsa *
                                                                               frame_ms))})
            if out["taglio_ms"] is None and politica.verdetto(d, a_ms) == "chiudi":
                out["taglio_ms"] = a_ms
        elif finale:
            break
        i = j
    return out


def esito(sim: dict, ripresa_s: float | None, politica: Politica) -> dict:
    """La simulazione confrontata con ciò che è successo (la ripresa dopo la chiusura, da
    `OsservaRipresa`). `esito`:
    - «taglio»: una pausa interna presa per la fine (avrebbe tagliato una frase che continuava);
    - «anticipo»: «finito» sicuro alla chiusura e nessuna ripresa: `risparmio_ms`;
    - «anticipo_ripresa»: «finito» sicuro, ma la persona ha ripreso (il fisso ha tagliato
      anche lui: chiudere prima non salva niente);
    - «taglio_evitato»: «non finito» sicuro e la ripresa entro il tetto dell'attesa;
    - «attesa»: «non finito» sicuro ma nessuno ha ripreso in tempo: `costo_ms`;
    - «come_prima»: incerto, lento o guasto: vale il silenzio fisso;
    - «nessuna»: il VAD dell'ombra non ha trovato la chiusura."""
    out = {"sonde": sim.get("sonde", 0), "interne": len(sim.get("interne") or ()),
           "ms_max": sim.get("ms_max")}
    ch = sim.get("chiusura")
    if ch is not None:
        out["p"] = ch.get("p")
    if sim.get("taglio_ms") is not None:
        out.update(esito="taglio", taglio_ms=sim["taglio_ms"])
        return out
    if ch is None:
        out["esito"] = "nessuna"
        return out
    v = ch.get("verdetto")
    if v == "chiudi":
        if ripresa_s is not None:
            out["esito"] = "anticipo_ripresa"
        else:
            out["esito"] = "anticipo"
            out["risparmio_ms"] = int(max(0, politica.silence_ms - politica.sonda_ms
                                          - (ch.get("ms") or 0)))
    elif v == "aspetta":
        if ripresa_s is not None and ripresa_s * 1000 <= politica.attesa_max_ms:
            out["esito"] = "taglio_evitato"
        else:
            out["esito"] = "attesa"
            out["costo_ms"] = int(max(0, politica.attesa_max_ms - politica.silence_ms))
    else:
        out["esito"] = "come_prima"
    return out


class OmbraFineTurno:
    """Il modo «ombra» sul server: dopo ogni frase, in un thread suo, rigioca l'audio con un VAD
    suo e chiede al decisore cosa avrebbe fatto (`valuta`); prima di scrivere il turno `chiudi`
    mette l'esito nel campo `ascolto` del registro. Non tocca mai la frase né il turno."""

    def __init__(self, cfg, decisore=None, vad=None, log=print):
        self.cfg = cfg
        self.log = log
        self.politica = Politica.da_cfg(cfg)
        dec = decisore if decisore is not None else carica(cfg, log)
        self.decisore = Sorvegliato(dec, log) if dec is not None else None
        self._vad = vad
        self._pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="fine-turno")
        self.valutate = 0

    @property
    def pronta(self) -> bool:
        return self.decisore is not None and not self.decisore.spento

    def _vad_suo(self):
        if self._vad is None:
            from ..vad import SileroOnnx, carica_vad, modello_onnx
            p = modello_onnx(getattr(self.cfg, "vad_modello", None))
            self._vad = (SileroOnnx(p) if p is not None
                         else carica_vad(self.cfg.vad_motore, self.cfg.vad_modello))
        return self._vad

    def _gira(self, audio) -> dict:
        t0 = time.perf_counter()
        inizio, flag = silenzi(audio, self._vad_suo(), float(self.cfg.vad_threshold))

        def decide(x):
            # Nel thread dell'ombra: il decisore sorvegliato, con un tempo largo (l'ombra non
            # ha fretta, ma un decisore bloccato non deve tenerla ferma per sempre)
            return self.decisore.chiedi(x, 2.0)
        sim = simula(audio, decide, self.politica, inizio, flag)
        sim["ombra_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self.valutate += 1
        return sim

    def valuta(self, audio) -> cf.Future | None:
        if not self.pronta or audio is None or not len(audio):
            return None
        try:
            return self._pool.submit(self._gira, np.asarray(audio, dtype=np.float32).copy())
        except RuntimeError:
            return None

    def chiudi(self, a: dict, fut: cf.Future | None, attesa_s: float = 0.05):
        """L'esito nel campo `ascolto` del turno (`a`), se la simulazione è finita; altrimenti
        «in_ritardo». La ripresa (`a["ripresa_s"]`) c'è già: `Ciclo._chiudi_ascolto`."""
        if fut is None or not isinstance(a, dict):
            return
        try:
            sim = fut.result(timeout=attesa_s)
        except cf.TimeoutError:
            fut.cancel()
            a["fine_turno"] = {"modo": "ombra", "esito": "in_ritardo"}
            return
        except Exception as e:  # noqa: BLE001 — una misura non ferma il turno
            a["fine_turno"] = {"modo": "ombra", "esito": "errore", "errore": type(e).__name__}
            return
        r = esito(sim, a.get("ripresa_s"), self.politica)
        r["modo"] = "ombra"
        r["ombra_ms"] = sim.get("ombra_ms")
        prima = a.get("fine_turno")
        if isinstance(prima, dict) and prima.get("modo") == "attiva":
            r["attiva"] = prima          # cosa ha fatto davvero il Listener (in locale)
        a["fine_turno"] = r

    def ferma(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
        if self.decisore is not None:
            self.decisore.chiudi()


def load_fine_turno(cfg, log=print) -> OmbraFineTurno | None:
    """Il servizio dell'ombra per `main.py`: None con il modo «spenta» o senza modello."""
    if modo(cfg) == "spenta":
        return None
    o = OmbraFineTurno(cfg, log=log)
    if not o.pronta:
        return None
    log(f"   [SYSTEM1] fine del turno in {modo(cfg)}: {o.decisore.nome}, sonda a "
        f"{o.politica.sonda_ms} ms, soglia {o.politica.soglia:.2f} (misure in "
        f"`calliope stato --turni`)")
    return o


# ─────────────────────────────── riassunto ───────────────────────────────
ESITI = ("anticipo", "anticipo_ripresa", "taglio", "taglio_evitato", "attesa", "come_prima",
         "nessuna", "in_ritardo", "errore")


def _q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))] if v else None


def riassunto(turni: list[dict]) -> dict:
    """Dai turni con `ascolto.fine_turno`: quanti per esito, ms risparmiati (mediana e
    totale), costo delle attese, tempi del decisore, chiusure anticipate vere (attiva)."""
    conta = {k: 0 for k in ESITI}
    risparmi, costi, ms, attive = [], [], [], {"anticipata": 0, "attesa": 0, "frasi": 0}
    n = 0
    for t in turni:
        a = t.get("ascolto") if isinstance(t.get("ascolto"), dict) else None
        f = a.get("fine_turno") if a else None
        if not isinstance(f, dict):
            continue
        n += 1
        e = f.get("esito")
        if e in conta:
            conta[e] += 1
        if isinstance(f.get("risparmio_ms"), (int, float)):
            risparmi.append(f["risparmio_ms"])
        if isinstance(f.get("costo_ms"), (int, float)):
            costi.append(f["costo_ms"])
        if isinstance(f.get("ms_max"), (int, float)) and f["ms_max"]:
            ms.append(f["ms_max"])
        at = f.get("attiva") if f.get("modo") != "attiva" else f
        if isinstance(at, dict):
            attive["frasi"] += 1
            if at.get("chiusura") in ("anticipata", "attesa"):
                attive[at["chiusura"]] += 1
    return {"frasi": n, "esiti": conta,
            "risparmio_ms": {"mediana": _q(risparmi, .5), "totale": int(sum(risparmi))},
            "costo_ms": {"totale": int(sum(costi))},
            "decisore_ms": {"p50": _q(ms, .5), "p90": _q(ms, .9)},
            "attiva": attive}


def testo(r: dict) -> str:
    if not r.get("frasi"):
        return ("Fine del turno (System 1): nessuna frase misurata (fine_turno: spenta, o "
                "manca il modello).")
    e = r["esiti"]
    errori = e["taglio"] + e["anticipo_ripresa"]
    ms = r["decisore_ms"]
    righe = [f"Fine del turno (System 1, ombra): {r['frasi']} frasi; avrebbe chiuso prima in "
             f"{e['anticipo']} (mediana {r['risparmio_ms']['mediana'] or 0} ms, in tutto "
             f"{r['risparmio_ms']['totale'] / 1000:.1f} s risparmiati)",
             f"    avrebbe tagliato {e['taglio']} (pausa dentro la frase) + "
             f"{e['anticipo_ripresa']} (la persona ha ripreso) = {errori}; avrebbe aspettato "
             f"di più in {e['attesa'] + e['taglio_evitato']} (tagli evitati "
             f"{e['taglio_evitato']}, attesa inutile {r['costo_ms']['totale'] / 1000:.1f} s)",
             f"    come prima {e['come_prima']}, senza chiusura {e['nessuna']}, in ritardo "
             f"{e['in_ritardo']}, errori {e['errore']}; decisore p50 "
             f"{ms['p50'] if ms['p50'] is not None else '—'} ms, p90 "
             f"{ms['p90'] if ms['p90'] is not None else '—'} ms"]
    at = r.get("attiva") or {}
    if at.get("frasi"):
        righe.append(f"    attiva: {at['frasi']} frasi, {at['anticipata']} chiuse prima, "
                     f"{at['attesa']} con l'attesa lunga")
    return "\n".join(righe)
