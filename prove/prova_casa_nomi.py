import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco: un comando che Home Assistant capisce ma per cui non trova i dispositivi
(`no_valid_targets`), con una casa finta in memoria (calliope/casa/nomi.py, 08/10).

Caso vero del 08/10: la luce «Soggiorno» sta nell'area Ingresso; «spegni la luce in
soggiorno» → HA cerca le luci dell'area Soggiorno e non ne trova. Qui: una sola candidata
(riprova con il nome esatto, frase che spiega l'area), uno switch con «luce» nel nome, due
candidate (domanda), nessuna (frase d'errore giusta), omonimi irraggiungibili, la riprova
che allargherebbe ad altre entità (non si esegue), domini delicati, scene, ospiti, verbi e
percentuali che non sono della regola, il consiglio a chi amministra una volta sola, la
frase di HA «non ho capito» con il codice no_valid_targets. Nomi e stanze di fantasia.

    python prove\\prova_casa_nomi.py
"""

import json

from calliope.casa import nomi
from calliope.casa.base import Diagnosi, Entita, Esito, HomeBackend, Interpretazione
from calliope.casa.errori import riformula_errore
from calliope.casa.parole import norm
from calliope.config import Config
from calliope.tools.casa import casa_specs
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


_INTENTI = {"accendi": "HassTurnOn", "spegni": "HassTurnOff", "apri": "HassTurnOn",
            "chiudi": "HassTurnOff", "alza": "HassTurnOn", "abbassa": "HassTurnOff"}


class CasaFinta(HomeBackend):
    """HA ridotto all'osso: «<verbo> <nome o alias>» trova l'entità; il resto è un errore
    no_valid_targets con la frase scelta (predefinita «Mi dispiace, non ho capito», il ripiego
    vero di HA)."""
    nome_sistema = "Home Assistant"

    def __init__(self, entita, aree):
        self._e, self._aree = entita, aree
        self.errori: dict[str, tuple[str, str]] = {}
        self.allarga: dict[str, list[str]] = {}
        self.comandi: list[str] = []
        self.eseguiti: list[tuple[str, list[str]]] = []

    def entita(self):
        return list(self._e)

    def aree(self):
        return dict(self._aree)

    def diagnosi(self, riprova=False):
        return Diagnosi("ok", {"entita": len(self._e), "aree": len(self._aree)})

    def comando(self, testo, autorizza):
        self.comandi.append(testo)
        verbo, _, resto = norm(testo).partition(" ")
        intent = _INTENTI.get(verbo)
        if not intent:
            return Esito(False, "errore", codice="non_capito",
                         interpretazione=Interpretazione(capito=False))
        if testo in self.allarga:
            targets = self.allarga[testo]
        else:
            targets = [e.id for e in self._e
                       if resto in {norm(e.nome), *(norm(a) for a in e.alias)}]
        interp = Interpretazione(capito=True, azione="comando", intento=intent,
                                 bersagli=targets)
        if not targets:
            speech, code = self.errori.get(testo, ("Mi dispiace, non ho capito",
                                                   "no_valid_targets"))
            return Esito(False, "errore", riformula_errore(speech, code)[0], codice=code,
                         interpretazione=interp)
        motivo = autorizza(interp)
        if motivo:
            return Esito(False, "rifiuto", codice=motivo, interpretazione=interp,
                         bersagli=targets)
        self.eseguiti.append((intent, targets))
        return Esito(True, "fatto", "Fatto.", bersagli=targets, interpretazione=interp)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False


def E(eid, nome, area=None, stato="on", alias=(), classe=None):
    return Entita(id=eid, nome=nome, dominio=eid.split(".")[0], area=area, stato=stato,
                  alias=list(alias), classe=classe)


CASA = [
    E("light.ingresso_1", "Soggiorno", "Ingresso"),             # il caso vero
    E("light.vecchia", "Soggiorno", None, stato="unavailable"),  # omonima irraggiungibile
    E("light.cucina", "Cucina", "Cucina"),                      # nome = area, HA non la trova
    E("switch.forno", "Forno", "Cucina"),                       # contrario: non è una luce
    E("switch.rele_studio", "Luce studio", None),               # switch mostrato come luce
    E("switch.presa_studio", "Studio", "Ufficio"),              # contrario per «la luce»
    E("light.taverna_a", "Taverna", "Cantina"),                 # due candidate
    E("light.taverna_b", "Faretti taverna", "Taverna"),
    E("switch.cancello", "Cancello", "Giardino"),               # delicato per nome
    E("lock.portone", "Portone", "Ingresso"),                   # delicato per dominio
    E("script.notte", "Notte", None),                           # solo da elenco
    E("cover.camera", "Camera", "Camera nord"),                 # tapparella
    E("light.altra", "Altra", "Ingresso"),
]
AREE = {"Ingresso": [], "Soggiorno": ["salotto"], "Cucina": [], "Cantina": [],
        "Taverna": [], "Giardino": [], "Ufficio": [], "Camera nord": []}

cfg = Config()
casa = CasaFinta(CASA, AREE)
specs = {s.name: s for s in casa_specs(True, ospite=False)}


def chiama(tool, livello="familiare", chi="Bianca", cfg_=None, **args):
    ctx = ToolContext(cfg=cfg_ or cfg, speakers=None, speaker_ctx=SpeakerCtx(chi, livello),
                      speaker=None, casa=casa)
    ctx.user_text = args.get("comando", "")
    casa.comandi.clear()
    casa.eseguiti.clear()
    out = specs[tool].func(ctx, **args)
    return out, ctx


print("— una sola candidata: il caso vero")
nomi.azzera_consigli()
r, ctx = chiama("casa_comando", comando="spegni la luce in soggiorno")
verifica("riprova con il nome esatto", casa.comandi == ["spegni la luce in soggiorno",
                                                         "spegni Soggiorno"], str(casa.comandi))
verifica("eseguito sulla candidata (e la sua omonima irraggiungibile, come fa HA)",
         casa.eseguiti == [("HassTurnOff", ["light.ingresso_1", "light.vecchia"])],
         str(casa.eseguiti))
verifica("la frase dice l'area vera", r.get("risposta_finale") ==
         "Ho spento «Soggiorno», che in Home Assistant è nell'area Ingresso.",
         str(r.get("risposta_finale")))
verifica("nel registro dei turni casa_nome_entita", "casa_nome_entita" in ctx.regole)
verifica("riferimento per «riaccendila»", (r.get("riferimento") or {}).get("nome") ==
         "Soggiorno", str(r.get("riferimento")))
verifica("a un familiare niente consiglio nella frase", "spostala" not in r["risposta_finale"])

r, _ = chiama("casa_comando", comando="accendi la luce in salotto")
verifica("contrario: «salotto» (alias dell'area Soggiorno, senza luci esposte) non è il "
         "nome «Soggiorno»: niente riprova", casa.comandi == ["accendi la luce in salotto"],
         str(casa.comandi))

print("— il consiglio a chi amministra, una volta")
r, _ = chiama("casa_integrazione", livello="amministra", chi="Dario")
verifica("casa_integrazione dice il consiglio",
         "La luce «Soggiorno» è nell'area Ingresso: se la chiami «luce in soggiorno», in Home "
         "Assistant spostala nell'area Soggiorno." in r["risposta_finale"], r["risposta_finale"])
verifica("niente URL nel consiglio", "http" not in r["risposta_finale"])
r, _ = chiama("casa_integrazione", livello="amministra", chi="Dario")
verifica("la seconda volta no", "Un consiglio" not in r["risposta_finale"], r["risposta_finale"])
r, _ = chiama("casa_comando", livello="amministra", chi="Dario",
              comando="spegni la luce in soggiorno")
verifica("lo stesso caso non ripete il consiglio", r["risposta_finale"] ==
         "Ho spento «Soggiorno», che in Home Assistant è nell'area Ingresso.",
         r["risposta_finale"])
nomi.azzera_consigli()
r, _ = chiama("casa_comando", livello="amministra", chi="Dario",
              comando="spegni la luce in soggiorno")
verifica("a chi amministra il consiglio subito dopo il comando",
         r["risposta_finale"].endswith("spostala nell'area Soggiorno."), r["risposta_finale"])
r, _ = chiama("casa_integrazione", livello="amministra", chi="Dario")
verifica("già detto: casa_integrazione non lo ripete", "Un consiglio" not in
         r["risposta_finale"], r["risposta_finale"])
r, _ = chiama("casa_integrazione", livello="familiare")
verifica("ai familiari casa_integrazione senza consigli", "consiglio" not in
         r["risposta_finale"].lower())

print("— nome uguale alla stanza, switch mostrato come luce")
nomi.azzera_consigli()
r, ctx = chiama("casa_comando", comando="spegni la luce in cucina")
verifica("«Cucina» nell'area Cucina: riprova e frase semplice, il forno no",
         casa.eseguiti == [("HassTurnOff", ["light.cucina"])]
         and r["risposta_finale"] == "Ho spento «Cucina».", f"{casa.eseguiti} {r}")
verifica("nessun consiglio se l'area è già quella detta", nomi.consigli_da_dire() == [])
r, _ = chiama("casa_comando", comando="accendi la luce in studio")
verifica("switch con «luce» nel nome: candidato unico (non la presa «Studio»)",
         casa.eseguiti == [("HassTurnOn", ["switch.rele_studio"])], str(casa.eseguiti))
verifica("senza area lo dice", r["risposta_finale"] ==
         "Ho acceso «Luce studio»: in Home Assistant non è in nessuna stanza.",
         r["risposta_finale"])
r, _ = chiama("casa_comando", comando="chiudi la luce in studio")
verifica("«chiudi la luce» diventa «spegni» nella riprova", casa.comandi[-1] ==
         "spegni Luce studio" and r["risposta_finale"].startswith("Ho spento"), str(casa.comandi))
r, _ = chiama("casa_comando", comando="spegni la presa in studio")
verifica("«la presa in studio»: lo switch «Studio» (e anche il relè, è uno switch) → domanda",
         casa.eseguiti == [] and "Quale intendi?" in r["risposta_finale"], r["risposta_finale"])

print("— più candidate, nessuna")
r, ctx = chiama("casa_comando", comando="accendi la luce in taverna")
verifica("due candidate: le elenca e chiede quale, niente eseguito",
         casa.eseguiti == [] and r["risposta_finale"] ==
         "Ho trovato più dispositivi: «Taverna», nell'area Cantina o «Faretti taverna», "
         "nell'area Taverna. Quale intendi?" and r.get("ok") is False, r["risposta_finale"])
verifica("domanda: regola nel registro", "casa_nome_entita" in ctx.regole)
r, ctx = chiama("casa_comando", comando="accendi la luce in mansarda")
verifica("nessuna candidata: la frase del codice vero, non «non ha capito»",
         r["risposta_finale"] == "In Home Assistant non trovo un dispositivo esposto ad Assist "
         "che corrisponda alla richiesta." and casa.comandi == ["accendi la luce in mansarda"],
         r["risposta_finale"])
verifica("nessuna candidata: nessuna regola nel registro", "casa_nome_entita" not in ctx.regole)
casa.errori["spegni la luce in ingresso"] = (
    "Mi dispiace, nell'area Ingresso il dominio light non è stato esposto", "no_valid_targets")
r, _ = chiama("casa_comando", comando="spegni la luce in ingresso")
verifica("«luce in ingresso»: per area «Soggiorno» e «Altra» → domanda, non una scelta",
         casa.eseguiti == [] and "Quale intendi?" in r["risposta_finale"], r["risposta_finale"])
casa.errori.clear()

print("— mai allargare, mai i delicati")
casa.allarga["spegni Soggiorno"] = ["light.ingresso_1", "light.altra"]
r, _ = chiama("casa_comando", comando="spegni la luce in soggiorno")
verifica("la riprova che toccherebbe altro non si esegue", casa.eseguiti == [] and
         casa.comandi[-1] == "spegni Soggiorno", str(casa.eseguiti))
verifica("…e si dice l'errore di prima", r["risposta_finale"].startswith(
    "In Home Assistant non trovo"), r["risposta_finale"])
casa.allarga.clear()
for testo in ("apri il cancello in giardino", "accendi il cancello", "apri il portone",
              "accendi la notte", "spegni il forno in cucina"):
    r, ctx = chiama("casa_comando", comando=testo)
    verifica(f"contrario «{testo}»: nessuna riprova (delicati, scene, né nome né area)",
             len(casa.comandi) == 1 and casa.eseguiti == [], str(casa.comandi))
for testo in ("imposta la luce in soggiorno al 30%", "accendi la luce in soggiorno al 30 per cento",
              "metti la luce in soggiorno", "alza la luce in soggiorno"):
    r, ctx = chiama("casa_comando", comando=testo)
    verifica(f"contrario «{testo}»: verbi, percentuali e tipi non adatti restano al modello",
             "casa_nome_entita" not in ctx.regole and casa.eseguiti == [], str(casa.comandi))
r, _ = chiama("casa_comando", comando="abbassa la tapparella in camera nord")
verifica("tapparella per area: abbassa «Camera»", casa.eseguiti == [("HassTurnOff",
                                                                     ["cover.camera"])],
         str(casa.eseguiti))

print("— ospite e lettura")
cfg_o = Config()
cfg_o.casa_ospite_domini = ["light"]
r, _ = chiama("casa_comando", livello="ospite", chi=None, cfg_=cfg_o,
              comando="accendi la luce in studio")
verifica("l'ospite non vede lo switch: nessuna riprova", len(casa.comandi) == 1, str(casa.comandi))
r, _ = chiama("casa_comando", livello="ospite", chi=None, cfg_=cfg_o,
              comando="spegni la luce in soggiorno")
verifica("l'ospite con le luci permesse: la luce sì", casa.eseguiti == [
    ("HassTurnOff", ["light.ingresso_1", "light.vecchia"])], str(casa.eseguiti))
verifica("candidate: niente per una domanda", nomi.candidate(
    "che luce c'è in soggiorno", CASA, AREE, lambda e: True) is None)
verifica("candidate: niente senza una stanza", nomi.candidate(
    "spegni la luce", CASA, AREE, lambda e: True) is None)

print("— frasi d'errore di HA con il codice vero")
for speech, code, atteso in [
        ("Mi dispiace, non ho capito", "no_valid_targets",
         "In Home Assistant non trovo un dispositivo esposto ad Assist che corrisponda alla "
         "richiesta."),
        ("Mi dispiace, non ho capito.", "failed_to_handle",
         "Home Assistant ha avuto un errore inatteso: il comando non è andato a buon fine."),
        ("Mi dispiace, non ho capito", "no_intent_match", "Home Assistant non ha capito il comando."),
        ("Mi dispiace, non ho capito", "", "Home Assistant non ha capito il comando."),
        ("Mi dispiace, non ho capito", "unknown", "Home Assistant non ha capito il comando.")]:
    verifica(f"«{speech}» con {code or 'nessun codice'}", riformula_errore(speech, code)[0]
             == atteso, riformula_errore(speech, code)[0])

print(json.dumps({"errori": errori}))
sys.exit(1 if errori else 0)
