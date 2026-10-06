import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "ricerche",
                                "banchi", "ricerca_tool"))

"""Molti tool con un LLM piccolo: rifà in breve le misure di docs/ricerche/banchi/ricerca_tool/ (26/09/2026).

Fa girare il banco (40 tool finti, 119 richieste vocali in italiano) con le strategie
indicate e stampa la tabella riassuntiva. Serve Ollama; usa num_ctx 16384 come Calliope,
quindi non provoca ricaricamenti del modello vocale.

Uso: prova_tool_scala.py [modello] [strategie] [limite]
  modello    predefinito gemma4:e4b-it-qat
  strategie  predefinite piatto10,piatto40,rag-bge-k5 (vedi docs/ricerche/banchi/ricerca_tool/banco.py)
  limite     numero di richieste (0 = tutte)
Rapporto: docs/ricerche/2026-09-26-tool-e-agenti.md
"""

import subprocess

modello = sys.argv[1] if len(sys.argv) > 1 else "gemma4:e4b-it-qat"
strategie = sys.argv[2] if len(sys.argv) > 2 else "piatto10,piatto40,rag-bge-k5"
limite = sys.argv[3] if len(sys.argv) > 3 else "0"
radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
banco = os.path.join(radice, "docs", "ricerche", "banchi", "ricerca_tool")
py = sys.executable
subprocess.run([py, "-u", os.path.join(banco, "banco.py"), "--modello", modello,
                "--strategie", strategie, "--limite", limite, "--etichetta", "_prova"], check=True)
subprocess.run([py, os.path.join(banco, "riassunto.py"), "_prova"], check=True)
