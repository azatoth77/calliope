import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco: microfono, casse e webcam del satellite nella sezione satellite (05/10).

Dario: «audio e pc non fanno parte del satellite rappresentato dal portatile? mi aspettavo che
quelle impostazioni fossero sotto satellite». Ora il satellite legge satellite_microfono,
satellite_casse e satellite_webcam; input_device, output_device e pc_webcam restano per
Calliope completa e valgono per il satellite solo da ripiego, con un avviso.

- priorità: chiave del satellite (file locale o CALLIOPE_SATELLITE_*) > chiave vecchia (con
  avviso «spostala») > predefiniti di avvia_satellite.py > quelli del sistema;
- il file d'esempio separa server (server_satelliti) e satellite (satellite); un file locale
  vecchio con audio_modo sotto «satellite:» si legge come prima;
- la scelta arriva a scegli_dispositivi (dispositivo trovato per nome o predefinito) e alla
  webcam dell'esecutore; l'installatore dei PC nuovi scrive le chiavi nuove.
"""

import contextlib
import io
import tempfile
import types
from pathlib import Path

from calliope.config import (ENV_OVERRIDES, SEZIONI, dispositivi_satellite, example_yaml,
                             load_config)

sys.stdout.reconfigure(encoding="utf-8")
errori = 0
radice = Path(__file__).resolve().parent.parent
VARIABILI = ("CALLIOPE_SATELLITE_MICROFONO", "CALLIOPE_SATELLITE_CASSE",
             "CALLIOPE_SATELLITE_WEBCAM", "CALLIOPE_INPUT_DEVICE", "CALLIOPE_OUTPUT_DEVICE",
             "CALLIOPE_AUDIO_MODO", "CALLIOPE_CONFIG", "CALLIOPE_CONFIG_LOCALE")
for v in VARIABILI:
    os.environ.pop(v, None)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


tmp = Path(tempfile.mkdtemp())
(tmp / "calliope.yaml").write_text(example_yaml(), encoding="utf-8")


def carica(locale: str, env: dict | None = None, predefiniti=None):
    """Config con questo calliope.locale.yaml e queste variabili, poi la scelta del satellite.
    Restituisce (cfg, origini, avvisi)."""
    (tmp / "calliope.locale.yaml").write_text(locale, encoding="utf-8")
    env = env or {}
    for k, v in env.items():
        os.environ[k] = v
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cfg = load_config(str(tmp / "calliope.yaml"))
        avvisi: list[str] = []
        origini = dispositivi_satellite(cfg, predefiniti, avvisa=avvisi.append)
        return cfg, origini, avvisi
    finally:
        for k in env:
            os.environ.pop(k, None)


# 1. Le chiavi nuove nella sezione satellite
cfg, origini, avvisi = carica("satellite:\n  satellite_microfono: C920 MME\n"
                              "  satellite_casse: 3\n  satellite_webcam: HD Pro Webcam C920\n")
verifica("chiavi del satellite: microfono per nome, casse per numero, webcam",
         (cfg.input_device, cfg.output_device, cfg.pc_webcam)
         == ("C920 MME", 3, "HD Pro Webcam C920") and not avvisi
         and set(origini.values()) == {"satellite"}, f"{origini} {avvisi}")

# 2. Le vecchie (audio, pc) come ripiego, con l'avviso che dice dove spostarle
cfg, origini, avvisi = carica("audio:\n  input_device: C920 MME\n  output_device: I52 MME\n"
                              "pc:\n  pc_webcam: HD Pro Webcam C920\n")
verifica("chiavi vecchie: usate dal satellite (ripiego)",
         (cfg.satellite_microfono, cfg.satellite_casse, cfg.satellite_webcam)
         == ("C920 MME", "I52 MME", "HD Pro Webcam C920")
         and (cfg.input_device, cfg.output_device) == ("C920 MME", "I52 MME")
         and set(origini.values()) == {"ripiego"}, str(origini))
verifica("chiavi vecchie: un avviso per chiave con il nome nuovo e la sezione",
         len(avvisi) == 3 and all("sezione satellite" in a for a in avvisi)
         and any("satellite_microfono: C920 MME" in a for a in avvisi)
         and any("satellite_webcam: HD Pro Webcam C920" in a for a in avvisi), " | ".join(avvisi))

# 3. Le nuove vincono sulle vecchie, senza avvisi
cfg, origini, avvisi = carica("audio:\n  input_device: Microfono vecchio\n"
                              "satellite:\n  satellite_microfono: C920 MME\n")
verifica("la chiave del satellite vince su input_device, senza avviso",
         cfg.input_device == "C920 MME" and not avvisi, f"{cfg.input_device} {avvisi}")

# 4. Variabili d'ambiente (lette all'import di config, come per input_device: in un processo
#    a parte): CALLIOPE_SATELLITE_* vincono sul file; la vecchia avvisa
FIGLIO = """
import contextlib, io, json, sys
sys.path.insert(0, sys.argv[1])
from calliope.config import dispositivi_satellite, load_config
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(sys.argv[2])
avvisi = []
dispositivi_satellite(cfg, avvisa=avvisi.append)
print(json.dumps([cfg.input_device, cfg.output_device, cfg.pc_webcam, avvisi]))
"""


def figlio(locale: str, env: dict):
    import json
    import subprocess
    (tmp / "calliope.locale.yaml").write_text(locale, encoding="utf-8")
    amb = {k: v for k, v in os.environ.items() if k not in VARIABILI}
    amb.update(env)
    r = subprocess.run([sys.executable, "-c", FIGLIO, str(radice), str(tmp / "calliope.yaml")],
                       capture_output=True, text=True, encoding="utf-8", env=amb, timeout=60)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return [None, None, None, [r.stderr[-300:]]]


mic, casse, cam, avvisi = figlio("satellite:\n  satellite_microfono: C920 MME\n",
                                 {"CALLIOPE_SATELLITE_MICROFONO": "Yeti MME",
                                  "CALLIOPE_SATELLITE_WEBCAM": "Logi"})
verifica("CALLIOPE_SATELLITE_MICROFONO e _WEBCAM vincono sul file",
         (mic, cam) == ("Yeti MME", "Logi") and not avvisi, f"{mic} {cam} {avvisi}")
mic, casse, cam, avvisi = figlio("", {"CALLIOPE_INPUT_DEVICE": "C920 MME"})
verifica("CALLIOPE_INPUT_DEVICE: ripiego con l'avviso di usare CALLIOPE_SATELLITE_MICROFONO",
         mic == "C920 MME" and len(avvisi) == 1
         and "CALLIOPE_SATELLITE_MICROFONO" in avvisi[0], " | ".join(map(str, avvisi)))
verifica("variabili nuove tra gli override d'ambiente",
         {ENV_OVERRIDES.get(k) for k in ("satellite_microfono", "satellite_casse",
                                         "satellite_webcam")}
         == {"CALLIOPE_SATELLITE_MICROFONO", "CALLIOPE_SATELLITE_CASSE",
             "CALLIOPE_SATELLITE_WEBCAM"})

# 5. I predefiniti di avvia_satellite.py valgono solo se la configurazione non sceglie
import avvia_satellite  # noqa: E402
cfg, origini, avvisi = carica("", predefiniti=avvia_satellite.PREDEFINITI)
verifica("avvia_satellite.py: C920 e I52 se la configurazione tace",
         (cfg.input_device, cfg.output_device, cfg.pc_webcam) == ("C920 MME", "I52 MME", "")
         and origini == {"satellite_microfono": "predefinito", "satellite_casse": "predefinito",
                         "satellite_webcam": "sistema"}, str(origini))
cfg, origini, avvisi = carica("satellite:\n  satellite_casse: Altoparlanti MME\n",
                              predefiniti=avvia_satellite.PREDEFINITI)
verifica("avvia_satellite.py: il file vince sui suoi predefiniti (prima era il contrario)",
         (cfg.input_device, cfg.output_device) == ("C920 MME", "Altoparlanti MME"),
         f"{cfg.input_device} {cfg.output_device}")
cfg, origini, avvisi = carica("")
verifica("niente scelto: quelli del sistema",
         (cfg.input_device, cfg.output_device, cfg.pc_webcam) == (None, None, "")
         and set(origini.values()) == {"sistema"} and not avvisi)

# 6. Il file d'esempio: server e satellite in due sezioni
es = example_yaml()
verifica("esempio: sezione satellite con microfono, casse e webcam",
         all(k in SEZIONI["satellite"] for k in ("satellite_microfono", "satellite_casse",
                                                  "satellite_webcam", "satellite_server")))
verifica("esempio: audio_modo, indirizzo, porta e TLS nella sezione del server",
         all(k in SEZIONI["server_satelliti"] for k in ("audio_modo", "satellite_indirizzo",
                                                        "satellite_porta", "satellite_tls_cert"))
         and "audio_modo" not in SEZIONI["satellite"])
verifica("esempio: le sezioni dicono a chi servono",
         "server_satelliti:\n  # == Lato server" in es and "satellite:\n  # == Lato satellite" in es
         and "audio:\n  # == Calliope completa" in es)
cfg, _, _ = carica("satellite:\n  audio_modo: satellite\n  satellite_indirizzo: 0.0.0.0\n")
verifica("file locale vecchio (audio_modo sotto satellite:) letto come prima",
         (cfg.audio_modo, cfg.satellite_indirizzo) == ("satellite", "0.0.0.0"))

# 7. La scelta arriva a scegli_dispositivi: trovato per nome, o predefinito se manca
from calliope.satellite.__main__ import scegli_dispositivi  # noqa: E402
presenti = {"input": {"C920 MME": "Microfono (C920)"}, "output": {}}


def query(dev=None, kind=None):
    if dev is None:
        return {"name": {"input": "Microfono interno", "output": "Altoparlanti"}[kind]}
    if dev not in presenti[kind]:
        raise ValueError(dev)
    return {"name": presenti[kind][dev]}


cfg, _, _ = carica("satellite:\n  satellite_microfono: C920 MME\n  satellite_casse: I52 MME\n")
righe: list[str] = []
nomi = scegli_dispositivi(cfg, righe.append, query=query)
verifica("satellite: microfono della sezione satellite trovato, casse assenti → predefinite",
         nomi == {"microfono": "Microfono (C920)", "uscita": "Altoparlanti"}
         and any("I52 MME" in r and "predefinito" in r for r in righe), " / ".join(righe))

# 8. La webcam arriva all'esecutore del satellite (LocalWindowsExecutor finto)
if sys.platform == "win32":
    from calliope.satellite import esecutore as E
    visto = {}

    class PcFinto:
        def __init__(self, nome, app, risultati, webcam=""):
            visto["webcam"] = webcam

        def __getattr__(self, nome):
            raise AttributeError(nome)

    modulo = types.ModuleType("calliope.pc.windows")
    modulo.LocalWindowsExecutor = PcFinto
    vero = sys.modules.get("calliope.pc.windows")
    sys.modules["calliope.pc.windows"] = modulo
    try:
        cfg, _, _ = carica("satellite:\n  satellite_webcam: HD Pro Webcam C920\n"
                           "pc:\n  pc_enabled: true\n  pc_webcam: Altra\n")
        cfg.documenti_cartella = str(tmp / "documenti")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                E.crea_esecutore(cfg, log=lambda m: None)
        except Exception:  # noqa: BLE001 — conta solo la webcam passata
            pass
        verifica("esecutore del satellite: la webcam di satellite_webcam",
                 visto.get("webcam") == "HD Pro Webcam C920", str(visto))
    finally:
        if vero is not None:
            sys.modules["calliope.pc.windows"] = vero
        else:
            sys.modules.pop("calliope.pc.windows", None)

# 9. L'installatore dei PC nuovi scrive le chiavi nuove
ps1 = (radice / "calliope" / "satellite" / "installazione" / "installa.ps1").read_text(
    encoding="utf-8")
verifica("installa.ps1: satellite_microfono, satellite_casse, satellite_webcam",
         all(f"  {k}:" in ps1 for k in ("satellite_microfono", "satellite_casse",
                                         "satellite_webcam"))
         and "input_device" not in ps1)

print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
