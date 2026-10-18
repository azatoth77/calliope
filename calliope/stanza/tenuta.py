"""
La tenuta su disco del testo della stanza (14/10, conversazione di stanza; decisione 0029 punto 5,
progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.3, § 3.10, § 4 punti 2 e 5).

Con `stanza_tenuta: true` (di serie spenta: la stanza resta solo in memoria, al più 24 h) le
righe del registro della stanza (stanza/registro.py) vanno anche in un SQLite accanto alla
configurazione (`stanza_tenuta_db`, di serie `stanza.db`) per `stanza_tenuta_giorni` (60), con
le presenze per persona (chi c'era, dove e quando: servono ai permessi della ricerca anche
dopo un riavvio). Il testo della stanza **non è un dato per le misure** (0029): il banco e la
regressione non lo leggono.

**Cosa va su disco** (`conserva.decidi(…, "stanza", …)`, il solo posto che decide):

- le righe di una persona di casa **riconosciuta dalla voce sopra soglia**, adulti e minori
  (scelta di chi amministra del 13/10, confermata il 14/10 a ogni età del minore): testo, chi,
  stanza e satellite, inizio e fine, «rivolta», minore;
- le righe di Calliope (ciò che ha detto ad alta voce lì) solo in risposta a una persona di casa
  riconosciuta dalla voce;
- dal 14/10 (decisione 0030, `stanza_conoscenti`) le righe di un **conoscente** confermato da
  chi amministra e riconosciuto dalla voce sopra soglia: `persona` «conoscente:<id>», con la
  nota che lo distingue dagli omonimi, e (14/10 sera, rifiniture) le sue presenze con la stessa
  chiave; via quando lo si dimentica o scade;
- **mai**: le voci non riconosciute (ospiti), la zona grigia (nel dubbio no), ciò che si dice in
  pausa («abbiamo ospiti»: in pausa la stanza non scrive niente, nemmeno in memoria), l'audio
  (non arriva mai qui), i profili tolti (la rotazione li cancella).
- **durante la valutazione** (18/10, decisione 0032, `conserva_valutazione_fino`): anche le righe
  che sopra restano fuori (ospiti, zona grigia, voci sconosciute, la TV, le risposte di Calliope a
  loro), con `sicurezza: valutazione`. Solo per chi rilegge il file: la ricerca, la guardia, i
  nomi e le stanze leggono soltanto le righe di sempre (`sicurezza: voce`). Mai in pausa. Restano
  per `stanza_tenuta_giorni` e le tolgono «dimentica» (il satellite), `--svuota` e, con la
  persona decisa nella zona grigia, `--persona`.

**Una porta sola verso il modello**: la ricerca (`stanza_cerca` e la ricerca anticipata,
stanza/cerca.py) con gli **stessi permessi** della memoria. Il blocco caldo dei dati del turno
(stanza/contesto.py) legge soltanto la memoria: dopo un riavvio non ripesca niente da qui.

**Cancellazione**: «dimentica» (conversazioni_dimentica, Stanza.dimentica) toglie tutte le
righe e le presenze del satellite; `calliope conserva --svuota` (anche da un altro processo) e
`dati_conservati` svuota tutto o le righe di una persona (anche le risposte di Calliope a lei);
dopo `stanza_tenuta_giorni` la rotazione (all'avvio e una volta al giorno). Sempre con
`secure_delete`, l'indice FTS5 ricompattato e il checkpoint del WAL, come l'archivio delle
conversazioni (10/10, «dimentica» vera).

**Tempi**: le scritture le fa un thread suo, in ordine (la voce non aspetta mai il disco); la
ricerca è sincrona, con FTS5 (`detail=full`, trappola nota; prefissi indicizzati per le radici
di stanza/cerca.py): sul banco a secco del 14/10, 60 giorni di righe (~180 000) si cercano in
pochi millisecondi (prove/prova_stanza_tenuta.py stampa la misura).

**Il diario della guardia** (14/10 sera, stanza/guardia.py): nello stesso file, come modulo di
schema a sé (`stanza_guardia`), quali righe il guardiano a posteriori ha già giudicato (avvio,
satellite, seq, esito: mai parole) e quando sullo schermo di un satellite era aperto un gioco;
dopo un riavvio la guardia riprende da qui le righe non ancora giudicate.

Solo libreria standard (sqlite3 con FTS5, già usato dall'archivio e dalla biblioteca).
"""

from __future__ import annotations

import os
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from ..persistenza import apri_db, prepara_schema

MODULO = "stanza_tenuta"
GIORNO_S = 86400.0
# Ogni quanto si riscrive la fine di una presenza ancora aperta (un riavvio non perde chi c'era)
PRESENZA_OGNI_S = 60.0
# Tetti delle letture per una ricerca (le righe poi le sceglie stanza/cerca.py)
TROVATE_MAX = 400
RECENTI_MAX = 300
VICINE_FINESTRA_S = 900.0
VICINE_PER_RIGA = 40
VICINE_RIGHE_MAX = 30
# Le righe tenute solo per la valutazione (18/10, decisione 0032): nessuna lettura le usa
VALUTAZIONE = "valutazione"
_NON_VALUTAZIONE = "COALESCE(r.sicurezza, '') != 'valutazione'"


def accesa(cfg) -> bool:
    return bool(getattr(cfg, "stanza_tenuta", False))


def percorso_db(cfg) -> Path:
    p = getattr(cfg, "stanza_tenuta_db", None) or "stanza.db"
    p = Path(os.path.expanduser(str(p)))
    if not p.is_absolute():
        p = Path(getattr(cfg, "config_dir", None) or ".") / p
    return p


def _v1(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS righe (
            id INTEGER PRIMARY KEY, avvio TEXT NOT NULL, sat TEXT NOT NULL, stanza TEXT,
            satellite TEXT, seq INTEGER NOT NULL, segmento INTEGER, scambio INTEGER,
            versione INTEGER NOT NULL DEFAULT 1, inizio REAL NOT NULL, fine REAL NOT NULL,
            testo TEXT NOT NULL, chi TEXT NOT NULL, persona TEXT, nome TEXT, sicurezza TEXT,
            rivolta TEXT, minore INTEGER NOT NULL DEFAULT 0, per_persona TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS righe_chiave ON righe(avvio, sat, seq);
        CREATE INDEX IF NOT EXISTS righe_sat ON righe(sat, fine);
        CREATE INDEX IF NOT EXISTS righe_persona ON righe(persona, fine);
        CREATE INDEX IF NOT EXISTS righe_nome ON righe(nome, fine);
        CREATE INDEX IF NOT EXISTS righe_fine ON righe(fine);
        CREATE VIRTUAL TABLE IF NOT EXISTS righe_fts USING fts5(
            testo, tokenize='unicode61 remove_diacritics 2', prefix='3 4 5', detail=full);
        CREATE TABLE IF NOT EXISTS presenze (
            id INTEGER PRIMARY KEY, persona TEXT NOT NULL, sat TEXT NOT NULL,
            inizio REAL NOT NULL, fine REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS presenze_chiave ON presenze(persona, sat, inizio);
        CREATE INDEX IF NOT EXISTS presenze_fine ON presenze(fine);
    """)


def _v2(db):
    # I conoscenti (14/10, decisione 0030): la nota che distingue due omonimi («collega di
    # Dario»), accanto al nome
    db.execute("ALTER TABLE righe ADD COLUMN nota TEXT")


MIGRAZIONI = [_v1, _v2]


def _g1(db):
    """Il diario del guardiano a posteriori (14/10, stanza/guardia.py), un modulo a sé nello
    stesso file (una versione di prima lo ignora, il file non passa in sola lettura): quali
    righe sono già state giudicate (avvio, satellite, seq, esito, istante: mai parole) e quando
    sullo schermo di un satellite era aperto un gioco. `dal`: da quando c'è il diario (le righe
    di prima le aveva già guardate la guardia in memoria: non si riprendono)."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS guardia_giudicate (
            avvio TEXT NOT NULL, sat TEXT NOT NULL, seq INTEGER NOT NULL, esito TEXT,
            t REAL NOT NULL, PRIMARY KEY (avvio, sat, seq));
        CREATE INDEX IF NOT EXISTS guardia_giudicate_t ON guardia_giudicate(t);
        CREATE TABLE IF NOT EXISTS guardia_giochi (
            sat TEXT NOT NULL, inizio REAL NOT NULL, fine REAL NOT NULL,
            PRIMARY KEY (sat, inizio));
        CREATE TABLE IF NOT EXISTS guardia_meta (chiave TEXT PRIMARY KEY, valore REAL);
    """)
    db.execute("INSERT OR IGNORE INTO guardia_meta(chiave, valore) VALUES ('dal', ?)",
               (time.time(),))


MODULO_GUARDIA = "stanza_guardia"
MIGRAZIONI_GUARDIA = [_g1]
_COLONNE = ("id", "avvio", "sat", "stanza", "satellite", "seq", "segmento", "scambio",
            "versione", "inizio", "fine", "testo", "chi", "persona", "nome", "sicurezza",
            "rivolta", "minore", "per_persona", "nota")
_SELEZIONE = ", ".join(f"r.{c}" for c in _COLONNE)


def _profilo(registry, pid):
    """Il profilo con questo id (by_id se c'è, altrimenti fra `users`), o None."""
    if registry is None or not pid:
        return None
    by_id = getattr(registry, "by_id", None)
    if callable(by_id):
        try:
            return by_id(pid)
        except Exception:  # noqa: BLE001
            return None
    for p in list(getattr(registry, "users", {}).values()):
        if str(getattr(p, "id", None) or getattr(p, "name", "")) == str(pid):
            return p
    return None


def _cancella_sicuro(db, sql: str, parametri=()) -> int:
    from ..eventi.registro import cancella_sicuro
    return cancella_sicuro(db, sql, parametri) or 0


class Tenuta:
    """Il disco della stanza di un processo: un avvio (id nuovo a ogni partenza), una
    connessione, un thread che scrive in ordine."""

    def __init__(self, path, giorni: int = 60, registry=None, log=print, avvia: bool = True):
        self.path = str(path)
        self.giorni = int(giorni or 60)
        self.registry = registry
        self.log = log
        # L'avvio: le righe di questo processo si distinguono da quelle di prima (il `seq` del
        # registro in memoria ricomincia da 1 a ogni avvio)
        self.avvio = uuid.uuid4().hex[:12]
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = apri_db(self.path)
        try:
            self.db.execute("PRAGMA secure_delete = ON")
        except sqlite3.Error:
            pass
        self.lock = threading.Lock()
        self.scrivibile = prepara_schema(self.db, MODULO, MIGRAZIONI, "conversazioni")
        # Il diario della guardia (14/10): None se non si prepara (la guardia non riprende
        # niente dal disco, come prima)
        self.guardia_dal = None
        if self.scrivibile:
            try:
                from ..persistenza import migra
                migra(self.db, MODULO_GUARDIA, MIGRAZIONI_GUARDIA)
                row = self.db.execute("SELECT valore FROM guardia_meta WHERE chiave = "
                                      "'dal'").fetchone()
                self.guardia_dal = float(row[0]) if row else None
            except Exception as e:  # noqa: BLE001
                self.log(f"   [STANZA] diario della guardia non pronto: {type(e).__name__}")
        self.coda: queue.Queue = queue.Queue()
        self._fermo = threading.Event()
        self._thread = None
        self._ultima_rotazione = 0.0
        # I conoscenti (stanza/conoscenti.Conoscenti, 14/10): le loro righe si tengono finché
        # il profilo c'è
        self.conoscenti = None
        # La valutazione (18/10, decisione 0032): una funzione che dice se vale adesso
        # (load_tenuta: conserva.valutazione_attiva); None = mai, come prima
        self.valutazione = None
        self.scritte = 0              # righe scritte da quando è partita
        self.saltate = 0              # righe non scritte (ospiti, zona grigia, profilo tolto)
        self.errori = 0
        if avvia:
            self._thread = threading.Thread(target=self._ciclo, name="stanza-tenuta",
                                            daemon=True)
            self._thread.start()

    # ── il thread ──
    def _ciclo(self):
        self._ruota_se_serve()
        while not self._fermo.is_set():
            try:
                lavoro = self.coda.get(timeout=1.0)
            except queue.Empty:
                self._ruota_se_serve()
                continue
            if lavoro is None:
                self.coda.task_done()
                break
            try:
                lavoro()
            except Exception as e:  # noqa: BLE001 — il disco non ferma la stanza
                self.errori += 1
                if self.errori == 1 or self.errori % 100 == 0:
                    self.log(f"   [STANZA] tenuta su disco: {type(e).__name__}: {e}")
            finally:
                self.coda.task_done()

    def _lavoro(self, f, aspetta: bool = False, timeout: float = 5.0):
        """In coda al thread (le scritture, in ordine), o subito senza thread (le prove, il
        terminale). Con `aspetta` il risultato, dopo i lavori di prima."""
        if self._thread is None:
            return f()
        if not aspetta:
            self.coda.put(f)
            return None
        fatto, esito = threading.Event(), {}

        def g():
            try:
                esito["r"] = f()
            finally:
                fatto.set()
        self.coda.put(g)
        fatto.wait(timeout)
        return esito.get("r")

    def attendi(self, timeout: float = 5.0) -> bool:
        """Aspetta che i lavori in coda siano finiti (prove, «dimentica», chiusura)."""
        fine = time.monotonic() + timeout
        while time.monotonic() < fine:
            if self.coda.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return False

    def chiudi(self):
        if self._thread is not None:
            self.attendi(3.0)
            self._fermo.set()
            self.coda.put(None)
            self._thread.join(timeout=2.0)
        with self.lock:
            try:
                self.db.close()
            except sqlite3.Error:
                pass

    # ── chi va su disco (conserva.decidi) ──
    def _tieni(self, persona, sicurezza) -> bool:
        if sicurezza != "voce" or not persona:
            return False
        from ..conserva import decidi
        if str(persona).startswith("conoscente:"):
            # Un conoscente (14/10): solo se il profilo c'è (confermato da chi amministra)
            con = self.conoscenti
            prof = con.per_id(persona) if con is not None else None
            return bool(prof is not None and decidi(prof, "stanza", "voce"))
        reg = self.registry
        if reg is None or not getattr(reg, "users", None):
            # Senza profili letti (prove senza registro): la voce riconosciuta basta
            return reg is None
        return bool(decidi(_profilo(reg, persona), "stanza", "voce"))

    def _in_valutazione(self) -> bool:
        f = self.valutazione
        try:
            return bool(f()) if callable(f) else False
        except Exception:  # noqa: BLE001 — nel dubbio come di serie
            return False

    # ── dal registro della stanza (thread della stanza o del ciclo) ──
    def evento(self, sat, info: dict | None, e) -> None:
        """Un evento del registro della stanza di `sat` (stanza/registro.Evento): le righe e le
        presenze che si possono tenere vanno in coda al thread; il resto no."""
        from .registro import ANALISI, DETTO_CALLIOPE, PRESENZA, RIGA, RIGA_SCARTATA
        d = dict(e.dati or {})
        s = str(sat)
        info = info or {}
        if e.tipo == RIGA:
            chi = str(d.get("chi") or "")
            pid = (chi[len("persona:"):] if chi.startswith("persona:")
                   else chi if chi.startswith("conoscente:") else None)
            seg = d.get("segmento")
            testo_ok = bool(str(d.get("testo") or "").strip())
            sic = "voce"
            if testo_ok and not self._tieni(pid, d.get("sicurezza")) and self._in_valutazione():
                # La valutazione (18/10, decisione 0032): la riga resta, segnata (la ricerca e la
                # guardia non la leggono); una versione nuova toglie quella di prima come sempre
                sic = VALUTAZIONE
            elif not testo_ok or not self._tieni(pid, d.get("sicurezza")):
                self.saltate += 1
                if seg is not None and int(d.get("versione") or 1) >= 2:
                    # Una versione nuova dello stesso segmento che non si tiene (passo 3: chi
                    # parla rivisto in «ignoto», la TV): quella di prima non resta (le parti
                    # della stessa versione già scritte sì)
                    v = int(d.get("versione") or 1)
                    self._lavoro(lambda: self._togli_segmento(s, seg, sotto=v))
                return
            riga = {"sat": s, "stanza": info.get("stanza"), "satellite": info.get("nome"),
                    "seq": e.seq, "segmento": seg, "scambio": d.get("scambio"),
                    "versione": int(d.get("versione") or 1),
                    "inizio": float(d.get("inizio") or e.t), "fine": float(d.get("fine") or e.t),
                    "testo": str(d.get("testo")), "chi": chi, "persona": pid,
                    "nome": d.get("nome"), "sicurezza": sic, "rivolta": d.get("rivolta"),
                    "minore": 1 if d.get("minore") else 0, "per_persona": None,
                    "nota": d.get("nota") or None}
            self._lavoro(lambda: self._scrivi(riga))
        elif e.tipo == DETTO_CALLIOPE:
            per = d.get("per") if isinstance(d.get("per"), dict) else {}
            pid = per.get("persona")
            testo_ok = bool(str(d.get("testo") or "").strip())
            sic = "voce"
            if testo_ok and not self._tieni(pid, per.get("sicurezza")) and self._in_valutazione():
                sic = VALUTAZIONE            # la risposta a un ospite (18/10, decisione 0032)
            elif not testo_ok or not self._tieni(pid, per.get("sicurezza")):
                self.saltate += 1
                return
            riga = {"sat": s, "stanza": info.get("stanza"), "satellite": info.get("nome"),
                    "seq": e.seq, "segmento": None, "scambio": None, "versione": 1,
                    "inizio": float(d.get("inizio") or e.t), "fine": float(d.get("fine") or e.t),
                    "testo": str(d.get("testo")), "chi": "calliope", "persona": None,
                    "nome": "Calliope", "sicurezza": sic, "rivolta": None, "minore": 0,
                    "per_persona": str(pid) if pid else None, "nota": None}
            self._lavoro(lambda: self._scrivi(riga))
        elif e.tipo == ANALISI and d.get("analisi") == "rivolta":
            seq, esito = d.get("riga"), d.get("esito")
            self._lavoro(lambda: self._rivolta(s, seq, esito))
        elif e.tipo == RIGA_SCARTATA and d.get("segmento") is not None:
            seg = d.get("segmento")
            self._lavoro(lambda: self._togli_segmento(s, seg))
        elif e.tipo == PRESENZA:
            self.presenza(d.get("persona"), sat, d.get("inizio"), d.get("fine"))

    def presenza(self, persona, sat, inizio, fine) -> None:
        """Chi c'era (la voce riconosciuta sopra soglia): l'intervallo, nuovo o allungato."""
        if not persona or inizio is None or fine is None:
            return
        if not self._tieni(str(persona), "voce"):
            return
        p, s, a, b = str(persona), str(sat), round(float(inizio), 3), round(float(fine), 3)

        def f():
            with self.lock:
                self.db.execute(
                    "INSERT INTO presenze(persona, sat, inizio, fine) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(persona, sat, inizio) DO UPDATE SET fine = max(fine, "
                    "excluded.fine)", (p, s, a, b))
                self.db.commit()
        self._lavoro(f)

    # ── scritture (dal thread) ──
    def _scrivi(self, r: dict):
        with self.lock:
            if r["segmento"] is not None:
                # La versione di prima dello stesso segmento (passo 3: la corsia lenta); le
                # altre parti della stessa versione (un segmento spezzato fra due voci) restano
                self._togli_dove("avvio = ? AND sat = ? AND segmento = ? AND versione < ?",
                                 (self.avvio, r["sat"], r["segmento"], r["versione"]))
            self._togli_dove("avvio = ? AND sat = ? AND seq = ?", (self.avvio, r["sat"], r["seq"]))
            cur = self.db.execute(
                "INSERT INTO righe(avvio, sat, stanza, satellite, seq, segmento, "
                "scambio, versione, inizio, fine, testo, chi, persona, nome, sicurezza, rivolta, "
                "minore, per_persona, nota) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?)", (self.avvio, r["sat"], r["stanza"], r["satellite"], r["seq"],
                                r["segmento"], r["scambio"], r["versione"], r["inizio"],
                                r["fine"], r["testo"], r["chi"], r["persona"], r["nome"],
                                r["sicurezza"], r["rivolta"], r["minore"], r["per_persona"],
                                r.get("nota")))
            rid = cur.lastrowid
            self.db.execute("INSERT INTO righe_fts(rowid, testo) VALUES (?, ?)",
                            (rid, r["testo"]))
            self.db.commit()
        self.scritte += 1

    def correggi(self, sat, seq, testo: str) -> None:
        """Il testo di una riga di questo avvio, ripulito (18/10, revisione della PR #178: la
        frase di sfida e i codici non restano sul disco della stanza), anche nell'indice. In
        coda dopo la scrittura della riga."""
        s, q, nuovo = str(sat), int(seq), str(testo)

        def f():
            with self.lock:
                ids = [r[0] for r in self.db.execute(
                    "SELECT id FROM righe WHERE avvio = ? AND sat = ? AND seq = ?",
                    (self.avvio, s, q))]
                for rid in ids:
                    _cancella_sicuro(self.db, "DELETE FROM righe_fts WHERE rowid = ?", (rid,))
                    self.db.execute("UPDATE righe SET testo = ? WHERE id = ?", (nuovo, rid))
                    self.db.execute("INSERT INTO righe_fts(rowid, testo) VALUES (?, ?)",
                                    (rid, nuovo))
                if ids:
                    self._compatta()
                else:
                    self.db.commit()
        self._lavoro(f)

    def _rivolta(self, sat: str, seq, esito):
        if seq is None:
            return
        with self.lock:
            self.db.execute("UPDATE righe SET rivolta = ? WHERE avvio = ? AND sat = ? AND seq = ?",
                            (esito, self.avvio, sat, int(seq)))
            self.db.commit()

    def _togli_segmento(self, sat: str, seg, sotto: int | None = None):
        """Le righe del segmento (scartato), o solo quelle di versione sotto `sotto`."""
        with self.lock:
            if sotto is None:
                self._togli_dove("avvio = ? AND sat = ? AND segmento = ?", (self.avvio, sat, seg))
            else:
                self._togli_dove("avvio = ? AND sat = ? AND segmento = ? AND versione < ?",
                                 (self.avvio, sat, seg, int(sotto)))
            self.db.commit()

    def _togli_dove(self, dove: str, args=()) -> int:
        """Con il lock: le righe che rispondono a `dove`, anche dall'indice, con secure_delete."""
        _cancella_sicuro(self.db, f"DELETE FROM righe_fts WHERE rowid IN (SELECT id FROM righe "
                                  f"WHERE {dove})", args)
        return _cancella_sicuro(self.db, f"DELETE FROM righe WHERE {dove}", args)

    def _compatta(self):
        """Con il lock: l'indice ricompattato e il WAL ricopiato e troncato (le parole tolte non
        restano nei segmenti dell'indice né nelle versioni vecchie delle pagine)."""
        from ..eventi.registro import checkpoint
        try:
            self.db.execute("INSERT INTO righe_fts(righe_fts) VALUES('optimize')")
        except sqlite3.Error:
            pass
        self.db.commit()
        checkpoint(self.db)

    # ── cancellazione ──
    def dimentica(self, sat) -> int:
        """«Dimentica» (decisione 0029 § 4 punto 5): tutte le righe e le presenze del satellite,
        di ogni giorno. Dopo i lavori in coda (una riga ancora da scrivere tornerebbe dopo)."""
        s = str(sat)

        def f():
            with self.lock:
                n = self._togli_dove("sat = ?", (s,))
                _cancella_sicuro(self.db, "DELETE FROM presenze WHERE sat = ?", (s,))
                self._compatta()
                return n
        return int(self._lavoro(f, aspetta=True) or 0)

    def svuota(self, persona=None) -> int:
        """Tutto (`calliope conserva --svuota`), o le righe di una persona con le risposte di
        Calliope a lei e le sue presenze (`--persona`, dati_conservati). Quante righe."""
        def f():
            with self.lock:
                if persona is None:
                    n = self._togli_dove("1 = 1")
                    _cancella_sicuro(self.db, "DELETE FROM presenze")
                else:
                    p = str(persona)
                    n = self._togli_dove("persona = ? OR per_persona = ?", (p, p))
                    _cancella_sicuro(self.db, "DELETE FROM presenze WHERE persona = ?", (p,))
                self._compatta()
                return n
        return int(self._lavoro(f, aspetta=True) or 0)

    def rinomina(self, vecchia, nuova, chi: str, nome: str | None = None) -> int:
        """Una persona che cambia tipo (14/10, conoscenti: promossa a familiare o tornata
        conoscente): le sue righe passano da `vecchia` a `nuova` («conoscente:<id>» o l'id del
        profilo), con il nome; dal 14/10 sera (rifiniture) anche le sue presenze, così chi è
        promosso cerca dove c'era già da conoscente. Quante righe."""
        v, n = str(vecchia), str(nuova)

        def f():
            with self.lock:
                cur = self.db.execute(
                    "UPDATE righe SET persona = ?, chi = ?, nome = coalesce(?, nome) WHERE "
                    "persona = ?", (n, chi, nome, v))
                self.db.execute("UPDATE righe SET per_persona = ? WHERE per_persona = ?", (n, v))
                # Un intervallo uguale già della persona nuova resta quello (indice unico)
                self.db.execute("UPDATE OR IGNORE presenze SET persona = ? WHERE persona = ?",
                                (n, v))
                _cancella_sicuro(self.db, "DELETE FROM presenze WHERE persona = ?", (v,))
                self.db.commit()
                return cur.rowcount
        return int(self._lavoro(f, aspetta=True) or 0)

    def _ruota_se_serve(self):
        if time.time() - self._ultima_rotazione >= GIORNO_S:
            try:
                self.ruota()
            except Exception as e:  # noqa: BLE001
                self.log(f"   [STANZA] rotazione della tenuta: {type(e).__name__}: {e}")

    def ruota(self, ora: float | None = None) -> dict:
        """Via le righe e le presenze oltre `giorni`, e quelle delle persone senza più il
        profilo (con i profili letti: un file illeggibile per un momento non toglie niente)."""
        ora = time.time() if ora is None else float(ora)
        self._ultima_rotazione = time.time()
        limite = ora - self.giorni * GIORNO_S
        out = {"vecchie": 0, "senza_profilo": 0}
        ids = None
        reg = self.registry
        if reg is not None and getattr(reg, "users", None):
            ids = [str(getattr(p, "id", None) or getattr(p, "name", ""))
                   for p in list(reg.users.values())]
            # I conoscenti salvati (14/10): le loro righe restano finché il profilo c'è
            con = self.conoscenti
            if con is not None:
                ids += [f"conoscente:{c.id}" for c in con.elenco()]
        with self.lock:
            out["vecchie"] = self._togli_dove("fine < ?", (limite,))
            _cancella_sicuro(self.db, "DELETE FROM presenze WHERE fine < ?", (limite,))
            if ids:
                segni = ", ".join("?" * len(ids))
                # Senza i conoscenti legati (spenti, o non ancora all'avvio) le loro righe non
                # si toccano qui: le toglie la scadenza dei giorni o il loro «dimentica»
                salvo = ("" if self.conoscenti is not None
                         else " AND persona NOT LIKE 'conoscente:%'")
                out["senza_profilo"] = self._togli_dove(
                    f"(persona IS NOT NULL AND persona NOT IN ({segni}){salvo}) OR (per_persona "
                    f"IS NOT NULL AND per_persona NOT IN ({segni}))", (*ids, *ids))
                # Le presenze dei conoscenti (14/10, rifiniture) come le loro righe
                _cancella_sicuro(self.db, f"DELETE FROM presenze WHERE persona NOT IN ({segni})"
                                          f"{salvo}", tuple(ids))
            if self.guardia_dal is not None:
                self.db.execute("DELETE FROM guardia_giudicate WHERE t < ?", (limite,))
                self.db.execute("DELETE FROM guardia_giochi WHERE fine < ?", (limite,))
            if out["vecchie"] or out["senza_profilo"]:
                self._compatta()
            else:
                self.db.commit()
        if out["vecchie"] or out["senza_profilo"]:
            self.log(f"   [STANZA] tenuta: tolte {out['vecchie']} righe oltre {self.giorni} "
                     f"giorni e {out['senza_profilo']} di profili tolti")
        return out

    # ── letture (la ricerca) ──
    def presenze(self, persona) -> list[tuple]:
        """Gli intervalli (sat come testo, inizio, fine) in cui la persona c'era."""
        if not persona:
            return []
        with self.lock:
            return [(r[0], float(r[1]), float(r[2])) for r in self.db.execute(
                "SELECT sat, inizio, fine FROM presenze WHERE persona = ? ORDER BY inizio",
                (str(persona),))]

    def stanze(self) -> dict:
        """{sat come testo: {stanza, nome}} dei satelliti con righe su disco (l'ultimo nome)."""
        with self.lock:
            rows = self.db.execute(
                "SELECT sat, stanza, satellite FROM righe WHERE id IN (SELECT max(r.id) FROM "
                f"righe r WHERE {_NON_VALUTAZIONE} GROUP BY r.sat)").fetchall()
        return {r[0]: {"stanza": r[1], "nome": r[2]} for r in rows}

    def nomi(self) -> list[str]:
        with self.lock:
            return [r[0] for r in self.db.execute(
                f"SELECT DISTINCT r.nome FROM righe r WHERE r.nome IS NOT NULL AND "
                f"{_NON_VALUTAZIONE}")]

    @staticmethod
    def _riga(row) -> dict:
        d = dict(zip(_COLONNE, row))
        rid = int(d.pop("id"))
        avvio = d.pop("avvio")
        d["_disco"] = True
        d["_avvio"] = avvio
        d["_seq"] = d["seq"]
        # Una chiave che non si confonde con i `seq` della memoria (sempre positivi)
        d["seq"] = -rid
        d["t"] = d["fine"]
        d["minore"] = bool(d["minore"])
        d["segmento"] = None                   # i segmenti sono dell'avvio, non del disco
        if d.get("scambio") is not None:
            d["scambio"] = f"{avvio}:{d['scambio']}"
        return d

    def cerca(self, radici=(), sats=None, da=None, a=None, nomi=(), minore_pid=None,
              tutore_di=(), recenti: bool = False, escludi=None) -> list[dict]:
        """Le righe candidate per stanza/cerca.py (i permessi fini, il punteggio e la scelta li
        fa lei): quelle con le radici (FTS5, con le vicine nello stesso tratto di tempo), quelle
        delle persone `nomi`, e con `recenti` le ultime delle stanze `sats`. Prefiltri dei
        permessi già qui: un minore (`minore_pid`) solo le sue con la voce; un adulto le righe
        dei minori solo di quelli in `tutore_di`. `escludi`: {sat: set dei seq} ancora nel
        registro in memoria di questo avvio (non si ripetono)."""
        filtri, args = [_NON_VALUTAZIONE], []
        if da is not None:
            filtri.append("r.fine >= ?")
            args.append(float(da))
        if a is not None:
            filtri.append("r.fine <= ?")
            args.append(float(a))
        if minore_pid is not None:
            filtri.append("r.persona = ? AND r.sicurezza = 'voce'")
            args.append(str(minore_pid))
        else:
            tut = [str(x) for x in tutore_di or ()]
            if tut:
                filtri.append(f"(r.minore = 0 OR r.persona IN ({', '.join('?' * len(tut))}))")
                args += tut
            else:
                filtri.append("r.minore = 0")
        dove = " AND ".join(filtri) or "1 = 1"
        sats_t = [str(s) for s in sats] if sats is not None else None
        out: dict = {}
        with self.lock:
            if radici:
                q = " OR ".join(f'"{r}"*' for r in radici if r.isalnum())
                if q:
                    trovate = self.db.execute(
                        f"SELECT {_SELEZIONE} FROM righe_fts f JOIN righe r ON r.id = f.rowid "
                        f"WHERE righe_fts MATCH ? AND {dove} ORDER BY bm25(righe_fts), "
                        f"r.fine DESC LIMIT {TROVATE_MAX}", (q, *args)).fetchall()
                    for row in trovate:
                        out[row[0]] = row
                    # Il discorso intorno (le righe vicine, VICINE_RIGHE in stanza/cerca.py):
                    # lo stesso tratto di tempo della stessa stanza, per le prime trovate
                    for row in trovate[:VICINE_RIGHE_MAX]:
                        sat, ini, fin = row[2], row[9], row[10]
                        for v in self.db.execute(
                                f"SELECT {_SELEZIONE} FROM righe r WHERE r.sat = ? AND r.fine "
                                f"BETWEEN ? AND ? AND {dove} ORDER BY r.fine LIMIT "
                                f"{VICINE_PER_RIGA}",
                                (sat, ini - VICINE_FINESTRA_S, fin + VICINE_FINESTRA_S, *args)):
                            out.setdefault(v[0], v)
            if nomi:
                nn = [str(n) for n in nomi]
                for row in self.db.execute(
                        f"SELECT {_SELEZIONE} FROM righe r WHERE r.nome IN "
                        f"({', '.join('?' * len(nn))}) AND {dove} ORDER BY r.fine DESC LIMIT "
                        f"{RECENTI_MAX}", (*nn, *args)):
                    out.setdefault(row[0], row)
            if recenti:
                ds, da_s = dove, list(args)
                if sats_t is not None:
                    if not sats_t:
                        ds = "0"
                    else:
                        ds += f" AND r.sat IN ({', '.join('?' * len(sats_t))})"
                        da_s += sats_t
                for row in self.db.execute(
                        f"SELECT {_SELEZIONE} FROM righe r WHERE {ds} ORDER BY r.fine DESC "
                        f"LIMIT {RECENTI_MAX}", da_s):
                    out.setdefault(row[0], row)
        righe = []
        for row in out.values():
            d = self._riga(row)
            if (escludi and d["_avvio"] == self.avvio
                    and d["_seq"] in escludi.get(d["sat"], ())):
                continue                       # ancora in memoria: la dà il registro
            righe.append(d)
        return righe

    # ── il diario della guardia (stanza/guardia.py, 14/10) ──
    def righe_guardia(self, da: float) -> list[dict]:
        """Le righe degli avvii di prima (quelle di questo avvio le dà il registro in memoria)
        finite da `da` in poi, per satellite e inizio, con `_giudicata` (già nel diario) e
        `_id` (la riga del disco). Vuoto senza diario."""
        if self.guardia_dal is None:
            return []
        with self.lock:
            rows = self.db.execute(
                f"SELECT {_SELEZIONE}, EXISTS(SELECT 1 FROM guardia_giudicate g WHERE "
                f"g.avvio = r.avvio AND g.sat = r.sat AND g.seq = r.seq) FROM righe r WHERE "
                f"r.avvio != ? AND r.fine >= ? AND {_NON_VALUTAZIONE} ORDER BY r.sat, r.inizio, "
                f"r.id",
                (self.avvio, float(da))).fetchall()
        out = []
        for row in rows:
            d = self._riga(row[:-1])
            d["_id"] = int(row[0])
            d["_giudicata"] = bool(row[-1])
            out.append(d)
        return out

    def vive(self, ids) -> set:
        """Quali di queste righe del disco ci sono ancora («dimentica», svuota, rotazione)."""
        ids = [int(i) for i in ids]
        if not ids:
            return set()
        with self.lock:
            return {int(r[0]) for r in self.db.execute(
                f"SELECT id FROM righe WHERE id IN ({', '.join('?' * len(ids))})", ids)}

    def non_giudicate_minori(self, da: float, a: float) -> int:
        """Quante righe di un minore degli avvii di prima, finite tra `da` e `a`, non sono nel
        diario (oltre il limite della ripresa: non si giudicano più, si contano). Senza le righe
        che la guardia non giudica per scelta (`Guardia._da_giudicare`: Calliope, la TV, le
        frasi rivolte a Calliope, il testo vuoto; 18/10, issue #159: il 17/10 erano 29 righe su
        29, contate come perse)."""
        if self.guardia_dal is None or a <= da:
            return 0
        with self.lock:
            return int(self.db.execute(
                "SELECT COUNT(*) FROM righe r WHERE r.avvio != ? AND r.minore = 1 AND r.fine >= ? "
                "AND r.fine < ? AND r.chi NOT IN ('calliope', 'tv') "
                "AND COALESCE(r.rivolta, '') != 'si' AND TRIM(r.testo) != '' "
                f"AND {_NON_VALUTAZIONE} "
                "AND NOT EXISTS (SELECT 1 FROM guardia_giudicate g WHERE "
                "g.avvio = r.avvio AND g.sat = r.sat AND g.seq = r.seq)",
                (self.avvio, float(da), float(a))).fetchone()[0])

    def oltre_contate_fino(self) -> float | None:
        """Fin dove le righe oltre il limite della ripresa sono già state contate da un avvio di
        prima (18/10, issue #159: ogni riavvio contava di nuovo le stesse). None se mai."""
        if self.guardia_dal is None:
            return None
        with self.lock:
            row = self.db.execute("SELECT valore FROM guardia_meta WHERE chiave = "
                                  "'oltre_fino'").fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def segna_oltre_contate(self, fino: float) -> None:
        """Le righe oltre il limite fino a `fino` sono contate: il riavvio dopo conta il resto."""
        if self.guardia_dal is None:
            return

        def f():
            with self.lock:
                self.db.execute(
                    "INSERT INTO guardia_meta(chiave, valore) VALUES ('oltre_fino', ?) ON "
                    "CONFLICT(chiave) DO UPDATE SET valore = MAX(valore, excluded.valore)",
                    (float(fino),))
                self.db.commit()
        self._lavoro(f)

    def segna_giudicate(self, chiavi, esito: str) -> None:
        """Le righe (avvio, sat, seq) giudicate o buttate per sempre: dopo un riavvio non si
        riprendono. In coda al thread, dopo le scritture delle righe."""
        if self.guardia_dal is None:
            return
        ora = time.time()
        valori = [(str(a), str(s), int(q), str(esito), ora) for a, s, q in chiavi]
        if not valori:
            return

        def f():
            with self.lock:
                self.db.executemany(
                    "INSERT INTO guardia_giudicate(avvio, sat, seq, esito, t) VALUES (?, ?, ?, "
                    "?, ?) ON CONFLICT(avvio, sat, seq) DO UPDATE SET esito = excluded.esito, "
                    "t = excluded.t", valori)
                self.db.commit()
        self._lavoro(f)

    def segna_gioco(self, sat, inizio: float, fine: float) -> None:
        """Un gioco aperto sullo schermo di `sat` da `inizio` a `fine` (nuovo o allungato)."""
        if self.guardia_dal is None:
            return
        s, a, b = str(sat), round(float(inizio), 3), round(float(fine), 3)

        def f():
            with self.lock:
                self.db.execute(
                    "INSERT INTO guardia_giochi(sat, inizio, fine) VALUES (?, ?, ?) ON "
                    "CONFLICT(sat, inizio) DO UPDATE SET fine = max(fine, excluded.fine)",
                    (s, a, b))
                self.db.commit()
        self._lavoro(f)

    def giochi(self, da: float = 0.0) -> list[tuple]:
        """(sat come testo, inizio, fine) dei giochi aperti finiti da `da` in poi."""
        if self.guardia_dal is None:
            return []
        with self.lock:
            return [(r[0], float(r[1]), float(r[2])) for r in self.db.execute(
                "SELECT sat, inizio, fine FROM guardia_giochi WHERE fine >= ? ORDER BY inizio",
                (float(da),))]

    # ── quanto c'è (solo numeri) ──
    def conteggi(self, persona=None) -> dict:
        with self.lock:
            return _conta(self.db, self.path, persona)


def _conta(db, path: str, persona=None) -> dict:
    if persona is not None:
        n = db.execute("SELECT COUNT(*) FROM righe WHERE persona = ?",
                       (str(persona),)).fetchone()[0]
        return {"righe": int(n)}
    n, persone, stanze, prima = db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT persona), COUNT(DISTINCT sat), min(fine) FROM "
        "righe").fetchone()
    minori = db.execute("SELECT COUNT(*) FROM righe WHERE minore = 1").fetchone()[0]
    valut = db.execute("SELECT COUNT(*) FROM righe WHERE sicurezza = ?",
                       (VALUTAZIONE,)).fetchone()[0]
    mb = 0.0
    if path and path != ":memory:":
        for suff in ("", "-wal"):
            try:
                mb += os.path.getsize(path + suff) / 1e6
            except OSError:
                pass
    return {"righe": int(n), "persone": int(persone or 0), "stanze": int(stanze or 0),
            "righe_minori": int(minori), "mb": round(mb, 2),
            **({"righe_valutazione": int(valut)} if valut else {}),
            "giorni": (round((time.time() - float(prima)) / GIORNO_S, 1) if prima else 0.0)}


def conta_file(cfg, persona=None) -> dict | None:
    """I numeri dal file, in sola lettura (`calliope stato --turni`, `calliope conserva`):
    None con la tenuta spenta e senza file."""
    p = percorso_db(cfg)
    if not p.exists():
        return None if not accesa(cfg) else {"righe": 0, "persone": 0, "stanze": 0,
                                             "righe_minori": 0, "mb": 0.0, "giorni": 0.0}
    try:
        db = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return None
    try:
        out = _conta(db, str(p), persona)
        if persona is None:
            out["giorni_tenuta"] = int(getattr(cfg, "stanza_tenuta_giorni", 60) or 60)
            out["accesa"] = accesa(cfg)
        return out
    except sqlite3.Error:
        return None
    finally:
        db.close()


def svuota_file(cfg, persona=None) -> int:
    """`calliope conserva --svuota` da un altro processo: il file della stanza svuotato (tutto o
    una persona), con secure_delete, indice ricompattato e WAL troncato. 0 senza file."""
    p = percorso_db(cfg)
    if not p.exists():
        return 0
    t = Tenuta(p, int(getattr(cfg, "stanza_tenuta_giorni", 60) or 60), log=lambda m: None,
               avvia=False)
    try:
        return t.svuota(persona)
    finally:
        t.chiudi()


def testo_stato(d: dict | None) -> str | None:
    """Una riga per `calliope stato --turni` (sezione «Stanza») e `calliope conserva`."""
    if not d:
        return None
    stato = "accesa" if d.get("accesa", True) else "spenta (il file resta finché non scade)"
    return (f"  Tenuta su disco ({stato}, {d.get('giorni_tenuta', 60)} giorni): {d['righe']} "
            f"righe di {d['persone']} persone in {d['stanze']} stanze (dei minori "
            f"{d['righe_minori']}), {d['mb']:.1f} MB, la più vecchia di {d['giorni']} giorni fa")
