import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Risultati dei lavori, dichiarazioni e consensi, a secco (07/10/2026, tre casi veri della DGX
del 07/10, qui con nomi di fantasia).

1. **Il risultato di un lavoro finito** (tool risultato_lavoro, calliope/agenti/risultato.py):
   dopo una ricerca annunciata, «E il risultato?» finiva in lavori_rispondi, «leggili e dammi
   un bel riassunto» in lavori_esegui («Non ho programmi finiti da eseguire»). Qui: quale
   lavoro (il più recente, per id, per parole del titolo, di un altro, in corso, dopo un
   riavvio dalla cartella dei risultati), riassunto salvato, riassunto col modello dell'agente
   (finto) quando quello salvato è già stato detto o si chiede «leggi», tempo massimo con la
   frase d'attesa e il ripiego, scheda sullo schermo personale («mostra»), codice mai a voce,
   numeri a pagamento del testo dell'agente fermati, classe nella politica; lavori_esegui,
   lavori_rispondi e lavori_stato che propongono il risultato.
2. **Dichiarazioni d'azione** (brain.ACTION_CLAIM): «Perfetto, allora inizio subito il
   lavoro.» senza nessun tool; i contrari («inizio a capire», «ti avviso quando inizio»,
   «inizio io?»). E la causa a monte: il «sì» di una voce diversa da chi ha la proposta ha nei
   dati del turno «c'è una proposta di <nome> in sospeso» (SOSPESO_ALTRUI_MSG, regola
   `sospeso_altrui_consenso`), anche dalla corsia di un satellite.
3. **Consenso** (politica.consenso, FORME_SI): «Ma sì dai, perché no?» alla domanda della
   politica con il risultato di un'estensione di mezzo; una domanda sola, il primo consenso
   valido basta; i contrari.

    python prove\\prova_risultati.py
"""

import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from calliope import politica
from calliope.agenti import Lavori, carica
from calliope.agenti import risultato as ar
from calliope.brain import ACTION_CLAIM, SOSPESO_ALTRUI_MSG, is_claim, proposta_altrui
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools import agenti as ta
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.ollama_finto import FakeOllama

errori = 0
TMP = Path(tempfile.mkdtemp(prefix="calliope-risultati-"))


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def sezione(nome):
    print(f"— {nome}", flush=True)


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Marta": Prof("marta", "Marta", True), "Luca": Prof("luca", "Luca"),
                  "Giorgio": Prof("giorgio", "Giorgio", True)}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


class Hub:
    """Schermi finti: `personale` = chi ha uno schermo suo."""

    def __init__(self, personale=("marta",)):
        self.personale = set(personale)
        self.inviate = []

    def mittente(self, ctx):
        sc = ctx.speaker_ctx
        prof = ctx.speakers.get(sc.current_speaker)
        return SimpleNamespace(persona=getattr(prof, "id", None))

    def invia(self, card, mitt, forza=False):
        if mitt.persona in self.personale:
            self.inviate.append((mitt.persona, card, forza))
            return {"schermi": ["tablet"], "destinatari": ["tablet"], "motivo": ""}
        return {"schermi": [], "destinatari": [], "motivo": "personale"}


COMPITO = ("Fai una ricerca approfondita sui pannelli fotovoltaici Solaris e sulla loro "
           "integrazione con Home Assistant.")
RIASSUNTO = ("Ho completato la ricerca sui pannelli Solaris e la loro integrazione con Home "
             "Assistant. Solaris offre pannelli ad alta efficienza con garanzie fino a 25 anni.")
TESTO = "\n\n".join([
    "I pannelli Solaris sono moduli monocristallini ad alta efficienza.",
    "Non esiste un'integrazione ufficiale di Home Assistant.",
    "Esiste un componente della comunità, installabile con HACS, chiamato solaris-locale.",
    "In alternativa l'inverter espone i dati con il protocollo Modbus TCP."] * 3)
DAL_MODELLO = ("Un'integrazione ufficiale non c'è, ma c'è un componente della comunità da "
               "installare con HACS. In alternativa l'inverter parla Modbus TCP.")


def servizio(agente, sotto="a"):
    cfg = Config()
    cfg.agenti_url = agente.url
    cfg.agenti_modello = "qwen3.6:35b"
    cfg.agenti_risultati = str(TMP / sotto / "risultati")
    cfg.agenti_sandbox = str(TMP / sotto / "sandbox")
    cfg.agenti_modelli = str(TMP / sotto / "modelli")
    cfg.agenti_risultato_s = 5.0
    svc = Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI)
    return cfg, svc


def finito(svc, tipo="ricerca", persona="marta", nome="Marta", compito=COMPITO, testo=TESTO,
           riassunto=RIASSUNTO, scrivi=True):
    lav = svc.nuovo(tipo, compito, persona, nome, "amministra")
    dest = Path(svc.cfg.agenti_risultati) / f"{lav.id}-{lav.titolo[:20]}"
    dest.mkdir(parents=True, exist_ok=True)
    lav.stato, lav.inizio, lav.fine, lav.cartella = "fatto", time.time() - 60, time.time(), \
        str(dest)
    lav.risultato = {"esito": "fatto", "riassunto": riassunto, "cartella": str(dest),
                     "file": []}
    if testo:
        lav.risultato["testo"] = testo
    if tipo == "codice":
        (dest / "somma.py").write_text("def somma(a, b):\n    return a + b\n", encoding="utf-8")
        lav.risultato["file"] = ["somma.py"]
    with svc._lock:
        svc.lavori.append(lav)
    if scrivi:
        svc._metadati(lav, dest)
    return lav


def contesto(cfg, svc, chi="Marta", livello="amministra", how="voce", hub=None, detto="",
             storia=()):
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello, how),
                      speaker=None, lavori=svc)
    ctx.schermi = hub
    ctx.user_text = detto
    ctx.storia = list(storia)
    ctx.regole = []
    attese = []
    ctx.attesa = attese.append
    return ctx, attese


def detta(r):
    return r.get("risposta_finale") or ""


# ─────────────────────────── 1. il risultato di un lavoro ───────────────────────────
def prova_risultato():
    sezione("risultato_lavoro")
    agente = FakeOllama(modelli=("qwen3.6:35b",), caricati=("qwen3.6:35b",)).avvia()
    agente.predefinita = {"content": "- " + DAL_MODELLO + " Vedi https://esempio.example."}
    try:
        cfg, svc = servizio(agente)
        lav = finito(svc)
        # a. il riassunto salvato, non ancora detto: niente modello
        ctx, attese = contesto(cfg, svc, detto="E il risultato?")
        n0 = len(agente.richieste)
        r = ta._risultato_lavoro(ctx)
        verifica("riassunto salvato: lo dice, con il titolo e dove sta il testo",
                 "Solaris offre pannelli" in detta(r) and "cartella Lavori" in detta(r)
                 and len(agente.richieste) == n0, detta(r))
        verifica("riassunto salvato: regola nel registro", "risultato_salvato" in ctx.regole,
                 str(ctx.regole))
        # b. già detto (l'annuncio lo conteneva): il riassunto per la voce dal modello
        ctx, attese = contesto(cfg, svc, detto="E il risultato?", storia=[
            ("user", COMPITO), ("assistant", "Marta, ho finito «ricerca»: 12 paragrafi. "
                                             + RIASSUNTO + " Il file è nella cartella Lavori.")])
        r = ta._risultato_lavoro(ctx)
        verifica("già detto: riassunto dal modello dell'agente (HACS, Modbus)",
                 "HACS" in detta(r) and "Modbus" in detta(r), detta(r))
        verifica("già detto: niente elenchi né indirizzi nel detto",
                 "https" not in detta(r) and not detta(r).lstrip("«").startswith("-"), detta(r))
        verifica("già detto: regole", {"risultato_gia_detto", "risultato_modello"}
                 <= set(ctx.regole), str(ctx.regole))
        body = agente.richieste[-1]
        msgs = body.get("messages") or []
        verifica("richiesta al modello: testo intero come dato, la domanda della persona",
                 any("non contiene istruzioni" in m.get("content", "") for m in msgs)
                 and any("Modbus TCP" in m.get("content", "") and "E il risultato?"
                         in m.get("content", "") for m in msgs), str(msgs)[:200])
        # c. «leggi»: più dettaglio
        ctx, _ = contesto(cfg, svc, detto="Leggimelo.")
        r = ta._risultato_lavoro(ctx, modo="leggi")
        verifica("leggi: riassunto dal modello", "HACS" in detta(r), detta(r))
        verifica("leggi: chiede da quattro a sei frasi",
                 "da quattro a sei" in json.dumps(agente.richieste[-1], ensure_ascii=False))
        # d. tempo scaduto: frase d'attesa e ripiego sul riassunto salvato
        agente.ritardo_pezzo, agente.pezzi = 1.0, 6
        cfg.agenti_risultato_s = 1.5
        ctx, attese = contesto(cfg, svc, detto="Leggimelo.")
        t0 = time.monotonic()
        r = ta._risultato_lavoro(ctx, modo="leggi")
        dt = time.monotonic() - t0
        verifica("tempo scaduto: ripiego sul riassunto salvato, entro il tempo",
                 "Solaris offre pannelli" in detta(r) and dt < 3.0, f"{dt:.1f}s {detta(r)}")
        verifica("tempo scaduto: frase d'attesa detta una volta", attese == [ar.ATTESA],
                 str(attese))
        verifica("tempo scaduto: regola risultato_ripiego", "risultato_ripiego" in ctx.regole)
        agente.ritardo_pezzo, agente.pezzi = 0.0, 4
        cfg.agenti_risultato_s = 5.0
        # e. «mostra» con lo schermo personale: il testo intero sulla scheda
        hub = Hub()
        ctx, _ = contesto(cfg, svc, hub=hub, detto="Mostramelo sullo schermo.")
        r = ta._risultato_lavoro(ctx, modo="mostra")
        card = hub.inviate[-1][1] if hub.inviate else {}
        verifica("mostra: scheda con il testo intero, forzata, frase breve",
                 "Modbus TCP" in json.dumps(card, ensure_ascii=False) and hub.inviate[-1][2]
                 and detta(r).startswith("Te l'ho mandato sullo schermo"), detta(r))
        # f. senza schermo: lo dice a voce
        ctx, _ = contesto(cfg, svc, hub=Hub(personale=()), detto="Mostramelo.")
        r = ta._risultato_lavoro(ctx, modo="mostra")
        verifica("mostra senza schermo: «Non vedo un tuo schermo» e il riassunto",
                 detta(r).startswith("Non vedo un tuo schermo") and "Solaris" in detta(r),
                 detta(r))
        # g. con lo schermo il testo va sempre, anche col riassunto
        hub = Hub()
        ctx, _ = contesto(cfg, svc, hub=hub, detto="E il risultato?")
        r = ta._risultato_lavoro(ctx)
        verifica("riassunto con lo schermo: la scheda va comunque, e lo dice",
                 len(hub.inviate) == 1 and "sul tuo schermo" in detta(r), detta(r))
        # h. permessi: un altro familiare no, chi amministra sì
        ctx, _ = contesto(cfg, svc, chi="Luca", livello="familiare", detto="E il risultato?")
        r = ta._risultato_lavoro(ctx)
        verifica("un altro familiare: rifiuto, regola risultato_lavoro_altrui",
                 not r.get("ok") and "altre persone" in detta(r)
                 and "risultato_lavoro_altrui" in ctx.regole, detta(r))
        ctx, _ = contesto(cfg, svc, chi="Luca", livello="familiare", detto="Il risultato di L1")
        r = ta._risultato_lavoro(ctx, lavoro=lav.id)
        verifica("un altro familiare con l'id: rifiuto", not r.get("ok")
                 and "un'altra persona" in detta(r), detta(r))
        ctx, _ = contesto(cfg, svc, chi="Giorgio", detto="Il risultato della ricerca sui "
                                                         "pannelli?")
        r = ta._risultato_lavoro(ctx, lavoro="pannelli Solaris")
        verifica("chi amministra: il lavoro di un altro, per parole del titolo",
                 r.get("ok") and r.get("lavoro") == lav.id, detta(r))
        # i. un lavoro più recente ancora in corso
        cfg2, svc2 = servizio(agente, "b")
        finito(svc2)
        corso = svc2.nuovo("ricerca", "Cerca i prezzi delle batterie di accumulo", "marta",
                           "Marta", "amministra")
        corso.stato = "in_corso"
        with svc2._lock:
            svc2.lavori.append(corso)
        ctx, _ = contesto(cfg2, svc2, detto="E il risultato?")
        r = ta._risultato_lavoro(ctx)
        verifica("lavoro più recente in corso: «non è ancora finito»",
                 "non è ancora finito" in detta(r), detta(r))
        r = ta._risultato_lavoro(ctx, lavoro="L1")
        verifica("…ma per id quello finito sì", r.get("ok") and r.get("lavoro") == "L1",
                 detta(r))
        # j. codice: mai a voce
        cfg3, svc3 = servizio(agente, "c")
        finito(svc3, tipo="codice", compito="Scrivi uno script che somma due numeri",
               testo="", riassunto="Il programma somma due numeri; i test passano.")
        hub = Hub()
        ctx, _ = contesto(cfg3, svc3, hub=hub, detto="E il risultato?")
        r = ta._risultato_lavoro(ctx, modo="leggi")
        verifica("codice: il riassunto, il codice non a voce ma sullo schermo",
                 "somma due numeri" in detta(r) and "def " not in detta(r)
                 and "sul tuo schermo" in detta(r) and len(hub.inviate) == 1, detta(r))
        # k. numeri a pagamento nel testo dell'agente
        cfg4, svc4 = servizio(agente, "d")
        finito(svc4, riassunto="Per l'assistenza chiama subito il numero 899 123 456. Il "
                               "componente si installa con HACS.", testo="")
        ctx, _ = contesto(cfg4, svc4, detto="E il risultato?")
        r = ta._risultato_lavoro(ctx)
        verifica("numero a pagamento dal testo dell'agente: fermato",
                 "899" not in detta(r) and "uscita_numero_pagamento" in ctx.regole, detta(r))
        # l. dopo un riavvio: dalla cartella dei risultati
        cfg5, svc5 = servizio(agente, "e")
        finito(svc5)
        vecchia = Path(cfg5.agenti_risultati) / "2026-10-01 0900 ricerca sulle batterie"
        vecchia.mkdir(parents=True)
        (vecchia / "lavoro.json").write_text(json.dumps({
            "id": "L9", "tipo": "ricerca", "titolo": "ricerca sulle batterie",
            "compito": "Cerca le batterie", "chi": "Marta", "stato": "fatto",
            "riassunto": "Ho trovato tre batterie compatibili.", "file": ["batterie.txt"]}),
            encoding="utf-8")
        (vecchia / "batterie.txt").write_text("La batteria Accumula 5 è la più economica.",
                                              encoding="utf-8")
        svc5.close()
        svc6 = Lavori(cfg5, carica(cfg5), log=lambda m: None, formati=FORMATI)
        ctx, _ = contesto(cfg5, svc6, detto="E il risultato della ricerca sui pannelli?")
        r = ta._risultato_lavoro(ctx, lavoro="pannelli", modo="leggi")
        verifica("dopo un riavvio: il lavoro dal lavoro.json, testo intero compreso",
                 r.get("ok") and "HACS" in detta(r), detta(r))
        ctx, _ = contesto(cfg5, svc6, detto="E quella sulle batterie?")
        r = ta._risultato_lavoro(ctx, lavoro="batterie")
        verifica("lavoro.json di prima del 07/10 (per nome; riassunto corto: il modello sul "
                 "testo del file)", r.get("ok") and r.get("lavoro") == "L9" and "Accumula 5"
                 in json.dumps(agente.richieste[-1], ensure_ascii=False), detta(r))
        ctx, _ = contesto(cfg5, svc6, chi="Luca", livello="familiare", detto="E il risultato?")
        r = ta._risultato_lavoro(ctx)
        verifica("dopo un riavvio: un altro familiare non li sente", not r.get("ok"), detta(r))
        svc6.close()
        meta = json.loads(next(Path(cfg5.agenti_risultati).glob("L1-*/lavoro.json"))
                          .read_text(encoding="utf-8"))
        verifica("lavoro.json: persona e testo intero", meta.get("persona") == "marta"
                 and "Modbus" in (meta.get("testo") or ""))
        # m. gli altri tool propongono il risultato
        ctx, _ = contesto(cfg, svc, detto="Leggili e dammi un bel riassunto.")
        r = ta._lavori_esegui(ctx, lavoro="L1")
        sosp = r.get("in_sospeso") or {}
        verifica("lavori_esegui su una ricerca: «è una ricerca, non un programma: vuoi il "
                 "risultato?» con l'azione in sospeso",
                 "non un programma" in detta(r) and detta(r).endswith("?")
                 and sosp.get("tool") == "risultato_lavoro"
                 and "lavori_offri_risultato" in ctx.regole, detta(r))
        ctx, _ = contesto(cfg, svc, detto="E il risultato?")
        r = ta._lavori_rispondi(ctx, risposta="Il lavoro è stato completato.")
        verifica("lavori_rispondi senza domande in attesa: propone il risultato",
                 (r.get("in_sospeso") or {}).get("tool") == "risultato_lavoro", detta(r))
        ctx, _ = contesto(cfg, svc, detto="A che punto è il lavoro?")
        r = ta._lavori_stato(ctx)
        verifica("lavori_stato con un lavoro finito: «Vuoi sentire il risultato?»",
                 detta(r).endswith("Vuoi sentire il risultato?")
                 and (r.get("in_sospeso") or {}).get("tool") == "risultato_lavoro", detta(r))
        svc.close(), svc2.close(), svc3.close(), svc4.close()
    finally:
        agente.ferma()
    # n. registro e politica
    reg = build_registry(agenti=True)
    spec = reg.get("risultato_lavoro")
    verifica("registro: risultato_lavoro con gli agenti, per i familiari",
             spec is not None and "ospite" not in spec.levels)
    cl = politica.classe_di("risultato_lavoro")
    verifica("politica: classe sicura, fonte agente (dato non fidato)",
             cl.classe == politica.SICURO and cl.fonte == "agente" and cl.dichiarata)
    desc = {n: reg.get(n).description for n in ("lavori_esegui", "lavori_rispondi",
                                                "lavori_stato", "delega_lavoro")}
    verifica("descrizioni: gli altri tool dei lavori rimandano a risultato_lavoro",
             all("risultato_lavoro" in d for d in desc.values())
             and desc["lavori_esegui"].startswith("Solo per i programmi")
             and desc["lavori_rispondi"].startswith("Solo quando l'agente ha fatto una domanda"))


# ─────────────────────────── 2. dichiarazioni e proposte altrui ───────────────────────────
DICHIARAZIONI = ["Perfetto, allora inizio subito il lavoro. Ti faccio sapere non appena ho "
                 "finito.", "Va bene, avvio la ricerca.", "Parto subito!", "Inizio subito.",
                 "Comincio subito a lavorarci.", "Ok, lo affido all'agente e ti avviso.",
                 "Lo mando subito all'agente.", "Certo, l'affido all'agente.",
                 "Mi metto subito al lavoro."]
NON_DICHIARAZIONI = ["Inizio a capire cosa intendi.", "Ti avviso quando inizio il lavoro.",
                     "Inizio io?", "Lo affido all'agente?",
                     "Se vuoi lo affido all'agente, procedo?",
                     "Non inizio il lavoro senza il tuo sì.",
                     "L'inizio del lavoro è previsto domani.",
                     "Appena inizio il lavoro ti avviso.", "Inizio subito il lavoro?",
                     "Lo passo a te.", "Il lavoro lo affido a te.",
                     "È una ricerca a più passi: vuoi che lo affidi all'agente?"]


def prova_dichiarazioni():
    sezione("dichiarazioni d'azione")
    for t in DICHIARAZIONI:
        verifica(f"dichiarazione: «{t}»", is_claim(t) and bool(ACTION_CLAIM.search(t)))
    for t in NON_DICHIARAZIONI:
        verifica(f"non dichiarazione: «{t}»", not is_claim(t))


def prova_proposta_altrui():
    sezione("il «sì» di chi non ha la proposta")
    from prove.prova_conferma_unica import LavoriFinti
    from prove.prova_politica import ChiParla, chiama, prepara, testo, turno
    import dataclasses
    p = {"chi": "marta", "chi_nome": "Marta", "domanda": "Procedo?", "cosa": "affidare un lavoro",
         "scade": time.monotonic() + 60}
    verifica("proposta_altrui: un'altra persona → i campi",
             (proposta_altrui(p, "luca") or {}).get("nome") == "Marta")
    verifica("proposta_altrui: la stessa persona → niente", proposta_altrui(p, "marta") is None)
    verifica("proposta_altrui: scaduta → niente",
             proposta_altrui({**p, "scade": time.monotonic() - 1}, "luca") is None)
    verifica("proposta_altrui: di un ospite → niente",
             proposta_altrui({**p, "chi": None}, "luca") is None)

    def brain():
        b, _, _ = prepara(True)
        b.tool_ctx.speakers.p["Marta"] = SimpleNamespace(
            id="marta", name="Marta", admin=True, gender="f", preferred_voice=None,
            giovane=False, young=False, tono=None)
        b.tool_ctx.speakers.p["Luca"] = SimpleNamespace(
            id="luca", name="Luca", admin=False, gender="m", preferred_voice=None,
            giovane=True, young=True, tono=None)
        reg = b.tools
        reg.register(dataclasses.replace(reg.get("delega_lavoro"), func=ta._delega_lavoro))
        svc = LavoriFinti()
        b.tool_ctx.lavori = svc
        visti = []
        orig = b.backend.stream

        def stream(messages, tools):
            visti.append([m.get("content") for m in messages if m.get("role") == "system"])
            yield from orig(messages, tools)
        b.backend.stream = stream
        return b, svc, visti

    RIC = {"tipo": "codice", "compito": "Scrivi uno script che somma due numeri"}
    b, svc, visti = brain()
    marta = ChiParla("Marta", "amministra")
    r1 = turno(b, "Scrivimi uno script che somma due numeri", chiama("delega_lavoro", RIC),
               testo("Va bene."), chi=marta)
    verifica("Marta: la proposta («Procedo?»)", r1.rstrip().endswith("?"), r1)
    visti.clear()
    r2 = turno(b, "Sì, procedi.", testo("Perfetto, allora inizio subito il lavoro. Ti faccio "
                                        "sapere non appena ho finito."),
               testo("La proposta è di Marta: se sei Marta, ripetilo con una frase più lunga."),
               chi=ChiParla("Luca", "familiare", "conversazione"))
    dati = " ".join(x for giro in visti for x in giro if x)
    verifica("«Sì, procedi.» di un'altra voce: nei dati del turno la proposta di Marta",
             "c'è una proposta di Marta in sospeso" in dati and "solo Marta" in dati, dati[-300:])
    verifica("…regole sospeso_altrui_consenso e spinta sulla dichiarazione",
             "sospeso_altrui_consenso" in b.rules_fired(), str(b.rules_fired()))
    verifica("…niente avviato, e «inizio subito il lavoro» non detto",
             not svc.avviati and "inizio subito" not in r2, r2)
    # Contrari: la stessa persona (il lavoro parte), un'altra domanda (niente dati)
    b, svc, visti = brain()
    turno(b, "Scrivimi uno script che somma due numeri", chiama("delega_lavoro", RIC),
          testo("Va bene."), chi=ChiParla("Marta", "amministra"))
    visti.clear()
    turno(b, "Sì, procedi pure con il lavoro.", chiama("delega_lavoro", {"proposta": "L1"}),
          testo("Fatto."), chi=ChiParla("Marta", "amministra"))
    dati = " ".join(x for giro in visti for x in giro if x)
    verifica("contrario: il «sì» di Marta → parte, niente dati sulla proposta altrui",
             len(svc.avviati) == 1 and "proposta di Marta" not in dati
             and "sospeso_altrui_consenso" not in b.rules_fired(), str(b.rules_fired()))
    b, svc, visti = brain()
    turno(b, "Scrivimi uno script che somma due numeri", chiama("delega_lavoro", RIC),
          testo("Va bene."), chi=ChiParla("Marta", "amministra"))
    visti.clear()
    turno(b, "Che ore sono?", testo("Sono le dieci."), chi=ChiParla("Luca", "familiare"))
    dati = " ".join(x for giro in visti for x in giro if x)
    verifica("contrario: un'altra voce che non acconsente → niente dati sulla proposta",
             "proposta di Marta" not in dati and "sospeso_altrui_consenso" not in
             b.rules_fired())
    # Dalla corsia di un satellite: la conversazione di Marta e quella anonima di Luca
    from calliope.corsie import Corsia, RegistroConversazioni
    b, svc, visti = brain()
    reg = RegistroConversazioni(b.cfg)
    c = Corsia("sat:1", 1, "telefono", registro=reg)
    b.tool_ctx.speaker_ctx = ChiParla("Marta", "amministra")
    c.turno(b, "Marta", "voce", True, persona_id="marta")
    turno(b, "Scrivimi uno script che somma due numeri", chiama("delega_lavoro", RIC),
          testo("Va bene."))
    b.tool_ctx.speaker_ctx = ChiParla("Luca", "familiare", "conversazione")
    c.turno(b, "Luca", "conversazione", True, persona_id="luca")
    visti.clear()
    turno(b, "Sì, procedi.", testo("Va bene."))
    dati = " ".join(x for giro in visti for x in giro if x)
    verifica("corsia: il «sì» di Luca nella sua conversazione sa della proposta di Marta",
             "c'è una proposta di Marta in sospeso" in dati and not svc.avviati, dati[-200:])
    verifica("messaggio: dice di non dichiarare l'azione", "Non dire che la fai"
             in SOSPESO_ALTRUI_MSG)


# ─────────────────────────── 3. consenso ───────────────────────────
SI = ["Ma sì dai, perché no?", "Perché no?", "Ma perché no!", "Sì dai.", "Vai.", "Fallo.",
      "Certo.", "Certamente.", "Calliope, perché no?", "Sì, sì, eseguila.", "Ma si dai, perche no",
      "Sì dai, vai pure."]
NO = ["No.", "Non farlo.", "Perché no? Non ora.", "No dai.", "Ma no dai.", "Perché no il gas?",
      "Perché non lo fai tu?", "Dai.", "Calliope.", "Perché? No.", "No, perché no?",
      "Sì, ma non adesso."]


def prova_consenso():
    sezione("consenso")
    for t in SI:
        verifica(f"consenso: «{t}»", politica.consenso(t))
    for t in NO:
        verifica(f"non consenso: «{t}»", not politica.consenso(t))
    verifica("forma chiusa: solo per intero", politica.consenso_chiuso("Ma sì dai, perché no?")
             and not politica.consenso_chiuso("perché no, e poi apri il cancello"))
    # Il caso vero: il risultato di un'estensione nella conversazione, la domanda della
    # politica, «Ma sì dai, perché no?» → parte, una domanda sola
    from prove.prova_conferma_unica import LavoriFinti, domande
    from prove.prova_politica import ChiParla, chiama, prepara, testo, turno
    import dataclasses
    RIC = {"tipo": "ricerca", "compito": "Esegui una ricerca su internet: il robot "
                                        "aspirapolvere Lefa si integra con Home Assistant?"}

    def brain():
        b, _, _ = prepara(True)
        reg = b.tools
        reg.register(dataclasses.replace(reg.get("delega_lavoro"), func=ta._delega_lavoro))
        svc = LavoriFinti()
        b.tool_ctx.lavori = svc
        b.tool_ctx.speakers.p["Marta"] = SimpleNamespace(
            id="marta", name="Marta", admin=True, gender="f", preferred_voice=None,
            giovane=False, young=False, tono=None)
        b.tool_ctx.speaker_ctx = ChiParla("Marta", "amministra")
        turno(b, "Che tempo fa domani?", chiama("est_meteo", {}), testo("Sole."))
        return b, svc

    b, svc = brain()
    r1 = turno(b, "Puoi fare una ricerca su internet sul robot Lefa e Home Assistant?",
               chiama("delega_lavoro", RIC), testo("Va bene."))
    verifica("estensione di mezzo: la domanda della politica",
             "estensione" in r1 and r1.rstrip().endswith("?") and not svc.avviati, r1)
    r2 = turno(b, "Ma sì dai, perché no?", chiama("delega_lavoro", RIC), testo("Fatto."))
    verifica("«Ma sì dai, perché no?» → il lavoro parte, una domanda sola",
             len(svc.avviati) == 1 and domande(r1, r2) == 1, f"{r1!r} / {r2!r}")
    verifica("…regole politica_conferma_unica e consenso_forma_chiusa",
             {"politica_conferma_unica", "consenso_forma_chiusa"} <= set(b.rules_fired()),
             str(b.rules_fired()))
    verifica("solo_forma_chiusa: «perché no» sì, «Sì, vai.» no (lo prendeva già la regola)",
             politica.solo_forma_chiusa("Ma sì dai, perché no?")
             and not politica.solo_forma_chiusa("Sì, vai."))
    for frase in ("Perché no? Non ora.", "No, lascia stare."):
        b, svc = brain()
        turno(b, "Puoi fare una ricerca su internet sul robot Lefa e Home Assistant?",
              chiama("delega_lavoro", RIC), testo("Va bene."))
        r = turno(b, frase, chiama("delega_lavoro", RIC), testo("Fatto."))
        verifica(f"contrario: «{frase}» → niente avviato", not svc.avviati, r)


prova_consenso()
prova_dichiarazioni()
prova_proposta_altrui()
prova_risultato()
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
