"""
Tabelle riassuntive dei risultati del banco (ricerca_tool/risultati/*__*.jsonl).

Uso: .venv\\Scripts\\python.exe docs\\ricerche\\banchi\\ricerca_tool\\riassunto.py [filtro]  → markdown su stdout
"""

import glob
import json
import os
import re
import statistics
import sys
from collections import defaultdict

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.abspath(os.path.join(QUI, "..", "..", "..", "..")))   # radice del repository

import catalogo as K                          # noqa: E402
from banco import esiti_effettivi, punteggio  # noqa: E402
from richieste import RICHIESTE               # noqa: E402

# Richieste risolvibili già con 5 tool: il confronto «a parità di domande» tra 5/10/20/40
COMUNI = {i for i, r in enumerate(RICHIESTE) if esiti_effettivi(r, K.S5)[1] == "catalogo"}


def carica(filtro=""):
    dati = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(QUI, "risultati", "*__*.jsonl"))):
        if filtro and filtro not in f:
            continue
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            # punteggio ricalcolato con le regole attuali di banco.punteggio
            m = re.match(r"piatto(\d+)", r["strategia"])
            intero = K.SOTTOINSIEMI[int(m.group(1))] if m else K.S40
            r["chiamate"] = [tuple(c) for c in r["chiamate"]]
            r.update(punteggio(RICHIESTE[r["id"]], r, intero))
            dati[(r["modello"], os.path.basename(f).split("__")[1][:-6])].append(r)
    return dati


def pc(a, b):
    return f"{100 * a / b:.0f} %" if b else "—"


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def riga(chiave, rr):
    cat = [r for r in rr if r["gruppo"] == "catalogo"]
    senza = [r for r in rr if r["gruppo"] == "senza"]
    fuori = [r for r in rr if r["gruppo"] == "fuori"]
    com = [r for r in rr if r["id"] in COMUNI]
    f = lambda xs: f"{xs:.2f}" if xs is not None else "—"
    return (f"| {chiave[0]} | {chiave[1]} | {pc(sum(r['tool_ok'] for r in cat), len(cat))} "
            f"({sum(r['tool_ok'] for r in cat)}/{len(cat)}) | {pc(sum(r['args_ok'] for r in cat), len(cat))} "
            f"| {pc(sum(r['tool_ok'] for r in com), len(com))} "
            f"| {sum(r['classe'] == 'falso' for r in senza)}/{len(senza)} "
            f"| {sum(r['classe'] == 'falso' for r in fuori)}/{len(fuori)} "
            f"| {sum(r['classe'] == 'mancato' for r in cat)} "
            f"| {sum(r['da_testo'] for r in rr)} | {sum(r['fuga'] for r in rr)} "
            f"| {sum(1 for r in cat if not r['offerto'])} "
            f"| {f(q([r['t_decisione'] for r in rr], .5))} / {f(q([r['t_decisione'] for r in rr], .9))} "
            f"| {f(q([r['t_testo'] for r in rr], .5))} / {f(q([r['t_testo'] for r in rr], .9))} "
            f"| {f(q([r['t_testo'] for r in cat], .5))} / {f(q([r['t_testo'] for r in cat], .9))} "
            f"| {statistics.median([r['prompt_tok'] or 0 for r in rr]):.0f} "
            f"| {statistics.median([r['prompt_ms'] for r in rr]):.0f} "
            f"| {statistics.median([r['pre_ms'] for r in rr]):.0f} |")


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    dati = carica(filtro)
    print(f"Richieste comuni (risolvibili con 5 tool): {len(COMUNI)}\n")
    print("| modello | strategia | tool giusto (con tool atteso) | + argomenti | giusto sulle comuni "
          "| falsi senza tool | falsi fuori catalogo | mancati | scritte come testo | fughe al TTS "
          "| atteso non offerto | decisione s (med/p90) | primo testo s (med/p90) | primo testo con tool s | token prompt "
          "| prompt ms | pre ms |")
    print("|" + "---|" * 18)
    for k in dati:
        print(riga(k, dati[k]))
    # per tipo di richiesta
    tipi = sorted({r["tipo"] for rr in dati.values() for r in rr})
    print("\n**Tool giusto per tipo di richiesta** (tutte le richieste; «senza»/«assente» = nessun tool chiamato)\n")
    print("| modello | strategia | " + " | ".join(tipi) + " |")
    print("|" + "---|" * (len(tipi) + 2))
    for k, rr in dati.items():
        cells = []
        for t in tipi:
            xs = [r for r in rr if r["tipo"] == t]
            cells.append(f"{sum(r['tool_ok'] for r in xs)}/{len(xs)}")
        print(f"| {k[0]} | {k[1]} | " + " | ".join(cells) + " |")
    # errori, per capire
    if "--errori" in sys.argv:
        for k, rr in dati.items():
            print(f"\n### Errori {k[0]} · {k[1]}")
            for r in rr:
                if not r["args_ok"] or r["da_testo"] or r["fuga"]:
                    print(f"- [{r['classe']}{' T' if r['da_testo'] else ''}{' F' if r['fuga'] else ''}] "
                          f"«{r['testo']}» → {[(n, a) for n, a in r['chiamate']]} | {r['detto'][:90]!r}")


if __name__ == "__main__":
    main()
