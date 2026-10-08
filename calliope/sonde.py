"""
Sonde dell'agente e ricollaudo alla consegna (08/10/2026 notte, specifica del § 9 di
docs/ricerche/2026-10-08-sonde-agente.md; aree agenti-estensioni e sicurezza-politica).

Una regola sola, decisa da Dario («una regola generalista e di buon senso, una bella rete di
protezione»): **Calliope prova davvero prima di dire «è pronto»**. Prova il codice con i casi
della persona, e risponde all'agente che vuole provare una richiesta. Lo fa solo verso host già
visti, con valori che vengono dal caso, in poche richieste, e scrive tutto.

- **Ricollaudo** (`ricollaudo`): quando l'agente consegna una correzione (o un lavoro ripartito
  dall'analisi dopo dei collaudi), la versione nuova gira nel container vero, dalla porta, con
  gli argomenti dei collaudi che non andavano, una volta per lavoro; il manifesto è ristretto
  alla sola lettura di rete verso gli host noti (`manifesto.restringi_per_sonda`) e nessuna
  conferma si chiede (porta, `ricollaudo_senza_conferme`). Se un caso non va ancora, la
  consegna torna all'agente con la traccia e il confronto, in busta.
- **Sonde** (`sonda`, lo strumento `sonda_rete` dell'agente nelle correzioni, al posto di
  `scarica_esempio`): una GET vera verso un host noto, con i soli valori del caso (il
  `Vocabolario`: specifica, collaudi, traccia; numeri e date), al più `sviluppo_sonde_max` per
  lavoro, `sviluppo_sonde_passata` per passata, `sviluppo_sonde_giorno` per sviluppo al giorno;
  la risposta torna in busta (dato non fidato) con i parametri come li ha letti il server.
- **Host noti** (`host_noti`): manifesto approvato, host che hanno risposto in un collaudo della
  persona (anche con un errore del sito, mai un rifiuto della porta), host concessi con
  `chiedi_permesso`. Mai il manifesto della versione in prova né `rete.pubblica`.

Le regole vanno nel log dell'agente e in `lav.segnali["regole"]`: sonda_fatta, sonda_finite,
sonda_host_nuovo, sonda_valore_estraneo, sonda_url_non_codificato, sonda_dato_riservato,
ricollaudo_fatto, ricollaudo_non_va, ricollaudo_saltato (ricollaudo_senza_conferme nella porta,
rete_casa_pubblica in web/rete.py). Solo libreria standard.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, unquote, unquote_plus, urlsplit

# Le forme neutre a banda bassa ammesse in ogni sonda (§ 9.4): numeri brevi anche con segno e
# decimali (coordinate), date ISO, vero e falso, codici di due o tre lettere (lingua e paese),
# e un elenco chiuso e corto di unità e formati
_NUMERO = re.compile(r"^[+-]?\d{1,8}([.,]\d{1,8})?$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$")
# Codici di lingua e di paese: due lettere (ISO 639-1, 3166 alpha-2), o tre di un elenco chiuso
# (le tre lettere libere erano un canale: «gio», «ved», «car»…)
_CODICE = re.compile(r"^[A-Za-z]{2}$")
CODICI_TRE = frozenset({"ita", "eng", "deu", "fra", "spa", "esp", "usa", "gbr", "che", "aut",
                        "eur", "usd", "gbp", "chf", "utc", "gmt", "cet", "all", "any"})
UNITA = frozenset({"true", "false", "celsius", "fahrenheit", "metric", "imperial", "standard",
                   "json", "xml", "csv", "geojson", "auto", "kmh", "ms", "mph", "mm", "inch",
                   "kn", "iso8601", "unixtime", "utc", "gmt", "daily", "hourly", "current",
                   "asc", "desc"})
# Nomi di parametri comuni delle API di dati (§ 9.4: «il percorso nuovo non si inventa», ma un
# parametro del paese sull'host noto sì, il caso del giro 4). Un nome è ammesso se è nei
# collaudi, oppure se ogni sua parola (separata da «_», «-» o maiuscole) è qui o nel caso
NOMI_API = frozenset("""
    q query name names city citta comune country code countrycode lang language locale lat lon
    lng latitude longitude limit count days day forecast past hours hour timezone tz format
    units unit page per size offset start end date from to sort order type types fields
    include exclude id ids key keys region state province postal postcode zip search cerca
    nome paese lingua giorni temperature temperature_2m weather daily hourly current min max
    mean sum precipitation wind speed direction cell selection models model elevation admin
    feature features level levels results result
""".split())
MAX_SONDE_SV = 20          # sonde tenute nello sviluppo (scheda)
MAX_RICOLLAUDI_SV = 10     # ricollaudi tenuti nello sviluppo (scheda)
SONDA_RISPOSTA = 1500      # caratteri della risposta dati all'agente
# Gli errori di una richiesta che dicono che il server ha risposto (o ci ha provato a lungo):
# solo questi fanno di un host «noto» (pagina.PaginaNonLetta; i rifiuti della porta no)
_RISPOSTO = re.compile(r"ha risposto \d|tempo scaduto|troppo grande|non è una pagina di testo"
                       r"|compressione|reindirizzamento senza destinazione", re.I)

REGOLE = ("sonda_fatta", "sonda_finite", "sonda_host_nuovo", "sonda_valore_estraneo",
          "sonda_url_non_codificato", "sonda_dato_riservato", "ricollaudo_fatto",
          "ricollaudo_non_va", "ricollaudo_saltato", "ricollaudo_senza_conferme",
          "rete_casa_pubblica")


# ─────────────────────────── utilità ───────────────────────────

def _norm(s) -> str:
    """Minuscolo, senza accenti."""
    t = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _compatto(s) -> str:
    """Senza maiuscole, accenti, spazi, «+», «%20» e punteggiatura: «Pratofiorito+Maggiore»,
    «pratofiorito maggiore» e «Pratofiorito%20Maggiore» sono lo stesso valore."""
    return re.sub(r"[^a-z0-9]", "", _norm(s))


def _parole(s) -> list[str]:
    return re.findall(r"[a-z0-9]+", _norm(s))


def _decodifiche(valore: str) -> list[str]:
    """Il valore com'è, decodificato una volta e due (§ 9.4: «%2B» contro «+»)."""
    out = [str(valore or "")]
    for _ in range(2):
        try:
            d = unquote_plus(out[-1])
        except Exception:  # noqa: BLE001
            break
        if d == out[-1]:
            break
        out.append(d)
    return out


def _neutro(valore: str) -> bool:
    v = str(valore or "").strip()
    return bool(_NUMERO.match(v) or _DATA.match(v) or _CODICE.match(v)
                or v.lower() in UNITA or v.lower() in CODICI_TRE)


def _host(url) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").rstrip(".").lower()
    except ValueError:
        return ""


def _oggi() -> str:
    return datetime.date.today().isoformat()


def nota(lav, regola: str, log=None, dettaglio: str = ""):
    """Una regola delle sonde o del ricollaudo: nel log e contata in `lav.segnali`."""
    try:
        seg = lav.segnali if isinstance(getattr(lav, "segnali", None), dict) else {}
        lav.segnali = seg
        conti = seg.setdefault("regole", {})
        conti[regola] = int(conti.get(regola, 0)) + 1
    except Exception:  # noqa: BLE001 — una statistica non ferma niente
        pass
    if log is not None:
        log(f"[SONDE] {getattr(lav, 'id', '?')}: {regola}" + (f" ({dettaglio})" if dettaglio
                                                               else ""))


# ─────────────────────────── host noti (§ 9.2) ───────────────────────────

def ha_risposto(r: dict) -> bool:
    """Una riga della traccia di un collaudo il cui server ha risposto: «stato …», oppure un
    errore del sito (4xx/5xx, tempo scaduto). Mai un rifiuto della porta («non concesso», «URL
    non valido», «dato riservato», un reindirizzamento non ammesso)."""
    if not isinstance(r, dict) or r.get("rifiutata"):
        return False
    esito = str(r.get("esito") or "")
    if esito.startswith("stato"):
        return True
    return esito == "errore" and bool(_RISPOSTO.search(str(r.get("errore") or "")))


def host_noti(sv, archivio=None, lav=None) -> set[str]:
    """Gli host noti dello sviluppo: quelli del manifesto **approvato** (rete.host e invia), quelli
    che hanno risposto in un collaudo della persona (l'host iniziale della richiesta: mai quello
    di un reindirizzamento), quelli concessi con chiedi_permesso (`sv.host_concessi`, e quelli
    del lavoro in corso). Mai il manifesto della versione in prova, mai `rete.pubblica`."""
    out: set[str] = set()
    nome = getattr(sv, "estensione", None)
    if archivio is not None and nome:
        try:
            m = archivio.manifesto(nome) or {}
            from .estensioni.manifesto import normalizza_permessi
            p = normalizza_permessi(m.get("permessi") or {})
            out |= set(p["rete"]["host"]) | {f["host"] for f in p["invia"]}
        except Exception:  # noqa: BLE001 — nessuna versione approvata
            pass
    for c in getattr(sv, "collaudi", None) or ():
        for r in (c.get("rete") or ()) if isinstance(c, dict) else ():
            if ha_risposto(r):
                h = _host(r.get("url"))
                if h:
                    out.add(h)
    for h in list(getattr(sv, "host_concessi", None) or ()) + list(
            getattr(lav, "host_concessi", None) or ()):
        h = str(h or "").strip().lower().rstrip(".")
        if h:
            out.add(h)
    out.discard("")
    return out


def concedi(svs, sv, lav, scope, risposta: str, log=None) -> list[str]:
    """La risposta a chiedi_permesso: se è un «sì» e lo scope chiede degli host di rete, quegli
    host diventano noti per le sonde (nel lavoro e nello sviluppo). La decisione vera resta la
    revisione con la sfida. Restituisce gli host concessi."""
    from . import politica
    hosts = []
    try:
        r = (scope or {}).get("rete") or {}
        hosts = [str(h).strip().lower().rstrip(".") for h in (r.get("host") or [])
                 if str(h).strip()] if isinstance(r, dict) else []
    except AttributeError:
        hosts = []
    if not hosts or not politica.consenso(str(risposta or "")):
        return []
    propri = list(getattr(lav, "host_concessi", None) or [])
    lav.host_concessi = sorted(set(propri) | set(hosts))
    if svs is not None and sv is not None:
        with svs._lock:
            sv.host_concessi = sorted(set(getattr(sv, "host_concessi", None) or []) | set(hosts))
        svs._salva()
    if log is not None:
        log(f"[SONDE] {getattr(lav, 'id', '?')}: host concessi con chiedi_permesso: "
            f"{', '.join(hosts)}")
    return hosts


# ─────────────────────────── vocabolario del caso (§ 9.4) ───────────────────────────

class Vocabolario:
    """I valori che una sonda può portare: quelli del caso (specifica, richiesta, dati e
    argomenti dei collaudi, nomi e valori dei parametri e pezzi del percorso delle richieste dei
    collaudi), confrontati senza maiuscole, accenti, «+», «%20» e spazi, decodificati fino a due
    volte, più le forme neutre. Mai il testo della conversazione, i file della sandbox, la
    diagnosi del modello o la risposta di una sonda."""

    def __init__(self):
        self.parole: set[str] = set()
        self.valori: set[str] = set()       # valori interi, compatti
        self.nomi: set[str] = set()         # nomi di parametri visti, compatti
        self.per_nome: dict[str, list[str]] = {}   # nome → valori visti (per i messaggi)

    def aggiungi(self, testo, nome: str | None = None):
        for d in _decodifiche(str(testo or "")):
            c = _compatto(d)
            if c:
                self.valori.add(c)
            self.parole.update(_parole(d))
            if nome is not None and d.strip():
                lista = self.per_nome.setdefault(_compatto(nome), [])
                if d.strip()[:60] not in lista and len(lista) < 20:
                    lista.append(d.strip()[:60])

    def aggiungi_url(self, url: str):
        try:
            u = urlsplit(str(url or "").rstrip("…"))
        except ValueError:
            return
        for pezzo in u.path.split("/"):
            if pezzo and "[tolto" not in pezzo:
                self.aggiungi(pezzo)
        for pezzo in (u.query.split("&") if u.query else ()):
            nome, _, valore = pezzo.partition("=")
            if not nome or "[tolto" in pezzo:
                continue
            for d in _decodifiche(nome):
                self.nomi.add(_compatto(d))
                self.parole.update(_parole(d))
            self.aggiungi(valore, nome)

    # ── controlli ──
    def valore_ok(self, valore: str) -> bool:
        for d in _decodifiche(valore):
            v = d.strip()
            if not v or _neutro(v):
                return True
            if _compatto(v) in self.valori:
                return True
            parole = _parole(v)
            # «Pratofiorito Maggiore» se ci sono «Pratofiorito» e «Maggiore»: le parole del caso
            # combinate, e i numeri; non i codici di due lettere (banda in più per niente)
            if parole and all(p in self.parole or p.isdigit() and len(p) <= 8 for p in parole):
                return True
        return False

    def nome_ok(self, nome: str) -> bool:
        for d in _decodifiche(nome):
            if _compatto(d) in self.nomi:
                return True
            pezzi = [p for p in re.split(r"[_\-.\[\]]+|(?<=[a-z])(?=[A-Z])", d) if p]
            if pezzi and all(_compatto(p) in NOMI_API or _compatto(p) in self.parole
                             or (_compatto(p).isdigit() and len(p) <= 2) for p in pezzi):
                return True
        return False

    def pezzo_ok(self, pezzo: str) -> bool:
        """Un pezzo del percorso: già visto nei collaudi (o una parola del caso), o un numero."""
        for d in _decodifiche(pezzo):
            v = d.strip()
            if not v or _NUMERO.match(v) or _compatto(v) in self.valori:
                return True
            parole = _parole(v)
            if parole and all(p in self.parole for p in parole):
                return True
        return False

    def ammessi(self, nome: str, quanti: int = 10) -> list[str]:
        return list(self.per_nome.get(_compatto(nome)) or [])[:quanti]


def vocabolario(sv) -> Vocabolario:
    voc = Vocabolario()
    voc.aggiungi(getattr(sv, "specifica", "") or "")
    voc.aggiungi(getattr(sv, "richiesta", "") or "")
    for c in getattr(sv, "collaudi", None) or ():
        if not isinstance(c, dict):
            continue
        voc.aggiungi(c.get("dati") or "")
        for k, v in (c.get("argomenti") or {}).items():
            voc.aggiungi(v if isinstance(v, str) else json.dumps(v), k)
            for d in _decodifiche(str(k)):
                voc.nomi.add(_compatto(d))
        for r in c.get("rete") or ():
            if isinstance(r, dict) and r.get("url"):
                voc.aggiungi_url(r["url"])
    return voc


def controlla_url(url: str, voc: Vocabolario) -> str:
    """"" o il motivo per cui un URL di una sonda porta un valore che non viene dal caso: ogni
    valore della query, ogni nome di parametro e ogni pezzo del percorso. Il nome dell'host lo
    controlla `host_noti`."""
    try:
        u = urlsplit(str(url or ""))
    except ValueError:
        return "URL illeggibile"
    for pezzo in u.path.split("/"):
        if pezzo and not voc.pezzo_ok(pezzo):
            return "un pezzo del percorso che non viene dai collaudi"
    for pezzo in (u.query.split("&") if u.query else ()):
        nome, _, valore = pezzo.partition("=")
        if not nome:
            if valore:
                return "un valore senza nome nei parametri"
            continue
        if not voc.nome_ok(nome):
            # Il nome rifiutato non si ripete (potrebbe portare il dato): i nomi ammessi sì
            visti = sorted(voc.per_nome)[:8]
            return ("un nome di parametro che non viene dai collaudi" + (
                " (quelli visti: " + ", ".join(visti) + ")" if visti else ""))
        if not voc.valore_ok(valore):
            ammessi = voc.ammessi(nome)
            return (f"un valore del parametro «{_corto(nome)}» che non viene dai collaudi né "
                    "dalla specifica" + (": valori ammessi " + ", ".join(
                        f"«{a}»" for a in ammessi) if ammessi else "")
                    + "; oltre a quelli, numeri, date, codici di lingua e di paese")
    return ""


def _corto(nome: str) -> str:
    n = re.sub(r"[^\w\-.\[\]]", "", str(nome or ""))[:30]
    return n or "?"


def come_l_ha_letto(url: str) -> dict:
    """I parametri come li legge il server, decodificati **una volta** (`parse_qsl`): è la riga
    che nel giro 5 avrebbe mostrato «Pratofiorito+Maggiore» con il «+» letterale."""
    try:
        coppie = parse_qsl(urlsplit(str(url or "")).query, keep_blank_values=True)
    except ValueError:
        return {}
    out = {}
    for k, v in coppie[:20]:
        out[str(k)[:40]] = str(v)[:200]
    return out


# ─────────────────────────── la sonda (§ 9.4) ───────────────────────────

SONDA_RETE = {"type": "function", "function": {
    "name": "sonda_rete",
    "description": (
        "Una richiesta GET vera, fatta da Calliope, per verificare un'ipotesi su un servizio "
        "che l'estensione usa già (per esempio: con «+» invece di «%2B» il geocoder trova la "
        "città?). Solo verso i siti già usati nei collaudi o approvati (sono nei vincoli), solo "
        "con i valori dei collaudi e della specifica, numeri e date. url: l'indirizzo completo, "
        "codificato. perche: l'ipotesi che vuoi verificare, in una frase."),
    "parameters": {"type": "object", "properties": {"url": {"type": "string"},
                                                    "perche": {"type": "string"}},
                   "required": ["url", "perche"]}}}


def sonde_ok(cfg, lav, sv, archivio=None) -> str | None:
    """None se il lavoro può avere sonda_rete (al posto di scarica_esempio), altrimenti il
    perché: internet spento, sonde spente, un file della persona nel lavoro, nessuno sviluppo
    con dei collaudi legato al lavoro, nessun host noto."""
    if not getattr(cfg, "online", True):
        return "questa installazione è senza internet"
    if int(getattr(cfg, "sviluppo_sonde_max", 4) or 0) <= 0:
        return "le sonde sono spente (sviluppo_sonde_max)"
    if (getattr(lav, "input", None) is not None or getattr(lav, "file_utente", None) is not None
            or getattr(lav, "input_testo", "")):
        return "con un file della persona nel lavoro internet resta spento"
    if sv is None or getattr(lav, "tipo", "") != "estensione":
        return "il lavoro non è di uno sviluppo"
    if not (getattr(lav, "correzione", False) or getattr(sv, "collaudi", None)):
        return "non è una correzione"
    if not host_noti(sv, archivio, lav):
        return "nessun host noto"
    return None


def riga_vincoli(cfg, sv, archivio=None, lav=None) -> str:
    """La riga dei vincoli che dice all'agente le sonde (§ 9.5)."""
    noti = sorted(host_noti(sv, archivio, lav))
    n = int(getattr(cfg, "sviluppo_sonde_max", 4) or 0)
    return (f"Siti già usati: {', '.join(noti[:6])}. Se la traccia non ti basta per capire, "
            f"verifica l'ipotesi con sonda_rete (al più {n} richieste, solo i valori dei "
            "collaudi): prima di correggere, non dopo.")


def _registra_sv(svs, sv, voce: dict):
    if svs is None or sv is None:
        return
    with svs._lock:
        lista = list(getattr(sv, "sonde", None) or [])
        lista.append(voce)
        sv.sonde = lista[-MAX_SONDE_SV:]
    svs._salva()


def sonde_oggi(sv) -> int:
    oggi = _oggi()
    return sum(1 for s in getattr(sv, "sonde", None) or ()
               if s.get("giorno") == oggi and s.get("inviata"))


def sonda(cfg, rete, svs, sv, lav, args: dict, archivio=None, log=print) -> dict:
    """Una sonda dell'agente: i controlli nell'ordine di § 9.4 (quote, URL, host noto,
    codifica, vocabolario), poi `RetePubblica.richiesta` con origine «sonda». Ogni rifiuto va
    nel registro delle uscite («bloccata» con il motivo) e torna all'agente come {"errore",
    "cosa_fare"}. La risposta in busta (dato non fidato)."""
    from .estensioni.porta import _pulisci_testo, url_per_traccia
    from .provenienza import racchiudi
    from .web import pagina
    url = str((args or {}).get("url") or "").strip()
    perche = " ".join(str((args or {}).get("perche") or "").split())[:200]
    host = _host(url)
    origine = {"origine": "sonda", "lavoro": getattr(lav, "id", None),
               "sviluppo": getattr(sv, "id", None), "persona": getattr(lav, "persona_nome", None)}
    massimo = int(getattr(cfg, "sviluppo_sonde_max", 4) or 0)
    per_passata = int(getattr(cfg, "sviluppo_sonde_passata", 2) or 1)
    al_giorno = int(getattr(cfg, "sviluppo_sonde_giorno", 12) or 0)
    noti = host_noti(sv, archivio, lav)
    # Nel registro delle uscite e sulla scheda di una sonda rifiutata solo l'host noto (un host
    # non noto può portare il dato nel nome: «cardiologo.sito-cattivo.org») e mai il percorso
    # né i valori
    host_reg = host if host in noti else ("[host non noto] " + ".".join(host.split(".")[-2:])
                                          if host else "")
    voce = {"quando": time.time(), "giorno": _oggi(), "lavoro": getattr(lav, "id", None),
            "perche": perche, "url": f"{host_reg}/…", "inviata": False}

    def no(regola: str, motivo: str, cosa_fare: str, per_agente: str = "") -> dict:
        if rete is not None:
            rete.registra(origine, host_reg, "GET", "bloccata", f"{regola}: {motivo}")
        nota(lav, regola, log, motivo[:80])
        voce["esito"] = f"rifiutata: {motivo}"[:160]
        _registra_sv(svs, sv, voce)
        return {"errore": f"sonda non fatta: {per_agente or motivo}", "cosa_fare": cosa_fare,
                "regola": regola}

    # 1. quote
    passo = int(getattr(lav, "passi", 0) or 0)
    if getattr(lav, "sonde_passo", None) != passo:
        lav.sonde_passo, lav.sonde_passata = passo, 0
    fatte = int(getattr(lav, "sonde", 0) or 0)
    if fatte >= massimo:
        return no("sonda_finite", f"sonde finite per questo lavoro ({massimo})",
                  "usa la traccia e quello che hai già visto")
    if int(getattr(lav, "sonde_passata", 0) or 0) >= per_passata:
        return no("sonda_finite", f"al più {per_passata} sonde per passata",
                  "guarda le risposte che hai, poi decidi")
    if al_giorno and sonde_oggi(sv) >= al_giorno:
        return no("sonda_finite", f"sonde finite per oggi in questo sviluppo ({al_giorno})",
                  "usa la traccia e quello che hai già visto")
    # 2. forma dell'URL: http o https, niente credenziali né frammento; il metodo è sempre GET
    try:
        u = urlsplit(url)
        credenziali = bool(u.username or u.password or "@" in u.netloc)
    except ValueError:
        u, credenziali = None, True
    if u is None or u.scheme not in ("http", "https") or not host:
        return no("sonda_valore_estraneo", "indirizzo non valido (solo http o https)",
                  "scrivi l'indirizzo completo, codificato")
    if credenziali or "#" in url:
        return no("sonda_valore_estraneo", "niente utente, password o frammento nell'indirizzo",
                  "togli utente, password e la parte dopo «#»")
    # 3. host noto
    if host not in noti:
        return no("sonda_host_nuovo", "host non tra i siti già usati",
                  "le sonde vanno solo a " + (", ".join(sorted(noti)[:6]) or "nessun sito")
                  + ". Per un sito nuovo chiedi il permesso con chiedi_permesso, scope "
                  f"{{\"rete\": {{\"host\": [\"{host[:60]}\"]}}}}",
                  per_agente=f"«{host[:60]}» non è tra i siti già usati")
    # 4. codifica
    rotto = pagina.url_non_codificato(url)
    if rotto:
        return no("sonda_url_non_codificato", rotto, "codifica i valori con urlencode")
    # 5. vocabolario del caso
    estraneo = controlla_url(url, vocabolario(sv))
    if estraneo:
        return no("sonda_valore_estraneo", estraneo,
                  "nelle sonde solo i valori dei collaudi e della specifica, numeri e date")
    # 6. la richiesta, dalla stessa porta delle estensioni
    lav.sonde = fatte + 1
    lav.sonde_passata = int(getattr(lav, "sonde_passata", 0) or 0) + 1
    voce["inviata"] = True
    voce["url"] = url_per_traccia(url, rete)
    kb = int(getattr(cfg, "sviluppo_sonda_kb", 256) or 256)
    sec = float(getattr(cfg, "sviluppo_sonda_s", 8.0) or 8.0)
    t0 = time.monotonic()
    letto = come_l_ha_letto(url)
    restanti = max(0, massimo - lav.sonde)
    try:
        r = rete.richiesta(url, origine, max_byte=kb * 1024, timeout_s=sec,
                           host_ammesso=lambda h: h in noti, max_rimandi=2)
    except pagina.PaginaVietata as e:
        motivo = str(e)
        regola = ("sonda_dato_riservato" if "riservato" in motivo else
                  "rete_casa_pubblica" if "casa" in motivo else "sonda_host_nuovo"
                  if "host non ammesso" in motivo else "sonda_valore_estraneo")
        nota(lav, regola, log, motivo[:80])
        voce["esito"] = f"rifiutata: {motivo}"[:160]
        _registra_sv(svs, sv, voce)
        return {"errore": f"sonda non fatta: {motivo}", "regola": regola,
                "sonde_restanti": restanti}
    except pagina.PaginaNonLetta as e:
        nota(lav, "sonda_fatta", log, f"errore del sito: {e}"[:80])
        voce["esito"] = f"errore: {e}"[:160]
        _registra_sv(svs, sv, voce)
        return {"stato": "errore", "errore_del_sito": str(e)[:200],
                "ms": int((time.monotonic() - t0) * 1000),
                "come_l_ha_letto_il_server": letto, "sonde_restanti": restanti}
    testo = str(r.get("testo_grezzo") or "")
    byte = len(testo.encode("utf-8"))
    nota(lav, "sonda_fatta", log, f"{host}, {byte} byte")
    voce["esito"] = f"stato 200, {byte} byte"
    _registra_sv(svs, sv, voce)
    pulito = _pulisci_testo(" ".join(testo[:SONDA_RISPOSTA * 3].split()), rete)[:SONDA_RISPOSTA]
    out = {"stato": 200, "tipo": str(r.get("tipo") or "")[:60], "byte": byte,
           "ms": int((time.monotonic() - t0) * 1000), "come_l_ha_letto_il_server": letto}
    doppia = pagina.doppia_codifica(url)
    if doppia:
        out["avviso"] = doppia
    out["risposta"] = racchiudi("web", pulito, titolo=host)
    out["sonde_restanti"] = restanti
    return out


# ─────────────────────────── ricollaudo (§ 9.3) ───────────────────────────

def _male(c: dict) -> bool:
    return not c.get("ok") or bool(c.get("giudizio"))


def casi_da_riprovare(sv, quanti: int = 3) -> list[dict]:
    """Gli ultimi collaudi falliti o giudicati sbagliati dalla persona, uno per dato distinto
    (dati e argomenti), dal più recente, al più `quanti`."""
    out, visti = [], set()
    for c in reversed(list(getattr(sv, "collaudi", None) or [])):
        if not isinstance(c, dict) or not _male(c):
            continue
        chiave = _compatto(c.get("dati") or "") + "|" + json.dumps(
            c.get("argomenti") or {}, sort_keys=True, ensure_ascii=False)
        if chiave in visti:
            continue
        visti.add(chiave)
        out.append(c)
        if len(out) >= quanti:
            break
    return out


def detto(c: dict) -> str:
    """Il caso com'è da dire: i valori degli argomenti («Pratofiorito Maggiore, 5»), o i dati
    detti."""
    a = c.get("argomenti")
    if isinstance(a, dict) and a:
        valori = [str(v) for v in a.values() if str(v).strip()]
        if valori:
            return ", ".join(valori)[:80]
    return str(c.get("dati") or "senza dati")[:80]


def _esito_testo(r: dict) -> str:
    ris = r.get("risultato")
    if isinstance(ris, dict) and ris.get("da_dire"):
        return re.sub(r"\s+", " ", str(ris["da_dire"])).strip()[:200]
    if ris is not None:
        return json.dumps(ris, ensure_ascii=False, default=str)[:200]
    return str(r.get("errore") or r.get("stato") or "")[:200]


def va(caso: dict, r: dict) -> tuple[bool, str]:
    """(il caso adesso va?, perché no). Con la regola del collaudo (fermata con un errore, un
    campo d'errore, nessun risultato) e in più: lo stesso risultato che la persona aveva già
    giudicato sbagliato, una richiesta rifiutata dalla porta o con l'avviso della doppia
    codifica."""
    if not r.get("ok"):
        return False, f"si è fermata: {r.get('errore') or r.get('stato')}"
    ris = r.get("risultato")
    if not ris:
        return False, "nessun risultato"
    if isinstance(ris, dict) and (ris.get("errore") or ris.get("error")
                                  or ris.get("ok") is False):
        return False, "il risultato ha un errore"
    for riga in r.get("traccia") or ():
        if riga.get("rifiutata"):
            return False, "una richiesta rifiutata dalla porta"
        if riga.get("avviso"):
            return False, "una richiesta con l'avviso della porta"
    nuovo = _esito_testo(r)
    if caso.get("giudizio") or caso.get("ok"):
        vecchio = str(caso.get("esito") or "")
        if vecchio and _compatto(vecchio) == _compatto(nuovo):
            return False, "lo stesso risultato che la persona aveva detto sbagliato"
    return True, ""


def _file_della_consegna(sandbox) -> dict[str, bytes]:
    from .estensioni.archivio import ESTENSIONI_FILE, RUNTIME
    from .estensioni.servizio import _solo_usati
    file = {}
    for f in sandbox.elenca():
        rel = f["percorso"]
        if rel in (RUNTIME, "CAPACITA.md") or not rel.lower().endswith(ESTENSIONI_FILE):
            continue
        if rel.startswith((".calliope/", "esempi_veri/")):
            continue
        file[rel] = (Path(sandbox.root) / rel).read_bytes()
    return _solo_usati(file)


def saltato(cfg, est, sv, lav) -> str:
    """"" o il perché il ricollaudo non parte (§ 9.3, «Quando non parte»)."""
    if not getattr(cfg, "sviluppo_ricollaudo", True):
        return "spento (sviluppo_ricollaudo)"
    if est is None:
        return "le estensioni non ci sono"
    if sv is None:
        return "il lavoro non è di uno sviluppo"
    if getattr(sv, "gioco", False) or getattr(lav, "gioco", False):
        return "un gioco"
    if str(getattr(lav, "livello", "amministra") or "amministra") != "amministra":
        return "le correzioni sono di chi amministra"
    if (getattr(lav, "input", None) is not None or getattr(lav, "file_utente", None) is not None
            or getattr(lav, "input_testo", "")):
        return "un file della persona nel lavoro"
    if not casi_da_riprovare(sv, 1):
        return "nessun collaudo da riprovare"
    return ""


def ricollaudo(cfg, est, svs, sv, lav, sandbox, log=print, resta_tempo=None) -> str | None:
    """Il ricollaudo alla consegna: None (la consegna va avanti) o il messaggio che la riporta
    all'agente. Una volta per lavoro (`lav.ricollaudo_fatto`); l'esito resta in
    `lav.ricollaudo` (per la frase «è pronto» e la scheda) e in `sv.ricollaudi`."""
    if getattr(lav, "ricollaudo_fatto", False):
        return None
    perche = saltato(cfg, est, sv, lav)
    if perche:
        if perche != "nessun collaudo da riprovare" or getattr(lav, "correzione", False):
            nota(lav, "ricollaudo_saltato", log, perche)
        return None
    if not est.pronto():
        nota(lav, "ricollaudo_saltato", log, "il contenitore non è pronto")
        return None
    lav.ricollaudo_fatto = True
    from .estensioni.manifesto import ManifestoNonValido, restringi_per_sonda, valida
    try:
        file = _file_della_consegna(sandbox)
        m = valida(json.loads(file.get("manifesto.json", b"").decode("utf-8") or "null"),
                   float(getattr(cfg, "estensioni_tempo_max_s", 30)),
                   int(getattr(cfg, "estensioni_memoria_max_mb", 512)))
    except (ValueError, ManifestoNonValido, OSError) as e:
        nota(lav, "ricollaudo_saltato", log, f"manifesto: {e}"[:80])
        return None
    if m.get("scheda"):
        nota(lav, "ricollaudo_saltato", log, "un gioco")
        return None
    file.pop("manifesto.json", None)
    noti = host_noti(sv, est.archivio, lav)
    ristretto = restringi_per_sonda(m, noti)
    casi = casi_da_riprovare(sv, int(getattr(cfg, "sviluppo_ricollaudo_max", 3) or 3))
    cart = Path(est.archivio.cartella) / "ricollaudi" / (
        f"{getattr(lav, 'id', 'L')}-{time.strftime('%Y%m%d-%H%M%S')}")
    vecchio_passo = getattr(lav, "passo", "")
    lav.passo = "riprova la versione con i casi della persona"
    esiti = []
    try:
        for rel, dati in file.items():
            p = cart / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(dati)
        # Il runtime legge il manifesto dalla cartella: quello ristretto
        (cart / "manifesto.json").write_text(json.dumps(ristretto, ensure_ascii=False),
                                             encoding="utf-8")
        from .tools.sviluppo import _argomenti
        origine = {"lavoro": getattr(lav, "id", None), "sviluppo": getattr(sv, "id", None),
                   "persona": getattr(lav, "persona", None),
                   "persona_nome": getattr(lav, "persona_nome", None)}
        for c in casi:
            argomenti = c.get("argomenti") or _argomenti(m, c.get("dati") or "")
            r = est.prova_bozza(cart, ristretto, dict(argomenti or {}), origine)
            if "saltato" in r:
                nota(lav, "ricollaudo_saltato", log, r["saltato"])
                lav.passo = vecchio_passo
                lav.ricollaudo_fatto = False if not esiti else True
                if not esiti:
                    return None
                break
            ok, motivo = va(c, r)
            esiti.append({"caso": c, "r": r, "va": ok, "motivo": motivo})
    except OSError as e:
        nota(lav, "ricollaudo_saltato", log, f"file: {e}"[:80])
        return None
    finally:
        for _ in range(5):
            shutil.rmtree(cart, ignore_errors=True)
            if not cart.exists():
                break
            time.sleep(0.2)
    if not esiti:
        return None
    vanno = all(e["va"] for e in esiti)
    nota(lav, "ricollaudo_fatto", log, f"{sum(e['va'] for e in esiti)} su {len(esiti)} vanno")
    dati_detti = [detto(e["caso"]) for e in esiti]
    lav.ricollaudo = {"casi": dati_detti, "vanno": vanno,
                      "non_vanno": [d for d, e in zip(dati_detti, esiti) if not e["va"]],
                      "quando": time.time()}
    voce = {"quando": time.time(), "lavoro": getattr(lav, "id", None),
            "versione": "consegna", "casi": [
                {"dati": d, "va": e["va"], "esito": _esito_testo(e["r"]),
                 "perche": e["motivo"]} for d, e in zip(dati_detti, esiti)]}
    if svs is not None:
        with svs._lock:
            lista = list(getattr(sv, "ricollaudi", None) or [])
            lista.append(voce)
            sv.ricollaudi = lista[-MAX_RICOLLAUDI_SV:]
        svs._salva()
        try:
            svs.agli_schermi(sv)
        except Exception:  # noqa: BLE001
            pass
    if vanno:
        lav.passo = ("riprovata con " + ", ".join(f"«{d}»" for d in dati_detti) + ": ora va"
                     + ("nno" if len(dati_detti) > 1 else ""))
        return None
    lav.passo = (f"riprovata con i casi della persona: {len(lav.ricollaudo['non_vanno'])} su "
                 f"{len(esiti)} non va ancora")
    nota(lav, "ricollaudo_non_va", log, ", ".join(lav.ricollaudo["non_vanno"])[:80])
    if resta_tempo is not None and not resta_tempo():
        # Niente più giro per correggere: la consegna va avanti e la frase lo dice
        lav.ricollaudo["tardi"] = True
        return None
    lav.ricollaudo["rimandata"] = True
    return messaggio_agente(sv, esiti)


def messaggio_agente(sv, esiti: list[dict]) -> str:
    """Il messaggio che riporta la consegna all'agente: i casi che non vanno, la traccia nuova
    e il confronto con i collaudi riusciti, ciò che viene dai siti in busta."""
    from .provenienza import racchiudi
    from .sviluppo import Sviluppi, confronto
    ko = [e for e in esiti if not e["va"]]
    righe = [f"Prima di consegnare ho riprovato la tua versione con i casi della persona: "
             f"{len(ko)} su {len(esiti)} non va ancora."]
    pseudo, avvisi = [], set()
    for e in esiti:
        c, r = e["caso"], e["r"]
        dati = detto(c)
        if not e["va"]:
            righe.append(f"«{dati}» → «{_esito_testo(r)[:160]}» ({e['motivo']}).")
        avvisi |= {x["avviso"] for x in r.get("traccia") or () if x.get("avviso")}
        pseudo.append({"quando": time.time(), "dati": dati, "ok": bool(e["va"]),
                       "giudizio": "" if e["va"] else e["motivo"],
                       "esito": _esito_testo(r), "versione": "consegnata",
                       "argomenti": c.get("argomenti"),
                       "rete": [dict(x) for x in (r.get("traccia") or ())]})
    if avvisi:
        righe.append("ATTENZIONE, dalla porta di Calliope: " + " ".join(
            a.rstrip(".") + "." for a in sorted(avvisi)))
    traccia = []
    for p in pseudo:
        tr = Sviluppi.righe_traccia(p)
        if tr:
            traccia.append(f"caso «{p['dati']}»:")
            traccia += ["  " + x for x in tr]
    if traccia:
        righe.append("Traccia di rete della tua versione (richieste vere fatte dalla porta di "
                     "Calliope):\n" + racchiudi("web", "\n".join(traccia),
                                                titolo="traccia di rete"))
    diff = confronto(list(getattr(sv, "collaudi", None) or []) + pseudo)
    if diff:
        righe.append(diff)
    righe.append("Correggi e consegna di nuovo. La seconda consegna non la riprovo: va alla "
                 "persona così com'è.")
    return "\n".join(righe)
