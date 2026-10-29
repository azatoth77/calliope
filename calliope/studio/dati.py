"""
I dati dello Studio in `memoria.db` (29/10, passo 4.1, issue #280, decisione 0035), nello stile
di `memory.py` e `conserva.py`: tabelle `studio_*` con la versione in `meta_schema` (modulo
«studio», `persistenza.prepara_schema`), una connessione e un lock.

Tabelle (versione 1):
- `studio_verifiche`: di chi è (`persona`, l'id del profilo, mai un nome), materia, argomento
  generale, data, classe o livello, obiettivo di padronanza in %, minuti al giorno (None = di
  serie), stato (bozza → aperta → fatta, oppure archiviata), chi l'ha creata, il giorno
  dell'ultimo calcolo del piano;
- `studio_materiali`: i materiali di una verifica (origine foto, cassetto, file, biblioteca,
  mano; titolo scelto dalla persona; il riferimento all'origine). Il caricamento vero arriva con
  il passo 4.2;
- `studio_pagine`: le pagine di un materiale, solo i riferimenti (ordine, numero letto,
  etichetta, stato, file nella cartella dello Studio); il testo letto (`testo`, `metodo`) lo
  scrive la lettura del passo 4.3 ed è un dato non fidato;
- `studio_argomenti`: gli argomenti con le pagine che citano (id, JSON), lo stato (proposto,
  tenuto, tolto, aggiunto dalla persona) e l'ordine; l'estrazione arriva con il passo 4.4, qui
  c'è la conferma a mano;
- `studio_piano`: un giorno per riga (fase, pagine, attività, minuti, fatto);
- `studio_giorni`: i giorni di una persona con minuti diversi (0 = senza piano: giorno senza
  scuola, giorno saltato con «non ce la faccio oggi»);
- `studio_misure`: le misure vere della padronanza (dal passo 5), per la previsione.

Tenuta (decisione 0035, punto 4): tutto ciò che è di una verifica resta fino a
`studio_tenuta_giorni` (60) giorni dopo la sua data, per sempre se archiviata; «dimentica le
nostre conversazioni» toglie lo Studio della persona tranne le verifiche archiviate (tenute di
proposito, come le foto archiviate della 0034); `calliope conserva --svuota` toglie tutto.
Sempre con `secure_delete`, e con i file delle pagine dentro la cartella dello Studio.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import threading
from pathlib import Path

from ..persistenza import apri_db, prepara_schema

MODULO = "studio"

# Le tabelle dello Studio, figlie prima dei genitori (l'ordine delle cancellazioni)
TABELLE = ("studio_piano", "studio_misure", "studio_argomenti", "studio_pagine",
           "studio_materiali", "studio_verifiche", "studio_giorni")

STATI_VERIFICA = ("bozza", "aperta", "fatta", "archiviata")
ORIGINI = ("foto", "cassetto", "file", "biblioteca", "mano")
STATI_PAGINA = ("da_controllare", "buona", "sfocata", "tolta", "letta", "illeggibile")
STATI_ARGOMENTO = ("proposto", "tenuto", "tolto", "aggiunto")
# Gli argomenti su cui si fa il piano
ARGOMENTI_DEL_PIANO = ("tenuto", "aggiunto")


def _v1(db: sqlite3.Connection):
    db.execute("""CREATE TABLE IF NOT EXISTS studio_verifiche (
        id INTEGER PRIMARY KEY,
        persona TEXT NOT NULL,
        materia TEXT NOT NULL,
        argomento TEXT,
        data TEXT NOT NULL,
        livello TEXT,
        obiettivo INTEGER NOT NULL DEFAULT 75,
        minuti_giorno INTEGER,
        stato TEXT NOT NULL DEFAULT 'bozza',
        creata TEXT NOT NULL,
        creata_da TEXT,
        archiviata TEXT,
        piano_del TEXT,
        piano_avvisi TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_verifiche_persona "
               "ON studio_verifiche(persona)")
    db.execute("""CREATE TABLE IF NOT EXISTS studio_materiali (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        origine TEXT NOT NULL,
        titolo TEXT,
        riferimento TEXT,
        creato TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_materiali_verifica "
               "ON studio_materiali(verifica)")
    db.execute("""CREATE TABLE IF NOT EXISTS studio_pagine (
        id INTEGER PRIMARY KEY,
        materiale INTEGER NOT NULL,
        ordine INTEGER NOT NULL,
        numero TEXT,
        etichetta TEXT,
        stato TEXT NOT NULL DEFAULT 'da_controllare',
        file TEXT,
        testo TEXT,
        metodo TEXT,
        creata TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_pagine_materiale ON studio_pagine(materiale)")
    db.execute("""CREATE TABLE IF NOT EXISTS studio_argomenti (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        titolo TEXT NOT NULL,
        pagine TEXT NOT NULL DEFAULT '[]',
        stato TEXT NOT NULL DEFAULT 'proposto',
        ordine INTEGER NOT NULL DEFAULT 0,
        avvisi TEXT,
        creato TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_argomenti_verifica "
               "ON studio_argomenti(verifica)")
    db.execute("""CREATE TABLE IF NOT EXISTS studio_piano (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        giorno TEXT NOT NULL,
        fase TEXT NOT NULL,
        pagine TEXT NOT NULL DEFAULT '[]',
        attivita TEXT NOT NULL,
        minuti INTEGER NOT NULL DEFAULT 0,
        oltre INTEGER NOT NULL DEFAULT 0,
        fatto TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_piano_verifica ON studio_piano(verifica)")
    db.execute("""CREATE TABLE IF NOT EXISTS studio_giorni (
        persona TEXT NOT NULL,
        giorno TEXT NOT NULL,
        minuti INTEGER NOT NULL,
        motivo TEXT,
        PRIMARY KEY (persona, giorno))""")
    db.execute("""CREATE TABLE IF NOT EXISTS studio_misure (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        argomento INTEGER,
        giorno TEXT NOT NULL,
        valore REAL NOT NULL,
        fonte TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_misure_verifica ON studio_misure(verifica)")


# Le versioni dello schema: si aggiungono in fondo, solo colonne con NULL o un predefinito
MIGRAZIONI = [_v1]


def adesso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def j(valore) -> str:
    return json.dumps(list(valore or ()), ensure_ascii=False)


def da_j(testo) -> list:
    try:
        v = json.loads(testo or "[]")
    except (TypeError, ValueError):
        return []
    return v if isinstance(v, list) else []


class Dati:
    """La connessione dello Studio a `memoria.db`, con il suo lock (persistenza.apri_db)."""

    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        self.db = apri_db(self.path)
        self.db.row_factory = sqlite3.Row
        self.scrivibile = prepara_schema(self.db, MODULO, MIGRAZIONI)

    def close(self):
        with self.lock:
            self.db.close()

    def uno(self, sql: str, arg=()) -> dict | None:
        with self.lock:
            r = self.db.execute(sql, arg).fetchone()
        return dict(r) if r is not None else None

    def tutti(self, sql: str, arg=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, arg).fetchall()]

    def scrivi(self, sql: str, arg=()) -> int:
        """Una scrittura con commit; l'id della riga nuova (o il numero di righe)."""
        with self.lock:
            c = self.db.execute(sql, arg)
            self.db.commit()
            return c.lastrowid if sql.lstrip().upper().startswith("INSERT") else c.rowcount


# ─────────────────────────── cancellare (tenuta, dimentica, svuota) ───────────────────────────

def _c_e(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND "
                      "name = 'studio_verifiche'").fetchone() is not None


def _togli_verifiche(db: sqlite3.Connection, ids: list[int]) -> list[str]:
    """Cancella le verifiche e tutto ciò che è loro (dentro una transazione già aperta). I file
    delle pagine tolte, da togliere dal disco dopo il commit."""
    file = []
    for vid in ids:
        mats = [r[0] for r in db.execute("SELECT id FROM studio_materiali WHERE verifica = ?",
                                         (vid,))]
        for m in mats:
            file += [r[0] for r in db.execute(
                "SELECT file FROM studio_pagine WHERE materiale = ? AND file IS NOT NULL", (m,))]
            db.execute("DELETE FROM studio_pagine WHERE materiale = ?", (m,))
        for t in ("studio_materiali", "studio_argomenti", "studio_piano", "studio_misure"):
            db.execute(f"DELETE FROM {t} WHERE verifica = ?", (vid,))
        db.execute("DELETE FROM studio_verifiche WHERE id = ?", (vid,))
    return file


def togli_file(file: list[str], cartella) -> int:
    """I file delle pagine dentro `cartella` (la cartella dello Studio); un percorso fuori non
    si tocca mai. Quanti tolti."""
    if not cartella or not file:
        return 0
    base = Path(cartella).resolve()
    n = 0
    for f in file:
        try:
            p = (base / f).resolve()
            if base not in p.parents:
                continue
            if p.exists():
                p.unlink()
                n += 1
        except OSError:
            continue
    return n


def cancella(db: sqlite3.Connection, *, persona: str | None = None, tutto: bool = False,
             scadute_prima: datetime.date | None = None, archiviate: bool = True,
             cartella=None) -> dict:
    """Il solo posto che cancella lo Studio, con `secure_delete` e in una transazione:
    - `tutto`: ogni verifica e ogni giorno (`svuota` di tutti);
    - `persona`: le verifiche di una persona e i suoi giorni; con `archiviate=False` quelle
      archiviate restano («dimentica»);
    - `scadute_prima`: le verifiche non archiviate con la data prima di quel giorno e i giorni
      segnati delle persone prima di quel giorno (la tenuta).
    Restituisce quante verifiche e quanti file. Senza le tabelle (Studio mai usato) niente."""
    out = {"verifiche": 0, "file": 0}
    if not _c_e(db):
        return out
    if tutto:
        q, arg = "SELECT id FROM studio_verifiche", ()
    elif persona is not None:
        q, arg = "SELECT id FROM studio_verifiche WHERE persona = ?", (str(persona),)
        if not archiviate:
            q += " AND stato != 'archiviata'"
    elif scadute_prima is not None:
        q, arg = ("SELECT id FROM studio_verifiche WHERE stato != 'archiviata' AND data < ?",
                  (scadute_prima.isoformat(),))
    else:
        return out
    if db.in_transaction:
        db.commit()
    prima = db.execute("PRAGMA secure_delete").fetchone()[0]
    db.execute("PRAGMA secure_delete = ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        ids = [r[0] for r in db.execute(q, arg)]
        giorni = 0
        file = _togli_verifiche(db, ids)
        if tutto:
            db.execute("DELETE FROM studio_giorni")
        elif persona is not None:
            db.execute("DELETE FROM studio_giorni WHERE persona = ?", (str(persona),))
        else:
            # I giorni di una persona («non ce la faccio oggi», senza scuola, minuti diversi)
            # scadono con lo stesso limite (revisione della PR #308): dati personali, anche dei
            # minori, mai per sempre
            giorni = db.execute("DELETE FROM studio_giorni WHERE giorno < ?",
                                (scadute_prima.isoformat(),)).rowcount or 0
        db.commit()
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.execute(f"PRAGMA secure_delete = {int(prima)}")
    out["verifiche"] = len(ids)
    out["giorni"] = giorni
    out["file"] = togli_file(file, cartella)
    return out


def cancella_file(path, log=print, **kw) -> dict:
    """`cancella` sul file della memoria, aprendolo e chiudendolo (conservazione e terminale).
    Un file che non c'è, o che non si apre, non ferma niente."""
    out = {"verifiche": 0, "file": 0}
    if not path or not Path(path).exists():
        return out
    try:
        db = apri_db(path)
    except (sqlite3.Error, OSError):
        return out
    try:
        return cancella(db, **kw)
    except sqlite3.Error as e:
        log(f"   [STUDIO] dati dello Studio non cancellati: {type(e).__name__}")
        return out
    finally:
        db.close()


def conta_file(path, persona: str | None = None) -> dict:
    """Quante verifiche ci sono (e quante archiviate), di tutti o di una persona: per
    `calliope stato`, la domanda di «svuota» e quella di «dimentica»."""
    out = {"verifiche": 0, "archiviate": 0}
    if not path or not Path(path).exists():
        return out
    try:
        db = apri_db(path)
    except (sqlite3.Error, OSError):
        return out
    try:
        if not _c_e(db):
            return out
        dove, arg = ("WHERE persona = ?", (str(persona),)) if persona is not None else ("", ())
        out["verifiche"] = db.execute(f"SELECT COUNT(*) FROM studio_verifiche {dove}",
                                      arg).fetchone()[0]
        e = "AND" if dove else "WHERE"
        out["archiviate"] = db.execute(f"SELECT COUNT(*) FROM studio_verifiche {dove} {e} "
                                       "stato = 'archiviata'", arg).fetchone()[0]
        return out
    except sqlite3.Error:
        return out
    finally:
        db.close()
