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
  scrive la lettura del passo 4.3 ed è un dato non fidato. Dalla versione 2 (29/10, passo 4.2,
  issue #281) anche ciò che dice il controllo del server sulla foto: gli angoli usati (`angoli`,
  JSON, in frazioni della foto), gli avvisi (`avvisi`, JSON: «bordi», «sfocata», «piccola»), la
  nitidezza e il lato della pagina salvata;
- `studio_argomenti`: gli argomenti con le pagine che citano (id, JSON), lo stato (proposto,
  tenuto, tolto, aggiunto dalla persona) e l'ordine; l'estrazione arriva con il passo 4.4, qui
  c'è la conferma a mano;
- `studio_piano`: un giorno per riga (fase, pagine, attività, minuti, fatto);
- `studio_giorni`: i giorni di una persona con minuti diversi (0 = senza piano: giorno senza
  scuola, giorno saltato con «non ce la faccio oggi»);
- `studio_misure`: le misure vere della padronanza (dal passo 5), per la previsione;
- `studio_tentativi` (versione 5, 30/10, passo 5, issue #245): i tentativi su un argomento (tipo:
  carta, esercizio, mappa, interrogazione, verifica finta; esito: giusto, indizio, sbagliato; chi
  ha deciso l'esito: la persona, il codice o il tutore, mai il modello da solo), da cui il codice
  calcola la padronanza (`studio/padronanza.py`). Solo id, codici e date: mai testo;
- `studio_eventi` (versione 4, 30/10, passo 4b, issue #244): la storia delle sessioni di una
  verifica, da cui si proiettano il resoconto di una sessione e il riepilogo della verifica
  (`studio/resoconto.py`): «inizio» (la sessione cominciata con le due domande, **senza** le
  risposte: lo stato d'animo e la conoscenza restano in memoria, decisione 0035 punto 27),
  «fatto» e «non_fatto» (il giorno del piano, con le pagine e i minuti previsti di quel giorno),
  «saltato» («non ce la faccio oggi»), «mancato» (un giorno del piano passato senza «fatto»,
  scritto dal ricalcolo prima di togliere la riga) e «spostata» (la data di prima e quella nuova).
  Solo id, numeri e date: mai titoli né testo delle pagine;
- `studio_carte` (versione 6, 30/10, passo 6, issue #246): le carte di una verifica (domanda e
  risposta, un dato non fidato come il testo delle pagine, chiunque l'abbia scritto; la forma
  chiusa della risposta per il confronto del codice; le pagine e l'argomento; l'origine, lo stato
  e il ripasso di Leitner: scatola, scadenza, ultima volta, `studio/carte.py`); dalla stessa
  versione `studio_tentativi.carta`, la carta da cui viene un tentativo. Dalla versione 7
  (seconda parte del passo 6) `studio_verifiche.carte_firma`, `carte_esito`, `carte_del`:
  l'ultima generazione delle carte dal lettore (`studio/genera.py`).

Tenuta (decisione 0035, punto 4): tutto ciò che è di una verifica resta fino a
`studio_tenuta_giorni` (60) giorni dopo la sua data, per sempre se archiviata; «dimentica le
nostre conversazioni» toglie lo Studio della persona tranne le verifiche archiviate (tenute di
proposito, come le foto archiviate della 0034); `calliope conserva --svuota` toglie tutto.
Sempre con `secure_delete`, e con i file delle pagine dentro la cartella dello Studio (dal
passo 4.2 anche il PDF originale di un materiale, `riferimento` «file:…»). Una cartella relativa
sta accanto a `memory_db`, come il cassetto (`cartella_di`).
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import threading
from pathlib import Path

from ..persistenza import apri_db, prepara_schema

MODULO = "studio"

# Le tabelle dello Studio, figlie prima dei genitori (l'ordine delle cancellazioni)
TABELLE = ("studio_tentativi", "studio_carte", "studio_eventi", "studio_piano", "studio_misure",
           "studio_argomenti", "studio_pagine", "studio_materiali", "studio_verifiche",
           "studio_giorni")

STATI_VERIFICA = ("bozza", "aperta", "fatta", "archiviata")
ORIGINI = ("foto", "cassetto", "file", "biblioteca", "mano")
# «da_leggere» (29/10, passo 4.2): la pagina arrivata dalla fotocamera o da un PDF, che aspetta la
# lettura del passo 4.3; «in_lettura» (30/10, passo 4.3, #282): la sta leggendo il lettore
# (studio/lettura.py), e dopo un riavvio torna «da_leggere»; «da_parte» (revisione della PR #314):
# la pagina che fa cadere vLLM due volte di fila, riprovata solo a mano o dopo un aggiornamento
STATI_PAGINA = ("da_controllare", "buona", "sfocata", "tolta", "letta", "illeggibile",
                "da_leggere", "in_lettura", "da_parte")
# Il riferimento di un materiale che è un file nella cartella dello Studio (il PDF originale)
RIF_FILE = "file:"
# Le immagini delle pagine e i PDF stanno in `cartella/pagine/<id della verifica>/`, con un nome
# scelto dal server (studio/pagine.py, `scrivi_file`)
CARTELLA_PAGINE = "pagine"
# Un file senza riga si toglie nella rotazione solo dopo un giorno (un invio in corso ha il file
# scritto un attimo prima della riga)
ORFANI_DOPO_S = 86400.0
# I provvisori della divisione dei PDF (seconda revisione della PR #312): dentro la cartella
# dello Studio, non nella cartella temporanea di sistema; tolti dopo la divisione, all'avvio dello
# Studio e, se un crollo li ha lasciati, dalla rotazione dopo un'ora
CARTELLA_PROVVISORI = "tmp"
PROVVISORI_DOPO_S = 3600.0
# All'avvio dello Studio (passo 4.5, terza revisione della PR #312): solo i provvisori più vecchi
# di 15 minuti, perché un'altra istanza sullo stesso disco può star dividendo un PDF adesso
PROVVISORI_AVVIO_S = 900.0
STATI_ARGOMENTO = ("proposto", "tenuto", "tolto", "aggiunto")
# Gli argomenti su cui si fa il piano
ARGOMENTI_DEL_PIANO = ("tenuto", "aggiunto")
# Gli eventi delle sessioni (versione 4, passo 4b, #244)
EVENTI = ("inizio", "fatto", "non_fatto", "saltato", "mancato", "spostata")


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


def _v2(db: sqlite3.Connection):
    """29/10, passo 4.2 (#281): il controllo del server sulle pagine dalla fotocamera e dai PDF."""
    for col in ("angoli TEXT", "avvisi TEXT", "nitidezza REAL", "larghezza INTEGER",
                "altezza INTEGER"):
        db.execute(f"ALTER TABLE studio_pagine ADD COLUMN {col}")


def _v3(db: sqlite3.Connection):
    """30/10, passo 4.4 (#283): l'ultima estrazione degli argomenti di una verifica (la firma
    delle pagine usate, l'esito e quando), per non chiederli due volte sulle stesse pagine; il
    titolo proposto dal modello di un argomento (`titolo_modello`, revisione della PR #315): un
    proposto rinominato dalla persona è una sua decisione, e il titolo del modello non si ripropone."""
    for col in ("argomenti_firma TEXT", "argomenti_esito TEXT", "argomenti_del TEXT"):
        db.execute(f"ALTER TABLE studio_verifiche ADD COLUMN {col}")
    db.execute("ALTER TABLE studio_argomenti ADD COLUMN titolo_modello TEXT")


def _v4(db: sqlite3.Connection):
    """30/10, passo 4b (#244): gli eventi delle sessioni, per il resoconto e il riepilogo.
    `persona` è di chi è la verifica, `chi` chi ha agito (lei o il tutore); `dati` è un JSON di
    soli id, numeri e date."""
    db.execute("""CREATE TABLE IF NOT EXISTS studio_eventi (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        persona TEXT NOT NULL,
        giorno TEXT NOT NULL,
        ora TEXT NOT NULL,
        tipo TEXT NOT NULL,
        chi TEXT,
        dati TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_eventi_verifica "
               "ON studio_eventi(verifica, giorno)")


def _v5(db: sqlite3.Connection):
    """30/10, passo 5 (#245): i tentativi su un argomento, per la padronanza. `persona` è di chi
    è la verifica, `chi` chi ha registrato il tentativo."""
    db.execute("""CREATE TABLE IF NOT EXISTS studio_tentativi (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        persona TEXT NOT NULL,
        argomento INTEGER NOT NULL,
        giorno TEXT NOT NULL,
        ora TEXT NOT NULL,
        tipo TEXT NOT NULL,
        esito TEXT NOT NULL,
        fonte TEXT NOT NULL,
        chi TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_tentativi_verifica "
               "ON studio_tentativi(verifica, argomento)")


def _v6(db: sqlite3.Connection):
    """30/10, passo 6 (#246): le carte e il loro ripasso. `persona` è di chi è la verifica;
    domanda e risposta sono un dato (sullo schermo con textContent, al modello in busta)."""
    db.execute("""CREATE TABLE IF NOT EXISTS studio_carte (
        id INTEGER PRIMARY KEY,
        verifica INTEGER NOT NULL,
        persona TEXT NOT NULL,
        argomento INTEGER,
        domanda TEXT NOT NULL,
        risposta TEXT NOT NULL,
        chiusa TEXT,
        pagine TEXT NOT NULL DEFAULT '[]',
        origine TEXT NOT NULL DEFAULT 'persona',
        stato TEXT NOT NULL DEFAULT 'attiva',
        avvisi TEXT,
        scatola INTEGER NOT NULL DEFAULT 1,
        scadenza TEXT,
        ultima TEXT,
        creata TEXT NOT NULL,
        creata_da TEXT,
        modificata TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS studio_carte_verifica ON studio_carte(verifica)")
    db.execute("ALTER TABLE studio_tentativi ADD COLUMN carta INTEGER")


def _v7(db: sqlite3.Connection):
    """30/10, passo 6, seconda parte (#246): l'ultima generazione delle carte di una verifica (la
    firma degli argomenti e delle pagine usate, l'esito e quando), per non chiederle due volte."""
    for col in ("carte_firma TEXT", "carte_esito TEXT", "carte_del TEXT"):
        db.execute(f"ALTER TABLE studio_verifiche ADD COLUMN {col}")


# Le versioni dello schema: si aggiungono in fondo, solo colonne con NULL o un predefinito (o
# tabelle nuove)
MIGRAZIONI = [_v1, _v2, _v3, _v4, _v5, _v6, _v7]
# Le tabelle con la verifica e la persona che possono restare orfane (una corsa fra una
# scrittura e una cancellazione): scadono per data, vanno via con la persona e con «svuota»
CON_ORFANI = ("studio_eventi", "studio_tentativi")
# Le tabelle venute dopo la prima versione: un db di prima (lo Studio spento non lo prepara) può
# non averle
NUOVE = (*CON_ORFANI, "studio_carte")


def cartella_di(cfg, db_path=None) -> Path | None:
    """La cartella dello Studio, assoluta: `studio_cartella` com'è se assoluta, altrimenti
    accanto al file della memoria (come il cassetto); None senza cartella."""
    c = str(getattr(cfg, "studio_cartella", "") or "") if cfg is not None else ""
    return _assoluta(c, db_path or (getattr(cfg, "memory_db", None) if cfg is not None
                                    else None))


def _assoluta(cartella, db_path) -> Path | None:
    if not cartella:
        return None
    p = Path(str(cartella))
    if not p.is_absolute() and db_path:
        p = Path(str(db_path)).resolve().parent / p
    return p


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


def _tabella(db: sqlite3.Connection, nome: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                      (nome,)).fetchone() is not None


def _togli_verifiche(db: sqlite3.Connection, ids: list[int]) -> list[str]:
    """Cancella le verifiche e tutto ciò che è loro (dentro una transazione già aperta). I file
    delle pagine tolte (dal passo 4.2 anche i PDF originali dei materiali), da togliere dal
    disco dopo il commit."""
    file = []
    for vid in ids:
        mats = []
        for mid, rif in db.execute("SELECT id, riferimento FROM studio_materiali WHERE "
                                   "verifica = ?", (vid,)).fetchall():
            mats.append(mid)
            if isinstance(rif, str) and rif.startswith(RIF_FILE):
                file.append(rif[len(RIF_FILE):])
        for m in mats:
            file += [r[0] for r in db.execute(
                "SELECT file FROM studio_pagine WHERE materiale = ? AND file IS NOT NULL", (m,))]
            db.execute("DELETE FROM studio_pagine WHERE materiale = ?", (m,))
        for t in ("studio_materiali", "studio_argomenti", "studio_piano", "studio_misure",
                  "studio_carte", *CON_ORFANI):
            # Un db ancora allo schema di prima (lo Studio spento non lo prepara): le tabelle
            # nuove possono mancare
            if t in NUOVE and not _tabella(db, t):
                continue
            db.execute(f"DELETE FROM {t} WHERE verifica = ?", (vid,))
        db.execute("DELETE FROM studio_verifiche WHERE id = ?", (vid,))
    return file


def togli_file(file: list[str], cartella) -> int:
    """I file delle pagine dentro `cartella` (la cartella dello Studio); un percorso fuori non
    si tocca mai. Quanti tolti. Le cartelle delle verifiche rimaste vuote si tolgono."""
    if not cartella or not file:
        return 0
    base = Path(cartella).resolve()
    n = 0
    padri = set()
    for f in file:
        try:
            p = (base / f).resolve()
            if base not in p.parents:
                continue
            if p.exists():
                p.unlink()
                n += 1
            padri.add(p.parent)
        except OSError:
            continue
    for d in padri:
        try:
            if d != base and base in d.parents and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            continue
    return n


def togli_orfani(cartella, conosciuti: set | None = None, piu_vecchi_di_s: float = 0.0) -> int:
    """I file sotto `cartella/pagine` che nessuna riga cita: tutti per `svuota` di tutti (dopo le
    righe); nella rotazione (revisione della PR #312) solo quelli non in `conosciuti` (percorsi
    relativi alla cartella) e più vecchi di `piu_vecchi_di_s`: un crollo fra la scrittura e il
    commit, o il ritorno di `calliope aggiorna` a un `memoria.db` di prima, non lasciano foto di
    quaderni per sempre. Mai fuori dalla cartella, mai seguendo un link."""
    import time
    if not cartella:
        return 0
    base = Path(cartella).resolve()
    radice = base / CARTELLA_PAGINE
    if radice.is_symlink() or not radice.is_dir() or base not in radice.resolve().parents:
        return 0
    n = 0
    for dirpath, _dirnames, filenames in os.walk(radice, followlinks=False):
        for nome in filenames:
            p = Path(dirpath) / nome
            try:
                if p.is_symlink() or base not in p.resolve().parents:
                    continue
                if conosciuti is not None and p.relative_to(base).as_posix() in conosciuti:
                    continue
                if piu_vecchi_di_s and time.time() - p.stat().st_mtime < piu_vecchi_di_s:
                    continue
                p.unlink()
                n += 1
            except OSError:
                continue
    for dirpath, _d, _f in sorted(os.walk(radice, followlinks=False), key=lambda t: -len(t[0])):
        d = Path(dirpath)
        try:
            if d != radice and not d.is_symlink() and not any(d.iterdir()):
                d.rmdir()
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
        # Gli eventi senza la loro verifica (una corsa fra un «inizio» e una cancellazione,
        # revisione della PR #321, nota 6): via con «svuota», con la persona, e per data con la
        # rotazione; mai per sempre
        # (dal passo 5 anche i tentativi, CON_ORFANI)
        presenti = [t for t in CON_ORFANI if _tabella(db, t)]
        orfani = "verifica NOT IN (SELECT id FROM studio_verifiche)"
        if tutto:
            db.execute("DELETE FROM studio_giorni")
            for t in presenti:
                db.execute(f"DELETE FROM {t}")
        elif persona is not None:
            db.execute("DELETE FROM studio_giorni WHERE persona = ?", (str(persona),))
            for t in presenti:
                db.execute(f"DELETE FROM {t} WHERE persona = ? AND {orfani}", (str(persona),))
        else:
            for t in presenti:
                db.execute(f"DELETE FROM {t} WHERE giorno < ? AND {orfani}",
                           (scadute_prima.isoformat(),))
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
    if tutto and cartella:
        # «svuota» di tutti: anche i file rimasti senza riga (un invio a metà)
        out["file"] += togli_orfani(cartella)
        togli_provvisori(cartella)
    elif scadute_prima is not None and cartella:
        # La rotazione: anche i provvisori della divisione dei PDF rimasti da un crollo
        out["provvisori"] = togli_provvisori(cartella, PROVVISORI_DOPO_S)
    if scadute_prima is not None and cartella and versione_schema(db) > len(MIGRAZIONI):
        # Uno schema dello Studio più nuovo di questa versione (seconda revisione della PR #312):
        # i file li possono citare tabelle o colonne che qui non si conoscono, quindi nessun
        # orfano si toglie (sola lettura, come prepara_schema)
        out["orfani_saltati"] = True
    elif scadute_prima is not None and cartella:
        # La rotazione: anche i file che nessuna riga cita, vecchi di più di un giorno
        conosciuti = {r[0] for r in db.execute(
            "SELECT file FROM studio_pagine WHERE file IS NOT NULL")}
        conosciuti |= {r[0][len(RIF_FILE):] for r in db.execute(
            "SELECT riferimento FROM studio_materiali WHERE riferimento LIKE ?",
            (RIF_FILE + "%",))}
        out["orfani"] = togli_orfani(cartella, conosciuti, ORFANI_DOPO_S)
        out["file"] += out["orfani"]
    return out


def versione_schema(db: sqlite3.Connection) -> int:
    """La versione dello schema «studio» scritta in `meta_schema` (0 se non c'è)."""
    try:
        r = db.execute("SELECT versione FROM meta_schema WHERE modulo = ?", (MODULO,)).fetchone()
    except sqlite3.Error:
        return 0
    return int(r[0]) if r else 0


def cartella_provvisori(cartella) -> Path | None:
    """`cartella/tmp`: dove il sottoprocesso divide un PDF (pagine.dividi_pdf_a_parte)."""
    return Path(cartella) / CARTELLA_PROVVISORI if cartella else None


def togli_provvisori(cartella, piu_vecchi_di_s: float = 0.0) -> int:
    """Le cartelle sotto `cartella/tmp` più vecchie di `piu_vecchi_di_s` (0: tutte, all'avvio
    dello Studio): ciò che resta di una divisione interrotta da un crollo. Mai seguendo un link."""
    import shutil
    import time
    tmp = cartella_provvisori(cartella)
    if tmp is None or tmp.is_symlink() or not tmp.is_dir():
        return 0
    base = Path(cartella).resolve()
    n = 0
    for d in tmp.iterdir():
        try:
            if d.is_symlink() or base not in d.resolve().parents:
                continue
            if piu_vecchi_di_s and time.time() - d.stat().st_mtime < piu_vecchi_di_s:
                continue
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
            else:
                d.unlink()
            n += 1
        except OSError:
            continue
    return n


def cancella_file(path, log=print, **kw) -> dict:
    """`cancella` sul file della memoria, aprendolo e chiudendolo (conservazione e terminale).
    Un file che non c'è, o che non si apre, non ferma niente."""
    out = {"verifiche": 0, "file": 0}
    if not path or not Path(path).exists():
        return out
    if kw.get("cartella"):
        # Una cartella relativa sta accanto al file della memoria (cartella_di)
        kw["cartella"] = _assoluta(kw["cartella"], path)
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


def conta_file(path, persona: str | None = None, solleva: bool = False) -> dict:
    """Quante verifiche ci sono (e quante archiviate), di tutti o di una persona: per
    `calliope stato`, la domanda di «svuota» e quella di «dimentica». Con `solleva` un errore
    del db si solleva invece di dare zero (il ricontrollo dopo «dimentica», PR #317)."""
    out = {"verifiche": 0, "archiviate": 0}
    if not path or not Path(path).exists():
        return out
    try:
        db = apri_db(path)
    except (sqlite3.Error, OSError):
        if solleva:
            raise
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
        if solleva:
            raise
        return out
    finally:
        db.close()
