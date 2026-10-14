"""
System 1: decisori piccoli e veloci per le scelte chiuse che pesano sulla latenza (14/10/2026,
richiesta di Dario; ricerca in docs/ricerche/2026-10-14-system1-fine-turno.md).

L'idea è quella dei due sistemi: un modello minuscolo (millisecondi, sulla CPU) decide da solo
quando è sicuro; quando non lo è, la decisione resta a chi la prendeva prima (una regola fissa,
o il modello grande: «System 2»). Ogni decisore è un modulo sostituibile (principio 2) con la
stessa interfaccia:

    decisore.decide(dati) -> Decisione(scelta, sicurezza, ms)

- `scelta`: una delle scelte chiuse del decisore (`decisore.scelte`);
- `sicurezza`: 0–1, quanto è sicuro **di quella scelta** (per un classificatore a due classi,
  la probabilità della classe scelta: mai sotto 0,5);
- `ms`: quanto ha impiegato.

Un decisore non deve mai fermare la voce: `Sorvegliato` lo fa girare in un thread suo, con un
tempo massimo; se è lento la risposta è None (chi chiama fa come prima), se si guasta più volte
di fila si spegne da solo fino al riavvio. Il primo decisore è la fine del turno
(`fine_turno.py`); i casi successivi sono nella roadmap («System 1»).
"""
from __future__ import annotations

import concurrent.futures as cf
import threading
import time
from dataclasses import dataclass
from typing import Protocol

GUASTI_MAX = 5            # errori di fila dopo cui il decisore si spegne (fino al riavvio)


@dataclass(frozen=True)
class Decisione:
    scelta: str
    sicurezza: float
    ms: float = 0.0
    prob: float | None = None      # l'uscita grezza del modello, se c'è (per le misure)


class Decisore(Protocol):
    nome: str
    scelte: tuple[str, ...]

    def decide(self, dati) -> Decisione: ...


class Sorvegliato:
    """Un decisore in un thread suo: la voce non aspetta mai un decisore lento o guasto.

    `avvia(dati)` restituisce un Future (o None se il decisore è spento o ancora occupato con
    la domanda di prima: chi chiama fa come prima); `chiedi(dati, tempo_s)` aspetta la
    risposta al più `tempo_s` e restituisce la Decisione o None. Conta le risposte, le lente
    e i guasti (solo numeri)."""

    def __init__(self, decisore, log=print):
        self.decisore = decisore
        self.nome = getattr(decisore, "nome", type(decisore).__name__)
        self.log = log
        self._pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="system1")
        self._lock = threading.Lock()
        self._in_corso: cf.Future | None = None
        self.spento = False
        self.risposte = 0
        self.lente = 0
        self.guasti = 0
        self._guasti_di_fila = 0

    def _gira(self, dati) -> Decisione:
        t0 = time.perf_counter()
        try:
            d = self.decisore.decide(dati)
        except Exception as e:
            with self._lock:
                self.guasti += 1
                self._guasti_di_fila += 1
                if self._guasti_di_fila >= GUASTI_MAX and not self.spento:
                    self.spento = True
                    self.log(f"   [SYSTEM1] {self.nome}: {GUASTI_MAX} errori di fila "
                             f"({type(e).__name__}): spento fino al riavvio, resta la regola "
                             f"di prima")
            raise
        with self._lock:
            self._guasti_di_fila = 0
            self.risposte += 1
        if not d.ms:
            d = Decisione(d.scelta, d.sicurezza, (time.perf_counter() - t0) * 1000, d.prob)
        return d

    def avvia(self, dati) -> cf.Future | None:
        with self._lock:
            if self.spento:
                return None
            if self._in_corso is not None and not self._in_corso.done():
                self.lente += 1          # la domanda di prima non ha ancora risposto
                return None
            try:
                self._in_corso = self._pool.submit(self._gira, dati)
            except RuntimeError:         # pool chiuso
                return None
            return self._in_corso

    def chiedi(self, dati, tempo_s: float) -> Decisione | None:
        fut = self.avvia(dati)
        if fut is None:
            return None
        try:
            return fut.result(timeout=max(0.0, tempo_s))
        except cf.TimeoutError:
            with self._lock:
                self.lente += 1
            return None
        except Exception:  # noqa: BLE001 — contato in _gira
            return None

    def chiudi(self):
        self._pool.shutdown(wait=False, cancel_futures=True)


def risposta(fut: cf.Future | None) -> Decisione | None:
    """La decisione di un Future già finito, altrimenti None (non aspetta mai)."""
    if fut is None or not fut.done() or fut.cancelled():
        return None
    try:
        return fut.result(timeout=0)
    except Exception:  # noqa: BLE001
        return None
