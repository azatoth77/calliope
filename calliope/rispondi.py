"""
«Rispondi dove ti ho chiesto» (04/10/2026).

Prova vera del 04/10: una domanda **scritta** nella casella della web app del telefono ha
avuto la risposta dalle casse del portatile (il satellite attivo era lo studio), e
«mostramelo sullo schermo» detto dal telefono è andato allo schermo dello studio. Qui si
decide, turno per turno, da dove arriva la richiesta (l'**origine**: satellite, schermo,
stanza) e dove va la risposta.

- Frase scritta da uno schermo che è di un satellite (il telefono, la pagina del
  portatile): quel satellite diventa l'attivo **in prestito** (`ServerSatelliti.presta`) per
  il turno e la finestra di follow-up, così la risposta si dice lì e il follow-up a voce si
  ascolta lì; poi l'attivo torna quello di prima, se il satellite non l'ha preso per sua
  scelta («Parla», microfono acceso).
- Frase scritta da uno schermo senza audio (schermo di stanza, tablet senza satellite): la
  risposta si dice solo se il satellite attivo è nella stessa stanza; altrimenti la voce
  resta muta per il turno (`Speaker.muto`) e non si apre la finestra di follow-up. Mai detta
  ad alta voce in un'altra stanza.
- La risposta a una frase scritta va anche **scritta** sullo schermo da cui è arrivata
  (scheda «risposta», `Schermi.invia_a`): chi scrive spesso non può ascoltare.
- Le schede (`schermo_mostra`, quelle dei tool) vanno prima allo schermo dell'origine
  (`Schermi.origine_corrente` → `Mittente.schermo`, hub.destinatari), poi agli altri come prima.
- Annunci (timer, promemoria, documenti, lavori): se la richiesta che li ha generati è
  arrivata da un satellite preciso, si dicono lì (prestito anche per loro); altrimenti, o
  con quel satellite scollegato, dal satellite attivo come prima. Timer e promemoria per id
  dell'agenda; documenti e lavori per persona (l'origine della sua ultima richiesta). In
  memoria: dopo un riavvio vale il satellite attivo.

Senza satelliti (audio di questo computer) conta solo la stanza: una frase scritta da uno
schermo di un'altra stanza (diversa da `schermi_stanza`, o non aperto su questo computer se
`schermi_stanza` è vuota) ha la risposta solo scritta.

Tutti i satelliti insieme (06/10, calliope/corsie.py): ogni satellite ha la sua corsia, e la
frase scritta dal telefono o l'annuncio per una richiesta del portatile li prende già la
corsia giusta (corsie.Smistatore). Qui allora niente prestiti; lo stato del turno (origine,
chi ha chiesto, muto) è della corsia, cioè del thread, e la voce è quella della corsia.
"""

import threading

from . import corsie
from .schermi.archivio import norm_stanza

# Origini ricordate per gli annunci: oltre, le più vecchie si dimenticano
MAX_ORIGINI = 500


class Instradamento:
    def __init__(self, satelliti=None, schermi=None, speaker=None, cfg=None, log=print):
        self.satelliti = satelliti
        self.schermi = schermi
        self.speaker = speaker
        self.cfg = cfg
        self.log = log
        self._lock = threading.Lock()
        # Lo stato del turno in corso (_scritto, _turno, _persona_turno, _awake_prima), uno
        # per thread: ogni corsia ha il suo (06/10)
        self._qui = threading.local()
        self._origini: dict = {}              # chiave → origine (annunci)
        self._persone: dict = {}              # persona → origine della sua ultima richiesta
        if schermi is not None:
            schermi.origine_corrente = self.origine

    # ── stato del turno, per corsia ──
    def _stato(self, nome):
        return getattr(self._qui, nome, None)

    _scritto = property(lambda self: self._stato("scritto"),
                        lambda self, v: setattr(self._qui, "scritto", v))
    _turno = property(lambda self: self._stato("turno"),
                      lambda self, v: setattr(self._qui, "turno", v))
    _persona_turno = property(lambda self: self._stato("persona"),
                              lambda self, v: setattr(self._qui, "persona", v))
    _awake_prima = property(lambda self: self._stato("awake_prima"),
                            lambda self, v: setattr(self._qui, "awake_prima", v))

    def _voce(self):
        """La voce in uscita del turno: quella della corsia, o quella di sempre."""
        return corsie.per_corsia(self.speaker, "speaker")

    # ── origine ──
    def origine(self) -> dict | None:
        """{"satellite", "schermo", "stanza"} da cui arriva la richiesta adesso."""
        if self._scritto is not None:
            return dict(self._scritto)
        c = getattr(self.satelliti, "attivo", None) if self.satelliti is not None else None
        if c is None:
            return None
        return {"satellite": c.satellite.get("id"), "schermo": getattr(c, "schermo_id", None),
                "stanza": c.stanza or None}

    # ── turni ──
    def dopo_turno(self, awake_until: float) -> float:
        """In cima a ogni giro del ciclo: il turno di prima è finito. Toglie il muto, ricorda
        l'origine per la persona, e il prestito dura fino alla fine della finestra di
        follow-up. Restituisce la fine della finestra (quella di prima del turno, se era una
        frase scritta senza voce: niente ascolto senza nome in un'altra stanza)."""
        voce = self._voce()
        if voce is not None:
            voce.muto = False
        if self._awake_prima is not None:
            awake_until, self._awake_prima = self._awake_prima, None
        with self._lock:
            if self._turno is not None and self._persona_turno:
                self._persone[self._persona_turno] = self._turno
            self._scritto = self._turno = self._persona_turno = None
        if self.satelliti is not None:
            self.satelliti.proroga_prestito(awake_until)
        return awake_until

    def inizio_voce(self):
        """Una frase detta: l'origine è il satellite che l'ha sentita (l'attivo)."""
        self._scritto = None
        if self.satelliti is not None:
            self.satelliti.trattieni_prestito()
        self._turno = self.origine()

    def inizio_scritto(self, item: dict, awake_until: float) -> str:
        """Una frase scritta (o un modulo) da uno schermo. Restituisce come si risponde a
        voce: «satellite» (dal satellite di quello schermo), «stanza» (dal satellite attivo,
        che è nella stessa stanza, o dalle casse di qui), «muta» (solo scritta)."""
        sid = item.get("schermo_id")
        stanza = norm_stanza(item.get("stanza") or "") or None
        coll = self.satelliti.per_schermo(sid) if self.satelliti is not None else None
        self._scritto = {"satellite": coll.satellite.get("id") if coll is not None else None,
                         "schermo": sid, "stanza": (coll.stanza or stanza) if coll else stanza}
        self._turno = dict(self._scritto)
        if coll is not None and self.satelliti.presta(coll):
            return "satellite"
        if self._stessa_stanza(sid, stanza):
            return "stanza"
        voce = self._voce()
        if voce is not None:
            voce.muto = True
        self._awake_prima = awake_until
        return "muta"

    def _stessa_stanza(self, sid, stanza) -> bool:
        if self.satelliti is not None:
            att = self.satelliti.attivo_pronto()
            return bool(att is not None and stanza and norm_stanza(att.stanza or "") == stanza)
        hub = self.schermi
        if hub is None:
            return True
        pref = hub.stanza_predefinita
        if pref:
            return stanza == pref
        return hub.collegato(sid, locale=True)

    def persona(self, persona_id):
        """Chi ha chiesto in questo turno (per gli annunci di documenti e lavori)."""
        self._persona_turno = persona_id

    def risposta_scritta(self, item: dict, domanda: str, testo: str) -> bool:
        """La risposta, scritta sullo schermo da cui è arrivata la frase. Richiamata nello
        stesso turno (una ricerca promessa che allunga la risposta) sostituisce la scheda."""
        hub, sid = self.schermi, item.get("schermo_id")
        testo = (testo or "").strip()
        if hub is None or sid is None or not testo:
            return False
        from .schermi import schede
        s = hub.schermo(sid) or {}
        vis = schede.PERSONALE if s.get("proprietario") else schede.PUBBLICA
        chiave = f"risposta:{item.setdefault('_chiave', id(item))}"
        return hub.invia_a(sid, schede.risposta(domanda or "", testo, vis, chiave=chiave))

    # ── annunci ──
    def segna(self, chiave):
        """Un oggetto nato in questo turno (un timer, un promemoria): il suo annuncio andrà
        all'origine del turno. Fuori da un turno (agenda da terminale) niente."""
        o = self._turno
        if o is None:
            return
        with self._lock:
            if len(self._origini) >= MAX_ORIGINI:
                self._origini.pop(next(iter(self._origini)))
            self._origini[chiave] = dict(o)

    def avvolgi_agenda(self, agenda):
        """Ogni voce aggiunta all'agenda durante un turno ricorda da dove è stata chiesta."""
        add = agenda.add

        def add_con_origine(*a, **k):
            ident = add(*a, **k)
            self.segna(("agenda", ident))
            return ident
        agenda.add = add_con_origine

    def origine_di(self, chiave=None, persona=None) -> dict | None:
        with self._lock:
            o = self._origini.get(chiave) if chiave is not None else None
            if o is None and persona:
                o = self._persone.get(persona)
            return dict(o) if o else None

    def annuncia_verso(self, chiave=None, persona=None) -> bool:
        """Prima di dire un annuncio: se è nato da un satellite preciso, collegato, lo si
        dice lì (prestito, che `dopo_turno` chiude alla fine della finestra di follow-up).
        True se l'attivo è cambiato."""
        srv = self.satelliti
        # Tutti insieme: l'annuncio l'ha già preso la corsia giusta (corsie.Smistatore)
        if srv is None or getattr(srv, "insieme", False):
            return False
        # Senza toglierla: la scheda del timer scaduto (thread dell'agenda) può leggerla dopo
        o = self.origine_di(chiave, persona)
        if o is None or o.get("satellite") is None:
            return False
        coll = srv.per_id(o["satellite"])
        if coll is None or srv.attivo is coll:
            return False
        voce = self._voce()
        if voce is not None:
            voce.wait()                   # ciò che è già in coda si dice dove stava andando
        return srv.presta(coll)

    def corsia_di(self, chiave=None, persona=None) -> str | None:
        """La corsia («sat:<id>») da cui annunciare un oggetto nato da una richiesta (un timer)
        o per una persona (documenti, lavori): quella del satellite da cui aveva chiesto. None
        se non si sa (una corsia qualunque)."""
        o = self.origine_di(chiave, persona)
        sat = (o or {}).get("satellite")
        return None if sat is None else f"sat:{sat}"

    def mittente_annuncio(self, chiave):
        """Il mittente di una scheda nata da un annuncio (il timer scaduto): verso lo schermo
        e la stanza dell'origine, se si sa."""
        hub = self.schermi
        m = hub.mittente(None)
        o = self.origine_di(chiave)
        if o:
            if o.get("schermo") is not None:
                m.schermo = o["schermo"]
            if o.get("stanza"):
                m.stanza = o["stanza"]
        return m
