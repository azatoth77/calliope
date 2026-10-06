"""
Le persone della prova end-to-end e le loro frasi (06/10/2026).

Nomi inventati: nessun nome vero nei file del repository. «Carlo» parla con le registrazioni
vere di chi amministra (elenco in `voce_reale.tsv`: cartella, file, testo; i file audio NON
sono nel repository: stanno sul portatile in `registrazioni/` e, durante la prova, sulla DGX
in `~/calliope-e2e/voce-reale/` con i permessi 700/600, cancellati alla fine). Le altre
persone parlano con le voci di Piper:

  Carlo   chi amministra, voce vera (frasi registrate: solo quelle che esistono)
  Andrea  chi amministra, Piper «ugo» (dice qualunque frase: sfide, comandi nuovi)
  Giulia  familiare adulta, Piper «paola»
  Sofia   minore (nata nel 2017: fascia «bambini»), Piper «aurora», tutori Andrea e Carlo
  ospite  voce non registrata, Piper «giorgio»
"""
from __future__ import annotations

import csv
import io
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

QUI = Path(__file__).resolve().parent
RATE = 16000


@dataclass
class Persona:
    nome: str
    voce: str | None              # file della voce di Piper (None = registrazioni vere)
    admin: bool = False
    registrata: bool = True
    genere: str | None = None
    nascita: str | None = None
    tutori: list[str] = field(default_factory=list)


PERSONE = {
    "Carlo": Persona("Carlo", None, admin=True, genere="m"),
    "Andrea": Persona("Andrea", "it_IT-ugo-medium.onnx", admin=True, genere="m"),
    "Giulia": Persona("Giulia", "it_IT-paola-medium.onnx", genere="f"),
    "Sofia": Persona("Sofia", "it_IT-aurora-medium.onnx", genere="f", nascita="2017-05-12",
                     tutori=["Andrea", "Carlo"]),
    "ospite": Persona("ospite", "it_IT-giorgio-medium.onnx", registrata=False, genere="m"),
}

# Frasi per l'impronta delle voci di Piper (come arruola.py: frasi lunghe, senza il nome)
ARRUOLA_PIPER = [
    "Raccontami cosa hai fatto oggi, con calma e senza fretta.",
    "Dimmi qual è il tuo piatto preferito e perché ti piace tanto.",
    "Descrivimi la stanza in cui ti trovi adesso, con tutti i mobili.",
    "Domenica scorsa siamo andati al mare e abbiamo mangiato il gelato.",
]


def elenco_reale(path: Path | None = None) -> dict[str, dict]:
    """chiave → {cartella, stem, testo, uso} da voce_reale.tsv."""
    path = path or QUI / "voce_reale.tsv"
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out[r["chiave"]] = r
    return out


def leggi_wav(path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    return ricampiona(x, rate)


def ricampiona(x: np.ndarray, rate: int, verso: int = RATE) -> np.ndarray:
    if rate == verso or len(x) == 0:
        return x.astype(np.float32)
    n = int(len(x) * verso / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def senza_coda(x: np.ndarray, soglia_db: float = -40.0, resto_s: float = 0.45) -> np.ndarray:
    """Le registrazioni vere finiscono con il silenzio che il VAD di allora ha tenuto: si
    toglie (lasciando `resto_s`), così la «fine del parlato» della prova è quella vera. Con
    0,15 s Whisper sbagliava le parole brevi («Sì.» → «SIGUE.», «Grazie.» → «Essi.», 06/10):
    il VAD vero lascia più coda."""
    n = 160
    soglia = 10 ** (soglia_db / 20)
    fine = len(x)
    for k in range(len(x) - n, 0, -n):
        if np.sqrt(np.mean(x[k:k + n] ** 2)) > soglia:
            fine = k + n
            break
    return x[:min(len(x), fine + int(resto_s * RATE))]


def wav_bytes(x: np.ndarray, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


class Voci:
    """Sintesi con Piper (una voce per persona, caricata una volta) e registrazioni vere."""

    def __init__(self, cartella_voci: Path, cartella_reale: Path | None):
        self.cartella_voci = Path(cartella_voci)
        self.cartella_reale = Path(cartella_reale) if cartella_reale else None
        self._piper: dict = {}
        self.reale = elenco_reale()

    def piper(self, voce: str, testo: str) -> np.ndarray:
        from piper import PiperVoice
        v = self._piper.get(voce)
        if v is None:
            v = self._piper[voce] = PiperVoice.load(str(self.cartella_voci / voce))
        pcm = b"".join(ch.audio_int16_bytes for ch in v.synthesize(testo))
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        return ricampiona(x, v.config.sample_rate)

    def ha_reale(self, chiave: str) -> bool:
        r = self.reale.get(chiave)
        return bool(r and self.cartella_reale
                    and (self.cartella_reale / f"{r['cartella']}__{r['stem']}.wav").is_file())

    def registrazione(self, chiave: str) -> tuple[np.ndarray, str]:
        r = self.reale[chiave]
        x = leggi_wav(self.cartella_reale / f"{r['cartella']}__{r['stem']}.wav")
        return senza_coda(x), r["testo"]

    def frase(self, persona: str, testo: str | None = None, reale: str | None = None
              ) -> tuple[np.ndarray, str]:
        """(audio a 16 kHz, testo detto): una registrazione vera (`reale`) o Piper."""
        if reale is not None:
            return self.registrazione(reale)
        p = PERSONE[persona]
        if p.voce is None:
            raise ValueError(f"{persona} parla solo con le registrazioni")
        return self.piper(p.voce, testo), testo

    def arruolamento(self, persona: str) -> list[np.ndarray]:
        p = PERSONE[persona]
        if p.voce is None:
            return [self.registrazione(k)[0] for k, r in self.reale.items()
                    if r["uso"] == "arruola" and self.ha_reale(k)]
        return [self.piper(p.voce, t) for t in ARRUOLA_PIPER]
