"""
Notizie dai feed RSS delle testate italiane (13/10/2026, ricerche
docs/ricerche/2026-10-12-notizie-rss.md e 2026-10-13-notizie-rss.md): i feed si scaricano in
casa ogni due ore (solo se qualcuno chiede notizie), le notizie si leggono dal disco e la
domanda non esce mai. Il tool `notizie` (calliope/tools/notizie.py) le dà al modello della voce
come fatti numerati, in busta come dato non fidato, e i fatti restano nel contesto.

    feed.py       l'elenco dei feed: configurazione, testate spente e accese, regione di casa
    lettore.py    scarico (condizionato, senza compressione, con un tetto) e lettura XML sicura
    pulizia.py    titoli e sommari per la voce, voci che non sono notizie
    gruppi.py     la stessa notizia da più testate, senza modello (TF-IDF)
    servizio.py   Notizie: indice su disco, scarico periodico, fatti, stato
    contesto.py   la forma ridotta dei fatti detti nei turni vecchi

Solo libreria standard: niente da verificare su ARM.
"""
from __future__ import annotations

__all__ = ["load_notizie"]


def load_notizie(cfg, log=print):
    """Il servizio delle notizie, o None se è spento o senza rete (`online: false`): allora il
    tool non c'è e il registro delle capacità lo dice. Il thread dello scarico lo avvia main.
    Gli import qui dentro: Brain importa contesto.py senza tirarsi dietro il servizio."""
    from .. import capacita
    from .feed import elenco
    from .servizio import Notizie
    d = capacita.check_notizie(cfg)
    if d["stato"] != "attiva":
        capacita.REGISTRO.da_dict(d)
        return None
    feeds = elenco(cfg, log=log)
    try:
        svc = Notizie(cfg, feeds, str(getattr(cfg, "notizie_db", "") or "notizie.db"), log=log)
    except Exception as e:  # noqa: BLE001 — senza indice, niente notizie (e lo si dice)
        log(f"[NOTIZIE] indice non aperto: {type(e).__name__}: {e}")
        capacita.REGISTRO.da_dict(capacita.check_notizie(cfg, errore=str(e)))
        return None
    capacita.REGISTRO.da_dict(capacita.check_notizie(cfg, svc))
    capacita.REGISTRO.dinamica("notizie", lambda: capacita.check_notizie(cfg, svc))
    return svc
