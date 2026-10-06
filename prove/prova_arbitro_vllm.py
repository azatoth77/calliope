import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dell'arbitro con l'agente su vLLM sulla stessa GPU della voce (04/10/2026).

Sulla DGX la voce è sull'Ollama locale (127.0.0.1:11434) e l'agente su vLLM nello stesso
computer (127.0.0.1:8000/v1): con 3–4 generazioni di vLLM la prima frase della voce passava
da 0,72 s a ~2 s di mediana. Qui, con il server finto (prove/ollama_finto.py, API OpenAI):
- `impostazioni.stessa_gpu`: casi della DGX, del portatile con il tunnel, di un agente su un
  altro host, stesso host della voce, localhost e [::1], `agenti_arbitro` sempre e mai;
- i client dell'agente con uno stream per thread: `interrompi(tid)` chiude solo quello, senza
  argomento tutti;
- un lavoro sul vLLM finto: la voce chiude lo stream subito (il server vede la chiusura),
  nessuna richiesta mentre la voce è occupata, «in pausa» sulla scheda, poi il lavoro finisce
  rifacendo solo il passo interrotto;
- `ClienteCedevole` (archivio, ufficio) insieme all'agente: la voce chiude tutti gli stream
  sullo stesso server, la richiesta si rifà dopo e il testo torna intero; chi è partito dal
  turno della voce (lo scrittore dell'ufficio) non cede a quel turno ma a quello dopo;
  l'annullo di un lavoro chiude solo lo stream del lavoro; una richiesta nuova aspetta la voce;
- `voce_occupata` non aspetta niente anche con tre stream da chiudere.
"""

import json
import queue
import tempfile
import threading
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.agenti.arbitro import Arbitro, ClienteCedevole
from calliope.agenti.impostazioni import Impostazioni, stessa_gpu
from calliope.agenti.remoto import Interrotto
from calliope.agenti.remoto_openai import ClienteOpenAI
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from prove.ollama_finto import FakeOllama

TMP = Path(tempfile.mkdtemp(prefix="calliope-arbitro-vllm-"))
MODELLO = "qwen3.6-35b"
SUBITO_S = 0.15
errori = 0
LOG: list[str] = []
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def aspetta(cond, s=5.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def cfg_base(url, **kw) -> Config:
    cfg = Config()
    cfg.agenti_url = url
    cfg.agenti_modello = MODELLO
    cfg.agenti_risultati = str(TMP / "risultati")
    cfg.agenti_sandbox = str(TMP / "sandbox")
    cfg.agenti_sandbox_motore = "processo"
    cfg.agenti_dimostrazione = False
    cfg.agenti_modelli = str(TMP / "modelli")
    # Come sulla DGX: la voce sull'Ollama locale, l'agente su un altro server nello stesso
    # computer
    cfg.llm_native_url = "http://127.0.0.1:11434"
    cfg.agenti_ripresa_s = 0.2
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


class Registro:
    def __init__(self):
        self.schede, self.lock = [], threading.Lock()

    def __call__(self, card):
        with self.lock:
            self.schede.append(json.loads(json.dumps(card, default=str)))

    def tutte(self):
        with self.lock:
            return list(self.schede)


# ═══════════════════════════ 1. stessa GPU ═══════════════════════════
sezione("stessa GPU della voce (agenti_arbitro)")


def imp(url, modo="diretto"):
    return Impostazioni(modo, url, MODELLO, motore="openai" if url.endswith("/v1") else "ollama")


def c(**kw):
    cfg = Config()
    cfg.llm_native_url = kw.pop("voce", "http://127.0.0.1:11434")
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


casi = [
    ("DGX: voce su Ollama locale, agente su vLLM locale", c(), imp("http://127.0.0.1:8000/v1"), True),
    ("stesso Ollama della voce", c(), imp("http://127.0.0.1:11434"), True),
    ("localhost", c(), imp("http://localhost:8000/v1"), True),
    ("[::1]", c(), imp("http://[::1]:8000/v1"), True),
    ("tunnel SSH: porta locale, GPU della DGX", c(), imp("http://127.0.0.1:11436", "tunnel"), False),
    ("agente su un altro host", c(), imp("http://192.168.1.50:8000/v1"), False),
    ("stesso host della voce (in LAN)", c(voce="http://192.168.1.50:11434"),
     imp("http://192.168.1.50:8000/v1"), True),
    ("voce sulla DGX, agente sul portatile", c(voce="http://192.168.1.50:11434"),
     imp("http://192.168.1.60:8000/v1"), False),
    ("agenti_arbitro: mai", c(agenti_arbitro="mai"), imp("http://127.0.0.1:8000/v1"), False),
    ("agenti_arbitro: sempre (anche con il tunnel)", c(agenti_arbitro="sempre"),
     imp("http://127.0.0.1:11436", "tunnel"), True),
    ("nessun agente", c(), None, False),
]
for nome, cfg, im, atteso in casi:
    verifica(f"{nome}: {'sì' if atteso else 'no'}", stessa_gpu(cfg, im) is atteso)
verifica("con un URL a parte (archivio_url)",
         stessa_gpu(c(), url="http://127.0.0.1:8000/v1")
         and not stessa_gpu(c(), url="http://10.0.0.9:8000/v1"))

fake = FakeOllama(modelli=(MODELLO,)).avvia()
URL = fake.url + "/v1"

# ═══════════════════════════ 2. client: uno stream per thread ═══════════════════════════
sezione("client OpenAI: uno stream per thread")
fake.predefinita = lambda body: {"content": "x" * 40 + body["messages"][-1]["content"]}
fake.ritardo_pezzo, fake.pezzi = 0.1, 20
cli = ClienteOpenAI(URL)
esiti: dict = {}


def corri(nome, cliente=cli):
    esiti[nome + "_tid"] = threading.get_ident()
    try:
        esiti[nome] = cliente.chat({"model": MODELLO, "messages": [
            {"role": "user", "content": nome}], "options": {"num_predict": 50}})["content"]
    except Interrotto:
        esiti[nome] = "interrotto"


ta = threading.Thread(target=corri, args=("A",), daemon=True)
tb = threading.Thread(target=corri, args=("B",), daemon=True)
interrotte = fake.interrotte
ta.start(), tb.start()
aspetta(lambda: len(cli._risposte) == 2, 3)
cli.interrompi(esiti["A_tid"])
ta.join(5), tb.join(8)
verifica("interrompi(tid) chiude solo quello stream", esiti.get("A") == "interrotto"
         and str(esiti.get("B", "")).endswith("B"), f"{esiti.get('A')!r} {str(esiti.get('B'))[-3:]!r}")
verifica("il server vede la chiusura (vLLM annulla la richiesta)",
         aspetta(lambda: fake.interrotte > interrotte, 3))
esiti.clear()
ta = threading.Thread(target=corri, args=("A",), daemon=True)
tb = threading.Thread(target=corri, args=("B",), daemon=True)
ta.start(), tb.start()
aspetta(lambda: len(cli._risposte) == 2, 3)
cli.interrompi()
ta.join(5), tb.join(5)
verifica("interrompi() senza thread li chiude tutti",
         esiti.get("A") == esiti.get("B") == "interrotto", str(esiti))
cli.close()

# ═══════════════════════════ 3. un lavoro su vLLM: la voce lo ferma ═══════════════════════════
sezione("lavoro su vLLM nella stessa macchina: pausa per la voce")
cfg = cfg_base(URL)
svc = Lavori(cfg, carica(cfg), log=LOG.append, formati=FORMATI)
verifica("vLLM accanto all'Ollama della voce: arbitro attivo (non è lo stesso Ollama)",
         svc.arbitro.condiviso and not svc.stesso and svc.stessa_gpu)
fake.predefinita = {"content": "Fatto."}
fake.ritardo_pezzo, fake.pezzi = 0.15, 25
fake.copione = [{"content": "y" * 250}, {"content": "z" * 30 + "\nRIASSUNTO: Fatto il lavoro."}]
fake.richieste.clear()
reg = Registro()
lav = svc.nuovo("altro", "Scrivi un testo lungo", "dario-id", "Dario")
lav.on_scheda = reg
interrotte = fake.interrotte
svc.avvia(lav)
aspetta(lambda: len(fake.richieste) >= 1 and lav.stato == "in_corso", 5)
time.sleep(0.5)
t0 = time.perf_counter()
svc.arbitro.voce_occupata()
dt = time.perf_counter() - t0
verifica("la voce non aspetta", dt < SUBITO_S, f"{dt * 1000:.2f} ms")
verifica("lo stream su vLLM si chiude subito", aspetta(lambda: fake.interrotte > interrotte, 2))
verifica("«in pausa: sto rispondendo a voce» sulla scheda", aspetta(
    lambda: any(c["avanzamento"].get("pausa") for c in reg.tutte()
                if c.get("tipo") == "lavoro" and c.get("stato") == "in_corso"), 1.5))
n = len(fake.richieste)
time.sleep(0.8)
verifica("mentre la voce è occupata l'agente non manda richieste", len(fake.richieste) == n)
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
svc.arbitro.voce_libera()
try:
    item = svc.done.get(timeout=15)
except queue.Empty:
    item = None
# Il copione del finto si consuma a ogni richiesta: la passata rifatta riceve già la risposta
# finale. Conta che dopo la voce ci sia una sola richiesta (il passo rifatto), non il lavoro
# da capo
verifica("finita la voce il lavoro finisce, rifacendo solo il passo interrotto",
         item and item["stato"] == "fatto" and lav.cedimenti >= 1 and len(fake.richieste) == n + 1
         and fake.richieste[-1]["messages"] == fake.richieste[0]["messages"],
         f"{item and item['stato']} cedimenti={lav.cedimenti} richieste={len(fake.richieste) - n}")

# ═══════════════════════════ 4. archivio e ufficio sullo stesso server ═══════════════════════════
sezione("ClienteCedevole: archivio, ufficio e agente insieme")
fake.copione = []
fake.predefinita = lambda body: {"content": "p" * 60 + "|" + body["messages"][-1]["content"]}
fake.ritardo_pezzo, fake.pezzi = 0.1, 30
arb = svc.arbitro
archivio = ClienteCedevole(ClienteOpenAI(URL), arb)
ufficio = ClienteCedevole(svc.cliente, arb, dalla_voce=True)     # lo stesso client dei lavori
esiti.clear()
lav2 = svc.nuovo("altro", "Un altro testo lungo", "dario-id", "Dario")
fake.richieste.clear()
svc.avvia(lav2)
ta = threading.Thread(target=corri, args=("archivio", archivio), daemon=True)
ta.start()
aspetta(lambda: len(fake.richieste) >= 2, 5)
# Un turno della voce comincia; durante il turno lo scrittore dell'ufficio parte
arb.voce_occupata()
t_occ = time.monotonic()
tu = threading.Thread(target=corri, args=("ufficio", ufficio), daemon=True)
tu.start()
verifica("la voce chiude archivio e agente", aspetta(
    lambda: archivio.cessioni >= 1 and lav2.cedimenti >= 1, 2),
    f"archivio={archivio.cessioni} agente={lav2.cedimenti}")
tu.join(6)
verifica("lo scrittore dell'ufficio, partito nel turno, non cede a quel turno e finisce",
         str(esiti.get("ufficio", "")).endswith("|ufficio") and ufficio.cessioni == 0,
         f"{str(esiti.get('ufficio'))[-10:]!r} cessioni={ufficio.cessioni}")
verifica("l'archivio aspetta la voce (nessun risultato durante il turno)", "archivio" not in esiti)
arb.voce_libera(0.1)
ta.join(8)
verifica("finita la voce l'archivio rifà la richiesta e il testo torna intero",
         str(esiti.get("archivio", "")) == "p" * 60 + "|archivio",
         f"{str(esiti.get('archivio'))[-12:]!r}")
# Lo scrittore dell'ufficio partito in un turno cede al turno dopo
esiti.pop("ufficio", None)
arb.voce_occupata()
tu = threading.Thread(target=corri, args=("ufficio", ufficio), daemon=True)
tu.start()
time.sleep(0.4)
arb.voce_libera(0.0)
time.sleep(0.3)
arb.voce_occupata()                  # un turno nuovo
verifica("…ma cede al turno dopo", aspetta(lambda: ufficio.cessioni >= 1, 2))
arb.voce_libera(0.0)
tu.join(8)
verifica("e poi finisce intero", str(esiti.get("ufficio", "")).endswith("|ufficio"))
# Una richiesta nuova aspetta la voce
arb.voce_occupata()
n = len(fake.richieste)
esiti.pop("archivio", None)
ta = threading.Thread(target=corri, args=("archivio", archivio), daemon=True)
ta.start()
time.sleep(0.5)
verifica("una richiesta nuova dell'archivio aspetta la voce", len(fake.richieste) == n)
arb.voce_libera(0.0)
ta.join(8)
verifica("…e parte quando la voce è libera", str(esiti.get("archivio", "")).endswith("|archivio"))
# Tre stream da chiudere: la voce non aspetta
esiti.clear()
fake.ritardo_pezzo = 0.2
tt = [threading.Thread(target=corri, args=(f"s{i}", archivio), daemon=True) for i in range(3)]
for t in tt:
    t.start()
aspetta(lambda: len(arb._streams) >= 3, 3)
t0 = time.perf_counter()
arb.voce_occupata()
dt = time.perf_counter() - t0
verifica("voce_occupata con tre stream da chiudere non aspetta", dt < SUBITO_S and
         aspetta(lambda: archivio.cessioni >= 4, 2), f"{dt * 1000:.2f} ms")
fake.ritardo_pezzo = 0.0
arb.voce_libera(0.0)
for t in tt:
    t.join(8)
verifica("…e tutte e tre finiscono dopo", all(str(esiti.get(f"s{i}", "")).endswith(f"|s{i}")
                                             for i in range(3)))
# L'annullo di un lavoro chiude solo lo stream del lavoro
try:
    svc.done.get(timeout=10)
except queue.Empty:
    pass
fake.ritardo_pezzo, fake.pezzi = 0.15, 30
esiti.clear()
lav3 = svc.nuovo("altro", "Un terzo testo lungo", "dario-id", "Dario")
svc.avvia(lav3)
ta = threading.Thread(target=corri, args=("archivio", archivio), daemon=True)
ta.start()
aspetta(lambda: lav3.stato == "in_corso" and len(svc.cliente._risposte) >= 1, 5)
time.sleep(0.3)
svc.annulla("dario-id", quale="tutti")
ta.join(10)
verifica("l'annullo di un lavoro non tocca l'archivio sullo stesso server",
         str(esiti.get("archivio", "")).endswith("|archivio"), str(esiti.get("archivio"))[-12:])
fake.ritardo_pezzo = 0.0
svc.close()

# Con l'arbitro spento ClienteCedevole è un passaggio diretto
spento = ClienteCedevole(ClienteOpenAI(URL), Arbitro(False))
Arbitro(False).voce_occupata()
fake.predefinita = {"content": "diretto"}
verifica("arbitro spento: passaggio diretto", spento.chat({"model": MODELLO, "messages": [
    {"role": "user", "content": "x"}]})["content"] == "diretto")
fake.ferma()

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} in {time.perf_counter() - T0:.1f}s")
sys.exit(1 if errori else 0)
