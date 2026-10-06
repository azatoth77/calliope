"""
Costanti e piccole funzioni comuni a più moduli (06/10, proposta P10 dell'analisi
complessiva): prima ognuna aveva la sua copia, e una correzione andava fatta in 10–17 posti.

Solo libreria standard: lo importa anche il pacchetto del satellite.
"""

import re

# Il campo «fatto» dei risultati dei tool rifiutati: con un semplice «non permesso» il
# modello diceva «ho registrato…» (vedi la memoria in CLAUDE.md)
NIENTE = "NIENTE: l'azione NON è stata eseguita"

# Livelli di chi parla (docs/architettura-tool.md)
ALL = frozenset({"ospite", "familiare", "amministra"})
FAMILY = frozenset({"familiare", "amministra"})
ADMIN = frozenset({"amministra"})
RANK = {"ospite": 0, "familiare": 1, "amministra": 2}
# I livelli ammessi «da questo livello in su»
LIVELLI_DA = {"ospite": ALL, "familiare": FAMILY, "amministra": ADMIN}

MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")

# Fine di una frase per lo streaming verso il TTS (tts.split_sentences, Brain)
SENTENCE_END = re.compile(r"[.!?…]+[\"»)\]]?\s+|\n+")

# Gli indirizzi che restano su questo computer
LOCALI = ("127.0.0.1", "localhost", "::1")


def solo_locale(host: str) -> bool:
    """L'indirizzo d'ascolto non esce da questo computer."""
    return str(host or "").strip() in LOCALI


def iban_ok(iban: str) -> bool:
    """IBAN con il controllo mod 97 (ISO 13616), senza spazi e in maiuscolo."""
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban or ""):
        return False
    n = "".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])
    return int(n) % 97 == 1
