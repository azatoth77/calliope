"""
Chi è Calliope e cosa c'è di nuovo (09/10/2026): `calliope_stato` con cosa=novita e
cosa=chi_sei (calliope/tools/stato.py).

Caso vero (DGX, 09/10): «Hai modo di sapere quali sono state le ultime novità sul tuo
aggiornamento?» → l'elenco intero delle capacità, poi «non ho un registro delle versioni»
(falso: c'è CHANGELOG.md) e «il mio codice risiede… distribuito su diversi server» (falso:
gira in locale). Qui i fatti veri, letti dal codice installato:

- la versione: il numero del pacchetto (pyproject.toml), il commit e la data del codice
  (VERSIONE.json del gestore di Linux, o il git del portatile: `cruscotto.versione_in_uso`),
  quando è stata installata e da quale versione si veniva (la `storia` di gestione.json,
  due cartelle sopra quella della versione: `versioni/<id>/`);
- le novità: le righe di CHANGELOG.md della versione installata, per data. Di norma quelle
  dopo la versione di prima (dal gestore), altrimenti le ultime due date; con un periodo
  («da ieri», «questa settimana») quelle del periodo;
- chi è: gira su questa macchina (tipo dall'inventario di calliope/macchina.py, mai il nome
  host), i modelli della voce e dell'agente, la versione, la licenza AGPL e il codice
  pubblico, niente cloud.

A voce una frase breve (risposta_finale: il modello non la riscrive); il testo intero va
nella scheda personale in Markdown, con «Scarica». Mai segreti, indirizzi, host o percorsi:
dalle frasi tolte le parti con un indirizzo o un percorso, i link ridotti al loro testo.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]

MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")
PERIODI = ("ultimo_aggiornamento", "oggi", "da_ieri", "settimana", "mese")
_GIORNI_PERIODO = {"oggi": 0, "da_ieri": 1, "settimana": 6, "mese": 30}
VOCE_PAROLE = 40          # le novità a voce: oltre, «il resto è sullo schermo»
VOCE_FRASE_PAROLE = 18    # una voce del registro detta a voce, al più
VOCE_DATE = 3             # date dette a voce, al più


# ─────────────────────────── versione ───────────────────────────

def _numero(radice: Path) -> str:
    """«0.3.0» → «0.3»: il numero del pacchetto, da pyproject.toml della versione."""
    try:
        import tomllib
        with open(radice / "pyproject.toml", "rb") as f:
            v = str(tomllib.load(f).get("project", {}).get("version") or "")
    except (OSError, ValueError, ImportError):
        return ""
    return re.sub(r"\.0$", "", v) if re.fullmatch(r"\d+\.\d+\.0", v) else v


def _data_id(vid: str) -> _dt.datetime | None:
    """La data del commit dall'id della cartella del gestore («20261009-0812-1e0a1440»)."""
    m = re.match(r"(\d{8})-(\d{4})", str(vid or ""))
    if not m:
        return None
    try:
        return _dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def _data(testo: str) -> _dt.datetime | None:
    t = str(testo or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = _dt.datetime.strptime(t[:25], fmt)
            return d.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _storia(radice: Path) -> list[dict]:
    """La storia del gestore (gestione.json), se questa è una versione installata da lui."""
    if radice.parent.name != "versioni":
        return []
    try:
        imp = json.loads((radice.parent.parent / "gestione.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    st = imp.get("storia") if isinstance(imp, dict) else None
    return [v for v in st if isinstance(v, dict)] if isinstance(st, list) else []


def versione(radice: Path | None = None) -> dict:
    """numero, commit (corto), codice (data del commit), aggiornata (quando è stata messa in
    uso qui, se lo sa il gestore), precedente (data del codice della versione di prima)."""
    from .schermi.cruscotto import versione_in_uso
    radice = Path(radice or _RADICE)
    v = versione_in_uso(radice)
    out = {"numero": _numero(radice), "commit": str(v.get("commit") or "")[:7],
           "codice": None, "aggiornata": None, "precedente": None,
           "origine": v.get("origine") or ""}
    if v.get("origine") == "installata":
        out["codice"] = _data_id(radice.name)
        out["aggiornata"] = _data(v.get("installata"))
        for voce in reversed(_storia(radice)):
            if voce.get("a") == radice.name and voce.get("esito") == "ok":
                out["aggiornata"] = _data(voce.get("quando")) or out["aggiornata"]
                out["precedente"] = _data_id(voce.get("da") or "")
                break
    else:
        out["codice"] = _data(v.get("installata"))
    return out


def data_detta(d, oggi: _dt.date | None = None) -> str:
    """«il 9 ottobre», «l'8 ottobre», con l'anno solo se non è quello di oggi."""
    if d is None:
        return ""
    oggi = oggi or _dt.date.today()
    art = "l'" if d.day in (8, 11) else "il "
    anno = "" if d.year == oggi.year else f" {d.year}"
    return f"{art}{d.day} {MESI[d.month - 1]}{anno}"


def frase_versione(v: dict, oggi: _dt.date | None = None) -> str:
    pezzi = "Sono la versione" + (f" {v['numero']}" if v.get("numero") else "")
    if v.get("codice"):
        dd = data_detta(v["codice"], oggi)
        pezzi += " dell'" + dd[2:] if dd.startswith("l'") else " del " + dd[3:]
    frase = pezzi + "."
    agg = v.get("aggiornata")
    if agg:
        frase += f" Mi hanno aggiornata qui {data_detta(agg, oggi)} alle {agg.hour}:{agg.minute:02d}."
    return frase


# ─────────────────────────── CHANGELOG ───────────────────────────

_DATA = re.compile(r"(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?/(\d{1,2})(?:/(\d{4}))?")


def voci_changelog(testo: str, anno: int | None = None) -> list[dict]:
    """Le voci di CHANGELOG.md: le righe della tabella «| Data | Tappa |» e le sezioni
    «## titolo (gg/mm/aaaa)» con il loro elenco. Ogni voce: data (l'ultimo giorno di un
    intervallo), etichetta come scritta, testo. In ordine di file."""
    anno = anno or _dt.date.today().year
    out = []
    sezione = None
    for riga in str(testo or "").splitlines():
        r = riga.strip()
        if r.startswith("#"):
            sezione = None
            m = _DATA.search(r)
            if r.startswith("## ") and m and m.group(4):
                anno = int(m.group(4))
                d = _dt.date(anno, int(m.group(3)), int(m.group(2) or m.group(1)))
                sezione = {"data": d, "etichetta": r.lstrip("# ").strip(), "voci": []}
                out.append(sezione)
            continue
        if sezione is not None and r.startswith(("- ", "* ")):
            sezione["voci"].append(r[2:].strip())
            continue
        if sezione is not None and r and sezione["voci"] and not r.startswith("|"):
            sezione["voci"][-1] += " " + r          # riga a capo dentro una voce
            continue
        if r.startswith("|"):
            celle = [c.strip() for c in r.strip("|").split("|")]
            if len(celle) < 2:
                continue
            m = _DATA.match(celle[0])
            if not m:
                continue
            if m.group(4):
                anno = int(m.group(4))
            try:
                d = _dt.date(anno, int(m.group(3)), int(m.group(2) or m.group(1)))
            except ValueError:
                continue
            out.append({"data": d, "etichetta": celle[0], "testo": " | ".join(celle[1:])})
    for v in out:
        if "voci" in v:
            v["testo"] = "; ".join(x.rstrip(".;") for x in v.pop("voci"))
    return out


def scegli(voci: list[dict], periodo: str = "", oggi: _dt.date | None = None,
           dopo: _dt.date | None = None, codice: _dt.date | None = None) -> tuple[list, str]:
    """Le voci da dire, dalla più recente, e come sono state scelte: «periodo» (nel periodo
    chiesto), «vuoto» (niente nel periodo: allora le ultime), «aggiornamento» (dopo la
    versione di prima), «ultime» (le ultime due date). `codice`: niente voci dopo la data
    del codice installato."""
    oggi = oggi or _dt.date.today()
    tutte = [v for v in voci if codice is None or v["data"] <= codice]
    # Dalla più recente; a parità di data l'ultima scritta (il file va avanti nel tempo)
    tutte = [v for _, v in sorted(enumerate(tutte), key=lambda iv: (iv[1]["data"], iv[0]),
                                  reverse=True)]
    if not tutte:
        return [], "ultime"

    def ultime(n=2):
        date = sorted({v["data"] for v in tutte}, reverse=True)[:n]
        return [v for v in tutte if v["data"] in date]

    if periodo in _GIORNI_PERIODO:
        da = oggi - _dt.timedelta(days=_GIORNI_PERIODO[periodo])
        scelte = [v for v in tutte if v["data"] >= da]
        return (scelte, "periodo") if scelte else (ultime(1), "vuoto")
    if dopo is not None:
        scelte = [v for v in tutte if v["data"] > dopo]
        if scelte:
            return scelte, "aggiornamento"
    return ultime(), "ultime"


# Ciò che non si dice mai: indirizzi, host, percorsi (anche se il CHANGELOG è pubblico)
_SENSIBILE = re.compile(r"https?://|www\.|\b\d{1,3}(?:\.\d{1,3}){3}\b|~/|[A-Za-z]:\\|"
                        r"\b[\w-]+\.(?:duckdns\.org|local|lan|home)\b|"
                        r"(?<![\w«])(?:[\w.-]+/){1,}[\w.-]+\.\w{1,5}\b", re.I)


def _pulisci_md(t: str) -> str:
    """Il testo per la scheda: link ridotti al testo, niente indirizzi."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", str(t or ""))
    return re.sub(r"https?://\S+", "…", t)


def _per_voce(t: str) -> str:
    """Il testo per la voce: senza parentesi (dettagli e comandi), senza codice tra apici,
    senza Markdown."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", str(t or ""))
    # Un indirizzo o un percorso segna il suo pezzo, che poi si toglie intero (_frasi): «casa
    # su http://…» non diventa «casa su»
    t = re.sub(r"`[^`]*`", lambda m: "\x00" if _SENSIBILE.search(m.group(0)) else "", t)
    t = _SENSIBILE.sub("\x00", t)
    prima = None
    while prima != t:                       # parentesi annidate: dall'interno
        prima = t
        t = re.sub(r"\s*\([^()]*\)", "", t)
    t = t.replace("**", "").replace("*", "").replace("→", ",")
    return re.sub(r"\s+([,;.:])", r"\1", re.sub(r"\s{2,}", " ", t)).strip(" ,;")


def _frasi(testo: str) -> list[str]:
    """Le voci di una riga: pezzi separati da «;» (fuori dalle parentesi, già tolte)."""
    out = []
    for p in _per_voce(testo).split(";"):
        p = p.strip(" ,.")
        if not p or "\x00" in p or _SENSIBILE.search(p):
            continue
        parole = p.split()
        if len(parole) > VOCE_FRASE_PAROLE:
            corto = " ".join(parole[:VOCE_FRASE_PAROLE])
            p = corto.rsplit(",", 1)[0] if "," in corto[len(corto) // 2:] else corto
        out.append(p)
    return out


def _minuscola(p: str) -> str:
    return p[:1].lower() + p[1:] if len(p) > 1 and p[1:2].islower() else p


def testo_voce(scelte: list[dict], modo: str, periodo: str = "",
               oggi: _dt.date | None = None) -> tuple[str, bool]:
    """Le novità a voce (2–4 frasi) e se ne è rimasto fuori qualcosa."""
    if not scelte:
        return "Nel registro dei cambiamenti di questa versione non trovo novità.", False
    per_data: dict = {}
    for v in scelte:
        per_data.setdefault(v["data"], []).extend(_frasi(v["testo"]))
    date = list(per_data)
    detto, parole, fuori = [], 0, False
    for i, d in enumerate(date):
        if i >= VOCE_DATE or parole >= VOCE_PAROLE:
            fuori = True
            break
        pezzi = []
        for p in per_data[d]:
            n = len(p.split())
            if pezzi and parole + n > VOCE_PAROLE:
                fuori = True
                break
            pezzi.append(_minuscola(p))
            parole += n
        if len(pezzi) < len(per_data[d]):
            fuori = True
        if pezzi:
            dd = data_detta(d, oggi)
            if detto:                       # dopo la prima, una frase nuova
                dd = dd[:1].upper() + dd[1:]
            detto.append(f"{dd}, " + "; ".join(pezzi) + ".")
    testa = {"periodo": {"oggi": "Novità di oggi, dal registro dei cambiamenti.",
                         "da_ieri": "Da ieri, dal registro dei cambiamenti:",
                         "settimana": "Questa settimana, dal registro dei cambiamenti:",
                         "mese": "Nell'ultimo mese, dal registro dei cambiamenti:"
                         }.get(periodo, "Dal registro dei cambiamenti:"),
             "vuoto": "In questo periodo il registro dei cambiamenti non ha novità; le "
                      "ultime:",
             "aggiornamento": "Dall'ultimo aggiornamento, nel registro dei cambiamenti:",
             }.get(modo, "Le ultime novità nel registro dei cambiamenti:")
    if testa.endswith("."):
        testa = testa[:-1] + ":"
    return testa + " " + " ".join(detto), fuori


def markdown(v: dict, voci: list[dict], scelte: list[dict], oggi: _dt.date | None = None
             ) -> str:
    """Il testo della scheda: la versione, le novità scelte per intero, le altre date."""
    oggi = oggi or _dt.date.today()
    righe = ["# Novità di Calliope", ""]
    info = []
    if v.get("numero"):
        info.append(f"Versione {v['numero']}")
    if v.get("commit"):
        info.append(f"commit {v['commit']}")
    if v.get("codice"):
        info.append(f"codice del {v['codice']:%d/%m/%Y}")
    if v.get("aggiornata"):
        info.append(f"installata qui il {v['aggiornata']:%d/%m/%Y alle %H:%M}")
    if info:
        righe += [", ".join(info) + ".", ""]
    if scelte:
        righe += ["## Le novità", ""]
        for x in scelte:
            righe.append(f"- **{_pulisci_md(x['etichetta'])}**: {_pulisci_md(x['testo'])}")
        righe.append("")
    altre = [x for x in sorted(voci, key=lambda x: x["data"], reverse=True)
             if x not in scelte][:8]
    if altre:
        righe += ["## Prima", ""]
        for x in altre:
            righe.append(f"- **{_pulisci_md(x['etichetta'])}**: {_pulisci_md(x['testo'])}")
        righe.append("")
    righe.append("Il registro completo è nel file CHANGELOG.md del codice.")
    return "\n".join(righe)


def novita(periodo: str = "", radice: Path | None = None, oggi: _dt.date | None = None
           ) -> dict:
    """{frase, markdown, fuori, voci}: la versione e le novità, per la voce e per la scheda."""
    radice = Path(radice or _RADICE)
    oggi = oggi or _dt.date.today()
    v = versione(radice)
    try:
        testo = (radice / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        testo = ""
    anno = v["codice"].year if v.get("codice") else oggi.year
    voci = voci_changelog(testo, anno)
    periodo = periodo if periodo in PERIODI else ""
    codice = v["codice"].date() if v.get("codice") else None
    dopo = v["precedente"].date() if v.get("precedente") else None
    if periodo and periodo != "ultimo_aggiornamento":
        scelte, modo = scegli(voci, periodo, oggi, codice=codice)
    else:
        scelte, modo = scegli(voci, "", oggi, dopo=dopo, codice=codice)
    if not voci:
        frase = frase_versione(v, oggi) + (" Il registro dei cambiamenti non è in questa "
                                           "installazione.")
        return {"frase": frase, "markdown": "", "fuori": False, "voci": 0}
    detto, fuori = testo_voce(scelte, modo, periodo, oggi)
    return {"frase": frase_versione(v, oggi) + " " + detto,
            "markdown": markdown(v, voci, scelte, oggi), "fuori": fuori,
            "voci": len(scelte)}


# ─────────────────────────── chi sei ───────────────────────────

def chi_sei(cfg, lavori=None, registro=None, radice: Path | None = None,
            oggi: _dt.date | None = None) -> str:
    """Fatti veri su di sé, per «chi sei?», «dove giri?», «chi ti ha fatta?»: questa
    macchina (senza nome host), i modelli, la versione, la licenza, niente cloud."""
    from .macchina import _dove, _modello_voce, dati
    d = dati()
    nome = getattr(cfg, "name", "") or "Calliope"
    mac = f"un {d['modello']}" if d.get("modello") else "un computer"
    if d.get("sistema"):
        mac += f" con {d['sistema']}"
    url = cfg.llm_native_url if getattr(cfg, "llm_backend", "") == "ollama" else \
        getattr(cfg, "llm_base_url", None)
    pezzi = [f"Sono {nome}, un'assistente vocale che gira in casa, su questo computer: {mac}."]
    modello = _modello_voce(getattr(cfg, "llm_model", "") or "")
    voce = f"Per parlare uso il modello {modello}" if modello else "Per parlare uso un modello"
    voce += (", qui sullo stesso computer" if _dove(url) == "sullo stesso computer"
             else ", su un altro computer della casa")
    imp = getattr(lavori, "imp", None)
    if imp is not None and getattr(imp, "modello", None):
        voce += f"; per i lavori lunghi l'agente {_modello_voce(imp.modello)}"
    pezzi.append(voce + ".")
    web = registro.get("web") if registro is not None and len(registro) else None
    pezzi.append("Non uso servizi nel cloud: quello che dici resta qui"
                 + (", e internet lo uso solo per le ricerche che mi chiedi."
                    if web is not None and web.attiva else "."))
    v = versione(radice)
    fv = frase_versione(v, oggi).split(". ")[0].rstrip(".")
    pezzi.append(f"{fv}. Il mio codice è libero, con licenza AGPL, ed è pubblico; qui mi "
                 f"installa e mi aggiorna chi amministra la casa.")
    return " ".join(pezzi)
