import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La padronanza per argomento dello Studio a secco (30/10, passo 5, issue #245, epic #251,
decisione 0035 punto 32; calliope/studio/padronanza.py, studio/servizio.py). Niente modello, un
orologio finto, i materiali di fantasia di `manuali/studio/storia.json` (Leo, il tutore Andrea).

1. **Il calcolo**: sotto la soglia di misura «non ancora misurata»; esiti, tipi, età e calo; tipi
   ed esiti sconosciuti ignorati; le parole alle soglie; il livello con metà misurati.
2. **Le lacune**: sotto l'obiettivo, dal più debole, con la lezione successiva dal piano; i non
   misurati non sono lacune.
3. **Il servizio**: `registra_tentativo` (codici validi, mai la fonte «modello», l'argomento di
   un'altra verifica, permessi: tutore sì, un altro adulto no), `padronanza`, la riapertura.
4. **Ombra e mostrata**: in ombra la misura del giorno con la fonte «padronanza_ombra», che la
   previsione ignora, niente sulla home né nel riepilogo, il registro senza titoli; mostrata: la
   misura entra nella previsione, la parola sulle tappe, le lacune sulla home col titolo e la
   lezione, nel riepilogo per numero; spenta rifiuta.
5. **Tenuta e stato d'animo**: i tentativi vanno via con la verifica, «dimentica», la rotazione
   (anche gli orfani) e «svuota»; lo stato d'animo in nessuna tabella.

    python prove/prova_studio_padronanza.py
"""

import datetime
import json
import tempfile
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import studio as S  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.conserva import TABELLE_STUDIO  # noqa: E402
from calliope.studio import dati as D  # noqa: E402
from calliope.studio import padronanza as PD  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                else ""))


def solleva(f, tipo) -> bool:
    try:
        f()
    except tipo:
        return True
    return False


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


ANDREA = Prof("a1", "Andrea")
BRUNO = Prof("b1", "Bruno")
LEO = Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
REG = Registro(ANDREA, BRUNO, LEO)
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-padronanza-"))
ORA = [datetime.datetime(2026, 10, 29, 16, 0)]
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
OGGI = datetime.date(2026, 10, 29)
registro: list = []


def cfg_nuova(nome, padronanza="ombra"):
    c = Config()
    c.memory_db = str(TMP / nome)
    c.studio_modo = "attivo"
    c.studio_cartella = str(TMP / "studio")
    c.studio_lettura = False
    c.studio_padronanza = padronanza
    return c


def studio(cfg):
    st = S.Studio(cfg, registry=REG, log=registro.append, adesso=lambda: ORA[0])
    st.avvia_lettura(None, avvia=False)
    return st


def carica(st, chi=LEO):
    vid = st.crea_verifica(chi, MAT["materia"], MAT["data_verifica"], argomento=MAT["argomento"])
    mid = st.aggiungi_materiale(chi, vid, "foto", "Libro")
    ids = {p["id"]: st.aggiungi_pagina(chi, mid, numero=p["numero"], stato="letta",
                                       testo=p["testo"], metodo="ocr") for p in MAT["pagine"]}
    for a in MAT["argomenti"]:
        st.aggiungi_argomento(chi, vid, a["titolo"], [ids[x] for x in a["pagine"]])
    st.conferma_argomenti(chi, vid)
    return vid, ids, [a["id"] for a in st.argomenti(chi, vid)]


def t(arg, giorno, esito="giusto", tipo="carta"):
    return {"argomento": arg, "giorno": giorno, "tipo": tipo, "esito": esito}


G = lambda n: (OGGI - datetime.timedelta(days=n)).isoformat()  # noqa: E731

# ═══════════════════════════ 1. il calcolo ═══════════════════════════
print("— il calcolo")
p = PD.calcola([t(1, G(0)), t(1, G(0))], OGGI)
verifica("due tentativi: non ancora misurata", p[1]["valore"] is None
         and p[1]["parola"] == "non ancora misurata", p)
p = PD.calcola([t(1, G(0)), t(1, G(0)), t(1, G(0))], OGGI)
verifica("tre tentativi in un giorno solo: non ancora misurata", p[1]["valore"] is None, p)
p = PD.calcola([t(1, G(1)), t(1, G(0)), t(1, G(0))], OGGI)
verifica("tre giusti in due giorni: 100, «la sai»", p[1]["valore"] == 100
         and p[1]["parola"] == "la sai", p)
p = PD.calcola([t(1, G(1), "sbagliato"), t(1, G(0), "indizio"), t(1, G(0))], OGGI)
w1 = 0.5 ** (1 / PD.MEZZA_VITA_GIORNI)
atteso = round(100 * (0 + 0.5 + 1) / (w1 + 2))
verifica("esiti ed età: il tentativo di ieri pesa meno", p[1]["valore"] == atteso,
         (p[1]["valore"], atteso))
p = PD.calcola([t(1, G(1), "sbagliato", "verifica_finta"), t(1, G(0)), t(1, G(0), tipo="mappa")],
               OGGI)
atteso = round(100 * (0.7 + 1) / (1.5 * w1 + 1 + 0.7))
verifica("i pesi per tipo (verifica finta 1,5, mappa 0,7)", p[1]["valore"] == atteso,
         (p[1]["valore"], atteso))
p = PD.calcola([t(1, G(22)), t(1, G(21)), t(1, G(21))], OGGI)
verifica("senza ripasso cala: tutto giusto 21 giorni fa vale la metà (50, «quasi»)",
         p[1]["valore"] == 50 and p[1]["parola"] == "quasi", p)
p = PD.calcola([t(1, G(1), tipo="giudizio_modello"), t(1, G(1), esito="forse"), t(1, G(0)),
                t(1, G(0)), t(None, G(0))], OGGI)
verifica("tipi ed esiti sconosciuti non contano (solo 2 tentativi validi)",
         p[1]["tentativi"] == 2 and p[1]["valore"] is None, p)
verifica("le parole alle soglie", PD.parola(75) == "la sai" and PD.parola(74) == "quasi"
         and PD.parola(45) == "quasi" and PD.parola(44) == "da studiare")
pad = {1: {"valore": 80}, 2: {"valore": 40}, 3: {"valore": None}}
verifica("il livello: la media dei misurati se lo è almeno metà",
         PD.livello([1, 2, 3], pad) == 60 and PD.livello([1, 3, 4, 5], pad) is None
         and PD.livello([], pad) is None)

# ═══════════════════════════ 2. le lacune ═══════════════════════════
print("— le lacune")
args = [{"id": 1, "numero": 1, "pagine": [10]}, {"id": 2, "numero": 3, "pagine": [11]},
        {"id": 3, "numero": 4, "pagine": [12]}, {"id": 4, "numero": 5, "pagine": [13]}]
pad = {1: {"valore": 90, "parola": "la sai"}, 2: {"valore": 60, "parola": "quasi"},
       3: {"valore": 30, "parola": "da studiare"}, 4: {"valore": None, "parola": "x"}}
giorni = [{"giorno": G(1), "fase": "studio", "pagine": [11], "fatto": None},
          {"giorno": G(-1), "fase": "studio", "pagine": [11], "attivita": "Leggi la pagina 11.",
           "fatto": None},
          {"giorno": G(-3), "fase": "ripasso", "pagine": [10, 11, 12, 13], "attivita": "Ripassa.",
           "fatto": None}]
lac = PD.lacune(args, pad, 75, giorni, OGGI)
verifica("sotto l'obiettivo, dal più debole; i misurati sopra e i non misurati fuori",
         [x["numero"] for x in lac] == [4, 3], lac)
verifica("la lezione successiva: il prossimo giorno di studio con le sue pagine, o il ripasso",
         lac[1]["lezione"]["giorno"] == G(-1) and lac[0]["lezione"]["fase"] == "ripasso", lac)

# ═══════════════════════════ 3. il servizio ═══════════════════════════
print("— il servizio, in ombra")
cfg = cfg_nuova("a.db")
st = studio(cfg)
vid, ids, aids = carica(st)
verifica("lo schema alla versione 6 (dal passo 6, #246), studio_tentativi fra le tabelle e nella conservazione",
         st.dati.uno("SELECT versione FROM meta_schema WHERE modulo='studio'")["versione"]
         == len(D.MIGRAZIONI) == 6 and "studio_tentativi" in D.TABELLE
         and set(TABELLE_STUDIO) == set(D.TABELLE))
pz = st.padronanza(LEO, vid)
verifica("senza tentativi: tutti «non ancora misurata», niente lacune né livello",
         all(a["parola"] == "non ancora misurata" for a in pz["argomenti"])
         and not pz["lacune"] and pz["livello"] is None and pz["modo"] == "ombra", pz)
verifica("tentativi non validi rifiutati (tipo, esito, la fonte «modello»)",
         solleva(lambda: st.registra_tentativo(LEO, vid, aids[0], "chat", "giusto"), ValueError)
         and solleva(lambda: st.registra_tentativo(LEO, vid, aids[0], "carta", "boh"), ValueError)
         and solleva(lambda: st.registra_tentativo(LEO, vid, aids[0], "carta", "giusto",
                                                   fonte="modello"), ValueError))
verifica("un altro adulto no, lo stesso «non c'è»",
         solleva(lambda: st.registra_tentativo(BRUNO, vid, aids[0], "carta", "giusto"),
                 S.NonTrovata) and solleva(lambda: st.padronanza(BRUNO, vid), S.NonTrovata))
vid_a, _, aids_a = carica(st, ANDREA)
verifica("l'argomento di un'altra verifica: non c'è",
         solleva(lambda: st.registra_tentativo(LEO, vid, aids_a[0], "carta", "giusto"),
                 S.NonTrovata))
# Leo: argomento 1 tutto giusto, argomento 2 tutto sbagliato, argomento 3 quasi; il tutore
# registra una carta controllata con lui
for g in (28, 29):
    ORA[0] = datetime.datetime(2026, 10, g, 17, 0)
    for _ in range(2):
        st.registra_tentativo(LEO, vid, aids[0], "carta", "giusto")
        st.registra_tentativo(LEO, vid, aids[1], "carta", "sbagliato")
        st.registra_tentativo(LEO, vid, aids[3], "esercizio", "giusto", fonte="codice")
        st.registra_tentativo(LEO, vid, aids[4], "carta", "giusto")
    st.registra_tentativo(LEO, vid, aids[2], "carta", "indizio")
st.registra_tentativo(ANDREA, vid, aids[2], "carta", "giusto", fonte="tutore")
pz = st.padronanza(LEO, vid)
per = {a["id"]: a for a in pz["argomenti"]}
verifica("le parole: 1 «la sai», 2 «da studiare», 3 «quasi»",
         per[aids[0]]["parola"] == "la sai" and per[aids[1]]["parola"] == "da studiare"
         and per[aids[2]]["parola"] == "quasi", per)
verifica("le lacune per numero: il 2 poi il 3, con la lezione dal piano",
         [x["numero"] for x in pz["lacune"]] == [2, 3]
         and all(x["lezione"] for x in pz["lacune"]), pz["lacune"])
verifica("il tutore la vede uguale", st.padronanza(ANDREA, vid) == pz)
m = st.dati.tutti("SELECT giorno, fonte FROM studio_misure WHERE verifica = ?", (vid,))
verifica("in ombra: la misura del giorno «padronanza_ombra» solo quando metà degli argomenti "
         "è misurata (il 29, non il 28), una per giorno",
         [x["giorno"] for x in m] == ["2026-10-29"]
         and {x["fonte"] for x in m} == {"padronanza_ombra"}, m)
pi = st.piano(LEO, vid)
verifica("in ombra la previsione e l'ultima prova le ignorano",
         pi["misure"] == 0 and pi["livello"] is None and pi["previsione"] is None, pi["misure"])
h = st.home(LEO)["verifiche"][0]
verifica("in ombra niente sulla home: nessuna parola sulle tappe, niente lacune",
         h["lacune"] is None and all("parola" not in x for x in h["tappe"]), h["tappe"][:2])
rp = st.riepilogo(LEO, vid)
verifica("in ombra niente nel riepilogo", "sotto l'obiettivo" not in rp["frase"], rp["frase"])
titoli = [a["titolo"] for a in MAT["argomenti"]]
righe = [x for x in registro if "padronanza" in x]
verifica("il registro: solo i conti, senza titoli né nomi",
         righe and all(not any(tt in x for tt in titoli) and "Leo" not in x for x in righe)
         and "la sai 3" in righe[-1], righe[-1:] if righe else registro[-3:])
verifica("Studio.stato(): i conti della padronanza",
         st.stato()["padronanza"]["tentativi"] == 19
         and st.stato()["padronanza"]["parole"].get("la sai") == 3, st.stato()["padronanza"])
st.close()
st = studio(cfg)
verifica("riaperto il db: la stessa padronanza", st.padronanza(LEO, vid) == pz)
st.close()

# ═══════════════════════════ 4. mostrata ═══════════════════════════
print("— mostrata")
ORA[0] = datetime.datetime(2026, 10, 28, 16, 0)
cfg2 = cfg_nuova("b.db", "mostrata")
st2 = studio(cfg2)
vid2, _, aids2 = carica(st2)
for g in (28, 29, 30, 31):
    ORA[0] = datetime.datetime(2026, 10, g, 17, 0)
    for _ in range(2):
        st2.registra_tentativo(LEO, vid2, aids2[0], "carta", "giusto")
        st2.registra_tentativo(LEO, vid2, aids2[1], "carta", "sbagliato")
        st2.registra_tentativo(LEO, vid2, aids2[2], "carta", "indizio")
        st2.registra_tentativo(LEO, vid2, aids2[3], "carta", "giusto")
        st2.registra_tentativo(LEO, vid2, aids2[4], "carta", "giusto")
        st2.registra_tentativo(LEO, vid2, aids2[5], "carta", "giusto")
pi = st2.piano(LEO, vid2)
verifica("mostrata: tre misure (dal secondo giorno), la previsione dalla padronanza (forbice); "
         "«l'ultima prova» no: non è una prova (#246, nota 5)",
         pi["misure"] == 3 and pi["previsione"] is not None and pi["livello"] is None, pi)
h = st2.home(LEO)["verifiche"][0]
par = [x.get("parola") for x in h["tappe"]]
verifica("la parola sulle tappe", "la sai" in par and "da studiare" in par and "quasi" in par,
         par)
verifica("le lacune sulla home col titolo e la lezione (textContent)",
         [x["titolo"] for x in h["lacune"]] == [MAT["argomenti"][1]["titolo"],
                                                MAT["argomenti"][2]["titolo"]]
         and all(x["lezione"] for x in h["lacune"]), h["lacune"])
rp = st2.riepilogo(LEO, vid2)
verifica("il riepilogo: le lacune per numero, mai col titolo",
         "sotto l'obiettivo gli argomenti 2 e 3." in rp["frase"]
         and not any(tt in rp["frase"] for tt in titoli), rp["frase"])
st2.imposta_sessione(LEO, vid2, conoscenza=1, umore="stressato")
tutto = " ".join(str(v) for tb in D.TABELLE for row in st2.dati.tutti(f"SELECT * FROM {tb}")
                 for v in row.values())
verifica("lo stato d'animo e la conoscenza in nessuna tabella",
         "stressato" not in tutto and "è nuovo per me" not in tutto)
st2.close()
cfg3 = cfg_nuova("c.db", "spenta")
st3 = studio(cfg3)
vid3, _, aids3 = carica(st3)
verifica("spenta: il tentativo è rifiutato",
         solleva(lambda: st3.registra_tentativo(LEO, vid3, aids3[0], "carta", "giusto"),
                 ValueError))
st3.close()

# ═══════════════════════════ 5. tenuta ═══════════════════════════
print("— tenuta")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st4 = studio(cfg_nuova("d.db"))
vA, _, aA = carica(st4)
vB, _, aB = carica(st4, ANDREA)
vC, _, aC = carica(st4)
for v, a, chi in ((vA, aA, LEO), (vB, aB, ANDREA), (vC, aC, LEO)):
    st4.registra_tentativo(chi, v, a[0], "carta", "giusto")


def n_tent(v):
    return st4.dati.uno("SELECT COUNT(*) AS n FROM studio_tentativi WHERE verifica = ?",
                        (v,))["n"]


st4.togli_verifica(LEO, vC)
verifica("la verifica tolta: via i suoi tentativi", n_tent(vC) == 0 and n_tent(vA) == 1)
st4.archivia(LEO, vA)
for g in ("2026-10-01", "2027-03-01"):
    st4.dati.scrivi("INSERT INTO studio_tentativi (verifica, persona, argomento, giorno, ora, "
                    "tipo, esito, fonte) VALUES (999, 'l1', 1, ?, ?, 'carta', 'giusto', "
                    "'persona')", (g, g + "T10:00:00"))
D.cancella(st4.dati.db, scadute_prima=datetime.date(2027, 1, 30))
orf = [x["giorno"] for x in st4.dati.tutti("SELECT giorno FROM studio_tentativi WHERE "
                                           "verifica = 999")]
verifica("la rotazione: via la verifica scaduta e l'orfano vecchio, l'archiviata resta",
         n_tent(vB) == 0 and n_tent(vA) == 1 and orf == ["2027-03-01"], orf)
D.cancella(st4.dati.db, persona="l1", archiviate=False)
verifica("«dimentica»: via gli orfani della persona, l'archiviata resta",
         n_tent(999) == 0 and n_tent(vA) == 1)
D.cancella(st4.dati.db, tutto=True)
verifica("«svuota»: nessun tentativo",
         st4.dati.uno("SELECT COUNT(*) AS n FROM studio_tentativi")["n"] == 0)
st4.close()

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
