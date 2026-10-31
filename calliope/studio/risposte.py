"""
Le domande delle prove dello Studio e l'esito delle risposte (31/10, passo 8, issue #248, epic
#251, decisione 0035 punto 40). Funzioni pure: il servizio (`prove.py`) legge e scrive il db.

**L'esito lo decide il codice**, dove si può, deterministico (principio 10: una conversione o il
riconoscimento di una forma chiusa, mai il significato della frase):
- `scelta` (da 2 a 5 opzioni, una giusta): la lettera («b», «la b», «risposta b») o il testo
  intero di un'opzione; un'altra opzione è «sbagliato», niente di riconoscibile «da rivedere»;
- `vero_falso`: una forma chiusa detta per intero («vero», «è falso», «sì», «no»…);
- `numero`: il valore e l'unità (`unita.py`), con la tolleranza dell'1 % (esatto per un intero
  detto intero), nella stessa grandezza; il numero giusto senza l'unità attesa vale «indizio»;
- `parole`: le parole chiave (uguali, una lettera di tolleranza da 7 lettere in su mai sulla
  prima, o la stessa radice di 5 lettere; non negate subito prima): tutte «giusto», almeno metà
  «indizio», meno «da rivedere» e mai «sbagliato», perché la trascrizione può sbagliare un nome;
- `carta` (una carta dello Studio usata come domanda): la risposta chiusa della carta nella
  frase (`carte.risposta_giusta`) «giusto», altrimenti «da rivedere»;
- `aperta`: sempre «da rivedere».
«Non lo so» detto per intero è «sbagliato» con la fonte «persona»; niente è «vuota».

**«Da rivedere» lo decidono la persona o il tutore**, dopo la consegna, mai il modello: il
modello può solo proporre (`PROPOSTE`), e la proposta resta una misura.
"""

from __future__ import annotations

import re

from . import carte as C
from . import unita as U

TIPI = ("scelta", "vero_falso", "numero", "parole", "aperta")
# Le carte usate come domande (non si scrivono in `studio_domande`)
CARTA = "carta"
GIUSTO, INDIZIO, SBAGLIATO, DA_RIVEDERE, VUOTA = (
    "giusto", "indizio", "sbagliato", "da_rivedere", "vuota")
ESITI = (GIUSTO, INDIZIO, SBAGLIATO, DA_RIVEDERE, VUOTA)
# Gli esiti decisi (quelli che diventano un tentativo della padronanza)
DECISI = (GIUSTO, INDIZIO, SBAGLIATO)
# La proposta del modello su una risposta aperta (solo una misura, mai un tentativo)
PROPOSTE = {"giusta": GIUSTO, "parziale": INDIZIO, "sbagliata": SBAGLIATO}
# «Era giusta / Quasi / No» della persona o del tutore su una voce da rivedere
REVISIONI = (GIUSTO, INDIZIO, SBAGLIATO)
# Le domande chiuse (revisione della PR #342, punto 2): la persona che rivede la sua risposta può
# dare al più «indizio»; il «giusto» resta al codice o al tutore
CHIUSE = ("scelta", "vero_falso", "numero", "carta")

TESTO_MAX = 300
OPZIONE_MAX = 120
ATTESA_MAX = 300
RISPOSTA_MAX = 600
OPZIONI_MIN, OPZIONI_MAX = 2, 5
CHIAVE_MAX = 5
LETTERE = "abcde"
DOMANDE_MAX = 200

_SPAZI = re.compile(r"[\x00-\x1f\x7f ​-‏‪-‮⁦-⁩]")


def riga(testo, massimo: int) -> str:
    """Una riga senza caratteri di controllo né di direzione, al più `massimo` caratteri."""
    return " ".join(_SPAZI.sub(" ", str(testo if testo is not None else "")).split())[:massimo]\
        .strip()


def parole(testo) -> list[str]:
    """Le parole per il confronto (come le carte: minuscole, senza accenti, numeri in lettere),
    senza articoli e preposizioni."""
    return [w for w in C.normale(testo) if w not in C._ARTICOLI]


def _bordi(ps: list[str]) -> list[str]:
    while ps and ps[0] in C._INTORNO:
        ps = ps[1:]
    while ps and ps[-1] in C._INTORNO:
        ps = ps[:-1]
    return ps


# «Non lo so» detto per intero (principio 10): una risposta, non un silenzio
_NON_SO = {" ".join(C.normale(f)) for f in (
    "non lo so", "non la so", "boh", "non ne ho idea", "nessuna idea", "non me lo ricordo",
    "non me la ricordo", "non ricordo", "non mi ricordo", "non saprei", "passo",
    "non lo so dimmela", "non so")}
_VERO = {" ".join(C.normale(f)) for f in (
    "vero", "vera", "e vero", "è vero", "e vera", "si", "sì", "si e vero", "sì, è vero", "giusto",
    "esatto", "corretto", "l affermazione e vera", "e giusto")}
_FALSO = {" ".join(C.normale(f)) for f in (
    "falso", "falsa", "e falso", "è falso", "e falsa", "no", "non e vero", "non è vero",
    "no e falso", "no, è falso", "sbagliato", "non e vera", "l affermazione e falsa",
    "e sbagliato", "non e giusto")}


def non_so(risposta) -> bool:
    return " ".join(_bordi(C.normale(risposta))) in _NON_SO


# ─────────────────────────── la forma di una domanda ───────────────────────────

def prepara(tipo, testo, attesa, opzioni=(), chiave=()) -> dict:
    """Una domanda pulita e controllata nella forma (ValueError se non va): {tipo, testo,
    opzioni, attesa, chiave}. Per `scelta` l'attesa è il testo di una delle opzioni (o la sua
    lettera); per `vero_falso` «vero» o «falso»; per `numero` un numero leggibile, con l'unità
    facoltativa; per `parole` la risposta e da 1 a 5 parole chiave (senza, le parole piene della
    risposta, se sono al più 5)."""
    if tipo not in TIPI:
        raise ValueError("tipo sconosciuto")
    t = riga(testo, TESTO_MAX)
    if not t:
        raise ValueError("manca la domanda")
    a = riga(attesa, ATTESA_MAX)
    ops: list[str] = []
    ch: list[str] = []
    if tipo == "scelta":
        ops = [riga(o, OPZIONE_MAX) for o in (opzioni or ())]
        ops = [o for o in ops if o]
        if not OPZIONI_MIN <= len(ops) <= OPZIONI_MAX:
            raise ValueError("servono da 2 a 5 opzioni")
        if len({" ".join(parole(o)) or o.lower() for o in ops}) != len(ops):
            raise ValueError("due opzioni uguali")
        if len(a) == 1 and a.lower() in LETTERE[:len(ops)]:
            a = ops[LETTERE.index(a.lower())]
        giuste = [o for o in ops if _uguale_opzione(o, a)]
        if len(giuste) != 1:
            raise ValueError("la risposta giusta deve essere una delle opzioni")
        a = giuste[0]
    elif tipo == "vero_falso":
        k = " ".join(C.normale(a))
        if k in ("vero", "vera"):
            a = "vero"
        elif k in ("falso", "falsa"):
            a = "falso"
        else:
            raise ValueError("la risposta è vero o falso")
    elif tipo == "numero":
        if U.una_misura(a) is None:
            raise ValueError("la risposta deve essere un numero")
    elif tipo == "parole":
        ch = [riga(x, 60) for x in (chiave or ())]
        ch = [x for x in dict.fromkeys(ch) if x and parole(x)][:CHIAVE_MAX]
        if not ch:
            piene = [w for w in parole(a) if len(w) > 3]
            if not 1 <= len(piene) <= CHIAVE_MAX:
                raise ValueError("servono da 1 a 5 parole chiave")
            ch = piene
    if not a:
        raise ValueError("manca la risposta")
    return {"tipo": tipo, "testo": t, "opzioni": ops, "attesa": a, "chiave": ch}


def _uguale_opzione(o: str, x: str) -> bool:
    po, px = parole(o), parole(x)
    return (po == px and bool(po)) or (not po and o.strip().lower() == x.strip().lower())


# ─────────────────────────── l'esito ───────────────────────────

def _simile(a: str, b: str) -> bool:
    """Una parola chiave detta: uguale, la stessa radice di 5 lettere, o da 7 lettere in su una
    lettera diversa, in più o in meno, mai sulla prima (come la mappa)."""
    if a == b:
        return True
    if a[:1] != b[:1]:
        return False
    if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:
        return True
    if min(len(a), len(b)) < 7 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    lungo, corto = (a, b) if len(a) > len(b) else (b, a)
    return any(lungo[:i] + lungo[i + 1:] == corto for i in range(len(lungo)))


def _trova(chiave: list[str], ps: list[str]) -> bool:
    """Le parole della chiave nella frase, di fila, non negate subito prima."""
    n = len(chiave)
    for i in range(len(ps) - n + 1):
        if all(_simile(ps[i + k], chiave[k]) for k in range(n)) and not (
                i and ps[i - 1] in C._NEGAZIONI):
            return True
    return False


# Le lettere dette a voce (revisione della PR #342, punto 5): valgono solo come forma chiusa per
# intero («bi», «la bi», «risposta ci»), mai dentro una frase
LETTERE_DETTE = {"a": "a", "bi": "b", "b": "b", "ci": "c", "c": "c", "di": "d", "d": "d",
                 "e": "e", "effe": "f", "f": "f"}
_PRIMA_DELLA_LETTERA = ("la", "risposta", "lettera", "opzione", "quella", "e")


def _lettera_chiusa(ps: list[str]) -> str | None:
    """La lettera della frase intera: «b», «la bi», «la risposta è la ci» (forma chiusa)."""
    resto = list(ps)
    while len(resto) > 1 and resto[0] in _PRIMA_DELLA_LETTERA:
        resto = resto[1:]
    return LETTERE_DETTE.get(resto[0]) if len(resto) == 1 else None


def _elise(risposta) -> list[bool]:
    """Per ogni parola di `_bordi(C.normale(risposta))`: è una lettera elisa con l'apostrofo
    («d'Aragona», «c'è», «l'India»)? Gli stessi passi di `carte.normale`, parola per parola."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(risposta or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", t)
    el = [t[m.end():m.end() + 1] in ("'", "’", "`") for m in re.finditer(r"[a-z0-9]+", t)]
    tutte = C.normale(risposta)
    ps = _bordi(tutte)
    inizio = next((i for i in range(len(tutte) - len(ps) + 1)
                   if tutte[i:i + len(ps)] == ps), 0)
    return el[inizio:inizio + len(ps)]


# Prima di una lettera dentro la frase: «la b», «è la c», «a o b», «a, anzi c», «non la d»
_PRIMA_DI_LETTERA = frozenset(_PRIMA_DELLA_LETTERA) | {"o", "oppure", "anzi", "no", "forse",
                                                        "non", "proprio"}
# Dopo la «a» in testa, perché sia la lettera e non la preposizione: «a o b», «a, anzi c», «a, no»
_DOPO_LA_A = frozenset({"o", "oppure", "anzi", "no", "forse", "e", "credo", "penso", "sicuro"})


def _lettera_in_frase(ps: list[str], elise: list[bool], k: int, quante: int) -> str | None:
    """La lettera di un'opzione detta dentro la frase, o None (banco del 31/10, #344: «Isabella di
    Castiglia e Ferdinando d'Aragona», la risposta attesa, era «sbagliato» per la «d» di
    «d'Aragona»). Una lettera sola fra quelle delle opzioni, «e» mai (è una congiunzione), mai
    elisa con l'apostrofo, e all'inizio della frase o dopo «la», «è», «o», «anzi», «no»…: così la
    «a» di «arrivò a Calicut» è una preposizione e non l'opzione a."""
    w = ps[k]
    if len(w) != 1 or w == "e" or w not in LETTERE[:quante] or (k < len(elise) and elise[k]):
        return None
    if k and ps[k - 1] not in _PRIMA_DI_LETTERA:
        return None
    if (w == "a" and not k and len(ps) > 1 and ps[1] not in _DOPO_LA_A
            and ps[1] not in LETTERE_DETTE):
        return None                 # «a Calicut»: la preposizione in testa
    return w


def _scelta(d: dict, risposta: str) -> str:
    """Più opzioni nella stessa risposta («a o b», «Colombo e Magellano»): «sbagliato» (revisione
    della PR #342, punto 2), così una risposta a cavallo non diventa giusta con «Era giusta»."""
    ops = list(d.get("opzioni") or ())
    ps = _bordi(C.normale(risposta))
    elise = _elise(risposta)
    giusta = next((i for i, o in enumerate(ops) if _uguale_opzione(o, d["attesa"])), None)
    lett = _lettera_chiusa(ps)
    if lett is not None:
        if lett not in LETTERE[:len(ops)]:
            return DA_RIVEDERE                       # una lettera che non c'è («f» con 3 opzioni)
        return GIUSTO if LETTERE.index(lett) == giusta else SBAGLIATO
    negata = any(w in C._NEGAZIONI for w in ps)
    pr = parole(risposta)
    # Seconda revisione della PR #342: prima le opzioni nominate **esattamente** (la lettera sola
    # dentro la frase, «e» no perché è una congiunzione; l'opzione uguale alla risposta; le sue
    # parole tutte uguali e di fila, i numeri come numeri), non negate subito prima. Il confronto
    # largo (radici, una lettera di tolleranza) solo se nessuna opzione è nominata così:
    # Austria/Australia, Costantinopoli/Costantino, 1491/1492 restano distinte
    lettere = {k: x for k in range(len(ps))
               if (x := _lettera_in_frase(ps, elise, k, len(ops))) is not None}
    esatte = {LETTERE.index(w) for k, w in lettere.items() if not _negata(ps, k)}
    esatte |= {i for i, o in enumerate(ops) if _uguale_opzione(o, risposta)}
    if len(pr) <= 12:
        esatte |= {i for i, o in enumerate(ops) if parole(o) and _di_fila(parole(o), pr)}
    # «la a, no, la c», «Austria no Australia», «a, anzi c» (terza revisione della PR #342):
    # una correzione fra due opzioni nominate esattamente la decide chi rivede, mai il codice
    nominate = {LETTERE.index(w) for w in lettere.values()}
    if len(pr) <= 12:
        nominate |= {i for i, o in enumerate(ops) if parole(o) and _di_fila(parole(o), pr,
                                                                             negate=True)}
    if len(nominate) > 1 and any(w in _CORREZIONI for w in ps):
        return DA_RIVEDERE
    if esatte:
        if len(esatte) > 1:
            # Più opzioni nominate esattamente («a o b»): «sbagliato»; con una negazione di
            # mezzo («Colombo e non Magellano») la decide chi rivede
            return DA_RIVEDERE if negata else SBAGLIATO
        e = GIUSTO if esatte == {giusta} else SBAGLIATO
        return DA_RIVEDERE if negata and e == SBAGLIATO else e
    if negata:
        # Negata («non è la a»): la decide la persona (al più «indizio») o il tutore
        return DA_RIVEDERE
    simili = set()
    if len(pr) <= 12:
        simili = {i for i, o in enumerate(ops) if parole(o) and _trova(parole(o), pr)}
    if len(simili) != 1:
        return DA_RIVEDERE                 # niente, o più opzioni solo per somiglianza
    return GIUSTO if simili == {giusta} else SBAGLIATO


def _di_fila(chiave: list[str], ps: list[str], negate: bool = False) -> bool:
    """Le parole dell'opzione tutte uguali e di fila nella frase, non negate subito prima (con
    `negate` anche negate)."""
    n = len(chiave)
    return any(ps[i:i + n] == chiave and (negate or not _negata(ps, i))
               for i in range(len(ps) - n + 1))


_TRA = frozenset(("la", "il", "lo", "l", "i", "gli", "le", "e", "era", "proprio"))


def _negata(ps: list[str], k: int) -> bool:
    """La parola k è negata: «non» subito prima, saltando articoli ed «è» («non è la a»). Solo
    «non» (terza revisione della PR #342): in «la a, no, la c» il «no» corregge, non nega."""
    j = k - 1
    while j >= 0 and ps[j] in _TRA:
        j -= 1
    return j >= 0 and ps[j] == "non"


# Le parole che correggono fra due opzioni («la a, no, la c», «a, anzi c», «cioè no»)
_CORREZIONI = frozenset(("no", "anzi"))


def _vero_falso(d: dict, risposta: str) -> str:
    ps = _bordi(C.normale(risposta))
    k = " ".join(ps)
    detto = "vero" if k in _VERO else "falso" if k in _FALSO else None
    if detto is None:
        # Vero e falso nella stessa risposta («boh, vero o falso»): «sbagliato» (PR #342, 2);
        # con una negazione («vero, non è falso») la decide chi rivede (seconda revisione)
        if ({"vero", "vera"} & set(ps) and {"falso", "falsa"} & set(ps)
                and not any(w in C._NEGAZIONI for w in ps)):
            return SBAGLIATO
        return DA_RIVEDERE
    return GIUSTO if detto == d["attesa"] else SBAGLIATO


def _numero(d: dict, risposta: str) -> str:
    """Seconda revisione della PR #342: un numero solo si confronta; più numeri sono «giusto»
    se, convertiti, valgono tutti l'atteso («20 m/s cioè 72 km/h») o se le misure della stessa
    grandezza sommate lo valgono («1 metro e 50 centimetri»); «sbagliato» solo con alternative
    esplicite («X o Y») fra cui non c'è l'atteso; altrimenti «da rivedere» (chi rivede una
    domanda chiusa dà al più «indizio»)."""
    attesa = U.una_misura(d["attesa"])
    nn = U.numeri_detti(risposta)
    if attesa is None or not nn:
        return DA_RIVEDERE
    if len({round(v, 9) for v, _u in nn}) == 1:
        e = U.confronta(next(((v, u) for v, u in nn if u), nn[0]), attesa)
        # Lo stesso numero ripetuto («1 kg, 1 kg e 1 kg») che non è l'atteso: forse una somma
        # che il codice non fa (terza revisione della PR #342), la decide chi rivede
        return DA_RIVEDERE if len(nn) > 1 and e != GIUSTO else e
    ua = attesa[1]
    # Con l'unità attesa contano le misure della sua grandezza («60 km/h in 2 ore»)
    stesse = [(v, u) for v, u in nn if u and ua and U.UNITA[u][0] == U.UNITA[ua][0]]
    if len(stesse) == 1:
        return U.confronta(stesse[0], attesa)
    gruppo = stesse or nn
    if all(U.confronta(x, attesa) == GIUSTO for x in gruppo):
        return GIUSTO
    # Si sommano solo le misure composte (terza revisione della PR #342): lunghezza, massa o
    # tempo, unità tutte diverse dalla più grande alla più piccola («1 km e 500 m», «1 metro e
    # 50 centimetri»); mai velocità né temperatura, mai la stessa unità due volte
    fattori = [U.UNITA[u][1] for _v, u in stesse]
    composta = (ua and U.UNITA[ua][0] in (U.L, U.M, U.T) and len(stesse) > 1
                and all(a > b for a, b in zip(fattori, fattori[1:])))
    if composta:
        somma = sum(v * U.UNITA[u][1] for v, u in stesse) / U.UNITA[ua][1]
        if U.confronta((somma, ua), attesa) == GIUSTO:
            return GIUSTO
    alt = U.alternative(risposta)
    if alt and not any(U.confronta(x, attesa) in (GIUSTO, INDIZIO) for x in alt):
        return SBAGLIATO
    return DA_RIVEDERE


# Una risposta con tante parole in più delle chiavi non si conta (un elenco a caso le prende)
_PAROLE_IN_PIU = 12


def _parole(d: dict, risposta: str) -> str:
    chiavi = [parole(x) for x in d.get("chiave") or () if parole(x)]
    if not chiavi:
        return DA_RIVEDERE
    ps = parole(risposta)
    if len(ps) > sum(len(c) for c in chiavi) * 3 + _PAROLE_IN_PIU:
        return DA_RIVEDERE
    trovate = sum(_trova(c, ps) for c in chiavi)
    if trovate == len(chiavi):
        return GIUSTO
    if trovate * 2 >= len(chiavi) and trovate:
        return INDIZIO
    return DA_RIVEDERE


def _carta(d: dict, risposta: str) -> str:
    ch = d.get("chiusa")
    return GIUSTO if ch and C.risposta_giusta(ch, risposta) else DA_RIVEDERE


def valuta(d: dict, risposta) -> tuple[str, str | None]:
    """(esito, fonte) della risposta a una domanda (`tipo`, `attesa`, `opzioni`, `chiave`,
    `chiusa` per le carte). La fonte è «codice», «persona» per «non lo so», None per «vuota» e
    «da rivedere» (le decide poi la persona o il tutore)."""
    r = riga(risposta, RISPOSTA_MAX)
    if not r or not C.normale(r):
        return VUOTA, None
    # «Non lo so» detto per intero, anche sul vero o falso (revisione della PR #342)
    if non_so(r):
        return SBAGLIATO, "persona"
    fn = {"scelta": _scelta, "vero_falso": _vero_falso, "numero": _numero, "parole": _parole,
          CARTA: _carta}.get(d.get("tipo"))
    if fn is None:
        return DA_RIVEDERE, None
    e = fn(d, r)
    return e, ("codice" if e in DECISI else None)


def attesa_detta(d: dict) -> str:
    """La risposta attesa da mostrare o da dire (in busta): per la scelta con la lettera."""
    if d.get("tipo") == "scelta":
        ops = list(d.get("opzioni") or ())
        i = next((k for k, o in enumerate(ops) if o == d["attesa"]), None)
        return f"{LETTERE[i]}) {d['attesa']}" if i is not None else str(d["attesa"])
    return str(d.get("attesa") or "")
