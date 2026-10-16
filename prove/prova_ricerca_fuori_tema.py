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


c = ctx_web(STARTUP, "Approfondiamo questo argomento", STORIA_ORIONE)
res = json.loads(reg_n.call("web_cerca", {"domanda": "Orionyx storia"}, c, "familiare"))
verifica("web_cerca: «pertinenti» 0 su 2 con la nota, regola ricerca_fuori_tema",
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

print(f"\n{errori} errori." if errori else "\nTutto ok.")
sys.exit(1 if errori else 0)
