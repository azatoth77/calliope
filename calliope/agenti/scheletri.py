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

Dal 19/10 (issue #186) il gioco non ha più lo scheletro nel prompt: i quattro file di partenza li
scrive il codice nella cartella (`file_gioco`, `prepara_gioco`), coerenti con min e max della
richiesta e verdi (test e prova di fumo), e nel prompt resta il paragrafo che dice cosa c'è
(`GIOCO`, 831 caratteri invece di 3 347). Ciò che si può dare come file già verde non si descrive
in prosa.
"""

GIOCO = """LA PARTENZA (gioco): per un gioco nuovo nella cartella ci sono già quattro file che \
passano i test e la prova di fumo, con giocatori min e max della richiesta: manifesto.json (la \
scheda con la macchina: una fase «turno» con il comando d'esempio «porta {n}»), logica.js (GIOCO: \
aprire le porte, un punto a porta, la fine quando sono aperte tutte), logica.test.js e \
gioco.test.js (la partita vera con apriGioco, che comincia dalla preparazione). È un gioco \
d'esempio: leggili, poi cambiali in quello chiesto con modifica_file, un pezzo alla volta, \
rifacendo girare esegui_test; nel manifesto cambia anche nome, titolo e cosa_fa. In una modifica \
o in una correzione ci sono invece i file della versione di prima: riparti da quelli. Un test che \
fallisce, o la prova di fumo, dice fase, comando, strada e file:riga: correggi quel punto."""

# I file di partenza di un gioco nuovo (19/10, #186, § 3.5 n. 28 della ricerca del 19/10 sulla
# solidità dell'agente): prima il gioco partiva da una cartella vuota e l'agente ricopiava dal
# prompt manifesto, logica e test, proprio la parte rotta nel tris per due del 18/10 (#174: i
# test davano per scontato che la partita cominciasse in «turno»). Li scrive il codice, coerenti
# con min e max della richiesta (l'analisi prima del codice, accettazione.py), e passano i test
# e la prova di fumo per costruzione (prova_partenza_gioco). Le porte sono quelle dello scheletro
# di prima: due in più dei giocatori, così il gioco finisce sempre
NOME_PARTENZA = "gioco_nuovo"
TITOLO_PARTENZA = "Gioco nuovo"
GIOCATORI_PARTENZA = (1, 4)         # senza l'analisi: come lo scheletro di prima

LOGICA_PARTENZA = """"use strict";
// Il gioco d'esempio della partenza: cambialo nel gioco chiesto. Solo GIOCO, funzioni pure,
// niente DOM: preparazione, turni, punti, esito, fine e disegno sono della macchina di Calliope
const GIOCO = {
  // I dati della partita: un oggetto JSON (qui le porte e quelle già aperte)
  nuovaPartita({ giocatori }) { return { porte: giocatori + 2, aperte: [] }; },
  // I comandi che valgono adesso, dentro quelli del manifesto: le porte ancora chiuse
  attivi: { turno: (d) => ({ porta: chiuse(d) }) },
  mosse: { turno: {
    // Qui ogni porta aperta è un punto fatto, quindi una mano finita: il testo nella fase
    // «esito», poi «dopo»: di nuovo «turno» (tocca al giocatore dopo) o «fine» quando sono aperte
    // tutte. Una mossa normale, che non chiude una mano (una casella del tris), restituisce solo
    // { dati } (e i punti, se ci sono) e resta nella fase: niente esito
    porta(d, { valore }) {
      const aperte = d.aperte.concat([valore]);
      return { dati: { ...d, aperte }, punti: 1, esito: `Porta ${valore} aperta!`,
               dopo: aperte.length === d.porte ? "fine" : "turno" };
    } } },
  vista: { turno: (d) => ({ titolo: "Quale porta apri?",
                            testo: `Porte aperte: ${d.aperte.length} su ${d.porte}` }) },
};
function chiuse(d) {
  const c = [];
  for (let p = 1; p <= d.porte; p++) if (!d.aperte.includes(p)) c.push(p);
  return c;
}
if (typeof module !== "undefined") module.exports = { GIOCO, chiuse };
"""

TEST_LOGICA_PARTENZA = """const { test } = require("node:test");
const assert = require("node:assert");
const { GIOCO, chiuse } = require("./logica.js");

test("una porta aperta dà un punto e la partita va avanti", () => {
  const r = GIOCO.mosse.turno.porta(GIOCO.nuovaPartita({ giocatori: __N__ }), { valore: 2 });
  assert.deepStrictEqual(r.dati.aperte, [2]);
  assert.strictEqual(r.punti, 1);
  assert.strictEqual(r.dopo, "turno");
});

test("l'ultima porta chiusa porta alla fine", () => {
  // Dati fatti a mano: un risultato che dipende dal caso si prova così, non con nuovaPartita
  const d = { porte: 3, aperte: [1, 3] };
  assert.deepStrictEqual(chiuse(d), [2]);
  assert.strictEqual(GIOCO.mosse.turno.porta(d, { valore: 2 }).dopo, "fine");
});
"""

TEST_GIOCO_PARTENZA = """const { test } = require("node:test");
const assert = require("node:assert");
// La partita vera con la macchina di Calliope: apriGioco e creaCaso ci sono già, senza require.
// Ogni partita comincia nella fase «preparazione»: __USCITA__

test("la partita comincia dalla preparazione", async () => {
  const g = await apriGioco({ seme: 1 });
  assert.strictEqual(g.stato().fase, "preparazione");
  await g.tocca("__TOCCA__");
  assert.strictEqual(g.stato().fase, "turno");
  assert.strictEqual(g.stato().giocatori.length, __N__);
});

test("una porta aperta: il testo, il punto e poi tocca __DOPO__", async () => {
  const g = await apriGioco(__APRI__);
  await g.tocca("Porta 1");
  assert.strictEqual(g.stato().fase, "esito");
  assert.match(g.testo(), /Porta 1 aperta/);
  await g.comando("avanti");
  const s = g.stato();
  assert.strictEqual(s.fase, "turno");
  assert.strictEqual(s.tocca, "__TOCCA_DOPO__");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), __PUNTI__);
  assert.deepStrictEqual(s.comandi.porta, __CHIUSE__);
  assert.deepStrictEqual(g.palco(), []);
});

test("aperte tutte le porte la partita finisce", async () => {
  const g = await apriGioco(__APRI__);
  for (let k = 0; k < 50 && g.stato().fase !== "fine"; k++) {
    if (g.stato().fase === "esito") await g.comando("avanti");
    else await g.comando("porta", g.stato().comandi.porta[0]);
  }
  const s = g.stato();
  assert.strictEqual(s.fase, "fine");
  assert.strictEqual(s.giocatori.reduce((t, x) => t + x.punti, 0), __PORTE__);
});
"""


def giocatori_partenza(giocatori=None) -> tuple[int, int]:
    """(min, max) dei giocatori della partenza: quelli dell'analisi se validi, altrimenti
    `GIOCATORI_PARTENZA`."""
    from ..estensioni.scheda import MAX_GIOCATORI
    g = giocatori if isinstance(giocatori, dict) else {}
    a, b = g.get("min"), g.get("max")
    if all(isinstance(x, int) and not isinstance(x, bool) for x in (a, b)) \
            and 1 <= a <= b <= MAX_GIOCATORI:
        return a, b
    return GIOCATORI_PARTENZA


_IN_FONDO_NO = frozenset(
    "di a da in con su per tra fra del dello della dei degli delle al allo alla ai agli alle "
    "dal dalla dai dalle nel nella nei nelle sul sulla sui sulle il lo la i gli le un uno una "
    "e o ed".split())


def _nome_titolo(titolo: str, presi=()) -> tuple[str, str]:
    """Il nome e il titolo del manifesto di partenza dal titolo del lavoro, se fanno un
    manifesto valido; altrimenti quelli di `NOME_PARTENZA`, che la consegna non accetta."""
    import re
    import unicodedata

    def intere(parole, massimo, sep):
        # Tagliate all'ultima parola intera (20/10, revisione della PR #188: «Hallowe»)
        out = ""
        for p in parole:
            prova = f"{out}{sep}{p}" if out else p
            if len(prova) > massimo:
                break
            out = prova
        # Né una preposizione né un articolo in fondo («…le carte di»: seconda revisione)
        pezzi = out.split(sep)
        while len(pezzi) > 1 and pezzi[-1].lower() in _IN_FONDO_NO:
            pezzi.pop()
        return sep.join(pezzi)
    # Solo lettere vere e cifre («3x3» resta, × e ÷ no: sono simboli, non lettere)
    parole = re.findall(r"[^\W_]+(?:['’][^\W_]+)*", str(titolo or ""))
    t = intere(parole, 40, " ")
    base = unicodedata.normalize("NFD", t.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    nome = intere(re.findall(r"[a-z0-9]+", base), 31, "_")
    if nome[:1].isdigit():
        nome = "gioco_" + nome if len("gioco_" + nome) <= 31 else ""
    if not t or len(nome) < 3 or nome in set(presi or ()) or nome == NOME_PARTENZA:
        return NOME_PARTENZA, TITOLO_PARTENZA
    return nome, t


def file_gioco(gmin: int, gmax: int, titolo: str = "", presi=()) -> dict[str, str]:
    """I quattro file di partenza di un gioco nuovo con `gmin`..`gmax` giocatori: manifesto,
    logica e i due test. Con min = max la partita si apre con «Inizia», con min < max con «N
    giocatori» (il primo N da 2, se c'è: così il test vede passare il turno)."""
    import json
    nome, tit = _nome_titolo(titolo, presi)
    manifesto = {
        "nome": nome, "titolo": tit,
        "cosa_fa": {"verbo": "propone", "oggetto": "una partita sullo schermo"},
        "input": {"type": "object", "properties": {}, "required": []},
        "permessi": {}, "livello": "familiare",
        "scheda": {"tipo": "gioco", "file": ["logica.js"], "giocatori": {"min": gmin, "max": gmax},
                   "macchina": {"inizio": "turno", "fasi": {"turno": {
                       "pagina": "scelte", "turni": True, "verso": ["esito", "fine"],
                       "comandi": {"porta": {"forme": ["porta {n}", "la porta {n}", "{n}"],
                                             "n": {"da": 1, "a": gmax + 2},
                                             "etichetta": "Porta {n}"}}}}}}}
    from ..estensioni.manifesto import ManifestoNonValido, valida
    try:
        valida(manifesto)
    except ManifestoNonValido:
        # Un titolo del lavoro che il controllo dei testi non accetta: il segnaposto
        manifesto["nome"], manifesto["titolo"] = NOME_PARTENZA, TITOLO_PARTENZA
    n = gmin if gmin == gmax else next((k for k in range(gmin, gmax + 1) if k >= 2), gmin)
    if gmin == gmax:
        tocca, apri = "Inizia", "{ seme: 1, inizia: true }"
        uscita = (f"con giocatori min = max ({gmin}) c'è solo «Inizia»; apriGioco({{ inizia: "
                  "true }) parte già dalla fase d'inizio.")
    else:
        tocca, apri = f"{n} giocatori", f"{{ seme: 1, inizia: true, giocatori: {n} }}"
        uscita = (f"con min < max ({gmin}–{gmax}) «N giocatori» sceglie quanti (e «Inizia» "
                  f"parte con {gmin}); apriGioco({{ inizia: true, giocatori: N }}) parte già "
                  "dalla fase d'inizio.")
    porte = n + 2
    sost = {"__USCITA__": uscita, "__TOCCA__": tocca, "__N__": str(n), "__APRI__": apri,
            "__DOPO__": "all'altro" if n > 1 else "di nuovo a te",
            "__TOCCA_DOPO__": "Giocatore 2" if n > 1 else "Giocatore 1",
            "__PUNTI__": json.dumps([1] + [0] * (n - 1)),
            "__CHIUSE__": json.dumps(list(range(2, porte + 1))), "__PORTE__": str(porte)}
    test_gioco, test_logica = TEST_GIOCO_PARTENZA, TEST_LOGICA_PARTENZA
    for k, v in sost.items():
        test_gioco, test_logica = test_gioco.replace(k, v), test_logica.replace(k, v)
    return {"manifesto.json": json.dumps(manifesto, ensure_ascii=False, indent=1) + "\n",
            "logica.js": LOGICA_PARTENZA, "logica.test.js": test_logica,
            "gioco.test.js": test_gioco}


def prepara_gioco(sandbox, giocatori=None, titolo: str = "", presi=()) -> list[str]:
    """La cartella di un gioco nuovo prima della prima passata: i file di partenza, solo se
    non c'è ancora un manifesto (una modifica, una correzione o una ripresa tengono i loro).
    I file scritti."""
    if any(f["percorso"] == "manifesto.json" for f in sandbox.elenca()):
        return []
    gmin, gmax = giocatori_partenza(giocatori)
    scritti = []
    for nome, testo in file_gioco(gmin, gmax, titolo, presi).items():
        sandbox.scrivi(nome, testo)
        scritti.append(nome)
    return scritti


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
