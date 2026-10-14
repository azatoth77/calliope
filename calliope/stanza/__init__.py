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
- `guardia` (passo 6, 14/10): il guardiano a posteriori sulle chiacchiere con un minore
  (`stanza_guardia: spenta|ombra|attiva`, di serie spenta): in ombra solo misure, attiva solo
  un avviso al tutore sullo schermo personale.
- `conoscenti` (14/10, decisione 0030): le voci sconosciute di adulti in gruppi in memoria, il
  nome dedotto dalla conversazione, la proposta a chi amministra sullo schermo personale, i
  conoscenti confermati (livello ospite) riconosciuti nelle righe (`stanza_conoscenti`, di serie
  spento).

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
    st.conoscenti = load_conoscenti_stanza(cfg, st, registry, mis, log)
    return st


def load_conoscenti_stanza(cfg, st, registry=None, misure=None, log=print):
    """I conoscenti (14/10) con `stanza_conoscenti: true`, legati alla stanza e alla tenuta:
    un conoscente tolto si toglie anche dalle righe, una promozione le sposta."""
    from .conoscenti import load_conoscenti
    con = load_conoscenti(cfg, registry, misure, log)
    if con is None:
        return None
    con.su_tolto.append(st.conoscente_tolto)
    con.su_livello.append(st.cambio_livello)
    if st.tenuta is not None:
        st.tenuta.conoscenti = con
    # I nomi delle stanze e dei satelliti non sono nomi di persona
    for v in (getattr(cfg, "stanza_satelliti", None) or []):
        con.esclusi.add(str(v))
    return con


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


def load_guardia(cfg, stanza, guardiano=None, occupato=(), log=print):
    """Il guardiano a posteriori (passo 6, 14/10) con `stanza_guardia: ombra|attiva`, la
    stanza accesa e i minori; altrimenti None (nessun thread). `guardiano`: quello della voce
    (calliope/guardiano.py), per lo stesso client e le stesse opzioni del rilevatore; senza,
    uno nuovo solo per il rilevatore. `occupato`: funzioni che dicono se la voce lavora."""
    from . import guardia
    if (stanza is None or guardia.modo(cfg) == guardia.SPENTA
            or not getattr(cfg, "minori_enabled", True)):
        return None
    if guardiano is None:
        from ..guardiano import Guardiano
        guardiano = Guardiano(cfg, log=log)
    if guardiano._pericolo_modello() is None:
        log("[GUARDIA] guardiano a posteriori spento: nessun rilevatore di pericolo "
            "(guardiano_pericolo)")
        return None
    g = guardia.Guardia(cfg, stanza, guardia.GiudiceModello(
        guardiano, float(getattr(cfg, "stanza_guardia_timeout_s", 30.0) or 30.0)),
        registry=stanza.registry, occupato=occupato, log=log)
    log(f"[GUARDIA] Guardiano a posteriori della stanza: {guardia.modo(cfg)} ("
        + ("solo misure, nessun avviso" if guardia.modo(cfg) == guardia.OMBRA else
           "avviso al tutore sullo schermo personale, mai a voce") + ")")
    return g


__all__ = ["OMBRA", "SPENTA", "Stanza", "load_guardia", "load_stanza", "load_tenuta", "modo"]
