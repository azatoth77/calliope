"""
Numeri e frazioni detti a voce o scritti, per gli esercizi (08/10/2026).

Il ragazzo risponde a voce («cinquantasei», «tre quarti», «meno due», «x uguale 4», «uno
virgola cinque») o scrivendo («56», «3/4», «-2», «1,5»): qui la risposta diventa un valore
esatto (`Fraction`), che il codice confronta con quello calcolato. E al contrario: un valore o
una frazione come va detto («3 quarti», «un mezzo», «meno 2»).

Solo libreria standard. Niente regole sul significato della frase (principio 10): il modello
passa la risposta così come l'ha sentita, qui se ne legge il numero.
"""

from __future__ import annotations

import re
import unicodedata
from fractions import Fraction

_UNITA = {"zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4,
          "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
          "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15,
          "sedici": 16, "diciassette": 17, "diciotto": 18, "diciannove": 19}
_DECINE = {"venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50, "sessanta": 60,
           "settanta": 70, "ottanta": 80, "novanta": 90}
_PAROLE_UNITA = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto",
                 "nove", "dieci", "undici", "dodici", "tredici", "quattordici", "quindici",
                 "sedici", "diciassette", "diciotto", "diciannove"]
_PAROLE_DECINE = {v: k for k, v in _DECINE.items()}
# Denominatori con un nome proprio (gli altri: «-esimi»)
_DENOMINATORI = {"mezzo": 2, "mezzi": 2, "mezza": 2, "mezze": 2, "terzo": 3, "terzi": 3,
                 "terza": 3, "terze": 3, "quarto": 4, "quarti": 4, "quarta": 4, "quarte": 4,
                 "quinto": 5, "quinti": 5, "sesto": 6, "sesti": 6, "settimo": 7, "settimi": 7,
                 "ottavo": 8, "ottavi": 8, "nono": 9, "noni": 9, "decimo": 10, "decimi": 10}
_NOMI_DENOMINATORI = {2: ("mezzo", "mezzi"), 3: ("terzo", "terzi"), 4: ("quarto", "quarti"),
                      5: ("quinto", "quinti"), 6: ("sesto", "sesti"), 7: ("settimo", "settimi"),
                      8: ("ottavo", "ottavi"), 9: ("nono", "noni"), 10: ("decimo", "decimi")}
# Esponenti detti: «elevato alla terza», «alla quinta»
ORDINALI_F = {2: "seconda", 3: "terza", 4: "quarta", 5: "quinta", 6: "sesta", 7: "settima",
              8: "ottava", 9: "nona", 10: "decima"}
_ORDINALI_F_INV = {v: k for k, v in ORDINALI_F.items()} | {"prima": 1}


def _semplice(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    t = t.replace("’", "'").replace("−", "-").replace("–", "-")
    return t


def _fino_a_99(w: str) -> int | None:
    if w in _UNITA:
        return _UNITA[w]
    for t, v in _DECINE.items():
        for pref in (t, t[:-1]):            # «vent-uno», «trent-otto»
            if w.startswith(pref):
                resto = w[len(pref):]
                if not resto:
                    return v if pref == t else None
                if resto in _UNITA and 0 < _UNITA[resto] < 10:
                    return v + _UNITA[resto]
    return None


def parola_numero(w: str) -> int | None:
    """Un numero intero scritto in lettere, da zero a 999 999 («ventitré», «centotto»,
    «milleduecentotrenta», «tremila»). None se non è un numero."""
    w = _semplice(w).replace(" ", "").replace("-", "")
    if not w or not w.isalpha():
        return None
    if w in ("mille",):
        return 1000
    if "mila" in w:
        sx, _, dx = w.partition("mila")
        a = parola_numero(sx)
        if a is None or a < 2:
            return None
        b = parola_numero(dx) if dx else 0
        return None if b is None or b >= 1000 else a * 1000 + b
    if w.startswith("mille"):
        b = parola_numero(w[5:])
        return None if b is None or b >= 1000 else 1000 + b
    i = w.find("cent")
    if i >= 0:
        sx, dx = w[:i], w[i + 4:]
        if dx.startswith("o"):
            dx = dx[1:]
        elif not dx.startswith("tt"):
            return None
        a = 1 if not sx else _fino_a_99(sx)
        if a is None or not 1 <= a <= 9:
            return None
        if dx.startswith("tt"):           # «centotto», «centottanta»
            dx = "o" + dx
        b = _fino_a_99(dx) if dx else 0
        return None if b is None else a * 100 + b
    return _fino_a_99(w)


def in_lettere(n: int) -> str:
    """Un intero da 0 a 999 999 in lettere («ventitré» senza accento: «ventitre»)."""
    n = int(n)
    if n < 0:
        return "meno " + in_lettere(-n)
    if n < 20:
        return _PAROLE_UNITA[n]
    if n < 100:
        d, u = divmod(n, 10)
        dec = _PAROLE_DECINE[d * 10]
        if u in (1, 8):
            dec = dec[:-1]
        return dec + (_PAROLE_UNITA[u] if u else "")
    if n < 1000:
        c, r = divmod(n, 100)
        cento = "cento" if c == 1 else _PAROLE_UNITA[c] + "cento"
        if r and in_lettere(r).startswith("o"):
            cento = cento[:-1]               # «centotto», «duecentottanta»
        return cento + (in_lettere(r) if r else "")
    m, r = divmod(n, 1000)
    mila = "mille" if m == 1 else in_lettere(m) + "mila"
    return mila + (in_lettere(r) if r else "")


def denominatore_parola(d: int, plurale: bool) -> str:
    """«quarti», «terzo», «dodicesimi»."""
    if d in _NOMI_DENOMINATORI:
        return _NOMI_DENOMINATORI[d][1 if plurale else 0]
    base = in_lettere(d)
    if base.endswith("tre") and d > 10:
        stem = base                              # «ventitreesimo»
    else:
        stem = base[:-1] if base[-1] in "aeio" else base
    return stem + ("esimi" if plurale else "esimo")


def _denominatore_da_parola(w: str) -> int | None:
    w = _semplice(w)
    if w in _DENOMINATORI:
        return _DENOMINATORI[w]
    m = re.fullmatch(r"([a-z]+?)esim[oiae]", w)
    if not m:
        return None
    stem = m.group(1)
    for coda in ("", "e", "i", "o", "a"):
        n = parola_numero(stem + coda)
        if n is not None and n > 10:
            return n
    return None


def frazione_detta(valore, articolo: bool = True) -> str:
    """Un valore come va detto: «3 quarti», «un mezzo», «meno 2», «5», «1,5» no (le
    frazioni restano frazioni)."""
    f = Fraction(valore)
    if f.denominator == 1:
        return ("meno " if f < 0 else "") + str(abs(f.numerator))
    segno = "meno " if f < 0 else ""
    n, d = abs(f.numerator), f.denominator
    if n == 1:
        return segno + ("un " if articolo else "1 ") + denominatore_parola(d, False)
    return f"{segno}{n} {denominatore_parola(d, True)}"


def frazione_scritta(valore) -> str:
    f = Fraction(valore)
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def numero_scritto(valore) -> str:
    """Per la scheda: «3/4», «-2», «1,5» se il valore ha un decimale finito breve."""
    return frazione_scritta(valore)


# ─────────────────────────── lettura della risposta ───────────────────────────

# Dopo uno di questi segni conta il numero che segue: «7 per 8 fa 56», «x uguale 4»
_DOPO = re.compile(r"(?:=|\bfa\b|\buguale(?:\s+a)?\b|\bvale\b|\bviene\b|\brisultato\b|"
                   r"\brisposta\b|\bsoluzione\b)")


def _token_numeri(t: str) -> list[tuple[int, Fraction, int]]:
    """I numeri di un testo già semplificato: (inizio, valore, fine)."""
    out = []
    # Cifre: «-3», «3/4», «3 / 4», «1,5», «1.5», «2 su 3» con le cifre
    for m in re.finditer(r"(?<![\w.,])(-\s*)?(\d+(?:[.,]\d+)?)(?:\s*(?:/|:|\bsu\b|\bfratto\b)\s*(\d+))?", t):
        try:
            n = Fraction(m.group(2).replace(",", "."))
            if m.group(3):
                den = int(m.group(3))
                if den == 0:
                    continue
                n = n / den
            # «3 quarti», «5 dodicesimi» con il numeratore in cifre
            dopo = t[m.end():].lstrip()
            pw = re.match(r"([a-z]+)", dopo)
            if not m.group(3) and pw and n.denominator == 1:
                den = _denominatore_da_parola(pw.group(1))
                if den:
                    n = n / den
                    fine = m.end() + (len(t[m.end():]) - len(dopo)) + pw.end()
                    out.append((m.start(), -n if m.group(1) else n, fine))
                    continue
            out.append((m.start(), -n if m.group(1) else n, m.end()))
        except (ValueError, ZeroDivisionError):
            continue
    if out:
        # «meno 3» con le cifre
        res = []
        for s, v, e in out:
            if re.search(r"\bmeno\s*$", t[:s]) and v > 0:
                v = -v
            res.append((s, v, e))
        return res
    # In lettere: parole consecutive
    parole = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[a-z']+", t)]
    i = 0
    while i < len(parole):
        s, e, w = parole[i]
        w = w.strip("'")
        segno = 1
        j = i
        if w == "meno" and i + 1 < len(parole):
            segno, j = -1, i + 1
        sj, ej, wj = parole[j]
        wj = wj.strip("'")
        n = parola_numero(wj) if wj not in ("mezzo", "mezza") else None
        if wj in ("mezzo", "mezza") and (j == 0 or parole[j - 1][2] not in ("un", "una")):
            out.append((s, Fraction(segno, 2), ej))
            i = j + 1
            continue
        if n is None:
            i += 1
            continue
        valore, fine, k = Fraction(n), ej, j + 1
        # «uno virgola cinque», «zero virgola zero cinque», «due virgola venticinque»
        if k + 1 < len(parole) and parole[k][2] == "virgola":
            cifre, k2 = _decimali_detti([w for _, _, w in parole], k + 1)
            if cifre:
                valore = Fraction(f"{n}.{cifre}")
                fine, k = parole[k2 - 1][1], k2
        # «tre quarti», «due su tre», «due fratto tre», «tre mezzi»
        elif k < len(parole):
            den = _denominatore_da_parola(parole[k][2])
            if den:
                valore, fine, k = Fraction(n, den), parole[k][1], k + 1
            elif parole[k][2] in ("su", "fratto", "diviso") and k + 1 < len(parole):
                d = parola_numero(parole[k + 1][2])
                if d:
                    valore, fine, k = Fraction(n, d), parole[k + 1][1], k + 2
        # «e mezzo»: «dieci e mezzo»
        if k + 1 < len(parole) and parole[k][2] == "e" and parole[k + 1][2] in ("mezzo", "mezza"):
            valore, fine, k = valore + Fraction(1, 2), parole[k + 1][1], k + 2
        out.append((s, segno * valore, fine))
        i = k
    return out


def _decimali_detti(parole: list[str], k: int) -> tuple[str, int]:
    """Le cifre dopo «virgola», dette: «cinque» → "5", «zero cinque» → "05", «venticinque»
    → "25", «zero zero tre» → "003". Gli zeri davanti si dicono uno a uno, poi una cifra o un
    numero fino a 99. ("", k) se non c'è niente."""
    cifre = ""
    while k < len(parole) and parole[k] == "zero":
        cifre += "0"
        k += 1
    if k < len(parole):
        n = parola_numero(parole[k])
        if n is not None and 0 < n < 100:
            return cifre + str(n), k + 1
    return cifre, k


def prepara_cifre(t: str) -> str:
    """Su un testo già semplificato: «2 virgola 5» → «2,5»; le migliaia col punto
    all'italiana («1.000», «12.500» → «1000», «12500»; mai «0.125» né «2.5»)."""
    t = re.sub(r"(\d)\s*virgola\s*(\d)", r"\1,\2", t)
    return re.sub(r"(?<![\d.,])([1-9]\d{0,2})((?:\.\d{3})+)(?![\d.,])",
                  lambda m: m.group(1) + m.group(2).replace(".", ""), t)


def leggi_valore(testo) -> Fraction | None:
    """Il numero di una risposta detta o scritta, esatto. Con più numeri, quello dopo «fa»,
    «uguale», «=», «è»… se c'è; altrimenti il primo («56, credo» → 56). None se non c'è."""
    if isinstance(testo, (int, Fraction)):
        return Fraction(testo)
    if isinstance(testo, float):
        return Fraction(str(testo))
    t = prepara_cifre(_semplice(testo))
    t = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1 per \2", t)
    t = re.sub(r"\bx\s*(?==|uguale)", " ", t)         # «x = 4»: la x non è un numero
    t = re.sub(r"\b(un|una)'", r"\1 ", t)
    numeri = _token_numeri(t)
    if not numeri:
        return None
    dopo = list(_DOPO.finditer(t))
    if dopo:
        ultimo = dopo[-1].end()
        seguenti = [v for s, v, _ in numeri if s >= ultimo]
        if seguenti:
            return seguenti[0]
    return numeri[0][1]


# ─────────────────────────── il numero detto davvero ───────────────────────────
# Il 12/10 sulla DGX (26B) il modello passava a esercizi(rispondi) il numero che si aspettava,
# non quello sentito: «Suttanto salida» → 76, «Pantano a bit» → 79, segnati giusti perché il
# modello conosceva la domanda. Qui si guarda se il valore passato si ricava dalla frase della
# persona (cifre o parole di numero, con storpiature piccole); se no il codice non giudica e
# chiede di ripetere (regola `esercizi_numero_non_detto`). È una regola su ciò che il modello non
# vede bene (la trascrizione), non sul significato (principio 10).

# Tutti i numeri fino a 999 in lettere (con gli accenti tolti: «ventitre»), per il confronto
# tollerante delle parole storpiate da Whisper
_IN_LETTERE: dict[str, int] = {}


def _lettere() -> dict[str, int]:
    if not _IN_LETTERE:
        for n in range(0, 1000):
            _IN_LETTERE[in_lettere(n)] = n
        _IN_LETTERE.update({"un": 1, "una": 1, "mille": 1000})
    return _IN_LETTERE


def _distanza(a: str, b: str, tetto: int = 2) -> int:
    """Distanza di modifica (Levenshtein), fermata oltre `tetto`."""
    if abs(len(a) - len(b)) > tetto:
        return tetto + 1
    prima = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        ora = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            ora[j] = min(prima[j] + 1, ora[j - 1] + 1, prima[j - 1] + (ca != cb))
        if min(ora) > tetto:
            return tetto + 1
        prima = ora
    return prima[-1]


def parola_tollerante(w: str) -> int | None:
    """Il numero di una parola, anche storpiata di una lettera («sedeci» → 16, «prenta» → 30),
    se la parola più vicina è una sola. Parole corte (meno di 5 lettere) solo esatte: «sei»,
    «tre», «fa» non si confondono."""
    w = _semplice(w).strip("'")
    n = parola_numero(w)
    if n is not None:
        return n
    if len(w) < 5 or not w.isalpha():
        return None
    vicine = {v for k, v in _lettere().items() if abs(len(k) - len(w)) <= 1
              and _distanza(w, k, 1) <= 1}
    return vicine.pop() if len(vicine) == 1 else None


def numeri_detti(testo) -> set[Fraction]:
    """Tutti i valori che si possono leggere in una frase detta: i numeri in cifre, quelli in
    lettere (anche separati: «trenta due» → 30, 2 e 32), con le storpiature di una lettera,
    frazioni e decimali come in `leggi_valore`. Largo di proposito: serve a dire se un valore
    *si ricava* dalla frase, non quale sia la risposta."""
    t = prepara_cifre(_semplice(testo))
    t = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1 per \2", t)
    t = re.sub(r"\b(un|una)'", r"\1 ", t)
    out: set[Fraction] = set()
    for _, v, _ in _token_numeri(t):
        out.add(v)
        out.add(abs(v))
    # Le parole, anche con le cifre nella stessa frase («6 per 8, quarantotto»)
    solo_parole = re.sub(r"\d+(?:[.,]\d+)?", " ", t)
    for _, v, _ in _token_numeri(solo_parole):
        out.add(v)
        out.add(abs(v))
    # Parole storpiate, una per una, e le coppie decina + unità o centinaia + resto
    parole = re.findall(r"[a-z']+", solo_parole)
    valori = [parola_tollerante(w) for w in parole]
    for i, v in enumerate(valori):
        if v is None:
            continue
        out.add(Fraction(v))
        if i + 1 < len(valori) and valori[i + 1] is not None:
            u = valori[i + 1]
            if v % 10 == 0 and v % 100 >= 20 and 0 < u < 10:        # «centoventi tre»
                out.add(Fraction(v + u))
            if v % 100 == 0 and v >= 100 and 0 < u < 100:            # «trecento dodici»
                out.add(Fraction(v + u))
            if v % 1000 == 0 and v >= 1000 and 0 < u < 1000:         # «mille duecento»
                out.add(Fraction(v + u))
    return out


def valore_detto(valore, testo) -> bool:
    """Il valore passato dal modello si ricava dalla frase della persona? Con una frase vuota
    (la scheda, le prove senza frase) non si controlla: True."""
    if not str(testo or "").strip():
        return True
    try:
        v = Fraction(valore)
    except (TypeError, ValueError):
        return True
    detti = numeri_detti(testo)
    return v in detti or (v < 0 and -v in detti and "meno" in _semplice(testo))


def leggi_frazione_scritta(testo) -> tuple[int, int] | None:
    """Numeratore e denominatore come detti (per «si può semplificare ancora»): «6/8» →
    (6, 8), «sei ottavi» → (6, 8); un intero → (n, 1); None se non c'è."""
    t = _semplice(testo)
    m = re.search(r"(-?\d+)\s*(?:/|\bsu\b|\bfratto\b)\s*(\d+)", t)
    if m and int(m.group(2)):
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s+([a-z]+)", t)
    if m and _denominatore_da_parola(m.group(2)):
        return int(m.group(1)), _denominatore_da_parola(m.group(2))
    parole = re.findall(r"[a-z]+", re.sub(r"\b(un|una)'", r"\1 ", t))
    for i, w in enumerate(parole):
        n = parola_numero(w)
        if n is None or i + 1 >= len(parole):
            continue
        den = _denominatore_da_parola(parole[i + 1])
        if den:
            return n, den
        if parole[i + 1] in ("su", "fratto") and i + 2 < len(parole):
            d = parola_numero(parole[i + 2])
            if d:
                return n, d
    v = leggi_valore(testo)
    if v is not None and v.denominator == 1:
        return int(v), 1
    return None
