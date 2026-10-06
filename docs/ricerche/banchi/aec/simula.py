r"""Simulazione offline dell'eco per il barge-in di «livello B» (AEC software).

Costruisce, per ogni condizione acustica, una lunga linea temporale a 16 kHz con tre
tipi di segmento, ripetuti per N frasi dell'utente:
  eco     Calliope parla, l'utente tace (serve per ERLE e falsi barge-in)
  doppio  l'utente parla sopra Calliope (la voce deve sopravvivere)
  utente  l'utente parla da solo (l'AEC non deve rovinarla)

La voce di Calliope è Piper a 22050 Hz (aec/dati/rif, da genera_riferimenti.py). L'eco
passa da: saturazione dell'altoparlantino, passa-alto, risposta all'impulso sintetica
della stanza, ritardo (con salti per il Bluetooth), deriva di clock tra uscita e
microfono (ricampionamento 22050·(1+ppm) → 16000) e rumore. Il riferimento dato
all'AEC è invece il ricampionamento esatto 22050 → 16000, come in un'integrazione
reale. Le frasi dell'utente sono registrazioni vere (registrazioni/*/, C920).

Il flusso è continuo: lo stato dell'AEC resta tra un segmento e l'altro, come se
girasse sempre (Calliope parla spesso). Il primo segmento misura l'avvio a freddo.

Uso (venv aec\.venv):
    docs\ricerche\banchi\aec\.venv\Scripts\python.exe docs\ricerche\banchi\aec\simula.py [--utenti 30] [--condizioni cassa,forte,bluetooth]
Scrive in aec/dati/sim/<condizione>/: mic.wav, rif.wav, <motore>.wav, segmenti.json,
e aec/dati/sim/erle.json.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
from scipy.signal import butter, fftconvolve, sosfilt

import motori

ROOT = Path(__file__).resolve().parents[4]   # radice del repository (docs/ricerche/banchi/aec)
DATI = ROOT / "docs" / "ricerche" / "banchi" / "aec" / "dati"
SR = 16000
SR_TTS = 22050
GAP_S = 1.2

# Condizioni acustiche. Il ritardo di 300 ms viene dalla misura reale (altoparlante del
# portatile via MME: 294–298 ms dal write() alla callback del microfono).
CONDIZIONI = {
    "cassa":     dict(ritardo_ms=300, ppm=30, ser_db=0, sat=1.2, rt60=0.35, salti=[]),
    "forte":     dict(ritardo_ms=300, ppm=30, ser_db=10, sat=3.0, rt60=0.45, salti=[]),
    "bluetooth": dict(ritardo_ms=250, ppm=50, ser_db=0, sat=1.2, rt60=0.35,
                      salti=[(0.33, +40), (0.66, -25)]),   # (frazione, ms) salti del buffer
}
# Varianti «con interruzione»: nel doppio parlato Calliope smette di parlare stop_s dopo
# l'inizio della voce dell'utente (VAD ~0,3 s + reazione), come farebbe il barge-in vero.
# L'eco continua ancora per il ritardo del percorso e la coda della stanza.
CONDIZIONI["cassa-stop"] = dict(CONDIZIONI["cassa"], stop_s=0.4)
CONDIZIONI["forte-stop"] = dict(CONDIZIONI["forte"], stop_s=0.4)


def rir_sintetica(rng, rt60, dur=0.5):
    """Percorso diretto + prime riflessioni + coda esponenziale di rumore."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    h = np.zeros(n)
    h[0] = 1.0
    for _ in range(8):                               # prime riflessioni 2–25 ms
        k = rng.integers(int(0.002 * SR), int(0.025 * SR))
        h[k] += rng.uniform(-0.5, 0.5)
    coda = rng.normal(0, 1, n) * np.exp(-6.91 * t / rt60)
    coda[: int(0.005 * SR)] = 0
    h += 0.25 * coda
    return h / np.sqrt(np.sum(h ** 2))


def utenti(n, rng):
    rows = [r for r in csv.DictReader(open(ROOT / "prove" / "riferimenti_whisper.tsv",
                                           encoding="utf-8"), delimiter="\t")
            if r["sicurezza"] == "sicura"]
    sel = []
    for r in rows:
        x, sr = sf.read(ROOT / "registrazioni" / r["cartella"] / f"{r['stem']}.wav",
                        dtype="float32")
        if sr == SR and 1.5 <= len(x) / SR <= 6.0 and len(r["riferimento"].split()) >= 2:
            sel.append((r, x))
    idx = rng.choice(len(sel), size=min(n, len(sel)), replace=False)
    return [sel[i] for i in sorted(idx)]


def costruisci(cond, par, users, refs, rng):
    """Restituisce mic, riferimento (16 kHz) e la lista dei segmenti."""
    tl_play, segs = [], []                           # (inizio_s, pcm22k)
    t = 1.0
    user_parts = []                                  # (inizio_s, audio16k)
    for i, (row, ux) in enumerate(users):
        r1 = refs[i % len(refs)]
        tl_play.append((t, r1))
        d1 = len(r1) / SR_TTS
        segs.append(dict(tipo="eco", inizio=t, fine=t + d1 + par["ritardo_ms"] / 1000 + 0.3))
        t += d1 + GAP_S + par["ritardo_ms"] / 1000
        r2 = refs[(i + 5) % len(refs)]
        d2 = len(r2) / SR_TTS
        off = rng.uniform(0.3, max(0.4, d2 - 1.0))
        us = t + par["ritardo_ms"] / 1000 + off      # l'utente parla sopra l'eco vera
        if "stop_s" in par:                          # Calliope si interrompe
            r2 = r2[: int((us + par["stop_s"] - t) * SR_TTS)]
        tl_play.append((t, r2))
        user_parts.append((us, ux))
        fine = max(t + d2 + par["ritardo_ms"] / 1000, us + len(ux) / SR)
        segs.append(dict(tipo="doppio", inizio=t, fine=fine, u_inizio=us,
                         u_fine=us + len(ux) / SR, testo=row["riferimento"],
                         file=f"{row['cartella']}/{row['stem']}"))
        t = fine + GAP_S
        user_parts.append((t, ux))
        segs.append(dict(tipo="utente", inizio=t, fine=t + len(ux) / SR, u_inizio=t,
                         u_fine=t + len(ux) / SR, testo=row["riferimento"],
                         file=f"{row['cartella']}/{row['stem']}"))
        t += len(ux) / SR + GAP_S
    tot = t + 1.0

    # Ciò che Calliope riproduce (22050 Hz) e il riferimento che vedrebbe l'AEC
    play = np.zeros(int(tot * SR_TTS) + SR_TTS, np.float32)
    for s, pcm in tl_play:
        k = int(s * SR_TTS)
        play[k:k + len(pcm)] += pcm
    ref = soxr.resample(play, SR_TTS, SR)[: int(tot * SR)]

    # Percorso dell'eco: deriva di clock, altoparlante, stanza, ritardo, salti
    eco = soxr.resample(play, SR_TTS * (1 + par["ppm"] * 1e-6), SR)[: len(ref)]
    a = par["sat"]
    eco = np.tanh(a * eco / (np.abs(eco).max() + 1e-9)) / np.tanh(a)
    eco = sosfilt(butter(2, 200, "highpass", fs=SR, output="sos"), eco)
    eco = fftconvolve(eco, rir_sintetica(rng, par["rt60"]))[: len(ref)]
    d = int(par["ritardo_ms"] * SR / 1000)
    eco = np.concatenate([np.zeros(d), eco])[: len(ref)]
    for frac, ms in par["salti"]:
        k, dk = int(frac * len(eco)), int(abs(ms) * SR / 1000)
        if ms > 0:
            eco = np.concatenate([eco[:k], np.zeros(dk), eco[k:]])[: len(ref)]
        else:
            eco = np.concatenate([eco[:k], eco[k + dk:], np.zeros(dk)])[: len(ref)]

    # Livelli: eco attiva = voce dell'utente (mediana) + ser_db
    voce = np.zeros(len(ref))
    for s, ux in user_parts:
        k = int(s * SR)
        voce[k:k + len(ux)] += ux[: len(voce) - k]
    u_rms = np.median([np.sqrt(np.mean(ux ** 2)) for _, ux in users])
    att = np.abs(eco) > 1e-4
    eco *= u_rms * 10 ** (par["ser_db"] / 20) / np.sqrt(np.mean(eco[att] ** 2))
    rumore = sosfilt(butter(1, 1000, "lowpass", fs=SR, output="sos"),
                     rng.normal(0, 1, len(ref)))
    rumore *= 10 ** (-62 / 20) / np.sqrt(np.mean(rumore ** 2))
    mic = (eco + voce + rumore).astype(np.float32)
    return mic, ref.astype(np.float32), eco.astype(np.float32), segs


def db(x):
    return float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--utenti", type=int, default=30)
    ap.add_argument("--condizioni", default=",".join(CONDIZIONI))
    ap.add_argument("--motori", default="")
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    users = utenti(a.utenti, rng)
    refs = [sf.read(p, dtype="float32")[0] for p in sorted((DATI / "rif").glob("rif_*.wav"))]
    risultati = []
    erle_path = DATI / "sim" / "erle.json"
    if erle_path.exists():
        nuovi = set(a.motori.split(",")) if a.motori else None
        risultati = [r for r in json.load(open(erle_path))
                     if r["condizione"] not in a.condizioni.split(",")
                     or (nuovi is not None and r["motore"] not in nuovi)]
    for cond in a.condizioni.split(","):
        par = CONDIZIONI[cond]
        out_dir = DATI / "sim" / cond
        out_dir.mkdir(parents=True, exist_ok=True)
        mic, ref, eco, segs = costruisci(cond, par, users, refs, np.random.default_rng(1))
        sf.write(out_dir / "mic.wav", mic, SR, subtype="FLOAT")
        sf.write(out_dir / "rif.wav", ref, SR, subtype="FLOAT")
        json.dump({"parametri": par, "segmenti": segs}, open(out_dir / "segmenti.json", "w",
                  encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"== {cond}: {len(mic) / SR / 60:.1f} min, {len(segs)} segmenti", flush=True)
        eco_segs = [s for s in segs if s["tipo"] == "eco"]
        for m in motori.tutti():
            if a.motori and m.nome not in a.motori.split(","):
                continue
            out, cpu = m.run(mic, ref)
            sf.write(out_dir / f"{m.nome}.wav", out, SR, subtype="FLOAT")
            erle = []
            for s in eco_segs:
                k0, k1 = int(s["inizio"] * SR), int(s["fine"] * SR)
                act = np.abs(eco[k0:k1]) > 1e-3
                erle.append(db(mic[k0:k1][act]) - db(out[k0:k1][act]))
            r = {"condizione": cond, "motore": m.nome, "cpu_ms_10ms": round(cpu, 3),
                 "erle_primo_db": round(erle[0], 1),
                 "erle_mediana_db": round(float(np.median(erle[1:])), 1),
                 "erle_p10_db": round(float(np.percentile(erle[1:], 10)), 1),
                 "ritardo_stimato_ms": getattr(m, "ritardo", 0) / 16}
            risultati.append(r)
            print(r, flush=True)
            json.dump(risultati, open(erle_path, "w"), indent=1)


if __name__ == "__main__":
    main()
