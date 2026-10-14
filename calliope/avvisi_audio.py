"""
L'anello dell'audio per gli avvisi di pericolo (14/10/2026, decisione di Dario che cambia la
decisione 0029 punto 4; documento d'area docs/aree/minori.md).

Un avviso di pericolo al tutore porta, **solo sul suo schermo personale**, la trascrizione di
ciò che ha detto il minore (con un po' di contesto, chi ha detto cosa) e, se `avvisi_audio` è
acceso, il file audio di quelle frasi. Oggi l'audio non va mai su disco (turni e stanza: l'audio
resta in RAM per la trascrizione e poi si butta). L'eccezione è ristretta:

- **In memoria**, un anello piccolo (`avvisi_audio_anello_min` minuti, al più
  `avvisi_audio_anello_mb` MB, in G.711 μ-law: 16 kB al secondo) con l'audio dei segmenti della
  stanza e dei turni **in cui parla un minore** riconosciuto (voce sopra soglia o zona grigia), e
  nella stanza quelli degli adulti di casa riconosciuti **mentre un minore è presente** su quel
  satellite (il contesto breve). Mai voci non riconosciute (potrebbero essere ospiti), mai le
  frasi di Calliope, mai durante la pausa per gli ospiti (lì non nasce nessun segmento).
- **Su disco** solo quando nasce un avviso di pericolo (i cancelli dei turni, il guardiano a
  posteriori in `attiva`): i soli segmenti del segnale, con `avvisi_audio_contesto_s` secondi di
  contesto, in un WAV μ-law nel **cassetto del tutore** (calliope/cassetto.py: file 600, fuori da
  git), con la sua scadenza (`avvisi_audio_giorni`). In ombra niente su disco: solo il conto
  «avrei salvato N s» nelle misure della stanza.
- «Dimentica» della stanza toglie dall'anello l'audio di quel satellite (e il materiale degli
  avvisi nati lì); `calliope conserva --svuota` toglie gli audio degli avvisi.

Solo libreria standard e numpy (già una dipendenza di base): nessuna libreria nativa nuova.
"""

from __future__ import annotations

import collections
import struct
import threading
import time
from dataclasses import dataclass

SR = 16000


@dataclass
class Pezzo:
    luogo: str             # «stanza:<sat>» o «turno:<chiave della corsia>»
    persona: str | None    # id del profilo
    minore: bool
    inizio: float          # epoch
    fine: float            # epoch
    dati: bytes            # μ-law a 16 kHz
    chiave: object = None  # il seq della riga della stanza (o None)

    @property
    def secondi(self) -> float:
        return len(self.dati) / float(SR)


class Anello:
    """L'audio recente dei minori (e del contesto breve), solo in memoria. Thread-safe."""

    def __init__(self, minuti: float = 30.0, mb: float = 16.0, orologio=time.time):
        self.max_s = max(0.0, float(minuti)) * 60.0
        self.max_byte = int(max(0.0, float(mb)) * 1_000_000)
        self.orologio = orologio
        self._lock = threading.Lock()
        self._pezzi: collections.deque = collections.deque()
        self._byte = 0
        self.buttati = 0              # pezzi usciti per il tetto in MB (non per il tempo)

    def _pota(self):
        ora = self.orologio()
        while self._pezzi and (ora - self._pezzi[0].fine > self.max_s):
            self._byte -= len(self._pezzi.popleft().dati)
        while self._pezzi and self._byte > self.max_byte:
            self._byte -= len(self._pezzi.popleft().dati)
            self.buttati += 1

    def metti(self, luogo: str, persona: str | None, minore: bool, inizio: float, fine: float,
              audio, sr: int = SR, chiave=None) -> bool:
        """Un pezzo di audio (float32 in [-1, 1] o int16) nell'anello. False se non entra
        (vuoto, frequenza diversa, anello a zero)."""
        if self.max_s <= 0 or self.max_byte <= 0 or audio is None:
            return False
        import numpy as np
        a = np.asarray(audio)
        if a.size == 0 or int(sr) != SR:
            return False
        if a.dtype == np.int16:
            a = a.astype(np.float32) / 32768.0
        from .conserva import mulaw
        dati = mulaw(a)
        if len(dati) > self.max_byte:
            return False
        with self._lock:
            self._pezzi.append(Pezzo(str(luogo), persona, bool(minore), float(inizio),
                                     float(fine), dati, chiave))
            self._byte += len(dati)
            self._pota()
        return True

    def prendi(self, luogo: str | None = None, persona: str | None = None,
               da: float | None = None, a: float | None = None) -> list[Pezzo]:
        """I pezzi (in ordine di tempo) di quel luogo e/o di quella persona che toccano
        l'intervallo [da, a]."""
        with self._lock:
            self._pota()
            out = [p for p in self._pezzi
                   if (luogo is None or p.luogo == luogo)
                   and (persona is None or p.persona == persona)
                   and (da is None or p.fine >= da) and (a is None or p.inizio <= a)]
        return sorted(out, key=lambda p: p.inizio)

    def togli(self, luogo: str | None = None, persona: str | None = None) -> int:
        """«Dimentica»: via i pezzi di un luogo (o di una persona, o tutti). Quanti."""
        with self._lock:
            tieni = collections.deque(p for p in self._pezzi
                                      if not ((luogo is None or p.luogo == luogo)
                                              and (persona is None or p.persona == persona)))
            n = len(self._pezzi) - len(tieni)
            self._pezzi = tieni
            self._byte = sum(len(p.dati) for p in tieni)
        return n

    def stato(self) -> dict:
        with self._lock:
            self._pota()
            return {"pezzi": len(self._pezzi), "secondi": round(self._byte / SR, 1),
                    "mb": round(self._byte / 1_000_000, 2), "buttati": self.buttati}


def secondi(pezzi) -> float:
    return round(sum(p.secondi for p in pezzi or ()), 1)


def wav(pezzi, pausa_s: float = 0.4) -> bytes:
    """Un WAV μ-law (formato 7, come calliope/conserva.py) con i pezzi uno dopo l'altro e una
    breve pausa tra l'uno e l'altro."""
    from .conserva import mulaw
    silenzio = mulaw([0.0]) * int(SR * max(0.0, pausa_s))     # μ-law dello zero
    dati = silenzio.join(p.dati for p in pezzi or ())
    n = len(dati)
    fmt = struct.pack("<HHIIHHH", 7, 1, SR, SR, 1, 8, 0)
    pad = b"\x00" if n % 2 else b""
    corpo = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
             + b"fact" + struct.pack("<II", 4, n) + b"data" + struct.pack("<I", n) + dati + pad)
    return b"RIFF" + struct.pack("<I", len(corpo)) + corpo


# Il servizio del processo (main.py, con `avvisi_audio` acceso); None = spento
_ANELLO: dict = {"anello": None}


def prepara(cfg) -> Anello | None:
    if not getattr(cfg, "avvisi_audio", False) or not getattr(cfg, "minori_enabled", True):
        _ANELLO["anello"] = None
        return None
    _ANELLO["anello"] = Anello(float(getattr(cfg, "avvisi_audio_anello_min", 30.0) or 0),
                               float(getattr(cfg, "avvisi_audio_anello_mb", 16.0) or 0))
    return _ANELLO["anello"]


def anello() -> Anello | None:
    return _ANELLO.get("anello")
