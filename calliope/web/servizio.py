"""
La ricerca su internet di Calliope (03/10/2026): SearXNG sulla DGX, solo quando internet c'è.

Calliope lavora offline (principio 9): questa è un'aggiunta facoltativa, per l'attualità
che la biblioteca non può sapere (meteo, notizie, risultati, orari, prezzi). Senza
SearXNG configurato, o con `online: false`, il tool non c'è e il registro delle capacità lo
dice; con SearXNG giù o senza internet il tool risponde con una frase pronta, senza inventare.

Tre regole, da qui in giù:
- **le domande escono di casa**: passano dal Ripulitore (privacy.py), vanno a SearXNG in POST
  (niente domanda in un URL), non restano nel registro dei turni (ToolSpec.segreti);
- **il testo che torna non è fidato**: si ripulisce (niente tag, niente nomi di tool con «_»,
  lunghezze massime) e arriva al modello marcato come dati di un sito, non istruzioni;
  Brain blocca le azioni nella stessa risposta e lo toglie dalla storia a risposta finita;
- **un tetto**: al più `web_max_minuto` ricerche al minuto (voce e agente insieme), per non
  farsi bloccare dai motori.
"""

import collections
import datetime
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .pagina import PaginaNonLetta, PaginaVietata, estrai_testo, reti, scarica
from .privacy import Ripulitore

# Nomi dei siti più comuni, per la voce («secondo l'ANSA»): mai l'indirizzo
_SITI = {
    "ansa.it": "ANSA", "ilmeteo.it": "iLMeteo", "3bmeteo.com": "3B Meteo",
    "meteo.it": "Meteo.it", "meteoam.it": "il servizio meteo dell'Aeronautica",
    "ilmeteo.net": "Meteored", "repubblica.it": "la Repubblica",
    "corriere.it": "il Corriere della Sera", "lastampa.it": "La Stampa",
    "ilsole24ore.com": "il Sole 24 Ore", "rainews.it": "RaiNews", "rai.it": "la Rai",
    "tgcom24.mediaset.it": "TGCom24", "skytg24.it": "Sky TG24", "ilpost.it": "il Post",
    "gazzetta.it": "la Gazzetta dello Sport", "corrieredellosport.it":
    "il Corriere dello Sport", "tuttosport.com": "Tuttosport", "diretta.it": "Diretta",
    "flashscore.it": "Flashscore", "wikipedia.org": "Wikipedia", "ilfattoquotidiano.it":
    "il Fatto Quotidiano", "fanpage.it": "Fanpage", "today.it": "Today",
    "quattroruote.it": "Quattroruote", "trenitalia.com": "Trenitalia", "italotreno.com":
    "Italo", "viaggiatreno.it": "ViaggiaTreno", "agi.it": "AGI", "adnkronos.com": "Adnkronos",
    "ilgiornale.it": "il Giornale", "ilmessaggero.it": "il Messaggero", "virgilio.it":
    "Virgilio", "sport.virgilio.it": "Virgilio Sport", "mise.gov.it": "il ministero",
    "mimit.gov.it": "il ministero delle Imprese", "governo.it": "il sito del Governo",
    "istat.it": "l'Istat", "protezionecivile.gov.it": "la Protezione civile",
}


def nome_sito(url: str) -> str:
    """«ANSA», «iLMeteo», altrimenti il dominio senza «www.» e senza la parte finale."""
    host = (urlsplit(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for dominio, nome in sorted(_SITI.items(), key=lambda x: -len(x[0])):
        if host == dominio or host.endswith("." + dominio):
            return nome
    parti = host.split(".")
    if len(parti) >= 3 and parti[-2] in ("co", "com", "gov", "org", "ac", "edu", "net"):
        return parti[-3]                     # «bbc.co.uk» → bbc
    if len(parti) >= 2:
        return parti[-2]                     # «comune.torino.it» → torino
    return host or "un sito"


# Testo non fidato: niente marcature, niente nomi di tool, niente caratteri di controllo
_TAG = re.compile(r"<[^>]{0,200}>")
_CONTROLLO = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏ -‮⁠-⁯﻿]")


def ripulisci_testo(testo, max_caratteri: int) -> str:
    """Testo di un sito, pronto per il modello: senza tag, senza «` * #», con i nomi tipo
    casa_comando spezzati («casa comando», che non è il nome di un tool), accorciato."""
    t = _CONTROLLO.sub(" ", str(testo or ""))
    t = _TAG.sub(" ", t)
    t = re.sub(r"[`*#|{}\[\]<>]", " ", t)
    t = re.sub(r"(?<=\w)_(?=\w)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_caratteri:
        t = t[:max_caratteri].rsplit(" ", 1)[0] + " …"
    return t


# La data in testa all'estratto, come la scrivono i motori: «27 gen 2025 · …», «1 giorno fa ·
# …». Il 03/10 il primo risultato di «meteo Milano domani» era un estratto di iLMeteo del
# gennaio 2025 («Pioggia diffusa… giovedì 13 marzo… tra 8 e 15 gradi») e gemma4 l'ha detto
# come previsione di domani, nonostante «se un testo ha una data vecchia…» nel risultato.
# Conversione della forma (principio 10): la data esce dal testo e diventa un campo, e un
# estratto più vecchio di GIORNI_VECCHIO va in fondo con «vecchio».
_MESI = {m: i for i, m in enumerate(("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago",
                                     "set", "ott", "nov", "dic"), 1)}
_DATA_ASSOLUTA = re.compile(r"^\s*(\d{1,2})\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)"
                            r"[a-zà]*\.?\s+(\d{4})\s*[·\-–—]\s*", re.I)
_DATA_RELATIVA = re.compile(r"^\s*(\d+)\s+(minut[oi]|or[ae]|giorn[oi]|settiman[ae]|mes[ei]|"
                            r"ann[oi])\s+fa\s*[·\-–—]\s*", re.I)
_GIORNI = {"minut": 0, "or": 0, "giorn": 1, "settiman": 7, "mes": 30, "ann": 365}
GIORNI_VECCHIO = 3


def data_estratto(testo: str, pubblicato: str = "", oggi: datetime.date | None = None
                  ) -> tuple[str, str, int | None]:
    """(testo senza la data in testa, data come detta, giorni fa o None)."""
    oggi = oggi or datetime.date.today()
    m = _DATA_ASSOLUTA.match(testo or "")
    if m:
        try:
            d = datetime.date(int(m.group(3)), _MESI[m.group(2).lower()], int(m.group(1)))
            return testo[m.end():], f"{d.day} {m.group(2).lower()} {d.year}", (oggi - d).days
        except ValueError:
            pass
    m = _DATA_RELATIVA.match(testo or "")
    if m:
        unita = next(v for k, v in _GIORNI.items() if m.group(2).lower().startswith(k))
        return testo[m.end():], f"{m.group(1)} {m.group(2).lower()} fa", int(m.group(1)) * unita
    if pubblicato:
        try:
            d = datetime.date.fromisoformat(pubblicato[:10])
            return testo, d.isoformat(), (oggi - d).days
        except ValueError:
            pass
    return testo, "", None


# Il tema di una ricerca di notizie (09/10, caso della DGX: «Sentimi le notizie di sport» →
# risultati senza sport). Nella categoria news di SearXNG la parola «notizie» non filtra niente
# (sono già notizie) e pesa come un tema: con «notizie di economia» uscivano titoli con
# «notizia» dentro («buone notizie per Allegri», il Nobel), con «economia» solo economia
# (misura sul SearXNG della DGX, docs/aree/biblioteca.md). Conversione della forma di una
# scelta del modello (principio 10): si tolgono le parole che dicono «notizie» e le
# preposizioni rimaste in testa o in coda; il tema resta come l'ha scritto il modello. Se non
# resta niente («ultime notizie») la domanda è «notizie». Regola `notizie_tema`
_PAROLE_NOTIZIE = re.compile(
    r"(?<![\w'’])(?:(?:le|la|una|delle|alcune)\s+)?(?:(?:ultim[ei]|principali|nuove)\s+)?"
    r"(?:notizi[ae]|news|novità)(?![\w'’])"
    r"|(?<![\w'’])(?:l[’']\s*)?(?:ultim[’']ora|ultima\s+ora|aggiornament[oi]|in\s+tempo\s+reale)"
    r"(?![\w'’])", re.I)
# Solo le preposizioni rimaste attaccate a ciò che si è tolto («notizie di sport» → «di
# sport»): mai gli articoli, che fanno parte dei nomi («La Spezia», «Il Sole 24 Ore»)
_PREPOSIZIONI = (r"(?:di|del|dello|della|dei|degli|delle|dell[’']|su|sul|sullo|sulla|sui|"
                 r"sugli|sulle|sull[’']|da|dal|dallo|dalla|dai|dagli|dalle|dall[’']|"
                 r"nel|nella|nei|nelle|in|e|ed)")
_TESTA = re.compile(r"^(?:" + _PREPOSIZIONI + r"(?:\s+|(?<=[’'])|$))+", re.I)
_CODA = re.compile(r"(?:\s+" + _PREPOSIZIONI + r")+$", re.I)
# Le notizie dell'ultima settimana (time_range di SearXNG): via le pagine di anni fa di
# DuckDuckGo News («sport» senza periodo: 2021 e 2022 tra i primi). «day» è troppo stretto:
# con «economia» Bing News dava titoli in portoghese e spagnolo, e per un paese piccolo
# non resta niente. ANSA non ha date e non ne tiene conto
PERIODO_NOTIZIE = "week"


def tema_notizie(domanda: str) -> str:
    """«notizie di sport» → «sport», «ultime notizie economia» → «economia», «le notizie di
    oggi» → «oggi», «ultime notizie» → «notizie»; «sport», «La Spezia» restano come sono."""
    q = str(domanda or "")
    t = _PAROLE_NOTIZIE.sub(" ", q)
    if t == q:
        return q
    t = re.sub(r"\s+", " ", t).strip(" ,;:.-")
    t = _CODA.sub("", _TESTA.sub("", t)).strip(" ,;:.-")
    return t if len(re.sub(r"\W", "", t)) >= 2 else "notizie"


# Il tema dalla frase di chi parla (09/10 sera, caso vero della DGX alle 21:04: «Le notizie di
# sport» → web_cerca({'tipo': 'notizie'}) senza domanda → notizie generali e «le notizie
# sportive non sono arrivate»). Il modello ha già scelto le notizie e ha lasciato vuoto il tema:
# lo si prende dalle parole che seguono «notizie» nella frase, fino alla fine dell'enunciato
# (principio 10: correzione della forma di una scelta del modello, e il tema c'è solo se è
# nella frase). Si tolgono le preposizioni ai bordi (come tema_notizie, mai gli articoli dei
# nomi), «ci sono», «c'è» in testa, il tempo («di oggi», «del giorno», «recenti»), «per favore».
# Se non resta niente («le ultime notizie», «notizie di oggi»), notizie generali. Regola
# `notizie_tema_frase`
_PAROLA_NOTIZIE = re.compile(r"(?<![\w'’])(?:notizi[ae]|news|novità|aggiornament[oi])"
                             r"(?![\w'’])", re.I)
_FINE_ENUNCIATO = re.compile(r"[.,;:?!«»\"]|\s(?:e\s+)?poi\b|\se\s+(?:dimmi|dammi|anche)\b",
                             re.I)
_RIEMPITIVI = re.compile(
    r"^(?:(?:che\s+)?(?:ci\s+sono(?:\s+state)?|c['’]\s*è(?:\s+stat[oa])?|hai|abbiamo|sono\s+"
    r"uscite|di\s+cui\s+parlano)(?:\s+|$))+", re.I)
_TEMPO = (r"(?:oggi|ieri|stamattina|stamani|stasera|stanotte|adesso|giornata|giorno|"
          r"questa\s+settimana|settimana|ultime\s+ore|ora|più\s+recenti|recenti|fresche|"
          r"importanti|principali|ultime|nuove|per\s+favore|grazie|calliope)")
_TEMPO_CODA = re.compile(r"(?:^|\s+)(?:" + _PREPOSIZIONI + r"\s+)?" + _TEMPO + r"$", re.I)
_TEMPO_TESTA = re.compile(r"^(?:" + _PREPOSIZIONI + r"\s+)?" + _TEMPO + r"(?:\s+|$)", re.I)
TEMA_FRASE_PAROLE = 6           # oltre, non è un tema ma un'altra frase


def tema_dalla_frase(frase: str) -> str:
    """«Le notizie di sport» → «sport», «Che notizie ci sono da Torino?» → «Torino», «le
    notizie sportive di oggi» → «sportive»; «Le ultime notizie», «notizie di oggi», una frase
    senza «notizie» → "" (notizie generali)."""
    trovate = list(_PAROLA_NOTIZIE.finditer(str(frase or "")))
    if not trovate:
        return ""
    coda = str(frase)[trovate[-1].end():]
    fine = _FINE_ENUNCIATO.search(coda)
    t = re.sub(r"\s+", " ", coda[:fine.start()] if fine else coda).strip(" ,;:.-")
    for _ in range(8):
        prima = t
        t = _RIEMPITIVI.sub("", t).strip()
        t = _CODA.sub("", _TESTA.sub("", t)).strip(" ,;:.-")
        t = _TEMPO_TESTA.sub("", _TEMPO_CODA.sub("", t)).strip(" ,;:.-")
        if t == prima:
            break
    if len(re.sub(r"\W", "", t)) < 2 or len(t.split()) > TEMA_FRASE_PAROLE:
        return ""
    return t


# ─────────────────────────── lingua dei risultati (09/10) ───────────────────────────
# Caso vero della DGX (09/10, 12:54): «qual è la miglior salsa di pomodoro» con
# language=it-IT → Bing dava forum taiwanesi e Zhihu tra i primi (Bing ignora la lingua di
# SearXNG), DuckDuckGo i siti italiani. Si preferiscono i risultati in italiano: prima loro,
# poi gli incerti, in fondo quelli in un'altra lingua (nessuno si toglie: se mancano gli
# italiani restano gli altri). Si riconosce la lingua del risultato (un dato, non le parole
# della persona) dalle parole più comuni di titolo ed estratto e dal dominio .it.
_PAROLE_IT = frozenset(
    "il lo gli della delle degli dello dei del nella nelle nel nei alla alle allo ai al "
    "che per sono è più anche questo questa come non di un una ed perché quando dove quale "
    "qual cosa migliore migliori ecco tutti tutte essere stato stata hanno ha".split())
_PAROLE_ALTRE = frozenset(
    "the and of to is are with for this that what how best your from "      # inglese
    "el los las y para por es está qué cómo mejor muy "                       # spagnolo
    "les et est pour une des avec dans sur qui meilleur "                    # francese
    "der die das und ist mit für nicht ein eine "                            # tedesco
    "os não são uma com melhor".split())                                     # portoghese
_NON_LATINO = re.compile(r"[\u0400-\u04ff\u0590-\u06ff\u0e00-\u0e7f\u3040-\u30ff"
                         r"\u3400-\u9fff\uac00-\ud7af]")
# La domanda chiede un'altra lingua o siti stranieri («in inglese», «siti spagnoli»,
# «giornali stranieri», «site:…»): allora nessuna preferenza e language=all. È la forma
# della domanda già scritta dal modello, non la frase della persona. «Calciatori stranieri»,
# «notizie internazionali», «ristorante inglese» non chiedono un'altra lingua
ALTRA_LINGUA = re.compile(
    r"\b(?:in|en)\s+(?:inglese|spagnolo|francese|tedesco|portoghese|russo|cinese|"
    r"giapponese|arabo|olandese|greco|polacco|coreano|english|spanish|french|german)\b|"
    r"\b(?:english|español|espanol|français|francais|deutsch)\b|\bsite:|"
    r"\b(?:sit[oi]|giornal[ei]|fonti|stampa)\s+(?:stranier|ester|ingles|american|spagnol|"
    r"frances|tedesc|portoghes)\w*", re.I)


def lingua_risultato(titolo: str, testo: str, url: str = "") -> str:
    """"it", "altra" o "" (non si capisce) per un risultato."""
    t = f"{titolo} {testo}"
    if len(_NON_LATINO.findall(t)) >= 3:
        return "altra"
    parole = re.findall(r"[^\W\d_]+", t.lower())
    it = sum(p in _PAROLE_IT for p in parole)
    altre = sum(p in _PAROLE_ALTRE for p in parole)
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith(".it"):
        it += 2
    if it >= 2 and it > altre:
        return "it"
    if altre >= 2 and altre > it:
        return "altra"
    return ""


def chiede_altra_lingua(domanda: str) -> bool:
    return bool(ALTRA_LINGUA.search(str(domanda or "")))


@dataclass
class Risultato:
    titolo: str
    url: str
    sito: str
    testo: str
    data: str = ""
    motori: list = field(default_factory=list)
    giorni: int | None = None          # quanti giorni fa, se la data si conosce

    @property
    def vecchio(self) -> bool:
        return self.giorni is not None and self.giorni > GIORNI_VECCHIO


class Web:
    """Ricerca (SearXNG) e lettura di pagine (pagina.py) con i tetti e i filtri di Calliope.
    Thread-safe: la usano il thread della voce e quello dei lavori dell'agente."""

    def __init__(self, cfg, ripulitore: Ripulitore | None = None, cliente=None, log=print):
        self.cfg = cfg
        self.url = str(getattr(cfg, "web_searxng_url", "") or "").rstrip("/")
        self.ripulitore = ripulitore or Ripulitore()
        self.log = log
        self.timeout_s = float(getattr(cfg, "web_timeout_s", 6.0))
        self.max_minuto = int(getattr(cfg, "web_max_minuto", 10))
        self.n_risultati = int(getattr(cfg, "web_risultati", 5))
        self.lingua = str(getattr(cfg, "web_lingua", "it-IT") or "it-IT")
        self.preferisci_lingua = bool(getattr(cfg, "web_preferisci_lingua", True))
        self.vietate = reti(getattr(cfg, "web_reti_vietate", None) or ())
        # Per le prove (un server finto su 127.0.0.1): mai da configurazione
        self.eccezioni: frozenset = frozenset()
        self.porte = (80, 443)
        self.risolutore = None
        self._cliente = cliente
        self._lock = threading.Lock()
        self._ricerche: collections.deque = collections.deque()
        self._ferma = threading.Event()       # chiusura: ferma il thread che riprova
        # Ultimo esito visto (registro delle capacità, senza rete): ok | non_provato |
        # searxng_giu | internet | errore
        self.diagnosi = {"codice": "non_provato"}
        # Il controllo quotidiano e l'aggiornamento di SearXNG (motore.py, 09/10), se c'è
        self.motore = None

    # ── collegamento ──
    def _http(self):
        if self._cliente is None:
            import httpx
            # trust_env=False: SearXNG è su 127.0.0.1, nessun proxy di sistema in mezzo
            self._cliente = httpx.Client(timeout=self.timeout_s, trust_env=False)
        return self._cliente

    def prova(self, timeout_s: float = 2.0) -> bool:
        """SearXNG risponde? (/healthz, nessuna ricerca: niente esce di casa)"""
        if not self.url:
            self.diagnosi = {"codice": "non_configurato"}
            return False
        try:
            r = self._http().get(self.url + "/healthz", timeout=timeout_s)
            ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            if self.diagnosi.get("codice") in ("non_provato", "searxng_giu", "non_configurato"):
                self.diagnosi = {"codice": "ok"}
        else:
            self.diagnosi = {"codice": "searxng_giu", "quando": time.time()}
        return ok

    @property
    def pronta(self) -> bool:
        return self.diagnosi.get("codice") not in ("searxng_giu", "non_configurato")

    def _posto(self) -> bool:
        """Il tetto delle ricerche al minuto: True se c'è posto (e lo prende)."""
        ora = time.monotonic()
        with self._lock:
            while self._ricerche and ora - self._ricerche[0] > 60:
                self._ricerche.popleft()
            if len(self._ricerche) >= self.max_minuto:
                return False
            self._ricerche.append(ora)
            return True

    # ── ricerca ──
    def cerca(self, domanda: str, tipo: str = "web", n: int | None = None,
              safesearch: int = 1) -> dict:
        """{"ok", "risultati": [Risultato], "domanda": quella mandata davvero, "tolti": tipi
        di dati tolti} oppure {"ok": False, "codice": vuota | troppe | searxng_giu |
        internet | errore}."""
        q, tolti = self.ripulitore.pulisci(domanda)
        if len(re.sub(r"\W", "", q)) < 2:
            return {"ok": False, "codice": "vuota", "tolti": tolti}
        # Le notizie: solo il tema, dell'ultima settimana (tema_notizie, PERIODO_NOTIZIE)
        tema = tema_notizie(q) if tipo == "notizie" else q
        tema_cambiato = tema != q
        q = tema
        if not self._posto():
            return {"ok": False, "codice": "troppe", "tolti": tolti}
        n = max(1, min(int(n or self.n_risultati), 10))
        t0 = time.perf_counter()
        # SafeSearch: 1 moderato; 2 rigoroso per i ragazzi 11–13 (calliope/minori.py, 05/10)
        # Un'altra lingua chiesta nella domanda: nessuna preferenza (09/10)
        altra = chiede_altra_lingua(q)
        dati = {"q": q, "format": "json", "language": "all" if altra else self.lingua,
                "safesearch": str(max(0, min(2, int(safesearch)))),
                "categories": "news" if tipo == "notizie" else "general"}
        if tipo == "notizie":
            dati["time_range"] = PERIODO_NOTIZIE
        try:
            r = self._http().post(self.url + "/search", data=dati, timeout=self.timeout_s,
                                  headers={"Accept": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            js = r.json()
        except Exception as e:  # noqa: BLE001
            # Non risponde, o risponde 5xx: SearXNG è giù (la capacità diventa «guasta»)
            giu = (type(e).__name__ in ("ConnectError", "ConnectTimeout", "RemoteProtocolError")
                   or str(e).startswith("HTTP 5"))
            self.diagnosi = {"codice": "searxng_giu" if giu else "errore", "quando": time.time(),
                             "errore": type(e).__name__}
            return {"ok": False, "codice": self.diagnosi["codice"], "tolti": tolti}
        ms = round((time.perf_counter() - t0) * 1000)
        risultati, visti = [], set()
        for x in js.get("results") or []:
            url = str(x.get("url") or "")
            if not url.startswith(("http://", "https://")) or url in visti:
                continue
            visti.add(url)
            testo, data, giorni = data_estratto(ripulisci_testo(x.get("content"), 450),
                                                str(x.get("publishedDate") or ""))
            risultati.append(Risultato(
                titolo=ripulisci_testo(x.get("title"), 150), url=url, sito=nome_sito(url),
                testo=testo[:400], data=data, giorni=giorni,
                motori=list(x.get("engines") or [x.get("engine")])))
        # I vecchi in fondo (ordine stabile); poi, a pari età, prima quelli nella lingua di
        # casa (09/10, solo con web_lingua italiana), gli incerti, le altre lingue
        preferisci = (self.preferisci_lingua and not altra
                      and self.lingua.lower().startswith("it"))
        rango = {"it": 0, "": 1, "altra": 2}
        lingue = {id(r): lingua_risultato(r.titolo, r.testo, r.url) for r in risultati}
        n_altre = sum(v == "altra" for v in lingue.values())
        risultati = sorted(risultati, key=lambda r: (
            r.vecchio, rango[lingue[id(r)]] if preferisci else 0))[:n]
        # Risposte dirette (cambi di valuta): come un risultato in testa, senza sito
        for a in (js.get("answers") or [])[:1]:
            testo = a.get("answer") if isinstance(a, dict) else a
            if testo:
                risultati.insert(0, Risultato(titolo="risposta diretta", url=str(
                    (a.get("url") if isinstance(a, dict) else "") or ""),
                    sito="il motore di ricerca", testo=ripulisci_testo(testo, 300)))
        giu = js.get("unresponsive_engines") or []
        if not risultati and giu:
            # Nessun motore ha risposto: di solito manca internet (SearXNG c'è)
            self.diagnosi = {"codice": "internet", "quando": time.time(),
                             "motori": [str(g[0]) for g in giu if g]}
            return {"ok": False, "codice": "internet", "tolti": tolti}
        self.diagnosi = {"codice": "ok", "quando": time.time()}
        return {"ok": True, "risultati": risultati, "domanda": q, "tolti": tolti, "ms": ms,
                **({"tema": True} if tema_cambiato else {}),
                **({"altra_lingua": True} if altra else {}),
                **({"lingua_preferita": n_altre} if preferisci and n_altre else {})}

    # ── pagine (per l'agente) ──
    def leggi(self, url: str, max_caratteri: int | None = None) -> dict:
        """{"ok", "titolo", "testo", "sito"} di una pagina, o {"ok": False, "errore"}."""
        maxc = int(max_caratteri or getattr(self.cfg, "web_pagina_caratteri", 8000))
        try:
            p = scarica(url, max_byte=int(getattr(self.cfg, "web_pagina_max_kb", 1024)) * 1024,
                        timeout_s=float(getattr(self.cfg, "web_pagina_timeout_s", 10.0)),
                        vietate=self.vietate, eccezioni=self.eccezioni, porte=self.porte,
                        risolutore=self.risolutore)
        except PaginaVietata as e:
            return {"ok": False, "vietata": True, "errore": str(e)}
        except PaginaNonLetta as e:
            return {"ok": False, "errore": str(e)}
        titolo, testo = estrai_testo(p["testo_grezzo"], p["tipo"], maxc)
        righe = [ripulisci_testo(r, 2000) for r in testo.split("\n")]
        return {"ok": True, "url": p["url"], "sito": nome_sito(p["url"]),
                "titolo": ripulisci_testo(titolo, 200),
                "testo": "\n".join(r for r in righe if r)[:maxc]}

    def close(self):
        self._ferma.set()
        if self._cliente is not None:
            try:
                self._cliente.close()
            except Exception:  # noqa: BLE001
                pass
