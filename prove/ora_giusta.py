"""L'ora detta in una risposta è quella di adesso? (03/10)

Dal 03/10 ora e data sono nel contesto del turno (calliope/brain.py, TURN_CONTEXT_MSG): a
«Che ore sono?» va bene anche la risposta giusta senza ora_attuale. Le prove con Ollama che
si aspettavano il tool accettano anche questa (ora_o_tool).
"""

import datetime
import re


def ore_dette(risposta: str) -> list[int]:
    """Gli orari detti nella risposta, in minuti dalla mezzanotte («le 8:31», «08.31»)."""
    return [int(h) * 60 + int(m)
            for h, m in re.findall(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", risposta or "")]


def ora_giusta(risposta: str) -> bool:
    """Un orario detto entro 2 minuti da adesso, e nessun altro (non quello della storia né
    uno inventato)."""
    now = datetime.datetime.now()
    adesso = now.hour * 60 + now.minute
    ore = ore_dette(risposta)
    return bool(ore) and all(min(abs(o - adesso), 1440 - abs(o - adesso)) <= 2 for o in ore)


def ora_o_tool(atteso, tools, risposta) -> bool:
    """Per un caso che aspettava ora_attuale: il tool, oppure l'ora giusta senza."""
    return atteso == "ora_attuale" and not tools and ora_giusta(risposta)
