"""
Una pagina web per l'agente (strumento web_leggi), scaricata senza fidarsi di niente
(03/10/2026). Solo libreria standard: http.client, ssl, html.parser.

Contro le richieste verso la rete interna (SSRF), che un risultato o una pagina potrebbero
chiedere all'agente («leggi http://192.168.1.40/…», «http://127.0.0.1:8000/v1/…»):

- solo http e https, porte 80 e 443, niente utente e password nell'URL;
- niente nomi locali («localhost», un nome senza punti, .local, .lan, .home, .internal…);
- il nome si risolve qui e **ogni** indirizzo deve essere pubblico (`ipaddress.is_global`:
  fuori restano 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, ::1, fc00::/7,
  fe80::/10, gli IPv4 dentro IPv6 e il resto dei riservati), né in `web_reti_vietate` (la
  rete dell'ufficio, se ha indirizzi pubblici);
- la connessione va **a quell'indirizzo** (niente seconda risoluzione: un DNS che cambia
  risposta tra il controllo e la connessione non porta dentro), con il nome solo per il TLS
  (SNI e verifica del certificato) e per l'intestazione Host;
- i reindirizzamenti si seguono a mano, al più 3, e ognuno ripassa tutti i controlli;
- tempo massimo totale, dimensione massima, solo testo (HTML o testo semplice), compressione
  solo gzip e con un tetto anche sui byte decompressi (niente «bombe»);
- il testo si estrae con html.parser: niente script, stili, moduli, elementi nascosti
  (`hidden`, `display:none`, `aria-hidden`: lì si nascondono le istruzioni per i modelli),
  nessun JavaScript eseguito, nessuna risorsa collegata scaricata.

Niente proxy di sistema: la connessione è diretta (la DGX esce da sola).

Dal 05/10 (estensioni che leggono siti, `calliope/web/rete.py`) anche: gli IPv4 scritti in
forme strane nel nome («2130706433», «0x7f.1», «0177.0.0.1», «127.1») sono vietati prima di
ogni risoluzione; gli IPv4 dentro gli IPv6 di NAT64 (64:ff9b::/96) si controllano come IPv4;
una lista fissa di reti mai pubbliche si somma a `is_global` (difesa in profondità: il
significato di `is_global` è cambiato tra le versioni di Python); `host_ammesso(host)` lascia
decidere a chi chiama anche i reindirizzamenti (le estensioni: solo gli host del manifesto).
"""

import http.client
import ipaddress
import re
import socket
import ssl
import time
import zlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

_NOMI_LOCALI = (".local", ".lan", ".home", ".internal", ".localdomain", ".intranet", ".corp",
                ".home.arpa", ".localhost", ".test", ".invalid", ".example")
_TIPI = ("text/html", "application/xhtml+xml", "text/plain")


class PaginaVietata(Exception):
    """L'URL o l'indirizzo non si può leggere (rete interna, schema, porta…)."""


class PaginaNonLetta(Exception):
    """La pagina non si è potuta leggere (tempo, dimensione, tipo, errore del server)."""


# Mai pubbliche, qualunque cosa dica `is_global` (che è cambiato tra Python 3.11 e 3.13)
SEMPRE_VIETATE = tuple(ipaddress.ip_network(c) for c in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
    "255.255.255.255/32", "::/128", "::1/128", "::ffff:0:0/96", "64:ff9b:1::/48",
    "100::/64", "2001::/23", "2001:db8::/32", "2002::/16", "fc00::/7", "fe80::/10",
    "fec0::/10", "ff00::/8"))
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
# Un nome fatto solo di numeri (decimali, ottali, esadecimali) e punti: un IPv4 travestito
_NUMERICO = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*\.?$", re.I)


def reti(cidr) -> list:
    out = []
    for c in cidr or ():
        try:
            out.append(ipaddress.ip_network(str(c).strip(), strict=False))
        except ValueError:
            continue
    return out


def indirizzo_vietato(ip: str, vietate=(), eccezioni=frozenset()) -> bool:
    """True se l'indirizzo non è pubblico, o è in una rete vietata."""
    if ip in eccezioni:
        return False
    try:
        a = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return True
    if a.version == 6 and getattr(a, "scope_id", None):
        return True                      # «fe80::1%eth0»: un indirizzo con l'interfaccia
    mapped = getattr(a, "ipv4_mapped", None) or getattr(a, "sixtofour", None)
    if mapped is None and a.version == 6 and a in _NAT64:
        mapped = ipaddress.IPv4Address(int(a) & 0xFFFFFFFF)
    if mapped is not None:
        a = mapped
    if not a.is_global or a.is_multicast or a.is_reserved or a.is_unspecified:
        return True
    if any(a in n for n in SEMPRE_VIETATE if n.version == a.version):
        return True
    return any(a in n for n in vietate if n.version == a.version)


def controlla_url(url: str, porte=(80, 443)) -> tuple[str, str, int, str]:
    """(schema, nome, porta, percorso) di un URL ammesso, o PaginaVietata."""
    try:
        u = urlsplit(str(url or "").strip())
    except ValueError:
        raise PaginaVietata("indirizzo non valido") from None
    if u.scheme not in ("http", "https"):
        raise PaginaVietata("solo pagine http o https")
    if u.username or u.password or "@" in u.netloc:
        raise PaginaVietata("niente utente e password nell'indirizzo")
    host = (u.hostname or "").rstrip(".").lower()
    if not host:
        raise PaginaVietata("indirizzo senza nome")
    try:
        porta = u.port or (443 if u.scheme == "https" else 80)
    except ValueError:
        raise PaginaVietata("porta non valida") from None
    if porta not in porte:
        raise PaginaVietata("porta non ammessa")
    if not re.fullmatch(r"[a-z0-9.:-]+", host):         # IDN: si accettano solo in punycode
        try:
            host = host.encode("idna").decode("ascii").rstrip(".").lower()
        except UnicodeError:
            raise PaginaVietata("nome non valido") from None
    try:
        letterale = str(ipaddress.ip_address(host.split("%", 1)[0])) == host.split("%", 1)[0]
    except ValueError:
        letterale = False
    if not letterale:
        # «2130706433», «0x7f.1», «0177.0.0.1», «127.1»: getaddrinfo li capisce come IPv4
        # (inet_aton) e porterebbero a 127.0.0.1 senza sembrarlo
        if _NUMERICO.match(host) or ":" in host:
            raise PaginaVietata("indirizzo numerico in una forma non standard")
        if host == "localhost" or "." not in host or host.endswith(_NOMI_LOCALI):
            raise PaginaVietata("nome della rete locale")
    path = u.path or "/"
    if u.query:
        path += "?" + u.query
    return u.scheme, host, porta, path


# I caratteri ammessi così come sono nel percorso, nella query e nel frammento (RFC 3986:
# non riservati, riservati e «%» delle codifiche). Uno spazio, un accento o un carattere di
# controllo devono arrivare codificati
_URL_AMMESSI = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                         "-._~:/?#[]@!$&'()*+,;=%")
_PERCENTO = re.compile(r"%(?![0-9A-Fa-f]{2})")


def url_non_codificato(url: str) -> str:
    """"" se percorso e parametri dell'URL sono codificati; se no il messaggio per chi scrive
    il codice (08/10, caso vero della DGX: l'estensione del meteo scriveva
    «…/search?name={citta}» a mano, «Bergamo» andava e una città di due parole no; la richiesta
    partiva rotta e tornava solo «collegamento non riuscito», e in cinque versioni l'agente
    non ha mai visto la causa). Nel messaggio il nome del parametro, mai il suo valore.
    La stessa regola è in calliope/estensioni/_ospite.py (CalliopeFinta, per i test
    dell'agente): le tiene uguali prova_estensioni_rete."""
    testo = str(url or "").strip()
    try:
        u = urlsplit(testo)
    except ValueError:
        return "URL non valido: non si riesce a leggere"
    i = testo.find(u.netloc) if u.netloc else -1
    resto = testo[i + len(u.netloc):] if i >= 0 else testo
    cattivo = next((c for c in resto if c not in _URL_AMMESSI), None)
    if cattivo is None and not _PERCENTO.search(resto):
        return ""
    if cattivo is None:
        cosa = "un «%» non seguito da due cifre esadecimali"
    elif cattivo == " ":
        cosa = "uno spazio"
    elif ord(cattivo) < 32 or ord(cattivo) == 127:
        cosa = "un carattere di controllo"
    else:
        cosa = f"il carattere «{cattivo}» non codificato"
    dove = "nel percorso"
    for pezzo in (u.query.split("&") if u.query else ()):
        if (cattivo is not None and cattivo in pezzo) or (
                cattivo is None and _PERCENTO.search(pezzo)):
            nome = pezzo.partition("=")[0]
            dove = (f"nel parametro «{nome[:40]}»"
                    if nome and all(c in _URL_AMMESSI for c in nome) else "nei parametri")
            break
    return (f"URL non valido: c'è {cosa} {dove}. Codifica i valori con urllib.parse.urlencode "
            "(o urllib.parse.quote per un pezzo del percorso), mai a mano nell'indirizzo: es. "
            "\"https://sito/cerca?\" + urlencode({\"nome\": valore})")


# La doppia codifica (08/10 sera, giro 5 della DGX): l'estensione faceva quote_plus(nome) e poi
# urlencode(params) → «name=Borgo%2BAlto», il geocoder cercava «Borgo+Alto» e
# rispondeva vuoto (31 byte); l'agente, con la traccia davanti, ha scritto «%2B is correct for
# space». Solo un avviso (un %2B può essere legittimo: «C++», «1+1»), mai un rifiuto
_PERC_XX = re.compile(r"%[0-9A-Fa-f]{2}")
_PIU_TRA_LETTERE = re.compile(r"[^\W\d_]\+[^\W\d_]")


def doppia_codifica(url: str) -> str:
    """"" o l'avviso «possibile doppia codifica» per un parametro dell'URL il cui valore,
    decodificato una volta, contiene ancora una sequenza «%XX» (era «%25XX») o un «+» tra due
    lettere (era «%2B»: un più letterale, mentre lo spazio è «+» o «%20»). Nel messaggio il nome
    del parametro, mai il suo valore. La stessa regola è in calliope/estensioni/_ospite.py."""
    from urllib.parse import unquote_plus
    try:
        u = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    for pezzo in (u.query.split("&") if u.query else ()):
        nome, _, valore = pezzo.partition("=")
        if not valore:
            continue
        uno = unquote_plus(valore)
        if _PERC_XX.search(uno):
            cosa = "«%25» è un «%» letterale"
        elif _PIU_TRA_LETTERE.search(uno):
            cosa = "«%2B» è un «+» letterale, mentre lo spazio è «+» o «%20»"
        else:
            continue
        dove = (f"nel parametro «{nome[:40]}»"
                if nome and all(c in _URL_AMMESSI for c in nome) else "nei parametri")
        return (f"possibile doppia codifica {dove}: {cosa}. Il valore è stato codificato due "
                "volte (per esempio quote_plus e poi urlencode): codifica una volta sola, con "
                "urlencode passa il testo com'è")
    return ""


def risolvi_pubblico(host: str, porta: int, vietate=(), eccezioni=frozenset(),
                     risolutore=None) -> str:
    """Un indirizzo del nome, solo se **tutti** i suoi indirizzi sono pubblici."""
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        try:
            info = (risolutore or socket.getaddrinfo)(host, porta, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError, OSError):
            raise PaginaNonLetta("il nome non si risolve") from None
        ips = list(dict.fromkeys(i[4][0] for i in info))
    if not ips:
        raise PaginaNonLetta("il nome non si risolve")
    if any(indirizzo_vietato(ip, vietate, eccezioni) for ip in ips):
        raise PaginaVietata("indirizzo della rete interna")
    # IPv4 prima: la DGX e molte case non hanno IPv6 in uscita
    ips.sort(key=lambda ip: ":" in ip)
    return ips[0]


class _Connessione(http.client.HTTPConnection):
    """HTTP verso un indirizzo già controllato, con il nome nell'intestazione Host."""

    def __init__(self, host, ip, porta, timeout):
        super().__init__(host, porta, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _ConnessioneTLS(http.client.HTTPSConnection):
    """HTTPS verso un indirizzo già controllato: SNI e certificato con il nome."""

    def __init__(self, host, ip, porta, timeout, contesto):
        super().__init__(host, porta, timeout=timeout, context=contesto)
        self._ip = ip
        self._ctx = contesto

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._ctx.wrap_socket(sock, server_hostname=self.host)


def _charset(tipo: str, dati: bytes) -> str:
    m = re.search(r"charset=([\w-]+)", tipo or "", re.I) or re.search(
        rb"<meta[^>]+charset=[\"']?([\w-]+)", dati[:4096], re.I)
    cs = m.group(1) if m else "utf-8"
    cs = cs.decode("ascii", "ignore") if isinstance(cs, bytes) else cs
    try:
        "".encode(cs)
        return cs
    except LookupError:
        return "utf-8"


def scarica(url: str, max_byte: int = 1_000_000, timeout_s: float = 10.0, vietate=(),
            eccezioni=frozenset(), porte=(80, 443), risolutore=None,
            max_rimandi: int = 3, contesto_tls=None, tipi=_TIPI, metodo: str = "GET",
            corpo: str | None = None, host_ammesso=None) -> dict:
    """{url, tipo, testo_grezzo}: il contenuto della pagina, o un'eccezione. `eccezioni`,
    `porte` e `risolutore` servono solo alle prove (un server finto su 127.0.0.1).
    `tipi`, `metodo` e `corpo` (JSON) per la porta stretta delle estensioni (04/10): anche
    risposte JSON, e un POST verso un host del manifesto (dopo la conferma).
    `host_ammesso(host) -> bool` (05/10): controllato a ogni passo, anche dopo un
    reindirizzamento (un'estensione che ha letto dati di casa va solo agli host del suo flusso).
    Nel risultato anche `byte` (ricevuti) e `rimandi`."""
    fine = time.monotonic() + timeout_s
    ctx = contesto_tls or ssl.create_default_context()
    for rimandi in range(max_rimandi + 1):
        schema, host, porta, path = controlla_url(url, porte)
        if host_ammesso is not None and not host_ammesso(host):
            raise PaginaVietata(f"host non ammesso: {host}" if not rimandi else
                                f"reindirizzato verso un host non ammesso: {host}")
        ip = risolvi_pubblico(host, porta, vietate, eccezioni, risolutore)
        resto = max(0.5, fine - time.monotonic())
        conn = (_ConnessioneTLS(host, ip, porta, resto, ctx) if schema == "https"
                else _Connessione(host, ip, porta, resto))
        try:
            intestazioni = {
                "User-Agent": "Mozilla/5.0 (compatible; Calliope)",
                "Accept": ("text/html,application/xhtml+xml,text/plain;q=0.8" if tipi is _TIPI
                           else ",".join(tipi)),
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
                "Accept-Encoding": "gzip, identity", "Connection": "close"}
            dati_inviati = None
            if corpo is not None:
                dati_inviati = corpo.encode("utf-8")
                intestazioni["Content-Type"] = "application/json; charset=utf-8"
            conn.request(metodo, path, body=dati_inviati, headers=intestazioni)
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                dove = r.getheader("Location")
                r.close()
                if not dove:
                    raise PaginaNonLetta("reindirizzamento senza destinazione")
                url = urljoin(url, dove)
                if metodo != "GET":
                    raise PaginaNonLetta("reindirizzamento di un invio: non lo ripeto")
                continue
            if r.status != 200 and not (metodo != "GET" and r.status in (201, 202)):
                raise PaginaNonLetta(f"il sito ha risposto {r.status}")
            tipo = (r.getheader("Content-Type") or "").lower()
            if not any(t in tipo for t in tipi):
                raise PaginaNonLetta("non è una pagina di testo")
            lung = r.getheader("Content-Length")
            if lung and lung.isdigit() and int(lung) > max_byte:
                raise PaginaNonLetta("pagina troppo grande")
            dati = bytearray()
            while True:
                resto = fine - time.monotonic()
                if resto <= 0:
                    raise PaginaNonLetta("tempo scaduto")
                # read1 e il tempo che resta sul socket (05/10, banco d'attacco): con read() un
                # sito che manda un byte ogni 0,2 s, a pezzi (chunked) o senza lunghezza, teneva
                # la richiesta aperta per 20 s invece dei 2 del tetto (read riempie il buffer
                # intero, e ogni byte arrivato rinnovava il tempo massimo del socket)
                if conn.sock is not None:
                    conn.sock.settimeout(max(0.05, resto))
                pezzo = r.read1(65536)
                if not pezzo:
                    break
                dati += pezzo
                if len(dati) > max_byte:
                    raise PaginaNonLetta("pagina troppo grande")
            cod = (r.getheader("Content-Encoding") or "identity").lower().strip()
            if cod == "gzip":
                d = zlib.decompressobj(16 + zlib.MAX_WBITS)
                try:
                    dati = d.decompress(bytes(dati), max_byte + 1)
                except zlib.error:
                    raise PaginaNonLetta("compressione rovinata") from None
                if len(dati) > max_byte or d.unconsumed_tail:
                    raise PaginaNonLetta("pagina troppo grande")
            elif cod not in ("identity", ""):
                raise PaginaNonLetta("compressione non supportata")
            dati = bytes(dati)
            return {"url": url, "tipo": tipo, "byte": len(dati), "rimandi": rimandi,
                    "testo_grezzo": dati.decode(_charset(tipo, dati), errors="replace")}
        except (socket.timeout, TimeoutError):
            raise PaginaNonLetta("tempo scaduto") from None
        except ssl.SSLError:
            raise PaginaNonLetta("certificato non valido") from None
        except (OSError, http.client.HTTPException) as e:
            if isinstance(e, (PaginaVietata, PaginaNonLetta)):
                raise
            raise PaginaNonLetta("collegamento non riuscito") from None
        finally:
            conn.close()
    raise PaginaNonLetta("troppi reindirizzamenti")


# ─────────────────────────── testo della pagina ───────────────────────────

_SALTA = {"script", "style", "noscript", "template", "svg", "math", "iframe", "object",
          "embed", "canvas", "form", "button", "select", "textarea", "head", "nav", "footer",
          "aside", "dialog"}
_VUOTI = {"br", "hr", "img", "input", "meta", "link", "wbr", "source", "area", "base", "col",
          "embed", "param", "track"}
_BLOCCHI = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
            "header", "blockquote", "pre", "dd", "dt", "table", "ul", "ol", "main"}
_NASCOSTO = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0"
                       r"|opacity\s*:\s*0(?![.\d])", re.I)


class _Estrattore(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titolo = ""
        self._in_title = False
        self._salta: list[str] = []      # pila dei tag che si stanno saltando
        self.righe: list[str] = []
        self._buf: list[str] = []

    def _a_capo(self):
        riga = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if riga:
            self.righe.append(riga)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":                  # dentro <head>, che per il resto si salta
            self._in_title = True
            return
        if tag in _VUOTI:
            if tag in ("br", "hr") and not self._salta:
                self._a_capo()
            return
        a = {k: (v or "") for k, v in attrs}
        nascosto = ("hidden" in a or a.get("aria-hidden", "").lower() == "true"
                    or _NASCOSTO.search(a.get("style", "")))
        if self._salta or tag in _SALTA or nascosto:
            self._salta.append(tag)
            return
        if tag in _BLOCCHI:
            self._a_capo()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            return
        if tag in _VUOTI:
            return
        if self._salta:
            # Chiude fino al tag giusto (HTML malformato: un tag non chiuso non salta tutto)
            if tag in self._salta:
                while self._salta and self._salta.pop() != tag:
                    pass
            return
        if tag in _BLOCCHI:
            self._a_capo()

    def handle_data(self, data):
        if self._in_title:
            self.titolo += data
            return
        if not self._salta:
            self._buf.append(data)

    def close(self):
        super().close()
        self._a_capo()


def estrai_testo(html: str, tipo: str = "text/html", max_caratteri: int = 8000) -> tuple[str, str]:
    """(titolo, testo) di una pagina: righe con almeno qualche parola, senza doppioni."""
    if "text/plain" in (tipo or ""):
        testo, titolo = html, ""
        righe = [re.sub(r"\s+", " ", r).strip() for r in testo.splitlines()]
    else:
        e = _Estrattore()
        try:
            e.feed(html)
            e.close()
        except Exception:  # noqa: BLE001 — HTML rotto: quello che si è letto basta
            pass
        titolo, righe = re.sub(r"\s+", " ", e.titolo).strip(), e.righe
    visti, buone = set(), []
    for r in righe:
        if len(r.split()) < 3 or r in visti:
            continue
        visti.add(r)
        buone.append(r)
    testo = "\n".join(buone)
    if len(testo) > max_caratteri:
        testo = testo[:max_caratteri].rsplit(" ", 1)[0] + " …"
    return titolo[:200], testo
