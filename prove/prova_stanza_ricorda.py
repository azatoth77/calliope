"""
Prova a secco di «ti ricordi…?» con la conversazione di stanza (14/10/2026 notte, terzo caso della
seconda prova in auto). Caso vero, con nomi di fantasia: Carlo chiede «tu ricordi quando è il
compleanno della crisima di Marta» (Whisper scrive «crisima»); il modello chiama due volte
archivio_cerca e poi conversazione_cerca, e non trova. La risposta era nella stanza: le righe di
Carlo e Nicola e soprattutto la risposta di Calliope con cresima, Marta e la data, nove minuti
prima, appena fuori dagli 8 minuti del blocco caldo (la conversazione si era riaperta).

- (a) la ricerca trova anche le storpiature di Whisper (`stanza/cerca.simile`: parole di almeno 6
  lettere a una modifica di distanza, stessa iniziale) e il nome proprio basta; la ricerca
  anticipata vuole due parole della domanda o il nome proprio (`nomi_propri`); contrari: una
  parola davvero diversa («crosta», «cristina»), il nome di un'altra persona («Martina»,
  «Raffaele»), parole corte, la riga con una parola sola su due («quando è la festa di
  Halloween?» non porta la riga che dice solo «festa»);
- (b) il prompt e la descrizione di stanza_cerca: prima della stanza, poi archivio e conversazioni;
  Brain cerca nella stanza dopo una ricerca vuota nei documenti o nelle conversazioni passate
  (regola `stanza_dopo_ricerca_vuota`, una volta, la frase «non trovo» non si dice); contrari:
  ricerca riuscita, stanza_cerca già chiamato, rete `spinta_stanza` spenta, un altro tool;
- (c) alla riapertura della conversazione il primo pezzo arriva all'inizio dell'ultimo scambio
  (la risposta di nove minuti prima c'è, con le chiacchiere rade), dentro il tetto.

Nomi di fantasia (Carlo amministra ed è tutore di Nicola, 14 anni; Bianca è di famiglia; Marta è
una cugina). ~1 s.
"""

import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prova_stanza_cerca as base  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.stanza import cerca as cerca_mod  # noqa: E402
from calliope.stanza import contesto as ctx_mod  # noqa: E402
from calliope.stanza import misure as misure_mod  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402
from calliope.tools import stanza as tool_mod  # noqa: E402
from calliope.tools.archivio import _no as archivio_no  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


def uguale(nome, ottenuto, atteso):
    verifica(nome, ottenuto == atteso, f"{ottenuto!r}" + ("" if ottenuto == atteso
                                                          else f", atteso {atteso!r}"))


DOMANDA = "tu ricordi quando è il compleanno della crisima di Marta"


def scena_auto(chiacchiere_fitte: bool = False):
    """In auto (satellite 1): Carlo e Nicola parlano della cresima di Marta 11 minuti fa, Calliope
    risponde con la data 9 minuti fa; poi altre chiacchiere (rade o fitte) fino a adesso."""
    cfg = base.cfg_base()
    st = Stanza(cfg, base.STTFinto(), registry=base.Voci(), misure=misure_mod.Misure(None),
                log=lambda m: None)
    st._info[1] = {"nome": "telefono di Carlo", "stanza": "auto", "canale": "telefono"}
    st.server = SimpleNamespace(attivo=SimpleNamespace(satellite={"id": 1}),
                                per_id=lambda s: None)
    ora = time.time()
    st._sentita("carlo-id", "Carlo", 1, ora - 900)
    st._sentita("nicola-id", "Nicola", 1, ora - 880)
    base.riga(st, 1, "Quand'è che c'è la crisima di Marta?", ora - 660, "Nicola")
    base.riga(st, 1, "Non mi ricordo, chiediamolo.", ora - 640, "Carlo")
    st.detto(1, "La cresima di Marta è sabato diciotto ottobre alle undici.", inizio=ora - 545,
             fine=ora - 540, per={"persona": "nicola-id", "sicurezza": "voce"})
    base.riga(st, 1, "Grazie, allora prendiamo il regalo venerdì.", ora - 520, "Carlo")
    passo = 8 if chiacchiere_fitte else 140
    k = 0
    for t in range(int(ora - 500), int(ora - 20), passo):
        base.riga(st, 1, f"Guarda che traffico c'è sulla tangenziale stasera ({k}).", t,
                  ("Carlo", "Nicola")[k % 2])
        k += 1
    st._sentita("carlo-id", "Carlo", 1, ora - 10)
    return cfg, st, ora


def contesto(st, nome="Carlo"):
    return base.contesto(st, nome)


# ─────────────────────────── (a) storpiature e nome proprio ───────────────────────────
def prova_simili():
    verifica("simile: «crisima» e «cresima» (una lettera cambiata)",
             cerca_mod.simile("crisima", "cresima"))
    verifica("simile: una lettera in più o in meno («cresime»/«cresima», «compleano»)",
             cerca_mod.simile("cresima", "cresime")
             and cerca_mod.simile("compleano", "compleanno"))
    contrari = [("crisima", "cristina"), ("crisima", "crosta"), ("rachele", "raffaele"),
                ("marta", "marte"), ("crisima", "brisima"), ("gita", "gite"),
                ("compleanno", "complemento")]
    uguale("contrari: due lettere, iniziale diversa, parole corte (le corte le trova la radice)",
           [c for c in contrari if cerca_mod.simile(*c)], [])
    r = cerca_mod.rare(DOMANDA)
    uguale("rare: le parole lunghe e utili della domanda", sorted(r.values()),
           ["compleanno", "crisima"])
    uguale("combacia: la riga con «cresima» e «Marta» prende due radici",
             len(cerca_mod.combacia(cerca_mod.chiavi(DOMANDA),
                                    cerca_mod.parole("La cresima di Marta è sabato"), r)), 2)
    uguale("contrario: senza le parole simili (la radice sola) «cresima» non c'era",
             len(cerca_mod.combacia(cerca_mod.chiavi(DOMANDA),
                                    cerca_mod.parole("La cresima è sabato"))), 0)
    uguale("nomi propri: la maiuscola in mezzo alla frase e i nomi di casa, non la wake word",
             (sorted(tool_mod.nomi_propri(contesto(scena_auto()[1]), DOMANDA)),
              sorted(tool_mod.nomi_propri(contesto(scena_auto()[1]),
                                          "Calliope, cosa ha detto nicola di Halloween?"))),
             (["mart"], ["hallo", "nicol"]))


def prova_anticipo():
    cfg, st, ora = scena_auto()
    a = tool_mod.anticipa(contesto(st), DOMANDA, None)
    verifica("anticipo: con «crisima» trova la risposta di Calliope con «cresima», Marta e la data",
             a is not None and "diciotto ottobre" in a.testo, getattr(a, "testo", None))
    a = tool_mod.anticipa(contesto(st), "quand'è la festa di Marta?", None)
    verifica("anticipo: il nome proprio da solo basta (una parola su due, ma è Marta)",
             a is not None and "Marta" in a.testo, getattr(a, "testo", None))
    a = tool_mod.anticipa(contesto(st), "tu ricordi quando è il compleanno della crosta di "
                                        "Martina", None)
    verifica("contrario: parola davvero diversa e un'altra persona → niente",
             a is not None and a.testo == "", getattr(a, "testo", None))
    base.riga(st, 1, "Che bella festa l'anno scorso al mare.", ora - 300, "Carlo")
    a = tool_mod.anticipa(contesto(st), "Calliope, quando è la festa di Halloween?", None)
    verifica("contrario: la riga con una parola sola su due («festa») non entra",
             a is not None and "mare" not in a.testo, getattr(a, "testo", None))
    base.riga(st, 1, "Ad Halloween andiamo dai nonni.", ora - 290, "Nicola")
    a = tool_mod.anticipa(contesto(st), "Calliope, quando è la festa di Halloween?", None)
    verifica("…la riga con «Halloween» (nome proprio) sì", a is not None and "nonni" in a.testo,
             getattr(a, "testo", None))
    # Il tool, chiamato dal modello con la parola giusta, trova anche la storpiatura nelle righe
    r = tool_mod._stanza_cerca(contesto(st), parole="cresima")
    verifica("stanza_cerca: «cresima» trova anche la riga di Nicola con «crisima»",
             r.get("trovato") and "crisima" in r.get("risultati", ""), r.get("risultati"))
    st.chiudi()


# ─────────────────────────── (b) prompt, descrizione, Brain ───────────────────────────
def prova_prompt():
    from calliope.config import Config
    c = base.cfg_base()
    p = c.prompt_for(biblioteca=False, stanza=True)
    verifica("prompt: con la stanza, le risposte di Calliope e stanza_cerca prima di archivio e "
             "conversazioni", "anche le tue risposte" in p
             and "stanza_cerca, prima di archivio_cerca, di conversazione_cerca" in p)
    p2 = Config().system_prompt
    verifica("contrario: senza la stanza la frase non c'è", "anche le tue risposte" not in p2)
    d = tool_mod.cerca_spec().description
    verifica("descrizione di stanza_cerca: le risposte dette a voce, «ti ricordi…?» prima dei "
             "documenti", "hai risposto tu a voce" in d and "ti ricordi" in d)


class Backend:
    def __init__(self, copione):
        self.copione, self.visti = list(copione), []

    def stream(self, messages, tools):
        self.visti.append(json.dumps(messages, ensure_ascii=False))
        yield from self.copione.pop(0)


def con_copione(st, copione, cfg=None, registro=None):
    from calliope.tools.builtin import build_registry
    from calliope.tools.spec import ToolSpec
    reg = registro
    if reg is None:
        reg = build_registry()
        for spec in tool_mod.stanza_specs(st.cfg):
            reg.register(spec)
        # Un archivio finto che non trova niente (la sua frase pronta, come quello vero)
        reg.register(ToolSpec(
            name="archivio_cerca", description="Cerca nei documenti di casa.",
            parameters={"type": "object", "properties": {"cosa": {"type": "string"}},
                        "required": []},
            func=lambda ctx, cosa="": archivio_no("Non trovo documenti nell'archivio."),
            risk="lettura", levels=tool_mod.LIVELLI_DA["familiare"]))
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg or st.cfg, reg, []
    b.tool_ctx = contesto(st)
    b.on_tool_start = None
    b.backend = Backend(copione)
    return b


def prova_brain():
    cfg, st, ora = scena_auto()
    senza_ant = base.cfg_base(stanza_cerca_anticipo=False)
    archivio = [("calls", [{"id": "a0", "name": "archivio_cerca",
                            "arguments": {"cosa": "cresima Marta"}}])]
    b = con_copione(st, [archivio, [("text", "La cresima di Marta è sabato diciotto ottobre.")]],
                    senza_ant)
    r = "".join(b.stream_reply(DOMANDA, "amministra"))
    secondo = b.backend.visti[1] if len(b.backend.visti) > 1 else ""
    verifica("dopo l'archivio vuoto Brain cerca nella stanza: il modello ha le righe davanti, la "
             "frase «non trovo» non si dice",
             "stanza_dopo_ricerca_vuota" in b.last_rules and "diciotto ottobre" in secondo
             and "Non trovo" not in r and r.startswith("La cresima"), r)
    # Contrari
    b = con_copione(st, [archivio, [("text", "x")]], senza_ant)
    b.cfg = base.cfg_base(stanza_cerca_anticipo=False, llm_reti_spente=["spinta_stanza"])
    r = "".join(b.stream_reply(DOMANDA, "amministra"))
    verifica("contrario: rete spenta → la frase dell'archivio, nessuna ricerca nella stanza",
             "stanza_dopo_ricerca_vuota" not in b.last_rules and "Non trovo" in r, r)
    stanza_poi_archivio = [[("calls", [{"id": "s0", "name": "stanza_cerca",
                                        "arguments": {"parole": "gelato"}}])],
                           archivio, [("text", "Non lo so.")]]
    b = con_copione(st, stanza_poi_archivio, senza_ant)
    r = "".join(b.stream_reply(DOMANDA, "amministra"))
    verifica("contrario: stanza_cerca già chiamato nella risposta → niente di nuovo",
             "stanza_dopo_ricerca_vuota" not in b.last_rules, str(b.last_rules))
    b = con_copione(st, [[("calls", [{"id": "o0", "name": "ora_attuale", "arguments": {}}])],
                         [("text", "Sono le dieci.")]], senza_ant)
    r = "".join(b.stream_reply("Calliope, che ore sono?", "amministra"))
    verifica("contrario: un altro tool (non una ricerca vuota) → niente",
             "stanza_dopo_ricerca_vuota" not in b.last_rules, r)
    from calliope.tools.builtin import build_registry
    from calliope.tools.spec import ToolSpec
    reg = build_registry()
    for spec in tool_mod.stanza_specs(st.cfg):
        reg.register(spec)
    reg.register(ToolSpec(
        name="archivio_cerca", description="Cerca nei documenti di casa.",
        parameters={"type": "object", "properties": {"cosa": {"type": "string"}}, "required": []},
        func=lambda ctx, cosa="": {"ok": True, "risultato": "Polizza auto n. 123."},
        risk="lettura", levels=tool_mod.LIVELLI_DA["familiare"]))
    b = con_copione(st, [archivio, [("text", "La polizza è la 123.")]], senza_ant, registro=reg)
    r = "".join(b.stream_reply("Calliope, il numero della polizza?", "amministra"))
    verifica("contrario: l'archivio trova → niente ricerca nella stanza",
             "stanza_dopo_ricerca_vuota" not in b.last_rules, r)
    st.chiudi()


# ─────────────────────────── (c) la riapertura ───────────────────────────
def prova_riapertura():
    cfg, st, ora = scena_auto(chiacchiere_fitte=False)
    blocco = ctx_mod.costruisci(st, 1, cfg, ora)
    p = ctx_mod.pezzo(blocco, set(), cfg, 1, primo=True, riapertura=True)
    verifica("riapertura con chiacchiere rade: il primo pezzo arriva alla risposta di nove "
             "minuti prima (oltre gli 8 minuti)", p is not None and "diciotto ottobre" in p.testo,
             getattr(p, "testo", None))
    p8 = ctx_mod.pezzo(blocco, set(), cfg, 1, primo=True, riapertura=False)
    verifica("contrario: senza riapertura (il pezzo di un turno) gli 8 minuti di sempre",
             p8 is not None and "diciotto ottobre" not in p8.testo)
    st.chiudi()
    cfg, st, ora = scena_auto(chiacchiere_fitte=True)
    blocco = ctx_mod.costruisci(st, 1, cfg, ora)
    p = ctx_mod.pezzo(blocco, set(), cfg, 1, primo=True, riapertura=True)
    verifica("riapertura con chiacchiere fitte: il tetto stanza_riapertura_caratteri vale (le più "
             "nuove), il resto lo trova la ricerca", p is not None
             and p.righe_caratteri <= cfg.stanza_riapertura_caratteri + 400
             and "diciotto ottobre" not in p.testo, getattr(p, "righe_caratteri", None))
    a = tool_mod.anticipa(contesto(st), DOMANDA, SimpleNamespace(righe_id={
        (1, q) for q in []}))
    verifica("…e la ricerca anticipata la trova", a is not None and "diciotto ottobre" in a.testo,
             getattr(a, "testo", None))
    st.chiudi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prova_simili()
    prova_anticipo()
    prova_prompt()
    prova_brain()
    prova_riapertura()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
