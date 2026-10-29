"""
Lo Studio (dal 29/10, passo 4.1 del progetto del telefono a sezioni, issue #280, epic #251,
decisione 0035): verifiche con una data, materiali e pagine, argomenti confermati e un piano a
giorni calcolato dal codice. Rifatto da capo dopo aver tolto il vecchio processo degli esercizi
(#279).

- `dati.py`: lo schema in `memoria.db` (`studio_*`, modulo «studio» in `meta_schema`) e il
  solo posto che cancella (tenuta, «dimentica», `--svuota`);
- `piano.py`: il piano a giorni, puro e deterministico, le tappe e la previsione;
- `servizio.py`: l'API interna (`Studio`) con i permessi e l'interruttore `studio_modo`.

Arrivano dopo: le pagine dalla fotocamera (4.2), la lettura (4.3), gli argomenti dal modello
(4.4), il tool, la home e la vista aperta (4.5).
"""

from .servizio import (ATTIVO, MODI, OMBRA, SPENTO, NonPermesso, NonTrovata, Studio, modo,
                       permesso, prepara)

__all__ = ["ATTIVO", "MODI", "OMBRA", "SPENTO", "NonPermesso", "NonTrovata", "Studio", "modo",
           "permesso", "prepara"]
