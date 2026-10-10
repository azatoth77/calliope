"""Il secondo giro vero della DGX del 10/10 (07:11–07:21, satellite «studio»), a secco
(10/10/2026; docs/aree/agenti-estensioni.md, docs/aree/voce-e-regole.md).

Tre difetti, con i turni veri:

A. Chiudere uno sviluppo era impossibile a voce. «Chiudo lo sviluppo di «…»? Se vuoi solo una
   pausa, dimmi «sospendi»…» non finiva con la domanda: `Brain.set_pending` non registrava la
   proposta, la conferma (che vuole `tool_in_sospeso`) non scattava e «No, chiudilo», «Non voglio
   una pausa, voglio che lo chiudi», «Sì, chiudi» rifacevano la domanda (07:17:03–07:18:33, 7
   volte). Ora la domanda è in fondo («… Lo chiudo?») e il sì, anche lungo, chiude; contrari:
   «sospendi» sospende, «no» non chiude. Uno sviluppo SOSPESO si chiude con la stessa conferma
   (prima «è sospeso: vuoi riprenderlo?», 07:14:03 e 07:21:20). La rete delle dichiarazioni
   prende «chiudo definitivamente lo sviluppo» senza tool (07:14:12), con i contrari (domande,
   offerte, condizionali).
B. Titoli che perdevano la parola che distingue: «…conti il numero di vocali…» e «…il numero di
   parole…» diventavano entrambi «programma in Python che conti il numero».
C. Ciò che Calliope ha detto davvero nella storia: il turno 07:17:03–07:18:33 ricostruito con il
   ciclo della voce (resa per la voce delle frasi e Brain vero con un modello finto): l'ultimo
   messaggio dell'assistente è esattamente ciò che è andato alla voce, frasi pronte dei tool
   comprese; dove la resa per la voce cambia il testo (nome di un tool, markdown) la storia si
   allinea (`storia_come_detta`), le frasi d'attesa restano fuori.

    python prove\\prova_giro_chiusura.py
"""

import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_ciclo as C  # noqa: E402
import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope import corsie  # noqa: E402
from calliope.agenti.servizio import titolo_da  # noqa: E402
from calliope.brain import is_claim  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.tts import split_sentences  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r) -> str:
    return str((r or {}).get("risposta_finale") or (r or {}).get("conferma") or "")


TITOLO = "programma in Python che conti il numero di vocali"
VOCALI = ("Scrivi un programma in Python che conti il numero di vocali presenti in una stringa "
          "inserita dall'utente.")


def sviluppo_fermato(svs, stato="aperta"):
    """Lo sviluppo delle vocali allo sviluppo, con il lavoro dell'agente fermato (07:16:48)."""
    sv = svs.apri("u1", "Dario", "programma", VOCALI, titolo=TITOLO)
    sv.specifica = VOCALI
    svs.passa(sv, "sviluppo")
    sv.nota = "annullato"
    if stato == "sospesa":
        svs.sospendi(sv)
    return sv


def turno(reg, ctx, detto, args, n, sospeso=None, come="voce"):
    ctx.regole = []
    ctx.user_text = detto
    ctx.speaker_ctx = P.speaker(come=come)
    ctx.tool_in_sospeso = sospeso
    try:
        return P.chiama(reg, ctx, "sviluppo_passo", args, turno=n)
    finally:
        ctx.tool_in_sospeso = None


# ═══════════════════════════ A. chiudere ═══════════════════════════

def prova_tool(tmp, iso):
    print("— A1. sviluppo_passo chiudi: la domanda in fondo; aperto e sospeso")
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "aperto", iso)
    sv = sviluppo_fermato(svc.sviluppi)
    r = turno(reg, ctx, "Chiudino sviluppo.", {"azione": "chiudi"}, 2)
    f, sosp = detta(r), r.get("in_sospeso") or {}
    verifica("07:17:03: chiede conferma con la domanda IN FONDO («… Lo chiudo?»), non chiude",
             sv.stato == "aperta" and f.endswith("Lo chiudo?") and "sospendi" in f
             and f"«{TITOLO}»" in f and sosp.get("domanda") == "Lo chiudo?"
             and sosp.get("argomenti") == {"azione": "chiudi"}
             and "sviluppo_chiudi_conferma" in ctx.regole, f)
    r = turno(reg, ctx, "Sì, chiudi.", {"azione": "chiudi"}, 3, sospeso="sviluppo_passo")
    verifica("…il «sì» (con l'azione in sospeso) chiude", sv.stato == "chiusa"
             and "sviluppo_chiuso" in ctx.regole and "torniamo alla conversazione normale"
             in detta(r), detta(r))

    # Sospeso (07:14:03 e 07:21:20)
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "sospeso", iso)
    sv = sviluppo_fermato(svc.sviluppi, "sospesa")
    r = turno(reg, ctx, "Chiudi proprio lo sviluppo.", {"azione": "chiudi"}, 2)
    f = detta(r)
    verifica("07:14:03: sviluppo sospeso → la stessa conferma, non «vuoi riprenderlo?»",
             sv.stato == "sospesa" and f.endswith("Lo chiudo?") and "riprenderlo" not in f
             and (r.get("in_sospeso") or {}).get("argomenti") == {"azione": "chiudi"}, f)
    r = turno(reg, ctx, "Sì.", {"azione": "chiudi"}, 3, sospeso="sviluppo_passo", come="breve")
    verifica("…e il «sì» chiude lo sviluppo sospeso", sv.stato == "chiusa", detta(r))
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "sospeso2", iso)
    sv = sviluppo_fermato(svc.sviluppi, "sospesa")
    turno(reg, ctx, "Sospendilo e chiudilo definitivamente.", {"azione": "chiudi"}, 2)
    r = turno(reg, ctx, "Chiudilo.", {"azione": "chiudi"}, 3)
    verifica("contrario: richiamato senza il «sì» alla domanda (nessuna azione in sospeso) "
             "non chiude", sv.stato == "sospesa", detta(r))
    r = turno(reg, ctx, "Riprendi lo sviluppo.", {"azione": "riprendi"}, 4)
    verifica("contrario: «riprendi» su uno sospeso lo riprende ancora",
             sv.stato == "aperta" and "sviluppo_ripreso" in ctx.regole, detta(r))


def prova_brain(tmp, iso):
    print("— A2. Brain: il turno vero, la proposta registrata e il sì lungo che chiude")
    casi = [("Sì, chiudi.", True), ("Non voglio una pausa, voglio che lo chiudi.", True),
            ("Ti ho detto che non voglio sospenderlo, voglio che tu lo chiudi proprio.", True),
            ("Chiudilo proprio.", True), ("No, chiudilo.", True)]
    for i, (frase, chiude) in enumerate(casi):
        cfg, reg, ctx, est, svc, b = S.brain(tmp / f"si{i}", iso)
        sv = sviluppo_fermato(svc.sviluppi)
        b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
        detto = S.risposta(b, "Chiudino sviluppo.")
        verifica(f"«Chiudino sviluppo.» → la domanda registrata come proposta ({frase})",
                 detto.endswith("Lo chiudo?") and b.has_pending()
                 and b.pending.get("tool") == "sviluppo_passo", detto)
        b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
        detto = S.risposta(b, frase)
        verifica(f"«{frase}» → chiuso (azione in sospeso, una volta sola)",
                 (sv.stato == "chiusa") == chiude and "azione_in_sospeso" in b.last_rules
                 and "torniamo alla conversazione normale" in detto
                 and "proposta_rifiutata" not in b.last_rules, f"{b.last_rules} {detto}")
    # Contrari: «sospendi» e «no»
    cfg, reg, ctx, est, svc, b = S.brain(tmp / "sosp", iso)
    sv = sviluppo_fermato(svc.sviluppi)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    S.risposta(b, "Chiudi lo sviluppo.")
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "sospendi"})]
    detto = S.risposta(b, "Sospendi.")
    verifica("contrario: «sospendi» dopo la domanda sospende, non chiude",
             sv.stato == "sospesa" and "sospendo" in detto, detto)
    cfg, reg, ctx, est, svc, b = S.brain(tmp / "no", iso)
    sv = sviluppo_fermato(svc.sviluppi)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    S.risposta(b, "Chiudi lo sviluppo.")
    b.backend.risposte = [[("text", "Va bene, lo lascio aperto.")]]
    detto = S.risposta(b, "No.")
    verifica("contrario: «no» rifiuta la proposta e lo sviluppo resta aperto",
             sv.stato == "aperta" and "proposta_rifiutata" in b.last_rules and not b.has_pending(),
             f"{b.last_rules} {detto}")
    # 07:20:43: «ferma il lavoro e chiudi tutti gli sviluppi» → due tool, la domanda in fondo
    cfg, reg, ctx, est, svc, b = S.brain(tmp / "due", iso)
    sv = sviluppo_fermato(svc.sviluppi)
    b.backend.risposte = [[("calls", [{"id": "c0", "name": "sviluppo_passo",
                                       "arguments": {"azione": "sospendi"}},
                                      {"id": "c1", "name": "sviluppo_passo",
                                       "arguments": {"azione": "chiudi"}}])]]
    detto = S.risposta(b, "Sospendilo e chiudilo definitivamente.")
    verifica("07:21:20: sospendi e chiudi nella stessa risposta → la domanda della chiusura "
             "in fondo, registrata", sv.stato == "sospesa" and detto.endswith("Lo chiudo?")
             and b.has_pending(), detto)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    S.risposta(b, "Sì, chiudilo.")
    verifica("…e il «sì» lo chiude", sv.stato == "chiusa")


def prova_dichiarate():
    print("— A3. dichiarazioni al presente su una cosa di Calliope")
    pos = ["Ho capito, chiudo definitivamente lo sviluppo di «programma in Python che conti il "
           "numero».", "Va bene, sospendo lo sviluppo.", "D'accordo, fermo subito il lavoro.",
           "Annullo il lavoro dell'agente.", "Ok, riprendo lo sviluppo di «somma».",
           "Chiudo tutti gli sviluppi.", "Perfetto, chiudo l'estensione.",
           "Apro lo sviluppo del programma.", "Interrompo il programma."]
    neg = ["Chiudo lo sviluppo?", "Lo chiudo?", "Se vuoi chiudo lo sviluppo.",
           "Se vuoi, chiudo lo sviluppo.", "Quando vuoi apro il programma.",
           "Chiudo lo sviluppo se me lo confermi.", "Chiudo lo sviluppo quando vuoi.",
           "Non chiudo lo sviluppo.", "Chiuderei lo sviluppo.", "Vuoi che chiudo lo sviluppo?",
           "Posso chiudere lo sviluppo.", "Il lavoro è fermo.",
           "Ti chiedo: chiudo lo sviluppo o lo sospendo?",
           "Chiudere lo sviluppo di «x» vuol dire finirlo qui; se vuoi solo una pausa, dimmi "
           "«sospendi» e lo riprendiamo quando vuoi. Lo chiudo?"]
    for t in pos:
        verifica(f"dichiarazione: «{t[:60]}»", is_claim(t))
    for t in neg:
        verifica(f"contrario: «{t[:60]}»", not is_claim(t))
    # Una dichiarazione con un'altra frase dopo resta tale (la regola di prima)
    verifica("contrario della condizione: «Apro il file, se ti serve altro dimmelo.» resta una "
             "dichiarazione", is_claim("Apro il file, se ti serve altro dimmelo."))


def prova_brain_dichiarata(tmp, iso):
    print("— A4. Brain: 07:14:12 «chiudo definitivamente lo sviluppo» senza tool non si dice")
    cfg, reg, ctx, est, svc, b = S.brain(tmp, iso)
    sv = sviluppo_fermato(svc.sviluppi)
    b.backend.risposte = [[("text", "Ho capito, chiudo definitivamente lo sviluppo di «" + TITOLO
                            + "».")],
                          S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    detto = S.risposta(b, "No, chiudilo.")
    verifica("spinta: la frase falsa non si dice, il modello chiama il tool (che chiede "
             "conferma)", "definitivamente" not in detto and "spinta_dichiarata" in b.last_rules
             and detto.endswith("Lo chiudo?") and sv.stato == "aperta",
             f"{b.last_rules} {detto}")


# ═══════════════════════════ B. titoli ═══════════════════════════

def prova_titoli():
    print("— B. titoli: la parola che distingue resta")
    casi = [
        (VOCALI, "programma in Python che conti il numero di vocali"),
        ("scrivi un programma in Python che conti il numero di parole in un testo fornito "
         "dall'utente", "programma in Python che conti il numero di parole"),
        ("Scrivi un programma in Python che calcoli la somma di tutti i numeri",
         "programma in Python che calcoli la somma di tutti i numeri"),
        ("Scrivi un programma in Python che stampi l'elenco dell'agenda di oggi",
         "programma in Python che stampi l'elenco dell'agenda di oggi"),
        # contrari: titoli già buoni restano uguali
        ("Scrivi uno script che rinomina le foto per data", "script che rinomina le foto per data"),
        ("Scrivi un programma in Python che sommi due numeri inseriti dall'utente e ne stampi "
         "il risultato.", "programma in Python che sommi due numeri"),
        ("Scrivi un programma in Python che moltiplica due numeri.",
         "programma in Python che moltiplica due numeri"),
        ("Scrivi un programma che conta le vocali", "programma che conta le vocali"),
        ("Crea un'estensione che dica il meteo di una città qualunque",
         "estensione che dica il meteo"),
    ]
    for compito, atteso in casi:
        t = titolo_da(compito)
        verifica(f"«{compito[:55]}» → «{atteso}»", t == atteso, t)
    verifica("i due programmi del giro hanno titoli diversi",
             titolo_da(VOCALI) != titolo_da(casi[1][0]))


# ═══════════════════════════ C. la storia = ciò che si è sentito ═══════════════════════════

def ciclo_per(b):
    cfg = b.cfg
    cfg.speaker_id_enabled = False
    cfg.barge_in_enabled = False
    srv = Servizi(cfg, registry=C.Persone(), stt=C.Whisper(),
                  instradamento=types.SimpleNamespace(), cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None),
                  attiva_minori=lambda: False, biblioteca=None, enroll_pending=False)
    c = Ciclo(srv, corsie.Corsia("locale"), C.Ascolto(), C.Voce(), C.ChiParla(), b,
              b.tool_ctx, types.SimpleNamespace(), None, threading.Event())
    c.rec = {}
    return c


def turno_voce(c, b, frase):
    """Il turno come lo fa il ciclo della voce (Ciclo._rispondi senza guardiano): ogni frase del
    modello passa dalla resa per la voce e va alla voce; poi `_storia_come_detta`."""
    t = types.SimpleNamespace(said=[], non_rivolta=False, context=None, watch={})
    attese = []
    b.on_tool_start = attese.append
    c.rec = {}
    for s in split_sentences(b.stream_reply(frase, "amministra")):
        s = c._frase_da_dire(t, s)
        if s:
            t.said.append(s)
    c._storia_come_detta(t)
    return t.said, attese


def ultima(b) -> str:
    return next((m.get("content") or "" for m in reversed(b.history)
                 if m.get("role") == "assistant" and not m.get("tool_calls")), "")


def prova_storia(tmp, iso):
    print("— C. la storia contiene ciò che la persona ha sentito")
    cfg, reg, ctx, est, svc, b = S.brain(tmp, iso)
    sv = sviluppo_fermato(svc.sviluppi)
    c = ciclo_per(b)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    sentito, _ = turno_voce(c, b, "Chiudino sviluppo.")
    verifica("07:17:03 ricostruito: l'ultimo messaggio dell'assistente è esattamente ciò che è "
             "andato alla voce (la frase pronta del tool, con la domanda)",
             ultima(b) == " ".join(sentito) and ultima(b).endswith("Lo chiudo?")
             and "storia_come_detta" not in c.rec.get("regole", []),
             f"{ultima(b)!r} ≠ {' '.join(sentito)!r}")
    ruoli = [m.get("role") for m in b.history]
    verifica("…con la chiamata e il risultato del tool prima (lo scambio tecnico resta come "
             "oggi: § 3.8 della macchina a stati)", ruoli[-4:] == ["user", "assistant", "tool",
                                                                   "assistant"], str(ruoli))
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    sentito, _ = turno_voce(c, b, "Sì, chiudi.")
    verifica("07:18:33 ricostruito: «Sì, chiudi.» chiude, e la storia ha ciò che si è sentito",
             sv.stato == "chiusa" and ultima(b) == " ".join(sentito), ultima(b))

    # La resa per la voce cambia il testo: la storia si allinea
    b.backend.risposte = [[("text", "Sono le **10:00** di mattina, come vedi. Ti serve altro?")]]
    sentito, _ = turno_voce(c, b, "Che ore sono?")
    verifica("markdown tolto per la voce: la storia diventa ciò che si è sentito "
             "(`storia_come_detta`)", ultima(b) == " ".join(sentito) and "**" not in ultima(b)
             and "10:00" in ultima(b)
             and "storia_come_detta" in c.rec.get("regole", []), f"{ultima(b)!r} {sentito}")
    # Le frasi d'attesa restano fuori
    b.backend.risposte = [S.chiamata("ora_attuale", {}), [("text", "Sono le 10:00.")]]
    reg.get("ora_attuale").announce = ("Vediamo.",)
    sentito, attese = turno_voce(c, b, "E adesso?")
    testi = " ".join(str(m.get("content") or "") for m in b.history[-4:])
    verifica("la frase d'attesa si sente ma non entra nella storia (come dal 26/09)",
             attese == ["Vediamo."] and "Vediamo" not in testi
             and ultima(b) == " ".join(sentito), f"{attese} {testi!r}")
    # Una frase detta diversa da quella del modello (i controlli dell'uscita): vince il detto
    b.backend.risposte = [[("text", "Il comune di Borgoverde ha circa diecimila abitanti. "
                                    "Ti serve altro?")]]
    t = types.SimpleNamespace(said=[], non_rivolta=False, context=None, watch={})
    for s in split_sentences(b.stream_reply("Quanti abitanti ha Borgoverde?", "amministra")):
        t.said.append("Secondo la ricerca il comune ha circa diecimila abitanti."
                      if s.startswith("Il comune") else s)
    c.rec = {}
    c._storia_come_detta(t)
    verifica("una frase cambiata prima della voce (i controlli dell'uscita): nella storia "
             "quella detta",
             ultima(b) == "Secondo la ricerca il comune ha circa diecimila abitanti. Ti serve "
                          "altro?"
             and "storia_come_detta" in c.rec.get("regole", []), ultima(b))
    # Contrario: niente detto (interrotta prima della prima frase) → la storia non si tocca
    prima = [dict(m) for m in b.history]
    c._storia_come_detta(types.SimpleNamespace(said=[], non_rivolta=False))
    verifica("contrario: nulla detto → storia invariata", b.history == prima)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro-chiusura-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    t0 = time.perf_counter()
    prova_tool(tmp0 / "tool", iso)
    prova_brain(tmp0 / "brain", iso)
    prova_dichiarate()
    prova_brain_dichiarata(tmp0 / "dichiarata", iso)
    prova_titoli()
    prova_storia(tmp0 / "storia", iso)
    print(f"\n[{time.perf_counter() - t0:.1f} s]")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
