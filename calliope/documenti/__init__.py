"""
Documenti Word, Excel e PDF creati e modificati a voce.

L'LLM scrive solo contenuti strutturati (JSON, formato.py) in una chiamata separata
(scrittore.py); il codice valida il JSON, fa il file (render.py) e lo consegna
(consegna.py: oggi la cartella Documenti del portatile, domani l'esecutore di un PC
remoto). Il servizio (servizio.py) tiene l'archivio dei JSON per le modifiche e fa i
lavori lunghi in secondo piano. I tool vocali sono in calliope/tools/documenti.py.
"""

from .formato import FORMATI, DocumentoNonValido, validate
from .servizio import Documenti

__all__ = ["FORMATI", "DocumentoNonValido", "Documenti", "load_documenti", "validate"]


def load_documenti(cfg, db_path: str, on_done=None, pcs=None,
                   satelliti=None) -> Documenti | None:
    """Il servizio dei documenti, o None se è spento o mancano tutte le librerie. Come la
    biblioteca e il PC: senza, i tool documento_* non ci sono e all'avvio si dice perché.
    Con `satelliti` (audio_modo: satellite, 03/10) i file vanno al satellite collegato
    (RemoteDelivery), e restano qui solo se nessun satellite li riceve."""
    from .. import capacita
    if not getattr(cfg, "documenti_enabled", False):
        capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "documenti"))
        return None
    from .render import available_formats, find_font
    formats, missing = available_formats()
    pip = (capacita.comando_libreria(" ".join(missing.values()), "documenti")
           if missing else "")
    if not formats:
        capacita.segnala("documenti", "mancante", "mancano python-docx, openpyxl e fpdf2",
                         "Vanno installate nell'ambiente di Calliope: "
                         + capacita.comando_libreria("python-docx openpyxl fpdf2", "documenti")
                         + ".")
        return None
    try:
        delivery = None
        if satelliti is not None:
            from .consegna import LocalDelivery, RemoteDelivery
            delivery = RemoteDelivery(satelliti,
                                      LocalDelivery(getattr(cfg, "documenti_cartella", None)),
                                      getattr(cfg, "pc_nome", "portatile"))
        svc = Documenti(cfg, db_path, formats=formats, on_done=on_done, pcs=pcs,
                        delivery=delivery)
    except Exception as e:  # noqa: BLE001 — i documenti sono un di più: Calliope parte comunque
        capacita.segnala("documenti", "guasta", f"{type(e).__name__}: {e}",
                         "Guarda il terminale di Calliope all'avvio.")
        return None
    notes = [f"{', '.join(formats)} in {svc.delivery.folder}"
             if satelliti is None else
             f"{', '.join(formats)} consegnati al satellite (se non c'è, in "
             f"{svc.delivery.folder})"]
    if missing:
        notes.append("manca " + ", ".join(missing))
    if "pdf" in formats:
        font = find_font(cfg.documenti_font)
        notes.append(f"font del PDF {font[0]}" if font else
                     "nessun font TrueType: il PDF usa Helvetica, senza «€» né virgolette "
                     "tipografiche")
    capacita.segnala("documenti", "attiva", "; ".join(notes),
                     f"Per gli altri formati: {pip}." if pip else "",
                     {"formati": list(formats), "cartella": str(svc.delivery.folder)})
    return svc
