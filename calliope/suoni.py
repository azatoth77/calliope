"""
Suoni di inizio e fine ascolto (04/10, docs/ricerche/2026-10-04-personalita-wake-word.md).

Con `suoni_ascolto` (acceso dalla modalità «startrek») chi ha il microfono suona un breve
segnale quando scatta la wake word («ti ascolto») e uno quando la frase è presa («ricevuto»):
le casse di questo PC, il satellite o il telefono, ognuno in locale, così il segnale arriva
subito e non passa dalla rete.

I suoni originali di Star Trek sono di Paramount/CBS: non stanno nel repository e il codice
non li scarica. Quelli di qui sono sintetici, fatti di pochi toni puri con un inviluppo
morbido, *ispirati* ai bip del computer di bordo: tre note che salgono per l'inizio, due che
scendono per la fine. Chi vuole un altro suono mette un suo WAV in `suono_inizio_ascolto` /
`suono_fine_ascolto` (calliope.locale.yaml, fuori da git).

Half-duplex: il segnale d'inizio suona mentre la persona sta ancora parlando («Computer, che
ore sono?»), quindi finisce nella frase che va a Whisper. Per questo è corto (~0,2 s), sopra
i 1300 Hz (lontano dalla voce, sotto il passa-banda dei microfoni da webcam che arriva a
~7,8 kHz) e non forte: misure nel rapporto. Il segnale di fine suona a frase chiusa, quando
il microfono non registra più per Whisper. Un file dell'utente si taglia a 1,5 s.

Solo numpy e la libreria standard (`wave`): niente dipendenze native nuove.
"""
from __future__ import annotations

import base64
import os
import wave

import numpy as np

INIZIO, FINE = "inizio", "fine"
MAX_FILE_S = 1.5             # un file più lungo si taglia: coprirebbe la frase che segue
# «nessuno» al posto del percorso spegne quel segnale: il bip d'inizio finisce nella frase che
# va a Whisper (misura nel rapporto), chi lo trova di troppo tiene solo quello di fine
SPENTO = ("nessuno", "no", "off", "spento")

# (frequenza Hz, durata s) delle note; tra una nota e l'altra 15 ms di silenzio
_NOTE = {
    INIZIO: [(1318.5, 0.055), (1760.0, 0.055), (2093.0, 0.085)],    # mi6, la6, do7: sale
    FINE: [(2093.0, 0.06), (1568.0, 0.09)],                         # do7, sol6: scende
}


def sintetico(tipo: str, rate: int, volume: float = 0.35) -> np.ndarray:
    """Il segnale sintetico `tipo` (INIZIO o FINE) in float32 a `rate`."""
    parti = []
    vol = float(min(1.0, max(0.0, volume)))
    for freq, dur in _NOTE[tipo]:
        t = np.arange(int(rate * dur)) / rate
        # Attacco 5 ms e coda 25 ms: senza, i bordi fanno un clic che il VAD sente
        env = np.minimum(1.0, np.minimum(t / 0.005, (t[-1] - t) / 0.025))
        # Un'armonica leggera: il bip suona meno «da telefono» e resta pulito
        nota = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * 2 * freq * t)
        parti.append((vol / 1.2) * nota * env)
        parti.append(np.zeros(int(rate * 0.015)))
    return np.concatenate(parti).astype(np.float32)


def ricampiona(x: np.ndarray, da: int, a: int) -> np.ndarray:
    """Ricampionamento lineare (basta per un segnale breve)."""
    if da == a or len(x) == 0:
        return x.astype(np.float32)
    n = max(1, int(round(len(x) * a / da)))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def leggi_wav(percorso: str, rate: int) -> np.ndarray:
    """Un WAV PCM (8, 16, 24 o 32 bit, mono o stereo) in float32 mono a `rate`, al più
    MAX_FILE_S secondi. Solleva ValueError se il file non si legge."""
    try:
        with wave.open(str(percorso), "rb") as w:
            canali, larghezza, fr = w.getnchannels(), w.getsampwidth(), w.getframerate()
            dati = w.readframes(min(w.getnframes(), int(fr * MAX_FILE_S)))
    except (OSError, EOFError, wave.Error) as e:
        raise ValueError(f"{percorso}: {e}") from e
    if larghezza == 1:
        x = (np.frombuffer(dati, np.uint8).astype(np.float32) - 128) / 128
    elif larghezza == 2:
        x = np.frombuffer(dati, "<i2").astype(np.float32) / 32768
    elif larghezza == 3:
        b = np.frombuffer(dati, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / (1 << 23)
    elif larghezza == 4:
        x = np.frombuffer(dati, "<i4").astype(np.float32) / (1 << 31)
    else:
        raise ValueError(f"{percorso}: campioni da {larghezza} byte non supportati")
    if canali > 1:
        x = x[: len(x) // canali * canali].reshape(-1, canali).mean(axis=1)
    return ricampiona(np.clip(x, -1, 1), fr, rate)


def a_pcm(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


class SuoniAscolto:
    """I due segnali, pronti per ogni frequenza d'uscita (calcolati una volta)."""

    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.attivi = bool(getattr(cfg, "suoni_ascolto", False))
        self._cache: dict[tuple[str, int], bytes] = {}
        self._file: dict[str, tuple[np.ndarray, int] | None] = {}
        if self.attivi:
            for tipo, chiave in ((INIZIO, "suono_inizio_ascolto"), (FINE, "suono_fine_ascolto")):
                self._file[tipo] = self._carica(getattr(cfg, chiave, None), chiave)

    def _carica(self, percorso, chiave):
        if not percorso:
            return None
        if str(percorso).strip().lower() in SPENTO:
            return False                        # questo segnale no (l'altro sì)
        p = str(percorso)
        if not os.path.isabs(p):
            base = getattr(self.cfg, "config_dir", None) or os.getcwd()
            p = os.path.join(base, p)
        try:
            x = leggi_wav(p, 48000)
        except ValueError as e:
            self.log(f"   [SUONI] {chiave}: non riesco a leggere il file ({e}): uso il "
                     f"segnale sintetico")
            return None
        return x, 48000

    def pcm(self, tipo: str, rate: int) -> bytes:
        """Il segnale `tipo` in PCM int16 mono a `rate` (b"" se i suoni sono spenti)."""
        if not self.attivi:
            return b""
        chiave = (tipo, int(rate))
        if self._file.get(tipo) is False:
            return b""
        if chiave not in self._cache:
            f = self._file.get(tipo)
            x = (ricampiona(f[0], f[1], rate) if f is not None
                 else sintetico(tipo, rate, getattr(self.cfg, "suoni_volume", 0.35)))
            self._cache[chiave] = a_pcm(x)
        return self._cache[chiave]

    def per_satellite(self, rate: int = 22050) -> dict | None:
        """Quello che il server manda nel benvenuto a satelliti e telefoni: i due segnali in
        base64 (PCM int16 mono a `rate`), oppure None se i suoni sono spenti."""
        if not self.attivi:
            return None
        return {"rate": int(rate),
                INIZIO: base64.b64encode(self.pcm(INIZIO, rate)).decode("ascii"),
                FINE: base64.b64encode(self.pcm(FINE, rate)).decode("ascii")}


def da_benvenuto(d) -> dict[str, tuple[bytes, int]]:
    """Dal campo «suoni» del benvenuto: {tipo: (pcm, rate)}; {} se manca o è rotto."""
    out: dict[str, tuple[bytes, int]] = {}
    if not isinstance(d, dict):
        return out
    try:
        rate = int(d.get("rate") or 0)
    except (TypeError, ValueError):
        return out
    if not 8000 <= rate <= 96000:
        return out
    for tipo in (INIZIO, FINE):
        v = d.get(tipo)
        if not isinstance(v, str) or len(v) > 400_000:      # ~2 s a 48 kHz
            continue
        try:
            pcm = base64.b64decode(v, validate=True)
        except (ValueError, TypeError):
            continue
        if pcm and len(pcm) % 2 == 0:
            out[tipo] = (pcm, rate)
    return out
