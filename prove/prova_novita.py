import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco di chi è Calliope, delle sue novità e di «cosa sai fare?» per aree (09/10/2026).

Caso vero (DGX, 09/10): «quali sono le ultime novità sul tuo aggiornamento?» → l'elenco intero
delle capacità, poi «non ho un registro delle versioni» e «il mio codice è distribuito su
diversi server», tutti e due falsi. Qui: CHANGELOG finto (tabella e sezioni, intervalli,
«(notte)», anno), gestore finto (versioni/<id>/, gestione.json con la storia), scelta delle
voci per periodo e dopo la versione di prima, frase per la voce breve e senza host, indirizzi
né percorsi, scheda personale in Markdown con «Scarica»; «chi sei?» con fatti veri e senza il
nome della macchina; «cosa sai fare?» solo per aree, il dettaglio con `area`; l'ospite come
prima; la spinta del prompt. Contrari: niente novità nel periodo → le ultime, voci dopo il
codice installato ignorate, area che non c'è.
"""

import datetime as dt
import json
import socket
import tempfile
from pathlib import Path

from calliope import capacita, novita
from calliope.config import Config
from calliope.schermi.hub import Mittente
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.pc_finto import FakePC

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


CHANGELOG = """# Cambiamenti

Introduzione con un [link](docs/aree/) che non è una voce.

## 0.3 — prima pubblicazione (07/10/2026)

- Codice sotto licenza AGPL; README tecnico ([`docs/installazione.md`](docs/installazione.md)).
- Nessun dato personale nel repository.

## Tappe dello sviluppo

| Data | Tappa |
|---|---|
| 21/09/2026 | Progettazione; primo test a voce completo |
| 22–24/09 | Tool calling nativo, riconoscimento di chi parla |
| 06/10 | Una conversazione per persona con più satelliti; cruscotto di chi amministra |
| 07/10 (dopo la pubblicazione) | Piper sulla GPU e prima frase a pezzi; misura delle pause |
| 08/10 | Casa raggiungibile su http://192.168.1.50:8123 (`calliope stato`); file in `~/calliope/dati.yaml`; il gestore in setup/linux/gestore.py; taratura della macchina (inventario, catalogo); cassetto dei file per persona |
| 08/10 (notte) | Modalità sviluppo: ricollaudo della versione consegnata prima di «è pronto»; nomi capiti male negli argomenti |
| 09/10 | Un «no» alla proposta la chiude e Calliope non la ripropone finché non le si chiede di nuovo; «Sì, però ascolta…» non vale più come consenso |
| 10/10 | Una voce scritta dopo il codice installato |
"""

OGGI = dt.date(2026, 10, 9)

# ── CHANGELOG ──
voci = novita.voci_changelog(CHANGELOG, 2026)
verifica("voci: sezione e righe della tabella, in ordine di file",
         [v["etichetta"][:5] for v in voci] == ["0.3 —", "21/09", "22–24", "06/10", "07/10",
                                                 "08/10", "08/10", "09/10", "10/10"],
         [v["etichetta"] for v in voci])
verifica("voci: intervallo all'ultimo giorno, anno ereditato",
         voci[2]["data"] == dt.date(2026, 9, 24) and voci[0]["data"] == dt.date(2026, 10, 7),
         str([v["data"] for v in voci[:3]]))
verifica("voci: la sezione con il suo elenco in una riga", "Nessun dato personale" in
         voci[0]["testo"] and "AGPL" in voci[0]["testo"], voci[0]["testo"])

codice = dt.date(2026, 10, 9)
s, modo = novita.scegli(voci, "", OGGI, dopo=dt.date(2026, 10, 7), codice=codice)
verifica("dopo la versione di prima (07/10): 08/10, 08/10 notte e 09/10, dalla più recente",
         modo == "aggiornamento" and [v["etichetta"] for v in s] ==
         ["09/10", "08/10 (notte)", "08/10"], str([v["etichetta"] for v in s]))
verifica("contrario: la voce del 10/10 è dopo il codice installato, mai detta",
         all(v["data"] <= codice for v in s))
s, modo = novita.scegli(voci, "", OGGI, codice=codice)
verifica("senza gestore: le ultime due date", modo == "ultime" and
         {v["data"] for v in s} == {dt.date(2026, 10, 9), dt.date(2026, 10, 8)})
s, modo = novita.scegli(voci, "da_ieri", OGGI, codice=codice)
verifica("da ieri: 08/10 e 09/10", modo == "periodo" and
         {v["data"] for v in s} == {dt.date(2026, 10, 9), dt.date(2026, 10, 8)})
s, modo = novita.scegli(voci, "oggi", OGGI, codice=codice)
verifica("oggi: solo il 09/10", modo == "periodo" and [v["etichetta"] for v in s] == ["09/10"])
s, modo = novita.scegli(voci, "settimana", OGGI, codice=codice)
verifica("questa settimana: dal 03/10", modo == "periodo" and len(s) == 6, len(s))
s, modo = novita.scegli(voci, "oggi", dt.date(2026, 10, 20), codice=codice)
verifica("contrario: niente nel periodo → le ultime, e lo dice", modo == "vuoto"
         and [v["etichetta"] for v in s] == ["09/10"])
t, _ = novita.testo_voce(s, modo, "oggi", OGGI)
verifica("contrario: la frase dice che nel periodo non c'è niente", "non ha novità" in t, t)

# ── frase per la voce ──
s, modo = novita.scegli(voci, "", OGGI, dopo=dt.date(2026, 10, 7), codice=codice)
t, fuori = novita.testo_voce(s, modo, "", OGGI)
verifica("voce: breve (al più ~50 parole), con le date dette", len(t.split()) <= 55
         and "il 9 ottobre" in t and fuori, f"{len(t.split())} parole: {t}")
s8 = [v for v in voci if v["etichetta"] == "08/10"]
t8, _ = novita.testo_voce(s8, "ultime", "", OGGI)
verifica("voce: niente indirizzi, host, percorsi, comandi tra apici, parentesi",
         not any(x in t8 for x in ("192.168", "http", "~/", "setup/linux", "gestore.py",
                                   "calliope stato", "(", "`")), t8)
verifica("voce: le parti pulite restano, quelle con indirizzo o percorso escono intere",
         "taratura della macchina" in t8 and "cassetto" in t8 and "raggiungibile" not in t8
         and "file in" not in t8 and "il gestore" not in t8 and "…" not in t8, t8)
verifica("voce: «l'8 ottobre»", "L'8 ottobre" in t8 or "l'8 ottobre" in t8, t8)
verifica("data detta: l'11, il 9, l'anno solo se diverso",
         novita.data_detta(dt.date(2026, 10, 11), OGGI) == "l'11 ottobre"
         and novita.data_detta(dt.date(2025, 9, 1), OGGI) == "il 1 settembre 2025")

# ── gestore finto: versioni/<id>/ con VERSIONE.json, gestione.json con la storia ──
TMP = Path(tempfile.mkdtemp(prefix="calliope-novita-"))
app = TMP / "app"
vid = "20261009-0812-1e0a1440"
rad = app / "versioni" / vid
rad.mkdir(parents=True)
(rad / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
(rad / "pyproject.toml").write_text('[project]\nname = "calliope"\nversion = "0.3.0"\n',
                                    encoding="utf-8")
(rad / "VERSIONE.json").write_text(json.dumps({
    "id": vid, "commit": "1e0a14401234567890", "descrizione": "1e0a144",
    "installata": "2026-10-09 08:15:02"}), encoding="utf-8")
(app / "gestione.json").write_text(json.dumps({
    "sorgente": "ssh://utente@host-finto.example/repo.git", "storia": [
        {"quando": "2026-10-07 16:00:00", "azione": "aggiorna", "da": "x",
         "a": "20261007-1500-11111111", "esito": "ok"},
        {"quando": "2026-10-09 08:16:30", "azione": "aggiorna",
         "da": "20261007-1500-11111111", "a": vid, "esito": "ok"}]}), encoding="utf-8")
v = novita.versione(rad)
verifica("versione dal gestore: numero, commit corto, codice, aggiornata, precedente",
         v["numero"] == "0.3" and v["commit"] == "1e0a144"
         and v["codice"] == dt.datetime(2026, 10, 9, 8, 12)
         and v["aggiornata"] == dt.datetime(2026, 10, 9, 8, 16, 30)
         and v["precedente"] == dt.datetime(2026, 10, 7, 15, 0), str(v))
fv = novita.frase_versione(v, OGGI)
verifica("frase della versione", fv == "Sono la versione 0.3 del 9 ottobre. Mi hanno "
         "aggiornata qui il 9 ottobre alle 8:16.", fv)
r = novita.novita("", rad, OGGI)
verifica("novità dall'ultimo aggiornamento (dopo il 07/10)", "Dall'ultimo aggiornamento" in
         r["frase"] and "il 9 ottobre" in r["frase"] and r["voci"] == 3, r["frase"])
verifica("mai la sorgente del gestore né host", "host-finto" not in r["frase"] + r["markdown"]
         and "ssh://" not in r["markdown"], r["markdown"][:200])
verifica("scheda: Markdown con la versione e le novità intere, link ridotti a testo",
         r["markdown"].startswith("# Novità di Calliope") and "commit 1e0a144" in r["markdown"]
         and "## Le novità" in r["markdown"] and "](docs" not in r["markdown"]
         and "http://" not in r["markdown"], r["markdown"][:300])
r2 = novita.novita("da_ieri", rad, OGGI)
verifica("periodo «da ieri»", r2["frase"].count("Da ieri") == 1, r2["frase"])
(rad / "CHANGELOG.md").unlink()
r3 = novita.novita("", rad, OGGI)
verifica("contrario: senza CHANGELOG lo dice, niente invenzioni",
         "non è in questa installazione" in r3["frase"] and r3["markdown"] == "", r3["frase"])
(rad / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")


# ── il tool ──
class Spk:
    def __init__(self, level, name="Dario"):
        self.current_level = level
        self.current_speaker = None if level == "ospite" else name
        self.from_session = False


class Prof:
    def __init__(self):
        self.id, self.name = "dario-id", "Dario"


class Speakers:
    def get(self, n):
        return Prof() if n == "Dario" else None


class HubFinto:
    """Uno schermo personale di Dario collegato (o nessuno)."""
    def __init__(self, collegato=True):
        self.c = collegato

    def mittente(self, ctx):
        return Mittente(persona="dario-id", nome="Dario", livello="amministra", certo=True,
                        stanza="studio")

    def collegati(self):
        return [{"id": 1, "proprietario": "dario-id", "stanza": "studio"}] if self.c else []


cfg = Config()
cfg.llm_native_url = "http://127.0.0.1:11434"
cfg.llm_model = "gemma4:e4b-it-qat"
reg = capacita.Registro()
for nome in ("llm", "stt", "voce", "chi_parla", "memoria", "pc", "documenti", "casa", "web",
             "schermi", "agenti"):
    reg.segnala(nome, "attiva")
reg.segnala("biblioteca", "mancante", "mancano i file di Wikipedia",
            "Dimmi «scarica la biblioteca».")
tools = build_registry(pc={"portatile": FakePC()}, documenti=("word",), casa=True,
                       schermi=True, agenti=True)


def chiama(level, args, hub=None):
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=Spk(level), speaker=None,
                      capacita=reg)
    ctx.strumenti = tools
    ctx.schermi = hub
    return json.loads(tools.call("calliope_stato", args, ctx, level))


novita._RADICE = rad                          # il codice «installato» è quello finto
r = chiama("amministra", {"cosa": "novita"}, HubFinto())
verifica("tool novita: frase pronta, versione e novità", r.get("risposta_finale", "")
         .startswith("Sono la versione 0.3") and "registro dei cambiamenti" in
         r["risposta_finale"], r.get("risposta_finale"))
sch = r.get("scheda") or {}
verifica("tool novita: scheda personale con il Markdown e «Scarica»",
         sch.get("tipo") == "documento" and sch.get("visibilita") == "personale"
         and sch.get("markdown", "").startswith("# Novità") and "md" in sch.get("scarica", [])
         and sch.get("chiave") == "calliope:novita", str(sch)[:200])
verifica("tool novita: «il resto è sullo schermo» con lo schermo personale collegato",
         "Il resto è sullo schermo." in r["risposta_finale"], r["risposta_finale"])
r = chiama("amministra", {"cosa": "novita"}, HubFinto(collegato=False))
verifica("contrario: schermo non collegato → non lo dice", "sullo schermo" not in
         r["risposta_finale"], r["risposta_finale"])
r = chiama("ospite", {"cosa": "novita", "periodo": "da_ieri"})
verifica("novità anche per l'ospite (il registro è pubblico), senza schermi niente scheda",
         r["risposta_finale"].startswith("Sono la versione") and "scheda" not in r)

ctx_r = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=Spk("familiare"), speaker=None,
                    capacita=reg)
ctx_r.regole = []
r = json.loads(tools.call("calliope_stato", {"periodo": "da_ieri"}, ctx_r, "familiare"))
verifica("solo il periodo («cosa è cambiato da ieri?», modello locale) → novità, regola nel "
         "registro", r["risposta_finale"].startswith("Sono la versione")
         and "Da ieri" in r["risposta_finale"] and ctx_r.regole == ["stato_periodo_novita"],
         f"{ctx_r.regole} {r['risposta_finale'][:80]}")
ctx_r.regole = []
r = json.loads(tools.call("calliope_stato", {"cosa": "sa_fare", "periodo": "da_ieri"}, ctx_r,
                          "familiare"))
verifica("contrario: con cosa=sa_fare il periodo non cambia niente",
         r["risposta_finale"].startswith("Posso aiutarti") and ctx_r.regole == [],
         r["risposta_finale"][:60])
r = chiama("familiare", {"cosa": "chi_sei"})
c = r["risposta_finale"]
host = socket.gethostname()
verifica("chi sei: in casa, su questo computer, modello, niente cloud, AGPL e codice pubblico",
         "Sono" in c and "su questo computer" in c and "gemma4 e4b" in c and "cloud" in c
         and "AGPL" in c and "pubblico" in c and "versione 0.3" in c, c)
verifica("chi sei: niente nome della macchina, indirizzi, percorsi",
         (not host or host.lower() not in c.lower()) and "127.0.0.1" not in c
         and "http" not in c and ":\\" not in c and "/" not in c, c)
verifica("chi sei: con la ricerca web attiva dice quando usa internet",
         "internet lo uso solo per le ricerche" in c, c)
cfg_r = cfg.llm_native_url
cfg.llm_native_url = "http://192.168.1.40:11434"
c2 = chiama("amministra", {"cosa": "chi_sei"})["risposta_finale"]
cfg.llm_native_url = cfg_r
verifica("chi sei: modello su un altro computer della casa, senza l'indirizzo",
         "su un altro computer della casa" in c2 and "192.168.1.40" not in c2, c2)

# ── «cosa sai fare?» per aree ──
r = chiama("amministra", {"capacita": "tutte", "cosa": "sa_fare"}, HubFinto())
f = r["risposta_finale"]
verifica("sa_fare: solo le aree, breve", f.startswith("Posso aiutarti con la casa, l'agenda, "
         "le ricerche, i documenti, il computer, i lavori lunghi, gli schermi")
         and len(f.split()) <= 60 and "luci" not in f and "tapparelle" not in f,
         f"{len(f.split())} parole: {f}")
verifica("sa_fare: cosa non va solo per nome, il perché con «cosa manca?»",
         "Non funziona ancora: biblioteca offline;" in f and "Wikipedia" not in f, f)
verifica("sa_fare: l'esempio di una domanda sull'area e «sullo schermo»",
         "«cosa sai fare con la casa?»" in f and "L'elenco completo è sullo schermo." in f, f)
md = (r.get("scheda") or {}).get("markdown", "")
verifica("sa_fare: la scheda con le aree e il dettaglio",
         "## La casa" in md and "Comandare luci" in md and "## Lavori lunghi e programmi" in md
         and "Costruire con te un programma" in md and "## Ricerche" in md
         and "Non funziona ancora: biblioteca offline" in md, md[:400])
verifica("sa_fare: aree nel risultato", r.get("aree", [])[:3] == ["casa", "agenda", "ricerca"],
         str(r.get("aree")))
r = chiama("amministra", {"cosa": "sa_fare", "area": "casa"})
verifica("area casa: il dettaglio", r["risposta_finale"] ==
         "Con la casa posso comandare luci, tapparelle e termostato di casa.",
         r["risposta_finale"])
r = chiama("familiare", {"cosa": "sa_fare", "area": "agenda"})
verifica("area agenda: «gestire timer…» (non «posso timer»)", r["risposta_finale"]
         .startswith("Con l'agenda posso gestire timer, promemoria"), r["risposta_finale"])
r = chiama("amministra", {"area": "ricerca"})
verifica("area ricerca con la biblioteca che manca: chi amministra sente il perché",
         "cercare su internet" in r["risposta_finale"] and "mancano i file di Wikipedia" in
         r["risposta_finale"], r["risposta_finale"])
r = chiama("familiare", {"area": "ricerca"})
verifica("area ricerca, familiare: senza il perché, «chiedi a chi amministra»",
         "Wikipedia" not in r["risposta_finale"] and "chiedi a chi amministra" in
         r["risposta_finale"], r["risposta_finale"])
r = chiama("amministra", {"area": "esercizi"})
verifica("contrario: area senza tool (esercizi senza minori) → non posso",
         r["risposta_finale"] == "Con i compiti in questa installazione non posso aiutarti.",
         r["risposta_finale"])
r = chiama("amministra", {"area": "lavori"})
verifica("area lavori: agenti e sviluppo dai tool", "affidare a un agente" in
         r["risposta_finale"] and "un passo alla volta" in r["risposta_finale"],
         r["risposta_finale"])
r = chiama("ospite", {"cosa": "sa_fare", "area": "casa"})
verifica("ospite: come prima, solo cosa può chiedere", r["risposta_finale"]
         .startswith("Puoi chiedermi"), r["risposta_finale"])
r = chiama("amministra", {"cosa": "manca"})
verifica("«cosa manca?» resta com'era (perché e aggiunte)", "mancano i file di Wikipedia" in
         r["risposta_finale"] and not r["risposta_finale"].startswith("Posso aiutarti"),
         r["risposta_finale"])
nomi = [a["nome"] for a in capacita.aree(reg, None)]
verifica("aree: nomi detti senza «e» né virgole (in fila si capiscono)",
         all(" e " not in n and "," not in n for n in nomi), str(nomi))
a0 = capacita.aree(reg, None)
verifica("aree senza elenco dei tool: solo capacità e «sempre»",
         [a["chiave"] for a in a0 if a["attiva"]] ==
         ["casa", "agenda", "ricerca", "documenti", "pc", "lavori", "schermi", "tempi",
          "persone"],
         str([a["chiave"] for a in a0 if a["attiva"]]))

# ── spinta nel prompt ──
p = capacita.testo_prompt(reg, ["calliope_stato"])
verifica("prompt: domande su di sé → calliope_stato", "domande su di te" in p
         and "che versione sei" in p and "chiama calliope_stato" in p, p)
schema = tools.get("calliope_stato").schema()["function"]
props = schema["parameters"]["properties"]
verifica("schema: cosa novita e chi_sei, area ed elenco chiuso, periodo",
         {"novita", "chi_sei"} <= set(props["cosa"]["enum"])
         and props["area"]["enum"] == list(capacita.AREE)
         and "da_ieri" in props["periodo"]["enum"], str(props)[:200])

print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
