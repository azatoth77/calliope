"""
Unità di misura dette a voce e lette dalle risposte (12/10/2026, materie calcolabili degli
esercizi: fisica e chimica; scelta documentata in docs/aree/minori.md).

Il problema: Piper legge con espeak-ng i simboli lettera per lettera («2,5 m/s» → «due virgola
cinque emme barra esse», «3 kg» → «tre kappagì», «m/s²» → «… esse due», «°C» → «gradi ci»),
mentre i decimali con la virgola li legge bene («due virgola cinque») e quelli col punto no
(«2.5» → «due punto cinque»). Misurato con il fonemizzatore di piper il 12/10. Quindi:

- **a voce le unità si scrivono per esteso**, in italiano, con il plurale giusto («1 metro»,
  «2,5 metri al secondo», «9,8 metri al secondo quadrato», «grammi per mole»), e i numeri in
  cifre con la **virgola** decimale (espeak li legge in italiano); gli esponenti sono parole
  («al quadrato», «cubo»), mai apici. `detta` e `misura_detta` per chi genera le frasi;
  `Pronuncia` (calliope/pronuncia.py) usa `SIMBOLI_DETTI` per i simboli scritti dopo un numero
  in qualunque frase che va a Piper (anche quelle del modello);
- **le risposte si leggono in tutte le forme** che Whisper può scrivere: simboli («m/s»,
  «km/h», «g/cm3», «m/s²»), nomi interi o storpiati («metri al secondi», «chilometri orari»,
  «chilometri allora», «kilogrammi», «chili», «giul»), numeri in cifre o in lettere, decimali
  con la virgola o detti («due virgola cinque», «zero virgola zero cinque»), «un chilo e
  mezzo». `leggi_misura` dà valore esatto (`Fraction`) e unità; `stessa_grandezza` e `in_si`
  servono al confronto (esatto, nessuna tolleranza: gli esercizi nascono con al più due
  decimali).

Solo libreria standard, nessuna regola sul significato della frase (principio 10): il modello
passa la risposta così come l'ha sentita, qui se ne leggono numero e unità.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

# Grandezze: esponenti di (lunghezza, massa, tempo, quantità di sostanza)
LUNGHEZZA = (1, 0, 0, 0)
MASSA = (0, 1, 0, 0)
TEMPO = (0, 0, 1, 0)
VELOCITA = (1, 0, -1, 0)
ACCELERAZIONE = (1, 0, -2, 0)
VOLUME = (3, 0, 0, 0)
DENSITA = (-3, 1, 0, 0)
FORZA = (1, 1, -2, 0)
ENERGIA = (2, 1, -2, 0)
POTENZA = (2, 1, -3, 0)
MOLI = (0, 0, 0, 1)
MASSA_MOLARE = (0, 1, 0, -1)
CONCENTRAZIONE = (-3, 0, 0, 1)

NOMI_GRANDEZZE = {LUNGHEZZA: "una lunghezza", MASSA: "una massa", TEMPO: "un tempo",
                  VELOCITA: "una velocità", ACCELERAZIONE: "un'accelerazione",
                  VOLUME: "un volume", DENSITA: "una densità", FORZA: "una forza",
                  ENERGIA: "un'energia o un lavoro", POTENZA: "una potenza",
                  MOLI: "una quantità di sostanza, in moli", MASSA_MOLARE: "una massa molare",
                  CONCENTRAZIONE: "una concentrazione"}


@dataclass(frozen=True)
class Unita:
    chiave: str            # il simbolo per la scheda e il registro («m/s»)
    singolare: str         # detto con 1 («metro al secondo»)
    plurale: str           # detto con ogni altro numero («metri al secondo»)
    grandezza: tuple
    fattore: Fraction      # verso le unità di base (m, kg, s, mol)
    alias: tuple = ()      # forme dette o scritte, già semplificate (`_semplice`)
    simboli: tuple = ()    # simboli brevi: valgono solo subito dopo un numero


F = Fraction
UNITA: dict[str, Unita] = {u.chiave: u for u in (
    Unita("m", "metro", "metri", LUNGHEZZA, F(1), ("metro", "metri"), ("m",)),
    Unita("km", "chilometro", "chilometri", LUNGHEZZA, F(1000),
          ("chilometro", "chilometri", "kilometro", "kilometri"), ("km",)),
    Unita("cm", "centimetro", "centimetri", LUNGHEZZA, F(1, 100),
          ("centimetro", "centimetri"), ("cm",)),
    Unita("mm", "millimetro", "millimetri", LUNGHEZZA, F(1, 1000),
          ("millimetro", "millimetri"), ("mm",)),
    Unita("g", "grammo", "grammi", MASSA, F(1, 1000), ("grammo", "grammi"), ("g", "gr")),
    Unita("kg", "chilogrammo", "chilogrammi", MASSA, F(1),
          ("chilogrammo", "chilogrammi", "kilogrammo", "kilogrammi", "chilo", "chili", "kilo",
           "kili"), ("kg",)),
    Unita("t", "tonnellata", "tonnellate", MASSA, F(1000), ("tonnellata", "tonnellate")),
    Unita("u", "unità di massa atomica", "unità di massa atomica", MASSA,
          F(1, 602214076000000000000000000),
          ("unita di massa atomica", "dalton"), ("u", "uma")),
    Unita("s", "secondo", "secondi", TEMPO, F(1), ("secondo", "secondi"), ("s", "sec")),
    Unita("min", "minuto", "minuti", TEMPO, F(60), ("minuto", "minuti"), ("min",)),
    Unita("h", "ora", "ore", TEMPO, F(3600), ("ora", "ore"), ("h",)),
    Unita("m/s", "metro al secondo", "metri al secondo", VELOCITA, F(1),
          ("metri al secondo", "metro al secondo", "metri al secondi", "metri per secondo",
           "metri su secondo", "metri secondo", "metri al sec"), ("m/s",)),
    Unita("km/h", "chilometro all'ora", "chilometri all'ora", VELOCITA, F(5, 18),
          ("chilometri all ora", "chilometro all ora", "chilometri allora", "chilometri l ora",
           "chilometri orari", "chilometro orario", "chilometri per ora", "chilometri ora",
           "kilometri all ora", "kilometri orari", "km all ora", "km orari", "km allora"),
          ("km/h", "kmh", "km h")),
    Unita("m/s²", "metro al secondo quadrato", "metri al secondo quadrato", ACCELERAZIONE, F(1),
          ("metri al secondo quadrato", "metri al secondo al quadrato", "metri al secondo quadro",
           "metro al secondo quadrato", "metri su secondo quadrato",
           "metri al secondo alla seconda", "metri per secondo quadrato"),
          ("m/s2", "m/s 2", "m/s^2", "m s2")),
    Unita("N/kg", "newton al chilogrammo", "newton al chilogrammo", ACCELERAZIONE, F(1),
          ("newton al chilogrammo", "newton al chilo", "newton per chilogrammo",
           "newton su chilogrammo"), ("n/kg",)),
    Unita("m³", "metro cubo", "metri cubi", VOLUME, F(1),
          ("metri cubi", "metro cubo", "metri cubici"), ("m3", "mc", "m 3")),
    Unita("L", "litro", "litri", VOLUME, F(1, 1000), ("litro", "litri"), ("l", "lt")),
    Unita("mL", "millilitro", "millilitri", VOLUME, F(1, 10**6),
          ("millilitro", "millilitri"), ("ml",)),
    Unita("cm³", "centimetro cubo", "centimetri cubi", VOLUME, F(1, 10**6),
          ("centimetri cubi", "centimetro cubo", "centimetri cubici"), ("cm3", "cc", "cm 3")),
    Unita("g/cm³", "grammo al centimetro cubo", "grammi al centimetro cubo", DENSITA, F(1000),
          ("grammi al centimetro cubo", "grammi per centimetro cubo", "grammi su centimetro cubo",
           "grammo al centimetro cubo", "grammi centimetro cubo", "grammi al centimetri cubi",
           "grammi al millilitro", "grammi per millilitro"),
          ("g/cm3", "g/cm 3", "g/ml", "gr/cm3")),
    Unita("kg/m³", "chilogrammo al metro cubo", "chilogrammi al metro cubo", DENSITA, F(1),
          ("chilogrammi al metro cubo", "chilogrammi per metro cubo", "chilogrammi su metro cubo",
           "chilogrammo al metro cubo", "chili al metro cubo", "kilogrammi al metro cubo"),
          ("kg/m3", "kg/m 3")),
    Unita("g/L", "grammo al litro", "grammi al litro", DENSITA, F(1),
          ("grammi al litro", "grammi per litro", "grammi su litro"), ("g/l",)),
    Unita("N", "newton", "newton", FORZA, F(1), ("newton", "niuton", "nuton", "niutone"), ("n",)),
    Unita("J", "joule", "joule", ENERGIA, F(1), ("joule", "joul", "giul", "giule", "jul"),
          ("j",)),
    Unita("kJ", "chilojoule", "chilojoule", ENERGIA, F(1000),
          ("chilojoule", "kilojoule", "chilo joule", "kilo joule"), ("kj",)),
    Unita("W", "watt", "watt", POTENZA, F(1), ("watt", "uatt", "uat", "vatt"), ("w",)),
    Unita("kW", "chilowatt", "chilowatt", POTENZA, F(1000),
          ("chilowatt", "kilowatt", "chilo watt"), ("kw",)),
    Unita("mol", "mole", "moli", MOLI, F(1), ("mole", "moli"), ("mol",)),
    Unita("g/mol", "grammo per mole", "grammi per mole", MASSA_MOLARE, F(1, 1000),
          ("grammi per mole", "grammi alla mole", "grammi su mole", "grammi a mole",
           "grammo per mole", "grammi mole", "grammi al mole"), ("g/mol",)),
    Unita("mol/L", "mole al litro", "moli al litro", CONCENTRAZIONE, F(1000),
          ("moli al litro", "moli per litro", "moli su litro", "mole al litro", "molare",
           "molari"), ("mol/l",)),
)}


def _semplice(testo: str) -> str:
    """Minuscole, senza accenti, apici come cifre, apostrofi e trattini come spazi."""
    t = str(testo or "").translate(str.maketrans("²³’`", "23''"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    t = t.replace("−", "-").replace("–", "-").replace("'", " ").replace("°", " gradi ")
    t = re.sub(r"\bmezz ora\b", "mezza ora", t)       # «mezz'ora»
    return re.sub(r"[ \t]+", " ", t)


def unita(chiave: str) -> Unita:
    return UNITA[chiave]


# ─────────────────────────── come si dice ───────────────────────────

def numero_detto(valore) -> str:
    """Un numero da dire: cifre con la virgola decimale («2,5», «0,05», «-3» → «meno 3»).
    Un valore con troppi decimali resta frazione («7 terzi»)."""
    f = Fraction(valore)
    segno = "meno " if f < 0 else ""
    f = abs(f)
    if f.denominator == 1:
        return f"{segno}{f.numerator}"
    for cifre in range(1, 7):
        if (f * 10**cifre).denominator == 1:
            intero, resto = divmod(f.numerator * 10**cifre // f.denominator, 10**cifre)
            return f"{segno}{intero},{str(resto).rjust(cifre, '0')}"
    from .esercizi.numeri import frazione_detta
    return segno + frazione_detta(f)


def numero_scritto(valore) -> str:
    """Per la scheda: come `numero_detto` ma con il segno meno («−3», «2,5»)."""
    s = numero_detto(valore)
    return "−" + s[5:] if s.startswith("meno ") else s


def detta(chiave: str, valore=2) -> str:
    """Il nome dell'unità accordato al numero: «metro» con 1, «metri» con ogni altro."""
    u = UNITA[chiave]
    return u.singolare if Fraction(valore) in (1, -1) else u.plurale


def misura_detta(valore, chiave: str) -> str:
    """«2,5 metri al secondo», «1 chilogrammo», «meno 3 metri al secondo»."""
    return f"{numero_detto(valore)} {detta(chiave, valore)}"


def misura_scritta(valore, chiave: str) -> str:
    """«2,5 m/s» per la scheda e il registro."""
    return f"{numero_scritto(valore)} {chiave}"


def decimali(valore) -> int | None:
    """Quanti decimali servono per scrivere il valore esatto (None se è periodico)."""
    f = Fraction(valore)
    for cifre in range(0, 7):
        if (f * 10**cifre).denominator == 1:
            return cifre
    return None


# Per la voce (calliope/pronuncia.py): simbolo scritto dopo un numero → parole (singolare,
# plurale). Solo simboli che in una frase dopo una cifra non possono voler dire altro: niente
# «h», «s», «t», «u» da soli (ore e secondi si scrivono per esteso), niente «G» maiuscola
# («5G», «3G» delle reti) e niente «K».
SIMBOLI_DETTI: dict[str, tuple[str, str]] = {
    "km/h": ("chilometro all'ora", "chilometri all'ora"),
    "m/s²": ("metro al secondo quadrato", "metri al secondo quadrato"),
    "m/s2": ("metro al secondo quadrato", "metri al secondo quadrato"),
    "m/s": ("metro al secondo", "metri al secondo"),
    "km/s": ("chilometro al secondo", "chilometri al secondo"),
    "g/cm³": ("grammo al centimetro cubo", "grammi al centimetro cubo"),
    "g/cm3": ("grammo al centimetro cubo", "grammi al centimetro cubo"),
    "kg/m³": ("chilogrammo al metro cubo", "chilogrammi al metro cubo"),
    "kg/m3": ("chilogrammo al metro cubo", "chilogrammi al metro cubo"),
    "g/mol": ("grammo per mole", "grammi per mole"),
    "mol/L": ("mole al litro", "moli al litro"),
    "mol/l": ("mole al litro", "moli al litro"),
    "N/kg": ("newton al chilogrammo", "newton al chilogrammo"),
    "g/L": ("grammo al litro", "grammi al litro"),
    "m²": ("metro quadrato", "metri quadrati"),
    "m³": ("metro cubo", "metri cubi"),
    "cm²": ("centimetro quadrato", "centimetri quadrati"),
    "cm³": ("centimetro cubo", "centimetri cubi"),
    "km²": ("chilometro quadrato", "chilometri quadrati"),
    "kWh": ("chilowattora", "chilowattora"),
    "kW": ("chilowatt", "chilowatt"),
    "kJ": ("chilojoule", "chilojoule"),
    "kg": ("chilogrammo", "chilogrammi"),
    "mg": ("milligrammo", "milligrammi"),
    "km": ("chilometro", "chilometri"),
    "cm": ("centimetro", "centimetri"),
    "mm": ("millimetro", "millimetri"),
    "ml": ("millilitro", "millilitri"),
    "mL": ("millilitro", "millilitri"),
    "mol": ("mole", "moli"),
    "°C": ("grado", "gradi"),
    "g": ("grammo", "grammi"),
    "m": ("metro", "metri"),
    "N": ("newton", "newton"),
    "J": ("joule", "joule"),
    "W": ("watt", "watt"),
    "Pa": ("pascal", "pascal"),
    "Hz": ("hertz", "hertz"),
}


# ─────────────────────────── come si legge una risposta ───────────────────────────

@dataclass
class Misura:
    valore: Fraction
    unita: str | None          # chiave di UNITA, o None se non detta
    letta: str                 # «2,5 m/s», per il registro e la scheda


def _regex_unita() -> re.Pattern:
    voci = []
    for u in UNITA.values():
        for a in u.alias:
            voci.append((a, u.chiave, False))
        for s in u.simboli:
            voci.append((s, u.chiave, True))
    voci.sort(key=lambda v: len(v[0]), reverse=True)
    _REGEX_VOCI.clear()
    parti = []
    for i, (a, chiave, simbolo) in enumerate(voci):
        _REGEX_VOCI[f"u{i}"] = (chiave, simbolo)
        corpo = r"\s*".join(re.escape(p) for p in a.split(" ")) if " " in a else re.escape(a)
        parti.append(f"(?P<u{i}>{corpo})")
    # Mai a metà parola; «secondo» seguito da «me», «te»… non è un'unità
    return re.compile(r"(?<![a-z])(?:" + "|".join(parti) + r")(?![a-z0-9])"
                      r"(?!\s+(?:me|te|lui|lei|noi|voi|loro)\b)")


_REGEX_VOCI: dict[str, tuple[str, bool]] = {}
_RE_UNITA = _regex_unita()


def trova_unita(testo: str) -> list[tuple[int, int, str]]:
    """Le unità nel testo già semplificato: (inizio, fine, chiave). Un simbolo breve («m»,
    «g», «s», «km/h») conta solo subito dopo una cifra o un numero in lettere."""
    out = []
    for m in _RE_UNITA.finditer(testo):
        nome = m.lastgroup
        chiave, simbolo = _REGEX_VOCI[nome]
        if simbolo:
            prima = testo[:m.start()].rstrip()
            if not prima or not (prima[-1].isdigit() or _finisce_con_numero(prima)):
                continue
        out.append((m.start(), m.end(), chiave))
    return out


def _finisce_con_numero(t: str) -> bool:
    from .esercizi.numeri import parola_numero
    m = re.search(r"([a-z]+)$", t)
    return bool(m and (parola_numero(m.group(1)) is not None or m.group(1) in ("mezzo", "mezza")))


def _prepara(testo: str) -> str:
    from .esercizi.numeri import prepara_cifre
    return prepara_cifre(_semplice(testo))


def leggi_misura(testo) -> Misura | None:
    """Il numero e l'unità di una risposta detta o scritta: «2,5 m/s», «due virgola cinque
    metri al secondo», «un chilo e mezzo», «diciotto grammi per mole», «36 chilometri
    orari». Con più numeri vale quello dopo «fa», «uguale», «viene»… come in
    `numeri.leggi_valore`, altrimenti il primo. L'unità è quella detta subito dopo il numero
    (None se non c'è). None se non c'è un numero."""
    from .esercizi.numeri import _DOPO, _token_numeri
    if isinstance(testo, (int, Fraction)):
        return Misura(Fraction(testo), None, numero_scritto(testo))
    t = _prepara(testo)
    spans = trova_unita(t)
    # Le unità si tolgono prima di leggere i numeri («cm3», «secondo» non sono numeri)
    m = list(t)
    for s, e, _ in spans:
        m[s:e] = " " * (e - s)
    mascherato = "".join(m)
    mascherato = re.sub(r"\b(un|una)'", r"\1 ", mascherato)
    numeri = _token_numeri(mascherato)
    if not numeri:
        return None
    scelto = numeri[0]
    dopo = list(_DOPO.finditer(mascherato))
    if dopo:
        seguenti = [n for n in numeri if n[0] >= dopo[-1].end()]
        if seguenti:
            scelto = seguenti[0]
    inizio, valore, fine = scelto
    # L'unità: dentro il numero («un metro e mezzo») o subito dopo, con in mezzo solo spazi o
    # una virgola, prima del numero seguente
    unita_detta = None
    for s, e, chiave in spans:
        if s < inizio:
            continue
        if s <= fine or re.fullmatch(r"[\s,]*", mascherato[fine:s]):
            unita_detta = chiave
            # «2 ore e mezza», «3 chili e mezzo»: il mezzo dopo l'unità
            if s > fine and re.match(r"\s+e\s+mezz[oa]\b", t[e:]):
                valore = Fraction(valore) + Fraction(1, 2)
        break
    letta = misura_scritta(valore, unita_detta) if unita_detta else numero_scritto(valore)
    return Misura(Fraction(valore), unita_detta, letta)


def in_si(valore, chiave: str) -> Fraction:
    """Il valore nelle unità di base (m, kg, s, mol): «36 km/h» → 10."""
    return Fraction(valore) * UNITA[chiave].fattore


def stessa_grandezza(a: str, b: str) -> bool:
    return UNITA[a].grandezza == UNITA[b].grandezza


def converti(valore, da: str, a: str) -> Fraction:
    if not stessa_grandezza(da, a):
        raise ValueError(f"{da} e {a} non misurano la stessa grandezza")
    return in_si(valore, da) / UNITA[a].fattore
