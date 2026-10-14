"""
La conversazione di stanza (13/10, decisione 0029; progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md). Passo 1: in ombra, sola trascrizione
veloce, niente nel contesto del modello.

- `ascolto.Stanza`: segmenti dai satelliti, corsia veloce, presenze, pausa, «dimentica»;
- `registro.RegistroStanza`: il registro della stanza di un satellite (in memoria);
- `coda.Precedenza`: Whisper una richiesta alla volta, con la precedenza turno > recupero >
  stanza > lenta;
- `misure`: i numeri (mai parole) per `calliope stato --turni`;
- `contesto` (passo 2, 14/10): il blocco della stanza nei dati del turno (`stanza_contesto`);
- `cerca` (passo 4, 14/10): la ricerca del tool `stanza_cerca`, con chi vede cosa e la frase
  d'attesa (`stanza_cerca`);
- `tenuta` (14/10): il testo della stanza su disco per 60 giorni (`stanza_tenuta`, di serie
  spenta), cercato con gli stessi permessi, cancellato da «dimentica» e da
  `calliope conserva --svuota`.

Di serie spenta (`stanza: spenta`): non parte nessun thread, i satelliti non mandano niente.
"""

from .ascolto import OMBRA, SPENTA, Stanza, modo


def load_stanza(cfg, stt, registry=None, log=print):
    """La stanza se `stanza: ombra` e ci sono i satelliti, altrimenti None."""
    if modo(cfg) == SPENTA or getattr(cfg, "audio_modo", "locale") != "satellite":
        return None
    from .misure import Misure
    mis = Misure(getattr(cfg, "turn_log_dir", None), int(getattr(cfg, "turn_log_days", 60) or 60))
    st = Stanza(cfg, stt, registry=registry, misure=mis, log=log)
    st.tenuta = load_tenuta(cfg, registry, log)
    return st


def load_tenuta(cfg, registry=None, log=print):
    """La tenuta su disco (14/10) con `stanza_tenuta: true`, altrimenti None. Un file che non
    si apre lascia la stanza in memoria, come prima, e lo dice."""
    from . import tenuta
    if not tenuta.accesa(cfg):
        return None
    try:
        t = tenuta.Tenuta(tenuta.percorso_db(cfg), int(getattr(cfg, "stanza_tenuta_giorni", 60)
                                                       or 60), registry=registry, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"[STANZA] tenuta su disco non pronta ({type(e).__name__}: {e}): solo in memoria")
        return None
    log(f"[STANZA] Testo della stanza anche su disco per {t.giorni} giorni (famiglia e minori; "
        f"mai ospiti né zona grigia)")
    return t


__all__ = ["OMBRA", "SPENTA", "Stanza", "load_stanza", "load_tenuta", "modo"]
