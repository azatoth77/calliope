import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Tool `calcola` con il Brain vero contro Ollama: domande di conti come a voce.

Conta se il modello chiama `calcola` (anche come testo salvato dalla guardia) e se
nella risposta detta c'è il risultato giusto. Ogni domanda in una sessione nuova.
"""

import re
import time

from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext


class SpeakerCtx:
    current_speaker, current_level = "Dario", "amministra"


class Speakers:
    def get(self, n):
        return None


DOMANDE = [
    ("Quanto fa 300 miliardi per 2748?", ["824,4 mila miliardi", "824.400", "824400", "824 mila"]),
    ("Quanto fa diciassette per sei?", ["102", "centodue"]),
    ("Quant'è il 15 per cento di 80?", ["12", "dodici"]),
    ("Qual è la radice quadrata di 144?", ["12", "dodici"]),
    ("Quanto fa 1234 diviso 7?", ["176,28", "176.28", "176,2", "176"]),
    ("Se ho 3 moli di ossigeno e ogni mole pesa 32 grammi, quanti grammi sono?", ["96", "novantasei"]),
    ("Quanto fa 2 alla decima?", ["1024", "1.024", "milleventiquattro"]),
    ("Qual è la capitale della Francia?", None),          # nessun conto
]

cfg = Config()
ok_tool = ok_res = 0
for giro in (1, 2):
    for domanda, attesi in DOMANDE:
        ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(), speaker=None)
        b = Brain(cfg, build_registry(), ctx)
        t0 = time.perf_counter()
        risposta = "".join(b.stream_reply(domanda, "amministra")).strip()
        dt = time.perf_counter() - t0
        tools = [t["nome"] + ("*" if t["da_testo"] else "") for t in b.last_tools]
        if attesi is None:
            giusto = "calcola" not in " ".join(tools)
            ok_tool += giusto
            ok_res += giusto
        else:
            chiamato = any(t.startswith("calcola") for t in tools)
            giusto = any(a in risposta.replace(" ", " ") for a in attesi)
            ok_tool += chiamato
            ok_res += giusto
        print(f"[{giro}] {'ok ' if giusto else 'ERR'} {dt:4.1f}s «{domanda}» → {tools or '—'} | {risposta[:100]!r}")
n = 2 * len(DOMANDE)
print(f"\nTool giusto {ok_tool}/{n}, risultato detto giusto {ok_res}/{n}")
