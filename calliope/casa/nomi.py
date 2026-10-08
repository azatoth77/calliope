"""
Quando Home Assistant non trova il dispositivo di un comando (08/10/2026).

Caso vero sulla DGX, 08/10: la luce che in casa si chiama «Soggiorno» in Home Assistant è
nell'area Ingresso. «Accendi il soggiorno» funzionava (HA la prende per nome), ma «spegni la
luce in soggiorno» no: Assist cerca le luci dell'area Soggiorno, risponde `no_valid_targets`
e Calliope diceva «In soggiorno non posso comandare nessuna luce: non è esposta ad Assist».

Qui, solo dopo quell'errore, si cercano tra le entità **già esposte e visibili** quelle che
corrispondono alla richiesta: la stanza detta («soggiorno») uguale al nome o a un alias
dell'entità (tolte le parole del tipo, «luce soggiorno» = «soggiorno»), oppure alla sua area
(nome o alias); il tipo detto («la luce») uguale al dominio (light, o uno switch con una
parola di luce nel nome: un relè che accende una lampada). È la correzione della forma di
una scelta già fatta dal modello (principio 10: il modello ha scelto casa_comando e il
dispositivo, qui si cambia solo come lo si nomina a HA), con un effetto reversibile
(accendi/spegni, apri/chiudi):

- una sola candidata → si riprova **una** volta con il nome esatto dell'entità, e la
  verifica a secco deve toccare solo lei (mai allargare: altrimenti non si esegue);
- più candidate → si elencano e si chiede quale;
- nessuna → la frase d'errore giusta di HA.

Mai per i domini delicati, i pulsanti di riavvio, scene e script (regole.py), mai oltre le
entità esposte che chi parla può vedere; percentuali e gradi restano al modello. Nel
registro dei turni la regola si chiama `casa_nome_entita`.

Se la stanza detta non è l'area dell'entità, chi amministra riceve un consiglio, una volta
per entità e stanza: detto dopo il comando se è lui a parlare, altrimenti nella risposta di
casa_integrazione (e nella sua guida scritta).
"""

import re
import threading

from .base import Entita
from .parole import _GRADI, _PERCENTO, _VERBI, _verbo_per, _vive, norm

# Parole del tipo di dispositivo: si tolgono dal nome e dalla richiesta per confrontare la
# stanza («luce soggiorno» → «soggiorno»)
_LUCE = re.compile(r"^(luc[ei]|lampad\w*|lampadar\w*|faretti|faretto|plafonier\w*|"
                   r"piantan\w*|applique|abat|jour|led|lumin\w*)$")
_PRESA = re.compile(r"^(pres[ae]|spin[ae]|interruttor\w*|rel[eè])$")
_TAPPARELLA = re.compile(r"^(tapparell\w*|persian\w*|tend[ae]|venezian\w*|oscurant\w*|"
                         r"serrand\w*)$")
_VENTILATORE = re.compile(r"^(ventilator\w*|ventol\w*|pal[ae])$")
_VUOTE = {"il", "lo", "la", "i", "gli", "le", "l", "di", "del", "della", "dello", "dei",
          "delle", "in", "nel", "nella", "nello", "a", "al", "alla", "allo", "ai", "alle",
          "da", "dal", "dalla", "su", "sul", "sulla", "per", "un", "una", "uno", "mi", "me",
          "tutta", "tutte", "tutti", "tutto", "anche", "pure", "per", "favore", "piacere",
          "subito", "adesso", "ora", "casa", "che", "c", "e", "ci", "si", "stanza"}

_PARTICIPI = {"accendi": "acceso", "spegni": "spento", "apri": "aperto", "chiudi": "chiuso",
              "alza": "alzato", "abbassa": "abbassato", "attiva": "attivato",
              "disattiva": "disattivato"}
_ACCENDI = {"accendi", "spegni", "attiva", "disattiva"}
_ACCENDIBILI = {"light", "switch", "fan", "input_boolean"}
_COPERTURE = {"", "shutter", "blind", "curtain", "awning", "shade"}

# Come si dice il tipo nel consiglio («la luce «Soggiorno» è nell'area Ingresso»)
_TIPO = {"light": "la luce", "switch": "l'interruttore", "fan": "il ventilatore",
         "cover": "la tapparella", "input_boolean": "l'interruttore"}


def _tipo_parola(w: str) -> str | None:
    for nome, rx in (("luce", _LUCE), ("presa", _PRESA), ("tapparella", _TAPPARELLA),
                     ("ventilatore", _VENTILATORE)):
        if rx.match(w):
            return nome
    return None


def _nucleo(text: str) -> tuple[str, set[str]]:
    """(le parole che restano, i tipi detti): «la luce in soggiorno» → («soggiorno», {luce})."""
    words, tipi = [], set()
    for w in norm(text).split():
        t = _tipo_parola(w)
        if t:
            tipi.add(t)
        elif w not in _VUOTE:
            words.append(w)
    return " ".join(words), tipi


def _del_tipo(e: Entita, tipi: set[str], verbo: str) -> bool:
    """L'entità è del tipo detto e il verbo le si addice."""
    copertura = e.dominio == "cover" and (e.classe or "") in _COPERTURE
    if verbo in ("alza", "abbassa"):
        adatta = copertura
    elif verbo in ("apri", "chiudi"):
        adatta = copertura or e.dominio in ("light", "switch")     # «chiudi la luce»
    else:
        adatta = e.dominio in _ACCENDIBILI
    if not adatta:
        return False
    if not tipi:
        return True
    luce_nel_nome = any(_LUCE.match(w) for n in [e.nome, *e.alias] for w in norm(n).split())
    return (("luce" in tipi and (e.dominio == "light" or (e.dominio == "switch"
                                                         and luce_nel_nome)))
            or ("presa" in tipi and e.dominio in ("switch", "input_boolean"))
            or ("tapparella" in tipi and copertura)
            or ("ventilatore" in tipi and e.dominio == "fan"))


def _nomi_area(area: str | None, aree: dict | None) -> set[str]:
    if not area:
        return set()
    return {norm(area), *(norm(a) for a in (aree or {}).get(area, []) if a)}


def candidate(testo: str, entita: list[Entita], aree: dict | None, ammessa) -> dict | None:
    """Le entità che corrispondono al comando non trovato da HA.

    `entita`: le esposte visibili a chi parla; `ammessa(e)`: False per quelle che le regole
    non lasciano comandare (delicate, riavvio, da elenco). None se la richiesta non è un
    comando semplice (verbo di accensione o apertura, senza percentuali né gradi) o se non
    nomina una stanza o un nome; altrimenti {"verbo", "stanza", "tipi", "trovate"}."""
    m = _VERBI.match(testo or "")
    if not m or _PERCENTO.search(testo) or _GRADI.search(testo):
        return None
    verbo = m.group(1).lower()
    if verbo not in _PARTICIPI:
        return None
    luogo, tipi = _nucleo(testo[m.end():])
    if not luogo:
        return None
    found = []
    for e in entita:
        if not _del_tipo(e, tipi, verbo) or not ammessa(e):
            continue
        nomi = {_nucleo(n)[0] for n in [e.nome, *e.alias] if n}
        if luogo in nomi or luogo in _nomi_area(e.area, aree):
            found.append(e)
    tutte = list(found)
    found = _vive(found) if found else []
    # Lo stesso nome più volte (una viva e una irraggiungibile, 01/10) è un dispositivo solo;
    # la riprova per nome può toccare anche gli omonimi (HA li risolve da sé), nient'altro
    unici: dict[str, Entita] = {}
    for e in found:
        unici.setdefault(norm(e.nome), e)
    return {"verbo": verbo, "stanza": luogo, "tipi": tipi, "trovate": list(unici.values()),
            "stesso_nome": {norm(e.nome): [x.id for x in tutte if norm(x.nome) == norm(e.nome)]
                            for e in unici.values()}}


def comando_esatto(verbo: str, e: Entita) -> str:
    """«spegni Soggiorno»: il nome come lo conosce HA."""
    return f"{_verbo_per(verbo, e)} {e.nome}"


def nell_area(e: Entita, stanza: str, aree: dict | None) -> bool:
    return stanza in _nomi_area(e.area, aree)


def frase_fatto(verbo: str, e: Entita, stanza: str, aree: dict | None) -> str:
    """«Ho spento «Soggiorno», che in Home Assistant è nell'area Ingresso.»"""
    fatto = _PARTICIPI.get(_verbo_per(verbo, e), "comandato")
    if not e.area:
        return f"Ho {fatto} «{e.nome}»: in Home Assistant non è in nessuna stanza."
    if not nell_area(e, stanza, aree):
        return f"Ho {fatto} «{e.nome}», che in Home Assistant è nell'area {e.area}."
    return f"Ho {fatto} «{e.nome}»."


def _elenco(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " o " + items[-1]


def frase_quale(trovate: list[Entita], massimo: int = 4) -> str:
    """«Ho trovato più dispositivi: «Soggiorno», nell'area Ingresso, o «Lampada», nell'area
    Soggiorno. Quale intendi?»"""
    parti = [f"«{e.nome}»" + (f", nell'area {e.area}" if e.area else "")
             for e in trovate[:massimo]]
    altri = f" e altri {len(trovate) - massimo}" if len(trovate) > massimo else ""
    return f"Ho trovato più dispositivi: {_elenco(parti)}{altri}. Quale intendi?"


# ─────────────────────────── consigli per chi amministra ───────────────────────────

_CONSIGLI: dict[tuple[str, str], dict] = {}
_LOCK = threading.Lock()
_MAX = 20


def _area_detta(stanza: str, aree: dict | None) -> str | None:
    """Il nome vero dell'area detta, se c'è in Home Assistant."""
    for area, alias in (aree or {}).items():
        if stanza in {norm(area), *(norm(a) for a in alias or [])}:
            return area
    return None


def testo_consiglio(e: Entita, detto: str, stanza: str, aree: dict | None) -> str:
    tipo = _TIPO.get(e.dominio, "il dispositivo")
    pron = "la" if tipo.startswith("la ") else "lo"
    dove = (f"è nell'area {e.area}" if e.area else "non è in nessuna area")
    area = _area_detta(stanza, aree)
    sposta = (f"sposta{pron} nell'area {area}" if area else
              f"crea l'area {stanza.capitalize()} e sposta{pron} lì")
    return (f"{tipo[:1].upper()}{tipo[1:]} «{e.nome}» {dove}: se {pron} chiami «{detto}», "
            f"in Home Assistant {sposta}.")


def segna_consiglio(e: Entita, detto: str, stanza: str, aree: dict | None) -> str | None:
    """Ricorda il consiglio (una volta per entità e stanza). Il testo, se è nuovo."""
    if nell_area(e, stanza, aree):
        return None
    key = (e.id, stanza)
    with _LOCK:
        if key in _CONSIGLI:
            return None
        if len(_CONSIGLI) >= _MAX:
            _CONSIGLI.pop(next(iter(_CONSIGLI)))
        text = testo_consiglio(e, detto, stanza, aree)
        _CONSIGLI[key] = {"testo": text, "detto": False}
        return text


def segna_detto(text: str):
    with _LOCK:
        for c in _CONSIGLI.values():
            if c["testo"] == text:
                c["detto"] = True


def consigli_da_dire() -> list[str]:
    """I consigli non ancora detti a chi amministra; li segna come detti."""
    with _LOCK:
        out = [c["testo"] for c in _CONSIGLI.values() if not c["detto"]]
        for c in _CONSIGLI.values():
            c["detto"] = True
        return out


def azzera_consigli():
    """Per le prove."""
    with _LOCK:
        _CONSIGLI.clear()
