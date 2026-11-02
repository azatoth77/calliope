"""
La modalità studio (02/11/2026, issue #376, decisione di chi amministra, 0035 punto 54).

Uno stato **in memoria**, per satellite, con un **elenco chiuso di due effetti**. Non è un
meccanismo per cambiare interruttori: non tocca la configurazione e non ha altri effetti.

**Si apre** alla prima chiamata di un tool dello Studio detta dal proprietario dal suo dispositivo
personale (`Ciclo._modalita_dopo_turno`, `apre`), o aprendo la sezione Studio su quello schermo
(`POST /api/vista`, se il satellite legato allo schermo è dello stesso proprietario, e mai fuori
orario per un minore). **Si chiude** uscendo dalla sezione (`{vista: null}`), dopo
`studio_modalita_inattivita_min` minuti senza attività dello Studio, a mezzanotte. Una riga della
stanza non apre niente: con righe di un'altra voce nel turno la frase deve parlare dello Studio.

**Effetto 1**: la stanza in pausa solo su quel satellite, motivo «studio» (`Stanza.pausa`): niente
righe nel turno e niente ascolto da lì, «in pausa» sugli schermi. La pausa scade da sola
(`fino`), e alla chiusura si riprende solo se è ancora la sua: quella scelta da una persona o quella
del ripasso non si toccano. Una pausa in memoria come le altre: dopo un riavvio la stanza riparte.
«Ascolta di nuovo la stanza» detto da chi può spegne l'effetto 1 fino alla chiusura (`ascolta`).

**Effetto 2** (`ToolRegistry.call`, `Ciclo._modalita_voce`): con la voce **non riconosciuta**, la
frase detta dal dispositivo personale vale come del proprietario, **solo per i tool dello Studio e
sui suoi dati** (`solo_propri`, `servizio.permesso`). Vale come la zona grigia (al più familiare,
`dispositivo.proprio`). La voce chiaramente di un altro vince. Niente con la compagnia, un
conoscente, un minore possibile, fuori orario per un minore; un tool fuori dallo Studio resta da
ospite. `togli` e `archivia` non si eseguono (`SOLO_VOCE_SICURA`). La conversazione è quella del
proprietario, se è l'ultima di quel satellite (come la continuità): senza, un «sì» non sa a cosa
risponde. Per quella frase niente ricordi né avvisi del proprietario, e della storia solo i turni da
quando la modalità si è aperta (`dal`, Brain._storia_per_modello).
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime
import re
import threading
import time

MOTIVO = "studio"
# I tool dello Studio (calliope/tools/studio.py): l'effetto 2 vale solo per loro
TOOL = frozenset({"studio", "studio_pagina_leggi", "studio_carte", "studio_interroga",
                  "studio_attivita", "studio_ascolta", "studio_esercizio",
                  "studio_mappa_consigli"})
# Con la voce non riconosciuta queste non si eseguono: non si rimettono a posto da una frase sola,
# e chi è vicino al telefono le farebbe senza che il proprietario se ne accorga. `sposta` e
# `salta_oggi` restano: si possono rimettere a posto
SOLO_VOCE_SICURA = frozenset({"togli", "archivia"})
# La frase del turno parla dello Studio: serve solo se nel turno ci sono righe di un'altra voce
# (un vincolo di permesso, principio 10). Per i tool senza parole proprie in politica.VERBI
_PAROLE_STUDIO = re.compile(r"(?<![a-zà-ù])(?:stud[iy]|verific|compit|ripass|interrog|cart[ae]|"
                            r"mapp|prov[ae]|eserciz|piano|argoment|librer|sched|pagin)", re.I)
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


def apre(nome: str, args: dict, t) -> bool:
    """Questa chiamata può aprire (o tenere viva) la modalità? Un tool dello Studio con un'azione
    che esiste, anche se fallisce (`proponi_data` su una verifica che non c'è ancora); con righe di
    un'altra voce nel turno, solo se è ancorata alla frase: un comando sentito dalla TV, che il
    modello ha seguito, non spegne l'ascolto. `t` è il `politica.Turno` della chiamata."""
    from ..tools.studio import chiamata_nota
    if nome not in TOOL or not chiamata_nota(nome, args):
        return False
    if not any(fonte == "stanza" and str(x or "").strip() for fonte, x in (t.esterni or ())):
        return True
    from ..politica import CLASSI
    from ..valore import ancorata
    cl = CLASSI.get(nome)
    return bool(_PAROLE_STUDIO.search(t.testo or "")
                or (cl is not None and ancorata(cl, nome, args or {}, t)))


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

    def _pausa(self, sat, stanza, ora: float, st: dict):
        """La pausa della stanza su questo satellite: si mette se non ce n'è una, si rinnova se è
        la sua e ne resta meno di metà; quella di un altro non si tocca. Niente dopo «ascolta di
        nuovo la stanza» (`ascolta`)."""
        if stanza is None or st.get("ascolta"):
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

    def apri(self, sat, persona, stanza=None, dal: float | None = None) -> bool:
        """Apre (o rinnova) la modalità sul satellite, per il suo proprietario. `dal`: da quando la
        storia vale per la voce non riconosciuta (di serie adesso; dalla voce, l'ora della frase
        del turno che apre, perché il suo «sì» risponde a quel turno). Il rinnovo non lo sposta."""
        if sat is None or not persona or not self.accesa():
            return False
        ora = self.orologio()
        with self._lock:
            prima = self._stati.get(sat)
            viva = (prima is not None and prima["persona"] == str(persona)
                    and ora - prima["ultimo"] <= self.inattivita_s()
                    and prima["giorno"] == self._giorno(ora))
            st = {"persona": str(persona), "giorno": self._giorno(ora), "ultimo": ora,
                  "dal": prima["dal"] if viva else (ora if dal is None else dal),
                  "ascolta": bool(viva and prima.get("ascolta"))}
            self._stati[sat] = st
        self._pausa(sat, stanza, ora, st)
        return True

    def ascolta(self, sat):
        """«Ascolta di nuovo la stanza» detto da chi può: l'effetto 1 è spento fino alla chiusura
        della modalità (tools/stanza.py). La pausa la toglie chi chiama."""
        with self._lock:
            st = self._stati.get(sat)
            if st is not None:
                st["ascolta"] = True

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
        self._pausa(sat, stanza, ora, st)
        return dict(st)
