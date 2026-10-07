"""
Minori in casa (05/10/2026, docs/ricerche/2026-10-05-minori.md): fasce d'età, preset, permessi
nel codice, orari, compiti e avvisi ai tutori.

Decisioni di Dario del 05/10:

- **Profilo**: nome, **data di nascita** (la fascia si ricalcola da sola), **tutori** (chi
  amministra quel profilo). Lo registra solo chi amministra, con la voce e la frase di sfida
  (`registra_utente` con `nascita`), poi parla il bambino con l'adulto presente. Il vecchio
  `giovane` (booleano) diventa la fascia «ragazzi» finché chi amministra non dice la data.
- **Fasce**: piccoli < 7, bambini 7–10, ragazzi 11–13, adolescenti 14–17 (`FASCE`). Ogni
  fascia ha un **preset** (`PRESET`): tono, fonti, internet, agenti, casa, PC, documenti,
  acquisti, compiti, orari. Chi amministra (o un tutore, per il suo minore) lo ritocca per
  persona, a voce (`minore_gestisci`) e da terminale (`python -m calliope.minori`); i ritocchi
  stanno in `memoria.db` (tabella `minori_regole`), così si vedono subito anche se cambiati
  da terminale con Calliope accesa.
- **Il preset arriva al modello come dato del turno** (`dato_turno`, come il tono: niente
  ordini nel prompt di sistema, il prefisso resta in cache) e **i permessi li fa rispettare il
  codice** (`permesso`, chiamato da `ToolRegistry.call` a ogni esecuzione, come i livelli).
- **Voce incerta tra un bambino e un altro profilo** (`piu_protetto`): vale il profilo più
  protetto, mai un adulto.
- **Compiti** (`Compiti`, tool `compiti_aiuto`): mai la soluzione, domande guida e indizi; dopo
  5 tentativi sbagliati sullo stesso esercizio si spiega, dicendo che i tutori vengono avvisati,
  e si avvisano davvero. `calcola` in modalità compiti non dà il risultato.
- **Avvisi ai tutori** (`Avvisi`): un canale solo; scheda personale sugli schermi del tutore
  subito, annuncio con il segnale quando il tutore parla a Calliope. Nel registro solo
  l'argomento, mai le frasi del minore.
- **Estensioni**: per un minore solo quelle abilitate dal tutore per lui
  (`estensione_consentita`, di partenza nessuna).
- **Privacy**: conversazioni archiviate dei minori < 14 visibili ai tutori, dai 14 solo gli
  avvisi di sicurezza (`conversazioni_visibili_ai_tutori`, GDPR art. 8 e d.lgs. 101/2018: 14
  anni in Italia); niente dati sanitari o sensibili nei ricordi di un minore
  (`ricordo_sensibile`).

Le regole sul testo qui sono vincoli di sicurezza o di permesso (principio 10): ognuna scrive
il suo nome nel registro dei turni e ha i casi contrari in prove/prova_minori.py.
"""

from __future__ import annotations

import datetime
import difflib
import json
import re
import threading
import time
import unicodedata
from .testi import MESI, NIENTE

# ─────────────────────────── fasce d'età ───────────────────────────

# (nome, da anni, a anni compresi)
FASCE = (("piccoli", 0, 6), ("bambini", 7, 10), ("ragazzi", 11, 13), ("adolescenti", 14, 17))
NOMI_FASCE = tuple(f[0] for f in FASCE)
_ORDINE = {"piccoli": 0, "bambini": 1, "ragazzi": 2, "adolescenti": 3}
# Età (anni compiuti) dalla quale un minore decide da sé chi vede le sue conversazioni: art. 8
# del GDPR, 14 anni in Italia (d.lgs. 101/2018, art. 2-quinquies)
ETA_CONSENSO = 14


def _norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s:/.-]", " ", t).split())


def leggi_data(testo) -> datetime.date | None:
    """Una data di nascita come detta o scritta: «2017-05-12», «12/5/2017», «12 maggio 2017»,
    «il 3 di marzo del 2017». None se non si capisce o è nel futuro."""
    if isinstance(testo, datetime.date):
        return testo
    t = _norm(testo)
    if not t:
        return None
    d = None
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    try:
        if m:
            d = datetime.date(int(m[1]), int(m[2]), int(m[3]))
        elif (m := re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", t)):
            d = datetime.date(int(m[3]), int(m[2]), int(m[1]))
        else:
            mesi = "|".join(MESI)
            m = re.search(r"\b(\d{1,2}|primo|1o)\s+(?:di\s+)?(" + mesi + r")\s+(?:del\s+)?(\d{4})\b", t)
            if m:
                g = 1 if m[1] in ("primo", "1o") else int(m[1])
                d = datetime.date(int(m[3]), MESI.index(m[2]) + 1, g)
    except ValueError:
        return None
    if d is None or d > datetime.date.today() or d.year < 1900:
        return None
    return d


def eta(nascita, oggi: datetime.date | None = None) -> int | None:
    """Anni compiuti a `oggi`, o None senza una data valida."""
    d = leggi_data(nascita)
    if d is None:
        return None
    oggi = oggi or datetime.date.today()
    return oggi.year - d.year - ((oggi.month, oggi.day) < (d.month, d.day))


def fascia_per_eta(anni: int | None) -> str | None:
    if anni is None:
        return None
    for nome, da, a in FASCE:
        if da <= anni <= a:
            return nome
    return None                                   # maggiorenne


def fascia(prof, oggi: datetime.date | None = None) -> str | None:
    """La fascia del profilo: dalla data di nascita (si ricalcola da sola), oppure quella
    scritta a mano (`fascia` nel profilo: il vecchio «giovane»); None = adulto o sconosciuto."""
    if prof is None:
        return None
    n = getattr(prof, "nascita", None)
    if n:
        return fascia_per_eta(eta(n, oggi))
    f = getattr(prof, "fascia", None)
    return f if f in _ORDINE else None


def e_minore(prof, oggi: datetime.date | None = None) -> bool:
    return fascia(prof, oggi) is not None


def piu_protetta(*fasce: str | None) -> str | None:
    """La fascia più protetta tra quelle date (la più giovane)."""
    f = [x for x in fasce if x in _ORDINE]
    return min(f, key=_ORDINE.get) if f else None


# ─────────────────────────── preset ───────────────────────────

# Valori:
# - tono: come parlargli, detto come un dato (dato_turno)
# - fonti: "vikidia" (Vikidia per prima, spiegazioni semplici) | "wikipedia_filtrata"
# - internet: "no" | "rigoroso" (SearXNG safesearch 2, sola lettura) | "filtrato" (safesearch 1
#   e il guardiano sulle risposte)
# - agenti: "no" | "autorizzazione" (solo con un permesso a tempo di un tutore) | "si"
# - casa: "luci_stanza" (solo le luci della sua stanza, `stanza`) | "luci_tapparelle" |
#   "senza_clima" (come un familiare, senza riscaldamento e clima) | "familiare"
# - pc, acquisti: "no" | "si";   documenti: "no" | "scuola" | "si"
# - compiti: "guida" (mai la soluzione; dopo `minori_compiti_tentativi` si spiega e si
#   avvisano i tutori) | "libero" (solo 14–17, se il tutore lo sceglie)
# - orari: fasce in cui Calliope non risponde, ["21:00-07:30", …]; di partenza nessuna: le
#   decidono i tutori
PRESET: dict[str, dict] = {
    "piccoli": {
        "tono": "è un bambino piccolo: frasi cortissime e parole semplicissime, tono dolce e "
                "allegro, un esempio concreto",
        "fonti": "vikidia", "internet": "no", "agenti": "no", "casa": "luci_stanza",
        "pc": "no", "documenti": "no", "acquisti": "no", "compiti": "guida", "orari": []},
    "bambini": {
        "tono": "è un bambino delle elementari: frasi brevi e parole semplici, tono allegro e "
                "incoraggiante, esempi concreti",
        "fonti": "vikidia", "internet": "no", "agenti": "no", "casa": "luci_tapparelle",
        "pc": "no", "documenti": "no", "acquisti": "no", "compiti": "guida", "orari": []},
    "ragazzi": {
        "tono": "è un ragazzo delle medie: parole semplici ma non infantili, tono amichevole",
        "fonti": "vikidia", "internet": "rigoroso", "agenti": "autorizzazione",
        "casa": "senza_clima", "pc": "no", "documenti": "scuola", "acquisti": "no",
        "compiti": "guida", "orari": []},
    "adolescenti": {
        "tono": "è un adolescente: tono amichevole e diretto, da pari a pari, senza prediche",
        "fonti": "wikipedia_filtrata", "internet": "filtrato", "agenti": "si",
        "casa": "familiare", "pc": "si", "documenti": "si", "acquisti": "si",
        "compiti": "guida", "orari": []},
}
# Valori ammessi per ogni chiave (ritocchi a voce e da terminale)
VALORI: dict[str, tuple] = {
    "fonti": ("vikidia", "wikipedia_filtrata"),
    "internet": ("no", "rigoroso", "filtrato"),
    "agenti": ("no", "autorizzazione", "si"),
    "casa": ("no", "luci_stanza", "luci_tapparelle", "senza_clima", "familiare"),
    "pc": ("no", "si"), "documenti": ("no", "scuola", "si"), "acquisti": ("no", "si"),
    "compiti": ("guida", "libero"),
}
# Gli ospiti: un ospite può essere un bambino. Filtro «moderato» del guardiano, niente
# avvisi (non ha tutori), la protezione sì
OSPITE = {"guardiano": "moderato"}

# Compiti «libero» solo da 14 anni: sotto, per decisione di Dario, la soluzione non si dà mai
# prima dei 5 tentativi. Dai 14 il tutore può scegliere (motivo nel rapporto: a quell'età serve
# anche controllare uno svolgimento intero, e l'art. 8 del GDPR riconosce già un'autonomia)
COMPITI_LIBERO_DA = "adolescenti"


def _orari_validi(valore) -> list[str]:
    out = []
    for parte in (valore if isinstance(valore, (list, tuple)) else re.split(r"[,;]", str(valore or ""))):
        m = re.fullmatch(r"\s*(\d{1,2})[:.]?(\d{2})?\s*-\s*(\d{1,2})[:.]?(\d{2})?\s*", str(parte))
        if not m:
            continue
        h1, m1, h2, m2 = int(m[1]), int(m[2] or 0), int(m[3]), int(m[4] or 0)
        if h1 < 24 and h2 < 24 and m1 < 60 and m2 < 60:
            out.append(f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}")
    return out


def controlla_valore(chiave: str, valore, fascia_: str | None = None):
    """Il valore normalizzato per un ritocco, o solleva ValueError con la frase da dire."""
    chiave = str(chiave or "").strip().lower()
    if chiave == "orari":
        v = _orari_validi(valore)
        if str(valore or "").strip().lower() in ("", "nessuno", "no", "niente"):
            return []
        if not v:
            raise ValueError("gli orari vanno detti come «21:00-07:30»")
        return v
    if chiave == "stanza":
        return str(valore or "").strip().lower()[:40]
    if chiave == "estensioni":
        return sorted({_norm(x).replace(" ", "_") for x in
                       (valore if isinstance(valore, list) else re.split(r"[,;]", str(valore or "")))
                       if _norm(x)})
    if chiave == "gioco_minuti":
        # Minuti di gioco al giorno sugli schermi (05/10): «45», «un'ora» no (cifre)
        m = re.search(r"\d+", str(valore or ""))
        if not m or not 0 <= int(m.group(0)) <= 600:
            raise ValueError("i minuti di gioco al giorno vanno detti in cifre, da 0 a 600")
        return int(m.group(0))
    if chiave not in VALORI:
        raise ValueError(f"non conosco l'impostazione «{chiave}»")
    v = _norm(valore).replace(" ", "_").replace("sì", "si")
    v = {"sì": "si", "true": "si", "false": "no"}.get(v, v)
    if v not in VALORI[chiave]:
        raise ValueError(f"per «{chiave}» vanno bene: {', '.join(VALORI[chiave])}")
    if chiave == "compiti" and v == "libero" and fascia_ is not None and \
            _ORDINE.get(fascia_, 0) < _ORDINE[COMPITI_LIBERO_DA]:
        raise ValueError("sotto i 14 anni i compiti restano guidati")
    return v


# ─────────────────────────── regole per persona (SQLite) ───────────────────────────

class Regole:
    """I ritocchi del preset per persona, gli orari, le estensioni abilitate e le
    autorizzazioni a tempo, in memoria.db (tabella `minori_regole`). Un file solo per tutti i
    processi: il terminale li cambia con Calliope accesa (cache di 5 s)."""

    def __init__(self, path: str):
        from .persistenza import apri_db, prepara_schema
        self._lock = threading.Lock()
        self.db = apri_db(path)

        def v1(db):
            db.execute("CREATE TABLE IF NOT EXISTS minori_regole (persona TEXT PRIMARY KEY, "
                       "dati TEXT NOT NULL, aggiornato TEXT NOT NULL)")
        self.scrivibile = prepara_schema(self.db, "minori", [v1])
        self._cache: dict[str, tuple[float, dict]] = {}

    def leggi(self, persona: str) -> dict:
        if not persona:
            return {}
        now = time.monotonic()
        with self._lock:
            c = self._cache.get(persona)
            if c and now - c[0] < 5.0:
                return dict(c[1])
            row = self.db.execute("SELECT dati FROM minori_regole WHERE persona = ?",
                                  (persona,)).fetchone()
            try:
                dati = json.loads(row[0]) if row else {}
            except (TypeError, ValueError):
                dati = {}
            self._cache[persona] = (now, dati)
            return dict(dati)

    def scrivi(self, persona: str, dati: dict):
        with self._lock:
            self.db.execute(
                "INSERT INTO minori_regole (persona, dati, aggiornato) VALUES (?, ?, ?) "
                "ON CONFLICT(persona) DO UPDATE SET dati = excluded.dati, "
                "aggiornato = excluded.aggiornato",
                (persona, json.dumps(dati, ensure_ascii=False),
                 datetime.datetime.now().isoformat(timespec="seconds")))
            self.db.commit()
            self._cache.pop(persona, None)

    def imposta(self, persona: str, chiave: str, valore):
        dati = self.leggi(persona)
        if valore is None:
            dati.pop(chiave, None)
        else:
            dati[chiave] = valore
        self.scrivi(persona, dati)
        return dati

    def autorizza(self, persona: str, cosa: str, minuti: float, da: str):
        dati = self.leggi(persona)
        aut = dict(dati.get("autorizzazioni") or {})
        aut[cosa] = {"fino": time.time() + max(1.0, float(minuti)) * 60, "da": da}
        dati["autorizzazioni"] = aut
        self.scrivi(persona, dati)

    def autorizzato(self, persona: str, cosa: str) -> bool:
        a = (self.leggi(persona).get("autorizzazioni") or {}).get(cosa)
        return bool(a) and float(a.get("fino", 0)) > time.time()

    def close(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass


# Il servizio del processo (lo prepara main.py con `prepara`): le funzioni qui sotto lo usano
# per leggere i ritocchi. Senza (prove, terminale) valgono i preset.
_SERVIZIO: dict = {"regole": None, "avvisi": None, "compiti": None, "cfg": None,
                   "gioco": None, "richieste": None}


def prepara(cfg, schermi=None, registry=None, log=print) -> dict:
    """Apre regole, avvisi e compiti sul file della memoria. Da main.py all'avvio."""
    path = getattr(cfg, "memory_db", "memoria.db")
    _SERVIZIO["cfg"] = cfg
    _SERVIZIO["regole"] = Regole(path)
    _SERVIZIO["avvisi"] = Avvisi(path, schermi=schermi, registry=registry, log=log)
    _SERVIZIO["compiti"] = Compiti(cfg)
    # Tempo di gioco e richieste ai tutori (05/10, giochi): stesso file
    _SERVIZIO["gioco"] = TempoGioco(path)
    _SERVIZIO["richieste"] = Richieste(path, cfg, registry=registry, log=log)
    return _SERVIZIO


def tempo_gioco() -> "TempoGioco | None":
    return _SERVIZIO.get("gioco")


def richieste() -> "Richieste | None":
    return _SERVIZIO.get("richieste")


def regole() -> Regole | None:
    return _SERVIZIO.get("regole")


def avvisi() -> "Avvisi | None":
    return _SERVIZIO.get("avvisi")


def compiti() -> "Compiti":
    if _SERVIZIO.get("compiti") is None:
        _SERVIZIO["compiti"] = Compiti(_SERVIZIO.get("cfg"))
    return _SERVIZIO["compiti"]


def preset(prof, oggi: datetime.date | None = None, reg: Regole | None = None) -> dict | None:
    """Il preset in vigore per il profilo (fascia + ritocchi), o None per un adulto."""
    cfg = _SERVIZIO.get("cfg")
    if cfg is not None and not getattr(cfg, "minori_enabled", True):
        return None
    f = fascia(prof, oggi)
    if f is None:
        return None
    out = dict(PRESET[f])
    out["fascia"] = f
    out["eta"] = eta(getattr(prof, "nascita", None), oggi)
    reg = reg if reg is not None else regole()
    rit = reg.leggi(getattr(prof, "id", "")) if reg is not None else {}
    out["gioco_minuti"] = gioco_minuti_fascia(f)
    for k, v in (rit or {}).items():
        if k in VALORI or k in ("orari", "stanza", "estensioni", "gioco_minuti"):
            if k == "compiti" and v == "libero" and _ORDINE[f] < _ORDINE[COMPITI_LIBERO_DA]:
                continue                    # sotto i 14: guidati comunque
            out[k] = v
    out.setdefault("estensioni", [])
    out.setdefault("stanza", "")
    return out


# ─────────────────────────── chi parla ───────────────────────────

def profilo(ctx):
    """Il profilo di chi parla (o None: ospite)."""
    sc = getattr(ctx, "speaker_ctx", None)
    name = getattr(sc, "current_speaker", None)
    speakers = getattr(ctx, "speakers", None)
    try:
        return speakers.get(name) if (name and speakers is not None) else None
    except Exception:  # noqa: BLE001
        return None


def tutori(prof, registry) -> list:
    """I profili dei tutori (per id); senza tutori, chi amministra la casa."""
    ids = list(getattr(prof, "tutori", None) or [])
    users = list(getattr(registry, "users", {}).values()) if registry is not None else []
    out = [u for u in users if getattr(u, "id", None) in ids]
    if not out:
        out = [u for u in users if getattr(u, "admin", False)]
    return out


def e_tutore(chi, minore) -> bool:
    """`chi` è un tutore di `minore` (o, se il minore non ne ha, chi amministra)."""
    if chi is None or minore is None:
        return False
    ids = list(getattr(minore, "tutori", None) or [])
    if ids:
        return getattr(chi, "id", None) in ids
    return bool(getattr(chi, "admin", False))


def conversazioni_visibili_ai_tutori(prof, oggi: datetime.date | None = None) -> bool:
    """Le conversazioni archiviate di questo profilo si possono mostrare ai tutori? Sì per i
    minori sotto i 14 anni; dai 14 solo gli avvisi di sicurezza (art. 8 GDPR). Per la fase 2
    del contesto (archivio delle conversazioni, ramo contesto-2)."""
    f = fascia(prof, oggi)
    if f is None:
        return False
    anni = eta(getattr(prof, "nascita", None), oggi)
    if anni is None:
        return _ORDINE[f] < _ORDINE["adolescenti"]
    return anni < ETA_CONSENSO


def estensione_consentita(prof, estensione: str, oggi: datetime.date | None = None) -> bool:
    """Un'estensione si può usare da questo profilo? Adulti sì; un minore solo se un tutore
    l'ha abilitata per lui (di partenza nessuna). Per calliope/estensioni (ramo
    estensioni-rete) e per ToolRegistry.call (tool est_<nome>)."""
    p = preset(prof, oggi)
    if p is None:
        return True
    nome = _norm(estensione).replace(" ", "_")
    return nome in set(p.get("estensioni") or ())


def dati_verso_internet(prof, estensione: str | None = None) -> bool:
    """I dati di questo profilo possono uscire verso internet (estensioni con la rete)? Per
    un minore solo con un'estensione abilitata apposta per lui."""
    if not e_minore(prof):
        return True
    return bool(estensione) and estensione_consentita(prof, estensione)


def safesearch(prof) -> int:
    """SafeSearch di SearXNG per chi parla: 2 (rigoroso) per i ragazzi, 1 altrimenti."""
    p = preset(prof)
    return 2 if p is not None and p.get("internet") == "rigoroso" else 1


# ─────────────────────────── orari ───────────────────────────

def fuori_orario(prof, adesso: datetime.datetime | None = None) -> str | None:
    """La fascia oraria in cui Calliope non risponde a questo minore, se adesso ci cade. Con
    un'eccezione concessa da un tutore (richiesta approvata, 05/10) per un po' no."""
    p = preset(prof)
    if not p:
        return None
    reg = regole()
    if reg is not None and reg.autorizzato(getattr(prof, "id", ""), "orari"):
        return None
    adesso = adesso or datetime.datetime.now()
    minuti = adesso.hour * 60 + adesso.minute
    for o in _orari_validi(p.get("orari") or []):
        a, b = o.split("-")
        ma = int(a[:2]) * 60 + int(a[3:])
        mb = int(b[:2]) * 60 + int(b[3:])
        dentro = ma <= minuti < mb if ma <= mb else (minuti >= ma or minuti < mb)
        if dentro:
            return o
    return None


def frase_fuori_orario(prof, orario: str) -> str:
    fine = orario.split("-")[1]
    return (f"Adesso è l'ora di riposare dagli schermi e dalle voci: ne riparliamo dopo le "
            f"{fine.lstrip('0') or '0'}. Se hai bisogno, chiama un adulto.")


# ─────────────────────────── dato del turno ───────────────────────────

def dato_turno(prof, cfg=None) -> str:
    """Il preset come dato su chi parla, dentro i dati del turno (Brain._turn_context): come il
    tono, un dato e non un ordine (misura del 04/10: gli ordini nel contesto toglievano le
    chiamate dei tool). "" per un adulto."""
    p = preset(prof)
    if p is None:
        return ""
    anni = p.get("eta")
    chi = f"{anni} anni" if anni is not None else {"piccoli": "meno di 7 anni",
                                                   "bambini": "7–10 anni",
                                                   "ragazzi": "11–13 anni",
                                                   "adolescenti": "14–17 anni"}[p["fascia"]]
    tono = p["tono"]
    if getattr(prof, "gender", None) == "f":
        for a, b in (("un bambino piccolo", "una bambina piccola"), ("un bambino", "una bambina"),
                     ("un ragazzo", "una ragazza"), ("un adolescente", "un'adolescente")):
            tono = tono.replace(a, b)
    parti = [f"minorenne, {chi}: {tono}",
             "argomenti difficili (morte, guerra, droghe, corpo) spiegati adatti alla sua età, "
             "niente contenuti per adulti"]
    if p.get("compiti") == "guida":
        parti.append("compiti: guida (per i compiti di scuola mai la soluzione: domande "
                     "guida e indizi, con compiti_aiuto)")
        # L'esercizio aperto (banco del 05/10: dopo la prima risposta il 26B controllava da sé
        # i tentativi senza richiamare compiti_aiuto, e i 5 tentativi non si contavano mai)
        aperto = compiti().aperto(getattr(prof, "id", ""))
        if aperto is not None:
            parti.append(f"esercizio aperto: «{aperto['testo']}», risposte sbagliate "
                         f"{aperto['tentativi']} su {compiti().massimo} (ogni risposta che "
                         f"dice va controllata con compiti_aiuto)")
    return "; ".join(parti)


# ─────────────────────────── permessi nel codice ───────────────────────────

# Frasi pronte per i rifiuti (risposta_finale: niente altra passata del modello)
FRASI = {
    "internet": "Su internet per te non cerco: chiedimelo in un altro modo, o chiedi a un adulto.",
    "agenti": "Questo è un lavoro lungo che per te può far partire solo un adulto: chiedilo a "
              "{tutore}.",
    "autorizzazione": "Per questo serve il permesso di un adulto: chiedi a {tutore} di dirmi "
                      "che va bene.",
    "pc": "Il computer per te non lo comando: chiedi a un adulto.",
    "documenti": "Documenti e file per te non li preparo: chiedi a un adulto.",
    "acquisti": "Acquisti e pagamenti per te no: chiedi a un adulto.",
    "casa": "Questo in casa lo può fare un adulto: chiediglielo.",
    "estensione": "Questa funzione per te non è abilitata: può abilitarla {tutore}.",
    "ufficio": "Fatture, rubrica e documenti di casa per te no.",
    "admin": "Questo lo può chiedere solo un adulto che amministra Calliope.",
}

# Tool → chiave del preset
_TOOL_CHIAVE = {
    "web_cerca": "internet",
    "delega_lavoro": "agenti", "lavori_rispondi": "agenti", "risultato_lavoro": "agenti",
    "documento_crea": "documenti", "documento_modifica": "documenti",
}
_UFFICIO = {"modello_compila", "anagrafica_cerca", "anagrafica_salva", "archivio_cerca",
            "archivio_scadenze", "archivio_somma",
            # «archivialo» porta un file o una foto nei documenti di casa (05/10, allegati)
            "allegato_archivia", "immagine_archivia"}
_SOLO_ADULTI = {"estensione_crea", "estensioni_gestisci", "installa_proponi", "installa_avvia",
                "registra_utente", "schermo_gestisci"}


def _tutore_nome(prof, registry) -> str:
    t = [getattr(u, "name", "") for u in tutori(prof, registry)]
    t = [x for x in t if x]
    if not t:
        return "un adulto"
    return t[0] if len(t) == 1 else ", ".join(t[:-1]) + " o " + t[-1]


def _rifiuto(ctx, motivo: str, regola: str, **fmt) -> dict:
    from .tools.spec import note_rule
    note_rule(ctx, regola)
    frase = FRASI[motivo].format(**fmt)
    return {"ok": False, "fatto": NIENTE, "motivo": "chi parla è minorenne: il preset non "
            "lo permette", "per_il_resto": "per le altre richieste chiama i tool come sempre",
            "conferma": frase, "risposta_finale": frase}


def permesso(ctx, nome: str, argomenti: dict | None = None) -> dict | None:
    """Il rifiuto da dare se chi parla è un minore e il suo preset non permette il tool; None
    se va bene (anche per gli adulti e gli ospiti: lì decidono i livelli). Lo chiama
    ToolRegistry.call dopo il controllo del livello, a ogni esecuzione."""
    prof = profilo(ctx)
    p = preset(prof) if prof is not None else None
    if p is None:
        return None
    reg = regole()
    speakers = getattr(ctx, "speakers", None)
    tutore = _tutore_nome(prof, speakers)
    if nome in _SOLO_ADULTI:
        return _rifiuto(ctx, "admin", "minore_solo_adulti")
    if nome in _UFFICIO:
        return _rifiuto(ctx, "ufficio", "minore_ufficio")
    if nome.startswith("est_"):
        if not estensione_consentita(prof, nome[4:]):
            out = _rifiuto(ctx, "estensione", "minore_estensione", tutore=tutore)
            # La richiesta resta in sospeso per il tutore (05/10, Richieste): la sente alla
            # sua prossima frase, con la scheda sui suoi schermi
            return _chiesta(ctx, out, prof, "estensione", nome[4:], tutore)
        return None
    if nome.startswith("pc_") and p.get("pc") != "si":
        return _rifiuto(ctx, "pc", "minore_pc")
    if nome in ("immagine_guarda",):
        return None
    chiave = _TOOL_CHIAVE.get(nome)
    if chiave is None:
        return None
    valore = p.get(chiave)
    if chiave == "internet":
        return _rifiuto(ctx, "internet", "minore_internet") if valore == "no" else None
    if chiave == "agenti":
        if valore == "no":
            return _rifiuto(ctx, "agenti", "minore_agenti", tutore=tutore)
        if valore == "autorizzazione" and not (reg is not None and reg.autorizzato(prof.id, "agenti")):
            out = _rifiuto(ctx, "autorizzazione", "minore_autorizzazione", tutore=tutore)
            return _chiesta(ctx, out, prof, "agenti", "agenti", tutore)
        return None
    if chiave == "documenti":
        return _rifiuto(ctx, "documenti", "minore_documenti") if valore == "no" else None
    return None


def _chiesta(ctx, out: dict, prof, tipo: str, oggetto: str, tutore: str) -> dict:
    """Il rifiuto con la richiesta al tutore messa in sospeso (una sola per cosa: se c'è già,
    lo dice e basta)."""
    r = richieste()
    if r is None:
        return out
    try:
        _, nuova = r.crea(prof, tipo, oggetto, registry=getattr(ctx, "speakers", None))
    except Exception:  # noqa: BLE001 — la richiesta non deve rompere il rifiuto
        return out
    from .tools.spec import note_rule
    note_rule(ctx, "minore_richiesta_tutore")
    frase = out["risposta_finale"].rstrip(".") + (
        f". L'ho chiesto a {tutore}: ti dico appena risponde." if nuova else
        f". L'ho già chiesto a {tutore}: aspettiamo la risposta.")
    out.update(conferma=frase, risposta_finale=frase, richiesta_tutore=True)
    return out


# Nota per lo scrittore dei documenti e per l'agente quando chiede un minore con i compiti
# guidati: decide il modello se la richiesta è un compito (niente parole chiave)
NOTA_COMPITI_DOCUMENTO = (" (Chi lo chiede è minorenne. Se è un compito di scuola, come un tema, "
                          "un riassunto o una ricerca, prepara solo una scaletta con domande "
                          "guida e spazi da completare, mai il testo svolto.)")
NOTA_SCUOLA = (" (Chi lo chiede è un ragazzo delle medie: solo documenti per la scuola, scritti "
               "in modo semplice.)")


def nota_documento(ctx) -> str:
    """Il testo da aggiungere alla richiesta di un documento o di un lavoro dell'agente
    chiesto da un minore ("" per gli adulti)."""
    p = preset(profilo(ctx))
    if p is None:
        return ""
    from .tools.spec import note_rule
    out = ""
    if p.get("compiti") == "guida":
        out += NOTA_COMPITI_DOCUMENTO
        note_rule(ctx, "minore_compiti_scaletta")
    if p.get("documenti") == "scuola":
        out += NOTA_SCUOLA
    return out


# Casa: cosa può comandare un minore (dopo le regole di Calliope, regole.py)
_CLIMA = {"climate", "water_heater", "humidifier", "fan"}
_TAPPARELLE = {"shutter", "blind", "curtain", "shade", "awning", "window"}


def casa_consentita(prof, entita) -> bool:
    """Il minore può comandare questa entità? (La lettura resta sempre.)"""
    p = preset(prof)
    if p is None:
        return True
    modo = p.get("casa") or "no"
    dom = getattr(entita, "dominio", "")
    if modo == "familiare":
        return True
    if modo == "senza_clima":
        return dom not in _CLIMA
    if modo == "luci_tapparelle":
        return dom == "light" or (dom == "cover" and (getattr(entita, "classe", None) or "")
                                  in _TAPPARELLE)
    if modo == "luci_stanza":
        stanza = _norm(p.get("stanza") or "")
        return dom == "light" and bool(stanza) and _norm(getattr(entita, "area", "") or "") == stanza
    return False


# ─────────────────────────── ricordi sensibili ───────────────────────────

# Dati sanitari e sensibili (art. 9 GDPR) che un minore dice di sé: non si salvano da soli
# nei ricordi. Vincolo di privacy (principio 10): l'effetto è un ricordo non salvato e detto.
_SENSIBILE = re.compile(
    r"\b(malat\w*|farmac\w*|medicin\w*|pastigli\w*|diagnos\w*|terapi\w*|psicolog\w*|"
    r"psichiatr\w*|ansia|ansios\w*|depress\w*|autolesion\w*|tagli[oa] (?:sul|sulle|sui)|"
    r"anoressi\w*|bulimi\w*|allergi\w*|asma|diabet\w*|epiless\w*|adhd|autis\w*|dislessi\w*|"
    r"disturb\w*|ricover\w*|ospedal\w*|operat[oa] (?:al|alla|di)|"
    r"religion\w*|musulman\w*|ebre\w*|gay|lesbic\w*|omosessual\w*|bisessual\w*|transgender|"
    r"fidanzat\w*|incinta|mestru\w*|ciclo mestruale|"
    r"divorzi\w*|separat[ie] |in carcere|arrestat\w*|assistenti sociali|"
    r"password|codice fiscale|indirizzo di casa)\b", re.I)


def ricordo_sensibile(fatto: str) -> bool:
    """Il fatto contiene dati sanitari o sensibili (per i ricordi di un minore)."""
    return bool(_SENSIBILE.search(fatto or ""))


# ─────────────────────────── contenuti adulti (regole fisse) ───────────────────────────

# Voci della biblioteca e risultati di internet per adulti: per un minore non si usano né si
# mostrano sugli schermi (terzo strato della sicurezza dei contenuti, rapporto §4). Vincolo di
# sicurezza (principio 10): decide solo se un testo arriva a un minore; il guardiano giudica
# poi la frase vera. Parole intere e composti chiari: «sesso» da solo no (riproduzione delle
# piante, «sesso del gatto»), «Sesto San Giovanni» no.
_ADULTO = re.compile(
    r"\b(porn\w*|pornograf\w*|erotic\w*|erotism\w*|hard ?core|xxx|prostitu\w*|escort|"
    r"pedofil\w*|pedopornograf\w*|incest\w*|stupr\w*|violenza sessuale|abus\w* sessual\w*|"
    r"rapporto sessuale|rapporti sessuali|atto sessuale|atti sessuali|posizioni sessuali|"
    r"sesso orale|sesso anale|masturba\w*|orgasm\w*|fetic\w*|bdsm|sadomaso\w*|"
    r"sex ?toy|vibrator\w*|camgirl|onlyfans|nud[oia] integrale|"
    r"gioco d'azzardo online|scommesse online|"
    r"suicid\w* (?:assistito|metodi|come)|metodi di suicidio|"
    r"decapitazion\w*|smembramento|snuff|gore)\b", re.I)


def contenuto_adulto(*testi) -> bool:
    """Il testo (titolo di una voce, risultato di internet) è per adulti."""
    return any(_ADULTO.search(str(t or "")) for t in testi)


def filtra_per_minore(ctx, elementi: list, testi) -> list:
    """Gli elementi adatti a chi parla: per un minore senza quelli per adulti (`testi(e)` dà i
    testi da controllare); per gli adulti tutti. Regola `minore_contenuto_adulto`."""
    if preset(profilo(ctx)) is None:
        return elementi
    tenuti = [e for e in elementi if not contenuto_adulto(*testi(e))]
    if len(tenuti) < len(elementi):
        from .tools.spec import note_rule
        note_rule(ctx, "minore_contenuto_adulto")
    return tenuti


# ─────────────────────────── voce incerta ───────────────────────────

def piu_protetto(registry, emb, nome: str | None, come: str | None, punteggio: float,
                 cfg) -> str | None:
    """Il minore che deve valere per questa frase, se la voce è incerta tra lui e un altro
    profilo (o non riconosciuta ma vicina a lui); None se la decisione di main.py resta.

    - nessun riconoscimento, zona grigia o voce «sicura» di un adulto, ma un minore ha un
      punteggio almeno nella zona grigia (soglia − speaker_id_session_margin) e, per l'adulto
      riconosciuto, a meno di `minori_margine_ambiguo` dal migliore: vale il minore (tra più
      minori, il più protetto);
    - una frase breve (vale chi parlava) cambia solo se un minore supera la soglia piena.
    Mai il contrario: una voce incerta non diventa mai un adulto."""
    if registry is None or emb is None or not getattr(cfg, "minori_enabled", True):
        return None
    import numpy as np
    thr = float(getattr(cfg, "speaker_id_threshold", 0.48))
    grigia = thr - float(getattr(cfg, "speaker_id_session_margin", 0.06))
    ambiguo = float(getattr(cfg, "minori_margine_ambiguo", 0.05))
    attuale = registry.get(nome) if nome else None
    if attuale is not None and e_minore(attuale):
        return None                           # è già un minore
    candidati = []
    for n, p in getattr(registry, "users", {}).items():
        vp = getattr(p, "voiceprint", None)
        if vp is None or not e_minore(p):
            continue
        s = float(np.dot(emb, vp))
        candidati.append((n, p, s))
    if not candidati:
        return None
    if come == "breve":
        vicini = [c for c in candidati if c[2] >= thr]
    elif come == "voce" and attuale is not None:
        vicini = [c for c in candidati if c[2] >= grigia and punteggio - c[2] < ambiguo]
    else:
        vicini = [c for c in candidati if c[2] >= grigia]
    if not vicini:
        return None
    f = piu_protetta(*(fascia(c[1]) for c in vicini))
    scelti = [c for c in vicini if fascia(c[1]) == f]
    return max(scelti, key=lambda c: c[2])[0]


# ─────────────────────────── impronta da rifare ───────────────────────────

def impronta_da_rifare(prof, oggi: datetime.date | None = None, soglia: float = 0.48,
                       cfg=None) -> str | None:
    """Il motivo per rifare l'impronta di un minore (la voce cambia in fretta), o None:
    vecchia di 6 mesi sotto i 14 anni, di 12 dai 14 (`minori_impronta_mesi`), oppure il
    riconoscimento medio delle ultime frasi sotto soglia + 0,05."""
    f = fascia(prof, oggi)
    if f is None or getattr(prof, "voiceprint", None) is None:
        return None
    oggi = oggi or datetime.date.today()
    mesi = getattr(cfg, "minori_impronta_mesi", None) or [6, 12]
    limite = int(mesi[0] if _ORDINE[f] < _ORDINE["adolescenti"] else mesi[-1])
    fatta = leggi_data(getattr(prof, "impronta_data", None))
    if fatta is not None and (oggi - fatta).days >= limite * 30.4:
        return f"la registrazione della voce ha più di {limite} mesi"
    media = getattr(prof, "riconoscimento", None)
    if isinstance(media, (int, float)) and media < soglia + 0.05:
        return "la riconosco sempre meno bene"
    return None


# ─────────────────────────── compiti ───────────────────────────

class Compiti:
    """Gli esercizi di un minore nella conversazione e i suoi tentativi (per id del profilo),
    in memoria: un esercizio vale 2 ore. Dopo `minori_compiti_tentativi` risposte sbagliate
    sullo stesso esercizio la soluzione si può spiegare, e i tutori vengono avvisati."""

    DURATA_S = 2 * 3600
    ATTIVA_S = 30 * 60            # «modalità compiti»: un esercizio aperto da meno di così

    def __init__(self, cfg=None):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._esercizi: dict[str, list[dict]] = {}

    @property
    def massimo(self) -> int:
        return int(getattr(self.cfg, "minori_compiti_tentativi", 5) or 5)

    def _pulisci(self, persona: str):
        ora = time.time()
        self._esercizi[persona] = [e for e in self._esercizi.get(persona, [])
                                   if ora - e["quando"] < self.DURATA_S]

    def trova(self, persona: str, esercizio: str, espressione: str = "") -> dict | None:
        key = _norm(esercizio)
        expr = re.sub(r"\s+", "", espressione or "")
        with self._lock:
            self._pulisci(persona)
            best, score = None, 0.0
            for e in self._esercizi.get(persona, []):
                if expr and e.get("espressione") == expr:
                    return e
                s = difflib.SequenceMatcher(None, key, e["chiave"]).ratio()
                if s > score:
                    best, score = e, s
            return best if score >= 0.72 else None

    def apri(self, persona: str, esercizio: str, espressione: str = "") -> dict:
        e = self.trova(persona, esercizio, espressione)
        if e is not None:
            if espressione and not e.get("espressione"):
                e["espressione"] = re.sub(r"\s+", "", espressione)
            e["quando"] = time.time()
            return e
        e = {"testo": str(esercizio or "").strip()[:120], "chiave": _norm(esercizio),
             "espressione": re.sub(r"\s+", "", espressione or ""), "tentativi": 0,
             "risolto": False, "spiegato": False, "quando": time.time(), "avvisato": False}
        with self._lock:
            self._esercizi.setdefault(persona, []).append(e)
        return e

    def attiva(self, persona: str) -> bool:
        """C'è un esercizio aperto e non risolto da poco (modalità compiti)."""
        ora = time.time()
        with self._lock:
            return any(not e["risolto"] and not e["spiegato"] and ora - e["quando"] < self.ATTIVA_S
                       for e in self._esercizi.get(persona, []))

    def aperto(self, persona: str) -> dict | None:
        """L'ultimo esercizio aperto e non risolto (modalità compiti), o None."""
        ora = time.time()
        with self._lock:
            aperti = [e for e in self._esercizi.get(persona, []) if not e["risolto"]
                      and not e["spiegato"] and ora - e["quando"] < self.ATTIVA_S]
        return max(aperti, key=lambda e: e["quando"]) if aperti else None

    def chiudi(self, persona: str):
        with self._lock:
            self._esercizi.pop(persona, None)


# ─────────────────────────── avvisi ai tutori ───────────────────────────

class Avvisi:
    """Il canale unico verso i tutori: un avviso per tutore in memoria.db (tabella
    `avvisi_tutori`), scheda personale subito sugli schermi del tutore, annuncio con il
    segnale alla prima frase del tutore riconosciuta dalla voce (main.py, `da_dire`). Nel
    testo solo l'argomento («ha parlato di farsi del male»), mai le frasi del minore. I
    compiti finiscono anche nel riepilogo del giorno (`riepilogo`)."""

    def __init__(self, path: str, schermi=None, registry=None, log=print):
        from .persistenza import apri_db, prepara_schema
        self._lock = threading.Lock()
        self.db = apri_db(path)
        self.schermi = schermi
        self.registry = registry
        self.log = log

        def v1(db):
            db.execute("CREATE TABLE IF NOT EXISTS avvisi_tutori (id INTEGER PRIMARY KEY, "
                       "tutore TEXT NOT NULL, minore TEXT NOT NULL, tipo TEXT NOT NULL, "
                       "testo TEXT NOT NULL, urgente INTEGER NOT NULL DEFAULT 0, "
                       "creato TEXT NOT NULL, detto TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS avvisi_tutori_t ON avvisi_tutori(tutore, detto)")
            db.execute("CREATE TABLE IF NOT EXISTS compiti_giorno (minore TEXT NOT NULL, "
                       "giorno TEXT NOT NULL, argomento TEXT NOT NULL, aiuti INTEGER NOT NULL "
                       "DEFAULT 0, soluzioni INTEGER NOT NULL DEFAULT 0, "
                       "PRIMARY KEY (minore, giorno, argomento))")
        self.scrivibile = prepara_schema(self.db, "avvisi_tutori", [v1])

    def manda(self, minore, tipo: str, testo: str, urgente: bool = False,
              registry=None, non_ripetere_s: float = 0.0) -> int:
        """Un avviso a tutti i tutori del minore. Restituisce quanti tutori, oppure -1 se
        `non_ripetere_s` > 0 e lo stesso avviso (stesso minore, tipo e testo, cioè lo stesso
        argomento) è partito da meno di tanti secondi: una frase spezzata in due turni, o la
        stessa cosa ridetta subito, è lo stesso episodio (prova e2e del 06/10: due avvisi
        «sicurezza» per Sofia a un secondo l'uno dall'altro). Il controllo e la scrittura sono
        sotto lo stesso lucchetto (due corsie insieme non mandano due avvisi). Un argomento
        diverso parte sempre: non si perde mai un avviso nuovo."""
        registry = registry or self.registry
        dest = tutori(minore, registry)
        adesso = datetime.datetime.now()
        ora = adesso.isoformat(timespec="seconds")
        with self._lock:
            if non_ripetere_s and non_ripetere_s > 0:
                da = (adesso - datetime.timedelta(seconds=float(non_ripetere_s))).isoformat(
                    timespec="seconds")
                gia = self.db.execute("SELECT 1 FROM avvisi_tutori WHERE minore = ? AND "
                                      "tipo = ? AND testo = ? AND creato >= ? AND "
                                      "tutore != minore LIMIT 1",
                                      (minore.id, tipo, testo, da)).fetchone()
                if gia:
                    self.log(f"   [MINORI] avviso «{tipo}» per {minore.name} già mandato da "
                             f"meno di {int(non_ripetere_s)} s: non lo ripeto")
                    return -1
            for t in dest:
                self.db.execute("INSERT INTO avvisi_tutori (tutore, minore, tipo, testo, "
                                "urgente, creato) VALUES (?, ?, ?, ?, ?, ?)",
                                (t.id, minore.id, tipo, testo, int(urgente), ora))
            self.db.commit()
        self.log(f"   [MINORI] avviso «{tipo}» per {minore.name} a "
                 f"{', '.join(t.name for t in dest) or 'nessuno'}")
        for t in dest:
            self._scheda(t, minore, testo, urgente)
        return len(dest)

    def _scheda(self, tutore, minore, testo: str, urgente: bool):
        hub = self.schermi
        if hub is None:
            return
        try:
            from .schermi import schede
            from .schermi.hub import Mittente
            card = schede.nuova("testo", ("Importante: " if urgente else "Avviso: ") + minore.name,
                                schede.PERSONALE, durata_s=None,
                                chiave=f"avviso:{minore.id}:{int(time.time())}", testo=testo)
            hub.invia(card, Mittente(persona=tutore.id, nome=tutore.name, livello="familiare",
                                     certo=True), forza=True)
        except Exception as e:  # noqa: BLE001 — lo schermo non deve fermare l'avviso
            self.log(f"   [MINORI] scheda dell'avviso non mandata: {type(e).__name__}")

    def diretto(self, persona, tipo: str, testo: str):
        """Un avviso per la persona stessa (05/10: l'esito di una sua richiesta, la scadenza):
        lo sente alla sua prossima frase riconosciuta, come gli avvisi dei tutori."""
        ora = datetime.datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self.db.execute("INSERT INTO avvisi_tutori (tutore, minore, tipo, testo, urgente, "
                            "creato) VALUES (?, ?, ?, ?, 0, ?)",
                            (persona.id, persona.id, tipo, testo, ora))
            self.db.commit()
        self._scheda(persona, persona, testo, False)

    def da_dire(self, tutore_id: str, segna: bool = True) -> list[dict]:
        """Gli avvisi non ancora detti a questo tutore (i più urgenti prima)."""
        with self._lock:
            rows = self.db.execute("SELECT id, minore, tipo, testo, urgente FROM avvisi_tutori "
                                   "WHERE tutore = ? AND detto IS NULL ORDER BY urgente DESC, id",
                                   (tutore_id,)).fetchall()
            if segna and rows:
                ora = datetime.datetime.now().isoformat(timespec="seconds")
                self.db.executemany("UPDATE avvisi_tutori SET detto = ? WHERE id = ?",
                                    [(ora, r[0]) for r in rows])
                self.db.commit()
        return [{"id": r[0], "minore": r[1], "tipo": r[2], "testo": r[3], "urgente": bool(r[4])}
                for r in rows]

    def frase(self, avvisi_: list[dict]) -> str:
        if not avvisi_:
            return ""
        testi = [a["testo"] for a in avvisi_[:3]]
        altri = len(avvisi_) - len(testi)
        out = ("Ho un avviso per te: " if len(avvisi_) == 1 else "Ho degli avvisi per te. ") \
            + " ".join(testi)
        if altri > 0:
            out += f" E altri {altri}: li trovi sul tuo schermo."
        return out

    def compito(self, minore, argomento: str, soluzione: bool = False):
        giorno = datetime.date.today().isoformat()
        arg = str(argomento or "").strip()[:80] or "compiti"
        with self._lock:
            self.db.execute("INSERT INTO compiti_giorno (minore, giorno, argomento, aiuti, "
                            "soluzioni) VALUES (?, ?, ?, 1, ?) ON CONFLICT(minore, giorno, "
                            "argomento) DO UPDATE SET aiuti = aiuti + 1, soluzioni = soluzioni "
                            "+ excluded.soluzioni", (minore.id, giorno, arg, int(soluzione)))
            self.db.commit()

    def riepilogo(self, minore, giorno: datetime.date | None = None) -> str:
        g = (giorno or datetime.date.today()).isoformat()
        with self._lock:
            rows = self.db.execute("SELECT argomento, aiuti, soluzioni FROM compiti_giorno "
                                   "WHERE minore = ? AND giorno = ? ORDER BY aiuti DESC",
                                   (minore.id, g)).fetchall()
        if not rows:
            return f"Oggi {minore.name} non mi ha chiesto aiuto per i compiti."
        args = [r[0] for r in rows[:4]]
        sol = sum(r[2] for r in rows)
        out = f"Oggi {minore.name} ha chiesto aiuto su: {', '.join(args)}."
        if sol:
            out += (f" Per {'un esercizio' if sol == 1 else f'{sol} esercizi'} gli ho spiegato "
                    f"la soluzione dopo 5 tentativi.")
        return out

    def close(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass


# ─────────────────────────── tempo di gioco (05/10) ───────────────────────────

def gioco_minuti_fascia(fascia_: str | None) -> int:
    """I minuti di gioco al giorno di partenza per una fascia (minori_gioco_minuti)."""
    cfg = _SERVIZIO.get("cfg")
    valori = list(getattr(cfg, "minori_gioco_minuti", None) or [20, 45, 60, 90])
    i = _ORDINE.get(fascia_ or "", 3)
    try:
        return max(0, int(valori[min(i, len(valori) - 1)]))
    except (TypeError, ValueError, IndexError):
        return 60


class TempoGioco:
    """Il tempo di gioco di ogni minore sugli schermi, per giorno, e il tempo in più concesso
    da un adulto («oggi Bianca può giocare mezz'ora in più»: solo quel minore, solo oggi, con
    chi l'ha concesso e se è un suo tutore). In memoria.db (tabelle `gioco_tempo`,
    `gioco_extra`). Lo conta il server dei giochi dai battiti delle pagine (giochi.py)."""

    def __init__(self, path: str):
        from .persistenza import apri_db, prepara_schema
        self._lock = threading.Lock()
        self.db = apri_db(path)

        def v1(db):
            db.execute("CREATE TABLE IF NOT EXISTS gioco_tempo (persona TEXT NOT NULL, "
                       "giorno TEXT NOT NULL, secondi REAL NOT NULL DEFAULT 0, "
                       "PRIMARY KEY (persona, giorno))")
            db.execute("CREATE TABLE IF NOT EXISTS gioco_extra (id INTEGER PRIMARY KEY, "
                       "persona TEXT NOT NULL, giorno TEXT NOT NULL, minuti REAL NOT NULL, "
                       "da_id TEXT, da_nome TEXT, tutore INTEGER NOT NULL DEFAULT 0, "
                       "quando TEXT NOT NULL)")
        self.scrivibile = prepara_schema(self.db, "gioco_tempo", [v1])

    @staticmethod
    def _oggi(oggi: datetime.date | None = None) -> str:
        return (oggi or datetime.date.today()).isoformat()

    def usato_s(self, persona: str, oggi: datetime.date | None = None) -> float:
        with self._lock:
            r = self.db.execute("SELECT secondi FROM gioco_tempo WHERE persona = ? AND giorno = ?",
                                (persona, self._oggi(oggi))).fetchone()
        return float(r[0]) if r else 0.0

    def extra_min(self, persona: str, oggi: datetime.date | None = None) -> float:
        with self._lock:
            r = self.db.execute("SELECT COALESCE(SUM(minuti), 0) FROM gioco_extra WHERE persona = ? "
                                "AND giorno = ?", (persona, self._oggi(oggi))).fetchone()
        return float(r[0] or 0)

    def aggiungi(self, persona: str, secondi: float, oggi: datetime.date | None = None):
        if secondi <= 0:
            return
        with self._lock:
            self.db.execute("INSERT INTO gioco_tempo (persona, giorno, secondi) VALUES (?, ?, ?) "
                            "ON CONFLICT(persona, giorno) DO UPDATE SET secondi = secondi + "
                            "excluded.secondi", (persona, self._oggi(oggi), float(secondi)))
            self.db.commit()

    def concedi(self, minore, minuti: float, da, tutore: bool,
                oggi: datetime.date | None = None) -> int:
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO gioco_extra (persona, giorno, minuti, da_id, da_nome, tutore, quando) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (minore.id, self._oggi(oggi), float(minuti), getattr(da, "id", None),
                 getattr(da, "name", None), int(bool(tutore)),
                 datetime.datetime.now().isoformat(timespec="seconds")))
            self.db.commit()
            return int(cur.lastrowid)

    def concessioni(self, persona: str, oggi: datetime.date | None = None) -> list[dict]:
        with self._lock:
            rows = self.db.execute("SELECT minuti, da_nome, tutore, quando FROM gioco_extra WHERE "
                                   "persona = ? AND giorno = ? ORDER BY id",
                                   (persona, self._oggi(oggi))).fetchall()
        return [{"minuti": r[0], "da": r[1], "tutore": bool(r[2]), "quando": r[3]} for r in rows]

    def close(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass


def gioco_restante_s(prof, oggi: datetime.date | None = None) -> float | None:
    """I secondi di gioco che restano oggi a un minore (None per un adulto o un ospite: per
    loro nessun limite)."""
    p = preset(prof)
    if p is None:
        return None
    tg = tempo_gioco()
    usato = tg.usato_s(prof.id, oggi) if tg is not None else 0.0
    extra = tg.extra_min(prof.id, oggi) if tg is not None else 0.0
    return (float(p.get("gioco_minuti") or 0) + extra) * 60.0 - usato


def minuti_detti(m: float) -> str:
    m = int(round(m))
    if m == 30:
        return "mezz'ora"
    if m == 60:
        return "un'ora"
    if m % 60 == 0:
        return f"{m // 60} ore"
    return f"{m} minuti" if m != 1 else "un minuto"


# ─────────────────────────── richieste ai tutori (05/10) ───────────────────────────

# Le cose che un minore può chiedere e che un tutore approva, con l'effetto
TIPI_RICHIESTA = ("estensione", "agenti", "tempo_gioco", "orari")
_MINUTI_PREDEFINITI = {"agenti": 60, "tempo_gioco": 30, "orari": 60}


class Richieste:
    """Il meccanismo generale delle richieste in attesa di approvazione (decisione 6 del
    05/10): un gioco, un'estensione, l'agente per i ragazzi, più tempo di gioco, un'eccezione
    agli orari. La richiesta resta in sospeso (tabella `richieste_tutori` in memoria.db); la
    riceve il tutore (o chi amministra, se il minore non ha tutori) alla sua prima frase
    riconosciuta dalla voce, dopo la prima risposta, una volta per conversazione (main.py), e
    subito come scheda sui suoi schermi personali; si approva con la voce riconosciuta (mai
    una frase breve), da minore_gestisci; dopo `minori_richieste_giorni` scade, e chi l'aveva
    chiesta lo sa (avviso)."""

    def __init__(self, path: str, cfg=None, registry=None, log=print):
        from .persistenza import apri_db, prepara_schema
        self._lock = threading.Lock()
        self.db = apri_db(path)
        self.cfg = cfg
        self.registry = registry
        self.log = log

        def v1(db):
            db.execute("CREATE TABLE IF NOT EXISTS richieste_tutori (id INTEGER PRIMARY KEY, "
                       "minore TEXT NOT NULL, tipo TEXT NOT NULL, oggetto TEXT NOT NULL, "
                       "minuti REAL, creata TEXT NOT NULL, creata_ts REAL NOT NULL, "
                       "stato TEXT NOT NULL DEFAULT 'in_attesa', deciso_da TEXT, decisa TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS richieste_tutori_s ON richieste_tutori(stato)")
        self.scrivibile = prepara_schema(self.db, "richieste_tutori", [v1])

    def _riga(self, r) -> dict:
        return {"id": r[0], "minore": r[1], "tipo": r[2], "oggetto": r[3], "minuti": r[4],
                "creata": r[5], "creata_ts": r[6], "stato": r[7], "deciso_da": r[8],
                "decisa": r[9]}

    _COLONNE = "id, minore, tipo, oggetto, minuti, creata, creata_ts, stato, deciso_da, decisa"

    def crea(self, minore, tipo: str, oggetto: str, minuti: float | None = None,
             registry=None) -> tuple[int, bool]:
        """(id, nuova). Una richiesta uguale già in attesa non si ripete."""
        if tipo not in TIPI_RICHIESTA:
            raise ValueError(f"tipo di richiesta sconosciuto: {tipo}")
        oggetto = str(oggetto or tipo).strip()[:60]
        self.scadi()
        with self._lock:
            r = self.db.execute("SELECT id FROM richieste_tutori WHERE minore = ? AND tipo = ? AND "
                                "oggetto = ? AND stato = 'in_attesa'",
                                (minore.id, tipo, oggetto)).fetchone()
            if r:
                return int(r[0]), False
            ora = datetime.datetime.now()
            cur = self.db.execute(
                "INSERT INTO richieste_tutori (minore, tipo, oggetto, minuti, creata, creata_ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (minore.id, tipo, oggetto, minuti, ora.isoformat(timespec="seconds"), time.time()))
            self.db.commit()
            rid = int(cur.lastrowid)
        reg = registry or self.registry
        self.log(f"   [MINORI] richiesta R{rid} di {minore.name}: {tipo} «{oggetto}»")
        # Subito la scheda sui suoi schermi personali (il canale degli avvisi)
        av = avvisi()
        if av is not None:
            for t in tutori(minore, reg):
                av._scheda(t, minore, self.frase({"id": rid, "tipo": tipo, "oggetto": oggetto,
                                                  "minuti": minuti}, minore.name)
                           + ". Rispondimi a voce.", False)
        return rid, True

    def leggi(self, rid) -> dict | None:
        try:
            rid = int(str(rid).strip().lstrip("Rr"))
        except ValueError:
            return None
        with self._lock:
            r = self.db.execute(f"SELECT {self._COLONNE} FROM richieste_tutori WHERE id = ?",
                                (rid,)).fetchone()
        return self._riga(r) if r else None

    def in_attesa_per(self, tutore, registry=None) -> list[dict]:
        """Le richieste in attesa dei minori di cui `tutore` è tutore (o, senza tutori, di chi
        amministra), le più vecchie prima."""
        self.scadi()
        reg = registry or self.registry
        with self._lock:
            rows = self.db.execute(f"SELECT {self._COLONNE} FROM richieste_tutori WHERE "
                                   "stato = 'in_attesa' ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = self._riga(r)
            m = _per_id(reg, d["minore"])
            if m is not None and e_tutore(tutore, m):
                out.append(d)
        return out

    def frase(self, r: dict, nome: str) -> str:
        t, o = r["tipo"], r["oggetto"]
        if t == "estensione":
            return f"{nome} ti ha chiesto di poter usare «{o.replace('_', ' ')}»"
        if t == "agenti":
            return (f"{nome} ti ha chiesto di poter usare l'agente per "
                    f"{minuti_detti(r.get('minuti') or _MINUTI_PREDEFINITI['agenti'])}")
        if t == "tempo_gioco":
            return (f"{nome} ti ha chiesto {minuti_detti(r.get('minuti') or 30)} di gioco in "
                    f"più per oggi")
        return (f"{nome} ti ha chiesto di poter parlare con me anche durante la pausa, per "
                f"{minuti_detti(r.get('minuti') or 60)}")

    def decidi(self, rid, si: bool, da, registry=None, minuti: float | None = None) -> str:
        """Approva o nega. La frase per chi decide; l'esito va anche al minore (avviso)."""
        r = self.leggi(rid)
        if r is None or r["stato"] != "in_attesa":
            raise ValueError("non c'è una richiesta in attesa con quel numero")
        reg = registry or self.registry
        minore = _per_id(reg, r["minore"])
        if minore is None:
            raise ValueError("il ragazzo di quella richiesta non c'è più")
        if not e_tutore(da, minore):
            raise PermissionError(f"la richiesta di {minore.name} la decide un suo tutore")
        minuti = float(minuti or r.get("minuti") or _MINUTI_PREDEFINITI.get(r["tipo"], 60))
        regole_ = regole()
        if si:
            if r["tipo"] == "estensione":
                if regole_ is None:
                    raise ValueError("le regole dei ragazzi qui non si possono salvare")
                attuali = set(regole_.leggi(minore.id).get("estensioni") or [])
                regole_.imposta(minore.id, "estensioni", sorted(attuali | {r["oggetto"]}))
                fatto = f"{minore.name} adesso può usare «{r['oggetto'].replace('_', ' ')}»"
            elif r["tipo"] in ("agenti", "orari"):
                if regole_ is None:
                    raise ValueError("le regole dei ragazzi qui non si possono salvare")
                regole_.autorizza(minore.id, r["tipo"], minuti, getattr(da, "id", "?"))
                fatto = (f"per {minuti_detti(minuti)} {minore.name} può usare l'agente"
                         if r["tipo"] == "agenti" else
                         f"per {minuti_detti(minuti)} {minore.name} può parlarmi anche in pausa")
            else:
                tg = tempo_gioco()
                if tg is None:
                    raise ValueError("il tempo di gioco qui non si può salvare")
                tg.concedi(minore, minuti, da, True)
                fatto = f"oggi {minore.name} ha {minuti_detti(minuti)} di gioco in più"
        stato = "approvata" if si else "negata"
        with self._lock:
            self.db.execute("UPDATE richieste_tutori SET stato = ?, deciso_da = ?, decisa = ? "
                            "WHERE id = ?", (stato, getattr(da, "name", None),
                                             datetime.datetime.now().isoformat(timespec="seconds"),
                                             r["id"]))
            self.db.commit()
        av = avvisi()
        cosa = self.frase(r, "").replace(" ti ha chiesto ", "", 1).strip()
        if av is not None:
            testo = (f"{getattr(da, 'name', 'Un adulto')} ha detto di sì: {fatto}." if si else
                     f"{getattr(da, 'name', 'Un adulto')} ha detto di no alla tua richiesta "
                     f"({cosa}).")
            av.diretto(minore, "richiesta", testo)
        self.log(f"   [MINORI] richiesta R{r['id']} {stato} da {getattr(da, 'name', '?')}")
        return (f"Fatto: {fatto}." if si else f"D'accordo: ho detto di no a {minore.name}.")

    def scadi(self, ora: float | None = None) -> int:
        """Le richieste in attesa da più di `minori_richieste_giorni`: scadute, con un avviso a
        chi le aveva chieste."""
        giorni = float(getattr(self.cfg, "minori_richieste_giorni", 3.0) or 3.0)
        limite = (ora or time.time()) - giorni * 86400
        with self._lock:
            rows = self.db.execute(f"SELECT {self._COLONNE} FROM richieste_tutori WHERE "
                                   "stato = 'in_attesa' AND creata_ts < ?", (limite,)).fetchall()
            if not rows:
                return 0
            self.db.executemany("UPDATE richieste_tutori SET stato = 'scaduta', decisa = ? WHERE "
                                "id = ?", [(datetime.datetime.now().isoformat(timespec="seconds"),
                                            r[0]) for r in rows])
            self.db.commit()
        av = avvisi()
        for r in rows:
            d = self._riga(r)
            m = _per_id(self.registry, d["minore"])
            if m is not None and av is not None:
                cosa = self.frase(d, "").replace(" ti ha chiesto ", "", 1).strip()
                av.diretto(m, "richiesta", f"La tua richiesta ({cosa}) è scaduta senza "
                                           f"risposta: se vuoi, chiedimela di nuovo.")
        return len(rows)

    def close(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass


def _per_id(registry, pid):
    for u in list(getattr(registry, "users", {}).values()) if registry is not None else []:
        if getattr(u, "id", None) == pid:
            return u
    return None


# ─────────────────────────── terminale ───────────────────────────

def _carica_profili(path="speakers.json") -> list[dict]:
    from .persistenza import leggi_json
    dati, _ = leggi_json(path)
    return dati if isinstance(dati, list) else []


class _P:
    """Un profilo letto da speakers.json senza caricare CAM++ (terminale)."""

    def __init__(self, d: dict):
        self.id, self.name = d.get("id"), d.get("name")
        self.nascita, self.tutori = d.get("nascita"), list(d.get("tutori") or [])
        self.fascia = "ragazzi" if d.get("giovane") and not d.get("nascita") else d.get("fascia")
        self.admin = bool(d.get("admin"))
        self.voiceprint = d.get("voiceprint")
        self.impronta_data = d.get("impronta_data")


def _main(argv: list[str]) -> int:
    """python -m calliope.minori                         i minori, con fascia e preset
       python -m calliope.minori --imposta Bianca internet=no [orari=21:00-07:30] …
       python -m calliope.minori --estensione Bianca meteo [--togli]
       python -m calliope.minori --autorizza Bianca agenti 60
       python -m calliope.minori --riepilogo Bianca
       python -m calliope.minori --preset              i preset delle fasce"""
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from .config import load_config
    cfg = load_config()
    if "--preset" in argv:
        for f, p in PRESET.items():
            da, a = next((x[1], x[2]) for x in FASCE if x[0] == f)
            print(f"{f} ({da}–{a} anni): " + ", ".join(f"{k}={v}" for k, v in p.items()
                                                      if k != "tono"))
        return 0
    prof = [_P(d) for d in _carica_profili()]
    reg = Regole(cfg.memory_db)
    _SERVIZIO["regole"] = reg

    def trova(nome):
        from .speaker_id import name_key
        k = name_key(nome)
        return next((p for p in prof if name_key(p.name or "") == k), None)

    def uso():
        print(_main.__doc__)
        return 2

    if "--imposta" in argv:
        i = argv.index("--imposta")
        p = trova(argv[i + 1]) if len(argv) > i + 1 else None
        if p is None or not e_minore(p):
            print("Profilo minorenne non trovato (serve la data di nascita: arruola.py "
                  "<nome> --nascita AAAA-MM-GG)")
            return 1
        for kv in argv[i + 2:]:
            if kv.startswith("--"):
                break
            k, _, v = kv.partition("=")
            try:
                reg.imposta(p.id, k.strip(), controlla_valore(k, v, fascia(p)))
            except ValueError as e:
                print(f"{kv}: {e}")
                return 1
        print(f"{p.name}: " + json.dumps(preset(p, reg=reg), ensure_ascii=False))
        return 0
    if "--estensione" in argv:
        i = argv.index("--estensione")
        if len(argv) < i + 3:
            return uso()
        p = trova(argv[i + 1])
        if p is None or not e_minore(p):
            print("Profilo minorenne non trovato")
            return 1
        attuali = set(reg.leggi(p.id).get("estensioni") or [])
        nome = _norm(argv[i + 2]).replace(" ", "_")
        attuali = attuali - {nome} if "--togli" in argv else attuali | {nome}
        reg.imposta(p.id, "estensioni", sorted(attuali))
        print(f"{p.name}: estensioni abilitate {sorted(attuali) or 'nessuna'}")
        return 0
    if "--autorizza" in argv:
        i = argv.index("--autorizza")
        if len(argv) < i + 4:
            return uso()
        p = trova(argv[i + 1])
        if p is None or not e_minore(p):
            print("Profilo minorenne non trovato")
            return 1
        reg.autorizza(p.id, argv[i + 2], float(argv[i + 3]), "terminale")
        print(f"{p.name}: «{argv[i + 2]}» autorizzato per {argv[i + 3]} minuti")
        return 0
    if "--riepilogo" in argv:
        i = argv.index("--riepilogo")
        p = trova(argv[i + 1]) if len(argv) > i + 1 else None
        if p is None:
            return uso()
        print(Avvisi(cfg.memory_db).riepilogo(p))
        return 0
    minori_ = [p for p in prof if e_minore(p)]
    if not minori_:
        print("Nessun profilo minorenne. Per registrarne uno: «Calliope, aggiungi un "
              "familiare» (chi amministra), oppure python arruola.py <nome> --nascita "
              "AAAA-MM-GG --tutore <nome>.")
        return 0
    nomi = {p.id: p.name for p in prof}
    for p in minori_:
        pr = preset(p, reg=reg)
        anni = pr.get("eta")
        print(f"{p.name}: {pr['fascia']}" + (f", {anni} anni" if anni is not None else
                                             " (senza data di nascita)")
              + f"; tutori: {', '.join(nomi.get(t, t) for t in p.tutori) or 'chi amministra'}")
        print("   " + ", ".join(f"{k}={pr[k]}" for k in ("fonti", "internet", "agenti", "casa",
                                                          "pc", "documenti", "acquisti",
                                                          "compiti", "orari", "stanza",
                                                          "estensioni")))
        motivo = impronta_da_rifare(p, cfg=cfg)
        if motivo:
            print(f"   impronta da rifare: {motivo}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
