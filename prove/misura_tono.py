import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Misura (04/10): il tono di voce abbassa le chiamate dei tool? Serve Ollama locale.

Lancia una prova con il modello (prova_stato_ollama.py, prova_casa.py…) con un tono messo
in uno dei due posti possibili:

    casa     → nel prompt di sistema (Config.tono, come il tono della casa)
    persona  → nei dati del turno, prima della domanda (Brain._tone_note, come il tono
               scelto da una persona), solo per chi è riconosciuto

    python prove\\misura_tono.py casa computer_di_bordo prova_stato_ollama.py 1
    python prove\\misura_tono.py persona ironico prova_casa.py 1
    python prove\\misura_tono.py nessuno normale prova_casa.py 1      # il riferimento

Con --campioni al posto della prova stampa le risposte a qualche domanda senza tool
(stile, lunghezza, niente markdown):

    python prove\\misura_tono.py casa ironico --campioni
"""

import runpy
import time

from calliope import brain as B
from calliope import config as C

modo, tono, prova = sys.argv[1], sys.argv[2], sys.argv[3]
resto = sys.argv[4:]

if modo == "casa":
    _post = C.Config.__post_init__

    def post(self):
        _post(self)
        self.tono = tono
    C.Config.__post_init__ = post
elif modo == "persona":
    def tone_note(self, name):
        self._rule("tono_persona")
        return C.frase_tono(tono)
    B.Brain._tone_note = tone_note
elif modo != "nessuno":
    sys.exit("modo: casa, persona o nessuno")

if prova != "--campioni":
    sys.argv = [prova] + resto
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), prova),
                   run_name="__main__")
    sys.exit(0)

# ── campioni di risposte ──
import types  # noqa: E402

from calliope.speaker_id import UserProfile  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402

DOMANDE = ["Ciao, come stai?", "Raccontami una barzelletta.", "Cos'è un buco nero?",
           "Mi consigli un film per stasera?", "Grazie per l'aiuto di prima."]


class Registro:
    def get(self, n):
        return UserProfile(n)


cfg = C.Config()
ctx = types.SimpleNamespace(speakers=Registro(), speaker_ctx=types.SimpleNamespace(
    current_speaker="Dario", identified_by="voce"))
for d in DOMANDE:
    br = B.Brain(cfg, ToolRegistry(), ctx)
    t0 = time.perf_counter()
    testo = "".join(br.stream_reply(d, "familiare"))
    print(f"[{modo}/{tono}] {d}\n    → {testo.strip()}  ({time.perf_counter() - t0:.2f} s, "
          f"{len(testo.split())} parole)", flush=True)
