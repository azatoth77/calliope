import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Lo Studio, dati e piano a giorni a secco (29/10, passo 4.1, issue #280, decisione 0035;
calliope/studio/). Con i materiali di fantasia di `prove/manuali/studio/` (storia, matematica,
scienze): lo schema che si crea e si riapre (e la sola lettura con uno schema più nuovo), il
piano deterministico (verifica domani, fra una settimana e fra un mese, nessun giorno libero,
orari di riposo che coprono la fascia, pagine più dei giorni, data spostata, verifica oggi e
passata, giorni fatti, «non ce la faccio oggi», giorni senza scuola, due verifiche negli stessi
giorni), tappe e previsione, i permessi (minore, tutore, adulto, chi amministra, ospite,
conoscente), la tenuta a 60 giorni dalla data con un orologio finto, «archivia la verifica»,
«dimentica» e `svuota`, l'interruttore spento, ombra e attivo. Niente modello, niente rete.
"""

import datetime
import json
import sqlite3
import tempfile
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import minori  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.config import VALIDATORI, Config  # noqa: E402
from calliope.conserva import Conservazione  # noqa: E402
from calliope.studio import dati as D  # noqa: E402
from calliope.studio import piano as P  # noqa: E402

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
    except Exception as e:  # noqa: BLE001
        print(f"    (sollevato {type(e).__name__}: {e})")
        return False
    return False


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None, tutori=(), tipo=None):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, tipo


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


# Persone di fantasia: Andrea (tutore), Leo (seconda media, tutore Andrea), Carla (amministra,
# non tutrice di Leo), Bruno (adulto), Mia (minore senza tutori: vale chi amministra), un
# conoscente
ANDREA = Prof("a1", "Andrea")
CARLA = Prof("c1", "Carla", admin=True)
BRUNO = Prof("b1", "Bruno")
LEO = Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
MIA = Prof("m1", "Mia", nascita="2016-05-01")
NOTO = Prof("k1", "Piero", tipo="conoscente")
REG = Registro(ANDREA, CARLA, BRUNO, LEO, MIA, NOTO)

MATERIALI = {m: json.loads((QUI / "manuali" / "studio" / f"{m}.json").read_text("utf-8"))
             for m in ("storia", "matematica", "scienze")}

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-"))
ORA = [datetime.datetime(2026, 10, 29, 10, 0)]          # giovedì 29/10, mattina


def cfg_nuova(nome="memoria.db", modo="ombra", **kw):
    c = Config()
    c.memory_db = str(TMP / nome)
    c.studio_modo = modo
    c.studio_cartella = str(TMP / "studio")
    c.turn_log_dir = str(TMP / "registro")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


righe_log = []


def studio(cfg):
    return S.Studio(cfg, registry=REG, log=righe_log.append, adesso=lambda: ORA[0])


def carica(st, chi, materia, persona=None, data=None, titolo_materiale="Libro", togli=()):
    """Una verifica dai materiali di fantasia: le pagine in ordine (gli appunti senza numero),
    gli argomenti proposti con le loro pagine, la conferma a mano."""
    m = MATERIALI[materia]
    vid = st.crea_verifica(chi, m["materia"], data or m["data_verifica"], livello=m["classe"],
                           argomento=m["argomento"], persona=persona)
    mid = st.aggiungi_materiale(chi, vid, "foto", titolo_materiale)
    ids = {}
    for p in m["pagine"]:
        ids[p["id"]] = st.aggiungi_pagina(
            chi, mid, numero=p["numero"],
            etichetta="Appunti" if p["tipo"] == "appunti" else (
                "Indice" if p["tipo"] == "indice" else None),
            file=f"{materia}/{p['id']}.jpg", testo=p["testo"], metodo="ocr")
    for a in m["argomenti"]:
        if a["titolo"] in togli:
            continue
        st.aggiungi_argomento(chi, vid, a["titolo"], [ids[x] for x in a["pagine"]])
    st.conferma_argomenti(chi, vid)
    return vid, ids


# ═══════════════════════════ 1. il piano puro ═══════════════════════════
print("— il piano puro")
oggi = datetime.date(2026, 10, 29)
pag = [P.Pagina(i, i, str(111 + i)) for i in range(1, 9)]          # pagine 112–119


def minuti_uguali(giorni, m=45):
    return {oggi + datetime.timedelta(days=i): m for i in range(giorni)}


p = P.calcola(oggi, oggi + datetime.timedelta(days=1), pag, minuti_uguali(1), 10)
verifica("verifica domani: un giorno solo, tutto da leggere, senza ripasso",
         len(p.giorni) == 1 and p.giorni[0].fase == P.STUDIO and len(p.giorni[0].pagine) == 8
         and P.SENZA_RIPASSO in p.avvisi)
verifica("verifica domani: 8 pagine in 45 minuti sono troppe (oltre e avviso)",
         p.giorni[0].oltre and P.TROPPE_PAGINE in p.avvisi and p.giorni[0].minuti == 80)
verifica("verifica domani: «Leggi le pagine 112–119.»",
         p.giorni[0].attivita == "Leggi le pagine 112–119.")

p = P.calcola(oggi, oggi + datetime.timedelta(days=30), pag, minuti_uguali(30), 10)
studio_g = [g for g in p.giorni if g.fase == P.STUDIO]
lette = [x for g in studio_g for x in g.pagine]
verifica("fra un mese: ogni pagina una volta sola, nell'ordine",
         lette == [x.id for x in pag])
verifica("fra un mese: nessun giorno oltre i suoi minuti e niente avvisi",
         not any(g.oltre for g in p.giorni) and p.avvisi == [] and all(
             len(g.pagine) <= 4 for g in studio_g))
verifica("fra un mese: l'ultimo giorno (la vigilia) è ripasso di tutte le pagine",
         p.giorni[-1].giorno == oggi + datetime.timedelta(days=29)
         and p.giorni[-1].fase == P.RIPASSO and p.giorni[-1].pagine == [x.id for x in pag]
         and p.giorni[-1].attivita == "Ripassa le pagine 112–119.")
verifica("fra un mese: un giorno di solo ripasso vale i minuti delle pagine lette",
         all(g.minuti <= len(g.pagine) * 10 for g in p.giorni[:-1] if g.fase == P.RIPASSO))
verifica("fra un mese: i giorni senza pagine nuove ripassano quelle lette",
         any(g.fase == P.RIPASSO and g.giorno < p.giorni[-1].giorno for g in p.giorni)
         and len(p.giorni) == 30 and p.giorni_mancanti == 30)
verifica("fra un mese: deterministico (due calcoli uguali, anche con i minuti in un altro ordine)",
         P.calcola(oggi, oggi + datetime.timedelta(days=30), list(reversed(pag)),
                   dict(reversed(list(minuti_uguali(30).items()))), 10) == p)

p = P.calcola(oggi, oggi + datetime.timedelta(days=5), pag, minuti_uguali(5, 0), 10)
verifica("nessun giorno libero: niente piano e l'avviso",
         p.giorni == [] and p.avvisi == [P.NESSUN_GIORNO])
p = P.calcola(oggi, oggi + datetime.timedelta(days=5), pag, minuti_uguali(5, 9), 10)
verifica("giorni con meno minuti di una pagina: nessun giorno libero",
         p.giorni == [] and p.avvisi == [P.NESSUN_GIORNO])

molte = [P.Pagina(i, i, str(i)) for i in range(1, 21)]
p = P.calcola(oggi, oggi + datetime.timedelta(days=3), molte, minuti_uguali(3), 10)
verifica("pagine più dei giorni: 20 pagine in tre giorni da 4, si legge anche la vigilia",
         [len(g.pagine) for g in p.giorni] == [7, 7, 6]
         and all(g.fase == P.STUDIO and g.oltre for g in p.giorni)
         and P.TROPPE_PAGINE in p.avvisi and P.SENZA_RIPASSO in p.avvisi)
p = P.calcola(oggi, oggi + datetime.timedelta(days=2), molte[:6], minuti_uguali(2), 10)
verifica("6 pagine in due giorni da 4: la vigilia si legge invece di andare oltre i minuti",
         [len(g.pagine) for g in p.giorni] == [3, 3] and not any(g.oltre for g in p.giorni)
         and p.avvisi == [P.SENZA_RIPASSO])
p = P.calcola(oggi, oggi + datetime.timedelta(days=4), molte[:9], minuti_uguali(4), 10)
verifica("9 pagine in tre giorni da 4: 3 al giorno, nessuno oltre",
         [len(g.pagine) for g in p.giorni if g.fase == P.STUDIO] == [3, 3, 3]
         and not any(g.oltre for g in p.giorni))

dis = {oggi: 20, oggi + datetime.timedelta(days=1): 60, oggi + datetime.timedelta(days=2): 45}
p = P.calcola(oggi, oggi + datetime.timedelta(days=3), molte[:8], dis, 10)
verifica("minuti diversi: le pagine in proporzione (2 e 6), poi il ripasso",
         [len(g.pagine) for g in p.giorni] == [2, 6, 8] and not any(g.oltre for g in p.giorni))

verifica("verifica oggi: niente piano", P.calcola(oggi, oggi, pag, {}, 10).avvisi == [P.OGGI])
verifica("verifica passata: niente piano",
         P.calcola(oggi, oggi - datetime.timedelta(days=1), pag, {}, 10).avvisi == [P.PASSATA])
verifica("nessuna pagina: l'avviso",
         P.calcola(oggi, oggi + datetime.timedelta(days=3), [], minuti_uguali(3),
                   10).avvisi == [P.NESSUNA_PAGINA])
p = P.calcola(oggi, oggi + datetime.timedelta(days=3), pag, minuti_uguali(3), 10,
              fatte={x.id for x in pag})
verifica("tutto letto: restano i giorni di ripasso",
         [g.fase for g in p.giorni] == [P.RIPASSO] * 3 and p.pagine_fatte == 8)
p = P.calcola(oggi, oggi + datetime.timedelta(days=4), pag, minuti_uguali(4), 10,
              fatte={1, 2}, giorni_fatti={oggi})
verifica("giorni fatti: oggi non si riempie, le pagine lette non tornano",
         all(g.giorno != oggi for g in p.giorni)
         and [x for g in p.giorni if g.fase == P.STUDIO for x in g.pagine] == [3, 4, 5, 6, 7, 8])

verifica("descrizione: «la pagina 114»", P.descrivi_pagine([P.Pagina(1, 1, "114")])
         == "la pagina 114")
verifica("descrizione: numeri non di fila e gli appunti",
         P.descrivi_pagine([P.Pagina(1, 1, "112"), P.Pagina(2, 2, "113"), P.Pagina(3, 3, "115"),
                            P.Pagina(4, 4, None, "Appunti")])
         == "le pagine 112–113 e 115 e «Appunti»")
verifica("descrizione: un numero romano resta com'è",
         P.descrivi_pagine([P.Pagina(1, 1, "IV"), P.Pagina(2, 2, "5")]) == "le pagine 5 e IV")

for strano in ("²", "①", "12²", "1 2", "-3", "p.12", "x" * 12, "\u200b"):
    pp = [P.Pagina(1, 1, "112"), P.Pagina(2, 2, strano, None, "Libro"), P.Pagina(3, 3, "113")]
    try:
        p = P.calcola(oggi, oggi + datetime.timedelta(days=3), pp, minuti_uguali(3), 10)
        ok = (P.NUMERO_STRANO in p.avvisi and sum(len(g.pagine) for g in p.giorni
                                                 if g.fase == P.STUDIO) == 3)
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"    ({strano!r}: {type(e).__name__}: {e})")
    verifica(f"numero di pagina strano {strano!r}: il piano c'è, la pagina senza numero e "
             f"l'avviso", ok)
verifica("numero strano: l'attività lo nomina col materiale, mai col numero",
         P.descrivi_pagine([P.Pagina(1, 1, "²", None, "Libro")]) == "«Libro»")
verifica("cifre decimali di un'altra scrittura (١٢) valgono 12",
         P.descrivi_pagine([P.Pagina(1, 1, "١٢")]) == "la pagina 12"
         and P.numero_pagina("²") is None and P.numero_pagina("0012") == 12)
verifica("una sigla corta resta (IV, 12a), il vuoto non è strano",
         P.numero_leggibile("12a") == "12a" and not P.numero_strano("")
         and not P.numero_strano(None) and P.numero_strano("²"))
due = [P.Pagina(1, 1, "12", None, "Libro"), P.Pagina(2, 2, "13", None, "Libro"),
       P.Pagina(3, 3, "12", None, "Quaderno")]
verifica("due materiali con la pagina 12: l'attività li distingue",
         P.descrivi_pagine(due, P.piu_materiali(due))
         == "le pagine 12–13 di «Libro» e la pagina 12 di «Quaderno»")
p = P.calcola(oggi, oggi + datetime.timedelta(days=2), due, minuti_uguali(2), 10)
verifica("due materiali nel piano: «di «Libro»» anche nell'attività",
         "di «Libro»" in p.giorni[0].attivita and "di «Quaderno»" in p.giorni[0].attivita)
verifica("un solo materiale: niente titolo accanto ai numeri",
         not P.piu_materiali(due[:2]) and P.descrivi_pagine(due[:2]) == "le pagine 12–13")

fascia = P.fascia_valida("15:00-20:00")
verifica("minuti liberi: la fascia intera", P.minuti_liberi(fascia) == 300)
verifica("minuti liberi: oggi alle 18:30 restano 90 minuti",
         P.minuti_liberi(fascia, da_minuto=18 * 60 + 30) == 90)
verifica("minuti liberi: oggi dopo la fascia niente", P.minuti_liberi(fascia, da_minuto=21 * 60)
         == 0)
verifica("minuti liberi: il riposo 19:00-07:30 (passa la mezzanotte) toglie un'ora",
         P.minuti_liberi(fascia, ["19:00-07:30"]) == 240)
verifica("minuti liberi: il riposo 14:00-23:00 copre tutta la fascia",
         P.minuti_liberi(fascia, ["14:00-23:00"]) == 0)
verifica("orari di riposo scritti come una stringa sola: letti come minori._orari_validi",
         P.minuti_liberi(fascia, "14:00-23:00") == 0
         and P.minuti_liberi(fascia, "19:00-07:30; 15:00-15:30") == 210
         and P.minuti_liberi(fascia, ["sempre", "25:00-26:00"]) == 300)
verifica("fascia scritta male rifiutata", P.fascia_valida("20:00-15:00") is None
         and P.fascia_valida("pomeriggio") is None)
verifica("giorni della settimana, anche senza accento",
         P.giorno_della_settimana("Domenica") == 6 and P.giorno_della_settimana("lunedi") == 0
         and P.giorno_della_settimana("festa") is None)

verifica("previsione: niente con nessuna o una misura",
         P.previsione([], oggi) is None
         and P.previsione([(oggi, 40.0)], oggi + datetime.timedelta(days=5)) is None)
verifica("previsione: due misure vere, la retta portata alla data (40 → 50 in 2 giorni: 75)",
         P.previsione([(oggi, 40.0), (oggi + datetime.timedelta(days=2), 50.0)],
                      oggi + datetime.timedelta(days=7)) == 75)
verifica("previsione: fra 0 e 100",
         P.previsione([(oggi, 60.0), (oggi + datetime.timedelta(days=1), 95.0)],
                      oggi + datetime.timedelta(days=10)) == 100
         and P.previsione([(oggi, 30.0), (oggi + datetime.timedelta(days=1), 5.0)],
                          oggi + datetime.timedelta(days=10)) == 0)
verifica("previsione: due misure dello stesso giorno, la media",
         P.previsione([(oggi, 40.0), (oggi, 60.0)], oggi + datetime.timedelta(days=3)) == 50)

# ═══════════════════════════ 2. lo schema ═══════════════════════════
print("— lo schema")
cfg = cfg_nuova()
st = studio(cfg)
nomi = {r[0] for r in st.dati.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
verifica("le sette tabelle studio_* e l'ultima versione in meta_schema (3 dal passo 4.4, #283)",
         set(D.TABELLE) <= nomi and st.dati.db.execute(
             "SELECT versione FROM meta_schema WHERE modulo='studio'").fetchone()[0]
         == len(D.MIGRAZIONI) == 3)
from calliope.conserva import TABELLE_STUDIO  # noqa: E402
verifica("le tabelle di conserva.TABELLE_STUDIO sono quelle dello Studio",
         set(TABELLE_STUDIO) == set(D.TABELLE))
vid, ids = carica(st, LEO, "storia")
st.close()
st = studio(cfg)
verifica("riaperta: la verifica c'è ancora, con le pagine e il piano",
         st.verifica(LEO, vid)["materia"] == "Storia" and len(st.pagine(LEO, vid)) == 8
         and len(st.piano(LEO, vid)["giorni"]) > 0)
st.close()
db = sqlite3.connect(cfg.memory_db)
db.execute("UPDATE meta_schema SET versione = 99 WHERE modulo = 'studio'")
db.commit()
db.close()
st = studio(cfg)
verifica("schema più nuovo: si legge, non si scrive",
         not st.dati.scrivibile and st.verifica(LEO, vid)["id"] == vid
         and solleva(lambda: st.crea_verifica(LEO, "Storia", "2026-11-20"), PermissionError))
st.close()
ORA[0] = datetime.datetime(2026, 10, 30, 9, 0)            # il giorno dopo: va ricalcolato
st = studio(cfg)
try:
    pi, og = st.piano(LEO, vid), st.oggi(LEO)
    ok = (pi["giorni"][0]["giorno"] == "2026-10-30" and pi["giorni"][-1]["fase"] == P.RIPASSO
          and len(og) == 1 and og[0]["attivita"].startswith("Leggi"))
except Exception as e:  # noqa: BLE001
    ok = False
    print(f"    ({type(e).__name__}: {e})")
verifica("schema più nuovo, il giorno dopo: piano e «Oggi» calcolati in memoria", ok)
st.close()
db = sqlite3.connect(cfg.memory_db)
verifica("schema più nuovo, il giorno dopo: niente scritto nel db",
         db.execute("SELECT piano_del FROM studio_verifiche WHERE id = ?", (vid,)).fetchone()[0]
         == "2026-10-29" and db.execute("SELECT MIN(giorno) FROM studio_piano WHERE "
                                        "verifica = ?", (vid,)).fetchone()[0] == "2026-10-29")
db.close()
ORA[0] = datetime.datetime(2026, 10, 29, 10, 0)
db = sqlite3.connect(cfg.memory_db)
db.execute("UPDATE meta_schema SET versione = ? WHERE modulo = 'studio'", (len(D.MIGRAZIONI),))
db.commit()
db.close()

# ═══════════════════════════ 3. il piano dal servizio ═══════════════════════════
print("— il piano dal servizio (storia, giovedì 5/11)")
ORA[0] = datetime.datetime(2026, 10, 29, 10, 0)
cfg = cfg_nuova("piano.db")
st = studio(cfg)
vid, ids = carica(st, LEO, "storia")
pi = st.piano(LEO, vid)
studio_g = [g for g in pi["giorni"] if g["fase"] == P.STUDIO]
verifica("obiettivo di serie 75 % e 7 giorni che mancano",
         pi["obiettivo"] == 75 and pi["giorni_mancanti"] == 7 and pi["stato"] == "aperta")
verifica("sei giorni di studio dal 29/10, la vigilia (4/11) di ripasso",
         [g["giorno"] for g in pi["giorni"]] == [f"2026-{d}" for d in (
             "10-29", "10-30", "10-31", "11-01", "11-02", "11-03", "11-04")]
         and pi["giorni"][-1]["fase"] == P.RIPASSO and len(studio_g) == 6)
verifica("le pagine degli argomenti, senza l'indice, ognuna una volta",
         sorted(x for g in studio_g for x in g["pagine"]) == sorted(
             ids[k] for k in ("p112", "p113", "p114", "p115", "p116", "appunti", "p117")))
verifica("l'attività del primo giorno: «Leggi le pagine 112–113.»",
         studio_g[0]["attivita"] == "Leggi le pagine 112–113.")
verifica("gli appunti si leggono col loro nome",
         any("«Appunti»" in g["attivita"] for g in studio_g))
verifica("nessun testo delle pagine né titolo degli argomenti nelle attività",
         not any("Colombo" in g["attivita"] or "ignora" in g["attivita"].lower()
                 for g in pi["giorni"]))
verifica("tappe: la prima aperta, le altre chiuse",
         pi["tappe"][0]["stato"] == "aperta"
         and all(t["stato"] == "chiusa" for t in pi["tappe"][1:])
         and pi["tappe"][0]["titolo"] == "Le cause delle scoperte geografiche")
verifica("previsione assente senza misure", pi["previsione"] is None and pi["misure"] == 0)
oggi_l = st.oggi(LEO)
verifica("la riga «Oggi» di Leo", len(oggi_l) == 1 and oggi_l[0]["attivita"]
         == "Leggi le pagine 112–113." and oggi_l[0]["materia"] == "Storia")

st.giorno_fatto(LEO, vid)
ORA[0] = datetime.datetime(2026, 10, 30, 9, 0)
pi = st.piano(LEO, vid)
verifica("il giorno dopo: il 29/10 resta fatto e non si rifà",
         pi["giorni"][0]["giorno"] == "2026-10-29" and pi["giorni"][0]["fatto"]
         and not any(ids["p112"] in g["pagine"] for g in pi["giorni"][1:]
                     if g["fase"] == P.STUDIO))
verifica("tappe: le prime due fatte (pagine 112 e 113), la terza aperta, le altre chiuse",
         [t["stato"] for t in pi["tappe"][:4]] == ["fatta", "fatta", "aperta", "chiusa"]
         and pi["giorni_mancanti"] == 6)

st.salta_oggi(LEO)
pi = st.piano(LEO, vid)
verifica("«non ce la faccio oggi»: il 30/10 senza piano, le pagine ai giorni dopo",
         all(g["giorno"] != "2026-10-30" for g in pi["giorni"])
         and sorted(x for g in pi["giorni"] if g["fase"] == P.STUDIO for x in g["pagine"])
         == sorted(ids[k] for k in ("p112", "p113", "p114", "p115", "p116", "appunti", "p117")))

st.imposta_giorno(LEO, "2026-11-02", 0, "senza_scuola")
pi = st.piano(LEO, vid)
verifica("giorno senza scuola segnato: niente piano il 2/11",
         all(g["giorno"] != "2026-11-02" for g in pi["giorni"]))

st.imposta(LEO, vid, data="2026-11-12")
pi = st.piano(LEO, vid)
verifica("data spostata al 12/11: il ripasso è l'11/11, il fatto resta",
         pi["giorni"][-1]["giorno"] == "2026-11-11" and pi["giorni"][-1]["fase"] == P.RIPASSO
         and pi["giorni"][0]["fatto"] and pi["giorni_mancanti"] == 13)
st.giorno_fatto(LEO, vid, "2026-11-03")
st.imposta(LEO, vid, data="2026-11-03")
pi = st.piano(LEO, vid)
verifica("data spostata prima di un giorno fatto: il fatto dopo la data non resta",
         all(g["giorno"] < "2026-11-03" for g in pi["giorni"]))
st.imposta(LEO, vid, data="2026-11-12")
verifica("data spostata nel passato rifiutata",
         solleva(lambda: st.imposta(LEO, vid, data="2026-10-01"), ValueError))

st.imposta(LEO, vid, minuti_giorno=0)
pi = st.piano(LEO, vid)
verifica("zero minuti al giorno: nessun giorno libero",
         pi["avvisi"] == [P.NESSUN_GIORNO]
         and all(g["fatto"] for g in pi["giorni"]))
st.imposta(LEO, vid, minuti_giorno=10)
pi = st.piano(LEO, vid)
verifica("10 minuti al giorno: una pagina al giorno",
         all(len(g["pagine"]) <= 1 for g in pi["giorni"] if g["fase"] == P.STUDIO
             and not g["fatto"]) and pi["avvisi"] == [])

prima = st.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? ORDER BY id", (vid,))
vero_j = D.j
chiamate = [0]


def j_rotto(x):
    chiamate[0] += 1
    if chiamate[0] > 2:
        raise RuntimeError("guasto a metà")
    return vero_j(x)


import calliope.studio.servizio as SV  # noqa: E402
SV.D.j = j_rotto
righe_log.clear()
try:
    st.imposta(LEO, vid, minuti_giorno=20)
    rotto_ok = True
except Exception:  # noqa: BLE001
    rotto_ok = False
finally:
    SV.D.j = vero_j
dopo = st.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? ORDER BY id", (vid,))
verifica("ricalcolo guasto a metà: rollback, il piano di prima resta, una riga nel registro",
         rotto_ok and dopo == prima and not st.dati.db.in_transaction
         and any("non ricalcolato: RuntimeError" in x for x in righe_log))
st.imposta(LEO, vid, minuti_giorno=10)
st.segna_argomento(LEO, st.argomenti(LEO, vid)[-1]["id"], False)     # «Esercizi» tolto
pi = st.piano(LEO, vid)
verifica("argomento tolto: le sue pagine escono dal piano",
         not any(ids["p116"] in g["pagine"] for g in pi["giorni"]))

st.aggiungi_misura(LEO, vid, 40, "prova")
pi = st.piano(LEO, vid)
verifica("una misura: c'è il livello, la previsione no",
         pi["livello"] == 40 and pi["previsione"] is None)
ORA[0] = datetime.datetime(2026, 11, 1, 9, 0)
st.aggiungi_misura(LEO, vid, 55, "prova")
pi = st.piano(LEO, vid)
verifica("due misure vere: la previsione compare (40 → 55 in 2 giorni, al 12/11 100)",
         pi["previsione"] == 100 and pi["misure"] == 2)
verifica("misura fuori da 0–100 rifiutata",
         solleva(lambda: st.aggiungi_misura(LEO, vid, 130, "prova"), ValueError))

# Orari di riposo di Leo che coprono tutta la fascia
minori._SERVIZIO["regole"] = minori.Regole(cfg.memory_db)
minori._SERVIZIO["regole"].imposta("l1", "orari", ["14:00-23:00"])
st.imposta(LEO, vid, minuti_giorno=45)
pi = st.piano(LEO, vid)
verifica("orari di riposo che coprono il pomeriggio: nessun giorno libero",
         pi["avvisi"] == [P.NESSUN_GIORNO])
minori._SERVIZIO["regole"].imposta("l1", "orari", ["19:00-07:30"])
st.imposta(LEO, vid, minuti_giorno=300)
pi = st.piano(LEO, vid)
verifica("riposo dalle 19: al più 240 minuti al giorno",
         all(g["minuti"] <= 240 for g in pi["giorni"]))
minori._SERVIZIO["regole"].imposta("l1", "orari", [])
st.imposta(LEO, vid, minuti_giorno=45)

ORA[0] = datetime.datetime(2026, 11, 12, 9, 0)
pi = st.piano(LEO, vid)
verifica("la verifica è oggi: niente piano da fare", pi["giorni_mancanti"] == 0
         and pi["avvisi"] == [P.OGGI])
ORA[0] = datetime.datetime(2026, 11, 13, 9, 0)
pi = st.piano(LEO, vid)
verifica("il giorno dopo la verifica: «fatta», il piano resta come storia",
         pi["stato"] == "fatta" and len(pi["giorni"]) > 0 and st.oggi(LEO) == [])
vn = st.crea_verifica(BRUNO, "Inglese", "2026-11-20")
mn = st.aggiungi_materiale(BRUNO, vn, "mano", "Quaderno")
for strano in ("²", "①", "12"):
    st.aggiungi_pagina(BRUNO, mn, numero=strano)
pg_b = [x["id"] for x in st.pagine(BRUNO, vn)]
st.aggiungi_argomento(BRUNO, vn, "Verbi", pg_b)
try:
    pn = st.conferma_argomenti(BRUNO, vn)
    ok = P.NUMERO_STRANO in pn["avvisi"] and len(pn["giorni"]) > 0 and len(st.oggi(BRUNO)) >= 1
except Exception as e:  # noqa: BLE001
    ok = False
    print(f"    ({type(e).__name__}: {e})")
verifica("pagine con «²» e «①» dal servizio: il piano e la riga «Oggi» ci sono, con l'avviso",
         ok)
verifica("verifica nuova con la data passata rifiutata",
         solleva(lambda: st.crea_verifica(LEO, "Storia", "2026-11-01"), ValueError))
st.close()

print("— più verifiche, giorni senza piano, verifica domani")
ORA[0] = datetime.datetime(2026, 10, 29, 10, 0)
cfg = cfg_nuova("due.db", studio_giorni_senza_piano=["domenica"])
st = studio(cfg)
v1, _ = carica(st, LEO, "storia")
v2, _ = carica(st, LEO, "scienze")
p1, p2 = st.piano(LEO, v1), st.piano(LEO, v2)
verifica("due verifiche il 5/11: i minuti si dividono (al più 22 per verifica)",
         all(g["minuti"] <= 22 for g in p1["giorni"] + p2["giorni"]))
v_vuota = st.crea_verifica(LEO, "Inglese", "2026-11-05")
st.conferma_argomenti(LEO, v_vuota)
p1b = st.piano(LEO, v1)
verifica("una terza verifica aperta senza pagine non toglie minuti alle altre",
         [g["minuti"] for g in p1b["giorni"]] == [g["minuti"] for g in p1["giorni"]]
         and st.piano(LEO, v_vuota)["avvisi"] == [P.NESSUNA_PAGINA])
verifica("domenica 1/11 senza piano", all(g["giorno"] != "2026-11-01"
                                          for g in p1["giorni"] + p2["giorni"]))
verifica("la riga «Oggi» con due verifiche", len(st.oggi(LEO)) == 2)
v3, _ = carica(st, BRUNO, "matematica", data="2026-10-30")
p3 = st.piano(BRUNO, v3)
verifica("verifica domani (Bruno, adulto): oggi si legge tutto, senza ripasso, troppe pagine",
         len(p3["giorni"]) == 1 and p3["giorni"][0]["giorno"] == "2026-10-29"
         and P.SENZA_RIPASSO in p3["avvisi"] and P.TROPPE_PAGINE in p3["avvisi"])
ORA[0] = datetime.datetime(2026, 10, 29, 21, 0)
v4 = st.crea_verifica(BRUNO, "Inglese", "2026-10-30")
mid = st.aggiungi_materiale(BRUNO, v4, "mano", "Quaderno")
pg = st.aggiungi_pagina(BRUNO, mid, numero="3")
st.aggiungi_argomento(BRUNO, v4, "Il passato", [pg])
p4 = st.conferma_argomenti(BRUNO, v4)
verifica("verifica domani chiesta alle 21: la fascia è finita, nessun giorno",
         p4["avvisi"] == [P.NESSUN_GIORNO] and p4["giorni"] == [])
verifica("una pagina di un'altra verifica non si cita",
         solleva(lambda: st.aggiungi_argomento(BRUNO, v4, "X", [ids["p112"]]), ValueError))
st.close()

# ═══════════════════════════ 4. i permessi ═══════════════════════════
print("— i permessi")
ORA[0] = datetime.datetime(2026, 10, 29, 10, 0)
cfg = cfg_nuova("permessi.db")
st = studio(cfg)
vl, _ = carica(st, LEO, "storia")
va = st.crea_verifica(ANDREA, "Inglese", "2026-11-20")
vc = st.crea_verifica(CARLA, "Diritto", "2026-11-20")
verifica("il minore vede la sua", st.verifica(LEO, vl)["persona"] == "l1")
verifica("il tutore vede quella del minore e ne cambia i minuti",
         st.verifica(ANDREA, vl)["id"] == vl and st.imposta(ANDREA, vl, minuti_giorno=30) is None
         and st.verifica(LEO, vl)["minuti_giorno"] == 30)
verifica("il tutore vede le verifiche del minore e la sua riga «Oggi»",
         [v["id"] for v in st.verifiche(ANDREA, persona="l1")] == [vl]
         and len(st.oggi(ANDREA, persona="l1")) == 1)
verifica("il tutore crea una verifica per il minore",
         st.verifica(LEO, st.crea_verifica(ANDREA, "Storia", "2026-11-25", persona="l1"))[
             "creata_da"] == "a1")
verifica("chi amministra, se non è tutore, non vede quella del minore",
         solleva(lambda: st.verifica(CARLA, vl), S.NonTrovata)
         and solleva(lambda: st.verifiche(CARLA, persona="l1"), S.NonPermesso))
verifica("il minore non vede quella del tutore",
         solleva(lambda: st.verifica(LEO, va), S.NonTrovata))
verifica("nessuno vede quella di un altro adulto (nemmeno chi amministra)",
         solleva(lambda: st.verifica(CARLA, va), S.NonTrovata)
         and solleva(lambda: st.verifica(ANDREA, vc), S.NonTrovata)
         and solleva(lambda: st.verifica(BRUNO, va), S.NonTrovata))
verifica("il tutore non crea né cambia per un altro adulto",
         solleva(lambda: st.crea_verifica(ANDREA, "Storia", "2026-11-25", persona="c1"),
                 S.NonPermesso)
         and solleva(lambda: st.imposta(ANDREA, vc, minuti_giorno=10), S.NonTrovata))
verifica("un ospite non crea, non vede, non ha una riga «Oggi»",
         solleva(lambda: st.crea_verifica(None, "Storia", "2026-11-25"), S.NonPermesso)
         and solleva(lambda: st.verifica(None, vl), S.NonTrovata)
         and solleva(lambda: st.oggi(None, persona="l1"), S.NonPermesso))
verifica("un ospite non crea nemmeno a nome di una persona di casa",
         solleva(lambda: st.crea_verifica(None, "Storia", "2026-11-25", persona="l1"),
                 S.NonPermesso))
verifica("un conoscente non ha lo Studio",
         solleva(lambda: st.crea_verifica(NOTO, "Storia", "2026-11-25"), S.NonPermesso)
         and solleva(lambda: st.verifica(NOTO, vl), S.NonTrovata))
vm = st.crea_verifica(MIA, "Italiano", "2026-11-20")
verifica("minore senza tutori: vale chi amministra, non un altro adulto",
         st.verifica(CARLA, vm)["id"] == vm
         and solleva(lambda: st.verifica(ANDREA, vm), S.NonTrovata))
verifica("una verifica che non c'è e quella di un altro: lo stesso rifiuto",
         solleva(lambda: st.verifica(LEO, 9999), S.NonTrovata))


def messaggio(f):
    try:
        f()
    except S.NonTrovata as e:
        return str(e)
    except Exception as e:  # noqa: BLE001
        return f"altro: {type(e).__name__}"
    return "niente"


mat_l = st.dati.uno("SELECT id FROM studio_materiali WHERE verifica = ?", (vl,))["id"]
pag_l = st.pagine(LEO, vl)[0]["id"]
arg_l = st.argomenti(LEO, vl)[0]["id"]
msg = {messaggio(f) for f in (
    lambda: st.verifica(CARLA, vl), lambda: st.verifica(CARLA, 99999),
    lambda: st.aggiungi_pagina(CARLA, mat_l), lambda: st.aggiungi_pagina(CARLA, 99999),
    lambda: st.segna_pagina(CARLA, pag_l, "tolta"), lambda: st.segna_pagina(CARLA, 99999, "tolta"),
    lambda: st.segna_argomento(CARLA, arg_l, False),
    lambda: st.segna_argomento(CARLA, 99999, False),
    lambda: st.giorno_fatto(CARLA, vl), lambda: st.giorno_fatto(LEO, vl, "2027-01-01"))}
verifica("materiale, pagina, argomento e giorno di un altro o che non c'è: lo stesso messaggio",
         msg == {S.servizio.NON_TROVATA}, str(msg))
ORFANO = Prof("o1", "Nina", nascita="2015-01-01", tutori=["via1"])     # tutore non più in casa
REG.users["Nina"] = ORFANO
vo_ = st.crea_verifica(ORFANO, "Storia", "2026-11-20")
verifica("tutore scritto ma non più in casa: vede chi amministra, non un altro adulto",
         st.verifica(CARLA, vo_)["id"] == vo_
         and solleva(lambda: st.verifica(ANDREA, vo_), S.NonTrovata)
         and S.permesso(CARLA, ORFANO, REG) == "tutore"
         and S.permesso(ANDREA, LEO, REG) == "tutore" and S.permesso(CARLA, LEO, REG) is None)
del REG.users["Nina"]
verifica("le funzioni dei permessi: proprietario, tutore, niente",
         S.permesso(LEO, LEO) == "proprietario" and S.permesso(ANDREA, LEO) == "tutore"
         and S.permesso(LEO, ANDREA) is None and S.permesso(None, LEO) is None
         and S.permesso(NOTO, NOTO) is None)
st.close()

# ═══════════════════════════ 5. tenuta, archivia, dimentica, svuota ═══════════════════════════
print("— tenuta, «archivia la verifica», «dimentica» e svuota")
ORA[0] = datetime.datetime(2026, 10, 29, 10, 0)
cfg = cfg_nuova("tenuta.db")
st = studio(cfg)
cart = Path(cfg.studio_cartella)
(cart / "storia").mkdir(parents=True, exist_ok=True)
fuori = TMP / "fuori.jpg"
fuori.write_bytes(b"x")
vs, ids_s = carica(st, LEO, "storia")                     # 5/11
for k in ids_s:
    (cart / "storia" / f"{k}.jpg").write_bytes(b"jpg")
mid = st.aggiungi_materiale(LEO, vs, "file", "Fuori")
st.aggiungi_pagina(LEO, mid, numero="1", file="../fuori.jpg")
vsc, _ = carica(st, LEO, "scienze")                       # 5/11, sarà archiviata
st.archivia(LEO, vsc)
vb, _ = carica(st, BRUNO, "matematica")                   # 10/11
st.close()
cons = Conservazione(cfg, REG, log=righe_log.append)


def quante(persona=None):
    db = sqlite3.connect(cfg.memory_db)
    try:
        q = "SELECT COUNT(*) FROM studio_verifiche" + (" WHERE persona = ?" if persona else "")
        return db.execute(q, (persona,) if persona else ()).fetchone()[0]
    finally:
        db.close()


def testi():
    db = sqlite3.connect(cfg.memory_db)
    try:
        return db.execute("SELECT COUNT(*) FROM studio_pagine WHERE testo IS NOT NULL"
                          ).fetchone()[0]
    finally:
        db.close()


prima = testi()
cons.ruota(oggi=datetime.date(2026, 11, 5) + datetime.timedelta(days=60))
verifica("60 giorni dopo la data (4/1): tutto resta", quante() == 3 and testi() == prima)
r = cons.ruota(oggi=datetime.date(2026, 11, 5) + datetime.timedelta(days=61))
verifica("61 giorni dopo: la verifica di storia via, con pagine e testo; l'archiviata resta",
         quante("l1") == 1 and r["studio"]["verifiche"] == 1
         and testi() == prima - len(MATERIALI["storia"]["pagine"]))
verifica("i file delle sue pagine tolti dalla cartella dello Studio",
         # La cartella rimasta vuota si toglie anche lei (dal passo 4.2, #281)
         not (cart / "storia").exists() and r["studio"]["file"] == len(ids_s))
verifica("un file fuori dalla cartella dello Studio non si tocca", fuori.exists())
verifica("la verifica di Bruno (10/11) resta al 5/1", quante("b1") == 1)
cons.ruota(oggi=datetime.date(2027, 12, 31))
verifica("archiviata: resta per sempre (un anno dopo)", quante("l1") == 1 and quante("b1") == 0)
db = sqlite3.connect(cfg.memory_db)
db.execute("INSERT INTO studio_giorni (persona, giorno, minuti, motivo) VALUES "
           "('l1', '2026-10-30', 0, 'saltato'), ('l1', '2027-12-01', 0, 'senza_scuola')")
db.commit()
db.close()
r = cons.ruota(oggi=datetime.date(2027, 12, 31))
db = sqlite3.connect(cfg.memory_db)
resti = db.execute("SELECT giorno FROM studio_giorni").fetchall()
db.close()
verifica("i giorni segnati scadono con la tenuta (60 giorni), quelli recenti restano",
         resti == [("2027-12-01",)] and r["studio"].get("giorni") == 1)
verifica("la tenuta scrive una riga nel registro, senza nomi",
         any("Studio: tolte" in x for x in righe_log)
         and not any("Leo" in x or "Storia" in x for x in righe_log if "[CONSERVA]" in x))

cfg = cfg_nuova("dimentica.db")
st = studio(cfg)
v1, _ = carica(st, LEO, "storia")
v2, _ = carica(st, LEO, "scienze")
st.archivia(LEO, v2)
st.imposta_giorno(LEO, "2026-11-02", 0, "senza_scuola")
v3, _ = carica(st, BRUNO, "matematica")
st.close()
D.cancella_file(cfg.memory_db, persona="l1", archiviate=False, cartella=cfg.studio_cartella)
db = sqlite3.connect(cfg.memory_db)
resto = [r[0] for r in db.execute("SELECT stato FROM studio_verifiche WHERE persona='l1'")]
giorni = db.execute("SELECT COUNT(*) FROM studio_giorni WHERE persona='l1'").fetchone()[0]
orfani = db.execute("SELECT COUNT(*) FROM studio_pagine WHERE materiale NOT IN "
                    "(SELECT id FROM studio_materiali)").fetchone()[0]
db.close()
verifica("«dimentica»: via le verifiche di Leo non archiviate e i suoi giorni",
         resto == ["archiviata"] and giorni == 0 and orfani == 0)
verifica("«dimentica» di Leo non tocca Bruno", quante("b1") == 1)
cons = Conservazione(cfg, REG, log=righe_log.append)
st = studio(cfg)
st.imposta_giorno(LEO, "2026-11-03", 0, "senza_scuola")
st.imposta_giorno(BRUNO, "2026-11-03", 20)
st.close()
r = cons.svuota("l1", "Leo")
db = sqlite3.connect(cfg.memory_db)
g_l = db.execute("SELECT COUNT(*) FROM studio_giorni WHERE persona='l1'").fetchone()[0]
g_b = db.execute("SELECT COUNT(*) FROM studio_giorni WHERE persona='b1'").fetchone()[0]
db.close()
verifica("svuota di Leo: anche l'archiviata e i suoi giorni, Bruno resta",
         r["studio"] == 1 and quante("l1") == 0 and quante("b1") == 1 and g_l == 0
         and g_b == 1)
r = cons.svuota()
db = sqlite3.connect(cfg.memory_db)
g_t = db.execute("SELECT COUNT(*) FROM studio_giorni").fetchone()[0]
db.close()
verifica("svuota di tutti: lo Studio vuoto, giorni compresi",
         r["studio"] == 1 and quante() == 0 and g_t == 0)
from calliope.tools import conversazioni as TC  # noqa: E402
cfg_d = cfg_nuova("frasi.db")
st = studio(cfg_d)
carica(st, LEO, "storia")
st.close()


class Ctx:
    cfg = cfg_d


verifica("«dimentica»: la domanda e la frase dicono lo Studio quando c'è da togliere",
         TC._studio_da_dimenticare(Ctx, "l1") and not TC._studio_da_dimenticare(Ctx, "b1")
         and "verifiche dello Studio, tranne quelle archiviate" in TC.STUDIO_DOMANDA
         and "archiviate restano" in TC.STUDIO_TOLTO
         and TC.DIMENTICA_DOMANDA.replace("Cancello", TC.STUDIO_DOMANDA + " Cancello", 1)
         != TC.DIMENTICA_DOMANDA)
src_tc = (QUI.parent / "calliope" / "tools" / "conversazioni.py").read_text("utf-8")
verifica("«dimentica»: il conto dello Studio prima di cancellare, la frase dopo",
         src_tc.index("studio = _studio_da_dimenticare(ctx, persona)")
         < src_tc.index("n = arch.dimentica(persona)")
         and "STUDIO_NON_TOLTO if rimaste else STUDIO_TOLTO" in src_tc)
src = (QUI.parent / "calliope" / "main.py").read_text("utf-8")
verifica("main.py lega «dimentica le nostre conversazioni» allo Studio (archiviate escluse)",
         "conv_arch.su_dimentica.append(_studio_dimentica)" in src
         and "archiviate=False" in src)
cfg_vuota = cfg_nuova("mai.db")
verifica("rotazione e svuota senza le tabelle dello Studio (mai usato): niente errori",
         Conservazione(cfg_vuota, REG, log=righe_log.append).ruota(
             oggi=datetime.date(2027, 1, 1))["studio"]["verifiche"] == 0)

# ═══════════════════════════ 6. l'interruttore ═══════════════════════════
print("— l'interruttore")
val = VALIDATORI["studio_modo"]
verifica("studio_modo: spento di serie", Config().studio_modo == "spento")
verifica("studio_modo: i tre modi validi, il true di YAML rifiutato, il false spento",
         [val(x) for x in ("spento", "ombra", "attivo")] == ["spento", "ombra", "attivo"]
         and solleva(lambda: val(True), ValueError) and val(False) == "spento")
verifica("spento: niente servizio", S.prepara(cfg_nuova("sp.db", modo="spento")) is None
         and not (TMP / "sp.db").exists())
righe_log.clear()
st = S.prepara(cfg_nuova("om.db", modo="ombra"), registry=REG, log=righe_log.append)
st.adesso = lambda: ORA[0]
vo, _ = carica(st, LEO, "storia")
verifica("ombra: i dati si scrivono e il piano si calcola",
         len(st.piano(LEO, vo)["giorni"]) == 7)
verifica("ombra: niente al modello né agli schermi", not st.per_modello()
         and not st.per_schermi())
verifica("ombra: le misure contate", st.stato()["piani"] >= 1
         and st.stato()["verifiche_create"] == 1 and st.stato()["modo"] == "ombra")
verifica("ombra: le righe del registro senza nomi, materie né titoli",
         righe_log and all("(ombra)" in x for x in righe_log)
         and not any(w in x for x in righe_log for w in ("Leo", "Storia", "Colombo", "Appunti",
                                                          "scoperte")))
st.close()
st = S.prepara(cfg_nuova("at.db", modo="attivo"), registry=REG, log=righe_log.append)
verifica("attivo: per il modello e gli schermi (passo 4.5)", st.per_modello()
         and st.per_schermi())
st.close()
verifica("un modo sconosciuto vale spento", S.modo(cfg_nuova(modo="acceso")) == "spento")
righe_log.clear()
st = studio(cfg_nuova("fascia.db", studio_fascia="20:00-15:00"))
verifica("studio_fascia scritta male: una riga nel registro e la fascia di serie",
         st.fascia == (900, 1200) and any("studio_fascia" in x for x in righe_log))
st.close()
from calliope.config import load_config  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402
(TMP / "c.yaml").write_text("studio:\n  studio_fascia: pomeriggio\n", encoding="utf-8")
vecchio_locale = os.environ.get("CALLIOPE_CONFIG_LOCALE")
os.environ["CALLIOPE_CONFIG_LOCALE"] = str(TMP / "nessuno.yaml")
uscita = io.StringIO()
with contextlib.redirect_stdout(uscita), contextlib.redirect_stderr(uscita):
    cc = load_config(str(TMP / "c.yaml"))
if vecchio_locale is None:
    os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
else:
    os.environ["CALLIOPE_CONFIG_LOCALE"] = vecchio_locale
verifica("studio_fascia sbagliata nel file: segnalata come le altre chiavi, resta la serie",
         cc.studio_fascia == "15:00-20:00" and "studio_fascia" in uscita.getvalue())
verifica(".gitignore tiene fuori la cartella dello Studio",
         "/studio/" in (QUI.parent / ".gitignore").read_text("utf-8").splitlines())

sys.exit(1 if errori else 0)
