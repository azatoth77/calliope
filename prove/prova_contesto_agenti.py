"""Contesto degli agenti (05/10/2026, fase 2b), a secco con un agente finto.

- finestra dal setup (`agenti_num_ctx: auto`): vLLM (max_model_len, cache da /metrics divisa per
  i contesti paralleli), Ollama remoto (al più 32 768), stesso Ollama e modello della voce
  (la finestra della voce), un numero scritto che vince; letta davvero da un server finto;
- tetti della passata: max_tokens senza superare la finestra con il prompt, il tetto del
  ragionamento tradotto in thinking_token_budget per vLLM e tolto per Ollama, i token di
  ragionamento contati a parte (vLLM: usage; Ollama: stima);
- niente più «…[omesso]»: un risultato lungo va per intero in .calliope/passo-N.txt (fuori da
  elenca, risultati e copie), nel contesto la parte utile con il rimando; leggi_file lo
  rilegge, anche a pezzi;
- alle soglie: i risultati vecchi nei file, poi il diario del lavoro scritto dal modello (o
  estrattivo se il tempo non basta o il modello sbaglia), con il compito e gli ultimi passi
  interi; il contesto torna sotto la soglia e la passata ci sta;
- domanda a metà lavoro: il contesto in attesa è compattato, la ripresa continua la
  numerazione dei file e il diario;
- ricerca: una pagina lunga resta in memoria e leggi_file compare per rileggerla.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope.agenti.arbitro import Arbitro  # noqa: E402
from calliope.agenti.ciclo import Agente, Lavoro, ragionamento  # noqa: E402
from calliope.agenti.contesto_lavoro import (ContestoLavoro, PassiMemoria, PassiSandbox,  # noqa: E402
                                             RISULTATO_MAX, e_passo, estrattivo)
from calliope.agenti.remoto import ClienteOllama  # noqa: E402
from calliope.agenti.remoto_openai import ClienteOpenAI, traduci_corpo  # noqa: E402
from calliope.agenti.sandbox import Isolamento, Sandbox  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.contesto import calcola_agenti, token_cache_vllm  # noqa: E402
from prove.ollama_finto import FakeOllama  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
TMP = Path(tempfile.mkdtemp(prefix="calliope-ctxag-"))
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


# ─────────────────────────── finestra ───────────────────────────
sezione("finestra dal setup")
cfg = Config()
b = calcola_agenti(cfg, "openai", {"modello": 131072, "cache": 2_116_147})
verifica("vLLM della DGX: il massimo del modello (cache 2,1 M / 2 contesti)",
         b.finestra == 131072 and b.motivo == "modello", b.frase())
b = calcola_agenti(cfg, "openai", {"modello": 131072, "cache": 100_000})
verifica("vLLM con poca cache: la cache divisa per i contesti paralleli",
         b.finestra == 49152 and b.motivo == "memoria", b.frase())
b = calcola_agenti(cfg, "openai", {})
verifica("vLLM che non dice niente: ripiego 32 768", b.finestra == 32768
         and b.motivo == "ripiego" and b.note, b.frase())
b = calcola_agenti(cfg, "ollama", {"modello": 262144})
verifica("Ollama remoto: al più 32 768 (la memoria di là non si legge)",
         b.finestra == 32768 and "memoria" in " ".join(b.note), b.frase())
b = calcola_agenti(cfg, "ollama", {"modello": 16384})
verifica("Ollama remoto con un modello corto: il suo massimo", b.finestra == 16384
         and b.motivo == "modello", b.frase())
cfg_s = Config()
cfg_s.llm_num_ctx = 20480
b = calcola_agenti(cfg_s, "ollama", {}, stesso=True)
verifica("stesso Ollama e modello della voce: la finestra della voce", b.finestra == 20480
         and b.motivo == "voce", b.frase())
cfg_n = Config()
cfg_n.agenti_num_ctx = 24576
b = calcola_agenti(cfg_n, "openai", {"modello": 131072, "cache": 2_000_000})
verifica("un numero in agenti_num_ctx vince (il calcolo resta)", b.finestra == 24576
         and b.fonte == "configurazione" and b.auto == 131072, b.frase())
verifica("cache di vLLM da /metrics", token_cache_vllm(
    'vllm:cache_config_info{block_size="2096",kv_cache_size_tokens="2116147"} 1.0') == 2116147)

fake = FakeOllama(modelli=("qwen3.6-35b",))
fake.max_model_len, fake.cache_token = 131072, 400_000
fake.avvia()
try:
    imp = SimpleNamespace(modello="qwen3.6-35b", modello_scrittore="qwen3.6-35b",
                          motore="openai", url=fake.url)
    cli = ClienteOpenAI(fake.url)
    log = []
    ag = Agente(Config(), imp, cli, Arbitro(False, 0), log=log.append)
    verifica("dal server finto (vLLM): 400 000 / 2 = 200 000 → il massimo del modello",
             ag.num_ctx() == 131072 and any("Contesto dell'agente" in x for x in log), log)
    fake.cache_token = 60_000
    ag._finestra_t = 0.0
    verifica("cache più piccola, ricalcolata: 30 000 → 28 672", ag.num_ctx() == 28672)
    # una passata vera sul server finto: thinking_token_budget e reasoning_tokens
    fake.copione = [{"content": "ok", "eval": 300, "prompt": 1000, "ragionamento": 250}]
    lav = Lavoro("p1", "altro", "prova")
    out = ag.passata(lav, [{"role": "user", "content": "ciao"}])
    req = fake.richieste[-1]
    verifica("vLLM: max_tokens della passata e thinking_token_budget (metà alla risposta)",
             req.get("max_tokens") == 14336 and req.get("thinking_token_budget") == 7168,
             str({k: req.get(k) for k in ("max_tokens", "thinking_token_budget")}))
    verifica("ragionamento contato a parte (usage di vLLM)", lav.ragionamento == 250
             and lav.token == 300 and out.get("ragionamento") == 250)
    # 06/10: con una finestra piccola il ragionamento lascia metà della passata alla risposta
    # (con 16 384 lasciava 1 024 token e scrivi_file si troncava vuota)
    _cfg16 = Config()
    _cfg16.agenti_num_ctx = 16384
    ag16 = Agente(_cfg16, imp, cli, Arbitro(False, 0), log=lambda *a: None)
    fake.copione = [{"content": "ok", "eval": 300, "prompt": 1000, "ragionamento": 250}]
    ag16.passata(Lavoro("p16", "altro", "prova"), [{"role": "user", "content": "ciao"}])
    req = fake.richieste[-1]
    verifica("finestra 16 384: passata da 8 192, ragionamento al più 4 096",
             req.get("max_tokens") == 8192 and req.get("thinking_token_budget") == 4096,
             str({k: req.get(k) for k in ("max_tokens", "thinking_token_budget")}))
    cli.close()
    fake.contesto_ollama = 262144
    fake.modelli = ["qwen3.6:35b"]
    imp_o = SimpleNamespace(modello="qwen3.6:35b", modello_scrittore="qwen3.6:35b",
                            motore="ollama", url=fake.url)
    clo = ClienteOllama(fake.url)
    ag_o = Agente(Config(), imp_o, clo, Arbitro(False, 0), log=lambda *a: None)
    verifica("dal server finto (Ollama remoto): 32 768", ag_o.num_ctx() == 32768)
    fake.copione = [{"content": "risposta", "thinking": "x" * 300, "eval": 400}]
    lav = Lavoro("p2", "altro", "prova")
    ag_o.passata(lav, [{"role": "user", "content": "ciao"}])
    req = fake.richieste[-1]
    verifica("Ollama: num_ctx e num_predict, niente thinking_budget",
             req["options"]["num_ctx"] == 32768 and req["options"]["num_predict"] == 16384
             and "thinking_budget" not in req, json.dumps(req["options"]))
    verifica("Ollama: ragionamento stimato dalla parte di testo", 0 < lav.ragionamento < 400,
             str(lav.ragionamento))
    clo.close()
finally:
    fake.ferma()

verifica("traduzione: thinking_budget → thinking_token_budget solo col thinking acceso",
         traduci_corpo({"model": "m", "messages": [], "think": True, "thinking_budget": 512,
                        "options": {"num_predict": 2048}}).get("thinking_token_budget") == 512
         and "thinking_token_budget" not in traduci_corpo(
             {"model": "m", "messages": [], "think": False, "thinking_budget": 512}))
verifica("ragionamento senza dati del motore e senza thinking: 0",
         ragionamento({"eval": 100, "content": "x"}) == 0)


# ─────────────────────────── risultati nel file ───────────────────────────
sezione("risultati lunghi nel file")


def sandbox(nome):
    return Sandbox(TMP / nome, 30, 512, isolamento=Isolamento("processo", "prova"))


sb = sandbox("file")
gc = ContestoLavoro(Config(), 32768, PassiSandbox(sb), log=lambda *a: None)
uscita = "riga di test\n" * 1500 + "FAILED (failures=2): test_b, test_c"
txt = gc.risultato("esegui_test", {"esito": {"eseguiti": 3, "falliti": 2}, "passano": False,
                                   "uscita": uscita})
d = json.loads(txt)
verifica("risultato lungo: nel contesto entro il limite, con il rimando",
         len(txt) <= RISULTATO_MAX and d.get("completo") == ".calliope/passo-1.txt", len(txt))
verifica("uscita dei test: resta la coda (l'esito è in fondo)",
         d["uscita"].endswith("FAILED (failures=2): test_b, test_c"))
pieno = (sb.root / ".calliope" / "passo-1.txt").read_text(encoding="utf-8")
verifica("nel file l'uscita intera, con gli a capo veri", uscita in pieno)
verifica("risultato corto: intero, senza file", gc.risultato("elenca_file", {"file": []})
         == '{"file": []}' and gc.n == 1)
sb.scrivi("a.py", "x = 1\n")
verifica("la cartella .calliope non è tra i file elencati", [f["percorso"] for f in sb.elenca()]
         == ["a.py"])
sb.copia_in(TMP / "copia")
verifica("né tra i risultati copiati", not (TMP / "copia" / ".calliope").exists()
         and (TMP / "copia" / "a.py").is_file())
verifica("e_passo: solo .calliope/passo-N.txt", e_passo(".calliope/passo-3.txt")
         and e_passo("./.calliope/passo-3.txt") and not e_passo(".calliope/../a.py")
         and not e_passo("passo-3.txt"))

ag = Agente(Config(), SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
            log=lambda *a: None)
lav = Lavoro("f1", "codice", "prova")
lav.gestore = gc
r = ag._leggi(lav, sb, {"percorso": ".calliope/passo-1.txt"})
verifica("leggi_file rilegge il risultato salvato (12 000 caratteri e il seguito)",
         r.get("caratteri") == len(pieno) and "da_carattere=12000" in r.get("continua", ""),
         str({k: v for k, v in r.items() if k != "contenuto"}))
r2 = ag._leggi(lav, sb, {"percorso": ".calliope/passo-1.txt", "da_carattere": 12000})
verifica("…e a pezzi con da_carattere", r2["contenuto"] == pieno[12000:24000])
verifica("un risultato che non c'è: errore", "errore" in ag._leggi(
    lav, sb, {"percorso": ".calliope/passo-9.txt"}))
verifica("un file corto si legge come prima", ag._leggi(lav, sb, {"percorso": "a.py"})
         == {"contenuto": "x = 1\n"})


# ─────────────────────────── soglie e diario ───────────────────────────
sezione("soglie, file e diario nel ciclo vero")
PAGINA = ("<p>riga di una pagina lunga con un po' di testo</p>\n" * 230)  # ~12 000 caratteri


class Cliente:
    """L'agente finto: un copione di chiamate; il diario (richiesta con lo schema) ha la sua
    risposta. «prompt» stimato come un motore: caratteri / 3,5."""

    def __init__(self, copione, diario=None, diario_rotto=False):
        self.copione = list(copione)
        self.visti = []
        self.diari = 0
        self.diario = diario
        self.rotto = diario_rotto

    def chat(self, body, controlla=None, **kw):
        prompt = int(ContestoLavoro.caratteri(body["messages"], body.get("tools")) / 3.5)
        self.visti.append({"prompt": prompt, "body": body,
                           "messages": [dict(m) for m in body["messages"]]})
        if body.get("format"):
            self.diari += 1
            if self.rotto:
                return {"content": "non è JSON", "tool_calls": [], "eval": 20, "prompt": prompt}
            return {"content": json.dumps(self.diario or {
                "piano": "leggere le pagine, poi scrivere il parser con i test",
                "fatto": ["letto pagina1.html: eventi in div.evento", "letto pagina2.html"],
                "decisioni": ["uso html.parser"], "test": "nessun test ancora",
                "manca": ["scrivere eventi.py e i test"]}), "tool_calls": [], "eval": 120,
                "prompt": prompt}
        p = self.copione.pop(0) if self.copione else [("consegna", {"riassunto": "Fatto.",
                                                                   "esito": "fatto"})]
        return {"content": "", "tool_calls": [{"name": n, "arguments": a} for n, a in p],
                "eval": 60, "prompt": prompt, "ragionamento": 40}


def lavoro_lungo(nome, cfg, copione, senza_tempo=False, **kw):
    sb = sandbox(nome)
    for i in range(1, 7):
        sb.scrivi(f"pagine/p{i}.html", PAGINA.replace("pagina lunga", f"pagina {i}"))
    for i in range(1, 15):
        sb.scrivi(f"note/n{i}.txt", f"nota {i}: " + "dato breve " * 90)
    cli = Cliente(copione, **kw)
    log = []
    ag = Agente(cfg, SimpleNamespace(modello="m"), cli, Arbitro(False, 0), log=log.append)
    if senza_tempo:
        ag._resta_tempo = lambda lav: False
    lav = Lavoro(nome, "codice", "scrivi un parser per le pagine")
    lav.inizio = time.time()
    ris = ag.codice(lav, sb)
    return ris, lav, sb, cli, log


# Prima solo la soglia dei file: finestra 32 768 (16 384 per i messaggi), una pagina ~3 400
# token; con 3 passi intatti alla quarta lettura la prima pagina va nel file
cfg_f = Config()
cfg_f.agenti_num_ctx = 32768
letture = [[("leggi_file", {"percorso": f"pagine/p{i}.html"})] for i in range(1, 7)]
copione = letture + [
    [("scrivi_file", {"percorso": "eventi.py", "contenuto": "def estrai():\n    return []\n"
                      + "# commento lungo\n" * 40})],
    [("leggi_file", {"percorso": ".calliope/passo-1.txt"})],
    [("consegna", {"riassunto": "Ho scritto il parser.", "esito": "fatto"})]]
ris, lav, sb, cli, log = lavoro_lungo("file", cfg_f, [list(x) for x in copione])
verifica("lavoro finito", ris["esito"] == "fatto", str(ris.get("esito")))
verifica("i risultati vecchi sono andati nei file (soglia del 50 %), senza diario",
         lav.uso_contesto.get("file", 0) >= 1 and any("risultati vecchi" in x for x in log)
         and not lav.uso_contesto.get("diari"), str(lav.uso_contesto))
vecchio = cli.visti[-1]["messages"][3]
verifica("il risultato vecchio: riassunto breve con il rimando al file",
         vecchio.get("role") == "tool" and len(vecchio["content"]) < 800
         and json.loads(vecchio["content"]).get("completo", "").startswith(".calliope/passo-"),
         vecchio.get("content", "")[:200])
verifica("i passi recenti restano interi (l'ultima scrittura con il codice)",
         any(m.get("tool_calls") and m["tool_calls"][0]["function"]["name"] == "scrivi_file"
             and "commento lungo" in m["tool_calls"][0]["function"]["arguments"]["contenuto"]
             for m in cli.visti[-1]["messages"]))
# la rilettura del passo 1: il risultato completo, non il riassunto
rilettura = [m for m in cli.visti[-1]["messages"] if m.get("role") == "tool"][-1:]
verifica("l'agente rilegge un risultato salvato e lo ha intero",
         rilettura and "pagina 1" in rilettura[0]["content"]
         and len(json.loads(rilettura[0]["content"]).get("contenuto", "")) > 10_000)
verifica("risultati in .calliope fuori dai file del lavoro",
         [f["percorso"] for f in sb.elenca() if f["percorso"].startswith(".")] == []
         and len(list((sb.root / ".calliope").glob("passo-*.txt"))) >= 1)
# Poi il diario: tanti risultati medi (sotto RISULTATO_LUNGO: non vanno nei file) finché si
# arriva al 75 %. Finestra 8 192: 4 096 per i messaggi
cfg_p = Config()
cfg_p.agenti_num_ctx = 8192
copione_d = ([[("leggi_file", {"percorso": f"note/n{i}.txt"})] for i in range(1, 15)]
             + [[("scrivi_file", {"percorso": "eventi.py", "contenuto": "def estrai():\n"
                                  "    return []\n"})],
                [("consegna", {"riassunto": "Ho scritto il parser.", "esito": "fatto"})]])
ris, lav, sb, cli, log = lavoro_lungo("soglie", cfg_p, [list(x) for x in copione_d])
budget = 8192 - 4096
picco = max(v["prompt"] for v in cli.visti if not v["body"].get("format"))
verifica("diario del lavoro scritto dal modello alla soglia (75 %)",
         cli.diari >= 1 and lav.uso_contesto.get("diari_modello", 0) >= 1, str(lav.uso_contesto))
ultimo = cli.visti[-1]["messages"]
verifica("il diario sta nel messaggio del compito, con il compito intero",
         ultimo[1]["role"] == "user" and "Compito: scrivi un parser" in ultimo[1]["content"]
         and "Diario del lavoro fin qui" in ultimo[1]["content"]
         and "letto pagina1.html" in ultimo[1]["content"])
verifica("il diario dice i file nella cartella",
         "File nella cartella adesso:" in ultimo[1]["content"]
         and "note/n1.txt" in ultimo[1]["content"])
verifica("il prompt resta sotto la finestra meno il tetto della passata", picco <= budget,
         f"picco {picco} su {budget}")
richieste = [v["body"] for v in cli.visti if not v["body"].get("format")]
verifica("ogni passata: prompt stimato + max_tokens dentro la finestra", all(
    int(ContestoLavoro.caratteri(r["messages"], r.get("tools")) / 3.5)
    + r["options"]["num_predict"] <= 8192 + 300 for r in richieste))
verifica("niente più «…[omesso]» nel contesto", not any(
    "[omesso]" in (m.get("content") or "") for v in cli.visti for m in v["messages"]))
verifica("dopo il diario restano il prompt, il compito e gli ultimi 3 passi",
         sum(1 for m in ultimo if m.get("role") == "assistant") <= 4
         and ultimo[0]["role"] == "system", str([m["role"] for m in ultimo]))
verifica("ragionamento contato a parte nel lavoro", lav.ragionamento == 40 * lav.passi
         and lav.token > lav.ragionamento, f"{lav.ragionamento} / {lav.token}")
verifica("il diario non conta tra le passate (ma i suoi token sì)",
         lav.passi == len(richieste) and lav.token == 60 * lav.passi + 120 * cli.diari)

# 06/10 (parser con 16 384 di finestra e qwen3.6): un diario che toglie meno di quanto il
# diario stesso cresce non si fa (costava 12–17 s per 300–500 token); se toglie abbastanza sì
def _passi(n_vecchio: int):
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Compito: x"}]
    for i, lung in enumerate([n_vecchio, 12000, 12000, 12000]):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "leggi_file", "arguments": {"percorso": f"p{i}.html"}}}]})
        msgs.append({"role": "tool", "tool_name": "leggi_file", "content": "y" * lung})
    return msgs


_chiesti = []
for vecchio, atteso in ((1500, False), (9000, True)):
    _gc = ContestoLavoro(Config(), 16384, PassiMemoria())
    _gc.cpt = 3.0
    _m = _passi(vecchio)
    _ok = _gc.diario_ora(_m, diario_modello=lambda t, d: _chiesti.append(t) or {
        "fatto": ["letto p0.html"]})
    verifica(f"diario solo se il guadagno netto basta (passo vecchio di {vecchio} caratteri)",
             _ok is atteso and (len(_m) == 10) is (not atteso), f"{_ok}, {len(_m)} messaggi")
verifica("il diario che non conviene non chiede nemmeno il modello", len(_chiesti) == 1)

# 06/10: alla soglia dura si accorciano i risultati recenti dal più vecchio e solo finché serve
# (prima tutti tranne l'ultimo passo: l'agente rileggeva a turno i due file del lavoro)
_gc = ContestoLavoro(Config(), 16384, PassiMemoria())
_gc.cpt = 3.0
_m = _passi(9000)
for _i in (5, 7, 9):
    _m[_i]["content"] = "z" * 9000
_gc.prima_della_passata(_m)
verifica("soglia dura: accorciato il passo recente più vecchio, il penultimo resta intero",
         len(_m[5]["content"]) < 1200 and len(_m[7]["content"]) == 9000
         and len(_m[9]["content"]) == 9000, str([len(x.get("content") or "") for x in _m]))
_gc = ContestoLavoro(Config(), 16384, PassiMemoria())
_gc.cpt = 3.0
_m = _passi(300)[:4]
_m[2]["tool_calls"] = _m[2]["tool_calls"] * 9
_m[3:] = [{"role": "tool", "tool_name": "leggi_file", "content": "w" * 12000}
          for _ in range(9)]
_gc.prima_della_passata(_m)
verifica("un passo solo con letture oltre la finestra: si accorciano anche le sue, tranne "
         "l'ultima", _gc.stima(_m) <= 16384 - 1024 and len(_m[-1]["content"]) == 12000,
         str(_gc.stima(_m)))

# 06/10: la stessa lettura due volte nella stessa passata non si rifà
_cop = [[("leggi_file", {"percorso": "note/n1.txt"}), ("leggi_file", {"percorso": "note/n1.txt"}),
         ("leggi_file", {"percorso": "note/n2.txt"})],
        [("scrivi_file", {"percorso": "eventi.py", "contenuto": "x = 1\n"})],
        [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]]
ris, lav, sb, cli, log = lavoro_lungo("doppie", Config(), [list(x) for x in _cop])
_ris = [m["content"] for m in cli.visti[1]["messages"] if m.get("role") == "tool"]
verifica("stessa lettura nella stessa passata: la seconda non si rifà",
         len(_ris) == 3 and "già fatta in questa passata" in _ris[1]
         and "nota 1" in _ris[0] and "nota 2" in _ris[2], str([x[:40] for x in _ris]))

# 06/10: lo stesso file riletto uguale dalla terza volta ha una nota (l'agente rileggeva a
# turno codice e test); cambiato, il conto riparte
_cop = [[("leggi_file", {"percorso": "note/n1.txt"})] for _ in range(3)] + [
        [("scrivi_file", {"percorso": "note/n1.txt", "contenuto": "nuovo\n"})],
        [("leggi_file", {"percorso": "note/n1.txt"})],
        [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]]
ris, lav, sb, cli, log = lavoro_lungo("riletture", Config(), [list(x) for x in _cop])
_ris = [m["content"] for m in cli.visti[-1]["messages"] if m.get("role") == "tool"
        and m.get("tool_name") == "leggi_file"]
verifica("file riletto uguale: nota dalla terza volta, non dopo una modifica",
         len(_ris) == 4 and "letto questo file" not in _ris[1]
         and "letto questo file 3 volte" in _ris[2] and "letto questo file" not in _ris[3],
         str([x[-60:] for x in _ris]))

sezione("diario estrattivo")
ris, lav, sb, cli, log = lavoro_lungo("rotto", cfg_p, [list(x) for x in copione_d],
                                      diario_rotto=True)
ultimo = cli.visti[-1]["messages"]
verifica("modello del diario che sbaglia: diario estrattivo e il lavoro va avanti",
         ris["esito"] == "fatto" and lav.uso_contesto.get("diari", 0) >= 1
         and lav.uso_contesto.get("diari_modello", 0) == 0
         and "leggi_file note/n1.txt" in ultimo[1]["content"], str(lav.uso_contesto))
# Tempo, passate o token che non bastano (_resta_tempo falso): niente passata per il diario
ris, lav, sb, cli, log = lavoro_lungo("tempo", cfg_p, [list(x) for x in copione_d],
                                      senza_tempo=True)
verifica("tempo o passate che non bastano: diario estrattivo, senza chiedere al modello",
         cli.diari == 0 and lav.uso_contesto.get("diari", 0) >= 1, str(lav.uso_contesto))
d = estrattivo([
    {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "scrivi_file", "arguments": {"percorso": "x.py"}}},
        {"function": {"name": "esegui_test", "arguments": {}}}]},
    {"role": "tool", "tool_name": "scrivi_file", "content": '{"ok": true}'},
    {"role": "tool", "tool_name": "esegui_test",
     "content": '{"esito": {"eseguiti": 3, "falliti": 1}, "passano": false}'},
    {"role": "user", "content": "Risposta di Dario alla tua domanda «quale tariffa?»: 0,30"}],
    None)
verifica("estrattivo: file scritti, esito dei test, risposte della persona, cosa manca",
         "scritto x.py" in d["fatto"] and d["test"] == "2 test su 3 passano"
         and any("0,30" in x for x in d["decisioni"]) and d["manca"], json.dumps(d))

sezione("domanda a metà lavoro")
cfg_d = Config()
cfg_d.agenti_num_ctx = 32768
copione_d = letture[:4] + [[("consegna", {"riassunto": "Serve un dato.", "esito": "mancano_dati",
                                          "domanda": "Quale formato di data vuoi?"})]]
sb = sandbox("domanda")
for i in range(1, 7):
    sb.scrivi(f"pagine/p{i}.html", PAGINA.replace("pagina lunga", f"pagina {i}"))
cli = Cliente(copione_d)
ag = Agente(cfg_d, SimpleNamespace(modello="m"), cli, Arbitro(False, 0), log=lambda *a: None)
lav = Lavoro("dom", "codice", "scrivi un parser per le pagine")
lav.inizio = time.time()
ris = ag.codice(lav, sb)
msgs = lav.contesto.get("messages") or []
lunghi = [m for m in msgs[2:] if m.get("role") == "tool" and len(m["content"]) > 1500]
verifica("domanda: il contesto in attesa è compattato (risultati lunghi nei file)",
         ris["esito"] == "mancano_dati" and not lunghi and lav.contesto.get("gestore", {})
         .get("n", 0) >= 3, f"{len(lunghi)} lunghi, n={lav.contesto.get('gestore', {}).get('n')}")
n_prima = lav.contesto["gestore"]["n"]
cli.copione = [[("leggi_file", {"percorso": "pagine/p5.html"}), ],
               [("consegna", {"riassunto": "Fatto con il formato giusto.", "esito": "fatto"})]]
lav.domande.append(["Quale formato di data vuoi?", None])
lav.risposta = "AAAA-MM-GG"
ris2 = ag.codice(lav, sb)
verifica("ripresa: continua con lo stesso stato del contesto",
         ris2["esito"] == "fatto" and lav.gestore.n >= n_prima
         and "Risposta di" in cli.visti[-1]["messages"][-3]["content"]
         or ris2["esito"] == "fatto" and any("AAAA-MM-GG" in (m.get("content") or "")
                                             for m in cli.visti[-1]["messages"]),
         str(ris2.get("esito")))

sezione("ricerca: pagina lunga in memoria")


class Biblioteca:
    def cerca(self, domanda):
        return [SimpleNamespace(titolo=f"Voce {i}", fonte="wikipedia", testo="testo " * 400)
                for i in range(4)]


cli = Cliente([[("biblioteca_cerca", {"domanda": "storia del borgo"})],
               [("leggi_file", {"percorso": ".calliope/passo-1.txt"})],
               [("consegna", {"testo": "Relazione.", "riassunto": "Fatto."})]])
ag = Agente(Config(), SimpleNamespace(modello="m"), cli, Arbitro(False, 0),
            log=lambda *a: None, biblioteca=Biblioteca())
lav = Lavoro("ric", "ricerca", "storia del borgo")
ris = ag.ricerca(lav)
strumenti = [t["function"]["name"] for t in cli.visti[-1]["body"]["tools"]]
rilegge = [m for m in cli.visti[-1]["messages"] if m.get("tool_name") == "leggi_file"]
verifica("ricerca: il risultato lungo resta per intero e leggi_file compare",
         ris["esito"] == "fatto" and "leggi_file" in strumenti and rilegge
         and len(json.loads(rilegge[0]["content"])["contenuto"]) > 6000, strumenti)

print(f"\n{'Tutto bene' if not errori else f'{errori} ERRORI'} "
      f"({time.perf_counter() - T0:.1f} s)")
sys.exit(1 if errori else 0)
