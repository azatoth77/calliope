"""
Misura della trascrivibilità delle frasi di sfida (04/10/2026, calliope/conferme.py).

Ogni voce italiana di Piper in `voices/` dice frasi di sfida («girasole, treno, limone,
quarantadue») scelte in modo che ogni parola dell'elenco `conferme.PAROLE` compaia più volte;
Whisper (`calliope.stt.Transcriber`, la configurazione predefinita: large-v3-turbo) le
trascrive. Si contano le sfide passate con `conferme.confronta` (il confronto vero), le
parole trascritte esatte e quelle che il confronto tollerante non riconosce, per parola.

    .venv\\Scripts\\python prove\\misura_sfida.py [--giri 3] [--parole tutte|elenco]

Le parole con un errore vanno tolte da `PAROLE` (o sostituite e rimisurate).
"""

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAIN = Path(r"C:\Source\Progetti\calliope")
VOCI = (ROOT / "voices") if any((ROOT / "voices").glob("*.onnx")) else MAIN / "voices"
SR = 16000

# Candidate in più, provate insieme a quelle dell'elenco (--parole candidate)
CANDIDATE = ("cammello", "papavero", "lampone", "cometa", "pagnotta", "scoiattolo", "ananas",
             "zucchero", "cavallo", "ciliegia", "melograno", "astronave", "farina", "barchetta",
             "pennello", "valigia", "tastiera", "mongolfiera", "conchiglia", "lumaca")


def sintetizza(voice, testo: str) -> np.ndarray:
    import soxr
    pcm = b"".join(ch.audio_int16_bytes for ch in voice.synthesize(testo))
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    sr = voice.config.sample_rate
    if sr != SR:
        a = soxr.resample(a, sr, SR).astype(np.float32)
    # pre-roll e silenzio finale come una frase captata dal VAD
    return np.concatenate([np.zeros(int(0.3 * SR), np.float32), a,
                           np.zeros(int(0.7 * SR), np.float32)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giri", type=int, default=3, help="volte che ogni parola compare per voce")
    ap.add_argument("--parole", default="elenco", choices=("elenco", "candidate", "tutte"))
    ap.add_argument("--salva", help="file JSON dove scrivere le trascrizioni")
    ap.add_argument("--rivaluta", help="file JSON di --salva: niente sintesi né Whisper")
    args = ap.parse_args()
    if args.rivaluta:
        return valuta(json.loads(Path(args.rivaluta).read_text(encoding="utf-8")), args.parole)
    from piper import PiperVoice
    from calliope import conferme as C
    from calliope.config import Config
    from calliope.stt import Transcriber

    parole = {"elenco": list(C.PAROLE), "candidate": list(CANDIDATE),
              "tutte": list(C.PAROLE) + list(CANDIDATE)}[args.parole]
    cfg = Config()
    stt = Transcriber(cfg)
    print(f"Whisper {cfg.whisper_model} su {stt.device}; {len(parole)} parole")
    rng = random.Random(7)
    righe = []
    t0 = time.time()
    for onnx in sorted(VOCI.glob("*.onnx")):
        voice = PiperVoice.load(str(onnx))
        sequenza = []
        for _ in range(args.giri):
            g = parole[:]
            rng.shuffle(g)
            sequenza += g
        for i in range(0, len(sequenza) - 2, 3):
            tre = tuple(sequenza[i:i + 3])
            if len(set(tre)) < 3:
                continue
            s = C.Sfida("x", tre, rng.randint(21, 99), "t")
            righe.append({"voce": onnx.stem, "parole": list(tre), "numero": s.numero,
                          "testo": stt.transcribe(sintetizza(voice, s.testo))})
        print(f"  {onnx.stem}: fatto ({time.time() - t0:.0f} s)", flush=True)
    if args.salva:
        Path(args.salva).write_text(json.dumps(righe, ensure_ascii=False, indent=0),
                                    encoding="utf-8")
    valuta(righe, args.parole)


def valuta(righe, quali="elenco"):
    """Sfide passate (per voce), parole non riconosciute, con il confronto di conferme.py.
    Con --parole elenco solo le sfide fatte tutte di parole dell'elenco attuale."""
    from calliope import conferme as C
    if quali == "elenco":
        righe = [r for r in righe if all(w in C.PAROLE for w in r["parole"])]
    passate, per_voce = 0, defaultdict(lambda: [0, 0])
    mancate, viste, esatte = Counter(), Counter(), Counter()
    numeri_ok = 0
    esempi = defaultdict(list)
    for r in righe:
        s = C.Sfida("x", tuple(r["parole"]), r["numero"], "t")
        ok = C.confronta(s, r["testo"]) == "ok"
        passate += ok
        per_voce[r["voce"]][0] += ok
        per_voce[r["voce"]][1] += 1
        norm = C._norm(r["testo"]).split()
        for w in r["parole"]:
            viste[w] += 1
            esatte[w] += w in norm
            if not C._parola_detta(w, norm):
                mancate[w] += 1
                esempi[w].append(f"{r['voce']}: «{r['testo']}»")
        numeri_ok += C._numero_detto(r["numero"], r["testo"])
        if not ok:
            esempi["_sfide"].append(f"{r['voce']}: {s.testo} → «{r['testo']}»")
    n = len(righe)
    print(f"\nSfide passate: {passate}/{n} ({100 * passate / max(1, n):.1f} %)")
    for v, (a, b) in sorted(per_voce.items()):
        print(f"  {v:24s} {a}/{b}")
    print(f"Numeri riconosciuti: {numeri_ok}/{n}")
    tot_v, tot_e = sum(viste.values()), sum(esatte.values())
    print(f"Parole trascritte esatte: {tot_e}/{tot_v} ({100 * tot_e / max(1, tot_v):.1f} %); "
          f"non riconosciute dal confronto: {sum(mancate.values())}/{tot_v}")
    print("\nParole non riconosciute (volte / viste; esatte):")
    for w, k in sorted(mancate.items(), key=lambda x: -x[1]):
        print(f"  {w:14s} {k}/{viste[w]}; esatte {esatte[w]}/{viste[w]}  es. {esempi[w][0]}")
    print("\nSfide non passate (prime 12):")
    for e in esempi["_sfide"][:12]:
        print("  " + e)


if __name__ == "__main__":
    main()
