import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova della wake word dedicata «Calliope» (wakeword/calliope.onnx), fuori dal ciclo di Calliope.

Uso (venv principale: servono solo numpy, onnxruntime e sounddevice):
  prova_wakeword.py                     ascolta il microfono e stampa ogni risveglio
  prova_wakeword.py file.wav [...]      punteggio massimo e istante di scatto per file
Opzioni: --soglia 0.5  --consecutivi 2 (blocchi da 80 ms sopra soglia)
         --modello percorso.onnx  --dispositivo N (come CALLIOPE_INPUT_DEVICE)

Non tocca la pipeline: serve a provare la wake word a voce prima di integrarla.
Rapporto: docs/ricerche/2026-09-24-wake-word.md.
"""

import time

import numpy as np

from wakeword.detector import CHUNK, WakeWordDetector


def _arg(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


def fired(scores, thr, k):
    """Indici dei blocchi in cui gli ultimi k punteggi sono tutti sopra soglia."""
    a = np.asarray(scores) >= thr
    ok = a.copy()
    for j in range(1, k):
        ok[j:] &= a[:-j]
        ok[:j] = False
    return np.where(ok)[0]


def run_files(det, files, thr, k):
    import soundfile as sf
    for f in files:
        audio, sr = sf.read(f, dtype="float32")
        assert sr == 16000, f"{f}: serve audio a 16 kHz"
        det.reset()
        x = np.concatenate([np.zeros(CHUNK * 10, np.float32), audio,
                            np.zeros(CHUNK * 10, np.float32)])
        scores = [det.process(x[i:i + CHUNK]) for i in range(0, len(x) - CHUNK + 1, CHUNK)]
        scores = np.array(scores)
        hit = fired(scores, thr, k)
        when = f"scatta a {(hit[0] + 1) * CHUNK / 16000 - 0.8:.2f} s" if len(hit) else "nessun risveglio"
        print(f"{os.path.basename(f)}: massimo {scores.max():.3f}, {when}")


def run_mic(det, thr, device, k):
    import sounddevice as sd
    print(f"In ascolto (soglia {thr}). Di' «Calliope»… Ctrl+C per uscire.")
    last = 0.0
    costs = []
    run = 0     # blocchi consecutivi sopra soglia
    with sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=CHUNK,
                        device=device) as stream:
        try:
            while True:
                block, _ = stream.read(CHUNK)
                t = time.perf_counter()
                s = det.process(block[:, 0])
                costs.append(time.perf_counter() - t)
                if s is None:
                    continue
                run = run + 1 if s >= thr else 0
                if run >= k and time.monotonic() - last > 2.0:
                    last = time.monotonic()
                    print(f"  {time.strftime('%H:%M:%S')}  Calliope! (punteggio {s:.3f})", flush=True)
        except KeyboardInterrupt:
            c = np.array(costs) * 1000
            print(f"\nCosto per blocco da 80 ms: media {c.mean():.2f} ms, p99 {np.percentile(c, 99):.2f} ms")


def main():
    thr = float(_arg("--soglia", "0.5"))
    k = int(_arg("--consecutivi", "2"))
    model = _arg("--modello", None)
    dev = _arg("--dispositivo", os.environ.get("CALLIOPE_INPUT_DEVICE"))
    dev = int(dev) if dev is not None and dev.isdigit() else dev
    det = WakeWordDetector(model, threads=1)
    files = sys.argv[1:]
    if files:
        run_files(det, files, thr, k)
    else:
        run_mic(det, thr, dev, k)


if __name__ == "__main__":
    main()
