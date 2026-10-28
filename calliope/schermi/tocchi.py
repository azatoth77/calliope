"""
I tocchi che cambiano qualcosa dallo schermo personale (28/10, passo 2a di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, decisione 10 del progetto e decisione 1
del 28/10 nell'issue #241; issue #256).

Un tocco vale come una frase della persona: passa da `ToolRegistry.call` come la voce (permessi,
livello, minori, politica; con `identified_by="schermo"` i tool che vogliono la voce restano
rifiutati) ed entra nella conversazione come un turno. Si fa **sempre** dallo schermo personale,
anche fuori da una conversazione cominciata a voce (decisione di chi amministra del 28/10).

L'elenco è chiuso (`TOCCHI`): la pagina non sceglie il tool né gli argomenti liberi, manda solo
il tipo di tocco e i dati che servono, che qui si controllano contro lo stato vero. Il primo è
la spunta della lista («ho preso il latte»).
"""

import re

from ..liste import say_list, split_items

_MAX_TESTO = 80
# Le forme che per lista_togli svuotano la lista (liste.Liste.remove)
_TUTTO = re.compile(r"\s*(tutto|tutta|tutte|tutti|tutto quanto)\s*", re.I)


def _testo(v, massimo=_MAX_TESTO) -> str | None:
    if not isinstance(v, str):
        return None
    t = re.sub(r"\s+", " ", v).strip()
    return t if 0 < len(t) <= massimo else None


def _spunta_lista(dati: dict, fonti) -> dict:
    """La spunta di una voce della lista: «lista_togli» con quella voce. La voce deve esserci
    adesso nella lista (la pagina può essere rimasta indietro). La scheda taglia le voci lunghe
    a 80 caratteri con «…» (schede._taglia): allora vale l'unica voce che comincia così."""
    liste = getattr(fonti, "liste", None)
    if liste is None:
        return {"errore": "Le liste non sono disponibili.", "_stato": 503}
    lista, voce = _testo(dati.get("lista"), 60), _testo(dati.get("voce"))
    if lista is None or voce is None:
        return {"errore": "dati non validi", "_stato": 400}
    key, voci = liste.read(lista)
    if voce not in voci and voce.endswith("…"):
        simili = [v for v in voci if v.startswith(voce[:-1].rstrip())]
        voce = simili[0] if len(simili) == 1 else voce
    if voce not in voci:
        return {"errore": f"«{voce}» non c'è più nella lista.", "_stato": 409}
    # lista_togli divide le cose su virgole e «e» e svuota la lista con «tutto»: una voce così
    # toglierebbe altro (o niente). Si chiede di dirlo a voce, dove il modello sceglie
    if split_items(voce) != [voce.strip(" .!?")] or _TUTTO.fullmatch(voce):
        return {"errore": "Questa voce si toglie a voce: dimmi che cosa togliere dalla lista.",
                "_stato": 422}
    return {"tool": "lista_togli", "argomenti": {"cose": voce, "lista": key},
            "descrizione": f"(Ho tolto «{voce}» {say_list(key, 'da')} toccando lo schermo.)"}


TOCCHI = {"spunta_lista": _spunta_lista}


def prepara(dati, fonti) -> dict:
    """Dal corpo della richiesta della pagina ({tocco, …}) al tool da chiamare:
    {tool, argomenti, descrizione} o {errore, _stato}."""
    if not isinstance(dati, dict):
        return {"errore": "dati non validi", "_stato": 400}
    f = TOCCHI.get(str(dati.get("tocco") or ""))
    if f is None:
        return {"errore": "tocco sconosciuto", "_stato": 400}
    return f(dati, fonti)
