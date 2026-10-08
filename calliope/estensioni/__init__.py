"""
Estensioni permanenti di Calliope (04/10/2026): funzioni scritte dall'agente su richiesta di
chi amministra, approvate con la frase di sfida, eseguite sempre in un container con la sola
porta stretta verso Calliope, sotto il guardrail (calliope/guardrail.py).

Progetto: docs/ricerche/2026-10-04-estensioni-e-guardrail.md.
"""

from pathlib import Path

from .servizio import Estensioni

__all__ = ["Estensioni", "cartella", "load_estensioni"]


def cartella(cfg) -> Path:
    p = Path(getattr(cfg, "estensioni_cartella", None) or "estensioni")
    if not p.is_absolute():
        base = getattr(cfg, "config_dir", None)
        p = Path(base) / p if base else p.resolve()
    return p


def load_estensioni(cfg, registry=None, tool_ctx=None, lavori=None, log=print):
    """Il servizio, o None se spento. Il container si sceglie in secondo piano (Docker può
    metterci secondi); il secondo parere usa il client degli agenti, se c'è."""
    if not getattr(cfg, "estensioni_enabled", True):
        return None
    parere = None
    cliente = getattr(lavori, "cliente", None)
    modello = getattr(getattr(lavori, "imp", None), "modello", None)
    if cliente is not None and modello and getattr(cfg, "estensioni_secondo_parere", True):
        from ..guardrail import SecondoParere
        parere = SecondoParere(cliente, modello,
                               float(getattr(cfg, "estensioni_parere_s", 4.0)), log=log)
    try:
        svc = Estensioni(cfg, cartella(cfg), registry=registry, tool_ctx=tool_ctx,
                         secondo_parere=parere, log=log)
    except Exception as e:  # noqa: BLE001 — senza estensioni Calliope parte uguale
        log(f"[ESTENSIONI] non disponibili: {type(e).__name__}: {e}")
        return None
    # I dati riservati di casa (ricordi, nomi, dati privati) non escono da nessuna richiesta:
    # né delle estensioni né delle pagine d'esempio dell'agente (web/riservati.py, 05/10)
    try:
        from ..web.riservati import da_contesto
        svc.rete.riservati = da_contesto(cfg, getattr(tool_ctx, "memory", None),
                                         getattr(tool_ctx, "speakers", None))
    except Exception as e:  # noqa: BLE001
        log(f"[ESTENSIONI] controllo dei dati riservati non disponibile: {e}")
        svc.scegli_in_secondo_piano()
    if lavori is not None:
        lavori.estensioni = svc
        # La modalità sviluppo (08/10, calliope/sviluppo.py): l'approvazione chiude l'iter
        svc.sviluppi = getattr(lavori, "sviluppi", None)
        # Una sola porta verso internet (e un solo tetto al minuto) per estensioni e agente
        agente = getattr(lavori, "agente", None)
        if agente is not None:
            agente.rete = svc.rete
    return svc
