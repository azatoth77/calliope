"""
La quota delle notizie in `calliope stato --turni` (16/10/2026, issue #31): dal registro dei
turni, per giorno e in totale, quante richieste di notizie hanno avuto i fatti dei giornali
scaricati in casa e quante sono finite su internet (decisione 0024: niente internet se non
serve), quante sono rimaste vuote e perché, e i rifiuti ai minori.

Legge solo il campo `regole` (scritte da calliope/tools/notizie.py e tools/web.py) e i nomi nel
campo `tool`; nessun tema e nessun titolo (il tema è tra i `segreti` del tool). Solo libreria
standard.
"""
from __future__ import annotations

# Le regole contate, con la chiave del riassunto
REGOLE = {
    "notizie_feed": "feed",
    "notizie_ripiego": "ripiego",
    "notizie_ripiego_fallito": "ripiego_fallito",
    "notizie_ripiego_negato": "ripiego_negato",
    "notizie_vuote": "vuote",
    "notizie_seguito": "seguiti",
    "minore_notizie": "minori_rifiutate",
    "web_notizie_al_tool": "web_girate",
}
CHIAVI = ("richieste",) + tuple(REGOLE.values())


def _vuoto() -> dict:
    return {k: 0 for k in CHIAVI}


def _quota(r: dict) -> int | None:
    """La quota dai feed in percento: feed / (feed + ripiego); None senza nessuno dei due."""
    n = r["feed"] + r["ripiego"]
    return round(100 * r["feed"] / n) if n else None


def _turno(t: dict) -> dict | None:
    """I conteggi di un turno, o None se non ha chiesto notizie."""
    regole = t.get("regole") or ()
    if not isinstance(regole, (list, tuple, set)):
        regole = ()
    tool = t.get("tool") or ()
    con_tool = any(isinstance(x, dict) and x.get("nome") == "notizie"
                   for x in (tool if isinstance(tool, (list, tuple)) else ()))
    conti = {k: int(r in regole) for r, k in REGOLE.items()}
    if not con_tool and not any(conti.values()):
        return None
    conti["richieste"] = 1
    return conti


def riassunto(turni: list[dict]) -> dict:
    """Totale e per giorno (`inizio`, AAAA-MM-GG) dei turni con notizie, con la quota dai feed."""
    tot, giorni = _vuoto(), {}
    for t in turni:
        if not isinstance(t, dict):
            continue
        c = _turno(t)
        if c is None:
            continue
        g = giorni.setdefault(str(t.get("inizio") or "")[:10] or "?", _vuoto())
        for k, v in c.items():
            tot[k] += v
            g[k] += v
    for g in giorni.values():
        g["quota_feed"] = _quota(g)
    tot["quota_feed"] = _quota(tot)
    tot["per_giorno"] = dict(sorted(giorni.items()))
    return tot


def _pct(q) -> str:
    return f" ({q} %)" if q is not None else ""


def _n(n: int, una: str, tante: str) -> str:
    return f"{n} {una if n == 1 else tante}"


def testo(r: dict) -> str:
    """La riga per `calliope stato --turni`."""
    if not r.get("richieste"):
        return "Notizie: nessuna richiesta nel registro dei turni."
    righe = [
        f"Notizie: {_n(r['richieste'], 'richiesta', 'richieste')}, {r['feed']} dai giornali"
        f"{_pct(r['quota_feed'])}, {r['ripiego']} da internet, "
        f"{_n(r['vuote'], 'vuota', 'vuote')}; ripiego fallito {r['ripiego_fallito']}, negato "
        f"{r['ripiego_negato']}; seguiti {r['seguiti']}; minori: "
        f"{_n(r['minori_rifiutate'], 'sezione rifiutata', 'sezioni rifiutate')}; web_cerca "
        f"girato a notizie {r['web_girate']}."]
    for giorno, g in (r.get("per_giorno") or {}).items():
        righe.append(f"    {giorno}  {_n(g['richieste'], 'richiesta', 'richieste')}, "
                     f"{g['feed']} dai giornali{_pct(g['quota_feed'])}, {g['ripiego']} da "
                     f"internet, {_n(g['vuote'], 'vuota', 'vuote')}")
    return "\n".join(righe)
