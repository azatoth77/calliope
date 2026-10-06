"""Candidate di prompt finale, thinking spento, su piu richieste."""

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

P1 = ("Sei Calliope, un'assistente vocale che gira in locale sul computer "
      "dell'utente. Rispondi in italiano, calda e concisa, da una a tre frasi. Il "
      "testo verra letto ad alta voce: niente markdown, elenchi, emoji, codice o "
      "URL. Il genere di chi ti parla non e noto: usa formule neutre. Non hai "
      "accesso a internet, al meteo o ai file. Hai dei tool e li chiami tu, senza "
      "annunciarli: chi_parla per chi ti parla, ora_attuale per l'ora, data_oggi "
      "per la data, elenca_voci per le voci. Chiama il tool quando serve, poi "
      "rispondi con quello che ti ha dato.")

P2 = ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, calda e "
      "conciso, da una a tre frasi, senza markdown (il testo va letto ad alta "
      "voce). Il genere di chi ti parla non e noto. Hai dei tool e li chiami tu, "
      "senza annunciarli: chi_parla, ora_attuale, data_oggi, elenca_voci. Chiama il "
      "tool quando serve, poi rispondi.")

P3 = ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, da una a tre "
      "frasi, senza markdown (va letto ad alta voce). Per l'ora chiama ora_attuale, "
      "per la data data_oggi, per chi parla chi_parla, per le voci elenca_voci. "
      "Chiama il tool, non annunciarlo, poi rispondi.")

domande = ["Che ore sono?", "Che giorno e oggi?", "Chi ti sta parlando?",
           "Che voci hai?", "Raccontami una barzelletta."]


def chat(system, frase):
    body = {"model": cfg.llm_model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": frase}],
            "tools": tools,
            "options": {"num_ctx": finestra(cfg), "temperature": cfg.llm_temperature},
            "think": False, "stream": False}
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


for nome, sysp in (("P1", P1), ("P2", P2), ("P3", P3)):
    for frase in domande:
        out = chat(sysp, frase)
        m = out["message"]
        nomi = [t["function"]["name"] for t in (m.get("tool_calls") or [])]
        print(f"[{nome}] «{frase}» → tool: {nomi or '—'}  "
              f"testo: {(m.get('content') or '').strip()!r}")
    print()
