import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il Markdown dei testi dell'agente, a secco (07/10/2026, decisioni di Dario: i testi
dell'agente in `risultato.md`, il lettore nella scheda del documento, «Scarica», le conversioni
a richiesta, il risultato al portatile).

1. **Il modulo** (calliope/documenti/markdown.py): blocchi, righe, voce, descrizione,
   conversioni in blocchi (PDF e Word veri con fpdf2 e python-docx) e da blocchi; i testi
   ostili (script, HTML grezzo, javascript:, tabelle enormi, annidamenti profondi, enfasi
   senza chiusura) restano testo e costano poco.
2. **L'agente** (FakeOllama): la ricerca consegnata in Markdown diventa `risultato.md`, la
   frase finale dice cosa contiene e resta senza simboli, la scheda è quella del documento con
   il Markdown e «Scarica»; il risultato va al portatile (RemoteDelivery con un satellite
   finto) con «Lo apro?» e l'azione in sospeso; senza portatile resta sul server e la frase lo
   dice; per_la_voce toglie il Markdown e scarta ancora il codice.
3. **Schermi e «Scarica»** (hub vero, server degli schermi vero su 127.0.0.1): la sorgente
   (`_scarica`) non esce mai verso le pagine né nella cronologia; il gettone solo per lo
   schermo personale a cui la scheda è arrivata, del suo proprietario (o di chi amministra),
   mai dalla zona grigia né da uno schermo di stanza; formato non ammesso; scadenza e usi; il
   GET con Content-Disposition, CSP «sandbox» e nosniff; PDF, Word e MD veri.
4. **«Fammene un PDF»** (lavoro_risultato con modo pdf/word): il file nella cartella del
   lavoro e al portatile, «Lo apro?»; il codice no; nella zona grigia la scheda senza
   «Scarica».

    python prove\\prova_markdown.py
"""

import io
import json
import queue
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from calliope.documenti import markdown as md

errori = 0
TMP = Path(tempfile.mkdtemp(prefix="calliope-markdown-"))


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {str(dettaglio)[:300]}" if dettaglio else ""),
          flush=True)


def sezione(nome):
    print(f"— {nome}", flush=True)


def aspetta(cond, s=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


RELAZIONE = """# Le api in Italia

Una **relazione** breve con un [collegamento](https://example.org/api) e del `codice`.

## Numeri

| Regione | Alveari |
|---|---:|
| Veneto | 120 |
| Lazio \\| Roma | 80 |

## Cosa fare

- primo punto
  - sotto punto
- secondo *punto*

1. uno
2. due

> una citazione
> > annidata

```python
print("<script>alert(1)</script>")
```
"""

# ═══════════════════════════ 1. il modulo ═══════════════════════════
sezione("modulo Markdown")
b = md.analizza(RELAZIONE)
tipi = [x["tipo"] for x in b]
verifica("blocchi: titoli, paragrafo, tabella, elenchi, citazione, codice",
         tipi == ["titolo", "paragrafo", "titolo", "tabella", "titolo", "elenco", "elenco",
                  "citazione", "codice"], tipi)
tab = next(x for x in b if x["tipo"] == "tabella")
verifica("tabella: colonne e «\\|» dentro una cella", tab["colonne"] == ["Regione", "Alveari"]
         and tab["righe"][1] == ["Lazio | Roma", "80"], tab)
el = [x for x in b if x["tipo"] == "elenco"]
verifica("elenchi: puntato con un livello annidato, poi numerato a parte",
         [v["livello"] for v in el[0]["voci"]] == [0, 1, 0] and el[1]["voci"][0]["numerato"]
         and not el[0]["voci"][0]["numerato"], el)
cit = next(x for x in b if x["tipo"] == "citazione")
verifica("citazione annidata", cit["blocchi"][1]["tipo"] == "citazione", cit)
verifica("titolo sottolineato (=== e ---)", [x["tipo"] for x in md.analizza("Uno\n===\n\nDue\n---")]
         == ["titolo", "titolo"])
verifica("in_linea: grassetto, corsivo, codice, collegamento con l'indirizzo",
         md.in_linea("Una **relazione** _breve_ con [qui](https://x.it) e `a*b`")
         == "Una relazione breve con qui (https://x.it) e a*b",
         md.in_linea("Una **relazione** _breve_ con [qui](https://x.it) e `a*b`"))
verifica("in_linea: le parole con «_» restano intere (nome_file, 2*3*4)",
         md.in_linea("nome_del_file e 2*3*4") == "nome_del_file e 2*3*4")
verifica("in_linea: immagine come segnaposto, mai l'indirizzo a voce",
         md.in_linea("![grafico](http://x/y.png)") == "[immagine: grafico]"
         and md.in_linea("![grafico](http://x/y.png)", indirizzi=False) == "")
voce = md.per_voce(RELAZIONE)
verifica("per_voce: niente simboli, niente indirizzi, niente codice né tabelle",
         not any(c in voce for c in "#*|`>_") and "example.org" not in voce
         and "script" not in voce and "Veneto" not in voce and "Le api in Italia." in voce,
         voce)
verifica("descrivi: «2 sezioni, 2 elenchi e una tabella»",
         md.descrivi(RELAZIONE) == "2 sezioni, 2 elenchi e una tabella", md.descrivi(RELAZIONE))
verifica("sembra_markdown: sì per titoli/elenchi/tabelle, no per una frase semplice",
         md.sembra_markdown(RELAZIONE) and md.sembra_markdown("- a\n- b")
         and not md.sembra_markdown("Ho trovato tre fonti. Il resto è nel file."))
recinto = "```markdown\n# Titolo\n\n- voce\n```"
verifica("senza_recinto: il testo tutto in ```markdown è il Markdown (misura del 07/10)",
         md.senza_recinto(recinto) == ("# Titolo\n\n- voce", True)
         and md.senza_recinto("  ~~~md\nciao\n~~~\n") == ("ciao", True))
verifica("senza_recinto, contrari: un recinto in mezzo, di un altro linguaggio, non chiuso",
         not md.senza_recinto("Testo\n" + recinto)[1]
         and not md.senza_recinto(recinto + "\nDopo")[1]
         and not md.senza_recinto("```python\nprint(1)\n```")[1]
         and not md.senza_recinto("```markdown\n# Titolo")[1])
verifica("con_titolo: aggiunge «# Titolo» solo se manca",
         md.con_titolo("testo", "Relazione").startswith("# Relazione\n")
         and md.con_titolo(RELAZIONE, "Altro").startswith("# Le api in Italia"))

doc = md.a_blocchi(RELAZIONE)
verifica("a_blocchi: titolo del documento dal primo #, che resta il primo titolo",
         doc["titolo"] == "Le api in Italia" and doc["blocchi"][0] == {"tipo": "titolo", "testo":
                                                                      "Le api in Italia"}, doc)
verifica("a_blocchi: elenco annidato con «– », citazione tra «», codice come paragrafo",
         any(b.get("voci") and "– sotto punto" in b["voci"] for b in doc["blocchi"])
         and any(b.get("testo") == "«una citazione»" for b in doc["blocchi"])
         and any("print(" in str(b.get("testo")) for b in doc["blocchi"]), doc)
from calliope.documenti.render import plain_text, render
pdf = render("pdf", doc)
word = render("word", doc)
verifica("PDF vero da Markdown (fpdf2)", pdf[:5] == b"%PDF-", len(pdf))
testo_w = plain_text("word", word)
verifica("Word vero da Markdown (python-docx): titolo, tabella, voci",
         word[:2] == b"PK" and "Le api in Italia" in testo_w and "Lazio | Roma" in testo_w
         and "secondo punto" in testo_w, testo_w[:200])
md2 = md.da_blocchi({"titolo": "Spese", "blocchi": [
    {"tipo": "paragrafo", "testo": "# non un titolo *né corsivo*"},
    {"tipo": "elenco", "voci": ["a | b", "c"], "numerato": True},
    {"tipo": "tabella", "colonne": ["Voce", "Euro"], "righe": [["Luce", "10"], ["Gas", "5"]],
     "totale": True}]})
b2 = md.analizza(md2)
verifica("da_blocchi: il testo resta testo (# e * con la barra), tabella con il totale",
         [x["tipo"] for x in b2] == ["titolo", "paragrafo", "elenco", "tabella"]
         and md.in_linea(b2[1]["testo"]) == "# non un titolo *né corsivo*"
         and b2[3]["righe"][-1][0] == "Totale" and b2[3]["righe"][-1][1].startswith("15"), b2)

sezione("testi ostili")
OSTILI = {
    "script": "<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>",
    "javascript": "[clicca](javascript:alert(1)) <javascript:alert(2)>",
    "enfasi": "*a " * 60000,
    "collegamenti": "[a" * 80000,
    "immagini": "![x](" * 40000,
    "citazioni": ">" * 5000 + " fondo",
    "rientri": "\n".join(" " * i + "- x" for i in range(3000)),
    "tabella": "|a|b|\n|-|-|\n" + "|1|2|\n" * 20000,
    "colonne": "|" + "c|" * 300 + "\n|" + "-|" * 300 + "\n" + ("|" + "x|" * 300 + "\n") * 10,
    "lungo": "parola " * 100000,
    "controllo": "testo‮nascosto\u0007 e \x00 nulli",
}
for nome, t in OSTILI.items():
    t0 = time.perf_counter()
    bb = md.analizza(t)
    md.per_voce(t)
    d = md.a_blocchi(t, "Prova")
    dt = time.perf_counter() - t0
    verifica(f"ostile «{nome}»: analizzato e convertito in {dt:.2f} s (< 3 s)", dt < 3.0)
tb = md.analizza(OSTILI["tabella"])[0]
verifica("tabella enorme: al più 500 righe, le altre contate",
         len(tb["righe"]) == md.MAX_RIGHE and tb["altre"] == 20000 - md.MAX_RIGHE)
verifica("tabella larga: al più 20 colonne lette, 12 nel documento",
         len(md.analizza(OSTILI["colonne"])[0]["colonne"]) == md.MAX_COLONNE
         and len(md.a_blocchi(OSTILI["colonne"])["blocchi"][0]["colonne"]) == 12)
verifica("citazioni annidate: al più 4 livelli", json.dumps(md.analizza(OSTILI["citazioni"]))
         .count('"citazione"') <= md.MAX_CITAZIONI)
verifica("rientri: al più 6 livelli", max(v["livello"] for v in md.analizza(OSTILI["rientri"])[0]
                                          ["voci"]) == md.MAX_LIVELLO - 1)
verifica("lunghezza: al più 200 000 caratteri", len(md.normalizza("x" * 300_000)) == md.MAX_CARATTERI)
verifica("caratteri di controllo e di direzione tolti",
         md.normalizza(OSTILI["controllo"]) == "testonascosto e  nulli")
verifica("javascript: a voce niente indirizzo (resta il testo del collegamento)",
         "javascript" not in md.in_linea(OSTILI["javascript"], indirizzi=False)
         and "clicca" in md.in_linea(OSTILI["javascript"], indirizzi=False),
         md.in_linea(OSTILI["javascript"], indirizzi=False))
t0 = time.perf_counter()
grosso = md.a_blocchi(OSTILI["tabella"], "Tabella")
for f in ("pdf", "word"):
    render(f, grosso)
verifica("tabella enorme in PDF e Word in poco tempo (< 20 s)", time.perf_counter() - t0 < 20,
         f"{time.perf_counter() - t0:.1f} s")

# ═══════════════════════════ 2. l'agente ═══════════════════════════
sezione("agente")
from calliope.agenti import Lavori, carica
from calliope.agenti.ciclo import per_la_voce
from calliope.config import Config
from calliope.documenti.consegna import LocalDelivery, RemoteDelivery
from calliope.documenti.formato import FORMATI
from prove.ollama_finto import FakeOllama

verifica("per_la_voce: Markdown tolto, il codice ancora scartato",
         per_la_voce("## Risultato\n\n- Ho trovato **tre** fonti.\n- La funzione `conta()` "
                     "serve.") == "Risultato. Ho trovato tre fonti."
         and per_la_voce("Ho scritto conta_parole.py. Funziona bene.") == "Funziona bene.")

fake = FakeOllama().avvia()


def call(name, args=None):
    return {"name": name, "arguments": args or {}}


class PC:
    def __init__(self):
        self.offerte = []

    def offri_file(self, chi, item):
        self.offerte.append((chi, item))


class Satellite:
    """Un satellite finto con l'esecutore del PC che riceve i file."""

    def __init__(self, cartella: Path, collegato=True):
        self.cartella, self.collegato = cartella, collegato
        self.ricevuti = []
        self.esecutore = {"file": True}

    def per_pc(self):
        return self if self.collegato else None

    def consegna_file(self, stem, ext, dati, sostituisci=None, mtime=None, timeout=10.0):
        self.cartella.mkdir(parents=True, exist_ok=True)
        p = self.cartella / f"{stem}.{ext}"
        p.write_bytes(dati)
        self.ricevuti.append(p.name)
        return {"ok": True, "rif": f"sat:{p.name}", "nome_file": p.name, "mtime": 0,
                "maniglia": f"m-{len(self.ricevuti)}"}


class Biblioteca:
    """Una biblioteca finta: la ricerca usa i suoi strumenti e consegna."""

    def cerca(self, domanda):
        return []


def servizio(sotto, consegna=None):
    cfg = Config()
    cfg.agenti_url = fake.url
    cfg.agenti_modello = "qwen3.6:35b"
    cfg.agenti_risultati = str(TMP / sotto / "risultati")
    cfg.agenti_sandbox = str(TMP / sotto / "sandbox")
    cfg.agenti_modelli = str(TMP / sotto / "modelli")
    cfg.agenti_conferma = "mai"
    svc = Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI, consegna=consegna)
    svc.pcs = {"portatile": PC()}
    svc.agente.biblioteca = Biblioteca()
    return svc


def ricerca(svc, compito="Fai una ricerca sulle api in Italia"):
    fake.copione = [{"tool_calls": [call("consegna", {
        "testo": RELAZIONE, "riassunto": "Ho trovato **tre** fonti sulle api: il Veneto ne ha di "
                                         "più."})]}]
    lav = svc.nuovo("ricerca", compito, "marta", "Marta", "amministra")
    svc.avvia(lav)
    try:
        return lav, svc.done.get(timeout=15)
    except queue.Empty:
        return lav, None


sat = Satellite(TMP / "portatile" / "Documenti" / "Calliope")
svc = servizio("con-pc", RemoteDelivery(sat, LocalDelivery(TMP / "riserva"), "portatile"))
lav, item = ricerca(svc)
r = lav.risultato
cart = Path(r.get("cartella") or ".")
verifica("ricerca finita: risultato.md nella cartella del lavoro, niente Word",
         item and item["stato"] == "fatto" and (cart / "risultato.md").is_file()
         and not list(cart.glob("*.docx")), item and item["messaggio"])
verifica("risultato.md: il Markdown dell'agente com'è", (cart / "risultato.md").read_text(
    encoding="utf-8").startswith("# Le api in Italia"))
msg = item["messaggio"] if item else ""
verifica("annuncio: cosa contiene, il riassunto senza Markdown, dove, «Lo apro?»",
         "2 sezioni, 2 elenchi e una tabella" in msg and "**" not in msg and "#" not in msg
         and "del portatile" in msg and msg.endswith("Lo apro?"), msg)
verifica("al portatile: il file con il titolo del lavoro, la maniglia offerta ad «aprilo»",
         sat.ricevuti == ["Ricerca sulle api in Italia.md"]
         and svc.pcs["portatile"].offerte[0][0] == "marta"
         and svc.pcs["portatile"].offerte[0][1]["percorso"] == "m-1", sat.ricevuti)
verifica("azione in sospeso: pc_apri_file con il risultato 1",
         (item.get("in_sospeso") or {}).get("tool") == "pc_apri_file"
         and item["in_sospeso"]["argomenti"] == {"risultato": 1}, item.get("in_sospeso"))
verifica("niente copia di riserva sul server", not (TMP / "riserva").exists()
         or not list((TMP / "riserva").iterdir()))
card = svc.scheda(lav)
verifica("scheda: quella del documento con il Markdown, chiave del lavoro, «Scarica»",
         card["tipo"] == "documento" and card["markdown"].startswith("# Le api")
         and card["chiave"] == f"lavoro:{lav.id}" and card["scarica"] == ["md", "pdf", "word"]
         and card["_scarica"]["markdown"].startswith("# Le api")
         and card["riassunto"].startswith("Ho trovato tre fonti"), {k: card[k] for k in
                                                                   ("tipo", "chiave", "scarica")})
meta = json.loads((cart / "lavoro.json").read_text(encoding="utf-8"))
verifica("lavoro.json: il testo e il file risultato.md (per lavoro_risultato dopo un riavvio)",
         meta["file"] == ["risultato.md"] and meta["testo"].startswith("# Le api"))

sat2 = Satellite(TMP / "spento", collegato=False)
svc2 = servizio("senza-pc", RemoteDelivery(sat2, LocalDelivery(TMP / "riserva2"), "portatile"))
lav2, item2 = ricerca(svc2)
msg2 = item2["messaggio"] if item2 else ""
verifica("senza portatile: resta sul server e la frase lo dice, niente «Lo apro?»",
         "sul server, nella cartella Lavori, perché il portatile non è collegato" in msg2
         and not msg2.endswith("?") and not item2.get("in_sospeso") and not sat2.ricevuti, msg2)
svc3 = servizio("locale", None)
lav3, item3 = ricerca(svc3)
msg3 = item3["messaggio"] if item3 else ""
verifica("Calliope sul PC stesso: il file è già nei suoi Documenti, «Lo apro?» con il percorso",
         msg3.endswith("Lo apro?") and svc3.pcs["portatile"].offerte
         and svc3.pcs["portatile"].offerte[0][1]["percorso"].endswith("risultato.md"), msg3)

# ═══════════════════════════ 3. schermi e «Scarica» ═══════════════════════════
sezione("schermi e «Scarica»")
from calliope.schermi import ArchivioSchermi, Schermi, schede
from calliope.schermi.hub import Mittente
from calliope.schermi.scarica import Rifiuto
from calliope.schermi.server import ServerSchermi

cfgs = Config()
cfgs.schermi_scarica_s = 2.0
hub = Schermi(cfgs, ArchivioSchermi(str(TMP / "schermi.db")), log=lambda m: None)
arch = hub.archivio
s_marta, t_marta = arch.crea_con_token("tablet-marta", proprietario="marta",
                                       proprietario_nome="Marta")
s_luca, t_luca = arch.crea_con_token("tablet-luca", proprietario="luca", proprietario_nome="Luca")
s_cucina, t_cucina = arch.crea_con_token("cucina")
hub._rinfresca()
ids = {"tablet-marta": s_marta["id"], "tablet-luca": s_luca["id"], "cucina": s_cucina["id"]}
nomi = {v: next(s["nome"] for s in hub.abbinati() if s["id"] == v) for v in ids.values()}
marta = Mittente(persona="marta", nome="Marta", livello="amministra", certo=True)
r = hub.invia(card, marta, forza=True)
verifica("la scheda va solo allo schermo personale di chi l'ha chiesto", r["destinatari"] ==
         [nomi[ids["tablet-marta"]]], r)
storia = hub.storia(ids["tablet-marta"])
verifica("la sorgente (_scarica) non entra nella cronologia (né nelle pagine)",
         storia and "_scarica" not in storia[-1] and storia[-1]["markdown"].startswith("# Le api"))
verifica("registrata per lo schermo di Marta, non per gli altri",
         hub.scaricamenti.voce(ids["tablet-marta"], card["chiave"]) is not None
         and hub.scaricamenti.voce(ids["tablet-luca"], card["chiave"]) is None)
grigia = Mittente(persona="marta", nome="Marta", livello="familiare", certo=False)
card_g = schede.documento_markdown("Altro", "# Altro\n\ntesto", ident="G1")
r = hub.invia(card_g, grigia, forza=True)
verifica("zona grigia: niente scheda personale e niente «Scarica»",
         not r["destinatari"] and hub.scaricamenti.voce(ids["tablet-marta"], "lavoro:G1") is None)
sm = hub.schermo(ids["tablet-marta"])
g = hub.scaricamenti.gettone(sm, card["chiave"], "pdf")
verifica("gettone per il proprietario: un indirizzo /scarica/… e il nome del file",
         g["url"].startswith("/scarica/") and g["nome"] == "Ricerca sulle api in Italia.pdf", g)


def rifiuto(f):
    try:
        f()
    except Rifiuto as e:
        return e.stato
    return None


sl = hub.schermo(ids["tablet-luca"])
sc = hub.schermo(ids["cucina"])
verifica("lo schermo di un altro: la scheda non c'è (404)",
         rifiuto(lambda: hub.scaricamenti.gettone(sl, card["chiave"], "pdf")) == 404)
verifica("uno schermo di stanza: mai (403)",
         rifiuto(lambda: hub.scaricamenti.gettone(sc, card["chiave"], "pdf")) == 403)
verifica("formato non ammesso (exe, excel per un testo): 400",
         rifiuto(lambda: hub.scaricamenti.gettone(sm, card["chiave"], "exe")) == 400
         and rifiuto(lambda: hub.scaricamenti.gettone(sm, card["chiave"], "excel")) == 400)
# Lo schermo di Marta passa a Luca (abbinato di nuovo): la scheda era per Marta
voce_vecchia = hub.scaricamenti.voce(ids["tablet-marta"], card["chiave"])
altro = dict(sm, proprietario="luca")
verifica("schermo passato a un'altra persona: 403; chi amministra sì",
         rifiuto(lambda: hub.scaricamenti.gettone(altro, card["chiave"], "pdf")) == 403
         and hub.scaricamenti.gettone(altro, card["chiave"], "pdf", amministra=True)["url"])
# invia_a (la risposta allo schermo da cui si è scritto): vale il proprietario dello schermo
doc_card = schede.documento({"titolo": "Lettera", "blocchi": [
    {"tipo": "paragrafo", "testo": "Gentile signora Bianchi,"}]}, "word", "Lettera.docx", ident=7)
hub.invia_a(ids["tablet-luca"], doc_card)
verifica("invia_a a uno schermo personale: scaricabile per il suo proprietario",
         hub.scaricamenti.gettone(sl, "documento:7", "md")["nome"] == "Lettera.md")
hub.invia_a(ids["cucina"], dict(doc_card, chiave="documento:8"))
verifica("invia_a a uno schermo di stanza: niente", hub.scaricamenti.voce(ids["cucina"],
                                                                         "documento:8") is None)

web = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
base = f"http://127.0.0.1:{web.port}"


def post(url, dati=None, intest=None):
    req = urllib.request.Request(base + url, data=json.dumps(dati or {}).encode(),
                                 headers={"Content-Type": "application/json", **(intest or {})},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}"), _min(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), _min(e.headers)


def _min(h):
    return {k.lower(): v for k, v in h.items()}


def get(url):
    try:
        with urllib.request.urlopen(base + url, timeout=20) as r:
            return r.status, r.read(), _min(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), _min(e.headers)


try:
    st, acc, _ = post("/api/accedi", intest={"Authorization": f"Bearer {t_marta}"})
    sess = acc.get("sessione", "")
    st, d, _ = post("/api/scarica", {"chiave": card["chiave"], "formato": "word"},
                    {"X-Calliope-Sessione": sess})
    verifica("POST /api/scarica dalla pagina di Marta: l'indirizzo", st == 200
             and d["url"].startswith("/scarica/"), d)
    st, dati, h = get(d["url"])
    verifica("GET: un Word vero, come allegato, con il nome in UTF-8",
             st == 200 and dati[:2] == b"PK" and h.get("content-disposition", "").startswith(
                 "attachment;") and "filename*=UTF-8''Ricerca%20sulle%20api" in
             h.get("content-disposition", ""), h.get("content-disposition"))
    verifica("GET: nosniff, CSP sandbox, niente cache",
             h.get("x-content-type-options") == "nosniff" and "sandbox" in
             h.get("content-security-policy", "") and h.get("cache-control") == "no-store", h)
    st, d, _ = post("/api/scarica", {"chiave": card["chiave"], "formato": "md"},
                    {"X-Calliope-Sessione": sess})
    st, dati, h = get(d["url"])
    verifica("MD: il testo com'è, text/markdown", st == 200 and dati.decode("utf-8").startswith(
        "# Le api in Italia") and h.get("content-type", "").startswith("text/markdown"), h)
    st, d, _ = post("/api/scarica", {"chiave": card["chiave"], "formato": "pdf"},
                    {"X-Calliope-Sessione": sess})
    usi = [get(d["url"])[0] for _ in range(4)]
    verifica("lo stesso indirizzo vale per 3 richieste, poi no", usi == [200, 200, 200, 404], usi)
    st, d, _ = post("/api/scarica", {"chiave": card["chiave"], "formato": "pdf"},
                    {"X-Calliope-Sessione": sess})
    time.sleep(2.2)
    verifica("l'indirizzo scade (schermi_scarica_s)", get(d["url"])[0] == 404)
    st, d, _ = post("/api/scarica", {"chiave": card["chiave"], "formato": "pdf"})
    verifica("senza sessione: 401", st == 401, st)
    st, acc_l, _ = post("/api/accedi", intest={"Authorization": f"Bearer {t_luca}"})
    st, d, _ = post("/api/scarica", {"chiave": card["chiave"], "formato": "pdf"},
                    {"X-Calliope-Sessione": acc_l.get("sessione", "")})
    verifica("dalla pagina di Luca il documento di Marta: no", st == 404, (st, d))
    verifica("un gettone inventato: 404", get("/scarica/inventato123")[0] == 404)
finally:
    web.ferma()

# ═══════════════════════════ 4. «fammene un PDF» ═══════════════════════════
sezione("fammene un PDF")
from calliope.agenti import risultato as ar

out = ar.converti(svc, lav, ar.testo_intero(lav), "pdf", attesa_s=10)
pdfs = list(cart.glob("*.pdf"))
verifica("PDF nella cartella del lavoro e al portatile, «Lo apro?»",
         out["ok"] and pdfs and pdfs[0].read_bytes()[:5] == b"%PDF-"
         and "Ricerca sulle api in Italia.pdf" in sat.ricevuti
         and out["frase"].endswith("Lo apro?") and out["in_sospeso"]["tool"] == "pc_apri_file",
         out)
out = ar.converti(svc2, lav2, ar.testo_intero(lav2), "word", attesa_s=10)
verifica("Word senza portatile: nella cartella del lavoro, la frase lo dice",
         out["ok"] and list(Path(lav2.risultato["cartella"]).glob("*.docx"))
         and "non è collegato" in out["frase"] and "in_sospeso" not in out, out)
out = ar.converti(svc, lav, ar.testo_intero(lav), "pdf", attesa_s=0.0)
verifica("oltre l'attesa: «ti avviso», poi l'annuncio", "ti avviso" in out["frase"]
         and aspetta(lambda: not svc.done.empty(), 10)
         and svc.done.get_nowait()["messaggio"].startswith("Marta, ho fatto il PDF"), out)

from calliope.tools import agenti as ta
from calliope.tools.spec import ToolContext


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    def get(self, n):
        return {"Marta": Prof("marta", "Marta")}.get(n)


class HubFinto:
    def __init__(self):
        self.inviate = []

    def mittente(self, ctx):
        return Mittente(persona="marta", nome="Marta", livello="familiare", certo=False)

    def invia(self, card, mitt, forza=False):
        self.inviate.append(card)
        return {"schermi": ["tablet-marta"], "destinatari": ["tablet-marta"], "motivo": ""}


def contesto(hubf=None):
    sc = SimpleNamespace(current_speaker="Marta", current_level="amministra",
                         from_session=True, identified_by="breve")
    ctx = ToolContext(cfg=svc.cfg, speaker_ctx=sc, speakers=Speakers(), speaker=None,
                      lavori=svc)
    ctx.schermi, ctx.user_text, ctx.regole = hubf, "Fammene un PDF", []
    return ctx


hubf = HubFinto()
ctx = contesto(hubf)
res = ta._risultato_lavoro(ctx, "", "word")
verifica("lavoro_risultato modo word: il file Word e la frase", res.get("ok")
         and "documento Word" in res["risposta_finale"] and list(cart.glob("*.docx")), res)
res = ta._risultato_lavoro(ctx, "", "mostra")
verifica("zona grigia (risultato proprio): la scheda c'è, senza «Scarica»",
         hubf.inviate and "scarica" not in hubf.inviate[-1] and "_scarica" not in hubf.inviate[-1]
         and hubf.inviate[-1].get("markdown"), [list(c) for c in hubf.inviate][-1:])
lc = svc.nuovo("codice", "Scrivi un programma che somma", "marta", "Marta", "amministra")
lc.stato, lc.fine, lc.risultato = "fatto", time.time(), {"esito": "fatto", "cartella": str(cart),
                                                          "file": []}
with svc._lock:
    svc.lavori.append(lc)
res = ta._risultato_lavoro(contesto(), lc.id, "pdf")
verifica("il codice non si converte", res.get("ok") is False
         and "programma" in res["risposta_finale"], res.get("risposta_finale"))

for s in (svc, svc2, svc3):
    s.close()
fake.ferma()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
sys.exit(1 if errori else 0)
