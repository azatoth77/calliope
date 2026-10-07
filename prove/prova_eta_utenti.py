import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Età, compleanni e persone registrate (07/10), dai casi veri della DGX del 06/10 sera, a
secco e con nomi di fantasia.

1. Una ragazza registrata con la data di nascita chiede «Quanti anni ho?»: il modello passava
   a data_calcola la data di oggi e diceva «oggi è il tuo compleanno». Ora la data di oggi
   come nascita è rifiutata (regola `data_eta_oggi`), `persona` («io» o un nome) prende la
   data dal profilo, e la data di nascita è nei dati del turno (minori.dato_nascita).
2. Il genitore chiede il compleanno: i giorni li conta il programma (339, non 309).
3. Privacy: età e compleanno di un altro solo a chi amministra e ai tutori; gli ospiti no.
4. elenca_utenti: `impronta_voce` sì/no (il vecchio «voce: null» era la voce di Calliope e
   il modello diceva «non ha ancora una sua voce»), niente rubrica dell'ufficio.
5. I tool di ricerca hanno `required`: `{}` si ferma (tool_argomenti_mancanti).
6. Registro dei turni: di un ospite restano i numeri di parole, non il testo.
7. La propria data di nascita (07/10 pomeriggio): data_calcola con la data passata dal
   modello se il profilo non ce l'ha, ricorda con `nascita` che propone di salvarla nel
   profilo (al «sì», solo per sé, mai per un minore), la rete «ho recuperato il dato» dopo
   soli tool falliti.
"""

import ast
import datetime
import json
import tempfile
from pathlib import Path

from calliope import minori
from calliope.config import Config
from calliope.tools import builtin as B
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


class Prof:
    def __init__(self, name, admin=False, nascita=None, tutori=(), impronta=True):
        self.id, self.name, self.admin = name.lower() + "-id", name, admin
        self.nascita, self.tutori, self.fascia = nascita, list(tutori), None
        self.voiceprint = [0.1] if impronta else None
        self.gender, self.preferred_voice, self.preferred_tone = None, None, None


class Speakers:
    def __init__(self):
        self.users = {
            "Marta": Prof("Marta", admin=True, nascita="1980-03-15"),
            "Bianca": Prof("Bianca", nascita="2012-09-10", tutori=["marta-id"]),
            "Luca": Prof("Luca"),
            "Tea": Prof("Tea", nascita="2019-01-01", tutori=["marta-id"], impronta=False),
        }

    def known_speakers(self):
        return list(self.users)

    def get(self, n):
        return self.users.get(n)

    def find(self, n):
        return next((k for k in self.users if k.casefold() == (n or "").strip().casefold()),
                    None)

    salvataggi = 0

    def save(self):
        self.salvataggi += 1


class SC:
    def __init__(self, name):
        self.current_speaker = name
        self.identified_by = "voce" if name else None

    @property
    def current_level(self):
        return "ospite" if self.current_speaker is None else (
            "amministra" if self.current_speaker == "Marta" else "familiare")


cfg = Config()
reg = build_registry()
SPEAKERS = Speakers()


def chiama(nome, args, chi="Marta"):
    ctx = ToolContext(cfg=cfg, speakers=SPEAKERS, speaker_ctx=SC(chi), speaker=None)
    ctx.regole = []
    livello = SC(chi).current_level
    return json.loads(reg.call(nome, args, ctx, livello)), ctx.regole


OGGI = datetime.date.today()


def anni(d):
    return OGGI.year - d.year - ((OGGI.month, OGGI.day) < (d.month, d.day))


# ── 1. i giorni al compleanno li conta il programma (caso vero: 339, il modello diceva 309) ──
d = B._dati_nascita(SPEAKERS.get("Bianca"), datetime.date(2026, 10, 6))
verifica("06/10/2026, nata il 10/09/2012: 14 anni, compleanno tra 339 giorni",
         (d.get("anni"), d.get("giorni_al_compleanno"), d.get("prossimo_compleanno"))
         == (14, 339, "10 settembre 2027"), str(d))
d = B._dati_nascita(SPEAKERS.get("Bianca"), datetime.date(2026, 9, 10))
verifica("il giorno del compleanno: 14 anni, 0 giorni", (d["anni"], d["giorni_al_compleanno"])
         == (14, 0), str(d))
verifica("senza data di nascita: niente dati", B._dati_nascita(SPEAKERS.get("Luca")) == {})

# ── data di oggi passata come nascita: rifiutata, con la strada giusta ──
r, regole = chiama("data_calcola", {"cosa": "eta", "data": OGGI.isoformat()}, chi="Bianca")
verifica("eta con la data di oggi: rifiutata, indica persona",
         r.get("ok") is False and "oggi" in r.get("errore", "")
         and "persona" in r.get("cosa_fare", "") and regole == ["data_eta_oggi"], str(r))
r, regole = chiama("data_calcola", {"cosa": "eta", "data": "oggi"}, chi="Bianca")
verifica("eta con «oggi»: rifiutata", r.get("ok") is False and regole == ["data_eta_oggi"])
r, regole = chiama("data_calcola", {"cosa": "eta", "data": "10 settembre 2012"}, chi="Bianca")
verifica("contrario: una data di nascita vera dà gli anni, nessuna regola",
         r.get("anni") == anni(datetime.date(2012, 9, 10)) and regole == [], str(r))
r, regole = chiama("data_calcola", {"cosa": "giorni_mancanti", "data": "oggi"}, chi="Bianca")
verifica("contrario: giorni_mancanti a oggi resta «È oggi.»", r.get("da_dire") == "È oggi.",
         str(r))
r, _ = chiama("data_calcola", {"cosa": "eta"}, chi="Bianca")
verifica("eta senza data né persona: errore che indica persona",
         r.get("ok") is False and "persona" in r.get("errore", ""), str(r))
r, regole = chiama("data_calcola", {}, chi="Bianca")
verifica("data_calcola({}): fermato (tool_argomenti_mancanti)",
         r.get("ok") is False and regole == ["tool_argomenti_mancanti"], str(r))

# ── persona: la data del profilo ──
nb = datetime.date(2012, 9, 10)
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "io"}, chi="Bianca")
verifica("«Quanti anni ho?» con persona=io: anni dal profilo, detto a lei",
         r.get("ok") and r.get("anni") == anni(nb) and r.get("da_dire", "").startswith(
             ("Hai", "Oggi compi")), str(r))
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "io",
                               "data": OGGI.isoformat()}, chi="Bianca")
verifica("persona vince sulla data di oggi passata insieme", r.get("anni") == anni(nb), str(r))
r, _ = chiama("data_calcola", {"cosa": "giorni_mancanti", "persona": "Bianca"}, chi="Marta")
prossimo = datetime.date(OGGI.year, 9, 10)
prossimo = prossimo if prossimo >= OGGI else datetime.date(OGGI.year + 1, 9, 10)
verifica("chi amministra: compleanno di Bianca, giorni contati dal programma",
         r.get("ok") and r.get("giorni_al_compleanno") == (prossimo - OGGI).days
         and r.get("da_dire", "").startswith(("Bianca ha", "Oggi Bianca")), str(r))
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "bianca"}, chi="Marta")
verifica("il nome con la minuscola", r.get("persona") == "Bianca", str(r))
r, regole = chiama("data_calcola", {"cosa": "eta", "persona": "Bianca"}, chi="Luca")
verifica("un familiare che non è tutore: età di Bianca riservata, frase pronta",
         r.get("ok") is False and "risposta_finale" in r and "anni" not in r
         and regole == ["nascita_riservata"], str(r))
r, regole = chiama("data_calcola", {"cosa": "eta", "persona": "Marta"}, chi="Bianca")
verifica("una minore non sa l'età del genitore dal profilo", r.get("ok") is False
         and regole == ["nascita_riservata"], str(r))
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "io"}, chi=None)
verifica("ospite: «non so chi sta parlando»", r.get("ok") is False
         and "non so chi" in r.get("errore", ""), str(r))
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "io"}, chi="Luca")
verifica("profilo senza data di nascita: lo dice e chiede la data", r.get("ok") is False
         and "data di nascita" in r.get("errore", ""), str(r))
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "Giovanni"}, chi="Marta")
verifica("persona non registrata: errore chiaro", r.get("ok") is False
         and "non è una persona registrata" in r.get("errore", ""), str(r))

# ── 4. elenca_utenti e chi_parla ──
r, _ = chiama("elenca_utenti", {}, chi="Marta")
u = {x["nome"]: x for x in r["utenti"]}
verifica("elenca_utenti: impronta della voce sì/no, niente «voce» ambigua",
         (u["Bianca"]["impronta_voce"], u["Tea"]["impronta_voce"], "voce" in u["Bianca"])
         == ("sì", "no", False), str(u["Bianca"]))
verifica("elenca_utenti per chi amministra: età e compleanno di tutti quelli che ce l'hanno",
         u["Bianca"].get("anni") == anni(nb) and u["Bianca"].get("minorenne") is True
         and "anni" in u["Marta"] and "anni" not in u["Luca"], str(u))
r, _ = chiama("elenca_utenti", {}, chi="Luca")
u = {x["nome"]: x for x in r["utenti"]}
verifica("elenca_utenti per un familiare non tutore: niente età degli altri",
         not any("anni" in x or "nascita" in x for x in u.values()), str(u))
r, _ = chiama("elenca_utenti", {}, chi="Bianca")
u = {x["nome"]: x for x in r["utenti"]}
verifica("elenca_utenti per la minore: la sua età sì, quella degli altri no",
         "anni" in u["Bianca"] and "anni" not in u["Marta"] and "anni" not in u["Tea"], str(u))
r, _ = chiama("chi_parla", {}, chi="Bianca")
verifica("chi_parla: nome, età e compleanno di chi parla", r.get("nome") == "Bianca"
         and r.get("anni") == anni(nb) and r.get("nascita") == "10 settembre 2012", str(r))
r, _ = chiama("chi_parla", {}, chi=None)
verifica("chi_parla di un ospite: solo «non riconosciuto»", r == {"nome": None,
                                                                 "riconosciuto": False}, str(r))

# ── dati del turno: la data di nascita di chi parla ──
verifica("dato_nascita: data e anni", minori.dato_nascita(
    SPEAKERS.get("Bianca"), datetime.date(2026, 10, 6))
         == "data di nascita 10 settembre 2012 (14 anni)")
verifica("dato_nascita senza data: vuoto", minori.dato_nascita(SPEAKERS.get("Luca")) == "")
from calliope.brain import Brain  # noqa: E402
b = Brain.__new__(Brain)
b.cfg, b.last_rules = cfg, []
b.tool_ctx = ToolContext(cfg=cfg, speakers=SPEAKERS, speaker_ctx=SC("Bianca"), speaker=None)
nota = b._turn_context()[0]["content"]
verifica("contesto del turno di Bianca: minorenne e data di nascita",
         "minorenne" in nota and "data di nascita 10 settembre 2012" in nota, nota[:300])
b.tool_ctx = ToolContext(cfg=cfg, speakers=SPEAKERS, speaker_ctx=SC("Marta"), speaker=None)
nota = b._turn_context()[0]["content"]
verifica("contesto del turno di un adulto con la data: la data sì, «minorenne» no",
         "data di nascita 15 marzo 1980" in nota and "minorenne" not in nota, nota[:300])
b.tool_ctx = ToolContext(cfg=cfg, speakers=SPEAKERS, speaker_ctx=SC("Luca"), speaker=None)
nota = b._turn_context()[0]["content"]
verifica("contrario: senza data nel profilo niente data di nascita", "nascita" not in nota)

# ── 5. tool di ricerca con `required`; rubrica e persone di casa distinte ──
radice = Path(__file__).resolve().parent.parent / "calliope"
senza = []
for f in radice.rglob("*.py"):
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        if not (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "ToolSpec"):
            continue
        kw = {k.arg: k.value for k in n.keywords}
        nome = kw.get("name")
        nome = nome.value if isinstance(nome, ast.Constant) else ""
        # pc_cerca_file: basta il tipo o il periodo («i PDF della settimana scorsa»)
        if not nome.endswith("_cerca") or nome == "pc_cerca_file":
            continue
        par = kw.get("parameters")
        req = None
        if isinstance(par, ast.Dict):
            for k, v in zip(par.keys, par.values):
                if isinstance(k, ast.Constant) and k.value == "required":
                    req = v
        if not (isinstance(req, ast.List) and req.elts):
            senza.append(nome)
verifica("ogni tool *_cerca ha argomenti obbligatori (la regola li ferma con {})", not senza,
         str(senza))
from calliope.tools.conversazioni import conversazioni_specs  # noqa: E402
from calliope.tools.ufficio import ufficio_specs  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
r2 = ToolRegistry()
for s in conversazioni_specs() + ufficio_specs(["fattura"]):
    r2.register(s)
verifica("conversazione_cerca({}) e anagrafica_cerca({}): mancano domanda e testo",
         (r2.mancanti("conversazione_cerca", {}), r2.mancanti("anagrafica_cerca", {}))
         == (["domanda"], ["testo"]))
desc = {s.name: s.description for s in ufficio_specs(["fattura"])}
verifica("anagrafica_cerca: rubrica dell'ufficio, rimanda a elenca_utenti per la casa",
         "ufficio" in desc["anagrafica_cerca"] and "elenca_utenti" in desc["anagrafica_cerca"])
eu = reg.get("elenca_utenti").description
verifica("elenca_utenti: persone della casa, impronta della voce, rimanda ad anagrafica_cerca",
         "casa" in eu and "impronta" in eu and "anagrafica_cerca" in eu)

# ── 6. registro dei turni: di un ospite i numeri di parole ──
from calliope.turnlog import TurnLog  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    tl = TurnLog(tmp)
    tl.write({"inizio": "2026-10-06T18:52:23", "livello": "ospite", "testo": "Chi sono io?",
            "richiesta": "Chi sono io?", "risposta": "Non ti riconosco dalla voce.",
            "tool": [{"nome": "chi_parla", "argomenti": {}}]})
    tl.write({"inizio": "2026-10-06T18:52:30", "livello": "familiare", "testo": "Ciao.",
            "risposta": "Ciao!"})
    righe = [json.loads(x) for f in Path(tmp).glob("*.jsonl")
             for x in f.read_text(encoding="utf-8").splitlines()]
o, f = righe
verifica("ospite: testo e risposta tolti, restano le parole (3 e 5)",
         (o["testo"], o["risposta"], o.get("testo_parole"), o.get("risposta_parole"))
         == (None, None, 3, 5), str(o))
verifica("contrario: per un familiare niente conteggi", "testo_parole" not in f
         and f["testo"] == "Ciao.", str(f))

# ── 7. la propria data di nascita (07/10 pomeriggio, caso vero della DGX) ──
# Un adulto senza data nel profilo: «Quanti anni ho?» falliva; «ricordati che il mio
# compleanno è il 4 luglio del 1977» era solo un ricordo, e data_calcola(persona=io) falliva
# di nuovo. Ora: (a) con la data passata dal modello si conta; (b) ricorda con `nascita`
# propone di salvarla nel profilo e la salva al «sì»; (c) brain: la rete sulle dichiarazioni
r, regole = chiama("data_calcola", {"cosa": "eta", "persona": "io"}, chi="Luca")
verifica("(a) senza data nel profilo: l'errore dice di passare la data se la conosce dai ricordi",
         r.get("ok") is False and "ricordi" in r.get("cosa_fare", "")
         and "data" in r.get("cosa_fare", ""), str(r))
n77 = datetime.date(1977, 7, 4)
r, regole = chiama("data_calcola", {"cosa": "eta", "persona": "io", "data": "4 luglio 1977"},
                   chi="Luca")
verifica("(a) persona=io e la data passata dal modello: anni contati, detto a lui",
         r.get("ok") and r.get("anni") == anni(n77) and r.get("da_dire", "").startswith(
             ("Hai", "Oggi compi")) and "eta_data_dal_modello" in regole, str(r))
r, regole = chiama("data_calcola", {"cosa": "eta", "persona": "io", "data": "4 luglio 1977"},
                   chi="Bianca")
verifica("(a) contrario: con la data nel profilo vince il profilo",
         r.get("anni") == anni(nb) and "eta_data_dal_modello" not in regole, str(r))
r, regole = chiama("data_calcola", {"cosa": "eta", "persona": "Bianca",
                                    "data": "10 settembre 2012"}, chi="Luca")
verifica("(a) contrario: l'età di un'altra riservata anche con la data passata",
         r.get("ok") is False and regole == ["nascita_riservata"], str(r))

from calliope.memory import Memory  # noqa: E402
_mem_dir = tempfile.mkdtemp()


def ctx_di(chi, turno, detto, storia=()):
    ctx = ToolContext(cfg=cfg, speakers=SPEAKERS, speaker_ctx=SC(chi), speaker=None)
    ctx.memory = MEM
    ctx.regole, ctx.turno, ctx.user_text, ctx.storia = [], turno, detto, list(storia)
    return ctx


def chiama_ctx(ctx, nome, args):
    return json.loads(reg.call(nome, args, ctx, ctx.speaker_ctx.current_level))


MEM = Memory(str(Path(_mem_dir) / "m.db"))
DETTO = "Ok, ricordati che il mio compleanno è il 4 luglio del 1977."
ARGS = {"fatto": "Il compleanno di Luca è il 4 luglio 1977.", "nascita": "4 luglio 1977"}
luca = SPEAKERS.get("Luca")
ctx = ctx_di("Luca", 5, DETTO)
r = chiama_ctx(ctx, "ricorda", ARGS)
sosp = r.get("in_sospeso") or {}
verifica("(b) ricorda con nascita: ricordo salvato, domanda «Lo salvo anche come tua data di "
         "nascita?», il profilo non cambia ancora",
         r.get("ok") and r.get("risposta_finale", "").endswith("data di nascita?")
         and sosp.get("tool") == "ricorda" and sosp.get("argomenti") == ARGS
         and luca.nascita is None and "nascita_proposta" in ctx.regole
         and any("1977" in f for f in MEM.facts(luca.id)), str(r))
r = chiama_ctx(ctx, "ricorda", ARGS)
verifica("(b) nella stessa risposta non si salva nel profilo", luca.nascita is None, str(r))
salv = SPEAKERS.salvataggi
ctx2 = ctx_di("Luca", 6, "Sì, grazie.", [("user", DETTO), ("assistant", r.get("conferma", ""))])
ctx2._nascite = ctx._nascite
r = chiama_ctx(ctx2, "ricorda", ARGS)
verifica("(b) il «sì» nella risposta dopo: data nel profilo, salvata, frase con gli anni",
         luca.nascita == "1977-07-04" and SPEAKERS.salvataggi == salv + 1
         and f"Hai {anni(n77)} anni" in r.get("risposta_finale", "")
         and "nascita_nel_profilo" in ctx2.regole, str(r))
r, _ = chiama("data_calcola", {"cosa": "eta", "persona": "io"}, chi="Luca")
verifica("(b) poi «Quanti anni ho?» con persona=io: dal profilo", r.get("ok")
         and r.get("anni") == anni(n77), str(r))
# (a2) la data di nascita in un ricordo di chi parla (il caso vero: il ricordo c'era già)
def con_ricordi(*fatti):
    global MEM
    MEM = Memory(str(Path(tempfile.mkdtemp()) / "m.db"))
    for f in fatti:
        MEM.remember("luca-id", f)


luca.nascita = None
con_ricordi("Il compleanno di Luca è il 4 luglio 1977.", "Luca ama il barbecue.")
ctx = ctx_di("Luca", 20, "Quanti anni ho?")
r = chiama_ctx(ctx, "data_calcola", {"cosa": "eta", "persona": "io"})
sosp = r.get("in_sospeso") or {}
verifica("(a2) nessuna nascita nel profilo, un suo ricordo col compleanno: anni contati da lì, "
         "e la domanda per salvarla nel profilo",
         r.get("ok") and r.get("anni") == anni(n77) and r.get("da_dire", "").endswith(
             "data di nascita?") and sosp.get("tool") == "ricorda"
         and "eta_dal_ricordo" in ctx.regole and luca.nascita is None, str(r))
ctx2 = ctx_di("Luca", 21, "Sì.", [("user", "Quanti anni ho?"), ("assistant", r["da_dire"])])
ctx2._nascite = ctx._nascite
r = chiama_ctx(ctx2, "ricorda", sosp.get("argomenti") or {})
verifica("(a2) il «sì»: la data del ricordo nel profilo (l'anno l'aveva detto lui, nel ricordo)",
         luca.nascita == "1977-07-04" and "nascita_nel_profilo" in ctx2.regole, str(r))
luca.nascita = None
for fatti, nome in ((("Il compleanno di Luca è il 4 luglio 1977.",
                      "Luca è nato il 5 luglio 1978."), "due date di nascita diverse"),
                    (("Luca si è sposato il 12 giugno 2005.",), "una data senza la nascita"),
                    ((), "nessun ricordo")):
    con_ricordi(*fatti)
    ctx = ctx_di("Luca", 30, "Quanti anni ho?")
    r = chiama_ctx(ctx, "data_calcola", {"cosa": "eta", "persona": "io"})
    verifica(f"(a2) contrario, {nome}: errore, nessuna età", r.get("ok") is False
             and "anni" not in r and "eta_dal_ricordo" not in ctx.regole, str(r))
con_ricordi("Il compleanno di Luca è il 4 luglio 1977.")
ctx = ctx_di("Marta", 31, "Quanti anni ha Luca?")
r = chiama_ctx(ctx, "data_calcola", {"cosa": "eta", "persona": "Luca"})
verifica("(a2) contrario: chi amministra chiede l'età di Luca → i ricordi di Luca restano suoi",
         r.get("ok") is False and "eta_dal_ricordo" not in ctx.regole, str(r))

luca.nascita = None
con_ricordi()
ctx = ctx_di("Luca", 9, "Ricordati del mio compleanno, è il 4 luglio.")
r = chiama_ctx(ctx, "ricorda", {"fatto": "Il compleanno di Luca è il 4 luglio.",
                                "nascita": "4 luglio 1977"})
verifica("(b) contrario: l'anno non l'ha detto → solo il ricordo, nessuna proposta",
         r.get("ok") and not r.get("in_sospeso") and "nascita_non_detta" in ctx.regole, str(r))
ctx = ctx_di("Bianca", 9, "Ricordati che sono nata il 3 marzo 2013.")
r = chiama_ctx(ctx, "ricorda", {"fatto": "Bianca è nata il 3 marzo 2013",
                                "nascita": "3 marzo 2013"})
verifica("(b) contrario: una minore non cambia la sua data di nascita (la cambia un tutore)",
         not r.get("in_sospeso") and SPEAKERS.get("Bianca").nascita == "2012-09-10"
         and "nascita_minore_tutore" in ctx.regole, str(r))
ctx = ctx_di("Luca", 9, "Ricordati che sono nato il 4 luglio 2015.")
r = chiama_ctx(ctx, "ricorda", {"fatto": "Luca è nato il 4 luglio 2015",
                                "nascita": "4 luglio 2015"})
verifica("(b) contrario: una data che renderebbe minorenne un profilo adulto non si propone",
         not r.get("in_sospeso") and "nascita_minore_tutore" in ctx.regole, str(r))
ctx = ctx_di("Luca", 9, "Ricordati che il wifi è Casa2024.")
r = chiama_ctx(ctx, "ricorda", {"fatto": "la password del wifi è Casa2024", "per_tutti": True,
                                "nascita": "4 luglio 1977"})
verifica("(b) contrario: con per_tutti la nascita non conta", not r.get("in_sospeso"), str(r))
verifica("(b) ricorda: «nascita» nello schema, solo per chi parla",
         "nascita" in reg.get("ricorda").parameters["properties"]
         and "mai per altre persone" in reg.get("ricorda").description)

# (c) la rete sulle dichiarazioni dopo soli tool falliti
from calliope import brain as BR  # noqa: E402
CASO = "Ho appena recuperato il dato che mi hai appena chiesto di ricordare: hai 49 anni."
verifica("(c) «Ho appena recuperato il dato…» dopo soli tool falliti: dichiarazione falsa",
         BR.is_claim(CASO, (), fallito=True))
verifica("(c) contrario: la stessa frase senza tool falliti non lo è (ricordo della "
         "conversazione)", not BR.is_claim(CASO, ()))
for f in ("Non ho calcolato niente.", "Ho trovato nei tuoi ricordi il 4 luglio 1977.",
          "Ho calcolato bene?"):
    verifica(f"(c) contrario anche dopo tool falliti: «{f}»", not BR.is_claim(f, (), True))

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
