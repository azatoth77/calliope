"""
Di che forma sono le chiamate «scritte come testo»? (26/09/2026)

Riprende le richieste che con piatto40 sono passate da TextCallGuard e ne registra il
contenuto grezzo del primo turno: formato nativo di gemma non riconosciuto dal parser di
Ollama («call:nome{…}», «<|tool_call>…») oppure scelta del modello («nome()», nome nudo).
Prova anche la temperatura 0 e un'istruzione in più nel prompt.

Uso: .venv\\Scripts\\python.exe -u docs\\ricerche\\banchi\\ricerca_tool\\sonda_testo.py [modello]
"""

import collections
import json
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.abspath(os.path.join(QUI, "..", "..", "..", "..")))   # radice del repository

import catalogo as K                                  # noqa: E402
import banco                                          # noqa: E402
from richieste import RICHIESTE                       # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemma4:e4b-it-qat"


def forma(raw: str) -> str:
    s = raw.strip()
    if "<|tool_call" in s or "<|" in s[:20]:
        return "token speciali gemma"
    if re.match(r"call:\w+\{", s):
        return "call:nome{…} (nativo gemma)"
    if re.match(r"\w+\(", s):
        return "nome(…)"
    if re.match(r"\w+\{", s):
        return "nome{…}"
    if re.match(r"\w+_\w+", s):
        return "nome nudo"
    return "altro: " + s[:30]


def prova(system, temp, ids):
    conta = collections.Counter()
    nativi = 0
    esempi = []
    for i in ids:
        req = RICHIESTE[i]
        msgs = [{"role": "system", "content": system}] + req["storia"] + [{"role": "user", "content": req["testo"]}]
        body = banco.corpo(MODEL, msgs, K.schemas(K.S40), stream=False, num_predict=80)
        body["options"]["temperature"] = temp
        d = banco.HTTP.post("/api/chat", json=body).json()
        m = d.get("message") or {}
        if m.get("tool_calls"):
            nativi += 1
            continue
        raw = m.get("content") or ""
        f = forma(raw)
        conta[f] += 1
        if len(esempi) < 6 and not f.startswith("altro"):
            esempi.append(raw[:90])
    return nativi, conta, esempi


def main():
    f = os.path.join(QUI, "risultati", f"{MODEL.replace(':', '_')}__piatto40.jsonl")
    righe = [json.loads(x) for x in open(f, encoding="utf-8")]
    ids = [r["id"] for r in righe if r["da_testo"]]
    tutti_tool = [r["id"] for r in righe if r["chiamate"]]
    print(f"{len(ids)} richieste passate dalla guardia su {len(tutti_tool)} con tool\n")
    extra = (" Per usare un tool emetti sempre una chiamata di funzione vera, mai il suo nome "
             "scritto nel testo.")
    for nome, system, temp in [("prompt del banco, T 0,3", banco.SYSTEM, 0.3),
                               ("prompt del banco, T 0", banco.SYSTEM, 0.0),
                               ("+ istruzione sulle chiamate, T 0,3", banco.SYSTEM + extra, 0.3)]:
        nativi, conta, esempi = prova(system, temp, tutti_tool)
        print(f"### {nome}: chiamate native {nativi}/{len(tutti_tool)}; nel testo: {dict(conta)}")
        for e in esempi:
            print("   ", repr(e))


if __name__ == "__main__":
    main()
