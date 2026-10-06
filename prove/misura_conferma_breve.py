"""
Misura della soglia per la conferma breve di chi amministra (04/10/2026).

Un «sì» breve (meno di `speaker_min_voice_s` di voce) dopo una proposta fatta a chi
amministra la conferma solo se, nella stessa conversazione, chi parla era stato riconosciuto
dalla voce come quella persona **e** l'impronta della frase breve non è incompatibile
(punteggio contro il suo profilo ≥ `speaker_conferma_breve_soglia`). Qui si misura quanta
parte delle frasi brevi di altre voci supera ogni soglia candidata, e quante frasi brevi di
Dario restano sotto.

Dati (fuori da git, gli stessi di docs/ricerche/2026-09-24-riconoscimento-parlante.md):
- Dario: le frasi brevi vere di `registrazioni/*/` (voce < 1 s, con pre-roll e silenzio
  finale come in main.py), più i ritagli di 0,5 / 0,7 / 0,9 s del pezzo più energico delle
  altre frasi; profilo = l'impronta di `speakers.json` (quella in uso).
- Altre voci (altri canali): MLS e VoxPopuli italiano (63 parlanti) e le 10 voci Piper, con
  gli stessi ritagli, contro l'impronta di Dario.
- Stesso canale (la misura che conta): ogni parlante MLS/VoxPopuli con almeno 6 frasi
  arruolato con 3 frasi intere e confrontato con i ritagli brevi degli altri parlanti dello
  stesso corpus (e con i suoi, per il rifiuto).

    .venv\\Scripts\\python prove\\misura_conferma_breve.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAIN = Path(r"C:\Source\Progetti\calliope")      # dati fuori da git: nella cartella principale
BASE = MAIN if (MAIN / "models" / "speaker" / "dati").exists() else ROOT
DATI = BASE / "models" / "speaker" / "dati"
SR = 16000
INCERTE = {"20260924-135711", "20260924-135714", "20260924-135725", "20260924-135740"}
DURATE = (0.5, 0.7, 0.9)
SOGLIE = (0.20, 0.25, 0.28, 0.30, 0.32, 0.35, 0.38, 0.40, 0.42, 0.45, 0.48)


def _read(path: Path) -> np.ndarray:
    import soundfile as sf
    a, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return a.mean(axis=1)


def loudest(a: np.ndarray, sec: float) -> np.ndarray:
    n = int(sec * SR)
    if len(a) <= n:
        return a
    c = np.concatenate([[0.0], np.cumsum(a.astype(np.float64) ** 2)])
    e = c[n::160] - c[:len(c) - n:160][:len(c[n::160])]
    s = int(np.argmax(e)) * 160
    return a[s:s + n]


def main():
    from calliope.speaker_id import SpeakerEmbedder, normalize
    model = BASE / "models" / "speaker" / "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
    emb = SpeakerEmbedder(str(model), threads=4)
    prof = json.loads((BASE / "speakers.json").read_text(encoding="utf-8"))
    dario = np.asarray(next(p for p in prof if p["name"] == "Dario")["voiceprint"], np.float32)

    # ── Dario ──
    native, crops = [], defaultdict(list)
    for wav in sorted((BASE / "registrazioni").glob("*/*.wav")):
        if wav.stem in INCERTE:
            continue
        a = _read(wav)
        voiced = len(a) / SR - 1.0                         # pre-roll 0,3 + silenzio 0,7
        if voiced < 1.0:
            native.append(float(np.dot(emb.embed(a), dario)))
        elif voiced >= 1.5:
            for d in DURATE:
                crops[d].append(float(np.dot(emb.embed(loudest(a, d)), dario)))

    # ── Altre voci contro Dario (altri canali) ──
    other = defaultdict(list)       # (gruppo, durata) → punteggi
    by_spk = defaultdict(list)      # corpus/parlante → [audio]
    for corpus in ("mls", "voxpopuli", "piper"):
        for wav in sorted((DATI / corpus).glob("*/*.wav")):
            a = _read(wav)
            g = "piper" if corpus == "piper" else "umani"
            if corpus != "piper":
                by_spk[(corpus, wav.parent.name)].append(a)
            for d in DURATE:
                other[(g, d)].append(float(np.dot(emb.embed(loudest(a, d)), dario)))

    # ── Stesso canale ──
    rng = np.random.default_rng(4)
    same_imp, same_tgt = defaultdict(list), defaultdict(list)
    short = {k: {d: [normalize(emb.embed(loudest(a, d))) for a in v] for d in DURATE}
             for k, v in by_spk.items()}
    for k, auds in by_spk.items():
        if len(auds) < 6:
            continue
        idx = rng.permutation(len(auds))
        enr, rest = idx[:3], idx[3:]
        p = normalize(np.mean([emb.embed(auds[i]) for i in enr], axis=0))
        for d in DURATE:
            same_tgt[d] += [float(np.dot(short[k][d][i], p)) for i in rest]
            for k2 in by_spk:
                if k2 != k and k2[0] == k[0]:
                    same_imp[d] += [float(np.dot(e, p)) for e in short[k2][d]]

    def pct(xs, thr, above=True):
        xs = np.asarray(xs)
        return 100.0 * (np.mean(xs >= thr) if above else np.mean(xs < thr)) if len(xs) else float("nan")

    print(f"Dario, frasi brevi vere: {len(native)}; ritagli per durata: {len(crops[0.9])}")
    print(f"Altre voci: umani {len(other[('umani', 0.9)])}, Piper {len(other[('piper', 0.9)])} "
          f"per durata; stesso canale: {len(same_imp[0.9])} prove impostore, "
          f"{len(same_tgt[0.9])} bersaglio")
    q = lambda xs: " / ".join(f"{np.percentile(xs, p):.2f}" for p in (1, 5, 50, 95, 99))  # noqa: E731
    print("\nPercentili 1/5/50/95/99")
    print(f"  Dario brevi vere      {q(native)}")
    for d in DURATE:
        print(f"  Dario ritaglio {d} s   {q(crops[d])}")
        print(f"  umani {d} s          {q(other[('umani', d)])}  max {max(other[('umani', d)]):.2f}")
        print(f"  Piper {d} s          {q(other[('piper', d)])}  max {max(other[('piper', d)]):.2f}")
        print(f"  stesso canale imp {d} {q(same_imp[d])}  max {max(same_imp[d]):.2f}")
    print("\nSoglia | Dario brevi rifiutate | Dario 0,5/0,7/0,9 rifiutati | umani accettati "
          "0,5/0,7/0,9 | Piper accettati | stesso canale accettati 0,5/0,7/0,9 | stesso "
          "canale bersaglio rifiutati 0,9")
    for t in SOGLIE:
        print(f"{t:.2f} | {pct(native, t, False):5.1f} % | "
              + " / ".join(f"{pct(crops[d], t, False):4.1f}" for d in DURATE) + " % | "
              + " / ".join(f"{pct(other[('umani', d)], t):4.2f}" for d in DURATE) + " % | "
              + " / ".join(f"{pct(other[('piper', d)], t):4.2f}" for d in DURATE) + " % | "
              + " / ".join(f"{pct(same_imp[d], t):4.2f}" for d in DURATE) + " % | "
              + f"{pct(same_tgt[0.9], t, False):4.1f} %")


if __name__ == "__main__":
    main()
