"""
Prova a secco dei minori (05/10, calliope/minori.py, calliope/guardiano.py, rapporto
docs/ricerche/2026-10-05-minori.md): niente modelli, niente Ollama.

- fasce d'età dalla data di nascita (confini), date dette a voce, migrazione di «giovane»,
  profili in speakers.json con la versione (e sola lettura con una versione più nuova);
- preset per fascia e ritocchi per persona (SQLite), «compiti libero» solo dai 14 anni;
- permessi nel codice (ToolRegistry.call): internet, agenti con l'autorizzazione a tempo, PC,
  documenti, ufficio, estensioni, solo adulti; i casi contrari per gli adulti e gli ospiti;
- orari di pausa (anche a cavallo della mezzanotte), dato del turno (adulti: niente);
- voce incerta: il profilo più protetto, mai un adulto;
- ricordi sensibili di un minore, voci e risultati per adulti, casa per fascia;
- compiti: mai la soluzione, 5 tentativi, poi spiegazione e avviso vero ai tutori; calcola
  in modalità compiti; la scaletta per un tema;
- avvisi ai tutori: scheda personale, annuncio, riepilogo dei compiti;
- guardiano (finto): frasi buone, frase vietata fermata, pericolo sulla domanda con la
  protezione, guasto per un minore e per un ospite, storia corretta;
- guardiano che non tace (Q3, 06/10): rilevatore guasto, scaduto o spento, guardiano guasto
  sulla domanda, schede trattenute fino al giudizio per i minori, guasti in `stato --turni`;
- registrazione di un familiare: data di nascita chiesta, frase di sfida, dati del profilo;
- privacy: conversazioni visibili ai tutori sotto i 14 anni, estensioni e dati verso internet.
"""

import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np  # noqa: E402

from calliope import guardiano as G  # noqa: E402
from calliope import minori as M  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.speaker_id import SpeakerContext, UserProfile, name_key  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""))


OGGI = datetime.date.today()


def nato(anni: int, giorni: int = 10) -> str:
    """Una data di nascita per chi ha `anni` compiuti (compleanno `giorni` fa)."""
    d = OGGI - datetime.timedelta(days=giorni)
    try:
        return d.replace(year=d.year - anni).isoformat()
    except ValueError:                       # 29 febbraio
        return (d - datetime.timedelta(days=1)).replace(year=d.year - anni).isoformat()


# ─────────────────────────── fasce ───────────────────────────
print("── fasce d'età e date ──")
for anni, attesa in ((0, "piccoli"), (6, "piccoli"), (7, "bambini"), (10, "bambini"),
                     (11, "ragazzi"), (13, "ragazzi"), (14, "adolescenti"), (17, "adolescenti"),
                     (18, None), (45, None)):
    verifica(f"{anni} anni → {attesa}", M.fascia_per_eta(M.eta(nato(anni))) == attesa)
# Il giorno prima del compleanno non ha ancora l'età
domani = OGGI + datetime.timedelta(days=1)
try:
    vigilia = domani.replace(year=domani.year - 7).isoformat()
except ValueError:
    vigilia = (domani + datetime.timedelta(days=1)).replace(year=domani.year - 7).isoformat()
verifica("vigilia del settimo compleanno: ancora piccoli", M.fascia_per_eta(M.eta(vigilia)) == "piccoli")
for testo, attesa in (("2017-05-12", datetime.date(2017, 5, 12)),
                      ("12/5/2017", datetime.date(2017, 5, 12)),
                      ("il 12 maggio 2017", datetime.date(2017, 5, 12)),
                      ("primo di settembre del 2015", datetime.date(2015, 9, 1)),
                      ("è nata il 12 Dicembre 2019", datetime.date(2019, 12, 12)),
                      ("31 febbraio 2017", None), ("domani", None), ("2999-01-01", None),
                      ("", None)):
    verifica(f"data «{testo}»", M.leggi_data(testo) == attesa, str(M.leggi_data(testo)))


# ─────────────────────────── profili ───────────────────────────
print("── profili in speakers.json ──")
p = UserProfile("Bianca", nascita="2017-05-12", tutori=["dario-id"])
d = p.to_dict()
verifica("versione 2 nel profilo", d.get("versione") == 2)
q = UserProfile.from_dict(d, None)
verifica("nascita e tutori tornano", (q.nascita, q.tutori) == ("2017-05-12", ["dario-id"]))
vecchio = {"name": "Matteo", "giovane": True}
r = UserProfile.from_dict(vecchio, None)
verifica("migrazione: «giovane» senza data = ragazzi", (r.fascia, M.fascia(r)) == ("ragazzi", "ragazzi"))
verifica("giovane resta vero (Vikidia)", r.young is True)
verifica("contrario: un adulto non è giovane", UserProfile("Dario").young is False)
verifica("la data vince sulla fascia scritta",
         M.fascia(UserProfile("X", nascita=nato(15), fascia="ragazzi")) == "adolescenti")
verifica("maggiorenne con la data: nessuna fascia", M.fascia(UserProfile("Y", nascita=nato(19))) is None)

# Una versione più nuova: sola lettura (SpeakerRegistry._load), con un registro senza CAM++
from calliope import speaker_id as S  # noqa: E402

tmp = Path(tempfile.mkdtemp())
f = tmp / "speakers.json"
f.write_text(json.dumps([{"name": "Dario", "admin": True, "versione": 99}]), encoding="utf-8")


class _Emb:
    model_name = "campplus"


reg_s = S.SpeakerRegistry.__new__(S.SpeakerRegistry)
reg_s.cfg, reg_s.embedder, reg_s.users = Config(), _Emb(), {}
reg_s._lock = __import__("threading").Lock()
reg_s.illeggibile, reg_s._salvato, reg_s._da_salvare = None, 0.0, False
vecchio_path = S.SpeakerRegistry.PATH
S.SpeakerRegistry.PATH = f
try:
    reg_s._load()
    prima = f.read_text(encoding="utf-8")
    reg_s.save()
    verifica("profili di una versione più nuova: sola lettura",
             reg_s.illeggibile is not None and f.read_text(encoding="utf-8") == prima)
finally:
    S.SpeakerRegistry.PATH = vecchio_path


# ─────────────────────────── ambiente finto ───────────────────────────
class Reg:
    def __init__(self, profili):
        self.cfg = Config()
        self.users = {p.name: p for p in profili}

    def get(self, n):
        return self.users.get(n)

    def find(self, n):
        k = name_key(n)
        return next((x for x in self.users if name_key(x) == k), None)

    def save(self):
        pass

    def by_id(self, i):
        return next((u for u in self.users.values() if u.id == i), None)


def profilo(nome, anni=None, admin=False, tutori=None, gender="f", giorni=10):
    pr = UserProfile(nome, admin=admin, gender=gender,
                     nascita=nato(anni, giorni) if anni is not None else None,
                     tutori=list(tutori or []))
    pr.id = nome.lower() + "-id"
    return pr


DARIO = profilo("Dario", admin=True, gender="m")
ELENA = profilo("Elena")
BIANCA = profilo("Bianca", 9, tutori=["dario-id", "elena-id"])
PIETRO = profilo("Pietro", 5, tutori=["dario-id"], gender="m")
LUCA = profilo("Luca", 12, tutori=["elena-id"], gender="m")
SARA = profilo("Sara", 16, tutori=["dario-id"])
REG = Reg([DARIO, ELENA, BIANCA, PIETRO, LUCA, SARA])
cfg = Config()
cfg.memory_db = str(tmp / "memoria.db")


class HubFinto:
    def __init__(self):
        self.schede = []

    def invia(self, scheda, mittente, forza=False):
        self.schede.append((scheda, mittente))
        return {"schermi": ["studio"], "motivo": ""}

    def mittente(self, ctx):
        from calliope.schermi.hub import mittente_da
        return mittente_da(ctx)


HUB = HubFinto()
M.prepara(cfg, schermi=HUB, registry=REG, log=lambda *a: None)
TOOLS = build_registry(minori_tool=True)


def ctx_di(nome, how="voce"):
    sc = SpeakerContext(REG)
    sc.current_speaker = nome
    sc.identified_by = how if nome else None
    return ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None)


def chiama(nome_tool, args, chi, how="voce"):
    ctx = ctx_di(chi, how)
    level = ctx.speaker_ctx.current_level
    out = json.loads(TOOLS.call(nome_tool, args, ctx, level))
    return out, ctx


# ─────────────────────────── preset e ritocchi ───────────────────────────
print("── preset e ritocchi ──")
verifica("preset di Bianca: bambini, internet no", (M.preset(BIANCA)["fascia"],
                                                    M.preset(BIANCA)["internet"]) == ("bambini", "no"))
verifica("contrario: Dario non ha preset", M.preset(DARIO) is None)
regole = M.regole()
regole.imposta(SARA.id, "compiti", M.controlla_valore("compiti", "libero", "adolescenti"))
verifica("16 anni: compiti liberi se il tutore vuole", M.preset(SARA)["compiti"] == "libero")
try:
    M.controlla_valore("compiti", "libero", "ragazzi")
    verifica("12 anni: compiti liberi rifiutati", False)
except ValueError:
    verifica("12 anni: compiti liberi rifiutati", True)
regole.scrivi(LUCA.id, {"compiti": "libero"})          # scritto a mano nel database
verifica("anche scritto a mano, sotto i 14 resta guidato", M.preset(LUCA)["compiti"] == "guida")
regole.scrivi(LUCA.id, {})
for k, v, ok in (("internet", "rigoroso", True), ("internet", "sempre", False),
                 ("orari", "21-7:30", True), ("orari", "dopo cena", False),
                 ("casa", "luci tapparelle", True), ("pippo", "x", False)):
    try:
        M.controlla_valore(k, v)
        verifica(f"valore {k}={v}", ok)
    except ValueError:
        verifica(f"valore {k}={v} rifiutato", not ok)
verifica("orari normalizzati", M.controlla_valore("orari", "21-7:30") == ["21:00-07:30"])

# ─────────────────────────── permessi ───────────────────────────
print("── permessi nel codice ──")
out, ctx = chiama("calcola", {"espressione": "2+2"}, "Bianca")
verifica("Bianca: calcola va", out.get("risultato") == "4")
if TOOLS.get("web_cerca") is None:
    from calliope.tools.web import web_spec
    TOOLS.register(web_spec())
out, ctx = chiama("web_cerca", {"domanda": "meteo"}, "Bianca")
verifica("Bianca (9): niente internet, frase pronta", out.get("ok") is False and "internet" in
         out.get("risposta_finale", "") and "minore_internet" in ctx.regole, str(out))
out, ctx = chiama("web_cerca", {"domanda": "meteo"}, "Luca")
verifica("Luca (12): internet rigoroso permesso (il tool risponde da sé)",
         "minore_internet" not in ctx.regole)
out, ctx = chiama("web_cerca", {"domanda": "meteo"}, "Dario")
verifica("contrario: Dario cerca su internet", "minore_internet" not in ctx.regole)
verifica("safesearch: 2 per Luca, 1 per Sara e Dario",
         (M.safesearch(LUCA), M.safesearch(SARA), M.safesearch(DARIO)) == (2, 1, 1))

from calliope.tools.agenti import agenti_specs  # noqa: E402
for s in agenti_specs((), ()):
    TOOLS.register(s)
out, ctx = chiama("lavoro_affida", {"tipo": "documento", "compito": "relazione sui vulcani"},
                  "Bianca")
verifica("Bianca: niente agenti", "minore_agenti" in ctx.regole and "Dario" in out["risposta_finale"])
out, ctx = chiama("lavoro_affida", {"tipo": "documento", "compito": "relazione"}, "Luca")
verifica("Luca: agenti solo con l'autorizzazione", "minore_autorizzazione" in ctx.regole
         and "Elena" in out["risposta_finale"], out.get("risposta_finale"))
regole.autorizza(LUCA.id, "agenti", 30, "elena-id")
out, ctx = chiama("lavoro_affida", {"tipo": "documento", "compito": "relazione"}, "Luca")
verifica("Luca autorizzato da Elena: passa il controllo dei minori",
         "minore_autorizzazione" not in ctx.regole)
dati = regole.leggi(LUCA.id)
dati["autorizzazioni"]["agenti"]["fino"] = time.time() - 1
regole.scrivi(LUCA.id, dati)
out, ctx = chiama("lavoro_affida", {"tipo": "documento", "compito": "relazione"}, "Luca")
verifica("autorizzazione scaduta: di nuovo no", "minore_autorizzazione" in ctx.regole)

from prove.pc_finto import FakePC  # noqa: E402
from calliope.tools.pc import pc_specs  # noqa: E402
for s in pc_specs({"portatile": FakePC()}, False):
    TOOLS.register(s)
out, ctx = chiama("pc_volume", {"azione": "alza"}, "Luca")
verifica("Luca: niente PC", "minore_pc" in ctx.regole)
out, ctx = chiama("pc_volume", {"azione": "alza"}, "Sara")
verifica("Sara (16): il PC sì", "minore_pc" not in ctx.regole)
out, ctx = chiama("installa_proponi", {"azione": "voce_paola"}, "Sara")
verifica("Sara: installazioni no (solo adulti)", out.get("ok") is False)
out, ctx = chiama("est_meteo", {}, "Bianca")
verifica("tool sconosciuto: errore come sempre", "errore" in out)
from calliope.tools.spec import ToolSpec  # noqa: E402
TOOLS.register(ToolSpec(name="est_meteo", description="meteo", parameters={"type": "object",
                        "properties": {}}, func=lambda ctx: {"ok": True, "meteo": "sole"},
                        levels=frozenset({"ospite", "familiare", "amministra"})))
out, ctx = chiama("est_meteo", {}, "Bianca")
verifica("estensione non abilitata per Bianca", "minore_estensione" in ctx.regole)
regole.imposta(BIANCA.id, "estensioni", ["meteo"])
out, ctx = chiama("est_meteo", {}, "Bianca")
verifica("abilitata dal tutore: va", out.get("meteo") == "sole")
verifica("estensione_consentita: adulti sì", M.estensione_consentita(DARIO, "qualunque"))
verifica("dati verso internet: Bianca solo con l'estensione abilitata",
         (M.dati_verso_internet(BIANCA), M.dati_verso_internet(BIANCA, "meteo"),
          M.dati_verso_internet(DARIO)) == (False, True, True))
for nome_t in ("archivio_cerca", "modello_compila"):
    TOOLS.register(ToolSpec(name=nome_t, description="x", parameters={"type": "object",
                            "properties": {}}, func=lambda ctx: {"ok": True},
                            levels=frozenset({"familiare", "amministra"})))
    out, ctx = chiama(nome_t, {}, "Sara")
    verifica(f"{nome_t}: no per un minore", "minore_ufficio" in ctx.regole)
    out, ctx = chiama(nome_t, {}, "Elena")
    verifica(f"contrario: {nome_t} per Elena", out.get("ok") is True)

# ─────────────────────────── orari e dato del turno ───────────────────────────
print("── orari e dato del turno ──")
regole.imposta(BIANCA.id, "orari", ["21:00-07:30"])
verifica("Bianca alle 22: pausa", M.fuori_orario(BIANCA, datetime.datetime(2026, 10, 5, 22, 0)) == "21:00-07:30")
verifica("alle 6: pausa (dopo la mezzanotte)", M.fuori_orario(BIANCA, datetime.datetime(2026, 10, 5, 6, 0)) is not None)
verifica("alle 7:30: si parla", M.fuori_orario(BIANCA, datetime.datetime(2026, 10, 5, 7, 30)) is None)
verifica("contrario: Dario non ha orari", M.fuori_orario(DARIO, datetime.datetime(2026, 10, 5, 23, 0)) is None)
regole.imposta(BIANCA.id, "orari", None)
t = M.dato_turno(BIANCA)
verifica("dato del turno di Bianca: età, compiti guidati", "9 anni" in t and "compiti: guida" in t
         and "bambina" in t, t)
verifica("contrario: dato del turno di Dario vuoto", M.dato_turno(DARIO) == "")


# Brain: il dato del turno entra nei dati del turno, solo per i minori
class _BrainFinto:
    pass


from calliope.brain import Brain  # noqa: E402

b = Brain.__new__(Brain)
b.cfg, b.tool_ctx, b.last_rules = cfg, ctx_di("Bianca"), []
msg = b._turn_context()[0]["content"]
verifica("Brain: Bianca ha il preset nei dati del turno", "minorenne" in msg and "minore_preset"
         in b.last_rules, msg)
b.tool_ctx, b.last_rules = ctx_di("Dario"), []
verifica("contrario Brain: Dario niente preset", "minorenne" not in b._turn_context()[0]["content"])

# ─────────────────────────── voce incerta ───────────────────────────
print("── voce incerta: il profilo più protetto ──")
rng = np.random.default_rng(3)


def vettore():
    v = rng.normal(size=192).astype(np.float32)
    return v / np.linalg.norm(v)


for pr in REG.users.values():
    pr.voiceprint = vettore()


def mescola(a, b, peso):
    """Un embedding con similarità controllata verso a e b."""
    v = peso * a + (1 - peso) * b
    return (v / np.linalg.norm(v)).astype(np.float32)


thr = cfg.speaker_id_threshold
emb = mescola(BIANCA.voiceprint, DARIO.voiceprint, 0.5)
sv, sd = float(emb @ BIANCA.voiceprint), float(emb @ DARIO.voiceprint)
verifica("adulto e bambina quasi uguali: vale Bianca",
         M.piu_protetto(REG, emb, "Dario", "voce", sd, cfg) == "Bianca", f"{sv:.2f} {sd:.2f}")
emb = mescola(DARIO.voiceprint, BIANCA.voiceprint, 0.97)
verifica("contrario: Dario sicuro, Bianca lontana: resta Dario",
         M.piu_protetto(REG, emb, "Dario", "voce", float(emb @ DARIO.voiceprint), cfg) is None)
emb = mescola(BIANCA.voiceprint, vettore(), 0.55)
s = float(emb @ BIANCA.voiceprint)
atteso = "Bianca" if s >= thr - cfg.speaker_id_session_margin else None
verifica(f"voce non riconosciuta vicina a Bianca ({s:.2f}): vale Bianca se nella zona grigia",
         M.piu_protetto(REG, emb, None, None, s, cfg) == atteso)
emb = mescola(PIETRO.voiceprint, BIANCA.voiceprint, 0.5)
verifica("tra due bambini: il più piccolo (Pietro, 5 anni)",
         M.piu_protetto(REG, emb, None, None, 0.4, cfg) == "Pietro")
verifica("contrario: già un minore, niente cambio",
         M.piu_protetto(REG, emb, "Bianca", "voce", 0.6, cfg) is None)
emb = vettore()
verifica("contrario: voce lontana da tutti, resta ospite",
         M.piu_protetto(REG, emb, None, None, 0.1, cfg) is None)

# ─────────────────────────── ricordi, contenuti, casa ───────────────────────────
print("── ricordi, contenuti per adulti, casa ──")
for t, atteso in (("prende una pastiglia per l'asma", True), ("è allergica alle noci", True),
                  ("ha la dislessia", True), ("il suo colore preferito è il blu", False),
                  ("gioca a calcio il martedì", False), ("ha un gatto che si chiama Fuffi", False)):
    verifica(f"ricordo «{t}»: sensibile {atteso}", M.ricordo_sensibile(t) == atteso)
for t, atteso in (("Pornografia", True), ("Prostituzione", True), ("Sesto San Giovanni", False),
                  ("Riproduzione sessuata delle piante", False), ("Seconda guerra mondiale", False),
                  ("Film erotico", True)):
    verifica(f"voce «{t}»: per adulti {atteso}", M.contenuto_adulto(t) == atteso)
ctx = ctx_di("Bianca")
roba = [("Pornografia", "x"), ("Vulcano", "monte che erutta")]
verifica("Bianca: voci per adulti tolte", [r[0] for r in M.filtra_per_minore(ctx, roba, lambda r: r)]
         == ["Vulcano"] and "minore_contenuto_adulto" in ctx.regole)
verifica("contrario: per Dario tutte", len(M.filtra_per_minore(ctx_di("Dario"), roba, lambda r: r)) == 2)
from calliope.casa.base import Entita  # noqa: E402
luce_cam = Entita("light.cam", "Luce cameretta", "light", area="Cameretta")
luce_cuc = Entita("light.cuc", "Luce cucina", "light", area="Cucina")
tapp = Entita("cover.t", "Tapparella", "cover", classe="shutter", area="Cucina")
garage = Entita("cover.g", "Garage", "cover", classe="garage")
clima = Entita("climate.c", "Termostato", "climate")
regole.imposta(PIETRO.id, "stanza", "cameretta")
verifica("Pietro (5): luce della sua stanza sì, cucina no",
         (M.casa_consentita(PIETRO, luce_cam), M.casa_consentita(PIETRO, luce_cuc)) == (True, False))
verifica("Bianca (9): luci e tapparelle, non il garage",
         (M.casa_consentita(BIANCA, luce_cuc), M.casa_consentita(BIANCA, tapp),
          M.casa_consentita(BIANCA, garage)) == (True, True, False))
verifica("Luca (12): niente clima", (M.casa_consentita(LUCA, clima), M.casa_consentita(LUCA, tapp))
         == (False, True))
verifica("Sara (16) e Dario: tutto", M.casa_consentita(SARA, clima) and M.casa_consentita(DARIO, clima))

out, ctx = chiama("ricorda", {"fatto": "prende una pastiglia per l'asma"}, "Bianca")
verifica("ricorda di Bianca: niente dati sanitari", out.get("ok") is False and
         "ricordo_minore_sensibile" in ctx.regole)

# ─────────────────────────── compiti ───────────────────────────
print("── compiti ──")
M.compiti().chiudi(BIANCA.id)
out, ctx = chiama("compiti_aiuto", {"esercizio": "3/4 + 1/2", "espressione": "3/4+1/2"}, "Bianca")
verifica("esercizio registrato, niente soluzione", out.get("tentativi") == 0 and "1.25" not in
         json.dumps(out) and "1,25" not in json.dumps(out))
out, ctx = chiama("calcola", {"espressione": "3/4+1/2"}, "Bianca")
verifica("calcola nei compiti: niente risultato", out.get("modalita_compiti") is True and
         "1,25" not in json.dumps(out), str(out))
out, _ = chiama("calcola", {"espressione": "3/4+1/2"}, "Dario")
verifica("contrario: calcola per Dario dà il risultato", out.get("risultato") == "1,25")
out, _ = chiama("compiti_aiuto", {"esercizio": "3/4+1/2", "espressione": "3/4+1/2",
                                  "risposta": "5/4"}, "Bianca")
verifica("risposta giusta (5/4 = 1,25) riconosciuta", out.get("giusta") is True)
M.compiti().chiudi(BIANCA.id)
av = M.avvisi()
HUB.schede.clear()
for i in range(1, 6):
    out, ctx = chiama("compiti_aiuto", {"esercizio": "7 per 8", "espressione": "7*8",
                                        "risposta": str(50 + i)}, "Bianca")
    if i < 5:
        verifica(f"tentativo {i} sbagliato: niente soluzione", out.get("giusta") is False
                 and "soluzione" not in out and out.get("tentativi") == i)
verifica("al quinto: soluzione permessa, la frase dice che lo dirà ai tutori",
         out.get("soluzione_permessa") and out.get("soluzione") == "56"
         and "Dario" in out.get("da_dire_prima", "") and "compiti_soluzione" in ctx.regole, str(out))
verifica("e l'avviso c'è davvero, per Dario e per Elena",
         len(av.da_dire(DARIO.id, segna=False)) == 1 and len(av.da_dire(ELENA.id, segna=False)) == 1)
verifica("scheda personale ai tutori", sorted(m.persona for s, m in HUB.schede
                                                if s.get("visibilita") == "personale")
         == ["dario-id", "elena-id"])
frase = av.frase(av.da_dire(DARIO.id))
verifica("annuncio al tutore con l'argomento, senza parole del minore",
         "7 per 8" in frase and "Bianca" in frase, frase)
verifica("detto una volta sola", av.da_dire(DARIO.id) == [])
verifica("riepilogo dei compiti", "7 per 8" in av.riepilogo(BIANCA), av.riepilogo(BIANCA))
# Il modello passa la risposta come esercizio ed espressione (banco del 05/10 sulla DGX)
M.compiti().chiudi(BIANCA.id)
chiama("compiti_aiuto", {"esercizio": "tre quarti più un mezzo", "espressione": "3/4+1/2"}, "Bianca")
out, ctx = chiama("compiti_aiuto", {"espressione": "1", "risposta": "1", "giusta": True}, "Bianca")
verifica("risposta passata come espressione: è un tentativo sbagliato dell'esercizio aperto",
         out.get("giusta") is False and out.get("tentativi") == 1
         and "compiti_stesso_esercizio" in ctx.regole, str(out))
out, ctx = chiama("compiti_aiuto", {"esercizio": "2/3", "risposta": "2/3", "giusta": True}, "Bianca")
verifica("e il «giusta» del modello non vale contro il conto", out.get("giusta") is False
         and out.get("tentativi") == 2, str(out))
out, ctx = chiama("compiti_aiuto", {"esercizio": "7 per 3", "espressione": "7*3"}, "Bianca")
verifica("contrario: un esercizio nuovo vero si apre", out.get("tentativi") == 0
         and out.get("esercizio") == "7 per 3", str(out))
out, ctx = chiama("compiti_aiuto", {"esercizio": "x"}, "Dario")
verifica("contrario: compiti_aiuto per un adulto non fa niente", out.get("ok") is False)
verifica("tema: la nota per la scaletta", "scaletta" in M.nota_documento(ctx_di("Bianca")))
verifica("contrario: nessuna nota per Dario", M.nota_documento(ctx_di("Dario")) == "")

# ─────────────────────────── minore_gestisci ───────────────────────────
print("── minore_gestisci ──")
out, ctx = chiama("minore_gestisci", {"nome": "Bianca", "azione": "imposta",
                                      "valore": "internet=rigoroso"}, "Elena")
verifica("Elena (tutrice) cambia internet di Bianca", out.get("ok") and M.preset(BIANCA)["internet"]
         == "rigoroso", out.get("risposta_finale"))
out, ctx = chiama("minore_gestisci", {"nome": "Bianca", "azione": "imposta",
                                      "valore": "internet=no"}, "Sara")
verifica("Sara non è tutrice di Bianca: no", out.get("ok") is False and
         M.preset(BIANCA)["internet"] == "rigoroso")
out, ctx = chiama("minore_gestisci", {"nome": "Bianca", "azione": "imposta",
                                      "valore": "internet=no"}, "Bianca")
verifica("Bianca non cambia le sue regole", out.get("ok") is False)
# e2e del 06/10: «posso giocare mezz'ora in più?» andava a minore_gestisci (rifiuto): da un
# ragazzo per sé è la richiesta al tutore
out, ctx = chiama("minore_gestisci", {"nome": "Luca", "azione": "tempo_extra",
                                      "valore": "mezz'ora"}, "Luca")
_rq = M.richieste()
verifica("Luca chiede tempo in più con minore_gestisci: la richiesta ad Elena",
         "L'ho chiesto a Elena" in out.get("risposta_finale", "")
         and "minore_gestisci_richiesta" in ctx.regole
         and any(x["tipo"] == "tempo_gioco" and x["minore"] == LUCA.id
                 for x in _rq.in_attesa_per(ELENA, REG))
         , out)
out, ctx = chiama("minore_gestisci", {"nome": "Bianca", "azione": "tempo_extra",
                                      "valore": "mezz'ora"}, "Luca")
verifica("contrario: per un altro ragazzo niente richiesta, il rifiuto di sempre",
         out.get("ok") is False and "minore_gestisci_richiesta" not in ctx.regole, out)
out, ctx = chiama("minore_gestisci", {"azione": "richieste"}, "Elena")
verifica("Elena sente la richiesta di Luca", "Luca" in out.get("risposta_finale", ""), out)

# «Intanto: Luca ti ha chiesto…» dopo la risposta al tutore (ciclo.richieste_al_tutore). e2e
# del 06/10, giro 5: detta due volte nello stesso turno dopo minore_gestisci(richieste), e
# attaccata a una risposta che finiva con una domanda («potresti spiegarmelo meglio?»)
from types import SimpleNamespace  # noqa: E402

from calliope.ciclo import Ciclo  # noqa: E402


class _BrainTutore:
    def __init__(self, tools=(), risposta="Sono le 8:24."):
        self.conv = SimpleNamespace()
        self.last_tools = list(tools)
        self.history = [{"role": "user", "content": "…"},
                        {"role": "assistant", "content": risposta}]
        self.annunci = []

    def has_pending(self):
        return False

    def ultima_domanda(self):
        from calliope.brain import Brain
        return Brain.ultima_domanda(self)

    def record_announcement(self, testo, pending=None, fonte=None):
        self.annunci.append(testo)


class _VoceTutore:
    def __init__(self):
        self.dette = []

    def start_turn(self):
        pass

    def say(self, t):
        self.dette.append(t)

    def wait(self):
        pass


def _al_tutore(brain):
    c = Ciclo.__new__(Ciclo)
    c.s = SimpleNamespace(registry=REG)
    c.brain, c.speaker, c.rec = brain, _VoceTutore(), {}
    c.richieste_al_tutore(ELENA)
    return c.speaker.dette, c.rec.get("regole", [])


_elenco = {"nome": "minore_gestisci", "argomenti": {"azione": "richieste"}, "ok": True}
dette, reg_t = _al_tutore(_BrainTutore([_elenco]))
verifica("richieste appena elencate dal tool: niente «Intanto…» nello stesso turno",
         (dette, reg_t) == ([], []), dette)
dette, reg_t = _al_tutore(_BrainTutore(risposta="Non ho capito: potresti spiegarmelo meglio?"))
verifica("dopo una risposta che chiede qualcosa: la richiesta aspetta",
         (dette, reg_t) == ([], []), dette)
_b = _BrainTutore()
dette, reg_t = _al_tutore(_b)
verifica("contrario: dopo una risposta senza domanda la richiesta si dice, una volta",
         len(dette) == 1 and "Luca" in dette[0] and reg_t == ["richiesta_al_tutore"]
         and _al_tutore(_b)[0] == [], dette)
dette, _ = _al_tutore(_BrainTutore([{**_elenco, "argomenti": {"azione": "stato"}}]))
verifica("contrario: un altro minore_gestisci non conta come elenco", len(dette) == 1, dette)
for _r in _rq.in_attesa_per(ELENA, REG):
    _rq.decidi(_r["id"], False, ELENA, REG)
out, ctx = chiama("minore_gestisci", {"azione": "stato"}, "Bianca")
verifica("Bianca sente le sue regole", out.get("ok") and "Bianca" in out["risposta_finale"])
out, ctx = chiama("minore_gestisci", {"nome": "Bianca", "azione": "orari",
                                      "valore": "21:00-07:00"}, "Elena", how="breve")
verifica("frase breve di una tutrice: non cambia", out.get("ok") is False and
         not M.preset(BIANCA)["orari"])
out, ctx = chiama("minore_gestisci", {"nome": "Bianca", "azione": "orari",
                                      "valore": "21:00-07:00"}, "Elena")
verifica("orari messi da Elena", M.preset(BIANCA)["orari"] == ["21:00-07:00"], out.get("risposta_finale"))
out, _ = chiama("minore_gestisci", {"nome": "Luca", "azione": "autorizza", "valore": "agenti 60"},
                "Elena")
verifica("autorizzazione a tempo", regole.autorizzato(LUCA.id, "agenti"))
regole.imposta(BIANCA.id, "internet", None)
regole.imposta(BIANCA.id, "orari", None)

# ─────────────────────────── guardiano (finto) ───────────────────────────
print("── guardiano ──")


class GuardianoFinto(G.Guardiano):
    def __init__(self, esiti, guasto=False, rilevatore="ok", ritardo=0.0):
        self.cfg = cfg
        self.timeout_s = 1.0
        self.esiti = esiti
        self.guasto = guasto
        self.rilevatore = rilevatore         # "ok", "guasto", "spento", "lento"
        self.ritardo = ritardo               # secondi del giudizio sulla domanda
        import concurrent.futures
        self._pool = concurrent.futures.ThreadPoolExecutor(3)

    def condivide_voce(self):
        return False

    def pericolo(self, domanda):
        if self.rilevatore == "guasto":
            return G.Giudizio(G.GUASTO, ms=3.0, grezzo="ConnectError")
        if self.rilevatore == "spento":
            return G.Giudizio(G.GUASTO, grezzo="spento")
        if self.rilevatore == "lento":
            time.sleep(self.timeout_s + 1.0)
        e = self.esiti.get("P:" + domanda, G.OK)
        return G.Giudizio(e, ("pericolo",) if e == G.PERICOLO else (), 7.0)

    def giudica(self, domanda, risposta=None, categorie_attive=None):
        if self.guasto:
            return G.Giudizio(G.GUASTO)
        if risposta is None and self.ritardo:
            time.sleep(self.ritardo)
        chiave = risposta if risposta is not None else ("D:" + domanda)
        e = self.esiti.get(chiave, G.OK)
        return G.Giudizio(e, ("autolesionismo",) if e == G.PERICOLO else
                          (("sessuale",) if e == G.VIETATO else ()), 5.0)


def gen(frasi, chiuso):
    try:
        for f_ in frasi:
            yield f_
    finally:
        chiuso.append(True)


def filtra(esiti, frasi, minore=True, domanda="d", guasto=False, rilevatore="ok"):
    e = G.Esito()
    chiuso = []
    out = list(G.filtra(GuardianoFinto(esiti, guasto, rilevatore), gen(frasi, chiuso), domanda,
                        minore, e))
    return out, e, chiuso


out, e, _ = filtra({}, ["Uno.", "Due."])
verifica("frasi buone: passano tutte", out == ["Uno.", "Due."] and e.fermata is None)
out, e, chiuso = filtra({"Due.": G.VIETATO}, ["Uno.", "Due.", "Tre."])
verifica("frase vietata: fermata, resto non detto, frase sostituta",
         out == ["Uno.", G.SOSTITUTA] and e.fermata == G.VIETATO and chiuso)
out, e, _ = filtra({"D:voglio morire": G.PERICOLO}, ["Ti capisco."], domanda="voglio morire")
verifica("pericolo sulla domanda: la protezione con il 19696", out == [G.PROTEZIONE] and
         "19696" in out[0] and e.fermata == G.PERICOLO)
out, e, _ = filtra({"D:x": G.PERICOLO}, [], domanda="x")
verifica("pericolo anche senza frasi del modello", out == [G.PROTEZIONE])
out, e, _ = filtra({"P:lo zio mi picchia": G.PERICOLO}, ["Ti capisco."],
                   domanda="lo zio mi picchia")
verifica("pericolo dal solo rilevatore (il guardiano dice ok): protezione", out == [G.PROTEZIONE]
         and e.categorie == ("pericolo",), str(out))
out, e, _ = filtra({}, ["Uno."], guasto=True)
verifica("guardiano guasto per un minore: non si dice", out == [G.GUASTO_FRASE])
out, e, _ = filtra({}, ["Uno."], minore=False, guasto=True)
verifica("guardiano guasto per un ospite: passa", out == ["Uno."])
out, e, _ = filtra({"D:d": G.PERICOLO}, ["Uno."], minore=False)
verifica("ospite in pericolo: la protezione per ospiti", out == [G.PROTEZIONE_OSPITE])

# Q3 dell'analisi del 06/10: il guardiano non tace. Un rilevatore di pericolo guasto o scaduto
# (o il guardiano guasto sulla sola domanda) per un minore vale «guasto», non «sicura»
out, e, _ = filtra({}, ["Uno."], rilevatore="guasto")
verifica("rilevatore guasto per un minore: la frase di guasto, non la risposta",
         out == [G.GUASTO_FRASE] and e.fermata == G.GUASTO and e.domanda.pericolo == G.GUASTO
         and e.domanda.pericolo_ms == 3.0, str(out))
out, e, _ = filtra({}, ["Uno."], rilevatore="lento")
verifica("rilevatore scaduto per un minore: la frase di guasto",
         out == [G.GUASTO_FRASE] and e.domanda.pericolo == G.GUASTO, str(out))
out, e, _ = filtra({"D:d": G.GUASTO}, ["Uno."])
verifica("guardiano guasto sulla sola domanda per un minore: la frase di guasto",
         out == [G.GUASTO_FRASE] and e.fermata == G.GUASTO, str(out))
out, e, _ = filtra({}, [], rilevatore="guasto")
verifica("rilevatore guasto senza frasi del modello: la frase di guasto", out == [G.GUASTO_FRASE])
out, e, _ = filtra({}, ["Uno."], rilevatore="spento")
verifica("contrario: rilevatore spento per configurazione → risposta, nessun esito",
         out == ["Uno."] and e.domanda.pericolo == "" and e.domanda.pericolo_ms is None
         and not e.domanda.guasto())
out, e, _ = filtra({}, ["Uno."], minore=False, rilevatore="guasto")
verifica("contrario: rilevatore guasto per un ospite → passa (con l'esito per il registro)",
         out == ["Uno."] and e.domanda.pericolo == G.GUASTO)
out, e, _ = filtra({}, ["Uno."])
verifica("contrario: tutto ok → risposta, esito e tempo del rilevatore",
         out == ["Uno."] and e.domanda.pericolo == G.OK and e.domanda.pericolo_ms == 7.0)
_c = cfg.guardiano_se_guasto
cfg.guardiano_se_guasto = "passa"
out, e, _ = filtra({}, ["Uno."], rilevatore="guasto")
verifica("contrario: guardiano_se_guasto «passa» → la risposta", out == ["Uno."])
cfg.guardiano_se_guasto = _c

# Le schede della prima passata aspettano il giudizio sulla domanda (Brain.trattieni_schede)
from calliope.brain import Brain  # noqa: E402

eventi = []


class HubEventi(HubFinto):
    def invia(self, scheda, mittente, forza=False):
        eventi.append(("scheda", scheda["tipo"], time.perf_counter()))
        return super().invia(scheda, mittente, forza)


def risposta_con_scheda(esiti, ritardo, minore=True, trattieni=True, rilevatore="ok"):
    """Un tool manda la sua scheda (biblioteca) prima della prima frase, come in _run_tool."""
    del eventi[:]
    b = Brain.__new__(Brain)
    b.tool_ctx = ctx_di("Bianca")
    b.tool_ctx.schermi = HubEventi()
    b.last_rules = []
    b.trattieni_schede = [] if trattieni else None
    t_scheda = []

    def frasi():
        t_scheda.append(time.perf_counter())
        b._send_cards([{"tipo": "biblioteca", "visibilita": "pubblica"}], "biblioteca_cerca")
        yield "Il Po è lungo 652 chilometri."
    e = G.Esito()
    out = list(G.filtra(GuardianoFinto(esiti, ritardo=ritardo, rilevatore=rilevatore), frasi(),
                        "d", minore, e, al_giudizio=b.rilascia_schede if trattieni else None))
    attesa = (eventi[0][2] - t_scheda[0]) if eventi else None
    return out, b, attesa


out, b, attesa = risposta_con_scheda({}, 0.2)
verifica("minore, domanda ok: la scheda parte dopo il giudizio (non prima)",
         [x[1] for x in eventi] == ["biblioteca"] and attesa is not None and attesa >= 0.15
         and b.trattieni_schede is None and b.schede_attesa_ms >= 150, f"{eventi} {attesa}")
if attesa is not None:
    print(f"   costo per i minori: scheda partita {attesa * 1000:.0f} ms dopo (giudizio finto "
          f"da 200 ms in parallelo con la risposta)")
out, b, _ = risposta_con_scheda({"D:d": G.PERICOLO}, 0.05)
verifica("minore in pericolo: la scheda non parte mai", not eventi and out == [G.PROTEZIONE]
         and "schede_trattenute_scartate" in b.last_rules, str(eventi))
out, b, _ = risposta_con_scheda({}, 0.05, rilevatore="guasto")
verifica("minore con il rilevatore guasto: la scheda non parte", not eventi
         and out == [G.GUASTO_FRASE], str(eventi))
out, b, attesa = risposta_con_scheda({}, 0.2, minore=False, trattieni=False)
verifica("contrario: senza trattenere (ospiti, adulti) la scheda parte subito",
         [x[1] for x in eventi] == ["biblioteca"] and attesa is not None and attesa < 0.05,
         f"{attesa}")
_src = (Path(__file__).resolve().parent.parent / "calliope" / "ciclo.py").read_text("utf-8")
verifica("ciclo: le schede si trattengono solo per i minori, fino al giudizio",
         "trattieni = t.usa_guardia and t.minore_turno" in _src
         and "al_giudizio=brain.rilascia_schede if trattieni else None" in _src)

# Nel registro e in `calliope stato --turni`: i giudizi mancati si contano
from calliope import latenza  # noqa: E402

_turni = [{"inizio": "2026-10-06T10:00:00", "prima_frase_s": 1.0,
           "guardiano": {"domanda": "ok", "pericolo": "guasto", "pericolo_ms": 3500.0,
                         "guasto": True, "fermata": "guasto"}},
          {"inizio": "2026-10-06T10:01:00", "prima_frase_s": 1.0,
           "guardiano": {"domanda": "ok", "pericolo": "ok", "pericolo_ms": 200.0}}]
_g = latenza.giorno(_turni)
verifica("stato --turni: guasti contati", _g["guardiano"]["guasti"] == 1, str(_g["guardiano"]))
verifica("stato --turni: l'avviso sui guasti anche con poche risposte",
         "in 1 turni" in latenza.testo(latenza.per_giorno(_turni))
         and latenza.avviso_guasti(_g) is not None)
verifica("contrario: nessun guasto, nessun avviso",
         latenza.avviso_guasti(latenza.giorno(_turni[1:])) is None)


class BrainStoria:
    history = [{"role": "user", "content": "domanda"},
               {"role": "assistant", "content": "Uno. Due vietata. Tre."}]


bs = BrainStoria()
G.correggi_storia(bs, ["Uno.", G.SOSTITUTA])
verifica("storia: solo ciò che è stato detto", bs.history[-1]["content"] == "Uno. " + G.SOSTITUTA
         and len(bs.history) == 2)
# Adattatori: lettura delle uscite
lg = G.LlamaGuard()
verifica("Llama Guard: «unsafe S1» = autolesionismo", lg.leggi("unsafe\nS1") == (True, ("autolesionismo",)))
verifica("Llama Guard: safe", lg.leggi("safe") == (False, ()))
qg = G.QwenGuard()
verifica("Qwen3Guard: categorie", qg.leggi("Safety: Unsafe\nCategories: Suicide & Self-Harm")
         == (True, ("autolesionismo",)))
verifica("Qwen3Guard: controverso = vietato per i minori", qg.leggi("Safety: Controversial\n"
                                                                    "Categories: Violent")[0])
verifica("Qwen3Guard: safe", qg.leggi("Safety: Safe\nCategories: None") == (False, ()))
verifica("adattatore per nome", isinstance(G.adattatore_per("llama-guard3:8b"), G.LlamaGuard))

# ─────────────────────────── registrazione ───────────────────────────
print("── aggiungi un familiare ──")
cfg.conferma_sfida = True
out, ctx = chiama("registra_utente", {"nome": "Emma"}, "Dario")
verifica("senza data di nascita: la domanda", out.get("ok") is False and "nata" in
         out["risposta_finale"] and "registra_chiede_nascita" in ctx.regole)
out, ctx = chiama("registra_utente", {"nome": "Emma", "nascita": "12 maggio 2017"}, "Dario")
verifica("con la data: la frase di sfida anche con la voce sicura",
         "ripeti" in out.get("risposta_finale", "").lower() and "sfida_voce" in ctx.regole,
         out.get("risposta_finale"))
ctx = ctx_di("Dario")
ctx.speaker_ctx.sfida_superata = True
out = json.loads(TOOLS.call("registra_utente", {"nome": "Emma", "nascita": "2017-05-12",
                                                "tutori": "Dario e Elena"}, ctx, "amministra"))
sc = ctx.speaker_ctx
verifica("sfida superata: registrazione di un minore con nascita e tutori",
         out.get("ok") and out.get("minorenne") and sc.enrolling_name == "Emma"
         and sc._enroll_meta == {"nascita": "2017-05-12", "tutori": ["dario-id", "elena-id"]},
         str(out))
out, ctx = chiama("registra_utente", {"nome": "Emma", "nascita": "2017-05-12"}, "Elena")
verifica("Elena (familiare): non aggiunge nessuno", out.get("ok") is False)
out, ctx = chiama("registra_utente", {"nome": "Ugo", "maggiorenne": True,
                                      "tutori": "Nessuno"}, "Dario")
verifica("tutore sconosciuto: errore", "non è tra le persone registrate" in out.get("errore", ""))

# ─────────────────────────── privacy ───────────────────────────
print("── privacy ──")
verifica("conversazioni di Bianca (9) visibili ai tutori", M.conversazioni_visibili_ai_tutori(BIANCA))
verifica("di Sara (16) no, solo gli avvisi", not M.conversazioni_visibili_ai_tutori(SARA))
verifica("compie 14 anni oggi: no", not M.conversazioni_visibili_ai_tutori(
    profilo("T", 14, giorni=0)))
verifica("contrario: Dario no (non è minore)", not M.conversazioni_visibili_ai_tutori(DARIO))
verifica("tutore: Elena di Bianca sì, di Sara no", M.e_tutore(ELENA, BIANCA) and not M.e_tutore(ELENA, SARA))
_p = profilo("Z", 9)
_p.voiceprint = np.ones(4, dtype=np.float32)
_p.impronta_data = "2025-01-01"
verifica("impronta di più di 6 mesi da rifare (sotto i 14)",
         M.impronta_da_rifare(_p, cfg=cfg) is not None)
_p.impronta_data = OGGI.isoformat()
verifica("impronta fresca: niente", M.impronta_da_rifare(_p, cfg=cfg) is None)
_p.riconoscimento = 0.40
verifica("riconoscimento in calo: da rifare", M.impronta_da_rifare(_p, cfg=cfg) is not None)

print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
