"""
L'archivio dei documenti di casa (03/10/2026): bollette, ricevute, contratti, polizze,
garanzie, referti, documenti d'identità e manuali resi interrogabili a voce, con un indice,
le schede strutturate e un grafo in SQLite (docs/ricerche/2026-10-03-documenti-grafo.md).

  normalizza.py  chiavi di deduplicazione, controlli dei valori contro il testo, come si dice
  grafo.py       il grafo: nodi e archi tipizzati, alias, file, schede, FTS5 (sola lettura
                 per chi interroga)
  tipi.py        i tipi di documento: campi e schema JSON delle schede, controllo, nel grafo
  testo.py       il testo dei file: PDF (pypdfium2), immagini (Pillow), Word; OCR con il
                 modello visivo
  estrattore.py  la scheda dal testo, con il modello grande e gli output strutturati
  servizio.py    la cartella osservata, la coda, i permessi, le interrogazioni della voce
  esplora.py     gli strumenti chiusi dell'agente per esplorare il grafo
  __main__.py    python -m calliope.archivio: stato, un giro subito, rielaborazione, unione

I tool della voce sono in calliope/tools/archivio.py; gli strumenti dell'agente entrano nelle
ricerche delegate (calliope/agenti/ciclo.py).
"""

from pathlib import Path

from .grafo import Grafo
from .servizio import Archivio, Chi, periodo

__all__ = ["Archivio", "Chi", "Grafo", "load_archivio", "percorso_db", "periodo"]


def percorso_db(cfg) -> Path:
    p = Path(getattr(cfg, "archivio_db", None) or "archivio.db")
    if not p.is_absolute():
        base = getattr(cfg, "config_dir", None)
        p = Path(base) / p if base else p.resolve()
    return p


def _modello(cfg, lavori=None):
    """(client, modello, motore, url, prima_di_chiamare) per OCR ed estrazione, o None.
    `archivio_url` vince; altrimenti il modello grande degli agenti (un client a parte: quello
    dei lavori serve al loro thread)."""
    url = (getattr(cfg, "archivio_url", None) or "").strip()
    prima = None
    if url:
        from ..agenti.impostazioni import Impostazioni
        motore = "openai" if url.rstrip("/").endswith("/v1") else "ollama"
        imp = Impostazioni("diretto", url.rstrip("/"),
                           getattr(cfg, "archivio_modello", None) or getattr(cfg, "llm_model", ""),
                           motore=motore)
    else:
        imp = getattr(lavori, "imp", None)
        if imp is None:
            from ..agenti.impostazioni import ConfigAgentiNonValida, carica
            try:
                imp = carica(cfg)
            except ConfigAgentiNonValida:
                imp = None
        if imp is None:
            return None
        if lavori is not None:
            tunnel = getattr(lavori, "tunnel", None)
            if tunnel is not None:
                def prima():
                    tunnel.assicura(imp.timeout_s)
    from ..agenti.remoto import crea_cliente
    modello = (getattr(cfg, "archivio_modello", None) or "").strip() or \
        getattr(imp, "modello_scrittore", None) or imp.modello
    cliente = crea_cliente(imp)
    # La voce prima (04/10): con il modello sulla GPU della voce (stesso Ollama, o vLLM sulla
    # stessa macchina) OCR ed estrazione aspettano la voce e cedono il passo quando qualcuno
    # parla a Calliope; la pagina interrotta si rifà dopo
    arbitro = getattr(lavori, "arbitro", None)
    if arbitro is not None and getattr(arbitro, "condiviso", False):
        from ..agenti.arbitro import ClienteCedevole
        from ..agenti.impostazioni import stessa_gpu
        if stessa_gpu(cfg, None if url else imp, url or None):
            cliente = ClienteCedevole(cliente, arbitro)
    return cliente, modello, imp.motore, imp.url, prima


def load_archivio(cfg, lavori=None, speakers=None, log=print, avvia: bool = True):
    """L'archivio, o None (spento o senza cartella): Calliope parte uguale e il registro delle
    capacità dice perché. Senza il modello grande l'archivio c'è (le domande sui documenti già
    letti funzionano) ma non legge i file nuovi."""
    from .. import capacita
    if not getattr(cfg, "archivio_enabled", False) or not getattr(cfg, "archivio_cartella", None):
        capacita.REGISTRO.da_dict(capacita.check_archivio(cfg))
        return None
    cartella = Path(cfg.archivio_cartella).expanduser()
    if not cartella.is_dir():
        capacita.REGISTRO.da_dict(capacita.check_archivio(cfg))
        return None
    try:
        grafo = Grafo(str(percorso_db(cfg)))
    except Exception as e:  # noqa: BLE001 — l'archivio è un di più
        capacita.segnala("archivio", "guasta", f"il database non si apre ({type(e).__name__})",
                         "Controlla archivio_db in calliope.locale.yaml.", {"errore": str(e)})
        return None
    from .estrattore import Estrattore
    from .testo import OcrVisivo
    est = ocr = None
    m = _modello(cfg, lavori)
    if m is not None:
        cliente, modello, motore, url, prima = m
        from ..agenti.impostazioni import opzioni_voce
        est = Estrattore(cliente, modello, prima_di_chiamare=prima,
                         voce=opzioni_voce(cfg, url, modello, motore))
        if getattr(cfg, "archivio_ocr", True):
            m_ocr = (getattr(cfg, "archivio_ocr_modello", None) or "").strip() or modello
            ocr = OcrVisivo(url, m_ocr, motore, prima_di_chiamare=prima,
                            voce=opzioni_voce(cfg, url, m_ocr, motore))
    profili = (lambda: list(speakers.known_speakers())) if speakers is not None else None
    svc = Archivio(cfg, grafo, cartella, est, ocr, log=log, profili=profili)
    capacita.REGISTRO.da_dict(capacita.check_archivio(cfg, svc))
    capacita.REGISTRO.dinamica("archivio", lambda: capacita.check_archivio(cfg, svc))
    if avvia:
        svc.avvia()
    return svc
