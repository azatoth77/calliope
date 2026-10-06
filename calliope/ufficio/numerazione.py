"""
Numerazione progressiva per serie e anno (fatture, preventivi, DDT): atomica e senza buchi.

- Un numero è emesso solo se il documento è stato scritto davvero: `emetti` lo prenota in
  una transazione `BEGIN IMMEDIATE` breve (un solo scrittore alla volta, anche fra processi
  diversi sullo stesso file SQLite), prepara i file **fuori** dalla transazione e poi lo
  conferma. Se la preparazione non riesce il numero torna libero se è ancora l'ultimo,
  altrimenti resta annullato con una nota: mai buchi (03/10).
- Ordine cronologico: per le fatture la data del numero n non può essere prima di quella
  del numero n−1 (art. 21 del DPR 633/72: numerazione progressiva per anno solare). Vale
  per tutte le serie: un DDT o un preventivo con una data indietro è quasi sempre un errore.
- Un numero emesso non si cancella e non si riusa: si può solo **annullare con una nota**
  (il motivo). Per una fattura già trasmessa allo SdI l'annullo vero è una nota di credito:
  la nota qui serve al registro interno (una fattura preparata e mai inviata).

Il formato del numero detto e stampato viene da `FORMATI` (o da `ufficio_serie` della
configurazione): «{n}/{anno}» → «12/2026».
"""

import datetime
import json
import sqlite3
import threading
import time

from ..persistenza import apri_db, prepara_schema

FORMATI = {"fatture": "{n}/{anno}", "note_credito": "NC{n}/{anno}",
           "preventivi": "P{n}/{anno}", "ddt": "DDT{n}/{anno}"}


# Stato di un numero preso ma con i file ancora in preparazione (03/10): conta come
# occupato (nessun altro lo prende), non come emesso
PRENOTATO = "in_preparazione"


class NumerazioneError(ValueError):
    """Un numero non si può emettere o annullare: il messaggio è una frase per la voce."""


def formatta(serie: str, numero: int, anno: int, formati: dict | None = None) -> str:
    fmt = (formati or {}).get(serie) or FORMATI.get(serie) or "{n}/{anno}"
    try:
        return fmt.format(n=numero, anno=anno, numero=numero)
    except (KeyError, IndexError, ValueError):
        return f"{numero}/{anno}"


class Numeratore:
    def __init__(self, path: str, formati: dict | None = None):
        self.path = path
        self.formati = dict(formati or {})
        self._lock = threading.Lock()          # nello stesso processo: niente attese inutili
        with self._conn() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS numeri (
                              serie TEXT NOT NULL,
                              anno INTEGER NOT NULL,
                              numero INTEGER NOT NULL,
                              data TEXT NOT NULL,            -- data del documento, AAAA-MM-GG
                              owner TEXT,                    -- UserProfile.id di chi l'ha emesso
                              owner_name TEXT,
                              modello TEXT,
                              titolo TEXT,
                              rif TEXT,                      -- file scritti (JSON: elenco)
                              dati TEXT,                     -- i dati del documento (JSON)
                              stato TEXT NOT NULL DEFAULT 'emesso',   -- emesso | annullato
                              nota TEXT,                     -- motivo dell'annullo
                              creato REAL NOT NULL,
                              annullato REAL,
                              PRIMARY KEY (serie, anno, numero))""")
            # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
            # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
            # predefinito. Dati di una versione più nuova: sola lettura
            self.scrivibile = prepara_schema(db, "numeri", [lambda db: None])

    def _conn(self) -> sqlite3.Connection:
        # Una connessione per operazione: le transazioni non si mescolano fra thread, e
        # BEGIN IMMEDIATE vale anche contro un altro processo sullo stesso file. WAL e
        # busy_timeout comuni a memoria.db (persistenza.apri_db, 03/10)
        db = apri_db(self.path, isolation_level=None)
        if not getattr(self, "scrivibile", True):
            db.execute("PRAGMA query_only = ON")      # schema più nuovo: sola lettura
        return db

    def testo(self, serie: str, numero: int, anno: int) -> str:
        return formatta(serie, numero, anno, self.formati)

    def prossimo(self, serie: str, anno: int) -> int:
        """Il numero che avrebbe il prossimo documento (solo per dirlo nella proposta: quello
        vero lo dà `emetti`, che può trovarne uno diverso se qualcuno ha emesso nel frattempo)."""
        db = self._conn()
        try:
            row = db.execute("SELECT MAX(numero) FROM numeri WHERE serie = ? AND anno = ?",
                             (serie, anno)).fetchone()
        finally:
            db.close()
        return (row[0] or 0) + 1

    # Una prenotazione più vecchia di così è di un processo morto durante la preparazione
    PRENOTAZIONE_MAX_S = 30 * 60

    def emetti(self, serie: str, data: datetime.date, prepara, owner=None, owner_name=None,
               modello: str = "", titolo: str = "", dati: dict | None = None) -> tuple[int, dict]:
        """Assegna il numero e chiama `prepara(numero, testo_numero)`, che deve scrivere i
        file e restituire un dict con "file" (elenco dei percorsi). (numero, risultato).

        Dal 03/10 (analisi di robustezza) i file si preparano **fuori** dalla transazione:
        prima `prepara` (XML, XSD, PDF, Word, magari su OneDrive) teneva il blocco di
        memoria.db anche per più di 5 s, e l'agenda o la memoria prendevano «database is
        locked». Ora tre passi brevi: (1) una transazione prenota il numero (riga in stato
        «in_preparazione», controllo della data); (2) `prepara` scrive i file senza nessun
        blocco del database; (3) una transazione lo conferma («emesso») con i file. Se
        `prepara` solleva il numero si libera: se è ancora l'ultimo della serie si cancella
        (nessun documento è uscito con quel numero, e il prossimo lo riusa); se intanto
        qualcuno ha preso il successivo resta **annullato con una nota** («preparazione non
        riuscita»), così non ci sono buchi."""
        anno = data.year
        with self._lock:
            numero = self._prenota(serie, anno, data, owner, owner_name, modello, titolo, dati)
            try:
                out = prepara(numero, self.testo(serie, numero, anno)) or {}
            except BaseException as e:
                self._libera(serie, anno, numero, f"preparazione non riuscita: "
                                                  f"{type(e).__name__}: {e}"[:300])
                raise
            try:
                self._conferma(serie, anno, numero, out.get("file") or [])
            except BaseException as e:
                _togli_file(out.get("file"))
                self._libera(serie, anno, numero, f"registrazione non riuscita: "
                                                  f"{type(e).__name__}: {e}"[:300])
                raise
            return numero, out

    def _transazione(self, fn):
        db = self._conn()
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                r = fn(db)
                db.execute("COMMIT")
                return r
            except BaseException:
                try:
                    db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        finally:
            db.close()

    def _prenota(self, serie, anno, data, owner, owner_name, modello, titolo, dati) -> int:
        def fn(db):
            self._pulisci_prenotazioni(db, serie, anno)
            last = db.execute("SELECT numero, data FROM numeri WHERE serie = ? AND anno = ? "
                              "ORDER BY numero DESC LIMIT 1", (serie, anno)).fetchone()
            numero = (last[0] if last else 0) + 1
            if last and data.isoformat() < last[1]:
                raise NumerazioneError(
                    f"la data {data.strftime('%d/%m/%Y')} viene prima di quella del "
                    f"numero {self.testo(serie, last[0], anno)} "
                    f"({datetime.date.fromisoformat(last[1]).strftime('%d/%m/%Y')}): i "
                    f"numeri devono seguire le date")
            db.execute("INSERT INTO numeri (serie, anno, numero, data, owner, owner_name, "
                       "modello, titolo, rif, dati, stato, creato) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (serie, anno, numero, data.isoformat(), owner, owner_name, modello,
                        titolo, "[]", json.dumps(dati or {}, ensure_ascii=False, default=str),
                        PRENOTATO, time.time()))
            return numero
        return self._transazione(fn)

    def _conferma(self, serie, anno, numero, files):
        def fn(db):
            cur = db.execute("UPDATE numeri SET stato = 'emesso', rif = ? WHERE serie = ? AND "
                             "anno = ? AND numero = ? AND stato = ?",
                             (json.dumps(files, ensure_ascii=False), serie, anno, numero,
                              PRENOTATO))
            if cur.rowcount != 1:
                raise NumerazioneError(f"la prenotazione del numero "
                                       f"{self.testo(serie, numero, anno)} non c'è più")
        self._transazione(fn)

    def _libera(self, serie, anno, numero, nota):
        """Una prenotazione non andata a buon fine: via se è l'ultima, altrimenti annullata
        con la nota (niente buchi). Non solleva: l'errore vero è quello di chi chiama."""
        try:
            self._transazione(lambda db: _libera_in(db, serie, anno, numero, nota))
        except Exception as e:  # noqa: BLE001
            print(f"   [UFFICIO] Numero {self.testo(serie, numero, anno)} non liberato "
                  f"({type(e).__name__}: {e}): si sistema alla prossima emissione", flush=True)

    def _pulisci_prenotazioni(self, db, serie, anno):
        """Prenotazioni rimaste da un processo morto a metà (più vecchie di
        PRENOTAZIONE_MAX_S): liberate come un errore di preparazione."""
        vecchie = db.execute("SELECT numero FROM numeri WHERE serie = ? AND anno = ? AND "
                             "stato = ? AND creato < ? ORDER BY numero DESC",
                             (serie, anno, PRENOTATO,
                              time.time() - self.PRENOTAZIONE_MAX_S)).fetchall()
        for (n,) in vecchie:
            _libera_in(db, serie, anno, n, "preparazione interrotta (Calliope si è fermata "
                                           "a metà)")

    def annulla(self, serie: str, anno: int, numero: int, nota: str) -> dict:
        """Annulla un numero emesso, con il motivo. Il numero resta occupato (niente buchi
        né riusi); i file non si toccano."""
        nota = str(nota or "").strip()
        if len(nota) < 5:
            raise NumerazioneError("per annullare un numero serve una nota con il motivo")
        db = self._conn()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT stato FROM numeri WHERE serie = ? AND anno = ? AND "
                             "numero = ?", (serie, anno, numero)).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                raise NumerazioneError(f"il numero {self.testo(serie, numero, anno)} non è "
                                       f"stato emesso")
            if row[0] == "annullato":
                db.execute("ROLLBACK")
                raise NumerazioneError(f"il numero {self.testo(serie, numero, anno)} è già "
                                       f"annullato")
            db.execute("UPDATE numeri SET stato = 'annullato', nota = ?, annullato = ? WHERE "
                       "serie = ? AND anno = ? AND numero = ?",
                       (nota, time.time(), serie, anno, numero))
            db.execute("COMMIT")
        finally:
            db.close()
        return {"serie": serie, "anno": anno, "numero": numero, "nota": nota}

    def elenco(self, serie: str | None = None, anno: int | None = None) -> list[dict]:
        where, args = [], []
        if serie:
            where.append("serie = ?")
            args.append(serie)
        if anno:
            where.append("anno = ?")
            args.append(anno)
        sql = ("SELECT serie, anno, numero, data, owner_name, modello, titolo, rif, stato, nota "
               "FROM numeri" + (" WHERE " + " AND ".join(where) if where else "")
               + " ORDER BY serie, anno, numero")
        db = self._conn()
        try:
            rows = db.execute(sql, args).fetchall()
        finally:
            db.close()
        keys = ("serie", "anno", "numero", "data", "chi", "modello", "titolo", "file", "stato",
                "nota")
        out = []
        for r in rows:
            d = dict(zip(keys, r))
            d["file"] = json.loads(d["file"] or "[]")
            d["testo"] = self.testo(d["serie"], d["numero"], d["anno"])
            out.append(d)
        return out

    def buchi(self, serie: str, anno: int) -> list[int]:
        """I numeri mancanti fra 1 e l'ultimo (per le prove: deve essere sempre vuoto)."""
        nums = [d["numero"] for d in self.elenco(serie, anno)]
        return sorted(set(range(1, (max(nums) if nums else 0) + 1)) - set(nums))


def _libera_in(db, serie, anno, numero, nota):
    ultimo = db.execute("SELECT MAX(numero) FROM numeri WHERE serie = ? AND anno = ?",
                        (serie, anno)).fetchone()[0]
    if ultimo == numero:
        db.execute("DELETE FROM numeri WHERE serie = ? AND anno = ? AND numero = ? AND "
                   "stato = ?", (serie, anno, numero, PRENOTATO))
    else:
        db.execute("UPDATE numeri SET stato = 'annullato', nota = ?, annullato = ? WHERE "
                   "serie = ? AND anno = ? AND numero = ? AND stato = ?",
                   (nota, time.time(), serie, anno, numero, PRENOTATO))


def _togli_file(files):
    from pathlib import Path
    for f in files or []:
        try:
            Path(f).unlink()
        except OSError:
            pass
