import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Le prove dello Studio a secco (31/10, passo 8, issue #248, epic #251, decisione 0035 punto 40;
calliope/studio/risposte.py, unita.py, prove.py, servizio.py, tools/studio.py, schermi/server.py).
Niente modello, un orologio finto, persone di fantasia (Leo, il tutore Andrea, Bruno adulto).

1. **Le risposte**: scelta multipla, vero o falso, numero con l'unità, parole chiave, carta,
   aperta, «non lo so», vuota; coi casi contrari (un'altra opzione, negata, un'altra grandezza,
   due numeri, un elenco di parole, «no» fuori dal vero o falso).
2. **Le domande**: la forma (`prepara`), scritte dalla persona e dal tutore, permessi, il tetto.
3. **La verifica finta**: solo la persona; la vista senza risposte attese né esiti; rispondi,
   consegna coi tentativi «verifica_finta» fonte «codice»; **gli imbrogli**: consegna doppia,
   rispondere dopo la consegna o dopo il tempo, carte e domande nascoste mentre è aperta, la
   prova di un'altra verifica, il tutore che risponde; il tempo scaduto; «da rivedere» deciso una
   volta (persona col peso dimezzato, tutore); la misura «l'ultima prova».
4. **La verifica che si chiude**: «conclusa», la data passata, «archivia», `imposta` che riapre:
   la prova si chiude davvero, «annullata», senza tentativi.
5. **Il mix**: uniforme in ombra, pesato dalla padronanza mostrata, le usate meno prima.
6. **Il tipo e la finestra «dal»**: interrogazione da una data, i giorni nella finestra, la fine.
7. **L'orale** dal registro dei tool (`studio_interroga`): la domanda in un turno, la risposta nel
   turno dopo dalla frase della persona (mai dalla proposta del modello), la correzione e la
   domanda dopo nello stesso risultato, «basta», il tutore no, le pagine chiuse durante l'orale,
   la frase al tutore in terza persona.
8. **Tenuta**: domande e prove vanno via con la verifica, «dimentica», «svuota»; lo schema 10.
9. **L'endpoint** `/api/studio/prova` col server vero.

    python prove/prova_studio_prove.py
"""

import datetime
import json
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import politica, valore  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi import tocchi as T  # noqa: E402
from calliope.studio import dati as D  # noqa: E402
from calliope.studio import padronanza as PD  # noqa: E402
from calliope.studio import prove as PV  # noqa: E402
from calliope.studio import risposte as RS  # noqa: E402
from calliope.studio import unita as U  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

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
    def __init__(self, pid, name, admin=False, nascita=None, tutori=()):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, None
        self.level = "amministra" if admin else "familiare"


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
REG = Registro(ANDREA, BRUNO, CARLA, LEO)
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-prove-"))
ORA = [datetime.datetime(2026, 10, 29, 16, 0)]          # giovedì 29/10, verifica il 5/11
registro: list = []


def cfg_nuova(nome, modo="attivo", padronanza="ombra"):
    c = Config()
    c.memory_db = str(TMP / nome)
    c.studio_modo = modo
    c.studio_cartella = str(TMP / "studio")
    c.turn_log_dir = str(TMP / "registro")
    c.studio_lettura = False
    c.studio_padronanza = padronanza
    return c


def studio(cfg):
    st = S.Studio(cfg, registry=REG, log=registro.append, adesso=lambda: ORA[0])
    st.avvia_lettura(None, avvia=False)
    return st


def carica(st, chi=LEO, data="2026-11-05", **kw):
    """Una verifica con due argomenti del piano e sei domande, una per tipo."""
    vid = st.crea_verifica(chi, "Storia", data, persona="l1", **kw)
    a1 = st.aggiungi_argomento(chi, vid, "Colombo", [], proposto=False)
    a2 = st.aggiungi_argomento(chi, vid, "Magellano", [], proposto=False)
    st.conferma_argomenti(chi, vid)
    d = [st.aggiungi_domanda(chi, vid, "scelta", "Da dove partì Colombo?", "Palos",
                             ["Palos", "Lisbona", "Genova"], argomento=a1),
         st.aggiungi_domanda(chi, vid, "vero_falso", "Magellano finì il giro del mondo.",
                             "falso", argomento=a2),
         st.aggiungi_domanda(chi, vid, "numero", "In che anno partì Colombo?", "1492",
                             argomento=a1),
         st.aggiungi_domanda(chi, vid, "parole", "Chi completò il giro?", "Juan Sebastián "
                             "Elcano", chiave=["Elcano"], argomento=a2),
         st.aggiungi_domanda(chi, vid, "aperta", "Perché le spezie erano preziose?",
                             "Servivano a conservare i cibi", argomento=a2)]
    return vid, a1, a2, d


GIUSTE = {"Da dove partì Colombo?": "a", "Magellano finì il giro del mondo.": "falso",
          "In che anno partì Colombo?": "1492", "Chi completò il giro?": "Elcano",
          "Perché le spezie erano preziose?": "per conservare il cibo",
          "Colombo era genovese.": "vero",
          "Chi diede il nome all'America?": "Vespucci"}


def tentativi(st, vid=None) -> list[dict]:
    q = "SELECT * FROM studio_tentativi" + (" WHERE verifica = ?" if vid else "") + " ORDER BY id"
    return st.dati.tutti(q, (vid,) if vid else ())


# ═══════════════════════════ 1. le risposte ═══════════════════════════
print("— le risposte")
sc = RS.prepara("scelta", "Da dove partì Colombo?", "b", ["Lisbona", "Palos", "Genova"])
verifica("scelta: la lettera attesa diventa l'opzione; la lettera, «la b», il testo intero",
         sc["attesa"] == "Palos" and RS.valuta(sc, "b") == ("giusto", "codice")
         and RS.valuta(sc, "la b")[0] == "giusto" and RS.valuta(sc, "Palos")[0] == "giusto"
         and RS.valuta(sc, "credo Palos")[0] == "giusto"
         and RS.valuta(sc, "la risposta è la b")[0] == "giusto")
verifica("scelta, contrari: un'altra opzione o più opzioni «sbagliato» (PR #342); negata, "
         "niente o una lettera che non c'è «da rivedere»", RS.valuta(sc, "a") == ("sbagliato", "codice")
         and RS.valuta(sc, "Genova")[0] == "sbagliato"
         and RS.valuta(sc, "non la b")[0] == "da_rivedere"
         and RS.valuta(sc, "Venezia")[0] == "da_rivedere"
         and RS.valuta(sc, "Palos o Lisbona")[0] == "sbagliato"
         and RS.valuta(sc, "a o b")[0] == "sbagliato"
         and RS.valuta(sc, "a b c")[0] == "sbagliato"
         and RS.valuta(sc, "f")[0] == "da_rivedere")
verifica("le lettere dette a voce, solo come forma chiusa per intero (PR #342, punto 5)",
         RS.valuta(sc, "bi")[0] == "giusto" and RS.valuta(sc, "la bi")[0] == "giusto"
         and RS.valuta(sc, "Calliope, la bi")[0] == "giusto"
         and RS.valuta(sc, "ci")[0] == "sbagliato" and RS.valuta(sc, "di")[0] == "da_rivedere"
         and RS.valuta(sc, "effe")[0] == "da_rivedere"
         and RS.valuta(sc, "io di storia non so niente")[0] == "da_rivedere")
verifica("scelta: due opzioni uguali o la giusta fuori dalle opzioni sono rifiutate",
         solleva(lambda: RS.prepara("scelta", "x?", "Palos", ["Palos", "palos"]), ValueError)
         and solleva(lambda: RS.prepara("scelta", "x?", "Roma", ["Palos", "Genova"]), ValueError)
         and solleva(lambda: RS.prepara("scelta", "x?", "a", ["Palos"]), ValueError))
vf = RS.prepara("vero_falso", "Colombo partì nel 1492.", "Vero")
verifica("vero o falso: forme chiuse dette per intero (principio 10)",
         vf["attesa"] == "vero" and RS.valuta(vf, "vero")[0] == "giusto"
         and RS.valuta(vf, "sì, è vero")[0] == "giusto" and RS.valuta(vf, "Calliope, vero")[0]
         == "giusto" and RS.valuta(vf, "falso")[0] == "sbagliato"
         and RS.valuta(vf, "no")[0] == "sbagliato" and RS.valuta(vf, "non è vero")[0]
         == "sbagliato")
verifica("vero o falso, contrari: una parola dentro una frase non basta",
         RS.valuta(vf, "vero, ma non sono sicuro che fosse il 1492")[0] == "da_rivedere"
         and RS.valuta(vf, "è vero che partì da Palos")[0] == "da_rivedere"
         and solleva(lambda: RS.prepara("vero_falso", "x", "forse"), ValueError))
nm = RS.prepara("numero", "Velocità?", "2,5 m/s")
verifica("numero con l'unità: cifre, lettere, conversione nella stessa grandezza, 1 %",
         RS.valuta(nm, "2,5 metri al secondo")[0] == "giusto"
         and RS.valuta(nm, "due virgola cinque m/s")[0] == "giusto"
         and RS.valuta(nm, "9 chilometri orari")[0] == "giusto"
         and RS.valuta(nm, "2.52 m/s")[0] == "giusto")
verifica("numero, contrari: un'altra grandezza, un altro valore o due numeri «sbagliato» (PR "
         "#342), senza unità «indizio», nessun numero «da rivedere»",
         RS.valuta(nm, "2,5 kg")[0] == "sbagliato" and RS.valuta(nm, "3 m/s")[0] == "sbagliato"
         and RS.valuta(nm, "2,5")[0] == "indizio" and RS.valuta(nm, "2 o 3 m/s")[0] ==
         "sbagliato" and RS.valuta(nm, "boh, veloce")[0] == "da_rivedere")
verifica("vero o falso tutti e due nella risposta «sbagliato»; «non lo so» anche sul vero o falso",
         RS.valuta(vf, "boh vero o falso")[0] == "sbagliato"
         and RS.valuta(vf, "non lo so") == ("sbagliato", "persona"))
an = RS.prepara("numero", "Anno?", "1492")
verifica("un intero sotto il tetto della tolleranza: anno esatto, in lettere",
         RS.valuta(an, "nel 1492")[0] == "giusto"
         and RS.valuta(an, "millequattrocentonovantadue")[0] == "giusto"
         and RS.valuta(an, "1493")[0] == "sbagliato"
         and RS.valuta(RS.prepara("numero", "Quanti?", "12"), "13")[0] == "sbagliato")
verifica("unità: leggi e confronta",
         U.una_misura("36 km/h") == (36.0, "km/h") and U.una_misura("5 o 6") is None
         and U.confronta((36.0, "km/h"), (10.0, "m/s")) == "giusto"
         and U.confronta((3.0, "kg"), (3.0, "m")) == "sbagliato"
         and U.una_misura("1.861") == (1861.0, None)
         and U.una_misura("tre e mezzo") == (3.5, None))
pa = RS.prepara("parole", "Cosa trovò Colombo?", "Il Nuovo Mondo, cioè l'America",
                chiave=["Nuovo Mondo", "America"])
verifica("parole chiave: tutte «giusto», metà «indizio», storpiate o con la stessa radice",
         RS.valuta(pa, "il nuovo mondo, l'America")[0] == "giusto"
         and RS.valuta(pa, "l'America")[0] == "indizio"
         and RS.valuta(pa, "il nuovo mondo cioè l'Amerika")[0] == "giusto"
         and RS.valuta(RS.prepara("parole", "Chi?", "Magellano", chiave=["Magellano"]),
                       "Magelano")[0] == "giusto")
verifica("parole chiave, contrari: negate, assenti o un elenco lungo «da rivedere», mai "
         "«sbagliato»", RS.valuta(pa, "non il nuovo mondo e non l'America")[0] == "da_rivedere"
         and RS.valuta(pa, "l'India")[0] == "da_rivedere"
         and RS.valuta(pa, " ".join(["America nuovo mondo India Cina Giappone Africa Europa"] * 4)
                       )[0] == "da_rivedere")
verifica("parole chiave: senza chiavi, le parole piene della risposta (al più 5)",
         RS.prepara("parole", "Chi?", "Amerigo Vespucci")["chiave"] == ["amerigo", "vespucci"]
         and solleva(lambda: RS.prepara("parole", "Chi?", "un"), ValueError))
car = {"tipo": "carta", "attesa": "Vespucci", "chiusa": "vespucci"}
verifica("carta: la risposta chiusa «giusto», altrimenti «da rivedere»",
         RS.valuta(car, "Amerigo Vespucci") == ("giusto", "codice")
         and RS.valuta(car, "Colombo") == ("da_rivedere", None))
ap = RS.prepara("aperta", "Perché?", "Servivano a conservare i cibi")
verifica("aperta: sempre «da rivedere»; «non lo so» «sbagliato» della persona; niente «vuota»",
         RS.valuta(ap, "per conservare i cibi") == ("da_rivedere", None)
         and RS.valuta(ap, "non lo so") == ("sbagliato", "persona")
         and RS.valuta(sc, "boh") == ("sbagliato", "persona")
         and RS.valuta(ap, "") == ("vuota", None) and RS.valuta(ap, "  ...  ") == ("vuota", None))
verifica("«no» fuori dal vero o falso non è «non lo so»", RS.valuta(ap, "no")[0] == "da_rivedere")
verifica("la forma: una riga, senza caratteri di controllo, al più il tetto",
         RS.prepara("aperta", "Chi\n‮ era?\x00", "x")["testo"] == "Chi era?"
         and len(RS.prepara("aperta", "x" * 999, "y")["testo"]) == RS.TESTO_MAX
         and solleva(lambda: RS.prepara("boh", "x", "y"), ValueError))

# ═══════════════════════════ 2. le domande ═══════════════════════════
print("— le domande")
st = studio(cfg_nuova("prove.db"))
vid, a1, a2, dd = carica(st)
verifica("domande scritte dalla persona, coi numeri degli argomenti",
         len(st.domande(LEO, vid)["domande"]) == 5
         and st.domande(LEO, vid)["domande"][0]["argomento_numero"] == 1)
did = st.aggiungi_domanda(ANDREA, vid, "vero_falso", "Colombo era genovese.", "vero",
                          argomento=a1)
verifica("il tutore scrive una domanda per il minore", st.domande(ANDREA, vid)["domande"][-1][
    "id"] == did)
verifica("un altro adulto no: NonTrovata", solleva(lambda: st.domande(BRUNO, vid), S.NonTrovata)
         and solleva(lambda: st.aggiungi_domanda(BRUNO, vid, "aperta", "x", "y"), S.NonTrovata))
verifica("un argomento di un'altra verifica no",
         solleva(lambda: st.aggiungi_domanda(LEO, vid, "aperta", "x", "y", argomento=999),
                 S.NonTrovata))
st.segna_domanda(LEO, did, False)
verifica("togli e rimetti", st.domande(LEO, vid)["domande"][-1]["stato"] == "tolta")
st.segna_domanda(LEO, did, True)
verifica("nel registro solo id e tipo, mai il testo",
         not any("Colombo era" in r or "Palos" in r for r in registro)
         and any("domanda" in r and "vero_falso" in r for r in registro))

# ═══════════════════════════ 3. la verifica finta ═══════════════════════════
print("— la verifica finta")
verifica("solo la persona la fa: il tutore no", solleva(lambda: st.inizia_prova(ANDREA, vid),
                                                         ValueError))
p = st.inizia_prova(LEO, vid)
pid = p["id"]
testo = json.dumps(p, ensure_ascii=False)
verifica("la vista aperta non ha mai la risposta attesa né l'esito",
         p["stato"] == "aperta" and len(p["voci"]) == 6
         and all("attesa" not in x and "esito" not in x for x in p["voci"])
         and "Elcano" not in testo and "Servivano" not in testo and p["secondi"] == 1200,
         testo[:200])
verifica("una sola prova aperta per verifica: la stessa si riprende, l'orale no",
         st.inizia_prova(LEO, vid)["id"] == pid
         and solleva(lambda: st.inizia_prova(LEO, vid, "orale"), ValueError))
k = st.aggiungi_carta(LEO, vid, "Chi diede il nome all'America?", "Vespucci", argomento=a1)
verifica("mentre la prova è aperta: carte e domande nascoste alla persona (al tutore senza le risposte; a voce nessuno, PR #348)",
         st.carte(LEO, vid) == [] and st.domande(LEO, vid) == {"domande": [], "nascoste": True}
         and st._conto_carte(st.verifica(LEO, vid))["totali"] == 0
         and solleva(lambda: st._carta(LEO, k), S.NonTrovata)
         and solleva(lambda: st.prossima_carta(LEO, vid), S.servizio.CarteFerme)
         and len(st.carte(ANDREA, vid)) == 1 and st.domande(ANDREA, vid)["domande"])
verifica("…e niente «conferma le domande» per la persona",
         solleva(lambda: st.conferma_domande(LEO, vid), ValueError))
for x in p["voci"]:
    st.rispondi_prova(LEO, pid, x["n"], GIUSTE.get(x["testo"], "boh"))
verifica("il tutore non risponde al posto del minore",
         solleva(lambda: st.rispondi_prova(ANDREA, pid, 1, "x"), ValueError))
verifica("la risposta salvata torna nella vista, senza esito",
         st.vista_prova(LEO, pid)["voci"][0]["risposta"] is not None
         and "esito" not in st.vista_prova(LEO, pid)["voci"][0])
n0 = len(tentativi(st))
r = st.consegna_prova(LEO, pid)
es = {x["testo"]: x["esito"] for x in r["voci"]}
t = tentativi(st)[n0:]
verifica("consegna: il codice decide, l'aperta resta da rivedere",
         es["Da dove partì Colombo?"] == "giusto" and es["In che anno partì Colombo?"] == "giusto"
         and es["Magellano finì il giro del mondo."] == "giusto"
         and es["Chi completò il giro?"] == "giusto"
         and es["Perché le spezie erano preziose?"] == "da_rivedere", es)
verifica("i tentativi: tipo «verifica_finta», fonte «codice», uno per voce decisa",
         len(t) == 5 and all(x["tipo"] == "verifica_finta" and x["fonte"] == "codice"
                             for x in t), t)
verifica("dopo la consegna la correzione ha le risposte attese",
         any(x["attesa"] == "a) Palos" for x in r["voci"]) and r["riepilogo"]["punteggio"] == 100)
verifica("consegna doppia: la stessa correzione, nessun tentativo nuovo",
         st.consegna_prova(LEO, pid)["stato"] == "consegnata" and len(tentativi(st)) == n0 + 5)
verifica("rispondere dopo la consegna: rifiutato, la risposta non cambia",
         solleva(lambda: st.rispondi_prova(LEO, pid, 1, "z"), ValueError)
         and st.vista_prova(LEO, pid)["voci"][0]["risposta"] != "z")
verifica("chiusa la prova, carte e domande tornano", len(st.carte(LEO, vid)) == 1
         and st.domande(LEO, vid)["nascoste"] is False)
mis = st.dati.tutti("SELECT * FROM studio_misure WHERE verifica = ? AND fonte = "
                    "'verifica_finta'", (vid,))
verifica("la misura «l'ultima prova» nel piano", len(mis) == 1
         and st.piano(LEO, vid)["livello"] == 100, mis)
nap = next(x["n"] for x in r["voci"] if x["esito"] == "da_rivedere")
verifica("«da rivedere»: un esito sconosciuto no, una voce già decisa no",
         solleva(lambda: st.rivedi_voce(LEO, pid, nap, "boh"), ValueError)
         and solleva(lambda: st.rivedi_voce(LEO, pid, next(
             x["n"] for x in r["voci"] if x["esito"] == "giusto"), "giusto"), ValueError))
st.rivedi_voce(LEO, pid, nap, "indizio")
t = tentativi(st)
verifica("la persona decide «da rivedere»: fonte «persona», una volta sola",
         t[-1]["fonte"] == "persona" and t[-1]["esito"] == "indizio"
         and solleva(lambda: st.rivedi_voce(ANDREA, pid, nap, "giusto"), ValueError))
verifica("il peso dell'autovalutazione su una prova è la metà (padronanza)",
         PD.calcola([{"argomento": 1, "giorno": "2026-10-28", "tipo": "verifica_finta",
                      "esito": "giusto", "fonte": "codice"},
                     {"argomento": 1, "giorno": "2026-10-29", "tipo": "verifica_finta",
                      "esito": "sbagliato", "fonte": "persona"},
                     {"argomento": 1, "giorno": "2026-10-29", "tipo": "verifica_finta",
                      "esito": "giusto", "fonte": "codice"}], "2026-10-29")[1]["valore"]
         > PD.calcola([{"argomento": 1, "giorno": "2026-10-28", "tipo": "verifica_finta",
                        "esito": "giusto", "fonte": "codice"},
                       {"argomento": 1, "giorno": "2026-10-29", "tipo": "verifica_finta",
                        "esito": "sbagliato", "fonte": "tutore"},
                       {"argomento": 1, "giorno": "2026-10-29", "tipo": "verifica_finta",
                        "esito": "giusto", "fonte": "codice"}], "2026-10-29")[1]["valore"])
# Il tempo scaduto
p2 = st.inizia_prova(LEO, vid)
st.rispondi_prova(LEO, p2["id"], 1, GIUSTE.get(p2["voci"][0]["testo"], "x"))
ORA[0] = ORA[0] + datetime.timedelta(minutes=21)
verifica("dopo il tempo: rispondere è rifiutato", solleva(
    lambda: st.rispondi_prova(LEO, p2["id"], 2, "x"), ValueError))
v2 = st.vista_prova(LEO, p2["id"])
verifica("il tempo scaduto chiude la prova con le risposte date: le altre «vuote», senza "
         "tentativo", v2["stato"] == "scaduta" and sum(x["esito"] == "vuota" for x in v2["voci"])
         == len(v2["voci"]) - 1 and v2["riepilogo"]["totali"]["vuota"] == len(v2["voci"]) - 1,
         v2.get("riepilogo"))
verifica("la frase del codice: conti e argomenti col numero, mai il testo",
         "risposto giusto" in v2["frase"] and "Colombo" not in v2["frase"]
         and "Palos" not in v2["frase"], v2["frase"])
verifica("al tutore in terza persona col nome",
         st.vista_prova(ANDREA, p2["id"])["frase"].startswith("Leo ha risposto"))
verifica("la prova di un'altra persona: NonTrovata per un altro adulto",
         solleva(lambda: st.vista_prova(BRUNO, pid), S.NonTrovata))
verifica("poche domande: la prova non parte", solleva(lambda: st.inizia_prova(
    BRUNO, st.crea_verifica(BRUNO, "Inglese", "2026-11-10")), ValueError))

# ═══════════════════════════ 4. la verifica che si chiude ═══════════════════════════
print("— la verifica che si chiude")
for come in ("conclusa", "data", "archivia", "riapre"):
    ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
    s2 = studio(cfg_nuova(f"chiude_{come}.db"))
    v, b1, b2, _d = carica(s2)
    q = s2.inizia_prova(LEO, v)
    for x in q["voci"]:
        s2.rispondi_prova(LEO, q["id"], x["n"], GIUSTE.get(x["testo"], "x"))
    if come == "conclusa":
        s2.conclusa(LEO, v)
    elif come == "archivia":
        s2.archivia(LEO, v)
    else:
        ORA[0] = datetime.datetime(2026, 11, 6, 10, 0)
        s2.ricalcola(v)
        if come == "riapre":
            s2.imposta(LEO, v, data="2026-11-20")
    stato = s2.dati.uno("SELECT stato FROM studio_prove WHERE id = ?", (q["id"],))["stato"]
    verifica(f"{come}: la prova si chiude davvero, «annullata», senza tentativi",
             stato == "annullata" and not tentativi(s2)
             and solleva(lambda: s2.consegna_prova(LEO, q["id"]), Exception) is False
             and s2.consegna_prova(LEO, q["id"])["stato"] == "annullata" and not tentativi(s2),
             stato)
    s2.close()

# ═══════════════════════════ 5. il mix ═══════════════════════════
print("— il mix")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
s3 = studio(cfg_nuova("mix.db"))
v3 = s3.crea_verifica(LEO, "Storia", "2026-11-05")
b = [s3.aggiungi_argomento(LEO, v3, f"Arg {i}", [], proposto=False) for i in range(3)]
s3.conferma_argomenti(LEO, v3)
for i, a in enumerate(b):
    for j in range(6):
        s3.aggiungi_domanda(LEO, v3, "numero", f"Quanto fa {i} più {j}?", str(i + j), argomento=a)
pool = s3._pool(s3.verifica(LEO, v3))
scelte, mix = s3._mix(s3.verifica(LEO, v3), pool, 9, 7)
verifica("in ombra il mix è uniforme (3, 3, 3)", mix["modo"] == "uniforme"
         and sorted(mix["quote"].values()) == [3, 3, 3])
verifica("quote pesate: più domande sull'argomento più debole",
         PV.Prove._quote({1: 3, 2: 1, 3: 2}, {1: [0] * 9, 2: [0] * 9, 3: [0] * 9}, 12)
         == {1: 6, 2: 2, 3: 4})
verifica("quote: non più di quelle che ci sono",
         PV.Prove._quote({1: 3, 2: 1}, {1: [0] * 2, 2: [0] * 9}, 6) == {1: 2, 2: 4})
s3.modo_padronanza = PD.MOSTRATA
for g in ("2026-10-27", "2026-10-28", "2026-10-29"):
    for a, e in ((b[0], "sbagliato"), (b[1], "giusto"), (b[2], "indizio")):
        s3.registra_tentativo(LEO, v3, a, "carta", e, "persona", giorno=g)
_s, mix2 = s3._mix(s3.verifica(LEO, v3), pool, 6, 7)
verifica("con la padronanza mostrata il mix pesa: «da studiare» 3, «quasi» 2, «la sai» 1",
         mix2["modo"] == "padronanza"
         and [mix2["quote"][str(a)] for a in b] == [3, 1, 2], mix2)
s3.modo_padronanza = PD.OMBRA
s3.cfg.studio_prova_domande = 9
q3 = s3.inizia_prova(LEO, v3)
s3.consegna_prova(LEO, q3["id"])
q4 = s3.inizia_prova(LEO, v3)
usate = {x["testo"] for x in q3["voci"]}
verifica("la prova dopo prende prima le domande usate meno",
         not usate & {x["testo"] for x in q4["voci"]})
s3.close()

# ═══════════════════════════ 6. il tipo e la finestra ═══════════════════════════
print("— il tipo e la finestra «dal»")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
s4 = studio(cfg_nuova("finestra.db"))
v4 = s4.crea_verifica(LEO, "Storia", "2026-11-02", prova="interrogazione", finestra=True)
x4 = s4.verifica(LEO, v4)
verifica("interrogazione dal 2/11: la finestra dura 14 giorni", x4["prova"] == "interrogazione"
         and x4["finestra"] == 1 and x4["fine"] == "2026-11-16" and not x4["in_finestra"])
verifica("la finestra solo per l'interrogazione; un tipo sconosciuto no",
         s4.verifica(LEO, s4.crea_verifica(LEO, "Arte", "2026-11-02", finestra=True))[
             "finestra"] == 0
         and solleva(lambda: s4.crea_verifica(LEO, "Arte", "2026-11-02", prova="orale"),
                     ValueError))
s4.aggiungi_argomento(LEO, v4, "Colombo", [], proposto=False)
s4.conferma_argomenti(LEO, v4)
ORA[0] = datetime.datetime(2026, 11, 5, 16, 0)
pi = s4.piano(LEO, v4)
x4 = s4.verifica(LEO, v4)
verifica("nella finestra: la verifica resta aperta, l'avviso «finestra», mai giorni negativi",
         pi["stato"] == "aperta" and "finestra" in pi["avvisi"] and x4["in_finestra"]
         and x4["giorni_mancanti"] == 0, (pi["stato"], pi["avvisi"]))
ORA[0] = datetime.datetime(2026, 11, 17, 16, 0)
verifica("passata la fine: fatta", s4.piano(LEO, v4)["stato"] == "fatta")
s4.imposta(LEO, v4, data="2026-11-20", prova="scritta")
verifica("tornata scritta: niente finestra", s4.verifica(LEO, v4)["finestra"] == 0)
s4.close()

# ═══════════════════════════ 7. l'orale dal registro dei tool ═══════════════════════════
print("— l'orale a voce")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st = studio(cfg_nuova("orale.db"))
vid, a1, a2, dd = carica(st)
TOOLS = ToolRegistry()
for spec in TS.studio_specs():
    TOOLS.register(spec)


def ctx_di(prof, come="voce", turno=1, frase=""):
    sc_ = types.SimpleNamespace(current_speaker=prof.name if prof else None, identified_by=come,
                                minore_incerto=None,
                                current_level=prof.level if prof else "ospite",
                                profile_level=prof.level if prof else "ospite")
    ctx = ToolContext(cfg=st.cfg, speakers=REG, speaker_ctx=sc_, speaker=None)
    ctx.studio = st
    ctx.turno = turno
    ctx.user_text = frase
    return ctx


def chiama(ctx, nome, **args) -> dict:
    return json.loads(TOOLS.call(nome, args, ctx, "familiare"))


cl = politica.classe_di("studio_interroga")
verifica("studio_interroga: classe «sicuro» con la fonte «foto», non fidato, mai toccabile",
         cl.classe == politica.SICURO and politica.fonte_di("studio_interroga") == "foto"
         and TOOLS.get("studio_interroga").non_fidato and "studio_interroga" in T.ESCLUSI)
verifica("studio «prove»: una lettura (E0); «tipo» e «conclusa» cambiano",
         valore.effetto("studio", {"azione": "prove"}) == valore.E0 and "prove" in TS.LETTURE
         and "tipo" not in TS.LETTURE and "conclusa" not in TS.LETTURE)
r = chiama(ctx_di(ANDREA, turno=1, frase="interroga Leo"), "studio_interroga", parte="inizia",
           verifica=vid)
verifica("il tutore non fa l'interrogazione al posto del minore", not r["ok"], r)
r = chiama(ctx_di(LEO, turno=1, frase="interrogami di storia"), "studio_interroga",
           parte="inizia")
d1 = r.get("domanda", "")
verifica("inizia: la prima domanda (in busta: è un dato), «1 di 5», senza risposta attesa",
         r["ok"] and r["posizione"] == "1 di 5" and "risposta" not in r and d1, r)
pagina = chiama(ctx_di(LEO, turno=1, frase="leggimi la pagina"), "studio_pagina_leggi",
                pagina="P1")
verifica("durante l'orale le pagine non si leggono a voce", not pagina["ok"]
         and "prova" in pagina.get("errore", ""), pagina)
r = chiama(ctx_di(LEO, turno=1, frase="la sapevo"), "studio_interroga", parte="risposta")
verifica("nello stesso turno della domanda niente esito", not r["ok"]
         and "appena" in r["errore"], r)


def giusta(domanda: str) -> str:
    return next((v for k, v in GIUSTE.items() if domanda.startswith(k)), "boh")


r = chiama(ctx_di(LEO, turno=2, frase=giusta(d1)), "studio_interroga", parte="risposta",
           proposta="sbagliata")
st_p = st.dati.uno("SELECT * FROM studio_prove WHERE modalita = 'orale'")
v1 = json.loads(st_p["voci"])[0]
verifica("la risposta nel turno dopo: l'esito dal codice, la correzione e la domanda dopo",
         r["ok"] and r["risposta"] and r["posizione"] == "2 di 5" and r["domanda"]
         and (r["esito"] == "giusta" or v1["tipo"] == "aperta"), r)
verifica("la proposta del modello resta una misura: non cambia l'esito",
         v1["proposta"] == "sbagliata" and v1["esito"] != "sbagliato"
         and st.misure["prove"]["proposte"] == 1, v1)
turno = 3
fine = None
while True:
    fr = giusta(r["domanda"])
    r = chiama(ctx_di(LEO, turno=turno, frase=fr), "studio_interroga", parte="risposta")
    turno += 1
    if r.get("riepilogo"):
        fine = r
        break
    if not r["ok"] or turno > 12:
        break
t = tentativi(st, vid)
verifica("alla quinta: il riepilogo del codice, i tentativi «interrogazione»",
         fine is not None and "risposto giusto" in fine["riepilogo"]
         and t and all(x["tipo"] == "interrogazione" for x in t), fine)
verifica("dopo la fine niente esiti", not chiama(ctx_di(LEO, turno=20, frase="vero"),
                                                 "studio_interroga", parte="risposta")["ok"])
r = chiama(ctx_di(LEO, turno=21, frase="interrogami ancora"), "studio_interroga",
           parte="inizia")
r2 = chiama(ctx_di(LEO, turno=22, frase="basta così"), "studio_interroga", parte="basta")
verifica("«basta» chiude con le voci valutate (nessuna): nessun tentativo nuovo",
         r2["ok"] and len(tentativi(st, vid)) == len(t), r2)
r = chiama(ctx_di(ANDREA, turno=23, frase="come vanno le prove di Leo?"), "studio",
           azione="prove", verifica=vid)
verifica("al tutore «prove» in terza persona, solo conti", r["ok"] and "di Leo" in
         r["conferma"] and "Palos" not in r["conferma"], r)
r = chiama(ctx_di(LEO, turno=24, frase="mi interrogano da lunedì"), "studio", azione="tipo",
           verifica=vid, prova="interrogazione", finestra=True)
verifica("«tipo»: interrogazione dal …, le due modalità restano", r["ok"]
         and "interrogazione" in r["conferma"] and "tutte e due" in r["conferma"], r)
r = chiama(ctx_di(None, turno=25), "studio_interroga", parte="inizia")
r2 = chiama(ctx_di(LEO, come="conversazione", turno=25), "studio_interroga", parte="inizia")
verifica("ospite e zona grigia no", not r["ok"] and not r2["ok"])
st.close()

# ═══════════════════════════ 8. tenuta e schema ═══════════════════════════
print("— tenuta e schema")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
s5 = studio(cfg_nuova("tenuta.db"))
v5, *_r = carica(s5)
s5.consegna_prova(LEO, s5.inizia_prova(LEO, v5)["id"])
va, *_r = carica(s5)
s5.archivia(LEO, va)


def n_di(t, s=s5):
    return s.dati.uno(f"SELECT COUNT(*) AS n FROM {t}")["n"]


verifica("lo schema alla versione 12 (dai premi, #296), domande e prove fra le tabelle e nella conservazione",
         D.versione_schema(s5.dati.db) == len(D.MIGRAZIONI) == 12
         and {"studio_domande", "studio_prove"} <= set(D.TABELLE)
         and {"studio_domande", "studio_prove"} <= set(
             __import__("calliope.conserva", fromlist=["x"]).TABELLE_STUDIO))
D.cancella(s5.dati.db, persona="l1", archiviate=False)
verifica("«dimentica»: via domande e prove, l'archiviata resta con le sue",
         n_di("studio_prove") == 0 and n_di("studio_domande") == 5)
D.cancella(s5.dati.db, tutto=True)
verifica("«svuota»: niente", n_di("studio_domande") == 0 and n_di("studio_prove") == 0)
s5.close()


# ═══════════════════════════ 9. l'endpoint ═══════════════════════════
def chiedi(port, percorso, sessione=None, token=None, corpo=None):
    h = {"Content-Type": "application/json"}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
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


print("— l'endpoint /api/studio/prova")
from calliope import minori  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402

ORA[0] = datetime.datetime.now().replace(microsecond=0)
for modo in ("attivo", "ombra"):
    cfg = cfg_nuova(f"server_{modo}.db", modo=modo)
    minori.prepara(cfg, registry=REG)
    st = studio(cfg)
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.profilo = REG.by_id
    serv = Servizi()
    serv.studio = st
    hub.servizi = serv
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    port = srv.port
    try:
        tok = {}
        for chi, pid_ in (("leo", "l1"), ("andrea", "a1"), ("bruno", "b1")):
            _, tok[chi] = hub.archivio.crea_con_token("telefono " + chi, proprietario=pid_,
                                                      proprietario_nome=chi.title())
        hub._rinfresca()
        sess = {k: chiedi(port, "/api/accedi", token=t_)[1].get("sessione")
                for k, t_ in tok.items()}
        data = (ORA[0].date() + datetime.timedelta(days=7)).isoformat()
        vid, a1, a2, dd = carica(st, data=data)
        if modo == "ombra":
            s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={"verifica": vid})
            verifica("ombra: il minore non vede le prove (403)", s == 403, f"{s} {d}")
            continue
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={"verifica": vid})
        verifica("la vista: le domande con le risposte attese, nessuna prova aperta",
                 s == 200 and len(d["domande"]) == 5 and d["aperta"] is None
                 and d["domande_pronte"] == 5 and d["prova_vera"] == "scritta", f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["leo"],
                      corpo={"verifica": vid, "azione": "inizia"})
        ap_ = d.get("aperta") or {}
        testo = json.dumps(d, ensure_ascii=False)
        verifica("inizia: la prova aperta senza risposte attese, le domande nascoste",
                 s == 200 and ap_.get("stato") == "aperta" and d["domande_nascoste"]
                 and d["domande"] == [] and "Elcano" not in testo and "Servivano" not in testo
                 and all("attesa" not in x for x in ap_.get("voci", [])), testo[:300])
        pid = ap_.get("id")
        s, d = chiedi(port, "/api/studio/prova", sess["andrea"], corpo={
            "verifica": vid, "azione": "rispondi", "prova": pid, "voce": 1, "risposta": "x"})
        verifica("il tutore non risponde: 400", s == 400, f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["bruno"], corpo={"verifica": vid})
        verifica("un altro adulto: 404", s == 404, f"{s} {d}")
        for x in ap_.get("voci", []):
            chiedi(port, "/api/studio/prova", sess["leo"], corpo={
                "verifica": vid, "azione": "rispondi", "prova": pid, "voce": x["n"],
                "risposta": GIUSTE.get(x["testo"], "x")})
        vb = st.crea_verifica(ANDREA, "Inglese", data)
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vb, "azione": "consegna", "prova": pid})
        verifica("la prova con un'altra verifica nella richiesta: 404", s == 404, f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "consegna", "prova": pid})
        ch = (d.get("chiuse") or [{}])[0]
        verifica("consegna: la correzione con le risposte attese", s == 200
                 and ch.get("stato") == "consegnata" and all("attesa" in x for x in ch["voci"]),
                 f"{s} {str(d)[:300]}")
        n1 = len(tentativi(st))
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "consegna", "prova": pid})
        verifica("consegna doppia: 200 e nessun tentativo nuovo", s == 200
                 and len(tentativi(st)) == n1)
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "rispondi", "prova": pid, "voce": 1, "risposta": "z"})
        verifica("rispondere dopo la consegna: 400", s == 400, f"{s} {d}")
        nap = next((x["n"] for x in ch.get("voci", []) if x["esito"] == "da_rivedere"), None)
        s, d = chiedi(port, "/api/studio/prova", sess["andrea"], corpo={
            "verifica": vid, "azione": "rivedi", "prova": pid, "voce": nap, "esito": "giusto"})
        verifica("il tutore decide una voce da rivedere: fonte «tutore»", s == 200
                 and tentativi(st)[-1]["fonte"] == "tutore", f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "domanda", "tipo": "scelta", "testo": "Capitale?",
            "attesa": "Roma", "opzioni": ["Roma", "Milano"], "argomento": a1})
        verifica("scrivi una domanda dalla pagina", s == 200 and d.get("scritta"), f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "domanda", "tipo": "scelta", "testo": "Capitale?",
            "attesa": "Napoli", "opzioni": ["Roma", "Milano"]})
        verifica("una scelta senza l'opzione giusta: 400", s == 400, f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "tipo", "prova_vera": "interrogazione", "finestra": True})
        verifica("il tipo dalla pagina", s == 200 and d["prova_vera"] == "interrogazione"
                 and d["finestra"], f"{s} {d}")
        s, d = chiedi(port, "/api/studio/prova", sess["leo"], corpo={
            "verifica": vid, "azione": "boh"})
        verifica("un'azione sconosciuta: 400", s == 400)
    finally:
        srv.ferma() if hasattr(srv, "ferma") else None
        st.close()

# ═══════════════════════════ 10. la revisione della PR #342 ═══════════════════════════
print("— la revisione della PR #342")
# La tabella del revisore: tutte risposte giuste (o «indizio» dove manca solo l'unità)
S_ = RS.prepara("scelta", "Chi arrivò in America nel 1492?", "b",
                ["Vasco da Gama", "Cristoforo Colombo", "Magellano", "Marco Polo"])
N_ANNO = RS.prepara("numero", "In che anno?", "1492")
N_VEL = RS.prepara("numero", "Velocità?", "20 m/s")
N_DEC = RS.prepara("numero", "Massa?", "0,125 kg")
N_G = RS.prepara("numero", "g?", "9,8 m/s2")
GIUSTI = [(S_, x) for x in ("b", "la b", "La B.", "bi", "la bi", "B, Cristoforo Colombo",
                            "Calliope, la b", "risposta b", "la risposta è la b",
                            "Cristoforo Colombo")] +     [(N_ANNO, x) for x in ("1492", "millequattrocentonovantadue", "nel 1492", "circa nel 1492",
                           "1.492", "mille quattrocento novantadue", "Calliope, 1492",
                           "il 12 ottobre 1492", "1492 d.C.")] +     [(N_VEL, x) for x in ("20 m/s", "20m/s", "20 metri al secondo", "venti metri al secondo",
                          "72 km/h", "72 chilometri orari", "20 m / s", "20 m s",
                          "20 metri/secondo")] +     [(N_DEC, x) for x in ("0,125 kg", "0.125 kg", "125 g", "125g", "0,125kg",
                          "zero virgola centoventicinque chili")] +     [(N_G, x) for x in ("9,8 m/s2", "9,8 m/s²", "9.8 metri al secondo quadrato", "9,81 m/s^2")]
sbagliati = [(d["attesa"], x, RS.valuta(d, x)) for d, x in GIUSTI if RS.valuta(d, x)[0] != "giusto"]
verifica("la tabella del revisore: tutte giuste (cifra attaccata al simbolo, «0.125», virgola "
         "detta, «m / s», migliaia staccate, il giorno della data)", not sbagliati, sbagliati)
verifica("…e i contrari: «a o b», «1490 o 1491», «20 metri»; «1492 o 1493» e «nel 1492, 500 "
         "anni fa» da rivedere (seconda revisione)",
         RS.valuta(S_, "a o b")[0] == "sbagliato" and RS.valuta(N_ANNO, "1490 o 1491")[0]
         == "sbagliato" and RS.valuta(N_VEL, "20 metri")[0] == "sbagliato"
         and RS.valuta(N_ANNO, "1492 o 1493")[0] == "da_rivedere"
         and RS.valuta(N_ANNO, "nel 1492, 500 anni fa")[0] == "da_rivedere"
         and RS.valuta(N_VEL, "20")[0] == "indizio")
verifica("unità: «0.125» decimale, «1.492» migliaia, «zero virgola centoventicinque»",
         U.una_misura("0.125 kg") == (0.125, "kg") and U.una_misura("1.492") == (1492.0, None)
         and U.una_misura("zero virgola centoventicinque") == (0.125, None)
         and U.una_misura("125g") == (125.0, "g"))
# La seconda revisione della PR #342: le opzioni con la stessa radice e più numeri giusti
SC = [(RS.prepara("scelta", "Dove?", "b", ["Austria", "Australia", "Argentina"]), "Australia",
       "giusto"),
      (RS.prepara("scelta", "Dove?", "b", ["Austria", "Australia", "Argentina"]), "Austria",
       "sbagliato"),
      (RS.prepara("scelta", "Quale?", "a", ["Costantinopoli", "Costantino", "Roma"]),
       "Costantinopoli", "giusto"),
      (RS.prepara("scelta", "Quale?", "a", ["Costantinopoli", "Costantino", "Roma"]),
       "Costantino", "sbagliato"),
      (RS.prepara("scelta", "Anno?", "b", ["1491", "1492", "1493"]), "1492", "giusto"),
      (RS.prepara("scelta", "Anno?", "b", ["1491", "1492", "1493"]), "nel 1492", "giusto"),
      (RS.prepara("scelta", "Anno?", "b", ["1491", "1492", "1493"]), "la b, il 1492", "giusto"),
      (RS.prepara("scelta", "Chi?", "a", ["I Germani", "I Romani", "La Germania"]), "i Germani",
       "giusto"),
      (RS.prepara("scelta", "Chi?", "a", ["I Germani", "I Romani", "La Germania"]), "Germani",
       "giusto"),
      (RS.prepara("scelta", "Dove?", "a", ["Spagna e Portogallo", "Francia", "Inghilterra"]),
       "Spagna e Portogallo", "giusto"),
      (S_, "Colombo e non Magellano", "da_rivedere"), (S_, "a o b", "sbagliato"),
      (S_, "b e basta", "giusto")]
male = [(d["opzioni"], r, RS.valuta(d, r)[0]) for d, r, e in SC if RS.valuta(d, r)[0] != e]
verifica("scelte con la stessa radice (Austria/Australia, Costantinopoli/Costantino, anni): "
         "l'opzione nominata esattamente vince", not male, male)
NN = [("1492", x, "giusto") for x in ("il dodici ottobre 1492", "millequattrocento novantadue",
                                      "1492, cioè nel quindicesimo secolo",
                                      "l'Italia si unì nel 1492 il 17 marzo")] +     [("1492", x, "da_rivedere") for x in ("non 1491 ma 1492", "1491 o 1492", "1492 o 1493",
                                          "nel 1492, 500 anni fa")] +     [("1492", "1490 o 1491", "sbagliato"), ("1492", "nel 1400", "sbagliato"),
     ("20 m/s", "20 m/s cioè 72 km/h", "giusto"),
     ("20 m/s", "20 m/s, ovvero 20 metri al secondo", "giusto"),
     ("0,5", "1/2", "giusto"), ("0,5", "un mezzo", "giusto"), ("0,75", "3/4", "giusto"),
     ("1,5 m", "un metro e mezzo", "giusto"), ("1,5 m", "1 metro e 50 centimetri", "giusto"),
     ("1,5 m", "1,5 metri, cioè 150 centimetri", "giusto"), ("100 °C", "100°C", "giusto"),
     ("5 N", "5 newton, cioè 5 N", "giusto"), ("60 km/h", "60 km/h in 2 ore", "giusto"),
     ("3600 s", "un'ora, cioè 3600 secondi", "giusto"), ("2 h", "2 ore e 30 minuti",
                                                          # sbagliato dal 31/10 (#343)
                                                          "sbagliato"),
     ("2,5 h", "2 ore e mezza", "giusto"), ("12", "12 o 13", "da_rivedere")]
male = [(a, r, RS.valuta(RS.prepara("numero", "q?", a), r)[0]) for a, r, e in NN
        if RS.valuta(RS.prepara("numero", "q?", a), r)[0] != e]
verifica("più numeri: tutti l'atteso o sommati «giusto», alternative senza l'atteso "
         "«sbagliato», il resto «da rivedere»; le frazioni come numeri", not male, male)
# La terza revisione della PR #342 (esiti3.py del revisore)
AU = RS.prepara("scelta", "Dove?", "a", ["Austria", "Australia", "Argentina"])
AB = RS.prepara("scelta", "Dove?", "b", ["Austria", "Australia", "Argentina"])
AT = RS.prepara("scelta", "Anno?", "b", ["1491", "1492", "1493"])
SC3 = [(AU, "la a, no, la c", "da_rivedere"), (AU, "la a no la c", "da_rivedere"),
       (AU, "a, anzi c", "da_rivedere"), (AU, "Austria no Australia", "da_rivedere"),
       (AB, "Austria, no, Australia", "da_rivedere"), (AT, "1492 no 1493", "da_rivedere"),
       (AU, "non è la b, è la a", "giusto"), (AU, "non Australia, Austria", "giusto"),
       (AT, "non il 1491, il 1492", "giusto"), (AU, "Austria e Argentina", "sbagliato"),
       (AU, "la a o forse la b", "sbagliato")]
male = [(d["attesa"], r, RS.valuta(d, r)[0]) for d, r, e in SC3 if RS.valuta(d, r)[0] != e]
verifica("«X, no, Y» e «X, anzi Y» fra due opzioni: da rivedere; «non X, Y» come prima", not male,
         male)
# Il banco del 31/10 (#344): la risposta attesa «Isabella di Castiglia e Ferdinando d'Aragona» era
# «sbagliato» per la «d» di «d'Aragona», presa per l'opzione d. Le lettere dentro la frase: mai
# elise, e solo all'inizio o dopo «la», «è», «o», «anzi», «no»…; la «a» in testa solo se segue
# «o», «anzi», «no»… (altrimenti è la preposizione)
IS = RS.prepara("scelta", "Quali sovrani?", "a", [
    "Isabella di Castiglia e Ferdinando d'Aragona", "Luigi XIV e Maria Antonietta",
    "Carlo V e Filippo II", "Elisabetta I e Giacomo I"])
CA = RS.prepara("scelta", "Dove arrivò?", "c", ["Lisbona", "Palos", "Calicut", "San Salvador"])
SC4 = [(IS, "Isabella di Castiglia e Ferdinando d'Aragona", "giusto"),
       (IS, "Isabella di Castiglia e Ferdinando d’Aragona", "giusto"),
       (IS, "allora, Isabella di Castiglia e Ferdinando d'Aragona", "giusto"),
       (IS, "la a", "giusto"), (IS, "la d", "sbagliato"), (IS, "d", "sbagliato"),
       (IS, "Carlo V e Filippo II", "sbagliato"), (IS, "a o d", "sbagliato"),
       (IS, "la d, anzi la a", "da_rivedere"),
       (CA, "arrivò a Calicut", "giusto"), (CA, "a Calicut", "giusto"),
       (CA, "a San Salvador", "sbagliato"), (CA, "la c", "giusto"), (CA, "c'è Calicut", "giusto"),
       (CA, "Calicut, la c", "giusto"), (CA, "a, anzi c", "da_rivedere"),
       (CA, "a o c", "sbagliato"), (CA, "la a", "sbagliato"), (CA, "non la a, la c", "giusto"),
       # Seconda revisione della PR #346: la preposizione «a» in ogni punto della frase
       (CA, "secondo me a Calicut", "giusto"), (CA, "penso a Calicut", "giusto"),
       (CA, "direi a Calicut", "giusto"), (CA, "boh, a Calicut", "giusto"),
       (CA, "credo a San Salvador", "sbagliato"), (CA, "credo a", "sbagliato"),
       (CA, "penso la a", "sbagliato"), (CA, "la a, no, la c", "da_rivedere")]
male = [(d["attesa"], r, RS.valuta(d, r)[0]) for d, r, e in SC4 if RS.valuta(d, r)[0] != e]
verifica("lettere dentro la frase: «d'Aragona», «c'è» e la preposizione «a» non sono opzioni; «la "
         "a», «a o c», «a, anzi c» sì (banco del 31/10)", not male, male)
# La revisione della PR #346: le risposte giuste di prima restano giuste (opinione, scelta, la
# lettera in fondo dopo una virgola o fra parentesi); «direi c» resta sbagliato
CB = RS.prepara("scelta", "Chi arrivò in America nel 1492?", "b",
                ["Vasco da Gama", "Cristoforo Colombo", "Magellano", "Amerigo Vespucci"])
SC5 = [(CB, r, "giusto") for r in ("direi b", "credo b", "penso b", "secondo me b", "scelgo b",
                                    "scelgo la b", "metto b", "dico b", "sicuramente b", "boh b",
                                    "Colombo, b", "Colombo (b)", "forse b", "b, Colombo")] +       [(CB, "direi c", "sbagliato"), (CB, "credo a", "sbagliato"), (CB, "c, Magellano", "sbagliato"),
       (CB, "Magellano b", "sbagliato"), (CB, "non la b", "da_rivedere"),
       (CB, "la b anzi la c", "da_rivedere")]
male = [(d["attesa"], r, RS.valuta(d, r)[0]) for d, r, e in SC5 if RS.valuta(d, r)[0] != e]
verifica("lettere dopo «direi», «credo», «secondo me», «scelgo»… e in fondo dopo una virgola o fra "
         "parentesi: giuste come prima; «direi c» sbagliato (revisione della PR #346)", not male, male)
# Banco del 31/10 07:02 (#349): un'opzione dentro un'altra. L'opzione uguale all'intera risposta
# vince sempre; un'opzione che sta dentro un'altra nominata nello stesso punto non conta a parte
EQ = RS.prepara("scelta", "Quale equazione?", "x + 3x = 32",
                ["x + 3x = 32", "3x - x = 32", "x + 3 = 32", "3x = 32"])
EQD = RS.prepara("scelta", "Quale equazione?", "3x = 32",
                 ["x + 3x = 32", "3x - x = 32", "x + 3 = 32", "3x = 32"])
SP = RS.prepara("scelta", "Chi firmò?", "Spagna e Portogallo", ["Spagna", "Spagna e Portogallo",
                                                               "Francia"])
SPS = RS.prepara("scelta", "Chi?", "Spagna", ["Spagna", "Spagna e Portogallo", "Francia"])
SC6 = [(EQ, "x + 3x = 32", "giusto"), (EQ, "x+3x=32", "giusto"), (EQ, "la a", "giusto"),
       (EQ, "credo x + 3x = 32", "giusto"), (EQ, "3x = 32", "sbagliato"),
       (EQ, "x + 3 = 32", "sbagliato"), (EQ, "3x - x = 32", "sbagliato"),
       (EQ, "3x = 32 o x + 3x = 32", "sbagliato"), (EQ, "x + 3x = 32 oppure 3x = 32", "sbagliato"),
       (EQD, "3x = 32", "giusto"), (EQD, "x + 3x = 32", "sbagliato"), (EQD, "la d", "giusto"),
       (SP, "Spagna e Portogallo", "giusto"), (SP, "la Spagna e il Portogallo", "giusto"),
       (SP, "Spagna", "sbagliato"), (SP, "Spagna e Francia", "sbagliato"),
       (SP, "Spagna o Francia", "sbagliato"), (SP, "Spagna e Portogallo o Francia", "sbagliato"),
       (SP, "Portogallo e Spagna", "da_rivedere"), (SP, "Spagna, Portogallo", "da_rivedere"),
       (SPS, "Spagna", "giusto"), (SPS, "solo la Spagna", "giusto"),
       (SPS, "Spagna e Portogallo", "sbagliato"), (SPS, "Portogallo e Spagna", "da_rivedere")]
male = [(d["attesa"], r, RS.valuta(d, r)[0]) for d, r, e in SC6 if RS.valuta(d, r)[0] != e]
verifica("un'opzione dentro un'altra (#349): l'opzione uguale alla risposta vince, vince la più "
         "lunga nello stesso punto; due opzioni in punti diversi sbagliato; la più lunga in un "
         "altro ordine da rivedere", not male, male)
# La revisione della PR #350: con delle formule fra le opzioni il confronto tiene gli operatori
# (le opzioni del banco del 31/10 07:02); le parole negate non contano per «l'altro ordine»
# Una formula che non è nessuna opzione: da rivedere, mai giusta né sbagliata dal codice (seconda
# revisione della PR #350); un'altra opzione resta sbagliata
SC7 = [(EQ, "x - 3x = 32", "da_rivedere"), (EQ, "x × 3x = 32", "da_rivedere"),
       (EQ, "x · 3x = 32", "da_rivedere"), (EQ, "3x + x = 32", "da_rivedere"),
       (EQ, "4x = 32", "da_rivedere"), (EQ, "x = 8", "da_rivedere"),
       (EQ, "3x = 32", "sbagliato"), (EQ, "3x - x = 32", "sbagliato"),
       (EQ, "x+3x=32", "giusto"), (EQ, "la risposta è x + 3x = 32", "giusto"),
       (EQ, "non 3x = 32 ma x + 3x = 32", "giusto"), (EQ, "x + 3x = 32, non 3x = 32", "giusto"),
       (EQD, "è 3x = 32 e non x + 3x = 32", "giusto"), (EQD, "direi 3x = 32", "giusto"),
       (SPS, "Spagna, non Portogallo", "giusto"), (SPS, "non Spagna e Portogallo, Spagna", "giusto"),
       (SPS, "Portogallo e Spagna", "da_rivedere")]
# «3x + x = 32» con l'atteso «3x - x = 32»: è «x + 3x = 32» in un altro ordine, mai la b
B3 = RS.prepara("scelta", "Quale?", "b", ["x + 3x = 32", "3x - x = 32", "x + 3 = 32", "3x = 32"])
SC7 += [(B3, "3x - x = 32", "giusto"), (B3, "3x + x = 32", "da_rivedere"),
        (B3, "x + 3x = 32", "sbagliato")]
male = [(d["attesa"], r, RS.valuta(d, r)[0]) for d, r, e in SC7 if RS.valuta(d, r)[0] != e]
verifica("formule fra le opzioni: gli operatori contano («x - 3x = 32» e «x × 3x = 32» non sono "
         "«x + 3x = 32»); una formula che non è un'opzione («4x = 32», «x = 8») da rivedere, "
         "un'altra opzione sbagliata; le parole negate fuori dall'«altro ordine» (PR #350)",
         not male, male)
ok_op, uguali = [], None
for ops in (["2x + 4", "2x - 4", "2x", "4"], ["x < 5", "x > 5", "x = 5"],
            ["x + 3x = 32", "3x - x = 32", "x + 3 = 32", "3x = 32"]):
    try:
        ok_op.append(RS.prepara("scelta", "Quale?", "a", ops)["opzioni"] == ops)
    except ValueError:
        ok_op.append(False)
try:
    RS.prepara("scelta", "Quale?", "a", ["x + 3", "x+3", "x"])
except ValueError as e:
    uguali = str(e)
verifica("prepara: opzioni diverse solo per l'operatore o il verso accettate («2x + 4» e «2x - 4», "
         "«x < 5» e «x > 5»); la stessa formula scritta due volte resta «due opzioni uguali»",
         all(ok_op) and uguali == "due opzioni uguali", (ok_op, uguali))
NN3 = [("0,5 kg", "1/2 kg", "giusto"), ("0,75 L", "3/4 di litro", "giusto"),
       ("0,5 kg", "mezzo chilo", "giusto"), ("1571", "in mezzo al Mediterraneo, nel 1571",
                                             "giusto"),
       ("1,5 h", "un'ora e mezza", "giusto"), ("1500 m", "1 km e 500 m", "giusto"),
       ("1,05 m", "1 metro e 5 centimetri", "giusto"),
       ("20 m/s", "5 m/s e 15 m/s", "da_rivedere"), ("50 °C", "20 °C e 30 °C", "da_rivedere"),
       ("100 m", "50 m e 50 m", "da_rivedere"), ("3 kg", "1 kg, 1 kg e 1 kg", "da_rivedere"),
       ("20 m/s", "18 o 19 m/s", "sbagliato"), ("0,05", "mezzo", "sbagliato")]
male = [(a, r, RS.valuta(RS.prepara("numero", "q?", a), r)[0]) for a, r, e in NN3
        if RS.valuta(RS.prepara("numero", "q?", a), r)[0] != e]
verifica("frazioni prima dell'unità o di «di», «mezzo» solo come numero vero, somme solo delle "
         "misure composte (mai velocità né temperatura)", not male, male)
# #343 (quarta revisione della PR #342): una misura composta sola con la somma diversa è
# sbagliata; con un altro numero o la stessa unità due volte si rivede come prima
NN4 = [("1,05 m", "1 metro e 50 centimetri", "sbagliato"),
       ("90 min", "1 ora e 20 minuti", "sbagliato"),
       ("1,5 m", "1 metro e 50 centimetri", "giusto"),
       ("1,05 m", "3 prove: 1 metro e 50 centimetri", "da_rivedere"),
       ("100 m", "50 m e 50 m", "da_rivedere")]
male = [(a, r, RS.valuta(RS.prepara("numero", "q?", a), r)[0]) for a, r, e in NN4
        if RS.valuta(RS.prepara("numero", "q?", a), r)[0] != e]
verifica("#343: la misura composta sola con la somma sbagliata è «sbagliato»; i contrari (somma "
         "giusta, un numero in più, la stessa unità due volte) come prima", not male, male)
# #343: dopo «di» non legano le unità che sono parole comuni; le altre sì
from calliope.studio import unita as U_  # noqa: E402
LL = [("2 di secondo grado", [(2.0, None)]), ("il 2 di secondo", [(2.0, None)]),
      ("3 di ore", [(3.0, None)]), ("2 di gradi", [(2.0, None)]),
      ("3 ore", [(3.0, "h")]), ("10 secondi", [(10.0, "s")]), ("3/4 di litro", [(0.75, "L")]),
      ("2 di metri", [(2.0, "m")])]
male = [(t, U_.leggi(t)) for t, e in LL if U_.leggi(t) != e]
verifica("#343: «2 di secondo grado», «3 di ore» senza unità; «3 ore», «3/4 di litro» con",
         not male, male)
VF_ = RS.prepara("vero_falso", "x", "vero")
verifica("vero e falso con una negazione («vero, non è falso») da rivedere; senza, sbagliato",
         RS.valuta(VF_, "vero, non è falso")[0] == "da_rivedere"
         and RS.valuta(VF_, "è vero, non falso")[0] == "da_rivedere"
         and RS.valuta(VF_, "boh vero o falso")[0] == "sbagliato")
import dataclasses  # noqa: E402
verifica("ToolContext dichiara user_text_stt",
         any(f.name == "user_text_stt" and f.default is None
             for f in dataclasses.fields(ToolContext)))
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
s6 = studio(cfg_nuova("rev342.db"))
v6, b1, b2, _d = carica(s6)
q = s6.inizia_prova(LEO, v6)
num = next(x for x in q["voci"] if x["tipo"] == "numero")
s6.rispondi_prova(LEO, q["id"], num["n"], "1492")
c6 = s6.consegna_prova(LEO, q["id"])
verifica("1 risposta giusta su 5: niente punteggio né misura, la frase lo dice",
         c6["riepilogo"]["punteggio"] is None and "non conta come misura" in c6["frase"]
         and not s6.dati.tutti("SELECT * FROM studio_misure WHERE verifica = ? AND fonte = "
                               "'verifica_finta'", (v6,)), c6["riepilogo"])
q2 = s6.inizia_prova(LEO, v6)
verifica("le vuote della prova prima in fondo, la risposta data prima (se non si può evitare)",
         q2["voci"][0]["testo"] == num["testo"], [x["testo"] for x in q2["voci"]])
for x in q2["voci"]:
    s6.rispondi_prova(LEO, q2["id"], x["n"], {"scelta": "a o b", "numero": "1490 o 1491",
                                              "vero_falso": "boh vero o falso"}.get(
        x["tipo"], "1492" if x["tipo"] == "numero" else "a"))
c7 = s6.consegna_prova(LEO, q2["id"])
chiuse = {x["tipo"]: x["esito"] for x in c7["voci"]}
verifica("risposte a cavallo sulle chiuse: «sbagliato» dal codice",
         chiuse["scelta"] == chiuse["numero"] == chiuse["vero_falso"] == "sbagliato", chiuse)
verifica("le vuote valgono 0 nel punteggio della scritta",
         c7["riepilogo"]["punteggio"] == 0 or c7["riepilogo"]["punteggio"] is None,
         c7["riepilogo"])
# Sulle chiuse la persona dà al più «indizio»: una carta chiusa da rivedere
s6.aggiungi_carta(LEO, v6, "Chi diede il nome all'America?", "Vespucci", argomento=b1)
q3 = s6.inizia_prova(LEO, v6)
for x in q3["voci"]:
    s6.rispondi_prova(LEO, q3["id"], x["n"], "Amerigo" if x["tipo"] == "carta" else "x")
c8 = s6.consegna_prova(LEO, q3["id"])
ca = next((x for x in c8["voci"] if x["tipo"] == "carta"), None)
if ca is not None and ca["esito"] == "da_rivedere":
    r8 = s6.rivedi_voce(LEO, q3["id"], ca["n"], "giusto")
    v8 = next(x for x in r8["voci"] if x["n"] == ca["n"])
    verifica("su una domanda chiusa «Era giusta» della persona vale «indizio»",
             v8["esito"] == "indizio" and tentativi(s6)[-1]["esito"] == "indizio"
             and ca["chiusa"] and not r8["tutore"], v8)
else:
    verifica("la carta chiusa nella prova, da rivedere", False, ca)
s6.close()
# L'orale dopo un riavvio: la domanda chiesta prima dell'avvio si valuta, quella di adesso no
s7 = studio(cfg_nuova("rev342b.db"))
v7, *_r = carica(s7)
o7 = s7.orale_inizia(LEO, v7, turno=5)
s7._orali.clear()
verifica("senza memoria, domanda chiesta in questo processo: stesso turno, niente esito",
         s7.orale_risposta(LEO, "boh", 5).get("motivo") == "stesso_turno")
s7.close()
ORA[0] = ORA[0] + datetime.timedelta(minutes=1)
s7 = studio(cfg_nuova("rev342b.db"))
r7 = s7.orale_risposta(LEO, "non lo so", 1)
verifica("dopo un riavvio la domanda di prima si valuta, anche col turno che riparte",
         (r7.get("valutata") or {}).get("esito") == "sbagliato", r7)
s7.close()
# «Parliamone» durante una prova aperta e l'orale sul testo di Whisper
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st = studio(cfg_nuova("rev342c.db"))
v9, *_r = carica(st)
st.inizia_prova(LEO, v9)
r = chiama(ctx_di(LEO, turno=1, frase="parliamo della mia mappa"), "studio_mappa_consigli",
           verifica=v9)
verifica("«Parliamone» durante una prova: niente concetti, «c'è una prova in corso»",
         not r["ok"] and "prova in corso" in r["conferma"] and "scheletro" not in r, r)
st.close()
st = studio(cfg_nuova("rev342d.db"))
v10, *_r = carica(st)
c = ctx_di(LEO, turno=1, frase="interrogami")
chiama(c, "studio_interroga", parte="inizia")
x = json.loads(st.dati.uno("SELECT voci FROM studio_prove")["voci"])[0]
giusta_ = GIUSTE.get(x["testo"], "x")
c = ctx_di(LEO, turno=2, frase=giusta_)
c.user_text_stt = "non lo so"           # Whisper ha sentito questo; «capito» ha riscritto
r = chiama(c, "studio_interroga", parte="risposta")
verifica("l'orale valuta la frase di Whisper, non quella riscritta da «capito»",
         r.get("esito") == "sbagliata", r)
st.close()

js = (QUI.parent / "calliope" / "schermi" / "pagina" / "studio.js").read_text(encoding="utf-8")
pezzo = js.split("// ── le prove (31/10", 1)[-1].split("// ── fine delle prove", 1)[0]
verifica("pagina: le prove solo con textContent (niente innerHTML)",
         len(pezzo) > 1000 and "innerHTML" not in pezzo and "insertAdjacentHTML" not in pezzo)

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
