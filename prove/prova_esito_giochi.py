"""Prova a secco dell'esito dei giochi e degli esempi di accettazione del tris (20/10/2026, issue
#197; area docs/aree/giochi.md).

Il caso vero: banco tris2 della DGX del 20/10 sera. L3: la logica dava `esito: "Mossa
effettuata"` a ogni casella (per il motore vuol dire «la mano è finita»), con il contratto che
diceva «esito di ogni mossa»; l'analisi prima del codice aveva 0 esempi senza dire perché. L1 e
L5: gli esempi di accettazione, giocati sul tris di riferimento (prove/giochi/tris), cadevano
tutti (11 su 11): «fase esito» dopo una mossa normale (il prompt del progettista dei test lo
metteva «dopo ogni mossa»), parole sullo schermo scelte dal modello («ok», «Vittoria»), il
pareggio «1, 2, …, 9» che vince alla 7ª mossa, due esempi che si contraddicono.

1. **I testi**: contratto, prompt del progettista dei test, capacità del gioco, vincolo della
   correzione e file di partenza non dicono più «esito di ogni mossa» e dicono che l'esito c'è
   solo quando una mano finisce; il contesto della mossa spiegato (tocca la posizione, turno il
   giro, giocatori un elenco; in nuovaPartita il numero; in g.stato() tocca il nome) e misurato
   sul motore vero.
2. **L'avviso della prova di fumo** (fumo_js.mjs `avvisoEsito`, test_js.mjs): una logica con
   l'esito a ogni mossa passa con la riga «AVVISO prova di fumo del gioco: …»; contrari: il tris
   giusto, le porte delle prove (un esito senza punti una volta su quattro) e il gioco di
   partenza (un punto a ogni porta) senza avviso; la soglia (più della metà, o la prima mossa di
   ogni partita); la riga è quella che il ciclo dell'agente conta (`AVVISO_ESITO`).
3. **Gli esempi del tris** (accettazione.interpreta con la richiesta): gli esempi veri di L1 e
   L5 filtrati (testo che la richiesta non usa, «esito» senza punti, più di 7 mosse, due esempi
   che si contraddicono) con il conto per causa in «tolti» e «esempi_modello»; i rimasti verdi
   sul tris giusto (se c'è node); contrari: un testo della richiesta resta, «esito» con i punti
   resta, senza la richiesta il testo resta.
4. **Nel servizio**: tutti gli esempi tolti → la regola accettazione_esempi_tutti_tolti nel
   registro con le cause; contrario: con un esempio tenuto niente regola.

    python prove/prova_esito_giochi.py
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_agente_guida as G  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
GIOCHI = RADICE / "prove" / "giochi"
errori = 0
T0 = time.perf_counter()

# La richiesta del caso tris2 del banco (prove/manuali/banco_temperatura.py)
RICHIESTA = (
    "Il gioco del tris per due giocatori sugli schermi (nome tris_due): sempre esattamente due "
    "giocatori, che a turno mettono X e O su una griglia 3×3 toccando una casella o dicendo "
    "«casella N» (il comando si chiama casella, con N da 1 a 9, da sinistra a destra e "
    "dall'alto in basso). Chi mette tre segni in fila (riga, colonna o diagonale) vince e prende "
    "un punto; con la griglia piena è pareggio; poi si può giocare ancora.")
REQUISITI = [{"testo": "Due giocatori, sempre esattamente due"},
             {"testo": "Griglia 3×3: a turno si mette X o O"},
             {"testo": "Tre segni in fila vincono e danno un punto"},
             {"testo": "Con la griglia piena senza tre in fila è pareggio"},
             {"testo": "Finita la partita si può giocare ancora"}]
TESTO = " ".join([RICHIESTA] + [r["testo"] for r in REQUISITI])


def _e(req, mosse, **atteso):
    return {"requisito": req, "giocatori": 2,
            "mosse": [{"comando": "casella", "valore": v} for v in mosse], "atteso": atteso}


TUTTE = list(range(1, 10))
# Gli esempi veri di L1 e L5 (banco del 20/10 sera, accettazione.test.js dei due lavori)
L1 = [_e(2, [1], fase="esito", testo="ok"), _e(2, [1, 2], fase="esito", testo="ok"),
      _e(3, [1, 2, 3], fase="esito", testo="ok"),
      _e(3, [1, 2, 3, 4, 5, 6], fase="fine", punti=[1, 0]),
      _e(4, TUTTE, fase="fine", punti=[0, 0], testo="Pareggio"),
      _e(5, TUTTE, fase="fine", testo="Nuova")]
L5 = [_e(2, [5], fase="esito", testo="X"), _e(2, [5, 1], fase="esito", testo="O"),
      _e(3, [1, 2, 4, 5, 7], fase="fine", punti=[1, 0], testo="Vittoria"),
      _e(4, TUTTE, fase="fine", punti=[0, 0], testo="Pareggio"),
      _e(5, TUTTE, testo="Nuova")]


def analisi(esempi):
    return {"contraddizioni": [], "scelte": [], "al_collaudo": [],
            "giocatori": {"min": 2, "max": 2},
            "comandi": [{"fase": "turno", "nome": "casella", "da": 1, "a": 9}],
            "esempi": esempi}


def sezione(nome):
    print(f"\n── {nome} ──")


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("ok  " if ok else "ERR ") + nome + ("" if ok else f"\n     {dettaglio}"))
    errori += not ok


# ═══════════════════════════ 1. i testi ═══════════════════════════

def prova_testi():
    sezione("1. i testi non dicono più «esito di ogni mossa»")
    from calliope.agenti import accettazione as acc
    from calliope.agenti import scheletri
    from calliope.estensioni import contratto
    from calliope.requisiti import CAPACITA_GIOCO
    from calliope.tools.sviluppo import VINCOLO_CORREZIONE_GIOCO
    righe = " ".join(contratto.scheda_testo()) + " " + contratto.testo(tipo="gioco")
    testi = {"contratto": righe, "progettista dei test": acc.SISTEMA_GIOCO,
             "capacità del gioco": CAPACITA_GIOCO, "vincolo della correzione":
             VINCOLO_CORREZIONE_GIOCO, "logica di partenza": scheletri.LOGICA_PARTENZA}
    for nome, t in testi.items():
        verifica(f"{nome}: niente «esito di ogni mossa» né «dopo ogni mossa … esito»",
                 "esito di ogni mossa" not in t and "dopo ogni mossa di solito" not in t
                 and "«esito» delle mosse" not in t, t[:200])
    c = righe
    verifica("il contratto dice che l'esito c'è solo quando una mano finisce e che una mossa "
             "normale resta nella fase con { dati }",
             "L'ESITO C'È SOLO QUANDO UNA " in c and "MANO FINISCE" in c
             and "restituisce { dati } (e i punti, se ci sono)" in c)
    verifica("il progettista dei test: la fase «esito» solo quando una mano finisce, mai dopo "
             "una mossa normale; le mosse a turno; al più 7",
             "c'è solo quando una mano finisce" in acc.SISTEMA_GIOCO
             and "mai «esito»" in acc.SISTEMA_GIOCO and "A TURNO" in acc.SISTEMA_GIOCO
             and "Al più 7 mosse" in acc.SISTEMA_GIOCO)
    # Il contesto della mossa (analisi della macchina, PR #200; banco tris2 L5: i test chiamavano
    # nuovaPartita({ giocatori: ["G1", "G2"] }), un elenco, e la logica non aveva giocatori:
    # «TypeError … 'punti'» a logica.js:62; e teneva un suo indice del turno che non passava mai)
    verifica("il contratto spiega il contesto della mossa: tocca la posizione (il segno del "
             "tris), turno il giro 1, 1, 2, 2, giocatori un elenco; in nuovaPartita giocatori è "
             "il numero; in g.stato() tocca è il nome",
             "{ valore, tocca, chi, giocatori, turno }" in c
             and "tocca la POSIZIONE di chi muove" in c and "[\"X\", \"O\"][tocca]" in c
             and "turno il GIRO (1, 1, 2, 2…" in c and "giocatori l'ELENCO" in c
             and "qui giocatori è il NUMERO dei giocatori" in c
             and "In g.stato() invece tocca è il NOME" in c, c[:300])
    verifica("il contratto: senza turni, con più giocatori e chi non si sa, un numero di punti "
             "non va a nessuno e la prova di fumo lo avvisa; se vanno a chi muove, i turni",
             "non va a nessuno e chi è null, e la prova di fumo lo avvisa" in c
             and "usa una fase con i turni" in c and "l'elenco, uno per giocatore)" not in c)
    verifica("il contratto: con un giocatore solo turno resta 1, le mosse si contano nei dati",
             "con un giocatore solo resta 1: per contare le mosse tienile nei dati" in c)
    from calliope.agenti import accettazione as A2
    verifica("il progettista dei test: «esito» quando la mano finisce, anche il pareggio, mai "
             "dopo la prima mossa; niente più «esito» solo con i punti",
             "«esito» solo quando la mano finisce (una vittoria, un pareggio, un punto fatto)"
             in A2.SISTEMA_GIOCO and "«esito» solo con i punti" not in A2.SISTEMA_GIOCO)
    verifica("la logica di partenza spiega perché lì c'è l'esito (un punto a ogni porta) e "
             "che una mossa normale restituisce { dati }",
             "un punto fatto, quindi una mano finita" in scheletri.LOGICA_PARTENZA
             and "restituisce solo" in scheletri.LOGICA_PARTENZA)


# ═══════════════════════════ 2. l'avviso della prova di fumo ═══════════════════════════

def _sandbox(tmp: Path, nome: str, file: dict):
    sb = G.sandbox(tmp, nome)
    for k, v in file.items():
        sb.scrivi(k, v)
    return sb


def _cartella(nome: str) -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in (GIOCHI / nome).iterdir()
            if p.is_file()}


def prova_avviso(tmp: Path):
    sezione("2. l'avviso dell'esito a ogni mossa nella prova di fumo")
    from calliope.agenti.ciclo import AVVISO_ESITO
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    tris = _cartella("tris")
    rotto = tris["logica.js"].replace("        return { dati };",
                                      "        return { dati, esito: \"Mossa effettuata\" };")
    verifica("(il tris rotto è diverso dal giusto)", rotto != tris["logica.js"])
    u = _sandbox(tmp, "rotto", {**tris, "logica.js": rotto}).test()["uscita"]
    verifica("il tris con l'esito a ogni casella: la prova di fumo passa con l'avviso",
             "ok prova di fumo del gioco" in u and AVVISO_ESITO in u
             and "l'esito vuol dire che la mano è finita" in u
             and "per una mossa normale restituisci { dati }" in u
             and "anche la prima di ogni partita" in u
             and "GIOCO.mosse.turno.casella → esito «Mossa effettuata»" in u
             and "va nei testi di GIOCO.vista" in u, u[-900:])
    verifica("…l'avviso non è un fallimento: nessuna riga FALLITO della prova di fumo",
             "FALLITO prova di fumo" not in u, u[-600:])
    for nome, file in (("il tris giusto (prove/giochi/tris)", tris),
                       ("le porte delle prove (esito senza punti a volte)",
                        _cartella("porte_fasi"))):
        u = _sandbox(tmp, "giusto_" + nome[:8].replace(" ", "_"), file).test()["uscita"]
        verifica(f"contrario: {nome} senza avviso",
                 "ok prova di fumo del gioco" in u and AVVISO_ESITO not in u, u[-600:])
    from calliope.agenti import scheletri
    for g in ((1, 4), (2, 2)):
        u = _sandbox(tmp, f"partenza_{g[0]}{g[1]}", scheletri.file_gioco(*g)).test()["uscita"]
        verifica(f"contrario: il gioco di partenza delle porte (giocatori {g}) senza avviso",
                 "ok prova di fumo del gioco" in u and AVVISO_ESITO not in u, u[-600:])
    # Il contesto della mossa com'è detto nel contratto, dal motore vero (apriGioco)
    spia = tris["logica.js"].replace(
        "      casella(d, { valore }) {\n        const celle = d.celle.slice();",
        "      casella(d, { valore, tocca, turno, giocatori }) {\n"
        "        const visti = (d.visti || []).concat([[tocca, turno, Array.isArray(giocatori)]]);\n"
        "        d = { ...d, visti };\n        const celle = d.celle.slice();").replace(
        'titolo: "Tris",', 'titolo: "Tris", sottotitolo: JSON.stringify(d.visti || []),')
    corpo = ('const { test } = require("node:test");\nconst assert = require("node:assert");\n'
             'test("contesto", async () => {\n'
             '  const g = await apriGioco({ seme: 1, inizia: true, giocatori: 2 });\n'
             '  for (const n of [1, 2, 3, 4]) await g.comando("casella", n);\n'
             '  console.log("VISTI " + g.testo());\n'
             '  console.log("TOCCA " + JSON.stringify(g.stato().tocca));\n});\n')
    if spia == tris["logica.js"] or "sottotitolo: JSON" not in spia:
        verifica("(la spia del contesto è nella logica)", False, spia[:300])
    else:
        sb = _sandbox(tmp, "contesto", {**tris, "logica.js": spia, "gioco.test.js": corpo})
        u = sb.test(fumo=False)["uscita"]
        verifica("il motore: tocca 0, 1, 0, 1 e turno 1, 1, 2, 2 nelle mosse, giocatori un "
                 "elenco", "[[0,1,true],[1,1,true],[0,2,true],[1,2,true]]" in u.replace(" ", ""),
                 u[-700:])
        verifica("contrario: in g.stato() tocca è il nome («Giocatore 1»), non la posizione",
                 'TOCCA "Giocatore 1"' in u, u[-400:])
    prova_senza_turni(tmp)
    prova_punti_persi(tmp)
    # Nel ciclo dell'agente: la regola nel registro, una volta per lavoro anche con due esecuzioni
    import prova_strumenti_onesti as SO
    esegui = {"name": "esegui_test", "arguments": {}}
    for nome, logica, attese in (("rotto", rotto, 1), ("giusto", tris["logica.js"], 0)):
        sb = _sandbox(tmp, "ciclo_" + nome, {**tris, "logica.js": logica})
        lav, _ris, _log, _cli, _sb = SO.gira(tmp, "ciclo_" + nome, [[esegui], [esegui],
                                                                    [SO.CONSEGNA]], sb=sb)
        n = SO.regole(lav).get("gioco_esito_ogni_mossa", 0)
        verifica(("nel ciclo dell'agente, due esecuzioni dei test: la regola "
                  "gioco_esito_ogni_mossa una volta, e non gioco_punti_persi") if attese else
                 "contrario: il tris giusto nel ciclo, niente regola", n == attese
                 and not SO.regole(lav).get("gioco_punti_persi"), str(SO.regole(lav)))
    # La soglia, sulla funzione da sola
    fumo = (RADICE / "calliope" / "agenti" / "fumo_js.mjs").as_uri()
    casi = {"metà esatta: niente": ({"mosse": 10, "vuoti": 5, "prime": 2, "primeVuote": 1}, False),
            "più della metà": ({"mosse": 10, "vuoti": 6, "prime": 2, "primeVuote": 0}, True),
            "la prima di ogni partita": ({"mosse": 20, "vuoti": 2, "prime": 2, "primeVuote": 2},
                                         True),
            "la prima di una partita sola: niente": (
                {"mosse": 20, "vuoti": 2, "prime": 2, "primeVuote": 1}, False),
            "nessuna mossa: niente": ({"mosse": 0, "vuoti": 0, "prime": 0, "primeVuote": 0},
                                      False)}
    import subprocess
    codice = (f"import {{ avvisoEsito }} from {json.dumps(fumo)};\n"
              f"const casi = {json.dumps({k: v[0] for k, v in casi.items()})};\n"
              "for (const [k, c] of Object.entries(casi)) console.log(k + '=' + "
              "(avvisoEsito(c) ? 1 : 0));\n")
    f = tmp / "soglia.mjs"
    f.write_text(codice, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
    visti = dict(x.split("=") for x in r.stdout.split("\n") if "=" in x)
    for k, (_, atteso) in casi.items():
        verifica(f"la soglia: {k}", visti.get(k) == ("1" if atteso else "0"),
                 r.stdout + r.stderr)


SENZA_TURNI = r"""
import { readFileSync } from "node:fs";
import vm from "node:vm";
const ctx = vm.createContext({ console, JSON, Math });
vm.runInContext(readFileSync(__MOTORE__, "utf8"), ctx);
vm.runInContext(`var GIOCO = {
  nuovaPartita: () => ({ n: 0 }),
  mosse: { gara: { premi: (d, c) => ({ dati: { n: d.n + 1, chi: c.chi }, punti: 1 }),
                   tutti: (d, c) => ({ dati: { n: d.n + 1 }, punti: c.giocatori.map((g, i) => i + 1) }) } },
  vista: { gara: () => ({ titolo: "Gara" }) } };`, ctx);
const fase = (turni) => ({ inizio: "gara", fasi: { gara: { pagina: "scelte", turni, verso: ["fine"],
  comandi: { premi: { forme: ["premi"] }, tutti: { forme: ["tutti"] } } } } });
const G = vm.runInContext("GIOCO", ctx);
const out = {};
const punti = (S) => S.giocatori.map((g) => g.punti);
for (const [nome, turni, voci, mossa] of [
    ["ignoto", false, ["v1", "v2"], {}], ["voce", false, ["v1", "v2"], { voce: "v2" }],
    ["solo", false, ["v1"], {}], ["turni", true, ["v1", "v2"], {}]]) {
  const nu = ctx.CalliopeMotore.crea(G, fase(turni), { min: 1, max: 4 });
  let S = nu.nuovo();
  for (const v of voci) S = nu.applica(S, "anchio", null, { voce: v });
  S = nu.applica(S, "inizia");
  S = nu.applica(S, "premi", null, mossa);
  out[nome] = { punti: punti(S), chi: S.dati.chi };
  if (nome === "ignoto") { S = nu.applica(S, "tutti", null, {}); out.elenco = punti(S); }
}
console.log("ESITO " + JSON.stringify(out));
"""


def prova_senza_turni(tmp: Path):
    """I punti di una mossa in una fase senza turni (revisione dell'analisi della PR #200):
    prima andavano sempre al Giocatore 1 quando non si sapeva chi aveva mosso."""
    import subprocess
    motore = RADICE / "calliope" / "estensioni" / "motore_gioco.js"
    f = tmp / "senza_turni.mjs"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(SENZA_TURNI.replace("__MOTORE__", json.dumps(str(motore))), encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
    riga = next((x for x in r.stdout.splitlines() if x.startswith("ESITO ")), "")
    o = json.loads(riga[6:]) if riga else {}
    verifica("senza turni, due giocatori e chi non si sa: il numero di punti non va a nessuno "
             "(prima al Giocatore 1) e chi è null",
             o.get("ignoto") == {"punti": [0, 0], "chi": None}, r.stdout + r.stderr)
    verifica("…l'elenco dei punti, uno per giocatore, vale lo stesso",
             o.get("elenco") == [1, 2], str(o))
    verifica("contrario: con la voce riconosciuta i punti vanno a chi ha mosso",
             o.get("voce") == {"punti": [0, 1], "chi": "Giocatore 2"}, str(o))
    verifica("contrario: con un giocatore solo i punti sono suoi",
             o.get("solo") == {"punti": [1], "chi": "Giocatore 1"}, str(o))
    verifica("contrario: con i turni i punti vanno a chi è di turno, come prima",
             o.get("turni") == {"punti": [1, 0], "chi": "Giocatore 1"}, str(o))


GARA = """"use strict";
const GIOCO = {
  nuovaPartita: () => ({ n: 0 }),
  attivi: { gara: (d) => ({ premi: d.n < 3 }) },
  mosse: { gara: { premi: (d, c) => ({ dati: { n: d.n + 1 }, __PUNTI__,
                                     ...(d.n + 1 >= 3 ? { fase: "fine" } : {}) }) } },
  vista: { gara: (d) => ({ titolo: "Premi", testo: `Premuto ${d.n} volte` }) },
};
if (typeof module !== "undefined") module.exports = { GIOCO };
"""


TEST_GARA = ('const { test } = require("node:test");\n'
             'const { GIOCO } = require("./logica.js");\n'
             'test("parte", () => GIOCO.nuovaPartita({ giocatori: 2 }));\n')


def prova_punti_persi(tmp: Path):
    """L'avviso dei punti che non vanno a nessuno (revisione della PR #201)."""
    from calliope.agenti.ciclo import AVVISO_ESITO
    for nome, punti, turni, gmax, attesa in (
            ("senza turni, due giocatori, un numero", "punti: 1", False, 2, True),
            ("contrario: con i turni", "punti: 1", True, 2, False),
            ("contrario: senza turni, l'elenco",
             "punti: c.giocatori.map((g, i) => (i ? 0 : 1))", False, 2, False),
            ("contrario: senza turni, un giocatore solo", "punti: 1", False, 1, False)):
        m = {"nome": "gara", "titolo": "Gara", "cosa_fa": {"verbo": "propone",
             "oggetto": "una gara sullo schermo"},
             "input": {"type": "object", "properties": {}, "required": []}, "permessi": {},
             "livello": "familiare",
             "scheda": {"tipo": "gioco", "file": ["logica.js"],
                        "giocatori": {"min": 1, "max": gmax},
                        "macchina": {"inizio": "gara", "fasi": {"gara": {
                            "pagina": "scelte", "turni": turni, "verso": ["fine"],
                            "comandi": {"premi": {"forme": ["premi"]}}}}}}}
        u = _sandbox(tmp, "persi_" + str(abs(hash(nome)) % 10 ** 6), {
            "logica.js": GARA.replace("__PUNTI__", punti),
            "manifesto.json": json.dumps(m),
            "logica.test.js": TEST_GARA,
            }).test()["uscita"]
        dice = AVVISO_ESITO in u and "non vanno a nessuno" in u and '"turni": true' in u
        verifica(f"i punti che non vanno a nessuno: {nome} → "
                 + ("avviso" if attesa else "niente avviso"),
                 "ok prova di fumo del gioco" in u and dice is attesa, u[-700:])
        # La regola sua, nel registro (seconda revisione della PR #201)
        from calliope.agenti.ciclo import regole_avvisi
        verifica(f"…la regola: {nome} → "
                 + ("gioco_punti_persi, e non quella dell'esito" if attesa else "nessuna"),
                 regole_avvisi(u) == (["gioco_punti_persi"] if attesa else []), str(
                     regole_avvisi(u)))


# ═══════════════════════════ 3. gli esempi del tris ═══════════════════════════

def prova_esempi(tmp: Path):
    sezione("3. gli esempi del tris del banco, filtrati")
    from calliope.agenti import accettazione as acc
    an1 = acc.interpreta(analisi(L1), 5, False, True, TESTO)
    verifica("L1: 6 esempi del modello, 3 tenuti; tolti per causa (testo «ok», «esito» senza "
             "punti alla prima mossa, più di 7 mosse, senza niente da controllare)",
             an1["esempi_modello"] == 6 and len(an1["esempi"]) == 3
             and an1["tolti"] == {"lunghi": 2, "niente": 1, "testo": 3,
                                  "esito_prima_mossa": 1}, json.dumps(an1, ensure_ascii=False))
    an5 = acc.interpreta(analisi(L5), 5, False, True, TESTO)
    verifica("L5: 5 del modello, 3 tenuti («X» e «O» sono nella richiesta, «Vittoria» no)",
             an5["esempi_modello"] == 5 and len(an5["esempi"]) == 3
             and an5["tolti"] == {"lunghi": 2, "testo": 1, "esito_prima_mossa": 1}
             and an5["esempi"][0]["atteso"] == {"testo": "X"}
             and an5["esempi"][1]["atteso"] == {"fase": "esito", "testo": "O"}
             and an5["esempi"][2]["atteso"] == {"fase": "fine", "punti": [1, 0]},
             json.dumps(an5, ensure_ascii=False))
    # I due esempi che si contraddicono: «1…6» finisce, «1…7» con le stesse mosse continua
    contr = [_e(3, [1, 2, 3, 4, 5, 6], fase="fine", punti=[1, 0]),
             _e(2, [1, 2, 3, 4, 5, 6, 7], punti=[1, 0]), _e(2, [4], non_attivi=[
                 {"comando": "casella", "valore": 4}])]
    an = acc.interpreta(analisi(contr), 5, False, True, TESTO)
    verifica("due esempi che si contraddicono (uno finisce, l'altro con le stesse mosse "
             "continua): tolti tutti e due, il terzo resta",
             an["tolti"] == {"dopo_la_fine": 2} and len(an["esempi"]) == 1
             and an["esempi"][0]["mosse"] == [["casella", 4]], json.dumps(an["tolti"]))
    an = acc.interpreta(analisi([_e(3, [1, 4, 2, 5, 3], fase="esito", punti=[1, 0],
                                    testo="pareggio"),
                                 _e(3, [1, 4, 2, 5, 3], fase="fine", punti=[1, 0]),
                                 _e(3, [1, 4, 2, 6], fase="turno")]),
                        5, False, True, TESTO)
    verifica("contrari: «esito» con i punti resta, una parola della richiesta resta, uno che "
             "finisce e uno diverso senza le stesse mosse in testa restano",
             len(an["esempi"]) == 3 and an["esempi"][0]["atteso"]["fase"] == "esito"
             and an["esempi"][0]["atteso"]["testo"] == "pareggio" and not an["tolti"],
             json.dumps(an, ensure_ascii=False)[:600])
    an = acc.interpreta(analisi(L1[:1]), 5, False, True)
    verifica("contrario: senza la richiesta il testo resta (le prove di prima)",
             an["esempi"] and an["esempi"][0]["atteso"].get("testo") == "ok"
             and "esito_prima_mossa" in an["tolti"], json.dumps(an, ensure_ascii=False))
    # Dalla revisione della PR #201
    an = acc.interpreta(analisi([_e(3, [1, 4, 2, 5, 3], fase="esito"),
                                 _e(3, [1, 4, 2, 5, 3, 6, 7], non_attivi=[
                                     {"comando": "casella", "valore": 7}]),
                                 _e(3, [1, 4, 2, 5, 3, 6, 7, 8], non_attivi=[
                                     {"comando": "casella", "valore": 8}])]),
                        5, False, True, TESTO)
    verifica("contrari: «1, 4, 2, 5, 3 → esito» senza punti resta (il pareggio e la vittoria "
             "sono esiti), un esempio di 7 mosse resta, di 8 si toglie",
             len(an["esempi"]) == 2 and an["esempi"][0]["atteso"] == {"fase": "esito"}
             and len(an["esempi"][1]["mosse"]) == 7 and an["tolti"] == {"lunghi": 1},
             json.dumps(an, ensure_ascii=False)[:600])
    an = acc.interpreta(analisi([_e(3, [1, 4, 2, 5, 3], testo="vinto"),
                                 _e(3, [1, 4, 2, 5, 3], testo="vince"),
                                 _e(3, [1, 4, 2, 5, 3], testo="Vittoria")]),
                        5, False, True, TESTO)
    verifica("il testo in una forma vicina: «vinto» (sullo schermo) e «vince» (nella richiesta) "
             "restano, «Vittoria» no",
             [e["atteso"].get("testo") for e in an["esempi"]] == ["vinto", "vince"]
             and an["tolti"] == {"testo": 1, "niente": 1}, json.dumps(an, ensure_ascii=False))
    casi = {("vince", "vinto"): True, ("pareggio", "pareggi"): True, ("punto", "punti"): True,
            ("vittoria", "vince"): False, ("ok", "oca"): False, ("x", "x"): True,
            ("turno", "tutti"): False}
    for (a, b), atteso in casi.items():
        verifica(f"simili({a!r}, {b!r}) = {atteso}", acc.simili(a, b) is atteso)
    vicino = acc.interpreta(analisi([_e(3, [1, 4, 2, 5, 3], fase="fine", testo="vince")]),
                            5, False, True, TESTO)
    an = acc.interpreta(analisi([_e(4, TUTTE, testo="pareggio")]), 5, False, True, TESTO)
    verifica("tutti tolti: 0 tenuti con il conto del modello (1) e la causa",
             an["esempi"] == [] and an["esempi_modello"] == 1 and an["tolti"] == {"lunghi": 1})
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    # I tenuti giocati sul tris giusto: prima cadevano tutti e 11
    tris = _cartella("tris")
    m = json.loads(tris["manifesto.json"])
    m["scheda"]["giocatori"] = {"min": 2, "max": 2}
    for nome, a in (("L1", an1), ("L5", an5)):
        sb = _sandbox(tmp, "rif_" + nome, {"logica.js": tris["logica.js"],
                                            "manifesto.json": json.dumps(m)})
        sb.scrivi(acc.FILE_GIOCO, acc.test_js(a))
        r = sb.test(acc.FILE_GIOCO, fumo=False)
        passano, rossi = acc.esito_js(r["uscita"])
        if nome == "L1":
            # Restano sbagliati «1, 2 → esito», «1, 2, 3 → esito» (le mosse non a turno) e
            # «1…6 finisce con un punto» (X ha 1, 3, 5): nessuna regola sul testo li vede
            # senza giocare la partita
            verifica("L1 sul tris giusto: rossi i requisiti 2 e 3 (mosse non a turno)",
                     not passano and rossi == [2, 3], r["uscita"][-600:])
        else:
            verifica("L5 sul tris giusto: rosso solo il requisito 2 («5, 1 → esito»: dopo la "
                     "prima mossa il filtro non lo vede)", not passano and rossi == [2],
                     r["uscita"][-600:])
    sb = _sandbox(tmp, "rif_vince", {"logica.js": tris["logica.js"],
                                     "manifesto.json": json.dumps(m)})
    sb.scrivi(acc.FILE_GIOCO, acc.test_js(vicino))
    r = sb.test(acc.FILE_GIOCO, fumo=False)
    verifica("sullo schermo una forma vicina basta: «vince» atteso, «Ha vinto X!» scritto",
             acc.esito_js(r["uscita"]) == (True, []), r["uscita"][-600:])
    sb.scrivi(acc.FILE_GIOCO, acc.test_js(acc.interpreta(analisi([_e(
        3, [1, 4, 2, 5, 3], fase="fine", testo="pareggio")]), 5, False, True, TESTO)))
    r = sb.test(acc.FILE_GIOCO, fumo=False)
    verifica("contrario: «pareggio» atteso dopo una vittoria resta rosso",
             acc.esito_js(r["uscita"]) == (False, [3]), r["uscita"][-600:])
    # Le parole di seguito (seconda revisione della PR #201): «X» e «O» sono anche nelle caselle
    for mosse, testo, verde in (([1], "Mette O", True), ([1], "Mette X", False),
                                ([1, 4], "Mette X", True), ([1, 4], "Mette O", False)):
        an = acc.interpreta(analisi([_e(2, mosse, testo=testo)]), 5, False, True, TESTO)
        sb.scrivi(acc.FILE_GIOCO, acc.test_js(an))
        r = sb.test(acc.FILE_GIOCO, fumo=False)
        verifica(f"sullo schermo le parole di seguito: {mosse} → «{testo}» "
                 + ("verde" if verde else "rosso (la lettera è in una casella)"),
                 an["esempi"] and acc.esito_js(r["uscita"]) == ((True, []) if verde
                                                                else (False, [2])),
                 r["uscita"][-500:])


# ═══════════════════════════ 4. nel servizio ═══════════════════════════

def prova_servizio(tmp: Path):
    sezione("4. nel servizio: la regola quando il codice li toglie tutti")
    import prova_fasi_agente_2 as F2
    from types import SimpleNamespace
    sv = SimpleNamespace(requisiti=[dict(r) for r in REQUISITI], richiesta=RICHIESTA)
    for nome, esempi, regola in (
            ("tutti tolti", [_e(4, TUTTE, testo="Vittoria"), _e(2, [5], fase="esito")], True),
            ("contrario: uno tenuto", [_e(4, TUTTE), _e(2, [5], testo="X")], False)):
        s, log = F2._servizio([analisi(esempi)], sviluppi=F2.SviluppiFinti(sv))
        lav = F2._lavoro("T" + str(int(regola)))
        sb = _sandbox(tmp, "srv_" + str(int(regola)), _cartella("tris"))
        s.analisi(lav, sb, True)
        a = lav.accettazione
        conti = ((getattr(lav, "segnali", None) or {}).get("regole") or {})
        righe = [x for x in log if "accettazione_esempi_tutti_tolti" in x]
        if regola:
            verifica(f"{nome}: la regola nel registro con le cause, «esempi_modello» 2",
                     conti.get("accettazione_esempi_tutti_tolti") == 1 and righe
                     and "2 del modello" in righe[0] and "lunghi 1" in righe[0]
                     and a.get("esempi") == 0 and a.get("esempi_modello") == 2,
                     f"{a} {log}")
        else:
            verifica(f"{nome}: niente regola, 1 esempio",
                     not conti.get("accettazione_esempi_tutti_tolti") and not righe
                     and a.get("esempi") == 1 and a.get("esempi_modello") == 2, f"{a} {log}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-esito-"))
    try:
        prova_testi()
        prova_avviso(radice / "avviso")
        prova_esempi(radice / "esempi")
        prova_servizio(radice / "servizio")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
