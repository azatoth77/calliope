import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della frase dopo il tool, System 1 (15/10, calliope/system1/dopo_tool.py;
roadmap 3.12).

- il decisore: «codice» per gli esiti semplici e chiusi (timer, promemoria, liste, volume, ora,
  data, calcoli: la frase pronta del tool) e i **contrari**, ognuno col suo perché: più tool, tool
  fallito, risultato da spiegare (`cosa_fare`, domanda in sospeso, nome incerto), tool fuori
  dall'elenco (una lista letta, la casa, la memoria), senza frase o frase lunga, testo del modello
  già detto, un minore, un tono che il codice non sa fare, la frase della persona con più frasi,
  lunga o con una domanda per un'azione, i dubbi di struttura di Brain;
- la sostanza (ombra): numeri in cifre e in parole, parole piene, percentuali;
- Brain con un motore finto: «spento» come prima; «attivo» una passata sola, la frase del tool
  detta e nella storia, la regola `dopo_tool_codice`; i contrari in Brain (due tool, testo prima
  del tool, minore, tono formale, contesto del turno, tool fallito, decisore guasto) fanno la
  seconda passata come prima; «ombra» fa la seconda passata, la cronometra (prima frase, passata),
  la confronta (uguale, diversa, domanda, altro tool), resta in streaming, e una risposta
  interrotta chiude la richiesta al modello; `casa_comando` già pronta;
- configurazione, calliope.yaml, ciclo e conservazione (la frase tolta senza le parole),
  riassunto e riga di `calliope stato --turni`.
"""

import json
from pathlib import Path

from calliope import frasi
from calliope.brain import Brain
from calliope.config import Config
from calliope.system1 import dopo_tool as dt
from calliope.tools.builtin import build_registry

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, ok, *resto):
    """verifica(nome, vero_o_falso[, dettaglio]) oppure verifica(nome, ottenuto, atteso[, …])."""
    global errori
    dettaglio = ""
    if resto and not (len(resto) == 1 and isinstance(resto[0], str) and isinstance(ok, bool)):
        ottenuto, atteso = ok, resto[0]
        ok = ottenuto == atteso
        dettaglio = "" if ok else f"→ {ottenuto!r} (atteso {atteso!r})"
    elif resto:
        dettaglio = resto[0]
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


TIMER = {"ok": True, "timer": "di 10 minuti", "durata": "10 minuti",
         "conferma": "Va bene, timer di 10 minuti avviato."}
ORA = {"ora": "09:05", "fuso": "locale", "da_dire": "Sono le 9:05."}
LISTA = {"ok": True, "lista": "spesa", "aggiunti": ["latte", "uova"], "gia_presenti": [],
         "conferma": "Ho aggiunto latte e uova alla lista della spesa."}


def esito(testo, chiamate=("timer_imposta",), risultati=(TIMER,), **k):
    return dt.Esito(testo=testo, chiamate=tuple(chiamate), risultati=tuple(risultati), **k)


# ─────────────────────────────── il decisore ───────────────────────────────
def prova_decisore():
    d = dt.DopoTool()
    casi = [
        ("timer", esito("Calliope, metti un timer di dieci minuti."), dt.CODICE,
         "esito_chiuso", TIMER["conferma"]),
        ("ora con la domanda", esito("Che ore sono?", ("ora_attuale",), (ORA,)), dt.CODICE,
         "esito_chiuso", "Sono le 9:05."),
        ("calcolo", esito("Quanto fa 17 per 6?", ("calcola",),
                          ({"ok": True, "espressione": "17*6", "risultato": "102",
                            "da_dire": "102"},)), dt.CODICE, "esito_chiuso", "Fa 102."),
        ("lista con «e» tra le cose", esito("Aggiungi latte e uova alla lista della spesa",
                                            ("lista_aggiungi",), (LISTA,)),
         dt.CODICE, "esito_chiuso", LISTA["conferma"]),
        ("volume", esito("Alza il volume", ("pc_volume",),
                         ({"ok": True, "livello": 40, "prima": 30,
                           "conferma": "Fatto, volume al 40 per cento."},)), dt.CODICE,
         "esito_chiuso", None),
        # contrari
        ("contrario: due tool", esito("Metti un timer e dimmi che ore sono",
                                      ("timer_imposta", "ora_attuale"), (TIMER, ORA)),
         dt.MODELLO, "piu_tool", None),
        ("contrario: tool fallito", esito("Metti un timer", risultati=(
            {"ok": False, "errore": "«boh» non è una durata"},)), dt.MODELLO, "tool_fallito",
         None),
        ("contrario: cosa_fare in un esito riuscito", esito("Togli il pane", ("lista_togli",), (
            {"ok": True, "tolti": [], "conferma": "x", "cosa_fare": "dillo in breve"},)),
         dt.MODELLO, "da_spiegare", None),
        ("contrario: domanda in sospeso", esito("Metti un timer", risultati=(
            {**TIMER, "in_sospeso": {"tool": "x"}},)), dt.MODELLO, "da_spiegare", None),
        ("contrario: nome incerto", esito("Metti un timer", risultati=(
            {**TIMER, "nome_incerto": {"forse": "pasta"}},)), dt.MODELLO, "da_spiegare", None),
        ("contrario: lista letta (dati da riassumere)", esito(
            "Cosa c'è nella lista della spesa?", ("lista_leggi",),
            ({"ok": True, "conferma": "Nella lista: latte, uova, pane."},)),
         dt.MODELLO, "non_coperto", None),
        ("contrario: la memoria", esito("Ricorda che a Ugo piace il tè", ("ricorda",),
                                        ({"ok": True, "conferma": "Va bene."},)),
         dt.MODELLO, "non_coperto", None),
        ("contrario: senza frase pronta", esito("Che ore sono?", ("ora_attuale",),
                                                ({"ora": "09:05"},)),
         dt.MODELLO, "senza_frase", None),
        ("contrario: frase lunga", esito("Metti un timer", risultati=(
            {**TIMER, "conferma": "Va bene. " * 40},)), dt.MODELLO, "frase_lunga", None),
        ("contrario: testo del modello già detto", esito("Metti un timer",
                                                         detto_prima="Certo, ci penso io."),
         dt.MODELLO, "testo_del_modello", None),
        ("contrario: un minore", esito("Che ore sono?", ("ora_attuale",), (ORA,), minore=True),
         dt.MODELLO, "minore", None),
        ("contrario: tono formale", esito("Metti un timer", tono="formale"), dt.MODELLO, "tono",
         None),
        ("contrario: tono computer di bordo", esito("Metti un timer", tono="computer_di_bordo"),
         dt.MODELLO, "tono", None),
        ("contrario: due frasi della persona", esito(
            "Metti un timer di dieci minuti. Poi raccontami una storia."), dt.MODELLO,
         "piu_frasi", None),
        ("contrario: domanda con un'azione", esito(
            "Metti un timer di dieci minuti, quanto manca a cena?"), dt.MODELLO, "domanda", None),
        ("contrario: frase lunga della persona", esito(
            "Metti un timer di dieci minuti per la pasta che ho appena buttato perché "
            "stasera vengono a cena i nonni di Ugo"), dt.MODELLO, "persona_lunga", None),
        ("contrario: dubbio di struttura (proposta aperta)", esito(
            "Sì", dubbi=("proposta",)), dt.MODELLO, "dubbio_proposta", None),
        ("contrario: nessun tool", esito("Ciao", (), ()), dt.MODELLO, "nessun_tool", None),
    ]
    for nome, e, scelta, perche, frase in casi:
        s = d.decide(e)
        ok = s.scelta == scelta and s.perche == perche and (frase is None or s.frase == frase)
        verifica(f"decisore: {nome}", ok, f"{s.scelta} {s.perche} {s.frase!r}")
        verifica(f"decisore: {nome}, sicurezza 0–1", 0.0 <= s.sicurezza <= 1.0)
    verifica("decisore: «codice» sopra la soglia", d.decide(casi[0][1]).sicurezza >= dt.SOGLIA)
    verifica("decisore: casa_comando non è nell'elenco (ha la sua risposta_finale)",
             "casa_comando" not in dt.COPERTI)
    verifica("decisore: frasi e parole", (dt.frasi_della_persona("Ciao. Come stai? Bene"),
                                          dt.frasi_della_persona("Calliope, che ore sono?"),
                                          dt.parole("Metti un timer di dieci minuti")) == (3, 1, 6))
    d2 = dt.DopoTool(parole_max=3)
    verifica("decisore: parole al più configurabili",
             d2.decide(esito("Metti un timer di dieci minuti")).perche == "persona_lunga")


# ─────────────────────────────── la sostanza ───────────────────────────────
def prova_sostanza():
    s = dt.sostanza("Sono le 9:05.", "Sono le nove e cinque.")
    verifica("sostanza: l'ora in parole è la stessa", s["uguale"] and s["numeri"], str(s))
    s = dt.sostanza("Sono le 9:05.", "Sono le 10:05.")
    verifica("sostanza, contrario: un'altra ora", not s["uguale"] and not s["numeri"], str(s))
    s = dt.sostanza("Va bene, timer di 10 minuti avviato.", "Ho avviato un timer di dieci minuti.")
    verifica("sostanza: il timer detto con altre parole", s["uguale"], str(s))
    s = dt.sostanza("Fatto, volume al 30 per cento.", "Volume al 30%.")
    verifica("sostanza: la percentuale", s["uguale"], str(s))
    s = dt.sostanza("Ho aggiunto latte e uova alla lista della spesa.",
                    "Fatto! Ho messo il latte nella lista.")
    verifica("sostanza, contrario: manca una cosa (uova)", s["copertura"] < 1.0, str(s))
    s = dt.sostanza("Fa 102.", "Il risultato è centodue.")
    verifica("sostanza, contrario: «centodue» non si legge (oltre 99: diversa, misura prudente)",
             not s["numeri"], str(s))
    verifica("sostanza: ventitré, trentotto", dt.numeri("ventitré e trentotto") == {23, 38})


# ─────────────────────────────── Brain ───────────────────────────────
class Motore:
    """Risponde a copione; conta le passate e se uno stream è stato chiuso a metà."""

    def __init__(self, copione):
        self.copione = list(copione)
        self.passate, self.chiusi, self.finiti = 0, 0, 0

    def stream(self, messages, tools):
        self.passate += 1
        eventi = self.copione.pop(0) if self.copione else [("text", "Altro.")]
        fine = False
        try:
            for ev in eventi:
                yield ev
            fine = True
            self.finiti += 1
        finally:
            if not fine:
                self.chiusi += 1


class CtxFinto:
    current_speaker = "Ugo"
    current_level = "familiare"


def brain(copione, modo="attivo", risultato=None):
    cfg = Config()
    cfg.system1_dopo_tool = modo
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.tool_ctx = type("T", (), {"speaker_ctx": CtxFinto()})()
    b.backend = Motore(copione)
    b.console_riservata = lambda: None
    if risultato is not None:
        b.tools.call = lambda *a, **k: json.dumps(risultato, ensure_ascii=False)
    frasi.FRASI.inizio_turno(None, "normale")
    return b


def chiama(nome, args=None, i=0):
    return ("calls", [{"id": f"call_{i}", "name": nome, "arguments": args or {}}])


def prova_brain_attivo():
    calc = [[chiama("calcola", {"espressione": "17*6"})], [("text", "Fa centodue.")]]
    # spento: come prima
    b = brain([list(x) for x in calc], modo="spento")
    detto = "".join(b.stream_reply("Quanto fa 17 per 6?", "familiare"))
    verifica("spento: due passate, la frase del modello, niente nel registro",
             (b.backend.passate, detto, b.last_dopo_tool), (2, "Fa centodue.", None))
    # attivo: una passata, la frase del tool
    b = brain([list(x) for x in calc])
    detto = "".join(b.stream_reply("Quanto fa 17 per 6?", "familiare"))
    verifica("attivo: una passata sola, detta la frase del tool",
             (b.backend.passate, detto.strip()), (1, "Fa 102."), detto)
    verifica("attivo: la storia coerente (utente, chiamata, risultato, la frase detta)",
             ([m["role"] for m in b.history], b.history[-1]["content"]),
             (["user", "assistant", "tool", "assistant"], "Fa 102."))
    verifica("attivo: la regola nel registro e l'esito",
             ("dopo_tool_codice" in b.last_rules, b.last_dopo_tool["esito"],
              b.last_dopo_tool["modo"], b.last_dopo_tool["tool"]),
             (True, "codice", "attivo", "calcola"))
    verifica("attivo: la frase marcata come esito per l'uscita unica",
             any(a == "esito" and t == "Fa 102." for t, a, _ in b.parlato_marcato))
    # timer con la conferma (risultato finto, l'agenda non serve)
    b = brain([[chiama("timer_imposta", {"durata": "10 minuti"})], [("text", "Fatto!")]],
              risultato=TIMER)
    detto = "".join(b.stream_reply("Metti un timer di dieci minuti", "familiare"))
    verifica("attivo: il timer con la sua conferma", (b.backend.passate, detto.strip()),
             (1, TIMER["conferma"]))
    # ospite: la frase non va nel registro
    b = brain([list(x) for x in calc])
    "".join(b.stream_reply("Quanto fa 17 per 6?", "ospite"))
    verifica("attivo, ospite: la frase del codice non va nel registro",
             (b.backend.passate, "frase" in b.last_dopo_tool), (1, False))

    # ── contrari in Brain: la seconda passata come prima ──
    def due_passate(nome, b, frase="Quanto fa 17 per 6?", perche=None, **k):
        detto = "".join(b.stream_reply(frase, "familiare", **k))
        reg = b.last_dopo_tool or {}
        ok = b.backend.passate >= 2 and "dopo_tool_codice" not in b.last_rules
        if perche is not None:
            ok = ok and reg.get("perche") == perche
        verifica(f"attivo, contrario: {nome}", ok, f"{b.backend.passate} {reg} {detto!r}")

    due_passate("due tool nella stessa passata", brain([
        [("calls", [{"id": "c0", "name": "calcola", "arguments": {"espressione": "17*6"}},
                    {"id": "c1", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Fa 102, e sono le dieci.")]]), perche="piu_tool")
    due_passate("testo del modello prima del tool", brain([
        [("text", "Allora, vediamo. "), chiama("calcola", {"espressione": "17*6"})],
        [("text", "Fa 102.")]]), perche="dubbio_detto")
    b = brain([list(x) for x in calc])
    b.parla_minore = lambda: True          # minori.parla_minore (16/10: prima console_riservata)
    due_passate("un minore", b, perche="minore")
    b = brain([list(x) for x in calc])
    frasi.FRASI.inizio_turno(None, "formale")
    b.stream_reply  # (il tono è del thread: inizio_turno qui sopra)
    detto = "".join(b.stream_reply("Quanto fa 17 per 6?", "familiare"))
    verifica("attivo, contrario: tono formale", (b.backend.passate, b.last_dopo_tool["perche"]),
             (2, "tono"))
    frasi.FRASI.inizio_turno(None, "normale")
    due_passate("dati del turno in più (contesto)", brain([list(x) for x in calc]),
                perche="dubbio_contesto", context="Passaggi della biblioteca: …")
    due_passate("tool fallito", brain([
        [chiama("calcola", {"espressione": "1/0"})], [("text", "Non si può dividere per zero.")]]),
        frase="Quanto fa uno diviso zero?", perche="tool_fallito")
    due_passate("lista letta: dati da riassumere", brain([
        [chiama("lista_leggi", {"lista": "spesa"})], [("text", "Ci sono latte e uova.")]],
        risultato={"ok": True, "conferma": "Nella lista della spesa: latte, uova."}),
        frase="Cosa c'è nella lista della spesa?", perche="non_coperto")

    class Guasto:
        nome, scelte = "guasto", ("codice", "modello")

        def decide(self, dati):
            raise RuntimeError("guasto di prova")

    b = brain([list(x) for x in calc])
    from calliope.system1 import Sorvegliato
    b.__dict__["_s1_dopo_tool"] = Sorvegliato(Guasto(), log=lambda *_: None)
    detto = "".join(b.stream_reply("Quanto fa 17 per 6?", "familiare"))
    verifica("attivo, contrario: decisore guasto → il modello, la voce non si ferma",
             (b.backend.passate, detto, b.last_dopo_tool["esito"]),
             (2, "Fa centodue.", "in_ritardo"))
    # casa_comando ha già la sua risposta_finale: «gia_pronta», una passata come sempre
    b = brain([[chiama("casa_comando", {"comando": "accendi la luce della cucina"})]],
              risultato={"ok": True, "fatto": "eseguito", "conferma": "Luce accesa.",
                         "risposta_finale": "Luce accesa."})
    detto = "".join(b.stream_reply("Accendi la luce in cucina", "familiare"))
    verifica("casa_comando: già pronta, una passata, nel registro «gia_pronta»",
             (b.backend.passate, detto, b.last_dopo_tool["esito"]),
             (1, "Luce accesa.", "gia_pronta"))


def prova_brain_ombra():
    def calc(seconda):
        return [[chiama("calcola", {"espressione": "17*6"})], seconda]

    b = brain(calc([("text", "Diciassette per sei "), ("text", "fa 102. "),
                    ("text", "Altro?")]), modo="ombra")
    g = b.stream_reply("Quanto fa 17 per 6?", "familiare")
    primo = next(g)
    # (la prima frase intera: dopo una lettura la rete delle azioni dichiarate la tiene fino al
    # punto, come prima; «Altro?» non è ancora arrivato)
    verifica("ombra: streaming, la prima frase della seconda passata prima della fine",
             (primo, b.backend.finiti), ("Diciassette per sei fa 102. ", 1))
    detto = primo + "".join(g)
    reg = b.last_dopo_tool
    verifica("ombra: due passate, detta la frase del modello",
             (b.backend.passate, detto), (2, "Diciassette per sei fa 102. Altro?"))
    verifica("ombra: nel registro codice, la frase, i tempi e il confronto",
             (reg["esito"], reg["modo"], reg["frase"], "dopo_tool_codice" in b.last_rules,
              isinstance(reg.get("prima_frase_ms"), int), isinstance(reg.get("passata_ms"), int),
              reg["prima_frase_ms"] <= reg["passata_ms"], reg["uguale"], reg["domanda"],
              reg["altro_tool"]),
             ("codice", "ombra", "Fa 102.", False, True, True, True, True, True, False), str(reg))
    verifica("ombra: la storia col testo del modello",
             b.history[-1]["content"], "Diciassette per sei fa 102. Altro?")
    b = brain(calc([("text", "Fa 104.")]), modo="ombra")
    "".join(b.stream_reply("Quanto fa 17 per 6?", "familiare"))
    verifica("ombra, contrario: il modello dice un altro numero → diversa",
             (b.last_dopo_tool["uguale"], b.last_dopo_tool["numeri"]), (False, False))
    b = brain([[chiama("calcola", {"espressione": "17*6"})],
               [chiama("ora_attuale", i=1)], [("text", "Fa 102, e sono le dieci.")]], modo="ombra")
    "".join(b.stream_reply("Quanto fa 17 per 6?", "familiare"))
    verifica("ombra: un altro tool nella seconda passata si segna (in attivo non partirebbe)",
             (b.backend.passate, b.last_dopo_tool["altro_tool"]), (3, True))
    # interrotta a metà della seconda passata: la richiesta al modello si chiude
    b = brain(calc([("text", "Diciassette per sei "), ("text", "fa 102. "), ("text", "E poi "),
                    ("text", "altro.")]), modo="ombra")
    g = b.stream_reply("Quanto fa 17 per 6?", "familiare")
    next(g)
    g.close()
    verifica("ombra, interrotta: stream del modello chiuso, segnata «interrotta»",
             (b.backend.chiusi, b.last_dopo_tool.get("interrotta")), (1, True))
    # i contrari in ombra: «modello» col perché, niente misura
    b = brain([[("calls", [{"id": "c0", "name": "calcola", "arguments": {"espressione": "1+1"}},
                           {"id": "c1", "name": "ora_attuale", "arguments": {}}])],
               [("text", "Fa 2.")]], modo="ombra")
    "".join(b.stream_reply("Quanto fa uno più uno?", "familiare"))
    verifica("ombra, contrario: due tool → «modello», nessun tempo",
             (b.last_dopo_tool["esito"], b.last_dopo_tool["perche"],
              "prima_frase_ms" in b.last_dopo_tool), ("modello", "piu_tool", False))


# ─────────────────────────────── configurazione e ciclo ───────────────────────────────
def prova_config_e_ciclo():
    c = Config()
    verifica("config: di serie spento, 16 parole",
             (c.system1_dopo_tool, c.system1_dopo_tool_parole_max) == ("spento", 16))
    from calliope import config as cm
    verifica("config: modo validato", cm.VALIDATORI["system1_dopo_tool"](" Ombra ") == "ombra"
             and cm.VALIDATORI["system1_dopo_tool"]("attivo") == "attivo")
    try:
        cm.VALIDATORI["system1_dopo_tool"]("acceso")
        ok = False
    except ValueError:
        ok = True
    verifica("config, contrario: «acceso» non è un modo", ok)
    verifica("config: parole al più con un intervallo",
             cm.fuori_limiti("system1_dopo_tool_parole_max", 0) is not None
             and cm.fuori_limiti("system1_dopo_tool_parole_max", 16) is None)
    c.system1_dopo_tool = "boh"
    verifica("modo sconosciuto: spento", dt.modo(c) == "spento")
    yaml = (RADICE / "calliope.yaml").read_text(encoding="utf-8")
    verifica("calliope.yaml: i campi", "system1_dopo_tool: spento" in yaml
             and "system1_dopo_tool_parole_max: 16" in yaml)
    src = (RADICE / "calliope" / "ciclo.py").read_text(encoding="utf-8")
    verifica("ciclo: l'esito nel registro dei turni, la frase ripulita",
             'rec["dopo_tool"] = dt' in src and 'brain.redact(dt["frase"])' in src)
    from calliope.conserva import togli_testo
    rec = togli_testo({"testo": "Che ore sono?", "dopo_tool": {"esito": "codice",
                                                               "frase": "Sono le 9:05."}})
    verifica("conservazione: senza le parole niente frase del codice, restano i numeri",
             rec["dopo_tool"], {"esito": "codice"})


def prova_riassunto():
    turni = [
        {"tool": [{"nome": "calcola"}], "dopo_tool": {
            "modo": "ombra", "esito": "codice", "tool": "calcola", "ms": 0.2,
            "prima_frase_ms": 800, "passata_ms": 900, "uguale": True, "domanda": False,
            "altro_tool": False}},
        {"tool": [{"nome": "timer_imposta"}], "dopo_tool": {
            "modo": "ombra", "esito": "codice", "tool": "timer_imposta", "ms": 0.3,
            "prima_frase_ms": 1000, "passata_ms": 1200, "uguale": True, "domanda": True,
            "altro_tool": False}},
        {"tool": [{"nome": "ora_attuale"}, {"nome": "calcola"}], "dopo_tool": {
            "modo": "ombra", "esito": "modello", "perche": "piu_tool", "ms": 0.2}},
        {"tool": [{"nome": "casa_comando"}], "dopo_tool": {"modo": "ombra",
                                                         "esito": "gia_pronta"}},
        {"tool": [{"nome": "calcola"}], "dopo_tool": {"modo": "attivo", "esito": "codice",
                                                    "tool": "calcola"}},
        {"tool": []},
    ]
    r = dt.riassunto(turni)
    verifica("riassunto: risposte, codice, attivo, già pronte, perché, ombra",
             (r["risposte"], r["codice"], r["attivo"], r["gia_pronte"], r["perche"],
              r["uguali"], r["diverse"], r["domande"], r["risparmio_p50_ms"], r["risparmio_s"])
             == (5, 3, 1, 1, [("piu_tool", 1)], 1, 1, 1, 1000, 1.8), str(r))
    t = dt.testo(r)
    verifica("riga di calliope stato", "frase del codice in 3" in t and "piu_tool ×1" in t
             and "risparmiabile p50 1000 ms" in t, t)
    verifica("riga senza misure", "nessuna risposta" in dt.testo(dt.riassunto([])))
    diverse = [turni[1]] * 25
    verifica("avviso con oltre il 5 % di frasi diverse",
             "ATTENZIONE" in dt.testo(dt.riassunto(diverse)))
    verifica("contrario: nessun avviso con le frasi uguali",
             "ATTENZIONE" not in dt.testo(dt.riassunto([turni[0]] * 25)))
    src = (RADICE / "calliope" / "stato.py").read_text(encoding="utf-8")
    verifica("calliope stato --turni: sezione e JSON",
             "dopo_tool_s1.testo(dopo_tool_r)" in src and '"dopo_tool": dopo_tool_r' in src)


def prova_script_dgx():
    """Lo script della DGX (prove/manuali/dopo_tool_dgx.py) a secco sui suoi turni finti."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dopo_tool_dgx", RADICE / "prove" / "manuali" / "dopo_tool_dgx.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    r = m.valuta(m._finti())
    verifica("script della DGX: coperti, già pronte, senza parole, perché",
             (r["coperti"], r["gia_pronte"], r["senza_parole"], dict(r["perche"])),
             (3, 1, 1, {"piu_tool": 1, "non_coperto": 1, "tool_fallito": 1,
                        "dubbio_proposta": 1}))
    verifica("script della DGX: risparmio stimato dai turni senza tool dello stesso giorno",
             (r["prima_frase_senza_tool"], r["risparmio_p50_s"]), (1.8, 0.9))


if __name__ == "__main__":
    prova_decisore()
    prova_sostanza()
    prova_brain_attivo()
    prova_brain_ombra()
    prova_config_e_ciclo()
    prova_riassunto()
    prova_script_dgx()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
