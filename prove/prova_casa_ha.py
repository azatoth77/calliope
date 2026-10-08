import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della casa via Home Assistant (calliope/casa/, calliope/tools/casa.py)
con l'HA finto di prove/ha_finto.py: niente rete vera, niente Home Assistant di casa.

Configurazione e token (solo file temporanei, mai segreti.yaml vero), diagnosi in ogni
stato, risposte action_done / query_answer / error, entità non esposte, domini delicati,
scene, frasi personalizzate, permessi (ospite, opzione ospite luci, familiare,
amministra), HA giù, muto o lento (tempo massimo, nessun blocco), ritorno di HA, stati
aggiornati dagli eventi, letture locali, TLS (nome, CA, impronta, nessuna verifica, se
c'è openssl), guida scritta, prompt. Alla fine: il token non compare mai nell'output.

    python prove\\prova_casa_ha.py
"""

import io
import json
import time
from pathlib import Path

from prove.ha_finto import (NOME_CERT, TOKEN, FakeHA, Muto, cartella_temporanea,
                            crea_certificato, disponibile, porta_chiusa)

manca = disponibile()
if manca:
    print(f"SALTO: per l'HA finto manca {manca}")
    sys.exit(77)    # saltata: il runner la conta a parte

os.environ.pop("CALLIOPE_HA_TOKEN", None)          # solo i file temporanei di questa prova


class Tee(io.TextIOBase):
    """Tiene tutto ciò che viene stampato (anche dai thread) per cercarci il token."""

    def __init__(self, real):
        self.real, self.parts = real, []

    def write(self, s):
        self.parts.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()


tee = Tee(sys.stdout)
sys.stdout = tee

from calliope.brain import TextCallGuard  # noqa: E402
from calliope.casa import diagnose, load_casa, read_token, secrets_path  # noqa: E402
from calliope.casa.base import Entita  # noqa: E402
from calliope.casa.homeassistant import HomeAssistantBackend, fingerprint  # noqa: E402
from calliope.casa.parole import (descrivi, frase_stato, nome_esatto, riscrivi,  # noqa: E402
                                  suggerimenti)
from calliope.config import Config, example_yaml, load_config  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0
risultati: list[str] = []


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


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
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False


TMP = cartella_temporanea()


def cfg_casa(url=None, token=True, **kw) -> Config:
    """Config con la cartella dei segreti temporanea; `token` scrive segreti.yaml."""
    d = Path(TMP) / f"c{len(list(Path(TMP).iterdir()))}"
    d.mkdir()
    c = Config()
    c.config_dir = str(d)
    c.casa_url = url
    c.casa_timeout_s = 1.0
    c.casa_connessione_s = 1.0
    for k, v in kw.items():
        setattr(c, k, v)
    if token:
        (d / "segreti.yaml").write_text(
            f'home_assistant:\n  token: "{TOKEN if token is True else token}"\n', encoding="utf-8")
    return c


def chiama(reg, ctx, nome, args, livello) -> dict:
    out = reg.call(nome, args, ctx, livello)
    risultati.append(out)
    return json.loads(out)


def contesto(cfg, casa, chi="Bianca", livello="familiare", documenti=None):
    return ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                       speaker=None, casa=casa, documenti=documenti)


def nomi(reg, livello):
    """I tool ammessi a quel livello (i permessi): il modello li vede tutti (03/10)."""
    return [s["function"]["name"] for s in reg.schemas_for(livello)]


def aspetta(condizione, max_s=5.0) -> bool:
    """Aspetta che una cosa fatta in secondo piano (evento di HA, rilettura, connessione
    chiusa) sia arrivata, invece di un tempo fisso: con la macchina carica 0,15–0,4 s non
    bastavano sempre (01/10, prova fallita una volta su tre nel runner)."""
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        if condizione():
            return True
        time.sleep(0.02)
    return bool(condizione())


# ─────────────────────────── 1. configurazione e token ───────────────────────────
print("— configurazione e token")
c = cfg_casa(url=None)
be, diag = load_casa(c)
verifica("senza casa_url: niente adattatore, diagnosi senza_indirizzo",
         be is None and diag["codice"] == "senza_indirizzo" and diag["stato"] == "da_configurare")
reg = build_registry(casa=False)
verifica("senza indirizzo: c'è solo casa_integrazione",
         "casa_integrazione" in nomi(reg, "familiare") and "casa_comando" not in nomi(reg, "amministra")
         and "casa_stato" not in nomi(reg, "amministra"))
verifica("casa_integrazione non è ammesso agli ospiti", "casa_integrazione" not in nomi(reg, "ospite"))
reg0 = build_registry()
verifica("casa spenta (casa=None): nessun tool casa_*",
         not any(n.startswith("casa_") for n in nomi(reg0, "amministra")))

c = cfg_casa(url="https://192.168.1.10:8123", token=False)
verifica("con l'indirizzo ma senza token: senza_token",
         diagnose(c)["codice"] == "senza_token")
c.casa_enabled = False
verifica("casa_enabled false: spenta", diagnose(c)["codice"] == "spenta")

c = cfg_casa(url="https://192.168.1.10:8123", token=False)
Path(c.config_dir, "segreti.yaml").write_text(f"home_assistant:\n  token: \"{TOKEN}\n  x: [",
                                              encoding="utf-8")
d = diagnose(c)
verifica("segreti.yaml rotto: segreti_illeggibili con la riga, senza il token",
         d["codice"] == "segreti_illeggibili" and TOKEN not in json.dumps(d), str(d["dettagli"]))

c = cfg_casa(url="https://192.168.1.10:8123")
verifica("token nel file: si legge dal file accanto alla configurazione",
         read_token(c)[0] == TOKEN and secrets_path(c).startswith(c.config_dir))
verifica("indirizzo e token senza adattatore: «riavviami»", diagnose(c)["codice"] == "riavvio"
         and "riavviami" in diagnose(c)["prossimo_passo"])
os.environ["CALLIOPE_HA_TOKEN"] = "tok-dall-ambiente"
verifica("la variabile d'ambiente vince sul file", read_token(c)[0] == "tok-dall-ambiente")
os.environ.pop("CALLIOPE_HA_TOKEN")

# segreti_file relativo alla cartella di CALLIOPE_CONFIG, non a quella di lavoro
sub = Path(TMP) / "conf"
sub.mkdir()
(sub / "altro.yaml").write_text("casa:\n  casa_url: https://10.0.0.2:8123\n", encoding="utf-8")
(sub / "segreti.yaml").write_text('home_assistant:\n  token: "abc"\n', encoding="utf-8")
lc = load_config(str(sub / "altro.yaml"))
verifica("segreti.yaml si cerca accanto al file di configurazione in uso",
         read_token(lc)[0] == "abc" and lc.casa_url == "https://10.0.0.2:8123")
ex = example_yaml()
verifica("il file d'esempio ha le sezioni casa e segreti, senza token",
         "\ncasa:\n" in ex and "segreti_file: segreti.yaml" in ex
         and not __import__("re").search(r"(?m)^\s*(casa_)?token\s*:", ex))

# ─────────────────────────── 2. collegamento e diagnosi ───────────────────────────
print("— collegamento e diagnosi")
ha = FakeHA().avvia()
c = cfg_casa(url=ha.url)
t0 = time.perf_counter()
be, diag = load_casa(c)
dt = time.perf_counter() - t0
verifica("load_casa non aspetta Home Assistant", be is not None and dt < 0.3, f"{dt:.3f}s")
d = diagnose(c, be, riprova=True)
verifica("collegata: attiva, 26 entità esposte, 9 stanze",
         d["stato"] == "attiva" and d["dettagli"].get("entita") == 26
         and d["dettagli"].get("aree") == 9, str(d["dettagli"]))
ents = {e.id: e for e in be.entita()}
verifica("le entità non esposte non si vedono",
         "light.laboratorio" not in ents and "switch.server" not in ents)
verifica("stanza dal dispositivo e alias dal registro",
         ents["light.camera"].area == "Camera" and ents["light.piantana"].alias == ["lampada da terra"]
         and ents["light.camera"].piano == "Primo piano")

# Riassunto dell'avvio (01/10): diceva «casa (Home Assistant) (collegamento in corso)» anche
# con la riga «[CASA] Collegata…» stampata subito sopra. Ora rilegge lo stato della casa
from calliope import capacita as _capacita  # noqa: E402
_reg_cap = _capacita.nuovo_registro()
c_r = cfg_casa(url=ha.url)
be_r, _ = load_casa(c_r, log=lambda m: None)
in_corso = "collegamento in corso" in _reg_cap.riassunto()
t0 = time.perf_counter()
# (in Calliope 0,3 s; qui di più, perché sotto carico il collegamento finto può tardare)
fine = be_r.attendi_primo_tentativo(5.0)
dt = time.perf_counter() - t0
righe_r = _reg_cap.righe_avvio()
verifica("avvio: finito il primo collegamento, il riassunto rilegge la casa",
         fine and "1 attive su 1" in righe_r[0]
         and "collegamento in corso" not in " ".join(righe_r),
         f"{dt:.3f}s, segnalata al caricamento {'in corso' if in_corso else 'già collegata'}: "
         f"{righe_r[0]}")
be_r.close()
muto_r = Muto()
_reg_cap = _capacita.nuovo_registro()
be_r, _ = load_casa(cfg_casa(url=f"http://127.0.0.1:{muto_r.port}"), log=lambda m: None)
t0 = time.perf_counter()
fine = be_r.attendi_primo_tentativo(0.3)
dt = time.perf_counter() - t0
verifica("avvio con HA muto: non si aspetta più di 0,3 s, e resta «in corso»",
         not fine and dt < 0.5 and "collegamento in corso" in _reg_cap.righe_avvio()[0],
         f"{dt:.3f}s {_reg_cap.righe_avvio()[0]}")
be_r.close()
muto_r.ferma()
_capacita.nuovo_registro()

reg = build_registry(casa=True, pc_nome="portatile")
ctx = contesto(c, be)
ctx_admin = contesto(c, be, "Dario", "amministra")
r = chiama(reg, ctx_admin, "casa_integrazione", {}, "amministra")
verifica("casa_integrazione (amministra, tutto ok): quante entità e un esempio",
         "26 dispositivi" in r["conferma"] and "«" in r["conferma"], r["conferma"])
r = chiama(reg, ctx, "casa_integrazione", {}, "familiare")
verifica("casa_integrazione (familiare): frase breve senza dettagli",
         "funziona" in r["conferma"] and "26" not in r["conferma"], r["conferma"])
r = chiama(reg, contesto(c, be, None, "ospite"), "casa_integrazione", {}, "ospite")
verifica("casa_integrazione (ospite): NON eseguita", r.get("ok") is False and "NON" in r["fatto"])


def stato_ha(eid):
    return ha.entita[eid]["stato"]


# ─────────────────────────── 3. comandi e risposte ───────────────────────────
print("— comandi")
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi la luce della cucina"}, "familiare")
verifica("action_done: luce accesa, risposta di HA come risposta finale",
         r["ok"] and stato_ha("light.cucina") == "on"
         and r["risposta_finale"] == "Ho acceso le luci in cucina.", r.get("conferma"))
verifica("riferimento di più luci in una stanza: i nomi, la stanza, l'oggetto del comando",
         r.get("riferimento") == {"cosa": "Luce cucina, Sottopensile (in cucina)",
                                  "nome": "la luce della cucina",
                                  "comando": "accendi la luce della cucina"}, str(r.get("riferimento")))
r = chiama(reg, ctx, "casa_comando", {"comando": "Calliope, spegni tutte le luci al piano di sopra."},
           "familiare")
verifica("piano di sopra (alias del piano), il nome di Calliope tolto",
         r["ok"] and stato_ha("light.bagno") == "off", r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "abbassa le tapparelle in sala"}, "familiare")
verifica("tapparelle in sala chiuse", r["ok"] and stato_ha("cover.sala") == "closed", r["conferma"])
r = chiama(reg, ctx, "casa_comando", {"comando": "imposta il termostato a 22 gradi"}, "familiare")
verifica("termostato a 22", r["ok"] and ha.entita["climate.termostato"]["attr"]["temperature"] == 22)
r = chiama(reg, ctx, "casa_comando", {"comando": "ci sono luci accese in sala"}, "familiare")
verifica("query_answer: la risposta di HA", r["ok"] and r["risposta_finale"].startswith("Sì"),
         r["conferma"])

n0 = len(ha.servizi)
r = chiama(reg, ctx, "casa_comando", {"comando": "sblocca la serratura ingresso"}, "amministra")
verifica("serratura: rifiutata anche a chi amministra, frase fissa, niente servizio",
         r["ok"] is False and "NON" in r["fatto"] and "serrature" in r["risposta_finale"]
         and stato_ha("lock.ingresso") == "locked" and len(ha.servizi) == n0, r["conferma"])
r = chiama(reg, ctx, "casa_comando", {"comando": "apri il cancello"}, "familiare")
verifica("cancello (cover gate): rifiutato", r["ok"] is False and stato_ha("cover.cancello") == "closed"
         and len(ha.servizi) == n0, r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "apri la porta garage"}, "familiare")
verifica("porta del garage (cover garage): mai aperta", stato_ha("cover.garage") == "closed"
         and len(ha.servizi) == n0, r.get("conferma") or r.get("errore"))
r = chiama(reg, ctx, "casa_comando", {"comando": "disattiva l'allarme"}, "amministra")
verifica("allarme: mai disinserito, con la frase dei domini delicati",
         stato_ha("alarm_control_panel.casa") == "disarmed" and len(ha.servizi) == n0
         and r["ok"] is False and "allarme" in r.get("risposta_finale", ""),
         r.get("conferma") or r.get("errore"))
r = chiama(reg, ctx, "casa_comando", {"comando": "attiva cinema"}, "familiare")
verifica("scena non in casa_consentiti: rifiutata", r["ok"] is False and len(ha.servizi) == n0
         and "scene" in r.get("risposta_finale", ""), r.get("conferma"))
c.casa_consentiti = ["scene.cinema"]
r = chiama(reg, ctx, "casa_comando", {"comando": "attiva cinema"}, "familiare")
verifica("scena in casa_consentiti: eseguita", r["ok"] and ha.servizi[-1][1] == "scene.cinema")
c.casa_consentiti = []
n0 = len(ha.servizi)
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi la luce laboratorio"}, "amministra")
verifica("entità NON esposta: rifiutata prima di eseguire", r["ok"] is False
         and stato_ha("light.laboratorio") == "off" and len(ha.servizi) == n0, r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "buonanotte casa"}, "amministra")
verifica("frase personalizzata (trigger): non eseguita", r["ok"] is False
         and ("process", "buonanotte casa") not in ha.testi, r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "che ore sono"}, "familiare")
verifica("non è della casa: torna al modello", r["ok"] is False and "risposta_finale" not in r
         and "cosa_fare" in r and ("process", "che ore sono") not in ha.testi)

ctx.user_text = "accendi la luce del frullatore"
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi la luce del frullatore"}, "familiare")
verifica("error (non capito): nomi vicini per riprovare una volta",
         r["ok"] is False and r.get("nomi_vicini") and "risposta_finale" not in r
         and any("Luce" in n for n in r["nomi_vicini"]), str(r.get("nomi_vicini")))
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi il frullatore"}, "familiare")
verifica("secondo errore nella stessa frase: risposta finale, niente altri giri",
         "risposta_finale" in r and "Non trovo" in r["risposta_finale"], r.get("conferma"))
ctx.user_text = ""
ha.entita["switch.presa_tv"]["stato"] = "on"
r = chiama(reg, ctx, "casa_comando", {"comando": "spegni la presa della TV"}, "familiare")
verifica("riscrittura locale con il nome esatto: «la presa della TV» → «presa TV»",
         r["ok"] and stato_ha("switch.presa_tv") == "off"
         and ("debug", "spegni la presa TV") in ha.testi, r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "metti la luce del bagno al 30 per cento"},
           "familiare")
verifica("riscrittura locale delle percentuali: luminosità al 30%",
         r["ok"] and abs(ha.entita["light.bagno"]["attr"].get("brightness", 0) - 76) <= 3,
         r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi la luce cucna"}, "familiare")
verifica("un refuso nel nome si corregge con il nome esatto", r["ok"], r.get("conferma"))
r = chiama(reg, ctx, "casa_comando", {"comando": "apri la porta garage"}, "familiare")
verifica("la riscrittura passa comunque dalle regole: porta del garage mai aperta",
         r["ok"] is False and stato_ha("cover.garage") == "closed")
r = chiama(reg, ctx, "casa_comando", {"comando": "cosa c'è acceso?"}, "familiare")
verifica("una domanda finita in casa_comando si legge dagli stati", r["ok"]
         and "accese" in r["risposta_finale"], r.get("conferma"))

# ─────────────────────────── 4. letture locali ───────────────────────────
print("— letture (casa_stato)")
n_req = len(ha.richieste)
r = chiama(reg, ctx, "casa_stato", {"cosa": "temperatura in camera"}, "familiare")
verifica("temperatura in camera dal sensore", r.get("risposta_finale") == "In camera ci sono 19,8 gradi.",
         r.get("conferma"))
verifica("le letture non mandano richieste a HA", len(ha.richieste) == n_req)
r = chiama(reg, ctx, "casa_stato", {"cosa": "che temperatura c'è in camera da letto?"}, "familiare")
verifica("alias della stanza", "19,8" in r.get("conferma", ""), r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "porta del garage"}, "familiare")
verifica("porta del garage", r.get("conferma") == "La porta del garage è chiusa.", r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "serratura"}, "familiare")
verifica("serratura: si legge", "chiusa a chiave" in r.get("conferma", ""), r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "allarme"}, "familiare")
verifica("allarme: si legge", r.get("conferma") == "L'allarme è disinserito.", r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "termostato"}, "familiare")
verifica("termostato", "segna 20,5 gradi ed è impostato a 22" in r.get("conferma", ""), r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "cosa c'è acceso"}, "familiare")
verifica("cosa c'è acceso", r.get("conferma", "").startswith("Sono accese") and "luce cucina"
         in r["conferma"], r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "finestre aperte"}, "familiare")
verifica("finestre aperte", "finestra cucina" in r.get("conferma", ""), r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "luci in cucina"}, "familiare")
verifica("luci in una stanza", "luce cucina" in r.get("conferma", "").lower(), r.get("conferma"))
r = chiama(reg, ctx, "casa_stato", {"cosa": "frigorifero"}, "familiare")
verifica("cosa sconosciuta: nomi e stanze per riprovare", r["ok"] is False and r.get("stanze"),
         str(r.get("nomi_vicini")))
ha.imposta("light.studio", "on")
aspetta(lambda: any(e.id == "light.studio" and e.stato == "on" for e in be.entita()))
r = chiama(reg, ctx, "casa_stato", {"cosa": "luce studio"}, "familiare")
verifica("stato cambiato in HA arriva dagli eventi", r.get("conferma") == "La luce studio è accesa.",
         r.get("conferma"))

# ─────────────────────────── 5. permessi ───────────────────────────
print("— permessi")
verifica("ospite: nessun tool casa_comando/casa_stato",
         "casa_comando" not in nomi(reg, "ospite") and "casa_stato" not in nomi(reg, "ospite"))
ctx_o = contesto(c, be, None, "ospite")
n0 = len(ha.servizi)
r = chiama(reg, ctx_o, "casa_comando", {"comando": "accendi la luce della cucina"}, "ospite")
verifica("ospite che chiama comunque: NON eseguita", r.get("ok") is False and "NON" in r["fatto"]
         and len(ha.servizi) == n0)
c_o = cfg_casa(url=ha.url, casa_ospite_domini=["light"])
be_o, _ = load_casa(c_o)
reg_o = build_registry(casa=True, casa_ospite=True)
ctx_o = contesto(c_o, be_o, None, "ospite")
verifica("con casa_ospite_domini: l'ospite può usare i tool", "casa_comando" in nomi(reg_o, "ospite"))
r = chiama(reg_o, ctx_o, "casa_comando", {"comando": "spegni la luce della cucina"}, "ospite")
verifica("ospite + luci: la luce sì", r["ok"] and stato_ha("light.cucina") == "off", r.get("conferma"))
n0 = len(ha.servizi)
r = chiama(reg_o, ctx_o, "casa_comando", {"comando": "apri le tapparelle in sala"}, "ospite")
verifica("ospite + luci: le tapparelle no", r.get("ok") is False and "NON" in r["fatto"]
         and len(ha.servizi) == n0)
r = chiama(reg_o, ctx_o, "casa_stato", {"cosa": "temperatura in camera"}, "ospite")
verifica("ospite + luci: legge solo le luci", r.get("ok") is False, r.get("conferma") or r.get("errore"))
be_o.close()

# ─────────────────────────── 6. HA giù, muto, lento, di ritorno ───────────────────────────
print("— HA giù o lento")
porta = porta_chiusa()
c_g = cfg_casa(url=f"http://127.0.0.1:{porta}")
t0 = time.perf_counter()
be_g, _ = load_casa(c_g)
verifica("HA spento: l'avvio non si blocca", time.perf_counter() - t0 < 0.3)
ctx_g = contesto(c_g, be_g)
t0 = time.perf_counter()
r = chiama(reg, ctx_g, "casa_comando", {"comando": "accendi la luce della cucina"}, "familiare")
dt = time.perf_counter() - t0
verifica("HA spento: «la casa non risponde» in fretta", r["ok"] is False and "non risponde"
         in r["risposta_finale"] and dt < c_g.casa_connessione_s + 1.0, f"{dt:.2f}s")
d = diagnose(c_g, be_g, riprova=True)
verifica("diagnosi: non_raggiunge, guasta, passo concreto", d["codice"] == "non_raggiunge"
         and d["stato"] == "guasta" and "acceso" in d["prossimo_passo"], d["motivo"])
# HA torna sulla stessa porta: la richiesta dopo si ricollega da sola
ha2 = FakeHA().avvia(port=porta)
t0 = time.perf_counter()
r = chiama(reg, ctx_g, "casa_comando", {"comando": "accendi la luce della cucina"}, "familiare")
verifica("HA tornato: la prima richiesta si ricollega", r["ok"], f"{time.perf_counter() - t0:.2f}s")
ha2.ferma()
aspetta(lambda: not be_g._ready.is_set())       # il lettore ha visto la connessione chiusa
r = chiama(reg, ctx_g, "casa_stato", {"cosa": "luce cucina"}, "familiare")
verifica("HA che cade durante l'uso: non risponde, senza eccezioni", r["ok"] is False
         and "non risponde" in r.get("risposta_finale", ""), r.get("conferma"))
be_g.close()

muto = Muto()
c_m = cfg_casa(url=f"http://127.0.0.1:{muto.port}")
be_m, _ = load_casa(c_m)
t0 = time.perf_counter()
r = chiama(reg, contesto(c_m, be_m), "casa_stato", {"cosa": "luci"}, "familiare")
dt = time.perf_counter() - t0
verifica("HA muto: scade entro il tempo di collegamento", r["ok"] is False and dt < 2.6, f"{dt:.2f}s")
be_m.close()
muto.ferma()

lento = FakeHA(ritardo_s=1.0).avvia()           # il riconoscimento delle frasi è lento
c_l = cfg_casa(url=lento.url, casa_timeout_s=0.3, casa_connessione_s=4.0)
be_l, _ = load_casa(c_l)
verifica("HA lento: il collegamento riesce", be_l.diagnosi(riprova=True).codice == "ok")
t0 = time.perf_counter()
r = chiama(reg, contesto(c_l, be_l), "casa_comando", {"comando": "accendi la luce della cucina"},
           "familiare")
dt = time.perf_counter() - t0
verifica("HA lento oltre il tempo massimo: non risponde, senza aspettare oltre", r["ok"] is False
         and dt < 0.8, f"{dt:.2f}s")
lento.ritardo_s = 0.0
real_process = lento._process


def process_lento(text):
    time.sleep(1.5)
    return real_process(text)


lento._process = process_lento                 # verifica veloce, esecuzione lenta
# HA finisce la richiesta lenta di prima (un tempo fisso non bastava sempre); la verifica ha
# 1 s di tempo (con 0,3 s, sotto carico, a volte scadeva già lei: «non risponde»)
aspetta(lambda: ("debug", "accendi la luce della cucina") in lento.testi)
be_l.timeout_s = 1.0
r = chiama(reg, contesto(c_l, be_l), "casa_comando", {"comando": "accendi la luce della cucina"},
           "familiare")
verifica("tempo scaduto durante l'esecuzione: «potrebbe essere partito», non «non risponde»",
         r["ok"] is False and "potrebbe" in r.get("risposta_finale", ""), r.get("conferma"))
be_l.close()
lento.ferma()

# ─────────────────────────── 7. stati della diagnosi ───────────────────────────
print("— diagnosi")


def diag_con(**kw):
    url = kw.pop("url", None)
    fake = FakeHA(**{k: v for k, v in kw.items() if k in ("admin", "agente", "entita", "token")})
    fake.avvia()
    cc = cfg_casa(url=url or fake.url, token=kw.get("mio_token", True))
    b, _ = load_casa(cc)
    out = diagnose(cc, b, riprova=True)
    rr = chiama(reg, contesto(cc, b, "Dario", "amministra"), "casa_integrazione", {}, "amministra")
    b.close()
    fake.ferma()
    return out, rr["conferma"]


d, frase = diag_con(token="un-altro-token")
verifica("token rifiutato (401): rigenerarlo", d["codice"] == "token_rifiutato"
         and "Sicurezza" in frase and "segreti.yaml" in frase, frase)
d, frase = diag_con(admin=False)
verifica("token non di un amministratore", d["codice"] == "non_admin" and "amministratore" in frase, frase)
d, frase = diag_con(agente=False)
verifica("agente integrato assente", d["codice"] == "agente_assente" and "Assistenti vocali" in frase,
         frase)
d, frase = diag_con(entita=[])
verifica("nessuna entità esposta: dove si espongono", d["codice"] == "nessuna_entita"
         and "Esponi" in frase and "Assistenti vocali" in frase, frase)
cc = cfg_casa(url=None)
rr = chiama(build_registry(casa=False), contesto(cc, None, "Dario", "amministra"),
            "casa_integrazione", {}, "amministra")
verifica("senza indirizzo: dove scriverlo", "casa_url" in rr["conferma"] and "DuckDNS" in rr["conferma"],
         rr["conferma"])
cc = cfg_casa(url="https://192.168.1.10:8123", token=False)
rr = chiama(build_registry(casa=False), contesto(cc, None, "Dario", "amministra"),
            "casa_integrazione", {}, "amministra")
verifica("senza token: profilo, Sicurezza, segreti.yaml, non dettarlo",
         all(k in rr["conferma"] for k in ("profilo", "Sicurezza", "lungo termine", "segreti.yaml",
                                           "Non dettarmelo")), rr["conferma"])
rr = chiama(build_registry(casa=False), contesto(cc, None, "Bianca", "familiare"),
            "casa_integrazione", {}, "familiare")
verifica("familiare: «chiedi a chi amministra», niente file", "amministra" in rr["conferma"]
         and "segreti" not in rr["conferma"], rr["conferma"])
c_g2 = cfg_casa(url=f"http://127.0.0.1:{porta_chiusa()}")
b, _ = load_casa(c_g2)
rr = chiama(reg, contesto(c_g2, b, "Dario", "amministra"), "casa_integrazione", {}, "amministra")
verifica("HA giù: Raspberry acceso e rete di casa", "non risponde" in rr["conferma"]
         and "Raspberry" in rr["conferma"], rr["conferma"])
b.close()

# Guida scritta: con il servizio documenti e una cartella temporanea, testo fisso
try:
    from calliope.documenti import Documenti
    from calliope.documenti.consegna import LocalDelivery
    from calliope.documenti.render import plain_text

    class NoWriter:
        def write(self, *a, **k):
            raise AssertionError("la guida non passa dall'LLM")

    svc = Documenti(c, str(Path(TMP) / "doc.db"), writer=NoWriter(),
                    delivery=LocalDelivery(Path(TMP) / "Documenti"))
    rr = chiama(reg, contesto(c, be, "Dario", "amministra", documenti=svc), "casa_integrazione",
                {"per_iscritto": True, "formato": "pdf" if "pdf" in svc.formati else "word"},
                "amministra")
    files = list((Path(TMP) / "Documenti").iterdir())
    text = plain_text("pdf" if files[0].suffix == ".pdf" else "word", files[0].read_bytes()) if files else ""
    verifica("guida scritta: file con i passi completi, senza token",
             len(files) == 1 and "lungo termine" in text and "Esponi" in text and TOKEN not in text
             and "Ti ho preparato la guida" in rr["conferma"], rr["conferma"])
    rr = chiama(reg, contesto(c, be, "Bianca", "familiare", documenti=svc), "casa_integrazione",
                {"per_iscritto": True}, "familiare")
    verifica("guida scritta: non per i familiari", len(list((Path(TMP) / "Documenti").iterdir())) == 1)
    svc.close()
except ImportError as e:
    print(f"SALTATA IN PARTE: guida scritta: {e}")

# ─────────────────────────── 8. TLS ───────────────────────────
print("— TLS")
cert = crea_certificato(Path(TMP))
if cert is None:
    print("SALTATA IN PARTE: openssl non trovato, prove TLS non fatte")
else:
    hs = FakeHA(ssl_files=cert).avvia()

    def tls(**kw):
        # Sulla DGX (02/10) con 1 s la stretta di mano dopo un tentativo rifiutato scadeva
        # una volta su sei («impronta giusta»): qui si prova il TLS, non il tempo massimo
        kw.setdefault("casa_connessione_s", 3.0)
        cc = cfg_casa(url=hs.url, **kw)
        b, _ = load_casa(cc)
        out = diagnose(cc, b, riprova=True)
        b.close()
        return out

    d = tls(casa_tls_nome=NOME_CERT, casa_tls_ca=str(cert[0]))
    verifica("nome del certificato (SNI) + CA: collegata all'IP", d["codice"] == "ok", d["motivo"])
    d = tls(casa_tls_ca=str(cert[0]))
    verifica("sull'IP senza nome: tls_nome, con il nome del certificato in dettaglio",
             d["codice"] == "tls_nome" and NOME_CERT in d["dettagli"].get("nomi", [])
             and "DuckDNS" in d["prossimo_passo"] and "casa_tls_nome" in d["prossimo_passo"],
             d["prossimo_passo"])
    d = tls(casa_tls_nome=NOME_CERT)
    verifica("certificato non firmato da un'autorità nota: tls_certificato",
             d["codice"] == "tls_certificato" and "casa_tls_impronta" in d["prossimo_passo"])
    der = __import__("ssl").PEM_cert_to_DER_cert(Path(cert[0]).read_text())
    d = tls(casa_tls_impronta=fingerprint(der).lower().replace(":", ""))
    verifica("impronta giusta: collegata", d["codice"] == "ok")
    d = tls(casa_tls_impronta="AB" * 32)
    verifica("impronta diversa: tls_impronta", d["codice"] == "tls_impronta"
             and d["dettagli"].get("trovata") == fingerprint(der))
    start = len(tee.parts)
    d = tls(casa_tls_verifica=False)
    verifica("verifica spenta: collegata, con l'avviso all'avvio", d["codice"] == "ok"
             and "ATTENZIONE" in "".join(tee.parts[start:]))
    hs.ferma()

# ─────────────────────────── 9. esposizione che cambia ───────────────────────────
print("— esposizione che cambia")
c.casa_aggiorna_s = 0.0
be.aggiorna_s = 0.0
ha.entita["light.laboratorio"]["esposta"] = True
be.entita()                                     # fa partire la rilettura in secondo piano
aspetta(lambda: any(e.id == "light.laboratorio" and e.stato for e in be.entita()))
ids = {e.id: e for e in be.entita()}
verifica("una luce esposta dopo l'avvio arriva da sola, con il suo stato",
         "light.laboratorio" in ids and ids["light.laboratorio"].stato == "off")

# ─────────────────── 9b. nomi uguali, entità irraggiungibili (01/10) ───────────────────
print("— nomi uguali e irraggiungibili")
from prove.ha_finto import _e, entita_casa  # noqa: E402

ha_t = FakeHA(entita=entita_casa() + [_e("light.taverna", "Taverna", None, "off"),
                                      _e("light.taverna_vecchia", "Taverna", None, "unavailable")]
              ).avvia()
c_t = cfg_casa(url=ha_t.url)
be_t, _ = load_casa(c_t)
ctx_t = contesto(c_t, be_t)
ctx_t.user_text = "Calliope, accendi l'interruttore taverna."
r = chiama(reg, ctx_t, "casa_comando", {"comando": "accendi l'interruttore taverna"}, "familiare")
verifica("«accendi l'interruttore taverna» (caso del 01/10): riprova da sola con il nome",
         r["ok"] and ha_t.entita["light.taverna"]["stato"] == "on"
         and any(k == "debug" and t.lower() in ("accendi la taverna", "accendi taverna")
                 for k, t in ha_t.testi), str([t for _, t in ha_t.testi]))
verifica("la regola che ha riscritto resta nel registro", "casa_riscrittura" in ctx_t.regole,
         str(ctx_t.regole))
verifica("riferimento per «spegnila» dopo: il nome dell'entità e il comando eseguito",
         r.get("riferimento", {}).get("nome") == "Taverna"
         and r["riferimento"].get("comando", "").lower() in ("accendi la taverna", "accendi taverna"),
         str(r.get("riferimento")))
ents_t = be_t.entita()
verifica("riscrittura con due «Taverna», una irraggiungibile: una frase sola, sul nome",
         riscrivi("spegni l'interruttore taverna", ents_t) == ["spegni la taverna"],
         str(riscrivi("spegni l'interruttore taverna", ents_t)))
nomi_t, _ = suggerimenti("accendi la tavernetta grande", ents_t)
verifica("suggerimenti: «Taverna» una volta sola", nomi_t.count("Taverna") == 1, str(nomi_t))
morte = [Entita("light.a", "Lampada A", "light", stato="unavailable"),
         Entita("light.b", "Lampada B", "light", stato="on")]
nomi_m, _ = suggerimenti("accendi la lampada", morte)
verifica("suggerimenti: a pari somiglianza prima le entità vive", nomi_m == ["Lampada B", "Lampada A"],
         str(nomi_m))
# «Chiudi»/«apri» una luce o un interruttore = spegni/accendi (01/10, «chiudi taverna»);
# per tapparelle e porte il verbo resta
for frase, attesa in [("chiudi taverna", ["spegni la taverna"]),
                      ("apri la presa TV", ["accendi la presa TV"]),
                      ("chiudi la tapparella sala adesso", ["chiudi la tapparella sala"]),
                      ("apri la tapparella cucina subito", ["apri la tapparella cucina"])]:
    verifica(f"riscrittura del verbo per il tipo: «{frase}»", riscrivi(frase, ents_t) == attesa,
             str(riscrivi(frase, ents_t)))
ctx_t.user_text = "Calliope, chiudi taverna."
ha_t.entita["light.taverna"]["stato"] = "on"
r = chiama(reg, ctx_t, "casa_comando", {"comando": "chiudi taverna"}, "familiare")
verifica("«chiudi taverna»: spenta con la riscrittura", r["ok"]
         and ha_t.entita["light.taverna"]["stato"] == "off", r.get("conferma") or r.get("errore"))
# Casi contrari: nessuna riscrittura dove non c'è un nome detto tale e quale
for frase in ("accendi la luce del frullatore", "accendi tutto", "spegni la tavernetta"):
    verifica(f"nessuna riscrittura per «{frase}»", riscrivi(frase, ents_t) == [],
             str(riscrivi(frase, ents_t)))
verifica("il nome esatto vince sui più corti: «luce cucina» non «cucina»",
         nome_esatto("accendi la luce cucina adesso", ents_t) == "Luce cucina",
         str(nome_esatto("accendi la luce cucina adesso", ents_t)))
be_t.close()
ha_t.ferma()

# ─────────────────────────── 10. parole, prompt, guardia ───────────────────────────
print("— parole e prompt")
e = Entita("cover.x", "Tapparelle studio", "cover", "shutter", stato="open",
           attributi={"current_position": 40})
verifica("plurale e posizione", frase_stato(e) == "Le tapparelle studio sono aperte al 40 per cento.",
         frase_stato(e))
e = Entita("light.x", "Abat-jour", "light", stato="on", attributi={"brightness": 128})
verifica("articolo davanti a vocale e luminosità", frase_stato(e) == "L'abat-jour è accesa al 50 per cento.",
         frase_stato(e))
e = Entita("sensor.x", "Consumo", "sensor", "power", stato="1520.0", unita="W")
verifica("sensore con unità", frase_stato(e) == "Il consumo segna 1520 watt.", frase_stato(e))
res = descrivi("", [Entita("light.a", "Luce a", "light", stato="off")])
verifica("riassunto senza parole: niente di acceso", res["frase"] == "Non c'è niente di acceso.",
         res["frase"])
p_casa = c.prompt_for(False, pc=("pc_volume",), casa=("casa_comando", "casa_stato", "casa_integrazione"))
p_no = c.prompt_for(False, pc=("pc_volume",))
verifica("prompt: con la casa niente «non comandi luci», chi fa cosa con il PC",
         "casa_comando" in p_casa and "non comandi luci" not in p_casa and "pc_*" in p_casa
         and "non comandi luci" in p_no and "casa_" not in p_no)
p_int = c.prompt_for(False, casa=("casa_integrazione",))
verifica("prompt: con la sola integrazione resta «non comandi luci»",
         "casa_integrazione" in p_int and "casa_comando" not in p_int and "non comandi luci" in p_int)
g = TextCallGuard(reg.all_schemas())
for ch in 'casa_comando("accendi la luce della cucina")':
    g.feed(ch)
g.flush()
verifica("chiamata scritta come testo: diventa casa_comando con il comando",
         g.call and g.call["name"] == "casa_comando"
         and g.call["arguments"].get("comando") == "accendi la luce della cucina", str(g.call))

# ─────────────────────────── frasi d'errore di HA in italiano normale ───────────────────────────
# 01/10, prova a voce: «Mi dispiace, nell'area Taverna il dominio light non è stato esposto.»
print("— errori di HA riformulati")
import re  # noqa: E402

from calliope.casa.errori import ERRORI_HA, riformula_errore  # noqa: E402
from prove.ha_finto import _intents, errore_ha  # noqa: E402

veri = _intents()[1]["errors"]
diversi = [k for k, v in ERRORI_HA.items() if veri.get(k) != v]
verifica("i modelli copiati sono quelli di home-assistant-intents", not diversi, str(diversi))
esempio = {"area": "Taverna", "floor": "Piano di sopra", "domain": "light",
           "device_class": "window", "entity": "Luce scale", "state": "Acceso"}
tecniche = re.compile(r"\b(dominio|classe|appartenente|light|window|area|Mi dispiace)\b", re.I)
for key in ERRORI_HA:
    frase, chiave = riformula_errore(errore_ha(key, **esempio) + ".", "no_valid_targets")
    verifica(f"errore {key} → italiano normale", chiave == key and not tecniche.search(frase)
             and frase.endswith("."), frase)
frase, _ = riformula_errore("Mi dispiace, nell'area Taverna il dominio light non è stato "
                            "esposto.", "no_valid_targets")
verifica("il caso vero del 01/10", frase == "In taverna non posso comandare nessuna luce: non è "
         "esposta ad Assist in Home Assistant.", frase)
for testo, codice, atteso in [
        ("Mi dispiace, nel piano Primo piano il dominio cover non è stato esposto", "x",
         "Al primo piano non posso comandare nessuna tapparella: non è esposta ad Assist in "
         "Home Assistant."),
        ("Mi dispiace, il dominio switch non è stato esposto", "x",
         "Non posso comandare nessun interruttore: non è esposto ad Assist in Home Assistant."),
        ("Mi dispiace, nell'area Cucina nessun dispositivo appartenente alla classe garage è "
         "stato esposto", "x", "In cucina non posso comandare nessuna porta del garage: non è "
                               "esposta ad Assist in Home Assistant."),
        ("Mi dispiace, nessun dispositivo è nello stato acceso", "x",
         "Non c'è nessun dispositivo acceso."),
        ("Mi dispiace, il dominio xyz_nuovo dice qualcosa di nuovo", "no_valid_targets",
         "In Home Assistant non trovo un dispositivo esposto ad Assist che corrisponda alla "
         "richiesta."),
        ("Mi dispiace, entità rotta", "failed_to_handle",
         "Home Assistant ha avuto un errore inatteso: il comando non è andato a buon fine."),
        ("Luce cucina non risponde.", "unknown", "Luce cucina non risponde."),
        ("", "no_intent_match", "Home Assistant non ha capito il comando.")]:
    verifica(f"riformula «{testo[:45]}…»", riformula_errore(testo, codice)[0] == atteso,
             riformula_errore(testo, codice)[0])
# Dall'HA finto, con la risposta vera di HA: casa_comando dice la frase riformulata. Un
# piano: le esposte che corrispondono per nome o stanza (casa/nomi.py, 08/10) non ci sono,
# quindi resta la frase di HA (fino al 08/10 qui c'era «la luce della cucina», che ora trova
# due luci esposte in cucina e chiede quale)
ha.errori_forzati["accendi le luci al piano di sopra"] = (
    "no_valid_targets", "no_domain_in_floor_exposed", {"floor": "Primo piano",
                                                       "domain": "light"})
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi le luci al piano di sopra"},
           "familiare")
verifica("HA finto: errore vero riformulato nella risposta finale",
         r.get("ok") is False and r.get("risposta_finale") == "Al primo piano non posso "
         "comandare nessuna luce: non è esposta ad Assist in Home Assistant.",
         str(r.get("risposta_finale")))
# La stessa luce in cucina, con l'errore forzato: due esposte in cucina → la domanda
ha.errori_forzati["accendi la luce della cucina"] = (
    "no_valid_targets", "no_domain_in_area_exposed", {"area": "Cucina", "domain": "light"})
r = chiama(reg, ctx, "casa_comando", {"comando": "accendi la luce della cucina"}, "familiare")
verifica("HA finto: due luci esposte nella stanza detta → chiede quale, non esegue",
         r.get("ok") is False and "Quale intendi?" in str(r.get("risposta_finale")),
         str(r.get("risposta_finale")))
ha.errori_forzati.clear()

be.close()
ha.ferma()

# ─────────────── pulsanti di riavvio e spegnimento (04/10) ───────────────
print("— pulsanti di riavvio e spegnimento")
from calliope.casa.base import Interpretazione  # noqa: E402
from calliope.casa.regole import FRASI, Regole  # noqa: E402


def _esito_pulsante(eid, nome, classe=None, livello="amministra", regole=None):
    e = Entita(id=eid, nome=nome, dominio=eid.split(".")[0], classe=classe, area="Studio")
    i = Interpretazione(capito=True, azione="comando", intento="HassTurnOn", bersagli=[eid],
                        origine="predefinita")
    return (regole or Regole(Config())).controlla(i, {eid: e}, livello) or "esegue"


for eid, nome, cl in (("button.router_restart", "Router", "restart"),
                      ("button.nas_spegni", "NAS", None),
                      ("button.pc", "Spegnimento PC", None),
                      ("button.server", "Server shutdown", None),
                      ("button.modem", "Riavvia modem", None),
                      ("button.fritz_reboot", "Fritz", None),
                      ("button.modem_riconnetti", "Modem", None),
                      ("input_button.riavvio_casa", "Casa", None)):
    verifica(f"pulsante {eid} «{nome}»: sola lettura anche per chi amministra",
             _esito_pulsante(eid, nome, cl) == "riavvio")
verifica("frase del rifiuto dei pulsanti di riavvio", "riavviano o spengono"
         in FRASI["riavvio"] and "casa_consentiti" in FRASI["riavvio"])
# Casi contrari: altri pulsanti, interruttori e luci con quelle parole, le radici in mezzo a
# una parola
for eid, nome, cl in (("button.campanello", "Campanello", None),
                      ("button.identifica", "Identifica lampada", "identify"),
                      ("button.aggiorna", "Aggiorna firmware", "update"),
                      ("switch.spegni_tutto", "Spegni tutto", None),
                      ("light.riavvio", "Luce riavvio", None),
                      ("button.prespegnere", "Prespegnere", None)):
    verifica(f"{eid} «{nome}» si comanda", _esito_pulsante(eid, nome, cl) == "esegue")
_cfg_ok = Config()
_cfg_ok.casa_consentiti = ["button.router_restart"]
verifica("casa_consentiti sblocca un pulsante di riavvio voluto",
         _esito_pulsante("button.router_restart", "Router", "restart",
                         regole=Regole(_cfg_ok)) == "esegue")
_cfg_ok.casa_consentiti = ["Riavvia modem"]
verifica("casa_consentiti anche per nome",
         _esito_pulsante("button.modem", "Riavvia modem", regole=Regole(_cfg_ok)) == "esegue")
verifica("la lettura di un pulsante di riavvio resta possibile",
         Regole(Config()).visibile(Entita(id="button.router_restart", nome="Router",
                                          dominio="button", classe="restart"), "familiare"))

# ─────────────── sonda_ha: indirizzo mascherato, consiglio sul certificato (04/10) ───────────────
print("— sonda_ha")
from prove.sonda_ha import consiglio_tls, maschera_url  # noqa: E402

for url, atteso in (("https://192.168.1.20:8123", "https://<IP privato>:8123"),
                    ("https://casa-mia.duckdns.org:8123", "https://c******a.duckdns.org:8123"),
                    ("http://1.1.1.1", "http://<IP>"), (None, "(manca)")):
    verifica(f"sonda: casa_url mascherato ({atteso})", maschera_url(url) == atteso
             and "192.168" not in maschera_url(url) and "casa-mia" not in maschera_url(url),
             maschera_url(url))
_nomi = ["casa-mia.duckdns.org"]
verifica("sonda: casa_tls_nome consigliato collegandosi a un IP con il certificato DuckDNS",
         bool(consiglio_tls("192.168.1.20", _nomi)))
verifica("sonda: niente consiglio se l'indirizzo è già un nome, se c'è già, o senza DuckDNS",
         consiglio_tls("casa-mia.duckdns.org", _nomi) is None
         and consiglio_tls("192.168.1.20", _nomi, "casa-mia.duckdns.org") is None
         and consiglio_tls("192.168.1.20", ["homeassistant.local"]) is None)

# ─────────────────────────── il token ───────────────────────────
uscita = "".join(tee.parts) + "\n".join(risultati)
verifica("il token non compare mai: né nell'output né nei risultati dei tool", TOKEN not in uscita)
verifica("repr dell'adattatore senza token", TOKEN not in repr(be) and TOKEN not in str(vars(be)))

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
