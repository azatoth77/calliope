"""Banco del revisore (19/10/2026, issue #182; ricerca docs/ricerche/2026-10-19-solidita-harness-
sviluppo.md § 3.6 e § 4, passo 6 del § 5; area agenti-estensioni).

In Cline e negli strumenti simili i punti di verifica li fa lo sviluppatore che guarda («stai
girando in tondo», «il test è sbagliato, non il codice»); in Calliope nessuno guarda le passate.
L'ipotesi da misurare prima di costruire il revisore nel ciclo: una passata dello **stesso
modello** dell'agente (qwen3.6 su vLLM, dalla Config) a **contesto pulito**, con le sole prove e
un'uscita chiusa, dà i verdetti che darebbe la persona. Caso guida: il tris del 18/10 (#174),
dove l'errore diceva già la fase «preparazione» e la risposta giusta era «correggi il test:
tocca Inizia».

**Il pacchetto delle prove** (l'unica cosa che il revisore vede): il contratto del gioco
(`estensioni/contratto.testo`, quello che vede l'agente), i requisiti, i file del lavoro
**senza commenti** (l'11/10 qwen3:8b ha creduto a «// Musica: fatto»), l'esito dei test con i
fallimenti in breve (`agenti/diagnosi.da_uscita`) e la coda dell'uscita, il registro dei
tentativi se il caso ne ha uno. Mai la trascrizione, il diario o il riassunto dell'agente.

**La passata**: `requisiti.chiama` (la stessa delle analisi a sé: schema chiuso in uscita, una
passata senza strumenti), con il ragionamento acceso (`--ragionamento`, di serie 4096 token) e
la temperatura dell'agente (`agenti_temperatura`, salvo `--temperatura`). Lo schema: `verdetto`
∈ {continua, cambia_strada, test_sbagliato, codice_sbagliato, consegna, chiedi_persona},
`file`, `riga`, `test`, `causa`, `azione` (una frase).

**I casi fissi**, costruiti dai riferimenti che ci sono già; l'uscita dei test è **vera**,
generata a ogni esecuzione del banco con Node e il motore dei giochi di adesso (la sandbox
della Config se il container di Node c'è, altrimenti il Node della macchina con il docker finto
delle prove; senza Node i casi si saltano, 77):

- `tris-inizia` → `test_sbagliato`, gioco.test.js: il tris per due di `prove/giochi/tris`
  (min = max = 2) con il test dell'agente del 18/10 che muove senza «Inizia»; l'errore vero
  del motore dice già «correggi il test, non il manifesto» (fumo_js.mjs, `viaDallaPreparazione`,
  da #174), quindi qui si misura anche se il modello legge il suggerimento;
- `tris-inizia-muto` → lo stesso, ma nel pacchetto la frase di consiglio dell'errore è tolta
  (restano la fase e i comandi attivi): si vede se riconosce il test sbagliato da solo;
- `porte-disegno` → `test_sbagliato`, gioco.test.js: le porte giuste di
  `prove/prova_fasi_agente.py` con il test del disegno di L7 del 14/10 («avanti» subito dopo
  «2 giocatori», `stato().punti["Giocatore 1"]`);
- contrari (senza, un revisore che dice sempre «test sbagliato» fa 100 %):
  `codice_sbagliato` → logica.js: le porte rotte (il mostro della porta accanto) con il test
  del disegno giusto; `consegna`: il tris per due con i test verdi, la prova di fumo compresa;
  `cambia_strada`: le porte rotte e un registro di cinque tentativi A-B-A-B-A
  (giocatori.min del manifesto 2 → 1 → 2 → 1 → 2 → 1) con lo stesso errore, vero, a ogni
  tentativo; `chiedi_persona`: un requisito lasciato alla persona («la caramella vale dei
  punti: quanti, poi te lo dico») e un test dell'agente che ne ha scelto uno (la logica dà
  «Nessun punto!» alla caramella: un «codice_sbagliato» è un'ambiguità del caso più che un
  errore del revisore).

**Da un lavoro vero** (`--da-lavoro <cartella>`, solo sulla DGX; niente di quella cartella va
nel repository): lo stesso pacchetto dalla cartella della sandbox di un lavoro o dalla sua
cartella dei risultati: i file (senza `.calliope/`, `esempi_veri/`, `lavoro.json`,
`risultato.md`, CAPACITA.md e il runtime; senza commenti, al più MAX_FILE caratteri per file
e MAX_FILE_TOTALE in tutto, prima il manifesto, il codice e i test, con l'avviso del taglio
anche nel pacchetto), i test rieseguiti adesso in una sandbox nuova su tutti i file,
i requisiti dello sviluppo del lavoro (sviluppi.json accanto alle sandbox, trovati dal numero
del lavoro e dall'ora; senza l'ora e con più sviluppi candidati il banco si ferma e chiede
`--sviluppo S32`), altrimenti la richiesta di lavoro.json; `--registro <file>` (JSON o testo)
aggiunge un registro dei tentativi. Il verdetto atteso lo dà `--atteso` (con `--file-atteso`).

**Misura**: per caso, N ripetizioni (`--ripetizioni`, 5): verdetti giusti su N, file giusto e
test giusto su N (dove il caso li dice), secondi e token medi (anche di ragionamento); una
tabella alla fine e `riepilogo.json` nella cartella d'uscita (`--uscita`). Criterio di #182:
≥ 4/5 sui casi (`tris-inizia`, `tris-inizia-muto`, `porte-disegno`) e ≥ 4/5 su ciascun
contrario: il revisore a contesto pulito si costruisce con qwen3.6; sotto, serve un modello
diverso (#175) o il revisore non vale.

**Sulla DGX quando vLLM è libero** (non insieme al banco della temperatura né a un lavoro
dell'agente), dalla cartella dei dati (configurazione e motore dell'agente di questa
installazione), con l'interprete di Calliope. Dopo l'unione, dalla versione installata:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_revisore.py --ripetizioni 5 \\
           --uscita ~/banco-revisore

Prima dell'unione, da un clone intero del ramo (il banco usa il codice del clone:
`requisiti.chiama` con la temperatura, dal 19/10), con l'interprete e i dati installati:

    git clone -b issue-182-banco-revisore https://github.com/azatoth77/calliope \\
        ~/banchi/src-issue182        # già clonato: git -C ~/banchi/src-issue182 pull
    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python ~/banchi/src-issue182/prove/manuali/banco_revisore.py \\
           [--ripetizioni 5] [--casi tris-inizia,porte-disegno,...] [--ragionamento 4096] \\
           [--temperatura 0.6] [--uscita ~/banco-revisore]

Una passata dura 20–90 s (fino a 4096 token di ragionamento più l'uscita, ~7 000 token di
prompt): 7 casi × 5 ripetizioni = 35 passate, 20–50 minuti.

A secco (nessun modello, anche sul portatile; serve Node), per controllare il banco stesso:
l'uscita vera di ogni caso (rossa o verde come deve, «preparazione» per tris-inizia, senza il
consiglio per tris-inizia-muto, lo stesso errore nei cinque tentativi), il pacchetto senza
commenti né trascrizione (anche da una cartella di lavoro finta con diario e passo-N.txt, con
la precedenza e il marcatore del taglio), e un modello finto con verdetti preparati,
giusti e sbagliati, contati come devono:

    python prove/manuali/banco_revisore.py --secco
"""

import argparse
import datetime
import io
import json
import re
import shutil
import statistics
import sys
import tempfile
import time
import tokenize
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

VERDETTI = ("continua", "cambia_strada", "test_sbagliato", "codice_sbagliato", "consegna",
            "chiedi_persona")
SALTATO = 77
CASI = ("tris-inizia", "tris-inizia-muto", "porte-disegno", "codice_sbagliato", "consegna",
        "cambia_strada", "chiedi_persona")
CODA_USCITA = 2500          # caratteri della coda dell'uscita dei test nel pacchetto
MAX_FILE = 12_000           # --da-lavoro: caratteri al più per file nel pacchetto…
MAX_FILE_TOTALE = 60_000    # …e in tutto (un messaggio oltre num_ctx, o prove diluite)
# Il consiglio dell'errore della preparazione (fumo_js.mjs, viaDallaPreparazione, da #174):
# tolto per tris-inizia-muto; restano la fase e i comandi attivi
CONSIGLIO = re.compile(r"prima delle mosse tocca «[^»]*» \(await g\.tocca\(\"[^\"]*\"\)\)"
                       r"(?: o apri con apriGioco\([^)]*\))?: ogni partita comincia nella fase "
                       r"«preparazione»; correggi il test, non il manifesto\. ")


# ═══════════════════════════ il revisore ═══════════════════════════

SISTEMA = """Sei il revisore di un lavoro di sviluppo per Calliope, un'assistente di casa. Un \
agente ha scritto il codice e i test; tu non scrivi codice e non hai strumenti. Giudichi solo \
dalle prove che ricevi: il contratto (cosa offre l'ambiente e come si scrivono i test), i \
requisiti della persona, i file del lavoro (senza commenti), l'esito vero dei test e, se c'è, \
il registro dei tentativi dell'agente. Dai il verdetto che darebbe una persona esperta che \
guarda il lavoro.

Verdetti:
- continua: il lavoro va nella direzione giusta e l'agente ha già quello che serve per andare \
avanti; nessun intervento.
- cambia_strada: il registro mostra che l'agente gira in tondo (torna a versioni già provate, \
lo stesso errore a ogni tentativo): la strada presa non porta da nessuna parte. Vale anche se \
sai dov'è l'errore vero: dillo in causa e azione.
- test_sbagliato: un test chiede qualcosa che il contratto o i requisiti non dicono (o il \
contrario di quello che dicono), e il codice è giusto: va corretto il test.
- codice_sbagliato: il test è giusto e il codice no: va corretto il codice.
- consegna: i test passano tutti e i file coprono i requisiti: si può consegnare.
- chiedi_persona: quello che decide dipende da una scelta che i requisiti lasciano alla \
persona: né il test né il codice possono saperla.

In «file» e «riga» il punto da cambiare (vuoto e 0 se non serve), in «test» il nome del test \
che conta (vuoto se nessuno), in «causa» il perché in breve, in «azione» una sola frase con \
la prossima cosa da fare. Rispondi solo con il JSON dello schema."""


def schema() -> dict:
    return {"type": "object",
            "properties": {"verdetto": {"type": "string", "enum": list(VERDETTI)},
                           "file": {"type": "string", "maxLength": 120},
                           "riga": {"type": "integer"},
                           "test": {"type": "string", "maxLength": 200},
                           "causa": {"type": "string", "maxLength": 400},
                           "azione": {"type": "string", "maxLength": 300}},
            "required": ["verdetto", "file", "riga", "test", "causa", "azione"]}


# ═══════════════════════════ i file senza commenti ═══════════════════════════

_PRIMA_REGEX = set("(,=:[!&|?{};+-*%<>~^") | {""}
_PAROLE_REGEX = ("return", "typeof", "case", "in", "of", "delete", "void", "throw", "new")


def senza_commenti_js(testo: str) -> str:
    """Il JavaScript senza commenti // e /* */, con le stringhe, i template e le espressioni
    regolari intatti, e le righe al loro posto (i file:riga dell'uscita dei test restano
    giusti)."""
    s, out, i, n = str(testo or ""), [], 0, len(str(testo or ""))
    ultimo = ""             # l'ultimo carattere significativo, per riconoscere una regex

    def prima_parola():
        m = re.search(r"([A-Za-z_$][\w$]*)\s*$", "".join(out[-40:]))
        return m.group(1) if m else ""
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * s.count("\n", i, j))
            i = j
            continue
        if c in "'\"`":
            j = i + 1
            while j < n and s[j] != c:
                if s[j] == "\\":
                    j += 1
                elif s[j] == "\n" and c != "`":
                    break
                j += 1
            out.append(s[i:j + 1])
            i, ultimo = j + 1, c
            continue
        if c == "/" and (ultimo in _PRIMA_REGEX or prima_parola() in _PAROLE_REGEX):
            j, classe = i + 1, False
            while j < n and s[j] != "\n":
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == "[":
                    classe = True
                elif s[j] == "]":
                    classe = False
                elif s[j] == "/" and not classe:
                    break
                j += 1
            j += 1
            while j < n and (s[j].isalpha()):
                j += 1
            out.append(s[i:j])
            i, ultimo = j, "a"
            continue
        out.append(c)
        if not c.isspace():
            ultimo = c
        i += 1
    return "\n".join(r.rstrip() for r in "".join(out).split("\n"))


def senza_commenti_py(testo: str) -> str:
    """Il Python senza commenti né docstring (una stringa da sola su una riga), con le righe al
    loro posto. Se non si riesce a leggerlo, solo le righe che cominciano con #."""
    s = str(testo or "")
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(s).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "\n".join("" if r.lstrip().startswith("#") else r for r in s.split("\n"))
    righe = s.split("\n")
    via: list[tuple] = []        # (riga, colonna, riga fine, colonna fine) da svuotare
    prima = tokenize.NEWLINE
    for k, t in enumerate(toks):
        if t.type == tokenize.COMMENT:
            via.append((*t.start, *t.end))
        elif (t.type == tokenize.STRING and prima in (tokenize.NEWLINE, tokenize.INDENT,
                                                      tokenize.DEDENT, tokenize.NL)
              and k + 1 < len(toks) and toks[k + 1].type in (tokenize.NEWLINE,
                                                              tokenize.ENDMARKER)):
            via.append((*t.start, *t.end, "docstring"))
        if t.type not in (tokenize.COMMENT, tokenize.NL):
            prima = t.type
    for v in reversed(via):
        r0, c0, r1, c1 = v[:4]
        segnaposto = '""' if len(v) > 4 else ""
        if r0 == r1:
            riga = righe[r0 - 1]
            righe[r0 - 1] = riga[:c0] + segnaposto + riga[c1:]
        else:
            righe[r0 - 1] = righe[r0 - 1][:c0] + segnaposto
            for r in range(r0, r1 - 1):
                righe[r] = ""
            righe[r1 - 1] = righe[r1 - 1][c1:]
    return "\n".join(r.rstrip() for r in righe)


def senza_commenti(nome: str, testo: str) -> str:
    n = nome.lower()
    if n.endswith((".js", ".mjs", ".cjs", ".ts", ".cs")):
        return senza_commenti_js(testo)
    if n.endswith(".py"):
        return senza_commenti_py(testo)
    return str(testo or "")


# ═══════════════════════════ i casi fissi ═══════════════════════════

def _porte():
    import prova_fasi_agente as F
    return F


REQUISITI_TRIS = [
    "Sempre esattamente due giocatori, che giocano a turno sullo stesso schermo.",
    "Una griglia 3×3: chi è di turno mette il suo segno (prima X, poi O) toccando una casella "
    "libera o dicendo «casella N» (N da 1 a 9, da sinistra a destra e dall'alto in basso).",
    "Chi mette tre segni in fila (riga, colonna o diagonale) vince e prende un punto.",
    "Con la griglia piena senza tre in fila è pareggio, senza punti.",
]
REQUISITI_PORTE = [
    "Da 2 a 4 giocatori: si sceglie in quanti, poi a turno ogni giocatore tocca una porta.",
    "Dietro ogni porta c'è un mostro che vale dei punti (il Fantasmino 3, il Pipistrello 2) o "
    "una caramella che non ne vale.",
    "Dopo ogni porta si vede cosa c'era dietro, con il nome, e i punti presi («+3 punti!» o "
    "«Nessun punto!»).",
    "Si vede il punteggio dei giocatori.",
]
REQUISITI_CARAMELLA = REQUISITI_PORTE[:1] + [
    "Dietro ogni porta c'è un mostro che vale dei punti (il Fantasmino 3, il Pipistrello 2) o "
    "una caramella.",
    "Anche la caramella vale dei punti: quanti lo decide la persona, che ha detto «poi ti dico "
    "quanti».",
    "Dopo ogni porta si vede cosa c'era dietro, con il nome, e i punti presi.",
] + REQUISITI_PORTE[3:]

LOGICA_TEST_TRIS = """const test = require("node:test");
const assert = require("node:assert");
const { GIOCO, vincitore } = require("./logica.js");

test("tre in riga vince", () => {
  assert.strictEqual(vincitore(["X", "X", "X", "", "", "", "", "", ""]), "X");
});

test("la casella va a chi tocca, poi il segno cambia", () => {
  const r = GIOCO.mosse.turno.casella(GIOCO.nuovaPartita({ giocatori: 2 }), { valore: 5 });
  assert.strictEqual(r.dati.celle[4], "X");
  assert.strictEqual(r.dati.segno, "O");
});
"""
_MOSSA = """async function mossa(g, n) {
  while (g.stato().fase === "esito") await g.comando("avanti");
  await g.comando("casella", n);
}
async function finePartita(g) {
  await g.avanza(20000);
  while (g.stato().fase === "esito") await g.comando("avanti");
}
"""
GIOCO_TEST_TRIS = """const { test } = require("node:test");
const assert = require("node:assert");
""" + _MOSSA + """
test("tre in fila vince e prende un punto", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("Inizia");
  for (const n of [1, 4, 2, 5, 3]) await mossa(g, n);
  await finePartita(g);
  assert.strictEqual(g.stato().fase, "fine");
  assert.deepStrictEqual(g.stato().giocatori.map((x) => x.punti).sort(), [0, 1]);
});

test("con la griglia piena è pareggio, senza punti", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("Inizia");
  for (const n of [1, 2, 3, 5, 4, 6, 8, 7, 9]) await mossa(g, n);
  await finePartita(g);
  assert.strictEqual(g.stato().fase, "fine");
  assert.deepStrictEqual(g.stato().giocatori.map((x) => x.punti), [0, 0]);
});
"""
# Il test dell'agente del 18/10 (#174): la partita data per cominciata, senza «Inizia»
GIOCO_TEST_TRIS_SENZA_INIZIA = """const { test } = require("node:test");
const assert = require("node:assert");
""" + _MOSSA + """
test("tre in fila vince e prende un punto", async () => {
  const g = await apriGioco({ seme: 1 });
  for (const n of [1, 4, 2, 5, 3]) await mossa(g, n);
  await finePartita(g);
  assert.strictEqual(g.stato().fase, "fine");
  assert.deepStrictEqual(g.stato().giocatori.map((x) => x.punti).sort(), [0, 1]);
});
"""
# Il test del disegno di L7 (14/10): «avanti» subito dopo «2 giocatori» (si è già nella fase
# d'inizio) e i punti letti come stato().punti["Giocatore 1"] (sono giocatori[0].punti)
GIOCO_TEST_PORTE_L7 = """const { test } = require("node:test");
const assert = require("node:assert");
test("la porta del fantasmino mostra il mostro e dà tre punti", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("2 giocatori");
  await g.comando("avanti");
  await g.tocca("Porta 1");
  assert.match(g.testo(), /Fantasmino/);
  assert.strictEqual(g.stato().punti["Giocatore 1"], 3);
});
"""
# Il test dell'agente che ha scelto da sé quanto vale la caramella
GIOCO_TEST_CARAMELLA = """const { test } = require("node:test");
const assert = require("node:assert");
test("la porta della caramella dà un punto", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("2 giocatori");
  await g.tocca("Porta 2");
  assert.match(g.testo(), /Caramella/);
  assert.match(g.testo(), /\\+1 punt/);
});
"""


def file_tris(gioco_test: str) -> dict:
    """Il tris delle prove dei giochi (prove/giochi/tris) con giocatori min = max = 2, come il
    riferimento del banco della temperatura (tris2)."""
    cartella = RADICE / "prove" / "giochi" / "tris"
    m = json.loads((cartella / "manifesto.json").read_text(encoding="utf-8"))
    m["nome"], m["titolo"] = "tris_due", "Tris per due"
    m["scheda"]["giocatori"] = {"min": 2, "max": 2}
    return {"logica.js": (cartella / "logica.js").read_text(encoding="utf-8"),
            "logica.test.js": LOGICA_TEST_TRIS, "gioco.test.js": gioco_test,
            "manifesto.json": json.dumps(m, ensure_ascii=False, indent=1)}


def file_porte(logica: str, gioco_test: str | None, minimo: int = 2) -> dict:
    F = _porte()
    m = json.loads(json.dumps(F.MANIFESTO_PORTE))
    m["scheda"]["giocatori"]["min"] = minimo
    out = {"logica.js": logica, "logica.test.js": F.TEST_LOGICA_PORTE,
           "manifesto.json": json.dumps(m, ensure_ascii=False, indent=1)}
    if gioco_test:
        out["gioco.test.js"] = gioco_test
    return out


def casi() -> dict:
    """{nome: caso}: file, requisiti, il registro (una lista di stati da eseguire: l'esito di
    ogni tentativo è quello vero), l'atteso (verdetto, file, test) e se è un contrario."""
    F = _porte()
    return {
        "tris-inizia": {"requisiti": REQUISITI_TRIS,
                        "file": file_tris(GIOCO_TEST_TRIS_SENZA_INIZIA),
                        "atteso": {"verdetto": "test_sbagliato", "file": "gioco.test.js",
                                   "test": "tre in fila vince"},
                        "contrario": False},
        "tris-inizia-muto": {"requisiti": REQUISITI_TRIS,
                             "file": file_tris(GIOCO_TEST_TRIS_SENZA_INIZIA), "muto": True,
                             "atteso": {"verdetto": "test_sbagliato", "file": "gioco.test.js",
                                        "test": "tre in fila vince"},
                             "contrario": False},
        "porte-disegno": {"requisiti": REQUISITI_PORTE,
                          "file": file_porte(F.GIOCO_GIUSTO, GIOCO_TEST_PORTE_L7),
                          "atteso": {"verdetto": "test_sbagliato", "file": "gioco.test.js",
                                     "test": "fantasmino"},
                          "contrario": False},
        "codice_sbagliato": {"requisiti": REQUISITI_PORTE,
                             "file": file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE),
                             "atteso": {"verdetto": "codice_sbagliato", "file": "logica.js",
                                        "test": "fantasmino"},
                             "contrario": True},
        "consegna": {"requisiti": REQUISITI_TRIS, "file": file_tris(GIOCO_TEST_TRIS),
                     "atteso": {"verdetto": "consegna"}, "contrario": True},
        # A-B-A-B-A: l'agente cambia giocatori.min nel manifesto (2 → 1 → 2 → 1 → 2 → 1) e
        # l'errore, nella logica, resta lo stesso; lo stato di adesso è l'ultimo tentativo
        "cambia_strada": {"requisiti": REQUISITI_PORTE,
                          "file": file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE, minimo=1),
                          "registro": [
                              ("manifesto.json", "scheda.giocatori.min da 2 a 1",
                               file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE, minimo=1)),
                              ("manifesto.json", "scheda.giocatori.min da 1 a 2",
                               file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE, minimo=2)),
                              ("manifesto.json", "scheda.giocatori.min da 2 a 1",
                               file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE, minimo=1)),
                              ("manifesto.json", "scheda.giocatori.min da 1 a 2",
                               file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE, minimo=2)),
                              ("manifesto.json", "scheda.giocatori.min da 2 a 1",
                               file_porte(F.GIOCO_ROTTO, F.TEST_GIOCO_PORTE, minimo=1))],
                          "atteso": {"verdetto": "cambia_strada", "file": "logica.js"},
                          "contrario": True},
        "chiedi_persona": {"requisiti": REQUISITI_CARAMELLA,
                           "file": file_porte(F.GIOCO_GIUSTO, GIOCO_TEST_CARAMELLA),
                           "atteso": {"verdetto": "chiedi_persona"}, "contrario": True},
    }


# ═══════════════════════════ la sandbox e i test ═══════════════════════════

class Sandboxes:
    """Le sandbox nuove dove si eseguono i test: quella della Config (il container di Node) se
    c'è, altrimenti il Node della macchina con il docker finto delle prove."""

    def __init__(self, cfg, tmp: Path, modo: str = "auto"):
        self.cfg, self.tmp, self.n = cfg, Path(tmp), 0
        self.vera = None
        self.descrizione = ""
        if modo in ("auto", "vera"):
            try:
                from calliope.agenti.linguaggi import scegli
                from calliope.agenti.sandbox import scegli_isolamento
                iso = scegli_isolamento(getattr(cfg, "agenti_sandbox_motore", "auto"),
                                        getattr(cfg, "agenti_sandbox_immagine", None))
                isolamenti = scegli(cfg, iso)
                js = isolamenti.get("javascript")
                if iso is not None and iso.pronto and js is not None and js.pronto:
                    self.vera = (iso, isolamenti)
                    self.descrizione = f"sandbox della Config ({js.descrizione})"
            except Exception as e:  # noqa: BLE001 — si ripiega sul Node della macchina
                self.descrizione = f"sandbox della Config non pronta ({type(e).__name__})"
        if self.vera is None and modo != "vera" and shutil.which("node"):
            self.descrizione = "Node della macchina (docker finto delle prove)"
        elif self.vera is None:
            self.descrizione = "nessun Node: " + (self.descrizione or "manca node")

    @property
    def pronte(self) -> bool:
        return self.vera is not None or self.descrizione.startswith("Node della macchina")

    def nuova(self):
        self.n += 1
        if self.vera is not None:
            from calliope.agenti.sandbox import Sandbox
            iso, isolamenti = self.vera
            return Sandbox(self.tmp / f"s{self.n}",
                           float(getattr(self.cfg, "agenti_esecuzione_s", 30.0)),
                           int(getattr(self.cfg, "agenti_memoria_mb", 1024)),
                           isolamento=iso, linguaggi=isolamenti)
        import prova_agente_guida as G
        return G.sandbox(self.tmp, f"s{self.n}")

    def test(self, file: dict) -> dict:
        """I test di tutti i file come li esegue esegui_test (con la prova di fumo per un
        gioco), in una sandbox nuova."""
        sb = self.nuova()
        for rel, testo in file.items():
            sb.scrivi(rel, testo)
        if any(n.endswith(".py") for n in file) and _manifesto(file) and not _gioco(file):
            import calliope.estensioni as E
            shutil.copy(Path(E.__file__).parent / "_ospite.py",
                        sb.root / "calliope_estensione.py")
        r = sb.test()
        shutil.rmtree(sb.root, ignore_errors=True)
        return r


def _manifesto(file: dict) -> dict:
    try:
        m = json.loads(file.get("manifesto.json") or "")
        return m if isinstance(m, dict) else {}
    except ValueError:
        return {}


def _gioco(file: dict) -> bool:
    return ((_manifesto(file).get("scheda") or {}).get("tipo") == "gioco")


def firma(r: dict) -> str:
    """L'errore di un'esecuzione in una riga (il primo dei fallimenti in breve)."""
    from calliope.agenti import diagnosi
    if r.get("passano"):
        return "tutti i test passano"
    f = diagnosi.fallimenti(str(r.get("uscita") or ""))
    return diagnosi.riga(f[0], 240) if f else str(r.get("uscita") or "").strip()[-240:]


# ═══════════════════════════ il pacchetto ═══════════════════════════

ESCLUSI = {"lavoro.json", "CAPACITA.md", "calliope_estensione.py", "risultato.md"}
# --da-lavoro: cartelle eseguite con i test ma non mostrate (le risposte vere delle sonde, fino
# a 8000 caratteri l'una: diluiscono le prove)
CARTELLE_ESCLUSE = ("esempi_veri",)
TAGLIATO = "…[tagliato dal banco]"


def pacchetto(cfg, requisiti: list, file: dict, r: dict, registro: list | None = None,
              richiesta: str = "", mostrati: dict | None = None,
              avvisi: list | None = None) -> dict:
    """Le sezioni che il revisore vede, e nient'altro: contratto, requisiti, file senza
    commenti, esito dei test, registro dei tentativi."""
    from calliope.agenti import diagnosi
    from calliope.estensioni import contratto
    gioco = _gioco(file)
    tipo = "gioco" if gioco else "estensione" if _manifesto(file) else "codice"
    u = str(r.get("uscita") or "")
    fall = "" if r.get("passano") else diagnosi.da_uscita(u)
    return {
        "contratto": contratto.testo(cfg, tipo),
        "requisiti": ("\n".join(f"{i}. {x}" for i, x in enumerate(requisiti, 1)) if requisiti
                      else f"(requisiti non trovati; la richiesta: «{richiesta}»)"
                      if richiesta else "(requisiti non trovati)"),
        # `mostrati` (--da-lavoro) è già senza commenti e tagliato: non si tocca di nuovo
        "file": ({n: senza_commenti(n, t) for n, t in sorted(file.items()) if n not in ESCLUSI}
                 if mostrati is None else dict(sorted(mostrati.items()))),
        "test": {"esito": diagnosi.conto_detto(r) + ("" if r.get("passano") else
                                                     ", non passano tutti"),
                 "passano": bool(r.get("passano")), "fallimenti": fall,
                 "uscita": u[-CODA_USCITA:]},
        "registro": list(registro or []),
        "avvisi": list(avvisi or []),
    }


def messaggio(p: dict) -> str:
    """Il pacchetto come messaggio dell'utente della passata."""
    parti = ["# CONTRATTO (quello che vede l'agente)", p["contratto"], "",
             "# REQUISITI DELLA PERSONA", p["requisiti"], "", "# FILE DEL LAVORO"]
    for n, t in p["file"].items():
        righe = t.split("\n")
        parti += [f"## {n}", "\n".join(f"{i:>3}| {x}" for i, x in enumerate(righe, 1)), ""]
    t = p["test"]
    parti += ["# ESITO DEI TEST (eseguiti adesso)", t["esito"]]
    if t["fallimenti"]:
        parti += ["Fallimenti in breve:", t["fallimenti"]]
    parti += ["Coda dell'uscita:", t["uscita"], ""]
    if p.get("avvisi"):
        parti += ["# AVVISI DEL BANCO (file tagliati o tolti dal pacchetto)"]
        parti += [f"- {a}" for a in p["avvisi"]] + [""]
    if p["registro"]:
        parti += ["# REGISTRO DEI TENTATIVI DELL'AGENTE (dal più vecchio)"]
        for i, x in enumerate(p["registro"], 1):
            parti.append(f"{i}. {x}" if isinstance(x, str) else
                         f"{i}. {x.get('file')}: {x.get('cosa')} → test: {x.get('esito')}")
    else:
        parti += ["# REGISTRO DEI TENTATIVI", "(nessun registro per questo lavoro)"]
    return "\n".join(parti)


def prepara(cfg, sbx: Sandboxes, caso: dict) -> dict:
    """Il pacchetto di un caso fisso, con l'uscita vera dei test e del registro."""
    r = sbx.test(caso["file"])
    registro = []
    for f, cosa, stato in caso.get("registro") or []:
        registro.append({"file": f, "cosa": cosa, "esito": firma(sbx.test(stato))})
    p = pacchetto(cfg, caso["requisiti"], caso["file"], r, registro)
    p["_risultato"] = {"passano": bool(r.get("passano")), "uscita": str(r.get("uscita") or "")}
    if caso.get("muto"):
        return muto(p)
    return p


def muto(p: dict) -> dict:
    """Il pacchetto senza il consiglio dell'errore della preparazione (tris-inizia-muto): il
    revisore vede la fase e i comandi attivi, non «correggi il test, non il manifesto»."""
    t = dict(p["test"])
    for k in ("fallimenti", "uscita"):
        t[k] = CONSIGLIO.sub("", t[k])
    reg = [dict(x, esito=CONSIGLIO.sub("", str(x.get("esito") or ""))) if isinstance(x, dict)
           else CONSIGLIO.sub("", str(x)) for x in p["registro"]]
    return {**p, "test": t, "registro": reg}


# ═══════════════════════════ da un lavoro vero ═══════════════════════════

class SviluppoAmbiguo(Exception):
    """Senza l'ora del lavoro più sviluppi lo contengono: si sceglie con --sviluppo."""


def precedenza(nome: str) -> tuple:
    """L'ordine dei file sotto il tetto: il manifesto, il codice, i test, poi il resto."""
    b = Path(nome).name.lower()
    test = b.endswith((".test.js", "_test.py")) or (b.startswith("test") and b.endswith(".py"))
    codice = b.endswith((".js", ".mjs", ".cjs", ".ts", ".py", ".cs"))
    return (0 if b == "manifesto.json" else 2 if test else 1 if codice else 3, nome)


def per_revisore(file: dict) -> tuple[dict, list[str]]:
    """I file da mostrare di un lavoro vero, già senza commenti: senza CARTELLE_ESCLUSE, al più
    MAX_FILE caratteri per file e MAX_FILE_TOTALE in tutto, prima il manifesto, il codice e i
    test (`precedenza`). I commenti si tolgono prima di tagliare, così il marcatore del taglio
    non finisce dentro un commento; gli avvisi dicono cosa è stato tagliato o tolto."""
    out, avvisi, totale = {}, [], 0
    for n in sorted(file, key=precedenza):
        if n.split("/")[0] in CARTELLE_ESCLUSE or Path(n).name in ESCLUSI:
            continue
        t = senza_commenti(n, file[n])
        if totale >= MAX_FILE_TOTALE:
            avvisi.append(f"{n} tolto: il pacchetto ha già {MAX_FILE_TOTALE} caratteri di file")
            continue
        tetto = min(MAX_FILE, MAX_FILE_TOTALE - totale)
        if len(t) > tetto:
            avvisi.append(f"{n} tagliato a {tetto} caratteri su {len(t)}")
            t = t[:tetto] + "\n" + TAGLIATO
        out[n] = t
        totale += len(t)
    return out, avvisi


def file_lavoro(cartella: Path) -> dict:
    out = {}
    for p in sorted(Path(cartella).rglob("*")):
        rel = p.relative_to(cartella)
        if (not p.is_file() or p.name in ESCLUSI
                or any(x.startswith(".") or x == "__pycache__" for x in rel.parts)):
            continue
        try:
            out[rel.as_posix()] = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return out


def requisiti_lavoro(cfg, cartella: Path, sviluppo: str = "") -> tuple[list, str, str]:
    """(requisiti, richiesta, da dove) del lavoro: lo sviluppo che lo contiene in
    sviluppi.json (accanto alle sandbox), scelto da `sviluppo` o dal numero del lavoro e
    dall'ora; altrimenti la richiesta di lavoro.json."""
    meta = {}
    p = Path(cartella) / "lavoro.json"
    if p.is_file():
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    ident = str(meta.get("id") or "")
    quando = None
    m = re.match(r"^(L\d+)-(\d{8}-\d{6})", Path(cartella).name)
    if m:
        ident = ident or m.group(1)
        quando = datetime.datetime.strptime(m.group(2), "%Y%m%d-%H%M%S").timestamp()
    elif meta.get("inizio"):
        try:
            quando = datetime.datetime.fromisoformat(meta["inizio"]).timestamp()
        except ValueError:
            pass
    try:
        from calliope.agenti.servizio import cartella_sandbox
        from calliope.sviluppo import FILE
        dati = json.loads((cartella_sandbox(cfg) / FILE).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — niente sviluppi: resta la richiesta
        dati = {}
    scelto, dist, candidati = None, None, []
    for sv in dati.get("sviluppi") or []:
        if sviluppo:
            if sv.get("id") == sviluppo:
                scelto = sv
                break
            continue
        for x in sv.get("lavori") or []:
            if x.get("id") != ident:
                continue
            candidati.append(sv)
            if quando is None:
                continue
            d = abs(float(x.get("creato") or 0) - quando)
            if d < 86400 and (dist is None or d < dist):
                scelto, dist = sv, d
    if not sviluppo and quando is None:
        # Senza l'ora gli id dei lavori si ripetono dopo un riavvio: non si sceglie a caso
        ids = list(dict.fromkeys(str(sv.get("id")) for sv in candidati))
        if len(ids) > 1:
            raise SviluppoAmbiguo(f"il lavoro {ident} è in più sviluppi ({', '.join(ids)}) e "
                                  "la cartella non dice l'ora: scegli con --sviluppo")
        scelto = candidati[0] if candidati else None
    if scelto and scelto.get("requisiti"):
        req = [str(r.get("testo") or "") + (f" — {r['dettaglio']}" if r.get("dettaglio") else "")
               + ("" if r.get("si_puo", True) else " [qui non si può: non va fatto]")
               for r in scelto["requisiti"] if r.get("testo")]
        return req, "", f"sviluppo {scelto.get('id')}"
    return [], str(meta.get("compito") or "")[:1500], "lavoro.json" if meta else "nessuno"


def registro_da_file(percorso: str | None) -> list:
    if not percorso:
        return []
    t = Path(percorso).expanduser().read_text(encoding="utf-8")
    try:
        d = json.loads(t)
        return [x if isinstance(x, (str, dict)) else str(x) for x in d] if isinstance(
            d, list) else [str(d)]
    except ValueError:
        return [r.strip() for r in t.splitlines() if r.strip()]


def caso_da_lavoro(cfg, sbx: Sandboxes, args) -> tuple[dict, dict, str]:
    cartella = Path(args.da_lavoro).expanduser()
    file = file_lavoro(cartella)
    req, richiesta, da = requisiti_lavoro(cfg, cartella, args.sviluppo or "")
    r = sbx.test(file)
    mostrati, avvisi = per_revisore(file)
    p = pacchetto(cfg, req, file, r, registro_da_file(args.registro), richiesta, mostrati,
                  avvisi)
    atteso = {"verdetto": args.atteso}
    if args.file_atteso:
        atteso["file"] = args.file_atteso
    if args.test_atteso:
        atteso["test"] = args.test_atteso
    return p, {"atteso": atteso, "contrario": False}, da


# ═══════════════════════════ la misura ═══════════════════════════

def _uguale(dato: str, atteso: str) -> bool:
    a, d = str(atteso or "").strip().lower(), str(dato or "").strip().lower()
    return bool(a) and bool(d) and (a in d or d.endswith(a) or Path(d).name == Path(a).name)


def giudica(risposta: dict | None, atteso: dict) -> dict:
    """{verdetto, file, test}: True/False, None dove il caso non dice cosa aspettarsi."""
    if not isinstance(risposta, dict):
        return {"verdetto": False, "file": False if atteso.get("file") else None,
                "test": False if atteso.get("test") else None}
    return {"verdetto": risposta.get("verdetto") == atteso["verdetto"],
            "file": _uguale(risposta.get("file"), atteso["file"]) if atteso.get("file")
            else None,
            "test": _uguale(risposta.get("test"), atteso["test"]) if atteso.get("test")
            else None}


def una_passata(svc, p: dict, ragionamento: int, temperatura: float, tempo_s: float) -> dict:
    from calliope.requisiti import chiama
    uso: dict = {}
    t0 = time.monotonic()
    dati, esito = chiama(svc, SISTEMA, messaggio(p), schema(), tempo_s, dalla_voce=False,
                         num_predict=700, ragionamento=ragionamento, uso=uso,
                         temperatura=temperatura)
    return {"risposta": dati, "esito": esito, "s": round(uso.get("s") or
                                                          (time.monotonic() - t0), 1),
            "token": int(uso.get("eval") or 0), "prompt": int(uso.get("prompt") or 0),
            "ragionamento_token": int(uso.get("ragionamento_token") or 0),
            "ragionamento_caratteri": int(uso.get("ragionamento") or 0)}


def misura(svc, pacchetti: dict, info: dict, ripetizioni: int, ragionamento: int,
           temperatura: float, tempo_s: float, scrivi=None, log=print) -> list[dict]:
    righe = []
    for rip in range(ripetizioni):
        for nome, p in pacchetti.items():
            atteso = info[nome]["atteso"]
            r = una_passata(svc, p, ragionamento, temperatura, tempo_s)
            g = giudica(r["risposta"], atteso)
            riga = {"caso": nome, "ripetizione": rip + 1, "atteso": atteso,
                    "contrario": info[nome]["contrario"], "giusto": g, **r}
            righe.append(riga)
            v = (r["risposta"] or {}).get("verdetto") if r["risposta"] else r["esito"]
            log(f"{'ok ' if g['verdetto'] else 'NO '} {nome} #{rip + 1}: {v} "
                f"(atteso {atteso['verdetto']})"
                + (f", file {(r['risposta'] or {}).get('file')!r}" if atteso.get("file") else "")
                + f", {r['s']} s, {r['token']} token")
            if scrivi:
                scrivi(righe)
    return righe


def conti(righe: list[dict]) -> dict:
    """Per caso: verdetti giusti, file e test giusti su N, secondi e token medi."""
    out: dict = {}
    for nome in dict.fromkeys(x["caso"] for x in righe):
        rr = [x for x in righe if x["caso"] == nome]
        c = {"n": len(rr), "contrario": rr[0]["contrario"],
             "atteso": rr[0]["atteso"]["verdetto"],
             "verdetti": sum(bool(x["giusto"]["verdetto"]) for x in rr),
             "dati": [((x["risposta"] or {}).get("verdetto") or x["esito"]) for x in rr],
             "s": round(statistics.mean(x["s"] for x in rr), 1),
             "token": round(statistics.mean(x["token"] for x in rr)),
             "ragionamento_token": round(statistics.mean(x["ragionamento_token"] for x in rr))}
        for k in ("file", "test"):
            if rr[0]["atteso"].get(k):
                c[k] = sum(bool(x["giusto"][k]) for x in rr)
        out[nome] = c
    return out


def criterio(c: dict) -> dict:
    """Il criterio di #182: ≥ 4/5 (la stessa frazione con altri N) su ogni caso e contrario."""
    ok = {n: x["verdetti"] >= 0.8 * x["n"] for n, x in c.items()}
    casi_ok = all(v for n, v in ok.items() if not c[n]["contrario"])
    contrari_ok = all(v for n, v in ok.items() if c[n]["contrario"])
    return {"per_caso": ok, "casi": casi_ok, "contrari": contrari_ok,
            "revisore": casi_ok and contrari_ok}


def tabella(c: dict):
    print(f"\n{'caso':<18} {'atteso':<17} {'verdetti':>8} {'file':>5} {'test':>5} "
          f"{'s':>6} {'token':>6} {'ragion.':>7}  dati")
    for nome, x in c.items():
        n = x["n"]
        print(f"{nome + (' (c)' if x['contrario'] else ''):<18} {x['atteso']:<17} "
              f"{x['verdetti']:>3}/{n:<4} "
              f"{(str(x['file']) + '/' + str(n)) if 'file' in x else '—':>5} "
              f"{(str(x['test']) + '/' + str(n)) if 'test' in x else '—':>5} "
              f"{x['s']:>6} {x['token']:>6} {x['ragionamento_token']:>7}  "
              + ", ".join(str(d) for d in x["dati"]))
    k = criterio(c)
    print(f"\nCriterio di #182 (≥ 4/5): casi {'sì' if k['casi'] else 'no'}, contrari "
          f"{'sì' if k['contrari'] else 'no'} → "
          + ("il revisore a contesto pulito si costruisce con questo modello" if k["revisore"]
             else "sotto il criterio: un modello diverso (#175) o il revisore non vale"))


# ═══════════════════════════ a secco ═══════════════════════════

def secco() -> int:
    from calliope.config import Config
    errori = [0]

    def verifica(nome, ok, dettaglio=""):
        errori[0] += not ok
        print(f"{'ok ' if ok else 'ERR'} {nome}" + ("" if ok else f"  {dettaglio}"))

    # 1. i commenti tolti, le righe al loro posto, stringhe e regex intatte
    js = ('const a = "http://x.it/y"; // Musica: fatto\n/* blocco\n   su due righe */ '
          'const r = /\\/\\/ non commento/g;\nconst t = `// nel template`;\n'
          'if (a) return x / 2; // Punteggio: fatto\n')
    s = senza_commenti_js(js)
    verifica("JavaScript senza commenti: tolti «// Musica: fatto», il blocco e «Punteggio»",
             "Musica" not in s and "blocco" not in s and "Punteggio" not in s, repr(s))
    verifica("…con le stringhe, i template, le regex e la divisione intatti e le righe al loro "
             "posto", '"http://x.it/y"' in s and "/\\/\\/ non commento/g" in s
             and "`// nel template`" in s and "x / 2" in s
             and s.count("\n") == js.count("\n"), repr(s))
    py = ('"""Modulo: fatto tutto."""\nimport os  # Musica: fatta\n\n\ndef f():\n'
          '    """Fa tutto."""\n    return "# non commento"\n')
    s = senza_commenti_py(py)
    verifica("Python senza commenti né docstring, la stringa con # intatta, le righe al loro "
             "posto", "Musica" not in s and "Fa tutto" not in s and "fatto tutto" not in s
             and '"# non commento"' in s and s.count("\n") == py.count("\n")
             and compile(s, "x", "exec") is not None, repr(s))

    cfg = Config()
    tmp = Path(tempfile.mkdtemp(prefix="banco-revisore-secco-"))
    try:
        sbx = Sandboxes(cfg, tmp / "sb", modo="locale")
        if not sbx.pronte:
            print("SALTATO: node non c'è (i casi fissi sono giochi)")
            return SALTATO
        # 2. i casi con l'uscita vera
        tutti = casi()
        pac = {n: prepara(cfg, sbx, c) for n, c in tutti.items()}
        attesi_verdi = {"consegna"}
        for n, p in pac.items():
            verde = p["_risultato"]["passano"]
            verifica(f"{n}: i test {'verdi' if n in attesi_verdi else 'rossi'} davvero",
                     verde == (n in attesi_verdi), p["_risultato"]["uscita"][-500:])
        u = pac["tris-inizia"]["test"]
        verifica("tris-inizia: l'uscita vera dice la fase «preparazione» e «Inizia», nei "
                 "fallimenti in breve", "preparazione" in u["fallimenti"]
                 and "Inizia" in u["fallimenti"] and "gioco.test.js" in u["fallimenti"],
                 u["fallimenti"])
        u = pac["tris-inizia"]["test"]["fallimenti"]
        verifica("tris-inizia: l'errore vero ha il consiglio «correggi il test, non il "
                 "manifesto» (quello che tris-inizia-muto toglie)",
                 bool(CONSIGLIO.search(u)) and "correggi il test" in u, u)
        mm = messaggio(pac["tris-inizia-muto"])
        m = mm[mm.index("# ESITO DEI TEST"):]
        verifica("tris-inizia-muto: senza il consiglio nell'esito dei test (il contratto resta "
                 "quello dell'agente), con la fase e i comandi attivi, e lo "
                 "stesso errore per il resto", "correggi il test" not in m
                 and "prima delle mosse" not in m and "apriGioco({ inizia" not in m
                 and "fase «preparazione», attivi:" in m
                 and pac["tris-inizia-muto"]["test"]["fallimenti"]
                 == CONSIGLIO.sub("", pac["tris-inizia"]["test"]["fallimenti"]),
                 pac["tris-inizia-muto"]["test"]["fallimenti"])
        u = pac["porte-disegno"]["test"]["fallimenti"]
        verifica("porte-disegno: l'errore dice «avanti» non attivo", "avanti" in u, u)
        u = pac["codice_sbagliato"]["test"]["fallimenti"]
        verifica("codice_sbagliato: il test del disegno vede la Caramella al posto del "
                 "Fantasmino", "Fantasmino" in u and "Caramella" in pac["codice_sbagliato"][
                     "test"]["uscita"], u)
        u = pac["consegna"]["test"]["uscita"]
        verifica("consegna: verdi anche la prova di fumo e i test del disegno",
                 "ok prova di fumo" in u and "ok tre in fila vince" in u
                 and "ok con la griglia piena" in u, u[-600:])
        reg = pac["cambia_strada"]["registro"]
        verifica("cambia_strada: cinque tentativi A-B-A-B-A, lo stesso errore vero a ogni "
                 "tentativo", len(reg) == 5 and len({x["esito"] for x in reg}) == 1
                 and "Fantasmino" in reg[0]["esito"], json.dumps(reg, ensure_ascii=False))
        verifica("chiedi_persona: il test dell'agente chiede un punto per la caramella e "
                 "fallisce", "+1 punt" in pac["chiedi_persona"]["test"]["fallimenti"]
                 or "caramella" in pac["chiedi_persona"]["test"]["fallimenti"],
                 pac["chiedi_persona"]["test"]["fallimenti"])
        # 3. il pacchetto: senza commenti, mai la trascrizione
        m = messaggio(pac["tris-inizia"])
        verifica("il pacchetto del tris senza i commenti di logica.js (come «Il computer: "
                 "vince se può») e con il contratto del gioco",
                 "Il computer: vince" not in m and "Le regole senza DOM" not in m
                 and "Contratto delle capacità (gioco)" in m and "preparazione" in m)
        verifica("…senza il runtime né CAPACITA.md, con le righe numerate",
                 "calliope_estensione.py" not in m and "  1| " in m)
        lav = tmp / "L3-20261018-170200"
        lav.mkdir()
        for n, t in file_tris(GIOCO_TEST_TRIS_SENZA_INIZIA).items():
            (lav / n).write_text(t.replace("const LINEE",
                                           "// Musica: fatto\nconst LINEE"), encoding="utf-8")
        (lav / ".calliope").mkdir()
        (lav / ".calliope" / "passo-4.txt").write_text("TRASCRIZIONE-DELL-AGENTE",
                                                       encoding="utf-8")
        (lav / "lavoro.json").write_text(json.dumps(
            {"id": "L3", "compito": "il tris per due", "riassunto": "RIASSUNTO-DELL-AGENTE"}),
            encoding="utf-8")
        (lav / "CAPACITA.md").write_text("CONTRATTO-COPIATO", encoding="utf-8")
        (lav / "risultato.md").write_text("TESTO-DEL-RISULTATO", encoding="utf-8")
        (lav / "esempi_veri").mkdir()
        (lav / "esempi_veri" / "x_1.json").write_text('"RISPOSTA-VERA"', encoding="utf-8")
        (lav / "dati.txt").write_text("riga di dati\n" * 2000, encoding="utf-8")
        for i in range(1, 6):
            (lav / f"aaa{i}.txt").write_text("d" * 11_000, encoding="utf-8")
        # Un commento a blocchi a cavallo del tetto: il marcatore resta dopo il taglio
        (lav / "lungo.js").write_text("const a = 1;\n" * 900 + "/* COMMENTO-TAGLIATO "
                                      + "x" * 3000 + " */\n" + "const b = `t`;\n" * 200,
                                      encoding="utf-8")
        sv = tmp / "sandbox"
        sv.mkdir()
        (sv / "sviluppi.json").write_text(json.dumps({"sviluppi": [
            {"id": "S7", "requisiti": [{"testo": "Un altro gioco"}],
             "lavori": [{"id": "L3", "creato": time.time() - 30 * 86400}]},
            {"id": "S9", "requisiti": [{"testo": "Il tris per due giocatori fissi"},
                                       {"testo": "La classifica su internet", "si_puo": False}],
             "lavori": [{"id": "L3", "creato": datetime.datetime(2026, 10, 18, 17, 1)
                         .timestamp()}]}]}), encoding="utf-8")
        cfg.agenti_sandbox = str(sv)
        args = SimpleNamespace(da_lavoro=str(lav), sviluppo="", registro=None,
                               atteso="test_sbagliato", file_atteso="gioco.test.js",
                               test_atteso="")
        p, info, da = caso_da_lavoro(cfg, sbx, args)
        m = messaggio(p)
        verifica("--da-lavoro: niente trascrizione, riassunto, lavoro.json, CAPACITA.md copiato "
                 "né commenti", all(x not in m for x in (
                     "TRASCRIZIONE-DELL-AGENTE", "RIASSUNTO-DELL-AGENTE", "CONTRATTO-COPIATO",
                     "Musica")), [x for x in ("TRASCRIZIONE", "RIASSUNTO", "COPIATO",
                                              "Musica") if x in m])
        verifica("--da-lavoro: i requisiti dello sviluppo del lavoro (S9, dall'ora), i test "
                 "rieseguiti adesso", da == "sviluppo S9" and "Il tris per due giocatori" in m
                 and "qui non si può" in m and "preparazione" in m, f"{da} {m[-400:]!r}")
        verifica("--da-lavoro: risultato.md ed esempi_veri/ fuori dal pacchetto, il file lungo "
                 "tagliato con l'avviso", "TESTO-DEL-RISULTATO" not in m
                 and "RISPOSTA-VERA" not in m and "…[tagliato dal banco]" in m
                 and any("lungo.js tagliato" in a for a in p.get("avvisi", []))
                 and "# AVVISI DEL BANCO" in m and "lungo.js tagliato a" in m,
                 p.get("avvisi"))
        verifica("--da-lavoro: sotto il tetto prima il manifesto, il codice e i test (i file "
                 "di dati «aaa» in testa all'alfabeto tolti, con l'avviso nel pacchetto)",
                 all(f"## {n}" in m for n in ("manifesto.json", "logica.js", "gioco.test.js",
                                              "logica.test.js"))
                 and "aaa5.txt tolto" in m and "dati.txt tolto" in m, p.get("avvisi"))
        verifica("--da-lavoro: il taglio dentro un commento lascia il marcatore, senza il "
                 "commento", "## lungo.js" in m and TAGLIATO in m[m.index("## lungo.js"):]
                 and "COMMENTO-TAGLIATO" not in m)
        senza_ora = tmp / "senza-ora"
        shutil.copytree(lav, senza_ora)
        (senza_ora / "lavoro.json").write_text(json.dumps({"id": "L3", "compito": "x"}),
                                               encoding="utf-8")
        try:
            requisiti_lavoro(cfg, senza_ora)
            ambiguo = False
        except SviluppoAmbiguo as e:
            ambiguo = "S7" in str(e) and "S9" in str(e) and "--sviluppo" in str(e)
        verifica("--da-lavoro senza l'ora e con due sviluppi candidati: fermo, chiede "
                 "--sviluppo", ambiguo)
        req, _, da2 = requisiti_lavoro(cfg, senza_ora, "S7")
        verifica("…e con --sviluppo S7 prende quello", da2 == "sviluppo S7"
                 and req == ["Un altro gioco"], da2)
        # 4. il modello finto: verdetti preparati, giusti e sbagliati, contati come devono
        risposte = {
            "tris-inizia": [{"verdetto": "test_sbagliato", "file": "gioco.test.js",
                             "test": "tre in fila vince e prende un punto"},
                            {"verdetto": "codice_sbagliato", "file": "manifesto.json",
                             "test": ""}],
            "tris-inizia-muto": [{"verdetto": "test_sbagliato", "file": "gioco.test.js",
                                  "test": "tre in fila vince"}] * 2,
            "porte-disegno": [{"verdetto": "test_sbagliato", "file": "logica.js",
                               "test": "la porta del fantasmino…"}, None],
            "codice_sbagliato": [{"verdetto": "codice_sbagliato", "file": "logica.js",
                                  "test": "toccando la porta del fantasmino"}] * 2,
            "consegna": [{"verdetto": "consegna", "file": "", "test": ""},
                         {"verdetto": "continua", "file": "", "test": ""}],
            "cambia_strada": [{"verdetto": "cambia_strada", "file": "logica.js", "test": ""},
                              {"verdetto": "cambia_strada", "file": "manifesto.json",
                               "test": ""}],
            "chiedi_persona": [{"verdetto": "test_sbagliato", "file": "gioco.test.js",
                                "test": ""}] * 2,
        }
        corpi: list = []
        ordine = [n for _ in range(2) for n in tutti]
        k = [0]

        def chat(body):
            corpi.append(body)
            nome = ordine[k[0]]
            rip = sum(1 for x in ordine[:k[0]] if x == nome)
            k[0] += 1
            r = risposte[nome][rip]
            if r is None:
                return {"content": "non è JSON", "eval": 5, "prompt": 100}
            return {"content": json.dumps({"riga": 0, "causa": "c", "azione": "a", **r}),
                    "eval": 300, "prompt": 7000, "ragionamento": 200, "thinking": "x" * 50}
        svc = SimpleNamespace(cliente=SimpleNamespace(chat=chat), cfg=cfg,
                              imp=SimpleNamespace(modello="revisore-finto"))
        pubblici = {n: {k2: v for k2, v in p.items() if not k2.startswith("_")}
                    for n, p in pac.items()}
        righe = misura(svc, pubblici, tutti, 2, 4096, 0.6, 30, log=lambda *_: None)
        c = conti(righe)
        attesi = {"tris-inizia": (1, 1, 1), "tris-inizia-muto": (2, 2, 2),
                  "porte-disegno": (1, 0, 1),
                  "codice_sbagliato": (2, 2, 2), "consegna": (1, None, None),
                  "cambia_strada": (2, 1, None), "chiedi_persona": (0, None, None)}
        for n, (v, f, t) in attesi.items():
            x = c[n]
            verifica(f"modello finto, {n}: verdetti {v}/2" + (f", file {f}/2" if f is not None
                                                              else "")
                     + (f", test {t}/2" if t is not None else ""),
                     x["verdetti"] == v and x.get("file") == f and x.get("test") == t,
                     json.dumps(x, ensure_ascii=False))
        verifica("modello finto: la risposta che non è JSON conta come sbagliata, con l'esito",
                 c["porte-disegno"]["dati"][1].startswith("errore"), c["porte-disegno"]["dati"])
        b = corpi[0]
        verifica("la passata: schema chiuso con l'enum dei verdetti, ragionamento con il suo "
                 "budget, la temperatura data, solo sistema e pacchetto",
                 b["format"]["properties"]["verdetto"]["enum"] == list(VERDETTI)
                 and b["think"] is True and b.get("thinking_budget") == 4096
                 and b["options"]["temperature"] == 0.6
                 and [x["role"] for x in b["messages"]] == ["system", "user"],
                 json.dumps({k2: v for k2, v in b.items() if k2 != "messages"})[:400])
        verifica("token e secondi nella riga (anche di ragionamento)",
                 c["tris-inizia"]["token"] == 300
                 and c["tris-inizia"]["ragionamento_token"] == 200)
        k2 = criterio(c)
        verifica("criterio di #182: con questi verdetti né i casi né i contrari passano",
                 not k2["casi"] and not k2["contrari"] and k2["per_caso"]["codice_sbagliato"])
        uscita = tmp / "uscita"
        uscita.mkdir()
        scrivi_riepilogo(uscita, "revisore-finto", 2, 4096, 0.6, list(tutti), righe, 0.0,
                         "secco")
        rr = json.loads((uscita / "riepilogo.json").read_text(encoding="utf-8"))
        verifica("riepilogo.json con i conti per caso, il criterio e le righe",
                 rr["conti"]["codice_sbagliato"]["verdetti"] == 2 and len(rr["righe"]) == 14
                 and "criterio" in rr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("TUTTO OK" if not errori[0] else f"{errori[0]} ERRORI"))
    return 1 if errori[0] else 0


def scrivi_riepilogo(uscita: Path, modello: str, ripetizioni: int, ragionamento: int,
                     temperatura: float, scelti: list, righe: list, t0: float, sandbox: str):
    c = conti(righe)
    r = {"revisore": modello, "data": datetime.datetime.now().isoformat(timespec="seconds"),
         "ripetizioni": ripetizioni, "ragionamento": ragionamento, "temperatura": temperatura,
         "casi": scelti, "sandbox": sandbox,
         "minuti": round((time.time() - t0) / 60, 1) if t0 else 0.0,
         "conti": c, "criterio": criterio(c), "righe": righe}
    (uscita / "riepilogo.json").write_text(json.dumps(r, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return r


# ═══════════════════════════ main ═══════════════════════════

def main(argv) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Banco del revisore a contesto pulito (#182)")
    ap.add_argument("--secco", action="store_true", help="solo il controllo del banco, con un "
                    "modello finto")
    ap.add_argument("--ripetizioni", type=int, default=5)
    ap.add_argument("--casi", default=",".join(CASI))
    ap.add_argument("--ragionamento", type=int, default=4096, help="token di ragionamento "
                    "della passata (0 = spento)")
    ap.add_argument("--temperatura", type=float, default=None, help="di serie quella "
                    "dell'agente (agenti_temperatura)")
    ap.add_argument("--tempo", type=float, default=300.0, help="secondi al più per passata")
    ap.add_argument("--sandbox", default="auto", choices=("auto", "vera", "locale"),
                    help="dove si eseguono i test: la sandbox della Config, il Node della "
                    "macchina, o la prima che c'è")
    ap.add_argument("--da-lavoro", help="la cartella di un lavoro vero (sandbox o risultati): "
                    "il pacchetto costruito da lì, al posto dei casi fissi")
    ap.add_argument("--atteso", choices=VERDETTI, help="con --da-lavoro: il verdetto atteso")
    ap.add_argument("--file-atteso", default="")
    ap.add_argument("--test-atteso", default="")
    ap.add_argument("--sviluppo", default="", help="con --da-lavoro: lo sviluppo dei requisiti "
                    "(S32), se non si trova da solo")
    ap.add_argument("--registro", help="con --da-lavoro: un registro dei tentativi (JSON o una "
                    "riga per tentativo)")
    ap.add_argument("--uscita")
    args = ap.parse_args(argv)
    if args.secco:
        return secco()
    if args.da_lavoro and not args.atteso:
        ap.error("--da-lavoro vuole --atteso")
    from calliope.agenti import carica
    from calliope.agenti.remoto import crea_cliente
    from calliope.config import load_config
    cfg = load_config()
    imp = carica(cfg)
    if imp is None:
        print("Nessun agente configurato in questa cartella (serve la configurazione di "
              "Calliope con l'agente).")
        return 1
    temperatura = (float(cfg.agenti_temperatura) if args.temperatura is None
                   else args.temperatura)
    uscita = Path(args.uscita).expanduser() if args.uscita else Path(
        tempfile.mkdtemp(prefix="banco-revisore-"))
    uscita.mkdir(parents=True, exist_ok=True)
    sbx = Sandboxes(cfg, uscita / "sandbox", args.sandbox)
    if not sbx.pronte:
        print(f"SALTATO: i test non si possono eseguire ({sbx.descrizione})")
        return SALTATO
    # Solo il cliente del motore dell'agente: niente servizio dei lavori, niente coda
    svc = SimpleNamespace(cliente=crea_cliente(imp), imp=imp, cfg=cfg)
    if args.da_lavoro:
        try:
            p, info, da = caso_da_lavoro(cfg, sbx, args)
        except SviluppoAmbiguo as e:
            print(f"Fermo: {e}.")
            return 2
        for a in p.get("avvisi") or []:
            print(f"   avviso: {a}")
        nome = "lavoro:" + Path(args.da_lavoro).name
        pacchetti, infos = {nome: p}, {nome: info}
        print(f"Dal lavoro {args.da_lavoro}: {len(p['file'])} file, requisiti da {da}, test "
              f"{p['test']['esito']}; pacchetto di {len(messaggio(p))} caratteri")
    else:
        tutti = casi()
        scelti = [c.strip() for c in args.casi.split(",") if c.strip()]
        ignoti = [c for c in scelti if c not in tutti]
        if ignoti:
            ap.error(f"casi che non ci sono: {ignoti} (ci sono: {list(tutti)})")
        pacchetti, infos = {}, {}
        for n in scelti:
            p = prepara(cfg, sbx, tutti[n])
            p.pop("_risultato", None)
            pacchetti[n], infos[n] = p, tutti[n]
            print(f"   {n}: test {p['test']['esito']}", flush=True)
    print(f"Banco del revisore: {imp.modello}, ragionamento {args.ragionamento}, temperatura "
          f"{temperatura:g}, {args.ripetizioni} ripetizioni, casi {list(pacchetti)}; test con "
          f"{sbx.descrizione}; risultati in {uscita}", flush=True)
    (uscita / "pacchetti.json").write_text(json.dumps(
        {n: messaggio(p) for n, p in pacchetti.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    t0 = time.time()

    def scrivi(righe):
        (uscita / "righe.json").write_text(json.dumps(righe, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    righe = misura(svc, pacchetti, infos, args.ripetizioni, args.ragionamento, temperatura,
                   args.tempo, scrivi=scrivi, log=lambda m: print(m, flush=True))
    tabella(conti(righe))
    r = scrivi_riepilogo(uscita, imp.modello, args.ripetizioni, args.ragionamento,
                         temperatura, list(pacchetti), righe, t0, sbx.descrizione)
    print(f"\nRiepilogo in {uscita / 'riepilogo.json'} ({r['minuti']} minuti)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
