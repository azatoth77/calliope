"""
Dalle clip sintetiche e dal parlato MLS alle feature per il classificatore.

Ogni esempio è una finestra di 2 s di audio → 16 embedding da 96 (le stesse che il
rilevatore vede in streaming). Aumenti di dati: guadagno, riverbero sintetico, filtri
passa-banda (microfono della webcam), rumore colorato e parlato MLS di sottofondo.

- Positivi: il nome finisce tra 20 e 350 ms prima della fine della finestra (il
  rilevatore deve scattare appena finita la parola, anche se la frase continua).
- Negativi: parole simili, frasi generiche, PEZZI del nome («Calli…»), rumori, silenzio,
  e il parlato MLS (dev + train) come sequenza continua di embedding.

Uscita in wakeword/dati/feat/: pos.npy, pos_val.npy, neg.npy, mls_seq.npy (float16).

    .\\wakeword\\.venv\\Scripts\\python.exe wakeword\\feature.py
"""
from __future__ import annotations

import glob
import os
import pickle
import random
import sys
import time

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from detector import FeatureExtractor  # noqa: E402

SR = 16000
WIN = 32000           # 2 s → esattamente 16 embedding
FEAT = os.path.join(HERE, "dati", "feat")
MLS = os.path.join(HERE, "dati", "mls")
TTS = os.path.join(HERE, "dati", "tts")
BASE_FEAT = FEAT                  # le feature di «Calliope»: negativi e MLS riusati

# Un'altra parola (04/10, parole.py): WW_PAROLA=computer. Si legge all'import, così vale
# anche nei processi di lavoro (multiprocessing «spawn» reimporta il modulo)
PAROLA = os.environ.get("WW_PAROLA", "").strip().lower()
if PAROLA == "calliope":
    PAROLA = ""
if PAROLA:
    FEAT = os.path.join(HERE, "dati", f"feat-{PAROLA}")
    TTS = os.path.join(HERE, "dati", f"tts-{PAROLA}")

_fx = None
_bg = None
_speech = None


def _init(seed_bg_files):
    global _fx, _bg, _speech
    _fx = FeatureExtractor(threads=1)
    # frasi sintetiche da mettere PRIMA del nome («… Calliope»): il nome non arriva
    # sempre dopo un silenzio
    frasi = os.path.join(TTS, "neg_frasi.pkl")
    _speech = pickle.load(open(frasi, "rb")) if os.path.exists(frasi) else []
    if not _speech:                        # parola nuova senza frasi MLS: le frasi simili
        _speech = pickle.load(open(os.path.join(TTS, "neg_simili.pkl"), "rb"))
    # sottofondo: qualche minuto di parlato MLS (solo train) caricato in memoria
    rng = random.Random(len(seed_bg_files))
    _bg = []
    for f in rng.sample(seed_bg_files, min(150, len(seed_bg_files))):
        a, _ = sf.read(f, dtype="float32")
        _bg.append(a)


def colored_noise(n, rng: np.random.Generator):
    kind = rng.integers(3)
    w = rng.standard_normal(n).astype(np.float32)
    if kind == 0:
        return w
    f = np.fft.rfft(w)
    freqs = np.arange(len(f)) + 1.0
    f /= freqs ** (0.5 if kind == 1 else 1.0)   # rosa o marrone
    x = np.fft.irfft(f, n).astype(np.float32)
    return x / (x.std() + 1e-9)


def synthetic_rir(rng: np.random.Generator):
    rt60 = rng.uniform(0.15, 0.7)
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    rir = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    rir[0] = rng.uniform(2, 8)                      # percorso diretto
    return (rir / np.abs(rir).sum() * 4).astype(np.float32)


def augment(x: np.ndarray, rng: np.random.Generator, bg_level=True) -> np.ndarray:
    x = x.astype(np.float32)
    if rng.random() < 0.5:
        x = fftconvolve(x, synthetic_rir(rng))[:len(x)].astype(np.float32)
    if rng.random() < 0.6:
        lo = rng.uniform(60, 300)
        hi = rng.uniform(3000, 7800)
        x = sosfilt(butter(4, [lo, hi], "bandpass", fs=SR, output="sos"), x).astype(np.float32)
    sig = np.sqrt(np.mean(x ** 2)) + 1e-9
    r = rng.random()
    if bg_level and r < 0.45 and _bg:
        b = _bg[rng.integers(len(_bg))]
        if len(b) < len(x):
            b = np.tile(b, len(x) // len(b) + 1)
        s = rng.integers(0, len(b) - len(x) + 1)
        b = b[s:s + len(x)]
        snr = rng.uniform(5, 25)
        x = x + b / (np.sqrt(np.mean(b ** 2)) + 1e-9) * sig / 10 ** (snr / 20)
    elif bg_level and r < 0.85:
        snr = rng.uniform(5, 35)
        x = x + colored_noise(len(x), rng) * sig / 10 ** (snr / 20)
    else:
        x = x + rng.standard_normal(len(x)).astype(np.float32) * 1e-4
    peak = rng.uniform(0.1, 0.9)
    x = x / (np.abs(x).max() + 1e-9) * peak
    # rumore di fondo del microfono: nelle registrazioni reali è tra -70 e -60 dBFS
    floor = 10 ** (rng.uniform(-78, -50) / 20)
    return (x + colored_noise(len(x), rng) * floor).astype(np.float32)


def place(clip: np.ndarray, end_at: int, rng, total=WIN) -> np.ndarray:
    """Mette `clip` in una finestra lunga `total` in modo che finisca al campione end_at."""
    out = np.zeros(total, np.float32)
    start = end_at - len(clip)
    a0, c0 = max(0, start), max(0, -start)
    n = min(total - a0, len(clip) - c0)
    out[a0:a0 + n] = clip[c0:c0 + n]
    return out


def feats(x: np.ndarray) -> np.ndarray:
    e = _fx.embeddings(x)
    assert e.shape[0] >= 16, e.shape
    return e[-16:].astype(np.float16)


def _pos_job(args):
    items, seed = args
    rng = np.random.default_rng(seed)
    out, out_neg = [], []
    for clip, end in items:
        c = clip.astype(np.float32) / 32767
        if rng.random() < 0.35:
            pre = _speech[rng.integers(len(_speech))].astype(np.float32) / 32767
            gap = np.zeros(int(rng.uniform(0.0, 0.5) * SR), np.float32)
            c = np.concatenate([pre * rng.uniform(0.5, 1.2), gap, c])
            end += len(pre) + len(gap)
        # positivo: fine del nome tra 20 e 350 ms prima della fine della finestra
        delay = int(rng.uniform(0.02, 0.35) * SR)
        # nel pezzo dopo il nome (se c'è un seguito) si tiene l'audio vero
        w = place(c, WIN - delay + (len(c) - end), rng)
        out.append(feats(augment(w, rng)))
        # negativo difficile: solo l'inizio del nome (fino al 40–65%), seguito da nulla
        if rng.random() < 0.5:
            name_start = max(0, end - int(0.8 * SR))
            cut = int(end - (end - name_start) * rng.uniform(0.35, 0.6))
            part = c[:max(1, cut)]
            w = place(part, WIN - int(rng.uniform(0.0, 0.3) * SR), rng)
            out_neg.append(feats(augment(w, rng)))
    return out, out_neg


def _neg_job(args):
    clips, seed = args
    rng = np.random.default_rng(seed)
    out = []
    for clip in clips:
        c = clip.astype(np.float32) / 32767
        for _ in range(2):
            r = rng.random()
            if r < 0.4:      # la clip finisce sul bordo destro (come un positivo)
                end_at = WIN - int(rng.uniform(0, 0.35) * SR)
            elif r < 0.7:    # si vede l'attacco dopo un silenzio (come le frasi dopo il VAD)
                end_at = int(rng.uniform(0.2, 1.8) * SR) + len(c)
            else:
                end_at = int(rng.uniform(0.3, 1.0) * (WIN + len(c)))
            out.append(feats(augment(place(c, min(end_at, WIN + len(c) - 1), rng), rng)))
    return out


def _noise_job(args):
    n, seed = args
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        k = rng.integers(4)
        if k == 0:
            x = colored_noise(WIN, rng) * rng.uniform(0.001, 0.3)
        elif k == 1:                               # clic (tastiera, stoviglie)
            x = np.zeros(WIN, np.float32)
            for t in rng.integers(0, WIN - 400, rng.integers(3, 30)):
                x[t:t + 400] += (rng.standard_normal(400) * np.exp(-np.arange(400) / 40)
                                 * rng.uniform(0.05, 0.8)).astype(np.float32)
        elif k == 2:                               # toni e accordi (musica, elettrodomestici)
            t = np.arange(WIN) / SR
            x = sum(np.sin(2 * np.pi * rng.uniform(80, 2000) * t + rng.uniform(0, 6))
                    for _ in range(rng.integers(1, 5))).astype(np.float32)
            x *= rng.uniform(0.01, 0.5) / (np.abs(x).max() + 1e-9)
        else:                                      # silenzio quasi totale
            x = rng.standard_normal(WIN).astype(np.float32) * rng.uniform(1e-5, 1e-3)
        out.append(feats(x.astype(np.float32)))
    return out


def _mls_job(args):
    files, seed = args
    rng = np.random.default_rng(seed)
    seqs = []
    for f in files:
        a, _ = sf.read(f, dtype="float32")
        # silenzio prima e dopo: così ci sono anche le finestre con l'attacco del parlato
        a = np.concatenate([np.zeros(int(rng.uniform(0.3, 2.5) * SR), np.float32), a,
                            np.zeros(int(rng.uniform(0.0, 1.0) * SR), np.float32)])
        if rng.random() < 0.5:
            a = augment(a, rng, bg_level=False)
        else:
            a = a / (np.abs(a).max() + 1e-9) * rng.uniform(0.1, 0.9)
            a = a + colored_noise(len(a), rng) * 10 ** (rng.uniform(-78, -50) / 20)
        seqs.append(_fx.embeddings(a).astype(np.float16))
    return seqs


def chunks(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def main(procs=16):
    from multiprocessing import Pool
    os.makedirs(FEAT, exist_ok=True)
    t0 = time.time()
    load = lambda n: pickle.load(open(os.path.join(TTS, n + ".pkl"), "rb"))
    pos, sim = load("pos"), load("neg_simili")
    phr = load("neg_frasi") if os.path.exists(os.path.join(TTS, "neg_frasi.pkl")) else []
    if PAROLA:
        return _main_parola(procs, pos, sim, phr, t0)
    rng = random.Random(0)
    rng.shuffle(pos)
    n_val = len(pos) // 10
    pos_val, pos_tr = pos[:n_val], pos[n_val:]
    bg_files = sorted(glob.glob(os.path.join(MLS, "train", "*.flac")))
    mls_files = sorted(glob.glob(os.path.join(MLS, "dev", "*.flac"))) + bg_files
    # frasi MLS con il nome (improbabile, ma si controlla)
    bad = set()
    for p in glob.glob(os.path.join(MLS, "*", "transcripts.txt")):
        for line in open(p, encoding="utf-8"):
            k, _, txt = line.partition("\t")
            if "callio" in txt.lower():
                bad.add(k)
    mls_files = [f for f in mls_files if os.path.basename(f)[:-5] not in bad]
    print(f"positivi {len(pos_tr)} + {n_val} validazione, simili {len(sim)}, frasi {len(phr)}, "
          f"file MLS {len(mls_files)} (esclusi col nome: {len(bad)})", flush=True)

    with Pool(procs, initializer=_init, initargs=(bg_files,)) as pool:
        P, H = [], []
        for i, (p, h) in enumerate(pool.imap_unordered(
                _pos_job, [(c, i) for i, c in enumerate(chunks(pos_tr * 2, 200))])):
            P += p; H += h
        print(f"  positivi: {len(P)}, pezzi del nome: {len(H)} ({time.time() - t0:.0f} s)", flush=True)
        PV = []
        for p, _ in pool.imap_unordered(_pos_job, [(c, 10_000 + i) for i, c in
                                                   enumerate(chunks(pos_val, 200))]):
            PV += p
        N = []
        for n in pool.imap_unordered(_neg_job, [(c, 20_000 + i) for i, c in
                                                enumerate(chunks(sim + phr, 200))]):
            N += n
        print(f"  negativi sintetici: {len(N)} ({time.time() - t0:.0f} s)", flush=True)
        for n in pool.imap_unordered(_noise_job, [(250, 30_000 + i) for i in range(32)]):
            N += n
        S = []
        for s in pool.imap_unordered(_mls_job, [(c, 40_000 + i) for i, c in
                                                enumerate(chunks(mls_files, 50))]):
            S += s
        print(f"  MLS: {len(S)} file, {sum(len(s) for s in S) * 0.08 / 3600:.1f} h "
              f"({time.time() - t0:.0f} s)", flush=True)

    np.save(os.path.join(FEAT, "pos.npy"), np.stack(P))
    np.save(os.path.join(FEAT, "pos_val.npy"), np.stack(PV))
    np.save(os.path.join(FEAT, "neg.npy"), np.stack(N + H))
    # sequenze MLS concatenate; mls_len.npy dice dove finisce ciascun file
    lens = np.array([len(s) for s in S])
    np.save(os.path.join(FEAT, "mls_seq.npy"), np.concatenate(S))
    np.save(os.path.join(FEAT, "mls_len.npy"), lens)
    print(f"fatto in {time.time() - t0:.0f} s")


def _main_parola(procs, pos, sim, phr, t0):
    """Un'altra parola (WW_PAROLA): positivi, pezzi e simili nuovi; negativi generici e
    parlato MLS ripresi dalle feature di «Calliope» (BASE_FEAT), senza MLS grezzo."""
    from multiprocessing import Pool
    rng = random.Random(0)
    rng.shuffle(pos)
    n_val = len(pos) // 10
    pos_val, pos_tr = pos[:n_val], pos[n_val:]
    print(f"[{PAROLA}] positivi {len(pos_tr)} + {n_val} validazione, simili {len(sim)}, "
          f"frasi {len(phr)}", flush=True)
    with Pool(procs, initializer=_init, initargs=([],)) as pool:
        P, H = [], []
        for p, h in pool.imap_unordered(_pos_job, [(c, i) for i, c in
                                                   enumerate(chunks(pos_tr * 2, 200))]):
            P += p
            H += h
        PV = []
        for p, _ in pool.imap_unordered(_pos_job, [(c, 10_000 + i) for i, c in
                                                   enumerate(chunks(pos_val, 200))]):
            PV += p
        N = []
        for n in pool.imap_unordered(_neg_job, [(c, 20_000 + i) for i, c in
                                                enumerate(chunks(sim + phr, 200))]):
            N += n
    print(f"  positivi {len(P)}, pezzi {len(H)}, simili {len(N)} ({time.time() - t0:.0f} s)",
          flush=True)
    vecchi = np.load(os.path.join(BASE_FEAT, "neg.npy"))
    np.save(os.path.join(FEAT, "pos.npy"), np.stack(P))
    np.save(os.path.join(FEAT, "pos_val.npy"), np.stack(PV))
    np.save(os.path.join(FEAT, "neg.npy"), np.concatenate([np.stack(N + H), vecchi]))
    import shutil
    for f in ("mls_seq.npy", "mls_len.npy"):
        shutil.copyfile(os.path.join(BASE_FEAT, f), os.path.join(FEAT, f))
    print(f"fatto in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
