"""
La scelta dei tool come metrica (12/10/2026, punto 1 di docs/ricerche/2026-10-10-scelta-dei-tool.md).

Nei giri del 10/10 quasi tutti i difetti veri erano scelte di tool: nomi inventati
(`sviluppo_stato`, `sviluppo_ferma`), il tool sbagliato fra due veri, il giusto usato male. Per
chi parla è come un'incomprensione, e fino a oggi lo si scopriva leggendo i registri. Qui, dal
registro dei turni (calliope/turnlog.py), per ogni giorno:

- **nomi inventati**: chiamate a un tool che non c'è. Corrette da Brain (`nome_inventato`, il
  nome scritto dal modello, accanto al `nome` vero) o senza un tool vicino (`sconosciuto`):
  allora «cosa si voleva» è la chiamata riuscita dopo, nella stessa risposta. Nei turni di prima
  del 12/10 si contano le regole `tool_nome_corretto` e `tool_nome_azione`, senza i nomi;
- **correzioni**: chiamate ferme per gli argomenti (`correggibile`) e quante sono riuscite al
  giro dopo (lo stesso tool, riuscito, dopo nella risposta); giri di correzione **esauriti**
  (`correzioni_esaurite`);
- **ripieghi**: «Non ci sono riuscita: puoi ripetere la richiesta?» (`vuoto_ripiego`,
  `nome_tool_ripetuto`, `dichiarata_taciuta`) o una risposta che comincia con «Non ci sono
  riuscita»;
- **richieste ripetute**: la stessa persona che, entro `RIPETUTA_S`, ridice o riformula la
  frase di prima (somiglianza delle parole ≥ `SOMIGLIANZA`): il segnale più forte di una scelta
  sbagliata. Contate a parte quelle dopo un turno con tool o un ripiego. Servono le parole: solo
  turni degli adulti (calliope/conserva.py);
- un **indice**: problemi (inventati senza tool vicino, giri esauriti, ripieghi, ripetute dopo
  un tool) ogni 100 turni con tool, e un **avviso** oltre `AVVISO` con almeno `MIN_CON_TOOL`
  turni con tool.

Solo lettura del registro, solo libreria standard. `calliope stato --turni`.
"""
from __future__ import annotations

import datetime
import difflib
import re

RIPETUTA_S = 90.0         # la frase dopo entro questi secondi
SOMIGLIANZA = 0.6         # parole in comune (difflib) per dire «ripetuta o riformulata»
AVVISO = 10.0             # problemi ogni 100 turni con tool
MIN_CON_TOOL = 20         # sotto, un giorno non fa statistica (e non dà avvisi)
REGOLE_RIPIEGO = frozenset({"vuoto_ripiego", "nome_tool_ripetuto", "dichiarata_taciuta"})
REGOLE_NOME = frozenset({"tool_nome_corretto", "tool_nome_azione"})
_PAROLA = re.compile(r"[a-zà-ù0-9]+", re.I)


def _parole(testo) -> list[str]:
    return [w.lower() for w in _PAROLA.findall(str(testo or ""))]


def somiglianza(a, b) -> float:
    """Quanto due frasi hanno le stesse parole, nello stesso ordine (0–1)."""
    pa, pb = _parole(a), _parole(b)
    if not pa or not pb:
        return 0.0
    return difflib.SequenceMatcher(None, pa, pb).ratio()


def _quando(t: dict) -> float | None:
    try:
        return datetime.datetime.fromisoformat(str(t.get("inizio"))).timestamp()
    except (TypeError, ValueError):
        return None


def _chi(t: dict):
    v = t.get("voce") if isinstance(t.get("voce"), dict) else {}
    return v.get("id") or v.get("nome")


def _ripiego(t: dict) -> bool:
    regole = set(t.get("regole") or ())
    r = t.get("risposta")
    return bool(regole & REGOLE_RIPIEGO) or (isinstance(r, str)
                                             and r.strip().startswith("Non ci sono riuscita"))


def turno(t: dict) -> dict:
    """Le misure di un turno: inventati [(scritto, voluto)], correzioni, riuscite, esauriti,
    ripiego, regole dei nomi (turni di prima)."""
    tool = [x for x in t.get("tool") or () if isinstance(x, dict)]
    inventati = []
    for i, x in enumerate(tool):
        if x.get("nome_inventato"):
            inventati.append((str(x["nome_inventato"]), str(x.get("nome")), True))
        elif x.get("sconosciuto"):
            dopo = next((y.get("nome") for y in tool[i + 1:]
                         if y.get("ok") and not y.get("sconosciuto")), None)
            inventati.append((str(x.get("nome")), str(dopo) if dopo else "?", False))
    corr = riuscite = 0
    for i, x in enumerate(tool):
        if x.get("correggibile"):
            corr += 1
            if any(y.get("nome") == x.get("nome") and y.get("ok") for y in tool[i + 1:]):
                riuscite += 1
    regole = set(t.get("regole") or ())
    return {"inventati": inventati, "correzioni": corr, "riuscite": riuscite,
            "esauriti": int("correzioni_esaurite" in regole), "ripiego": _ripiego(t),
            "nomi_regole": sum(1 for r in t.get("regole") or () if r in REGOLE_NOME),
            "con_tool": bool(tool)}


def giorno(turni: list[dict]) -> dict:
    """Le misure di un gruppo di turni (di solito un giorno), in ordine di tempo."""
    risposte = [t for t in turni if t.get("esito") == "risposta"]
    misure = [turno(t) for t in risposte]
    inventati = [x for m in misure for x in m["inventati"]]
    nomi: dict[tuple, int] = {}
    for scritto, voluto, _corretto in inventati:
        nomi[(scritto, voluto)] = nomi.get((scritto, voluto), 0) + 1
    con_tool = sum(1 for m in misure if m["con_tool"])
    # Le richieste ripetute: due turni di fila della stessa persona (con le parole)
    ripetute = dopo_tool = con_parole = 0
    prec = None
    for t in turni:
        if t.get("esito") not in ("risposta", "interruzione") or not isinstance(
                t.get("testo"), str) or not t["testo"].strip():
            continue
        con_parole += 1
        q, chi = _quando(t), _chi(t)
        if prec is not None and chi and chi == _chi(prec) and q is not None \
                and _quando(prec) is not None and 0 <= q - _quando(prec) <= RIPETUTA_S \
                and somiglianza(prec["testo"], t["testo"]) >= SOMIGLIANZA:
            ripetute += 1
            if prec.get("tool") or _ripiego(prec):
                dopo_tool += 1
        prec = t
    senza_vicino = sum(1 for x in inventati if not x[2])
    esauriti = sum(m["esauriti"] for m in misure)
    ripieghi = sum(1 for m in misure if m["ripiego"])
    problemi = senza_vicino + esauriti + ripieghi + dopo_tool
    return {
        "risposte": len(risposte), "con_tool": con_tool,
        "inventati": {"n": len(inventati), "corretti": len(inventati) - senza_vicino,
                      "senza_vicino": senza_vicino,
                      "regole": sum(m["nomi_regole"] for m in misure),
                      "nomi": [{"scritto": s, "voluto": v, "volte": n} for (s, v), n in
                               sorted(nomi.items(), key=lambda kv: -kv[1])][:8]},
        "correzioni": {"n": sum(m["correzioni"] for m in misure),
                       "riuscite": sum(m["riuscite"] for m in misure), "esauriti": esauriti},
        "ripieghi": ripieghi,
        "ripetute": {"n": ripetute, "dopo_tool": dopo_tool, "turni_con_parole": con_parole},
        "problemi": problemi,
        "indice": round(100.0 * problemi / con_tool, 1) if con_tool else None,
    }


def per_giorno(turni: list[dict]) -> dict[str, dict]:
    gruppi: dict[str, list] = {}
    for t in turni:
        d = str(t.get("inizio") or "")[:10]
        if d:
            gruppi.setdefault(d, []).append(t)
    return {d: giorno(sorted(g, key=lambda x: str(x.get("inizio") or "")))
            for d, g in sorted(gruppi.items())}


def avviso(d: dict, soglia: float = AVVISO, data: str = "") -> str | None:
    if d["con_tool"] < MIN_CON_TOOL or d["indice"] is None or d["indice"] <= soglia:
        return None
    quando = f" del {data}" if data else ""
    return (f"la scelta dei tool{quando} ha {d['indice']:.1f} problemi ogni 100 turni con tool "
            f"(soglia {soglia:.0f}): {d['inventati']['senza_vicino']} nomi inventati senza un "
            f"tool vicino, {d['correzioni']['esauriti']} giri di correzione esauriti, "
            f"{d['ripieghi']} ripieghi, {d['ripetute']['dopo_tool']} richieste ripetute dopo un "
            f"tool.")


def testo(giorni: dict[str, dict]) -> str:
    """Le righe per `calliope stato --turni`."""
    if not giorni:
        return "Scelta dei tool: nessun turno nel registro."
    righe = ["Scelta dei tool dal registro dei turni (nomi inventati, correzioni, ripieghi, "
             "richieste ripetute)", ""]
    for data, d in giorni.items():
        inv, c, rp = d["inventati"], d["correzioni"], d["ripetute"]
        righe.append(f"{data}  {d['risposte']} risposte, {d['con_tool']} con tool"
                     + (f"  indice {d['indice']:.1f} ogni 100" if d["indice"] is not None
                        else ""))
        pezzi = []
        if inv["n"] or inv["regole"]:
            pezzi.append(f"nomi inventati {inv['n']} ({inv['corretti']} corretti, "
                         f"{inv['senza_vicino']} senza un tool vicino)"
                         + (f", regole dei nomi {inv['regole']}" if inv["regole"] else ""))
        if c["n"] or c["esauriti"]:
            pezzi.append(f"correzioni {c['n']} ({c['riuscite']} riuscite al giro dopo), "
                         f"{c['esauriti']} esaurite")
        if d["ripieghi"]:
            pezzi.append(f"ripieghi {d['ripieghi']}")
        if rp["turni_con_parole"]:
            pezzi.append(f"ripetute {rp['n']} ({rp['dopo_tool']} dopo un tool) su "
                         f"{rp['turni_con_parole']} frasi con le parole")
        if pezzi:
            righe.append("    " + "; ".join(pezzi))
        if inv["nomi"]:
            righe.append("    " + ", ".join(f"{x['scritto']} → {x['voluto']}"
                                            + (f" ×{x['volte']}" if x["volte"] > 1 else "")
                                            for x in inv["nomi"]))
        a = avviso(d)
        if a:
            righe.append("    ATTENZIONE: " + a[0].upper() + a[1:])
    return "\n".join(righe)


def avviso_recente(cfg, oggi: datetime.date | None = None) -> str | None:
    """L'avviso di oggi o di ieri (il primo giorno con abbastanza turni con tool)."""
    from . import latenza
    oggi = oggi or datetime.date.today()
    try:
        giorni = per_giorno(latenza.leggi(getattr(cfg, "turn_log_dir", None), 2))
        for data in (oggi.isoformat(), (oggi - datetime.timedelta(days=1)).isoformat()):
            d = giorni.get(data)
            if d and d["con_tool"] >= MIN_CON_TOOL:
                a = avviso(d, AVVISO, data)
                return (a[0].upper() + a[1:]) if a else None
    except Exception:  # noqa: BLE001 — un registro strano non ferma niente
        pass
    return None
