"""
L'ufficio di casa (03/10/2026): modelli di documento compilati a voce, rubrica dei clienti,
numerazione progressiva, fatture elettroniche (PDF di cortesia + XML FatturaPA) e DDT.

- modelli.py: i modelli pronti e quelli dell'utente (Word con docxtpl, PowerPoint con
  python-pptx, JSON del formato dei documenti);
- rubrica.py: clienti, fornitori e contatti in SQLite, con i controlli di partita IVA e
  codice fiscale;
- numerazione.py: numeri per serie e anno, atomici e senza buchi, annullabili con una nota;
- conti.py: imponibile, IVA per aliquota, ritenuta, cassa, bollo (Decimal, mai il modello);
- fatturapa.py: l'XML FPR12 e la validazione con l'XSD ufficiale, se c'è;
- stampe.py: le stampe in PDF (copia di cortesia, preventivo, DDT);
- servizio.py: il flusso a voce (estrazione dei campi, domande, proposta, emissione).
I tool sono in calliope/tools/ufficio.py. Calliope non trasmette niente allo SdI.
"""

from pathlib import Path

from .servizio import Ufficio, scrittore_agenti, scrittore_locale

__all__ = ["Ufficio", "cartella_modelli", "load_ufficio"]


def cartella_modelli(cfg) -> Path:
    folder = getattr(cfg, "ufficio_modelli", None) or getattr(cfg, "agenti_modelli", None)
    if folder:
        return Path(folder)
    from ..documenti.consegna import default_folder
    return default_folder() / "Modelli"


def load_ufficio(cfg, db_path: str, documenti, lavori=None) -> Ufficio | None:
    """Il servizio, o None se è spento o mancano i documenti. Segnala la capacità «ufficio»
    con cosa funziona (modelli, XSD, emittente) e cosa manca."""
    from .. import capacita
    if not getattr(cfg, "ufficio_enabled", False):
        capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "ufficio"))
        return None
    if documenti is None or "pdf" not in getattr(documenti, "formati", ()):
        capacita.segnala("ufficio", "mancante", "servono i documenti in PDF (fpdf2)",
                         "Installa le librerie dei documenti: "
                         + capacita.comando_libreria("fpdf2", "documenti") + ".")
        return None
    try:
        locale = scrittore_locale(documenti.writer)
        scrittore = scrittore_agenti(lavori, locale) if lavori is not None else locale
        svc = Ufficio(cfg, db_path, documenti, scrittore=scrittore,
                      cartella_modelli=cartella_modelli(cfg))
    except Exception as e:  # noqa: BLE001 — l'ufficio è un di più: Calliope parte comunque
        capacita.segnala("ufficio", "guasta", f"{type(e).__name__}: {e}",
                         "Guarda il terminale di Calliope all'avvio.")
        return None
    capacita.REGISTRO.da_dict(capacita.check_ufficio(cfg, svc))
    for err in svc.errori_modelli:
        print(f"   [UFFICIO] modello saltato: {err}", flush=True)
    return svc
