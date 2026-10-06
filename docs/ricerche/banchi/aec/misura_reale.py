r"""Misura reale dell'eco: riproduce una frase Piper dall'altoparlante e registra il microfono.

Nessuna voce umana: serve solo a sapere quanto e con che ritardo la voce di Calliope
rientra nel microfono. Imita Speaker/Listener di calliope/tts.py e calliope/audio.py: uscita RawOutputStream
int16 alla frequenza di Piper (22050 Hz) con silenzio iniziale e keepalive, ingresso
InputStream float32 a 16 kHz a blocchi di 512 campioni sempre aperto.

Il ritardo misurato è quello che vedrebbe il programma: dal momento in cui la frase
viene passata a stream.write() al momento in cui l'eco arriva nella callback del
microfono (quindi comprende buffer di PortAudio, driver e aria).

Uso (venv aec\.venv, che ha sounddevice):
    docs\ricerche\banchi\aec\.venv\Scripts\python.exe docs\ricerche\banchi\aec\misura_reale.py [--mic "C920 MME"] [--out "Speakers (Realtek(R) Audio) MME"]
        [--frasi 0,6] [--guadagni 1.0,0.5] [--sessione A]

Scrive in aec/dati/reale/: eco_<sessione>_<n>.wav (microfono, 16 kHz) e
rif_<sessione>_<n>.wav (la frase ricampionata a 16 kHz, posta sulla linea temporale
del microfono nell'istante del write), più un riepilogo JSON.
"""
import argparse
import json
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
import soxr

ROOT = Path(__file__).resolve().parents[4]   # radice del repository (docs/ricerche/banchi/aec)
RIF = ROOT / "docs" / "ricerche" / "banchi" / "aec" / "dati" / "rif"
OUT = ROOT / "docs" / "ricerche" / "banchi" / "aec" / "dati" / "reale"
SR_MIC = 16000


def find_device(name: str, kind: str) -> int:
    """Cerca per nome; «… MME» restringe all'API MME (come avvia_calliope.py)."""
    if name.isdigit():
        return int(name)
    try:
        return sd.query_devices(name, kind)["index"]
    except Exception:
        pass
    base, _, api = name.rpartition(" ")
    for d in sd.query_devices():
        if base in d["name"] and d[f"max_{kind}_channels"] > 0 and \
                sd.query_hostapis(d["hostapi"])["name"] == api:
            return d["index"]
    raise SystemExit(f"Dispositivo {kind} non trovato: {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mic", default="Microphone (Realtek(R) Audio) MME")
    ap.add_argument("--out", default="Speakers (Realtek(R) Audio) MME")
    ap.add_argument("--frasi", default="0,6")
    ap.add_argument("--guadagni", default="1.0,0.5")
    ap.add_argument("--sessione", default="A")
    ap.add_argument("--mic-sr", type=int, default=SR_MIC,
                    help="frequenza nativa del microfono (WDM-KS non ricampiona)")
    ap.add_argument("--mic-ch", type=int, default=1)
    a = ap.parse_args()
    mic, spk = find_device(a.mic, "input"), find_device(a.out, "output")
    print(f"microfono: {sd.query_devices(mic)['name']} | uscita: {sd.query_devices(spk)['name']}")
    OUT.mkdir(parents=True, exist_ok=True)

    captured, lock = [], threading.Lock()
    n_in = [0]

    def cb(indata, n, t, status):
        with lock:
            captured.append(indata[:, 0].copy())
            n_in[0] += n

    frasi = [int(x) for x in a.frasi.split(",")]
    guadagni = [float(x) for x in a.guadagni.split(",")]
    summary = []
    msr = a.mic_sr
    ins = sd.InputStream(samplerate=msr, channels=a.mic_ch, dtype="float32",
                         blocksize=512 * msr // SR_MIC,
                         device=mic, callback=cb)
    ins.start()
    for k, (fi, g) in enumerate(zip(frasi, guadagni)):
        pcm, sr = sf.read(RIF / f"rif_{fi:02d}.wav", dtype="int16")
        pcm = (pcm.astype(np.float32) * g).astype(np.int16)
        outs = sd.RawOutputStream(samplerate=sr, channels=1, dtype="int16", device=spk)
        outs.start()
        outs.write(b"\0\0" * int(sr * 0.3))             # tts_lead_s
        for _ in range(75):                              # 1,5 s di keepalive (blocchi da 20 ms)
            outs.write(b"\0\0" * int(sr * 0.02))
        with lock:
            start_in = n_in[0]
            i0 = len(captured)
        t_write = time.perf_counter()
        outs.write(pcm.tobytes())
        t_done = time.perf_counter()
        for _ in range(100):                             # 2 s di keepalive dopo la frase
            outs.write(b"\0\0" * int(sr * 0.02))
        outs.write(b"\0\0" * int(sr * 0.3))             # tts_tail_s
        outs.stop()
        outs.close()
        time.sleep(0.3)
        with lock:
            n_before = sum(len(c) for c in captured[:i0])
            rec = np.concatenate(captured)
        # Linea temporale del microfono: dall'inizio della riproduzione (meno 1 s) in poi
        s0 = max(0, n_before - msr)
        mic_sig = rec[s0:]
        if msr != SR_MIC:
            mic_sig = soxr.resample(mic_sig, msr, SR_MIC)
            start_in, s0 = round(start_in * SR_MIC / msr), round(s0 * SR_MIC / msr)
        ref16 = soxr.resample(pcm.astype(np.float32) / 32768, sr, SR_MIC)
        ref_line = np.zeros_like(mic_sig)
        off = start_in - s0
        m = min(len(ref16), len(ref_line) - off)
        ref_line[off:off + m] = ref16[:m]
        tag = f"{a.sessione}_{k}"
        sf.write(OUT / f"eco_{tag}.wav", mic_sig, SR_MIC, subtype="FLOAT")
        sf.write(OUT / f"rif_{tag}.wav", ref_line, SR_MIC, subtype="FLOAT")
        summary.append({"tag": tag, "frase": fi, "guadagno": g, "sr_uscita": sr,
                        "write_s": round(t_done - t_write, 3),
                        "durata_frase_s": round(len(pcm) / sr, 3),
                        "latenza_uscita_s": outs.latency, "latenza_ingresso_s": ins.latency})
        print(summary[-1], flush=True)
        with lock:
            captured.clear()
            n_in[0] = 0
        time.sleep(0.5)
    ins.stop()
    ins.close()
    with open(OUT / f"riepilogo_{a.sessione}.json", "w", encoding="utf-8") as f:
        json.dump({"mic": sd.query_devices(mic)["name"], "uscita": sd.query_devices(spk)["name"],
                   "prove": summary}, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
