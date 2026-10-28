"""
Numeri in lettere (28/10/2026, #279): `in_lettere` per il filtro dell'eco della stanza
(`stanza/eco.py`), che confronta il testo detto da Calliope con quello sentito da Whisper.

Dall'08/10 al 28/10 stava in `calliope/esercizi/numeri.py`, con la lettura delle risposte degli
esercizi; gli esercizi sono stati tolti (decisione 0035) e qui resta solo ciò che serve fuori.
Solo libreria standard.
"""

from __future__ import annotations

_PAROLE_UNITA = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto",
                 "nove", "dieci", "undici", "dodici", "tredici", "quattordici", "quindici",
                 "sedici", "diciassette", "diciotto", "diciannove"]
_PAROLE_DECINE = {20: "venti", 30: "trenta", 40: "quaranta", 50: "cinquanta", 60: "sessanta",
                  70: "settanta", 80: "ottanta", 90: "novanta"}


def in_lettere(n: int) -> str:
    """Un intero da 0 a 999 999 in lettere («ventitré» senza accento: «ventitre»)."""
    n = int(n)
    if n < 0:
        return "meno " + in_lettere(-n)
    if n < 20:
        return _PAROLE_UNITA[n]
    if n < 100:
        d, u = divmod(n, 10)
        dec = _PAROLE_DECINE[d * 10]
        if u in (1, 8):
            dec = dec[:-1]
        return dec + (_PAROLE_UNITA[u] if u else "")
    if n < 1000:
        c, r = divmod(n, 100)
        cento = "cento" if c == 1 else _PAROLE_UNITA[c] + "cento"
        if r and in_lettere(r).startswith("o"):
            cento = cento[:-1]               # «centotto», «duecentottanta»
        return cento + (in_lettere(r) if r else "")
    m, r = divmod(n, 1000)
    mila = "mille" if m == 1 else in_lettere(m) + "mila"
    return mila + (in_lettere(r) if r else "")
