"""
Esercizi di logica (12/10/2026, materie calcolabili, S1 della roadmap): sequenze di numeri,
insiemi, vero o falso con i connettivi.

Stesso schema della matematica: generatori deterministici dal seme, risposta calcolata dal
codice, ricalcolo indipendente:

- **sequenze**: il generatore usa la sua regola; il ricalcolo non la conosce e prova da capo un
  catalogo di regole sui soli numeri mostrati (ricorrenza `a·x + b`, differenze seconde
  costanti, differenze che si alternano, somma dei due precedenti). Ogni regola che spiega i
  numeri deve dare lo **stesso** numero dopo, e quello deve essere la risposta: una sequenza
  ambigua (due continuazioni sensate) non nasce;
- **insiemi**: il generatore costruisce le parti (solo A, solo B, tutte e due, nessuna); il
  ricalcolo rifà il conto con gli insiemi veri (elementi elencati) o con la formula di
  inclusione ed esclusione dai soli numeri detti;
- **vero o falso**: il generatore calcola il valore con la sua funzione; il ricalcolo valuta la
  formula scritta (`A and not B`…) con un valutatore a parte. Per evitare l'ambiguità dell'«o»
  italiano (inclusivo o esclusivo) le frasi con «o» non hanno mai le due parti vere.

La risposta di vero o falso si legge con `leggi_vero_falso` («vero», «è falsa», «non è vero» →
falso; due risposte diverse nella stessa frase → non capita, non conta).
"""

from __future__ import annotations

import ast
import random
import re
import unicodedata
from fractions import Fraction as F

from .modello import Classe, Esercizio, Esito, livello_da_classe
from .numeri import leggi_valore

MATERIA = "logica"
VERIFICA = "calcolato"

ARGOMENTI = {
    "sequenze": {"nome": "sequenze di numeri", "alias": ("sequenz", "successio", "serie",
                                                          "numero dopo", "prossimo numero"),
                 "classi": (Classe("elementari", 2), Classe("superiori", 2))},
    "insiemi": {"nome": "insiemi", "alias": ("insiem", "venn", "intersezion", "union"),
                "classi": (Classe("elementari", 3), Classe("superiori", 1))},
    "vero_falso": {"nome": "vero o falso con i connettivi",
                   "alias": ("vero o falso", "vero e falso", "connettiv", "tavol",
                             "proposizion"),
                   "classi": (Classe("elementari", 4), Classe("superiori", 5))},
}

NOMI = ("Marta", "Tommaso", "Giulia", "Lorenzo", "Ottavia", "Matteo", "Chiara", "Filippo")


# ─────────────────────────── sequenze ───────────────────────────

def _prossimi(termini: list[int]) -> set:
    """Il numero dopo secondo ogni regola del catalogo che spiega tutti i termini mostrati."""
    t = [F(x) for x in termini]
    out = set()
    # Ricorrenza del primo ordine a(n+1) = p·a(n) + q (aritmetiche, geometriche, «×2 + 1»)
    if t[1] != t[0]:
        p = (t[2] - t[1]) / (t[1] - t[0])
        q = t[1] - p * t[0]
        if all(t[i + 1] == p * t[i] + q for i in range(len(t) - 1)):
            out.add(p * t[-1] + q)
    elif all(x == t[0] for x in t):
        out.add(t[0])
    # Differenze seconde costanti (quadrati, numeri triangolari, «+1, +2, +3…»)
    d = [t[i + 1] - t[i] for i in range(len(t) - 1)]
    d2 = [d[i + 1] - d[i] for i in range(len(d) - 1)]
    if all(x == d2[0] for x in d2):
        out.add(t[-1] + d[-1] + d2[0])
    # Differenze che si alternano (+a, +b, +a, +b…)
    if len(d) >= 4 and all(d[i] == d[i % 2] for i in range(len(d))):
        out.add(t[-1] + d[len(d) % 2])
    # Ogni numero è la somma dei due precedenti
    if all(t[i] == t[i - 1] + t[i - 2] for i in range(2, len(t))):
        out.add(t[-1] + t[-2])
    return out


def _sequenze(rng: random.Random, L: int, seme: int) -> Esercizio:
    for _ in range(50):
        if L == 1:
            a, d = rng.randint(0, 20), rng.randint(2, 10)
            seq = [a + d * i for i in range(6)]
            regola = f"ogni volta si aggiunge {d}"
            sugg = ["Guarda di quanto cresce ogni numero rispetto a quello prima.",
                    f"Fai la differenza tra il secondo e il primo: {seq[1]} meno {seq[0]}."]
        elif L == 2:
            tipo = rng.choice(("giu", "per", "alterna"))
            if tipo == "giu":
                d = rng.randint(3, 12)
                a = rng.randint(5 * d, 9 * d)
                seq = [a - d * i for i in range(6)]
                regola = f"ogni volta si toglie {d}"
                sugg = ["I numeri diminuiscono: di quanto ogni volta?",
                        f"Fai {seq[0]} meno {seq[1]}."]
            elif tipo == "per":
                k = rng.choice((2, 3))
                a = rng.randint(1, 5)
                seq = [a * k ** i for i in range(6)]
                regola = f"ogni numero è il precedente per {k}"
                sugg = ["Non si aggiunge sempre lo stesso numero: prova con una moltiplicazione.",
                        f"Quante volte {seq[1]} sta in {seq[2]}?"]
            else:
                x, y = rng.sample(range(1, 10), 2)
                a = rng.randint(1, 15)
                seq = [a]
                for i in range(5):
                    seq.append(seq[-1] + (x if i % 2 == 0 else y))
                regola = f"si aggiunge una volta {x} e una volta {y}"
                sugg = ["Le differenze tra un numero e il successivo non sono tutte uguali, ma "
                        "si ripetono.", "Scrivi le differenze: più quanto, più quanto…?"]
        else:
            tipo = rng.choice(("quadrati", "crescente", "fibonacci", "doppio_piu"))
            if tipo == "quadrati":
                s = rng.randint(1, 5)
                seq = [(s + i) ** 2 for i in range(6)]
                regola = "sono i quadrati dei numeri uno dopo l'altro"
                sugg = ["Prova a pensare ai numeri moltiplicati per sé stessi.",
                        f"{seq[0]} è {s} per {s}."]
            elif tipo == "crescente":
                a, d0 = rng.randint(1, 10), rng.randint(1, 4)
                seq = [a]
                for i in range(5):
                    seq.append(seq[-1] + d0 + i)
                regola = f"si aggiunge {d0}, poi {d0 + 1}, poi {d0 + 2}, e così via"
                sugg = ["Scrivi le differenze tra un numero e il successivo.",
                        "Le differenze crescono di uno ogni volta."]
            elif tipo == "fibonacci":
                a, b = rng.randint(1, 5), rng.randint(1, 6)
                seq = [a, b]
                for _i in range(4):
                    seq.append(seq[-1] + seq[-2])
                regola = "ogni numero è la somma dei due prima"
                sugg = ["Prova a sommare due numeri vicini.",
                        f"{seq[2]} è {seq[0]} più {seq[1]}."]
            else:
                a = rng.randint(1, 5)
                seq = [a]
                for _i in range(5):
                    seq.append(seq[-1] * 2 + 1)
                regola = "ogni numero è il doppio del precedente più uno"
                sugg = ["I numeri crescono sempre di più: prova a raddoppiare.",
                        f"{seq[0]} per 2 fa {seq[0] * 2}: e poi?"]
        mostrati, dopo = seq[:-1], seq[-1]
        if _prossimi(mostrati) == {F(dopo)}:
            break
    elenco = ", ".join(str(x) for x in mostrati)
    return Esercizio(MATERIA, "sequenze", L, seme, f"{elenco}, ? (qual è il numero dopo?)",
                     f"Qual è il numero che viene dopo in questa sequenza: {elenco}?", "valore",
                     F(dopo), str(dopo), sugg, f"La regola è: {regola}. Quindi dopo {seq[-2]} "
                                              f"viene {dopo}.", [], "",
                     {"sequenza": mostrati}, {"tipo": "calcolato"})


# ─────────────────────────── insiemi ───────────────────────────

def _insiemi(rng: random.Random, L: int, seme: int) -> Esercizio:
    if L == 1:
        comuni = rng.sample(range(1, 30), rng.randint(1, 3))
        resto = [x for x in range(1, 30) if x not in comuni]
        solo_a = rng.sample(resto, rng.randint(2, 4))
        resto = [x for x in resto if x not in solo_a]
        solo_b = rng.sample(resto, rng.randint(1, 3))
        A, B = sorted(comuni + solo_a), sorted(comuni + solo_b)
        domanda = rng.choice(("intersezione", "unione"))
        if domanda == "intersezione":
            r = len(comuni)
            chiedi, chiedi_v = ("Quanti numeri stanno sia in A sia in B?",) * 2
            sugg = ["Cerca i numeri che compaiono in tutti e due gli elenchi.",
                    "Prendi i numeri di B uno per uno e guarda se ci sono anche in A."]
            spieg = (f"I numeri in comune sono {', '.join(map(str, sorted(comuni)))}: "
                     f"sono {r}.")
        else:
            r = len(comuni) + len(solo_a) + len(solo_b)
            chiedi = chiedi_v = "Quanti numeri diversi ci sono mettendo insieme A e B?"
            sugg = ["Conta tutti i numeri di A, poi aggiungi quelli di B che non sono già in A.",
                    "Attenzione: i numeri che stanno in tutti e due si contano una volta sola."]
            spieg = (f"A ha {len(A)} numeri, B ne aggiunge {len(solo_b)} nuovi: in tutto "
                     f"{r}.")
        return Esercizio(MATERIA, "insiemi", L, seme,
                         f"A = {{{', '.join(map(str, A))}}}, B = {{{', '.join(map(str, B))}}}. "
                         f"{chiedi}",
                         f"Nell'insieme A ci sono i numeri {', '.join(map(str, A))}. Nell'insieme "
                         f"B ci sono {', '.join(map(str, B))}. {chiedi_v}", "valore", F(r), str(r),
                         sugg, spieg, [], "", {"A": A, "B": B, "domanda": domanda},
                         {"tipo": "calcolato"})
    a_cosa, b_cosa = rng.choice((("a calcio", "a pallavolo"), ("il pianoforte", "la chitarra"),
                                 ("nuoto", "danza"), ("l'inglese", "il francese")))
    verbo = "suonano" if "pianoforte" in a_cosa else ("studiano" if "inglese" in a_cosa else
                                                      "fanno" if a_cosa == "nuoto" else "giocano")
    solo_a, solo_b = rng.randint(3, 12), rng.randint(3, 12)
    tutti_e_due = rng.randint(1, 6)
    nessuno = rng.randint(0, 6) if L == 2 else rng.randint(1, 6)
    tot = solo_a + solo_b + tutti_e_due + nessuno
    na, nb = solo_a + tutti_e_due, solo_b + tutti_e_due
    gruppo = rng.choice(("In una classe", "In un gruppo di amici", "In una squadra"))
    if L == 2:
        r = nessuno
        domanda, dato = "nessuno", "nessuno"
        testo = (f"{gruppo} ci sono {tot} ragazzi: {na} {verbo} {a_cosa}, {nb} {verbo} "
                 f"{b_cosa} e {tutti_e_due} fanno tutte e due le cose. Quanti non fanno né "
                 f"l'una né l'altra?")
        sugg = ["Se sommi i due gruppi, chi fa tutte e due le cose lo conti due volte.",
                f"{na} più {nb} meno {tutti_e_due} sono quelli che fanno almeno una cosa: "
                f"toglili da {tot}."]
        spieg = (f"Almeno una cosa: {na} più {nb} meno {tutti_e_due}, cioè "
                 f"{na + nb - tutti_e_due}; {tot} meno {na + nb - tutti_e_due} fa {nessuno}.")
    else:
        r = solo_a + solo_b
        domanda = "una_sola"
        testo = (f"{gruppo} ci sono {tot} ragazzi: {na} {verbo} {a_cosa}, {nb} {verbo} "
                 f"{b_cosa}, {tutti_e_due} fanno tutte e due le cose e {nessuno} nessuna delle "
                 f"due. Quanti fanno una cosa sola?")
        sugg = ["Chi fa una cosa sola fa solo la prima o solo la seconda.",
                f"Solo la prima: {na} meno {tutti_e_due}; solo la seconda: {nb} meno "
                f"{tutti_e_due}."]
        spieg = (f"Solo la prima: {na} meno {tutti_e_due} fa {solo_a}; solo la seconda: {nb} "
                 f"meno {tutti_e_due} fa {solo_b}; in tutto {r}.")
    return Esercizio(MATERIA, "insiemi", L, seme, testo, testo, "valore", F(r), str(r), sugg,
                     spieg, [], "", {"totale": tot, "a": na, "b": nb, "entrambi": tutti_e_due,
                                     "nessuno": nessuno if L == 3 else None,
                                     "domanda": domanda}, {"tipo": "calcolato"})


def _verifica_insiemi(es: Esercizio) -> bool:
    d = es.dati
    if d["domanda"] == "intersezione":
        return F(len(set(d["A"]) & set(d["B"]))) == es.risposta
    if d["domanda"] == "unione":
        return F(len(set(d["A"]) | set(d["B"]))) == es.risposta
    almeno_uno = d["a"] + d["b"] - d["entrambi"]
    if d["domanda"] == "nessuno":
        return almeno_uno <= d["totale"] and F(d["totale"] - almeno_uno) == es.risposta
    # Una sola cosa: quelli con almeno una, meno chi le fa tutte e due; e i conti tornano
    return (almeno_uno + d["nessuno"] == d["totale"]
            and F(almeno_uno - d["entrambi"]) == es.risposta)


# ─────────────────────────── vero o falso ───────────────────────────

# Frasi semplici per il livello 1 (coppie che possono essere vere o false insieme)
FRASI = (("piove", "fa freddo"), ("il negozio è aperto", "è domenica"),
         ("Marta ha un cane", "Marta ha un gatto"), ("la luce è accesa", "la porta è chiusa"),
         ("Tommaso gioca a calcio", "Tommaso suona la chitarra"),
         ("il treno è in ritardo", "la stazione è piena"))

# Schema: (livello, formula per il ricalcolo, frase scritta, coppie in «o» da non avere vere
# insieme, funzione del generatore)
SCHEMI = (
    (1, "A and B", "{A} e {B}", (), lambda a, b, c: a and b),
    (1, "A or B", "{A} oppure {B}", (("A", "B"),), lambda a, b, c: a or b),
    (1, "not A", "non è vero che {A}", (), lambda a, b, c: not a),
    (2, "A and not B", "{A} e non {B}", (), lambda a, b, c: a and not b),
    (2, "(not A) or B", "non {A} oppure {B}", (("nA", "B"),), lambda a, b, c: (not a) or b),
    (2, "not (A and B)", "non è vero che {A} e {B}", (), lambda a, b, c: not (a and b)),
    (2, "not (A or B)", "non è vero che {A} oppure {B}", (("A", "B"),),
     lambda a, b, c: not (a or b)),
    (2, "(A and B) or C", "{A} e {B}, oppure {C}", (("AB", "C"),),
     lambda a, b, c: (a and b) or c),
    (3, "(not A) or B", "se {A} allora {B}", (), lambda a, b, c: b if a else True),
    (3, "A == B", "{A} se e solo se {B}", (), lambda a, b, c: a == b),
    (3, "(not A) or (not B)", "se {A} allora non {B}", (), lambda a, b, c: not b if a else True),
    (3, "A or B", "se non {A} allora {B}", (), lambda a, b, c: b if not a else True),
    (3, "(not (A and B)) or C", "se {A} e {B} allora {C}", (),
     lambda a, b, c: c if (a and b) else True),
)


def _valuta_logica(formula: str, valori: dict[str, bool]) -> bool:
    """Valutatore indipendente: solo and, or, not, == e le lettere A, B, C."""
    def v(n):
        if isinstance(n, ast.Expression):
            return v(n.body)
        if isinstance(n, ast.BoolOp):
            vals = [v(x) for x in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return not v(n.operand)
        if (isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.Eq)):
            return v(n.left) == v(n.comparators[0])
        if isinstance(n, ast.Name) and n.id in valori:
            return bool(valori[n.id])
        raise ValueError(f"non ammesso: {type(n).__name__}")
    return v(ast.parse(formula, mode="eval"))


def _vero(b: bool, f: bool = False) -> str:
    return ("vera" if b else "falsa") if f else ("vero" if b else "falso")


def _vero_falso(rng: random.Random, L: int, seme: int) -> Esercizio:
    schemi = [s for s in SCHEMI if s[0] == L]
    for _ in range(100):
        _, formula, frase, o_coppie, calcolo = rng.choice(schemi)
        a, b, c = (rng.random() < 0.5 for _ in range(3))
        parti = {"A": a, "B": b, "C": c, "nA": not a, "AB": a and b}
        if any(parti[x] and parti[y] for x, y in o_coppie):
            continue                      # «o» con tutte e due vere: ambiguo, si cambia
        break
    r = calcolo(a, b, c)
    usa_c = "{C}" in frase
    if L == 1:
        pa, pb = rng.choice(FRASI)
        detta = frase.format(A=pa, B=pb, C="")
        noti = (f"Sappiamo che «{pa}» è {_vero(a)}" + ("" if formula == "not A" else
                                                         f" e che «{pb}» è {_vero(b)}"))
        testo = f"{noti}. La frase «{detta}» è vera o falsa?"
        voce = testo
    else:
        detta = frase.format(A="A", B="B", C="C")
        lettere = ["A", "B"] + (["C"] if usa_c else [])
        val = {"A": a, "B": b, "C": c}
        noti = ", ".join(f"{x} è {_vero(val[x], True)}" for x in lettere)
        testo = f"{noti}. La frase «{detta}» è vera o falsa?"
        voce = ("L" + ", ".join(f"la frase {x} è {_vero(val[x], True)}" for x in lettere)[1:]
                + f". La frase «{detta}» è vera o falsa?")
    sugg = {"A and B": ["Con «e» la frase è vera solo se sono vere tutte e due le parti.",
                        "Guarda se c'è almeno una parte falsa."],
            "A or B": ["Con «oppure» basta che una delle due parti sia vera.",
                       "Guarda se almeno una delle due parti è vera."],
            "not A": ["«Non è vero che…» rovescia la frase: se era vera diventa falsa.",
                      "Com'era la frase senza il «non è vero che»?"]}.get(
        formula, ["Prima trova il valore delle parti più piccole, poi mettile insieme.",
                  "Ricorda: «e» vuole tutte e due vere; «oppure» almeno una; «se… allora…» è "
                  "falsa solo quando la prima parte è vera e la seconda falsa; «se e solo se» "
                  "vuole le due parti uguali."])
    spieg = (f"La frase «{detta}» è {_vero(r, True)}." + (
        " Con «se… allora…» la frase è falsa solo quando la prima parte è vera e la seconda "
        "falsa." if "allora" in frase else ""))
    return Esercizio(MATERIA, "vero_falso", L, seme, testo, voce, "scelta", _vero(r),
                     _vero(r), sugg, spieg, ["vero", "falso"], "",
                     {"formula": formula, "valori": {"A": a, "B": b, "C": c}},
                     {"tipo": "calcolato"})


def leggi_vero_falso(testo) -> str | None:
    """«vero», «è vera», «falso!», «non è vero» → falso, «non è falsa» → vero. None se non
    dice né l'uno né l'altro o li dice tutti e due («vero… no, falso»: meglio richiedere)."""
    t = unicodedata.normalize("NFKD", str(testo or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).casefold()
    t = " ".join(re.sub(r"[^\w\s]", " ", t).split())
    if not t:
        return None
    t = re.sub(r"\bnon (?:e )?(?:vero|vera)\b", " FALSO ", t)
    t = re.sub(r"\bnon (?:e )?(?:falso|falsa)\b", " VERO ", t)
    vero = bool(re.search(r"\b(vero|vera|VERO)\b", t))
    falso = bool(re.search(r"\b(falso|falsa|FALSO)\b", t))
    if vero == falso:
        return None
    return "vero" if vero else "falso"


# ─────────────────────────── generazione, ricalcolo, correzione ───────────────────────────

GENERATORI = {"sequenze": _sequenze, "insiemi": _insiemi, "vero_falso": _vero_falso}


def verifica(es: Esercizio) -> bool:
    try:
        if es.argomento == "sequenze":
            return _prossimi(es.dati["sequenza"]) == {F(es.risposta)}
        if es.argomento == "insiemi":
            return _verifica_insiemi(es)
        if es.argomento == "vero_falso":
            r = _valuta_logica(es.dati["formula"], es.dati["valori"])
            return _vero(r) == es.risposta
    except (ValueError, KeyError, TypeError, SyntaxError, ZeroDivisionError):
        return False
    return False


def genera(argomento: str, livello: int, seme: int) -> Esercizio:
    rng = random.Random(f"{MATERIA}:{argomento}:{livello}:{seme}")
    es = GENERATORI[argomento](rng, max(1, min(3, int(livello))), seme)
    if not verifica(es):
        raise ValueError(f"esercizio {argomento}/{livello}/{seme}: il ricalcolo non torna")
    es.verifica = {"tipo": "calcolato", "ricalcolo": True}
    return es


def controlla(es: Esercizio, risposta) -> Esito:
    if es.tipo == "scelta":
        r = leggi_vero_falso(risposta)
        if r is None:
            return Esito(None, "", "Dimmi solo «vero» o «falso».", False)
        return Esito(r == es.risposta, r)
    v = leggi_valore(risposta)
    if v is None:
        return Esito(None, "", "Non ho capito il numero: dimmelo o scrivilo in cifre.", False)
    letta = str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return Esito(v == es.risposta, letta)


def livello_per(argomento: str, classe: Classe) -> int:
    return livello_da_classe(ARGOMENTI[argomento]["classi"], classe)
