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


def parole(testo: str) -> list[str]:
    return re.findall(r"\w+", (testo or "").lower())


def inizia_come(frase: str, precedente: str) -> bool:
    """La prima frase della risposta comincia come la risposta precedente (quasi uguale alla
    sua parte iniziale della stessa lunghezza), e la precedente era lunga."""
    a, b = parole(frase), parole(precedente)
    if len(b) < MIN_PAROLE or len(a) < 4:
        return False
    return difflib.SequenceMatcher(None, a, b[:len(a)], autojunk=False).ratio() >= SOGLIA


def ripete(testo: str, precedente: str) -> bool:
    """La risposta intera è (quasi) uguale alla precedente, ed è lunga."""
    a, b = parole(testo), parole(precedente)
    if len(a) < MIN_PAROLE or len(b) < MIN_PAROLE:
        return False
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= SOGLIA


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
