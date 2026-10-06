"""
Agenda di Calliope: timer, promemoria e appuntamenti, salvati in SQLite (stesso file
della memoria).

Un thread dorme fino alla prossima scadenza e, quando arriva, mette la voce in `due`
e chiama `on_due` (in main.py sveglia l'ascolto, così Calliope annuncia subito).
I promemoria sopravvivono a un riavvio: quelli scaduti a Calliope spenta si annunciano
all'avvio. Durate e orari detti a voce si convertono in tempi.py.

Tipi (colonna kind):
  timer        della casa, anche per gli ospiti;
  promemoria   personale («ricordami di…»);
  appuntamento personale («martedì alle 17 ho il dentista»), annunciato all'ora;
  avviso       il promemoria automatico prima di un appuntamento (colonna parent):
               interno, non si elenca e si annulla insieme all'appuntamento.
"""

import datetime
import difflib
import queue
import re
import sqlite3
import threading
import time

from .tempi import word_number
from .persistenza import apri_db, prepara_schema

_FIELDS = ("id", "kind", "owner", "owner_name", "label", "due", "parent", "created")
_COLS = ", ".join(_FIELDS)
# Annullare tutto: la richiesta intera è «tutto», «tutti i timer», «annulla tutti e tre i
# promemoria», «tutti gli appuntamenti di domani» no (resta alla somiglianza)
_ALL = re.compile(r"\W*(?:(?:annulla|cancella|elimina|togli|ferma)\w*\s+)?"
                  r"(?:tutto(?:\s+quanto)?|tutt[ie](?:\s+quanti)?(?:\s+e\s+\w+)?"
                  r"(?:\s+(?:i|gli|le|quanti\s+i)?\s*(?:timer|promemoria|appuntamenti|sveglie|"
                  r"voci|avvisi))?|(?:i|gli)\s+(?:timer|promemoria|appuntamenti)\s+tutti)"
                  r"\W*", re.I)


def is_cancel_all(query: str) -> bool:
    """La richiesta intera chiede di annullare tutto (o tutti i timer, i promemoria…)?"""
    return bool(_ALL.fullmatch((query or "").strip()))


_GENERIC = {"timer", "minuto", "minuti", "secondo", "secondi", "mezzora", "quarto",
            "della", "delle", "degli", "dello", "promemoria", "appuntamento", "sveglia"}


def _words(text: str) -> set[str]:
    """Le parole che distinguono una voce («pasta», «dentista»), senza durate e numeri."""
    return {w for w in re.findall(r"\w{4,}", (text or "").lower())
            if w not in _GENERIC and word_number(w) is None}


# Parole della richiesta che non nominano una voce: verbi dell'annullo, rimandi, riempitivi
_NOT_NAMES = {"annulla", "annullalo", "annullala", "annullami", "cancella", "cancellalo",
              "cancellala", "cancellami", "elimina", "eliminalo", "togli", "toglilo", "ferma",
              "fermalo", "fermala", "spegni", "spegnilo", "quello", "quella", "questo",
              "questa", "ultimo", "ultima", "anzi", "adesso", "subito", "allora", "messo",
              "messa", "appena", "impostato", "detto", "prima", "calliope", "grazie",
              "favore", "appuntamenti", "sveglie"}


def _share(a: set[str], b: set[str]) -> bool:
    """Una parola in comune, anche storpiata dopo le prime 5 lettere («dentisa»)."""
    return any(x == y or (len(x) >= 5 and len(y) >= 5 and x[:5] == y[:5])
               for x in a for y in b)


def _score(q: str, it: dict) -> float:
    """Quanto la richiesta («il timer della pasta», «il dentista») somiglia alla voce."""
    text = f"{it['kind']} {it['label']}".lower()
    label = it["label"].lower()
    return (difflib.SequenceMatcher(None, q, text).ratio()
            + (0.3 if q in text else 0)
            # «annulla il dentista»: la parola della voce nella richiesta
            + (0.4 if any(w in q for w in re.findall(r"\w{4,}", label)) else 0))


MIGRAZIONI = [lambda db: None]      # 1: lo schema del 03/10 (tabella creata in __init__)


class Agenda:
    def __init__(self, path: str, on_due=None, on_scaduta=None):
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.on_due = on_due
        # Chiamata per ogni voce appena scaduta, dal thread dell'agenda (02/10: la scheda
        # del timer sugli schermi diventa «scaduto alle …»). Non deve bloccare
        self.on_scaduta = on_scaduta
        self.due: queue.Queue = queue.Queue()         # voci scadute da annunciare
        # L'ultima voce messa o cambiata per tipo e persona (03/10): «impostalo di un minuto»
        # cambia quella, non la più simile. In memoria: dopo un riavvio vale la più recente
        self._last: dict[tuple, int] = {}
        # WAL e busy_timeout comuni (persistenza.apri_db, 03/10): memoria.db è condiviso
        self.db = apri_db(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS agenda (
                               id INTEGER PRIMARY KEY,
                               kind TEXT NOT NULL,          -- timer | promemoria | appuntamento | avviso
                               owner TEXT,                  -- UserProfile.id, None = ospite
                               owner_name TEXT,
                               label TEXT NOT NULL,
                               due REAL NOT NULL,           -- epoch
                               created REAL NOT NULL,
                               parent INTEGER)              -- avviso → id dell'appuntamento""")
        try:                                           # file di prima degli appuntamenti
            self.db.execute("ALTER TABLE agenda ADD COLUMN parent INTEGER")
        except sqlite3.OperationalError:
            pass                                       # colonna già presente
        self.db.commit()
        # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
        # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
        # predefinito. Dati di una versione più nuova: sola lettura
        self.scrivibile = prepara_schema(self.db, "agenda", MIGRAZIONI)
        if self.scrivibile:          # in sola lettura le scadenze non si possono togliere
            threading.Thread(target=self._run, daemon=True).start()

    # ── scrittura ──
    def add(self, kind: str, label: str, due: float, owner=None, owner_name=None,
            parent: int | None = None) -> int:
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO agenda (kind, owner, owner_name, label, due, created, parent) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, owner, owner_name, label, due, time.time(), parent))
            self.db.commit()
        if kind != "avviso":
            self._last[(kind, owner)] = cur.lastrowid
        self._wake.set()                               # la prossima scadenza può essere cambiata
        return cur.lastrowid

    def get(self, item_id: int) -> dict | None:
        with self._lock:
            row = self.db.execute(f"SELECT {_COLS} FROM agenda WHERE id = ?",
                                  (item_id,)).fetchone()
        return dict(zip(_FIELDS, row)) if row else None

    def last(self, kind: str, owner=None) -> tuple[dict | None, bool]:
        """L'ultima voce di `kind` messa o cambiata da `owner` (i timer, della casa: anche da
        altri, se lui non ne ha). Restituisce (voce, scaduta): `scaduta` True se l'ultima
        messa non c'è più (scaduta o annullata) e voce None: «impostalo di un minuto» dopo
        un timer di un secondo già suonato non deve cambiare un altro timer."""
        tid = self._last.get((kind, owner))
        if tid is not None:
            item = self.get(tid)
            return (item, False) if item else (None, True)
        mine = [it for it in self.items(owner) if it["kind"] == kind]
        if kind == "timer":
            mine = [it for it in mine if it["owner"] == owner] or mine
        if not mine:
            return None, False
        return max(mine, key=lambda it: (it["created"] or 0, it["id"])), False

    def find(self, kind: str, query: str, owner=None) -> tuple[dict | None, bool]:
        """La voce di `kind` da cambiare: l'unica di quel tipo, la più simile a `query` («il
        timer della pasta», «il dentista»), altrimenti l'ultima messa (`last`)."""
        items = [it for it in self.items(owner) if it["kind"] == kind]
        if len(items) == 1:
            return items[0], False
        q = (query or "").lower().strip()
        # Solo una parola vera della voce nella richiesta: «di 1 minuto» somiglia a «di 1
        # secondo» quanto basta per scambiare due timer senza nome
        named = [it for it in items if _words(it["label"]) & _words(q)]
        if named:
            return max(named, key=lambda it: _score(q, it)), False
        return self.last(kind, owner)

    def reschedule(self, item_id: int, due: float, lead_s: float = 0,
                   label: str | None = None) -> dict | None:
        """Sposta una voce a `due` (epoch), con la stessa identità (id e created: la scheda
        sullo schermo si aggiorna al suo posto). L'avviso di un appuntamento si rifà
        `lead_s` prima, se è ancora nel futuro; `label` cambia anche il nome («di 1 minuto»).
        Restituisce la voce cambiata."""
        with self._lock:
            row = self.db.execute("SELECT kind, owner, owner_name, label FROM agenda "
                                  "WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                return None
            kind, owner, owner_name, old_label = row
            label = label or old_label
            self.db.execute("UPDATE agenda SET due = ?, label = ? WHERE id = ?",
                            (due, label, item_id))
            if kind == "appuntamento":
                self.db.execute("DELETE FROM agenda WHERE parent = ?", (item_id,))
                if lead_s > 0 and due - lead_s > time.time():
                    self.db.execute(
                        "INSERT INTO agenda (kind, owner, owner_name, label, due, created, "
                        "parent) VALUES ('avviso', ?, ?, ?, ?, ?, ?)",
                        (owner, owner_name, label, due - lead_s, time.time(), item_id))
            self.db.commit()
        self._last[(kind, owner)] = item_id
        self._wake.set()
        return self.get(item_id)

    def items(self, owner=None) -> list[dict]:
        """Voci attive: tutti i timer (sono della casa) e le voci personali di `owner`
        (promemoria, appuntamenti). Gli avvisi interni restano fuori."""
        with self._lock:
            rows = self.db.execute(
                f"SELECT {_COLS} FROM agenda "
                "WHERE kind != 'avviso' AND (kind = 'timer' OR owner IS ?) ORDER BY due",
                (owner,)).fetchall()
        return [dict(zip(_FIELDS, r)) for r in rows]

    def appointments(self, owner, start: float, end: float) -> list[dict]:
        """Gli appuntamenti di `owner` tra due istanti (epoch), in ordine."""
        with self._lock:
            rows = self.db.execute(
                f"SELECT {_COLS} FROM agenda "
                "WHERE kind = 'appuntamento' AND owner IS ? AND due >= ? AND due < ? "
                "ORDER BY due", (owner, start, end)).fetchall()
        return [dict(zip(_FIELDS, r)) for r in rows]

    def match(self, query: str, owner=None, items=None) -> list[dict]:
        """La voce da annullare per `query`, o [] se non è chiaro quale (03/10).

        Prima bastava la somiglianza (difflib ≥ 0,35) o il solo tipo: «annulla il dentista»
        con un solo timer «di 5 minuti» annullava il timer, «il timer della pasta» quello
        delle uova. Ora vale solo una parola vera della voce nella richiesta (anche
        storpiata dopo le prime 5 lettere: «dentisa»), o il nome intero («il timer di 10
        minuti»); se la richiesta non nomina niente oltre al tipo («annulla il timer»,
        «annulla»), l'unica voce di quel tipo (o l'unica in tutto). Altrimenti nessuna: il
        tool chiede quale."""
        items = self.items(owner) if items is None else items
        q = (query or "").lower().strip()
        kinds = {k for k in ("timer", "promemoria", "appuntamento")
                 if k in q or (k == "appuntamento" and "appuntament" in q)
                 or (k == "timer" and "svegli" in q)}
        pool = [it for it in items if it["kind"] in kinds] if kinds else items
        asked = _words(q) - _NOT_NAMES
        named = [it for it in pool if _share(_words(it["label"]), asked)
                 or (it["label"] and it["label"].lower() in q)]
        if named:
            return [max(named, key=lambda it: _score(q, it))]
        if not asked and len(pool) == 1:
            return pool
        return []

    def cancel(self, query: str, owner=None) -> list[dict]:
        """Annulla la voce nominata da `query` («il timer della pasta», «il dentista»: vedi
        match), o tutte («tutto», «tutti i timer»). Un appuntamento si porta via il suo avviso.
        Restituisce le voci annullate."""
        items = self.items(owner)
        q = query.lower().strip()
        kinds_named = {k for k in ("timer", "promemoria", "appuntamento")
                       if k in q or (k == "appuntamento" and "appuntament" in q)
                       or (k == "timer" and "svegli" in q)}
        # «Tutto» solo come richiesta intera («tutto», «tutti i timer», «annulla tutti i
        # promemoria»), come in liste.remove: «il promemoria di salutare tutti» annullava
        # tutti e 3 i promemoria (rapporto del 01/10)
        if is_cancel_all(q):
            kinds = kinds_named or {"timer", "promemoria", "appuntamento"}
            chosen = [it for it in items if it["kind"] in kinds]
        else:
            chosen = self.match(q, owner, items)
        with self._lock:
            for it in chosen:
                self.db.execute("DELETE FROM agenda WHERE id = ? OR parent = ?",
                                (it["id"], it["id"]))
            self.db.commit()
        self._wake.set()
        return chosen

    # ── scadenze ──
    errori = 0                      # giri falliti (diagnosi e prove)

    def _run(self):
        """Il thread delle scadenze. Non muore mai (03/10, analisi di robustezza): prima il
        primo «database is locked» (una fattura che teneva il blocco, un DB Browser aperto,
        il disco pieno) lo uccideva, e timer e promemoria non suonavano più fino al riavvio.
        Ora un errore va nel log, la transazione si annulla e si riprova con attese
        crescenti (1, 2, 4… fino a 30 s): le voci scadute restano nel database e si
        annunciano appena un giro riesce."""
        attesa = 1.0
        while True:
            try:
                self._giro()
                attesa = 1.0
            except Exception as e:  # noqa: BLE001
                self.errori += 1
                print(f"   [AGENDA] Errore nel controllo delle scadenze ({type(e).__name__}: "
                      f"{e}): riprovo tra {attesa:.0f} s", flush=True)
                try:
                    with self._lock:
                        self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                self._wake.wait(attesa)
                self._wake.clear()
                attesa = min(attesa * 2, 30.0)

    def _giro(self):
        """Un giro: aspetta la prossima scadenza (al più 60 s) o toglie e annuncia quelle
        arrivate. Le voci si tolgono e si annunciano solo a transazione riuscita."""
        with self._lock:
            row = self.db.execute("SELECT MIN(due) FROM agenda").fetchone()
        next_due = row[0]
        wait = None if next_due is None else max(0.0, next_due - time.time())
        if wait is None or wait > 0:
            self._wake.wait(timeout=wait if wait is None else min(wait, 60))
            self._wake.clear()
            return
        items = []
        with self._lock:
            rows = self.db.execute(
                f"SELECT {_COLS} FROM agenda "
                "WHERE due <= ? ORDER BY due", (time.time(),)).fetchall()
            for r in rows:
                item = dict(zip(_FIELDS, r))
                if item["kind"] == "avviso" and item["parent"]:
                    # All'annuncio serve l'ora dell'appuntamento («tra un'ora hai…»)
                    p = self.db.execute("SELECT due FROM agenda WHERE id = ?",
                                        (item["parent"],)).fetchone()
                    item["target_due"] = p[0] if p else None
                items.append(item)
                self.db.execute("DELETE FROM agenda WHERE id = ?", (item["id"],))
            self.db.commit()
        for item in items:
            self.due.put(item)
            if self.on_scaduta is not None:
                try:
                    self.on_scaduta(dict(item))
                except Exception as e:  # noqa: BLE001 — l'annuncio conta di più
                    print(f"   [AGENDA] on_scaduta: {type(e).__name__}: {e}", flush=True)
        if items and self.on_due:
            try:
                self.on_due()
            except Exception as e:  # noqa: BLE001
                print(f"   [AGENDA] on_due: {type(e).__name__}: {e}", flush=True)


def _in(seconds: float) -> str:
    """Quanto manca, detto a voce: «tra un'ora», «tra 45 minuti», «tra 2 ore»."""
    minutes = max(1, round(seconds / 60))
    if minutes == 60:
        return "tra un'ora"
    if minutes % 60 == 0:
        return f"tra {minutes // 60} ore"
    if minutes > 60:
        h, m = divmod(minutes, 60)
        return f"tra {h} {'ora' if h == 1 else 'ore'} e {m} minuti"
    return "tra un minuto" if minutes == 1 else f"tra {minutes} minuti"


def announcement(item: dict, now: float | None = None) -> str:
    """La frase da dire quando una voce scade."""
    now = now or time.time()
    who = f"{item['owner_name']}, " if item.get("owner_name") else ""
    late = now - item["due"] > 120                    # scaduto mentre Calliope era spenta
    at = datetime.datetime.fromtimestamp(item["due"]).strftime("%H e %M")
    if item["kind"] == "timer":
        what = f"il timer {item['label']}" if item["label"] else "il timer"
        return f"{who}{'era scaduto' if late else 'è scaduto'} {what}."
    if item["kind"] == "appuntamento":
        return (f"{who}alle {at} avevi: {item['label']}." if late
                else f"{who}adesso hai: {item['label']}.")
    if item["kind"] == "avviso":
        target = item.get("target_due")
        if target is None or target <= now:
            return f"{who}ricordati: {item['label']}."
        return f"{who}{_in(target - now)} hai: {item['label']}."
    when = f" Era per le {at}." if late else ""
    return f"{who}ti ricordo: {item['label']}.{when}"
