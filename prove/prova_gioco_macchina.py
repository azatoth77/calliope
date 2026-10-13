"""Prova a secco della macchina a stati dei giochi (13/10/2026; progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md, area docs/aree/giochi.md).

1. **Il manifesto** (calliope/estensioni/macchina.py): la macchina del gioco delle prove
   (`prove/giochi/porte_fasi`) è valida, i comandi a voce piatti che Calliope ricava (slot
   espansi, comandi standard) sono gli stessi che il motore conosce; chi approva sente «si gioca
   a voce o toccando». Contrari: `ascolta` con `macchina`, una fase di Calliope dichiarata,
   «verso» e «inizio» verso fasi che non ci sono, un comando con il nome di uno standard, {n}
   senza «n» e «n» senza {n}, {n} da solo con troppi valori, una forma uguale a una standard o
   riservata («basta»), troppi comandi, una pagina sconosciuta, una fase senza comandi, esito_s.
2. **Il documento del riquadro**: runtime, motore, logica, avvio in quest'ordine, ognuno con la
   sua impronta nella CSP; un gioco senza macchina resta com'era.
3. **Il nucleo** (motore_gioco.js, in Node): preparazione, turni, esito con il turno che passa
   all'uscita, punti, fine con la classifica e «ancora», comandi non attivi rifiutati; la forma
   dei risultati: l'esito annidato del 12/10 (campi sconosciuti), «dati» mancante, una fase
   fuori da «verso», attivi che allarga, vista con un oggetto; la tela che esce.
4. **La prova di fumo per fasi** (fumo_js.mjs, esplora): il gioco giusto passa; contrari: esito
   annidato, fase senza uscita, fase mai raggiunta, comando mai attivo, partita che non finisce,
   mossa che lancia con file:riga, attivi fuori dal dominio.
5. **apriGioco** con la macchina: tocchi sui pulsanti del motore, g.stato(), g.comando con il
   valore, l'esito che va avanti da solo dopo esito_s; g.stato() su un gioco senza macchina.

    python prove/prova_gioco_macchina.py
"""

import copy
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
PORTE = RADICE / "prove" / "giochi" / "porte_fasi"
MOTORE = RADICE / "calliope" / "estensioni" / "motore_gioco.js"
FUMO = RADICE / "calliope" / "agenti" / "fumo_js.mjs"
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def manifesto() -> dict:
    return json.loads((PORTE / "manifesto.json").read_text(encoding="utf-8"))


def logica() -> str:
    return (PORTE / "logica.js").read_text(encoding="utf-8")


def node(tmp: Path, codice: str) -> tuple[int, str]:
    tmp.mkdir(parents=True, exist_ok=True)
    f = tmp / "prova.mjs"
    f.write_text(codice, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ═══════════════════════════ 1. il manifesto ═══════════════════════════

def prova_manifesto(tmp: Path):
    from calliope.estensioni import scheda
    sezione("1. il manifesto: scheda.macchina")
    m = manifesto()
    s = scheda.normalizza(m["scheda"], {})
    a = s.get("ascolta") or {}
    piatti = list(a.get("comandi") or {})
    verifica("la macchina delle porte è valida, con l'elenco piatto dei comandi a voce",
             s.get("macchina", {}).get("inizio") == "turno" and "porta_6" in piatti
             and "giocatori_4" in piatti and "avanti" in piatti and "ancora" in piatti
             and "porta_7" not in piatti, str(piatti))
    verifica("…le forme espanse sul dominio («la porta 3», «3»)",
             a["comandi"].get("porta_3") == ["porta 3", "la porta 3", "3"], str(a["comandi"].get("porta_3")))
    from calliope import gioco_voce
    verifica("…riconosciute per intero: «Calliope, la porta tre» → porta_3, «tre gatti» no",
             gioco_voce.trova("Calliope, la porta tre", a["comandi"]) == "porta_3"
             and gioco_voce.trova("tre gatti", a["comandi"]) is None
             and gioco_voce.trova("siamo in due", a["comandi"]) == "giocatori_2")
    voci = scheda.in_parole({"scheda": s})
    verifica("chi approva sente «si gioca a voce o toccando, con una fase e un comando»",
             any("si gioca a voce o toccando, con una fase e un comando" in v for v in voci),
             str(voci))
    if shutil.which("node"):
        rc, out = node(tmp / "piatti", (
            f"import {{ tuttiPiatti }} from {json.dumps(FUMO.as_uri())};\n"
            f"console.log(JSON.stringify(tuttiPiatti({json.dumps(m['scheda']['macchina'])}, 1, 4)));\n"))
        try:
            js = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            js = None
        verifica("gli stessi comandi piatti in Python (macchina.ascolta) e nel motore "
                 "(tuttiPiatti)", js is not None and sorted(js) == sorted(piatti),
                 f"{js} != {piatti}")

    def rifiutata(nome, modifica, attesa):
        sc = copy.deepcopy(m["scheda"])
        modifica(sc)
        try:
            scheda.normalizza(sc, {})
        except scheda.SchedaNonValida as e:
            verifica(f"contrario: {nome}", attesa in str(e), str(e)[:200])
            return
        verifica(f"contrario: {nome}", False, "accettata")

    T = lambda sc: sc["macchina"]["fasi"]["turno"]  # noqa: E731
    P = lambda sc: T(sc)["comandi"]["porta"]  # noqa: E731
    rifiutata("«ascolta» insieme alla macchina",
              lambda sc: sc.update(ascolta={"comandi": {"uno": ["uno"]}}), "non va con «macchina»")
    rifiutata("una fase di Calliope dichiarata dal gioco",
              lambda sc: sc["macchina"]["fasi"].update(esito={"comandi": {"x": ["x"]}}),
              "è una fase di Calliope")
    rifiutata("«verso» una fase che non c'è",
              lambda sc: T(sc).update(verso=["bonus"]), "fasi che non ci sono: bonus")
    rifiutata("«inizio» che non è una fase", lambda sc: sc["macchina"].update(inizio="via"),
              "una delle fasi dichiarate")
    rifiutata("un comando con il nome di uno standard",
              lambda sc: T(sc)["comandi"].update(avanti={"forme": ["vai"]}),
              "è un comando di Calliope")
    rifiutata("{n} in una forma senza «n»",
              lambda sc: T(sc)["comandi"].update(salta={"forme": ["salta {n}"]}),
              "ma il comando non ha «n»")
    rifiutata("«n» con una forma senza {n}",
              lambda sc: P(sc)["forme"].append("apri"), "ogni forma ha {n} una volta")
    rifiutata("{n} da solo con più di 12 valori",
              lambda sc: P(sc).update(n={"da": 1, "a": 20}), "da solo solo con al più 12")
    rifiutata("una forma uguale a una di Calliope («avanti»)",
              lambda sc: T(sc)["comandi"].update(passo={"forme": ["avanti"]}),
              "vale sia per")
    rifiutata("una forma riservata («basta»)",
              lambda sc: T(sc)["comandi"].update(stop={"forme": ["basta"]}),
              "ferma la voce")
    rifiutata("troppi comandi a voce con gli slot espansi",
              lambda sc: T(sc)["comandi"].update(
                  casella={"forme": ["casella {n}"], "n": {"da": 1, "a": 60}}),
              "troppi comandi a voce")
    rifiutata("una pagina sconosciuta", lambda sc: T(sc).update(pagina="podio"),
              "una tra scelte, messaggio, tela")
    rifiutata("una fase senza comandi (non tela)",
              lambda sc: sc["macchina"]["fasi"].update(bonus={"verso": ["turno"]}),
              "almeno un comando")
    rifiutata("esito_s fuori misura", lambda sc: sc["macchina"].update(esito_s=99),
              "da 0 a 30 secondi")
    sc = copy.deepcopy(m["scheda"])
    sc["macchina"]["fasi"]["gioco"] = {"pagina": "tela", "verso": ["fine"]}
    s2 = scheda.normalizza(sc, {})
    verifica("contrario: una fase «tela» senza comandi va, e porta «fine partita» tra i "
             "comandi a voce", "fine_partita" in s2["ascolta"]["comandi"])


# ═══════════════════════════ 2. il documento ═══════════════════════════

def prova_documento():
    from calliope.estensioni import scheda
    sezione("2. il documento del riquadro")
    m = manifesto()
    sc = copy.deepcopy(m["scheda"])
    sc["macchina"]["fasi"]["turno"]["comandi"]["porta"]["etichetta"] = "</script> {n}"
    s = scheda.normalizza(sc, {})
    html, csp = scheda.documento(s, {"logica.js": logica().encode("utf-8")})
    pezzi = html.split("<script>")[1:]
    verifica("quattro script: runtime, motore, logica, avvio",
             len(pezzi) == 4 and "Object.defineProperty(window, \"calliope\"" in pezzi[0]
             and "CalliopeMotore" in pezzi[1] and "const GIOCO" in pezzi[2]
             and pezzi[3].startswith("CalliopeMotore.avvia("), str([p[:40] for p in pezzi]))
    verifica("ogni script con la sua impronta nella CSP", csp.count("'sha256-") == 4)
    verifica("«</script» dentro la macchina non chiude il tag",
             html.count("</script>") == 4 and "<\\/script> {n}" in html)
    verifica("lo stile del motore c'è", ".motore .comando" in html)
    vecchio = scheda.normalizza({"tipo": "gioco", "file": ["logica.js", "gioco.js"]}, {})
    html2, csp2 = scheda.documento(vecchio, {"logica.js": b"var a=1;", "gioco.js": b"var b=2;"})
    verifica("contrario: un gioco senza macchina resta com'era (niente motore)",
             "CalliopeMotore" not in html2 and csp2.count("'sha256-") == 3)


# ═══════════════════════════ 3. il nucleo ═══════════════════════════

NUCLEO = r"""
import { readFileSync } from "node:fs";
import vm from "node:vm";
const ctx = vm.createContext({ console, JSON, Math });
vm.runInContext(readFileSync(__MOTORE__, "utf8"), ctx);
vm.runInContext(__LOGICA__, ctx);
const M = __MACCHINA__;
const out = {};
const prova = (nome, f) => { try { out[nome] = f(); } catch (e) { out[nome] = "ERRORE: " + e.message; } };
const crea = (G2, M2) => ctx.CalliopeMotore.crea(G2 || vm.runInContext("GIOCO", ctx), M2 || M, { min: 1, max: 4 });
const nu = crea();
prova("partita", () => {
  let S = nu.nuovo();
  const r = { prep: nu.piatti(nu.attivi(S)) };
  S = nu.applica(S, "giocatori", 2);
  r.inizio = nu.istantanea(S);
  S = nu.applica(S, "porta", 2);
  r.esito = nu.istantanea(S);
  S = nu.applica(S, "avanti");
  r.dopo = nu.istantanea(S);
  try { nu.applica(S, "porta", 2); r.vecchio = "accettato"; } catch (e) { r.vecchio = e.message; }
  for (const p of [1, 3, 4]) { S = nu.applica(S, "porta", p); S = nu.applica(S, "avanti"); }
  r.fine = nu.istantanea(S);
  r.classifica = nu.classifica(S);
  S = nu.applica(S, "ancora");
  r.ancora = nu.istantanea(S);
  r.piatto = [nu.daPiatto("porta_5"), nu.daPiatto("giocatori_3"), nu.daPiatto("niente")];
  return r;
});
const variante = (mosse, attivi, vista, M2) => {
  const G0 = vm.runInContext("GIOCO", ctx);
  return crea({ ...G0, mosse: mosse || G0.mosse, attivi: attivi || G0.attivi, vista: vista || G0.vista }, M2);
};
const prima = (n2) => n2.applica(n2.nuovo(), "giocatori", 2);
prova("annidato", () => { const n2 = variante({ turno: { porta: (d) => ({ ...d, risultato: { punti: 3 } }) } }); n2.applica(prima(n2), "porta", 1); });
prova("senza_dati", () => { const n2 = variante({ turno: { porta: () => ({ punti: 1 }) } }); n2.applica(prima(n2), "porta", 1); });
prova("fuori_verso", () => { const M2 = JSON.parse(JSON.stringify(M)); M2.fasi.bonus = { comandi: { prendi: ["prendi"] }, verso: ["turno"] }; const n2 = variante({ turno: { porta: (d) => ({ dati: d, fase: "bonus" }) } }, null, null, M2); n2.applica(prima(n2), "porta", 1); });
prova("allarga", () => { const n2 = variante(null, { turno: () => ({ porta: [1], salta: true }) }); n2.attivi(prima(n2)); });
prova("vista", () => { const n2 = variante(null, null, { turno: () => ({ titolo: "x", colore: "rosso" }) }); n2.vista(prima(n2)); });
prova("punti_lista", () => { const n2 = variante({ turno: { porta: (d) => ({ dati: d, punti: [1, 2] }) } }); const S = n2.applica(prima(n2), "porta", 1); return S.giocatori.map((g) => g.punti).join(",") + "|" + S.fase + "|" + S.tocca; });
prova("ancora_stesso", () => { const n2 = variante({ turno: { porta: (d) => ({ dati: d, ancora: true }) } }); const S = n2.applica(prima(n2), "porta", 1); return S.fase + "|" + S.tocca; });
prova("tela", () => {
  const M2 = JSON.parse(JSON.stringify(M)); M2.fasi.turno.verso = ["gioco", "esito", "fine"]; M2.fasi.gioco = { pagina: "tela", verso: ["fine"], comandi: {} };
  const n2 = variante({ turno: { porta: (d) => ({ dati: d, fase: "gioco" }) } }, null, null, M2);
  let S = n2.applica(prima(n2), "porta", 1);
  const att = n2.piatti(n2.attivi(S));
  S = n2.esciTela(S, { dati: { fatto: 1 }, punti: 5, fase: "fine" });
  return att.join(",") + "|" + S.fase + "|" + (S.giocatori[0].punti + S.giocatori[1].punti);
});
console.log(JSON.stringify(out));
"""


def prova_nucleo(tmp: Path):
    sezione("3. il nucleo del motore (Node)")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    codice = (NUCLEO.replace("__MOTORE__", json.dumps(str(MOTORE)))
              .replace("__LOGICA__", json.dumps(logica() + "\nthis.GIOCO = GIOCO;"))
              .replace("__MACCHINA__", json.dumps(manifesto()["scheda"]["macchina"])))
    rc, out = node(tmp / "nucleo", codice)
    try:
        r = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        verifica("il nucleo gira", False, out[-600:])
        return
    p = r.get("partita")
    if not isinstance(p, dict):
        verifica("una partita intera", False, str(p))
        return
    verifica("preparazione: il numero dei giocatori (1–4) e «inizia»",
             p["prep"] == ["giocatori_1", "giocatori_2", "giocatori_3", "giocatori_4", "inizia"],
             str(p["prep"]))
    i = p["inizio"]
    verifica("«2 giocatori»: fase turno, tocca a Giocatore 1, quattro porte attive",
             i["fase"] == "turno" and i["tocca"] == "Giocatore 1" and i["comandi"] == {"porta": [1, 2, 3, 4]}
             and len(i["giocatori"]) == 2, str(i))
    e = p["esito"]
    verifica("una porta: l'esito con il testo, il turno non è ancora passato, solo «avanti»",
             e["fase"] == "esito" and "Dietro la porta 2" in (e["esito"] or "")
             and e["tocca"] == "Giocatore 1" and e["comandi"] == {"avanti": True}, str(e))
    d = p["dopo"]
    verifica("«avanti»: tocca a Giocatore 2, la porta 2 non è più attiva",
             d["fase"] == "turno" and d["tocca"] == "Giocatore 2"
             and d["comandi"] == {"porta": [1, 3, 4]}, str(d))
    verifica("un comando non attivo (la porta già aperta) si rifiuta e lo dice",
             "«porta_2» adesso non vale" in p["vecchio"], p["vecchio"])
    f = p["fine"]
    verifica("aperte tutte: la fine con «ancora»", f["fase"] == "fine"
             and f["comandi"] == {"ancora": True}, str(f))
    cl = p["classifica"]
    verifica("la classifica in ordine di punti", len(cl) == 2
             and cl[0]["punti"] >= cl[1]["punti"], str(cl))
    a = p["ancora"]
    verifica("«ancora»: una partita nuova con gli stessi giocatori e i punti a zero",
             a["fase"] == "turno" and len(a["giocatori"]) == 2
             and all(g["punti"] == 0 for g in a["giocatori"]), str(a))
    verifica("i comandi piatti tornano comando e valore",
             p["piatto"] == [["porta", 5], ["giocatori", 3], None], str(p["piatto"]))
    verifica("l'esito annidato del 12/10: campi sconosciuti, detti con la mossa e la forma "
             "giusta", "GIOCO.mosse.turno.porta (valore 1) restituisce campi che il motore non "
             "conosce: porte" in r["annidato"] and "risultato" in r["annidato"]
             and "{ dati, punti, esito, fase, dopo, ancora }" in r["annidato"], r["annidato"])
    verifica("una mossa senza «dati»", "manca «dati»" in r["senza_dati"], r["senza_dati"])
    verifica("una fase fuori da «verso»", "non è in «verso» della fase «turno»"
             in r["fuori_verso"], r["fuori_verso"])
    verifica("attivi che allarga con un comando non dichiarato",
             "comandi che la fase non dichiara: salta" in r["allarga"], r["allarga"])
    verifica("una vista con campi che il motore non conosce",
             "colore" in r["vista"] and "il disegno è del motore" in r["vista"], r["vista"])
    verifica("punti a tutti con un elenco, il turno passa subito senza esito",
             r["punti_lista"] == "1,2|turno|1", r["punti_lista"])
    verifica("«ancora»: true tiene il turno allo stesso giocatore", r["ancora_stesso"] == "turno|0",
             r["ancora_stesso"])
    verifica("la tela: «fine partita» sempre attivo, l'uscita come una mossa",
             r["tela"] == "fine_partita|fine|5", r["tela"])


# ═══════════════════════════ 4. la prova di fumo per fasi ═══════════════════════════

def _gioco(tmp: Path, nome: str, logica_js: str, macchina: dict | None = None,
           test_gioco: str | None = None):
    m = manifesto()
    if macchina is not None:
        m["scheda"]["macchina"] = macchina
    file = {"logica.js": logica_js, "manifesto.json": json.dumps(m),
            "logica.test.js": (PORTE / "logica.test.js").read_text(encoding="utf-8")}
    if test_gioco is not None:
        file["gioco.test.js"] = test_gioco
    sb = G.sandbox(tmp, nome)
    for k, v in file.items():
        sb.scrivi(k, v)
    return sb


def prova_fumo(tmp: Path):
    sezione("4. la prova di fumo per fasi")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    L = logica()
    r = _gioco(tmp, "giusto", L).test()
    verifica("il gioco delle porte passa la logica e la prova di fumo per fasi",
             r["passano"] and "ok prova di fumo del gioco" in r["uscita"], r["uscita"][-500:])
    casi = {
        "annidato": (L.replace("return { dati: { ...d, aperte }, punti, esito:",
                               "return { ...d, aperte, punti, esito:"), None,
                     ["fase «turno», comando «porta_1»", "campi che il motore non conosce: porte"]),
        "senza uscita": (L.replace("turno: (d) => ({ porta: chiuse(d) }),",
                                   "turno: (d) => ({ porta: chiuse(d).slice(1) }),"), None,
                         ["fase «turno» senza uscita", "strada:"]),
        "lancia": (L.replace("const [cosa, punti] = SORPRESE[d.dietro[valore - 1]];",
                             "if (valore === 3) d.nulla.x = 1;\n"
                             "        const [cosa, punti] = SORPRESE[d.dietro[valore - 1]];"), None,
                   ["comando «porta_3»", "TypeError", "logica.js:19"]),
        "fuori dominio": (L.replace("turno: (d) => ({ porta: chiuse(d) }),",
                                    "turno: (d) => ({ porta: chiuse(d).concat([9]) }),"), None,
                          ["valori fuori da quelli dichiarati nel manifesto: [9]"]),
        "non finisce": (L.replace("dopo: finite ? \"fine\" : \"turno\"", "dopo: \"turno\"")
                        .replace("const aperte = d.aperte.concat([valore]);",
                                 "const aperte = d.aperte.length >= d.porte - 1 ? [] : "
                                 "d.aperte.concat([valore]);"), None,
                        ["non arriva alla fine in 500 passi"]),
    }
    M = manifesto()["scheda"]["macchina"]
    mai = copy.deepcopy(M)
    mai["fasi"]["bonus"] = {"comandi": {"prendi": ["prendi"]}, "verso": ["turno"]}
    casi["fase mai raggiunta"] = (L.replace("vista: {", "mosse_bonus: null,\n  vista: {")
                                  .replace("  mosse: {\n", "  mosse: {\n    bonus: { prendi: (d) => "
                                           "({ dati: d, fase: \"turno\" }) },\n"), mai,
                                  ["fase «bonus»", "dichiarata ma mai raggiunta"])
    mai_att = copy.deepcopy(M)
    mai_att["fasi"]["turno"]["comandi"]["salta"] = {"forme": ["salta"]}
    casi["comando mai attivo"] = (L.replace("turno: (d) => ({ porta: chiuse(d) }),",
                                            "turno: (d) => ({ porta: chiuse(d), salta: false }),")
                                  .replace("    turno: {\n      porta(",
                                           "    turno: {\n      salta: (d) => ({ dati: d }),\n"
                                           "      porta("), mai_att,
                                  ["comando «turno.salta»", "mai attivo"])
    for nome, (codice, mac, attese) in casi.items():
        u = _gioco(tmp, "fumo_" + nome.replace(" ", "_"), codice, mac).test()["uscita"]
        ok = "FALLITO prova di fumo del gioco" in u and all(a in u for a in attese)
        verifica(f"contrario: {nome}", ok, u[-700:])


# ═══════════════════════════ 5. apriGioco ═══════════════════════════

def prova_apri(tmp: Path):
    sezione("5. apriGioco con la macchina")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    t = (PORTE / "gioco.test.js").read_text(encoding="utf-8")
    r = _gioco(tmp, "apri", logica(), test_gioco=t).test()
    verifica("il test del disegno delle porte: tocchi, g.stato(), g.comando con il valore, "
             "l'esito che va avanti da solo", r["passano"]
             and "ok toccando una porta si vede cosa c'è dietro" in r["uscita"], r["uscita"][-500:])
    corpo = ('const { test } = require("node:test");\nconst assert = require("node:assert");\n'
             'test("x", async () => { const g = await apriGioco(); await g.tocca("Inizia"); '
             'assert.strictEqual(g.stato().fase, "turno"); await g.comando("porta", 9); });\n')
    u = _gioco(tmp, "apri_non_attivo", logica(), test_gioco=corpo).test(fumo=False)["uscita"]
    verifica("un comando con un valore non attivo lo dice", "il comando «porta_9» adesso non è "
             "attivo" in u, u[-300:])
    corpo = ('const { test } = require("node:test");\n'
             'test("x", async () => { const g = await apriGioco(); g.stato(); });\n')
    sb = G.sandbox(tmp, "apri_vecchio")
    for k, v in {"logica.js": "var a = 1;\n", "gioco.js": "calliope.quandoPronto(() => { "
                 "document.getElementById('gioco').textContent = 'ciao'; });\n",
                 "manifesto.json": json.dumps({"scheda": {"file": ["logica.js", "gioco.js"]}}),
                 "x.test.js": corpo}.items():
        sb.scrivi(k, v)
    u = sb.test(fumo=False)["uscita"]
    verifica("contrario: g.stato() su un gioco senza macchina lo dice",
             "solo per un gioco con «scheda.macchina»" in u, u[-300:])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-macchina-"))
    try:
        prova_manifesto(radice / "manifesto")
        prova_documento()
        prova_nucleo(radice / "nucleo")
        prova_fumo(radice / "fumo")
        prova_apri(radice / "apri")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
