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

Dal 13/10 (macchina a stati dei giochi, estensioni/macchina.py e motore_gioco.js) lo scheletro del
gioco è un altro: la scheda con «macchina» (una fase, un comando con lo slot «porta {n}»),
logica.js con il solo GIOCO (partita nuova, attivi, mosse, vista), i due test; niente gioco.js,
niente DOM, niente sicuro(): preparazione, turni, punti, esito, fine, disegno, pulsanti e voce
sono del motore. 2 923 caratteri (prima 2 938), circa 840 token con lo stesso rapporto; il §5 del
contratto cresce di circa 1 100 caratteri (~320 token): da rimisurare sulla DGX.

Dal 14/10 (passo 4, il palco fisso) la fase dichiara il modello di pagina («pagina»: scelte nello
scheletro), una riga dice i modelli e il test del disegno controlla anche il palco (g.palco():
[] se la pagina ci sta nei due orientamenti); la prova di fumo lo misura per ogni pagina. Misura
dei caratteri: scheletro 3 347 (prima 2 923, ~120 token in più), §5 del contratto 6 294 (prima
4 973, ~380 token), il prompt intero del gioco 24 900 (prima 22 902, ~575 token); stima con il
rapporto 3,47 caratteri per token di Qwen3.6, da rimisurare sulla DGX.

Dal 17/10 (issue #54) il programma JavaScript, solo con «javascript» acceso in agenti_linguaggi:
740 caratteri, ~210 token con lo stesso rapporto.
"""

GIOCO = """SCHELETRO DI PARTENZA (gioco): parti da qui e cambia solo quello che serve. \
Preparazione (quanti giocatori), turni, punti, esito della mossa, fine con la classifica e \
«ancora», il disegno della pagina, i pulsanti e la voce sono della macchina a stati di Calliope: \
NON scriverli. Ogni comando è anche un pulsante. Niente gioco.js, niente DOM.
manifesto.json — la sezione "scheda":
{"tipo": "gioco", "file": ["logica.js"], "giocatori": {"min": 1, "max": 4},
 "macchina": {"inizio": "turno", "fasi": {"turno": {"pagina": "scelte", "verso": ["esito", "fine"],
  "comandi": {"porta": {"forme": ["porta {n}", "la porta {n}", "{n}"], "n": {"da": 1, "a": 6},
                        "etichetta": "Porta {n}"}}}}}}
Ogni fase sceglie una pagina di Calliope: scelte (un pulsante per comando e valore), griglia \
(una scacchiera: vista dà «caselle»), messaggio, punteggi, titolo, classifica; tela solo per il \
tempo reale.
logica.js — solo GIOCO, funzioni pure, niente DOM:
"use strict";
const GIOCO = {
  nuovaPartita({ giocatori }) { return { porte: 2 + giocatori, aperte: [] }; },
  attivi: { turno: (d) => ({ porta: chiuse(d) }) },
  mosse: { turno: {
    porta(d, { valore }) {
      const aperte = d.aperte.concat([valore]);
      return { dati: { ...d, aperte }, punti: 1, esito: `Porta ${valore} aperta!`,
               dopo: aperte.length === d.porte ? "fine" : "turno" };
    } } },
  vista: { turno: (d) => ({ titolo: "Quale porta apri?" }) },
};
function chiuse(d) {
  const c = [];
  for (let p = 1; p <= d.porte; p++) if (!d.aperte.includes(p)) c.push(p);
  return c;
}
if (typeof module !== "undefined") module.exports = { GIOCO, chiuse };
logica.test.js:
const { test } = require("node:test");
const assert = require("node:assert");
const { GIOCO } = require("./logica.js");
test("una porta aperta dà un punto", () => {
  const r = GIOCO.mosse.turno.porta(GIOCO.nuovaPartita({ giocatori: 1 }), { valore: 2 });
  assert.deepStrictEqual(r.dati.aperte, [2]);
  assert.strictEqual(r.punti, 1);
});
gioco.test.js — la partita vera con la macchina di Calliope; apriGioco e creaCaso ci sono già, \
senza require:
const { test } = require("node:test");
const assert = require("node:assert");
test("si apre una porta e poi tocca all'altro", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("2 giocatori");
  await g.tocca("Porta 1");
  assert.match(g.testo(), /Porta 1 aperta/);
  await g.comando("avanti");
  assert.strictEqual(g.stato().tocca, "Giocatore 2");
  assert.deepStrictEqual(g.palco(), []);
});
Una mossa restituisce SOLO { dati, punti, esito, fase, dopo, ancora }: tutto lo stato del gioco \
dentro «dati», il testo da mostrare in «esito», e «dopo» (la fase dopo l'esito, di solito la \
stessa o "fine"). attivi restringe (true, false o valori), mai fuori dal manifesto; vista dà \
solo testi { titolo, sottotitolo, testo }. Ciò che la persona deve VEDERE si prova in \
gioco.test.js: g.tocca("testo"), g.comando("porta", 3) (come la voce), g.avanza(ms), g.testo(), \
g.stato() (fase, tocca, giocatori e punti, esito, comandi), g.palco() (cosa non sta nella \
pagina). La prova di fumo percorre ogni fase con ogni comando e valore, gioca partite intere e \
misura ogni pagina sul palco (1280×720 e 720×1280: testi troppo lunghi, troppi pulsanti): un \
errore dice fase, pagina, strada e file:riga. Correggi quel punto con modifica_file."""

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
        # Il servizio lo segna in sola lettura insieme al contratto, prima di qui: lo si
        # scrive comunque (è il codice di Calliope, non dell'agente)
        sandbox.sola_lettura.discard("calliope_estensione.py")
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

# JavaScript (17/10, #54): Node in CommonJS, la funzione esportata per il test e il main solo
# quando il file si esegue
PROGRAMMA_JAVASCRIPT = """SCHELETRO DI PARTENZA (programma JavaScript, Node): parti da qui.
programma.js:
"use strict";
function calcola(a, b) { return a + b; }
function main(argv) {
  const [a, b] = argv.length >= 2 ? argv.slice(0, 2).map(Number) : [3, 5];
  console.log(`La somma di ${a} e ${b} è ${calcola(a, b)}`);
}
if (require.main === module) main(process.argv.slice(2));
module.exports = { calcola };
programma.test.js:
const { test } = require("node:test");
const assert = require("node:assert");
const { calcola } = require("./programma.js");
test("la somma", () => { assert.strictEqual(calcola(2, 3), 5); });
Si prova con esegui_js (argomenti noti) ed esegui_test; un test che fallisce dice \
l'asserzione e file:riga: correggi quel punto con modifica_file."""

SCHELETRI = {"gioco": GIOCO, "estensione": ESTENSIONE, "python": PROGRAMMA_PYTHON,
             "csharp": PROGRAMMA_CSHARP, "javascript": PROGRAMMA_JAVASCRIPT}


def per_programma(linguaggi=("python",)) -> str:
    """Gli scheletri dei programmi per i linguaggi che qui si eseguono (Python sempre)."""
    voluti = set(linguaggi or ())
    nomi = ["python"] + [n for n in ("csharp", "javascript") if n in voluti]
    return "\n\n".join(SCHELETRI[n] for n in nomi)
