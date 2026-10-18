"""Tempi delle sole primitive di ricerca della biblioteca: full-text e suggerimenti sui titoli.

    python prove\\arm\\bench_query.py            # indice SQLite FTS5 (calliope/biblioteca_indice.py)
    python prove\\arm\\bench_query.py libzim     # Xapian dentro gli ZIM, se libzim c'è (solo x64)
    <python della versione> prove/arm/bench_query.py --dati ~/calliope   # DGX (18/10, #64)

Domande: i tre banchi di prove/prova_biblioteca.py (107), due giri, si misura il secondo
(cache calda). Stampa mediana, p95 e massimo in ms, e la memoria del processo (privata: psutil
su Windows, RssAnon di /proc su Linux; picco). Configurazione con `load_config`: senza `--dati`
quella della cartella del codice senza il file locale, con `--dati <cartella>` quella della
cartella dei dati, locale compreso. Da
rifare sullo Spark [storico: misurato sulla DGX il 18/10, docs/aree/biblioteca.md]. Sull'Alienware (01/10, Wikipedia ridotta): full-text FTS5 3,9 / 36 / 57 ms
contro Xapian 1,1 / 6,7 / 12 ms; suggerimenti FTS5 3,1 / 18 / 46 ms contro 10,9 / 40 / 64 ms
(docs/ricerche/2026-10-01-biblioteca-senza-libzim.md, §3).
"""
import json
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
from prove.arm.comune import memoria, prepara  # noqa: E402

ARGV = prepara(sys.argv)

from calliope.biblioteca import _DATA_HINTS, Biblioteca, keywords  # noqa: E402
from calliope.config import load_config  # noqa: E402
from prove.prova_biblioteca import BANCO, BANCO_DIFFICILE, BANCO_NUOVO  # noqa: E402


class _Xapian:
    """Le stesse due primitive con libzim (per il confronto su x64)."""

    def __init__(self, path):
        from libzim.reader import Archive
        from libzim.search import Searcher
        from libzim.suggestion import SuggestionSearcher
        self.archive = Archive(path)
        self.searcher = Searcher(self.archive)
        self.suggester = SuggestionSearcher(self.archive)

    def fulltext(self, words, n):
        from libzim.search import Query
        attempt = list(words)
        while attempt:
            found = list(self.searcher.search(Query().set_query(" ".join(attempt)))
                         .getResults(0, n))
            if found:
                return found
            attempt.remove(min(attempt, key=len))
        return []

    def titles(self, words, n):
        out = []
        for size in (len(words), 3, 2, 1):
            if size < 1 or size > len(words):
                continue
            for i in range(len(words) - size + 1):
                for p in self.suggester.suggest(" ".join(words[i:i + size])).getResults(0, 3):
                    if p not in out:
                        out.append(p)
                if len(out) >= n:
                    return out
        return out


def main():
    impl = ARGV[1] if len(ARGV) > 1 else "fts5"
    cfg = load_config()
    bib = Biblioteca(cfg)
    if not bib.archivi:
        print("Biblioteca assente: niente da misurare (dati altrove: --dati <cartella>).")
        return 1
    arch = bib.archivi[0]
    if impl == "libzim":
        arch = _Xapian(arch.path)
    elif arch.indice is None:
        print("Manca l'indice di Wikipedia ridotta: python -m calliope.biblioteca_indice")
        return 1
    qs = [c[0] for c in BANCO + BANCO_DIFFICILE + BANCO_NUOVO]
    tf, tt = [], []
    for q in qs * 2:
        words = keywords(q)
        entity = [w for w in words if w not in _DATA_HINTS]
        t = time.perf_counter()
        arch.fulltext(words, 6)
        tf.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        arch.titles(entity or words, 6)
        tt.append((time.perf_counter() - t) * 1000)
    tf, tt = tf[len(qs):], tt[len(qs):]

    def p(xs, f):
        return round(sorted(xs)[int(f * (len(xs) - 1))], 1)

    res = dict(impl=impl, domande=len(qs), fulltext_med=p(tf, .5), fulltext_p95=p(tf, .95),
               fulltext_max=round(max(tf), 1), titoli_med=p(tt, .5), titoli_p95=p(tt, .95),
               titoli_max=round(max(tt), 1))
    mem = memoria()
    res["privata_mb"], res["picco_mb"] = mem["privata_mb"], mem["picco_mb"]
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
