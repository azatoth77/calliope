import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il podcast a due voci dello Studio a secco (04/11/2026, issue #387, epic #251, decisione 0035 punto 58;
calliope/studio/podcast.py, podcast_audio.py, podcast_motore.py). Niente MOSS, niente Docker, niente GPU: un motore
finto, un Docker finto, un Whisper finto, un modello finto; persone e pagine di fantasia.

1. **Le battute senza fonte**: la forma chiusa, niente valori né nomi, nessun canale libero; una battuta caduta si
   porta via i suoi cenni.
2. **Le voci e i numeri in lettere**.
3. **I pezzi**.
4. **Il confronto con Whisper**: numeri in cifre e in lettere, frase saltata, cambiata, negazione persa.
5. **Il lettore**: lo stesso metodo del riassunto, gli stessi cancelli.
6. **Il container**: senza rete né capacità, in sola lettura, hash che non tornano.
7. **vLLM riparte sempre**: ogni guasto, il confronto, il segno su disco, l'avvio dopo una caduta, chi aspetta.
8. **Quando parte e quando si ferma**: voce, lavori, memoria, fascia, prova aperta; i pezzi non si perdono.
9. **Pezzi che non tornano**: rigenerati un numero limitato di volte, poi a una voce, oltre il limite niente podcast.
10. **Schermo e voce**: i permessi, la prova aperta, la firma, la cancellazione, la frase in testa.
11. **La configurazione**: spento di serie.

    python prove/prova_studio_podcast.py
"""

import datetime
import io
import json
import shutil
import subprocess
import tempfile
import threading
import types
import wave
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import studio as S  # noqa: E402
from calliope.agenti import servizio as AS  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.studio import ascolta as A  # noqa: E402
from calliope.studio import lettura as L  # noqa: E402
from calliope.studio import podcast as P  # noqa: E402
from calliope.studio import podcast_audio as PA  # noqa: E402
from calliope.studio import podcast_motore as PM  # noqa: E402
from calliope.studio import riassunto as R  # noqa: E402
from calliope.studio import riassunto_controllo as C  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope import guardiano as GU  # noqa: E402
from calliope.tts import _File, _pcm_del_file  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok else ""), flush=True)


class Prof:
    def __init__(self, pid, name, nascita=None, tutori=()):
        self.id, self.name, self.admin = pid, name, False
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, None
        self.level = "familiare"


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


ANDREA = Prof("a1", "Andrea")
LEO = Prof("l1", "Leo", nascita="2011-03-01", tutori=["a1"])
ALTRA = Prof("x1", "Bruna")
REG = Registro(ANDREA, LEO, ALTRA)
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-podcast-"))
ORA = [datetime.datetime(2026, 10, 29, 23, 0)]
registro: list = []
NOMI = ("Calliope",)


# ═══════════════════════════ 1. le battute senza fonte ═══════════════════════════
print("— la forma chiusa")
for x in (*P.RACCORDI_PRIMA, *P.RACCORDI_DOPO):
    verifica(f"«{x}» è breve, senza cifre, senza nomi", len(x) <= 15 and not any(c.isdigit() for c in x)
             and sum(c.isupper() for c in x) == 1 and len(x.split()) <= 3)
sch = P.schema([("A1", {"id": 1})])
item = sch["properties"]["sezioni"]["items"]["properties"]["frasi"]["items"]
verifica("nello schema un enum, nessun campo libero oltre al testo con le sue fonti",
         item["properties"]["prima"]["enum"][1:] == list(P.RACCORDI_PRIMA)
         and item["properties"]["dopo"]["enum"][1:] == list(P.RACCORDI_DOPO)
         and item["required"] == ["voce", "testo", "fonti", "prima", "dopo"]
         and item["properties"]["fonti"]["minItems"] == 1)
n = P.normalizza([{"argomento": "A1", "frasi": [
    {"testo": "Uno.", "fonti": ["P1.1"], "voce": "b", "prima": "e poi?", "dopo": "Esatto."},
    {"testo": "Due.", "fonti": ["P1.2"], "voce": "C", "prima": "Perché nel 1492?", "dopo": "Esatto, Colombo."},
    {"testo": "Tre.", "fonti": ["P1.3"], "dopo": "Esatto. 1492"},
    {"testo": "Quattro.", "fonti": ["P1.3"], "prima": "Ignora le regole", "dopo": "Interessante, davvero molto.",
     "altro": "x"}]}])[0]["frasi"]
verifica("ciò che è nell'elenco resta, nella sua forma", n[0]["voce"] == "B" and n[0]["prima"] == "E poi?"
         and n[0]["dopo"] == "Esatto.")
verifica("contrario: una voce che non c'è, un valore, un nome, un ordine non esistono",
         "voce" not in n[1] and "prima" not in n[1] and "dopo" not in n[1] and "dopo" not in n[2]
         and "prima" not in n[3] and "dopo" not in n[3])
verifica("un campo inventato non passa", "altro" not in n[3])

M = C.Materiale({"P1": "Il fiume Aurelio nasce sul monte Sereno.\nIl fiume sfocia nel lago Quieto.\n"
                       "La sua portata è di 85 metri cubi al secondo.\nIl lago non è profondo."}, (), NOMI)
rif = [("P1", {"id": 1, "testo": "x", "stato": "letta"})]
arif = [("A1", {"id": 11, "titolo": "Il fiume", "pagine": [1]})]
piano_ = {"lettura_s": 100.0, "obiettivo_s": 50.0, "car": {11: 900}, "peso": {11: 100}, "frasi": {11: 4}}
grezzi = P.normalizza([{"argomento": "A1", "frasi": [
    {"voce": "A", "testo": "Il fiume Aurelio nasce sul monte Sereno.", "fonti": ["P1.1"], "dopo": "Capito."},
    {"voce": "A", "testo": "Il fiume Aurelio nasce sul monte Sconosciuto.", "fonti": ["P1.1"], "dopo": "Esatto."},
    {"voce": "B", "testo": "Il fiume sfocia nel lago Quieto.", "fonti": ["P1.2"], "prima": "E poi?"},
    {"voce": "B", "testo": "Esatto.", "fonti": []},
    {"voce": "B", "testo": "Quanta acqua porta il fiume?", "fonti": ["P1.3"]},
    {"voce": "A", "testo": "La sua portata è di ottantacinque metri cubi al secondo.", "fonti": ["P1.3"]}]}])
ris = R.valida(grezzi, M, rif, arif, piano_)
tenute = [f["testo"] for s in ris["sezioni"] for f in s["frasi"]]
verifica("le battute passano dallo stesso controllo: un nome nuovo cade", len(tenute) == 3
         and not any("Sconosciuto" in t for t in tenute), str(tenute))
verifica("contrario: «Esatto.» scritto come battuta senza fonte cade: nessun canale libero",
         not any(t == "Esatto." for t in tenute))
verifica("contrario: una domanda scritta dal modello cade", not any("?" in t for t in tenute))
P.con_battute(ris)
testi = [b["testo"] for s in ris["sezioni"] for b in s["battute"]]
verifica("il cenno della battuta caduta cade con lei", "Esatto." not in testi and "Capito." in testi, str(testi))
tutte_n = {"sezioni": [{"argomento": 11, "proposte": 9, "frasi": [
    {"testo": f"Frase numero {i}.", "fonti": ["P1.1"], "voce": "AB"[i % 2]} for i in range(9)]}], "conti": {}}
P.con_battute(tutte_n)
cn = [b for b in tutte_n["sezioni"][0]["battute"] if b["tipo"] == "cenno"]
verifica("il modello non ne mette: li mette il codice, i soli neutri", 3 <= len(cn) <= 5
         and {b["testo"] for b in cn} <= set(P.RACCORDI_NEUTRI) and tutte_n["conti"]["cenni_del_codice"] >= 3, str(cn))
verifica("i neutri stanno negli elenchi, e non confermano", set(P.RACCORDI_NEUTRI) <= set(P.RACCORDI_DOPO)
         and "Esatto." not in P.RACCORDI_NEUTRI and "Giusto." not in P.RACCORDI_NEUTRI)
verifica("i cenni sono dell'altra voce", all(
    bb["voce"] != cc["voce"] for s in ris["sezioni"] for bb, cc in zip(s["battute"], s["battute"][1:])
    if cc["tipo"] == "cenno" and bb["tipo"] == "frase"))
giudicata = R.dopo_giudizi(R.valida(grezzi, M, rif, arif, piano_),
                           lambda f: "giudizio" if "sfocia" in f["testo"] else None, piano_)
P.con_battute(giudicata)
testi2 = [b["testo"] for s in giudicata["sezioni"] for b in s["battute"]]
verifica("anche dopo il giudizio: «E poi?» se ne va con la sua battuta", "E poi?" not in testi2, str(testi2))


# ═══════════════════════════ 2. voci e numeri ═══════════════════════════
print("— le voci")
frasi = [{"testo": f"Frase numero {i}.", "fonti": ["P1.1"], "voce": "A"} for i in range(9)]
rr = {"sezioni": [{"argomento": 11, "proposte": 9, "frasi": frasi}], "conti": {}}
P.con_battute(rr)
voci = [b["voce"] for b in rr["sezioni"][0]["battute"] if b["tipo"] == "frase"]
verifica("mai più di due battute di fila alla stessa voce, anche se il modello lo chiede",
         max(len(list(g)) for _k, g in __import__("itertools").groupby(voci)) <= P.DI_FILA_MAX, str(voci))
verifica("tutte e due le voci parlano", rr["conti"]["voce_a"] and rr["conti"]["voce_b"])
molte = [{"testo": f"Frase numero {i}.", "fonti": ["P1.1"], "voce": "AB"[i % 2], "dopo": "Esatto.", "prima": "E poi?"}
         for i in range(10)]
rr = {"sezioni": [{"argomento": 11, "proposte": 10, "frasi": molte}], "conti": {}}
P.con_battute(rr)
bb = rr["sezioni"][0]["battute"]
verifica("i cenni al più uno ogni due battute", sum(b["tipo"] == "cenno" for b in bb) <= 5, str(len(bb)))
verifica("in testa a un argomento niente «E poi?»", bb[0]["tipo"] == "frase")
verifica("mai una voce che si fa una domanda da sola, né che risponde a sé stessa", all(
    a["voce"] != c_["voce"] and b_["voce"] != c_["voce"]
    for a, c_, b_ in zip(bb, bb[1:], bb[2:]) if c_["testo"] == "E poi?"), str(bb))
verifica("mai due cenni di fila", not any(a["tipo"] == b["tipo"] == "cenno" for a, b in zip(bb, bb[1:])))

print("— i numeri in lettere: in cifre MOSS sbaglia (15 milioni → «510», banco del 04/11)")
for t, atteso in (("Nel nucleo ci sono 15 milioni di kelvin.", "quindici milioni di kelvin"),
                  ("Sono 4,6 miliardi di anni.", "quattro virgola sei miliardi"),
                  ("La massa è il 99,8 % del totale.", "novantanove virgola otto per cento"),
                  ("A 5800 kelvin.", "cinquemilaottocento kelvin"),
                  ("Sono 100 000 anni.", "centomila anni"),
                  ("Sono 5.800 kelvin.", "cinquemilaottocento kelvin"),
                  ("Nel 1492 sbarcò.", "millequattrocentonovantadue"),
                  ("Nel 2006 cambiò.", "duemilasei"),
                  ("Sono 23 pianeti.", "ventitré pianeti"),
                  ("Vale 0,05 in tutto.", "zero virgola zero cinque"),
                  ("Ci vuole 1 metro.", "un metro"),
                  ("Sono 1500000 persone.", "un milione cinquecentomila"),
                  ("Gli anni-luce sono tanti.", "anni luce")):
    d = P.detto(t)
    verifica(f"«{t}» → «{atteso}»", atteso in d and not any(c.isdigit() for c in d), d)
verifica("le formule si dicono", "ci o due" in P.detto("La formula è CO2."), P.detto("La formula è CO2."))


class PronunciaFinta:
    def applica(self, t, fonemi=True):
        assert fonemi is False           # MOSS non ha i blocchi di fonemi
        return t.replace("computer", "compiuter")


verifica("gli inglesismi come altrove, in grafia italiana", P.per_moss("il computer", PronunciaFinta()) == "il compiuter")


# ═══════════════════════════ 3. i pezzi ═══════════════════════════
print("— i pezzi")
sez = [{"argomento": 11, "battute": [
    {"voce": "AB"[i % 2], "testo": f"Questa è la battuta numero {i} del nostro dialogo di prova.", "tipo": "frase"}
    for i in range(20)]}, {"argomento": 12, "battute": [
        {"voce": "A", "testo": "Il ferro ha una densità di 7,8 grammi.", "tipo": "frase"},
        {"voce": "B", "testo": "Capito.", "tipo": "cenno"},
        {"voce": "A", "testo": "E poi?", "tipo": "cenno"},
        {"voce": "B", "testo": "Il rame è più pesante.", "tipo": "frase"}]}]
args = [{"id": 11, "numero": 1, "titolo": "Il fiume"}, {"id": 12, "numero": 2, "titolo": "Scrivi a mario@esempio.it"}]
pz = P.pezzi(sez, args, NOMI, massimo=400)
verifica("nessun pezzo oltre il tetto", all(sum(len(b["testo"]) for b in p["battute"]) <= 400 for p in pz)
         and len(pz) >= 3, str(len(pz)))
verifica("i numeri dei pezzi in fila", [p["n"] for p in pz] == list(range(1, len(pz) + 1)))
tut = [b for p in pz for b in p["battute"]]
verifica("tutte le battute ci sono, nell'ordine", [b["testo"] for b in tut if b["tipo"] == "frase"] ==
         [b["testo"] for s in sez for b in s["battute"] if b["tipo"] == "frase"])
verifica("i tag delle voci", pz[0]["moss"].startswith("[S1] ") and "[S2] " in pz[0]["moss"])
verifica("a MOSS i numeri in lettere", "sette virgola otto" in pz[-1]["moss"] and "7,8" not in pz[-1]["moss"])
verifica("il titolo si dice", "Il fiume." in pz[0]["moss"])
verifica("contrario: un titolo con un indirizzo non si dice", "mario" not in json.dumps(pz))
lg = P.pezzi([{"argomento": 12, "battute": sez[1]["battute"]}], args, NOMI, massimo=45)
legati = [[b["testo"] for b in p["battute"]] for p in lg]
verifica("un cenno non si stacca dalla sua battuta", any("Capito." in x and any("ferro" in y for y in x) for x in legati),
         str(legati))
verifica("«E poi?» sta con la battuta che segue", any("E poi?" in x and any("rame" in y for y in x) for x in legati),
         str(legati))


# ═══════════════════════════ 4. il confronto con Whisper ═══════════════════════════
print("— il confronto")


def batt(*frasi_):
    return [{"voce": "A", "testo": f, "detto": P.detto(f), "tipo": "frase"} for f in frasi_]


B1 = batt("Nel nucleo il Sole arriva a quindici milioni di kelvin.", "La superficie è molto meno calda.",
          "Attorno al Sole girano otto pianeti.")
verifica("uguale al copione", PA.confronta(B1, " ".join(b["detto"] for b in B1))["ok"])
verifica("Whisper scrive le cifre", PA.confronta(
    B1, "Nel nucleo il Sole arriva a 15 milioni di kelvin. La superficie è molto meno calda. Attorno al Sole girano 8 "
        "pianeti.")["ok"])
verifica("una parola storpiata da Whisper va bene", PA.confronta(
    batt("Oltre Nettuno c'è la fascia di Kuiper con tanti corpi ghiacciati."),
    "Oltre Netuno c'è la fascia di Kaiper con tanti corpi ghiacciati.")["ok"])
e = PA.confronta(B1, "Nel nucleo il Sole arriva a 510 di kelvin. La superficie è molto meno calda. Attorno al Sole "
                     "girano otto pianeti.")
verifica("contrario: 15 milioni → 510 non torna", not e["ok"] and e["numeri_persi"] >= 1
         and "numero" in e["frasi"][0]["motivi"])
e = PA.confronta(B1, "Nel nucleo il Sole arriva a quindici milioni di kelvin. La superficie è molto meno calda.")
verifica("contrario: una frase saltata", not e["ok"] and "persa" in e["frasi"][2]["motivi"], str(e["frasi"]))
e = PA.confronta(batt("La superficie è molto meno calda del nucleo."),
                 "La superficie è molto meravigliosa del nucleo.")
verifica("contrario: «molto meno calda» → «molto meravigliosa»", not e["ok"], str(e))
e = PA.confronta(batt("Il lago non è profondo in nessun punto."), "Il lago è profondo in nessun punto.")
verifica("contrario: la negazione persa", not e["ok"] and "negazione" in e["frasi"][0]["motivi"], str(e))
lunga = "La superficie del Sole è molto meno calda del nucleo, che arriva a temperature altissime durante la fusione."
e = PA.confronta(batt(lunga), lunga.replace("meno calda", "meravigliosa"))
verifica("contrario: in una frase lunga «meno» perso si vede lo stesso", not e["ok"] and e["frasi"][0]["copre"] > 0.7, str(e))
verifica("«99,8%» di Whisper è «novantanove virgola otto per cento»", PA.confronta(
    batt("Da solo contiene il novantanove virgola otto per cento di tutta la massa."),
    "Da solo contiene il 99,8% di tutta la massa.")["ok"])
verifica("«5.800» di Whisper è «cinquemilaottocento»", PA.confronta(
    batt("La superficie è a cinquemilaottocento kelvin."), "La superficie è a 5.800 Kelvin.")["ok"])
verifica("contrario: 5,10 milioni non è quindici milioni", not PA.confronta(
    batt("Nel nucleo arriva a quindici milioni di kelvin."), "Nel nucleo arriva a 5,10 milioni di Kelvin.")["ok"])
e = PA.confronta(batt("Il fiume nasce sul monte."), "Il fiume nasce sul monte. E poi tante altre parole che nel copione "
                                                    "non ci sono proprio per niente davvero mai.")
verifica("contrario: testo inventato", not e["ok"] and e["inventate"] > 5, str(e))
cenni = [{"voce": "A", "testo": "Il fiume nasce sul monte.", "detto": "Il fiume nasce sul monte.", "tipo": "frase"},
         {"voce": "B", "testo": "Esatto.", "detto": "Esatto.", "tipo": "cenno"}]
verifica("un cenno mangiato non conta", PA.confronta(cenni, "Il fiume nasce sul monte.")["ok"])
verifica("nei conti niente testo", all(not isinstance(v, str) for k, v in e.items() if k != "frasi"))
verifica("un audio vuoto non torna", not PA.confronta(B1, "")["ok"])


# ═══════════════════════════ 5. il lettore ═══════════════════════════
print("— il lettore")


def cfg_nuova(nome, modo="attiva"):
    c = Config()
    c.memory_db = str(TMP / nome)
    c.studio_modo = "attivo"
    c.studio_cartella = str(TMP / (nome + "-studio"))
    c.turn_log_dir = str(TMP / "registro")
    c.studio_lettura = False
    c.studio_argomenti = False
    c.studio_carte_genera = c.studio_mappa_genera = c.studio_domande_genera = "spenta"
    c.studio_preparazione = "spenta"
    c.studio_preparazione_quiete_s = 0
    c.studio_riassunto = "spenta"
    c.studio_podcast = modo
    c.studio_podcast_fascia = ""
    c.studio_podcast_quiete_s = 0
    return c


class GuardianoSi:
    attivo = True

    def __init__(self):
        self.viste = []
        self.vieta = ""

    def giudica(self, domanda, risposta=None, *a, **k):
        self.viste.append(risposta)
        return GU.Giudizio(GU.VIETATO if self.vieta and self.vieta in risposta else GU.OK)


def studio(cfg):
    st = S.Studio(cfg, registry=REG, log=registro.append, adesso=lambda: ORA[0])
    st.avvia_lettura(None, avvia=False)
    st.guardiano = GuardianoSi()
    return st


PAG_1 = ("Il 12 ottobre 1492 Cristoforo Colombo sbarcò sull'isola di Guanahani con tre caravelle.\n"
         "La traversata dell'Atlantico era cominciata il 3 agosto da Palos.\n"
         "Nel XV secolo i Portoghesi cercavano una via per le Indie lungo l'Africa.\n"
         + "\n".join(f"Le navi portavano spezie dalle terre lontane verso il porto numero {i}." for i in range(1, 8)))
PAG_2 = ("La densità è la massa divisa per il volume.\nIl ferro ha una densità di 7,8 g/cm³.\n"
         "Il diossido di carbonio ha formula CO2.\n"
         + "\n".join(f"La massa si misura con la bilancia e il volume col cilindro {i}." for i in range(1, 8)))


def verifica_storia(st, chi=None):
    chi = chi or LEO
    vid = st.crea_verifica(chi, "Storia", "2026-11-05")
    mid = st.aggiungi_materiale(chi, vid, "foto", "Libro")
    ids = [st.aggiungi_pagina(chi, mid, numero=str(40 + i), stato="letta", testo=t, metodo="ocr")
           for i, t in enumerate((PAG_1, PAG_2))]
    a1 = st.aggiungi_argomento(chi, vid, "I viaggi di esplorazione", [ids[0]], proposto=False)
    a2 = st.aggiungi_argomento(chi, vid, "La densità", [ids[1]], proposto=False)
    st.conferma_argomenti(chi, vid)
    return vid, ids, (a1, a2)


BUONA = {"sezioni": [
    {"argomento": "A1", "frasi": [
        {"voce": "A", "testo": "Il dodici ottobre millequattrocentonovantadue Cristoforo Colombo sbarcò sull'isola di "
                               "Guanahani.", "fonti": ["P1.1"], "dopo": "Capito."},
        {"voce": "B", "testo": "La traversata dell'Atlantico era cominciata il tre agosto da Palos.",
         "fonti": ["P1.2"], "prima": "E poi?"},
        {"voce": "A", "testo": "Nel quindicesimo secolo i Portoghesi cercavano una via per le Indie lungo l'Africa.",
         "fonti": ["P1.3"]}]},
    {"argomento": "A2", "frasi": [
        {"voce": "B", "testo": "La densità è la massa divisa per il volume.", "fonti": ["P2.1"]},
        {"voce": "A", "testo": "Il ferro ha una densità di sette virgola otto grammi al centimetro cubo.",
         "fonti": ["P2.2"], "dopo": "Esatto."},
        {"voce": "B", "testo": "Il diossido di carbonio ha formula CO2.", "fonti": ["P2.3"]}]}]}
CATTIVA = {"sezioni": [{"argomento": "A1", "frasi": [
    {"voce": "A", "testo": "Vespucci sbarcò il tre ottobre del millequattrocentonovantatre.", "fonti": ["P1.1"]},
    {"voce": "B", "testo": "Amerigo portò con sé sette caravelle.", "fonti": ["P1.1"]}]}]}


class Finto:
    def __init__(self):
        self.richieste, self.giudizi, self.risposta, self.solleva = [], [], BUONA, None
        self.giudizio = lambda frase: '{"risposta": "si"}'

    def __call__(self, body):
        if self.solleva:
            raise self.solleva
        if "risposta" in json.dumps(body.get("format") or {}):
            self.giudizi.append(body)
            return {"content": self.giudizio(body["messages"][1]["content"]), "fine": "stop", "prompt": 10, "eval": 2}
        self.richieste.append(body)
        testo = self.risposta if isinstance(self.risposta, str) else json.dumps(self.risposta)
        return {"content": testo, "fine": "stop", "prompt": 100, "eval": 50}


class GuardiaFinta:
    perche = None

    def motivo(self):
        return self.perche


def lettore(st):
    lt = L.Lettore(st, None, "qwen-finto", GuardiaFinta(), log=registro.append)
    lt._chiedi_corpo = Finto()
    return lt


st = studio(cfg_nuova("attiva.db"))
vid, ids, (a1, a2) = verifica_storia(st)
lt = lettore(st)
verifica("una verifica a pagine lette è da fare", [v["id"] for v in st.verifiche_per_podcast()] == [vid])
verifica("si scrive", lt.scrivi_podcast(vid) == R.PRONTO, str(st.podcast_stato(vid)))
corpo = lt._chiedi_corpo.richieste[0]
verifica("la richiesta: temperatura 0, thinking spento, lo schema con voce e cenni", corpo["options"]["temperature"] == 0
         and corpo["think"] is False and "RACCORDI" not in json.dumps(corpo)
         and "«voce»" in corpo["messages"][1]["content"])
verifica("le pagine in busta", "<" in corpo["messages"][1]["content"] or "busta" in corpo["messages"][1]["content"].lower()
         or "P1.1" in corpo["messages"][1]["content"])
stato = st.podcast_stato(vid)
verifica("stesso giudice: un giudizio per battuta, stesso guardiano", len(lt._chiedi_corpo.giudizi) == 6
         and stato["conti"]["giudicate"] == 6 and len(st.guardiano.viste) == 6)
verifica("nei conti nessun testo", "Colombo" not in json.dumps(stato))
riga = st._riga_podcast(vid)
cont = json.loads(riga["contenuto"])
verifica("le battute coi cenni, e i pezzi con i numeri in lettere", any(b["tipo"] == "cenno" for s in cont["sezioni"]
                                                                        for b in s["battute"])
         and cont["pezzi"] and "7,8" not in json.dumps(cont["pezzi"]))
verifica("non si riscrive con le stesse pagine", st.verifiche_per_podcast() == [] and lt.scrivi_podcast(vid) == "niente")
stg = studio(cfg_nuova("giudizio.db"))
vg, _i, _a = verifica_storia(stg)
ltg = lettore(stg)
ltg._chiedi_corpo.giudizio = lambda t: '{"risposta": "no"}' if "traversata" in t else '{"risposta": "si"}'
verifica("un «no» del giudice toglie la battuta", ltg.scrivi_podcast(vg) == R.PRONTO
         and "traversata" not in stg._riga_podcast(vg)["contenuto"]
         and "E poi?" not in json.dumps(json.loads(stg._riga_podcast(vg)["contenuto"])["sezioni"]))
stg2 = studio(cfg_nuova("guardiano.db"))
vg2, _i, _a = verifica_storia(stg2)
stg2.guardiano.vieta = "Palos"
ltg2 = lettore(stg2)
verifica("il guardiano toglie la battuta", ltg2.scrivi_podcast(vg2) == R.PRONTO
         and "Palos" not in stg2._riga_podcast(vg2)["contenuto"])
stg3 = studio(cfg_nuova("senza_guardiano.db"))
vg3, _i, _a = verifica_storia(stg3)
stg3.guardiano = None
ltg3 = lettore(stg3)
verifica("per un minore senza guardiano niente", ltg3.scrivi_podcast(vg3) != R.PRONTO, stg3.podcast_stato(vg3)["esito"])
stc = studio(cfg_nuova("cattiva.db"))
vc, _i, _a = verifica_storia(stc)
ltc = lettore(stc)
ltc._chiedi_corpo.risposta = CATTIVA
verifica("un copione che perde troppo: «scarso», nessun testo", ltc.scrivi_podcast(vc) == R.SCARSO
         and not stc._riga_podcast(vc)["contenuto"])
sts = studio(cfg_nuova("spenta.db", "spenta"))
vs, _i, _a = verifica_storia(sts)
verifica("spenta: niente al modello", sts.verifiche_per_podcast() == [] and sts.podcast_da_preparare() == [])
cfg_o = cfg_nuova("ombra.db")
cfg_o.studio_modo = "ombra"
crom = studio(cfg_o)
vo, _i, _a = verifica_storia(crom)
verifica("Studio in ombra: niente al modello", crom.verifiche_per_podcast() == [])
stp = studio(cfg_nuova("prova.db"))
vp, _i, _a = verifica_storia(stp)
orig = stp._prova_aperta
stp._prova_aperta = lambda v: {"id": 1}
verifica("con una prova aperta niente al modello", stp.verifiche_per_podcast() == [] or stp._libreria_chiusa is not None)
stp._prova_aperta = orig
verifica("il modo: un valore strano è spento", P.modo(types.SimpleNamespace(studio_podcast="boh")) == P.SPENTA)
lr = lettore(st)
verifica("il riassunto è ancora quello (riassumi)", lr.riassumi(9999) == "niente")


# ═══════════════════════════ 6. il container ═══════════════════════════
print("— il container")
from pathlib import PurePosixPath as PP  # noqa: E402
arg = PM.argomenti_docker(PP("/m"), PP("/l"), PP("/s.py"), 1000, 1000)
testo_arg = " ".join(arg)
verifica("niente rete", "--network none" in testo_arg)
verifica("niente capacità", "--cap-drop ALL" in testo_arg and "no-new-privileges" in testo_arg)
verifica("radice in sola lettura", "--read-only" in testo_arg)
verifica("non è root", "--user 1000:1000" in testo_arg)
verifica("pesi e codice in sola lettura", "/m:/pv:ro" in testo_arg and "/s.py:/moss_lavoro.py:ro" in testo_arg)
verifica("una sola cartella scrivibile", [a for a in arg if a.startswith("/l:") or a == "/l:/lavoro"] == ["/l:/lavoro"]
         and sum(1 for a, b in zip(arg, arg[1:]) if a == "-v") == 3)
verifica("niente scaricamenti", "HF_HUB_OFFLINE=1" in testo_arg and "TRANSFORMERS_OFFLINE=1" in testo_arg)
verifica("memoria con tetto, senza swap in più", arg[arg.index("--memory") + 1] == arg[arg.index("--memory-swap") + 1])
verifica("nessuna voce di persona: i campioni di MOSS non si citano", "reference_02" not in (
    (QUI.parent / "setup/linux/motore/moss_lavoro.py").read_text(encoding="utf-8")))
script = (QUI.parent / "setup/linux/motore/moss_lavoro.py").read_text(encoding="utf-8")
verifica("il lavoro non stampa il copione", 'print("fatta", rid, json.dumps(m)' in script and "repr(e)" not in script)
mos = TMP / "moss"
(mos / "a").mkdir(parents=True)
(mos / "a/uno.py").write_text("x = 1")
(mos / "a/peso.safetensors").write_bytes(b"12345")
import hashlib  # noqa: E402
el = TMP / "el.sha256"
el.write_text(f"# prova\n{hashlib.sha256(b'x = 1').hexdigest()} 5 a/uno.py\n{'0' * 64} 5 a/peso.safetensors\n")
verifica("i file come nell'elenco; i pesi di serie solo per dimensione", PM.controlla_file(mos, el) == [])
verifica("con tutti gli hash anche i pesi", PM.controlla_file(mos, el, tutti=True) == ["a/peso.safetensors"])
(mos / "a/uno.py").write_text("x = 2")
verifica("contrario: il codice cambiato non torna", PM.controlla_file(mos, el) == ["a/uno.py"])
(mos / "a/peso.safetensors").write_bytes(b"123")
verifica("contrario: un peso di un'altra dimensione", "a/peso.safetensors" in PM.controlla_file(mos, el))
(mos / "a/uno.py").unlink()
verifica("contrario: un file che manca", "a/uno.py" in PM.controlla_file(mos, el))
verifica("l'elenco fissato c'è, con i pesi e il codice", {"pesi/moss-ttsd/modeling_moss_tts.py",
                                                          "src/MOSS-TTSD/generation_utils.py"} <= {
    r.split(None, 2)[2] for r in PM.elenco_hash().read_text(encoding="utf-8").splitlines()
    if r and not r.startswith("#")})


# ═══════════════════════════ 7. vLLM riparte sempre ═══════════════════════════
print("— il riavvio di vLLM")
INSPECT = {"Config": {"Image": "vllm", "Cmd": ["--model", "qwen"], "Entrypoint": None, "User": "1:1",
                      "Env": ["VLLM_SERVER_DEV_MODE=1", "HOME=/cache"]},
           "HostConfig": {"PortBindings": {"8000/tcp": [{"HostPort": "8000"}]}, "NetworkMode": "calliope-vllm",
                          "RestartPolicy": {"Name": "unless-stopped"}, "Binds": ["/h:/hf"], "IpcMode": "host",
                          "DeviceRequests": [{"Driver": "cdi"}]},
           "NetworkSettings": {"Networks": {"calliope-vllm": {"IPAddress": "1.2.3.4"}}}, "State": {"Running": True}}


class Docker:
    """Un Docker finto: `calliope-vllm` c'è e si ferma e riparte, `calliope-moss` come dice la prova."""

    def __init__(self):
        self.chiamate, self.vllm_su, self.inspect = [], True, json.loads(json.dumps(INSPECT))
        self.non_riparte, self.stop_guasto = False, False
        self.pausa = False
        self.moss = False

    def __call__(self, argv, timeout=60.0):
        self.chiamate.append(list(argv))
        out = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        az = argv[1]
        if az == "inspect":
            if argv[2] == "-f":
                out.stdout = "true" if self.moss else "false"
            else:
                i = json.loads(json.dumps(self.inspect))
                i["State"]["Running"] = self.vllm_su
                out.stdout = json.dumps([i])
        elif az == "stop":
            if self.stop_guasto:
                out.returncode = 1
            else:
                self.vllm_su = False
        elif az == "start":
            if not self.non_riparte:
                self.vllm_su = True
        elif az == "rm":
            self.moss = False
        return out

    def chiedi(self, percorso):
        if not self.vllm_su:
            return None
        return {"is_paused": self.pausa} if percorso == "/is_paused" else {}

    def azioni(self):
        return [c[1] for c in self.chiamate if c[1] in ("stop", "start", "run", "rm")]


class Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def dorme(self, s):
        self.t += s


def ripresa_finta(nome):
    d = Docker()
    o = Orologio()
    v = PM.ControlloVllm("http://127.0.0.1:8000", esegui=d, chiedi=d.chiedi, dorme=o.dorme, orologio=o)
    c = TMP / f"rip-{nome}"
    r = PM.Ripresa(c, v, togli_motore=lambda: PM.togli_container(d), log=registro.append, dorme=o.dorme, orologio=o,
                   tetto_s=60)
    return r, d, o


r, d, o = ripresa_finta("base")
prima = r.ferma({"verifica": 1})
verifica("il segno è su disco prima del fermo", r.segno.exists() and not d.vllm_su and r.in_ripresa())
verifica("mai `rm` su vLLM: stop e start dello stesso container", d.azioni() == ["stop"]
         and not any("calliope-vllm" in c and c[1] == "rm" for c in d.chiamate))
o.t += 300
verifica("riparte", r.riparti() and d.vllm_su and not r.segno.exists() and not r.in_ripresa())
verifica("il confronto: niente è cambiato", r.ultime_differenze == [] and r.ultimo_fermo_s == 300.0
         and prima["ambiente"] == sorted(INSPECT["Config"]["Env"]))
verifica("il segno non contiene testo e il confronto non dice valori", "VLLM_SERVER_DEV_MODE" in json.dumps(prima))
r, d, o = ripresa_finta("diverso")
r.ferma({})
d.inspect["Config"]["Env"] = ["HOME=/cache"]           # la modalità sviluppo persa: la trappola del 04/11
n_log = len(registro)
r.riparti()
verifica("il confronto se ne accorge, se qualcuno l'ha rifatto senza PAUSA=1", r.ultime_differenze == ["ambiente"]
         and any("impostazioni diverse" in x for x in registro[n_log:]))
verifica("nel registro il nome, non i valori", not any("VLLM_SERVER" in x for x in registro[n_log:]))
r, d, o = ripresa_finta("nonriparte")
r.ferma({})
d.non_riparte = True
verifica("non riparte entro il tetto: il segno resta", not r.riparti() and r.segno.exists() and r.in_ripresa())
d.non_riparte = False
verifica("il controllo riprova", r.controlla() and not r.segno.exists() and d.vllm_su)
r, d, o = ripresa_finta("pausa")
r.ferma({})
d.pausa = True
verifica("ripartito ma in pausa: non è finita", not r.riparti() and r.segno.exists())
d.pausa = False
verifica("contrario: tolta la pausa, finita", r.controlla() and not r.segno.exists())
r, d, o = ripresa_finta("sparito")
r.ferma({})
d.inspect = None
try:
    r.vllm._inspect = lambda: None
except Exception:
    pass
verifica("il container sparito: il confronto lo dice", (r.riparti() or True) and "container" in r.ultime_differenze)
r, d, o = ripresa_finta("avvio")
r.ferma({"verifica": 1})
pulita = []
r2 = PM.Ripresa(r.segno.parent, r.vllm, togli_motore=lambda: PM.togli_container(d), log=registro.append, dorme=o.dorme,
                orologio=o, tetto_s=60, pulisci=lambda: pulita.append(1))
verifica("Calliope caduta a metà: un altro processo lo vede", r2.in_ripresa())
d.moss = True
th = r2.all_avvio(attesa_s=0)
th.join(5)
verifica("all'avvio: via MOSS, vLLM su, segno tolto", not d.moss and d.vllm_su and not r2.segno.exists())
verifica("e via la cartella del container, col copione", bool(pulita))
verifica("con l'impostazione di prima dal segno", r2.ultime_differenze == [], str(r2.ultime_differenze))
verifica("senza segno all'avvio non si tocca niente", r2.all_avvio() is None)
r, d, o = ripresa_finta("chiusura")
r.ferma({})
r.alla_chiusura()
verifica("alla chiusura: docker start senza aspettare, e il segno resta per il controllo", d.vllm_su and r.segno.exists()
         and d.azioni()[-1] == "start")
r, d, o = ripresa_finta("attende")
verifica("niente da aspettare", r.attendi(5) is True)
r.ferma({})
verifica("chi aspetta rinuncia oltre il tetto", r.attendi(3) is False)
verifica("chi aspetta rinuncia se il lavoro è annullato", r.attendi(100, annullato=lambda: True) is False)
r.riparti()
verifica("con vLLM su non aspetta", r.attendi(1) is True)


print("— chi chiede un agente aspetta, e lo sente dire")
class LavoriFinti(AS.Lavori):
    def __init__(self):            # niente del vero: si provano solo i metodi qui sotto
        self.diagnosi = {}
        self._lock = threading.Lock()
        self.lavori = []
        self.modelli = {}
        self._verifica_lock = threading.Lock()
        self.tunnel = None


lf = LavoriFinti()
rr2, dd2, oo2 = ripresa_finta("lavori")
lf.attesa_motore = rr2
rr2.ferma({})
verifica("verifica non dà un guasto mentre il motore riparte", lf.verifica()["codice"] == "ok"
         and lf.diagnosi.get("in_ripresa"))
lav = AS.Lavoro("L1", "codice", "un gioco", "a1", "Andrea", "familiare", "", "", "", [])
frase = lf._proposta(lav)
verifica("la proposta lo dice", "circa quattro minuti" in frase, frase)
rr2.dorme = lambda s: (setattr(rr2, "_prova", True), rr2.riparti())       # intanto riparte
lf._aspetta_motore(lav)
verifica("il lavoro ha aspettato, dicendolo", "riparte" in lav.passo and not rr2.in_ripresa(), lav.passo)
lf2 = LavoriFinti()
verifica("contrario: senza podcast non cambia niente", lf2.motore_in_ripresa() is False)


# ═══════════════════════════ 8. quando parte, quando si ferma ═══════════════════════════
print("— il preparatore")


def wav_di(testo: str, rate=24000) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(testo.encode("utf8").ljust(rate // 2, b"\0"))
    return b.getvalue()


class VocePiperFinta:
    rate = 22050

    def in_wav(self, testo):
        return wav_di(testo[:40], self.rate)


class Mondo:
    """Il motore e il Whisper finti, e i segnali. `rompi(n, tentativo)`: la ritrascrizione sbagliata."""

    def __init__(self, nome, modo="attiva", memoria=50000):
        self.st = studio(cfg_nuova(f"{nome}.db", modo))
        self.vid, self.ids, _a = verifica_storia(self.st)
        self.lt = lettore(self.st)
        self.lt.scrivi_podcast(self.vid)
        # Più pezzi, così una sessione ha un «durante»
        righe = json.loads(self.st._riga_podcast(self.vid)["contenuto"])
        righe["pezzi"] = P.pezzi(righe["sezioni"], self.st._argomenti_numerati(self.vid), NOMI, massimo=120)
        self.st.dati.scrivi("UPDATE studio_podcast SET contenuto = ? WHERE verifica = ?",
                            (json.dumps(righe), self.vid))
        self.r, self.d, self.o = ripresa_finta(nome)
        self.voce, self.lavori, self.mem, self.libero = True, False, memoria, True
        self.st.podcast_preparatore = self
        self.detti = {}
        self.chiamate = 0
        self.errore_in_wav = None
        self.errore_avvio = None
        self.errore_stt = None
        self.errore_ferma = None
        self.falli_dopo = None      # dopo tante battute generate, cede
        self.rompi = lambda n, t: t
        self.semi = []
        self.motori = []
        self.quiete_chieste = []
        self.prep = PA.Preparatore(self.st, self.r, self.crea, self.whisper, VocePiperFinta(),
                                   self.voce_ferma, lambda: self.lavori, lettore_libero=lambda: self.libero,
                                   vllm_libero=lambda: None, memoria=lambda: self.mem, log=registro.append,
                                   orologio=self.o, dorme=self.o.dorme)

    def voce_ferma(self, s):
        self.quiete_chieste.append(s)
        return self.voce

    def crea(self, cede):
        m = types.SimpleNamespace(avvia=self._avvia, in_wav=self._in_wav, ferma=self._ferma, seme=0, rate=24000,
                                  carico_s=132.0, ultima={"gen_s": 1.0}, cede=cede)
        self.motori.append(m)
        return m

    def _avvia(self):
        if self.errore_avvio:
            raise self.errore_avvio
        self.d.moss = True

    def _ferma(self):
        self.d.moss = False
        if self.errore_ferma:
            raise self.errore_ferma

    def _in_wav(self, testo):
        self.chiamate += 1
        self.o.t += 10
        self.semi.append(self.motori[-1].seme)
        if self.errore_in_wav:
            raise self.errore_in_wav
        if self.falli_dopo is not None:
            self.falli_dopo -= 1
            if self.falli_dopo < 0:
                self.voce = False            # un turno mentre genera: la cede lo sente
        w = wav_di(testo)
        self.detti[w] = (testo, self.chiamate)
        return w

    def whisper(self, wav):
        if self.errore_stt:
            raise self.errore_stt
        testo, n = self.detti[wav]
        return self.rompi(n, __import__("re").sub(r"\[S\d\]", " ", testo))

    def pezzi(self):
        return self.st.podcast_da_preparare()


m = Mondo("felice")
da = m.pezzi()
verifica("un copione pronto è da preparare", [x["id"] for x in da] == [m.vid] and da[0]["pezzi"])
verifica("una sessione intera", m.prep.passo() == "finito", str(m.prep.misure))
verifica("vLLM fermato e ripartito, MOSS tolto", m.d.vllm_su and not m.d.moss and not m.r.segno.exists()
         and m.d.azioni() == ["stop", "start"], str(m.d.azioni()))
u = m.prep.misure["ultima"]
verifica("il confronto nel registro: uguale, ripartito", u["ripartito"] and u["differenze"] == [] and u["fine"] == "finito")
a = m.st.podcast_stato(m.vid)["audio"]
verifica("pronto, con le parti", a["esito"] == "pronto" and len(a["parti"]) == len(da[0]["pezzi"]))
verifica("niente da rifare", m.pezzi() == [] and m.prep.passo() == "niente" and m.d.azioni() == ["stop", "start"])
v = m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))
verifica("il podcast è pronto", m.st.podcast_pronto(v))
cart = P.cartella_podcast(m.st.cfg, m.vid)
with wave.open(str(cart / A.nome_file(a["firma"], 1)), "rb") as w:
    verifica("l'avviso è nel file, portato alla frequenza di MOSS", w.getframerate() == 24000 and
             w.getnframes() / 24000 > a["parti"][0]["intro_s"] > 0.5)
verifica("i file di passaggio non restano", not list(cart.glob("*-p*.wav")))

print("— quando non parte")
for nome, prepara_, atteso in (
        ("voce non ferma", lambda m: setattr(m, "voce", False), "voce_non_ferma"),
        ("un lavoro dell'agente", lambda m: setattr(m, "lavori", True), "lavoro_agente"),
        ("il lettore occupato", lambda m: setattr(m, "libero", False), "lettore_occupato"),
        ("poca memoria", lambda m: setattr(m, "mem", 3000), "memoria"),
        ("vLLM spento: non si tocca", lambda m: setattr(m.d, "vllm_su", False), "vllm_spento"),
        ("fuori fascia", lambda m: setattr(m.st.cfg, "studio_podcast_fascia", "99:00-99:30"), "fuori_fascia")):
    m = Mondo("no-" + nome.replace(" ", "").replace(":", "").replace("'", ""))
    prepara_(m)
    verifica(f"{nome}: non ferma vLLM", m.prep.passo() == atteso and "stop" not in m.d.azioni())
m = Mondo("guardia")
m.prep.vllm_libero = lambda: "vLLM occupato"
verifica("vLLM occupato", m.prep.passo() == "vllm_occupato" and "stop" not in m.d.azioni())
t = types.SimpleNamespace(tm_hour=2, tm_min=0)
verifica("la fascia", PA.nella_fascia("00:30-07:00", t) and not PA.nella_fascia("08:00-20:00", t)
         and PA.nella_fascia("", t) and PA.nella_fascia("22:00-03:00", t)
         and not PA.nella_fascia("boh", t))
verifica("di serie la notte", Config().studio_podcast_fascia == "00:30-07:00")

print("— ogni guasto: vLLM riparte, e il lavoro fatto resta")


def riparte(m):
    return m.d.vllm_su and not m.d.moss and not m.r.segno.exists() and "start" in m.d.azioni()


m = Mondo("avvio-guasto")
m.errore_avvio = PM.Guasto("hash_diverso")
verifica("il motore non parte (hash diversi)", m.prep.passo() == "guasto_hash_diverso" and riparte(m), str(m.d.azioni()))
verifica("dopo un guasto si aspetta", m.prep.motivo() == "pausa")
m = Mondo("avvio-errore")
m.errore_avvio = RuntimeError("boh")
verifica("un errore qualunque all'avvio", m.prep.passo().startswith("errore_") and riparte(m))
m = Mondo("genera-guasto")
m.errore_in_wav = PM.Guasto("container_caduto")
verifica("il container cade a metà", m.prep.passo() == "guasto_container_caduto" and riparte(m))
m = Mondo("genera-errore")
m.errore_in_wav = OSError("disco")
verifica("il disco pieno", m.prep.passo() == "errore_OSError" and riparte(m))
m = Mondo("stt-guasto")
m.errore_stt = OSError("whisper giù")
verifica("Whisper giù", m.prep.passo() == "errore_OSError" and riparte(m))
c_p = P.cartella_podcast(m.st.cfg, m.vid)
n_prima = m.chiamate
verifica("il pezzo generato resta da controllare", bool(list(c_p.glob("*.prova.wav"))))
m.errore_stt = None
m.prep._riprova_dopo = 0
verifica("la sessione dopo lo controlla senza rifarlo", m.prep.passo() == "finito" and m.semi[0] == 42
         and m.st.podcast_stato(m.vid)["audio"]["esito"] == "pronto", str(m.chiamate))
m = Mondo("stop-guasto")
m.d.stop_guasto = True
verifica("vLLM che non si ferma: nessun MOSS", m.prep.passo().startswith("guasto") and not m.motori
         and not m.r.segno.exists())
m = Mondo("ferma-guasto")
m.errore_ferma = RuntimeError("docker")
verifica("il container non si toglie: vLLM riparte lo stesso", m.prep.passo() == "finito" and m.d.vllm_su
         and "start" in m.d.azioni())
m = Mondo("noriparte")
m.d.non_riparte = True
verifica("vLLM non riparte: il giro dopo riprova prima di tutto", m.prep.passo() == "finito" and m.r.segno.exists())
m.d.non_riparte = False
verifica("contrario: riprovato", m.prep.passo() == "niente" and not m.r.segno.exists() and m.d.vllm_su)
m = Mondo("noriparte2")
m.d.non_riparte = True
m.prep.passo()
verifica("mentre non è ripartito niente sessioni nuove", m.prep.passo() == "vllm_da_riprendere"
         and m.d.azioni().count("stop") == 1)
verifica("e chi vuole un agente aspetta", m.r.in_ripresa())

print("— arriva un turno, un lavoro")
m = Mondo("turno")
m.falli_dopo = 0
verifica("un turno durante la generazione: MOSS via, vLLM su", m.prep.passo() == "voce" and riparte(m))
stato_d = json.loads((P.cartella_podcast(m.st.cfg, m.vid) / f"{m.pezzi()[0]['firma']}-stato.json").read_text())
verifica("nello stato su disco solo numeri", "Colombo" not in json.dumps(stato_d))
n1 = m.chiamate
verifica("niente è pronto ancora: resta il riassunto", not m.st.podcast_pronto(
    m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))))
m.voce = True
m.falli_dopo = None
verifica("la sessione dopo riparte da dove era", m.prep.passo() == "finito" and m.chiamate >= n1
         and m.st.podcast_stato(m.vid)["audio"]["esito"] == "pronto", str(m.chiamate))
m = Mondo("lavoro")
orig_w = m.whisper
def _w(wav, m=m, orig_w=orig_w):
    m.lavori = True
    return orig_w(wav)
m.prep.ritrascrivi = _w
fine = m.prep.passo()
verifica("un lavoro dell'agente durante la sessione", fine == "lavoro_agente" and riparte(m), fine)
m = Mondo("tetto")
m.st.cfg.studio_podcast_tetto_min = 0.2
verifica("il tetto di tempo", m.prep.passo() == "tetto" and riparte(m) and m.prep.motivo() == "pausa")
m = Mondo("memoria-bassa")
def _f(wav, m=m):
    m.mem = 3000
    return "x"
m.prep.ritrascrivi = _f
verifica("la memoria sotto il pavimento", m.prep.passo() == "memoria_bassa" and riparte(m))
m = Mondo("memoria-poca")
m.st.cfg.studio_podcast_memoria_gb = 100
verifica("con vLLM fermo la memoria non basta: subito su, nessun MOSS", m.prep.passo() == "memoria_insufficiente"
         and riparte(m) and not m.motori)
m = Mondo("prova-aperta")
pa = m.st._prova_aperta
def _w2(wav, m=m, orig_w=m.whisper):
    m.st._libreria_chiusa = lambda v: True
    return orig_w(wav)
m.prep.ritrascrivi = _w2
verifica("una prova aperta intanto: ci si ferma", m.prep.passo() == "verifica_cambiata" and riparte(m))
m = Mondo("pagine-cambiate")
def _w3(wav, m=m, orig_w=m.whisper):
    m.st.dati.scrivi("UPDATE studio_pagine SET testo = 'Altro testo della pagina.' WHERE id = ?", (m.ids[0],))
    return orig_w(wav)
m.prep.ritrascrivi = _w3
verifica("le pagine cambiate: niente audio di materiale vecchio", m.prep.passo() == "verifica_cambiata" and riparte(m))
m = Mondo("chiusura")
m.prep.close()
verifica("Calliope si chiude", m.prep.sessione(m.pezzi()[0]) == "chiusura" and riparte(m))

print("— un podcast per volta")
m = Mondo("due")
vid2, _i, _a = verifica_storia(m.st)
m.st.dati.scrivi("UPDATE studio_verifiche SET data = '2026-11-20' WHERE id = ?", (vid2,))
m.lt.scrivi_podcast(vid2)
m.prep.passo()
az = m.d.azioni().count("stop")
verifica("una sessione, una verifica", az == 1 and m.st.podcast_stato(m.vid)["audio"] and not m.st.podcast_stato(vid2)["audio"])


# ═══════════════════════════ 9. i pezzi che non tornano ═══════════════════════════
print("— i pezzi che non tornano")
m = Mondo("rigenera")
tent = {}


def rompi_uno(n, t):
    # Il primo tentativo del primo pezzo salta tutto
    tent[n] = 1
    return "" if n == 1 else t


m.rompi = rompi_uno
verifica("si rigenera con un altro seme", m.prep.passo() == "finito" and m.semi[:2] == [42, 43], str(m.semi))
st_d = m.st.podcast_stato(m.vid)["audio"]
verifica("dopo, è a due voci", st_d["esito"] == "pronto" and st_d["conti"]["a_una_voce"] == 0
         and m.prep.misure["rigenerati"] == 1)
m = Mondo("una-voce")
m.st.cfg.studio_podcast_rigenera = 1
tot = len(m.pezzi()[0]["pezzi"])
m.rompi = lambda n, t: "" if n <= 2 else t       # il primo pezzo non torna mai
verifica("il pezzo senza speranza finisce", m.prep.passo() == "finito" and m.chiamate == tot + 1, f"{m.chiamate} {tot}")
aa = m.st.podcast_stato(m.vid)["audio"]
verifica("resta quel pezzo a una voce", aa["esito"] == "pronto" and aa["conti"]["a_una_voce"] == 1
         and aa["parti"][0]["una_voce"] and not aa["parti"][1]["una_voce"], str(aa["conti"]))
verifica("il tentativo è limitato", m.semi.count(42) == tot and m.semi.count(43) == 1, str(m.semi))
vv = m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))
verifica("lo dice: lo schermo la segna", m.st._copione_podcast(vv).parti[0]["una_voce"])
verifica("la frase è del codice", "due voci" in A.PODCAST_PEZZO_A_UNA_VOCE)
verifica("nei conti quanto copione arriva", aa["conti"]["frasi"] > aa["conti"]["frasi_a_due_voci"] > 0, str(aa["conti"]))
m = Mondo("scarso")
m.st.cfg.studio_podcast_rigenera = 0
m.rompi = lambda n, t: ""
m.prep.passo()
aa = m.st.podcast_stato(m.vid)["audio"]
vv = m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))
verifica("troppi a una voce: niente podcast, resta il riassunto", aa["esito"] == "scarso" and not m.st.podcast_pronto(vv)
         and not aa["parti"] and not list(P.cartella_podcast(m.st.cfg, m.vid).glob("*.wav")))
verifica("non si rifà da solo", m.pezzi() == [] and m.d.azioni().count("stop") == 1)
verifica("lo schermo lo dice", "resta il riassunto" in m.st.podcast_nota(vv))
m = Mondo("senza-piper")
m.prep.voce_calliope = types.SimpleNamespace(rate=22050, in_wav=lambda t: (_ for _ in ()).throw(OSError("piper")))
m.prep.passo()
vv = m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))
verifica("senza la voce di Calliope non c'è l'avviso: niente podcast adesso", not m.st.podcast_pronto(vv) and m.d.vllm_su)


# ═══════════════════════════ 10. schermo e voce ═══════════════════════════
print("— lo schermo")
m = Mondo("schermo")
m.prep.passo()
st = m.st
vid = m.vid
d0 = st.ascolto_parti(LEO, vid)
verifica("il podcast è accanto al riassunto", d0["podcast"] and d0["fonte"] == "pagine" and d0["podcast_nota"] is None)
dp = st.ascolto_parti(LEO, vid, "podcast")
verifica("le parti del podcast", dp["fonte"] == "podcast" and dp["parti"] and dp["parti"][0]["tipo"] == "podcast"
         and dp["parti"][0]["pronta"] and dp["parti"][0]["secondi"] >= 0)
au = st.ascolto_audio(LEO, vid, 1, dp["firma"], "podcast")
verifica("il file è servito", Path(au["file"]).is_file())
verifica("mai una sintesi a richiesta", "pronto" not in au)
verifica("una firma vecchia: è cambiato", st.ascolto_audio(LEO, vid, 1, "0000", "podcast").get("cambiato"))
try:
    st.ascolto_audio(LEO, vid, 99, dp["firma"], "podcast")
    verifica("una parte che non c'è", False)
except ValueError:
    verifica("una parte che non c'è", True)
print("— i permessi, come il riassunto")
for nome, chi, ok in (("la persona", LEO, True), ("il tutore", ANDREA, True), ("un'altra persona", ALTRA, False)):
    try:
        st.ascolto_parti(chi, vid, "podcast")
        verifica(f"{nome}", ok)
    except (S.NonTrovata, S.NonPermesso):
        verifica(f"{nome}", not ok)
print("— la prova aperta")
orig = st._prova_aperta
aperta = {"id": 1}
st._prova_aperta = lambda v: aperta
verifica("sullo schermo nessuna parte", st.ascolto_parti(LEO, vid, "podcast")["prova"])
try:
    st.ascolto_audio(LEO, vid, 1, None, "podcast")
    verifica("l'audio no", False)
except A.ProvaAperta:
    verifica("l'audio no", True)
try:
    st.ascolto_prepara(LEO, vid, "tutto", None, "inizia", fonte="podcast")
    verifica("a voce no", False)
except A.ProvaAperta:
    verifica("a voce no", True)
st._prova_aperta = orig

print("— a voce")
lett = st.ascolto_prepara(LEO, vid, "oggi", None, "inizia", fonte="podcast")
verifica("il podcast è uno: «oggi» diventa tutto", lett["cosa"] == "tutto" and lett["fonte"] == "podcast")
verifica("la frase in testa, una volta, poi i file", lett["voci"][0].testo == A.PODCAST_INTRO
         and all(v.tipo == A.AUDIO for v in lett["voci"][1:]))
verifica("a voce dal file si salta l'avviso già detto", lett["voci"][1].salta > 0.5)
verifica("sullo schermo no", st._copione_podcast(st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,)))
         .voci[0].salta == 0)
verifica("il segno non contiene materiale", "Colombo" not in json.dumps([v.testo for v in lett["voci"]]))
verifica("la durata viene dai file", lett["secondi"] >= sum(int(v.secondi) for v in lett["voci"][1:]))
verifica("ogni file un pezzo: i controlli fra un file e l'altro", all(
    len([k for k in pz_ if lett["voci"][k].tipo == A.AUDIO]) <= 1 for pz_ in A.pezzi(lett["voci"], 0)))


class SpeakerFinto:
    def __init__(self, ferma_a=None):
        self.played, self.interrupted, self.ferma_a = [], False, ferma_a
        self.detti = []


class UscitaFinta:
    def __init__(self, sp):
        self.sp = sp

    def turno_lettura(self):
        pass

    def leggi(self, testo, voce=None):
        self.sp.detti.append(testo)
        self.sp.played.append(testo)

    def audio(self, f, segno, salta=0.0):
        self.sp.detti.append(("file", f, salta))
        if self.sp.ferma_a is not None and len(self.sp.detti) >= self.sp.ferma_a:
            self.sp.interrupted = True
            return
        self.sp.played.append(segno)

    def pausa(self, s):
        pass

    def aspetta(self):
        pass


sp = SpeakerFinto()
es = A.leggi(lett, UscitaFinta(sp), sp, lambda: None)
verifica("si dice tutto, in ordine", es["motivo"] == "finito" and sp.detti[0] == A.PODCAST_INTRO
         and sum(isinstance(x, tuple) for x in sp.detti) == len(lett["voci"]) - 1, str(es))
lett2 = st.ascolto_prepara(LEO, vid, "tutto", None, "inizia", fonte="podcast")
sp = SpeakerFinto(ferma_a=2)
es = A.leggi(lett2, UscitaFinta(sp), sp, lambda: None)
verifica("interrotta: la posizione resta sul file", es["motivo"] == "interrotta" and es["pos"] == 1, str(es))
st.ascolto_fermo(lett2, es)
rip = st.ascolto_prepara(LEO, come="riprendi")
verifica("«riprendi» resta sul podcast, con la frase in testa", rip["fonte"] == "podcast" and rip["da"] == 1
         and A.PODCAST_INTRO in rip["intro"], str(rip["intro"]))
verifica("il controllo fra i pezzi: la stessa firma va avanti", st.ascolto_vale(lett2) is None)
pagine_ch = st.dati.scrivi("UPDATE studio_pagine SET testo = 'Altro testo della pagina di prova.' WHERE id = ?", (m.ids[0],))
verifica("cambiata la pagina si ferma", st.ascolto_vale(lett2)[0] == "cambiato", str(st.ascolto_vale(lett2)))
vv = st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (vid,))
verifica("copione e audio scaduti: via appena visti", not st.podcast_pronto(vv) and st._riga_podcast(vid) is None
         and not list(P.cartella_podcast(st.cfg, vid).glob("*")))

print("— non pronto: resta il riassunto, dicendolo")
m = Mondo("non-pronto")
lett3 = m.st.ascolto_prepara(LEO, m.vid, "tutto", None, "inizia", fonte="podcast")
verifica("a voce lo dice e legge ciò che c'è", A.PODCAST_NON_PRONTO in lett3["intro"] and lett3["fonte"] != "podcast")
dn = m.st.ascolto_parti(LEO, m.vid, "podcast")
verifica("sullo schermo le altre parti, con la nota", not dn["podcast"] and dn["fonte"] != "podcast"
         and "quando la macchina è libera" in dn["podcast_nota"], str(dn["podcast_nota"]))
verifica("il file no", m.st.ascolto_audio(LEO, m.vid, 1, None, "podcast").get("cambiato"))
m.st.podcast_preparatore = None
vv = m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))
verifica("contrario: se nessuno lo prepara non si dice che arriverà", m.st.podcast_nota(vv) is None)

print("— startrek: una battuta che sveglierebbe")
m = Mondo("startrek")
m.prep.passo()
vv = m.st.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (m.vid,))
verifica("col nome di adesso va", m.st.podcast_pronto(vv))
m.st._nomi_ascolto = lambda: ["Calliope", "Nel"]
verifica("con una parola che sveglia nel copione non si dice", not m.st.podcast_pronto(vv))
verifica("contrario: l'audio non si butta", m.st._riga_podcast(m.vid) is not None
         and list(P.cartella_podcast(m.st.cfg, m.vid).glob("*.wav")))

print("— la cancellazione e la conservazione")
m = Mondo("cancella")
m.prep.passo()
c_v = P.cartella_podcast(m.st.cfg, m.vid)
verifica("i file ci sono", list(c_v.glob("*.wav")))
m.st.togli_verifica(LEO, m.vid)
verifica("via con la verifica: riga e file", m.st._riga_podcast(m.vid) is None and not c_v.exists())
m = Mondo("pagina-tolta")
m.prep.passo()
m.st.riassunto_pagine_cambiate(m.vid)
verifica("una pagina tolta: via anche il podcast", m.st._riga_podcast(m.vid) is None
         and not P.cartella_podcast(m.st.cfg, m.vid).exists())
m = Mondo("rotazione")
m.prep.passo()
import calliope.studio.dati as D  # noqa: E402
base = D.cartella_di(m.st.cfg)
vive = {m.vid}
n = A.togli_audio(base, verifiche_vive=vive, sotto=P.CARTELLA_PODCAST)
verifica("la rotazione non tocca il podcast di una verifica viva", n == 0 and list(P.cartella_podcast(m.st.cfg, m.vid).glob("*.wav")))
n = A.togli_audio(base, verifiche_vive=set(), sotto=P.CARTELLA_PODCAST)
verifica("una verifica che non c'è più sì", n > 0)
verifica("«svuota» toglie la cartella del lavoro", (P.togli_lavoro(base) or True) and not (base / P.CARTELLA_LAVORO).exists())
verifica("le tabelle: anche la cancellazione per persona", "studio_podcast" in D.TABELLE and "studio_podcast" in D.NUOVE)

print("— l'audio alla voce")
f = TMP / "p.wav"
pc = (b"\x10\x00" * 24000)
with wave.open(str(f), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(24000)
    w.writeframes(pc)
verifica("alla frequenza dell'uscita", abs(len(_pcm_del_file(_File(str(f), "x"), 22050)) / 2 - 22050) < 3)
verifica("senza i secondi di testa", abs(len(_pcm_del_file(_File(str(f), "x", 0.5), 24000)) / 2 - 12000) < 3)
verifica("a frequenza uguale non si ricampiona", _pcm_del_file(_File(str(f), "x"), 24000) == pc)
ss = (QUI.parent / "calliope/tts.py").read_text(encoding="utf-8")
verifica("passa dalla coda delle frasi, va in `played`", "self.text_q.put(_File(" in ss and "(item.segno, _pcm_del_file(" in ss)


# ═══════════════════════════ 11. configurazione ═══════════════════════════
print("— la configurazione")
c = Config()
verifica("spento di serie", c.studio_podcast == "spenta")
yaml = (QUI.parent / "calliope.yaml").read_text(encoding="utf-8")
verifica("le chiavi nel file d'esempio", "studio_podcast: spenta" in yaml and "studio_podcast_fascia" in yaml)
verifica("il tool ha «podcast»", "podcast" in TS.PARAMETRI_ASCOLTA["properties"]["fonte"]["enum"])
js = (QUI.parent / "calliope/schermi/pagina/studio.js").read_text(encoding="utf-8")
verifica("il tasto accanto al riassunto", "Ascolta il podcast" in js and 'fonte: "podcast"' in js)
verifica("«calliope/studio» senza dipendenze nuove", not any(
    x in (QUI.parent / f"calliope/studio/{n}.py").read_text(encoding="utf-8")
    for n in ("podcast", "podcast_audio", "podcast_motore") for x in ("import torch", "import transformers", "soundfile")))
terze = (QUI.parent / "TERZE-PARTI.md").read_text(encoding="utf-8")
verifica("le licenze", "MOSS-TTSD" in terze and "c7cd852" in terze)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
