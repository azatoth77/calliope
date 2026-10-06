"""
Prova a secco della portabilità su Linux aarch64 (DGX Spark, 02/10/2026), girando su
Windows: ciò che si può provare senza la DGX.

1. Silero VAD senza torch (calliope/vad.py): onnxruntime + numpy contro il modello di
   torch, finestra per finestra, sulle registrazioni vere se ci sono (registrazioni/, fuori
   da git) o su audio sintetico; con torch bloccato «auto» sceglie onnxruntime.
2. Una «DGX simulata» in un sottoprocesso: sys.platform = linux, macchina aarch64, librerie
   di Windows (pycaw, comtypes, pywin32, winrt…) e torch bloccate, CTranslate2 senza GPU,
   PortAudio assente, calliope.locale.yaml d'esempio per la DGX: tutti i moduli si
   importano, il registro delle capacità dice cosa manca con i passi di Linux.
3. Whisper su un server (stt_motore: server) contro un server HTTP finto con l'API di
   OpenAI: campi della richiesta, testo, ripiego su CPU quando cade, ritorno al server.
4. Backend «openai» della voce contro un vLLM finto (prove/ollama_finto.py): testo in
   streaming, chiamate ai tool a pezzi, chat_template_kwargs, niente reasoning_effort.
5. Cartella dei documenti di xdg-user-dirs; sd_notify senza NOTIFY_SOCKET; lock di uv
   senza torch su Linux; il comando `calliope` del pyproject.

    python prove/prova_linux.py
"""

import json
import os
import subprocess
import sys
import threading
import time
import tomllib
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

import numpy as np  # noqa: E402

errori = 0


def ok(cond, msg):
    global errori
    print(("ok  " if cond else "ERR ") + msg)
    if not cond:
        errori += 1


# ─────────────────────────── 1. VAD senza torch ───────────────────────────
def prova_vad():
    from calliope.vad import SileroOnnx, carica_vad, modello_onnx
    path = modello_onnx()
    ok(path is not None, f"modello ONNX di Silero trovato senza importare silero_vad ({path})")
    if path is None:
        return
    onnx = SileroOnnx(path)
    rng = np.random.default_rng(0)
    rumore = rng.normal(0, 0.01, 512 * 20).astype(np.float32)
    probs = [onnx.prob(rumore[i:i + 512]) for i in range(0, len(rumore), 512)]
    ok(max(probs) < 0.5, f"rumore debole: nessun parlato (max {max(probs):.3f})")

    try:
        from calliope.vad import SileroTorch
        torch_vad = SileroTorch()
    except ImportError:
        print("SALTATA IN PARTE: torch non c'è: confronto con il modello di torch saltato")
        return
    files = sorted((RADICE / "registrazioni").glob("**/*.wav"))[:25]
    finestre, uguali, diff = 0, 0, 0.0
    sorgenti = []
    for f in files:
        with wave.open(str(f)) as w:
            if w.getframerate() != 16000 or w.getnchannels() != 1:
                continue
            sorgenti.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                            .astype(np.float32) / 32768)
    if not sorgenti:          # le registrazioni non sono in git: audio sintetico
        t = np.arange(16000 * 3) / 16000
        voce = (0.3 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 3 * t) > 0))
        sorgenti = [np.concatenate([rumore, voce.astype(np.float32), rumore])]
    for a in sorgenti:
        onnx.reset_states()
        torch_vad.reset_states()
        for i in range(0, len(a) - 511, 512):
            fr = np.ascontiguousarray(a[i:i + 512])
            p1, p2 = torch_vad.prob(fr), onnx.prob(fr)
            diff = max(diff, abs(p1 - p2))
            uguali += (p1 >= 0.5) == (p2 >= 0.5)
            finestre += 1
    ok(uguali == finestre and diff < 1e-3,
       f"onnxruntime = torch su {finestre} finestre di {len(sorgenti)} file "
       f"(differenza massima {diff:.1e}, decisioni uguali {uguali}/{finestre})")
    vad = carica_vad("onnx")
    ok(vad.motore == "onnx", "vad_motore «onnx» forzato")


# ─────────────────────────── 2. DGX simulata ───────────────────────────
SIMULA = r'''
import json, sys, platform, importlib, pkgutil, os
# le librerie native si caricano prima di fingere Linux (numpy guarda os.uname)
import numpy, sounddevice, onnxruntime, httpx, yaml, piper, faster_whisper, ctranslate2
for m in ("pycaw", "comtypes", "win32com", "win32api", "pythoncom", "winrt",
          "screen_brightness_control", "torch", "torchaudio"):
    sys.modules[m] = None
ctranslate2.get_cuda_device_count = lambda: 0      # il wheel aarch64 è solo per CPU
sys.platform = "linux"
platform.machine = lambda: "aarch64"
platform.system = lambda: "Linux"
sys.path.insert(0, sys.argv[1])
import calliope
falliti = []
for mi in pkgutil.walk_packages(calliope.__path__, "calliope."):
    if mi.name in ("calliope.pc.windows", "calliope.agenti._avvio"):
        continue                     # solo Windows; script della sandbox
    try:
        importlib.import_module(mi.name)
    except Exception as e:
        falliti.append(f"{mi.name}: {type(e).__name__}: {e}")
from calliope import capacita
from calliope.config import load_config
from calliope.vad import carica_vad
orig = capacita.importa
capacita.importa = lambda m: None if m == "sounddevice" else orig(m)   # PortAudio assente
cfg = load_config()
cfg.llm_native_url = "http://127.0.0.1:9"          # Ollama spento
reg = capacita.controlla(cfg)
out = {"falliti": falliti, "vad": carica_vad("auto").motore,
       "capacita": {c.nome: [c.stato, c.motivo, c.prossimo_passo] for c in reg.tutte()},
       "pip_documenti": capacita.comando_libreria("python-docx", "documenti")}
print("RISULTATO " + json.dumps(out, ensure_ascii=False))
'''


def prova_dgx_simulata(tmp: Path):
    # calliope.yaml copiato in una cartella vuota: niente segreti.yaml né dgx.yaml veri
    import shutil
    shutil.copy2(RADICE / "calliope.yaml", tmp / "calliope.yaml")
    env = dict(os.environ, PYTHONUTF8="1", CALLIOPE_GESTITA="1",
               CALLIOPE_CONFIG=str(tmp / "calliope.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(tmp / "nessun-dgx.yaml"),
               CALLIOPE_CONFIG_LOCALE=str(RADICE / "setup/linux/calliope.locale.esempio.yaml"))
    r = subprocess.run([sys.executable, "-c", SIMULA, str(RADICE)], cwd=tmp, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    riga = next((x for x in r.stdout.splitlines() if x.startswith("RISULTATO ")), None)
    ok(r.returncode == 0 and riga, "DGX simulata: il controllo gira senza eccezioni"
       + ("" if riga else f" ({(r.stderr or r.stdout)[-300:]})"))
    if not riga:
        return
    res = json.loads(riga[len("RISULTATO "):])
    avvisi = [x for x in r.stdout.splitlines() if "sconosciut" in x or "tipo giusto" in x]
    ok(not avvisi, f"calliope.locale.yaml d'esempio per la DGX senza avvisi {avvisi}")
    ok(not res["falliti"], f"tutti i moduli si importano senza le librerie di Windows "
       f"{res['falliti'][:3]}")
    ok(res["vad"] == "onnx", "senza torch il VAD usa onnxruntime")
    cap = res["capacita"]
    # Su Linux il PC a voce non c'è comunque: «mancante» con il motivo, non «metti
    # pc_enabled a true» (prima installazione sulla DGX, 02/10)
    ok(cap["pc"][0] == "mancante" and "pc_enabled" not in cap["pc"][2],
       f"PC a voce sulla DGX: niente passo su pc_enabled ({cap['pc']})")
    ok(cap["audio"][0] == "mancante" and "libportaudio2" in cap["audio"][2],
       f"PortAudio assente: «sudo apt install libportaudio2» ({cap['audio'][2]})")
    # «attiva» con il modello per la CPU già in cache, «mancante» senza (la DGX vera alla
    # prima installazione): in tutti e due i casi il passo è il server di trascrizione
    ok(cap["stt"][0] in ("attiva", "mancante") and "server di trascrizione" in cap["stt"][2],
       f"Whisper su CPU con il passo per la GPU di Linux ARM ({cap['stt'][2][:60]}…)")
    ok(cap["llm"][0] == "guasta", "Ollama spento: guasta")
    ok("~/.ssh/config" in cap["agenti"][2] and "\\" not in cap["agenti"][2],
       f"agenti: il passo nomina ~/.ssh/config ({cap['agenti']})")
    ok(res["pip_documenti"] == "calliope extra documenti",
       "nell'installazione gestita il passo è «calliope extra», non pip")


def prova_pc_linux():
    """check_pc fuori da Windows con pc_enabled acceso: «mancante» con il motivo."""
    from calliope import capacita
    from calliope.config import Config
    c = Config()
    vero = sys.platform
    for acceso in (True, False):
        c.pc_enabled = acceso
        try:
            sys.platform = "linux"
            r = capacita.check_pc(c)
        finally:
            sys.platform = vero
        # Spento (come nell'esempio della DGX) il passo non deve dire «metti pc_enabled
        # a true»: su Linux non servirebbe
        ok(r["stato"] == "mancante" and "solo su Windows" in r["prossimo_passo"],
           f"check_pc su Linux, pc_enabled={acceso}: {r['motivo']}")


def prova_stt_linux_senza_cache():
    """DGX alla prima installazione: CTranslate2 solo CPU e modello per la CPU non ancora in
    cache. Il passo deve dire il server di trascrizione, non solo «lo scarica al primo
    avvio» (02/10)."""
    import types
    from calliope import capacita
    from calliope.config import Config
    c = Config()
    c.stt_motore, c.whisper_device = "locale", "cuda"
    vero = (sys.platform, capacita._arm, capacita._whisper_in_cache, capacita.importa)
    ct2 = types.SimpleNamespace(get_cuda_device_count=lambda: 0)
    try:
        sys.platform = "linux"
        capacita._arm = lambda: True
        capacita._whisper_in_cache = lambda m, cfg=None: False
        capacita.importa = lambda m: ct2 if m == "ctranslate2" else vero[3](m)
        r = capacita.check_stt(c)
    finally:
        sys.platform, capacita._arm, capacita._whisper_in_cache, capacita.importa = vero
    ok(r["stato"] == "mancante" and "server di trascrizione" in r["prossimo_passo"]
       and "faster-whisper" in r["prossimo_passo"],
       f"Whisper non scaricato su Linux ARM: passo con il server ({r['prossimo_passo'][:70]}…)")


def prova_audio_pipewire():
    """La DGX in ufficio (02/10): PortAudio dà «default» con 64 ingressi anche senza nessun
    microfono, e l'unica uscita di PipeWire è «Dummy Output». Il registro deve dirlo."""
    from calliope import capacita
    nodo = lambda classe, nome, descr: {  # noqa: E731
        "type": "PipeWire:Interface:Node",
        "info": {"props": {"media.class": classe, "node.name": nome,
                           "node.description": descr}}}
    dgx = [nodo("Audio/Sink", "auto_null", "Dummy Output"), {"type": "PipeWire:Interface:Link"}]
    pw = capacita.pipewire_da_dump(dgx)
    ok(pw == {"microfoni": [], "uscite": [], "uscite_finte": ["Dummy Output"]},
       f"pw-dump della DGX: nessun microfono, solo l'uscita finta ({pw})")
    casa = dgx + [nodo("Audio/Source", "alsa_input.usb", "Jabra Speak 510"),
                  nodo("Audio/Sink", "alsa_output.usb", "Jabra Speak 510")]
    pw_casa = capacita.pipewire_da_dump(casa)
    vero = capacita.pipewire_audio
    virtuali = {"microfono": "default", "uscita": "default"}
    try:
        capacita.pipewire_audio = lambda timeout=2.0: pw
        senza = capacita.audio_virtuale_senza_dispositivi(virtuali)
        per_nome = capacita.audio_virtuale_senza_dispositivi(
            {"microfono": "Jabra Speak 510: USB Audio (hw:1,0)", "uscita": "default"})
        capacita.pipewire_audio = lambda timeout=2.0: pw_casa
        con = capacita.audio_virtuale_senza_dispositivi(virtuali)
        capacita.pipewire_audio = lambda timeout=2.0: None
        ignoto = capacita.audio_virtuale_senza_dispositivi(virtuali)
    finally:
        capacita.pipewire_audio = vero
    ok(senza and "nessun microfono" in senza[0], f"senza microfono: guasta ({senza})")
    ok(con is None, "con un microfono e un'uscita USB: niente da dire")
    ok(per_nome is None, "dispositivo scelto per nome: non si guarda PipeWire")
    ok(ignoto is None, "senza pw-dump (Windows, PipeWire spento): non si sa, niente da dire")


# ─────────────────────────── 3. Whisper su un server ───────────────────────────
class ServerSTT:
    def __init__(self):
        self.richieste = []
        self.giu = False
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(n)
                if srv.giu:
                    self.send_response(503)
                    self.end_headers()
                    return
                srv.richieste.append((self.path, self.headers.get("Content-Type", ""), corpo))
                data = json.dumps({"text": " Calliope, che ore sono? "}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.porta = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


def prova_stt_server():
    from calliope import capacita, stt
    from calliope.config import Config
    srv = ServerSTT()
    cfg = Config()
    cfg.stt_motore = "server"
    cfg.stt_url = f"http://127.0.0.1:{srv.porta}/v1"
    cfg.stt_modello = "whisper-large-v3-turbo"

    class CPUFinto:
        chiamate = 0

        def _run(self, audio):
            CPUFinto.chiamate += 1
            return "trascritto su cpu"

    class Prova(stt.ServerTranscriber):
        def _cpu_pronto(self):
            self._cpu = self._cpu or CPUFinto()
            return self._cpu

    capacita.REGISTRO = capacita.Registro()
    t = Prova(cfg)
    ok(t.device == "server" and capacita.REGISTRO.get("stt").stato == "attiva",
       "server di trascrizione: verificato all'avvio, capacità attiva")
    audio = (0.1 * np.sin(np.arange(16000) / 5)).astype(np.float32)
    testo = t.transcribe(audio)
    ok(testo == "Calliope, che ore sono?", f"testo dal server: «{testo}»")
    path, ctype, corpo = srv.richieste[-1]
    ok(path == "/v1/audio/transcriptions" and "multipart/form-data" in ctype,
       "POST multipart su /v1/audio/transcriptions")
    ok(b"RIFF" in corpo and b"whisper-large-v3-turbo" in corpo and b"Conversazione con Calliope"
       in corpo and b'name="language"' in corpo, "WAV, modello, lingua e prompt nella richiesta")
    srv.giu = True
    testo = t.transcribe(audio)
    ok(testo == "trascritto su cpu" and capacita.REGISTRO.get("stt").stato == "guasta",
       "server giù: la frase si trascrive su CPU e la capacità è «guasta»")
    t.transcribe(audio)
    ok(len(srv.richieste) == 2 and CPUFinto.chiamate == 2,
       "dopo un errore il server non si riprova a ogni frase")
    srv.giu = False
    t.RIPROVA_S = 0.0
    testo = t.transcribe(audio)
    ok(testo == "Calliope, che ore sono?" and capacita.REGISTRO.get("stt").stato == "attiva",
       "server tornato: di nuovo sul server, capacità attiva")
    cfg.stt_url = None
    try:
        stt.make_transcriber(cfg)
        ok(False, "stt_motore server senza stt_url va rifiutato")
    except ValueError:
        ok(True, "stt_motore server senza stt_url: errore chiaro")
    # Un server che risponde ma non ha /models (whisper.cpp; il finto risponde 501 al GET):
    # vivo, non «non risponde» (DGX, 02/10)
    cfg.stt_url = f"http://127.0.0.1:{srv.porta}/v1"
    r = capacita._check_stt_server(cfg)
    ok(r["stato"] == "attiva", f"registro: server senza /models (whisper.cpp) attivo ({r['motivo']})")
    prova_riserva_whisper(cfg)
    srv.httpd.shutdown()
    srv.httpd.server_close()
    r = capacita._check_stt_server(cfg)
    ok(r["stato"] == "guasta", f"registro: server spento guasto ({r['motivo']})")
    cfg.stt_url = None
    r = capacita._check_stt_server(cfg)
    ok(r["stato"] == "da_configurare", "registro: server senza indirizzo da configurare")


def prova_riserva_whisper(cfg):
    """Il modello di riserva per la CPU (02/10): sulla DGX mancava, e al primo guasto del
    server faster-whisper l'avrebbe scaricato. Il registro lo dice, il catalogo lo installa
    in models/whisper/<modello>, e Transcriber lo usa da lì."""
    import tempfile
    from calliope import capacita, stt
    from calliope.installa.catalogo import HOST_HF, catalogo, whisper_locale
    vero = capacita._whisper_in_cache
    with tempfile.TemporaryDirectory() as tmp:
        cfg.whisper_cartella = str(Path(tmp) / "whisper")
        a = catalogo(cfg).get("whisper_riserva")
        ok(a is not None and a.tipo == "file" and len(a.files) == 5
           and all(f.sha256 and f.size for f in a.files)
           and all(Path(f.dest).parent == Path(tmp) / "whisper" / cfg.whisper_model
                   for f in a.files) and a.files[-1].dest.endswith("model.bin")
           and "/resolve/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/" in a.files[0].url
           and a.hosts == HOST_HF and "us.aws.cdn.hf.co" in HOST_HF,
           "catalogo: whisper_riserva, 5 file con dimensione e SHA-256, revisione fissa, "
           "model.bin per ultimo, in whisper_cartella/<modello>")
        try:
            capacita._whisper_in_cache = lambda m, cfg=None: (
                True if cfg is not None and whisper_locale(cfg) else False)
            r = capacita._check_stt_server(cfg)
            ok(r["stato"] == "attiva" and "manca il modello Whisper" in r["motivo"]
               and "--installa whisper_riserva" in r["prossimo_passo"]
               and r["dettagli"]["riserva"] is False,
               f"registro: server vivo ma senza modello di riserva lo dice ({r['motivo']}; "
               f"{r['prossimo_passo']})")
            d = Path(cfg.whisper_cartella) / cfg.whisper_model
            d.mkdir(parents=True)
            (d / "config.json").write_text("{}")
            ok(whisper_locale(cfg) is None and stt.modello_whisper(cfg) == cfg.whisper_model,
               "senza model.bin (download a metà) la cartella non vale: si usa il nome")
            (d / "model.bin").write_bytes(b"x")
            ok(stt.modello_whisper(cfg) == str(d), "con i file installati faster-whisper "
               "carica la cartella del catalogo")
            r = capacita._check_stt_server(cfg)
            ok(r["stato"] == "attiva" and not r["motivo"] and r["dettagli"]["riserva"],
               "registro: con il modello di riserva niente da dire")
            ok(capacita._whisper_in_cache.__code__ is not vero.__code__ and
               vero(cfg.whisper_model + "-inesistente", cfg) is True,
               "_whisper_in_cache vero: la cartella del catalogo conta come scaricato")
        finally:
            capacita._whisper_in_cache = vero
            cfg.whisper_cartella = "models/whisper"


# ─────────────────────────── 4. voce su vLLM ───────────────────────────
def prova_voce_vllm():
    sys.path.insert(0, str(RADICE / "prove"))
    from ollama_finto import FakeOllama
    from calliope.brain import OpenAIBackend
    from calliope.config import Config
    fake = FakeOllama(modelli=("gemma4-e4b",))
    fake.avvia()
    port = fake.srv.server_address[1]
    cfg = Config()
    cfg.llm_backend = "openai"
    cfg.llm_base_url = f"http://127.0.0.1:{port}/v1"
    cfg.llm_model = "gemma4-e4b"
    cfg.llm_reasoning_effort = None
    cfg.llm_chat_template_kwargs = {"enable_thinking": False}
    b = OpenAIBackend(cfg)
    fake.copione = [{"content": "Sono le dieci e un quarto."},
                    {"content": "", "tool_calls": [{"name": "casa_comando",
                                                     "arguments": {"frase": "accendi taverna"}}]}]
    tools = [{"type": "function", "function": {"name": "casa_comando", "parameters": {
        "type": "object", "properties": {"frase": {"type": "string"}}}}}]
    pezzi = list(b.stream([{"role": "user", "content": "che ore sono?"}], tools))
    testo = "".join(v for k, v in pezzi if k == "text")
    ok(testo == "Sono le dieci e un quarto." and len([k for k, _ in pezzi if k == "text"]) > 1,
       "testo in streaming a pezzi")
    corpo = fake.richieste[-1]
    ok(corpo.get("chat_template_kwargs") == {"enable_thinking": False}
       and "reasoning_effort" not in corpo and "num_ctx" not in json.dumps(corpo),
       "chat_template_kwargs inviato, niente reasoning_effort né num_ctx")
    pezzi = list(b.stream([{"role": "user", "content": "accendi taverna"}], tools))
    calls = [v for k, v in pezzi if k == "calls"]
    ok(calls and calls[0][0]["name"] == "casa_comando"
       and calls[0][0]["arguments"] == {"frase": "accendi taverna"},
       "chiamata al tool ricomposta dai pezzi (come vLLM)")
    cfg.llm_chat_template_kwargs = None
    cfg.llm_reasoning_effort = "none"
    b = OpenAIBackend(cfg)
    list(b.stream([{"role": "user", "content": "ciao"}], None))
    ok("chat_template_kwargs" not in fake.richieste[-1]
       and fake.richieste[-1].get("reasoning_effort") == "none",
       "con Ollama (predefinito) il corpo resta quello di prima")
    fake.srv.shutdown()


def prova_template_gemma4():
    # 03/10: il modello di chat della voce (setup/linux/motore/gemma4_template.py) mette il
    # canale di pensiero vuoto anche dopo il risultato di un tool; idempotente; un modello
    # che non è quello di Gemma 4 si rifiuta
    sys.path.insert(0, str(RADICE / "setup" / "linux" / "motore"))
    import gemma4_template as g
    coda = ("{%- if add_generation_prompt -%}\n"
            "    {%- if ns.prev_message_type != 'tool_response' and ns.prev_message_type != "
            "'tool_call' -%}\n        {{- '<|turn>model\\n' -}}\n"
            "        {%- if not enable_thinking | default(false) -%}\n"
            "            {{- '<|channel>thought\\n<channel|>' -}}\n        {%- endif -%}\n"
            "    {%- endif -%}\n{%- endif -%}")
    out = g.corretto("{{- bos_token -}}\n" + coda)
    ok(out.count("<|channel>thought\\n<channel|>") == 2
       and "{%- elif not enable_thinking" in out and out.rstrip().endswith("{%- endif -%}"),
       "modello di chat di Gemma 4: canale vuoto anche dopo un tool")
    ok(g.corretto(out) == out, "modello di chat di Gemma 4: correzione idempotente")
    try:
        g.corretto("{{ messages }}")
        rifiuta = False
    except ValueError:
        rifiuta = True
    ok(rifiuta, "modello di chat inatteso: rifiutato, non corretto alla cieca")


# ─────────────────────────── 5. varie ───────────────────────────
def prova_varie(tmp: Path):
    from calliope.documenti.consegna import xdg_documents
    home = Path.home()
    conf = tmp / "config"
    conf.mkdir()
    (conf / "user-dirs.dirs").write_text('# commento\nXDG_DESKTOP_DIR="$HOME/Scrivania"\n'
                                         'XDG_DOCUMENTS_DIR="$HOME/Documenti"\n')
    vecchio = os.environ.pop("XDG_DOCUMENTS_DIR", None)
    try:
        ok(xdg_documents(conf) == home / "Documenti",
           "xdg-user-dirs: «~/Documenti» del desktop in italiano")
        (conf / "user-dirs.dirs").write_text('XDG_DOCUMENTS_DIR="$HOME/"\n')
        ok(xdg_documents(conf) is None, "cartella disattivata (la home): ripiego su ~/Documents")
        ok(xdg_documents(tmp / "nessuna") is None, "senza user-dirs.dirs: ripiego")
    finally:
        if vecchio is not None:
            os.environ["XDG_DOCUMENTS_DIR"] = vecchio

    from calliope.main import notifica_systemd
    vecchio = os.environ.pop("NOTIFY_SOCKET", None)
    ok(notifica_systemd("READY=1") is False, "sd_notify fuori da systemd: non fa niente")
    if vecchio is not None:
        os.environ["NOTIFY_SOCKET"] = vecchio
    if sys.platform.startswith("linux"):           # pragma: no cover — solo sulla DGX
        import socket
        p = str(tmp / "notify.sock")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.bind(p)
        os.environ["NOTIFY_SOCKET"] = p
        ok(notifica_systemd("READY=1") and s.recv(100) == b"READY=1", "sd_notify vero")
        del os.environ["NOTIFY_SOCKET"]
    # 06/10: NOTIFY_SOCKET tolto all'avvio, i figli non lo ereditano (systemctl 255 mandava
    # «EXIT_STATUS=0»); notifica_systemd continua a funzionare con il valore tenuto
    import calliope.main as M
    vecchio, prima = os.environ.pop("NOTIFY_SOCKET", None), M._NOTIFY_SOCKET
    try:
        os.environ["NOTIFY_SOCKET"] = "/percorso/di/prova.sock"
        ok(M.trattieni_notify_socket() == "/percorso/di/prova.sock"
           and "NOTIFY_SOCKET" not in os.environ
           and M._NOTIFY_SOCKET == "/percorso/di/prova.sock",
           "NOTIFY_SOCKET tolto dall'ambiente dei figli e tenuto per sd_notify")
        ok(M.trattieni_notify_socket() == "/percorso/di/prova.sock",
           "trattieni_notify_socket due volte: il valore resta")
    finally:
        M._NOTIFY_SOCKET = prima
        if vecchio is not None:
            os.environ["NOTIFY_SOCKET"] = vecchio

    lock = tomllib.loads((RADICE / "uv.lock").read_text(encoding="utf-8"))
    pacchetti = {p["name"]: p for p in lock["package"]}
    torch_dip = [d for p in lock["package"] for d in p.get("dependencies", [])
                 if d["name"] in ("torch", "torchaudio")]
    ok(torch_dip and all("win32" in d.get("marker", "") for d in torch_dip),
       "uv.lock: torch solo su Windows (Linux senza CUDA da PyPI)")
    for nome in ("ctranslate2", "onnxruntime", "numpy", "piper-tts", "lxml", "pillow"):
        wheels = [w["url"].rsplit("/", 1)[-1] for w in pacchetti[nome].get("wheels", [])]
        ok(any("aarch64" in w and "manylinux" in w for w in wheels) or
           any("none-any" in w for w in wheels),
           f"uv.lock: {nome} ha un wheel per Linux aarch64")
    proj = tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))
    ep = proj["project"]["scripts"]["calliope"]
    mod, fn = ep.split(":")
    import importlib
    ok(callable(getattr(importlib.import_module(mod), fn, None)), f"comando calliope = {ep}")
    pc = proj["project"]["optional-dependencies"]["pc"]
    ok(all("sys_platform == 'win32'" in d for d in pc), "extra «pc» solo su Windows")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    import tempfile
    import shutil
    tmp = Path(tempfile.mkdtemp(prefix="calliope-linux-"))
    t0 = time.perf_counter()
    try:
        prova_vad()
        prova_dgx_simulata(tmp)
        prova_pc_linux()
        prova_stt_linux_senza_cache()
        prova_audio_pipewire()
        prova_stt_server()
        prova_voce_vllm()
        prova_template_gemma4()
        prova_varie(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{time.perf_counter() - t0:.1f} s. " + ("Tutto a posto." if not errori
                                                     else f"{errori} errori."))
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
