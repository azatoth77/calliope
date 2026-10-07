"""
Una conversazione per persona e più satelliti che ascoltano insieme (06/10/2026, fase 3 del
progetto «Contesto di Calliope», decisioni di Dario del 05/10; rapporto
docs/ricerche/2026-10-06-conversazione-persona.md).

Fino al 05/10 c'era una conversazione per tutta la casa e un satellite **attivo** alla
volta: il telefono «prendeva» il posto del portatile, e una persona che cambiava stanza
ricominciava da capo, mentre due persone in due stanze si toglievano la parola. Qui:

- **Corsie.** Ogni satellite collegato ha la sua *corsia*: un thread con il ciclo di
  main.py (`giro`), il suo ascolto, la sua voce in uscita, il suo `SpeakerContext` (chi
  parla, voce sicura, frase di sfida, finestra di ascolto) e il suo Brain. Con l'audio di
  questo computer la corsia è una sola, quella del thread principale. Il ciclo è un oggetto
  `ciclo.Ciclo` per corsia (dal 06/10, P8: prima `giro` era copiato con le sue chiusure). La corsia del thread
  si legge con `corrente()`: i pezzi condivisi che dipendono dal satellite (la stanza per
  gli schermi, l'origine della richiesta, il PC da comandare) la chiedono a lei.
- **Conversazioni per persona** (`RegistroConversazioni`). Una persona riconosciuta dalla
  voce sopra la soglia normale apre o riprende la **sua** conversazione da qualunque
  satellite (comincio al portatile, continuo dal telefono): storia, azione in sospeso,
  riferimenti, foto e allegati viaggiano con lei. Le frasi brevi e la zona grigia
  continuano solo la conversazione di chi ha parlato **su quel satellite**, nella sua
  finestra di ascolto; ospiti e voci incerte hanno una conversazione anonima per satellite,
  mai condivisa; lo scritto da uno schermo personale continua la conversazione della
  persona solo se c'è (cominciata a voce: schermi/conversazione.py).
- **Risposte in parallelo** (`Varco`): fino a `conversazioni_parallele` risposte del
  modello insieme; oltre, una frase già sintetizzata («Sto rispondendo anche a un'altra
  persona: dammi un attimo.») e la coda in ordine d'arrivo. Una risposta cominciata non si
  interrompe.
- **Annunci e frasi scritte** (`Smistatore`): un timer, un documento, un lavoro finito si
  annunciano dalla corsia del satellite dove la persona aveva chiesto (calliope/rispondi.py);
  una frase scritta dallo schermo di un satellite (il telefono) va alla sua corsia.

La stessa frase sentita da due satelliti nella stessa stanza (portatile e telefono sulla
scrivania) avrebbe due risposte: la seconda corsia la scarta se un'altra ha appena preso una
frase quasi uguale (`conversazione_doppione_s`, regola `doppione_altro_satellite`).

Solo libreria standard.
"""
from __future__ import annotations

import collections
import difflib
import itertools
import re
import threading
import time

from .conversazione import UNSET, Conversazione

_qui = threading.local()

# La frase quando le risposte in corso sono già `conversazioni_parallele`
FRASE_CODA = "Sto rispondendo anche a un'altra persona: dammi un attimo."


def corrente():
    """La corsia del thread che chiama (None fuori da una corsia: thread degli schermi, dei
    lavori, delle prove)."""
    return getattr(_qui, "corsia", None)


def entra(corsia):
    """Il thread corrente è la corsia `corsia` (all'inizio del suo ciclo)."""
    _qui.corsia = corsia


class in_corsia:
    """Per un pezzo di codice che gira in un altro thread per conto di una corsia (la voce
    che comincia a parlare, nel thread di riproduzione)."""

    def __init__(self, corsia):
        self.corsia = corsia

    def __enter__(self):
        self.prima = corrente()
        _qui.corsia = self.corsia
        return self.corsia

    def __exit__(self, *exc):
        _qui.corsia = self.prima
        return False


def per_corsia(predefinito, nome: str):
    """L'oggetto `nome` della corsia corrente (speaker, listener…), o `predefinito`."""
    c = corrente()
    v = getattr(c, nome, None) if c is not None else None
    return v if v is not None else predefinito


# ───────────────────────────── corsia ─────────────────────────────
class Corsia:
    """Un satellite (o l'audio di questo computer) con il suo ciclo e i suoi oggetti."""

    def __init__(self, chiave: str, satellite_id=None, nome: str = "", registro=None,
                 varco=None):
        self.chiave = chiave                 # "locale" o "sat:<id>"
        self.satellite_id = satellite_id
        self.nome = nome or chiave
        self.registro = registro             # RegistroConversazioni
        self.varco = varco                   # Varco
        self.listener = self.speaker = self.speaker_ctx = self.brain = self.tool_ctx = None
        self.sveglia = threading.Event()     # annunci e frasi scritte per questa corsia
        self.conv: Conversazione | None = None    # la conversazione dell'ultimo turno qui
        self._in_uso: Conversazione | None = None
        self._nel_varco = False
        self.thread = None
        self.ciclo = None                    # il suo ciclo.Ciclo (main.py)
        self.ultimo_turno = 0.0

    @property
    def chiave_schermi(self):
        """La chiave della conversazione per lo scritto (schermi/conversazione.py): None con
        l'audio di questo computer (come prima), il satellite altrimenti."""
        return None if self.satellite_id is None else self.chiave

    # ── conversazione del turno ──
    def turno(self, brain, nome, how, in_session: bool, testo: str = "", rec=None,
              scritto=None, persona_id=None, impronta=None) -> bool:
        """Dopo il riconoscimento di chi parla: la conversazione del turno in `brain.conv`.
        False se la frase è un doppione di un'altra corsia (la si scarta)."""
        reg = self.registro
        if reg is None:
            return True
        self.ultimo_turno = time.monotonic()
        if (testo and scritto is None
                and reg.doppione(self.chiave, testo, impronta=impronta)):
            if rec is not None:
                rec.update(esito="doppione", satellite=self.nome)
                rec.setdefault("regole", []).append("doppione_altro_satellite")
            print(f"   [CORSIE] {self.nome}: la stessa frase l'ha appena presa un altro "
                  f"satellite: la lascio a lui", flush=True)
            return False
        conv, come = reg.scegli(self, persona_id, how, in_session)
        # Una proposta ancora valida di chi parlava prima su questo satellite (07/10): se ora
        # risponde un'altra voce, il turno lo sa (brain.SOSPESO_ALTRUI_MSG)
        vecchia = self.conv
        try:
            from .brain import proposta_altrui
            brain.sospeso_altrui = (proposta_altrui(getattr(vecchia, "pending", None),
                                                    persona_id)
                                    if vecchia is not None and vecchia is not conv else None)
        except Exception:  # noqa: BLE001 — un dato del turno non ferma la voce
            pass
        self.fine_turno()                    # una conversazione per volta
        conv = reg.occupa(conv, self)
        self._in_uso = conv
        self.conv = conv
        try:
            brain.conv = conv
        except AttributeError:
            pass
        try:
            reg.pulisci(brain)
        except Exception as e:  # noqa: BLE001 — la pulizia non ferma la voce
            print(f"   [CORSIE] pulizia delle conversazioni: {type(e).__name__}: {e}",
                  flush=True)
        if rec is not None:
            rec["conversazione"] = {"tipo": "ospite" if conv.chiave.startswith("ospite:")
                                    else "persona", "come": come, "n": reg.numero(conv)}
            if self.satellite_id is not None:
                rec["satellite"] = self.nome
        return True

    def annuncio_per(self, brain, persona_id):
        """Un annuncio per una persona (documento pronto, lavoro finito): entra nella sua
        conversazione, così il «sì, aprilo» detto dopo la ritrova (anche da un altro
        satellite, se lo dice con la voce riconosciuta)."""
        reg = self.registro
        if reg is None or not persona_id:
            return
        conv = reg.di_persona(persona_id, crea=True)
        if conv is None or conv is self._in_uso:
            return
        self.fine_turno()
        conv = reg.occupa(conv, self)
        self._in_uso = self.conv = conv
        try:
            brain.conv = conv
        except AttributeError:
            pass

    def fine_turno(self):
        """Il turno è finito (in cima al giro dopo): la conversazione torna libera per le
        altre corsie, e il varco si chiude se una risposta è uscita male."""
        if self._in_uso is not None and self.registro is not None:
            self.registro.libera(self._in_uso, self)
        self._in_uso = None
        self.esci_llm()

    # ── risposte del modello ──
    def entra_llm(self, attesa=None) -> float:
        """Prima di chiedere una risposta al modello: aspetta il suo posto (attesa(): la
        frase della coda, una volta). Restituisce i secondi aspettati."""
        if self.varco is None or self._nel_varco:
            return 0.0
        s = self.varco.entra(attesa)
        self._nel_varco = True
        return s

    def esci_llm(self):
        if self.varco is not None and self._nel_varco:
            self._nel_varco = False
            self.varco.esci()


# ───────────────────────────── conversazioni ─────────────────────────────
def _norm(testo: str) -> str:
    return re.sub(r"[^\w]+", " ", (testo or "").lower()).strip()


class RegistroConversazioni:
    """Le conversazioni in corso, per chiave: «persona:<id del profilo>» (una per persona,
    da qualunque satellite) e «ospite:<corsia>» (una per satellite, mai condivisa)."""

    PULIZIA_S = 30.0

    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self._cond = threading.Condition(threading.RLock())
        self._conv: dict[str, Conversazione] = {}
        self._numeri: dict[str, int] = {}          # ultimo turn_number di una chiave chiusa
        self._uso: dict[int, tuple] = {}           # id(conv) → (corsia, da quando)
        self._ids: dict[int, int] = {}             # id(conv) → numero breve (registro)
        self._contatore = itertools.count(1)
        self._recenti: collections.deque = collections.deque(maxlen=32)
        self._pulita = time.monotonic()

    @staticmethod
    def chiave_persona(persona_id) -> str:
        return f"persona:{persona_id}"

    @staticmethod
    def chiave_ospite(corsia_chiave: str) -> str:
        return f"ospite:{corsia_chiave}"

    def doppio_s(self) -> float:
        return float(getattr(self.cfg, "conversazione_doppione_s", 2.0) or 0.0)

    # ── scelta ──
    def _nuova(self, chiave: str) -> Conversazione:
        c = Conversazione(chiave)
        c.turn_number = self._numeri.get(chiave, 0)
        self._conv[chiave] = c
        return c

    def _di(self, chiave: str, crea: bool = True) -> Conversazione | None:
        c = self._conv.get(chiave)
        if c is None and crea:
            c = self._nuova(chiave)
        return c

    def scegli(self, corsia, persona_id, how, in_session: bool) -> tuple[Conversazione, str]:
        """(conversazione, come) per un turno della `corsia`. Regole (decise da Dario il
        05/10):
          - voce sopra la soglia normale («voce») con un profilo: la conversazione della
            persona, nuova o ripresa da un altro satellite;
          - frase breve o zona grigia: continua la conversazione di chi ha parlato su
            **questo** satellite nella sua finestra di ascolto; altrimenti anonima;
          - scritto da uno schermo personale («schermo»): la conversazione della persona se
            c'è, altrimenti anonima;
          - ospite o voce incerta: la conversazione anonima di questo satellite."""
        with self._cond:
            if persona_id and how == "voce":
                chiave = self.chiave_persona(persona_id)
                nuova = chiave not in self._conv
                c = self._di(chiave)
                if corsia.conv is not c and not nuova and c.history:
                    return c, "ripresa"
                return c, "persona"
            if persona_id and how in ("breve", "conversazione"):
                chiave = self.chiave_persona(persona_id)
                c = corsia.conv
                if in_session and c is not None and c.chiave == chiave \
                        and self._conv.get(chiave) is c:
                    return c, "continua"
            elif persona_id and how == "schermo":
                c = self._conv.get(self.chiave_persona(persona_id))
                if c is not None:
                    return c, "schermo"
            return self._di(self.chiave_ospite(corsia.chiave)), "anonima"

    def di_persona(self, persona_id, crea: bool = False) -> Conversazione | None:
        """La conversazione in corso di una persona (annunci per lei)."""
        if not persona_id:
            return None
        with self._cond:
            return self._di(self.chiave_persona(persona_id), crea)

    def numero(self, conv) -> int:
        """Un numero breve e stabile della conversazione (registro dei turni)."""
        with self._cond:
            n = self._ids.get(id(conv))
            if n is None:
                n = self._ids[id(conv)] = next(self._contatore)
            return n

    # ── una corsia alla volta ──
    def occupa(self, conv: Conversazione, corsia, attesa_max: float = 60.0) -> Conversazione:
        """La conversazione è di questa corsia per il turno. Se la sta usando un'altra (la
        stessa persona che parla a due satelliti di seguito) si aspetta la fine di quel
        turno; dopo `attesa_max` si va avanti comunque (un turno rimasto appeso non blocca)."""
        fine = time.monotonic() + attesa_max
        with self._cond:
            while True:
                u = self._uso.get(id(conv))
                if u is None or u[0] is corsia or time.monotonic() > fine:
                    break
                self._cond.wait(min(0.5, max(0.01, fine - time.monotonic())))
            # La conversazione può essere stata chiusa e sostituita mentre si aspettava
            corrente_ = self._conv.get(conv.chiave)
            if corrente_ is not None and corrente_ is not conv:
                conv = corrente_
            self._uso[id(conv)] = (corsia, time.monotonic())
            return conv

    def libera(self, conv: Conversazione, corsia):
        with self._cond:
            u = self._uso.get(id(conv))
            if u is not None and u[0] is corsia:
                del self._uso[id(conv)]
            # anche quella che l'ha sostituita durante il turno («esci», scaduta)
            nuova = self._conv.get(conv.chiave)
            if nuova is not None and nuova is not conv:
                u = self._uso.get(id(nuova))
                if u is not None and u[0] is corsia:
                    del self._uso[id(nuova)]
            self._cond.notify_all()

    def sostituita(self, vecchia: Conversazione, nuova: Conversazione):
        """Brain.end_conversation: al posto di `vecchia` c'è `nuova` (stessa chiave)."""
        with self._cond:
            chiave = vecchia.chiave
            self._numeri[chiave] = max(self._numeri.get(chiave, 0),
                                       getattr(vecchia, "turn_number", 0))
            if self._conv.get(chiave) is vecchia or chiave not in self._conv:
                self._conv[chiave] = nuova
            u = self._uso.pop(id(vecchia), None)
            if u is not None:
                self._uso[id(nuova)] = u
            self._cond.notify_all()

    # ── doppioni ──
    # Due microfoni che sentono la stessa persona: impronte CAM++ della stessa frase almeno
    # così simili (la stessa voce sopra soglia è 0,48; due persone diverse 0,3)
    DOPPIONE_VOCE = 0.6

    def doppione(self, corsia_chiave: str, testo: str, ora: float | None = None,
                 impronta=None) -> bool:
        """La stessa frase appena presa da un'altra corsia (due satelliti nella stessa
        stanza): testo quasi uguale e, se ci sono le impronte, la stessa voce (due persone
        diverse che chiedono la stessa cosa da due stanze non sono un doppione). Se no, la
        frase si ricorda per le altre."""
        finestra = self.doppio_s()
        t = _norm(testo)
        if not t:
            return False
        ora = time.monotonic() if ora is None else ora
        with self._cond:
            for quando, chi, altro, emb in self._recenti:
                if chi == corsia_chiave or ora - quando > finestra:
                    continue
                if not (t == altro or difflib.SequenceMatcher(None, t, altro).ratio() >= 0.8):
                    continue
                if impronta is not None and emb is not None:
                    try:
                        if float(sum(a * b for a, b in zip(impronta, emb)))                                 < self.DOPPIONE_VOCE:
                            continue             # voci diverse: due persone
                    except (TypeError, ValueError):
                        pass
                return True
            if finestra > 0:
                self._recenti.append((ora, corsia_chiave, t, impronta))
            return False

    # ── fine e ripresa ──
    def pulisci(self, brain, ora: float | None = None, forza: bool = False) -> int:
        """Chiude (archivio e riassunto di chiusura, in secondo piano) le conversazioni
        ferme da più di `storia_inattiva_s` e non in uso: chi non torna non lascia la
        conversazione aperta per sempre. Al più ogni PULIZIA_S. Quante ne ha chiuse."""
        ora = time.monotonic() if ora is None else ora
        idle = float(getattr(self.cfg, "storia_inattiva_s", 0) or 0)
        if idle <= 0 or (not forza and ora - self._pulita < self.PULIZIA_S):
            return 0
        self._pulita = ora
        chiudi = getattr(brain, "chiudi_conversazione", None)
        if chiudi is None:
            return 0
        with self._cond:
            ferme = [c for c in self._conv.values()
                     if id(c) not in self._uso and c.last_turn_at is not None
                     and ora - c.last_turn_at > idle and not c.vuota()]
            for c in ferme:                  # nessuna corsia la prende mentre si chiude
                self._uso[id(c)] = ("pulizia", ora)
        try:
            for c in ferme:
                chiudi(c, "conversazione_scaduta")
        finally:
            with self._cond:
                for c in ferme:
                    for x in (c, self._conv.get(c.chiave)):
                        if x is not None and (self._uso.get(id(x)) or (None,))[0] == "pulizia":
                            del self._uso[id(x)]
                self._cond.notify_all()
        return len(ferme)

    def riprendi(self, archivio, log=print) -> int:
        """All'avvio: le conversazioni salvate prima del riavvio e non scadute, una per
        chiave. Quella della casa di prima del 06/10 («casa») va alla sua persona."""
        if archivio is None:
            return 0
        scade = float(getattr(self.cfg, "storia_inattiva_s", 0) or 0)
        n = 0
        try:
            chiavi = archivio.chiavi_correnti()
        except Exception:  # noqa: BLE001
            return 0
        for chiave in chiavi:
            try:
                c = Conversazione.importa(archivio.leggi_corrente(chiave), scade)
            except Exception:  # noqa: BLE001
                c = None
            if c is None or not (c.history or c.riassunto):
                continue
            if not (chiave.startswith("persona:") or chiave.startswith("ospite:")):
                if c.owner is UNSET or not c.owner:
                    continue                 # la vecchia conversazione di un ospite: no
                chiave = self.chiave_persona(c.owner)
                c.chiave = chiave
            with self._cond:
                if chiave in self._conv:
                    continue
                self._conv[chiave] = c
            n += 1
        if n:
            log(f"[STORIA] Riprese {n} conversazioni di prima del riavvio", flush=True)
        return n

    def tutte(self) -> list[Conversazione]:
        with self._cond:
            return list(self._conv.values())


# ───────────────────────────── risposte in parallelo ─────────────────────────────
class Varco:
    """Al più `limite` risposte del modello insieme, le altre in coda in ordine d'arrivo.
    `limite` 0: nessun limite."""

    def __init__(self, limite: int):
        self.limite = max(0, int(limite or 0))
        self._cond = threading.Condition()
        self._attivi = 0
        self._coda: collections.deque = collections.deque()
        self.attese = 0                       # risposte che hanno aspettato (misure)
        self.massimo = 0                      # massimo di risposte insieme visto

    def entra(self, attesa=None) -> float:
        t0 = time.monotonic()
        with self._cond:
            if self.limite <= 0 or (self._attivi < self.limite and not self._coda):
                self._attivi += 1
                self.massimo = max(self.massimo, self._attivi)
                return 0.0
            biglietto = object()
            self._coda.append(biglietto)
            self.attese += 1
        if attesa is not None:
            try:
                attesa()
            except Exception:  # noqa: BLE001 — la frase d'attesa non ferma la risposta
                pass
        with self._cond:
            while not (self._coda[0] is biglietto and self._attivi < self.limite):
                self._cond.wait()
            self._coda.popleft()
            self._attivi += 1
            self.massimo = max(self.massimo, self._attivi)
            self._cond.notify_all()
        return time.monotonic() - t0

    def esci(self):
        with self._cond:
            self._attivi = max(0, self._attivi - 1)
            self._cond.notify_all()

    @property
    def attivi(self) -> int:
        with self._cond:
            return self._attivi


def condivisa(occupa, libera):
    """Una coppia «voce occupata / voce libera» pensata per un microfono solo (l'arbitro degli
    agenti, la compressione in secondo piano) usata da più corsie: la voce è libera solo
    quando nessuna corsia la tiene. Restituisce le due funzioni da mettere al loro posto."""
    lock = threading.Lock()
    chi: set = set()

    def occupata(*a, **k):
        with lock:
            chi.add(threading.get_ident())
        return occupa(*a, **k)

    def liberata(*a, **k):
        with lock:
            chi.discard(threading.get_ident())
            vuota = not chi
        if vuota:
            return libera(*a, **k)
        return None
    return occupata, liberata


# ───────────────────────────── annunci e scritti ─────────────────────────────
class Smistatore:
    """Gli annunci (timer, documenti, lavori, installazioni, estensioni) e le frasi scritte
    dagli schermi, ognuno alla corsia giusta. Le code dei servizi restano quelle di sempre:
    lo smistatore le svuota (`raccogli`) e ogni corsia prende i suoi (`vista`).

    `fonti`: nome → (coda, destinazione), dove destinazione(item) è la chiave di una corsia o
    None (una qualunque). Un item per una corsia che non c'è o il cui satellite non è
    collegato va alla prima corsia che passa."""

    def __init__(self, fonti: dict, disponibile=None):
        self.fonti = fonti
        self.disponibile = disponibile or (lambda chiave: True)
        self._lock = threading.Lock()
        self._attesa: dict[str, list] = {nome: [] for nome in fonti}
        self.corsie: dict[str, Corsia] = {}

    def raccogli(self) -> set:
        """Svuota le code dei servizi; le chiavi delle corsie che hanno qualcosa (None:
        per tutte)."""
        import queue as _q
        chi: set = set()
        with self._lock:
            for nome, (coda, dest) in self.fonti.items():
                if coda is None:
                    continue
                while True:
                    try:
                        item = coda.get_nowait()
                    except _q.Empty:
                        break
                    try:
                        d = dest(item) if dest is not None else None
                    except Exception:  # noqa: BLE001
                        d = None
                    self._attesa[nome].append((item, d))
            for lista in self._attesa.values():
                for _, d in lista:
                    chi.add(d if d in self.corsie and self.disponibile(d) else None)
        return chi

    def sveglia(self):
        """Raccoglie e sveglia le corsie che hanno qualcosa (tutte, per ciò che non ha una
        corsia sua)."""
        chi = self.raccogli()
        for k, c in list(self.corsie.items()):
            if None in chi or k in chi:
                c.sveglia.set()

    def _indice(self, nome: str, corsia_chiave: str) -> int | None:
        lista = self._attesa.get(nome) or []
        for i, (_, d) in enumerate(lista):
            if d == corsia_chiave or d is None or d not in self.corsie \
                    or not self.disponibile(d):
                return i
        return None

    def prendi(self, nome: str, corsia_chiave: str):
        self.raccogli()
        with self._lock:
            i = self._indice(nome, corsia_chiave)
            return None if i is None else self._attesa[nome].pop(i)[0]

    def vuota(self, nome: str, corsia_chiave: str) -> bool:
        self.raccogli()
        with self._lock:
            return self._indice(nome, corsia_chiave) is None

    def rimetti(self, nome: str, item, corsia_chiave: str):
        """Un annuncio rinviato (main.rinvia) torna in attesa per la stessa corsia."""
        with self._lock:
            self._attesa[nome].append((item, corsia_chiave))

    def vista(self, nome: str, corsia) -> "VistaCoda | None":
        if nome not in self.fonti or self.fonti[nome][0] is None:
            return None
        return VistaCoda(self, nome, corsia.chiave)


class VistaCoda:
    """Una coda di un servizio vista da una corsia: solo i suoi item (stessa interfaccia di
    queue.Queue per ciò che usa main.py)."""

    def __init__(self, smistatore: Smistatore, nome: str, chiave: str):
        self.s, self.nome, self.chiave = smistatore, nome, chiave

    def empty(self) -> bool:
        return self.s.vuota(self.nome, self.chiave)

    def vuoto(self) -> bool:                 # come schermi.moduli.Ingresso
        return self.empty()

    def get_nowait(self):
        import queue as _q
        item = self.s.prendi(self.nome, self.chiave)
        if item is None:
            raise _q.Empty
        return item

    def prendi(self):                        # come schermi.moduli.Ingresso
        return self.s.prendi(self.nome, self.chiave)

    def put(self, item):
        self.s.rimetti(self.nome, item, self.chiave)


# ───────────────────────────── trascrizione condivisa ─────────────────────────────
class STTCondiviso:
    """Il trascrittore usato da più corsie: una trascrizione alla volta (faster-whisper sulla
    GPU, whisper.cpp che comunque le mette in fila), e la confidenza dell'ultima frase per
    corsia."""

    def __init__(self, stt):
        self.__dict__["_stt"] = stt
        self.__dict__["_lock"] = threading.Lock()
        self.__dict__["_qui"] = threading.local()

    def transcribe(self, audio, *a, **k):
        with self._lock:
            testo = self._stt.transcribe(audio, *a, **k)
            self._qui.conf = getattr(self._stt, "ultima_confidenza", None)
        return testo

    @property
    def ultima_confidenza(self):
        return getattr(self._qui, "conf", None)

    def __getattr__(self, nome):
        return getattr(self._stt, nome)

    def __setattr__(self, nome, valore):
        setattr(self._stt, nome, valore)
