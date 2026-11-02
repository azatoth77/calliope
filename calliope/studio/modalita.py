"""
La modalità studio (02/11/2026, issue #376, decisione di chi amministra, 0035 punto 54).

Uno stato **in memoria**, per satellite, con un **elenco chiuso di due effetti**. Non è un
meccanismo per cambiare interruttori: non tocca la configurazione e non ha altri effetti.

**Si apre** alla prima chiamata riuscita di un tool dello Studio detta dal proprietario dal suo
dispositivo personale (`Ciclo._modalita_dopo_turno`), o aprendo la sezione Studio su quello schermo
(`POST /api/vista`, se il satellite legato allo schermo è dello stesso proprietario). **Si chiude**
uscendo dalla sezione (`{vista: null}`), dopo `studio_modalita_inattivita_min` minuti senza attività
dello Studio, a mezzanotte. Una riga della stanza non apre niente: la stanza non chiama tool.

**Effetto 1**: la stanza in pausa solo su quel satellite, motivo «studio» (`Stanza.pausa`): niente
righe nel turno e niente ascolto da lì, «in pausa» sugli schermi. La pausa scade da sola
(`fino`), e alla chiusura si riprende solo se è ancora la sua: quella scelta da una persona o quella
del ripasso non si toccano. Una pausa in memoria come le altre: dopo un riavvio la stanza riparte.

**Effetto 2** (`ToolRegistry.call`, `Ciclo._modalita_voce`): con la voce **non riconosciuta**, la
frase detta dal dispositivo personale vale come del proprietario, **solo per i tool dello Studio e
sui suoi dati** (`solo_propri`, `servizio.permesso`). Vale come la zona grigia (al più familiare,
`dispositivo.proprio`). La voce chiaramente di un altro vince. Niente con la compagnia, un
conoscente, un minore possibile; un tool fuori dallo Studio resta da ospite. La conversazione resta
quella anonima dell'ospite: la storia del proprietario non si apre a una voce non riconosciuta.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime
import threading
import time

MOTIVO = "studio"
# I tool dello Studio (calliope/tools/studio.py): l'effetto 2 vale solo per loro
TOOL = frozenset({"studio", "studio_pagina_leggi", "studio_carte", "studio_interroga",
                  "studio_attivita", "studio_ascolta", "studio_esercizio",
                  "studio_mappa_consigli"})
# Durante l'effetto 2 i permessi dello Studio valgono solo per i dati del proprietario (da tutore
# non si vedono quelli del suo minore): servizio.permesso
_SOLO_PROPRI = contextvars.ContextVar("studio_solo_propri", default=False)


def solo_propri_attivo() -> bool:
    return _SOLO_PROPRI.get()


@contextlib.contextmanager
def solo_propri():
    tok = _SOLO_PROPRI.set(True)
    try:
        yield
    finally:
        _SOLO_PROPRI.reset(tok)


class Modalita:
    def __init__(self, cfg, orologio=time.time):
        self.cfg, self.orologio = cfg, orologio
        self._stati: dict = {}                 # sat → {persona, giorno, ultimo}
        self._lock = threading.Lock()

    def inattivita_s(self) -> float:
        return float(getattr(self.cfg, "studio_modalita_inattivita_min", 0.0) or 0.0) * 60

    def accesa(self) -> bool:
        return self.inattivita_s() > 0

    def _giorno(self, ora: float) -> str:
        return datetime.date.fromtimestamp(ora).isoformat()

    def _minuti_pausa(self, ora: float) -> float:
        """I minuti della pausa della stanza: l'inattività, al più fino a mezzanotte."""
        dom = datetime.datetime.fromtimestamp(ora).date() + datetime.timedelta(days=1)
        mezzanotte = datetime.datetime.combine(dom, datetime.time()).timestamp()
        return max(min(self.inattivita_s(), mezzanotte - ora), 1.0) / 60

    def _pausa(self, sat, stanza, ora: float):
        """La pausa della stanza su questo satellite: si mette se non ce n'è una, si rinnova se è
        la sua e ne resta meno di metà; quella di un altro non si tocca."""
        if stanza is None:
            return
        try:
            p = stanza.stato_pausa(sat)
            nostra = p is not None and p.get("motivo") == MOTIVO
            if p is None and stanza.accesa_qui(sat):
                stanza.pausa(sat, MOTIVO, minuti=self._minuti_pausa(ora))
            elif nostra and (p.get("fino") or 0) - ora < self.inattivita_s() / 2:
                stanza.pausa(sat, MOTIVO, minuti=self._minuti_pausa(ora))
        except Exception:  # noqa: BLE001 — la stanza non ferma lo Studio
            pass

    def apri(self, sat, persona, stanza=None) -> bool:
        """Apre (o rinnova) la modalità sul satellite, per il suo proprietario."""
        if sat is None or not persona or not self.accesa():
            return False
        ora = self.orologio()
        with self._lock:
            self._stati[sat] = {"persona": str(persona), "giorno": self._giorno(ora), "ultimo": ora}
        self._pausa(sat, stanza, ora)
        return True

    def chiudi(self, sat, stanza=None) -> bool:
        with self._lock:
            st = self._stati.pop(sat, None)
        if stanza is not None:
            try:
                p = stanza.stato_pausa(sat)
                if p is not None and p.get("motivo") == MOTIVO:
                    stanza.riprendi(sat)
            except Exception:  # noqa: BLE001
                pass
        return st is not None

    def di(self, sat, stanza=None) -> dict | None:
        """Lo stato del satellite, o None; scaduta (inattività, mezzanotte) si chiude qui. Con la
        pausa della stanza finita intanto (quella del ripasso, un riavvio della stanza) la rimette."""
        ora = self.orologio()
        with self._lock:
            st = self._stati.get(sat)
        if st is None:
            return None
        if ora - st["ultimo"] > self.inattivita_s() or self._giorno(ora) != st["giorno"]:
            self.chiudi(sat, stanza)
            return None
        self._pausa(sat, stanza, ora)
        return dict(st)
