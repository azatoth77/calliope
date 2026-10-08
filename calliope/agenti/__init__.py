"""
Agenti in secondo piano: «gemma davanti, agenti dietro» (02/10/2026,
docs/ricerche/2026-10-02-llm-per-spark.md).

La voce (gemma4, sempre residente) riconosce un lavoro lungo e lo delega con il tool
`lavoro_affida`; un modello grande lo fa in secondo piano, su un'altra macchina (la DGX
Spark, via tunnel SSH) o sullo stesso Ollama (prove, macchina senza DGX), e Calliope lo
annuncia a lavoro finito.

  impostazioni.py  dove sta l'agente: dgx.yaml (tunnel o diretto) oppure agenti_url
  tunnel.py        ssh -N -L … con BatchMode, riaperto se cade, diagnosi senza host né utente
  winjob.py        job object di Windows (ssh muore con Calliope; limiti della sandbox)
  remoto.py        client dell'API nativa di Ollama, interrompibile da un altro thread
  arbitro.py       la voce prima di tutto quando l'agente usa lo stesso Ollama
  sandbox.py       cartella del lavoro, Python e test con tempo massimo, niente rete
  _avvio.py        avvio isolato del codice dell'agente (audit hook)
  ciclo.py         il ciclo dell'agente: codice, documento, modello, ricerca, altro
  file_utente.py   i file della persona dati all'agente: estensioni, testo, nome del risultato
  modelli.py       modelli di documento (template): schema dei campi → compilazione
  servizio.py      coda, proposta e conferma, risultati, scheda, annuncio
  __main__.py      python -m calliope.agenti --prova: solo tunnel, /api/version, /api/tags

I tool vocali sono in calliope/tools/agenti.py.
"""

from .impostazioni import ConfigAgentiNonValida, Impostazioni, carica, ssh_eseguibile
from .servizio import Lavori

__all__ = ["ConfigAgentiNonValida", "Impostazioni", "Lavori", "carica", "load_agenti"]


def load_agenti(cfg, on_done=None, biblioteca=None, formati=("word", "excel", "pdf"),
                log=print, verifica: bool = True, consegna=None) -> Lavori | None:
    """Il servizio dei lavori, o None (spento, nessun agente configurato, file rovinato,
    niente client SSH): Calliope parte uguale e il registro delle capacità dice perché.
    Il primo collegamento (tunnel compreso) parte in secondo piano: l'avvio non aspetta."""
    from .. import capacita
    if not getattr(cfg, "agenti_enabled", False) or not capacita.presente("httpx"):
        capacita.REGISTRO.da_dict(capacita.check_agenti(cfg))
        return None
    try:
        imp = carica(cfg)
    except ConfigAgentiNonValida:
        capacita.REGISTRO.da_dict(capacita.check_agenti(cfg))
        return None
    if imp is None or (imp.tunnel and not ssh_eseguibile()):
        capacita.REGISTRO.da_dict(capacita.check_agenti(cfg))
        return None
    for a in imp.avvisi:
        log(f"[AGENTI] {a}")
    try:
        svc = Lavori(cfg, imp, on_done=on_done, biblioteca=biblioteca, formati=formati, log=log,
                     consegna=consegna)
    except Exception as e:  # noqa: BLE001 — gli agenti sono un di più
        capacita.segnala("agenti", "guasta", f"il servizio non parte ({type(e).__name__})",
                         "Guarda il terminale di Calliope: python -m calliope.stato.",
                         {"errore": str(e)})
        return None
    if getattr(cfg, "agenti_analisi", True):
        # L'analisi della richiesta prima della proposta (06/10, richiesta.py)
        from .richiesta import Analizzatore
        svc.analizzatore = Analizzatore(cfg, svc, log=log)
    if getattr(cfg, "sviluppo_enabled", True):
        # La modalità sviluppo (08/10, calliope/sviluppo.py): l'iter delle estensioni e dei
        # programmi, su disco accanto allo stato dei lavori
        try:
            from ..sviluppo import Sviluppi
            from .servizio import cartella_sandbox
            svc.sviluppi = Sviluppi(cfg, cartella_sandbox(cfg), svc, log=log)
        except Exception as e:  # noqa: BLE001 — senza, i lavori vanno come prima
            log(f"[SVILUPPO] non disponibile: {type(e).__name__}: {e}")
    capacita.REGISTRO.da_dict(capacita.check_agenti(cfg, svc))

    capacita.REGISTRO.dinamica("agenti", lambda: capacita.check_agenti(cfg, svc))
    if verifica:
        svc.verifica_in_secondo_piano()
    return svc
