"""
La modalità studio (02/11/2026, issue #376, decisione di chi amministra, 0035 punto 54).

Uno stato **in memoria**, per satellite, con un **elenco chiuso di tre effetti**. Non è un
meccanismo per cambiare interruttori: non tocca la configurazione e non ha altri effetti.

**Si apre** alla prima chiamata di un tool dello Studio detta dal proprietario dal suo dispositivo
personale (`Ciclo._modalita_dopo_turno`, `apre`), o aprendo la sezione Studio su quello schermo
(`POST /api/vista`, se il satellite legato allo schermo è dello stesso proprietario, e mai fuori
orario per un minore). **Si chiude** uscendo dalla sezione (`{vista: null}`), dopo
`studio_modalita_inattivita_min` minuti senza attività dello Studio, a mezzanotte. Una riga della
stanza non apre niente: con un dato letto nel turno (righe di un'altra voce, una pagina, una
ricerca) la frase deve parlare dello Studio.

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
ospite. `togli`, `archivia` e `conclusa` non si eseguono (`SOLO_VOCE_SICURA`).

**Effetto 3** (04/11, issue #383, `Ciclo._modalita_turno`, `Brain._sviluppo_coda`): su quel satellite
Calliope non aggiunge alle risposte il promemoria degli sviluppi sospesi né la riga dello sviluppo
aperto, a meno che si stia parlando dello sviluppo. Il promemoria non si consuma: torna dopo la
chiusura. Giro vero del 03/11: «A proposito: lo sviluppo di … è sospeso» detto a chi stava studiando.

**Per quella frase Brain lavora come per un ospite qualunque**: la sua conversazione è una da ospite
(`corsie`, «modalita»), `_speaker_key` è None, e ciò che è legato al proprietario non c'è per
costruzione, anche un canale nuovo. Le eccezioni sono questo elenco chiuso, in `presta` e `riporta`:
- i turni da quando la modalità si è aperta (`dal`), copiati senza foto, allegati, righe della stanza e
  dati fissi, se la sua conversazione è l'ultima di questo satellite: senza, un «sì» non sa a cosa
  risponde. Il turno di quella voce torna poi nella conversazione del proprietario, che lo ritrova. Se non
  lo è, quella voce tiene i suoi turni, che tornano a lui quando parla qui;
- le proposte dei tool dello Studio (`TOOL`), con i «no» dati a quelle;
- i tool dello Studio come proprietario (`ToolRegistry._come_proprietario`);
- la riga dei dati del turno che dice chi parla (Brain, «voce non riconosciuta, dal telefono di…»);
- i testi dei dati non fidati (`esterni`): solo per la provenienza degli argomenti, non vanno al modello.
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
# `salta_oggi` restano: si possono rimettere a posto. `conclusa` chiude le prove aperte come
# «annullate» e le mappe come controllate: spostare la data riapre la verifica, non la prova
SOLO_VOCE_SICURA = frozenset({"togli", "archivia", "conclusa"})
# La frase del turno parla dello Studio: serve solo se nel turno c'è un dato letto (le righe di
# un'altra voce, una pagina, una ricerca)
# (un vincolo di permesso, principio 10). Per i tool senza parole proprie in politica.VERBI
_PAROLE_STUDIO = re.compile(r"(?<![a-zà-ù])(?:stud[iy]|verific|compit|ripass|interrog|cart[ae]|"
                            r"mapp|prov[ae]|eserciz|piano|argoment|librer|sched|pagin)", re.I)
# Dei turni prestati alla voce non riconosciuta restano fuori: foto, allegati, righe della stanza, dati
# fissi e schede del proprietario
_DEL_PROPRIETARIO = frozenset({"_img", "_all", "_all_info", "_stanza", "_dati", "_schede", "_turno"})
# Quanti «no» d'altro tiene la conversazione di quella voce
_RIFIUTI_VOCE = 8
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


def consegna(voce, proprietario, chi, prestata: bool = False):
    """I turni di quella voce (non le copie), con la proposta dello Studio e i «no» a quelle, passano
    alla conversazione del `proprietario`, senza i segni che valgono solo per la sua (foto, allegati,
    righe). Quella d'altro del proprietario resta intatta. `prestata`: la proposta che ha adesso era sua."""
    nuovi = [{k: v for k, v in m.items() if k == "_turno" or k not in _DEL_PROPRIETARIO}
             for m in voce.history if not m.get("_prestato")]
    voce.history.clear()
    voce.archiviati = 0
    proprietario.riporta_turno(nuovi)
    if voce.last_turn_at is not None:
        proprietario.last_turn_at = voce.last_turn_at
    proprietario.rifiutate.extend(r for r in voce.rifiutate if r.get("tool") in TOOL
                                  and r not in proprietario.rifiutate)
    voce.rifiutate = [r for r in voce.rifiutate if r.get("tool") not in TOOL][-_RIFIUTI_VOCE:]
    p, q = voce.pending, proprietario.pending
    if not isinstance(q, dict) or q.get("tool") in TOOL:
        if isinstance(p, dict) and p.get("tool") in TOOL:
            proprietario.pending = {**p, "chi": chi}
            voce.pending = None
        elif prestata:
            proprietario.pending = None     # consumata o rifiutata da quella voce


def presta(voce, proprietario, dal: float, chi):
    """Prima della frase della voce non riconosciuta. Con la conversazione del `proprietario` (di
    persona `chi`), se è l'ultima di questo satellite: entrano solo le eccezioni qui sopra, in copia,
    e i turni che quella voce aveva tenuti tornano a lui. Senza (`proprietario` None: modalità aperta
    dalla pagina, conversazione chiusa a tempo o usata da un altro satellite) la conversazione della
    voce tiene i suoi turni e scade a tempo come ogni altra."""
    voce.owner = None
    if proprietario is None:
        voce.prestito = None
        return
    consegna(voce, proprietario, chi)
    da = next((i for i, m in enumerate(proprietario.history)
               if m.get("role") == "user" and float(m.get("_t") or 0.0) >= dal), None)
    voce.history[:] = [] if da is None else [
        {**{k: v for k, v in m.items() if k not in _DEL_PROPRIETARIO}, "_prestato": True}
        for m in proprietario.history[da:]]
    voce.archiviati = len(voce.history)
    voce.prestito = {"proprietario": proprietario, "chi": chi}
    # Le copie non scadono qui: se la conversazione del proprietario è ferma da troppo la chiude il
    # registro, prima di questo prestito
    voce.last_turn_at = None
    voce.turn_number = proprietario.turn_number
    voce.esterni = list(proprietario.esterni)
    voce.rifiutate = list(voce.rifiutate) + [
        r for r in proprietario.rifiutate if r.get("tool") in TOOL and r not in voce.rifiutate]
    q = proprietario.pending
    if isinstance(q, dict) and q.get("tool") in TOOL:
        voce.pending = {**q, "chi": None}
        voce.prestito["proposta"] = True


def riporta(voce):
    """Dopo quella frase: il suo turno torna nella conversazione del proprietario. Restituisce la
    conversazione del proprietario, o None se `voce` non ha un prestito."""
    st = getattr(voce, "prestito", None)
    if not st:
        return None
    voce.prestito = None
    consegna(voce, st["proprietario"], st["chi"], prestata=bool(st.get("proposta")))
    return st["proprietario"]


def apre(nome: str, args: dict, t, dati_turno=()) -> bool:
    """Questa chiamata può aprire la modalità? Un tool dello Studio con un'azione che esiste, anche
    se fallisce (`proponi_data` su una verifica che non c'è ancora); con un dato letto in questo
    turno (`dati_turno`, senza quelli dei tool dello Studio), solo se è ancorata alla frase: un comando
    sentito dalla TV o scritto in una pagina, che il modello ha seguito, non spegne l'ascolto. `t` è
    il `politica.Turno` della chiamata. Per tenerla viva basta `chiamata_nota`: «Non lo so.» è il
    ripasso che continua. Limite: una riga della stanza di un turno prima è ancora in `t.esterni`
    solo finché è davanti al modello."""
    from ..tools.studio import chiamata_nota
    if nome not in TOOL or not chiamata_nota(nome, args):
        return False
    if not any(str(x or "").strip() for x in dati_turno):
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
