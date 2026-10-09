"""
Il meteo di casa da Home Assistant (09/10, decisione di Dario: «se chiedo il meteo senza
indicazioni specifiche si intende quello di casa»; e niente internet quando se ne può fare a
meno).

Se in Home Assistant c'è un'entità `weather.*` esposta ad Assist (per esempio Met.no, che HA
scarica da sé), il meteo di casa lo dà lei: condizione, temperatura, umidità, vento dagli stati
già in memoria (nessuna richiesta), e le previsioni con il servizio di sola lettura
`weather.get_forecasts` (giornaliere o orarie, secondo `supported_features`). Senza entità
esposta vale la città di casa (calliope/luogo.py) con l'estensione meteo o la ricerca web.

Le condizioni di HA sono un insieme chiuso (documentazione dell'entità weather, verificata il
09/10): `clear-night`, `cloudy`, `exceptional`, `fog`, `hail`, `lightning`, `lightning-rainy`,
`partlycloudy`, `pouring`, `rainy`, `snowy`, `snowy-rainy`, `sunny`, `windy`,
`windy-variant`. Qui diventano parole italiane per la voce.

Il giorno chiesto (`quando`) lo sceglie il modello («domani», «stasera», «sabato»): qui c'è solo
la conversione in date (principio 10: conversione di una scelta già fatta dal modello).

Solo la libreria standard.
"""
from __future__ import annotations

import datetime as _dt
import re
import threading
import time

from .base import CasaNonRisponde, Entita
from .parole import norm, numero

# Le condizioni di HA in italiano: (con «è», da sola)
CONDIZIONI = {
    "clear-night": "sereno",
    "sunny": "sereno e soleggiato",
    "partlycloudy": "parzialmente nuvoloso",
    "cloudy": "nuvoloso",
    "fog": "nebbia",
    "rainy": "pioggia",
    "pouring": "pioggia forte",
    "lightning": "temporale",
    "lightning-rainy": "temporale con pioggia",
    "hail": "grandine",
    "snowy": "neve",
    "snowy-rainy": "pioggia mista a neve",
    "windy": "vento forte",
    "windy-variant": "vento forte e nuvole",
    "exceptional": "condizioni eccezionali",
}
# Le condizioni che si dicono «c'è …» invece di «è …» («c'è nebbia», non «è nebbia»)
_SOSTANTIVI = {"fog", "rainy", "pouring", "lightning", "lightning-rainy", "hail", "snowy",
               "snowy-rainy", "windy", "windy-variant", "exceptional"}

# supported_features dell'entità weather (WeatherEntityFeature)
PREVISIONI_GIORNALIERE, PREVISIONI_ORARIE, PREVISIONI_DUE_VOLTE = 1, 2, 4

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]

# Le previsioni si tengono qualche minuto: «e domani?» subito dopo «che tempo fa?» non
# chiede di nuovo a HA (Met.no aggiorna ogni ora)
CACHE_S = 600.0


def condizione(stato: str | None) -> str:
    """«partlycloudy» → «parzialmente nuvoloso»; una sconosciuta resta com'è, senza trattini."""
    s = str(stato or "").strip().lower()
    return CONDIZIONI.get(s) or s.replace("-", " ").replace("_", " ")


def condizione_detta(stato: str | None) -> str:
    """La condizione in una frase: «è parzialmente nuvoloso», «c'è pioggia»."""
    s = str(stato or "").strip().lower()
    return ("c'è " if s in _SOSTANTIVI else "è ") + condizione(s)


def esposte(entita: list[Entita]) -> list[Entita]:
    """Le entità meteo tra le esposte, la più adatta prima: una che risponde, poi una con
    «casa» o «home» nel nome o nell'id (HA chiama così quella della posizione di casa)."""
    meteo = [e for e in entita if e.dominio == "weather"]

    def peso(e: Entita):
        vivo = e.stato not in (None, "unavailable", "unknown")
        casa = bool(re.search(r"\b(casa|home)\b", norm(f"{e.nome} {e.id.replace('_', ' ')}")))
        return (not vivo, not casa, e.id)
    return sorted(meteo, key=peso)


def _numero_o_none(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _vento(v, unita: str | None) -> str:
    u = (unita or "km/h").strip().lower()
    detta = {"km/h": "chilometri orari", "m/s": "metri al secondo", "mph": "miglia orarie",
             "kn": "nodi", "ft/s": "piedi al secondo"}.get(u, u)
    return f"{numero(v)} {detta}"


def _gradi(unita: str | None) -> str:
    return "gradi Fahrenheit" if (unita or "").strip().upper() == "°F" else "gradi"


def adesso(e: Entita) -> dict:
    """Il meteo di adesso dagli attributi dell'entità (già in memoria)."""
    a = e.attributi or {}
    out = {"cielo": condizione(e.stato)}
    t = _numero_o_none(a.get("temperature"))
    if t is not None:
        out["temperatura"] = t
    for k_ha, k in (("apparent_temperature", "percepita"), ("humidity", "umidita"),
                    ("wind_speed", "vento"), ("pressure", "pressione"),
                    ("cloud_coverage", "nuvole_percento")):
        v = _numero_o_none(a.get(k_ha))
        if v is not None:
            out[k] = v
    return out


def frase_adesso(e: Entita) -> str:
    a = e.attributi or {}
    d = adesso(e)
    parti = [f"A casa adesso {condizione_detta(e.stato)}"]
    if "temperatura" in d:
        parti.append(f"{numero(d['temperatura'])} {_gradi(a.get('temperature_unit'))}")
    if "umidita" in d:
        parti.append(f"umidità al {numero(d['umidita'])} per cento")
    if "vento" in d and d["vento"] >= 1:
        parti.append(f"vento a {_vento(d['vento'], a.get('wind_speed_unit'))}")
    return ", ".join(parti) + "."


# ─────────────────────────── quando ───────────────────────────

_ORE = {"mattina": (6, 12), "stamattina": (6, 12), "pomeriggio": (12, 18),
        "stasera": (18, 24), "sera": (18, 24), "stanotte": (0, 6), "notte": (0, 6)}


def giorni_chiesti(quando: str, oggi: _dt.date) -> tuple[list[_dt.date], tuple | None]:
    """(date chieste, fascia oraria o None). «» o «adesso» → ([], None): il meteo di adesso.
    «oggi», «domani», «dopodomani», un giorno della settimana («sabato»: il prossimo, oggi
    compreso), «weekend» / «fine settimana», «prossimi giorni» / «settimana» (5 giorni).
    «stasera», «domani mattina», «sabato pomeriggio»: la fascia oraria (previsioni orarie)."""
    q = norm(quando)
    if not q or re.fullmatch(r"(adesso|ora|ora come ora|in questo momento|attuale|corrente)", q):
        return [], None
    fascia = next((v for k, v in _ORE.items() if re.search(rf"\b{k}\b", q)), None)
    if re.search(r"\bdopodomani\b", q):
        giorni = [oggi + _dt.timedelta(days=2)]
    elif re.search(r"\bdomani\b", q):
        giorni = [oggi + _dt.timedelta(days=1)]
    elif re.search(r"\b(weekend|week end|fine settimana)\b", q):
        sab = oggi + _dt.timedelta(days=(5 - oggi.weekday()) % 7)
        giorni = [sab, sab + _dt.timedelta(days=1)] if oggi.weekday() != 6 else [oggi]
    elif re.search(r"\b(prossimi giorni|settimana|giorni)\b", q):
        giorni = [oggi + _dt.timedelta(days=i) for i in range(5)]
    else:
        nomi = [norm(g) for g in GIORNI]
        giorno = next((i for i, g in enumerate(nomi) if re.search(rf"\b{g}\b", q)), None)
        if giorno is not None:
            giorni = [oggi + _dt.timedelta(days=(giorno - oggi.weekday()) % 7)]
        elif re.search(r"\b(oggi|stamattina|stasera|stanotte|stamani|oggi pomeriggio)\b", q) \
                or fascia:
            giorni = [oggi]
        else:
            giorni = [oggi]
    return giorni, fascia


def nome_giorno(g: _dt.date, oggi: _dt.date) -> str:
    diff = (g - oggi).days
    base = {0: "oggi", 1: "domani", 2: "dopodomani"}.get(diff)
    lungo = f"{GIORNI[g.weekday()]} {g.day}"
    return f"{base}, {lungo}" if base else lungo


# ─────────────────────────── previsioni ───────────────────────────

def _data_locale(s) -> tuple[_dt.date, int] | None:
    """La data e l'ora locali di un `datetime` delle previsioni (ISO, di solito in UTC)."""
    try:
        t = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone()                     # ora locale della macchina
    return t.date(), t.hour


def riassumi_giorno(voci: list[dict]) -> dict:
    """Una o più voci delle previsioni (dello stesso giorno) in un riassunto: cielo (la
    condizione più frequente, a pari merito la più «brutta»), massima, minima, pioggia."""
    gravita = list(CONDIZIONI)                  # in ordine dal sereno all'eccezionale
    conti: dict = {}
    for v in voci:
        c = str(v.get("condition") or "")
        if c:
            conti[c] = conti.get(c, 0) + 1
    out: dict = {}
    if conti:
        c = max(conti, key=lambda k: (conti[k], gravita.index(k) if k in gravita else -1))
        out["cielo"] = condizione(c)
        out["_condizione"] = c
    temps = [_numero_o_none(v.get("temperature")) for v in voci]
    temps = [t for t in temps if t is not None]
    bassi = [_numero_o_none(v.get("templow")) for v in voci]
    bassi = [t for t in bassi if t is not None]
    if temps:
        out["massima"] = max(temps)
        out["minima"] = min(bassi + temps) if (bassi or len(temps) > 1) else None
        if out["minima"] is None:
            out.pop("minima")
    pioggia = [_numero_o_none(v.get("precipitation")) for v in voci]
    pioggia = [p for p in pioggia if p is not None]
    if pioggia:
        out["pioggia_mm"] = round(sum(pioggia), 1)
    prob = [_numero_o_none(v.get("precipitation_probability")) for v in voci]
    prob = [p for p in prob if p is not None]
    if prob:
        out["probabilita_pioggia"] = max(prob)
    vento = [_numero_o_none(v.get("wind_speed")) for v in voci]
    vento = [x for x in vento if x is not None]
    if vento:
        out["vento"] = max(vento)
    return out


def frase_giorno(nome: str, r: dict, unita_vento: str | None = None) -> str:
    parti = []
    c = r.get("_condizione")
    if c:
        parti.append(condizione(c))
    if "massima" in r and "minima" in r and abs(r["massima"] - r["minima"]) >= 0.5:
        parti.append(f"tra {numero(r['minima'])} e {numero(r['massima'])} gradi")
    elif "massima" in r:
        parti.append(f"{numero(r['massima'])} gradi")
    if r.get("probabilita_pioggia") is not None and r["probabilita_pioggia"] >= 20:
        parti.append(f"probabilità di pioggia {numero(r['probabilita_pioggia'])} per cento")
    elif r.get("pioggia_mm"):
        parti.append(f"{numero(r['pioggia_mm'])} millimetri di pioggia")
    if r.get("vento") is not None and r["vento"] >= 30:
        parti.append(f"vento fino a {_vento(r['vento'], unita_vento)}")
    testo = ", ".join(parti) if parti else "nessuna previsione"
    return f"{nome[:1].upper()}{nome[1:]}: {testo}."


class MeteoCasa:
    """Il meteo di casa da un HomeBackend con un'entità weather esposta. Le previsioni si
    chiedono al backend (`previsioni`) e si tengono CACHE_S secondi."""

    def __init__(self, backend, oggi=None, ora=None):
        self.be = backend
        self._oggi = oggi or _dt.date.today
        self._ora = ora or time.monotonic
        self._cache: dict = {}
        self._lock = threading.Lock()

    def entita(self) -> Entita | None:
        meteo = esposte(self.be.entita())
        return meteo[0] if meteo else None

    def _previsioni(self, eid: str, tipo: str) -> list[dict]:
        k = (eid, tipo)
        with self._lock:
            hit = self._cache.get(k)
            if hit and self._ora() - hit[0] < CACHE_S:
                return hit[1]
        voci = self.be.previsioni(eid, tipo)
        with self._lock:
            self._cache[k] = (self._ora(), voci)
        return voci

    def leggi(self, quando: str = "") -> dict:
        """Il risultato per il tool meteo_leggi. Solleva CasaNonRisponde."""
        e = self.entita()
        if e is None:
            return {"ok": False, "entita": False,
                    "errore": "in Home Assistant non c'è un'entità meteo esposta"}
        if e.stato in (None, "unavailable", "unknown"):
            return {"ok": False, "entita": False,
                    "errore": "l'entità meteo di Home Assistant non risponde"}
        oggi = self._oggi()
        giorni, fascia = giorni_chiesti(quando, oggi)
        if not giorni:
            return {"ok": True, "dove": "casa", "quando": "adesso", "adesso": adesso(e),
                    "frase": frase_adesso(e)}
        feat = int(_numero_o_none((e.attributi or {}).get("supported_features")) or 0)
        tipo = None
        if fascia and feat & PREVISIONI_ORARIE:
            tipo = "hourly"
        elif feat & PREVISIONI_GIORNALIERE:
            tipo = "daily"
        elif feat & PREVISIONI_ORARIE:
            tipo = "hourly"
        elif feat & PREVISIONI_DUE_VOLTE:
            tipo = "twice_daily"
        if tipo is None:
            out = {"ok": True, "dove": "casa", "quando": "adesso", "adesso": adesso(e),
                   "frase": frase_adesso(e),
                   "nota": "Home Assistant non dà previsioni per questa entità: solo il meteo "
                           "di adesso. Dillo in breve se chiedevano un altro giorno."}
            return out
        try:
            voci = self._previsioni(e.id, tipo)
        except CasaNonRisponde:
            raise
        except Exception as ex:  # noqa: BLE001 — servizio assente o risposta strana
            return {"ok": False, "errore": f"previsioni non disponibili ({type(ex).__name__})",
                    "adesso": adesso(e), "frase_adesso": frase_adesso(e)}
        per_giorno: dict = {}
        for v in voci or ():
            if not isinstance(v, dict):
                continue
            d = _data_locale(v.get("datetime"))
            if d is None:
                continue
            g, h = d
            if g not in giorni:
                continue
            if fascia and tipo == "hourly" and not (fascia[0] <= h < fascia[1]):
                continue
            per_giorno.setdefault(g, []).append(v)
        unita_vento = (e.attributi or {}).get("wind_speed_unit")
        risultati, frasi = [], []
        for g in giorni:
            if g not in per_giorno:
                continue
            r = riassumi_giorno(per_giorno[g])
            nome = nome_giorno(g, oggi) + (f" ({quando.strip()})" if fascia else "")
            frasi.append(frase_giorno(nome, r, unita_vento))
            risultati.append({"giorno": nome, **{k: v for k, v in r.items()
                                                 if not k.startswith("_")}})
        if not risultati:
            return {"ok": False, "errore": "nessuna previsione per il giorno chiesto",
                    "frase_adesso": frase_adesso(e),
                    "giorni_previsti": sorted({str(_data_locale(v.get("datetime"))[0])
                                               for v in voci or () if isinstance(v, dict)
                                               and _data_locale(v.get("datetime"))})[:7]}
        return {"ok": True, "dove": "casa", "quando": quando.strip(), "previsioni": risultati,
                "frase": " ".join(frasi)}
