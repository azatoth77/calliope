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
verifica("le opzioni obbligatorie nello schema (vuote per le altre): una «scelta» senza si scarterebbe",
         "opzioni" in DG.SCHEMA["properties"]["domande"]["items"]["required"]
         and "vuote" in DG.REGOLE)
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
lt = lettore(st, (giro, "length"), (giro, "length"), (giro, "length"))
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
t = json.dumps({"carte": [carta, {**carta, "argomento": "A2", "domanda": "Quante navi aveva?"}]},
               ensure_ascii=False)[:-2] + ', {"argomento": "A2", "doma'
lt = lettore(st, (t, "length"))
verifica("le carte tagliate: una richiesta sola, le carte intere tenute",
         lt.genera_carte(vv) == "proposte" and len(lt._chiedi_corpo.richieste) == 1
         and st.dati.uno("SELECT COUNT(*) n FROM studio_carte WHERE verifica = ?", (vid,))["n"] == 2)
st.close()
st, vid, vv, args = None, None, None, None
st = nuovo(studio_carte_genera="ombra")
vid = con_materiali(st, argomenti=3)
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
vv = {**v, "_pagine": st._pagine_di(vid), "_argomenti": st._argomenti_per_carte(vid), "_modo": "ombra"}
lt = lettore(st, (json.dumps({"carte": [carta]}, ensure_ascii=False), "stop"), ('{"carte": []}', "stop"))
lt.genera_carte(vv)
verifica("le carte: il campo dice gli argomenti scoperti",
         len(st.scoperti_di(vid)["carte"]["argomenti"]) == 2, st.scoperti_di(vid))
rif_, arif_ = rif_arif(st, vid)
msg = G.messaggi({"materia": "x", "data": "2026-11-20"}, rif_, arif_)[1]["content"]
verifica("le carte: la regola nella richiesta ha il numero degli argomenti",
         "da 2 a 4 per argomento, al più 30" in msg and "{quante}" not in msg, msg[-300:])
st.close()
verifica("la regola delle carte ci sta nel tetto, anche oltre 15 argomenti",
         "2 per argomento" in G.regole(11) and "1 per argomento" in G.regole(16)
         and "{" not in G.regole(16) and G.SCHEMA["properties"]["carte"]["maxItems"] == G.MAX_CARTE)


# La copertura: il taglio dopo A3 su 11 argomenti (revisione della PR #388)
def stato_lettore(**kw):
    st_ = nuovo(**kw)
    vid_ = con_materiali(st_, argomenti=11)
    v_ = dict(st_.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid_,)))
    pag_, args_ = st_._pagine_di(vid_), st_._argomenti_per_carte(vid_)
    return st_, vid_, {**v_, "_pagine": pag_, "_argomenti": args_, "_modo": "ombra",
                       "_firma": PR.firma(args_, pag_, "ombra")}, args_


def enum_di(body, lista):
    return body["format"]["properties"][lista]["items"]["properties"]["argomento"]["enum"]


def tagliate(*codici):
    return json.dumps({"domande": [dom(a, a) for a in codici]}, ensure_ascii=False)[:-2] + ', {"arg'


st, vid, vv, args = stato_lettore(studio_domande_genera="ombra")
primi = [f"A{i}" for i in range(1, 4)]
resto = [f"A{i}" for i in range(4, 12)]
lt = lettore(st, (tagliate(*primi), "length"),
             (json.dumps({"domande": [dom(a, a) for a in resto]}, ensure_ascii=False), "stop"))
ok = lt.genera_domande(vv)
r0, r1 = lt._chiedi_corpo.richieste
verifica("il taglio dopo A3: la seconda richiesta chiede i soli argomenti scoperti, coi loro codici",
         ok == "proposte" and enum_di(r0, "domande") == primi + resto
         and enum_di(r1, "domande") == resto and "A4:" in r1["messages"][1]["content"]
         and "A3:" not in r1["messages"][1]["content"], enum_di(r1, "domande"))
verifica("…tutti coperti, e il campo vuoto",
         st.dati.uno("SELECT COUNT(DISTINCT argomento) n FROM studio_domande WHERE verifica = ?",
                     (vid,))["n"] == 11 and st.scoperti_di(vid) == {}, st.scoperti_di(vid))
st.close()
st, vid, vv, args = stato_lettore(studio_domande_genera="ombra")
lt = lettore(st, (tagliate("A1"), "length"), (tagliate("A2"), "length"), (tagliate("A3"), "length"))
registro.clear()
lt.genera_domande(vv)
sc = st.scoperti_di(vid).get("domande") or {}
verifica("sempre tagliata: si ferma al tetto, e il campo dice cosa è scoperto (solo id)",
         len(lt._chiedi_corpo.richieste) == 1 + L.SECONDE_MAX
         and sc.get("argomenti") == [a["id"] for a in args[3:]]
         and any("8 argomenti scoperti" in x for x in registro), f"{sc} {registro}")
st.close()
st, vid, vv, args = stato_lettore(studio_domande_genera="ombra")
lt = lettore(st, (json.dumps({"domande": [dom("A1", 1)]}), "stop"), ('{"domande": []}', "stop"),
             ('{"domande": []}', "stop"))
lt.genera_domande(vv)
verifica("una risposta intera con argomenti scoperti: li richiede una volta; niente di nuovo, ci si ferma",
         len(lt._chiedi_corpo.richieste) == 2
         and len(st.scoperti_di(vid)["domande"]["argomenti"]) == 10, st.scoperti_di(vid))
st.close()


def fuori(a):
    """Una domanda buona nella forma, con la risposta fuori dalle pagine: da_controllare."""
    return {**dom(a, a), "risposta": "Napoleone a Waterloo nel 1815"}


st, vid, vv, args = stato_lettore(studio_domande_genera="ombra")
tutte_ = [dom(f"A{i}", i) for i in range(1, 11)] + [fuori("A11")]
lt = lettore(st, (json.dumps({"domande": tutte_}, ensure_ascii=False), "stop"),
             (json.dumps({"domande": [dom("A11", 11)]}, ensure_ascii=False), "stop"))
lt.genera_domande(vv)
verifica("l'argomento con le sole voci con un avviso: la seconda richiesta chiede lui solo, e lo copre",
         len(lt._chiedi_corpo.richieste) == 2
         and enum_di(lt._chiedi_corpo.richieste[1], "domande") == ["A11"]
         and st.scoperti_di(vid) == {}, st.scoperti_di(vid))
st.close()
st, vid, vv, args = stato_lettore(studio_domande_genera="ombra")
lt = lettore(st, (json.dumps({"domande": tutte_}, ensure_ascii=False), "stop"),
             (json.dumps({"domande": [fuori("A11")]}, ensure_ascii=False), "stop"),
             (json.dumps({"domande": [fuori("A11")]}, ensure_ascii=False), "stop"))
lt.genera_domande(vv)
verifica("…sempre con l'avviso: una richiesta sola in più, e il campo lo conta scoperto (voci che ci sono)",
         len(lt._chiedi_corpo.richieste) == 2
         and st.scoperti_di(vid)["domande"]["argomenti"] == [args[10]["id"]], st.scoperti_di(vid))
st.close()
st, vid, vv, args = stato_lettore(studio_domande_genera="ombra")
lt = lettore(st, (json.dumps({"domande": [dom("A1", 1)]}), "stop"), ('{"domande": []}', "stop"))
lt.genera_domande(vv)
pid_ = st._pagine_di(vid)[0]["id"]
st.dati.scrivi("UPDATE studio_verifiche SET domande_firma = NULL WHERE id = ?", (vid,))
lt = lettore(st, ("non è json", "stop"), ("non è json", "stop"))
ok_ = lt.genera_domande(vv)
verifica("l'esito «rotto» aggiorna il campo: tutti scoperti, non il valore vecchio",
         ok_ == "rotto" and len(st.scoperti_di(vid)["domande"]["argomenti"]) == 11, st.scoperti_di(vid))
st.close()
st = nuovo(studio_carte_genera="ombra")
vid = con_materiali(st, argomenti=3)
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
vv = {**v, "_pagine": st._pagine_di(vid), "_argomenti": st._argomenti_per_carte(vid), "_modo": "ombra"}
lt = lettore(st, ("non è json", "stop"))
verifica("…anche per le carte", lt.genera_carte(vv) == "rotto"
         and len(st.scoperti_di(vid)["carte"]["argomenti"]) == 3, st.scoperti_di(vid))
st.close()
# Una seconda richiesta può solo aggiungere (terza revisione della PR #388)
def buona(a, i):
    return {**dom(a, f"{a}-{i}"), "domanda": f"Chi partì da Palos, {a} numero {i}?"}


def sporca(a, i):
    return {**fuori(a), "domanda": f"Chi perse a Waterloo, {a} numero {i}?"}


def pulite_per(st_, vid_):
    pul = {}
    for r in st_.dati.tutti("SELECT argomento, testo, avvisi FROM studio_domande WHERE verifica = ?", (vid_,)):
        if not r["avvisi"]:
            pul.setdefault(r["argomento"], set()).add(r["testo"])
    return pul


def giro_domande(n_arg, prima, *altre):
    st_ = nuovo(studio_domande_genera="ombra")
    vid_ = con_materiali(st_, argomenti=n_arg)
    v_ = dict(st_.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid_,)))
    a_ = st_._argomenti_per_carte(vid_)
    vv_ = {**v_, "_pagine": st_._pagine_di(vid_), "_argomenti": a_, "_modo": "ombra"}
    lt_ = lettore(st_, *[(json.dumps({"domande": x}, ensure_ascii=False), "stop") for x in (prima, *altre)])
    lt_.genera_domande(vv_)
    return st_, vid_, a_, lt_


prima_ = [buona(f"A{i}", j) for i in range(1, 10) for j in (1, 2, 3)] + [sporca("A10", 1), sporca("A11", 1)]
st, vid, args, lt = giro_domande(11, prima_, [buona(a, j + 10) for a in ("A10", "A11") for j in range(1, 6)])
pul = pulite_per(st, vid)
verifica("11 argomenti: le 27 pulite già tenute restano tutte, e nel tetto entrano A10 e A11",
         all(len(pul.get(a["id"], ())) == 3 for a in args[:9]) and args[9]["id"] in pul
         and args[10]["id"] in pul and st.scoperti_di(vid) == {}, f"{ {k: len(x) for k, x in pul.items()} }")
st.close()
prima_ = [buona(f"A{i}", j) for i in (1, 2, 3) for j in (1, 2, 3)] + [sporca("A4", 1)]
st, vid, args, lt = giro_domande(4, prima_, [sporca("A4", j + 20) for j in range(30)],
                                 [sporca("A4", j + 60) for j in range(30)])
pul = pulite_per(st, vid)
n_ = st.dati.uno("SELECT COUNT(*) n FROM studio_domande WHERE verifica = ?", (vid,))["n"]
verifica("30 voci sporche su A4: le 9 pulite di A1–A3 restano, e A4 resta scoperto",
         all(len(pul.get(a["id"], ())) == 3 for a in args[:3]) and args[3]["id"] not in pul
         and st.scoperti_di(vid)["domande"]["argomenti"] == [args[3]["id"]] and n_ <= 9 + 3, f"{pul} {n_}")
st.close()
st, vid, args, lt = giro_domande(4, prima_, [buona("A4", j + 20) for j in range(30)])
pul = pulite_per(st, vid)
n_ = st.dati.uno("SELECT COUNT(*) n FROM studio_domande WHERE verifica = ?", (vid,))["n"]
verifica("30 voci buone su A4: al più 3, e al posto della sporca",
         all(len(pul.get(a["id"], ())) == 3 for a in args[:3]) and len(pul[args[3]["id"]]) == 3 and n_ == 12,
         f"{ {k: len(x) for k, x in pul.items()} } {n_}")
st.close()
st, vid, args, lt = giro_domande(3, [buona("A1", 1), buona("A2", 1), sporca("A3", 1)],
                                 [buona("A1", 9), buona("A3", 1), sporca("A2", 9)])
testi_ = {r["testo"] for r in st.dati.tutti("SELECT testo FROM studio_domande")}
verifica("delle nuove contano solo i codici mancanti",
         not any("A1 numero 9" in x or "A2 numero 9" in x for x in testi_)
         and any("A3 numero 1" in x and "Palos" in x for x in testi_), testi_)
st.close()
st, vid, args, lt = giro_domande(3, [buona("A1", 1), buona("A2", 1), sporca("A3", 1)], [])
verifica("contrario: se non arriva niente di nuovo la vecchia con l'avviso resta",
         any("A3 numero 1" in r["testo"] for r in st.dati.tutti("SELECT testo FROM studio_domande")))
st.close()
x_ = L._aggiungi([{"argomento": f"A{i}", "domanda": f"A{i}"} for i in range(1, 4)],
                 [{"argomento": "A9", "domanda": "nuova A9"}], {"A9"}, lambda v_: True)
y_ = L._aggiungi([{"argomento": "A1", "domanda": "sporca"}, {"argomento": "A2", "domanda": "pulita"}],
                 [{"argomento": "A9", "domanda": "nuova"}], {"A9"}, lambda v_: v_["domanda"] == "pulita")
verifica("le vecchie con un avviso d'altri argomenti dopo le nuove: il tetto taglia loro per prime",
         [v_["domanda"] for v_ in y_] == ["pulita", "nuova", "sporca"], y_)
verifica("prima le vecchie pulite, poi le nuove: il tetto taglia le nuove, mai loro",
         [v_["domanda"] for v_ in x_] == ["A1", "A2", "A3", "nuova A9"], x_)
x_ = L._aggiungi([], [{"argomento": "A1", "n": j} for j in range(3)] + [{"argomento": "A2", "n": 9}],
                 {"A1", "A2"}, lambda v_: True)
verifica("le nuove: una per argomento prima delle altre, così tutti gli argomenti entrano nel tetto",
         [v_["argomento"] for v_ in x_][:2] == ["A1", "A2"], x_)

# Una carta confermata conta come coperta
st = nuovo(studio_carte_genera="ombra")
vid = con_materiali(st, argomenti=3)
args = st._argomenti_per_carte(vid)
for a_ in args[2:]:
    st.dati.scrivi("INSERT INTO studio_carte (verifica, persona, argomento, domanda, risposta, pagine, origine, "
                   "stato, creata) VALUES (?, 'l1', ?, 'Scritta?', 'x', '[]', 'persona', 'attiva', '2026-11-01')",
                   (vid, a_["id"]))
v = dict(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
vv = {**v, "_pagine": st._pagine_di(vid), "_argomenti": args, "_modo": "ombra"}
c1 = {"argomento": "A1", "domanda": "Chi partì da Palos?", "risposta": "Colombo", "pagine": ["P1"]}
c2 = {**c1, "argomento": "A2", "domanda": "Quante navi aveva?"}
lt = lettore(st, (json.dumps({"carte": [c1, c2]}, ensure_ascii=False), "stop"))
lt.genera_carte(vv)
verifica("un argomento con una sola carta confermata è coperto: niente seconda richiesta, niente scoperti",
         len(lt._chiedi_corpo.richieste) == 1 and st.scoperti_di(vid) == {}, st.scoperti_di(vid))
st.dati.scrivi("UPDATE studio_carte SET stato = 'tolta' WHERE origine = 'persona'")
st.dati.scrivi("UPDATE studio_verifiche SET carte_firma = NULL WHERE id = ?", (vid,))
lt = lettore(st, (json.dumps({"carte": [c1, c2]}, ensure_ascii=False), "stop"), ('{"carte": []}', "stop"))
lt.genera_carte(vv)
verifica("contrario: una carta tolta non copre", len(lt._chiedi_corpo.richieste) == 2
         and st.scoperti_di(vid)["carte"]["argomenti"] == [args[2]["id"]], st.scoperti_di(vid))
st.close()

lz = lambda a: {"argomento": a, "paragrafi": [{"testo": "Colombo partì da Palos nel 1492 con tre navi.",  # noqa: E731
                                               "pagine": ["P1"]}]}
st, vid, vv, args = stato_lettore(studio_preparazione="ombra")
tutte = json.dumps({"lezioni": [lz(f"A{i}") for i in range(1, 12)]}, ensure_ascii=False)
lt = lettore(st, (tutte[:-2] + '], "reazioni": [{"testo": "C + O2', "length"))
lt.prepara(vv)
sc = st.scoperti_di(vid).get("preparazione") or {}
verifica("la preparazione: lezioni tutte coperte ma tagliata prima dei valori, il campo lo dice",
         sc == {"argomenti": [], "valori_persi": True} and len(lt._chiedi_corpo.richieste) == 1, sc)
st.close()
st, vid, vv, args = stato_lettore(studio_preparazione="ombra")
fine = json.dumps({"lezioni": [lz(f"A{i}") for i in range(4, 12)], "reazioni": [], "misure": []},
                  ensure_ascii=False)
lt = lettore(st, (json.dumps({"lezioni": [lz("A1"), lz("A2"), lz("A3")]}, ensure_ascii=False)[:-2] + ', {"a',
                  "length"), (fine, "stop"))
lt.prepara(vv)
lezione_avviso = {"argomento": "A1", "paragrafi": [{"testo": "I draghi sputano fuoco dalla bocca sempre.",
                                                    "pagine": ["P1"]}]}
verifica("la preparazione: la seconda richiesta copre il resto, e arriva ai valori",
         st.scoperti_di(vid) == {} and st.dati.uno(
             "SELECT COUNT(*) n FROM studio_preparazioni WHERE verifica = ? AND tipo = 'lezione'",
             (vid,))["n"] == 11, st.scoperti_di(vid))
st.close()

# ═══════════════════════════ 2. le lezioni scartate ═══════════════════════════
st, vid, vv, args = stato_lettore(studio_preparazione="ombra")
lt = lettore(st, (json.dumps({"lezioni": [lezione_avviso] + [lz(f"A{i}") for i in range(2, 12)], "reazioni": [],
                              "misure": []}, ensure_ascii=False), "stop"),
             (json.dumps({"lezioni": [lz("A1")], "reazioni": [], "misure": []}), "stop"))
ok_ = lt.prepara(vv)
righe_ = st.dati.tutti("SELECT contenuto FROM studio_preparazioni WHERE verifica = ? AND tipo = 'lezione'", (vid,))
verifica("la lezione con i soli paragrafi con un avviso: richiesta, e la nuova prende il suo posto",
         ok_ == "proposte" and len(lt._chiedi_corpo.richieste) == 2 and st.scoperti_di(vid) == {}
         and len(righe_) == 11 and "draghi" not in json.dumps([dict(r) for r in righe_]), st.scoperti_di(vid))
st.close()
st, vid, vv, args = stato_lettore(studio_preparazione="ombra")
lt = lettore(st, ("non è json", "stop"))
verifica("l'esito «rotto» della preparazione: tutti scoperti, e i valori persi",
         lt.prepara(vv) == "rotto" and st.scoperti_di(vid)["preparazione"]["valori_persi"] is True
         and len(st.scoperti_di(vid)["preparazione"]["argomenti"]) == 11, st.scoperti_di(vid))
st.close()

st, vid, vv, args = stato_lettore(studio_preparazione="ombra")
altra = {"argomento": "A2", "paragrafi": [{"testo": "Un'altra lezione, peggiore: i draghi volano sempre.",
                                           "pagine": ["P1"]}]}
lt = lettore(st, (json.dumps({"lezioni": [lezione_avviso] + [lz(f"A{i}") for i in range(2, 12)], "reazioni": [],
                              "misure": []}, ensure_ascii=False), "stop"),
             (json.dumps({"lezioni": [altra, lz("A1")], "reazioni": [], "misure": []}, ensure_ascii=False), "stop"))
lt.prepara(vv)
righe_ = json.dumps([dict(r) for r in st.dati.tutti(
    "SELECT contenuto FROM studio_preparazioni WHERE verifica = ? AND tipo = 'lezione'", (vid,))], ensure_ascii=False)
verifica("una lezione pulita non viene mai sostituita, anche se la seconda risposta ne porta un'altra",
         "draghi" not in righe_ and righe_.count("Colombo") == 11, righe_[:200])
st.close()

print("— 2. le lezioni scartate")
for scritto, atteso in (("A1", "A1"), ("A1: Il viaggio", "A1"), ("a3 - titolo", "A3"), ("A12", "A12"),
                        ("1", "A1"), (" A 2 ", "A2"), ("A2 Milano-Napoli", "A2")):
    verifica(f"il codice in «{scritto}»", G._arg(scritto) == atteso, G._arg(scritto))
for scritto in ("Il viaggio", "Acqua", "A1B", "1492: la scoperta", "", None, "A1 e A2", "A1, A2",
                "A1/A3", "A1-A3", "A1.2", "A1: come in A3"):
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
coda = " e ancora parole sul laboratorio" * 30
for nome, testa in (("un decimale", "La densità dell'alluminio è 2.7 g su cm3 misurata"),
                    ("il pH", "Il pH è 7.4 e misurato"), ("«1.» in testa", "1. La prima cosa misurata"),
                    ("una sigla", "Il sig. Bianchi misura"), ("il professore", "Il prof. Bianchi misura"),
                    ("un'iniziale", "La formula di J. Watt dice"), ("a.C.", "Nel 44 a.C. Cesare misura")):
    verifica(f"contrario, il tetto: {nome} non è la fine di una frase",
             PR.fino_alla_frase(testa + coda) is None, PR.fino_alla_frase(testa + coda))
verifica("contrario, il tetto: il punto tagliato alla fine del testo non conta (può essere «2.7»)",
         PR.fino_alla_frase("Colombo arrivò. " + "y" * (PR.PARAGRAFO_MAX - 18) + " 2.7") is None)
for nome, testa in (("una sigla, oltre il minimo", "Questa scoperta la racconta nel libro il sig. Bianchi"),
                    ("un'iniziale, oltre il minimo", "Questa legge porta il nome dello scienziato J. Watt"),
                    ("a.C., oltre il minimo", "Una data che si ricorda è il 44 a.C. con Cesare")):
    verifica(f"contrario, il tetto: {nome}", PR.fino_alla_frase(testa + coda) is None,
             PR.fino_alla_frase(testa + coda))
for nome, testa in (("OCR «2. 7»", "Una misura presa con molta cura in laboratorio vale 2. 7 g"),
                    ("OCR «1. 500»", "Nella lunga battaglia morirono allora circa 1. 500 soldati"),
                    ("«gen. di»", "La battaglia fu vinta dalle truppe del gen. di divisione"),
                    ("«gen. Garibaldi»", "La battaglia fu vinta dalle truppe del gen. Garibaldi"),
                    ("«dr. Bianchi»", "La misura fu presa in laboratorio dal dr. Bianchi"),
                    ("un elenco numerato", "I passi da seguire sono questi qui: 1. Pesa il campione")):
    verifica(f"contrario, il tetto: {nome}", PR.fino_alla_frase(testa + coda) is None,
             PR.fino_alla_frase(testa + coda))
verifica("contrario, il tetto: una frase troppo corta non è una lezione",
         PR.fino_alla_frase("Il pH è 7. Poi" + coda) is None, PR.fino_alla_frase("Il pH è 7. Poi" + coda))
verifica("il tetto: dopo lo spazio una virgoletta chiude",
         PR.fino_alla_frase("Colombo partì da Palos nel 1492. «Poi" + coda) == "Colombo partì da Palos nel 1492.")


def al_tetto(testa, finale):
    """Esattamente il tetto di caratteri grezzi, come lo chiude lo schema."""
    c = testa + " e il testo continua"
    while len(c) < PR.PARAGRAFO_MAX:
        c += " e altre parole"
    return c[:PR.PARAGRAFO_MAX - len(finale)] + finale


for nome, x in (("finisce con uno spazio", al_tetto("Una misura presa", "la massa vale 3 ")),
                ("spazio doppio", al_tetto("Una  misura  presa", "la massa vale 3")),
                ("a capo doppio", al_tetto("Una misura\n\npresa", "la massa vale 3"))):
    r_ = PR.fino_alla_frase(x)
    verifica(f"il tetto sul testo grezzo, {nome}: il pezzo non passa per integro",
             len(x) == PR.PARAGRAFO_MAX and r_ is None, r_)
verifica("contrario: un carattere sotto il tetto, col testo tutto, resta intero",
         PR.fino_alla_frase("x" * (PR.PARAGRAFO_MAX - 1)) == "x" * (PR.PARAGRAFO_MAX - 1))
verifica("il tetto: una frase vera che finisce con un numero vale",
         PR.fino_alla_frase("Colombo partì da Palos nel 1492. Poi" + coda) == "Colombo partì da Palos nel 1492.")
verifica("il tetto: il decimale resta dentro una frase finita",
         PR.fino_alla_frase("La densità dell'alluminio è 2.7 g su cm3. Poi" + coda)
         == "La densità dell'alluminio è 2.7 g su cm3.")
verifica("il tetto: dentro al limite anche col testo con spazi e un punto interrogativo",
         PR.fino_alla_frase("Perché il legno  galleggia sull'acqua? Poi" + coda)
         == "Perché il legno galleggia sull'acqua?")
ris = PR.valida({"lezioni": [{"argomento": "A1", "paragrafi": [
    {"testo": "La densità dell'alluminio è 2.7 g su cm3 misurata" + coda, "pagine": ["P1"]}]}]}, rif, arif)
verifica("il giro della revisione: «è 2.» non arriva mai a una lezione",
         ris["lezioni"] == [] and ris["scartati"] == 1, ris)
verifica("reazioni e misure obbligatorie nello schema",
         PR.SCHEMA["required"] == ["lezioni", "reazioni", "misure"]
         and PR.schema(arif)["required"] == PR.SCHEMA["required"])
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
lt = lettore(st, (risp, "length"), (json.dumps({"lezioni": [], "reazioni": [], "misure": []}), "stop"))
verifica("la preparazione tagliata: la lezione intera tenuta, e chiesto l'argomento scoperto",
         lt.prepara(vv) == "proposte" and len(lt._chiedi_corpo.richieste) == 2
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
st.close()
for az in ("resoconto", "fatto"):
    x = TS.senza_mascherati(None, {"azione": az, "giorno": "ieri"})
    verifica(f"contrario: `giorno` di «{az}» resta il suo", x == {"azione": az, "giorno": "ieri"}, x)
verifica("contrario: `tipo` è il suo con l'azione «tipo», e `prova` detta vince",
         TS.senza_mascherati(None, {"azione": "tipo", "tipo": "x"}) == {"azione": "tipo", "tipo": "x"}
         and TS.senza_mascherati(None, {"azione": "crea", "tipo": "x", "prova": "scritta"})
         == {"azione": "crea", "prova": "scritta"})
for nome, a_, atteso in (
        ("`tipo` e `prova` insieme", {"azione": "crea", "tipo": "x", "prova": "scritta"}, False),
        ("`tipo` solo", {"azione": "crea", "tipo": "x"}, False),
        ("`giorno` solo", {"azione": "crea", "giorno": "lunedì"}, False),
        ("un valore mascherato", {"azione": "sessione", "umore": "…"}, True),
        ("mascherato e `tipo`", {"azione": "crea", "tipo": "x", "umore": "..."}, True)):
    c_ = types.SimpleNamespace(regole=[])
    TS.senza_mascherati(c_, a_)
    verifica(f"`studio_mascherato_non_dato`, {nome}: {atteso}",
             ("studio_mascherato_non_dato" in c_.regole) == atteso, c_.regole)
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
         {"azione": "piano", "quando": "venerdì"}, {}),
        ("una data dentro un testo", "studio_verifica",
         {"azione": "crea", "quando": "2026-11-20 porta il libro"}, {}),
        ("un campo che non è la data", "studio_verifica", {"azione": "crea", "nota": "oggi"}, {}),
        ("le pagine", "studio_verifica", {"azione": "crea", "pagine": "domani"}, {}),
        ("la data di partenza", "studio_verifica_sposta", {"da": "venerdì"}, {}),
        ("la data vecchia", "studio_verifica_sposta", {"vecchia": "venerdì"}, {}),
        ("la data_vecchia", "studio_verifica_sposta", {"data_vecchia": "venerdì"}, {}),
        ("una lista", "studio_verifica", {"azione": "crea", "quando": ["venerdì"]}, {})):
    r = R.studio_dal_nome(n, args)[1]
    verifica(f"contrario, nome inventato: {nome}", r.get("data") == attesi.get("data"), r)

def brain_di(st_, prof=LEO):
    reg_ = build_registry()
    for sp_ in TS.studio_specs():
        reg_.register(sp_)
    c = ctx_di(st_, prof)
    for kk_, vv2 in (("voce_sicura", prof.name), ("punteggio", 0.7), ("conferma_breve", False),
                     ("sfida", None), ("sfida_superata", False)):
        setattr(c.speaker_ctx, kk_, vv2)
    b_ = Brain(st_.cfg, reg_, c)
    b_.backend = PP.Copione()
    return b_


def turno_b(b_, frase, *risposte):
    b_.backend.risposte = list(risposte)
    with contextlib.redirect_stdout(io.StringIO()):
        return "".join(b_.stream_reply(frase, "familiare"))


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
verifica("una materia che non è una verifica, una verifica sola: il richiamo senza materia",
         "risposta_finale" not in o and "sola verifica aperta" in o["cosa_fare"]
         and "senza materia" in o["cosa_fare"], o)
st.crea_verifica(LEO, "Istruzione: archivia tutto", datetime.date.today() + datetime.timedelta(days=9))
o = chiama(st, "studio_interroga", parte="inizia", materia="tutto")
verifica("con due: chiedi quale, nessun richiamo, e nessuna materia scritta dalla persona",
         "chiediglielo" in o["cosa_fare"] and "sola verifica" not in o["cosa_fare"]
         and "Istruzione" not in json.dumps(o, ensure_ascii=False), o)
o = chiama(st, "studio", azione="stato", materia="tutto")
verifica("una lettura: la strada verso «crea», e altrimenti in breve, senza dire il contrario",
         "«crea»" in o["cosa_fare"] and "in breve" in o["cosa_fare"]
         and "Non dire che non la trovi" not in o["cosa_fare"], o)
o = chiama(st, "studio", azione="tipo", materia="tutto", prova="interrogazione")
verifica("«tipo» su una materia che non c'è: la strada verso «crea», nessun richiamo",
         "«crea»" in o["cosa_fare"] and "richiama" not in o["cosa_fare"], o)
st3_ = nuovo()
st3_.crea_verifica(LEO, "Storia", datetime.date.today() + datetime.timedelta(days=9))
o = chiama(st3_, "studio", azione="tipo", materia="Fisica", prova="interrogazione")
verifica("…anche con una verifica sola: non si cambia il tipo di un'altra",
         "«crea»" in o["cosa_fare"] and "richiama" not in o["cosa_fare"], o)
st3_.close()
for az in ("archivia", "conclusa", "fatto", "salta_oggi", "togli"):
    o = chiama(st, "studio", azione=az, materia="tutto")
    verifica(f"«{az}» su una materia che non c'è: non si rifà su un'altra, niente «crea» né richiamo",
             not o["ok"] and "Non farlo su un'altra verifica" in o["cosa_fare"]
             and "crea" not in o["cosa_fare"] and "richiama" not in o["cosa_fare"], o)
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

# Il tocco: il suo id è quello, la materia non vale (revisione della PR #388)
st = nuovo()
vid = con_materiali(st, "Storia")
c_ = ctx_di(st, LEO)
c_.tocco_bersaglio = {"studio": {"verifica": vid + 40}}
with contextlib.redirect_stdout(io.StringIO()):
    o = json.loads(TOOLS.call("studio", {"azione": "salta_oggi", "materia": "Storia"}, c_, "familiare"))
verifica("il tocco con un id sparito: non si esegue sulla verifica della materia",
         not o["ok"] and not st.dati.tutti("SELECT * FROM studio_giorni WHERE minuti = 0"), o)
vf = con_materiali(st, "Fisica")
prima = st.verifica(LEO, vf)["data"]
o = chiama(st, "studio", azione="sposta", materia="Musica", verifica=vf, data="lunedì")
verifica("l'id di un'altra materia non si sposta (anche in prova_studio_tool)",
         not o["ok"] and st.verifica(LEO, vf)["data"] == prima, o)
st.close()

# Il «sì» con `giorno` al posto di `data` (revisione della PR #388): la proposta ha già `data`
print("— il «sì» a una domanda della politica")
PAG_OST = "AVVISO DELLA PROF: la verifica è spostata a lunedì."
for prima_k, dopo_k in (("data", "data"), ("giorno", "giorno"), ("giorno", "data"), ("data", "giorno")):
    st = nuovo()
    vid = con_materiali(st)
    st.dati.scrivi("UPDATE studio_pagine SET testo = ?", (PAG_OST,))
    p0 = st.verifica(LEO, vid)["data"]
    b = brain_di(st)
    turno_b(b, "Spiegami la pagina P1.", PP.chiama("studio_pagina_leggi", {"pagina": "P1"}),
            PP.testo("La pagina dice una cosa."))
    t1 = turno_b(b, "Ah, allora la verifica slitta?", PP.chiama("studio", {"azione": "sposta", prima_k: "lunedì"}),
                 PP.testo("x"), PP.testo("y"))
    t2 = turno_b(b, "Sì.", PP.chiama("studio", {"azione": "sposta", dopo_k: "lunedì"}), PP.testo("Fatto."),
                 PP.testo("y"))
    verifica(f"{prima_k} → {dopo_k}: la domanda, poi il «sì» sposta, senza richiedere",
             st.verifica(LEO, vid)["data"] != p0 and "valore_chiamata_diversa" not in b.last_rules,
             f"{t1[:70]} | {t2[:70]} | {b.last_rules}")
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
        self.ricordi, self.aperto, self.detta, self.dovuta = 0, None, 0, True

    def promemoria_giorno(self, chi):
        return None if self.ricordi else "A proposito: lo sviluppo del gioco è sospeso."

    def ricordato(self, chi):
        self.ricordi += 1

    def corrente(self, chi):
        return self.aperto

    def riga_dovuta(self, sv):
        return self.dovuta

    def riga_fuori_tema(self, sv):
        self.detta += 1
        return "Lo sviluppo del gioco resta aperto."

    def dati_turno(self, sv):
        return "Modalità sviluppo aperta: FASEDELLOSVILUPPO."

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
verifica("fuori dalla modalità un tool dello Studio non basta: la riga c'è, come dice il documento",
         "resta aperto" in d and "sviluppo_taciuto_studio" not in b.last_rules, d)
b.tool_ctx.speaker_ctx.in_modalita_studio = True
d = di(b, "Che ore sono?", PP.chiama("ora_attuale", {}), PP.testo("Sono le dieci."))
verifica("in modalità, un tool d'altro: niente riga dello sviluppo, e la regola",
         "resta aperto" not in d and "sviluppo_taciuto_studio" in b.last_rules, d)
svs.dovuta = False
d = di(b, "Che ore sono?", PP.chiama("ora_attuale", {}), PP.testo("Sono le dieci."))
verifica("contrario: la riga già detta da poco, nulla da tacere, nessuna regola",
         "resta aperto" not in d and "sviluppo_taciuto_studio" not in b.last_rules, b.last_rules)
svs.dovuta = True
verifica("in modalità il modello non riceve la fase dello sviluppo",
         "FASEDELLOSVILUPPO" not in (b._sviluppo_turno("Che ore sono?") or "")
         and "sta studiando" in (b._sviluppo_turno("Che ore sono?") or ""))
b.tool_ctx.speaker_ctx.in_modalita_studio = False
verifica("contrario: fuori dalla modalità la riceve",
         "FASEDELLOSVILUPPO" in (b._sviluppo_turno("Che ore sono?") or ""))
svs.aperto = None
svs.dati_sospesi = lambda chi: "SOSPESIDELLOSVILUPPO"
b.tool_ctx.speaker_ctx.in_modalita_studio = True
for frase_ in ("Continuiamo il ripasso.", "Come si sviluppa la fotosintesi?", "Riprendo a studiare."):
    verifica(f"in modalità, «{frase_}»: niente sospesi nei dati del turno",
             not b._sviluppo_turno(frase_), b._sviluppo_turno(frase_))
for frase_ in ("Riprendiamo lo sviluppo del gioco.", "Quali sviluppi ho sospesi?"):
    verifica(f"in modalità, «{frase_}»: i sospesi ci sono",
             b._sviluppo_turno(frase_) == "SOSPESIDELLOSVILUPPO")
b.tool_ctx.speaker_ctx.in_modalita_studio = False
verifica("contrario: fuori dalla modalità «continuiamo» li porta, come prima",
         b._sviluppo_turno("Continuiamo il ripasso.") == "SOSPESIDELLOSVILUPPO")
svs.aperto = types.SimpleNamespace(titolo="Tris", di=lambda: "di Tris", fase="analisi")
b.tool_ctx.speaker_ctx.in_modalita_studio = True
b.last_tools = [{"nome": "sviluppo_passo"}]
verifica("contrario: in modalità, se se ne è appena parlato, la riceve",
         "FASEDELLOSVILUPPO" in (b._sviluppo_turno("E adesso?") or ""))
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
import ast  # noqa: E402
albero = ast.parse((QUI.parent / "calliope" / "ciclo.py").read_text("utf-8"))
chi_parla = next(n for n in ast.walk(albero) if isinstance(n, ast.FunctionDef) and n.name == "_chi_parla")
verifica("il ciclo la aggiorna a ogni turno (`_chi_parla`), fuori da ogni condizione",
         any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "attr", "") == "_modalita_turno" for n in chi_parla.body))
c._modalita = lambda: None
Ciclo._modalita_turno(c)
verifica("contrario: senza satellite no", sc.in_modalita_studio is False)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
