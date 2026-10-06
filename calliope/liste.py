"""
Liste della casa: spesa, cose da fare, regali… condivise da tutta la famiglia, in SQLite
(stesso file della memoria).

«Aggiungi latte, pane e uova alla lista della spesa» → tre voci; «ho preso il pane» →
via il pane; «svuota la lista» → vuota. Le voci si confrontano senza articoli, maiuscole
e differenze di plurale («le uova» e «uovo» sono la stessa cosa), così non si creano
doppioni e si toglie la voce giusta anche detta in un altro modo. Si annota chi ha
aggiunto ogni voce. Gli ospiti non usano le liste (i tool sono per i familiari).
"""

import datetime
import difflib
import re
import sqlite3
import threading

from .persistenza import apri_db, prepara_schema

# Articoli e partitivi iniziali, come parole a sé: senza lo spazio o l'apostrofo, «la»
# prendeva anche l'inizio di «Latte» («tte»)
_ARTICLES = re.compile(r"^(?:un\s+po'?\s+di\s+|(?:il|lo|la|i|gli|le|un|uno|una|del|dello|"
                       r"della|dei|degli|delle|qualche)\s+|(?:l|un|dell|dall|nell)'\s*)", re.I)
# Espressioni del nome della lista da togliere: «la lista della spesa» → «spesa»
_LIST_WORDS = re.compile(r"\b(la|nella|alla|dalla|sulla)?\s*lista\b|^\s*(della|delle|dei|degli|"
                         r"del|dello|di|per|la|le|il|i)\s+", re.I)
DEFAULT = "spesa"


def list_key(name: str | None) -> str:
    """Nome normalizzato della lista: «lista della spesa», «della spesa», «Spesa» →
    «spesa»; «la lista delle cose da fare» → «cose da fare»."""
    n = (name or "").lower().strip(" .,!?")
    for _ in range(3):                                  # «nella lista della …»
        n = _LIST_WORDS.sub(" ", n).strip()
    return re.sub(r"\s+", " ", n) or DEFAULT


def say_list(key: str, prep: str = "") -> str:
    """Come dire il nome della lista, con la preposizione articolata se serve: «la lista
    della spesa», «alla lista cose da fare» (prep="a"), «nella…» ("in"), «dalla…» ("da")."""
    art = {"": "la", "a": "alla", "in": "nella", "da": "dalla"}[prep]
    return f"{art} lista della spesa" if key == DEFAULT else f"{art} lista {key}"


def split_items(text: str) -> list[str]:
    """«latte, pane e uova» → ["latte", "pane", "uova"]."""
    parts = re.split(r",|;|\s+e\s+|\s+ed\s+|\s+poi\s+|\s+anche\s+", text or "", flags=re.I)
    out = []
    for p in parts:
        p = p.strip(" .!?")
        if p and p.lower() not in ("e", "anche"):
            out.append(p)
    return out


def _norm(item: str) -> str:
    """Forma per confrontare: minuscole, senza articoli né vocale finale (plurali)."""
    t = item.lower().strip(" .!?")
    for _ in range(2):
        t = _ARTICLES.sub("", t).strip()
    words = [w[:-1] if len(w) > 3 and w[-1] in "aeio" else w for w in t.split()]
    return " ".join(words)


class Liste:
    SAME = 0.8          # somiglianza oltre la quale due voci sono la stessa cosa

    def __init__(self, path: str):
        self._lock = threading.Lock()
        self.db = apri_db(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS liste (
                               id INTEGER PRIMARY KEY,
                               lista TEXT NOT NULL,
                               voce TEXT NOT NULL,
                               norm TEXT NOT NULL,
                               added_by TEXT,
                               created TEXT NOT NULL)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS liste_lista ON liste(lista)")
        self.db.commit()
        # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
        # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
        # predefinito. Dati di una versione più nuova: sola lettura
        self.scrivibile = prepara_schema(self.db, "liste", [lambda db: None])

    def _rows(self, key: str) -> list[tuple[int, str, str]]:
        return self.db.execute("SELECT id, voce, norm FROM liste WHERE lista = ? ORDER BY id",
                               (key,)).fetchall()

    def _find(self, key: str, item: str) -> tuple[int, str] | None:
        n = _norm(item)
        best, score = None, 0.0
        for rid, voce, norm in self._rows(key):
            r = 1.0 if norm == n else difflib.SequenceMatcher(None, norm, n).ratio()
            if r > score:
                best, score = (rid, voce), r
        return best if score >= self.SAME else None

    def add(self, name: str | None, items: list[str], who: str | None = None):
        """Aggiunge le voci; restituisce (lista, aggiunte, già presenti)."""
        key = list_key(name)
        added, already = [], []
        with self._lock:
            for it in items:
                clean = _ARTICLES.sub("", it.strip()).strip() or it.strip()
                if self._find(key, clean):
                    already.append(clean)
                    continue
                self.db.execute("INSERT INTO liste (lista, voce, norm, added_by, created) "
                                "VALUES (?, ?, ?, ?, ?)",
                                (key, clean, _norm(clean), who,
                                 datetime.datetime.now().isoformat(timespec="seconds")))
                added.append(clean)
            self.db.commit()
        return key, added, already

    def read(self, name: str | None) -> tuple[str, list[str]]:
        key = list_key(name)
        with self._lock:
            return key, [voce for _, voce, _ in self._rows(key)]

    def remove(self, name: str | None, items: list[str]):
        """Toglie le voci («tutto» svuota); restituisce (lista, tolte, non trovate)."""
        key = list_key(name)
        removed, missing = [], []
        with self._lock:
            if any(re.fullmatch(r"\s*(tutto|tutta|tutte|tutti|tutto quanto)\s*", i, re.I)
                   for i in items):
                removed = [voce for _, voce, _ in self._rows(key)]
                self.db.execute("DELETE FROM liste WHERE lista = ?", (key,))
            else:
                for it in items:
                    found = self._find(key, it)
                    if found:
                        self.db.execute("DELETE FROM liste WHERE id = ?", (found[0],))
                        removed.append(found[1])
                    else:
                        missing.append(it)
            self.db.commit()
        return key, removed, missing

    def names(self) -> list[str]:
        with self._lock:
            return [r[0] for r in self.db.execute(
                "SELECT DISTINCT lista FROM liste ORDER BY lista").fetchall()]
