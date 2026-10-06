"""
Il grafo dei documenti di casa, in SQLite (03/10/2026).

Progettato da subito come **grafo completo** (decisione del 02/10: niente doppio lavoro quando
arrivano altri tipi): nodi tipizzati con attributi, archi tipizzati con attributi e con la
**fonte** (il documento che li afferma), alias per la deduplicazione. Un tipo nuovo di nodo o
di relazione è una riga in `TIPI_NODO` o `TIPI_ARCO`: lo schema delle tabelle non cambia.

Tabelle (vedi docs/ricerche/2026-10-03-documenti-grafo.md, §2):

  tipi_nodo, tipi_arco   i tipi ammessi, con la descrizione (anche per l'agente)
  nodi                   id, tipo, chiave (unica per tipo), nome, data, valore, attributi JSON
  archi                  da, rel, a, attributi JSON, fonte (il documento), unico per (da, rel, a, fonte)
  alias                  (tipo, forma) → nodo, con l'origine (piva, cf, nome, simile, manuale)
  file                   percorso → sha256, dimensione, data di modifica, stato, versione
  schede                 il documento: tipo, versione dell'estrattore, scheda JSON, testo, scartati
  testi                  FTS5 sul nome e sul testo dei documenti (rowid = id del documento)

`data` e `valore` sono colonne vere (con indice) e non attributi: le scadenze e le somme le
fanno le query, non il modello. Due viste in sola lettura, `v_documenti` e `v_archi`, sono
quelle su cui ragionano i tool (mai SQL scritto dal modello).

Concorrenza: WAL, una connessione per chi scrive (il thread dell'archivio) e una per chi
legge (la voce, l'agente), ognuna con il suo lock: una lettura non aspetta una scrittura.
"""

import datetime
import json
import sqlite3
import threading

from . import normalizza as nz
from ..persistenza import apri_db

# Il grafo si estende qui: un tipo nuovo è una riga, lo schema delle tabelle non cambia
TIPI_NODO: dict[str, str] = {
    "documento": "un documento archiviato (bolletta, ricevuta, contratto, polizza, garanzia, "
                 "referto, documento d'identità, manuale): data = data del documento, "
                 "valore = importo totale in euro",
    "persona": "una persona: intestatario, contraente, titolare, paziente, medico",
    "ente": "un'azienda, un ente o un professionista che emette documenti",
    "importo": "una cifra in euro di un documento (totale, canone, premio, una voce): "
               "valore = la cifra, data = la data del documento",
    "scadenza": "una data da ricordare (pagamento, fine validità, disdetta, fine garanzia): "
                "data = il giorno",
    "bene": "un oggetto o un servizio: auto (targa), elettrodomestico (matricola), fornitura "
            "(POD, PDR), linea telefonica",
    "luogo": "un indirizzo o un immobile",
    "categoria": "di cosa si tratta: luce, gas, acqua, telefono, internet, auto, salute…",
}

# nome: (tipi di partenza, tipi di arrivo, descrizione)
TIPI_ARCO: dict[str, tuple[frozenset, frozenset, str]] = {
    "emesso_da": (frozenset({"documento"}), frozenset({"ente"}),
                  "il documento è emesso da un ente (fornitore, negozio, compagnia)"),
    "intestato_a": (frozenset({"documento"}), frozenset({"persona"}),
                    "il documento è intestato a una persona (intestatario, contraente, "
                    "titolare, paziente)"),
    "redatto_da": (frozenset({"documento"}), frozenset({"persona", "ente"}),
                   "chi ha firmato o redatto il documento (medico, struttura)"),
    "riguarda": (frozenset({"documento"}), frozenset({"bene", "luogo", "categoria", "persona"}),
                 "di cosa parla il documento"),
    "copre": (frozenset({"documento"}), frozenset({"bene"}),
              "la garanzia o la polizza copre un bene"),
    "ha_importo": (frozenset({"documento"}), frozenset({"importo"}),
                   "una cifra del documento (attributo voce: totale, canone, premio…)"),
    "scade_il": (frozenset({"documento"}), frozenset({"scadenza"}),
                 "una scadenza del documento (attributo cosa: pagamento, fine_validita…)"),
    "paga": (frozenset({"persona"}), frozenset({"importo"}),
             "chi paga un importo (l'intestatario di bollette, ricevute, contratti, polizze)"),
    "fornisce": (frozenset({"ente"}), frozenset({"bene"}),
                 "l'ente fornisce un servizio (la fornitura di luce con quel POD)"),
    "si_trova_in": (frozenset({"bene"}), frozenset({"luogo"}),
                    "dove si trova un bene o una fornitura"),
    "rinnova": (frozenset({"documento"}), frozenset({"documento"}),
                "il documento rinnova o sostituisce un altro"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (chiave TEXT PRIMARY KEY, valore TEXT);
CREATE TABLE IF NOT EXISTS tipi_nodo (nome TEXT PRIMARY KEY, descrizione TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tipi_arco (nome TEXT PRIMARY KEY, da TEXT NOT NULL, a TEXT NOT NULL,
                                      descrizione TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nodi (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL REFERENCES tipi_nodo(nome),
    chiave TEXT NOT NULL,
    nome TEXT NOT NULL,
    data TEXT,
    valore REAL,
    attributi TEXT NOT NULL DEFAULT '{}',
    creato TEXT NOT NULL,
    aggiornato TEXT NOT NULL,
    UNIQUE (tipo, chiave));
CREATE INDEX IF NOT EXISTS nodi_tipo_data ON nodi(tipo, data);
CREATE TABLE IF NOT EXISTS archi (
    id INTEGER PRIMARY KEY,
    da INTEGER NOT NULL REFERENCES nodi(id) ON DELETE CASCADE,
    rel TEXT NOT NULL REFERENCES tipi_arco(nome),
    a INTEGER NOT NULL REFERENCES nodi(id) ON DELETE CASCADE,
    attributi TEXT NOT NULL DEFAULT '{}',
    fonte INTEGER REFERENCES nodi(id) ON DELETE CASCADE,
    UNIQUE (da, rel, a, fonte));
CREATE INDEX IF NOT EXISTS archi_da ON archi(da, rel);
CREATE INDEX IF NOT EXISTS archi_a ON archi(a, rel);
CREATE INDEX IF NOT EXISTS archi_fonte ON archi(fonte);
CREATE TABLE IF NOT EXISTS alias (
    tipo TEXT NOT NULL,
    forma TEXT NOT NULL,
    nodo INTEGER NOT NULL REFERENCES nodi(id) ON DELETE CASCADE,
    origine TEXT NOT NULL,
    PRIMARY KEY (tipo, forma));
CREATE INDEX IF NOT EXISTS alias_nodo ON alias(nodo);
CREATE TABLE IF NOT EXISTS file (
    percorso TEXT PRIMARY KEY,
    sha256 TEXT,
    dimensione INTEGER,
    mtime REAL,
    stato TEXT NOT NULL,
    errore TEXT,
    versione TEXT,
    nodo INTEGER REFERENCES nodi(id) ON DELETE SET NULL,
    aggiornato TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS file_sha ON file(sha256);
CREATE TABLE IF NOT EXISTS schede (
    nodo INTEGER PRIMARY KEY REFERENCES nodi(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    versione TEXT NOT NULL,
    scheda TEXT NOT NULL,
    testo TEXT NOT NULL,
    metodo TEXT,
    versione_testo TEXT,
    scartati TEXT NOT NULL DEFAULT '[]');
CREATE VIRTUAL TABLE IF NOT EXISTS testi USING fts5(
    nome, testo, tokenize = 'unicode61 remove_diacritics 2');
CREATE VIEW IF NOT EXISTS v_documenti AS
    SELECT n.id, n.nome, n.data, n.valore AS totale,
           json_extract(n.attributi, '$.tipo_doc') AS tipo_doc,
           json_extract(n.attributi, '$.categoria') AS categoria,
           json_extract(n.attributi, '$.visibilita') AS visibilita,
           json_extract(n.attributi, '$.cartella') AS cartella,
           json_extract(n.attributi, '$.file') AS file
    FROM nodi n WHERE n.tipo = 'documento';
CREATE VIEW IF NOT EXISTS v_archi AS
    SELECT r.id, r.da, d.tipo AS da_tipo, d.nome AS da_nome, r.rel, r.a, b.tipo AS a_tipo,
           b.nome AS a_nome, b.data AS a_data, b.valore AS a_valore, r.attributi, r.fonte
    FROM archi r JOIN nodi d ON d.id = r.da JOIN nodi b ON b.id = r.a;
"""

VERSIONE_SCHEMA = "1"


class ErroreGrafo(Exception):
    pass


def _ora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _connetti(path: str) -> sqlite3.Connection:
    # isolation_level=None: le transazioni le apre e chiude _Transazione (BEGIN IMMEDIATE)
    db = apri_db(path, isolation_level=None, foreign_keys=True)
    db.row_factory = sqlite3.Row
    return db


class Grafo:
    def __init__(self, path: str):
        self.path = str(path)
        self._w = _connetti(self.path)
        try:
            self._w.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        self._w.executescript(SCHEMA)
        # La versione dello schema si legge (03/10): una versione vecchia di Calliope la
        # riscriveva al ribasso. Più nuova di questa: sola lettura, e lo dice il registro
        row = self._w.execute("SELECT valore FROM meta WHERE chiave = 'schema'").fetchone()
        self.scrivibile = not (row and str(row[0]).isdigit()
                               and int(row[0]) > int(VERSIONE_SCHEMA))
        if not self.scrivibile:
            self._w.execute("PRAGMA query_only = ON")
            print(f"[ARCHIVIO] {self.path}: schema {row[0]}, più nuovo di questa versione "
                  f"({VERSIONE_SCHEMA}): lo apro in sola lettura", flush=True)
            from .. import capacita
            capacita.segnala("archivio", "guasta", "archivio di una versione più nuova: sola "
                             "lettura", "Torna alla versione nuova (calliope aggiorna) o rimetti "
                             "i dati di allora (calliope torna --con-dati).")
            self._r = _connetti(self.path)
            self._r.execute("PRAGMA query_only = ON")
            self._wlock = threading.RLock()
            self._rlock = threading.Lock()
            return
        self._w.execute("INSERT INTO meta (chiave, valore) VALUES ('schema', ?) ON CONFLICT"
                        "(chiave) DO UPDATE SET valore = excluded.valore", (VERSIONE_SCHEMA,))
        # I tipi si aggiornano (descrizioni nuove, tipi nuovi) senza toccare i nodi che li usano
        self._w.executemany("INSERT INTO tipi_nodo (nome, descrizione) VALUES (?, ?) "
                            "ON CONFLICT(nome) DO UPDATE "
                            "SET descrizione = excluded.descrizione", TIPI_NODO.items())
        self._w.executemany("INSERT INTO tipi_arco (nome, da, a, descrizione) VALUES "
                            "(?, ?, ?, ?) ON CONFLICT(nome) DO "
                            "UPDATE SET da = excluded.da, a = excluded.a, "
                            "descrizione = excluded.descrizione",
                            [(k, json.dumps(sorted(d)), json.dumps(sorted(a)), desc)
                             for k, (d, a, desc) in TIPI_ARCO.items()])
        self._wlock = threading.RLock()
        self._r = _connetti(self.path)
        self._r.execute("PRAGMA query_only = ON")
        self._rlock = threading.Lock()

    def close(self):
        for db in (self._r, self._w):
            try:
                db.close()
            except sqlite3.Error:
                pass

    # ─────────────────────────── lettura ───────────────────────────
    def leggi(self, sql: str, params=()) -> list[sqlite3.Row]:
        """Query in sola lettura (connessione con query_only): solo dal codice di Calliope,
        mai testo scritto dal modello."""
        with self._rlock:
            return self._r.execute(sql, params).fetchall()

    def nodo_info(self, nid: int) -> dict | None:
        rows = self.leggi("SELECT * FROM nodi WHERE id = ?", (nid,))
        return riga_nodo(rows[0]) if rows else None

    # ─────────────────────────── scrittura ───────────────────────────
    def transazione(self):
        """`with grafo.transazione() as db:` una scrittura atomica (thread dell'archivio)."""
        return _Transazione(self)

    def nodo(self, db, tipo: str, chiave: str, nome: str, data: str | None = None,
             valore: float | None = None, attributi: dict | None = None) -> int:
        """Crea o aggiorna il nodo (tipo, chiave). Gli attributi si uniscono a quelli che c'erano."""
        if tipo not in TIPI_NODO:
            raise ErroreGrafo(f"tipo di nodo sconosciuto: {tipo}")
        row = db.execute("SELECT id, attributi FROM nodi WHERE tipo = ? AND chiave = ?",
                         (tipo, chiave)).fetchone()
        now = _ora()
        if row is None:
            cur = db.execute("INSERT INTO nodi (tipo, chiave, nome, data, valore, attributi, "
                             "creato, aggiornato) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (tipo, chiave, nome, data, valore,
                              json.dumps(attributi or {}, ensure_ascii=False), now, now))
            return cur.lastrowid
        attrs = json.loads(row["attributi"] or "{}")
        attrs.update({k: v for k, v in (attributi or {}).items() if v is not None})
        db.execute("UPDATE nodi SET nome = ?, data = COALESCE(?, data), "
                   "valore = COALESCE(?, valore), attributi = ?, aggiornato = ? WHERE id = ?",
                   (nome, data, valore, json.dumps(attrs, ensure_ascii=False), now, row["id"]))
        return row["id"]

    def entita(self, db, tipo: str, nome: str, attributi: dict | None = None, **ids) -> int | None:
        """Il nodo di un'entità (persona, ente, bene, luogo, categoria), deduplicato con le
        regole di normalizza.py e la tabella degli alias. None se non c'è niente per
        riconoscerla."""
        keys = nz.chiavi(tipo, nome, **ids)
        if not keys:
            return None
        strong = [k for k in keys if nz.forte(k)]

        def conflitto(nodo: int) -> bool:
            """Il nodo ha già un identificativo forte dello stesso genere ma diverso: è
            un'altra entità con lo stesso nome (due aziende omonime, due Mario Rossi)."""
            if not strong:
                return False
            prefix = strong[0].split(":", 1)[0] + ":"
            return any(r["forma"].startswith(prefix) and r["forma"] != strong[0]
                       for r in db.execute("SELECT forma FROM alias WHERE nodo = ?", (nodo,)))
        found = None
        for k in keys:                       # prima l'identificativo forte, poi il nome
            row = db.execute("SELECT nodo FROM alias WHERE tipo = ? AND forma = ?",
                             (tipo, k)).fetchone()
            if row is not None and (nz.forte(k) or not conflitto(row["nodo"])):
                found = row["nodo"]
                break
        if found is None:
            name_key = next((k for k in keys if not nz.forte(k)), None)
            if name_key:
                for r in db.execute("SELECT forma, nodo FROM alias WHERE tipo = ? AND "
                                    "forma LIKE 'nome:%'", (tipo,)).fetchall():
                    if nz.simile(r["forma"], name_key) and not conflitto(r["nodo"]):
                        found = r["nodo"]
                        break
        if found is None:
            found = self.nodo(db, tipo, keys[0], nome.strip() or keys[0], attributi=attributi)
        else:
            row = db.execute("SELECT attributi FROM nodi WHERE id = ?", (found,)).fetchone()
            attrs = json.loads(row["attributi"] or "{}")
            attrs.update({k: v for k, v in (attributi or {}).items() if v is not None})
            db.execute("UPDATE nodi SET attributi = ?, aggiornato = ? WHERE id = ?",
                       (json.dumps(attrs, ensure_ascii=False), _ora(), found))
        for k in keys:
            origine = k.split(":", 1)[0]
            db.execute("INSERT OR IGNORE INTO alias (tipo, forma, nodo, origine) "
                       "VALUES (?, ?, ?, ?)",
                       (tipo, k, found, origine if nz.forte(k) else "nome"))
        return found

    def arco(self, db, da: int, rel: str, a: int, fonte: int | None,
             attributi: dict | None = None):
        if rel not in TIPI_ARCO:
            raise ErroreGrafo(f"relazione sconosciuta: {rel}")
        tipi = {r["id"]: r["tipo"] for r in db.execute(
            "SELECT id, tipo FROM nodi WHERE id IN (?, ?)", (da, a))}
        dal, al, _ = TIPI_ARCO[rel]
        if tipi.get(da) not in dal or tipi.get(a) not in al:
            raise ErroreGrafo(f"{rel} non va da {tipi.get(da)} a {tipi.get(a)}")
        db.execute("INSERT OR IGNORE INTO archi (da, rel, a, attributi, fonte) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (da, rel, a, json.dumps(attributi or {}, ensure_ascii=False), fonte))

    def togli_fonte(self, db, doc: int):
        """Toglie tutto quello che il documento affermava (archi e nodi solo suoi): prima di
        rielaborarlo o quando il file sparisce."""
        db.execute("DELETE FROM archi WHERE fonte = ?", (doc,))
        db.execute("DELETE FROM nodi WHERE tipo IN ('importo', 'scadenza') AND "
                   "chiave LIKE ?", (f"doc:{doc}:%",))
        self.pulisci(db)

    def pulisci(self, db):
        """Nodi rimasti senza archi (un'azienda che compariva solo in un documento tolto). Si
        tengono quelli con un alias messo a mano."""
        db.execute("""DELETE FROM nodi WHERE tipo NOT IN ('documento') AND id NOT IN
                      (SELECT da FROM archi UNION SELECT a FROM archi)
                      AND id NOT IN (SELECT nodo FROM alias WHERE origine = 'manuale')""")

    def togli_documento(self, db, doc: int):
        self.togli_fonte(db, doc)
        db.execute("DELETE FROM testi WHERE rowid = ?", (doc,))
        db.execute("DELETE FROM nodi WHERE id = ?", (doc,))
        self.pulisci(db)

    def unisci(self, tenere: int, togliere: int) -> bool:
        """Unisce due nodi dello stesso tipo (deduplicazione a mano): archi e alias passano a
        `tenere`, e i nomi di `togliere` restano come alias «manuale»."""
        with self.transazione() as db:
            a = db.execute("SELECT tipo, chiave FROM nodi WHERE id = ?", (tenere,)).fetchone()
            b = db.execute("SELECT tipo, chiave FROM nodi WHERE id = ?", (togliere,)).fetchone()
            if a is None or b is None or a["tipo"] != b["tipo"] or tenere == togliere:
                return False
            for col in ("da", "a"):
                for r in db.execute(f"SELECT id, da, rel, a, fonte FROM archi WHERE {col} = ?",
                                    (togliere,)).fetchall():
                    nd = tenere if r["da"] == togliere else r["da"]
                    na = tenere if r["a"] == togliere else r["a"]
                    db.execute("INSERT OR IGNORE INTO archi (da, rel, a, attributi, fonte) "
                               "SELECT ?, rel, ?, attributi, fonte FROM archi WHERE id = ?",
                               (nd, na, r["id"]))
                    db.execute("DELETE FROM archi WHERE id = ?", (r["id"],))
            db.execute("UPDATE alias SET nodo = ?, origine = 'manuale' WHERE nodo = ?",
                       (tenere, togliere))
            db.execute("INSERT OR IGNORE INTO alias (tipo, forma, nodo, origine) "
                       "VALUES (?, ?, ?, 'manuale')",
                       (b["tipo"], b["chiave"], tenere))
            db.execute("DELETE FROM nodi WHERE id = ?", (togliere,))
        return True

    # ─────────────────────────── statistiche ───────────────────────────
    def conteggi(self) -> dict:
        nodi = {r["tipo"]: r["n"] for r in self.leggi(
            "SELECT tipo, COUNT(*) AS n FROM nodi GROUP BY tipo")}
        archi = {r["rel"]: r["n"] for r in self.leggi(
            "SELECT rel, COUNT(*) AS n FROM archi GROUP BY rel")}
        return {"nodi": nodi, "archi": archi}


class _Transazione:
    def __init__(self, g: Grafo):
        self.g = g

    def __enter__(self):
        self.g._wlock.acquire()
        self.g._w.execute("BEGIN IMMEDIATE")
        return self.g._w

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.g._w.execute("COMMIT")
            else:
                self.g._w.execute("ROLLBACK")
        finally:
            self.g._wlock.release()
        return False


def riga_nodo(r) -> dict:
    d = {"id": r["id"], "tipo": r["tipo"], "nome": r["nome"]}
    if r["data"]:
        d["data"] = r["data"]
    if r["valore"] is not None:
        d["valore"] = r["valore"]
    attrs = json.loads(r["attributi"] or "{}")
    if attrs:
        d["attributi"] = attrs
    return d
