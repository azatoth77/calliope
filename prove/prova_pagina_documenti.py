"""Prova a secco della pagina Documenti di «Le mie cose» (28/10/2026, passo 2d di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md § 4.8, issue #259 di #241; area
docs/aree/schermi-telefono.md).

1. **Fatti da Calliope** (`raccolte.pagina(…, "documenti")`): i propri, con la scheda `documento`
   di sempre («Scarica» nei suoi formati, la sorgente resta sul server); chi amministra vede anche
   quelli di Bianca e di un minore, ognuno col nome (decisione di Dario del 28/10); un familiare
   non vede quelli di Dario; un minore vede solo i suoi, e con il preset «documenti: no» nessuno.
2. **Archivio di casa** per tipo (`Archivio.documenti` con `Chi`, come a voce): chi amministra
   tutto, anche i personali degli altri; un familiare quelli di casa e i suoi, non i personali di
   Dario né quelli di un minore; un minore niente (come i tool dell'archivio a voce); ogni riga
   dice di chi è e ha «Scarica» del file originale.
3. **La ricerca** (`raccolte.cerca`): le stesse regole; testo ostile (HTML, virgolette, FTS)
   restituito come testo, mai un errore; testo vuoto e troppo lungo.
4. **Servizi che mancano o sollevano**: la pagina dà una nota o un 503, mai un'eccezione; la
   tessera Documenti col servizio vero (prima chiamava `recenti` sul servizio, che non l'ha).
5. **«Scarica»** (scarica.py): il file originale dell'archivio col tipo giusto e il nome con gli
   accenti (`filename*` e il nome di riserva senza accenti); i permessi rifatti al clic (il file
   tolto, la persona che non può più vederlo: 404); un formato che non è del documento: 400.
6. **Il server** vero su 127.0.0.1: la pagina da `/api/raccolte`, la ricerca da
   `/api/raccolte/cerca` (20 al minuto: la 21ª dà 429; un ospite 403; dati sbagliati 400), lo
   scaricamento vero da `/scarica/<gettone>` per chi amministra (il documento di Bianca) e per
   Bianca (il suo referto), mai una riga dell'archivio di un altro.
7. **L'annuncio** di un documento finito in secondo piano, rimasto sul server, con lo schermo
   personale abbinato ma chiuso: «in Le mie cose, alla voce Documenti», senza dire «telefono».
8. **Dalla revisione della PR #268**: la pagina con più di 8 documenti lo dice e la ricerca li trova
   tutti (anche oltre i 50); la ricerca con sole parole vuote non elenca niente; le voci di «Scarica»
   di uno schermo non tolgono quelle di un altro; il file originale riletto a ogni uso, con nome e
   tipo dal file letto davvero; `Archivio.file_di` mai fuori dalla cartella (`..`, percorso assoluto,
   giunzione NTFS) né oltre `archivio_max_mb`; la tessera di chi amministra dice «tuoi».
9. **Dalla seconda revisione della PR #268** (commento sulla #260): la ricerca trova i titoli fatti
   di parole corte («CV», «Tre re») e ordina per pertinenza (il documento cercato non resta fuori dai
   primi 20 dietro a quelli più recenti); il nome in «Scaricato: …» è quello del file salvato anche
   quando la copia vera ha un'altra estensione; le voci di «Scarica» degli schermi revocati (dal
   tool, e da terminale con un altro processo) se ne vanno.

Nomi e dati di fantasia, niente rete né modelli.

    python prove/prova_pagina_documenti.py
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope.archivio import testo as lettura  # noqa: E402
from calliope.archivio.grafo import Grafo  # noqa: E402
from calliope.archivio.servizio import Archivio  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.documenti.servizio import Archive  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi, raccolte, scarica  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

import prova_raccolte as pr  # noqa: E402  (chiedi: le richieste al server)

TMP = Path(tempfile.mkdtemp(prefix="calliope-pagina-documenti-"))
ERRORI = []
OSTILE = '<img src=x onerror="alert(1)">'


def js(x, **k):
    k.setdefault("ensure_ascii", False)
    return json.dumps(x, default=str, **k)


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


class Profilo:
    def __init__(self, pid, nome, admin=False, nascita=None, tutori=()):
        self.id, self.name, self.admin, self.nascita = pid, nome, admin, nascita
        self.fascia, self.tutori, self.preferred_tone, self.preferred_voice = None, list(tutori), None, None


DARIO = Profilo("dario", "Dario Rossi", admin=True, nascita="1978-02-02")
BIANCA = Profilo("bianca", "Bianca", nascita="1981-06-06")
TEO = Profilo("teo", "Teo", nascita="2011-05-05", tutori=["bianca"])       # 15 anni: documenti sì
LIA = Profilo("lia", "Lia", nascita="2016-04-04", tutori=["bianca"])       # 10 anni: documenti no


class Persone:
    def __init__(self):
        self.users = {p.name: p for p in (DARIO, BIANCA, TEO, LIA)}

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)


def doc_word(titolo, testo):
    return {"titolo": titolo, "blocchi": [{"tipo": "titolo", "testo": titolo}, {"tipo": "paragrafo", "testo": testo}]}


def documenti_calliope() -> Archive:
    a = Archive(str(TMP / "documenti.db"))
    a.add("dario", "Dario Rossi", "word", "Lettera al condominio", "x", "Lettera al condominio.docx",
          doc_word("Lettera al condominio", "Chiedo la riunione."), None, "lettera")
    a.add("bianca", "Bianca", "word", "Relazione sulla città", "x", "Relazione sulla città.docx",
          doc_word("Relazione sulla città", "La città è grande."), None, "relazione")
    a.add("teo", "Teo", "word", "Ricerca sui vulcani", "x", "Ricerca sui vulcani.docx",
          doc_word("Ricerca sui vulcani", "I vulcani eruttano."), None, "ricerca")
    a.add("lia", "Lia", "word", "Disegno del gatto", "x", "Disegno del gatto.docx",
          doc_word("Disegno del gatto", "Un gatto."), None, "disegno")
    return a


# I file dell'archivio di casa: percorso, tipo, scheda estratta
FILE = [
    ("bolletta luce.pdf", "bolletta", {"categoria": "luce", "data_documento": "2026-09-10", "importo_totale": 84.5,
                                        "emittente": {"nome": "Lumen Energia"}}),
    ("Bianca/referto città.pdf", "referto", {"data_documento": "2026-05-02", "esame": "emocromo"}),
    ("Dario Rossi/contratto affitto.pdf", "contratto", {"categoria": "affitto", "data_documento": "2025-01-01"}),
    ("Teo/pagella.jpg", "altro", {"data_documento": "2026-06-10"}),
    # Il testo estratto è un dato non fidato: l'oggetto entra nel nome del documento
    ("scontrino ostile.pdf", "ricevuta", {"data_documento": "2026-03-03", "oggetto": OSTILE,
                                           "emittente": {"nome": "Negozio Fittizio"}}),
]


def archivio_casa() -> Archivio:
    cart = TMP / "archivio"
    cfg = Config()
    grafo = Grafo(str(TMP / "grafo.db"))
    arch = Archivio(cfg, grafo, cart, log=lambda *a: None, profili=lambda: [p.name for p in (DARIO, BIANCA, TEO, LIA)])
    for rel, tipo, s in FILE:
        p = cart / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        dati = f"%PDF-1.4 finto: {rel}".encode("utf-8")
        p.write_bytes(dati)
        sha = hashlib.sha256(dati).hexdigest()
        doc = arch.registra(rel, sha, lettura.Estratto(f"{tipo} {rel} {s.get('prodotto', '')}", "testo"),
                            {"tipo": tipo, "scheda": s})
        arch._segna(rel, sha, p.stat(), "ok", nodo=doc)
    return arch


def prepara(cartella: Path, tool_ctx):
    """Per le prove nel browser (prova_telefono_schermo, prova_pc_pagina): i documenti fatti da
    Calliope e l'archivio di casa in `cartella`, dati al contesto dei tool dello schermo."""
    global TMP
    TMP = Path(cartella)
    TMP.mkdir(parents=True, exist_ok=True)
    doc, arch = documenti_calliope(), archivio_casa()
    tool_ctx.documenti = types.SimpleNamespace(archive=doc)
    tool_ctx.archivio = arch
    return doc, arch


def hub_di(doc, arch):
    return types.SimpleNamespace(servizi=types.SimpleNamespace(documenti=types.SimpleNamespace(archive=doc), archivio=arch),
                                 tool_ctx=types.SimpleNamespace(speakers=Persone()))


def titoli(p, tipo="documento"):
    return [c.get("titolo") for c in p.get("schede") or [] if c.get("tipo") == tipo]


def righe(p):
    return {v["nome"]: v for c in p.get("schede") or [] if c.get("tipo") == "archivio" for v in c.get("voci") or []}


# ─────────────────────────── 1–2. la pagina ───────────────────────────
def pagina(hub):
    p = raccolte.pagina(hub, DARIO, "documenti")
    sc = p.get("schede") or []
    per = {c.get("titolo"): c for c in sc if c.get("tipo") == "documento"}
    verifica("calliope: chi amministra vede i suoi e quelli di Bianca, di Teo e di Lia (decisione del 28/10)",
             set(per) == {"Lettera al condominio", "Relazione sulla città", "Ricerca sui vulcani", "Disegno del gatto"},
             js(list(per)))
    verifica("calliope: i suoi per primi, senza «di»; gli altri col nome e il gruppo",
             titoli(p)[0] == "Lettera al condominio" and not per["Lettera al condominio"].get("di")
             and per["Lettera al condominio"].get("gruppo") == "Fatti da Calliope per te"
             and per["Relazione sulla città"].get("di") == "Bianca"
             and per["Relazione sulla città"].get("gruppo") == "Fatti da Calliope per Bianca"
             and per["Disegno del gatto"].get("di") == "Lia", js(per["Relazione sulla città"], ensure_ascii=False)[:200])
    verifica("calliope: ognuno con «Scarica» e la sorgente sul server",
             all(c.get("scarica") and "_scarica" in c for c in per.values()))
    r = righe(p)
    verifica("archivio: chi amministra vede tutto, anche i personali degli altri",
             len(r) == len(FILE), js(list(r), ensure_ascii=False))
    di = {k: v["di"] for k, v in r.items()}
    verifica("archivio: ogni riga dice di chi è (la cartella della persona, o la casa)",
             sorted(di.values()) == sorted(["Di casa", "Di Bianca", "Di Dario Rossi", "Di Teo", "Di casa"]),
             js(di, ensure_ascii=False))
    gruppi = [c.get("titolo") for c in p["schede"] if c.get("tipo") == "archivio"]
    verifica("archivio: una scheda per tipo nell'ordine dei tipi, nel gruppo «Archivio di casa»",
             gruppi == ["Bollette", "Ricevute e fatture", "Contratti", "Referti", "Altri documenti"]
             and all(c.get("gruppo") == "Archivio di casa" for c in p["schede"] if c.get("tipo") == "archivio")
             and all(c.get("sezione") == "cose/documenti" for c in p["schede"]), js(gruppi))
    verifica("archivio: «Scarica» per riga, con la chiave della riga e l'estensione, la sorgente in _scarica_voci",
             all(v["chiave"].startswith("archivio:file:") and v["estensione"] in ("pdf", "jpg") for v in r.values())
             and sum(len(c.get("_scarica_voci") or []) for c in p["schede"]) == len(FILE))
    verifica("archivio: il testo estratto arriva com'è, come dato (la pagina lo scrive con textContent)",
             any(OSTILE in k for k in r), js(list(r)))

    p = raccolte.pagina(hub, BIANCA, "documenti")
    verifica("calliope: un familiare vede solo i suoi, non quelli di Dario né dei figli",
             titoli(p) == ["Relazione sulla città"], js(titoli(p)))
    r = righe(p)
    nomi = " ".join(r).lower()
    verifica("archivio: un familiare vede quelli di casa e il suo referto, non il contratto di Dario né la pagella di Teo",
             len(r) == 3 and "referto" in nomi and "contratto" not in nomi and not any(v["di"] == "Di Teo" for v in r.values()),
             js(list(r), ensure_ascii=False))
    verifica("un familiare: niente gruppi degli altri", not any("per Dario" in str(c.get("gruppo")) for c in p["schede"]))

    p = raccolte.pagina(hub, TEO, "documenti")
    verifica("un minore (15 anni) vede solo i suoi documenti, e niente archivio di casa (come a voce)",
             titoli(p) == ["Ricerca sui vulcani"] and not righe(p) and "archivio" in p.get("nota", "").lower(),
             js(p, ensure_ascii=False)[:300])
    p = raccolte.pagina(hub, LIA, "documenti")
    verifica("un minore col preset «documenti: no» non li vede (come documento_leggi)",
             titoli(p) == [] and not righe(p) and "adulto" in p.get("nota", ""), js(p, ensure_ascii=False)[:300])

    t = {x["id"]: x for x in raccolte.tessere(hub, BIANCA)}
    verifica("tessera: Documenti col servizio vero, il conto e la pagina", t["documenti"]["conto"] == 1
             and t["documenti"]["pagina"] is True and isinstance(t["documenti"]["ultimo"], float), js(t["documenti"]))


# ─────────────────────────── 3. la ricerca ───────────────────────────
def ricerca(hub):
    q = raccolte.cerca(hub, BIANCA, "documenti", "bolletta luce")
    verifica("cerca: Bianca trova la bolletta di casa", "bolletta" in " ".join(righe(q)).lower()
             and all(c.get("sezione") == "cose/documenti" for c in q.get("schede") or []), js(q, ensure_ascii=False)[:300])
    q = raccolte.cerca(hub, BIANCA, "documenti", "contratto affitto")
    verifica("cerca: Bianca non trova il contratto personale di Dario", not righe(q), js(q, ensure_ascii=False)[:300])
    q = raccolte.cerca(hub, DARIO, "documenti", "contratto affitto")
    verifica("cerca: chi amministra lo trova", "contratto" in " ".join(righe(q)).lower(), js(q, ensure_ascii=False)[:300])
    q = raccolte.cerca(hub, BIANCA, "documenti", "lettera condominio")
    verifica("cerca: Bianca non trova la lettera fatta da Calliope per Dario", titoli(q) == [], js(titoli(q)))
    q = raccolte.cerca(hub, DARIO, "documenti", "relazione città")
    verifica("cerca: chi amministra trova quella di Bianca, col nome", titoli(q) == ["Relazione sulla città"]
             and q["schede"][0].get("di") == "Bianca", js(titoli(q)))
    q = raccolte.cerca(hub, TEO, "documenti", "bolletta vulcani")
    verifica("cerca: un minore trova i suoi, mai l'archivio di casa", titoli(q) == ["Ricerca sui vulcani"] and not righe(q))
    for testo in (OSTILE, '"bolletta" OR *', "NEAR(a b) ' ; DROP TABLE nodi; --", "\u0000‮", "x" * 5000):
        q = raccolte.cerca(hub, BIANCA, "documenti", testo)
        verifica(f"cerca: testo ostile {testo[:20]!r}… una risposta, mai un errore", "_stato" not in q
                 and isinstance(q.get("nota"), str), js(q, ensure_ascii=False)[:200])
    q = raccolte.cerca(hub, BIANCA, "documenti", "   ")
    verifica("cerca: vuoto, la pagina lo dice", q.get("schede") == [] and "cercare" in q.get("nota", ""))
    verifica("cerca: solo nella pagina Documenti", raccolte.cerca(hub, BIANCA, "liste", "latte").get("_stato") == 404
             and raccolte.cerca(hub, BIANCA, "ufficio", "x").get("_stato") == 404)


# ─────────────────────────── 4. servizi ───────────────────────────
def servizi(doc, arch):
    vuoto = types.SimpleNamespace(servizi=None, tool_ctx=None)
    p = raccolte.pagina(vuoto, BIANCA, "documenti")
    verifica("servizio che manca: la pagina dice una nota, nessun errore", p.get("schede") == []
             and "non ci sono" in p.get("nota", "") and "_stato" not in p, js(p))

    class Rotto:
        def recenti(self, *a, **k):
            raise RuntimeError("database chiuso")
    log = []
    p = raccolte.pagina(types.SimpleNamespace(servizi=types.SimpleNamespace(documenti=Rotto()), tool_ctx=None),
                        BIANCA, "documenti", log=log.append)
    verifica("servizio che solleva: 503 e il registro, mai un'eccezione", p.get("_stato") == 503 and any("documenti" in m for m in log))
    q = raccolte.cerca(types.SimpleNamespace(servizi=types.SimpleNamespace(documenti=Rotto()), tool_ctx=None),
                       BIANCA, "documenti", "bolletta", log.append)
    verifica("ricerca col servizio che solleva: 503, senza il testo cercato nel registro",
             q.get("_stato") == 503 and not any("bolletta" in m for m in log), str(log))
    solo_arch = types.SimpleNamespace(servizi=types.SimpleNamespace(archivio=arch), tool_ctx=types.SimpleNamespace(speakers=Persone()))
    p = raccolte.pagina(solo_arch, BIANCA, "documenti")
    verifica("senza i documenti di Calliope: l'archivio di casa c'è lo stesso", len(righe(p)) == 3 and "non ci sono" in p.get("nota", ""))


# ─────────────────────────── 5. «Scarica» ───────────────────────────
def scaricamenti(hub, arch):
    cfg = Config()
    sc = scarica.Scaricamenti(cfg)
    from calliope.schermi.hub import registra_scaricabili
    p = raccolte.pagina(hub, BIANCA, "documenti")
    for c in p["schede"]:
        registra_scaricabili(sc, 7, c, "bianca")
    r = righe(p)
    referto = next(v for k, v in r.items() if "referto" in k.lower())
    schermo = {"id": 7, "proprietario": "bianca"}
    g = sc.gettone(schermo, referto["chiave"], "originale")
    nome, tipo, dati = sc.prendi(g["url"].rsplit("/", 1)[1])
    verifica("scarica: il referto originale, tipo PDF, nome con l'accento", tipo == "application/pdf"
             and dati.startswith(b"%PDF") and nome == "referto città.pdf", f"{nome} {tipo}")
    disp = scarica.disposizione(nome)
    verifica("scarica: Content-Disposition con filename* in UTF-8 e il nome di riserva senza accenti",
             'filename="referto citta.pdf"' in disp and "filename*=UTF-8''referto%20citt%C3%A0.pdf" in disp, disp)
    try:
        sc.gettone(schermo, referto["chiave"], "pdf")
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 400
    verifica("scarica: un formato che non è del file dell'archivio 400", ok)
    contratto = next((v for v in righe(raccolte.pagina(hub, DARIO, "documenti")).values() if "Dario" in v["di"]), None)
    try:
        sc.gettone(schermo, contratto["chiave"], "originale")
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 404
    verifica("scarica: una riga di un altro, non arrivata a questo schermo, 404", ok)
    # I permessi rifatti al clic: il file tolto, poi Bianca che diventa «ospite» (non più nel registro)
    bolletta = next(v for k, v in r.items() if "bolletta" in k.lower())
    g = sc.gettone(schermo, bolletta["chiave"], "originale")
    (arch.cartella / "bolletta luce.pdf").rename(arch.cartella / "bolletta luce.tolta")
    try:
        sc.prendi(g["url"].rsplit("/", 1)[1])
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 404
    (arch.cartella / "bolletta luce.tolta").rename(arch.cartella / "bolletta luce.pdf")
    verifica("scarica: il file tolto dalla cartella dopo la pagina, 404", ok)
    reg = hub.tool_ctx.speakers
    g = sc.gettone(schermo, bolletta["chiave"], "originale")
    via = reg.users.pop("Bianca")
    try:
        sc.prendi(g["url"].rsplit("/", 1)[1])
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 404
    try:                                # e dal 2e già alla richiesta del gettone (estensione_fn)
        sc.gettone(schermo, bolletta["chiave"], "originale")
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 404
    reg.users["Bianca"] = via
    verifica("scarica: i permessi si rifanno al clic (la persona tolta dal registro non scarica)", ok)
    verifica("scarica: nomi e tipi dei file originali", scarica.tipo_mime("originale", {"estensione": "jpg"}) == "image/jpeg"
             and scarica.nome_file("Città", "originale", {"estensione": "exe"}) == "Città.bin"
             and scarica.tipo_mime("originale", {"estensione": "exe"}) == "application/octet-stream")
    nfd = "Città"
    verifica("scarica: il nome del file in forma NFC (come lo scrive iOS)", scarica.nome_file(nfd, "md") == "Città.md")


# ─────────────────────────── 6. il server ───────────────────────────
def scarica_vero(port, sessione, chiave, formato):
    st, d = pr.chiedi(port, "/api/scarica", sessione, corpo={"chiave": chiave, "formato": formato})
    if st != 200:
        return st, None, None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{d['url']}", timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""


def server(doc, arch):
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    reg = Persone()
    hub.profilo = reg.by_id
    hub.tool_ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=None, speaker=None,
                               documenti=types.SimpleNamespace(archive=doc), archivio=arch)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        _, t_dario = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario Rossi")
        _, t_bianca = hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
        _, t_ugo = hub.archivio.crea_con_token("telefono", proprietario="ugo", proprietario_nome="Ugo")
        hub._rinfresca()
        port = srv.port
        sess_d = pr.chiedi(port, "/api/accedi", token=t_dario)[1].get("sessione")
        sess_b = pr.chiedi(port, "/api/accedi", token=t_bianca)[1].get("sessione")
        sess_u = pr.chiedi(port, "/api/accedi", token=t_ugo)[1].get("sessione")
        st, d = pr.chiedi(port, "/api/raccolte", sess_d, corpo={"raccolta": "documenti"})
        sc = d.get("schede") or []
        verifica("server: la pagina Documenti di chi amministra", st == 200 and len(sc) == 4 + 5, f"{st} {len(sc)}")
        verifica("server: nessuna chiave privata alla pagina (né _scarica né _scarica_voci)",
                 not any(str(k).startswith("_") for c in sc for k in c))
        di_bianca = next(c for c in sc if c.get("titolo") == "Relazione sulla città")
        st, h, dati = scarica_vero(port, sess_d, di_bianca["chiave"], "md")
        verifica("server: chi amministra scarica il documento fatto per Bianca, nome con l'accento",
                 st == 200 and "Relazione sulla citt" in dati.decode("utf-8") and "citt%C3%A0" in h.get("content-disposition", ""),
                 f"{st} {h.get('content-disposition') if h else ''}")
        st, d = pr.chiedi(port, "/api/raccolte", sess_b, corpo={"raccolta": "documenti"})
        r = righe(d)
        referto = next(v for k, v in r.items() if "referto" in k.lower())
        st, h, dati = scarica_vero(port, sess_b, referto["chiave"], "originale")
        verifica("server: Bianca scarica il suo referto originale (PDF, attachment, sandbox)",
                 st == 200 and dati.startswith(b"%PDF") and h.get("content-type") == "application/pdf"
                 and h.get("content-disposition", "").startswith("attachment;") and "sandbox" in h.get("content-security-policy", ""),
                 f"{st} {h}")
        st, _, _ = scarica_vero(port, sess_b, di_bianca["chiave"], "md")
        st2, _, _ = scarica_vero(port, sess_b, next(c for c in sc if c.get("titolo") == "Lettera al condominio")["chiave"], "md")
        verifica("server: Bianca scarica il suo documento, non quello di Dario (mai registrato per lei)", st == 200 and st2 == 404,
                 f"{st} {st2}")
        st, d = pr.chiedi(port, "/api/raccolte/cerca", sess_b, corpo={"raccolta": "documenti", "testo": "contratto affitto"})
        verifica("server: la ricerca di Bianca non trova il contratto di Dario", st == 200 and not righe(d), f"{st} {d}")
        st, d = pr.chiedi(port, "/api/raccolte/cerca", sess_b, corpo={"raccolta": "documenti", "testo": OSTILE})
        verifica("server: la ricerca con testo ostile risponde 200", st == 200 and isinstance(d.get("nota"), str), f"{st} {d}")
        st, d = pr.chiedi(port, "/api/raccolte/cerca", sess_b, corpo={"raccolta": "documenti", "testo": 3})
        verifica("server: la ricerca con dati sbagliati 400", st == 400, f"{st} {d}")
        st, d = pr.chiedi(port, "/api/raccolte/cerca", sess_u, corpo={"raccolta": "documenti", "testo": "bolletta"})
        verifica("server: un ospite (lo schermo senza profilo) 403", st == 403, f"{st} {d}")
        st, d = pr.chiedi(port, "/api/raccolte/cerca", None, corpo={"raccolta": "documenti", "testo": "bolletta"})
        verifica("server: senza sessione 401", st == 401, f"{st}")
        stati = [pr.chiedi(port, "/api/raccolte/cerca", sess_d, corpo={"raccolta": "documenti", "testo": "bolletta"})[0]
                 for _ in range(21)]
        verifica("server: la ricerca al più 20 al minuto per schermo (la 21ª 429)",
                 stati[:20] == [200] * 20 and stati[20] == 429, str(stati))
    finally:
        srv.ferma()


# ─────────────────────────── 7. l'annuncio ───────────────────────────
def annuncio():
    from calliope.documenti.consegna import LocalDelivery
    from calliope.documenti.formato import validate
    from calliope.documenti.servizio import Documenti

    class Scrittore:                    # lo scrittore finto: una lettera, niente modello
        last_stats: dict = {}

        def write(self, formato, richiesta, detto="", persona=None, titolo=""):
            time.sleep(0.3)             # il tempo di mettere ha_pagina e lasciarlo in secondo piano
            return validate("word", doc_word("Lettera alla scuola", "Gentile maestra."))

    class SulServer(LocalDelivery):     # come consegna.RemoteDelivery._sul_server
        def deliver(self, *a, **k):
            d = super().deliver(*a, **k)
            d["dove"], d["remoto"] = "tra i miei documenti, perché il portatile non è collegato", False
            return d
    cfg = Config()
    cfg.documenti_attesa_s = 0.0
    svc = Documenti(cfg, str(TMP / "annuncio.db"), writer=Scrittore(), delivery=SulServer(TMP / "server"))
    job = svc.crea("dario", "Dario", "word", "lettera")
    job.ha_pagina = lambda: True
    svc.wait(job, 0.0)                  # in secondo piano, come il tool dopo documenti_attesa_s
    job.event.wait(20)
    m = svc.done.get(timeout=20)["messaggio"]
    verifica("annuncio: finito in secondo piano con lo schermo abbinato ma chiuso, «in Le mie cose, alla voce Documenti»",
             "Le mie cose, alla voce Documenti" in m and "sul server" not in m and "telefono" not in m, m)
    job = svc.crea("dario", "Dario", "word", "lettera")
    job.ha_pagina = lambda: False
    svc.wait(job, 0.0)                  # in secondo piano, come il tool dopo documenti_attesa_s
    job.event.wait(20)
    m = svc.done.get(timeout=20)["messaggio"]
    verifica("annuncio: contrario, senza schermi abbinati la frase di sempre (senza «server», #290)",
             "tra i miei documenti" in m and "server" not in m, m)
    svc.close()


# ─────────────────────────── 8. dalla revisione della PR #268 ───────────────────────────
def molti_documenti():
    """La pagina mostra gli ultimi DOCUMENTI_PAGINA e lo dice; la ricerca li trova tutti, anche oltre
    i 50 che guardava prima («lo trovi in Le mie cose» deve essere vero)."""
    a = Archive(str(TMP / "molti.db"))
    a.add("bianca", "Bianca", "word", "Verbale della gita al lago", "x", "Verbale della gita al lago.docx",
          doc_word("Verbale della gita al lago", "Il lago."), None, "")
    for i in range(60):
        a.add("bianca", "Bianca", "word", f"Appunto numero {i}", "x", f"Appunto {i}.docx",
              doc_word(f"Appunto numero {i}", "x"), None, "")
    hub = types.SimpleNamespace(servizi=types.SimpleNamespace(documenti=types.SimpleNamespace(archive=a)),
                                tool_ctx=types.SimpleNamespace(speakers=Persone()))
    p = raccolte.pagina(hub, BIANCA, "documenti")
    verifica("molti documenti: la pagina ne mostra gli ultimi 8 e dice che gli altri si trovano con «Cerca»",
             len(titoli(p)) == raccolte.DOCUMENTI_PAGINA and "«Cerca»" in p.get("nota", ""), js(p.get("nota")))
    q = raccolte.cerca(hub, BIANCA, "documenti", "verbale gita")
    verifica("molti documenti: la ricerca trova il più vecchio, oltre i 50 più recenti",
             titoli(q) == ["Verbale della gita al lago"], js(titoli(q)))
    t = {x["id"]: x for x in raccolte.tessere(hub, BIANCA)}
    verifica("molti documenti: la tessera conta tutti i suoi (non al più 50)", t["documenti"]["conto"] == 61,
             js(t["documenti"]))


def parole_vuote(hub):
    for testo in ("di", "è a", "il la le", "x"):
        q = raccolte.cerca(hub, DARIO, "documenti", testo)
        verifica(f"cerca: solo parole vuote ({testo!r}) → niente da cercare, non i più recenti",
                 q.get("schede") == [] and "niente da cercare" in q.get("nota", ""), js(q)[:200])
    # Una cifra sola (revisione della PR #269): l'archivio non la usa, e senza filtro dava i 20 più
    # recenti come «trovati»; i documenti fatti da Calliope la confrontano (nessuno ha un «3» qui)
    for testo in ("3", "di 3", "7 e"):
        q = raccolte.cerca(hub, DARIO, "documenti", testo)
        verifica(f"cerca: una cifra sola ({testo!r}) → niente dall'archivio, non i più recenti",
                 not righe(q) and q.get("schede") == [] and "Trovat" not in q.get("nota", ""), js(q)[:200])


def tessera_admin(hub):
    t = {x["id"]: x for x in raccolte.tessere(hub, DARIO)}
    verifica("tessera: per chi amministra il conto è dei suoi e lo stato dice «tuoi» e quanti degli altri",
             t["documenti"]["conto"] == 1 and "1 documento tuo" in t["documenti"]["stato"]
             and "3 degli altri" in t["documenti"]["stato"], js(t["documenti"]))


def voci_per_schermo():
    """Le voci di «Scarica» per schermo: la pagina riletta su uno schermo non toglie le voci
    dell'altro (prima un tetto unico di 400 per tutti)."""
    sc = scarica.Scaricamenti(Config())
    sc.registra(7, {"chiave": "documento:1", "_scarica": {"documento": {}, "formato": "word"}, "scarica": ["md"]}, "dario")
    for i in range(scarica.MAX_VOCI + 50):
        sc.registra(8, {"chiave": f"archivio:file:{i}", "_scarica": {"file_fn": lambda: None}, "scarica": ["originale"]}, "dario")
    verifica("scarica: le voci di uno schermo restano anche se un altro ne registra più del tetto",
             sc.voce(7, "documento:1") is not None and sc.voce(8, "archivio:file:0") is None
             and sc.voce(8, f"archivio:file:{scarica.MAX_VOCI + 49}") is not None)


def originale_riletto():
    """Il file originale: riletto a ogni uso (il gettone non tiene i byte), nome e tipo dal file letto
    davvero (una copia .jpg di un documento il cui attributo dice .pdf)."""
    sc = scarica.Scaricamenti(Config())
    letture = []

    def leggi():
        letture.append(1)
        return b"\xff\xd8 foto", "jpg"
    sc.registra(7, {"chiave": "archivio:file:1", "scarica": ["originale"],
                    "_scarica": {"file_fn": leggi, "titolo": "ricevuta città", "estensione": "pdf"}}, "bianca")
    g = sc.gettone({"id": 7, "proprietario": "bianca"}, "archivio:file:1", "originale")
    tok = g["url"].rsplit("/", 1)[1]
    nome, tipo, dati = sc.prendi(tok)
    sc.prendi(tok)
    verifica("scarica: l'originale col nome e il tipo del file letto davvero, riletto a ogni uso e non tenuto nel gettone",
             nome == "ricevuta città.jpg" and tipo == "image/jpeg" and dati.startswith(b"\xff\xd8")
             and len(letture) == 2 and sc._gettoni[tok]["dati"] is None, f"{nome} {tipo} {len(letture)}")


def file_di_fuori():
    """`Archivio.file_di` non esce mai dalla cartella dell'archivio e non supera archivio_max_mb."""
    import subprocess
    cart = TMP / "archivio-file-di"
    fuori = TMP / "fuori-file-di"
    cart.mkdir(parents=True, exist_ok=True)
    fuori.mkdir(parents=True, exist_ok=True)
    (fuori / "segreto.pdf").write_bytes(b"%PDF segreto")
    (cart / "buono.pdf").write_bytes(b"%PDF buono")
    grafo = Grafo(str(TMP / "grafo-file-di.db"))
    arch = Archivio(Config(), grafo, cart, log=lambda *a: None, profili=lambda: [])
    dati = b"%PDF buono"
    doc = arch.registra("buono.pdf", hashlib.sha256(dati).hexdigest(), lettura.Estratto("bolletta", "testo"),
                        {"tipo": "bolletta", "scheda": {"categoria": "luce"}})
    arch._segna("buono.pdf", "x", (cart / "buono.pdf").stat(), "ok", nodo=doc)
    verifica("file_di: il file dentro la cartella sì", arch.file_di(doc) == (cart / "buono.pdf").resolve())

    def con_percorso(per):
        with grafo.transazione() as db:
            db.execute("UPDATE file SET percorso = ? WHERE nodo = ?", (per, doc))
        return arch.file_di(doc)
    giunzione = cart / "giunzione"
    fatta = False
    if os.name == "nt":
        try:
            fatta = subprocess.run(["cmd", "/c", "mklink", "/J", str(giunzione), str(fuori)],
                                   capture_output=True, timeout=20).returncode == 0
        except (OSError, subprocess.SubprocessError):
            fatta = False
    casi = [("../fuori-file-di/segreto.pdf", "con «..»"), ("..\\fuori-file-di\\segreto.pdf", "con «..\\»"),
            (str(fuori / "segreto.pdf"), "percorso assoluto")]
    if fatta:
        casi.append(("giunzione/segreto.pdf", "giunzione NTFS verso fuori"))
    for per, come in casi:
        verifica(f"file_di: mai fuori dalla cartella ({come})", con_percorso(per) is None)
    if not fatta:
        print("SALTATA IN PARTE: giunzione NTFS non creata qui (file_di fuori dalla cartella con una giunzione)")
    con_percorso("buono.pdf")
    arch.max_byte = 4
    verifica("file_di: mai oltre archivio_max_mb", arch.file_di(doc) is None)
    arch.max_byte = 50 * 1024 * 1024
    verifica("file_di: e di nuovo sì col tetto normale", arch.file_di(doc) is not None)
    if fatta:
        try:
            os.rmdir(giunzione)                 # toglie la giunzione, non la cartella a cui punta
        except OSError:
            pass


# ─────────────────────────── 9. dalla seconda revisione della PR #268 ───────────────────────────
def ricerca_corta_e_pertinenza():
    a = Archive(str(TMP / "corte.db"))
    a.add("bianca", "Bianca", "word", "CV", "x", "CV.docx", doc_word("CV", "Esperienze."), None, "")
    a.add("bianca", "Bianca", "word", "Tre re", "x", "Tre re.docx", doc_word("Tre re", "Una fiaba."), None, "")
    a.add("bianca", "Bianca", "word", "Verbale 3", "x", "Verbale 3.docx", doc_word("Verbale 3", "Terzo."), None, "")
    a.add("bianca", "Bianca", "word", "Lettera al comune di Lodi", "x", "Lettera al comune di Lodi.docx",
          doc_word("Lettera al comune di Lodi", "Gentile sindaco."), None, "")
    for i in range(30):                 # più recenti, con una parola in comune
        a.add("bianca", "Bianca", "word", f"Lettera numero {i}", "x", f"Lettera {i}.docx",
              doc_word(f"Lettera numero {i}", "x"), None, "")
    hub = types.SimpleNamespace(servizi=types.SimpleNamespace(documenti=types.SimpleNamespace(archive=a)),
                                tool_ctx=types.SimpleNamespace(speakers=Persone()))
    q = raccolte.cerca(hub, BIANCA, "documenti", "CV")
    verifica("cerca corta: «CV» trova il CV (prima solo parole di 4 lettere)", titoli(q) == ["CV"], js(titoli(q)))
    q = raccolte.cerca(hub, BIANCA, "documenti", "tre re")
    verifica("cerca corta: «tre re» trova «Tre re»", titoli(q)[:1] == ["Tre re"], js(titoli(q)))
    q = raccolte.cerca(hub, BIANCA, "documenti", "lettera comune")
    verifica("cerca: per pertinenza, la lettera al comune prima delle 30 più recenti (e dentro i primi 20)",
             titoli(q)[:1] == ["Lettera al comune di Lodi"] and len(titoli(q)) == raccolte.CERCA_RISULTATI, js(titoli(q)[:3]))
    q = raccolte.cerca(hub, BIANCA, "documenti", "lett")
    verifica("cerca: l'inizio di una parola trova lo stesso (mezzo punto)", len(titoli(q)) == raccolte.CERCA_RISULTATI)
    q = raccolte.cerca(hub, BIANCA, "documenti", "3")
    verifica("cerca: la cifra sola trova i titoli che la hanno, uguale e non dentro un numero", set(titoli(q)) == {"Verbale 3", "Lettera numero 3"}, js(titoli(q)))
    q = raccolte.cerca(hub, BIANCA, "documenti", "di il")
    verifica("cerca corta: contrario, le parole vuote restano fuori", q.get("schede") == [] and "niente da cercare" in q.get("nota", ""))
    q = raccolte.cerca(hub, TEO, "documenti", "CV")
    verifica("cerca corta: contrario, un'altra persona non trova il CV di Bianca", titoli(q) == [], js(titoli(q)))
    q = raccolte.cerca(hub, DARIO, "documenti", "CV")
    verifica("cerca corta: chi amministra trova il CV di Bianca, col nome",
             titoli(q) == ["CV"] and q["schede"][0].get("di") == "Bianca", js(titoli(q)))


def nome_scaricato_uguale():
    sc = scarica.Scaricamenti(Config())
    sc.registra(7, {"chiave": "archivio:file:9", "scarica": ["originale"],
                    "_scarica": {"file_fn": lambda: (b"JFIF foto", "jpg"), "estensione_fn": lambda: "jpg",
                                 "titolo": "garanzia frigo", "estensione": "pdf"}}, "bianca")
    g = sc.gettone({"id": 7, "proprietario": "bianca"}, "archivio:file:9", "originale")
    nome, tipo, _ = sc.prendi(g["url"].rsplit("/", 1)[1])
    verifica("scarica: il nome di «Scaricato: …» è quello del file salvato (la copia vera è .jpg)",
             g["nome"] == nome == "garanzia frigo.jpg" and tipo == "image/jpeg", f"{g['nome']} {nome}")
    sc.registra(7, {"chiave": "archivio:file:10", "scarica": ["originale"],
                    "_scarica": {"file_fn": lambda: None, "estensione_fn": lambda: None, "titolo": "via"}}, "bianca")
    try:
        sc.gettone({"id": 7, "proprietario": "bianca"}, "archivio:file:10", "originale")
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 404
    verifica("scarica: il file non c'è più già alla richiesta del gettone: 404 subito", ok)


def revocati(doc, arch):
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria-revoca.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
    hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario Rossi")
    hub._rinfresca()
    ids = [s["id"] for s in hub.abbinati()]
    a, b = ids[0], ids[1]
    for sid, persona in ((a, "bianca"), (b, "dario")):
        for i in range(5):
            hub.scaricamenti.registra(sid, {"chiave": f"documento:{i}", "_scarica": {"documento": {}, "formato": "word"},
                                            "scarica": ["md"]}, persona)
    hub.scaricamenti.gettone({"id": a, "proprietario": "bianca"}, "documento:1", "md")
    hub.revoca(a)
    verifica("revoca: le voci di «Scarica» e i gettoni dello schermo revocato se ne vanno, quelle dell'altro restano",
             hub.scaricamenti.voce(a, "documento:1") is None and hub.scaricamenti.voce(b, "documento:1") is not None
             and not any(g["sid"] == a for g in hub.scaricamenti._gettoni.values()))
    # Da terminale: un altro processo toglie lo schermo dal file; la cache si rilegge
    altro = ArchivioSchermi(cfg.memory_db)
    altro.revoca(b)
    hub._rinfresca()
    hub.abbinati()
    verifica("revoca da terminale: alla rilettura degli abbinati anche quelle voci se ne vanno",
             hub.scaricamenti.voce(b, "documento:1") is None and not hub.scaricamenti._voci)


def main():
    try:
        doc = documenti_calliope()
        arch = archivio_casa()
        hub = hub_di(doc, arch)
        print("— 1–2. la pagina")
        pagina(hub)
        print("— 3. la ricerca")
        ricerca(hub)
        print("— 4. servizi")
        servizi(doc, arch)
        print("— 5. «Scarica»")
        scaricamenti(hub, arch)
        print("— 6. il server")
        server(doc, arch)
        print("— 7. l'annuncio")
        annuncio()
        print("— 8. dalla revisione della PR #268")
        molti_documenti()
        parole_vuote(hub)
        tessera_admin(hub)
        voci_per_schermo()
        originale_riletto()
        file_di_fuori()
        print("— 9. dalla seconda revisione della PR #268")
        ricerca_corta_e_pertinenza()
        nome_scaricato_uguale()
        revocati(doc, arch)
        arch.grafo.close() if hasattr(arch.grafo, "close") else None
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(ERRORI)} errori" if ERRORI else "\ntutto ok")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
