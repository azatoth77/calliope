"""
Scarica una PARTE delle feature negative precalcolate di openWakeWord (ACAV100M,
~2000 h di parlato, musica e rumori da YouTube, in molte lingue).

Il file intero pesa 17,3 GB: qui si prendono 6 blocchi da ~500 MB sparsi nel file con
richieste HTTP a intervalli (Range), per ~970 000 finestre (~1/6 del totale).
Licenza dei dati: CC-BY-NC-SA 4.0 → il modello addestrato con queste feature è per uso
personale/non commerciale (va bene per Calliope in casa).

Uscita: wakeword/dati/acav_parziale.npy, forma (N, 16, 96) float16.
"""
import os

import numpy as np
import requests

URL = ("https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/"
       "openwakeword_features_ACAV100M_2000_hrs_16bit.npy")
HEADER = 128
ROW = 16 * 96 * 2
TOTAL = 5_625_000
N_BLOCKS, ROWS_PER_BLOCK = 6, 162_000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dati", "acav_parziale.npy")


def main():
    out = np.lib.format.open_memmap(OUT, mode="w+", dtype=np.float16,
                                    shape=(N_BLOCKS * ROWS_PER_BLOCK, 16, 96))
    for b in range(N_BLOCKS):
        first = int(b * (TOTAL - ROWS_PER_BLOCK) / (N_BLOCKS - 1))
        start = HEADER + first * ROW
        end = start + ROWS_PER_BLOCK * ROW - 1
        r = requests.get(URL, headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=60)
        r.raise_for_status()
        buf = bytearray()
        for chunk in r.iter_content(1 << 22):
            buf += chunk
        assert len(buf) == ROWS_PER_BLOCK * ROW, len(buf)
        out[b * ROWS_PER_BLOCK:(b + 1) * ROWS_PER_BLOCK] = \
            np.frombuffer(bytes(buf), np.float16).reshape(-1, 16, 96)
        print(f"blocco {b + 1}/{N_BLOCKS} (righe {first}…)", flush=True)
    out.flush()
    print("salvato", OUT)


if __name__ == "__main__":
    main()
