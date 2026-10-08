"""
Esercizi d'italiano generati al momento (08/10/2026, decisione di Dario del 07/10: tipo
«linguistico»): analisi grammaticale (parti del discorso) e analisi logica di base (soggetto,
predicato, complemento oggetto; predicato nominale al livello 3).

Le frasi si **costruiscono** da un piccolo lessico annotato (`NOMI`, `VERBI`, `AGGETTIVI`…)
con modelli di frase: la parte del discorso di ogni parola e il ruolo di ogni gruppo si sanno
per costruzione, non si indovinano. Le risposte sono forme chiuse (una delle nove parti del
discorso, uno dei ruoli, le parole di un gruppo della frase). Sopra ci sono due controlli
(verifica.py): la parte del discorso di ogni parola deve comparire nella voce del
**Wikizionario** della biblioteca, e un **secondo modello** risolve l'esercizio da solo; se
non concorda l'esercizio si scarta.

Il lessico evita le parole con due letture comuni nella stessa forma («porta», «lava»,
«parte»): lo controlla anche prova_esercizi sul Wikizionario.
"""

from __future__ import annotations

import random
import re
import unicodedata

from .modello import Classe, Esercizio, Esito

MATERIA = "italiano"

ARGOMENTI = {
    "analisi_grammaticale": {"nome": "analisi grammaticale",
                             "alias": ("grammatical", "parti del discorso", "parte del discorso"),
                             "classi": (Classe("elementari", 2), Classe("medie", 2))},
    "analisi_logica": {"nome": "analisi logica",
                       "alias": ("logic", "soggett", "predicat", "complement"),
                       "classi": (Classe("elementari", 4), Classe("medie", 3))},
}

PARTI = ("articolo", "nome", "aggettivo", "pronome", "verbo", "avverbio", "preposizione",
         "congiunzione", "interiezione")
PARTI_BASE = ("articolo", "nome", "aggettivo", "verbo")
RUOLI = ("soggetto", "predicato verbale", "predicato nominale", "complemento oggetto")

# ─────────────────────────── lessico ───────────────────────────
# Nomi: (singolare, plurale, genere, categoria). Solo nomi che cominciano per consonante
# semplice (articoli il, la, i, le, un, una: niente «lo», «gli», «l'»)
NOMI = [
    ("gatto", "gatti", "m", "animale"), ("cane", "cani", "m", "animale"),
    ("cavallo", "cavalli", "m", "animale"), ("coniglio", "conigli", "m", "animale"),
    ("topo", "topi", "m", "animale"), ("gallina", "galline", "f", "animale"),
    ("mucca", "mucche", "f", "animale"), ("pecora", "pecore", "f", "animale"),
    ("bambino", "bambini", "m", "persona"), ("bambina", "bambine", "f", "persona"),
    ("ragazzo", "ragazzi", "m", "persona"), ("ragazza", "ragazze", "f", "persona"),
    ("nonno", "nonni", "m", "persona"), ("nonna", "nonne", "f", "persona"),
    ("maestra", "maestre", "f", "persona"), ("cuoco", "cuochi", "m", "persona"),
    ("pittore", "pittori", "m", "persona"), ("dottore", "dottori", "m", "persona"),
    ("mela", "mele", "f", "cibo"), ("torta", "torte", "f", "cibo"),
    ("panino", "panini", "m", "cibo"), ("biscotto", "biscotti", "m", "cibo"),
    ("formaggio", "formaggi", "m", "cibo"), ("pizza", "pizze", "f", "cibo"),
    ("carota", "carote", "f", "cibo"),
    ("libro", "libri", "m", "lettura"), ("lettera", "lettere", "f", "lettura"),
    ("giornale", "giornali", "m", "lettura"), ("fiaba", "fiabe", "f", "lettura"),
    ("fiore", "fiori", "m", "disegno"), ("nave", "navi", "f", "disegno"),
    ("farfalla", "farfalle", "f", "disegno"), ("montagna", "montagne", "f", "disegno"),
    ("palla", "palle", "f", "gioco"), ("bambola", "bambole", "f", "gioco"),
    ("pallone", "palloni", "m", "gioco"), ("trottola", "trottole", "f", "gioco"),
    ("treno", "treni", "m", "veicolo"), ("bicicletta", "biciclette", "f", "veicolo"),
    ("barca", "barche", "f", "veicolo"),
    ("canzone", "canzoni", "f", "musica"), ("musica", "musiche", "f", "musica"),
]
# Luoghi con «in» senza articolo: «in giardino»
LUOGHI = ("giardino", "cortile", "cucina", "piscina", "biblioteca")
# Verbi: (3ª singolare, 3ª plurale, soggetti, oggetti); oggetti None = intransitivo
VERBI = [
    ("mangia", "mangiano", ("persona", "animale"), ("cibo",)),
    ("legge", "leggono", ("persona",), ("lettura",)),
    ("disegna", "disegnano", ("persona",), ("disegno",)),
    ("cerca", "cercano", ("persona", "animale"), ("gioco",)),
    ("prepara", "preparano", ("persona",), ("cibo",)),
    ("ascolta", "ascoltano", ("persona",), ("musica",)),
    ("guarda", "guardano", ("persona", "animale"), ("veicolo", "disegno")),
    ("corre", "corrono", ("persona", "animale"), None),
    ("dorme", "dormono", ("persona", "animale"), None),
    ("ride", "ridono", ("persona",), None),
    ("salta", "saltano", ("persona", "animale"), None),
    ("canta", "cantano", ("persona",), None),
    ("gioca", "giocano", ("persona", "animale"), None),
    ("arriva", "arrivano", ("persona", "veicolo"), None),
    ("nuota", "nuotano", ("persona", "animale"), None),
]
# Aggettivi: (m sing, f sing, m plur, f plur), categorie dei nomi a cui si danno
AGGETTIVI = [
    (("nero", "nera", "neri", "nere"), ("animale", "veicolo")),
    (("bianco", "bianca", "bianchi", "bianche"), ("animale", "disegno", "gioco")),
    (("piccolo", "piccola", "piccoli", "piccole"), ("animale", "persona", "disegno", "gioco")),
    (("allegro", "allegra", "allegri", "allegre"), ("persona", "musica")),
    (("bravo", "brava", "bravi", "brave"), ("persona",)),
    (("felice", "felice", "felici", "felici"), ("persona",)),
    (("buono", "buona", "buoni", "buone"), ("cibo",)),
    (("dolce", "dolce", "dolci", "dolci"), ("cibo", "musica")),
    (("rosso", "rossa", "rossi", "rosse"), ("cibo", "gioco", "veicolo", "disegno")),
    (("nuovo", "nuova", "nuovi", "nuove"), ("lettura", "gioco", "veicolo")),
    (("veloce", "veloce", "veloci", "veloci"), ("veicolo", "animale")),
    (("lungo", "lunga", "lunghi", "lunghe"), ("lettura", "musica", "veicolo")),
]
AVVERBI = ("sempre", "spesso", "volentieri", "lentamente", "velocemente", "oggi")
PRONOMI = {("m", False): "lui", ("f", False): "lei", ("m", True): "loro", ("f", True): "loro"}
INTERIEZIONI = ("oh", "ah")
ARTICOLI = {("m", False): "il", ("f", False): "la", ("m", True): "i", ("f", True): "le"}
INDETERMINATIVI = {"m": "un", "f": "una"}

# Parole che il ragazzo può dire per una parte del discorso (forma della risposta, non
# significato della frase: «sostantivo» = nome, «articolo determinativo» = articolo)
SINONIMI_PARTI = {
    "articolo": ("articolo",), "nome": ("nome", "sostantivo"),
    "aggettivo": ("aggettivo",), "pronome": ("pronome",),
    "verbo": ("verbo", "voce verbale"), "avverbio": ("avverbio",),
    "preposizione": ("preposizione",), "congiunzione": ("congiunzione",),
    "interiezione": ("interiezione", "esclamazione"),
}
SINONIMI_RUOLI = {
    "soggetto": ("soggetto",), "predicato verbale": ("predicato verbale",),
    "predicato nominale": ("predicato nominale",),
    "complemento oggetto": ("complemento oggetto", "oggetto", "complemento diretto"),
}


def _semplice(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


# ─────────────────────────── frasi ───────────────────────────

class Frase:
    """Parole con la parte del discorso e gruppi con il ruolo, costruiti insieme."""

    def __init__(self):
        self.parole: list[tuple[str, str]] = []           # (forma, parte del discorso)
        self.gruppi: list[tuple[list[int], str]] = []     # (indici delle parole, ruolo)
        self.esclamativa = False

    def aggiungi(self, forme: list[tuple[str, str]], ruolo: str | None = None):
        idx = list(range(len(self.parole), len(self.parole) + len(forme)))
        self.parole.extend(forme)
        if ruolo:
            self.gruppi.append((idx, ruolo))
        return idx

    def testo(self) -> str:
        out = []
        for i, (f, p) in enumerate(self.parole):
            if i > 0 and self.parole[i - 1][1] == "interiezione":
                out[-1] += ","
            out.append(f)
        s = " ".join(out)
        return s[0].upper() + s[1:] + ("!" if self.esclamativa else ".")

    def gruppo(self, ruolo: str) -> list[int] | None:
        g = [i for idx, r in self.gruppi if r == ruolo for i in idx]
        return g or None

    def gruppo_testo(self, idx: list[int]) -> str:
        return " ".join(self.parole[i][0] for i in idx)


def _nome(rng, categorie, plurale=None, evita=()):
    scelti = [n for n in NOMI if n[3] in categorie and n[0] not in evita]
    sing, plur, g, cat = rng.choice(scelti)
    pl = rng.random() < 0.3 if plurale is None else plurale
    return (plur if pl else sing), g, pl, cat, sing


def _agg(rng, cat, g, pl):
    adatti = [a for a, cats in AGGETTIVI if cat in cats]
    if not adatti:
        return None
    a = rng.choice(adatti)
    return a[(2 if pl else 0) + (1 if g == "f" else 0)]


def _gruppo_nome(rng, categorie, con_agg=False, indeterminativo=False, plurale=None, evita=()):
    """[(forma, parte)], genere, plurale, categoria, singolare."""
    forma, g, pl, cat, sing = _nome(rng, categorie, plurale, evita)
    if indeterminativo and not pl:
        art = INDETERMINATIVI[g]
    else:
        art = ARTICOLI[(g, pl)]
    parole = [(art, "articolo"), (forma, "nome")]
    if con_agg:
        a = _agg(rng, cat, g, pl)
        if a:
            parole.append((a, "aggettivo"))
    return parole, g, pl, cat, sing


def costruisci(rng: random.Random, modello: str) -> Frase:
    """Una frase dal modello: «sv», «sav», «svo», «svoa», «svavv», «svprep», «pronvo», «sve_v»,
    «s_e_s_v», «interiez», «nominale»."""
    f = Frase()
    if modello == "pronvo":
        verbi = [v for v in VERBI if v[3] and "persona" in v[2]]
        v = rng.choice(verbi)
        g, pl = rng.choice((("m", False), ("f", False), ("m", True)))
        f.aggiungi([(PRONOMI[(g, pl)], "pronome")], "soggetto")
        f.aggiungi([(v[1] if pl else v[0], "verbo")], "predicato verbale")
        og, *_ = _gruppo_nome(rng, v[3], indeterminativo=True, plurale=False)
        f.aggiungi(og, "complemento oggetto")
        return f
    if modello == "s_e_s_v":
        v = rng.choice([x for x in VERBI if x[3] is None])
        cat = rng.choice(v[2])
        s1, *_r1 = _gruppo_nome(rng, (cat,), plurale=False)
        s2, *_r2 = _gruppo_nome(rng, (cat,), plurale=False, evita=(_r1[3],))
        f.aggiungi(s1 + [("e", "congiunzione")] + s2, "soggetto")
        f.aggiungi([(v[1], "verbo")], "predicato verbale")
        return f
    if modello == "nominale":
        cat = rng.choice(("animale", "persona", "veicolo", "cibo"))
        sog, g, pl, cat, _ = _gruppo_nome(rng, (cat,))
        a = _agg(rng, cat, g, pl)
        f.aggiungi(sog, "soggetto")
        f.aggiungi([("sono" if pl else "è", "verbo"), (a, "aggettivo")], "predicato nominale")
        return f
    if modello == "interiez":
        f.aggiungi([(rng.choice(INTERIEZIONI), "interiezione")])
        f.esclamativa = True
        v = rng.choice([x for x in VERBI if x[0] in ("arriva", "canta", "ride", "salta")])
        sog, g, pl, cat, _ = _gruppo_nome(rng, v[2], plurale=False)
        f.aggiungi(sog, "soggetto")
        f.aggiungi([(v[0], "verbo")], "predicato verbale")
        return f
    # Modelli con soggetto nome e un verbo
    trans = modello in ("svo", "svoa")
    verbi = [v for v in VERBI if (v[3] is not None) == trans]
    if modello == "sve_v":                 # due verbi: persone e animali ne hanno più d'uno
        verbi = [v for v in verbi if {"persona", "animale"} & set(v[2])]
    v = rng.choice(verbi)
    cats = tuple(c for c in v[2] if modello != "sve_v" or c in ("persona", "animale"))
    sog, g, pl, cat, sing = _gruppo_nome(rng, cats, con_agg=modello == "sav")
    f.aggiungi(sog, "soggetto")
    f.aggiungi([(v[1] if pl else v[0], "verbo")], "predicato verbale")
    if trans:
        og, *_ = _gruppo_nome(rng, v[3], con_agg=modello == "svoa", evita=(sing,))
        f.aggiungi(og, "complemento oggetto")
    elif modello == "svavv":
        f.aggiungi([(rng.choice(AVVERBI), "avverbio")])
    elif modello == "svprep":
        if rng.random() < 0.5:
            f.aggiungi([("in", "preposizione"), (rng.choice(LUOGHI), "nome")], "altro complemento")
        else:
            prep, cats = rng.choice((("con", ("gioco",)), ("per", ("persona",))))
            gn, *_ = _gruppo_nome(rng, cats, plurale=False, evita=(sing,))
            f.aggiungi([(prep, "preposizione")] + gn, "altro complemento")
    elif modello == "sve_v":
        altri = [x for x in VERBI if x[3] is None and x[0] != v[0]
                 and set(x[2]) & {cat}]
        v2 = rng.choice(altri)
        idx = f.gruppo("predicato verbale")
        f.parole.extend([("e", "congiunzione"), (v2[1] if pl else v2[0], "verbo")])
        # il predicato sono i due verbi (con la congiunzione in mezzo)
        f.gruppi = [(i, r) if r != "predicato verbale" else
                    (idx + [len(f.parole) - 2, len(f.parole) - 1], r) for i, r in f.gruppi]
    return f


# ─────────────────────────── generatori ───────────────────────────

_MODELLI_GRAMMATICA = {1: ("sv", "sav", "svo"), 2: ("svoa", "svavv", "svprep", "pronvo", "sve_v"),
                       3: ("s_e_s_v", "interiez", "svprep", "svoa", "nominale")}


def _analisi_grammaticale(rng: random.Random, L: int, seme: int) -> Esercizio:
    for _ in range(50):
        f = costruisci(rng, rng.choice(_MODELLI_GRAMMATICA[L]))
        consentite = PARTI_BASE if L == 1 else PARTI
        cand = [i for i, (forma, p) in enumerate(f.parole) if p in consentite
                # una forma che compare due volte con due parti diverse non si chiede
                and len({pp for ff, pp in f.parole if ff == forma}) == 1]
        if L >= 2:
            # Al livello 2 e 3 si preferiscono le parti meno ovvie
            rare = [i for i in cand if f.parole[i][1] not in ("articolo", "nome")]
            cand = rare or cand
        if cand:
            break
    i = rng.choice(cand)
    forma, parte = f.parole[i]
    frase = f.testo()
    spieg = {
        "articolo": f"«{forma}» è un articolo: sta davanti al nome e ne dice genere e numero.",
        "nome": f"«{forma}» è un nome: indica una persona, un animale, una cosa o un luogo.",
        "aggettivo": f"«{forma}» è un aggettivo: dice com'è il nome a cui si accompagna.",
        "pronome": f"«{forma}» è un pronome: sta al posto di un nome.",
        "verbo": f"«{forma}» è un verbo: dice che cosa si fa o com'è.",
        "avverbio": f"«{forma}» è un avverbio: dice come o quando avviene l'azione.",
        "preposizione": f"«{forma}» è una preposizione: lega una parola a un'altra.",
        "congiunzione": f"«{forma}» è una congiunzione: unisce due parole o due frasi.",
        "interiezione": f"«{forma}» è un'interiezione: esprime un'emozione.",
    }[parte]
    domande = {
        "articolo": "Sta davanti a un nome?", "nome": "Indica una persona, un animale o una cosa?",
        "aggettivo": "Dice com'è qualcuno o qualcosa?", "pronome": "Sta al posto di un nome?",
        "verbo": "Dice che cosa fa qualcuno?", "avverbio": "Dice come o quando si fa l'azione?",
        "preposizione": "È una parolina che lega due parti della frase?",
        "congiunzione": "Unisce due parole o due pezzi di frase?",
        "interiezione": "Esprime un'emozione, come una piccola esclamazione?",
    }
    sugg = ["Guarda che cosa fa la parola nella frase: a che cosa si riferisce?",
            domande[parte] + " Prova a pensarci.",
            f"È una di queste: {', '.join(sorted({parte, *rng.sample([p for p in (PARTI_BASE if L == 1 else PARTI) if p != parte], 2)}))}."]
    return Esercizio(MATERIA, "analisi_grammaticale", L, seme,
                     f"Nella frase «{frase}», che parte del discorso è «{forma}»?",
                     f"Nella frase: {frase} Che parte del discorso è «{forma}»?",
                     "scelta", parte, parte, sugg, spieg,
                     list(PARTI_BASE if L == 1 else PARTI), "",
                     {"frase": frase, "parola": forma, "indice": i,
                      "parole": [list(p) for p in f.parole],
                      "gruppi": [[idx, r] for idx, r in f.gruppi]}, {})


_MODELLI_LOGICA = {1: ("sv", "sav", "svo", "svavv"), 2: ("svo", "svoa", "pronvo", "svprep", "sav"),
                   3: ("s_e_s_v", "nominale", "svoa", "svprep", "interiez")}


def _analisi_logica(rng: random.Random, L: int, seme: int) -> Esercizio:
    f = costruisci(rng, rng.choice(_MODELLI_LOGICA[L]))
    ruoli = [r for _, r in f.gruppi if r in RUOLI]
    if L == 1:
        ruoli = [r for r in ruoli if r in ("soggetto", "predicato verbale")]
    tipo = "parole" if (L == 1 or rng.random() < 0.6) else "ruolo"
    ruolo = rng.choice(ruoli)
    idx = f.gruppo(ruolo)
    testo_g = f.gruppo_testo(idx)
    frase = f.testo()
    nome_ruolo = "predicato" if ruolo.startswith("predicato") else ruolo
    spieg = {
        "soggetto": f"Il soggetto è «{testo_g}»: è chi compie l'azione o di cui si parla.",
        "predicato verbale": f"Il predicato è «{testo_g}»: dice che cosa fa il soggetto.",
        "predicato nominale": f"Il predicato è «{testo_g}»: il verbo essere con una parola che "
                              f"dice com'è il soggetto, cioè un predicato nominale.",
        "complemento oggetto": f"Il complemento oggetto è «{testo_g}»: risponde alla domanda "
                               f"«chi? che cosa?» dopo il verbo.",
    }[ruolo]
    domanda_guida = {
        "soggetto": "Chi è che fa l'azione, o di chi si parla?",
        "predicato verbale": "Qual è il verbo? Che cosa fa il soggetto?",
        "predicato nominale": "C'è il verbo essere? Con quale parola si accompagna?",
        "complemento oggetto": "Dopo il verbo chiediti: chi? che cosa?",
    }[ruolo]
    if tipo == "parole":
        testo = f"Nella frase «{frase}», qual è il {nome_ruolo}?"
        voce = f"Nella frase: {frase} Qual è il {nome_ruolo}?"
        essenziali = [i for i in idx if f.parole[i][1] in ("nome", "pronome", "verbo")
                      or ruolo == "predicato nominale"]
        risposta = [f.parole[i][0] for i in essenziali]
        sugg = [domanda_guida, f"Cerca tra queste parole: {_alcune(rng, f, idx)}."]
        scelte = []
    else:
        testo = f"Nella frase «{frase}», che cosa è «{testo_g}»?"
        voce = f"Nella frase: {frase} Che cosa è «{testo_g}»?"
        risposta = ruolo
        scelte = [r for r in RUOLI if L == 3 or r != "predicato nominale"]
        sugg = [domanda_guida.replace("Qual è il verbo? ", ""),
                f"Prova a chiederti se «{testo_g}» fa l'azione, è l'azione o la riceve."]
    return Esercizio(MATERIA, "analisi_logica", L, seme, testo, voce,
                     "parole" if tipo == "parole" else "scelta", risposta,
                     testo_g if tipo == "parole" else ruolo, sugg, spieg, scelte, "",
                     {"frase": frase, "ruolo": ruolo, "gruppo": testo_g, "indici": idx,
                      "parole": [list(p) for p in f.parole],
                      "gruppi": [[i, r] for i, r in f.gruppi]}, {})


def _alcune(rng, f: Frase, idx: list[int]) -> str:
    """Il gruppo giusto mescolato con un'altra parola piena della frase (un indizio)."""
    piene = [i for i, (_, p) in enumerate(f.parole) if p in ("nome", "verbo", "pronome")]
    altre = [i for i in piene if i not in idx]
    giuste = [i for i in idx if f.parole[i][1] in ("nome", "verbo", "pronome", "aggettivo")]
    scelte = sorted(set(giuste[:1] + rng.sample(altre, min(1, len(altre)))))
    return ", ".join(f"«{f.parole[i][0]}»" for i in scelte)


GENERATORI = {"analisi_grammaticale": _analisi_grammaticale, "analisi_logica": _analisi_logica}


def genera(argomento: str, livello: int, seme: int) -> Esercizio:
    rng = random.Random(f"{argomento}:{livello}:{seme}")
    es = GENERATORI[argomento](rng, max(1, min(3, int(livello))), seme)
    es.verifica = {"tipo": "lessico"}
    return es


# ─────────────────────────── correzione ───────────────────────────

def _parte_detta(risposta: str) -> str | None:
    t = _semplice(risposta)
    trovate = {p for p, sin in SINONIMI_PARTI.items() for s in sin if re.search(rf"\b{s}\b", t)}
    return next(iter(trovate)) if len(trovate) == 1 else None


def _ruolo_detto(risposta: str) -> str | None:
    t = _semplice(risposta)
    trovati = [r for r, sin in SINONIMI_RUOLI.items() for s in sin if re.search(rf"\b{s}\b", t)]
    # «complemento oggetto» contiene «oggetto»: vale il più lungo
    if "complemento oggetto" in trovati:
        return "complemento oggetto"
    trovati = list(dict.fromkeys(trovati))
    if not trovati and re.search(r"\bpredicato\b", t):
        return "predicato"
    return trovati[0] if len(trovati) == 1 else None


# «Il soggetto è…», «è…»: la forma della risposta, non una parola della frase
_PREMESSA = re.compile(r"^(?:(?:allora|dunque|secondo me|credo|penso)\s+)*"
                       r"(?:(?:il|e il)\s+)?(?:soggetto|predicato(?:\s+verbale|\s+nominale)?|"
                       r"complemento\s+oggetto)\s+(?:e|sono)\s+")


def controlla(es: Esercizio, risposta) -> Esito:
    t = _semplice(risposta)
    if not t:
        return Esito(None, "", "Non ho sentito la risposta.", False)
    if es.argomento == "analisi_grammaticale":
        p = _parte_detta(t)
        if p is None:
            if re.search(r"\b(soggetto|predicato|complemento)\b", t):
                return Esito(False, t[:40], "Quella è analisi logica: qui si chiede la parte del "
                                            "discorso.", False)
            return Esito(None, t[:40], "Dimmi una parte del discorso: nome, articolo, verbo…",
                         False)
        return Esito(p == es.risposta, p)
    if es.tipo == "scelta":
        r = _ruolo_detto(t)
        if r is None:
            return Esito(None, t[:40], "Dimmi se è soggetto, predicato o complemento oggetto.",
                         False)
        if r == "predicato" and es.risposta.startswith("predicato"):
            return Esito(True, es.risposta, "Giusto! Più precisamente: " + es.risposta + ".")
        return Esito(r == es.risposta, r)
    # Le parole di un gruppo della frase
    t = _PREMESSA.sub("", t)
    parole_frase = [(_semplice(fm), p) for fm, p in es.dati.get("parole", [])]
    gruppo = set(es.dati.get("indici") or [])
    dette = set(t.split())
    essenziali = {_semplice(w) for w in es.risposta}
    if not dette & {w for w, _ in parole_frase}:
        return Esito(None, t[:40], "Dimmi le parole della frase.", False)
    altre = {w for i, (w, p) in enumerate(parole_frase) if i not in gruppo
             and p in ("nome", "verbo", "pronome", "aggettivo", "avverbio")
             and w not in {pw for j, (pw, _) in enumerate(parole_frase) if j in gruppo}}
    giusta = essenziali <= dette and not (dette & altre)
    return Esito(giusta, t[:40])


def livello_per(argomento: str, classe: Classe) -> int:
    da, a = ARGOMENTI[argomento]["classi"]
    if classe.indice <= da.indice:
        return 1
    if classe.indice >= a.indice:
        return 3
    pos = (classe.indice - da.indice) / max(1, a.indice - da.indice)
    return 1 if pos < 0.34 else 2 if pos < 0.67 else 3


def forme_lessico() -> dict[str, set[str]]:
    """Ogni forma del lessico con le parti del discorso con cui la usano i modelli di frase
    (per il controllo sul Wikizionario in prova_esercizi)."""
    out: dict[str, set[str]] = {}

    def add(f, p):
        out.setdefault(f, set()).add(p)
    for s, pl, g, _ in NOMI:
        add(s, "nome")
        add(pl, "nome")
    for luogo in LUOGHI:
        add(luogo, "nome")
    for v3, v6, *_ in VERBI:
        add(v3, "verbo")
        add(v6, "verbo")
    add("è", "verbo")
    add("sono", "verbo")
    for forme, _ in AGGETTIVI:
        for f in forme:
            add(f, "aggettivo")
    for a in AVVERBI:
        add(a, "avverbio")
    for p in set(PRONOMI.values()):
        add(p, "pronome")
    for i in INTERIEZIONI:
        add(i, "interiezione")
    for a in list(ARTICOLI.values()) + list(INDETERMINATIVI.values()):
        add(a, "articolo")
    for p in ("in", "con", "per"):
        add(p, "preposizione")
    add("e", "congiunzione")
    return out
