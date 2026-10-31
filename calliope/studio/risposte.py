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


def _scelta(d: dict, risposta: str) -> str:
    ops = list(d.get("opzioni") or ())
    ps = _bordi(C.normale(risposta))
    if any(w in C._NEGAZIONI for w in ps):
        return DA_RIVEDERE
    # «b», «la b», «risposta b», «lettera b», «la risposta è la b»
    resto = [w for w in ps if w not in ("la", "risposta", "lettera", "e", "opzione", "quella")]
    if len(resto) == 1 and len(resto[0]) == 1 and resto[0] in LETTERE[:len(ops)]:
        scelta = ops[LETTERE.index(resto[0])]
        return GIUSTO if _uguale_opzione(scelta, d["attesa"]) else SBAGLIATO
    prese = [o for o in ops if _uguale_opzione(o, risposta)]
    if len(prese) != 1:
        # Un'opzione detta dentro una frase corta («credo Lisbona»): di fila, una sola
        pr = parole(risposta)
        if len(pr) <= 8:
            prese = [o for o in ops if parole(o) and _trova(parole(o), pr)]
    if len(prese) != 1:
        return DA_RIVEDERE
    return GIUSTO if _uguale_opzione(prese[0], d["attesa"]) else SBAGLIATO


def _vero_falso(d: dict, risposta: str) -> str:
    k = " ".join(_bordi(C.normale(risposta)))
    detto = "vero" if k in _VERO else "falso" if k in _FALSO else None
    if detto is None:
        return DA_RIVEDERE
    return GIUSTO if detto == d["attesa"] else SBAGLIATO


def _numero(d: dict, risposta: str) -> str:
    detta = U.una_misura(risposta)
    attesa = U.una_misura(d["attesa"])
    if detta is None or attesa is None:
        return DA_RIVEDERE
    return U.confronta(detta, attesa)


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
    if d.get("tipo") != "vero_falso" and non_so(r):
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
