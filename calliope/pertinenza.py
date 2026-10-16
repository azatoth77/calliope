"""
Quanto i risultati di una ricerca parlano di ciò di cui si parlava (16/10/2026, issue #101).

Caso vero della DGX del 15/10 sera: dopo un racconto sul mito di Orione, «approfondiamo questo
argomento» → web_cerca con una domanda storpiata, risultati su una startup dal nome simile a una
parola della conversazione, e il modello li riferiva per intero nonostante il `cosa_fare`.

Qui solo una **misura**, scritta nel risultato come dato per il modello (`pertinenti: 0 su 5`):
decide il modello se i risultati c'entrano (principio 10), il codice non toglie nulla. La misura
è per parole in comune, senza modelli: un risultato è «pertinente» se ha almeno una parola piena
in comune con la frase di chi parla, oppure almeno due con i turni appena prima. La domanda
composta dal modello non conta: è proprio quella che può uscire storpiata. Parole piene: almeno
quattro lettere, senza accenti, fuori dall'elenco delle parole vuote; confrontate sulle prime
cinque lettere («Milano» e «milanese», «stelle» e «stella»).
"""
from __future__ import annotations

import re
import unicodedata

PREFISSO = 5          # lettere confrontate di ogni parola
MIN_LETTERE = 4
MIN_STORIA = 2        # parole in comune con i turni di prima per dirlo pertinente
TURNI_STORIA = 4      # messaggi della conversazione guardati (utente e Calliope)

# Parole senza contenuto, e quelle che incorniciano la domanda («approfondiamo questo
# argomento», «dimmi di più»): non dicono di cosa si parla
_VUOTE = frozenset("""
anche ancora molto molti molta molte tanto tanta tanti tante tutto tutta tutti tutte sono
essere stato stata stati state hanno avere aveva avevano della delle dello degli dalla dalle
dallo dagli nella nelle nello negli sulla sulle sullo sugli alla alle allo agli questo questa
questi queste quello quella quelli quelle quel perche quando quanto quanta quanti quante come
cosa cose dove mentre dopo prima sempre ogni altro altra altri altre loro nostro nostra vostro
vostra proprio propria pero quindi infatti invece oppure circa fino cosi solo sola soli anni
anno parte modo volta volte fatto fatta fatti fare fanno dire detto detta dici dimmi parlami
raccontami raccontare spiegami spiegare parlare parliamo sapere saperne vorrei voglio vuoi
posso puoi potresti possiamo cerca cercare cercato trova trovare trovato trovati grazie certo
bene allora ecco quale quali qualche qualcosa nessuno nessuna niente nulla calliope argomento
argomenti approfondiamo approfondisci approfondire approfondimento interessante storia secondo
inoltre ecco essa esso esse essi sulla viene vengono venire puo deve devono possono anzi
inizio fine dentro fuori sopra sotto senza verso presso
""".split())
_PAROLA = re.compile(r"[^\W\d_]+", re.UNICODE)


def _senza_accenti(testo: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", testo.lower())
                   if unicodedata.category(c) != "Mn")


def radici(testo: str) -> set[str]:
    """Le parole piene di `testo`, ridotte alle prime PREFISSO lettere."""
    out = set()
    for p in _PAROLA.findall(_senza_accenti(str(testo or ""))):
        if len(p) >= MIN_LETTERE and p not in _VUOTE:
            out.add(p[:PREFISSO])
    return out


def misura(testi: list[str], frase: str, storia: list | None = None) -> dict | None:
    """{"pertinenti": n, "totale": m} per i testi dei risultati (titolo e testo di ognuno),
    rispetto alla frase di chi parla e alla conversazione appena prima (`storia`: [(ruolo,
    testo)], come ToolContext.storia). None se non c'è niente con cui confrontare (né la frase
    né i turni hanno parole piene) o nessun risultato."""
    if not testi:
        return None
    r_frase = radici(frase)
    r_storia = set()
    for voce in list(storia or [])[-TURNI_STORIA:]:
        testo = voce[1] if isinstance(voce, (tuple, list)) and len(voce) > 1 else voce
        r_storia |= radici(testo if isinstance(testo, str) else "")
    r_storia -= r_frase
    if not r_frase and not r_storia:
        return None
    n = 0
    for t in testi:
        r = radici(t)
        if r & r_frase or len(r & r_storia) >= MIN_STORIA:
            n += 1
    return {"pertinenti": n, "totale": len(testi)}


def detta(m: dict | None) -> str | None:
    """La misura come la legge il modello: «0 su 5», o None."""
    if not m:
        return None
    return f"{m['pertinenti']} su {m['totale']}"


# La nota quando nessun risultato ha parole in comune con la conversazione: un dato, non un
# ordine (il modello può sapere che c'entrano lo stesso)
NOTA_NESSUNO = ("nessun risultato ha parole in comune con ciò di cui state parlando: "
                "probabilmente parlano d'altro")
