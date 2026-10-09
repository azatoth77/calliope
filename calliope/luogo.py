"""
La città della casa (09/10, decisione di Dario: «se chiedo il meteo senza indicazioni
specifiche si intende quello di casa»).

Da dove viene, in ordine:

1. `casa_citta` della configurazione (calliope.locale.yaml, o CALLIOPE_CASA_CITTA), se è una
   città vera: non vuota e non un segnaposto («<città>», «la tua città», «TODO»…);
2. altrimenti quella detta a voce da chi amministra e salvata da Calliope in `luogo.json`,
   accanto al file di configurazione (fuori da git, come personalita.json). Calliope non
   scrive mai calliope.yaml né calliope.locale.yaml;
3. altrimenti nessuna: Calliope chiede alla persona dove si trova la casa.

Niente servizi esterni: le coordinate di Home Assistant non si convertono in un nome di città
(principio 9, e la decisione di Dario di non dipendere da internet quando se ne può fare a
meno). Il meteo di casa, quando Home Assistant ha un'entità `weather.*` esposta, lo dà Home
Assistant (calliope/casa/meteo.py) e la città non serve.

Solo la libreria standard.
"""
from __future__ import annotations

import datetime
import os
import re
import threading

FILE = "luogo.json"
MAX_LEN = 60

# I segnaposto che si trovano nei file d'esempio o scritti per ricordarsi di riempirli: il
# valore intero (minuscolo, senza punteggiatura ai bordi). «Città di Castello» è una città:
# conta il valore intero, mai una parola dentro
_SEGNAPOSTO = {
    "citta", "città", "la citta", "la città", "la tua citta", "la tua città", "tua citta",
    "tua città", "nome della citta", "nome della città", "paese", "il paese", "il tuo paese",
    "comune", "il tuo comune", "luogo", "casa", "todo", "tbd", "xxx", "xx", "x", "...", "…",
    "esempio", "example", "city", "your city", "town", "changeme", "cambiami", "da fare",
    "inserisci", "inserire", "nessuna", "nessuno", "none", "null", "n/a", "na", "-", "?",
    "sconosciuta", "boh",
}
_PAROLE_SEGNAPOSTO = re.compile(r"\b(todo|tbd|changeme|cambiami|inserisci|inserire|xxx)\b",
                                re.I)


def valida(valore) -> str:
    """La città pulita (spazi normalizzati), o "" se è vuota, un segnaposto o non sembra il
    nome di un posto: parentesi («<città>», «[città]», «{citta}»), niente lettere, troppo
    lunga, parole come TODO."""
    if not isinstance(valore, str):
        return ""
    t = " ".join(valore.split()).strip(" .,;:!\"'«»")
    if not t or len(t) > MAX_LEN:
        return ""
    if re.search(r"[<>\[\]{}()=/\\|@#$%*_]", t) or not re.search(r"[^\W\d_]", t):
        return ""
    if t.lower() in _SEGNAPOSTO or _PAROLE_SEGNAPOSTO.search(t):
        return ""
    return t


def percorso(cfg) -> str | None:
    """Il file della città detta a voce, accanto al file di configurazione. Senza
    `config_dir` (una Config fatta nel codice, le prove) nessun file: mai la cartella
    corrente."""
    base = getattr(cfg, "config_dir", None)
    return os.path.join(base, FILE) if base else None


_cache: dict = {}
_lock = threading.Lock()


def salvata(cfg) -> str:
    """La città salvata a voce (valida), o "". Riletta solo quando il file cambia."""
    p = percorso(cfg)
    if not p:
        return ""
    try:
        mtime = os.path.getmtime(p)
    except OSError:
        return ""
    with _lock:
        hit = _cache.get(p)
        if hit and hit[0] == mtime:
            return hit[1]
    from .persistenza import FileRovinato, leggi_json
    try:
        dati, _ = leggi_json(p)
    except FileRovinato:
        dati = None
    citta = valida((dati or {}).get("casa_citta")) if isinstance(dati, dict) else ""
    with _lock:
        _cache[p] = (mtime, citta)
    return citta


def da_config(cfg) -> str:
    """La città della configurazione, se valida."""
    return valida(getattr(cfg, "casa_citta", "") or "")


def citta_casa(cfg) -> str:
    """La città della casa che vale adesso: la configurazione, poi quella salvata a voce."""
    return da_config(cfg) or salvata(cfg)


def origine(cfg) -> str:
    """"configurazione", "voce" o "" (nessuna)."""
    if da_config(cfg):
        return "configurazione"
    return "voce" if salvata(cfg) else ""


def salva(cfg, citta: str, chi: str | None = None) -> str:
    """Scrive la città detta a voce (già valida) in luogo.json. Restituisce la città
    salvata. Solleva ValueError se non è valida o se non c'è dove scriverla."""
    c = valida(citta)
    if not c:
        raise ValueError("città non valida")
    p = percorso(cfg)
    if not p:
        raise ValueError("nessuna cartella di configurazione")
    from .persistenza import scrivi_json
    scrivi_json(p, {"casa_citta": c, "da": chi,
                    "quando": datetime.datetime.now().isoformat(timespec="seconds")})
    with _lock:
        _cache.pop(p, None)
    return c
