import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Prova a secco dei lavori dell'agente che sopravvivono a un riavvio di Calliope
(calliope/agenti/ripresa.py, servizio.py, tools/agenti.py, 06/10/2026).

Caso vero della DGX: alle 16:56 il lavoro «gioco memory da giocare sullo schermo» (codice), alle
17:07 un `calliope aggiorna` riavvia il servizio, il lavoro muore e dopo il riavvio Calliope
non dice niente («Non ho lavori in corso.»). Qui il riavvio è un servizio dei lavori chiuso e
ricreato nello stesso processo, con il pid del file cambiato (come un processo nuovo).

- lo stato su disco (in_corso.json) a ogni cambio, con la sandbox e la cartella;
- all'avvio il lavoro in corso diventa interrotto: annuncio alla persona con «Lo rifaccio?» e
  azione in sospeso; lavoro_stato lo elenca; gli id nuovi non ripetono quelli di prima;
- «sì» detto alla voce (Brain con una voce finta, annuncio con la fonte «agente» come nel
  ciclo): lavoro nuovo con lo stesso compito, la stessa cartella e la sandbox con i file già
  scritti (l'agente li vede, con il vincolo della ripresa); finisce e lo dice;
- «no»: niente riparte, resta nell'elenco, e al riavvio dopo non si annuncia di nuovo;
- un'altra persona non può dire «sì» al posto suo;
- scadenza: interrotto da più di agenti_interrotti_annuncio_h ore → solo nell'elenco, senza
  domanda; da più di un giorno → sparisce;
- un lavoro su un file della persona: annuncio senza domanda («chiedimelo di nuovo»);
- due lavori della stessa persona (in corso e in coda): un annuncio, «Li rifaccio?», e al «sì»
  ripartono tutti e due;
- un lavoro in attesa di una risposta: dopo il riavvio la domanda si ripete, la risposta lo fa
  ripartire con la conversazione dell'agente di prima; se la conversazione non si poteva
  salvare diventa interrotto;
- un file dello stato rovinato non ferma l'avvio.
"""

import json
import queue
import re
import tempfile
import threading
import time
from pathlib import Path

from calliope.agenti import Lavori, carica, ripresa
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from ollama_finto import FakeOllama

TMP = Path(tempfile.mkdtemp(prefix="calliope-riavvio-"))
MODELLO = "qwen3.6:35b"
errori = 0
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
    p = {"Mario": Prof("mario-id", "Mario"), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


LIVELLO = {"Mario": "amministra", "Bianca": "familiare"}


class SpeakerCtx:
    def __init__(self, name, how="voce"):
        self.current_speaker, self.from_session = name, False
        self.current_level = LIVELLO.get(name, "ospite")
        self.identified_by = how


def cfg_base(url, nome, **kw) -> Config:
    cfg = Config()
    cfg.agenti_url = url
    cfg.agenti_modello = MODELLO
    cfg.agenti_risultati = str(TMP / nome / "risultati")
    cfg.agenti_sandbox = str(TMP / nome / "sandbox")
    cfg.agenti_sandbox_motore = "processo"
    cfg.agenti_modelli = str(TMP / "modelli")
    cfg.llm_native_url = "http://127.0.0.1:9"
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def servizio(cfg) -> Lavori:
    return Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI)


def fine(svc, s=15.0):
    try:
        return svc.done.get(timeout=s)
    except queue.Empty:
        return None


def stato_file(cfg) -> dict:
    return json.loads(ripresa.percorso(Path(cfg.agenti_sandbox)).read_text(encoding="utf-8"))


def riavvia(cfg, svc=None, **cambia) -> Lavori:
    """Il riavvio: il servizio si chiude (i lavori fermati restano «in corso» nel file), il
    file sembra scritto da un altro processo, e se ne crea uno nuovo."""
    if svc is not None:
        svc.close()
        time.sleep(0.3)
    p = ripresa.percorso(Path(cfg.agenti_sandbox))
    d = json.loads(p.read_text(encoding="utf-8"))
    d["pid"] = 999_999_999
    for r in d["lavori"]:
        for k, v in cambia.items():
            r[k] = v(r) if callable(v) else v
    p.write_text(json.dumps(d), encoding="utf-8")
    return servizio(cfg)


class Banco:
    def __init__(self, cfg, svc):
        self.cfg, self.svc = cfg, svc
        self.reg = build_registry(documenti=FORMATI, agenti=True)
        self.regole: list = []

    def tool(self, name, args, chi, turno, testo=""):
        sc = SpeakerCtx(chi)
        ctx = ToolContext(cfg=self.cfg, speakers=Speakers(), speaker_ctx=sc, speaker=None,
                          lavori=self.svc, turno=turno, user_text=testo)
        out = json.loads(self.reg.call(name, args, ctx, sc.current_level))
        self.regole = list(ctx.regole)
        return out


fake = FakeOllama(modelli=(MODELLO,)).avvia()
libera = threading.Event()


def lento(body):
    libera.wait(10)
    return {"content": "…"}


# ═══════════════════════════ 1. il caso vero: in corso, riavvio, annuncio, «sì» ════════════════
sezione("lavoro di codice in corso, riavvio, annuncio")
cfg = cfg_base(fake.url, "uno")
svc = servizio(cfg)
fake.copione = [{"tool_calls": [call("scrivi_file", {"percorso": "gioco.js",
                                                     "contenuto": "// memory\n"})]},
                {"tool_calls": [call("scrivi_file", {"percorso": "logica.js",
                                                     "contenuto": "export const x = 1;\n"})]},
                lento]
lav = svc.nuovo("codice", "Fammi un gioco memory da giocare sullo schermo", "mario-id", "Mario")
svc.avvia(lav)
verifica("in coda: lo stato è già su disco", aspetta(lambda: any(
    r["id"] == lav.id for r in stato_file(cfg)["lavori"]), 3))
aspetta(lambda: lav.sandbox is not None and (lav.sandbox.root / "logica.js").is_file(), 10)
riga = next(r for r in stato_file(cfg)["lavori"] if r["id"] == lav.id)
verifica("in corso: stato, cartella dei risultati e sandbox nel file", riga["stato"] == "in_corso"
         and riga["cartella"] and riga["sandbox"] and Path(riga["sandbox"]).is_dir()
         and riga["persona_nome"] == "Mario" and riga["compito"].startswith("Fammi un gioco"),
         str({k: riga[k] for k in ("stato", "titolo")}))
radice = Path(riga["sandbox"])
svc2 = riavvia(cfg, svc)
libera.set()
interr = next((lv for lv in svc2.lavori if lv.id == lav.id), None)
verifica("dopo il riavvio il lavoro c'è, interrotto", interr is not None
         and interr.stato == "interrotto", str(interr and interr.stato))
item = fine(svc2, 5)
msg = (item or {}).get("messaggio", "")
verifica("annuncio a Mario: si è interrotto, ripartirei dai file, «Lo rifaccio?»",
         msg.startswith("Mario, il lavoro «gioco memory da giocare sullo schermo» si è "
                        "interrotto per un riavvio di Calliope.")
         and "aveva già scritto 2 file" in msg and msg.endswith("Lo rifaccio?")
         and item.get("chi") == "mario-id", msg)
off = (item or {}).get("in_sospeso") or {}
verifica("azione in sospeso: lavoro_affida con l'id del lavoro interrotto",
         off.get("tool") == "lavoro_affida" and off.get("argomenti") == {"proposta": lav.id},
         str(off))
meta = json.loads((Path(riga["cartella"]) / "lavoro.json").read_text(encoding="utf-8"))
verifica("lavoro.json nella cartella dice «interrotto»", meta["stato"] == "interrotto")
banco = Banco(cfg, svc2)
out = banco.tool("lavoro_stato", {}, "Mario", 1)
verifica("lavoro_stato: lo elenca come interrotto e chiede se rifarlo, con l'azione in sospeso",
         "si è interrotto per un riavvio di Calliope: lo rifaccio?" in out["risposta_finale"]
         and (out.get("in_sospeso") or {}).get("argomenti") == {"proposta": lav.id},
         out["risposta_finale"])
nuovo_id = svc2.nuovo("altro", "prova", "mario-id", "Mario").id
verifica("gli id nuovi non ripetono quelli di prima", nuovo_id != lav.id
         and int(nuovo_id[1:]) > int(lav.id[1:]), nuovo_id)
out = banco.tool("lavoro_affida", {"tipo": "codice", "compito": "x", "proposta": lav.id},
                 "Bianca", 2)
verifica("un'altra persona non può dire «sì» al posto di Mario", out.get("ok") is False
         and interr.stato == "interrotto" and not svc2.attivi(), out.get("risposta_finale"))

# «Sì» detto alla voce: il modello vede l'azione in sospeso e richiama lavoro_affida
visto = {}


def ripreso(body):
    visto["user"] = next(m["content"] for m in body["messages"] if m["role"] == "user")
    return {"tool_calls": [call("consegna", {"riassunto": "Ho finito il gioco memory.",
                                             "esito": "fatto"})]}


fake.copione = [ripreso]
voce = FakeOllama(modelli=("gemma4:e4b-it-qat",)).avvia()
cfg_v = cfg_base(fake.url, "uno")
cfg_v.llm_native_url = voce.url
ctx_v = ToolContext(cfg=cfg_v, speakers=Speakers(), speaker_ctx=SpeakerCtx("Mario"),
                    speaker=None, lavori=svc2)
brain = Brain(cfg_v, banco.reg, ctx_v)
brain.record_announcement(msg, item.get("in_sospeso"), fonte="agente")


def dice_si(body):
    sis = " ".join(m["content"] for m in body["messages"] if m["role"] == "system")
    m = re.search(r'proposta="(L\d+)"', sis)
    visto["sospeso"] = bool(m)
    return {"tool_calls": [call("lavoro_affida", {"tipo": "codice", "compito": "gioco memory",
                                                  "proposta": m.group(1) if m else ""})]}


voce.copione = [dice_si]
risposta = "".join(brain.stream_reply("Sì, rifallo.", "amministra"))
verifica("il modello della voce vede l'azione in sospeso con l'id", visto.get("sospeso"))
verifica("«sì»: riparte in secondo piano", "secondo piano" in risposta or "coda" in risposta,
         risposta)
item = fine(svc2, 15)
nuovo = next((lv for lv in svc2.lavori if getattr(lv, "ripresa_di", None) == lav.id), None)
verifica("finisce, e lo dice", item and item["stato"] == "fatto" and nuovo is not None
         and item["id"] == nuovo.id and "ho finito «gioco memory" in item["messaggio"],
         str(item and item["messaggio"]))
verifica("lavoro nuovo: stesso compito, stessa persona, stessa cartella dei risultati",
         nuovo is not None and nuovo.compito == lav.compito and nuovo.persona == "mario-id"
         and nuovo.cartella == riga["cartella"])
verifica("riparte dalla sandbox di prima: l'agente vede i file e sa della ripresa",
         "gioco.js" in visto.get("user", "") and "logica.js" in visto.get("user", "")
         and "interrotto da un riavvio" in visto.get("user", ""), visto.get("user", "")[-300:])
verifica("i file di prima nella cartella dei risultati", Path(riga["cartella"], "gioco.js")
         .is_file() and Path(riga["cartella"], "logica.js").is_file())
verifica("il vecchio è «ripreso», non più interrotto né da rifare",
         interr.stato == "ripreso" and svc2.offerta_ripresa("mario-id") is None)
out = banco.tool("lavoro_stato", {}, "Mario", 5)
verifica("lavoro_stato dopo: l'ultimo è finito", "è finito" in out["risposta_finale"],
         out["risposta_finale"])
voce.ferma()
svc2.close()

# ═══════════════════════════ 2. «no», niente secondo annuncio, scadenze ═════════════════════════
sezione("«no», niente secondo annuncio, scadenze")
libera.clear()
cfg = cfg_base(fake.url, "due")
svc = servizio(cfg)
fake.copione = [lento]
lav = svc.nuovo("ricerca", "Cerca i treni per Bologna di domani", "mario-id", "Mario")
svc.avvia(lav)
aspetta(lambda: lav.stato == "in_corso", 3)
time.sleep(0.2)
svc2 = riavvia(cfg, svc)
libera.set()
item = fine(svc2, 5)
verifica("ricerca interrotta: annuncio con «Lo rifaccio?» (niente file da riprendere)",
         item and item["messaggio"].endswith("si è interrotto per un riavvio di Calliope. Lo "
                                             "rifaccio?"), str(item and item["messaggio"]))
# «No»: il modello non chiama niente (l'azione in sospeso si perde): niente riparte
time.sleep(0.3)
verifica("«no»: nessun lavoro riparte", not svc2.attivi())
banco = Banco(cfg, svc2)
out = banco.tool("lavoro_stato", {}, "Mario", 1)
verifica("resta nell'elenco come interrotto", "si è interrotto" in out["risposta_finale"],
         out["risposta_finale"])
svc3 = riavvia(cfg, svc2)
verifica("al riavvio dopo non si annuncia di nuovo", fine(svc3, 1.0) is None
         and any(lv.stato == "interrotto" for lv in svc3.lavori))
svc3.close()

# Interrotto da più di agenti_interrotti_annuncio_h ore: solo nell'elenco
cfg = cfg_base(fake.url, "tre", agenti_interrotti_annuncio_h=3.0)
svc = servizio(cfg)
libera.clear()
fake.copione = [lento]
lav = svc.nuovo("altro", "Scrivi una poesia lunga sul mare", "mario-id", "Mario")
svc.avvia(lav)
aspetta(lambda: lav.stato == "in_corso", 3)
time.sleep(0.2)
svc2 = riavvia(cfg, svc, vivo=lambda r: time.time() - 5 * 3600)
libera.set()
verifica("vecchio di 5 ore: nessun annuncio", fine(svc2, 1.0) is None)
banco = Banco(cfg, svc2)
out = banco.tool("lavoro_stato", {}, "Mario", 1)
verifica("ma lavoro_stato lo elenca, senza domanda", out["risposta_finale"].endswith(
    "si è interrotto per un riavvio di Calliope.") and not out.get("in_sospeso"),
         out["risposta_finale"])
out = banco.tool("lavoro_affida", {"tipo": "altro", "compito": "x", "proposta": lav.id},
                 "Mario", 2)
verifica("e non si rifà con l'id: va chiesto di nuovo", out.get("ok") is False
         and not svc2.attivi(), out.get("risposta_finale"))
svc3 = riavvia(cfg, svc2, vivo=lambda r: time.time() - 25 * 3600)
verifica("più vecchio di un giorno: sparisce anche dall'elenco",
         not any(lv.stato == "interrotto" for lv in svc3.lavori)
         and "interrott" not in svc3.stato("mario-id"))
svc3.close()

# ═══════════════════════════ 3. file della persona, più lavori, file rovinato ═══════════════════
sezione("file della persona, due lavori, file rovinato")
cfg = cfg_base(fake.url, "quattro")
svc = servizio(cfg)
libera.clear()
fake.copione = [lento]
a = svc.nuovo("codice", "Scrivi un programma che rinomina le foto per data", "mario-id", "Mario")
b = svc.nuovo("documento", "Prepara una relazione sulle spese di casa", "mario-id", "Mario")
svc.avvia(a)
svc.avvia(b)
aspetta(lambda: a.stato == "in_corso", 3)
time.sleep(0.2)
verifica("nel file: uno in corso e uno in coda", sorted(r["stato"] for r in stato_file(cfg)[
    "lavori"]) == ["in_coda", "in_corso"])
svc2 = riavvia(cfg, svc)
libera.set()
item = fine(svc2, 5)
verifica("due lavori di Mario: un annuncio solo, «Li rifaccio?»", item and fine(svc2, 0.5) is None
         and "i lavori «programma che rinomina le foto per data» e «relazione sulle spese di "
             "casa» si sono interrotti" in item["messaggio"]
         and item["messaggio"].endswith("Li rifaccio?")
         and item["in_sospeso"]["domanda"] == "Li rifaccio?", str(item and item["messaggio"]))
fake.copione = [{"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]},
                {"content": json.dumps({"titolo": "Spese di casa", "blocchi": [
                    {"tipo": "paragrafo", "testo": "Le spese."}]})}]
banco = Banco(cfg, svc2)
out = banco.tool("lavoro_affida", {"tipo": "codice", "compito": "x",
                                   "proposta": item["in_sospeso"]["argomenti"]["proposta"]},
                 "Mario", 1)
finiti = [fine(svc2, 15), fine(svc2, 15)]
verifica("«sì»: ripartono tutti e due", out.get("ok") and all(finiti)
         and sorted(f["titolo"] for f in finiti) == sorted([a.titolo, b.titolo]),
         str([f and (f["titolo"], f["stato"]) for f in finiti]))
svc2.close()

# Un lavoro su un file della persona: niente «Lo rifaccio?»
cfg = cfg_base(fake.url, "cinque")
svc = servizio(cfg)
svc._salva_stato()
p = ripresa.percorso(Path(cfg.agenti_sandbox))
p.write_text(json.dumps({"versione": 1, "pid": 1, "lavori": [
    {"id": "L7", "tipo": "codice", "titolo": "correggi backup", "compito": "Correggi backup.py",
     "persona": "mario-id", "persona_nome": "Mario", "stato": "in_corso", "file_persona": True,
     "vivo": time.time(), "file_iniziali": {}}]}), encoding="utf-8")
svc.close()
svc2 = servizio(cfg)
item = fine(svc2, 5)
verifica("lavoro su un file della persona: annuncio senza domanda, «chiedimelo di nuovo»",
         item and "chiedimelo di nuovo" in item["messaggio"] and not item.get("in_sospeso")
         and not item["messaggio"].endswith("?"), str(item and item["messaggio"]))
verifica("e non si offre di rifarlo", svc2.offerta_ripresa("mario-id") is None)
svc2.close()
p.write_text("{rotto", encoding="utf-8")
try:
    svc3 = servizio(cfg)
    verifica("file dello stato rovinato: l'avvio va, nessun lavoro", not svc3.lavori)
    svc3.close()
except Exception as e:  # noqa: BLE001
    verifica("file dello stato rovinato: l'avvio va", False, repr(e))

# ═══════════════════════════ 4. in attesa di una risposta ═══════════════════════════════════════
sezione("in attesa di una risposta: sopravvive al riavvio")
cfg = cfg_base(fake.url, "sei")
svc = servizio(cfg)
ripresa_msgs = {}


def dopo_risposta(body):
    ripresa_msgs["m"] = body["messages"]
    return {"tool_calls": [call("consegna", {"riassunto": "Fatto con il punto e virgola.",
                                             "esito": "fatto"})]}


fake.copione = [
    {"tool_calls": [call("scrivi_file", {"percorso": "leggi_csv.py",
                                         "contenuto": "def leggi(r):\n    return r\n"})]},
    {"tool_calls": [call("consegna", {"riassunto": "Manca un dato.", "esito": "mancano_dati",
                                      "domanda": "Che separatore usa il file CSV"})]},
    dopo_risposta]
lav = svc.nuovo("codice", "Scrivi una funzione che legge il CSV delle spese", "mario-id", "Mario")
svc.avvia(lav)
item = fine(svc)
verifica("in attesa: domanda annunciata", item and item["stato"] == "in_attesa")
# Il file si scrive appena il thread dei lavori chiude il giro (subito dopo l'annuncio)
aspetta(lambda: any(r["id"] == lav.id and r["stato"] == "in_attesa" and r.get("contesto")
                    for r in stato_file(cfg)["lavori"]), 3)
riga = next(r for r in stato_file(cfg)["lavori"] if r["id"] == lav.id)
verifica("nel file in attesa, con la conversazione dell'agente", riga["stato"] == "in_attesa"
         and (riga.get("contesto") or {}).get("tipo") == "codice")
svc2 = riavvia(cfg, svc)
item = fine(svc2, 5)
verifica("dopo il riavvio la domanda si ripete, con l'azione in sospeso per lavoro_rispondi",
         item and item["stato"] == "in_attesa" and item["messaggio"].endswith(
             "che separatore usa il file CSV?") and (item.get("in_sospeso") or {}).get("tool")
         == "lavoro_rispondi", str(item and item["messaggio"]))
banco = Banco(cfg, svc2)
out = banco.tool("lavoro_rispondi", {"risposta": "punto e virgola"}, "Mario", 1)
item = fine(svc2, 15)
msgs = ripresa_msgs.get("m") or []
verifica("la risposta lo fa ripartire e finisce", out.get("ok") and item
         and item["stato"] == "fatto", str(item and item["messaggio"]))
verifica("con la conversazione dell'agente di prima e il file già scritto",
         any(m.get("role") == "tool" for m in msgs) and "punto e virgola" in msgs[-1]["content"]
         and Path(item["cartella"], "leggi_csv.py").is_file())
svc2.close()

# La conversazione non si poteva salvare: interrotto
cfg = cfg_base(fake.url, "sette")
svc = servizio(cfg)
svc._salva_stato()
p = ripresa.percorso(Path(cfg.agenti_sandbox))
p.write_text(json.dumps({"versione": 1, "pid": 1, "lavori": [
    {"id": "L3", "tipo": "ricerca", "titolo": "treni per Bologna", "compito": "Cerca i treni",
     "persona": "mario-id", "persona_nome": "Mario", "stato": "in_attesa", "contesto": None,
     "domande": [["Che giorno?", None]], "vivo": time.time(), "file_iniziali": {}}]}),
    encoding="utf-8")
svc.close()
svc2 = servizio(cfg)
item = fine(svc2, 5)
verifica("in attesa senza conversazione salvata: interrotto, «Lo rifaccio?»",
         item and item["messaggio"].endswith("Lo rifaccio?")
         and svc2.lavori[0].stato == "interrotto", str(item and item["messaggio"]))
svc2.close()

fake.ferma()
print("\nTutto a posto." if not errori else f"\n{errori} errori")
sys.exit(1 if errori else 0)
