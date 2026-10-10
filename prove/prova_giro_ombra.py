"""Il giro vero della DGX del 10/10 mattina (06:09–06:18, satellite «studio»), a secco
(10/10/2026; docs/aree/agenti-estensioni.md, docs/aree/voce-e-regole.md).

Due difetti, con i turni veri:

1. Una richiesta NUOVA per un programma diverso, con uno sviluppo già aperto, faceva avanzare
   quello VECCHIO. Alle 06:10:59, con «programma in Python che sommi due numeri» aperto
   all'analisi, «scrivi un programma in Python che moltiplica due numeri» → sviluppo_apri col
   compito nuovo, regole `lavori_conferma_implicita` e `sviluppo_fase`, «Ci lavoro in secondo
   piano» e l'agente lavorava sulla somma. Alle 06:16:44 lo stesso con «conta le parole» e
   «conta le vocali». La conferma implicita guardava solo difflib (≥ 0,6), e due frasi che
   differiscono di una parola ci stanno. Ora un compito che sostituisce una parola piena del
   titolo (sviluppo.altro_compito) non è mai il «sì» (`lavori_conferma_diversa`): Calliope
   chiede se sospendere quello aperto e aprire il nuovo, con i due titoli, e il «sì» lo fa
   (`sviluppo_cambio`). Contrari: la stessa richiesta ripetuta con altre parole o un «sì»
   restano conferma; una modifica dello stesso programma («che somma e moltiplica») resta
   dello sviluppo aperto.
2. Frasi che dichiarano un'azione mai fatta, senza tool: «Ho capito, l'analisi è stata
   annullata.» (06:10:40) e «D'accordo, procedo allora con lo sviluppo. Siamo passati alla fase
   di sviluppo…» (06:12:47, dopo la spinta). La rete `spinta_dichiarata` non le vedeva: le fasi
   dello sviluppo non erano tra le cose di Calliope del passivo, «procedo allora con» non
   aveva l'avverbio di raccordo e il cambio di fase non c'era. Contrari: lo stato («siamo
   all'analisi»), l'offerta («quando vuoi passiamo allo sviluppo»), le domande.

    python prove\\prova_giro_ombra.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope.brain import is_claim  # noqa: E402
from calliope.sviluppo import altro_compito  # noqa: E402
from calliope.tools import sviluppo as ts  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r) -> str:
    return str((r or {}).get("risposta_finale") or (r or {}).get("conferma") or "")


SOMMA = ("Scrivi un programma in Python che sommi due numeri inseriti dall'utente e ne stampi "
         "il risultato.")
MOLTIPLICA = ("Scrivi un programma in Python che moltiplichi due numeri inseriti dall'utente e "
              "ne stampi il risultato.")
VOCALI = "scrivi un programma in Python che conti le vocali in una stringa fornita dall'utente"
PAROLE = "scrivi un programma in Python che conti le parole in una stringa fornita dall'utente"


def apri(tmp, iso, compito=SOMMA, detto="Scrivi un programma in Python che somma due numeri."):
    """Dario chiede un programma con la voce: sviluppo aperto all'analisi, proposta L1."""
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    ctx.speaker_ctx = P.speaker()
    ctx.user_text = detto
    r = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "programma", "compito": compito}, turno=1)
    return cfg, reg, ctx, est, svc, r


def turno(reg, ctx, detto, nome, args, n, come="voce"):
    ctx.regole = []
    ctx.user_text = detto
    ctx.speaker_ctx = P.speaker(come=come)
    return P.chiama(reg, ctx, nome, args, turno=n)


# ═══════════════════════════ 1. un altro programma ═══════════════════════════

def prova_altro_compito():
    print("— 1a. altro_compito: sostituzione di una parola piena del titolo")
    t_somma = "programma in Python che sommi due numeri"
    casi = [
        ("moltiplica al posto di somma (06:10:59)", MOLTIPLICA, t_somma, SOMMA, True),
        ("parole al posto di vocali (06:16:44)", PAROLE, "programma in Python che conti le "
                                                         "vocali", VOCALI, True),
        ("un programma tutto diverso", "Scrivi un programma che traduce un testo in inglese",
         t_somma, SOMMA, True),
        ("contrario: la stessa richiesta con altre parole",
         "Scrivi il programma che somma i due numeri", t_somma, SOMMA, False),
        ("contrario: dettagli aggiunti dal modello",
         "Scrivi un programma Python che somma due numeri presi dalla tastiera, anche decimali",
         t_somma, SOMMA, False),
        ("contrario: una modifica (somma e moltiplica)",
         "Scrivi un programma che somma e moltiplica due numeri", t_somma, SOMMA, False),
        ("contrario: le risposte alle domande dell'analisi (la richiesta con le risposte)",
         "un programma in Python che sommi due numeri interi letti da riga di comando",
         t_somma, SOMMA, False),
        ("contrario: compito vuoto", "", t_somma, SOMMA, False),
    ]
    for nome, compito, titolo, rif, atteso in casi:
        verifica(nome, altro_compito(compito, titolo, rif) == atteso, compito)


def prova_moltiplica(tmp, iso):
    print("— 1b. il giro vero: «moltiplica» con «somma» aperto non avvia la somma")
    cfg, reg, ctx, est, svc, r = apri(tmp / "a", iso)
    svs = svc.sviluppi
    somma = svs.corrente("u1")
    verifica("preparazione: sviluppo della somma all'analisi, proposta L1",
             somma is not None and somma.fase == "analisi" and somma.proposto == "L1"
             and "Va bene così" in detta(r), detta(r))
    r = turno(reg, ctx, "Calliope scrive un programma in Python che moltiplica due numeri.",
              "sviluppo_apri", {"tipo": "programma", "compito": MOLTIPLICA}, 3)
    sosp = r.get("in_sospeso") or {}
    verifica("06:10:59: nessun lavoro avviato, la somma resta all'analisi senza lavoro",
             not svc.attivi() and somma.lavoro is None and somma.fase == "analisi"
             and "lavori_conferma_implicita" not in ctx.regole
             and "sviluppo_fase" not in ctx.regole, f"{ctx.regole} {detta(r)}")
    verifica("…regole `lavori_conferma_diversa` e `sviluppo_altro_bloccato`",
             "lavori_conferma_diversa" in ctx.regole
             and "sviluppo_altro_bloccato" in ctx.regole, str(ctx.regole))
    f = detta(r)
    verifica("…la domanda dice i due titoli e finisce con la domanda",
             "«programma in Python che sommi due numeri»" in f
             and "«programma in Python che moltiplichi due numeri»" in f
             and f.endswith("e apra «programma in Python che moltiplichi due numeri»?")
             and sosp.get("tool") == "sviluppo_passo"
             and sosp.get("argomenti") == {"azione": "sospendi"}
             and "aprire quello di" in sosp.get("cosa", ""), f)
    r = turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "sospendi"}, 4, come="breve")
    nuovo = svs.corrente("u1")
    verifica("«sì» (sviluppo_passo sospendi, frase breve): la somma sospesa, aperto lo "
             "sviluppo della moltiplicazione con la sua proposta (`sviluppo_cambio`)",
             somma.stato == "sospesa" and nuovo is not None and nuovo is not somma
             and "moltiplic" in nuovo.titolo and nuovo.fase == "analisi"
             and nuovo.proposto
             and "sviluppo_cambio" in ctx.regole and not svc.attivi(),
             f"{ctx.regole} {detta(r)}")
    f = detta(r)
    verifica("…la risposta dice la sospensione e poi la specifica nuova con «Va bene così?»",
             f.startswith("Ho sospeso lo sviluppo di «programma in Python che sommi due "
                          "numeri»") and "moltiplichi" in f and "Va bene così" in f
             and (r.get("in_sospeso") or {}).get("argomenti", {}).get("proposta")
             == nuovo.proposto, f)
    lav = svc.offerte["u1"]["lavoro"]
    r = turno(reg, ctx, "Sì, va bene.", "sviluppo_apri", {"proposta": lav.id}, 5, come="breve")
    verifica("…e il «sì» alla proposta avvia la MOLTIPLICAZIONE",
             "Ci lavoro" in detta(r) and nuovo.lavoro == lav.id and "moltiplic" in lav.compito,
             detta(r))

    # Contrario: il «sì» arriva troppo tardi → solo la sospensione
    cfg, reg, ctx, est, svc, r = apri(tmp / "b", iso)
    somma = svc.sviluppi.corrente("u1")
    turno(reg, ctx, "Scrivi un programma che moltiplica due numeri.", "sviluppo_apri",
          {"tipo": "programma", "compito": MOLTIPLICA}, 3)
    r = turno(reg, ctx, "Sospendi lo sviluppo.", "sviluppo_passo", {"azione": "sospendi"}, 9)
    verifica("contrario: sospendi sei turni dopo → solo la sospensione, niente sviluppo nuovo",
             somma.stato == "sospesa" and svc.sviluppi.corrente("u1") is None
             and "sviluppo_cambio" not in ctx.regole, detta(r))

    # Contrario: la richiesta nuova senza la voce riconosciuta → il «sì» non la apre da sé
    cfg, reg, ctx, est, svc, r = apri(tmp / "c", iso)
    turno(reg, ctx, "Scrivi un programma che moltiplica due numeri.", "sviluppo_apri",
          {"tipo": "programma", "compito": MOLTIPLICA}, 3, come="breve")
    r = turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "sospendi"}, 4, come="breve")
    nuovo = svc.sviluppi.corrente("u1")
    verifica("contrario: richiesta nuova con una frase breve, «sì» breve → nessuna proposta "
             "senza la voce (la domanda della voce o la sfida)",
             nuovo is None or not nuovo.proposto, f"{ctx.regole} {detta(r)}")


def prova_parole(tmp, iso):
    print("— 1c. il giro vero: «conta le parole» con «conta le vocali» aperto")
    cfg, reg, ctx, est, svc, r = apri(tmp, iso, VOCALI,
                                      "Scrivimi un programma in Python che conta le vocali.")
    vocali = svc.sviluppi.corrente("u1")
    r = turno(reg, ctx, "Scrivimi un programma che conta le parole.", "sviluppo_apri",
              {"tipo": "programma", "compito": PAROLE}, 4)
    verifica("06:16:44: niente lavoro sulle vocali, la domanda con i due titoli",
             not svc.attivi() and vocali.lavoro is None and "vocali" in detta(r)
             and "parole" in detta(r) and "lavori_conferma_diversa" in ctx.regole, detta(r))


def prova_contrari(tmp, iso):
    print("— 1d. contrari: stessa richiesta = conferma, modifica = modifica")
    # La stessa richiesta ripetuta con altre parole (il «sì» del 08/10)
    cfg, reg, ctx, est, svc, r = apri(tmp / "a", iso)
    r = turno(reg, ctx, "Sì, scrivi il programma che somma i due numeri.", "sviluppo_apri",
              {"tipo": "programma", "compito": "Scrivi un programma in Python che somma due "
                                               "numeri"}, 2)
    verifica("la richiesta ripetuta con altre parole vale come il «sì» "
             "(`lavori_conferma_implicita`)",
             "lavori_conferma_implicita" in ctx.regole and "Ci lavoro" in detta(r)
             and svc.attivi(), f"{ctx.regole} {detta(r)}")
    cfg, reg, ctx, est, svc, r = apri(tmp / "b", iso)
    r = turno(reg, ctx, "Sì, procedi.", "sviluppo_apri",
              {"tipo": "programma", "compito": "Scrivi il programma Python che somma due "
                                               "numeri dati dall'utente"}, 2, come="breve")
    verifica("un «sì» con il compito riscritto dal modello resta conferma",
             "lavori_conferma_implicita" in ctx.regole and svc.attivi(), str(ctx.regole))
    cfg, reg, ctx, est, svc, r = apri(tmp / "b2", iso)
    r = turno(reg, ctx, "Sì.", "sviluppo_apri",
              {"tipo": "programma", "compito": MOLTIPLICA}, 2, come="breve")
    verifica("contrario: un «sì» con un compito che ne sostituisce una parola (moltiplichi) "
             "non conferma la somma", not svc.attivi()
             and "lavori_conferma_implicita" not in ctx.regole, f"{ctx.regole} {detta(r)}")
    # La modifica dello stesso programma: resta dello sviluppo aperto, nuova analisi
    ts._PROSSIMI.clear()
    cfg, reg, ctx, est, svc, r = apri(tmp / "c", iso)
    somma = svc.sviluppi.corrente("u1")
    r = turno(reg, ctx, "Fai che sommi e moltiplichi i due numeri.", "sviluppo_apri",
              {"tipo": "programma", "compito": "Scrivi un programma in Python che sommi e "
                                               "moltiplichi due numeri inseriti dall'utente"}, 2)
    verifica("una modifica non conferma la proposta di prima e non è un altro sviluppo: la "
             "specifica nuova nello stesso sviluppo",
             not svc.attivi() and "lavori_conferma_implicita" not in ctx.regole
             and "sviluppo_altro_bloccato" not in ctx.regole
             and svc.sviluppi.corrente("u1") is somma and somma.proposto == "L2"
             and "moltiplic" in somma.specifica, f"{ctx.regole} {detta(r)}")
    verifica("…e nessuna richiesta nuova in attesa", not ts._PROSSIMI.get("u1"),
             str(ts._PROSSIMI))


# ═══════════════════════════ 2. azioni dichiarate ═══════════════════════════

def prova_dichiarate():
    print("— 2a. dichiarazioni d'azione: le fasi dello sviluppo")
    pos = ["Ho capito, l'analisi è stata annullata. Siamo ancora in fase di analisi per "
           "«programma in Python che sommi due numeri».",
           "D'accordo, procedo allora con lo sviluppo. Siamo passati alla fase di sviluppo per "
           "il programma «programma in Python che moltiplichi due numeri».",
           "Siamo passati alla fase di sviluppo.", "Lo sviluppo è stato sospeso.",
           "Perfetto, passiamo allo sviluppo.", "Sono tornata all'analisi.",
           "Lo sviluppo è passato al collaudo.", "Torniamo alla fase di analisi.",
           "Procedo dunque con l'avvio del lavoro.", "La revisione è stata chiusa."]
    neg = ["Siamo all'analisi di «programma che conta le vocali».",
           "Siamo ancora in fase di analisi.", "Restiamo pure in fase di analisi.",
           "Quando vuoi passiamo allo sviluppo.", "Quando vuoi, passiamo allo sviluppo.",
           "Se vuoi, torniamo all'analisi.", "Passiamo allo sviluppo?",
           "Vuoi che passiamo allo sviluppo?", "Non siamo passati allo sviluppo.",
           "Dopo passiamo al collaudo.", "La modalità sviluppo serve per scrivere programmi.",
           "Il programma è pronto: siamo al collaudo.", "Va bene, procedo con la ricerca.",
           "L'analisi è stata chiara?", "Lo sviluppo resta aperto, allo sviluppo."]
    for t in pos:
        verifica(f"dichiarazione: «{t[:60]}»", is_claim(t))
    for t in neg:
        verifica(f"contrario: «{t[:60]}»", not is_claim(t))


def prova_brain(tmp, iso):
    print("— 2b. Brain: le due frasi del giro vero non si dicono")
    cfg, reg, ctx, est, svc, b = S.brain(tmp, iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", SOMMA,
                  titolo="programma in Python che sommi due numeri")
    sv.specifica = SOMMA
    b.backend.risposte = [[("text", "Ho capito, l'analisi è stata annullata. Siamo ancora in "
                                    "fase di analisi per «programma in Python che sommi due "
                                    "numeri».")],
                          S.chiamata("sviluppo_passo", {"azione": "chiudi"}),
                          [("text", "Va bene.")]]
    detto = S.risposta(b, "Annullahi.")
    verifica("06:10:40: «l'analisi è stata annullata» senza tool → spinta, e il modello chiama "
             "il tool (la frase falsa non si dice)",
             "annullata" not in detto and "spinta_dichiarata" in b.last_rules
             and "sviluppo_passo" in str(b.last_tools) and "Chiudo lo sviluppo" in detto,
             f"{b.last_rules} {detto}")
    b.backend.risposte = [[("text", "Ho avviato lo sviluppo.")],
                          [("text", "D'accordo, procedo allora con lo sviluppo. Siamo passati "
                                    "alla fase di sviluppo per il programma.")]]
    detto = S.risposta(b, "Non c'è problema.")
    verifica("06:12:47: di nuovo dichiarato dopo la spinta → «Non ci sono riuscita…», mai "
             "«siamo passati alla fase di sviluppo» (`dichiarata_taciuta`)",
             "passati" not in detto and "procedo" not in detto
             and "dichiarata_taciuta" in b.last_rules, f"{b.last_rules} {detto}")
    b.backend.risposte = [[("text", "Siamo ancora all'analisi di «programma in Python che "
                                    "sommi due numeri»: dimmi se la specifica va bene.")]]
    detto = S.risposta(b, "A che punto siamo?")
    verifica("contrario: lo stato detto senza dichiarare un'azione si dice, senza spinta",
             "Siamo ancora all'analisi" in detto and "spinta_dichiarata" not in b.last_rules,
             f"{b.last_rules} {detto}")


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro-ombra-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    prova_altro_compito()
    prova_moltiplica(tmp0 / "moltiplica", iso)
    prova_parole(tmp0 / "parole", iso)
    prova_contrari(tmp0 / "contrari", iso)
    prova_dichiarate()
    prova_brain(tmp0 / "brain", iso)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
