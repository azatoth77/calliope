"""
I satelliti abbinati e i codici in attesa: lo stesso abbinamento degli schermi
(calliope/schermi/archivio.py, «device flow»), nelle tabelle `satelliti*` dello stesso file
della memoria.

1. il satellite nuovo si collega a /abbina e riceve un codice di 6 cifre (lo stampa) e una
   richiesta segreta e lunga, che tiene per sé;
2. chi amministra scrive il codice sul server: `python -m calliope.satellite --abbina 123456
   --stanza studio` (anche mentre Calliope è accesa: il file è condiviso);
3. il satellite, che aspetta sulla stessa connessione, scopre di essere abbinato: la
   richiesta diventa il suo token, che salva in satellite.json (fuori da git).

Sul server solo lo SHA-256 del token; 5 codici sbagliati in 10 minuti annullano tutti quelli
in attesa. Un satellite si revoca con `--revoca <stanza o nome>`: la sua connessione si
chiude al controllo successivo (ogni 5 s) e non si riapre.

**Abbinamento che riprende** (03/10, prova vera con un iPhone): per dire il codice la persona
esce dal browser, iOS sospende la pagina e chiude il WebSocket, e il token mandato a una
connessione morta si perdeva. Ora chi lo chiede (la web app del telefono, `ripresa: true`)
riceve con il codice anche una **ripresa**: un secondo segreto che tiene in localStorage e
che, su una connessione nuova, ritira lo stato («attesa» con lo stesso codice, «abbinato» con
il token, consegnato una volta sola, o «scaduto»). Sul disco ci sono solo lo SHA-256 della
ripresa e il token cifrato con una chiave che si ricava dalla ripresa (SHAKE-256): chi legge
il file non ricava né l'una né l'altro. La ripresa vale quanto il codice e, ad abbinamento
fatto, altri `codice_s` (10 minuti) per ritirare il token.

**Niente abbinamenti orfani**: un satellite abbinato ha `consegna` (la scadenza) finché il suo
token non è arrivato davvero, cioè finché non apre la prima sessione o la pagina non dice di
averlo salvato. Scaduta quella, l'abbinamento si toglie da solo.
"""

import hashlib
import secrets
import time

from ..persistenza import aggiungi_colonna
from ..schermi.archivio import ArchivioSchermi, cifre, hash_token, norm_stanza

__all__ = ["ArchivioSatelliti", "cifre", "hash_token", "norm_stanza"]


def _migra_ripresa(db):
    """Versione 2 (03/10): riprese degli abbinamenti e scadenza della consegna del token."""
    db.execute("""CREATE TABLE IF NOT EXISTS satelliti_ripresa (
                      id INTEGER PRIMARY KEY,
                      ripresa_hash TEXT NOT NULL UNIQUE,
                      richiesta_hash TEXT NOT NULL,
                      cifrato TEXT NOT NULL,      -- la richiesta (= il token) cifrata
                      scade REAL NOT NULL)""")
    # NULL: token consegnato (e tutti i satelliti abbinati prima)
    aggiungi_colonna(db, "satelliti", "consegna", "REAL")


def _chiave(ripresa: str, n: int) -> bytes:
    return hashlib.shake_256(b"calliope-ripresa:" + ripresa.encode("utf-8")).digest(n)


def _cifra(testo: str, ripresa: str) -> str:
    b = testo.encode("utf-8")
    return bytes(x ^ y for x, y in zip(b, _chiave(ripresa, len(b)))).hex()


def _decifra(cifrato: str, ripresa: str) -> str:
    b = bytes.fromhex(cifrato)
    return bytes(x ^ y for x, y in zip(b, _chiave(ripresa, len(b)))).decode("utf-8")


class ArchivioSatelliti(ArchivioSchermi):
    TABELLA = "satelliti"
    MIGRAZIONI = (_migra_ripresa,)

    # ── revoca: anche lo schermo del satellite (05/10) ──
    def revoca(self, chi) -> list[dict]:
        """Toglie i satelliti indicati e i loro schermi (la pagina che il satellite apriva,
        il carosello del telefono): uno schermo senza il suo satellite resterebbe un
        abbinamento orfano. Ogni satellite tolto ha in «schermi» i nomi degli schermi tolti
        con lui."""
        via = super().revoca(chi)
        if not via:
            return via
        ids = [s["id"] for s in via]
        with self._lock:
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(schermi)")}
            if "satellite" not in cols:          # schermi mai usati in questo file
                for s in via:
                    s["schermi"] = []
                return via
            segnaposti = ",".join("?" * len(ids))
            righe = self.db.execute(f"SELECT id, nome, satellite FROM schermi WHERE satellite "
                                    f"IN ({segnaposti})", ids).fetchall()
            if righe:
                self.db.execute(f"DELETE FROM schermi WHERE satellite IN ({segnaposti})", ids)
                self.db.commit()
        for s in via:
            s["schermi"] = [r[1] for r in righe if r[2] == s["id"]]
        return via

    # ── pulizia ──
    def _pulisci(self, now: float):
        super()._pulisci(now)
        self.db.execute("DELETE FROM satelliti_ripresa WHERE scade < ?", (now,))
        cur = self.db.execute("DELETE FROM satelliti WHERE consegna IS NOT NULL AND consegna < ?",
                              (now,))
        if cur.rowcount:
            self.versione += 1

    def _pulisci_ora(self):
        """Per le letture frequenti (per_token ogni 5 s per sessione): si scrive solo se
        c'è davvero qualcosa di scaduto."""
        now = time.time()
        with self._lock:
            if not self.db.execute(
                    "SELECT 1 FROM satelliti WHERE consegna IS NOT NULL AND consegna < ? UNION ALL "
                    "SELECT 1 FROM satelliti_ripresa WHERE scade < ? LIMIT 1",
                    (now, now)).fetchone():
                return
            self._pulisci(now)
            if self.db.in_transaction:
                self.db.commit()

    # ── richieste e riprese ──
    def nuova_richiesta(self, personale_chiesto: str | None = None,
                        ripresa: bool = False) -> dict:
        req = super().nuova_richiesta(personale_chiesto)
        if ripresa:
            r = secrets.token_urlsafe(32)
            with self._lock:
                self.db.execute("INSERT INTO satelliti_ripresa (ripresa_hash, richiesta_hash, "
                                "cifrato, scade) VALUES (?, ?, ?, ?)",
                                (hash_token(r), hash_token(req["richiesta"]),
                                 _cifra(req["richiesta"], r), req["scade"]))
                self.db.commit()
            req["ripresa"] = r
        return req

    def ritira(self, ripresa: str) -> dict:
        """Lo stato della richiesta di questa ripresa:
        {"stato": "attesa", "codice", "richiesta", "scade"}: ancora da abbinare;
        {"stato": "abbinato", "token", "schermo"}: il token, una volta sola (poi la ripresa
        non vale più); {"stato": "scaduto"}: scaduta, già usata o mai esistita, senza
        differenza (chi prova riprese a caso non impara niente)."""
        if not ripresa:
            return {"stato": "scaduto"}
        h = hash_token(ripresa)
        now = time.time()
        with self._lock:
            self._pulisci(now)
            row = self.db.execute("SELECT id, richiesta_hash, cifrato FROM satelliti_ripresa "
                                  "WHERE ripresa_hash = ?", (h,)).fetchone()
            if row is None:
                if self.db.in_transaction:
                    self.db.commit()
                return {"stato": "scaduto"}
            rid, rh, cifrato = row
            try:
                richiesta = _decifra(cifrato, ripresa)
            except (ValueError, UnicodeDecodeError):
                richiesta = ""
            sat = self.db.execute("SELECT id FROM satelliti WHERE token_hash = ?",
                                  (rh,)).fetchone()
            att = self.db.execute("SELECT codice, scade FROM satelliti_attesa WHERE "
                                  "richiesta_hash = ?", (rh,)).fetchone()
            if hash_token(richiesta) != rh or (sat is None and att is None):
                # Codice scaduto o annullato (5 codici sbagliati): la ripresa non serve più
                self.db.execute("DELETE FROM satelliti_ripresa WHERE id = ?", (rid,))
                self.db.commit()
                return {"stato": "scaduto"}
            if sat is not None:
                self.db.execute("DELETE FROM satelliti_ripresa WHERE id = ?", (rid,))
                self.db.commit()
                return {"stato": "abbinato", "token": richiesta, "schermo": self._get(sat[0])}
            if self.db.in_transaction:
                self.db.commit()
            return {"stato": "attesa", "codice": att[0], "richiesta": richiesta,
                    "scade": att[1]}

    def ricevuto(self, ripresa: str):
        """La pagina ha salvato il token arrivato sulla connessione: consegnato, e la ripresa
        non serve più."""
        if not ripresa:
            return
        h = hash_token(ripresa)
        with self._lock:
            self.db.execute("UPDATE satelliti SET consegna = NULL WHERE token_hash = (SELECT "
                            "richiesta_hash FROM satelliti_ripresa WHERE ripresa_hash = ?)", (h,))
            self.db.execute("DELETE FROM satelliti_ripresa WHERE ripresa_hash = ?", (h,))
            self.db.commit()

    def segna_consegnato(self, token: str):
        """Il token è arrivato (il satellite apre una sessione): l'abbinamento non scade più."""
        h = hash_token(token)
        with self._lock:
            cur = self.db.execute("UPDATE satelliti SET consegna = NULL WHERE token_hash = ? "
                                  "AND consegna IS NOT NULL", (h,))
            if cur.rowcount:
                self.db.execute("DELETE FROM satelliti_ripresa WHERE richiesta_hash = ?", (h,))
            if self.db.in_transaction:
                self.db.commit()

    # ── abbinamento ──
    def abbina(self, codice, stanza: str, *args, **kwargs) -> dict:
        res = super().abbina(codice, stanza, *args, **kwargs)
        if res.get("ok"):
            now = time.time()
            sid = res["schermo"]["id"]
            with self._lock:
                # Il token deve ancora arrivare al satellite: se non apre una sessione entro
                # codice_s l'abbinamento si toglie; la ripresa, se c'è, vale fino ad allora
                self.db.execute("UPDATE satelliti SET consegna = ? WHERE id = ?",
                                (now + self.codice_s, sid))
                self.db.execute("UPDATE satelliti_ripresa SET scade = ? WHERE richiesta_hash = "
                                "(SELECT token_hash FROM satelliti WHERE id = ?)",
                                (now + self.codice_s, sid))
                self.db.commit()
        return res

    def in_consegna(self) -> int:
        """Abbinamenti il cui token non è ancora arrivato al satellite."""
        self._pulisci_ora()
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM satelliti WHERE consegna IS NOT NULL"
                                   ).fetchone()[0]

    # ── letture: un abbinamento orfano scaduto non vale più ──
    def per_token(self, token: str) -> dict | None:
        if token:
            self._pulisci_ora()
        return super().per_token(token)

    def elenco(self) -> list[dict]:
        self._pulisci_ora()
        return super().elenco()
