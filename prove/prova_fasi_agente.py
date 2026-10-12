"""Prova a secco del flusso dell'agente a fasi, parte 1 (12/10/2026 sera; ricerca
docs/ricerche/2026-10-12-flusso-agente-fasi.md, area agenti-estensioni e giochi; caso vero: il
gioco delle porte del 12/10, qui con nomi di fantasia).

1. **La correzione parte da un test che fallisce** (calliope/agenti/riproduzione.py):
   - a. il controllo sugli artefatti: un test nuovo che fallisce sulla versione di prima →
     «riprodotto»; i contrari: codice uguale (anche con un file di prova in più), nessun test
     nuovo, un test nuovo che passa anche prima, nessun file di partenza;
   - b. il ciclo vero con un cliente finto: la consegna senza test torna all'agente una volta,
     con il test giusto passa; senza mai il test la seconda consegna va avanti segnata; un
     lavoro che non è una correzione non si controlla; senza passate non si rimanda;
   - c. la frase a voce: «non sono riuscita a riprodurre il problema: me lo descrivi in un altro
     modo?» con la correzione in sospeso; il codice uguale lo dice; contrario: riprodotto →
     come sempre.
2. **I test toccano il comportamento visibile** (apriGioco in calliope/agenti/fumo_js.mjs):
   - a. il difetto del 12/10 (l'esito annidato letto al primo livello): logica e prova di fumo
     verdi, il test del disegno rosso; contrario: il gioco giusto lo passa;
   - b. l'API: un elemento che non c'è, un gestore che lancia (file:riga), un elemento
     disabilitato, il seme (stessa partita con lo stesso seme, creaCaso), un comando non
     attivo, nessuna scheda;
   - c. la riproduzione di una correzione di gioco: il test del disegno è rosso sulla versione
     di prima; contrario: un test nuovo solo sulla logica passa anche prima.
3. **esegui_js e il seme**: esegui_js nel container di Node (la stampa dell'esito annidato,
   un errore, solo .js, mai senza container), i file prova_*.js fuori dal codice; al
   ricontrollo i test due volte: un test che cambia esito torna all'agente con «fissa il seme»
   (regola agente_test_instabili); contrari: sempre verdi, sempre rossi, i test con creaCaso e
   apriGioco con il seme.

    python prove/prova_fasi_agente.py
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

errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


# ═══════════════════════════ 1. la correzione parte da un test rosso ═══════════════════════════

CALCOLA_ROTTO = "def somma(a, b):\n    return a - b\n"
CALCOLA_GIUSTO = "def somma(a, b):\n    return a + b\n"
TEST_VECCHIO = ("import unittest\nfrom calcola import somma\n\n\nclass P(unittest.TestCase):\n"
                "    def test_zero(self):\n        self.assertEqual(somma(0, 0), 0)\n")
# Riproduce il difetto segnalato («due più tre fa meno uno»): fallisce sul codice di prima
TEST_ROSSO = TEST_VECCHIO + ("\n    def test_due_piu_tre(self):\n"
                             "        self.assertEqual(somma(2, 3), 5)\n")
# Un test nuovo che passa anche sul codice di prima: non riproduce niente
TEST_VERDE = TEST_VECCHIO + ("\n    def test_tre_meno_tre(self):\n"
                             "        self.assertEqual(somma(3, 3) - 6 + 6, somma(3, 3))\n")
PRIMA = {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_VECCHIO}


def _lav(correzione=True, prima=PRIMA, problema="due più tre fa meno uno"):
    from calliope.agenti.ciclo import Lavoro
    lav = Lavoro("C1", "codice", "una funzione che somma")
    lav.correzione = correzione
    lav.problema_correzione = problema
    lav.file_iniziali = dict(prima or {})
    return lav


def _sb(tmp: Path, nome: str, file: dict):
    sb = G.sandbox(tmp, nome)
    for k, v in file.items():
        sb.scrivi(k, v)
    return sb


def prova_riproduzione(tmp: Path):
    sezione("1a. la correzione: il controllo sugli artefatti")
    from calliope.agenti.riproduzione import controlla, messaggio_agente
    casi = [
        ("un test nuovo che fallisce prima e passa adesso → riprodotto", "rosso",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_ROSSO}, PRIMA, "riprodotto"),
        ("contrario: il codice uguale (cambiato solo il test) → uguale", "uguale",
         {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_ROSSO}, PRIMA, "uguale"),
        ("contrario: un file di prova dell'agente non cambia il codice → uguale", "prova",
         {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_ROSSO,
          "prova_somma.py": "print(1)\n"}, PRIMA, "uguale"),
        ("contrario: il codice corretto ma nessun test nuovo → nessun_test", "senza",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_VECCHIO}, PRIMA, "nessun_test"),
        ("contrario: un test nuovo che passa anche prima → passa_prima", "verde",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_VERDE}, PRIMA, "passa_prima"),
        ("un file di test nuovo accanto a quello di prima → riprodotto", "nuovo_file",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_VECCHIO,
          "test_segnalazione.py": TEST_ROSSO}, PRIMA, "riprodotto"),
        ("nessun file di partenza → saltato (la consegna va avanti)", "vuoto",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_ROSSO}, {}, "saltato"),
    ]
    for nome, cart, ora, prima, atteso in casi:
        sb = _sb(tmp, cart, ora)
        e = controlla(_lav(prima=prima), sb, log=lambda *_: None)
        verifica(nome, e["stato"] == atteso, str(e)[:300])
        if cart == "rosso":
            verifica("…solo il file nuovo o cambiato, e la sandbox di prima tolta",
                     e["test"] == ["test_calcola.py"]
                     and not (sb.root.parent / "rosso-prima").exists(), str(e["test"]))
    m = messaggio_agente({"stato": "passa_prima", "test": ["test_calcola.py"]},
                         "due più tre fa meno uno")
    verifica("il rimando dice quale test, «versione di PRIMA» e il problema",
             "test_calcola.py" in m and "versione di PRIMA" in m and "due più tre" in m, m)
    m = messaggio_agente({"stato": "nessun_test"}, "", gioco=True)
    verifica("…senza test: «prima scrivi un test», e per un gioco gioco.test.js con apriGioco",
             "prima scrivi un test" in m and "gioco.test.js" in m and "apriGioco" in m, m)


def prova_ciclo(tmp: Path):
    sezione("1b. il ciclo vero: la consegna di una correzione")
    scrivi = lambda p, c: {"name": "scrivi_file",  # noqa: E731
                           "arguments": {"percorso": p, "contenuto": c}}
    consegna = {"name": "consegna", "arguments": {"riassunto": "Corretto.", "esito": "fatto"}}
    test = {"name": "esegui_test", "arguments": {}}
    # Prima consegna senza test nuovo; il rimando; poi il test rosso e la consegna
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [test], [consegna],
                      [scrivi("test_calcola.py", TEST_ROSSO)], [test], [consegna]])
    log = []
    ag = G.agente(cli, log)
    sb = _sb(tmp, "ciclo1", PRIMA)
    lav = _lav()
    ris = ag.codice(lav, sb)
    tool = [json.loads(m["content"]) for m in lav.contesto["messages"]
            if m.get("role") == "tool" and m.get("tool_name") == "consegna"]
    verifica("la prima consegna senza test torna all'agente: «non hai scritto né cambiato un "
             "test»", len(tool) == 2 and tool[0].get("consegna") == "rifiutata"
             and "non hai scritto né cambiato un test" in tool[0].get("errore", ""),
             str(tool)[:400])
    verifica("…con il test che riproduce, la seconda passa: riprodotto",
             ris.get("esito") == "fatto" and tool[1].get("ok") is True
             and lav.riproduzione.get("stato") == "riprodotto"
             and lav.riproduzione.get("rimandi") == 1, str(lav.riproduzione))
    verifica("…la regola nel log e nei segnali",
             any("correzione_rimandata" in x for x in log)
             and lav.segnali.get("regole", {}).get("correzione_rimandata") == 1, str(log[-4:]))
    # Mai il test: la seconda consegna va avanti, segnata
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [consegna], [consegna]])
    log = []
    ag = G.agente(cli, log)
    sb = _sb(tmp, "ciclo2", PRIMA)
    lav = _lav()
    ris = ag.codice(lav, sb)
    verifica("senza mai il test: rimandata una volta, poi la consegna va avanti segnata "
             "«nessun_test»", ris.get("esito") == "fatto"
             and lav.riproduzione.get("stato") == "nessun_test"
             and lav.segnali.get("regole", {}).get("correzione_non_riprodotta") == 1,
             str(lav.riproduzione))
    # Contrari: non è una correzione; non restano passate
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [consegna]])
    ag = G.agente(cli, [])
    sb = _sb(tmp, "ciclo3", PRIMA)
    lav = _lav(correzione=False)
    ris = ag.codice(lav, sb)
    verifica("contrario: un lavoro che non è una correzione non si controlla",
             ris.get("esito") == "fatto" and not getattr(lav, "riproduzione", None)
             and len(cli.corpi) == 2)
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [consegna]])
    ag = G.agente(cli, [])
    ag.max_passi = 3
    sb = _sb(tmp, "ciclo4", PRIMA)
    lav = _lav()
    ris = ag.codice(lav, sb)
    verifica("contrario: senza passate per correggere non si rimanda (resta segnata)",
             ris.get("esito") == "fatto" and len(cli.corpi) == 2
             and lav.riproduzione.get("stato") == "nessun_test", str(lav.riproduzione))


def prova_frase(tmp: Path):
    sezione("1c. la frase a voce dopo una correzione che non riproduce")
    import prova_giro_porte as GP
    import prova_specifica_viva as S
    agente = S.AgenteVivo(requisiti=GP.REQ, stima="piccolo",
                          modifiche=[{"tipo": "difetto", "operazioni": []}] * 3)
    cfg, reg, ctx, est, svc, sv = GP.al_collaudo(tmp / "frase", agente)
    problema = "toccando una porta non si vede nessun mostro e non si prendono punti"
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 4,
             "Toccando una porta non si vede nessun mostro e non si prendono punti.")
    lav = svc.lavori[-1]
    from calliope.tools.sviluppo import VINCOLO_RIPRODUCI
    verifica("i vincoli della correzione: prima il test che fallisce",
             lav.correzione and VINCOLO_RIPRODUCI.strip() in lav.vincoli
             and "deve FALLIRE" in lav.vincoli, lav.vincoli[-400:])
    lav.riproduzione = {"stato": "passa_prima", "test": ["gioco.test.js"], "rimandi": 1}
    item = S.consegna(svc, est, sv)
    m = item["messaggio"]
    verifica("non riprodotta: «non sono riuscita a riprodurre il problema: me lo descrivi in "
             "un altro modo?»", "non sono riuscita a riprodurre il problema: me lo descrivi in "
             "un altro modo?" in m and "pronto" not in m.lower(), m)
    verifica("…con la correzione in sospeso (la risposta è il problema detto di nuovo)",
             (item.get("in_sospeso") or {}).get("tool") == "sviluppo_correggi"
             and "problema" in str(item["in_sospeso"].get("argomenti")), str(item))
    # Il codice uguale (il caso delle 08:46) con il controllo fatto: lo dice
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 6,
             "Non si vede ancora nessun mostro.")
    lav = svc.lavori[-1]
    lav.riproduzione = {"stato": "uguale", "rimandi": 1}
    item = S.consegna(svc, est, sv)
    verifica("codice uguale e controllo fatto: «il codice è uguale a prima, e non sono riuscita "
             "a riprodurre…»", "il codice è uguale a prima, e non sono riuscita a riprodurre"
             in item["messaggio"], item["messaggio"])
    # Contrario: riprodotta → la frase di sempre (si prova)
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 8,
             "Non si vede ancora nessun mostro.")
    lav = svc.lavori[-1]
    lav.riproduzione = {"stato": "riprodotto", "test": ["gioco.test.js"], "rimandi": 0}
    import prova_estensioni as P
    import prova_sviluppo as SS
    import prova_sviluppo_v2 as V
    n = est.archivio.nuova_candidata(P.valida(SS.M2), {"estensione.py": (
        V.CODICE_GEO + "# corretto\n").encode()}, "Dario", {"eseguiti": 4, "falliti": 0},
        {"rischi": [], "sintassi": []}, lav.id, True)
    item = svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       test={"eseguiti": 4, "falliti": 0}, messaggio="ho corretto il gioco.")
    verifica("contrario: riprodotta → «riprovala», niente «non sono riuscita»",
             "non sono riuscita" not in item["messaggio"]
             and (item.get("in_sospeso") or {}).get("tool") == "sviluppo_collauda",
             item["messaggio"])


# ═══════════════════════════ 2. i test toccano il comportamento visibile ═══════════════════════════
# Il difetto vero del 12/10 (11:05–12:06, sei versioni), con nomi di fantasia: logica.js
# restituisce lo stato con l'esito annidato, gioco.js lo legge al primo livello. Niente mostro,
# sempre «Nessun punto!», i test della logica verdi e la prova di fumo pure (nessun «undefined»)

LOGICA_PORTE = """"use strict";
const DIETRO = [
  { tipo: "mostro", nome: "Fantasmino", emoji: "👻", punti: 3 },
  { tipo: "oggetto", nome: "Caramella", emoji: "🍬", punti: 0 },
  { tipo: "mostro", nome: "Pipistrello", emoji: "🦇", punti: 2 },
];
function nuovaPartita(nGiocatori) {
  if (!(nGiocatori >= 2 && nGiocatori <= 4)) throw new Error("da 2 a 4 giocatori");
  return { turno: 0, punti: new Array(nGiocatori).fill(0), porte: DIETRO.map((d) => ({ ...d })) };
}
function apriPorta(stato, porta) {
  const risultato = { ...stato.porte[porta] };
  const punti = stato.punti.slice();
  punti[stato.turno] += risultato.punti;
  return { ...stato, punti, turno: (stato.turno + 1) % punti.length, risultato };
}
if (typeof module !== "undefined") module.exports = { nuovaPartita, apriPorta };
"""
GIOCO_PORTE = """"use strict";
const radice = document.getElementById("gioco");
let partita = null;
function sicuro(f) {
  return (ev) => { try { f(ev); } catch (e) { const p = document.createElement("p"); p.textContent = e.message; radice.appendChild(p); } };
}
function mostra(esito) {
  const r = document.createElement("div");
  r.className = "esito";
  const e = document.createElement("span");
  e.textContent = esito.emoji;
  const n = document.createElement("span");
  n.textContent = esito.nome;
  const p = document.createElement("p");
  p.textContent = esito.punti > 0 ? "+" + esito.punti + " punti!" : "Nessun punto!";
  r.append(e, n, p);
  radice.appendChild(r);
}
function disegna(esito) {
  radice.replaceChildren();
  if (!partita) {
    const b = document.createElement("button");
    b.textContent = "Inizia";
    b.addEventListener("click", sicuro(() => { partita = nuovaPartita(2); disegna(); }));
    radice.appendChild(b);
    return;
  }
  const t = document.createElement("p");
  t.textContent = "Tocca al giocatore " + (partita.turno + 1) + " · punti " + partita.punti.join(" a ");
  radice.appendChild(t);
  partita.porte.forEach((_, i) => {
    const b = document.createElement("button");
    b.className = "porta";
    b.textContent = "Porta " + (i + 1);
    b.addEventListener("click", sicuro(() => {
      const nuovo = apriPorta(partita, i);
      partita = nuovo;
      disegna(MOSTRA_ESITO);
    }));
    radice.appendChild(b);
  });
  if (esito) mostra(esito);
}
calliope.quandoPronto(() => disegna());
"""
# Il collegamento rotto (12/10) e quello giusto
GIOCO_ROTTO = GIOCO_PORTE.replace("MOSTRA_ESITO", "nuovo")
GIOCO_GIUSTO = GIOCO_PORTE.replace("MOSTRA_ESITO", "nuovo.risultato")
TEST_LOGICA_PORTE = """const { test } = require("node:test");
const assert = require("node:assert");
const { nuovaPartita, apriPorta } = require("./logica.js");
test("la porta del fantasmino dà 3 punti al primo giocatore", () => {
  const s = apriPorta(nuovaPartita(2), 0);
  assert.strictEqual(s.risultato.punti, 3);
  assert.deepStrictEqual(s.punti, [3, 0]);
});
"""
# Il test del disegno: tocca come la persona e legge cosa compare
TEST_GIOCO_PORTE = """const { test } = require("node:test");
const assert = require("node:assert");
test("toccando la porta del fantasmino si vedono il mostro e i suoi punti", async () => {
  const g = await apriGioco({ giocatori: 2, seme: 1 });
  await g.tocca("Inizia");
  await g.tocca("Porta 1");
  assert.match(g.testo(), /Fantasmino/);
  assert.match(g.testo(), /\\+3 punti/);
  assert.match(g.testo(), /punti 3 a 0/);
});
"""
MANIFESTO_PORTE = {"nome": "porte_borgofiore", "titolo": "Le porte di Borgofiore",
                   "cosa_fa": {"verbo": "propone", "oggetto": "un gioco di porte e mostri"},
                   "permessi": {}, "scheda": {"tipo": "gioco", "file": ["logica.js", "gioco.js"],
                                              "giocatori": {"min": 2, "max": 4}}}


def _gioco(tmp: Path, nome: str, gioco: str, test_gioco: str | None = TEST_GIOCO_PORTE,
           extra: dict | None = None):
    file = {"logica.js": LOGICA_PORTE, "gioco.js": gioco, "logica.test.js": TEST_LOGICA_PORTE,
            "manifesto.json": json.dumps(MANIFESTO_PORTE)}
    if test_gioco:
        file["gioco.test.js"] = test_gioco
    file.update(extra or {})
    return _sb(tmp, nome, file)


def prova_disegno(tmp: Path):
    sezione("2a. il difetto del 12/10: l'esito annidato letto al primo livello")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    sb = _gioco(tmp, "rotto_senza", GIOCO_ROTTO, None)
    r = sb.test()
    verifica("com'era il 12/10: i test della logica e la prova di fumo passano (il difetto non "
             "si vede)", r["passano"] and "ok prova di fumo" in r["uscita"], r["uscita"][-400:])
    sb = _gioco(tmp, "rotto", GIOCO_ROTTO)
    r = sb.test()
    u = r["uscita"]
    verifica("con il test del disegno (apriGioco, tocca, testo): fallisce e dice cosa si vede",
             not r["passano"] and "FALLITO toccando la porta del fantasmino" in u
             and "Fantasmino" in u, u[-600:])
    sb = _gioco(tmp, "giusto", GIOCO_GIUSTO)
    r = sb.test()
    verifica("contrario: il gioco giusto passa il test del disegno, la logica e la prova di fumo",
             r["passano"] and "ok toccando la porta del fantasmino" in r["uscita"]
             and "ok prova di fumo" in r["uscita"], r["uscita"][-400:])

    sezione("2b. apriGioco: tocchi, errori, comandi, seme")
    casi = {
        "assente": ('test("x", async () => { const g = await apriGioco(); '
                    'await g.tocca("Porta 9"); });',
                    lambda u: "nessun elemento da toccare con «Porta 9»" in u
                    and "Inizia" in u),
        "lancia": ('test("x", async () => { const g = await apriGioco(); '
                   'await g.tocca("Inizia"); await g.tocca(".porta", 2); });',
                   lambda u: "toccando «.porta»" in u and "porta rotta" in u
                   and "gioco.js:" in u),
        "disabilitato": ('test("x", async () => { const g = await apriGioco(); '
                         'g.trova("Inizia")[0].disabled = true; await g.tocca("Inizia"); '
                         'require("node:assert").doesNotMatch(g.testo(), /Tocca al giocatore/); });',
                         lambda u: "ok x" in u),
        "seme": ('test("x", async () => { const a = await apriGioco({ seme: 7 }); '
                 'const b = await apriGioco({ seme: 7 }); const c = await apriGioco({ seme: 8 }); '
                 'const assert = require("node:assert"); '
                 'assert.strictEqual(a.testo(), b.testo()); assert.notStrictEqual(a.testo(), '
                 'c.testo()); const r1 = creaCaso(3), r2 = creaCaso(3); '
                 'assert.strictEqual(r1(), r2()); });',
                 lambda u: "ok x" in u),
    }
    gioco = GIOCO_GIUSTO.replace(
        'b.textContent = "Inizia";',
        'b.textContent = "Inizia"; const k = document.createElement("i"); '
        'k.textContent = String(Math.random()); radice.appendChild(k);').replace(
        "const nuovo = apriPorta(partita, i);",
        'if (i === 2) throw new Error("porta rotta"); const nuovo = apriPorta(partita, i);')
    # Il gestore che lancia senza sicuro(): un'eccezione che esce dal tocco
    gioco = gioco.replace('b.addEventListener("click", sicuro(() => {\n      if (i === 2)',
                          'b.addEventListener("click", (() => {\n      if (i === 2)')
    for nome, (corpo, controllo) in casi.items():
        sb = _gioco(tmp, "api_" + nome, gioco,
                    'const { test } = require("node:test");\n' + corpo + "\n")
        u = sb.test(fumo=False)["uscita"]
        # «disabilitato» e «seme» devono passare il test; «assente» e «lancia» fallirlo
        verifica(f"apriGioco: {nome}", controllo(u), u[-500:])
    sb = _gioco(tmp, "api_comando", GIOCO_GIUSTO,
                'const { test } = require("node:test");\ntest("x", async () => { '
                'const g = await apriGioco(); await g.comando("tre"); });\n')
    u = sb.test(fumo=False)["uscita"]
    verifica("apriGioco: un comando non attivo lo dice", "il comando «tre» adesso non è attivo"
             in u, u[-300:])
    sb = _sb(tmp, "api_senza_scheda", {"logica.js": LOGICA_PORTE, "x.test.js": (
        'const { test } = require("node:test");\ntest("x", async () => { await apriGioco(); });\n')})
    u = sb.test()["uscita"]
    verifica("apriGioco senza scheda nel manifesto: lo dice", "manca la «scheda»" in u, u[-300:])

    sezione("2c. la riproduzione di una correzione di gioco")
    from calliope.agenti.riproduzione import controlla
    prima = {"logica.js": LOGICA_PORTE, "gioco.js": GIOCO_ROTTO,
             "logica.test.js": TEST_LOGICA_PORTE, "manifesto.json": json.dumps(MANIFESTO_PORTE)}
    sb = _gioco(tmp, "rip_giusta", GIOCO_GIUSTO)
    e = controlla(_lav(prima=prima), sb, log=lambda *_: None)
    verifica("la correzione con il test del disegno: rosso sulla versione di prima → "
             "riprodotto", e["stato"] == "riprodotto" and e["test"] == ["gioco.test.js"], str(e))
    test_logica2 = TEST_LOGICA_PORTE + (
        'test("la porta della caramella non dà punti", () => {\n'
        '  assert.strictEqual(apriPorta(nuovaPartita(2), 1).risultato.punti, 0);\n});\n')
    sb = _gioco(tmp, "rip_logica", GIOCO_GIUSTO, None, {"logica.test.js": test_logica2})
    e = controlla(_lav(prima=prima), sb, log=lambda *_: None)
    verifica("contrario: un test nuovo solo sulla logica passa anche prima → passa_prima (il "
             "11:37 del 12/10)", e["stato"] == "passa_prima", str(e))
    from calliope.tools.sviluppo import VINCOLO_CORREZIONE_GIOCO
    verifica("i vincoli della correzione di un gioco: gioco.test.js con apriGioco",
             "gioco.test.js" in VINCOLO_CORREZIONE_GIOCO
             and "apriGioco" in VINCOLO_CORREZIONE_GIOCO)


# ═══════════════════════════ 3. esegui_js e i test con il seme ═══════════════════════════

# Un test che cambia esito a ogni esecuzione (un contatore su file: qui deterministico, come
# un Math.random senza seme il 12/10 alle 07:39)
TEST_INSTABILE = ("import os\nimport unittest\n\n\nclass P(unittest.TestCase):\n"
                  "    def test_caso(self):\n"
                  "        n = int(open('conta.txt').read()) if os.path.exists('conta.txt') else 0\n"
                  "        open('conta.txt', 'w').write(str(n + 1))\n"
                  "        self.assertEqual(n % 2, 0)\n")


def prova_js_e_seme(tmp: Path):
    sezione("3a. esegui_js: un pezzo di JavaScript nella sandbox")
    from calliope.agenti.ciclo import ESEGUI_JS, Lavoro, strumenti_codice
    from calliope.agenti.sandbox import ErroreSandbox
    nomi = lambda ling: [t["function"]["name"] for t in strumenti_codice(ling)]  # noqa: E731
    verifica("esegui_js solo con il container di Node",
             "esegui_js" in nomi(["python", "javascript"]) and "esegui_js" not in nomi(["python"])
             and "prova_*.js" in ESEGUI_JS["function"]["description"])
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
    else:
        sb = _gioco(tmp, "js", GIOCO_ROTTO, None, {"prova_esito.js": (
            'const { nuovaPartita, apriPorta } = require("./logica.js");\n'
            'const s = apriPorta(nuovaPartita(2), 0);\n'
            'console.log(Object.keys(s).join(","), s.emoji, s.risultato.nome);\n')})
        r = sb.esegui_js("prova_esito.js")
        verifica("la stampa mostra l'esito annidato (quello che il 12/10 si cercava a mente)",
                 r.get("codice_uscita") == 0 and "risultato" in r["uscita"]
                 and "undefined Fantasmino" in r["uscita"], str(r)[:300])
        sb.scrivi("prova_rotta.js", "const x = nonDichiarata + 1;\n")
        r = sb.esegui_js("prova_rotta.js")
        verifica("…un errore esce con il codice e il messaggio", r.get("codice_uscita") != 0
                 and "nonDichiarata" in r["uscita"], str(r)[:300])
        try:
            sb.esegui_js("manifesto.json")
            verifica("esegui_js: solo file .js", False)
        except ErroreSandbox as e:
            verifica("esegui_js: solo file .js della cartella", ".js" in str(e), str(e))
        cli = G._Copione([[{"name": "esegui_js", "arguments": {"percorso": "prova_esito.js"}}],
                          [{"name": "consegna", "arguments": {"riassunto": "x",
                                                              "esito": "fatto"}}]])
        lav = Lavoro("J1", "codice", "una prova")
        G.agente(cli, []).codice(lav, sb)
        res = next((json.loads(m["content"]) for m in lav.contesto["messages"]
                    if m.get("tool_name") == "esegui_js"), {})
        verifica("…nel ciclo dell'agente esegui_js restituisce l'uscita",
                 "Fantasmino" in str(res.get("uscita")), str(res)[:200])
    sb = _sb(tmp, "senza_node", {"prova.js": "console.log(1)\n"})
    sb.linguaggi = {}
    try:
        sb.esegui_js("prova.js")
        verifica("senza il container di Node: lo dice", False)
    except ErroreSandbox as e:
        verifica("contrario: senza il container di Node lo dice, mai sull'host",
                 "container di Node" in str(e), str(e))
    from calliope.agenti.riproduzione import codice as solo_codice
    from calliope.estensioni.servizio import _solo_usati
    verifica("i file prova_*.js non sono codice del gioco né della versione",
             "prova_esito.js" not in solo_codice({"prova_esito.js": "x", "gioco.js": "y"})
             and "prova_esito.js" not in _solo_usati({"prova_esito.js": b"x", "gioco.js": b"y"})
             and "gioco.js" in _solo_usati({"prova_esito.js": b"x", "gioco.js": b"y"}))

    sezione("3b. al ricontrollo i test si eseguono due volte")
    from calliope.agenti import diagnosi
    a = {"passano": True, "esito": {"eseguiti": 2, "falliti": 0, "errori": 0}, "uscita": ""}
    b = {"passano": False, "esito": {"eseguiti": 2, "falliti": 1, "errori": 0},
         "uscita": "FALLITO punti a caso: 3 !== 4 [in logica.test.js:9]\n"}
    verifica("diagnosi.instabili: esiti diversi → i nomi; uguali → None",
             diagnosi.instabili(a, b) == ["punti a caso"] and diagnosi.instabili(a, a) is None
             and diagnosi.instabili(b, dict(b)) is None
             and diagnosi.conto_detto(b) == "1 su 2 passano")
    log = []
    ag = G.agente(None, log)
    lav = _lav(correzione=False)
    sb = _sb(tmp, "instabile", {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_INSTABILE})
    r = ag._test_falliti(lav, sb)
    err = (r or {}).get("errore", "")
    verifica("un test che cambia esito tra due esecuzioni: la consegna torna con «fissa il "
             "seme» e il nome del test", r is not None and "test_caso" in err
             and "fissa il seme" in err and "prima 1 su 1 passano, poi 0 su 1" in err, err[:300])
    verifica("…la regola agente_test_instabili", lav.segnali.get("regole", {}).get(
        "agente_test_instabili") == 1 and any("agente_test_instabili" in x for x in log))
    sb = _sb(tmp, "stabile", {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_ROSSO})
    verifica("contrario: i test che passano sempre → la consegna va",
             ag._test_falliti(_lav(), sb) is None)
    sb = _sb(tmp, "sempre_rosso", {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_ROSSO})
    r = ag._test_falliti(_lav(), sb) or {}
    verifica("contrario: un test che fallisce sempre → il rimando di sempre, niente «seme»",
             r.get("consegna") == "rifiutata" and "seme" not in r.get("errore", "")
             and "i test non passano" in r.get("errore", ""), str(r)[:300])
    if shutil.which("node"):
        test_seme = ('const { test } = require("node:test");\n'
                     'const assert = require("node:assert");\n'
                     'test("caso con il seme", () => { const a = creaCaso(5), b = creaCaso(5); '
                     'assert.strictEqual(a(), b()); });\n'
                     'test("disegno con il seme", async () => { '
                     'const g = await apriGioco({ seme: 5 }); await g.tocca("Inizia"); '
                     'assert.match(g.testo(), /Porta 1/); });\n')
        sb = _gioco(tmp, "seme_js", GIOCO_GIUSTO, test_seme)
        verifica("contrario: i test JavaScript con il seme (creaCaso, apriGioco) danno lo "
                 "stesso esito due volte", ag._test_falliti(_lav(), sb) is None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-fasi-"))
    try:
        prova_riproduzione(radice / "riproduzione")
        prova_ciclo(radice / "ciclo")
        prova_frase(radice / "frase")
        prova_disegno(radice / "disegno")
        prova_js_e_seme(radice / "js")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
