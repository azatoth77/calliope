"""
Il computer appena acceso, per le prove (14/10/2026). `time.monotonic()` parte da un valore
piccolo dopo l'avvio di Windows: una prova che scrive 0.0 per dire «tanto tempo fa» (una cache
o un rifiuto scaduti) cadeva nei primi minuti dopo un riavvio, e solo lì (prova_esercizi_
programma e prova_contesto_agenti il 14/10, nella prima suite dopo il riavvio). Le prove
scrivono «adesso meno la durata» (`fa`); i contrari girano con `appena_acceso`, che dà a un
modulo un orologio monotono che parte da pochi secondi.

    with appena_acceso(sessione_mod):     # sessione_mod.time.monotonic() ≈ 5 s
        ...

L'ora del giorno (18/10, issue #151). Una scena «tre ore fa» controllata con un formato fisso
(«HH:MM») cadeva fra mezzanotte e le 3, quando le righe diventano di «ieri» («ieri 23:42»):
`prova_stanza_cerca` fermava l'hook ogni notte. Con `ora_del_giorno` la prova gira a un'ora nota
di oggi, e i casi della notte si provano apposta:

    with ora_del_giorno(0, 30):           # time.time() = oggi alle 00:30, e avanza
        ...
"""
import contextlib
import datetime
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


def adesso_alle(ore: int, minuti: int = 0, giorno: datetime.date | None = None,
                secondi: int = 0) -> float:
    """L'epoch di `giorno` (di serie oggi) alle `ore`:`minuti`:`secondi`, ora locale."""
    giorno = giorno or datetime.date.today()
    return datetime.datetime(giorno.year, giorno.month, giorno.day, ore, minuti,
                             secondi).timestamp()


@contextlib.contextmanager
def ora_del_giorno(ore: int, minuti: int = 0, giorno: datetime.date | None = None,
                   secondi: int = 0):
    """Dentro il blocco `time.time()` di tutto il processo parte da `giorno` (di serie oggi)
    alle `ore`:`minuti` e avanza come quello vero. Solo `time.time()`: `datetime.now()` e
    `time.monotonic()` restano veri (le scene che dipendono dall'ora si scrivono da
    `time.time()`). Rende l'epoch di partenza."""
    vero = time.time
    scarto = adesso_alle(ore, minuti, giorno, secondi) - vero()
    with mock.patch.object(time, "time", lambda: vero() + scarto):
        yield vero() + scarto
