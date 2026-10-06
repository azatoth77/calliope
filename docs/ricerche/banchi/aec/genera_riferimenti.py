r"""Genera con Piper la "voce di Calliope" usata come riferimento (far-end) nelle prove AEC.

Va lanciato con il .venv PRINCIPALE (serve piper-tts):
    .\.venv\Scripts\python.exe docs\ricerche\banchi\aec\genera_riferimenti.py

Scrive in aec/dati/rif/ un WAV a 22050 Hz (come esce da Piper) per ogni frase.
"""
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]   # radice del repository (docs/ricerche/banchi/aec)
OUT = ROOT / "docs" / "ricerche" / "banchi" / "aec" / "dati" / "rif"

# Risposte tipiche di Calliope: brevi, parlate, senza elenchi
FRASI = [
    "Sono le cinque e venti del pomeriggio.",
    "Oggi è venerdì ventisei settembre duemilaventisei.",
    "La capitale della Francia è Parigi, una delle città più visitate d'Europa.",
    "Certo, posso cambiare voce. Al momento ho quattro voci italiane disponibili: "
    "Serena, Paola, Aurora e Riccardo.",
    "La Luna dista dalla Terra circa trecentottantaquattromila chilometri, "
    "e la sua luce impiega poco più di un secondo per arrivare fino a noi.",
    "Non ho accesso a internet, quindi non posso dirti che tempo farà domani. "
    "Posso però dirti l'ora, la data e chi sta parlando.",
    "Ciao Dario, è bello sentirti. Come posso aiutarti oggi?",
    "La ricetta della carbonara prevede guanciale, uova, pecorino romano e pepe nero. "
    "La panna non ci va.",
    "Va bene, da adesso ti chiamerò Dario. Se vuoi cambiare di nuovo il nome basta dirmelo.",
    "Il Colosseo fu inaugurato nell'ottanta dopo Cristo sotto l'imperatore Tito, "
    "e poteva ospitare decine di migliaia di spettatori.",
]


def main():
    sys.path.insert(0, str(ROOT))
    from piper import PiperVoice
    voice_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "voices" / "it_IT-serena-high.onnx")
    voice = PiperVoice.load(voice_path)
    OUT.mkdir(parents=True, exist_ok=True)
    sr = voice.config.sample_rate
    tot = 0.0
    for i, text in enumerate(FRASI):
        pcm = b"".join(ch.audio_int16_bytes for ch in voice.synthesize(text))
        with wave.open(str(OUT / f"rif_{i:02d}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm)
        tot += len(pcm) / 2 / sr
    print(f"{len(FRASI)} frasi, {tot:.1f} s a {sr} Hz in {OUT}")


if __name__ == "__main__":
    main()
