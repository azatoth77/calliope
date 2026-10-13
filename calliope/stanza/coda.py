"""
La coda di Whisper con la precedenza (13/10, conversazione di stanza, passo 1: progetto § 3.2,
§ 3.11, § 5.5).

whisper-server serve una richiesta alla volta, faster-whisper sulla GPU anche: le trascrizioni
passano una alla volta (come `corsie.STTCondiviso` da sempre), ma chi aspetta passa nell'ordine
della precedenza e non di arrivo:

    TURNO      la frase di un turno (e le parole incerte dei suoi argomenti)
    RECUPERO   i segmenti della stanza del satellite appena interpellato, detti prima della
               domanda (§ 3.11: la risposta li deve vedere)
    STANZA     gli altri segmenti della stanza
    LENTA      la corsia lenta (passo 3: ritrascrizione, non ancora)

Una trascrizione già cominciata non si interrompe: la frase del turno aspetta al più quella
(un segmento ha il tetto di 20 s, ~0,6 s di Whisper sulla GPU). Per questo la stanza non comincia
un segmento qualunque mentre qualcuno sta parlando a Calliope (`stanza/ascolto.py`).
"""

import heapq
import itertools
import threading
from contextlib import contextmanager

TURNO, RECUPERO, STANZA, LENTA = 0, 1, 2, 3


class Precedenza:
    """Un lock con la precedenza: tra chi aspetta entra il più importante (poi il primo
    arrivato)."""

    def __init__(self):
        self._cond = threading.Condition()
        self._occupato = False
        self._attese: list = []
        self._n = itertools.count()
        self.chi = None                      # la precedenza di chi la tiene adesso

    @contextmanager
    def tieni(self, priorita: int = TURNO):
        biglietto = (int(priorita), next(self._n))
        with self._cond:
            heapq.heappush(self._attese, biglietto)
            try:
                while self._occupato or self._attese[0] != biglietto:
                    self._cond.wait()
            except BaseException:
                self._attese.remove(biglietto)
                heapq.heapify(self._attese)
                self._cond.notify_all()
                raise
            heapq.heappop(self._attese)
            self._occupato, self.chi = True, biglietto[0]
        try:
            yield
        finally:
            with self._cond:
                self._occupato, self.chi = False, None
                self._cond.notify_all()

    def aspetta_turno(self) -> bool:
        """Una frase di un turno aspetta la trascrizione (la stanza non ne comincia altre)."""
        with self._cond:
            return any(p == TURNO for p, _ in self._attese)
