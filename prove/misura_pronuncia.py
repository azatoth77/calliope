"""
Misura della pronuncia degli inglesismi (calliope/pronuncia.py, 04/10/2026).

Sintetizza con Piper ogni frase prima e dopo la correzione, la ritrascrive con faster-whisper
(su CPU: la GPU può essere occupata) e stampa i fonemi di espeak, le due trascrizioni e il
costo di `Pronuncia.applica`. Con --wav <cartella> salva anche gli audio da ascoltare.

    python prove/misura_pronuncia.py [--voce voices/it_IT-serena-high.onnx] [--wav cartella]
                                     [--modello large-v3-turbo] [--lingua it|auto]

Non è nel runner (serve un minuto di CPU e il modello di Whisper).
"""
import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from calliope.pronuncia import Pronuncia  # noqa: E402

FRASI = [
    "Ho trovato 2 file: chiavi csv e chiavi xlsx.",
    "Il file è nella cartella Documenti.",
    "Ti ho mandato una email con il riassunto.",
    "La password del wifi è sul frigorifero.",
    "Ho fatto il backup dei documenti.",
    "Ho salvato uno screenshot sul desktop.",
    "Metto la tua playlist su Spotify.",
    "Il meeting è alle 10 su Zoom.",
    "Apro Outlook sul notebook.",
    "Il file è aperto in PowerPoint.",
    "Lo trovi su OneDrive, in Windows.",
    "Apro Chrome o il browser?",
    "Le cuffie headset sono collegate.",
    "Home Assistant gira sul Raspberry.",
    "Whisper e Piper girano sulla DGX, con Docker.",
    "Ho trovato la citazione su Wikiquote.",
    "Accetta i cookie del sito.",
    "Ci sono tre file di sedie in sala.",
    "Siediti nelle prime file.",
    "Ho messo un timer di 5 minuti.",
    "Il computer ha un mouse e un tablet.",
    "Scarico il download sullo smartphone.",
    "OK, ci vediamo nel weekend.",
    "Ho cercato su YouTube e Netflix.",
]


def pcm(voice, text):
    return b"".join(ch.audio_int16_bytes for ch in voice.synthesize(text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voce", default="voices/it_IT-serena-high.onnx")
    ap.add_argument("--wav", default="")
    ap.add_argument("--modello", default="large-v3-turbo")
    ap.add_argument("--lingua", default="it")
    ap.add_argument("--parole", action="store_true",
                    help="ogni parola del lessico da sola, trascritta in inglese: in italiano "
                         "Whisper scrive «file» sia per «fìle» sia per «fàil»")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    from faster_whisper import WhisperModel
    from piper import PiperVoice
    voice = PiperVoice.load(a.voce)
    rate = voice.config.sample_rate
    model = WhisperModel(a.modello, device="cpu", compute_type="int8")
    p = Pronuncia()
    out = Path(a.wav) if a.wav else None
    if out:
        out.mkdir(parents=True, exist_ok=True)

    # Costo di applica: 1000 volte su tutte le frasi
    t0 = time.perf_counter()
    for _ in range(1000):
        for f in FRASI:
            p.applica(f)
    us = (time.perf_counter() - t0) / (1000 * len(FRASI)) * 1e6
    print(f"applica: {us:.1f} µs a frase\n")

    def trascrivi(audio):
        x = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768
        if rate != 16000:
            x = np.interp(np.arange(0, len(x), rate / 16000), np.arange(len(x)), x)
        segs, _ = model.transcribe(x.astype(np.float32), language=None if a.lingua == "auto"
                                   else a.lingua, beam_size=5)
        return "".join(s.text for s in segs).strip()

    if a.parole:
        from calliope.pronuncia import LESSICO
        for chiavi in LESSICO:
            w = chiavi.split("|")[0]
            g = p.applica(w)
            def en(au):
                x = np.frombuffer(au, dtype=np.int16).astype(np.float32) / 32768
                if rate != 16000:
                    x = np.interp(np.arange(0, len(x), rate / 16000), np.arange(len(x)), x)
                segs, _ = model.transcribe(x.astype(np.float32), language="en", beam_size=5)
                return "".join(s.text for s in segs).strip()
            print(f"{w:12} prima: {en(pcm(voice, w + '.')):25} dopo ({g}): {en(pcm(voice, g + '.'))}")
        return

    for i, f in enumerate(FRASI):
        g = p.applica(f)
        t1 = time.perf_counter()
        prima = pcm(voice, f)
        t2 = time.perf_counter()
        dopo = pcm(voice, g) if g != f else prima
        t3 = time.perf_counter()
        fon = " | ".join("".join(s) for s in voice.phonemize(g))
        print(f"[{i:02d}] {f}")
        if g != f:
            print(f"     testo a Piper: {g}")
            print(f"     fonemi: {fon}")
            print(f"     prima: {trascrivi(prima)}")
            print(f"     dopo:  {trascrivi(dopo)}   (sintesi {t2 - t1:.2f} → {t3 - t2:.2f} s)")
        else:
            print(f"     invariata: {trascrivi(prima)}")
        if out:
            for nome, au in (("prima", prima), ("dopo", dopo)):
                with wave.open(str(out / f"{i:02d}-{nome}.wav"), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    w.writeframes(au)


if __name__ == "__main__":
    main()
