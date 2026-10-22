"""Le porte residue dell'harness dello sviluppo, a secco (22/10/2026, issue #223, epic #86; area
agenti-estensioni; analisi docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.1, n. 5, 10
e 7). Nomi di fantasia («fiera di Borgo Alto», «Pratofiorito Maggiore»).

1. Ricollaudo pieno (n. 5, `sonde.va`): il caso della persona che prima si fermava con un errore
   e adesso risponde «Non ho trovato…» non va (motivo detto, regola ricollaudo_esito_vuoto); così
   anche risultati vuoti e «trovato»: false. Contrari: un esito pieno va; «Non ho trovato
   pioggia» con i dati accanto va; una risposta giudicata sbagliata dalla persona che adesso dice
   «non trovato» va (può essere proprio la correzione).
2. Revisione e attivazione senza nessuna prova (n. 10, `tools/sviluppo._porta_prove`): senza
   collaudo e con gli esempi non eseguiti (analisi «non_fatta») «avanti» non va alla revisione:
   la ragione detta e la domanda in sospeso verso sviluppo_passo avanti
   (sviluppo_senza_prove_chiesto); il modello che richiama avanti senza il sì, o un «no», non
   bastano; il sì alla domanda sì (sviluppo_senza_prove_confermato) e la revisione lo dice; poi
   l'attivazione parte; una versione nuova chiede di nuovo; l'attivazione da sola si ferma come
   la revisione; un programma come un'estensione. Contrari: con un collaudo, con gli esempi
   eseguiti (verdi o rossi), una versione che non si può approvare (si rivede comunque).
3. Test indeboliti (n. 7, `agenti/fotografia_test.py`): la misura (test, asserzioni vere,
   salti) per Python e JavaScript; assertEqual → assertTrue(True), skipTest, @unittest.skip, un
   test tolto, il file tolto, test.skip e assert.ok(true) in JavaScript: detti. Nel ciclo
   dell'agente finto: la nota nel risultato di modifica_file e scrivi_file
   (agente_test_indebolito_scritto), il fatto nel risultato di esegui_test rispetto alla
   fotografia della prima esecuzione (agente_test_indeboliti), il rapporto della consegna e la
   frase a voce senza nomi di file; i file iniziali di una correzione nella fotografia.
   Contrari: un test aggiunto, un test rinominato o spostato con le stesse asserzioni, un file di
   test nuovo, gli esempi di Calliope in sola lettura: niente.

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
    sezione("1. ricollaudo: un esito vuoto non è una risposta")
    ok, motivo = sonde.va(caso(), esito({"da_dire": "Non ho trovato la fiera di Borgo Alto."}))
    verifica("prima un errore, adesso «Non ho trovato…»: non va, con il motivo",
             ok is False and motivo == sonde.MOTIVO_VUOTO and "chiedeva un dato" in motivo,
             f"{ok} {motivo}")
    for nome, ris in [("risultati vuoti", {"eventi": []}),
                      ("«trovato»: false", {"trovato": False, "da_dire": "Niente."}),
                      ("«nessun risultato» per il luogo",
                       {"da_dire": "Nessun risultato per Borgo Alto."})]:
        ok, motivo = sonde.va(caso(), esito(ris))
        verifica(f"…anche {nome}", ok is False and motivo == sonde.MOTIVO_VUOTO,
                 f"{ok} {motivo}")
    vecchio = caso()
    vecchio.pop("tipo")
    ok, motivo = sonde.va(vecchio, esito({"da_dire": "Non ho trovato la fiera di Borgo Alto."}))
    verifica("…anche con un collaudo di prima del 12/10 (senza tipo, fallito)",
             ok is False and motivo == sonde.MOTIVO_VUOTO, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(tipo="vuoto", ok=True, giudizio="non la trova"),
                          esito({"da_dire": "Non ho trovato la fiera di Borgo Alto."}))
    verifica("…e un «non trovato» giudicato sbagliato che resta «non trovato»",
             ok is False and motivo == sonde.MOTIVO_VUOTO, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(), esito({"da_dire": "La fiera di Borgo Alto è il 12 novembre, "
                                                    "in piazza."}))
    verifica("contrario: un esito pieno va", ok is True and motivo == "", f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(dati="Pratofiorito Maggiore",
                               argomenti={"citta": "Pratofiorito Maggiore"}),
                          esito({"da_dire": "Non ho trovato pioggia: sereno.",
                                 "temperatura": 21, "cielo": "sereno"}))
    verifica("contrario: «Non ho trovato pioggia» con i dati accanto va", ok is True,
             f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(tipo="risposta", ok=True, esito="Il 3 marzo.",
                               giudizio="quella fiera non esiste, deve dirlo"),
                          esito({"da_dire": "Non ho trovato la fiera di Borgo Alto."}))
    verifica("contrario: una risposta giudicata sbagliata che adesso dice «non trovato» va",
             ok is True, f"{ok} {motivo}")
    ok, motivo = sonde.va(caso(), {"ok": True, "risultato": {}, "traccia": []})
    verifica("invariato: nessun risultato resta «nessun risultato»",
             ok is False and motivo == "nessun risultato", motivo)


# ═══════════════════════════ 2. revisione senza prove ═══════════════════════════

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
             m == {"test": 2, "nomi": ["P.test_somma", "P.test_zero"], "asserzioni": 2,
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
    frase = ft.frase_voce(ft.confronta(foto, {"test_programma.py": ft.misura(
        "test_programma.py", PY.replace("self.assertEqual(somma(2, 3), 5)",
                                        "self.skipTest('x')"))}))
    verifica("la frase a voce: i conti, senza nomi di file",
             frase == "Attenzione: da quando ha eseguito i test la prima volta, l'agente li ha "
                      "indeboliti: un test saltato." and ".py" not in frase, frase)


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
             mod and "un'asserzione in meno" in str(mod[-1].get("test_indebolito"))
             and reg.get("agente_test_indebolito_scritto") == 1, str(mod[-1:]))
    verifica("la prima esecuzione è la fotografia: niente fatto",
             len(es) == 2 and "test_indeboliti" not in es[0], str(es[:1])[:300])
    verifica("la seconda esecuzione (verde): il fatto rispetto alla fotografia",
             len(es) == 2 and es[1].get("passano") is True
             and "test_programma.py: un'asserzione in meno" in str(es[1].get("test_indeboliti"))
             and reg.get("agente_test_indeboliti") == 1, str(es[-1:])[:400])
    verifica("alla consegna: nel rapporto, con i conti",
             ris.get("esito") == "fatto" and ris.get("test_indeboliti")
             and ris["test_indeboliti"][0]["asserzioni_meno"] == 1, str(ris)[:400])
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
             "un test saltato in più" in str(scr[-1].get("test_indebolito"))
             and "un test saltato in più" in str(es[-1].get("test_indeboliti")),
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
             not any("test_indebolito" in r for r in SO.risultati(lav, "modifica_file")
                     + SO.risultati(lav, "scrivi_file"))
             and not any("test_indeboliti" in r for r in es)
             and "agente_test_indeboliti" not in reg and "test_indeboliti" not in ris
             and ris.get("esito") == "fatto", str(es)[:300])
    # Una correzione: i test iniziali sono già nella fotografia
    from calliope.agenti.ciclo import Lavoro
    lav = Lavoro("corr", "codice", "una funzione che somma")
    lav.file_iniziali = {"programma.py": GIUSTO, "test_programma.py": PY}
    sb = SO.G.sandbox(tmp, "corr")
    sb.scrivi("programma.py", GIUSTO)
    sb.scrivi("test_programma.py", debole)
    lav, ris, log, cli, sb = SO.gira(tmp, "corr", [[SO.ESEGUI], [SO.CONSEGNA]], lav=lav, sb=sb)
    es = SO.risultati(lav, "esegui_test")
    verifica("una correzione: il test indebolito prima della prima esecuzione è detto (i file "
             "iniziali nella fotografia)",
             es and "un'asserzione in meno" in str(es[0].get("test_indeboliti")), str(es)[:300])


# ═══════════════════ dalla prima revisione della PR #232 ═══════════════════

def prova_ricollaudo_2():
    sezione("1b. ricollaudo: le frasi vuote e quelle con un dato (revisione della PR #232)")
    for testo in ("Non trovo nessun luogo chiamato Borgo Alto.",
                  "Mi dispiace, nessuna fiera a Borgo Alto.",
                  "Nessun evento trovato a Borgo Alto.",
                  "Purtroppo non sono riuscita a trovare la fiera."):
        ok, motivo = sonde.va(caso(), esito({"da_dire": testo}))
        verifica(f"«{testo}» dopo un errore: vuoto", ok is False and motivo == sonde.MOTIVO_VUOTO,
                 f"{ok} {motivo}")
    verifica("…e il motivo dice la via onesta (il dato che non esiste, nel riassunto)",
             "se il dato non esiste davvero, dillo nel riassunto" in sonde.MOTIVO_VUOTO)
    for testo in ("Non ho trovato pioggia: sereno, 21 gradi.",
                  "Nessuna pioggia, cielo sereno su Borgo Alto.",
                  "La fiera di Borgo Alto è il 12 novembre."):
        ok, motivo = sonde.va(caso(), esito({"da_dire": testo}))
        verifica(f"contrario: «{testo}» (solo da_dire) è pieno", ok is True, f"{ok} {motivo}")
    from types import SimpleNamespace
    lav = SimpleNamespace(id="L5", segnali={})
    sonde.esito_caso(lav, caso(), esito({"da_dire": "Non ho trovato la fiera."}))
    sonde.esito_caso(lav, caso(), esito({"da_dire": "Il 12 novembre, in piazza."}))
    verifica("la regola ricollaudo_esito_vuoto nel registro del lavoro, una volta",
             (lav.segnali.get("regole") or {}).get("ricollaudo_esito_vuoto") == 1,
             str(lav.segnali))


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


DEBOLE = [{"file": "test_meteo.py", "tolto": False, "test_meno": 0, "asserzioni_meno": 0,
           "skip_piu": 0, "banali_piu": 1, "nomi": []}]
CALO = [{"file": "test_meteo.py", "tolto": False, "test_meno": 0, "asserzioni_meno": 3,
         "skip_piu": 0, "banali_piu": 0, "nomi": []}]
FRASE = "Attenzione: da quando ha eseguito i test la prima volta, l'agente li ha indeboliti"


def prova_voce(tmp: Path, iso):
    sezione("3c. i test indeboliti a voce: annuncio, revisione, rapporto (revisione della PR #232)")
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "voce", iso, test_indeboliti=DEBOLE)
    verifica("l'annuncio dello sviluppo lo dice (una asserzione che non controlla niente)",
             FRASE + ": un controllo che non controlla niente." in sv.annuncio, sv.annuncio)
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("…e la revisione", FRASE in PS.detta(out), PS.detta(out))
    reg, ctx, est, svc, sv, lav = al_collaudo(tmp / "calo", iso, test_indeboliti=CALO)
    verifica("contrario: le asserzioni calate (un ciclo, un parametrize) non vanno a voce",
             "indebolit" not in sv.annuncio, sv.annuncio)
    from calliope.agenti import fotografia_test as F
    unite = F.avvisi_voce({"test_tolti": {"nomi": ["test_zero"], "meno": 1},
                           "test_indeboliti": [{**DEBOLE[0], "test_meno": 1, "skip_piu": 1}]})
    verifica("con i test tolti dall'ultima tappa: un solo «Attenzione», il test non contato due "
             "volte", unite.count("Attenzione") == 1 and "In più, da quando ha eseguito i test "
             "la prima volta: un test saltato e un controllo che non controlla niente." in unite
             and "test tolto" not in unite.split("In più")[1], unite)
    verifica("niente «dalla prima prova» (si confonde con il collaudo)",
             "prima prova" not in F.frase_voce(DEBOLE))
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
                    "test_indeboliti": DEBOLE}
    lavori._annuncia(lv)
    item = lavori.done.get_nowait()
    verifica("l'annuncio di un lavoro (Lavori) lo dice", FRASE in item["messaggio"],
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
                                     "self.assertTrue(True or somma(2, 3) == 5)")),
            ("lo stesso valore ai due lati", PY.replace("self.assertEqual(somma(2, 3), 5)",
                                                        "self.assertEqual(somma(2, 3), "
                                                        "somma(2, 3))"))]:
        cambi = ft.confronta({"t.py": ft.misura("test_programma.py", PY)},
                             {"t.py": ft.misura("test_programma.py", dopo)})
        verifica(f"{nome}: un controllo che non controlla niente, detto a voce",
                 "un controllo che non controlla niente" in ft.frase_voce(cambi), str(cambi))
    for nome, dopo in [
            ("return in testa (JavaScript)", JS.replace('test("somma", () => { ',
                                                       'test("somma", () => { return; ')),
            ("if (false) (JavaScript)", JS.replace("assert.strictEqual(somma(2, 3), 5);",
                                                   "if (false) { assert.strictEqual(somma(2, 3)"
                                                   ", 5); }"))]:
        cambi = ft.confronta({"t.js": ft.misura("a.test.js", JS)},
                             {"t.js": ft.misura("a.test.js", dopo)})
        verifica(f"{nome}: detto", "un controllo che non controlla niente"
                 in ft.frase_voce(cambi), str(cambi))
    verifica("«//» dentro una stringa non taglia la riga",
             ft.misura("a.test.js", 'test("u", () => { assert.strictEqual(url("a//b"), 1); '
                                    'assert.ok(f(2)); });\n')["asserzioni"] == 2)
    verifica("i sottotest t.test(…) contano come test",
             ft.misura("a.test.js", 'test("p", async (t) => { await t.test("a", () => '
                                    '{ assert.ok(f(1)); }); });\n')["test"] == 2)
    calo = ft.confronta({"t.py": ft.misura("test_programma.py", PY)},
                        {"t.py": ft.misura("test_programma.py", PY.replace(
                            "        self.assertEqual(somma(0, 0), 0)\n", "        pass\n"))})
    verifica("un'asserzione tolta: un fatto per l'agente, non a voce",
             calo and calo[0]["asserzioni_meno"] == 1 and ft.frase_voce(calo) == ""
             and "un'asserzione in meno" in ft.fatto_per_agente(calo), str(calo))


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
             len(es) == 2 and "test_indeboliti" not in es[0]
             and "un test saltato in più" in str(es[1].get("test_indeboliti"))
             and ris.get("test_indeboliti"), str(es)[:300])
    lav, ris, log, cli, sb = SO.gira(tmp, "tappa", [
        [SO.scrivi("programma.py", GIUSTO), SO.scrivi("test_programma.py", PY)],
        [SO.ESEGUI],
        [SO.modifica("test_programma.py", "self.assertEqual(somma(2, 3), 5)",
                     "self.assertTrue(True)")],
        [SO.ESEGUI], [SO.ESEGUI], [SO.ESEGUI], [SO.ESEGUI]], max_passi=5, tappe=True)
    verifica("alla tappa: i test indeboliti nel rapporto",
             ris.get("esito") == "tappa" and ris.get("test_indeboliti")
             and ris["test_indeboliti"][0]["banali_piu"] == 1, str(ris)[:300])
    sb = SO.G.sandbox(tmp, "sola")
    sb.scrivi("test_calliope.py", PY)
    sb.scrivi("test_mio.py", PY)
    sb.sola_lettura.add("test_calliope.py")
    m = ft.misura_cartella(sb)
    verifica("i file in sola lettura (di Calliope) non si fotografano",
             "test_calliope.py" not in m and "test_mio.py" in m, str(list(m)))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-porte-residue-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    try:
        prova_ricollaudo()
        prova_ricollaudo_2()
        prova_senza_prove(tmp / "senza_prove", iso)
        prova_si_sicuro(tmp / "si_sicuro", iso)
        prova_versioni(tmp / "versioni", iso)
        prova_approva(tmp / "approva", iso)
        prova_misura()
        prova_misura_2()
        prova_voce(tmp / "voce", iso)
        prova_ciclo(tmp / "ciclo")
        prova_ciclo_2(tmp / "ciclo2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
