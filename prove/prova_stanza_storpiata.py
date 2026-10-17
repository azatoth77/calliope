import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco delle righe della stanza storpiate e della domanda insistita (15/10, caso vero
in auto col 26B; qui con nomi e risultati di fantasia).

A. Le righe della stanza sono trascrizione grezza: il blocco, il primo pezzo nella storia, i
   pezzi dopo e il prompt di sistema (con stanza_cerca) dicono al modello di ricostruire con
   prudenza le parole evidenti invece di dire che non sono state dette (fino al 16/10 con
   l'esempio «mi è sembrato di sentire…», storico; dal 16/10 «avvertendo in breve che è una tua
   ricostruzione», parte C), e che la correzione di chi parla su un nome vale subito.
C. Dal 16/10 (issue #134, chi parla da solo): la nota vale per le sole righe della stanza, non
   per la frase di chi parla adesso (presa com'è; un nome che non si conosce si ripete o si
   chiede, mai sostituito), senza una formula di risposta da ripetere («mi è sembrato…»), e la
   correzione vale per il resto della conversazione; la nota resta ferma nel prefisso (una volta,
   nel primo pezzo, uguale a ogni turno: cache #95), con una voce sola e con due. Anche le
   frasi della domanda insistita (INSISTE_MSG, RIPETUTA_NUDGE_INSISTE) senza «sembrato».
D. Il conteggio del caso `da_solo` del banco (prove/manuali/banco_stanza_storpiata.py, 16/10,
   #134) su risposte finte: il nome sentito ripetuto o chiesto, un terzo nome («Borgoletto»,
   «Borgolietti») contato, un «?» qualsiasi non è una domanda sul nome, la forma corretta solo
   al turno 3 non basta.
B. La domanda che riprende quella di prima dopo una risposta lunga (rete `domanda_insistita`,
   calliope/ripetizione.py): una frase condizionale nei dati del turno (INSISTE_MSG, regola
   `domanda_insistita`) e, se la risposta è di nuovo uguale, la spinta senza «una cosa nuova»
   (RIPETUTA_NUDGE_INSISTE). Contrari: domanda d'altro, risposta breve, il seguito su un'altra
   città, rete spenta, la sola rete risposta_ripetuta spenta.

Niente rete: backend finto."""

import time

from calliope.brain import Brain
from calliope.config import RETI, Config
from calliope.ripetizione import (INSISTE_MSG, RIPETUTA_NUDGE, RIPETUTA_NUDGE_INSISTE,
                                  domanda_simile, insiste, piene)
from calliope.stanza import contesto as ctx_mod
from calliope.tools.builtin import build_registry

errori = 0


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""))


# ─────────────────────────── A. le righe storpiate ───────────────────────────
class RegistroFinto:
    def __init__(self, righe):
        self._r = righe

    def righe(self, dal=None):
        return list(self._r)

    def riassunto(self):
        return None


class StanzaFinta:
    def __init__(self, righe):
        self._reg = RegistroFinto(righe)
        self._info = {1: {"nome": "auto", "stanza": "auto"}}
        self.registry = None

    def accesa_qui(self, sat):
        return True

    def registro(self, sat):
        return self._reg

    def presenti(self, sat):
        return []


RIGHE_AUTO = ["regionali GRS 2.300, nazionali GRS 2.300.", "2023 BRONDO, coppa GRS 2024 AR.",
              "c'è nazionale bronzo i nazionali"]


def prova_righe():
    ora = time.time()
    righe = [{"seq": i + 1, "segmento": i + 1, "inizio": ora - 120 + i * 10,
              "fine": ora - 116 + i * 10, "testo": t, "chi": "persona:Carlo", "nome": "Carlo",
              "sicurezza": "voce"} for i, t in enumerate(RIGHE_AUTO)]
    cfg = Config()
    cfg.stanza_contesto = True
    st = StanzaFinta(righe)
    b = ctx_mod.costruisci(st, 1, cfg, ora)
    verifica("blocco: le righe sono trascrizione storpiata da ricostruire con prudenza",
             b is not None and ctx_mod.STORPIATE in b.testo
             and "è una tua ricostruzione" in b.testo
             and "invece di dire che non è stato detto" in b.testo)
    verifica("blocco: la nota è di Calliope, fuori dalla busta e prima",
             b.testo.startswith(ctx_mod.STORPIATE + "\n[DATO NON FIDATO (fonte: stanza)")
             and b.testo.count("trascritte da un riconoscimento vocale") == 1)
    verifica("blocco: la correzione di chi parla vale da subito",
             "vale la sua forma da subito" in b.testo)
    verifica("blocco: le righe restano com'erano, in busta (niente corretto dal codice)",
             all(t in b.testo.split("<<<", 1)[1] for t in RIGHE_AUTO))
    p1 = ctx_mod.pezzo(b, set(), cfg, 1, primo=True)
    verifica("primo pezzo nella storia: la stessa nota, fuori dalla busta",
             p1 is not None
             and p1.testo.startswith(ctx_mod.STORPIATE + "\n[DATO NON FIDATO (fonte: stanza)")
             and "Altre righe arriveranno" in p1.testo)
    p2 = ctx_mod.pezzo(b, set(), cfg, 2, primo=False)
    verifica("pezzi dopo: niente nota (resta nel prefisso), solo «storpiate» nell'intestazione",
             p2 is not None and "parole spesso storpiate" in p2.testo
             and ctx_mod.STORPIATE not in p2.testo
             and p2.testo.startswith("[DATO NON FIDATO (fonte: stanza)"))
    verifica("gli esempi non sono le parole del banco (argento, oro, 2025)",
             not any(w in ctx_mod.STORPIATE.lower() for w in ("argento", " oro", "2025")))
    con = Config().prompt_for(False, stanza=True)
    senza = Config().prompt_for(False, stanza=False)
    verifica("prompt con stanza_cerca: storpiature e correzione del nome",
             "parole storpiate" in con and "corregge un nome usa il suo da subito" in con)
    verifica("contrario: prompt senza la stanza non ne parla", "storpiate" not in senza)


# ──────────────── C. il perimetro della nota: chi parla da solo (16/10, issue #134) ────────────────
# Caso vero (prove a voce sulla DGX col 26B, chi amministra da solo dal telefono, stanza accesa;
# qui di fantasia): «Oggi vado in palestra.» → «Mi è sembrato di sentire che oggi vai in
# palestra…»; «Borgo Lieto» trascritto «Borgolieti» nella frase del turno → un terzo nome
# «ricostruito», ripetuto anche dopo la correzione. La nota diceva «mi è sembrato di sentire bronzo
# nel 2023» (una formula) senza dire che valeva per le sole righe della stanza.
RIGHE_SOLO = ["Devo ricordarmi di passare in farmacia."]
DOMANDE_SOLO = ["Calliope, oggi vado in palestra.", "Calliope, quanto dista Borgolieti?",
                "Calliope, no, si dice Borgolieto.", "Calliope, e ci sono negozi a Borgolieto?"]


def _virgolettati(testo):
    """I pezzi tra «» del testo."""
    return [p.split("»", 1)[0] for p in testo.split("«")[1:]]


def prova_perimetro():
    nota = ctx_mod.STORPIATE
    verifica("nota: vale per le sole righe della stanza qui sotto",
             "sole righe della stanza" in nota and "In quelle righe" in nota)
    verifica("nota: non per la frase di chi parla adesso (presa com'è, senza dubbio)",
             "non vale per ciò che chi ti parla ti dice adesso" in nota
             and "lo prendi com'è" in nota)
    verifica("nota: un nome che non conosci si ripete come sentito o si chiede, mai sostituito",
             "come l'hai sentito o chiedi com'è" in nota
             and "senza mai sostituirlo con un altro" in nota)
    verifica("nota: la correzione vale per tutto il resto della conversazione, non si torna "
             "alla propria forma", "per tutto il resto della conversazione" in nota
             and "non tornare alla tua" in nota)
    verifica("nota: niente formula da ripetere («sembrato», nessuna frase di risposta tra «»)",
             "sembrat" not in nota.lower()
             and all(len(v.split()) <= 2 for v in _virgolettati(nota)),
             str(_virgolettati(nota)))
    con = Config().prompt_for(False, stanza=True)
    verifica("prompt con la stanza: solo le righe, non ciò che ti dicono adesso",
             "in quelle righe, non in ciò che ti dicono adesso" in con)
    verifica("prompt con la stanza: correzione per il resto della conversazione, senza "
             "«sembrato»", "per il resto della conversazione" in con and "sembrat" not in con)
    verifica("contrario: prompt senza la stanza non ne parla",
             "ti dicono adesso" not in Config().prompt_for(False, stanza=False))

    # La conversazione a una voce (una riga di Carlo nella stanza, quattro turni) e il contrario
    # con due voci: la nota nel primo pezzo, una volta sola, ferma nel prefisso per tutta la
    # conversazione (la correzione «per il resto della conversazione» resta davanti al modello)
    # senza rompere la cache. La nota resta anche con una voce sola: il punto 3 della issue (nota
    # solo con altre voci) è da fare solo se il banco dice che il perimetro non basta
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import prova_stanza_storia as pss
    for righe, nomi, cosa in ((RIGHE_SOLO, ("Carlo",), "una voce sola"),
                              (RIGHE_AUTO, ("Carlo", "Nicola"), "contrario: due voci")):
        cfg = pss.cfg_base(stanza_contesto_in_storia=True)
        st = pss.nuova_stanza(cfg)
        b = pss.brain(cfg, st)
        t0 = time.time() - 120
        for i, t in enumerate(righe):
            pss.riga(st, 1, t, t0 + i * 10, nomi[i % len(nomi)])
        rotte = []
        for n, d in enumerate(DOMANDE_SOLO):
            if n == 2:                       # una riga nuova a metà: un seguito, senza nota
                pss.riga(st, 1, "Prendo anche il pane.", time.time() - 30, "Carlo")
            b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, time.time())
            "".join(b.stream_reply(d, "amministra"))
            rotte.append(bool((b.last_cache or {}).get("rotta")))
        v = b.backend.visti
        con_n = [[i for i, m in enumerate(r) if nota in str(m.get("content"))] for r in v]
        pos = con_n[0][0] if con_n and con_n[0] else None
        verifica(f"{cosa}: la nota nel primo pezzo, una volta sola, allo stesso posto in ogni "
                 "turno", pos is not None and all(c == [pos] for c in con_n), str(con_n))
        ok = pos is not None and all(
            [(m["role"], m.get("content")) for m in v[i][:pos + 1]]
            == [(m["role"], m.get("content")) for m in v[i - 1][:pos + 1]]
            for i in range(1, len(v)))
        verifica(f"{cosa}: il prefisso fino alla nota uguale byte per byte da un turno "
                 "all'altro, cache mai rotta", ok and not any(rotte), str(rotte))
        seguiti = [m for m in v[-1] if "Altre frasi sentite" in str(m.get("content"))]
        verifica(f"{cosa}: il seguito senza la nota", len(seguiti) == 1
                 and nota not in str(seguiti[0].get("content")), str(len(seguiti)))
        utente = [str(m.get("content")) for m in v[-1] if m["role"] == "user"]
        verifica(f"{cosa}: le frasi dei turni restano com'erano (niente corretto dal codice)",
                 all(any(d in u for u in utente) for d in DOMANDE_SOLO), str(utente[-1:]))

# ─────────────────────────── B. la domanda insistita ───────────────────────────
R = ("Ha menzionato dei risultati relativi ai nazionali GRS 2.300 e alla coppa GRS 2024, ma "
     "non ha specificato altro.")


def storia(domanda, risposta=R):
    return [{"role": "user", "content": domanda}, {"role": "assistant", "content": risposta}]


def prova_forma():
    q1 = "Quali erano questi risultati?"
    q2 = "Ma quali sono questi risultati? Lo hai capito?"
    verifica("caso vero: la domanda riprende la parola piena di prima",
             domanda_simile(q2, q1) and insiste(storia(q1), q2) == R)
    verifica("la stessa domanda uguale", insiste(storia(q1), q1) == R)
    verifica("parole piene: niente articoli, domande, ausiliari, numeri",
             piene("Ma quali sono questi risultati del 2023? Lo hai capito?")
             == {"risultati", "capito"})
    verifica("dopo una risposta con un tool: conta l'ultima risposta detta",
             insiste(storia(q1)[:1] + [{"role": "assistant", "content": "",
                                        "tool_calls": [{}]},
                                       {"role": "tool", "content": "{}"},
                                       {"role": "assistant", "content": R}], q2) == R)
    verifica("contrario: domanda d'altro («e chi ha vinto la gara?»)",
             insiste(storia(q1), "E chi ha vinto la gara?") is None)
    verifica("contrario: il seguito su un'altra città", insiste(storia(
        "Che tempo fa a Roma?", "A Roma oggi è sereno con venti gradi e un po' di vento da "
        "nord."), "E a Milano che tempo fa?") is None)
    verifica("contrario: risposta breve di prima («Fatto.»)",
             insiste(storia("Accendi la luce in cucina", "Fatto."),
                     "Accendi la luce in cucina") is None)
    verifica("contrario: nessun turno prima", insiste([], q2) is None
             and insiste(storia(q1), "") is None)
    verifica("contrario: domande di sole parole vuote diverse («E allora?» / «Cosa?»)",
             insiste(storia("E allora?"), "Cosa?") is None)
    verifica("contrario: la medaglia dopo i risultati (parole piene diverse)",
             insiste(storia(q2), "Sì, ma quale medaglia d'oro, quale d'argento?") is None)


class BackendFinto:
    def __init__(self, risposte=None):
        self.risposte = list(risposte or [])
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        testo = self.risposte.pop(0) if self.risposte else "Va bene."
        yield "text", testo
        yield "usage", {"prompt": 1000, "output": 20}


class Profilo:
    def __init__(self, id, nome):
        self.id, self.name = id, nome
        self.preferred_tone = None


class Speakers:
    def get(self, nome):
        return Profilo("p-carlo", "Carlo") if nome == "Carlo" else None


class SCtx:
    current_speaker = "Carlo"
    current_level = "amministra"
    identified_by = "voce"


class Ctx:
    def __init__(self):
        self.speaker_ctx = SCtx()
        self.speakers = Speakers()
        self.conversazioni = None
        self.turno = 0
        self.user_text = ""
        self.regole = []
        self.memory = None


def brain_finto(risposte):
    cfg = Config()
    cfg.llm_num_ctx = 16384
    b = Brain.__new__(Brain)
    b.cfg, b.tools = cfg, build_registry()
    b.tool_ctx = Ctx()
    b.backend = BackendFinto(risposte)
    b.archivio_conv = None
    b.compressore = None
    b.luogo_fn = lambda: "locale"
    return b


def parla(b, testo):
    return "".join(b.stream_reply(testo, "amministra"))


def sistema(visti):
    return [m.get("content") or "" for m in visti if m["role"] == "system"]


NUOVA = ("Mi è sembrato di sentire bronzo nel 2023 e argento alla coppa del 2024, ma non ne "
         "sono sicura.")


def prova_brain():
    q1, q2 = "Quali erano questi risultati?", "Ma quali sono questi risultati? Lo hai capito?"
    b = brain_finto([R, R, NUOVA])
    parla(b, q1)
    verifica("primo turno: niente insistenza", INSISTE_MSG not in sistema(b.backend.visti[0])
             and "domanda_insistita" not in b.rules_fired())
    detto = parla(b, q2)
    primo, ultimo = b.backend.visti[1], b.backend.visti[-1]
    verifica("caso vero: la frase dell'insistenza nei dati del turno, prima della domanda",
             INSISTE_MSG in sistema(primo)
             and [m.get("content") for m in primo].index(INSISTE_MSG)
             < max(i for i, m in enumerate(primo) if m.get("content") == q2))
    verifica("…regola domanda_insistita nel registro", "domanda_insistita" in b.rules_fired())
    verifica("…la risposta uguale non si dice, spinta senza «una cosa nuova»",
             detto == NUOVA and "spinta_ripetuta" in b.rules_fired()
             and RIPETUTA_NUDGE_INSISTE in sistema(ultimo)
             and RIPETUTA_NUDGE not in sistema(ultimo), detto)
    verifica("…mai nella storia (dato del solo turno)",
             not any(m.get("content") == INSISTE_MSG for m in b.history))
    nomi = [d["nome"] for d in getattr(b, "last_dati_turno", None) or ()]
    verifica("…nei dati del turno col nome «insistenza»", "insistenza" in nomi, str(nomi))

    # Quasi uguale (0,79 sulle parole, sotto la soglia di sempre 0,85): con l'insistenza si
    # trattiene già da SOGLIA_INSISTE (0,7); senza, passa come prima
    R2 = ("Ho capito che ha menzionato dei risultati relativi ai nazionali GRS 2.300 e alla "
          "coppa GRS 2024.")
    b = brain_finto([R, R2, NUOVA])
    parla(b, q1)
    detto = parla(b, q2)
    verifica("con l'insistenza la risposta quasi uguale si trattiene (soglia 0,7)",
             detto == NUOVA and "spinta_ripetuta" in b.rules_fired()
             and RIPETUTA_NUDGE_INSISTE in sistema(b.backend.visti[-1]), detto)
    b = brain_finto([R, R2])
    parla(b, q1)
    detto = parla(b, "E poi cosa ha detto Bianca?")
    verifica("contrario: senza l'insistenza la quasi uguale passa (soglia di sempre)",
             detto == R2 and "spinta_ripetuta" not in b.rules_fired()
             and len(b.backend.visti) == 2, detto)

    b = brain_finto([R, "Sono le dieci e venti."])
    parla(b, q1)
    parla(b, "Che ore sono?")
    verifica("contrario: una domanda d'altro, niente frase né regola",
             INSISTE_MSG not in sistema(b.backend.visti[-1])
             and "domanda_insistita" not in b.rules_fired())

    b = brain_finto([R, R])
    b.cfg.llm_reti_spente = ["domanda_insistita"]
    parla(b, q1)
    parla(b, q2)
    visti = b.backend.visti
    verifica("contrario: rete spenta → niente frase; la spinta della ripetuta è quella di prima",
             all(INSISTE_MSG not in sistema(v) for v in visti)
             and "domanda_insistita" not in b.rules_fired()
             and RIPETUTA_NUDGE in sistema(visti[-1]))

    b = brain_finto([R, R])
    parla(b, q1)
    detto = parla(b, q1)
    verifica("la stessa domanda uguale: la frase c'è, ma la risposta uguale si dice (come prima)",
             INSISTE_MSG in sistema(b.backend.visti[-1]) and detto == R
             and len(b.backend.visti) == 2 and "spinta_ripetuta" not in b.rules_fired())


def prova_config():
    verifica("rete domanda_insistita fra quelle del modello (si spegne dal profilo)",
             "domanda_insistita" in RETI and RETI["domanda_insistita"].categoria == "modello")
    verifica("accesa di serie", Config().rete("domanda_insistita"))
    verifica("domanda insistita: niente formula «sembrato di sentirlo» (16/10, #134)",
             "sembrat" not in INSISTE_MSG and "sembrat" not in RIPETUTA_NUDGE_INSISTE
             and "ricostruzione" in INSISTE_MSG and "ricostruzione" in RIPETUTA_NUDGE_INSISTE)


def prova_conteggio_banco():
    import importlib.util
    qui = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "banco_stanza_storpiata", os.path.join(qui, "manuali", "banco_stanza_storpiata.py"))
    bn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bn)
    chiara = "Buon allenamento con Marta!"
    giusto = "Borgolieto è vicino al lago, ci vuole mezz'ora."
    seguito = "Da Borgolieto la strada costeggia il lago."
    e = bn.esito_solo([chiara, "Non so dove sia Borgolieti, vuoi che cerchi?", giusto, seguito])
    verifica("banco: la forma sentita ripetuta, poi quella di Carlo in ogni turno",
             e["nome_t2"] and not e["terzo_t2"] and e["corretto"] and not e["altra_forma"]
             and not e["senza_nome"] and e["sembra"] == 0, str(e))
    e = bn.esito_solo([chiara, "Intendi forse Borgoletto, vicino al lago?", giusto, seguito])
    verifica("banco: un terzo nome al turno 2 («Borgoletto») non è «ripetuto o chiesto»",
             not e["nome_t2"] and e["terzo_t2"], str(e))
    e = bn.esito_solo([chiara, "Non conosco quel posto. Vuoi che cerchi la strada?", giusto,
                       seguito])
    verifica("banco: un «?» qualsiasi non è una domanda sul nome", not e["nome_t2"], str(e))
    e = bn.esito_solo([chiara, "Come si scrive il nome del paese?", giusto, seguito])
    verifica("banco: chiedere com'è il nome vale", e["nome_t2"], str(e))
    e = bn.esito_solo([chiara, "Borgolieti? Non lo conosco.", giusto,
                       "Da Borgolietti la strada sale."])
    verifica("banco: un terzo nome dopo la correzione («Borgolietti») è un'altra forma",
             e["altra_forma"] and not e["corretto"], str(e))
    e = bn.esito_solo([chiara, "Borgolieti? Non lo conosco.", giusto,
                       "La strada costeggia il lago."])
    verifica("banco: la forma corretta solo al turno 3 non basta",
             not e["corretto"] and e["senza_nome"] and not e["altra_forma"], str(e))
    e = bn.esito_solo(["Mi è sembrato di sentire che vai in palestra.", "Borgolieti?", giusto,
                       "Da Borgo Lieto la strada costeggia un borgo vicino."])
    verifica("banco: «sembrato» sulla frase chiara; «Borgo Lieto» staccato è la forma di Carlo, "
             "un «borgo» minuscolo no", e["sembra_t1"] and e["corretto"]
             and not e["altra_forma"], str(e))


prova_righe()
prova_perimetro()
prova_forma()
prova_brain()
prova_config()
prova_conteggio_banco()
print(f"\n{errori} errori" if errori else "\nTutto bene")
sys.exit(1 if errori else 0)
