"""Prompt corti con thinking SPENTO: la chiamata dei tool regge?"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import urllib.request

from calliope.config import Config
from calliope.contesto import finestra
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
URL = "http://127.0.0.1:11434/api/chat"

varianti = {
    "H-corto": ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, calda "
                "e concisa, da una a tre frasi. Niente markdown: il testo va letto ad "
                "alta voce. Hai dei tool e li chiami tu, senza annunciarli: chi_parla "
                "per chi ti parla, ora_attuale per l'ora, data_oggi per la data."),
    "I-corto": ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, da una "
                "a tre frasi, senza markdown (va letto ad alta voce). Per l'ora chiama "
                "ora_attuale, per la data data_oggi, per chi parla chi_parla. Chiama il "
                "tool, non annunciarlo."),
    "G-minimo": ("Sei un assistente vocale. Hai alcuni tool: usali quando servono davvero, "
                 "senza annunciarli. Per sapere l'ora chiama il tool ora_attuale."),
}


def chat(system, frase, think):
    body = {"model": cfg.llm_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": frase}],
            "tools": tools,
            "options": {"num_ctx": finestra(cfg), "temperature": cfg.llm_temperature},
            "stream": False}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


for nome, sysp in varianti.items():
    for frase in ("Che ore sono?", "Chi ti sta parlando?"):
        out = chat(sysp, frase, False)
        m = out["message"]
        nomi = [t["function"]["name"] for t in (m.get("tool_calls") or [])]
        print(f"[{nome}] «{frase}» → tool: {nomi or '—'}  "
              f"testo: {(m.get('content') or '').strip()!r}")
    print()
