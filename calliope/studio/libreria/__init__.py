"""
La libreria dello Studio (31/10, issue #297, epic #251, decisione 0035 punto 46): contenuti
preparati con Claude, scritti e rivisti da noi, originali e AGPL, che a runtime **il codice
sceglie** dagli argomenti della verifica e dalla padronanza. Niente modello: sono dati fidati
(come le frasi pronte), a differenza dei materiali della persona.

- `formato.py`: il formato JSON dei contenuti (schede, mazzi, mini-app) e il suo controllo;
- `indice.py`: la libreria caricata, l'indice per argomento e la scelta (`scegli`);
- `studio.py`: i metodi di `Studio` (proposte, scheda, «Aggiungi le carte», la home);
- `contenuti/<materia>/*.json`: i contenuti. Come se ne aggiunge uno:
  `prove/manuali/libreria-studio.md`.
"""

from .formato import FORMATO, MAZZO, MINIAPP, SCHEDA, TIPI, valida
from .indice import Libreria, parole, scegli

__all__ = ["FORMATO", "MAZZO", "MINIAPP", "SCHEDA", "TIPI", "Libreria", "parole", "scegli",
           "valida"]
