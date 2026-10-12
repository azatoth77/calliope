"""
Esercizi di matematica generati al momento (08/10/2026, decisione di Dario del 07/10: tipo
«calcolabile»): operazioni, frazioni, problemi, potenze, equazioni di primo grado.

Ogni generatore è deterministico (`random.Random(seme)`) e costruisce l'esercizio **dalla
soluzione** (prima la x, poi l'equazione): niente esercizi senza soluzione intera quando non
servono. La risposta la calcola il codice; in più ogni esercizio porta l'espressione, che un
valutatore indipendente (`valuta`, frazioni esatte) rifà da capo: se i due conti non tornano
l'esercizio si scarta (`verifica`). Così un errore in un generatore non arriva mai al ragazzo.

I testi dei problemi usano nomi di fantasia, mai i nomi di casa.
"""

from __future__ import annotations

import ast
import math
import random
from fractions import Fraction

from .modello import Classe, Esercizio, Esito
from .numeri import ORDINALI_F, frazione_detta, frazione_scritta, leggi_frazione_scritta, \
    leggi_valore

MATERIA = "matematica"
VERIFICA = "calcolato"            # il codice rifà il conto (sessione: ricalcolo, scheda)

# Argomento → nome detto, parole con cui si chiede, classi (dalla, alla)
ARGOMENTI = {
    "addizioni": {"nome": "addizioni", "alias": ("addizion", "somm"),
                  "classi": (Classe("elementari", 1), Classe("medie", 1))},
    "sottrazioni": {"nome": "sottrazioni", "alias": ("sottrazion", "differenz"),
                    "classi": (Classe("elementari", 1), Classe("medie", 1))},
    "moltiplicazioni": {"nome": "moltiplicazioni e tabelline",
                        "alias": ("moltiplicazion", "tabellin", "prodott"),
                        "classi": (Classe("elementari", 2), Classe("medie", 1))},
    "divisioni": {"nome": "divisioni", "alias": ("division", "diviso", "quozient"),
                  "classi": (Classe("elementari", 3), Classe("medie", 1))},
    "frazioni": {"nome": "frazioni", "alias": ("frazion",),
                 "classi": (Classe("elementari", 3), Classe("medie", 3))},
    "problemi": {"nome": "problemi", "alias": ("problem",),
                 "classi": (Classe("elementari", 1), Classe("medie", 2))},
    "potenze": {"nome": "potenze", "alias": ("potenz", "elevat", "espon"),
                "classi": (Classe("medie", 1), Classe("superiori", 5))},
    "equazioni": {"nome": "equazioni di primo grado", "alias": ("equazion", "incognit"),
                  "classi": (Classe("medie", 3), Classe("superiori", 5))},
}

# Nomi di fantasia per i problemi (mai i nomi della casa)
NOMI = (("Marta", "f"), ("Tommaso", "m"), ("Giulia", "f"), ("Lorenzo", "m"), ("Ottavia", "f"),
        ("Matteo", "m"), ("Chiara", "f"), ("Filippo", "m"), ("Irene", "f"), ("Nicola", "m"))
COSE = ("figurine", "caramelle", "biglie", "matite", "mele", "conchiglie", "castagne",
        "pagine", "palline", "cartoline")


# ─────────────────────────── valutatore indipendente ───────────────────────────

def valuta(espressione: str, x: Fraction | None = None) -> Fraction:
    """Il valore esatto di un'espressione con + - * / ** e parentesi, interi e x. Solleva
    ValueError su tutto il resto (nomi, chiamate, divisione per zero)."""
    def v(n):
        if isinstance(n, ast.Expression):
            return v(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            return Fraction(n.value)
        if isinstance(n, ast.Name) and n.id == "x" and x is not None:
            return Fraction(x)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            r = v(n.operand)
            return -r if isinstance(n.op, ast.USub) else r
        if isinstance(n, ast.BinOp):
            a, b = v(n.left), v(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                if b == 0:
                    raise ValueError("divisione per zero")
                return a / b
            if isinstance(n.op, ast.Pow):
                if b.denominator != 1 or abs(b) > 20:
                    raise ValueError("esponente non ammesso")
                return a ** int(b)
        raise ValueError(f"non ammesso: {type(n).__name__}")
    return v(ast.parse(espressione, mode="eval"))


def verifica(es: Esercizio) -> bool:
    """Il conto rifatto dal valutatore torna con la risposta del generatore?"""
    try:
        if es.dati.get("confronto"):
            # Confronto: prodotti in croce, senza passare dalle frazioni
            (a, b), (c, d) = es.dati["confronto"]
            croce = valuta(f"{a}*{d}-{c}*{b}")
            giusta = Fraction(a, b) if croce > 0 else Fraction(c, d)
            return croce != 0 and giusta == es.risposta
        if "=" in es.espressione:
            sx, dx = es.espressione.split("=")
            return valuta(sx, es.risposta) == valuta(dx, es.risposta)
        return valuta(es.espressione) == Fraction(es.risposta)
    except (ValueError, ZeroDivisionError, SyntaxError, TypeError):
        return False


# ─────────────────────────── limiti del programma (12/10 sera) ───────────────────────────
# Decisione di Dario del 12/10 sera: il livello sta dentro la voce dell'indice del programma
# (calliope/esercizi/programma/), che per le operazioni dice «entro quale numero» e «con o senza
# cambio» (riporto o prestito). I generatori li ricevono come parametri; `rispetta` li ricontrolla
# sull'esercizio finito (anche le operazioni di un problema: un'interrogazione sulle addizioni non
# ha sottrazioni né moltiplicazioni) e un esercizio fuori limite non esce mai (ValueError).

# Gli argomenti per cui «entro» ha senso (il numero più grande, risultato compreso)
CON_ENTRO = ("addizioni", "sottrazioni", "moltiplicazioni", "divisioni", "problemi")
# Le operazioni dei generatori, per nome (le stesse parole dell'argomento)
OPERAZIONI = {"addizioni": "+", "sottrazioni": "-", "moltiplicazioni": "*", "divisioni": "/"}
TENTATIVI = 400


def riporto(a: int, b: int) -> bool:
    """L'addizione a + b ha almeno un riporto in colonna?"""
    a, b = abs(int(a)), abs(int(b))
    while a or b:
        if a % 10 + b % 10 >= 10:
            return True
        a, b = a // 10, b // 10
    return False


def prestito(a: int, b: int) -> bool:
    """La sottrazione a − b ha almeno un prestito in colonna?"""
    a, b = abs(int(a)), abs(int(b))
    while b:
        if a % 10 < b % 10:
            return True
        a, b = a // 10, b // 10
    return False


def _cambio_ok(ha_cambio: bool, cambio: bool | None) -> bool:
    """cambio None: indifferente; False: mai; True: sempre."""
    return cambio is None or ha_cambio == bool(cambio)


def operazioni_di(espressione: str) -> set[str]:
    """Le operazioni di un'espressione: {"+", "-", "*", "/", "**"} (senza «=»: il lato
    sinistro e il destro insieme)."""
    out: set[str] = set()
    simboli = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**"}
    for pezzo in str(espressione or "").split("="):
        if not pezzo.strip():
            continue
        try:
            albero = ast.parse(pezzo, mode="eval")
        except SyntaxError:
            continue
        for n in ast.walk(albero):
            if isinstance(n, ast.BinOp) and type(n.op) in simboli:
                out.add(simboli[type(n.op)])
    return out


def numeri_di(es: Esercizio) -> list[int]:
    """Gli interi dell'esercizio: quelli dell'espressione e il risultato."""
    out = []
    try:
        for n in ast.walk(ast.parse(es.espressione.split("=")[0] or "0", mode="eval")):
            if isinstance(n, ast.Constant) and isinstance(n.value, int):
                out.append(abs(n.value))
    except SyntaxError:
        pass
    r = es.risposta
    if isinstance(r, Fraction) and r.denominator == 1:
        out.append(abs(int(r)))
    return out


def rispetta(es: Esercizio, entro: int | None = None, cambio: bool | None = None,
             solo: set | frozenset | None = None) -> bool:
    """L'esercizio sta dentro il limite? `entro`: nessun numero (risultato compreso) oltre;
    `cambio`: riporto o prestito (addizioni e sottrazioni); `solo`: le operazioni ammesse (un
    problema in un'interrogazione su un'operazione sola)."""
    if entro and es.argomento in CON_ENTRO and any(n > entro for n in numeri_di(es)):
        return False
    if cambio is not None and es.argomento in ("addizioni", "sottrazioni"):
        a, b = es.dati.get("operandi", (0, 0))
        ha = riporto(a, b) if es.argomento == "addizioni" else prestito(a, b)
        if not _cambio_ok(ha, cambio):
            return False
    if solo and not operazioni_di(es.espressione) <= set(solo):
        return False
    return True


# ─────────────────────────── generatori ───────────────────────────

def _es(argomento, livello, seme, testo, voce, risposta, sugg, spieg, espressione,
        tipo="valore", **dati) -> Esercizio:
    r = Fraction(risposta)
    return Esercizio(MATERIA, argomento, livello, seme, testo, voce, tipo, r,
                     frazione_detta(r), list(sugg), spieg, [], espressione, dati,
                     {"tipo": "calcolato"})


def _scegli(rng: random.Random, estrai, va_bene, cosa: str):
    """Estrae finché `va_bene` (al più TENTATIVI volte): ValueError se il limite non lascia
    niente (mai con le voci dell'indice: lo controlla prova_esercizi_programma)."""
    for _ in range(TENTATIVI):
        x = estrai()
        if va_bene(*x):
            return x
    raise ValueError(f"nessun esercizio di {cosa} dentro il limite")


def _addizioni(rng: random.Random, L: int, seme: int, entro: int | None = None,
               cambio: bool | None = None) -> Esercizio:
    def estrai():
        if L == 1:
            a = rng.randint(2, 12)
            return a, rng.randint(1, 20 - a)
        if L == 2:
            return rng.randint(12, 89), rng.randint(11, 79)
        return rng.randint(120, 899), rng.randint(105, 899)
    a, b = _scegli(rng, estrai, lambda a, b: (not entro or a + b <= entro)
                   and _cambio_ok(riporto(a, b), cambio), "addizioni")
    s = a + b
    grande, piccolo = max(a, b), min(a, b)
    if L == 1:
        sugg = [f"Parti dal numero più grande, {grande}, e conta in avanti di {piccolo}.",
                f"Tieni {grande} in testa e alza {piccolo} dita, poi conta una a una."]
    else:
        ua, ub = a % 10, b % 10
        sugg = ["Somma prima le unità, poi le decine" + (", poi le centinaia." if L == 3 else "."),
                f"Le unità: {ua} più {ub} fa {ua + ub}" + (", scrivi l'unità e riporta 1 alle decine."
                                                         if ua + ub >= 10 else ".")]
    return _es("addizioni", L, seme, f"{a} + {b} = ?", f"Quanto fa {a} più {b}?", s, sugg,
               f"{a} più {b} fa {s}.", f"{a}+{b}", operandi=[a, b])


def _sottrazioni(rng, L, seme, entro=None, cambio=None):
    def estrai():
        if L == 1:
            a = rng.randint(5, 20)
            return a, rng.randint(1, a - 1)
        if L == 2:
            a = rng.randint(30, 99)
            return a, rng.randint(11, a - 5)
        a = rng.randint(300, 999)
        return a, rng.randint(101, a - 20)
    a, b = _scegli(rng, estrai, lambda a, b: (not entro or a <= entro)
                   and _cambio_ok(prestito(a, b), cambio), "sottrazioni")
    d = a - b
    if L == 1:
        sugg = [f"Parti da {a} e conta all'indietro di {b}.",
                f"Oppure pensa: quanto manca da {b} per arrivare a {a}?"]
    else:
        sugg = ["Togli prima le unità, poi le decine" + (", poi le centinaia." if L == 3 else "."),
                f"Se le unità di sopra ({a % 10}) sono meno di quelle di sotto ({b % 10}), prendi "
                f"in prestito una decina." if a % 10 < b % 10 else
                f"Le unità: {a % 10} meno {b % 10} fa {a % 10 - b % 10}."]
    return _es("sottrazioni", L, seme, f"{a} − {b} = ?", f"Quanto fa {a} meno {b}?", d, sugg,
               f"{a} meno {b} fa {d}: infatti {d} più {b} fa {a}.", f"{a}-{b}", operandi=[a, b])


def _moltiplicazioni(rng, L, seme, entro=None, cambio=None):
    def estrai():
        if L == 1:
            a, b = rng.randint(2, 5), rng.randint(1, 10)
        elif L == 2:
            a, b = rng.randint(3, 10), rng.randint(2, 10)
        else:
            a, b = rng.randint(12, 99), rng.randint(3, 9)
        if rng.random() < 0.5 and L < 3:
            a, b = b, a
        return a, b
    a, b = _scegli(rng, estrai, lambda a, b: not entro or a * b <= entro, "moltiplicazioni")
    p = a * b
    if L < 3:
        sugg = [f"È come sommare {b} volte il numero {a}.",
                f"Pensa alla tabellina del {a}: {a} per {b - 1} fa {a * (b - 1)}, poi aggiungi "
                f"ancora {a}." if b > 1 else f"Un numero per 1 resta uguale."]
    else:
        dec, un = a // 10 * 10, a % 10
        sugg = [f"Spezza {a} in {dec} più {un} e moltiplica i due pezzi per {b}.",
                f"{dec} per {b} fa {dec * b}; ora fai {un} per {b} e somma."]
    return _es("moltiplicazioni", L, seme, f"{a} × {b} = ?", f"Quanto fa {a} per {b}?", p, sugg,
               f"{a} per {b} fa {p}.", f"{a}*{b}")


def _divisioni(rng, L, seme, entro=None, cambio=None):
    def estrai():
        if L == 1:
            return rng.randint(2, 5), rng.randint(1, 10)
        if L == 2:
            return rng.randint(3, 10), rng.randint(2, 10)
        return rng.randint(2, 9), rng.randint(11, 99)
    d, q = _scegli(rng, estrai, lambda d, q: not entro or d * q <= entro, "divisioni")
    n = d * q
    sugg = [f"Pensa alla tabellina del {d}: quale numero moltiplicato per {d} fa {n}?",
            f"Prova con un numero e controlla: per esempio {d} per {max(1, q - 2)} fa "
            f"{d * max(1, q - 2)}, è ancora poco?" if q > 2 else
            f"{d} per 1 fa {d}: e {d} per 2?"]
    return _es("divisioni", L, seme, f"{n} : {d} = ?", f"Quanto fa {n} diviso {d}?", q, sugg,
               f"{n} diviso {d} fa {q}, perché {q} per {d} fa {n}.", f"{n}/{d}")


def _frazione_casuale(rng, den_max=12, propria=True):
    d = rng.randint(2, den_max)
    n = rng.randint(1, d - 1) if propria else rng.randint(1, 2 * d)
    return n, d


def _frazioni(rng, L, seme):
    tipo = rng.choice((("stesso", "equivalente") if L == 1 else
                       ("confronto", "semplifica", "stesso") if L == 2 else
                       ("diversi", "prodotto", "semplifica")))
    if tipo == "stesso":
        d = rng.randint(3, 12)
        a = rng.randint(1, d - 1)
        b = rng.randint(1, d - 1)
        meno = rng.random() < 0.4 and a != b
        if meno and a < b:
            a, b = b, a
        r = Fraction(a - b if meno else a + b, d)
        op, op_v = ("−", "meno") if meno else ("+", "più")
        return _es("frazioni", L, seme, f"{a}/{d} {op} {b}/{d} = ?",
                   f"Quanto fa {_fd(a, d)} {op_v} {_fd(b, d)}?", r,
                   ["Le frazioni hanno lo stesso denominatore: il denominatore resta quello.",
                    f"Fai {a} {op_v} {b} ai numeratori e lascia {d} sotto."],
                   f"Il denominatore resta {d}; {a} {op_v} {b} fa {a - b if meno else a + b}: "
                   f"{_fd(a - b if meno else a + b, d)}"
                   + (f", cioè {frazione_detta(r)}." if r.denominator != d else "."),
                   f"{a}/{d}{'-' if meno else '+'}{b}/{d}", errore_tipico="denominatori")
    if tipo == "equivalente":
        n, d = _frazione_casuale(rng, 6)
        k = rng.randint(2, 5)
        return Esercizio(MATERIA, "frazioni", L, seme, f"{n}/{d} = ?/{d * k}",
                         f"{_fd(n, d).capitalize()} è uguale a quanti {_den(d * k)}?",
                         "valore", Fraction(n * k), str(n * k),
                         [f"Il denominatore è passato da {d} a {d * k}: per quanto l'hai "
                          f"moltiplicato?",
                          f"{d} per {k} fa {d * k}: fai la stessa cosa al numeratore {n}."],
                         f"Il denominatore è moltiplicato per {k}, quindi anche il numeratore: "
                         f"{n} per {k} fa {n * k}.", [], f"{n}*{d * k}/{d}", {},
                         {"tipo": "calcolato"})
    if tipo == "confronto":
        while True:
            a, b = _frazione_casuale(rng, 9), _frazione_casuale(rng, 9)
            fa, fb = Fraction(*a), Fraction(*b)
            if fa != fb and a[1] != b[1] and fa.denominator == a[1] and fb.denominator == b[1]:
                break
        r = max(fa, fb)
        return _es("frazioni", L, seme, f"Qual è la più grande: {a[0]}/{a[1]} o {b[0]}/{b[1]}?",
                   f"Qual è la frazione più grande: {_fd(*a)} o {_fd(*b)}?", r,
                   ["Per confrontarle, portale allo stesso denominatore.",
                    f"Un denominatore comune è {a[1] * b[1] // math.gcd(a[1], b[1])}."],
                   f"Con lo stesso denominatore si vede che la più grande è {frazione_detta(r)}.",
                   "", confronto=[[*a], [*b]])
    if tipo == "semplifica":
        n, d = _frazione_casuale(rng, 9)
        f = Fraction(n, d)
        k = rng.randint(2, 6)
        n2, d2 = f.numerator * k, f.denominator * k
        return Esercizio(MATERIA, "frazioni", L, seme, f"Semplifica: {n2}/{d2}",
                         f"Semplifica la frazione {_fd(n2, d2)}: quanto viene, ridotta ai minimi "
                         f"termini?", "frazione_ridotta", f, frazione_detta(f),
                         [f"Cerca un numero che divida sia {n2} sia {d2}.",
                          f"Prova a dividere tutti e due per {math.gcd(n2, d2)}."],
                         f"Il massimo comune divisore di {n2} e {d2} è {math.gcd(n2, d2)}: "
                         f"dividendo si ottiene {frazione_detta(f)}.", [], f"{n2}/{d2}", {},
                         {"tipo": "calcolato"})
    if tipo == "diversi":
        while True:
            a, b = _frazione_casuale(rng, 8), _frazione_casuale(rng, 8)
            if a[1] != b[1]:
                break
        meno = rng.random() < 0.4 and Fraction(*a) > Fraction(*b)
        r = Fraction(*a) - Fraction(*b) if meno else Fraction(*a) + Fraction(*b)
        mcm = a[1] * b[1] // math.gcd(a[1], b[1])
        op, op_v = ("−", "meno") if meno else ("+", "più")
        return _es("frazioni", L, seme, f"{a[0]}/{a[1]} {op} {b[0]}/{b[1]} = ?",
                   f"Quanto fa {_fd(*a)} {op_v} {_fd(*b)}?", r,
                   [f"I denominatori sono diversi: trova il minimo comune multiplo di {a[1]} e "
                    f"{b[1]}.", f"Il minimo comune multiplo è {mcm}: trasforma le due frazioni "
                    f"in {_den(mcm)}."],
                   f"Con denominatore {mcm}: {_fd(a[0] * mcm // a[1], mcm)} {op_v} "
                   f"{_fd(b[0] * mcm // b[1], mcm)} fa {frazione_detta(r)}.",
                   f"{a[0]}/{a[1]}{'-' if meno else '+'}{b[0]}/{b[1]}",
                   errore_tipico="denominatori")
    # prodotto
    a, b = _frazione_casuale(rng, 7), _frazione_casuale(rng, 7)
    r = Fraction(*a) * Fraction(*b)
    return _es("frazioni", L, seme, f"{a[0]}/{a[1]} × {b[0]}/{b[1]} = ?",
               f"Quanto fa {_fd(*a)} per {_fd(*b)}?", r,
               ["Nella moltiplicazione tra frazioni non serve il denominatore comune.",
                "Moltiplica i numeratori tra loro e i denominatori tra loro, poi semplifica."],
               f"{a[0]} per {b[0]} sopra, {a[1]} per {b[1]} sotto: viene {frazione_detta(r)}.",
               f"{a[0]}/{a[1]}*{b[0]}/{b[1]}")


def _fd(n, d) -> str:
    """Una frazione detta così com'è scritta (6 ottavi, non 3 quarti)."""
    if n == 1:
        return "un " + _den(d, False)
    return f"{n} {_den(d)}"


def _den(d, plurale=True) -> str:
    from .numeri import denominatore_parola
    return denominatore_parola(d, plurale)


# I problemi per livello, con le operazioni che usano (12/10 sera: un'interrogazione sulle
# addizioni sceglie solo quelli con «+»). Ogni modello riceve (rng, nome, g, nome2, cose) e
# restituisce (testo, risposta, indizi, spiegazione, espressione).
def _p_riceve(rng, nome, g, nome2, cose):
    a, b = rng.randint(3, 12), rng.randint(2, 8)
    return (f"{nome} ha {a} {cose}. Ne riceve altre {b}. Quante {cose} ha adesso?", a + b,
            ["Le cose aumentano o diminuiscono?", f"Aumentano: devi fare {a} più {b}."],
            f"Le {cose} aumentano: {a} più {b} fa {a + b}.", f"{a}+{b}")


def _p_regala(rng, nome, g, nome2, cose, grandi=False):
    if grandi:
        a = rng.randint(30, 99)
        b = rng.randint(11, a - 6)
    else:
        a = rng.randint(6, 18)
        b = rng.randint(2, a - 2)
    gli = "le" if g == "f" else "gli"
    return (f"{nome} ha {a} {cose} e ne regala {b} a {nome2}. Quante {cose} {gli} restano?",
            a - b, ["Le cose aumentano o diminuiscono?", f"Diminuiscono: devi fare {a} meno {b}."],
            f"Le {cose} diminuiscono: {a} meno {b} fa {a - b}.", f"{a}-{b}")


def _p_regala_grandi(rng, nome, g, nome2, cose):
    return _p_regala(rng, nome, g, nome2, cose, grandi=True)


def _p_insieme(rng, nome, g, nome2, cose):
    a, b = rng.randint(12, 59), rng.randint(11, 39)
    return (f"{nome} ha {a} {cose} e {nome2} ne ha {b}. Quante {cose} hanno in tutto?", a + b,
            ["In tutto: le metti insieme o ne togli?", f"Le metti insieme: {a} più {b}."],
            f"In tutto: {a} più {b} fa {a + b}.", f"{a}+{b}")


def _p_file(rng, nome, g, nome2, cose):
    a, b = rng.randint(3, 9), rng.randint(3, 9)
    return (f"In una scatola ci sono {a} file di {b} {cose} ciascuna. Quante {cose} ci sono in "
            f"tutto?", a * b,
            [f"Ogni fila ha {b} {cose}, e le file sono {a}.",
             f"Puoi fare {b} più {b} per {a} volte, o più in fretta {a} per {b}."],
            f"{a} file da {b}: {a} per {b} fa {a * b}.", f"{a}*{b}")


def _p_divide(rng, nome, g, nome2, cose):
    b, q = rng.randint(2, 6), rng.randint(2, 9)
    a = b * q
    return (f"{nome} divide {a} {cose} in parti uguali tra {b} amici. Quante {cose} riceve ogni "
            f"amico?", q,
            ["Parti uguali: che operazione serve?", f"Serve una divisione: {a} diviso {b}."],
            f"In parti uguali: {a} diviso {b} fa {q}.", f"{a}/{b}")


def _p_quaderni(rng, nome, g, nome2, cose):
    n, p = rng.randint(2, 6), rng.randint(2, 4)
    t = rng.choice([x for x in (10, 20, 50) if x > n * p])
    return (f"{nome} compra {n} quaderni da {p} euro l'uno e paga con {t} euro. Quanti euro "
            f"riceve di resto?", t - n * p,
            ["Prima calcola quanto spende in tutto.",
             f"Spende {n} per {p} euro; poi togli la spesa dai {t} euro."],
            f"Spende {n} per {p}, cioè {n * p} euro; {t} meno {n * p} fa {t - n * p}.",
            f"{t}-{n}*{p}")


def _p_pullman(rng, nome, g, nome2, cose):
    a = rng.randint(30, 54)
    b, c = rng.randint(5, 14), rng.randint(5, 14)
    return (f"Un pullman ha {a} posti. Alla prima fermata salgono {b} bambini e alla seconda "
            f"{c}. Quanti posti restano liberi?", a - b - c,
            ["Prima conta quanti bambini salgono in tutto.",
             f"Salgono {b} più {c} bambini: toglili dai {a} posti."],
            f"Salgono {b} più {c}, cioè {b + c} bambini; {a} meno {b + c} fa {a - b - c}.",
            f"{a}-{b}-{c}")


def _p_gita(rng, nome, g, nome2, cose):
    a, b, c = rng.randint(18, 55), rng.randint(18, 55), rng.randint(18, 55)
    return (f"Alla gita vanno {a} bambini sul primo pullman, {b} sul secondo e {c} sul terzo. "
            f"Quanti bambini vanno alla gita in tutto?", a + b + c,
            ["Devi mettere insieme i bambini dei tre pullman.",
             f"Prima {a} più {b}, poi aggiungi {c}."],
            f"{a} più {b} fa {a + b}, più {c} fa {a + b + c}.", f"{a}+{b}+{c}")


def _p_scaffali(rng, nome, g, nome2, cose):
    a, b = rng.randint(12, 40), rng.randint(3, 9)
    return (f"In biblioteca ci sono {b} scaffali con {a} libri ciascuno. Quanti libri ci sono "
            f"in tutto?", a * b,
            [f"Ogni scaffale ha {a} libri, e gli scaffali sono {b}.",
             f"Fai {a} per {b}: spezza {a} in decine e unità."],
            f"{b} scaffali da {a}: {a} per {b} fa {a * b}.", f"{a}*{b}")


# livello → modelli (le operazioni stanno nell'espressione: le ricontrolla `rispetta`)
PROBLEMI = {1: (_p_riceve, _p_regala),
            2: (_p_file, _p_divide, _p_insieme, _p_regala_grandi),
            3: (_p_quaderni, _p_pullman, _p_gita, _p_scaffali)}


def _problemi(rng, L, seme, entro=None, cambio=None, solo=None):
    """Un problema del livello (o, se nessun modello del livello sta nel limite, del livello
    sotto), dentro `entro`, con le sole operazioni di `solo`."""
    for lv in range(L, 0, -1):
        modelli = list(PROBLEMI[lv])
        for _ in range(TENTATIVI // 4):
            nome, g = rng.choice(NOMI)
            nome2 = rng.choice([n for n, _ in NOMI if n != nome])
            cose = rng.choice(COSE)
            testo, r, sugg, spieg, espr = rng.choice(modelli)(rng, nome, g, nome2, cose)
            es = _es("problemi", lv, seme, testo, testo, r, sugg, spieg, espr)
            if rispetta(es, entro, None, solo):
                return es
    raise ValueError("nessun problema dentro il limite")


_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _alla(n: int) -> str:
    """«alla terza», «alla 12», «alla meno 3»."""
    if n < 0:
        return f"alla meno {-n}"
    return f"alla {ORDINALI_F.get(n, str(n))}"


def _potenze(rng, L, seme):
    if L == 1:
        a = rng.choice((2, 2, 3, 3, 4, 5, 10))
        n = rng.randint(2, 4 if a < 10 else 5)
        r = a ** n
        return _es("potenze", L, seme, f"{a}{str(n).translate(_SUP)} = ?",
                   f"Quanto fa {a} elevato {_alla(n)}?", r,
                   [f"Elevare {_alla(n)} vuol dire moltiplicare {a} per sé stesso {n} volte.",
                    f"{a} per {a} fa {a * a}" + (f", poi continua per {n - 2} volte ancora."
                                                 if n > 2 else ".")],
                   f"{' per '.join([str(a)] * n)} fa {r}.", f"{a}**{n}")
    if L == 2:
        a = rng.randint(2, 9)
        m, n = rng.randint(2, 7), rng.randint(2, 6)
        tipo = rng.choice(("prodotto", "quoziente", "potenza"))
        if tipo == "quoziente" and m <= n:
            m, n = n + rng.randint(1, 3), m
        if tipo == "prodotto":
            r, testo = m + n, f"{a}{str(m).translate(_SUP)} · {a}{str(n).translate(_SUP)} = {a}ⁿ"
            voce = f"{a} {_alla(m)} per {a} {_alla(n)} fa {a} elevato a quanto?"
            regola = "con la stessa base, nel prodotto gli esponenti si sommano"
            espr = f"{m}+{n}"
        elif tipo == "quoziente":
            r, testo = m - n, f"{a}{str(m).translate(_SUP)} : {a}{str(n).translate(_SUP)} = {a}ⁿ"
            voce = f"{a} {_alla(m)} diviso {a} {_alla(n)} fa {a} elevato a quanto?"
            regola = "con la stessa base, nella divisione gli esponenti si sottraggono"
            espr = f"{m}-{n}"
        else:
            r, testo = m * n, f"({a}{str(m).translate(_SUP)}){str(n).translate(_SUP)} = {a}ⁿ"
            voce = f"{a} {_alla(m)}, tutto elevato {_alla(n)}, fa {a} elevato a quanto?"
            regola = "la potenza di una potenza moltiplica gli esponenti"
            espr = f"{m}*{n}"
        return _es("potenze", L, seme, testo + "  (quanto vale n?)", voce, r,
                   ["Non serve calcolare le potenze: basta una proprietà.",
                    f"Ricorda: {regola}."],
                   f"{regola[0].upper() + regola[1:]}: l'esponente è {r}.", espr,
                   proprieta=tipo)
    # Livello 3 (superiori): esponente zero o negativo, base frazionaria
    tipo = rng.choice(("negativo", "frazione", "zero"))
    if tipo == "negativo":
        a, n = rng.choice((2, 3, 4, 5, 10)), rng.randint(1, 3)
        r = Fraction(1, a ** n)
        return _es("potenze", L, seme, f"{a}{str(-n).translate(_SUP)} = ?",
                   f"Quanto fa {a} elevato {_alla(-n)}?", r,
                   ["Un esponente negativo vuol dire: il reciproco.",
                    f"{a} {_alla(-n)} è uguale a uno fratto {a} {_alla(n)}."],
                   f"È il reciproco di {a} {_alla(n)}, cioè {frazione_detta(r)}.",
                   f"{a}**(-{n})")
    if tipo == "frazione":
        n, d = _frazione_casuale(rng, 5)
        e = rng.randint(2, 3)
        r = Fraction(n, d) ** e
        return _es("potenze", L, seme, f"({n}/{d}){str(e).translate(_SUP)} = ?",
                   f"Quanto fa {_fd(n, d)}, tutto elevato {_alla(e)}?", r,
                   ["Si eleva sia il numeratore sia il denominatore.",
                    f"Fai {n} {_alla(e)} sopra e {d} {_alla(e)} sotto."],
                   f"{n} {_alla(e)} fa {n ** e}, {d} {_alla(e)} fa {d ** e}: "
                   f"{frazione_detta(r)}.", f"({n}/{d})**{e}")
    a = rng.randint(2, 99)
    return _es("potenze", L, seme, f"{a}⁰ = ?", f"Quanto fa {a} elevato alla zero?", 1,
               ["Pensa a una divisione tra due potenze uguali.",
                f"{a} {_alla(3)} diviso {a} {_alla(3)}: quanto fa? E che esponente viene?"],
               "Ogni numero diverso da zero elevato alla zero fa 1.", f"{a}**0")


def _x(coef: int, primo: bool = True) -> tuple[str, str]:
    """(scritto, detto) di un termine in x: «3x», «−x», «3 ics»."""
    if coef == 1:
        return ("x", "ics") if primo else ("+ x", "più ics")
    if coef == -1:
        return ("−x", "meno ics") if primo else ("− x", "meno ics")
    if primo:
        return (f"{coef}x".replace("-", "−"), f"{'meno ' if coef < 0 else ''}{abs(coef)} ics")
    return (f"{'−' if coef < 0 else '+'} {abs(coef)}x",
            f"{'meno' if coef < 0 else 'più'} {abs(coef)} ics")


def _il(n: int) -> str:
    """«il 5», «l'8», «l'11»: l'articolo davanti a un numero."""
    from .numeri import in_lettere
    return ("l'" if in_lettere(n)[0] in "aeiou" else "il ") + str(n)


def _v(n) -> str:
    """Un intero detto: «meno 11» invece di «-11»."""
    return f"meno {abs(n)}" if n < 0 else str(n)


def _n(c: int) -> tuple[str, str]:
    return (f"{'−' if c < 0 else '+'} {abs(c)}", f"{'meno' if c < 0 else 'più'} {abs(c)}")


def _equazioni(rng, L, seme):
    if L == 1:
        a, x = rng.randint(2, 9), rng.randint(1, 10)
        b = rng.choice([i for i in range(-15, 16) if i])
        c = a * x + b
        xs, xv = _x(a)
        bs, bv = _n(b)
        testo = f"{xs} {bs} = {c}".replace("-", "−")
        voce = f"Risolvi: {xv} {bv} uguale {_v(c)}. Quanto vale ics?"
        sugg = [f"Porta {_il(abs(b))} dall'altra parte dell'uguale, cambiandogli il segno.",
                f"Ti resta {a} ics uguale {_v(c - b)}: ora dividi per {a}."]
        spieg = (f"Sposto {bv.split()[-1]}: {a} ics uguale {c} {'meno' if b > 0 else 'più'} "
                 f"{abs(b)}, cioè {_v(c - b)}; divido per {a}: ics uguale {_v(x)}.")
        espr = f"{a}*x+({b})={c}"
    elif L == 2:
        x = rng.randint(-6, 8)
        a, c = rng.randint(2, 9), rng.randint(1, 7)
        if a == c:
            a += 1
        b = rng.randint(-12, 12)
        d = a * x + b - c * x
        xs, xv = _x(a)
        bs, bv = _n(b) if b else ("", "")
        cs, cv = _x(c)
        ds, dv = _n(d) if d else ("", "")
        testo = f"{xs} {bs} = {cs} {ds}".replace("  ", " ").replace("-", "−").strip()
        voce = f"Risolvi: {xv} {bv} uguale {cv} {dv}. Quanto vale ics?".replace("  ", " ")
        sugg = ["Porta i termini con la ics a sinistra e i numeri a destra, cambiando il segno "
                "a ciò che sposti.",
                f"Ti viene {_v(a - c)} ics uguale {_v(d - b)}: ora dividi."]
        spieg = (f"Raccolgo le ics a sinistra: {a} meno {c} fa {_v(a - c)} ics; i numeri a destra: "
                 f"{_v(d)} meno {_v(b)} fa {_v(d - b)}. Quindi ics uguale {frazione_detta(Fraction(d - b, a - c))}.")
        espr = f"{a}*x+({b})={c}*x+({d})"
    else:
        a = rng.choice((2, 3, 4, 5, 6))
        p = rng.choice([i for i in range(-9, 10) if i and i % a])
        x = Fraction(p, a)
        b = rng.choice([i for i in range(-9, 10) if i])
        c = a * x + b                                      # intero: a·(p/a) = p
        xs, xv = _x(a)
        bs, bv = _n(b)
        testo = f"{xs} {bs} = {int(c)}".replace("-", "−")
        voce = f"Risolvi: {xv} {bv} uguale {_v(int(c))}. Quanto vale ics?"
        sugg = [f"Porta {_il(abs(b))} dall'altra parte, cambiandogli il segno.",
                f"Ti resta {a} ics uguale {_v(int(c) - b)}: la divisione non viene intera, lascia "
                f"una frazione."]
        spieg = (f"{a} ics uguale {_v(int(c) - b)}, quindi ics uguale {_v(int(c) - b)} fratto {a}, cioè "
                 f"{frazione_detta(x)}.")
        espr = f"{a}*x+({b})={int(c)}"
    return _es("equazioni", L, seme, testo, voce, x, sugg, spieg, espr)


GENERATORI = {"addizioni": _addizioni, "sottrazioni": _sottrazioni,
              "moltiplicazioni": _moltiplicazioni, "divisioni": _divisioni,
              "frazioni": _frazioni, "problemi": _problemi, "potenze": _potenze,
              "equazioni": _equazioni}


def genera(argomento: str, livello: int, seme: int, entro: int | None = None,
           cambio: bool | None = None, solo=None) -> Esercizio:
    """L'esercizio di quel seme; ValueError se il ricalcolo non torna (mai, se i generatori
    sono giusti: lo controlla prova_esercizi su migliaia di semi) o se esce dal limite del
    programma (`entro`, `cambio`, `solo`: vedi `rispetta`)."""
    rng = random.Random(f"{argomento}:{livello}:{seme}")
    L = max(1, min(3, int(livello)))
    if argomento in OPERAZIONI:
        es = GENERATORI[argomento](rng, L, seme, entro=entro, cambio=cambio)
    elif argomento == "problemi":
        es = _problemi(rng, L, seme, entro=entro, solo=solo)
    else:
        es = GENERATORI[argomento](rng, L, seme)
    if not verifica(es):
        raise ValueError(f"esercizio {argomento}/{livello}/{seme}: il ricalcolo non torna")
    if not rispetta(es, entro, cambio, solo):
        raise ValueError(f"esercizio {argomento}/{livello}/{seme}: fuori dal limite")
    es.verifica = {"tipo": "calcolato", "ricalcolo": True}
    return es


# ─────────────────────────── correzione ───────────────────────────

def controlla(es: Esercizio, risposta) -> Esito:
    v = leggi_valore(risposta)
    if v is None:
        return Esito(None, "", "Non ho capito il numero: dimmelo o scrivilo in cifre.", False)
    letta = frazione_scritta(v)
    if v == es.risposta:
        if es.tipo == "frazione_ridotta":
            nd = leggi_frazione_scritta(risposta)
            if nd and nd[1] and math.gcd(*nd) > 1:
                return Esito(False, f"{nd[0]}/{nd[1]}",
                             "È uguale, ma si può semplificare ancora.", False)
        nota = ""
        if es.argomento == "frazioni" and v.denominator > 1:
            nd = leggi_frazione_scritta(risposta)
            if nd and nd[1] and math.gcd(*nd) > 1:
                nota = f"Giusto! Si poteva anche semplificare: {frazione_detta(v)}."
        return Esito(True, letta, nota)
    nota = ""
    if es.dati.get("errore_tipico") == "denominatori":
        nota = "Attenzione: i denominatori non si sommano e non si sottraggono."
    elif v == -es.risposta and v != 0:
        nota = "Controlla il segno."
    return Esito(False, letta, nota)


def livello_per(argomento: str, classe: Classe) -> int:
    """Il livello da cui partire per la classe: 1 all'inizio dell'intervallo
    dell'argomento, 3 alla fine."""
    da, a = ARGOMENTI[argomento]["classi"]
    if classe.indice <= da.indice:
        return 1
    if classe.indice >= a.indice:
        return 3
    pos = (classe.indice - da.indice) / max(1, a.indice - da.indice)
    return 1 if pos < 0.34 else 2 if pos < 0.67 else 3
