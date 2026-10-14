"""
Il computer appena acceso, per le prove (14/10/2026). `time.monotonic()` parte da un valore
piccolo dopo l'avvio di Windows: una prova che scrive 0.0 per dire «tanto tempo fa» (una cache
o un rifiuto scaduti) cadeva nei primi minuti dopo un riavvio, e solo lì (prova_esercizi_
programma e prova_contesto_agenti il 14/10, nella prima suite dopo il riavvio). Le prove
scrivono «adesso meno la durata» (`fa`); i contrari girano con `appena_acceso`, che dà a un
modulo un orologio monotono che parte da pochi secondi.

    with appena_acceso(sessione_mod):     # sessione_mod.time.monotonic() ≈ 5 s
        ...
"""
import contextlib
import time
from unittest import mock


def fa(secondi: float) -> float:
    """Il valore di `time.monotonic()` di `secondi` fa (anche negativo: va bene così)."""
    return time.monotonic() - secondi


class _TempoAppenaAcceso:
    """Il modulo `time`, con `monotonic()` che parte da `inizio` secondi."""

    def __init__(self, inizio: float):
        self._scarto = time.monotonic() - inizio

    def monotonic(self) -> float:
        return time.monotonic() - self._scarto

    def __getattr__(self, nome):
        return getattr(time, nome)


@contextlib.contextmanager
def appena_acceso(*moduli, inizio: float = 5.0):
    """Dentro il blocco i `moduli` (che fanno `import time`) vedono un computer acceso da
    `inizio` secondi. Solo il loro `time`: il resto del processo (server finti, thread) no."""
    finto = _TempoAppenaAcceso(inizio)
    with contextlib.ExitStack() as pila:
        for m in moduli:
            pila.enter_context(mock.patch.object(m, "time", finto))
        yield finto
