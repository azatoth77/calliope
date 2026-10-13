import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco delle notizie dai feed RSS (13/10, calliope/notizie/, tool `notizie`): feed
di fantasia scritti qui (testate, fatti e nomi inventati), un server finto su 127.0.0.1,
niente internet.

1. Lettore: RSS 2.0 e Atom, encoding ISO-8859-1, entità e «billion laughs» rifiutati, XML
   rotto, non un feed; date RFC 822, ISO 8601, in italiano, Sky TG24 con l'ora italiana marcata
   GMT (fuso del feed), ora legale.
2. Pulizia dei titoli e dei sommari (principio 10): ogni regola con i suoi casi contrari.
3. Gruppi: la stessa notizia da più testate, testate uguali e fatti lontani non collegati,
   catena fermata dal tetto.
4. Elenco dei feed: righe valide e no, testate spente e accese per nome, regione di casa.
5. Scarico dal server finto: richieste condizionate (304), compressione rifiutata, tetto di
   dimensione, robots.txt, un feed rotto non ferma gli altri, doppioni, voci vecchie e non
   notizie fuori, date future riportate ad adesso; quando si scarica (attivo, veloci, subito).
6. Fatti: principali per numero di testate, ricerca con le radici, già detti in fondo,
   «quando» a parole, feed fermi.
7. Tool: livelli, niente indirizzi, seguito con «fatto», sezioni, tema dalla frase, minori,
   ripiego su SearXNG (e non per minori e ospiti), web_cerca senza il tipo «notizie», capacità
   e prompt.
8. Brain a secco (decisione 7): dopo `notizie` i fatti restano nel contesto in busta; la
   domanda dopo arriva al modello con i fatti; i turni vecchi tengono la forma ridotta (non la
   traccia generica); dopo il risultato, nella stessa risposta, niente azioni; le proiezioni
   del registro degli eventi fanno lo stesso.
"""

import datetime as dt
import functools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from calliope import capacita, provenienza
from calliope.brain import Brain, WEB_TOLTO, _compatta_storia
from calliope.config import Config
from calliope.notizie import contesto, gruppi, lettore, pulizia
from calliope.notizie.feed import (Feed, elenco, leggi_riga, regione_ansa, regione_di_casa,
                                   testate_spente)
from calliope.notizie.servizio import Notizie, quando, radici_ricerca
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


UTC = dt.timezone.utc
# Un martedì d'ottobre alle 15:00 italiane (13:00 UTC): l'ora delle prove
ADESSO = dt.datetime(2026, 10, 13, 13, 0, tzinfo=UTC).timestamp()


def rfc(t: float) -> str:
    return dt.datetime.fromtimestamp(t, UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")


def rss(titolo_canale: str, voci: list[tuple], enc: str = "utf-8") -> bytes:
    """voci: (titolo, sommario, link, data RFC o "")."""
    it = "".join(
        f"<item><title>{t}</title><description>{s}</description><link>{ln}</link>"
        + (f"<pubDate>{d}</pubDate>" if d else "") + "</item>" for t, s, ln, d in voci)
    testo = (f'<?xml version="1.0" encoding="{enc}"?><rss version="2.0"><channel>'
             f"<title>{titolo_canale}</title>{it}</channel></rss>")
    return testo.encode(enc)


# ─────────────────────────── 1. lettore ───────────────────────────
voci = lettore.leggi(rss("Prova", [("Primo titolo &amp; altro", "&lt;p&gt;Un sommario &lt;b&gt;"
                                    "con&lt;/b&gt; marcatura&lt;/p&gt;", "https://a.esempio.it/1",
                                    "Tue, 13 Oct 2026 12:00:00 GMT")]))
verifica("lettore: RSS 2.0, testo senza marcatura e con le entità risolte",
         voci == [{"titolo": "Primo titolo & altro", "sommario": "Un sommario con marcatura",
                   "link": "https://a.esempio.it/1",
                   "data_grezza": "Tue, 13 Oct 2026 12:00:00 GMT"}], str(voci))
atom = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>X</title>'
        '<entry><title>Voce Atom</title><link rel="alternate" href="https://b.esempio.it/2"/>'
        '<published>2026-10-13T10:00:00Z</published><content>Testo della voce</content>'
        '</entry></feed>').encode()
v = lettore.leggi(atom)
verifica("lettore: Atom (link, published, content)",
         v[0]["titolo"] == "Voce Atom" and v[0]["link"] == "https://b.esempio.it/2"
         and v[0]["sommario"] == "Testo della voce", str(v))
v = lettore.leggi(rss("Prova", [("Città e caffè", "Perché sì", "https://c.esempio.it/3", "")],
                      enc="iso-8859-1"))
verifica("lettore: ISO-8859-1 dai byte (accenti giusti)", v[0]["titolo"] == "Città e caffè",
         str(v))
verifica("lettore: spazi prima di <?xml accettati",
         lettore.leggi(b"  \n" + rss("P", [("T", "S", "https://d.esempio.it", "")]))[0]["titolo"]
         == "T")
for nome, dati in [
        ("entità interna", b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel>'
                           b'<item><title>&a;</title></item></channel></rss>'),
        ("billion laughs", b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY l0 "ha">'
                           b'<!ENTITY l1 "&l0;&l0;&l0;&l0;&l0;&l0;&l0;&l0;&l0;&l0;">]>'
                           b'<rss><channel><item><title>&l1;</title></item></channel></rss>'),
        ("entità esterna", b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY e SYSTEM '
                           b'"file:///etc/passwd">]><rss><channel><item><title>&e;</title>'
                           b'</item></channel></rss>'),
        ("XML rotto", b"<rss><channel><item><title>senza chiusura"),
        ("non è un feed", b"<html><body>pagina</body></html>"),
        ("vuoto", b"   ")]:
    try:
        lettore.leggi(dati)
        verifica(f"lettore: {nome} rifiutato", False)
    except lettore.FeedNonLetto as e:
        verifica(f"lettore: {nome} rifiutato", True, str(e))
verifica("lettore: DOCTYPE senza entità (come Corriere e Gazzetta) accettato",
         lettore.leggi(b'<?xml version="1.0"?><!DOCTYPE xml><rss version="2.0"><channel>'
                       b'<item><title>Va bene</title></item></channel></rss>')[0]["titolo"]
         == "Va bene")

# Date
d = lettore.leggi_data("Tue, 13 Oct 2026 12:00:00 GMT")
verifica("date: RFC 822", d == dt.datetime(2026, 10, 13, 12, tzinfo=UTC), str(d))
d = lettore.leggi_data("Tue, 13 Oct 2026 14:00:00 +0200")
verifica("date: RFC 822 con il fuso", d.astimezone(UTC).hour == 12, str(d))
d = lettore.leggi_data("2026-10-13T10:00:00Z")
verifica("date: ISO 8601", d == dt.datetime(2026, 10, 13, 10, tzinfo=UTC), str(d))
d = lettore.leggi_data("mar, 13 ott 2026 13:10:00 GMT")
verifica("date: in italiano (Il Messaggero, GMT vero)",
         d == dt.datetime(2026, 10, 13, 13, 10, tzinfo=UTC), str(d))
d = lettore.leggi_data("mar, 13 ott 2026 13:10:00 GMT", fuso="Europe/Rome")
verifica("date: Sky TG24, ora italiana marcata GMT (ottobre: +2)",
         d == dt.datetime(2026, 10, 13, 11, 10, tzinfo=UTC), str(d))
d = lettore.leggi_data("Tue, 13 Jan 2026 13:10:00 GMT", fuso="Europe/Rome")
verifica("date: ora italiana d'inverno (+1)",
         d == dt.datetime(2026, 1, 13, 12, 10, tzinfo=UTC), str(d))
verifica("date: cambio dell'ora (ultima domenica di ottobre alle 01:00 UTC)",
         lettore.utc_a_roma(dt.datetime(2026, 10, 25, 0, 59)).hour == 2
         and lettore.utc_a_roma(dt.datetime(2026, 10, 25, 1, 1)).hour == 2
         and lettore.utc_a_roma(dt.datetime(2026, 10, 25, 1, 1)).minute == 1
         and lettore.utc_a_roma(dt.datetime(2026, 3, 29, 1, 0)).hour == 3)
d = lettore.leggi_data("2026-10-13T12:00:00+00:00", fuso="Europe/Rome")
verifica("date: fuso del feed anche su ISO 8601 marcato UTC", d.hour == 10, str(d))
d = lettore.leggi_data("Tue, 13 Oct 2026 14:00:00 +0200", fuso="Europe/Rome")
verifica("contrario date: un fuso vero (+0200) resta quello", d.astimezone(UTC).hour == 12,
         str(d))
verifica("date: illeggibile o assente → None",
         lettore.leggi_data("ieri sera") is None and lettore.leggi_data("") is None)

# ─────────────────────────── 2. pulizia (principio 10) ───────────────────────────
CASI_TITOLI = [
    # (titolo, sommario, atteso, regole)
    ('Il ministro: "Pronti alla riforma"', "", "Il ministro: «Pronti alla riforma»",
     ["notizie_titolo_virgolette"]),
    ("Il sindaco: “Lavori finiti”", "", "Il sindaco: «Lavori finiti»",
     ["notizie_titolo_virgolette"]),
    ("Rossi: 'serve un accordo' sul porto", "", "Rossi: «serve un accordo» sul porto",
     ["notizie_titolo_virgolette"]),
    ("Taglio dell'Irpef, l'accordo c'è", "", "Taglio dell'Irpef, l'accordo c'è", []),
    ("Già «giuste» le virgolette basse", "", "Già «giuste» le virgolette basse", []),
    ("++ Scossa di terremoto nel Lumenese ++", "", "Scossa di terremoto nel Lumenese",
     ["notizie_titolo_agenzia"]),
    (">LUMEN-FOCUS/ Il porto riapre domani", "", "Il porto riapre domani",
     ["notizie_titolo_agenzia"]),
    ("Incendio in un deposito a Borgoverde VIDEO", "", "Incendio in un deposito a Borgoverde",
     ["notizie_titolo_marcatore"]),
    ("LIVE: la regata di Borgoverde", "", "la regata di Borgoverde",
     ["notizie_titolo_marcatore"]),
    ("Il video del ministro sul porto", "", "Il video del ministro sul porto", []),
    ("Live Aid quarant'anni dopo", "", "Live Aid quarant'anni dopo", []),
    ("Le FOTO più belle sono nel mezzo del titolo", "",
     "Le FOTO più belle sono nel mezzo del titolo", []),
    ("Borgoverde, le notizie in diretta | Chiuso il ponte sul fiume", "",
     "Chiuso il ponte sul fiume", ["notizie_titolo_doppio"]),
    ("Chiuso il ponte sul fiume | Cronaca di Borgoverde", "", "Chiuso il ponte sul fiume",
     ["notizie_titolo_doppio"]),
    ("Rincari dei trasporti, biglietti sopra i l...",
     "Rincari dei trasporti, biglietti sopra i limiti fissati dalla regione. Lo dice l'agenzia.",
     "Rincari dei trasporti, biglietti sopra i limiti fissati dalla regione",
     ["notizie_titolo_troncato"]),
    ("E adesso che succede…", "Il campionato riparte sabato con la sfida al vertice.",
     "E adesso che succede…", []),
]
for tit, somm, atteso, regole in CASI_TITOLI:
    t, r = pulizia.titolo_per_voce(tit, somm)
    verifica(f"titolo: «{tit[:45]}»", (t, r) == (atteso, regole), f"{t!r} {r}")
CASI_SOMMARI = [
    ("Agenzia Lumen - Il porto riapre domani alle 8.", "Agenzia Lumen",
     "Il porto riapre domani alle 8.", ["notizie_sommario_sigla"]),
    ("Borgoverde - Il porto riapre domani.", "Agenzia Lumen",
     "Borgoverde - Il porto riapre domani.", []),
    ("Il porto riapre. The post Il porto riapre appeared first on Lumen Ragazzi.",
     "Lumen Ragazzi", "Il porto riapre.", ["notizie_sommario_coda"]),
    ("Il porto riapre domani", "Agenzia Lumen", "", []),
]
for somm, testata, atteso, regole in CASI_SOMMARI:
    s, r = pulizia.sommario_per_voce(somm, "Il porto riapre domani", testata)
    verifica(f"sommario: «{somm[:40]}»", (s, r) == (atteso, regole), f"{s!r} {r}")
for tit, link, atteso in [
        ("Il caffè del mattino", "https://www.esempio.it/episodes/caffe-13-10", True),
        ("La newsletter di oggi", "https://www.esempio.it/newsletter/oggi", True),
        ("Puntata del 13/10/2026", "https://www.esempio.it/tg/1", True),
        ("Tg Lumen Salute del 13/10", "https://www.esempio.it/tg/2", True),
        ("Peanuts", "https://www.esempio.it/strisce/1", True),
        ("Alluvione, il video dei soccorsi", "https://www.rainews.it/video/2026/10/x", False),
        ("Il podcast sul clima vince un premio", "https://www.esempio.it/cultura/1", False)]:
    verifica(f"non notizia: «{tit}»", pulizia.non_notizia(tit, link) == atteso)

# ─────────────────────────── 3. gruppi ───────────────────────────
T0 = ADESSO - 3600
G = [(1, "Agenzia Lumen", T0, "Frana sulla statale del passo Ventoso, strada chiusa"),
     (2, "Tele Aurora", T0 + 600, "Statale del passo Ventoso chiusa per una frana"),
     (3, "Gazzetta di Borgoverde", T0 + 900, "Frana sul passo Ventoso: chiusa la statale"),
     (4, "Agenzia Lumen", T0 + 1200, "Statale del passo Ventoso, frana: strada chiusa"),
     (5, "Tele Aurora", T0, "Il festival delle lanterne apre a Borgoverde"),
     (6, "Gazzetta di Borgoverde", T0 - 30 * 3600, "Frana sul passo Ventoso, chiusa la statale"),
     (7, "Radio Brezza", T0, "Concerto in piazza per la festa del raccolto")]
gr = gruppi.raggruppa(G)
verifica("gruppi: la stessa frana da tre testate in un gruppo",
         gr[1] == gr[2] == gr[3], str(gr))
verifica("contrario gruppi: due voci della stessa testata non si collegano tra loro "
         "(la seconda resta fuori se somiglia solo a lei)", gr[4] in (gr[1], 4), str(gr))
verifica("contrario gruppi: un fatto diverso resta da solo", gr[5] == 5 and gr[7] == 7)
verifica("contrario gruppi: oltre 24 ore non si collega", gr[6] == 6, str(gr))
CATENA = [(1, "A", T0, "Vertice sul porto di Borgoverde, accordo sui moli"),
          (2, "B", T0, "Porto di Borgoverde, accordo sui moli e sui traghetti"),
          (3, "C", T0, "Traghetti in ritardo per la nebbia, moli affollati"),
          (4, "D", T0, "Nebbia fitta in pianura, autostrade rallentate")]
gr = gruppi.raggruppa(CATENA)
verifica("gruppi: la catena porto → traghetti → nebbia non unisce porto e autostrade",
         gr[1] == gr[2] and gr[4] != gr[1], str(gr))
verifica("radici: prime sei lettere, senza accenti né parole vuote",
         gruppi.radici("Città dell'Università di Borgoverde") == ["citta", "univer", "borgov"])
verifica("radici della ricerca: «scioperi» e «sciopero» coincidono",
         radici_ricerca("scioperi") == radici_ricerca("sciopero"))

# ─────────────────────────── 4. elenco dei feed ───────────────────────────
f = leggi_riga("Tele Aurora | generale | https://tele.esempio.it/rss | fuso=Europe/Rome | veloce")
verifica("feed: riga con opzioni", f == Feed("Tele Aurora", "generale", "https://tele.esempio.it/rss",
                                             "Europe/Rome", True, ("fuso=Europe/Rome", "veloce")),
         str(f))
for riga in ["Tele Aurora | generale", "Tele Aurora | cucina | https://x.esempio.it/rss",
             " | generale | https://x.esempio.it/rss", "Tele Aurora | generale | ftp://x.it/rss"]:
    verifica(f"contrario feed: riga non valida «{riga}»", leggi_riga(riga) is None)
cfg_f = Config()
nomi = {x.testata for x in elenco(cfg_f)}
verifica("feed di serie: Il Post e Il Sole 24 Ore spenti, gli altri accesi",
         "Il Post" not in nomi and "Il Sole 24 Ore" not in nomi and "ANSA" in nomi
         and "Focus Junior" in nomi and testate_spente(cfg_f) == ["Il Post", "Il Sole 24 Ore"],
         str(nomi))
cfg_f.notizie_accese = ["il post", "Il Sole 24 ore"]
nomi = [x.testata for x in elenco(cfg_f)]
verifica("feed: accesi per nome (maiuscole a parte), anche i due feed del Sole",
         "Il Post" in nomi and nomi.count("Il Sole 24 Ore") == 2 and not testate_spente(cfg_f))
cfg_f.notizie_spente = ["HDblog"]
cfg_f.notizie_accese = []
cfg_f.notizie_feed_extra = ["Gazzetta di Borgoverde | locale | https://gb.esempio.it/rss",
                            "riga sbagliata"]
nomi = [x.testata for x in elenco(cfg_f)]
verifica("feed: spenti per nome e feed in più della casa (la riga sbagliata si salta)",
         "HDblog" not in nomi and "Gazzetta di Borgoverde" in nomi and "Il Post" in nomi)
for citta, attesa in [("Milano", "lombardia"), ("reggio emilia", "emiliaromagna"),
                      ("Forlì", "emiliaromagna"), ("L'Aquila", "abruzzo"),
                      ("Lombardia", "lombardia"), ("Valle d'Aosta", "valledaosta"),
                      ("Friuli", "friuliveneziagiulia"), ("La Spezia", "liguria"),
                      ("Borgoverde", ""), ("Città di Lumen", ""), ("", ""),
                      ("Milano Marittima", "")]:
    verifica(f"regione: «{citta}» → «{attesa}»", regione_ansa(citta) == attesa,
             regione_ansa(citta))
c_r = Config()
c_r.casa_citta = "Torino"
fr = [x for x in elenco(c_r) if x.tema == "locale"]
verifica("regione di casa dalla città: il feed ANSA del Piemonte, da solo",
         [x.url for x in fr] == ["https://www.ansa.it/piemonte/notizie/piemonte_rss.xml"])
c_r.notizie_regione = "no"
verifica("contrario regione: «no» = nessun feed regionale",
         not [x for x in elenco(c_r) if x.tema == "locale"] and regione_di_casa(c_r) == "")
c_r.notizie_regione = "Sicilia"
verifica("regione scritta a mano vince sulla città", regione_di_casa(c_r) == "sicilia")
c_r.notizie_regione, c_r.casa_citta = "", "Borgoverde"
verifica("contrario regione: città sconosciuta → nessun feed regionale",
         regione_di_casa(c_r) == "")

# ─────────────────────────── 5. scarico dal server finto ───────────────────────────


class ServerFeed:
    """Feed su 127.0.0.1: {percorso: (codice, intestazioni, corpo)}, ETag con 304, richieste
    ricevute con le intestazioni."""

    def __init__(self):
        self.percorsi: dict = {}
        self.richieste: list = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.richieste.append((self.path, dict(self.headers)))
                codice, intest, corpo = outer.percorsi.get(self.path, (404, {}, b""))
                etag = intest.get("ETag")
                if etag and self.headers.get("If-None-Match") == etag:
                    codice, corpo = 304, b""
                self.send_response(codice)
                for k, val in intest.items():
                    self.send_header(k, val)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                try:
                    self.wfile.write(corpo)
                except OSError:
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def porta(self):
        return self.server.server_address[1]

    def url(self, p):
        return f"http://feed.esempio.it:{self.porta}{p}"

    def ferma(self):
        self.server.shutdown()
        self.server.server_close()


srv = ServerFeed()


def dns(host, porta, type=None):
    import socket
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", porta))]


scarica = functools.partial(lettore.scarica, eccezioni=frozenset({"127.0.0.1"}),
                            porte=(80, 443, srv.porta), risolutore=dns)
H, M = 3600, 60
XML = {"Content-Type": "application/rss+xml; charset=utf-8"}
srv.percorsi["/robots.txt"] = (200, {"Content-Type": "text/plain"},
                               b"User-agent: *\nDisallow: /privato/\n")
FRANA = [("Frana sul passo Ventoso, chiusa la statale",
          "La statale del passo Ventoso è chiusa da stamattina per una frana: nessun ferito.",
          "https://lumen.esempio.it/frana", rfc(ADESSO - 2 * H)),
         ("Il festival delle lanterne apre a Borgoverde",
          "Tre giorni di musica e lanterne sul lungofiume.", "https://lumen.esempio.it/festival",
          rfc(ADESSO - 5 * H)),
         ("Vecchia notizia di un mese fa", "Non deve entrare.", "https://lumen.esempio.it/vecchia",
          rfc(ADESSO - 30 * 86400)),
         ("Il caffè del mattino", "Episodio del podcast.", "https://lumen.esempio.it/episodes/1",
          rfc(ADESSO - H)),
         ("Frana sul passo Ventoso, chiusa la statale", "Doppione nella stessa testata.",
          "https://lumen.esempio.it/frana-bis", rfc(ADESSO - 2 * H)),
         ("Sciopero dei treni regionali venerdì", "I sindacati confermano lo sciopero di "
          "venerdì sulle linee regionali.", "https://lumen.esempio.it/sciopero",
          rfc(ADESSO - 3 * H)),
         ("Una notizia dal futuro", "Data sbagliata del feed.", "https://lumen.esempio.it/futuro",
          rfc(ADESSO + 4 * H))]
srv.percorsi["/lumen.xml"] = (200, {**XML, "ETag": '"v1"'}, rss("Agenzia Lumen", FRANA))
srv.percorsi["/aurora.xml"] = (200, XML, rss("Tele Aurora", [
    ("Statale del passo Ventoso chiusa per una frana", "Strada chiusa per la frana caduta "
     "stanotte sul passo Ventoso.", "https://aurora.esempio.it/frana",
     # Ora italiana marcata GMT (come Sky TG24): 13:30 italiane = 11:30 UTC = 1 h 30 fa
     "mar, 13 ott 2026 13:30:00 GMT"),
    ("Derby di Borgoverde, vince la Lumenese 2-1", "Doppietta del centravanti nel derby.",
     "https://aurora.esempio.it/derby", rfc(ADESSO - 4 * H))]))
srv.percorsi["/gazzetta.xml"] = (200, XML, rss("Gazzetta di Borgoverde", [
    ("Frana sul passo Ventoso: chiusa la statale, deviazioni", "Deviazioni per i camion sulla "
     "provinciale dopo la frana.", "https://gb.esempio.it/frana", rfc(ADESSO - 1 * H)),
    ("Derby, la Lumenese batte il Borgoverde 2-1", "Il derby va alla Lumenese.",
     "https://gb.esempio.it/derby", rfc(ADESSO - 3 * H)),
    ("Nuova app per i biglietti dei treni", "Arriva l'app per i biglietti regionali.",
     "https://gb.esempio.it/app", rfc(ADESSO - 6 * H))]))
srv.percorsi["/ragazzi.xml"] = (200, XML, rss("Lumen Ragazzi", [
    ("Come nascono le lanterne di carta", "Un laboratorio per costruire lanterne in classe.",
     "https://lr.esempio.it/lanterne", rfc(ADESSO - 20 * H)),
    ("Il festival delle lanterne apre a Borgoverde: tre giorni di musica",
     "Tre giorni di musica e lanterne sul lungofiume, anche per le scuole.",
     "https://lr.esempio.it/festival", rfc(ADESSO - 4 * H))]))
srv.percorsi["/tech.xml"] = (200, XML, rss("Bit Lumen", [
    ("Un robot che ripara le strade", "Il robot tappa le buche da solo.",
     "https://bit.esempio.it/robot", rfc(ADESSO - 10 * H)),
    ("Arriva un'app di gioco d'azzardo online", "Per i soli maggiorenni.",
     "https://bit.esempio.it/azzardo", rfc(ADESSO - 9 * H))]))
srv.percorsi["/gzip.xml"] = (200, {**XML, "Content-Encoding": "gzip"}, b"\x1f\x8b finto")
srv.percorsi["/enorme.xml"] = (200, XML, b"<rss>" + b"x" * 2_100_000 + b"</rss>")
srv.percorsi["/privato/feed.xml"] = (200, XML, rss("Segreto", [("Non letto", "", "", "")]))
FEEDS = [Feed("Agenzia Lumen", "generale", srv.url("/lumen.xml")),
         Feed("Tele Aurora", "generale", srv.url("/aurora.xml"), fuso="Europe/Rome",
              veloce=True),
         Feed("Gazzetta di Borgoverde", "generale", srv.url("/gazzetta.xml")),
         Feed("Lumen Ragazzi", "ragazzi", srv.url("/ragazzi.xml")),
         Feed("Bit Lumen", "tecnologia", srv.url("/tech.xml")),
         Feed("Compressa", "generale", srv.url("/gzip.xml")),
         Feed("Enorme", "generale", srv.url("/enorme.xml")),
         Feed("Segreto", "generale", srv.url("/privato/feed.xml")),
         Feed("Assente", "sport", srv.url("/manca.xml"))]
orologio = [ADESSO]
cfg = Config()
cfg.notizie_intervallo_min = 120
svc = Notizie(cfg, FEEDS, ":memory:", log=lambda *a: None, orologio=lambda: orologio[0],
              scarica=scarica)
verifica("scarico: senza richieste di notizie non si scarica (decisione del 12/10)",
         svc.forse_scarica() is None and not srv.richieste)
svc.richiesta()
esito = svc.forse_scarica()
verifica("scarico: con una richiesta recente sì, un feed rotto non ferma gli altri",
         esito is not None and esito["ok"] == 5 and set(esito["errori"]) == {
             "Compressa (generale)", "Enorme (generale)", "Segreto (generale)",
             "Assente (sport)"}, str(esito and esito["errori"]))
verifica("scarico: compressione rifiutata, tetto di dimensione, robots.txt, 404",
         "compressa" in esito["errori"]["Compressa (generale)"]
         and "grande" in esito["errori"]["Enorme (generale)"]
         and "robots" in esito["errori"]["Segreto (generale)"]
         and "404" in esito["errori"]["Assente (sport)"], str(esito["errori"]))
lumen = [r for r in srv.richieste if r[0] == "/lumen.xml"][0][1]
verifica("scarico: User-Agent onesto, niente compressione chiesta",
         lumen.get("User-Agent", "").startswith("Calliope/")
         and lumen.get("Accept-Encoding") == "identity", str(lumen))
verifica("scarico: il feed vietato dal robots.txt non è stato chiesto",
         not any(r[0] == "/privato/feed.xml" for r in srv.richieste))
titoli = {v.titolo for v in svc._voci}
verifica("scarico: voce vecchia, podcast e doppione nella stessa testata fuori",
         "Vecchia notizia di un mese fa" not in titoli and "Il caffè del mattino" not in titoli
         and sum(1 for v in svc._voci if v.testata == "Agenzia Lumen"
                 and v.titolo.startswith("Frana")) == 1, str(titoli))
fut = [v for v in svc._voci if v.titolo == "Una notizia dal futuro"][0]
verifica("scarico: data nel futuro riportata ad adesso", fut.t == ADESSO)
aur = [v for v in svc._voci if v.link == "https://aurora.esempio.it/frana"][0]
verifica("scarico: fuso del feed (13:30 italiane marcate GMT = 1 h 30 fa)",
         aur.t == ADESSO - 1.5 * H, str((ADESSO - aur.t) / H))
verifica("scarico: notizie_non_notizia contata", esito["regole"].get("notizie_non_notizia") == 1,
         str(esito["regole"]))
n_rich = len(srv.richieste)
orologio[0] += 30 * M
verifica("scarico: prima dell'intervallo niente (i veloci ogni metà intervallo)",
         svc.forse_scarica() is None and len(srv.richieste) == n_rich)
orologio[0] += 31 * M
e2 = svc.forse_scarica()
verifica("scarico: dopo un'ora solo i feed veloci (nei giorni in cui si chiedono notizie)",
         e2 is not None and e2["veloci"] and e2["feed"] == 1
         and [r[0] for r in srv.richieste[n_rich:]] == ["/aurora.xml"], str(srv.richieste[n_rich:]))
orologio[0] += 60 * M
n_rich = len(srv.richieste)
e3 = svc.forse_scarica()
cond = [r[1] for r in srv.richieste[n_rich:] if r[0] == "/lumen.xml"]
verifica("scarico: dopo l'intervallo tutti, con la richiesta condizionata (ETag → 304)",
         e3 is not None and not e3["veloci"] and cond and cond[0].get("If-None-Match") == '"v1"'
         and e3["nuove"] == 0, str(cond))
verifica("scarico: robots.txt letto una volta sola nel giorno",
         sum(1 for r in srv.richieste if r[0] == "/robots.txt") == 1)
orologio[0] = ADESSO
# Dopo una pausa: l'indice vecchio si riscarica subito alla richiesta
svc2 = Notizie(cfg, FEEDS[:3], ":memory:", log=lambda *a: None, orologio=lambda: orologio[0],
               scarica=scarica)
frasi = []
t0 = time.perf_counter()
fresco = svc2.prepara(attesa=lambda: frasi.append("attesa"))
verifica("prima richiesta dopo la pausa: scarico subito, poi l'indice è fresco",
         fresco and svc2._voci and time.perf_counter() - t0 < 4.0,
         f"{time.perf_counter() - t0:.2f} s")
verifica("prima richiesta: la richiesta resta segnata (lo scarico periodico si accende)",
         svc2.attivo())
svc2.close()
# Senza internet: uno scarico fallito da poco non si ritenta a ogni domanda (niente attesa)
svc3 = Notizie(cfg, [Feed("Assente", "generale", srv.url("/manca.xml"))], ":memory:",
               log=lambda *a: None, orologio=lambda: orologio[0], scarica=scarica)
svc3.prepara()
n_rich = len(srv.richieste)
t0 = time.perf_counter()
verifica("senza feed raggiungibili: la domanda dopo non riprova subito lo scarico",
         svc3.prepara() is False and len(srv.richieste) == n_rich
         and time.perf_counter() - t0 < 0.2, f"{time.perf_counter() - t0:.2f} s")
svc3.close()

# ─────────────────────────── 6. fatti ───────────────────────────
fatti = svc.principali(n=3)
verifica("fatti: il primo è la frana, data da tre testate",
         fatti and fatti[0].titolo.startswith("Frana") and len(fatti[0].testate) == 3,
         str([(f.titolo, f.testate) for f in fatti]))
verifica("fatti: il derby da due testate è il secondo",
         len(fatti) > 1 and "erby" in fatti[1].titolo and len(fatti[1].testate) == 2,
         str([(f.titolo, f.testate) for f in fatti]))
verifica("fatti: titolo più corto del gruppo (almeno 25 caratteri)",
         fatti[0].titolo == "Frana sul passo Ventoso, chiusa la statale", fatti[0].titolo)
dette = set(fatti[0].ids)
f2 = svc.principali(n=10, gia_dette=dette)
verifica("fatti: quelli già detti in fondo", not f2[0].titolo.startswith("Frana")
         and f2[-1].titolo.startswith("Frana"), str([f.titolo for f in f2]))
fs, rec = svc.cerca("scioperi")
verifica("ricerca: «scioperi» trova «sciopero» (radici), con le voci recenti contate",
         fs and fs[0].titolo.startswith("Sciopero") and rec == 1, str(rec))
fs, rec = svc.cerca("lanterne", temi=("ragazzi",))
verifica("ricerca per temi: solo il feed per ragazzi", len(fs) == 2
         and all(f.testate == ["Lumen Ragazzi"] for f in fs), str([f.testate for f in fs]))
verifica("ricerca: niente → nessun fatto, zero recenti", svc.cerca("vulcano") == ([], 0))
for t, atteso in [(ADESSO - 5 * M, "poco fa"), (ADESSO - 40 * M, "40 minuti fa"),
                  (ADESSO - 5 * H, "stamattina alle 10:00"),
                  (ADESSO - 19 * H, "ieri sera"), (ADESSO - 22 * H, "ieri pomeriggio"), (ADESSO - 3 * 86400, "sabato"),
                  (ADESSO - 9 * 86400, "il 4 ottobre")]:
    verifica(f"quando: «{atteso}»", quando(t, ADESSO) == atteso, quando(t, ADESSO))
verifica("quando: senza data «di recente», mai «oggi»",
         quando(ADESSO, ADESSO, senza_data=True) == "di recente")
st = svc.stato()
verifica("stato: guasti nominati, nessun fermo", "Assente (sport)" in st["guasti"]
         and not st["fermi"] and st["voci"] > 5, str(st))
orologio[0] = ADESSO + 3 * 86400
st = svc.stato()
verifica("stato: un feed generale fermo da tre giorni è «fermo»; i ragazzi no",
         "Agenzia Lumen (generale)" in st["fermi"]
         and not any("Ragazzi" in x for x in st["fermi"]), str(st["fermi"]))
orologio[0] = ADESSO

# ─────────────────────────── 7. tool ───────────────────────────
from prove.searxng_finto import SearxngFinto  # noqa: E402
from calliope.web import Web  # noqa: E402


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None):
        self.id, self.name, self.admin, self.nascita = pid, name, admin, nascita
        self.preferred_voice = None


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", True), "Bianca": Prof("bianca-id", "Bianca"),
                  "Pietro": Prof("pietro-id", "Pietro", nascita="2016-05-10")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.profile_level = level
        self.identified_by = "voce" if name else None


sx = SearxngFinto().avvia()
cfg.web_searxng_url = sx.url
web = Web(cfg)
web.prova()
reg = build_registry(web=cfg, notizie=cfg)


def contesto_tool(nome="Dario", livello="familiare", testo=""):
    c = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(nome, livello),
                    speaker=None, web=web, notizie=svc)
    c.user_text = testo
    return c


schema_web = next(s for s in reg.all_schemas() if s["function"]["name"] == "web_cerca")
verifica("web_cerca con il tool notizie: niente tipo, domanda obbligatoria, rimanda a notizie",
         "tipo" not in schema_web["function"]["parameters"]["properties"]
         and schema_web["function"]["parameters"]["required"] == ["domanda"]
         and "usa invece notizie" in schema_web["function"]["description"])
schema_n = next(s for s in reg.all_schemas() if s["function"]["name"] == "notizie")
verifica("notizie: schema con tema e fatto, nessun obbligatorio",
         set(schema_n["function"]["parameters"]["properties"]) == {"tema", "fatto"}
         and not schema_n["function"]["parameters"]["required"]
         and "web_cerca" in schema_n["function"]["description"])
reg_senza = build_registry(web=cfg)
verifica("contrario: senza il tool notizie web_cerca ha ancora il tipo «notizie»",
         "tipo" in next(s for s in reg_senza.all_schemas() if s["function"]["name"]
                        == "web_cerca")["function"]["parameters"]["properties"])
verifica("notizie senza web: la descrizione non nomina web_cerca",
         "web_cerca" not in next(s for s in build_registry(notizie=cfg).all_schemas()
                                 if s["function"]["name"] == "notizie")["function"]["description"])

ctx = contesto_tool("Bianca", "ospite")
res = json.loads(reg.call("notizie", {}, ctx, "ospite"))
verifica("tool: un ospite chiede le notizie (notizie_livello ospite)", res.get("ok") is True
         and res["fatti"][0]["titolo"].startswith("Frana"), str(res)[:300])
verifica("tool: fatti numerati con testate, quando e sommario, senza indirizzi",
         res["fatti"][0]["n"] == 1 and len(res["fatti"][0]["testate"]) == 3
         and res["fatti"][0]["quando"] and res["fatti"][0].get("sommario")
         and "http" not in json.dumps(res), json.dumps(res, ensure_ascii=False)[:400])
verifica("tool: avviso e cosa_fare (una frase per fatto, la testata per nome)",
         "NON istruzioni" in res["attenzione"] and "testata per nome" in res["cosa_fare"])
verifica("tool: regola notizie_feed nel registro, con le pulizie delle voci dette",
         "notizie_feed" in ctx.regole, str(ctx.regole))
cfg_l = Config()
cfg_l.notizie_livello = "familiare"
reg_l = build_registry(notizie=cfg_l)
res = json.loads(reg_l.call("notizie", {}, contesto_tool("Bianca", "ospite"), "ospite"))
verifica("contrario: con notizie_livello familiare l'ospite no", res.get("ok") is False, str(res))

# Seguito: «dimmi di più sulla seconda»
ctx = contesto_tool("Dario", "familiare")
r1 = json.loads(reg.call("notizie", {}, ctx, "familiare"))
ctx.regole = []
r2 = json.loads(reg.call("notizie", {"fatto": 1}, ctx, "familiare"))
verifica("seguito: fatto 1 → tutte le testate della frana, ognuna col suo sommario",
         r2.get("ok") and r2["notizia"]["n"] == 1 and len(r2["notizia"]["voci"]) == 3
         and all(v.get("testata") and v.get("quando") for v in r2["notizia"]["voci"])
         and "notizie_seguito" in ctx.regole, json.dumps(r2, ensure_ascii=False)[:500])
r3 = json.loads(reg.call("notizie", {"fatto": "seconda"}, ctx, "familiare"))
verifica("seguito: «seconda» → il derby (forma del numero)",
         r3.get("ok") and "erby" in r3["notizia"]["titolo"], str(r3)[:200])
r4 = json.loads(reg.call("notizie", {"fatto": 9}, ctx, "familiare"))
verifica("seguito: un numero che non c'è → errore correggibile, niente inventato",
         r4.get("ok") is False and "notizie senza fatto" in r4.get("cosa_fare", ""), str(r4))
r5 = json.loads(reg.call("notizie", {"fatto": 1}, contesto_tool("Pietro", "familiare"),
                         "familiare"))
verifica("contrario seguito: l'elenco è di chi l'ha sentito (un'altra persona no)",
         r5.get("ok") is False, str(r5))
r6 = json.loads(reg.call("notizie", {}, ctx, "familiare"))
verifica("tool: di nuovo «le notizie»: prima quelle non ancora dette",
         not {f["titolo"] for f in r6["fatti"]} & {f["titolo"] for f in r1["fatti"]},
         str([(f["titolo"], f.get("gia_detto")) for f in r6["fatti"]]))
r7 = json.loads(reg.call("notizie", {}, ctx, "familiare"))
verifica("tool: finite le nuove, le già dette tornano con gia_detto",
         any(f.get("gia_detto") for f in r7["fatti"]),
         str([(f["titolo"], f.get("gia_detto")) for f in r7["fatti"]]))
# Sezioni e tema dalla frase
ctx = contesto_tool("Dario", "familiare", "Calliope, le notizie di tecnologia")
res = json.loads(reg.call("notizie", {}, ctx, "familiare"))
verifica("tema dalla frase quando il modello lo lascia vuoto (notizie_tema_frase)",
         res.get("ok") and res["fatti"][0]["testate"] == ["Bit Lumen"]
         and "notizie_tema_frase" in ctx.regole, str(ctx.regole))
ctx = contesto_tool("Dario", "familiare")
res = json.loads(reg.call("notizie", {"tema": "tecnologiche"}, ctx, "familiare"))
verifica("sezione detta con un'altra parola (notizie_sezione)",
         res.get("ok") and res["fatti"][0]["testate"] == ["Bit Lumen"]
         and "notizie_sezione" in ctx.regole, str(ctx.regole))
ctx = contesto_tool("Dario", "familiare")
res = json.loads(reg.call("notizie", {"tema": "tecnologia"}, ctx, "familiare"))
verifica("contrario: la sezione già giusta non scrive notizie_sezione",
         res.get("ok") and "notizie_sezione" not in ctx.regole, str(ctx.regole))
ctx = contesto_tool("Dario", "familiare")
res = json.loads(reg.call("notizie", {"tema": "locale"}, ctx, "familiare"))
verifica("sezione senza giornali in casa (nessuna regione): lo dice, senza cercare",
         res.get("trovato") is False and "regione" in res["cosa_fare"], str(res))
ctx = contesto_tool("Dario", "familiare")
res = json.loads(reg.call("notizie", {"tema": "notizie sul derby"}, ctx, "familiare"))
verifica("tema con «notizie» dentro: resta l'argomento (il derby, due voci: niente ripiego)",
         res.get("ok") and "erby" in res["fatti"][0]["titolo"]
         and "notizie_ripiego" not in ctx.regole, str(res)[:300])
ctx = contesto_tool("Dario", "familiare")
res = json.loads(reg.call("notizie", {"tema": "sciopero"}, ctx, "familiare"))
verifica("ripiego: una voce sola sul tema in 72 ore → anche internet (notizie_ripiego)",
         res.get("risultati") and "notizie_ripiego" in ctx.regole, str(res)[:300])
# Ripiego su SearXNG: poche voci sul tema
sx.risposte["vulcano"] = [{"url": "https://www.esempio.it/vulcano", "title": "Il vulcano Lumen",
                          "content": "Eruzione modesta stamattina.", "engine": "bing"}]
ctx = contesto_tool("Dario", "familiare")
n_sx = len(sx.richieste)
res = json.loads(reg.call("notizie", {"tema": "vulcano"}, ctx, "familiare"))
verifica("ripiego: nessuna voce sul tema → SearXNG (notizie_ripiego), categoria news",
         res.get("ok") and res.get("risultati") and "notizie_ripiego" in ctx.regole
         and sx.richieste[n_sx:] and sx.richieste[-1][2].get("categories") == "news",
         str(res)[:300])
ctx = contesto_tool("Bianca", "ospite")
n_sx = len(sx.richieste)
res = json.loads(reg.call("notizie", {"tema": "vulcano"}, ctx, "ospite"))
verifica("contrario ripiego: un ospite (web_livello familiare) non esce: «non c'è niente»",
         res.get("trovato") is False and len(sx.richieste) == n_sx, str(res))
# Minori: solo sport, tecnologia e ragazzi
ctx = contesto_tool("Pietro", "familiare")
res = json.loads(reg.call("notizie", {}, ctx, "familiare"))
testate_min = {t for f in res.get("fatti", []) for t in f["testate"]}
verifica("minore: le notizie generali sono quelle dei temi dei ragazzi",
         res.get("ok") and testate_min <= {"Bit Lumen", "Lumen Ragazzi"}
         and "Agenzia Lumen" not in testate_min, str(res)[:300])
fest = [f for f in res.get("fatti", []) if "festival" in f["titolo"].lower()]
verifica("minore: un fatto dato anche dai generali ha solo le voci dei temi dei ragazzi",
         fest and fest[0]["testate"] == ["Lumen Ragazzi"], str(fest))
fest_a = [f for f in svc.principali(("generale",), n=10) if "festival" in f.titolo.lower()]
verifica("contrario: per un adulto lo stesso fatto ha tutte le testate",
         fest_a and set(fest_a[0].testate) == {"Agenzia Lumen", "Lumen Ragazzi"},
         str(fest_a and fest_a[0].testate))
verifica("minore: filtro dei contenuti per adulti (il gioco d'azzardo fuori)",
         not any("azzardo" in f["titolo"].lower() for f in res.get("fatti", []))
         and "minore_contenuto_adulto" in ctx.regole, str(ctx.regole))
ctx = contesto_tool("Pietro", "familiare")
res = json.loads(reg.call("notizie", {"tema": "economia"}, ctx, "familiare"))
verifica("minore: una sezione per adulti no, con la frase pronta (minore_notizie)",
         res.get("ok") is False and "sport" in res.get("risposta_finale", "")
         and "minore_notizie" in ctx.regole, str(res))
ctx = contesto_tool("Pietro", "familiare")
n_sx = len(sx.richieste)
res = json.loads(reg.call("notizie", {"tema": "vulcano"}, ctx, "familiare"))
verifica("minore: niente ripiego su internet", len(sx.richieste) == n_sx
         and res.get("trovato") is False, str(res))
ctx = contesto_tool("Pietro", "familiare")
res = json.loads(reg.call("notizie", {"tema": "frana"}, ctx, "familiare"))
verifica("minore: la ricerca resta nei temi dei ragazzi (la frana dei generali no)",
         not res.get("fatti"), str(res)[:200])
# web_cerca con il tipo «notizie» rimasto nell'abitudine del modello
ctx = contesto_tool("Dario", "familiare")
res = json.loads(reg.call("web_cerca", {"tipo": "notizie", "domanda": "derby"}, ctx,
                          "familiare"))
verifica("web_cerca tipo notizie → le notizie dei feed (web_notizie_al_tool)",
         res.get("fatti") and "web_notizie_al_tool" in ctx.regole, str(ctx.regole))

# Capacità e prompt
c_off = Config()
c_off.notizie_enabled = False
c_on = Config()
c_on.online = False
verifica("capacità: spente e senza rete «da configurare»",
         capacita.check_notizie(c_off)["stato"] == "da_configurare"
         and capacita.check_notizie(c_on)["stato"] == "da_configurare")
d = capacita.check_notizie(cfg, svc)
verifica("capacità: attiva con le voci e i guasti nei dettagli", d["stato"] == "attiva"
         and d["dettagli"]["voci"] > 5 and d["dettagli"]["spente"] == ["Il Post",
                                                                         "Il Sole 24 Ore"],
         str(d))
verifica("capacità: «notizie dai giornali» nel prompt quando il tool c'è",
         "notizie dai giornali" in capacita.testo_prompt(None, ["notizie"])
         and "notizie dai giornali" not in capacita.testo_prompt(None, ["web_cerca"]))
p = Config().prompt_for(True, web=True, notizie=True)
verifica("prompt: le notizie al tool notizie, web_cerca per il resto",
         "chiama notizie" in p and "Per il meteo, i risultati sportivi" in p, p[-900:])
verifica("contrario prompt: senza notizie il prompt è quello di prima",
         Config().prompt_for(True, web=True) == Config().prompt_for(True, web=True,
                                                                     notizie=False)
         and "chiama notizie" not in Config().prompt_for(True, web=True))
p = Config().prompt_for(False, notizie=True)
verifica("prompt senza web: le notizie sì, il meteo no",
         "chiama notizie" in p and "Non puoi sapere il meteo" in p and "meteo e notizie" not in p,
         p[-500:])

# ─────────────────────────── 8. Brain a secco (decisione 7) ───────────────────────────


class BackendFinto:
    def __init__(self, copione):
        self.copione = list(copione)
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append(json.dumps(messages, ensure_ascii=False))
        yield from self.copione.pop(0)


def call(i, nome, args):
    return {"id": f"call_{i}", "name": nome, "arguments": args}


def brain(copione, nome="Lucia"):
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, reg, []
    b.tool_ctx = contesto_tool(nome, "familiare")
    b.backend = BackendFinto(copione)
    b.on_tool_start = None
    return b


b = brain([
    [("calls", [call(0, "notizie", {})])],
    [("text", "Tre notizie: una frana chiude il passo Ventoso, secondo l'Agenzia Lumen e altre "
              "due testate; la Lumenese vince il derby; e venerdì c'è sciopero dei treni. "
              "Vuoi saperne di più su una?")],
    # «Dimmi di più sulla seconda»: il modello chiama notizie con fatto 2
    [("calls", [call(1, "notizie", {"fatto": 2})])],
    [("text", "Secondo Tele Aurora la Lumenese ha vinto 2 a 1.")],
    # «E chi l'ha detto?»: risponde dal contesto, senza tool
    [("text", "L'hanno detto Tele Aurora e la Gazzetta di Borgoverde.")],
    [("text", "Prego.")],
    [("text", "Va bene.")],
])
"".join(b.stream_reply("Che notizie ci sono?", "familiare"))
tool_n = [m for m in b.history if m["role"] == "tool" and m["name"] == "notizie"]
verifica("brain: il risultato di notizie resta nella storia (non WEB_TOLTO)",
         tool_n and tool_n[0]["content"] != WEB_TOLTO and "Frana sul passo Ventoso"
         in tool_n[0]["content"], tool_n[0]["content"][:200] if tool_n else "")
verifica("brain: ... in busta come dato non fidato (fonte web), con avviso e cosa_fare fuori",
         "DATO NON FIDATO (fonte: web)" in tool_n[0]["content"]
         and json.loads(tool_n[0]["content"]).get("cosa_fare")
         and "fatti" in json.loads(tool_n[0]["content"])["dato_non_fidato"]["contenuto"])
verifica("brain: la conversazione resta contaminata (provenienza)",
         "web" in provenienza.fonti(b.history))
"".join(b.stream_reply("Dimmi di più sulla seconda", "familiare"))
prima_passata_2 = b.backend.visti[2]
verifica("brain: la domanda dopo arriva al modello con i fatti nel contesto (titoli, testate, "
         "sommari)", "Frana sul passo Ventoso" in prima_passata_2
         and "Lumenese" in prima_passata_2 and "Tele Aurora" in prima_passata_2
         and "Deviazioni per i camion" in prima_passata_2, prima_passata_2[-600:])
verifica("brain: notizie con fatto 2 → il derby, risultato nella storia",
         "Derby" in [m for m in b.history if m["role"] == "tool"][-1]["content"])
"".join(b.stream_reply("E chi l'ha detto?", "familiare"))
terza = b.backend.visti[4]
verifica("brain: due turni dopo il primo elenco è ancora nel contesto (forma ridotta: titoli e "
         "testate, senza sommario)", "Frana sul passo Ventoso" in terza
         and "Deviazioni per i camion" not in terza and contesto.NOTA_RIDOTTA in terza
         and "Risultato di un turno precedente, ridotto" not in terza, terza[-900:])
verifica("brain: il seguito del turno appena prima è intero (sommari delle testate)",
         "Doppietta del centravanti" in terza)
"".join(b.stream_reply("Grazie", "familiare"))
"".join(b.stream_reply("Ok", "familiare"))
quinta = b.backend.visti[-1]
verifica("brain: quattro turni dopo titoli e testate restano (forma ridotta, in busta)",
         "Frana sul passo Ventoso" in quinta and "DATO NON FIDATO (fonte: web)" in quinta
         and "Derby" in quinta)
# Dopo il risultato, nella stessa risposta, niente azioni (DOPO_DATO)
b = brain([
    [("calls", [call(0, "notizie", {})])],
    [("calls", [call(1, "ricorda", {"fatto": "il passo Ventoso è chiuso"}),
                call(2, "ora_attuale", {})])],
    [("text", "Ecco.")],
])
"".join(b.stream_reply("Le notizie, e ricordati della frana", "familiare"))
stato = {t["nome"]: t for t in b.last_tools}
verifica("brain: dopo le notizie, nella stessa risposta, le azioni sono bloccate",
         stato["ricorda"]["ok"] is False and stato["ricorda"].get("bloccato") == "web"
         and stato["ora_attuale"]["ok"] is True, str(b.last_tools))
verifica("brain: il tema non va nel registro dei turni (segreti)",
         stato["notizie"]["argomenti"] in ({}, {"tema": "******"}), str(stato["notizie"]))
# _compatta_storia da sola: il turno precedente intero, i più vecchi ridotti
storia = [{"role": "user", "content": "notizie"},
          {"role": "assistant", "content": "", "tool_calls": [call(0, "notizie", {})]},
          {"role": "tool", "name": "notizie", "tool_call_id": "call_0", "content": tool_n[0]["content"]},
          {"role": "assistant", "content": "Tre notizie."},
          {"role": "user", "content": "e poi?"}]
copia = [dict(m) for m in storia]
_compatta_storia(copia)
verifica("compattazione: il turno precedente non si tocca", copia[2]["content"]
         == tool_n[0]["content"])
copia = [dict(m) for m in storia] + [{"role": "assistant", "content": "Sì."},
                                     {"role": "user", "content": "altro?"}]
_compatta_storia(copia)
rid = json.loads(copia[2]["content"])
verifica("compattazione: due turni dopo la forma ridotta (n, titolo, testate, quando)",
         rid["nota"] == contesto.NOTA_RIDOTTA
         and set(rid["dato_non_fidato"]["contenuto"]["fatti"][0]) <= {"n", "titolo", "testate",
                                                                     "quando"}
         and rid["dato_non_fidato"]["avviso"].startswith("[DATO NON FIDATO") is False
         and "DATO NON FIDATO (fonte: web)" in rid["dato_non_fidato"]["avviso"], str(rid)[:300])
verifica("contrario compattazione: un altro tool lungo diventa la traccia generica",
         contesto.riduci(json.dumps({"ok": True, "risultati": ["x" * 500]})) is None)

# Le proiezioni del registro degli eventi (passo 3) fanno lo stesso
from calliope.eventi import proiezioni  # noqa: E402
from calliope.eventi.ombra import _forma_brain  # noqa: E402
forma = _forma_brain()
r = {"content": tool_n[0]["content"], "name": "notizie", "non_fidato": True, "resta": True}
verifica("eventi: il risultato di notizie resta nel turno dopo",
         proiezioni._esito_reso(r, False, False, forma, False) == tool_n[0]["content"])
verifica("eventi: nei turni vecchi la forma ridotta",
         json.loads(proiezioni._esito_reso(r, True, False, forma, False))["nota"]
         == contesto.NOTA_RIDOTTA)
verifica("contrario eventi: un non fidato senza «resta» (web_cerca) diventa WEB_TOLTO",
         proiezioni._esito_reso({**r, "name": "web_cerca", "resta": None}, False, False, forma,
                                False) == WEB_TOLTO)

svc.close()
srv.ferma()
sx.ferma()
web.close()
print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
