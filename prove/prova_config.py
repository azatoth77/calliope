import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della configurazione YAML (calliope/config.py, roadmap 2 del 26/09/2026).

- calliope.yaml generato dal sorgente deve dare esattamente i valori di Config();
- una variabile d'ambiente CALLIOPE_* vince sul file;
- chiavi sconosciute e tipi sbagliati si segnalano (con suggerimento) senza fermarsi;
- il file d'esempio rigenerato coincide con calliope.yaml in radice.
"""

import contextlib
import io
import tempfile
from dataclasses import asdict
from pathlib import Path

from calliope.config import Config, example_yaml, load_config

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


radice = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())

# 1. Il file d'esempio rigenerato dà gli stessi valori dei predefiniti
esempio = tmp / "esempio.yaml"
esempio.write_text(example_yaml(), encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(esempio))
diff = {k: (v, getattr(Config(), k)) for k, v in asdict(cfg).items() if v != getattr(Config(), k)}
verifica("file d'esempio = predefiniti", not diff, str(diff))

# 2. calliope.yaml in radice è aggiornato rispetto al sorgente
verifica("calliope.yaml in radice aggiornato",
         (radice / "calliope.yaml").read_text(encoding="utf-8").strip() == example_yaml().strip())

# 3. Un valore nel file cambia la configurazione; l'ambiente vince sul file
f = tmp / "prova.yaml"
f.write_text("llm:\n  llm_temperature: 0.7\nwake_word:\n  wake_mode: testo\n", encoding="utf-8")
vecchio = os.environ.pop("CALLIOPE_WAKE_MODE", None)
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(f))
verifica("valori dal file", (cfg.llm_temperature, cfg.wake_mode) == (0.7, "testo"))
os.environ["CALLIOPE_WAKE_MODE"] = "modello"
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(f))
verifica("l'ambiente vince sul file", cfg.wake_mode == "modello", cfg.wake_mode)
if vecchio is None:
    os.environ.pop("CALLIOPE_WAKE_MODE")
else:
    os.environ["CALLIOPE_WAKE_MODE"] = vecchio

# 4. Errori nel file: segnalati, non bloccano
f.write_text("llm:\n  llm_temperatura: 0.7\n  llm_num_ctx: tanti\nidentitaa:\n  name: X\n",
             encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    cfg = load_config(str(f))
log = out.getvalue()
verifica("chiave sbagliata segnalata con suggerimento", "forse «llm_temperature»" in log, log.strip())
verifica("tipo sbagliato segnalato, resta il predefinito",
         "llm_num_ctx" in log and cfg.llm_num_ctx == Config().llm_num_ctx)
verifica("sezione sbagliata segnalata", "forse «identita»" in log)

# 5. File mancante: predefiniti
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(tmp / "non-esiste.yaml"))
verifica("file mancante → predefiniti", asdict(cfg) == asdict(Config()))

# 6. calliope.locale.yaml (accanto al file, fuori da git) vince su calliope.yaml;
#    l'ambiente vince su tutti e due (01/10)
base = tmp / "base"
base.mkdir()
(base / "calliope.yaml").write_text("llm:\n  llm_temperature: 0.7\n", encoding="utf-8")
(base / "calliope.locale.yaml").write_text(
    "llm:\n  llm_temperature: 0.2\ncasa:\n  casa_url: https://192.168.0.10:8123\n", encoding="utf-8")
vecchio_locale = os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "calliope.yaml"))
verifica("file locale accanto: vince su calliope.yaml",
         (cfg.llm_temperature, cfg.casa_url) == (0.2, "https://192.168.0.10:8123"),
         str((cfg.llm_temperature, cfg.casa_url)))
os.environ["CALLIOPE_CONFIG_LOCALE"] = str(tmp / "non-esiste-locale.yaml")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "calliope.yaml"))
verifica("CALLIOPE_CONFIG_LOCALE sceglie un altro file (qui assente)", cfg.llm_temperature == 0.7)
if vecchio_locale is None:
    os.environ.pop("CALLIOPE_CONFIG_LOCALE")
else:
    os.environ["CALLIOPE_CONFIG_LOCALE"] = vecchio_locale

# 7. Reti (03/10): un nome sbagliato in llm_reti_spente si segnala; quelle dei file si
#    aggiungono a quelle del profilo; il profilo del 26B tiene accesa TextCallGuard
(base / "reti.yaml").write_text("llm:\n  llm_profilo: gemma4-26b-ollama\n"
                                "  llm_reti_spente: [citazione_tolta, spinta_dichiarta]\n",
                                encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    cfg = load_config(str(base / "reti.yaml"))
log = out.getvalue()
verifica("rete sconosciuta segnalata con suggerimento", "forse «spinta_dichiarata»" in log,
         log.strip()[-200:])
verifica("reti dei file aggiunte a quelle del profilo",
         "citazione_tolta" in cfg.llm_reti_spente and "spinta_promessa" in cfg.llm_reti_spente,
         str(cfg.llm_reti_spente))
verifica("26B: TextCallGuard e chiamata_in_mezzo accese, ricerca_promessa spenta",
         (cfg.rete("textcallguard"), cfg.rete("chiamata_in_mezzo"), cfg.rete("ricerca_promessa")),
         str(cfg.llm_reti_spente))
from calliope.config import PROFILI_LLM, RETI
verifica("profili: solo nomi di reti veri", all(r in RETI for p in PROFILI_LLM.values()
                                                 for r in p.get("llm_reti_spente", ())))

# 7b. Categorie delle reti (06/10, P6): «modello» si spegne da un profilo, «sicurezza» mai
from calliope.config import MODELLO, SICUREZZA, check_reti, reti_di
verifica("reti: ognuna con categoria e perché",
         all(r.categoria in (MODELLO, SICUREZZA) and r.perche.strip() for r in RETI.values()),
         str([n for n, r in RETI.items() if r.categoria not in (MODELLO, SICUREZZA)]))
verifica("profili: spengono solo reti del modello",
         all(RETI[r].categoria == MODELLO for p in PROFILI_LLM.values()
             for r in p.get("llm_reti_spente", ())))
import re as _re
usate = set(_re.findall(r'_net\("([a-z_]+)"\)', (radice / "calliope" / "brain.py").read_text(
    encoding="utf-8"))) | set(_re.findall(r'rete\("([a-z_]+)"\)', (
        radice / "calliope" / "ciclo.py").read_text(encoding="utf-8")))   # il ciclo (06/10, P8)
verifica("reti usate nel codice: tutte in RETI",
         usate and all(RETI.get(n) is not None for n in usate),
         str(sorted(n for n in usate if n not in RETI)))
# Q6 dell'analisi del 06/10: le reti di sicurezza hanno un effetto vero nel codice (prima
# nessuna chiamata cfg.rete per loro), e il consenso non si spegne da un profilo
verifica("reti di sicurezza usate davvero: azione_in_sospeso e riferire",
         {"azione_in_sospeso", "riferire"} <= usate
         and RETI["azione_in_sospeso"].categoria == SICUREZZA, str(sorted(usate)))
verifica("il ciclo non guarda più uscita_controllo (è la rete «riferire»)",
         "uscita_controllo" not in (radice / "calliope" / "ciclo.py").read_text("utf-8"))
c = Config()
c.llm_profilo, c.llm_reti_spente = "provato", ["politica", "permessi", "textcallguard"]
out = io.StringIO()
with contextlib.redirect_stdout(out):
    check_reti(c)
verifica("una rete di sicurezza in llm_reti_spente: segnalata e tolta, resta accesa",
         "è di sicurezza" in out.getvalue() and c.llm_reti_spente == ["textcallguard"]
         and c.rete("politica") and not c.rete("textcallguard"), out.getvalue())
c.llm_reti_spente = ["tutte"]
verifica("«tutte» spegne solo le reti del modello",
         all(c.rete(n) for n in reti_di(SICUREZZA)) and not any(c.rete(n)
                                                              for n in reti_di(MODELLO)))
verifica("«tutte»: azione in sospeso e riferire restano accese",
         c.rete("azione_in_sospeso") and c.rete("riferire"))
c.uscita_controllo = False
out = io.StringIO()
with contextlib.redirect_stdout(out):
    check_reti(c)
verifica("uscita_controllo: false segnalato e ignorato (resta acceso)",
         c.uscita_controllo and "riferire" in out.getvalue(), out.getvalue())
(base / "ignoto.yaml").write_text("llm:\n  llm_profilo: modello-mai-visto\n", encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "ignoto.yaml"))
verifica("profilo sconosciuto: tutte le reti accese",
         not cfg.llm_reti_spente and all(cfg.rete(n) for n in RETI), str(cfg.llm_reti_spente))
# Il registro dei turni scrive profilo e modello in ogni turno (la misura per profilo)
from calliope.turnlog import TurnLog
tl = TurnLog(str(base / "registro"), modello={"profilo": "gemma4-26b-ollama",
                                              "modello": "gemma4:26b", "vuoto": None})
tl.write({"testo": "ciao", "regole": ["textcallguard"]})
import json as _json
riga = _json.loads(next((base / "registro").glob("turni-*.jsonl")).read_text(
    encoding="utf-8").splitlines()[-1])
verifica("registro dei turni: profilo e modello in ogni turno",
         riga.get("profilo") == "gemma4-26b-ollama" and riga.get("modello") == "gemma4:26b"
         and "vuoto" not in riga, str(riga))

# 8. llm_keep_alive (03/10): «-1» come testo faceva rispondere 400 a Ollama. Numeri e durate
#    con l'unità passano, «-1» diventa -1, il resto si segnala e resta il valore di prima;
#    il profilo del 26B lo vuole sempre caricato, ma solo se i file non dicono niente
from calliope.config import keep_alive_valido
casi = {"-1": -1, -1: -1, "30m": "30m", "-1m": "-1m", "24h": "24h", "1h30m": "1h30m",
        300: 300, "0": 0, 2.5: 2.5}
verifica("keep_alive: numeri e durate valide", all(keep_alive_valido(k) == v
                                                     for k, v in casi.items()),
         str({k: keep_alive_valido(k) for k in casi}))
sbagliati = []
for v in ("sempre", "30 minuti", "-1 m", "m", "", True):
    try:
        keep_alive_valido(v)
        sbagliati.append(v)
    except ValueError:
        pass
verifica("keep_alive: «sempre», «30 minuti», «-1 m», vuoto rifiutati", not sbagliati,
         str(sbagliati))
for testo, atteso in (('"-1"', -1), ("-1", -1), ('"-1m"', "-1m"), ("24h", "24h"),
                      ("sempre", "30m")):
    (base / "ka.yaml").write_text(f"llm:\n  llm_keep_alive: {testo}\n", encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cfg = load_config(str(base / "ka.yaml"))
    verifica(f"llm_keep_alive: {testo} = {atteso!r}", cfg.llm_keep_alive == atteso
             and (atteso != "30m" or "non è valido" in out.getvalue()),
             f"{cfg.llm_keep_alive!r} {out.getvalue().strip()[-120:]}")
(base / "ka.yaml").write_text("llm:\n  llm_profilo: gemma4-26b-ollama\n", encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "ka.yaml"))
verifica("profilo del 26B senza keep_alive nei file: -1 (sempre caricato)",
         cfg.llm_keep_alive == -1, repr(cfg.llm_keep_alive))
(base / "ka.yaml").write_text("llm:\n  llm_profilo: gemma4-26b-ollama\n"
                              "  llm_keep_alive: 2h\n", encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "ka.yaml"))
verifica("profilo del 26B con keep_alive nei file: vale il file", cfg.llm_keep_alive == "2h",
         repr(cfg.llm_keep_alive))
(base / "ka.yaml").write_text("llm:\n  llm_profilo: gemma4-e4b-ollama\n", encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "ka.yaml"))
verifica("profilo del 4B: keep_alive predefinito (30m)", cfg.llm_keep_alive == "30m",
         repr(cfg.llm_keep_alive))


# 9. keep_alive (04/10): il «30m» dell'esempio in calliope.yaml non toglie il -1 del profilo
#    (nel file locale sì: lì è una scelta), e CALLIOPE_LLM_KEEP_ALIVE vince su tutto
(base / "ka.yaml").write_text("llm:\n  llm_profilo: gemma4-26b-ollama\n"
                              "  llm_keep_alive: 30m\n", encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    cfg = load_config(str(base / "ka.yaml"))
verifica("profilo del 26B con il 30m dell'esempio in calliope.yaml: -1",
         cfg.llm_keep_alive == -1, repr(cfg.llm_keep_alive))
(base / "ka_locale.yaml").write_text("llm:\n  llm_keep_alive: 30m\n", encoding="utf-8")
(base / "ka.yaml").write_text("llm:\n  llm_profilo: gemma4-26b-ollama\n", encoding="utf-8")
_prima = os.environ.get("CALLIOPE_CONFIG_LOCALE")
os.environ["CALLIOPE_CONFIG_LOCALE"] = str(base / "ka_locale.yaml")
try:
    with contextlib.redirect_stdout(io.StringIO()):
        cfg = load_config(str(base / "ka.yaml"))
finally:
    if _prima is None:
        os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
    else:
        os.environ["CALLIOPE_CONFIG_LOCALE"] = _prima
verifica("profilo del 26B con 30m nel file locale: vale il 30m (scelto)",
         cfg.llm_keep_alive == "30m", repr(cfg.llm_keep_alive))
(base / "ka.yaml").write_text("llm:\n  llm_profilo: gemma4-26b-ollama\n"
                              "  llm_keep_alive: 2h\n", encoding="utf-8")
for env, atteso in (("-1", -1), ("45m", "45m"), ("", None)):
    os.environ["CALLIOPE_LLM_KEEP_ALIVE"] = env
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cfg = load_config(str(base / "ka.yaml"))
            nudo = Config()
    finally:
        os.environ.pop("CALLIOPE_LLM_KEEP_ALIVE", None)
    verifica(f"CALLIOPE_LLM_KEEP_ALIVE={env!r} vince su file e profilo, anche in Config()",
             cfg.llm_keep_alive == atteso and nudo.llm_keep_alive == atteso,
             f"{cfg.llm_keep_alive!r} {nudo.llm_keep_alive!r}")
os.environ["CALLIOPE_LLM_KEEP_ALIVE"] = "sempre"
try:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        nudo = Config()
finally:
    os.environ.pop("CALLIOPE_LLM_KEEP_ALIVE", None)
verifica("CALLIOPE_LLM_KEEP_ALIVE non valido: segnalato, resta il predefinito",
         nudo.llm_keep_alive == "30m" and "non è valido" in out.getvalue(), out.getvalue())
from calliope.config import ENV_OVERRIDES
verifica("CALLIOPE_LLM_KEEP_ALIVE tra gli override d'ambiente",
         ENV_OVERRIDES.get("llm_keep_alive") == "CALLIOPE_LLM_KEEP_ALIVE")
# Il runner delle prove con Ollama manda il keep_alive della voce
from prove.__main__ import keep_alive_della_voce
verifica("runner: keep_alive della voce letto dalla configurazione",
         keep_alive_della_voce() is not None or not (radice / "calliope.yaml").exists())

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
