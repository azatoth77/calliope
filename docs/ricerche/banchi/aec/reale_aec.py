r"""Applica i motori AEC alle registrazioni reali di aec/misura_reale.py (solo eco).

Uso: docs\ricerche\banchi\aec\.venv\Scripts\python.exe docs\ricerche\banchi\aec\reale_aec.py   → aec/dati/reale/out/<tag>_<motore>.wav
     e aec/dati/reale/erle.json (ERLE e livelli sulla zona in cui c'è eco)
"""
import json
from pathlib import Path

import numpy as np
import soundfile as sf

import motori

D = Path(__file__).resolve().parent / "dati" / "reale"


def db(x):
    return float(10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-20))


def main():
    (D / "out").mkdir(exist_ok=True)
    res = []
    for f in sorted(D.glob("eco_*.wav")):
        tag = f.stem[4:]
        mic, _ = sf.read(f, dtype="float32")
        ref, _ = sf.read(D / f"rif_{tag}.wav", dtype="float32")
        d = motori.stima_ritardo(mic, ref)
        act = np.convolve(np.abs(motori.ritarda(ref, d)) > 1e-3, np.ones(1600), "same") > 0
        quiet = np.zeros(len(mic), bool)
        quiet[:int(0.9 * motori.SR)] = True          # prima della frase: solo rumore
        for m in motori.tutti():
            m.stima_s = 60
            out, cpu = m.run(mic, ref)
            sf.write(D / "out" / f"{tag}_{m.nome}.wav", out, motori.SR, subtype="FLOAT")
            r = {"tag": tag, "motore": m.nome, "ritardo_ms": d / 16,
                 "eco_dbfs": round(db(mic[act]), 1), "uscita_dbfs": round(db(out[act]), 1),
                 "rumore_in_dbfs": round(db(mic[quiet]), 1), "rumore_out_dbfs": round(db(out[quiet]), 1),
                 "erle_db": round(db(mic[act]) - db(out[act]), 1),
                 "erle_2a_meta_db": round(db(mic[act][len(mic[act]) // 2:]) - db(out[act][len(out[act]) // 2:]), 1),
                 "cpu_ms_10ms": round(cpu, 3)}
            res.append(r)
            print(r, flush=True)
    json.dump(res, open(D / "erle.json", "w"), indent=1)


if __name__ == "__main__":
    main()
