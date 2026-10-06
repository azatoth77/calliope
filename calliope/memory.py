"""
Memoria persistente di Calliope: fatti per persona, in SQLite.

Ogni fatto è legato al profilo di chi l'ha detto (UserProfile.id), non al nome, e lo
vede solo quella persona. Degli ospiti non si salva nulla. I fatti arrivano al modello
come un breve messaggio prima della domanda (Brain), così un modello da 4B non deve
ricordarsi di chiamare un tool per sapere «qual è il mio numero preferito?». Si
aggiungono e si tolgono con i tool `ricorda` e `dimentica` (tools/builtin.py).

Un fatto molto simile a uno già salvato lo sostituisce: «il mio numero preferito è 12»
prende il posto di «il mio numero preferito è 47».
"""

import datetime
import difflib
import re
import sqlite3
import threading
import time

from .persistenza import apri_db, prepara_schema


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\wàèéìòù ]", " ", text.lower())).strip()


# «Persona» dei fatti della casa, condivisi da tutta la famiglia (wifi, caldaia, dove
# stanno le cose): li vede chi è riconosciuto, gli ospiti no
HOUSE = "casa"


# ─────────── Un fatto da ricordare deve averlo detto la persona (04/10) ───────────
# «Qual è il mio numero preferito?» di chi non ne ha uno: gemma4 e4b inventava «47» (l'esempio
# della descrizione di `ricorda`) e lo salvava, 3 volte su 4. Vincolo verificabile, prima di
# salvare (tools/builtin._ricorda, regola `ricordo_non_detto`): ogni numero del fatto è stato
# detto dalla persona (in cifre o in lettere) in questa conversazione; e se la frase di adesso
# è una domanda, il fatto non porta parole nuove (una domanda non dice un fatto). Le parole si
# confrontano per radice («abito» = «abita»), senza articoli, preposizioni e parole di cornice
# («suo», «preferito», il nome di chi parla).
_FRAME = frozenset(
    "il lo la i gli le un uno una di a da in con su per tra fra del dello della dei degli "
    "delle al allo alla ai agli alle dal dalla dai dalle nel nello nella nei negli nelle sul "
    "sulla sui sulle e ed o che è sono ha hanno era suo sua suoi sue mio mia miei mie tuo tua "
    "lui lei si chiama preferito preferita preferiti preferite piace piacciono utente persona "
    "ricorda ricordati ricordare non più anche come cosa".split())


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 4 else w


def _numbers(text: str) -> list[str]:
    """I numeri di un testo, in cifre («ventitré» → «23»)."""
    from .tempi import word_number
    out = []
    for w in _norm(text).split():
        if w.isdigit():
            out.append(str(int(w)))
        else:
            n = word_number(w)
            if n is not None and w not in ("un", "una", "uno"):
                out.append(str(n))
    return out


def unsaid_value(fact: str, now: str, earlier=(), names=()) -> str | None:
    """Il pezzo di `fact` che la persona non ha detto (None se va bene). `now` è la frase di
    questo turno, `earlier` le sue frasi prima nella conversazione. Senza frase (`now`
    vuoto: chiamata fuori dal ciclo della voce) non si controlla niente."""
    if not (now or "").strip():
        return None
    said = " ".join([now, *earlier])
    have = set(_numbers(said))
    digits = "".join(_numbers(said))
    for n in _numbers(fact):
        if n not in have and n not in digits:
            return n
    if not now.rstrip().endswith("?"):
        return None
    skip = _FRAME | {_norm(n) for n in names if n}
    words = {_stem(w) for w in _norm(now).split()}
    for w in _norm(fact).split():
        if w in skip or len(w) < 3 or w.isdigit():
            continue
        if _stem(w) not in words:
            return w
    return None


class Memory:
    SAME_FACT = 0.75      # sopra questa somiglianza un fatto nuovo sostituisce il vecchio
    FORGET_MATCH = 0.45   # somiglianza minima per `forget`
    # Secondi in cui un ricordo cancellato si può ancora recuperare («annulla», «no,
    # ricordalo»: `recupera`, da ricorda). Solo in memoria: dopo un riavvio è cancellato
    RECUPERO_S = 300.0

    def __init__(self, path: str, max_facts: int = 50):
        self.max_facts = max_facts
        self._lock = threading.Lock()
        self.db = apri_db(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS facts (
                               id INTEGER PRIMARY KEY,
                               person TEXT NOT NULL,
                               text TEXT NOT NULL,
                               created TEXT NOT NULL,
                               updated TEXT NOT NULL)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS facts_person ON facts(person)")
        self.db.commit()
        # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
        # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
        # predefinito. Dati di una versione più nuova: sola lettura
        self.scrivibile = prepara_schema(self.db, "memoria", [lambda db: None])

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    def facts(self, person: str) -> list[str]:
        """I fatti di una persona, dal più vecchio al più recente."""
        with self._lock:
            rows = self.db.execute("SELECT text FROM facts WHERE person = ? ORDER BY id",
                                   (person,)).fetchall()
        return [r[0] for r in rows]

    def _closest(self, person: str, text: str) -> tuple[int | None, str | None, float]:
        rows = self.db.execute("SELECT id, text FROM facts WHERE person = ?",
                               (person,)).fetchall()
        best = (None, None, 0.0)
        for fid, ftext in rows:
            ratio = difflib.SequenceMatcher(None, _norm(ftext), _norm(text)).ratio()
            if ratio > best[2]:
                best = (fid, ftext, ratio)
        return best

    @staticmethod
    def _same_subject(a: str, b: str) -> bool:
        """Stesso fatto con un valore nuovo: le frasi iniziano con le stesse parole e
        cambia solo la coda («il suo numero preferito è quarantasette» → «… è dodici»).
        La somiglianza carattere per carattere non basta quando i valori sono lunghi."""
        wa, wb = _norm(a).split(), _norm(b).split()
        common = 0
        for x, y in zip(wa, wb):
            if x != y:
                break
            common += 1
        return common >= max(3, 0.6 * min(len(wa), len(wb)))

    def remember(self, person: str, text: str) -> dict:
        """Salva un fatto. Se ce n'è già uno molto simile lo sostituisce."""
        text = text.strip().rstrip(".") + "."
        with self._lock:
            fid, old, ratio = self._closest(person, text)
            if fid is None or ratio < self.SAME_FACT:
                # Stesso soggetto con un valore diverso?
                for rid, rtext in self.db.execute(
                        "SELECT id, text FROM facts WHERE person = ?", (person,)).fetchall():
                    if self._same_subject(rtext, text):
                        fid, old, ratio = rid, rtext, 1.0
                        break
            if fid is not None and ratio >= self.SAME_FACT:
                self.db.execute("UPDATE facts SET text = ?, updated = ? WHERE id = ?",
                                (text, self._now(), fid))
                self.db.commit()
                return {"ok": True, "aggiornato": True, "prima": old, "ora": text}
            count = self.db.execute("SELECT COUNT(*) FROM facts WHERE person = ?",
                                    (person,)).fetchone()[0]
            if count >= self.max_facts:
                # Si toglie il fatto toccato meno di recente
                self.db.execute("DELETE FROM facts WHERE id = (SELECT id FROM facts "
                                "WHERE person = ? ORDER BY updated LIMIT 1)", (person,))
            now = self._now()
            self.db.execute("INSERT INTO facts (person, text, created, updated) "
                            "VALUES (?, ?, ?, ?)", (person, text, now, now))
            self.db.commit()
        return {"ok": True, "aggiornato": False, "ora": text}

    def forget(self, person: str, text: str) -> dict:
        """Toglie il fatto più simile a `text` (o tutti con «tutto»). Quello che toglie resta
        recuperabile per `RECUPERO_S` secondi (`recupera`; prova e2e del 06/10: un ricordo
        cancellato a una domanda non tornava più)."""
        with self._lock:
            if _norm(text) in ("tutto", "tutti", "ogni cosa", "tutto quanto"):
                rows = self.db.execute("SELECT text, created, updated FROM facts WHERE "
                                       "person = ? ORDER BY id", (person,)).fetchall()
                n = self.db.execute("DELETE FROM facts WHERE person = ?", (person,)).rowcount
                self.db.commit()
                self._metti_da_parte(person, rows)
                return {"ok": True, "dimenticati": n}
            fid, old, ratio = self._closest(person, text)
            # Anche una parola chiave contenuta nel fatto basta («il numero preferito»)
            if fid is None or (ratio < self.FORGET_MATCH and _norm(text) not in _norm(old)):
                return {"ok": False, "errore": "non ricordo niente del genere"}
            rows = self.db.execute("SELECT text, created, updated FROM facts WHERE id = ?",
                                   (fid,)).fetchall()
            self.db.execute("DELETE FROM facts WHERE id = ?", (fid,))
            self.db.commit()
            self._metti_da_parte(person, rows)
        return {"ok": True, "dimenticato": old}

    def _metti_da_parte(self, person: str, rows):
        """I ricordi appena cancellati di una persona (solo l'ultima cancellazione)."""
        if not hasattr(self, "_cancellati"):
            self._cancellati = {}
        if rows:
            self._cancellati[person] = (time.monotonic(), [tuple(r) for r in rows])

    def recupera(self, person: str, text: str | None = None) -> list[str]:
        """Rimette i ricordi cancellati da meno di `RECUPERO_S` secondi (con le loro date), se
        `text` è vuoto, «tutto» o «annulla», oppure è uno di loro (somiglianza ≥ `SAME_FACT`
        e gli stessi numeri: «il mio numero preferito è 12» dopo aver dimenticato «… è 47» è
        un fatto nuovo, non un recupero). Restituisce i testi rimessi ([] = niente)."""
        with self._lock:
            quando, rows = getattr(self, "_cancellati", {}).get(person, (0.0, []))
            if not rows or time.monotonic() - quando > self.RECUPERO_S:
                return []
            n = _norm(text or "")
            if n and n not in ("tutto", "tutti", "annulla", "ogni cosa", "tutto quanto"):
                if not any(difflib.SequenceMatcher(None, _norm(r[0]), n).ratio()
                           >= self.SAME_FACT and set(_numbers(r[0])) == set(_numbers(text))
                           for r in rows):
                    return []
            presenti = {_norm(r[0]) for r in self.db.execute(
                "SELECT text FROM facts WHERE person = ?", (person,)).fetchall()}
            rimessi = []
            for testo, creato, aggiornato in rows:
                if _norm(testo) in presenti:
                    continue
                self.db.execute("INSERT INTO facts (person, text, created, updated) VALUES "
                                "(?, ?, ?, ?)", (person, testo, creato, aggiornato))
                rimessi.append(testo)
            self.db.commit()
            self._cancellati.pop(person, None)
        return rimessi
