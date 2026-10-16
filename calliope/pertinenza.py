"""
Quanto i risultati di una ricerca parlano di ciò di cui si parlava (16/10/2026, issue #101).

Caso vero della DGX del 15/10 sera: dopo un racconto sul mito di Orione, «approfondiamo questo
argomento» → web_cerca con una domanda storpiata, risultati su una startup dal nome simile a una
parola della conversazione, e il modello li riferiva per intero nonostante il `cosa_fare`.

Qui solo una **misura** (principio 10: decide il modello se i risultati c'entrano, il codice non
toglie nulla), con tre modi (`ricerca_pertinenza`): «ombra» (di serie) la scrive solo nel registro
dei turni, «attiva» anche nel risultato come dato per il modello (`pertinenti: 0 su 5`),
«spenta» niente.

La misura è per parole in comune, senza modelli: un risultato è «pertinente» se ha almeno una
parola piena in comune con la frase di chi parla, oppure con i turni appena prima: almeno due, o
una sola quando la frase è breve e ha parole sue («e domani?», «e adesso chi è primo?»: un
seguito). La domanda composta dal modello non conta: è proprio quella che può uscire storpiata.

Parole piene: da quattro lettere fuori dall'elenco delle parole vuote, più le sigle in maiuscolo
(«PIL», «NBA», «F1») e i nomi brevi con la maiuscola («Eco», «Gea»). Due parole sono la stessa
(revisione della PR #115) se lo sono senza le vocali finali («gatti» e «gatto», «Orione» e
«Orion»), se una continua l'altra con una vocale («Roma» e «romano», «Milano» e «milanese», ma non
«Orione» e «Orionyx»), se cambiano solo nell'ultima lettera della radice («vinto» e «vince»), o se
da cinque lettere differiscono per una lettera sola («Siner» di Whisper e «Sinner»). Non vede i
sinonimi né le traduzioni («macchina» e «automobile», «mitologia» e «mythology»): per questo è in
ombra finché non si misura sulle ricerche vere.
"""
from __future__ import annotations

import re
import unicodedata

MIN_LETTERE = 4
MIN_STORIA = 2        # parole in comune con i turni di prima per dirlo pertinente
FRASE_BREVE = 5       # parole di una frase «breve»: con parole sue ne basta una con la storia
TURNI_STORIA = 4      # messaggi della conversazione guardati (utente e Calliope)
MODI = ("spenta", "ombra", "attiva")

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
inoltre essa esso esse essi viene vengono venire deve devono possono anzi inizio fine dentro
fuori sopra sotto senza verso presso
""".split())
# Parole brevi con la maiuscola che non sono nomi (inizio di frase)
_VUOTE_BREVI = frozenset("""
chi che cos com per con non una uno gli dei del nel sul dal dai sei sta era ora poi qui qua
mia mio tuo tua suo sua
""".split())
_PAROLA = re.compile(r"[^\W_]+", re.UNICODE)
_VOCALI = "aeiou"


def _senza_accenti(testo: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", testo)
                   if unicodedata.category(c) != "Mn")


def parole(testo: str) -> set[str]:
    """Le parole piene di `testo`, in minuscolo e senza accenti."""
    out = set()
    for p in _PAROLA.findall(_senza_accenti(str(testo or ""))):
        m = p.lower()
        if len(m) >= MIN_LETTERE and m.isalpha():
            if m not in _VUOTE:
                out.add(m)
        elif len(p) >= 2 and any(c.isalpha() for c in p) and (
                p.isupper() or any(c.isdigit() for c in p)):
            out.add(m)                                   # sigle: PIL, NBA, F1
        elif (len(p) == 3 and p.isalpha() and p[0].isupper() and p[1:].islower()
              and m not in _VUOTE_BREVI):
            out.add(m)                                   # nomi brevi: Eco, Gea
    return out


def _radice(p: str) -> str:
    r = p.rstrip(_VOCALI)
    return r if len(r) >= 3 else p


def _uno_di_distanza(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def stessa(a: str, b: str) -> bool:
    """Le due parole (già da `parole`) sono la stessa, con le flessioni (docstring del modulo)."""
    if a == b:
        return True
    ra, rb = _radice(a), _radice(b)
    if ra == rb:
        return True
    corta, lunga = (ra, rb) if len(ra) <= len(rb) else (rb, ra)
    if (len(corta) >= 3 and lunga.startswith(corta) and len(lunga) - len(corta) <= 4
            and lunga[len(corta)] in _VOCALI):
        return True
    if len(ra) == len(rb) >= 4 and ra[:-1] == rb[:-1]:
        return True
    return min(len(a), len(b)) >= 5 and _uno_di_distanza(a, b)


def _per_inizio(gruppo: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in gruppo:
        out.setdefault(p[:2], []).append(p)
    return out


def _comuni(cercate: set[str], indice: dict[str, list[str]], basta: int) -> int:
    """Quante parole di `cercate` hanno una parola uguale (`stessa`) nell'indice (le parole di
    un risultato per le prime due lettere), fermandosi a `basta`."""
    n = 0
    for p in cercate:
        if any(stessa(p, q) for q in indice.get(p[:2], ())):
            n += 1
            if n >= basta:
                break
    return n


def misura(testi: list[str], frase: str, storia: list | None = None) -> dict | None:
    """{"pertinenti": n, "totale": m} per i testi dei risultati (titolo e testo di ognuno),
    rispetto alla frase di chi parla e alla conversazione appena prima (`storia`: [(ruolo,
    testo)], come ToolContext.storia). None se non c'è niente con cui confrontare (né la frase
    né i turni hanno parole piene) o nessun risultato."""
    if not testi:
        return None
    p_frase = parole(frase)
    p_storia = set()
    for voce in list(storia or [])[-TURNI_STORIA:]:
        testo = voce[1] if isinstance(voce, (tuple, list)) and len(voce) > 1 else voce
        p_storia |= parole(testo if isinstance(testo, str) else "")
    p_storia -= p_frase
    if not p_frase and not p_storia:
        return None
    # Un seguito breve con parole sue («e domani?» dopo il meteo): basta una parola della storia
    breve = bool(p_frase) and len(_PAROLA.findall(str(frase or ""))) <= FRASE_BREVE
    soglia = 1 if breve else MIN_STORIA
    n = 0
    for t in testi:
        indice = _per_inizio(parole(t))
        if _comuni(p_frase, indice, 1) >= 1 or _comuni(p_storia, indice, soglia) >= soglia:
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


def modo(cfg) -> str:
    m = str(getattr(cfg, "ricerca_pertinenza", "ombra") or "ombra").strip().lower()
    return m if m in MODI else "ombra"


def applica(ctx, out: dict, testi: list[str]) -> None:
    """La misura sul risultato `out` di web_cerca o biblioteca_cerca, secondo il modo: sempre
    `ricerca_pertinenza_misurata`; in ombra, a zero, solo `ricerca_fuori_tema_ombra` (registro
    dei turni, niente al modello); attiva anche il campo «pertinenti» e `ricerca_fuori_tema`."""
    from .tools.spec import note_rule
    m_ = modo(getattr(ctx, "cfg", None))
    if m_ == "spenta":
        return
    pert = misura(testi, getattr(ctx, "user_text", "") or "", getattr(ctx, "storia", None))
    if pert is None:
        return
    note_rule(ctx, "ricerca_pertinenza_misurata")
    if m_ == "ombra":
        if pert["pertinenti"] == 0:
            note_rule(ctx, "ricerca_fuori_tema_ombra")
        return
    out["pertinenti"] = detta(pert) + (f" ({NOTA_NESSUNO})" if pert["pertinenti"] == 0 else "")
    if pert["pertinenti"] == 0:
        note_rule(ctx, "ricerca_fuori_tema")


# ── la riga di `calliope stato --turni` ──

def riassunto(turni: list[dict]) -> dict:
    """Ricerche misurate e «fuori tema» (attiva e in ombra) dal registro dei turni."""
    misurate = fuori = ombra = 0
    for t in turni:
        regole = t.get("regole") or ()
        misurate += "ricerca_pertinenza_misurata" in regole
        fuori += "ricerca_fuori_tema" in regole
        ombra += "ricerca_fuori_tema_ombra" in regole
    return {"misurate": misurate, "fuori_tema": fuori, "fuori_tema_ombra": ombra}


def testo(r: dict, modo_: str = "ombra") -> str:
    """La riga per `calliope stato --turni`."""
    if not r.get("misurate"):
        return (f"Pertinenza delle ricerche ({modo_}): nessuna ricerca misurata nel registro "
                "dei turni.")
    n = r["fuori_tema"] + r["fuori_tema_ombra"]
    return (f"Pertinenza delle ricerche ({modo_}): {n} «fuori tema» su {r['misurate']} turni "
            f"con ricerche misurate ({round(100 * n / r['misurate'])} %; in ombra "
            f"{r['fuori_tema_ombra']}, detti al modello {r['fuori_tema']}). Prima di «attiva» "
            "rileggere i turni con ricerca_fuori_tema_ombra.")
