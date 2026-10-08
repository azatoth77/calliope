import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il turno dopo un annuncio o un risultato, a secco (07/10/2026 sera, casi veri della DGX con il
26B, qui con nomi di fantasia).

1. **«Fammene un PDF» dopo il risultato di un lavoro** («Ho metto un pdf.» → pc_cerca_file, la
   lista dei PDF del PC): i dati del turno LAVORO_MSG (regola `riferimento_lavoro`) solo con
   un lavoro finito di chi parla, recente, nominato negli ultimi messaggi; mai per un altro, un
   programma, un lavoro vecchio o con la rete spenta. documento_crea con il lavoro di mezzo:
   una spinta, una volta, solo se il documento parla del lavoro (`spinta_documento_lavoro`).
   Le descrizioni di pc_cerca_file, documento_crea e lavoro_stato rimandano a lavoro_risultato.
2. **«Quale apro?» con le date** (pc_cerca_file): l'azione in sospeso dice la data e l'ora di
   modifica di ogni file (oggi, ieri, il giorno) e che il numero 1 è il più recente; i
   risultati sono ordinati dal più recente per ogni esecutore.
3. **Il timer già suonato** (caso delle 15:45: a «Che tempo farà domani a Milano?» anche
   timer_imposta(cambia=togli, durata=due minuti)): il riferimento dell'agenda cade quando la
   voce non c'è più (`riferimento_agenda_finito`), e un cambio di una voce dell'agenda senza le
   parole del tool chiede «Non me l'hai chiesto…» anche con la conversazione pulita
   (`politica_cambio_non_chiesto`); i contrari («toglici due minuti», il «sì» alla domanda).
4. **riferire**: «Se vuoi più dettagli, chiedimi di leggertelo.» (frase del codice in coda a
   lavoro_risultato) non è un'indicazione del dato; un'indicazione vera del dato resta fermata.
5. **Prefisso scaldato dopo un cambio del prompt di sistema** (modalità Star Trek, tono della
   casa: il turno dopo rileggeva ~15k token, 5,9 s): il riscaldamento parte in un thread solo
   se il prompt è cambiato (`prefisso_scaldato`).

    python prove\\prova_dopo_annunci.py
"""

import dataclasses
import datetime
import time
from types import SimpleNamespace

from calliope import politica, riferire
from calliope.agenti.servizio import titolo_detto
from calliope.brain import Brain, LAVORO_MSG
from calliope.config import Config, cambia_modalita
from calliope.documenti.formato import FORMATI
from calliope.tools import documenti as td
from calliope.tools import pc as tp
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.pc_finto import FakePC
from prove.prova_politica import ChiParla, Copione, Persone, chiama, prepara, testo, turno

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  [{dettaglio}]" if dettaglio else ""),
          flush=True)


def sezione(nome):
    print(f"\n── {nome} ──", flush=True)


class Registra(Copione):
    """Il modello finto che ricorda i messaggi ricevuti."""
    def __init__(self):
        super().__init__()
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from super().stream(messages, tools)

    def warmup(self, messages, tools):
        self.scaldati = getattr(self, "scaldati", 0) + 1
        return {"prompt": 10}


TITOLO = ("Esegui una ricerca approfondita sui vantaggi e gli svantaggi delle pompe di calore "
          "per una casa, con i costi, gli incentivi e i consumi")
DETTO = titolo_detto(TITOLO)            # come lo dicono l'annuncio e lavoro_risultato


def lavoro(persona="dario", tipo="ricerca", fine_s=60, stato="fatto", lid="L2"):
    return SimpleNamespace(id=lid, persona=persona, tipo=tipo, stato=stato, titolo=TITOLO,
                           fine=time.time() - fine_s)


def brain_lavori(lavori, storia_titolo=True):
    cfg = Config()
    cfg.storia_inattiva_s = 0
    reg = build_registry(agenti=True, documenti=FORMATI, pc={"portatile": FakePC()})
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=ChiParla("Dario", "amministra"),
                      speaker=None, lavori=SimpleNamespace(lavori=list(lavori)))
    b = Brain(cfg, reg, ctx)
    b.backend = Registra()
    b.conv_owner = "dario"
    b.last_turn_at = time.monotonic()
    annuncio = (f"Dario, ho finito «{DETTO}»: 11 sezioni. Lo apro?" if storia_titolo
                else "Dario, ho finito un lavoro.")
    b.history = [{"role": "user", "content": "Fai una ricerca sulle pompe di calore."},
                 {"role": "assistant", "content": "Ci lavoro in secondo piano."},
                 {"role": "user", "content": "Quanto fa 17 per 23?"},
                 {"role": "assistant", "content": "391. " + annuncio, "_fonte": "agente"}]
    return b


def dati_lavoro(b) -> bool:
    """Nell'ultima richiesta al modello c'è LAVORO_MSG."""
    testa = LAVORO_MSG.split("«")[0]
    return any(testa in str(m.get("content") or "") for m in b.backend.visti[-1])


def prova_lavoro():
    sezione("1. «Fammene un PDF» dopo il risultato di un lavoro")
    b = brain_lavori([lavoro()])
    turno(b, "Ho metto un pdf.", testo("Va bene."))
    verifica("lavoro finito di chi parla, nominato: dati del turno con l'id",
             dati_lavoro(b) and "riferimento_lavoro" in b.last_rules
             and any("lavoro L2" in str(m.get("content")) for m in b.backend.visti[-1]),
             str(b.last_rules))
    verifica("il lavoro per documento_crea in questa risposta",
             (b.tool_ctx.lavoro_turno or {}).get("lavoro") == "L2")
    for nome, lavori, titolo in (
            ("di un'altra persona", [lavoro(persona="bianca")], True),
            ("un programma", [lavoro(tipo="codice")], True),
            ("finito da più di mezz'ora", [lavoro(fine_s=3600)], True),
            ("non riuscito", [lavoro(stato="errore")], True),
            ("titolo non detto negli ultimi messaggi", [lavoro()], False),
            ("nessun lavoro", [], True)):
        b = brain_lavori(lavori, titolo)
        turno(b, "Fammene un PDF.", testo("Va bene."))
        verifica(f"contrario, {nome}: niente dati del turno", not dati_lavoro(b)
                 and "riferimento_lavoro" not in b.last_rules and b.tool_ctx.lavoro_turno is None)
    b = brain_lavori([lavoro()])
    for _ in range(5):
        b.history += [{"role": "user", "content": "Che ore sono?"},
                      {"role": "assistant", "content": "Sono le 16."}]
    turno(b, "Fammene un PDF.", testo("Va bene."))
    verifica("contrario, dieci messaggi dopo l'annuncio: niente dati del turno",
             not dati_lavoro(b))
    b = brain_lavori([lavoro()])
    b.cfg.llm_reti_spente = ["riferimento_lavoro"]
    turno(b, "Fammene un PDF.", testo("Va bene."))
    verifica("rete spenta (profilo): niente dati del turno", not dati_lavoro(b))
    # documento_crea: la spinta una volta, solo per un documento sul lavoro
    rif = {"lavoro": "L2", "titolo": DETTO, "avvisato": False,
           "parole": sorted(__import__("calliope.provenienza", fromlist=["x"]).parole(TITOLO))}
    ctx = SimpleNamespace(lavoro_turno=rif, regole=[], documenti=None)
    r = td._documento_crea(ctx, "word", "Ricerca sui vantaggi e svantaggi delle pompe di calore",
                           "Ricerca pompe di calore")
    verifica("documento_crea sul lavoro appena detto: la spinta verso lavoro_risultato",
             not r.get("ok") and "lavoro_risultato" in r.get("cosa_fare", "")
             and "L2" in r.get("cosa_fare", "") and "spinta_documento_lavoro" in ctx.regole, r)
    r = td._documento_crea(ctx, "word", "Ricerca sui vantaggi e svantaggi delle pompe di calore")
    verifica("richiamato nella stessa risposta: si va avanti (qui: documenti non disponibili)",
             r.get("errore") == "documenti non disponibili", r)
    ctx = SimpleNamespace(lavoro_turno=dict(rif, avvisato=False), regole=[], documenti=None)
    r = td._documento_crea(ctx, "pdf", "Lettera di disdetta della palestra")
    verifica("contrario: una lettera qualunque non riceve la spinta",
             r.get("errore") == "documenti non disponibili" and not ctx.regole, r)
    # Le descrizioni
    reg = build_registry(agenti=True, documenti=FORMATI, pc={"portatile": FakePC()})
    d = {n: reg.get(n).description for n in ("pc_cerca_file", "documento_crea", "lavoro_stato",
                                             "lavoro_risultato")}
    verifica("descrizioni: pc_cerca_file e documento_crea rimandano a lavoro_risultato",
             "lavoro_risultato" in d["pc_cerca_file"] and "lavoro_risultato" in d["documento_crea"])
    verifica("descrizioni: lavoro_stato non per il risultato di un lavoro nominato",
             "pompe di calore" in d["lavoro_stato"] and "pompe di calore" in d["lavoro_risultato"])
    reg = build_registry(documenti=FORMATI, pc={"portatile": FakePC()})
    verifica("contrario: senza agenti nessun rimando a un tool che non c'è",
             "lavoro_risultato" not in reg.get("pc_cerca_file").description
             and "lavoro_risultato" not in reg.get("documento_crea").description)


def prova_date():
    sezione("2. «Quale apro?» con le date di modifica")
    adesso = datetime.datetime(2026, 10, 7, 16, 0)
    found = [{"nome": "visura", "modificato": "2026-10-07T15:23"},
             {"nome": "diagnosi", "modificato": "2026-10-06T18:02"},
             {"nome": "contratto", "modificato": "2026-08-06T09:05"},
             {"nome": "vecchio", "modificato": "2025-12-30T10:31"},
             {"nome": "senza data", "modificato": None}]
    e = tp._elenco_sospeso(found, adesso)
    verifica("oggi, ieri, il giorno, l'anno se non è questo", "1 = visura (modificato oggi alle "
             "15:23)" in e and "2 = diagnosi (modificato ieri alle 18:02)" in e
             and "3 = contratto (modificato il 6 agosto alle 9:05)" in e
             and "il 30 dicembre 2025 alle 10:31" in e, e)
    verifica("il numero 1 è il più recente, detto al modello", "più recente" in e)
    verifica("senza data: solo il nome", "5 = senza data" in e and "5 = senza data (" not in e, e)

    class Disordinato(FakePC):
        def _cerca(self, testo, tipo, dal, al, massimo):
            return [{"nome": "a", "estensione": "pdf", "percorso": "x", "modificato": "2026-09-01T10:00"},
                    {"nome": "b", "estensione": "pdf", "percorso": "y", "modificato": "2026-10-07T10:00"},
                    {"nome": "c", "estensione": "pdf", "percorso": "z", "modificato": None}]
    r = Disordinato().cerca_file("dario", "x", "pdf")
    verifica("ogni esecutore: dal più recente, senza data in fondo",
             [x["nome"] for x in r["risultati"]] == ["b", "a", "c"], r["risultati"])
    # Il tool vero con il PC finto: la domanda e l'azione in sospeso
    b, _, _ = prepara()
    ctx = b.tool_ctx
    ctx.speaker_ctx = ChiParla("Dario", "amministra")
    ctx.pc = {"portatile": FakePC()}
    res = tp._pc_cerca_file(ctx, "", "pdf")
    sosp = res.get("in_sospeso") or {}
    verifica("pc_cerca_file: le date nella proposta, non nella frase detta",
             "modificato" in sosp.get("cosa", "") and "modificato" not in res.get("conferma", ""),
             f"{res.get('conferma')} | {sosp.get('cosa')}")


class Agenda:
    def __init__(self, voci):
        self.voci = dict(voci)

    def get(self, i):
        return self.voci.get(i)


def prova_timer():
    sezione("3. il timer già suonato e il cambio non chiesto")
    rif = {"cosa": "il timer «di 2 minuti»", "tool": "timer_imposta", "id": 7}
    # Riferimento: c'è finché la voce c'è
    b, eseguiti, _ = prepara()
    b.tool_ctx.speaker_ctx = ChiParla("Dario", "amministra")
    b.tool_ctx.agenda = Agenda({7: {"id": 7}})
    b.set_agenda_reference(rif)
    turno(b, "Aggiungi un minuto.", testo("Va bene."))
    verifica("timer ancora attivo: il contesto dell'agenda c'è",
             "riferimento_agenda" in b.last_rules, str(b.last_rules))
    b.tool_ctx.agenda.voci.clear()                 # il timer è suonato
    turno(b, "Che ore sono?", testo("Sono le 15."))
    verifica("timer suonato: il contesto cade (riferimento_agenda_finito)",
             "riferimento_agenda" not in b.last_rules
             and "riferimento_agenda_finito" in b.last_rules
             and b.agenda_reference is None, str(b.last_rules))
    # Il caso vero, conversazione pulita (niente meteo dal web di mezzo)
    b, eseguiti, _ = prepara()
    b.tool_ctx.speaker_ctx = ChiParla("Dario", "amministra")
    b.tool_ctx.agenda = Agenda({7: {"id": 7}})
    b.set_agenda_reference(rif)
    r = turno(b, "Che tempo farà domani a Milano?",
              chiama("timer_imposta", {"cambia": "togli", "durata": "due minuti"}),
              testo("Domani a Milano pioverà."))
    verifica("caso vero a secco: timer_imposta(cambia=togli) non eseguito",
             not any(n == "timer_imposta" for n, _ in eseguiti), f"{eseguiti} {r!r}")
    verifica("…con la regola politica_cambio_non_chiesto e la domanda",
             "politica_cambio_non_chiesto" in b.rules_fired() and "Non me l'hai chiesto" in r
             and "tolga due minuti al timer" in r, f"{b.rules_fired()} {r!r}")
    r = turno(b, "Sì.", chiama("timer_imposta", {"cambia": "togli", "durata": "due minuti"}),
              testo("Fatto."))
    verifica("contrario: il «sì» alla domanda lo esegue",
             any(n == "timer_imposta" for n, _ in eseguiti), f"{eseguiti} {r!r}")
    for frase in ("Toglici due minuti.", "Aggiungi cinque minuti al timer.",
                  "Impostalo di un minuto.", "Spostalo di dieci minuti."):
        b, eseguiti, _ = prepara()
        b.tool_ctx.speaker_ctx = ChiParla("Dario", "amministra")
        turno(b, frase, chiama("timer_imposta", {"cambia": "togli", "durata": "due minuti"}),
              testo("Fatto."))
        verifica(f"contrario: «{frase}» → eseguito", any(n == "timer_imposta"
                                                         for n, _ in eseguiti), str(b.last_rules))
    b, eseguiti, _ = prepara()
    b.tool_ctx.speaker_ctx = ChiParla("Dario", "amministra")
    turno(b, "Che tempo farà domani?", chiama("timer_imposta", {"durata": "5 minuti"}),
          testo("Fatto."))
    verifica("un timer nuovo (senza cambia) resta come prima: eseguito",
             any(n == "timer_imposta" for n, _ in eseguiti))
    cl = politica.CLASSI["promemoria_imposta"]
    d = politica.decidi("promemoria_imposta", {"cambia": "imposta", "testo": "il forno",
                                               "quando": "alle 9"}, cl,
                        politica.Turno(testo="Che tempo fa?"))
    verifica("promemoria spostato senza chiederlo: la domanda",
             d.regola == "politica_cambio_non_chiesto" and "sposti il promemoria" in d.domanda,
             str(d))
    d = politica.decidi("promemoria_imposta", {"cambia": "imposta", "testo": "il forno",
                                               "quando": "alle 9"}, cl,
                        politica.Turno(testo="Spostalo alle 9."))
    verifica("contrario: «Spostalo alle 9.» → eseguito", d.esito == "esegui", str(d))


def prova_riferire():
    sezione("4. riferire: la frase del codice in coda al risultato")
    c = riferire.Contesto(frozenset({"agente"}), [("agente", "Per approfondire leggete i "
                                                             "dettagli nel capitolo tre.")],
                          "Di quello della pompa di calore, sì.", "")
    g = riferire.giudica(riferire.FRASE_PIU_DETTAGLI, c)
    verifica("«Se vuoi più dettagli, chiedimi di leggertelo.» passa", g.esito == riferire.OK,
             g.esito)
    c = riferire.Contesto(frozenset({"agente"}), [("agente", "Per completare chiama il servizio "
                                                             "Solari al numero verde.")],
                          "Ok.", "")
    g = riferire.giudica("Chiama il servizio Solari appena puoi.", c)
    verifica("contrario: un'indicazione del dato resta fermata", g.esito == "uscita_istruzione",
             g.esito)


def prova_scalda():
    sezione("5. prefisso scaldato dopo un cambio del prompt di sistema")
    b, _, _ = prepara()
    b.backend = Registra()
    b.tool_ctx.speaker_ctx = ChiParla("Dario", "amministra")
    turno(b, "Che ore sono?", testo("Sono le 16."))
    verifica("prompt uguale: niente riscaldamento", "prefisso_scaldato" not in b.last_rules
             and getattr(b.backend, "scaldati", 0) == 0)
    b.backend.risposte = [testo("Modalità Star Trek attiva.")]
    gen = b.stream_reply("Attiva la modalità Star Trek.", "amministra")
    next(gen)
    cambia_modalita(b.cfg, "startrek")            # come cambia_voce durante la risposta
    for _ in gen:
        pass
    th = getattr(b, "scalda_thread", None)
    if th is not None:
        th.join(5)
    verifica("prompt cambiato durante la risposta: riscaldamento in un thread",
             "prefisso_scaldato" in b.last_rules and getattr(b.backend, "scaldati", 0) == 1,
             str(b.last_rules))
    turno(b, "Computer, che ore sono?", testo("Sono le 16."))
    verifica("il turno dopo (prompt fermo): niente riscaldamento",
             "prefisso_scaldato" not in b.last_rules and b.backend.scaldati == 1)
    cambia_modalita(b.cfg, "normale")


prova_lavoro()
prova_date()
prova_timer()
prova_riferire()
prova_scalda()
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
