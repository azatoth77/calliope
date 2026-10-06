"""
Installazioni a voce e da terminale, solo da un catalogo nel codice (01/10/2026).

- catalogo.py: cosa si può scaricare (biblioteca di Kiwix, voci di Piper, modello CAM++,
  modello di Ollama in llm_model), da dove, con quale checksum, dove va;
- scarica.py: lo scaricamento con ripresa (.part e Range), origini ammesse, checksum,
  spostamento atomico;
- servizio.py: prerequisiti, offerta in sospeso (avvio solo nel turno dopo la proposta,
  dalla stessa persona), lavoro in secondo piano, annullo, annuncio e attivazione.

Il modello non sceglie mai un URL né un comando: solo l'id di un'azione del catalogo. pip,
calliope.yaml e calliope.locale.yaml restano fuori: Calliope può solo dire cosa fare.
I tool vocali sono in calliope/tools/stato.py; da terminale python -m calliope.stato
--installa <azione>.
"""

from .catalogo import DESCRIZIONI, Azione, catalogo, risolvi_zim
from .servizio import Installazioni, parla_byte

__all__ = ["DESCRIZIONI", "Azione", "Installazioni", "catalogo", "parla_byte", "risolvi_zim"]
