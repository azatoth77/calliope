"""
Prova a secco della fase B dell'indice del programma (12/10/2026 sera, decisioni di Dario sugli
esercizi; nomi di fantasia). Niente modelli: le chiamate del tool sono quelle che farebbe il
modello, la data dell'anno scolastico è fissata.

1. **Limite stretto** (`programma.limite`, `matematica.genera(entro, cambio, solo)`): terza
   elementare a ottobre entro il 100 (livello 2, mai il 3 da solo), a marzo entro il 999; prima
   elementare a ottobre entro il 10 senza riporto (contrario: a marzo il riporto c'è); la salita
   automatica resta dentro la voce; frazioni in terza: nessun livello adatto, lo dice e propone
   un argomento della classe (contrario: in quarta parte); oltre solo se chiesto (oltre=true,
   «tre cifre», piu_difficile al limite), detto dal codice e solo per la sessione; ogni voce
   dell'indice con un livello genera esercizi dentro il suo limite.
2. **Numeri**: frasi per ripetere sempre diverse (mai due uguali di fila), col tono; dopo due
   non capiti lo schermo, se c'è (contrari: il primo, senza schermo); una risposta senza numero.
3. **A che punto siete**: a inizio sessione per un minore se manca o ha più di 14 giorni
   (contrari: appena detto, un adulto, `esercizi_punto_giorni: 0`); la risposta mappata
   sull'indice stringe il limite; non mappata → la foto della pagina; «non lo so» → si parte
   dal programma; a metà sessione con molte sbagliate o tutte giuste, una volta sola; un
   tutore lo dice per il ragazzo (contrario: un adulto che non lo segue); la classe salvata e
   l'anno dopo; 60 giorni e svuota.
4. **Interrogazioni**: dall'indice (domande aperte con i criteri, giudizio e sicurezza del
   modello, «da guardare» nel riepilogo per i tutori; i conti dal codice; il problema solo con
   l'operazione chiesta), dalla pagina del libro (con le domande prese da lì), senza pagina per
   storia o «il capitolo 4» la chiede (contrari).
"""

import datetime
import json
import sqlite3
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope import conserva as C  # noqa: E402
from calliope import minori as M  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.esercizi import matematica as MAT  # noqa: E402
from calliope.esercizi import programma as P  # noqa: E402
from calliope.esercizi import sessione as SE  # noqa: E402
from calliope.esercizi.modello import Classe  # noqa: E402
from calliope.esercizi.numeri import frazione_scritta  # noqa: E402
from calliope.esercizi.registro import Registro  # noqa: E402
from calliope.esercizi.varianti import CATALOGO as VARIANTI, Varianti  # noqa: E402
from calliope.frasi import FRASI  # noqa: E402
from calliope.speaker_id import SpeakerContext, UserProfile, name_key  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


OTTOBRE = datetime.date(2026, 10, 12)
MARZO = datetime.date(2027, 3, 10)

# ─────────────────────────── 1a. i generatori col limite ───────────────────────────
print("── i generatori dentro il limite ──")


def semi(arg, liv, n=300, **lim):
    return [MAT.genera(arg, liv, s, **lim) for s in range(n)]


es = semi("addizioni", 2, entro=100)
verifica("addizioni livello 2 entro 100: mai oltre 100 (senza limite arriva a 168)",
         max(max(MAT.numeri_di(e)) for e in es) <= 100
         and max(max(MAT.numeri_di(e)) for e in semi("addizioni", 2)) > 100)
es = semi("addizioni", 1, entro=10, cambio=False)
verifica("prima a ottobre: entro 10, mai un riporto",
         all(max(MAT.numeri_di(e)) <= 10 and not MAT.riporto(*e.dati["operandi"]) for e in es))
es = semi("addizioni", 1, entro=20)
verifica("contrario: entro 20 col cambio ammesso, il riporto c'è",
         any(MAT.riporto(*e.dati["operandi"]) for e in es))
es = semi("sottrazioni", 2, entro=100, cambio=True)
verifica("sottrazioni col prestito obbligato: sempre un prestito",
         all(MAT.prestito(*e.dati["operandi"]) for e in es))
es = semi("problemi", 3, solo={"+"})
verifica("problemi di un'interrogazione sulle addizioni: solo «+»",
         all(MAT.operazioni_di(e.espressione) == {"+"} for e in es))
verifica("contrario: senza limite i problemi del livello 3 hanno anche − e ×",
         {"-", "*"} <= set().union(*(MAT.operazioni_di(e.espressione) for e in semi("problemi", 3))))
es = semi("problemi", 3, solo={"*"})
verifica("problemi solo con «×»", all(MAT.operazioni_di(e.espressione) == {"*"} for e in es))
try:
    MAT.genera("problemi", 1, 1, solo={"/"})
    verifica("nessun problema di divisione al livello 1: ValueError", False)
except ValueError:
    verifica("nessun problema di divisione al livello 1: ValueError, mai un problema a caso", True)
verifica("operazioni_di: «10-3*2» → {-, *}", MAT.operazioni_di("10-3*2") == {"-", "*"})

# Ogni voce dell'indice con un livello genera dentro il suo limite
fuori = []
controllate = 0
for nome in ("matematica",):
    for arg, classi in P.carica()[nome]["mappa"].items():
        for cl in classi:
            for d in (OTTOBRE, MARZO):
                lim = P.limite(arg, Classe.da_testo(cl), d)
                if lim is None or not lim.adatto:
                    continue
                controllate += 1
                for s in range(60):
                    try:
                        e = MAT.genera(arg, lim.livello, s, entro=lim.entro, cambio=lim.cambio)
                    except ValueError as x:
                        fuori.append((arg, cl, str(d), str(x)))
                        break
                    if not MAT.rispetta(e, lim.entro, lim.cambio):
                        fuori.append((arg, cl, str(d), e.testo))
                        break
verifica(f"ogni voce della mappa con un livello genera dentro il limite ({controllate} voci)",
         not fuori and controllate >= 30, fuori[:3])

# ─────────────────────────── 1b. il limite dell'indice ───────────────────────────
print("── il limite dell'indice ──")
TERZA, QUARTA, PRIMA = Classe("elementari", 3), Classe("elementari", 4), Classe("elementari", 1)
lim = P.limite("addizioni", TERZA, OTTOBRE)
verifica("terza a ottobre: addizioni livello 2 entro 100, Indicazioni 2012",
         (lim.livello, lim.entro, lim.indicazioni) == (2, 100, "2012"), lim)
lim = P.limite("addizioni", TERZA, MARZO)
verifica("terza a marzo: livello 3 entro 999", (lim.livello, lim.entro) == (3, 999), lim)
lim = P.limite("addizioni", PRIMA, OTTOBRE)
verifica("prima a ottobre: entro 10 senza cambio", (lim.entro, lim.cambio) == (10, False), lim)
verifica("contrario: prima a marzo, il cambio come capita",
         P.limite("addizioni", PRIMA, MARZO).cambio is None)
verifica("frazioni in terza: livello 0 (nessun livello adatto)",
         not P.limite("frazioni", TERZA, OTTOBRE).adatto)
verifica("divisioni in seconda: prima della mappa, livello 0",
         not P.limite("divisioni", Classe("elementari", 2), OTTOBRE).adatto)
verifica("contrario: addizioni in seconda media, dopo la mappa: nessun limite",
         P.limite("addizioni", Classe("medie", 2), OTTOBRE) is None)
verifica("contrario: logica senza mappa: nessun limite", P.limite("sequenze", TERZA) is None)
lim = P.con_punto(P.limite("addizioni", TERZA, OTTOBRE),
                  {"argomento": "addizioni", "entro": 5000, "cambio": True})
verifica("a che punto «entro 5000» in terza: tenuto dentro l'anno (999, livello 3)",
         (lim.entro, lim.livello, lim.cambio, lim.fonte) == (999, 3, True, "punto"), lim)
verifica("contrario: il punto di un altro argomento non cambia il limite",
         P.con_punto(P.limite("addizioni", TERZA, OTTOBRE),
                     {"argomento": "sottrazioni", "entro": 20}).entro == 100)
verifica("interrogazioni.yaml: forma giusta (in controlla)", not P.controlla(), P.controlla())
verifica("domande aperte per le addizioni in terza", len(P.domande_aperte("addizioni", TERZA)) == 2)

# ─────────────────────────── servizio ───────────────────────────
TMP = Path(tempfile.mkdtemp(prefix="calliope-esercizi-programma-"))
cfg = Config()
cfg.memory_db = str(TMP / "memoria.db")
cfg.esercizi_pronti = 0
OGGI = datetime.date.today()


def nato(anni: int) -> str:
    d = OGGI - datetime.timedelta(days=30)
    try:
        return d.replace(year=d.year - anni).isoformat()
    except ValueError:
        return (d - datetime.timedelta(days=1)).replace(year=d.year - anni).isoformat()


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


def profilo(nome, anni=None, admin=False, tutori=None, gender="f"):
    pr = UserProfile(nome, admin=admin, gender=gender,
                     nascita=nato(anni) if anni is not None else None, tutori=list(tutori or []))
    pr.id = nome.lower() + "-id"
    return pr


# Nomi di fantasia: Ada amministra ed è tutrice; Ugo è un adulto che non segue nessuno
ADA = profilo("Ada", admin=True)
UGO = profilo("Ugo", gender="m")
NINA = profilo("Nina", 8, tutori=["ada-id"])            # terza elementare
TEO = profilo("Teo", 9, tutori=["ada-id"], gender="m")  # quarta
REG = Reg([ADA, UGO, NINA, TEO])


class HubFinto:
    def __init__(self):
        self.schede = []
        self.personale = False

    def invia(self, scheda, mittente, forza=False):
        self.schede.append((scheda, mittente))
        return {"schermi": ["camera"], "destinatari": ["camera"], "motivo": ""}

    def mittente(self, ctx):
        from calliope.schermi.hub import mittente_da
        return mittente_da(ctx)

    def personale_collegato(self, mittente):
        return self.personale

    def ultima(self, sender):
        return None


HUB = HubFinto()
M.prepara(cfg, schermi=HUB, registry=REG, log=lambda *a: None)
REGISTRO = Registro(cfg.memory_db)


def servizio_nuovo(data=OTTOBRE):
    srv = SE.Servizio(cfg, REGISTRO, schermi=HUB, log=lambda *a: None, registry=REG)
    srv._oggi = lambda: data
    SE.imposta(srv)
    return srv


class Giudice:
    """Il giudice finto delle domande aperte (niente modello nelle prove a secco)."""
    pronto = False                      # nessun secondo parere per l'italiano: nessun modello
    ultimo_ms, ultimo_errore, modello = None, "prova", ""

    def __init__(self):
        self.v, self.chiamate = None, 0

    def chiedi(self, prompt, opzioni):
        return None

    def risolvi(self, es):
        return None

    def giudica(self, domanda, criteri, risposta):
        self.chiamate += 1
        return self.v


GIUDICE = Giudice()
_servizio_nuovo = servizio_nuovo


def servizio_nuovo(data=OTTOBRE):
    srv = _servizio_nuovo(data)
    srv._parere = GIUDICE
    return srv


SRV = servizio_nuovo()
TOOLS = build_registry(minori_tool=True)
from calliope.tools.minori import minori_specs  # noqa: E402

for spec in minori_specs():
    TOOLS.register(spec)


class Album:
    """Una foto nella conversazione (la pagina del libro)."""
    def __len__(self):
        return 1


def chiama(args, chi, detto="", storia=(), pagina=False):
    sc = SpeakerContext(REG)
    sc.current_speaker = chi
    sc.identified_by = "voce"
    ctx = ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None, schermi=HUB)
    ctx.regole = []
    ctx.user_text = detto
    ctx.storia = list(storia)
    if pagina:
        ctx.immagini = Album()
    return json.loads(TOOLS.call("esercizi", args, ctx, sc.current_level)), ctx


def giusta(chi, n=1):
    out = None
    for _ in range(n):
        s = SRV.sessione(REG.get(chi).id)
        out, _ = chiama({"azione": "rispondi", "risposta": frazione_scritta(s.es.risposta)}, chi)
    return out


def sbagliata(chi):
    s = SRV.sessione(REG.get(chi).id)
    return chiama({"azione": "rispondi", "risposta": frazione_scritta(s.es.risposta + 3)}, chi)


# Le prove del limite senza la domanda «a che punto siete» (ha la sua parte sotto)
cfg.esercizi_punto_giorni = 0

print("── la sessione dentro il limite ──")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("terza a ottobre: livello 2, entro 100, livello più alto 2",
         (s.livello, s.entro, s.livello_max) == (2, 100, 2), (s.livello, s.entro, s.livello_max))
massimo = 0
for _ in range(4):
    massimo = max(massimo, max(MAT.numeri_di(SRV.sessione(NINA.id).es)))
    out = giusta("Nina")
s = SRV.sessione(NINA.id)
verifica("tre giuste al primo colpo: niente salita oltre la voce (resta al 2)", s.livello == 2,
         s.livello)
verifica("i numeri restano entro il 100", massimo <= 100, massimo)
out, ctx = chiama({"azione": "piu_facile"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("piu_facile: livello 1, regola", s.livello == 1 and "esercizi_piu_facile" in ctx.regole)
giusta("Nina", 1)        # quinto: fine blocco (terza: blocchi da 5)
chiama({"azione": "continua"}, "Nina")
giusta("Nina", 3)
s = SRV.sessione(NINA.id)
verifica("salita dentro il limite: dal 1 torna al 2, non al 3", s.livello == 2, s.livello)
out, ctx = chiama({"azione": "piu_difficile"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("piu_difficile al limite: oltre il programma, detto dal codice",
         s.oltre and s.livello == 3 and "oltre il programma di terza elementare"
         in out["risposta_finale"] and "esercizi_oltre_programma" in ctx.regole, out)
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("oltre vale solo per quella sessione: la nuova torna al limite",
         not s.oltre and s.livello == 2 and s.entro == 100, (s.oltre, s.livello))
chiama({"azione": "fine"}, "Nina")

print("── nessun livello adatto ──")
out, ctx = chiama({"azione": "inizia", "argomento": "frazioni"}, "Nina")
verifica("frazioni in terza: lo dice e propone argomenti della classe",
         "non ho esercizi adatti" in out["risposta_finale"]
         and ("le addizioni" in out["risposta_finale"] or "le sottrazioni" in out["risposta_finale"])
         and "esercizi_fuori_programma" in ctx.regole and SRV.sessione(NINA.id) is None, out)
verifica("la proposta resta in sospeso con gli argomenti come istruzioni (oltre=true solo per "
         "chi insiste: un «sì» non riparte con la sola materia)",
         "azione=inizia" in out.get("in_sospeso", {}).get("argomenti", "")
         and "argomento=frazioni e oltre=true" in out["in_sospeso"]["argomenti"]
         and "oltre=true" in out["in_sospeso"]["messaggio"], out.get("in_sospeso"))
out, ctx = chiama({"azione": "inizia", "argomento": "frazioni"}, "Teo")
verifica("contrario: frazioni in quarta partono", SRV.sessione(TEO.id) is not None
         and SRV.sessione(TEO.id).argomento == "frazioni", out)
chiama({"azione": "fine"}, "Teo")
out, ctx = chiama({"azione": "inizia", "materia": "matematica"}, "Nina")
verifica("dopo il rifiuto, la sola materia («sì, voglio provarle lo stesso» del 4B): una "
         "domanda sì/no del codice, in sospeso con oltre=true",
         "Vuoi provare le frazioni lo stesso" in out["risposta_finale"]
         and out["in_sospeso"]["argomenti"] == {"azione": "inizia", "materia": "matematica",
                                                "argomento": "frazioni", "oltre": True}
         and "esercizi_oltre_domanda" in ctx.regole and SRV.sessione(NINA.id) is None, out)
out, ctx = chiama({"azione": "inizia", "argomento": "frazioni"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("le chiede di nuovo subito dopo il rifiuto: insiste, oltre il programma",
         s is not None and s.oltre and "esercizi_oltre_insiste" in ctx.regole
         and "oltre il programma" in out["risposta_finale"], out)
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "inizia", "argomento": "frazioni"}, "Nina")
verifica("contrario: dopo che ha insistito una volta, la richiesta nuova si rifiuta di nuovo",
         SRV.sessione(NINA.id) is None and "esercizi_fuori_programma" in ctx.regole, ctx.regole)
SRV._rifiutati[NINA.id] = ("matematica", "frazioni", 0.0)
out, ctx = chiama({"azione": "inizia", "argomento": "frazioni"}, "Nina")
verifica("contrario: un rifiuto di più di 10 minuti fa non vale come insistere",
         SRV.sessione(NINA.id) is None and "esercizi_fuori_programma" in ctx.regole, ctx.regole)
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
verifica("contrario: un argomento diverso dopo il rifiuto parte normale, senza oltre",
         SRV.sessione(NINA.id) is not None and not SRV.sessione(NINA.id).oltre, out)
chiama({"azione": "fine"}, "Nina")
SRV._rifiutati.clear()
out, ctx = chiama({"azione": "inizia", "argomento": "frazioni", "oltre": True}, "Nina")
s = SRV.sessione(NINA.id)
verifica("frazioni in terza chieste lo stesso: «un passo oltre il programma», livello 1",
         s is not None and s.oltre and s.livello == 1 and "oltre il programma di terza"
         in out["risposta_finale"] and "esercizi_oltre_programma" in ctx.regole, out)
# Caso vero della DGX (13/10): «Facciamo frazioni, livello da terza elementare. Questo va un po'
# oltre il programma di terza elementare…» si contraddiceva
verifica("oltre il programma: niente «livello da terza», l'argomento con l'articolo",
         "livello da" not in out["risposta_finale"]
         and out["risposta_finale"].startswith("Facciamo le frazioni."), out["risposta_finale"])
chiama({"azione": "fine"}, "Nina")
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
verifica("contrario: dentro il programma «Facciamo le addizioni, livello da terza elementare.»",
         out["risposta_finale"].startswith(
             "Facciamo le addizioni, livello da terza elementare."), out["risposta_finale"])
chiama({"azione": "fine"}, "Nina")

SRV._rifiutati.clear()
out, ctx = chiama({"azione": "inizia", "materia": "matematica"}, "Nina",
                  detto="Facciamo le frazioni.")
verifica("inizia con la sola materia e la frase che nomina le frazioni (4B): l'argomento dalla "
         "frase, e il rifiuto", "esercizi_argomento_dalla_frase" in ctx.regole
         and "esercizi_fuori_programma" in ctx.regole, ctx.regole)
out, ctx = chiama({"azione": "inizia", "materia": "matematica"}, "Nina",
                  detto="Sì, voglio provarle lo stesso.")
verifica("«sì, voglio provarle lo stesso» con la sola materia: la domanda sì/no",
         "esercizi_oltre_domanda" in ctx.regole
         and "esercizi_argomento_dalla_frase" not in ctx.regole, ctx.regole)
SRV._rifiutati.clear()
out, ctx = chiama({"azione": "inizia", "materia": "matematica"}, "Nina",
                  detto="Facciamo le addizioni e le sottrazioni.")
verifica("contrario: due argomenti nella frase → «Su che cosa?»",
         "Su che cosa" in out["risposta_finale"]
         and "esercizi_argomento_dalla_frase" not in ctx.regole, out["risposta_finale"])
out, ctx = chiama({"azione": "inizia", "materia": "matematica"}, "Nina",
                  detto="Facciamo un po' di matematica.")
verifica("contrario: nessun argomento nella frase → «Su che cosa?»",
         "Su che cosa" in out["risposta_finale"], out["risposta_finale"])

print("── «entro» chiesto ──")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni", "entro": "tre cifre"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("«facciamo quelle a tre cifre» a ottobre in terza: oltre, entro 999, detto",
         s.oltre and s.entro == 999 and s.livello == 3 and "oltre il programma"
         in out["risposta_finale"], (s.entro, s.livello, out["risposta_finale"]))
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni", "entro": "20"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("contrario: «entro il 20» è dentro il limite: livello 1, niente «oltre»",
         not s.oltre and s.entro == 20 and s.livello == 1 and "oltre" not in
         out["risposta_finale"] and max(MAT.numeri_di(s.es)) <= 20, out["risposta_finale"])
chiama({"azione": "fine"}, "Nina")

# ─────────────────────────── 2. numeri non capiti ───────────────────────────
print("── ripetere il numero, con frasi diverse ──")
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
v = int(s.es.risposta)
frasi = []
for i in range(6):
    out, ctx = chiama({"azione": "rispondi", "risposta": str(v)}, "Nina", detto="Prenta due")
    frasi.append(out["risposta_finale"])
verifica("«Prenta due» col numero giusto: mai giudicato", s.errori == 0 and s.fatti == 0)
verifica("sei richieste: mai la stessa frase due volte di fila",
         all(a != b for a, b in zip(frasi, frasi[1:])), frasi)
verifica("le frasi vengono dalle varianti (ripetere scandendo, una cifra alla volta)",
         all(any(f.startswith(x) for x in VARIANTI["numero.ripeti"]["normale"]) for f in frasi))
verifica("contrario: senza schermo, nessuna proposta dello schermo",
         not any("schermo" in f for f in frasi), frasi)
chiama({"azione": "fine"}, "Nina")
HUB.personale = True
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
v = int(s.es.risposta)
out1, ctx1 = chiama({"azione": "rispondi", "risposta": str(v)}, "Nina", detto="Suttanto")
out2, ctx2 = chiama({"azione": "rispondi", "risposta": str(v)}, "Nina", detto="Salida")
verifica("contrario: il primo non capito non propone lo schermo",
         "schermo" not in out1["risposta_finale"], out1["risposta_finale"])
verifica("il secondo non capito, con lo schermo personale: «scrivilo sullo schermo»",
         "schermo" in out2["risposta_finale"] and "esercizi_numero_schermo" in ctx2.regole,
         out2["risposta_finale"])
out, ctx = chiama({"azione": "rispondi", "risposta": "boh"}, "Nina", detto="boh")
verifica("una risposta senza numero: non capito (varianti), nessun tentativo",
         "esercizi_numero_schermo" in ctx.regole and s.errori == 0, ctx.regole)
giusta("Nina")
out, ctx = chiama({"azione": "rispondi", "risposta": "boh"}, "Nina", detto="boh")
verifica("esercizio nuovo: si riparte da zero non capiti (niente schermo al primo)",
         "esercizi_numero_non_capito" in ctx.regole and "schermo" not in out["risposta_finale"],
         ctx.regole)
HUB.personale = False
chiama({"azione": "fine"}, "Nina")
var = Varianti()
FRASI.inizio_turno("prova-formale", "formale")
f1 = var.dici("numero.ripeti", "x")
FRASI.inizio_turno("prova-formale", None)
verifica("col tono formale le varianti formali (il «lei»)",
         f1 in VARIANTI["numero.ripeti"]["formale"], f1)
verifica("contrario: senza varianti per il tono, quelle normali",
         var.dici("numero.schermo", "x", tono="ironico") in VARIANTI["numero.schermo"]["normale"])

# ─────────────────────────── 3. a che punto siete ───────────────────────────
print("── a che punto siete ──")
cfg.esercizi_punto_giorni = 14
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("prima sessione di matematica: la domanda, detta dal codice, senza esercizio",
         s.es is None and s.attesa_punto == "inizio" and "a che punto siete in matematica"
         in out["risposta_finale"].lower() and "esercizi_punto_inizio" in ctx.regole, out)
verifica("in sospeso: azione a_che_punto, un «no» non la rifiuta",
         out["in_sospeso"]["argomenti"]["azione"] == "a_che_punto"
         and out["in_sospeso"].get("risposta") is True)
verifica("dato del turno: aspetta a che punto sono", "a_che_punto" in M.dato_turno(NINA))
out, ctx = chiama({"azione": "rispondi", "risposta": "le addizioni"}, "Nina")
verifica("una «risposta» mentre aspetta: ok false con cosa fare (a_che_punto)",
         out.get("ok") is False and "a_che_punto" in out.get("cosa_fare", ""), out)
# Il 4B del 12/10 sera: «siamo alle addizioni col riporto, fino a cento» → continua, entro=100
out, ctx = chiama({"azione": "continua", "entro": "100", "materia": "matematica"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("«continua» con entro mentre aspetta: vale come a_che_punto (azione dedotta)",
         "esercizi_azione_dedotta" in ctx.regole and "esercizi_punto_salvato" in ctx.regole
         and s.entro == 100 and s.es is not None, (ctx.regole, out["risposta_finale"]))
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("contrario: lo stesso giorno, dopo il punto, nessuna domanda", s.attesa_punto is None)
chiama({"azione": "fine"}, "Nina")
REGISTRO.salva_punto(NINA.id, "matematica", {}, OTTOBRE - datetime.timedelta(days=30))
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
out, ctx = chiama({"azione": "continua"}, "Nina")
verifica("contrario: «continua» senza dati è «non lo so», non a_che_punto",
         "esercizi_punto_saltato" in ctx.regole and "esercizi_punto_salvato" not in ctx.regole,
         ctx.regole)
chiama({"azione": "fine"}, "Nina")
REGISTRO.salva_punto(NINA.id, "matematica", {}, OTTOBRE - datetime.timedelta(days=30))
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
out, ctx = chiama({"azione": "a_che_punto", "argomento": "addizioni col riporto",
                   "entro": "20", "riporto": True}, "Nina")
s = SRV.sessione(NINA.id)
verifica("risposta mappata: salvata, detta dal codice, e la prima domanda",
         "addizioni col riporto entro il 20" in out["risposta_finale"]
         and "Prima domanda" in out["risposta_finale"] and s.es is not None
         and "esercizi_punto_salvato" in ctx.regole, out["risposta_finale"])
verifica("il limite stretto dal punto: entro 20 col riporto, livello 1",
         (s.entro, s.cambio, s.livello) == (20, True, 1)
         and MAT.riporto(*s.es.dati["operandi"]) and max(MAT.numeri_di(s.es)) <= 20,
         (s.entro, s.cambio, s.livello, s.es.testo))
r = REGISTRO.punto(NINA.id, "matematica")
verifica("salvato per persona e materia con la data", r["dati"]["argomento"] == "addizioni"
         and r["aggiornato"] == OTTOBRE, r)
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
verifica("contrario: detto oggi, la sessione dopo non lo richiede",
         SRV.sessione(NINA.id).es is not None and "esercizi_punto_inizio" not in ctx.regole)
chiama({"azione": "fine"}, "Nina")
SRV = servizio_nuovo(OTTOBRE + datetime.timedelta(days=15))
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
verifica("15 giorni dopo: «Siete ancora sulle addizioni col riporto entro il 20…»",
         "sulle addizioni col riporto entro il 20" in out["risposta_finale"]
         and "esercizi_punto_inizio" in ctx.regole, out["risposta_finale"])
out, ctx = chiama({"azione": "continua"}, "Nina")
verifica("«non lo so» (continua): si parte, regola esercizi_punto_saltato",
         SRV.sessione(NINA.id).es is not None and "esercizi_punto_saltato" in ctx.regole, out)
chiama({"azione": "fine"}, "Nina")
SRV = servizio_nuovo(OTTOBRE)
out, ctx = chiama({"azione": "inizia", "argomento": "divisioni"}, "Teo")
out, ctx = chiama({"azione": "a_che_punto", "argomento": "il teorema di Pitagora"}, "Teo")
verifica("risposta che non si collega all'indice: la foto della pagina, e si parte",
         any(out["risposta_finale"].startswith(x[:30]) for x in VARIANTI["punto.foto"]["normale"])
         and "esercizi_punto_foto" in ctx.regole, out["risposta_finale"])
chiama({"azione": "fine"}, "Teo")
out, ctx = chiama({"azione": "inizia", "materia": "matematica", "argomento": "addizioni"}, "Ada")
verifica("contrario: un adulto che prova gli esercizi non riceve la domanda",
         "esercizi_punto_inizio" not in ctx.regole, ctx.regole)
chiama({"azione": "fine"}, "Ada")
cfg.esercizi_punto_giorni = 0
out, ctx = chiama({"azione": "inizia", "argomento": "sottrazioni"}, "Teo")
verifica("contrario: esercizi_punto_giorni 0, mai la domanda",
         "esercizi_punto_inizio" not in ctx.regole and SRV.sessione(TEO.id).es is not None)
chiama({"azione": "fine"}, "Teo")
cfg.esercizi_punto_giorni = 14

print("── a metà sessione ──")
REGISTRO.salva_punto(TEO.id, "matematica", {"argomento": "moltiplicazioni"}, OTTOBRE)
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Teo")
regole = []
for _ in range(4):
    out, ctx = sbagliata("Teo")
    regole += ctx.regole
s = SRV.sessione(TEO.id)
verifica("quattro sbagliate di fila: «troppo difficili?», una domanda",
         "esercizi_punto_difficile" in regole and s.attesa_punto == "difficile", regole)
verifica("l'esercizio resta, e la domanda finisce con «?»",
         s.es is not None and out["risposta_finale"].endswith("?"), out["risposta_finale"])
out, ctx = chiama({"azione": "a_che_punto", "argomento": "addizioni", "entro": "100"}, "Teo")
verifica("la risposta a metà: limite nuovo e si continua", s.attesa_punto is None
         and s.entro == 100 and s.es is not None, (s.entro, out["risposta_finale"]))
regole = []
for _ in range(5):
    out, ctx = sbagliata("Teo")
    regole += ctx.regole
verifica("contrario: la seconda volta nella sessione non si richiede",
         "esercizi_punto_difficile" not in regole, regole)
chiama({"azione": "fine"}, "Teo")
out, ctx = chiama({"azione": "inizia", "argomento": "moltiplicazioni"}, "Teo")
s = SRV.sessione(TEO.id)
regole = []
for _ in range(5):
    out, ctx = giusta("Teo"), None
    if s.attesa_punto:
        break
verifica("cinque giuste al primo colpo al livello più alto: «troppo facili?»",
         s.attesa_punto == "facile" and s.livello == s.livello_max, (s.livello, s.livello_max))
chiama({"azione": "fine"}, "Teo")

print("── un tutore lo dice per il ragazzo ──")
out, ctx = chiama({"azione": "a_che_punto", "nome": "Nina", "materia": "matematica",
                   "argomento": "sottrazioni", "riporto": False, "entro": "100"}, "Ada")
r = REGISTRO.punto(NINA.id, "matematica")
verifica("Ada (tutrice): salvato per Nina", r["dati"]["argomento"] == "sottrazioni"
         and r["dati"]["cambio"] is False and "esercizi_punto_salvato" in ctx.regole, out)
out, ctx = chiama({"azione": "a_che_punto", "nome": "Nina", "materia": "matematica",
                   "argomento": "divisioni"}, "Ugo")
verifica("contrario: un adulto che non la segue no",
         out.get("ok") is False and REGISTRO.punto(NINA.id, "matematica")["dati"]["argomento"]
         == "sottrazioni", out)

print("── la classe salvata ──")
out, ctx = chiama({"azione": "a_che_punto", "classe": "quarta elementare",
                   "argomento": "addizioni"}, "Nina")
cfg.esercizi_punto_giorni = 0
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
verifica("la classe detta resta: quarta (non la terza dell'età)",
         SRV.sessione(NINA.id).classe == QUARTA, SRV.sessione(NINA.id).classe)
chiama({"azione": "fine"}, "Nina")
SRV = servizio_nuovo(datetime.date(2027, 10, 5))
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Nina")
verifica("l'anno scolastico dopo: quinta", SRV.sessione(NINA.id).classe == Classe("elementari", 5),
         SRV.sessione(NINA.id).classe)
chiama({"azione": "fine"}, "Nina")
SRV = servizio_nuovo(OTTOBRE)
cfg.esercizi_punto_giorni = 14

print("── conservazione ──")
db = sqlite3.connect(cfg.memory_db)
for chi, fa in (("vecchia-id", 61), ("sessanta-id", 60)):
    db.execute("INSERT INTO esercizi_punto (persona, materia, dati, aggiornato) VALUES "
               "(?, 'matematica', '{}', ?)", (chi, (OGGI - datetime.timedelta(days=fa)).isoformat()))
db.commit()
db.close()
REGISTRO.salva_punto(TEO.id, "matematica", {"argomento": "addizioni"}, OGGI)
cons = C.Conservazione(cfg, REG, log=lambda m: None)
cons.ruota()
db = sqlite3.connect(cfg.memory_db)
chi = {r[0] for r in db.execute("SELECT persona FROM esercizi_punto")}
db.close()
verifica("rotazione: «a che punto» di 61 giorni via, di 60 restano",
         "vecchia-id" not in chi and "sessanta-id" in chi and TEO.id in chi, chi)
cons.svuota(TEO.id, "Teo")
verifica("svuota la persona: anche «a che punto»", REGISTRO.punto(TEO.id, "matematica") is None)

# ─────────────────────────── 4. interrogazioni ───────────────────────────
print("── interrogazione sull'indice ──")
cfg.esercizi_punto_giorni = 0
out, ctx = chiama({"azione": "interroga", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
piano = [v["tipo"] for v in s.interroga["piano"]]
verifica("interroga le addizioni in terza: 5 domande, 2 aperte, un problema",
         len(piano) == 5 and piano.count("aperta") == 2 and piano.count("problema") == 1
         and "esercizi_interroga_indice" in ctx.regole, piano)
verifica("prima domanda aperta dall'indice, in sospeso col messaggio dei criteri",
         s.es.tipo == "aperta" and "Criteri" in out["in_sospeso"]["messaggio"]
         and s.es.testo in out["risposta_finale"], out)
verifica("dato del turno: domanda aperta con giudizio e sicurezza",
         "giudizio e sicurezza" in M.dato_turno(NINA))
out, ctx = chiama({"azione": "rispondi", "risposta": "si parte dalle unità e si riporta uno",
                   "giudizio": "giusta", "sicurezza": "alta"}, "Nina")
verifica("aperta giudicata giusta con sicurezza alta: conta", s.giuste == 1
         and "esercizi_aperta_giudicata" in ctx.regole, out)
verifica("contrario: col giudizio del modello della voce il giudice non si chiama",
         GIUDICE.chiamate == 0)
problema = None
while s.es is not None and s.es.tipo != "aperta":
    if s.es.argomento == "problemi":
        problema = s.es
    out = giusta("Nina")
verifica("il problema dell'interrogazione sulle addizioni ha solo addizioni",
         problema is not None and MAT.operazioni_di(problema.espressione) == {"+"},
         getattr(problema, "espressione", None))
verifica("i conti li corregge il codice (tutti giusti)", s.giuste == 4, s.giuste)
out, ctx = chiama({"azione": "rispondi", "risposta": "non cambia perché sì",
                   "giudizio": "giusta", "sicurezza": "bassa"}, "Nina")
verifica("sicurezza bassa: «da guardare», e l'interrogazione finisce col conto",
         "Interrogazione finita: molto bene!" in out["risposta_finale"]
         and "4" not in out["risposta_finale"].split("finita")[1]
         and "la guarda chi ti segue" in out["risposta_finale"]
         and SRV.sessione(NINA.id) is None, out["risposta_finale"])
rie = SRV.riepilogo(NINA)
verifica("riepilogo per i tutori: «da guardare tu», con la risposta nel campione",
         "da guardare tu" in rie["frase"] and any(c.get("da_guardare") for c in rie["campione"]),
         rie["frase"])
av = [a for a in M.avvisi().da_dire(ADA.id, segna=False) if a["tipo"] == "esercizi"]
verifica("avviso alla tutrice: interrogazione con una risposta da guardare",
         any("interrogazione" in a["testo"] for a in av), av)

out, ctx = chiama({"azione": "interroga", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
GIUDICE.v = None
out, ctx = chiama({"azione": "rispondi", "risposta": "boh"}, "Nina")
verifica("aperta senza giudizio e il giudice che non risponde: da guardare, mai giusta da sola",
         s.interroga["da_guardare"] == 1 and s.giuste == 0 and GIUDICE.chiamate == 1
         and "esercizi_aperta_da_guardare" in ctx.regole, out)
while s.es is not None and s.es.tipo != "aperta" and SRV.sessione(NINA.id) is not None:
    giusta("Nina")
GIUDICE.v = ("giusta", "alta")
out, ctx = chiama({"azione": "rispondi", "risposta": "non cambia, l'ordine non conta"}, "Nina")
verifica("aperta senza giudizio del modello della voce: lo dà il giudice col codice (4B)",
         s.giuste == 4 and GIUDICE.chiamate == 2 and "esercizi_aperta_giudice" in ctx.regole
         and "esercizi_aperta_giudicata" in ctx.regole, (ctx.regole, s.giuste))
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "interroga", "argomento": "addizioni"}, "Nina")
s = SRV.sessione(NINA.id)
GIUDICE.v = ("giusta", "bassa")
out, ctx = chiama({"azione": "rispondi", "risposta": "mah, forse sì"}, "Nina")
verifica("il giudice non è sicuro: da guardare", s.interroga["da_guardare"] == 1
         and s.giuste == 0, ctx.regole)
while s.es is not None and s.es.tipo != "aperta" and SRV.sessione(NINA.id) is not None:
    giusta("Nina")
n = GIUDICE.chiamate
GIUDICE.v = ("giusta", "alta")
out = SRV.rispondi(NINA, "si comincia dalle unità", canale="scheda")
verifica("dalla scheda: anche la risposta scritta la giudica il giudice",
         GIUDICE.chiamate == n + 1 and "Interrogazione finita" in out["risposta_finale"], out)
chiama({"azione": "fine"}, "Nina")
out, ctx = chiama({"azione": "interroga", "argomento": "frazioni",
                   "classe": "terza elementare"}, "Nina")
verifica("interrogazione sulle frazioni in terza: nessun livello adatto, si propone altro",
         "non ho esercizi adatti" in out["risposta_finale"] and SRV.sessione(NINA.id) is None,
         out["risposta_finale"])

out, ctx = chiama({"azione": "interroga", "materia": "matematica"}, "Teo",
                  detto="Simuliamo un'interrogazione sulle addizioni.")
verifica("interroga con la sola materia e la frase che nomina un argomento: quello "
         "(esercizi_argomento_dalla_frase)", SRV.sessione(TEO.id) is not None
         and SRV.sessione(TEO.id).argomento == "addizioni"
         and "esercizi_argomento_dalla_frase" in ctx.regole, ctx.regole)
chiama({"azione": "fine"}, "Teo")
out, ctx = chiama({"azione": "interroga", "materia": "matematica"}, "Teo",
                  detto="Mi interroghi di matematica?")
verifica("contrario: la frase non nomina un argomento → «Su che cosa ti interrogo?»",
         SRV.sessione(TEO.id) is None and "Su che cosa ti interrogo" in out["risposta_finale"]
         and "esercizi_interroga_quale" in ctx.regole, out["risposta_finale"])
out, ctx = chiama({"azione": "interroga", "materia": "matematica"}, "Teo",
                  detto="Interrogami sulle addizioni e sulle sottrazioni.")
verifica("contrario: due argomenti nella frase → la domanda, non una scelta a caso",
         SRV.sessione(TEO.id) is None and "esercizi_interroga_quale" in ctx.regole, ctx.regole)

print("── interrogazione dalla pagina ──")
out, ctx = chiama({"azione": "interroga", "argomento": "storia, gli egizi"}, "Teo")
verifica("storia senza la pagina: la chiede, non improvvisa",
         ("pagina del libro" in out["risposta_finale"] or "testo del libro" in out["risposta_finale"])
         and "esercizi_interroga_serve_pagina" in ctx.regole, out["risposta_finale"])
verifica("nessuna sessione aperta", SRV.sessione(TEO.id) is None)
out, ctx = chiama({"azione": "interroga", "argomento": "il capitolo 4 sulle frazioni"}, "Teo")
verifica("«il capitolo 4» senza la pagina: la chiede anche se c'è un argomento noto",
         "esercizi_interroga_serve_pagina" in ctx.regole, ctx.regole)
out, ctx = chiama({"azione": "interroga", "argomento": "storia, gli egizi"}, "Teo", pagina=True)
verifica("con la pagina ma senza le domande: ok false, cosa fare (prenderle dalla pagina)",
         out.get("ok") is False and "pagina" in out.get("cosa_fare", ""), out)
out, ctx = chiama({"azione": "interroga", "argomento": "storia, gli egizi", "domande": [
    "Dove vivevano gli antichi Egizi", "Chi era il faraone?", "A che cosa servivano le piramidi?"]},
    "Teo", pagina=True)
s = SRV.sessione(TEO.id)
verifica("contrario: con la pagina e le domande parte, tre domande aperte",
         s is not None and s.interroga["tipo"] == "pagina" and len(s.interroga["piano"]) == 3
         and s.es.testo == "Dove vivevano gli antichi Egizi?"
         and "esercizi_interroga_pagina" in ctx.regole, out)
chiama({"azione": "rispondi", "risposta": "lungo il Nilo", "giudizio": "giusta",
        "sicurezza": "alta"}, "Teo")
chiama({"azione": "rispondi", "risposta": "un dio", "giudizio": "sbagliata",
        "sicurezza": "alta"}, "Teo")
out, ctx = chiama({"azione": "rispondi", "risposta": "per i re", "giudizio": "in_parte",
                   "sicurezza": "alta"}, "Teo")
verifica("fine dell'interrogazione dalla pagina (1 giusta su 3): giudizio a parole, senza voto",
         "da ripassare insieme" in out["risposta_finale"]
         and "1 su 3" not in out["risposta_finale"],
         out["risposta_finale"])

print()
print("ESITO: " + ("tutto ok" if not errori else f"{errori} errori"))
sys.exit(1 if errori else 0)
