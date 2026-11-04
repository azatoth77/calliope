"""
Il giro vero dello Studio del 03/11, a secco (04/11/2026, issue #383, epic #251, decisione 0035 punto
55), coi materiali di fantasia e il modello a copione:

1. **La risposta tagliata a `max_tokens`** (93,5 s e nessuna domanda): quante per argomento ci stanno
   nel tetto, lo schema col tetto, le voci intere tenute senza rifare la richiesta, ciò che è tagliato
   a metà fuori; si richiede solo senza una voce intera; il giro in tondo vero non passa i doppioni.
2. **Le lezioni scartate** (0 lezioni, 11 scartati): «A1: il titolo» è A1, lo schema coi soli codici; i
   contrari (un titolo, un codice che non c'è); il paragrafo al tetto finisce a una frase.
3. **Il giorno detto**: `cosa_fare` non fa chiedere il giorno già detto; `giorno` al posto di `data`;
   la data in un campo inventato di un nome inventato; contrari (due date, una che non è una data, un'
   azione senza data).
4. **L'interrogazione senza verifica**: con la materia niente frase pronta e la strada verso «crea»,
   anche con l'id inventato; il giro attraverso Brain; senza materia «non la trovo», uguale per
   tutti; la descrizione del tool.
5. **L'interrogazione senza domande**: dice ciò che può fare, le carte in ombra non contano e non si
   nominano, quelle proposte sì, «fai le carte» non si dice più.
6. **Il promemoria dello sviluppo**: in modalità studio taciuto e non consumato, la riga dello
   sviluppo anche; contrari: fuori dalla modalità c'è, e parlando dello sviluppo c'è.

    python prove/prova_studio_giro.py
"""
import contextlib
import io
import json
import os
import sys
import shutil
import tempfile
import types
import datetime
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))
sys.path.insert(0, str(QUI))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import prova_politica as PP  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.ciclo import Ciclo  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.studio import argomenti as A  # noqa: E402
from calliope.studio import domande_genera as DG  # noqa: E402
from calliope.studio import genera as G  # noqa: E402
from calliope.studio import lettura as L  # noqa: E402
from calliope.studio import preparazione as PR  # noqa: E402
from calliope.studio.modalita import Modalita  # noqa: E402
from calliope.tools import registry as R  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                else ""), flush=True)


class Prof:
    def __init__(self, pid, name, nascita=None, tutori=()):
        self.id, self.name, self.admin = pid, name, False
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, None
        self.level = "familiare"
        self.preferred_voice = self.preferred_tone = None


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)

    def known_speakers(self):
        return list(self.users)


ANDREA = Prof("a1", "Andrea")
LEO = Prof("l1", "Leo", nascita="2011-03-01", tutori=["a1"])
REG = Registro(ANDREA, LEO)
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-giro-"))
os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(TMP / "niente.yaml"))
registro: list = []
PAGINA = ("Le scoperte geografiche. Colombo partì da Palos nel 1492 con tre navi. Vasco da Gama "
          "arrivò in India nel 1498 doppiando il Capo di Buona Speranza. Magellano partì nel 1519.")
n_db = [0]


def nuovo(**kw):
    n_db[0] += 1
    c = Config()
    c.memory_db = str(TMP / f"g{n_db[0]}.db")
    c.studio_modo, c.studio_cartella = "attivo", str(TMP / "studio")
    c.turn_log_dir = str(TMP / "registro")
    c.studio_lettura = c.studio_argomenti = False
    c.studio_carte_genera = c.studio_mappa_genera = c.studio_domande_genera = "spenta"
    c.studio_preparazione = "spenta"
    for k, v in kw.items():
        setattr(c, k, v)
    st = S.Studio(c, registry=REG, log=registro.append)
    st.avvia_lettura(None, avvia=False)
    return st


def con_materiali(st, materia="Storia", argomenti=2):
    """Una verifica con una pagina letta e `argomenti` argomenti confermati."""
    domani = datetime.date.today() + datetime.timedelta(days=6)
    vid = st.crea_verifica(LEO, materia, domani)
    mid = st.aggiungi_materiale(LEO, vid, "foto", "Libro")
    pid = st.aggiungi_pagina(LEO, mid, numero="12", stato="letta", testo=PAGINA, metodo="ocr")
    for i in range(argomenti):
        st.aggiungi_argomento(LEO, vid, f"Il viaggio numero {i + 1}", [pid], proposto=False)
    if argomenti >= 2:
        st.conferma_argomenti(LEO, vid)
    return vid


def rif_arif(st, vid):
    pagine = st._pagine_di(vid)
    return A.riferimenti(pagine), G.argomenti_rif(st._argomenti_per_carte(vid))


def dom(a, i):
    return {"argomento": a, "tipo": "aperta", "domanda": f"Chi partì da Palos, viaggio {i}?",
            "risposta": "Colombo partì da Palos", "pagine": ["P1"]}


class Finto:
    """Le risposte del modello, in fila: (testo, fine)."""
    def __init__(self, *risposte):
        self.risposte, self.richieste = list(risposte), []

    def __call__(self, body):
        self.richieste.append(body)
        testo, fine = self.risposte.pop(0)
        return {"content": testo, "fine": fine, "prompt": 100, "eval": 50}


def lettore(st, *risposte):
    lt = L.Lettore(st, None, "qwen-finto", types.SimpleNamespace(motivo=lambda: None),
                   log=registro.append)
    lt._chiedi_corpo = Finto(*risposte)
    return lt


# ═══════════════════════════ 1. la risposta tagliata ═══════════════════════════
print("— 1. la risposta tagliata a max_tokens")
verifica("11 argomenti: la regola ci sta nel tetto (era «da 3 a 5 … al più 30»)",
         G.quante_per_argomento(11, 3, 5, 30) == "2 per argomento, al più 30 in tutto",
         G.quante_per_argomento(11, 3, 5, 30))
verifica("4 argomenti: da 3 a 5",
         G.quante_per_argomento(4, 3, 5, 30) == "da 3 a 5 per argomento, al più 30 in tutto")
verifica("7 argomenti: da 3 a 4",
         G.quante_per_argomento(7, 3, 5, 30).startswith("da 3 a 4"))
verifica("più argomenti del tetto: una per i più importanti",
         "una sola" in G.quante_per_argomento(40, 3, 5, 30))
verifica("le regole delle domande dicono il numero giusto, e il tetto sta anche nello schema",
         "2 per argomento" in DG.regole(11) and "{" not in DG.regole(11)
         and DG.SCHEMA["properties"]["domande"]["maxItems"] == DG.MAX_DOMANDE)
verifica("il budget ci sta per il tetto, a 150 token per domanda",
         DG.MAX_TOKENS >= DG.MAX_DOMANDE * 150, DG.MAX_TOKENS)
intere = [dom("A1", 1), dom("A2", 2)]
tagliata = json.dumps({"domande": intere}, ensure_ascii=False)
tagliata = tagliata[:-2] + ', {"argomento": "A1", "tipo": "aperta", "domanda": "Una tagliata a me'
verifica("le voci intere di un JSON tagliato, senza quella tagliata",
         G.oggetti_completi(tagliata, "domande") == intere,
         G.oggetti_completi(tagliata, "domande"))
for nome, t in (("niente", ""), ("un'altra chiave", '{"carte": [{"a": 1}]}'),
                ("tagliata nella prima voce", '{"domande": [{"argomento": "A1", "dom'),
                ("una voce che non è un oggetto", '{"domande": ["A1", {"a": 1}]}')):
    verifica(f"contrario, voci intere: {nome}", G.oggetti_completi(t, "domande") == [], t)

st = nuovo(studio_domande_genera="ombra")
vid = con_materiali(st)
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
pag, args = st._pagine_di(vid), st._argomenti_per_carte(vid)
vv = {**v, "_pagine": pag, "_argomenti": args, "_modo": "ombra"}
lt = lettore(st, (tagliata, "length"))
registro.clear()
verifica("tagliata: una richiesta sola, le domande intere tenute",
         lt.genera_domande(vv) == "proposte" and len(lt._chiedi_corpo.richieste) == 1
         and st.dati.uno("SELECT COUNT(*) n FROM studio_domande WHERE verifica = ? AND stato = "
                         "'ombra'", (vid,))["n"] == 2, registro)
verifica("il registro dice «tagliate», non «in tondo», e l'esito è «proposte»",
         any("tagliate a max_tokens, tengo le 2" in x for x in registro)
         and not any("illeggibili" in x or "in tondo" in x for x in registro)
         and st.dati.uno("SELECT domande_esito e FROM studio_verifiche WHERE id = ?",
                         (vid,))["e"] == DG.PROPOSTE, registro)
verifica("la misura delle tagliate", lt.misure["domande"].get("tagliate") == 1)
st.close()

st = nuovo(studio_domande_genera="ombra")
vid = con_materiali(st)
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
vv = {**v, "_pagine": st._pagine_di(vid), "_argomenti": st._argomenti_per_carte(vid), "_modo": "ombra"}
lt = lettore(st, ('{"domande": [{"argomento": "A1", "dom', "length"),
             ('{"domande": [{"argomento": "A1", "dom', "length"))
verifica("contrario: senza una voce intera si richiede, poi è «rotto» come prima",
         lt.genera_domande(vv) == "rotto" and len(lt._chiedi_corpo.richieste) == 2)
giro = json.dumps({"domande": [dom("A1", 1)] * 12}, ensure_ascii=False)[:-2]
lt = lettore(st, (giro, "length"))
vv["_firma"] = None
st.dati.scrivi("UPDATE studio_verifiche SET domande_firma = NULL WHERE id = ?", (vid,))
verifica("un giro in tondo vero: lo stesso controllo toglie i doppioni",
         lt.genera_domande(vv) == "proposte"
         and st.dati.uno("SELECT COUNT(*) n FROM studio_domande WHERE verifica = ?",
                         (vid,))["n"] == 1)
st.close()

# Le carte: lo stesso meccanismo
st = nuovo(studio_carte_genera="ombra")
vid = con_materiali(st)
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
vv = {**v, "_pagine": st._pagine_di(vid), "_argomenti": st._argomenti_per_carte(vid), "_modo": "ombra"}
carta = {"argomento": "A1", "domanda": "Chi partì da Palos?", "risposta": "Colombo", "pagine": ["P1"]}
t = json.dumps({"carte": [carta]}, ensure_ascii=False)[:-2] + ', {"argomento": "A2", "doma'
lt = lettore(st, (t, "length"))
verifica("le carte tagliate: una richiesta sola, la carta intera tenuta",
         lt.genera_carte(vv) == "proposte" and len(lt._chiedi_corpo.richieste) == 1
         and st.dati.uno("SELECT COUNT(*) n FROM studio_carte WHERE verifica = ?", (vid,))["n"] == 1)
st.close()

# ═══════════════════════════ 2. le lezioni scartate ═══════════════════════════
print("— 2. le lezioni scartate")
for scritto, atteso in (("A1", "A1"), ("A1: Il viaggio", "A1"), ("a3 - titolo", "A3"), ("A12", "A12"),
                        ("1", "A1"), (" A 2 ", "A2")):
    verifica(f"il codice in «{scritto}»", G._arg(scritto) == atteso, G._arg(scritto))
for scritto in ("Il viaggio", "Acqua", "A1B", "1492: la scoperta", "", None):
    verifica(f"contrario, nessun codice in «{scritto}»",
             G._arg(scritto) not in ("A1", "A2", "A3", "A12"), G._arg(scritto))
st = nuovo(studio_preparazione="ombra")
vid = con_materiali(st, argomenti=2)
rif, arif = rif_arif(st, vid)
frase = "Colombo partì da Palos nel 1492 con tre navi."
ris = PR.valida({"lezioni": [
    {"argomento": "A1: Il viaggio numero 1", "paragrafi": [{"testo": frase, "pagine": ["P1"]}]},
    {"argomento": "A2", "paragrafi": [{"testo": frase, "pagine": ["P1"]}]},
    {"argomento": "A9: Un altro", "paragrafi": [{"testo": frase, "pagine": ["P1"]}]},
    {"argomento": "Il viaggio numero 1", "paragrafi": [{"testo": frase, "pagine": ["P1"]}]}]},
    rif, arif)
verifica("il giro del 03/11: «A1: il titolo» vale A1; un codice che non c'è e un titolo si scartano",
         len(ris["lezioni"]) == 2 and ris["scartati"] == 2, ris)
for nome, sch, lista in (("preparazione", PR.schema(arif), "lezioni"),
                         ("domande", DG.schema(arif), "domande"),
                         ("carte", G.corpo("m", {"materia": "x", "data": "2026-11-20"}, rif, arif)["format"],
                          "carte")):
    verifica(f"lo schema di {nome}: i soli codici di questa richiesta",
             sch["properties"][lista]["items"]["properties"]["argomento"]["enum"] == ["A1", "A2"], sch)
verifica("…e lo schema di base non cambia",
         "enum" not in PR.SCHEMA["properties"]["lezioni"]["items"]["properties"]["argomento"])
t = "Colombo partì da Palos nel 1492. " + "Con tre navi attraversò il mare " * 30
ris = PR.valida({"lezioni": [{"argomento": "A1", "paragrafi": [{"testo": t, "pagine": ["P1"]}]}]},
                rif, arif)
par = ris["lezioni"][0]["paragrafi"][0]["testo"]
verifica("il paragrafo al tetto finisce all'ultima frase intera, mai a metà",
         par == "Colombo partì da Palos nel 1492.", par[:60])
ris = PR.valida({"lezioni": [{"argomento": "A1", "paragrafi": [{"testo": "parola " * 200,
                                                                 "pagine": ["P1"]}]}]}, rif, arif)
verifica("contrario: al tetto senza una frase finita si scarta",
         ris["lezioni"] == [] and ris["scartati"] == 1, ris)
corto = "Colombo partì da Palos nel 1492 con tre navi"
ris = PR.valida({"lezioni": [{"argomento": "A1", "paragrafi": [{"testo": corto, "pagine": ["P1"]}]}]},
                rif, arif)
verifica("contrario: un paragrafo sotto il tetto resta com'è, anche senza il punto",
         ris["lezioni"][0]["paragrafi"][0]["testo"] == corto)
risp = json.dumps({"lezioni": [{"argomento": "A1", "paragrafi": [{"testo": frase, "pagine": ["P1"]}]}]},
                  ensure_ascii=False)[:-2] + ', {"argomento": "A2", "paragrafi": [{"testo": "tagl'
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
pag, args = st._pagine_di(vid), st._argomenti_per_carte(vid)
vv = {**v, "_pagine": pag, "_argomenti": args, "_modo": "ombra",
      "_firma": PR.firma(args, pag, "ombra")}
lt = lettore(st, (risp, "length"))
verifica("la preparazione tagliata: la lezione intera tenuta, una richiesta sola",
         lt.prepara(vv) == "proposte" and len(lt._chiedi_corpo.richieste) == 1
         and st.dati.uno("SELECT COUNT(*) n FROM studio_preparazioni WHERE verifica = ?",
                         (vid,))["n"] == 1)
st.close()

# ═══════════════════════════ 3-5. i tool ═══════════════════════════
TOOLS = ToolRegistry()
for sp in TS.studio_specs():
    TOOLS.register(sp)


def ctx_di(st, prof):
    c = ToolContext(cfg=st.cfg, speakers=REG, speaker_ctx=types.SimpleNamespace(
        current_speaker=prof.name, identified_by="voce", current_level="familiare",
        profile_level="familiare", from_session=False, minore_incerto=None), speaker=None)
    c.studio = st
    return c


def chiama(st, nome, **args):
    with contextlib.redirect_stdout(io.StringIO()):
        return json.loads(TOOLS.call(nome, args, ctx_di(st, LEO), "familiare"))


print("— 3. il giorno detto")
st = nuovo()
o = chiama(st, "studio", azione="crea", materia="Biologia")
verifica("senza data: non fa chiedere il giorno già detto",
         o.get("errore") == "manca la data" and "già detto" in o["cosa_fare"]
         and "senza chiederglielo" in o["cosa_fare"] and "risposta_finale" not in o, o)
o = chiama(st, "studio", azione="crea", materia="Biologia", giorno="venerdì")
verifica("il giorno in `giorno`: vale come data", o.get("ok") and "venerdì" in o["conferma"], o)
st2 = nuovo()
o = chiama(st2, "studio", azione="crea", materia="Fisica", data="lunedì", tipo="interrogazione")
verifica("`tipo` al posto di `prova` con «crea»: vale, senza una passata in più",
         o.get("ok") and "interrogazione di fisica" in o["conferma"], o)
st2.close()
o = chiama(st, "studio", azione="sposta", materia="Biologia", giorno="lunedì")
verifica("anche per spostare", o.get("ok") and "lunedì" in str(o.get("conferma")), o)
o = chiama(st, "studio", azione="resoconto", materia="Biologia", giorno="ieri")
verifica("contrario: `giorno` del resoconto resta il suo", "data" not in o.get("cosa_fare", ""), o)
st.close()
verifica("nome inventato: la data in un campo inventato va in `data`",
         R.studio_dal_nome("studio_verifica", {"azione": "crea", "materia": "Biologia",
                                               "quando": "venerdì"})
         == ("studio", {"azione": "crea", "materia": "Biologia", "data": "venerdì"}))
verifica("…anche AAAA-MM-GG",
         R.studio_dal_nome("studio_verifica_crea", {"materia": "x", "il_giorno": "2026-11-20"})[1]
         ["data"] == "2026-11-20")
for nome, n, args, attesi in (
        ("la data detta c'è già", "studio_verifica",
         {"azione": "crea", "data": "lunedì", "quando": "venerdì"}, {"data": "lunedì"}),
        ("due date: non si sceglie", "studio_verifica",
         {"azione": "crea", "quando": "venerdì", "fine": "lunedì"}, {}),
        ("un campo che non è una data", "studio_verifica",
         {"azione": "crea", "nota": "porta il libro"}, {}),
        ("un'azione senza data", "studio_verifica",
         {"azione": "piano", "quando": "venerdì"}, {})):
    r = R.studio_dal_nome(n, args)[1]
    verifica(f"contrario, nome inventato: {nome}", r.get("data") == attesi.get("data"), r)

print("— 4. l'interrogazione senza verifica")
st = nuovo()
for nome, args in (("con la materia", {"materia": "Biologia"}),
                   ("con la materia e l'id inventato (il giro del 03/11)",
                    {"materia": "Biologia", "verifica": 1})):
    o = chiama(st, "studio_interroga", parte="inizia", **args)
    verifica(f"niente verifica, {nome}: niente frase pronta, la strada verso «crea»",
             not o["ok"] and "risposta_finale" not in o and "«crea»" in o["cosa_fare"]
             and "interrogazione" in o["cosa_fare"] and "Non dire che non la trovi" in o["cosa_fare"], o)
o = chiama(st, "studio_interroga", parte="inizia")
verifica("contrario: senza materia, la frase e la domanda su quando",
         "Dimmi quando è la prossima" in o.get("conferma", ""), o)
o = chiama(st, "studio_interroga", parte="inizia", verifica=99)
verifica("contrario: un id solo, lo stesso «non la trovo» di una verifica di un altro",
         o.get("conferma") == TS.NON_CE, o)
for nome_tool, args in (("studio_carte", {"parte": "prossima"}),
                        ("studio_ascolta", {"azione": "ascolta"})):
    o = chiama(st, nome_tool, materia="Biologia", **args)
    if o.get("errore", "").startswith("nessuna verifica"):
        verifica(f"{nome_tool}, lo stesso percorso", "«crea»" in o["cosa_fare"], o)
    else:
        verifica(f"{nome_tool}: risponde senza il vicolo cieco", o.get("conferma") != TS.NON_CE, o)
vid = st.crea_verifica(LEO, "Biologia", datetime.date.today() + datetime.timedelta(days=6))
o = chiama(st, "studio", azione="piano", materia="Biologia", verifica=vid + 7)
verifica("un id inventato con la materia: vale la materia, per ogni azione",
         o.get("verifica") == vid or "biologia" in str(o.get("conferma")).lower(), o)
o = chiama(st, "studio_interroga", parte="inizia", materia="Biologia", verifica=vid + 7)
verifica("…e per l'interrogazione: la verifica appena creata non è «chiusa», dice cosa manca",
         "prima servono le pagine" in o.get("conferma", ""), o)
st.close()
st = nuovo()
vid = con_materiali(st, "Biologia")
o = chiama(st, "studio_interroga", parte="inizia", materia="Biologia", verifica=vid + 7)
verifica("…con le pagine e gli argomenti: arriva alle domande che mancano",
         "almeno tre" in o.get("conferma", ""), o)
o = chiama(st, "studio_interroga", parte="inizia", materia="tutto")
verifica("una materia che non è una verifica: dice quali ci sono (giro col modello del 04/11)",
         "risposta_finale" not in o and "Le verifiche aperte sono di: Biologia" in o["cosa_fare"], o)
st.close()
verifica("la descrizione: annunciare un'interrogazione è «crea», non «inizia»",
         "venerdì ho l'interrogazione di storia" in TS.DESCRIZIONE_INTERROGA
         and "«crea» e prova «interrogazione»" in TS.DESCRIZIONE_INTERROGA)

st = nuovo()
reg = build_registry()
for sp in TS.studio_specs():
    reg.register(sp)
c_ = ctx_di(st, LEO)
for kk, vv_ in (("voce_sicura", "Leo"), ("punteggio", 0.7), ("conferma_breve", False), ("sfida", None),
                ("sfida_superata", False)):
    setattr(c_.speaker_ctx, kk, vv_)
b = Brain(st.cfg, reg, c_)
b.backend = PP.Copione()
b.backend.risposte = [PP.chiama("studio_interroga", {"parte": "inizia", "materia": "Biologia",
                                                     "verifica": 1}),
                      PP.chiama("studio", {"azione": "crea", "materia": "Biologia", "data": "venerdì",
                                           "prova": "interrogazione"}),
                      PP.testo("Non dovrebbe servire.")]
with contextlib.redirect_stdout(io.StringIO()):
    detto = "".join(b.stream_reply("Venerdì ho l'interrogazione su Biologia.", "familiare"))
righe = st.dati.tutti("SELECT materia, prova FROM studio_verifiche")
verifica("il giro attraverso Brain: l'interrogazione detta diventa la verifica, nello stesso turno",
         [(r["materia"], r["prova"]) for r in righe] == [("Biologia", "interrogazione")]
         and "non la trovo" not in detto.lower() and "venerdì" in detto, f"{righe} {detto}")
st.close()

print("— 5. l'interrogazione senza domande")
st = nuovo()
vid = con_materiali(st)
o = chiama(st, "studio_interroga", parte="inizia", verifica=vid)
f = o.get("conferma", "")
verifica("dice ciò che usa e cosa si può fare, senza «fai le carte»",
         not o["ok"] and "scritte o confermate" in f and "scriverle tu" in f
         and "fai le carte" not in f and "ripasso" in f, f)
o2 = chiama(st, "studio", azione="prove", verifica=vid)
verifica("anche il conto delle prove", "fai le carte" not in o2.get("conferma", "")
         and "scriverle" in o2.get("conferma", ""), o2)
agora = datetime.datetime.now().isoformat(timespec="seconds")
aid = st._argomenti_per_carte(vid)[0]["id"]


def carte(stato, quante, avvisi=None):
    for i in range(quante):
        st.dati.scrivi("INSERT INTO studio_carte (verifica, persona, argomento, domanda, risposta, "
                       "pagine, origine, stato, avvisi, creata) VALUES (?, ?, ?, ?, 'x', '[]', "
                       "'modello', ?, ?, ?)", (vid, "l1", aid, f"Q{stato}{i}{avvisi}", stato, avvisi,
                                               agora))


carte("ombra", 23)
f = chiama(st, "studio_interroga", parte="inizia", verifica=vid).get("conferma", "")
verifica("il giro del 03/11: le carte in ombra non contano e non si nominano",
         "da confermare" not in f and "23" not in f, f)
carte("proposta", 2, json.dumps(["da_controllare"]))
f = chiama(st, "studio_interroga", parte="inizia", verifica=vid).get("conferma", "")
verifica("contrario: quelle con un avviso non si contano", "da confermare" not in f, f)
carte("proposta", 4)
f = chiama(st, "studio_interroga", parte="inizia", verifica=vid).get("conferma", "")
verifica("quelle proposte sì, con dove confermarle", "ne ho 4 da confermare" in f and "Studio" in f, f)
st.close()
st = nuovo(studio_ascolta="spenta")
vid = con_materiali(st)
f = chiama(st, "studio_interroga", parte="inizia", verifica=vid).get("conferma", "")
verifica("contrario: col ripasso spento non lo offre", "ripasso" not in f and "scriverle" in f, f)
st.close()

# ═══════════════════════════ 6. il promemoria ═══════════════════════════
print("— 6. il promemoria dello sviluppo")


class Sviluppi:
    def __init__(self):
        self.ricordi, self.aperto, self.detta = 0, None, 0

    def promemoria_giorno(self, chi):
        return None if self.ricordi else "A proposito: lo sviluppo del gioco è sospeso."

    def ricordato(self, chi):
        self.ricordi += 1

    def corrente(self, chi):
        return self.aperto

    def riga_fuori_tema(self, sv):
        self.detta += 1
        return "Lo sviluppo del gioco resta aperto."

    def __getattr__(self, n):
        return lambda *a, **k: None


def brain_admin(svs, modalita):
    st_ = nuovo()
    reg_ = build_registry()
    for sp_ in TS.studio_specs():
        reg_.register(sp_)
    c = ctx_di(st_, ANDREA)
    c.speaker_ctx.current_level = c.speaker_ctx.profile_level = "amministra"
    for kk_, vv2 in (("voce_sicura", "Andrea"), ("punteggio", 0.7), ("conferma_breve", False),
                     ("sfida", None), ("sfida_superata", False)):
        setattr(c.speaker_ctx, kk_, vv2)
    c.speaker_ctx.in_modalita_studio = modalita
    c.lavori = types.SimpleNamespace(lavori=[], sviluppi=svs)
    b_ = Brain(st_.cfg, reg_, c)
    b_.backend = PP.Copione()
    return b_, st_


def di(b_, frase, *risposte):
    b_.backend.risposte = list(risposte)
    with contextlib.redirect_stdout(io.StringIO()):
        return "".join(b_.stream_reply(frase, "amministra"))


svs = Sviluppi()
b, st = brain_admin(svs, True)
d = di(b, "Lo faccio io.", PP.testo("Va bene, ti lascio studiare."))
verifica("in modalità studio: il promemoria non si dice e non si consuma",
         "sviluppo" not in d and svs.ricordi == 0 and "sviluppo_taciuto_studio" in b.last_rules, d)
b.tool_ctx.speaker_ctx.in_modalita_studio = False
d = di(b, "Ciao.", PP.testo("Ciao!"))
verifica("chiusa la modalità, il promemoria torna",
         "A proposito: lo sviluppo" in d and svs.ricordi == 1
         and "sviluppo_promemoria_giorno" in b.last_rules, d)
st.close()
svs = Sviluppi()
svs.ricordi = 1
svs.aperto = types.SimpleNamespace(titolo="Tris", di=lambda: "di Tris", fase="analisi")
b, st = brain_admin(svs, False)
d = di(b, "Com'è lo Studio?", PP.chiama("studio", {"azione": "premi"}), PP.testo("Bene."))
verifica("il turno con un tool dello Studio, a modalità ancora chiusa: niente riga dello sviluppo",
         "resta aperto" not in d and svs.detta == 0 and "sviluppo_taciuto_studio" in b.last_rules, d)
b.tool_ctx.speaker_ctx.in_modalita_studio = True
d = di(b, "Che ore sono?", PP.chiama("ora_attuale", {}), PP.testo("Sono le dieci."))
verifica("in modalità, un tool d'altro: niente riga dello sviluppo", "resta aperto" not in d, d)
b.tool_ctx.speaker_ctx.in_modalita_studio = False
d = di(b, "Che ore sono?", PP.chiama("ora_attuale", {}), PP.testo("Sono le dieci."))
verifica("contrario: fuori dalla modalità la riga c'è", "resta aperto" in d, d)
st.close()

mod = Modalita(types.SimpleNamespace(studio_modalita_inattivita_min=20.0))
sc = types.SimpleNamespace()
c = types.SimpleNamespace(speaker_ctx=sc, _modalita=lambda: (mod, 1, None))
Ciclo._modalita_turno(c)
verifica("il ciclo: modalità chiusa", sc.in_modalita_studio is False)
mod.apri(1, "a1")
Ciclo._modalita_turno(c)
verifica("il ciclo: modalità aperta su questo satellite", sc.in_modalita_studio is True)
c._modalita = lambda: (mod, 2, None)
Ciclo._modalita_turno(c)
verifica("contrario: su un altro satellite no", sc.in_modalita_studio is False)
c._modalita = lambda: None
Ciclo._modalita_turno(c)
verifica("contrario: senza satellite no", sc.in_modalita_studio is False)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
