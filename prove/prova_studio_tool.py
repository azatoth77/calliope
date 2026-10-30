import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""I tool dello Studio, i tocchi, la vista aperta e le due domande a secco (30/10, passo 4.5,
issue #284, epic #251, decisione 0035; calliope/tools/studio.py, schermi/tocchi.py,
studio/vista.py). Niente modello: le chiamate passano da `ToolRegistry.call` con un contesto finto.

1. **Tool, permessi e politica**: i due tool, le classi («azione» con le letture di sola lettura,
   «sicuro» con la fonte «foto»), gli effetti, i livelli; proprietario, tutore (anche con `per`),
   un altro adulto (lo stesso «non la trovo»), l'ospite e la zona grigia (`None`), il minore
   incerto che vale il minore; «archivia» che chiede senza le sue parole.
2. **La busta**: `studio` non dà mai il testo né i titoli; `studio_pagina_leggi` li dà nudi e
   Brain li mette nella busta «foto» (`racchiudi_risultato`), la pagina ostile resta dentro.
3. **I tocchi nuovi**: in `TOCCABILI` col perché, `studio_pagina_leggi` escluso, l'azione fissa,
   il bersaglio, il titolo in busta nella descrizione (e fuori dalle parole della persona), lo stato
   d'animo mai nella descrizione né negli argomenti, la verifica di un altro rifiutata.
4. **La vista aperta**: `valida`, `Viste` (scade), la riga dagli id senza titoli né testo, solo
   per chi parla dal suo schermo collegato; in ombra niente; nel turno, non nel prompt.
5. **Le due domande**: in memoria, mai su disco né nel registro, scadono, regolano la nota.
6. **Le note delle revisioni**: `piano_non_aggiornato`, la frase senza lettore, «dimentica» che
   dice lo Studio solo se l'ha tolto (attraverso il tool, con una verifica vera), la previsione
   solo dopo due misure.
7. **Un minore con `REGOLA_COMPITI`**: `studio_pagina_leggi` ricorda «mai la soluzione intera».
"""

import datetime
import json
import sqlite3
import tempfile
import types
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import politica, provenienza, valore  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi import tocchi as T  # noqa: E402
from calliope.studio import piano as P  # noqa: E402
from calliope.studio import vista as V  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                else ""))


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None, tutori=(), tipo=None):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, tipo
        self.level = "amministra" if admin else "familiare"


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


# Persone di fantasia: Andrea tutore di Leo (seconda media), Bruno adulto, Carla amministra
ANDREA = Prof("a1", "Andrea")
BRUNO = Prof("b1", "Bruno")
CARLA = Prof("c1", "Carla", admin=True)
LEO = Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
REG = Registro(ANDREA, BRUNO, CARLA, LEO)
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-tool-"))
ORA = [datetime.datetime(2026, 10, 29, 10, 0)]          # giovedì 29/10
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
righe_log: list = []


def cfg_nuova(nome, modo="attivo", **kw):
    c = Config()
    c.memory_db = str(TMP / nome)
    c.studio_modo = modo
    c.studio_cartella = str(TMP / "studio")
    c.turn_log_dir = str(TMP / "registro")
    c.studio_lettura = False
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def studio(cfg):
    st = S.Studio(cfg, registry=REG, log=righe_log.append, adesso=lambda: ORA[0])
    st.avvia_lettura(None, avvia=False)
    return st


def carica(st, chi, persona=None, conferma=True):
    vid = st.crea_verifica(chi, MAT["materia"], MAT["data_verifica"], livello=MAT["classe"],
                           argomento=MAT["argomento"], persona=persona)
    mid = st.aggiungi_materiale(chi, vid, "foto", "Libro")
    ids = {}
    for p in MAT["pagine"]:
        ids[p["id"]] = st.aggiungi_pagina(chi, mid, numero=p["numero"], stato="letta",
                                          testo=p["testo"], metodo="ocr",
                                          file=f"storia/{p['id']}.jpg")
    for a in MAT["argomenti"]:
        st.aggiungi_argomento(chi, vid, a["titolo"], [ids[x] for x in a["pagine"]])
    if conferma:
        st.conferma_argomenti(chi, vid)
    return vid, ids


def ctx_di(st, prof, come="voce", minore_incerto=None):
    sc = types.SimpleNamespace(current_speaker=prof.name if prof else None, identified_by=come,
                               minore_incerto=minore_incerto, current_level=(
                                   prof.level if prof else "ospite"),
                               profile_level=prof.level if prof else "ospite")
    ctx = ToolContext(cfg=st.cfg, speakers=REG, speaker_ctx=sc, speaker=None)
    ctx.studio = st
    return ctx


TOOLS = ToolRegistry()
for spec in TS.studio_specs():
    TOOLS.register(spec)


def chiama(ctx, nome, livello="familiare", **args) -> dict:
    return json.loads(TOOLS.call(nome, args, ctx, livello))


# ═══════════════════════════ 1. tool, permessi e politica ═══════════════════════════
print("— tool, permessi e politica")
cl, clp = politica.classe_di("studio"), politica.classe_di("studio_pagina_leggi")
verifica("studio: classe «azione», senza fonte; le letture di sola lettura (E0)",
         cl.classe == politica.AZIONE and politica.fonte_di("studio") is None
         and all(valore.effetto("studio", {"azione": a}) == valore.E0
                 for a in ("stato", "piano", "oggi")))
verifica("studio: gli effetti al più E2 (crea e archivia E2, il resto E1)",
         valore.effetto("studio", {"azione": "archivia"}) == valore.E2
         and valore.effetto("studio", {"azione": "fatto"}) == valore.E1
         and max(valore.effetto("studio", {"azione": a}) for a in TS.AZIONI) <= valore.E2)
verifica("studio_pagina_leggi: classe «sicuro» con la fonte «foto»",
         clp.classe == politica.SICURO and politica.fonte_di("studio_pagina_leggi") == "foto")
verifica("i due tool: familiari e chi amministra, mai gli ospiti",
         all(TOOLS.get(n).levels == frozenset({"familiare", "amministra"})
             for n in ("studio", "studio_pagina_leggi")))
verifica("«archivia» senza le sue parole chiede prima; con «archiviala» no",
         cl.chiedi_se("ok fallo", {"azione": "archivia"}, None) is not None
         and cl.chiedi_se("archiviala pure", {"azione": "archivia"}, None) is None
         and cl.chiedi_se("ok", {"azione": "fatto"}, None) is None)

st = studio(cfg_nuova("t1.db"))
vid, ids = carica(st, LEO)
r = chiama(ctx_di(st, LEO), "studio", azione="stato")
verifica("proprietario: «stato» della sua verifica (materia, data, pagine)",
         r["ok"] and r["verifica"] == vid and r["materia"] == "Storia"
         and r["pagine"]["lette"] == len(MAT["pagine"]), str(r)[:200])
verifica("«stato» non dà mai titoli né testo delle pagine (il risultato di un tool fidato)",
         not any(a["titolo"] in json.dumps(r, ensure_ascii=False) for a in MAT["argomenti"])
         and not any(p["testo"][:40] in json.dumps(r, ensure_ascii=False)
                     for p in MAT["pagine"]))
r = chiama(ctx_di(st, ANDREA), "studio", azione="stato", verifica=vid)
verifica("tutore: vede la verifica del suo minore", r["ok"] and r["verifica"] == vid)
r = chiama(ctx_di(st, BRUNO), "studio", azione="stato", verifica=vid)
r2 = chiama(ctx_di(st, BRUNO), "studio", azione="stato", verifica=9999)
verifica("un altro adulto: lo stesso «non la trovo» di una verifica che non c'è",
         not r["ok"] and r["conferma"] == r2["conferma"] == TS.NON_CE)
r = chiama(ctx_di(st, CARLA), "studio", azione="piano", verifica=vid, livello="amministra")
verifica("chi amministra non tutore: non vede quella di Leo", not r["ok"])
r = chiama(ctx_di(st, None), "studio", livello="ospite", azione="stato")
verifica("ospite: rifiutato dal livello del tool", not r["ok"])
r = chiama(ctx_di(st, LEO, come="conversazione"), "studio", azione="stato")
verifica("zona grigia da un dispositivo non suo: chi = None, nessun dato", not r["ok"]
         and r["conferma"] == TS.CHI_NO)
r = chiama(ctx_di(st, ANDREA, come="conversazione", minore_incerto="Leo"), "studio",
           azione="stato")
verifica("minore incerto: vale il minore (la sua verifica)", r["ok"] and r["verifica"] == vid)
r = chiama(ctx_di(st, ANDREA), "studio", azione="crea", materia="Matematica", data="lunedì",
           per="Leo")
v_mat = r.get("verifica")
verifica("tutore: crea per il minore con «per», la data dal nome del giorno (lunedì 2/11)",
         r["ok"] and st.verifica(LEO, v_mat)["data"] == "2026-11-02"
         and st.verifica(LEO, v_mat)["persona"] == "l1", str(r))
r = chiama(ctx_di(st, BRUNO), "studio", azione="crea", materia="Storia", data="2026-11-05",
           per="Leo")
verifica("un adulto non tutore non crea per il minore", not r["ok"])
r = chiama(ctx_di(st, LEO), "studio", azione="crea", materia="storia", data="2026-11-05")
verifica("la stessa verifica due volte: «ce l'hai già», niente doppione",
         r["ok"] and r["verifica"] == vid and "già" in r["conferma"])
r = chiama(ctx_di(st, LEO), "studio", azione="crea", materia="Storia", data="2026-10-01")
verifica("una data passata: chiede di nuovo", not r["ok"] and "passata" in r["conferma"])
r = chiama(ctx_di(st, LEO), "studio", azione="crea", materia="Storia")
verifica("senza data: «cosa_fare» chiede quando", not r["ok"] and "quando" in r["cosa_fare"])
r = chiama(ctx_di(st, LEO), "studio", azione="piano", verifica=vid)
verifica("piano: i giorni con l'attività, l'obiettivo, niente previsione senza misure",
         r["ok"] and r["giorni"] and r["obiettivo"] == "75%" and "previsione" not in r)
st.aggiungi_misura(LEO, vid, 40, "carte")
verifica("una misura sola: ancora niente previsione",
         "previsione" not in chiama(ctx_di(st, LEO), "studio", azione="piano", verifica=vid))
ORA[0] += datetime.timedelta(days=1)
st.aggiungi_misura(LEO, vid, 55, "carte")
r = chiama(ctx_di(st, LEO), "studio", azione="piano", verifica=vid)
verifica("due misure: la previsione compare (spunto del 28/10)", "previsione" in r, str(r)[:200])
ORA[0] -= datetime.timedelta(days=1)

# ═══════════════════════════ 2. la busta ═══════════════════════════
print("— la busta")
ostile = next(p for p in MAT["pagine"] if "ignora" in p["testo"].lower()
              or "SYSTEM" in p["testo"])
r = chiama(ctx_di(st, LEO), "studio_pagina_leggi", pagina=str(ostile["numero"]), verifica=vid)
busta = provenienza.racchiudi_risultato(politica.fonte_di("studio_pagina_leggi"),
                                        json.dumps(r, ensure_ascii=False))
dentro = json.loads(busta)
verifica("la pagina: il testo nudo nel risultato, Brain lo mette nella busta «foto»",
         r["ok"] and r["testo"] == ostile["testo"]
         and "DATO NON FIDATO (fonte: foto)" in dentro["dato_non_fidato"]["avviso"]
         and dentro["dato_non_fidato"]["contenuto"]["testo"] == ostile["testo"]
         and "testo" not in dentro and "cosa_fare" in dentro)
verifica("la busta «foto» porta l'avviso degli annunci (verifica annullata…)",
         provenienza.ANNUNCI in dentro["dato_non_fidato"]["avviso"])
r = chiama(ctx_di(st, LEO), "studio_pagina_leggi", pagina="argomenti", verifica=vid)
verifica("i titoli degli argomenti solo da studio_pagina_leggi (fonte «foto»)",
         r["ok"] and {a["titolo"] for a in r["argomenti"]} >= {MAT["argomenti"][0]["titolo"]})
r = chiama(ctx_di(st, LEO), "studio_pagina_leggi", pagina="P99", verifica=vid)
verifica("una pagina che non c'è: l'elenco delle pagine nel «cosa_fare»",
         not r["ok"] and "P1" in r["cosa_fare"])
r = chiama(ctx_di(st, BRUNO), "studio_pagina_leggi", pagina="P1", verifica=vid)
verifica("il testo di Leo non a un altro adulto", not r["ok"])

# ═══════════════════════════ 7. REGOLA_COMPITI ═══════════════════════════
print("— un minore con i compiti guidati")
p1 = chiama(ctx_di(st, LEO), "studio_pagina_leggi", pagina="P1", verifica=vid)
pa = chiama(ctx_di(st, ANDREA), "studio_pagina_leggi", pagina="P1", verifica=vid)
verifica("al minore coi compiti guidati: «mai la soluzione intera» nel cosa_fare",
         TS.COMPITI_PAGINA in p1["cosa_fare"] and "soluzione intera" in TS.COMPITI_PAGINA)
verifica("al tutore adulto la regola non c'è", pa["ok"] and TS.COMPITI_PAGINA not in pa["cosa_fare"])
verifica("lo Studio non dà soluzioni: nessuna azione restituisce testo delle pagine",
         all(not any(p["testo"][:30] in json.dumps(chiama(ctx_di(st, LEO), "studio", azione=a,
                                                          verifica=vid), ensure_ascii=False)
                     for p in MAT["pagine"]) for a in ("stato", "piano", "oggi")))

# ═══════════════════════════ 5. le due domande ═══════════════════════════
print("— le due domande")
r = chiama(ctx_di(st, LEO), "studio", azione="oggi")
verifica("«cosa devo studiare oggi?»: la riga di oggi con le due domande, detta dal codice",
         r["ok"] and r["risposta_finale"].startswith("Oggi per storia")
         and "come ti senti oggi?" in r["risposta_finale"], r.get("risposta_finale"))
r = chiama(ctx_di(st, LEO), "studio", azione="sessione", verifica=vid, conoscenza=2,
           umore="stressato")
verifica("le risposte: lo stato d'animo non torna nel risultato (che resta nella storia)",
         r["ok"] and "stressato" not in json.dumps(r, ensure_ascii=False))
nota = st.nota_sessione("l1")
verifica("la nota del turno regola tono e difficoltà", "ne so poco" in nota
         and "parti dalle basi" in nota and "frasi brevi" in nota)
verifica("dopo la sessione «oggi» non ripete le domande",
         "come ti senti" not in chiama(ctx_di(st, LEO), "studio", azione="oggi")["conferma"])
db = sqlite3.connect(str(TMP / "t1.db"))
tutto = " ".join(str(x) for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                 for r_ in db.execute(f"SELECT * FROM {t[0]}") for x in r_)
db.close()
verifica("mai su disco né nel registro", "stressato" not in tutto
         and not any("stressato" in x for x in righe_log))
verifica("risposte non valide rifiutate",
         not chiama(ctx_di(st, LEO), "studio", azione="sessione", verifica=vid, conoscenza=9)["ok"])
ORA[0] += datetime.timedelta(hours=4)
verifica("scade dopo tre ore", st.sessione("l1") is None and st.nota_sessione("l1") == "")
ORA[0] -= datetime.timedelta(hours=4)
st_om = studio(cfg_nuova("om.db", modo="ombra"))
st_om._sessioni["l1"] = {"verifica": 1, "conoscenza": 1, "umore": "pronto",
                         "fino": ORA[0] + datetime.timedelta(hours=1)}
verifica("in ombra la nota non arriva al modello", st_om.nota_sessione("l1") == "")

# ═══════════════════════════ 3. i tocchi ═══════════════════════════
print("— i tocchi")
verifica("controlla(): nessun errore coi tocchi nuovi", T.controlla() == [], str(T.controlla()))
verifica("studio in TOCCABILI col perché; studio_pagina_leggi negli ESCLUSI",
         "studio" in T.TOCCABILI and len(T.TOCCABILI["studio"].perche) > 80
         and "studio_pagina_leggi" in T.ESCLUSI and T.ammesso("studio_pagina_leggi"))
fonti = types.SimpleNamespace(studio=st)
args_l = st.argomenti(LEO, vid)
tieni = T.prepara({"tocco": "studio_tieni", "verifica": vid, "argomento": args_l[2]["id"]},
                  fonti, LEO)
verifica("tieni: azione fissa, bersaglio con gli id, il titolo in busta col numero",
         tieni.get("tool") == "studio" and tieni["argomenti"]["azione"] == "tieni"
         and tieni["bersaglio"]["studio"]["argomento"] == args_l[2]["id"]
         and "argomento 3" in tieni["descrizione"]
         and "DATO NON FIDATO (fonte: foto)" in tieni["descrizione"]
         and args_l[2]["titolo"] in tieni["descrizione"], str(tieni)[:300])
verifica("il titolo nella descrizione non vale come parole della persona",
         args_l[2]["titolo"].split()[-1].lower() not in provenienza.testo_persona(
             [{"role": "user", "content": tieni["descrizione"]}]).lower())
verifica("tieni sulla verifica di Leo dallo schermo di Bruno: rifiutato",
         T.prepara({"tocco": "studio_tieni", "verifica": vid, "argomento": args_l[2]["id"]},
                   fonti, BRUNO).get("_stato") == 404)
sess = T.prepara({"tocco": "studio_sessione", "verifica": vid, "conoscenza": 3,
                  "umore": "poca energia"}, fonti, LEO)
verifica("le due domande col tocco: lo stato d'animo solo nel bersaglio",
         sess.get("tool") == "studio" and "poca energia" not in sess["descrizione"]
         and "poca energia" not in json.dumps(sess["argomenti"], ensure_ascii=False)
         and sess["bersaglio"]["studio"]["umore"] == "poca energia")
verifica("le due domande col tocco: valori fuori elenco rifiutati",
         T.prepara({"tocco": "studio_sessione", "verifica": vid, "umore": "felicissimo"},
                   fonti, LEO).get("_stato") == 400)
scritto = {"tocco": "studio_tieni", "tool": "studio",
           "argomenti": {"azione": "archivia", "verifica": vid},
           "bersaglio": tieni["bersaglio"]}
verifica("il ciclo rifiuta un tocco con un'azione diversa dalla sua",
         T.non_ammesso(scritto, TOOLS.get("studio")) is not None
         and T.non_ammesso({**scritto, "argomenti": tieni["argomenti"]},
                           TOOLS.get("studio")) is None)
verifica("senza bersaglio dello Studio: rifiutato (`senza_bersaglio`)",
         T.senza_bersaglio({"tocco": "studio_fatto", "bersaglio": None})
         and T.senza_bersaglio({"tocco": "studio_fatto", "bersaglio": {"studio": {}}})
         and not T.senza_bersaglio({"tocco": "studio_fatto",
                                    "bersaglio": {"studio": {"verifica": vid}}}))
# Il tocco eseguito dal tool: gli id dal bersaglio, mai dagli argomenti
ctx_t = ctx_di(st, LEO, come="schermo")
st.segna_argomento(LEO, args_l[2]["id"], False)
ctx_t.tocco_bersaglio = tieni["bersaglio"]
r = json.loads(TOOLS.call("studio", {"azione": "tieni", "verifica": vid, "id": args_l[0]["id"]},
                          ctx_t, "familiare"))
verifica("il tool usa l'argomento del bersaglio, non quello degli argomenti",
         r["ok"] and next(a for a in st.argomenti(LEO, vid)
                          if a["id"] == args_l[2]["id"])["stato"] == "tenuto")
r = json.loads(TOOLS.call("studio", {"azione": "archivia", "verifica": vid}, ctx_t,
                          "familiare"))
verifica("con un bersaglio solo le azioni dei tocchi", not r["ok"]
         and st.verifica(LEO, vid)["stato"] == "aperta")
ctx_t.tocco_bersaglio = sess["bersaglio"]
r = json.loads(TOOLS.call("studio", sess["argomenti"], ctx_t, "familiare"))
verifica("la sessione col tocco: le risposte dal bersaglio, in memoria",
         r["ok"] and st.sessione("l1")["umore"] == "poca energia")
ctx_t.tocco_bersaglio = None
fatto = T.prepara({"tocco": "studio_fatto", "verifica": vid}, fonti, LEO)
ctx_t.tocco_bersaglio = fatto["bersaglio"]
r = json.loads(TOOLS.call("studio", fatto["argomenti"], ctx_t, "familiare"))
oggi = ORA[0].date().isoformat()
verifica("fatto col tocco: il giorno di oggi segnato, poi il tocco non c'è più",
         r["ok"] and any(g["giorno"] == oggi and g["fatto"] for g in st.piano(LEO, vid)["giorni"])
         and T.prepara({"tocco": "studio_fatto", "verifica": vid}, fonti, LEO).get("_stato") == 409)
ctx_t.tocco_bersaglio = None
salta = T.prepara({"tocco": "studio_salta", "verifica": vid}, fonti, LEO)
verifica("salta: «non ce la faccio oggi» col bersaglio", salta.get("tool") == "studio"
         and salta["argomenti"]["azione"] == "salta_oggi")
# Una pagina da parte e «Riprova»
st.dati.scrivi("UPDATE studio_pagine SET stato = 'da_parte' WHERE id = ?", (ids[MAT["pagine"][1]["id"]],))
rip = T.prepara({"tocco": "studio_riprova", "verifica": vid,
                 "pagina": ids[MAT["pagine"][1]["id"]]}, fonti, LEO)
ctx_t.tocco_bersaglio = rip["bersaglio"]
r = json.loads(TOOLS.call("studio", rip["argomenti"], ctx_t, "familiare"))
verifica("riprova: la pagina da parte torna «da leggere»", r["ok"] and next(
    p for p in st.pagine(LEO, vid) if p["id"] == ids[MAT["pagine"][1]["id"]])["stato"]
    == "da_leggere")
ctx_t.tocco_bersaglio = None

# ═══════════════════════════ 4. la vista aperta ═══════════════════════════
print("— la vista aperta")
verifica("valida: tipi e id interi; il resto rifiutato",
         V.valida({"vista": "piano", "verifica": 3}) == {"vista": "piano", "verifica": 3}
         and V.valida({"vista": "x"}) is None and V.valida({"vista": "piano", "verifica": "3"})
         is None and V.valida({"vista": None}) == {"vista": None})
t_ = [100.0]
viste = V.Viste(orologio=lambda: t_[0])
viste.metti(7, {"vista": "piano", "verifica": vid})
t_[0] += V.VISTA_S + 1
verifica("Viste: scade dopo VISTA_S", viste.di(7) is None)
pag_id = ids[MAT["pagine"][2]["id"]]
riga = st.riga_vista(LEO, {"vista": "pagina", "verifica": vid, "pagina": pag_id})
verifica("la riga: verifica, materia, data e pagina dagli id, niente titoli né testo",
         f"verifica {vid}" in riga and "Storia" in riga and f"pagina {pag_id}" in riga
         and not any(a["titolo"] in riga for a in MAT["argomenti"])
         and not any(p["testo"][:20] in riga for p in MAT["pagine"]), riga)
verifica("la riga per una verifica di un altro: niente",
         st.riga_vista(BRUNO, {"vista": "piano", "verifica": vid}) == "")
verifica("in ombra: niente riga", st_om.riga_vista(LEO, {"vista": "home"}) == "")


class Hub:
    def __init__(self):
        self.viste_studio = V.Viste()
        self.persona, self.certo = "l1", True

    def mittente(self, ctx):
        return types.SimpleNamespace(persona=self.persona, certo=self.certo)

    def abbinati(self):
        return [{"id": 1, "proprietario": "l1"}, {"id": 2, "proprietario": "a1"}]

    def collegato(self, sid):
        return sid in (1, 2)


hub = Hub()
hub.viste_studio.metti(1, {"vista": "piano", "verifica": vid})
c = ctx_di(st, LEO)
c.schermi = hub
verifica("vista.riga: dallo schermo collegato di chi parla", f"verifica {vid}" in V.riga(c, st))
c2 = ctx_di(st, ANDREA)
c2.schermi = hub
hub.persona = "a1"
verifica("vista.riga: lo schermo di Leo non vale per Andrea", V.riga(c2, st) == "")
hub.persona, hub.certo = "l1", False
verifica("vista.riga: chi parla non certo (e non dal suo dispositivo): niente",
         V.riga(c, st) == "")
src = (QUI.parent / "calliope" / "brain.py").read_text("utf-8")
i_turno = src.index("def _turn_context") if "def _turn_context" in src else src.index(
    "TURN_CONTEXT_MSG.format(")
verifica("prefisso stabile: la riga è nei dati del turno (TURN_CONTEXT_MSG), non nel prompt",
         src.index("studio = self._nota_studio()") < src.index("TURN_CONTEXT_MSG.format(", src.index(
             "studio = self._nota_studio()"))
         and "_nota_studio" not in src[src.index("def _system_messages"):src.index(
             "def _system_messages") + 4000])

# ═══════════════════════════ 6. le note delle revisioni ═══════════════════════════
print("— le note delle revisioni")
st.ricalcola = lambda v: (_ for _ in ()).throw(RuntimeError("guasto"))
ORA[0] += datetime.timedelta(days=1)
pi = st.piano(LEO, vid)
verifica("piano_non_aggiornato: il ricalcolo fallito lo dice (e conta l'errore)",
         P.NON_AGGIORNATO in pi["avvisi"] and st.misure["errori"] >= 1)
r = chiama(ctx_di(st, LEO), "studio", azione="piano", verifica=vid)
verifica("piano_non_aggiornato: a voce la frase", TS.AVVISI_PIANO["piano_non_aggiornato"]
         in r["avvisi"])
ORA[0] -= datetime.timedelta(days=1)
del st.ricalcola
st.dati.scrivi("UPDATE studio_pagine SET stato = 'da_leggere' WHERE id = ?",
               (ids[MAT["pagine"][0]["id"]],))
lett = st.lettura(LEO, vid)
verifica("senza vLLM: la frase al posto di un «da leggere» muto",
         st.lettura_motivo == "spenta" and lett["frase"] == S.FRASI_LETTURA["spenta"])
st2 = studio(cfg_nuova("nv.db", studio_lettura=True))
v2, _ = carica(st2, LEO)
st2.dati.scrivi("UPDATE studio_pagine SET stato = 'da_leggere'")
verifica("senza modello dell'agente: «le leggo quando c'è il modello che vede»",
         st2.lettura_motivo == "senza_modello" and "modello che vede" in (
             st2.lettura(LEO, v2)["frase"] or ""))
r = chiama(ctx_di(st2, LEO), "studio_pagina_leggi", pagina="P1", verifica=v2)
verifica("la pagina non letta, senza modello: la stessa frase alla voce",
         not r["ok"] and "modello che vede" in r["conferma"])
st2.close()

# «dimentica» attraverso il tool, con una verifica vera
from calliope.tools import conversazioni as TC  # noqa: E402


class Arch:
    def __init__(self, gancio):
        self.gancio = gancio

    def dimentica(self, persona):
        self.gancio(persona)
        return 1


def dimentica_con(gancio, nome):
    cfg = cfg_nuova(nome)
    s_ = studio(cfg)
    carica(s_, LEO)
    s_.close()
    ctx = ctx_di(st, LEO)
    ctx.cfg = cfg
    ctx.conversazioni = Arch(lambda p: gancio(cfg, p))
    ctx.turno = 1
    TC._conversazioni_dimentica(ctx)
    ctx.turno = 2
    return TC._conversazioni_dimentica(ctx)


from calliope.studio.dati import cancella_file  # noqa: E402
ok_ = dimentica_con(lambda cfg, p: cancella_file(cfg.memory_db, persona=str(p),
                                                 archiviate=False,
                                                 cartella=cfg.studio_cartella), "dim1.db")
ko = dimentica_con(lambda cfg, p: None, "dim2.db")          # il gancio non toglie niente
verifica("«dimentica»: «ho tolto le verifiche dello Studio» solo se le ha tolte",
         TC.STUDIO_TOLTO in ok_["conferma"] and TC.STUDIO_NON_TOLTO not in ok_["conferma"]
         and TC.STUDIO_NON_TOLTO in ko["conferma"] and TC.STUDIO_TOLTO not in ko["conferma"],
         f"{ok_['conferma']} | {ko['conferma']}")
verifica("la cartella dei provvisori all'avvio: solo dopo 15 minuti",
         S.dati.PROVVISORI_AVVIO_S == 900.0)

# ═══════════════════════════ registro: il conto dei tool ═══════════════════════════
src_main = (QUI.parent / "calliope" / "main.py").read_text("utf-8")
verifica("main.py: i tool dello Studio solo con lo Studio per il modello",
         "if s.studio.per_modello():" in src_main and "studio_specs()" in src_main)
st.close()
st_om.close()
sys.exit(1 if errori else 0)
