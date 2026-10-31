import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Le carte dello Studio a secco (30/10, passo 6, issue #246, epic #251, decisione 0035 punto 33;
calliope/studio/carte.py, studio/servizio.py, tools/studio.py, schermi/server.py). Niente
modello, un orologio finto, i materiali di fantasia di `manuali/studio/storia.json` (Leo, il
tutore Andrea, Bruno adulto, Carla che amministra).

1. **Leitner** (`carte.prossima`): le tre risposte, le scatole fino a 5, la vigilia come tetto,
   «fra 10 minuti» nella stessa sessione; `fra_quanto`.
2. **Le risposte**: la forma chiusa (un numero, al più tre parole), il confronto del codice (solo
   il «giusto»; contrari: negata, un'altra cifra, una frase lunga), l'autovalutazione per intero
   (contrari: «sì ma non ricordavo la data», «la sapevo quasi tutta», una parola dentro la frase).
3. **Il servizio**: scrivere, correggere, togliere e rimettere; da ripassare, l'ordine, un
   argomento fuori dal piano; l'esito coi tentativi di tipo «carta» (persona, tutore, codice);
   permessi (un altro adulto no, la verifica chiusa no); il registro senza testo.
4. **A voce** (`studio_carte` dal registro dei tool): la domanda in un turno, l'esito nel turno
   dopo dalla frase della persona (mai dall'argomento del modello), una volta sola; la risposta;
   il confronto del codice; nello stesso turno niente; ospite e zona grigia no.
5. **Le sei note della revisione della PR #323**: il giorno futuro, i tentativi all'unione degli
   argomenti, le misure «padronanza» tornando in ombra, la misura del giorno a None, «l'ultima
   prova», la fonte confrontata con chi registra.
6. **Tenuta**: le carte vanno via con la verifica, «dimentica» (non le archiviate), «svuota».
7. **L'endpoint** `/api/studio/carte` col server vero: scrivi, esito, correggi, togli; un altro
   adulto 404; ombra: il minore 403. A mezzogiorno di oggi (31/10, #337: dopo le 23:00 «quasi»
   diceva «fra N minuti» e la prova cadeva fino a mezzanotte), e la mezzanotte a parte: due carte
   alle 23:50; dal #356 «quasi» dice «domani» e torna alle 11:50, «non la sapevo» a mezzanotte.

    python prove/prova_studio_carte.py
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
from calliope.studio import carte as C  # noqa: E402
from calliope.studio import dati as D  # noqa: E402
from calliope.studio import padronanza as PD  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from prove.orologio import ora_del_giorno  # noqa: E402

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
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-carte-"))
ORA = [datetime.datetime(2026, 10, 29, 16, 0)]          # giovedì 29/10, verifica il 5/11
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
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


def carica(st, chi=LEO, persona=None):
    vid = st.crea_verifica(chi, MAT["materia"], MAT["data_verifica"], argomento=MAT["argomento"],
                           persona=persona)
    mid = st.aggiungi_materiale(chi, vid, "foto", "Libro")
    ids = {p["id"]: st.aggiungi_pagina(chi, mid, numero=p["numero"], stato="letta",
                                       testo=p["testo"], metodo="ocr") for p in MAT["pagine"]}
    for a in MAT["argomenti"]:
        st.aggiungi_argomento(chi, vid, a["titolo"], [ids[x] for x in a["pagine"]])
    st.conferma_argomenti(chi, vid)
    return vid, ids, [a["id"] for a in st.argomenti(chi, vid)]


# ═══════════════════════════ 1. Leitner ═══════════════════════════
print("— Leitner")
A = datetime.datetime(2026, 10, 29, 16, 0)
verifica("«non la sapevo»: scatola 1, di nuovo fra 10 minuti",
         C.prossima(3, "non_sapevo", A) == (1, "2026-10-29T16:10:00"))
# Dal 31/10 (#356) una scadenza a giorni è la più tarda fra la mezzanotte di quel giorno e adesso
# più i giorni meno 12 ore: alle 16:00 «domani» è alle 4:00 di domani
verifica("«quasi»: la scatola resta, domani (alle 16:00: domani alle 4:00, adesso + 12 ore)",
         C.prossima(3, "quasi", A) == (3, "2026-10-30T04:00:00"))
verifica("«la sapevo»: scatola + 1, fra l'intervallo della scatola nuova",
         C.prossima(1, "sapevo", A) == (2, "2026-10-31T04:00:00")
         and C.prossima(2, "sapevo", A) == (3, "2026-11-02T04:00:00"))
verifica("al più la scatola 5 (16 giorni)", C.prossima(5, "sapevo", A) == (5, "2026-11-14T04:00:00"))
MATTINA = datetime.datetime(2026, 10, 29, 8, 0)
verifica("#356, contrario: alle 8:00 vince la mezzanotte (domani alle 0:00, 16 ore dopo)",
         C.prossima(3, "quasi", MATTINA) == (3, "2026-10-30T00:00:00")
         and C.prossima(1, "sapevo", MATTINA) == (2, "2026-10-31T00:00:00"))
SERA = datetime.datetime(2026, 10, 29, 23, 50)
verifica("#356: alle 23:50 «quasi» torna domani alle 11:50 (non a mezzanotte, dopo 10 minuti), "
         "«la sapevo» dopo 36 ore",
         C.prossima(3, "quasi", SERA) == (3, "2026-10-30T11:50:00")
         and C.prossima(1, "sapevo", SERA) == (2, "2026-10-31T11:50:00")
         and C.fra_quanto(C.prossima(3, "quasi", SERA)[1], SERA) == "domani"
         and C.fra_quanto(C.prossima(1, "sapevo", SERA)[1], SERA) == "fra 2 giorni")
verifica("#356: la vigilia resta il tetto anche a tarda sera (la vigilia è di ripasso)",
         C.prossima(1, "sapevo", SERA, datetime.date(2026, 10, 31)) == (2, "2026-10-31T00:00:00")
         and C.prossima(3, "quasi", SERA, datetime.date(2026, 10, 30))
         == (3, "2026-10-30T00:00:00"))
verifica("la vigilia è il tetto: nessuna scadenza dopo il giorno prima della verifica",
         C.prossima(4, "sapevo", A, datetime.date(2026, 11, 4)) == (5, "2026-11-04T00:00:00"))
verifica("una vigilia già passata (o oggi) non conta",
         C.prossima(4, "sapevo", A, datetime.date(2026, 10, 29))[1] == "2026-11-14T04:00:00")
verifica("un esito sconosciuto: ValueError", solleva(lambda: C.prossima(1, "boh", A), ValueError))
verifica("fra_quanto: minuti, domani, giorni, adesso",
         C.fra_quanto("2026-10-29T16:10:00", A) == "fra 10 minuti"
         and C.fra_quanto("2026-10-30T00:00:00", A) == "domani"
         and C.fra_quanto("2026-11-02T00:00:00", A) == "fra 4 giorni"
         and C.fra_quanto("2026-10-29T15:00:00", A) == "adesso")
M = datetime.datetime(2026, 10, 29, 23, 55)
verifica("mezzanotte (nota 4 della PR #324): «non la sapevo» alle 23:55 torna «fra 10 minuti», "
         "non «domani»", C.fra_quanto(C.prossima(2, "non_sapevo", M)[1], M) == "fra 10 minuti")
verifica("da_ripassare: attiva e scaduta (vuota vale subito); tolta mai",
         C.da_ripassare({"stato": "attiva", "scadenza": None}, A)
         and not C.da_ripassare({"stato": "attiva", "scadenza": "2026-10-30T00:00:00"}, A)
         and not C.da_ripassare({"stato": "tolta", "scadenza": None}, A))

# ═══════════════════════════ 2. le risposte ═══════════════════════════
print("— le risposte")
verifica("forma chiusa: un anno, un nome, al più tre parole senza articoli né preposizioni",
         C.chiusa("Nel 1453.") == C.chiusa("1453") == "#1453"
         and C.chiusa("Il Portogallo") == "portogallo"
         and C.chiusa("Servivano a conservare e insaporire i cibi") is None, C.chiusa("1453"))
# #361: i numeri restano numeri (un gettone «#valore@unità»), confrontati con studio/unita.py
verifica("#361: «1» è una risposta chiusa (prima diventava «uno» e si scartava come articolo); "
         "«uno» detto vale 1, «2» e «è 1» no",
         C.chiusa("1") == "#1" and C.risposta_giusta(C.chiusa("1"), "1")
         and C.risposta_giusta(C.chiusa("1"), "uno") and not C.risposta_giusta(C.chiusa("1"), "2")
         and not C.risposta_giusta(C.chiusa("1"), "è 1"), C.chiusa("1"))
ch_d = C.chiusa("1,5 g/cm³")
verifica("#361: «1,5 g/cm³» non sta dentro «2,5 g/cm³»; la stessa misura detta o convertita sì",
         ch_d == "#1.5@g/cm3" and not C.risposta_giusta(ch_d, "2,5 g/cm³")
         and not C.risposta_giusta(ch_d, "è 2,5 g/cm³ credo")
         and not C.risposta_giusta(ch_d, "15 g/cm³")
         and C.risposta_giusta(ch_d, "1,5 g/cm³")
         and C.risposta_giusta(ch_d, "la densità è 1,5 grammi al centimetro cubo")
         and C.risposta_giusta(ch_d, "1500 kg/m³"), ch_d)
verifica("#361, contrari dei numeri: «12» non dentro «112», «5» non dentro «15», la misura senza "
         "l'unità attesa non basta",
         not C.risposta_giusta(C.chiusa("12"), "112")
         and not C.risposta_giusta(C.chiusa("5"), "15 credo")
         and not C.risposta_giusta(ch_d, "1,5")
         and C.risposta_giusta(C.chiusa("20 m/s"), "72 km/h"))
ch = C.chiusa("1453")
verifica("il codice: la cifra detta, anche dentro una frase corta",
         C.risposta_giusta(ch, "1453") and C.risposta_giusta(ch, "nel 1453 mi pare")
         and C.risposta_giusta(ch, "Millequattrocentocinquantatré"))
verifica("contrari: negata, un'altra cifra, una frase lunga, nessuna forma chiusa",
         not C.risposta_giusta(ch, "non 1453") and not C.risposta_giusta(ch, "non è il 1453")
         and not C.risposta_giusta(ch, "1454") and not C.risposta_giusta(ch, "145")
         and not C.risposta_giusta(ch, "allora io direi che forse era il 1453 ma potrei anche "
                                       "sbagliarmi di parecchio")
         and not C.risposta_giusta(None, "1453"))
verifica("il codice: un nome con le maiuscole e gli accenti",
         C.risposta_giusta(C.chiusa("Magellano"), "magellano!")
         and not C.risposta_giusta(C.chiusa("Magellano"), "Colombo"))
verifica("nota 2 della PR #324: le risposte corte («sì», «no», «quasi», «5», «Ra») valgono "
         "solo come frase intera",
         C.corta(C.chiusa("Sì")) and C.corta(C.chiusa("5")) and C.corta(C.chiusa("Ra"))
         and not C.corta(C.chiusa("1453")) and not C.corta(C.chiusa("Colombo"))
         and C.risposta_giusta(C.chiusa("Sì"), "Sì.")
         and C.risposta_giusta(C.chiusa("Sì"), "Calliope, sì")
         and not C.risposta_giusta(C.chiusa("Sì"), "sì, accendi la luce")
         and not C.risposta_giusta(C.chiusa("5"), "ne ho 5 o 6")
         and C.risposta_giusta(C.chiusa("5"), "cinque")
         and not C.risposta_giusta(C.chiusa("No"), "no, non lo so"))
verifica("autovalutazione per intero: la sapevo, quasi, no",
         C.autovalutazione("La sapevo.") == "sapevo" and C.autovalutazione("sì") == "sapevo"
         and C.autovalutazione("Calliope, quasi") == "quasi"
         and C.autovalutazione("più o meno") == "quasi"
         and C.autovalutazione("No, non la sapevo.") == "non_sapevo"
         and C.autovalutazione("non lo so") == "non_sapevo")
verifica("contrari dell'autovalutazione: una parola dentro la frase non basta",
         C.autovalutazione("sì ma non ricordavo la data") is None
         and C.autovalutazione("la sapevo quasi tutta") is None
         and C.autovalutazione("nel 1453") is None
         and C.autovalutazione("non so se la sapevo davvero, dimmi tu") is None
         and C.autovalutazione("") is None)
verifica("testo_normale: una riga, senza caratteri di controllo né di direzione, al più N",
         C.testo_normale("Chi\n‮ era?\x00", 50) == "Chi era?"
         and len(C.testo_normale("x" * 999, C.DOMANDA_MAX)) == C.DOMANDA_MAX
         and solleva(lambda: C.testo_normale("  \n ", 10), ValueError))

# ═══════════════════════════ 3. il servizio ═══════════════════════════
print("— il servizio")
st = studio(cfg_nuova("a.db"))
vid, ids, aids = carica(st)
DOM = MAT["domande"]
c1 = st.aggiungi_carta(LEO, vid, DOM[0]["domanda"], "1453", argomento=aids[0],
                       pagine=[ids["p112"]])
c2 = st.aggiungi_carta(ANDREA, vid, DOM[1]["domanda"], DOM[1]["attesa"], argomento=aids[0])
c3 = st.aggiungi_carta(LEO, vid, "Chi scoprì l'America?", "Cristoforo Colombo")
tutte = st.carte(LEO, vid)
verifica("scritte dalla persona e dal tutore: attive, scatola 1, da ripassare subito",
         [c["id"] for c in tutte] == [c1, c2, c3]
         and all(c["stato"] == "attiva" and c["scatola"] == 1 and c["da_ripassare"]
                 for c in tutte) and tutte[0]["chiusa"] == C.chiusa("1453")
         and tutte[1]["chiusa"] is None, tutte[:1])
verifica("il numero dell'argomento nell'elenco della verifica",
         tutte[0]["argomento_numero"] == 1 and tutte[2]["argomento_numero"] is None)
verifica("un altro adulto non vede né scrive le carte di Leo (lo stesso «non c'è»)",
         solleva(lambda: st.carte(BRUNO, vid), S.NonTrovata)
         and solleva(lambda: st.aggiungi_carta(BRUNO, vid, "x?", "y"), S.NonTrovata))
verifica("domanda o risposta vuote: ValueError; un argomento di un'altra verifica: non c'è",
         solleva(lambda: st.aggiungi_carta(LEO, vid, " ", "y"), ValueError)
         and solleva(lambda: st.aggiungi_carta(LEO, vid, "x?", "y", argomento=99999),
                     S.NonTrovata))
r = st.esito_carta(LEO, c1, "sapevo")
verifica("«la sapevo»: scatola 2, fra 2 giorni, un tentativo «giusto» della persona",
         r["scatola"] == 2 and r["fra"] == "fra 2 giorni" and r["tentativo"] is not None
         and r["restano"] == 2, r)
t = st.dati.uno("SELECT * FROM studio_tentativi WHERE id = ?", (r["tentativo"],))
verifica("il tentativo: tipo carta, esito giusto, fonte persona, la carta, l'argomento",
         t["tipo"] == "carta" and t["esito"] == "giusto" and t["fonte"] == "persona"
         and t["carta"] == c1 and t["argomento"] == aids[0] and t["chi"] == "l1", t)
r = st.esito_carta(ANDREA, c2, "quasi")
t = st.dati.uno("SELECT * FROM studio_tentativi WHERE id = ?", (r["tentativo"],))
verifica("il tutore: «quasi» → indizio con la fonte «tutore»",
         t["esito"] == "indizio" and t["fonte"] == "tutore" and r["fra"] == "domani", t)
r = st.esito_carta(LEO, c3, "non_sapevo")
verifica("«non la sapevo» senza argomento: fra 10 minuti, nessun tentativo",
         r["fra"] == "fra 10 minuti" and r["tentativo"] is None and r["scatola"] == 1)
verifica("dopo 10 minuti torna da ripassare", not st.da_ripassare(LEO, vid))
ORA[0] = datetime.datetime(2026, 10, 29, 16, 11)
verifica("…e c'è di nuovo", [c["id"] for c in st.da_ripassare(LEO, vid)] == [c3])
st.segna_argomento(LEO, aids[0], False)
ORA[0] = datetime.datetime(2026, 11, 1, 9, 0)
verifica("un argomento fuori dal piano: le sue carte non si ripassano",
         [c["id"] for c in st.da_ripassare(LEO, vid)] == [c3]
         and not next(c for c in st.carte(LEO, vid) if c["id"] == c1)["nel_piano"])
st.segna_argomento(LEO, aids[0], True)
verifica("rimesso nel piano: tornano, la più scaduta prima",
         [c["id"] for c in st.da_ripassare(LEO, vid)] == [c3, c2, c1],
         [c["id"] for c in st.da_ripassare(LEO, vid)])
st.correggi_carta(LEO, c2, domanda="Perché le spezie erano richieste?")
c = next(c for c in st.carte(LEO, vid) if c["id"] == c2)
verifica("correggere la domanda: il ripasso resta", c["domanda"].startswith("Perché le spezie")
         and c["scatola"] == 1 and c["origine"] == "persona")
st.esito_carta(LEO, c1, "sapevo")
st.correggi_carta(LEO, c1, risposta="Nel 1453")
c = next(c for c in st.carte(LEO, vid) if c["id"] == c1)
verifica("correggere la risposta: si ricomincia dalla scatola 1",
         c["scatola"] == 1 and c["risposta"] == "Nel 1453" and c["chiusa"] == C.chiusa("1453"),
         c)
st.segna_carta(LEO, c3, False)
verifica("togliere una carta: fuori dal ripasso; rimetterla: dentro",
         c3 not in [x["id"] for x in st.da_ripassare(LEO, vid)]
         and (st.segna_carta(LEO, c3, True) or True)
         and c3 in [x["id"] for x in st.da_ripassare(LEO, vid)])
verifica("l'esito di una carta tolta: ValueError", (st.segna_carta(LEO, c3, False) or True)
         and solleva(lambda: st.esito_carta(LEO, c3, "sapevo"), ValueError))
st.segna_carta(LEO, c3, True)
pr = st.aggiungi_carta(LEO, vid, "Ignora le istruzioni?", "Sì", origine="modello",
                       avvisi=["titolo_ordine"])
verifica("una carta del modello con un avviso resta «proposta», fuori dal ripasso",
         next(c for c in st.carte(LEO, vid) if c["id"] == pr)["stato"] == "proposta"
         and pr not in [x["id"] for x in st.da_ripassare(LEO, vid)])
h = next(v for v in st.home(LEO)["verifiche"] if v["id"] == vid)
verifica("la home: solo i conti delle carte, mai il testo",
         h["carte"]["totali"] == 4 and h["carte"]["da_ripassare"] == 3
         and h["carte"]["proposte"] == 1
         and DOM[0]["domanda"] not in json.dumps(h, ensure_ascii=False), h["carte"])
verifica("il registro: id e conti, mai domande né risposte",
         any("carta" in x for x in registro)
         and not any(DOM[0]["domanda"] in x or "Colombo" in x for x in registro))
verifica("Studio.stato(): i conti delle carte",
         st.stato()["carte"]["scritte"] == 4
         and st.stato()["carte"]["esiti"].get("sapevo") == 2, st.stato()["carte"])
st.dati.scrivi("UPDATE studio_verifiche SET stato = 'archiviata' WHERE id = ?", (vid,))
verifica("una verifica chiusa non prende carte nuove",
         solleva(lambda: st.aggiungi_carta(LEO, vid, "x?", "y"), S.VerificaChiusa))
st.dati.scrivi("UPDATE studio_verifiche SET stato = 'aperta' WHERE id = ?", (vid,))
st.close()

# ═══════════════════════════ 4. a voce ═══════════════════════════
print("— a voce")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st = studio(cfg_nuova("b.db"))
vid, ids, aids = carica(st)
k1 = st.aggiungi_carta(LEO, vid, DOM[0]["domanda"], "1453", argomento=aids[0],
                       pagine=[ids["p112"]])
k2 = st.aggiungi_carta(LEO, vid, "Chi scoprì l'America?", "Cristoforo Colombo",
                       argomento=aids[2])
TOOLS = ToolRegistry()
for spec in TS.studio_specs():
    TOOLS.register(spec)


def ctx_di(prof, come="voce", turno=1, frase=""):
    sc = types.SimpleNamespace(current_speaker=prof.name if prof else None, identified_by=come,
                               minore_incerto=None,
                               current_level=prof.level if prof else "ospite",
                               profile_level=prof.level if prof else "ospite")
    ctx = ToolContext(cfg=st.cfg, speakers=REG, speaker_ctx=sc, speaker=None)
    ctx.studio = st
    ctx.turno = turno
    ctx.user_text = frase
    return ctx


def chiama(ctx, nome, **args) -> dict:
    return json.loads(TOOLS.call(nome, args, ctx, "familiare"))


cl = politica.classe_di("studio_carte")
verifica("studio_carte: classe «sicuro» con la fonte «foto», non fidato, mai toccabile",
         cl.classe == politica.SICURO and politica.fonte_di("studio_carte") == "foto"
         and TOOLS.get("studio_carte").non_fidato and "studio_carte" in T.ESCLUSI
         and TOOLS.get("studio_carte").levels == frozenset({"familiare", "amministra"}))
verifica("studio «carte»: una lettura (E0)",
         valore.effetto("studio", {"azione": "carte"}) == valore.E0
         and "carte" in TS.LETTURE)
r = chiama(ctx_di(LEO, turno=1, frase="ripassiamo le carte"), "studio_carte", parte="domanda")
verifica("la domanda: la prima carta, la posizione scritta dal codice",
         r["ok"] and r["domanda"] == DOM[0]["domanda"] and r["carta"] == "1 di 2"
         and "1453" not in json.dumps(r), r)
r = chiama(ctx_di(LEO, turno=1, frase="la sapevo"), "studio_carte", parte="esito")
verifica("nello stesso turno l'esito non si scrive", not r["ok"]
         and "appena" in r["errore"] and not st.dati.tutti("SELECT * FROM studio_tentativi"))
verifica("il modello non può passare l'esito: lo schema di studio_carte non lo ha",
         set(TS.PARAMETRI_CARTE["properties"]) == {"parte", "verifica", "materia"})
r = chiama(ctx_di(LEO, turno=2, frase="boh forse i Romani"), "studio_carte", parte="esito")
verifica("una frase che non è una forma chiusa né la risposta: niente esito",
         not r["ok"] and r["errore"] == "esito non detto"
         and not st.dati.tutti("SELECT * FROM studio_tentativi"), r)
r = chiama(ctx_di(LEO, turno=2), "studio_carte", parte="risposta")
verifica("la risposta della carta in corso, con le pagine (cifre)",
         r["ok"] and r["risposta"] == "1453" and r.get("pagine") == ["112"], r)
r = chiama(ctx_di(LEO, turno=3, frase="no, non la sapevo"), "studio_carte", parte="esito")
t = st.dati.tutti("SELECT * FROM studio_tentativi")
verifica("«no, non la sapevo»: un tentativo «sbagliato» della persona, fra 10 minuti",
         r["ok"] and r["esito"] == "non la sapeva" and r["prossima_volta"] == "fra 10 minuti"
         and len(t) == 1 and t[0]["esito"] == "sbagliato" and t[0]["fonte"] == "persona", r)
r = chiama(ctx_di(LEO, turno=4, frase="la sapevo"), "studio_carte", parte="esito")
verifica("una volta sola: dopo l'esito la carta non è più in corso",
         not r["ok"] and r["errore"] == "nessuna carta in corso"
         and len(st.dati.tutti("SELECT * FROM studio_tentativi")) == 1)
r = chiama(ctx_di(LEO, turno=4, frase="la prossima"), "studio_carte", parte="domanda")
verifica("la prossima: l'altra carta (la prima torna fra 10 minuti)",
         r["ok"] and r["domanda"] == "Chi scoprì l'America?" and r["carta"] == "1 di 1", r)
r = chiama(ctx_di(LEO, turno=5, frase="Cristoforo Colombo"), "studio_carte", parte="esito")
t = st.dati.tutti("SELECT * FROM studio_tentativi ORDER BY id")
verifica("la risposta chiusa detta: «giusto» con la fonte «codice»",
         r["ok"] and r["esito"] == "la sapeva" and "codice" in r["controllata"]
         and t[-1]["fonte"] == "codice" and t[-1]["esito"] == "giusto", r)
ORA[0] = datetime.datetime(2026, 10, 29, 16, 11)
k3 = st.aggiungi_carta(LEO, vid, "Chi arrivò in India per mare?", "Vasco da Gama")
st.segna_carta(LEO, k1, False)
r = chiama(ctx_di(LEO, turno=6), "studio_carte", parte="domanda")
r = chiama(ctx_di(LEO, turno=7), "studio_carte", parte="risposta")
r = chiama(ctx_di(LEO, turno=8, frase="Vasco da Gama"), "studio_carte", parte="esito")
verifica("dopo aver sentito la risposta, ripeterla non è saperla: niente esito del codice",
         not r["ok"] and r["errore"] == "esito non detto", r)
r = chiama(ctx_di(LEO, turno=8), "studio_carte", parte="risposta")
r = chiama(ctx_di(LEO, turno=9, frase="quasi"), "studio_carte", parte="esito")
verifica("…l'autovalutazione sì: «quasi» (dopo la risposta riletta, nel turno dopo)",
         r["ok"] and r["esito"] == "quasi", r)
k4 = st.aggiungi_carta(LEO, vid, "Il Portogallo cercava l'oro? Sì o no", "No")
st.segna_carta(LEO, k3, False)
r = chiama(ctx_di(LEO, turno=10), "studio_carte", parte="domanda")
r = chiama(ctx_di(LEO, turno=11, frase="no"), "studio_carte", parte="esito")
t = st.dati.tutti("SELECT * FROM studio_tentativi ORDER BY id")
verifica("una carta che risponde «no»: prima vale come risposta (codice giusto)",
         r["ok"] and r["esito"] == "la sapeva" and "codice" in r["controllata"], r)
st.segna_carta(LEO, k1, True)
st.segna_carta(LEO, k4, False)
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st.dati.scrivi("UPDATE studio_carte SET scadenza = '2026-10-30T00:00:00' WHERE id = ?", (k1,))
r = chiama(ctx_di(LEO, turno=12), "studio_carte", parte="domanda")
verifica("finite: la frase pronta del codice, senza testo delle carte",
         not r.get("domanda") and "finite" in r["conferma"] and "1453" not in r["conferma"], r)
ORA[0] = datetime.datetime(2026, 10, 29, 16, 20)
st.dati.scrivi("UPDATE studio_carte SET scadenza = NULL WHERE id = ?", (k1,))
r = chiama(ctx_di(ANDREA, turno=7), "studio_carte", parte="domanda", verifica=vid)
r2 = chiama(ctx_di(ANDREA, turno=8, frase="sì"), "studio_carte", parte="esito")
t = st.dati.tutti("SELECT * FROM studio_tentativi ORDER BY id")
verifica("il tutore che interroga: l'esito con la fonte «tutore»",
         r["ok"] and r2["ok"] and t[-1]["fonte"] == "tutore" and t[-1]["chi"] == "a1", r2)
r = chiama(ctx_di(BRUNO, turno=9), "studio_carte", parte="domanda", verifica=vid)
verifica("un altro adulto: «non la trovo»", not r["ok"] and r["conferma"] == TS.NON_CE)
r = chiama(ctx_di(None, turno=9), "studio_carte", parte="domanda")
r2 = chiama(ctx_di(LEO, come="conversazione", turno=9), "studio_carte", parte="domanda")
verifica("l'ospite e la zona grigia: lo Studio non si apre",
         not r["ok"] and not r2["ok"] and r["conferma"] == r2["conferma"] == TS.CHI_NO)
r = chiama(ctx_di(LEO, turno=10, frase="quante carte ho?"), "studio", azione="carte")
verifica("studio «carte»: solo i conti nella frase",
         r["ok"] and "2 carte" in r["conferma"] and "1453" not in r["conferma"], r["conferma"])
st.aggiungi_carta(LEO, vid, "Chi era Magellano?", "Un navigatore")
r = chiama(ctx_di(LEO, turno=10, frase="cosa devo studiare oggi?"), "studio", azione="oggi")
verifica("«oggi» dice anche le carte da ripassare, solo il conto",
         "una carta da ripassare" in r["conferma"] and "Magellano" not in r["conferma"],
         r["conferma"])
# Le note 1, 3 e 4 della revisione della PR #324
k5 = st.aggiungi_carta(LEO, vid, "La capitale del Portogallo?", "Lisbona")
r = chiama(ctx_di(LEO, turno=20), "studio_carte", parte="domanda", verifica=vid)
r2 = chiama(ctx_di(LEO, turno=22, frase="no"), "studio_carte", parte="esito")
verifica("nota 1: due turni dopo la domanda (in mezzo «che ore sono?») un «no» non è un esito",
         r["ok"] and not r2["ok"] and r2["errore"] == "nessuna carta in corso"
         and st.carta_in_corso(LEO) is None, r2)
r = chiama(ctx_di(LEO, turno=30), "studio_carte", parte="domanda", verifica=vid)
cid = st.carta_in_corso(LEO)["id"]
st.segna_carta(LEO, cid, False)
r2 = chiama(ctx_di(LEO, turno=31, frase="la sapevo"), "studio_carte", parte="esito")
verifica("nota 3: la carta tolta mentre è in corso: risposta chiara, ed esce da «in corso»",
         not r2["ok"] and r2["errore"] == "la carta è stata tolta dal ripasso"
         and st.carta_in_corso(LEO) is None, r2)
st.segna_carta(LEO, cid, True)
st.dati.scrivi("UPDATE studio_carte SET scadenza = NULL WHERE id = ?", (k5,))
ORA[0] = datetime.datetime(2026, 10, 29, 23, 58)
r = chiama(ctx_di(LEO, turno=40), "studio_carte", parte="domanda", verifica=vid)
ORA[0] = datetime.datetime(2026, 10, 30, 0, 2)
r2 = chiama(ctx_di(LEO, turno=41, frase="la sapevo"), "studio_carte", parte="esito")
verifica("nota 4: chiesta alle 23:58, risposta alle 00:02 nel turno dopo: vale", r["ok"]
         and r2["ok"], r2)
ORA[0] = datetime.datetime(2026, 10, 29, 16, 20)
st.dimentica_sessione("l1")
verifica("«dimentica»: la carta in corso esce dalla memoria", st.carta_in_corso(LEO) is None)
st.close()

# ═══════════════════════════ 5. le sei note della PR #323 ═══════════════════════════
print("— le note della revisione della PR #323")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st = studio(cfg_nuova("c.db"))
vid, ids, aids = carica(st)
verifica("1. un giorno nel futuro è rifiutato",
         solleva(lambda: st.registra_tentativo(LEO, vid, aids[0], "carta", "giusto",
                                               giorno="2027-01-10"), ValueError)
         and not st.dati.tutti("SELECT * FROM studio_tentativi"))
verifica("6. la fonte confrontata con chi registra: Leo «tutore» no, Andrea «persona» no, "
         "«codice» tutti e due",
         solleva(lambda: st.registra_tentativo(LEO, vid, aids[0], "carta", "giusto",
                                               fonte="tutore"), ValueError)
         and solleva(lambda: st.registra_tentativo(ANDREA, vid, aids[0], "carta", "giusto",
                                                   fonte="persona"), ValueError)
         and st.registra_tentativo(LEO, vid, aids[0], "carta", "giusto", fonte="codice")
         and st.registra_tentativo(ANDREA, vid, aids[0], "carta", "giusto", fonte="codice"))
kc = st.aggiungi_carta(LEO, vid, "Domanda?", "Risposta", argomento=aids[1])
st.registra_tentativo(LEO, vid, aids[1], "carta", "sbagliato")
st.unisci_argomenti(LEO, [aids[0], aids[1]])
n1 = st.dati.uno("SELECT COUNT(*) AS n FROM studio_tentativi WHERE argomento = ?", (aids[1],))
n0 = st.dati.uno("SELECT COUNT(*) AS n FROM studio_tentativi WHERE argomento = ?", (aids[0],))
verifica("2. unire due argomenti sposta tentativi e carte su quello che resta",
         n1["n"] == 0 and n0["n"] == 3
         and next(c for c in st.carte(LEO, vid) if c["id"] == kc)["argomento"] == aids[0])
st.close()

# 3, 4, 5: la padronanza mostrata, poi in ombra
ORA[0] = datetime.datetime(2026, 10, 28, 16, 0)
cfg = cfg_nuova("d.db", padronanza="mostrata")
st = studio(cfg)
vid, ids, aids = carica(st)
for g in (28, 29, 30):
    ORA[0] = datetime.datetime(2026, 10, g, 17, 0)
    for a in aids:
        for _ in range(2):
            st.registra_tentativo(LEO, vid, a, "carta", "giusto")
pi = st.piano(LEO, vid)
verifica("mostrata: le misure della padronanza nella forbice", pi["misure"] >= 2, pi["misure"])
verifica("5. «l'ultima prova» non viene dalla padronanza", pi["livello"] is None
         and "ultima prova" not in st.riepilogo(LEO, vid)["frase"].lower(), pi["livello"])
st.aggiungi_misura(LEO, vid, 55, "verifica_finta", giorno="2026-10-30")
verifica("5. …ma da una prova vera sì", st.piano(LEO, vid)["livello"] == 55)
st.close()
cfg.studio_padronanza = "ombra"
st = studio(cfg)
pi = st.piano(LEO, vid)
verifica("3. tornando in ombra le misure «padronanza» escono dalla forbice",
         pi["misure"] == 1 and pi["previsione"] is None, pi["misure"])
# 4: il livello che torna a None toglie la misura di oggi
oggi = ORA[0].date().isoformat()
st._misura_padronanza(st.verifica(LEO, vid))
prima = st.dati.tutti("SELECT * FROM studio_misure WHERE verifica = ? AND giorno = ? AND "
                      "fonte = ?", (vid, oggi, PD.FONTE_OMBRA))
for a in aids[1:]:
    st.dati.scrivi("DELETE FROM studio_tentativi WHERE argomento = ?", (a,))
st._misura_padronanza(st.verifica(LEO, vid))
dopo = st.dati.tutti("SELECT * FROM studio_misure WHERE verifica = ? AND giorno = ? AND "
                     "fonte IN (?, ?)", (vid, oggi, PD.FONTE_OMBRA, PD.FONTE_MISURA))
verifica("4. il livello tornato a None toglie la misura del giorno", len(prima) == 1 and not dopo,
         f"{prima} {dopo}")
st.close()

# ═══════════════════════════ 6. tenuta ═══════════════════════════
print("— tenuta")
ORA[0] = datetime.datetime(2026, 10, 29, 16, 0)
st = studio(cfg_nuova("e.db"))
vA, _, aA = carica(st)
vB, _, _ = carica(st, ANDREA)
vC, _, _ = carica(st)
for v in (vA, vC):
    st.aggiungi_carta(LEO, v, "Domanda di Leo?", "Risposta")
st.aggiungi_carta(ANDREA, vB, "Domanda di Andrea?", "Risposta")


def n_carte(v=None):
    q = "SELECT COUNT(*) AS n FROM studio_carte" + (" WHERE verifica = ?" if v else "")
    return st.dati.uno(q, (v,) if v else ())["n"]


verifica("le carte nelle tabelle dello Studio e nella conservazione",
         "studio_carte" in D.TABELLE and len(D.MIGRAZIONI) >= 6)
st.togli_verifica(LEO, vC)
verifica("la verifica tolta: via le sue carte", n_carte(vC) == 0 and n_carte(vA) == 1)
st.archivia(LEO, vA)
D.cancella(st.dati.db, persona="l1", archiviate=False)
verifica("«dimentica» di Leo: l'archiviata resta con le sue carte, Andrea non si tocca",
         n_carte(vA) == 1 and n_carte(vB) == 1)
D.cancella(st.dati.db, tutto=True)
verifica("«svuota»: nessuna carta", n_carte() == 0)
st.close()
db = D.apri_db(str(TMP / "vecchio.db"))
db.execute("CREATE TABLE studio_verifiche (id INTEGER PRIMARY KEY, persona TEXT, stato TEXT, "
           "data TEXT)")
for t in ("studio_materiali", "studio_argomenti", "studio_piano", "studio_misure"):
    db.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY, verifica INTEGER, riferimento TEXT)")
db.execute("CREATE TABLE studio_pagine (id INTEGER, materiale INTEGER, file TEXT)")
db.execute("CREATE TABLE studio_giorni (persona TEXT, giorno TEXT)")
db.execute("INSERT INTO studio_verifiche VALUES (1, 'l1', 'aperta', '2026-01-01')")
db.commit()
verifica("un db allo schema di prima (senza carte né tentativi) si ruota senza errori",
         D.cancella(db, scadute_prima=datetime.date(2026, 6, 1))["verifiche"] == 1)
db.close()


# ═══════════════════════════ 7. l'endpoint ═══════════════════════════
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


print("— l'endpoint /api/studio/carte")
from calliope import minori  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402

# Tutto l'endpoint a mezzogiorno di oggi (31/10, #337): con l'orologio vero, dopo le 23:00 la
# scadenza di «quasi» (domani a mezzanotte) è meno di un'ora avanti, i tasti dicevano «fra 10
# minuti» alle 23:50 invece di «domani» e la prova cadeva fino a mezzanotte. La notte è a parte
with ora_del_giorno(12, 0) as _inizio:
    ORA[0] = datetime.datetime.fromtimestamp(_inizio).replace(microsecond=0)
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
            for chi, pid in (("leo", "l1"), ("andrea", "a1"), ("bruno", "b1"), ("carla", "c1")):
                _, tok[chi] = hub.archivio.crea_con_token("telefono " + chi, proprietario=pid,
                                                          proprietario_nome=chi.title())
            hub._rinfresca()
            sess = {k: chiedi(port, "/api/accedi", token=t)[1].get("sessione")
                    for k, t in tok.items()}
            data = (ORA[0].date() + datetime.timedelta(days=7)).isoformat()
            vid = st.crea_verifica(LEO, "Storia", data)
            a1 = st.aggiungi_argomento(LEO, vid, "Le scoperte", [], proposto=False)
            st.conferma_argomenti(LEO, vid)
            if modo == "ombra":
                s, d = chiedi(port, "/api/studio/carte", sess["leo"], corpo={"verifica": vid})
                verifica("ombra: il minore non vede le carte (403)", s == 403, f"{s} {d}")
                continue
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "scrivi", "domanda": "Chi era Colombo?",
                                 "risposta": "Un navigatore", "argomento": a1})
            verifica("scrivi: la carta c'è, da ripassare, coi tre tasti scritti dal server",
                     s == 200 and len(d["carte"]) == 1 and d["da_ripassare"] == [d["scritta"]]
                     and d["carte"][0]["tasti"] == {"sapevo": "fra 2 giorni", "quasi": "domani",
                                                    "non_sapevo": "fra 10 minuti"}
                     and d["argomenti"][0]["titolo"] == "Le scoperte", f"{s} {str(d)[:300]}")
            cid = d.get("scritta")
            s, d = chiedi(port, "/api/studio/carte", sess["bruno"], corpo={"verifica": vid})
            verifica("un altro adulto: 404", s == 404, f"{s} {d}")
            s, d = chiedi(port, "/api/studio/carte", sess["andrea"],
                          corpo={"verifica": vid, "azione": "esito", "carta": cid,
                                 "esito": "sapevo"})
            t = st.dati.tutti("SELECT * FROM studio_tentativi")
            verifica("esito dal tutore: il ripasso avanza, il tentativo col tutore",
                     s == 200 and d["ultimo"]["fra"] == "fra 2 giorni" and not d["da_ripassare"]
                     and t and t[-1]["fonte"] == "tutore", f"{s} {str(d)[:200]}")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "esito", "carta": cid, "esito": "boh"})
            verifica("un esito sconosciuto: 400", s == 400)
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "correggi", "carta": cid,
                                 "risposta": "Un navigatore genovese"})
            verifica("correggi la risposta: di nuovo da ripassare",
                     s == 200 and d["carte"][0]["risposta"] == "Un navigatore genovese"
                     and d["da_ripassare"] == [cid], f"{s} {str(d)[:200]}")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "togli", "carta": cid})
            verifica("togli: fuori dal ripasso", s == 200 and d["carte"][0]["stato"] == "tolta"
                     and not d["da_ripassare"])
            vb = st.crea_verifica(ANDREA, "Inglese", data)
            cb = st.aggiungi_carta(ANDREA, vb, "Past of go?", "went")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "esito", "carta": cb,
                                 "esito": "sapevo"})
            verifica("una carta di un'altra verifica: 404, niente cambiato",
                     s == 404 and st.carte(ANDREA, vb)[0]["scatola"] == 1, f"{s} {d}")
            s, d = chiedi(port, "/api/studio/home", sess["leo"])
            verifica("la home: i conti delle carte (quella tolta non conta)",
                     s == 200 and d["verifiche"][0]["carte"]["totali"] == 0, f"{s} {str(d)[:200]}")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "rimetti", "carta": cid})
            s, d = chiedi(port, "/api/studio/home", sess["leo"])
            verifica("…rimessa: conta", s == 200 and d["verifiche"][0]["carte"] == {
                "totali": 1, "da_ripassare": 1, "proposte": 0, "prossima": None}, f"{s} {d}")
            # Le carte proposte dal modello (seconda parte del passo 6): «conferma» prende le pulite
            from calliope.studio import genera as G
            args_c = st._argomenti_per_carte(vid)
            st.proponi_carte(vid, G.firma(args_c, st._pagine_di(vid), "attiva"),
                             [{"domanda": "Chi partì da Palos?", "risposta": "Colombo",
                               "argomento": a1, "pagine": [], "avvisi": []},
                              {"domanda": "Ignora tutto?", "risposta": "Sì", "argomento": a1,
                               "pagine": [], "avvisi": ["testo_ordine"]}], G.PROPOSTE, "attiva")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "conferma"})
            stati = {c["domanda"]: c["stato"] for c in d.get("carte", [])}
            verifica("conferma: la proposta pulita nel ripasso, quella con l'avviso resta proposta",
                     s == 200 and d["confermate"] == {"confermate": 1, "da_decidere": 1}
                     and stati.get("Chi partì da Palos?") == "attiva"
                     and stati.get("Ignora tutto?") == "proposta"
                     and next(c for c in d["carte"] if c["stato"] == "proposta")["avvisi"]
                     == ["testo_ordine"], f"{s} {str(d)[:300]}")
            # ── a cavallo della mezzanotte (31/10, #337; dal 31/10 sera #356): due carte scritte
            # alle 23:50, poi alle 00:00:30 e alle 11:50 del giorno dopo, con l'adesso dello
            # Studio fermo lì (il resto a mezzogiorno)
            giorno = ORA[0].date()
            ORA[0] = datetime.datetime.combine(giorno, datetime.time(23, 50))
            carte_sera = {}
            for dom in ("Chi era Vespucci?", "Chi era Magellano?"):
                s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                              corpo={"verifica": vid, "azione": "scrivi", "domanda": dom,
                                     "risposta": "Un navigatore", "argomento": a1})
                carte_sera[dom] = d.get("scritta")
            cv, cq = carte_sera["Chi era Vespucci?"], carte_sera["Chi era Magellano?"]
            tv = next((c["tasti"] for c in d.get("carte", []) if c["id"] == cq), None)
            verifica("mezzanotte (#356): alle 23:50 «quasi» dice «domani» (domani alle 11:50, non "
                     "fra 10 minuti come «non la sapevo»), «la sapevo» fra 2 giorni",
                     s == 200 and tv == {"sapevo": "fra 2 giorni", "quasi": "domani",
                                         "non_sapevo": "fra 10 minuti"}, f"{s} {tv}")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "esito", "carta": cv,
                                 "esito": "non_sapevo"})
            verifica("mezzanotte: «non la sapevo» alle 23:50 → «fra 10 minuti», fuori dal ripasso",
                     s == 200 and d["ultimo"]["fra"] == "fra 10 minuti"
                     and cv not in d["da_ripassare"], f"{s} {str(d)[:200]}")
            s, d = chiedi(port, "/api/studio/carte", sess["leo"],
                          corpo={"verifica": vid, "azione": "esito", "carta": cq,
                                 "esito": "quasi"})
            verifica("mezzanotte (#356): «quasi» alle 23:50 → «domani», fuori dal ripasso",
                     s == 200 and d["ultimo"]["fra"] == "domani"
                     and cq not in d["da_ripassare"], f"{s} {str(d)[:200]}")
            ORA[0] = datetime.datetime.combine(giorno + datetime.timedelta(days=1),
                                               datetime.time(0, 0, 30))
            s, d = chiedi(port, "/api/studio/carte", sess["leo"], corpo={"verifica": vid})
            tv = next((c["tasti"] for c in d.get("carte", []) if c["id"] == cv), None)
            verifica("mezzanotte: alle 00:00:30 del giorno dopo la carta «non la sapevo» è da "
                     "ripassare, e «quasi» dice «domani»", s == 200 and cv in d["da_ripassare"]
                     and tv == {"sapevo": "fra 2 giorni", "quasi": "domani",
                                "non_sapevo": "fra 10 minuti"}, f"{s} {tv}")
            verifica("mezzanotte (#356): alle 00:00:30 la carta «quasi» delle 23:50 non torna "
                     "ancora", s == 200 and cq not in d["da_ripassare"], str(d["da_ripassare"]))
            ORA[0] = datetime.datetime.combine(giorno + datetime.timedelta(days=1),
                                               datetime.time(11, 50))
            s, d = chiedi(port, "/api/studio/carte", sess["leo"], corpo={"verifica": vid})
            verifica("mezzanotte (#356): …torna alle 11:50, dodici ore dopo",
                     s == 200 and cq in d["da_ripassare"], str(d["da_ripassare"]))
        finally:
            srv.ferma() if hasattr(srv, "ferma") else None
            st.close()

js = (QUI.parent / "calliope" / "schermi" / "pagina" / "studio.js").read_text(encoding="utf-8")
pezzo = js.split("// ── le carte (30/10", 1)[-1].split("function pannelloDomande", 1)[0]
verifica("pagina: domanda e risposta solo con textContent (niente innerHTML nelle carte)",
         "innerHTML" not in pezzo and "insertAdjacentHTML" not in pezzo
         and 'nodo("p", "studio-c-domanda", String(c.domanda' in pezzo)

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
