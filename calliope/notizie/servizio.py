"""
Il servizio delle notizie (13/10/2026): scarico dei feed, indice su disco, fatti raggruppati.

- **Indice**: un file SQLite (`notizie_db`) con le voci delle ultime `notizie_conserva_giorni`
  (titolo pulito accanto all'originale, sommario di al più 600 caratteri, testata, tema, data,
  link solo per i doppioni e la scheda) e lo stato di ogni feed (ETag, Last-Modified, ultimo
  scarico, età dell'ultima voce). Doppioni nella stessa testata (stesso link o stesso titolo)
  una volta sola. In memoria le voci con le loro radici per la ricerca e i gruppi.
- **Quando si scarica**: ogni `notizie_intervallo_min`, solo se qualcuno ha chiesto notizie
  negli ultimi `notizie_attesa_giorni` (decisione del 12/10, compromesso con la 0024); i feed
  `veloce` ogni metà intervallo nei giorni in cui qualcuno le chiede. La prima richiesta dopo una
  pausa scarica subito (circa 1 s in parallelo, PRIMA_ATTESA_S al più). Richieste condizionate,
  PARALLELI feed alla volta, un feed che fallisce non ferma gli altri, `robots.txt` rispettato.
- **Fatti**: le voci delle ultime 36 ore raggruppate (gruppi.py); un fatto ha le voci di tutte
  le testate che l'hanno dato. Per «le notizie di oggi» i fatti dei feed generali delle ultime 24
  ore, dal più dato; per un tema o una parola le voci che la contengono (radici delle parole,
  come la biblioteca).

La domanda non esce mai di casa: esce solo lo scarico, uguale per ogni casa. Solo libreria
standard (sqlite3, threading, concurrent.futures).
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..testi import MESI
from ..web.servizio import ripulisci_testo
from . import gruppi, lettore, pulizia
from .feed import TEMI_MINORI, Feed

PARALLELI = 6
SOMMARIO_MAX = 600              # caratteri tenuti del sommario (AGI ne dà 2 000)
TITOLO_MAX = 220
ORE_GRUPPI = 36                 # si raggruppano le voci di queste ultime ore
ORE_OGGI = 24                   # «le notizie di oggi»
GIORNI_VECCHIO = 3              # come web_cerca: oltre, «vecchio»
ORE_RIPIEGO = 72                # meno di VOCI_RIPIEGO voci sul tema in queste ore: ripiego
VOCI_RIPIEGO = 2
VECCHIO_S = 6 * 3600            # l'ultimo scarico riuscito più vecchio: ripiego
PRIMA_ATTESA_S = 4.0            # al più tanto si aspetta lo scarico alla prima richiesta
GIRO_S = 300.0                  # ogni quanto il thread guarda se è ora di scaricare
ROBOTS_S = 24 * 3600
DETTE_S = 6 * 3600              # i fatti già detti a una persona valgono per tante ore
# Un feed fermo (età dell'ultima voce), per tema: una testata sportiva ferma da giorni è rotta,
# la Protezione civile o una rivista per ragazzi no (ricerca del 13/10, § 3.3)
FERMO_GIORNI = {"generale": 2, "sport": 2, "economia": 3, "locale": 3, "tecnologia": 7,
                "ragazzi": 14, "allerta": 14}

_GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


def _senza_accenti(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def radici_ricerca(testo: str) -> list[str]:
    """Le radici delle parole per la ricerca, come la biblioteca (`_stem`: «scioperi» e
    «sciopero» coincidono), senza accenti e senza parole vuote."""
    from ..biblioteca import _STOP, _stem
    out = []
    for w in re.findall(r"[a-z0-9]+", _senza_accenti(testo).replace("'", " ")):
        if w in _STOP or (len(w) < 2 and not w.isdigit()):
            continue
        r = _stem(w)
        if r not in out:
            out.append(r)
    return out


@dataclass
class Voce:
    id: int
    feed: str
    testata: str
    tema: str
    titolo: str
    sommario: str
    link: str
    t: float
    senza_data: bool = False
    regole: tuple = ()
    titolo_orig: str = ""
    r_titolo: frozenset = field(default_factory=frozenset)
    r_tutto: frozenset = field(default_factory=frozenset)


@dataclass
class Fatto:
    ids: list                   # le voci del gruppo, dalla più recente
    voci: list
    punteggio: float = 0.0

    @property
    def testate(self) -> list[str]:
        out = []
        for v in self.voci:
            if v.testata not in out:
                out.append(v.testata)
        return out

    @property
    def t(self) -> float:
        return max(v.t for v in self.voci)

    @property
    def titolo(self) -> str:
        """Il titolo più corto del gruppo, purché dica qualcosa (almeno 25 caratteri)."""
        buoni = [v.titolo for v in self.voci if len(v.titolo) >= 25] or [
            v.titolo for v in self.voci]
        return min(buoni, key=len) if buoni else ""

    @property
    def sommario(self) -> str:
        for v in self.voci:
            if v.sommario:
                return v.sommario
        return ""

    @property
    def senza_data(self) -> bool:
        return all(v.senza_data for v in self.voci)


# ─────────────────────────── le parole del tempo ───────────────────────────

def quando(t: float, adesso: float | None = None, senza_data: bool = False) -> str:
    """«poco fa», «40 minuti fa», «stamattina alle 9:40», «ieri sera», «sabato», «il 3
    ottobre»; «di recente» senza data (mai «oggi»)."""
    if senza_data:
        return "di recente"
    adesso = time.time() if adesso is None else adesso
    diff = adesso - t
    if diff < 600:
        return "poco fa"
    if diff < 3600:
        return f"{int(diff // 60)} minuti fa"
    loc = lettore.utc_a_roma(dt.datetime.fromtimestamp(t, lettore.UTC))
    ora = lettore.utc_a_roma(dt.datetime.fromtimestamp(adesso, lettore.UTC))
    giorni = (ora.date() - loc.date()).days
    h = loc.hour
    parte = ("stanotte" if h < 6 else "stamattina" if h < 12 else "oggi pomeriggio" if h < 18
             else "stasera")
    if giorni == 0:
        return f"{parte} alle {loc.hour}:{loc.minute:02d}"
    if giorni == 1:
        return {"stanotte": "ieri notte", "stamattina": "ieri mattina",
                "oggi pomeriggio": "ieri pomeriggio", "stasera": "ieri sera"}[parte]
    if giorni < 7:
        return _GIORNI[loc.weekday()]
    return f"il {loc.day} {MESI[loc.month - 1]}"


def oggi_detto(adesso: float | None = None) -> str:
    ora = lettore.utc_a_roma(dt.datetime.fromtimestamp(
        time.time() if adesso is None else adesso, lettore.UTC))
    return f"{_GIORNI[ora.weekday()]} {ora.day} {MESI[ora.month - 1]} {ora.year}"


# ─────────────────────────── il servizio ───────────────────────────

class Notizie:
    """Feed, indice e fatti. Thread-safe: il thread dello scarico e quello della voce."""

    def __init__(self, cfg, feeds: list[Feed], db_path: str = ":memory:", log=print,
                 orologio=time.time, scarica=None):
        self.cfg = cfg
        self.feeds = list(feeds)
        self.log = log
        self.orologio = orologio
        # Lo scaricatore (lettore.scarica): le prove ne passano uno verso un server finto
        self._scarica = scarica or lettore.scarica
        self.intervallo_s = max(60.0, float(getattr(cfg, "notizie_intervallo_min", 120)) * 60)
        self.attesa_s = max(0.0, float(getattr(cfg, "notizie_attesa_giorni", 7)) * 86400)
        self.conserva_s = max(3600.0, float(getattr(cfg, "notizie_conserva_giorni", 7)) * 86400)
        self._lock = threading.RLock()
        self._scarico_lock = threading.Lock()
        self._scarico_fatto = threading.Event()
        self._scarico_fatto.set()
        self._ferma = threading.Event()
        self._thread = None
        self._robots: dict[str, tuple[float, object]] = {}
        self._voci: list[Voce] = []
        self._gruppo: dict[int, int] = {}
        self._membri: dict[int, list[int]] = {}
        self._per_id: dict[int, Voce] = {}
        self._dette: dict[str, tuple[float, set]] = {}
        self._elenchi: dict[str, tuple[float, list]] = {}
        self.ultimo_giro: dict = {}
        if db_path != ":memory:":
            d = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS voci (
                id INTEGER PRIMARY KEY, feed TEXT, testata TEXT, tema TEXT, titolo TEXT,
                titolo_orig TEXT, titolo_l TEXT, sommario TEXT, link TEXT, t REAL,
                senza_data INTEGER, visto REAL, regole TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS voci_link ON voci(testata, link);
            CREATE UNIQUE INDEX IF NOT EXISTS voci_titolo ON voci(testata, titolo_l);
            CREATE INDEX IF NOT EXISTS voci_t ON voci(t);
            CREATE TABLE IF NOT EXISTS feed (
                url TEXT PRIMARY KEY, testata TEXT, tema TEXT, etag TEXT, modificato TEXT,
                ultimo_ok REAL, ultimo_tentativo REAL, ultima_voce REAL, errore TEXT,
                voci INTEGER);
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
        """)
        self.db.commit()
        self._ricarica()

    # ── stato su disco ──
    def _meta(self, k: str, v=None):
        with self._lock:
            if v is None:
                r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
                return r[0] if r else None
            self.db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)", (k, str(v)))
            self.db.commit()
            return v

    def _meta_t(self, k: str) -> float:
        try:
            return float(self._meta(k) or 0)
        except ValueError:
            return 0.0

    @property
    def ultima_richiesta(self) -> float:
        return self._meta_t("ultima_richiesta")

    @property
    def ultimo_ok(self) -> float:
        """L'ultimo scarico in cui almeno un feed ha risposto (200 o 304)."""
        return self._meta_t("ultimo_ok")

    @property
    def ultimo_scarico(self) -> float:
        return self._meta_t("ultimo_scarico")

    def richiesta(self):
        """Qualcuno ha chiesto le notizie: lo scarico periodico resta acceso."""
        self._meta("ultima_richiesta", f"{self.orologio():.0f}")

    def attivo(self) -> bool:
        """Lo scarico periodico è acceso (qualcuno ha chiesto notizie di recente)."""
        r = self.ultima_richiesta
        return bool(r) and self.orologio() - r <= self.attesa_s

    def fresco(self) -> bool:
        """L'indice è aggiornato: non serve scaricare prima di rispondere."""
        return bool(self._voci) and self.orologio() - self.ultimo_ok <= self.intervallo_s + 1800

    # ── scarico ──
    def _permesso(self, url: str) -> bool:
        """Il robots.txt del sito permette il feed a «Calliope»? (letto una volta al giorno;
        se non si legge, il feed resta permesso: è fatto per i lettori)."""
        u = urlsplit(url)
        base = f"{u.scheme}://{u.netloc}"
        adesso = self.orologio()
        with self._lock:
            c = self._robots.get(base)
        if c is None or adesso - c[0] > ROBOTS_S:
            rp = None
            try:
                r = self._scarica(base + "/robots.txt", max_byte=500_000, timeout_s=5.0)
                if r.get("stato") == 200:
                    rp = urllib.robotparser.RobotFileParser()
                    rp.parse(r["dati"].decode("utf-8", "replace").splitlines())
            except lettore.FeedNonLetto:
                rp = None
            except Exception:  # noqa: BLE001 — un robots.txt strano non ferma lo scarico
                rp = None
            c = (adesso, rp)
            with self._lock:
                self._robots[base] = c
        return c[1] is None or c[1].can_fetch("Calliope", url)

    def _uno(self, f: Feed) -> dict:
        """Scarica e legge un feed: {"feed", "stato", "voci" | "errore", "etag", "modificato"}."""
        with self._lock:
            r = self.db.execute("SELECT etag, modificato FROM feed WHERE url=?",
                                (f.url,)).fetchone()
        etag, modif = (r or ("", ""))
        try:
            if not self._permesso(f.url):
                return {"feed": f, "errore": "vietato dal robots.txt"}
            r = self._scarica(f.url, etag=etag or "", modificato=modif or "")
            if r["stato"] == 304:
                return {"feed": f, "stato": 304, "voci": [], "etag": etag, "modificato": modif}
            return {"feed": f, "stato": 200, "voci": lettore.leggi(r["dati"]),
                    "etag": r.get("etag") or "", "modificato": r.get("modificato") or ""}
        except lettore.FeedNonLetto as e:
            return {"feed": f, "errore": str(e)}
        except Exception as e:  # noqa: BLE001 — un feed rotto non ferma gli altri
            return {"feed": f, "errore": f"{type(e).__name__}"}

    def _inserisci(self, f: Feed, grezze: list[dict], adesso: float) -> tuple[int, float, dict]:
        """(voci nuove, istante della voce più recente del feed, regole contate)."""
        nuove, ultima, conta = 0, 0.0, {}
        limite = adesso - self.conserva_s
        for g in grezze:
            titolo_raw = ripulisci_testo(g.get("titolo"), 400)
            link = str(g.get("link") or "").strip()[:500]
            if not titolo_raw or pulizia.non_notizia(titolo_raw, link):
                if titolo_raw:
                    conta["notizie_non_notizia"] = conta.get("notizie_non_notizia", 0) + 1
                continue
            somm_raw = str(g.get("sommario") or "")
            titolo, regole = pulizia.titolo_per_voce(titolo_raw, somm_raw)
            sommario, r2 = pulizia.sommario_per_voce(somm_raw, titolo, f.testata)
            regole = regole + r2
            titolo = ripulisci_testo(titolo, TITOLO_MAX)
            sommario = ripulisci_testo(sommario, SOMMARIO_MAX)
            for x in regole:
                conta[x] = conta.get(x, 0) + 1
            d = lettore.leggi_data(g.get("data_grezza") or "", f.fuso)
            senza = d is None
            t = adesso if senza else d.timestamp()
            if t > adesso + 300:
                t = adesso                    # data nel futuro: riportata ad adesso
                conta["notizie_data_futura"] = conta.get("notizie_data_futura", 0) + 1
            if t < limite:
                continue
            ultima = max(ultima, t)
            with self._lock:
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO voci(feed, testata, tema, titolo, titolo_orig, "
                    "titolo_l, sommario, link, t, senza_data, visto, regole) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f.url, f.testata, f.tema, titolo, titolo_raw[:400],
                     re.sub(r"\W+", " ", titolo.lower()).strip(), sommario, link or None, t,
                     int(senza), adesso, ",".join(regole)))
                nuove += cur.rowcount or 0
        return nuove, ultima, conta

    def scarica_tutti(self, solo_veloci: bool = False) -> dict:
        """Uno scarico (tutti i feed, o solo quelli veloci): {"feed", "ok", "nuove",
        "errori": {testata: motivo}, "s"}. Uno alla volta."""
        with self._scarico_lock:
            self._scarico_fatto.clear()
            try:
                return self._scarica_tutti(solo_veloci)
            finally:
                self._scarico_fatto.set()

    def _scarica_tutti(self, solo_veloci: bool) -> dict:
        t0 = time.perf_counter()
        adesso = self.orologio()
        feeds = [f for f in self.feeds if f.veloce or not solo_veloci]
        risultati = []
        if feeds:
            # Prima i robots.txt, uno per sito (in parallelo fra siti diversi): così due feed
            # dello stesso sito non lo chiedono due volte
            siti = {}
            for f in feeds:
                u = urlsplit(f.url)
                siti.setdefault(f"{u.scheme}://{u.netloc}", f.url)
            with concurrent.futures.ThreadPoolExecutor(min(PARALLELI, len(feeds))) as ex:
                list(ex.map(self._permesso, siti.values()))
                risultati = list(ex.map(self._uno, feeds))
        ok, nuove, errori, conta = 0, 0, {}, {}
        for r in risultati:
            f = r["feed"]
            if "errore" in r:
                errori[f"{f.testata} ({f.tema})"] = r["errore"]
                with self._lock:
                    self.db.execute(
                        "INSERT INTO feed(url, testata, tema, ultimo_tentativo, errore) "
                        "VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET "
                        "ultimo_tentativo=excluded.ultimo_tentativo, errore=excluded.errore",
                        (f.url, f.testata, f.tema, adesso, r["errore"][:200]))
                continue
            ok += 1
            n, ultima, c = self._inserisci(f, r["voci"], adesso)
            nuove += n
            for k, v in c.items():
                conta[k] = conta.get(k, 0) + v
            with self._lock:
                self.db.execute(
                    "INSERT INTO feed(url, testata, tema, etag, modificato, ultimo_ok, "
                    "ultimo_tentativo, ultima_voce, errore, voci) VALUES(?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, "
                    "modificato=excluded.modificato, ultimo_ok=excluded.ultimo_ok, "
                    "ultimo_tentativo=excluded.ultimo_tentativo, "
                    "ultima_voce=MAX(COALESCE(feed.ultima_voce, 0), "
                    "COALESCE(excluded.ultima_voce, 0)), "
                    "errore=NULL, voci=excluded.voci",
                    (f.url, f.testata, f.tema, r.get("etag") or "", r.get("modificato") or "",
                     adesso, adesso, ultima or None, None, len(r["voci"])))
        with self._lock:
            self.db.execute("DELETE FROM voci WHERE t < ?", (adesso - self.conserva_s,))
            self.db.commit()
        self._meta("ultimo_scarico_veloci" if solo_veloci else "ultimo_scarico", f"{adesso:.0f}")
        if ok:
            self._meta("ultimo_ok", f"{adesso:.0f}")
        self._ricarica()
        esito = {"feed": len(feeds), "ok": ok, "nuove": nuove, "errori": errori,
                 "regole": conta, "s": round(time.perf_counter() - t0, 2),
                 "quando": adesso, "veloci": solo_veloci}
        self.ultimo_giro = esito
        self.log(f"[NOTIZIE] scarico{' dei feed veloci' if solo_veloci else ''}: {ok}/"
                 f"{len(feeds)} feed, {nuove} voci nuove, {esito['s']} s"
                 + (f"; non letti: {', '.join(f'{k} ({v})' for k, v in errori.items())}"
                    if errori else ""))
        return esito

    # ── in memoria ──
    def _ricarica(self):
        """Le voci dal disco in memoria, con le radici e i gruppi delle ultime ORE_GRUPPI."""
        adesso = self.orologio()
        with self._lock:
            righe = self.db.execute(
                "SELECT id, feed, testata, tema, titolo, sommario, link, t, senza_data, regole, "
                "titolo_orig FROM voci WHERE t >= ? ORDER BY t DESC",
                (adesso - self.conserva_s,)).fetchall()
        voci = []
        for r in righe:
            v = Voce(id=r[0], feed=r[1], testata=r[2], tema=r[3], titolo=r[4] or "",
                     sommario=r[5] or "", link=r[6] or "", t=float(r[7] or 0),
                     senza_data=bool(r[8]), regole=tuple(x for x in (r[9] or "").split(",") if x),
                     titolo_orig=r[10] or "")
            v.r_titolo = frozenset(radici_ricerca(v.titolo))
            v.r_tutto = v.r_titolo | frozenset(radici_ricerca(v.sommario))
            voci.append(v)
        recenti = [(v.id, v.testata, v.t,
                    v.titolo + " " + v.sommario[:gruppi.SOMMARIO_CARATTERI])
                   for v in voci if adesso - v.t <= ORE_GRUPPI * 3600 and v.tema != "allerta"]
        t0 = time.perf_counter()
        gr = gruppi.raggruppa(recenti)
        ms = (time.perf_counter() - t0) * 1000
        membri: dict[int, list[int]] = {}
        for v in voci:
            g = gr.get(v.id, v.id)
            membri.setdefault(g, []).append(v.id)
        with self._lock:
            self._voci = voci
            self._per_id = {v.id: v for v in voci}
            self._gruppo = {v.id: gr.get(v.id, v.id) for v in voci}
            self._membri = membri
        if recenti and ms > 2000:
            self.log(f"[NOTIZIE] gruppi di {len(recenti)} voci in {ms:.0f} ms")

    def _fatto(self, gid: int, punteggio: float = 0.0, temi=None) -> Fatto:
        ids = self._membri.get(gid, [gid])
        voci = [self._per_id[i] for i in ids if i in self._per_id
                and (temi is None or self._per_id[i].tema in temi)]
        voci.sort(key=lambda v: -v.t)
        return Fatto(ids=[v.id for v in voci], voci=voci, punteggio=punteggio)

    # ── richieste ──
    def prepara(self, attesa=None) -> bool:
        """Prima di rispondere: segna la richiesta e, se l'indice è vecchio o vuoto, scarica
        subito (al più PRIMA_ATTESA_S; `attesa()` dice la frase d'attesa se ci vuole). True se
        l'indice è fresco."""
        self.richiesta()
        if self.fresco():
            return True
        if self._scarico_fatto.is_set():
            self._scarico_fatto.clear()        # prima del thread: l'attesa qui sotto lo vede
            threading.Thread(target=self.scarica_tutti, name="notizie-subito",
                             daemon=True).start()
        if not self._scarico_fatto.wait(0.4) and attesa is not None:
            try:
                attesa()
            except Exception:  # noqa: BLE001 — la frase d'attesa non cambia il risultato
                pass
        self._scarico_fatto.wait(PRIMA_ATTESA_S)
        return self.fresco()

    def principali(self, temi=("generale",), ore: float = ORE_OGGI, n: int = 3,
                   gia_dette: set | None = None) -> list[Fatto]:
        """I fatti più dati delle ultime `ore` dai feed di `temi`: prima quelli con più testate,
        poi i più recenti; quelli già detti in fondo."""
        adesso = self.orologio()
        with self._lock:
            gids = {self._gruppo.get(v.id, v.id) for v in self._voci
                    if v.tema in temi and adesso - v.t <= ore * 3600}
            fatti = [self._fatto(g) for g in gids]
        fatti = [f for f in fatti if f.voci]
        fatti.sort(key=lambda f: (-len(f.testate), -f.t))
        return _con_dette(fatti, gia_dette, n)

    def cerca(self, testo: str, temi=None, n: int = 3, gia_dette: set | None = None
              ) -> tuple[list[Fatto], int]:
        """I fatti con le parole di `testo` (tutte; con tre parole o più ne basta una meno),
        dai feed di `temi` (None = tutti). (fatti, voci trovate delle ultime ORE_RIPIEGO ore)."""
        q = radici_ricerca(testo)
        if not q:
            return [], 0
        adesso = self.orologio()
        minimo = len(q) if len(q) < 3 else len(q) - 1
        punti: dict[int, float] = {}
        recenti = 0
        with self._lock:
            for v in self._voci:
                if temi is not None and v.tema not in temi:
                    continue
                presi = sum(1 for r in q if r in v.r_tutto)
                if presi < minimo:
                    continue
                if adesso - v.t <= ORE_RIPIEGO * 3600:
                    recenti += 1
                p = presi + sum(1 for r in q if r in v.r_titolo)
                ore = (adesso - v.t) / 3600
                p += 1.0 if ore <= 24 else 0.5 if ore <= ORE_RIPIEGO else 0.0
                g = self._gruppo.get(v.id, v.id)
                punti[g] = max(punti.get(g, 0.0), p)
            fatti = [self._fatto(g, p, temi) for g, p in punti.items()]
        fatti = [f for f in fatti if f.voci]
        fatti.sort(key=lambda f: (-f.punteggio, -len(f.testate), -f.t))
        return _con_dette(fatti, gia_dette, n), recenti

    def dettaglio(self, ids) -> Fatto | None:
        """Il fatto di una voce già detta, con le voci di tutte le testate (oggi): il gruppo
        attuale della prima voce che c'è ancora."""
        with self._lock:
            for i in ids or ():
                if i in self._per_id:
                    return self._fatto(self._gruppo.get(i, i))
        return None

    # ── per conversazione: l'ultimo elenco detto e i fatti già detti ──
    def ricorda_elenco(self, chiave: str, fatti: list[Fatto]):
        adesso = self.orologio()
        with self._lock:
            self._elenchi[chiave] = (adesso, [list(f.ids) for f in fatti])
            t, dette = self._dette.get(chiave, (adesso, set()))
            if adesso - t > DETTE_S:
                dette = set()
            dette |= {i for f in fatti for i in f.ids}
            self._dette[chiave] = (adesso, dette)

    def elenco(self, chiave: str) -> list | None:
        with self._lock:
            e = self._elenchi.get(chiave)
        if e is None or self.orologio() - e[0] > DETTE_S:
            return None
        return e[1]

    def dette(self, chiave: str) -> set:
        with self._lock:
            d = self._dette.get(chiave)
        if d is None or self.orologio() - d[0] > DETTE_S:
            return set()
        return set(d[1])

    # ── stato (registro delle capacità, cruscotto) ──
    def stato(self) -> dict:
        adesso = self.orologio()
        with self._lock:
            righe = self.db.execute("SELECT url, testata, tema, ultimo_ok, ultima_voce, errore "
                                    "FROM feed").fetchall()
            n = len(self._voci)
        attuali = {f.url for f in self.feeds}
        fermi, guasti = [], []
        for url, testata, tema, ok, ultima, err in righe:
            if url not in attuali:
                continue
            nome = f"{testata} ({tema})"
            if err:
                guasti.append(nome)
            elif ultima and adesso - float(ultima) > FERMO_GIORNI.get(tema, 3) * 86400:
                fermi.append(nome)
        return {"voci": n, "feed": len(self.feeds), "ultimo_ok": self.ultimo_ok,
                "ultimo_scarico": self.ultimo_scarico, "ultima_richiesta": self.ultima_richiesta,
                "attivo": self.attivo(), "fermi": fermi, "guasti": guasti}

    # ── il thread ──
    def forse_scarica(self) -> dict | None:
        """Uno scarico se è ora (e qualcuno ha chiesto notizie di recente), altrimenti None."""
        if not self.attivo():
            return None
        adesso = self.orologio()
        if adesso - self.ultimo_scarico >= self.intervallo_s:
            return self.scarica_tutti()
        oggi = adesso - self.ultima_richiesta <= 86400
        if (oggi and any(f.veloce for f in self.feeds)
                and adesso - max(self.ultimo_scarico, self._meta_t("ultimo_scarico_veloci"))
                >= self.intervallo_s / 2):
            return self.scarica_tutti(solo_veloci=True)
        return None

    def avvia(self):
        if self._thread is not None:
            return

        def giro():
            while not self._ferma.wait(GIRO_S):
                try:
                    self.forse_scarica()
                except Exception as e:  # noqa: BLE001 — il thread non muore
                    self.log(f"[NOTIZIE] scarico non riuscito: {type(e).__name__}: {e}")
        self._thread = threading.Thread(target=giro, name="notizie", daemon=True)
        self._thread.start()

    def ferma(self):
        self._ferma.set()

    def close(self):
        self.ferma()
        try:
            with self._lock:
                self.db.close()
        except Exception:  # noqa: BLE001
            pass


def _con_dette(fatti: list[Fatto], gia_dette: set | None, n: int) -> list[Fatto]:
    """I primi `n` fatti, quelli già detti in fondo (servono solo se mancano i nuovi)."""
    if not gia_dette:
        return fatti[:n]
    nuovi = [f for f in fatti if not (set(f.ids) & gia_dette)]
    vecchi = [f for f in fatti if set(f.ids) & gia_dette]
    return (nuovi + vecchi)[:n]


def per_minore(temi) -> tuple:
    """I temi di una richiesta, ristretti a quelli dei minori."""
    return tuple(t for t in (temi or TEMI_MINORI) if t in TEMI_MINORI)
