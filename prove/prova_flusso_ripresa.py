"""
Comandi del flusso e ripresa nella modalità sviluppo (12/10/2026, lavoro 3 dell'analisi del
flusso; calliope/sviluppo.py, tools/sviluppo.py, politica.py, tools/estensioni.py,
agenti/servizio.py). I casi veri della DGX del 06–12/10, riscritti con parole e nomi nostri:

1. **Comandi del flusso** (forme chiuse brevi e intere, principio 10): «chiudi tutti gli
   sviluppi» con una domanda sola (anche se il modello l'ha presa per una domanda all'agente);
   un'azione che non si disfa (fermare il lavoro, chiudere al «sì», annullare) non parte da una
   storpiatura («Am nulla il lavoro.», «Annullahi.»), al più una domanda; «ricominciamo» con uno
   sviluppo aperto lo sospende; `estensione_gestisci modifica` (inventato) è sviluppo_apri con la
   modifica; «modifica l'estensione X» senza `modifica` non ne crea una nuova; «rinomina»
   detto all'analisi non è impossibile. Con i contrari.
2. **A4**: «torniamo all'analisi» non ferma niente prima della modifica; la modifica non ferma il
   lavoro prima del «sì» e «lascia com'era» torna al collaudo della versione provata o al lavoro
   che intanto continua; al «sì» il lavoro di prima si ferma e quello nuovo parte dai suoi file
   (anche alla prima versione).
3. **A5**: un lavoro fermo a una tappa che aspetta troppo è «messo da parte» con i file del giro,
   non «non è andato»; lo sviluppo sospeso si riprende con il lavoro; «rifallo» dopo «fermalo» o
   un arresto riparte dai file del giro (il thread dei lavori li rilegge quando comincia).
4. **Ripresa più corta**: «riprendiamo lo sviluppo di…» con lo sviluppo già aperto e il lavoro
   fermato è una domanda sola, e il «sì» lo fa ripartire (2 turni; erano 4–5).
5. **M7**: un programma consegnato tiene i requisiti e si riapre con «riapri il programma…».
6. **Uscire con un lavoro in corso**: lo sviluppo resta sospeso e il lavoro consegnato dopo si
   collauda (anche con il lavoro fermo a una domanda).

A secco, ~2 s.

    python prove\\prova_flusso_ripresa.py
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_specifica_viva as SV  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope import politica  # noqa: E402
from calliope.agenti import richiesta as ar  # noqa: E402
from calliope.agenti import servizio as srv  # noqa: E402
from calliope.sviluppo import (MESSO_DA_PARTE, VINCOLO_GIRO, file_del_giro)  # noqa: E402
from calliope.tools import estensioni as te  # noqa: E402
from calliope.tools import sviluppo as ts  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r) -> str:
    return str((r or {}).get("risposta_finale") or (r or {}).get("conferma") or "")


def turno(reg, ctx, nome, args, n, detto="", sospeso=None, politica_turno=None):
    ctx.regole = []
    ctx.user_text = detto
    ctx.tool_in_sospeso = sospeso
    ctx.politica = politica_turno
    try:
        return P.chiama(reg, ctx, nome, args, turno=n)
    finally:
        ctx.tool_in_sospeso = None
        ctx.politica = None


def cartella_giro(tmp: Path) -> Path:
    """La cartella dei risultati di un giro fermo, come la lascia il servizio dei lavori."""
    d = tmp / "giro"
    (d / "esempi_veri").mkdir(parents=True, exist_ok=True)
    (d / "estensione.py").write_text("def esegui(dati, calliope):\n    return {}\n",
                                     encoding="utf-8")
    (d / "test_estensione.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (d / "lavoro.json").write_text("{}", encoding="utf-8")
    (d / "calliope_estensione.py").write_text("# runtime\n", encoding="utf-8")
    (d / "CAPACITA.md").write_text("contratto\n", encoding="utf-8")
    (d / "esempi_veri" / "a.json").write_text("{}", encoding="utf-8")
    return d


def sviluppo_al_lavoro(tmp, iso, titolo="Meteo per città"):
    """Uno sviluppo di un'estensione allo sviluppo con l'agente al lavoro."""
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "estensione", "il meteo di una città", titolo=titolo)
    sv.specifica = "dice il meteo di una città qualunque"
    lav = svc.nuovo("estensione", sv.specifica, "u1", "Dario")
    lav.titolo = titolo
    svc.avvia(lav)
    svs.avviato(lav)
    return cfg, reg, ctx, est, svc, svs, sv, lav


# ═══════════════════════════ 1. comandi del flusso ═══════════════════════════

def prova_chiudi_tutti(tmp, iso):
    print("— 1a. «chiudi tutti gli sviluppi»: una domanda sola, anche da sviluppo_chiedi")
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "tutti", iso)
    svs = svc.sviluppi
    a = svs.apri("u1", "Dario", "programma", "conta le vocali", titolo="conta vocali")
    svs.sospendi(a)
    b = svs.apri("u1", "Dario", "programma", "conta le parole", titolo="conta parole")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, 2, "Chiudi tutti gli sviluppi.")
    f = detta(r)
    verifica("10/10 13:43, il modello chiama chiudi senza quale: la forma chiusa intera → una "
             "domanda per tutti (sviluppo_chiudi_tutti_forma)",
             f.endswith("Chiudo «conta parole» e «conta vocali»?")
             and "sviluppo_chiudi_tutti_forma" in ctx.regole
             and (r.get("in_sospeso") or {}).get("argomenti", {}).get("quale") == "tutti"
             and a.stato == "sospesa" and b.stato == "aperta", f)
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, 3, "Sì.",
              sospeso="sviluppo_passo")
    verifica("…il «sì» li chiude tutti", a.stato == "chiusa" and b.stato == "chiusa", detta(r))

    cfg, reg, ctx, est, svc = S.ambiente(tmp / "uno", iso)
    svs = svc.sviluppi
    a = svs.apri("u1", "Dario", "programma", "conta le vocali", titolo="conta vocali")
    svs.sospendi(a)
    b = svs.apri("u1", "Dario", "programma", "conta le parole", titolo="conta parole")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, 2, "Chiudi lo sviluppo.")
    verifica("contrario: «Chiudi lo sviluppo.» chiude solo quello aperto",
             detta(r).endswith("Lo chiudo?") and "sviluppo_chiudi_tutti_forma" not in ctx.regole,
             detta(r))
    r = turno(reg, ctx, "sviluppo_chiedi", {"domanda": "chiudi tutti gli sviluppi"}, 3,
              "Calliope, chiudi tutti gli sviluppi.")
    verifica("10/10 11:48, preso per una domanda a chi l'ha scritto (sviluppo_chiedi): è la "
             "chiusura, con la sua domanda (prima «di quale codice parli?»)",
             detta(r).endswith("Chiudo «conta parole» e «conta vocali»?")
             and "sviluppo_chiudi_tutti_forma" in ctx.regole, detta(r))
    r = turno(reg, ctx, "sviluppo_chiedi", {"domanda": "perché conta male?"}, 4,
              "Perché conta male le parole?")
    verifica("contrario: una domanda vera resta una domanda", "Chiudo" not in detta(r)
             and "sviluppo_chiudi_tutti_forma" not in ctx.regole, detta(r))


def prova_storpiature(tmp, iso):
    print("— 1b. un'azione che non si disfa non parte da una storpiatura")
    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "storp", iso)
    t = politica.Turno(testo="Am nulla il lavoro.", persona="u1")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, 3, "Am nulla il lavoro.",
              politica_turno=t)
    verifica("«Am nulla il lavoro.» → ferma: prima la domanda, il lavoro va avanti",
             lav.stato == "in_corso" and "Non sono sicura di aver capito" in detta(r)
             and "fermi il lavoro" in detta(r), json.dumps(r, ensure_ascii=False)[:300])
    t = politica.Turno(testo="Annullahi.", persona="u1")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, 4, "Annullahi.",
              politica_turno=t)
    verifica("«Annullahi.» → ferma: la domanda", lav.stato == "in_corso"
             and "Non sono sicura" in detta(r), detta(r))
    t = politica.Turno(testo="Ferma il lavoro dell'agente.", persona="u1")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, 5, "Ferma il lavoro dell'agente.",
              politica_turno=t)
    verifica("contrario: «Ferma il lavoro dell'agente.» ferma subito", lav.stato == "annullato"
             and "Ho fermato il lavoro" in detta(r), detta(r))
    # Le regole sul testo, una per una (anche in prova_testo)
    ferma, chiudi = {"azione": "ferma"}, {"azione": "chiudi"}
    casi = [("sviluppo_passo", ferma, "Am nulla il lavoro.", None, True),
            ("sviluppo_passo", ferma, "Spendilo.", None, True),
            ("lavoro_annulla", {}, "Nulla è lavoro.", None, True),
            ("sviluppo_passo", chiudi, "Chiudin.", "sviluppo_passo", True),
            ("sviluppo_passo", chiudi, "Giudino.", "sviluppo_passo", True),
            # contrari
            ("sviluppo_passo", chiudi, "Chiudin.", None, False),       # chiede comunque lui
            ("sviluppo_passo", chiudi, "Sì, chiudilo.", "sviluppo_passo", False),
            ("sviluppo_passo", ferma, "Fermalo.", None, False),
            ("sviluppo_passo", ferma, "Annulla il lavoro.", None, False),
            ("sviluppo_passo", {"azione": "sospendi"}, "Spendilo.", None, False),
            ("lavoro_annulla", {}, "Annulla la sveglia delle 7.", None, False),
            ("casa_comando", {}, "Annullahi.", None, False)]
    for nome, args, testo, sosp, atteso in casi:
        t = politica.Turno(testo=testo, in_sospeso=sosp)
        verifica(f"irreversibile da storpiatura: {nome} {args} «{testo}» → {atteso}",
                 politica.irreversibile_storpiato(nome, args, t) is atteso)
    t = politica.Turno(testo="Annullahi.", sfida=True)
    verifica("contrario: la frase di sfida superata vale", not politica.irreversibile_storpiato(
        "sviluppo_passo", ferma, t))


def prova_ricominciamo(tmp, iso):
    print("— 1c. «ricominciamo» con uno sviluppo aperto lo sospende")
    from calliope.ciclo import Ciclo
    from calliope.tools.conversazioni import NUOVA_FRASE, _conversazione_nuova
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "ric", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", "gradi in Fahrenheit",
                  titolo="programma che converte i gradi Celsius in Fahrenheit")
    regole = []
    ciclo = SimpleNamespace(tool_ctx=ctx, rule=regole.append)
    frase = Ciclo._sviluppo_sospeso_ricominciando(ciclo)
    verifica("10/10 10:39: «ricominciamo» (regola della forma chiusa) sospende lo sviluppo "
             "aperto e lo dice", sv.stato == "sospesa" and "l'ho sospeso" in frase
             and "sviluppo_sospeso_ricominciando" in regole, frase)
    verifica("…così la richiesta dopo («un programma che converte i chilometri…») è uno "
             "sviluppo nuovo, non una modifica di quello di prima", svs.corrente("u1") is None)
    verifica("contrario: senza uno sviluppo aperto, niente", Ciclo._sviluppo_sospeso_ricominciando(
        SimpleNamespace(tool_ctx=ctx, rule=regole.append)) == "")
    svs.riprendi(sv)
    ctx.regole = []
    r = _conversazione_nuova(ctx, cosa="")
    verifica("conversazione_nuova (detta con parole sue): lo stesso, nella frase del tool",
             sv.stato == "sospesa" and detta(r).startswith(NUOVA_FRASE) and "sospeso" in detta(r),
             detta(r))
    r = _conversazione_nuova(ctx, cosa="")
    verifica("contrario: senza sviluppo aperto la frase di sempre", detta(r) == NUOVA_FRASE,
             detta(r))
    ctx.speaker_ctx = P.speaker("Bianca", "familiare")
    svs.riprendi(sv)
    r = _conversazione_nuova(ctx, cosa="")
    verifica("contrario: un'altra persona non sospende lo sviluppo di chi amministra",
             sv.stato == "aperta" and detta(r) == NUOVA_FRASE, detta(r))
    ctx.speaker_ctx = P.speaker()


def prova_estensioni(tmp, iso):
    print("— 1d. modificare un'estensione: niente nuove accanto, niente tool inventati")
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "est", iso)
    P.installa(est, S.M1, S.CODICE1)
    r = turno(reg, ctx, "estensione_gestisci", {"azione": "modifica",
                                                "nome": "Meteo Borgoverde e Valfiorita"}, 1,
              "Modifica l'estensione Meteo Borgoverde e Valfiorita: deve dire anche il vento.")
    sv = svc.sviluppi.corrente("u1")
    verifica("09/10 20:40: estensione_gestisci con azione «modifica» (non esiste) → sviluppo_apri "
             "con modifica (estensione_gestisci_modifica): una versione nuova di quella",
             "estensione_gestisci_modifica" in ctx.regole and sv is not None
             and sv.estensione == "meteo_citta"
             and "Sarà una versione nuova di «Meteo Borgoverde e Valfiorita»" in detta(r),
             json.dumps(r, ensure_ascii=False)[:300])
    off = svc.offerte.get("u1")
    verifica("…con la frase della persona come compito",
             off is not None and "anche il vento" in off["lavoro"].compito,
             str(off and off["lavoro"].compito))
    verifica("contrario: «aggiorna» resta di estensione_gestisci (approva la versione nuova)",
             te.modifica_inventata({"azione": "aggiorna", "nome": "x"}, ctx) is None
             and te.modifica_inventata({"azione": "elenca"}, ctx) is None)

    cfg, reg, ctx, est, svc = S.ambiente(tmp / "est2", iso)
    P.installa(est, S.M1, S.CODICE1)
    r = turno(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": "codifica il nome "
              "della città"}, 1, "Modifica l'estensione Meteo Borgoverde e Valfiorita: codifica "
              "bene il nome della città.")
    verifica("08/10 15:36: «Modifica l'estensione X» senza modifica né nome → la scelta torna al "
             "modello, niente estensione nuova accanto (estensione_simile_scelta)",
             "estensione_simile_scelta" in ctx.regole and svc.sviluppi.corrente("u1") is None
             and "modifica = \"meteo_citta\"" in str(r.get("cosa_fare")), json.dumps(r)[:300])
    ctx.user_text = "Fammi un'estensione che dica le maree."
    verifica("contrario: una richiesta che non nomina un'estensione che c'è",
             te._detta_nella_frase(ctx, est, "") == "")
    ctx.user_text = "Modifica l'estensione Meteo Borgoverde e Valfiorita."
    svc.sviluppi.apri("u1", "Dario", "estensione", "le maree", titolo="Maree")
    verifica("contrario: dentro uno sviluppo aperto decide il modello (l'analisi)",
             te._detta_nella_frase(ctx, est, "") == "")

    # «Rinomina»: all'analisi non è impossibile né un lavoro (caso vero dell'08/10 15:46)
    e = ar.interpreta(json.dumps({"punti": {}, "impossibile": "RINOMINA"}), "estensione")
    verifica("l'analisi: «RINOMINA» per un'estensione → esito rinomina", e.esito == "rinomina"
             and not e.motivo, e.esito)
    e = ar.interpreta(json.dumps({"punti": {}, "impossibile": "serve la rete di casa"}),
                      "estensione")
    verifica("contrario: un impossibile vero resta impossibile", e.esito == "impossibile")
    e = ar.interpreta(json.dumps({"punti": {}, "impossibile": "RINOMINA"}), "codice")
    verifica("contrario: per un programma «RINOMINA» non è un esito", e.esito == "impossibile")


# ═══════════════════════════ 2. A4: la modifica non distrugge ═══════════════════════════

def gioco_al_lavoro(tmp, modifiche):
    """Il gioco delle porte (prova_specifica_viva) con la proposta accettata: allo sviluppo,
    l'agente al lavoro."""
    agente = SV.AgenteVivo(modifiche=modifiche)
    cfg, reg, ctx, est, svc, sv, out = SV.gioco(tmp, agente)
    lav = SV.ultimo(svc)
    SV.chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id, "tappe": False}, 2,
              "Sì, tutto insieme.")
    return cfg, reg, ctx, est, svc, sv, lav


def prova_a4(tmp, iso):
    print("— 2. A4: «torniamo all'analisi» e la modifica non buttano via niente prima del «sì»")
    cfg, reg, ctx, est, svc, sv, lav = gioco_al_lavoro(tmp / "a4a", [SV.MOD_MOSTRI])
    verifica("(il gioco è allo sviluppo, con l'agente al lavoro)", sv.fase == "sviluppo"
             and lav.stato == "in_corso" and sv.lavoro == lav.id, f"{sv.fase} {lav.stato}")
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi"}, 3, "Torniamo all'analisi.")
    verifica("«torniamo all'analisi» senza dire cosa: niente si ferma né cambia fase, la domanda",
             sv.fase == "sviluppo" and lav.stato == "in_corso" and sv.lavoro == lav.id
             and detta(r).startswith("D'accordo: cosa vuoi cambiare?")
             and "sviluppo_analisi_senza_modifica" in ctx.regole, detta(r))
    req_prima = [x["testo"] for x in sv.requisiti]
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i mostri "
                  "danno punti"}, 4, "Anche i mostri danno punti.")
    nuovo = SV.ultimo(svc)
    verifica("la modifica con l'agente al lavoro: il lavoro NON si ferma, la proposta dice cosa "
             "cambia e che il lavoro di prima continua fino al «sì»",
             lav.stato == "in_corso" and svc.annullati == [] and sv.fase == "analisi"
             and sv.ritorno.get("lavoro") == lav.id
             and detta(r).startswith("Il lavoro di prima intanto continua: lo fermo solo al tuo "
                                     "sì. Ho cambiato una cosa:")
             and "sviluppo_modifica_lavoro_continua" in ctx.regole, detta(r))
    verifica("…il lavoro nuovo ripartirà dai file di quello di prima (parti_da)",
             getattr(nuovo, "parti_da", None) is lav)
    verifica("…e lo sviluppo non si sospende dopo 30 minuti mentre l'agente lavora",
             (setattr(sv, "ultimo", time.time() - 40 * 60) or True)
             and svc.sviluppi.corrente("u1") is sv)
    sv.ultimo = time.time()
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "indietro"}, 5, "No, lascia com'era.")
    verifica("«lascia com'era»: si torna allo sviluppo con il lavoro di prima, i requisiti di "
             "prima, e la proposta scartata (sviluppo_modifica_lasciata)",
             sv.fase == "sviluppo" and sv.lavoro == lav.id and lav.stato == "in_corso"
             and [x["testo"] for x in sv.requisiti] == req_prima and not sv.ritorno
             and "u1" not in svc.offerte and "sviluppo_modifica_lasciata" in ctx.regole
             and "l'agente continua il lavoro di prima" in detta(r), detta(r))
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "indietro"}, 6, "Lascia com'era.")
    verifica("contrario: senza una modifica in attesa, «indietro» non tocca niente",
             sv.fase == "sviluppo" and "Non c'è una modifica da togliere" in detta(r), detta(r))

    # Il «sì» alla modifica: il lavoro di prima si ferma ADESSO, il nuovo parte dai suoi file
    cfg, reg, ctx, est, svc, sv, lav = gioco_al_lavoro(tmp / "a4b", [SV.MOD_MOSTRI])
    giro = cartella_giro(tmp / "a4b")
    lav.cartella = str(giro)
    SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i mostri "
              "danno punti"}, 3, "Anche i mostri danno punti.")
    nuovo = SV.ultimo(svc)
    verifica("alla prima versione (nessuna candidata) il lavoro nuovo ha già i file del giro in "
             "corso, e il vincolo lo dice", "estensione.py" in nuovo.file_iniziali
             and "lavoro.json" not in nuovo.file_iniziali and VINCOLO_GIRO in nuovo.vincoli,
             str(list(nuovo.file_iniziali)))
    SV.chiama(reg, ctx, "sviluppo_apri", {"proposta": nuovo.id}, 4, "Sì, va bene.")
    verifica("…il «sì»: il lavoro di prima si ferma ora, il nuovo parte (ritorno tolto)",
             lav.stato == "annullato" and svc.annullati == [lav.id] and nuovo.stato == "in_corso"
             and sv.lavoro == nuovo.id and not sv.ritorno and sv.fase == "sviluppo",
             f"{lav.stato} {nuovo.stato} {sv.ritorno}")

    # Il lavoro di prima finisce mentre la modifica aspetta: «lascia com'era» porta al collaudo
    cfg, reg, ctx, est, svc, sv, lav = gioco_al_lavoro(tmp / "a4c", [SV.MOD_MOSTRI])
    SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i mostri "
              "danno punti"}, 3, "Anche i mostri danno punti.")
    import prova_revisione_onesta as R
    n = R.candidata(est, lav.id)
    item = svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       test={"eseguiti": 3, "falliti": 0}, messaggio="ho finito.")
    verifica("il lavoro di prima finisce durante la modifica: la fase resta l'analisi, l'annuncio "
             "lo dice senza domande", sv.fase == "analisi" and sv.ritorno.get("fase") ==
             "collaudo" and sv.ritorno.get("versione") == n and "in_sospeso" not in item
             and "di prima della modifica è pronto" in item["messaggio"], item["messaggio"])
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "indietro"}, 5, "Lascia com'era.")
    verifica("…«lascia com'era»: al collaudo di quella versione", sv.fase == "collaudo"
             and sv.versione == n and not sv.ritorno and "di nuovo al collaudo" in detta(r)
             or (sv.fase == "collaudo" and "Lo apro in prova?" in detta(r)), detta(r))

    # Al collaudo di una versione consegnata: la modifica dice che la versione resta
    agente = SV.AgenteVivo(modifiche=[SV.MOD_MOSTRI])
    cfg, reg, ctx, est, svc, sv, out = SV.gioco(tmp / "a4d", agente)
    lav = SV.ultimo(svc)
    SV.chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id, "tappe": False}, 2, "Sì.")
    SV.consegna(svc, est, sv)
    versione = sv.versione
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i mostri "
                  "danno punti"}, 3, "Anche i mostri danno punti.")
    verifica("al collaudo: la modifica propone e dice che la versione provata resta",
             sv.fase == "analisi" and detta(r).startswith(f"La versione {versione} resta: se "
                                                           "lasci com'era, torniamo a provarla."),
             detta(r))
    r = SV.chiama(reg, ctx, "sviluppo_passo", {"azione": "ripristina"}, 4, "No, lasciala com'era.")
    verifica("…«lascia com'era» (anche come «ripristina»): di nuovo al collaudo della stessa "
             "versione", sv.fase == "collaudo" and sv.versione == versione
             and "sviluppo_modifica_lasciata" in ctx.regole, detta(r))


# ═══════════════════════════ 3. A5: tappe, arresti, «rifallo» ═══════════════════════════

def prova_a5(tmp, iso):
    print("— 3. A5: una tappa che aspetta, la sospensione, «rifallo» dai file del giro")
    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "a5", iso)
    giro = cartella_giro(tmp / "a5")
    svc.continua_chiesti = []

    def continua(l, nota=""):
        svc.continua_chiesti.append(l.id)
        l.stato = "in_coda"
        return "Continuo con un altro giro."
    svc.continua = continua
    item = svc.finisci(lav, "in_attesa", esito="tappa", cartella=str(giro),
                       messaggio="il lavoro è arrivato al limite del giro.")
    verifica("una tappa: il giro con la sua cartella resta nello sviluppo",
             sv.giro.get("perche") == "tappa" and sv.giro.get("cartella") == str(giro)
             and (item.get("in_sospeso") or {}).get("argomenti") == {"azione": "avanti"})
    sv.ultimo = time.time() - 31 * 60
    verifica("dopo 30 minuti senza parlarne lo sviluppo si sospende (una tappa non blocca gli "
             "altri sviluppi)", svs.corrente("u1") is None and sv.stato == "sospesa")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "riprendi"}, 5, "Riprendiamo lo sviluppo.")
    verifica("…e si riprende con il lavoro: «fermo a una tappa e aspetta te. Continuo con un "
             "altro giro?»", sv.stato == "aperta" and detta(r).endswith(
                 "Il lavoro dell'agente è fermo a una tappa e aspetta te. Continuo con un altro "
                 "giro?") and (r.get("in_sospeso") or {}).get("argomenti") == {"azione": "avanti"},
             detta(r))
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, 6, "Sì, rifallo.")
    verifica("«rifallo» a una tappa è un altro giro dello stesso lavoro, non uno da zero",
             svc.continua_chiesti == [lav.id] and "sviluppo_tappa_continua" in ctx.regole,
             detta(r))

    # La tappa che aspetta troppo (2 ore): messa da parte, non «non è andato»
    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "a5b", iso)
    giro = cartella_giro(tmp / "a5b")
    svc.finisci(lav, "in_attesa", esito="tappa", cartella=str(giro), messaggio="limite.")
    item = svc.finisci(lav, "scaduto", esito="scaduto", tappa=True, cartella=str(giro),
                       messaggio="ho chiuso «x»: aspettava da troppo.")
    verifica("scaduta dopo due ore a una tappa: «messo da parte» con i file, niente domanda né "
             "«non è andato»", sv.nota == MESSO_DA_PARTE and "in_sospeso" not in item
             and "messo da parte" in item["messaggio"] and "non è andato" not in
             item["messaggio"] and sv.giro.get("cartella") == str(giro), item["messaggio"])
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "stato"}, 3, "A che punto siamo?")
    verifica("…lo stato lo dice con una domanda sola: «riparto da lì?»",
             detta(r).endswith("era fermo a una tappa e l'ho messo da parte: riparto da lì?")
             and "azione = rifai" in str((r.get("in_sospeso") or {}).get("argomenti")), detta(r))
    n = len(svc.lavori)
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, 4, "Sì, riparti da lì.")
    nuovo = svc.lavori[-1]
    verifica("…«sì»: un lavoro nuovo dai file del giro (non lavoro.json, non il runtime, non gli "
             "esempi), con il vincolo", len(svc.lavori) == n + 1 and nuovo.stato == "in_corso"
             and "estensione.py" in nuovo.file_iniziali and "test_estensione.py" in
             nuovo.file_iniziali and "lavoro.json" not in nuovo.file_iniziali
             and "esempi_veri/a.json" not in nuovo.file_iniziali and VINCOLO_GIRO in nuovo.vincoli
             and getattr(nuovo, "parti_da", None) is lav
             and "ripartendo da quello che aveva già scritto" in detta(r),
             f"{list(nuovo.file_iniziali)} {detta(r)}")

    # «Fermalo» e poi «rifallo»: dai file del giro fermato, anche dopo un riavvio
    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "a5c", iso)
    giro = cartella_giro(tmp / "a5c")
    lav.cartella = str(giro)
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, 3, "Fermo lo sviluppo.")
    verifica("«Fermo lo sviluppo» → ferma: il giro fermato resta con la sua cartella",
             lav.stato == "annullato" and sv.giro.get("perche") == "fermato"
             and sv.giro.get("cartella") == str(giro), detta(r))
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, 4, "Rifallo.")
    nuovo = svc.lavori[-1]
    verifica("«rifallo» dopo «fermalo»: riparte dai file del giro (prima da zero)",
             nuovo is not lav and "estensione.py" in nuovo.file_iniziali
             and getattr(nuovo, "parti_da", None) is lav, str(list(nuovo.file_iniziali)))
    # dopo un riavvio: il lavoro non c'è più in memoria, la cartella sì
    svc.finisci(nuovo, "errore", motivo="ho dovuto fermarlo: tetto delle passate",
                cartella=str(giro), messaggio="non sono riuscita.")
    svc.lavori.clear()
    from calliope.sviluppo import Sviluppi
    svs2 = Sviluppi(cfg, Path(svs.percorso).parent, svc)
    svc.sviluppi = svs2
    sv2 = svs2.corrente("u1")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, 5, "Rifallo.")
    nuovo2 = svc.lavori[-1] if svc.lavori else None
    verifica("…anche dopo un riavvio: dalla cartella del giro salvata nello sviluppo",
             sv2 is not None and nuovo2 is not None and "estensione.py" in nuovo2.file_iniziali
             and getattr(nuovo2, "parti_da", None) == str(giro), detta(r))

    # Il thread dei lavori rilegge i file quando il lavoro comincia
    vuota = tmp / "a5d" / "vuota"
    vuota.mkdir(parents=True)
    vecchio = SimpleNamespace(cartella=str(vuota), risultato={})
    lv = SimpleNamespace(id="L9", file_iniziali={"calliope_estensione.py": "rt"}, vincoli="v.",
                         parti_da=vecchio)
    finto = SimpleNamespace(log=lambda *a: None)
    srv.Lavori._file_del_giro(finto, lv, None)
    verifica("servizio: un giro senza file → niente cambia", lv.file_iniziali ==
             {"calliope_estensione.py": "rt"} and lv.vincoli == "v." and lv.parti_da is None)
    lv.parti_da = vecchio
    (vuota / "gioco.js").write_text("// giro\n", encoding="utf-8")
    srv.Lavori._file_del_giro(finto, lv, None)
    verifica("servizio: i file arrivati dopo (il lavoro fermato al «sì») entrano quando il "
             "lavoro nuovo comincia, una volta, con il vincolo", lv.file_iniziali.get(
                 "gioco.js") == "// giro\n" and lv.file_iniziali["calliope_estensione.py"] == "rt"
             and lv.vincoli.count(VINCOLO_GIRO) == 1)
    lv.parti_da = vecchio
    srv.Lavori._file_del_giro(finto, lv, None)
    verifica("…riletto due volte, il vincolo resta uno", lv.vincoli.count(VINCOLO_GIRO) == 1)
    lv.parti_da = vecchio
    lv.file_iniziali = {}
    srv.Lavori._file_del_giro(finto, lv, "sandbox di prima")
    verifica("contrario: un lavoro ripreso con la sua sandbox non rilegge", lv.file_iniziali == {})
    verifica("file_del_giro: solo i file dell'agente", sorted(file_del_giro(
        cartella_giro(tmp / "a5e"))) == ["estensione.py", "test_estensione.py"])

    # La scadenza nel servizio vero: una tappa è segnata come tale
    t = srv.Lavori.__new__(srv.Lavori)
    chiusi = []
    lav_t = SimpleNamespace(id="L1", stato="in_attesa", attesa_dal=time.time() - 3 * 3600,
                            risultato={"esito": "tappa"}, fine=None, passo="")
    lav_d = SimpleNamespace(id="L2", stato="in_attesa", attesa_dal=time.time() - 3 * 3600,
                            risultato={"esito": "domanda"}, fine=None, passo="")
    t.cfg, t._lock, t.lavori, t.log = SimpleNamespace(agenti_attesa_risposta_min=120.0), \
        threading.RLock(), [lav_t, lav_d], (lambda *a: None)
    t._chiudi_attesa = lambda lv, ris: chiusi.append((lv.id, ris))
    t._annuncia = lambda lv: None
    t._salva_stato = lambda: None
    t._scadenze()
    verifica("servizio: alla scadenza una tappa porta «tappa», una domanda no",
             dict(chiusi).get("L1", {}).get("tappa") is True
             and "tappa" not in dict(chiusi).get("L2", {}), str(chiusi))


# ═══════════════════════════ 4. ripresa più corta ═══════════════════════════

def prova_ripresa(tmp, iso):
    print("— 4. ripresa più corta: una domanda sola, e il «sì» fa ripartire")
    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "rip", iso,
                                                                titolo="Meteo città")
    lav.cartella = str(cartella_giro(tmp / "rip"))
    turno(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, 2, "Fermo lo sviluppo.")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "riprendi", "quale": "meteo città"}, 3,
              "Riprendiamo lo sviluppo di meteo città.")
    f = detta(r)
    verifica("09/10 20:41: «Riprendiamo lo sviluppo di…» con lo sviluppo già aperto: non «è già "
             "aperto», ma dove siamo e una domanda sola su cosa farà",
             "è già aperto" not in f and f.count("?") == 1 and f.endswith(
                 "Il lavoro dell'agente l'hai fermato tu: lo rifaccio ripartendo da quello che "
                 "aveva già scritto?") and "sviluppo_ripreso_aperto" in ctx.regole
             and "(2 di 5)" not in f, f)
    n = len(svc.lavori)
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, 4, "Sì, rifallo.",
              sospeso="sviluppo_passo")
    verifica("…«Sì, rifallo»: il lavoro riparte subito, senza «Ho capito così… va bene così?» "
             "(2 turni: erano 4–5)", len(svc.lavori) == n + 1 and svc.lavori[-1].stato ==
             "in_corso" and "Ho capito così" not in detta(r) and "?" not in detta(r), detta(r))
    turno(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, 5, "Fermalo.")
    n = len(svc.lavori)
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, 6, "Niente, vai avanti così.")
    verifica("«avanti» con il lavoro fermo: lo rifà (prima un'altra domanda)",
             len(svc.lavori) == n + 1 and "sviluppo_avanti_rifai" in ctx.regole, detta(r))
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "riprendi"}, 7, "Riprendiamo lo sviluppo.")
    verifica("contrario: con l'agente al lavoro la ripresa dice che lavora, senza domande",
             "L'agente ci sta lavorando" in detta(r) and "?" not in detta(r), detta(r))


# ═══════════════════════════ 5. M7: il programma chiuso si riapre ═══════════════════════════

def prova_m7(tmp, iso):
    print("— 5. M7: un programma consegnato tiene i requisiti e si riapre")
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "m7", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", "somma due numeri", titolo="programma somma")
    sv.requisiti = [{"testo": "somma due numeri", "nucleo": True, "si_puo": True, "tappa": 0}]
    cartella = tmp / "m7" / "ris"
    cartella.mkdir(parents=True)
    (cartella / "somma.py").write_text("print(3 + 5)\n", encoding="utf-8")
    sv.cartella = str(cartella)
    svs.passa(sv, "collaudo")
    contesto = svs._file_contesto(sv)
    contesto.parent.mkdir(parents=True, exist_ok=True)
    contesto.write_text("{}", encoding="utf-8")
    # Provato una volta (22/10, #223: senza nessuna prova la revisione chiede prima)
    sv.collaudi.append({"quando": time.time(), "dati": "3 e 5", "ok": True, "esito": "8"})
    turno(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, 2, "Va bene, andiamo avanti.")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, 3, "Sì.")
    verifica("«va bene così» alla revisione: chiuso, e la frase dice che si può riaprire",
             sv.stato == "chiusa" and sv.motivo == "consegnato" and "riaprirlo" in detta(r)
             and contesto.exists(), detta(r))
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "riprendi"}, 4, "Riprendiamo lo sviluppo.")
    verifica("contrario: «riprendiamo lo sviluppo» senza dire quale non riapre un programma "
             "chiuso", sv.stato == "chiusa" and "Non ho sviluppi sospesi" in detta(r), detta(r))
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "riapri", "quale": "somma"}, 5,
              "Riapri il programma della somma.")
    verifica("«riapri il programma della somma»: riaperto al collaudo, con la richiesta e i "
             "requisiti (sviluppo_riaperto)", sv.stato == "aperta" and sv.fase == "collaudo"
             and sv.requisiti and sv.requisiti[0]["testo"] == "somma due numeri"
             and sv.cartella == str(cartella) and "sviluppo_riaperto" in ctx.regole
             and detta(r).startswith("Riapro «programma somma»"), detta(r))
    # Chiuso con «chiudi» (uscita): non è un programma consegnato
    sv.chiusa = time.time()
    svs.chiudi(sv, "uscita")
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "riprendi", "quale": "somma"}, 6,
              "Riprendiamo la somma.")
    verifica("contrario: uno chiuso con «chiudi» resta chiuso", sv.stato == "chiusa"
             and not contesto.exists(), detta(r))


# ═══════════════════════════ 6. uscire con un lavoro in corso ═══════════════════════════

def prova_uscita(tmp, iso):
    print("— 6. uscire dalla modalità sviluppo con un lavoro in corso")
    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "esci", iso)
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "esci"}, 2, "Ok, chiudi allora.")
    verifica("08/10 11:19, «esci» con l'agente al lavoro: sospeso, non chiuso",
             sv.stato == "sospesa" and lav.stato == "in_corso", detta(r))
    n = S.candidata(est)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                messaggio="ho finito.")
    verifica("…il lavoro consegnato dopo riapre lo sviluppo al collaudo",
             sv.stato == "aperta" and sv.fase == "collaudo")
    r = turno(reg, ctx, "sviluppo_collauda", {"dati": "Valfiorita"}, 3, "Prova con Valfiorita.")
    verifica("…e si collauda (prima «Non c'è nessuno sviluppo aperto da provare»)",
             "Non c'è nessuno sviluppo aperto" not in detta(r) and len(sv.collaudi) == 1,
             detta(r))

    cfg, reg, ctx, est, svc, svs, sv, lav = sviluppo_al_lavoro(tmp / "esci2", iso)
    lav.stato = "in_attesa"
    lav.risultato = {"esito": "domanda"}
    r = turno(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, 2, "Chiudi lo sviluppo.")
    verifica("con il lavoro fermo a una domanda per la persona: chiudere lo sospende (prima "
             "chiedeva solo «Lo chiudo?» e il lavoro restava senza sviluppo)",
             sv.stato == "sospesa" and "invece di chiudere, sospendo" in detta(r), detta(r))


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-flusso-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    prova_chiudi_tutti(tmp0, iso)
    prova_storpiature(tmp0, iso)
    prova_ricominciamo(tmp0, iso)
    prova_estensioni(tmp0, iso)
    prova_a4(tmp0, iso)
    prova_a5(tmp0, iso)
    prova_ripresa(tmp0, iso)
    prova_m7(tmp0, iso)
    prova_uscita(tmp0, iso)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
