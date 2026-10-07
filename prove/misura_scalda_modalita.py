import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Misura: la lettura del prompt del turno dopo un cambio di modalità (o del tono della casa),
con e senza il riscaldamento del prefisso nuovo in secondo piano (Brain._scalda_se_cambiato,
07/10). Ollama locale con il modello della voce; una conversazione di qualche turno davanti.

Caso vero della DGX del 07/10: dopo «attiva la modalità Star Trek» il turno dopo («Computer,
che ore sono?») ha avuto prima frase 7,14 s con lettura 5,93 s: il tono della casa sta nel
prompt di sistema, che cambia, e Ollama rileggeva ~15k token.

Per ogni giro: un turno per mettere in cache la conversazione, poi il cambio di modalità
(startrek ↔ normale, come fa cambia_voce), poi «Che ore sono?» e la sua lettura (lettura_s):
  - senza: subito;
  - con: prima il riscaldamento (il thread di Brain, aspettato come la conferma detta).

    python prove\\misura_scalda_modalita.py        # 3 giri
"""

import time

from calliope.brain import Brain
from calliope.config import Config, cambia_modalita
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3


class SpeakerCtx:
    current_speaker, current_level, from_session, identified_by = None, "ospite", False, "voce"


STORIA = []
for i in range(12):
    STORIA += [{"role": "user", "content": f"Raccontami qualcosa sul tema numero {i}: la storia "
                                           f"di una città italiana a scelta, in breve."},
               {"role": "assistant", "content": ("Firenze nacque come colonia romana e divenne "
                                                 "nel Rinascimento il centro delle arti e dei "
                                                 "commerci, con i Medici. ") * 6}]


def turno(b, frase):
    t0 = time.perf_counter()
    primo = None
    for pezzo in b.stream_reply(frase, "ospite"):
        if primo is None and pezzo.strip():
            primo = time.perf_counter() - t0
    return primo or 0.0, b.last_lettura_s or 0.0


cfg = Config()
reg = build_registry()
ctx = ToolContext(cfg=cfg, speakers=None, speaker_ctx=SpeakerCtx(), speaker=None)
b = Brain(cfg, reg, ctx)
b.history = [dict(m) for m in STORIA]
b.last_turn_at = time.monotonic()
righe = {"senza": [], "con": []}
modi = ["startrek", "normale"]
for giro in range(GIRI):
    for come in ("senza", "con"):
        # Una conversazione mai vista (altrimenti il prefisso di un giro prima è ancora in
        # cache in un altro slot di Ollama e la misura non dice niente)
        b.history = [{"role": "user", "content": f"[{time.time():.6f}] Ciao."},
                     {"role": "assistant", "content": "Ciao!"}] + [dict(m) for m in STORIA]
        turno(b, "Grazie, e quanto fa due per tre?")          # conversazione in cache
        firma = b._firma_sistema()
        cambia_modalita(cfg, modi[0])
        modi.reverse()
        if come == "con":
            b._scalda_se_cambiato(firma)
            b.scalda_thread.join()
        primo, lettura = turno(b, "Che ore sono?")
        righe[come].append((primo, lettura))
        print(f"[{giro + 1}] {come:5} riscaldamento: prima frase {primo:.2f} s, lettura "
              f"{lettura:.2f} s", flush=True)
for come, rr in righe.items():
    rr = sorted(rr, key=lambda r: r[1])
    print(f"{come}: lettura mediana {rr[len(rr) // 2][1]:.2f} s, prima frase mediana "
          f"{sorted(r[0] for r in rr)[len(rr) // 2]:.2f} s")
