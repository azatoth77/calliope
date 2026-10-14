"""Prova a secco del palco fisso dei giochi (14/10/2026, passo 4 del progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md § 5; area docs/aree/giochi.md).

1. **L'impaginazione pura** (calliope/estensioni/motore_gioco.js: impagina, controllaPalco, in
   Node): il gioco delle prove `prove/giochi/pagine` passa per tutti i modelli (titolo, scelte,
   griglia, messaggio, punteggi, classifica, tela; la preparazione e l'esito di Calliope) e ogni
   pagina sta nel palco 1280×720 e 720×1280: niente fuori, niente sovrapposto, nessun testo
   tagliato, le scatole in ordine di lettura; anche il tris (griglia) e le porte (scelte), e
   otto giocatori nella fascia e nei punteggi. I difetti messi apposta li trova e li dice per
   l'agente: troppi pulsanti (con quanti ne stanno, e chi esce e si sovrappone), un titolo
   lunghissimo (con la fonte, GIOCO.vista), il testo di una casella, un esito lungo, una griglia
   12×12 con troppo testo sopra, una tela schiacciata.
2. **La prova di fumo misura il palco** (calliope/agenti/fumo_js.mjs): il gioco delle pagine
   passa i suoi test (g.palco() in ogni fase) e la prova di fumo; contrari: un titolo troppo
   lungo in una fase raggiunta dopo qualche mossa (detto con la fase, la strada e la fonte),
   una griglia troppo grande, troppi pulsanti; g.palco() li dice anche nei test.
3. **Il server**: la diagnosi «palco» del riquadro passa anche in una partita di prova (è un
   ingresso di diagnosi, come i comandi), mai il ponte.

    python prove/prova_gioco_palco.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_agente_guida as G  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
GIOCHI = RADICE / "prove" / "giochi"
MOTORE = RADICE / "calliope" / "estensioni" / "motore_gioco.js"
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def manifesto(gioco: str) -> dict:
    return json.loads((GIOCHI / gioco / "manifesto.json").read_text(encoding="utf-8"))


def node(tmp: Path, codice: str) -> dict | None:
    tmp.mkdir(parents=True, exist_ok=True)
    f = tmp / "prova.mjs"
    f.write_text(codice, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8",
                       timeout=120)
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        print((r.stdout or "")[-800:], (r.stderr or "")[-800:])
        return None


# ═══════════════════════════ 1. l'impaginazione pura ═══════════════════════════

IMPAGINA = r"""
import { readFileSync } from "node:fs";
import vm from "node:vm";
const ctx = vm.createContext({ console, JSON, Math, Array, Object });
vm.runInContext(readFileSync(__MOTORE__, "utf8"), ctx);
const CM = ctx.CalliopeMotore;
const ORIENT = ["orizzontale", "verticale"];
const giochi = __GIOCHI__;
function carica(nome) {
  const c = vm.createContext({ console, JSON, Math });
  vm.runInContext(readFileSync(giochi[nome].logica, "utf8") + "\nthis.GIOCO = GIOCO;", c);
  const m = giochi[nome].manifesto;
  return CM.crea(c.GIOCO, m.scheda.macchina, m.scheda.giocatori, { titolo: m.titolo });
}
// Le scatole di una pagina: dentro il palco? sovrapposte? in ordine di lettura?
function esame(pag) {
  const out = {};
  for (const O of ORIENT) {
    const imp = CM.impagina(pag, O);
    const s = imp.scatole;
    const fuori = s.filter((b) => b.x < 0 || b.y < 0 || b.x + b.w > imp.W || b.y + b.h > imp.H).length;
    const ordine = s.every((b, i) => i === 0 || s[i - 1].y < b.y || (s[i - 1].y === b.y && s[i - 1].x <= b.x));
    out[O] = { W: imp.W, H: imp.H, n: s.length, fuori, ordine, difetti: CM.difettiPalco(pag, O),
               pulsanti: s.filter((b) => b.tipo === "pulsante" || (b.tipo === "casella" && b.comando)).length,
               minPulsante: Math.min(...s.filter((b) => b.tipo === "pulsante").map((b) => Math.min(b.w, b.h)), 999) };
  }
  return out;
}
const r = { pagine: [], tris: null, porte: null, apposta: {} };
// il giro delle pagine
let nu = carica("pagine");
let S = nu.nuovo();
const giro = [["giocatori", 2], ["parti", null], ["colore", "rosso"], ["avanti", null], ["casella", 7],
              ["prosegui", null], ["vediamo", null], ["fine_partita", null]];
r.pagine.push({ fase: S.fase, modello: nu.pagina(S).modello, esame: esame(nu.pagina(S)) });
for (const [c, v] of giro) {
  S = nu.applica(S, c, v);
  const pag = nu.pagina(S);
  r.pagine.push({ fase: S.fase, modello: pag.modello, esame: esame(pag) });
}
// otto giocatori: la fascia e i punteggi
const P8 = JSON.parse(JSON.stringify(giochi.pagine.manifesto));
P8.scheda.giocatori = { min: 1, max: 8 };
{
  const c = vm.createContext({ console, JSON, Math });
  vm.runInContext(readFileSync(giochi.pagine.logica, "utf8") + "\nthis.GIOCO = GIOCO;", c);
  const n8 = CM.crea(c.GIOCO, P8.scheda.macchina, P8.scheda.giocatori, {});
  let s8 = n8.applica(n8.nuovo(), "giocatori", 8);
  r.otto_prep = esame(n8.pagina(n8.nuovo()));
  s8 = n8.applica(s8, "parti", null);
  r.otto_scelte = esame(n8.pagina(s8));
  s8 = n8.applica(s8, "colore", "blu"); s8 = n8.applica(s8, "avanti"); s8 = n8.applica(s8, "casella", 2);
  s8 = n8.applica(s8, "prosegui");
  r.otto_punteggi = esame(n8.pagina(s8));
}
// il tris (griglia) e le porte (scelte)
nu = carica("tris");
S = nu.applica(nu.nuovo(), "giocatori", 2);
r.tris = { modello: nu.pagina(S).modello, esame: esame(nu.pagina(S)) };
nu = carica("porte_fasi");
S = nu.applica(nu.nuovo(), "giocatori", 4);
r.porte = { modello: nu.pagina(S).modello, esame: esame(nu.pagina(S)) };
// i difetti messi apposta (sul contenuto di una pagina vera)
const base = (n, c, v) => { const k = carica("pagine"); let s = k.applica(k.nuovo(), "giocatori", 2); s = k.applica(s, "parti", null); return [k, s]; };
{
  const [k, s] = base();
  const pag = k.pagina(s);
  pag.pulsanti = Array.from({ length: 40 }, (_, i) => ({ c: "colore", v: String(i), etichetta: "Porta " + (i + 1) }));
  r.apposta.troppi = esame(pag);
  const pag2 = k.pagina(s);
  pag2.titolo = "Quale delle centoventi porte del castello stregato apri adesso, prima che arrivi la mezzanotte e il fantasma si svegli? ".repeat(6);
  r.apposta.titolo = esame(pag2);
}
{
  const k = carica("pagine");
  let s = k.applica(k.nuovo(), "giocatori", 2);
  s = k.applica(s, "parti"); s = k.applica(s, "colore", "verde");
  const pag = k.pagina(s);
  pag.grande = "Dietro la porta c'era un drago enorme che ha detto molte cose lunghissime ".repeat(14);
  r.apposta.esito = esame(pag);
  s = k.applica(s, "avanti");
  const g = k.pagina(s);
  g.caselle[0][0].testo = "una casella con un testo davvero troppo lungo per starci dentro tutto quanto ".repeat(3);
  r.apposta.casella = esame(g);
  const g12 = k.pagina(s);
  g12.caselle = Array.from({ length: 12 }, () => Array.from({ length: 12 }, () => ({ testo: "", colore: "", risorsa: "" })));
  r.apposta.griglia12_solo_titolo = esame(g12);
  g12.sottotitolo = "Un sottotitolo che occupa una riga";
  g12.testo = "Un testo lungo che va a capo e prende spazio sopra la griglia, così le caselle non ci stanno più come prima. ".repeat(2);
  r.apposta.griglia12_testo = esame(g12);
}
{
  const k = carica("pagine");
  let s = k.applica(k.nuovo(), "giocatori", 2);
  for (const [c, v] of [["parti", null], ["colore", "blu"], ["avanti", null], ["casella", 3], ["prosegui", null], ["vediamo", null]]) s = k.applica(s, c, v);
  const pag = k.pagina(s);
  pag.titolo = "Un titolo molto lungo per la tela che va a capo più volte e ruba spazio all'area libera";
  pag.testo = "Spiegazione lunghissima ".repeat(30);
  r.apposta.tela = esame(pag);
}
console.log(JSON.stringify(r));
"""


def prova_impaginazione(tmp: Path):
    sezione("1. l'impaginazione pura: i modelli nei due orientamenti")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    giochi = {g: {"logica": str(GIOCHI / g / "logica.js"), "manifesto": manifesto(g)}
              for g in ("pagine", "tris", "porte_fasi")}
    r = node(tmp / "impagina", IMPAGINA.replace("__MOTORE__", json.dumps(str(MOTORE)))
             .replace("__GIOCHI__", json.dumps(giochi)))
    if r is None:
        verifica("l'impaginazione gira in Node", False)
        return
    modelli = [(p["fase"], p["modello"]) for p in r["pagine"]]
    verifica("il gioco delle pagine passa per tutti i modelli",
             {m for _, m in modelli} == {"titolo", "scelte", "griglia", "messaggio", "punteggi",
                                         "classifica", "tela"}, str(modelli))

    def pulita(e):
        return all(x["fuori"] == 0 and not x["difetti"] and x["ordine"] for x in e.values())
    sporche = [(p["fase"], {o: x["difetti"] for o, x in p["esame"].items() if x["difetti"]})
               for p in r["pagine"] if not pulita(p["esame"])]
    verifica("ogni pagina sta nel palco 1280×720 e 720×1280 (niente fuori, sovrapposto, "
             "tagliato), in ordine di lettura", not sporche, str(sporche)[:600])
    e = r["pagine"][0]["esame"]
    verifica("i palchi: 1280×720 in orizzontale, 720×1280 in verticale",
             (e["orizzontale"]["W"], e["orizzontale"]["H"], e["verticale"]["W"],
              e["verticale"]["H"]) == (1280, 720, 720, 1280))
    verifica("pulsanti grandi: almeno 150×80 sul palco (in verticale ~44 px veri sul telefono)",
             all(x["minPulsante"] >= 80 for p in r["pagine"] for x in p["esame"].values()),
             str([x["minPulsante"] for p in r["pagine"] for x in p["esame"].values()]))
    verifica("otto giocatori: la preparazione, la fascia e i punteggi ci stanno",
             pulita(r["otto_prep"]) and pulita(r["otto_scelte"]) and pulita(r["otto_punteggi"]),
             str([r["otto_prep"], r["otto_scelte"], r["otto_punteggi"]])[:500])
    verifica("il tris (griglia, 9 caselle-pulsante) e le porte (scelte) ci stanno",
             r["tris"]["modello"] == "griglia" and pulita(r["tris"]["esame"])
             and r["tris"]["esame"]["orizzontale"]["pulsanti"] == 9
             and r["porte"]["modello"] == "scelte" and pulita(r["porte"]["esame"]),
             str([r["tris"], r["porte"]])[:400])

    sezione("1b. i difetti messi apposta, detti per l'agente")
    a = r["apposta"]
    d = a["troppi"]["orizzontale"]["difetti"]
    verifica("40 pulsanti: quanti ne stanno, chi esce dal palco e su chi si sovrappone",
             any("40 pulsanti non ci stanno nella pagina «scelte» (orizzontale 1280×720): al più"
                 in x and "GIOCO.attivi" in x and "«griglia»" in x for x in d)
             and any("escono dal palco in basso" in x for x in d)
             and any("si sovrappone" in x for x in d), str(d))
    verifica("…la misura è per orientamento: in verticale 40 pulsanti ci stanno (4 colonne "
             "per 10 righe)", not a["troppi"]["verticale"]["difetti"]
             and a["troppi"]["verticale"]["pulsanti"] == 40, str(a["troppi"]["verticale"]))
    d = a["titolo"]["orizzontale"]["difetti"] + a["titolo"]["verticale"]["difetti"]
    verifica("un titolo lunghissimo: non ci sta neanche a 30 px, quanti caratteri, la fonte",
             any(x.startswith("il titolo «Quale delle centoventi") and "neanche a 30 px" in x
                 and "accorcialo, al più circa" in x and "GIOCO.vista.domanda.titolo" in x
                 for x in d), str(d)[:400])
    d = a["esito"]["verticale"]["difetti"]
    verifica("un esito lungo: il messaggio non ci sta, «esito» della mossa",
             any(x.startswith("il messaggio «Dietro la porta") and "«esito» della mossa" in x
                 for x in d), str(d)[:300])
    d = a["casella"]["orizzontale"]["difetti"]
    verifica("il testo di una casella troppo lungo: la casella con riga e colonna",
             any("la casella «una casella con un testo" in x and "(riga 1, colonna 1)" in x
                 and "GIOCO.vista.tabellone.caselle" in x for x in d), str(d)[:300])
    verifica("una griglia 12×12 con il solo titolo ci sta",
             not a["griglia12_solo_titolo"]["orizzontale"]["difetti"]
             and not a["griglia12_solo_titolo"]["verticale"]["difetti"],
             str(a["griglia12_solo_titolo"]["orizzontale"]["difetti"]))
    d = a["griglia12_testo"]["orizzontale"]["difetti"]
    verifica("…con troppo testo sopra no: le caselle verrebbero piccole, quante ne stanno",
             any(x.startswith("la griglia 12×12 non ci sta nella pagina «griglia» (orizzontale")
                 and "Usa meno righe o colonne" in x for x in d), str(d)[:300])
    d = a["tela"]["orizzontale"]["difetti"]
    verifica("una tela schiacciata da titolo e testo lunghi",
             any("la tela resta alta solo" in x or "il testo «Spiegazione" in x for x in d),
             str(d)[:300])


# ═══════════════════════════ 2. la prova di fumo misura il palco ═══════════════════════════

def _gioco(tmp: Path, nome: str, logica: str, m: dict | None = None, test: str | None = None):
    sb = G.sandbox(tmp, nome)
    sb.scrivi("logica.js", logica)
    sb.scrivi("manifesto.json", json.dumps(m or manifesto("pagine")))
    sb.scrivi("gioco.test.js", test if test is not None else
              (GIOCHI / "pagine" / "gioco.test.js").read_text(encoding="utf-8"))
    return sb


def prova_fumo(tmp: Path):
    sezione("2. la prova di fumo misura il palco")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    L = (GIOCHI / "pagine" / "logica.js").read_text(encoding="utf-8")
    t0 = time.perf_counter()
    r = _gioco(tmp, "buono", L).test()
    ms = (time.perf_counter() - t0) * 1000
    verifica("il gioco delle pagine passa i suoi test (g.palco() in ogni fase) e la prova di "
             "fumo con il palco", r["passano"] and "ok ogni pagina sta nel palco" in r["uscita"]
             and "ok prova di fumo del gioco" in r["uscita"], r["uscita"][-400:])
    print(f"     (test e prova di fumo: {ms:.0f} ms, Node compreso)")
    lungo = L.replace('domanda: () => ({ titolo: "Che colore scegli?" }),',
                      'domanda: () => ({ titolo: "Che colore scegli? ' + "Pensaci bene, " * 40 + '" }),')
    u = _gioco(tmp, "titolo", lungo, test="").test()["uscita"]
    verifica("un titolo troppo lungo in una fase dopo qualche mossa: FALLITO con la fase, la "
             "strada, il titolo e la fonte",
             "FALLITO prova di fumo del gioco" in u and "palco: fase «domanda» (strada:" in u
             and "il titolo «Che colore scegli?" in u and "GIOCO.vista.domanda.titolo" in u
             and "non il disegno" in u, u[-700:])
    m = manifesto("pagine")
    m["scheda"]["macchina"]["fasi"]["domanda"]["comandi"]["colore"] = {
        "forme": ["numero {n}"], "n": {"da": 1, "a": 40}, "etichetta": "Numero {n}"}
    molti = L.replace('punti: valore === "rosso" ? 1 : 0', "punti: valore === 1 ? 1 : 0")
    u = _gioco(tmp, "troppi", molti, m, test="").test()["uscita"]
    verifica("troppi pulsanti in una pagina «scelte»: FALLITO con quanti ne stanno",
             "FALLITO prova di fumo del gioco" in u and "40 pulsanti non ci stanno" in u
             and "palco: fase «domanda»" in u, u[-600:])
    grande = L.replace("caselle: [0, 1, 2].map((r) => [0, 1, 2, 3].map((c) => {\n"
                       "        const n = r * 4 + c + 1;",
                       "testo: \"Scegli bene, la casella giusta vale molti punti e quella sbagliata "
                       "nessuno, quindi pensaci prima di toccare\", sottotitolo: \"Un tabellone "
                       "grande\", caselle: Array.from({ length: 12 }, (_, r) => r).map((r) => "
                       "Array.from({ length: 12 }, (_, c) => c).map((c) => {\n"
                       "        const n = r * 12 + c + 1;\n"
                       "        if (n > 12) return { testo: \"\" };")
    u = _gioco(tmp, "griglia", grande, test="").test()["uscita"]
    verifica("una griglia 12×12 con troppo testo sopra: FALLITO, «usa meno righe o colonne»",
             "FALLITO prova di fumo del gioco" in u and "la griglia 12×12 non ci sta" in u
             and "palco: fase «tabellone»" in u, u[-600:])
    test_palco = ('const { test } = require("node:test");\nconst assert = require("node:assert");\n'
                  'test("palco", async () => { const g = await apriGioco(); await g.tocca("2 giocatori"); '
                  'await g.tocca("Parti"); const d = g.palco(); assert.ok(d.length > 0); '
                  'assert.match(d.join(" "), /il titolo «Che colore scegli\\?/); '
                  'assert.match(d[0], /^(orizzontale|verticale)|nella pagina/); });\n')
    r = _gioco(tmp, "g_palco", lungo, test=test_palco).test(fumo=False)
    verifica("g.palco() nei test dice i difetti della pagina di adesso",
             r["passano"] and "ok palco" in r["uscita"], r["uscita"][-400:])


# ═══════════════════════════ 3. il server ═══════════════════════════

def prova_server(tmp: Path):
    sezione("3. il server: la diagnosi del palco anche in prova, il ponte no")
    from prova_giochi import Ambiente, file_gioco
    from calliope.estensioni.manifesto import valida
    a = Ambiente(tmp)
    try:
        A = a.abbina("A", "studio")
        mp, _ = file_gioco("pagine")
        out = a.giochi.avvia_prova(a.chi("Dario", schermo=A), "pagine", 1, valida(mp))
        pp = out["partita"]
        a.pagina(A, {"partita": pp, "tipo": "pronto"})
        r = a.pagina(A, {"partita": pp, "tipo": "palco",
                         "difetti": ["testo tagliato sullo schermo: <h1 class=\"titolo\">"]})
        rs = a.pagina(A, {"partita": pp, "tipo": "salva", "chiave": "x", "valore": 1})
        verifica("partita di prova: «palco» passa e resta sul posto, «salva» no",
                 r.get("ok") and a.giochi.partite[pp].posti[A["id"]].palco
                 and rs.get("_stato") == 403, f"{r} {rs}")
    finally:
        from calliope import minori as M
        for s in ("regole", "avvisi", "gioco", "richieste"):
            x = M._SERVIZIO.get(s)
            if x is not None:
                try:
                    x.close()
                except Exception:  # noqa: BLE001
                    pass
        a.hub.archivio.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-palco-"))
    try:
        prova_impaginazione(radice / "impagina")
        prova_fumo(radice / "fumo")
        prova_server(radice / "server")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
