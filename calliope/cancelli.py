"""
Il giro a due cancelli per un minore che forse è in pericolo (09/10/2026, decisione di Dario).

Caso vero sulla DGX dell'08/10 (22:23–22:25, telefono in un locale rumoroso): un amico adulto
ospite, voce non registrata, prende 0,433 e 0,470 sul profilo del ragazzo (incerta: vale il
ragazzo, il profilo più protetto); una sua frase di 0,6 s (probabilmente un saluto) diventa
«pericolo» per il rilevatore; risposta con Telefono Azzurro e 112 e avviso «sicurezza» al
tutore. Il ragazzo non c'era.

«Un minore venga prima rassicurato, poi si cerca di capire se il problema è reale; solo
superato il secondo cancello si manda la notifica.» Con prudenza: un falso negativo su un
minore in pericolo è peggio di un falso positivo.

- **Acuto** (il rilevatore dice che il segnale è esplicito: `Guardiano.gravita`; un giudizio
  guasto vale acuto): come prima, protezione e avviso urgente subito. Se la voce non era sicura
  l'avviso lo dice.
- **Da verificare** (una parola, un saluto, un modo di dire, manca il contesto): **cancello 1**,
  una frase che rassicura e chiede con delicatezza, adatta all'età, senza nominare l'allarme
  (`rassicura`); il segnale resta aperto su quel minore (e su quel satellite) per
  `minori_pericolo_attesa_s`.
- **Cancello 2**: la frase dopo dello stesso minore (o, se la voce non era sicura, di chi parla
  su quel satellite, ma mai di un adulto riconosciuto con sicurezza) va al rilevatore con il primo segnale (`Guardiano.verifica`). Conferma (o
  guasto) → protezione e avviso urgente con i due segnali; smentita → si risponde normalmente,
  niente avviso, ma il segnale conta per `minori_pericolo_finestra_s`: un secondo segnale
  dubbio in quella finestra vale confermato.
- **Silenzio**: nessuna risposta entro l'attesa → con `minori_pericolo_silenzio: avvisa` un
  avviso **non urgente** «da verificare, segnale debole» (scelta prudente: il minore che dice
  una cosa preoccupante e poi tace non deve restare senza nessuno che lo sappia).

Il testo del primo segnale resta solo in memoria per il secondo giudizio: mai nel registro dei
turni, nel journal o negli avvisi (che dicono solo l'argomento). Ospiti e adulti: niente cambia.
"""

from __future__ import annotations

import dataclasses
import datetime
import threading
import time

from . import guardiano as guardia
from . import minori

CONFERMATO, DA_VERIFICARE = "confermato", "da_verificare"

# Cancello 1: rassicura e chiede, per fascia d'età (mai «pericolo», «allarme», «avviso»)
RASSICURA = {
    "piccoli": "Sono qui con te. Se c'è qualcosa che ti fa paura o ti fa stare male, puoi "
               "dirmelo. Va tutto bene?",
    "bambini": "Sono qui con te. Se c'è qualcosa che ti preoccupa o ti fa stare male, puoi "
               "dirmelo. Va tutto bene?",
    "ragazzi": "Ehi, se c'è qualcosa che ti preoccupa puoi parlarmene, senza fretta. Va tutto "
               "bene?",
    "adolescenti": "Ehi, se c'è qualcosa che ti pesa puoi parlarmene, quando vuoi. Va tutto "
                   "bene?",
}


def rassicura(prof) -> str:
    return RASSICURA.get(minori.fascia(prof) or "", RASSICURA["bambini"])


def argomento(categorie) -> str:
    return next((guardia.ARGOMENTI[c] for c in (categorie or ()) if c in guardia.ARGOMENTI),
                "ha detto una cosa che mi preoccupa")


def testo_avviso(nome: str, categorie, livello: str, motivo: str, voce_incerta: bool,
                 categorie_prima=None) -> str:
    """L'avviso ai tutori: livello, argomento (mai le parole del minore), cosa ha fatto
    Calliope. Con lo stesso minore, argomento e motivo il testo è uguale (l'avviso ripetuto
    entro `minori_avviso_ripetuto_s` si riconosce dal testo)."""
    arg = argomento(categorie)
    if livello == DA_VERIFICARE:
        out = (f"Da verificare, segnale debole: {nome} {arg}, ma in modo poco chiaro. Gli ho "
               f"chiesto con delicatezza se andava tutto bene e non ha risposto. Quando puoi, "
               f"chiedigli con calma come sta.")
    else:
        if motivo == "secondo_cancello":
            come = ("Prima mi ha detto una cosa poco chiara; gli ho chiesto se andava tutto bene "
                    "e la risposta ha confermato che qualcosa non va.")
        elif motivo == "secondo_segnale":
            come = (f"È il secondo segnale in poco tempo: anche poco prima {nome} "
                    f"{argomento(categorie_prima)}, in modo meno chiaro.")
        else:
            come = ""
        out = (f"Segnale confermato: {nome} {arg}. " + (come + " " if come else "")
               + "Gli ho detto di parlarne con un adulto e gli ho dato il numero del Telefono "
                 "Azzurro. Parlagli appena puoi, con calma.")
    if voce_incerta:
        out += " Attenzione: la voce non era sicura, potrebbe non essere stato lui."
    return out


@dataclasses.dataclass
class Segnale:
    """Un segnale di pericolo da verificare. `testo` resta solo in memoria (secondo giudizio)."""
    persona_id: str
    nome: str
    testo: str
    categorie: tuple
    voce_incerta: bool
    corsia: str | None
    ora: float                                   # monotonic
    aperto: bool = True
    esito: str | None = None                     # "smentita" | "conferma" | "silenzio"
    timer: object = None


class Cancelli:
    """I segnali da verificare, condivisi da tutte le corsie (un minore può cambiare stanza)."""

    def __init__(self, cfg, log=print, avvisi=None, registra=None, orologio=time.monotonic):
        self.cfg = cfg
        self.log = log
        self._avvisi = avvisi                    # None = minori.avvisi()
        self.registra = registra                 # turns.write (registro dei turni) o None
        self.orologio = orologio
        self._lock = threading.Lock()
        self.segnali: list[Segnale] = []

    # ── configurazione ──
    @property
    def attivo(self) -> bool:
        return bool(getattr(self.cfg, "minori_pericolo_verifica", True))

    def _attesa(self) -> float:
        return float(getattr(self.cfg, "minori_pericolo_attesa_s", 300.0) or 0.0)

    def _finestra(self) -> float:
        return float(getattr(self.cfg, "minori_pericolo_finestra_s", 1800.0) or 0.0)

    # ── stato ──
    def _pulisci(self, ora: float):
        keep = max(self._finestra(), self._attesa())
        self.segnali = [s for s in self.segnali if s.aperto or ora - s.ora <= keep]

    def apri(self, prof, testo: str, categorie, voce_incerta: bool, corsia) -> Segnale:
        """Cancello 1 superato con un segnale da verificare: resta aperto fino alla risposta o
        a `minori_pericolo_attesa_s` (poi `scaduto`)."""
        ora = self.orologio()
        s = Segnale(prof.id, prof.name, str(testo or ""), tuple(categorie or ()),
                    bool(voce_incerta), corsia, ora)
        with self._lock:
            self._pulisci(ora)
            self.segnali.append(s)
        attesa = self._attesa()
        if attesa > 0:
            s.timer = threading.Timer(attesa, self.scaduto, args=(s,))
            s.timer.daemon = True
            s.timer.start()
        return s

    def aperto_per(self, persona_id: str | None, corsia) -> Segnale | None:
        """Il segnale aperto a cui risponde questa frase: dello stesso minore, oppure (voce non
        sicura al primo segnale) di chi parla su quel satellite senza essere un adulto
        riconosciuto con sicurezza (chi chiama passa `corsia` None)."""
        ora = self.orologio()
        with self._lock:
            for s in reversed(self.segnali):
                attesa = self._attesa()
                if not s.aperto or (attesa > 0 and ora - s.ora > attesa):
                    continue
                if (persona_id and s.persona_id == persona_id) or (
                        s.voce_incerta and corsia is not None and s.corsia == corsia):
                    return s
        return None

    def recente(self, persona_id: str | None) -> Segnale | None:
        """Un altro segnale dubbio di questo minore entro `minori_pericolo_finestra_s` (aperto,
        smentito o rimasto senza risposta): un secondo segnale vale confermato."""
        if not persona_id:
            return None
        ora = self.orologio()
        with self._lock:
            for s in reversed(self.segnali):
                if s.persona_id == persona_id and ora - s.ora <= self._finestra():
                    return s
        return None

    def chiudi(self, s: Segnale, esito: str):
        with self._lock:
            s.aperto, s.esito = False, esito
        if s.timer is not None:
            s.timer.cancel()

    def scaduto(self, s: Segnale) -> bool:
        """Nessuna risposta entro l'attesa (il timer, o una prova): con
        `minori_pericolo_silenzio: avvisa` l'avviso non urgente «da verificare». True se
        l'avviso è partito."""
        with self._lock:
            if not s.aperto:
                return False
            s.aperto, s.esito = False, "silenzio"
        avvisa = str(getattr(self.cfg, "minori_pericolo_silenzio", "avvisa")) == "avvisa"
        self.log(f"   [MINORI] segnale da verificare per {s.nome} senza risposta: "
                 + ("avviso non urgente ai tutori" if avvisa else "nessun avviso"))
        if self.registra is not None:
            try:
                self.registra({"inizio": datetime.datetime.now().isoformat(timespec="seconds"),
                               "esito": "pericolo_silenzio", "regole": ["pericolo_silenzio"],
                               "voce": {"nome": s.nome},
                               "pericolo": {"livello": DA_VERIFICARE, "cancello": 2,
                                            "esito": "silenzio", "avviso": avvisa,
                                            "voce_incerta": s.voce_incerta}})
            except Exception:  # noqa: BLE001 — il registro non ferma l'avviso
                pass
        if not avvisa:
            return False
        return self.avvisa(s.persona_id, s.categorie, DA_VERIFICARE, "silenzio",
                           s.voce_incerta, urgente=False) is not None

    def avvisa(self, minore, categorie, livello: str, motivo: str,
               voce_incerta: bool, urgente: bool = True, categorie_prima=None,
               registry=None) -> int | None:
        """L'avviso ai tutori del minore (il profilo o il suo id; tipo «sicurezza»). Il numero
        di tutori, -1 se è lo stesso avviso ripetuto entro `minori_avviso_ripetuto_s`, None se
        non è partito."""
        av = self._avvisi if self._avvisi is not None else minori.avvisi()
        if av is None or minore is None:
            return None
        reg = registry or getattr(av, "registry", None)
        prof = minore if getattr(minore, "id", None) else None
        if prof is None and reg is not None:
            prof = next((u for u in getattr(reg, "users", {}).values()
                         if getattr(u, "id", None) == minore), None)
        if prof is None:
            return None
        try:
            return av.manda(prof, "sicurezza",
                            testo_avviso(prof.name, categorie, livello, motivo, voce_incerta,
                                         categorie_prima),
                            urgente=urgente, registry=reg,
                            non_ripetere_s=float(getattr(self.cfg, "minori_avviso_ripetuto_s",
                                                         0) or 0))
        except Exception as e:  # noqa: BLE001
            self.log(f"   [MINORI] avviso non mandato: {type(e).__name__}: {e}")
            return None
