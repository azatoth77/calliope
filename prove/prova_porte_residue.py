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

def al_collaudo(tmp, iso, esempi=None, test_passano=True):
    cfg, reg, ctx, est, svc = PS.ambiente(tmp, iso)
    P.installa(est, PS.M1, PS.CODICE1)
    _, _, lav = PS.apri_e_avvia(ctx, est, svc)
    lav.accettazione = esempi if esempi is not None else {"stato": "non_fatta",
                                                         "perche": "tempo scaduto"}
    n = PS.candidata(est, test_passano=test_passano)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})
    sv = svc.sviluppi.corrente("u1")
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
                 "Non c'è nessuna prova: non l'hai provata e gli esempi non sono stati "
                 "eseguiti. Vado avanti lo stesso?")
             and "sviluppo_senza_prove_chiesto" in ctx.regole, f"{sv.fase} {f}")
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
                   "skip": 0}, str(m))
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
             frase == "Attenzione: dalla prima prova l'agente ha indebolito i suoi test: un "
                      "controllo in meno e un test saltato." and ".py" not in frase, frase)


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
        prova_misura()
        prova_ciclo(tmp / "ciclo")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
