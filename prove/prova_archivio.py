import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Archivio dei documenti di casa, a secco (niente modello, niente rete).

Documenti finti (prove/archivio_finto.py: PDF con testo, PDF scansionati, foto storte, Word)
in una cartella temporanea con le sottocartelle personali; OCR finto (il testo vero del file)
ed estrattore finto (la scheda che darebbe un modello bravo, con qualche valore inventato da
scartare). Si prova: normalizzazione e deduplicazione, controllo contro il testo, date
calcolate, grafo, interrogazioni della voce con i permessi (ospite, familiare, sensibili,
cartelle personali, zona grigia), esplorazione dell'agente, ciclo di ricerca dell'agente con un
client finto, riprocessamento a versione nuova (senza rifare l'OCR), file sparito, copia dello
stesso file, registro dei turni senza dati, prompt, registro delle capacità.

Senza pypdfium2 i PDF diventano file di testo e foto (la parte sui PDF si salta).

    python prove\\prova_archivio.py
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archivio_finto as af  # noqa: E402

from calliope import capacita  # noqa: E402
from calliope.archivio import Archivio, Chi, Grafo, periodo  # noqa: E402
from calliope.archivio import normalizza as nz  # noqa: E402
from calliope.archivio import testo as lettura  # noqa: E402
from calliope.archivio import tipi  # noqa: E402
from calliope.archivio.esplora import Esploratore  # noqa: E402
from calliope.archivio.estrattore import Estrattore  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""))


TMP = Path(tempfile.mkdtemp(prefix="calliope-archivio-"))
OGGI = datetime.date(2026, 10, 3)

# ─────────────────────────── normalizzazione ───────────────────────────
verifica("ente: S.p.A. e SpA uguali", nz.chiavi("ente", "LUMEN ENERGIA S.p.A.")[-1]
         == nz.chiavi("ente", "Lumen Energia SpA")[-1] == "nome:lumen energia")
verifica("ente: s.n.c. tolto", nz.nome_ente("Elettrodomestici Rossi s.n.c.") == "elettrodomestici rossi")
verifica("persona: ordine e titoli", nz.nome_persona("dott.ssa Anna Verdi") ==
         nz.nome_persona("VERDI ANNA") == "anna verdi")
verifica("partita IVA con la cifra di controllo", nz.partita_iva("01234567897") == "01234567897"
         and nz.partita_iva("01234567890") is None)
verifica("codice fiscale nella forma", nz.codice_fiscale("bncmra80a01f205x") == "BNCMRA80A01F205X"
         and nz.codice_fiscale("BNCMRA80A01") is None)
verifica("chiavi: forte prima", nz.chiavi("ente", "Lumen", partita_iva="01234567897")
         == ["piva:01234567897", "nome:lumen"])
verifica("numeri italiani", {84.5, 1234.56, 97.2, 520.0} <= nz.numeri(
    "Totale 84,50 euro; 1.234,56; 97.20; 520"))
giorni, mesi = nz.date("dal 01/08/2026, 12 marzo 2025, agosto 2025, 1-2-26")
verifica("date nel testo", {"2026-08-01", "2025-03-12", "2026-02-01"} <= giorni
         and "2025-08" in mesi, str(giorni))
verifica("come si dice", nz.euro(84.5) == "84,50 euro" and nz.euro(1234.5) == "1.234,50 euro"
         and nz.euro(520) == "520 euro" and nz.data_detta("2026-10-15") == "15 ottobre 2026")
verifica("luoghi: CAP e trattino non contano", nz.nome_luogo("Via dei Tigli 12, 20100 Milano")
         == nz.nome_luogo("Via dei Tigli 12 - Milano"))

# ─────────────────────────── periodi ───────────────────────────
for detto, atteso in (("2025", ("2025-01-01", "2026-01-01")), ("nel 2025", ("2025-01-01", "2026-01-01")),
                      ("settembre 2026", ("2026-09-01", "2026-10-01")),
                      ("dicembre 2025", ("2025-12-01", "2026-01-01")),
                      ("quest'anno", ("2026-01-01", "2026-10-04")),
                      ("l'anno scorso", ("2025-01-01", "2026-01-01")),
                      ("dal 2024 al 2025", ("2024-01-01", "2026-01-01")), ("", (None, None))):
    d = periodo(detto, OGGI)
    verifica(f"periodo «{detto}»", d[:2] == atteso, str(d))

# ─────────────────────────── controllo contro il testo ───────────────────────────
T = "Polizza n. AU-1\nContraente: Mario Bianchi\nScadenza: 01/11/2026\nPremio annuo: 520,00 euro"
s, sc = tipi.pulisci("assicurazione", {
    "numero": "AU-1", "intestatari": [{"nome": "Mario Bianchi", "codice_fiscale": "XXXYYY80A01F205X"},
                                      {"nome": "Paolo Neri", "codice_fiscale": None}],
    "premio": 530, "data_fine": "2026-11-01", "data_inizio": "2025-11-01",
    "scadenze": [{"data": "2026-12-01", "cosa": "rinnovo"}], "emittente": {"nome": "Ignota Spa"},
    "ramo": "volo"}, T)
verifica("inventati: premio, data, persona, ente, codice fiscale scartati",
         s["premio"] is None and s["data_inizio"] is None and len(s["intestatari"]) == 1
         and s["emittente"] is None and "codice_fiscale" not in s["intestatari"][0]
         and {x["campo"] for x in sc} >= {"premio", "data_inizio", "intestatari", "emittente",
                                         "scadenze", "intestatari.codice_fiscale"}, str(sc))
verifica("enum fuori elenco → null", s["ramo"] is None)
verifica("fine validità tra le scadenze", s["scadenze"] == [{"data": "2026-11-01",
                                                            "cosa": "fine_validita"}], str(s["scadenze"]))
s, _ = tipi.pulisci("garanzia", {"data_acquisto": "2025-03-12", "durata_mesi": 24},
                    "Data di acquisto: 12/03/2025. Durata: 24 mesi")
verifica("garanzia: fine calcolata dal programma", s["data_fine"] == "2027-03-12"
         and s["scadenze"][0].get("calcolata") and s["_calcolati"] == ["data_fine"])
s, _ = tipi.pulisci("contratto", {"data_inizio": "2026-02-01", "durata_mesi": 24,
                                  "rinnovo_tacito": True, "preavviso_disdetta_giorni": 30},
                    "attivazione 01/02/2026, durata 24 mesi, preavviso di 30 giorni")
verifica("contratto: fine e disdetta calcolate", [x["cosa"] for x in s["scadenze"]] ==
         ["disdetta", "fine_contratto"] and s["scadenze"][0]["data"] == "2028-01-02",
         str(s["scadenze"]))
verifica("schema strict: tutti i campi richiesti", set(tipi.schema("bolletta")["required"])
         == set(tipi.TIPI["bolletta"].campi) and tipi.schema("referto")["additionalProperties"] is False)
verifica("descrizione a voce", tipi.descrivi("bolletta", {
    "categoria": "luce", "emittente": {"nome": "LUMEN ENERGIA S.p.A."},
    "data_documento": "2026-09-10"}) == "la bolletta della luce di Lumen Energia del 10 settembre 2026")

# ─────────────────────────── i documenti finti ───────────────────────────
from archivio_finto import (CON_PDF, ClienteFinto, OcrFinto, SpeakerCtx, Speakers,  # noqa: E402
                            prepara_cartella)

if not CON_PDF:
    print("SALTATA IN PARTE: pypdfium2 manca: i PDF diventano testo e foto, la lettura dei PDF si salta")

ROOT = TMP / "Documenti casa"
TESTI = prepara_cartella(ROOT, TMP / "generati")
cfg = Config()
cfg.archivio_cartella = str(ROOT)
cfg.archivio_intestatari = {"Mario": "Mario Bianchi, BNCMRA80A01F205X", "Laura": "Laura Bianchi",
                            "Giulia": "Giulia Bianchi"}
ocr, cliente = OcrFinto(), ClienteFinto()
speakers = Speakers()
grafo = Grafo(str(TMP / "archivio.db"))
svc = Archivio(cfg, grafo, ROOT, Estrattore(cliente, "finto"), ocr, log=lambda *a: None,
               profili=speakers.known_speakers)
t0 = time.perf_counter()
giro = svc.giro()
verifica(f"primo giro: 10 documenti letti ({time.perf_counter() - t0:.2f} s)",
         giro["fatti"] == 10 and giro["errori"] == 0, str(giro))
verifica("OCR solo per foto e scansioni (4 foto, 2 scansioni)", ocr.chiamate == 6, str(ocr.chiamate))
c = grafo.conteggi()
verifica("deduplicazione: 8 enti (Lumen e Rossi una volta sola)", c["nodi"].get("ente") == 8,
         str(c))
verifica("deduplicazione: 4 persone (Mario Bianchi e BIANCHI MARIO uguali)",
         c["nodi"].get("persona") == 4, str(c))
verifica("beni: lavatrice condivisa da ricevuta e garanzia, Panda, POD, PDR",
         c["nodi"].get("bene") == 4, str(c))
scheda_luce25 = svc.scheda(grafo.leggi("SELECT nodo FROM schede WHERE scheda LIKE '%97.2%'")[0]["nodo"])
verifica("codice cliente inventato scartato", scheda_luce25.get("codice_cliente") is None)
sc = json.loads(grafo.leggi("SELECT scartati FROM schede WHERE tipo = 'assicurazione'")[0]["scartati"])
verifica("scadenza inventata della polizza tra gli scartati", any(x["campo"] == "scadenze" for x in sc))
lav = grafo.leggi("SELECT id FROM nodi WHERE tipo = 'bene' AND nome LIKE '%lavatrice%'")[0]["id"]
rels = {r["rel"] for r in grafo.leggi("SELECT rel FROM archi WHERE a = ?", (lav,))}
verifica("la lavatrice: coperta dalla garanzia e citata dalla ricevuta", rels == {"copre", "riguarda"},
         str(rels))
verifica("la persona paga gli importi", grafo.leggi(
    "SELECT COUNT(*) AS n FROM archi WHERE rel = 'paga'")[0]["n"] >= 6)
verifica("FTS sui testi", grafo.leggi("SELECT COUNT(*) AS n FROM testi WHERE testi MATCH 'emocromo'")[0]["n"] == 1)
verifica("vista v_documenti", len(grafo.leggi("SELECT * FROM v_documenti")) == 10)
verifica("secondo giro: niente da rifare", svc.giro()["in_coda"] == 0)

# ─────────────────────────── permessi ───────────────────────────
laura, giulia = Chi("familiare", "laura-id", "Laura"), Chi("familiare", "giulia-id", "Giulia")
mario, grigio = Chi("amministra", "mario-id", "Mario"), Chi("amministra", "mario-id", "Mario", True)
ospite = Chi("ospite")
n = {k: len(svc.documenti(v)) for k, v in (("laura", laura), ("giulia", giulia), ("mario", mario),
                                            ("grigio", grigio), ("ospite", ospite))}
verifica("visibili: Laura 7 (casa), Giulia 9 (casa + i suoi), Mario 10, zona grigia 8, ospite 0",
         n == {"laura": 7, "giulia": 9, "mario": 10, "grigio": 8, "ospite": 0}, str(n))
ref = {"attributi": {"sensibile": True, "cartella": ""}, "persone": svc.persone_di("Giulia")}
verifica("sensibile nella cartella comune: lo vede l'intestataria, non gli altri",
         svc.puo_vedere(ref, giulia) and not svc.puo_vedere(ref, laura))
verifica("persone collegate ai profili da archivio_intestatari",
         len(svc.persone_di("Mario")) == 1 and svc.persone_di("Nessuno") == set())

# ─────────────────────────── tool della voce ───────────────────────────
reg = build_registry(archivio=True)


def chiama(nome, args, chi, livello, grigia=False, schermi=None):
    ctx = ToolContext(cfg=cfg, speakers=speakers, speaker_ctx=SpeakerCtx(chi, livello, grigia),
                      speaker=None, archivio=svc, schermi=schermi)
    return json.loads(reg.call(nome, args, ctx, livello))


nomi = {s["function"]["name"] for s in reg.schemas_for("familiare")}
verifica("tool per i familiari", {"archivio_cerca", "archivio_scadenze", "archivio_somma"} <= nomi)
verifica("nessun tool per gli ospiti", not any(s["function"]["name"].startswith("archivio")
                                                for s in reg.schemas_for("ospite")))
r = chiama("archivio_cerca", {"cosa": "bolletta luce", "dato": "importo"}, None, "ospite")
verifica("ospite: rifiuto", r.get("ok") is False and "NON" in r.get("fatto", ""))
r = chiama("archivio_cerca", {"cosa": "bolletta della luce", "dato": "importo"}, "Laura", "familiare")
verifica("ultima bolletta della luce: 84,50", "84,50 euro" in r["risposta_finale"]
         and "settembre 2026" in r["risposta_finale"], r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "luce", "periodo": "2025", "dato": "importo"}, "Laura", "familiare")
verifica("luce del 2025: 97,20", "97,20 euro" in r["risposta_finale"], r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "polizza auto", "dato": "numero"}, "Laura", "familiare")
verifica("numero della polizza", "AU-2026-445566" in r["risposta_finale"], r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "lavatrice", "tipo": "garanzia", "dato": "scadenza"},
           "Laura", "familiare")
verifica("garanzia della lavatrice: fino al 12 marzo 2027", "12 marzo 2027" in r["risposta_finale"],
         r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "referto emocromo"}, "Laura", "familiare")
verifica("referto di Giulia: Laura non lo trova", r.get("ok") is False
         and "Non trovo" in r["risposta_finale"], r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "referto emocromo", "dato": "data"}, "Giulia", "familiare")
verifica("referto: Giulia lo trova", "5 settembre 2026" in r.get("risposta_finale", ""),
         r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "carta d'identità", "dato": "scadenza"}, "Mario", "amministra")
verifica("carta d'identità: chi amministra la vede", "14 luglio 2031" in r.get("risposta_finale", ""),
         r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "carta d'identità"}, "Mario", "amministra", grigia=True)
verifica("…ma non nella zona grigia", "identità" not in r.get("risposta_finale", ""),
         r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "contratto internet"}, "Laura", "familiare")
verifica("contratto nella cartella di Mario: Laura no", r.get("ok") is False)
r = chiama("archivio_cerca", {"cosa": "contratto internet", "dato": "scadenza"}, "Mario", "amministra")
verifica("contratto: disdetta e fine calcolate", "2 gennaio 2028" in r.get("risposta_finale", "")
         and "1 febbraio 2028" in r["risposta_finale"], r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "bollette", "persona": "mie", "tipo": "bolletta"}, "Laura",
           "familiare")
verifica("«le mie bollette» per Laura: l'acqua", "acqua" in r.get("risposta_finale", ""),
         r.get("risposta_finale"))
r = chiama("archivio_cerca", {"cosa": "bolletta gas", "dato": "dettagli"}, "Laura", "familiare")
verifica("dettagli: i campi al modello, senza risposta pronta",
         "risposta_finale" not in r and r["campi"].get("consumo") == 45, str(r)[:200])
r = chiama("archivio_somma", {"categoria": "luce", "periodo": "2025"}, "Laura", "familiare")
verifica("somma luce 2025", r.get("totale") == 97.2 and "97,20 euro" in r["risposta_finale"],
         r.get("risposta_finale"))
r = chiama("archivio_somma", {"categoria": "luce"}, "Laura", "familiare")
verifica("somma luce di sempre, con gli anni", r.get("totale") == 181.7
         and "Nel 2025 97,20 euro, nel 2026 84,50 euro" in r["risposta_finale"],
         r.get("risposta_finale"))
r = chiama("archivio_somma", {"periodo": "2026"}, "Laura", "familiare")
verifica("tutte le spese del 2026 (luce, gas, acqua)", r.get("totale") == 226.61, str(r.get("totale")))
r = chiama("archivio_somma", {"ente": "Lumen Energia"}, "Laura", "familiare")
verifica("somma per ente", r.get("totale") == 181.7, str(r.get("totale")))
r = chiama("archivio_somma", {"categoria": "luce", "periodo": "2024"}, "Laura", "familiare")
verifica("somma vuota", r.get("ok") is False and "Non trovo" in r["risposta_finale"])
lst = svc.scadenze(laura, 31, oggi=OGGI)
verifica("scadenze del mese (Laura): luce, gas, polizza",
         [(x["data"], x["cosa"]) for x in lst] == [("2026-10-15", "pagamento"),
                                                    ("2026-10-20", "pagamento"),
                                                    ("2026-11-01", "fine_validita")],
         str([(x["data"], x["cosa"]) for x in lst]))
r = chiama("archivio_scadenze", {"entro": "anno"}, "Laura", "familiare")
verifica("tool delle scadenze", r.get("ok") is True and r.get("risposta_finale"))


class SchermiFinti:
    def mittente(self, ctx):
        return None


r = chiama("archivio_cerca", {"cosa": "referto"}, "Giulia", "familiare", schermi=SchermiFinti())
verifica("scheda per gli schermi: personale per un referto",
         r.get("scheda", {}).get("visibilita") == "personale")
r = chiama("archivio_cerca", {"cosa": "bolletta gas"}, "Laura", "familiare", schermi=SchermiFinti())
verifica("scheda per gli schermi: della casa per una bolletta",
         r.get("scheda", {}).get("visibilita") == "casa"
         and r["scheda"]["chiave"].startswith("archivio:"))

# ─────────────────────────── registro dei turni ───────────────────────────
from calliope.brain import Brain  # noqa: E402

b = Brain.__new__(Brain)
b.cfg, b.tools, b.history, b.last_tools, b.last_private = cfg, reg, [], [], False
b.tool_ctx = ToolContext(cfg=cfg, speakers=speakers, speaker_ctx=SpeakerCtx("Laura", "familiare"),
                         speaker=None, archivio=svc)
import contextlib  # noqa: E402
import io  # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    out = b._run_tool({"name": "archivio_cerca", "id": "c1",
                       "arguments": {"cosa": "bolletta luce", "dato": "importo"}}, "familiare")
verifica("registro dei turni: solo il nome del tool", b.last_tools[0]["argomenti"] == {}
         and b.last_private and "84,50" in out and "84,50" not in buf.getvalue()
         and "bolletta" not in buf.getvalue(), buf.getvalue())

# ─────────────────────────── esplorazione dell'agente ───────────────────────────
esp = Esploratore(svc, Chi("familiare", "laura-id", "Laura", zona_grigia=True))
r = esp.esegui("grafo_somma", {"categoria": "luce", "raggruppa": "anno"})
verifica("agente: somma per anno", r["gruppi"] == {"2025": {"totale": 97.2, "documenti": 1},
                                                   "2026": {"totale": 84.5, "documenti": 1}}, str(r))
r = esp.esegui("grafo_trova", {"testo": "Lumen"})
lumen = [x for x in r["nodi"] if x["tipo"] == "ente"]
verifica("agente: trova l'ente", len(lumen) == 1, str(r))
r = esp.esegui("grafo_vicini", {"nodo": lumen[0]["id"], "relazione": "emesso_da", "verso": "entranti"})
verifica("agente: i documenti di Lumen", len(r["archi"]) == 2, str(r)[:300])
luce = esp.esegui("grafo_trova", {"testo": "luce", "tipo": "categoria"})["nodi"][0]["id"]
r = esp.esegui("grafo_cammino", {"partenza": [luce], "passi": [
    {"relazione": "riguarda", "verso": "entranti"}, {"relazione": "ha_importo", "verso": "uscenti"}]})
verifica("agente: cammino categoria → documenti → importi", sorted(
    n["valore"] for n in r["nodi"]) == [84.5, 97.2], str(r)[:300])
r = esp.esegui("grafo_trova", {"testo": "Verdi"})
verifica("agente: il medico del referto non compare", r["nodi"] == [], str(r))
r = Esploratore(svc, Chi("familiare", "giulia-id", "Giulia", zona_grigia=True)).esegui(
    "grafo_documenti", {"tipo_doc": "referto"})
verifica("agente: i documenti sensibili mai, nemmeno all'interessata", r["quanti"] == 0)
r = esp.esegui("grafo_documenti", {"tipo_doc": "bolletta", "periodo": "2026"})
verifica("agente: documenti filtrati con i campi", r["quanti"] == 3 and all(
    "scadenze" in d for d in r["documenti"]), str(r)[:200])
verifica("agente: strumento sconosciuto", "errore" in esp.esegui("grafo_sql", {"q": "x"}))
verifica("agente: schema", "relazioni" in esp.esegui("grafo_schema", {}))

# ciclo di ricerca dell'agente con un client finto
from calliope.agenti.arbitro import Arbitro  # noqa: E402
from calliope.agenti.ciclo import Agente, Lavoro  # noqa: E402


class ClienteAgente:
    def __init__(self):
        self.visti = []
        self.passo = 0

    def chat(self, body, su_pezzo=None, controlla=None):
        self.visti.append(body)
        self.passo += 1
        if self.passo == 1:
            calls = [{"name": "grafo_somma", "arguments": {"categoria": "luce", "raggruppa": "anno"}}]
            return {"content": "", "tool_calls": calls, "eval": 10, "prompt": 100, "s": 0.0}
        return {"content": "", "tool_calls": [{"name": "consegna", "arguments": {
            "testo": "Luce: 97,20 euro nel 2025, 84,50 nel 2026.",
            "riassunto": "Nel 2026 hai speso 84,50 euro di luce, nel 2025 97,20."}}],
                "eval": 10, "prompt": 100, "s": 0.0}

    def interrompi(self):
        pass


ca = ClienteAgente()
ag = Agente(cfg, SimpleNamespace(modello="finto", modello_scrittore="finto"), ca, Arbitro(False))
ag.archivio = svc
ris = ag.ricerca(Lavoro("L1", "ricerca", "quanto ho speso di luce quest'anno rispetto al 2025?",
                        "laura-id", "Laura", "familiare"))
strumenti = {t["function"]["name"] for t in ca.visti[0]["tools"]}
tool_msg = next(m for m in ca.visti[1]["messages"] if m["role"] == "tool")
verifica("ricerca dell'agente con il grafo: strumenti, risultato vero, consegna",
         {"grafo_somma", "grafo_cammino", "consegna"} <= strumenti
         and "biblioteca_cerca" not in strumenti and "97.2" in tool_msg["content"]
         and ris["riassunto"].startswith("Nel 2026"), str(strumenti))

# ─────────────────────────── riprocessamento, file spariti, copie ───────────────────────────
vecchia = tipi.VERSIONE
tipi.VERSIONE = "prova-2"
ocr.chiamate = cliente.chiamate = 0
g2 = svc.giro()
verifica("versione nuova dell'estrattore: rielabora tutto senza rifare l'OCR",
         g2["fatti"] == 10 and ocr.chiamate == 0 and cliente.chiamate == 20, str((g2, ocr.chiamate)))
verifica("…e il grafo non raddoppia", grafo.conteggi() == c, str(grafo.conteggi()))
verifica("…e le schede hanno la versione nuova", grafo.leggi(
    "SELECT COUNT(*) AS n FROM schede WHERE versione = 'prova-2'")[0]["n"] == 10)
tipi.VERSIONE = vecchia
svc.riprocessa()
svc.giro()
gas = next(ROOT.glob("gas ottobre.*"))
copia = ROOT / "copie" / next(ROOT.glob("bolletta luce settembre 2026.*")).name
copia.parent.mkdir()
shutil.copy(next(ROOT.glob("bolletta luce settembre 2026.*")), copia)
gas.unlink()
svc.giro()
c3 = grafo.conteggi()
verifica("file sparito: tolto il documento e quello che affermava (Gasnova, PDR)",
         len(grafo.leggi("SELECT id FROM nodi WHERE tipo = 'documento'")) == 9
         and c3["nodi"].get("ente") == 7 and c3["nodi"].get("bene") == 3, str(c3))
verifica("copia dello stesso file: un documento solo, due file",
         grafo.leggi("SELECT COUNT(*) AS n FROM file")[0]["n"] == 10)
(ROOT / "rovinato.pdf").write_bytes(b"%PDF-1.4 non proprio")
(ROOT / "vuota.png").write_bytes(b"")
g4 = svc.giro()
verifica("file rovinati: errore, non un crash", g4["errori"] == (2 if CON_PDF else 1)
         or g4["errori"] >= 1, str(g4))
tutto_via = list(ROOT.rglob("*.*"))
shutil.move(str(ROOT), str(TMP / "staccato"))
ROOT.mkdir()
svc.giro()
verifica("cartella vuota (disco staccato): l'archivio non si svuota",
         len(grafo.leggi("SELECT id FROM nodi WHERE tipo = 'documento'")) == 9)

# ─────────────────────────── lettura dei file ───────────────────────────
gen = af.genera(TMP / "lettura")
dx = next(d for d in gen if d["formato"] == "docx")
verifica("Word: paragrafi", "LV800-55A21" in lettura.leggi(dx["percorso"]).testo)
foto = next(d for d in gen if d["formato"] == "foto")
try:
    lettura.leggi(foto["percorso"], None)
    verifica("foto senza OCR: errore chiaro", False)
except lettura.ErroreTesto as e:
    verifica("foto senza OCR: errore chiaro", "OCR" in str(e), str(e))
if CON_PDF:
    pdf = next(d for d in gen if d["formato"] == "pdf")
    e = lettura.leggi(pdf["percorso"])
    verifica("PDF con testo: niente OCR", e.metodo == "pdf" and "84,50" in e.testo, e.metodo)
    scan = next(d for d in gen if d["formato"] == "scansione")
    o = OcrFinto()
    TESTI[Path(scan["percorso"]).stem] = scan["testo"]
    e = lettura.leggi(scan["percorso"], o)
    verifica("PDF scansionato: la pagina va all'OCR", e.metodo == "ocr" and o.chiamate == 1)

# ─────────────────────────── prompt e capacità ───────────────────────────
verifica("prompt: archivio nominato solo se c'è", "archivio_cerca" in Config().prompt_for(
    False, archivio=True) and "archivio_cerca" not in Config().prompt_for(False))
c0 = Config()
verifica("capacità: senza cartella da configurare",
         capacita.check_archivio(c0)["stato"] == "da_configurare")
c0.archivio_cartella = str(TMP / "non-esiste")
verifica("capacità: cartella che non c'è", capacita.check_archivio(c0)["stato"] == "guasta")
r = capacita.check_archivio(cfg, svc)
verifica("capacità: attiva con il numero di documenti", r["stato"] == "attiva"
         and "9 documenti" in r["motivo"], r["motivo"])

# ── Stesso Ollama e stesso modello della voce: num_ctx e keep_alive della voce (04/10) ──
from calliope.agenti.impostazioni import opzioni_voce  # noqa: E402
from calliope.archivio.estrattore import Estrattore  # noqa: E402
from calliope.archivio.testo import OcrVisivo  # noqa: E402
from calliope.config import Config as _Cfg  # noqa: E402

_cv = _Cfg()
_cv.llm_native_url, _cv.llm_model = "http://127.0.0.1:11434", "gemma4:26b-a4b-it-qat"
_cv.llm_num_ctx, _cv.llm_keep_alive = 16384, "-1"
_ov = opzioni_voce(_cv, "http://localhost:11434/", "gemma4:26b-a4b-it-qat")
verifica("opzioni della voce: stesso Ollama e stesso modello → num_ctx e keep_alive",
         _ov == {"options": {"num_ctx": 16384}, "keep_alive": -1}, _ov)
for _u, _m, _mot in [("http://127.0.0.1:11434", "qwen3.6:35b", "ollama"),
                     ("http://127.0.0.1:11436", "gemma4:26b-a4b-it-qat", "ollama"),
                     ("http://127.0.0.1:11434/v1", "gemma4:26b-a4b-it-qat", "openai")]:
    verifica(f"opzioni della voce: niente con {_u} {_m} {_mot}",
             opzioni_voce(_cv, _u, _m, _mot) == {})


class _ClienteVisto:
    def __init__(self):
        self.body = None

    def chat(self, body):
        self.body = body
        return {"content": "{}"}


# Lo schema del tipo va nel corpo come «format» (output strutturati di Ollama), senza
# thinking (06/10: prima la verifica era sempre vera)
from calliope.archivio import tipi as _tipi  # noqa: E402
_cl = _ClienteVisto()
Estrattore(_cl, "gemma4:26b-a4b-it-qat")._chiedi("s", "u", _tipi.schema_tipo())
verifica("estrattore: schema del tipo nel corpo",
         _cl.body.get("format") == _tipi.schema_tipo() and _cl.body.get("think") is False
         and _cl.body.get("model") == "gemma4:26b-a4b-it-qat", _cl.body)
_t0 = next(iter(_tipi.TIPI))
Estrattore(_cl, "m")._chiedi("s", "u", _tipi.schema(_t0))
verifica(f"estrattore: schema della scheda ({_t0}) nel corpo",
         _cl.body.get("format") == _tipi.schema(_t0), _cl.body.get("format"))
_cl = _ClienteVisto()
Estrattore(_cl, "gemma4:26b-a4b-it-qat", voce=_ov)._chiedi("s", "u", {"type": "object"})
verifica("estrattore con le opzioni della voce",
         _cl.body["options"].get("num_ctx") == 16384 and _cl.body.get("keep_alive") == -1
         and _cl.body["options"].get("num_predict") == 2500, _cl.body)
_ocr = OcrVisivo("http://127.0.0.1:11434", "gemma4:26b-a4b-it-qat", "ollama", voce=_ov)
_visto = {}


class _Risp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": "testo"}}


class _Http:
    def post(self, path, json):
        _visto.update(json)
        return _Risp()

    def close(self):
        pass


_ocr.http.close()
_ocr.http = _Http()
from PIL import Image  # noqa: E402
_ocr.leggi(Image.new("RGB", (8, 8)))
verifica("OCR con le opzioni della voce",
         _visto["options"].get("num_ctx") == 16384 and _visto.get("keep_alive") == -1
         and _visto["options"].get("num_predict") == 3000, _visto.get("options"))

grafo.close()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}.")
sys.exit(1 if errori else 0)
