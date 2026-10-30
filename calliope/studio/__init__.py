"""
Lo Studio (dal 29/10, passo 4.1 del progetto del telefono a sezioni, issue #280, epic #251,
decisione 0035): verifiche con una data, materiali e pagine, argomenti confermati e un piano a
giorni calcolato dal codice. Rifatto da capo dopo aver tolto il vecchio processo degli esercizi
(#279).

- `dati.py`: lo schema in `memoria.db` (`studio_*`, modulo «studio» in `meta_schema`) e il
  solo posto che cancella (tenuta, «dimentica», `--svuota`);
- `piano.py`: il piano a giorni, puro e deterministico, le tappe e la previsione;
- `servizio.py`: l'API interna (`Studio`) con i permessi e l'interruttore `studio_modo`;
- `pagine.py` (29/10, passo 4.2, #281): il controllo del server sulle foto e sui PDF delle pagine
  (bordi ricontrollati, raddrizzamento, nitidezza, PDF divisi in pagine, file su disco), per
  `POST /api/studio/pagina`.

- `lettura.py` (30/10, passo 4.3, #282): il lettore delle pagine in un thread, con l'harness del
  banco (qwen3.6 su vLLM), i controlli del codice e la guardia della DGX.

- `argomenti.py` (30/10, passo 4.4, #283): gli argomenti dal solo testo letto, chiesti dal thread
  del lettore con l'harness del banco, il controllo delle pagine citate e la forma del titolo; la
  conferma della persona è in `servizio.py`.

Arrivano dopo: il tool, la home e la vista aperta (4.5).
"""

from .servizio import (ATTIVO, MODI, OMBRA, SPENTO, NonPermesso, NonTrovata, Studio,
                       TroppePagine, VerificaChiusa, modo, permesso, prepara)

__all__ = ["ATTIVO", "MODI", "OMBRA", "SPENTO", "NonPermesso", "NonTrovata", "Studio",
           "TroppePagine", "VerificaChiusa", "modo", "permesso", "prepara"]
