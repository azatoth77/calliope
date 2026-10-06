"""
Cache del prefisso di Ollama con i tool che cambiano (ricerca del 26/09/2026).

Il renderer di gemma4 mette i tool nel turno di sistema, in testa al prompt: se l'elenco
cambia, tutto ciò che segue (storia compresa) si rivaluta. Qui si misura quanto costa,
al crescere della storia, e le alternative:
  A  tool fissi (un turno nuovo in coda)
  B  tool diversi a ogni turno (recupero top-k ingenuo)
  C  tool fissi + messaggio di sistema variabile in coda (dopo la storia)
  D  una chiamata «router» con un altro prompt tra un turno e l'altro (slot unico)

Uso: .venv\\Scripts\\python.exe -u docs\\ricerche\\banchi\\ricerca_tool\\cache.py [modello]
"""

import json
import os
import statistics
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.abspath(os.path.join(QUI, "..", "..", "..", "..")))   # radice del repository

import catalogo as K                         # noqa: E402
from banco import HTTP, corpo, SYSTEM, ROUTER_SYS, ROUTER_FMT   # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemma4:e4b-it-qat"
FRASI = ["Qual è la capitale della Francia?", "E quella della Spagna?", "Quanto dista la Luna?",
         "Perché il cielo è azzurro?", "Chi ha scritto I promessi sposi?",
         "Raccontami una curiosità sul mare.", "Dimmi tre città della Toscana."]
RISPOSTA = ("È una bella domanda. " + "Ti rispondo con qualche dettaglio in più su storia, "
            "geografia e curiosità, come faccio di solito quando la domanda lo merita. " * 3)


def storia(turni):
    h = []
    for i in range(turni):
        h += [{"role": "user", "content": FRASI[i % len(FRASI)] + f" (domanda {i})"},
              {"role": "assistant", "content": RISPOSTA}]
    return h


def chiama(messages, tools):
    t0 = time.perf_counter()
    r = HTTP.post("/api/chat", json=corpo(MODEL, messages, tools, stream=False, num_predict=1)).json()
    return {"tok": r.get("prompt_eval_count"), "eval_ms": round((r.get("prompt_eval_duration") or 0) / 1e6),
            "ms": round((time.perf_counter() - t0) * 1000)}


def main():
    fissi = K.schemas(K.S10)
    righe = []
    for turni in (0, 5, 15, 30):
        h = storia(turni)
        sys_ = [{"role": "system", "content": SYSTEM}]
        out = {"turni": turni}
        misure = {"A": [], "B": [], "C": [], "D": []}
        for rip in range(3):
            q1 = {"role": "user", "content": f"Che ore sono? ({rip})"}
            chiama(sys_ + h + [q1], fissi)                          # scalda il prefisso
            # A: tool fissi, domanda nuova
            misure["A"].append(chiama(sys_ + h + [{"role": "user", "content": f"Che giorno è? ({rip})"}], fissi))
            # B: tool diversi (5 del nucleo + 5 a rotazione)
            altri = K.S40[10 + rip * 5: 15 + rip * 5]
            misure["B"].append(chiama(sys_ + h + [{"role": "user", "content": f"Accendi la luce ({rip})"}],
                                      K.schemas(K.NUCLEO + altri)))
            # C: tool fissi, suggerimento variabile in coda
            chiama(sys_ + h + [q1], fissi)
            misure["C"].append(chiama(sys_ + h + [{"role": "system", "content": f"Tool utili ora: {', '.join(altri)}."},
                                                  {"role": "user", "content": f"Accendi la luce ({rip})"}], fissi))
            # D: router con un altro prompt, poi di nuovo la conversazione
            chiama(sys_ + h + [q1], fissi)
            HTTP.post("/api/chat", json=corpo(MODEL, [{"role": "system", "content": ROUTER_SYS},
                                                      {"role": "user", "content": f"Accendi la luce ({rip})"}],
                                              stream=False, fmt=ROUTER_FMT, num_predict=20))
            misure["D"].append(chiama(sys_ + h + [q1, {"role": "assistant", "content": "Sono le 9."},
                                                  {"role": "user", "content": f"Accendi la luce ({rip})"}], fissi))
        for k, v in misure.items():
            out[k + "_tok"] = v[0]["tok"]
            out[k + "_eval_ms"] = statistics.median(x["eval_ms"] for x in v)
            out[k + "_ms"] = statistics.median(x["ms"] for x in v)
        righe.append(out)
        print(json.dumps(out), flush=True)
    with open(os.path.join(QUI, "risultati", f"cache_{MODEL.replace(':', '_')}.jsonl"), "w",
              encoding="utf-8") as f:
        for r in righe:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
