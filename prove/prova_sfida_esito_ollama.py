"""L'esito dopo la frase di sfida col modello vero della voce (16/10/2026, issue #94): il
caso di `prova_sfida_esito.py` (registra_utente riuscito con `cosa_fare`, nomi di fantasia)
con il modello di Config() al posto del backend finto. Per un altro modello il profilo in
CALLIOPE_LLM_PROFILO (calliope/config.py, PROFILI_LLM).

Errore: la frase onesta «non ho salvato niente» (riconosciuta dall'atto `onesta` o dalla regola
`dichiarata_onesta`, non dal testo: dal 18/10, issue #28, ha varianti per tono e una forma per gli
ospiti), una rete delle azioni dichiarate scattata, il tool eseguito più di una volta. A parte (solo contato): quante risposte dicono che adesso deve parlare lei
(`cosa_fare` del risultato).

    python prove\\prova_sfida_esito_ollama.py       # 3 giri
    python prove\\prova_sfida_esito_ollama.py 1     # 1 giro
"""

import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_sfida_esito as P  # noqa: E402
from calliope.brain import make_backend  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
errori = parlare = 0
for giro in range(1, GIRI + 1):
    fatti = []
    b = P._brain([], P._registra(fatti))
    b.backend = make_backend(b.cfg)
    # La richiesta e la frase di sfida del turno prima, come sul vero
    b.history = [{"role": "user", "content": f"Registra {P.NOME} come familiare."},
                 {"role": "assistant", "content": "Per confermare ripeti: girasole, treno, "
                                                  "limone, quarantadue."}]
    t0 = time.perf_counter()
    detto = "".join(b.stream_reply(P.SFIDA_DETTA, "amministra")).strip()
    reti = [r for r in b.rules_fired() if r in P.RETI]
    # La frase onesta dall'atto o dalla regola, non dal testo (18/10, #28: le varianti)
    onesta = ("dichiarata_onesta" in b.rules_fired()
              or any(m[2] == "onesta" for m in b.__dict__.get("parlato_marcato") or ()))
    ok = fatti == [{"nome": P.NOME}] and bool(detto) and not onesta and not reti
    errori += not ok
    parlare += bool(re.search(r"\bparl", detto, re.I))
    print(f"{'ok ' if ok else 'ERR'} [{giro}] {time.perf_counter() - t0:.1f} s, tool "
          f"{len(fatti)}, reti {reti or '—'}: «{detto}»", flush=True)

print(f"\n{b.cfg.llm_model}: {GIRI - errori}/{GIRI} giusti; «deve parlare» detto {parlare}/{GIRI}")
# Il modello caricato esce dalla memoria (come prova_argomenti_ollama: il portatile ne ha poca)
if b.cfg.llm_backend == "ollama":
    try:
        subprocess.run(["ollama", "stop", b.cfg.llm_model], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
sys.exit(1 if errori else 0)
