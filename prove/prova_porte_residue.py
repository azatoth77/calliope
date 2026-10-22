"""Le porte residue dell'harness dello sviluppo, a secco (22/10/2026, issue #223, epic #86; area
agenti-estensioni; analisi docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.1, n. 5, 10
e 7; con le due revisioni della PR #232). Nomi di fantasia («fiera di Borgo Alto»).

1. Ricollaudo pieno (n. 5, `sonde.va`): vuoto solo per struttura (risultati vuoti o «trovato»:
   false, senza nessuna frase) quando prima il caso dava un dato o un errore: non va, con il
   motivo e la via onesta (regola ricollaudo_esito_vuoto). Contrari: ogni frase, anche negativa
   («Non ho trovato la fiera», «Nessuna allerta…», «Non c'è traffico», «Non ho risultati…»), è
   un dato e va.
2. Revisione e attivazione senza nessuna prova (n. 10, `tools/sviluppo._porta_prove`): la
   ragione e «Vado avanti lo stesso?» in sospeso; il sì solo a quella domanda e per quella
   versione; anteprime e collaudi di un'altra versione, il collaudo del programma di prima, gli
   esempi eseguiti come chiave salvata nello sviluppo (anche dopo un riavvio, non il segno
   «provato» ereditato); `estensione_gestisci approva` passa dalla porta con lo sviluppo aperto,
   sospeso o chiuso con quella versione, dopo permesso e test.
3. Test cambiati (n. 7, `agenti/fotografia_test.py`): la fotografia parte dai test scritti
   dall'agente (o, in una correzione, da quelli della versione di prima), mai dai file di
   partenza del codice; i conti cambiati sono un fatto per l'agente e una riga neutra sulla
   scheda; a voce solo il fatto neutro su uno stesso test che diventa banale o riceve un salto
   vero. Contrari: tutte le riscritture oneste della seconda revisione.

    python prove\\prova_porte_residue.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

import prova_estensioni as P  # noqa: E402
import prova_strumenti_onesti as SO  # noqa: E402
import prova_sviluppo as PS  # noqa: E402
from calliope import sonde  # noqa: E402
from calliope.agenti import fotografia_test as ft  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def sezione(t):
    print(f"\n— {t}", flush=True)


# ═══════════════════════════ 1. ricollaudo pieno ═══════════════════════════

def caso(**extra):
    c = {"dati": "fiera di Borgo Alto", "ok": False, "tipo": "errore",
         "esito": "KeyError: 'eventi'", "argomenti": {"luogo": "Borgo Alto"}}
    c.update(extra)
    return c


def esito(ris):
    return {"ok": True, "risultato": ris, "traccia": []}


def prova_ricollaudo():
    sezione("1. ricollaudo: vuoto solo per struttura (seconda revisione della PR #232)")
    for nome, ris in [("risultati vuoti", {"eventi": []}),
                      ("«trovato»: false senza frase", {"trovato": False}),
                      ("tutti i campi vuoti", {"eventi": [], "luogo": ""})]:
        ok, motivo = sonde.va(caso(), esito(ris))
        verifica(f"prima un errore, adesso {nome}: non va, con il motivo",
                 ok is False and motivo == sonde.MOTIVO_VUOTO, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(tipo="risposta", ok=True, esito="Il 3 marzo.",
                               giudizio="la data è sbagliata"), esito({"eventi": []}))
    verifica("…anche dopo una risposta giudicata sbagliata",
             ok is False and motivo == sonde.MOTIVO_VUOTO, f"{ok} {motivo}")
    vecchio = caso()
    vecchio.pop("tipo")
    ok, motivo = sonde.va(vecchio, esito({"eventi": []}))
    verifica("…e con un collaudo di prima del 12/10 (senza tipo, fallito)",
             ok is False and motivo == sonde.MOTIVO_VUOTO, f"{ok} {motivo}")
    verifica("il motivo dice la via onesta (il dato che non esiste, detto)",
             "se il dato non esiste davvero, dillo in da_dire" in sonde.MOTIVO_VUOTO)
    for testo in ("Non ho trovato la fiera di Borgo Alto.",
                  "Nessuna allerta meteo per Borgo Alto.",
                  "Non c'è traffico sulla provinciale.",
                  "Nessun ritardo per il treno delle otto.",
                  "Non ci sono eventi questo weekend a Borgo Alto.",
                  "Non ho risultati per Borgo Alto.",
                  "Non ho trovato la fiera di sabato. Domenica c'è quella del tartufo."):
        ok, motivo = sonde.va(caso(), esito({"da_dire": testo}))
        verifica(f"contrario: «{testo}» dopo un errore è un dato", ok is True, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(), esito({"trovato": False,
                                         "da_dire": "Non risulta nessuna fiera a Borgo Alto."}))
    verifica("contrario: «trovato»: false con la frase detta va", ok is True, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(), esito("Nessuna fiera a Borgo Alto."))
    verifica("contrario: una stringa è una frase", ok is True, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(tipo="vuoto", ok=True), esito({"eventi": []}))
    verifica("contrario: prima già vuoto (non un dato né un errore): non è questa regola",
             motivo != sonde.MOTIVO_VUOTO, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(), {"ok": True, "risultato": {}, "traccia": []})
    verifica("invariato: nessun risultato resta «nessun risultato»",
             ok is False and motivo == "nessun risultato", motivo)
    from types import SimpleNamespace
    lav = SimpleNamespace(id="L5", segnali={})
    sonde.esito_caso(lav, caso(), esito({"eventi": []}))
    sonde.esito_caso(lav, caso(), esito({"da_dire": "Il 12 novembre, in piazza."}))
    verifica("la regola ricollaudo_esito_vuoto nel registro del lavoro, una volta",
             (lav.segnali.get("regole") or {}).get("ricollaudo_esito_vuoto") == 1,
             str(lav.segnali))


def al_collaudo(tmp, iso, esempi=None, test_passano=True, **risultato):
    cfg, reg, ctx, est, svc = PS.ambiente(tmp, iso)
    P.installa(est, PS.M1, PS.CODICE1)
    _, _, lav = PS.apri_e_avvia(ctx, est, svc)
    lav.accettazione = esempi if esempi is not None else {"stato": "non_fatta",
                                                         "perche": "tempo scaduto"}
    n = PS.candidata(est, test_passano=test_passano)
    item = svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       **risultato)
    sv = svc.sviluppi.corrente("u1")
    sv.annuncio = (item or {}).get("messaggio", "")
    ctx.regole = []
    return reg, ctx, est, svc, sv, lav


def si(ctx, testo="Sì, vai avanti."):
    ctx.tool_in_sospeso = "sviluppo_passo"
    ctx.user_text = testo


def niente(ctx):
    ctx.tool_in_sospeso = None
    ctx.user_text = ""


def prova_senza_prove(tmp: Path, iso):
    sezione("2. revisione e attivazione senza nessuna prova")
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "a", iso)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    f = PS.detta(out)
    sosp = out.get("in_sospeso") or {}
    verifica("senza collaudo e con gli esempi «non_fatta»: niente revisione, la ragione e la "
             "domanda", sv.fase == "collaudo" and f == (
                 "Non c'è nessuna prova: non l'hai provata e non ci sono esempi. Vado avanti "
                 "lo stesso?")
             and "sviluppo_senza_prove_chiesto" in ctx.regole
             # la domanda viene prima della revisione: la sua regola si conta una volta, al sì
             and "sviluppo_revisione_senza_collaudo" not in ctx.regole, f"{sv.fase} {f}")
    verifica("…la domanda in sospeso verso sviluppo_passo avanti",
             sosp.get("tool") == "sviluppo_passo" and sosp.get("argomenti") == {
                 "azione": "avanti"} and sosp.get("domanda") == "Vado avanti lo stesso?"
             and out.get("ok") is False, str(sosp))
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("il modello che richiama avanti senza il sì: di nuovo la domanda",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?")
             and "sviluppo_senza_prove_confermato" not in ctx.regole, PS.detta(out))
    si(ctx, "No, aspetta, prima la provo.")
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=7)
    verifica("un «no» alla domanda non è un sì", sv.fase == "collaudo"
             and PS.detta(out).endswith("Vado avanti lo stesso?"), PS.detta(out))
    si(ctx)
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=8)
    f = PS.detta(out)
    verifica("il sì alla domanda: la revisione, che lo dice (regola nel registro)",
             sv.fase == "revisione" and "Nessuna prova: hai scelto di andare avanti lo stesso."
             in f and "l'hai saltato" not in f and f.endswith("vuoi attivarla?")
             and "sviluppo_senza_prove_confermato" in ctx.regole
             and "Nessuna prova" in sv.revisione, f)
    niente(ctx)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=9)
    verifica("…poi l'attivazione parte (la frase di sfida), senza un'altra domanda",
             sv.fase == "attivazione" and "ripeti" in PS.detta(out), PS.detta(out))
    # Una versione nuova: il sì valeva per quella di prima
    sv.versione = (sv.versione or 0) + 1
    sv.fase = "revisione"
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=10)
    verifica("una versione nuova senza prove: l'attivazione chiede di nuovo",
             sv.fase == "revisione" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))

    # L'attivazione da sola (la revisione fatta prima, oggi o da una versione di ieri)
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "b", iso)
    sv.fase = "revisione"
    attiva_prima = est.archivio.voce("meteo_citta")["attiva"]
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("dalla revisione senza nessuna prova: l'attivazione non parte, la domanda",
             sv.fase == "revisione" and PS.detta(out).endswith("Vado avanti lo stesso?")
             and est.archivio.voce("meteo_citta")["attiva"] == attiva_prima, PS.detta(out))

    # Contrari
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "c", iso)
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("contrario: con un collaudo la revisione come prima",
             sv.fase == "revisione" and "Prova: una" in PS.detta(out)
             and "sviluppo_senza_prove_chiesto" not in ctx.regole, PS.detta(out))
    for nome, passano in (("verdi", True), ("rossi", False)):
        reg, ctx, est, svc, sv, lav = al_collaudo(
            tmp / f"es-{nome}", iso, {"stato": "pronta", "passano": passano, "rossi": []})
        out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
        verifica(f"contrario: con gli esempi eseguiti ({nome}) niente domanda",
                 sv.fase == "revisione" and "sviluppo_senza_prove_chiesto" not in ctx.regole
                 and "l'hai saltato" in PS.detta(out), PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "d", iso, test_passano=False)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("contrario: una versione che non si può approvare si rivede comunque",
             "non si può approvare" in PS.detta(out)
             and "sviluppo_senza_prove_chiesto" not in ctx.regole, PS.detta(out))

    # Un programma
    cfg, reg, ctx, est, svc = PS.ambiente(tmp / "programma", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", "somma", titolo="somma")
    cart = tmp / "programma" / "ris"
    cart.mkdir(parents=True)
    (cart / "somma.py").write_text("print(3 + 5)\n", encoding="utf-8")
    sv.cartella = str(cart)
    svs.passa(sv, "collaudo")
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=3)
    verifica("un programma senza prove: la stessa domanda, al maschile",
             sv.fase == "collaudo" and PS.detta(out).startswith(
                 "Non c'è nessuna prova: non l'hai provato e") , PS.detta(out))
    sv.collaudi.append({"quando": 1.0, "dati": "3 e 5", "ok": True, "esito": "stampa 8"})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=4)
    verifica("contrario: con un collaudo «Va bene così?»", sv.fase == "revisione"
             and PS.detta(out).endswith("Va bene così?"), PS.detta(out))
    svs.chiudi(sv, "consegnato")
    sv2 = svs.apri("u1", "Dario", "programma", "differenza", titolo="differenza")
    sv2.cartella = str(cart)
    svs.passa(sv2, "revisione")
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("un programma alla revisione senza prove: non si chiude, la domanda",
             sv2.stato == "aperta" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             f"{sv2.stato} {PS.detta(out)}")


# ═══════════════════════════ 3. test indeboliti ═══════════════════════════

PY = ("import unittest\nfrom programma import somma\n\n\nclass P(unittest.TestCase):\n"
      "    def test_somma(self):\n        self.assertEqual(somma(2, 3), 5)\n\n"
      "    def test_zero(self):\n        self.assertEqual(somma(0, 0), 0)\n")
JS = ('const test = require("node:test");\nconst assert = require("node:assert");\n'
      'test("somma", () => { assert.strictEqual(somma(2, 3), 5); });\n'
      'test("zero", () => { assert.strictEqual(somma(0, 0), 0); });\n')
GIUSTO = "def somma(a, b):\n    return a + b\n"


def prova_misura():
    sezione("3a. la misura dei test (senza eseguirli)")
    m = ft.misura("test_programma.py", PY)
    verifica("Python: due test, due asserzioni, nessun salto",
             {k: v for k, v in m.items() if k != "per_test"} == {
                 "test": 2, "nomi": ["P.test_somma", "P.test_zero"], "asserzioni": 2,
                 "banali": 0, "skip": 0}, str(m))
    casi = [
        ("assertEqual → assertTrue(True)",
         PY.replace("self.assertEqual(somma(2, 3), 5)", "self.assertTrue(True)"),
         "un'asserzione in meno"),
        ("assertEqual(1, 1)", PY.replace("somma(2, 3), 5", "1, 1"), "un'asserzione in meno"),
        ("assert True", PY.replace("self.assertEqual(somma(2, 3), 5)", "assert True"),
         "un'asserzione in meno"),
        ("skipTest", PY.replace("        self.assertEqual(somma(2, 3), 5)",
                                "        self.skipTest('dopo')\n"
                                "        self.assertEqual(somma(2, 3), 5)"),
         "un test saltato in più"),
        ("@unittest.skip", PY.replace("    def test_zero", "    @unittest.skip('x')\n"
                                                         "    def test_zero"),
         "un test saltato in più"),
        ("un test tolto", PY.split("\n    def test_zero")[0] + "\n",
         "un test in meno (P.test_zero)")]
    for nome, dopo, atteso in casi:
        n = ft.nota_scrittura("test_programma.py", PY, dopo)
        verifica(f"Python, {nome}: detto", atteso in n, n)
    for nome, dopo in [
            ("un test aggiunto", PY + "\n    def test_tre(self):\n"
                                      "        self.assertEqual(somma(1, 2), 3)\n"),
            ("un test rinominato", PY.replace("test_zero", "test_nulla")),
            ("le asserzioni spostate in un altro test",
             PY.replace("        self.assertEqual(somma(0, 0), 0)\n", "        pass\n")
             .replace("        self.assertEqual(somma(2, 3), 5)\n",
                      "        self.assertEqual(somma(2, 3), 5)\n"
                      "        self.assertEqual(somma(0, 0), 0)\n")),
            ("la sintassi rotta (non si misura)", PY + "\n    def (\n")]:
        verifica(f"contrario Python: {nome}: niente",
                 ft.nota_scrittura("test_programma.py", PY, dopo) == "",
                 ft.nota_scrittura("test_programma.py", PY, dopo))
    m = ft.misura("somma.test.js", JS)
    verifica("JavaScript: due test, due asserzioni",
             m["test"] == 2 and m["asserzioni"] == 2 and m["skip"] == 0, str(m))
    for nome, dopo, atteso in [
            ("assert.ok(true)", JS.replace("assert.strictEqual(somma(2, 3), 5)",
                                           "assert.ok(true)"), "un'asserzione in meno"),
            ("test.skip", JS.replace('test("zero"', 'test.skip("zero"'), "un test in meno"),
            ("{ skip: true }", JS.replace('test("zero", ', 'test("zero", { skip: true }, '),
             "un test saltato in più"),
            ("un test tolto", JS.split('test("zero"')[0], "un test in meno")]:
        n = ft.nota_scrittura("somma.test.js", JS, dopo)
        verifica(f"JavaScript, {nome}: detto", atteso in n, n)
    verifica("contrario JavaScript: un test rinominato: niente",
             ft.nota_scrittura("somma.test.js", JS, JS.replace('"zero"', '"nulla"')) == "")
    verifica("contrario: gli esempi di Calliope e i file che non sono test non si misurano",
             ft.misura("test_accettazione.py", PY) is None
             and ft.misura("accettazione.test.js", JS) is None
             and ft.misura("programma.py", PY) is None
             and ft.misura(".calliope/test_x.py", PY) is None)
    foto = {"test_programma.py": ft.misura("test_programma.py", PY)}
    cambi = ft.confronta(foto, {})
    verifica("il file di test tolto: detto con i suoi conti",
             cambi and cambi[0]["tolto"] and "non c'è più (aveva 2 test e 2 asserzioni)"
             in ft.fatto_per_agente(cambi), ft.fatto_per_agente(cambi))
    verifica("contrario: un file di test nuovo non è un cambio",
             ft.confronta(foto, {**foto, "test_altro.py": ft.misura("test_altro.py", PY)}) == [])
    ora = {"test_programma.py": ft.misura("test_programma.py", PY.replace(
        "self.assertEqual(somma(2, 3), 5)", "self.skipTest('x')"))}
    frase = ft.frase_voce(ft.segnali(foto, ora))
    verifica("a voce un fatto neutro sullo stesso test, senza nomi di file né accuse",
             frase == "Sui test dell'agente: il test «test_somma» adesso è saltato."
             and ".py" not in frase and "indebolit" not in frase, frase)
    banale = {"test_programma.py": ft.misura("test_programma.py", PY.replace(
        "self.assertEqual(somma(2, 3), 5)", "self.assertTrue(True)"))}
    verifica("…e su uno stesso test che non controlla niente",
             ft.segnali(foto, banale) == [{"test": "test_somma", "cosa": "banale"}],
             str(ft.segnali(foto, banale)))
    spostato = {"tests/test_altro.py": ft.misura("tests/test_altro.py", PY.replace(
        "self.assertEqual(somma(2, 3), 5)", "self.assertTrue(True)"))}
    verifica("…anche se il test è stato spostato in un altro file",
             ft.segnali(foto, spostato) == [{"test": "test_somma", "cosa": "banale"}],
             str(ft.segnali(foto, spostato)))


def prova_ciclo(tmp: Path):
    sezione("3b. nel ciclo dell'agente: la fotografia alla prima esecuzione")
    debole = PY.replace("self.assertEqual(somma(2, 3), 5)", "self.assertTrue(True)")
    lav, ris, log, cli, sb = SO.gira(tmp, "indebolito", [
        [SO.scrivi("programma.py", GIUSTO), SO.scrivi("test_programma.py", PY)],
        [SO.ESEGUI],
        [SO.modifica("test_programma.py", "self.assertEqual(somma(2, 3), 5)",
                     "self.assertTrue(True)")],
        [SO.ESEGUI],
        [SO.CONSEGNA]])
    mod = SO.risultati(lav, "modifica_file")
    es = SO.risultati(lav, "esegui_test")
    reg = SO.regole(lav)
    verifica("modifica_file su un test che perde un'asserzione: la nota nel risultato",
             mod and "un'asserzione in meno" in str(mod[-1].get("test_cambiato"))
             and reg.get("agente_test_cambiato_scritto") == 1, str(mod[-1:]))
    verifica("la prima esecuzione è la fotografia: niente fatto",
             len(es) == 2 and "test_cambiati" not in es[0], str(es[:1])[:300])
    verifica("la seconda esecuzione (verde): il fatto rispetto alla fotografia",
             len(es) == 2 and es[1].get("passano") is True
             and "test_programma.py: un'asserzione in meno" in str(es[1].get("test_cambiati"))
             and reg.get("agente_test_cambiati") == 1, str(es[-1:])[:400])
    verifica("alla consegna: nel rapporto, con i conti",
             ris.get("esito") == "fatto" and ris.get("test_cambiati")
             and ris["test_cambiati"][0]["asserzioni_meno"] == 1
             and ris.get("test_segnali") == [{"test": "test_somma", "cosa": "banale"}],
             str(ris)[:400])
    # scrivi_file che riscrive il test con uno skip, dopo la prima esecuzione
    lav, ris, log, cli, sb = SO.gira(tmp, "skip", [
        [SO.scrivi("programma.py", GIUSTO), SO.scrivi("test_programma.py", PY)],
        [SO.ESEGUI],
        [SO.scrivi("test_programma.py", PY.replace(
            "    def test_zero(self):\n",
            "    def test_zero(self):\n        self.skipTest('dopo')\n"))],
        [SO.ESEGUI],
        [SO.CONSEGNA]])
    scr = SO.risultati(lav, "scrivi_file")
    es = SO.risultati(lav, "esegui_test")
    verifica("scrivi_file con skipTest: la nota e il fatto all'esecuzione dopo",
             "un test saltato in più" in str(scr[-1].get("test_cambiato"))
             and "un test saltato in più" in str(es[-1].get("test_cambiati")),
             str(scr[-1:]) + str(es[-1:])[:300])
    # Contrari: un test rinominato e uno aggiunto, eseguiti
    lav, ris, log, cli, sb = SO.gira(tmp, "rinomina", [
        [SO.scrivi("programma.py", GIUSTO), SO.scrivi("test_programma.py", PY)],
        [SO.ESEGUI],
        [SO.modifica("test_programma.py", "test_zero", "test_nulla")],
        [SO.modifica("test_programma.py", "        self.assertEqual(somma(0, 0), 0)\n",
                     "        self.assertEqual(somma(0, 0), 0)\n\n"
                     "    def test_tre(self):\n        self.assertEqual(somma(1, 2), 3)\n")],
        [SO.scrivi("test_altro.py", PY.replace("class P", "class Q"))],
        [SO.ESEGUI],
        [SO.CONSEGNA]])
    reg = SO.regole(lav)
    es = SO.risultati(lav, "esegui_test")
    verifica("contrario: rinominato, aggiunto, un file nuovo: niente note né fatti",
             not any("test_cambiato" in r for r in SO.risultati(lav, "modifica_file")
                     + SO.risultati(lav, "scrivi_file"))
             and not any("test_cambiati" in r for r in es)
             and "agente_test_cambiati" not in reg and "test_cambiati" not in ris
             and ris.get("esito") == "fatto", str(es)[:300])
    # Una correzione: i test iniziali sono già nella fotografia
    from calliope.agenti.ciclo import Lavoro
    lav = Lavoro("corr", "codice", "una funzione che somma")
    lav.file_iniziali = {"programma.py": GIUSTO, "test_programma.py": PY}
    lav.correzione = True
    sb = SO.G.sandbox(tmp, "corr")
    sb.scrivi("programma.py", GIUSTO)
    sb.scrivi("test_programma.py", debole)
    lav, ris, log, cli, sb = SO.gira(tmp, "corr", [[SO.ESEGUI], [SO.CONSEGNA]], lav=lav, sb=sb)
    es = SO.risultati(lav, "esegui_test")
    verifica("una correzione: il test indebolito prima della prima esecuzione è detto (i file "
             "iniziali nella fotografia)",
             SO.regole(lav).get("agente_test_cambiati") == 1, str(SO.regole(lav)))
    lav = Lavoro("modifica", "codice", "togli le previsioni")
    lav.file_iniziali = {"programma.py": GIUSTO, "test_programma.py": PY}
    sb = SO.G.sandbox(tmp, "modifica")
    sb.scrivi("programma.py", GIUSTO)
    sb.scrivi("test_programma.py", PY.split("\n    def test_zero")[0] + "\n")
    lav, ris, log, cli, sb = SO.gira(tmp, "modifica", [[SO.ESEGUI], [SO.CONSEGNA]], lav=lav,
                                     sb=sb)
    verifica("contrario: una modifica chiesta (non una correzione) che toglie una funzione e i "
             "suoi test: i file iniziali non sono la fotografia, niente",
             not ris.get("test_cambiati") and not ris.get("test_segnali")
             and "agente_test_cambiati" not in SO.regole(lav), str(ris)[:300])


# ═══════════════════ dalla prima revisione della PR #232 ═══════════════════

def prova_si_sicuro(tmp: Path, iso):
    sezione("2b. il sì vale solo per «Vado avanti lo stesso?» (revisione della PR #232)")
    from calliope import politica
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "si", iso)
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    for domanda in ("Lo chiudo?", "Vuoi attivarla?"):
        ctx.tool_in_sospeso = "sviluppo_passo"
        ctx.politica = politica.Turno(testo="Sì.", in_sospeso="sviluppo_passo",
                                      domanda_sospeso=domanda)
        ctx.user_text = "Sì."
        out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
        verifica(f"un «sì» detto per «{domanda}» non è il sì senza prove",
                 sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?")
                 and "sviluppo_senza_prove_confermato" not in ctx.regole, PS.detta(out))
    ctx.tool_in_sospeso = None
    ctx.politica = politica.Turno(testo="Sì, attivala.")
    ctx.user_text = "Sì, attivala."
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=7)
    verifica("«Sì, attivala.» senza nessuna proposta in sospeso (dopo un riavvio): la domanda",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))
    ctx.tool_in_sospeso = "sviluppo_passo"
    ctx.politica = politica.Turno(testo="Sì, vai.", in_sospeso="sviluppo_passo",
                                  domanda_sospeso="Vado avanti lo stesso?")
    ctx.user_text = "Sì, vai."
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=8)
    verifica("contrario: il sì a «Vado avanti lo stesso?» con la politica del turno: avanti",
             sv.fase == "revisione" and "sviluppo_senza_prove_confermato" in ctx.regole,
             PS.detta(out))
    ctx.politica = None
    niente(ctx)


def prova_versioni(tmp: Path, iso):
    sezione("2c. le prove della versione di adesso (revisione della PR #232)")
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "ant", iso)
    sv.collaudi.append({"quando": 1.0, "dati": "", "ok": True, "esito": "visto",
                        "anteprima": True, "versione": (sv.versione or 1) - 1})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("un'anteprima della versione di prima non è una prova di questa",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "vecchio", iso)
    sv.collaudi.append({"quando": 1.0, "dati": "Bergamo", "ok": True, "esito": "sereno",
                        "versione": (sv.versione or 1) - 1})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("…né un collaudo della versione di prima",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "scritti", iso, {"stato": "pronta",
                                                                     "file": "x"})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("gli esempi scritti e non eseguiti: «gli esempi non sono stati eseguiti»",
             "non l'hai provata e gli esempi non sono stati eseguiti." in PS.detta(out),
             PS.detta(out))
    # Un programma corretto: i collaudi del lavoro di prima non valgono
    cfg, reg, ctx, est, svc = PS.ambiente(tmp / "prog", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", "somma", titolo="somma")
    cart = tmp / "prog" / "ris"
    cart.mkdir(parents=True)
    (cart / "somma.py").write_text("print(3 + 5)\n", encoding="utf-8")
    sv.cartella, sv.lavoro = str(cart), "L2"
    sv.collaudi.append({"quando": 1.0, "dati": "3 e 5", "ok": True, "esito": "8",
                        "versione": None, "lavoro": "L1"})
    svs.passa(sv, "collaudo")
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=3)
    verifica("un programma corretto: il collaudo del programma di prima non vale",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))
    sv.collaudi.append({"quando": 2.0, "dati": "3 e 5", "ok": True, "esito": "8",
                        "versione": None, "lavoro": "L2"})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=4)
    verifica("contrario: un collaudo del programma corretto vale", sv.fase == "revisione",
             PS.detta(out))
    sv3 = svs.apri("u2", "Ada", "programma", "x", titolo="x")
    sv3.lavoro = "L7"
    svs.collaudo(sv3, "1", True, "uno")
    verifica("il collaudo salvato dice il lavoro", sv3.collaudi[-1].get("lavoro") == "L7",
             str(sv3.collaudi[-1]))


def prova_approva(tmp: Path, iso):
    sezione("2d. estensione_gestisci approva dentro lo sviluppo (revisione della PR #232)")
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "approva", iso)
    prima = est.archivio.voce("meteo_citta")["attiva"]
    ctx.speaker_ctx.sfida_superata = True
    out = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "approva", "nome": "meteo_citta"},
                   turno=5)
    ctx.speaker_ctx.sfida_superata = False
    verifica("senza prove, anche con la frase di sfida superata: la domanda, non approvata",
             PS.detta(out).endswith("Vado avanti lo stesso?")
             and est.archivio.voce("meteo_citta")["attiva"] == prima
             and "sviluppo_senza_prove_chiesto" in ctx.regole, PS.detta(out))
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=6)
    out = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "approva", "nome": "meteo_citta"},
                   turno=7)
    verifica("contrario: con un collaudo, l'approvazione di sempre (la frase di sfida)",
             "ripeti" in PS.detta(out) and not PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))


SEGNALE = [{"test": "test_meteo", "cosa": "banale"}]
CALO = [{"file": "test_meteo.py", "tolto": False, "test_meno": 1, "asserzioni_meno": 3,
         "skip_piu": 0, "banali_piu": 0, "nomi": ["test_vento"]}]
FRASE = "Sui test dell'agente: il test «test_meteo» adesso non controlla niente."


def prova_voce(tmp: Path, iso):
    sezione("3c. a voce solo il fatto neutro, la scheda per i conti (seconda revisione)")
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "voce", iso, test_segnali=SEGNALE,
                                              test_cambiati=CALO)
    verifica("l'annuncio dello sviluppo dice il fatto neutro sullo stesso test, nessuna accusa",
             FRASE in sv.annuncio and "indebolit" not in sv.annuncio
             and "test in meno" not in sv.annuncio, sv.annuncio)
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("…e la revisione a voce", FRASE in PS.detta(out)
             and "Test cambiati" not in PS.detta(out), PS.detta(out))
    verifica("…mentre i conti cambiati sono una riga neutra sulla scheda",
             "Test cambiati rispetto alla prima esecuzione: test_meteo.py: un test in meno "
             "(test_vento), 3 asserzioni in meno" in sv.revisione, sv.revisione[-400:])
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "calo", iso, test_cambiati=CALO)
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("contrario: solo i conti cambiati (test tolti, asserzioni): niente a voce",
             "Sui test" not in sv.annuncio and "Sui test" not in PS.detta(out)
             and "test in meno" not in PS.detta(out) and "Test cambiati" in sv.revisione,
             sv.annuncio + " | " + PS.detta(out))
    from calliope.agenti import fotografia_test as F
    unite = F.avvisi_voce({"test_tolti": {"nomi": ["test_zero"], "meno": 1},
                           "test_segnali": SEGNALE})
    verifica("con i test tolti dall'ultima tappa (frase di prima): le due frasi, un solo "
             "«Attenzione»", unite.count("Attenzione") == 1 and FRASE in unite, unite)
    # L'annuncio dei lavori fuori da uno sviluppo (agenti/servizio.Lavori._annuncia)
    from calliope.agenti import Lavori, carica
    from calliope.agenti.ciclo import Lavoro
    from calliope.config import Config
    cfg = Config()
    for k in ("risultati", "sandbox", "modelli"):
        setattr(cfg, f"agenti_{k}", str(tmp / "lavori-annuncio" / k))
    cfg.agenti_sandbox_motore = "processo"
    cfg.agenti_url, cfg.agenti_modello = "http://127.0.0.1:9", "agente-finto"
    cfg.llm_native_url = "http://127.0.0.1:9"
    lavori = Lavori(cfg, carica(cfg), log=lambda *a: None)
    lavori.sviluppi = None
    lv = Lavoro("L9", "codice", "una funzione che somma")
    lv.stato = "fatto"
    lv.risultato = {"esito": "fatto", "riassunto": "Fatto.", "cartella": str(tmp),
                    "test_segnali": SEGNALE, "test_cambiati": CALO}
    lavori._annuncia(lv)
    item = lavori.done.get_nowait()
    verifica("l'annuncio di un lavoro (Lavori) dice il fatto neutro, non i conti",
             FRASE in item["messaggio"] and "test in meno" not in item["messaggio"],
             item["messaggio"])


def prova_misura_2():
    sezione("3d. riscritture oneste e salti veri (revisione della PR #232)")
    quattro = ("import unittest\nfrom m import f\n\n\nclass P(unittest.TestCase):\n"
               "    def test_f(self):\n"
               "        self.assertEqual(f(1), 1)\n        self.assertEqual(f(2), 4)\n"
               "        self.assertEqual(f(3), 9)\n        self.assertEqual(f(4), 16)\n")
    ciclo = ("import unittest\nfrom m import f\n\n\nclass P(unittest.TestCase):\n"
             "    def test_f(self):\n        for x, y in [(1, 1), (2, 4), (3, 9), (4, 16)]:\n"
             "            with self.subTest(x=x):\n                self.assertEqual(f(x), y)\n")
    tre = ("from m import f\n\n\ndef test_uno():\n    assert f(1) == 1\n\n\n"
           "def test_due():\n    assert f(2) == 4\n\n\ndef test_tre():\n    assert f(3) == 9\n")
    param = ("import pytest\nfrom m import f\n\n\n@pytest.mark.parametrize('x,y', "
             "[(1, 1), (2, 4), (3, 9)])\ndef test_f(x, y):\n    assert f(x) == y\n")
    for nome, prima, dopo in [("quattro assertEqual in un ciclo con subTest", quattro, ciclo),
                              ("tre test in un parametrize", tre, param)]:
        verifica(f"contrario: {nome}: niente", ft.nota_scrittura("test_m.py", prima, dopo) == "",
                 ft.nota_scrittura("test_m.py", prima, dopo))
    js = ('const test = require("node:test");\nconst assert = require("node:assert");\n'
          'test("lista", () => { assert.deepStrictEqual(aggiungi([], "pane"), ["pane"]); });\n')
    for nome, extra in [("un oggetto con «todo» di un'app di liste",
                         'test("todo", () => { assert.ok(aggiungi(l, { todo: "latte" })); });\n'),
                        ("«salta il turno» di un gioco",
                         'test("salta", () => { assert.ok(mossa(stato(), { skip: true })); });\n'),
                        ("un metodo skip del gioco",
                         'test("salta 2", () => { assert.ok(gioco.skip(1)); });\n')]:
        m = ft.misura("a.test.js", js + extra)
        verifica(f"contrario JavaScript: {nome}: nessun salto", m["skip"] == 0, str(m))
    for nome, dopo in [
            ("t.skip() nel test", js.replace("() => {", "(t) => { t.skip();")),
            ("{ todo: true } nelle opzioni", js.replace('test("lista", ', 'test("lista", '
                                                        '{ todo: true }, ')),
            ("describe.skip", js + 'describe.skip("tutto", () => {});\n')]:
        verifica(f"JavaScript, {nome}: un salto vero", ft.misura("a.test.js", dopo)["skip"] == 1,
                 str(ft.misura("a.test.js", dopo)))
    for nome, dopo in [
            ("return in testa (Python)", PY.replace(
                "    def test_somma(self):\n", "    def test_somma(self):\n        return\n")),
            ("if False (Python)", PY.replace("        self.assertEqual(somma(2, 3), 5)",
                                             "        if False:\n"
                                             "            self.assertEqual(somma(2, 3), 5)")),
            ("try che ingoia l'AssertionError", PY.replace(
                "        self.assertEqual(somma(2, 3), 5)",
                "        try:\n            self.assertEqual(somma(2, 3), 5)\n"
                "        except AssertionError:\n            pass")),
            ("True or …", PY.replace("self.assertEqual(somma(2, 3), 5)",
                                     "self.assertTrue(True or somma(2, 3) == 5)"))]:
        sig = ft.segnali({"t.py": ft.misura("test_programma.py", PY)},
                         {"t.py": ft.misura("test_programma.py", dopo)})
        verifica(f"{nome}: lo stesso test non controlla niente, un fatto a voce",
                 sig == [{"test": "test_somma", "cosa": "banale"}], str(sig))
    for nome, dopo in [
            ("return; in testa (JavaScript)", JS.replace('test("somma", () => { ',
                                                        'test("somma", () => { return; ')),
            ("if (false) (JavaScript)", JS.replace("assert.strictEqual(somma(2, 3), 5);",
                                                   "if (false) { assert.strictEqual(somma(2, 3)"
                                                   ", 5); }"))]:
        sig = ft.segnali({"t.js": ft.misura("a.test.js", JS)}, {"t.js": ft.misura("a.test.js", dopo)})
        verifica(f"{nome}: detto", sig == [{"test": "somma", "cosa": "banale"}], str(sig))
    # Le riscritture oneste della seconda revisione: mai a voce
    app = ("from app import a, b\n\n\ndef test_a():\n    assert a() == 1\n\n\n"
           "def test_b():\n    assert b() == 2\n")
    solo_a = "from app import a\n\n\ndef test_a():\n    assert a() == 1\n"
    solo_b = "from app import b\n\n\ndef test_b():\n    assert b() == 2\n"
    tre = ("import unittest\nfrom m import f\n\n\nclass P(unittest.TestCase):\n"
           "    def test_uno(self):\n        self.assertEqual(f(1), 1)\n\n"
           "    def test_due(self):\n        self.assertEqual(f(2), 4)\n\n"
           "    def test_tre(self):\n        self.assertEqual(f(3), 9)\n")
    uniti = ("import unittest\nfrom m import f\n\n\nclass P(unittest.TestCase):\n"
             "    def test_f(self):\n        for x, y in [(1, 1), (2, 4), (3, 9)]:\n"
             "            with self.subTest(x=x):\n                self.assertEqual(f(x), y)\n")
    js3 = ('const test = require("node:test");\nconst assert = require("node:assert");\n'
           'test("uno", () => { assert.equal(f(1), 1); });\n'
           'test("due", () => { assert.equal(f(2), 4); });\n'
           'test("tre", () => { assert.equal(f(3), 9); });\n')
    tabella = ('const test = require("node:test");\nconst assert = require("node:assert");\n'
               'for (const [x, y] of [[1, 1], [2, 4], [3, 9]]) {\n'
               '  test(`f(${x})`, () => { assert.equal(f(x), y); });\n}\n')
    seme = PY.replace("self.assertEqual(somma(2, 3), 5)",
                      "self.assertEqual(mescola(42), mescola(42))")
    promessa = JS.replace("assert.strictEqual(somma(2, 3), 5);",
                          "return carica().then((v) => assert.equal(v, 3));")
    partita = PY.replace("self.assertEqual(somma(2, 3), 5)",
                         "p = partita()\n        p.skip()\n        self.assertEqual(p.turno, 2)")
    turno = JS.replace("assert.strictEqual(somma(2, 3), 5);",
                       "const t = turno(); t.skip(); assert.equal(t.chi, 2);")
    for nome, prima, dopo in [
            ("un file diviso in due", {"test_app.py": app},
             {"test_app.py": solo_a, "test_media.py": solo_b}),
            ("un file spostato in tests/", {"test_app.py": app}, {"tests/test_app.py": app}),
            ("tre test Python uniti con un ciclo e subTest", {"test_m.py": tre},
             {"test_m.py": uniti}),
            ("tre test JavaScript in un ciclo su una tabella", {"m.test.js": js3},
             {"m.test.js": tabella}),
            ("un test di determinismo con lo stesso seme", {"test_programma.py": PY},
             {"test_programma.py": seme}),
            ("JavaScript, la promessa restituita", {"somma.test.js": JS},
             {"somma.test.js": promessa}),
            ("Python, p.skip() di una partita", {"test_programma.py": PY},
             {"test_programma.py": partita}),
            ("JavaScript, t.skip() di un turno (non il contesto del test)", {"somma.test.js": JS},
             {"somma.test.js": turno}),
            ("JavaScript, g.skip() di un gioco in un test col contesto t", {"somma.test.js": JS},
             {"somma.test.js": JS.replace(
                 'test("somma", () => { assert.strictEqual(somma(2, 3), 5);',
                 'test("somma", (t) => { const g = gioco(); g.skip(); '
                 'assert.strictEqual(somma(2, 3), 5);')}),
            ("una funzione tolta con i suoi test", {"test_programma.py": PY},
             {"test_programma.py": PY.split("\n    def test_zero")[0] + "\n"})]:
        foto = {k: ft.misura(k, v) for k, v in prima.items()}
        ora = {k: ft.misura(k, v) for k, v in dopo.items()}
        sig = ft.segnali(foto, ora)
        verifica(f"contrario: {nome}: niente a voce", sig == [] and ft.frase_voce(sig) == "",
                 f"{sig} {ft.confronta(foto, ora)}")
    verifica("…ma il file diviso resta un fatto per l'agente e una riga neutra sulla scheda",
             "Test cambiati rispetto alla prima esecuzione: test_app.py: un test in meno"
             in ft.riga_scheda(ft.confronta({"test_app.py": ft.misura("test_app.py", app)},
                                            {"test_app.py": ft.misura("test_app.py", solo_a)})))
    verifica("«//» dentro una stringa non taglia la riga",
             ft.misura("a.test.js", 'test("u", () => { assert.strictEqual(url("a//b"), 1); '
                                    'assert.ok(f(2)); });\n')["asserzioni"] == 2)
    verifica("i sottotest t.test(…) contano come test",
             ft.misura("a.test.js", 'test("p", async (t) => { await t.test("a", () => '
                                    '{ assert.ok(f(1)); }); });\n')["test"] == 2)
    prima = {"t.py": ft.misura("test_programma.py", PY)}
    ora = {"t.py": ft.misura("test_programma.py", PY.replace(
        "        self.assertEqual(somma(0, 0), 0)\n", "        pass\n"))}
    calo = ft.confronta(prima, ora)
    verifica("un'asserzione tolta: un fatto per l'agente, non a voce",
             calo and calo[0]["asserzioni_meno"] == 1 and ft.segnali(prima, ora) == []
             and "un'asserzione in meno" in ft.fatto_per_agente(calo), str(calo))
    verifica("JavaScript: { skip: false } non è un salto",
             ft.misura("a.test.js", JS.replace('test("zero", ', 'test("zero", { skip: false }, '))
             ["skip"] == 0)
    verifica("i file *.spec.js sono test", ft.e_file_di_test("src/somma.spec.js")
             and ft.misura("somma.spec.js", JS)["test"] == 2)
    verifica("t.assert.equal(…) di node:test conta come asserzione",
             ft.misura("a.test.js", 'test("x", (t) => { t.assert.equal(f(1), 1); });\n')
             ["asserzioni"] == 1)


def prova_ciclo_2(tmp: Path):
    sezione("3e. nel ciclo: l'esecuzione di un file solo, la tappa, la sola lettura")
    lav, ris, log, cli, sb = SO.gira(tmp, "parziale", [
        [SO.scrivi("programma.py", GIUSTO), SO.scrivi("test_programma.py", PY)],
        [{"name": "esegui_test", "arguments": {"percorso": "test_programma.py"}}],
        [SO.modifica("test_programma.py", "self.assertEqual(somma(2, 3), 5)",
                     "self.skipTest('dopo')")],
        [{"name": "esegui_test", "arguments": {"percorso": "test_programma.py"}}],
        [SO.CONSEGNA]])
    es = SO.risultati(lav, "esegui_test")
    verifica("chi lancia un file alla volta: la fotografia del file e il fatto dopo",
             len(es) == 2 and "test_cambiati" not in es[0]
             and "un test saltato in più" in str(es[1].get("test_cambiati"))
             and ris.get("test_segnali") == [{"test": "test_somma", "cosa": "saltato"}],
             str(es)[:300])
    lav, ris, log, cli, sb = SO.gira(tmp, "tappa", [
        [SO.scrivi("programma.py", GIUSTO), SO.scrivi("test_programma.py", PY)],
        [SO.ESEGUI],
        [SO.modifica("test_programma.py", "self.assertEqual(somma(2, 3), 5)",
                     "self.assertTrue(True)")],
        [SO.ESEGUI], [SO.ESEGUI], [SO.ESEGUI], [SO.ESEGUI]], max_passi=5, tappe=True)
    verifica("alla tappa: i test cambiati e il segnale nel rapporto",
             ris.get("esito") == "tappa" and ris.get("test_cambiati")
             and ris["test_cambiati"][0]["banali_piu"] == 1
             and ris.get("test_segnali") == [{"test": "test_somma", "cosa": "banale"}],
             str(ris)[:300])
    sb = SO.G.sandbox(tmp, "sola")
    sb.scrivi("test_calliope.py", PY)
    sb.scrivi("test_mio.py", PY)
    sb.sola_lettura.add("test_calliope.py")
    m = ft.misura_cartella(sb)
    verifica("i file in sola lettura (di Calliope) non si fotografano",
             "test_calliope.py" not in m and "test_mio.py" in m, str(list(m)))


# ═══════════════════ dalla seconda revisione della PR #232 ═══════════════════

def _approva(reg, ctx, turno, livello=None):
    ctx.speaker_ctx.sfida_superata = True
    try:
        return P.chiama(reg, ctx, "estensione_gestisci", {"azione": "approva",
                                                          "nome": "meteo_citta"},
                        livello=livello, turno=turno)
    finally:
        ctx.speaker_ctx.sfida_superata = False


def prova_porta_2(tmp: Path, iso):
    sezione("2e. la porta con lo sviluppo sospeso o chiuso, dopo permesso e test; gli esempi "
            "dopo un riavvio (seconda revisione della PR #232)")
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "sospeso", iso)
    prima = est.archivio.voce("meteo_citta")["attiva"]
    svc.sviluppi.sospendi(sv, "cambio di argomento")
    out = _approva(reg, ctx, 5)
    verifica("sviluppo sospeso senza prove: «Attiva…» non approva, chiede",
             sv.stato == "sospesa" and PS.detta(out).endswith("Vado avanti lo stesso?")
             and est.archivio.voce("meteo_citta")["attiva"] == prima
             and (out.get("in_sospeso") or {}).get("tool") == "estensione_gestisci",
             PS.detta(out))
    sv.versione = (sv.versione or 1) - 1
    out = _approva(reg, ctx, 6)
    verifica("…anche se la versione segnata nello sviluppo sospeso è un'altra (non è concluso)",
             PS.detta(out).endswith("Vado avanti lo stesso?")
             and est.archivio.voce("meteo_citta")["attiva"] == prima, PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "chiuso", iso)
    svc.sviluppi.chiudi(sv, "uscita")
    out = _approva(reg, ctx, 5)
    verifica("sviluppo chiuso con la versione da attivare: chiede",
             PS.detta(out).endswith("Vado avanti lo stesso?")
             and est.archivio.voce("meteo_citta")["attiva"] == prima, PS.detta(out))
    sv.versione = (sv.versione or 1) - 1
    out = _approva(reg, ctx, 6)
    verifica("contrario: chiuso con un'altra versione: l'approvazione di sempre",
             not PS.detta(out).endswith("Vado avanti lo stesso?")
             and est.archivio.voce("meteo_citta")["attiva"] != prima, PS.detta(out))
    # Q4: prima permesso e test, poi la porta
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "familiare", iso)
    dario = ctx.speaker_ctx
    ctx.speaker_ctx = P.speaker("Bianca", "familiare")
    out = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "approva",
                                                     "nome": "meteo_citta"}, turno=5)
    ctx.speaker_ctx = dario
    verifica("un familiare che non può approvare: il rifiuto, non la domanda (e niente segno "
             "sullo sviluppo di chi amministra)",
             not PS.detta(out).endswith("Vado avanti lo stesso?") and not sv.senza_prove,
             PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "rossi2", iso, test_passano=False)
    out = _approva(reg, ctx, 5)
    verifica("i test rossi: «non si può approvare», senza la domanda prima",
             "non si può approvare" in PS.detta(out)
             and not PS.detta(out).endswith("Vado avanti lo stesso?"), PS.detta(out))
    # Q3: gli esempi eseguiti come chiave della versione, anche dopo un riavvio
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "riavvio", iso,
                                              {"stato": "pronta", "passano": True})
    verifica("gli esempi eseguiti: la chiave della versione nello sviluppo",
             sv.esempi_eseguiti == f"{sv.versione}|{sv.lavoro or ''}", sv.esempi_eseguiti)
    svc.lavori.remove(lav)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("dopo un riavvio (il lavoro non è in memoria) gli esempi valgono ancora",
             sv.fase == "revisione", PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "ereditato", iso)
    sv.requisiti = [{"testo": "dice il meteo", "nucleo": True, "si_puo": True,
                     "provato": True}]
    svc.lavori.remove(lav)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    verifica("contrario: il segno «provato» di una versione di prima non è una prova",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))
    sv.esempi_eseguiti = f"{(sv.versione or 1) - 1}|{sv.lavoro or ''}"
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("contrario: gli esempi eseguiti di un'altra versione non valgono",
             sv.fase == "collaudo", PS.detta(out))
    # Mo: il sì vale per la domanda di questa versione
    from calliope import politica
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "chiesta", iso)
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    sv.versione = (sv.versione or 1) + 1
    ctx.tool_in_sospeso = "sviluppo_passo"
    ctx.politica = politica.Turno(testo="Sì, vai.", in_sospeso="sviluppo_passo",
                                  domanda_sospeso="Vado avanti lo stesso?")
    ctx.user_text = "Sì, vai."
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    ctx.politica = None
    niente(ctx)
    verifica("un sì alla domanda fatta per la versione di prima: di nuovo la domanda",
             sv.fase == "collaudo" and PS.detta(out).endswith("Vado avanti lo stesso?"),
             PS.detta(out))


def prova_partenza_gioco(tmp: Path):
    sezione("3f. i file di partenza messi dal codice non sono la fotografia")
    from calliope.agenti.ciclo import Lavoro
    esempio = ('const test = require("node:test");\nconst assert = require("node:assert");\n'
               'test("porta 1", () => { assert.equal(apri(1), 1); });\n'
               'test("porta 2", () => { assert.equal(apri(2), 2); });\n'
               'test("fine", () => { assert.equal(fine(), true); });\n')
    tris = ('const test = require("node:test");\nconst assert = require("node:assert");\n'
            'test("tris", () => { assert.equal(vince([1, 2, 3]), true); });\n')
    lav = Lavoro("gioco", "codice", "un tris")
    sb = SO.G.sandbox(tmp, "gioco")
    sb.scrivi("gioco.test.js", esempio)      # lo scheletro, messo dal codice
    lav, ris, log, cli, sb = SO.gira(tmp, "gioco", [
        [SO.ESEGUI],
        [SO.scrivi("gioco.test.js", tris)],
        [SO.ESEGUI],
        [SO.CONSEGNA]], lav=lav, sb=sb)
    es = SO.risultati(lav, "esegui_test")
    verifica("i test del gioco d'esempio sostituiti da quelli del tris: niente fatti, niente "
             "a voce", not any("test_cambiati" in r for r in es)
             and not ris.get("test_cambiati") and not ris.get("test_segnali"),
             str(ris)[:300])
    verifica("…la fotografia parte dal file scritto dall'agente",
             list((lav.segnali.get("foto_test") or {})) == ["gioco.test.js"]
             and (lav.segnali["foto_test"]["gioco.test.js"]["test"] == 1),
             str(lav.segnali.get("foto_test"))[:300])


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-porte-residue-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    try:
        prova_ricollaudo()
        prova_senza_prove(tmp / "senza_prove", iso)
        prova_si_sicuro(tmp / "si_sicuro", iso)
        prova_versioni(tmp / "versioni", iso)
        prova_approva(tmp / "approva", iso)
        prova_porta_2(tmp / "porta2", iso)
        prova_misura()
        prova_misura_2()
        prova_voce(tmp / "voce", iso)
        prova_ciclo(tmp / "ciclo")
        prova_ciclo_2(tmp / "ciclo2")
        prova_partenza_gioco(tmp / "partenza")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
