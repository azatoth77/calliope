"""
Misura per la «modalità compagnia» (09/10/2026, docs/ricerche/2026-10-09-piu-persone.md):
quanto le impronte CAM++ delle frasi dicono che sullo stesso satellite parlano più persone.

Manuale, non nel runner. Dati fuori da git, gli stessi di `misura_conferma_breve.py`:
MLS e VoxPopuli italiano (stesso canale tra loro), le voci Piper e le registrazioni di Dario in
`registrazioni/` (escluse le cartelle del 26/09, dove ci sono altre voci e la TV). Esclusi due
«parlanti» del corpus che sono in realtà più voci (mls428, vp124812) e la frase anomala di
mls645 (etichette sbagliate del corpus, non errori dell'impronta).

  A. coseno tra le impronte di due frasi (stessa persona / persone diverse) per durata;
  B. frase contro il profilo (media di 5 frasi) di chi è stato riconosciuto da poco;
  C. raggruppamento in linea di 10 frasi di una voce (falsa compagnia) o 6+3 di due voci
     (rilevamento), con le durate delle frasi vere della DGX (02–09/10);
  D. due voci dentro una frase (finestre di 1,5 / 2 s, coseno minimo tra finestre) e costo di
     CAM++ per finestra su CPU.

    .venv\\Scripts\\python prove\\misura_voci_compagnia.py [A B C D]
"""

import collections
import itertools
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAIN = Path(r"C:\Source\Progetti\calliope")      # dati fuori da git: nella cartella principale
BASE = MAIN if (MAIN / "models" / "speaker" / "dati").exists() else ROOT
DATI = BASE / "models" / "speaker" / "dati"
MODELLO = BASE / "models" / "speaker" / "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
SR = 16000
DURATE = (1.0, 1.5, 2.0, 3.0)
FUORI = {"mls428", "vp124812"}
INCERTE = {"20260924-135711", "20260924-135714", "20260924-135725", "20260924-135740"}
# Durate della voce nelle frasi vere della DGX (registro dei turni 02–09/10, 1158 frasi)
DISTRIBUZIONE = [(0.5, 0.244), (1.0, 0.123), (1.5, 0.125), (2.0, 0.177), (3.0, 0.091),
                 ("intera", 0.24)]


def _read(path: Path) -> np.ndarray:
    import soundfile as sf
    a, _ = sf.read(str(path), dtype="float32", always_2d=True)
    return a.mean(axis=1)


def loudest(a: np.ndarray, sec: float) -> np.ndarray:
    n = int(sec * SR)
    if len(a) <= n:
        return a
    c = np.concatenate([[0.0], np.cumsum(a.astype(np.float64) ** 2)])
    e = c[n::160] - c[:len(c) - n:160][:len(c[n::160])]
    s = int(np.argmax(e)) * 160
    return a[s:s + n]


def frasi(emb):
    """[{corpus, spk, sessione, dur, audio, e: {durata: impronta}}]"""
    out = []
    for corpus in ("mls", "voxpopuli", "piper"):
        for w in sorted((DATI / corpus).glob("*/*.wav")):
            spk = w.parent.name
            if spk in FUORI:
                continue
            if corpus == "piper":
                spk = spk.split("-")[1]          # serena-high e serena-medium: una voce
            out.append({"corpus": corpus, "spk": spk, "sessione": w.parent.name, "a": _read(w)})
    for d in sorted((BASE / "registrazioni").iterdir()):
        if not d.is_dir() or d.name.startswith("2026-09-26"):
            continue
        for w in sorted(d.glob("*.wav")):
            if w.stem in INCERTE:
                continue
            a = _read(w)                         # pre-roll 0,3 s + silenzio finale 0,7 s
            a = a[int(0.3 * SR):max(int(0.3 * SR) + SR // 2, len(a) - int(0.7 * SR))]
            out.append({"corpus": "dario", "spk": "dario", "sessione": d.name, "a": a})
    for r in out:
        r["dur"] = len(r["a"]) / SR
        r["e"] = {d: emb.embed(loudest(r["a"], d)) for d in DURATE if r["dur"] >= d}
        r["e"]["intera"] = emb.embed(r["a"][:8 * SR])
    # La frase anomala di mls645 (un'altra voce nella cartella)
    v = [r for r in out if r["spk"] == "mls645"]
    if v:
        m = np.mean([r["e"]["intera"] for r in v], axis=0)
        strana = min(v, key=lambda r: float(np.dot(r["e"]["intera"], m)))
        out = [r for r in out if r is not strana]
    return out


def q(xs):
    return " / ".join(f"{np.percentile(xs, p):.2f}" for p in (1, 5, 50, 95, 99))


def misura_a(R):
    print("\n== A. Due frasi: coseno tra le impronte ==")
    umani = ("mls", "voxpopuli")
    for d in (1.5, 2.0, 3.0):
        rs = [r for r in R if d in r["e"]]
        stessa, dario, diverse = [], [], []
        for a, b in itertools.combinations(rs, 2):
            c = float(np.dot(a["e"][d], b["e"][d]))
            if a["corpus"] == b["corpus"] and a["spk"] == b["spk"]:
                (dario if a["corpus"] == "dario" else stessa if a["corpus"] in umani else []).append(c)
            elif a["corpus"] in umani and b["corpus"] in umani:
                diverse.append(c)
        print(f"  {d} s: stessa persona (corpus) p1/5/50/95/99 {q(stessa)}; Dario {q(dario)}; "
              f"persone diverse {q(diverse)}")
        for t in (0.15, 0.20, 0.25, 0.30):
            print(f"     < {t:.2f}: stessa {100 * np.mean(np.array(stessa) < t):4.1f} %, Dario "
                  f"{100 * np.mean(np.array(dario) < t):4.1f} %, diverse "
                  f"{100 * np.mean(np.array(diverse) < t):5.1f} %")


def misura_b(R, rng):
    print("\n== B. Frase contro il profilo (5 frasi) di chi è stato riconosciuto ==")
    by = collections.defaultdict(list)
    for r in R:
        by[(r["corpus"], r["spk"])].append(r)
    spk = [k for k, v in by.items() if k[0] in ("mls", "dario") and len(v) >= 8]
    own, oth = collections.defaultdict(list), collections.defaultdict(list)
    for _ in range(30):
        for k in spk:
            v = by[k]
            if k[0] == "dario":                  # arruolamento in una sessione, prova nelle altre
                sess = rng.choice(sorted({x["sessione"] for x in v if x["dur"] >= 2}))
                enr = rng.sample([x for x in v if x["sessione"] == sess and x["dur"] >= 2] * 5, 5)
                rest = [x for x in v if x["sessione"] != sess]
            else:
                enr = rng.sample(v, 5)
                scelte = {id(x) for x in enr}
                rest = [x for x in v if id(x) not in scelte]
            p = np.mean([x["e"]["intera"] for x in enr], axis=0)
            p /= np.linalg.norm(p)
            g = "Dario" if k[0] == "dario" else "MLS"
            for d in DURATE:
                own[(g, d)] += [float(np.dot(x["e"][d], p))
                                for x in rng.sample(rest, min(6, len(rest))) if d in x["e"]]
                for k2 in rng.sample([s for s in spk if s != k], 5):
                    oth[(g, d)] += [float(np.dot(x["e"][d], p))
                                    for x in rng.sample(by[k2], 2) if d in x["e"]]
    for g in ("Dario", "MLS"):
        for d in DURATE:
            o, x = np.asarray(own[(g, d)]), np.asarray(oth[(g, d)])
            print(f"  {g:5s} {d} s: stessa {q(o)} | altra {q(x)} | " + "  ".join(
                f"<{t:.2f}: stessa {100 * np.mean(o < t):4.1f} %, altra {100 * np.mean(x < t):5.1f} %"
                for t in (0.20, 0.25, 0.30)))


class Gruppi:
    """Raggruppamento in linea: una frase (>= dmin) entra nel gruppo col centroide più vicino
    se il coseno è >= tau, altrimenti apre un gruppo. Compagnia = almeno due gruppi confermati
    (due frasi, o una frase di almeno `conferma` secondi)."""

    def __init__(self, tau, dmin, conferma):
        self.tau, self.dmin, self.conf, self.g = tau, dmin, conferma, []

    def add(self, e, d) -> bool:
        if e is not None and d >= self.dmin:
            cs = [float(np.dot(e, g[0] / np.linalg.norm(g[0]))) for g in self.g]
            i = int(np.argmax(cs)) if cs else -1
            if i >= 0 and cs[i] >= self.tau:
                self.g[i][0] = self.g[i][0] + e
                self.g[i][1] += 1
                self.g[i][2] = max(self.g[i][2], d)
            else:
                self.g.append([e.copy(), 1, d])
        return sum(1 for g in self.g if g[1] >= 2 or g[2] >= self.conf) >= 2


def misura_c(R, rng):
    print("\n== C. Raggruppamento in linea (durate delle frasi vere) ==")
    by = collections.defaultdict(list)
    for r in R:
        by[(r["corpus"], r["spk"])].append(r)
    mls = [k for k, v in by.items() if k[0] == "mls" and len(v) >= 10]

    def frase(r):
        x, acc = rng.random(), 0.0
        for d, p in DISTRIBUZIONE:
            acc += p
            if x <= acc:
                break
        if d == 0.5:
            return None, 0.5
        if d == "intera" and r["dur"] >= 4:
            return r["e"]["intera"], min(r["dur"], 8.0)
        ks = [k for k in DURATE if k in r["e"] and (d == "intera" or k <= d)]
        return (r["e"][max(ks)], max(ks)) if ks else (None, r["dur"])

    N = 500
    print("  profilo tau dmin conferma | falsa compagnia una voce (sessioni MLS / Dario) | "
          "due voci 6+3 rilevate (se B ha detto una frase utile)")
    for prof in (False, True):
        for tau in (0.20, 0.25, 0.30):
            for dmin, conf in ((1.5, 3.0), (1.5, 99.0), (2.0, 99.0)):
                falsi = []
                for k0 in (None, ("dario", "dario")):
                    n = 0
                    for _ in range(N):
                        k = k0 or rng.choice(mls)
                        G = Gruppi(tau, dmin, conf)
                        if prof:
                            p = np.mean([x["e"]["intera"] for x in rng.sample(by[k], 5)], axis=0)
                            G.g.append([p * 5, 5, 9.0])
                        for _ in range(10):
                            ok = G.add(*frase(rng.choice(by[k])))
                        n += ok
                    falsi.append(100 * n / N)
                det = tot = 0
                for _ in range(N):
                    a, b = rng.sample(mls, 2)
                    ordine = ["a"] * 6 + ["b"] * 3
                    rng.shuffle(ordine)
                    G = Gruppi(tau, dmin, conf)
                    if prof:
                        p = np.mean([x["e"]["intera"] for x in rng.sample(by[a], 5)], axis=0)
                        G.g.append([p * 5, 5, 9.0])
                    preso = utile = False
                    for o in ordine:
                        e, d = frase(rng.choice(by[a if o == "a" else b]))
                        utile |= o == "b" and e is not None and d >= dmin
                        preso |= G.add(e, d)
                    if utile:
                        tot += 1
                        det += preso
                print(f"  {'sì' if prof else 'no'} {tau:.2f} {dmin} "
                      f"{conf if conf < 50 else '2 frasi'} | {falsi[0]:4.1f} / {falsi[1]:4.1f} % | "
                      f"{100 * det / max(1, tot):5.1f} % di {tot}")


def misura_d(R, rng, emb):
    print("\n== D. Due voci dentro una frase ==")
    by = collections.defaultdict(list)
    for r in R:
        if r["corpus"] in ("mls", "voxpopuli"):
            by[r["spk"]].append(r["a"])
    spk = [k for k, v in by.items() if len(v) >= 2]
    lunghe = [r["a"][:10 * SR] for r in R if r["corpus"] == "dario" and r["dur"] >= 4]

    def pezzo(a, sec):
        n = int(sec * SR)
        s = rng.randrange(0, max(1, len(a) - n))
        return a[s:s + n]

    pausa = np.zeros(int(0.3 * SR), np.float32)

    def minimo(a, w):
        n, h = int(w * SR), int(w * SR / 2)
        es = [emb.embed(a[i:i + n]) for i in range(0, max(1, len(a) - n + 1), h)]
        return min((float(np.dot(x, y)) for x, y in itertools.combinations(es, 2)), default=1.0)

    res = collections.defaultdict(list)
    for _ in range(150):
        la, lb = rng.choice((2.0, 3.0, 4.0)), rng.choice((1.5, 2.0, 3.0))
        a, b = rng.sample(spk, 2)
        mista = np.concatenate([pezzo(rng.choice(by[a]), la), pausa, pezzo(rng.choice(by[b]), lb)])
        f1, f2 = rng.sample(by[a], 2)
        due = np.concatenate([pezzo(f1, la), pausa, pezzo(f2, lb)])
        for w in (1.5, 2.0):
            res[("mista", w)].append(minimo(mista, w))
            res[("una voce, due frasi", w)].append(minimo(due, w))
    for a in lunghe:
        for w in (1.5, 2.0):
            res[("Dario, frase lunga", w)].append(minimo(a, w))
    for w in (1.5, 2.0):
        print(f"  finestra {w} s: " + "; ".join(f"{k} {q(res[(k, w)])}" for k in
                                                ("mista", "una voce, due frasi", "Dario, frase lunga")))
        for t in (0.05, 0.10, 0.15, 0.20):
            print(f"     min < {t:.2f}: " + ", ".join(
                f"{k} {100 * np.mean(np.array(res[(k, w)]) < t):4.1f} %"
                for k in ("mista", "una voce, due frasi", "Dario, frase lunga")))
    from calliope.speaker_id import SpeakerEmbedder
    x = np.random.default_rng(0).standard_normal(12 * SR).astype(np.float32) * 0.05
    for th in (2, 4):
        e = SpeakerEmbedder(str(MODELLO), threads=th)
        for sec in (1.5, 2.0, 5.0, 10.0):
            e.embed(x[:int(sec * SR)])
            t0 = time.perf_counter()
            for _ in range(10):
                e.embed(x[:int(sec * SR)])
            print(f"  costo, {th} thread, {sec} s: {100 * (time.perf_counter() - t0):.1f} ms")


def main():
    from calliope.speaker_id import SpeakerEmbedder
    parti = set(sys.argv[1:]) or {"A", "B", "C", "D"}
    emb = SpeakerEmbedder(str(MODELLO), threads=4)
    rng = random.Random(7)
    R = frasi(emb)
    print(f"{len(R)} frasi, {len({(r['corpus'], r['spk']) for r in R})} voci")
    if "A" in parti:
        misura_a(R)
    if "B" in parti:
        misura_b(R, rng)
    if "C" in parti:
        misura_c(R, rng)
    if "D" in parti:
        misura_d(R, rng, emb)


if __name__ == "__main__":
    main()
