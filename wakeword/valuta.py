"""
Valuta un modello della wake word sulle registrazioni REALI e su audio lungo senza nome.

- Registrazioni reali (wakeword/dati/reali.tsv, preparato da etichette_reali.py):
  ogni WAV passa nel rilevatore in streaming a blocchi da 80 ms, preceduto da 1,5 s e
  seguito da 1 s di quasi-silenzio (nel programma vero il flusso è continuo).
  Positivo riconosciuto se il punteggio supera la soglia; negativo sbagliato se la supera.
  Per i positivi si misura quando scatta rispetto alla fine del nome (timestamp Whisper).
- Audio lungo senza nome: i negativi reali concatenati, il test di MLS italiano (mai
  visto in addestramento) e le 10,7 h di validazione di openWakeWord → falsi risvegli
  per ora (dopo uno scatto si ignorano 2 s, come farebbe il programma).
- Costo: tempo per blocco da 80 ms su un solo thread della CPU.

    .\\wakeword\\.venv\\Scripts\\python.exe wakeword\\valuta.py [modello.onnx]
"""
from __future__ import annotations

import csv
import glob
import os
import sys
import time

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from detector import CHUNK, FeatureExtractor, WakeWordDetector, _session  # noqa: E402

SR = 16000
THRESHOLDS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
LEAD, TAIL = int(1.5 * SR), int(1.0 * SR)


def stream_scores(det: WakeWordDetector, audio: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    det.reset()
    x = np.concatenate([rng.standard_normal(LEAD).astype(np.float32) * 3e-4, audio,
                        rng.standard_normal(TAIL).astype(np.float32) * 3e-4])
    scores, times, costs = [], [], []
    for i in range(0, len(x) - CHUNK + 1, CHUNK):
        t = time.perf_counter()
        s = det.process(x[i:i + CHUNK])
        costs.append(time.perf_counter() - t)
        scores.append(s)
        times.append((i + CHUNK - LEAD) / SR)       # fine del blocco, rispetto all'inizio clip
    return np.array(scores), np.array(times), np.array(costs)


K = 1   # blocchi consecutivi sopra soglia per dire «sveglia» (--consecutivi N)


def above(scores: np.ndarray, thr: float) -> np.ndarray:
    """True dove gli ultimi K punteggi sono tutti sopra soglia."""
    a = scores >= thr
    out = a.copy()
    for k in range(1, K):
        out[k:] &= a[:-k]
        out[:k] = False
    return out


def count_triggers(scores, thr, refractory=25):
    n, last = 0, -10 ** 9
    for i in np.where(above(scores, thr))[0]:
        if i - last > refractory:
            n += 1
            last = i
    return n


def batch_scores(clf, seq: np.ndarray, batch=8192) -> np.ndarray:
    name = clf.get_inputs()[0].name
    out = []
    for s in range(16, len(seq) + 1, batch):
        idx = np.arange(s, min(s + batch, len(seq) + 1))
        w = np.stack([seq[i - 16:i] for i in idx]).astype(np.float32)
        out.append(np.asarray(clf.run(None, {name: w})[0]).ravel())
    return np.concatenate(out) if out else np.zeros(0)


def main(model_path=None, quick=False):
    model_path = model_path or os.path.join(HERE, "modelli", "calliope.onnx")
    rng = np.random.default_rng(0)
    det = WakeWordDetector(model_path, threads=1)
    rows = list(csv.DictReader(open(os.path.join(HERE, "dati", "reali.tsv"), encoding="utf-8"),
                               delimiter="\t"))
    res, all_costs, neg_audio = [], [], []
    for r in rows:
        audio, sr = sf.read(os.path.join(ROOT, "registrazioni", r["cartella"], r["stem"] + ".wav"),
                            dtype="float32")
        sc, tm, cost = stream_scores(det, audio, rng)
        all_costs.append(cost)
        res.append((r, sc, tm))
        if r["etichetta"] == "neg":
            neg_audio.append(audio)

    print(f"\nModello: {os.path.relpath(model_path, ROOT)}")
    pos = [x for x in res if x[0]["etichetta"] == "pos"]
    neg = [x for x in res if x[0]["etichetta"] == "neg"]
    print(f"Registrazioni reali: {len(pos)} positive, {len(neg)} negative\n")
    print("| soglia | risvegli corretti | falsi risvegli (frasi negative) | ritardo mediano dalla fine del nome |")
    print("|---|---|---|---|")
    table = {}
    for thr in THRESHOLDS:
        hits = [x for x in pos if above(x[1], thr).any()]
        fas = [x for x in neg if above(x[1], thr).any()]
        lat = []
        for r, sc, tm in hits:
            if r["fine_nome"] and "calli" in r["parola_whisper"].lower():
                lat.append(tm[np.argmax(above(sc, thr))] - float(r["fine_nome"]))
        med = f"{np.median(lat) * 1000:+.0f} ms (n={len(lat)})" if lat else "—"
        table[thr] = (len(hits), len(fas), lat)
        print(f"| {thr:.2f} | {len(hits)}/{len(pos)} ({len(hits) / len(pos):.0%}) | "
              f"{len(fas)}/{len(neg)} | {med} |")

    print("\nPunteggio massimo per clip (positivi mancati alla soglia 0,5 e negativi sopra 0,2):")
    for r, sc, tm in pos:
        if sc.max() < 0.5:
            print(f"  MANCATO {sc.max():.3f}  {r['cartella']}/{r['stem']}  «{r['riferimento'][:50]}»")
    for r, sc, tm in [x for x in res if x[0]["etichetta"] == "dubbio"]:
        print(f"  DUBBIO  {sc.max():.3f}  {r['cartella']}/{r['stem']}  «{r['riferimento'][:50]}»")
    for r, sc, tm in neg:
        if sc.max() >= 0.2:
            print(f"  NEG     {sc.max():.3f}  {r['cartella']}/{r['stem']}  «{r['riferimento'][:50]}»")

    costs = np.concatenate(all_costs) * 1000
    print(f"\nCosto per blocco da 80 ms (1 thread): media {costs.mean():.2f} ms, "
          f"p99 {np.percentile(costs, 99):.2f} ms, massimo {costs.max():.2f} ms "
          f"→ {costs.mean() / 80:.1%} di un core")

    # audio lungo senza nome
    fx = FeatureExtractor(threads=4)
    clf = _session(model_path, 4)
    long_sets = []
    seq = fx.embeddings(np.concatenate(neg_audio))
    long_sets.append(("negativi reali concatenati", seq))
    if not quick:
        test = sorted(glob.glob(os.path.join(HERE, "dati", "mls", "test", "*.flac")))
        seqs = []
        for f in test:
            a, _ = sf.read(f, dtype="float32")
            seqs.append(batch_scores(clf, fx.embeddings(a)))
        long_sets.append(("MLS italiano, test (mai visto)", seqs))
        V = np.load(os.path.join(HERE, "dati", "validation_set_features.npy"))
        long_sets.append(("validazione openWakeWord (usata per scegliere il passo)", V))
    print("\n| audio senza nome | ore | " + " | ".join(f"soglia {t:.2f}" for t in THRESHOLDS[1:8]) + " |")
    print("|---|---|" + "---|" * 7)
    for label, data in long_sets:
        if isinstance(data, list):     # punteggi già calcolati, file per file
            hours = sum(len(s) + 15 for s in data) * 0.08 / 3600
            counts = [sum(count_triggers(s, t) for s in data) for t in THRESHOLDS[1:8]]
        else:
            sc = batch_scores(clf, data)
            hours = len(data) * 0.08 / 3600
            counts = [count_triggers(sc, t) for t in THRESHOLDS[1:8]]
        print(f"| {label} | {hours:.2f} | " + " | ".join(
            f"{c} ({c / hours:.2f}/h)" for c in counts) + " |")
    return table


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--consecutivi" in sys.argv:
        K = int(sys.argv[sys.argv.index("--consecutivi") + 1])
        args = [a for a in args if a != str(K)]
    print(f"Scatto con {K} blocco/i consecutivo/i sopra soglia")
    main(args[0] if args else None, quick="--rapido" in sys.argv)
