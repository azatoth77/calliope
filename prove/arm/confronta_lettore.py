"""Lettore ZIM in puro Python (calliope/zim.py) contro libzim: correttezza e tempi.

    python prove\\arm\\confronta_lettore.py corretto              # serve libzim (solo x64)
    python prove\\arm\\confronta_lettore.py tempi zim [<file>]    # anche senza libzim (ARM)
    python prove\\arm\\confronta_lettore.py tempi libzim [<file>]

`corretto`: 150 voci a caso del namespace C per file; titolo, redirect e destinazione, tipo
MIME, SHA-1 del contenuto, ricerca per titolo, percorsi inesistenti, metadati.
`tempi`: un file per volta (tutti e quattro se non se ne indica uno); apertura, ricerca per
percorso e per titolo, lettura di una voce, memoria privata del processo. Da rifare sullo
Spark (docs/ricerche/2026-10-01-biblioteca-senza-libzim.md, §2). I file sono quelli di
calliope.yaml (cartella biblioteca/).
"""
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
os.chdir(RADICE)
# Come le altre prove: niente calliope.locale.yaml (valori di questa installazione)
os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(RADICE / "prove" / "nessun-file-locale.yaml"))

from calliope import zim  # noqa: E402
from calliope.config import load_config  # noqa: E402
from calliope.installa.catalogo import risolvi_zim  # noqa: E402


def files() -> list[str]:
    cfg = load_config()
    out = []
    for attr in ("biblioteca_mini", "biblioteca_completa", "biblioteca_ragazzi",
                 "biblioteca_dizionario"):
        p = risolvi_zim(getattr(cfg, attr, None))
        if p and Path(p).is_file():
            out.append(p)
    return out


def sample_paths(z: zim.ZimFile, n: int, seed: int) -> list[str]:
    """Percorsi a caso del namespace C (voci, redirect, risorse)."""
    rnd = random.Random(seed)
    out: list[str] = []
    while len(out) < n:
        d = z.dirent(rnd.randrange(z.entry_count))
        if d.namespace == "C" and d.path not in out:
            out.append(d.path)
    return out


def corretto(n_per_file=150) -> int:
    from libzim.reader import Archive
    tot = bad = 0
    for f in files():
        z = zim.ZimFile(f)
        a = Archive(f)
        paths = sample_paths(z, n_per_file, seed=len(Path(f).name))
        ok = redirects = 0
        diffs = []
        for p in paths:
            e1, e2 = a.get_entry_by_path(p), z.get_entry_by_path(p)
            same = e1.title == e2.title and e1.is_redirect == e2.is_redirect
            if e1.is_redirect:
                redirects += 1
                same = same and e1.get_redirect_entry().path == e2.get_redirect_entry().path
            i1, i2 = e1.get_item(), e2.get_item()
            same = same and i1.mimetype == i2.mimetype
            same = same and hashlib.sha1(bytes(i1.content)).digest() == \
                hashlib.sha1(i2.content).digest()
            t = e1.title
            if a.has_entry_by_title(t):
                # titoli doppi: le due librerie possono scegliere voci diverse con lo stesso
                # titolo, e allora basta che il titolo sia quello
                same = same and (a.get_entry_by_title(t).path == z.get_entry_by_title(t).path
                                 or z.get_entry_by_title(t).title == t)
            ok += same
            if not same:
                diffs.append(p)
        for p in ("Questa_voce_non_esiste_xyz", "Monte_Bianco_", "monte_Bianco"):
            if a.has_entry_by_path(p) != z.has_entry_by_path(p):
                diffs.append("inesistente:" + p)
        meta_diff = []
        for k in ("Language", "Title", "Date", "Flavour"):
            try:
                if bytes(a.get_metadata(k)) != z.get_metadata(k):
                    meta_diff.append(k)
            except KeyError:
                pass
        print(Path(f).name, dict(campione=len(paths), uguali=ok, redirect=redirects,
                                 diversi=diffs[:10], metadati_diversi=meta_diff), flush=True)
        tot += len(paths)
        bad += len(paths) - ok + len(meta_diff)
        z.close()
    print(json.dumps({"totale": tot, "diversi": bad}))
    return 1 if bad else 0


def tempi(impl: str, f: str, n=300):
    import psutil
    proc = psutil.Process()
    z0 = zim.ZimFile(f)
    paths = sample_paths(z0, n, seed=7)
    titles = [z0.get_entry_by_path(p).title for p in paths]
    z0.close()
    rss_base = proc.memory_info().rss
    t = time.perf_counter()
    if impl == "libzim":
        from libzim.reader import Archive
        arc = Archive(f)
    else:
        arc = zim.ZimFile(f)
    open_ms = (time.perf_counter() - t) * 1000
    t_title, t_read, t_path = [], [], []
    for p, ti in zip(paths, titles):
        t = time.perf_counter()
        arc.has_entry_by_path(p)
        t_path.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        try:
            arc.get_entry_by_title(ti)
        except KeyError:
            pass
        t_title.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        bytes(arc.get_entry_by_path(p).get_item().content)
        t_read.append((time.perf_counter() - t) * 1000)

    def q(xs, p):
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(p * len(xs)))], 3)

    mem = proc.memory_info()
    print(json.dumps(dict(impl=impl, file=Path(f).name, apertura_ms=round(open_ms, 2),
                          percorso_med=q(t_path, .5), percorso_p95=q(t_path, .95),
                          titolo_med=q(t_title, .5), titolo_p95=q(t_title, .95),
                          lettura_med=q(t_read, .5), lettura_p95=q(t_read, .95),
                          rss_mb=round((mem.rss - rss_base) / 2**20, 1),
                          privata_mb=round(getattr(mem, "private", 0) / 2**20, 1))))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) < 2 or sys.argv[1] not in ("corretto", "tempi"):
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "corretto":
        sys.exit(corretto())
    impl = sys.argv[2] if len(sys.argv) > 2 else "zim"
    if len(sys.argv) > 3:
        tempi(impl, sys.argv[3])
    else:                       # un processo per file: memoria e cache pulite
        for f in files():
            subprocess.run([sys.executable, __file__, "tempi", impl, f])
