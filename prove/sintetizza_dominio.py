import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Frasi di dominio per il confronto dello STT (05/10, docs/ricerche/2026-10-05-stt-confronto.md).

Sintetizza le frasi di prove/riferimenti_dominio.tsv con tre voci di Piper diverse da quella di
Calliope (giorgio, paola, riccardo x_low; aurora scartata: anche pulita e senza rumore Whisper non la capisce, «Palanplassa le tapparelle»), a 16 kHz, con un rumore leggero (rosa, SNR 20 dB),
una piccola variazione di velocità e 0,3 s di silenzio intorno. Riproducibile (seme fisso).

Uso: python prove/sintetizza_dominio.py <cartella di uscita> [--voci cartella_voci]
Scrive <uscita>/<voce>__<id>.wav. Le voci si cercano in voices/ (o --voci).
"""
import csv
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VOCI = ["it_IT-giorgio-medium", "it_IT-paola-medium", "it_IT-riccardo-x_low"]
SR = 16000
SNR_DB = 20.0


def frasi():
    with open(ROOT / "prove" / "riferimenti_dominio.tsv", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def rumore_rosa(n: int, rng) -> np.ndarray:
    """Rumore rosa (1/f) con il filtro di Voss semplificato nel dominio della frequenza."""
    spettro = np.fft.rfft(rng.normal(size=n))
    f = np.arange(len(spettro))
    f[0] = 1
    x = np.fft.irfft(spettro / np.sqrt(f), n)
    return x / (np.std(x) + 1e-9)


def sintetizza(voce, testo: str, length_scale: float) -> np.ndarray:
    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=length_scale)
    pcm = b"".join(ch.audio_int16_bytes for ch in voce.synthesize(testo, syn_config=cfg))
    return np.frombuffer(pcm, np.int16).astype(np.float32) / 32768


def main():
    from piper import PiperVoice
    from scipy.signal import resample_poly
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cartella = Path(sys.argv[sys.argv.index("--voci") + 1]) if "--voci" in sys.argv \
        else ROOT / "voices"
    rng = np.random.default_rng(5)
    for nome in VOCI:
        voce = PiperVoice.load(str(cartella / f"{nome}.onnx"))
        sr = voce.config.sample_rate
        for r in frasi():
            audio = sintetizza(voce, r["riferimento"], float(rng.uniform(0.9, 1.1)))
            g = np.gcd(sr, SR)
            audio = resample_poly(audio, SR // g, sr // g).astype(np.float32)
            pad = np.zeros(int(0.3 * SR), np.float32)
            audio = np.concatenate([pad, audio, pad])
            p = np.sqrt(np.mean(audio ** 2)) + 1e-9
            audio = audio + rumore_rosa(len(audio), rng) * p / (10 ** (SNR_DB / 20))
            audio *= float(rng.uniform(0.3, 0.6)) / (np.max(np.abs(audio)) + 1e-9)
            with wave.open(str(out / f"{nome}__{r['id']}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        print(nome, "fatto", flush=True)


if __name__ == "__main__":
    main()
