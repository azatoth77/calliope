import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco di brain.py: filtro thinking, chiamate scritte come testo, accumulo
dei tool_calls, taglio della storia e ciclo completo con un backend finto."""

from calliope.brain import Brain, TextCallGuard, ThinkFilter, merge_tool_deltas, strip_think
from calliope.config import Config
from calliope.tools.builtin import build_registry

errori = 0


def verifica(nome, ottenuto, atteso):
    global errori
    ok = ottenuto == atteso
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome} → {ottenuto!r}" + ("" if ok else f"  (atteso {atteso!r})"))


def prova_filtro():
    def filtra(pezzi):
        f = ThinkFilter()
        return "".join([f.feed(t) for t in pezzi] + [f.flush()])

    verifica("thinking spezzato", filtra(["<thin", "king>ciao</thin", "king> mondo", "!"]), " mondo!")
    verifica("think spezzato", filtra(["<thi", "nk>pensa", "</th", "ink>Ciao, come va?"]), "Ciao, come va?")
    verifica("due blocchi", filtra(["<think>a</think>X<thinking>b</thinking>Y"]), "XY")
    verifica("minore non tag", filtra(["3 < 5 e ", "<b>"]), "3 < 5 e <b>")
    verifica("strip_think", "".join(strip_think(["<think>", "pensa", "</think>", "Ciao"])), "Ciao")


def guardia(pezzi):
    g = TextCallGuard(build_registry().all_schemas())
    detto = [g.feed(p) for p in pezzi]
    detto.append(g.flush())
    return "".join(detto), g.call, detto


def prova_guardia():
    detto, call, _ = guardia(["Chi_", "parla()"])
    verifica("chi_parla() maiuscolo", (detto, call and call["name"], call and call["arguments"]),
             ("", "chi_parla", {}))
    detto, call, _ = guardia(["elenca_voci()\n", "Ho diverse voci a disposizione."])
    verifica("tool + testo", (detto, call and call["name"]), ("", "elenca_voci"))
    detto, call, _ = guardia(["`cambia_voce(voce=\"paola\")`"])
    verifica("argomento nome=\"x\"", call and call["arguments"], {"voce": "paola"})
    detto, call, _ = guardia(["cambia_voce('paola')"])
    verifica("argomento posizionale", call and call["arguments"], {"voce": "paola"})
    detto, call, _ = guardia(['cambia_voce({"voce": "serena"})'])
    verifica("argomento JSON", call and call["arguments"], {"voce": "serena"})
    detto, call, _ = guardia(["call:cambia", "_voce{voce:<|\"|>paola<|\"|>}\n",
                              "Ho cambiato la mia voce."])
    verifica("formato grezzo di gemma", (detto, call and call["name"], call and call["arguments"]),
             ("", "cambia_voce", {"voce": "paola"}))
    detto, call, _ = guardia(["call:chi_parla{}"])
    verifica("formato grezzo senza argomenti", call and call["arguments"], {})
    detto, call, _ = guardia(["chi_parla", "{}"])
    verifica("graffe senza call:", (detto, call and call["name"]), ("", "chi_parla"))
    detto, call, _ = guardia(["Ora_attuale{}\n", "Sono le dieci."])
    verifica("graffe + testo", (detto, call and call["name"]), ("", "ora_attuale"))
    detto, call, _ = guardia(["Chi_parla."])
    verifica("nome nudo", (detto, call and call["name"], call and call["arguments"]),
             ("", "chi_parla", {}))
    detto, call, _ = guardia(["cambia_voce{voce: \"paola\"}"])
    verifica("graffe con argomento", call and call["arguments"], {"voce": "paola"})
    detto, call, _ = guardia(["calliope", ".cambia_voce(voce=\"paola\")"])
    verifica("qualificatore «calliope.»", (detto, call and call["name"], call and call["arguments"]),
             ("", "cambia_voce", {"voce": "paola"}))
    detto, call, _ = guardia(["default_api.ora_attuale()"])
    verifica("qualificatore «default_api.»", (detto, call and call["name"]), ("", "ora_attuale"))
    detto, call, _ = guardia(["call", "_cambia_voce(voce='serena')"])
    verifica("prefisso «call_»", (call and call["name"], call and call["arguments"]),
             ("cambia_voce", {"voce": "serena"}))
    detto, call, pezzi = guardia(["Certo", ". Ecco una storia."])
    verifica("«Certo. Ecco…» passa", (detto, call), ("Certo. Ecco una storia.", None))
    detto, call, pezzi = guardia(["Venezia", " è una città."])
    verifica("parola sola: attende un token, poi passa", (pezzi[0], detto), ("", "Venezia è una città."))
    detto, call, _ = guardia(["calcola(300e9*2748)"])
    verifica("calcola come testo", (detto, call and call["name"], call and call["arguments"]),
             ("", "calcola", {"espressione": "300e9*2748"}))
    detto, call, pezzi = guardia(["Ora", " sono le dieci."])
    verifica("«Ora sono…» passa", (detto, call), ("Ora sono le dieci.", None))
    detto, call, pezzi = guardia(["Call", "iope sono io."])
    verifica("«Calliope…» passa", (detto, call), ("Calliope sono io.", None))
    detto, call, pezzi = guardia(["Chi", " sei tu?"])
    verifica("«Chi sei» passa", (detto, call), ("Chi sei tu?", None))
    verifica("«Chi sei» rilasciato al 2° token", pezzi[1], "Chi sei tu?")
    detto, call, pezzi = guardia(["Sono", " le dieci."])
    # Una parola sola si trattiene per un token (potrebbe essere «parola.tool(…)»)
    verifica("risposta normale al secondo token", (pezzi[0], pezzi[1]), ("", "Sono le dieci."))
    detto, call, _ = guardia(["registra_utente(nome=\"Mario\")"])
    verifica("anche i tool nascosti sono intercettati", (detto, call and call["name"]),
             ("", "registra_utente"))


class FintoDelta:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = type("F", (), {"name": name, "arguments": arguments})()


def prova_merge():
    acc = {}
    merge_tool_deltas(acc, [FintoDelta(0, id="call_abc", name="ora_", arguments="{}")])
    merge_tool_deltas(acc, [FintoDelta(0, name="attuale")])
    merge_tool_deltas(acc, [FintoDelta(1, id="call_def", name="chi_parla", arguments="{}")])
    verifica("merge", [acc[i]["name"] for i in sorted(acc)], ["ora_attuale", "chi_parla"])


class BackendFinto:
    """Risponde a copione: una lista di risposte, ciascuna una lista di eventi."""

    def __init__(self, copione):
        self.copione = list(copione)
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])   # copie: la storia cambia dopo
        yield from self.copione.pop(0)


class CtxFinto:
    current_speaker = None
    current_level = "ospite"


def brain_finto(copione, turni=10):
    cfg = Config()
    cfg.max_history_turns = turni
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.tool_ctx = type("T", (), {"speaker_ctx": CtxFinto()})()
    b.backend = BackendFinto(copione)
    return b


def prova_ciclo():
    b = brain_finto([
        [("text", "chi_parla()\nStai parlando con un ospite.")],   # chiamata come testo
        [("text", "Non ti riconosco ancora.")],
    ])
    detto = "".join(b.stream_reply("Chi ti parla?", "ospite"))
    verifica("ciclo: detto solo il finale", detto, "Non ti riconosco ancora.")
    verifica("ciclo: ruoli nella storia", [m["role"] for m in b.history],
             ["user", "assistant", "tool", "assistant"])

    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le dieci.")],
    ])
    detto = "".join(b.stream_reply("Che ore sono?", "ospite"))
    verifica("ciclo: tool_call vero", (detto, b.history[2]["name"]), ("Sono le dieci.", "ora_attuale"))


def prova_promessa():
    # 27/09: «devo prima cercarlo» senza tool → una spinta, poi il tool e la risposta
    b = brain_finto([
        [("text", "Per sapere l'ora devo prima controllarla.")],
        [("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le dieci.")],
    ])
    detto = "".join(b.stream_reply("Che ore sono?", "ospite"))
    verifica("promessa: spinta e tool", ("ora_attuale" in [t["nome"] for t in b.last_tools],
                                         detto.endswith("Sono le dieci.")), (True, True))
    verifica("promessa: spinta fuori dalla storia",
             any("non hai chiamato" in m.get("content", "") for m in b.history), False)
    # Una sola spinta: se promette di nuovo, si ferma
    b = brain_finto([[("text", "Lo cerco.")], [("text", "Lo cerco subito.")]])
    "".join(b.stream_reply("Cerca il file", "ospite"))
    verifica("promessa: una sola spinta", len(b.backend.visti), 2)
    # Risposta vuota dopo un tool con conferma: si dice la conferma
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "timer_imposta", "arguments": {"durata": "5 minuti"}}])],
        [("text", "")],
    ])
    b.tool_ctx.agenda = None
    b.tools.call = lambda *a, **k: '{"ok": true, "conferma": "Timer di 5 minuti avviato."}'
    detto = "".join(b.stream_reply("Metti un timer di 5 minuti", "ospite"))
    verifica("vuota dopo il tool: detta la conferma", detto, "Timer di 5 minuti avviato.")
    # Frase normale: nessuna spinta
    b = brain_finto([[("text", "Ciao, come posso aiutarti?")]])
    "".join(b.stream_reply("Ciao", "ospite"))
    verifica("promessa: frase normale, nessuna spinta", len(b.backend.visti), 1)


def prova_promessa_domanda():
    # «Lo apro?» senza tool nel turno: è una domanda di consenso, niente spinta (01/10)
    b = brain_finto([[("text", "Si chiama Compiti Matteo. Lo apro?")]])
    "".join(b.stream_reply("Come si chiama il file?", "amministra"))
    verifica("domanda di consenso: nessuna spinta", (len(b.backend.visti), b.last_rules), (1, []))


def prova_dichiarata():
    # 01/10: «Ho aperto il documento» senza nessun tool. La frase si trattiene, non si dice e
    # non entra nella storia; il modello riceve una spinta e chiama il tool
    b = brain_finto([
        [("text", "Ho aperto il documento \"Disdetta Palestra.docx\" sul portatile.")],
        [("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le dieci.")],
    ])
    detto = "".join(b.stream_reply("Sì grazie.", "amministra"))
    verifica("dichiarata all'inizio: non detta", detto, "Sono le dieci.")
    verifica("dichiarata: niente frase falsa nella storia",
             any("Ho aperto" in (m.get("content") or "") for m in b.history), False)
    # Senza la frase trattenuta davanti: con lei il modello la ripeteva (misura del 01/10)
    verifica("dichiarata: la spinta segue la domanda, la frase non si mostra",
             [m["role"] for m in b.backend.visti[1][-2:]], ["user", "system"])
    verifica("dichiarata: regola nel registro", b.rules_fired(), ["spinta_dichiarata"])
    # Già detta (non all'inizio): spinta, e se il tool arriva la frase esce dalla storia
    b = brain_finto([
        [("text", "Certo! Te lo dico subito, un momento solo. Ho acceso le luci in taverna.")],
        [("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Fatto.")],
    ])
    detto = "".join(b.stream_reply("Accendi la luce in taverna", "amministra"))
    verifica("dichiarata dopo: detta (era già partita), poi il tool",
             ("Ho acceso" in detto, b.last_tools[0]["nome"] if b.last_tools else None),
             (True, "ora_attuale"))
    verifica("dichiarata dopo: tolta dalla storia quando il tool arriva",
             any("Ho acceso" in (m.get("content") or "") for m in b.history), False)
    # Di nuovo «ho aperto» senza tool dopo la spinta (misura del 01/10, 2 volte su 3 senza
    # azione in sospeso): la frase falsa non si dice mai
    b = brain_finto([[("text", "Ho aperto il documento \"Disdetta Palestra.docx\".")],
                     [("text", "Ho aperto il documento \"Disdetta Palestra.docx\".")]])
    detto = "".join(b.stream_reply("Sì.", "amministra"))
    verifica("dichiarata due volte: mai detta, frase di ripiego",
             (detto, any("Ho aperto" in (m.get("content") or "") for m in b.history)),
             ("Non ci sono riuscita: puoi ripetere la richiesta?", False))
    # Dopo la spinta niente tool e niente testo: una frase vera, non il silenzio
    b = brain_finto([[("text", "Ho acceso le luci in taverna.")], [("text", "")]])
    detto = "".join(b.stream_reply("Accendi la luce in taverna", "amministra"))
    verifica("dichiarata e poi silenzio: frase di ripiego", detto,
             "Non ci sono riuscita: puoi ripetere la richiesta?")
    import json as _json
    # Con un tool d'azione riuscito nel turno nessuna spinta: «Ho impostato…» è vero
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "timer_imposta", "arguments": {"durata": "5 minuti"}}])],
        [("text", "Ho impostato tutto.")],
    ])
    b.tools.call = lambda *a, **k: _json.dumps({"ok": True, "conferma": "Timer avviato."})
    "".join(b.stream_reply("Metti un timer di 5 minuti", "amministra"))
    verifica("dichiarata dopo un tool d'azione vero: nessuna spinta", len(b.backend.visti), 2)
    # Dopo soli tool falliti (04/10, 26B: quattro «ricorda» con «non so chi sei», poi «Ho
    # salvato questa informazione.») o sola una lettura, la dichiarazione è falsa: spinta
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "ricorda", "arguments": {"fatto": "pizza"}}])],
        [("text", "Ho salvato questa informazione.")],
        [("text", "Non sono riuscita a ricordarlo.")],
    ])
    b.tools.call = lambda *a, **k: _json.dumps({"ok": False, "errore": "non so chi sei"})
    detto = "".join(b.stream_reply("Ricordati che mi piace la pizza.", "amministra"))
    verifica("dichiarata dopo soli tool falliti: non detta, spinta",
             (detto, len(b.backend.visti), "spinta_dichiarata" in b.rules_fired()),
             ("Non sono riuscita a ricordarlo.", 3, True))
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Ho impostato tutto.")],
        [("text", "Sono le 10.")],
    ])
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("dichiarata dopo una sola lettura: non detta, spinta",
             (detto, len(b.backend.visti)), ("Sono le 10.", 3))
    # Contrario: dopo una lettura una risposta normale passa, senza spinta
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le 10 e 3.")],
    ])
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("dopo una lettura, risposta normale: nessuna spinta",
             (detto, len(b.backend.visti)), ("Sono le 10 e 3.", 2))
    # Frase relativa: non è una dichiarazione
    b = brain_finto([[("text", "Il file che ho creato si chiama Compiti Matteo.pdf.")]])
    detto = "".join(b.stream_reply("Come si chiama il file?", "amministra"))
    verifica("«il file che ho creato…»: detta, nessuna spinta",
             (detto, len(b.backend.visti)), ("Il file che ho creato si chiama Compiti Matteo.pdf.", 1))


def _storia_taverna():
    """Il turno vero del 01/10: «chiudi taverna» → casa_comando(«spegni Taverna»)."""
    return [{"role": "user", "content": "Calliope, chiudi taverna."},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_0", "name": "casa_comando", "arguments": {"comando": "spegni Taverna"}}]},
            {"role": "tool", "tool_call_id": "call_0", "name": "casa_comando",
             "content": '{"ok": true, "fatto": "eseguito", "conferma": "Ho spento Taverna.", '
                        '"risposta_finale": "Ho spento Taverna."}'},
            {"role": "assistant", "content": "Ho spento Taverna."}]


def prova_ricordo():
    # 01/10, prova a voce: il ricordo di un'azione vera non è una dichiarazione falsa
    frase = ("Ho spento Taverna, quindi se intendi riaccenderla, posso eseguire il comando "
             "per riaccenderla.")
    b = brain_finto([[("text", frase)]])
    b.history = _storia_taverna()
    detto = "".join(b.stream_reply("Allora voglio che la accendi l'ultima stanza che abbiamo "
                                   "spento.", "amministra"))
    verifica("ricordo di un'azione vera: detto, nessuna spinta",
             (detto, len(b.backend.visti), b.rules_fired()), (frase, 1, ["dichiarata_ricordo"]))
    # Casi contrari: la stessa frase senza l'azione nella storia, e la dichiarazione nuda
    # uguale all'azione vecchia (come «TAVERNA» → «Ho acceso le luci in taverna», 01/10)
    b = brain_finto([[("text", frase)], [("text", "Non ci sono riuscita.")]])
    "".join(b.stream_reply("Accendi taverna.", "amministra"))
    verifica("stessa frase senza azioni prima: spinta", b.rules_fired(), ["spinta_dichiarata"])
    b = brain_finto([[("text", "Ho spento Taverna.")], [("text", "Non ci sono riuscita.")]])
    b.history = _storia_taverna()
    "".join(b.stream_reply("Spegni Taverna.", "amministra"))
    verifica("dichiarazione nuda uguale all'azione vecchia: spinta", b.rules_fired(),
             ["spinta_dichiarata"])


def prova_riferimento():
    # 01/10: «Scendila» dopo «Ho spento Taverna» → «a quale dispositivo?». L'ultimo
    # dispositivo della casa arriva al modello prima della domanda, nei turni dopo
    import json as _json
    import time as _time
    rif = {"cosa": "Taverna", "nome": "Taverna", "comando": "spegni Taverna"}
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "casa_comando", "arguments": {"comando": "spegni Taverna"}}])],
        [("text", "Ecco.")], [("text", "Ecco.")], [("text", "Ecco.")]])
    b._memory_message = lambda: [{"role": "system", "content": "RICORDI"}]
    b.tools.call = lambda *a, **k: _json.dumps({"ok": True, "conferma": "Ho spento Taverna.",
                                                "risposta_finale": "Ho spento Taverna.",
                                                "riferimento": rif})
    "".join(b.stream_reply("Calliope, chiudi taverna.", "amministra"))
    verifica("riferimento: il modello non vede il campo nel risultato",
             "riferimento" in b.history[2]["content"], False)
    verifica("riferimento: non nella stessa risposta", "riferimento_casa" in b.rules_fired(), False)
    "".join(b.stream_reply("Scendila.", "amministra"))
    visti = b.backend.visti[-1]
    verifica("riferimento: dopo i ricordi, subito prima della domanda, con nome e comando",
             (visti[-3]["content"], visti[-2]["role"], "Taverna (comando «spegni Taverna»)"
              in visti[-2]["content"], visti[-1]["content"]),
             ("RICORDI", "system", True, "Scendila."))
    verifica("riferimento: nel registro, fuori dalla storia",
             ("riferimento_casa" in b.rules_fired(),
              any("Contesto della casa" in (m.get("content") or "") for m in b.history)),
             (True, False))
    "".join(b.stream_reply("E adesso?", "amministra"))
    verifica("riferimento: vale anche il turno dopo (non si consuma)",
             any("Contesto della casa" in m["content"] for m in b.backend.visti[-1]
                 if m["role"] == "system"), True)
    b.reference["scade"] = _time.monotonic() - 1
    "".join(b.stream_reply("E adesso?", "amministra"))
    verifica("riferimento: scaduto, non c'è più",
             any("Contesto della casa" in m["content"] for m in b.backend.visti[-1]
                 if m["role"] == "system"), False)
    b.set_reference(rif)
    b.end_conversation()
    verifica("riferimento: azzerato quando si addormenta", b.reference, None)


def prova_riferimento_agenda():
    # 03/10: «Mettimi un timer di un secondo», poi «impostalo di un minuto» → un secondo timer.
    # L'ultima voce dell'agenda arriva al modello prima della domanda, nei turni dopo
    import json as _json
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "timer_imposta", "arguments": {"durata": "un secondo"}}])],
        [("text", "Fatto.")], [("text", "Ecco.")], [("text", "Ecco.")]])
    b._memory_message = lambda: [{"role": "system", "content": "RICORDI"}]
    b.tools.call = lambda *a, **k: _json.dumps({
        "ok": True, "conferma": "Va bene, timer di 1 secondo avviato.",
        "riferimento_agenda": {"cosa": "il timer «di 1 secondo»", "tool": "timer_imposta"}},
        ensure_ascii=False)
    "".join(b.stream_reply("Mettimi un timer di un secondo.", "amministra"))
    verifica("agenda: il modello non vede il campo nel risultato",
             any("riferimento_agenda" in (m.get("content") or "") for m in b.history), False)
    verifica("agenda: non nella stessa risposta", "riferimento_agenda" in b.rules_fired(), False)
    "".join(b.stream_reply("Adesso impostalo di un minuto.", "amministra"))
    visti = b.backend.visti[-1]
    verifica("agenda: subito prima della domanda, con la voce e il tool",
             (visti[-2]["role"], "il timer «di 1 secondo»" in visti[-2]["content"],
              "timer_imposta con cambia" in visti[-2]["content"], visti[-1]["content"]),
             ("system", True, True, "Adesso impostalo di un minuto."))
    verifica("agenda: nel registro, fuori dalla storia",
             ("riferimento_agenda" in b.rules_fired(),
              any("Contesto dell'agenda" in (m.get("content") or "") for m in b.history)),
             (True, False))
    b.cfg.llm_reti_spente = ["riferimento_agenda"]
    "".join(b.stream_reply("E adesso?", "amministra"))
    verifica("agenda: rete spegnibile",
             any("Contesto dell'agenda" in m["content"] for m in b.backend.visti[-1]
                 if m["role"] == "system"), False)
    b.cfg.llm_reti_spente = []
    b.end_conversation()
    verifica("agenda: azzerato quando si addormenta", b.agenda_reference, None)


def prova_sospeso():
    import json as _json
    offerta = {"domanda": "La apro?", "cosa": "la lettera «Disdetta Palestra»",
               "tool": "pc_apri_file", "argomenti": {"risultato": 1}}
    frase = "Ho preparato la lettera «Disdetta Palestra». La apro?"
    risultato = _json.dumps({"ok": True, "conferma": frase, "risposta_finale": frase,
                             "in_sospeso": offerta}, ensure_ascii=False)
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "documento_crea",
                     "arguments": {"formato": "word", "richiesta": "disdetta palestra"}}])],
        [("text", "Ho aperto la lettera.")],    # (non usata: la risposta finale chiude)
        [("calls", [{"id": "call_1", "name": "pc_apri_file", "arguments": {"risultato": 1}}])],
        [("text", "Ecco.")],
        [("text", "Prego.")],
    ])
    b.tools.call = lambda nome, *a, **k: (risultato if nome == "documento_crea"
                                          else '{"ok": true, "conferma": "Apro la lettera."}')
    # Ricordi di chi parla: l'azione in sospeso va DOPO di loro, subito prima della domanda
    b._memory_message = lambda: [{"role": "system", "content": "RICORDI"}]
    detto = "".join(b.stream_reply("Preparami una lettera di disdetta per la palestra", "amministra"))
    verifica("sospeso: la risposta finale del tool è detta", detto, frase)
    verifica("sospeso: il modello non vede il campo in_sospeso",
             "in_sospeso" in b.history[2]["content"], False)
    verifica("sospeso: ricordata", b.has_pending(), True)
    b.backend.copione.pop(0)
    "".join(b.stream_reply("Sì grazie.", "amministra"))
    visti = b.backend.visti[-2] if len(b.backend.visti) >= 2 else []
    sistema = [m["content"] for m in visti if m["role"] == "system"]
    verifica("sospeso: dopo i ricordi, subito prima della domanda",
             (visti[-2]["role"], "Azione in sospeso" in visti[-2]["content"], sistema[-2] == "RICORDI",
              visti[-1]["content"]),
             ("system", True, True, "Sì grazie."))
    verifica("sospeso: nomina il tool e gli argomenti",
             "pc_apri_file con risultato=1" in visti[-2]["content"]
             and "«La apro?»" in visti[-2]["content"], True)
    verifica("sospeso: nel registro", "azione_in_sospeso" in b.rules_fired(), True)
    verifica("sospeso: vale un turno solo", b.has_pending(), False)
    "".join(b.stream_reply("Grazie.", "amministra"))
    verifica("sospeso: il turno dopo non c'è più",
             any("Azione in sospeso" in m["content"] for m in b.backend.visti[-1]
                 if m["role"] == "system"), False)
    # Scade dopo azione_in_sospeso_s
    b.set_pending(offerta)
    b.pending["scade"] = 0
    verifica("sospeso: scaduto", b.has_pending(), False)
    # Solo se la risposta detta finisce con la domanda
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "pc_cerca_file", "arguments": {"testo": "bolletta"}}])],
        [("text", "Ho trovato la bolletta di agosto.")],
    ])
    b.tools.call = lambda *a, **k: _json.dumps({"ok": True, "in_sospeso": offerta})
    "".join(b.stream_reply("Cerca la bolletta", "amministra"))
    verifica("sospeso: niente domanda detta, niente azione in sospeso", b.has_pending(), False)
    # L'annuncio di un documento pronto in secondo piano con «La apro?»
    b = brain_finto([])
    b.record_announcement("Dario, è pronta la lettera «Disdetta». La apro?", offerta)
    verifica("sospeso: anche dall'annuncio", b.has_pending(), True)
    b.end_conversation()
    verifica("addormentata: storia e azione in sospeso azzerate", (b.history, b.has_pending()),
             ([], False))


def prova_rinomina():
    """Rinominare chiede conferma (02/10, «chiamami Davio, ma vorrei sapere chi sono»): la
    prima chiamata propone e basta, il nome cambia solo con la stessa chiamata nella
    risposta dopo; con un «no» in mezzo, una chiamata più tardi è di nuovo una proposta."""
    from calliope.tools.spec import ToolContext

    class Prof:
        def __init__(self, n):
            self.id, self.name = n.lower() + "-id", n

    class Voci:
        def __init__(self):
            self.users = {"Dario": Prof("Dario"), "Ilaria": Prof("Ilaria")}

        def known_speakers(self):
            return list(self.users)

        def get(self, n):
            return self.users.get(n)

        def rename(self, old, new):
            prof = self.users.pop(old)
            prof.name = new
            self.users[new] = prof
            return prof

    class Chi:
        current_speaker, current_level = "Dario", "amministra"

    davio = [("calls", [{"id": "call_0", "name": "rinomina_interlocutore",
                         "arguments": {"nome": "Davio"}}])]
    b = brain_finto([davio, [("text", "Ok.")], davio, [("text", "Fatto.")], [("text", "Va bene.")],
                     davio, [("text", "x")]])
    voci = Voci()
    chi = Chi()
    b.tool_ctx = ToolContext(cfg=b.cfg, speakers=voci, speaker_ctx=chi, speaker=None)
    detto = "".join(b.stream_reply("Calliope, chiamami Davio, ma vorrei sapere chi sono",
                                   "amministra"))
    verifica("rinomina: la prima chiamata chiede e basta",
             (detto, sorted(voci.users), b.has_pending()),
             ("Vuoi che ti chiami Davio d'ora in poi?", ["Dario", "Ilaria"], True))
    verifica("rinomina: nel registro", "rinomina_conferma" in b.rules_fired(), True)
    b.backend.copione.pop(0)            # «Ok.»: non usata, la domanda chiude il turno
    detto = "".join(b.stream_reply("Sì.", "amministra"))
    visti = b.backend.visti[-2]
    verifica("rinomina: azione in sospeso con il tool e il nome", any(
        "rinomina_interlocutore con nome=\"Davio\"" in m["content"] for m in visti
        if m["role"] == "system"), True)
    verifica("rinomina: con il «sì» nel turno dopo il nome cambia",
             (sorted(voci.users), chi.current_speaker), (["Davio", "Ilaria"], "Davio"))
    # Un «no»: il modello non richiama; più tardi una chiamata è di nuovo una proposta
    voci.rename("Davio", "Dario")
    chi.current_speaker = "Dario"
    b.backend.copione = [davio, [("text", "Ok.")], [("text", "Va bene, resto con Dario.")],
                         davio, [("text", "x")]]
    "".join(b.stream_reply("Chiamami Davio", "amministra"))
    b.backend.copione.pop(0)
    "".join(b.stream_reply("No, lascia stare.", "amministra"))
    # Dal 04/10 la proposta vale 3 turni (calliope/conferme.py): qui ne passano altri 3
    b.turn_number += 3
    detto = "".join(b.stream_reply("Chiamami Davio", "amministra"))
    verifica("rinomina: dopo un «no» e più di tre turni, di nuovo solo una proposta",
             (detto, sorted(voci.users)), ("Vuoi che ti chiami Davio d'ora in poi?",
                                           ["Dario", "Ilaria"]))
    # La domanda fatta a parole dal modello, senza il tool (04/10, 26B: «Chiamami Davide.» →
    # «Vuoi davvero che ti chiami Davide?», «Sì.» → la chiamata proponeva di nuovo)
    davide = [("calls", [{"id": "call_0", "name": "rinomina_interlocutore",
                          "arguments": {"nome": "Davide"}}])]
    b = brain_finto([[("text", "Vuoi davvero che ti chiami Davide?")], davide,
                     [("text", "Fatto.")]])
    voci, chi = Voci(), Chi()
    b.tool_ctx = ToolContext(cfg=b.cfg, speakers=voci, speaker_ctx=chi, speaker=None)
    "".join(b.stream_reply("D'ora in poi chiamami Davide.", "amministra"))
    "".join(b.stream_reply("Sì.", "amministra"))
    verifica("rinomina: la domanda detta senza tool vale come proposta, al «sì» rinomina",
             (sorted(voci.users), "rinomina_domanda_detta" in b.rules_fired()),
             (["Davide", "Ilaria"], True))
    # Contrario: la domanda era su un altro nome → solo una proposta
    b = brain_finto([[("text", "Vuoi davvero che ti chiami Davio?")], davide])
    voci, chi = Voci(), Chi()
    b.tool_ctx = ToolContext(cfg=b.cfg, speakers=voci, speaker_ctx=chi, speaker=None)
    "".join(b.stream_reply("D'ora in poi chiamami Davio.", "amministra"))
    detto = "".join(b.stream_reply("No, Davide.", "amministra"))
    verifica("rinomina: domanda detta su un altro nome, di nuovo solo una proposta",
             (detto, sorted(voci.users)), ("Vuoi che ti chiami Davide d'ora in poi?",
                                           ["Dario", "Ilaria"]))
    # Contrario: nella stessa risposta della domanda il tool non conferma (turno dopo solo)
    b = brain_finto([[("text", "Vuoi che ti chiami Davide?")], [("text", "Va bene.")],
                     [("text", "Altro?")], davide])
    voci, chi = Voci(), Chi()
    b.tool_ctx = ToolContext(cfg=b.cfg, speakers=voci, speaker_ctx=chi, speaker=None)
    "".join(b.stream_reply("Chiamami Davide.", "amministra"))
    "".join(b.stream_reply("No.", "amministra"))
    "".join(b.stream_reply("Che ore sono?", "amministra"))
    detto = "".join(b.stream_reply("Chiamami Davide.", "amministra"))
    verifica("rinomina: la domanda detta vale solo nella risposta subito dopo",
             (detto, sorted(voci.users)), ("Vuoi che ti chiami Davide d'ora in poi?",
                                           ["Dario", "Ilaria"]))


def prova_permessi():
    # Dal 03/10 l'ospite vede tutti i tool: il registro rifiuta a ogni esecuzione, con una
    # frase pronta (risposta_finale) e senza un'altra passata del modello
    from calliope.tools.registry import REFUSAL
    b = brain_finto([
        [("calls", [{"id": "call_0", "name": "cambia_voce", "arguments": {"voce": "paola"}}])],
        [("text", "Ho cambiato voce.")],
    ])
    b.tool_ctx.regole = []
    detto = "".join(b.stream_reply("Cambia voce in paola", "ospite"))
    verifica("permessi: tool vietato rifiutato, con la frase pronta e senza seconda passata",
             ("NON è stata eseguita" in b.history[2]["content"], detto, len(b.backend.visti),
              b.last_tools[0]["ok"], b.rules_fired()),
             (True, REFUSAL["ospite"], 1, False, ["permesso_livello"]))
    b = brain_finto([[("text", "cambia_voce(voce='paola')")], [("text", "Ho cambiato voce.")]])
    detto = "".join(b.stream_reply("Cambia voce in paola", "ospite"))
    verifica("permessi: vietato scritto come testo, non eseguito, detta la frase pronta",
             (detto, "NON è stata eseguita" in b.history[2]["content"]),
             (REFUSAL["ospite"], True))
    # Un familiare con un tool di chi amministra: un'altra frase
    b = brain_finto([[("calls", [{"id": "c", "name": "installa_avvia",
                                  "arguments": {"azione": "biblioteca"}}])]])
    verifica("permessi: familiare e tool di chi amministra",
             "".join(b.stream_reply("Sì, scaricala", "familiare")), REFUSAL["familiare"])
    # Il tool ammesso nella risposta dopo funziona come sempre (il rifiuto non avvelena)
    b = brain_finto([
        [("calls", [{"id": "c0", "name": "ricorda", "arguments": {"fatto": "x"}}])],
        [("calls", [{"id": "c1", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le dieci.")]])
    "".join(b.stream_reply("Ricordati che x", "ospite"))
    verifica("permessi: dopo un rifiuto il tool ammesso va",
             "".join(b.stream_reply("Che ore sono?", "ospite")), "Sono le dieci.")


def prova_prefisso_uguale():
    """Dal 03/10 il prefisso che arriva al modello (prompt di sistema e schemi dei tool, nello
    stesso ordine) è identico byte per byte per ospite, familiare e chi amministra: con un
    elenco di tool per livello Ollama rileggeva ~6000 token quando cambiava chi parla."""
    import json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ollama_finto import FakeOllama
    from pc_finto import FakePC
    from calliope.documenti.formato import FORMATI
    for motore in ("ollama", "openai"):
        cfg = Config()
        fake = FakeOllama(modelli=(cfg.llm_model,))
        fake.predefinita = {"content": "Ciao."}
        fake.avvia()
        try:
            cfg.llm_backend = motore
            cfg.llm_native_url = fake.url
            cfg.llm_base_url = fake.url + "/v1"
            # Tutti i tool che una casa può avere, anche quelli con livelli diversi per
            # l'ospite (volume del PC, domini della casa)
            reg = build_registry(biblioteca=True, citazioni=True, pc={"portatile": FakePC()},
                                 documenti=FORMATI, casa=True, schermi=True, agenti=True)
            b = Brain(cfg, reg, None)
            b.warmup("amministra")
            for livello in ("ospite", "familiare", "amministra", "ospite"):
                "".join(b.stream_reply("Ciao", livello))
            prefissi = [json.dumps([r["messages"][0], r.get("tools")], ensure_ascii=False)
                        for r in fake.richieste]
            verifica(f"prefisso ({motore}): system + tool identici per ogni livello e per il "
                     f"riscaldamento", (len(set(prefissi)), len(prefissi)), (1, 5))
            nomi = [t["function"]["name"] for t in fake.richieste[1]["tools"]]
            verifica(f"prefisso ({motore}): l'ospite vede anche i tool della famiglia",
                     all(n in nomi for n in ("ricorda", "lista_aggiungi", "pc_cerca_file",
                                             "installa_avvia", "schermo_gestisci")), True)
        finally:
            fake.ferma()


def prova_taglio():
    b = brain_finto([], turni=4)
    for i in range(5):
        b.history += [{"role": "user", "content": f"d{i}"},
                      {"role": "assistant", "content": "", "tool_calls": [
                          {"id": "c", "name": "ora_attuale", "arguments": {}}]},
                      {"role": "tool", "tool_call_id": "c", "name": "ora_attuale", "content": "{}"},
                      {"role": "assistant", "content": f"r{i}"}]
    b.history.append({"role": "user", "content": "d5"})
    b._trim_history()
    verifica("taglio: inizia con user", b.history[0]["role"], "user")
    verifica("taglio: turni rimasti", [m["content"] for m in b.history if m["role"] == "user"],
             ["d4", "d5"])
    prima = list(b.history)
    b._trim_history()
    verifica("taglio: a blocchi (niente taglio sotto la soglia)", b.history, prima)


def prova_richiesta_trattenuta():
    # 01/10, prova a voce: «Calliope, apri il PDF della spesa» → detto «Non ho trovato alcun
    # PDF associato alla spesa, potresti dirmi il nome del file?» e subito dopo «Ho trovato un
    # file chiamato Lista della spesa, lo apro?». La prima frase ora si trattiene: con la
    # spinta non si dice e non entra nella storia
    from prove.pc_finto import FakePC
    cerca = {"id": "call_0", "name": "pc_cerca_file", "arguments": {"testo": "spesa"}}

    def b_pc(copione):
        b = brain_finto(copione)
        b.tools = build_registry(pc={"portatile": FakePC()})
        b.tools.call = lambda *a, **k: '{"ok": true, "trovati": 1}'
        return b

    b = b_pc([
        [("text", "Non ho trovato alcun PDF associato alla spesa, "),
         ("text", "potresti dirmi il nome del file?")],
        [("calls", [cerca])],
        [("text", "Ho trovato un file chiamato Lista della spesa, lo apro?")],
    ])
    detto = "".join(b.stream_reply("apri il PDF della spesa", "familiare"))
    verifica("richiesta di un file: la frase senza tool non si dice", detto,
             "Ho trovato un file chiamato Lista della spesa, lo apro?")
    verifica("richiesta di un file: la frase non resta nella storia",
             any("Non ho trovato" in (m.get("content") or "") for m in b.history), False)
    verifica("richiesta di un file: regole nel registro", b.rules_fired(),
             ["richiesta_trattenuta"])
    # Testo e tool nella stessa passata: la frase si dice (dopo, con il tool)
    b = b_pc([[("text", "Cerco il file della spesa. "), ("calls", [cerca])],
              [("text", "Trovato.")]])
    detto = "".join(b.stream_reply("apri il PDF della spesa", "familiare"))
    verifica("richiesta di un file con il tool: la frase si dice",
             (detto, b.rules_fired()), ("Cerco il file della spesa. Trovato.", []))
    # Dopo la spinta di nuovo solo testo: questa volta si dice (una spinta sola)
    b = b_pc([[("text", "Quale file intendi?")], [("text", "Mi dici il nome del file?")]])
    detto = "".join(b.stream_reply("apri il PDF della spesa", "familiare"))
    verifica("richiesta di un file: dopo la spinta la risposta si dice", detto,
             "Mi dici il nome del file?")
    # Senza il PC (nessun pc_cerca_file) niente trattenuta
    b = brain_finto([[("text", "Non posso aprire file.")]])
    detto = "".join(b.stream_reply("apri il PDF della spesa", "familiare"))
    verifica("richiesta di un file senza PC: detta subito", (detto, len(b.backend.visti)),
             ("Non posso aprire file.", 1))

    # Latenza: una domanda normale rilascia la prima frase prima che il modello finisca
    class Lento:
        def __init__(self):
            self.finito = False
            self.visti = []

        def stream(self, messages, tools):
            self.visti.append(messages)
            yield "text", "Sono le dieci e un quarto, "
            yield "text", "una bella serata. "
            yield "text", "Altro?"
            self.finito = True

    for domanda in ("Che ore sono?", "Apri la finestra della cucina"):
        b = b_pc([])
        b.backend = Lento()
        g = b.stream_reply(domanda, "familiare")
        primo = next(g)
        verifica(f"latenza invariata su «{domanda}»: prima frase prima della fine",
                 (bool(primo), b.backend.finito), (True, False))
        "".join(g)


def prova_riscaldamento():
    """Il riscaldamento (02/10) manda il prefisso di una risposta vera: stesso prompt di
    sistema, stessi tool e stesse opzioni (num_ctx, think, keep_alive: se cambiano Ollama
    ricarica il modello). Con un «ciao» nudo la prima domanda elaborava ~4 600 token di
    prompt e tool: sul portatile prima frase 2,35 s contro 0,49 (DGX: 1,89 s)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ollama_finto import FakeOllama
    for motore in ("ollama", "openai"):
        cfg = Config()
        fake = FakeOllama(modelli=(cfg.llm_model,))
        fake.predefinita = {"content": "Sono le dieci."}
        fake.avvia()
        try:
            cfg.llm_backend = motore
            cfg.llm_native_url = fake.url
            cfg.llm_base_url = fake.url + "/v1"
            b = Brain(cfg, build_registry(), None)
            b.warmup("amministra")
            "".join(b.stream_reply("Che ore sono?", "amministra"))
            w, r = fake.richieste[0], fake.richieste[1]
            verifica(f"riscaldamento ({motore}): stesso prompt di sistema della risposta",
                     w["messages"][0] == r["messages"][0] and w["messages"][0]["role"] == "system",
                     True)
            verifica(f"riscaldamento ({motore}): stessi tool della risposta",
                     bool(w.get("tools")) and w.get("tools") == r.get("tools"), True)
            if motore == "ollama":
                verifica("riscaldamento: stesse opzioni (salvo num_predict), think e keep_alive",
                         ({k: v for k, v in w["options"].items() if k != "num_predict"},
                          w.get("think"), w.get("keep_alive")),
                         (r["options"], r.get("think"), r.get("keep_alive")))
                verifica("riscaldamento: genera una parola sola", w["options"].get("num_predict"), 1)
        finally:
            fake.ferma()


def prova_reti_spente():
    # 03/10: con llm_reti_spente (dal profilo del modello) le reti non scattano
    copione = [[("text", "chi_parla() Stai parlando con un ospite.")],
               [("text", "altro")]]
    b = brain_finto(copione)
    b.cfg.llm_reti_spente = ["textcallguard", "chiamata_in_mezzo"]
    detto = "".join(b.stream_reply("Chi ti parla?", "ospite"))
    verifica("textcallguard e chiamata_in_mezzo spente: il testo resta testo, nessun tool",
             (detto.startswith("chi_parla()"), b.last_tools, b.last_rules), (True, [], []))
    b = brain_finto([[("text", "Per sapere l'ora devo prima controllarla.")], [("text", "x")]])
    b.cfg.llm_reti_spente = ["spinta_promessa"]
    "".join(b.stream_reply("Che ore sono?", "ospite"))
    verifica("spinta_promessa spenta: nessuna seconda passata", (len(b.backend.visti),
                                                                 b.last_rules), (1, []))
    b = brain_finto([[("text", "Ho acceso la luce in taverna.")], [("text", "x")]])
    b.cfg.llm_reti_spente = ["tutte"]
    detto = "".join(b.stream_reply("Accendi la luce in taverna", "amministra"))
    verifica("tutte spente: la dichiarazione si dice, nessuna spinta",
             (detto, len(b.backend.visti), b.last_rules),
             ("Ho acceso la luce in taverna.", 1, []))
    b = brain_finto([[("text", "Ho acceso la luce in taverna.")],
                     [("calls", [{"id": "c", "name": "ora_attuale", "arguments": {}}])],
                     [("text", "Sono le dieci.")]])
    b.cfg.llm_reti_spente = ["spinta_promessa"]       # le altre accese: la rete c'è ancora
    "".join(b.stream_reply("Accendi la luce in taverna", "amministra"))
    verifica("spinta_dichiarata accesa se non è nell'elenco", "spinta_dichiarata" in b.last_rules,
             True)
    b = brain_finto([[("text", "x")]])
    b.cfg.llm_reti_spente = ["riferimento_casa", "azione_in_sospeso"]
    b.set_reference({"cosa": "Taverna", "comando": "spegni Taverna"})
    b.reference["turno"] = -1
    b.set_pending({"tool": "pc_apri_file", "argomenti": {"numero": 1}, "domanda": "Lo apro?"})
    "".join(b.stream_reply("Sì.", "amministra"))
    sistema = [m["content"] for m in b.backend.visti[0] if m["role"] == "system"]
    verifica("riferimento spento: niente messaggio della casa",
             any("Contesto della casa" in c for c in sistema), False)
    # Q6 (06/10): l'azione in sospeso è una rete di sicurezza (il consenso dipende da lei)
    verifica("azione in sospeso: resta accesa anche se un profilo la spegne",
             any("Azione in sospeso" in c for c in sistema), True)


def prova_nomi_tool_parlati():
    """03/10: «Che comando hai per le luci?» → «Io ho il comando casa_comando che…» veniva
    taciuta intera e Calliope restava muta. Ora il nome diventa parole; l'annuncio di una
    chiamata («Chiamo ora_attuale…») resta taciuto."""
    b = brain_finto([])
    # Nel registro di prova la casa non c'è: stessa forma con un tool sempre presente
    frase = ("Io ho il comando timer_imposta che mi permette di mettere un timer, ad esempio "
             "dicendomi quanto deve durare.")
    detta = b.speak_tool_names(frase)
    verifica("nome del tool detto a parole", detta, "Io ho il mio comando per i timer che mi "
             "permette di mettere un timer, ad esempio dicendomi quanto deve durare.")
    verifica("annuncio di una chiamata taciuto",
             b.speak_tool_names("Chiamo ora_attuale per sapere l'ora."), None)
    verifica("frase senza tool invariata", b.speak_tool_names("Sono le 10."), "Sono le 10.")
    verifica("nome nudo in mezzo", b.speak_tool_names(
        "Per sapere l'ora c'è ora_attuale, che è sempre giusta."),
        "Per sapere l'ora c'è il mio comando per l'ora, che è sempre giusta.")


def prova_conversazione_per_persona():
    """03/10 (analisi del comportamento): la storia passava da una persona all'altra, e un
    ospite si faceva ripetere la password del wifi chiesta da Dario. Ora la conversazione si
    chiude quando cambia chi parla e dopo storia_inattiva_s; i risultati riservati e personali
    restano nella storia solo come traccia o conferma."""
    import json as _json
    import time as _time

    class Prof:
        def __init__(self, pid):
            self.id = pid

    class Voci:
        def get(self, n):
            return {"Dario": Prof("dario-id"), "Bianca": Prof("bianca-id")}.get(n)

    class Chi:
        current_speaker, current_level = "Dario", "amministra"

    def nuovo(copione):
        b = brain_finto(copione)
        chi = Chi()
        b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": Voci()})()
        return b, chi

    b, chi = nuovo([[("text", "La password è Girasole.")], [("text", "Certo.")],
                    [("text", "Non lo so.")], [("text", "Ciao Bianca.")]])
    "".join(b.stream_reply("Qual è la password del wifi?", "amministra"))
    "".join(b.stream_reply("Grazie, ripetila.", "amministra"))
    verifica("stessa persona: la conversazione continua", len(b.history), 4)
    chi.current_speaker, chi.current_level = None, "ospite"
    "".join(b.stream_reply("Scusa, me la ripeti?", "ospite"))
    visti = b.backend.visti[-1]
    verifica("ospite dopo Dario: la storia di Dario non arriva al modello",
             (any("Girasole" in (m.get("content") or "") for m in visti),
              [m["role"] for m in b.history], "conversazione_altra_persona" in b.last_rules),
             (False, ["user", "assistant"], True))
    chi.current_speaker = "Bianca"
    b.set_pending({"tool": "pc_apri_file", "argomenti": {"risultato": 1}, "domanda": "Lo apro?"})
    "".join(b.stream_reply("Ciao.", "familiare"))
    verifica("Bianca dopo l'ospite: si riparte da capo, anche l'azione in sospeso",
             (len(b.history), any("Azione in sospeso" in (m.get("content") or "")
                                  for m in b.backend.visti[-1])), (2, False))
    # Rinomina: stesso profilo, stesso id, la conversazione continua
    b, chi = nuovo([[("text", "Ciao.")], [("text", "Sì.")]])
    "".join(b.stream_reply("Ciao.", "amministra"))
    b.tool_ctx.speakers.get = lambda n: Prof("dario-id")
    chi.current_speaker = "Davide"
    "".join(b.stream_reply("Mi senti?", "amministra"))
    verifica("rinomina (stesso id): la conversazione continua", len(b.history), 4)
    # Storia messa da fuori (banco di regressione): la prima risposta la adotta
    b, chi = nuovo([[("text", "Sono le 10.")]])
    b.history = [{"role": "user", "content": "Che ore sono?"},
                 {"role": "assistant", "content": "Sono le 9."}]
    "".join(b.stream_reply("E adesso?", "amministra"))
    verifica("storia iniziale: la prima risposta non la chiude", len(b.history), 4)
    # Scadenza: dopo storia_inattiva_s senza turni si riparte da capo
    b, chi = nuovo([[("text", "Uno.")], [("text", "Due.")], [("text", "Tre.")]])
    b.cfg.storia_inattiva_s = 300
    "".join(b.stream_reply("Uno?", "amministra"))
    b.last_turn_at = _time.monotonic() - 299
    "".join(b.stream_reply("Due?", "amministra"))
    verifica("entro la scadenza: continua", len(b.history), 4)
    b.last_turn_at = _time.monotonic() - 301
    "".join(b.stream_reply("Tre?", "amministra"))
    verifica("dopo la scadenza: storia chiusa", (len(b.history), "conversazione_scaduta"
                                                 in b.last_rules), (2, True))
    b.last_turn_at = _time.monotonic() - 400
    b.record_announcement("Dario, è scaduto il timer.")
    verifica("annuncio dopo la scadenza: non si attacca alla storia vecchia",
             [m["content"] for m in b.history], ["Dario, è scaduto il timer."])
    # Risultati personali e riservati: dopo la risposta solo la conferma o una traccia
    b, chi = nuovo([
        [("calls", [{"id": "c0", "name": "agenda_elenca", "arguments": {}}])],
        [("text", "Hai il dentista alle 17.")],
        [("calls", [{"id": "c1", "name": "promemoria_imposta",
                     "arguments": {"testo": "pane", "quando": "alle 18"}}])],
        [("text", "Va bene.")],
        [("calls", [{"id": "c2", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le 10.")]])
    risultati = {"agenda_elenca": {"voci": [{"appuntamento": "dentista", "quando": "oggi alle 17"}],
                                   "numero": 1},
                 "promemoria_imposta": {"ok": True, "promemoria": "pane", "quando": "oggi alle 18",
                                        "conferma": "Alle 18 ti ricordo il pane."},
                 "ora_attuale": {"ora": "10:00", "fuso": "locale"}}
    b.tools.call = lambda nome, *a, **k: _json.dumps(risultati[nome], ensure_ascii=False)
    visti_prima = None
    "".join(b.stream_reply("Cosa ho in agenda?", "amministra"))
    visti_prima = b.backend.visti[-1]
    verifica("personale: il modello vede il risultato intero nella risposta",
             any("dentista" in (m.get("content") or "") for m in visti_prima
                 if m["role"] == "tool"), True)
    tool = [m for m in b.history if m["role"] == "tool"]
    verifica("personale senza conferma: dopo la risposta resta una traccia neutra",
             ("dentista" in tool[0]["content"], "riservato" in tool[0]["content"]), (False, True))
    "".join(b.stream_reply("Ricordami il pane alle 18.", "amministra"))
    "".join(b.stream_reply("Che ore sono?", "amministra"))
    tool = {m["name"]: _json.loads(m["content"]) for m in b.history if m["role"] == "tool"}
    verifica("personale con conferma: resta solo la conferma",
             tool["promemoria_imposta"], {"ok": True, "conferma": "Alle 18 ti ricordo il pane."})
    verifica("non personale: invariato", tool["ora_attuale"], risultati["ora_attuale"])
    from calliope.tools.spec import ToolSpec
    b, chi = nuovo([[("calls", [{"id": "c0", "name": "segreto_finto", "arguments": {}}])],
                    [("text", "Il numero è 1234.")]])
    b.tools.register(ToolSpec(name="segreto_finto", description="x", parameters={
        "type": "object", "properties": {}}, func=lambda ctx: {"ok": True, "numero": "1234",
                                                                "conferma": "È 1234."},
        riservato=True, levels=frozenset({"amministra"})))
    b.tools.call = lambda nome, *a, **k: _json.dumps({"ok": True, "numero": "1234",
                                                      "conferma": "È 1234."})
    "".join(b.stream_reply("Che numero è?", "amministra"))
    tool = [m for m in b.history if m["role"] == "tool"][0]
    verifica("riservato: traccia neutra, nemmeno la conferma", "1234" in tool["content"], False)


def prova_chiamata_in_mezzo():
    """03/10: il 4B scrive la chiamata in mezzo alla frase («Ora sono ora_attuale.»), dove
    TextCallGuard non guarda; con c4e0f3d diventava «Ora sono il mio comando per l'ora.» e
    il tool non partiva. Ora la frase non si dice: il tool si esegue (se non vuole argomenti
    obbligatori, o li ha scritti) o arriva una spinta; mai una risposta muta."""
    b = brain_finto([[("text", "Ora sono ora_attuale.")], [("text", "Sono le 10:00.")]])
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("in mezzo, senza argomenti: eseguito, la frase non si dice",
             (detto, [t["nome"] for t in b.last_tools], b.last_rules,
              any("ora_attuale." in (m.get("content") or "") for m in b.history
                  if m["role"] == "assistant")),
             ("Sono le 10:00.", ["ora_attuale"], ["chiamata_in_mezzo"], False))
    b = brain_finto([[("text", "Certo. Chiamo calliope_stato(cosa=\"sa_fare\") per dirtelo.")],
                     [("text", "So fare tante cose.")]])
    detto = "".join(b.stream_reply("Cosa sai fare?", "amministra"))
    verifica("in mezzo, con argomenti: eseguito con gli argomenti; la frase prima si dice",
             (detto, b.last_tools[0]["nome"], b.last_tools[0]["argomenti"]),
             ("Certo. So fare tante cose.", "calliope_stato", {"cosa": "sa_fare"}))
    b = brain_finto([[("text", "Per il timer uso timer_imposta, va bene?")],
                     [("calls", [{"id": "c", "name": "timer_imposta",
                                  "arguments": {"durata": "5 minuti"}}])],
                     [("text", "Fatto: 5 minuti.")]])
    b.tool_ctx.agenda = None
    detto = "".join(b.stream_reply("Metti un timer di 5 minuti", "amministra"))
    verifica("in mezzo, argomenti obbligatori mancanti: spinta, la frase non si dice",
             ("timer_imposta" in detto, b.last_rules[:1], len(b.backend.visti),
              "Non hai chiamato nessun tool" in b.backend.visti[1][-1]["content"]),
             (False, ["spinta_nome_tool"], 3, True))
    b = brain_finto([[("text", "Uso timer_imposta.")], [("text", "Uso timer_imposta.")]])
    detto = "".join(b.stream_reply("Metti un timer", "amministra"))
    verifica("di nuovo dopo la spinta: mai muta",
             (detto, b.last_rules), ("Non ci sono riuscita: puoi ripetere la richiesta?",
                                     ["spinta_nome_tool", "nome_tool_ripetuto"]))
    b = brain_finto([[("text", "Ho il comando timer_imposta, che mette un timer.")]])
    detto = "".join(b.stream_reply("Che comando hai per i timer?", "amministra"))
    verifica("domanda sui comandi: è una spiegazione, passa (main.py la dice a parole)",
             (detto, b.last_tools, b.last_rules),
             ("Ho il comando timer_imposta, che mette un timer.", [], []))
    b = brain_finto([[("calls", [{"id": "c", "name": "ora_attuale", "arguments": {}}])],
                     [("text", "Con ora_attuale ho visto che sono le 10.")]])
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("dopo un tool vero: la frase passa (main.py la dice a parole)",
             detto, "Con ora_attuale ho visto che sono le 10.")
    b = brain_finto([[("text", "Adesso sono le dieci in punto. "), ("text", "Ti serve altro?")]])
    pezzi = list(b.stream_reply("Che ore sono?", "amministra"))
    verifica("senza nomi di tool: le frasi escono appena finite", pezzi,
             ["Adesso sono le dieci in punto. ", "Ti serve altro?"])


def prova_sospeso_per_persona():
    """03/10: l'azione in sospeso vale solo per la persona a cui era rivolta la domanda."""
    class Prof:
        def __init__(self, pid):
            self.id = pid

    class Voci:
        def get(self, n):
            return {"Dario": Prof("dario-id"), "Bianca": Prof("bianca-id")}.get(n)

    class Chi:
        current_speaker, current_level = "Dario", "amministra"

    b = brain_finto([[("text", "Va bene.")], [("text", "Va bene.")]])
    chi = Chi()
    b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": Voci()})()
    b.cfg.storia_inattiva_s = 0
    b.conv_owner = None                     # una conversazione dell'ospite, già aperta
    chi.current_speaker = None
    b.set_pending({"tool": "pc_apri_file", "argomenti": {"risultato": 1}, "domanda": "Lo apro?"})
    chi.current_speaker = "Dario"
    b.conv_owner = "dario-id"               # (stessa conversazione: solo il sospeso conta)
    "".join(b.stream_reply("Sì.", "amministra"))
    verifica("sospeso: il «sì» di un'altra persona non conferma",
             (any("Azione in sospeso" in (m.get("content") or "") for m in b.backend.visti[-1]),
              "sospeso_altra_persona" in b.last_rules), (False, True))
    b.set_pending({"tool": "pc_apri_file", "argomenti": {"risultato": 1}, "domanda": "Lo apro?"})
    "".join(b.stream_reply("Sì.", "amministra"))
    verifica("sospeso: il «sì» della stessa persona sì",
             any("Azione in sospeso" in (m.get("content") or "") for m in b.backend.visti[-1]),
             True)


def prova_continuazione():
    """03/10: la ricerca promessa si fa con una continuazione, senza «Cerca pure.» finto
    dell'utente nella storia."""
    b = brain_finto([[("text", "Devo fare una ricerca.")], [("text", "Il Tevere è lungo 405 km.")]])
    b.cfg.llm_reti_spente = ["spinta_promessa"]
    "".join(b.stream_reply("Quanto è lungo il Tevere?", "amministra"))
    detto = "".join(b.stream_continuation("amministra", context="PASSAGGI"))
    visti = b.backend.visti[-1]
    verifica("continuazione: detta, nessun utente finto, contesto dopo la risposta",
             (detto, [m["role"] for m in b.history], visti[-1]["content"]),
             ("Il Tevere è lungo 405 km.", ["user", "assistant", "assistant"], "PASSAGGI"))


def prova_budget_contesto():
    """03/10: la storia si taglia anche in token rispetto a llm_num_ctx, e i risultati
    lunghi dei turni vecchi si riducono alla conferma o a una traccia."""
    import json as _json
    b = brain_finto([[("text", "Ok.")]] * 12)
    lungo = _json.dumps({"passaggi": "x" * 2000, "cosa_fare": "rispondi in breve"})
    for i in range(3):
        b.history += [{"role": "user", "content": f"domanda {i}"},
                      {"role": "assistant", "content": "", "tool_calls": [
                          {"id": f"c{i}", "name": "biblioteca_cerca", "arguments": {}}]},
                      {"role": "tool", "tool_call_id": f"c{i}", "name": "biblioteca_cerca",
                       "content": lungo},
                      {"role": "assistant", "content": f"risposta {i}"}]
    "".join(b.stream_reply("E poi?", "amministra"))
    tool = [m["content"] for m in b.history if m["role"] == "tool"]
    verifica("risultati vecchi ridotti, quello del turno precedente intero",
             [len(t) > 1000 for t in tool], [False, False, True])
    b = brain_finto([[("text", "Ok.")]] * 3)
    b.cfg.llm_num_ctx = 1                     # budget minimo (1000 token, ~3500 caratteri)
    for i in range(8):
        b.history += [{"role": "user", "content": f"domanda {i} " + "y" * 600},
                      {"role": "assistant", "content": "z" * 600}]
    "".join(b.stream_reply("Ultima?", "amministra"))
    verifica("storia tagliata in token: resta sotto il budget, a blocchi, la domanda c'è",
             (len(_json.dumps(b.history)) < 3600, b.history[0]["role"],
              b.history[-2]["content"], "storia_tagliata" in b.last_rules),
             (True, "user", "Ultima?", True))


def prova_vuoto_dopo_lettura():
    """04/10: risposta vuota dopo un tool di sola lettura → una seconda passata (la conferma
    di data_oggi perdeva «e domani?»); di nuovo vuota → la conferma; dopo un'azione riuscita
    la conferma subito, senza seconda passata."""
    import json as _json
    from calliope.tools.spec import ToolSpec
    data = [("calls", [{"id": "c0", "name": "data_oggi", "arguments": {}}])]
    b = brain_finto([data, [("text", "")], [("text", "Domani è lunedì 5 ottobre.")]])
    detto = "".join(b.stream_reply("Cerca la data di oggi e deduci quella di domani.",
                                   "amministra"))
    verifica("vuoto dopo lettura: seconda passata, detta la risposta intera",
             (detto, "vuoto_seconda_passata" in b.last_rules, len(b.backend.visti),
              "risposta era vuota" in b.backend.visti[-1][-1]["content"],
              [m["role"] for m in b.history]),
             ("Domani è lunedì 5 ottobre.", True, 3, True, ["user", "assistant", "tool",
                                                            "assistant"]))
    b = brain_finto([data, [("text", "")], [("text", "")]])
    detto = "".join(b.stream_reply("Che giorno è oggi?", "amministra"))
    verifica("vuoto due volte: la conferma, una sola seconda passata",
             (detto.startswith("Oggi è"), len(b.backend.visti),
              "conferma_al_posto_del_vuoto" in b.last_rules), (True, 3, True))
    b = brain_finto([[("calls", [{"id": "c0", "name": "azione_finta", "arguments": {}}])],
                     [("text", "")]])
    b.tools.register(ToolSpec(name="azione_finta", description="x", parameters={
        "type": "object", "properties": {}}, func=lambda ctx: {"ok": True,
                                                                "conferma": "Timer avviato."},
        risk="azione", levels=frozenset({"ospite", "familiare", "amministra"})))
    detto = "".join(b.stream_reply("Metti un timer.", "amministra"))
    verifica("vuoto dopo un'azione: la conferma subito",
             (detto, len(b.backend.visti), "vuoto_seconda_passata" in b.last_rules),
             ("Timer avviato.", 2, False))
    b = brain_finto([data, [("text", "")]])
    b.cfg.llm_reti_spente = ["vuoto_seconda_passata"]
    detto = "".join(b.stream_reply("Che giorno è oggi?", "amministra"))
    verifica("rete vuoto_seconda_passata spenta: la conferma come prima",
             (detto.startswith("Oggi è"), len(b.backend.visti)), (True, 2))



def prova_ora_vecchia():
    """04/10: il risultato di ora_attuale dei turni prima diventa «ora di allora» (il 4B
    ridiceva «Sono le 21:50» a «No, intendevo che ore sono»); gli altri risultati no."""
    import json as _json
    b = brain_finto([[("text", "Sono le 13:00.")]])
    b.history = [{"role": "user", "content": "Che ore sono?"},
                 {"role": "assistant", "content": "", "tool_calls": [
                     {"id": "c0", "name": "ora_attuale", "arguments": {}},
                     {"id": "c1", "name": "data_oggi", "arguments": {}}]},
                 {"role": "tool", "tool_call_id": "c0", "name": "ora_attuale",
                  "content": _json.dumps({"ora": "21:50", "da_dire": "Sono le 21:50."})},
                 {"role": "tool", "tool_call_id": "c1", "name": "data_oggi",
                  "content": _json.dumps({"data": "04/10/2026"})},
                 {"role": "assistant", "content": "Sono le 21:50."}]
    "".join(b.stream_reply("No, intendevo che ore sono.", "amministra"))
    visti = {m.get("name"): _json.loads(m["content"]) for m in b.backend.visti[-1]
             if m["role"] == "tool"}
    verifica("ora vecchia: «ora di allora», senza «da_dire»; data_oggi invariata",
             (visti["ora_attuale"].get("ora_di_allora"), "ora" in visti["ora_attuale"],
              "da_dire" in visti["ora_attuale"], visti["data_oggi"]),
             ("21:50", False, False, {"data": "04/10/2026"}))


prova_filtro()
prova_reti_spente()
prova_riscaldamento()
prova_guardia()
prova_richiesta_trattenuta()
prova_merge()
prova_ciclo()
prova_promessa()
prova_promessa_domanda()
prova_dichiarata()
prova_ricordo()
prova_riferimento()
prova_riferimento_agenda()
prova_sospeso()
prova_rinomina()
prova_permessi()
prova_prefisso_uguale()
prova_taglio()
prova_nomi_tool_parlati()
prova_conversazione_per_persona()
prova_chiamata_in_mezzo()
prova_sospeso_per_persona()
prova_continuazione()
prova_budget_contesto()
prova_vuoto_dopo_lettura()
prova_ora_vecchia()
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
