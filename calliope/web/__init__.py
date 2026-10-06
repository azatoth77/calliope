"""
Ricerca su internet (03/10/2026, docs/ricerche/2026-10-03-ricerca-web.md): SearXNG sulla DGX
(setup/linux/motore/searxng.sh), il tool web_cerca per la voce (calliope/tools/web.py) e
web_cerca e web_leggi per l'agente (calliope/agenti/ciclo.py).

    servizio.py   Web: ricerca, pagine, tetto al minuto, diagnosi
    privacy.py    Ripulitore: niente nomi e dati personali nelle domande che escono di casa
    pagina.py     lettura di una pagina senza SSRF, testo estratto senza eseguire niente
"""

import threading

from .. import capacita
from .privacy import Ripulitore, nomi_da, privati_da_config
from .servizio import Risultato, Web, nome_sito, ripulisci_testo

__all__ = ["Web", "Ripulitore", "Risultato", "load_web", "nome_sito", "ripulisci_testo"]


def load_web(cfg, speakers=None, riprova: bool = True, log=print) -> Web | None:
    """La ricerca web, o None se è spenta, senza rete (`online: false`) o senza SearXNG
    configurato: allora il tool non c'è e il registro delle capacità dice il passo.

    Con SearXNG configurato ma giù all'avvio il servizio c'è ma non è `pronta`: il tool non
    si registra, e un thread riprova ogni minuto (/healthz, nessuna ricerca); quando risponde
    main.py registra il tool tra un turno e l'altro, senza riavvio."""
    d = capacita.check_web(cfg)
    if d["stato"] in ("da_configurare", "mancante"):
        capacita.REGISTRO.da_dict(d)
        return None
    svc = Web(cfg, Ripulitore(nomi_da(cfg, speakers), lambda: privati_da_config(cfg)), log=log)
    svc.prova()
    capacita.REGISTRO.da_dict(capacita.check_web(cfg, svc))
    capacita.REGISTRO.dinamica("web", lambda: capacita.check_web(cfg, svc))
    if not svc.pronta and riprova:
        def giro():
            while not svc.prova(timeout_s=2.0):
                svc._ferma.wait(60)
                if svc._ferma.is_set():
                    return
            capacita.REGISTRO.da_dict(capacita.check_web(cfg, svc))
            log("[WEB] SearXNG ora risponde: la ricerca su internet è attiva.")
        threading.Thread(target=giro, name="web-riprova", daemon=True).start()
    return svc
