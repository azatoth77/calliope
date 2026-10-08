import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il suggerimento dopo un esito vuoto con il modello vero (08/10/2026, F1 di
docs/ricerche/2026-10-08-parole-incerte.md). Manuale, non nel runner: serve l'Ollama di questo
PC (gemma4 e4b di calliope.yaml, o `--modello`). Mai l'Ollama della DGX.

L'estensione «Meteo città» è finta (trova solo le città di prove/prova_argomenti_incerti.py), il
resto dei tool è vero. Per ogni giro, con il suggerimento acceso e spento:

- **forse**: «Pradello Dugnasco» è un nome noto; la persona dice «Patello Giugnasco» (Whisper
  incerto), l'estensione non trova niente. Si conta se la risposta chiede «intendevi Pradello
  Dugnasco?» (domanda finale, proposta in sospeso) e se il «Sì.» del turno dopo richiama
  l'estensione con il nome giusto;
- **ripeti**: «Rocca Barba», nessun nome noto vicino, Whisper incerto: la risposta chiede di
  ripeterlo o scriverlo, senza inventare un nome;
- **pieno** (contrario): «Pradello Dugnasco» trovato: nessun «intendevi».

    python prove\\misura_argomenti_forse.py [giri] [--modello NOME]
"""

import re
import time

from calliope import argomenti_incerti as ai
from calliope.brain import make_backend
from prove.prova_argomenti_incerti import P_PATELLO, prepara_brain, parla
from prove.prova_politica import ChiParla

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
MODELLO = sys.argv[sys.argv.index("--modello") + 1] if "--modello" in sys.argv else None
DESCRIZIONE = ("L'estensione «Meteo città»: il meteo di oggi in una città o un paese italiano. "
               "citta: il nome come detto.")


def brain(forse: bool):
    b, eseguiti = prepara_brain()
    if MODELLO:
        b.cfg.llm_model = MODELLO
    b.backend = make_backend(b.cfg)
    import dataclasses
    for n in ("est_meteo_citta",):
        b.tools.register(dataclasses.replace(b.tools.get(n), description=DESCRIZIONE))
    b.tools.unregister("est_prenota")
    if not forse:
        b.cfg.llm_reti_spente = ["argomento_forse"]
    b.tool_ctx.speaker_ctx = ChiParla(name="Dario", level="amministra")
    return b, eseguiti


def giro(n: int, forse: bool) -> dict:
    out = {}
    # forse
    b, eseguiti = brain(forse)
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    t0 = time.perf_counter()
    r, reg, _ = parla(b, "Calliope, che tempo fa a Patello Giugnasco? Usa Meteo città.",
                      parole=[("che", 0.97), ("tempo", 0.99), ("fa", 0.98), ("a", 0.9)]
                      + P_PATELLO[3:])
    s1 = time.perf_counter() - t0
    chiamato = any(e[0] == "est_meteo_citta" for e in eseguiti)
    nomina = "pradello" in r.lower()
    chiede = r.rstrip().endswith("?") and nomina
    pending = (b.pending or {}).get("args") == {"citta": "Pradello Dugnasco"}
    k = len(eseguiti)
    r2, _, _ = parla(b, "Sì.", parole=[("Sì", 0.95)]) if nomina else ("", [], None)
    richiama = eseguiti[k:] and eseguiti[k:][0] == ("est_meteo_citta",
                                                    {"citta": "Pradello Dugnasco"})
    print(f"   [{n} forse {'on' if forse else 'off'}] {s1:.1f}s → {r!r}"
          + (f" | sì → {r2!r} {eseguiti[k:]}" if nomina else ""), flush=True)
    out["forse"] = dict(chiamato=chiamato, nomina=nomina, chiede=chiede, pending=pending,
                        richiama=bool(richiama), regole=b.rules_fired(), s=s1)
    # ripeti
    b, eseguiti = brain(forse)
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    r, _, _ = parla(b, "Calliope, che tempo fa a Rocca Barba? Usa Meteo città.",
                    parole=[("che", 0.97), ("tempo", 0.99), ("fa", 0.98), ("a", 0.9),
                            ("Rocca", 0.33), ("Barba", 0.62)])
    ripeti = bool(re.search(r"ripet|scriv|ridir|di nuovo|rimand|come si (scrive|chiama)",
                            r, re.I))
    inventa = bool(re.search(r"intendevi|forse (?:intendi|volevi)", r, re.I))
    print(f"   [{n} ripeti {'on' if forse else 'off'}] → {r!r}", flush=True)
    out["ripeti"] = dict(chiamato=any(e[0] == "est_meteo_citta" for e in eseguiti),
                         ripeti=ripeti, inventa=inventa)
    # pieno
    b, eseguiti = brain(forse)
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    r, _, _ = parla(b, "Calliope, che tempo fa a Pradello Dugnasco? Usa Meteo città.",
                    parole=[("che", 0.97), ("tempo", 0.99), ("fa", 0.98), ("a", 0.9),
                            ("Pradello", 0.9), ("Dugnasco", 0.9)])
    print(f"   [{n} pieno {'on' if forse else 'off'}] → {r!r}", flush=True)
    out["pieno"] = dict(chiamato=any(e[0] == "est_meteo_citta" for e in eseguiti),
                        intendevi=bool(re.search(r"intendevi", r, re.I)))
    return out


def main():
    tot = {}
    for forse in (True, False):
        righe = [giro(n + 1, forse) for n in range(GIRI)]
        f = [x["forse"] for x in righe if x["forse"]["chiamato"]]
        rp = [x["ripeti"] for x in righe if x["ripeti"]["chiamato"]]
        pi = [x["pieno"] for x in righe if x["pieno"]["chiamato"]]
        tot[forse] = (
            f"suggerimento {'acceso' if forse else 'spento'}: forse {len(f)} chiamate, "
            f"nomina Pradello Dugnasco {sum(x['nomina'] for x in f)}, "
            f"«intendevi Pradello Dugnasco?» {sum(x['chiede'] for x in f)}, proposta "
            f"{sum(x['pending'] for x in f)}, «sì» → richiamata giusta "
            f"{sum(x['richiama'] for x in f)}; ripeti {len(rp)} chiamate, chiede di ripetere o "
            f"scrivere {sum(x['ripeti'] for x in rp)}, «intendevi» inventato "
            f"{sum(x['inventa'] for x in rp)}; pieno {len(pi)} chiamate, «intendevi» "
            f"{sum(x['intendevi'] for x in pi)}")
    print()
    for v in tot.values():
        print(v)


if __name__ == "__main__":
    main()
