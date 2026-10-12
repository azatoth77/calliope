"""
Esercizi con le unità di misura (12/10/2026): il pezzo comune a fisica e chimica.

Un esercizio «misura» ha la risposta in un'unità precisa (`dati["unita"]`, chiave di
`calliope.unita.UNITA`) e porta l'espressione del conto **nelle unità di base** (m, kg, s,
mol): il ricalcolo (`verifica`) la rifà con il valutatore a frazioni esatte della matematica e
la confronta con la risposta convertita. Così un errore del generatore o di un fattore di
conversione non arriva mai al ragazzo. La risposta ha al più due decimali (l'esercizio si
costruisce dalla soluzione): il confronto è esatto, senza tolleranza.

La correzione (`controlla`) legge numero e unità con `unita.leggi_misura`:

- unità giusta e numero giusto → giusta;
- **nessuna unità** e numero giusto (la domanda la dice già) → giusta, con «ricordati di dire
  anche l'unità»;
- un'altra unità della stessa grandezza con la stessa misura («10 metri al secondo» per «36
  chilometri all'ora») → giusta, con la misura nell'unità chiesta; se l'esercizio è una
  **conversione** (`obbligatoria`) non vale, e non conta come errore;
- un'unità di un'altra grandezza → sbagliata («qui serve una velocità»); con il numero giusto
  non conta come errore (l'unità si corregge al tentativo dopo);
- unità «tollerate» (la massa molare detta in grammi o in unità di massa atomica) → giusta,
  con la forma corretta.
"""

from __future__ import annotations

from fractions import Fraction

from .. import unita as U
from .modello import Esercizio, Esito


def q(valore) -> str:
    """Un valore esatto scritto per `matematica.valuta` («(27/10)», «5»)."""
    f = Fraction(valore)
    return str(f.numerator) if f.denominator == 1 else f"({f.numerator}/{f.denominator})"


def nuovo(materia: str, argomento: str, livello: int, seme: int, testo: str, voce: str,
          valore, unita: str, suggerimenti, spiegazione: str, espressione_si: str,
          obbligatoria: bool = False, tollerate=(), **dati) -> Esercizio:
    v = Fraction(valore)
    return Esercizio(materia, argomento, livello, seme, testo, voce, "misura", v,
                     U.misura_detta(v, unita), list(suggerimenti), spiegazione, [],
                     espressione_si, {"unita": unita, "obbligatoria": bool(obbligatoria),
                                      "tollerate": list(tollerate), **dati},
                     {"tipo": "calcolato"})


def verifica(es: Esercizio) -> bool:
    """Il conto rifatto nelle unità di base torna con la risposta convertita? E la risposta
    si scrive con al più due decimali (si dice e si scrive esatta)?"""
    from .matematica import valuta
    try:
        attesa = U.in_si(es.risposta, es.dati["unita"])
        d = U.decimali(es.risposta)
        return d is not None and d <= 2 and valuta(es.espressione) == attesa
    except (ValueError, ZeroDivisionError, SyntaxError, TypeError, KeyError):
        return False


def controlla(es: Esercizio, risposta) -> Esito:
    m = U.leggi_misura(risposta)
    if m is None:
        return Esito(None, "", "Non ho capito il numero: dimmi il risultato, con l'unità di "
                               "misura.", False)
    chiave = es.dati["unita"]
    attesa = Fraction(es.risposta)
    nome = U.detta(chiave, attesa)
    if m.unita is None:
        if m.valore == attesa:
            return Esito(True, m.letta, f"Giusto! Ricordati di dire anche l'unità di misura: "
                                        f"{U.misura_detta(attesa, chiave)}.")
        return Esito(False, m.letta, _nota_numero(m.valore, attesa))
    if m.unita in es.dati.get("tollerate", ()):
        if m.valore == attesa:
            return Esito(True, m.letta, f"Giusto! Si dice {U.misura_detta(attesa, chiave)}.")
        return Esito(False, m.letta, _nota_numero(m.valore, attesa))
    if not U.stessa_grandezza(m.unita, chiave):
        grandezza = U.NOMI_GRANDEZZE.get(U.UNITA[chiave].grandezza, "un'altra grandezza")
        if m.valore == attesa:
            return Esito(False, m.letta, f"Il numero è giusto, ma l'unità no: qui serve "
                                         f"{grandezza}, in {U.detta(chiave)}.", False)
        return Esito(False, m.letta, f"Attenzione all'unità di misura: qui serve {grandezza}, "
                                     f"in {U.detta(chiave)}.")
    if U.in_si(m.valore, m.unita) == U.in_si(attesa, chiave):
        if m.unita == chiave:
            return Esito(True, m.letta)
        if es.dati.get("obbligatoria"):
            return Esito(False, m.letta, f"È la stessa misura, ma te l'ho chiesta in "
                                         f"{U.detta(chiave)}: quanto fa in {U.detta(chiave)}?",
                         False)
        return Esito(True, m.letta, f"Giusto! In {U.detta(chiave)} sono "
                                    f"{U.misura_detta(attesa, chiave)}.")
    if m.unita != chiave:
        return Esito(False, m.letta, f"Ricordati che te l'ho chiesta in {nome}.")
    return Esito(False, m.letta, _nota_numero(m.valore, attesa))


def _nota_numero(data: Fraction, attesa: Fraction) -> str:
    if data == -attesa and data != 0:
        return "Controlla il segno."
    if data != 0 and attesa != 0:
        r = attesa / data
        if r in (10, 100, 1000, Fraction(1, 10), Fraction(1, 100), Fraction(1, 1000)):
            return "Le cifre sono quelle giuste: controlla la virgola."
    return ""


def ore_dette(t) -> str:
    """Un tempo in ore detto come si dice: «mezz'ora», «un'ora e mezza», «2 ore e mezza»,
    «3 ore»."""
    t = Fraction(t)
    intere, resto = divmod(t, 1)
    if resto == Fraction(1, 2):
        if intere == 0:
            return "mezz'ora"
        return ("un'ora" if intere == 1 else f"{intere} ore") + " e mezza"
    if resto == 0:
        return "un'ora" if intere == 1 else f"{intere} ore"
    return U.misura_detta(t, "h")
