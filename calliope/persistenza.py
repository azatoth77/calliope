"""
Persistenza comune (03/10/2026, analisi di robustezza): come si apre `memoria.db` e come si
scrivono i file di stato, uguale per tutti i servizi.

- `apri_db(path)`: una connessione SQLite in WAL con un `busy_timeout` lungo. Prima ogni
  servizio apriva `memoria.db` a modo suo (journal di rollback, timeout di 5 s): una
  fattura che teneva il blocco più di 5 s faceva morire il thread dell'agenda al primo
  «database is locked». Con il WAL i lettori non aspettano mai lo scrittore, e gli
  scrittori si aspettano fino a `ATTESA_S`. Ogni servizio tiene **una** connessione e un
  suo lock (`threading.Lock`) attorno a ogni uso: `check_same_thread=False` è sicuro solo
  così.
- `scrivi_atomico(path, dati)`: file temporaneo nella stessa cartella, `fsync`,
  `os.replace`; con `copia=True` la versione buona di prima resta in `<nome>.bak`. Una
  corrente che salta a metà lascia il file vecchio intero, mai uno troncato.
- `leggi_json(path)`: il file, o la sua copia `.bak` se il file è rovinato; dice quale.
- `versione_schema` / `migra`: una tabella `meta_schema` con la versione di ogni modulo
  nello stesso database e migrazioni numerate. Una versione di Calliope più vecchia che
  trova uno schema più nuovo (dopo `calliope torna` senza i dati) lo dice e non scrive.

Solo la libreria standard: va anche su Windows ARM e sulla DGX.
"""

import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path

ATTESA_S = 30.0          # quanto uno scrittore aspetta un altro (busy_timeout)


def apri_db(path, *, timeout: float = ATTESA_S, isolation_level: str | None = "",
            foreign_keys: bool = False, wal: bool = True,
            check_same_thread: bool = False) -> sqlite3.Connection:
    """Apre un database SQLite con le impostazioni comuni (WAL, busy_timeout, synchronous
    NORMAL con il WAL). `isolation_level=None` per chi apre le transazioni da sé
    (BEGIN IMMEDIATE)."""
    db = sqlite3.connect(str(path), timeout=timeout, isolation_level=isolation_level,
                         check_same_thread=check_same_thread)
    db.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    if wal and str(path) != ":memory:" and not str(path).startswith("file::memory:"):
        try:
            modo = db.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(modo).lower() == "wal":
                # Con il WAL «NORMAL» è sicuro contro i crash del processo (un'interruzione di
                # corrente può perdere solo le ultime transazioni, mai rovinare il file)
                db.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.DatabaseError:
            pass                 # un file system che non regge il WAL: resta il journal
    if foreign_keys:
        db.execute("PRAGMA foreign_keys = ON")
    return db


# ─────────────────────────── versioni dello schema ───────────────────────────
class SchemaPiuNuovo(RuntimeError):
    """Il database è stato scritto da una versione di Calliope più nuova di questa."""


_schema_lock = threading.Lock()


def versione_schema(db: sqlite3.Connection, modulo: str) -> int:
    """La versione dello schema di `modulo` nel database (0 se mai registrata)."""
    db.execute("CREATE TABLE IF NOT EXISTS meta_schema (modulo TEXT PRIMARY KEY, "
               "versione INTEGER NOT NULL)")
    row = db.execute("SELECT versione FROM meta_schema WHERE modulo = ?",
                     (modulo,)).fetchone()
    return int(row[0]) if row else 0


def migra(db: sqlite3.Connection, modulo: str, migrazioni: list) -> int:
    """Porta lo schema di `modulo` all'ultima versione: `migrazioni[i]` è una funzione
    `f(db)` che va dalla versione i alla i+1 (la prima crea le tabelle; tutte idempotenti,
    perché un database di prima delle versioni ha già le tabelle). Regola per le nuove:
    solo colonne con NULL ammesso o con un predefinito, e INSERT sempre con l'elenco
    delle colonne, così una versione vecchia continua a scrivere.

    Se il database ha una versione **più nuova** di quelle conosciute solleva
    SchemaPiuNuovo (prima di scrivere qualunque cosa). Restituisce la versione."""
    with _schema_lock:
        ver = versione_schema(db, modulo)
        ultima = len(migrazioni)
        if ver > ultima:
            raise SchemaPiuNuovo(
                f"il database ha lo schema «{modulo}» alla versione {ver}, questa versione di "
                f"Calliope conosce fino alla {ultima}: è stato scritto da una versione più "
                f"nuova (calliope torna senza i dati?)")
        for i in range(ver, ultima):
            migrazioni[i](db)
            db.execute("INSERT INTO meta_schema (modulo, versione) VALUES (?, ?) "
                       "ON CONFLICT(modulo) DO UPDATE SET versione = excluded.versione",
                       (modulo, i + 1))
        if db.in_transaction:
            db.commit()
        return ultima


def aggiungi_colonna(db: sqlite3.Connection, tabella: str, colonna: str, tipo: str):
    """ALTER TABLE … ADD COLUMN solo se la colonna manca (migrazioni idempotenti)."""
    cols = {r[1] for r in db.execute(f"PRAGMA table_info({tabella})")}
    if colonna not in cols:
        db.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {tipo}")


# ─────────────────────────── file di stato ───────────────────────────
def scrivi_atomico(path, dati, copia: bool = False, encoding: str = "utf-8"):
    """Scrive `dati` (str o bytes) in `path` in modo atomico: temporaneo nella stessa
    cartella, fsync, os.replace. Con `copia` la versione di prima (se c'è) diventa
    `<path>.bak`, sempre intera anche lei."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = dati.encode(encoding) if isinstance(dati, str) else bytes(dati)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if copia and path.exists():
            bak = path.with_name(path.name + ".bak")
            fd2, tmp2 = tempfile.mkstemp(prefix=bak.name + ".", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd2, "wb") as f:
                    f.write(path.read_bytes())
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp2, bak)
            except BaseException:
                _togli(tmp2)
                raise
        os.replace(tmp, path)
    except BaseException:
        _togli(tmp)
        raise


def _togli(p):
    try:
        os.unlink(p)
    except OSError:
        pass


def scrivi_json(path, oggetto, copia: bool = False, **kw):
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("indent", 2)
    scrivi_atomico(path, json.dumps(oggetto, **kw), copia=copia)


class FileRovinato(ValueError):
    """Il file c'è ma non si legge, e nemmeno la sua copia `.bak`."""


def leggi_json(path):
    """(dati, da_dove): da_dove è "file", "bak" (il file è rovinato, vale la copia) o
    None (nessuno dei due esiste). Solleva FileRovinato se il file c'è ma né lui né la
    copia si leggono: chi chiama non deve mai scambiarlo per «nessun file»."""
    path = Path(path)
    bak = path.with_name(path.name + ".bak")
    errore = None
    for p, quale in ((path, "file"), (bak, "bak")):
        if not p.exists():
            continue
        try:
            return json.loads(p.read_text(encoding="utf-8")), quale
        except (OSError, ValueError) as e:
            errore = errore or e
    if errore is not None:
        raise FileRovinato(f"{path.name} non si legge ({errore}) e non c'è una copia buona")
    return None, None


def prepara_schema(db: sqlite3.Connection, modulo: str, migrazioni: list,
                   capacita_nome: str = "memoria") -> bool:
    """`migra` per i servizi: True se il database è scrivibile. Con uno schema più nuovo di
    questa versione di Calliope la connessione passa in sola lettura (`query_only`): le
    letture vanno, ogni scrittura fallisce con un errore (detto come gli altri), il file non
    si tocca; il registro delle capacità lo dice con il passo."""
    try:
        migra(db, modulo, migrazioni)
        return True
    except SchemaPiuNuovo as e:
        db.execute("PRAGMA query_only = ON")
        print(f"[DATI] {e}: lo apro in sola lettura", flush=True)
        try:
            from . import capacita
            capacita.segnala(capacita_nome, "guasta",
                             f"dati di una versione più nuova ({modulo}): sola lettura",
                             "Questa versione di Calliope è più vecchia dei suoi dati: torna "
                             "alla versione nuova (calliope aggiorna), oppure rimetti i dati "
                             "di allora (calliope torna --con-dati).")
        except Exception:  # noqa: BLE001
            pass
        return False
