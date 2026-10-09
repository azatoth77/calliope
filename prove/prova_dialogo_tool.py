"""
Il dialogo tra i tool e i modelli (09/10/2026, docs/ricerche/2026-10-09-dialogo-tool.md).

    python prove/prova_dialogo_tool.py

Caso vero della DGX (09/10 08:19): `web_cerca({'tipo': 'notizie'})` → «argomenti non validi:
_web_cerca() missing 1 required positional argument: 'domanda'» e «ho avuto un piccolo
intoppo, riprovo subito» senza riprovare, quattro volte. A secco, senza modello né rete:
- **ogni tool registrato** con argomenti obbligatori, chiamato vuoto: errore strutturato
  (`ok` false, `errore` in parole, `campo`, `argomenti` con tipo e valori ammessi, `esempio`,
  `correggibile`, `cosa_fare`), nessuna traccia, funzione mai eseguita;
- obbligatorio mancante con un altro argomento presente (il caso vero), argomento sconosciuto,
  conversioni di forma (maiuscole, accenti, numeri come testo) e i contrari (valore fuori dai
  valori ammessi: decide il tool; obbligatorio con un predefinito nella funzione: lo completa il
  tool; funzione con soli **kw: lo schema vale solo per le estensioni);
- eccezioni del tool: mai la traccia, errore di programmazione non correggibile, ValueError
  correggibile con la sua riga; la forma vecchia {errore} diventa {ok: false, errore};
- Brain: giro di correzione (la frase «riprovo subito» non si dice, il modello rilegge e
  richiama), la domanda alla persona si dice dopo il primo giro, errore non correggibile
  detto senza giri, tetto
  dei giri, frase d'attesa una volta, errore del registro fuori dalla busta dei dati non fidati;
- strumenti dell'agente: obbligatorio assente, contenuto vuoto ammesso, eccezione in una riga.
"""
import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope.tools import dialogo  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext, ToolSpec  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


def ctx_vuoto():
    return ToolContext(cfg=None, speakers=None, speaker_ctx=None, speaker=None)


def registro_completo():
    from prove.pc_finto import FakePC
    return build_registry(biblioteca=True, pc={"portatile": FakePC()},
                          documenti=("word", "excel", "pdf"), casa=True, schermi=True,
                          agenti=True, ufficio=("fattura",), archivio=True, web=True,
                          conversazioni=True, immagini={}, minori_tool=True, allegati=True,
                          cassetto=True)


def strutturato(r: dict) -> bool:
    return (r.get("ok") is False and isinstance(r.get("errore"), str)
            and "Traceback" not in r["errore"] and "positional argument" not in r["errore"]
            and isinstance(r.get("cosa_fare"), str) and "correggibile" in r)


def prova_tutti_i_tool():
    reg = registro_completo()
    con_obbligatori = [s for s in reg._tools.values() if (s.parameters or {}).get("required")]
    verifica("registro completo: tool con argomenti obbligatori", len(con_obbligatori) >= 30,
             str(len(con_obbligatori)))
    male = []
    for spec in con_obbligatori:
        eseguito = []
        orig = spec.func

        # La stessa firma della funzione vera: la validazione la legge
        def spia(*a, _o=orig, **k):
            eseguito.append(1)
            return _o(*a, **k)
        spia.__signature__ = __import__("inspect").signature(orig)
        reg.register(dataclasses.replace(spec, func=spia))
        ctx = ctx_vuoto()
        try:
            r = json.loads(reg.call(spec.name, {}, ctx))
        finally:
            reg.register(dataclasses.replace(spec, func=orig))
        req = spec.parameters["required"]
        ok = (strutturato(r) and r.get("correggibile") is True and r.get("campo") in req
              and set(r.get("argomenti") or ()) == set(req)
              and (r.get("esempio") or {}).get("tool") == spec.name
              and set((r["esempio"].get("argomenti") or {})) >= set(req)
              and not eseguito and "tool_argomenti_mancanti" in ctx.regole
              and ctx.errore_registro is True)
        if not ok:
            male.append((spec.name, r, eseguito))
    verifica(f"chiamata vuota a ognuno dei {len(con_obbligatori)} tool: errore strutturato, "
             "niente esecuzione", not male, str(male[:2]))
    # Le enum dello schema nell'errore
    r = json.loads(reg.call("schermo_gestisci", {}, ctx_vuoto()))
    verifica("valori ammessi dallo schema nell'errore",
             "valori_ammessi" in r["argomenti"]["azione"], str(r.get("argomenti")))


class _WebFinto:
    def __init__(self):
        self.cercate = []

    def cerca(self, domanda, tipo="web", **_):
        self.cercate.append((domanda, tipo))
        return {"ok": True, "risultati": []}


def prova_caso_vero():
    reg = registro_completo()
    # Dal 09/10 (caso vero delle 11:03, tre giri fermati) con tipo «notizie» la domanda è
    # facoltativa: senza tema, le ultime notizie generali
    ctx = ctx_vuoto()
    ctx.web = _WebFinto()
    r = json.loads(reg.call("web_cerca", {"tipo": "notizie"}, ctx))
    verifica("web_cerca({'tipo': 'notizie'}): parte, le notizie generali",
             r.get("ok") is True and ctx.web.cercate == [("notizie", "notizie")]
             and "notizie_generali" in ctx.regole, f"{r} {ctx.web.cercate}")
    verifica("…nello schema «domanda» non è più obbligatoria, e la descrizione lo dice",
             "domanda" not in (reg.get("web_cerca").parameters.get("required") or ())
             and "facoltativa" in reg.get("web_cerca").description)
    verifica("…nessun errore per il registro né per la frase d'attesa",
             reg.mancanti("web_cerca", {"tipo": "notizie"}) == [])
    # Con tipo «web» (o senza tipo) la domanda serve: lo stesso errore dello schema
    ctx = ctx_vuoto()
    ctx.web = _WebFinto()
    r = json.loads(reg.call("web_cerca", {"tipo": "web"}, ctx))
    verifica("web_cerca({'tipo': 'web'}): manca «domanda», detto in parole",
             strutturato(r) and r["campo"] == "domanda" and "«domanda»" in r["errore"]
             and "per le notizie è facoltativa" in r["errore"] and r["correggibile"] is True
             and not ctx.web.cercate and "tool_argomenti_mancanti" in ctx.regole
             and ctx.errore_registro is True, r.get("errore"))
    verifica("…con la descrizione dell'argomento presa dalla descrizione del tool",
             "motore di ricerca" in r["argomenti"]["domanda"].get("cosa", ""),
             str(r["argomenti"]))
    verifica("…l'esempio tiene «tipo» e mette «domanda» al suo posto",
             r["esempio"]["argomenti"] == {"tipo": "web", "domanda": "<domanda>"},
             str(r["esempio"]))
    verifica("…cosa_fare: richiamare con le parole della persona, chiedere solo se mancano",
             "Richiama subito web_cerca" in r["cosa_fare"] and "Chiedi alla persona solo se"
             in r["cosa_fare"], r["cosa_fare"])
    c = ctx_vuoto()
    c.web = _WebFinto()
    c.user_text = "Cercami una cosa"
    r = json.loads(reg.call("web_cerca", {}, c))
    verifica("web_cerca({}): tipo «web», stesso errore, con la frase della persona",
             r.get("correggibile") is True and "(«Cercami una cosa»)" in r["cosa_fare"]
             and not c.web.cercate, r.get("cosa_fare"))
    verifica("contrario: con la domanda niente da dire",
             reg.mancanti("web_cerca", {"domanda": "notizie di oggi"}) == [])
    r = json.loads(reg.call("web_cerca", {"query": "notizie"}, ctx_vuoto()))
    verifica("argomento sconosciuto: detto, con gli argomenti veri",
             strutturato(r) and "«query» non esiste" in r["errore"]
             and "domanda, tipo" in r["errore"], r.get("errore"))
    verifica("…e l'esempio non lo ripete", "query" not in r["esempio"]["argomenti"])


def prova_forma_e_contrari():
    visti = []
    spec = ToolSpec(name="prova_forma", description="prova. modo: «uno» o «due».",
                    parameters={"type": "object", "properties": {
                        "modo": {"type": "string", "enum": ["uno", "due", "età"]},
                        "quanti": {"type": "integer"}, "tutti": {"type": "boolean"},
                        "testo": {"type": "string"}}, "required": ["testo"]},
                    func=lambda ctx, testo, modo="uno", quanti=1, tutti=False:
                    visti.append((testo, modo, quanti, tutti)) or {"ok": True})
    reg = build_registry()
    reg.register(spec)
    ctx = ctx_vuoto()
    r = json.loads(reg.call("prova_forma", {"testo": "x", "modo": " DUE ", "quanti": "3",
                                            "tutti": "sì"}, ctx))
    verifica("forma: maiuscole e spazi, numero e sì come testo",
             r.get("ok") and visti[-1] == ("x", "due", 3, True)
             and "tool_argomento_forma" in ctx.regole, f"{r} {visti}")
    reg.call("prova_forma", {"testo": "x", "modo": "eta"}, ctx_vuoto())
    verifica("forma: senza accento → il valore ammesso con l'accento", visti[-1][1] == "età",
             str(visti[-1]))
    r = json.loads(reg.call("prova_forma", {"testo": "x", "modo": "boh", "quanti": "molti"},
                            ctx_vuoto()))
    verifica("contrario: fuori dai valori ammessi o non numero → decide il tool",
             r.get("ok") and visti[-1][1:3] == ("boh", "molti"), str(visti[-1]))
    r = json.loads(reg.call("prova_forma", {"modo": "uno", "testo": "  "}, ctx_vuoto()))
    verifica("obbligatorio vuoto con un altro argomento: errore", strutturato(r)
             and r["campo"] == "testo", str(r))
    # Obbligatori con un valore predefinito nella funzione (lavoro_affida, compiti_aiuto)
    completo = ToolSpec(name="prova_completa", description="",
                        parameters={"type": "object", "properties": {
                            "compito": {"type": "string"}, "proposta": {"type": "string"}},
                            "required": ["compito"]},
                        func=lambda ctx, compito="", proposta="": {"ok": True, "c": compito})
    reg.register(completo)
    verifica("contrario: un obbligatorio che il tool completa da sé passa",
             json.loads(reg.call("prova_completa", {"proposta": "L1"}, ctx_vuoto())).get("ok"))
    verifica("…ma la chiamata senza nessun argomento no (06/10)",
             reg.mancanti("prova_completa", {}) == ["compito"])
    # Soli **kw: il tool di Calliope decide; un'estensione ha lo schema come contratto
    for fonte, atteso in ((None, True), ("estensione", False)):
        s = ToolSpec(name="est_x" if fonte else "kw_x", description="",
                     parameters={"type": "object", "properties": {
                         "citta": {"type": "string"}, "giorni": {"type": "integer"}},
                         "required": ["citta"]},
                     func=lambda ctx, _n="x", **kw: {"ok": True}, fonte=fonte,
                     classe="sicuro")
        reg.register(s)
        r = json.loads(reg.call(s.name, {"giorni": 2}, ctx_vuoto()))
        verifica(f"soli **kw ({fonte or 'tool di Calliope'}): "
                 + ("passa" if atteso else "obbligatorio mancante"),
                 bool(r.get("ok")) == atteso, str(r))


def prova_eccezioni():
    reg = build_registry()

    def rotta(ctx, cosa):
        return {}["chiave"]

    def valore(ctx, cosa):
        raise ValueError("la data «31 febbraio» non esiste")

    def multi(ctx, cosa):
        raise RuntimeError('Traceback (most recent call last):\n  File "x.py"')
    for n, f in (("rotta", rotta), ("valore", valore), ("multi", multi)):
        reg.register(ToolSpec(name=n, description="", parameters={
            "type": "object", "properties": {"cosa": {"type": "string"}},
            "required": ["cosa"]}, func=f))
    ctx = ctx_vuoto()
    r = json.loads(reg.call("rotta", {"cosa": "x"}, ctx))
    verifica("errore di programmazione: «si è fermato», non correggibile, niente nomi interni",
             strutturato(r) and r["correggibile"] is False and "chiave" not in r["errore"]
             and "Non richiamarlo" in r["cosa_fare"] and "tool_errore_interno" in ctx.regole,
             str(r))
    r = json.loads(reg.call("valore", {"cosa": "x"}, ctx_vuoto()))
    verifica("ValueError: la sua riga, correggibile",
             r["correggibile"] is True and "31 febbraio" in r["errore"], str(r))
    r = json.loads(reg.call("multi", {"cosa": "x"}, ctx_vuoto()))
    verifica("una traccia nel messaggio non arriva al modello",
             "Traceback" not in json.dumps(r) and 'File "' not in r["errore"], str(r))
    verifica("forma vecchia {errore} → {ok: false, errore}",
             dialogo.uniforma({"errore": "x"}) == {"ok": False, "errore": "x"}
             and dialogo.uniforma({"ok": True}) == {"ok": True})


def _brain_con_web(risultato_web=None):
    from prove.prova_politica import prepara
    b, _, _ = prepara()
    cercate = []

    def web(ctx, domanda, tipo="web"):
        cercate.append((domanda, tipo))
        return risultato_web or {"ok": True, "trovato": True, "risultati": [
            {"sito": "Notiziario", "titolo": "Notizia", "testo": "Oggi piove."}]}
    # Uno schema con «domanda» obbligatoria (com'era web_cerca fino al 09/10): il giro di
    # correzione è uguale per ogni tool
    spec = b.tools.get("web_cerca")
    b.tools.register(dataclasses.replace(spec, func=web, parameters=dict(
        spec.parameters, required=["domanda"])))
    copione = b.backend
    copione.messaggi = []
    stream = copione.stream

    def registra(messages, tools):
        copione.messaggi.append(list(messages))
        yield from stream(messages, tools)
    copione.stream = registra
    return b, cercate


def prova_giro_di_correzione():
    from prove.prova_politica import turno, chiama, testo
    b, cercate = _brain_con_web()
    attese = []
    b.on_tool_start = attese.append
    r = turno(b, "raccontami le ultime novità della giornata",
              chiama("web_cerca", {"tipo": "notizie"}),
              testo("Ho avuto un piccolo intoppo, riprovo subito."),
              chiama("web_cerca", {"tipo": "notizie", "domanda": "notizie di oggi"}),
              testo("Secondo Notiziario oggi piove."))
    verifica("caso vero: «riprovo subito» non si dice, il modello richiama e risponde",
             r == "Secondo Notiziario oggi piove." and cercate == [("notizie di oggi",
                                                                     "notizie")],
             f"{r!r} {cercate}")
    regole = b.rules_fired()
    verifica("…regole tool_argomenti_mancanti e correzione_tool, una volta",
             "tool_argomenti_mancanti" in regole and regole.count("correzione_tool") == 1,
             str(regole))
    verifica("…la frase d'attesa del tool solo con la chiamata giusta",
             len(attese) == 1 and "internet" in attese[0], str(attese))
    nudge = [m for ms in b.backend.messaggi for m in ms if m.get("role") == "system"
             and "Il tool web_cerca non è partito" in str(m.get("content"))
             and "«domanda»" in str(m.get("content"))]
    verifica("…il modello ha avuto l'errore in parole nella spinta", bool(nudge))
    tool_msg = [m for m in b.history if m.get("role") == "tool"]
    verifica("…l'errore del registro non è nella busta dei dati non fidati",
             "dato_non_fidato" not in tool_msg[0]["content"]
             and "fallito_senza_dato" in regole, tool_msg[0]["content"][:120])
    ultimi = b.last_tools
    verifica("…nel registro dei turni il primo tool è segnato correggibile",
             ultimi[0].get("correggibile") is True and not ultimi[0]["ok"] and ultimi[1]["ok"],
             str(ultimi))

    # La domanda alla persona: al primo giro aspetta (il 4B chiedeva il dato appena detto),
    # dopo la spinta si dice
    b, cercate = _brain_con_web()
    r = turno(b, "raccontami le novità", chiama("web_cerca", {"tipo": "notizie"}),
              testo("Quanti minuti?"), testo("Di quale argomento vuoi le notizie?"))
    verifica("domanda alla persona dopo l'errore: al primo giro aspetta, dopo la spinta si dice",
             r == "Di quale argomento vuoi le notizie?"
             and b.rules_fired().count("correzione_tool") == 1 and not cercate,
             f"{r} {b.rules_fired()}")

    # Tetto: il modello continua a promettere
    b, cercate = _brain_con_web()
    r = turno(b, "raccontami le novità", chiama("web_cerca", {"tipo": "notizie"}),
              testo("Riprovo subito."), testo("Riprovo ancora."), testo("Non ci riesco."),
              testo("Altro."))
    verifica("tetto dei giri (2): poi la frase si dice, niente giro infinito",
             r == "Non ci riesco." and b.rules_fired().count("correzione_tool") == 2, r)

    # Caso vero delle 11:03 (09/10): il modello richiama subito, sbagliato di nuovo, senza
    # frasi in mezzo. Ogni passata dopo l'errore è un giro: dopo i 2 giri l'ultima passata è
    # senza tool, con l'errore davanti (prima si andava avanti fino a max_tool_turns)
    b, cercate = _brain_con_web()
    sbagliata = chiama("web_cerca", {"tipo": "notizie"})
    r = turno(b, "le ultime notizie", sbagliata, sbagliata, sbagliata,
              testo("Di quale argomento vuoi le notizie?"),
              chiama("web_cerca", {"tipo": "notizie", "domanda": "notizie"}))
    regole = b.rules_fired()
    ultima = b.backend.messaggi[-1]
    verifica("richiamate subito sbagliate: dopo 2 giri di correzione niente quarta chiamata",
             r == "Di quale argomento vuoi le notizie?" and not cercate
             # la prima eseguita, le due identiche dopo con il suo esito (09/10,
             # `chiamata_ripetuta`)
             and regole.count("tool_argomenti_mancanti") == 1
             and regole.count("chiamata_ripetuta") == 2
             and "correzioni_esaurite" in regole and len(b.backend.messaggi) == 4,
             f"{r!r} {cercate} {regole} {len(b.backend.messaggi)}")
    verifica("…l'ultima passata ha l'errore e «non richiamarlo»",
             any("non è partito neanche questa volta" in str(m.get("content"))
                 and "«domanda»" in str(m.get("content")) for m in ultima
                 if m.get("role") == "system"), str([m for m in ultima
                                                     if m.get("role") == "system"][-1:])[:300])
    # Contrario: corretta al secondo giro → nessun tetto
    b, cercate = _brain_con_web()
    r = turno(b, "le ultime notizie", sbagliata, sbagliata,
              chiama("web_cerca", {"tipo": "notizie", "domanda": "notizie"}),
              testo("Secondo Notiziario oggi piove."))
    verifica("contrario: corretta entro i giri → la ricerca parte, niente correzioni_esaurite",
             r == "Secondo Notiziario oggi piove." and cercate == [("notizie", "notizie")]
             and "correzioni_esaurite" not in b.rules_fired(), f"{r!r} {b.rules_fired()}")
    # Contrario: con tool_correzioni_max = 3 il terzo giro c'è
    b, cercate = _brain_con_web()
    b.cfg.tool_correzioni_max = 3
    r = turno(b, "le ultime notizie", sbagliata, sbagliata, sbagliata,
              chiama("web_cerca", {"tipo": "notizie", "domanda": "notizie"}),
              testo("Secondo Notiziario oggi piove."))
    verifica("contrario: tool_correzioni_max = 3 → la quarta chiamata parte",
             r == "Secondo Notiziario oggi piove." and len(cercate) == 1
             and "correzioni_esaurite" not in b.rules_fired(), f"{r!r} {b.rules_fired()}")

    # Errore non correggibile: lo si dice subito, nessun giro
    def rotta(ctx, domanda, tipo="web"):
        raise KeyError("x")
    b, _ = _brain_con_web()
    b.tools.register(dataclasses.replace(b.tools.get("web_cerca"), func=rotta))
    r = turno(b, "notizie?", chiama("web_cerca", {"domanda": "notizie"}),
              testo("Adesso non ci sono riuscita."))
    verifica("contrario: errore interno non correggibile → detto subito, nessun giro",
             r == "Adesso non ci sono riuscita." and "correzione_tool" not in b.rules_fired()
             and "tool_errore_interno" in b.rules_fired(), f"{r} {b.rules_fired()}")

    # Frase d'attesa quando i giri si allungano: una volta
    b, _ = _brain_con_web()
    b.cfg.tool_correzione_avviso_s = 0.0
    attese = []
    b.on_tool_start = attese.append
    turno(b, "novità?", chiama("web_cerca", {"tipo": "notizie"}), testo("Riprovo."),
          testo("Riprovo."), testo("Niente."))
    verifica("frase d'attesa dei giri: una sola, tra quelle preparate",
             len(attese) == 1 and attese[0] in dialogo.FRASI_CORREZIONE
             and "correzione_avviso" in b.rules_fired(), str(attese))
    verifica("…e si sintetizza all'avvio con gli annunci",
             set(dialogo.FRASI_CORREZIONE) <= set(b.tools.announcements()))
    # Rete spenta da un profilo: come prima
    b, _ = _brain_con_web()
    b.cfg.llm_reti_spente = ["correzione_tool"]
    r = turno(b, "novità?", chiama("web_cerca", {"tipo": "notizie"}), testo("Riprovo subito."))
    verifica("rete correzione_tool spenta: la frase si dice com'era",
             r == "Riprovo subito." and "correzione_tool" not in b.rules_fired(), r)


def prova_agente():
    from calliope.agenti.ciclo import STRUMENTI_CODICE
    args, err = dialogo.controlla_strumento("scrivi_file", STRUMENTI_CODICE,
                                            {"percorso": "a.py"})
    verifica("agente: scrivi_file senza contenuto → errore con esempio",
             err is not None and err["campo"] == "contenuto" and "esempio" in err
             and "Richiama scrivi_file" in err["cosa_fare"], str(err))
    _, err = dialogo.controlla_strumento("scrivi_file", STRUMENTI_CODICE,
                                         {"percorso": "__init__.py", "contenuto": ""})
    verifica("agente: contrario, contenuto vuoto ammesso (un file vuoto)", err is None)
    _, err = dialogo.controlla_strumento("leggi_file", STRUMENTI_CODICE,
                                         {"percorso": "a.py", "da_carattere": "100"})
    verifica("agente: numero come testo convertito", err is None)
    e = dialogo.errore_strumento("esegui_python", OSError("disco pieno\nriga 2"))
    verifica("agente: eccezione in una riga con il tipo",
             e["ok"] is False and e["errore"] == "esegui_python non è riuscito: OSError: disco "
                                                 "pieno" and "cosa_fare" in e, str(e))


def main():
    prova_tutti_i_tool()
    prova_caso_vero()
    prova_forma_e_contrari()
    prova_eccezioni()
    prova_giro_di_correzione()
    prova_agente()
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
