"""
I giochi sugli schermi (05/10/2026, decisioni di Dario del 04–05/10): le estensioni con una
scheda interattiva (calliope/estensioni/scheda.py) girano nel browser, in un riquadro isolato;
qui il lato di Calliope. Rapporto: docs/ricerche/2026-10-05-giochi.md.

- **Partita**: nasce dal tool del gioco (`est_<nome>`, a voce o scritto) su uno schermo; ha un
  gettone a caso che è l'indirizzo del suo documento (`GET /gioco/<gettone>`: lo compone
  scheda.documento dai file della versione approvata, impronta ricontrollata) e uno o più
  **posti** (uno per schermo), ognuno con il suo giocatore (chi ha aperto la partita da lì).
- **Messaggi dal riquadro** (`POST /api/gioco`, dalla pagina, che li ha già controllati): qui
  si ricontrolla tutto (schermo della sessione nella partita, tipo, dimensione, frequenza):
  `pronto` (il posto e i dati d'avvio), `battito` (tempo di gioco dei minori), `salva` e
  `leggi` (lo spazio dati dell'estensione), `manda` (a chi gioca da altri schermi, passando
  da qui), `chat` (testo libero tra giocatori: con un minore o un ospite nella partita passa
  dal guardiano), `di` (una frase detta da Calliope: poche al minuto, controllate come gli
  annunci, per i minori dal guardiano), `azione` (un metodo della porta stretta, con le regole
  delle estensioni), `fine`, `errore` e `guasto` (il cane da guardia della pagina).
- **Verso il riquadro**: l'evento SSE «gioco» allo schermo (messaggi degli altri, chat,
  giocatori, risposte che arrivano dopo, fine del tempo di gioco).

Nessun dato di casa passa di qui se il gioco non l'ha chiesto con la porta stretta; e una
partita che l'ha letto non manda più messaggi agli altri schermi (`gioco_dati_personali`).

- **Partita di prova** (11/10, collaudo di un gioco nella modalità sviluppo: `avvia_prova`): la
  versione candidata, NON approvata, sullo schermo da cui parla chi amministra, con il campo
  `"prova": true` nella scheda (la pagina la mostra con la cornice «PROVA»). Stesso riquadro e
  stessa CSP di una partita vera; in più nessun ponte verso Calliope: dal riquadro passano solo
  `pronto`, `battito`, `fine`, `errore` e `guasto` (`TIPI_PROVA`), mai `salva`/`leggi`, `manda`,
  `chat`, `di` né `azione`. Un posto solo, nessuno si unisce; il documento c'è finché quella
  versione è la candidata con l'impronta di quando è stata consegnata.

- **Comandi a voce** (11/10, `scheda.ascolta`, calliope/gioco_voce.py; dal 14/10 ricavati dalla
  macchina a stati, e a dirli è il motore nel riquadro): dal 14/10 il motore manda dopo ogni
  disegno l'**istantanea** numerata della partita (`stato`: fase, a chi tocca, giocatori e
  punti, esito, comandi a voce attivi), validata qui contro il manifesto (solo un sottoinsieme
  dei comandi di quella fase) e tenuta come stato della partita (`Posto.istantanea`); il ciclo
  della voce chiede `ascolto(schermi)` per il gioco aperto sullo schermo del satellite che
  ascolta e manda la mossa con `comando` (evento SSE «gioco» di tipo «comando», con il numero
  dell'istantanea: il motore rifiuta un comando vecchio e lo dice con `rifiutato`). Al gioco
  arrivano solo il nome del comando, il numero e, se il manifesto lo chiede, il nome di chi è
  riconosciuto dalla voce. Valgono anche in una partita di prova: sono un ingresso, come i
  tocchi, non un ponte verso Calliope.
"""

from __future__ import annotations

import json
import queue
import re
import secrets
import threading
import time
from collections import deque

from . import schede
from .hub import Mittente, destinatari
from ..testi import NIENTE, RANK

_CHIAVE = re.compile(r"^[A-Za-z0-9_\-. ]{1,40}$")
# Con un minore o un ospite nella partita i messaggi del gioco non portano testo libero: solo
# valori brevi senza spazi (mosse, coordinate, colori); il testo va con la chat, dal guardiano
_VALORE_BREVE = re.compile(r"^[\w\-.:#+/]{0,24}$")
MAX_STORIA = 200
MAX_SALVA = 16_000
MAX_DATI = 1_000_000
MAX_FRASE = 160
MAX_CHAT = 200
NOTE_GUASTO = {"non risponde": "Il gioco non rispondeva più: l'ho chiuso.",
               "navigazione": "Il gioco ha provato a cambiare pagina: l'ho chiuso.",
               "troppi messaggi": "Il gioco mandava troppi messaggi: l'ho chiuso.",
               "messaggi non validi": "Il gioco mandava messaggi non validi: l'ho chiuso.",
               "non parte": "Il gioco non è partito: l'ho chiuso."}
TIPI_PAGINA = ("pronto", "battito", "salva", "leggi", "manda", "chat", "di", "azione", "fine",
               "errore", "guasto", "stato", "rifiutato", "chiuso", "palco", "mossa", "gira")
# Una partita di prova (11/10): il gioco gira e basta, senza ponte verso Calliope né dati. I
# comandi a voce sì (`stato`, l'istantanea del motore, dice quali valgono; `rifiutato`, un
# comando arrivato su un'istantanea vecchia; `chiuso` lo manda la pagina quando il gioco si
# chiude): sono un ingresso, come i tocchi, e non portano niente fuori dal riquadro.
# Anche `palco` (14/10): la diagnosi del motore su ciò che esce dal palco, per il collaudo
# E `gira` (15/10): la tela vuole l'altro orientamento, e Calliope lo dice con una frase sua
TIPI_PROVA = ("pronto", "battito", "fine", "errore", "guasto", "stato", "rifiutato", "chiuso",
              "palco", "gira")
# «Gira il telefono» (15/10, decisione 3 del 12/10): detto a voce una volta per schermo
FRASE_GIRA = {"orizzontale": "Per questo gioco gira il telefono in orizzontale.",
              "verticale": "Per questo gioco tieni il telefono in verticale."}
MAX_VOCI = 64                          # persone riconosciute in una partita (i segni «v1»…)
# Un riquadro di cui la pagina non dice niente da tanto (il battito arriva ogni 15 s mentre si
# vede) non riceve comandi a voce: lo schermo è spento, la pagina è altrove o il gioco è nascosto
VIVO_S = 40.0
MAX_ATTIVI = 64
# Il messaggio «stato» (14/10): l'istantanea più, per la ripresa dopo «Riapri», lo stato intero
# del motore (opaco, al più come `salva`)
MAX_RIPRESA = MAX_SALVA


def candidata_intatta(est, nome: str, n) -> bool:
    """La versione `n` di `nome` è ancora la candidata (non approvata) e i suoi file sono quelli
    consegnati dall'agente (impronta di quando è stata consegnata)."""
    from ..estensioni.archivio import impronta
    try:
        if n is None or est.archivio.candidata(nome) != n:
            return False
        ver = est.archivio.versione(nome, n) or {}
        return bool(ver.get("impronta")) and impronta(
            est.archivio.cartella_versione(nome, n)) == ver.get("impronta")
    except (OSError, AttributeError, TypeError, ValueError):
        return False


def _final(testo: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": testo, "risposta_finale": testo}


def _rifiuto(ctx, testo: str, regola: str) -> dict:
    from ..tools.spec import note_rule
    note_rule(ctx, regola)
    return _final(testo, ok=False, fatto=NIENTE)


class Posto:
    def __init__(self, sid: int, mitt: Mittente, minore: bool):
        self.sid = sid
        self.persona = mitt.persona
        self.nome = mitt.nome
        self.livello = mitt.livello if mitt.persona else "ospite"
        self.minore = minore
        self.giocatore: int | None = None
        self.ultimo_battito = 0.0
        self.fermato = False
        self.messaggi: deque = deque(maxlen=200)     # istanti, per la frequenza
        self.chat: deque = deque(maxlen=50)
        # I comandi a voce (11/10): il riquadro è aperto (dopo «pronto», fino a «chiuso» o al
        # cane da guardia), l'ultimo messaggio della pagina (time.time) e l'ultima mossa o
        # apertura (monotonic)
        self.aperto = False
        self.contatto = 0.0
        self.segno = 0.0
        # L'istantanea della partita (14/10, passo 2 del progetto): l'ultima valida mandata dal
        # motore, controllata contro il manifesto (macchina.valida_istantanea). I comandi a voce
        # attivi vengono solo da qui: senza un'istantanea valida il gioco non ascolta
        self.istantanea: dict | None = None
        self.ist_n = -1                     # il numero dell'ultima valida (non può calare)
        self.scartate = 0                   # istantanee non valide (diagnosi)
        self.rifiutati = 0                  # comandi a voce rifiutati dal motore (vecchi)
        # La ripresa dopo «Riapri» (14/10, decisione 7): lo stato intero del motore mandato con
        # l'ultima istantanea valida (opaco: il server lo conserva e lo restituisce allo stesso
        # posto all'avvio di un riquadro nuovo, non lo legge), al più MAX_RIPRESA
        self.ripresa: dict | None = None
        # La diagnosi del palco (14/10): i difetti misurati dal motore sullo schermo vero (al
        # più tre frasi; [] = la pagina ci sta), None finché non arriva
        self.palco: list[str] | None = None
        self.palco_n = 0                    # quante misure sono arrivate
        # «Gira il telefono» (15/10): già detto a voce per questo schermo
        self.gira_detto = False

    @property
    def attivi(self) -> list[str] | None:
        """I comandi a voce dell'ultima istantanea valida, nell'ordine del motore (None senza
        istantanea): per le prove e la diagnosi."""
        return list(self.istantanea["comandi"]) if self.istantanea is not None else None


class Partita:
    def __init__(self, nome: str, versione: int, manifesto: dict, avviata_da: Mittente,
                 prova: bool = False):
        self.id = "P" + secrets.token_hex(4)
        # La versione candidata nel collaudo (11/10): niente ponte verso Calliope
        self.prova = bool(prova)
        self.gettone = secrets.token_urlsafe(24)
        self.nome, self.versione, self.manifesto = nome, versione, manifesto
        self.titolo = manifesto.get("titolo", nome)
        self.scheda = manifesto.get("scheda") or {}
        self.avviata_da = avviata_da
        self.creata = self.ultimo = time.time()
        self.posti: dict[int, Posto] = {}
        self.storia: deque = deque(maxlen=MAX_STORIA)
        self.contaminazione: set[str] = set()
        self.frasi: deque = deque(maxlen=50)
        self.carte: dict[int, dict] = {}            # la scheda mandata a ogni schermo
        self.n = 0
        # I nomi di chi gioca (14/10, passo 4 del progetto): quelli che Calliope stessa ha
        # mandato al riquadro dalla voce riconosciuta («gioco anch'io», le mosse con
        # «giocatore»), e il giudizio sugli altri (scritti sullo schermo o detti «sono Pippo»):
        # Calliope li dice solo dopo i controlli delle frasi dei giochi
        self.nomi_voce: set[str] = set()
        self.nomi_ok: dict[tuple, bool] = {}
        # La partita condivisa con il motore (14/10, decisione 6 del 12/10, rimandata e fatta
        # qui): il posto che tiene la partita (il suo motore è l'unico che scrive lo stato) e
        # l'ultimo stato intero che ha mandato, che gli altri schermi («specchi») disegnano
        self.autorevole: int | None = None
        self.stato_condiviso: dict | None = None
        # Chi è quale giocatore (15/10): un segno opaco per ogni persona riconosciuta dalla voce
        # in questa partita («v1», «v2»…). Il motore lega il segno al giocatore con «gioco
        # anch'io»; il riquadro non sa chi è (il nome lo riceve solo se il manifesto lo chiede)
        self.voci: dict[str, str] = {}

    def voce_di(self, nome: str | None, crea: bool = True) -> str | None:
        """Il segno della voce di una persona riconosciuta in questa partita (None senza nome,
        o oltre MAX_VOCI)."""
        if not nome:
            return None
        v = self.voci.get(nome)
        if v is None and crea and len(self.voci) < MAX_VOCI:
            v = self.voci[nome] = f"v{len(self.voci) + 1}"
        return v

    @property
    def condivisa(self) -> bool:
        return bool(self.scheda.get("condivisa")) and not self.prova

    @property
    def massimo(self) -> int:
        return int((self.scheda.get("giocatori") or {}).get("max", 1))

    @property
    def motore_condiviso(self) -> bool:
        """Una partita condivisa tra schermi con la macchina a stati e senza tela: un solo motore
        tiene la partita, gli altri schermi la disegnano e gli mandano le mosse. Con una tela
        resta com'era (ogni riquadro il suo motore, i messaggi con `manda`)."""
        m = self.macchina
        return bool(self.condivisa and m is not None
                    and not any(f.get("pagina") == "tela" for f in m["fasi"].values()))

    def tiene(self, posto: "Posto") -> "Posto":
        """Il posto il cui motore tiene la partita: quello autorevole in una partita condivisa
        con il motore, altrimenti il posto stesso."""
        if self.motore_condiviso and self.autorevole is not None:
            return self.posti.get(self.autorevole) or posto
        return posto

    @property
    def macchina(self) -> dict | None:
        """La macchina a stati del manifesto approvato (scheda.macchina), o None."""
        m = self.scheda.get("macchina")
        return m if isinstance(m, dict) and m.get("fasi") else None

    @property
    def ascolta(self) -> dict | None:
        """La sezione «ascolta» del manifesto (comandi a voce), o None."""
        a = self.scheda.get("ascolta")
        return a if isinstance(a, dict) and a.get("comandi") else None

    def protetta(self) -> bool:
        """Nella partita c'è un minore o un ospite (testo libero dal guardiano)."""
        return any(p.minore or not p.persona for p in self.posti.values())


class Giochi:
    def __init__(self, cfg, hub, estensioni=None, log=print):
        self.cfg = cfg
        self.hub = hub
        self.estensioni = estensioni
        self.log = log
        self._lock = threading.RLock()
        self.partite: dict[str, Partita] = {}
        self._per_gettone: dict[str, str] = {}
        self._documenti: dict[tuple, tuple] = {}
        # Le frasi che i giochi fanno dire a Calliope: le dice il ciclo principale (main.py)
        # quando nessuno parla, come gli annunci
        self.frasi: queue.Queue = queue.Queue()
        self.on_frase = None
        self.guardiano = None              # main.py: calliope.guardiano.Guardiano (o None)
        self.guasti: deque = deque(maxlen=100)
        # Le sveglie dei cicli della voce (11/10): un gioco che apre o cambia i suoi comandi a
        # voce le suona, così l'ascolto riparte con la finestra giusta (Ciclo._ascolta)
        self._sveglie: list = []

    # ── configurazione ──
    def _c(self, k: str, d):
        try:
            return type(d)(getattr(self.cfg, k, d))
        except (TypeError, ValueError):
            return d

    # ── dal tool del gioco ──
    def avvia(self, ctx, nome: str, versione: int, m: dict, argomenti: dict,
              prova: bool = False) -> dict:
        """Apre una partita (o si unisce a quella aperta da un altro schermo) e manda la
        scheda del gioco a uno schermo. Il risultato per la voce. `prova` (11/10): un gioco
        non ancora approvato, aperto per il collaudo: la scheda porta "prova": true e la
        pagina lo mostra nella modalità gioco con la cornice arancio e «PROVA» (contratto in
        docs/aree/giochi.md; chi apre la versione non attiva è lo sviluppo, non questo)."""
        from .. import minori
        from ..estensioni.scheda import e_gioco_puro, ha_macchina
        if not getattr(self.cfg, "giochi_enabled", True):
            return _rifiuto(ctx, "I giochi sugli schermi sono spenti.", "gioco_spento")
        self.pulisci()
        titolo = m.get("titolo", nome)
        prof = minori.profilo(ctx)
        minore = minori.e_minore(prof)
        if minore:
            resta = minori.gioco_restante_s(prof)
            if resta is not None and resta <= 0:
                out = _rifiuto(ctx, "Per oggi il tempo dei giochi è finito.", "gioco_tempo_finito")
                rq = minori.richieste()
                if rq is not None:
                    try:
                        _, nuova = rq.crea(prof, "tempo_gioco", "tempo_gioco",
                                           registry=getattr(ctx, "speakers", None))
                        t = minori._tutore_nome(prof, getattr(ctx, "speakers", None))
                        frase = ("Per oggi il tempo dei giochi è finito. " + (
                            f"Ho chiesto a {t} se puoi giocare ancora un po'." if nuova else
                            f"L'ho già chiesto a {t}: aspettiamo la risposta."))
                        out.update(conferma=frase, risposta_finale=frase)
                    except Exception:  # noqa: BLE001
                        pass
                return out
        if not ha_macchina(m):
            # 14/10 (passo 4, decisione 9 del 12/10): un gioco del formato di prima, con
            # gioco.js libero, non si apre più: si rifà con la macchina a stati
            return _rifiuto(ctx, f"«{titolo}» è un gioco del formato di prima: va rifatto con lo "
                                 "sviluppo, chiedimelo come modifica.", "gioco_formato_vecchio")
        mitt = self.hub.mittente(ctx)
        puro = e_gioco_puro(m)
        perm = m.get("permessi") or {}
        vis = (schede.PUBBLICA if puro else schede.PERSONALE
               if (perm.get("legge") or {}).get("agenda") else schede.CASA)
        stanza = mitt.stanza or self.hub.stanza_predefinita or None
        dest, motivo = destinatari(vis, mitt, self.hub.abbinati(), stanza)
        if not dest:
            frasi = {"nessuno_schermo": "Per giocare serve uno schermo abbinato: non ne ho.",
                     "ospite": f"«{titolo}» lo mostro solo a chi vive in casa.",
                     "personale": f"«{titolo}» va sul tuo schermo personale, e non ne hai uno.",
                     "zona_grigia": "Non ti ho riconosciuto bene: ripetimelo con una frase più "
                                    "lunga.",
                     "stanza": "Qui non c'è uno schermo per giocare."}
            return _rifiuto(ctx, frasi.get(motivo, "Non trovo uno schermo per giocare."),
                            "gioco_senza_schermo")
        # Uno schermo solo: quello da cui arriva la richiesta, altrimenti il personale di chi
        # parla, altrimenti il primo della stanza
        s = next((x for x in dest if x.get("id") == mitt.schermo), None) or next(
            (x for x in dest if mitt.persona and x.get("proprietario") == mitt.persona), dest[0])
        sid = s["id"]
        unisciti = str((argomenti or {}).get("partita") or "").strip().lower() != "nuova"
        with self._lock:
            p = None
            if m.get("scheda", {}).get("condivisa") and unisciti:
                aperte = [x for x in self.partite.values() if x.nome == nome
                          and x.versione == versione and not x.prova and sid not in x.posti
                          and len(x.posti) < x.massimo and time.time() - x.ultimo < 1800]
                p = max(aperte, key=lambda x: x.ultimo) if aperte else None
            nuova = p is None
            if nuova:
                p = Partita(nome, versione, m, mitt)
                self.partite[p.id] = p
                self._per_gettone[p.gettone] = p.id
            p.posti[sid] = Posto(sid, mitt, minore)
            p.ultimo = time.time()
        card = schede.nuova("gioco", titolo, vis, durata_s=None, chiave=f"gioco:{p.id}",
                            partita=p.id, doc=f"/gioco/{p.gettone}", condivisa=p.condivisa,
                            giocatori=p.massimo, watchdog_s=self._c("giochi_watchdog_s", 6.0),
                            **({"prova": True} if prova else {}))
        self.hub.ricorda(card, mitt)
        p.carte[sid] = card
        collegato = self.hub.invia_a(sid, card)
        self._registra(p, "avvio" if nuova else "unito", schermo=s.get("nome"),
                       persona=mitt.nome)
        dove = s.get("nome") or "schermo"
        if not nuova:
            altri = [self._nome_schermo(x) for x in p.posti if x != sid]
            frase = (f"Sei nella partita di «{titolo}»" + (f" con {', '.join(altri)}"
                                                           if altri else "") + ".")
        elif p.condivisa:
            frase = (f"Ecco «{titolo}» sullo schermo {self._di(dove)}. Per giocare da un'altra "
                     f"stanza, chiedimelo da lì.")
        else:
            frase = f"Ecco «{titolo}» sullo schermo {self._di(dove)}."
        if not collegato:
            frase += " Lo schermo sembra spento: lo vedrai appena si riaccende."
        from ..tools.spec import note_rule
        note_rule(ctx, "gioco_avviato")
        return _final(frase, partita=p.id)

    def avvia_prova(self, ctx, nome: str, versione: int, m: dict) -> dict:
        """Il collaudo di un gioco (11/10, DGX delle 16:25: «è un gioco, dovrei vederlo» e
        «Un gioco si prova sullo schermo dopo l'approvazione»): la versione candidata, non
        approvata, in una partita di prova sullo schermo da cui si parla (o il personale di chi
        parla, o il primo della stanza), con `"prova": true` nella scheda. Solo per chi vive in
        casa (la chiede chi amministra, nella modalità sviluppo); una prova per gioco alla
        volta. Il risultato per la voce."""
        from ..estensioni.scheda import ha_macchina
        if not getattr(self.cfg, "giochi_enabled", True):
            return _rifiuto(ctx, "I giochi sugli schermi sono spenti.", "gioco_spento")
        self.pulisci()
        titolo = m.get("titolo", nome)
        if not ha_macchina(m):
            return _rifiuto(ctx, f"«{titolo}» è un gioco del formato di prima: va rifatto con la "
                                 "macchina a stati.", "gioco_formato_vecchio")
        mitt = self.hub.mittente(ctx)
        stanza = mitt.stanza or self.hub.stanza_predefinita or None
        dest, motivo = destinatari(schede.CASA, mitt, self.hub.abbinati(), stanza)
        if not dest:
            frasi = {"nessuno_schermo": "Per vederlo serve uno schermo abbinato: non ne ho.",
                     "zona_grigia": "Non ti ho riconosciuto bene: ripetimelo con una frase più "
                                    "lunga.",
                     "stanza": "Qui non c'è uno schermo dove mostrarlo."}
            return _rifiuto(ctx, frasi.get(motivo, "Non trovo uno schermo dove mostrarlo."),
                            "gioco_senza_schermo")
        s = next((x for x in dest if x.get("id") == mitt.schermo), None) or next(
            (x for x in dest if mitt.persona and x.get("proprietario") == mitt.persona), dest[0])
        sid = s["id"]
        with self._lock:
            # Una prova per gioco: quella di prima non vale più (il suo indirizzo muore)
            for vecchia in [k for k, v in self.partite.items() if v.prova and v.nome == nome]:
                self._per_gettone.pop(self.partite.pop(vecchia).gettone, None)
            p = Partita(nome, versione, m, mitt, prova=True)
            self.partite[p.id] = p
            self._per_gettone[p.gettone] = p.id
            p.posti[sid] = Posto(sid, mitt, False)
        card = schede.nuova("gioco", titolo, schede.CASA, durata_s=None,
                            chiave=f"gioco:{p.id}", partita=p.id, doc=f"/gioco/{p.gettone}",
                            condivisa=False, giocatori=p.massimo,
                            watchdog_s=self._c("giochi_watchdog_s", 6.0), prova=True,
                            versione=versione)
        self.hub.ricorda(card, mitt)
        p.carte[sid] = card
        collegato = self.hub.invia_a(sid, card)
        self._registra(p, "prova", schermo=s.get("nome"), persona=mitt.nome)
        frase = (f"Ecco «{titolo}» in prova sullo schermo {self._di(s.get('nome') or 'schermo')}"
                 f": è la versione {versione}, non ancora attiva.")
        if not collegato:
            frase += " Lo schermo sembra spento: lo vedrai appena si riaccende."
        from ..tools.spec import note_rule
        note_rule(ctx, "gioco_prova")
        return _final(frase, partita=p.id, schermo=s.get("nome"))

    def _nome_schermo(self, sid) -> str:
        s = self.hub.schermo(sid) or {}
        return f"lo schermo {self._di(s.get('nome') or 'senza nome')}"

    @staticmethod
    def _di(nome: str) -> str:
        n = str(nome or "").strip()
        return n if n.lower().startswith(("del", "dello", "della", "di ")) else f"«{n}»"

    # ── il documento del riquadro ──
    def documento(self, gettone: str) -> tuple[str, str] | None:
        """(HTML, CSP) del riquadro della partita, dai file della versione approvata (impronta
        ricontrollata). None: gettone sconosciuto, partita finita o file cambiati."""
        from ..estensioni.scheda import SchedaNonValida, documento
        with self._lock:
            pid = self._per_gettone.get(str(gettone or ""))
            p = self.partite.get(pid) if pid else None
        est = self.estensioni
        if p is None or est is None:
            return None
        if p.prova:
            # La versione candidata (11/10): ancora la candidata, con i file di quando l'agente
            # l'ha consegnata (come Estensioni.prova_candidata)
            if not candidata_intatta(est, p.nome, p.versione):
                return None
        else:
            voce = est.archivio.voce(p.nome) or {}
            if voce.get("stato") != "attiva" or voce.get("attiva") != p.versione \
                    or not est.archivio.verifica(p.nome):
                return None
        chiave = (p.nome, p.versione, p.prova)
        d = self._documenti.get(chiave)
        if d is None:
            try:
                d = documento(p.scheda, est.file_versione(p.nome, p.versione), p.titolo)
            except SchedaNonValida:
                return None                       # un gioco del formato di prima (14/10)
            self._documenti = {chiave: d}             # una versione per volta in memoria
        return d

    # ── dalla pagina ──
    def da_pagina(self, schermo: dict, dati: dict) -> dict:
        """Un messaggio di un riquadro, arrivato dalla pagina dello schermo. Il risultato va
        alla pagina (e al riquadro, se aveva un id); `_stato` è il codice HTTP."""
        if not isinstance(dati, dict):
            return {"errore": "dati non validi", "_stato": 400}
        tipo = str(dati.get("tipo") or "")
        if tipo not in TIPI_PAGINA:
            return {"errore": "tipo sconosciuto", "_stato": 400}
        sid = schermo.get("id")
        with self._lock:
            p = self.partite.get(str(dati.get("partita") or ""))
            posto = p.posti.get(sid) if p is not None else None
        if p is None or posto is None:
            return {"errore": "partita sconosciuta per questo schermo", "_stato": 404}
        if p.prova and tipo not in TIPI_PROVA:
            # Una versione non approvata non parla con Calliope (11/10): né dati, né altri
            # schermi, né frasi, né tool
            self._registra(p, "prova_rifiutata", regola="gioco_prova_senza_ponte", tipo=tipo)
            return {"errore": "gioco in prova: qui gira e basta, senza dati né azioni",
                    "_stato": 403}
        # Frequenza (il battito e il cane da guardia non contano)
        ora = time.time()
        if tipo not in ("battito", "guasto"):
            n = self._c("giochi_messaggi_secondo", 10)
            recenti = [t for t in posto.messaggi if ora - t < 1.0]
            if len(recenti) >= n:
                self._registra(p, "troppi_messaggi", regola="gioco_troppi_messaggi")
                return {"errore": "troppi messaggi", "_stato": 429}
            posto.messaggi.append(ora)
        try:
            grezzo = len(json.dumps(dati, ensure_ascii=False))
        except (TypeError, ValueError):
            return {"errore": "dati non validi", "_stato": 400}
        tetto = self._c("giochi_messaggio_max", 4096) + 512
        if tipo == "stato":
            tetto += MAX_RIPRESA
        if grezzo > tetto:
            self._registra(p, "messaggio_grande", regola="gioco_messaggio_grande")
            return {"errore": "messaggio troppo grande", "_stato": 413}
        p.ultimo = ora
        posto.contatto = ora
        f = getattr(self, "_t_" + tipo)
        try:
            return f(p, posto, dati)
        except Exception as e:  # noqa: BLE001 — un messaggio non ferma il server
            self.log(f"[GIOCHI] {p.titolo}: {tipo} non riuscito: {type(e).__name__}: {e}")
            return {"errore": "non riuscito", "_stato": 500}

    def _avvio(self, p: Partita, posto: Posto) -> dict:
        d = {"partita": p.id, "giocatore": posto.giocatore,
             "giocatori": len(p.posti), "massimo": p.massimo, "condivisa": p.condivisa,
             "storia": list(p.storia)[-100:], "lingua": "it"}
        if p.motore_condiviso:
            # Chi tiene la partita riparte dall'ultimo stato condiviso; uno specchio lo disegna
            ruolo = "autorevole" if p.autorevole == posto.sid else "specchio"
            d["ruolo"] = ruolo
            if p.stato_condiviso is not None:
                d["ripresa" if ruolo == "autorevole" else "stato"] = p.stato_condiviso
        elif posto.ripresa is not None:
            d["ripresa"] = posto.ripresa
        return d

    def _t_pronto(self, p: Partita, posto: Posto, dati) -> dict:
        from .. import minori
        with self._lock:
            if posto.giocatore is None:
                usati = {x.giocatore for x in p.posti.values() if x.giocatore is not None}
                posto.giocatore = next(i for i in range(1, p.massimo + 2) if i not in usati)
        if posto.minore:
            prof = self._profilo(posto.persona)
            resta = minori.gioco_restante_s(prof) if prof is not None else None
            if resta is not None and resta <= 0:
                posto.fermato = True
                return {"ok": False, "fine_tempo": True,
                        "nota": "Per oggi il tempo dei giochi è finito."}
        posto.fermato = False
        # Riquadro nuovo (anche «Riapri» o la pagina ricaricata): il motore riparte e manda la
        # sua istantanea (fino ad allora niente comandi a voce: il server non deduce lo stato),
        # e la finestra senza nome riparte da adesso
        posto.aperto, posto.segno = True, time.monotonic()
        posto.istantanea, posto.ist_n = None, -1
        if p.motore_condiviso:
            with self._lock:
                t = p.posti.get(p.autorevole) if p.autorevole is not None else None
                # chi la teneva non c'è più (chiuso, fermato, o la sua pagina tace da VIVO_S)
                if (t is None or t is posto or not t.aperto or t.fermato
                        or time.time() - t.contatto > VIVO_S):
                    p.autorevole = posto.sid
        if p.ascolta:
            self.sveglia_voce()
        self._agli_altri(p, posto, "giocatori", {"giocatori": len(p.posti),
                                                 "pronto": posto.giocatore})
        return {"ok": True, "avvio": self._avvio(p, posto)}

    def _t_battito(self, p: Partita, posto: Posto, dati) -> dict:
        """Il tempo di gioco (05/10, decisione 5): la pagina manda un battito ogni ~15 s mentre
        il riquadro si vede. Conta per il giocatore del posto, se è un minore."""
        from .. import minori
        ora = time.time()
        try:
            secondi = float(dati.get("secondi") or 0)
        except (TypeError, ValueError):
            secondi = 0.0
        # Mai più del tempo vero passato dal battito di prima (una pagina non gonfia né
        # sgonfia il conto), al più 30 s
        passato = ora - posto.ultimo_battito if posto.ultimo_battito else secondi
        secondi = max(0.0, min(secondi, passato + 1.0, 30.0))
        posto.ultimo_battito = ora
        if not posto.minore or posto.fermato:
            return {"ok": True, "fine_tempo": posto.fermato}
        prof = self._profilo(posto.persona)
        tg = minori.tempo_gioco()
        if prof is None or tg is None:
            return {"ok": True}
        tg.aggiungi(prof.id, secondi)
        resta = minori.gioco_restante_s(prof)
        if resta is not None and resta <= 0:
            posto.fermato = True
            self._registra(p, "fine_tempo", regola="gioco_tempo_finito", persona=prof.name)
            nota = "Per oggi il tempo dei giochi è finito."
            self.hub.evento_a(posto.sid, "gioco", {"partita": p.id, "tipo": "fine_tempo",
                                                   "dati": {"nota": nota}})
            return {"ok": True, "fine_tempo": True, "nota": nota}
        return {"ok": True, "resta_s": round(resta) if resta is not None else None}

    def _file_dati(self, p: Partita, chiave: str):
        est = self.estensioni
        cart = est.archivio.cartella_dati(p.nome)
        return cart, cart / f"gioco_{chiave}.json"

    def _t_salva(self, p: Partita, posto: Posto, dati) -> dict:
        if not p.scheda.get("salva"):
            return {"errore": "questo gioco non salva dati", "_stato": 403}
        chiave = str(dati.get("chiave") or "")
        if not _CHIAVE.match(chiave) or ".." in chiave:
            return {"errore": "chiave non valida (lettere, cifre, - _ . e spazi)", "_stato": 400}
        try:
            testo = json.dumps(dati.get("valore"), ensure_ascii=False)
        except (TypeError, ValueError):
            return {"errore": "valore non valido", "_stato": 400}
        if len(testo.encode("utf-8")) > MAX_SALVA:
            return {"errore": "valore troppo grande", "_stato": 413}
        cart, f = self._file_dati(p, chiave)
        cart.mkdir(parents=True, exist_ok=True)
        altri = sum(x.stat().st_size for x in cart.iterdir() if x.is_file() and x != f)
        if altri + len(testo.encode("utf-8")) > MAX_DATI:
            return {"errore": "spazio dei dati esaurito", "_stato": 413}
        from ..persistenza import scrivi_atomico
        if p.contaminazione:
            # Dati personali letti dalla partita: chi li rilegge è contaminato (come porta.py)
            self.estensioni.archivio.contamina(p.nome, p.contaminazione)
        scrivi_atomico(f, testo)
        return {"ok": True}

    def _t_leggi(self, p: Partita, posto: Posto, dati) -> dict:
        if not p.scheda.get("salva"):
            return {"errore": "questo gioco non salva dati", "_stato": 403}
        chiave = str(dati.get("chiave") or "")
        if not _CHIAVE.match(chiave) or ".." in chiave:
            return {"errore": "chiave non valida", "_stato": 400}
        _, f = self._file_dati(p, chiave)
        if not f.is_file():
            return {"ok": True, "valore": None}
        p.contaminazione |= set(self.estensioni.archivio.contaminazione(p.nome))
        try:
            return {"ok": True, "valore": json.loads(f.read_text(encoding="utf-8"))}
        except ValueError:
            return {"ok": True, "valore": None}

    def _t_manda(self, p: Partita, posto: Posto, dati) -> dict:
        if not p.condivisa:
            return {"errore": "partita non condivisa", "_stato": 403}
        valore = dati.get("dati")
        if p.contaminazione:
            # La partita ha letto dati personali (porta stretta): agli altri schermi niente
            self._registra(p, "bloccato", regola="gioco_dati_personali")
            return {"errore": "la partita ha letto dati personali: niente messaggi agli altri "
                              "schermi", "_stato": 403}
        if p.protetta() and not _solo_valori_brevi(valore):
            self._registra(p, "bloccato", regola="gioco_testo_libero")
            return {"errore": "con un bambino o un ospite nella partita i messaggi del gioco "
                              "portano solo valori brevi: il testo va con la chat",
                    "_stato": 422}
        with self._lock:
            p.n += 1
            msg = {"n": p.n, "da": posto.giocatore, "dati": valore}
            p.storia.append(msg)
        self._agli_altri(p, posto, "messaggio", msg)
        return {"ok": True, "n": p.n}

    def _t_chat(self, p: Partita, posto: Posto, dati) -> dict:
        if not (p.condivisa and p.scheda.get("chat")):
            return {"errore": "questo gioco non ha la chat", "_stato": 403}
        testo = _pulisci(dati.get("testo"), MAX_CHAT)
        if not testo:
            return {"errore": "messaggio vuoto", "_stato": 400}
        ora = time.time()
        if len([t for t in posto.chat if ora - t < 60]) >= self._c("giochi_chat_minuto", 6):
            return {"errore": "troppi messaggi: aspetta un momento", "_stato": 429}
        posto.chat.append(ora)
        if p.protetta():
            esito = self._guardiano(testo, domanda=True, minore=any(
                x.minore for x in p.posti.values()))
            if esito != "ok":
                regola = "gioco_chat_pericolo" if esito == "pericolo" else "gioco_chat_fermata"
                self._registra(p, "chat_fermata", regola=regola)
                if esito == "pericolo" and posto.minore:
                    self._avviso_pericolo(posto)
                return {"errore": "messaggio non mandato", "_stato": 422}
        self._agli_altri(p, posto, "chat", {"da": posto.giocatore, "testo": testo})
        return {"ok": True}

    def _t_di(self, p: Partita, posto: Posto, dati) -> dict:
        """Una frase del gioco detta da Calliope («Hai vinto!»): poche al minuto, nessun
        simbolo, controllata come gli annunci (riferire.controlla_testo: numeri a pagamento,
        segreti, soldi, indicazioni sulla casa); per un minore o un ospite dal guardiano. Non
        entra nella storia della conversazione."""
        if not p.scheda.get("voce"):
            return {"errore": "questo gioco non parla", "_stato": 403}
        testo = _pulisci(dati.get("testo"), MAX_FRASE)
        if not testo or not re.search(r"[A-Za-zÀ-ÿ]{2}", testo):
            return {"errore": "frase vuota", "_stato": 400}
        ora = time.time()
        with self._lock:
            if len([t for t in p.frasi if ora - t < 60]) >= self._c("giochi_frasi_minuto", 3):
                self._registra(p, "frase_fermata", regola="gioco_frasi_troppe")
                return {"errore": "troppe frasi: al più qualcuna al minuto", "_stato": 429}
            p.frasi.append(ora)
        from .. import riferire
        detto, regole = riferire.controlla_testo(testo, "estensione")
        if regole:
            # Un numero a pagamento, un ordine, un segreto: la frase non si dice affatto (una
            # frase fissa al posto di «Hai vinto!» non servirebbe a nessuno)
            self._registra(p, "frase_fermata", regola=",".join(regole))
            return {"errore": "frase non detta", "_stato": 422}
        if posto.minore or not posto.persona:
            esito = self._guardiano(detto, domanda=False, minore=posto.minore)
            if esito != "ok":
                self._registra(p, "frase_fermata", regola="gioco_frase_guardiano")
                return {"errore": "frase non detta", "_stato": 422}
        self.frasi.put({"messaggio": detto, "partita": p.id, "titolo": p.titolo,
                        "persona": posto.persona, "minore": posto.minore,
                        "schermo": posto.sid})
        if self.on_frase is not None:
            try:
                self.on_frase()
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True}

    def _t_azione(self, p: Partita, posto: Posto, dati) -> dict:
        """Un metodo della porta stretta chiesto dal riquadro (con gli scope del manifesto):
        sicura → subito; vietata → errore; pericolosa → si chiede a voce, e la risposta arriva
        al riquadro dopo (evento «gioco»)."""
        nome = str(dati.get("nome") or "")
        args = dati.get("argomenti") if isinstance(dati.get("argomenti"), dict) else {}
        if nome not in (p.scheda.get("azioni") or []):
            self._registra(p, "azione_rifiutata", regola="gioco_azione_non_dichiarata",
                           azione=nome[:40])
            return {"errore": f"«{nome[:40]}» non è tra le azioni del gioco", "_stato": 403}
        est = self.estensioni
        if est is None:
            return {"errore": "estensioni spente", "_stato": 503}
        rif = dati.get("id")
        es = AzioneGioco(self, p, posto, nome, args, rif)
        return es.avvia()

    def _t_stato(self, p: Partita, posto: Posto, dati) -> dict:
        """L'istantanea della partita dal motore (14/10, passo 2 del progetto): fase, a chi tocca,
        giocatori e punti, esito, i comandi a voce che valgono adesso, numerata. Validata contro
        il manifesto approvato (macchina.valida_istantanea): solo comandi che quella fase può
        avere, mai nuovi; il numero non cala. Una non valida si scarta e il gioco resta senza
        comandi a voce finché non ne manda una buona (regola gioco_stato_non_valido)."""
        from ..estensioni import macchina as mc
        m = p.macchina
        if m is None or p.ascolta is None:
            return {"errore": "questo gioco non ha la macchina a stati", "_stato": 403}
        if p.motore_condiviso and p.autorevole != posto.sid:
            # In una partita condivisa lo stato lo scrive un motore solo. Uno schermo che
            # crede di tenerla (la sua pagina taceva e la partita è passata a un altro) torna
            # specchio, con lo stato di adesso
            self._registra(p, "stato_rifiutato", regola="gioco_stato_non_autorevole")
            self.hub.evento_a(posto.sid, "gioco", {"partita": p.id, "tipo": "specchio",
                                                   "dati": {"stato": p.stato_condiviso}})
            return {"errore": "la partita la tiene un altro schermo", "_stato": 403}
        try:
            ist = mc.valida_istantanea(dati.get("istantanea"), m, p.scheda.get("giocatori")
                                       or {}, posto.ist_n)
        except mc.IstantaneaNonValida as e:
            prima = bool(self._attivi(p, posto))
            posto.istantanea = None
            posto.scartate += 1
            self._registra(p, "stato_scartato", regola="gioco_stato_non_valido",
                           motivo=str(e)[:120])
            if prima:
                self.sveglia_voce()
            return {"errore": f"istantanea non valida: {e}", "_stato": 400}
        # Un segno di voce che Calliope non ha dato in questa partita non lega nessuno
        noti = set(p.voci.values())
        for g in ist["giocatori"]:
            if g.get("voce") is not None and g["voce"] not in noti:
                g.pop("voce")
        self._nomi_detti(p, posto, ist)
        prima = self._attivi(p, posto)
        ripresa = self._ripresa(dati.get("ripresa"), ist)
        with self._lock:
            posto.istantanea, posto.ist_n = ist, ist["n"]
            # Solo quella che accompagna l'ultima istantanea valida (senza: niente ripresa, mai
            # una partita vecchia)
            posto.ripresa = ripresa
            if p.motore_condiviso and ripresa is not None:
                p.stato_condiviso = ripresa
        if p.motore_condiviso and ripresa is not None:
            self._agli_specchi(p, posto, ist, ripresa)
        if bool(prima) != bool(ist["comandi"]):
            self.sveglia_voce()
        return {"ok": True, "n": ist["n"]}

    def _agli_specchi(self, p: Partita, posto: Posto, ist: dict, stato: dict):
        """Lo stato della partita condivisa agli altri schermi, che lo disegnano. Come per
        `manda`: niente se la partita ha letto dati personali; con un minore o un ospite nella
        partita niente se un nome scritto non passa i controlli (resta sullo schermo di chi
        tiene la partita)."""
        if p.contaminazione:
            self._registra(p, "bloccato", regola="gioco_dati_personali")
            return
        if p.protetta() and any(g.get("scritto") and g.get("detto") != g.get("nome")
                                for g in ist["giocatori"]):
            self._registra(p, "bloccato", regola="gioco_nome_fermato")
            return
        self._agli_altri(p, posto, "partita", {"stato": stato})

    def _t_mossa(self, p: Partita, posto: Posto, dati) -> dict:
        """Una mossa (un tocco) o un nome scritto su uno specchio di una partita condivisa con
        il motore: va al motore che tiene la partita, che la controlla come un comando a voce
        (con il numero dell'istantanea: una mossa vecchia la rifiuta). Qui solo i comandi
        attivi dell'ultima istantanea valida, e un nome nella forma chiusa."""
        from ..estensioni import macchina as mc
        if not p.motore_condiviso or p.autorevole == posto.sid:
            return {"errore": "qui le mosse le fa il gioco stesso", "_stato": 403}
        t = p.posti.get(p.autorevole) if p.autorevole is not None else None
        if t is not None and t.aperto and time.time() - t.contatto > VIVO_S:
            # La pagina di chi teneva la partita tace (schermo spento): la prende un altro
            self._passa_la_partita(p, t)
            return {"errore": "la partita passa a un altro schermo: riprova", "_stato": 409}
        ist = t.istantanea if t is not None and t.aperto and not t.fermato else None
        if ist is None:
            return {"errore": "la partita non è aperta su nessuno schermo", "_stato": 409}
        if dati.get("rinomina") is not None:
            i, nome = dati.get("rinomina"), dati.get("nome")
            if (not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(ist["giocatori"])
                    or not mc.nome_chiuso(nome)):
                return {"errore": "nome non valido", "_stato": 400}
            self.hub.evento_a(t.sid, "gioco", {"partita": p.id, "tipo": "nome",
                                               "dati": {"i": i, "nome": nome}})
            return {"ok": True}
        comando, n = dati.get("comando"), dati.get("n")
        if (not isinstance(comando, str) or comando not in ist["comandi"]
                or not isinstance(n, int) or isinstance(n, bool)):
            self._registra(p, "mossa_rifiutata", regola="gioco_mossa_rifiutata",
                           comando=str(comando)[:24])
            return {"errore": "la mossa adesso non vale", "_stato": 400}
        posto.segno = t.segno = time.monotonic()
        # Il numero di questo schermo (15/10, chi è quale giocatore): lo mette il server, non lo
        # specchio. Il motore che tiene la partita lo usa per «gioco anch'io» e per i turni
        dati_m = {"comando": comando, "n": n}
        if posto.giocatore:
            dati_m["schermo"] = posto.giocatore
        self.hub.evento_a(t.sid, "gioco", {"partita": p.id, "tipo": "comando", "dati": dati_m})
        return {"ok": True}

    def _passa_la_partita(self, p: Partita, posto: Posto):
        """Lo schermo che teneva la partita condivisa si è chiuso: la tiene un altro schermo
        aperto, che riparte dall'ultimo stato (evento «autorevole»)."""
        if not p.motore_condiviso or p.autorevole != posto.sid:
            return
        ora = time.time()
        altri = [x for x in p.posti.values() if x is not posto and x.aperto and not x.fermato
                 and ora - x.contatto <= VIVO_S]
        p.autorevole = altri[0].sid if altri else None
        if altri:
            self._registra(p, "passa", regola="gioco_partita_passata")
            self.hub.evento_a(altri[0].sid, "gioco", {"partita": p.id, "tipo": "autorevole",
                                                      "dati": {"stato": p.stato_condiviso}})

    @staticmethod
    def _ripresa(r, ist: dict) -> dict | None:
        """Lo stato per la ripresa, se è un oggetto JSON entro MAX_RIPRESA con lo stesso numero
        e la stessa fase dell'istantanea che accompagna; altrimenti None."""
        if not isinstance(r, dict) or r.get("n") != ist["n"] or r.get("fase") != ist["fase"]:
            return None
        try:
            if len(json.dumps(r, ensure_ascii=False)) > MAX_RIPRESA:
                return None
        except (TypeError, ValueError):
            return None
        return r

    def _nomi_detti(self, p: Partita, posto: Posto, ist: dict):
        """Come Calliope dice ogni giocatore (14/10, passo 4 del progetto, decisione 1 di chi
        amministra): «Giocatore N» e i nomi che Calliope stessa ha mandato dalla voce
        riconosciuta si dicono; gli altri (scritti sullo schermo, detti «gioco anch'io, sono
        Pippo») sono testo del gioco: si dicono solo se passano i controlli delle frasi dei giochi
        (riferire.controlla_testo; con un minore o un ospite nella partita il guardiano), mai in
        una partita di prova; se no restano sullo schermo e a voce sono «Giocatore N». Segna
        `detto` e `scritto` su ogni giocatore dell'istantanea."""
        from ..estensioni import macchina as mc
        for i, g in enumerate(ist["giocatori"]):
            nome = g["nome"]
            if g.get("fuori_forma") or mc.NOME_DEFAULT.match(nome) or nome in p.nomi_voce:
                g["detto"] = nome
                g.pop("scritto", None)
                continue
            g["scritto"] = True
            g["detto"] = nome if self._nome_dicibile(p, nome) else f"Giocatore {i + 1}"

    def _nome_dicibile(self, p: Partita, nome: str) -> bool:
        if p.prova:
            return False                     # una partita di prova non fa dire nomi scritti
        # Il giudizio vale per chi c'è nella partita: con un minore o un ospite arrivati dopo il
        # nome si rigiudica (con il guardiano)
        minore = any(x.minore for x in p.posti.values())
        chiave = (nome, p.protetta(), minore)
        ok = p.nomi_ok.get(chiave)
        if ok is not None:
            return ok
        from .. import riferire
        _detto, regole = riferire.controlla_testo(nome, "estensione")
        ok = not regole
        if ok and p.protetta():
            ok = self._guardiano(nome, domanda=False, minore=minore) == "ok"
        if len(p.nomi_ok) < 64:
            p.nomi_ok[chiave] = ok
        if not ok:
            self._registra(p, "nome_fermato", regola="gioco_nome_fermato")
        return ok

    def _t_rifiutato(self, p: Partita, posto: Posto, dati) -> dict:
        """Il motore ha rifiutato un comando a voce: era stato riconosciuto su un'istantanea
        che nel frattempo è cambiata (un tocco arrivato prima), o non vale più. Solo per il
        registro: lo stato resta quello del motore."""
        posto.rifiutati += 1
        motivo = str(dati.get("motivo") or "")[:20]
        self._registra(p, "comando_rifiutato", regola="gioco_comando_vecchio"
                       if motivo == "vecchio" else "gioco_comando_rifiutato",
                       comando=str(dati.get("comando") or "")[:24], motivo=motivo)
        return {"ok": True}

    def _t_chiuso(self, p: Partita, posto: Posto, dati) -> dict:
        """La pagina ha chiuso il gioco (✕, Esc, «chiudi il gioco»): niente più comandi a voce
        finché un riquadro nuovo non manda «pronto» («Riapri»)."""
        posto.aperto = False
        self._passa_la_partita(p, posto)
        if p.ascolta:
            self.sveglia_voce()
        return {"ok": True}

    def _t_palco(self, p: Partita, posto: Posto, dati) -> dict:
        """La diagnosi del palco (14/10, motore_gioco.js): ciò che sullo schermo vero esce dal
        palco o ha il testo tagliato, misurato dal motore dopo il disegno. Al più tre frasi
        brevi; [] = la pagina ci sta. Resta sul posto (per il collaudo e le prove) e, se ci sono
        difetti nuovi, nel registro e nel log. Non porta dati fuori dal riquadro: è una diagnosi."""
        lista = dati.get("difetti")
        if not isinstance(lista, list) or len(lista) > 3 or any(not isinstance(x, str)
                                                                for x in lista):
            return {"errore": "difetti: un elenco di al più tre frasi", "_stato": 400}
        difetti = [_pulisci(x, 300) for x in lista]
        nuovi = difetti and difetti != posto.palco
        posto.palco = difetti
        posto.palco_n += 1
        if nuovi:
            self._registra(p, "palco", regola="gioco_fuori_dal_palco", difetti=difetti)
            self.log(f"[GIOCHI] «{p.titolo}»: il disegno non sta nel palco: {difetti[0]}")
        return {"ok": True}

    def _t_gira(self, p: Partita, posto: Posto, dati) -> dict:
        """«Gira il telefono» (15/10, decisione 3 del 12/10): la tela del gioco ha un orientamento
        solo e il telefono è girato dall'altra parte. Lo schermo lo dice già (una fascia sopra il
        gioco, che non si ferma); qui Calliope lo dice a voce, una volta per schermo e partita,
        con una frase sua (niente testo del gioco), anche in una partita di prova."""
        o = dati.get("orientamento")
        if o not in FRASE_GIRA:
            return {"errore": "orientamento: orizzontale o verticale", "_stato": 400}
        if posto.gira_detto:
            return {"ok": True, "detto": False}
        posto.gira_detto = True
        self._registra(p, "gira", regola="gioco_gira_telefono", orientamento=o)
        self.frasi.put({"messaggio": FRASE_GIRA[o], "partita": p.id, "titolo": p.titolo,
                        "persona": posto.persona, "minore": False, "schermo": posto.sid,
                        "regola": "gioco_gira_telefono"})
        if self.on_frase is not None:
            try:
                self.on_frase()
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "detto": True}

    def _t_fine(self, p: Partita, posto: Posto, dati) -> dict:
        self._registra(p, "fine", giocatore=posto.giocatore)
        return {"ok": True}

    def _t_errore(self, p: Partita, posto: Posto, dati) -> dict:
        self.log(f"[GIOCHI] {p.titolo}: errore nel riquadro: "
                 f"{_pulisci(dati.get('testo'), 160)}")
        return {"ok": True}

    def _t_guasto(self, p: Partita, posto: Posto, dati) -> dict:
        """Il cane da guardia della pagina ha chiuso il riquadro (non risponde, troppi
        messaggi, ha provato a cambiare pagina): si segnala e resta scritto."""
        motivo = _pulisci(dati.get("motivo"), 80) or "guasto"
        self.guasti.append({"quando": time.time(), "gioco": p.nome, "motivo": motivo})
        # La scheda di quello schermo resta chiusa (anche dopo che la pagina si ricarica: un
        # riquadro bloccato non riparte da solo dalla cronologia)
        card = p.carte.get(posto.sid)
        if card is not None:
            nota = NOTE_GUASTO.get(motivo, "Il gioco si è chiuso.")
            p.carte[posto.sid] = chiusa = {**card, "stato": "chiuso", "nota": nota,
                                           "sposta": False}
            self.hub.invia_a(posto.sid, chiusa)
        posto.fermato = True
        posto.aperto = False
        self._passa_la_partita(p, posto)
        self._registra(p, "guasto", regola="gioco_chiuso_dal_controllo", motivo=motivo)
        self.log(f"[GIOCHI] «{p.titolo}» chiuso sullo schermo "
                 f"{self._nome_schermo(posto.sid)}: {motivo}")
        return {"ok": True}

    # ── i comandi a voce (11/10, calliope/gioco_voce.py) ──
    @staticmethod
    def _attivi(p: Partita, posto: Posto) -> list[str]:
        """I comandi a voce che valgono adesso: quelli dell'ultima istantanea valida (14/10),
        nell'ordine del manifesto; nessuno senza istantanea."""
        a = p.ascolta
        ist = p.tiene(posto).istantanea
        if a is None or ist is None:
            return []
        scelti = set(ist["comandi"])
        return [c for c in a["comandi"] if c in scelti]

    def aggiungi_sveglia(self, ev):
        """La sveglia di un ciclo della voce (Ciclo.__init__)."""
        with self._lock:
            if ev not in self._sveglie:
                self._sveglie.append(ev)

    def sveglia_voce(self):
        for ev in list(self._sveglie):
            try:
                ev.set()
            except Exception:  # noqa: BLE001
                pass

    def schermi_voce(self, coll=None) -> list:
        """Gli schermi del satellite che ascolta, per i comandi a voce: il suo schermo, se ne ha
        uno (la pagina del PC, il telefono); se no quelli della sua stanza che non sono di un
        altro satellite (un satellite senza schermo accanto alla TV). Senza satellite (l'audio
        di questo computer) quelli della stanza predefinita, o quelli di nessun satellite."""
        hub = self.hub
        sid = getattr(coll, "schermo_id", None) if coll is not None else None
        if sid is not None:
            return [sid]
        try:
            righe = hub.abbinati()
        except Exception:  # noqa: BLE001
            return []
        sat = getattr(hub, "satelliti", None)

        def di_un_satellite(x) -> bool:
            try:
                c = sat.per_schermo(x.get("id")) if sat is not None else None
            except Exception:  # noqa: BLE001
                c = None
            return c is not None and c is not coll
        if coll is not None:
            stanza = getattr(coll, "stanza", None) or ""
            if not stanza:
                return []
        else:
            stanza = getattr(hub, "stanza_predefinita", None) or ""
        from .archivio import norm_stanza
        st = norm_stanza(stanza) if stanza else ""
        return [x.get("id") for x in righe
                if (not st or x.get("stanza") == st) and not di_un_satellite(x)]

    def ascolto(self, schermi) -> dict | None:
        """Il gioco aperto su uno di questi schermi che aspetta un comando a voce (comandi
        attivi non vuoti), il più recente: {partita, schermo, titolo, comandi: {id: forme}
        (solo gli attivi), giocatore, segno (monotonic dell'ultima mossa o apertura), prova}.
        None se nessuno."""
        ids = {x for x in (schermi or []) if x is not None}
        if not ids:
            return None
        ora = time.time()
        migliore = None
        with self._lock:
            for p in self.partite.values():
                if p.ascolta is None:
                    continue
                for sid, posto in p.posti.items():
                    if sid not in ids or not posto.aperto or posto.fermato \
                            or ora - posto.contatto > VIVO_S:
                        continue
                    attivi = self._attivi(p, posto)
                    if attivi and (migliore is None or posto.contatto > migliore[1].contatto):
                        migliore = (p, posto, attivi)
        if migliore is None:
            return None
        p, posto, attivi = migliore
        a = p.ascolta
        return {"partita": p.id, "schermo": posto.sid, "titolo": p.titolo,
                "comandi": {c: list(a["comandi"][c]) for c in attivi},
                "giocatore": bool(a.get("giocatore")), "segno": posto.segno,
                "prova": p.prova,
                "istantanea": json.loads(json.dumps(p.tiene(posto).istantanea)),
                "macchina": p.macchina,
                # Chi è quale giocatore (15/10): quanti possono giocare, il numero di questo
                # schermo, i nomi degli altri schermi della partita e i segni delle voci (per
                # «tocca a te» e «quanti punti ho?»: restano dentro Calliope)
                "massimo": p.massimo, "posto": posto.giocatore,
                "schermi": {x.giocatore: (self.hub.schermo(x.sid) or {}).get("nome") or ""
                            for x in p.posti.values() if x.giocatore},
                "voci": dict(p.voci)}

    def turno_altrui(self, partita: str, schermo, comando: str,
                     persona: str | None = None) -> str | None:
        """Chi è quale giocatore (15/10): la frase da dire se il comando a voce non vale per chi
        l'ha detto («Tocca ad Ada.», «Tocca ad Ada, sullo schermo della cucina.», «Sei già nella
        partita: sei Ada.»), None se vale. Lo stesso criterio del motore (macchina.chi_muove)
        sull'ultima istantanea valida: la voce di un altro giocatore, o lo schermo di un altro
        giocatore quando la voce non è riconosciuta. Il motore lo ricontrolla comunque."""
        from .. import gioco_stato
        from ..estensioni import macchina as mc
        with self._lock:
            p = self.partite.get(str(partita or ""))
            posto = p.posti.get(schermo) if p is not None else None
            if p is None or posto is None or p.macchina is None:
                return None
            t = p.tiene(posto)
            ist = t.istantanea
            if ist is None:
                return None
            voce = p.voce_di(persona, crea=False)
            ok, motivo, i = mc.chi_muove(ist, p.macchina, comando, posto.giocatore, voce)
            if ok or i is None:
                return None
            nomi = gioco_stato.nomi_detti(ist)
            nome = nomi[i] if 0 <= i < len(nomi) else f"Giocatore {i + 1}"
            altro = None
            sch = (ist["giocatori"][i] or {}).get("schermo")
            if motivo != "gia" and sch and sch != posto.giocatore:
                altro = next((x for x in p.posti.values() if x.giocatore == sch), False)
        # il nome dello schermo dall'hub, fuori dal lock dei giochi
        dove = ""
        if altro is not None:
            n_s = (self.hub.schermo(altro.sid) or {}).get("nome") if altro else None
            dove = f", sullo schermo {self._di(n_s)}" if n_s else ", sull'altro schermo"
        self._registra(p, "turno_altrui", regola="gioco_turno_altrui", motivo=motivo,
                       comando=str(comando)[:24])
        if motivo == "gia":
            return f"Sei già nella partita: sei {nome}."
        return f"Tocca {gioco_stato._a(nome)}{dove}."

    def in_corso(self, schermi) -> bool:
        """Un gioco è aperto e si vede adesso su uno di questi schermi (riquadro aperto da
        «pronto» a «chiuso», non fermato, la pagina viva da al più VIVO_S), con o senza comandi
        a voce, anche una partita di prova. Per il guardiano a posteriori della stanza (14/10,
        stanza/guardia.py): le righe dette mentre si gioca si giudicano col contesto «gioco»
        dichiarato."""
        ids = {x for x in (schermi or []) if x is not None}
        if not ids:
            return False
        ora = time.time()
        with self._lock:
            for p in self.partite.values():
                for sid, posto in p.posti.items():
                    if (sid in ids and posto.aperto and not posto.fermato
                            and ora - posto.contatto <= VIVO_S):
                        return True
        return False

    def comando(self, partita: str, schermo, comando: str, giocatore: str | None = None,
                dalla_voce: bool = True) -> bool:
        """Manda una mossa a voce al riquadro della partita su quello schermo (evento «gioco»
        di tipo «comando»). Solo un comando attivo di quel gioco; il nome di chi gioca solo se
        il manifesto lo chiede. `dalla_voce`: il nome è di chi è riconosciuto dalla voce (si
        dice senza altri controlli); False per un nome detto a parole («gioco anch'io, sono
        Pippo»), che vale come uno scritto. True se mandata."""
        with self._lock:
            p = self.partite.get(str(partita or ""))
            posto = p.posti.get(schermo) if p is not None else None
            if p is None or posto is None or not posto.aperto or posto.fermato:
                return False
            a = p.ascolta
            if a is None or comando not in self._attivi(p, posto):
                return False
            # Il numero dell'istantanea su cui il comando è stato riconosciuto (14/10): se nel
            # frattempo il motore ne ha fatta un'altra (un tocco arrivato prima), lo rifiuta. In
            # una partita condivisa la mossa va al motore che la tiene, anche se l'ha sentita lo
            # schermo di uno specchio
            t = p.tiene(posto)
            if t.istantanea is None or not t.aperto or t.fermato:
                return False
            dati = {"comando": comando, "n": t.istantanea["n"]}
            if giocatore and a.get("giocatore"):
                dati["giocatore"] = str(giocatore)[:40]
                if dalla_voce and len(p.nomi_voce) < 64:
                    p.nomi_voce.add(dati["giocatore"])
            # Chi è quale giocatore (15/10): il segno della voce riconosciuta (mai il nome, se il
            # manifesto non lo chiede) in un gioco per più giocatori, e, in una partita tra più
            # schermi, il numero dello schermo che l'ha sentita
            if giocatore and dalla_voce and p.massimo > 1:
                v = p.voce_di(str(giocatore)[:40])
                if v:
                    dati["voce"] = v
            if p.motore_condiviso and posto.giocatore:
                dati["schermo"] = posto.giocatore
            posto.segno = t.segno = time.monotonic()
            p.ultimo = time.time()
        self.hub.evento_a(t.sid, "gioco", {"partita": p.id, "tipo": "comando", "dati": dati})
        return True

    # ── utilità ──
    def _profilo(self, pid):
        from ..minori import _per_id
        return _per_id(getattr(getattr(self.estensioni, "tool_ctx", None), "speakers", None)
                       or getattr(self, "speakers", None), pid)

    def _agli_altri(self, p: Partita, da: Posto, tipo: str, dati: dict):
        for sid, posto in list(p.posti.items()):
            if sid != da.sid and not posto.fermato:
                self.hub.evento_a(sid, "gioco", {"partita": p.id, "tipo": tipo, "dati": dati})

    def manda_a(self, p: Partita, posto: Posto, tipo: str, dati: dict):
        self.hub.evento_a(posto.sid, "gioco", {"partita": p.id, "tipo": tipo, "dati": dati})

    def _guardiano(self, testo: str, domanda: bool, minore: bool) -> str:
        """ok | vietato | pericolo | guasto. Senza guardiano: per un minore si blocca (come
        guardiano_se_guasto), per un ospite passa."""
        g = self.guardiano
        se_guasto = "ok" if not minore or str(getattr(self.cfg, "guardiano_se_guasto",
                                                      "blocca")) != "blocca" else "guasto"
        if g is None:
            return se_guasto
        try:
            from .. import guardiano as gd
            att = None if minore else set(getattr(gd, "MODERATO", ()) or ()) or None
            r = (g.giudica_domanda(testo, att) if domanda else
                 g.giudica("(frase di un gioco)", testo, att))
        except Exception:  # noqa: BLE001
            return se_guasto
        if r.esito == "ok":
            return "ok"
        if r.esito == "guasto":
            return se_guasto
        return r.esito

    def _avviso_pericolo(self, posto: Posto):
        from .. import minori
        prof = self._profilo(posto.persona)
        av = minori.avvisi()
        if prof is None or av is None:
            return
        try:
            av.manda(prof, "sicurezza", f"{prof.name} ha scritto nella chat di un gioco una cosa "
                                        f"che mi preoccupa. Parlagli appena puoi, con calma.",
                     urgente=True, origine="da una frase scritta nella chat di un gioco")
        except Exception:  # noqa: BLE001
            pass

    def _registra(self, p: Partita, evento: str, **extra):
        est = self.estensioni
        if est is not None:
            est.archivio.registra({"gioco": p.nome, "versione": p.versione, "partita": p.id,
                                   "evento": evento, **extra})
        regola = extra.get("regola")
        if regola:
            est_nota = getattr(est, "nota_regola", None)
            if est_nota is not None:
                for r in str(regola).split(","):
                    est_nota(r)

    def pulisci(self):
        """Le partite senza segni da più di `giochi_partita_ore`: il loro indirizzo non vale
        più."""
        ore = self._c("giochi_partita_ore", 6.0)
        limite = time.time() - ore * 3600
        with self._lock:
            for pid in [k for k, v in self.partite.items() if v.ultimo < limite]:
                p = self.partite.pop(pid)
                self._per_gettone.pop(p.gettone, None)

    def chiudi_di(self, nome: str) -> list[str]:
        """Le partite di un gioco eliminato (09/10, estensione_gestisci rimuovi): finite, il
        loro indirizzo non vale più. Gli id, per togliere le loro schede."""
        with self._lock:
            pids = [k for k, v in self.partite.items() if v.nome == nome]
            for pid in pids:
                p = self.partite.pop(pid)
                self._per_gettone.pop(p.gettone, None)
            self._documenti = {k: v for k, v in self._documenti.items() if k[0] != nome}
        return pids

    def stato(self) -> dict:
        with self._lock:
            return {"partite": len(self.partite), "guasti_recenti": len(
                [g for g in self.guasti if time.time() - g["quando"] < 3600])}


def _solo_valori_brevi(v, profondita: int = 0) -> bool:
    if profondita > 6:
        return False
    if isinstance(v, str):
        return bool(_VALORE_BREVE.match(v))
    if isinstance(v, (int, float, bool)) or v is None:
        return True
    if isinstance(v, list):
        return len(v) <= 100 and all(_solo_valori_brevi(x, profondita + 1) for x in v)
    if isinstance(v, dict):
        return len(v) <= 50 and all(_VALORE_BREVE.match(str(k)) and
                                    _solo_valori_brevi(x, profondita + 1) for k, x in v.items())
    return False


def _pulisci(testo, massimo: int) -> str:
    t = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f​-‏‪-‮]", " ",
                                   str(testo or ""))).strip()
    return t[:massimo]


class AzioneGioco:
    """Una richiesta del riquadro alla porta stretta (estensioni/porta.py), con la stessa
    interfaccia di un'esecuzione (estensioni/esecuzione.py) per la porta e per il «sì» della
    persona (estensione_gestisci consenti/nega). La contaminazione è della partita: un gioco
    che ha letto l'agenda non manda più messaggi agli altri schermi."""

    def __init__(self, giochi: Giochi, p: Partita, posto: Posto, azione: str, params: dict,
                 rif):
        from ..guardrail import StatoEsecuzione
        est = giochi.estensioni
        with est._lock:
            est._n += 1
            self.id = f"G{est._n}"
        self.giochi, self.partita, self.posto = giochi, p, posto
        self.azione, self.params, self.rif = azione, dict(params or {}), rif
        self.nome, self.versione, self.manifesto = p.nome, p.versione, p.manifesto
        self.persona, self.persona_nome = posto.persona, posto.nome
        self.livello = min(posto.livello, "familiare", key=lambda x: RANK.get(x, 0))
        self.storia = StatoEsecuzione()
        if p.contaminazione:
            self.storia.contamina(*p.contaminazione)
        self.decisioni: list = []
        self.mittente = Mittente(persona=posto.persona, nome=posto.nome, livello=self.livello,
                                 certo=bool(posto.persona), schermo=posto.sid)
        self.stato = "in_corso"
        self.richiesta = None
        self.risultato = None
        self.errore = ""
        self.tempo_s = 0.0
        self.da_annunciare = False
        self._cambio = threading.Condition()
        self._decisione = None

    def avvia(self) -> dict:
        est = self.giochi.estensioni
        porta = est.porta
        esito = porta.gestisci(self, self.azione, self.params)
        if not esito.get("conferma"):
            self._fine(esito)
            return self._per_pagina(esito)
        # Pericolosa: si chiede a voce (come un'estensione sospesa), la risposta arriva dopo
        with self._cambio:
            self.richiesta = {"azione": self.azione, "argomenti": self.params, **esito}
            self.stato = "in_attesa"
        with est._lock:
            est.esecuzioni[self.id] = self
        q = est._domanda(est.tool_ctx, self)
        est.done.put({"id": self.id, "estensione": self.nome, "chi": self.persona,
                      "chi_nome": self.persona_nome, "stato": "in_attesa",
                      "messaggio": q["risposta_finale"], "in_sospeso": q["in_sospeso"]})
        if est.on_done:
            est.on_done()
        threading.Thread(target=self._aspetta, args=(esito,), daemon=True,
                         name=f"gioco-azione-{self.id}").start()
        return {"ok": True, "in_attesa": True, "domanda": esito.get("domanda")}

    def _aspetta(self, esito: dict):
        est = self.giochi.estensioni
        fine = time.monotonic() + float(getattr(est, "conferma_s", 120.0))
        with self._cambio:
            while self._decisione is None and self.stato == "in_attesa":
                resto = fine - time.monotonic()
                if resto <= 0:
                    break
                self._cambio.wait(resto)
            dec = self._decisione
        out = est.porta.dopo_conferma(self, self.azione, self.params, esito, dec)
        self._fine(out)
        r = self._per_pagina(out)
        self.giochi.manda_a(self.partita, self.posto, "risposta",
                            {"rif": self.rif, **{k: v for k, v in r.items() if k != "_stato"}})

    def _fine(self, out: dict):
        self.partita.contaminazione |= set(self.storia.contaminazione)
        with self._cambio:
            if "errore" in out:
                self.stato, self.errore = "errore", str(out["errore"])[:300]
            else:
                self.stato = "finita"
                self.risultato = {"da_dire": ""}
            self._cambio.notify_all()

    @staticmethod
    def _per_pagina(out: dict) -> dict:
        if "errore" in out:
            return {"ok": False, "errore": str(out["errore"])[:300]}
        ris = out.get("risultato")
        return {"ok": True, "valore": ris}

    # ── come Esecuzione, per estensione_gestisci consenti/nega ──
    def attendi(self, timeout: float) -> str:
        fine = time.monotonic() + timeout
        with self._cambio:
            while self.stato == "in_corso":
                resto = fine - time.monotonic()
                if resto <= 0:
                    break
                self._cambio.wait(resto)
            return self.stato

    def decidi(self, si: bool, chi=None, sempre: bool = False) -> bool:
        with self._cambio:
            if self.stato != "in_attesa" or self.richiesta is None:
                return False
            self._decisione = {"si": bool(si), "chi": chi, "sempre": bool(sempre)}
            self.stato = "in_corso"
            self.richiesta = None
            self._cambio.notify_all()
            return True

    def annulla(self):
        with self._cambio:
            if self.stato in ("in_corso", "in_attesa"):
                self.stato = "negata"
                self.errore = "annullata"
                self._cambio.notify_all()
