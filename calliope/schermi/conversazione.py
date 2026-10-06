"""
Scrivere solo durante una conversazione (05/10/2026, richiesta di Dario).

Prima lo scritto da uno schermo personale valeva come il suo proprietario (al più familiare)
anche se nessuno aveva parlato: chi aveva in mano il telefono o il tablet di Dario poteva
fare richieste a suo nome. Ora la casella «Scrivi», i moduli (e domani le immagini) valgono
solo mentre c'è una **conversazione attiva**, cominciata a voce. È un vincolo di permesso,
non una regola sul significato del testo (principio 10): regola `scritto_senza_conversazione`
nel registro dei turni.

Conversazione attiva per uno schermo **personale**:
  - il proprietario dello schermo ha parlato a Calliope ed è stato **riconosciuto dalla voce**
    (`identified_by == "voce"`: non la frase breve, non la zona grigia, non lo scritto);
  - da allora nessun altro ha parlato (un'altra persona, o una voce non riconosciuta, chiude
    la conversazione, come `Brain._check_conversation`), e non ha detto «esci» (si
    addormenta: `chiudi`);
  - l'ultima frase riconosciuta dalla sua voce è di meno di `storia_inattiva_s` secondi fa.
    Le frasi brevi, quelle della zona grigia e quelle scritte **non** allungano il tempo:
    lo scritto non si tiene vivo da solo. La finestra di follow-up (`followup_s`, 8 s) non
    conta: per scrivere un IBAN serve più tempo, e la storia del modello resta comunque.

Da **quale satellite**: da uno qualunque. I moduli vanno a tutti gli schermi personali della
persona (moduli.py): il caso tipico è parlare al portatile e scrivere la partita IVA sul
telefono, che chiedere la voce dal satellite di quello schermo renderebbe impossibile (e uno
schermo senza audio non potrebbe mai scrivere). La condizione prova che il proprietario c'è e
sta parlando adesso; il rischio che resta (qualcuno con il suo telefono in un'altra stanza
mentre lui parla) dura al più `storia_inattiva_s` e finisce appena parla un altro.

Schermi **di stanza** con `schermi_scritto_stanza` (chi scrive vale come ospite): stessa
regola, con la stanza al posto della persona. Serve una conversazione a voce aperta **in
quella stanza** (di chiunque, anche di un ospite: lì l'identità non conta, conta che ci sia
qualcuno davanti), dal satellite della stanza o, con l'audio di questo computer, dalla stanza
di `schermi_stanza` (vuota: le pagine aperte su questo computer). Un tablet sempre acceso in
un corridoio non diventa una tastiera per chiunque sia in rete.

Fase 3 (una conversazione per satellite): la condizione è `scrittura_consentita(schermo,
conversazione, …)`, una funzione pura con la conversazione come argomento; `Conversazioni`
le tiene per chiave (oggi una sola, `None`: c'è una conversazione per tutta la casa, come in
Brain). Il punto da chiamare è `Schermi.scrittura_consentita(schermo)` (hub.py), usato dal
server per /api/scrivi, /api/modulo e da ogni ingresso nuovo dalle pagine.
"""

import threading
import time
from dataclasses import dataclass

from .archivio import norm_stanza

# Motivi del rifiuto (nel registro dei turni e alla pagina): niente nomi né dati
NESSUNA = "nessuna_conversazione"
SCADUTA = "scaduta"
ALTRA_PERSONA = "altra_persona"
ALTRA_STANZA = "altra_stanza"
REGOLA = "scritto_senza_conversazione"


@dataclass(frozen=True)
class Conversazione:
    """Una conversazione cominciata a voce. `persona` None: la voce non è stata riconosciuta
    (un ospite), vale solo per gli schermi di stanza."""
    persona: str | None              # UserProfile.id riconosciuto dalla voce
    voce_at: float                   # time.monotonic() dell'ultima frase che lo prova
    stanza: str | None = None        # stanza del microfono che l'ha sentita
    satellite: str | None = None     # id del satellite (None: audio di questo computer)
    locale: bool = False             # audio di questo computer, senza satelliti


def durata(cfg) -> float:
    """Quanto vale una conversazione dopo l'ultima frase riconosciuta dalla voce:
    `storia_inattiva_s` (300 s); se è spenta (0) comunque 300 s, perché lo scritto deve
    scadere."""
    d = float(getattr(cfg, "storia_inattiva_s", 300.0) or 0.0)
    return d if d > 0 else 300.0


def attiva(conv: Conversazione | None, ora: float, durata_s: float) -> bool:
    return conv is not None and ora - conv.voce_at <= durata_s


def stessa_stanza(schermo: dict, conv: Conversazione) -> bool:
    s = norm_stanza(schermo.get("stanza") or "")
    return bool(s and conv.stanza and norm_stanza(conv.stanza) == s)


def scrittura_consentita(schermo: dict, conv: Conversazione | None, *, ora: float,
                         durata_s: float, stanza_ok=None) -> tuple[bool, str]:
    """(True, "") se da `schermo` si può scrivere durante `conv`; altrimenti (False, motivo).
    Schermo personale: la conversazione è del suo proprietario. Schermo di stanza: la
    conversazione è in quella stanza (`stanza_ok(schermo, conv)`, predefinito
    `stessa_stanza`)."""
    if conv is None:
        return False, NESSUNA
    if not attiva(conv, ora, durata_s):
        return False, SCADUTA
    proprietario = schermo.get("proprietario")
    if proprietario:
        return (True, "") if conv.persona == proprietario else (False, ALTRA_PERSONA)
    ok = (stanza_ok or stessa_stanza)(schermo, conv)
    return (True, "") if ok else (False, ALTRA_STANZA)


class Conversazioni:
    """Le conversazioni cominciate a voce, per chiave (oggi una sola: `None`). Il ciclo
    principale le aggiorna a ogni frase rivolta a Calliope (`voce`) e le chiude con «esci»
    (`chiudi`); un thread avvisa (`on_cambio`) quando una scade, così le pagine si
    disattivano da sole."""

    def __init__(self, durata_s=lambda: 300.0, on_cambio=None):
        self._durata = durata_s
        self.on_cambio = on_cambio
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._conv: dict = {}
        self._thread = None

    def durata_s(self) -> float:
        try:
            return float(self._durata())
        except Exception:  # noqa: BLE001
            return 300.0

    def tutte(self) -> list[Conversazione]:
        with self._lock:
            return list(self._conv.values())

    def attive(self, ora: float | None = None) -> list[Conversazione]:
        ora = time.monotonic() if ora is None else ora
        d = self.durata_s()
        return [c for c in self.tutte() if attiva(c, ora, d)]

    def di(self, chiave=None) -> Conversazione | None:
        with self._lock:
            return self._conv.get(chiave)

    def voce(self, persona: str | None, modo: str | None, stanza: str | None = None,
             satellite: str | None = None, locale: bool = False, chiave=None,
             ora: float | None = None) -> Conversazione | None:
        """Una frase detta e rivolta a Calliope. `modo` è `SpeakerContext.identified_by`:
          - «voce» con un profilo: la conversazione è sua (nuova o rinnovata);
          - «breve», «conversazione», «schermo» della stessa persona: resta com'è, senza
            allungare il tempo (non è una prova della voce);
          - altrimenti (un ospite, una voce non riconosciuta, un'altra persona): una
            conversazione senza persona in quella stanza, che chiude quella di prima."""
        ora = time.monotonic() if ora is None else ora
        with self._lock:
            prima = self._conv.get(chiave)
            if modo == "voce" and persona:
                nuova = Conversazione(persona, ora, stanza, satellite, locale)
            elif modo in ("breve", "conversazione", "schermo") and persona \
                    and prima is not None and prima.persona == persona:
                return prima
            elif persona and modo in ("breve", "conversazione", "schermo"):
                nuova = None                 # chi non è provato dalla voce non apre nulla
            else:
                nuova = Conversazione(None, ora, stanza, satellite, locale)
            if nuova is None:
                self._conv.pop(chiave, None)
            else:
                self._conv[chiave] = nuova
            self._sveglia()
        self._avvisa()
        return nuova

    def chiudi(self, chiave=None) -> bool:
        """«Esci», «vai a dormire»: la conversazione finisce, lo scritto si spegne."""
        with self._lock:
            c = self._conv.pop(chiave, None)
        if c is not None:
            self._avvisa()
        return c is not None

    def _avvisa(self):
        if self.on_cambio is not None:
            try:
                self.on_cambio()
            except Exception as e:  # noqa: BLE001 — gli schermi non fermano la voce
                print(f"   [SCHERMI] stato dello scritto: {type(e).__name__}", flush=True)

    def _sveglia(self):
        """Con il lock: il thread delle scadenze ricalcola la prossima."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._scadenze, daemon=True,
                                            name="schermi-conversazione")
            self._thread.start()
        self._cond.notify_all()

    def _scadenze(self):
        avvisate: set = set()
        while True:
            with self._lock:
                d = self.durata_s()
                ora = time.monotonic()
                # Le conversazioni scadute ora (una volta sola per ciascuna)
                scadute = [c for c in self._conv.values()
                           if ora - c.voce_at > d and c not in avvisate]
                vive = [c.voce_at + d - ora for c in self._conv.values() if ora - c.voce_at <= d]
                avvisate &= set(self._conv.values())
                if not scadute:
                    self._cond.wait(min(vive) + 0.05 if vive else None)
                    continue
                avvisate.update(scadute)
            self._avvisa()
