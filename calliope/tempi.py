"""
Espressioni di tempo dette a voce → secondi o istanti, in Python.

Il modello passa la durata o l'orario così come l'ha sentito («mezz'ora», «un'ora e un
quarto», «domani alle 9», «alle 6 e mezza») e la conversione si fa qui: nel banco dei
tool del 26/09 gemma4 trasformava «tra mezz'ora» in minuti=60 in ogni strategia,
anche con il thinking (docs/ricerche/2026-09-26-tool-e-agenti.md).

    parse_duration("un'ora e un quarto")  → 4500
    parse_when("domani alle 9", adesso)   → datetime di domani alle 9:00
"""

import datetime
import re
from .testi import MESI

_UNITS = {"zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4,
          "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
          "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15,
          "sedici": 16, "diciassette": 17, "diciotto": 18, "diciannove": 19}
_TENS = {"venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50, "sessanta": 60,
         "settanta": 70, "ottanta": 80, "novanta": 90}


def word_number(w: str) -> int | None:
    """Numero da 0 a 199 scritto in lettere («ventitré», «trentuno», «centoventi»)."""
    w = w.lower().replace("é", "e").replace("è", "e")
    if w.isdigit():
        return int(w)
    base = 0
    if w.startswith("cento"):
        base, w = 100, w[5:]
        if not w:
            return 100
    if w in _UNITS:
        return base + _UNITS[w]
    for t, v in _TENS.items():
        stem = t[:-1]                      # «vent», «trent»… davanti a «uno» e «otto»
        for prefix in (t, stem):
            if w.startswith(prefix):
                rest = w[len(prefix):]
                if not rest:
                    return base + v if prefix == t else None
                if rest in _UNITS and _UNITS[rest] < 10:
                    return base + v + _UNITS[rest]
    return None


def _normalize(text: str) -> str:
    t = text.lower().strip()
    t = t.replace("’", "'").replace("mezz'ora", "mezzora").replace("mezz ora", "mezzora")
    t = re.sub(r"\bun'", "un ", t)
    t = re.sub(r"\bquarti d'ora\b", "quartidora", t)
    t = re.sub(r"\bquarto d'ora\b", "quartodora", t)
    t = re.sub(r"\bd'(ore|ora)\b", r"di \1", t)        # «un paio d'ore»
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    return re.sub(r"[^\w\s.:']", " ", t)


def _num(tok: str) -> float | None:
    try:
        return float(tok)
    except ValueError:
        n = word_number(tok)
        return float(n) if n is not None else None


_UNIT_SECONDS = {"secondo": 1, "secondi": 1, "sec": 1, "minuto": 60, "minuti": 60,
                 "min": 60, "ora": 3600, "ore": 3600, "giorno": 86400, "giorni": 86400}


def parse_duration(text: str) -> int | None:
    """Durata detta a voce → secondi (None se non si capisce)."""
    t = _normalize(text)
    t = re.sub(r"^\s*(tra|fra|per|di|circa)\s+", "", t)
    words = t.split()
    total, value, last_unit, i, found = 0.0, None, None, 0, False
    while i < len(words):
        w = words[i]
        if w == "mezzora":
            total += 1800 * (value if value else 1)
            value, found = None, True
        elif w in ("quartodora", "quartidora"):
            total += 900 * (value if value else 1)
            value, found = None, True
        elif w in _UNIT_SECONDS:
            total += (value if value is not None else 1) * _UNIT_SECONDS[w]
            last_unit, value, found = _UNIT_SECONDS[w], None, True
        elif w in ("mezzo", "mezza") and last_unit:
            total += last_unit / 2                     # «un'ora e mezza», «un minuto e mezzo»
        elif w in ("paio", "coppia") and value in (None, 1):
            value = 2                                    # «un paio di minuti» (04/10: era 1)
        elif w == "quarto" and last_unit == 3600:
            total += 900                                 # «un'ora e un quarto»
            value = None
        elif w in ("e", "d", "di", "dora", "un", "uno", "una") and value is None and w not in ("un", "uno", "una"):
            pass
        else:
            n = _num(w)
            if n is not None:
                value = n
        i += 1
    if value is not None:
        if not found:
            total, found = value * 60, True            # numero senza unità: minuti
        elif last_unit and last_unit >= 60:
            total += value * last_unit / 60            # «un'ora e 30» → 30 minuti
    return int(round(total)) if found and total > 0 else None


# Una durata detta come spostamento (03/10, cambiare un timer o un promemoria già messo):
# «5 minuti in più», «altri 5 minuti», «aggiungi 5 minuti», «mezz'ora più tardi» allungano;
# «2 minuti in meno», «toglici 2 minuti», «10 minuti prima» accorciano
_PLUS = re.compile(r"^\s*\+|\b(?:in\s+più|più\s+tardi|più|altr[ie]|aggiung\w*|ancora|dopo|"
                   r"in\s+avanti|posticip\w*|rimand\w*|allung\w*)\b")
_MINUS = re.compile(r"^\s*-|\b(?:in\s+meno|meno|togli\w*|prima|in\s+anticipo|anticip\w*|"
                    r"più\s+presto|accorci\w*)\b")
_ABSOLUTE = re.compile(r"\b(?:alle|all|ore|tra|fra|domani|dopodomani|oggi|stasera|mezzogiorno|"
                       r"mezzanotte|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica)\b")


def parse_shift(text: str) -> int | None:
    """Spostamento detto a voce → secondi con il segno («5 minuti in più» → 300, «toglici due
    minuti» → -120). None se la frase non dice di allungare o accorciare, o è un orario
    («alle sette meno un quarto», «tra 5 minuti»): allora vale com'è."""
    raw = (text or "").strip().lower()
    t = _normalize(raw).replace("ì", "i")
    if _ABSOLUTE.search(t):
        return None
    plus = _PLUS.search(raw) and not re.search(r"\bpiù\s+presto\b", raw)
    minus = _MINUS.search(raw)
    if bool(plus) == bool(minus):
        return None
    secs = parse_duration(t)
    if not secs:
        return None
    return secs if plus else -secs


_WEEKDAYS = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]


def _clock(t: str) -> tuple[int, int] | None:
    """Orario detto a voce («18», «18:30», «6 e mezza», «le sette e un quarto»)."""
    if re.search(r"\bmezzogiorno\b", t):
        return 12, 0
    if re.search(r"\bmezzanotte\b", t):
        return 0, 0
    m = re.search(r"\b(?:alle|all|le|ore|per le)\s+([\w.:]+)(.*)", t)
    if not m:
        return None
    first, rest = m.group(1), m.group(2)
    hm = re.fullmatch(r"(\d{1,2})[.:](\d{2})", first)
    if hm:
        return int(hm.group(1)) % 24, int(hm.group(2))
    h = word_number(first) if not first.isdigit() else int(first)
    if h is None or h > 24:
        return None
    minute = 0
    r = rest.split()
    if r and r[0] == "e" and len(r) > 1:
        if r[1] in ("mezza", "mezzo"):
            minute = 30
        elif r[1] == "quarto" or (r[1] == "un" and len(r) > 2 and r[2] == "quarto"):
            minute = 15
        elif r[1] == "tre" and len(r) > 2 and r[2] == "quarti":
            minute = 45
        else:
            n = word_number(r[1])
            if n is not None and n < 60:
                minute = n
    elif r and r[0] == "meno" and len(r) > 1:
        sub = 15 if r[1] in ("un", "quarto") else (word_number(r[1]) or 0)
        h, minute = (h - 1) % 24, 60 - sub
    return h % 24, minute


def sposta(when: datetime.datetime, secondi: float) -> datetime.datetime:
    """`when` più `secondi` di tempo **reale** (03/10, ora legale). Con i datetime senza
    fuso `when + timedelta` somma i minuti dell'orologio: il 25/10/2026 alle 02:50 (ora
    legale) «tra 20 minuti» scadeva dopo 80 minuti veri, il 29/03 alle 01:30 «tra 2 ore»
    dopo una sola. Sull'epoch il conto è giusto, e fromtimestamp rimette l'ora locale."""
    return datetime.datetime.fromtimestamp(when.timestamp() + secondi)


def parse_when(text: str, now: datetime.datetime | None = None) -> datetime.datetime | None:
    """Istante detto a voce («tra 20 minuti», «alle 18», «domani alle 9», «lunedì alle
    10», «stasera alle 8») → datetime. Un orario ambiguo («alle 6») è il primo nel futuro,
    anche di pomeriggio."""
    now = now or datetime.datetime.now()
    t = _normalize(text).replace("ì", "i")
    if re.search(r"\b(tra|fra)\b", t):
        secs = parse_duration(t[re.search(r"\b(tra|fra)\b", t).start():])
        return sposta(now, secs) if secs else None          # tempo reale (ora legale)

    day = now.date()
    explicit_day = False
    if "dopodomani" in t:
        day, explicit_day = day + datetime.timedelta(days=2), True
    elif "domani" in t:
        day, explicit_day = day + datetime.timedelta(days=1), True
    else:
        for i, name in enumerate(_WEEKDAYS):
            if re.search(rf"\b{name}\b", t):
                ahead = (i - now.weekday()) % 7 or 7
                day, explicit_day = day + datetime.timedelta(days=ahead), True
                break
    evening = re.search(r"\b(stasera|sera|pomeriggio|stanotte)\b", t)
    morning = re.search(r"\b(stamattina|mattina|mattino)\b", t)

    clock = _clock(t)
    if clock is None:
        if evening:
            clock = (20, 0) if "sera" in evening.group(0) else (15, 0)
        elif morning:
            clock = (9, 0)
        else:
            return None
    h, m = clock
    if evening and h < 12:
        h += 12
    when = datetime.datetime.combine(day, datetime.time(h, m))
    if not explicit_day and not morning and when <= now:
        if h < 12 and not evening and when + datetime.timedelta(hours=12) > now:
            when += datetime.timedelta(hours=12)       # «alle 6» alle 14 → le 18
        else:
            when += datetime.timedelta(days=1)
    return when


def parse_day_range(text: str, now: datetime.datetime | None = None
                    ) -> tuple[datetime.datetime, datetime.datetime, str]:
    """Giorno o intervallo detto a voce → (inizio, fine, come dirlo), per «cosa ho…?».

    «oggi», «domani», «dopodomani», un giorno della settimana (il prossimo, oggi
    compreso: «cosa ho martedì?» detto di martedì vale oggi), «questa settimana»
    (fino a domenica), «la prossima settimana» (da lunedì a domenica). Vuoto o non
    capito → i prossimi 7 giorni.
    """
    now = now or datetime.datetime.now()
    t = _normalize(text or "").replace("ì", "i")
    midnight = datetime.datetime.combine(now.date(), datetime.time())
    day = datetime.timedelta(days=1)

    def whole(d: datetime.datetime, label: str):
        # di oggi conta solo ciò che resta da qui in avanti
        return max(d, now) if d.date() == now.date() else d, d + day, label

    if re.search(r"\b(prossima settimana|settimana prossima)\b", t):
        start = midnight + (7 - now.weekday()) * day
        return start, start + 7 * day, "la prossima settimana"
    if re.search(r"\b(questa settimana|in settimana)\b", t):
        return now, midnight + (7 - now.weekday()) * day, "questa settimana"
    if "dopodomani" in t:
        return whole(midnight + 2 * day, "dopodomani")
    if "domani" in t:
        return whole(midnight + day, "domani")
    if re.search(r"\b(oggi|stasera|stamattina|stanotte)\b", t):
        return whole(midnight, "oggi")
    for i, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            ahead = (i - now.weekday()) % 7
            label = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato",
                     "domenica"][i]
            return whole(midnight + ahead * day, "oggi" if ahead == 0 else label)
    return now, now + 7 * day, "nei prossimi 7 giorni"


def _month_start(year: int, month: int) -> datetime.datetime:
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return datetime.datetime(year, month, 1)


def parse_past_range(text: str, now: datetime.datetime | None = None
                     ) -> tuple[datetime.datetime | None, datetime.datetime | None, str]:
    """Periodo passato detto a voce → (dal, al, come dirlo), per cercare file («il PDF
    della settimana scorsa»). `al` None = fino a adesso; (None, None, "") = nessun
    filtro, anche quando il periodo non si capisce: meglio cercare in tutto che nel
    periodo sbagliato.

    parse_day_range guarda avanti (appuntamenti); qui si guarda indietro: «lunedì» è
    l'ultimo lunedì (oggi compreso), «agosto» l'ultimo agosto.
    """
    now = now or datetime.datetime.now()
    t = _normalize(text or "").replace("ì", "i")
    if not t.strip():
        return None, None, ""
    midnight = datetime.datetime.combine(now.date(), datetime.time())
    day = datetime.timedelta(days=1)
    monday = midnight - now.weekday() * day
    this_month = _month_start(now.year, now.month)

    if re.search(r"\b(l'?altro ?ieri|altroieri)\b", t):
        return midnight - 2 * day, midnight - day, "l'altro ieri"
    if re.search(r"\bieri\b", t):
        return midnight - day, midnight, "ieri"
    if re.search(r"\b(oggi|stamattina|stamani)\b", t):
        return midnight, None, "oggi"
    m = re.search(r"\b(\w+)\s+(giorn[oi]|settiman[ae]|mes[ei])\s+fa\b", t)
    if m and _num(m.group(1)):
        n = int(_num(m.group(1)))
        if m.group(2).startswith("giorn"):
            start = midnight - n * day
            return start, start + day, f"{n} giorni fa" if n > 1 else "ieri"
        if m.group(2).startswith("settiman"):
            start = monday - 7 * n * day
            return start, start + 7 * day, f"{n} settimane fa" if n > 1 else "la settimana scorsa"
        start = _month_start(now.year, now.month - n)
        return start, _month_start(now.year, now.month - n + 1), f"{n} mesi fa"
    m = re.search(r"\bultim[ieao]\s+(\w+)?\s*(giorn[oi]|settiman[ae]|mes[ei]|ann[oi])\b", t)
    if m:
        n = int(_num(m.group(1)) or 1) if m.group(1) else (7 if m.group(2) == "giorni" else 1)
        span = {"g": 1, "s": 7, "m": 30, "a": 365}[m.group(2)[0]] * n
        return now - span * day, None, f"negli ultimi {span} giorni" if span > 1 else "oggi"
    if re.search(r"\b(settimana scorsa|scorsa settimana|settimana passata)\b", t):
        return monday - 7 * day, monday, "la settimana scorsa"
    if re.search(r"\b(questa settimana|in settimana)\b", t):
        return monday, None, "questa settimana"
    if re.search(r"\b(mese scorso|scorso mese|mese passato)\b", t):
        return _month_start(now.year, now.month - 1), this_month, "il mese scorso"
    if re.search(r"\bquesto mese\b", t):
        return this_month, None, "questo mese"
    if re.search(r"\b(anno scorso|scorso anno|anno passato)\b", t):
        return datetime.datetime(now.year - 1, 1, 1), datetime.datetime(now.year, 1, 1), \
            "l'anno scorso"
    if re.search(r"\b(quest'?anno)\b", t):
        return datetime.datetime(now.year, 1, 1), None, "quest'anno"
    if re.search(r"\b(recente|recenti|ultimamente|di recente)\b", t):
        return now - 7 * day, None, "negli ultimi 7 giorni"
    for i, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            back = (now.weekday() - i) % 7
            if back == 0 and re.search(r"\bscors[oa]\b", t):
                back = 7                                # «lunedì scorso» detto di lunedì
            start = midnight - back * day
            label = "oggi" if back == 0 else ["lunedì", "martedì", "mercoledì", "giovedì",
                                              "venerdì", "sabato", "domenica"][i]
            return start, start + day, label
    for i, name in enumerate(MESI, 1):
        if re.search(rf"\b{name}\b", t):
            year = now.year if i <= now.month else now.year - 1
            return (_month_start(year, i), _month_start(year, i + 1),
                    f"{'ad' if name[0] in 'aeiou' else 'a'} {name}")
    return None, None, ""


def say_duration(seconds: int) -> str:
    """Secondi → «1 ora e 15 minuti», per la conferma a voce."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} {'ora' if h == 1 else 'ore'}")
    if m:
        parts.append(f"{m} {'minuto' if m == 1 else 'minuti'}")
    if s and not h:
        parts.append(f"{s} {'secondo' if s == 1 else 'secondi'}")
    return " e ".join(parts) or "0 secondi"


def say_when(when: datetime.datetime, now: datetime.datetime | None = None) -> str:
    """Istante → «oggi alle 18:30», «domani alle 9:00», «lunedì alle 10:00»."""
    now = now or datetime.datetime.now()
    delta = (when.date() - now.date()).days
    day = {0: "oggi", 1: "domani", 2: "dopodomani"}.get(delta)
    if day is None:
        day = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato",
               "domenica"][when.weekday()] + (f" {when.day}" if delta > 6 else "")
    # «alle 9», «alle 18 e 30»: «09:00» la voce lo leggerebbe male
    clock = f"{when.hour}" + (f" e {when.minute}" if when.minute else "")
    return f"{day} alle {clock}"


# ─────────────────────────────── DATE (05/10 sera) ───────────────────────────────
# «Quanti anni ho?» con la nascita il 4/7/1977: il 26B sulla DGX chiamava
# calcola('2026-07-04-1977-07-04') (errore: zeri iniziali) e poi 2026-1977 = 49, mentre il
# 05/10/2026 gli anni compiuti erano 48. I conti con le date li fa il programma (tool
# data_calcola): il modello passa le date come dette.
_FESTE = {"natale": (12, 25), "santo stefano": (12, 26), "capodanno": (1, 1),
          "san silvestro": (12, 31), "ferragosto": (8, 15), "epifania": (1, 6),
          "befana": (1, 6), "san valentino": (2, 14), "festa della repubblica": (6, 2),
          "festa dei lavoratori": (5, 1), "festa della liberazione": (4, 25),
          "ognissanti": (11, 1), "halloween": (10, 31)}
GIORNI_SETTIMANA = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato",
                     "domenica"]


def _anno(tok: str, now: datetime.date) -> int | None:
    if not tok.isdigit():
        return None
    a = int(tok)
    if len(tok) == 2:                          # «4/7/77»: il secolo che non è nel futuro
        a += 2000 if 2000 + a <= now.year else 1900
    return a if 1 <= a <= 9999 else None


def parse_date(text: str, now: datetime.date | datetime.datetime | None = None
               ) -> tuple[datetime.date, bool] | None:
    """Data detta o scritta → (data, anno detto). «4 luglio 1977», «il 4 luglio del 1977»,
    «1° maggio», «primo maggio», «04/07/1977», «4.7.77», «1977-07-04», «25 dicembre»,
    «Natale», «oggi», «domani», «ieri», «dopodomani». Senza anno vale quello di adesso
    (chi la usa decide se andare all'anno dopo: `prossima`). Non capita → None."""
    now = now or datetime.date.today()
    if isinstance(now, datetime.datetime):
        now = now.date()
    t = (text or "").lower().strip().replace("’", "'").replace("°", "")
    t = re.sub(r"\s+", " ", t)
    rel = {"oggi": 0, "domani": 1, "dopodomani": 2, "ieri": -1, "l'altro ieri": -2,
           "altroieri": -2}
    if t.strip(" .") in rel:
        return now + datetime.timedelta(days=rel[t.strip(" .")]), True
    try:
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)              # ISO
        if m:
            return datetime.date(int(m[1]), int(m[2]), int(m[3])), True
        m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{4}|\d{2}))?\b", t)
        if m:
            a = _anno(m[3], now) if m[3] else now.year
            return (datetime.date(a, int(m[2]), int(m[1])), bool(m[3])) if a else None
        t2 = t.replace("primo ", "1 ")
        for nome, (mese, giorno) in _FESTE.items():
            if nome in t2:
                y = re.search(r"\b(\d{4})\b", t2)
                return (datetime.date(int(y[1]) if y else now.year, mese, giorno), bool(y))
        mesi = "|".join(MESI)
        m = re.search(rf"\b(\d{{1,2}}|[a-zé]+)\s+(?:di\s+)?({mesi})\b(?:\s+(?:del\s+|dell'\s*)?"
                      rf"(\d{{4}}|\d{{2}})\b)?", t2)
        if m:
            g = int(m[1]) if m[1].isdigit() else word_number(m[1])
            if not g:
                return None
            a = _anno(m[3], now) if m[3] else now.year
            if not a:
                return None
            return datetime.date(a, MESI.index(m[2]) + 1, g), bool(m[3])
    except ValueError:                         # «31 febbraio», mese 13
        return None
    return None


def prossima(d: datetime.date, now: datetime.date) -> datetime.date:
    """La prossima volta di una data senza anno (oggi compreso): «a Natale» il 26/12 è il
    Natale dell'anno dopo."""
    return d if d >= now else stesso_giorno(d, now.year + 1)


def stesso_giorno(d: datetime.date, anno: int) -> datetime.date:
    try:
        return d.replace(year=anno)
    except ValueError:                         # 29 febbraio in un anno non bisestile
        return datetime.date(anno, 3, 1)


def anni_compiuti(nascita: datetime.date, giorno: datetime.date) -> int:
    """Anni compiuti a `giorno`: il compleanno di quest'anno conta solo se è già passato
    (o è oggi)."""
    return giorno.year - nascita.year - ((giorno.month, giorno.day) < (nascita.month, nascita.day))


def say_date(d: datetime.date, now: datetime.date | None = None, anno: bool = True) -> str:
    """Data → «4 luglio 1977», «primo maggio»; senza l'anno se è quello di adesso e `anno` è
    False."""
    s = f"{'primo' if d.day == 1 else d.day} {MESI[d.month - 1]}"     # «primo maggio»
    return s + (f" {d.year}" if anno or (now and d.year != now.year) else "")
