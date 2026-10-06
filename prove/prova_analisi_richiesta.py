import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dell'analisi della richiesta prima di partire (06/10/2026,
calliope/agenti/richiesta.py), con l'agente su un Ollama FINTO (prove/ollama_finto.py):

- interpretazione del JSON (rotto, esito sconosciuto, vaga senza domande, raffinabile senza
  specifica, impossibile senza motivo), frasi delle domande (al più 2 a voce), funzioni dal
  registro dei tool (senza i tool dei lavori), schema senza «vaga» dopo le domande;
- delega_lavoro di tipo codice: chiara (proposta di sempre), raffinabile («Ho capito così: …»
  e il compito all'agente raffinato), vaga (domande in sospeso, niente lavoro; la risposta si
  analizza di nuovo senza domande e porta alla proposta), «c'è già» con un tool vero (e il «sì,
  comunque» che propone senza un'altra analisi) e con un tool inventato (si procede),
  «impossibile qui» (niente lavoro); tempo scaduto, errore del motore e analisi spenta: si
  procede come prima; frase d'attesa solo oltre la soglia; thinking spento e schema JSON nella
  richiesta;
- estensione_crea: titolo dal nome dell'estensione, fonte web che non risponde → vaga con la
  domanda sulla fonte, fonte che risponde → chiara; modulo dello schermo con tutte le domande e
  ripresa dai valori scritti;
- motivo in parole di un lavoro fermato da un tetto senza il codice («ha cercato i dati senza
  arrivare a scrivere il codice»).
"""

import json
import tempfile
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.agenti import richiesta as ar
from calliope.agenti.ciclo import Lavoro
from calliope.agenti.servizio import cosa_ha_fatto
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.estensioni import estensioni_specs
from calliope.tools.spec import ToolContext
from prove.ollama_finto import FakeOllama

TMP = Path(tempfile.mkdtemp(prefix="calliope-analisi-"))
MODELLO = "qwen3.6:35b"
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def sezione(nome):
    print(f"— {nome}", flush=True)


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name="Dario", level="amministra", how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


def risposta(esito="chiara", tipo="codice", domande=(), specifica="", nome="", fonte_url="",
             tool="", come_chiederlo="", motivo="", stati=None) -> dict:
    """La risposta del modello nel formato dell'analizzatore (stati dei punti), da un esito."""
    punti = {p: {"stato": "detto", "nota": ""} for p in ar.PUNTI[tipo]}
    primo = "output"
    if esito == "vaga":
        punti[primo]["stato"] = "manca"
    elif esito == "raffinabile":
        punti[primo]["stato"] = "dal_contesto"
    for p, st in (stati or {}).items():
        punti[p] = {"stato": st, "nota": ""}
    d = {"impossibile": motivo, "gia_fatto": tool, "come_chiederlo": come_chiederlo,
         "punti": punti, "domande": list(domande), "specifica": specifica, "nome": nome,
         "fonte_url": fonte_url}
    return {"content": json.dumps(d, ensure_ascii=False)}


# ═══════════════════════════ 1. pezzi ═══════════════════════════
sezione("interpretazione e frasi")
verifica("JSON rotto → nessuna (si procede)", ar.interpreta("non json", "codice").esito == "nessuna")
verifica("senza i punti → nessuna",
         ar.interpreta(json.dumps({"esito": "chiara"}), "codice").esito == "nessuna")
verifica("un punto che manca senza domande → chiara",
         ar.interpreta(risposta(esito="vaga")["content"], "codice").esito == "chiara")
verifica("dal contesto senza specifica → chiara",
         ar.interpreta(risposta(esito="raffinabile")["content"], "codice").esito == "chiara")
verifica("estensione: l'input non manca mai (lo dice chi la usa), anche se il modello lo dice",
         ar.interpreta(risposta(tipo="estensione", stati={"input": "manca"}, domande=["Quale?"])[
             "content"], "estensione").esito == "chiara"
         and "manca" not in ar.schema("estensione")["properties"]["punti"]["properties"][
             "input"]["enum"])
e = ar.interpreta(risposta(esito="raffinabile", specifica="x")["content"], "codice",
                  conversazione=False)
verifica("senza conversazione non c'è raffinabile", e.esito == "chiara")
verifica("stato sconosciuto → scelta ragionevole",
         ar.interpreta(risposta(stati={"input": "boh"})["content"], "codice").stati["input"]
         == "scelta_ragionevole")
verifica("impossibile prima di tutto, poi c'è già",
         ar.interpreta(risposta(esito="vaga", domande=["a?"], motivo="no", tool="calcola")[
             "content"], "codice").esito == "impossibile"
         and ar.interpreta(risposta(esito="vaga", domande=["a?"], tool="calcola")["content"],
                           "codice").esito == "gia_fatto")
e = ar.interpreta(risposta(esito="vaga", domande=[
    {"domanda": "Vuoi anche i simboli?", "senza_risposta": "sceglie"}])["content"], "codice")
verifica("una domanda che l'agente sceglie da solo non si fa (e non c'è altro: chiara)",
         e.esito == "chiara" and not e.domande)
e = ar.interpreta(risposta(esito="vaga", domande=[
    {"domanda": "Vuoi anche i simboli?", "senza_risposta": "sceglie"},
    {"domanda": "Che tariffa usa l'azienda?", "senza_risposta": "sbaglia"}])["content"], "codice")
verifica("restano solo le domande indispensabili", e.esito == "vaga"
         and e.domande == ["Che tariffa usa l'azienda?"], str(e.domande))
verifica("le ricerche (web_cerca, archivio) non sono funzioni da proporre",
         "web_cerca" not in [n for n, _ in ar.funzioni(build_registry(web=Config()))])
e = ar.interpreta(risposta(esito="vaga", domande=["Quale tariffa usa l'azienda"],

                           specifica="x")["content"], "codice", senza_domande=True)
verifica("dopo le domande una vaga diventa raffinabile", e.esito == "raffinabile")
e = ar.interpreta(risposta(esito="vaga", tipo="estensione",
                           domande=["**Quale** linea https://x.it"])["content"], "estensione")
verifica("domande pulite (niente markdown né indirizzi, «?» in fondo), punti che mancano",
         e.domande == ["Quale linea?"] and e.mancano == ["output"], str(e.domande))
f = ar.frase_domande(["Quale linea?", "Quale fermata?", "Di quale azienda?"])
verifica("a voce al più 2 domande", "Quale linea?" in f and "Quale fermata?" in f
         and "azienda" not in f and f.endswith("?"), f)
verifica("con lo schermo: «le altre sullo schermo»",
         "sullo schermo" in ar.frase_domande(["a?", "b?", "c?"], schermo=True))
reg = build_registry(documenti=FORMATI, agenti=True)
for s in estensioni_specs():
    reg.register(s)
nomi = [n for n, _ in ar.funzioni(reg)]
verifica("funzioni dal registro dei tool: calcola e data_calcola sì, i lavori no",
         "calcola" in nomi and "data_calcola" in nomi and "delega_lavoro" not in nomi
         and "estensione_crea" not in nomi, f"{len(nomi)} funzioni")
def stati_schema(sc):
    return sc["properties"]["punti"]["properties"]["input"]["enum"]


verifica("schema senza «manca» dopo le domande",
         "manca" not in stati_schema(ar.schema("codice", True))
         and "manca" in stati_schema(ar.schema("codice")))

# ═══════════════════════════ 2. delega_lavoro di codice ═══════════════════════════
fake = FakeOllama(modelli=(MODELLO,), caricati=(MODELLO,)).avvia()
cfg = Config()
cfg.agenti_url = fake.url
cfg.agenti_modello = MODELLO
cfg.agenti_risultati = str(TMP / "risultati")
cfg.agenti_sandbox = str(TMP / "sandbox")
cfg.agenti_sandbox_motore = "processo"
cfg.agenti_modelli = str(TMP / "modelli")
cfg.llm_native_url = "http://127.0.0.1:9"
cfg.agenti_arbitro = "mai"
cfg.agenti_analisi_s = 2.0
cfg.estensioni_cartella = str(TMP / "estensioni")
svc = Lavori(cfg, carica(cfg), log=lambda *_: None, formati=FORMATI)
svc.modelli = {}
svc.diagnosi.update(codice="ok", stato="attiva", caricato=True)
svc.analizzatore = ar.Analizzatore(cfg, svc, log=lambda *_: None)
attese: list = []


def ctx(turno, testo="", storia=None, schermi=None):
    return ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(), speaker=None,
                       lavori=svc, turno=turno, user_text=testo, storia=list(storia or []),
                       strumenti=reg, attesa=attese.append, schermi=schermi)


def delega(compito, turno, testo=None, storia=None, **altro):
    return json.loads(reg.call("delega_lavoro", {"tipo": "codice", "compito": compito, **altro},
                               ctx(turno, compito if testo is None else testo, storia),
                               "amministra"))


def nuove(n0):
    return fake.richieste[n0:]


sezione("delega_lavoro: chiara")
n0 = len(fake.richieste)
fake.copione = [risposta(esito="chiara", specifica="Primi fino a mille in Python")]
out = delega("Scrivi un programma in Python che trova i numeri primi fino a mille", 10)
corpo = (nuove(n0) or [{}])[0]
verifica("chiara: la proposta di sempre, senza specifica", out["risposta_finale"].endswith(
    "Procedo?") and "Ho capito così" not in out["risposta_finale"], out["risposta_finale"])
verifica("una richiesta all'agente, senza ragionamento, con lo schema e il modello dell'agente",
         len(nuove(n0)) == 1 and corpo.get("think") is False and isinstance(
             corpo.get("format"), dict) and corpo.get("model") == MODELLO)
sistema = corpo["messages"][0]["content"]
verifica("il prompt ha la lista di controllo del codice e le funzioni di Calliope",
         "dati_persona" in sistema and "data_calcola" in sistema and "niente rete" in sistema)

sezione("delega_lavoro: raffinabile")
storia = [("user", "Il mutuo è di 120 000 euro a 20 anni al 3,1 % fisso"),
          ("assistant", "Va bene.")]
spec = ("Piano di ammortamento alla francese per 120 000 euro, 20 anni, 3,1 % fisso, rata "
        "mensile")
fake.copione = [risposta(esito="raffinabile", specifica=spec)]
n0 = len(fake.richieste)
out = delega("Scrivimi un programma che mi fa il piano di ammortamento", 20, storia=storia)
utente = nuove(n0)[0]["messages"][1]["content"]
verifica("la conversazione recente va all'analisi", "120 000 euro" in utente, utente[:120])
verifica("raffinabile: «Ho capito così: …» prima di «Procedo?»",
         out["risposta_finale"].startswith("Ho capito così: piano di ammortamento alla francese")
         and out["risposta_finale"].endswith("Procedo?"), out["risposta_finale"])
off = svc.offerta("dario-id", 21)
verifica("il compito all'agente è quello raffinato, il titolo quello della richiesta",
         off and off["lavoro"].compito == spec and "piano" in off["lavoro"].titolo
         and "Richiesta come detta" in off["lavoro"].vincoli, off and off["lavoro"].titolo)
svc._offerte.clear()

sezione("delega_lavoro: vaga, domande e risposta")
fake.copione = [risposta(esito="vaga", stati={"dati_persona": "manca"},
                         domande=["Che tariffa al chilometro usa la tua azienda?",
                                  "Quanti chilometri hai fatto?"])]
n_lav = len(svc.lavori)
out = delega("Calcolami il rimborso con la tariffa al chilometro che usa la mia azienda", 30)
sosp = out.get("in_sospeso") or {}
verifica("vaga: due domande a voce, azione in sospeso per delega_lavoro, niente lavoro",
         "tariffa" in out["risposta_finale"] and "chilometri" in out["risposta_finale"]
         and sosp.get("tool") == "delega_lavoro" and svc.offerta("dario-id", 31) is None
         and len(svc.lavori) == n_lav and "NON" in out.get("fatto", ""), out["risposta_finale"])
fake.copione = [risposta(esito="raffinabile",
                         specifica="Rimborso di 455,5 km a 0,42 euro al chilometro")]
n0 = len(fake.richieste)
out = delega("Rimborso chilometrico a 0,42 euro al chilometro per 455,5 km", 31,
             testo="0,42 euro al chilometro, ho fatto 455,5 chilometri")
corpo = nuove(n0)[0]
verifica("la risposta si analizza di nuovo senza «vaga», con domande e risposta nel prompt",
         "manca" not in stati_schema(corpo["format"])
         and "Domande fatte" in corpo["messages"][1]["content"]
         and "455,5 chilometri" in corpo["messages"][1]["content"])
verifica("dopo la risposta: la proposta con la specifica", out["risposta_finale"].startswith(
    "Ho capito così: rimborso di 455,5 km") and out["risposta_finale"].endswith("Procedo?"),
    out["risposta_finale"])
svc._offerte.clear()

sezione("delega_lavoro: c'è già e impossibile qui")
fake.copione = [risposta(esito="gia_fatto", tool="data_calcola",
                         come_chiederlo="quanti giorni mancano al 25 dicembre?")]
out = delega("Scrivi un programma che dice quanti giorni mancano a una data", 40)
verifica("c'è già: lo dice, come chiederlo, «vuoi comunque…?» in sospeso, niente lavoro",
         out["risposta_finale"].startswith("Questo lo so già fare: chiedimi pure «quanti giorni")
         and out["in_sospeso"]["tool"] == "delega_lavoro"
         and svc.offerta("dario-id", 41) is None, out["risposta_finale"])
n0 = len(fake.richieste)
out = delega("Scrivi un programma che dice quanti giorni mancano a una data", 41, testo="sì")
verifica("«sì, comunque»: la proposta senza un'altra analisi",
         out["risposta_finale"].endswith("Procedo?") and not nuove(n0), out["risposta_finale"])
svc._offerte.clear()
fake.copione = [risposta(esito="gia_fatto", tool="fa_tutto_lui", come_chiederlo="fallo")]
out = delega("Scrivi un programma che converte i numeri romani", 50)
verifica("c'è già con un tool inventato: si procede", out["risposta_finale"].endswith(
    "Procedo?"), out["risposta_finale"])
svc._offerte.clear()
fake.copione = [risposta(esito="impossibile",
                         motivo="La sandbox non raggiunge la rete di casa, quindi nemmeno l'inverter.")]
out = delega("Fammi un programma che legge i dati del mio inverter", 60)
verifica("impossibile qui: lo dice subito, senza domande né lavoro",
         out["risposta_finale"].startswith("Questo qui non posso farlo: la sandbox non raggiunge")
         and not out.get("in_sospeso") and svc.offerta("dario-id", 61) is None,
         out["risposta_finale"])

sezione("ripieghi: tempo, errore, spenta")
fake.copione = [risposta(esito="vaga", domande=["Quale?"])]
fake.ritardo_pezzo = 1.0
attese.clear()
t0 = time.monotonic()
out = delega("Scrivi uno script che ordina un file CSV", 70)
dt = time.monotonic() - t0
fake.ritardo_pezzo = 0.0
verifica("tempo scaduto: si procede come prima, entro il tempo dell'analisi",
         out["risposta_finale"].endswith("Procedo?") and dt < cfg.agenti_analisi_s + 1.0,
         f"{dt:.2f} s")
verifica("oltre la soglia la frase d'attesa, una volta", attese == [ar.ATTESA], str(attese))
svc._offerte.clear()
time.sleep(1.5)                          # lo stream interrotto finisce
fake.copione = [{"errore": "boom", "status": 500}]
attese.clear()
out = delega("Scrivi uno script che ordina un file CSV", 80)
verifica("errore del motore: si procede, senza frase d'attesa",
         out["risposta_finale"].endswith("Procedo?") and attese == [], out["risposta_finale"])
svc._offerte.clear()
cfg.agenti_analisi = False
n0 = len(fake.richieste)
out = delega("Scrivi uno script che ordina un file CSV", 90)
verifica("analisi spenta (agenti_analisi): nessuna richiesta, proposta di sempre",
         not nuove(n0) and out["risposta_finale"].endswith("Procedo?"))
cfg.agenti_analisi = True
svc._offerte.clear()

# ═══════════════════════════ 3. estensione_crea ═══════════════════════════
sezione("estensione_crea")


class ArchivioFinto:
    def voce(self, nome):
        return None

    def nomi(self):
        return []


class EstFinte:
    archivio = ArchivioFinto()

    def pronto(self):
        return True


class Moduli:
    def __init__(self):
        self.aperti = []

    def apri(self, spec, riprendi, mittente, tool, livello):
        self.aperti.append((spec, riprendi, tool))
        return {"mostrato": True, "id": "m1"}

    def aperto(self, mid):
        return object()

    def chiudi_per_tool(self, *a, **k):
        return 0


class HubFinto:
    def __init__(self):
        self.moduli = Moduli()

    def mittente(self, ctx):
        return "Dario"

    def invia(self, card, sender):
        return {"schermi": ["studio"]}


def crea(compito, turno, schermi=None, **altro):
    c = ctx(turno, compito, schermi=schermi)
    c.estensioni = EstFinte()
    return json.loads(reg.call("estensione_crea", {"compito": compito, **altro}, c, "amministra"))


fake.copione = [risposta(esito="chiara", nome="regioni d'italia",
                         specifica="Dalla tabella delle regioni di Wikipedia, capoluogo e abitanti",
                         fonte_url="https://it.wikipedia.org/wiki/Regioni_d%27Italia")]
svc.analizzatore.verifica_fonte = lambda url, t: True
out = crea("Leggi la tabella delle regioni da Wikipedia e dimmi capoluogo e abitanti", 100)
off = svc.offerta("dario-id", 101)
verifica("estensione chiara con la fonte che risponde: proposta, titolo dal nome dell'analisi",
         out["risposta_finale"].endswith("Procedo?") and off
         and off["lavoro"].titolo == "regioni d'italia", off and off["lavoro"].titolo)
svc._offerte.clear()
fake.copione = [risposta(esito="chiara", nome="comune dal cap",
                         fonte_url="https://www.esempio-cap.it/elenco.csv")]
svc.analizzatore.verifica_fonte = lambda url, t: False
out = crea("Un'estensione che dato il CAP mi dice il comune", 110, nome="cap e comuni")
verifica("fonte che non risponde: vaga, con la domanda sul sito",
         "da quale sito" in out["risposta_finale"]

         and out["in_sospeso"]["tool"] == "estensione_crea", out["risposta_finale"])
svc.analizzatore.dimentica("dario-id")
fake.copione = [risposta(esito="vaga", tipo="estensione", stati={"fonte": "manca"},
                         domande=["Quale linea?", "Quale fermata?", "Di quale azienda?"])]
hub = HubFinto()
out = crea("Fammi un'estensione che mi dice quando passa il prossimo autobus", 120,
           schermi=hub)
spec_m, riprendi, tool = hub.moduli.aperti[-1] if hub.moduli.aperti else ({}, None, "")
verifica("tre domande: due a voce, tutte e tre sul modulo dello schermo",
         len(spec_m.get("campi") or []) == 3 and tool == "estensione_crea"
         and "sullo schermo" in out["risposta_finale"] and "azienda" not in
         out["risposta_finale"], out["risposta_finale"])
r = riprendi({"d0": "linea 7", "d1": "piazza Fantasia", "d2": "Trasporti Fantasia"}, 121)
off = svc.offerta("dario-id", 122)
verifica("risposte scritte nel modulo: la proposta, con le risposte nel compito",
         str(r.get("risposta_finale", "")).endswith("Procedo?") and off
         and "linea 7" in off["lavoro"].compito and off["lavoro"].tipo == "estensione",
         r.get("risposta_finale"))
svc._offerte.clear()

# ═══════════════════════════ 4. motivo del tetto in parole ═══════════════════════════
sezione("lavoro fermato da un tetto")
lav = Lavoro("L9", "estensione", "città della regione")
lav.titolo = "città della regione"
lav.esempi = 5
r = {"esito": "limite", "motivo": "ho dovuto fermarlo: ha fatto tutte le 24 passate del lavoro",
     "file": ["esempi/lombardia.html", "esplora.py", "esplora2.py", "manifesto.json"]}
verifica("estensione senza estensione.py: «ha cercato i dati senza arrivare a scrivere il codice»",
         cosa_ha_fatto(lav, r) == "ha cercato i dati senza arrivare a scrivere il codice")
lav.stato, lav.risultato = "errore", r
frase = svc.frase_finale(lav)
verifica("l'annuncio lo dice prima del tetto", "ha cercato i dati senza arrivare a scrivere il "
         "codice, e ha fatto tutte le 24 passate" in frase, frase)
r2 = dict(r, file=["estensione.py", "test_estensione.py"])
verifica("con estensione.py niente frase (parlano i test)", cosa_ha_fatto(lav, r2) == "")
lav_c = Lavoro("L10", "codice", "x")
verifica("codice con solo test: «non è arrivato a scrivere il codice»",
         cosa_ha_fatto(lav_c, {"file": ["test_x.py"]}) == "non è arrivato a scrivere il codice")
verifica("codice con il programma e i test: niente",
         cosa_ha_fatto(lav_c, {"file": ["rimborso.py", "test_rimborso.py"]}) == "")
verifica("codice senza test: «ha scritto il codice senza arrivare a provarlo»",
         cosa_ha_fatto(lav, {"file": ["estensione.py", "manifesto.json"]})
         == "ha scritto il codice senza arrivare a provarlo")


svc.close()
fake.ferma()
print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
