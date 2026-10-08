import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco degli agenti in secondo piano (calliope/agenti/, 02/10/2026).

Niente DGX, niente ssh vero, niente Ollama vero:
- impostazioni: dgx.yaml (tunnel e diretto), agenti_url, file rovinati, Config senza file;
- tunnel con un ssh FINTO nel PATH (prove/ssh_finto.py): comando (BatchMode,
  ExitOnForwardFailure, -N, -L, alias dopo «--»), apertura e inoltro vero verso l'Ollama
  finto, chiave rifiutata, VPN spenta, nome sconosciuto, host cambiato, porta occupata,
  ssh muto (tempo massimo), ssh mancante, caduta e riapertura, chiusura (porta libera);
  mai l'utente o l'indirizzo nei messaggi;
- sandbox: rete, file fuori, processi, ctypes, sottointerpreti, tempo massimo, memoria,
  percorsi; il job object da solo (senza audit hook) impedisce un secondo processo;
- agente con un Ollama FINTO (prove/ollama_finto.py): codice con i tool (test rifatti dal
  programma), chiamata scritta come testo, tetto dei passi, documento (bozza + JSON),
  modello di documento completo e con dati mancanti, errori (modello mancante, Ollama giù),
  annullo durante lo stream;
- arbitro con l'agente sullo stesso Ollama della voce: la voce chiude lo stream subito, non
  aspetta, l'agente riparte dopo;
- tool lavoro_affida, lavoro_stato, lavoro_annulla: livelli, proposta e conferma (solo nel
  turno dopo, solo la stessa persona), conferma implicita, agente irraggiungibile; la voce
  non aspetta mai (anche con il tunnel bloccato);
- Brain con una voce finta: delega → «Procedo?» → azione in sospeso → «sì» → lavoro;
- annuncio (niente codice a voce) e scheda personale con il codice intero;
- capacità «agenti» e `python -m calliope.agenti --prova` in un sottoprocesso.
Tutto in cartelle temporanee: non legge dgx.yaml né calliope.locale.yaml.
"""

import json
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from calliope import capacita
from calliope.contesto import finestra
from calliope.agenti import Lavori, carica
from calliope.agenti.ciclo import per_la_voce
from calliope.agenti.impostazioni import ConfigAgentiNonValida, ssh_eseguibile, stesso_ollama
from calliope.agenti.remoto import ClienteOllama
from calliope.agenti.sandbox import ErroreSandbox, Sandbox
from calliope.agenti.tunnel import Tunnel, porta_in_uso
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove import ssh_finto
from prove.ollama_finto import FakeOllama

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-agenti-"))
MODELLO = "qwen3.6:35b"
errori = 0
# «La voce non aspetta» (03/10): le chiamate della voce costano meno di un millisecondo, e
# ciò che non devono aspettare (un pezzo dello stream, il tunnel, il portatile lento, la
# copia di un file) dura dai 0,2 s in su. Con 50 ms la prova falliva sotto carico (più
# prove insieme: «la delega risponde subito  50.5 ms», dove c'è anche l'avvio di un thread)
SUBITO_S = 0.15
LOG: list[str] = []


T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def aspetta(cond, s=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", True), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


class Hub:
    """Schermi finti: registrano le schede inviate."""

    def __init__(self):
        self.inviate = []

    def mittente(self, ctx):
        return getattr(ctx.speaker_ctx, "current_speaker", None)

    def invia(self, card, sender):
        self.inviate.append((card, sender))
        return {"schermi": ["studio"]}


def cfg_base(fake_url=None, **kw) -> Config:
    cfg = Config()
    cfg.agenti_url = fake_url
    cfg.agenti_modello = MODELLO
    cfg.agenti_risultati = str(TMP / "risultati")
    cfg.agenti_sandbox = str(TMP / "sandbox")
    # Il codice dell'agente gira solo con il motore scelto a mano (03/10): qui il processo
    cfg.agenti_sandbox_motore = "processo"
    cfg.agenti_modelli = str(TMP / "modelli")
    cfg.llm_native_url = "http://127.0.0.1:9"     # la voce altrove: niente contesa
    cfg.agenti_esecuzione_s = 15.0
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def servizio(cfg, **kw) -> Lavori:
    return Lavori(cfg, carica(cfg), log=LOG.append, formati=FORMATI, **kw)


def fine(svc, s=15.0):
    try:
        import queue
        return svc.done.get(timeout=s)
    except queue.Empty:
        return None


def call(name, args=None):
    return {"name": name, "arguments": args or {}}


# ═══════════════════════════ 1. impostazioni ═══════════════════════════
sezione("impostazioni")
verifica("Config() senza file di configurazione: nessun agente (non cerca dgx.yaml)",
         carica(Config()) is None)
dgx = TMP / "dgx.yaml"
dgx.write_text("dgx:\n  ssh_alias: \"dgx-finto\"\n  collegamento: tunnel\n  porta_remota: 11434\n"
               "  porta_locale: 11499\n  agente_modello: \"qwen3.6:35b\"\n  scrittore_modello: \"\"\n"
               "  timeout_collegamento_s: 2\n  sconosciuta: 1\n", encoding="utf-8")
c = Config()
c.config_dir = str(TMP)
c.agenti_config_file = "dgx.yaml"
imp = carica(c)
verifica("dgx.yaml: tunnel, alias, porte, modello, url locale del tunnel",
         imp and imp.tunnel and imp.ssh_alias == "dgx-finto" and imp.porta_locale == 11499
         and imp.url == "http://127.0.0.1:11499" and imp.modello == MODELLO
         and imp.modello_scrittore == MODELLO, str(imp))
verifica("chiave sconosciuta: avviso, non errore", any("sconosciuta" in a for a in imp.avvisi))
for testo, attesa in (("dgx: [", "non si legge alla riga"),
                      ("dgx:\n  ssh_alias: \"-oProxyCommand=calc\"\n  agente_modello: x\n",
                       "ssh_alias"),
                      ("dgx:\n  ssh_alias: dgx\n", "agente_modello"),
                      ("dgx:\n  collegamento: diretto\n  agente_modello: x\n", "url_diretto"),
                      ("altro: 1\n", "manca la sezione")):
    dgx.write_text(testo, encoding="utf-8")
    try:
        carica(c)
        verifica(f"file rovinato rifiutato ({attesa})", False)
    except ConfigAgentiNonValida as e:
        verifica(f"file rovinato rifiutato ({attesa})", attesa in str(e)
                 and "calc" not in str(e), str(e))
dgx.write_text("dgx:\n  collegamento: diretto\n  url_diretto: http://192.168.1.50:11434\n"
               "  agente_modello: qwen3.6:35b\n", encoding="utf-8")
imp = carica(c)
verifica("dgx.yaml diretto (una DGX in casa, in LAN)", imp and not imp.tunnel
         and imp.url == "http://192.168.1.50:11434")
c2 = Config()
c2.agenti_url = "http://127.0.0.1:11434"
imp2 = carica(c2)
verifica("agenti_url vince: stesso Ollama della voce → contesa", imp2.modo == "diretto"
         and imp2.modello == c2.llm_model and stesso_ollama(c2, imp2))
c2.agenti_enabled = False
verifica("agenti_enabled false: niente agente", carica(c2) is None)

# ═══════════════════════════ 2. tunnel con ssh finto ═══════════════════════════
sezione("tunnel (ssh finto nel PATH)")
fake = FakeOllama(modelli=(MODELLO, "gemma4:e4b-it-qat")).avvia()
bin_dir = TMP / "bin"
bin_dir.mkdir()
ssh_finto.prepara(bin_dir)
os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
os.environ.pop("CALLIOPE_SSH", None)
os.environ["SSH_FINTO_DESTINO"] = str(fake.porta)
os.environ["SSH_FINTO_LOG"] = str(TMP / "ssh_argv.jsonl")
exe = ssh_eseguibile()
verifica("ssh trovato nel PATH è quello finto", bool(exe) and Path(exe).parent == bin_dir, exe)
LP = porta_libera()
messaggi = []


def tunnel_prova(modo, timeout=2.0):
    os.environ["SSH_FINTO_MODO"] = modo
    t = Tunnel("dgx-finto", LP, 11434, timeout_s=timeout, ssh=exe, log=messaggi.append)
    t0 = time.perf_counter()
    code = t.assicura()
    return t, code, time.perf_counter() - t0


t, code, dt = tunnel_prova("ok")
verifica("tunnel aperto", code == "ok" and t.aperto(), f"{code} in {dt:.2f}s")
try:
    ver = ClienteOllama(f"http://127.0.0.1:{LP}").versione()
except Exception as e:  # noqa: BLE001
    ver = repr(e)
verifica("dal tunnel risponde l'Ollama finto (inoltro vero)", ver == fake.versione, ver)
argv = json.loads((TMP / "ssh_argv.jsonl").read_text(encoding="utf-8").splitlines()[-1])
verifica("comando: -N -L 127.0.0.1:LP:127.0.0.1:11434, BatchMode, ExitOnForwardFailure, "
         "keepalive, alias dopo «--»",
         argv[0] == "-N" and f"127.0.0.1:{LP}:127.0.0.1:11434" in argv and "BatchMode=yes" in argv
         and "ExitOnForwardFailure=yes" in argv and "ServerAliveInterval=15" in argv
         and argv[-2:] == ["--", "dgx-finto"] and "ForwardAgent=no" in argv, " ".join(argv))
t.chiudi()
verifica("chiuso: porta libera (job object terminato)", aspetta(lambda: not porta_in_uso(LP), 3))
for modo, attesa in (("chiave", "chiave"), ("vpn", "vpn"), ("nome", "nome"),
                     ("host", "host_sconosciuto"), ("porta", "porta_locale")):
    t, code, dt = tunnel_prova(modo)
    verifica(f"ssh {modo} → {attesa}", code == attesa and not t.vivo(), f"{code} {dt:.2f}s")
    t.chiudi()
occupa = socket.socket()
if os.name != "nt":
    # Linux (DGX, 02/10): la porta del tunnel appena chiuso è in TIME_WAIT e bind fallisce
    # senza SO_REUSEADDR (che lì non ruba una porta in ascolto, a differenza di Windows)
    occupa.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
occupa.bind(("127.0.0.1", LP))
occupa.listen(1)
t, code, dt = tunnel_prova("ok")
verifica("porta locale già occupata da un altro programma → porta_locale, ssh non parte",
         code == "porta_locale" and t.proc is None, code)
occupa.close()
t, code, dt = tunnel_prova("muto", timeout=0.5)
verifica("ssh che non risponde (VPN spenta, nessun errore) → timeout entro il tempo massimo",
         code == "timeout" and dt < 3.5 and not t.vivo(), f"{dt:.2f}s")
t.chiudi()
t2 = Tunnel("dgx-finto", LP, 11434, timeout_s=1, ssh=None, log=messaggi.append)
verifica("ssh mancante → ssh_mancante", t2.assicura() == "ssh_mancante")
os.environ["SSH_FINTO_MODO"] = "cade:0.8"
t = Tunnel("dgx-finto", LP, 11434, timeout_s=2, ssh=exe, log=messaggi.append)
t.ATTESE = (0.3,)
code = t.assicura()
time.sleep(1.2)
os.environ["SSH_FINTO_MODO"] = "ok"
verifica("il tunnel cade e si riapre da solo", code == "ok" and aspetta(
    lambda: t.codice == "ok" and t.tentativi >= 2 and t.vivo(), 8), f"{t.codice} {t.tentativi}")
t.chiudi()
verifica("messaggi del tunnel senza utente né indirizzo",
         not any(ssh_finto.UTENTE in m or ssh_finto.HOST in m for m in messaggi), str(messaggi))

# ═══════════════════════════ 3. sandbox ═══════════════════════════
sezione("sandbox")
# 15 s: con due runner insieme un attacco da 3 s di tempo massimo finiva a volte senza
# uscita (Python non era ancora partito) e la verifica cadeva su un IndexError (06/10). Il
# tempo massimo si prova più sotto con 3 s
sb = Sandbox(TMP / "sb", tempo_s=15, memoria_mb=512)
sb.scrivi("ciao.py", "print('ciao', 2 + 2)\n")
r = sb.esegui("ciao.py")
verifica("esegue un file della cartella", r["codice_uscita"] == 0 and "ciao 4" in r["uscita"])
attacchi = {
    "rete": "import socket\nsocket.socket()\n",
    "rete_http": "import urllib.request\nurllib.request.urlopen('http://127.0.0.1:%d')\n" % fake.porta,
    "leggi_fuori": f"print(open(r'{RADICE / 'CLAUDE.md'}').read()[:20])\n",
    "scrivi_fuori": f"open(r'{TMP / 'fuori.txt'}', 'w').write('x')\n",
    "elenca_fuori": f"import os\nprint(os.listdir(r'{RADICE}'))\n",
    "processi": "import subprocess\nsubprocess.run(['cmd', '/c', 'echo x'])\n",
    "os_system": "import os\nos.system('echo x')\n",
    "ctypes_mem": "import ctypes\nctypes.string_at(id(1), 8)\n",
    "sottointerprete": "from concurrent import interpreters\ninterpreters.create()\n",
    "chdir_fuori": "import os\nos.chdir('..')\n",
}
if os.name == "nt":
    attacchi.update({
        "startfile": "import os\nos.startfile('notepad.exe')\n",
        "ctypes_dll": "import ctypes\nctypes.windll.kernel32.GetTickCount()\n",
        "winapi": "import _winapi\n_winapi.CreateProcess(None, 'cmd /c echo x', None, None, 0, 0, None, None, None)\n",
    })
else:
    # Linux (DGX, 02/10): startfile, windll e _winapi non esistono; questi gli equivalenti
    attacchi.update({
        "fork": "import os\nos.fork()\n",
        "posix_spawn": "import os\nos.posix_spawn('/bin/echo', ['echo', 'x'], {})\n",
        "execv": "import os\nos.execv('/bin/echo', ['echo', 'x'])\n",
        "ctypes_dll": "import ctypes\nctypes.CDLL(None).getpid()\n",
    })
for nome, codice in attacchi.items():
    sb.scrivi(f"{nome}.py", codice)
    r = sb.esegui(f"{nome}.py")
    out = r["uscita"]
    verifica(f"sandbox blocca: {nome}", r["codice_uscita"] != 0 and "Bloccato dalla sandbox"
             in out and not (TMP / "fuori.txt").exists(),
             ((out.strip().splitlines() or [""])[-1] or r.get("errore") or "")[:120])
sb.scrivi("ambiente.py", "import os\nprint(sorted(os.environ))\n")
envs = sb.esegui("ambiente.py")["uscita"]
verifica("ambiente ripulito (niente CALLIOPE_*, niente token, PATH ridotto)",
         "CALLIOPE" not in envs and "TOKEN" not in envs.upper(), envs[:200])
sb.scrivi("ciclo.py", "while True:\n    pass\n")
t0 = time.perf_counter()
sb.tempo_s = 3.0
r = sb.esegui("ciclo.py")
sb.tempo_s = 15.0
verifica("tempo massimo: processo fermato", r["scaduto"] and time.perf_counter() - t0 < 8,
         f"{time.perf_counter() - t0:.1f}s")
sb.scrivi("memoria.py", "x = bytearray(3_000_000_000)\n")
r = sb.esegui("memoria.py")
verifica("tetto di memoria del job", r["codice_uscita"] != 0 and "MemoryError" in r["uscita"])
sb.scrivi("xl.py", "import openpyxl\nwb = openpyxl.Workbook()\nwb.active['A1'] = 3\n"
                   "wb.save('a.xlsx')\nprint('ok')\n")
r = sb.esegui("xl.py")
verifica("openpyxl funziona nella sandbox (numpy e ctypes importabili)",
         r["codice_uscita"] == 0 and r["uscita"].strip().endswith("ok"),
         r["uscita"][-200:])
for bad in ("ctypes.py", "socket.py", "../x.py", "C:/x.py", "a:b.py", "con.py", "x.exe", "x.bat", ".nascosto.py",
            "a/../../b.py", "\\\\server\\share\\x.py", "a/b/c/d/e/f.py"):
    try:
        sb.percorso(bad)
        verifica(f"percorso rifiutato: {bad}", False)
    except ErroreSandbox:
        verifica(f"percorso rifiutato: {bad}", True)
sb.scrivi("mod.py", "def somma(a, b):\n    return a + b\n")
sb.scrivi("test_mod.py", "import unittest\nfrom mod import somma\n\n"
                         "class T(unittest.TestCase):\n    def test_uno(self):\n"
                         "        self.assertEqual(somma(1, 2), 3)\n\n"
                         "def test_due():\n    assert somma(2, 2) == 5\n")
r = sb.test()
verifica("test: unittest e funzioni test_* contati, esito dal programma",
         r["esito"] == {"eseguiti": 2, "falliti": 1, "errori": 0, "saltati": 0}
         and r["passano"] is False, str(r["esito"]))
sb.scrivi("test_finto.py", "print('ESITO_0000 {\"eseguiti\": 9, \"falliti\": 0, \"errori\": 0, "
                           "\"saltati\": 0}')\nimport os\nos._exit(0)\n")
r = sb.test("test_finto.py")
verifica("un test che stampa un esito finto non lo falsifica", not r["passano"], str(r["esito"]))
if sys.platform == "win32":
    from calliope.agenti import winjob
    exe_base = getattr(sys, "_base_executable", sys.executable)
    job = winjob.JobObject(una_sola=True, memoria_mb=512, ui=True)
    p = winjob.avvia_nel_job([exe_base, "-I", "-c",
                              "import subprocess,sys\n"
                              "try:\n subprocess.run(['cmd','/c','echo x'],check=True)\n"
                              " print('PARTITO')\n"
                              "except OSError as e:\n print('NEGATO', e.winerror)\n"],
                             job, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             creationflags=winjob.CREATE_NO_WINDOW)
    out = p.communicate(timeout=20)[0].decode(errors="replace")
    job.close()
    verifica("job object da solo (senza audit hook): un secondo processo non parte",
             "NEGATO" in out and "PARTITO" not in out, out.strip())

# ═══════════════════════════ 4. agente con l'Ollama finto ═══════════════════════════
sezione("agente (Ollama finto)")
CODICE = [
    {"thinking": "Guardo la cartella.", "tool_calls": [call("elenca_file")]},
    {"tool_calls": [call("scrivi_file", {"percorso": "somma.py",
                                         "contenuto": "def somma(a, b):\n    return a + b\n"})]},
    {"tool_calls": [call("scrivi_file", {"percorso": "test_somma.py", "contenuto":
                                         "from somma import somma\n\n\ndef test_somma():\n"
                                         "    assert somma(2, 3) == 5\n"})]},
    {"tool_calls": [call("esegui_test")]},
    {"tool_calls": [call("consegna", {"riassunto": "Ho scritto la funzione che somma due "
                                                   "numeri, con il suo test. Si usa con "
                                                   "`somma(a, b)`.", "esito": "fatto"})]},
]
cfg = cfg_base(fake.url)
svc = servizio(cfg)
hub = Hub()
ev = threading.Event()
svc.on_done = ev.set
fake.copione = [dict(x) for x in CODICE]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi una funzione Python che somma due numeri, con un test",
                "dario-id", "Dario", "amministra")
lav.on_scheda = lambda card: hub.invia(card, "Dario")
t0 = time.perf_counter()
frase = svc.avvia(lav)
dt = time.perf_counter() - t0
item = fine(svc)
verifica("avvia non aspetta niente", dt < SUBITO_S, f"{dt * 1000:.1f} ms")
verifica("lavoro di codice finito, annunciato e on_done chiamato",
         item is not None and item["stato"] == "fatto" and ev.is_set(), str(item))
msg = (item or {}).get("messaggio", "")
verifica("annuncio breve, con il test detto dal programma e senza codice",
         msg.startswith("Dario, ho finito «") and "Il test passa." in msg and "`" not in msg
         and "somma(" not in msg and "def " not in msg, msg)
dest = Path((item or {}).get("cartella") or TMP)
verifica("file di risultato nella cartella del lavoro, con lavoro.json",
         (dest / "somma.py").is_file() and (dest / "test_somma.py").is_file()
         and json.loads((dest / "lavoro.json").read_text(encoding="utf-8"))["test"]["eseguiti"] == 1,
         str(dest))
verifica("la cartella dei risultati è quella configurata", dest.parent == TMP / "risultati")
body = fake.richieste[0]
verifica("richiesta all'agente: modello, tool, thinking acceso, contesto dell'agente",
         body["model"] == MODELLO and body.get("think") is True and len(body["tools"]) == 6
         # agenti_num_ctx «auto» con un Ollama remoto che non dice il contesto: 32 768 (05/10);
         # tetto della passata agenti_token_passata; il tetto del ragionamento è di vLLM e a
         # Ollama non arriva
         and body["options"]["num_ctx"] == 32768 and body["options"]["num_predict"] == 16384
         and "thinking_budget" not in body, json.dumps(body["options"]))
card = hub.inviate[-1][0] if hub.inviate else {}
verifica("scheda personale con il codice intero (a capo conservati)",
         card.get("tipo") == "lavoro" and card.get("visibilita") == "personale"
         and any("def somma(a, b):\n    return a + b" in f["testo"] for f in card.get("file", [])),
         str(card)[:200])
verifica("per_la_voce toglie codice e simboli",
         per_la_voce("Fatto. Usa `x = 1` e poi run.py. Tutto bene.") == "Fatto. Tutto bene.")

# Chiamata scritta come testo (gemma4 senza thinking lo fa spesso)
fake.copione = [{"content": "```json\n{\"name\": \"scrivi_file\", \"arguments\": {\"percorso\": "
                            "\"ciao.py\", \"contenuto\": \"print('ciao')\\n\"}}\n```"},
                {"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]}]
lav = svc.nuovo("codice", "Scrivi un programma che saluta", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
verifica("chiamata scritta come testo eseguita lo stesso", item and item["stato"] == "fatto"
         and (Path(item["cartella"]) / "ciao.py").is_file() and "Non ci sono test" in
         item["messaggio"], str(item and item["messaggio"]))

# Tetto dei passi
cfg.agenti_max_passi = 3
svc.agente.max_passi = 3
fake.richieste.clear()
fake.copione = [{"tool_calls": [call("scrivi_file", {
    "percorso": "test_somma.py", "contenuto": "import unittest\n\n\nclass T(unittest.TestCase):\n"
    "    def test_a(self):\n        self.assertEqual(1 + 1, 2)\n\n    def test_b(self):\n"
    "        self.assertEqual(1, 2)\n"})]}] + [{"tool_calls": [call("elenca_file")]}
                                             for _ in range(6)]
lav = svc.nuovo("codice", "Un lavoro che non finisce mai", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
verifica("tetto dei passi: fermato e detto", item and item["esito"] == "limite"
         and "ho fermato" in item["messaggio"] and lav.passi == 3, str(item and item["messaggio"]))
# 06/10: vicino al tetto l'agente riceve una volta l'avviso di chiudere; fermato, l'annuncio
# dice anche come vanno i test (rifatti dal programma)
_avvisi = [m for r in fake.richieste for m in r.get("messages", [])
           if m.get("role") == "user" and "sta per finire" in str(m.get("content"))]
verifica("tetto vicino: avviso di chiusura all'agente (una volta)",
         _avvisi and len({str(m["content"]) for m in _avvisi}) == 1, str(len(_avvisi)))
verifica("tetto raggiunto: l'annuncio dice i test (1 su 2)",
         item and "ne passano 1 su 2" in item["messaggio"], str(item and item["messaggio"]))
svc.agente.max_passi = cfg.agenti_max_passi = 24

# Tetto dei token per tipo (06/10): token al minuto × minuti, al più agenti_max_token
from calliope.agenti.ciclo import Lavoro as _Lav  # noqa: E402
_ag = svc.agente
_prima = (_ag.max_token, dict(_ag.token_minuto), _ag.tempo_max_s)
_ag.max_token, _ag.token_minuto, _ag.tempo_max_s = 0, {"codice": 5000, "altro": 2000}, 1800
verifica("tetto dei token per tipo: codice 5000/min × 30 min, ricerca come «altro»",
         _ag.tetto_token(_Lav("t", "codice", "x")) == 150000
         and _ag.tetto_token(_Lav("t", "ricerca", "x")) == 60000)
_ag.max_token = 100000
verifica("agenti_max_token vince se è più basso",
         _ag.tetto_token(_Lav("t", "codice", "x")) == 100000
         and _ag.tetto_token(_Lav("t", "ricerca", "x")) == 60000)
_ag.max_token, _ag.token_minuto, _ag.tempo_max_s = _prima

# Un dato della persona (verifica sulla DGX del 04/10: «la tariffa al chilometro che usa la
# mia azienda» → 0,21 €/km inventato 2 volte su 5): il prompt dice di chiederlo prima del
# codice, e la domanda come prima mossa sospende il lavoro senza file scritti
fake.copione = [{"tool_calls": [call("consegna", {
    "riassunto": "Mi serve la tariffa.", "esito": "mancano_dati",
    "domanda": "Qual è la tariffa al chilometro della tua azienda"})]}]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi lo script rimborso.py che legge viaggi.csv e stampa il "
                "rimborso con la tariffa al chilometro che usa la mia azienda", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
_sis = fake.richieste[0]["messages"][0]["content"] if fake.richieste else ""
verifica("prompt del codice: i dati della persona si chiedono, mai un valore tipico",
         "della sua azienda" in _sis and "valore tipico" in _sis and "PRIMA di scrivere il codice"
         in _sis, _sis[-400:])
verifica("dato della persona chiesto come prima mossa: lavoro in attesa, nessun file",
         item is not None and item["stato"] == "in_attesa" and lav.domanda.endswith("azienda?")
         and not list(Path(lav.risultato.get("cartella") or TMP / "nessuna").glob("*.py")),
         str(item and item.get("messaggio")))
svc.annulla("dario-id")
fine(svc, 3.0)

# Consegna con i test che falliscono (verifica sulla DGX del 04/10: accettata, poi «1 test su
# 4 non passa»): il programma rifà i test e la rimanda all'agente con l'uscita, al più 2
# volte; poi l'annuncio onesto
SBAGLIATA = {"tool_calls": [call("scrivi_file", {"percorso": "doppio.py", "contenuto":
                                                 "def doppio(x):\n    return x + 2\n"})]}
GIUSTA = {"tool_calls": [call("scrivi_file", {"percorso": "doppio.py", "contenuto":
                                              "def doppio(x):\n    return x * 2\n"})]}
TEST_D = {"tool_calls": [call("scrivi_file", {"percorso": "test_doppio.py", "contenuto":
                                              "from doppio import doppio\n\n\ndef test_d():\n"
                                              "    assert doppio(5) == 10\n"})]}
CONSEGNA = {"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]}
fake.copione = [dict(SBAGLIATA), dict(TEST_D), dict(CONSEGNA), dict(GIUSTA), dict(CONSEGNA)]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi la funzione doppio con un test", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
_rif = [m for m in fake.richieste[-1]["messages"] if m.get("role") == "tool"
        and "rifiutata" in str(m.get("content"))] if fake.richieste else []
verifica("consegna con i test che falliscono: rimandata con l'uscita dei test",
         len(_rif) == 1 and "correggi" in _rif[0]["content"] and "FAIL" in _rif[0]["content"],
         str(_rif)[:300])
verifica("dopo la correzione la consegna vale e i test passano", item is not None
         and item["stato"] == "fatto" and "Il test passa." in item["messaggio"]
         and len(fake.richieste) == 5, str(item and item["messaggio"]))
# Sempre sbagliata: rimandata 2 volte, poi accettata con l'annuncio onesto
fake.copione = [dict(SBAGLIATA), dict(TEST_D)] + [dict(CONSEGNA) for _ in range(3)]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi la funzione doppio con un test, versione testarda",
                "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
_rif = [m for m in fake.richieste[-1]["messages"] if m.get("role") == "tool"
        and "rifiutata" in str(m.get("content"))] if fake.richieste else []
verifica("al più 2 rimandi, poi l'annuncio dice che i test non passano",
         len(_rif) == 2 and len(fake.richieste) == 5 and item is not None
         and "1 test su 1 non passa" in item["messaggio"], str(item and item["messaggio"]))
# Finito senza chiamare consegna (testo dopo la spinta), con i test rossi: lo stesso controllo
fake.copione = [dict(SBAGLIATA), dict(TEST_D), {"content": "Ho finito."},
                {"content": "Ho finito davvero."}, dict(GIUSTA), dict(CONSEGNA)]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi la funzione doppio con un test, senza consegna",
                "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
_usr = [m for m in fake.richieste[-1]["messages"] if m.get("role") == "user"
        and "I test non passano" in str(m.get("content"))] if fake.richieste else []
verifica("finito senza consegna e test rossi: torna all'agente, poi i test passano",
         len(_usr) == 1 and item is not None and "Il test passa." in item["messaggio"]
         and len(fake.richieste) == 6, str(item and item["messaggio"]))
# Senza passi per correggere la consegna vale subito
svc.agente.max_passi = 3
fake.copione = [dict(SBAGLIATA), dict(TEST_D), dict(CONSEGNA)]
fake.richieste.clear()
lav = svc.nuovo("codice", "Scrivi la funzione doppio, pochi passi", "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
verifica("senza passi rimasti la consegna non si rimanda (niente limite raggiunto)",
         item is not None and item["stato"] == "fatto" and "non passa" in item["messaggio"]
         and len(fake.richieste) == 3, str(item and item["messaggio"]))
svc.agente.max_passi = 24

# Titolo detto a voce (verifica sulla DGX del 04/10: «Dario, ho finito «modulo
# codice_fiscale.py con la funzione carattere_controllo(cf15)»»): titolo_da taglia a «(» e
# l'annuncio dice il titolo senza nomi di file né trattini bassi
from calliope.agenti.servizio import titolo_da, titolo_detto  # noqa: E402
_cf = ("Scrivi il modulo codice_fiscale.py con la funzione carattere_controllo(cf15) che "
       "calcola il carattere di controllo")
verifica("titolo_da taglia anche a «(»", titolo_da(_cf) == "modulo codice_fiscale.py con la "
         "funzione carattere_controllo", titolo_da(_cf))
verifica("titolo detto: niente estensioni, trattini bassi, parentesi; il resto uguale",
         titolo_detto(titolo_da(_cf)) == "modulo codice fiscale con la funzione carattere "
         "controllo" and titolo_detto("relazione sui consumi di casa nel 2025")
         == "relazione sui consumi di casa nel 2025" and titolo_detto("x = {1}") == "x 1"
         and titolo_detto("") == "il lavoro")
fake.copione = [dict(GIUSTA), dict(TEST_D), dict(CONSEGNA)]
lav = svc.nuovo("codice", "Scrivi il modulo doppio_numeri.py con la funzione doppio(x)",
                "dario-id", "Dario")
svc.avvia(lav)
item = fine(svc)
_m = (item or {}).get("messaggio", "")
verifica("annuncio con il titolo detto (la cartella resta col titolo intero)",
         "«modulo doppio numeri con la funzione doppio»" in _m and "_" not in _m
         and ".py" not in _m and "(" not in _m and "doppio_numeri.py" in Path(
             item["cartella"]).name, _m + " | " + str(item and Path(item["cartella"]).name))

# Documento: bozza con il ragionamento, poi il JSON senza
DOC = {"titolo": "Relazione sul giardino", "blocchi": [
    {"tipo": "titolo", "testo": "Relazione sul giardino"},
    {"tipo": "paragrafo", "testo": "Il giardino ha bisogno di acqua due volte a settimana."},
    {"tipo": "elenco", "voci": ["Potare le rose", "Concimare il prato"], "numerato": False}]}
# «la domanda di acqua» nella bozza: non deve far diventare il documento una lettera
fake.copione = [{"content": "Bozza: il giardino, la domanda di acqua, le rose."},
                {"content": json.dumps(DOC, ensure_ascii=False)}]
fake.richieste.clear()
hub.inviate.clear()
lav = svc.nuovo("documento", "Prepara una relazione di due pagine sul giardino", "bianca-id",
                "Bianca", formato="word")
lav.on_scheda = lambda card: hub.invia(card, "Bianca")
svc.avvia(lav)
item = fine(svc)
docx = list(Path(item["cartella"]).glob("*.docx")) if item else []
verifica("documento: file Word nella cartella del lavoro", item and item["stato"] == "fatto"
         and len(docx) == 1, str(item and item["messaggio"]))
verifica("documento: bozza con thinking, JSON con lo schema e senza thinking",
         len(fake.richieste) == 2 and fake.richieste[0].get("think") is True
         and "format" not in fake.richieste[0] and fake.richieste[1].get("think") is False
         and isinstance(fake.richieste[1].get("format"), dict))
_sis = fake.richieste[1]["messages"][0]["content"] if len(fake.richieste) > 1 else ""
_usr = fake.richieste[1]["messages"][-1]["content"] if len(fake.richieste) > 1 else ""
verifica("documento: la bozza va allo scrittore ma non lo fa diventare una lettera",
         "la domanda di acqua" in _usr and "blocco titolo" in _usr
         and "È una lettera" not in _sis, _sis[-200:])
verifica("documento: scheda «documento» personale",
         hub.inviate and hub.inviate[-1][0]["tipo"] == "documento"
         and hub.inviate[-1][0]["visibilita"] == "personale")

# Modello di documento (template)
(TMP / "modelli").mkdir(exist_ok=True)
(TMP / "modelli" / "verbale.json").write_text(json.dumps({
    "nome": "verbale", "titolo": "Verbale di assemblea", "formato": "word",
    "campi": {"condominio": {"descrizione": "il nome del condominio"},
              "data": {"descrizione": "la data dell'assemblea", "tipo": "data"},
              "punti": {"descrizione": "i punti discussi", "tipo": "elenco"},
              "note": {"tipo": "testo", "obbligatorio": False}},
    "documento": {"titolo": "Verbale {{condominio}}", "blocchi": [
        {"tipo": "titolo", "testo": "Verbale di assemblea del condominio {{condominio}}"},
        {"tipo": "paragrafo", "testo": "Il giorno {{data}} si è riunita l'assemblea."},
        {"tipo": "elenco", "voci": "{{punti}}"},
        {"tipo": "paragrafo", "testo": "{{note}}"}]}}, ensure_ascii=False), encoding="utf-8")
svc2 = servizio(cfg)
verifica("modelli caricati dalla cartella", "verbale" in svc2.modelli)
fake.copione = [{"content": json.dumps({"condominio": "Le Querce", "data": "3 ottobre 2026",
                                        "punti": ["Facciata", "Ascensore"], "note": None})}]
fake.richieste.clear()
lav = svc2.nuovo("documento", "Compila il verbale del condominio Le Querce del 3 ottobre: "
                 "facciata e ascensore", "dario-id", "Dario", modello="verbale")
svc2.avvia(lav)
item = fine(svc2)
verifica("modello completo: documento compilato dal programma",
         item and item["stato"] == "fatto" and list(Path(item["cartella"]).glob("*.docx")),
         str(item and item["messaggio"]))
sch = fake.richieste[0].get("format") or {}
verifica("modello: lo schema dei campi va a Ollama (null ammesso), thinking spento",
         set(sch.get("properties", {})) == {"condominio", "data", "punti", "note"}
         and fake.richieste[0].get("think") is False)
fake.copione = [{"content": json.dumps({"condominio": "Le Querce", "data": None, "punti": None,
                                        "note": None})}]
lav = svc2.nuovo("documento", "Compila il verbale del condominio Le Querce", "dario-id", "Dario",
                 modello="verbale")
svc2.avvia(lav)
item = fine(svc2)
# Dal 03/10 il lavoro aspetta la risposta (stato in_attesa, lavoro_rispondi): vedi
# prove/prova_agenti_domande.py
verifica("modello con dati mancanti: chiede invece di inventare",
         item and item["stato"] == "in_attesa" and item.get("in_sospeso")
         and "data dell'assemblea" in item["messaggio"]
         and "punti discussi" in item["messaggio"], str(item and item["messaggio"]))
svc2.annulla("dario-id")
fine(svc2, 3.0)
# 04/10: la data di oggi nel prompt (la data del documento, se non detta, è oggi) e, con un
# dato solo, «mi serve … Me la dici?» invece di «mi servono: … Me li dici?»
from calliope.documenti.scrittore import today_text  # noqa: E402
_sis = fake.richieste[-1]["messages"][0]["content"] if fake.richieste else ""
verifica("modello: oggi nel prompt, la data del documento se non detta è oggi",
         f"Oggi è {today_text(with_day=False)}" in _sis and "se non è detta, è oggi" in _sis,
         _sis[:300])
fake.copione = [{"content": json.dumps({"condominio": "Le Querce", "data": None,
                                        "punti": ["Facciata"], "note": None})}]
lav = svc2.nuovo("documento", "Compila il verbale del condominio Le Querce: la facciata",
                 "dario-id", "Dario", modello="verbale")
svc2.avvia(lav)
item = fine(svc2)
verifica("modello con un dato solo mancante: «mi serve … Me la dici?»",
         item and item["stato"] == "in_attesa" and "mi serve la data dell'assemblea. Me la dici?"
         in item["messaggio"], str(item and item["messaggio"]))
from calliope.agenti.ciclo import _accordo  # noqa: E402
verifica("accordo della domanda con un dato solo: la/una, le, i/gli, il/l'/niente",
         [_accordo(x) for x in ("la data", "una firma", "le firme", "i punti discussi",
                                "gli invitati", "il nome del cliente", "l'indirizzo",
                                "importo", "lavoro")]
         == [("serve", "la"), ("serve", "la"), ("servono", "le"), ("servono", "li"),
             ("servono", "li"), ("serve", "lo"), ("serve", "lo"), ("serve", "lo"),
             ("serve", "lo")])
svc2.annulla("dario-id")
fine(svc2, 3.0)
svc2.close()

# Errori dell'Ollama dell'agente
cfg_m = cfg_base(fake.url, agenti_modello="modello-che-non-ce:1b")
svc_m = servizio(cfg_m)
svc_m.avvia(svc_m.nuovo("altro", "Fai un lavoro", "dario-id", "Dario"))
item = fine(svc_m)
verifica("modello mancante sull'agente: «manca … ollama pull …»",
         item and item["stato"] == "errore" and "ollama pull modello-che-non-ce:1b"
         in item["messaggio"], str(item and item["messaggio"]))
d = capacita.check_agenti(cfg_m, svc_m)
verifica("capacità: modello mancante → passo con ollama pull", d["stato"] == "mancante"
         and "ollama pull" in d["prossimo_passo"], str(d))
svc_m.close()
cfg_g = cfg_base(f"http://127.0.0.1:{porta_libera()}")
svc_g = servizio(cfg_g)
svc_g.avvia(svc_g.nuovo("altro", "Fai un lavoro", "dario-id", "Dario"))
item = fine(svc_g, 20)
verifica("Ollama dell'agente giù: errore detto", item and item["stato"] == "errore"
         and "non risponde" in item["messaggio"], str(item and item["messaggio"]))
svc_g.close()

# Annullo durante lo stream
fake.ritardo_pezzo, fake.pezzi = 0.25, 30
fake.copione = [{"content": "x" * 300}]
interrotte = fake.interrotte
lav = svc.nuovo("altro", "Scrivi un racconto lunghissimo", "dario-id", "Dario")
svc.avvia(lav)
aspetta(lambda: lav.stato == "in_corso" and len(fake.richieste) > 0, 5)
time.sleep(0.4)
t0 = time.perf_counter()
res = svc.annulla("dario-id")
dt = time.perf_counter() - t0
verifica("annulla risponde subito", res["ok"] and dt < SUBITO_S and "Ho fermato" in res["frase"],
         f"{dt * 1000:.1f} ms {res['frase']}")
verifica("lavoro annullato in meno di un secondo, stream chiuso, nessun annuncio",
         aspetta(lambda: lav.stato == "annullato", 2) and aspetta(
             lambda: fake.interrotte > interrotte, 3) and svc.done.empty(),
         f"{lav.stato} {fake.interrotte - interrotte}")
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
svc.close()

# ═══════════════════════════ 5. arbitro: stesso Ollama ═══════════════════════════
sezione("arbitro (agente sullo stesso Ollama della voce)")
cfg_s = cfg_base(fake.url, agenti_ripresa_s=0.2)
cfg_s.llm_native_url = fake.url
cfg_s.llm_model = MODELLO
svc_s = servizio(cfg_s)
verifica("stesso Ollama riconosciuto: arbitro attivo", svc_s.stesso and svc_s.arbitro.condiviso)
fake.ritardo_pezzo, fake.pezzi = 0.2, 20
fake.copione = [{"content": "y" * 200}, {"content": "z" * 50 + "\nRIASSUNTO: Fatto il lavoro."}]
fake.richieste.clear()
interrotte = fake.interrotte
lav = svc_s.nuovo("altro", "Scrivi un testo lungo", "dario-id", "Dario")
svc_s.avvia(lav)
aspetta(lambda: len(fake.richieste) >= 1, 5)
time.sleep(0.4)
t0 = time.perf_counter()
svc_s.arbitro.voce_occupata()
dt = time.perf_counter() - t0
# Il criterio è «non aspetta la chiusura dello stream» (un pezzo dura 200 ms): con più prove
# insieme sul portatile il solo avvio di un thread arrivava a 15–18 ms (03/10); ora la
# chiusura la fa un thread già pronto dell'arbitro
verifica("la voce non aspetta: voce_occupata subito", dt < SUBITO_S, f"{dt * 1000:.2f} ms")
verifica("lo stream dell'agente si chiude subito", aspetta(
    lambda: fake.interrotte > interrotte, 2), f"{fake.interrotte - interrotte}")
n = len(fake.richieste)
time.sleep(0.8)
verifica("mentre la voce è occupata l'agente non manda richieste", len(fake.richieste) == n)
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
svc_s.arbitro.voce_libera()
item = fine(svc_s, 10)
verifica("finita la voce l'agente riparte e finisce", item and item["stato"] == "fatto"
         and lav.cedimenti >= 1, f"{item and item['messaggio']} cedimenti={lav.cedimenti}")
body = fake.richieste[-1]
verifica("stesso modello della voce: num_ctx della voce (niente ricaricamenti)",
         body["options"]["num_ctx"] == finestra(cfg_s))
svc_s.close()
# Senza tempi: la chiusura dello stream resta ferma finché la voce non ha finito; se
# voce_occupata la aspettasse (anche solo per far partire un thread) resterebbe bloccata
from calliope.agenti.arbitro import Arbitro
arb, sblocca, chiuse = Arbitro(True), threading.Event(), []
arb.registra_stream(lambda: (sblocca.wait(10), chiuse.append(1)))
th = threading.Thread(target=arb.voce_occupata, daemon=True)
th.start()
th.join(5)
tornata = not th.is_alive()
sblocca.set()
verifica("voce_occupata torna anche se la chiusura dello stream resta ferma, che poi avviene",
         tornata and aspetta(lambda: chiuse == [1], 5))
# Il server finto è su 127.0.0.1, cioè su questa macchina (stessa GPU per «auto», 04/10):
# l'agente «altrove» si dice con agenti_arbitro: mai (i casi di «auto» in prova_arbitro_vllm)
svc_n = servizio(cfg_base(fake.url, agenti_arbitro="mai"))
svc_n.arbitro.voce_occupata()
verifica("agente su un'altra GPU (agenti_arbitro: mai): l'arbitro non ferma niente",
         not svc_n.arbitro.deve_cedere() and svc_n.arbitro.attendi() == 0.0)
svc_n.close()

# ═══════════════════════════ 6. tool vocali e permessi ═══════════════════════════
sezione("tool vocali")
cfg_t = cfg_base(fake.url)
svc_t = servizio(cfg_t)
svc_t.modelli = {}
reg = build_registry(documenti=FORMATI, agenti=True)
names_ospite = [s["function"]["name"] for s in reg.schemas_for("ospite")]
verifica("gli ospiti non possono usare i tool dei lavori (permessi; il modello li vede)",
         not {"lavoro_affida", "lavoro_stato", "lavoro_annulla"} & set(names_ospite))
hub = Hub()


def ctx_per(chi, livello, turno, how="voce", testo=""):
    return ToolContext(cfg=cfg_t, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello, how),
                       speaker=None, lavori=svc_t, schermi=hub, turno=turno, user_text=testo)


def tool(name, args, chi, livello, turno, how="voce", testo=""):
    t0 = time.perf_counter()
    out = json.loads(reg.call(name, args, ctx_per(chi, livello, turno, how, testo), livello))
    return out, time.perf_counter() - t0


out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "script"}, None, "ospite", 1)
verifica("ospite: rifiutato dal registro", out.get("ok") is False and "NON" in out.get("fatto", ""))
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script di backup"},
              "Bianca", "familiare", 2)
verifica("familiare e codice: solo chi amministra", out.get("ok") is False
         and "amministra" in out["risposta_finale"] and not svc_t.lavori)
fake.copione = [{"content": "Testo.\nRIASSUNTO: Ho scritto il testo."}]
out, dt = tool("lavoro_affida", {"tipo": "altro", "compito": "Scrivi un racconto per bambini"},
               "Bianca", "familiare", 3)
verifica("familiare e lavoro non costoso: parte subito, senza conferma",
         out.get("ok") and "Ci lavoro" in out["risposta_finale"] and "in_sospeso" not in out,
         out.get("risposta_finale"))
verifica("la delega risponde subito", dt < SUBITO_S, f"{dt * 1000:.1f} ms")
item = fine(svc_t)
verifica("annuncio a Bianca", item and item["messaggio"].startswith("Bianca, ho finito"),
         str(item and item["messaggio"]))
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script che rinomina le "
                                "foto per data"}, "Dario", "amministra", 10)
off = out.get("in_sospeso") or {}
verifica("codice: proposta con «Procedo?» e azione in sospeso con l'id del lavoro (dal 08/10 verso sviluppo_apri)",
         out["risposta_finale"].endswith("Procedo?") and off.get("tool") == "sviluppo_apri"
         and str(off.get("argomenti", {}).get("proposta", "")).startswith("L")
         and not svc_t.attivi(), out["risposta_finale"])
lid = off.get("argomenti", {}).get("proposta")
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "x", "proposta": lid}, "Dario",
              "amministra", 10)
verifica("conferma nello stesso turno: rifiutata", out.get("ok") is False and not svc_t.attivi())
ctx = ctx_per("Dario", "amministra", 15)
out = json.loads(reg.call("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script "
                          "che rinomina le foto per data", "proposta": "Sì"}, ctx, "amministra"))
verifica("«proposta» che non è un id (gemma4 ci metteva «Sì»): vale come richiesta nuova",
         out["risposta_finale"].endswith("Procedo?") and "lavori_proposta_non_id" in ctx.regole
         and not svc_t.attivi(), out["risposta_finale"])
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script che rinomina le "
                                "foto per data"}, "Dario", "amministra", 20)
lid = (out.get("in_sospeso") or {}).get("argomenti", {}).get("proposta")
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "x", "proposta": lid}, "Bianca",
              "familiare", 21)
verifica("conferma di un'altra persona: rifiutata", out.get("ok") is False and not svc_t.attivi())
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script che rinomina le "
                                "foto per data"}, "Dario", "amministra", 30)
lid = (out.get("in_sospeso") or {}).get("argomenti", {}).get("proposta")
fake.ritardo_pezzo, fake.pezzi = 0.2, 10
fake.copione = [{"content": "w" * 100}] + [dict(x) for x in CODICE]
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Sì", "proposta": lid}, "Dario",
              "amministra", 31, how="breve")
verifica("«sì» nel turno dopo (frase breve): lavoro avviato", out.get("ok") and
         "Ci lavoro" in out["risposta_finale"] and svc_t.attivi(), out["risposta_finale"])
aspetta(lambda: svc_t.corrente is not None, 3)
out, dt = tool("lavoro_stato", {}, "Dario", "amministra", 32)
verifica("lavoro_stato: a che punto è, senza aspettare", "Sto lavorando a «script che rinomina"
         in out["risposta_finale"] and dt < SUBITO_S, f"{dt * 1000:.1f} ms {out['risposta_finale']}")
out, _ = tool("lavoro_annulla", {}, "Bianca", "familiare", 33)
verifica("un familiare non ferma il lavoro di un altro", out.get("ok") is False
         and "altri" in out["risposta_finale"] and svc_t.attivi())
out, _ = tool("lavoro_annulla", {}, "Dario", "amministra", 34)
verifica("chi l'ha chiesto lo ferma", out.get("ok") and "Ho fermato" in out["risposta_finale"]
         and aspetta(lambda: not svc_t.attivi(), 3))
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
aspetta(lambda: svc_t.corrente is None, 3)
# Conferma implicita: dopo il «sì» il modello richiama lavoro_affida senza conferma
out, _ = tool("lavoro_affida", {"tipo": "ricerca", "compito": "Fai una ricerca sulla storia di "
                                "Venezia e scrivi una relazione"}, "Dario", "amministra", 40)
fake.copione = [{"content": "Venezia.\nRIASSUNTO: Relazione su Venezia pronta."}]
ctx = ctx_per("Dario", "amministra", 41, "breve", "Sì, procedi.")
out = json.loads(reg.call("lavoro_affida", {"tipo": "ricerca", "compito": "Ricerca sulla storia "
                          "di Venezia e relazione"}, ctx, "amministra"))
verifica("conferma implicita (stesso tipo, compito simile, turno dopo)",
         out.get("ok") and "Ci lavoro" in out["risposta_finale"]
         and "lavori_conferma_implicita" in ctx.regole, str(ctx.regole))
item = fine(svc_t)
# Dal 07/10 il testo dell'agente è Markdown in risultato.md (PDF e Word a richiesta)
verifica("ricerca senza biblioteca: testo in risultato.md", item and item["stato"] == "fatto"
         and (Path(item["cartella"]) / "risultato.md").is_file()
         and not list(Path(item["cartella"]).glob("*.docx")), str(item and item["messaggio"]))
# Conferma implicita di un programma con il «sì» breve (03/10, prova_agenti_ollama sulla DGX):
# vale come il «sì» con proposta=id, senza la voce; una richiesta nuova di codice con una
# frase breve resta rifiutata
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script che rinomina le "
                                "foto per data"}, "Dario", "amministra", 50)
fake.copione = [dict(x) for x in CODICE]
ctx = ctx_per("Dario", "amministra", 51, "breve", "Sì, vai.")
out = json.loads(reg.call("lavoro_affida", {"tipo": "codice", "compito": "Scrivi uno script "
                          "Python che rinomina le foto per data"}, ctx, "amministra"))
verifica("conferma implicita di un programma con il «sì» breve", out.get("ok")
         and "Ci lavoro" in out["risposta_finale"] and "lavori_conferma_implicita" in ctx.regole,
         out.get("risposta_finale", ""))
fine(svc_t)
out, _ = tool("lavoro_affida", {"tipo": "codice", "compito": "Scrivi un programma per i backup"},
              "Dario", "amministra", 60, how="breve")
# Dal 04/10 chi amministra con una frase che non basta riceve la frase di sfida
verifica("codice nuovo con una frase breve: rifiutato, frase di sfida", out.get("ok") is False
         and "ripeti:" in out["risposta_finale"], out["risposta_finale"])
svc_t.close()

# Agente irraggiungibile (tunnel, VPN spenta): rifiuto immediato e diagnosi, poi riprova
sezione("servizio con il tunnel (ssh finto)")
dgx.write_text(f"dgx:\n  ssh_alias: dgx-finto\n  collegamento: tunnel\n  porta_remota: 11434\n"
               f"  porta_locale: {LP}\n  agente_modello: {MODELLO}\n"
               f"  timeout_collegamento_s: 1\n", encoding="utf-8")
cfg_d = cfg_base(None)
cfg_d.config_dir = str(TMP)
cfg_d.agenti_config_file = "dgx.yaml"
os.environ["SSH_FINTO_MODO"] = "vpn"
svc_d = servizio(cfg_d)
verifica("servizio con il tunnel", svc_d.tunnel is not None and svc_d.imp.url ==
         f"http://127.0.0.1:{LP}")
reg_d = build_registry(documenti=FORMATI, agenti=True)
svc_d.avvia(svc_d.nuovo("altro", "Fai un riassunto", "dario-id", "Dario"))
item = fine(svc_d)
verifica("VPN spenta: il lavoro non parte e l'annuncio dice perché, senza host né utente",
         item and item["stato"] == "errore" and "VPN" in item["messaggio"]
         and ssh_finto.HOST not in item["messaggio"], str(item and item["messaggio"]))
cap = capacita.check_agenti(cfg_d, svc_d)
verifica("capacità guasta: «VPN spenta?» e il passo", cap["stato"] == "guasta"
         and "VPN" in cap["motivo"] and "VPN" in cap["prossimo_passo"], str(cap))
ctx = ToolContext(cfg=cfg_d, speakers=Speakers(), speaker_ctx=SpeakerCtx("Dario", "amministra"),
                  speaker=None, lavori=svc_d, turno=50)
out = json.loads(reg_d.call("lavoro_affida", {"tipo": "altro", "compito": "Un riassunto"}, ctx,
                            "amministra"))
verifica("delega con l'agente irraggiungibile da poco: rifiuto subito con il motivo",
         out.get("ok") is False and out["risposta_finale"].startswith("Adesso non posso")
         and "VPN" in out["risposta_finale"], out["risposta_finale"])
os.environ["SSH_FINTO_MODO"] = "muto"
svc_d.diagnosi["quando"] -= 100       # diagnosi vecchia: si lascia provare al lavoro
fake.copione = [{"content": "Ok.\nRIASSUNTO: Fatto."}]
svc_d.avvia(svc_d.nuovo("altro", "Fai un riassunto", "dario-id", "Dario"))
aspetta(lambda: svc_d.corrente is not None, 2)
ctx.turno = 60
t0 = time.perf_counter()
reg_d.call("lavoro_stato", {}, ctx, "amministra")
out = json.loads(reg_d.call("lavoro_affida", {"tipo": "altro", "compito": "Un altro riassunto"},
                            ctx, "amministra"))
dt = time.perf_counter() - t0
verifica("tunnel bloccato nel thread dei lavori: i tool rispondono subito", dt < SUBITO_S,
         f"{dt * 1000:.1f} ms")
verifica("un lavoro già in corso: il nuovo chiede conferma e dice che va in coda",
         out.get("in_sospeso") and "prima devo finire" in out["risposta_finale"],
         out.get("risposta_finale"))
item = fine(svc_d, 10)
verifica("ssh muto: errore «la DGX non risponde»", item and item["stato"] == "errore"
         and "non risponde" in item["messaggio"], str(item and item["messaggio"]))
os.environ["SSH_FINTO_MODO"] = "ok"
d = svc_d.verifica()
verifica("VPN accesa: il tunnel si apre e l'agente risponde", d["codice"] == "ok"
         and svc_d.tunnel.aperto(), str(d))
fake.copione = [{"content": "Ok.\nRIASSUNTO: Fatto il riassunto."}]
svc_d.avvia(svc_d.nuovo("altro", "Fai un riassunto", "dario-id", "Dario"))
item = fine(svc_d)
verifica("lavoro fatto attraverso il tunnel", item and item["stato"] == "fatto",
         str(item and item["messaggio"]))
cap = capacita.check_agenti(cfg_d, svc_d)
verifica("capacità attiva con la descrizione (alias, mai l'host)", cap["stato"] == "attiva"
         and "dgx-finto" in cap["motivo"] and ssh_finto.HOST not in json.dumps(cap), cap["motivo"])
svc_d.close()
verifica("chiusura: tunnel chiuso, porta libera", aspetta(lambda: not porta_in_uso(LP), 3))

# ═══════════════════════════ 7. Brain: delega → «Procedo?» → «sì» ═══════════════════════════
sezione("Brain con una voce finta")
voce = FakeOllama(modelli=("gemma4:e4b-it-qat",)).avvia()
cfg_b = cfg_base(fake.url)
cfg_b.llm_native_url = voce.url
svc_b = servizio(cfg_b)
reg_b = build_registry(documenti=FORMATI, agenti=True)
ctx_b = ToolContext(cfg=cfg_b, speakers=Speakers(), speaker_ctx=SpeakerCtx("Dario", "amministra"),
                    speaker=None, lavori=svc_b, schermi=hub)
brain = Brain(cfg_b, reg_b, ctx_b)
voce.copione = [{"tool_calls": [call("lavoro_affida", {
    "tipo": "codice", "compito": "Scrivi una funzione che somma due numeri, con un test"})]}]
risposta = "".join(brain.stream_reply("Scrivimi un programma che somma due numeri, con i test",
                                      "amministra"))
sistema = voce.richieste[0]["messages"][0]["content"]
verifica("il prompt della voce nomina lavoro_affida e il criterio",
         "lavoro_affida" in sistema and "le rispondi tu" in sistema)
verifica("proposta detta così com'è, azione in sospeso", risposta.endswith("Procedo?")
         and brain.has_pending() and len(voce.richieste) == 1, risposta)


def conferma_dal_sospeso(body):
    pend = [m["content"] for m in body["messages"] if m["role"] == "system"
            and m["content"].startswith("Azione in sospeso")]
    import re as _re
    lid = _re.search(r"proposta=\"(L\d+)\"", pend[-1]).group(1) if pend else "?"
    return {"tool_calls": [call("lavoro_affida", {"tipo": "codice", "compito": "Sì",
                                                  "proposta": lid})]}


voce.copione = [conferma_dal_sospeso]
fake.copione = [dict(x) for x in CODICE]
ctx_b.speaker_ctx = SpeakerCtx("Dario", "amministra", "breve")
risposta = "".join(brain.stream_reply("Sì, vai.", "amministra"))
verifica("«sì»: il modello vede l'azione in sospeso e il lavoro parte",
         "Ci lavoro" in risposta and "azione_in_sospeso" in brain.rules_fired(), risposta)
item = fine(svc_b)
verifica("lavoro finito e annunciato", item and item["stato"] == "fatto",
         str(item and item["messaggio"]))
brain.record_announcement(item["messaggio"])
verifica("l'annuncio entra nella storia", brain.history[-1]["content"].endswith(
    item["messaggio"]))
voce.ferma()
svc_b.close()

# ═══════════════════════════ 8. capacità e prompt ═══════════════════════════
sezione("capacità")
d = capacita.check_agenti(Config())
verifica("senza configurazione: da_configurare con il passo", d["stato"] == "da_configurare"
         and "dgx.yaml" in d["prossimo_passo"])
dgx.write_text("dgx: [\n", encoding="utf-8")
d = capacita.check_agenti(cfg_d)
verifica("file della DGX rovinato: guasta, senza il contenuto", d["stato"] == "guasta"
         and "riga" in d["motivo"], str(d))
dgx.write_text(f"dgx:\n  ssh_alias: dgx-finto\n  agente_modello: {MODELLO}\n", encoding="utf-8")
d = capacita.check_agenti(cfg_d)
verifica("da terminale: configurata, collegamento non provato, passo con --prova",
         d["stato"] == "attiva" and "--prova" in d["prossimo_passo"], str(d))
reg_n = capacita.controlla(cfg_d)
verifica("18 capacità nel registro (con archivio, ufficio, conversazioni e ricerca web)", len(reg_n) == 18, str(len(reg_n)))
txt = capacita.testo_prompt(None, [s["function"]["name"] for s in reg.all_schemas()])
verifica("prompt: gli agenti tra quelle che funzionano quando il tool c'è",
         "agenti (lavori lunghi)" in txt.split("Non disponibili")[0], txt[:200])

# ═══════════════════════════ 9. python -m calliope.agenti --prova ═══════════════════════════
sezione("python -m calliope.agenti --prova")
dgx.write_text(f"dgx:\n  ssh_alias: dgx-finto\n  collegamento: tunnel\n  porta_remota: 11434\n"
               f"  porta_locale: {LP}\n  agente_modello: {MODELLO}\n"
               f"  timeout_collegamento_s: 2\n", encoding="utf-8")


def prova_cmd(modo):
    env = dict(os.environ, PYTHONUTF8="1", SSH_FINTO_MODO=modo,
               CALLIOPE_CONFIG=str(TMP / "calliope-nessuno.yaml"),
               CALLIOPE_CONFIG_LOCALE=str(TMP / "nessun-locale.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(dgx))
    env.pop("CALLIOPE_AGENTI_URL", None)
    r = subprocess.run([sys.executable, "-m", "calliope.agenti", "--prova"], cwd=RADICE, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=60)
    return r.returncode, r.stdout + r.stderr


rc, out = prova_cmd("ok")
verifica("--prova: tunnel, versione, modelli, modello presente, tunnel chiuso", rc == 0
         and "Tutto pronto" in out and "Tunnel chiuso" in out and "BatchMode=yes" in out,
         out[-400:])
verifica("--prova: porta libera dopo", aspetta(lambda: not porta_in_uso(LP), 3))
rc, out = prova_cmd("chiave")
verifica("--prova con la chiave rifiutata: esce con 1 e dice cosa fare, senza host né utente",
         rc == 1 and "ssh-add" in out and ssh_finto.HOST not in out and ssh_finto.UTENTE
         not in out, out[-300:])
fake.modelli = ["altro:1b"]
rc, out = prova_cmd("ok")
verifica("--prova con il modello mancante: ollama pull", rc == 1 and
         f"ollama pull {MODELLO}" in out, out[-300:])
fake.modelli = [MODELLO]

fake.ferma()
log = "\n".join(LOG)
verifica("log senza utente né indirizzo della DGX", ssh_finto.HOST not in log
         and ssh_finto.UTENTE not in log)
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
