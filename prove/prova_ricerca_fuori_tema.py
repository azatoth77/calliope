import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dei risultati della ricerca fuori tema (16/10, issue #101).

Casi veri della DGX del 15/10 sera: dopo un racconto sul mito di Orione, «approfondiamo questo
argomento» → web_cerca con una domanda storpiata, risultati su una startup dal nome simile,
riferiti per intero; biblioteca_cerca con voci omonime; dichiarazioni attribuite a un altro
politico tre minuti dopo una lettura delle notizie, a memoria.

1. I testi di brain.py: nessun «tipo notizie» (le notizie hanno il loro tool dal 13/10); la riga
   delle ricerche con le notizie per nome, i risultati fuori tema da non riferire, niente nomi e
   cifre a memoria. Contrario: senza il tool notizie web_cerca ha ancora il tipo.
2. Il tool notizie nell'elenco delle ricerche (tema o numero del fatto), e «approfondisci» dopo
   le notizie va al modello (ricerca_recente).
3. La misura di pertinenza (calliope/pertinenza.py): Orione e la startup «0 su N», i contrari
   (risultati sul mito, la frase con il suo nome, niente con cui confrontare).
4. web_cerca e biblioteca_cerca con «pertinenti» e la regola `ricerca_fuori_tema`; «pertinenti»
   fuori dalla busta dei dati non fidati.
"""

import json
from types import SimpleNamespace

import calliope.brain as brain_mod
from calliope import pertinenza, provenienza
from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class SpeakerCtx:
    def __init__(self, name=None, level="familiare"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = "voce" if name else None


class Speakers:
    def get(self, n):
        return None

    def known_speakers(self):
        return []


class BackendFinto:
    def __init__(self, copione):
        self.copione = list(copione)
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append(json.dumps(messages, ensure_ascii=False))
        yield from self.copione.pop(0)


# ── storia e risultati del caso vero (nomi di fantasia) ──
STORIA_ORIONE = [
    ("user", "Raccontami il mito di Orione"),
    ("assistant", "Orione era un gigante cacciatore, figlio di Poseidone. Secondo il mito fu "
                  "ucciso da uno scorpione mandato da Gea, e Zeus lo pose tra le stelle come "
                  "costellazione, opposta a quella dello Scorpione."),
]
STARTUP = [("Orionyx raccoglie 40 milioni", "La startup di modelli linguistici annuncia un "
            "nuovo round di finanziamento guidato da fondi americani."),
           ("Orionyx, il nuovo modello", "Il modello linguistico open source supera i "
            "concorrenti nei test di programmazione.")]
MITO = [("Orione (mitologia)", "Orione è un gigante cacciatore della mitologia greca, figlio "
         "di Poseidone, ucciso da uno scorpione."),
        ("La costellazione di Orione", "Una delle costellazioni più riconoscibili del cielo "
         "invernale, con le stelle Betelgeuse e Rigel.")]


# ─────────────────────── 1. i testi di brain.py ───────────────────────
testi = {k: v for k, v in vars(brain_mod).items() if k.startswith("RICERCA") and isinstance(v, str)}
verifica("testi: nessun «tipo notizie» nelle righe delle ricerche",
         testi and not any("tipo notizie" in v for v in testi.values()),
         str([k for k, v in testi.items() if "tipo notizie" in v]))
verifica("testi: i risultati fuori tema non si riferiscono",
         "non riguardano ciò di cui parlavate, non riferirli" in brain_mod.RICERCA_MSG
         and "chiedi cosa cercare" in brain_mod.RICERCA_MSG)
verifica("testi: niente nomi e cifre di risultati che non ha più davanti",
         "non hai più davanti non citare nomi, cifre o dichiarazioni" in brain_mod.RICERCA_MSG)

cfg = Config()
cfg.online = True


def brain(reg, copione):
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, reg, []
    b.tool_ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Ada"),
                             speaker=None)
    b.backend = BackendFinto(copione)
    b.on_tool_start = None
    return b


def call(i, nome, args):
    return {"id": f"call_{i}", "name": nome, "arguments": args}


def turno(utente, risposta, chiamata=None):
    out = [{"role": "user", "content": utente}]
    if chiamata:
        out += [{"role": "assistant", "content": "", "tool_calls": [chiamata]},
                {"role": "tool", "name": chiamata["name"], "content": "{}"}]
    return out + [{"role": "assistant", "content": risposta}]


reg_n = build_registry(web=cfg, notizie=cfg, biblioteca=True)
reg_senza = build_registry(web=cfg, biblioteca=True)

# web_cerca col tipo «notizie» rimasto nella storia, con il tool notizie: si richiama notizie
b = brain(reg_n, [[("text", "Ok.")]])
b.history = turno("Le notizie di sport", "Secondo l'ANSA…",
                  call(0, "web_cerca", {"domanda": "sport", "tipo": "notizie"}))
"".join(b.stream_reply("Dimmi di più", "familiare"))
dati = b.backend.visti[-1]
verifica("con notizie: niente «tipo notizie» nei dati del turno, «(le notizie con notizie)»",
         "tipo notizie" not in dati and "(le notizie con notizie)" in dati
         and "«sport» con notizie" in dati and "web_cerca (notizie)" not in dati, dati[-900:])
verifica("con notizie: la spinta richiamerebbe notizie",
         b._ricerca_turno(len(b.history), "familiare")[1] == "notizie")

# Contrario: senza il tool notizie web_cerca ha ancora il tipo, e la fonte lo dice
b = brain(reg_senza, [[("text", "Ok.")]])
b.history = turno("Le notizie di sport", "Secondo l'ANSA…",
                  call(0, "web_cerca", {"domanda": "sport", "tipo": "notizie"}))
"".join(b.stream_reply("Dimmi di più", "familiare"))
dati = b.backend.visti[-1]
verifica("senza notizie: «web_cerca (notizie)», niente «(le notizie con notizie)»",
         "«sport» con web_cerca (notizie)" in dati and "(le notizie con notizie)" not in dati
         and "tipo notizie" not in dati, dati[-900:])

# ─────────────── 2. il tool notizie nell'elenco delle ricerche ───────────────
# Caso vero delle 18:59 → 19:02: una testata letta con notizie, poi «chi l'ha detto?» a memoria
b = brain(reg_n, [[("text", "Ok.")]])
b.history = (turno("Novità sullo sciopero dei treni?", "Secondo due testate…",
                   call(0, "notizie", {"tema": "sciopero treni"}))
             + turno("Dimmi di più sulla seconda", "La seconda…",
                     call(1, "notizie", {"fatto": 2})))
"".join(b.stream_reply("Chi l'ha detto?", "familiare"))
dati = b.backend.visti[-1]
verifica("notizie nell'elenco: il numero del fatto e il tema",
         "«notizia 2» con notizie; «sciopero treni» con notizie" in dati
         and "ricerca_recente" in b.rules_fired(), dati[-900:])
verifica("notizie: «restano qui sopra» invece di «non sono più qui» (le notizie restano in busta)",
         "le notizie appena lette sono ancora qui sopra" in dati
         and "quei risultati non sono più qui" not in dati, dati[-900:])
verifica("spinta verso notizie: tema o numero del fatto, non «una domanda»",
         "Chiama notizie con il tema o con fatto = il numero della notizia"
         in brain_mod.RICERCA_NUDGE.format(tool="notizie", come=brain_mod.RICERCA_COME["notizie"])
         and "una domanda" not in brain_mod.RICERCA_COME["notizie"])
b2 = brain(reg_n, [[("text", "Ok.")]])
b2.history = (turno("Novità sullo sciopero dei treni?", "Secondo due testate…",
                    call(0, "notizie", {"tema": "sciopero treni"}))
              + turno("Che ore sono?", "Le 19.") + turno("Grazie", "Prego.")
              + turno("Il mito di Orione", "Orione…",
                      call(1, "biblioteca_cerca", {"domanda": "mito di Orione"})))
"".join(b2.stream_reply("E poi?", "familiare"))
dati2 = b2.backend.visti[-1]
verifica("misti: la biblioteca non c'è più, delle notizie titoli e testate",
         "quei risultati non sono più qui, delle notizie restano qui sopra titoli e testate"
         in dati2, dati2[-900:])
verifica("notizie: ricerca_recente per il ciclo («approfondisci» al modello)",
         b.ricerca_recente() == {"tool": "notizie", "domanda": "notizia 2"},
         str(b.ricerca_recente()))
# Contrario: nessuna ricerca prima → niente riga delle ricerche
b = brain(reg_n, [[("text", "Ok.")]])
b.history = turno("Che ore sono?", "Le 19.")
"".join(b.stream_reply("Chi l'ha detto?", "familiare"))
verifica("contrario: senza ricerche prima niente riga", "hai cercato" not in b.backend.visti[-1]
         and b.ricerca_recente() is None)
# Il criterio biblioteca/internet resta con le due fonti, anche con notizie
b = brain(reg_n, [[("text", "Ok.")]])
b.history = turno("Il mito di Orione", "Orione…",
                  call(0, "biblioteca_cerca", {"domanda": "mito di Orione"}))
"".join(b.stream_reply("Approfondiamo questo argomento", "familiare"))
dati = b.backend.visti[-1]
verifica("con biblioteca, web e notizie: il criterio c'è",
         "biblioteca_cerca per i fatti da enciclopedia" in dati
         and "«mito di Orione» con biblioteca_cerca" in dati, dati[-700:])

# ─────────────────────── 3. la misura di pertinenza ───────────────────────
testi_s = [f"{t} {x}" for t, x in STARTUP]
testi_m = [f"{t} {x}" for t, x in MITO]
m = pertinenza.misura(testi_s, "Approfondiamo questo argomento", STORIA_ORIONE)
verifica("pertinenza: la startup dopo il mito di Orione, 0 su 2",
         m == {"pertinenti": 0, "totale": 2}, str(m))
m = pertinenza.misura(testi_m, "Approfondiamo questo argomento", STORIA_ORIONE)
verifica("pertinenza, contrario: i risultati sul mito, 2 su 2",
         m == {"pertinenti": 2, "totale": 2}, str(m))
m = pertinenza.misura(testi_s + testi_m, "Approfondiamo questo argomento", STORIA_ORIONE)
verifica("pertinenza: misti, 2 su 4", pertinenza.detta(m) == "2 su 4", str(m))
m = pertinenza.misura(["Camillo Benso, conte di Cavour Statista piemontese"], "Chi era Cavour?",
                      [])
verifica("pertinenza, contrario: una parola della frase basta (senza storia)",
         m == {"pertinenti": 1, "totale": 1}, str(m))
m = pertinenza.misura(["Meteo Milano: domani sole"], "Che tempo fa a Milano?", STORIA_ORIONE)
verifica("pertinenza, contrario: argomento nuovo nella frase, pertinente",
         m["pertinenti"] == 1, str(m))
verifica("pertinenza: niente con cui confrontare → None",
         pertinenza.misura(testi_s, "Dimmi di più", []) is None
         and pertinenza.misura([], "Chi era Cavour?", []) is None)
# I falsi «fuori tema» della revisione della PR #115 (scratchpad rev115script): ora pertinenti
METEO = [("user", "Che tempo fa a Milano?"), ("assistant", "A Milano oggi c'è sole con 22 gradi.")]
PARTITA = [("user", "Chi ha vinto ieri sera?"),
           ("assistant", "Ha vinto l'Inter due a uno sul Napoli.")]
ALTRO = [("user", "Metti un timer di 5 minuti"), ("assistant", "Fatto, timer di cinque minuti.")]
CASI_REVISORE = [
    ("seguito breve «e domani?» dopo il meteo, una parola della storia",
     ["Previsioni meteo Milano: martedì pioggia e temporali, minime 12 gradi"], "e domani?", METEO),
    ("«e adesso chi è primo?»: primo e primi",
     ["Serie A: nerazzurri primi dopo la settima giornata"], "e adesso chi è primo?", PARTITA),
    ("sigla breve nella frase: PIL", ["PIL: cos'è e come si calcola"], "Cos'è il PIL?", ALTRO),
    ("sigla breve: NBA", ["Risultati NBA della notte"], "E la NBA?", ALTRO),
    ("nome breve con la maiuscola: Eco", ["Umberto Eco, semiologo e scrittore"], "Chi era Eco?",
     ALTRO),
    ("sigla con cifra: F1", ["F1, GP di Monza: vince Leclerc"], "Chi ha vinto in F1?", []),
    ("flessione: gatti e gatto", ["Il gatto dorme fino a sedici ore al giorno"],
     "Quanto dormono i gatti?", []),
    ("flessione: Roma e romano", ["L'impero romano raggiunse la massima estensione sotto Traiano"],
     "Quando era più grande l'impero di Roma?", []),
    ("flessione: vinto e vince", ["Leclerc vince a Monza"], "Chi ha vinto?", []),
    ("nome storpiato da Whisper: Siner e Sinner", ["Jannik Sinner vince a Shanghai"],
     "Come è andato Siner?", []),
    ("inglese con lo stesso nome: Orion e Orione",
     ["Orion (mythology) Orion was a giant huntsman in Greek mythology, son of Poseidon"],
     "Approfondiamo questo argomento", STORIA_ORIONE),
]
for nome, testi, frase, storia in CASI_REVISORE:
    m = pertinenza.misura(testi, frase, storia)
    verifica(f"pertinenza, contrario dei falsi fuori tema: {nome}",
             m is not None and m["pertinenti"] == m["totale"], str(m))
# Le flessioni non si allargano ai nomi simili: Orione e Orionyx restano diversi
verifica("pertinenza: Orione e Orionyx non sono la stessa parola, Orione e Orion sì",
         not pertinenza.stessa("orione", "orionyx") and pertinenza.stessa("orione", "orion")
         and not pertinenza.stessa("mito", "modelli"))
verifica("pertinenza: le parole brevi con la maiuscola in testa non sono nomi",
         pertinenza.parole("Chi era Eco? Che bello") == {"eco", "bello"},
         str(pertinenza.parole("Chi era Eco? Che bello")))
verifica("pertinenza: una sola parola in comune con la storia non basta",
         pertinenza.misura(["Gigante buono, un film"], "e poi?", STORIA_ORIONE)["pertinenti"] == 0)


# ─────────────── 4. web_cerca e biblioteca_cerca con «pertinenti» ───────────────
class WebFinto:
    def __init__(self, risultati):
        self.risultati = risultati

    def cerca(self, domanda, tipo="web", **kw):
        return {"ok": True, "domanda": domanda, "risultati": [
            SimpleNamespace(sito="Sito", titolo=t, testo=x, url="https://esempio.it/a",
                            data=None, vecchio=False) for t, x in self.risultati]}


def ctx_web(risultati, frase, storia):
    c = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Ada"), speaker=None,
                    web=WebFinto(risultati))
    c.user_text, c.storia = frase, list(storia)
    return c


# Di serie in ombra (revisione della PR #115): solo nel registro dei turni, niente al modello
verifica("config: ricerca_pertinenza di serie «ombra»", Config().ricerca_pertinenza == "ombra")
c = ctx_web(STARTUP, "Approfondiamo questo argomento", STORIA_ORIONE)
res = json.loads(reg_n.call("web_cerca", {"domanda": "Orionyx storia"}, c, "familiare"))
verifica("ombra: niente «pertinenti» al modello, regole ricerca_fuori_tema_ombra e misurata",
         "pertinenti" not in res and "pertinenti" not in res.get("cosa_fare", "")
         and "ricerca_fuori_tema_ombra" in c.regole and "ricerca_pertinenza_misurata" in c.regole
         and "ricerca_fuori_tema" not in c.regole, str(c.regole))
c = ctx_web(MITO, "Approfondiamo questo argomento", STORIA_ORIONE)
reg_n.call("web_cerca", {"domanda": "mito di Orione"}, c, "familiare")
verifica("ombra, contrario: risultati sul mito, misurata senza fuori tema",
         "ricerca_pertinenza_misurata" in c.regole and "ricerca_fuori_tema_ombra" not in c.regole)
cfg.ricerca_pertinenza = "spenta"
c = ctx_web(STARTUP, "Approfondiamo questo argomento", STORIA_ORIONE)
res = json.loads(reg_n.call("web_cerca", {"domanda": "Orionyx storia"}, c, "familiare"))
verifica("spenta: niente misura né regole", "pertinenti" not in res
         and not [r for r in c.regole if r.startswith("ricerca_")], str(c.regole))
cfg.ricerca_pertinenza = "attiva"
c = ctx_web(STARTUP, "Approfondiamo questo argomento", STORIA_ORIONE)
res = json.loads(reg_n.call("web_cerca", {"domanda": "Orionyx storia"}, c, "familiare"))
verifica("attiva: «pertinenti» 0 su 2 con la nota, regola ricerca_fuori_tema",
         str(res.get("pertinenti", "")).startswith("0 su 2 (nessun risultato")
         and "ricerca_fuori_tema" in c.regole, str(res)[:400])
busta = json.loads(provenienza.racchiudi_risultato("web", json.dumps(res, ensure_ascii=False)))
verifica("web_cerca: «pertinenti» fuori dalla busta dei dati non fidati (come la legge Brain)",
         busta.get("pertinenti", "").startswith("0 su 2")
         and "risultati" in busta["dato_non_fidato"]["contenuto"]
         and "pertinenti" not in busta["dato_non_fidato"]["contenuto"], str(busta)[-300:])
verifica("web_cerca: cosa_fare, i risultati fuori tema non si riferiscono",
         "non riferirli" in res.get("cosa_fare", "") and "chiedi cosa cercare" in res["cosa_fare"])
c = ctx_web(MITO, "Approfondiamo questo argomento", STORIA_ORIONE)
res = json.loads(reg_n.call("web_cerca", {"domanda": "mito di Orione"}, c, "familiare"))
verifica("web_cerca, contrario: risultati sul mito, 2 su 2 e nessuna regola",
         res.get("pertinenti") == "2 su 2" and "ricerca_fuori_tema" not in c.regole, str(res)[:300])
c = ctx_web(STARTUP, "Dimmi di più", [])
res = json.loads(reg_n.call("web_cerca", {"domanda": "Orionyx"}, c, "familiare"))
verifica("web_cerca, contrario: niente con cui confrontare, niente «pertinenti»",
         "pertinenti" not in res and "ricerca_fuori_tema" not in c.regole)
verifica("provenienza: «pertinenti» fra i campi di controllo",
         "pertinenti" in provenienza.CONTROLLO)


class BibliotecaFinta:
    def __init__(self, passaggi):
        self.passaggi = passaggi

    def cerca(self, domanda, semplice=False):
        return [SimpleNamespace(titolo=t, testo=x, fonte="Wikipedia") for t, x in self.passaggi]

    def richieste(self, q):
        return set()

    def opzioni(self, q):
        return []

    def testo_voce(self, p):
        return p.testo


OMONIMI = [("Orione (nave)", "Orione fu un incrociatore ausiliario della Regia Marina varato nel "
            "1931."), ("Orione (fumetto)", "Personaggio dei fumetti americani creato nel 1971.")]
c = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Ada"), speaker=None,
                biblioteca=BibliotecaFinta(OMONIMI))
c.user_text, c.storia = "Approfondiamo questo argomento", list(STORIA_ORIONE)
res = json.loads(reg_n.call("biblioteca_cerca",
                            {"domanda": "mito di Orione e la sua storia astronomica"}, c,
                            "familiare"))
# «Orione» è nella storia ma una parola sola non basta: la nave e il fumetto non parlano del mito
verifica("biblioteca_cerca: voci omonime, «pertinenti» 0 su 2 e la regola",
         str(res.get("pertinenti", "")).startswith("0 su 2") and "ricerca_fuori_tema" in c.regole,
         str(res)[:400])
verifica("biblioteca_cerca: cosa_fare, se non è sicura lo dice e chiede",
         "nella biblioteca non hai trovato niente su quello" in res.get("cosa_fare", ""))
c.biblioteca, c.regole = BibliotecaFinta(MITO), []
res = json.loads(reg_n.call("biblioteca_cerca", {"domanda": "mito di Orione"}, c, "familiare"))
verifica("biblioteca_cerca, contrario: voci sul mito, 2 su 2 e nessuna regola",
         res.get("pertinenti") == "2 su 2" and "ricerca_fuori_tema" not in c.regole, str(res)[:300])

# La riga di `calliope stato --turni` (revisione della PR #115: conta davvero le regole)
turni = [{"regole": ["ricerca_pertinenza_misurata", "ricerca_fuori_tema_ombra"]},
         {"regole": ["ricerca_pertinenza_misurata"]}, {"regole": ["ricerca_recente"]},
         {"regole": ["ricerca_pertinenza_misurata", "ricerca_fuori_tema"]}]
r = pertinenza.riassunto(turni)
riga = pertinenza.testo(r, "ombra")
verifica("stato --turni: misurate 3, fuori tema 1 in ombra e 1 detta",
         r == {"misurate": 3, "fuori_tema": 1, "fuori_tema_ombra": 1}
         and "2 «fuori tema» su 3" in riga and "in ombra 1" in riga, riga)
verifica("stato --turni: senza ricerche misurate lo dice",
         "nessuna ricerca misurata" in pertinenza.testo(pertinenza.riassunto([]), "ombra"))
import inspect  # noqa: E402
from calliope import stato as stato_mod  # noqa: E402
verifica("stato --turni stampa la riga della pertinenza",
         "pertinenza.testo(pert_r" in inspect.getsource(stato_mod))
from calliope.tools.conversazioni import FONTI_TIPO  # noqa: E402
verifica("conversazioni: la fonte delle notizie senza «tipo «notizie»»",
         "tipo «notizie»" not in FONTI_TIPO[("web_cerca", "notizie")]
         and "notizie" in FONTI_TIPO[("web_cerca", "notizie")])

print(f"\n{errori} errori." if errori else "\nTutto ok.")
sys.exit(1 if errori else 0)
