"""Prova a secco della guida dell'agente (11/10/2026, docs/aree/agenti-estensioni.md, «Dove e
perché, scheletri, spinta concreta»; caso vero: il gioco «Halloween - Apri le porte» sulla
DGX, 45 minuti a vuoto).

1. Ogni controllo dice dove e perché (calliope/agenti/diagnosi.py):
   - prova di fumo con un gestore che lancia: elemento toccato, file:riga dello script della
     scheda, la frase «un gestore di evento ha lanciato un'eccezione…», i tocchi prima;
     dichiarazioni doppie tra due script della scheda con le due righe (dal 14/10 i gestori
     dell'agente ci sono solo in una tela: logica.js e tela.js);
   - test JavaScript falliti con il file:riga del test;
   - test Python falliti: l'asserzione con i valori e file:riga (anche il file dell'estensione
     chiamato dal test), un import che si rompe, un programma che si ferma; C#: errore di
     compilazione ed eccezione con la riga;
   - il risultato di esegui_test con «fallimenti» prima dell'uscita, la consegna rifiutata, il
     registro del lavoro (esito breve), il diario estrattivo; i contrari (test che passano,
     programma che finisce bene);
   - l'estensione che si ferma nel contenitore dice il file e la riga (collaudo, ricollaudo);
   - il manifesto sbagliato dice il valore ricevuto.
2. Scheletri di partenza nel prompt (calliope/agenti/scheletri.py): gioco, estensione,
   programma Python e C#; quello del gioco passa la prova di fumo e i suoi test, quello
   Python e quello dell'estensione i loro; i contrari (niente gioco nel prompt
   dell'estensione, niente C# senza il C#).
3. Spinta concreta: dopo un giro a vuoto con un errore noto («l'ultimo errore è X in
   file:riga; leggi quel punto e correggi solo quello»), dopo tre riscritture intere di fila
   dello stesso file lungo; modifica_file e leggi_file con riga; il ciclo vero con un cliente
   finto.

    python prove/prova_agente_guida.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calliope.agenti import diagnosi  # noqa: E402
from calliope.agenti.sandbox import Isolamento, Sandbox  # noqa: E402
from calliope.config import Config  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
FINTO = [sys.executable, str(Path(__file__).with_name("docker_finto.py"))]
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def sandbox(tmp: Path, nome: str) -> Sandbox:
    os.environ["DOCKER_FINTO_IMMAGINI"] = "img-py,img-node"
    os.environ["DOCKER_FINTO_DIR"] = str(tmp / "docker")
    iso_py = Isolamento("docker", "finto", True, "", "img-py", FINTO)
    iso_js = Isolamento("docker", "finto", True, "", "img-node", FINTO)
    return Sandbox(tmp / nome, 30, 256, isolamento=iso_py, linguaggi={"javascript": iso_js})


def agente(cliente=None, log=None):
    from calliope.agenti.arbitro import Arbitro
    from calliope.agenti.ciclo import Agente
    cfg = Config()
    cfg.agenti_num_ctx = 32768
    imp = SimpleNamespace(modello="qwen-finto", modello_scrittore="qwen-finto", motore="openai")
    return Agente(cfg, imp, cliente or SimpleNamespace(chat=lambda body: {}), Arbitro(False, 0),
                  log=(log.append if log is not None else (lambda *_: None)))


# Il caso vero (11/10): logica.js alza l'errore con i campi vuoti, il gestore di «Inizia» in
# gioco.js non lo cattura. Il primo tocco va, l'errore arriva al terzo. Dal 14/10 il gioco si
# scrive con la macchina a stati e i gestori dell'agente ci sono solo in una TELA (la via libera):
# lo stesso caso con il pulsante «Apri» disegnato dalla tela in tela.js
LOGICA = """"use strict";
function creaStato(nomi) {
  if (!Array.isArray(nomi) || nomi.length < 1 || nomi.length > 4) {
    throw new Error("Devi inserire da 1 a 4 giocatori");
  }
  return { nomi, turno: 0 };
}
if (typeof module !== "undefined") module.exports = { creaStato };
"""
GIOCO = """"use strict";
let stato = null;
let tocchi = 0;
function avvia() {
  tocchi++;
  const nomi = tocchi < 3 ? ["Ottavio"] : [];
  stato = creaStato(nomi);
}
const GIOCO = {
  nuovaPartita() { return {}; },
  tela: {
    gioco(area) {
      const b = document.createElement("button");
      b.id = "apri";
      b.textContent = "Apri";
      b.addEventListener("click", () => avvia());
      area.appendChild(b);
    },
  },
};
"""
TEST_JS = """const { test } = require("node:test");
const assert = require("node:assert");
const { creaStato } = require("./logica.js");
test("uno stato", () => assert.strictEqual(creaStato(["Ottavio"]).turno, 0));
test("turno sbagliato", () => {
  assert.strictEqual(creaStato(["Ottavio", "Bea"]).turno, 1);
});
"""
MANIFESTO_GIOCO = {"nome": "porte_halloween", "titolo": "Apri le porte",
                   "cosa_fa": {"verbo": "propone", "oggetto": "un gioco di porte"},
                   "permessi": {}, "scheda": {"tipo": "gioco", "file": ["logica.js", "tela.js"],
                                              "giocatori": {"min": 1, "max": 1},
                                              "macchina": {"inizio": "gioco", "fasi": {
                                                  "gioco": {"pagina": "tela",
                                                            "verso": ["fine"]}}}}}


# ═══════════════════════════ 1. dove e perché ═══════════════════════════

def prova_fumo(tmp: Path):
    sezione("1a. prova di fumo: il gestore che lancia (il caso del 11/10)")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    sb = sandbox(tmp, "fumo")
    sb.scrivi("logica.js", LOGICA)
    sb.scrivi("tela.js", GIOCO)
    sb.scrivi("logica.test.js", TEST_JS.replace("turno, 1)", "turno, 0)"))
    sb.scrivi("manifesto.json", json.dumps(MANIFESTO_GIOCO))
    r = sb.test()
    u = r["uscita"]
    verifica("i test passano, la prova di fumo no", not r["passano"]
             and r["esito"]["falliti"] == 1 and "FALLITO prova di fumo" in u, str(r["esito"]))
    verifica("…dice l'elemento toccato (tag, id, testo)",
             '<button id="apri"> «Apri»' in u, u[-600:])
    verifica("…file e riga dello script della scheda, dalla logica al gestore",
             re.search(r"\[in logica\.js:4 \(creaStato\) ← tela\.js:7 \(avvia\)", u) is not None,
             u[-600:])
    verifica("…la frase esplicita sul gestore",
             "un gestore di evento ha lanciato un'eccezione: ogni gestore deve catturare gli "
             "errori della logica" in u.lower())
    verifica("…gli ultimi tocchi prima dell'errore", "Tocchi prima: " in u
             and "<button id=\"apri\">" in u.split("Tocchi prima: ", 1)[-1], u[-400:])
    verifica("…e come lavora la prova (calliope e il contenitore ci sono)",
             "l'oggetto calliope" in u and "<div id=\"gioco\">" in u)
    from calliope.agenti.ciclo import Lavoro
    ag = agente()
    lav = Lavoro("G1", "estensione", "il gioco delle porte")
    res = ag._strumento(lav, sb, "esegui_test", {})
    f = res.get("fallimenti") or ""
    verifica("esegui_test: «fallimenti» prima dell'uscita, con il punto e l'elemento",
             list(res).index("fallimenti") < list(res).index("uscita")
             and "prova di fumo del gioco" in f and "logica.js:4" in f
             and "<button id=\"apri\">" in f and len(f) <= diagnosi.MAX_TESTO, f)
    from calliope.agenti.avanzamento import esito_breve
    e = esito_breve("esegui_test", res)
    verifica("il registro del lavoro conserva l'errore, non solo «0 test su 1 passano»",
             "passano" in e and "Devi inserire da 1 a 4 giocatori" in e and "logica.js:4" in e, e)

    sezione("1b. dichiarazioni doppie tra logica.js e tela.js, test JS con la riga")
    sb.scrivi("tela.js", '"use strict";\n\nconst TIPI_SORPRESA = [];\n' + GIOCO.split("\n", 1)[1])
    sb.scrivi("logica.js", LOGICA.replace('"use strict";\n',
                                          '"use strict";\nconst TIPI_SORPRESA = [1];\n'))
    sb.scrivi("logica.test.js", TEST_JS)
    r = sb.test()
    u = r["uscita"]
    verifica("SyntaxError con le due righe delle dichiarazioni (Node dice solo la riga 1)",
             "Identifier 'TIPI_SORPRESA' has already been declared [in tela.js:3]" in u
             and "è dichiarato in logica.js:2 e tela.js:3" in u, u[-500:])
    verifica("il test JS fallito dice l'asserzione e la riga del test",
             re.search(r"FALLITO turno sbagliato: .*0 !== 1.*\[in logica\.test\.js:6\]", u, re.S)
             is not None, u[:400])
    fall = diagnosi.fallimenti(u)
    verifica("diagnosi: due fallimenti, ognuno con il suo punto",
             len(fall) == 2 and {f["dove"].split(" ")[0] for f in fall}
             == {"logica.test.js:6", "tela.js:3"}, str(fall))
    sb.scrivi("tela.js", GIOCO.replace("() => avvia()", "() => { try { avvia(); } catch (e) "
                                                        "{ area.append(e.message); } }"))
    sb.scrivi("logica.js", LOGICA)
    sb.scrivi("logica.test.js", TEST_JS.replace("turno, 1)", "turno, 0)"))
    r = sb.test()
    verifica("contrario: con il gestore che cattura, la prova di fumo passa",
             r["passano"] and "ok prova di fumo" in r["uscita"], r["uscita"][-300:])
    res = ag._strumento(lav, sb, "esegui_test", {})
    verifica("…e il risultato non ha «fallimenti»", "fallimenti" not in res, str(list(res)))


ESTENSIONE = """import json


def esegui(dati, calliope):
    gradi = json.loads(calliope.rete_leggi("https://api.esempio.it/x")["testo"])["gradi"]
    return {"da_dire": f"Ci sono {gradi + 1} gradi."}
"""
TEST_EST = """import json
import unittest
from calliope_estensione import CalliopeFinta
from estensione import esegui


class Prove(unittest.TestCase):
    def test_gradi(self):
        c = CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "tipo": "application/json",
                                                   "testo": json.dumps({"gradi": 18})}})
        self.assertEqual(esegui({}, c)["da_dire"], "Ci sono 18 gradi.")

    def test_pagina_vuota(self):
        c = CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "tipo": "application/json",
                                                   "testo": "{}"}})
        self.assertIn("gradi", esegui({}, c)["da_dire"])


def test_funzione():
    assert 1 + 1 == 3, "conto sbagliato"
"""


def prova_python(tmp: Path):
    sezione("1c. test Python: asserzione e riga, anche nel file dell'estensione")
    sb = sandbox(tmp, "py")
    shutil.copy(RADICE / "calliope" / "estensioni" / "_ospite.py",
                sb.root / "calliope_estensione.py")
    sb.scrivi("estensione.py", ESTENSIONE)
    sb.scrivi("test_estensione.py", TEST_EST)
    from calliope.agenti.ciclo import Lavoro, ultimo_errore
    ag = agente()
    lav = Lavoro("P1", "estensione", "il meteo")
    res = ag._strumento(lav, sb, "esegui_test", {})
    f = res.get("fallimenti") or ""
    verifica("tre fallimenti: l'asserzione con i valori e la riga del test",
             "test_gradi: AssertionError: 'Ci sono 19 gradi.' != 'Ci sono 18 gradi.'" in f
             and "(in test_estensione.py:11)" in f, f)
    verifica("…l'errore nel file dell'estensione con il test che lo chiama",
             "test_pagina_vuota: KeyError: 'gradi' (in estensione.py:5 ← test_estensione.py:16)"
             in f, f)
    verifica("…una funzione test_* in stile pytest con il messaggio",
             "test_estensione.py::test_funzione: AssertionError: conto sbagliato "
             "(in test_estensione.py:20)" in f, f)
    u = ultimo_errore(res)
    verifica("ultimo errore per la spinta: il primo con un punto preciso",
             u is not None and u["dove"].startswith(("test_estensione.py", "estensione.py")),
             str(u))
    from calliope.agenti.avanzamento import esito_breve
    e = esito_breve("esegui_test", res)
    verifica("registro: «0 test su 3 passano · test_gradi: AssertionError…»",
             e.startswith("0 test su 3 passano · ") and "AssertionError" in e, e)
    r = ag._test_falliti(lav, sb)
    verifica("consegna rifiutata con i fallimenti", r is not None and "AssertionError" in
             r.get("fallimenti", "") and esito_breve("consegna", r).startswith(
                 "consegna rifiutata: 0 test su 3 passano · "), json.dumps(r)[:300])
    # Il diario estrattivo tiene il primo fallimento
    from calliope.agenti.contesto_lavoro import estrattivo
    msgs = [{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "esegui_test", "arguments": {}}}]},
            {"role": "tool", "tool_name": "esegui_test", "content": json.dumps(res)}]
    d = estrattivo(msgs, None)
    verifica("il diario estrattivo tiene il primo fallimento",
             any("KeyError: 'gradi'" in x for x in d["fatto"]), str(d["fatto"]))

    sb.scrivi("test_rotto.py", "import inesistente_xyz\n")
    res = ag._strumento(lav, sb, "esegui_test", {"percorso": "test_rotto.py"})
    verifica("un import che si rompe: il modulo e la riga",
             "import di test_rotto.py: ModuleNotFoundError: No module named 'inesistente_xyz' "
             "(in test_rotto.py:1)" in (res.get("fallimenti") or ""), str(res.get("fallimenti")))
    (sb.root / "test_rotto.py").unlink()
    sb.scrivi("programma.py", "def media(x):\n    return sum(x) / len(x)\n\n\nprint(media([]))\n")
    res = ag._strumento(lav, sb, "esegui_python", {"percorso": "programma.py"})
    verifica("un programma che si ferma: l'eccezione e la riga",
             "ZeroDivisionError: division by zero (in programma.py:2)"
             in (res.get("fallimenti") or ""), str(res)[:400])
    sb.scrivi("programma.py", "print('ciao')\n")
    res = ag._strumento(lav, sb, "esegui_python", {"percorso": "programma.py"})
    verifica("contrario: un programma che finisce bene non ha «fallimenti»",
             "fallimenti" not in res, str(res))
    sb.scrivi("estensione.py", ESTENSIONE.replace("gradi + 1", "gradi")
              .replace('["gradi"]', '.get("gradi", "non so quanti")'))
    sb.scrivi("test_estensione.py", TEST_EST.split("\n\ndef test_funzione")[0] + "\n")
    res = ag._strumento(lav, sb, "esegui_test", {})
    verifica("contrario: i test che passano non hanno «fallimenti»",
             res.get("passano") and "fallimenti" not in res, str(res)[:300])


def prova_diagnosi_testi():
    sezione("1d. diagnosi: C#, test JS, lunghezze")
    u = ("Program.cs(12,5): error CS1002: ; expected\n— compilazione non riuscita —\n")
    f = diagnosi.fallimenti(u)
    verifica("C#: errore di compilazione con file e riga",
             f == [{"test": "compilazione", "errore": "CS1002: ; expected",
                    "dove": "Program.cs:12"}], str(f))
    u = ("Unhandled exception. System.DivideByZeroException: Attempted to divide by zero.\n"
         "   at Program.<<Main>$>g__Div|0_0(Int32 a, Int32 b) in /lavoro/Program.cs:line 2\n"
         "   at Program.<Main>$(String[] args) in /lavoro/Program.cs:line 4\n")
    f = diagnosi.fallimenti(u)
    verifica("C#: eccezione non gestita con la riga più interna",
             len(f) == 1 and f[0]["dove"] == "Program.cs:2"
             and "DivideByZeroException" in f[0]["errore"], str(f))
    tanti = "\n".join(f"FALLITO prova {i}: Expected values to be strictly equal: {i} !== 0 "
                      + "x" * 400 + f" [in a.test.js:{i}]" for i in range(10))
    t = diagnosi.da_uscita(tanti)
    verifica("lunghezze limitate: al più 4 fallimenti e il conto degli altri, testo corto",
             len(t) <= diagnosi.MAX_TESTO and "…e altri 6" not in t or t.count("\n") <= 4,
             f"{len(t)} {t[-80:]!r}")
    verifica("…il punto resta anche quando l'errore è tagliato",
             "(in a.test.js:0)" in diagnosi.riga(diagnosi.fallimenti(tanti)[0]))
    verifica("contrario: un'uscita senza errori → niente",
             diagnosi.fallimenti("ok uno\nok due\nESITO {}") == [])


def prova_ospite_e_manifesto(tmp: Path):
    sezione("1e. l'estensione che si ferma dice file e riga; il manifesto il valore")
    cart = tmp / "ospite"
    cart.mkdir(parents=True)
    (cart / "manifesto.json").write_text(json.dumps({"nome": "prova", "input": {}}),
                                         encoding="utf-8")
    (cart / "estensione.py").write_text("def esegui(dati, calliope):\n    x = {}\n"
                                        "    return {'da_dire': x['manca']}\n", encoding="utf-8")
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"arguments": {}}}) + "\n"
    env = dict(os.environ, TMPDIR=str(tmp / "ospite-tmp"))
    (tmp / "ospite-tmp").mkdir()
    p = subprocess.run([sys.executable, "-I", str(RADICE / "calliope" / "estensioni" /
                                                  "_ospite.py"), str(cart)],
                       input=msg, capture_output=True, text=True, timeout=30, env=env,
                       encoding="utf-8")
    righe = [json.loads(x) for x in p.stdout.splitlines() if x.strip().startswith("{")]
    ris = next((x.get("result") for x in righe if x.get("id") == 1), {}) or {}
    testo = " ".join(c.get("text", "") for c in ris.get("content") or [])
    verifica("errore dell'estensione con il file e la riga (collaudo e ricollaudo)",
             ris.get("isError") and testo == "KeyError: 'manca' (in estensione.py:3)",
             testo or p.stderr[-300:])
    from calliope.estensioni.manifesto import ManifestoNonValido, valida
    for d, atteso in (({"nome": "Meteo Domani"}, "«nome» \"Meteo Domani\" non va"),
                      ({"nome": "meteo", "titolo": "Meteo", "cosa_fa": {"verbo": "fa",
                                                                        "oggetto": "x"}},
                       "«cosa_fa.verbo» «fa» non va")):
        try:
            valida(d)
            m = ""
        except ManifestoNonValido as e:
            m = str(e)
        verifica(f"manifesto: {atteso}", atteso in m, m[:120])


# ═══════════════════════════ 2. scheletri ═══════════════════════════

def _estrai(testo: str, nomi: set) -> dict:
    out, cur = {}, None
    for r in testo.split("\n"):
        m = re.match(r"^([\w.]+\.(?:js|py|json))( —.*)?:$", r)
        if m and m.group(1) in nomi:
            cur = m.group(1)
            out[cur] = []
            continue
        if cur and r.startswith(("Ogni gestore", "Un test che", "Ciò che", "Una mossa",
                                 "Ogni fase")):
            cur = None
            continue
        if cur:
            out[cur].append(r)
    return {k: "\n".join(v) + "\n" for k, v in out.items()}


def prova_scheletri(tmp: Path):
    sezione("2. scheletri di partenza nel prompt")
    from calliope.agenti.ciclo import sistema_codice
    from calliope.agenti.scheletri import SCHELETRI
    from calliope.estensioni.prompt import sistema_estensione
    pg, pe = sistema_estensione(Config(), gioco=True), sistema_estensione(Config())
    pp, pc = sistema_codice(["python"]), sistema_codice(["python", "csharp"])
    verifica("gioco, estensione, programma Python e C# hanno il loro scheletro",
             SCHELETRI["gioco"] in pg and SCHELETRI["estensione"] in pe
             and SCHELETRI["python"] in pp and SCHELETRI["csharp"] in pc)
    verifica("contrari: niente gioco nel prompt dell'estensione, niente C# senza il C#",
             "LA PARTENZA (gioco)" not in pe and "(programma C#)" not in pp
             and "(estensione)" not in pg)
    # Dal 19/10 (#186) il gioco non ha più i file nel prompt: sono nella cartella, già verdi
    # (scheletri.prepara_gioco, prova_partenza_gioco); qui si dice solo cosa c'è (prima 3 347
    # caratteri, il tetto era 3 400)
    verifica("corti: al più 1 200 caratteri il gioco, 1 600 l'estensione, 600 i programmi",
             len(SCHELETRI["gioco"]) <= 1200 and len(SCHELETRI["estensione"]) <= 1600
             and len(SCHELETRI["python"]) <= 600 and len(SCHELETRI["csharp"]) <= 600,
             str({k: len(v) for k, v in SCHELETRI.items()}))
    from calliope.agenti.scheletri import file_gioco
    g = file_gioco(1, 4)
    # Dal 13/10 la macchina a stati di Calliope: la scheda con «macchina», logica.js con GIOCO
    # e niente gioco.js (niente DOM, niente gestori: il disegno è del motore)
    from calliope.estensioni import scheda as sch
    try:
        scheda_gioco = sch.normalizza(json.loads(g["manifesto.json"])["scheda"], {})
    except (ValueError, sch.SchedaNonValida) as e:
        scheda_gioco = None
        print("   ", e)
    verifica("gioco: i file di partenza con la macchina a stati valida, logica.js dichiara "
             "GIOCO, niente gioco.js", sorted(g) == ["gioco.test.js", "logica.js",
                                                    "logica.test.js", "manifesto.json"]
             and scheda_gioco is not None and scheda_gioco.get("macchina")
             and "const GIOCO" in g["logica.js"] and "gioco.js" not in scheda_gioco["file"]
             and "document" not in g["logica.js"], str(sorted(g)))
    if shutil.which("node"):
        sb = sandbox(tmp, "scheletro-gioco")
        for k, v in g.items():
            sb.scrivi(k, v)
        r = sb.test()
        verifica("…e passano i loro test (anche la partita, con apriGioco) e la prova di fumo "
                 "per fasi", r["passano"] and "ok prova di fumo" in r["uscita"]
                 and "ok una porta aperta: il testo, il punto e poi tocca all'altro"
                 in r["uscita"], r["uscita"][-300:])
        from calliope.estensioni.prompt import controlla_consegna
        # Dal 20/10 (revisione della PR #188) la partenza non cambiata non si consegna
        verifica("…e la consegna non la accetta: è un esempio da sostituire",
                 "gioco d'esempio" in str(controlla_consegna(sb)), str(controlla_consegna(sb)))
    else:
        print("SALTATA IN PARTE: node non c'è")
    sb = sandbox(tmp, "scheletro-est")
    from calliope.agenti.scheletri import TEST_ESTENSIONE, prepara_estensione
    # Dal 13/10 test_estensione.py di partenza è già nella cartella (prepara_estensione): lo
    # scheletro nel prompt mostra solo i casi da aggiungere nella classe Prove
    scritti = prepara_estensione(sb)
    verifica("estensione: nella cartella il runtime (sola lettura) e test_estensione.py di "
             "partenza", scritti == ["calliope_estensione.py", "test_estensione.py"]
             and "calliope_estensione.py" in sb.sola_lettura
             and "test_estensione.py" not in sb.sola_lettura, str(scritti))
    parti = _estrai(SCHELETRI["estensione"], {"estensione.py", "test_estensione.py"})
    sb.scrivi("estensione.py", parti["estensione.py"])
    sb.scrivi("test_estensione.py", TEST_ESTENSIONE + parti["test_estensione.py"])
    r = sb.test()
    verifica("estensione: i test di partenza con i casi dello scheletro passano", r["passano"]
             and r["esito"]["eseguiti"] == 3, str(r["esito"]) + r["uscita"][-400:])
    prova_test_di_partenza(tmp)
    sb = sandbox(tmp, "scheletro-py")
    for k, v in _estrai(SCHELETRI["python"], {"programma.py", "test_programma.py"}).items():
        sb.scrivi(k, v)
    r = sb.test()
    e = sb.esegui("programma.py", [])
    verifica("programma Python: i test passano e gira senza argomenti", r["passano"]
             and "8" in e["uscita"], e["uscita"][:100])


CONVERTITORE = '''METRI = {"metri": 1.0, "chilometri": 1000.0, "miglia": 1609.344}


def esegui(dati, calliope):
    da, a = str(dati.get("da") or "").lower(), str(dati.get("a") or "").lower()
    if da not in METRI or a not in METRI:
        return {"da_dire": "Non conosco questa unità.", "trovato": False}
    r = float(dati.get("valore") or 0) * METRI[da] / METRI[a]
    return {"da_dire": f"Sono {r:g} {a}.", "risultato": r}
'''


ROTTA_SENZA_INPUT = '''def esegui(dati, calliope):
    return {"da_dire": f"Sono {dati['valore'] * 2}."}
'''
FIRMA_SBAGLIATA = '''def esegui(dati):
    return {"da_dire": "ciao"}
'''


def prova_test_di_partenza(tmp: Path):
    """Il test di partenza così com'è (13/10): passa con un'estensione che risponde, non con
    una che si rompe senza input o ha la firma sbagliata; non sostituisce i test di una
    modifica; il servizio lo mette nella cartella di un'estensione, non di un gioco."""
    sezione("2b. test_estensione.py di partenza")
    from calliope.agenti.scheletri import prepara_estensione
    from calliope.agenti.servizio import Lavori
    sb = sandbox(tmp, "partenza-conv")
    prepara_estensione(sb)
    sb.scrivi("estensione.py", CONVERTITORE)
    r = sb.test()
    verifica("così com'è, nella sandbox: passa con un convertitore che risponde",
             r["passano"] and r["esito"]["eseguiti"] == 1, str(r["esito"]) + r["uscita"][-300:])
    sb.scrivi("estensione.py", ROTTA_SENZA_INPUT)
    r = sb.test()
    verifica("contrario: fallisce con un'estensione che si rompe senza input (KeyError)",
             not r["passano"] and "KeyError" in r["uscita"], r["uscita"][-300:])
    sb.scrivi("estensione.py", FIRMA_SBAGLIATA)
    r = sb.test()
    verifica("contrario: la firma sbagliata si vede subito nel test di partenza",
             not r["passano"] and "positional argument" in r["uscita"], r["uscita"][-300:])
    sb = sandbox(tmp, "partenza-modifica")
    sb.scrivi("test_meteo.py", "def test_x():" + chr(10) + "    assert True" + chr(10))
    scritti = prepara_estensione(sb, runtime="# runtime finto" + chr(10))
    verifica("contrario: una modifica con i suoi test non riceve test_estensione.py",
             scritti == ["calliope_estensione.py"]
             and not (sb.root / "test_estensione.py").exists(), str(scritti))
    trovati = {}
    for nome, gioco in (("E1", False), ("G1", True)):
        sb = sandbox(tmp, f"servizio-{nome}")
        # Come nel servizio: il contratto e il runtime già segnati in sola lettura (13/10: così
        # la prima versione non scriveva il runtime, preso nel --secco del banco)
        sb.sola_lettura |= {"CAPACITA.md", "calliope_estensione.py"}
        Lavori._prepara_cartella_estensione(SimpleNamespace(log=lambda *_: None),
                                            SimpleNamespace(id=nome, gioco=gioco), sb)
        trovati[nome] = sorted(f["percorso"] for f in sb.elenca())
    verifica("il servizio: un'estensione ha runtime e test di partenza, un gioco no",
             trovati["E1"] == ["calliope_estensione.py", "test_estensione.py"]
             and trovati["G1"] == [], str(trovati))


# ═══════════════════════════ 3. spinta concreta ═══════════════════════════

ERRORE = {"test": "prova di fumo del gioco", "errore": "tocco (click) su <button id=\"inizia\"> "
          "«Inizia»: Error: Devi inserire da 1 a 4 giocatori",
          "dove": "logica.js:4 (creaStato) ← gioco.js:412 (avvia)"}


def prova_spinte():
    sezione("3a. la spinta con l'ultimo errore")
    from calliope.agenti.ripetizioni import spinta, spinta_riscritture
    s = spinta("La soluzione più semplice è riscrivere tutto", ERRORE)
    verifica("dopo un giro a vuoto: l'ultimo errore, il punto, «correggi solo quello»",
             "stai ripetendo lo stesso ragionamento" in s and "l'ultimo errore è" in s.lower()
             and "Devi inserire da 1 a 4 giocatori" in s and "logica.js:4" in s
             and "leggi_file con percorso «logica.js» e riga 4" in s
             and "correggi solo quello con modifica_file" in s
             and "non riscrivere il file intero" in s, s)
    verifica("contrario: senza errore noto la spinta di prima",
             spinta("x") == spinta("x", None) and "chiama uno strumento" in spinta("x"))
    s = spinta_riscritture("gioco.js", 3, ERRORE)
    verifica("dopo tre riscritture: lo dice e porta al punto",
             "Hai riscritto gioco.js per intero 3 volte" in s and "logica.js:4" in s
             and "modifica_file" in s, s)


class _Copione:
    """Un cliente finto che recita le passate: ogni voce è una lista di chiamate o «ripete»
    (un ragionamento ripetuto, che il rilevatore ferma)."""

    PARAGRAFO = ("Il problema è che la prova di fumo non trova il contenitore del gioco nel "
                 "documento finto.\n")

    def __init__(self, passate):
        self.passate, self.corpi, self.url = list(passate), [], None

    def chat(self, body, su_pezzo=None, controlla=None, su_flusso=None):
        self.corpi.append(json.loads(json.dumps(body["messages"], default=str)))
        p = self.passate.pop(0) if self.passate else [
            {"name": "consegna", "arguments": {"riassunto": "Fatto.", "esito": "fatto"}}]
        out = {"content": "", "thinking": "", "tool_calls": [], "eval": 50, "prompt": 100,
               "s": 0}
        if p == "ripete":
            for _ in range(40):
                if controlla is not None:
                    controlla()
                if su_flusso is not None:
                    su_flusso("pensiero", self.PARAGRAFO)
            return out
        out["tool_calls"] = p
        return out


def prova_ciclo(tmp: Path):
    sezione("3b. il ciclo vero: riscritture intere di fila, giro a vuoto, modifica_file")
    from calliope.agenti.ciclo import Lavoro, RISCRITTURE_MAX
    lungo = "def somma(a, b):\n    return a - b\n" + "".join(f"# riga {i}\n" for i in range(70))
    test = ("import unittest\nfrom programma import somma\n\n\nclass P(unittest.TestCase):\n"
            "    def test_somma(self):\n        self.assertEqual(somma(2, 3), 5)\n")
    scrivi = {"name": "scrivi_file", "arguments": {"percorso": "programma.py", "contenuto": lungo}}
    passate = [[scrivi, {"name": "scrivi_file", "arguments": {"percorso": "test_programma.py",
                                                              "contenuto": test}}],
               [{"name": "esegui_test", "arguments": {}}]]
    passate += [[scrivi]] * RISCRITTURE_MAX
    passate += ["ripete",
                [{"name": "leggi_file", "arguments": {"percorso": "programma.py", "riga": 2}}],
                [{"name": "modifica_file", "arguments": {"percorso": "programma.py",
                                                         "vecchio": "a - a", "nuovo": "x"}}],
                [{"name": "modifica_file", "arguments": {"percorso": "programma.py",
                                                         "vecchio": "    return a - b",
                                                         "nuovo": "    return a + b"}}],
                [{"name": "esegui_test", "arguments": {}}],
                [{"name": "consegna", "arguments": {"riassunto": "Somma corretta.",
                                                    "esito": "fatto"}}]]
    cli = _Copione(passate)
    log = []
    ag = agente(cli, log)
    sb = sandbox(tmp, "ciclo")
    lav = Lavoro("C1", "codice", "una funzione che somma")
    eventi = []
    lav.osservatore = lambda lv, ev, dati: eventi.append((ev, dict(dati)))
    ris = ag.codice(lav, sb)
    msgs = lav.contesto.get("messages") or []
    utenti = [m["content"] for m in msgs if m.get("role") == "user"]
    rif = next((u for u in utenti if "Hai riscritto programma.py per intero" in u), "")
    verifica("dopo tre riscritture intere di fila con lo stesso errore: la spinta",
             f"per intero {RISCRITTURE_MAX} volte" in rif
             and "AssertionError: -1 != 5" in rif and "in test_programma.py:7" in rif
             and "leggi_file con percorso «test_programma.py» e riga 7" in rif, rif[:400])
    verifica("…la regola nel log, sulla scheda e contata nei segnali del lavoro (19/10, #9)",
             any("agente_riscrittura_ripetuta" in x for x in log)
             and any(ev == "spinta" and d.get("regola") == "agente_riscrittura_ripetuta"
                     for ev, d in eventi)
             and (lav.segnali.get("regole") or {}).get("agente_riscrittura_ripetuta", 0) >= 1,
             f"{log[-3:]} {lav.segnali.get('regole')}")
    rip = next((u for u in utenti if "stai ripetendo lo stesso ragionamento" in u), "")
    verifica("giro a vuoto con un errore noto: la spinta concreta",
             "AssertionError: -1 != 5" in rip and "non riscrivere il file intero" in rip,
             rip[:400])
    tool = [m for m in msgs if m.get("role") == "tool"]
    letto = next((json.loads(m["content"]) for m in tool
                  if m.get("tool_name") == "leggi_file"), {})
    verifica("leggi_file con riga: le righe intorno, numerate",
             letto.get("contenuto", "").startswith("1: def somma(a, b):")
             and "2:     return a - b" in letto.get("contenuto", ""), str(letto)[:200])
    mod = [json.loads(m["content"]) for m in tool if m.get("tool_name") == "modifica_file"]
    verifica("modifica_file: il testo che non c'è → errore chiaro; quello giusto → riga",
             len(mod) == 2 and mod[0].get("ok") is False and "non c'è" in mod[0]["errore"]
             and mod[1].get("ok") and mod[1].get("riga") == 2, str(mod))
    verifica("…e il lavoro finisce con i test che passano", ris.get("esito") == "fatto"
             and ris.get("test_passano") is True
             and "return a + b" in (sb.root / "programma.py").read_text(), str(ris)[:300])
    from calliope.agenti.avanzamento import esito_breve
    verifica("registro: «corretto alla riga 2»",
             esito_breve("modifica_file", mod[1]) == "corretto alla riga 2")
    sb.scrivi("doppio.py", "x = 1\nx = 1\n")
    r = ag._modifica(lav, sb, {"percorso": "doppio.py", "vecchio": "x = 1", "nuovo": "y"})
    verifica("modifica_file: un testo che compare due volte → chiede più righe intorno",
             r.get("ok") is False and "2 volte" in r["errore"], str(r))
    sb.sola_lettura |= {"doppio.py"}
    try:
        ag._modifica(lav, sb, {"percorso": "doppio.py", "vecchio": "x = 1\nx", "nuovo": "y"})
        verifica("modifica_file rispetta la sola lettura", False)
    except Exception as e:  # noqa: BLE001
        verifica("modifica_file rispetta la sola lettura", "sola lettura" in str(e), str(e))

    sezione("3c. contrari della fila: un file corto, un errore che cambia")
    corto = {"name": "scrivi_file", "arguments": {"percorso": "test_programma.py",
                                                  "contenuto": test}}
    # In fondo il programma giusto: dal 19/10 (#180) la consegna con i test rossi non chiude
    # più il lavoro «fatto», e il copione finito consegna
    giusto = {"name": "scrivi_file", "arguments": {"percorso": "programma.py",
                                                   "contenuto": "def somma(a, b):\n"
                                                                "    return a + b\n"}}
    cli = _Copione([[corto], [{"name": "esegui_test", "arguments": {}}]] + [[corto]] * 4
                   + [[giusto]])
    ag = agente(cli, [])
    sb = sandbox(tmp, "ciclo2")
    sb.scrivi("programma.py", "def somma(a, b):\n    return a - b\n")
    lav = Lavoro("C2", "codice", "x")
    ag.codice(lav, sb)
    utenti = [m["content"] for m in lav.contesto["messages"] if m.get("role") == "user"]
    verifica("un file corto riscritto più volte: nessuna spinta",
             not any("Hai riscritto" in u for u in utenti))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-guida-"))
    try:
        prova_fumo(radice / "fumo")
        prova_python(radice / "python")
        prova_diagnosi_testi()
        prova_ospite_e_manifesto(radice / "ospite")
        prova_scheletri(radice / "scheletri")
        prova_spinte()
        prova_ciclo(radice / "ciclo")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
