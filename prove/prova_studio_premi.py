import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""I premi dello Studio a secco (31/10, issue #296, epic #251, decisione 0035 punto 45;
`calliope/studio/premi.py`, `tools/studio.py`, `schermi/server.py`), con `manuali/studio/storia.json`
e un orologio finto. Persone di fantasia: Andrea tutore di Leo e di Sofia, Bruno adulto, Carla
amministra, un conoscente; Leo e Sofia minori di casa.

1. **Schema**: «studio» alla versione 12, `studio_stelle`, `studio_premi`, `studio_duelli` in
   `TABELLE` e `conserva.TABELLE_STUDIO`.
2. **Funzioni pure**: il giorno di studio (soglie), la serie con le pause, i giorni senza piano,
   oggi che aspetta, i giorni dopo oggi che non contano; la prova superata coi soli esiti del
   codice e del tutore; le frasi.
3. **La serie dai dati, con gli imbrogli**: una sessione aperta e chiusa subito, «Fatto» senza
   «Inizia», la pausa in mezzo; la stessa carta ripetuta, le carte del tutore; l'esito delle carte
   (autovalutazione) che non cambia niente; l'orologio spostato avanti e indietro; le pause, il
   giorno saltato, i giorni senza piano.
4. **Le stelle**: la verifica finta superata dal codice (una volta sola anche ripetendola), quella
   «superata» solo con le autovalutazioni (no) e con il tutore (sì); il ripasso delle carte in due
   giorni; l'argomento all'obiettivo solo con la padronanza mostrata e coi soli esiti del codice;
   il piano seguito; dette una volta.
5. **Interruttori e permessi**: in ombra niente; il tutore spegne le stelle di Leo, Leo no; un
   adulto le sue; Bruno quelle di Leo no.
6. **Duelli**: spenti di serie; per un minore solo col tutore; mai con un conoscente, con sé
   stessi o con chi li ha spenti; senza il consenso di chi riceve niente risposte; le risposte
   attese solo a duello finito; con una prova aperta il duello aspetta; nessun tentativo né
   stella; scadenza; spenti dal tutore → annullati; tenuta.
7. **Tool**: «premi» per sé e per il tutore (terza persona), mai per un altro adulto; «fatto» con
   la serie una volta al giorno; politica.
8. **Attraverso Brain**: «ho finito» detto da Leo → la frase della serie nella voce, una volta;
   «quante stelle ho?»; niente titoli né testo nelle frasi.
9. **Gli endpoint** `/api/studio/premi` e `/api/studio/duello`.
"""

import contextlib
import datetime
import io
import json
import tempfile
import types
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import politica  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.studio import dati as D  # noqa: E402
from calliope.studio import padronanza as PD  # noqa: E402
from calliope.studio import premi as PM  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                else ""))


def solleva(f, tipo=Exception) -> bool:
    try:
        f()
    except tipo:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None, tutori=(), tipo=None):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, tipo
        self.level = "amministra" if admin else "familiare"
        self.gender, self.preferred_voice, self.giovane, self.young, self.tono = (
            "m", None, False, False, None)


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


ANDREA = Prof("a1", "Andrea")
BRUNO = Prof("b1", "Bruno")
CARLA = Prof("c1", "Carla", admin=True)
LEO = Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
SOFIA = Prof("s1", "Sofia", nascita="2016-05-01", tutori=["a1"])
CONO = Prof("k1", "Ugo", tipo="conoscente")
REG = Registro(ANDREA, BRUNO, CARLA, LEO, SOFIA, CONO)
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-premi-"))
ORA = [datetime.datetime(2026, 10, 29, 16, 0)]          # giovedì 29/10
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
righe_log: list = []


def ora(giorno, h=16, m=0):
    ORA[0] = datetime.datetime(2026, 10, giorno, h, m) if giorno > 10 else \
        datetime.datetime(2026, 11, giorno, h, m)


def cfg_nuova(nome, modo="attivo", **kw):
    c = Config()
    c.memory_db = str(TMP / nome)
    c.studio_modo = modo
    c.studio_cartella = str(TMP / "studio")
    c.turn_log_dir = str(TMP / "registro")
    c.studio_lettura = False
    c.studio_giorni_senza_piano = []
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def studio(cfg):
    st = S.Studio(cfg, registry=REG, log=righe_log.append, adesso=lambda: ORA[0])
    st.avvia_lettura(None, avvia=False)
    return st


def carica(st, chi=LEO, persona=None):
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
    st.conferma_argomenti(chi, vid)
    return vid


def sessione(st, vid, minuti, chi=LEO):
    """«Inizia» adesso e «Fatto» dopo `minuti`, lo stesso giorno."""
    inizio = ORA[0]
    st.imposta_sessione(chi, vid, 3, None)
    ORA[0] = inizio + datetime.timedelta(minutes=minuti)
    st.giorno_fatto(chi, vid)
    ORA[0] = inizio


def serie(st, persona="l1") -> dict:
    return st._serie_di(persona)


TITOLI = [a["titolo"] for a in MAT["argomenti"]]

# ═══════════════════════════ 1. schema ═══════════════════════════
print("— schema")
st = studio(cfg_nuova("schema.db"))
from calliope.conserva import TABELLE_STUDIO  # noqa: E402
verifica("schema «studio» alla versione 12", D.versione_schema(st.dati.db) == 12
         and len(D.MIGRAZIONI) == 12)
verifica("le tabelle dei premi in TABELLE e in conserva.TABELLE_STUDIO",
         {"studio_stelle", "studio_premi", "studio_duelli"} <= set(D.TABELLE)
         and set(TABELLE_STUDIO) == set(D.TABELLE))
st.close()

# ═══════════════════════════ 2. funzioni pure ═══════════════════════════
print("— funzioni pure")
verifica("giorno di studio: 10 minuti misurati sì, 9 no",
         PM.studiato({"minuti": 10}) and not PM.studiato({"minuti": 9}))
verifica("giorno di studio: 5 carte diverse sì, 4 no",
         PM.studiato({"carte": {1, 2, 3, 4, 5}}) and not PM.studiato({"carte": {1, 2, 3, 4}}))
verifica("giorno di studio: una prova sì, 3 caselle sì, 2 no",
         PM.studiato({"prove": 1}) and PM.studiato({"caselle": 3})
         and not PM.studiato({"caselle": 2}))
OGGI = datetime.date(2026, 11, 20)


def g(n):
    return (OGGI - datetime.timedelta(days=n)).isoformat()


si = {"minuti": 20}
pr = {g(0): si, g(1): si, g(2): si}
verifica("tre giorni di fila: 3", PM.serie(pr, {g(0), g(1), g(2)}, OGGI)["giorni"] == 3)
pr = {g(1): si, g(2): si}
s_ = PM.serie(pr, {g(0), g(1), g(2)}, OGGI)
verifica("oggi non ancora studiato aspetta: 2, e «oggi» falso", s_["giorni"] == 2 and not s_["oggi"])
pr = {g(0): si, g(2): si, g(3): si}
s_ = PM.serie(pr, {g(0), g(1), g(2), g(3)}, OGGI, pause=1)
verifica("un giorno del piano senza pratica usa la pausa: 3, una pausa",
         s_["giorni"] == 3 and s_["pause"] == [g(1)], str(s_))
verifica("senza pause lo stesso buco ferma la serie: 1",
         PM.serie(pr, {g(0), g(1), g(2), g(3)}, OGGI, pause=0)["giorni"] == 1)
pr = {g(0): si, g(2): si, g(4): si}
verifica("due buchi nella stessa settimana con una pausa: si ferma al secondo (2)",
         PM.serie(pr, {g(i) for i in range(5)}, OGGI, pause=1)["giorni"] == 2)
pr = {g(0): si, g(2): si, g(9): si, g(11): si}
verifica("due buchi in settimane diverse: 4",
         PM.serie(pr, {g(i) for i in range(12)} - {g(i) for i in (3, 4, 5, 6, 7, 8, 10)} | {g(1),
                                                                                          g(10)},
                  OGGI, pause=1)["giorni"] == 4)
pr = {g(0): si, g(5): si}
verifica("i giorni senza piano non contano e non fermano: 2",
         PM.serie(pr, {g(0), g(5)}, OGGI)["giorni"] == 2)
verifica("un giorno dopo oggi (orologio) non conta",
         PM.serie({(OGGI + datetime.timedelta(days=1)).isoformat(): si}, set(), OGGI)["giorni"] == 0)
verifica("senza pratica: 0", PM.serie({}, {g(1)}, OGGI)["giorni"] == 0)
voci = [{"esito": "giusto", "fonte_esito": "codice"}] * 3 + [{"esito": "giusto",
                                                               "fonte_esito": "persona"}]
verifica("superata: le autovalutate valgono 0 (3 su 4 = 75 %, obiettivo 75 sì, 80 no)",
         PM.superata(voci, 75) and not PM.superata(voci, 80))
verifica("superata: meno di 3 domande no", not PM.superata(voci[:2], 10))
verifica("le frasi: «La tua serie è a 1 giorno di studio.», al tutore col nome",
         PM.frase_serie(1) == "La tua serie è a 1 giorno di studio."
         and PM.frase_serie(4, "Leo") == "La serie di Leo è a 4 giorni di studio.")
verifica("la frase delle stelle nuove: numero, mai titolo",
         PM.frase_stelle_nuove([{"tipo": "argomento", "numero": 3}])
         == "Hai una stella nuova: l'argomento 3 all'obiettivo.")

# ═══════════════════════════ 3. la serie dai dati ═══════════════════════════
print("— la serie dai dati, con gli imbrogli")
ora(29)
st = studio(cfg_nuova("serie.db"))
v = carica(st)
sessione(st, v, 1)
verifica("una sessione aperta e chiusa in un minuto: non conta", serie(st)["giorni"] == 0,
         str(serie(st)))
st.giorno_fatto(LEO, v, fatto=False)
ORA[0] = datetime.datetime(2026, 10, 29, 17, 0)
st.giorno_fatto(LEO, v)
verifica("«Fatto» senza un «Inizia» nuovo (il tempo non è misurato): non conta",
         serie(st)["giorni"] == 0, str(serie(st)))
st.giorno_fatto(LEO, v, fatto=False)
st.dimentica_sessione("l1")
ORA[0] = datetime.datetime(2026, 10, 29, 17, 10)
sessione(st, v, 25)
verifica("una sessione nuova di 25 minuti misurata: la serie è a 1", serie(st)["giorni"] == 1
         and serie(st)["oggi"], str(serie(st)))
st.close()

# Le carte: la stessa ripetuta, quelle del tutore, l'esito che non conta
ora(29)
st = studio(cfg_nuova("carte.db"))
v = carica(st)
args = st._argomenti_numerati(v)
carte = [st.aggiungi_carta(LEO, v, f"Domanda {i}?", f"risposta {i}", argomento=args[i]["id"])
         for i in range(6)]
for _ in range(10):
    st.esito_carta(LEO, carte[0], "sapevo")
verifica("la stessa carta ripetuta dieci volte: non fa un giorno", serie(st)["giorni"] == 0)
for c in carte[1:4]:
    st.esito_carta(ANDREA, c, "sapevo")
verifica("le carte ripassate dal tutore non sono la pratica di Leo", serie(st)["giorni"] == 0)
for c in carte[1:5]:
    st.esito_carta(LEO, c, "non_sapevo")
verifica("cinque carte diverse, tutte «non la sapevo»: il giorno conta",
         serie(st)["giorni"] == 1, str(serie(st)))
st.close()

# L'orologio
ora(29)
st = studio(cfg_nuova("orologio.db"))
v = carica(st)
args = st._argomenti_numerati(v)
carte = [st.aggiungi_carta(LEO, v, f"Domanda {i}?", f"risposta {i}", argomento=args[i]["id"])
         for i in range(5)]
ORA[0] = datetime.datetime(2026, 11, 2, 16, 0)
sessione(st, v, 30)
for c in carte:
    st.esito_carta(LEO, c, "quasi")
ora(29)
verifica("una sessione e cinque carte con l'orologio avanti: tornati a oggi non contano",
         serie(st)["giorni"] == 0, str(serie(st)))
for c in carte:
    st.esito_carta(LEO, c, "quasi")
verifica("la frase della serie si dice", "La tua serie è a 1 giorno" in st.frase_premi(LEO))
verifica("una seconda volta lo stesso giorno no", "serie" not in st.frase_premi(LEO))
ORA[0] = datetime.datetime(2026, 10, 28, 16, 0)
verifica("con l'orologio indietro di un giorno non si ripete", "serie" not in st.frase_premi(LEO))
st.close()

# Pause, giorni saltati e senza piano: Leo studia il 29, il 30, salta il 31, studia il 2/11
ora(29)
st = studio(cfg_nuova("pause.db"))
v = carica(st)
sessione(st, v, 20)
ora(30)
sessione(st, v, 20)
ora(31)
st.salta_oggi(LEO)
for gg in (1, 2):
    ora(gg)
    sessione(st, v, 20)
s_ = serie(st)
verifica("un giorno saltato con «non ce la faccio oggi» usa la pausa: la serie continua (4)",
         s_["giorni"] == 4 and s_["pause"] == ["2026-10-31"], str(s_))
ora(3)
st.salta_oggi(LEO)
ora(4)
sessione(st, v, 20)
s_ = serie(st)
verifica("un secondo giorno saltato nella stessa settimana: la serie riparte dopo il primo (3)",
         s_["giorni"] == 3 and s_["dal"] == "2026-11-01", str(s_))
detto = st.frase_premi(LEO)
verifica("quando la serie riparte la frase non parla di perdite",
         "pers" not in detto.lower() and "azzer" not in detto.lower(), detto)
st.close()

# ═══════════════════════════ 4. le stelle ═══════════════════════════
print("— le stelle")
ora(29)
st = studio(cfg_nuova("stelle.db"))
v = carica(st)
args = st._argomenti_numerati(v)
for i in range(4):
    st.aggiungi_domanda(LEO, v, "numero", f"In che anno {i}?", str(1490 + i),
                        argomento=args[i]["id"])
p = st.inizia_prova(LEO, v)
for x in p["voci"]:
    st.rispondi_prova(LEO, p["id"], x["n"], str(1490 + int(x["testo"].split()[-1][:-1])))
st.consegna_prova(LEO, p["id"])
nuove = st.aggiorna_stelle("l1")
verifica("la verifica finta superata dal codice: una stella «prova_scritta»",
         [s["tipo"] for s in nuove] == ["prova_scritta"], str(nuove))
p = st.inizia_prova(LEO, v)
for x in p["voci"]:
    st.rispondi_prova(LEO, p["id"], x["n"], str(1490 + int(x["testo"].split()[-1][:-1])))
st.consegna_prova(LEO, p["id"])
verifica("rifatta e superata di nuovo: nessuna stella in più", st.aggiorna_stelle("l1") == []
         and len(st._stelle("l1")) == 1)
detto = st.frase_premi(LEO)
verifica("la stella nuova si dice una volta, senza titoli",
         "verifica finta superata" in detto and not any(t in detto for t in TITOLI), detto)
verifica("e non si ridice", "stella" not in st.frase_premi(LEO))
st.close()

# Le autovalutazioni non fanno stelle; il tutore sì
ora(29)
st = studio(cfg_nuova("stelle_auto.db"))
v = carica(st)
args = st._argomenti_numerati(v)
for i in range(3):
    st.aggiungi_domanda(LEO, v, "aperta", f"Perché {i}?", f"perché {i}", argomento=args[i]["id"])
p = st.inizia_prova(LEO, v)
for x in p["voci"]:
    st.rispondi_prova(LEO, p["id"], x["n"], "una risposta")
st.consegna_prova(LEO, p["id"])
for x in p["voci"]:
    st.rivedi_voce(LEO, p["id"], x["n"], "giusto")
verifica("tutto «Era giusta» deciso da Leo: nessuna stella", st.aggiorna_stelle("l1") == [])
p = st.inizia_prova(LEO, v)
for x in p["voci"]:
    st.rispondi_prova(LEO, p["id"], x["n"], "una risposta")
st.consegna_prova(LEO, p["id"])
for x in p["voci"]:
    st.rivedi_da_tutore(ANDREA, v, p["id"], x["n"], "giusto")
st.aggiorna_stelle("l1")
verifica("«Era giusta» deciso dal tutore: la stella (data già dalla vista del tutore)",
         [s["tipo"] for s in st._stelle("l1")] == ["prova_scritta"])
st.close()

# Il ripasso delle carte in due giorni; l'argomento all'obiettivo con la padronanza mostrata
ora(29)
st = studio(cfg_nuova("stelle_carte.db", studio_padronanza="mostrata"))
v = carica(st)
args = st._argomenti_numerati(v)
carte = [st.aggiungi_carta(LEO, v, f"Anno {i}?", str(1500 + i), argomento=args[0]["id"])
         for i in range(5)]
for c in carte:
    st.esito_carta(LEO, c, "sapevo")
verifica("le carte in un giorno solo: niente stella del ripasso",
         "ripasso" not in {s["tipo"] for s in st.aggiorna_stelle("l1")})
verifica("cinque carte «la sapevo» (autovalutazione): niente stella dell'argomento",
         not st.aggiorna_stelle("l1"))
ora(30)
for c in carte:
    st.esito_carta(LEO, c, "sapevo")
verifica("in un secondo giorno: la stella del ripasso",
         [s["tipo"] for s in st.aggiorna_stelle("l1")] == ["ripasso"])
for gg in (30, 31, 2):
    ora(gg)
    for c in carte:
        st.esito_carta(LEO, c, "sapevo", fonte="codice")
nuove = st.aggiorna_stelle("l1")
verifica("le risposte giuste decise dal codice in più giorni: la stella dell'argomento 1",
         [(s["tipo"], s["chiave"]) for s in nuove] == [("argomento", str(args[0]["id"]))],
         str(nuove))
verifica("l'argomento detto col numero, mai col titolo",
         st._stelle("l1")[-1]["nome"] == "l'argomento 1 all'obiettivo")
st.close()
ora(29)
st = studio(cfg_nuova("stelle_ombra_pad.db"))
v = carica(st)
args = st._argomenti_numerati(v)
carte = [st.aggiungi_carta(LEO, v, f"Anno {i}?", str(1500 + i), argomento=args[0]["id"])
         for i in range(3)]
for gg in (29, 30, 31):
    ora(gg)
    for c in carte:
        st.esito_carta(LEO, c, "sapevo", fonte="codice")
verifica("con la padronanza in ombra niente stella dell'argomento (non si rivela la cifra)",
         "argomento" not in {s["tipo"] for s in st.aggiorna_stelle("l1")})
st.close()

# Il piano seguito: sessioni misurate nei giorni del piano, poi la data della verifica
ora(29)
st = studio(cfg_nuova("piano.db"))
v = carica(st)
giorni_piano = [r["giorno"] for r in st.dati.tutti("SELECT giorno FROM studio_piano WHERE "
                                                   "verifica = ? AND minuti > 0", (v,))]
for gg in giorni_piano:
    d = datetime.date.fromisoformat(gg)
    ORA[0] = datetime.datetime(d.year, d.month, d.day, 16, 0)
    sessione(st, v, 20)
verifica("prima della data niente stella del piano",
         "piano" not in {s["tipo"] for s in st.aggiorna_stelle("l1")})
ORA[0] = datetime.datetime(2026, 11, 5, 9, 0)
verifica(f"alla data, coi {len(giorni_piano)} giorni del piano fatti e misurati: la stella",
         "piano" in {s["tipo"] for s in st.aggiorna_stelle("l1")}, str(giorni_piano))
st.close()
ora(29)
st = studio(cfg_nuova("piano_vuoto.db"))
v = carica(st)
for gg in giorni_piano:
    d = datetime.date.fromisoformat(gg)
    ORA[0] = datetime.datetime(d.year, d.month, d.day, 16, 0)
    st.giorno_fatto(LEO, v)
ORA[0] = datetime.datetime(2026, 11, 5, 9, 0)
verifica("«Fatto» ogni giorno senza sessioni misurate: niente stella del piano",
         "piano" not in {s["tipo"] for s in st.aggiorna_stelle("l1")})
st.close()

# ═══════════════════════════ 5. interruttori e permessi ═══════════════════════════
print("— interruttori e permessi")
ora(29)
st = studio(cfg_nuova("ombra.db", modo="ombra"))
v = carica(st)
sessione(st, v, 20)
p = st.premi(LEO)
verifica("in ombra niente premi (né serie né stelle) e nessuna frase",
         not p["acceso"] and p["serie"] is None and st.frase_premi(LEO) == "")
st.close()
st = studio(cfg_nuova("interruttori.db"))
v = carica(st)
verifica("di serie per Leo: serie e stelle sì, duelli no",
         {k: st.impostazioni_premi("l1")["scelte"][k] for k in PM.CHIAVI}
         == {"serie": True, "stelle": True, "duelli": False})
verifica("Leo non cambia i suoi premi", solleva(lambda: st.imposta_premi(LEO, "l1", stelle=False),
                                                S.NonPermesso))
verifica("Bruno non cambia quelli di Leo", solleva(
    lambda: st.imposta_premi(BRUNO, "l1", stelle=False), (S.NonPermesso, S.NonTrovata)))
imp = st.imposta_premi(ANDREA, "l1", stelle=False)
verifica("il tutore spegne le stelle di Leo", imp["stelle"] is False and imp["serie"] is True)
sessione(st, v, 20)
verifica("con le stelle spente: nessuna stella e nessun conto", st.premi(LEO)["stelle"] is None
         and st.aggiorna_stelle("l1") == [])
imp = st.imposta_premi(BRUNO, "b1", serie=False)
verifica("un adulto spegne la sua serie", imp["serie"] is False)
verifica("Andrea non cambia quelli di Bruno",
         solleva(lambda: st.imposta_premi(ANDREA, "b1", serie=True), (S.NonPermesso, S.NonTrovata)))
verifica("il registro dei premi senza nomi", not any("Leo" in r or "Bruno" in r for r in righe_log
                                                     if "premi" in r))
st.close()

# ═══════════════════════════ 6. duelli ═══════════════════════════
print("— duelli")
ora(29)
st = studio(cfg_nuova("duelli_spenti.db"))
v = carica(st)
verifica("duelli spenti nell'installazione: niente proposta",
         solleva(lambda: st.proponi_duello(LEO, v, "b1"), ValueError)
         and st.persone_per_duello(BRUNO) == [])
st.close()
st = studio(cfg_nuova("duelli.db", studio_duelli=True))
v = carica(st)
args = st._argomenti_numerati(v)
for i in range(5):
    st.aggiungi_domanda(LEO, v, "numero", f"In che anno {i}?", str(1490 + i),
                        argomento=args[i]["id"])
st.aggiungi_domanda(LEO, v, "aperta", "Perché?", "Per il commercio", argomento=args[0]["id"])
verifica("Leo senza il tutore: i duelli non sono accesi",
         solleva(lambda: st.proponi_duello(LEO, v, "b1"), ValueError))
st.imposta_premi(ANDREA, "l1", duelli=True)
persone = {x["id"] for x in st.persone_per_duello(LEO)}
verifica("le persone per un duello: gli adulti di casa, non Sofia (spenti), non il conoscente",
         persone == {"a1", "b1", "c1"}, str(persone))
for a, perche in (("k1", "un conoscente"), ("l1", "sé stesso"), ("s1", "Sofia coi duelli spenti"),
                  ("zz", "una persona che non c'è")):
    verifica(f"duello con {perche}: rifiutato",
             solleva(lambda a=a: st.proponi_duello(LEO, v, a), (S.NonTrovata, ValueError)))
verifica("il duello lo propone chi studia, non il tutore sulla verifica di Leo",
         solleva(lambda: st.proponi_duello(ANDREA, v, "b1"), (S.NonPermesso, S.NonTrovata)))
did = st.proponi_duello(LEO, v, "b1")
d = st.vista_duello(BRUNO, did)
verifica("la proposta: Bruno la vede con chi, senza domande", d["stato"] == "proposto"
         and d["con"] == "Leo" and d["puo_accettare"] and d["voci"] == [])
verifica("un terzo non la vede (lo stesso «non c'è»)",
         solleva(lambda: st.vista_duello(CARLA, did), S.NonTrovata)
         and solleva(lambda: st.vista_duello(ANDREA, did), S.NonTrovata))
verifica("senza il consenso di Bruno nessuno risponde",
         solleva(lambda: st.rispondi_duello(LEO, did, 1, "1490"), ValueError)
         and solleva(lambda: st.rispondi_duello(BRUNO, did, 1, "1490"), ValueError))
verifica("Leo non accetta al posto di Bruno", solleva(lambda: st.accetta_duello(LEO, did),
                                                      S.NonTrovata))
d = st.accetta_duello(BRUNO, did)
verifica("Bruno accetta: le domande del codice (mai le aperte), senza risposte attese",
         d["stato"] == "in_corso" and len(d["voci"]) == 5
         and all(x["tipo"] != "aperta" for x in d["voci"])
         and "attesa" not in json.dumps(d["voci"]) and "esito" not in json.dumps(d["voci"]))
for x in d["voci"]:
    st.rispondi_duello(BRUNO, did, x["n"], str(1490 + int(x["testo"].split()[-1][:-1])))
dl = st.vista_duello(LEO, did)
for k, x in enumerate(dl["voci"]):
    st.rispondi_duello(LEO, did, x["n"], "1490" if k == 0 else "1300")
d = st.consegna_duello(BRUNO, did)
verifica("Bruno consegna: le sue risposte restano senza esito finché Leo non consegna",
         d["consegnato"] and "esito" not in json.dumps(d["voci"]) and "punti" not in d)
verifica("dopo la consegna Bruno non cambia le risposte",
         solleva(lambda: st.rispondi_duello(BRUNO, did, 1, "0"), ValueError))
tent_prima = len(st.dati.tutti("SELECT id FROM studio_tentativi"))
d = st.consegna_duello(LEO, did)
verifica("finito: i punti di tutti e due e le risposte attese",
         d["stato"] == "finito" and d["punti"]["altro"] == 5 and d["punti"]["io"] in (0, 1)
         and all(x.get("attesa") for x in d["voci"]), json.dumps(d)[:300])
verifica("il duello non scrive tentativi e non dà stelle",
         len(st.dati.tutti("SELECT id FROM studio_tentativi")) == tent_prima
         and not st.dati.tutti("SELECT id FROM studio_stelle WHERE tipo LIKE 'duel%'"))
verifica("nessuna parola «vinto» o «perso» nei dati del duello",
         "vint" not in json.dumps(d) and "pers" not in json.dumps(d))
# Una prova aperta: il duello aspetta (nessuna strada laterale per le domande)
did2 = st.proponi_duello(LEO, v, "a1")
st.accetta_duello(ANDREA, did2)
pv = st.inizia_prova(LEO, v)
d2 = st.vista_duello(ANDREA, did2)
verifica("con la prova di Leo aperta: il duello senza domande per tutti e due",
         d2["voci"] == [] and d2["in_attesa_prova"] and st.vista_duello(LEO, did2)["voci"] == [])
verifica("con la prova aperta niente risposte né consegna",
         solleva(lambda: st.rispondi_duello(ANDREA, did2, 1, "1490"), ValueError)
         and solleva(lambda: st.consegna_duello(ANDREA, did2), ValueError))
verifica("con la prova aperta niente duelli nuovi",
         solleva(lambda: st.proponi_duello(LEO, v, "c1"), ValueError))
st.consegna_prova(LEO, pv["id"])
verifica("dopo la consegna il duello riprende", st.vista_duello(ANDREA, did2)["voci"] != [])
# Una mappa da zero aperta e una carta nata dalla mappa nel duello: aspetta anche lui (lo
# scheletro è nascosto da tutte le strade, decisione 0035 punto 38)
cm = st.aggiungi_carta(LEO, v, "Mappa di storia: cosa scoprì?", "America", argomento=args[0]["id"])
st.dati.scrivi("UPDATE studio_carte SET origine = 'mappa' WHERE id = ?", (cm,))
r2 = st.dati.uno("SELECT voci FROM studio_duelli WHERE id = ?", (did2,))
vv = json.loads(r2["voci"])
vv[0].update(fonte="carta", id=cm)
st.dati.scrivi("UPDATE studio_duelli SET voci = ? WHERE id = ?", (json.dumps(vv), did2))
mid_ = st.dati.scrivi("INSERT INTO studio_mappe (verifica, persona, tipo, stato, creata) VALUES "
                      "(?, 'l1', 'libera', 'aperta', '2026-10-29T16:00:00')", (v,))
verifica("con la mappa da zero aperta e una sua carta nel duello: niente domande, niente risposte",
         st.vista_duello(ANDREA, did2)["voci"] == []
         and solleva(lambda: st.rispondi_duello(ANDREA, did2, 1, "x"), ValueError))
st.dati.scrivi("DELETE FROM studio_mappe WHERE id = ?", (mid_,))
verifica("finita la mappa il duello riprende", st.vista_duello(ANDREA, did2)["voci"] != [])
# Il tutore spegne i duelli di Leo: quelli aperti si annullano
st.imposta_premi(ANDREA, "l1", duelli=False)
verifica("il tutore spegne i duelli: quello aperto è annullato",
         st.vista_duello(ANDREA, did2)["stato"] == "annullato")
verifica("e non se ne propongono", solleva(lambda: st.proponi_duello(LEO, v, "b1"), ValueError))
st.imposta_premi(ANDREA, "l1", duelli=True)
# La scadenza
did3 = st.proponi_duello(LEO, v, "c1")
ORA[0] = ORA[0] + datetime.timedelta(hours=PM.DUELLO_ORE + 1)
verifica("una proposta senza risposta per un giorno: scaduta",
         st.vista_duello(CARLA, did3)["stato"] == "scaduto")
# Il tutore vede i duelli di Leo, senza domande
vt = st.vista_tutore(ANDREA, v)
dt = (vt.get("premi") or {}).get("duelli") or []
verifica("nella vista del tutore i duelli di Leo: con chi, stato e punti, mai le domande",
         dt and all("voci" not in x for x in dt) and "In che anno" not in json.dumps(vt["premi"]))
verifica("nel registro dei duelli solo id e stati",
         not any("In che anno" in r or "Bruno" in r for r in righe_log if "duello" in r))
# La tenuta: «dimentica» di Bruno toglie i suoi duelli; «svuota» tutto
D.cancella(st.dati.db, persona="b1", archiviate=False)
verifica("«dimentica» di Bruno: via i duelli con lui",
         not st.dati.tutti("SELECT id FROM studio_duelli WHERE da = 'b1' OR a = 'b1'"))
st.togli_verifica(LEO, v)
verifica("via la verifica, via i suoi duelli e le sue stelle",
         not st.dati.tutti("SELECT id FROM studio_duelli")
         and not st.dati.tutti("SELECT id FROM studio_stelle"))
st.imposta_premi(ANDREA, "l1", serie=False)
D.cancella(st.dati.db, tutto=True)
verifica("«svuota»: via anche gli interruttori", not st.dati.tutti("SELECT * FROM studio_premi"))
st.close()

# ═══════════════════════════ 7. tool ═══════════════════════════
print("— tool")
TOOLS = ToolRegistry()
for spec in TS.studio_specs():
    TOOLS.register(spec)


def ctx_di(st_, prof, come="voce", frase=""):
    sc = types.SimpleNamespace(current_speaker=prof.name if prof else None, identified_by=come,
                               minore_incerto=None, current_level=(prof.level if prof else "ospite"),
                               profile_level=prof.level if prof else "ospite")
    ctx = ToolContext(cfg=st_.cfg, speakers=REG, speaker_ctx=sc, speaker=None)
    ctx.studio = st_
    ctx.user_text = frase
    return ctx


def chiama(ctx, **a) -> dict:
    return json.loads(TOOLS.call("studio", a, ctx, "familiare"))


ora(29)
st = studio(cfg_nuova("tool.db"))
v = carica(st)
r = chiama(ctx_di(st, LEO, frase="quante stelle ho?"), azione="premi")
verifica("«premi» prima della pratica: la frase che invita, senza perdite", r["ok"]
         and "comincia con la prossima sessione" in r["conferma"], str(r))
st.imposta_sessione(LEO, v, 3, None)
ORA[0] = datetime.datetime(2026, 10, 29, 16, 30)
r = chiama(ctx_di(st, LEO, frase="ho finito, segna fatto"), azione="fatto", verifica=v)
verifica("«fatto» dopo 30 minuti: il resoconto e la serie", r["ok"]
         and "La tua serie è a 1 giorno di studio." in r["conferma"], r["conferma"])
ORA[0] = datetime.datetime(2026, 10, 29, 17, 30)
r = chiama(ctx_di(st, LEO, frase="ho finito, segna fatto"), azione="fatto", verifica=v)
verifica("«fatto» di nuovo lo stesso giorno: la serie non si ridice",
         r["ok"] and "serie" not in r["conferma"], r["conferma"])
r = chiama(ctx_di(st, ANDREA, frase="quante stelle ha Leo?"), azione="premi", per="Leo")
verifica("«premi» del tutore: alla terza persona", r["ok"] and "La serie di Leo è a 1 giorno"
         in r["conferma"], r["conferma"])
r = chiama(ctx_di(st, BRUNO, frase="quante stelle ha Leo?"), azione="premi", per="Leo")
verifica("«premi» di Leo chiesto da Bruno: rifiutato", not r["ok"])
verifica("politica: «premi» una lettura", "premi" in TS.LETTURE
         and "premi" in politica.CLASSI["studio"].sola_lettura[1])
st.close()

# ═══════════════════════════ 8. attraverso Brain ═══════════════════════════
print("— attraverso Brain")
import prova_politica as PP  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402


def brain_vero(st_, prof):
    reg = build_registry()
    for sp in TS.studio_specs():
        reg.register(sp)
    c_ = ctx_di(st_, prof)
    for kk, vv in (("from_session", False), ("voce_sicura", prof.name), ("punteggio", 0.7),
                   ("conferma_breve", False), ("sfida", None), ("sfida_superata", False)):
        setattr(c_.speaker_ctx, kk, vv)
    b_ = Brain(st_.cfg, reg, c_)
    b_.backend = PP.Copione()
    return b_


def turno(b_, frase, *risposte):
    b_.backend.risposte = list(risposte)
    b_.tool_ctx.user_text = frase
    with contextlib.redirect_stdout(io.StringIO()):
        return "".join(b_.stream_reply(frase, "familiare"))


ora(29)
st = studio(cfg_nuova("brain.db"))
v = carica(st)
st.imposta_sessione(LEO, v, 2, "stressato")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 40)
b = brain_vero(st, LEO)
detto = turno(b, "ho finito di studiare, segna fatto",
              PP.chiama("studio", {"azione": "fatto", "verifica": v}))
verifica("Leo: «ho finito» → nella voce la serie, detta dal codice",
         "La tua serie è a 1 giorno di studio." in detto, detto[:300])
verifica("nella voce niente stato d'animo né titoli",
         "stress" not in detto and not any(t in detto for t in TITOLI))
detto = turno(b, "quante stelle ho?", PP.chiama("studio", {"azione": "premi"}))
verifica("«quante stelle ho?» → la serie e le stelle", "La tua serie è a 1 giorno" in detto
         and "stelle" in detto.lower(), detto[:300])
storia = json.dumps(b.history, ensure_ascii=False)
verifica("nella storia niente stato d'animo", "stressato" not in storia)
st.close()

# ═══════════════════════════ 9. gli endpoint ═══════════════════════════
print("— gli endpoint")
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from calliope import minori  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402


def chiedi(port, percorso, sessione_=None, token=None, corpo=None):
    h = {"Content-Type": "application/json"}
    if sessione_:
        h["X-Calliope-Sessione"] = sessione_
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST",
                                 data=json.dumps(corpo if corpo is not None else {}).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            return e.code, {}


class Servizi:
    studio = None


ORA[0] = datetime.datetime.now().replace(microsecond=0)
cfg5 = cfg_nuova("server.db", studio_duelli=True)
minori.prepara(cfg5, registry=REG)
st5 = studio(cfg5)
hub = Schermi(cfg5, ArchivioSchermi(cfg5.memory_db), log=righe_log.append)
hub.profilo = REG.by_id
serv = Servizi()
serv.studio = st5
hub.servizi = serv
srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
hub.server = srv
try:
    tok = {}
    for chi, pid in (("leo", "l1"), ("andrea", "a1"), ("bruno", "b1")):
        _, tok[chi] = hub.archivio.crea_con_token("telefono " + chi, proprietario=pid,
                                                  proprietario_nome=chi.title())
    hub._rinfresca()
    port = srv.port
    sess = {k: chiedi(port, "/api/accedi", token=t)[1].get("sessione") for k, t in tok.items()}
    data = (ORA[0].date() + datetime.timedelta(days=7)).isoformat()
    v5 = st5.crea_verifica(LEO, "Storia", data)
    m5 = st5.aggiungi_materiale(LEO, v5, "foto", "Libro")
    p5 = st5.aggiungi_pagina(LEO, m5, numero="12", stato="letta", metodo="ocr", testo="Nel 1453.")
    st5.aggiungi_argomento(LEO, v5, "La caduta di Costantinopoli", [p5], proposto=False)
    st5.conferma_argomenti(LEO, v5)
    a5 = st5.argomenti(LEO, v5)[0]["id"]
    for i in range(3):
        st5.aggiungi_domanda(LEO, v5, "numero", f"Anno {i}?", str(1450 + i), argomento=a5)
    s, d = chiedi(port, "/api/studio/premi", sess["leo"])
    verifica("premi di Leo: 200, serie e stelle, duelli spenti per lui", s == 200 and d["acceso"]
             and d["impostazioni"]["duelli"] is False and d["persone_duello"] == [], str(d)[:300])
    s, d = chiedi(port, "/api/studio/premi", sess["leo"],
                  corpo={"azione": "imposta", "duelli": True})
    verifica("Leo non accende i suoi duelli: 404", s == 404)
    s, d = chiedi(port, "/api/studio/premi", sess["andrea"],
                  corpo={"persona": "l1", "azione": "imposta", "duelli": True})
    verifica("il tutore accende i duelli di Leo", s == 200 and d["impostazioni"]["duelli"] is True)
    s, d = chiedi(port, "/api/studio/premi", sess["bruno"], corpo={"persona": "l1"})
    verifica("Bruno non vede i premi di Leo: 404", s == 404)
    s, d = chiedi(port, "/api/studio/premi", sess["andrea"],
                  corpo={"persona": "l1", "azione": "imposta", "duelli": "sì"})
    verifica("un valore che non è vero o falso: 400", s == 400)
    s, d = chiedi(port, "/api/studio/duello", sess["leo"],
                  corpo={"azione": "proponi", "verifica": v5, "a": "b1"})
    did5 = d.get("id")
    verifica("Leo propone un duello a Bruno", s == 200 and d.get("stato") == "proposto", str(d))
    s, d = chiedi(port, "/api/studio/duello", sess["andrea"], corpo={"duello": did5})
    verifica("Andrea non ne fa parte: 404", s == 404)
    s, d = chiedi(port, "/api/studio/duello", sess["leo"],
                  corpo={"duello": did5, "azione": "rispondi", "voce": 1, "risposta": "1450"})
    verifica("rispondere prima del sì di Bruno: 400", s == 400)
    s, d = chiedi(port, "/api/studio/duello", sess["bruno"], corpo={"duello": did5,
                                                                   "azione": "accetta"})
    verifica("Bruno accetta: le domande senza risposte attese", s == 200 and d["stato"] == "in_corso"
             and d["voci"] and all("attesa" not in x for x in d["voci"]))
    for chi in ("leo", "bruno"):
        for x in d["voci"]:
            chiedi(port, "/api/studio/duello", sess[chi],
                   corpo={"duello": did5, "azione": "rispondi", "voce": x["n"],
                          "risposta": "<b>1450</b>"})
        s, dd = chiedi(port, "/api/studio/duello", sess[chi], corpo={"duello": did5,
                                                                    "azione": "consegna"})
    verifica("tutti e due consegnano: finito coi punti", s == 200 and dd["stato"] == "finito"
             and "punti" in dd, str(dd)[:300])
    s, d = chiedi(port, "/api/studio/home", sess["leo"])
    verifica("la home di Leo: i premi coi duelli", s == 200 and d.get("premi")
             and d["premi"]["duelli"] and d["premi"]["duelli"][0]["stato"] == "finito")
    s, d = chiedi(port, "/api/studio/tutore", sess["andrea"], corpo={"verifica": v5})
    verifica("la vista del tutore: i premi di Leo con gli interruttori", s == 200
             and d.get("premi", {}).get("impostazioni", {}).get("duelli") is True)
    verifica("nel registro del server niente testo delle domande",
             not any("Anno" in r for r in righe_log if "duello" in r))
finally:
    srv.ferma()
    st5.close()
sys.exit(1 if errori else 0)
