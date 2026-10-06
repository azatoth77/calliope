"""
L'ufficio da terminale.

    python -m calliope.ufficio --modelli               # i modelli che ci sono e i loro avvisi
    python -m calliope.ufficio --scarica-xsd           # lo schema ufficiale di FatturaPA
    python -m calliope.ufficio --valida FILE.xml       # una fattura contro lo schema
    python -m calliope.ufficio --numeri [SERIE] [--anno 2026]
    python -m calliope.ufficio --annulla fatture 2026 12 --nota "mai inviata: dati sbagliati"
    python -m calliope.ufficio --rubrica               # i contatti (solo nomi e città)
"""

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="python -m calliope.ufficio",
                                 description="Modelli, numerazione e fatture di Calliope")
    ap.add_argument("--modelli", action="store_true")
    ap.add_argument("--scarica-xsd", action="store_true")
    ap.add_argument("--valida", metavar="FILE")
    ap.add_argument("--numeri", nargs="?", const="", metavar="SERIE")
    ap.add_argument("--anno", type=int)
    ap.add_argument("--annulla", nargs=3, metavar=("SERIE", "ANNO", "NUMERO"))
    ap.add_argument("--nota", default="")
    ap.add_argument("--rubrica", action="store_true")
    a = ap.parse_args(argv)
    from ..config import load_config
    cfg = load_config()
    from . import cartella_modelli
    from .fatturapa import cartella_xsd, scarica_xsd, valida_xsd, xsd_presente
    db = cfg.memory_db or "memoria.db"
    if a.scarica_xsd:
        return 0 if scarica_xsd(cartella_xsd(cfg)) else 1
    if a.valida:
        if not xsd_presente(cartella_xsd(cfg)):
            print(f"Lo schema non c'è in {cartella_xsd(cfg)}: python -m calliope.ufficio "
                  f"--scarica-xsd")
            return 1
        err = valida_xsd(Path(a.valida).read_bytes(), cartella_xsd(cfg))
        print("valido" if not err else "\n".join(err))
        return 0 if not err else 1
    if a.modelli:
        from .modelli import carica, librerie
        cat, errori = carica(cartella_modelli(cfg))
        lib = librerie()
        print(f"Cartella dei modelli: {cartella_modelli(cfg)}")
        for m in cat.values():
            manca = m.tipo in ("docx", "pptx") and not lib.get(m.tipo)
            print(f"- {m.nome} ({m.tipo}, uscita {m.uscita}"
                  + (f", serie {m.serie}" if m.serie else "") + ")"
                  + ("  [manca la libreria]" if manca else ""))
            print(f"    campi: {m.descrivi_campi()}")
            for av in m.avvisi:
                print(f"    avviso: {av}")
        for e in errori:
            print(f"! {e}")
        return 0
    if a.numeri is not None or a.annulla:
        from .numerazione import NumerazioneError, Numeratore
        num = Numeratore(db, getattr(cfg, "ufficio_serie", None) or {})
        if a.annulla:
            serie, anno, numero = a.annulla[0], int(a.annulla[1]), int(a.annulla[2])
            try:
                num.annulla(serie, anno, numero, a.nota)
            except NumerazioneError as e:
                print(f"Non annullato: {e}.")
                return 1
            print(f"Annullato {num.testo(serie, numero, anno)}: {a.nota}")
            return 0
        for d in num.elenco(a.numeri or None, a.anno):
            stato = {"emesso": "", "annullato": f"  ANNULLATO ({d['nota']})"}.get(
                d["stato"], "  IN PREPARAZIONE")
            print(f"{d['serie']:13} {d['testo']:14} {d['data']}  {d['titolo'] or ''}  "
                  f"{d['chi'] or ''}{stato}")
        return 0
    if a.rubrica:
        from .rubrica import Rubrica
        r = Rubrica(db)
        for c in r._rows():
            print(f"{c['id']:4}  {c['nome_completo']}  {c.get('comune', '')}  "
                  f"({c.get('tipo', '')}, {'casa' if c['ambito'] == 'casa' else 'personale'})")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
