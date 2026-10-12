"""
Prova a secco delle materie calcolabili (12/10/2026, S1 della roadmap: logica, fisica e chimica
con lo stesso schema della matematica; calliope/esercizi/{logica,fisica,chimica,misure}.py,
calliope/unita.py). Niente modelli, niente Ollama.

- unità di misura lette dalle risposte come le scrive Whisper (simboli, nomi interi o
  storpiati, numeri in lettere, decimali detti, «un chilo e mezzo», «mezz'ora») e i contrari
  («secondo me», «ora» prima del numero, simboli senza numero, nessun numero);
- numeri: decimali detti con gli zeri («zero virgola zero cinque»), «2 virgola 5», migliaia
  col punto («1.000») e i contrari («0.125», «2.5»);
- unità dette: plurale accordato, virgola decimale, nessun simbolo nella voce;
- generatori di logica, fisica e chimica: 300 semi per argomento e livello, ricalcolo
  indipendente che torna, risposta giusta accettata scritta, detta, in lettere con
  un'unità storpiata, senza unità (con il promemoria), in un'unità equivalente (non nelle
  conversioni), sbagliata rifiutata, unità di un'altra grandezza rifiutata;
- ricalcolo che **prende** gli errori: massa molare con la composizione sbagliata, reazione
  non bilanciata o non minima, sequenza ambigua, insiemi e vero o falso con la risposta
  rovesciata;
- vero o falso letto dalla frase («è vera», «non è vero», «non è falsa»; contrari: tutti e
  due, nessuno, «sì»);
- flusso dal tool: fisica con la scheda «misura», «logica» come argomento è la materia (non
  l'analisi logica), «analisi logica» resta italiano, chimica con la segnalazione ricalcolata,
  indizio con «l'unità di misura», argomenti che elencano le cinque materie.
"""

import json
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope import esercizi as E  # noqa: E402
from calliope import minori as M  # noqa: E402
from calliope import unita as U  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.esercizi import chimica as CH  # noqa: E402
from calliope.esercizi import fisica as FI  # noqa: E402
from calliope.esercizi import logica as LO  # noqa: E402
from calliope.esercizi import sessione as SE  # noqa: E402
from calliope.esercizi.numeri import in_lettere, leggi_valore  # noqa: E402
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


F = Fraction

# ─────────────────────────── numeri ───────────────────────────
print("── numeri: decimali e migliaia ──")
for testo, attesa in (("zero virgola zero cinque", F(1, 20)), ("due virgola cinque", F(5, 2)),
                      ("2 virgola 5", F(5, 2)), ("zero virgola novantadue", F(23, 25)),
                      ("centodiciassette virgola sei", F(588, 5)), ("1.000", 1000),
                      ("12.500", 12500), ("0.125", F(1, 8)), ("2.5", F(5, 2)),
                      ("uno virgola cinque", F(3, 2)), ("tre virgola zero zero uno",
                                                        F(3001, 1000))):
    v = leggi_valore(testo)
    verifica(f"«{testo}» → {attesa}", v == F(attesa), str(v))

# ─────────────────────────── unità lette ───────────────────────────
print("── unità di misura lette dalle risposte ──")
CASI = (
    ("2,5 m/s", F(5, 2), "m/s"), ("due virgola cinque metri al secondo", F(5, 2), "m/s"),
    ("Fa 10 metri al secondo.", 10, "m/s"), ("5m/s", 5, "m/s"),
    ("dieci metri al secondi", 10, "m/s"), ("36 chilometri orari", 36, "km/h"),
    ("trentasei chilometri allora", 36, "km/h"), ("36 km all'ora", 36, "km/h"),
    ("settantadue km/h", 72, "km/h"), ("un chilo e mezzo", F(3, 2), "kg"),
    ("tre kilogrammi", 3, "kg"), ("diciotto grammi per mole", 18, "g/mol"),
    ("18 grammi alla mole", 18, "g/mol"), ("18 g/mol", 18, "g/mol"),
    ("zero virgola zero cinque moli", F(1, 20), "mol"), ("0,5 molare", F(1, 2), "mol/L"),
    ("mezza mole al litro", F(1, 2), "mol/L"),
    ("9,8 m/s²", F(49, 5), "m/s²"), ("2 metri al secondo al quadrato", 2, "m/s²"),
    ("117,6 newton", F(588, 5), "N"), ("centodiciassette virgola sei niuton", F(588, 5), "N"),
    ("2,7 g/cm3", F(27, 10), "g/cm³"), ("2 virgola 7 grammi al centimetro cubo", F(27, 10),
                                         "g/cm³"),
    ("2700 chilogrammi al metro cubo", 2700, "kg/m³"), ("1.000 kg/m³", 1000, "kg/m³"),
    ("un'ora e mezza", F(3, 2), "h"), ("mezz'ora", F(1, 2), "h"), ("2 ore e mezza", F(5, 2), "h"),
    ("novanta minuti", 90, "min"), ("cento giul", 100, "J"), ("250 joule", 250, "J"),
    ("50 watt", 50, "W"), ("40 centimetri cubi", 40, "cm³"), ("0,5 litri", F(1, 2), "L"),
    ("la velocità è di 12 m/s", 12, "m/s"), ("Credo 3 ore", 3, "h"),
    ("5, secondo me", 5, None), ("Secondo me 5", 5, None), ("venti", 20, None),
    ("ora fa 20 metri", 20, "m"),
)
for testo, valore, unita in CASI:
    m = U.leggi_misura(testo)
    ok = m is not None and m.valore == F(valore) and m.unita == unita
    verifica(f"«{testo}» → {valore} {unita}", ok, str(m))
for testo in ("non lo so", "metri al secondo", "", "boh, chilogrammi"):
    verifica(f"contrario: «{testo}» senza numero → niente", U.leggi_misura(testo) is None,
             str(U.leggi_misura(testo)))
# «s», «m», «g» da soli valgono solo subito dopo un numero
verifica("contrario: «g» senza numero davanti non è un'unità",
         U.trova_unita(U._prepara("la g di gatto")) == [])
verifica("contrario: «secondo me» non è un'unità",
         not U.trova_unita(U._prepara("5 secondo me")))
verifica("contrario: il numero dopo un'altra parola non prende l'unità lontana",
         U.leggi_misura("5 perché sono metri").unita is None)

# ─────────────────────────── unità dette ───────────────────────────
print("── unità dette ──")
for v, u, attesa in ((F(5, 2), "m/s", "2,5 metri al secondo"), (1, "kg", "1 chilogrammo"),
                     (-3, "m/s", "meno 3 metri al secondo"), (F(1, 20), "mol", "0,05 moli"),
                     (F(49, 5), "m/s²", "9,8 metri al secondo quadrato"),
                     (1, "mol/L", "1 mole al litro"), (36, "km/h", "36 chilometri all'ora"),
                     (F(1, 2), "h", "0,5 ore")):
    verifica(f"detta: {v} {u} → «{attesa}»", U.misura_detta(v, u) == attesa,
             U.misura_detta(v, u))
verifica("scritta: «2,5 m/s»", U.misura_scritta(F(5, 2), "m/s") == "2,5 m/s")
verifica("conversione esatta: 36 km/h = 10 m/s", U.converti(36, "km/h", "m/s") == 10)
verifica("conversione: 2,7 g/cm³ = 2700 kg/m³", U.converti(F(27, 10), "g/cm³", "kg/m³") == 2700)
try:
    U.converti(1, "kg", "m")
    verifica("contrario: chilogrammi in metri non si convertono", False)
except ValueError:
    verifica("contrario: chilogrammi in metri non si convertono", True)
verifica("ogni unità ha un nome singolare e plurale e una grandezza con nome",
         all(u.singolare and u.plurale and u.grandezza in U.NOMI_GRANDEZZE
             for u in U.UNITA.values()))


# ─────────────────────────── generatori ───────────────────────────
def in_lettere_decimale(v: Fraction) -> str:
    """Come lo trascriverebbe Whisper se il ragazzo dice il numero in lettere."""
    segno = "meno " if v < 0 else ""
    v = abs(v)
    intero = int(v)
    s = segno + in_lettere(intero)
    resto = v - intero
    if resto:
        d = U.decimali(resto)
        cifre = str(int(resto * 10**d)).rjust(d, "0")
        zeri = len(cifre) - len(cifre.lstrip("0"))
        s += " virgola " + " ".join(["zero"] * zeri) + (" " if zeri else "") + \
            in_lettere(int(cifre.lstrip("0")))
    return s


ALTRA_GRANDEZZA = {U.MASSA: "m", U.LUNGHEZZA: "kg"}
EQUIVALENTE = {"m/s": ("km/h", F(18, 5)), "km/h": ("m/s", F(5, 18)), "g": ("kg", F(1, 1000)),
               "kg": ("g", F(1000)), "h": ("min", F(60)), "km": ("m", F(1000)),
               "cm³": ("mL", F(1)), "g/cm³": ("kg/m³", F(1000)), "kg/m³": ("g/cm³", F(1, 1000)),
               "J": ("kJ", F(1, 1000)), "W": ("kW", F(1, 1000))}
SIMBOLI_VOCE = ("/", "²", "³", "₂", "₃", "₄", "=", "→", "{", "}", "°", "·", " m/s", " kg ", "²")

print("── generatori: fisica, chimica, logica ──")
for mod in (FI, CH, LO):
    for arg in mod.GENERATORI:
        for L in (1, 2, 3):
            rotti, voce_male, problemi = [], [], {}
            visti = set()

            def nota(chiave, cosa):
                problemi.setdefault(chiave, []).append(cosa)
            for seme in range(300):
                try:
                    es = mod.genera(arg, L, seme)
                except ValueError as e:
                    rotti.append(str(e))
                    continue
                visti.add(es.testo)
                if not mod.verifica(es):
                    rotti.append(seme)
                if any(s in es.voce for s in SIMBOLI_VOCE):
                    voce_male.append(es.voce)
                ok = lambda r: E.controlla(es, r).giusta is True  # noqa: E731
                no = lambda r: E.controlla(es, r).giusta is False  # noqa: E731
                if es.tipo == "misura":
                    u, r = es.dati["unita"], es.risposta
                    if not ok(U.misura_scritta(r, u)):
                        nota("scritta", U.misura_scritta(r, u))
                    if not ok(es.risposta_detta):
                        nota("detta", es.risposta_detta)
                    alias = U.UNITA[u].alias
                    lettere = f"Fa {in_lettere_decimale(r)} {alias[-1] if alias else u}."
                    if not ok(lettere):
                        nota("lettere", lettere)
                    e = E.controlla(es, U.numero_scritto(r))
                    if not (e.giusta is True and "unità" in e.nota):
                        nota("senza unità", (U.numero_scritto(r), e))
                    if not no(U.misura_scritta(r + 1, u)):
                        nota("+1", U.misura_scritta(r + 1, u))
                    altra = ALTRA_GRANDEZZA.get(U.UNITA[u].grandezza, "kg")
                    if altra not in es.dati.get("tollerate", ()) and not no(
                            U.misura_scritta(r, altra)):
                        nota("altra grandezza", U.misura_scritta(r, altra))
                    if u in EQUIVALENTE:
                        u2, k = EQUIVALENTE[u]
                        e = E.controlla(es, U.misura_scritta(r * k, u2))
                        atteso = (e.giusta is False and e.conta is False) if \
                            es.dati.get("obbligatoria") else e.giusta is True
                        if not atteso:
                            nota("equivalente", (U.misura_scritta(r * k, u2), e))
                elif es.tipo == "scelta":
                    if not ok(es.risposta) or not ok(f"È {es.risposta[:-1]}a."):
                        nota("scelta", es.risposta)
                    altra = "falso" if es.risposta == "vero" else "vero"
                    if not no(altra):
                        nota("scelta sbagliata", altra)
                else:
                    r = es.risposta
                    if not ok(str(r)) or not ok(in_lettere(int(r))):
                        nota("valore", r)
                    if not no(str(r + 1)):
                        nota("+1", r + 1)
            nome = f"{mod.MATERIA}/{arg} livello {L}"
            verifica(f"{nome}: 300 semi, ricalcolo che torna", not rotti, str(rotti[:3]))
            verifica(f"{nome}: voce senza simboli", not voce_male, str(voce_male[:2]))
            verifica(f"{nome}: risposte giuste accettate e sbagliate rifiutate (in tutte le "
                     f"forme)", not problemi,
                     str({k: v[:2] for k, v in problemi.items()}))
            verifica(f"{nome}: esercizi diversi ({len(visti)})", len(visti) >= 5, len(visti))

# ─────────────────────────── correzioni con le unità ───────────────────────────
print("── correzione con le unità ──")
es = next(e for e in (FI.genera("velocita", 3, s) for s in range(300))
          if e.dati.get("obbligatoria") and e.dati["unita"] == "m/s")
kmh = es.risposta * F(18, 5)
e = E.controlla(es, U.misura_scritta(kmh, "km/h"))
verifica("conversione: rispondere con il valore di partenza non vale e non conta",
         e.giusta is False and e.conta is False and "metri al secondo" in e.nota, e)
es = FI.genera("velocita", 1, 4)
e = E.controlla(es, U.misura_scritta(es.risposta, "kg"))
verifica("numero giusto ma unità di un'altra grandezza: non giusta, non conta, lo dice",
         e.giusta is False and e.conta is False and "una velocità" in e.nota, e)
e = E.controlla(es, U.misura_scritta(es.risposta * 10, "m/s"))
verifica("virgola spostata: «controlla la virgola»", e.giusta is False and "virgola" in e.nota, e)
e = E.controlla(es, "metri al secondo")
verifica("solo l'unità, senza numero: non capita, non conta", e.giusta is None and not e.conta)
es = CH.genera("massa_molare", 1, 0)
e = E.controlla(es, U.misura_scritta(es.risposta, "g"))
verifica("massa molare detta in grammi: giusta, con la forma corretta",
         e.giusta is True and "grammi per mole" in e.nota, e)
es = CH.genera("bilanciamento", 1, 3)
e = E.controlla(es, "tre e mezzo")
verifica("bilanciamento: un coefficiente con la virgola è sbagliato e lo dice",
         e.giusta is False and "intero" in e.nota, e)

# ─────────────────────────── il ricalcolo prende gli errori ───────────────────────────
print("── ricalcolo che prende gli errori ──")
es = CH.genera("massa_molare", 2, 1)
es.risposta = es.risposta + 1
verifica("massa molare sbagliata → il ricalcolo dalla formula non torna", not CH.verifica(es))
vecchi = CH.COMPOSTI
try:
    CH.COMPOSTI = tuple((f, d, L, dict(c, O=c.get("O", 0) + 1) if f == "H2O" else c)
                        for f, d, L, c in vecchi)
    rotti = 0
    for s in range(200):
        try:
            CH.genera("massa_molare", 1, s)
        except ValueError:
            rotti += 1
    verifica("composizione scritta male (H2O con 2 ossigeni) → quegli esercizi non nascono",
             rotti > 0, rotti)
finally:
    CH.COMPOSTI = vecchi
es = CH.genera("bilanciamento", 2, 5)
es.dati["prodotti"] = [[c + 1, f] for c, f in es.dati["prodotti"]]
verifica("reazione non bilanciata → il ricalcolo non torna", not CH.verifica(es))
es = CH.genera("bilanciamento", 1, 2)
es.dati["reagenti"] = [[c * 2, f] for c, f in es.dati["reagenti"]]
es.dati["prodotti"] = [[c * 2, f] for c, f in es.dati["prodotti"]]
es.risposta = es.risposta * 2
verifica("coefficienti non minimi (tutti doppi) → il ricalcolo non torna", not CH.verifica(es))
verifica("atomi letti dalla formula: H2SO4", CH.atomi("H2SO4") == {"H": 2, "S": 1, "O": 4})
verifica("massa molare dalla formula: NaCl = 58,5", CH.massa_molare("NaCl") == F(117, 2))
for cattiva in ("h2o", "H2O)", "", "2H2O"):
    try:
        CH.atomi(cattiva)
        verifica(f"contrario: «{cattiva}» non è una formula", False)
    except ValueError:
        verifica(f"contrario: «{cattiva}» non è una formula", True)
verifica("formula detta: «acca 2 esse o 4»", CH.formula_detta("H2SO4") == "acca 2 esse o 4",
         CH.formula_detta("H2SO4"))
verifica("formula detta: NaCl lettera per lettera", CH.formula_detta("NaCl") == "enne a ci elle")
verifica("formula scritta con i pedici", CH.formula_scritta("C6H12O6") == "C₆H₁₂O₆")
verifica("ogni composto: composizione scritta uguale alla formula letta",
         all(CH.atomi(f) == c for f, _, _, c in CH.COMPOSTI))
es = FI.genera("densita", 2, 3)
es.risposta = es.risposta * 2
verifica("fisica: risposta raddoppiata → il ricalcolo non torna", not FI.verifica(es))
verifica("sequenza ambigua (1, 2, 4: raddoppio o +1, +2) → più continuazioni",
         len(LO._prossimi([1, 2, 4])) > 1, LO._prossimi([1, 2, 4]))
verifica("sequenza aritmetica: una sola continuazione", LO._prossimi([3, 7, 11, 15, 19]) == {23})
verifica("Fibonacci: una sola continuazione", LO._prossimi([2, 3, 5, 8, 13]) == {21},
         LO._prossimi([2, 3, 5, 8, 13]))
es = LO.genera("sequenze", 2, 7)
es.risposta = es.risposta + 1
verifica("sequenza con la risposta sbagliata → il ricalcolo non torna", not LO.verifica(es))
for arg in ("insiemi", "vero_falso"):
    for L in (1, 2, 3):
        es = LO.genera(arg, L, 11)
        es.risposta = ("falso" if es.risposta == "vero" else "vero") if es.tipo == "scelta" \
            else es.risposta + 1
        verifica(f"{arg} livello {L}: risposta rovesciata → il ricalcolo non torna",
                 not LO.verifica(es))
verifica("«o» mai con tutte e due le parti vere (ambiguo)", all(
    not (e.dati["valori"]["A"] and e.dati["valori"]["B"])
    for e in (LO.genera("vero_falso", 1, s) for s in range(300)) if e.dati["formula"] == "A or B"))

# ─────────────────────────── vero o falso letto ───────────────────────────
print("── vero o falso letto dalla frase ──")
for testo, attesa in (("Vero.", "vero"), ("È vera!", "vero"), ("falso", "falso"),
                      ("Secondo me è falsa.", "falso"), ("non è vero", "falso"),
                      ("Non è falsa.", "vero"), ("È vero, credo", "vero")):
    verifica(f"«{testo}» → {attesa}", LO.leggi_vero_falso(testo) == attesa,
             LO.leggi_vero_falso(testo))
for testo in ("vero o falso?", "sì", "no", "non lo so", "vero... no, falso", ""):
    verifica(f"contrario: «{testo}» → non capita", LO.leggi_vero_falso(testo) is None,
             LO.leggi_vero_falso(testo))

# ─────────────────────────── scelta della materia dal testo ───────────────────────────
print("── materia e argomento dal testo ──")
for testo, attesa in (("logica", "logica"), ("la fisica", "fisica"), ("chimica", "chimica"),
                      ("esercizi di logica", "logica"), ("analisi logica", None),
                      ("le frazioni", None)):
    verifica(f"solo materia: «{testo}» → {attesa}", E.solo_materia(testo) == attesa,
             E.solo_materia(testo))
for testo, materia, attesa in (("densità", None, "densita"), ("velocità", "fisica", "velocita"),
                               ("le moli", "chimica", "moli"),
                               ("bilanciare le reazioni", None, "bilanciamento"),
                               ("massa molare", None, "massa_molare"),
                               ("sequenze", None, "sequenze"),
                               ("moltiplicare", None, None),
                               ("le moltiplicazioni", None, "moltiplicazioni"),
                               ("analisi logica", None, "analisi_logica"),
                               ("insiemi", "logica", "insiemi"),
                               ("vero o falso", None, "vero_falso")):
    verifica(f"argomento: «{testo}» ({materia}) → {attesa}",
             E.argomento_da_testo(testo, materia) == attesa,
             E.argomento_da_testo(testo, materia))
verifica("materia: «analisi logica» resta italiano", E.materia_da_testo("analisi logica") ==
         "italiano")

# ─────────────────────────── flusso dal tool ───────────────────────────
print("── flusso dal tool ──")
TMP = Path(tempfile.mkdtemp(prefix="calliope-materie-"))
cfg = Config()
cfg.memory_db = str(TMP / "memoria.db")
cfg.esercizi_pronti = 0


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
    import datetime
    nascita = None
    if anni is not None:
        d = datetime.date.today() - datetime.timedelta(days=30)
        nascita = d.replace(year=d.year - anni).isoformat()
    pr = UserProfile(nome, admin=admin, gender=gender, nascita=nascita, tutori=list(tutori or []))
    pr.id = nome.lower() + "-id"
    return pr


DARIO = profilo("Dario", admin=True, gender="m")
SARA = profilo("Sara", 16, tutori=["dario-id"])
LUCA = profilo("Luca", 12, tutori=["dario-id"], gender="m")
REG = Reg([DARIO, SARA, LUCA])


class HubFinto:
    def __init__(self):
        self.schede = []

    def invia(self, scheda, mittente, forza=False):
        self.schede.append((scheda, mittente))
        return {"schermi": ["camera"], "motivo": ""}

    def mittente(self, ctx):
        from calliope.schermi.hub import mittente_da
        return mittente_da(ctx)


HUB = HubFinto()
M.prepara(cfg, schermi=HUB, registry=REG, log=lambda *a: None)
SRV = SE.Servizio(cfg, Registro(cfg.memory_db), schermi=HUB, log=lambda *a: None, registry=REG)
SE.imposta(SRV)
TOOLS = build_registry(minori_tool=True)
from calliope.tools.minori import minori_specs  # noqa: E402

for spec in minori_specs():
    TOOLS.register(spec)


def chiama(args, chi):
    sc = SpeakerContext(REG)
    sc.current_speaker, sc.identified_by = chi, "voce"
    ctx = ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None, schermi=HUB)
    ctx.regole = []
    return json.loads(TOOLS.call("esercizi", args, ctx, sc.current_level)), ctx


def ultima_scheda():
    return next((s for s, _ in reversed(HUB.schede) if s["tipo"] == "esercizio"), None)


out, _ = chiama({"azione": "inizia", "materia": "fisica", "argomento": "densità"}, "Sara")
s = SRV.sessione(SARA.id)
verifica("fisica, densità: prima domanda", s is not None and s.materia == "fisica"
         and s.argomento == "densita" and "Prima domanda" in out.get("risposta_finale", ""), out)
verifica("voce della domanda senza simboli", not any(x in out["risposta_finale"]
                                                     for x in ("/", "³", "²")),
         out["risposta_finale"])
sc = ultima_scheda()
verifica("scheda: campo «misura», domanda con i simboli, nessuna risposta",
         sc["campo"] == "misura" and sc["domanda"] == s.es.testo
         and "risposta" not in sc and s.es.spiegazione not in json.dumps(sc, ensure_ascii=False),
         sc)
verifica("in sospeso con il messaggio degli esercizi",
         out.get("in_sospeso", {}).get("tool") == "esercizi")
prima = s.es.firma
out, ctx = chiama({"azione": "rispondi", "risposta": "Fa " + s.es.risposta_detta + "."}, "Sara")
verifica("risposta detta con l'unità → giusta, prossima", out.get("giusta") is True
         and SRV.sessione(SARA.id).es.firma != prima, out)
verifica("regola: corretta dal codice", "esercizi_corretto_dal_codice" in ctx.regole)
s = SRV.sessione(SARA.id)
out, _ = chiama({"azione": "rispondi", "risposta": U.misura_scritta(s.es.risposta + 3,
                                                                     s.es.dati["unita"])},
                "Sara")
verifica("sbagliata → «Non ancora», riprova con l'unità di misura",
         out.get("giusta") is False and "unità di misura" in out["risposta_finale"], out)
out, _ = chiama({"azione": "aiuto"}, "Sara")
verifica("aiuto → indizio e «con l'unità di misura?»",
         "Un indizio" in out["risposta_finale"] and out["risposta_finale"].endswith(
             "con l'unità di misura?"), out["risposta_finale"])
out, ctx = chiama({"azione": "segnala", "nota": "secondo me è sbagliato"}, "Sara")
verifica("segnala: ricalcolo con un altro conto, mi torna",
         "con un altro conto" in out["risposta_finale"]
         and "esercizi_segnalato_confermato" in ctx.regole, out)
out, _ = chiama({"azione": "fine"}, "Sara")
verifica("fine: il conto", "Abbiamo finito" in out["risposta_finale"], out)

out, _ = chiama({"azione": "inizia", "argomento": "logica"}, "Luca")
verifica("«logica» come argomento è la materia: chiede l'argomento di logica",
         "logica" in out["risposta_finale"] and "sequenze" in out["risposta_finale"]
         and SRV.sessione(LUCA.id) is None, out["risposta_finale"])
out, _ = chiama({"azione": "inizia", "materia": "logica", "argomento": "logica"}, "Luca")
verifica("materia logica e argomento «logica»: non diventa analisi logica",
         SRV.sessione(LUCA.id) is None and "sequenze" in out["risposta_finale"], out)
verifica("contrario: materia italiano e «analisi logica» restano l'analisi logica",
         E.argomento_da_testo("analisi logica", E.materia_da_testo("italiano"))
         == "analisi_logica" and E.solo_materia("analisi logica") is None)
out, _ = chiama({"azione": "inizia", "materia": "logica", "argomento": "vero o falso"}, "Luca")
s = SRV.sessione(LUCA.id)
verifica("logica, vero o falso: scelte sulla scheda", s is not None
         and ultima_scheda()["scelte"] == ["vero", "falso"], out)
out, _ = chiama({"azione": "rispondi", "risposta": "Forse."}, "Luca")
verifica("vero o falso: «Forse.» non capita, non conta", s.errori == 0
         and "vero" in out["risposta_finale"], out)
out, _ = chiama({"azione": "rispondi", "risposta": f"È {s.es.risposta}."}, "Luca")
verifica("vero o falso: giusta detta in una frase", out.get("giusta") is True, out)
out, _ = chiama({"azione": "inizia", "materia": "chimica", "argomento": "bilanciamento"},
                "Luca")
s = SRV.sessione(LUCA.id)
verifica("chimica, bilanciamento (12 anni: livello più basso)", s is not None
         and s.argomento == "bilanciamento" and s.livello == 1, out)
verifica("bilanciamento: scheda con il campo dei numeri", ultima_scheda()["campo"] == "numero")
out, _ = chiama({"azione": "rispondi", "risposta": in_lettere(int(s.es.risposta))}, "Luca")
verifica("bilanciamento: coefficiente in lettere → giusta", out.get("giusta") is True, out)
# Senza azione (banco del 12/10: il modello la ometteva accanto a materia, argomento e
# risposta, e ogni risposta ricominciava da un esercizio nuovo)
s = SRV.sessione(LUCA.id)
prima, sid = s.es.firma, s.id
out, ctx = chiama({"materia": "chimica", "argomento": "bilanciamento",
                   "risposta": str(s.es.risposta + 5)}, "Luca")
s2 = SRV.sessione(LUCA.id)
verifica("senza azione, con la risposta e la sessione aperta → rispondi (stessa sessione)",
         s2 is not None and s2.id == sid and s2.es.firma == prima and s2.errori == 1
         and "esercizi_azione_dedotta" in ctx.regole and out.get("giusta") is False, out)
out, ctx = chiama({"materia": "chimica", "argomento": "bilanciamento"}, "Luca")
verifica("senza azione né risposta, stesso argomento → ripeti la domanda",
         SRV.sessione(LUCA.id).id == sid and out["risposta_finale"] == s2.es.voce
         and "esercizi_azione_dedotta" in ctx.regole, out)
out, ctx = chiama({"materia": "fisica", "argomento": "velocità"}, "Luca")
verifica("contrario: senza azione con un'altra materia → inizia (sessione nuova)",
         SRV.sessione(LUCA.id) is not None and SRV.sessione(LUCA.id).id != sid
         and SRV.sessione(LUCA.id).materia == "fisica"
         and "esercizi_azione_dedotta" not in ctx.regole, out)
chiama({"azione": "fine"}, "Luca")
out, ctx = chiama({"classe": "seconda media"}, "Luca")
verifica("contrario: senza azione e senza sessione → inizia (chiede la materia)",
         "materia" in out["risposta_finale"] and "esercizi_azione_dedotta" not in ctx.regole,
         out)
out, _ = chiama({"azione": "argomenti"}, "Dario")
verifica("argomenti a un tutore: le cinque materie", all(m in out["risposta_finale"]
                                                       for m in E.MATERIE),
         out["risposta_finale"])
out, _ = chiama({"azione": "argomenti"}, "Luca")
verifica("argomenti a 12 anni: niente chimica (dalla terza media)",
         "chimica" not in out["risposta_finale"] and "fisica" in out["risposta_finale"],
         out["risposta_finale"])
out, _ = chiama({"azione": "inizia"}, "Luca")
verifica("senza materia: «Di che materia?» con le cinque", all(
    m in out["risposta_finale"] for m in E.MATERIE), out["risposta_finale"])

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
