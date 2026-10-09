import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del registro delle capacità (calliope/capacita.py, 01/10/2026).

Ambienti finti: file mancanti, libreria mancante, Ollama giù, casa da configurare, persone
registrate o no; il riassunto dell'avvio; l'elenco per il prompt (stabile); il tool
calliope_stato filtrato per livello; `python -m calliope.stato` su una «macchina appena
installata» (librerie bloccate in un sottoprocesso): niente crash, «mancante».
Non legge calliope.locale.yaml né i file veri della biblioteca e dei modelli: tutto in una
cartella temporanea.
"""

import json
import socket
import subprocess
import tempfile
from pathlib import Path

from calliope import capacita
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


def porta_chiusa() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


TMP = Path(tempfile.mkdtemp(prefix="calliope-capacita-"))
os.chdir(TMP)                       # speakers.json e cartelle relative: tutto qui


def cfg_finta(**kw) -> Config:
    c = Config()
    c.llm_native_url = f"http://127.0.0.1:{porta_chiusa()}"     # Ollama giù
    c.biblioteca_mini = str(TMP / "biblioteca" / "wikipedia_it_all_mini_2026-08.zim")
    c.biblioteca_completa = str(TMP / "biblioteca" / "wikipedia_it_all_nopic_2026-08.zim")
    c.biblioteca_ragazzi = str(TMP / "biblioteca" / "vikidia_it_all_nopic_2026-09.zim")
    c.biblioteca_dizionario = str(TMP / "biblioteca" / "wiktionary_it_all_nopic_2026-08.zim")
    c.speaker_model = str(TMP / "models" / "speaker" / "campp.onnx")
    c.wake_model = str(TMP / "wakeword" / "calliope.onnx")
    c.piper_voice = str(TMP / "voices" / "it_IT-serena-high.onnx")
    c.memory_db = str(TMP / "memoria.db")
    c.casa_url = None
    c.config_dir = str(TMP)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# ── controlli in ambienti finti ──
cfg = cfg_finta()
r = capacita.check_llm(cfg)
verifica("Ollama giù → guasta, con il passo", r["stato"] == "guasta" and "Ollama" in r["motivo"]
         and "avvia" in r["prossimo_passo"].lower(), str(r))

r = capacita.check_biblioteca(cfg)
verifica("biblioteca senza file → mancante, propone di scaricarla",
         r["stato"] == "mancante" and "scarica la biblioteca" in r["prossimo_passo"], str(r))

# Dal 01/10 la biblioteca non ha librerie: libzim assente non cambia niente
capacita._SENZA.add("libzim")
r = capacita.check_biblioteca(cfg)
verifica("libzim assente: non conta (lettore in puro Python)", "libzim" not in str(r)
         and r["stato"] == "mancante" and "scarica la biblioteca" in r["prossimo_passo"], str(r))

# Con un file mini vero (piccolo): senza indice la ricerca è ridotta, con l'indice no
from calliope.biblioteca_indice import costruisci  # noqa: E402
from prove.zim_finto import mini_wikipedia  # noqa: E402
(TMP / "biblioteca").mkdir()
Path(cfg.biblioteca_mini).write_bytes(mini_wikipedia())
r = capacita.check_biblioteca(cfg)
verifica("mini senza indice → attiva, «ricerca ridotta», passo: prepara l'indice",
         r["stato"] == "attiva" and "ricerca ridotta" in r["motivo"]
         and "prepara l'indice" in r["prossimo_passo"]
         and r["dettagli"]["indici"] == {"mini": "mancante"}, str(r))
costruisci(cfg.biblioteca_mini, processi=1)
r = capacita.check_biblioteca(cfg)
verifica("biblioteca con il solo mini e il suo indice → attiva, dice cosa manca",
         r["stato"] == "attiva" and "Wikipedia completa" in r["motivo"]
         and "Vikidia" in r["motivo"] and "ridotta" not in r["motivo"], r["motivo"])
from calliope.biblioteca import load_biblioteca  # noqa: E402
capacita.nuovo_registro()
b = load_biblioteca(cfg)
verifica("load_biblioteca senza libzim: aperta, con l'indice", b is not None
         and b.archivi[0].indice is not None
         and capacita.REGISTRO.get("biblioteca").stato == "attiva")
b.close()
capacita._SENZA.discard("libzim")
# Una fonte in più scaricata e verificata che la ricerca non sa usare (WikiMed):
# «scaricate, non ancora usate nella ricerca»
q = TMP / "biblioteca" / "wikipedia_it_medicine_nopic_2026-07.zim"
q.write_bytes(b"q")
Path(str(q) + ".verificato").write_text("x", encoding="utf-8")
r = capacita.check_biblioteca(cfg)
verifica("fonte in più scaricata → non ancora usata nella ricerca",
         "non ancora usate nella ricerca: WikiMed" in r["motivo"]
         and r["dettagli"].get("scaricate_non_usate") == ["WikiMed"], r["motivo"])
# Wikiquote (01/10: citazioni): usata, ma solo con il suo indice
from prove.zim_finto import VOCI, crea_zim  # noqa: E402
w = TMP / "biblioteca" / "wikiquote_it_all_nopic_2026-07.zim"
w.write_bytes(crea_zim(VOCI[:2]))
Path(str(w) + ".verificato").write_text("x", encoding="utf-8")
r = capacita.check_biblioteca(cfg)
verifica("Wikiquote senza indice → lo dice (non «ricerca ridotta»), passo: prepara l'indice",
         "manca l'indice di ricerca per Wikiquote" in r["motivo"]
         and "ridotta" not in r["motivo"] and "prepara l'indice" in r["prossimo_passo"],
         r["motivo"])
costruisci(w, processi=1)
r = capacita.check_biblioteca(cfg)
verifica("Wikiquote con l'indice → «cerca anche in Wikiquote»",
         "cerca anche in Wikiquote" in r["motivo"]
         and r["dettagli"].get("fonti_extra") == ["Wikiquote"], r["motivo"])
cfg.biblioteca_fonti_extra = []
r = capacita.check_biblioteca(cfg)
verifica("Wikiquote spenta in biblioteca_fonti_extra → scaricata, non usata",
         "Wikiquote" in r["dettagli"].get("scaricate_non_usate", []), r["motivo"])

r = capacita.check_chi_parla(cfg)
verifica("modello CAM++ mancante → mancante, --installa modello_chi_parla",
         r["stato"] == "mancante" and "modello_chi_parla" in r["prossimo_passo"], str(r))
Path(cfg.speaker_model).parent.mkdir(parents=True)
Path(cfg.speaker_model).write_bytes(b"m")
if capacita.presente("onnxruntime"):
    r = capacita.check_chi_parla(cfg)
    verifica("nessuno registrato → da_configurare", r["stato"] == "da_configurare"
             and "presentiamo" in r["prossimo_passo"], str(r))
    (TMP / "speakers.json").write_text(json.dumps([
        {"name": "Dario", "admin": True, "voiceprint": [0.1], "model": "campp"},
        {"name": "Bianca", "voiceprint": None, "model": "campp"}]), encoding="utf-8")
    r = capacita.check_chi_parla(cfg)
    verifica("persone registrate, una da rifare → attiva con il passo",
             r["stato"] == "attiva" and r["dettagli"]["amministra"] == ["Dario"]
             and "arruola.py Bianca" in r["prossimo_passo"], str(r))

r = capacita.check_voce(cfg)
verifica("voce mancante → mancante, --installa voce_…",
         r["stato"] in ("mancante",) and "--installa voce_" in r["prossimo_passo"], str(r))
r = capacita.check_wake(cfg)
verifica("modello della wake word mancante → mancante, ripiego testuale",
         r["stato"] == "mancante" and "nel testo" in r["motivo"], str(r))
r = capacita.check_wake(cfg_finta(wake_mode="testo"))
verifica("wake word testuale → attiva con la nota", r["stato"] == "attiva", str(r))
r = capacita.check_casa(cfg)
verifica("casa senza indirizzo → da_configurare, passo per casa_url",
         r["stato"] == "da_configurare" and "casa_url" in r["prossimo_passo"], str(r))
r = capacita.check_memoria(cfg_finta(memory_db=None))
verifica("memoria spenta → da_configurare", r["stato"] == "da_configurare", str(r))
r = capacita.check_documenti(cfg_finta(documenti_enabled=False))
verifica("documenti spenti → da_configurare", r["stato"] == "da_configurare", str(r))
capacita._SENZA.update({"docx", "openpyxl", "fpdf"})
r = capacita.check_documenti(cfg)
verifica("documenti senza librerie → mancante", r["stato"] == "mancante", str(r))
capacita._SENZA.difference_update({"docx", "openpyxl", "fpdf"})

# Un controllo che solleva un'eccezione: «guasta», non un crash
_orig = capacita.CONTROLLI["pc"]
capacita.CONTROLLI["pc"] = lambda c: 1 / 0
r = capacita.controlla_una(cfg, "pc")
verifica("controllo che si rompe → guasta", r["stato"] == "guasta"
         and "ZeroDivisionError" in r["motivo"], str(r))
capacita.CONTROLLI["pc"] = _orig

# ── registro, riassunto, prompt ──
reg = capacita.controlla(cfg)
riass = reg.riassunto()
verifica("riassunto compatto", riass.startswith("Capacità: ") and " attive su 18" in riass
         and "non funziona: modello linguistico (Ollama non risponde)" in riass, riass)
righe = reg.righe_avvio()
verifica("righe dell'avvio: riassunto e passi", righe[0].startswith("[CAPACITÀ]")
         and any("Avvia Ollama" in x for x in righe), "\n".join(righe[:3]))

tools = [s["function"]["name"] for s in build_registry().all_schemas()]
t1 = capacita.testo_prompt(reg, tools)
t2 = capacita.testo_prompt(reg, tools)
verifica("prompt: elenco con cosa c'è e cosa no", "Non disponibili qui:" in t1
         and "biblioteca offline" in t1 and "calliope_stato" in t1, t1)
verifica("prompt: stabile tra due turni", t1 == t2)
v0 = reg.versione
reg.segnala("documenti", "mancante", "mancano le librerie")
verifica("prompt: cambia solo quando cambia una capacità", capacita.testo_prompt(reg, tools)
         != t1 and reg.versione == v0 + 1)
reg.segnala("documenti", "mancante", "mancano le librerie")
verifica("stesso stato segnalato di nuovo: versione invariata", reg.versione == v0 + 1)
t_tools = capacita.testo_prompt(None, tools)
verifica("prompt senza registro: dai tool", "Non disponibili qui: biblioteca offline" in t_tools,
         t_tools)
verifica("prompt di Config con le capacità in fondo",
         Config().prompt_for(False, capacita=t1).endswith(t1)
         and Config().prompt_for(False) == Config().system_prompt)
# Casa con i tool registrati ma HA momentaneamente giù: il prompt la dà per presente
reg.segnala("casa", "guasta", "Home Assistant non risponde")
t_casa = capacita.testo_prompt(reg, tools + ["casa_comando"])
verifica("prompt: casa giù ma collegata → presente",
         "casa (Home Assistant)" in t_casa.split("Non disponibili qui:")[0], t_casa)

# ── il tool calliope_stato per livello ──
reg = capacita.controlla(cfg)


class Spk:
    def __init__(self, level, name="Dario"):
        self.current_level = level
        self.current_speaker = None if level == "ospite" else name


def stato(level, cap="tutte"):
    reg_t = build_registry()
    ctx = ToolContext(cfg=cfg, speakers=None, speaker_ctx=Spk(level), speaker=None,
                      capacita=reg)
    return json.loads(reg_t.call("calliope_stato", {"capacita": cap}, ctx, level))


o = stato("ospite")
verifica("ospite: solo cosa può chiedere", o["risposta_finale"].startswith("Puoi chiedermi")
         and "Ollama" not in o["risposta_finale"] and "amministra" not in o["risposta_finale"],
         o["risposta_finale"])
o = stato("ospite", "biblioteca")
verifica("ospite su una capacità: niente diagnosi", "libzim" not in o["risposta_finale"]
         and "manca" not in o["risposta_finale"], o["risposta_finale"])
f = stato("familiare")
verifica("familiare: le aree e «chiedi a chi amministra»",
         f["risposta_finale"].startswith("Posso aiutarti con") and "chiedi a chi amministra"
         in f["risposta_finale"] and "Ollama" not in f["risposta_finale"], f["risposta_finale"])
f = stato("familiare", "casa")
verifica("familiare su una capacità che manca: senza dettagli",
         "chiedi a chi amministra" in f["risposta_finale"]
         and "casa_url" not in f["risposta_finale"], f["risposta_finale"])
f = stato("familiare", "documenti")
verifica("familiare su una capacità attiva: cosa può chiedere",
         "funzionano" in f["risposta_finale"] and "Puoi chiedermi" in f["risposta_finale"],
         f["risposta_finale"])
a = stato("amministra")
# 09/10 (caso vero: l'elenco intero interrotto): a «cosa sai fare?» le aree e i nomi di ciò che
# non va, il perché solo con «cosa manca?»
verifica("chi amministra: le aree e cosa non va, senza il perché",
         a["risposta_finale"].startswith("Posso aiutarti con")
         and "Non funzionano ancora: modello linguistico, voce, wake word e altre" in
         a["risposta_finale"] and "Ollama non risponde" not in a["risposta_finale"]
         and "«cosa manca?»" in a["risposta_finale"], a["risposta_finale"])
a = stato("amministra", "casa")
verifica("chi amministra su una capacità: motivo e passo",
         "manca casa url" in a["risposta_finale"] and "calliope.locale.yaml"
         in a["risposta_finale"], a["risposta_finale"])
# A voce le chiavi della configurazione non si dicono col trattino basso (e2e del 06/10:
# «perché spento (archivioenabled)»); nel terminale e nei dettagli restano
_reg_k = capacita.Registro()
_reg_k.segnala("archivio", "da_configurare", "spento (archivio_enabled)",
               "In calliope.locale.yaml metti archivio_enabled a true e riavviami.")
_ctx_k = ToolContext(cfg=cfg, speakers=None, speaker_ctx=Spk("amministra"), speaker=None,
                     capacita=_reg_k)
for _cap_k in ("tutte", "archivio"):
    k = json.loads(build_registry().call(
        "calliope_stato", {"capacita": _cap_k, "cosa": "manca" if _cap_k == "tutte" else ""},
        _ctx_k, "amministra"))["risposta_finale"]
    verifica(f"a voce il motivo in parole, senza il nome della chiave ({_cap_k})",
             "_enabled" not in k and "(archivio" not in k
             and "spento nella configurazione" in k, k)
verifica("nel terminale e nei dettagli la chiave resta",
         "archivio_enabled" in _reg_k.riassunto()
         and _reg_k.get("archivio").motivo == "spento (archivio_enabled)", _reg_k.riassunto())
verifica("calliope_stato chiude il turno (risposta_finale)", "risposta_finale" in a)
# Una capacità definita ma non segnalata qui (04/10, 26B: Wikipedia → capacita=web → «Non so
# niente di questa capacità.»): non c'è, e per il web si dice anche della biblioteca
_reg_senza_web = capacita.Registro()
_reg_senza_web.segnala("biblioteca", "mancante", "mancano i file di Wikipedia",
                       "Dimmi «scarica la biblioteca».")
_ctx_w = ToolContext(cfg=cfg, speakers=None, speaker_ctx=Spk("amministra"), speaker=None,
                     capacita=_reg_senza_web)
w = json.loads(build_registry().call("calliope_stato", {"capacita": "web"}, _ctx_w,
                                     "amministra"))["risposta_finale"]
verifica("capacità non segnalata (web): non c'è, e la biblioteca con il suo perché",
         w.startswith("La ricerca su internet in questa installazione non c'è.")
         and "mancano i file di Wikipedia" in w, w)
w = json.loads(build_registry().call("calliope_stato", {"capacita": "schermi"}, _ctx_w,
                                     "amministra"))["risposta_finale"]
verifica("capacità non segnalata (schermi): non ci sono, senza la biblioteca",
         w == "Gli schermi in questa installazione non ci sono.", w)

# ── «cosa manca?»: anche cosa si può aggiungere dal catalogo (01/10, prova a voce) ──
add = capacita.aggiungibili(cfg)
# Qui c'è solo Wikipedia ridotta (con Wikiquote e WikiMed scaricate), nessuna voce
verifica("aggiungibili: le fonti della ricerca che mancano, le altre, le voci (una per nome)",
         [x for x, _ in add["utili"]] == ["biblioteca_completa", "biblioteca_ragazzi",
                                          "biblioteca_dizionario"]
         and "Wikisource" in add["altre"] and "WikiMed" not in add["altre"]
         and "Wikipedia completa con le immagini" not in add["altre"]
         and [n for _, n in add["voci"]] == ["Serena", "Paola", "Riccardo"], str(add))
vuota = cfg_finta(biblioteca_mini=str(TMP / "vuota" / "wikipedia_it_all_mini_2026-08.zim"),
                  biblioteca_completa=None)
add_v = capacita.aggiungibili(vuota)
verifica("aggiungibili: senza Wikipedia la biblioteca intera, poi Wikiquote",
         [x for x, _ in add_v["utili"]] == ["biblioteca", "fonte_wikiquote"], str(add_v))


def stato_cosa(level, cosa, installazioni=True, cap="tutte"):
    reg_t = build_registry()
    ctx = ToolContext(cfg=cfg, speakers=None, speaker_ctx=Spk(level), speaker=None,
                      capacita=reg)
    ctx.installazioni = object() if installazioni else None
    return json.loads(reg_t.call("calliope_stato", {"capacita": cap, "cosa": cosa}, ctx,
                                 level))["risposta_finale"]


a = stato_cosa("amministra", "manca")
verifica("chi amministra, «cosa manca?»: cosa non va, cosa si può aggiungere e come chiederlo",
         not a.startswith("Posso dirti") and "Non funzionano ancora" in a
         and "Vikidia, per le spiegazioni semplici" in a and "le voci Serena, Paola e Riccardo" in a
         and "che per ora non uso nelle risposte" in a and "«scarica Wikipedia completa»" in a, a)
a = stato_cosa("amministra", "sa_fare")
verifica("chi amministra, «cosa sai fare?»: solo le aree, le aggiunte con «cosa manca?»",
         a.startswith("Posso aiutarti con") and "aggiungere" not in a
         and "per le spiegazioni semplici" not in a, a)
a = stato_cosa("amministra", "manca", installazioni=False)
verifica("installazioni spente: niente «dimmi quale installare», il terminale",
         "Dimmi quale" not in a and "python -m calliope.stato" in a, a)
f = stato_cosa("familiare", "manca")
verifica("familiare, «cosa manca?»: solo un cenno, niente nomi né comandi",
         "Chi amministra può aggiungere altre fonti alla biblioteca e altre voci" in f
         and "Wikiquote" not in f and "scarica" not in f, f)
o = stato_cosa("ospite", "manca")
verifica("ospite, «cosa manca?»: niente aggiunte", "aggiung" not in o and o.startswith("Puoi"), o)
f = stato_cosa("familiare", "", cap="biblioteca")
verifica("familiare sulla biblioteca: il cenno alle fonti, non alle voci",
         "Chi amministra può aggiungere altre fonti alla biblioteca." in f and "voci" not in f, f)

# ── python -m calliope.stato su una macchina «appena installata» ──
BLOCCATI = ["numpy", "onnxruntime", "faster_whisper", "ctranslate2", "piper", "sounddevice",
            "libzim", "httpx", "yaml", "websockets", "docx", "openpyxl", "fpdf", "pycaw",
            "comtypes", "win32com", "psutil", "screen_brightness_control", "winrt",
            "huggingface_hub", "starlette", "uvicorn"]
codice = ("import sys\n"
          f"for m in {BLOCCATI!r}: sys.modules[m] = None\n"
          "from calliope.stato import main\n"
          "sys.exit(main(['--json']))\n")
env = dict(os.environ, PYTHONPATH=str(RADICE), PYTHONUTF8="1",
           CALLIOPE_CONFIG_LOCALE=str(TMP / "nessun-file.yaml"))
vuota = Path(tempfile.mkdtemp(prefix="calliope-nuova-"))
p = subprocess.run([sys.executable, "-c", codice], cwd=vuota, env=env, capture_output=True,
                   text=True, encoding="utf-8")
try:
    data = json.loads(p.stdout)
    stati = {c["nome"]: c["stato"] for c in data["capacita"]}
except (ValueError, KeyError):
    data, stati = None, {}
verifica("macchina nuova: esce con 0 e JSON valido", p.returncode == 0 and data is not None,
         p.stderr[-300:])
verifica("macchina nuova: librerie assenti = mancante",
         all(stati.get(k) == "mancante" for k in ("llm", "stt", "voce", "audio", "biblioteca",
                                                  "documenti", "schermi")), str(stati))
verifica("macchina nuova: 18 capacità (con archivio, ufficio, conversazioni e ricerca web), nessun crash", len(stati) == 18, str(stati))
p = subprocess.run([sys.executable, "-m", "calliope.stato"], cwd=vuota, env=env,
                   capture_output=True, text=True, encoding="utf-8")
verifica("tabella da terminale", p.returncode == 0 and "CAPACITÀ" in p.stdout
         and "Prossimi passi:" in p.stdout, p.stderr[-300:])
p = subprocess.run([sys.executable, "-m", "calliope.stato", "--catalogo"], cwd=vuota, env=env,
                   capture_output=True, text=True, encoding="utf-8")
verifica("catalogo da terminale", p.returncode == 0 and "fonte_wikiquote" in p.stdout
         and "pip" in p.stdout, p.stdout[-200:])

# «Su che hardware giri?» (04/10, calliope/macchina.py): la macchina e i modelli, per tutti i
# livelli, senza indirizzi, utenti né percorsi
from types import SimpleNamespace  # noqa: E402
from calliope import macchina  # noqa: E402
for lv in ("ospite", "familiare", "amministra"):
    m = stato_cosa(lv, "macchina")
    verifica(f"hardware ({lv}): computer, memoria e modello della voce",
             m.startswith("Giro su") and "di memoria" in m and "Per parlare uso" in m
             and "Posso dirti" not in m, m)
remota = cfg_finta(llm_native_url="http://192.168.7.21:11434", stt_motore="server",
                   stt_url="http://10.1.2.3:8003/v1")
lav = SimpleNamespace(imp=SimpleNamespace(modello="qwen3.6-35b", su_nome="sulla DGX"))
m = macchina.descrivi(remota, lav)
utente = os.environ.get("USERNAME") or os.environ.get("USER") or "§"
verifica("hardware: modelli remoti senza indirizzo, agente con il nome, niente utente né "
         "percorsi", "192.168" not in m and "10.1.2.3" not in m and "su un altro computer" in m
         and "agente qwen3.6-35b sulla DGX" in m and utente.lower() not in m.lower()
         and "\\" not in m and ":/" not in m, m)
verifica("hardware: memoria come sull'etichetta",
         (macchina._gb(31.46), macchina._gb(119.6), macchina._gb(7.96)) == ("32 GB", "128 GB", "8 GB"))


# Linux (la DGX) con /proc e /sys finti: senza «model name» (ARM) il processore è l'architettura
_finti = {"/sys/class/dmi/id/product_name": "NVIDIA DGX Spark\n",
          "/proc/cpuinfo": "processor\t: 0\nCPU part\t: 0xd85\n",
          "/proc/meminfo": "MemTotal:       125411392 kB\n",
          "/proc/driver/nvidia/gpus/000f:01:00.0/information": "Model: \t\t NVIDIA GB10\n",
          "/etc/os-release": 'PRETTY_NAME="Ubuntu 24.04.3 LTS"\n'}
_leggi, _glob = macchina._leggi, macchina.glob.glob
macchina._leggi = lambda p: _finti.get(p, "")
macchina.glob.glob = lambda pat: [k for k in _finti if k.startswith("/proc/driver/nvidia/")]
try:
    d = macchina._linux()
finally:
    macchina._leggi, macchina.glob.glob = _leggi, _glob
verifica("hardware su Linux: modello, memoria, GPU dai file del sistema",
         (d["modello"], macchina._gb(d["memoria_gb"]), d["gpu"], d["sistema"], d["processore"])
         == ("NVIDIA DGX Spark", "128 GB", [("NVIDIA GB10", None)], "Ubuntu 24.04.3 LTS", ""),
         str(d))

# La DGX vera (04/10): product_name è un codice d'ordine, il nome sta nella famiglia
for nome, famiglia, marca, atteso in (("30KL0005IE", "DGX Spark", "LENOVO", "Lenovo DGX Spark"),
                                     ("Alienware Aurora 16X", "Alienware", "Dell Inc.",
                                      "Alienware Aurora 16X"),
                                     ("30KL0005IE", "", "LENOVO", "30KL0005IE")):
    _finti["/sys/class/dmi/id/product_name"] = nome + "\n"
    _finti["/sys/class/dmi/id/product_family"] = famiglia + "\n"
    _finti["/sys/class/dmi/id/sys_vendor"] = marca + "\n"
    macchina._leggi = lambda p: _finti.get(p, "")
    macchina.glob.glob = lambda pat: [k for k in _finti if k.startswith("/proc/driver/nvidia/")]
    try:
        d = macchina._linux()
    finally:
        macchina._leggi, macchina.glob.glob = _leggi, _glob
    verifica(f"hardware su Linux: «{nome}» → «{atteso}»", d["modello"] == atteso, str(d))


print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
