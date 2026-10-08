"""
Lo smistamento delle schede: quali schermi, quale stanza, quale livello.

Una scheda con la stessa `chiave` di una già nella cronologia (lo stesso timer, documento,
lista) la sostituisce invece di aggiungersi (schede.py, «Identità»).

`Schermi.invia(scheda, mittente)` si chiama dal thread dei tool (o da quello dei documenti
in secondo piano) e **non aspetta mai**: sceglie gli schermi, mette la scheda nella loro
cronologia e la passa al ciclo asyncio del server con `call_soon_threadsafe` +
`put_nowait`. Se uno schermo è lento o spento la scheda si perde per lui (resta nella
cronologia e arriva quando si ricollega); la voce non cambia.

Chi riceve (docs/ricerche/2026-10-01-mappe-e-schermi.md, §10.4):
  - `pubblica`: ogni schermo della stanza, anche per gli ospiti;
  - `casa`: gli schermi della stanza, solo se chi parla è riconosciuto (familiare o chi
    amministra);
  - `personale`: solo gli schermi personali di chi parla (di qualunque stanza: sono suoi),
    e solo se l'identità è certa (non la zona grigia del riconoscimento: lì il livello si
    ferma a familiare e il personale non si mostra, come per i PC).
La stanza: quella del satellite che ha sentito la frase (domani); oggi c'è un microfono
solo, quindi `schermi_stanza` della configurazione, e vuota = tutti gli schermi abbinati.

Lo stato della voce (02/10, `Schermi.voce`): addormentata, in ascolto (con la fine della
finestra di follow-up), sta pensando, sta parlando. Va solo agli schermi del microfono che
ascolta: con un satellite quelli della sua stanza, con l'audio locale quelli di
`schermi_stanza` o, se è vuota, quelli aperti su questo computer (127.0.0.1). È pubblico:
nessun nome, nessun dato di chi parla.

Questo modulo non importa Starlette: lo usano anche le prove e i tool senza server.
"""

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass

from . import conversazione as conv_mod
from .archivio import ArchivioSchermi, norm_stanza
from .conversazione import Conversazioni
from .moduli import Ingresso, Moduli
from .scarica import Scaricamenti
from .schede import CASA, PERSONALE, PUBBLICA

# Coda per connessione: oltre, le schede vecchie di uno schermo lento si scartano
CODA_MAX = 32
# Stati della voce mostrati sugli schermi (Schermi.voce)
VOCE_STATI = ("dorme", "ascolta", "pensa", "parla")


@dataclass
class Mittente:
    """Chi ha chiesto (o provocato) la scheda, e da dove."""
    persona: str | None = None    # UserProfile.id
    nome: str | None = None
    livello: str = "ospite"       # ospite | familiare | amministra
    certo: bool = False           # identità decisa dalla voce, non dalla zona grigia
    stanza: str | None = None     # stanza del microfono (satelliti: domani)
    # Lo schermo da cui arriva la richiesta (04/10, «rispondi dove ti ho chiesto»): quello
    # del satellite che ha sentito la frase, o quello dove è stata scritta. Riceve per primo
    schermo: int | None = None

    @property
    def chiave(self) -> str:
        return self.persona or "ospite"


def mittente_da(ctx, stanza: str | None = None) -> Mittente:
    """Il mittente dal contesto dei tool (SpeakerContext e registro delle voci)."""
    sc = getattr(ctx, "speaker_ctx", None)
    name = getattr(sc, "current_speaker", None)
    speakers = getattr(ctx, "speakers", None)
    prof = speakers.get(name) if (name and speakers) else None
    level = getattr(sc, "current_level", "ospite") or "ospite"
    # Zona grigia: identità confermata solo dalla conversazione (speaker_id.py)
    certo = bool(prof) and not getattr(sc, "from_session", False)
    return Mittente(persona=getattr(prof, "id", None), nome=getattr(prof, "name", name),
                    livello=level if prof else "ospite", certo=certo, stanza=stanza)


def destinatari(visibilita: str, mittente: Mittente, schermi: list[dict],
                stanza: str | None) -> tuple[list[dict], str]:
    """Gli schermi che possono ricevere la scheda e, se nessuno, il motivo:
    «nessuno_schermo», «ospite» (la scheda è della casa o personale), «personale» (nessuno
    schermo personale di chi parla), «zona_grigia», «stanza» (nessuno schermo qui).
    Dal 04/10 lo schermo da cui arriva la richiesta (`mittente.schermo`) viene per primo, e
    c'è anche se è in un'altra stanza, purché la visibilità lo permetta (una scheda
    personale solo se è suo); poi gli altri, come prima."""
    dest, motivo = _destinatari(visibilita, mittente, schermi, stanza)
    sid = mittente.schermo
    if sid is None or (visibilita == PERSONALE and motivo in ("ospite", "zona_grigia")):
        return dest, motivo
    if visibilita == CASA and motivo == "ospite":
        return dest, motivo
    origine = next((s for s in schermi if s.get("id") == sid), None)
    if origine is None or visibilita not in (PUBBLICA, CASA, PERSONALE):
        return dest, motivo
    if visibilita == PERSONALE and origine.get("proprietario") != mittente.persona:
        return dest, motivo
    return [origine] + [s for s in dest if s.get("id") != sid], ""


def _destinatari(visibilita: str, mittente: Mittente, schermi: list[dict],
                 stanza: str | None) -> tuple[list[dict], str]:
    if not schermi:
        return [], "nessuno_schermo"
    famiglia = mittente.livello in ("familiare", "amministra") and mittente.persona
    if visibilita == PERSONALE:
        if not famiglia:
            return [], "ospite"
        if not mittente.certo:
            return [], "zona_grigia"
        mine = [s for s in schermi if s.get("proprietario") == mittente.persona]
        return (mine, "") if mine else ([], "personale")
    if visibilita == CASA and not famiglia:
        return [], "ospite"
    if visibilita not in (PUBBLICA, CASA):
        return [], "visibilita"
    stanza = norm_stanza(stanza) if stanza else ""
    qui = [s for s in schermi if not stanza or s.get("stanza") == stanza]
    return (qui, "") if qui else ([], "stanza")


def pubblica(scheda: dict) -> dict:
    """La scheda come va alle pagine e nella cronologia: senza le chiavi che cominciano con
    «_» (07/10: `_scarica`, la sorgente intera del documento, resta sul server)."""
    if not any(str(k).startswith("_") for k in scheda):
        return scheda
    return {k: v for k, v in scheda.items() if not str(k).startswith("_")}


class _Connessione:
    def __init__(self, schermo: dict, loop: asyncio.AbstractEventLoop, locale: bool = False):
        self.schermo = schermo
        self.loop = loop
        self.locale = locale                # pagina aperta su questo computer (127.0.0.1)
        self.coda: asyncio.Queue = asyncio.Queue(maxsize=CODA_MAX)
        self.persi = 0
        self.scrittura = None               # ultimo stato dello scritto mandato a questa pagina

    def _metti(self, item):                 # nel ciclo del server
        try:
            self.coda.put_nowait(item)
        except asyncio.QueueFull:
            self.persi += 1

    def consegna(self, item) -> bool:       # da qualunque thread
        try:
            self.loop.call_soon_threadsafe(self._metti, item)
            return True
        except RuntimeError:                # ciclo chiuso
            return False


class Schermi:
    """Il registro vivo degli schermi: abbinati (archivio), collegati (connessioni SSE),
    cronologia per schermo, ultima scheda per persona."""

    def __init__(self, cfg, archivio: ArchivioSchermi, log=print):
        self.cfg = cfg
        self.archivio = archivio
        self.log = log
        self._lock = threading.RLock()
        self._conn: dict[int, list[_Connessione]] = {}
        self._storia: dict[int, deque] = {}
        self._ultime: dict[str, dict] = {}
        self._cache: tuple[float, int, list[dict]] = (0.0, -1, [])
        self.url = ""                       # lo imposta il server quando parte
        # Il certificato della pagina, se è in HTTPS (schermi/tls.py): lo SPKI va al
        # satellite, che apre la pagina fidandosi solo di lui
        self.tls: dict | None = None
        self.inviate = 0
        self.server_attivo = False
        # Funzione senza argomenti → la stanza del satellite che ascolta (main.py con
        # audio_modo: satellite), o None: allora vale schermi_stanza
        self.stanza_corrente = None
        # Il server dei satelliti (main.py con audio_modo: satellite): il telefono entra da
        # qui con il loro protocollo (telefono.py), e «questo schermo è mio» detto a voce vale
        # per lo schermo del satellite da cui si parla (tools/schermi.py, 03/10). None = senza satelliti
        self.satelliti = None
        # Funzione senza argomenti → {"schermo", "stanza"} da cui arriva la richiesta del turno
        # (calliope/rispondi.py, 04/10), o None: allora vale `stanza_corrente`
        self.origine_corrente = None
        # Proposte di schermo_gestisci personale/condiviso: {persona: {...}}, valide nella
        # risposta dopo (come le installazioni)
        self.proposte: dict = {}
        # Stato della voce per stanza (06/10, P9: con più corsie lo studio che pensa e la
        # cucina che dorme si sovrascrivevano): chiave → {"stato", "fino"} (fino: istante in
        # secondi epoch in cui la finestra di follow-up scade, o None). La chiave è la stanza
        # (normalizzata), "" per le pagine di questo computer, None se nessuno schermo la
        # mostra. Un thread solo, avviato al primo «ascolta» con una scadenza, riporta a
        # «dorme» le stanze la cui finestra finisce
        self._voce: dict = {}
        # Lo stato di ogni sorgente (06/10, Q9: due satelliti nella stessa stanza): chiave →
        # {sorgente: {"stato", "fino"}}; `_voce` è la loro unione (parla > pensa > ascolta >
        # dorme). Prima vinceva chi scriveva per ultimo: una corsia che scartava una frase
        # riportava «dorme» mentre l'altra parlava. Sorgente None = il microfono che ascolta
        self._voce_src: dict = {}
        self._voce_cond = threading.Condition(self._lock)
        self._voce_thread = None
        # Scrivere invece di parlare (03/10, moduli.py): i moduli aperti sugli schermi personali
        # e la coda di ciò che arriva dalle pagine (testo scritto, moduli inviati) per il ciclo
        # principale, che la sveglia (ingresso.sveglia) fa guardare tra un turno e l'altro
        self.moduli = Moduli(self)
        self.ingresso = Ingresso()
        # Scrivere solo durante una conversazione cominciata a voce (05/10, conversazione.py):
        # il ciclo principale le aggiorna, le pagine si accendono e spengono da sole
        self.conversazioni = Conversazioni(lambda: conv_mod.durata(self.cfg),
                                           on_cambio=self._scrittura_cambiata)
        self._scrittura_persone: set = set()
        # Chi vuole sapere quando la conversazione di una persona finisce (main.py: le foto
        # in attesa della domanda decadono): funzioni con l'id della persona
        self.su_fine_conversazione: list = []
        # turns.write di main.py: i rifiuti dello scritto (dal thread del server) nel registro
        self.registro_turni = None
        # Uso del contesto dell'ultima risposta per persona (05/10, calliope/contesto.py): la
        # barra discreta degli schermi personali, rimandata quando una pagina si ricollega
        self._contesto: dict[str, dict] = {}
        # I giochi delle estensioni (05/10, giochi.py): lo imposta main.py con le estensioni
        self.giochi = None
        # Gli esercizi (08/10, calliope/esercizi/sessione.py): la scheda risponde da
        # /api/esercizio; lo imposta main.py
        self.esercizi = None
        # Il cruscotto di chi amministra (06/10, cruscotto.py: sola lettura), da main.py;
        # None = niente pulsante e /api/cruscotto risponde 404
        self.cruscotto = None
        # «Scarica» nella scheda del documento (07/10, scarica.py): le schede scaricabili
        # arrivate a ogni schermo personale e i gettoni degli indirizzi
        self.scaricamenti = Scaricamenti(cfg)
        # Il cassetto dei file per persona (08/10, calliope/cassetto.py), da main.py: None =
        # /api/cassetto risponde 404
        self.cassetto = None

    # ── configurazione ──
    @property
    def automatiche(self) -> bool:
        return bool(getattr(self.cfg, "schermi_automatiche", True))

    @property
    def stanza_predefinita(self) -> str:
        return norm_stanza(getattr(self.cfg, "schermi_stanza", "") or "")

    def mittente(self, ctx) -> Mittente:
        stanza = None
        if self.stanza_corrente is not None:
            try:
                stanza = self.stanza_corrente()
            except Exception:  # noqa: BLE001 — la scheda non deve rompere il tool
                stanza = None
        m = mittente_da(ctx, stanza=stanza)
        # Da dove arriva la richiesta (calliope/rispondi.py): schermo e stanza dell'origine
        if self.origine_corrente is not None:
            try:
                o = self.origine_corrente() or {}
            except Exception:  # noqa: BLE001
                o = {}
            if o.get("schermo") is not None:
                m.schermo = o["schermo"]
            if o.get("stanza"):
                m.stanza = o["stanza"]
        return m

    # ── abbinati ──
    def abbinati(self) -> list[dict]:
        """Gli schermi abbinati, con una cache breve: il comando da terminale può abbinare
        o revocare mentre Calliope è accesa (stesso file)."""
        t, ver, rows = self._cache
        if ver == self.archivio.versione and time.monotonic() - t < 5.0:
            return rows
        rows = self.archivio.elenco()
        self._cache = (time.monotonic(), self.archivio.versione, rows)
        return rows

    def _rinfresca(self):
        self._cache = (0.0, -1, [])

    def collegati(self) -> list[dict]:
        with self._lock:
            return [c[0].schermo for c in self._conn.values() if c]

    def valido(self, sid: int) -> bool:
        return any(s["id"] == sid for s in self.abbinati())

    # ── connessioni (dal server) ──
    def collega(self, schermo: dict, loop, locale: bool = False
                ) -> tuple[_Connessione, list[dict]]:
        """Nuova connessione SSE: la sua coda e la cronologia da mostrare subito. `locale`:
        la pagina è aperta su questo computer (per lo stato della voce con l'audio locale)."""
        conn = _Connessione(schermo, loop, locale)
        with self._lock:
            self._conn.setdefault(schermo["id"], []).append(conn)
            storia = list(self._storia.get(schermo["id"], ()))
        return conn, storia

    def scollega(self, conn: _Connessione):
        with self._lock:
            lst = self._conn.get(conn.schermo["id"], [])
            if conn in lst:
                lst.remove(conn)
            if not lst:
                self._conn.pop(conn.schermo["id"], None)

    # ── invio ──
    def ricorda(self, scheda: dict, mittente: Mittente):
        """L'ultima scheda della persona, per «mostramelo sullo schermo» (anche se in quel
        momento non è andata su nessuno schermo)."""
        if scheda.get("tipo") != "vuota":
            with self._lock:
                prima = self._ultime.get(mittente.chiave)
                # Un aggiornamento automatico (l'avanzamento di un lavoro) non diventa «l'ultima
                # cosa mostrata» al posto di un calcolo detto dopo: aggiorna solo sé stessa
                if scheda.get("sposta") is False and scheda.get("chiave") and                         (prima or {}).get("chiave") != scheda["chiave"] and prima is not None:
                    return
                self._ultime[mittente.chiave] = scheda

    def ultima(self, mittente: Mittente) -> dict | None:
        with self._lock:
            return self._ultime.get(mittente.chiave)

    def invia(self, scheda: dict, mittente: Mittente, forza: bool = False) -> dict:
        """Manda la scheda agli schermi giusti. Non blocca. {"schermi": [nomi raggiunti
        ora], "destinatari": [nomi], "motivo": perché nessuno, "abbinati": n}."""
        t0 = time.perf_counter()
        self.ricorda(scheda, mittente)
        if not forza and not self.automatiche:
            return {"schermi": [], "destinatari": [], "motivo": "automatiche_spente",
                    "abbinati": len(self.abbinati())}
        tutti = self.abbinati()
        stanza = mittente.stanza or self.stanza_predefinita or None
        dest, motivo = destinatari(scheda.get("visibilita", PERSONALE), mittente, tutti, stanza)
        pub = pubblica(scheda)
        msg = json.dumps(pub, ensure_ascii=False, default=str)
        raggiunti = []
        # «Scarica» (07/10): solo gli schermi personali di chi parla, con l'identità decisa
        # dalla voce (mai la zona grigia: lì una scheda personale non parte comunque)
        scaricabile = ("_scarica" in scheda and scheda.get("visibilita") == PERSONALE
                       and mittente.certo and mittente.persona)
        with self._lock:
            for s in dest:
                self._in_storia(s["id"], pub)
                if scaricabile and s.get("proprietario") == mittente.persona:
                    self.scaricamenti.registra(s["id"], scheda, mittente.persona)
                for c in self._conn.get(s["id"], []):
                    if c.consegna(("scheda", msg)):
                        raggiunti.append(s["nome"])
        self.inviate += bool(raggiunti)
        return {"schermi": list(dict.fromkeys(raggiunti)),
                "destinatari": [s["nome"] for s in dest], "motivo": motivo,
                "abbinati": len(tutti), "ms": round((time.perf_counter() - t0) * 1000, 2)}

    def invia_a(self, sid: int, scheda: dict) -> bool:
        """La scheda a uno schermo preciso, senza scegliere i destinatari: la risposta a una
        frase scritta torna sullo schermo da cui è arrivata (04/10). True se una sua pagina è
        collegata (altrimenti resta nella sua cronologia)."""
        if not self.valido(sid):
            return False
        pub = pubblica(scheda)
        msg = json.dumps(pub, ensure_ascii=False, default=str)
        ok = False
        if "_scarica" in scheda:
            # Lo schermo da cui è stata scritta la richiesta: il suo proprietario (se è personale)
            s = self.schermo(sid) or {}
            if s.get("proprietario"):
                self.scaricamenti.registra(sid, scheda, s["proprietario"])
        with self._lock:
            self._in_storia(sid, pub)
            for c in self._conn.get(sid, []):
                ok = c.consegna(("scheda", msg)) or ok
        return ok

    def evento_a(self, sid: int, tipo: str, dati: dict) -> int:
        """Un evento SSE a tutte le pagine aperte di uno schermo (05/10: i messaggi dei giochi
        verso il loro riquadro). Non entra nella cronologia; non blocca. Quante pagine."""
        msg = json.dumps(dati, ensure_ascii=False, default=str)
        n = 0
        with self._lock:
            for c in self._conn.get(sid, []):
                n += c.consegna((tipo, msg))
        return n

    def schermo(self, sid) -> dict | None:
        return next((s for s in self.abbinati() if s["id"] == sid), None)

    def collegato(self, sid, locale: bool | None = None) -> bool:
        """Lo schermo ha una pagina aperta (con `locale`: aperta su questo computer)."""
        with self._lock:
            return any(locale is None or c.locale == locale for c in self._conn.get(sid, []))

    def _in_storia(self, sid: int, scheda: dict):
        """La scheda nella cronologia dello schermo (con il lock). Con una `chiave` già
        presente la sostituisce: in cima (di norma: è cambiata per un'azione o un evento) o
        al suo posto (`sposta: false`, aggiornamento automatico). Niente doppioni, anche
        nella cronologia rimandata quando la pagina si ricollega."""
        n = max(1, int(getattr(self.cfg, "schermi_cronologia", 6)))
        h = list(self._storia.get(sid, ()))
        k = scheda.get("chiave")
        if k:
            i = next((j for j, x in enumerate(h) if x.get("chiave") == k), None)
            if i is not None and scheda.get("sposta") is False:
                h[i] = scheda
                self._storia[sid] = deque(h, maxlen=n)
                return
            h = [x for x in h if x.get("chiave") != k]
        h.append(scheda)
        self._storia[sid] = deque(h, maxlen=n)

    def storia(self, sid: int) -> list[dict]:
        with self._lock:
            return list(self._storia.get(sid, ()))

    # ── stato della voce ──
    _DORME = {"stato": "dorme", "fino": None}

    def _chiave_voce(self, stanza) -> str | None:
        """La stanza a cui va lo stato della voce (chiamare con il lock): quella data (la
        corsia di un satellite), altrimenti quella del microfono che ascolta: il satellite
        attivo, `schermi_stanza`, o "" (le pagine aperte su questo computer). None: nessuno
        schermo."""
        if stanza:
            return norm_stanza(stanza)
        if self.stanza_corrente is not None:             # satellite: la sua stanza
            try:
                s = self.stanza_corrente()
            except Exception:  # noqa: BLE001
                s = None
            return norm_stanza(s) if s else None
        return self.stanza_predefinita or ""

    def _conn_voce(self, chiave: str | None) -> list[_Connessione]:
        """Le connessioni che mostrano lo stato della voce di `chiave` (con il lock)."""
        if chiave is None:
            return []
        if chiave == "":
            return [c for lst in self._conn.values() for c in lst if c.locale]
        return [c for lst in self._conn.values() for c in lst
                if c.schermo.get("stanza") == chiave]

    def _voce_effettiva(self, chiave) -> dict:
        v = self._voce.get(chiave, self._DORME)
        if v["stato"] == "ascolta" and v["fino"] is not None and v["fino"] <= time.time():
            return dict(self._DORME)
        return dict(v)

    _PRIORITA = {"parla": 3, "pensa": 2, "ascolta": 1, "dorme": 0}

    def voce(self, stato: str, fino: float | None = None, stanza: str | None = None,
             sorgente: str | None = None) -> int:
        """Nuovo stato della voce, da mandare agli schermi di `stanza` (la corsia del
        satellite che lo cambia) o, senza, del microfono che ascolta. Non blocca (lock breve e
        `call_soon_threadsafe`): si chiama dal ciclo, dal thread della riproduzione e dal VAD.
        `fino` (epoch) solo con «ascolta»: la fine della finestra di follow-up. `sorgente`
        (la corsia, «sat:<id>»): con più satelliti nella stessa stanza gli schermi mostrano
        l'unione dei loro stati (`_unione`). Restituisce quante pagine l'hanno ricevuto (0 se
        lo stato della stanza è lo stesso di prima)."""
        if stato not in VOCE_STATI:
            raise ValueError(f"stato della voce sconosciuto: {stato!r}")
        nuovo = {"stato": stato,
                 "fino": round(fino, 3) if stato == "ascolta" and fino else None}
        with self._lock:
            chiave = self._chiave_voce(stanza)
            n = 0
            # Una sorgente sta in una stanza sola: un satellite spostato lascia quella di prima
            if sorgente is not None:
                for k in [k for k, src in self._voce_src.items()
                          if k != chiave and sorgente in src]:
                    del self._voce_src[k][sorgente]
                    n += self._ricalcola_voce(k)
            self._voce_src.setdefault(chiave, {})[sorgente] = nuovo
            if nuovo["fino"] is not None:
                if self._voce_thread is None:
                    self._voce_thread = threading.Thread(target=self._scadenze, daemon=True,
                                                         name="schermi-voce")
                    self._voce_thread.start()
                self._voce_cond.notify_all()
            return n + self._ricalcola_voce(chiave)

    def voce_via(self, sorgente: str) -> int:
        """Una sorgente (il satellite di una corsia) se ne va: il suo stato si toglie, e la
        stanza mostra quello degli altri satelliti, o «dorme» se non ne restano. Prima una
        stanza lasciata restava con l'ultimo stato («pensa»), anche per le pagine che si
        ricollegavano."""
        with self._lock:
            n = 0
            for k in [k for k, src in self._voce_src.items() if sorgente in src]:
                del self._voce_src[k][sorgente]
                n += self._ricalcola_voce(k)
            return n

    def _unione(self, srcs: dict) -> dict:
        """Lo stato di una stanza dagli stati delle sue sorgenti (con il lock)."""
        ora = time.time()
        vivi = [v for v in srcs.values()
                if not (v["stato"] == "ascolta" and v["fino"] is not None and v["fino"] <= ora)]
        if not vivi:
            return dict(self._DORME)
        primo = max(vivi, key=lambda v: self._PRIORITA.get(v["stato"], 0))
        if primo["stato"] != "ascolta":
            return {"stato": primo["stato"], "fino": None}
        fini = [v["fino"] for v in vivi if v["stato"] == "ascolta"]
        return {"stato": "ascolta", "fino": None if None in fini else max(fini)}

    def _ricalcola_voce(self, chiave) -> int:
        """Lo stato della stanza dopo un cambio di una sua sorgente: alle pagine solo se è
        cambiato (con il lock). Una stanza senza più sorgenti esce da `_voce`."""
        srcs = self._voce_src.get(chiave) or {}
        eff = self._unione(srcs)
        prima = self._voce.get(chiave)
        if srcs:
            self._voce[chiave] = eff
        else:
            self._voce_src.pop(chiave, None)
            self._voce.pop(chiave, None)
        if eff == (prima or self._DORME):
            return 0
        return self._manda_voce(chiave)

    def _manda_voce(self, chiave) -> int:
        msg = json.dumps(self._voce_effettiva(chiave))
        n = 0
        for c in self._conn_voce(chiave):
            n += c.consegna(("voce", msg))
        return n

    def _scadenze(self):
        """La finestra di follow-up di una stanza scade: «ascolta» torna «dorme» sui suoi
        schermi."""
        with self._lock:
            while True:
                fini = [v["fino"] for v in self._voce.values() if v["fino"] is not None]
                if not fini:
                    self._voce_cond.wait()
                    continue
                resto = min(fini) - time.time()
                if resto > 0:
                    self._voce_cond.wait(resto)
                    continue
                ora = time.time()
                for chiave, v in list(self._voce.items()):
                    if v["fino"] is not None and v["fino"] <= ora:
                        # Le sorgenti la cui finestra è finita tornano a dormire; la stanza
                        # mostra l'unione di quello che resta
                        for k, x in list((self._voce_src.get(chiave) or {}).items()):
                            if x["stato"] == "ascolta" and x["fino"] is not None                                     and x["fino"] <= ora:
                                self._voce_src[chiave][k] = dict(self._DORME)
                        srcs = self._voce_src.get(chiave)
                        self._voce[chiave] = (self._unione(srcs) if srcs
                                              else dict(self._DORME))
                        self._manda_voce(chiave)

    def voce_per(self, conn: _Connessione) -> dict | None:
        """Lo stato della voce per una pagina che si (ri)collega, se è tra quelle che lo
        mostrano: così dopo una riconnessione non resta quello vecchio. Vale lo stato della
        sua stanza (o di questo computer); senza, quello del microfono che ascolta."""
        with self._lock:
            for chiave in list(self._voce):
                if chiave is not None and conn in self._conn_voce(chiave):
                    return self._voce_effettiva(chiave)
            pred = self._chiave_voce(None)
            if pred is not None and conn in self._conn_voce(pred):
                return self._voce_effettiva(pred)
            return None

    # ── uso del contesto ──
    def contesto(self, mittente: Mittente, uso: dict) -> int:
        """L'uso del contesto della risposta ({"token", "finestra", "percento"}) agli schermi
        personali di chi parla (stesse regole delle schede personali: niente ospiti né zona
        grigia). È solo un evento per la barra: non entra nella cronologia. Non blocca;
        restituisce quante pagine l'hanno ricevuto. Il telefono non lo disegna."""
        try:
            dati = {"token": int(uso["token"]), "finestra": int(uso["finestra"]),
                    "percento": int(uso["percento"])}
        except (KeyError, TypeError, ValueError):
            return 0
        dest, _ = _destinatari(PERSONALE, mittente, self.abbinati(), None)
        if not dest:
            return 0
        msg = json.dumps(dati)
        n = 0
        with self._lock:
            self._contesto[mittente.chiave] = dati
            for s in dest:
                for c in self._conn.get(s["id"], []):
                    n += c.consegna(("contesto", msg))
        return n

    def contesto_per(self, schermo: dict) -> dict | None:
        """L'ultimo uso del contesto del proprietario di uno schermo personale, per la pagina
        che si (ri)collega."""
        persona = schermo.get("proprietario")
        if not persona:
            return None
        with self._lock:
            return self._contesto.get(persona)

    def avvisa_revoca(self, sids):
        """Le pagine degli schermi revocati tornano all'abbinamento subito."""
        with self._lock:
            for sid in sids:
                for c in self._conn.get(sid, []):
                    c.consegna(("revocato", "{}"))
                self._storia.pop(sid, None)

    def chiudi_tutte(self):
        """Arresto: ogni flusso SSE finisce da sé (le pagine si ricollegheranno), così uvicorn
        non deve cancellarli a forza (traccia di CancelledError nei log)."""
        with self._lock:
            for lst in self._conn.values():
                for c in lst:
                    c.consegna(("fine", ""))

    # ── scrivere solo durante una conversazione (05/10) ──
    def _stanza_ok(self, schermo: dict, conv) -> bool:
        """Uno schermo di stanza e una conversazione: stessa stanza. Con l'audio di questo
        computer e `schermi_stanza` vuota, le pagine aperte qui (come per lo stato della voce)."""
        if conv.stanza:
            return conv_mod.stessa_stanza(schermo, conv)
        return bool(conv.locale and self.collegato(schermo.get("id"), locale=True))

    def scrittura_consentita(self, schermo: dict | None) -> tuple[bool, str]:
        """Il punto unico (05/10): da questo schermo si può scrivere adesso (casella, moduli,
        immagini)? (True, "") o (False, motivo di conversazione.py). Una qualunque delle
        conversazioni aperte basta (fase 3: una per satellite)."""
        if not schermo:
            return False, conv_mod.NESSUNA
        ora, d = time.monotonic(), self.conversazioni.durata_s()
        motivo = conv_mod.NESSUNA
        for c in self.conversazioni.tutte():
            ok, m = conv_mod.scrittura_consentita(schermo, c, ora=ora, durata_s=d,
                                                  stanza_ok=self._stanza_ok)
            if ok:
                return True, ""
            motivo = m
        return False, motivo

    def scrittura_persona(self, persona: str | None) -> bool:
        """La persona è in una conversazione attiva (i suoi schermi personali scrivono)."""
        return bool(persona) and any(c.persona == persona for c in self.conversazioni.attive())

    def testo_senza_conversazione(self) -> str:
        nome = (getattr(self.cfg, "wake_names", None) or ["Calliope"])[0]
        return f"Di' «{nome}» per scrivermi: scrivo solo durante una conversazione a voce."

    def stato_scrittura(self, schermo: dict) -> dict:
        """Per la pagina: {"attiva", "motivo", "testo"} (nessun nome, nessun dato)."""
        ok, motivo = self.scrittura_consentita(schermo)
        return {"attiva": ok, "motivo": motivo,
                "testo": "" if ok else self.testo_senza_conversazione()}

    def stato_scrittura_per(self, conn: _Connessione) -> dict:
        """Lo stato per una pagina che si (ri)collega: lo ricorda, così i cambi dopo partono
        da qui."""
        st = self.stato_scrittura(conn.schermo)
        conn.scrittura = st
        return st

    def _scrittura_cambiata(self):
        """Una conversazione è cominciata, cambiata, chiusa o scaduta: le pagine il cui stato
        è cambiato ricevono «scrittura»; i moduli aperti di chi non è più in conversazione si
        chiudono, con una nota (si richiedono a voce)."""
        with self._lock:
            conns = [c for lst in self._conn.values() for c in lst]
        for c in conns:
            st = self.stato_scrittura(c.schermo)
            if st != c.scrittura:
                c.scrittura = st
                c.consegna(("scrittura", json.dumps(st, ensure_ascii=False)))
        ora = {c.persona for c in self.conversazioni.attive() if c.persona}
        finite, self._scrittura_persone = self._scrittura_persone - ora, ora
        for persona in finite:
            for f in list(self.su_fine_conversazione):
                try:
                    f(persona)
                except Exception:  # noqa: BLE001
                    pass
            for m in self.moduli.aperti(persona):
                self.moduli.chiudi(m, "Chiuso: la conversazione è finita. Chiedimelo di "
                                      "nuovo a voce.")

    def rifiuta_scritto(self, schermo: dict, motivo: str, canale: str):
        """Una richiesta dalla pagina rifiutata senza conversazione: nel registro dei turni
        solo il canale, lo schermo e il motivo (mai il testo)."""
        if self.registro_turni is None:
            return
        import datetime
        try:
            self.registro_turni({
                "inizio": datetime.datetime.now().isoformat(timespec="milliseconds"),
                "esito": "rifiutato", "canale": canale, "schermo": schermo.get("nome"),
                "motivo": motivo, "regole": [conv_mod.REGOLA]})
        except Exception:  # noqa: BLE001
            pass

    # ── gestione (tool e terminale) ──
    def abbina(self, codice, stanza, proprietario=None, proprietario_nome=None) -> dict:
        res = self.archivio.abbina(codice, stanza, proprietario, proprietario_nome)
        self._rinfresca()
        return res

    def revoca(self, chi) -> list[dict]:
        via = self.archivio.revoca(chi)
        self._rinfresca()
        self.avvisa_revoca([s["id"] for s in via])
        return via

    def stato(self) -> dict:
        ab = self.abbinati()
        coll = {s["id"] for s in self.collegati()}
        return {"abbinati": len(ab), "collegati": len(coll), "url": self.url,
                "schermi": [{"nome": s["nome"], "stanza": s["stanza"],
                             "personale_di": s.get("proprietario_nome"),
                             "collegato": s["id"] in coll} for s in ab]}
