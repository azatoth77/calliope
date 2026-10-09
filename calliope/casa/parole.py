"""
Le entità della casa dette a voce: articoli, accordi, stati in italiano, numeri, e la
ricerca locale di casa_stato («che temperatura c'è in camera?», «cosa c'è acceso?»).

Tutto deterministico: la frase arriva al TTS così com'è (risposta_finale), senza una
seconda passata del modello. Il genere dei nomi si indovina dalla prima parola, con un
piccolo elenco per le eccezioni: «la luce», «il termostato», «l'abat-jour».
"""

import difflib
import re
import unicodedata
from dataclasses import replace

from .base import Entita

# ─────────────────────────── genere, articoli, accordi ───────────────────────────

_FEMMINILI = {"luce", "luci", "presa", "prese", "tapparella", "tapparelle", "porta", "porte",
              "finestra", "finestre", "serratura", "tenda", "tende", "persiana", "persiane",
              "lampada", "lampade", "lampadina", "piantana", "plafoniera", "abat-jour",
              "applique", "ventola", "caldaia", "stufa", "pompa", "valvola", "striscia",
              "lavatrice", "lavastoviglie", "televisione", "tv", "tivù", "radio", "cappa",
              "serranda", "saracinesca", "temperatura", "umidità", "telecamera", "sirena",
              "centrale", "cucina", "camera", "cameretta", "sala", "basculante", "macchina",
              "spina", "veneziana", "fontana", "irrigazione"}
_MASCHILI_IN_A = {"clima", "sistema", "programma", "tema", "lampadario", "climatizzatore"}
_PLURALI = {"luci", "prese", "tapparelle", "porte", "finestre", "tende", "persiane",
            "lampade", "faretti", "termosifoni", "led", "veneziane", "serrande"}


def _first_word(nome: str) -> str:
    return (re.findall(r"[\wàèéìòù'-]+", nome.lower()) or [""])[0]


def genere(nome: str) -> tuple[bool, bool]:
    """(femminile, plurale) del nome, indovinato dalla prima parola."""
    w = _first_word(nome)
    plural = w in _PLURALI or (w.endswith("i") and len(w) > 3 and w not in ("taxi",))
    if w in _FEMMINILI:
        return True, plural
    if w in _MASCHILI_IN_A:
        return False, plural
    return (w.endswith(("a", "à")) or (plural and w.endswith("e"))), plural


def articolo(nome: str) -> str:
    fem, plural = genere(nome)
    w = _first_word(nome)
    vowel = w[:1] in "aeiouàèéìòùh"
    special = bool(re.match(r"(s[^aeiou]|z|gn|ps|x|y|pn)", w))
    if fem:
        return "le " if plural else ("l'" if vowel else "la ")
    if plural:
        return "gli " if (vowel or special) else "i "
    return "l'" if vowel else ("lo " if special else "il ")


def nome_detto(e: Entita | str) -> str:
    """«la luce cucina»: articolo e iniziale minuscola (le sigle restano: «la presa TV»)."""
    nome = e.nome if isinstance(e, Entita) else str(e)
    nome = nome.strip()
    if len(nome) > 1 and nome[0].isupper() and not nome[1].isupper():
        nome = nome[0].lower() + nome[1:]
    return articolo(nome) + nome


def accorda(base: str, nome: str) -> str:
    """«acces» + «luce» → «accesa»; «chius» + «tapparelle» → «chiuse»."""
    fem, plural = genere(nome)
    return base + ("e" if fem and plural else "i" if plural else "a" if fem else "o")


def _verbo(nome: str) -> str:
    return "sono" if genere(nome)[1] else "è"


def numero(x) -> str:
    """20.5 → «20,5»; 21.0 → «21». I numeri restano in cifre: la voce li legge da sola."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if abs(v - round(v)) < 0.05:
        return str(int(round(v)))
    return f"{v:.1f}".replace(".", ",")


_UNITA = {"°c": "gradi", "°f": "gradi Fahrenheit", "%": "per cento", "w": "watt",
          "kw": "chilowatt", "kwh": "chilowattora", "wh": "wattora", "lx": "lux",
          "hpa": "ettopascal", "ppm": "parti per milione", "v": "volt", "a": "ampere",
          "µg/m³": "microgrammi per metro cubo", "db": "decibel", "l": "litri",
          "m³": "metri cubi", "mm": "millimetri"}


def unita_detta(u: str | None) -> str:
    if not u:
        return ""
    return _UNITA.get(u.strip().lower(), u)


def _is_number(s) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


# ─────────────────────────── stati detti ───────────────────────────

_ACCENDIBILI = {"light", "switch", "fan", "input_boolean", "humidifier", "media_player",
                "siren", "remote"}
_ALLARME = {"disarmed": "è disinserito", "armed_away": "è inserito",
            "armed_home": "è inserito in modalità casa", "armed_night": "è inserito per la notte",
            "armed_vacation": "è inserito in modalità vacanza",
            "armed_custom_bypass": "è inserito con alcune zone escluse",
            "arming": "si sta inserendo", "disarming": "si sta disinserendo",
            "pending": "sta per scattare", "triggered": "è scattato"}
_CLIMA = {"off": "è spento", "heat": "scalda", "cool": "raffresca", "heat_cool": "è in automatico",
          "auto": "è in automatico", "dry": "deumidifica", "fan_only": "fa solo ventilazione"}
_APERTURE = {"door", "garage_door", "window", "opening", "garage"}


def is_on(e: Entita) -> bool:
    """Acceso, in senso largo: per «cosa c'è acceso?»."""
    if e.dominio in _ACCENDIBILI:
        return e.stato in ("on", "playing", "paused", "buffering")
    if e.dominio == "climate":
        return e.stato not in (None, "off", "unavailable", "unknown")
    return False


def is_open(e: Entita) -> bool:
    """Aperto: tapparelle, porte, finestre, serrature non chiuse a chiave."""
    if e.dominio in ("cover", "valve"):
        return e.stato in ("open", "opening", "closing")
    if e.dominio == "binary_sensor" and (e.classe or "") in _APERTURE | {"lock"}:
        return e.stato == "on"
    if e.dominio == "lock":
        return e.stato in ("unlocked", "open", "opening", "unlocking")
    return False


def stato_detto(e: Entita) -> str:
    """Il predicato, senza soggetto: «è accesa», «è chiusa a chiave», «segna 19,8 gradi»."""
    s, n, a = e.stato, e.nome, e.attributi
    if s in (None, "unavailable"):
        return f"{_verbo(n)} {'irraggiungibili' if genere(n)[1] else 'irraggiungibile'}"
    if s == "unknown":
        return "ha uno stato sconosciuto"
    d = e.dominio
    if d == "light" and s == "on" and a.get("brightness") is not None:
        pct = round(int(a["brightness"]) * 100 / 255)
        return f"{_verbo(n)} {accorda('acces', n)} al {pct} per cento"
    if d == "media_player":
        return {"playing": "sta suonando", "paused": "è in pausa", "idle": "è in attesa",
                "off": f"{_verbo(n)} {accorda('spent', n)}",
                "on": f"{_verbo(n)} {accorda('acces', n)}"}.get(s, f"è {s}")
    if d in _ACCENDIBILI:
        return f"{_verbo(n)} {accorda('acces' if s == 'on' else 'spent', n)}"
    if d in ("cover", "valve"):
        pos = a.get("current_position")
        if s == "open" and pos is not None and 0 < int(pos) < 100:
            return f"{_verbo(n)} {accorda('apert', n)} al {int(pos)} per cento"
        return {"open": f"{_verbo(n)} {accorda('apert', n)}",
                "closed": f"{_verbo(n)} {accorda('chius', n)}",
                "opening": "si sta aprendo", "closing": "si sta chiudendo"}.get(s, f"è {s}")
    if d == "lock":
        return {"locked": f"{_verbo(n)} {accorda('chius', n)} a chiave",
                "unlocked": f"non {_verbo(n)} {accorda('chius', n)} a chiave",
                "open": f"{_verbo(n)} {accorda('apert', n)}",
                "jammed": f"{_verbo(n)} {accorda('bloccat', n)}",
                "locking": "si sta chiudendo", "unlocking": "si sta aprendo"}.get(s, f"è {s}")
    if d == "alarm_control_panel":
        return _ALLARME.get(s, f"è nello stato {s}")
    if d == "binary_sensor":
        c, on = (e.classe or ""), s == "on"
        if c in _APERTURE:
            return f"{_verbo(n)} {accorda('apert' if on else 'chius', n)}"
        if c == "lock":                     # binary_sensor lock: on = non chiusa
            return (f"non {_verbo(n)} {accorda('chius', n)} a chiave" if on
                    else f"{_verbo(n)} {accorda('chius', n)} a chiave")
        if c in ("motion", "occupancy", "presence"):
            return "rileva qualcuno" if on else "non rileva nessuno"
        if c in ("moisture",):
            return "segnala acqua" if on else "è asciutto"
        if c in ("smoke", "gas", "carbon_monoxide", "safety", "problem"):
            return "segnala un allarme" if on else "non segnala niente"
        if c == "battery":
            return "ha la batteria scarica" if on else "ha la batteria a posto"
        return "è attivo" if on else "non è attivo"
    if d == "climate":
        parts = [_CLIMA.get(s, f"è in modalità {s}")]
        cur, target = a.get("current_temperature"), a.get("temperature")
        if cur is not None:
            parts.append(f"segna {numero(cur)} gradi")
        if target is not None and s != "off":
            parts.append(f"è impostato a {numero(target)}")
        last = parts[-1]
        joint = (" ed " if last.startswith("è") else " e ") if len(parts) > 1 else ""
        return ", ".join(parts[:-1]) + joint + last
    if d == "weather":
        # L'entità meteo letta per nome da casa_stato (09/10): «partlycloudy» in italiano
        from .meteo import condizione
        t = a.get("temperature")
        return f"dice {condizione(s)}" + (f", {numero(t)} gradi" if t is not None else "")
    if d == "sensor" and _is_number(s):
        u = unita_detta(e.unita)
        return f"segna {numero(s)}" + (f" {u}" if u else "")
    return f"è {s}"


_TIPO_DETTO = {"climate": "il termostato", "light": "la luce", "switch": "la presa",
               "cover": "la tapparella", "media_player": "il lettore", "fan": "il ventilatore",
               "lock": "la serratura", "alarm_control_panel": "l'allarme"}
_CLASSE_DETTA = {"motion": "il sensore di movimento", "occupancy": "il sensore di presenza",
                 "presence": "il sensore di presenza", "temperature": "il sensore di temperatura",
                 "humidity": "il sensore di umidità", "door": "la porta", "window": "la finestra"}


def _tipo(e: Entita, stanze: set[str] | None) -> str | None:
    """Il tipo detto («il termostato») se l'entità si chiama come una stanza, altrimenti
    None. Il 01/10 22 termostati su 23 avevano il nome della stanza: «la camera è accesa»."""
    if stanze and norm(e.nome) in stanze:
        return _CLASSE_DETTA.get(e.classe or "") or _TIPO_DETTO.get(e.dominio, "il dispositivo")
    return None


def soggetto(e: Entita, stanze: set[str] | None = None) -> str:
    """«la luce cucina»; per un nome uguale a una stanza «il termostato in camera»."""
    tipo = _tipo(e, stanze)
    return f"{tipo} in {e.nome.lower()}" if tipo else nome_detto(e)


def frase_stato(e: Entita, stanze: set[str] | None = None) -> str:
    """«La luce cucina è accesa.»; «Il termostato in camera è in automatico.»"""
    tipo = _tipo(e, stanze)
    # L'accordo («acceso/accesa») segue il nome che si dice: il tipo, se c'è
    pred = stato_detto(e if not tipo else replace(e, nome=tipo.split(" ", 1)[-1].lstrip("'")))
    s = soggetto(e, stanze)
    return s[:1].upper() + s[1:] + " " + pred + "."


_MORTI = (None, "unavailable", "unknown")


# ─────────────────────────── ricerca per casa_stato ───────────────────────────

def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", t).strip()


_STOP = {"il", "lo", "la", "i", "gli", "le", "l", "di", "del", "della", "dello", "dei",
         "delle", "in", "nel", "nella", "nello", "a", "al", "alla", "e", "c", "e'", "che",
         "cosa", "com", "come", "quanto", "quanti", "quante", "qual", "quale", "sono", "ci",
         "c'e", "da", "su", "sul", "sulla", "per", "un", "una", "uno", "mi", "dimmi", "casa"}

# Categorie: parole della domanda → quali entità
_CATEGORIE = [
    ("temperatura", r"temperatur|\bgradi\b|\bcaldo\b|\bfreddo\b|\bfresco\b"),
    ("umidita", r"umidit"),
    ("luce", r"\bluc[ei]\b|lampad|faretti|plafonier|piantan|abat ?jour|applique"),
    ("tapparella", r"tapparell|persian|\btend[ae]\b|venezian|oscurant"),
    ("finestra", r"finestr"),
    ("garage", r"garage|basculant|serrand|saracinesc"),
    ("cancello", r"cancell"),
    ("porta", r"\bport[ae]\b|portone|ingresso"),
    ("presa", r"\bpres[ae]\b|\bspin[ae]\b|interruttor"),
    ("serratura", r"serratur|\bchiav|lucchett"),
    ("allarme", r"allarm|antifurto"),
    ("clima", r"termostat|riscaldament|caldaia|climatizz|condizionat|termosifon"),
    ("presenza", r"moviment|presenz|qualcuno"),
    ("acceso", r"\bacces[oaie]\b|\bspent[oaie]\b|\bacceso\b"),
    ("aperto", r"\bapert[oaie]\b|\bchius[oaie]\b"),
]


def _in_categoria(e: Entita, cat: str) -> bool:
    c, d = (e.classe or ""), e.dominio
    return {
        "temperatura": (d == "sensor" and c == "temperature") or d == "climate",
        "umidita": d == "sensor" and c == "humidity",
        "luce": d == "light",
        "tapparella": d == "cover" and c in ("", "shutter", "blind", "curtain", "awning",
                                             "shade"),
        "finestra": c == "window",
        "garage": c in ("garage", "garage_door"),
        "cancello": c == "gate",
        "porta": c in ("door", "garage_door", "garage", "opening") or d == "lock",
        "presa": d == "switch",
        "serratura": d == "lock",
        "allarme": d == "alarm_control_panel",
        "clima": d == "climate",
        "presenza": d == "binary_sensor" and c in ("motion", "occupancy", "presence"),
        "acceso": d in _ACCENDIBILI or d == "climate",
        "aperto": is_open(e) or d in ("cover", "lock") or c in _APERTURE,
    }.get(cat, False)


def _parole(text: str) -> list[str]:
    return [w for w in norm(text).split() if w not in _STOP]


def _nomi(e: Entita) -> list[str]:
    return [n for n in [e.nome, *e.alias] if n]


def trova_area(testo: str, entita: list[Entita], aree: dict[str, list[str]] | None = None
               ) -> tuple[str | None, str | None]:
    """(stanza, piano) nominati nella frase. `aree`: nome → alias, se l'adattatore li ha."""
    t = f" {norm(testo)} "
    names: dict[str, tuple[str, str]] = {}
    for e in entita:
        if e.area:
            names.setdefault(norm(e.area), ("area", e.area))
        if e.piano:
            names.setdefault(norm(e.piano), ("piano", e.piano))
    for area, aliases in (aree or {}).items():
        for a in [area, *aliases]:
            names.setdefault(norm(a), ("area", area))
    best = None
    for key, (kind, value) in names.items():
        if key and f" {key} " in t and (best is None or len(key) > len(best[0])):
            best = (key, kind, value)
    if best is None:
        return None, None
    return (best[2], None) if best[1] == "area" else (None, best[2])


def trova_per_nome(testo: str, entita: list[Entita]) -> list[Entita]:
    """Le entità nominate nella frase: tutte le parole del nome (o di un alias) presenti,
    oppure un nome molto simile. Vince il nome più lungo trovato."""
    words = set(_parole(testo))
    t = f" {norm(testo)} "
    scored = []
    for e in entita:
        best = 0.0
        for n in _nomi(e):
            nw = _parole(n)
            if not nw:
                continue
            if f" {norm(n)} " in t or all(w in words for w in nw):
                best = max(best, 1.0 + len(nw) / 10)
            else:
                # Tolleranza sulle storpiature: ogni parola del nome ha una parola simile
                close = [max((difflib.SequenceMatcher(None, w, x).ratio() for x in words),
                             default=0) for w in nw]
                if close and min(close) >= 0.84:
                    best = max(best, min(close))
        if best:
            scored.append((best, e))
    if not scored:
        return []
    top = max(s for s, _ in scored)
    return [e for s, e in scored if s >= top - 1e-6]


_VERBI = re.compile(r"^\W*(accendi|spegni|apri|chiudi|alza|abbassa|attiva|disattiva|"
                    r"imposta|metti|porta|regola|setta)\b", re.I)
_PERCENTO = re.compile(r"\b(?:al|a|del)\s+(\d{1,3})\s*(?:%|per\s*cento)", re.I)
_GRADI = re.compile(r"\b(?:a|ai)\s+(\d{1,2}(?:[.,]5)?)\s*(?:°|gradi)", re.I)


_ONOFF = ("accendi", "spegni", "apri", "chiudi", "alza", "abbassa", "attiva", "disattiva")


def _vive(entita: list[Entita]) -> list[Entita]:
    """Le entità raggiungibili, se ce n'è almeno una; altrimenti tutte."""
    alive = [e for e in entita if e.stato not in _MORTI]
    return alive or list(entita)


def nome_esatto(testo: str, entita: list[Entita]) -> str | None:
    """Il nome (o alias) di un'entità detto tale e quale dentro la frase, a parole intere:
    «accendi l'interruttore taverna» con un'entità «Taverna» → «Taverna». Il più lungo, e
    tra nomi uguali quello di un'entità viva."""
    t = f" {norm(testo)} "
    best = None
    for e in sorted(entita, key=lambda e: e.stato in _MORTI):
        for n in _nomi(e):
            k = norm(n)
            if k and f" {k} " in t and (best is None or len(k) > len(norm(best))):
                best = n
    return best


def riscrivi(testo: str, entita: list[Entita]) -> list[str]:
    """Riformulazioni deterministiche di un comando che la casa non ha capito, nella forma
    delle frasi standard di Home Assistant: il nome esatto del dispositivo («spegni la presa
    della TV» → «spegni la presa TV») e le percentuali («metti la luce del bagno al 30 per
    cento» → «imposta la luminosità della luce bagno al 30%»). Il modello sbaglia spesso
    proprio queste due cose; un tentativo locale costa pochi millisecondi."""
    m = _VERBI.match(testo or "")
    if not m:
        return []
    verb = m.group(1).lower()
    found = _vive(trova_per_nome(testo, entita))
    # Più entità con lo stesso nome (01/10: due «Taverna», una irraggiungibile): è un nome
    # solo, e vale quello delle vive. HA lo risolve da sé
    if len(found) > 1 and len({norm(e.nome) for e in found}) == 1:
        found = found[:1]
    pct, deg = _PERCENTO.search(testo), _GRADI.search(testo)
    out = []
    if len(found) == 1:
        e = found[0]
        name = nome_detto(e)
        verb = _verbo_per(verb, e)
        if pct and e.dominio == "light":
            out.append(f"imposta la luminosità di {e.nome} al {pct.group(1)}%")
        elif pct and e.dominio == "cover":
            out.append(f"imposta {name} al {pct.group(1)}%")
        elif deg and e.dominio == "climate":
            out.append(f"imposta {name} a {deg.group(1).replace(',', '.')} gradi")
        elif verb in _ONOFF:
            out.append(f"{verb} {name}")
    if pct and not out:
        area, _ = trova_area(testo, entita)
        if area and re.search(r"\bluc[ei]\b|lampad", norm(testo)):
            out.append(f"imposta la luminosità in {area.lower()} al {pct.group(1)}%")
    # Un nome detto tale e quale dentro una frase che HA non capisce («accendi
    # l'interruttore taverna», 01/10: HA non conosce «l'interruttore X»): «<verbo> <nome>»
    if not out and not pct and not deg and verb in _ONOFF:
        exact = nome_esatto(testo, entita)
        if exact:
            same = [e for e in entita if norm(e.nome) == norm(exact)]
            out.append(f"{_verbo_per(verb, same[0]) if same else verb} {exact}")
    return [t for t in out if norm(t) != norm(testo)]


def _verbo_per(verb: str, e: Entita) -> str:
    """«Chiudi»/«apri» una luce o un interruttore è «spegni»/«accendi» (in molte regioni si
    dice «chiudi la luce»): le frasi di HA li accettano solo per tapparelle e porte. 01/10,
    «chiudi taverna» con Taverna interruttore: HA non capiva, e la riscrittura teneva il
    verbo («chiudi la taverna»)."""
    if e.dominio in ("light", "switch"):
        return {"chiudi": "spegni", "apri": "accendi"}.get(verb, verb)
    return verb


def categorie(testo: str) -> list[str]:
    t = norm(testo)
    return [cat for cat, pat in _CATEGORIE if re.search(pat, t)]


def suggerimenti(testo: str, entita: list[Entita], n: int = 6) -> tuple[list[str], list[str]]:
    """(nomi, stanze) più vicini alle parole dette: per l'errore «non ho capito»."""
    words = _parole(testo)
    # Un nome per dispositivo, anche se più entità lo condividono (01/10: «Taverna» due
    # volte, una irraggiungibile); i nomi delle sole entità irraggiungibili vanno in fondo
    alive = {norm(x) for e in entita if e.stato not in _MORTI for x in _nomi(e)}
    unique: dict[str, str] = {}
    for e in sorted(entita, key=lambda e: e.stato in _MORTI):
        for x in _nomi(e):
            unique.setdefault(norm(x), x)
    nomi = sorted(unique.values(), key=lambda x: (norm(x) not in alive, x))
    stanze = sorted({e.area for e in entita if e.area} | {e.piano for e in entita if e.piano})

    def score(name: str) -> float:
        nw = _parole(name) or [norm(name)]
        return max((difflib.SequenceMatcher(None, a, b).ratio() for a in nw for b in words),
                   default=0.0)

    best = sorted(nomi, key=lambda x: (-score(x), norm(x) not in alive))
    near = [x for x in best if score(x) >= 0.5][:n] or best[:n]
    return near, stanze[:12]


def _elenco(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


def _dove(area: str | None, piano: str | None) -> str:
    if area:
        return f"in {area.lower()}"
    if piano:
        return f"al {piano.lower()}" if norm(piano).startswith(("primo", "secondo", "terzo",
                                                                  "piano", "ultimo")) \
            else f"al piano {piano.lower()}"
    return ""


_SINONIMI = [(re.compile(r"\b(fuori|all'aperto|esterno)\b", re.I), "esterna"),
             (re.compile(r"\bsalotto\b", re.I), "sala")]


def descrivi(testo: str, entita: list[Entita], aree: dict | None = None,
             massimo: int = 5) -> dict:
    """La risposta di casa_stato: {"ok", "frase", "entita": [id]} oppure {"ok": False,
    "motivo", "nomi_vicini", "stanze"}."""
    for pat, repl in _SINONIMI:
        testo = pat.sub(repl, testo or "")
    area, piano = trova_area(testo, entita, aree)
    cats = categorie(testo)
    by_name = trova_per_nome(testo, entita)
    pool = entita
    if area:
        pool = [e for e in pool if e.area == area]
    elif piano:
        pool = [e for e in pool if e.piano == piano]
    where = _dove(area, piano)
    named = [e for e in by_name if e in pool] if (area or piano) else by_name
    # Un dispositivo che si chiama come la stanza nominata («Cucina» in cucina) non è un
    # nome preciso: vale la stanza (01/10: vincevano 4 dispositivi morti di nome «Cucina»)
    named = [e for e in named if norm(e.nome) not in {norm(area or ""), norm(piano or "")}]
    state_cats = [c for c in cats if c in ("acceso", "aperto")]
    kind_cats = [c for c in cats if c not in ("acceso", "aperto")]

    # Un nome preciso vince sulle categorie: «la porta del garage è chiusa?»
    if named and not state_cats:
        chosen = named
    elif kind_cats:
        chosen = [e for e in pool if any(_in_categoria(e, c) for c in kind_cats)]
    elif state_cats:
        chosen = [e for e in pool if any(_in_categoria(e, c) for c in state_cats)]
    elif area or piano:
        chosen = pool
    elif not _parole(testo):
        chosen = entita            # «com'è la casa?»: riassunto
        state_cats = ["acceso"]
    else:
        chosen = []
    if len(chosen) > 1 and kind_cats:
        # «quanti gradi ci sono fuori?» → solo «Temperatura esterna»: una parola del nome
        # che non è la categoria stessa restringe la scelta
        # Le parole della stanza non contano: «temperatura in cucina» teneva solo i sensori
        # con «cucina» nel nome (morti) e scartava «Interno Temperatura», che è in cucina
        place = set(_parole(area or "")) | set(_parole(piano or ""))
        specific = {w for w in _parole(testo)
                    if w not in place and not any(re.search(p, w) for _, p in _CATEGORIE)}
        narrowed = [e for e in chosen
                    if specific & {w for n in _nomi(e) for w in _parole(n)}]
        if narrowed:
            chosen = narrowed
    if not chosen:
        nomi, stanze = suggerimenti(testo, entita)
        return {"ok": False, "motivo": f"nessun dispositivo per «{testo}»"
                + (f" {where}" if where else ""), "nomi_vicini": nomi, "stanze": stanze}
    rooms = ({norm(e.area) for e in entita if e.area} | {norm(e.piano) for e in entita if e.piano}
             | {norm(a) for a in (aree or {})})

    # «Cosa c'è acceso?», «c'è qualcosa di aperto in camera?»: si contano le cose
    on_kinds = all(c in ("luce", "presa", "clima") for c in kind_cats)
    if "acceso" in state_cats and on_kinds:
        on = [e for e in chosen if is_on(e)]
        return _conta(on, "accese", "acceso", where, chosen, rooms)
    if "aperto" in state_cats and (not kind_cats or not named):
        opened = [e for e in chosen if is_open(e)]
        return _conta(opened, "aperte", "aperto", where, chosen, rooms)

    # Le entità irraggiungibili si saltano se ce ne sono di vive (01/10: per «temperatura in
    # cucina» c'erano 4 sensori morti e uno vivo, e la risposta era «la cucina è
    # irraggiungibile» quattro volte). Se sono tutte morte lo si dice una volta.
    live = [e for e in chosen if e.stato not in _MORTI]
    if not live:
        n = len(chosen)
        cosa_ = "il dispositivo" if n == 1 else f"i {n} dispositivi"
        verbo = "non risponde" if n == 1 else "non rispondono"
        frase = f"{cosa_.capitalize()}{' ' + where if where else ''} {verbo} in questo momento."
        return {"ok": True, "frase": frase, "entita": [e.id for e in chosen]}
    chosen = live

    # Temperature di una stanza: una frase per sensore o termostato
    sentences = []
    for e in chosen[:massimo]:
        if e.dominio == "sensor" and (e.classe or "") == "temperature" and _is_number(e.stato):
            if e.area:
                same_room = sum(1 for x in chosen if x.area == e.area) > 1
                extra = f" ({e.nome.lower()})" if same_room else ""
                sentences.append(f"In {e.area.lower()} ci sono {numero(e.stato)} gradi{extra}.")
            else:
                subject = soggetto(e, rooms)
                sentences.append(f"{subject[:1].upper()}{subject[1:]} segna "
                                 f"{numero(e.stato)} gradi.")
        else:
            sentences.append(frase_stato(e, rooms))
    if len(chosen) > massimo:
        sentences.append(f"E altri {len(chosen) - massimo}.")
    sentences = list(dict.fromkeys(sentences))     # mai la stessa frase due volte
    return {"ok": True, "frase": " ".join(sentences), "entita": [e.id for e in chosen]}


def _conta(found: list[Entita], plural: str, singular: str, where: str,
           chosen: list[Entita], rooms: set[str] | None = None) -> dict:
    """«Ora sono accese 2 cose: la luce cucina e la piantana.» (cose: femminile, così
    l'accordo va bene con qualunque dispositivo)."""
    where_s = f" {where}" if where else ""
    if not found:
        frase = (f"{where_s.strip().capitalize()} non c'è niente di {singular}." if where
                 else f"Non c'è niente di {singular}.")
    elif len(found) == 1:
        frase = (f"{where_s.strip().capitalize() + ' è' if where else 'È'} "
                 f"{plural[:-1]}a solo una cosa: {soggetto(found[0], rooms)}.")
    else:
        names = list(dict.fromkeys(soggetto(e, rooms) for e in found[:6]))
        more = f" e altre {len(found) - 6}" if len(found) > 6 else ""
        frase = (f"{where_s.strip().capitalize() + ' sono' if where else 'Sono'} "
                 f"{plural} {len(found)} cose: {_elenco(names) if not more else ', '.join(names)}"
                 f"{more}.")
    return {"ok": True, "frase": frase, "entita": [e.id for e in found or chosen]}
