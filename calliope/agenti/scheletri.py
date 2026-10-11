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
test_estensione.py:
import json, unittest
from calliope_estensione import CalliopeFinta
from estensione import esegui

class Prove(unittest.TestCase):
    def test_trovata(self):
        c = CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "tipo": "application/json",
                                    "testo": json.dumps({"risultati": [{"gradi": 18}]})}})
        self.assertIn("18 gradi", esegui({"citta": "Borgo Alto"}, c)["da_dire"])
    def test_rete_negata(self):
        out = esegui({"citta": "Borgo Alto"}, CalliopeFinta(negate=["rete_leggi"]))
        self.assertIn("Non riesco", out["da_dire"])
Un test che fallisce dice l'asserzione e file:riga: correggi quel punto con modifica_file."""

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
