"""
La stessa notizia data da più testate, raggruppata senza modello (13/10/2026, ricerca del
13/10 § 3.2): coseno TF-IDF sulle radici del titolo e dell'inizio del sommario.

- si collegano solo voci di **testate diverse**, a meno di 24 ore l'una dall'altra, con il
  coseno almeno SOGLIA (0,30: 19–20 gruppi giusti su 20 nella misura; sotto 0,25 si incatenano
  fatti diversi);
- **tetto contro le catene**: due gruppi si uniscono solo se almeno metà delle coppie fra le
  loro voci sono simili almeno SOGLIA_LEGAME. Una voce che somiglia a una sola voce di un
  gruppo di tre non lo tira dentro un altro fatto;
- le coppie si cercano con un indice delle radici (solo le voci che ne hanno una in comune) e
  si uniscono dalla più simile.

Il modello serve per **dire** il gruppo in una frase, non per formarlo. Solo libreria standard.
"""
from __future__ import annotations

import collections
import math
import re
import unicodedata

SOGLIA = 0.30
SOGLIA_LEGAME = 0.20
FINESTRA_S = 24 * 3600
SOMMARIO_CARATTERI = 200
GRUPPO_MAX = 40

STOP = frozenset("""il lo la i gli le un uno una di a da in con su per tra fra e o ma che chi
non piu più del dello della dei degli delle al allo alla ai agli alle dal dallo dalla dai
dagli dalle nel nello nella nei negli nelle sul sullo sulla sui sugli sulle col è ha hanno
sono era stato stata essere fa dopo prima ecco come anche ancora già oggi ieri domani sua suo
suoi sue loro questo questa quello quella cosa dove quando perché se ci si ne mi ti vi lui lei
noi voi tutto tutti tutte molto ora live video foto diretta news ultime ultima dice detto
contro verso sempre mai solo poi tre due anni anno the and of dell nell sull dall all
coll quell""".split())


def norm(s: str) -> list[str]:
    t = unicodedata.normalize("NFKD", str(s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)


def radici(testo: str) -> list[str]:
    """Le radici (prime 6 lettere) delle parole significative."""
    return [w[:6] for w in norm(testo) if w not in STOP and len(w) > 2]


def _vettori(testi: list[str]) -> list[dict[str, float]]:
    docs = [collections.Counter(radici(t)) for t in testi]
    df = collections.Counter(r for d in docs for r in d)
    n = len(docs)
    out = []
    for d in docs:
        # idf smussato (n + 1): con poche voci una radice comune a tutte conta ancora un po'
        v = {r: (1 + math.log(c)) * math.log((n + 1) / df[r]) for r, c in d.items()}
        norma = math.sqrt(sum(a * a for a in v.values())) or 1.0
        out.append({r: a / norma for r, a in v.items() if a > 0})
    return out


def _coseno(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(r, 0.0) for r, w in a.items())


def raggruppa(voci: list[tuple]) -> dict:
    """voci: [(id, testata, istante in secondi, testo)] (testo = titolo + inizio del
    sommario). → {id: id del gruppo} (il gruppo è l'id della sua prima voce in elenco)."""
    n = len(voci)
    if not n:
        return {}
    vett = _vettori([str(v[3] or "") for v in voci])
    indice = collections.defaultdict(list)
    for i, v in enumerate(vett):
        for r in v:
            indice[r].append(i)
    # Le coppie candidate: almeno una radice in comune, testate diverse, entro la finestra
    simili = {}
    for i, v in enumerate(vett):
        visti = set()
        for r in v:
            for j in indice[r]:
                if j <= i or j in visti:
                    continue
                visti.add(j)
                if voci[i][1] == voci[j][1]:
                    continue
                if abs(float(voci[i][2] or 0) - float(voci[j][2] or 0)) > FINESTRA_S:
                    continue
                s = _coseno(v, vett[j])
                if s >= SOGLIA_LEGAME:
                    simili[(i, j)] = s
    padre = list(range(n))
    membri = {i: [i] for i in range(n)}

    def radice(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def sim(a, b):
        return simili.get((a, b) if a < b else (b, a), 0.0)

    for (i, j), s in sorted(simili.items(), key=lambda x: -x[1]):
        if s < SOGLIA:
            break
        ri, rj = radice(i), radice(j)
        if ri == rj:
            continue
        a, b = membri[ri], membri[rj]
        if len(a) + len(b) > GRUPPO_MAX:
            continue
        coppie = [(x, y) for x in a for y in b]
        legate = sum(1 for x, y in coppie if sim(x, y) >= SOGLIA_LEGAME)
        if legate * 2 < len(coppie):
            continue                     # catena: il nuovo pezzo somiglia a troppo poco
        padre[rj] = ri
        membri[ri] = a + b
        del membri[rj]
    out = {}
    for i in range(n):
        r = radice(i)
        out[voci[i][0]] = voci[min(membri[r])][0]
    return out
