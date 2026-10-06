import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Brain vero contro Ollama, con un contesto finto: tool chiamati, testo detto e
tempo al primo testo. Uso: prova_brain_ollama.py [giri] [backend]"""

import subprocess
import time

from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext


class FakeSpeakers:
    def known_speakers(self):
        return []

    def get(self, n):
        return None

    def save(self):
        pass


class FakeCtx:
    current_speaker = None
    current_level = "ospite"
    enroll_needed = 3

    def start_enroll(self, n):
        pass


class FakeSpeaker:
    def change_voice(self, p):
        return True


DOMANDE = [("ospite", "Che ore sono?"), ("ospite", "Che giorno è oggi?"),
           ("ospite", "Chi ti sta parlando?"), ("ospite", "Che voci hai?"),
           ("ospite", "Raccontami una barzelletta."), ("familiare", "Cambia voce in paola.")]

giri = int(sys.argv[1]) if len(sys.argv) > 1 else 2
cfg = Config()
if len(sys.argv) > 2:
    cfg.llm_backend = sys.argv[2]
reg = build_registry()
chiamati = []
chiama = reg.call
reg.call = lambda nome, args, ctx, level=None: (chiamati.append(nome),
                                                chiama(nome, args, ctx, level))[1]
ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx(),
                  speaker=FakeSpeaker())
brain = Brain(cfg, reg, ctx)
t = time.perf_counter()
brain.warmup()
print(f"backend {cfg.llm_backend}, warmup {time.perf_counter() - t:.2f}s")

for g in range(giri):
    print(f"\n=== giro {g + 1} ===")
    for livello, frase in DOMANDE:
        brain.history = []
        chiamati.clear()
        t0 = time.perf_counter()
        primo, pezzi = None, []
        for pezzo in brain.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            pezzi.append(pezzo)
        tot = time.perf_counter() - t0
        primo_s = f"{primo:.2f}s" if primo is not None else "—"
        print(f"RIGA\t{livello}\t{frase}\t{','.join(chiamati) or '—'}\t{primo_s}\t{tot:.2f}s\t"
              f"{''.join(pezzi).strip()!r}")

print()
print(subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout)
