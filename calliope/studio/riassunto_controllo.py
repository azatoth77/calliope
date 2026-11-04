"""
Il controllo del copione del riassunto (04/11/2026, issue #386, epic #251, decisione 0035 punto 57). Solo
codice, nessun modello.

**Ogni frase detta si appoggia a una frase della pagina.** Le pagine arrivano al modello numerate per frase
(`Materiale`: «P1.3»), già ripulite: senza le pagine con «ISTRUZIONI: sì» e senza le frasi che non si dicono
mai. Ogni frase del copione cita da quali viene, al più `FONTI_MAX` e della stessa pagina, e **il codice
guarda solo quelle** (`controlla`):
- i **valori** con la loro unità: numeri in cifre o in lettere («mille metri» vale «1 km»; grandezze diverse
  no), anni, mesi, ore (`_TEMPI`), «a.C.» e «d.C.», giorno e mese come coppia, ordinali e romani, frazioni,
  formule e sigle uguali, simboli brevi («K»);
- i **nomi**: ogni parola con la maiuscola, uguale (senza radici né tolleranza: «Napoleone» non è «Napoli»,
  «Maria» non è «Mario»), e la prima parola se non è una parola grammaticale;
- la **negazione**: se c'è nella frase detta c'è nelle frasi citate, e viceversa;
- le **parole piene**: in gran parte nella sorgente (`SOGLIA_PAROLE`), così un'aggiunta cade senza un elenco.

Ciò che qui resta (un valore vero attaccato al soggetto sbagliato dentro la stessa frase) è del giudizio
indipendente del modello (`riassunto.giudizio`).

**La cintura** (`forma`, `_vietata`): ciò che non va detto mai, anche se è scritto: indirizzi, telefoni anche a
parole o spezzati, seconda persona, inglese (non in una verifica d'inglese), ordini, domande, simboli. Non è il
controllo: elenchi così non convergono. Vale anche per le frasi della pagina: una frase così non è una fonte.

Gli esiti sono **nomi di motivi, mai testo**. Solo libreria standard.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import argomenti as A
from . import ascolta as S
from . import unita as U

FRASE_PAROLE_MAX = 40
FRASE_MIN_CAR = 15
FONTI_MAX = 3                 # le frasi della pagina che una frase detta può citare
SOGLIA_PAROLE = 0.6           # delle parole piene, nella sorgente
RADICE = 5                    # le parole piene (non i nomi) si confrontano sulla radice: «conquistò»

_PEDICI = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre")
_MESE_RE = "|".join(_MESI)


def _norma(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


# ─────────────────────────── la cintura: ciò che non si dice mai ───────────────────────────
_TELEFONO_CIFRE = re.compile(r"(?<![\d,.])(?:\+\s?)?\d(?:[ .\-]?\d){6,}(?![\d])")
_CIFRE_DETTE = frozenset("zero uno due tre quattro cinque sei sette otto nove".split())
_FILA_TELEFONO = 5
# «via Roma 12», «via Roma numero dodici», «piazza Duomo, 3»; «la via Appia» resta
_VIA = re.compile(r"\b(?:via|viale|piazza|corso|vicolo|largo)\s+(?:(?:del|della|dei|delle|di)\s+)?"
                  r"(?:[A-ZÀ-Ý][\w'’]*\s*){1,4},?\s*(?:(?:n\.?\s*)?\d|numero\s+\w+)")
# La seconda persona. «sei» è anche un numero: solo in testa o dopo «tu», «non»
_SECONDA = re.compile(r"\b(?:tu|ti|te|vi|devi|dovete|puoi|potete|sai|sapete|vuoi|volete|hai|avete|tuo|tua|"
                      r"tuoi|tue|vostro|vostra|vostri|vostre|ricordati|ricordatevi|preparati)\b|"
                      r"^\W*sei\b|\b(?:tu|non)\s+sei\b", re.I)
_INGLESE = re.compile(r"\b(?:you|your|must|tell|please|ignore|answer|the|write)\b", re.I)
# L'imperativo in testa, oltre agli ordini a un assistente di `argomenti._ORDINE`
_IMPERATIVO = re.compile(
    r"^\W*(?:ricorda|ricordate|nota|notate|osserva|osservate|pensa|pensate|immagina|immaginate|"
    r"studia|studiate|ripassa|ripassate|leggi|leggete|guarda|guardate|ascolta|ascoltate|prova|"
    r"provate|impara|imparate|porta|portate|vai|andate|apri|aprite|fai|fate|controlla|controllate|"
    r"telefona|telefonate|contatta|contattate|scarica|scaricate|clicca|cliccate|visita|visitate|"
    r"attenzione|importante)(?!\w)", re.I)
# Una comunicazione della scuola o un discorso sul testo: non è materia, e nemmeno fonte
_COMUNICAZIONE = re.compile(
    r"\b(?:professor\w*|prof|insegnant\w*|maestr[ae]|preside|segreteria|scuola|famiglie|genitori|"
    r"bidell\w*|rappresentant\w*)\b[^.;:]{0,40}?\b(?:ha comunicato|hanno comunicato|comunica|comunicano|"
    r"ha detto|hanno detto|dice che|dicono che|ricorda che|ricordano che|avvisa|avvisano|chiede di|"
    r"chiedono di|versa\w*|paga\w*|consegna\w*|devono|deve)\b|"
    r"\bnon (?:è|e') più (?:necessari\w|obbligatori\w|richiest\w)|"
    r"\bparol[ae] (?:segret[ae]|d'ordine)\b|\bpassword\b|\bcredenziali\b|"
    r"\b(?:il tool|i tool|chatbot|prompt)\b|\bda ora in poi\b|\brispondi\b[^.;:]{0,20}\b(?:solo|in \w+)\b|"
    r"\b(?:chi legge|chi ascolta|allo studente|agli studenti|alla studentessa|questo testo|"
    r"questa pagina|questo capitolo)\b", re.I)
_MARKUP = re.compile(r"[*#_`|\[\]{}<>~^\\]|->|=>|→|⟶|⇌|⇄|\bhttp", re.I)
_SIMBOLI = re.compile(r"[^\w\s.,;:!?'’\"«»“”()\-–—%°/+=²³ªº€$£¹]")
_PRIMO_ELENCO = re.compile(r"^\s*(?:[-•·▪◦]|\d{1,2}[.)]\s|[a-z][.)]\s)")


def _e_telefono(cifre: str) -> bool:
    """Una fila di cifre è un telefono, non due anni («1519-1521») né un numero con le migliaia."""
    gruppi = re.findall(r"\d+", cifre)
    if all(len(g) == 4 and 1000 <= int(g) <= 2100 for g in gruppi):
        return False
    return not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cifre.strip())


def _vietata(frase: str, straniera: bool = False) -> str | None:
    """Ciò che non si dice e non fa da fonte, nemmeno se sta nella pagina. Il motivo o None."""
    if any(_e_telefono(m.group(0)) for m in _TELEFONO_CIFRE.finditer(frase)):
        return "telefono"
    run = 0
    for w in re.findall(r"[a-z0-9]+", _norma(frase)):
        run = run + 1 if w in _CIFRE_DETTE or (w.isdigit() and len(w) <= 3) else 0
        if run >= _FILA_TELEFONO:
            return "telefono"
    if _VIA.search(frase):
        return "indirizzo"
    if _COMUNICAZIONE.search(frase):
        return "comunicazione"
    if _SECONDA.search(frase) or _IMPERATIVO.search(frase):
        return "seconda_persona"
    if not straniera and _INGLESE.search(frase):
        return "inglese"
    return None


def forma(frase: str, nomi=(), straniera: bool = False) -> str | None:
    """Il motivo per cui la frase non si può dire, a prescindere dalle pagine; None se va."""
    f = str(frase or "").strip()
    if len(f) < FRASE_MIN_CAR or len(f.split()) > FRASE_PAROLE_MAX:
        return "lunghezza"
    # Prima ciò che dice la frase, poi come è scritta: i conti delle voci ostili devono essere giusti
    motivo = S.scarto(f, nomi, True) or _vietata(f, straniera)
    if motivo is not None:
        return motivo
    if _PRIMO_ELENCO.match(f) or _MARKUP.search(f) or _SIMBOLI.search(f):
        return "forma"
    if not f.endswith(".") or f.endswith("..."):
        return "domanda" if f.endswith("?") else "forma"
    # La maiuscola in testa: i nomi si riconoscono da lì («colombo scrisse…» non passa di lato)
    if not (f[0].isupper() or f[0].isdigit()):
        return "forma"
    return None


# ─────────────────────────── i valori di un testo ───────────────────────────
_FORMULA = re.compile(r"(?<![\w])((?:[A-Z][a-z]?\d*){1,8})(?![\w])")
_SIGLA = re.compile(r"(?<![\w.])([A-Z]{2,6})(?![\w.])")
_ARTICOLO = re.compile(r"\bun(?:a)?\b(?!\s+(?:metr|chil|litr|gramm|or[ae]\b|minut|centimetr|millimetr|mol|"
                       r"grad|newton|joule|watt))\s*")
_FRAZIONE = re.compile(r"\b(un|una|due|tre|quattro|cinque|sei|sette|otto|nove)\s+"
                       r"(mezz[oi]|terz[oi]|quart[oi]|quint[oi]|sest[oi]|settim[oi]|ottav[oi]|"
                       r"non[oi]|decim[oi])\b", re.I)
_DIVISORE = {"mezz": 2, "terz": 3, "quart": 4, "quint": 5, "sest": 6, "settim": 7, "ottav": 8,
             "non": 9, "decim": 10}
_CARDINALI = {"un": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
              "otto": 8, "nove": 9}
_FRAZIONE_CIFRE = re.compile(r"(?<![\d,./])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")
_MIGLIAIA_SPAZIO = re.compile(r"(?<![\d,.])(\d{1,3})((?: \d{3})+)(?![\d])")
_GRANDI = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mila|milion[ei]|miliard[oi])\b")
_GRANDI_UN = re.compile(r"\b(?:un[ao]?\s+)?(milione|miliardo)\b")
_FATTORE = {"mila": 1e3, "milion": 1e6, "miliard": 1e9}
_SEGNI = re.compile(r"(?<!\d)[.,;:!?]|[.,;:!?](?!\d)|[()«»“”\"]")
_TEMPI = {"anno": "anno", "anni": "anno", "mese": "mese", "mesi": "mese", "giorno": "giorno",
          "giorni": "giorno", "settimana": "settimana", "settimane": "settimana", "secolo": "secolo",
          "secoli": "secolo", "decennio": "decennio", "decenni": "decennio"}
_TEMPO_RE = re.compile(r"(\d+(?:,\d+)?)\s+(" + "|".join(_TEMPI) + r")\b")
_ERA = re.compile(r"(\d+)\s*(a\.\s?c\b\.?|d\.\s?c\b\.?|avanti cristo|dopo cristo)", re.I)


def _via_formule(testo: str) -> str:
    """Il testo senza le formule con una cifra: le loro cifre non sono numeri («H2O»)."""
    def sost(m: re.Match) -> str:
        return " " if any(c.isdigit() for c in m.group(1)) else m.group(0)
    t = str(testo or "").translate(_PEDICI)
    t = re.sub(r"(?<![\w,.])\d+(?=[A-Z][a-z]?\d*(?:[A-Z]|\b))(?![A-Z]?[a-z]+\b)", " ", t)
    return _FORMULA.sub(sost, t)


def _fattore(parola: str) -> float:
    return next(v for k, v in _FATTORE.items() if parola.startswith(k))


def _frazioni(testo: str) -> tuple[str, set]:
    out = set()

    def detta(m: re.Match) -> str:
        n = _CARDINALI.get(m.group(1).lower())
        d = next(v for k, v in _DIVISORE.items() if m.group(2).lower().startswith(k))
        out.add(round(n / d, 6))
        return " "

    def scritta(m: re.Match) -> str:
        if int(m.group(2)):
            out.add(round(int(m.group(1)) / int(m.group(2)), 6))
        return m.group(0)
    return _FRAZIONE_CIFRE.sub(scritta, _FRAZIONE.sub(detta, testo)), out


def _normale(testo: str) -> str:
    """Il testo con i numeri a cifre: senza formule, senza articoli («un» resta con un'unità: «un
    chilometro» è 1 km; non «in un secondo momento»), le migliaia staccate unite («12 000»)."""
    t = _via_formule(testo)
    t = _MIGLIAIA_SPAZIO.sub(lambda m: m.group(1) + m.group(2).replace(" ", ""), t)
    t = _SEGNI.sub(" ", t)
    # L'elisione non è un'unità: «numero atomico sei, l'ossigeno otto» si leggeva «6 litri»; «un'ora» resta
    t = re.sub(r"(?i)\b(?!un['’])[a-zà-ù]+['’]", " ", t)
    t = re.sub(r"(\d)\s*[-–—]\s*(\d)", r"\1 \2", t)      # l'intervallo non è un numero negativo
    t = U._semplice(t)
    t = _GRANDI_UN.sub(lambda m: str(int(_fattore(m.group(1)))), t)
    t = _ARTICOLO.sub(" ", t)
    t = U._in_cifre(" ".join(t.split()))
    t = _GRANDI.sub(lambda m: ("%f" % (float(m.group(1).replace(",", ".")) * _fattore(m.group(2)))
                               ).rstrip("0").rstrip(".").replace(".", ","), t)
    return t


def _base(v: float, u: str) -> tuple:
    g, f = U.UNITA[u]
    return g, round(v * f, 9)


_ORDINALI: dict = {}


def _ordinali(testo: str) -> set:
    """Gli ordinali che affermano qualcosa, e valgono solo contro altri ordinali (mai «15» per
    «quindicesimo»): «-esimo» dovunque, i primi dieci davanti a «secolo» o dopo un nome; i romani
    (`pronuncia.romani_detti`, anche «secolo XV») e «15°»."""
    from ..pronuncia import _romano, ordinale, romani_detti
    if not _ORDINALI:
        for n in range(1, 101):
            o = ordinale(n)
            for finale in "oaie":
                _ORDINALI[o[:-1] + finale] = n
    t = romani_detti(str(testo or ""))
    out = {int(m.group(1)) for m in re.finditer(r"(\d{1,3})\s*°(?!\s*[cC]\b)", t)}
    for m in re.finditer(r"\bsec(?:olo|\.)\s+([IVXLCDM]{1,8})\b", t):
        n = _romano(m.group(1))
        if n:
            out.add(n)
    for m in re.finditer(r"\b([A-Za-zÀ-ÿ']+)\b", t):
        w = _norma(m.group(1))
        n = _ORDINALI.get(w)
        if n is None:
            continue
        prima, dopo = t[:m.start()].rstrip(), t[m.end():].lstrip()
        nome = (re.search(r"[A-ZÀ-Ý][a-zà-ÿ]+$", prima) and w.endswith("o")
                and w not in ("primo", "secondo") and not re.match(r"di\b", dopo))
        if n > 10 or nome or re.match(r"(?:secolo|secoli|sec\.|millennio)", dopo, re.I):
            out.add(n)
    return out


def _formule(testo: str) -> set:
    from ..pronuncia import _formula_detta
    t = str(testo or "").translate(_PEDICI)
    return {m.group(1) for m in _FORMULA.finditer(t) if _formula_detta(m.group(1)) is not None}


def _date(testo: str) -> set:
    """Le coppie (giorno, mese): «12 ottobre», «il dodici di ottobre», «primo maggio», «12/10/1492»."""
    t = U._in_cifre(" ".join(U._semplice(_SEGNI.sub(" ", str(testo or ""))).split()))
    out = set()
    for m in re.finditer(rf"\b(\d{{1,2}}|primo)°?\s+(?:di\s+)?({_MESE_RE})\b", t):
        out.add((1 if m.group(1) == "primo" else int(m.group(1)), m.group(2)))
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})/\d{2,4}(?![\d/])", str(testo or "")):
        if 1 <= int(m.group(2)) <= 12:
            out.add((int(m.group(1)), _MESI[int(m.group(2)) - 1]))
    return out


_ERA_DETTA = re.compile(r"\b(?:avanti|dopo) cristo\b", re.I)
_NEGAZIONE = re.compile(r"\b(?:non|mai|né|nessun\w*)\b", re.I)
# Le lettere dette di una formula: una fila è buona solo se è la forma detta di una della sorgente
_LETTERE_SOLE = "acca|effe|elle|emme|enne|erre|zeta|ics|vu|bi|cu|gi|kappa"
_LETTERE_TUTTE = _LETTERE_SOLE + "|a|ci|di|e|esse|i|o|pi|ti|u"
_NUMERI_PICCOLI = "uno|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|dodici"
_FILA_LETTERE = re.compile(
    rf"\b(?:{_LETTERE_SOLE}|ci\s+o)(?:\s+(?:{_LETTERE_TUTTE}|{_NUMERI_PICCOLI}))*\b")
_PICCOLE_DOPO = frozenset("a ci di e esse i o pi ti u".split())
# Parole grammaticali: non sono né nomi in testa né simboli. Solo queste, nessuna ipotesi sulla forma
_GRAMMATICA = frozenset("""il lo la i gli le l un una uno del della dello dei degli delle al alla allo ai
agli alle dal dalla dallo dai dagli dalle nel nella nello nei negli nelle sul sulla sullo sui sugli
sulle col con per tra fra su di da in a e ed o ma pero anche ancora poi quindi dunque infatti inoltre
invece mentre quando dove come perche se che chi cui cio questo questa questi queste quel quello quella
quelli quelle quei quegli ogni ciascun ciascuna ciascuno alcuni alcune altri altre altro altra tutti tutte
tutto tutta molti molte molto molta pochi poche poco poca tanti tante tanto tanta piu meno non ne si ci
sono e era erano fu furono ha hanno aveva avevano essa esso essi esse egli ella loro lui lei prima dopo
durante allora cosi qui la gia sempre spesso infine grazie entro senza sopra sotto dentro fuori verso
contro presso oltre circa nessun nessuna nessuno due tre ad va fa no li mi me secondo attraverso mediante
tramite nonostante sebbene benche poiche siccome oppure cioe ovvero ossia anzi tuttavia pertanto percio""".split())


def _toglie_file(frase_n: str, detto: str) -> tuple[str, bool]:
    """(la frase senza le file di lettere dette, tutte stanno nella sorgente?)."""
    tutte = True

    def sost(m: re.Match) -> str:
        nonlocal tutte
        w = m.group(0).split()
        while w:
            if " ".join(w) in detto:
                return " "
            if w[-1] not in _PICCOLE_DOPO:
                break
            w.pop()
        tutte = False
        return " "
    return _FILA_LETTERE.sub(sost, frase_n), tutte


@dataclass
class Valori:
    """Ciò che dice di preciso un testo: la sorgente di una frase, o la frase stessa."""
    nudi: set = field(default_factory=set)       # tutti i valori, con o senza unità
    misure: set = field(default_factory=set)     # (grandezza, valore in base)
    frazioni: set = field(default_factory=set)
    tempi: set = field(default_factory=set)
    ere: set = field(default_factory=set)
    date: set = field(default_factory=set)
    mesi: set = field(default_factory=set)
    ordinali: set = field(default_factory=set)
    formule: set = field(default_factory=set)
    sigle: set = field(default_factory=set)
    parole: set = field(default_factory=set)
    radici: set = field(default_factory=set)
    detto: str = ""
    negazione: bool = False


def _unisci(a: Valori, b: Valori):
    for k in ("nudi", "misure", "frazioni", "tempi", "ere", "date", "mesi", "ordinali", "formule",
              "sigle", "parole", "radici"):
        getattr(a, k).update(getattr(b, k))
    a.detto = f"{a.detto} {b.detto}".strip()
    a.negazione = a.negazione or b.negazione


def _ere(testo: str) -> set:
    t = U._in_cifre(" ".join(U._semplice(_via_formule(testo)).split()))
    out = set()
    for m in _ERA.finditer(t):
        out.add((int(m.group(1)), "a" if m.group(2).lower().startswith("a") else "d"))
    return out


def valori(testo: str, sorgente: bool = True) -> Valori:
    """I valori di un testo. Per una sorgente anche la forma detta (`per_ripasso`): «XV secolo»,
    «ci o due»; per la frase detta i numeri si leggono senza le file di lettere già giuste."""
    from ..pronuncia import per_ripasso
    V = Valori()
    detto = per_ripasso(testo) if sorgente else ""
    t, V.frazioni = _frazioni(str(testo or ""))
    n = _normale(t)
    for v, u in U.leggi(n):
        V.nudi.add(round(v, 9))
        if u is not None:
            V.misure.add(_base(v, u))
    V.tempi = {(float(m.group(1).replace(",", ".")), _TEMPI[m.group(2)]) for m in _TEMPO_RE.finditer(n)}
    V.ere = _ere(testo)
    V.date, V.mesi = _date(testo), {m for m in _MESI if re.search(rf"\b{m}\b", _norma(testo))}
    V.ordinali = _ordinali(testo)
    V.formule = _formule(testo)
    V.sigle = {m.group(1) for m in _SIGLA.finditer(str(testo or ""))} - V.formule
    V.parole = set(re.findall(r"[a-z0-9]+", _norma(testo))) | set(re.findall(r"[a-z0-9]+", _norma(detto)))
    V.radici = {w[:RADICE] for w in V.parole if len(w) >= RADICE}
    V.detto = _norma(detto)
    V.negazione = bool(_NEGAZIONE.search(str(testo or "")))
    return V


# ─────────────────────────── il materiale numerato per frase ───────────────────────────
def frasi_pulite(testo, nomi=(), straniera: bool = False) -> list[str]:
    """Le frasi di una pagina che possono fare da fonte."""
    out = []
    for p in S.paragrafi(testo):
        for f in S.frasi(p):
            if S.scarto(f, nomi, True) is None and not _vietata(f, straniera):
                out.append(f)
    return out


class Materiale:
    """Le frasi delle pagine, una volta sola per tutto il giro (la CPU del processo della voce): i codici
    «P1.3», i testi, i valori calcolati al primo uso. `rif` [(«P1», pagina)]; le pagine in `istruzioni`
    non ci sono."""

    def __init__(self, testi: dict, istruzioni=(), nomi=(), straniera: bool = False):
        self.frasi: dict[str, str] = {}
        self.per_pagina: dict[str, list[str]] = {}
        self.nomi, self.straniera = tuple(nomi), straniera
        self._v: dict = {}
        for r, t in testi.items():
            if r in istruzioni:
                continue
            codici = []
            for i, f in enumerate(frasi_pulite(t, nomi, straniera), 1):
                self.frasi[f"{r}.{i}"] = f
                codici.append(f"{r}.{i}")
            if codici:
                self.per_pagina[r] = codici

    def fonte(self, codici) -> Valori:
        k = tuple(sorted(codici))
        if k not in self._v:
            V = Valori()
            for c in k:
                if c not in self._v:
                    self._v[c] = valori(self.frasi[c])
                _unisci(V, self._v[c])
            self._v[k] = V
        return self._v[k]

    def testo_fonte(self, codici) -> str:
        return " ".join(self.frasi[c] for c in codici)


_CODICE = re.compile(r"^P\d+\.\d+$")


def citazioni(fonti, M: Materiale) -> list[str] | None:
    """Le fonti valide di una frase, o None: al più `FONTI_MAX`, tutte esistenti, della stessa pagina."""
    if not isinstance(fonti, list) or not fonti or len(fonti) > FONTI_MAX:
        return None
    cod = list(dict.fromkeys(re.sub(r"\s+", "", str(c)).upper() for c in fonti))
    if not all(_CODICE.match(c) and c in M.frasi for c in cod):
        return None
    if len({c.split(".")[0] for c in cod}) != 1:
        return None
    return cod


# ─────────────────────────── una frase contro la sua fonte ───────────────────────────
def mancanti(frase: str, F: Valori) -> list[str]:
    """I tipi dei valori della frase che nella fonte non ci sono (una voce per valore)."""
    out: list[str] = []
    fn, file_ok = _toglie_file(_norma(frase), F.detto)
    senza_era = _ERA_DETTA.sub(" ", str(frase or ""))
    if not file_ok:
        out.append("formula")
    # Le file già riconosciute non si rileggono come numeri
    testo = frase if fn == _norma(frase) else fn
    D = valori(testo, sorgente=False)
    for x in D.frazioni:
        if x not in F.frazioni and x not in F.nudi:
            out.append("numero")
    t, _f = _frazioni(testo)
    for v, u in U.leggi(_normale(t)):
        if u is None and abs(v) == 1:
            continue                       # «uno dei»: non afferma una quantità
        if u is None and round(v, 9) in F.nudi:
            continue
        if u is not None and _base(v, u) in F.misure:
            continue
        out.append("numero")
    out += ["numero"] * len(D.tempi - F.tempi)
    out += ["data"] * len(D.ere - F.ere)
    out += ["data"] * len(D.date - F.date)
    out += ["data"] * len(D.mesi - F.mesi)
    out += ["numero"] * len(D.ordinali - F.ordinali)
    D2 = valori(frase, sorgente=False)
    out += ["formula"] * len(D2.formule - F.formule)
    out += ["sigla"] * len(D2.sigle - F.sigle)
    # I nomi: uguali, dentro la frase e in testa
    corpo = senza_era.strip()
    primo = re.match(r"\W*([A-ZÀ-Ý][a-zà-ÿ]*)(?![\w'’])", corpo)
    for m in re.finditer(r"(?<![\w])([A-ZÀ-Ý][a-zà-ÿ]{1,})(?![\w])", corpo):
        w = _norma(m.group(1))
        in_testa = primo is not None and m.start(1) == primo.start(1)
        if in_testa and w in _GRAMMATICA:
            continue
        # In testa la maiuscola non dice che è un nome: «Atomi sono…» con «atomo» nella fonte. Dentro la
        # frase il nome è uguale, senza radici («Napoli» non è «Napoleone»)
        if in_testa and len(w) >= RADICE and w[:RADICE] in F.radici:
            continue
        if w not in F.parole and U.parola_numero(w) is None and w not in _MESI:
            out.append("nome")
    # I simboli brevi: «K», «h due o due»: una o due lettere che non sono grammatica
    for w in re.findall(r"(?<![\w'’])([A-Za-z]{1,2})(?![\w'’])", corpo):
        x = _norma(w)
        if x not in _GRAMMATICA and x not in F.parole:
            out.append("simbolo")
    if bool(_NEGAZIONE.search(corpo)) != F.negazione:
        out.append("negazione")
    return out


_PAROLE_DI_MISURA = frozenset(["virgola", "mezzo", "mezza", "milione", "milioni", "miliardo", "miliardi",
                               "mila"]) | frozenset(_TEMPI) | frozenset(
    p for nome, _c, simbolo in U._VOCI if not simbolo for p in nome.split(" ") if len(p) >= 4)


def parole_piene(frase: str, F: Valori) -> bool:
    """Le parole piene della frase stanno in gran parte nella fonte (uguali o con la stessa radice)."""
    from ..provenienza import parole
    def e_valore(w: str) -> bool:
        return (U.parola_numero(w) is not None or w in _PAROLE_DI_MISURA or w in _MESI
                or w in _ORDINALI)
    pp = [w for w in parole(_ERA_DETTA.sub(" ", frase)) if not w.isdigit() and not any(c.isdigit() for c in w)
          and not e_valore(w)]
    if not pp:
        return True
    dentro = sum(w in F.parole or (len(w) >= RADICE and w[:RADICE] in F.radici) for w in pp)
    return dentro / len(pp) >= SOGLIA_PAROLE


_OPERATORE = re.compile(r"[=+×]|\s-\s")


def controlla(frase: str, fonti, M: Materiale) -> dict:
    """{"ok", "motivi", "fonti"}: la frase contro le sole frasi citate. I motivi sono nomi, mai testo."""
    m = forma(frase, M.nomi, M.straniera)
    if m is not None:
        return {"ok": False, "motivi": [m], "fonti": None}
    cod = citazioni(fonti, M)
    if cod is None:
        return {"ok": False, "motivi": ["citazione"], "fonti": None}
    F = M.fonte(cod)
    motivi = mancanti(frase, F)
    if not parole_piene(frase, F):
        motivi.append("parole")
    # Una formula o un'equazione detta: i suoi pezzi di fila nella fonte («3x - 5» non è «3x + 5»)
    if _OPERATORE.search(frase):
        _es, dentro = A.controlla(frase, ["F"], {"F": M.testo_fonte(cod)})
        if not dentro:
            motivi.append("formula")
    return {"ok": not motivi, "motivi": motivi, "fonti": cod}
