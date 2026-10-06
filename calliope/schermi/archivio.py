"""
Gli schermi abbinati e i codici in attesa (SQLite, solo libreria standard).

Abbinamento sul modello del «device flow» (RFC 8628) e dell'esecutore dei PC
(docs/ricerche/2026-10-01-mappe-e-schermi.md, §9.3):

1. la pagina di uno schermo nuovo chiede un abbinamento: riceve un **codice di 6 cifre**, da
   mostrare grande, e una **richiesta** segreta e lunga che resta solo nella pagina;
2. chi amministra dice il codice a Calliope (o lo scrive in `python -m calliope.schermi`)
   con la stanza: il codice si lega a quello schermo;
3. la pagina, che intanto chiede a che punto è con la sua richiesta, scopre di essere
   abbinata: **la richiesta diventa il token** dello schermo, senza che un token viaggi una
   seconda volta.

Sul disco c'è solo lo SHA-256 della richiesta (e del token): chi legge il file non può
fingersi uno schermo. Il codice sta in chiaro finché è in attesa (10 minuti al massimo):
a voce si confronta con quello detto. Dopo 5 codici sbagliati in 10 minuti tutti i codici
in attesa si annullano e le pagine ne chiedono uno nuovo.

Lo stesso file della memoria (memoria.db): la usano sia Calliope (server e tool) sia il
comando da terminale, anche mentre Calliope è accesa.
"""

import hashlib
import re
import secrets
import sqlite3
import threading
import time

from ..persistenza import apri_db, prepara_schema

# Codici in attesa tenuti al massimo (una pagina che si ricarica ne chiede uno nuovo)
MAX_ATTESA = 20
TENTATIVI = 5                 # codici sbagliati ammessi …
TENTATIVI_FINESTRA_S = 600.0  # … in questa finestra

# Parole intere davanti al nome della stanza («ilaria» non perde «il»)
_PREPOSIZIONI = re.compile(
    r"^(?:(?:al|allo|alla|alle|ai|agli|nel|nello|nella|nelle|nei|negli|in|del|dello|della|"
    r"delle|dei|degli|di|da|dal|dalla|il|lo|la|le|i|gli|per|sul|sulla|schermo|schermi)"
    r"(?:\s+|$)"
    r"|(?:all|nell|dell|l|sull)'\s*)", re.I)


def hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def norm_stanza(testo: str | None) -> str:
    """«al soggiorno», «della Cucina», «lo studio.» → «soggiorno», «cucina», «studio».
    È una conversione dell'argomento scelto dal modello (principio 10), non una scelta."""
    t = re.sub(r"[^\w' ]+", " ", str(testo or "").lower().replace("’", "'"))
    t = re.sub(r"\s+", " ", t).strip()
    for _ in range(5):
        nuovo = _PREPOSIZIONI.sub("", t).strip()
        if nuovo == t:
            break
        t = nuovo
    return t


def quando(t: float | None) -> str:
    """«05/10 14:50», o «mai» (per gli elenchi e gli avvisi degli abbinamenti)."""
    return time.strftime("%d/%m %H:%M", time.localtime(t)) if t else "mai"


def avviso_inattivi(inattivi: list[dict], cosa: str, giorni: float, comando: str) -> str:
    """La riga per chi amministra: quali abbinamenti non si collegano da più di `giorni` e
    come revocarli. Solo un avviso: niente si toglie da solo (05/10)."""
    if not inattivi:
        return ""
    voci = ", ".join(
        f"«{s['nome']}» (" + ("mai collegato" if not s.get("visto")
                              else "ultimo " + quando(s["visto"])) + ")"
        for s in inattivi)
    return (f"{len(inattivi)} {cosa} senza collegamento da più di {giorni:g} giorni: {voci}. "
            f"Se non servono: {comando} <nome>.")


def cifre(testo) -> str:
    """Solo le cifre: «123 456», «123.456», «1-2-3-4-5-6» → «123456»."""
    return "".join(ch for ch in str(testo or "") if ch.isdigit())


class ArchivioSchermi:
    # Nome della tabella: i satelliti (calliope/satellite/archivio.py) usano lo stesso
    # abbinamento con le loro tabelle, nello stesso file
    TABELLA = "schermi"
    # Migrazioni dalla versione 1 in poi, per la tabella di questa classe (i satelliti ne
    # hanno una loro: calliope/satellite/archivio.py)
    MIGRAZIONI: tuple = ()

    def __init__(self, path: str, codice_min: float = 10.0):
        self.T = self.TABELLA
        self.path = path
        self.codice_s = max(60.0, float(codice_min) * 60.0)
        self._lock = threading.Lock()
        self.db = apri_db(path)
        with self._lock:
            self.db.executescript(f"""
                CREATE TABLE IF NOT EXISTS {self.T} (
                    id INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL,
                    stanza TEXT NOT NULL,
                    proprietario TEXT,            -- UserProfile.id: schermo personale
                    proprietario_nome TEXT,
                    token_hash TEXT NOT NULL UNIQUE,
                    creato REAL NOT NULL,
                    visto REAL);
                CREATE TABLE IF NOT EXISTS {self.T}_attesa (
                    id INTEGER PRIMARY KEY,
                    codice TEXT NOT NULL,
                    richiesta_hash TEXT NOT NULL UNIQUE,
                    creato REAL NOT NULL,
                    scade REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS {self.T}_tentativi (t REAL NOT NULL);
            """)
            # 02/10: chi il satellite chiede come proprietario del suo schermo (una richiesta,
            # mai applicata da sola: vedi abbina). Aggiunta alle tabelle già esistenti
            cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({self.T}_attesa)")}
            if "personale_chiesto" not in cols:
                self.db.execute(f"ALTER TABLE {self.T}_attesa ADD COLUMN personale_chiesto TEXT")
            # 03/10 (analisi di sicurezza, rete, difetto 3): il ruolo di un satellite, deciso
            # da chi abbina. Solo «pc» porta con sé l'esecutore del PC (volume, file,
            # documenti); prima lo prendeva qualunque satellite che lo dichiarasse. Ai
            # satelliti abbinati prima resta il comportamento di prima
            cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({self.T})")}
            if "ruolo" not in cols:
                self.db.execute(f"ALTER TABLE {self.T} ADD COLUMN ruolo TEXT")
                if self.T == "satelliti":
                    self.db.execute(f"UPDATE {self.T} SET ruolo = 'pc'")
            # 05/10: lo schermo di un satellite sa di chi è (id nella tabella `satelliti`), così
            # ai ricollegamenti e dopo i riavvii il satellite ritrova il suo invece di farne
            # nascere uno nuovo, e revocare il satellite revoca anche lui. Colonna con NULL
            # fuori dalle versioni dello schema: una versione di prima la ignora
            if self.T == "schermi" and "satellite" not in cols:
                self.db.execute("ALTER TABLE schermi ADD COLUMN satellite INTEGER")
            self.db.commit()
            # Le colonne lette: «satellite» solo dove c'è (non nella tabella dei satelliti)
            cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({self.T})")}
            self._campi = tuple(c for c in self._CAMPI if c in cols)
            # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
            # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
            # predefinito. Dati di una versione più nuova: sola lettura
            self.scrivibile = prepara_schema(self.db, self.T,
                                             [lambda db: None, *self.MIGRAZIONI])
        # Cambia a ogni abbinamento o revoca fatti da questo processo (cache dell'hub)
        self.versione = 0

    def close(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass

    # ── codici in attesa ──
    def _pulisci(self, now: float):
        self.db.execute(f"DELETE FROM {self.T}_attesa WHERE scade < ?", (now,))
        self.db.execute(f"DELETE FROM {self.T}_tentativi WHERE t < ?",
                        (now - TENTATIVI_FINESTRA_S,))

    def nuova_richiesta(self, personale_chiesto: str | None = None) -> dict:
        """Per una pagina senza token: {codice, richiesta, scade}. La richiesta è il segreto
        della pagina (diventerà il suo token): qui si salva solo il suo hash.
        `personale_chiesto`: il nome che il satellite chiede come proprietario del suo
        schermo; resta una richiesta, che `abbina` restituisce e non applica."""
        now = time.time()
        richiesta = secrets.token_urlsafe(32)
        with self._lock:
            self._pulisci(now)
            usati = {r[0] for r in self.db.execute(f"SELECT codice FROM {self.T}_attesa")}
            codice = f"{secrets.randbelow(10 ** 6):06d}"
            while codice in usati:
                codice = f"{secrets.randbelow(10 ** 6):06d}"
            chiesto = str(personale_chiesto or "").strip()[:40] or None
            self.db.execute(f"INSERT INTO {self.T}_attesa (codice, richiesta_hash, creato, scade, "
                            "personale_chiesto) VALUES (?, ?, ?, ?, ?)",
                            (codice, hash_token(richiesta), now, now + self.codice_s, chiesto))
            # Al massimo MAX_ATTESA codici: i più vecchi lasciano il posto
            self.db.execute(f"DELETE FROM {self.T}_attesa WHERE id NOT IN (SELECT id FROM "
                            f"{self.T}_attesa ORDER BY creato DESC LIMIT ?)", (MAX_ATTESA,))
            self.db.commit()
        return {"codice": codice, "richiesta": richiesta, "scade": now + self.codice_s}

    def stato_richiesta(self, richiesta: str) -> dict:
        """«attesa», «abbinato» (con lo schermo) o «scaduto» per la richiesta della pagina."""
        h = hash_token(richiesta)
        now = time.time()
        with self._lock:
            row = self.db.execute(f"SELECT id FROM {self.T} WHERE token_hash = ?", (h,)).fetchone()
            if row:
                return {"stato": "abbinato", "schermo": self._get(row[0])}
            row = self.db.execute(f"SELECT scade FROM {self.T}_attesa WHERE richiesta_hash = ?",
                                  (h,)).fetchone()
        if row and row[0] >= now:
            return {"stato": "attesa", "scade": row[0]}
        return {"stato": "scaduto"}

    def in_attesa(self) -> int:
        with self._lock:
            self._pulisci(time.time())
            return self.db.execute(f"SELECT COUNT(*) FROM {self.T}_attesa").fetchone()[0]

    # ── abbinamento ──
    def abbina(self, codice, stanza: str, proprietario: str | None = None,
               proprietario_nome: str | None = None, nome: str | None = None,
               ruolo: str | None = None) -> dict:
        """Lega il codice detto a uno schermo in attesa. {"ok", "esito", "schermo"}:
        esito «abbinato», «sbagliato» (nessun codice così in attesa), «troppi» (codici
        annullati per sicurezza), «formato» (non sono 6 cifre), «stanza» (manca)."""
        codice = cifre(codice)
        stanza = norm_stanza(stanza)
        if len(codice) != 6:
            return {"ok": False, "esito": "formato"}
        if not stanza:
            return {"ok": False, "esito": "stanza"}
        now = time.time()
        with self._lock:
            self._pulisci(now)
            row = self.db.execute(f"SELECT id, richiesta_hash, personale_chiesto FROM "
                                  f"{self.T}_attesa WHERE codice = ?", (codice,)).fetchone()
            if row is None:
                self.db.execute(f"INSERT INTO {self.T}_tentativi (t) VALUES (?)", (now,))
                n = self.db.execute(f"SELECT COUNT(*) FROM {self.T}_tentativi").fetchone()[0]
                if n >= TENTATIVI:
                    # Qualcuno prova i codici a caso: si annullano tutti, le pagine ne
                    # chiederanno uno nuovo da sole
                    self.db.execute(f"DELETE FROM {self.T}_attesa")
                    self.db.execute(f"DELETE FROM {self.T}_tentativi")
                    self.db.commit()
                    return {"ok": False, "esito": "troppi"}
                self.db.commit()
                return {"ok": False, "esito": "sbagliato"}
            base = norm_stanza(nome) if nome else stanza
            if proprietario_nome and not nome:
                base = f"{stanza} di {proprietario_nome}".lower()
            nomi = {r[0] for r in self.db.execute(f"SELECT nome FROM {self.T}")}
            nome_finale, k = base, 2
            while nome_finale in nomi:
                nome_finale, k = f"{base} {k}", k + 1
            cur = self.db.execute(
                f"INSERT INTO {self.T} (nome, stanza, proprietario, proprietario_nome, token_hash, "
                "creato, ruolo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nome_finale, stanza, proprietario, proprietario_nome, row[1], now, ruolo))
            self.db.execute(f"DELETE FROM {self.T}_attesa WHERE id = ?", (row[0],))
            self.db.execute(f"DELETE FROM {self.T}_tentativi")
            self.db.commit()
            sid = cur.lastrowid
            self.versione += 1
            # La richiesta del satellite si restituisce, non si applica: decide chi abbina
            return {"ok": True, "esito": "abbinato", "schermo": self._get(sid),
                    "personale_chiesto": row[2]}

    def crea_con_token(self, stanza: str, proprietario: str | None = None,
                       proprietario_nome: str | None = None,
                       ruolo: str | None = None,
                       satellite: int | None = None) -> tuple[dict, str]:
        """Da terminale, per il kiosk di Edge (InPrivate: localStorage perso a ogni avvio):
        uno schermo già abbinato e il suo token, da mettere nell'URL dopo «#t=». Il token si
        mostra una volta sola e non si salva. Con `satellite` (id) è lo schermo di quel
        satellite (solo nella tabella degli schermi)."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        stanza = norm_stanza(stanza)
        if not stanza:
            raise ValueError("manca la stanza")
        with self._lock:
            nomi = {r[0] for r in self.db.execute(f"SELECT nome FROM {self.T}")}
            base = f"{stanza} di {proprietario_nome}".lower() if proprietario_nome else stanza
            nome_finale, k = base, 2
            while nome_finale in nomi:
                nome_finale, k = f"{base} {k}", k + 1
            cur = self.db.execute(
                f"INSERT INTO {self.T} (nome, stanza, proprietario, proprietario_nome, token_hash, "
                "creato, ruolo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nome_finale, stanza, proprietario, proprietario_nome, hash_token(token), now,
                 ruolo))
            if satellite is not None and "satellite" in self._campi:
                self.db.execute(f"UPDATE {self.T} SET satellite = ? WHERE id = ?",
                                (int(satellite), cur.lastrowid))
            self.db.commit()
            self.versione += 1
            return self._get(cur.lastrowid), token

    # ── schermi ──
    _CAMPI = ("id", "nome", "stanza", "proprietario", "proprietario_nome", "creato", "visto",
              "ruolo", "satellite")

    def _get(self, sid: int) -> dict | None:
        row = self.db.execute(f"SELECT {', '.join(self._campi)} FROM {self.T} WHERE id = ?",
                              (sid,)).fetchone()
        return dict(zip(self._campi, row)) if row else None

    def per_token(self, token: str) -> dict | None:
        """Lo schermo di questo token, o None (mai abbinato, o revocato)."""
        if not token:
            return None
        with self._lock:
            row = self.db.execute(f"SELECT id FROM {self.T} WHERE token_hash = ?",
                                  (hash_token(token),)).fetchone()
            return self._get(row[0]) if row else None

    def segna_visto(self, sid: int):
        with self._lock:
            self.db.execute(f"UPDATE {self.T} SET visto = ? WHERE id = ?", (time.time(), sid))
            self.db.commit()

    def elenco(self) -> list[dict]:
        with self._lock:
            rows = self.db.execute(f"SELECT {', '.join(self._campi)} FROM {self.T} "
                                   f"ORDER BY id").fetchall()
        return [dict(zip(self._campi, r)) for r in rows]

    def esiste(self, sid: int) -> bool:
        with self._lock:
            return self.db.execute(f"SELECT 1 FROM {self.T} WHERE id = ?",
                                   (sid,)).fetchone() is not None

    def trova(self, chi) -> list[dict]:
        """Gli schermi indicati da id, nome o stanza («cucina», «lo schermo della cucina»)."""
        tutti = self.elenco()
        if isinstance(chi, int) or str(chi).strip().isdigit():
            return [s for s in tutti if s["id"] == int(chi)]
        q = norm_stanza(chi)
        if not q:
            return []
        esatti = [s for s in tutti if s["nome"] == q]
        return esatti or [s for s in tutti if s["stanza"] == q]

    def imposta_proprietario(self, sid: int, proprietario: str | None,
                             proprietario_nome: str | None) -> dict | None:
        """Rende personale (o della stanza, con None) uno schermo o un satellite già
        abbinato, senza rifare l'abbinamento. Il nome resta quello di prima."""
        with self._lock:
            cur = self.db.execute(f"UPDATE {self.T} SET proprietario = ?, proprietario_nome = ? "
                                  "WHERE id = ?", (proprietario or None,
                                                   proprietario_nome or None, sid))
            self.db.commit()
            if not cur.rowcount:
                return None
            self.versione += 1
            return self._get(sid)

    def imposta_ruolo(self, sid: int, ruolo: str | None) -> dict | None:
        """Il ruolo di un satellite già abbinato («pc» o None). Il nome resta."""
        with self._lock:
            cur = self.db.execute(f"UPDATE {self.T} SET ruolo = ? WHERE id = ?",
                                  (ruolo or None, sid))
            self.db.commit()
            if not cur.rowcount:
                return None
            self.versione += 1
            return self._get(sid)

    # ── schermi dei satelliti (05/10) ──
    def per_satellite(self, sat_id: int) -> dict | None:
        """Lo schermo legato al satellite `sat_id` (il più recente, se ce ne fosse più d'uno)."""
        with self._lock:
            row = self.db.execute(f"SELECT id FROM {self.T} WHERE satellite = ? ORDER BY id DESC "
                                  "LIMIT 1", (int(sat_id),)).fetchone()
            return self._get(row[0]) if row else None

    def lega_satellite(self, sid: int, sat_id: int) -> dict | None:
        """Lo schermo `sid` diventa quello del satellite `sat_id` (uno schermo di prima del
        05/10, ritrovato dal token che il satellite ha conservato)."""
        with self._lock:
            cur = self.db.execute(f"UPDATE {self.T} SET satellite = ? WHERE id = ?",
                                  (int(sat_id), sid))
            self.db.commit()
            if not cur.rowcount:
                return None
            self.versione += 1
            return self._get(sid)

    def rinnova_token(self, sid: int) -> str | None:
        """Un token nuovo per lo schermo `sid`, che resta lo stesso (nome, stanza,
        proprietario, cronologia): serve quando il suo satellite ha perso il token (file
        delle credenziali rifatto, pagina del telefono ripulita). Sul disco solo l'hash, come
        sempre; il token vecchio non vale più."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            cur = self.db.execute(f"UPDATE {self.T} SET token_hash = ? WHERE id = ?",
                                  (hash_token(token), sid))
            self.db.commit()
            if not cur.rowcount:
                return None
            self.versione += 1
        return token

    def inattivi(self, giorni: float, now: float | None = None) -> list[dict]:
        """Gli abbinamenti senza un collegamento da più di `giorni` (mai collegati: dalla
        creazione). Si segnalano e basta: decide chi amministra se revocarli."""
        if not giorni or giorni <= 0:
            return []
        limite = (now if now is not None else time.time()) - float(giorni) * 86400.0
        return [s for s in self.elenco() if (s.get("visto") or s["creato"]) < limite]

    def revoca(self, chi) -> list[dict]:
        """Toglie gli schermi indicati: il loro token non vale più. Restituisce i tolti."""
        via = self.trova(chi)
        if not via:
            return []
        with self._lock:
            self.db.executemany(f"DELETE FROM {self.T} WHERE id = ?", [(s["id"],) for s in via])
            self.db.commit()
            self.versione += 1
        return via
