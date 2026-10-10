"""
L'uscita unica verso la voce (10/10/2026, passo 2 del § 8 di
docs/ricerche/2026-10-10-registro-eventi.md, § 3.2).

Ogni frase che Calliope dice passa da qui: le risposte del modello frase per frase (lo stream di
Brain, `Ciclo._di_frase` e la ricerca promessa), le frasi pronte dei tool, gli atti del ciclo
(cortesia, annunci, registrazione della voce, «Sì?», protezione…), le frasi d'attesa, i segnali
e il saluto. Fuori da questo file e da `calliope/tts.py` nessuno chiama `say`, `say_cached`,
`chime`, `suono`, `suono_ascolto`, `sintetizza`, `start_turn` né aspetta la voce
(`prova_uscita_unica`, AST).

Una `Uscita` per voce (quindi per corsia: `per_voce`), intorno allo `Speaker` di oggi:

- `di(testo, atto, autore)`: il `detto_calliope` nasce qui, **all'invio**, in memoria (testo
  mandato a Piper prima della pronuncia, autore `contenuto | atto | esito`, atto dall'elenco
  chiuso `tipi.ATTI`, canale `voce | scritto | muta`, posizione fra le chiamate dei tool), poi la
  frase va al TTS. La voce non aspetta niente: nessun file, nessun database (§ 5, § 11.6).
- **Nessuna frase fuori turno** (correzione del quarto giro del 10/10, assorbita qui): un atto
  detto senza un turno della voce aperto, o in un turno fermato da un'interruzione, apre prima un
  turno nuovo (il satellite scarta le frasi di un turno non oltre l'ultimo fermato, e la voce di
  una corsia nuova sta al turno 0). Le parole di una risposta restano nel turno della risposta:
  interrotta, la voce le scarta come prima.
- `turno()`: un turno della voce nuovo; quello che si chiude dice all'osservatore (il registro
  in ombra, `Ombra.sente`) quali frasi si sono sentite per intero (`played`) e se c'è stata
  un'interruzione: è il `voce_fine`.
- `testo_scritto()`: la risposta scritta sugli schermi, dalle frasi della persona in corso (le
  stesse degli eventi), non più ricostruita dal ciclo.

Gli eventi entrano nel registro della conversazione a turno finito (`Ombra.chiudi_turno`), con
il `seq` dopo il `detto_persona` del turno: finché l'ombra scrive il turno a cose fatte (fino al
passo 3) l'ordine del registro lo vuole così (§ 8.1 del progetto).

Solo libreria standard.
"""
from __future__ import annotations

import threading
import time

from .tipi import ATTI, AUTORI, categoria

# Le frasi di una persona tenute in memoria al più (un ciclo finto che non chiude mai)
FRASI_MAX = 400


class Uscita:
    """L'uscita verso la voce di una corsia."""

    def __init__(self, speaker, log=print):
        self.speaker = speaker
        self.log = log
        self.osservatore = None        # il registro in ombra (Ombra.sente), o None
        self.cervello = None           # Brain: le chiamate dei tool fatte nella risposta
        self.scritto = False           # la frase della persona è scritta (da uno schermo)
        self._aperto = False           # un turno della voce aperto da questa uscita
        self._lock = threading.Lock()
        self._scritte: list[str] = []  # le frasi della persona in corso, per lo schermo
        self._sconosciuti: set = set()
        # La posizione fra le chiamate: la lista `last_tools` di Brain e quante chiamate c'erano
        # nelle liste di prima dello stesso turno (la ricerca promessa ne fa una nuova)
        self._lt_ref = None
        self._lt_base = 0

    # ── turni ──
    def _usabile(self) -> bool:
        return self._aperto and not bool(getattr(self.speaker, "interrupted", False))

    def turno(self):
        """Un turno della voce nuovo (`Speaker.start_turn`). Quello che si chiude: le frasi
        sentite per intero e l'interruzione, all'osservatore (il `voce_fine`)."""
        sp = self.speaker
        self._nota(("fine", list(getattr(sp, "played", None) or ()),
                    bool(getattr(sp, "interrupted", False))))
        sp.start_turn()
        self._aperto = True
        self._lt_ref, self._lt_base = None, 0

    def persona(self, scritto: bool = False):
        """Comincia il giro di una frase della persona: le frasi per lo schermo ripartono, e
        `scritto` dice il canale."""
        self.scritto = bool(scritto)
        with self._lock:
            self._scritte = []

    def aspetta(self, stallo_s: float | None = None):
        """Aspetta che la voce abbia detto ciò che ha in coda (`Speaker.wait`)."""
        if stallo_s is None:
            return self.speaker.wait()
        return self.speaker.wait(stallo_s)

    # ── le frasi ──
    def _chiamate(self) -> int | None:
        b = self.cervello
        lt = getattr(b, "last_tools", None) if b is not None else None
        if not isinstance(lt, list):
            return None
        if lt is not self._lt_ref:
            if self._lt_ref is not None:
                self._lt_base += len(self._lt_ref)
            self._lt_ref = lt
        return self._lt_base + len(lt)

    def di(self, testo: str, atto: str = "risposta", autore: str | None = None, *,
           fonte: str | None = None, pronta: bool = False) -> dict | None:
        """Una frase alla voce. `atto`: dall'elenco chiuso `tipi.ATTI`; `autore`: contenuto,
        atto o esito (predefinito: contenuto per le parole della risposta, atto per il resto);
        `fonte`: il dato non fidato da cui viene (agente, estensione); `pronta`: una frase già
        sintetizzata o d'attesa (`say_cached`, fuori da `played`). Restituisce il detto (in
        memoria) o None se il testo è vuoto."""
        if not isinstance(testo, str) or not testo.strip():
            return None
        cat = categoria(atto)
        if cat is None and atto not in self._sconosciuti:
            self._sconosciuti.add(atto)
            self.log(f"   [USCITA] atto fuori dall'elenco: {atto!r} (calliope/eventi/tipi.py)")
        if autore not in AUTORI:
            autore = "contenuto" if cat == "risposta" else "atto"
        sp = self.speaker
        if cat != "risposta" and not self._usabile():
            # Nessuna frase fuori turno (10/10, quarto giro): il satellite la scarterebbe
            self.turno()
        muto = bool(getattr(sp, "muto", False))
        canale = ("muta" if muto else "scritto" if self.scritto and cat != "voluto"
                  else "voce")
        detto = {"testo": testo, "atto": atto, "autore": autore, "canale": canale,
                 "pronta": bool(pronta), "t": time.time(),
                 "dopo_chiamate": self._chiamate() if cat == "risposta" else None,
                 "fonte": fonte}
        if cat != "voluto":
            with self._lock:
                if len(self._scritte) < FRASI_MAX:
                    self._scritte.append(testo)
        self._nota(("frase", detto))
        if pronta:
            sp.say_cached(testo)
        else:
            sp.say(testo)
        return detto

    def di_e_aspetta(self, testo: str, atto: str, autore: str | None = None) -> bool:
        """Una frase fuori da una risposta, in un turno della voce suo, e l'attesa che sia
        finita. Con l'uscita di un satellite controlla che lui l'abbia detta per intero (le
        frasi dette tornano in `played` con la fine del turno). True se detta, o se non si può
        sapere (10/10, «ricominciamo» muto sulla DGX)."""
        sp = self.speaker
        self.turno()
        prima = len(getattr(sp, "played", None) or [])
        self.di(testo, atto, autore)
        finita = self.aspetta()
        if getattr(sp, "remota", None) is None or getattr(sp, "muto", False):
            return True
        dette = [d.strip() for d in list(getattr(sp, "played", None) or [])[prima:]]
        if any(d and d in testo for d in dette):
            return True
        self.log(f"   [VOCE] il satellite non ha detto «{testo}» (turno "
                 f"{getattr(sp, 'turno', '?')}, interrotta {getattr(sp, 'interrupted', None)}, "
                 f"attesa finita {finita})")
        return False

    # ── segnali (niente testo: non sono frasi) ──
    def segnale(self):
        """Le due note prima di un annuncio (`Speaker.chime`)."""
        self.speaker.chime()

    def segnale_suono(self, suoni, tipo: str):
        """Il segnale d'inizio o di fine ascolto deciso dal server (`Speaker.suono`)."""
        self.speaker.suono(suoni, tipo)

    def segnale_ascolto(self, suoni, tipo: str):
        """Il segnale d'inizio o di fine ascolto dalle casse locali (`Speaker.suono_ascolto`)."""
        self.speaker.suono_ascolto(suoni, tipo)

    # ── ciò che si è detto ──
    def testo_scritto(self) -> str:
        """La risposta scritta sullo schermo (§ 3.5): le frasi della persona in corso, attese
        escluse, nell'ordine in cui sono andate alla voce."""
        with self._lock:
            return " ".join(t.strip() for t in self._scritte if t.strip())

    def _nota(self, item):
        oss = self.osservatore
        if oss is None:
            return
        try:
            oss(item)
        except Exception:  # noqa: BLE001 — l'ombra non ferma mai la voce
            pass


def per_voce(speaker, log=print) -> Uscita:
    """L'uscita di una voce: la stessa per il ciclo della corsia, per `main.py` e per
    `rispondi.py` (una per Speaker)."""
    u = getattr(speaker, "_uscita_unica", None)
    if isinstance(u, Uscita) and u.speaker is speaker:
        return u
    u = Uscita(speaker, log=log)
    try:
        speaker._uscita_unica = u
    except (AttributeError, TypeError):   # una voce finta senza attributi
        pass
    return u


def sintetizza_saluto(speaker, testo: str):
    """Il saluto che ogni satellite dice alla prima connessione, sintetizzato subito (fuori da
    una conversazione e dalle code: atto `saluto_avvio`, dichiarato)."""
    return speaker.sintetizza(testo)


__all__ = ["Uscita", "per_voce", "sintetizza_saluto", "ATTI"]
