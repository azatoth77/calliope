"""
Prova a secco degli esercizi (08/10/2026, calliope/esercizi/, docs/ricerche/
2026-10-08-esercizi.md): niente modelli, niente Ollama; il secondo parere è finto.

- numeri detti e scritti («tre quarti», «meno due», «x uguale 4», «uno virgola cinque») e i
  contrari (nessun numero, «sei» da solo non è un esercizio di frazioni);
- generatori di matematica: migliaia di semi per argomento e livello, ricalcolo indipendente
  che torna, risposta giusta accettata in cifre e in lettere, sbagliata rifiutata, voce senza
  simboli, frazione da semplificare ancora (non conta come errore);
- generatori d'italiano: risposte giuste e sinonimi («sostantivo»), sbagliate, analisi logica
  con «il soggetto è…», articolo facoltativo, parole d'altri gruppi rifiutate; lessico sul
  Wikizionario (se c'è il file della biblioteca);
- verifica linguistica: secondo parere che concorda (buono), che non concorda (scartato),
  guasto (non verificato, niente esercizi senza `esercizi_senza_secondo_parere`), banco che
  evita di richiedere;
- flusso: inizio con la classe dall'età, scheda personale senza risposta né spiegazione,
  azione in sospeso con la domanda, giusta e prossima, sbagliata con indizio, 5 errori →
  spiegazione e avviso ai tutori una volta sola, aiuto che non conta, salta senza soluzione,
  soluzione negata ai bambini e data a un adulto, segnalazione (ricalcolo, italiano scartato),
  livello che sale e scende, fine con il conto, registro dei tentativi;
- permessi dal tool: ospite no, adulto che non segue ragazzi no, tutore sì (prova e
  riepilogo con la scheda), un ragazzo non vede il riepilogo di un altro; dato del turno;
- scheda: `/api/esercizio` sul server vero (sessione, schermo personale, esercizio giusto,
  fuori orario, limite al minuto), la risposta attesa mai nella risposta HTTP.
"""

import datetime
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope import esercizi as E  # noqa: E402
from calliope import minori as M  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.esercizi import italiano as IT  # noqa: E402
from calliope.esercizi import matematica as MA  # noqa: E402
from calliope.esercizi import sessione as SE  # noqa: E402
from calliope.esercizi.modello import Classe  # noqa: E402
from calliope.esercizi.numeri import frazione_scritta, leggi_valore  # noqa: E402
from calliope.esercizi.registro import Registro  # noqa: E402
from calliope.esercizi.verifica import Wikizionario, verifica_italiano  # noqa: E402
from calliope.speaker_id import SpeakerContext, UserProfile, name_key  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

errori = 0
saltate = []


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


OGGI = datetime.date.today()


def nato(anni: int) -> str:
    d = OGGI - datetime.timedelta(days=30)
    try:
        return d.replace(year=d.year - anni).isoformat()
    except ValueError:
        return (d - datetime.timedelta(days=1)).replace(year=d.year - anni).isoformat()


# ─────────────────────────── numeri ───────────────────────────
print("── numeri detti e scritti ──")
for testo, attesa in (("56", 56), ("cinquantasei", 56), ("tre quarti", Fraction(3, 4)),
                      ("3 quarti", Fraction(3, 4)), ("3/4", Fraction(3, 4)), ("meno due", -2),
                      ("-2", -2), ("x = 4", 4), ("x uguale meno 3", -3),
                      ("uno virgola cinque", Fraction(3, 2)), ("1,5", Fraction(3, 2)),
                      ("un mezzo", Fraction(1, 2)), ("sette per otto fa cinquantasei", 56),
                      ("7 x 8 = 56", 56), ("cinque dodicesimi", Fraction(5, 12)),
                      ("due su tre", Fraction(2, 3)), ("milleduecentotrenta", 1230),
                      ("centotto", 108), ("dieci e mezzo", Fraction(21, 2)),
                      ("meno 9 mezzi", Fraction(-9, 2)), ("Fa 12.", 12)):
    v = leggi_valore(testo)
    verifica(f"«{testo}» → {attesa}", v == Fraction(attesa), str(v))
for testo in ("non lo so", "boh", "", "aggettivo"):
    verifica(f"contrario: «{testo}» non è un numero", leggi_valore(testo) is None,
             str(leggi_valore(testo)))

# ─────────────────────────── matematica ───────────────────────────
print("── generatori di matematica ──")
SIMBOLI_VOCE = ("/", "^", "−", "*", "=", "²", "³", "⁻", "ⁿ", "×", "·")
for arg in MA.GENERATORI:
    for L in (1, 2, 3):
        rotti, voce_male, giusta_no, sbagliata_si, lettere_no = [], [], [], [], []
        for seme in range(300):
            try:
                es = MA.genera(arg, L, seme)
            except ValueError as e:
                rotti.append(str(e))
                continue
            if not MA.verifica(es):
                rotti.append(seme)
            if any(s in es.voce for s in SIMBOLI_VOCE) or "-" in es.voce:
                voce_male.append(es.voce)
            if E.controlla(es, frazione_scritta(es.risposta)).giusta is not True:
                giusta_no.append((es.testo, frazione_scritta(es.risposta)))
            if E.controlla(es, es.risposta_detta).giusta is not True:
                lettere_no.append((es.testo, es.risposta_detta))
            if E.controlla(es, frazione_scritta(es.risposta + 1)).giusta is not False:
                sbagliata_si.append(es.testo)
        verifica(f"{arg} livello {L}: 300 semi, ricalcolo che torna", not rotti, str(rotti[:3]))
        verifica(f"{arg} livello {L}: voce senza simboli", not voce_male, str(voce_male[:2]))
        verifica(f"{arg} livello {L}: risposta giusta in cifre accettata", not giusta_no,
                 str(giusta_no[:2]))
        verifica(f"{arg} livello {L}: risposta detta («{es.risposta_detta}») accettata",
                 not lettere_no, str(lettere_no[:2]))
        verifica(f"{arg} livello {L}: risposta sbagliata rifiutata", not sbagliata_si,
                 str(sbagliata_si[:2]))
verifica("stesso seme, stesso esercizio",
         MA.genera("frazioni", 2, 7).testo == MA.genera("frazioni", 2, 7).testo)
es = next(e for e in (MA.genera("frazioni", 2, s) for s in range(200))
          if e.tipo == "frazione_ridotta")
f = es.risposta
non_ridotta = f"{f.numerator * 2}/{f.denominator * 2}"
r = E.controlla(es, non_ridotta)
verifica("semplifica: equivalente non ridotta → non giusta, non conta come errore",
         r.giusta is False and r.conta is False and "semplificare" in r.nota, str(r))
es = next(e for e in (MA.genera("frazioni", 3, s) for s in range(200))
          if e.dati.get("errore_tipico") and "+" in e.espressione)
a, b = es.espressione.split("+")
(n1, d1), (n2, d2) = [tuple(map(int, x.split("/"))) for x in (a, b)]
r = E.controlla(es, f"{n1 + n2}/{d1 + d2}")
verifica("frazioni: denominatori sommati → l'errore tipico detto",
         r.giusta is False and "denominatori" in r.nota or Fraction(n1 + n2, d1 + d2) == es.risposta,
         str(r))
es = MA.genera("equazioni", 1, 3)
verifica("equazione: «x uguale …» accettata", E.controlla(es, f"x uguale {es.risposta}").giusta)
r = E.controlla(es, "non lo so")
verifica("contrario: «non lo so» non conta come tentativo", r.giusta is None and not r.conta)
for cattivo in ("__import__('os')", "open('x')", "2**999", "1/0", "a+1"):
    try:
        MA.valuta(cattivo)
        verifica(f"valutatore: «{cattivo}» rifiutato", False)
    except (ValueError, ZeroDivisionError, SyntaxError):
        verifica(f"valutatore: «{cattivo}» rifiutato", True)

# ─────────────────────────── italiano ───────────────────────────
print("── generatori d'italiano ──")
for arg in IT.GENERATORI:
    for L in (1, 2, 3):
        giusta_no, sbagliata_si, forme = [], [], set()
        for seme in range(200):
            es = IT.genera(arg, L, seme)
            forme.add(es.dati["frase"])
            if E.controlla(es, es.risposta_detta).giusta is not True:
                giusta_no.append((es.testo, es.risposta_detta))
            if es.tipo == "scelta":
                altra = next(x for x in (IT.PARTI if arg == "analisi_grammaticale" else IT.RUOLI)
                             if x != es.risposta and not (x.startswith("predicato")
                                                          and es.risposta.startswith("predicato")))
                if E.controlla(es, altra).giusta is not False:
                    sbagliata_si.append((es.testo, altra))
        verifica(f"{arg} livello {L}: risposta giusta accettata", not giusta_no, str(giusta_no[:2]))
        verifica(f"{arg} livello {L}: risposta sbagliata rifiutata", not sbagliata_si,
                 str(sbagliata_si[:2]))
        verifica(f"{arg} livello {L}: frasi varie ({len(forme)} diverse su 200)", len(forme) > 40)
es = next(e for e in (IT.genera("analisi_grammaticale", 1, s) for s in range(100))
          if e.risposta == "nome")
verifica("«sostantivo» vale nome", E.controlla(es, "è un sostantivo").giusta is True)
verifica("contrario: «nome e verbo» non si capisce (due parti)",
         E.controlla(es, "nome o verbo").giusta is None)
verifica("contrario: «soggetto» in analisi grammaticale → nota, nessun tentativo",
         (lambda r: r.giusta is False and not r.conta)(E.controlla(es, "soggetto")))
es = next(e for e in (IT.genera("analisi_logica", 1, s) for s in range(200))
          if e.tipo == "parole" and e.dati["ruolo"] == "soggetto"
          and len(e.dati["indici"]) == 2)
art, nome = es.dati["gruppo"].split()
verifica("soggetto: «il soggetto è …» accettato",
         E.controlla(es, f"il soggetto è {art} {nome}").giusta is True)
verifica("soggetto: senza articolo accettato", E.controlla(es, nome).giusta is True)
verbo = next(p[0] for p in es.dati["parole"] if p[1] == "verbo")
verifica("contrario: il verbo come soggetto → sbagliata", E.controlla(es, verbo).giusta is False)
verifica("contrario: soggetto con il verbo attaccato → sbagliata",
         E.controlla(es, f"{art} {nome} {verbo}").giusta is False)
es = next(e for e in (IT.genera("analisi_logica", 3, s) for s in range(300))
          if e.tipo == "scelta" and e.risposta == "predicato nominale")
verifica("predicato nominale: «predicato» da solo vale, con la precisazione",
         (lambda r: r.giusta is True and "nominale" in r.nota)(E.controlla(es, "è il predicato")))

zim = Path(__file__).resolve().parent.parent / "biblioteca" / "wiktionary_it_all_nopic_2026-08.zim"
if not zim.exists():
    from calliope.installa.catalogo import risolvi_zim
    p = risolvi_zim(str(zim))
    zim = Path(p) if p else zim
if zim.exists():
    w = Wikizionario(path=str(zim))
    problemi = [(f, ps, w.parti(f)) for f, ps in IT.forme_lessico().items()
                if w.parti(f) is None or not ps <= w.parti(f)]
    verifica(f"lessico sul Wikizionario: ogni forma c'è con la sua parte "
             f"({len(IT.forme_lessico())} forme)", not problemi, str(problemi[:4]))
    verifica("Wikizionario: «mangiano» è un verbo, «gatto» un nome",
             w.parti("mangiano") == {"verbo"} and "nome" in w.parti("gatto"))
else:
    saltate.append("lessico sul Wikizionario")
    print("SALTATA IN PARTE: lessico sul Wikizionario (manca biblioteca/wiktionary_*.zim)")


# ─────────────────────────── verifica linguistica ───────────────────────────
print("── verifica linguistica ──")


class ParereFinto:
    def __init__(self, modo="giusto"):
        self.modo, self.chiamate, self.modello = modo, 0, "finto"
        self.ultimo_ms, self.ultimo_errore = 5.0, ""

    @property
    def pronto(self):
        return True

    def risolvi(self, es):
        from calliope.esercizi.verifica import attesa
        self.chiamate += 1
        if self.modo == "guasto":
            self.ultimo_errore = "ConnectTimeout"
            return None
        if self.modo == "sbagliato_una":
            self.modo = "giusto"
            return "verbo" if attesa(es) != "verbo" else "nome"
        if self.modo == "sbagliato":
            return "verbo" if attesa(es) != "verbo" else "nome"
        return attesa(es)


class DizFinto:
    pronto = True

    def __init__(self, sbaglia=()):
        self.sbaglia = set(sbaglia)

    def controlla_frase(self, parole):
        bad = [f for f, _ in parole if f in self.sbaglia]
        return not bad, [f"«{f}» no" for f in bad]


es = IT.genera("analisi_grammaticale", 2, 11)
verifica("secondo parere d'accordo → buono",
         verifica_italiano(es, DizFinto(), ParereFinto())["esito"] == "buono")
verifica("secondo parere diverso → scartato",
         verifica_italiano(es, DizFinto(), ParereFinto("sbagliato"))["esito"] == "scartato")
verifica("secondo parere guasto → non verificato",
         verifica_italiano(es, DizFinto(), ParereFinto("guasto"))["esito"] == "non_verificato")
parola = es.dati["parole"][0][0]
p = ParereFinto()
verifica("Wikizionario contrario → scartato senza chiedere al modello",
         verifica_italiano(es, DizFinto([parola]), p)["esito"] == "scartato" and p.chiamate == 0)

TMP = Path(tempfile.mkdtemp(prefix="calliope-esercizi-"))
cfg = Config()
cfg.memory_db = str(TMP / "memoria.db")
cfg.esercizi_pronti = 0                 # niente lavoro in secondo piano nelle prove


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
DARIO = profilo("Dario", admin=True, gender="m")
ELENA = profilo("Elena")
MARCO = profilo("Marco", gender="m")                 # adulto che non segue nessun ragazzo
BIANCA = profilo("Bianca", 9, tutori=["dario-id", "elena-id"])
LUCA = profilo("Luca", 12, tutori=["elena-id"], gender="m")
SARA = profilo("Sara", 16, tutori=["dario-id"])
REG = Reg([DARIO, ELENA, MARCO, BIANCA, LUCA, SARA])


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
REGISTRO = Registro(cfg.memory_db)
PARERE = ParereFinto()
SRV = SE.Servizio(cfg, REGISTRO, schermi=HUB, log=lambda *a: None, parere=PARERE,
                  wikizionario=DizFinto(), registry=REG)
SE.imposta(SRV)
TOOLS = build_registry(minori_tool=True)
from calliope.tools.minori import minori_specs  # noqa: E402

for spec in minori_specs():
    TOOLS.register(spec)


def ctx_di(nome, how="voce"):
    sc = SpeakerContext(REG)
    sc.current_speaker = nome
    sc.identified_by = how if nome else None
    c = ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None, schermi=HUB)
    c.regole = []
    return c


def chiama(args, chi, how="voce"):
    ctx = ctx_di(chi, how)
    level = ctx.speaker_ctx.current_level
    return json.loads(TOOLS.call("esercizi", args, ctx, level)), ctx


def ultima_scheda(tipo="esercizio"):
    return next((s for s, m in reversed(HUB.schede) if s["tipo"] == tipo), None)


# Il banco evita di richiedere al modello lo stesso esercizio
es = IT.genera("analisi_logica", 2, 5)
PARERE.chiamate = 0
SRV._verifica_italiano(es)
SRV._verifica_italiano(es)
verifica("banco: lo stesso esercizio si controlla una volta sola", PARERE.chiamate == 1,
         PARERE.chiamate)
verifica("banco: l'esercizio buono è salvato", REGISTRO.banco_leggi(es.firma)[0] == "buono")

# ─────────────────────────── flusso ───────────────────────────
print("── flusso a voce ──")
out, ctx = chiama({"azione": "inizia", "materia": "matematica", "argomento": "le frazioni"},
                  "Bianca")
verifica("inizio: frase con la prima domanda", "Prima domanda" in out.get("risposta_finale", ""),
         out)
verifica("inizio: classe dall'età (9 anni → quarta elementare)",
         "quarta elementare" in out["risposta_finale"], out["risposta_finale"])
verifica("inizio: azione in sospeso con il messaggio degli esercizi",
         out.get("in_sospeso", {}).get("tool") == "esercizi"
         and "azione=rispondi" in out["in_sospeso"]["messaggio"])
verifica("inizio: finisce con «?» (resta in sospeso nel turno dopo)",
         out["risposta_finale"].endswith("?"))
verifica("regola nel registro dei turni", "esercizi_inizio" in ctx.regole, ctx.regole)
sc = ultima_scheda()
s = SRV.sessione(BIANCA.id)
verifica("scheda personale con la domanda", sc is not None and sc["visibilita"] == "personale"
         and sc["domanda"] == s.es.testo and sc["chiave"] == f"esercizi:{BIANCA.id}")
pub = json.dumps(sc, ensure_ascii=False)
verifica("scheda senza risposta né spiegazione", not ({"risposta", "spiegazione",
                                                         "suggerimenti", "risposta_detta"}
                                                        & set(sc))
         and s.es.spiegazione not in pub)
verifica("dato del turno: esercizi in corso con la domanda",
         "esercizi in corso" in M.dato_turno(BIANCA) and s.es.testo in M.dato_turno(BIANCA))
verifica("contrario: nessun dato degli esercizi per un adulto", M.dato_turno(DARIO) == "")

giusta = frazione_scritta(s.es.risposta)
prima = s.es.firma
out, ctx = chiama({"azione": "rispondi", "risposta": giusta}, "Bianca")
verifica("giusta → complimenti e prossima", out.get("giusta") is True
         and "Prossima" in out["risposta_finale"] and SRV.sessione(BIANCA.id).es.firma != prima,
         out)
verifica("regola: corretta dal codice", "esercizi_corretto_dal_codice" in ctx.regole)
s = SRV.sessione(BIANCA.id)
sbagliata = frazione_scritta(s.es.risposta + 7)
out, _ = chiama({"azione": "rispondi", "risposta": sbagliata}, "Bianca")
verifica("sbagliata → «Non ancora» con un indizio, senza la soluzione",
         out.get("giusta") is False and "indizio" in out["risposta_finale"].lower()
         and s.es.spiegazione not in out["risposta_finale"], out)
out2, _ = chiama({"azione": "rispondi", "risposta": sbagliata}, "Bianca")
verifica("seconda sbagliata → un indizio diverso",
         out2["risposta_finale"] != out["risposta_finale"], out2["risposta_finale"])
out, _ = chiama({"azione": "aiuto"}, "Bianca")
verifica("aiuto: non conta come errore", s.errori == 2 and out["risposta_finale"].endswith("?"))
for _ in range(2):
    chiama({"azione": "rispondi", "risposta": sbagliata}, "Bianca")
verifica("prima del quinto errore: nessun avviso ai tutori",
         not [a for a in M.avvisi().da_dire(DARIO.id, segna=False) if a["tipo"] == "esercizi"])
spieg = s.es.spiegazione
out, ctx = chiama({"azione": "rispondi", "risposta": sbagliata}, "Bianca")
verifica("quinto errore → spiegazione", spieg in out["risposta_finale"]
         and out.get("soluzione_spiegata"), out["risposta_finale"])
verifica("quinto errore → «lo dico anche a Dario e ad Elena»",
         "a Dario e ad Elena" in out["risposta_finale"], out["risposta_finale"])
av_d = [a for a in M.avvisi().da_dire(DARIO.id, segna=False) if a["tipo"] == "esercizi"]
av_e = [a for a in M.avvisi().da_dire(ELENA.id, segna=False) if a["tipo"] == "esercizi"]
verifica("avviso vero ai due tutori, con l'argomento e senza le risposte",
         len(av_d) == 1 and len(av_e) == 1 and "frazioni" in av_d[0]["testo"]
         and sbagliata not in av_d[0]["testo"], (av_d, av_e))
s = SRV.sessione(BIANCA.id)
sbagliata = frazione_scritta(s.es.risposta + 7)
for _ in range(5):
    out, _ = chiama({"azione": "rispondi", "risposta": sbagliata}, "Bianca")
av_d2 = [a for a in M.avvisi().da_dire(DARIO.id, segna=False) if a["tipo"] == "esercizi"]
verifica("seconda spiegazione nella sessione: nessun altro avviso", len(av_d2) == 1, av_d2)
s = SRV.sessione(BIANCA.id)
spieg = s.es.spiegazione
out, ctx = chiama({"azione": "soluzione"}, "Bianca")
verifica("soluzione chiesta da una bambina → negata (regola dei tentativi)",
         spieg not in out["risposta_finale"] and "esercizi_soluzione_negata" in ctx.regole, out)
out, _ = chiama({"azione": "salta"}, "Bianca")
verifica("salta: niente soluzione, prossima", spieg not in out["risposta_finale"]
         and "Prossima" in out["risposta_finale"])
out, _ = chiama({"azione": "ripeti"}, "Bianca")
verifica("ripeti: la domanda", out["risposta_finale"] == SRV.sessione(BIANCA.id).es.voce)
out, ctx = chiama({"azione": "segnala", "nota": "secondo me è sbagliato"}, "Bianca")
verifica("segnala (matematica): ricalcolo che torna, segnato per i tutori",
         "torna" in out["risposta_finale"] and REGISTRO.segnalazioni(BIANCA.id)
         and REGISTRO.segnalazioni(BIANCA.id)[-1]["esito"] == "confermato", out)
s = SRV.sessione(BIANCA.id)
liv = s.livello
for _ in range(3):
    chiama({"azione": "rispondi", "risposta": frazione_scritta(SRV.sessione(BIANCA.id).es.risposta)},
           "Bianca")
verifica("tre giuste al primo colpo → livello più alto",
         SRV.sessione(BIANCA.id).livello == min(3, liv + 1), (liv, SRV.sessione(BIANCA.id).livello))
out, _ = chiama({"azione": "fine"}, "Bianca")
verifica("fine: il conto della sessione", "Abbiamo finito" in out["risposta_finale"]
         and SRV.sessione(BIANCA.id) is None, out)
verifica("scheda finita", ultima_scheda()["stato"] == "finita")
t = REGISTRO.tentativi(BIANCA.id)
verifica("registro: tentativi con esito, risposta data e canale",
         {"giusta", "sbagliata", "aiuto", "spiegato", "saltato"} <= {x["esito"] for x in t}
         and all(x["canale"] == "voce" for x in t), {x["esito"] for x in t})
out, _ = chiama({"azione": "rispondi", "risposta": "3"}, "Bianca")
verifica("contrario: rispondi senza esercizi aperti", out.get("ok") is False)

print("── italiano: secondo parere ──")
PARERE.modo = "giusto"
out, _ = chiama({"azione": "inizia", "argomento": "analisi logica"}, "Luca")
verifica("italiano: inizio (12 anni → seconda media)", "seconda media" in out.get(
    "risposta_finale", ""), out)
s = SRV.sessione(LUCA.id)
verifica("italiano: esercizio controllato (buono)", s.es.verifica.get("esito") == "buono",
         s.es.verifica)
sc = ultima_scheda()
verifica("italiano: scheda con le scelte o il campo", sc["tipo"] == "esercizio" and (
    sc["scelte"] or sc["campo"] == "testo"))
PARERE.modo = "sbagliato_una"
firma = s.es.firma
out, ctx = chiama({"azione": "segnala"}, "Luca")
verifica("segnala (italiano) con il ricontrollo che non torna → tolto e prossimo",
         "lo tolgo" in out["risposta_finale"] and REGISTRO.banco_leggi(firma)[0] == "scartato"
         and "esercizi_segnalato_tolto" in ctx.regole, out)
verifica("avviso della segnalazione a Elena", any(
    a["tipo"] == "esercizi" and "segnalato" in a["testo"]
    for a in M.avvisi().da_dire(ELENA.id, segna=False)))
PARERE.modo = "guasto"
SRV._pronti.clear()
out, _ = chiama({"azione": "inizia", "argomento": "analisi grammaticale", "classe": "terza media"},
                "Luca")
verifica("secondo parere guasto: niente esercizi d'italiano non controllati",
         out.get("ok") is False and "non riesco" in out["risposta_finale"], out)
cfg.esercizi_senza_secondo_parere = True
out, _ = chiama({"azione": "inizia", "argomento": "analisi grammaticale"}, "Luca")
verifica("con esercizi_senza_secondo_parere: esercizio dato, segnato «non_verificato»",
         out.get("ok") is True and SRV.sessione(LUCA.id).es.verifica.get("esito") == "non_verificato",
         out)
cfg.esercizi_senza_secondo_parere = False
PARERE.modo = "giusto"
chiama({"azione": "fine"}, "Luca")

print("── permessi ──")
out, ctx = chiama({"azione": "inizia", "materia": "matematica"}, None)
verifica("ospite: rifiutato", out.get("ok") is False, out)
out, ctx = chiama({"azione": "inizia", "materia": "matematica", "argomento": "potenze"}, "Marco")
verifica("adulto che non segue ragazzi: rifiutato", out.get("ok") is False
         and "esercizi_permesso" in ctx.regole, out)
out, _ = chiama({"azione": "inizia", "argomento": "equazioni"}, "Dario")
verifica("tutore che li prova: sì", out.get("ok") is True and "Prima domanda" in out[
    "risposta_finale"], out)
s = SRV.sessione(DARIO.id)
spieg = s.es.spiegazione
out, _ = chiama({"azione": "soluzione"}, "Dario")
verifica("adulto: la soluzione quando la chiede", spieg in out["risposta_finale"], out)
chiama({"azione": "fine"}, "Dario")
out, _ = chiama({"azione": "inizia", "materia": "matematica"}, "Sara")
verifica("materia senza argomento → domanda con gli argomenti adatti",
         out["risposta_finale"].endswith("?") and "equazioni" in out["risposta_finale"]
         and "addizioni" not in out["risposta_finale"]
         and out.get("in_sospeso", {}).get("tool") == "esercizi", out)
out, _ = chiama({"azione": "inizia", "materia": "matematica", "argomento": "potenze"}, "Sara")
verifica("adolescente: «i tuoi tutori vedono come vanno»", "tutori vedono" in out[
    "risposta_finale"], out)
chiama({"azione": "rispondi", "risposta": "1"}, "Sara")
chiama({"azione": "fine"}, "Sara")
out, ctx = chiama({"azione": "riepilogo", "nome": "Bianca"}, "Luca")
verifica("un ragazzo non sente il riepilogo di un altro", out.get("ok") is False
         and "esercizi_riepilogo_permesso" in ctx.regole, out)
n = len(HUB.schede)
out, _ = chiama({"azione": "riepilogo", "nome": "Bianca"}, "Dario")
verifica("tutore: riepilogo con i numeri", "Bianca ha fatto" in out["risposta_finale"]
         and "frazioni" in out["risposta_finale"], out)
rs = next((s for s, m in HUB.schede[n:] if s["tipo"] == "esercizi_riepilogo"), None)
verifica("tutore: scheda del riepilogo con dettaglio, campione e segnalazioni",
         rs is not None and rs["righe"] and rs["campione"] and rs["segnalazioni"]
         and HUB.schede[-1][1].persona == DARIO.id, rs and list(rs))
out, _ = chiama({"azione": "riepilogo"}, "Sara")
verifica("adolescente: il proprio riepilogo", "Sara ha fatto" in out["risposta_finale"], out)
r = M.dato_turno(SARA)
verifica("contrario: dopo «fine» niente esercizi nel dato del turno", "esercizi in corso" not in r)
mg = json.loads(TOOLS.call("minore_gestisci", {"nome": "Bianca", "azione": "riepilogo_compiti"},
                           ctx_di("Dario"), "amministra"))
verifica("riepilogo dei compiti del tutore: con gli esercizi",
         "esercizi" in mg.get("risposta_finale", ""), mg)

# ─────────────────────────── scheda: /api/esercizio ───────────────────────────
print("── scheda: /api/esercizio sul server vero ──")
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402


def chiedi(port, percorso, sessione=None, token=None, dati=None):
    h = {"Content-Type": "application/json"}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST",
                                 data=json.dumps(dati or {}).encode("utf-8"))
    for tentativo in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except (ConnectionResetError, urllib.error.URLError):
            # Sotto carico (hook in parallelo) Windows a volte chiude la prima connessione
            if tentativo == 2:
                raise
            time.sleep(0.3)


hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
srv_http = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
hub.esercizi = SRV
SRV.schermi = hub
try:
    arch = hub.archivio
    _, t_b = arch.crea_con_token("camera", proprietario=BIANCA.id, proprietario_nome="Bianca")
    _, t_l = arch.crea_con_token("cameretta", proprietario=LUCA.id, proprietario_nome="Luca")
    _, t_s = arch.crea_con_token("cucina")
    hub._rinfresca()
    port = srv_http.port
    sess = {k: chiedi(port, "/api/accedi", token=t)[1]["sessione"]
            for k, t in (("b", t_b), ("l", t_l), ("s", t_s))}
    st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "rispondi", "risposta": "3"})
    verifica("senza sessione degli esercizi (si comincia a voce) → 409", st == 409, (st, r))
    out, _ = chiama({"azione": "inizia", "argomento": "addizioni", "classe": "prima elementare"},
                    "Bianca")
    s = SRV.sessione(BIANCA.id)
    st, r = chiedi(port, "/api/esercizio", None, dati={"azione": "rispondi"})
    verifica("senza sessione dello schermo → 401", st == 401, st)
    st, r = chiedi(port, "/api/esercizio", sess["s"], dati={"azione": "rispondi",
                                                           "esercizio": s.es.firma, "risposta": "3"})
    verifica("schermo di stanza → 403", st == 403, (st, r))
    st, r = chiedi(port, "/api/esercizio", sess["l"], dati={"azione": "rispondi",
                                                           "esercizio": s.es.firma, "risposta": "3"})
    verifica("schermo di un altro ragazzo (nessuna sua sessione) → 409", st == 409, (st, r))
    st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "rispondi",
                                                           "esercizio": "vecchio", "risposta": "3"})
    verifica("esercizio che non c'è più → 409 con la scheda nuova", st == 409
             and r.get("scheda", {}).get("esercizio") == s.es.firma, (st, r))
    attesa = frazione_scritta(s.es.risposta)
    sbagliata = frazione_scritta(s.es.risposta + 3)
    st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "rispondi",
                                                           "esercizio": s.es.firma,
                                                           "risposta": sbagliata})
    verifica("risposta sbagliata scritta → esito nella scheda, nessuna soluzione",
             st == 200 and r["scheda"]["esito"]["giusta"] is False
             and s.es.spiegazione not in json.dumps(r, ensure_ascii=False), (st, r))
    verifica("nella risposta HTTP mai la risposta attesa come campo",
             not ({"risposta", "spiegazione", "suggerimenti"} & set(r["scheda"])))
    st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "rispondi",
                                                           "esercizio": s.es.firma,
                                                           "risposta": attesa})
    verifica("risposta giusta scritta → esito giusto e domanda nuova", st == 200
             and r["scheda"]["esito"]["giusta"] is True and r["scheda"]["esercizio"] != s.es.firma
             or (st == 200 and r["scheda"]["esito"]["giusta"] is True), (st, r))
    verifica("canale «scheda» nel registro", any(x["canale"] == "scheda"
                                                 for x in REGISTRO.tentativi(BIANCA.id)))
    st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "pippo", "esercizio":
                                                           SRV.sessione(BIANCA.id).es.firma})
    verifica("azione sconosciuta → 400", st == 400, st)
    # Fuori orario: niente esercizi nemmeno dalla scheda
    M.regole().imposta(BIANCA.id, "orari", ["00:00-23:59"])
    st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "aiuto", "esercizio":
                                                           SRV.sessione(BIANCA.id).es.firma})
    verifica("fuori orario → 403 con la frase della pausa", st == 403 and "riposare" in r.get(
        "errore", ""), (st, r))
    M.regole().imposta(BIANCA.id, "orari", None)
    n = 0
    for _ in range(35):
        st, r = chiedi(port, "/api/esercizio", sess["b"], dati={"azione": "aiuto", "esercizio":
                                                               SRV.sessione(BIANCA.id).es.firma})
        n += st == 429
    verifica("limite al minuto per schermo → 429", n > 0, n)
finally:
    srv_http.ferma()

print()
if saltate:
    print(f"SALTATA IN PARTE: {', '.join(saltate)}")
print("ESITO:", "tutto ok" if not errori else f"{errori} errori")
sys.exit(1 if errori else 0)
