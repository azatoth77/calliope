"""
La conversazione di stanza (13/10, decisione 0029; progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md). Passo 1: in ombra, sola trascrizione
veloce, niente nel contesto del modello.

- `ascolto.Stanza`: segmenti dai satelliti, corsia veloce, presenze, pausa, «dimentica»;
- `registro.RegistroStanza`: il registro della stanza di un satellite (in memoria);
- `coda.Precedenza`: Whisper una richiesta alla volta, con la precedenza turno > recupero >
  stanza > lenta;
- `misure`: i numeri (mai parole) per `calliope stato --turni`.

Di serie spenta (`stanza: spenta`): non parte nessun thread, i satelliti non mandano niente.
"""

from .ascolto import OMBRA, SPENTA, Stanza, modo


def load_stanza(cfg, stt, registry=None, log=print):
    """La stanza se `stanza: ombra` e ci sono i satelliti, altrimenti None."""
    if modo(cfg) == SPENTA or getattr(cfg, "audio_modo", "locale") != "satellite":
        return None
    from .misure import Misure
    mis = Misure(getattr(cfg, "turn_log_dir", None), int(getattr(cfg, "turn_log_days", 60) or 60))
    return Stanza(cfg, stt, registry=registry, misure=mis, log=log)


__all__ = ["OMBRA", "SPENTA", "Stanza", "load_stanza", "modo"]
