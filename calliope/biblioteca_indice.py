"""
Indice di ricerca della biblioteca in SQLite FTS5, al posto di Xapian (01/10/2026).

Gli indici Xapian dentro i file ZIM si leggono solo con libzim, che non ha wheel per Windows
su ARM. Questo modulo costruisce da un file ZIM (letto con calliope/zim.py) un indice SQLite
FTS5 accanto, e lo interroga. FTS5 c'è nel `sqlite3` di python.org anche su ARM64. Ricerca e
misure: docs/ricerche/2026-10-01-biblioteca-senza-libzim.md.

    python -m calliope.biblioteca_indice              # gli indici che mancano (configurazione)
    python -m calliope.biblioteca_indice <file.zim>   # un file preciso
        [--processi N] [--forza] [--stato]
        [--avanzamento] [--stdin]    # per l'installatore: righe AVANZAMENTO/FATTO, e stop
                                     # pulito quando si chiude lo stdin

Dove: `biblioteca/indici/<nome dello ZIM senza .zim>.fts.sqlite`, nella cartella dei file ZIM.
Serve solo ai file in cui si cerca per parole (Wikipedia ridotta e Vikidia): la Wikipedia
completa si legge per titolo e il Wikizionario per percorso esatto. Indicizzare la completa
non cambiava nessuna risposta, e costava 4,8 GiB e 11 minuti.

Schema (un file SQLite per file ZIM; rowid = indice del dirent nel file ZIM, il percorso si
rilegge dallo ZIM e non si salva):
  testi(titolo, testo)  una riga per voce HTML: titolo più i titoli dei redirect (alias),
                        testo del <body> senza tag, script, stili e note; parole ridotte a
                        radice con biblioteca._stem, la stessa del punteggio
  titoli(t)             una riga per voce «front» (anche i redirect): parole del titolo senza
                        radice, con l'indice dei prefissi (suggerimenti)
  meta                  uuid e dimensione dello ZIM, versione dell'estrattore, firma delle
                        radici, conteggi; `completo=1` scritto per ultimo
`detail=full` è obbligatorio: con `content=''` e `detail=column` bm25 vale sempre 0 e i
risultati escono in ordine alfabetico.

Un indice si usa solo se è completo, della stessa versione e dello stesso file ZIM (uuid e
dimensione). La costruzione scrive `<indice>.tmp` e lo rinomina alla fine, così un indice a
metà non si usa mai e la biblioteca vecchia resta in uso mentre si costruisce. RAM: i
risultati dei processi si consumano a lotti (picco del processo principale ~2 GB sul mini).
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

from .biblioteca import _norm, _stem
from .zim import ZimError, ZimFile, read_uuid

# Da alzare quando cambia l'estrazione del testo o lo schema: l'indice va ricostruito.
# Un cambiamento di `_stem` si vede da solo (firma delle radici).
VERSIONE = 1
CARTELLA = "indici"
SUFFISSO = ".fts.sqlite"
_PROVA_RADICI = ("vulcani", "vulcano", "laghi", "parchi", "caduta", "città", "1989",
                 "Monte", "giulio", "perché", "è", "dell'acqua")

_RE_DROP = re.compile(r"<(script|style|sup)\b[^>]*>.*?</\1>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WORD = re.compile(r"[^\W_]+")


class IndiceAnnullato(Exception):
    pass


def firma_radici() -> str:
    """Impronta del comportamento di `_stem`: se cambia, gli indici vecchi non valgono più."""
    probe = " ".join(_stem(w.lower()) for w in _PROVA_RADICI)
    return hashlib.sha1(probe.encode("utf-8")).hexdigest()[:12]


def percorso_indice(zim_path: str | os.PathLike) -> Path:
    p = Path(zim_path)
    return p.parent / CARTELLA / (p.stem + SUFFISSO)


def _uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro"


def _leggi_meta(db_path: Path) -> dict:
    con = sqlite3.connect(_uri(db_path), uri=True)
    try:
        return dict(con.execute("SELECT chiave, valore FROM meta").fetchall())
    finally:
        con.close()


def stato_indice(zim_path: str | os.PathLike) -> tuple[str, str]:
    """(codice, spiegazione) dell'indice di un file ZIM, in <1 ms:
    ok | mancante | incompleto | versione | diverso | illeggibile."""
    idx = percorso_indice(zim_path)
    if not idx.is_file():
        return "mancante", "l'indice non c'è"
    try:
        meta = _leggi_meta(idx)
    except sqlite3.Error as e:
        return "illeggibile", f"l'indice non si legge ({e})"
    if meta.get("completo") != "1":
        return "incompleto", "l'indice è a metà"
    if meta.get("versione") != str(VERSIONE) or meta.get("firma_radici") != firma_radici():
        return "versione", "l'indice è di una versione vecchia"
    try:
        uuid = read_uuid(zim_path).hex()
        size = os.path.getsize(zim_path)
    except (OSError, ZimError) as e:
        return "illeggibile", f"il file ZIM non si legge ({e})"
    if meta.get("zim_uuid") != uuid or meta.get("zim_dimensione") != str(size):
        return "diverso", "l'indice è di un altro file ZIM"
    return "ok", ""


def pronto(zim_path: str | os.PathLike | None) -> bool:
    return bool(zim_path) and stato_indice(zim_path)[0] == "ok"


# ─────────────────────────────── interrogazione ───────────────────────────────

def _match(tokens: list[str], prefix_last: bool = False) -> str:
    """Espressione MATCH in AND, ogni parola tra virgolette (niente operatori di FTS5)."""
    out = ['"%s"' % t.replace('"', "") for t in tokens if t]
    if prefix_last and out and len(tokens[-1]) >= 3:
        out[-1] += "*"
    return " ".join(out)


class Indice:
    """Un indice aperto in sola lettura. Thread-safe (una connessione, un lock)."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self._db = sqlite3.connect(_uri(self.path), uri=True, check_same_thread=False)
        self._db.execute("PRAGMA mmap_size=1073741824")
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            self._db.close()

    def fulltext(self, words: list[str], n: int, peso_titolo: float = 1.0) -> list[int]:
        """Rowid (indici dei dirent) delle voci con TUTTE le parole, per bm25. Se non trova
        nulla toglie la parola più corta e riprova, come si faceva con Xapian."""
        attempt = list(dict.fromkeys(w for w in words if w))
        with self._lock:
            while attempt:
                stems = list(dict.fromkeys(_stem(w) for w in attempt))
                rows = self._db.execute(
                    "SELECT rowid FROM testi WHERE testi MATCH ? "
                    "ORDER BY bm25(testi, ?, 1.0) LIMIT ?",
                    (_match(stems), float(peso_titolo), int(n))).fetchall()
                if rows:
                    return [r[0] for r in rows]
                attempt.remove(min(attempt, key=len))
        return []

    def titoli(self, testo: str, n: int = 30) -> list[tuple[int, float]]:
        """(rowid, bm25) dei titoli con tutte le parole di `testo`, l'ultima come prefisso."""
        toks = _RE_WORD.findall(_norm(testo))
        if not toks:
            return []
        with self._lock:
            return self._db.execute(
                "SELECT rowid, bm25(titoli) FROM titoli WHERE titoli MATCH ? "
                "ORDER BY rank LIMIT ?", (_match(toks, prefix_last=True), int(n))).fetchall()


def apri(zim_path: str | os.PathLike | None) -> Indice | None:
    """L'indice di un file ZIM se è valido (completo, stessa versione, stesso file)."""
    if not zim_path or stato_indice(zim_path)[0] != "ok":
        return None
    try:
        return Indice(percorso_indice(zim_path))
    except sqlite3.Error:
        return None


def parole_titolo(title: str) -> str:
    return " ".join(_RE_WORD.findall(_norm(title)))


# ─────────────────────────────── costruzione ───────────────────────────────

def text_of(raw: bytes) -> str:
    """Testo di una voce per l'indice: espressioni regolari invece di HTMLParser (~10× più
    veloce). All'indice basta trovare le voci; i paragrafi li legge poi biblioteca.extract."""
    s = raw.decode("utf-8", "replace")
    b = s.find("<body")
    if b >= 0:
        s = s[b:]
    s = _RE_DROP.sub(" ", s)
    s = _RE_TAG.sub(" ", s)
    return html.unescape(s)


_STEMS: dict[str, str] = {}


def stems_of(text: str) -> str:
    cache = _STEMS
    out = []
    for w in _RE_WORD.findall(text.lower()):
        s = cache.get(w)
        if s is None:
            s = _stem(w)
            if len(cache) < 300_000:
                cache[w] = s
        out.append(s)
    return " ".join(out)


_ZIM: ZimFile | None = None


def _init_worker(path: str):
    global _ZIM
    _ZIM = ZimFile(path, cluster_cache=0, dirent_cache=0)


def _work(job) -> list[tuple[int, str, str, int]]:
    """job = (cluster, [(blob, indice, titolo, alias)]) → righe per `testi`."""
    c, items = job
    try:
        cl = _ZIM.cluster(c)
    except ZimError:
        return []
    rows = []
    for blob, idx, title, aliases in items:        # blob in ordine: decompressione a pezzi
        try:
            t = text_of(cl.blob(blob))
        except ZimError:
            continue
        rows.append((idx, stems_of(" ".join([title, *aliases])), stems_of(t), len(t)))
    return rows


def _scan(z: ZimFile, db: sqlite3.Connection, cancel=None) -> tuple[list, int, int]:
    """Voci da indicizzare, raggruppate per cluster; intanto riempie `titoli`.
    Solo le voci «front» (articoli e loro redirect): immagini, stili e script no."""
    html_mimes = {i for i, m in enumerate(z.mimetypes) if m.startswith("text/html")}
    front = z.front_indices
    if not len(front):              # file senza elenco per titolo: tutte le voci HTML
        front = [d.index for d in z.iter_dirents()
                 if d.namespace == "C" and (d.is_redirect or d.mime in html_mimes)]
    by_cluster: dict[int, list] = {}
    aliases: dict[int, list[str]] = {}
    n_titles = n_red = 0
    batch = []
    for i in front:
        d = z._read_dirent(i)
        if d.namespace != "C":
            continue
        title = d.shown_title
        batch.append((i, parole_titolo(title)))
        n_titles += 1
        if d.is_redirect:
            n_red += 1
            al = aliases.setdefault(d.redirect, [])
            if len(al) < 20:
                al.append(title)
        elif d.mime in html_mimes:
            by_cluster.setdefault(d.cluster, []).append((d.blob, i, title))
        if len(batch) >= 50_000:
            db.executemany("INSERT INTO titoli(rowid, t) VALUES (?, ?)", batch)
            batch.clear()
            if cancel is not None and cancel.is_set():
                raise IndiceAnnullato()
    if batch:
        db.executemany("INSERT INTO titoli(rowid, t) VALUES (?, ?)", batch)
    jobs = []
    for c in sorted(by_cluster):
        items = sorted(by_cluster.pop(c))
        jobs.append((c, [(b, i, t, aliases.get(i, ())) for b, i, t in items]))
    return jobs, n_titles, n_red


def costruisci(zim_path: str | os.PathLike, processi: int = 4, avanz=None,
               cancel: threading.Event | None = None, log=None) -> dict:
    """Costruisce l'indice di un file ZIM e restituisce le statistiche. `avanz(fatte,
    totale)` riceve le voci indicizzate; `cancel` ferma tutto (IndiceAnnullato) e cancella
    il file temporaneo. Solleva ZimError, sqlite3.Error o OSError se non riesce.

    Con `processi` > 1 i processi figli partono con «spawn» e rieseguono il modulo
    principale: chiamarla così solo da un main protetto da `if __name__ == "__main__"`.
    L'installatore e Calliope passano dalla riga di comando di questo modulo."""
    t0 = time.perf_counter()
    zim_path = str(zim_path)
    final = percorso_indice(zim_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")
    tmp.unlink(missing_ok=True)
    z = ZimFile(zim_path, cluster_cache=0, dirent_cache=0)
    db = None
    pool = None
    try:
        db = sqlite3.connect(tmp)
        db.executescript("""
            PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-131072;
            CREATE TABLE meta(chiave TEXT PRIMARY KEY, valore TEXT);
            CREATE VIRTUAL TABLE testi USING fts5(titolo, testo, content='', detail=full,
                columnsize=1, tokenize='unicode61 remove_diacritics 2');
            CREATE VIRTUAL TABLE titoli USING fts5(t, content='', prefix='2 3 4',
                tokenize='unicode61 remove_diacritics 2');
        """)
        db.execute("BEGIN")
        jobs, n_titles, n_red = _scan(z, db, cancel)
        total = sum(len(j[1]) for j in jobs)
        t_scan = time.perf_counter() - t0
        if log:
            log(f"{Path(zim_path).name}: {n_titles} titoli ({n_red} redirect), {total} voci "
                f"da indicizzare in {len(jobs)} cluster (scansione {t_scan:.0f} s)")
        if avanz:
            avanz(0, total)
        processi = max(1, int(processi or 1))
        if processi > 1 and len(jobs) > 1:
            import multiprocessing as mp
            pool = mp.get_context("spawn").Pool(processi, initializer=_init_worker,
                                                initargs=(zim_path,))

            def results():
                step = processi * 4          # a lotti: niente risultati accumulati in RAM
                for k in range(0, len(jobs), step):
                    yield from pool.imap_unordered(_work, jobs[k:k + step])
        else:
            _init_worker(zim_path)

            def results():
                for job in jobs:
                    yield _work(job)
        n = chars = 0
        last = 0.0
        for rows in results():
            if cancel is not None and cancel.is_set():
                raise IndiceAnnullato()
            db.executemany("INSERT INTO testi(rowid, titolo, testo) VALUES (?, ?, ?)",
                           ((r[0], r[1], r[2]) for r in rows))
            n += len(rows)
            chars += sum(r[3] for r in rows)
            now = time.perf_counter()
            if avanz and now - last >= 0.5:
                last = now
                avanz(n, total)
        if pool is not None:
            pool.close()
            pool.join()
            pool = None
        jobs.clear()
        meta = dict(versione=VERSIONE, firma_radici=firma_radici(), zim=Path(zim_path).name,
                    zim_uuid=z.uuid.hex(), zim_dimensione=os.path.getsize(zim_path), voci=n,
                    titoli=n_titles, redirect=n_red, caratteri=chars,
                    creato=time.strftime("%Y-%m-%dT%H:%M:%S"))
        db.executemany("INSERT INTO meta VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
        db.commit()
        t_text = time.perf_counter() - t0 - t_scan
        if cancel is not None and cancel.is_set():
            raise IndiceAnnullato()
        db.execute("INSERT INTO testi(testi) VALUES ('optimize')")
        db.execute("INSERT INTO titoli(titoli) VALUES ('optimize')")
        db.commit()
        db.execute("VACUUM")
        db.execute("INSERT INTO meta VALUES ('completo', '1')")     # per ultimo
        db.commit()
        db.close()
        db = None
        z.close()
        if avanz:
            avanz(total, total)
        os.replace(tmp, final)
        stats = dict(meta, indice=str(final), byte=final.stat().st_size,
                     secondi=round(time.perf_counter() - t0, 1), scansione_s=round(t_scan, 1),
                     testi_s=round(t_text, 1), processi=processi)
        if log:
            log(f"{final.name}: {n} voci, {chars / 1e6:.0f} M caratteri, "
                f"{stats['byte'] / 2**20:.0f} MiB in {stats['secondi']:.0f} s")
        return stats
    except BaseException:
        if pool is not None:
            pool.terminate()
            pool.join()
        if db is not None:
            db.close()
        z.close()
        tmp.unlink(missing_ok=True)
        raise
    finally:
        global _ZIM
        if _ZIM is not None:
            _ZIM.close()
            _ZIM = None


# ─────────────────────────────── da terminale ───────────────────────────────

def da_indicizzare(cfg) -> list[str]:
    """I file ZIM in uso che hanno bisogno di un indice (Wikipedia ridotta, Vikidia e le
    fonti in più usate nella ricerca), anche se l'indice c'è già."""
    from .installa.catalogo import file_indicizzati
    return [str(p) for p in file_indicizzati(cfg)]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if {"-h", "--help", "/?"} & set(argv):
        print(__doc__.strip())
        return 0
    procs = None
    if "--processi" in argv:
        i = argv.index("--processi")
        procs = int(argv[i + 1])
        del argv[i:i + 2]
    forza = "--forza" in argv
    solo_stato = "--stato" in argv
    macchina = "--avanzamento" in argv          # righe per l'installatore (servizio.py)
    files = [a for a in argv if not a.startswith("--")]
    cfg = None
    if not files or procs is None:
        from .stato import _config
        cfg = _config(quiet=macchina)       # anche senza PyYAML; con --avanzamento su stderr
    if procs is None:
        procs = int(getattr(cfg, "biblioteca_indice_processi", 4) or 4)
    if not files:
        files = da_indicizzare(cfg)
        if not files:
            print("Nessun file della biblioteca ha bisogno di un indice (mancano i file ZIM?).")
            return 0
    cancel = threading.Event()
    if "--stdin" in argv:
        # Lanciato dall'installatore: quando chiude lo stdin (annullo, o Calliope che si
        # chiude) ci si ferma e si cancella il file a metà
        def watch():
            try:
                while sys.stdin.readline():
                    pass
            except (OSError, ValueError):
                pass
            cancel.set()
        threading.Thread(target=watch, daemon=True).start()
    rc = 0
    for f in files:
        code, why = stato_indice(f)
        if solo_stato:
            print(f"{Path(f).name}: {code}" + (f" ({why})" if why else ""))
            continue
        if code == "ok" and not forza:
            print(f"{Path(f).name}: indice già pronto ({percorso_indice(f)})")
            continue

        def avanz(n, tot, f=f, last=[-1]):
            if macchina:
                print(f"AVANZAMENTO {n} {tot}", flush=True)
            elif tot:
                pct = int(n * 100 / tot)
                if pct // 10 != last[0]:
                    last[0] = pct // 10
                    print(f"  {Path(f).name}: {pct}%", flush=True)
        try:
            stats = costruisci(f, procs, avanz, cancel, log=None if macchina else print)
        except (KeyboardInterrupt, IndiceAnnullato):
            print("Interrotto: l'indice a metà è stato cancellato.", flush=True)
            return 130
        except (ZimError, sqlite3.Error, OSError) as e:
            print(f"ERRORE {Path(f).name}: {e}", flush=True)
            rc = 1
            continue
        if macchina:
            print("FATTO " + json.dumps(stats, ensure_ascii=False), flush=True)
    return rc


if __name__ == "__main__":
    # Anche così le funzioni dei processi figli stanno in calliope.biblioteca_indice
    # (non in __main__): con «spawn» i figli importano solo questo modulo, non Calliope
    from calliope.biblioteca_indice import main as _main
    sys.exit(_main())
