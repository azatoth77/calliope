"""
Recupero dei tool per similarità, senza LLM: richiamo@k, tempi dell'embedding e VRAM.

Per ogni richiesta che richiede un tool: il tool atteso è nel nucleo fisso o tra i primi
k recuperati? Confronta bge-m3 e nomic-embed-text, descrizioni con e senza frasi
d'esempio, domanda da sola o con il turno prima (seguiti), GPU contro CPU.

Uso: .venv\\Scripts\\python.exe -u docs\\ricerche\\banchi\\ricerca_tool\\recupero.py
"""

import json
import os
import statistics
import subprocess
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.abspath(os.path.join(QUI, "..", "..", "..", "..")))   # radice del repository

import catalogo as K                                   # noqa: E402
from banco import Embedder, esiti_effettivi, query_di, HTTP, corpo   # noqa: E402
from richieste import RICHIESTE                        # noqa: E402

KS = [3, 5, 8, 12]


def vram():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.strip()
    return int(out), ps


def main():
    righe = []
    reqs = [r for r in RICHIESTE if esiti_effettivi(r, K.S40)[1] == "catalogo"]
    print(f"{len(reqs)} richieste con tool atteso")
    mib0, ps0 = vram()
    print(f"VRAM prima: {mib0} MiB\n{ps0}\n")
    for sigla in ("nomic", "bge"):
        for esempi in (False, True):
            emb = Embedder(sigla, esempi)
            mib, ps = vram()
            for contesto in (False, True):
                hit = {k: 0 for k in KS}
                hit_cat = 0
                tempi = []
                for r in reqs:
                    q = query_di(r) if contesto else r["testo"]
                    sc, dt = emb.punteggi(q)
                    tempi.append(dt * 1000)
                    ordinati = [n for _, n in sc if n not in K.NUCLEO]
                    for k in KS:
                        pool = set(K.NUCLEO) | set(ordinati[:k])
                        if any(all(n in pool for n, _ in e) for e in r["esiti"] if e):
                            hit[k] += 1
                    cats = []
                    for _, n in sc[:3]:
                        if K.BY_NAME[n]["cat"] not in cats:
                            cats.append(K.BY_NAME[n]["cat"])
                    pool = set(K.NUCLEO) | {t["name"] for t in K.TOOLS if t["cat"] in cats}
                    hit_cat += any(all(n in pool for n, _ in e) for e in r["esiti"] if e)
                riga = {"emb": emb.model, "esempi": esempi, "contesto": contesto,
                        **{f"r@{k}": round(hit[k] / len(reqs), 3) for k in KS},
                        "r_cat3": round(hit_cat / len(reqs), 3),
                        "ms_med": round(statistics.median(tempi), 1),
                        "ms_p90": round(sorted(tempi)[int(.9 * len(tempi))], 1),
                        "vram_mib": mib}
                righe.append(riga)
                print(json.dumps(riga, ensure_ascii=False), flush=True)
            print(ps, "\n")
    # Stessa cosa su CPU (num_gpu 0): costo senza VRAM
    for sigla in ("nomic", "bge"):
        HTTP.post("/api/generate", json={"model": Embedder.MODELLI[sigla], "keep_alive": 0})
        emb = Embedder(sigla, True, cpu=True)
        tempi = [emb.punteggi(r["testo"])[1] * 1000 for r in reqs[:40]]
        mib, ps = vram()
        riga = {"emb": emb.model + " (CPU)", "ms_med": round(statistics.median(tempi), 1),
                "ms_p90": round(sorted(tempi)[int(.9 * len(tempi))], 1), "vram_mib": mib}
        righe.append(riga)
        print(json.dumps(riga, ensure_ascii=False), "\n", ps, flush=True)
        HTTP.post("/api/generate", json={"model": Embedder.MODELLI[sigla], "keep_alive": 0})
    # l'LLM è ancora al suo posto?
    t = time.perf_counter()
    r = HTTP.post("/api/chat", json=corpo("gemma4:e4b-it-qat", [{"role": "user", "content": "ciao"}],
                                          stream=False, num_predict=1)).json()
    print(f"gemma4 dopo gli embedding: {time.perf_counter() - t:.2f}s, "
          f"load_duration {(r.get('load_duration') or 0) / 1e9:.2f}s")
    with open(os.path.join(QUI, "risultati", "recupero.jsonl"), "w", encoding="utf-8") as f:
        for riga in righe:
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
