"""
Prova a secco delle righe della stanza nella storia, in sola aggiunta (14/10/2026 sera, dopo la
prova vera in auto: con il blocco della stanza ricostruito a ogni turno la prima frase mediana
era 2,81 s contro 1,3 s senza, ~3900 token riletti per turno col 26B; `stanza_contesto_in_storia`,
calliope/stanza/contesto.py `Pezzo`, Brain `_stanza_prepara`, `_con_stanza`, `_stanza_pota`).

- la cache: su una conversazione finta di 10 turni con righe che arrivano tra un turno e l'altro,
  la richiesta di ogni turno ha come prefisso, byte per byte, quella del turno prima fino alla
  frase di quel turno; i token riletti stimati (`last_cache.riletti_stimati`, il contatore della
  guardia della cache) sono molto meno che col blocco intero a ogni turno (lo stesso giro con
  `stanza_contesto_in_storia: false`); con `--misura` la tabella per turno;
- ogni riga una volta sola, nell'ordine, ogni pezzo subito prima della frase del suo turno, in
  busta (fonte «stanza»); i presenti e le righe non trascritte nei dati del turno, fuori busta;
- mai nella storia, mai su disco: `esporta` senza righe né segno, l'archivio (`turni`) senza righe;
- la politica: le righe dei turni prima restano un dato non fidato (un bersaglio preso da lì
  chiede, uno detto nella frase no);
- i contrari: spento (niente righe), in pausa per ospiti (nascoste, poi tornano uguali),
  «dimentica» (via), il blocco intero con `stanza_contesto_in_storia: false`, il turno tolto dalla
  storia (via anche le sue righe), il tetto (`stanza_storia_caratteri`: via le più vecchie fino a
  metà, una volta, e il prefisso scaldato in secondo piano).

Nomi di fantasia (Carlo amministra, Nicola ha 14 anni). ~1 s.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import politica as pol
from calliope import provenienza as prov
from calliope import valore
from calliope.brain import Brain, _tokens
from calliope.config import Config
from calliope.conversazione import Conversazione, turni
from calliope.stanza import contesto as ctx_mod
from calliope.stanza.ascolto import Stanza

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
    P = {"Carlo": Prof("carlo-id", "Carlo"), "Nicola": Prof("nicola-id", "Nicola", "2012-05-01")}

    def get(self, n):
        return self.P.get(n)

    def known_speakers(self):
        return list(self.P)


class Backend:
    def __init__(self):
        self.visti, self.scaldati = [], []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield ("text", "Va bene, ne terrò conto.")

    def warmup(self, messages, tools):
        self.scaldati.append([dict(m) for m in messages])
        return {"prompt": 100}


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "amministra", "voce"
    compagnia = compagnia_sconosciute = False


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza = "ombra"
    c.stanza_contesto = True
    for a, v in k.items():
        setattr(c, a, v)
    return c


def nuova_stanza(cfg, sat=1, nome="auto"):
    st = Stanza(cfg, STTFinto(), registry=Voci(), log=lambda m: None)
    st._info[sat] = {"nome": nome, "stanza": nome, "canale": "satellite"}
    return st


def brain(cfg, st):
    from calliope.tools.builtin import build_registry
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.conv = Conversazione("persona:carlo-id")
    b.tool_ctx = type("T", (), {"speaker_ctx": Chi(), "speakers": Voci(), "stanza": st})()
    b.backend = Backend()
    return b


def riga(st, sat, testo, inizio, nome=None, durata=3.0, segmento=None):
    return st.registro(sat).aggiungi(
        "riga", segmento=segmento, versione=1, inizio=round(inizio, 3),
        fine=round(inizio + durata, 3), testo=testo, chi=f"persona:{nome}" if nome else "ignoto",
        nome=nome, sicurezza="voce" if nome else "nessuna", p_min=None, rivolta="ignoto",
        minore=nome == "Nicola").seq


FRASI = ["Hai controllato quanta benzina c'è?", "Siamo a metà serbatoio, basta fino a Lucca.",
         "La scuola ha mandato due notifiche sul telefono.", "Una è sul programma della gita.",
         "L'altra riguarda i colloqui di venerdì.", "Allora venerdì esco prima dal lavoro.",
         "Ricordati di comprare il pane.", "Prendo anche le uova al mercato.",
         "Il cancello della taverna è rimasto aperto.", "Ci penso quando torniamo."]
DOMANDE = ["Calliope, quanto manca a Lucca?", "Calliope, a cosa si riferiscono le notifiche?",
           "Calliope, che ore sono?", "Calliope, tu che ne pensi?", "Calliope, grazie.",
           "Calliope, cosa diceva Nicola?", "Calliope, e il programma?",
           "Calliope, a che ora sono i colloqui?", "Calliope, ricordamelo dopo.",
           "Calliope, quanto manca adesso?"]


def giro(in_storia: bool, turni_n: int = 10, righe_per_turno: int = 12, tetto: int = 16000,
         cfg_extra: dict | None = None):
    """Una conversazione finta: a ogni turno `righe_per_turno` righe nuove dette nei due minuti
    prima della domanda, poi la domanda. Restituisce (brain, stanza, misure per turno)."""
    cfg = cfg_base(stanza_contesto_in_storia=in_storia, stanza_storia_caratteri=tetto,
                   **(cfg_extra or {}))
    st = nuova_stanza(cfg)
    b = brain(cfg, st)
    t0 = time.time() - 3600
    out = []
    k = 0
    for n in range(turni_n):
        base = t0 + n * 150
        for j in range(righe_per_turno):
            nome = ("Carlo", "Nicola", None)[j % 3]
            riga(st, 1, f"{FRASI[k % len(FRASI)]} ({n}.{j})", base + j * 10, nome)
            k += 1
        inizio = base + righe_per_turno * 10 + 5
        b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, inizio)
        "".join(b.stream_reply(DOMANDE[n % len(DOMANDE)], "amministra"))
        c = b.last_cache or {}
        # I token riletti della sola stanza: i suoi messaggi dopo il prefisso uguale
        k_ = c.get("prefisso")
        riletti_st = (sum(_tokens(m) for m in _stanza_msgs(b.backend.visti[-1][k_:]))
                      if isinstance(k_, int) else None)
        out.append({"turno": n + 1, "riletti": c.get("riletti_stimati"),
                    "riletti_stanza": riletti_st,
                    "prefisso": c.get("prefisso"), "messaggi": c.get("messaggi"),
                    "rotta": bool(c.get("rotta")), "storia": b.last_stanza_storia})
    return b, st, out


def _stanza_msgs(visti):
    return [m for m in visti if "fonte: stanza" in str(m.get("content"))]


# ─────────────────────────── 1. la cache ───────────────────────────
def prova_cache():
    b, st, dopo = giro(True, tetto=60000)
    _, st2, prima = giro(False)
    riletti_d = [m["riletti"] for m in dopo[1:]]
    riletti_p = [m["riletti"] for m in prima[1:]]
    st_d = [m["riletti_stanza"] for m in dopo[1:]]
    st_p = [m["riletti_stanza"] for m in prima[1:]]
    verifica("cache: in sola aggiunta, i token riletti per turno meno che col blocco intero "
             "(stessa conversazione di 10 turni)", max(riletti_d) < min(riletti_p),
             f"dopo {riletti_d}, prima {riletti_p}")
    nuove = [int(m["storia"]["nuove_caratteri"] / 3.5) for m in dopo[1:]]
    verifica("cache: della stanza si rileggono solo le righe nuove del turno (prima tutto il "
             "blocco della finestra)", all(d <= n_ * 1.1 + 20 for d, n_ in zip(st_d, nuove))
             and sum(st_d) * 2 < sum(st_p), f"dopo {st_d}, prima {st_p}")
    # Il prefisso: la richiesta di ogni turno comincia con quella di prima fino alla frase di
    # quel turno (compresa la riga della stanza che la precede)
    ok = True
    v = b.backend.visti
    for i in range(1, len(v)):
        prec, ora = v[i - 1], v[i]
        # fino al pezzo nuovo del turno prima compreso (dopo ci sono i dati del turno di allora)
        fine = max(j for j, m in enumerate(prec) if "fonte: stanza" in str(m.get("content"))) + 1
        if [(m["role"], m.get("content")) for m in ora[:fine]] != [
                (m["role"], m.get("content")) for m in prec[:fine]]:
            ok = False
    verifica("cache: storia e righe della stanza dei turni prima uguali byte per byte",
             ok and not any(m["rotta"] for m in dopo))
    # Ogni riga una volta sola, nell'ordine, ogni pezzo subito prima della frase del suo turno
    ultimo = v[-1]
    testo = "\n".join(str(m.get("content")) for m in _stanza_msgs(ultimo))
    tutte = [r["testo"] for r in st.registro(1).righe()]
    conte = [testo.count(t) for t in tutte]
    pos = [testo.find(t) for t in tutte]
    verifica("righe: ognuna una volta sola e nell'ordine in cui sono state dette",
             conte == [1] * len(tutte) and pos == sorted(pos), str(conte))
    domande_pos = [i for i, m in enumerate(ultimo) if m.get("role") == "user"]
    verifica("righe: ogni pezzo subito prima della frase del suo turno (l'ultimo prima dei dati "
             "del turno)", all("fonte: stanza" in str(ultimo[i - 1].get("content"))
                               for i in domande_pos[:-1])
             and len(_stanza_msgs(ultimo)) == 10, str(len(_stanza_msgs(ultimo))))
    verifica("righe: in busta come dato non fidato, intestazione intera solo nel primo pezzo",
             all(prov.fonti([m]) == {"stanza"} for m in _stanza_msgs(ultimo))
             and sum("Conversazione sentita" in str(m.get("content"))
                     for m in _stanza_msgs(ultimo)) == 1
             and sum("Altre frasi sentite" in str(m.get("content"))
                     for m in _stanza_msgs(ultimo)) == 9)
    verifica("registro: righe nuove e righe davanti al modello, solo numeri",
             dopo[-1]["storia"]["nuove"] == 12 and dopo[-1]["storia"]["righe"] == 120
             and dopo[-1]["storia"]["pezzi"] == 10
             and all(isinstance(x, int) for x in dopo[-1]["storia"].values()),
             str(dopo[-1]["storia"]))
    verifica("dati del turno: il nome «stanza» con la lunghezza del solo pezzo nuovo",
             [d["nome"] for d in b.last_dati_turno][:1] == ["stanza"]
             and b.last_dati_turno[0]["caratteri"] < 3000)
    st.chiudi()
    st2.chiudi()
    return prima, dopo


# ─────────────────────────── 2. mai su disco ───────────────────────────
def prova_disco():
    b, st, _ = giro(True, turni_n=3)
    verifica("storia: le righe della stanza non entrano nella storia (solo il segno)",
             not any("fonte: stanza" in str(m.get("content")) for m in b.history)
             and sum("_stanza" in m for m in b.history) == 3)
    e = b.conv.esporta()
    import json
    js = json.dumps(e, ensure_ascii=False)
    verifica("esporta: né righe né segno della stanza",
             "benzina" not in js and "_stanza" not in js and "fonte: stanza" not in js)
    tt = json.dumps(turni(b.history), ensure_ascii=False)
    verifica("archivio delle conversazioni: senza righe della stanza",
             "benzina" not in tt and "serbatoio" not in tt)
    c2 = Conversazione.importa(e)
    verifica("ripresa dopo un riavvio: nessuna riga della stanza (come il blocco caldo)",
             c2 is not None and not c2.stanza and not c2.stanza_mandate)
    st.chiudi()


# ─────────────────────────── 3. politica ───────────────────────────
def prova_politica():
    cfg = cfg_base()
    st = nuova_stanza(cfg)
    b = brain(cfg, st)
    ora = time.time()
    riga(st, 1, "Nella taverna c'è il cancello del garage aperto.", ora - 40, "Nicola")
    b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, ora)
    "".join(b.stream_reply("Calliope, che ore sono?", "amministra"))
    riga(st, 1, "Andiamo in bici al lago domenica?", ora + 10, "Carlo")
    b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, ora + 30)
    "".join(b.stream_reply("Calliope, fallo tu.", "amministra"))
    t = b._turno_politica()
    verifica("politica: le righe dei turni prima restano un dato non fidato (fonte e parole)",
             "stanza" in t.contaminazione
             and any(f == "stanza" and "cancello" in x for f, x in t.esterni))
    from calliope.tools.spec import ToolContext
    tctx = ToolContext(cfg=b.cfg, speakers=Voci(), speaker_ctx=Chi(), speaker=None)

    def decidi(nome, args, testo):
        turno = pol.Turno(testo=testo, contaminazione=t.contaminazione,
                          persona_txt=t.persona_txt, esterni=t.esterni, persona="carlo-id")
        cl = pol.classe_di(nome)
        base = pol.decidi(nome, args, cl, valore.copia_turno(turno), True, True)
        return valore.decidi_valore(nome, args, cl, turno, base, True, True, None, tctx,
                                    None, ())[0]
    d = decidi("casa_comando", {"comando": "apri il cancello del garage"}, "Calliope, fallo tu.")
    verifica("politica: un bersaglio preso da una riga di un turno prima chiede",
             d.esito != "esegui", str(d))
    d = decidi("casa_comando", {"comando": "accendi la luce in cucina"},
               "Calliope, accendi la luce in cucina")
    verifica("politica, contrario: il bersaglio detto nella frase si esegue",
             d.esito == "esegui", str(d))
    st.chiudi()


# ─────────────────────────── 4. contrari ───────────────────────────
def prova_contrari():
    # Pausa: le righe si nascondono, poi tornano uguali
    b, st, _ = giro(True, turni_n=3)
    st.pausa(1, "ospiti", 240)
    b.stanza_turno = None
    "".join(b.stream_reply("Calliope, che ore sono?", "amministra"))
    v = b.backend.visti[-1]
    verifica("contrario: in pausa per ospiti le righe della stanza non si mostrano",
             not _stanza_msgs(v) and "stanza_contesto" not in b.last_rules
             and "stanza" not in b._turno_politica().contaminazione)
    st.riprendi(1)
    "".join(b.stream_reply("Calliope, e adesso?", "amministra"))
    v2 = b.backend.visti[-1]
    verifica("…ripresa: tornano, gli stessi pezzi nello stesso posto",
             len(_stanza_msgs(v2)) == 3 and "stanza_contesto" in b.last_rules)
    # Dimentica: il registro svuotato porta via le righe
    st.dimentica(1)
    "".join(b.stream_reply("Calliope, di cosa parlavamo?", "amministra"))
    verifica("contrario: dopo «dimentica» le righe escono dalla storia",
             not _stanza_msgs(b.backend.visti[-1]) and not b.conv.stanza
             and "stanza_storia_dimenticata" in b.last_rules)
    st.chiudi()
    # Spento: niente
    b, st, _ = giro(True, turni_n=2, cfg_extra={"stanza_contesto": False})
    verifica("contrario: `stanza_contesto: false` → nessuna riga",
             not _stanza_msgs(b.backend.visti[-1]) and not b.conv.stanza)
    st.chiudi()
    # Il blocco intero, come prima
    b, st, _ = giro(False, turni_n=3)
    v = b.backend.visti[-1]
    verifica("contrario: `stanza_contesto_in_storia: false` → il blocco intero nei dati del "
             "turno, solo nel turno in corso", len(_stanza_msgs(v)) == 1
             and "Conversazione sentita" in str(_stanza_msgs(v)[0].get("content"))
             and not b.conv.stanza and not any("_stanza" in m for m in b.history))
    st.chiudi()
    # Turni tolti dalla storia: via anche le loro righe (e possono tornare se ancora nuove)
    b, st, _ = giro(True, turni_n=4)
    users = [i for i, m in enumerate(b.history) if m["role"] == "user"]
    b.conv.togli_in_testa(users[2])
    b.stanza_turno = None
    "".join(b.stream_reply("Calliope, ripetimelo.", "amministra"))
    verifica("contrario: un turno tolto dalla storia porta via le sue righe",
             len(b.conv.stanza) == 2 and len(_stanza_msgs(b.backend.visti[-1])) == 2,
             str(len(b.conv.stanza)))
    st.chiudi()
    # Il tetto: via le più vecchie fino a metà, una volta, e il prefisso scaldato
    b, st, misure = giro(True, turni_n=10, tetto=6000)
    if b.scalda_thread is not None:
        b.scalda_thread.join(5)
    potature = sum(1 for m in misure if (m["storia"] or {}).get("potati"))
    verifica("tetto: oltre `stanza_storia_caratteri` via le righe più vecchie fino a metà, a "
             "blocchi (non a ogni turno)", 1 <= potature <= 4
             and b._stanza_caratteri() <= 6000, f"potature {potature}")
    verifica("tetto: il prefisso nuovo scaldato in secondo piano, con le righe al loro posto",
             len(b.backend.scaldati) >= 1
             and any("fonte: stanza" in str(m.get("content")) for m in b.backend.scaldati[-1]))
    st.chiudi()


# ─────────────────── 5. le frasi della conversazione stessa ───────────────────
def prova_doppioni():
    """La domanda a Calliope e la sua risposta sono già nella storia: nel pezzo dopo non
    tornano (col blocco intero c'erano a ogni turno). La domanda di un'altra persona sì."""
    cfg = cfg_base()
    st = nuova_stanza(cfg)
    b = brain(cfg, st)
    ora = time.time() - 300
    riga(st, 1, "Domani piove, prendiamo l'ombrello.", ora, "Nicola")
    b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, ora + 20)
    "".join(b.stream_reply("Calliope, che tempo fa domani?", "amministra"))
    # Il ciclo mette nella stanza la frase del turno («→ Calliope») e la risposta detta
    st.registro(1).aggiungi("riga", segmento=None, versione=1, inizio=ora + 20, fine=ora + 22,
                            testo="Calliope, che tempo fa domani?", chi="persona:carlo-id",
                            nome="Carlo", sicurezza="voce", p_min=None, rivolta="si",
                            minore=False)
    st.detto(1, "Va bene, ne terrò conto.", ora + 23, ora + 25)
    riga(st, 1, "Calliope, metti la sveglia alle sette.", ora + 40, "Nicola")
    seq = st.registro(1).righe()[-1]["seq"]
    st.segna_rivolta(1, seq, "si", None)
    riga(st, 1, "Allora usciamo presto.", ora + 50, "Nicola")
    b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, ora + 70)
    "".join(b.stream_reply("Calliope, cosa ha detto Nicola?", "amministra"))
    nuovo = str(_stanza_msgs(b.backend.visti[-1])[-1].get("content"))
    verifica("doppioni: la domanda di questa conversazione e la risposta di Calliope non tornano "
             "nel pezzo dopo", "che tempo fa domani" not in nuovo
             and "ne terrò conto" not in nuovo and "usciamo presto" in nuovo, nuovo[-300:])
    verifica("doppioni, contrario: la frase rivolta a Calliope da un'altra persona resta",
             "Nicola → Calliope: Calliope, metti la sveglia" in nuovo, nuovo[-300:])
    st.chiudi()


# ─────────────────────────── 6. misure ───────────────────────────
def prova_misure():
    from calliope.stanza import misure as misure_mod
    turni_ = [{"stanza": {"contesto": {"righe": 30, "caratteri": 4000},
                          "storia": {"nuove": 12, "nuove_caratteri": 1300, "righe": 60,
                                     "caratteri": 7000, "pezzi": 5}},
               "prima_frase_s": 1.35, "cache": {"riletti": 600}},
              {"stanza": {"contesto": {"righe": 30, "caratteri": 4000},
                          "storia": {"nuove": 10, "nuove_caratteri": 1100, "righe": 30,
                                     "caratteri": 3500, "pezzi": 3, "potati": 3}},
               "prima_frase_s": 1.4, "cache": {"riletti": 9000}}]
    r = misure_mod.riassunto([], turni_)
    t = misure_mod.testo(r)
    s = r["blocco"]["storia"]
    verifica("misure: le righe nella storia in `calliope stato --turni` (nuove per turno, davanti "
             "al modello, potature)", s["turni"] == 2 and s["potature"] == 1
             and s["nuove_p50"] in (10.0, 11.0, 12.0) and "Righe della stanza nella storia" in t, t)
    c = Config()
    verifica("configurazione: in sola aggiunta di serie, tetto 16000 caratteri",
             c.stanza_contesto_in_storia is True and c.stanza_storia_caratteri == 16000)
    import calliope.ciclo as ciclo_mod
    src = open(ciclo_mod.__file__, encoding="utf-8").read()
    verifica("ciclo: il registro dei turni riceve `stanza.storia` da Brain",
             'info["storia"] = dict(st_s)' in src)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prima, dopo = prova_cache()
    if "--misura" in sys.argv:
        print("\nToken riletti stimati per turno (tutto / della sola stanza), conversazione "
              "finta di 10 turni, 12 righe nuove fra un turno e l'altro (~2 minuti)")
        print("turno   prima (blocco intero)   dopo (sola aggiunta)   righe nuove   righe "
              "nella storia")
        for p, d in zip(prima, dopo):
            s = d["storia"] or {}
            print(f"{p['turno']:>5}   {p['riletti']!s:>9} / {p['riletti_stanza']!s:>5}     "
                  f"{d['riletti']!s:>9} / {d['riletti_stanza']!s:>5}    "
                  f"{s.get('nuove', '-')!s:>11}   {s.get('righe', '-')!s:>17}")
        import statistics
        print("p50 dal turno 2: prima "
              f"{statistics.median(p['riletti'] for p in prima[1:])} / "
              f"{statistics.median(p['riletti_stanza'] for p in prima[1:])}, dopo "
              f"{statistics.median(d['riletti'] for d in dopo[1:])} / "
              f"{statistics.median(d['riletti_stanza'] for d in dopo[1:])}\n")
    prova_disco()
    prova_politica()
    prova_contrari()
    prova_doppioni()
    prova_misure()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
