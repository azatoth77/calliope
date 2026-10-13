"""
L'elenco dei feed delle notizie (13/10/2026): dalla configurazione (`notizie_feed`,
`notizie_feed_extra`, testate spente e accese per nome) più il feed regionale dell'ANSA dalla
città di casa (`notizie_regione`, o `casa_citta` → regione). Solo libreria standard.

Un feed si scrive come una riga: «testata | tema | indirizzo [| opzioni]», con le opzioni
`fuso=Europe/Rome` (la testata scrive l'ora italiana con l'etichetta GMT, come Sky TG24) e
`veloce` (il feed cambia per intero in meno di due ore, come Adnkronos).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

TEMI = ("generale", "sport", "economia", "tecnologia", "ragazzi", "allerta", "locale")
# I temi che sentono i minori (decisione di chi amministra del 13/10)
TEMI_MINORI = ("sport", "tecnologia", "ragazzi")


@dataclass(frozen=True)
class Feed:
    testata: str          # il nome detto a voce («ANSA», «Sky TG24»)
    tema: str
    url: str
    fuso: str = ""        # «Europe/Rome»: le ore del feed sono italiane anche se dicono GMT
    veloce: bool = False
    opzioni: tuple = field(default_factory=tuple)


def _chiave(nome: str) -> str:
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t.lower())


def leggi_riga(riga: str) -> Feed | None:
    """Una riga di notizie_feed → Feed, o None se non è valida (indirizzo non http(s), tema
    sconosciuto, testata vuota)."""
    parti = [p.strip() for p in str(riga or "").split("|")]
    if len(parti) < 3:
        return None
    testata, tema, url, *opz = parti
    tema = tema.lower()
    if not testata or tema not in TEMI or not re.match(r"^https?://[^\s/]+", url):
        return None
    fuso, veloce = "", False
    for o in opz:
        if o.lower().startswith("fuso="):
            fuso = o.split("=", 1)[1].strip()
        elif o.lower() == "veloce":
            veloce = True
    return Feed(testata=testata, tema=tema, url=url, fuso=fuso, veloce=veloce,
                opzioni=tuple(o for o in opz if o))


# ─────────────────────────── la regione di casa ───────────────────────────
# Il nome dell'ANSA per ogni regione (indirizzi provati il 13/10: 20 su 20 rispondono)
REGIONI = {
    "abruzzo": "abruzzo", "basilicata": "basilicata", "calabria": "calabria",
    "campania": "campania", "emilia romagna": "emiliaromagna",
    "friuli venezia giulia": "friuliveneziagiulia", "lazio": "lazio", "liguria": "liguria",
    "lombardia": "lombardia", "marche": "marche", "molise": "molise", "piemonte": "piemonte",
    "puglia": "puglia", "sardegna": "sardegna", "sicilia": "sicilia", "toscana": "toscana",
    "trentino alto adige": "trentino", "umbria": "umbria", "valle d aosta": "valledaosta",
    "veneto": "veneto",
}
# Altri modi di dire una regione
_REGIONI_ALTRE = {"emilia": "emiliaromagna", "friuli": "friuliveneziagiulia",
                  "trentino": "trentino", "alto adige": "trentino", "sudtirolo": "trentino",
                  "valle daosta": "valledaosta", "vallee d aoste": "valledaosta"}
# I capoluoghi di provincia (e qualche città grande) con la loro regione: la città di casa si
# riconosce solo per intero, mai una parola dentro il nome
_CITTA = {
    "lombardia": "milano bergamo brescia como cremona lecco lodi mantova monza pavia sondrio "
                 "varese legnano busto arsizio sesto san giovanni cinisello balsamo vigevano",
    "piemonte": "torino alessandria asti biella cuneo novara verbania vercelli",
    "valledaosta": "aosta",
    "liguria": "genova imperia la spezia savona sanremo",
    "veneto": "venezia belluno padova rovigo treviso verona vicenza mestre",
    "trentino": "trento bolzano merano rovereto",
    "friuliveneziagiulia": "trieste gorizia pordenone udine",
    "emiliaromagna": "bologna ferrara forli cesena modena parma piacenza ravenna "
                     "reggio emilia rimini imola carpi",
    "toscana": "firenze arezzo grosseto livorno lucca massa carrara pisa pistoia prato siena "
               "viareggio",
    "umbria": "perugia terni foligno",
    "marche": "ancona ascoli piceno fermo macerata pesaro urbino",
    "lazio": "roma frosinone latina rieti viterbo fiumicino guidonia",
    "abruzzo": "l aquila chieti pescara teramo",
    "molise": "campobasso isernia",
    "campania": "napoli avellino benevento caserta salerno torre del greco",
    "puglia": "bari andria barletta trani brindisi foggia lecce taranto",
    "basilicata": "potenza matera",
    "calabria": "catanzaro cosenza crotone reggio calabria vibo valentia",
    "sicilia": "palermo agrigento caltanissetta catania enna messina ragusa siracusa trapani "
               "marsala gela",
    "sardegna": "cagliari nuoro oristano sassari olbia carbonia",
}
# Le città con due parole e più: si cercano prima delle parole sole
_CITTA_MULTI = ("busto arsizio", "sesto san giovanni", "cinisello balsamo", "la spezia",
                "reggio emilia", "massa carrara", "ascoli piceno", "l aquila",
                "torre del greco", "reggio calabria", "vibo valentia")


def _norm_luogo(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z]+", " ", t).strip()
    return re.sub(r"\s+", " ", t)


def _indice_citta() -> dict[str, str]:
    out = {}
    for reg, nomi in _CITTA.items():
        resto = " " + nomi + " "
        for multi in _CITTA_MULTI:
            if f" {multi} " in resto:
                out[multi] = reg
                resto = resto.replace(f" {multi} ", " ")
        for n in resto.split():
            out[n] = reg
    return out


_INDICE_CITTA = _indice_citta()


def regione_ansa(valore: str) -> str:
    """Il nome ANSA della regione da una regione o da una città scritta per intero
    («Lombardia», «Milano», «Reggio Emilia», «Forlì»), oppure "" se non si riconosce."""
    t = _norm_luogo(valore)
    if not t:
        return ""
    if t in REGIONI:
        return REGIONI[t]
    if t in _REGIONI_ALTRE:
        return _REGIONI_ALTRE[t]
    if t.replace(" ", "") in REGIONI.values():
        return t.replace(" ", "")
    return _INDICE_CITTA.get(t, "")


def feed_regione(slug: str) -> Feed:
    return Feed(testata="ANSA", tema="locale",
                url=f"https://www.ansa.it/{slug}/notizie/{slug}_rss.xml")


def regione_di_casa(cfg) -> str:
    """Lo slug ANSA della regione di casa: `notizie_regione` («no» = nessuna), altrimenti la
    città di casa (configurazione o detta a voce, calliope/luogo.py)."""
    scelta = str(getattr(cfg, "notizie_regione", "") or "").strip()
    if scelta.lower() in ("no", "nessuna", "false", "spenta"):
        return ""
    if scelta:
        return regione_ansa(scelta)
    try:
        from ..luogo import citta_casa
        citta = citta_casa(cfg) or ""
    except Exception:  # noqa: BLE001 — senza città, nessun feed regionale
        citta = ""
    return regione_ansa(citta)


def elenco(cfg, log=None) -> list[Feed]:
    """I feed accesi di questa casa: notizie_feed e notizie_feed_extra senza le testate
    spente (salvo quelle accese per nome), più la regione di casa. Un indirizzo una volta sola."""
    spente = {_chiave(n) for n in getattr(cfg, "notizie_spente", None) or ()}
    accese = {_chiave(n) for n in getattr(cfg, "notizie_accese", None) or ()}
    out, visti = [], set()
    righe = list(getattr(cfg, "notizie_feed", None) or ()) + list(
        getattr(cfg, "notizie_feed_extra", None) or ())
    for r in righe:
        f = leggi_riga(r)
        if f is None:
            if log:
                log(f"[NOTIZIE] riga di feed non valida, la salto: «{str(r)[:80]}»")
            continue
        k = _chiave(f.testata)
        if k in spente and k not in accese:
            continue
        if f.url in visti:
            continue
        visti.add(f.url)
        out.append(f)
    slug = regione_di_casa(cfg)
    if slug:
        f = feed_regione(slug)
        if f.url not in visti:
            out.append(f)
    return out


def testate_spente(cfg) -> list[str]:
    """Le testate di notizie_feed spente in questa casa (per il registro delle capacità)."""
    spente = {_chiave(n) for n in getattr(cfg, "notizie_spente", None) or ()}
    accese = {_chiave(n) for n in getattr(cfg, "notizie_accese", None) or ()}
    out = []
    for r in getattr(cfg, "notizie_feed", None) or ():
        f = leggi_riga(r)
        if f is not None and _chiave(f.testata) in spente - accese and f.testata not in out:
            out.append(f.testata)
    return out
