"""
Lo scheletro di partenza per tipo di lavoro, in fondo al prompt dell'agente (11/10/2026,
docs/aree/agenti-estensioni.md, «Scheletri di partenza»).

Caso vero della DGX (11/10): per il gioco «Halloween - Apri le porte» qwen3.6 ha dichiarato
le stesse costanti in logica.js e in gioco.js (che nel riquadro stanno nello stesso spazio
globale: «Identifier 'TIPI_SORPRESA' has already been declared»), poi ha lasciato uscire
un'eccezione dal gestore del pulsante «Inizia» e ha riscritto gioco.js intero nove volte, con
ipotesi sbagliate sulla prova di fumo («calliope non è definito», «il contenitore non è nel
DOM»). Le regole c'erano già, sparse nel prompt e nel contratto; lo scheletro le mostra nella
forma del codice, che il modello copia.

Sono corti apposta: stanno nel prompt di sistema, quindi in ogni passata. Misura (11/10, con
il tokenizer di Qwen3.6 sulla DGX): gioco 591 token (il prompt del gioco arriva a 5 522),
estensione 476 (prompt 4 562), programma Python 190, C# 168. Dall'11/10 sera il gioco mostra
anche i comandi a voce (`ascolta` e `quandoComando`, docs/aree/giochi.md): 231 caratteri, circa
67 token in più (stima con il rapporto caratteri/token della misura sopra, 3,47; quella esatta
si rifà sulla DGX), e la riga del contratto sui comandi a voce circa 177.

Dal 12/10 sera (flusso dell'agente a fasi, parte 1) il gioco ha anche `gioco.test.js`, un test
del disegno con `apriGioco` (agenti/fumo_js.mjs): il difetto vero del 12/10 (l'esito annidato
letto al primo livello, sempre «Nessun punto!») stava lì, e i test della logica erano verdi.
Circa 650 caratteri in più, ~190 token con lo stesso rapporto (da rimisurare sulla DGX).
"""

GIOCO = """SCHELETRO DI PARTENZA (gioco): parti da qui e cambia solo quello che serve.
logica.js — regole pure, niente DOM:
"use strict";
function nuovaPartita(nGiocatori) {
  if (!(nGiocatori >= 1 && nGiocatori <= 4)) throw new Error("da 1 a 4 giocatori");
  return { turno: 0, punti: new Array(nGiocatori).fill(0), finita: false };
}
function mossa(stato, scelta) { return { ...stato, turno: stato.turno + 1 }; }
if (typeof module !== "undefined") module.exports = { nuovaPartita, mossa };
gioco.js — stesso spazio globale di logica.js: usa nuovaPartita e mossa direttamente e NON \
ridichiarare nomi che logica.js ha già (né const né function); niente require:
"use strict";
const radice = document.getElementById("gioco");
let partita = null;
function sicuro(f) {
  return (ev) => { try { f(ev); } catch (e) { avviso(e.message); } };
}
function avviso(testo) { const p = document.createElement("p"); p.textContent = testo; \
radice.appendChild(p); }
function disegna() {
  radice.replaceChildren();
  const b = document.createElement("button");
  b.textContent = partita ? "Mossa" : "Inizia";
  b.addEventListener("click", sicuro(() => {
    partita = partita ? mossa(partita, 0) : nuovaPartita(1);
    disegna();
  }));
  radice.appendChild(b);
}
calliope.quandoPronto(() => disegna());
// A voce, se la richiesta lo chiede: nella scheda "ascolta": {"comandi": {"mossa": \
["mossa", "vai"]}}
calliope.quandoComando(sicuro((m) => {
  if (m.comando === "mossa" && partita) { partita = mossa(partita, 0); disegna(); }
}));
logica.test.js:
const { test } = require("node:test");
const assert = require("node:assert");
const { nuovaPartita } = require("./logica.js");
test("partita nuova", () => assert.strictEqual(nuovaPartita(2).punti.length, 2));
gioco.test.js — il gioco vero nel DOM finto; apriGioco e creaCaso ci sono già, senza require:
const { test } = require("node:test");
const assert = require("node:assert");
test("si tocca Inizia e compare la mossa", async () => {
  const g = await apriGioco({ giocatori: 1, seme: 1 });
  await g.tocca("Inizia");
  assert.match(g.testo(), /Mossa/);
});
Ciò che la persona deve VEDERE (punti, esito, vincitore) si prova in gioco.test.js: tocca \
come lei (g.tocca("testo o #id"), g.comando("nome"), g.avanza(ms)) e leggi g.testo(). Il \
caso con un seme: apriGioco({ seme }) e, nei test della logica, creaCaso(seme) passato alla \
funzione al posto di Math.random.
Ogni gestore di evento passa da sicuro(): un errore della logica (un dato mancante, una \
scelta non valida) si mostra nel gioco e non esce dal gestore. La prova di fumo di \
esegui_test carica logica.js e gioco.js come nel riquadro (document finto con <div \
id="gioco">, l'oggetto calliope, timer finti), chiama quandoPronto e tocca a caso ogni \
elemento con un gestore, anche con i campi vuoti: un'eccezione che esce da un gestore la fa \
fallire, e il messaggio dice file:riga, l'elemento toccato e i tocchi prima. Correggi quel \
punto con modifica_file."""

ESTENSIONE = """SCHELETRO DI PARTENZA (estensione): parti da qui e cambia solo quello che serve.
estensione.py:
import json
import urllib.parse
from calliope_estensione import ErroreCalliope

def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    if not citta:
        return {"da_dire": "Mi serve il nome della città.", "trovato": False}
    url = "https://api.esempio.it/cerca?" + urllib.parse.urlencode({"q": citta})
    try:
        r = calliope.rete_leggi(url)
    except ErroreCalliope as e:
        return {"da_dire": f"Non riesco a leggere il servizio: {e}."}
    dati_sito = json.loads(r["testo"])
    if not dati_sito.get("risultati"):
        return {"da_dire": f"Non ho trovato {citta}.", "trovato": False}
    return {"da_dire": f"A {citta} ci sono {dati_sito['risultati'][0]['gradi']} gradi."}
test_estensione.py — C'È GIÀ nella cartella: chiama(dati, risposte=…, negate=…) chiama \
esegui(dati, calliope) con la Calliope finta già pronta, e un primo test. Non riscriverlo: \
aggiungi i tuoi casi nella classe Prove con modifica_file, così:
    def test_trovata(self):
        out = chiama({"citta": "Borgo Alto"}, risposte={"rete_leggi": {"stato": 200,
                     "tipo": "application/json", "testo": json.dumps({"risultati": [{"gradi": 18}]})}})
        self.assertIn("18 gradi", out["da_dire"])
    def test_rete_negata(self):
        out = chiama({"citta": "Borgo Alto"}, negate=["rete_leggi"])
        self.assertIn("Non riesco", out["da_dire"])
Un test che fallisce dice l'asserzione e file:riga: correggi quel punto con modifica_file."""

# Il file di test di partenza di un'estensione (13/10, banco della temperatura sulla DGX: in un
# lavoro 41 test su 41 in errore con «esegui() missing 1 required positional argument:
# 'calliope'», e le passate spese a sistemare i test invece del codice). Va nella cartella del
# lavoro prima della prima passata (`prepara_estensione`), modificabile: la firma giusta, la
# Calliope finta pronta in `chiama` e un test che passa con qualunque estensione che risponde.
# Gli esempi nei commenti sono neutri: niente casi del banco
TEST_ESTENSIONE = '''"""I test dell'estensione (unittest). La firma è esegui(dati, calliope): «dati» è il
dict degli input del manifesto, «calliope» la Calliope finta (CalliopeFinta), che risponde al
posto di quella vera. Usa chiama(): la Calliope finta è già pronta."""
import json  # noqa: F401 — per le risposte della rete nei test
import unittest

from calliope_estensione import CalliopeFinta, ErroreCalliope  # noqa: F401
from estensione import esegui


def chiama(dati, risposte=None, negate=()):
    """esegui(dati, calliope) con una Calliope finta: risposte = {azione: risultato} (per
    esempio {"rete_leggi": {"stato": 200, "tipo": "text/html", "testo": "..."}}), negate = le
    azioni che alzano ErroreCalliope (per esempio ["rete_leggi"])."""
    return esegui(dict(dati), CalliopeFinta(risposte=risposte or {}, negate=list(negate)))


class Prove(unittest.TestCase):
    def test_risponde_sempre_con_una_frase(self):
        # Senza input l'estensione risponde con una frase (che cosa le serve), mai un'eccezione
        out = chiama({})
        self.assertIsInstance(out, dict)
        self.assertTrue(str(out.get("da_dire") or "").strip())

    # Aggiungi qui i tuoi casi, uno per cosa chiesta, con i valori veri e il risultato atteso:
    # def test_un_caso(self):
    #     out = chiama({"citta": "Borgo Alto"})
    #     self.assertIn("Borgo Alto", out["da_dire"])
'''


def prepara_estensione(sandbox, runtime: str | None = None) -> list[str]:
    """La cartella di un lavoro su un'estensione (non un gioco) prima della prima passata: il
    runtime con CalliopeFinta, in sola lettura, se manca (13/10: il banco partiva senza, e
    l'agente non poteva importare la Calliope finta), e `test_estensione.py` di partenza se
    nella cartella non c'è nessun test (una modifica tiene i suoi). I file scritti."""
    nomi = {f["percorso"] for f in sandbox.elenca()}
    scritti = []
    if "calliope_estensione.py" not in nomi:
        if runtime is None:
            from ..estensioni.servizio import runtime_testo
            runtime = runtime_testo()
        sandbox.scrivi("calliope_estensione.py", runtime)
        scritti.append("calliope_estensione.py")
    sandbox.sola_lettura |= {"calliope_estensione.py"}
    if not any(n.rsplit("/", 1)[-1].startswith("test") and n.endswith(".py") for n in nomi):
        sandbox.scrivi("test_estensione.py", TEST_ESTENSIONE)
        scritti.append("test_estensione.py")
    return scritti

PROGRAMMA_PYTHON = """SCHELETRO DI PARTENZA (programma Python): parti da qui.
programma.py:
import sys

def calcola(a, b):
    return a + b

def main(argv):
    a, b = (float(x) for x in argv[:2]) if len(argv) >= 2 else (3.0, 5.0)
    print(f"La somma di {a:g} e {b:g} è {calcola(a, b):g}")

if __name__ == "__main__":
    main(sys.argv[1:])
test_programma.py:
import unittest
from programma import calcola

class Prove(unittest.TestCase):
    def test_somma(self):
        self.assertEqual(calcola(2, 3), 5)
Un test che fallisce dice l'asserzione e file:riga: correggi quel punto con modifica_file."""

PROGRAMMA_CSHARP = """SCHELETRO DI PARTENZA (programma C#): un file Program.cs in una cartella.
using System;
using System.Globalization;
static double Somma(double a, double b) => a + b;
var it = CultureInfo.GetCultureInfo("it-IT");
double a = args.Length >= 2 ? double.Parse(args[0], it) : 3;
double b = args.Length >= 2 ? double.Parse(args[1], it) : 5;
Console.WriteLine($"La somma di {a} e {b} è {Somma(a, b)}");
Si prova con esegui_csharp e argomenti noti, controllando l'uscita; un errore di \
compilazione o un'eccezione dicono file e riga: correggi quel punto con modifica_file."""

SCHELETRI = {"gioco": GIOCO, "estensione": ESTENSIONE, "python": PROGRAMMA_PYTHON,
             "csharp": PROGRAMMA_CSHARP}


def per_programma(linguaggi=("python",)) -> str:
    """Gli scheletri dei programmi per i linguaggi che qui si eseguono (Python sempre)."""
    nomi = ["python"] + (["csharp"] if "csharp" in set(linguaggi or ()) else [])
    return "\n\n".join(SCHELETRI[n] for n in nomi)
