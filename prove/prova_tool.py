import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dei tool nativi e dei permessi per livello (nessun modello caricato).

Dal 26/09 verifica davvero (prima stampava soltanto): elenco dei tool per livello,
esiti dei tool con un contesto finto, rifiuto dei tool vietati. Dal 03/10 il modello vede
lo stesso elenco a ogni livello (ToolRegistry.schemas): gli elenchi per livello qui sotto
sono i **permessi** (ToolRegistry.schemas_for), che il registro controlla a ogni esecuzione.
"""

import json

from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


class FakeProfile:
    def __init__(self, name):
        self.id = name.lower() + "-id"
        self.name = name
        self.gender = "m"
        self.preferred_voice = None
        self.admin = False


class FakeSpeakers:
    def __init__(self):
        self.users = {"Dario": FakeProfile("Dario"), "Primo": FakeProfile("Primo")}

    def known_speakers(self):
        return list(self.users)

    def get(self, n):
        return self.users.get(n)

    def save(self):
        pass

    def rename(self, old, new):
        prof = self.users.pop(old, None)
        if prof is None:
            return None
        prof.name = new
        self.users[new] = prof
        return prof


class FakeCtx:
    def __init__(self, current_speaker="Dario"):
        self.current_speaker = current_speaker
        self.enroll_needed = 5
        self.enrolling = None

    @property
    def current_level(self):
        return "ospite" if self.current_speaker is None else "familiare"

    def start_enroll(self, name):
        self.enrolling = name


class FakeSpeaker:
    def change_voice(self, p):
        return True


cfg = Config()
reg = build_registry()

# ── permessi per livello (cosa il registro esegue; il modello li vede tutti) ──
OSPITE = {"chi_parla", "elenca_voci", "ora_attuale", "data_oggi", "calcola", "data_calcola",
          "timer_imposta",
          "agenda_elenca", "agenda_annulla", "calliope_stato",
          # la città di casa (09/10): per tutti, ma la salva solo chi amministra (nel codice)
          "citta_casa_salva"}
FAMILIARE = OSPITE | {"elenca_utenti", "cambia_voce", "rinomina_interlocutore",
                      "promemoria_imposta", "ricorda", "dimentica", "lista_aggiungi",
                      "lista_leggi", "lista_togli", "appuntamento_aggiungi",
                      "appuntamenti_elenca", "installa_proponi", "installa_gestisci"}
# installa_avvia solo a chi amministra (01/10): anche nascosto, il codice lo ricontrolla
# registra_utente solo a chi amministra (05/10, minori: «aggiungi un familiare» con la sfida)
AMMINISTRA = FAMILIARE | {"installa_avvia", "registra_utente"}
for level, atteso in (("ospite", OSPITE), ("familiare", FAMILIARE), ("amministra", AMMINISTRA)):
    names = {s["function"]["name"] for s in reg.schemas_for(level)}
    verifica(f"tool ammessi per {level}: {len(names)}", names == atteso,
             "" if names == atteso else f"in più {names - atteso}, mancano {atteso - names}")

# Con il PC (esecutore finto, tutte le capacità): 8 tool pc_* per la famiglia, nessuno per
# l'ospite (Config.pc_ospite_volume_media è False). Il registro qui sopra resta senza PC,
# come quando le librerie mancano o non è Windows.
from prove.pc_finto import FakePC

PC = {"pc_stato", "pc_volume", "pc_media", "pc_luminosita", "pc_apri_app", "pc_blocca",
      "pc_cerca_file", "pc_apri_file"}
reg_pc = build_registry(pc={"portatile": FakePC()})
for level, atteso in (("ospite", OSPITE), ("familiare", FAMILIARE | PC),
                      ("amministra", AMMINISTRA | PC)):
    names = {s["function"]["name"] for s in reg_pc.schemas_for(level)}
    verifica(f"tool ammessi per {level} con il PC: {len(names)}", names == atteso,
             "" if names == atteso else f"in più {names - atteso}, mancano {atteso - names}")


def chiama(nome, args, speaker="Dario", level=None):
    ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx(speaker),
                      speaker=FakeSpeaker())
    return json.loads(reg.call(nome, args, ctx, level))


# ── esiti ──
verifica("chi_parla", chiama("chi_parla", {}) == {"nome": "Dario", "riconosciuto": True})
verifica("chi_parla senza livello nel risultato", "livello" not in chiama("chi_parla", {}))
verifica("ora_attuale", ":" in chiama("ora_attuale", {}).get("ora", ""))
verifica("elenca_voci senza doppioni", len(set(v := chiama("elenca_voci", {})["voci"])) == len(v), str(v))
verifica("cambia_voce paola", chiama("cambia_voce", {"voce": "paola"}).get("ok") is True)
verifica("cambia_voce sconosciuta", chiama("cambia_voce", {"voce": "inesistente"}).get("ok") is False)
# Dal 05/10 una persona nuova vuole la data di nascita (o «maggiorenne»): senza, la domanda
verifica("registra_utente: nome pulito (nella domanda sulla data di nascita)",
         "Mario Rossi" in chiama("registra_utente", {"nome": "mario rossi"}).get(
             "risposta_finale", ""))
verifica("rinomina senza argomento → errore leggibile",
         "errore" in chiama("rinomina_interlocutore", {}))
verifica("tool inesistente → errore", "errore" in chiama("tool_inesistente", {}))

# ── rinomina con conferma (02/10): propone, cambia solo nella risposta dopo ──
ctx_r = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx("Dario"),
                    speaker=FakeSpeaker())


def rinomina(nome, turno):
    ctx_r.turno = turno
    return json.loads(reg.call("rinomina_interlocutore", {"nome": nome}, ctx_r, "familiare"))


r = rinomina("davio", 1)
verifica("rinomina: la prima chiamata propone e non cambia niente",
         r.get("risposta_finale") == "Vuoi che ti chiami Davio d'ora in poi?"
         and r["in_sospeso"]["argomenti"] == {"nome": "Davio"}
         and "Dario" in ctx_r.speakers.users, str(r))
r = rinomina("Davio", 1)
verifica("rinomina: nello stesso turno della proposta no", "Dario" in ctx_r.speakers.users
         and r.get("in_sospeso"), str(r))
r = rinomina("Davide", 2)
verifica("rinomina: un altro nome nel turno dopo è una proposta nuova",
         "Dario" in ctx_r.speakers.users and "Davide" in r.get("risposta_finale", ""), str(r))
r = rinomina("Davide", 6)
verifica("rinomina: quattro turni dopo la proposta no (valida per 3, 04/10)",
         "Dario" in ctx_r.speakers.users and r.get("in_sospeso"), str(r))
r = rinomina("Davide", 9)
verifica("rinomina: lo stesso nome tre turni dopo la proposta → rinominato",
         "Davide" in ctx_r.speakers.users and ctx_r.speaker_ctx.current_speaker == "Davide"
         and r.get("fatto") == "rinominato", str(r))
r = rinomina("primo", 10)
verifica("rinomina: il nome di un'altra persona registrata è rifiutato",
         r.get("ok") is False and "Primo" in ctx_r.speakers.users
         and ctx_r.speakers.users["Primo"].id == "primo-id", str(r))
verifica("calcola 17*6", chiama("calcola", {"espressione": "17*6"}).get("risultato") == "102")
# Conti con le date (05/10 sera, DGX: calcola('2026-07-04-1977-07-04') → errore, poi
# 2026−1977): data_calcola con le date come dette, la data di oggi la sa il programma
import datetime as _dt
_oggi = _dt.date.today()
r = chiama("calcola", {"espressione": "2026-07-04-1977-07-04"})
verifica("calcola con una data: rimanda a data_calcola", r.get("ok") is False
         and "data_calcola" in r.get("errore", ""), str(r))
verifica("contrario: calcola 2026-1977 resta un conto",
         chiama("calcola", {"espressione": "2026-1977"}).get("risultato") == "49")
_anni = _oggi.year - 1977 - ((_oggi.month, _oggi.day) < (7, 4))
for data in ("4 luglio 1977", "il 4 luglio del 1977", "04/07/1977", "1977-07-04", "4/7/77"):
    r = chiama("data_calcola", {"cosa": "eta", "data": data})
    verifica(f"data_calcola età da «{data}»: {_anni}", r.get("anni") == _anni
             and f" {_anni} anni" in r.get("da_dire", ""), str(r))
r = chiama("data_calcola", {"cosa": "eta", "data": "4 luglio"})
verifica("età senza anno: errore che chiede l'anno", r.get("ok") is False
         and "anno" in r.get("errore", ""), str(r))
r = chiama("data_calcola", {"cosa": "giorno_settimana", "data": "4 luglio 1977"})
verifica("4 luglio 1977 era un lunedì", r.get("giorno") == "lunedì"
         and r.get("da_dire") == "Il 4 luglio 1977 era un lunedì.", str(r))
_natale = _dt.date(_oggi.year, 12, 25)
_natale = _natale if _natale >= _oggi else _dt.date(_oggi.year + 1, 12, 25)
r = chiama("data_calcola", {"cosa": "giorni_mancanti", "data": "Natale"})
verifica("giorni a Natale (il prossimo)", r.get("giorni") == (_natale - _oggi).days, str(r))
r = chiama("data_calcola", {"cosa": "differenza", "data": "1 gennaio 2026",
                            "data2": "1 gennaio 2027"})
verifica("differenza tra due date: 365 giorni, 1 anno", r.get("giorni") == 365
         and r.get("anni") == 1, str(r))
r = chiama("data_calcola", {"cosa": "giorni_mancanti", "data": "31 febbraio 2027"})
verifica("data impossibile: errore, niente eccezione", r.get("ok") is False, str(r))
r = chiama("data_calcola", {"cosa": "boh", "data": "oggi"})
verifica("cosa sconosciuta: errore", r.get("ok") is False, str(r))

# ── il modello vede gli stessi tool a ogni livello (03/10) ──
verifica("elenco del modello: tutti i tool, uguale per ogni livello",
         [s["function"]["name"] for s in reg_pc.schemas()]
         == [s["function"]["name"] for s in reg_pc.all_schemas()], "")

# ── permessi: il registro rifiuta a ogni esecuzione, con una frase pronta ──
from calliope.tools.registry import REFUSAL
r = chiama("cambia_voce", {"voce": "paola"}, speaker=None, level="ospite")
verifica("ospite: cambia_voce rifiutato in modo esplicito, con la frase pronta",
         r.get("ok") is False and "NON" in r.get("fatto", "")
         and r.get("risposta_finale") == REFUSAL["ospite"]
         and "come sempre" in r.get("per_il_resto", ""), str(r))
r = chiama("installa_avvia", {"azione": "biblioteca"}, level="familiare")
verifica("familiare: installa_avvia rifiutato, frase di chi amministra",
         r.get("ok") is False and r.get("risposta_finale") == REFUSAL["familiare"], str(r))
verifica("amministra: niente rifiuto per permessi",
         chiama("elenca_utenti", {}, level="amministra").get("ok") is not False)
_ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx(None),
                   speaker=FakeSpeaker())
_ctx.regole = []
reg.call("ricorda", {"fatto": "x"}, _ctx, "ospite")
verifica("rifiuto per permessi nel registro dei turni", _ctx.regole == ["permesso_livello"],
         str(_ctx.regole))
r = chiama("ricorda", {"fatto": "x"}, speaker=None, level="ospite")
verifica("ospite: ricorda rifiutato", r.get("ok") is False)
r = chiama("lista_aggiungi", {"cose": "latte"}, speaker=None, level="ospite")
verifica("ospite: lista_aggiungi rifiutato", r.get("ok") is False and "NON" in r.get("fatto", ""),
         str(r))
r = chiama("appuntamento_aggiungi", {"cosa": "dentista", "quando": "domani alle 9"},
           speaker=None, level="ospite")
verifica("ospite: appuntamento_aggiungi rifiutato", r.get("ok") is False)

# ── nome del tool storpiato (06/10, prova e2e B2: «richesta_tutore») ──
from calliope.tools.registry import ToolRegistry, distanza
from calliope.tools.minori import minori_specs
from calliope.tools.spec import ToolSpec

verifica("distanza: una lettera tolta, uno scambio, nomi lontani",
         distanza("richesta_tutore", "richiesta_tutore") == 1 and distanza("ab", "ba") == 1
         and distanza("kitten", "sitting") == 3 and distanza("abc", "abcdefgh", 2) == 3)
reg_m = build_registry(pc={"portatile": FakePC()})
for spec in minori_specs():
    reg_m.register(spec)
verifica("«richesta_tutore» → richiesta_tutore",
         reg_m.nome_vicino("richesta_tutore") == "richiesta_tutore")
_ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx("Dario"),
                   speaker=FakeSpeaker())
_ctx.regole = []
r = json.loads(reg.call("orra_attuale", {}, _ctx, "familiare"))
verifica("nome storpiato vicino: eseguito il tool giusto, regola nel registro dei turni",
         ":" in r.get("ora", "") and _ctx.regole == ["tool_nome_corretto"], f"{r} {_ctx.regole}")
_ctx.regole = []
r = json.loads(reg.call("ricodra", {"fatto": "x"}, _ctx, "ospite"))
verifica("il nome corretto passa dai permessi: «ricodra» da un ospite → rifiutato",
         r.get("ok") is False and _ctx.regole == ["tool_nome_corretto", "permesso_livello"],
         f"{r} {_ctx.regole}")
_ctx.regole = []
r = json.loads(reg.call("Ora-Attuale", {}, _ctx, "familiare"))
verifica("maiuscole e trattini contano zero", ":" in r.get("ora", ""), str(r))
_ctx.regole = []
r = json.loads(reg.call("orario_attuale", {}, _ctx, "familiare"))
verifica("contrario: distanza 3 → niente eseguito, il nome giusto nell'errore",
         "errore" in r and r.get("ok") is False and "ora_attuale" in r.get("nomi_giusti", [])
         and _ctx.regole == [], str(r))
r = json.loads(reg.call("accendi_luce", {}, _ctx, "familiare"))
verifica("contrario: nome lontano → errore senza suggerimenti", "errore" in r
         and "nomi_giusti" not in r and _ctx.regole == [], str(r))
verifica("contrario: nome corto mai corretto", reg.nome_vicino("orx") is None)
amb = ToolRegistry()
for n in ("est_meteo_casa", "est_meteo_cosa"):
    amb.register(ToolSpec(name=n, description="x", parameters={"type": "object",
                                                               "properties": {}},
                          func=lambda ctx: {"ok": True}, levels=frozenset({"familiare"})))
r = json.loads(amb.call("est_meteo_cesa", {}, _ctx, "familiare"))
verifica("contrario: due tool vicinissimi → ambiguo, niente eseguito, entrambi suggeriti",
         amb.nome_vicino("est_meteo_cesa") is None and "errore" in r
         and set(r.get("nomi_giusti", [])) == {"est_meteo_casa", "est_meteo_cosa"}, str(r))
# Nessun tool vero a distanza ≤ 2 da un altro: un nome giusto non diventa mai un altro tool
nomi = sorted(n for n in (s["function"]["name"] for s in reg_m.all_schemas()))
vicini = [(a, b) for i, a in enumerate(nomi) for b in nomi[i + 1:] if distanza(a, b, 2) <= 2]
verifica(f"nessuna coppia di tool veri a distanza ≤ 2 ({len(nomi)} tool)", not vicini,
         str(vicini))
verifica("un nome esatto non si corregge", all(reg_m.nome_vicino(n) is None for n in nomi))

# Brain: il nome si corregge prima di tutto il resto (riservatezza, schede, politica)
from calliope.brain import Brain
b = Brain.__new__(Brain)
b.tools, b.last_rules = reg, []
call = {"id": "c1", "name": "orra_attuale", "arguments": {}}
b._nome_corretto(call)
verifica("Brain: la chiamata prende il nome giusto e la regola",
         call["name"] == "ora_attuale" and b.last_rules == ["tool_nome_corretto"], str(call))
call = {"id": "c2", "name": "orario_attuale", "arguments": {}}
b._nome_corretto(call)
verifica("Brain, contrario: un nome lontano resta com'è", call["name"] == "orario_attuale")

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
