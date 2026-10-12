"""
Esercizi di chimica con i numeri (12/10/2026, materie calcolabili, S1 della roadmap): massa
molare, moli e concentrazione, bilanciamento delle reazioni.

Stesso schema della matematica e della fisica: generatori deterministici dal seme, risposta
calcolata dal codice e ricalcolo indipendente:

- **massa molare**: il generatore somma la composizione scritta a mano accanto al composto; il
  ricalcolo legge la **formula** da capo (`atomi`) e rifà la somma: un errore in una delle due
  e l'esercizio non nasce;
- **moli e concentrazione**: espressione nelle unità di base rifatta dal valutatore
  (`misure.verifica`), con la massa molare ricalcolata dalla formula;
- **bilanciamento**: i coefficienti vengono da una tabella; il ricalcolo conta gli atomi di
  ogni elemento ai due lati, controlla che i coefficienti siano i più piccoli (MCD 1) e che il
  bilanciamento sia unico (le soluzioni formano una retta sola: rango = specie − 1), e che il
  coefficiente chiesto non abbia un altro valore che bilancia.

Le formule a voce si leggono lettera per lettera come a scuola, con i pedici come numeri
(«H₂SO₄» → «acca due esse o quattro»), dopo il nome del composto; sulla scheda con i pedici.
Masse atomiche arrotondate come sui libri (cloro 35,5), dette nella domanda.
"""

from __future__ import annotations

import math
import random
import re
from fractions import Fraction as F

from .. import unita as U
from .misure import controlla as controlla_misura
from .misure import nuovo, q
from .misure import verifica as verifica_misura
from .modello import Classe, Esercizio, Esito, livello_da_classe
from .numeri import leggi_valore

MATERIA = "chimica"
VERIFICA = "calcolato"

ARGOMENTI = {
    "massa_molare": {"nome": "massa molare", "alias": ("massa molar", "peso molecolar",
                                                       "massa molecolar", "formul"),
                     "classi": (Classe("medie", 3), Classe("superiori", 5))},
    "moli": {"nome": "moli e concentrazione", "alias": ("moli", "mole", "concentrazion",
                                                          "molarit"),
             "classi": (Classe("superiori", 1), Classe("superiori", 5))},
    "bilanciamento": {"nome": "bilanciamento delle reazioni",
                      "alias": ("bilanci", "reazion", "coefficient"),
                      "classi": (Classe("medie", 3), Classe("superiori", 5))},
}

# Masse atomiche come sui libri, nome dell'elemento
MASSE = {"H": F(1), "C": F(12), "N": F(14), "O": F(16), "Na": F(23), "Mg": F(24),
         "Al": F(27), "S": F(32), "Cl": F(71, 2), "K": F(39), "Ca": F(40), "Fe": F(56),
         "Zn": F(65)}
ELEMENTI = {"H": "idrogeno", "C": "carbonio", "N": "azoto", "O": "ossigeno", "Na": "sodio",
            "Mg": "magnesio", "Al": "alluminio", "S": "zolfo", "Cl": "cloro", "K": "potassio",
            "Ca": "calcio", "Fe": "ferro", "Zn": "zinco"}
# Nomi italiani delle lettere, per leggere le formule
LETTERE = {"a": "a", "b": "bi", "c": "ci", "d": "di", "e": "e", "f": "effe", "g": "gi",
           "h": "acca", "i": "i", "k": "cappa", "l": "elle", "m": "emme", "n": "enne", "o": "o",
           "p": "pi", "r": "erre", "s": "esse", "t": "ti", "u": "u", "v": "vu", "z": "zeta"}

# Formula, «del …» (il nome con la preposizione), livello, composizione scritta a mano
COMPOSTI = (
    ("H2O", "dell'acqua", 1, {"H": 2, "O": 1}),
    ("CO2", "dell'anidride carbonica", 1, {"C": 1, "O": 2}),
    ("O2", "dell'ossigeno", 1, {"O": 2}),
    ("N2", "dell'azoto", 1, {"N": 2}),
    ("NaCl", "del cloruro di sodio", 1, {"Na": 1, "Cl": 1}),
    ("CH4", "del metano", 1, {"C": 1, "H": 4}),
    ("NH3", "dell'ammoniaca", 1, {"N": 1, "H": 3}),
    ("HCl", "dell'acido cloridrico", 1, {"H": 1, "Cl": 1}),
    ("MgO", "dell'ossido di magnesio", 1, {"Mg": 1, "O": 1}),
    ("C6H12O6", "del glucosio", 2, {"C": 6, "H": 12, "O": 6}),
    ("H2SO4", "dell'acido solforico", 2, {"H": 2, "S": 1, "O": 4}),
    ("CaCO3", "del carbonato di calcio", 2, {"Ca": 1, "C": 1, "O": 3}),
    ("HNO3", "dell'acido nitrico", 2, {"H": 1, "N": 1, "O": 3}),
    ("NaOH", "dell'idrossido di sodio", 2, {"Na": 1, "O": 1, "H": 1}),
    ("KCl", "del cloruro di potassio", 2, {"K": 1, "Cl": 1}),
    ("SO2", "dell'anidride solforosa", 2, {"S": 1, "O": 2}),
    ("H2O2", "dell'acqua ossigenata", 2, {"H": 2, "O": 2}),
    ("C2H6O", "dell'etanolo", 2, {"C": 2, "H": 6, "O": 1}),
    ("Al2O3", "dell'ossido di alluminio", 3, {"Al": 2, "O": 3}),
    ("Fe2O3", "dell'ossido di ferro", 3, {"Fe": 2, "O": 3}),
    ("CaCl2", "del cloruro di calcio", 3, {"Ca": 1, "Cl": 2}),
    ("Na2CO3", "del carbonato di sodio", 3, {"Na": 2, "C": 1, "O": 3}),
    ("C12H22O11", "del saccarosio", 3, {"C": 12, "H": 22, "O": 11}),
    ("MgCl2", "del cloruro di magnesio", 3, {"Mg": 1, "Cl": 2}),
    ("KNO3", "del nitrato di potassio", 3, {"K": 1, "N": 1, "O": 3}),
    ("NaHCO3", "del bicarbonato di sodio", 3, {"Na": 1, "H": 1, "C": 1, "O": 3}),
)

# Reazioni bilanciate con i coefficienti più piccoli: (reagenti, prodotti), livello
REAZIONI = (
    (((2, "H2"), (1, "O2")), ((2, "H2O"),), 1),
    (((1, "N2"), (3, "H2")), ((2, "NH3"),), 1),
    (((2, "Na"), (1, "Cl2")), ((2, "NaCl"),), 1),
    (((2, "Mg"), (1, "O2")), ((2, "MgO"),), 1),
    (((1, "H2"), (1, "Cl2")), ((2, "HCl"),), 1),
    (((2, "H2O2"),), ((2, "H2O"), (1, "O2")), 1),
    (((1, "CH4"), (2, "O2")), ((1, "CO2"), (2, "H2O")), 2),
    (((1, "Zn"), (2, "HCl")), ((1, "ZnCl2"), (1, "H2")), 2),
    (((2, "KClO3"),), ((2, "KCl"), (3, "O2")), 2),
    (((4, "Fe"), (3, "O2")), ((2, "Fe2O3"),), 2),
    (((4, "Al"), (3, "O2")), ((2, "Al2O3"),), 2),
    (((1, "C3H8"), (5, "O2")), ((3, "CO2"), (4, "H2O")), 3),
    (((1, "C2H6O"), (3, "O2")), ((2, "CO2"), (3, "H2O")), 3),
    (((2, "Al"), (6, "HCl")), ((2, "AlCl3"), (3, "H2")), 3),
    (((1, "C6H12O6"), (6, "O2")), ((6, "CO2"), (6, "H2O")), 3),
    (((2, "C2H6"), (7, "O2")), ((4, "CO2"), (6, "H2O")), 3),
)


# ─────────────────────────── formule ───────────────────────────

_RE_FORMULA = re.compile(r"([A-Z][a-z]?)(\d*)")


def atomi(formula: str) -> dict[str, int]:
    """Gli atomi di una formula senza parentesi, letti dalla scrittura: «H2SO4» → {H: 2, S:
    1, O: 4}. ValueError per ciò che non è una formula."""
    out: dict[str, int] = {}
    pos = 0
    for m in _RE_FORMULA.finditer(formula):
        if m.start() != pos:
            raise ValueError(f"formula non valida: {formula}")
        out[m.group(1)] = out.get(m.group(1), 0) + int(m.group(2) or 1)
        pos = m.end()
    if pos != len(formula) or not out:
        raise ValueError(f"formula non valida: {formula}")
    return out


def massa_molare(formula: str) -> F:
    return sum((MASSE[el] * n for el, n in atomi(formula).items()), F(0))


_PEDICI = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def formula_scritta(formula: str) -> str:
    """Per la scheda, con i pedici: «H₂SO₄»."""
    return _RE_FORMULA.sub(lambda m: m.group(1) + m.group(2).translate(_PEDICI), formula)


def formula_detta(formula: str) -> str:
    """Lettera per lettera, i pedici come numeri: «H2SO4» → «acca due esse o quattro», «NaCl»
    → «enne a ci elle». Misurato con espeak: «acca due o», «ci o due» si capiscono; «NaCl»
    scritto com'è diventava «na ci elle»."""
    parti = []
    for m in _RE_FORMULA.finditer(formula):
        parti.append(" ".join(LETTERE[c.lower()] for c in m.group(1)))
        if m.group(2):
            parti.append(m.group(2))
    return " ".join(parti)


def _masse_dette(formule, scritte: bool) -> str:
    """«idrogeno 1, ossigeno 16» (voce) o «H 1, O 16» (scheda), nell'ordine della formula."""
    visti = []
    for f in formule:
        for el in atomi(f):
            if el not in visti:
                visti.append(el)
    return ", ".join(f"{el if scritte else ELEMENTI[el]} {U.numero_detto(MASSE[el])}"
                     for el in visti)


def _composto(rng, L):
    scelti = [c for c in COMPOSTI if c[2] == L]
    return rng.choice(scelti)


# ─────────────────────────── massa molare ───────────────────────────

def _massa_molare(rng: random.Random, L: int, seme: int) -> Esercizio:
    formula, del_, _, comp = _composto(rng, L)
    M = sum((MASSE[el] * n for el, n in comp.items()), F(0))
    pezzi = [f"{n} per {U.numero_detto(MASSE[el])}" if n > 1 else U.numero_detto(MASSE[el])
             for el, n in comp.items()]
    es = nuovo(MATERIA, "massa_molare", L, seme,
               f"Qual è la massa molare {del_}, {formula_scritta(formula)}, in g/mol? Masse "
               f"atomiche: {_masse_dette([formula], True)}.",
               f"Qual è la massa molare {del_}, {formula_detta(formula)}, in grammi per mole? "
               f"Usa queste masse atomiche: {_masse_dette([formula], False)}.",
               M, "g/mol",
               ["Somma le masse di tutti gli atomi della formula.",
                "Il numero piccolo dopo un elemento dice quanti atomi ce ne sono: moltiplica "
                "la sua massa per quel numero."],
               f"Sommo gli atomi: {' più '.join(pezzi)} fa {U.misura_detta(M, 'g/mol')}.",
               f"{q(M)}/1000", tollerate=("g", "u"), formula=formula)
    return es


# ─────────────────────────── moli e concentrazione ───────────────────────────

def _moli(rng: random.Random, L: int, seme: int) -> Esercizio:
    if L == 1:
        formula, del_, _, _ = _composto(rng, 1)
        M = massa_molare(formula)
        n = rng.choice((F(1, 2), F(1), F(3, 2), F(2), F(5, 2), F(3), F(4), F(5)))
        m = n * M
        return nuovo(MATERIA, "moli", L, seme,
                     f"Quante moli ci sono in {U.misura_scritta(m, 'g')} "
                     f"{_di(del_)} ({formula_scritta(formula)})? La massa molare è "
                     f"{U.misura_scritta(M, 'g/mol')}.",
                     f"Quante moli ci sono in {U.misura_detta(m, 'g')} {_di(del_)}? La sua "
                     f"massa molare è {U.misura_detta(M, 'g/mol')}.", n, "mol",
                     ["Il numero di moli è la massa divisa la massa molare.",
                      f"Dividi {U.numero_detto(m)} per {U.numero_detto(M)}."],
                     f"Moli uguale massa diviso massa molare: {U.numero_detto(m)} diviso "
                     f"{U.numero_detto(M)} fa {U.misura_detta(n, 'mol')}.",
                     f"({q(m)}/1000)/({q(massa_molare(formula))}/1000)", formula=formula)
    if L == 2:
        for _ in range(50):
            formula, del_, _, _ = _composto(rng, rng.choice((1, 2)))
            M = massa_molare(formula)
            n = rng.choice((F(1, 2), F(1, 4), F(2), F(3), F(1, 10), F(5)))
            m = n * M
            if (U.decimali(m) or 9) <= 2:
                break
        return nuovo(MATERIA, "moli", L, seme,
                     f"Quanti grammi pesano {U.misura_scritta(n, 'mol')} {_di(del_)} "
                     f"({formula_scritta(formula)})? Masse atomiche: "
                     f"{_masse_dette([formula], True)}.",
                     f"Quanti grammi pesano {U.misura_detta(n, 'mol')} {_di(del_)}, "
                     f"{formula_detta(formula)}? Usa queste masse atomiche: "
                     f"{_masse_dette([formula], False)}.", m, "g",
                     ["Prima calcola la massa molare sommando le masse degli atomi.",
                      f"La massa molare è {U.misura_detta(M, 'g/mol')}: moltiplicala per "
                      f"{U.numero_detto(n)}."],
                     f"La massa molare è {U.numero_detto(M)}; {U.numero_detto(n)} per "
                     f"{U.numero_detto(M)} fa {U.misura_detta(m, 'g')}.",
                     f"{q(n)}*{q(massa_molare(formula))}/1000", formula=formula)
    for _ in range(50):
        formula, del_, _, _ = rng.choice([c for c in COMPOSTI
                                          if c[0] in ("NaCl", "NaOH", "KCl", "C6H12O6",
                                                      "HCl", "CaCl2", "KNO3")])
        M = massa_molare(formula)
        c = rng.choice((F(1, 10), F(1, 5), F(1, 4), F(1, 2), F(1), F(2)))
        V = rng.choice((F(1, 4), F(1, 2), F(1), F(2), F(5)))
        n = c * V
        m = n * M
        if (U.decimali(m) or 9) <= 2 and (U.decimali(n) or 9) <= 2:
            break
    if rng.random() < 0.5:
        return nuovo(MATERIA, "moli", L, seme,
                     f"Sciogli {U.misura_scritta(n, 'mol')} {_di(del_)} "
                     f"({formula_scritta(formula)}) in acqua fino a {U.misura_scritta(V, 'L')}. "
                     f"Qual è la concentrazione, in mol/L?",
                     f"Sciogli {U.misura_detta(n, 'mol')} {_di(del_)} in acqua fino a "
                     f"{U.misura_detta(V, 'L')} di soluzione. Qual è la concentrazione, in moli "
                     f"al litro?", c, "mol/L",
                     ["La concentrazione molare è il numero di moli diviso i litri di "
                      "soluzione.", f"Dividi {U.numero_detto(n)} per {U.numero_detto(V)}."],
                     f"Concentrazione uguale moli diviso volume: {U.numero_detto(n)} diviso "
                     f"{U.numero_detto(V)} fa {U.misura_detta(c, 'mol/L')}.",
                     f"{q(n)}/({q(V)}/1000)", formula=formula)
    return nuovo(MATERIA, "moli", L, seme,
                 f"Sciogli {U.misura_scritta(m, 'g')} {_di(del_)} ({formula_scritta(formula)}, "
                 f"{U.misura_scritta(M, 'g/mol')}) in acqua fino a {U.misura_scritta(V, 'L')}. "
                 f"Qual è la concentrazione, in mol/L?",
                 f"Sciogli {U.misura_detta(m, 'g')} {_di(del_)} in acqua fino a "
                 f"{U.misura_detta(V, 'L')} di soluzione. La massa molare è "
                 f"{U.misura_detta(M, 'g/mol')}. Qual è la concentrazione, in moli al litro?",
                 c, "mol/L",
                 ["Prima trova le moli: la massa divisa la massa molare.",
                  f"Sono {U.misura_detta(n, 'mol')}: ora dividi per i litri, "
                  f"{U.numero_detto(V)}."],
                 f"{U.numero_detto(m)} diviso {U.numero_detto(M)} fa {U.misura_detta(n, 'mol')}; "
                 f"diviso {U.numero_detto(V)} litri fa {U.misura_detta(c, 'mol/L')}.",
                 f"(({q(m)}/1000)/({q(massa_molare(formula))}/1000))/({q(V)}/1000)",
                 formula=formula)


def _davanti(formula: str) -> str:
    """«davanti ad acca 2 o», «davanti a ci o 2» (a voce)."""
    detta = formula_detta(formula)
    return ("davanti ad " if detta[0] in "aeiou" else "davanti a ") + detta


def _di(del_: str) -> str:
    """«dell'acqua» → «di acqua», «del glucosio» → «di glucosio»."""
    if del_.startswith("dell'"):
        return "di " + del_[5:]
    return "di " + del_.split(" ", 1)[1]


# ─────────────────────────── bilanciamento ───────────────────────────

def _lato(specie, nascondi: str | None, scritte: bool, coeff: bool = True) -> str:
    parti = []
    for c, f in specie:
        nome = formula_scritta(f) if scritte else formula_detta(f)
        if f == nascondi:
            parti.append(("? " if scritte else "") + nome)
        elif coeff and c != 1:
            parti.append(f"{c} {nome}")
        else:
            parti.append(nome)
    return (" + " if scritte else " più ").join(parti)


def _bilanciamento(rng: random.Random, L: int, seme: int) -> Esercizio:
    reagenti, prodotti, _ = rng.choice([r for r in REAZIONI if r[2] == L])
    tutte = list(reagenti) + list(prodotti)
    if L < 3:
        c, f = rng.choice(tutte)
        testo = (f"Bilancia: {_lato(reagenti, f, True)} → {_lato(prodotti, f, True)}. Che "
                 f"coefficiente va al posto del punto di domanda, davanti a "
                 f"{formula_scritta(f)}?")
        voce = (f"Bilancia la reazione: {_lato(reagenti, f, False)}, dà, "
                f"{_lato(prodotti, f, False)}. Che coefficiente va {_davanti(f)}?")
        sugg = ["Conta gli atomi di ogni elemento a sinistra e a destra della freccia: devono "
                "essere uguali.",
                f"Guarda un elemento che sta in {formula_scritta(f)} e conta quanti atomi ne "
                f"servono."]
    else:
        c, f = rng.choice([x for x in tutte if x[0] > 1])
        testo = (f"Bilancia con i coefficienti più piccoli: {_lato(reagenti, None, True, False)}"
                 f" → {_lato(prodotti, None, True, False)}. Che coefficiente va davanti a "
                 f"{formula_scritta(f)}?")
        voce = (f"Bilancia con i coefficienti più piccoli la reazione: "
                f"{_lato(reagenti, None, False, False)}, dà, "
                f"{_lato(prodotti, None, False, False)}. Che coefficiente va "
                f"{_davanti(f)}?")
        sugg = ["Di solito conviene bilanciare prima il carbonio, poi l'idrogeno, e "
                "l'ossigeno per ultimo.",
                "Conta gli atomi di ogni elemento ai due lati e cambia solo i coefficienti, mai "
                "i pedici."]
    completa = (" + ".join(f"{x} {formula_scritta(y)}" if x > 1 else formula_scritta(y)
                           for x, y in reagenti) + " → "
                + " + ".join(f"{x} {formula_scritta(y)}" if x > 1 else formula_scritta(y)
                             for x, y in prodotti))
    completa_detta = (" più ".join(f"{x} {formula_detta(y)}" if x > 1 else formula_detta(y)
                                   for x, y in reagenti) + ", dà, "
                      + " più ".join(f"{x} {formula_detta(y)}" if x > 1 else formula_detta(y)
                                     for x, y in prodotti))
    return Esercizio(MATERIA, "bilanciamento", L, seme, testo, voce, "valore", F(c), str(c),
                     sugg, f"La reazione bilanciata è: {completa_detta}. "
                           f"{_davanti(f).capitalize()} va {c}.", [], "",
                     {"reagenti": [[x, y] for x, y in reagenti],
                      "prodotti": [[x, y] for x, y in prodotti], "chiesto": f,
                      "completa": completa}, {"tipo": "calcolato"})


def _conta(reagenti, prodotti) -> tuple[dict, dict]:
    sx: dict[str, int] = {}
    dx: dict[str, int] = {}
    for lato, out in ((reagenti, sx), (prodotti, dx)):
        for c, f in lato:
            for el, n in atomi(f).items():
                out[el] = out.get(el, 0) + int(c) * n
    return sx, dx


def _rango(righe: list[list[F]]) -> int:
    m = [list(r) for r in righe]
    rango, col = 0, 0
    ncol = len(m[0]) if m else 0
    while rango < len(m) and col < ncol:
        piv = next((i for i in range(rango, len(m)) if m[i][col] != 0), None)
        if piv is None:
            col += 1
            continue
        m[rango], m[piv] = m[piv], m[rango]
        for i in range(len(m)):
            if i != rango and m[i][col] != 0:
                k = m[i][col] / m[rango][col]
                m[i] = [a - k * b for a, b in zip(m[i], m[rango])]
        rango += 1
        col += 1
    return rango


def verifica_bilanciamento(es: Esercizio) -> bool:
    reagenti = [(int(c), f) for c, f in es.dati["reagenti"]]
    prodotti = [(int(c), f) for c, f in es.dati["prodotti"]]
    chiesto = es.dati["chiesto"]
    sx, dx = _conta(reagenti, prodotti)
    if sx != dx:
        return False
    coeff = [c for c, _ in reagenti + prodotti]
    if math.gcd(*coeff) != 1:
        return False
    # Unico a meno di un fattore: la matrice degli atomi ha rango = specie − 1
    specie = [f for _, f in reagenti] + [f for _, f in prodotti]
    elementi = sorted(sx)
    righe = [[F(atomi(f).get(el, 0)) * (1 if i < len(reagenti) else -1)
              for i, f in enumerate(specie)] for el in elementi]
    if _rango(righe) != len(specie) - 1:
        return False
    # Il coefficiente chiesto: nessun altro valore bilancia con gli altri fermi
    giusto = next(c for c, f in reagenti + prodotti if f == chiesto)
    for prova in range(1, 21):
        if prova == giusto:
            continue
        r2 = [(prova if f == chiesto else c, f) for c, f in reagenti]
        p2 = [(prova if f == chiesto else c, f) for c, f in prodotti]
        a, b = _conta(r2, p2)
        if a == b:
            return False
    return F(giusto) == es.risposta


# ─────────────────────────── generazione, ricalcolo, correzione ───────────────────────────

GENERATORI = {"massa_molare": _massa_molare, "moli": _moli, "bilanciamento": _bilanciamento}


def verifica(es: Esercizio) -> bool:
    try:
        if es.argomento == "bilanciamento":
            return verifica_bilanciamento(es)
        if es.argomento == "massa_molare":
            # La formula riletta da capo deve dare la stessa massa molare
            if massa_molare(es.dati["formula"]) != es.risposta:
                return False
        return verifica_misura(es)
    except (ValueError, KeyError, TypeError):
        return False


def genera(argomento: str, livello: int, seme: int) -> Esercizio:
    rng = random.Random(f"{MATERIA}:{argomento}:{livello}:{seme}")
    es = GENERATORI[argomento](rng, max(1, min(3, int(livello))), seme)
    if not verifica(es):
        raise ValueError(f"esercizio {argomento}/{livello}/{seme}: il ricalcolo non torna")
    es.verifica = {"tipo": "calcolato", "ricalcolo": True}
    return es


def controlla(es: Esercizio, risposta) -> Esito:
    if es.tipo == "misura":
        return controlla_misura(es, risposta)
    v = leggi_valore(risposta)
    if v is None:
        return Esito(None, "", "Non ho capito il numero: dimmi il coefficiente.", False)
    letta = U.numero_scritto(v)
    if v == es.risposta:
        return Esito(True, letta)
    return Esito(False, letta, "Il coefficiente è un numero intero, senza virgola."
                 if v.denominator != 1 else "")


def livello_per(argomento: str, classe: Classe) -> int:
    return livello_da_classe(ARGOMENTI[argomento]["classi"], classe)
