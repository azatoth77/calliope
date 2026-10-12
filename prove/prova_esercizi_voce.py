"""
Prova a secco delle correzioni agli esercizi dopo la prova vera del 12/10/2026 (DGX, 26B, una
bambina di terza e quarta elementare; qui solo nomi di fantasia). Niente modelli.

- il numero si ricava dalla frase: «sedeci», «ventuno», «6 per 8, 48», «quattordici, ah no,
  sedici» passano; «Suttanto salida» → 76, «Pantano a bit» → 79, «Prenta due» → 22 e (dal 12/10
  sera, niente approssimazioni) → 32 no (regola `esercizi_numero_non_detto`, nessun tentativo
  contato, frase di `varianti.py`); «Bentanto» → 28 no;
- le domande le fa solo il programma: una risposta a una domanda inventata dal modello non si
  giudica (`esercizi_domanda_non_sua`), con i contrari (la domanda del programma, una frase
  senza domanda); in Brain, dopo la spinta, la domanda inventata non si dice e al suo posto c'è
  quella del programma (`esercizi_domanda_inventata`), la promessa «Segno tutto» nemmeno
  (`esercizi_promessa_taciuta`), una frase d'altro sì; la spinta anche a sessione aperta senza
  l'azione in sospeso;
- blocchi: 5 esercizi in terza elementare, 10 in quarta, poi «Facciamo una pausa o cambiamo?»
  detta dal codice con l'azione in sospeso; in pausa una risposta non si giudica; «continua»;
  «pausa» a metà esercizio;
- punti (2 al primo colpo, 1 dopo un errore) e tappe («Tappa 1 di 3 superata!», percorso
  finito all'ultima), modo giocoso («Sfida numero…»), detti dal codice;
- preferenze salvate per persona: valgono in una sessione nuova e con un servizio nuovo (una
  conversazione nuova, un riavvio); scadono con la conservazione (61 giorni via, 60 restano) e si
  svuotano con la persona;
- «Un indizio:» mai senza indizio;
- `schermo_mostra` con un testo scelto (`cosa=testo`) e, con gli esercizi aperti, l'esercizio;
- «te lo scrivo qui nella conversazione» tolto a chi parla a voce, non a chi scrive.
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
from calliope.esercizi import sessione as SE  # noqa: E402
from calliope.esercizi.numeri import frazione_scritta, in_lettere, valore_detto  # noqa: E402
from calliope.esercizi.registro import Registro  # noqa: E402
from calliope.speaker_id import SpeakerContext, UserProfile, name_key  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


# ─────────────────────────── il numero detto ───────────────────────────
print("── il numero si ricava dalla frase ──")
for detto, valore in (("sedeci", 16), ("Sedeci.", 16), ("ventuno", 21), ("6 per 8, 48", 48),
                      ("quattordici, ah no, sedici", 16), ("Ottantatre.", 83), ("83", 83),
                      ("trenta due", 32), ("centoventi tre", 123),
                      ("trecentosedeci", 316), ("ventiquatro", 24), ("diciasette", 17),
                      ("tre quarti", Fraction(3, 4)), ("meno tre", -3),
                      ("due virgola cinque metri al secondo", Fraction(5, 2)),
                      ("Fa 104.", 104), ("il risultato è quarantotto", 48)):
    verifica(f"passa: «{detto}» → {valore}", valore_detto(Fraction(valore), detto))
for detto, valore in (("Suttanto salida", 76), ("Pantano a bit", 79), ("Prenta due", 22),
                      ("Prenta due", 32), ("trenda", 30), ("sedecina", 16),
                      ("Bentanto", 28), ("otto per sei", 48), ("quattordici, ah no, sedici", 15),
                      ("sei", 16)):
    verifica(f"contrario: «{detto}» non dà {valore}", not valore_detto(Fraction(valore), detto))
verifica("frase vuota (scheda, prove): nessun controllo", valore_detto(Fraction(7), ""))
verifica("ogni numero da 0 a 999 detto in lettere si ricava",
         all(valore_detto(Fraction(n), in_lettere(n)) for n in range(1000)))

# ─────────────────────────── servizio ───────────────────────────
TMP = Path(tempfile.mkdtemp(prefix="calliope-esercizi-voce-"))
cfg = Config()
cfg.memory_db = str(TMP / "memoria.db")
cfg.esercizi_pronti = 0
cfg.esercizi_punto_giorni = 0          # «a che punto siete» ha la sua prova (prova_esercizi_programma)
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


# Nomi di fantasia
ADA = profilo("Ada", admin=True)
NINA = profilo("Nina", 8, tutori=["ada-id"])          # terza elementare: blocchi da 5
TEO = profilo("Teo", 9, tutori=["ada-id"], gender="m")  # quarta: blocchi da 10
REG = Reg([ADA, NINA, TEO])


class HubFinto:
    def __init__(self):
        self.schede = []

    def invia(self, scheda, mittente, forza=False):
        self.schede.append((scheda, mittente))
        return {"schermi": ["camera"], "destinatari": ["camera"], "motivo": ""}

    def mittente(self, ctx):
        from calliope.schermi.hub import mittente_da
        return mittente_da(ctx)

    def ultima(self, sender):
        return None


HUB = HubFinto()
M.prepara(cfg, schermi=HUB, registry=REG, log=lambda *a: None)
REGISTRO = Registro(cfg.memory_db)
SRV = SE.Servizio(cfg, REGISTRO, schermi=HUB, log=lambda *a: None, registry=REG)
SE.imposta(SRV)
TOOLS = build_registry(minori_tool=True)
from calliope.tools.minori import minori_specs  # noqa: E402
from calliope.tools.schermi import schermi_specs  # noqa: E402

for spec in minori_specs():
    TOOLS.register(spec)
if TOOLS.get("schermo_mostra") is None:
    for spec in schermi_specs():
        TOOLS.register(spec)


def ctx_di(nome, how="voce", detto="", storia=()):
    sc = SpeakerContext(REG)
    sc.current_speaker = nome
    sc.identified_by = how if nome else None
    c = ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None, schermi=HUB)
    c.regole = []
    c.user_text = detto
    c.storia = list(storia)
    return c


def chiama(args, chi, detto="", storia=(), tool="esercizi"):
    ctx = ctx_di(chi, detto=detto, storia=storia)
    return json.loads(TOOLS.call(tool, args, ctx, ctx.speaker_ctx.current_level)), ctx


def tentativi(persona):
    return len(REGISTRO.tentativi(persona))


print("── il numero non detto non si giudica ──")
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Teo")
s = SRV.sessione(TEO.id)
giusta = s.es.risposta
domanda = out["risposta_finale"]
storia = [("user", "facciamo le addizioni"), ("assistant", domanda)]
prima = tentativi(TEO.id)
out, ctx = chiama({"azione": "rispondi", "risposta": str(giusta)}, "Teo",
                  detto="Suttanto salida", storia=storia)
from calliope.esercizi.varianti import CATALOGO as VARIANTI  # noqa: E402
verifica("«Suttanto salida» passato come il numero giusto: non giudicato, si chiede di "
         "ripetere scandendo",
         out["risposta_finale"] in VARIANTI["numero.ripeti"]["normale"]
         and out.get("in_sospeso") and "giusta" not in out, out)
verifica("regola esercizi_numero_non_detto nel registro dei turni",
         "esercizi_numero_non_detto" in ctx.regole, ctx.regole)
verifica("nessun tentativo contato né scritto", s.errori == 0 and tentativi(TEO.id) == prima)
out, ctx = chiama({"azione": "rispondi", "risposta": str(giusta)}, "Teo",
                  detto=f"Fa {in_lettere(int(giusta))}.", storia=storia)
verifica("il numero detto in lettere: giudicato (giusta)", out.get("giusta") is True, out)
s = SRV.sessione(TEO.id)
domanda = out["risposta_finale"]
sbagliata = int(s.es.risposta) + 3
out, ctx = chiama({"azione": "rispondi", "risposta": str(sbagliata)}, "Teo",
                  detto=f"{int(s.es.risposta) - 2}, ah no, {sbagliata}",
                  storia=[("assistant", domanda)])
verifica("contrario: «X, ah no, Y» con Y passato: giudicato (sbagliata)",
         out.get("giusta") is False and "esercizi_numero_non_detto" not in ctx.regole, out)

print("── le domande le fa solo il programma ──")
s = SRV.sessione(TEO.id)
inventata = "Facciamo un gioco più divertente! Quanto fa 45 più 38?"
prima = tentativi(TEO.id)
errori_prima = s.errori
out, ctx = chiama({"azione": "rispondi", "risposta": "83"}, "Teo", detto="83",
                  storia=[("assistant", domanda), ("user", "rendili più giocosi"),
                          ("assistant", inventata)])
verifica("risposta a una domanda inventata: non giudicata, si torna alla domanda vera",
         "non l'ho preparata io" in out["risposta_finale"]
         and s.es.voce in out["risposta_finale"] and "giusta" not in out, out)
verifica("regola esercizi_domanda_non_sua; nessun tentativo",
         "esercizi_domanda_non_sua" in ctx.regole and tentativi(TEO.id) == prima
         and s.errori == errori_prima, ctx.regole)
for ultima in ("45 più 38?", "Quanto fa quarantacinque più trentotto?",
               "Brava! Adesso calcola 12 per 3, ce la fai?"):
    verifica(f"domanda inventata riconosciuta: «{ultima}»", SE.domanda_inventata(ultima))
for ultima in ("Brava, continua così!", "Vuoi un indizio?", "Ho 3 gatti e 2 cani.",
               "Facciamo una pausa o cambiamo?"):
    verifica(f"contrario, nessuna domanda d'esercizio: «{ultima}»",
             not SE.domanda_inventata(ultima))
out, ctx = chiama({"azione": "rispondi", "risposta": frazione_scritta(s.es.risposta)}, "Teo",
                  detto=frazione_scritta(s.es.risposta),
                  storia=[("assistant", "Quasi! " + s.es.voce)])
verifica("contrario: la domanda del programma (anche dopo altre parole) si giudica",
         out.get("giusta") is True, out)
out, ctx = chiama({"azione": "rispondi", "risposta": frazione_scritta(SRV.sessione(TEO.id).es.risposta)},
                  "Teo", detto=frazione_scritta(SRV.sessione(TEO.id).es.risposta),
                  storia=[("assistant", "Che bello sentirti così allegro!")])
verifica("contrario: una frase d'altro senza domanda non ferma il giudizio",
         out.get("giusta") is True, out)
chiama({"azione": "fine"}, "Teo")

# ─────────────────────────── blocchi e pausa ───────────────────────────
print("── blocchi e pausa ──")


def rispondi_giusta(chi, n=1):
    out = None
    for _ in range(n):
        s = SRV.sessione(PROFILI[chi].id)
        r = frazione_scritta(s.es.risposta)
        out, _ = chiama({"azione": "rispondi", "risposta": r}, chi)
    return out


PROFILI = {"Nina": NINA, "Teo": TEO}
verifica("blocco: 5 in terza elementare, 10 in quarta",
         SE.blocco_per(SE.Classe("elementari", 3), cfg) == 5
         and SE.blocco_per(SE.Classe("elementari", 4), cfg) == 10
         and SE.blocco_per(SE.Classe("medie", 1), cfg) == 10)
out, _ = chiama({"azione": "inizia", "argomento": "tabelline"}, "Nina")
out = rispondi_giusta("Nina", 4)
verifica("dopo 4 esercizi in terza: ancora la prossima domanda", "Prossima" in out["risposta_finale"])
out = rispondi_giusta("Nina", 1)
s = SRV.sessione(NINA.id)
verifica("al quinto: «Facciamo una pausa o cambiamo?» detto dal codice",
         out["risposta_finale"].endswith(SE.PAUSA_DOMANDA) and "Siamo a 5 esercizi" in
         out["risposta_finale"] and s.es is None and s.in_pausa, out["risposta_finale"])
verifica("la proposta resta in sospeso con il suo messaggio",
         out.get("in_sospeso", {}).get("messaggio") == SE.PAUSA_MSG)
out, ctx = chiama({"azione": "rispondi", "risposta": "12"}, "Nina", detto="12")
verifica("in pausa una risposta non si giudica", "Siamo in pausa" in out["risposta_finale"]
         and "giusta" not in out and "esercizi_in_pausa" in ctx.regole, out)
verifica("dato del turno: esercizi in pausa", "esercizi in pausa" in M.dato_turno(NINA))
out, ctx = chiama({"azione": "continua"}, "Nina")
verifica("continua: riprende con una domanda nuova", out["risposta_finale"].startswith("Riprendiamo.")
         and SRV.sessione(NINA.id).es is not None and out.get("in_sospeso"), out)
out, ctx = chiama({"azione": "pausa"}, "Nina")
s = SRV.sessione(NINA.id)
verifica("pausa a metà esercizio: l'esercizio resta, «continuiamo» per riprendere",
         "pausa" in out["risposta_finale"] and s.es is not None and s.in_pausa
         and "esercizi_pausa" in ctx.regole, out)
voce = s.es.voce
out, _ = chiama({"azione": "continua"}, "Nina")
verifica("continua dopo la pausa a metà: la stessa domanda", voce in out["risposta_finale"])
verifica("dato del turno: le domande le fa solo il programma",
         "le domande le fa solo il programma" in M.dato_turno(NINA))
chiama({"azione": "fine"}, "Nina")

# ─────────────────────────── preferenze, punti, tappe ───────────────────────────
print("── preferenze, punti e tappe ──")
out, ctx = chiama({"azione": "inizia", "argomento": "addizioni"}, "Teo")
out, ctx = chiama({"azione": "preferenze", "modo": "punti"}, "Teo")
s = SRV.sessione(TEO.id)
verifica("«facciamolo a punti»: frase del codice, salvata, e la domanda di nuovo",
         "a punti" in out["risposta_finale"] and "Me lo ricordo" in out["risposta_finale"]
         and s.es.voce in out["risposta_finale"] and REGISTRO.preferenze(TEO.id).get("punti")
         and "esercizi_preferenze" in ctx.regole, out)
out = rispondi_giusta("Teo")
verifica("giusta al primo colpo: più 2 punti", "Più 2 punti: sei a 2." in out["risposta_finale"],
         out["risposta_finale"])
s = SRV.sessione(TEO.id)
chiama({"azione": "rispondi", "risposta": str(int(s.es.risposta) + 1)}, "Teo")
out = rispondi_giusta("Teo")
verifica("giusta dopo un errore: più 1 punto", "Più 1 punto: sei a 3." in out["risposta_finale"],
         out["risposta_finale"])
verifica("scheda: i punti contati dal server", HUB.schede[-1][0].get("punti") == 3)
out, ctx = chiama({"modo": "tappe", "blocco": "più corti"}, "Teo")
verifica("azione omessa con modo e blocco: preferenze (azione dedotta)",
         "a tappe" in out["risposta_finale"] and "blocchi da 5" in out["risposta_finale"]
         and "esercizi_azione_dedotta" in ctx.regole, out)
s = SRV.sessione(TEO.id)
verifica("blocco più corto subito nella sessione", s.blocco == 5 and s.tappe_on)
for _ in range(10):
    out = rispondi_giusta("Teo")
    if SRV.sessione(TEO.id) is None or SRV.sessione(TEO.id).in_pausa:
        break
verifica("fine blocco a tappe: «Tappa 1 di 3 superata!» e i punti",
         "Tappa 1 di 3 superata!" in out["risposta_finale"] and "punti." in out["risposta_finale"]
         and out["risposta_finale"].endswith(SE.PAUSA_DOMANDA), out["risposta_finale"])
for tappa in (2, 3):
    chiama({"azione": "continua"}, "Teo")
    for _ in range(10):
        out = rispondi_giusta("Teo")
        s = SRV.sessione(TEO.id)
        if s is None or s.in_pausa:
            break
verifica("ultima tappa: percorso finito e il conto", "percorso finito" in out["risposta_finale"]
         and "Abbiamo finito" in out["risposta_finale"] and SRV.sessione(TEO.id) is None,
         out["risposta_finale"])

print("── la preferenza resta in una conversazione nuova ──")
SRV2 = SE.Servizio(cfg, Registro(cfg.memory_db), schermi=HUB, log=lambda *a: None, registry=REG)
SE.imposta(SRV2)
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Teo")
s = SRV2.sessione(TEO.id)
verifica("servizio nuovo (riavvio, conversazione nuova): punti, tappe e blocco ripresi",
         s.punti_on and s.tappe_on and s.blocco == 5 and "percorso a 3 tappe" in
         out["risposta_finale"], out["risposta_finale"])
out, _ = chiama({"azione": "preferenze", "modo": "giocoso"}, "Teo")
verifica("modo giocoso: la domanda come sfida, detta dal codice",
         "Sfida" in out["risposta_finale"] or "sfida" in out["risposta_finale"],
         out["risposta_finale"])
out, _ = chiama({"azione": "preferenze", "modo": "normale"}, "Teo")
s = SRV2.sessione(TEO.id)
verifica("modo normale: niente giochi né punti", not (s.giocoso or s.punti_on or s.tappe_on))
out, _ = chiama({"azione": "preferenze"}, "Teo")
verifica("contrario: preferenze senza come → errore con cosa_fare, niente «segno tutto»",
         out.get("ok") is False and "cosa_fare" in out, out)
verifica("contrario: le preferenze di Teo non sono di Nina", REGISTRO.preferenze(NINA.id) == {})
chiama({"azione": "fine"}, "Teo")
SE.imposta(SRV)

print("── conservazione delle preferenze ──")
db = sqlite3.connect(cfg.memory_db)
for chi, fa in (("vecchia-id", 61), ("sessanta-id", 60)):
    db.execute("INSERT INTO esercizi_preferenze (persona, dati, aggiornato) VALUES (?, '{}', ?)",
               (chi, (OGGI - datetime.timedelta(days=fa)).isoformat()))
db.commit()
db.close()
cons = C.Conservazione(cfg, REG, log=lambda m: None)
cons.ruota()
db = sqlite3.connect(cfg.memory_db)
chi = {r[0] for r in db.execute("SELECT persona FROM esercizi_preferenze")}
db.close()
verifica("rotazione: preferenze di 61 giorni via, di 60 restano",
         "vecchia-id" not in chi and "sessanta-id" in chi and TEO.id in chi, chi)
cons.svuota(TEO.id, "Teo")
verifica("svuota la persona: anche le sue preferenze", REGISTRO.preferenze(TEO.id) == {})

# ─────────────────────────── indizi vuoti ───────────────────────────
print("── «Un indizio:» mai vuoto ──")
out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Teo")
s = SRV.sessione(TEO.id)
s.es.suggerimenti = ["", "   "]
out, _ = chiama({"azione": "rispondi", "risposta": str(int(s.es.risposta) + 1)}, "Teo")
verifica("sbagliata con indizi vuoti: niente «Un indizio:»",
         "indizio" not in out["risposta_finale"].lower(), out["risposta_finale"])
out, _ = chiama({"azione": "aiuto"}, "Teo")
verifica("aiuto con indizi vuoti: «Gli indizi sono finiti»",
         "Gli indizi sono finiti" in out["risposta_finale"], out["risposta_finale"])

# ─────────────────────────── schermo_mostra ───────────────────────────
print("── schermo_mostra: testo ed esercizio ──")
out, ctx = chiama({"cosa": "ultima"}, "Teo", tool="schermo_mostra")
card = HUB.schede[-1][0]
verifica("con gli esercizi aperti «scrivimelo sullo schermo»: la scheda dell'esercizio",
         card["tipo"] == "esercizio" and card.get("domanda") == s.es.testo
         and "schermo_esercizio" in ctx.regole, card.get("tipo"))
chiama({"azione": "fine"}, "Teo")
testo = "Un negozio ha 150 scatole e ne vende 65. Quante ne restano?"
out, ctx = chiama({"cosa": "testo", "testo": testo}, "Teo", tool="schermo_mostra")
card = HUB.schede[-1][0]
verifica("cosa=testo: il testo scelto sullo schermo", card["tipo"] == "testo"
         and testo in json.dumps(card, ensure_ascii=False) and out.get("ok") is not False, out)
out, ctx = chiama({"cosa": "ultima", "testo": testo}, "Teo", tool="schermo_mostra")
verifica("testo con cosa=ultima: vale testo (regola schermo_testo_dedotto)",
         "schermo_testo_dedotto" in ctx.regole and HUB.schede[-1][0]["tipo"] == "testo")
out, _ = chiama({"cosa": "testo"}, "Teo", tool="schermo_mostra")
verifica("contrario: cosa=testo senza testo → chiede cosa scrivere", out.get("ok") is False
         and "cosa vuoi che scriva" in out["risposta_finale"], out)
out, _ = chiama({"cosa": "esercizio"}, "Teo", tool="schermo_mostra")
verifica("contrario: cosa=esercizio senza esercizi aperti", out.get("ok") is False, out)

# ─────────────────────────── Brain ───────────────────────────
print("── Brain: domande inventate, promesse, «scrivo qui» ──")
from calliope.brain import Brain  # noqa: E402


class BackendFinto:
    def __init__(self, copione):
        self.copione, self.visti = list(copione), []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from (self.copione.pop(0) if self.copione else [("text", "Va bene.")])


def brain_finto(copione, chi, how="voce"):
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, TOOLS, []
    b.tool_ctx = ctx_di(chi, how)
    b.backend = BackendFinto(copione)
    b.turn_number = 0
    return b


out, _ = chiama({"azione": "inizia", "argomento": "addizioni"}, "Teo")
s = SRV.sessione(TEO.id)
voce = s.es.voce
b = brain_finto([[("text", "Che bello giocare!")],
                 [("text", "Ecco una sfida: quanto fa 125 più 87?")]], "Teo")
b.set_pending(out["in_sospeso"])
detto = "".join(b.stream_reply("rendili più giocosi", "familiare"))
verifica("domanda inventata dopo la spinta: non si dice, al suo posto quella del programma",
         "125" not in detto and voce in detto, detto)
verifica("regole spinta_esercizi ed esercizi_domanda_inventata",
         {"spinta_esercizi", "esercizi_domanda_inventata"} <= set(b.rules_fired()),
         b.rules_fired())
b = brain_finto([[("text", "Va bene, più giochi!")], [("text", "Ricevuto. Segno tutto.")]], "Teo")
b.set_pending(out["in_sospeso"])
detto = "".join(b.stream_reply("voglio blocchi più corti e più giocosi", "familiare"))
verifica("«Segno tutto» senza tool dopo la spinta: non si dice",
         "Segno tutto" not in detto and detto == SE.PROMESSA_FRASE
         and "esercizi_promessa_taciuta" in b.rules_fired(), detto)
b = brain_finto([[("text", "Che bello!")], [("text", "Sono contenta che ti piaccia.")]], "Teo")
b.set_pending(out["in_sospeso"])
detto = "".join(b.stream_reply("mi piacciono le addizioni", "familiare"))
verifica("contrario: una frase d'altro dopo la spinta si dice",
         detto == "Sono contenta che ti piaccia.", detto)
b = brain_finto([[("text", "Allora, quanto fa 2 più 2?")],
                 [("text", "Facciamo così: quanto fa 3 più 3?")]], "Teo")
detto = "".join(b.stream_reply("dai, un altro", "familiare"))
verifica("sessione aperta senza l'azione in sospeso: spinta e domanda vera",
         "spinta_esercizi" in b.rules_fired() and voce in detto and "3 più 3" not in detto,
         detto)
chiama({"azione": "fine"}, "Teo")

testo = "Certo! Te lo scrivo qui nella conversazione. Un negozio ha 150 scatole."
b = brain_finto([[("text", testo)]], "Teo")
detto = "".join(b.stream_reply("scrivimelo", "familiare"))
verifica("«te lo scrivo qui» a voce: la frase si toglie, il resto si dice",
         "scrivo" not in detto and "150 scatole" in detto and "scrivo_qui_tolto"
         in b.rules_fired(), detto)
b = brain_finto([[("text", testo)]], "Teo", how="schermo")
detto = "".join(b.stream_reply("scrivimelo", "familiare"))
verifica("contrario: a chi scrive dallo schermo resta", "scrivo qui" in detto, detto)
b = brain_finto([[("text", "Scrivo la lista della spesa sul quaderno. Fatto.")]], "Teo")
detto = "".join(b.stream_reply("cosa fai?", "familiare"))
verifica("contrario: «scrivo» senza «qui» resta", "Scrivo la lista" in detto, detto)

print()
print("ESITO: " + ("tutto ok" if not errori else f"{errori} errori"))
sys.exit(1 if errori else 0)
