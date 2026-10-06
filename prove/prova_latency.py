"""Misura latenza e affidabilita: thinking acceso vs spento."""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import urllib.request

from calliope.config import Config
from calliope.contesto import finestra
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
URL = "http://127.0.0.1:11434/api/chat"

LUNGO = cfg.system_prompt
CORTO = ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, da una a tre "
         "frasi, senza markdown (va letto ad alta voce). Per l'ora chiama ora_attuale, "
         "per la data data_oggi, per chi parla chi_parla, per le voci elenca_voci. "
         "Chiama il tool, non annunciarlo, poi rispondi.")

domande = ["Che ore sono?", "Che giorno e oggi?", "Chi ti sta parlando?",
           "Che voci hai?", "Raccontami una barzelletta."]


def prova(nome, system, frase, think):
    body = {"model": cfg.llm_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": frase}],
            "tools": tools,
            "options": {"num_ctx": finestra(cfg),
                        "temperature": cfg.llm_temperature},
            "stream": True}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    primo, calls, testo = None, [], ""
    with urllib.request.urlopen(req, timeout=180) as r:
        for line in r:
            obj = json.loads(line)
            m = obj.get("message", {})
            for t in (m.get("tool_calls") or []):
                calls.append(t["function"]["name"])
            if m.get("content"):
                testo += m["content"]
                if primo is None:
                    primo = time.perf_counter() - t0
            if obj.get("done"):
                break
    tot = time.perf_counter() - t0
    primo_s = f"{primo:.2f}s" if primo is not None else "—"
    print(f"[{nome}] «{frase}» → tool: {calls or '—'}  "
          f"primo testo: {primo_s}  totale: {tot:.2f}s  "
          f"testo: {testo.strip()[:60]!r}")


print("=== thinking SPENTO, prompt corto ===")
for d in domande:
    prova("corto/spento", CORTO, d, False)

print("\n=== thinking ACCESO, prompt corto ===")
for d in domande:
    prova("corto/acceso", CORTO, d, True)

print("\n=== thinking ACCESO, prompt lungo ===")
for d in domande:
    prova("lungo/acceso", LUNGO, d, True)
