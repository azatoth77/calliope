"""
Numeri e unità di misura nelle risposte delle prove dello Studio (31/10, passo 8, issue #248,
decisione 0035 punto 40). Il vecchio `calliope/unita.py` degli esercizi è stato tolto col passo
4.0 (#279, «niente del vecchio»); qui c'è solo ciò che serve a leggere una risposta scritta o
trascritta e a confrontarla con quella attesa: il valore e l'unità, nella grandezza giusta.

- I numeri in cifre con la virgola o il punto decimale («2,5», «2.5»; «1.861» con le migliaia),
  in lettere fino a 2100 e le migliaia tonde («milleottocentosessantuno», «due virgola cinque»,
  «tre e mezzo», «meno quattro»).
- Le unità per nome o per simbolo dopo un numero: lunghezza, massa, tempo, velocità,
  accelerazione, area, volume, densità, forza, energia, potenza, moli, temperatura e
  percentuale. Un simbolo breve («m», «g», «s») vale solo subito dopo un numero.
- `leggi` dà i numeri trovati con l'unità detta subito dopo; `confronta` dice se una misura è
  quella attesa, con la tolleranza e la conversione nella stessa grandezza.

Solo libreria standard, nessuna regola sul significato della frase (principio 10): si leggono
numero e unità di una risposta che la persona ha dato a una domanda.
"""

from __future__ import annotations

import re
import unicodedata

# Grandezze: esponenti di (lunghezza, massa, tempo, quantità di sostanza, temperatura, %)
L, M, T, N, K, P = ((1, 0, 0, 0, 0, 0), (0, 1, 0, 0, 0, 0), (0, 0, 1, 0, 0, 0),
                    (0, 0, 0, 1, 0, 0), (0, 0, 0, 0, 1, 0), (0, 0, 0, 0, 0, 1))


def _g(*pezzi) -> tuple:
    out = [0] * 6
    for base, esp in pezzi:
        for i, x in enumerate(base):
            out[i] += x * esp
    return tuple(out)


VEL, ACC = _g((L, 1), (T, -1)), _g((L, 1), (T, -2))
AREA, VOL, DENS = _g((L, 2)), _g((L, 3)), _g((M, 1), (L, -3))
FORZA = _g((M, 1), (L, 1), (T, -2))
ENERGIA, POTENZA = _g((M, 1), (L, 2), (T, -2)), _g((M, 1), (L, 2), (T, -3))
MOLARE, CONC = _g((M, 1), (N, -1)), _g((N, 1), (L, -3))

# (chiave, grandezza, fattore verso la base, nomi, simboli)
_TABELLA = (
    ("m", L, 1.0, ("metro", "metri"), ("m",)),
    ("km", L, 1000.0, ("chilometro", "chilometri", "kilometro", "kilometri"), ("km",)),
    ("cm", L, 0.01, ("centimetro", "centimetri"), ("cm",)),
    ("mm", L, 0.001, ("millimetro", "millimetri"), ("mm",)),
    ("g", M, 0.001, ("grammo", "grammi"), ("g", "gr")),
    ("kg", M, 1.0, ("chilogrammo", "chilogrammi", "kilogrammo", "kilogrammi", "chilo", "chili"),
     ("kg",)),
    ("mg", M, 1e-6, ("milligrammo", "milligrammi"), ("mg",)),
    ("t", M, 1000.0, ("tonnellata", "tonnellate"), ()),
    ("s", T, 1.0, ("secondo", "secondi"), ("s", "sec")),
    ("min", T, 60.0, ("minuto", "minuti"), ("min",)),
    ("h", T, 3600.0, ("ora", "ore"), ("h",)),
    ("m/s", VEL, 1.0, ("metri al secondo", "metro al secondo", "metri al secondi",
                       "metri per secondo"), ("m/s",)),
    ("km/h", VEL, 1 / 3.6, ("chilometri all ora", "chilometro all ora", "chilometri orari",
                            "chilometri allora", "chilometri l ora", "km all ora", "km orari"),
     ("km/h", "kmh")),
    ("m/s2", ACC, 1.0, ("metri al secondo quadrato", "metri al secondo al quadrato",
                        "metro al secondo quadrato"), ("m/s2", "m/s^2")),
    ("m2", AREA, 1.0, ("metri quadrati", "metro quadrato", "metri quadri"), ("m2", "mq")),
    ("cm2", AREA, 1e-4, ("centimetri quadrati", "centimetro quadrato"), ("cm2",)),
    ("km2", AREA, 1e6, ("chilometri quadrati", "chilometro quadrato"), ("km2",)),
    ("m3", VOL, 1.0, ("metri cubi", "metro cubo"), ("m3", "mc")),
    ("cm3", VOL, 1e-6, ("centimetri cubi", "centimetro cubo"), ("cm3", "cc")),
    ("L", VOL, 0.001, ("litro", "litri"), ("l", "lt")),
    ("mL", VOL, 1e-6, ("millilitro", "millilitri"), ("ml",)),
    ("g/cm3", DENS, 1000.0, ("grammi al centimetro cubo", "grammi per centimetro cubo",
                             "grammi al millilitro"), ("g/cm3", "g/ml")),
    ("kg/m3", DENS, 1.0, ("chilogrammi al metro cubo", "chilogrammi per metro cubo"),
     ("kg/m3",)),
    ("N", FORZA, 1.0, ("newton", "niuton"), ("n",)),
    ("J", ENERGIA, 1.0, ("joule", "giul"), ("j",)),
    ("kJ", ENERGIA, 1000.0, ("chilojoule", "kilojoule"), ("kj",)),
    ("cal", ENERGIA, 4.184, ("caloria", "calorie"), ("cal",)),
    ("kcal", ENERGIA, 4184.0, ("chilocaloria", "chilocalorie"), ("kcal",)),
    ("W", POTENZA, 1.0, ("watt",), ("w",)),
    ("kW", POTENZA, 1000.0, ("chilowatt", "kilowatt"), ("kw",)),
    ("mol", N, 1.0, ("mole", "moli"), ("mol",)),
    ("g/mol", MOLARE, 0.001, ("grammi per mole", "grammi alla mole", "grammo per mole"),
     ("g/mol",)),
    ("mol/L", CONC, 1000.0, ("moli al litro", "moli per litro", "molare"), ("mol/l",)),
    ("°C", K, 1.0, ("gradi centigradi", "gradi celsius", "gradi", "grado"), ("°c", "c")),
    ("%", P, 1.0, ("per cento", "percento"), ("%",)),
)
UNITA = {c: (g, f) for c, g, f, _n, _s in _TABELLA}


def _semplice(testo) -> str:
    t = str(testo or "").translate(str.maketrans("²³’`−–", "23''--"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    t = t.replace("°c", " °c ").replace("%", " % ").replace("'", " ")
    return re.sub(r"[ \t]+", " ", t).strip()


def _voci():
    voci = []
    for c, _g_, _f, nomi, simboli in _TABELLA:
        voci += [(n, c, False) for n in nomi] + [(s, c, True) for s in simboli]
    voci.sort(key=lambda v: len(v[0]), reverse=True)
    return voci


_VOCI = _voci()


def _regex_unita() -> re.Pattern:
    parti = []
    for i, (a, _c, _s) in enumerate(_VOCI):
        corpo = r"\s+".join(re.escape(p) for p in a.split(" "))
        parti.append(f"(?P<u{i}>{corpo})")
    return re.compile(r"(?<![a-z0-9/])(?:" + "|".join(parti) + r")(?![a-z0-9/])")


_RE_U = _regex_unita()

# I numeri in lettere: 0–2100 e le migliaia tonde (gli anni, le misure di scuola)
_PAROLE: dict[str, int] = {}


def _parole() -> dict:
    if not _PAROLE:
        from ..numeri import in_lettere
        for n in range(0, 2101):
            _PAROLE[in_lettere(n).replace(" ", "")] = n
        for k in range(2, 1000):
            _PAROLE[in_lettere(k * 1000).replace(" ", "")] = k * 1000
        _PAROLE.update({"un": 1, "una": 1, "mezzo": 0.5, "mezza": 0.5})
    return _PAROLE


_NUM = re.compile(r"-?\d+(?:[.,]\d+)*")


def _cifre(tok: str) -> float | None:
    t = tok
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", t):          # «1.861», «12.000»
        t = t.replace(".", "")
    elif t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    elif t.count(",") > 1 or t.count(".") > 1:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _in_cifre(t: str) -> str:
    """I numeri in lettere diventano cifre; «X virgola Y», «X e mezzo», «meno X»."""
    pw = _parole()
    out = []
    for w in t.split(" "):
        out.append(str(pw[w]) if w in pw and w not in ("un", "una", "mezzo", "mezza") else w)
    t = " ".join(out)
    t = re.sub(r"(\d+) virgola ((?:\d+ )*\d+)",
               lambda m: m.group(1) + "." + m.group(2).replace(" ", ""), t)
    t = re.sub(r"\bmeno (\d)", r"-\1", t)
    return t


def leggi(testo) -> list[tuple[float, str | None]]:
    """I numeri della risposta, ognuno con l'unità detta subito dopo (o None)."""
    t = _in_cifre(_semplice(testo))
    unita = []
    for m in _RE_U.finditer(t):
        a, c, simbolo = _VOCI[int(m.lastgroup[1:])]
        if simbolo:
            prima = t[:m.start()].rstrip()
            if not prima or not prima[-1].isdigit():
                continue
        unita.append((m.start(), m.end(), c))
    out = []
    for m in _NUM.finditer(t):
        if any(s <= m.start() < e for s, e, _c in unita):
            continue                                  # «m3», «cm2» non sono numeri
        v = _cifre(m.group(0))
        if v is None:
            continue
        dopo = t[m.end():]
        if re.match(r"\s+e\s+mezz[oa]\b", dopo) or re.match(r"\s+e\s+0\.5\b", dopo):
            v += 0.5
        u = next((c for s, _e, c in unita if s >= m.end()
                  and re.fullmatch(r"[\s,]*(?:e\s+mezz[oa]\s*)?", t[m.end():s])), None)
        out.append((v, u))
    return out


def una_misura(testo) -> tuple[float, str | None] | None:
    """La misura di una risposta: l'unico numero (o lo stesso ripetuto); None se non c'è un
    numero o se ce ne sono di diversi («5 o 6»)."""
    nn = leggi(testo)
    if not nn:
        return None
    if len({round(v, 9) for v, _u in nn}) > 1:
        return None
    return next(((v, u) for v, u in nn if u), nn[0])


TOLLERANZA = 0.01      # relativa, 1 %


def confronta(detta: tuple[float, str | None], attesa: tuple[float, str | None]) -> str:
    """«giusto», «indizio» (il numero giusto senza l'unità attesa) o «sbagliato» (numero diverso
    o grandezza diversa). Un intero atteso e detto intero, senza conversione, va detto esatto;
    altrimenti vale la tolleranza dell'1 %."""
    v, u = detta
    va, ua = attesa
    # Un intero atteso e detto senza conversione va detto esatto (un anno, un conteggio)
    esatto = float(va).is_integer() and float(v).is_integer() and (not u or not ua or u == ua)
    if u and ua:
        gu, fu = UNITA[u]
        ga, fa = UNITA[ua]
        if gu != ga:
            return "sbagliato"
        v = v * fu / fa                               # la temperatura ha solo °C
    tol = 1e-9 if esatto else abs(va) * TOLLERANZA
    if abs(v - va) > tol + 1e-9:
        return "sbagliato"
    return "indizio" if ua and not u else "giusto"
