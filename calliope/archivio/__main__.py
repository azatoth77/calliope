"""
L'archivio dei documenti di casa da terminale (03/10/2026):

    python -m calliope.archivio                    # stato: documenti, file, errori
    python -m calliope.archivio --giro             # legge subito i file nuovi (serve il modello)
    python -m calliope.archivio --riprocessa       # rilegge tutto al prossimo giro (e lo fa)
    python -m calliope.archivio --nodi ente        # i nodi di un tipo, con l'id
    python -m calliope.archivio --unisci 12 31     # 31 è la stessa entità di 12: la unisce

Con Calliope accesa il giro lo fa già lei ogni archivio_intervallo_min minuti; questo comando
apre lo stesso database (SQLite in WAL: si può usare insieme).
"""

import argparse
import sys

from ..config import load_config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m calliope.archivio")
    ap.add_argument("--giro", action="store_true", help="legge subito i file nuovi o cambiati")
    ap.add_argument("--riprocessa", action="store_true", help="rilegge tutti i documenti")
    ap.add_argument("--nodi", metavar="TIPO", help="elenca i nodi di un tipo")
    ap.add_argument("--unisci", nargs=2, type=int, metavar=("TENERE", "TOGLIERE"))
    a = ap.parse_args(argv)
    cfg = load_config()
    from . import load_archivio
    svc = load_archivio(cfg, avvia=False)
    if svc is None:
        from .. import capacita
        r = capacita.check_archivio(cfg)
        print(f"Archivio: {r['motivo']}. {r['prossimo_passo']}")
        return 1
    try:
        if a.unisci:
            ok = svc.grafo.unisci(*a.unisci)
            print("Uniti." if ok else "Non si possono unire (tipi diversi o id sbagliati).")
            return 0 if ok else 1
        if a.nodi:
            for r in svc.grafo.leggi("SELECT id, nome, data, valore FROM nodi WHERE tipo = ? "
                                     "ORDER BY nome", (a.nodi,)):
                extra = " ".join(str(x) for x in (r["data"], r["valore"]) if x is not None)
                print(f"{r['id']:6}  {r['nome']}" + (f"  ({extra})" if extra else ""))
            return 0
        if a.riprocessa:
            print(f"Da rileggere: {svc.riprocessa()} file.")
        if a.giro or a.riprocessa:
            if svc.estrattore is None:
                print("Manca il modello grande (agenti o archivio_url): non leggo i file nuovi.")
                return 1
            g = svc.giro()
            print(f"Letti {g['fatti']}, errori {g['errori']}, tolti {g['tolti']} "
                  f"({g['secondi']} s).")
        st = svc.stato()
        print(f"Cartella: {st['cartella']}")
        print(f"Documenti: {st['documenti']}; file: "
              + (", ".join(f"{k} {v}" for k, v in st["file"].items()) or "nessuno"))
        for r in svc.grafo.leggi("SELECT percorso, errore FROM file WHERE stato != 'ok' "
                                 "ORDER BY percorso LIMIT 20"):
            print(f"   {r['percorso']}: {r['errore']}")
        c = svc.grafo.conteggi()
        print("Nodi: " + ", ".join(f"{k} {v}" for k, v in sorted(c["nodi"].items())))
        print("Archi: " + ", ".join(f"{k} {v}" for k, v in sorted(c["archi"].items())))
        return 0
    finally:
        svc.close()
        svc.grafo.close()


if __name__ == "__main__":
    sys.exit(main())
