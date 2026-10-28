"""Prova a secco della pagina Ufficio di «Le mie cose» (28/10/2026, passo 2e di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md § 4.9, issue #260 di #241; area
docs/aree/schermi-telefono.md).

1. **La pagina** (`raccolte.pagina(…, "ufficio")`) con `Numeratore` e `Rubrica` veri: una scheda
   `ufficio` per serie (fatture, note di credito, preventivi, DDT, poi le serie dei modelli), i più
   recenti per primi, al più 20 per serie con la nota; per riga numero, data, cliente, importo
   (`_totale` salvato all'emissione; niente per i DDT e per i numeri di prima), stato (emessa,
   annullata col motivo, in preparazione) e «Scarica» dei file generati (PDF e XML); la rubrica
   (`Rubrica.visibili`: di casa e sua, non i personali degli altri).
2. **Permessi**: solo chi amministra; un familiare, un minore (anche col segno di chi amministra) e
   un ospite 404, sulla pagina, sulla ricerca e su «Scarica».
3. **La ricerca** (`raccolte.cerca(…, "ufficio")`): per numero, cliente, comune, partita IVA; parole
   corte e pertinenza come nei Documenti; parole vuote; testo ostile.
4. **Servizi che mancano o sollevano**: senza ufficio una nota; un registro che solleva 503 (pagina
   e ricerca), senza il testo cercato nel registro; la tessera «non disponibile».
5. **Testo ostile** nei nomi dei clienti e nel motivo dell'annullo: arriva com'è, come dato (la
   pagina lo scrive con textContent: prova_telefono_schermo e prova_pc_pagina).
6. **«Scarica»** (scarica.py): il PDF e l'XML col tipo e il nome giusti, uguali in «Scaricato: …»;
   i permessi rifatti al clic (chi non amministra più, il file tolto o non più nel registro: 404).
7. **Il server** vero su 127.0.0.1: `/api/raccolte` e `/api/raccolte/cerca` per chi amministra (200),
   per un familiare (404) e per uno schermo senza profilo (403); lo scaricamento vero dell'XML (tipo,
   attachment, sandbox) e mai da uno schermo di un'altra persona.

Nomi, partite IVA e indirizzi di fantasia, niente rete né modelli.

    python prove/prova_pagina_ufficio.py
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope.config import Config  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi, raccolte, scarica  # noqa: E402
from calliope.schermi.hub import registra_scaricabili  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from calliope.ufficio.numerazione import Numeratore  # noqa: E402
from calliope.ufficio.rubrica import Rubrica  # noqa: E402

import prova_raccolte as pr  # noqa: E402  (chiedi: le richieste al server)

TMP = Path(tempfile.mkdtemp(prefix="calliope-pagina-ufficio-"))
ERRORI = []
OSTILE = '<img src=x onerror="alert(1)">'
ANNO = datetime.date.today().year


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
TEO = Profilo("teo", "Teo", nascita="2011-05-05", tutori=["bianca"])
XENO = Profilo("xeno", "Xeno", admin=True, nascita="2014-01-01")        # minore col segno di chi amministra
OSPITE = Profilo("ospite", "Ospite")                                     # non nel registro


class Persone:
    def __init__(self):
        self.users = {p.name: p for p in (DARIO, BIANCA, TEO, XENO)}

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)


# Contatti di fantasia (le partite IVA hanno la cifra di controllo giusta, ma non sono di nessuno)
ROSSI = {"tipo": "cliente", "denominazione": "Fittizia Rossi Srl", "partita_iva": "12345678903",
         "indirizzo": "Via Verdi", "civico": "5", "cap": "00184", "comune": "Roma", "provincia": "RM",
         "pec": "fittizia@pec.example"}
OSTILE_CLIENTE = {"tipo": "cliente", "denominazione": OSTILE, "codice_fiscale": "RSSMRA80A01H501U",
                  "cap": "10121", "comune": "Torino", "provincia": "TO"}
PRIVATO = {"tipo": "cliente", "nome": "Ada", "cognome": "Lodi", "cap": "26900", "comune": "Lodi", "provincia": "LO"}
CV = {"tipo": "fornitore", "denominazione": "CV Servizi", "comune": "Bra", "provincia": "CN"}


def contatto(rub, dati, ambito, autore="dario"):
    cid = rub.aggiungi(dati, ambito, autore)
    return rub.get(cid, ambito if ambito != "casa" else autore)


def ufficio_finto(cartella: Path):
    """Numeratore e Rubrica veri su un file solo, con fatture, una nota di credito, un preventivo,
    un DDT, una serie di un modello, e i file scritti davvero."""
    cartella.mkdir(parents=True, exist_ok=True)
    db = str(cartella / "ufficio.db")
    numeri, rub = Numeratore(db), Rubrica(db)
    rossi = contatto(rub, ROSSI, "casa")
    ostile = contatto(rub, OSTILE_CLIENTE, "casa")
    privato = contatto(rub, PRIVATO, "dario")              # personale di Dario
    contatto(rub, CV, "casa")
    contatto(rub, {"tipo": "contatto", "nome": "Nadia", "cognome": "Segreta", "comune": "Asti"}, "bianca", "bianca")
    oggi = datetime.date(ANNO, 1, 10)

    def file_di(nome, *estensioni):
        def prepara(n, testo):
            out = []
            for ext in estensioni:
                p = cartella / f"{nome} {n}.{ext}"
                p.write_bytes((b"%PDF-1.4 finto " if ext == "pdf" else b"<?xml version='1.0'?><Fattura/>")
                              + testo.encode("utf-8"))
                out.append(str(p))
            return {"file": out}
        return prepara

    numeri.emetti("fatture", oggi, file_di("Fattura", "pdf", "xml"), "dario", "Dario Rossi", "fattura", "Fattura",
                  {"cliente": rossi, "righe": [], "_totale": "1220.00", "_da_pagare": "1020.00"})
    numeri.emetti("fatture", oggi, file_di("Fattura", "pdf", "xml"), "dario", "Dario Rossi", "fattura", "Fattura",
                  {"cliente": ostile, "_totale": "100.00"})
    numeri.annulla("fatture", ANNO, 2, f"prova sbagliata {OSTILE}")
    # Un numero di prima del 28/10: senza `_totale` (la pagina non inventa l'importo)
    numeri.emetti("fatture", oggi, file_di("Fattura", "pdf"), "dario", "Dario Rossi", "fattura", "Fattura",
                  {"cliente": privato})
    numeri.emetti("note_credito", oggi, file_di("Nota", "pdf", "xml"), "dario", "Dario Rossi", "nota_di_credito",
                  "Nota", {"cliente": rossi, "_totale": "50.00"})
    numeri.emetti("preventivi", oggi, file_di("Preventivo", "pdf"), "dario", "Dario Rossi", "preventivo",
                  "Sito vetrina", {"cliente": privato, "_totale": "1830.00"})
    numeri.emetti("ddt", oggi, file_di("DDT", "pdf"), "dario", "Dario Rossi", "ddt", "DDT", {"cliente": rossi})
    numeri.emetti("verbali", oggi, lambda n, t: {"file": []}, "dario", "Dario Rossi", "verbale_riunione", "Verbale",
                  {"luogo": "sala"})
    return types.SimpleNamespace(numeri=numeri, rubrica=rub)


def prepara(cartella: Path, tool_ctx):
    """Per le prove nel browser (prova_telefono_schermo, prova_pc_pagina): l'ufficio finto in
    `cartella`, dato al contesto dei tool dello schermo."""
    uff = ufficio_finto(Path(cartella))
    tool_ctx.ufficio = uff
    return uff


def hub_di(uff):
    return types.SimpleNamespace(servizi=types.SimpleNamespace(ufficio=uff), tool_ctx=types.SimpleNamespace(speakers=Persone()))


def per_titolo(p):
    return {c.get("titolo"): c for c in p.get("schede") or [] if c.get("tipo") == "ufficio"}


def voci(c):
    return {v["nome"]: v for v in (c or {}).get("voci") or []}


# ─────────────────────────── 1. la pagina ───────────────────────────
def pagina(hub):
    p = raccolte.pagina(hub, DARIO, "ufficio")
    sc = p.get("schede") or []
    titoli = [c.get("titolo") for c in sc]
    verifica("pagina: una scheda per serie nell'ordine, poi la serie del modello e la rubrica",
             titoli == ["Fatture", "Note di credito", "Preventivi", "DDT", "Verbale riunione", "Rubrica"], js(titoli))
    verifica("pagina: tutte di tipo «ufficio», nella sezione cose/ufficio, coi gruppi",
             all(c.get("tipo") == "ufficio" and c.get("sezione") == "cose/ufficio" for c in sc)
             and [c.get("gruppo") for c in sc].count("Documenti dell'ufficio") == 5 and sc[-1].get("gruppo") == "Rubrica")
    f = voci(per_titolo(p)["Fatture"])
    verifica("fatture: dalla più recente", list(f) == [f"Fattura 3/{ANNO}", f"Fattura 2/{ANNO}", f"Fattura 1/{ANNO}"], js(list(f)))
    uno = f[f"Fattura 1/{ANNO}"]
    verifica("fattura: data, cliente, importo e da pagare, «Emessa»",
             uno["dettagli"] == [f"10/01/{ANNO}", "Fittizia Rossi Srl", "1.220,00 €, da pagare 1.020,00 €"]
             and uno["stato"] == "Emessa" and uno["annullato"] is False, js(uno))
    verifica("fattura: «Scarica» del PDF e dell'XML, con le sorgenti sul server",
             [x["estensione"] for x in uno["file"]] == ["pdf", "xml"]
             and all(x["chiave"].startswith("ufficio:file:fatture:") for x in uno["file"])
             and len(per_titolo(p)["Fatture"].get("_scarica_voci") or []) == 5, js(uno["file"]))
    due = f[f"Fattura 2/{ANNO}"]
    verifica("fattura annullata: «Annullata» col motivo, e annullato", due["annullato"] is True
             and due["stato"].startswith("Annullata: prova sbagliata"), js(due))
    verifica("testo ostile: il nome del cliente e il motivo arrivano com'è (dato, scritto come testo)",
             OSTILE in due["dettagli"] and OSTILE in due["stato"], js(due))
    tre = f[f"Fattura 3/{ANNO}"]
    verifica("numero di prima del 28/10: niente importo inventato", tre["dettagli"] == [f"10/01/{ANNO}", "Ada Lodi"], js(tre))
    ddt = voci(per_titolo(p)["DDT"])[f"DDT DDT1/{ANNO}"]
    verifica("DDT: niente importo, «Emesso»", ddt["dettagli"] == [f"10/01/{ANNO}", "Fittizia Rossi Srl"]
             and ddt["stato"] == "Emesso", js(ddt))
    nc = voci(per_titolo(p)["Note di credito"])
    verifica("nota di credito: «Emessa», col suo numero", list(nc) == [f"Nota di credito NC1/{ANNO}"]
             and nc[f"Nota di credito NC1/{ANNO}"]["stato"] == "Emessa", js(nc))
    verb = voci(per_titolo(p)["Verbale riunione"])
    verifica("serie di un modello senza file: la riga senza «Scarica»", all(not v["file"] for v in verb.values()), js(verb))
    rub = voci(per_titolo(p)["Rubrica"])
    verifica("rubrica: quelli di casa e i personali di Dario, per nome, non quelli di Bianca",
             list(rub) == [OSTILE, "Ada Lodi", "CV Servizi", "Fittizia Rossi Srl"], js(list(rub)))
    verifica("rubrica: tipo, partita IVA, luogo, PEC; di casa o solo sua",
             rub["Fittizia Rossi Srl"]["dettagli"] == ["Cliente", "P. IVA 12345678903", "00184 Roma (RM)", "fittizia@pec.example"]
             and rub["Fittizia Rossi Srl"]["stato"] == "Di casa" and rub["Ada Lodi"]["stato"] == "Solo tua",
             js(rub["Fittizia Rossi Srl"]))
    verifica("pagina: la nota dice che l'invio allo SdI è a mano", "SdI" in p.get("nota", "") and "a mano" in p.get("nota", ""))
    t = {x["id"]: x for x in raccolte.tessere(hub, DARIO)}
    verifica("tessera: Ufficio con la pagina, il conto degli emessi dell'anno", t["ufficio"]["pagina"] is True
             and t["ufficio"]["conto"] == 6, js(t["ufficio"]))


def molte(cartella: Path):
    """Più di 20 fatture: la pagina ne mostra 20 e lo dice; una prenotazione in corso «In preparazione»."""
    db = str(cartella / "molte.db")
    numeri = Numeratore(db)
    for i in range(25):
        numeri.emetti("fatture", datetime.date(ANNO, 1, 1), lambda n, t: {"file": []}, "dario", "Dario", "fattura",
                      "Fattura", {"cliente": {"nome_completo": f"Cliente {i}"}})
    numeri._prenota("fatture", ANNO, datetime.date(ANNO, 1, 2), "dario", "Dario", "fattura", "Fattura", {})
    uff = types.SimpleNamespace(numeri=numeri, rubrica=Rubrica(db))
    p = raccolte.pagina(hub_di(uff), DARIO, "ufficio")
    f = per_titolo(p)["Fatture"]
    verifica("molte: 20 righe e «E altri 6: cercali con «Cerca»»", len(f["voci"]) == raccolte.UFFICIO_PER_SERIE
             and "E altri 6" in f.get("nota", ""), js(f.get("nota")))
    verifica("molte: il numero prenotato «In preparazione»", f["voci"][0]["stato"] == "In preparazione"
             and f["voci"][0]["nome"] == f"Fattura 26/{ANNO}", js(f["voci"][0]))
    q = raccolte.cerca(hub_di(uff), DARIO, "ufficio", "cliente 0")
    verifica("molte: la ricerca trova la più vecchia («Cliente 0») per prima", voci(per_titolo(q).get("Trovati fra i documenti"))
             and next(iter(voci(per_titolo(q)["Trovati fra i documenti"]).values()))["dettagli"][-1] == "Cliente 0",
             js(per_titolo(q).get("Trovati fra i documenti"))[:300])
    verifica("molte: rubrica vuota con la frase", per_titolo(p)["Rubrica"].get("vuoto", "").startswith("La rubrica è vuota"))


# ─────────────────────────── 2. permessi ───────────────────────────
def permessi(hub):
    for chi, come in ((BIANCA, "un familiare"), (TEO, "un minore"), (XENO, "un minore col segno di chi amministra"),
                      (OSPITE, "un ospite")):
        p = raccolte.pagina(hub, chi, "ufficio")
        q = raccolte.cerca(hub, chi, "ufficio", "Rossi")
        verifica(f"permessi: {come}, pagina e ricerca 404", p.get("_stato") == 404 and q.get("_stato") == 404
                 and "schede" not in p, js([p, q]))
        verifica(f"permessi: {come}, niente tessera Ufficio", "ufficio" not in [x["id"] for x in raccolte.tessere(hub, chi)])
    # Anche chiamata direttamente, la pagina ricontrolla (non solo `visibili`)
    verifica("permessi: _pagina_ufficio e _cerca_ufficio ricontrollano da sole",
             raccolte._pagina_ufficio(hub, BIANCA).get("_stato") == 404
             and raccolte._cerca_ufficio(hub, BIANCA, "Rossi").get("_stato") == 404)


# ─────────────────────────── 3. la ricerca ───────────────────────────
def ricerca(hub):
    def trovati(q):
        return [v["nome"] for c in q.get("schede") or [] for v in c.get("voci") or []]
    q = raccolte.cerca(hub, DARIO, "ufficio", "Fittizia")
    verifica("cerca: per cliente, i documenti dal più recente e il contatto",
             trovati(q) == [f"DDT DDT1/{ANNO}", f"Nota di credito NC1/{ANNO}", f"Fattura 1/{ANNO}", "Fittizia Rossi Srl"]
             and [c.get("titolo") for c in q["schede"]] == ["Trovati fra i documenti", "Trovati in rubrica"], js(trovati(q)))
    q = raccolte.cerca(hub, DARIO, "ufficio", f"fattura 1 {ANNO}")
    verifica("cerca: per numero, la più pertinente per prima", trovati(q)[:1] == [f"Fattura 1/{ANNO}"], js(trovati(q)))
    q = raccolte.cerca(hub, DARIO, "ufficio", "CV")
    verifica("cerca: una parola corta («CV») trova il contatto", trovati(q) == ["CV Servizi"], js(trovati(q)))
    q = raccolte.cerca(hub, DARIO, "ufficio", "Lodi")
    verifica("cerca: per comune e per nome, anche il personale di Dario", "Ada Lodi" in trovati(q)
             and f"Preventivo P1/{ANNO}" in trovati(q), js(trovati(q)))
    q = raccolte.cerca(hub, DARIO, "ufficio", "12345678903")
    verifica("cerca: per partita IVA", trovati(q) == ["Fittizia Rossi Srl"], js(trovati(q)))
    q = raccolte.cerca(hub, DARIO, "ufficio", "Segreta")
    verifica("cerca: mai i personali di un'altra persona", trovati(q) == [] and "Non trovo" in q.get("nota", ""), js(q)[:200])
    q = raccolte.cerca(hub, DARIO, "ufficio", "di il la")
    verifica("cerca: sole parole vuote, niente da cercare", q.get("schede") == [] and "niente da cercare" in q.get("nota", ""))
    q = raccolte.cerca(hub, DARIO, "ufficio", "  ")
    verifica("cerca: vuoto, la pagina lo dice", q.get("schede") == [] and "cercare" in q.get("nota", ""))
    for testo in (OSTILE, '"Rossi" OR *', "'; DROP TABLE numeri; --", "\u0000‮", "x" * 5000):
        q = raccolte.cerca(hub, DARIO, "ufficio", testo)
        verifica(f"cerca: testo ostile {testo[:20]!r}… una risposta, mai un errore", "_stato" not in q
                 and isinstance(q.get("nota"), str), js(q)[:200])
    q = raccolte.cerca(hub, DARIO, "ufficio", "img onerror")
    verifica("cerca: il cliente col nome ostile si trova, e resta testo", OSTILE in trovati(q), js(trovati(q)))


# ─────────────────────────── 4. servizi ───────────────────────────
def servizi(uff):
    vuoto = types.SimpleNamespace(servizi=None, tool_ctx=None)
    p = raccolte.pagina(vuoto, DARIO, "ufficio")
    verifica("servizio che manca: una nota, nessun errore", p.get("schede") == [] and "non è attivo" in p.get("nota", "")
             and "_stato" not in p, js(p))
    q = raccolte.cerca(vuoto, DARIO, "ufficio", "Rossi")
    verifica("servizio che manca: la ricerca lo dice", q.get("schede") == [] and "non è attivo" in q.get("nota", ""))

    class Rotto:
        def elenco(self, *a, **k):
            raise RuntimeError("database chiuso")
    log = []
    rotto = types.SimpleNamespace(servizi=types.SimpleNamespace(ufficio=types.SimpleNamespace(numeri=Rotto(), rubrica=uff.rubrica)),
                                  tool_ctx=None)
    p = raccolte.pagina(rotto, DARIO, "ufficio", log=log.append)
    verifica("servizio che solleva: 503 e il registro, mai un'eccezione", p.get("_stato") == 503
             and any("ufficio" in m for m in log), js(p))
    q = raccolte.cerca(rotto, DARIO, "ufficio", "Fittizia", log.append)
    verifica("ricerca col servizio che solleva: 503, senza il testo cercato nel registro",
             q.get("_stato") == 503 and not any("Fittizia" in m for m in log), str(log))
    t = {x["id"]: x for x in raccolte.tessere(rotto, DARIO, log.append)}
    verifica("servizio che solleva: la tessera «non disponibile»", t["ufficio"]["stato"] == "non disponibile")

    class RubricaRotta:
        def visibili(self, owner):
            raise RuntimeError("rubrica illeggibile")
    p = raccolte.pagina(types.SimpleNamespace(servizi=types.SimpleNamespace(
        ufficio=types.SimpleNamespace(numeri=uff.numeri, rubrica=RubricaRotta())), tool_ctx=None), DARIO, "ufficio", log=log.append)
    verifica("rubrica che solleva: 503 anche lei", p.get("_stato") == 503)
    p = raccolte.pagina(types.SimpleNamespace(servizi=types.SimpleNamespace(
        ufficio=types.SimpleNamespace(numeri=uff.numeri, rubrica=None)), tool_ctx=None), DARIO, "ufficio")
    verifica("senza rubrica: i documenti ci sono lo stesso", "Rubrica" not in per_titolo(p) and "Fatture" in per_titolo(p))


# ─────────────────────────── 6. «Scarica» ───────────────────────────
def scaricamenti(hub, uff):
    sc = scarica.Scaricamenti(Config())
    p = raccolte.pagina(hub, DARIO, "ufficio")
    for c in p["schede"]:
        registra_scaricabili(sc, 7, c, "dario")
    schermo = {"id": 7, "proprietario": "dario"}
    uno = voci(per_titolo(p)["Fatture"])[f"Fattura 1/{ANNO}"]
    pdf, xml = uno["file"]
    g = sc.gettone(schermo, xml["chiave"], "originale")
    nome, tipo, dati = sc.prendi(g["url"].rsplit("/", 1)[1])
    verifica("scarica: l'XML della FatturaPA, tipo application/xml, nome uguale in «Scaricato: …»",
             tipo == "application/xml" and dati.startswith(b"<?xml") and nome == g["nome"] == "Fattura 1.xml", f"{nome} {g['nome']} {tipo}")
    g = sc.gettone(schermo, pdf["chiave"], "originale")
    nome, tipo, dati = sc.prendi(g["url"].rsplit("/", 1)[1])
    verifica("scarica: il PDF di cortesia", tipo == "application/pdf" and dati.startswith(b"%PDF") and nome == "Fattura 1.pdf", nome)
    try:
        sc.gettone(schermo, pdf["chiave"], "pdf")
        ok = False
    except scarica.Rifiuto as e:
        ok = e.stato == 400
    verifica("scarica: un formato che non è del file 400", ok)

    def rifiutato(fn):
        try:
            fn()
            return None
        except scarica.Rifiuto as e:
            return e.stato
    # Uno schermo di Bianca: la voce non c'è (mai registrata per lei)
    verifica("scarica: dallo schermo di un familiare 404 (la voce non è sua)",
             rifiutato(lambda: sc.gettone({"id": 8, "proprietario": "bianca"}, pdf["chiave"], "originale")) == 404)
    g = sc.gettone(schermo, pdf["chiave"], "originale")
    DARIO.admin = False
    stato = rifiutato(lambda: sc.prendi(g["url"].rsplit("/", 1)[1]))
    stato2 = rifiutato(lambda: sc.gettone(schermo, pdf["chiave"], "originale"))
    DARIO.admin = True
    verifica("scarica: chi non amministra più non scarica (al clic e alla richiesta del gettone)", stato == 404 and stato2 == 404,
             f"{stato} {stato2}")
    f = Path(next(r for r in uff.numeri.elenco("fatture", ANNO) if r["numero"] == 1)["file"][0])
    g = sc.gettone(schermo, pdf["chiave"], "originale")
    f.rename(f.with_suffix(".tolto"))
    stato = rifiutato(lambda: sc.prendi(g["url"].rsplit("/", 1)[1]))
    f.with_suffix(".tolto").rename(f)
    verifica("scarica: il file tolto dalla cartella 404", stato == 404)
    # Un file che non è più fra quelli registrati per quel numero (il registro cambiato): 404
    leggi, _ = raccolte._leggi_file_ufficio(hub, DARIO, uff, "fatture", ANNO, 1, str(TMP / "altro.pdf"))
    (TMP / "altro.pdf").write_bytes(b"%PDF altro")
    verifica("scarica: mai un file che non è nel registro dei numeri", leggi() is None)
    leggi, _ = raccolte._leggi_file_ufficio(hub, DARIO, uff, "fatture", ANNO, 99, str(f))
    verifica("scarica: mai il file di un numero che non c'è", leggi() is None)
    verifica("scarica: i tipi nuovi (xml, pptx) e mai un eseguibile", scarica.tipo_mime("originale", {"estensione": "xml"}) == "application/xml"
             and scarica.estensione("originale", {"estensione": "pptx"}) == "pptx"
             and scarica.estensione("originale", {"estensione": "exe"}) == "bin")


# ─────────────────────────── 7. il server ───────────────────────────
def scarica_vero(port, sessione, chiave):
    st, d = pr.chiedi(port, "/api/scarica", sessione, corpo={"chiave": chiave, "formato": "originale"})
    if st != 200:
        return st, None, None, d
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{d['url']}", timeout=20) as r:
            return r.status, dict(r.headers), r.read(), d
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b"", d


def server(uff):
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    reg = Persone()
    hub.profilo = reg.by_id
    hub.tool_ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=None, speaker=None, ufficio=uff)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        _, t_dario = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario Rossi")
        _, t_bianca = hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
        _, t_teo = hub.archivio.crea_con_token("telefono", proprietario="teo", proprietario_nome="Teo")
        _, t_ugo = hub.archivio.crea_con_token("telefono", proprietario="ugo", proprietario_nome="Ugo")
        hub._rinfresca()
        port = srv.port
        sess = {k: pr.chiedi(port, "/api/accedi", token=t)[1].get("sessione")
                for k, t in (("dario", t_dario), ("bianca", t_bianca), ("teo", t_teo), ("ugo", t_ugo))}
        st, d = pr.chiedi(port, "/api/raccolte", sess["dario"], corpo={"raccolta": "ufficio"})
        sc = d.get("schede") or []
        verifica("server: la pagina Ufficio di chi amministra", st == 200 and len(sc) == 6, f"{st} {len(sc)}")
        verifica("server: nessuna chiave privata alla pagina (né _scarica_voci né le funzioni)",
                 not any(str(k).startswith("_") for c in sc for k in c))
        for chi, atteso in (("bianca", 404), ("teo", 404), ("ugo", 403)):
            st, _ = pr.chiedi(port, "/api/raccolte", sess[chi], corpo={"raccolta": "ufficio"})
            st2, _ = pr.chiedi(port, "/api/raccolte/cerca", sess[chi], corpo={"raccolta": "ufficio", "testo": "Rossi"})
            verifica(f"server: {chi} sulla pagina e sulla ricerca {atteso}", st == atteso and st2 == atteso, f"{st} {st2}")
        st, d = pr.chiedi(port, "/api/raccolte/cerca", sess["dario"], corpo={"raccolta": "ufficio", "testo": "Fittizia"})
        verifica("server: la ricerca di chi amministra", st == 200 and len(d.get("schede") or []) == 2
                 and not any(str(k).startswith("_") for c in d["schede"] for k in c), f"{st} {d}"[:300])
        uno = next(v for c in sc if c.get("titolo") == "Fatture" for v in c["voci"] if v["nome"] == f"Fattura 1/{ANNO}")
        xml = next(x for x in uno["file"] if x["estensione"] == "xml")
        st, h, dati, g = scarica_vero(port, sess["dario"], xml["chiave"])
        verifica("server: chi amministra scarica l'XML (tipo, attachment, sandbox, nome uguale)",
                 st == 200 and dati.startswith(b"<?xml") and h.get("content-type") == "application/xml"
                 and h.get("content-disposition", "").startswith("attachment;") and "sandbox" in h.get("content-security-policy", "")
                 and g.get("nome") == "Fattura 1.xml" and "Fattura%201.xml" in h.get("content-disposition", ""),
                 f"{st} {h} {g}")
        for chi in ("bianca", "teo"):
            st, _, _, _ = scarica_vero(port, sess[chi], xml["chiave"])
            verifica(f"server: {chi} non scarica l'XML di chi amministra (404)", st == 404, f"{st}")
        st, _, _, _ = scarica_vero(port, sess["ugo"], xml["chiave"])
        verifica("server: uno schermo senza profilo non scarica", st in (403, 404), f"{st}")
    finally:
        srv.ferma()


def main():
    try:
        uff = ufficio_finto(TMP / "uff")
        hub = hub_di(uff)
        print("— 1. la pagina")
        pagina(hub)
        molte(TMP)
        print("— 2. permessi")
        permessi(hub)
        print("— 3. la ricerca")
        ricerca(hub)
        print("— 4. servizi")
        servizi(uff)
        print("— 5–6. «Scarica»")
        scaricamenti(hub, uff)
        print("— 7. il server")
        server(uff)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(ERRORI)} errori" if ERRORI else "\ntutto ok")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
