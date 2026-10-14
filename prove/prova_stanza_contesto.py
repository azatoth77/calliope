"""
Prova a secco del passo 2 della conversazione di stanza (14/10/2026, decisione 0029, progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.5, § 3.5 bis, § 3.11, § 6): il blocco
della stanza nei dati del turno, la copertura all'interpellazione, il giudizio «rivolta» con le
righe della stanza, la frase non rivolta che resta nella stanza.

- il blocco (calliope/stanza/contesto.py): righe in ordine, con chi le ha dette («Carlo»,
  «Carlo?» in zona grigia, «voce non riconosciuta», «→ Calliope», «Calliope»), in busta come dato
  non fidato (fonte «stanza»), senza la frase del turno stesso; gli ultimi `stanza_caldo_sempre_s`
  sempre per intero anche oltre il tetto, il resto dalla più nuova finché sta nel tetto, niente
  oltre `stanza_caldo_min`; i contrari: spento, in pausa («abbiamo ospiti»), nessuna riga,
  «dimentica», stanza non accesa su quel satellite;
- la copertura: il recupero delle righe ancora in coda aspettato al più `stanza_recupero_max_s`,
  `nel_contesto` e `scartate`, la nota «non ancora trascritte» oltre il tetto;
- Brain: il blocco nei dati del turno (dopo la storia, prima della frase), mai nella storia, nel
  registro solo nome e lunghezza; la politica lo vede come dato non fidato (un bersaglio preso
  dalla stanza non si esegue senza chiedere, uno detto nella frase sì);
- il ciclo: il blocco prima della risposta con i numeri nel registro dei turni, la frase ignorata
  che resta nella stanza con «rivolta: no», la risposta detta come riga di Calliope (una volta);
- il giudizio «rivolta» con le righe della stanza (e senza righe i messaggi di prima);
- la sezione «Stanza» di `calliope stato --turni` con il blocco, la copertura e i tempi con e
  senza blocco; la configurazione (di serie spento).

Nomi di fantasia (Carlo amministra, Nicola ha 14 anni, Bianca è un'amica). ~2 s.
"""

import os
import sys
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import politica as pol
from calliope import provenienza as prov
from calliope import rivolta as rivolta_mod
from calliope import valore
from calliope.brain import Brain
from calliope.config import Config
from calliope.conversazione import Conversazione
from calliope.stanza import contesto as ctx_mod
from calliope.stanza import misure as misure_mod
from calliope.stanza.ascolto import Segmento, Stanza

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


class STTFinto:
    def transcribe(self, audio, **k):
        return ""


class Prof:
    def __init__(self, pid, name, nascita=None):
        self.id, self.name, self.nascita = pid, name, nascita
        self.admin = name == "Carlo"
        self.tutori = []
        self.fascia = self.preferred_voice = self.tono = self.preferred_tone = None


class Voci:
    P = {"Carlo": Prof("carlo-id", "Carlo"), "Nicola": Prof("nicola-id", "Nicola", "2012-05-01"),
         "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.P.get(n)

    def known_speakers(self):
        return list(self.P)


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza = "ombra"
    c.stanza_contesto = True
    for a, v in k.items():
        setattr(c, a, v)
    return c


def stanza_con(cfg, sat=1, nome="cucina"):
    st = Stanza(cfg, STTFinto(), registry=Voci(), log=lambda m: None)
    st._info[sat] = {"nome": nome, "stanza": nome, "canale": "satellite"}
    return st


def riga(st, sat, testo, fa_s, nome=None, sicurezza="voce", rivolta="ignoto", segmento=None,
         ora=None, durata=2.0):
    ora = time.time() if ora is None else ora
    return st.registro(sat).aggiungi(
        "riga", segmento=segmento, versione=1, inizio=round(ora - fa_s - durata, 3),
        fine=round(ora - fa_s, 3), testo=testo, chi=f"persona:{nome}" if nome else "ignoto",
        nome=nome, sicurezza=sicurezza if nome else "nessuna", p_min=None, rivolta=rivolta,
        minore=nome == "Nicola").seq


# ─────────────────────────── 1. il blocco ───────────────────────────
def prova_blocco():
    cfg = cfg_base()
    st = stanza_con(cfg)
    ora = time.time()
    riga(st, 1, "Hai preso il caricabatterie?", 40, "Carlo", ora=ora)
    riga(st, 1, "Sì, è nello zaino.", 35, "Nicola", ora=ora)
    riga(st, 1, "Domenica andiamo in bici?", 30, "Carlo", sicurezza="grigia", ora=ora)
    riga(st, 1, "Volentieri, se non piove.", 25, None, ora=ora)
    riga(st, 1, "Calliope, che tempo fa domenica?", 20, "Carlo", rivolta="si", ora=ora)
    st.detto(1, "Domenica sole, massime di diciannove gradi.", ora - 18, ora - 16)
    riga(st, 1, "Calliope, tu che ne pensi?", -2.0, "Bianca", rivolta="si", ora=ora)
    b = ctx_mod.costruisci(st, 1, cfg, ora)
    testo = b.testo if b else ""
    verifica("blocco: c'è, in busta come dato non fidato (fonte «stanza»)",
             b is not None and "DATO NON FIDATO (fonte: stanza)" in testo
             and prov.fonti([{"content": testo}]) == {"stanza"}, testo[:200])
    ordine = [testo.find(x) for x in ("Carlo: Hai preso", "Nicola: Sì, è nello",
                                      "Carlo?: Domenica andiamo",
                                      "voce non riconosciuta: Volentieri",
                                      "Carlo → Calliope: Calliope, che tempo",
                                      "Calliope: Domenica sole")]
    verifica("blocco: righe nell'ordine, con chi le ha dette (voce, zona grigia, sconosciuta, "
             "rivolta a Calliope, Calliope)", all(i >= 0 for i in ordine)
             and ordine == sorted(ordine), str(ordine))
    verifica("blocco: la frase del turno stesso non c'è (è la domanda)",
             "tu che ne pensi" not in testo and b.righe == 6, str(b.righe))
    verifica("blocco: intestazione con la stanza e i presenti riconosciuti dalla voce",
             "«cucina»" in testo and "trascrizione automatica" in testo)
    verifica("blocco: nel registro solo numeri", set(b.per_registro()) <= {
        "righe", "sempre", "tagliate", "caratteri", "mancano"}
             and all(isinstance(v, int) for v in b.per_registro().values()))
    verifica("blocco: per la provenienza le sole parole delle persone (non quelle di Calliope)",
             "zaino" in b.esterno and "diciannove" not in b.esterno)
    # Presenti: Carlo e Nicola riconosciuti dalla voce (il minore segnato)
    st._sentita("carlo-id", "Carlo", 1, time.time())
    st._sentita("nicola-id", "Nicola", 1, time.time())
    b2 = ctx_mod.costruisci(st, 1, cfg, ora)
    verifica("blocco: i presenti con il minore segnato",
             "presenti riconosciuti dalla voce: Carlo, Nicola (minorenne)" in b2.testo,
             b2.testo[:400])
    # Rivolta: una frase segnata «no» perde la freccia
    seq = riga(st, 1, "Calliope accendi la radio", 10, "Nicola", rivolta="si", ora=ora)
    st.segna_rivolta(1, seq, "no", False)
    b3 = ctx_mod.costruisci(st, 1, cfg, ora)
    verifica("blocco: la frase non rivolta resta nella stanza, senza «→ Calliope»",
             "Nicola: Calliope accendi la radio" in b3.testo
             and "Nicola → Calliope: Calliope accendi" not in b3.testo)
    st.chiudi()


def prova_contrari():
    ora = time.time()
    cfg = cfg_base(stanza_contesto=False)
    st = stanza_con(cfg)
    riga(st, 1, "Hai preso il caricabatterie?", 10, "Carlo", ora=ora)
    verifica("contrario: `stanza_contesto: false` → nessun blocco",
             ctx_mod.costruisci(st, 1, cfg, ora) is None)
    cfg.stanza_contesto = True
    verifica("…acceso → il blocco c'è", ctx_mod.costruisci(st, 1, cfg, ora) is not None)
    st.pausa(1, "ospiti", 240)
    verifica("contrario: in pausa («abbiamo ospiti») → nessun blocco",
             ctx_mod.costruisci(st, 1, cfg, ora) is None)
    st.riprendi(1)
    verifica("…ripresa → di nuovo", ctx_mod.costruisci(st, 1, cfg, ora) is not None)
    st.dimentica(1)
    verifica("contrario: dopo «dimentica» → nessun blocco",
             ctx_mod.costruisci(st, 1, cfg, ora) is None)
    vuota = stanza_con(cfg, 2, "studio")
    verifica("contrario: nessuna riga → nessun blocco", ctx_mod.costruisci(vuota, 2, cfg, ora)
             is None)
    riga(vuota, 2, "Calliope, che ore sono?", -2.0, "Carlo", rivolta="si", ora=ora)
    verifica("contrario: c'è solo la frase del turno → nessun blocco",
             ctx_mod.costruisci(vuota, 2, cfg, ora) is None)
    verifica("contrario: satellite sconosciuto alla stanza → nessun blocco",
             ctx_mod.costruisci(vuota, 99, cfg, ora) is None)
    cfg.stanza_satelliti = ["cucina"]
    riga(vuota, 2, "Che bella giornata.", 5, "Carlo", ora=ora)
    verifica("contrario: satellite fuori da `stanza_satelliti` → nessun blocco",
             ctx_mod.costruisci(vuota, 2, cfg, ora) is None)
    st.chiudi()
    vuota.chiudi()


def prova_tetto():
    ora = time.time()
    cfg = cfg_base(stanza_caldo_caratteri=200, stanza_caldo_sempre_s=45.0, stanza_caldo_min=8.0)
    st = stanza_con(cfg)
    riga(st, 1, "Una frase di dieci minuti fa, fuori dalla finestra.", 600, "Carlo", ora=ora)
    for i in range(10):
        riga(st, 1, f"Frase vecchia numero {i} della chiacchierata di prima.", 300 - i * 20,
             "Nicola", ora=ora)
    recenti = [f"Recente {i}: una frase detta da poco, lunga abbastanza da pesare sul tetto."
               for i in range(4)]
    for i, t in enumerate(recenti):
        riga(st, 1, t, 40 - i * 10, "Carlo", ora=ora)
    b = ctx_mod.costruisci(st, 1, cfg, ora)
    righe = [r for r in b.testo.splitlines() if " Carlo: " in r or " Nicola: " in r]
    verifica("tetto: gli ultimi 45 s sempre, per intero, anche oltre il tetto",
             all(t in b.testo for t in recenti) and b.sempre == 4 and b.caratteri > 200,
             f"sempre {b.sempre}, caratteri {b.caratteri}")
    verifica("tetto: le più vecchie fuori (contate), nessuna oltre `stanza_caldo_min`",
             b.tagliate > 0 and "dieci minuti fa" not in b.testo
             and "numero 0 " not in b.testo, f"tagliate {b.tagliate}")
    cfg.stanza_caldo_caratteri = 2000
    b2 = ctx_mod.costruisci(st, 1, cfg, ora)
    numeri = [int(r.split("numero ")[1].split()[0]) for r in b2.testo.splitlines()
              if "numero " in r]
    verifica("tetto: con più spazio entrano dalla più nuova all'indietro, senza buchi e in "
             "ordine", numeri == sorted(numeri) and numeri and numeri[-1] == 9
             and numeri == list(range(numeri[0], 10)) and b2.tagliate < b.tagliate,
             str(numeri))
    verifica("tetto: le righe del blocco restano in ordine di tempo",
             [r.split(" ", 1)[0] for r in righe] == sorted(r.split(" ", 1)[0] for r in righe))
    st.chiudi()


# ─────────────────────────── 2. la copertura ───────────────────────────
def segmento(st, sat, ident, fine_fa, stato="fatto", esito="riga"):
    ora = time.monotonic()
    s = Segmento(sat, "cucina", "satellite", ident, ora - fine_fa - 2)
    s.fine, s.chiuso, s.stato, s.esito = ora - fine_fa, ora - fine_fa + 0.5, stato, esito
    s.fatto = ora if stato == "fatto" else None
    import collections
    st._recenti.setdefault(sat, collections.deque()).append(s)
    return s


def prova_copertura():
    cfg = cfg_base(stanza_recupero_max_s=1.5)
    st = stanza_con(cfg)
    ora_m, ora = time.monotonic(), time.time()
    segmento(st, 1, 1, 10)
    riga(st, 1, "Hai preso il caricabatterie?", 10, "Carlo", segmento=1, ora=ora)
    segmento(st, 1, 2, 8, esito="vuota")
    lento = segmento(st, 1, 3, 3, stato="in_coda", esito=None)
    cop = st.copertura(1, ora_m)
    verifica("copertura: alla domanda una riga ancora in coda", cop.mancano() == 1
             and cop.dette == 3 and lento.recupero)

    def finisci():
        time.sleep(0.2)
        riga(st, 1, "Sì, è nello zaino.", 3, "Nicola", segmento=3, ora=ora)
        with st._cond:
            lento.stato, lento.esito, lento.fatto = "fatto", "riga", time.monotonic()
            st._cond.notify_all()
    threading.Thread(target=finisci, daemon=True).start()
    attesa = cop.aspetta(cop.t0 + 1.5)
    b = ctx_mod.costruisci(st, 1, cfg, ora, mancano=cop.mancano())
    cop.nel_blocco(b.segmenti)
    d = cop.a_dict()
    verifica("copertura: il recupero aspettato prima del blocco, poi tutte nel contesto",
             150 <= attesa < 1400 and d["nel_contesto"] == 2 and d["scartate"] == 1
             and d["dette"] == 3 and "zaino" in b.testo and ctx_mod.NON_TRASCRITTE not in b.testo,
             f"attesa {attesa} {d}")
    # Contrario: un segmento che non finisce entro il tetto → la nota nel blocco
    st2 = stanza_con(cfg, 2)
    segmento(st2, 2, 1, 6)
    riga(st2, 2, "Allora domenica si va.", 6, "Nicola", segmento=1, ora=ora)
    segmento(st2, 2, 2, 2, stato="in_coda", esito=None)
    cop2 = st2.copertura(2, time.monotonic())
    t0 = time.monotonic()
    cop2.aspetta(cop2.t0 + 0.3)
    b2 = ctx_mod.costruisci(st2, 2, cfg, ora, mancano=cop2.mancano())
    cop2.nel_blocco(b2.segmenti)
    d2 = cop2.a_dict()
    verifica("copertura, contrario: oltre il tetto si risponde con ciò che c'è e il blocco lo "
             "dice", time.monotonic() - t0 < 0.8 and ctx_mod.NON_TRASCRITTE in b2.testo
             and d2["nel_contesto"] == 1 and d2["in_coda"] == 1 and b2.mancano == 1, str(d2))
    st.chiudi()
    st2.chiudi()


# ─────────────────────────── 3. Brain e la politica ───────────────────────────
class Backend:
    def __init__(self):
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield ("text", "Secondo me è una buona idea.")


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "amministra", "voce"
    compagnia = compagnia_sconosciute = False


def brain():
    from calliope.tools.builtin import build_registry
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = Config(), build_registry(), []
    b.conv = Conversazione("persona:carlo-id")
    b.tool_ctx = type("T", (), {"speaker_ctx": Chi(), "speakers": Voci()})()
    b.backend = Backend()
    return b


def prova_brain():
    cfg = cfg_base()
    st = stanza_con(cfg)
    ora = time.time()
    riga(st, 1, "Nella taverna c'è il cancello del garage aperto.", 20, "Nicola", ora=ora)
    riga(st, 1, "Domenica andiamo in bici al lago?", 10, "Carlo", ora=ora)
    blocco = ctx_mod.costruisci(st, 1, cfg, ora)
    b = brain()
    "".join(b.stream_reply("Ciao, come va?", "amministra"))
    b.stanza_turno = blocco
    r = "".join(b.stream_reply("Tu che ne pensi?", "amministra"))
    visti = b.backend.visti[-1]
    i_stanza = next((i for i, m in enumerate(visti) if "fonte: stanza" in str(m.get("content"))),
                    None)
    i_domanda = max(i for i, m in enumerate(visti) if m.get("role") == "user")
    i_prima = next(i for i, m in enumerate(visti) if m.get("content") == "Ciao, come va?")
    verifica("Brain: il blocco nei dati del turno, dopo la storia e prima della frase",
             r and i_stanza is not None and i_prima < i_stanza < i_domanda,
             f"{i_prima} {i_stanza} {i_domanda}")
    verifica("Brain: regola `stanza_contesto` e nei dati del turno solo nome e lunghezza",
             "stanza_contesto" in b.last_rules and any(
                 d["nome"] == "stanza" and d["caratteri"] > 0 for d in b.last_dati_turno)
             and all(set(d) == {"nome", "caratteri"} for d in b.last_dati_turno))
    verifica("Brain: il blocco non entra nella storia",
             not any("fonte: stanza" in str(m.get("content")) for m in b.history))
    # La politica: la stanza è un dato non fidato di questo turno
    t = b._turno_politica()
    verifica("politica: con il blocco la conversazione ha la fonte «stanza» e le sue parole",
             "stanza" in t.contaminazione and any(f == "stanza" and "cancello" in x
                                                  for f, x in t.esterni))
    from calliope.tools.spec import ToolContext
    tctx = ToolContext(cfg=b.cfg, speakers=Voci(), speaker_ctx=Chi(), speaker=None)

    def decidi(nome, args, turno):
        cl = pol.classe_di(nome)
        base = pol.decidi(nome, args, cl, valore.copia_turno(turno), True, True)
        nuova, _ = valore.decidi_valore(nome, args, cl, turno, base, True, True, None, tctx,
                                        None, ())
        return nuova
    d = decidi("casa_comando", {"comando": "apri il cancello del garage"},
               pol.Turno(testo="Calliope, fallo tu", contaminazione=t.contaminazione,
                         persona_txt=t.persona_txt, esterni=t.esterni, persona="carlo-id"))
    verifica("politica: un bersaglio preso solo dalla stanza non si esegue senza chiedere",
             d.esito != "esegui", str(d))
    d = decidi("casa_comando", {"comando": "accendi la luce in cucina"},
               pol.Turno(testo="Calliope, accendi la luce in cucina",
                         contaminazione=t.contaminazione, persona_txt=t.persona_txt,
                         esterni=t.esterni, persona="carlo-id"))
    verifica("politica, contrario: il bersaglio detto nella frase si esegue",
             d.esito == "esegui", str(d))
    # Contrario: il turno dopo senza blocco → niente stanza, né nei messaggi né per la politica
    "".join(b.stream_reply("Grazie.", "amministra"))
    visti = b.backend.visti[-1]
    verifica("Brain, contrario: senza blocco (vale una risposta sola) niente stanza",
             not any("fonte: stanza" in str(m.get("content")) for m in visti)
             and "stanza" not in b._turno_politica().contaminazione
             and "stanza_contesto" not in b.last_rules)
    st.chiudi()


# ─────────────────────────── 4. il ciclo ───────────────────────────
def finto_ciclo(cfg, st, sat=4, said=None):
    from calliope.ciclo import Ciclo, Servizi
    s = Servizi(cfg)
    s.stanza, s.registry = st, Voci()
    scritti = []
    s.turns = SimpleNamespace(write=scritti.append)
    coll = SimpleNamespace(satellite={"id": sat})
    ora = time.monotonic()
    finto = SimpleNamespace(s=s, corsia=SimpleNamespace(satellite_id=None), ombra=None,
                            listener=SimpleNamespace(_ultima=(coll, 9), started_at=ora - 2.0,
                                                     ended_at=ora - 0.5),
                            rec={"voce": {"nome": "Carlo", "modo": "voce"}}, _turno=None)
    for nome in ("_stanza_dove", "_stanza_inizio_epoch", "_stanza_blocco", "_stanza_esito",
                 "_stanza_copertura", "_stanza_turno", "_stanza_righe_rivolta"):
        setattr(finto, nome, getattr(Ciclo, nome).__get__(finto))
    return finto, scritti


def prova_ciclo():
    from calliope.ciclo import Ciclo, Turno
    cfg = cfg_base()
    st = stanza_con(cfg, 4, "studio")
    riga(st, 4, "Domenica andiamo in bici al lago?", 8, "Carlo")
    riga(st, 4, "Sì, ma partiamo presto.", 5, "Nicola")
    finto, scritti = finto_ciclo(cfg, st)
    t = Turno()
    t.scritto, t.text = None, "Calliope, tu che ne pensi?"
    finto._turno = t
    finto._stanza_copertura(t)
    finto._stanza_turno(t)
    b = finto._stanza_blocco(t)
    verifica("ciclo: il blocco prima della risposta, senza la frase del turno",
             b is not None and "partiamo presto" in b.testo and "tu che ne pensi" not in b.testo
             and finto.rec["stanza"]["contesto"]["righe"] == 2, str(finto.rec.get("stanza")))
    t.said = ["Il lago è una bella idea.", "Partite presto davvero."]
    rec = dict(finto.rec)
    Ciclo._scrivi_turno(finto, rec)
    w = scritti[-1]["stanza"]
    verifica("ciclo: nel registro dei turni copertura e blocco in numeri",
             w["copertura"].get("nel_contesto") == 0 and w["contesto"]["righe"] == 2
             and not any(isinstance(v, str) for v in w["contesto"].values()), str(w))
    ultime = st.registro(4).righe()
    verifica("ciclo: la risposta detta entra nella stanza come riga di Calliope",
             ultime[-1]["chi"] == "calliope" and "bella idea" in ultime[-1]["testo"]
             and ultime[-2]["rivolta"] == "si")
    Ciclo._scrivi_turno(finto, dict(finto.rec))
    verifica("ciclo: una volta per turno (un altro registro non la ripete)",
             sum(r["chi"] == "calliope" for r in st.registro(4).righe()) == 1)
    # Frase ignorata (senza il nome, fuori dalla finestra): resta nella stanza con «no»
    t2 = Turno()
    t2.scritto, t2.text = None, "Passami il sale."
    finto._turno, finto.rec = t2, {"voce": {"nome": "Nicola", "modo": "voce"}}
    finto._stanza_turno(t2)
    Ciclo._scrivi_turno(finto, {"esito": "ignorato", "testo": None})
    r2 = [r for r in st.registro(4).righe() if r.get("testo") == "Passami il sale."]
    verifica("ciclo: la frase ignorata resta nella stanza, «rivolta: no», senza risposta",
             r2 and r2[-1]["rivolta"] == "no"
             and sum(r["chi"] == "calliope" for r in st.registro(4).righe()) == 1)
    # Contrari: spento → niente blocco né «contesto»; scritto → niente
    cfg.stanza_contesto = False
    t3 = Turno()
    t3.scritto, t3.text = None, "Calliope, che ore sono?"
    finto.rec = {}
    verifica("ciclo, contrario: `stanza_contesto: false` → niente blocco, niente numeri",
             finto._stanza_blocco(t3) is None and "contesto" not in finto.rec.get("stanza", {}))
    cfg.stanza_contesto = True
    t3.scritto = {"schermo": "tablet"}
    verifica("ciclo, contrario: frase scritta → niente blocco", finto._stanza_blocco(t3) is None)
    st.pausa(4, "ospiti", 240)
    t3.scritto = None
    verifica("ciclo, contrario: in pausa → niente blocco", finto._stanza_blocco(t3) is None)
    st.chiudi()


# ─────────────────────────── 5. il giudizio «rivolta» ───────────────────────────
def prova_rivolta():
    conv = [("Carlo (registrato)", "Che tempo fa domani?"), ("Calliope", "Sole.")]
    prima = rivolta_mod.messaggi(conv, "Allora andiamo al lago.")
    verifica("rivolta, contrario: senza righe della stanza i messaggi di prima",
             rivolta_mod.STANZA_TITOLO not in prima[1]["content"]
             and prima[1]["content"].startswith("Carlo (registrato): Che tempo"))
    stanza = [("Nicola", "Papà, domenica andiamo al lago?"), ("Carlo", "Vediamo che tempo fa.")]
    con = rivolta_mod.messaggi(conv, "Allora andiamo al lago.", stanza)
    c = con[1]["content"]
    verifica("rivolta: con la stanza le righe (con chi parlava) prima degli scambi",
             c.index(rivolta_mod.STANZA_TITOLO) < c.index("Nicola: Papà")
             < c.index(rivolta_mod.CONVERSAZIONE_TITOLO) < c.index("Frase nuova")
             and con[0]["content"] == rivolta_mod.PROMPT)
    visti = []
    g = rivolta_mod.Giudice(Config(), chiama=lambda m, to: (visti.append(m),
                                                             '{"per_calliope": false}')[1])
    esito = g.giudica(conv, "Allora andiamo al lago.", stanza=stanza)
    verifica("rivolta: il giudice riceve le righe della stanza", esito.per_calliope is False
             and "Nicola: Papà" in visti[-1][1]["content"])
    # Il ciclo prende le righe solo con `stanza_contesto`
    cfg = cfg_base()
    st = stanza_con(cfg, 4, "studio")
    riga(st, 4, "Papà, domenica andiamo al lago?", 6, "Nicola")
    finto, _ = finto_ciclo(cfg, st)
    righe = finto._stanza_righe_rivolta()
    cfg.stanza_contesto = False
    verifica("rivolta: dal ciclo le righe della stanza solo con `stanza_contesto` (contrario)",
             righe == [("Nicola", "Papà, domenica andiamo al lago?")]
             and finto._stanza_righe_rivolta() == [], str(righe))
    st.chiudi()


# ─────────────────────────── 6. misure e configurazione ───────────────────────────
def prova_misure():
    turni = [
        {"stanza": {"contesto": {"righe": 4, "caratteri": 300, "sempre": 2, "tagliate": 0},
                    "copertura": {"dette": 3, "pronte": 2, "recupero_ms": 120,
                                  "nel_contesto": 2, "scartate": 1, "attesa_ms": 120}},
         "prima_frase_s": 1.35, "cache": {"riletti": 420}},
        {"stanza": {"contesto": {"righe": 0}, "copertura": {"dette": 0, "pronte": 0,
                                                             "recupero_ms": 0}},
         "prima_frase_s": 1.2, "cache": {"riletti": 60}},
        {"prima_frase_s": 1.1},
    ]
    r = misure_mod.riassunto([], turni)
    t = misure_mod.testo(r)
    verifica("misure: copertura nel contesto e blocco nella sezione «Stanza»",
             r["copertura"]["tutte"] == 1 and r["blocco"]["turni"] == 1
             and r["blocco"]["vuoti"] == 1 and "Copertura nel contesto" in t
             and "Blocco della stanza" in t, t)
    verifica("misure: prima frase e token riletti con e senza blocco",
             r["tempi"]["blocco"]["prima_p50_s"] == 1.35
             and r["tempi"]["senza_blocco"]["prima_p50_s"] == 1.2
             and r["tempi"]["blocco"]["riletti_p50"] == 420 and "Con il blocco" in t)
    c = Config()
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "calliope.yaml"), encoding="utf-8") as f:
        yaml = f.read()
    verifica("configurazione: `stanza_contesto` di serie spento, nel file d'esempio",
             c.stanza_contesto is False and "stanza_contesto: false" in yaml
             and c.stanza_caldo_sempre_s == 45.0 and "stanza_caldo_caratteri:" in yaml)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prova_blocco()
    prova_contrari()
    prova_tetto()
    prova_copertura()
    prova_brain()
    prova_ciclo()
    prova_rivolta()
    prova_misure()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
