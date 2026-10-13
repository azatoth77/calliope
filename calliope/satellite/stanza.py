"""
L'ascolto della stanza sul satellite (13/10, conversazione di stanza, passo 1: progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.1, decisione 0029).

Un **rubinetto** sui frame del microfono: il callback di `audio.Listener` ne copia ognuno anche
qui (`frame`, non blocca), e un thread con **il suo** Silero VAD (lo stato del VAD non si
condivide: `listen` lo azzera) taglia il parlato in segmenti chiusi dal silenzio (`silence_ms`,
come i comandi) o da un tetto corto (`stanza_segmento_max_s`, 20 s: per Whisper e per chi parla
è meglio un pezzo breve). Un segmento parte verso il server solo quando ha almeno
`min_speech_ms` di voce, e poi a pezzi mentre si parla (protocollo versione 3: `stanza_inizio`,
b"R", `stanza_fine`), così all'interpellazione il server ha già quasi tutto.

Il flusso dei comandi non cambia (wake word, b"A", finestra). **Half-duplex** come i comandi
(principio 8, il passo 5 del piano lo cambierà): mentre Calliope parla sulle casse di qui il
segmento in corso si butta (chiusura «voce», il server lo conta) e non se ne aprono altri.
Un segmento che si sovrappone a una frase dei comandi mandata al server porta l'id di
quell'ascolto (`ascolto`): il server lo lega al turno e non lo trascrive due volte.

`Segmentatore` è la logica pura (frame, probabilità del VAD, Calliope parla?) → messaggi: la
stessa del telefono (`AscoltoStanza` in schermi/pagina/telefono/voce.js) e delle prove.
"""

import collections
import itertools
import queue
import threading
import time

from . import protocollo as P

FRAME = 512
PEZZO_FRAME = 8              # i b"R" a gruppi di 8 frame (256 ms): meno messaggi, poco ritardo


class Segmentatore:
    """Frame per frame: `passo(frame, prob, occupato, ora)` → lista di messaggi da mandare,
    ciascuno («inizio», {…}) | («audio», id, [frame]) | («fine», {…})."""

    def __init__(self, cfg, ultimo_comando=None, max_s: float | None = None):
        self.cfg = cfg
        self.fms = FRAME / cfg.sample_rate * 1000
        self.max_s = float(max_s or getattr(cfg, "stanza_segmento_max_s", 20.0) or 20.0)
        # () → (monotonic dell'ultimo audio dei comandi mandato, id dell'ascolto) o None
        self.ultimo_comando = ultimo_comando
        self._ids = itertools.count(1)
        self.pre = collections.deque(maxlen=max(1, int(cfg.preroll_ms / self.fms)))
        self._azzera()
        # Misure (prove e terminale)
        self.segmenti = 0
        self.buttati = {"corto": 0, "voce": 0, "spenta": 0}

    def _azzera(self):
        self.parla, self.seg, self.voce, self.silenzio = False, [], 0, 0
        self.sid, self.inviati, self.t0 = None, 0, 0.0

    def _chiudi(self, chiusura: str, ora: float) -> list:
        out = []
        if self.sid is not None:
            if chiusura in ("silenzio", "lunga") and self.inviati < len(self.seg):
                out.append(("audio", self.sid, self.seg[self.inviati:]))
            ascolto = None
            u = self.ultimo_comando() if self.ultimo_comando is not None else None
            if u is not None and u[0] >= self.t0:
                ascolto = u[1]
            out.append(("fine", {"id": self.sid, "durata_s": round(len(self.seg) * self.fms / 1000, 3),
                                 "parlato_ms": int(self.voce * self.fms), "chiusura": chiusura,
                                 "ascolto": ascolto}))
            if chiusura in ("silenzio", "lunga"):
                self.segmenti += 1
            else:
                self.buttati[chiusura] = self.buttati.get(chiusura, 0) + 1
        elif self.parla and chiusura in ("silenzio", "lunga"):
            self.buttati["corto"] += 1
        self._azzera()
        return out

    def ferma(self, ora: float | None = None) -> list:
        """La stanza si spegne (pausa, ospiti, interruttore): il segmento in corso si butta."""
        self.pre.clear()
        return self._chiudi("spenta", ora or time.monotonic())

    def passo(self, frame, prob: float, occupato: bool, ora: float | None = None) -> list:
        cfg, ora = self.cfg, (time.monotonic() if ora is None else ora)
        if occupato:
            # Calliope parla qui: half-duplex, niente stanza (e niente pre-roll con la sua voce)
            self.pre.clear()
            return self._chiudi("voce", ora) if self.parla else []
        if not self.parla:
            self.pre.append(frame)
            if prob >= cfg.vad_threshold:
                self.parla, self.seg, self.voce, self.silenzio = True, list(self.pre), 1, 0
                self.t0 = ora - len(self.seg) * self.fms / 1000
                self.pre.clear()
            return []
        out = []
        self.seg.append(frame)
        if prob >= cfg.vad_threshold:
            self.voce += 1
        self.silenzio = self.silenzio + 1 if prob < cfg.vad_threshold - 0.15 else 0
        if self.sid is None and self.voce * self.fms >= cfg.min_speech_ms:
            self.sid = next(self._ids)
            out.append(("inizio", {"id": self.sid, "fa_s": round(ora - self.t0, 3)}))
            out.append(("audio", self.sid, list(self.seg)))
            self.inviati = len(self.seg)
        elif self.sid is not None and len(self.seg) - self.inviati >= PEZZO_FRAME:
            out.append(("audio", self.sid, self.seg[self.inviati:]))
            self.inviati = len(self.seg)
        if self.silenzio * self.fms >= cfg.silence_ms:
            out += self._chiudi("silenzio", ora)
        elif len(self.seg) * self.fms >= self.max_s * 1000:
            out += self._chiudi("lunga", ora)
        return out


class AscoltoStanza:
    """Il thread della stanza sul satellite Python. `manda(**campi)` e `manda_raw(bytes)` sono
    quelli della connessione; `occupato()` vero mentre le casse di qui suonano."""

    def __init__(self, cfg, manda, manda_raw, occupato, ultimo_comando=None, vad=None,
                 log=print):
        self.cfg = cfg
        self.manda, self.manda_raw, self.occupato = manda, manda_raw, occupato
        self.log = log
        self._vad = vad
        self.seg = Segmentatore(cfg, ultimo_comando)
        self.q: queue.Queue = queue.Queue(maxsize=600)      # ~19 s di audio
        self.attiva = False
        self.stato: dict = {}
        self.inviato = 0                     # byte di audio della stanza mandati
        self.persi = 0                       # frame persi (coda piena: il VAD non sta dietro)
        self._fermo = threading.Event()
        self._thread = None

    # ── dal server ──
    def imposta(self, stato: dict | None):
        """Lo stato mandato dal server (benvenuto o messaggio `stanza`)."""
        stato = stato if isinstance(stato, dict) else {}
        prima = self.attiva
        self.stato = stato
        try:
            self.seg.max_s = float(stato.get("segmento_max_s") or self.seg.max_s)
        except (TypeError, ValueError):
            pass
        self.attiva = bool(stato.get("attiva"))
        if self.attiva and self._thread is None:
            self._thread = threading.Thread(target=self._lavora, name="stanza", daemon=True)
            self._thread.start()
        if prima != self.attiva:
            motivo = stato.get("motivo") or ""
            self.log("[STANZA] Ascolto la stanza." if self.attiva else
                     "[STANZA] Ascolto della stanza fermo" + (f" ({motivo})." if motivo else "."))

    def ferma(self):
        self.attiva = False
        self._fermo.set()

    # ── dal callback del microfono: non blocca mai ──
    def frame(self, frame):
        if not self.attiva:
            return
        try:
            self.q.put_nowait(frame)
        except queue.Full:
            self.persi += 1

    # ── thread ──
    def _vad_pronto(self):
        if self._vad is None:
            from ..vad import SileroOnnx, carica_vad, modello_onnx
            p = modello_onnx(getattr(self.cfg, "vad_modello", None) or None)
            self._vad = (SileroOnnx(p) if p is not None
                         else carica_vad(self.cfg.vad_motore, self.cfg.vad_modello))
        return self._vad

    def _lavora(self):
        try:
            vad = self._vad_pronto()
        except Exception as e:  # noqa: BLE001 — senza VAD la stanza resta spenta
            self.log(f"[STANZA] Non parte: VAD non caricato ({type(e).__name__}: {e}).")
            self.attiva = False
            self._thread = None
            return
        while not self._fermo.is_set():
            try:
                frame = self.q.get(timeout=0.5)
            except queue.Empty:
                if not self.attiva and self.seg.parla:
                    self._esegui(self.seg.ferma())
                continue
            if not self.attiva:
                self._esegui(self.seg.ferma())
                continue
            if len(frame) != FRAME:
                continue
            try:
                prob = vad.prob(frame)
                occ = bool(self.occupato())
            except Exception:  # noqa: BLE001 — un frame non ferma la stanza
                continue
            self._esegui(self.seg.passo(frame, prob, occ))

    def _esegui(self, messaggi: list):
        for m in messaggi:
            if m[0] == "inizio":
                self.manda(tipo="stanza_inizio", **m[1])
            elif m[0] == "audio":
                pcm = P.a_pcm(m[2])
                if self.manda_raw(P.binario(P.STANZA, m[1], pcm)):
                    self.inviato += len(pcm)
            elif m[0] == "fine":
                self.manda(tipo="stanza_fine", **m[1])
