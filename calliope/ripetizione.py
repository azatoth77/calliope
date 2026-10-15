"""
La risposta uguale alla precedente (09/10/2026, rete del modello `risposta_ripetuta`).

Caso vero della DGX alle 19:06:49 e 19:07:04: a «No, mi riferivo alla richiesta di un attimo
fa» e poi a «Punto prima.» il modello ha detto due volte, parola per parola, la stessa frase
lunga («Mi hai chiesto esattamente cos'è che mi avevi chiesto un attimo fa. Un loop degno di
un film di Christopher Nolan…»). La persona aveva detto una cosa nuova; la risposta no.

Brain.ClaimHold trattiene la prima frase della risposta (non costa latenza: la voce
aspetterebbe comunque la fine di quella frase) e, se comincia come la risposta precedente,
anche il resto; a risposta finita, se è quasi uguale alla precedente (`ripete`), non si dice:
il modello riceve la spinta `RIPETUTA_NUDGE` una volta e decide (anche di ripeterla, se la
persona l'ha chiesto). Le risposte brevi uguali sono legittime («Fatto.», «Va bene.»): sotto
`MIN_PAROLE` parole non si guarda niente. È una correzione della forma di una scelta del
modello, non un significato deciso dal codice (principio 10).

**La domanda insistita** (15/10, rete `domanda_insistita`, caso vero in auto col 26B; qui con
nomi di fantasia): «Quali erano questi risultati?» → «ha menzionato dei risultati relativi ai
mondiali…», poi «Ma quali sono questi risultati? Lo hai capito?» → la stessa risposta (la rete
qui sopra ne ha scartata una, la seconda era quasi uguale e passava). La spinta di prima diceva
«chi parla ha appena detto una cosa nuova»: falso, chiedeva di nuovo la stessa cosa perché la
risposta non bastava. `insiste` riconosce, solo sulla forma, una domanda che riprende le parole
della domanda di prima (le parole piene della più corta quasi tutte nell'altra) dopo una
risposta lunga: allora nei dati del turno va `INSISTE_MSG` (il modello decide se è
un'insistenza) e, se la risposta è di nuovo uguale, la spinta `RIPETUTA_NUDGE_INSISTE`. Non è un
significato deciso dal codice (principio 10): una frase di contesto, condizionale. Con
l'insistenza la rete della risposta uguale trattiene già da `SOGLIA_INSISTE` (una correzione
della forma, come quella di sempre).

Solo libreria standard.
"""
from __future__ import annotations

import difflib
import re

# Sotto queste parole una risposta uguale è legittima («Fatto.», «Sono le dieci e venti.»)
MIN_PAROLE = 8
# Quanto devono somigliarsi le parole (SequenceMatcher sulle liste di parole)
SOGLIA = 0.85

RIPETUTA_NUDGE = ("La risposta che stavi per dare è uguale alla tua risposta precedente, e chi "
                  "parla ha appena detto una cosa nuova: non ripeterla. Rispondi a quello che "
                  "ha detto adesso, con parole nuove; se non capisci cosa vuole, chiediglielo "
                  "in breve. Solo se ti ha chiesto proprio di ripetere, ripeti pure.")


# Con l'insistenza (domanda_insistita) la spinta non dice «una cosa nuova»
RIPETUTA_NUDGE_INSISTE = (
    "La risposta che stavi per dare è uguale alla tua risposta precedente, e chi parla ti ha "
    "chiesto di nuovo la stessa cosa perché quella risposta non gli è bastata: non ripeterla. "
    "Dai il dettaglio preciso che chiede con quello che hai, anche se incerto (dicendo che ti "
    "è sembrato di sentirlo o di capirlo), oppure di' chiaramente quale pezzo non hai capito.")
# Dati del turno quando la domanda riprende quella di prima (rete domanda_insistita)
INSISTE_MSG = (
    "Dati del turno: chi parla ti fa una domanda simile a quella del turno prima. Se ti sta "
    "chiedendo di nuovo la stessa cosa, la tua risposta di prima non gli è bastata: non "
    "ripeterla con altre parole. Di' il dettaglio preciso che chiede (quali, quanti, chi, cosa "
    "di preciso) con quello che hai, anche incerto, dicendo che ti è sembrato di sentirlo o di "
    "capirlo; se quel pezzo non l'hai capito, di' quale. Se invece chiede altro, questa riga "
    "non conta.")
# Parole che non dicono di che cosa si parla: articoli, preposizioni, pronomi, ausiliari, le
# parole delle domande. Le altre sono «piene»
VUOTE = frozenset("""
a ad al allo alla ai agli alle da dal dallo dalla dai dagli dalle di del dello della dei degli
delle in nel nello nella nei negli nelle con col coi su sul sullo sulla sui sugli sulle per tra
fra il lo la i gli le l un uno una un' e ed o od ma però anche poi allora quindi dunque che chi
cosa cos come dove quando quanto quanta quanti quante quale quali perché perche se non sì si no
mi ti ci vi ne lo li me te ce ve se sé gli io tu lui lei noi voi loro mio mia miei mie tuo tua
tuoi tue suo sua suoi sue questo questa questi queste quello quella quelli quelle quel quei
è e' era erano sono sei siamo siete sia stato stata essere ho hai ha abbiamo avete hanno avevi
aveva avevo avere c ci più già ancora proprio solo tutto tutti tutta tutte calliope dimmi
dici detto dire sai so ok ecco eh beh
""".split())
# Quante parole piene della domanda più corta devono essere nell'altra
INSISTE_SOGLIA = 0.6
# Con la domanda insistita la risposta «quasi uguale» si trattiene già da qui (15/10: sul banco
# col 4B la risposta al «lo hai capito?» somigliava a quella di prima per 0,76–0,79 e passava)
SOGLIA_INSISTE = 0.7


def parole(testo: str) -> list[str]:
    return re.findall(r"\w+", (testo or "").lower())


def inizia_come(frase: str, precedente: str, soglia: float = SOGLIA) -> bool:
    """La prima frase della risposta comincia come la risposta precedente (quasi uguale alla
    sua parte iniziale della stessa lunghezza), e la precedente era lunga."""
    a, b = parole(frase), parole(precedente)
    if len(b) < MIN_PAROLE or len(a) < 4:
        return False
    return difflib.SequenceMatcher(None, a, b[:len(a)], autojunk=False).ratio() >= soglia


def ripete(testo: str, precedente: str, soglia: float = SOGLIA) -> bool:
    """La risposta intera è (quasi) uguale alla precedente, ed è lunga."""
    a, b = parole(testo), parole(precedente)
    if len(a) < MIN_PAROLE or len(b) < MIN_PAROLE:
        return False
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= soglia


def risposta_precedente(storia: list[dict], domanda: str | None = None) -> str | None:
    """L'ultima risposta detta nella storia (prima della domanda di adesso): il testo
    dell'ultimo messaggio di Calliope senza chiamate di tool. None se la domanda di adesso è
    (quasi) uguale a quella che l'aveva avuta: alla stessa domanda la stessa risposta va bene
    (prova_corsie_satelliti, «Che tempo fa domani?» chiesto di nuovo dopo un riavvio)."""
    risposta = None
    for m in reversed(storia or ()):
        ruolo = m.get("role")
        if (risposta is None and ruolo == "assistant" and not m.get("tool_calls")
                and (m.get("content") or "").strip()):
            risposta = str(m["content"])
        elif risposta is not None and ruolo == "user":
            a, b = parole(domanda or ""), parole(str(m.get("content") or ""))
            if a and b and difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= SOGLIA:
                return None
            return risposta
    return risposta


def piene(testo: str) -> set[str]:
    """Le parole piene (non in VUOTE, almeno 3 lettere) di una frase."""
    return {w for w in parole(testo) if w not in VUOTE and len(w) >= 3 and not w.isdigit()}


def domanda_simile(domanda: str, precedente: str) -> bool:
    """La domanda riprende quella di prima: uguale o quasi (SOGLIA sulle parole), oppure le
    parole piene della più corta sono quasi tutte (INSISTE_SOGLIA) nell'altra. Solo forma."""
    a, b = parole(domanda), parole(precedente)
    if not a or not b:
        return False
    if difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= SOGLIA:
        return True
    pa, pb = piene(domanda), piene(precedente)
    if not pa or not pb:
        return False
    corta, lunga = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return len(corta & lunga) / len(corta) >= INSISTE_SOGLIA


def insiste(storia: list[dict], domanda: str | None) -> str | None:
    """La risposta di prima, se la domanda di adesso riprende la domanda dell'ultimo turno
    (`domanda_simile`) e quella risposta era lunga (almeno MIN_PAROLE parole: a «Fatto.» non
    c'è un dettaglio mancato); None altrimenti. L'ultimo turno è l'ultima frase di chi parla
    nella storia (prima della domanda di adesso) e l'ultima risposta detta dopo di essa."""
    if not domanda:
        return None
    risposta = None
    for m in reversed(storia or ()):
        ruolo = m.get("role")
        if (risposta is None and ruolo == "assistant" and not m.get("tool_calls")
                and (m.get("content") or "").strip()):
            risposta = str(m["content"])
        elif ruolo == "user":
            if risposta is None or len(parole(risposta)) < MIN_PAROLE:
                return None
            return risposta if domanda_simile(domanda, str(m.get("content") or "")) else None
    return None
