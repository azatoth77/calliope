"""
Scarico e lettura dei feed (13/10/2026): libreria standard, nessuna dipendenza nuova
(decisione di chi amministra, ricerca del 13/10 § 5).

Scarico (`scarica`): solo http e https verso indirizzi pubblici (gli stessi controlli delle
pagine dell'agente, calliope/web/pagina.py), al più MAX_BYTE, **niente compressione** accettata
(`Accept-Encoding: identity`; una risposta compressa si rifiuta: niente bombe), richieste
condizionate con ETag e Last-Modified (304 = niente di nuovo), User-Agent onesto, certificato
sempre verificato.

Lettura (`leggi`): RSS 2.0 e Atom con `xml.etree`, che non risolve le entità esterne; un
feed con `<!ENTITY` si rifiuta prima del parser (quello che farebbe defusedxml: nessun feed
vero ne ha, e l'Expat 2.6 della DGX non basta contro le espansioni). Il testo che esce è
ancora **non fidato**: lo ripuliscono pulizia.py e web.servizio.ripulisci_testo.

Date: RFC 822, ISO 8601 e le date in italiano («mar, 13 ott 2026 13:10:00 GMT», Sky TG24 e
Il Messaggero); con `fuso` del feed l'ora si legge come ora italiana anche se dice GMT (Sky
TG24, § 1.4 della ricerca); le date nel futuro si riportano ad adesso.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import http.client
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin

from ..web.pagina import (PaginaNonLetta, PaginaVietata, _Connessione, _ConnessioneTLS,
                          controlla_url, risolvi_pubblico)

UA = "Calliope/0.3 (lettore di feed personale)"
MAX_BYTE = 2_000_000          # il feed più grande provato il 13/10 è di 379 kB
TIMEOUT_S = 10.0
UTC = dt.timezone.utc


class FeedNonLetto(Exception):
    """Il feed non si è potuto scaricare o leggere (il motivo è il messaggio)."""


# ─────────────────────────── scarico ───────────────────────────

def scarica(url: str, etag: str = "", modificato: str = "", max_byte: int = MAX_BYTE,
            timeout_s: float = TIMEOUT_S, eccezioni=frozenset(), porte=(80, 443),
            risolutore=None, max_rimandi: int = 3, contesto_tls=None) -> dict:
    """{"stato": 200 | 304, "dati": bytes, "etag", "modificato", "url"} o FeedNonLetto.
    `eccezioni`, `porte`, `risolutore` e `contesto_tls` servono solo alle prove."""
    fine = time.monotonic() + timeout_s
    ctx = contesto_tls or ssl.create_default_context()
    for _ in range(max_rimandi + 1):
        try:
            schema, host, porta, path = controlla_url(url, porte)
            ip = risolvi_pubblico(host, porta, (), eccezioni, risolutore)
        except (PaginaVietata, PaginaNonLetta) as e:
            raise FeedNonLetto(str(e)) from None
        resto = max(0.5, fine - time.monotonic())
        conn = (_ConnessioneTLS(host, ip, porta, resto, ctx) if schema == "https"
                else _Connessione(host, ip, porta, resto))
        try:
            intest = {"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, "
                      "application/xml;q=0.9, text/xml;q=0.9, */*;q=0.1",
                      "Accept-Encoding": "identity", "Connection": "close"}
            if etag:
                intest["If-None-Match"] = etag
            if modificato:
                intest["If-Modified-Since"] = modificato
            conn.request("GET", path, headers=intest)
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                dove = r.getheader("Location")
                r.close()
                if not dove:
                    raise FeedNonLetto("reindirizzamento senza destinazione")
                url = urljoin(url, dove)
                continue
            if r.status == 304:
                return {"stato": 304, "dati": b"", "etag": etag, "modificato": modificato,
                        "url": url}
            if r.status != 200:
                raise FeedNonLetto(f"il sito ha risposto {r.status}")
            cod = (r.getheader("Content-Encoding") or "identity").lower().strip()
            if cod not in ("identity", ""):
                raise FeedNonLetto("risposta compressa: non la accetto")
            tipo = (r.getheader("Content-Type") or "").lower()
            if tipo.startswith(("image/", "audio/", "video/")):
                raise FeedNonLetto("non è un feed")
            lung = r.getheader("Content-Length")
            if lung and lung.isdigit() and int(lung) > max_byte:
                raise FeedNonLetto("feed troppo grande")
            dati = bytearray()
            while True:
                resto = fine - time.monotonic()
                if resto <= 0:
                    raise FeedNonLetto("tempo scaduto")
                if conn.sock is not None:
                    conn.sock.settimeout(max(0.05, resto))
                pezzo = r.read1(65536)
                if not pezzo:
                    break
                dati += pezzo
                if len(dati) > max_byte:
                    raise FeedNonLetto("feed troppo grande")
            return {"stato": 200, "dati": bytes(dati), "url": url,
                    "etag": (r.getheader("ETag") or "")[:200],
                    "modificato": (r.getheader("Last-Modified") or "")[:100]}
        except (socket.timeout, TimeoutError):
            raise FeedNonLetto("tempo scaduto") from None
        except ssl.SSLError:
            # Mai la verifica spenta: il feed si salta e si riprova al giro dopo
            raise FeedNonLetto("certificato non valido") from None
        except FeedNonLetto:
            raise
        except (OSError, http.client.HTTPException):
            raise FeedNonLetto("collegamento non riuscito") from None
        finally:
            conn.close()
    raise FeedNonLetto("troppi reindirizzamenti")


# ─────────────────────────── date ───────────────────────────

_MESI = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8,
         "set": 9, "ott": 10, "nov": 11, "dic": 12}
_DATA_IT = re.compile(
    r"^\s*(?:(?:lun|mar|mer|gio|ven|sab|dom)[a-zì]*\.?,?\s+)?(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+"
    r"(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([A-Za-z]{1,5}|[+-]\d{2}:?\d{2})?\s*$", re.I)


def _ultima_domenica(anno: int, mese: int) -> dt.date:
    d = dt.date(anno, mese, 31 if mese in (3, 10) else 30)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def _ora_legale_utc(t: dt.datetime) -> bool:
    """`t` (UTC, senza fuso) è nell'ora legale europea? (dall'ultima domenica di marzo
    all'ultima di ottobre, alle 01:00 UTC; senza tzdata, che su Windows manca)."""
    inizio = dt.datetime.combine(_ultima_domenica(t.year, 3), dt.time(1))
    fine = dt.datetime.combine(_ultima_domenica(t.year, 10), dt.time(1))
    return inizio <= t < fine


def roma_a_utc(locale: dt.datetime) -> dt.datetime:
    """Un'ora italiana senza fuso → datetime UTC."""
    t = locale.replace(tzinfo=None)
    estiva = t - dt.timedelta(hours=2)
    if _ora_legale_utc(estiva):
        return estiva.replace(tzinfo=UTC)
    return (t - dt.timedelta(hours=1)).replace(tzinfo=UTC)


def utc_a_roma(t: dt.datetime) -> dt.datetime:
    """Un datetime (con fuso, o UTC senza) → ora italiana senza fuso."""
    u = t.astimezone(UTC).replace(tzinfo=None) if t.tzinfo else t
    return u + dt.timedelta(hours=2 if _ora_legale_utc(u) else 1)


def leggi_data(testo: str, fuso: str = "") -> dt.datetime | None:
    """La data di una voce (UTC, con fuso) o None. `fuso` «Europe/Rome»: l'ora scritta è
    italiana anche se dice GMT o UTC (Sky TG24)."""
    s = str(testo or "").strip()
    if not s:
        return None
    italiana = fuso.lower() in ("europe/rome", "italia", "italiana")
    d, etichetta = None, ""
    m = _DATA_IT.match(s)
    if m and m.group(2).lower()[:3] in _MESI:
        try:
            d = dt.datetime(int(m.group(3)), _MESI[m.group(2).lower()[:3]], int(m.group(1)),
                            int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
        except ValueError:
            return None
        etichetta = (m.group(7) or "").upper()
        mm = re.match(r"([+-])(\d{2}):?(\d{2})$", etichetta)
        if mm and not italiana:
            off = dt.timedelta(hours=int(mm.group(2)), minutes=int(mm.group(3)))
            return d.replace(tzinfo=dt.timezone(off if mm.group(1) == "+" else -off))
        if italiana or etichetta in ("CET", "CEST"):
            return roma_a_utc(d)
        return d.replace(tzinfo=UTC)
    try:
        d = email.utils.parsedate_to_datetime(s)
        etichetta = s.rsplit(" ", 1)[-1].upper()
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            etichetta = "Z" if d.tzinfo is not None and not d.utcoffset() else ""
        except ValueError:
            return None
    if italiana and (d.tzinfo is None or etichetta in ("GMT", "UTC", "Z", "+0000", "-0000",
                                                        "UT")):
        return roma_a_utc(d.replace(tzinfo=None))
    if d.tzinfo is None:
        return d.replace(tzinfo=UTC)
    return d


# ─────────────────────────── lettura ───────────────────────────

_ENTITA = re.compile(rb"<!\s*ENTITY", re.I)
_NS = {"content": "http://purl.org/rss/1.0/modules/content/",
       "dc": "http://purl.org/dc/elements/1.1/"}
_ATOM = "{http://www.w3.org/2005/Atom}"

# Caratteri letti di un campo HTML (#133, 17/10): il sommario se ne tiene 600, ma un tag
# enorme in testa (un'immagine in data: base64, un srcset di trenta immagini) non deve far
# perdere il paragrafo dopo; il parser è lineare (misure nella prova), il tetto tiene breve
# anche il caso peggiore su un input costruito apposta (dato non fidato)
HTML_MAX = 100_000
# In coda, ciò che il parser non ha chiuso: un tag troncato (nome e attributi in ASCII, almeno
# uno con «=», anche con un valore fra virgolette aperto) o un commento troncato si buttano;
# tutto il resto resta testo («x<y», «Saldi <a partire da 5 euro, qualità=prezzo»). Gruppi
# atomici `(?>…)` (Python ≥ 3.11): «a = b» si legge come «a» con valore «b» oppure «a» con
# valore vuoto e poi l'attributo «b», e senza gruppi atomici le letture possibili crescono come
# 2^n (seconda revisione della PR #137: 1,5 s con 22 attributi, minuti con 30)
_TAG_TRONCO = re.compile(
    r"^<(?:!--.*|[A-Za-z][\w:.-]*(?>\s+[\w:.-]+(?>\s*=\s*(?:\"[^\"]*\"?|'[^']*'?|"
    r"[^\s\"'<>]*))?)*\s*/?)$", re.S | re.A)
# Ripiego se il parser solleva un'eccezione: lineare anche con molti «<» senza «>»
_TAG_RIPIEGO = re.compile(r"<[^<>]*>")
# Elementi saltati col loro contenuto: non sono testo che si legge
_SALTATI = frozenset({"script", "style", "noscript", "template", "iframe"})
# Codice: se resta aperto fino alla fine, il testo saltato resta buttato
_CODICE = frozenset({"script", "style"})
# Elementi senza chiusura: un attributo «hidden» su questi non nasconde altro
_VUOTI = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                    "param", "source", "track", "wbr"})
# Elementi che si chiudono da soli e non si annidano: un altro dello stesso nome chiude quello
# nascosto («<p hidden>x<p>y» → «y»), senza contare la profondità
_AUTOCHIUSI = frozenset({"p", "li", "option", "optgroup", "dt", "dd", "tr", "td", "th", "rp",
                         "rt", "thead", "tbody", "tfoot", "colgroup", "caption"})
_DISPLAY_NONE = re.compile(r"display\s*:\s*none", re.I)


def _troncato(resto: str) -> bool:
    return resto.startswith("<!--") or ("=" in resto and bool(_TAG_TRONCO.match(resto)))


def _nascosto(attrs) -> bool:
    for k, v in attrs:
        if k == "hidden" or (k == "style" and v and _DISPLAY_NONE.search(v)):
            return True
    return False


class _SoloTesto(HTMLParser):
    """Tiene i soli dati di testo, con le entità risolte; salta script, style, noscript,
    template, iframe e gli elementi con «hidden» o «display:none»; ogni tag diventa uno
    spazio (come faceva la regola di prima: «<b>Ro</b>ma» → «Ro ma»). Il testo saltato si
    tiene da parte: se l'elemento resta aperto fino alla fine (non era un elemento nascosto
    ma un tag rotto) torna testo, tranne per script e style (`finito`)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pezzi: list[str] = []
        self.saltati: list[str] = []
        self.salta_tag: str | None = None   # l'elemento saltato che si sta attraversando
        self.salta_prof = 0                 # quanti dello stesso nome aperti dentro

    def _chiudi_salto(self):
        self.salta_tag, self.salta_prof, self.saltati = None, 0, []

    def handle_starttag(self, tag, attrs):
        if self.salta_tag is not None and tag == self.salta_tag:
            if tag in _AUTOCHIUSI:
                self._chiudi_salto()        # «<p hidden>x<p>y»: il secondo chiude il primo
            else:
                self.salta_prof += 1
        if self.salta_tag is None:
            if tag in _SALTATI or (tag not in _VUOTI and _nascosto(attrs)):
                self.salta_tag, self.salta_prof, self.saltati = tag, 1, []
            self.pezzi.append(" ")
        else:
            self.saltati.append(" ")

    def handle_startendtag(self, tag, attrs):
        (self.pezzi if self.salta_tag is None else self.saltati).append(" ")

    def handle_endtag(self, tag):
        if tag == self.salta_tag:
            self.salta_prof -= 1
            if self.salta_prof <= 0 or tag in _AUTOCHIUSI:
                self._chiudi_salto()
        (self.pezzi if self.salta_tag is None else self.saltati).append(" ")

    def handle_data(self, data):
        (self.pezzi if self.salta_tag is None else self.saltati).append(data)

    def finito(self) -> bool:
        """A fine lettura: rimette il testo di un elemento saltato rimasto aperto (non script
        né style). Vero se la coda non letta va trattata come testo."""
        if self.salta_tag is None:
            return True
        if self.salta_tag in _CODICE:
            return False
        self.pezzi.extend(self.saltati)
        self._chiudi_salto()
        return True


def _senza_tag(t: str) -> str:
    """Un passaggio del parser HTML della libreria standard (#133): toglie i tag di qualunque
    lunghezza, mentre un «<» che non apre un tag («<5 gradi») resta testo. Non si chiama
    close(): la coda non chiusa la decide `_troncato`, uguale in ogni versione di Python."""
    p = _SoloTesto()
    try:
        p.feed(t)
    except Exception:  # noqa: BLE001 — il testo è non fidato: mai un'eccezione al lettore
        return html.unescape(_TAG_RIPIEGO.sub(" ", t))
    resto = p.rawdata
    if p.finito() and resto and not _troncato(resto):
        p.pezzi.append(html.unescape(resto))
    return "".join(p.pezzi)


def testo_semplice(s) -> str:
    """Senza marcatura HTML e con le entità risolte, spazi normalizzati. Dal 17/10 (#133) con
    `html.parser` al posto di `<[^>]{0,500}>`, che lasciava intero un `<img srcset=…>` più
    lungo di 500 caratteri: il sommario diventava il testo del tag."""
    t = _senza_tag(str(s or "")[:HTML_MAX])
    if "<" in t:
        # L'HTML scritto come &lt;p&gt; nel feed: un secondo passaggio, con le «&» già
        # risolte protette (le entità si risolvono una volta sola, come prima)
        t = _senza_tag(t.replace("&", "&amp;"))
    return re.sub(r"\s+", " ", t).strip()


def _testo(el, path: str) -> str:
    x = el.find(path, _NS)
    return (x.text or "") if x is not None else ""


def leggi(dati: bytes) -> list[dict]:
    """Le voci di un feed RSS 2.0 o Atom: [{"titolo", "sommario", "link", "data_grezza"}],
    testo ancora da ripulire. FeedNonLetto se il feed ha entità, non è XML o non è un feed."""
    if not isinstance(dati, (bytes, bytearray)) or not dati.strip():
        raise FeedNonLetto("feed vuoto")
    if len(dati) > MAX_BYTE:
        raise FeedNonLetto("feed troppo grande")
    if _ENTITA.search(dati):
        raise FeedNonLetto("feed con entità XML: rifiutato")
    try:
        radice = ET.fromstring(bytes(dati).lstrip())
    except ET.ParseError as e:
        raise FeedNonLetto(f"XML non valido ({str(e)[:60]})") from None
    out = []
    if radice.tag == "rss":
        canale = radice.find("channel")
        for it in (canale.findall("item") if canale is not None else ()):
            somm = _testo(it, "description") or _testo(it, "content:encoded")
            link = _testo(it, "link").strip()
            if not link:
                g = it.find("guid")
                if g is not None and (g.text or "").startswith(("http://", "https://")):
                    link = g.text.strip()
            out.append({"titolo": testo_semplice(_testo(it, "title")),
                        "sommario": testo_semplice(somm), "link": link,
                        "data_grezza": (_testo(it, "pubDate") or _testo(it, "dc:date")).strip()})
    elif radice.tag == _ATOM + "feed":
        for e in radice.findall(_ATOM + "entry"):
            link = ""
            for ln in e.findall(_ATOM + "link"):
                if ln.get("rel") in (None, "alternate") and ln.get("href"):
                    link = ln.get("href").strip()
                    break
            somm = e.findtext(_ATOM + "summary") or e.findtext(_ATOM + "content") or ""
            out.append({"titolo": testo_semplice(e.findtext(_ATOM + "title")),
                        "sommario": testo_semplice(somm), "link": link,
                        "data_grezza": (e.findtext(_ATOM + "published")
                                        or e.findtext(_ATOM + "updated") or "").strip()})
    else:
        raise FeedNonLetto("non è un feed RSS o Atom")
    return out
