"""
Sigle che Whisper scrive male, riscritte nella trascrizione (15/10/2026, caso vero in auto).

Il 14/10 sera, in auto, «PEGI 16» (la fascia d'età dei videogiochi) è arrivato come «PG-16»
nella stanza e nella ritrascrizione a blocchi della corsia lenta (revisione di Dario del
15/10). Il prompt di Whisper non si allunga (taratura del 24/09) e sulla DGX le hotwords non
passano: la sigla si riscrive dopo. È una conversione sulla trascrizione, ciò che il modello
non vede (principio 10), e solo la forma chiusa **sigla + fascia vera**: le fasce PEGI sono
3, 7, 12, 16 e 18, quindi «PG-13» (la sigla dei film americani), «PG» da sola e «Peggy» restano
come sono. Nel registro dei turni la regola `sigla_trascrizione`. Casi in prove/prova_testo.py.
"""
from __future__ import annotations

import re

# Le forme sentite e quelle vicine: «PG-16», «PG 16», «P.G. 16», «Pegi16», «peghi 16»,
# «PEGGI 16» (non «Peggy»: è un nome). «PG» solo maiuscola: «pg» minuscola non è Whisper
_PEGI = re.compile(
    r"(?<![\w.])(?:PG|P\.\s?G\.?|[Pp][Ee][Gg]{1,2}[HhIi]?[Ii])\s?[-–]?\s?(3|7|12|16|18)(?!\d|[.,]\d)")


def correggi_sigle(testo: str) -> tuple[str, list[str]]:
    """Il testo con le sigle riscritte e l'elenco delle forme cambiate (vuoto se niente)."""
    if not testo:
        return testo, []
    cambiate: list[str] = []

    def _pegi(m: re.Match) -> str:
        nuova = f"PEGI {m.group(1)}"
        if m.group(0) != nuova:
            cambiate.append(m.group(0))
        return nuova

    return _PEGI.sub(_pegi, testo), cambiate
