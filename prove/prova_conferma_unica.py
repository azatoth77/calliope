import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Una conferma per azione, a secco (06/10/2026, caso vero della DGX delle 17:30–17:34).

Dario manda una foto dal telefono («Vedi?»), due minuti dopo a voce: «Creiamo un'estensione
che prende due parametri e li somma». Sulla DGX:

1. `sviluppo_apri` rifiutato dalla guardia delle immagini: «creiamo» non era una richiesta
   (il lessico aveva solo «crea»);
2. il modello passava a `lavoro_affida(tipo=codice)`: conferma della politica per la foto, al
   «Sì.» breve la frase di sfida, dopo la sfida ancora il «Procedo?» del tool («Sì, ma quante
   volte me lo chiedi?»);
3. l'annuncio diceva «ho creato un'estensione», e a «come la richiamo?» il modello inventava un
   comando a voce che non esiste;
4. la dimostrazione senza argomenti finiva «errore, codice 1» mentre l'annuncio diceva «funziona
   correttamente e tutti i test passano».

Qui la sequenza con Brain vero, i tool veri di sviluppo_apri e lavoro_affida, un servizio dei
lavori finto e un modello finto che fa le stesse chiamate della DGX; più i contrari (con la
conversazione pulita il «Procedo?» del tool resta; argomenti cambiati al «sì» → di nuovo la
proposta; un'altra persona; il lessico delle coniugazioni e le frasi che non chiedono azioni).

    python prove\\prova_conferma_unica.py
"""

import dataclasses
from types import SimpleNamespace

from calliope import politica
from calliope.agenti import servizio as srv
from calliope.agenti.esecuzione import Esecuzioni
from calliope.immagini import Immagine
from calliope.tools import agenti as ta
from calliope.tools.estensioni import estensioni_specs
from prove.prova_politica import ChiParla, chiama, prepara, testo, turno

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if ok:
        print(f"  ok  {nome}")
    else:
        errori += 1
        print(f"  NO  {nome}" + (f"\n      {dettaglio}" if dettaglio else ""))


class LavoriFinti:
    """Il servizio dei lavori, quanto basta ai tool: proposta, offerta, conferma, avvio."""

    def __init__(self):
        self.offerte, self.avviati, self.n = {}, [], 0
        self.isolamento = SimpleNamespace(pronto=True)
        self.modelli = {}

    def nuovo(self, tipo, compito, persona=None, persona_nome=None, livello="familiare",
              formato="", modello="", vincoli="", dati=None):
        self.n += 1
        lav = SimpleNamespace(id=f"L{self.n}", tipo=tipo, compito=compito, persona=persona,
                              titolo=srv.titolo_da(compito), file_candidati=[],
                              file_utente=None, estensione=None, file_iniziali={},
                              on_scheda=None, formato=formato)
        if tipo == "codice":
            lav.titolo = srv.senza_estensione(lav.titolo)
            lav.non_estensione = srv.senza_estensione(compito) != compito
        return lav

    def serve_conferma(self, lav):
        return True

    def proponi(self, lav, turno):
        self.offerte[lav.persona] = {"lavoro": lav, "turno": turno}
        return "È un lavoro di programmazione: lo affido all'agente. Procedo?"

    def offerta(self, persona, turno):
        off = self.offerte.get(persona)
        return off if off and 1 <= turno - off["turno"] <= 3 else None

    def conferma(self, persona, ident, turno):
        off = self.offerta(persona, turno)
        if off is None or off["lavoro"].id != ident:
            return None
        self.offerte.pop(persona, None)
        return off["lavoro"]

    def avvia(self, lav):
        self.avviati.append(lav)
        return "Ci lavoro in secondo piano: ti avviso quando è pronto."

    def collegamento_guasto(self):
        return None

    def verifica_in_secondo_piano(self):
        pass


def prepara_dgx(foto=True):
    """Brain del banco della politica, con Dario che amministra, i tool veri degli agenti e
    delle estensioni e (con `foto`) la foto mandata due minuti prima."""
    b, _, _ = prepara(True)
    reg = b.tools
    reg.register(dataclasses.replace(reg.get("lavoro_affida"), func=ta._delega_lavoro))
    for s in estensioni_specs():
        reg.register(s)
    svc = LavoriFinti()
    b.tool_ctx.lavori = svc
    b.tool_ctx.estensioni = SimpleNamespace(pronto=lambda: True,
                                            archivio=SimpleNamespace(voce=lambda n: None,
                                                                     nomi=lambda: []))
    b.tool_ctx.speaker_ctx = ChiParla("Dario", "amministra")
    if foto:
        turno(b, "Vedi?", testo("Vedo un uomo con gli occhiali che sorride."),
              immagini=[Immagine(b"\xff\xd8finto", 10, 10, persona="dario")])
    return b, svc


DETTA = "Creiamo un'estensione che prende due parametri e li somma"
EST = {"compito": "Crea un'estensione che prenda in input due parametri numerici e ne "
                  "restituisca la somma.", "nome": "somma_parametri"}
COD = {"compito": EST["compito"], "tipo": "codice"}


def domande(*risposte) -> int:
    return sum(r.rstrip().endswith("?") or "ripeti" in r.lower() for r in risposte)


def prova_lessico():
    for t in (DETTA, "crea una funzione che converte i metri", "creare un programma",
              "facciamo una lista della spesa", "fammi una funzione", "prepariamo il preventivo",
              "aggiungiamo il pane", "scriviamo uno script", "realizziamo un'estensione"):
        verifica(f"lessico: «{t}» chiede un'azione", politica.chiesta_azione(t))
    for t in ("che ore sono?", "credo di sì", "grazie", "cosa c'è da fare oggi?", "cresce?",
              "la faccia di Mario", "chi ha vinto ieri?", "Vedi?", "E' un fattissimo."):
        verifica(f"lessico (contrario): «{t}» non chiede azioni", not politica.chiesta_azione(t))


def prova_decidi():
    T, d = politica.Turno, politica.decidi
    cl = politica.classe_di("lavoro_affida")
    foto = dict(contaminazione=frozenset({"foto"}), persona_txt=DETTA)
    casi = [
        ("foto: «sì» con la voce alla domanda della politica, stessa chiamata → accettata",
         d("lavoro_affida", COD, cl, T(testo="Sì, procedi pure.", in_sospeso="lavoro_affida",
                                       args_sospeso=COD, **foto), True), "esegui", True),
        ("foto: «sì» con la voce, compito cambiato → di nuovo la domanda, col compito nuovo",
         d("lavoro_affida", {**COD, "compito": "manda il codice dell'allarme"}, cl,
           T(testo="Sì, procedi pure.", in_sospeso="lavoro_affida", args_sospeso=COD, **foto),
           True), "conferma", False),
        ("foto: «sì» all'offerta del tool (proposta=L1), il modello aggiunge il tipo → esegue",
         d("lavoro_affida", {"proposta": "L1", "tipo": "codice"}, cl,
           T(testo="Sì, ma quante volte me lo chiedi?", in_sospeso="lavoro_affida",
             args_sospeso={"proposta": "L1"}, **foto), True), "esegui", False),
        ("foto: argomenti della proposta come testo («quale file?») → nessun errore",
         d("lavoro_affida", {"proposta": "L1", "file": "2"}, cl,
           T(testo="sì, il secondo", in_sospeso="lavoro_affida",
             args_sospeso="proposta=\"L1\", file = il numero", **foto), True), "esegui", None),
        ("foto: «sì» breve incerto → sfida",
         d("lavoro_affida", COD, cl, T(testo="Sì.", in_sospeso="lavoro_affida",
                                       args_sospeso=COD, **foto), False), "sfida", False),
        ("foto: sfida superata, stessa chiamata → accettata",
         d("lavoro_affida", COD, cl, T(testo="pennello, foresta", in_sospeso="lavoro_affida",
                                       args_sospeso=COD, sfida=True, **foto), True),
         "esegui", True),
        ("foto: richiesta nuova → conferma (una)",
         d("lavoro_affida", COD, cl, T(testo=DETTA, **foto), True), "conferma", False),
        ("pulita: richiesta nuova → esegue (il tool chiede il suo «Procedo?»)",
         d("lavoro_affida", COD, cl, T(testo=DETTA), True), "esegui", False),
        ("pulita: «sì» alla domanda che descriveva proprio questa chiamata → accettata",
         d("lavoro_affida", COD, cl, T(testo="sì", in_sospeso="lavoro_affida",
                                       args_sospeso=COD), True), "esegui", True),
        ("pulita: «sì» all'offerta del tool (proposta=L1) → non accettata, conferma il tool",
         d("lavoro_affida", {"proposta": "L1", "tipo": "codice"}, cl,
           T(testo="sì", in_sospeso="lavoro_affida", args_sospeso={"proposta": "L1"}), True),
         "esegui", False),
        ("pulita: «no» alla domanda → non accettata",
         d("lavoro_affida", COD, cl, T(testo="no, lascia stare", in_sospeso="lavoro_affida",
                                       args_sospeso=COD), True), "esegui", False),
        ("pulita: sfida superata, stessa chiamata → accettata",
         d("lavoro_affida", COD, cl, T(testo="pennello", in_sospeso="lavoro_affida",
                                       args_sospeso=COD, sfida=True), True), "esegui", True),
    ]
    for nome, dec, esito, acc in casi:
        verifica(f"decidi: {nome}", dec.esito == esito and acc in (None, dec.accettata),
                 f"{dec}")
    est = politica.da_confermare("sviluppo_apri", EST)
    verifica("decidi: la domanda per sviluppo_apri dice il compito",
             est.startswith("creare una funzione nuova di Calliope") and "due parametri" in est,
             est)


def prova_estensione_con_foto():
    """Il caso della DGX dopo la correzione: una domanda sola (la conferma della politica, che
    nomina la foto e il compito), al «sì» con la voce l'estensione parte."""
    b, svc = prepara_dgx()
    r1 = turno(b, DETTA, chiama("sviluppo_apri", EST), testo("Va bene."))
    verifica("DGX 1: «creiamo…» non è rifiutato come azione non chiesta",
             "politica_azione_non_chiesta" not in b.rules_fired(), str(b.rules_fired()))
    verifica("DGX 1: una domanda che nomina la foto e il compito, niente avviato",
             "foto" in r1 and "due parametri" in r1 and r1.rstrip().endswith("?")
             and not svc.avviati, r1)
    r2 = turno(b, "Sì procedi pure.", chiama("sviluppo_apri", EST), testo("Fatto."))
    verifica("DGX 2: al «sì» con la voce parte subito, senza un altro «Procedo?»",
             len(svc.avviati) == 1 and svc.avviati[0].tipo == "estensione"
             and "Procedo" not in r2, r2)
    verifica("DGX 2: regole nel registro", {"politica_conferma_unica"}
             <= set(b.rules_fired()), str(b.rules_fired()))
    verifica("DGX: domande in tutto = 1", domande(r1, r2) == 1, f"{r1!r} / {r2!r}")


def prova_delega_con_foto_sfida():
    """La sequenza vera (il modello usa lavoro_affida): conferma, «Sì.» breve incerto → sfida,
    sfida superata → il lavoro parte, senza il terzo «Procedo?»."""
    b, svc = prepara_dgx()
    r1 = turno(b, DETTA, chiama("lavoro_affida", COD), testo("Va bene."))
    verifica("sfida 1: conferma della politica per la foto", "C'è di mezzo una foto" in r1
             and not svc.avviati, r1)
    sc = b.tool_ctx.speaker_ctx
    sc.identified_by, sc.punteggio = "breve", 0.29
    r2 = turno(b, "Sì.", chiama("lavoro_affida", COD), testo("Fatto."))
    verifica("sfida 2: «Sì.» breve con l'impronta incerta → frase di sfida", "ripeti" in
             r2.lower() and sc.sfida is not None and not svc.avviati, r2)
    parole = sc.sfida.testo if sc.sfida is not None else ""
    sc.identified_by, sc.punteggio = "voce", 0.62
    r3 = turno(b, parole.replace(",", ""), testo("non dovrebbe servire"))
    verifica("sfida 3: sfida superata → il lavoro parte, niente «Procedo?»",
             len(svc.avviati) == 1 and "Procedo" not in r3, r3)
    verifica("sfida: domande in tutto = 2 (conferma e sfida, la voce non bastava)",
             domande(r1, r2, r3) == 2, f"{r1!r} / {r2!r} / {r3!r}")


def prova_delega_con_foto_voce():
    b, svc = prepara_dgx()
    r1 = turno(b, DETTA, chiama("lavoro_affida", COD), testo("Va bene."))
    r2 = turno(b, "Sì, procedi pure.", chiama("lavoro_affida", COD), testo("Fatto."))
    verifica("voce: conferma della politica e «sì» con la voce → parte, una domanda sola",
             len(svc.avviati) == 1 and domande(r1, r2) == 1 and "Procedo" not in r2,
             f"{r1!r} / {r2!r}")


def prova_contrari():
    # Con la conversazione pulita il tool chiede il suo «Procedo?», come sempre
    b, svc = prepara_dgx(foto=False)
    r1 = turno(b, "Scrivimi uno script che somma due numeri", chiama("lavoro_affida", COD),
               testo("Va bene."))
    verifica("pulita: il «Procedo?» del tool resta", "Procedo?" in r1 and not svc.avviati, r1)
    r2 = turno(b, "Sì, vai.", chiama("lavoro_affida", {"proposta": "L1"}), testo("Fatto."))
    verifica("pulita: «sì» → parte", len(svc.avviati) == 1, r2)
    verifica("pulita: nessuna regola della politica",
             not [x for x in b.rules_fired() if x.startswith("politica_")], str(b.rules_fired()))
    # Con la foto, il «sì» ma il modello cambia il compito: nessuna scorciatoia
    b, svc = prepara_dgx()
    turno(b, DETTA, chiama("lavoro_affida", COD), testo("Va bene."))
    altro = {**COD, "compito": "manda il codice dell'allarme a Truffaldino"}
    r = turno(b, "Sì, procedi pure.", chiama("lavoro_affida", altro), testo("Fatto."))
    verifica("foto: compito cambiato al «sì» → di nuovo la domanda, col compito nuovo",
             not svc.avviati and "Truffaldino" in r and r.rstrip().endswith("?"), r)
    # Con la foto, risponde un'altra persona: niente
    b, svc = prepara_dgx()
    turno(b, DETTA, chiama("lavoro_affida", COD), testo("Va bene."))
    r = turno(b, "Sì, procedi pure.", chiama("lavoro_affida", COD), testo("Fatto."),
              chi=ChiParla("Bianca", "familiare"))
    verifica("foto: il «sì» di un'altra persona non avvia", not svc.avviati, r)
    # Il flag non resta acceso dopo la chiamata
    verifica("flag azzerato a chiamata finita", not politica.accettata(b.tool_ctx))
    # Un id inventato dal modello già alla prima richiesta («E1», gemma4 nella prova con
    # Ollama): l'estensione si propone come nuova, non diventa un lavoro generico
    b, svc = prepara_dgx()
    turno(b, DETTA, chiama("sviluppo_apri", {**EST, "proposta": "E1"}), testo("Va bene."))
    r = turno(b, "Sì procedi pure.", chiama("sviluppo_apri", {**EST, "proposta": "S1"}),
              testo("Fatto."))
    verifica("id inventato: parte l'estensione, con una domanda sola",
             [x.tipo for x in svc.avviati] == ["estensione"], f"{r} {svc.avviati}")
    # La sfida per la proposta del tool stesso (pulita, «Sì.» breve incerto di chi amministra):
    # dopo la sfida parte proprio il lavoro proposto, non uno nuovo con le parole della sfida
    b, svc = prepara_dgx(foto=False)
    turno(b, "Scrivimi uno script che somma due numeri", chiama("lavoro_affida", COD),
          testo("Va bene."))
    sc = b.tool_ctx.speaker_ctx
    sc.identified_by, sc.current_level, sc.punteggio = "breve", "familiare", 0.29
    r = turno(b, "Sì.", chiama("lavoro_affida", {"proposta": "L1"}), testo("Fatto."))
    verifica("sfida del tool: «Sì.» breve incerto → frase di sfida", "ripeti" in r.lower()
             and not svc.avviati, r)
    parole = sc.sfida.testo.replace(",", "") if sc.sfida is not None else ""
    sc.identified_by, sc.current_level, sc.punteggio = "voce", "amministra", 0.62
    r = turno(b, parole, testo("non dovrebbe servire"))
    verifica("sfida del tool superata → parte il lavoro proposto (L1, il compito di prima)",
             [(x.id, x.compito) for x in svc.avviati] == [("L1", COD["compito"])],
             f"{r} {[(x.id, x.compito) for x in svc.avviati]}")


def prova_doppione():
    """Un'estensione che rifà una capacità che c'è già (06/10, Dario: «somma due numeri» è
    calcola): lo decide il modello con `gia_fatto_da`; Calliope lo dice e chiede se la vuole
    comunque, senza partire. Il «sì» la crea (una domanda sola); un nome inventato non scavalca
    la politica."""
    dop = {**EST, "gia_fatto_da": "calcola", "come_chiederlo": "quanto fa 3 più 5"}
    b, svc = prepara_dgx()
    r1 = turno(b, DETTA, chiama("sviluppo_apri", dop), testo("Va bene."))
    verifica("doppione: «Questo lo so già fare: chiedimi pure…», niente avviato",
             r1.startswith("Questo lo so già fare: chiedimi pure «quanto fa 3 più 5»")
             and r1.rstrip().endswith("?") and not svc.avviati, r1)
    verifica("doppione: nessuna conferma della politica prima",
             not [x for x in b.rules_fired() if x.startswith("politica_")]
             and "estensione_doppione" in b.rules_fired(), str(b.rules_fired()))
    # Al «sì» il modello rimanda anche i campi del doppione (gemma4 con Ollama, 06/10)
    r2 = turno(b, "Sì, la voglio comunque.", chiama("sviluppo_apri", dop), testo("Fatto."))
    verifica("doppione: «sì, comunque» con la voce → parte, una domanda sola",
             [x.tipo for x in svc.avviati] == ["estensione"] and domande(r1, r2) == 1,
             f"{r1!r} / {r2!r}")
    b, svc = prepara_dgx()
    turno(b, DETTA, chiama("sviluppo_apri", dop), testo("Va bene."))
    r = turno(b, "No, allora lascia stare.", chiama("sviluppo_apri", {**dop, "comune": True}),
              testo("D'accordo."))
    verifica("doppione: «no» (anche se il modello richiama il tool) → niente", not svc.avviati, r)
    # Al «sì» gemma4 aggiungeva campi («comune»), e la domanda tornava all'infinito
    b, svc = prepara_dgx()
    turno(b, DETTA, chiama("sviluppo_apri", dop), testo("Va bene."))
    r = turno(b, "Sì, la voglio comunque.", chiama("sviluppo_apri", {**dop, "comune": True}),
              testo("Fatto."))
    verifica("doppione: campi in più al «sì» → vale lo stesso",
             [x.tipo for x in svc.avviati] == ["estensione"], r)
    b, svc = prepara_dgx()
    r = turno(b, DETTA, chiama("sviluppo_apri", {**EST, "gia_fatto_da": "inventato"}),
              testo("Va bene."))
    verifica("doppione: un tool inventato non vale (conferma della politica, niente avviato)",
             "C'è di mezzo una foto" in r and not svc.avviati, r)


def prova_doppione_piano():
    """Lo stesso controllo nel piano dell'agente (qwen3.6 sulla DGX: più affidabile del 4B
    davanti): il piano con gia_fatto_da diventa una domanda a metà lavoro, una volta sola."""
    from calliope.agenti import ciclo
    from calliope.tools.estensioni import funzioni_di_calliope
    ag = object.__new__(ciclo.Agente)
    ag.log = lambda *a, **k: None
    lav = ciclo.Lavoro("L1", "estensione", "prende due parametri e li somma")
    piano = {"capacita_necessarie": [], "fattibile": True, "motivo": "somma",
             "gia_fatto_da": "calcola", "come_chiederlo": "quanto fa 3 più 5"}
    res, chiusura = ag._piano(lav, None, piano, None)
    verifica("piano: doppione → domanda a metà lavoro, «Vuoi comunque l'estensione?»",
             chiusura is not None and chiusura["esito"] == "mancano_dati"
             and chiusura["domanda"] == "Questo lo so già fare: chiedimi pure «quanto fa 3 più "
                                        "5». Vuoi comunque l'estensione?"
             and lav.doppione_chiesto and res.get("_stato", 0) is None, f"{res} {chiusura}")
    vuota = SimpleNamespace(elenca=lambda: [])
    try:
        _, chiusura2 = ag._piano(lav, vuota, piano, None)
    except Exception:  # noqa: BLE001 — oltre il doppione il piano vuole una sandbox vera
        chiusura2 = None
    verifica("piano: dopo la risposta il doppione non si richiede",
             chiusura2 is None or chiusura2.get("esito") != "mancano_dati", f"{chiusura2}")
    lav2 = ciclo.Lavoro("L2", "estensione", "x")
    try:
        _, ch = ag._piano(lav2, vuota, {**piano, "gia_fatto_da": "inventato"}, None)
    except Exception:  # noqa: BLE001
        ch = None
    verifica("piano: un tool inventato non è un doppione", not lav2.doppione_chiesto
             and (ch is None or ch.get("esito") != "mancano_dati"), f"{ch}")
    verifica("vincoli: l'agente vede le funzioni che Calliope ha già",
             "calcola" in funzioni_di_calliope() and "casa_comando" not in funzioni_di_calliope())


def prova_rinuncia():
    """Caso della DGX delle 18:20: dopo il rifiuto sbagliato rimasto nella storia, «creiamo una
    nuova estensione… per le mie cotture» → «come ti spiegavo prima, non posso creare
    direttamente un'estensione», senza tool. La rete (spinta_rinuncia) fa chiamare il tool;
    i guasti si dicono come guasti; il riassunto non porta avanti un «non posso»."""
    D = {"sviluppo_apri", "lavoro_affida", "documento_crea"}
    for t, r in (("Come ti spiegavo prima, non posso creare direttamente un'estensione.",
                  "creiamo una nuova estensione che tenga traccia delle mie cotture"),
                 ("Capisco, ma la mia architettura non mi permette di creare estensioni.",
                  "io voglio che sia un'estensione")):
        verifica(f"rinuncia: «{t[:50]}…» → sviluppo_apri",
                 politica.rinuncia(t, r, D) == "sviluppo_apri")
    for t, r, d in (("Non posso creare un'estensione.", "che ore sono?", D),
                    ("Non posso sapere il meteo, ma posso scriverti un programma.",
                     "scrivimi un programma", D),
                    ("Non posso creare un'estensione.", "creiamo un'estensione",
                     {"lavoro_affida"}),
                    ("Ho creato l'estensione.", "creiamo un'estensione", D)):
        verifica(f"rinuncia (contrario): «{t[:40]}…» / «{r[:30]}»",
                 politica.rinuncia(t, r, d) is None)
    # Con Brain: il modello rinuncia, la spinta lo fa chiamare; la frase non resta nella storia
    b, svc = prepara_dgx(foto=False)
    frase = "creiamo una nuova estensione che tenga traccia delle mie cotture"
    r = turno(b, frase, testo("Come ti spiegavo prima, non posso creare direttamente "
                              "un'estensione."),
              chiama("sviluppo_apri", {"compito": "tenere traccia delle cotture"}),
              testo("Fatto."))
    verifica("rinuncia: spinta e poi sviluppo_apri (la proposta del tool)",
             "spinta_rinuncia" in b.rules_fired() and "Procedo?" in r, r)
    verifica("rinuncia: il «non posso» non resta nella storia",
             not any("non posso creare" in str(m.get("content") or "")
                     for m in b.history if m.get("role") == "assistant"),
             str([m.get("content") for m in b.history if m.get("role") == "assistant"]))
    b, svc = prepara_dgx(foto=False)
    b.cfg.llm_reti_spente = ["spinta_rinuncia"]
    r = turno(b, frase, testo("Non posso creare direttamente un'estensione."))
    verifica("rinuncia: rete spenta → niente spinta", "spinta_rinuncia" not in b.rules_fired(), r)
    b, svc = prepara_dgx(foto=False)
    r = turno(b, "che ore sono?", testo("Non posso creare estensioni, ma sono le dieci."))
    verifica("rinuncia (contrario): nessuna richiesta d'azione → niente spinta",
             "spinta_rinuncia" not in b.rules_fired(), r)
    # Un guasto di adesso si dice come guasto, con la nota per il modello nella storia
    b, svc = prepara_dgx(foto=False)
    b.tool_ctx.estensioni = SimpleNamespace(pronto=lambda: False,
                                            archivio=SimpleNamespace(voce=lambda n: None,
                                                                     nomi=lambda: []))
    r = turno(b, frase, chiama("sviluppo_apri", {"compito": "cotture"}), testo("Fatto."))
    tool = [m for m in b.history if m.get("role") == "tool"][-1]["content"]
    verifica("guasto: «Adesso non posso crearla…», con la nota «guasto di adesso»",
             r.startswith("Adesso non posso crearla") and "guasto di adesso" in tool, r)
    from calliope import compressione as cp
    verifica("riassunto: i rifiuti sono «non riuscito, da riprovare»",
             "non riuscito, da riprovare" in cp.SISTEMA and "non riuscito, da riprovare"
             in cp.ISTRUZIONE_VOCE)
    verifica("riassunto e ripresa: un «non riuscito» di allora non vale adesso",
             "non vale adesso" in cp.testo_riassunto({}, "Dario")
             and "non vale adesso" in cp.testo_ripresa("x", 0))


def prova_descrizioni():
    reg = prepara_dgx(foto=False)[0].tools
    d = reg.get("lavoro_affida").description
    verifica("descrizione: lavoro_affida non sostituisce sviluppo_apri",
             "sviluppo_apri" in d and "rifiutato" in d, d[-300:])
    g = reg.get("estensione_gestisci").description
    verifica("descrizione: estensione_gestisci elenca quelle vere prima di dire come usarle",
             "davvero" in g, g[:160])
    e = reg.get("programma_esegui").description
    verifica("descrizione: programma_esegui è il modo di riusare un programma dell'agente",
             "comando a voce" in e, e[-160:])


def _lavoro(r, input_=()):
    return SimpleNamespace(stato="fatto", tipo="codice", risultato=r, input=list(input_),
                           titolo="programma che prenda in input due parametri", domanda="")


def prova_annuncio():
    lav = object.__new__(srv.Lavori)
    lav.female = True
    base = {"riassunto": "Ho creato un'estensione in Python che prende due parametri numerici e "
                         "ne restituisce la somma. Il programma funziona correttamente e tutti "
                         "i test passano.",
            "test": {"eseguiti": 6, "falliti": 0, "errori": 0}, "test_passano": True,
            "file": ["estensione_somma.py"]}
    ok = srv.Lavori.frase_finale(lav, _lavoro({**base, "dimostrazione": "Il programma ha finito "
                                               "in 0,2 secondi. L'ultima riga dice: «8».",
                                               "dimostrazione_esito": "fatto"}))
    verifica("annuncio: un lavoro di codice non si chiama estensione",
             "estension" not in ok.lower() and "programma in Python" in ok, ok)
    verifica("annuncio: dice come usarlo di nuovo (niente comandi inventati)",
             "«eseguilo»" in ok, ok)
    ko = srv.Lavori.frase_finale(lav, _lavoro({**base, "dimostrazione": "Il programma si è "
                                               "fermato con un errore (codice 1): «Uso: somma "
                                               "a b».", "dimostrazione_esito": "errore"}))
    verifica("annuncio: dimostrazione fermata → niente «funziona correttamente»",
             "funziona" not in ko and "errore" in ko and "senza dati" in ko
             and "eseguilo con" in ko, ko)
    verifica("annuncio: l'esito dei test resta (lo dice il programma)", "6 su 6" in ko, ko)
    chiesta = _lavoro({**base, "dimostrazione": "Il programma ha finito.",
                       "dimostrazione_esito": "fatto"})
    chiesta.non_estensione = True
    detto = srv.Lavori.frase_finale(lav, chiesta)
    verifica("annuncio: chiesto come «estensione» → dice che è un programma a sé",
             "Non è un'estensione di Calliope" in detto and "«eseguilo»" in detto, detto)
    verifica("annuncio (contrario): chiesto come programma → niente avviso",
             "Non è un'estensione" not in ok, ok)
    con = srv.Lavori.frase_finale(lav, _lavoro({**base, "dimostrazione": "Il programma si è "
                                                "fermato con un errore (codice 2).",
                                                "dimostrazione_esito": "errore",
                                                "dimostrazione_con_dati": True}))
    verifica("annuncio: fermata con i valori d'esempio → lo dice",
             "con i valori d'esempio" in con and "funziona" not in con, con)
    verifica("titolo: «Crea un'estensione che…» di un lavoro di codice → «programma…»",
             srv.senza_estensione(srv.titolo_da(EST["compito"])).startswith("programma che"))


def prova_dimostrazione():
    """La dimostrazione passa gli argomenti d'esempio dati dall'agente in consegna."""
    es = object.__new__(Esecuzioni)
    es.cfg = SimpleNamespace(agenti_dimostrazione=True, agenti_dimostrazione_attesa_s=0.1)
    visti = []

    def avvia(lav, dati=()):
        visti.append(list(dati))
        return SimpleNamespace(stato="fatto", dati=list(dati)), ""
    es.avvia = avvia
    es.attendi = lambda e, s: True
    es.frase = lambda e: "Il programma ha finito."
    es.log = print
    lav = SimpleNamespace(tipo="codice", stato="fatto", on_scheda=lambda c: None, input=[],
                          segui_schermi=True, id="L1",
                          risultato={"argomenti_esempio": ["3", "5"]})
    Esecuzioni.dimostra(es, lav)
    verifica("dimostrazione: con gli argomenti d'esempio dell'agente", visti == [["3", "5"]],
             str(visti))
    verifica("dimostrazione: esito e dati per l'annuncio",
             lav.risultato.get("dimostrazione_esito") == "fatto"
             and lav.risultato.get("dimostrazione_con_dati") is True, str(lav.risultato))
    from calliope.agenti import ciclo
    cons = next(f for f in ciclo.STRUMENTI_CODICE if f["function"]["name"] == "consegna")
    verifica("consegna: l'agente può dare gli argomenti d'esempio",
             "argomenti_esempio" in cons["function"]["parameters"]["properties"])


if __name__ == "__main__":
    prova_lessico()
    prova_decidi()
    prova_estensione_con_foto()
    prova_delega_con_foto_sfida()
    prova_delega_con_foto_voce()
    prova_contrari()
    prova_doppione()
    prova_doppione_piano()
    prova_rinuncia()
    prova_descrizioni()
    prova_annuncio()
    prova_dimostrazione()
    print(f"\n{errori} errori")
    sys.exit(1 if errori else 0)
