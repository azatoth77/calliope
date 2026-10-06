"""
Etichette delle registrazioni reali per la valutazione della wake word.

Per ogni WAV in registrazioni/*/ scrive in wakeword/dati/reali.tsv:
cartella, stem, etichetta (pos/neg), durata, inizio e fine del nome (secondi, solo pos),
riferimento.

- Etichetta: dal testo realmente detto in prove/riferimenti_whisper.tsv («Calliope» nel
  riferimento → positivo). La sessione 2026-09-24-v03c non è nel file dei riferimenti:
  le sue etichette sono scritte qui sotto a mano (vedi console.log e docs/test-vocale.md).
- Inizio/fine del nome: timestamp per parola di faster-whisper (large-v3-turbo, con
  «Calliope» come hotword). Serve a misurare dove cade l'attivazione rispetto alla fine
  della parola. Se Whisper storpia il nome si prende la prima parola della frase e la
  colonna parola_whisper lo mostra: in quel caso la fine è inaffidabile.

Va lanciato con il venv PRINCIPALE (serve faster-whisper, meglio su GPU):
    .\\.venv\\Scripts\\python.exe wakeword\\etichette_reali.py
"""
import csv
import glob
import os
import sys

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "wakeword", "dati", "reali.tsv")

# Sessione senza riferimenti: positivi riconosciuti dal console.log, il resto è negativo
# (conversazione con un'altra persona, «passeggiata a cavallo», «che ore sono?»…)
V03C_POS = {"20260924-135743": "Calliope.",
            "20260924-135837": "Calliope, dimmi tre città della Toscana.",
            "20260924-135909": "Calliope, esci."}


def load_refs():
    refs = {}
    with open(os.path.join(ROOT, "prove", "riferimenti_whisper.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            refs[(r["cartella"], r["stem"])] = (r["riferimento"], r["sicurezza"])
    # Correzioni verificate il 24/09 con i timestamp per parola di Whisper: in questa clip
    # il nome c'è (0,0–0,7 s, poi una pausa di 0,4 s e «ricordati…»), ma nel file dei
    # riferimenti manca. La wake word dedicata scattava a +120 ms dalla fine del nome.
    refs[("2026-09-21-webcam", "20260921-141138")] = (
        "Calliope, ricordati che il mio numero preferito è quarantasette.", "corretto")
    return refs


def load_whisper(folder):
    """Trascrizioni fatte da Calliope durante il test (solo per mostrarle)."""
    out = {}
    p = os.path.join(ROOT, "registrazioni", folder, "trascrizioni.tsv")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                out[parts[0]] = parts[2]
    return out


def main():
    sys.path.insert(0, ROOT)
    from calliope.stt import _add_cuda_dlls   # DLL di cuBLAS/cuDNN installate via pip
    _add_cuda_dlls()
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
    except Exception as e:  # ripiego su CPU
        print("GPU non disponibile, uso la CPU:", e)
        model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")

    refs = load_refs()
    rows = []
    for wav in sorted(glob.glob(os.path.join(ROOT, "registrazioni", "*", "*.wav"))):
        folder = os.path.basename(os.path.dirname(wav))
        stem = os.path.splitext(os.path.basename(wav))[0]
        label = None
        if (folder, stem) in refs:
            ref, sure = refs[(folder, stem)]
            # Riferimento vuoto e incerto: non si sa cosa sia stato detto (Whisper aveva
            # scritto «Allio, Pede», «Andiopera»…: forse proprio il nome). Fuori dai conti.
            if not ref and sure == "incerto":
                label = "dubbio"
                ref = "(whisper) " + load_whisper(folder).get(stem, "")
        elif folder == "2026-09-24-v03c":
            ref = V03C_POS.get(stem) or "(whisper) " + load_whisper(folder).get(stem, "")
        else:
            print("senza riferimento, salto:", folder, stem)
            continue
        audio, sr = sf.read(wav, dtype="float32")
        assert sr == 16000, wav
        pos = label is None and "calliope" in ref.lower() and not ref.startswith("(whisper)")
        start = end = word = ""
        if pos:
            segs, _ = model.transcribe(audio, language="it", word_timestamps=True,
                                       beam_size=5, hotwords="Calliope",
                                       vad_filter=False)
            words = [w for s in segs for w in s.words]
            hit = next((w for w in words if "calli" in w.word.lower()
                        or "allio" in w.word.lower()), None) or (words[0] if words else None)
            if hit:
                start, end = f"{hit.start:.2f}", f"{hit.end:.2f}"
                word = hit.word.strip(" ,.!?")
            print(f"{folder}/{stem}: {ref[:40]!r} → {hit.word if hit else None} {start}–{end}")
        rows.append([folder, stem, label or ("pos" if pos else "neg"), f"{len(audio) / sr:.2f}",
                     start, end, word, ref])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["cartella", "stem", "etichetta", "durata", "inizio_nome", "fine_nome",
                    "parola_whisper", "riferimento"])
        w.writerows(rows)
    print(f"{len(rows)} righe, {sum(r[2] == 'pos' for r in rows)} positive → {OUT}")


if __name__ == "__main__":
    sys.exit(main())
