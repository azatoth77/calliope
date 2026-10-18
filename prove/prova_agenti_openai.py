import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del motore «openai» dell'agente (calliope/agenti/remoto_openai.py, 02/10/2026).

Sulla DGX Ollama 0.35.0 va in «CUDA error: an illegal memory access» con la richiesta vera
dell'agente; l'agente passa a vLLM (API compatibile OpenAI). Qui, senza rete e senza DGX:
- traduzione del corpo nel formato di Ollama (quello di `ciclo.Agente.passata`) in quello
  di /v1/chat/completions: id delle chiamate e tool_call_id, argomenti in stringa,
  thinking, schema JSON, max_tokens, niente num_ctx;
- impostazioni: `motore` in dgx.yaml (porta remota 8000 predefinita), valore sbagliato,
  agenti_url con /v1;
- client contro il server finto (prove/ollama_finto.py, che serve anche /v1): versione,
  modelli, chat con testo, ragionamento, chiamate a pezzi e token; modello mancante,
  server giù, modello senza thinking, server senza /version (llama.cpp), annullo;
- servizio dei lavori completo con il motore «openai»: codice con i test, documento con lo
  schema, errori detti a voce senza «ollama pull»;
- `python -m calliope.agenti --prova` con un dgx.yaml diretto e motore «openai».
Tutto in cartelle temporanee: non legge dgx.yaml né calliope.locale.yaml.

Tempi (18/10, #142, lo stesso criterio di `prova_satellite` in #5): un'attesa di un evento
(il lavoro finito, il test nella sandbox, lo stream chiuso sul server, il comando --prova)
aspetta l'evento con un tetto largo e, se scade, stampa la traccia; resta stretto solo ciò
che misura una cosa che deve essere veloce («interrompi chiude lo stream subito»). Il lavoro
di codice esegue i test quattro volte (esegui_test, due alla consegna, uno alla fine), e
su Windows la sandbox «processo» gira sotto il normale: con la CPU piena di processi a
priorità normale (le altre prove di un `--completo`) un Python lì dentro parte in secondi o
minuti invece di 0,3 s.
"""

import json
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from calliope import capacita
from calliope.agenti import Lavori, carica
from calliope.agenti.impostazioni import ConfigAgentiNonValida, stesso_ollama
from calliope.agenti.remoto import ClienteOllama, ErroreOllama, Interrotto, crea_cliente
from calliope.agenti.remoto_openai import ClienteOpenAI, traduci_corpo
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.agenti import sandbox as sandbox_mod
from prove.ollama_finto import FakeOllama
from prove.porte import porta_fuori_effimere

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-agenti-openai-"))
MODELLO = "qwen3.6-35b"
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


def call(name, args=None):
    return {"name": name, "arguments": args or {}}


# Attese di un evento (#142): larghe, perché sotto carico la sandbox a bassa priorità rallenta
# di minuti e non è ciò che la prova guarda. Il tetto serve solo a non restare appesi: il
# runner ferma comunque una prova oltre i 300 s
# Ogni esecuzione nella sandbox (prima 15 s): a vuoto 0,2–0,4 s, durante un `--completo` fino
# a 27 s misurati il 18/10 (e oltre i 60 con 32 processi pieni a priorità normale)
ESECUZIONE_S = 60.0
# Un lavoro finito (prima 15 s): il codice esegue i test quattro volte, e se una sfora il tetto
# qui sopra il lavoro finisce con «il test non passa» e la traccia, non con un'attesa scaduta
ATTESA_LAVORO_S = 4 * ESECUZIONE_S + 10
ATTESA_COMANDO_S = 120.0     # python -m calliope.agenti --prova (prima 60)
# Le esecuzioni dei test nella sandbox, con la durata: la traccia se un lavoro sfora
ESECUZIONI: list[str] = []
_test_originale = sandbox_mod.Sandbox.test


def _test_misurato(self, *a, **k):
    t = time.perf_counter()
    try:
        r = _test_originale(self, *a, **k)
    except Exception as e:
        ESECUZIONI.append(f"{time.perf_counter() - t:.1f} s: {type(e).__name__}")
        raise
    ESECUZIONI.append(f"{time.perf_counter() - t:.1f} s, passano: {r.get('passano')}")
    return r


sandbox_mod.Sandbox.test = _test_misurato


def traccia() -> str:
    """Le esecuzioni della sandbox e le ultime righe del servizio (per un lavoro che sfora)."""
    return (f"esecuzioni della sandbox: {ESECUZIONI or 'nessuna'}; ultime righe: "
            + " | ".join(LOG[-6:]))


def fine(svc, lav, s=ATTESA_LAVORO_S):
    """La fine di quel lavoro. Quella di un lavoro precedente che ha sforato si scarta, detta:
    prima arrivava al controllo del lavoro dopo e gli errori andavano a cascata (#142)."""
    t = time.perf_counter()
    while (resta := s - (time.perf_counter() - t)) > 0:
        try:
            item = svc.done.get(timeout=resta)
        except queue.Empty:
            break
        if item.get("id") == lav.id:
            return item
        print(f"    scartata la fine di un altro lavoro ({item.get('id')}, {item.get('stato')})",
              flush=True)
    print(f"    il lavoro non è finito in {time.perf_counter() - t:.0f} s; {traccia()}",
          flush=True)
    return None


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
    cfg.agenti_esecuzione_s = ESECUZIONE_S
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


# ═══════════════════════════ 1. traduzione del corpo ═══════════════════════════
sezione("traduzione del corpo (Ollama → OpenAI)")
TOOLS = [{"type": "function", "function": {"name": "scrivi_file", "description": "x",
                                           "parameters": {"type": "object", "properties": {}}}},
         {"type": "function", "function": {"name": "esegui_test", "description": "y",
                                           "parameters": {"type": "object", "properties": {}}}}]
body = {"model": MODELLO, "keep_alive": "30m", "think": True, "tools": TOOLS,
        "options": {"num_ctx": 32768, "temperature": 0.4, "num_predict": 900},
        "messages": [
            {"role": "system", "content": "sistema"},
            {"role": "user", "content": "compito"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "scrivi_file", "arguments": {"percorso": "a.py",
                                                                   "contenuto": "è"}}},
                {"function": {"name": "esegui_test", "arguments": {}}}]},
            {"role": "tool", "tool_name": "esegui_test", "content": "{\"ok\": true}"},
            {"role": "tool", "tool_name": "scrivi_file", "content": "{\"ok\": true}"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "esegui_test", "arguments": {}}}]},
            {"role": "tool", "tool_name": "esegui_test", "content": "{\"ok\": false}"}]}
req = traduci_corpo(body)
m = req["messages"]
ids = [c["id"] for c in m[2]["tool_calls"]]
verifica("chiamate con id distinti e argomenti in stringa JSON",
         len(set(ids)) == 2 and m[2]["tool_calls"][0]["type"] == "function"
         and json.loads(m[2]["tool_calls"][0]["function"]["arguments"])["contenuto"] == "è",
         str(m[2]))
verifica("risposte degli strumenti con il tool_call_id giusto (per nome, anche fuori ordine)",
         m[3]["tool_call_id"] == ids[1] and m[4]["tool_call_id"] == ids[0]
         and m[6]["tool_call_id"] == m[5]["tool_calls"][0]["id"] not in ids
         and "tool_name" not in m[3], str(m[3:]))
verifica("thinking → chat_template_kwargs.enable_thinking; stream con usage",
         req["chat_template_kwargs"] == {"enable_thinking": True} and req["stream"] is True
         and req["stream_options"] == {"include_usage": True})
verifica("temperatura, max_tokens; niente num_ctx, options, keep_alive, think",
         req["temperature"] == 0.4 and req["max_tokens"] == 900
         and not {"options", "keep_alive", "think", "num_ctx"} & set(req), str(req.keys()))
verifica("strumenti passati così come sono, tool_choice auto",
         req["tools"] == TOOLS and req["tool_choice"] == "auto")
SCHEMA = {"type": "object", "properties": {"titolo": {"type": "string"}}, "required": ["titolo"]}
r2 = traduci_corpo({"model": MODELLO, "messages": [], "think": False, "format": SCHEMA})
verifica("schema JSON → response_format json_schema (decodifica guidata), thinking spento",
         r2["response_format"] == {"type": "json_schema", "json_schema": {
             "name": "risposta", "schema": SCHEMA, "strict": True}}
         and r2["chat_template_kwargs"] == {"enable_thinking": False} and "tools" not in r2)
r3 = traduci_corpo({"model": "gpt-oss:120b", "messages": [], "think": "high", "format": "json"})
r4 = traduci_corpo({"model": MODELLO, "messages": [], "options": {"num_ctx": 32768}})
verifica("senza num_predict: tetto della passata a metà di num_ctx (vLLM andrebbe fino a "
         "--max-model-len)", r4.get("max_tokens") == 16384, str(r4.get("max_tokens")))
verifica("think «high» → reasoning_effort (gpt-oss); format json → json_object",
         r3.get("reasoning_effort") == "high" and "chat_template_kwargs" not in r3
         and r3["response_format"] == {"type": "json_object"})

# ═══════════════════════════ 2. impostazioni ═══════════════════════════
sezione("impostazioni")
dgx = TMP / "dgx.yaml"
c = Config()
c.config_dir = str(TMP)
c.agenti_config_file = "dgx.yaml"
dgx.write_text("dgx:\n  ssh_alias: dgx-finto\n  motore: openai\n  agente_modello: qwen3.6-35b\n",
               encoding="utf-8")
imp = carica(c)
verifica("dgx.yaml con motore openai: porta remota 8000 predefinita, nessun avviso",
         imp.motore == "openai" and imp.porta_remota == 8000 and imp.tunnel
         and not imp.avvisi, str(imp))
verifica("client giusto per il motore", isinstance(crea_cliente(imp), ClienteOpenAI))
dgx.write_text("dgx:\n  ssh_alias: dgx-finto\n  agente_modello: qwen3.6:35b\n", encoding="utf-8")
imp = carica(c)
verifica("senza motore: Ollama sulla 11434 (come prima)", imp.motore == "ollama"
         and imp.porta_remota == 11434 and isinstance(crea_cliente(imp), ClienteOllama))
dgx.write_text("dgx:\n  ssh_alias: dgx-finto\n  motore: tgi\n  agente_modello: x\n",
               encoding="utf-8")
try:
    carica(c)
    verifica("motore sconosciuto rifiutato", False)
except ConfigAgentiNonValida as e:
    verifica("motore sconosciuto rifiutato", "motore" in str(e), str(e))
dgx.write_text("dgx:\n  collegamento: diretto\n  motore: openai\n  agente_modello: x\n",
               encoding="utf-8")
try:
    carica(c)
    verifica("diretto senza url: l'esempio dice la porta 8000", False)
except ConfigAgentiNonValida as e:
    verifica("diretto senza url: l'esempio dice la porta 8000", ":8000" in str(e), str(e))
c2 = Config()
c2.agenti_url = "http://127.0.0.1:8000/v1"
imp2 = carica(c2)
verifica("agenti_url con /v1 → motore openai, non è lo stesso Ollama della voce",
         imp2.motore == "openai" and not stesso_ollama(c2, imp2))

# ═══════════════════════════ 3. client contro il server finto ═══════════════════════════
sezione("client OpenAI (server finto)")
fake = FakeOllama(modelli=(MODELLO,), versione="0.29.0").avvia()
cl = ClienteOpenAI(fake.url + "/v1")
verifica("versione da /version (vLLM)", cl.versione() == "vLLM 0.29.0", cl.versione())
verifica("modelli da /v1/models; ha() senza «:latest»", cl.modelli() == [MODELLO]
         and cl.ha(cl.modelli(), MODELLO) and not cl.ha(cl.modelli(), "qwen3.6-35b:latest")
         and cl.caricati() == [MODELLO])
fake.copione = [{"thinking": "Penso.", "content": "Scrivo il file.", "eval": 77, "prompt": 321,
                 "tool_calls": [call("scrivi_file", {"percorso": "a.py",
                                                     "contenuto": "print('è')\n"}),
                                call("esegui_test")]}]
pezzi = []
out = cl.chat(body, su_pezzo=pezzi.append)
verifica("chat: testo a pezzi, ragionamento, due chiamate ricomposte, token",
         out["content"] == "Scrivo il file." and "".join(pezzi) == out["content"]
         and out["thinking"] == "Penso." and out["eval"] == 77 and out["prompt"] == 321
         and out["tool_calls"] == [call("scrivi_file", {"percorso": "a.py",
                                                        "contenuto": "print('è')\n"}),
                                   call("esegui_test")], json.dumps(out)[:300])
verifica("il server ha ricevuto il corpo tradotto", fake.richieste[-1].get("tools") == TOOLS
         and "options" not in fake.richieste[-1])
try:
    cl.chat(dict(body, model="non-ce"))
    verifica("modello mancante → modello_mancante", False)
except ErroreOllama as e:
    verifica("modello mancante → modello_mancante", e.codice == "modello_mancante", str(e))
fake.copione = [{"status": 500, "errore": "CUDA error"}]
try:
    cl.chat(body)
    verifica("errore del server → motore_errore con il messaggio", False)
except ErroreOllama as e:
    verifica("errore del server → motore_errore con il messaggio",
             e.codice == "motore_errore" and "CUDA error" in str(e), str(e))
fake.senza_think.add(MODELLO)
n = len(fake.richieste)
fake.copione = [{"content": "ok"}]
out = cl.chat(body)
verifica("modello senza thinking: si riprova senza chat_template_kwargs, e si ricorda",
         out["content"] == "ok" and len(fake.richieste) == n + 2
         and "chat_template_kwargs" not in fake.richieste[-1]
         and MODELLO in cl.senza_think)
fake.senza_think.clear()
fake.vllm = False
verifica("server senza /version (llama.cpp): risponde con «?»", cl.versione() == "?")
fake.vllm = True
# Una porta fuori dalle effimere: una presa con bind(0) e rilasciata può finire a un altro
# processo, che risponderebbe al posto del server giù (prove/porte.py, #5)
giu = ClienteOpenAI(f"http://127.0.0.1:{porta_fuori_effimere()}", timeout_connessione=2)
try:
    giu.versione()
    verifica("server giù → motore_giu", False)
except ErroreOllama as e:
    verifica("server giù → motore_giu", e.codice == "motore_giu", e.codice)
# Annullo durante lo stream (l'arbitro e «annulla» usano interrompi)
fake.ritardo_pezzo, fake.pezzi = 0.2, 30
fake.copione = [{"content": "x" * 300}]
interrotte = fake.interrotte
res = {}


def lungo():
    try:
        res["out"] = cl.chat(body)
    except Interrotto:
        res["interrotto"] = True


pezzi0 = len(fake.pezzi_tempi)
th = threading.Thread(target=lungo)
th.start()
# Lo stream aperto e già a metà (il secondo pezzo arriva 0,2 s dopo il primo): prima un'attesa
# fissa di 0,6 s, che sotto carico poteva finire prima che lo stream partisse (#142)
in_corso = aspetta(lambda: len(fake.pezzi_tempi) >= pezzi0 + 2, 20)
t0 = time.perf_counter()
cl.interrompi()
th.join(3)
chiuso_s = time.perf_counter() - t0
# Il tetto di 1 s resta: è la misura. L'arbitro chiude lo stream dell'agente quando qualcuno
# parla, e la voce riavrà la GPU solo dopo: non dipende dalla CPU libera (il thread ha la
# risposta in mano e la chiude), mentre lo stream intero durerebbe 6 s. Lo stream chiuso visto
# dal server è invece un'attesa: 10 s
verifica("interrompi chiude lo stream subito", in_corso and res.get("interrotto")
         and not th.is_alive() and chiuso_s < 1.0
         and aspetta(lambda: fake.interrotte > interrotte, 10),
         f"{res}"[:100] + f" in {chiuso_s:.2f} s, stream partito: {in_corso}")
fake.ritardo_pezzo, fake.pezzi = 0.0, 4

# ═══════════════════════════ 4. servizio dei lavori con il motore openai ═══════════════════════════
sezione("lavori con il motore «openai»")
CODICE = [
    {"thinking": "Guardo la cartella.", "tool_calls": [call("elenca_file")]},
    {"tool_calls": [call("scrivi_file", {"percorso": "somma.py",
                                         "contenuto": "def somma(a, b):\n    return a + b\n"}),
                    call("scrivi_file", {"percorso": "test_somma.py", "contenuto":
                                         "from somma import somma\n\n\ndef test_somma():\n"
                                         "    assert somma(2, 3) == 5\n"})]},
    {"tool_calls": [call("esegui_test")]},
    {"tool_calls": [call("consegna", {"riassunto": "Ho scritto la funzione che somma due "
                                                   "numeri, con il suo test.", "esito": "fatto"})]},
]
cfg = cfg_base(fake.url + "/v1")
svc = Lavori(cfg, carica(cfg), log=LOG.append, formati=FORMATI)
verifica("il servizio usa il client OpenAI", isinstance(svc.cliente, ClienteOpenAI)
         and not svc.stesso)
d = svc.verifica()
verifica("verifica del collegamento: ok, versione di vLLM, modello caricato",
         d["codice"] == "ok" and d.get("versione") == "vLLM 0.29.0" and d.get("caricato"), str(d))
fake.copione = [dict(x) for x in CODICE]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi una funzione Python che somma due numeri, con un test",
                "dario-id", "Dario", "amministra")
ESECUZIONI.clear()   # prima di avviare: il lavoro può eseguire i test subito
svc.avvia(lav)
item = fine(svc, lav)
verifica("lavoro di codice finito con il test passato", item is not None
         and item["stato"] == "fatto" and "Il test passa." in item["messaggio"],
         f"{item and item['messaggio']}; {traccia()}")
# Sempre, per misurare (#142): quanto ha preso ogni esecuzione dei test nella sandbox
print(f"    nota: esecuzioni della sandbox del lavoro di codice: {ESECUZIONI}", flush=True)
dest = Path((item or {}).get("cartella") or TMP)
verifica("file nella cartella del lavoro", (dest / "somma.py").is_file()
         and (dest / "test_somma.py").is_file())
r0, r2 = fake.richieste[0], fake.richieste[2] if len(fake.richieste) > 2 else {}
verifica("prima richiesta: 7 strumenti (modifica_file dall'11/10), thinking acceso, niente "
         "num_ctx, tetto della passata e del ragionamento",
         len(r0.get("tools", [])) == 7 and r0["chat_template_kwargs"]["enable_thinking"] is True
         and "options" not in r0 and r0.get("max_tokens") == cfg.agenti_token_passata
         and r0.get("thinking_token_budget") == cfg.agenti_ragionamento_passata,
         str({k: r0.get(k) for k in ("max_tokens", "thinking_token_budget")}))
tool_msgs = [x for x in r2.get("messages", []) if x["role"] == "tool"]
asst = [x for x in r2.get("messages", []) if x.get("tool_calls")]
verifica("storia rimandata con id coerenti (due scritture nella stessa passata)",
         len(tool_msgs) == 3 and {t["tool_call_id"] for t in tool_msgs}
         == {c["id"] for a in asst for c in a["tool_calls"]}, json.dumps(tool_msgs)[:300])

DOC = {"titolo": "Relazione sul giardino", "blocchi": [
    {"tipo": "titolo", "testo": "Relazione sul giardino"},
    {"tipo": "paragrafo", "testo": "Il giardino ha bisogno di acqua due volte a settimana."}]}
fake.copione = [{"content": "Bozza: il giardino e l'acqua."},
                {"content": json.dumps(DOC, ensure_ascii=False)}]
fake.richieste.clear()
lav = svc.nuovo("documento", "Prepara una relazione sul giardino", "bianca-id", "Bianca",
                formato="word")
# La fine in ritardo di un lavoro di prima (sotto carico il codice sforava il tetto, #142):
# fine() aspetta quella del documento e la scarta
svc.done.put({"id": "L-ritardo", "tipo": "codice", "stato": "fatto", "messaggio": "in ritardo",
             "cartella": ""})
ESECUZIONI.clear()   # prima di avviare: il lavoro può eseguire i test subito
svc.avvia(lav)
item = fine(svc, lav)
verifica("la fine in ritardo di un altro lavoro non prende il posto del documento",
         item is not None and item.get("id") == lav.id and item.get("tipo") == "documento",
         str(item and (item.get("id"), item.get("tipo"))))
verifica("documento Word con lo schema come response_format",
         item and item["stato"] == "fatto"
         and len(list(Path(item["cartella"]).glob("*.docx"))) == 1
         and fake.richieste[1].get("response_format", {}).get("type") == "json_schema"
         and fake.richieste[1]["chat_template_kwargs"]["enable_thinking"] is False,
         str(item and item["messaggio"]))
svc.close()

cfg_m = cfg_base(fake.url + "/v1", agenti_modello="modello-che-non-ce")
svc_m = Lavori(cfg_m, carica(cfg_m), log=LOG.append, formati=FORMATI)
lav = svc_m.nuovo("altro", "Fai un lavoro", "dario-id", "Dario")
svc_m.avvia(lav)
# Senza sandbox: 60 s bastano (i 250 s solo per il codice e per il documento che lo segue)
item = fine(svc_m, lav, 60)
verifica("modello non servito: detto senza «ollama pull»", item and item["stato"] == "errore"
         and "ollama pull" not in item["messaggio"] and "modello-che-non-ce" in item["messaggio"],
         str(item and item["messaggio"]))
d = capacita.check_agenti(cfg_m, svc_m)
verifica("capacità: mancante, con i modelli serviti e senza ollama pull",
         d["stato"] == "mancante" and MODELLO in d["prossimo_passo"]
         and "ollama pull" not in d["prossimo_passo"], str(d))
svc_m.close()
cfg_g = cfg_base(f"http://127.0.0.1:{porta_fuori_effimere()}/v1")
svc_g = Lavori(cfg_g, carica(cfg_g), log=LOG.append, formati=FORMATI)
lav = svc_g.nuovo("altro", "Fai un lavoro", "dario-id", "Dario")
svc_g.avvia(lav)
item = fine(svc_g, lav, 60)
verifica("motore giù: «il server del modello dell'agente non risponde»",
         item and item["stato"] == "errore" and "server del modello" in item["messaggio"]
         and "non risponde" in item["messaggio"], str(item and item["messaggio"]))
svc_g.close()

# ═══════════════════════════ 5. python -m calliope.agenti --prova ═══════════════════════════
sezione("python -m calliope.agenti --prova (motore openai)")
dgx.write_text(f"dgx:\n  collegamento: diretto\n  motore: openai\n  url_diretto: {fake.url}\n"
               f"  agente_modello: {MODELLO}\n  timeout_collegamento_s: 10\n", encoding="utf-8")


def prova_cmd():
    env = dict(os.environ, PYTHONUTF8="1",
               CALLIOPE_CONFIG=str(TMP / "calliope-nessuno.yaml"),
               CALLIOPE_CONFIG_LOCALE=str(TMP / "nessun-locale.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(dgx))
    env.pop("CALLIOPE_AGENTI_URL", None)
    r = subprocess.run([sys.executable, "-m", "calliope.agenti", "--prova"], cwd=RADICE, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=ATTESA_COMANDO_S)
    return r.returncode, r.stdout + r.stderr


rc, out = prova_cmd()
verifica("--prova: server OpenAI, versione, modello presente", rc == 0 and "vLLM 0.29.0" in out
         and "motore «openai»" in out and "Tutto pronto" in out, out[-400:])
fake.modelli = ["altro-modello"]
rc, out = prova_cmd()
verifica("--prova con il modello non servito: elenca quelli serviti, niente ollama pull",
         rc == 1 and "altro-modello" in out and "ollama pull" not in out, out[-300:])
fake.modelli = [MODELLO]

fake.ferma()
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
