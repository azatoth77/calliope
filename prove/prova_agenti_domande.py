import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Prova a secco delle domande dell'agente a metà lavoro e dei file della persona dati
all'agente (calliope/agenti/servizio.py, file_utente.py, tools/agenti.py, 03/10/2026).

Niente DGX né Ollama vero: l'agente è un Ollama FINTO (prove/ollama_finto.py) con un copione,
il PC è un PC finto (prove/pc_finto.py) con file veri in una cartella temporanea, il satellite
è vero (server e client WebSocket su 127.0.0.1, protocollo 2) con il PC finto sul satellite.

Domande:
- codice: l'agente scrive un file e chiede un dato → lavoro in_attesa, sandbox e conversazione
  conservate, annuncio con la domanda e azione in sospeso (RISPOSTA_MSG); risposta nel turno
  dopo (Brain con una voce finta: il modello vede la domanda e chiama lavori_rispondi), il
  lavoro riprende dal punto in cui era; il tempo d'attesa non conta nel tetto dei minuti;
- modello di documento: risposta più tardi, per titolo («il verbale»), i campi già compilati
  restano;
- persona sbagliata (rifiutata, regola nel registro), chi amministra sì; più lavori in attesa;
- scadenza: si chiude da solo e lo dice; tetto delle domande; annullo di un lavoro in attesa;
- la voce non aspetta mai (tool in pochi millisecondi anche con l'agente occupato).
File:
- in locale: ricerca, conferma esplicita, copia nella sandbox, risultato «backup
  (corretto).py», originale intatto; PDF e Excel letti per i lavori di documento; più file
  trovati («Quale mando?»); estensione vietata; file troppo grande; permessi (proprietari);
- con il satellite: copia a pezzi con lo SHA-256, risultato consegnato al portatile come file
  nuovo, checksum sbagliato, troppo grande, estensione vietata e maniglia inventata rifiutate
  dal satellite, satellite scollegato, satellite che non sa mandare file; la conferma risponde
  subito anche con il PC lento.
"""

import json
import queue
import re
import tempfile
import threading
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.agenti.file_utente import nome_risultato, testo_del_file
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.consegna import LocalDelivery, RemoteDelivery
from calliope.documenti.formato import FORMATI
from calliope.pc.remoto import PCNonCollegato, RemotePCExecutor
from calliope.satellite.archivio import ArchivioSatelliti
from calliope.satellite.client import Satellite
from calliope.satellite.esecutore import EsecutoreSatellite
from calliope.satellite.server import ServerSatelliti
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from ollama_finto import FakeOllama
from pc_finto import FakePC

TMP = Path(tempfile.mkdtemp(prefix="calliope-domande-"))
MODELLO = "qwen3.6:35b"
errori = 0
# «La voce non aspetta» (03/10): le chiamate della voce costano meno di un millisecondo, e
# ciò che non devono aspettare (un pezzo dello stream, il tunnel, il portatile lento, la
# copia di un file) dura dai 0,2 s in su. Con 50 ms la prova falliva sotto carico (più
# prove insieme: «la delega risponde subito  50.5 ms», dove c'è anche l'avvio di un thread)
SUBITO_S = 0.15
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def aspetta(cond, s=10.0):
    fine_ = time.monotonic() + s
    while time.monotonic() < fine_:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


def call(name, args=None):
    return {"name": name, "arguments": args or {}}


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    p = {"Dario": Prof("dario-id", "Dario"), "Bianca": Prof("bianca-id", "Bianca"),
         "Marco": Prof("marco-id", "Marco")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


LIVELLO = {"Dario": "amministra", "Bianca": "familiare", "Marco": "familiare"}


class SpeakerCtx:
    def __init__(self, name, how="voce"):
        self.current_speaker, self.from_session = name, False
        self.current_level = LIVELLO.get(name, "ospite")
        self.identified_by = how


def cfg_base(url, **kw) -> Config:
    cfg = Config()
    cfg.agenti_url = url
    cfg.agenti_modello = MODELLO
    cfg.agenti_risultati = str(TMP / "risultati")
    cfg.agenti_sandbox = str(TMP / "sandbox")
    # Il codice dell'agente gira solo con il motore scelto a mano (03/10): qui il processo
    cfg.agenti_sandbox_motore = "processo"
    cfg.agenti_modelli = str(TMP / "modelli")
    cfg.llm_native_url = "http://127.0.0.1:9"     # la voce altrove: niente contesa
    cfg.agenti_esecuzione_s = 15.0
    cfg.pc_proprietari = ["Marco"]
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def servizio(cfg, **kw) -> Lavori:
    return Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI, **kw)


def fine(svc, s=15.0):
    try:
        return svc.done.get(timeout=s)
    except queue.Empty:
        return None


class Banco:
    """Registro dei tool e contesto per una persona e un turno."""

    def __init__(self, cfg, svc, pcs=None):
        self.cfg, self.svc, self.pcs = cfg, svc, pcs
        self.reg = build_registry(pc=pcs, documenti=FORMATI, agenti=True)
        self.regole: list = []

    def tool(self, name, args, chi, turno, testo=""):
        sc = SpeakerCtx(chi)
        ctx = ToolContext(cfg=self.cfg, speakers=Speakers(), speaker_ctx=sc, speaker=None,
                          lavori=self.svc, pc=self.pcs, turno=turno, user_text=testo)
        t0 = time.perf_counter()
        out = json.loads(self.reg.call(name, args, ctx, sc.current_level))
        self.regole = list(ctx.regole)
        return out, time.perf_counter() - t0


fake = FakeOllama(modelli=(MODELLO,)).avvia()

# ═══════════════════════════ 1. domanda a metà di un lavoro di codice ═══════════════════════════
sezione("codice: domanda, risposta nel turno dopo, ripresa")
cfg = cfg_base(fake.url, agenti_tempo_max_min=0.03)       # 1,8 s di lavoro al massimo
svc = servizio(cfg)
banco = Banco(cfg, svc)
nomi = [s["function"]["name"] for s in banco.reg.all_schemas()]
verifica("lavori_rispondi registrato (familiari e chi amministra)", "lavori_rispondi" in nomi
         and "lavori_rispondi" not in [s["function"]["name"]
                                       for s in banco.reg.schemas_for("ospite")])
verifica("senza PC delega_lavoro non ha il parametro file",
         "file" not in next(s for s in banco.reg.all_schemas()
                            if s["function"]["name"] == "delega_lavoro")["function"][
             "parameters"]["properties"])
ripresa = {}


def dopo_risposta(body):
    ripresa["messaggi"] = body["messages"]
    return {"tool_calls": [call("consegna", {"riassunto": "Ho scritto la funzione per il CSV.",
                                             "esito": "fatto"})]}


fake.copione = [
    {"tool_calls": [call("scrivi_file", {"percorso": "leggi_csv.py",
                                         "contenuto": "def leggi(riga):\n    return riga\n"})]},
    {"tool_calls": [call("consegna", {"riassunto": "Mi manca un dato.", "esito": "mancano_dati",
                                      "domanda": "Che separatore usa il file CSV"})]},
    dopo_risposta]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi una funzione che legge il CSV delle spese", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
verifica("il lavoro resta in attesa, non finisce", item and item["stato"] == "in_attesa"
         and lav.stato == "in_attesa", str(item and item["stato"]))
verifica("annuncio con la domanda, che finisce con «?»", item and item["messaggio"].startswith(
    "Dario, per «") and item["messaggio"].endswith("che separatore usa il file CSV?"),
         str(item and item["messaggio"]))
off = (item or {}).get("in_sospeso") or {}
verifica("azione in sospeso per lavori_rispondi con il testo della domanda",
         off.get("tool") == "lavori_rispondi" and "Domanda in sospeso" in off.get("messaggio", "")
         and f'lavoro="{lav.id}"' in off.get("messaggio", ""), str(off)[:200])
verifica("sandbox e conversazione conservate durante l'attesa",
         lav.sandbox is not None and (lav.sandbox.root / "leggi_csv.py").is_file()
         and lav.contesto.get("tipo") == "codice")
verifica("lavoro.json scritto con la domanda", lav.cartella and json.loads(
    (Path(lav.cartella) / "lavoro.json").read_text(encoding="utf-8"))["stato"] == "in_attesa")
out, dt = banco.tool("lavori_stato", {}, "Dario", 2)
verifica("lavori_stato: aspetta una risposta, con la domanda e l'azione in sospeso",
         "aspetta una risposta" in out["risposta_finale"] and out.get("in_sospeso"),
         out["risposta_finale"])

# La voce: annuncio nella storia, poi «punto e virgola» → il modello vede la domanda
voce = FakeOllama(modelli=("gemma4:e4b-it-qat",)).avvia()
cfg_v = cfg_base(fake.url)
cfg_v.llm_native_url = voce.url
ctx_v = ToolContext(cfg=cfg_v, speakers=Speakers(), speaker_ctx=SpeakerCtx("Dario", "breve"),
                    speaker=None, lavori=svc)
brain = Brain(cfg_v, banco.reg, ctx_v)
brain.record_announcement(item["messaggio"], item.get("in_sospeso"))
visto = {}


def risponde_alla_domanda(body):
    sis = [m["content"] for m in body["messages"] if m["role"] == "system"]
    visto["sospeso"] = [x for x in sis if x.startswith("Domanda in sospeso")]
    m = re.search(r'lavoro="(L\d+)"', visto["sospeso"][-1] if visto["sospeso"] else "")
    return {"tool_calls": [call("lavori_rispondi", {"lavoro": m.group(1) if m else "",
                                                    "risposta": "punto e virgola"})]}


voce.copione = [risponde_alla_domanda]
time.sleep(2.0)            # l'attesa supera il tetto dei minuti del lavoro: non deve contare
t0 = time.perf_counter()
risposta = "".join(brain.stream_reply("Punto e virgola.", "amministra"))
dt = time.perf_counter() - t0
verifica("il modello della voce vede la domanda in sospeso (non «se acconsente»)",
         visto.get("sospeso") and "risponde alla domanda" in visto["sospeso"][-1]
         and "acconsente" not in visto["sospeso"][-1])
verifica("risposta nel turno dopo: «Grazie, … riprendo»", risposta.startswith("Grazie")
         and "riprendo" in risposta, risposta)
item = fine(svc)
verifica("il lavoro riprende e finisce", item and item["stato"] == "fatto",
         str(item and item["messaggio"]))
msgs = ripresa.get("messaggi") or []
verifica("ripresa dal punto in cui era: la conversazione dell'agente c'è tutta",
         any(m.get("role") == "tool" and m.get("tool_name") == "scrivi_file" for m in msgs)
         and "punto e virgola" in msgs[-1]["content"] and "Che separatore" in msgs[-1]["content"],
         str([m.get("role") for m in msgs]))
verifica("il tempo d'attesa non conta nel tetto dei minuti", lav.attesa_s >= 1.9
         and lav.stato == "fatto", f"attesa {lav.attesa_s:.1f} s")
verifica("i file del lavoro nella stessa cartella", Path(lav.cartella, "leggi_csv.py").is_file())
meta = json.loads((Path(lav.cartella) / "lavoro.json").read_text(encoding="utf-8"))
verifica("lavoro.json: domande e risposte", meta["domande"] == [
    ["Che separatore usa il file CSV?", "punto e virgola"]], str(meta.get("domande")))
voce.ferma()
svc.close()

# ═══════════════════════════ 2. modello di documento: risposta più tardi ═══════════════════════
sezione("modello di documento: risposta più tardi, per titolo; persone")
(TMP / "modelli").mkdir(exist_ok=True)
(TMP / "modelli" / "verbale.json").write_text(json.dumps({
    "nome": "verbale", "titolo": "Verbale di assemblea", "formato": "word",
    "campi": {"condominio": {"descrizione": "il nome del condominio"},
              "data": {"descrizione": "la data dell'assemblea", "tipo": "data"}},
    "documento": {"titolo": "Verbale {{condominio}}", "blocchi": [
        {"tipo": "titolo", "testo": "Verbale del condominio {{condominio}}"},
        {"tipo": "paragrafo", "testo": "Il giorno {{data}} si è riunita l'assemblea."}]}},
    ensure_ascii=False), encoding="utf-8")
cfg = cfg_base(fake.url)
svc = servizio(cfg)
banco = Banco(cfg, svc)
seconda = {}


def compila(body):
    seconda["user"] = body["messages"][-1]["content"]
    return {"content": json.dumps({"condominio": None, "data": "3 ottobre 2026"})}


fake.copione = [{"content": json.dumps({"condominio": "Le Querce", "data": None})}, compila]
lav = svc.nuovo("documento", "Compila il verbale del condominio Le Querce", "bianca-id", "Bianca",
                modello="verbale")
svc.avvia(lav)
item = fine(svc)
verifica("dati mancanti: in attesa, la domanda dice cosa manca", item
         and item["stato"] == "in_attesa" and "data dell'assemblea" in item["messaggio"]
         and item["messaggio"].endswith("?"), str(item and item["messaggio"]))
out, _ = banco.tool("lavori_rispondi", {"lavoro": "verbale", "risposta": "il 3 ottobre"},
                    "Marco", 5)
verifica("un altro familiare non risponde: rifiutato, NON eseguito, regola nel registro",
         out.get("ok") is False and "NON" in out.get("fatto", "")
         and "lavori_risposta_altrui" in banco.regole and lav.stato == "in_attesa",
         out.get("risposta_finale"))
out, _ = banco.tool("lavori_rispondi", {"risposta": "il 3 ottobre"}, "Dario", 6)
verifica("senza nominare il lavoro, chi non l'ha chiesto ma amministra: va",
         out.get("ok") and lav.stato in ("in_coda", "in_corso", "fatto"), out["risposta_finale"])
item = fine(svc)
verifica("il verbale si compila con i campi di prima più la risposta",
         item and item["stato"] == "fatto" and list(Path(item["cartella"]).glob("*.docx"))
         and "Le Querce" in seconda.get("user", "") and "il 3 ottobre" in seconda.get("user", ""),
         str(item and item["messaggio"]))

# Più tardi, per titolo, dalla persona che l'ha chiesto; due lavori in attesa
fake.copione = [{"content": json.dumps({"condominio": None, "data": None})},
                {"tool_calls": [call("scrivi_file", {"percorso": "a.py", "contenuto": "x = 1\n"})]},
                {"tool_calls": [call("consegna", {"riassunto": "Manca.", "esito": "mancano_dati",
                                                  "domanda": "Quale cartella devo usare?"})]}]
l_v = svc.nuovo("documento", "Compila il verbale", "bianca-id", "Bianca", modello="verbale")
svc.avvia(l_v)
fine(svc)
l_c = svc.nuovo("codice", "Scrivi uno script di backup delle foto", "bianca-id", "Bianca")
svc.avvia(l_c)
fine(svc)
out, _ = banco.tool("lavori_rispondi", {"risposta": "Le Querce"}, "Bianca", 7)
verifica("due lavori in attesa e nessun nome: «A quale rispondi?»", out.get("ok") is False
         and out["risposta_finale"].endswith("A quale rispondi?")
         and l_v.stato == l_c.stato == "in_attesa", out["risposta_finale"])
fake.copione = [{"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]}]
out, dt = banco.tool("lavori_rispondi", {"lavoro": "lo script del backup",
                                         "risposta": "la cartella Immagini"}, "Bianca", 8)
verifica("«per lo script del backup: …» trova il lavoro giusto, subito", out.get("ok")
         and l_c.stato != "in_attesa" and l_v.stato == "in_attesa" and dt < SUBITO_S,
         f"{out['risposta_finale']} ({dt * 1000:.1f} ms)")
item = fine(svc)
verifica("e il lavoro finisce", item and item["id"] == l_c.id and item["stato"] == "fatto")
out, _ = banco.tool("lavori_annulla", {}, "Bianca", 9)
verifica("annullo di un lavoro in attesa: fermato, nessun annuncio",
         out.get("ok") and l_v.stato == "annullato" and svc.done.empty(), out["risposta_finale"])
out, _ = banco.tool("lavori_rispondi", {"risposta": "x"}, "Bianca", 10)
verifica("nessun lavoro in attesa: lo dice, NON eseguito", out.get("ok") is False
         and "Non ho lavori" in out["risposta_finale"])
svc.close()

# ═══════════════════════════ 3. scadenza, tetto delle domande, voce libera ═══════════════════════
sezione("scadenza e tetto delle domande")
cfg = cfg_base(fake.url, agenti_attesa_risposta_min=0.01)        # 0,6 s
svc = servizio(cfg)
banco = Banco(cfg, svc)
fake.copione = [{"tool_calls": [call("scrivi_file", {"percorso": "b.py", "contenuto": "y = 2\n"})]},
                {"tool_calls": [call("consegna", {"riassunto": "Manca.", "esito": "mancano_dati",
                                                  "domanda": "Per chi è?"})]}]
lav = svc.nuovo("codice", "Scrivi un programma per il compleanno", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
verifica("domanda annunciata", item and item["stato"] == "in_attesa")
item = fine(svc, 5)
verifica("nessuna risposta in tempo: si chiude da solo e lo dice", item
         and item["stato"] == "scaduto" and "ho chiuso" in item["messaggio"]
         and "chiedimelo di nuovo" in item["messaggio"], str(item and item["messaggio"]))
verifica("i file fatti fin lì restano nella cartella", Path(lav.cartella, "b.py").is_file()
         and lav.sandbox is None)
out, _ = banco.tool("lavori_rispondi", {"risposta": "per Bianca"}, "Dario", 3)
verifica("risposta dopo la scadenza: niente da riprendere", out.get("ok") is False)
svc.close()

cfg = cfg_base(fake.url, agenti_domande_max=1)
svc = servizio(cfg)
banco = Banco(cfg, svc)
fake.copione = [{"tool_calls": [call("consegna", {"riassunto": "Manca.", "esito": "mancano_dati",
                                                  "domanda": "Prima domanda?"})]},
                {"tool_calls": [call("consegna", {"riassunto": "Manca ancora.",
                                                  "esito": "mancano_dati",
                                                  "domanda": "Seconda domanda?"})]}]
lav = svc.nuovo("codice", "Scrivi un programma", "dario-id", "Dario")
svc.avvia(lav)
fine(svc)
banco.tool("lavori_rispondi", {"risposta": "sì"}, "Dario", 2)
item = fine(svc)
verifica("oltre agenti_domande_max: il lavoro si chiude con la domanda (come prima)",
         item and item["stato"] == "mancano_dati" and "Seconda domanda" in item["messaggio"],
         str(item and item["messaggio"]))

# La voce non aspetta: l'agente sta generando lentamente, i tool rispondono subito
fake.ritardo_pezzo, fake.pezzi = 0.2, 20
fake.copione = [{"content": "z" * 100 + "\nRIASSUNTO: fatto."}]
lento = svc.nuovo("altro", "Un lavoro lento", "dario-id", "Dario")
svc.avvia(lento)
aspetta(lambda: lento.stato == "in_corso", 3)
tempi = []
for nome, args in (("lavori_stato", {}), ("lavori_rispondi", {"risposta": "x"})):
    _, dt = banco.tool(nome, args, "Dario", 4)
    tempi.append(dt)
verifica("con l'agente occupato i tool rispondono in pochi millisecondi", max(tempi) < SUBITO_S,
         ", ".join(f"{t * 1000:.1f} ms" for t in tempi))
svc.annulla("dario-id")
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
svc.close()

# ═══════════════════════════ 4. i file della persona, in locale ═══════════════════════════════
sezione("file della persona: PC locale")
CART = TMP / "pc"
CART.mkdir()
BACKUP = "import shutil\n\ndef copia(a, b):\n    shutil.copy(a, b)\n    return Tru\n"
(CART / "backup.py").write_text(BACKUP, encoding="utf-8")
(CART / "foto mare.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 100)
(CART / "grande.txt").write_text("a" * 30_000, encoding="utf-8")
from fpdf import FPDF  # noqa: E402
pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", size=12)
pdf.multi_cell(0, 8, "Contratto di affitto. Il canone mensile e di 800 euro, durata 4 anni.")
pdf.output(str(CART / "contratto affitto.pdf"))
import openpyxl  # noqa: E402
for anno, importo in (("2025", 120), ("2026", 340)):
    wb = openpyxl.Workbook()
    wb.active.append(["Voce", "Importo"])
    wb.active.append(["Luce", importo])
    wb.save(CART / f"spese {anno}.xlsx")


def voce_file(nome, giorni):
    p = CART / nome
    return {"nome": p.stem, "estensione": p.suffix.lstrip("."), "percorso": str(p),
            "modificato": f"2026-09-{30 - giorni:02d}T10:00"}


FILE = [voce_file("backup.py", 1), voce_file("foto mare.jpg", 2), voce_file("grande.txt", 3),
        voce_file("contratto affitto.pdf", 4), voce_file("spese 2025.xlsx", 6),
        voce_file("spese 2026.xlsx", 5)]
pc = FakePC(file=FILE)
pcs = {"portatile": pc}
verifica("testo di un PDF (pypdf) e di un Excel (openpyxl) per l'agente",
         "800 euro" in testo_del_file("c.pdf", (CART / "contratto affitto.pdf").read_bytes())
         and "Luce ; 340" in testo_del_file("s.xlsx", (CART / "spese 2026.xlsx").read_bytes()))
verifica("nome del risultato: «backup (corretto).py», «spese (modificato).xlsx»",
         nome_risultato("backup.py", "codice") == "backup (corretto).py"
         and nome_risultato("spese.xlsx", "codice") == "spese (modificato).xlsx")
cfg = cfg_base(fake.url, agenti_file_max_mb=0.02)          # 20 KB
svc = servizio(cfg)
banco = Banco(cfg, svc, pcs)
schema = next(s for s in banco.reg.all_schemas() if s["function"]["name"] == "delega_lavoro")
verifica("con il PC delega_lavoro ha il parametro file", "file" in schema["function"][
    "parameters"]["properties"])

out, _ = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Correggi lo script",
                                      "file": "backup.py"}, "Bianca", 1)
verifica("familiare non proprietario: niente file (prima il codice: solo chi amministra)",
         out.get("ok") is False and not svc.lavori, out.get("risposta_finale") or out.get("motivo"))
out, _ = banco.tool("delega_lavoro", {"tipo": "documento", "compito": "Riassumimi il contratto",
                                      "file": "contratto"}, "Bianca", 1)
verifica("familiare non proprietario del PC: il file non lascia il PC, regola nel registro",
         out.get("ok") is False and "proprietario" in out.get("motivo", "")
         and "lavori_file_permesso" in banco.regole and not svc.lavori, str(out)[:160])
out, _ = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Guarda la foto",
                                      "file": "foto mare.jpg"}, "Dario", 1)
verifica("estensione vietata: rifiutata prima di cercare", out.get("ok") is False
         and ".jpg" in out["risposta_finale"] and pc.ultima_ricerca is None,
         out["risposta_finale"])

CODICE_FIX = "import shutil\n\ndef copia(a, b):\n    shutil.copy(a, b)\n    return True\n"
primo = {}


def legge(body):
    primo["user"] = body["messages"][1]["content"]
    return {"tool_calls": [call("leggi_file", {"percorso": "backup.py"})]}


fake.copione = [legge,
                {"tool_calls": [call("scrivi_file", {"percorso": "backup.py",
                                                     "contenuto": CODICE_FIX})]},
                {"tool_calls": [call("consegna", {"riassunto": "Ho corretto il valore restituito.",
                                                  "esito": "fatto"})]}]
fake.richieste.clear()
out, _ = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Correggi lo script backup",
                                      "file": "backup.py"}, "Dario", 2)
off = out.get("in_sospeso") or {}
verifica("conferma esplicita: «Mando una copia dello script Python «backup»… Procedo?»",
         out["risposta_finale"].startswith("Mando una copia dello script Python «backup»")
         and "l'originale non lo tocco" in out["risposta_finale"]
         and out["risposta_finale"].endswith("Procedo?") and off.get("tool") == "delega_lavoro"
         and not svc.lavori and not fake.richieste, out["risposta_finale"])
out, dt = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Correggi lo script backup",
                                       "proposta": off["argomenti"]["proposta"]}, "Dario", 3)
verifica("al «sì» parte, e la voce non aspetta la copia", out.get("ok") and dt < SUBITO_S,
         f"{dt * 1000:.1f} ms")
item = fine(svc)
lav = svc.lavori[-1]
dest = Path(item["cartella"]) if item else TMP
verifica("l'agente lavora sulla copia nella sandbox (il nome nel compito)",
         "«backup.py»" in primo.get("user", "") and lav.input["nome"] == "backup.py")
verifica("risultato come file nuovo «backup (corretto).py», originale intatto",
         item and item["stato"] == "fatto" and (dest / "backup (corretto).py").read_text(
             encoding="utf-8") == CODICE_FIX
         and (CART / "backup.py").read_text(encoding="utf-8") == BACKUP,
         str(item and item["messaggio"]))
verifica("l'annuncio dice il file nuovo e che l'originale non è toccato",
         item and "«backup (corretto)»" in item["messaggio"]
         and "l'originale non l'ho toccato" in item["messaggio"], str(item and item["messaggio"]))

# PDF per un lavoro di documento (il testo nella richiesta, il formato dal file)
DOC = {"titolo": "Riassunto contratto", "blocchi": [
    {"tipo": "titolo", "testo": "Riassunto del contratto"},
    {"tipo": "paragrafo", "testo": "Il canone è di 800 euro al mese per 4 anni."}]}
fake.copione = [{"content": "Bozza del riassunto."}, {"content": json.dumps(DOC)}]
fake.richieste.clear()
out, _ = banco.tool("delega_lavoro", {"tipo": "documento", "compito": "Riassumimi il contratto",
                                      "file": "contratto"}, "Marco", 4)
verifica("proprietario del PC (familiare): proposta con «del PDF»", "del PDF «contratto affitto»"
         in out.get("risposta_finale", ""), out.get("risposta_finale"))
banco.tool("delega_lavoro", {"tipo": "documento", "compito": "Riassumimi il contratto",
                             "proposta": out["in_sospeso"]["argomenti"]["proposta"]}, "Marco", 5)
item = fine(svc)
verifica("il testo del PDF arriva all'agente", fake.richieste
         and "800 euro" in fake.richieste[0]["messages"][-1]["content"])
verifica("riassunto fatto, nel formato del file (PDF)", item and item["stato"] == "fatto"
         and list(Path(item["cartella"]).glob("Riassunto contratto.pdf")),
         str(item and item["messaggio"]))

# Più file trovati: «Quale mando all'agente?», poi il numero
DOC2 = {"titolo": "Spese 2026", "fogli": [{"nome": "Spese", "colonne": ["Voce", "Importo", "Note"],
                                          "righe": [["Luce", 340, "bolletta"]]}]}
fake.copione = [{"content": json.dumps(DOC2)}]
fake.richieste.clear()
out, _ = banco.tool("delega_lavoro", {"tipo": "documento", "compito": "Aggiungi una colonna Note",
                                      "file": "spese"}, "Dario", 6)
off = out.get("in_sospeso") or {}
verifica("due file trovati: «Quale mando all'agente?» con i numeri", "Quale mando all'agente?"
         in out.get("risposta_finale", "") and off.get("domanda") == "Quale mando all'agente?"
         and "1 = " in off.get("cosa", ""), out.get("risposta_finale"))
lid = re.search(r'proposta="(L\d+)"', off.get("argomenti", "")).group(1)
out, _ = banco.tool("delega_lavoro", {"tipo": "documento", "compito": "Aggiungi una colonna Note",
                                      "proposta": lid}, "Dario", 7)
verifica("senza dire quale: lo richiede", "Quale mando" in out.get("risposta_finale", ""))
out, _ = banco.tool("delega_lavoro", {"tipo": "documento", "compito": "Aggiungi una colonna Note",
                                      "proposta": lid, "file": "il primo"}, "Dario", 8)
item = fine(svc)
# Il più recente prima: «spese 2026» è il primo risultato
verifica("scelto il primo: Excel con lo stesso nome → «Spese 2026 (modificato).xlsx»",
         item and item["stato"] == "fatto"
         and list(Path(item["cartella"]).glob("Spese 2026 (modificato).xlsx"))
         and "Luce ; 340" in fake.richieste[0]["messages"][-1]["content"],
         str(item and item["messaggio"]))

# Troppo grande
out, _ = banco.tool("delega_lavoro", {"tipo": "altro", "compito": "Leggi il file grande",
                                      "file": "grande.txt"}, "Dario", 9)
banco.tool("delega_lavoro", {"tipo": "altro", "compito": "Leggi il file grande",
                             "proposta": out["in_sospeso"]["argomenti"]["proposta"]}, "Dario", 10)
item = fine(svc)
verifica("file troppo grande: il lavoro non parte e lo dice", item and item["stato"] == "errore"
         and "troppo grande" in item["messaggio"], str(item and item["messaggio"]))
pc.locked = True
out, _ = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Correggi",
                                      "file": "backup.py"}, "Dario", 11)
verifica("schermo bloccato: niente ricerca, niente file", out.get("ok") is False
         and "bloccato" in json.dumps(out, ensure_ascii=False))
pc.locked = False
svc.close()

# ═══════════════════════════ 5. i file della persona, con il satellite ═══════════════════════
sezione("file della persona: satellite (copia a pezzi, risultato al portatile)")
import prova_satellite as T  # noqa: E402


class Rilevatore:
    def reset(self):
        pass

    def process(self, frame):
        return None


class PCLento(FakePC):
    ritardo = 0.0

    def _leggi(self, percorso, max_byte):
        time.sleep(self.ritardo)
        return super()._leggi(percorso, max_byte)


(TMP / "srv").mkdir()
(TMP / "sat").mkdir()
cfg_srv = T.cfg_prova(TMP / "srv")
arch = ArchivioSatelliti(cfg_srv.memory_db)
srv = ServerSatelliti(cfg_srv, arch, log=lambda m: None).avvia()
srv.avviato.set()
_, token = arch.crea_con_token("studio", ruolo="pc")
cfg_sat = T.cfg_prova(TMP / "sat", satellite_server=f"ws://127.0.0.1:{srv.port}")
cfg_sat.satellite_credenziali = str(TMP / "sat" / "cred.json")
Path(cfg_sat.satellite_credenziali).write_text(json.dumps({"token": token}), encoding="utf-8")
pc_sat = PCLento(file=FILE)
portatile = TMP / "portatile" / "Documenti" / "Calliope"
ese = EsecutoreSatellite(pc_sat, LocalDelivery(portatile), "portatile", log=lambda m: None)
sat = Satellite(cfg_sat, sorgente=lambda **kw: T.MicFinto(T.Scena(), **kw),
                apri_uscita=T.Casse().flusso, log=lambda m: None, rilevatore=Rilevatore(),
                esecutore=ese)
threading.Thread(target=sat.esegui, daemon=True).start()
verifica("satellite collegato, sa mandare file (invio nel «ciao»)", aspetta(
    lambda: srv.attivo_pronto() is not None and (srv.attivo_pronto().esecutore or {}).get(
        "invio"), 10))
remoto = RemotePCExecutor(srv, "portatile", [], 5, timeout_s=2.0)
pcs = {"portatile": remoto}
cfg = cfg_base(fake.url, agenti_file_max_mb=0.02)
svc = servizio(cfg, consegna=RemoteDelivery(srv, LocalDelivery(TMP / "server"), "portatile"))
banco = Banco(cfg, svc, pcs)

fake.copione = [{"tool_calls": [call("scrivi_file", {"percorso": "backup.py",
                                                     "contenuto": CODICE_FIX})]},
                {"tool_calls": [call("consegna", {"riassunto": "Ho corretto lo script.",
                                                  "esito": "fatto"})]}]
pc_sat.ritardo = 0.8
out, _ = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Correggi lo script backup",
                                      "file": "backup.py"}, "Dario", 1)
verifica("ricerca sul satellite e proposta", out["risposta_finale"].endswith("Procedo?"),
         out["risposta_finale"])
out, dt = banco.tool("delega_lavoro", {"tipo": "codice", "compito": "Correggi lo script backup",
                                       "proposta": out["in_sospeso"]["argomenti"]["proposta"]},
                     "Dario", 2)
verifica("al «sì» la voce non aspetta il portatile lento (0,8 s)", out.get("ok") and dt < SUBITO_S,
         f"{dt * 1000:.1f} ms")
item = fine(svc)
lav = svc.lavori[-1]
verifica("la copia arriva a pezzi con lo SHA-256 (uguale all'originale)",
         lav.input and lav.input["dati"] == (CART / "backup.py").read_bytes()
         and aspetta(lambda: ese.file_mandati == 1, 3))
verifica("il risultato torna al portatile come file nuovo (uno script come .py.txt, 03/10), l'originale intatto",
         item and item["stato"] == "fatto"
         and (portatile / "backup (corretto).py.txt").read_text(encoding="utf-8") == CODICE_FIX
         and (CART / "backup.py").read_text(encoding="utf-8") == BACKUP,
         str(item and item["messaggio"]))
verifica("l'annuncio dice dove: la cartella Calliope dei Documenti del portatile",
         item and "Documenti del portatile" in item["messaggio"], str(item and item["messaggio"]))
pc_sat.ritardo = 0.0

c = srv.attivo_pronto()
remoto.cerca_file("dario-id", "contratto")
it = remoto.risultato("dario-id", 1)["item"]
ese.rovina_invio = True
r = remoto.copia_file(it, 100_000, ["pdf"])
verifica("checksum diverso: rifiutato dal server", r.get("ok") is False
         and "checksum" in r.get("errore", ""), str(r.get("errore")))
ese.rovina_invio = False
r = remoto.copia_file(it, 100_000, ["pdf"])
verifica("lo stesso file, integro", r.get("ok") and r["dati"] == (CART / "contratto affitto.pdf")
         .read_bytes() and r["nome"] == "contratto affitto.pdf")
r = remoto.copia_file(it, 200, ["pdf"])
verifica("troppo grande per il massimo chiesto: rifiutato dal satellite",
         r.get("ok") is False and r.get("troppo_grande"), str(r.get("errore")))
remoto.cerca_file("dario-id", "foto")
it_jpg = remoto.risultato("dario-id", 1)["item"]
r = c.ricevi_file(it_jpg["percorso"], 100_000, ["jpg", "pdf"], 5.0)
verifica("estensione fuori dall'elenco del satellite: rifiutata anche se il server la chiede",
         r.get("ok") is False and ".jpg" in r.get("errore", ""), str(r.get("errore")))
r = c.ricevi_file("maniglia-inventata", 100_000, ["pdf"], 5.0)
verifica("maniglia inventata: nessun file", r.get("ok") is False and r.get("serve_ricerca"),
         str(r.get("errore")))
pc_sat.locked = True
r = c.ricevi_file(it["percorso"], 100_000, ["pdf"], 5.0)
verifica("schermo bloccato sul portatile: nessun file", r.get("ok") is False
         and r.get("bloccato"), str(r.get("errore")))
pc_sat.locked = False

# Satellite che non sa mandare file (aggiornato solo a metà) e satellite scollegato
c.esecutore["invio"] = False
try:
    remoto.copia_file(it, 100_000, ["pdf"])
    msg = ""
except PCNonCollegato as e:
    msg = str(e)
verifica("satellite senza invio: «va aggiornato»", "aggiornato" in msg, msg)
c.esecutore["invio"] = True
fake.copione = [{"content": "Ok.\nRIASSUNTO: Fatto."}]
out, _ = banco.tool("delega_lavoro", {"tipo": "altro", "compito": "Riassumi",
                                      "file": "contratto"}, "Dario", 20)
lid = out["in_sospeso"]["argomenti"]["proposta"]
sat.ferma()
aspetta(lambda: srv.attivo_pronto() is None, 5)
banco.tool("delega_lavoro", {"tipo": "altro", "compito": "Riassumi", "proposta": lid},
           "Dario", 21)
item = fine(svc, 20)
verifica("satellite scollegato al momento della copia: il lavoro non parte e lo dice",
         item and item["stato"] == "errore" and "non ho potuto prendere" in item["messaggio"],
         str(item and item["messaggio"]))
svc.close()
srv.ferma()
fake.ferma()

print("\nTutto a posto." if not errori else f"\n{errori} errori")
sys.exit(1 if errori else 0)
