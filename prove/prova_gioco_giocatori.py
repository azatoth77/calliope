"""Chi è quale giocatore e «Gira il telefono» (15/10/2026, roadmap 1.4, il resto del progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md; area docs/aree/giochi.md), a secco.

1. **Il motore** (motore_gioco.js nel DOM finto di fumo_js.mjs, Node), i quattro casi:
   - *due schermi, due persone* (partita condivisa: chi la tiene e uno specchio): «Gioco
     anch'io» toccato su ogni schermo lega un giocatore a quello schermo; la mossa dallo schermo
     dell'altro giocatore non parte (un avviso sul palco, nessuna mossa al server), quella dal
     proprio sì; la mossa arrivata da un altro schermo (il server ci mette il numero) è
     rifiutata («schermo»); il nome del giocatore di questo schermo è segnato nella fascia;
   - *uno schermo, due persone*: «gioco anch'io» detto da due voci riconosciute lega ognuna al
     suo giocatore (un segno opaco, mai il nome se il manifesto non lo chiede); la mossa detta
     dalla voce dell'altro giocatore è rifiutata («turno»), quella senza voce riconosciuta e il
     tocco valgono per chi è di turno;
   - *un ospite senza nome*: «Gioco anch'io» toccato → «Giocatore 2», gioca toccando;
   - *chi entra a metà*: «gioco anch'io» a partita cominciata (solo a voce, nessun pulsante in
     più): senza GIOCO.entra entra dalla prossima partita (avviso, poi «ancora» con tre), con
     GIOCO.entra subito (a zero punti, il suo turno arriva); la stessa voce due volte no
     («gia»); g.stato() dei test dell'agente non lo vede.
   Ogni istantanea passa la validazione del server (andata e ritorno con Python).
2. **Il server** (calliope/schermi/giochi.py, macchina.py): la validazione dei legami (schermo,
   voce) e i contrari; `chi_muove` come il motore; il comando a voce porta il segno della voce
   (in un gioco per più giocatori) e, tra più schermi, il numero dello schermo; un segno che
   Calliope non ha dato non lega nessuno; `turno_altrui` («Tocca ad Ada.», «…, sullo schermo
   …», «Sei già nella partita…»).
3. **Le domande** (calliope/gioco_stato.py): «a chi tocca?» → «Tocca a te.» dalla voce legata,
   «Tocca a Bruno, sullo schermo …» per il giocatore di un altro schermo; «che giocatore
   sono?» dalla voce o dallo schermo.
4. **Nel ciclo** (ciclo.py con ascolto, Whisper, voce e Brain finti): la mossa detta dalla voce
   dell'altro giocatore non va al gioco e Calliope dice «Tocca ad Ada.» (regola
   gioco_turno_altrui, niente testo nel registro); quella di chi è di turno sì, con il segno;
   «Che giocatore sono?» senza il modello.
5. **«Gira il telefono»**: la tela che dichiara un orientamento (manifesto validato: solo una
   tela, solo i due valori); sul telefono in verticale il palco resta orizzontale, la fascia
   «Gira il telefono in orizzontale» compare e Calliope lo sa una volta sola (anche girando e
   rigirando), girato il telefono la fascia sparisce; su un PC con la finestra alta niente
   fascia; la prova di fumo misura la tela solo nel suo orientamento. Sul server la frase a
   voce una volta per schermo (regola gioco_gira_telefono), anche in una partita di prova;
   contrari: un orientamento inventato.

    python prove/prova_gioco_giocatori.py
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

from prova_giochi import Ambiente, file_gioco  # noqa: E402

from calliope.estensioni import macchina as mc  # noqa: E402
from calliope.estensioni.manifesto import valida  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
FUMO = RADICE / "calliope" / "agenti" / "fumo_js.mjs"
GIOCHI = RADICE / "prove" / "giochi"
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def node(tmp: Path, codice: str) -> dict:
    tmp.mkdir(parents=True, exist_ok=True)
    f = tmp / "prova.mjs"
    f.write_text(codice, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8",
                       timeout=120)
    testo = (r.stdout or "") + (r.stderr or "")
    riga = next((x for x in testo.splitlines() if x.startswith("JSON")), None)
    if r.returncode != 0 or riga is None:
        return {"_errore": testo[-1500:]}
    return json.loads(riga[4:])


def opzioni(cartella: Path, **extra) -> tuple[list[str], dict]:
    m = json.loads((cartella / "manifesto.json").read_text(encoding="utf-8"))
    sc = m["scheda"]
    file = [str(cartella / f) for f in sc["file"]]
    return file, {"macchina": sc["macchina"], "minimo": sc["giocatori"]["min"],
                  "massimo": sc["giocatori"]["max"], "titolo": m["titolo"], "seme": 7, **extra}


# Aiuti nel programma Node: l'ultima istantanea, un comando come lo manda il server
AIUTI = """
const ultima = (g) => g.calliope.istantanee().slice(-1)[0];
const n = (g) => ultima(g).n;
async function voce(g, comando, extra) { await g.calliope.comando({ comando, n: n(g), ...(extra || {}) }); }
async function inoltra(gA, gB) { await gB.calliope.evento("partita", { stato: gA.calliope.riprese().slice(-1)[0] }); }
async function mosseB(gA, gB, da, schermo) {
  for (const m of gB.calliope.mosse().slice(da)) await gA.calliope.comando({ ...m, schermo });
}
"""


def js(file, opz, corpo: str) -> str:
    return (f"import {{ apriGioco, fumo }} from {json.dumps(FUMO.as_uri())};\n"
            f"const F = {json.dumps(file)}; const O = {json.dumps(opz)};\n" + AIUTI
            + "const out = {};\n" + corpo + "\nconsole.log('JSON' + JSON.stringify(out));\n")


def andata_e_ritorno(nome, istantanee, cartella="porte_fasi"):
    m, g = valida(file_gioco(cartella)[0])["scheda"]["macchina"], \
        valida(file_gioco(cartella)[0])["scheda"]["giocatori"]
    ultimo, scartate = -1, []
    for ist in istantanee:
        try:
            ultimo = mc.valida_istantanea(ist, m, g, ultimo)["n"]
        except mc.IstantaneaNonValida as e:
            scartate.append(f"{ist.get('n')}: {e}")
    verifica(f"{nome}: le {len(istantanee)} istantanee passano la validazione del server",
             not scartate and istantanee, str(scartate)[:300])


# ═══════════════════════════ 1. il motore ═══════════════════════════

def prova_due_schermi(tmp: Path):
    sezione("1a. due schermi, due persone (partita condivisa)")
    file, opz = opzioni(GIOCHI / "porte_fasi", condivisa=True)
    out = node(tmp / "due", js(file, opz, """
const gA = await apriGioco(F, { ...O, posto: 1 });
const gB = await apriGioco(F, { ...O, posto: 2, ruolo: "specchio" });
await inoltra(gA, gB);
await gA.tocca("Gioco anch'io");
await inoltra(gA, gB);
await gB.tocca("Gioco anch'io");
out.mossaB = gB.calliope.mosse().slice(-1)[0];
await mosseB(gA, gB, 0, 2);
await gA.tocca("Inizia");
await inoltra(gA, gB);
out.inizio = ultima(gA);
out.mioA = gA.trova("button.giocatore.mio").map((x) => x.textContent);
out.mioB = gB.trova("button.giocatore.mio").map((x) => x.textContent);
const k = gB.calliope.mosse().length;
await gB.tocca("Porta 1");
out.B_non_tocca = { mosse: gB.calliope.mosse().length - k, testo: gB.testo() };
await gA.tocca("Porta 1");
out.dopoA = ultima(gA);
await gA.avanza(4500);
await inoltra(gA, gB);
out.turno2 = ultima(gA);
const nA = ultima(gA).n;
await gA.tocca("Porta 2");
out.A_non_tocca = { n: ultima(gA).n - nA, testo: gA.testo(), fase: gA.stato().fase };
await voce(gA, "porta_3", { schermo: 1 });
out.rifiuto_schermo = gA.calliope.rifiutati().slice(-1)[0];
await gB.tocca("Porta 2");
await mosseB(gA, gB, k, 2);
out.dopoB = ultima(gA);
out.tutte = gA.calliope.istantanee();
out.errori = gA.errori.length + gB.errori.length;
"""))
    if "_errore" in out:
        verifica("due motori nel DOM finto", False, out["_errore"])
        return
    verifica("«Gioco anch'io» toccato sullo specchio: la mossa al motore che tiene la partita",
             out["mossaB"].get("comando") == "anchio", str(out["mossaB"]))
    gs = out["inizio"]["giocatori"]
    verifica("«Inizia»: due giocatori, ognuno legato al suo schermo (1 e 2)",
             [g.get("schermo") for g in gs] == [1, 2] and out["inizio"]["fase"] == "turno",
             str(gs))
    verifica("la fascia segna il giocatore di questo schermo («mio»), diverso sui due",
             out["mioA"] and out["mioB"] and out["mioA"] != out["mioB"]
             and "Giocatore 1" in out["mioA"][0] and "Giocatore 2" in out["mioB"][0],
             f"{out['mioA']} {out['mioB']}")
    verifica("tocca al giocatore 1: lo specchio (giocatore 2) che tocca «Porta 1» non manda la "
             "mossa, e lo dice sul palco",
             out["B_non_tocca"]["mosse"] == 0
             and "Tocca a Giocatore 1, sull'altro schermo" in out["B_non_tocca"]["testo"],
             str(out["B_non_tocca"])[:200])
    verifica("…dal proprio schermo sì", out["dopoA"]["fase"] == "esito")
    verifica("poi tocca al giocatore 2: chi tiene la partita (schermo 1) non muove per lui",
             out["turno2"]["tocca"] == 1 and out["A_non_tocca"]["n"] == 0
             and out["A_non_tocca"]["fase"] == "turno"
             and "Tocca a Giocatore 2" in out["A_non_tocca"]["testo"], str(out["A_non_tocca"])[:200])
    verifica("una mossa arrivata dallo schermo 1 per il giocatore 2 è rifiutata («schermo»)",
             (out["rifiuto_schermo"] or {}).get("motivo") == "schermo", str(out["rifiuto_schermo"]))
    verifica("la mossa del giocatore 2 dal suo schermo (specchio → server → motore) vale",
             out["dopoB"]["fase"] == "esito" and out["dopoB"]["n"] > out["turno2"]["n"],
             str(out["dopoB"]))
    verifica("nessun errore del gioco (gli avvisi sui turni non sono errori)", out["errori"] == 0)
    andata_e_ritorno("due schermi", out["tutte"])


def prova_uno_schermo(tmp: Path):
    sezione("1b. uno schermo, due persone (la voce); un ospite senza nome")
    file, opz = opzioni(GIOCHI / "porte_fasi")
    out = node(tmp / "uno", js(file, opz, """
const g = await apriGioco(F, O);
await voce(g, "anchio", { voce: "v1" });
await voce(g, "anchio", { voce: "v2" });
await voce(g, "anchio", { voce: "v2" });
await g.tocca("Inizia");
out.inizio = ultima(g);
out.testo = g.testo();
await voce(g, "porta_1", { voce: "v2" });
out.rifiuto_voce = g.calliope.rifiutati().slice(-1)[0];
out.dopo_rifiuto = ultima(g).fase;
await voce(g, "porta_1", { voce: "v1" });
out.mossa_v1 = ultima(g).fase;
await g.avanza(4500);
await g.tocca("Porta 2");
out.tocco = ultima(g).fase;
await g.avanza(4500);
await voce(g, "porta_3");
out.senza_voce = ultima(g).fase;
out.tutte = g.calliope.istantanee();
out.stato = g.stato();
out.errori = g.errori.length;
const h = await apriGioco(F, O);
await voce(h, "anchio", { voce: "v1", giocatore: "Ada" });
await h.tocca("Gioco anch'io");
await h.tocca("Inizia");
out.ospite = ultima(h).giocatori;
await h.tocca("Porta 1");
out.ospite_fase = ultima(h).fase;
"""))
    if "_errore" in out:
        verifica("il motore nel DOM finto", False, out["_errore"])
        return
    gs = out["inizio"]["giocatori"]
    verifica("due voci con «gioco anch'io»: due giocatori, ognuno con il suo segno (la stessa "
             "voce due volte non prende due posti); niente schermo in una partita di uno schermo",
             [g.get("voce") for g in gs] == ["v1", "v2"]
             and not any("schermo" in g for g in gs), str(gs))
    verifica("il segno della voce non si vede sullo schermo", "v1" not in out["testo"])
    verifica("tocca al giocatore della voce v1: la mossa detta da v2 è rifiutata («turno») e la "
             "partita non cambia", (out["rifiuto_voce"] or {}).get("motivo") == "turno"
             and out["dopo_rifiuto"] == "turno", str(out["rifiuto_voce"]))
    verifica("…detta da v1 sì", out["mossa_v1"] == "esito")
    verifica("il tocco vale per chi è di turno (uno schermo solo: non si sa chi tocca)",
             out["tocco"] == "esito")
    verifica("una mossa senza voce riconosciuta (una parola sola) vale per chi è di turno",
             out["senza_voce"] == "esito")
    verifica("g.stato() dei test dell'agente non ha i segni né «gioco anch'io»",
             "voce" not in json.dumps(out["stato"]) and "anchio" not in out["stato"]["comandi"],
             str(out["stato"])[:200])
    verifica("nessun errore del gioco", out["errori"] == 0)
    andata_e_ritorno("uno schermo", out["tutte"])
    o = out["ospite"]
    verifica("un ospite senza nome: «Gioco anch'io» toccato → «Giocatore 2», e Ada con il nome",
             [g["nome"] for g in o] == ["Ada", "Giocatore 2"] and o[0].get("voce") == "v1"
             and "voce" not in o[1], str(o))
    verifica("…e si gioca toccando", out["ospite_fase"] == "esito")


def prova_entra(tmp: Path):
    sezione("1c. chi entra a partita cominciata («gioco anch'io»)")
    file, opz = opzioni(GIOCHI / "porte_fasi")
    out = node(tmp / "entra", js(file, opz, """
const g = await apriGioco(F, O);
await voce(g, "anchio", { voce: "v1" });
await voce(g, "anchio", { voce: "v2" });
await g.tocca("Inizia");
out.pulsanti = g.trova("button").map((x) => x.textContent);
out.comandi = ultima(g).comandi;
await voce(g, "anchio", { voce: "v3" });
out.avviso = g.testo();
out.dopo = ultima(g).giocatori.length;
await voce(g, "anchio", { voce: "v3" });
out.di_nuovo = g.calliope.rifiutati().slice(-1)[0];
await voce(g, "anchio", { voce: "v1" });
out.gia = g.calliope.rifiutati().slice(-1)[0];
for (let i = 0; i < 20 && ultima(g).fase !== "fine"; i++) {
  const s = ultima(g);
  const c = s.comandi.find((x) => x.startsWith("porta_")) || "avanti";
  const chi = s.fase === "turno" ? s.giocatori[s.tocca].voce : null;
  await voce(g, c, chi ? { voce: chi } : {});
}
out.fine = ultima(g);
await voce(g, "ancora");
out.ancora = ultima(g).giocatori;
out.errori = g.errori.length;
"""))
    if "_errore" in out:
        verifica("il motore nel DOM finto", False, out["_errore"])
        return
    verifica("a partita cominciata nessun pulsante «Gioco anch'io» (la pagina non cambia), ma "
             "Calliope lo sente a voce", not any("anch" in p for p in out["pulsanti"])
             and "anchio" in out["comandi"], f"{out['pulsanti']} {out['comandi']}")
    verifica("senza GIOCO.entra si entra dalla prossima partita: un avviso, i giocatori restano "
             "due", out["dopo"] == 2 and "dalla prossima partita" in out["avviso"],
             out["avviso"][:200])
    verifica("la stessa voce due volte no, e chi gioca già neanche («gia»)",
             (out["di_nuovo"] or {}).get("motivo") == "gia"
             and (out["gia"] or {}).get("motivo") == "gia", f"{out['di_nuovo']} {out['gia']}")
    verifica("alla fine «ancora»: si gioca in tre, il terzo con la sua voce",
             out["fine"]["fase"] == "fine" and len(out["ancora"]) == 3
             and out["ancora"][2].get("voce") == "v3", str(out["ancora"]))
    verifica("nessun errore del gioco", out["errori"] == 0)
    # Con GIOCO.entra: si entra subito
    cart = tmp / "entra_subito"
    shutil.copytree(GIOCHI / "porte_fasi", cart, dirs_exist_ok=True)
    lg = (cart / "logica.js").read_text(encoding="utf-8")
    lg = lg.replace("  attivi: {", "  entra(d, ctx) { return { ...d, entrato: ctx.nuovo }; },\n"
                                    "  attivi: {", 1)
    (cart / "logica.js").write_text(lg, encoding="utf-8")
    file, opz = opzioni(cart)
    out = node(tmp / "entra2", js(file, opz, """
const g = await apriGioco(F, O);
await g.tocca("2 giocatori");
await voce(g, "anchio", { voce: "v3", giocatore: "Carla" });
out.subito = ultima(g);
out.ripresa = g.calliope.riprese().slice(-1)[0];
for (let i = 0; i < 4; i++) { const s = ultima(g); await voce(g, s.fase === "esito" ? "avanti" : s.comandi.find((x) => x.startsWith("porta_"))); }
out.tocca = ultima(g).tocca;
out.errori = g.errori.length;
const esp = await fumo(F, O);
out.fumo = esp;
"""))
    if "_errore" in out:
        verifica("il motore nel DOM finto (GIOCO.entra)", False, out["_errore"])
        return
    gs = out["subito"]["giocatori"]
    verifica("con GIOCO.entra si entra subito: Carla terza, a zero punti, con la sua voce, e la "
             "logica lo sa (ctx.nuovo)", [g["nome"] for g in gs] == ["Giocatore 1", "Giocatore 2",
                                                                    "Carla"]
             and gs[2]["punti"] == 0 and gs[2].get("voce") == "v3"
             and (out["ripresa"] or {}).get("dati", {}).get("entrato") == 2, str(gs))
    verifica("…e il suo turno arriva", out["tocca"] == 2, str(out["tocca"]))
    verifica("la prova di fumo per fasi passa con GIOCO.entra (anche «gioco anch'io» a metà)",
             out["fumo"] == [] and out["errori"] == 0, str(out["fumo"])[:300])


# ═══════════════════════════ 2. il server ═══════════════════════════

def stato(a, S, pid, ist, ripresa=None):
    a.giochi.partite[pid].posti[S["id"]].messaggi.clear()
    d = {"partita": pid, "tipo": "stato", "istantanea": ist}
    if ripresa is not None:
        d["ripresa"] = ripresa
    return a.pagina(S, d)


def ist_di(n=3, tocca=0, fase="turno", gs=None, comandi=None):
    return {"n": n, "fase": fase, "tocca": tocca, "turno": 1,
            "giocatori": gs if gs is not None else [
                {"nome": "Ada", "punti": 3, "schermo": 1, "voce": "v1"},
                {"nome": "Bruno", "punti": 5, "schermo": 2, "voce": "v2"}],
            "esito": None, "comandi": comandi or ["porta_1", "porta_3", "porta_4", "anchio"]}


def prova_server(tmp: Path):
    sezione("2. il server: i legami validati, chi muove, il segno e lo schermo nelle mosse")
    m = valida(file_gioco("porte_fasi")[0])["scheda"]
    mm, gg = m["macchina"], m["giocatori"]
    v = mc.valida_istantanea(ist_di(), mm, gg)
    verifica("un'istantanea con schermo e voce dei giocatori passa, i legami restano",
             v["giocatori"][1].get("schermo") == 2 and v["giocatori"][1].get("voce") == "v2")
    for nome, g in (("schermo 0", {"schermo": 0}), ("schermo testo", {"schermo": "2"}),
                    ("schermo vero/falso", {"schermo": True}), ("voce lunga", {"voce": "v123"}),
                    ("voce con il nome", {"voce": "Ada"}), ("campo in più", {"persona": "x"})):
        gs = [dict({"nome": "Ada", "punti": 0}, **g)]
        try:
            mc.valida_istantanea(ist_di(gs=gs), mm, gg)
            ok = False
        except mc.IstantaneaNonValida:
            ok = True
        verifica(f"contrario: un giocatore con {nome} è scartato", ok)
    ist = mc.valida_istantanea(ist_di(), mm, gg)
    casi = [("la voce di chi è di turno", ("porta_1", 2, "v1"), (True, None, 0)),
            ("la voce dell'altro giocatore", ("porta_1", 1, "v2"), (False, "turno", 0)),
            ("lo schermo dell'altro, voce non riconosciuta", ("porta_1", 2, None),
             (False, "schermo", 0)),
            ("il proprio schermo, voce non riconosciuta", ("porta_1", 1, None), (True, None, 0)),
            ("una voce che non gioca, dal proprio schermo", ("porta_1", 1, "v9"),
             (True, None, 0)),
            ("«gioco anch'io» da chi gioca già", ("anchio", 2, "v2"), (False, "gia", 1)),
            ("«gioco anch'io» da una voce nuova", ("anchio", 2, "v3"), (True, None, None))]
    for nome, (c, s, vo), atteso in casi:
        r = mc.chi_muove(ist, mm, c, s, vo)
        verifica(f"chi_muove: {nome}", r == atteso, str(r))
    a = Ambiente(tmp)
    a.installa("porte_fasi", scheda={"condivisa": True})
    A, B = a.abbina("A", "studio"), a.abbina("B", "cucina")
    pid = a.chiama("est_porte_fasi", {}, "Dario", schermo=A)["partita"]
    a.chiama("est_porte_fasi", {}, "Elena", schermo=B)
    p = a.giochi.partite[pid]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    a.pagina(B, {"partita": pid, "tipo": "pronto"})
    stato(a, A, pid, ist_di(n=1, fase="preparazione", tocca=None, gs=[],
                            comandi=["giocatori_2", "anchio", "inizia"]))
    a.eventi.clear()
    a.giochi.comando(pid, B["id"], "anchio", "Elena")
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco" and x[2].get("tipo") == "comando"]
    verifica("«gioco anch'io» sentito dal satellite dello schermo B: al motore che tiene la "
             "partita con il segno della voce e il numero dello schermo, senza il nome (il "
             "manifesto non lo chiede)", e == [{"comando": "anchio", "n": 1, "voce": "v1",
                                                 "schermo": 2}], str(e))
    a.eventi.clear()
    a.giochi.comando(pid, A["id"], "anchio", "Dario")
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco" and x[2].get("tipo") == "comando"]
    verifica("una seconda persona ha un altro segno; la stessa persona lo stesso",
             e and e[0].get("voce") == "v2" and p.voce_di("Elena") == "v1", str(e))
    r = stato(a, A, pid, ist_di(n=2, gs=[{"nome": "Giocatore 1", "punti": 0, "schermo": 2,
                                          "voce": "v1"},
                                         {"nome": "Giocatore 2", "punti": 0, "schermo": 1,
                                          "voce": "v7"}]))
    gs = p.posti[A["id"]].istantanea["giocatori"]
    verifica("un segno di voce che Calliope non ha dato in questa partita non lega nessuno",
             r.get("ok") and gs[0].get("voce") == "v1" and "voce" not in gs[1], str(gs))
    stato(a, A, pid, ist_di(n=3, gs=[{"nome": "Giocatore 1", "punti": 0, "schermo": 2,
                                      "voce": "v1"},
                                     {"nome": "Giocatore 2", "punti": 0, "schermo": 1,
                                      "voce": "v2"}]))
    frase = a.giochi.turno_altrui(pid, A["id"], "porta_1", "Dario")
    verifica("turno_altrui: la voce di Dario (giocatore 2) mentre tocca al giocatore 1 → «Tocca "
             "a Giocatore 1, sullo schermo …»", bool(frase) and frase.startswith(
                 "Tocca a Giocatore 1, sullo schermo"), str(frase))
    frase = a.giochi.turno_altrui(pid, A["id"], "porta_1", None)
    verifica("…senza voce riconosciuta, dallo schermo del giocatore 2: lo stesso",
             bool(frase) and frase.startswith("Tocca a Giocatore 1"), str(frase))
    verifica("…la voce di Elena (di turno) dallo schermo A: vale",
             a.giochi.turno_altrui(pid, A["id"], "porta_1", "Elena") is None)
    verifica("…dallo schermo B senza voce: vale",
             a.giochi.turno_altrui(pid, B["id"], "porta_1", None) is None)
    verifica("«gioco anch'io» da chi gioca già: «Sei già nella partita: sei Giocatore 2.»",
             a.giochi.turno_altrui(pid, A["id"], "anchio", "Dario")
             == "Sei già nella partita: sei Giocatore 2.")
    verifica("«avanti» e i comandi di Calliope valgono per tutti",
             a.giochi.turno_altrui(pid, A["id"], "inizia", "Dario") is None)
    info = a.giochi.ascolto([A["id"]]) or {}
    verifica("Giochi.ascolto: il numero di questo schermo, i nomi degli schermi della partita, "
             "i segni delle voci e quanti possono giocare",
             info.get("posto") == 1 and set(info.get("schermi") or {}) == {1, 2}
             and info.get("voci") == {"Elena": "v1", "Dario": "v2"} and info.get("massimo") == 4,
             str({k: info.get(k) for k in ("posto", "schermi", "voci", "massimo")}))
    a.eventi.clear()
    p.posti[B["id"]].messaggi.clear()
    a.pagina(B, {"partita": pid, "tipo": "mossa", "comando": "porta_3", "n": 3})
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco" and x[2].get("tipo") == "comando"]
    verifica("il tocco su uno specchio arriva al motore con il numero del suo schermo (messo dal "
             "server)", e == [{"comando": "porta_3", "n": 3, "schermo": 2}], str(e))
    # Una partita di uno schermo solo, per un giocatore: niente segno né schermo
    a.installa("porte")
    pid1 = a.chiama("est_porte", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid1, "tipo": "pronto"})
    stato(a, A, pid1, ist_di(n=1, gs=[{"nome": "Dario", "punti": 0}], comandi=["porta_1"]))
    a.eventi.clear()
    a.giochi.comando(pid1, A["id"], "porta_1", "Dario")
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco" and x[2].get("tipo") == "comando"]
    verifica("contrario: un gioco per un giocatore su uno schermo: né segno né schermo (come "
             "prima)", e and "voce" not in e[0] and "schermo" not in e[0], str(e))
    return a


# ═══════════════════════════ 3. le domande ═══════════════════════════

def prova_domande():
    sezione("3. le domande: «a chi tocca?» con il nome, «che giocatore sono?»")
    from calliope import gioco_stato as GS
    ist = {"n": 3, "fase": "turno", "tocca": 1, "turno": 1,
           "giocatori": [{"nome": "Ada", "punti": 3, "schermo": 1, "voce": "v1", "detto": "Ada"},
                         {"nome": "Bruno", "punti": 5, "schermo": 2, "voce": "v2",
                          "detto": "Bruno"}],
           "esito": None, "comandi": ["porta_1", "anchio"]}
    info = {"istantanea": ist, "posto": 1, "schermi": {1: "Studio", 2: "Cucina"},
            "voci": {"Elena": "v1", "Marco": "v2"}, "macchina": None}
    verifica("«a chi tocca?» da Marco (la voce del giocatore Bruno): «Tocca a te.»",
             GS.risposta("tocca", info, "Marco") == "Tocca a te.")
    r = GS.risposta("tocca", info, "Elena")
    verifica("…da Elena allo schermo dello studio: «Tocca a Bruno, sullo schermo «Cucina».»",
             r == "Tocca a Bruno, sullo schermo «Cucina».", r)
    verifica("«quanti punti ho?» da Elena (la voce del giocatore Ada, il nome non c'entra)",
             GS.risposta("punti", info, "Elena") == "Hai 3 punti.")
    verifica("«che giocatore sono?» dalla voce: «Sei Bruno.»",
             GS.risposta("io", info, "Marco") == "Sei Bruno.")
    verifica("…senza voce riconosciuta, dallo schermo: «Su questo schermo gioca Ada.»",
             GS.risposta("io", info, None) == "Su questo schermo gioca Ada.")
    info2 = dict(info, posto=3)
    r = GS.risposta("io", info2, None)
    verifica("…da uno schermo senza giocatori: come entrare", "gioco anch'io" in r, r)
    verifica("le forme della domanda, per intero; contrario dentro una frase più lunga",
             GS.domanda("Calliope, che giocatore sono?") == "io"
             and GS.domanda("Quale giocatore sono io?") == "io"
             and GS.domanda("che giocatore sono stato ieri?") is None)


# ═══════════════════════════ 4. nel ciclo ═══════════════════════════

def prova_ciclo(tmp: Path):
    import prova_gioco_voce as PV
    sezione("4. nel ciclo: la mossa dell'altro giocatore, «che giocatore sono?»")
    a = Ambiente(tmp)
    a.installa("porte_fasi")
    A = a.abbina("A", "studio")
    sat = a.hub.satelliti = PV.Satelliti({7: PV.Coll(id=7, schermo_id=A["id"], stanza="studio")})
    turni = []
    c, stt, voce, cervello, ascolto = PV.nuovo_ciclo(a, sat, 7, turni)
    a.cfg.giochi_ascolto_s = 60.0
    chi = {"nome": None}
    c._giocatore_dalla_voce = lambda t: chi["nome"]
    pid = a.chiama("est_porte_fasi", {}, "Dario", schermo=A)["partita"]
    p = a.giochi.partite[pid]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    va, vb = p.voce_di("Ada"), p.voce_di("Bruno")
    stato(a, A, pid, ist_di(n=4, tocca=0, gs=[
        {"nome": "Giocatore 1", "punti": 0, "voce": va},
        {"nome": "Giocatore 2", "punti": 0, "voce": vb}]))

    def giro(frase, nome):
        chi["nome"] = nome
        c.awake_until = 0.0
        stt.frasi.append(frase)
        a.eventi.clear()
        n, m_ = len(voce.detto), len(cervello.richieste)
        c.giro()
        return (voce.detto[n:], cervello.richieste[m_:],
                [x[2]["dati"] for x in a.eventi if x[1] == "gioco"
                 and x[2].get("tipo") == "comando"])
    detto, chiesto, mosse = giro("Porta tre.", "Bruno")
    verifica("«Porta tre.» detta da Bruno mentre tocca al giocatore di Ada: nessuna mossa, "
             "Calliope dice «Tocca a Giocatore 1.» senza il modello (regola gioco_turno_altrui, "
             "niente testo nel registro)",
             not mosse and not chiesto and "Tocca a Giocatore 1." in " ".join(map(str, detto))
             and c.rec.get("esito") == "gioco_turno_altrui" and c.rec.get("testo") is None
             and "gioco_turno_altrui" in (c.rec.get("regole") or []),
             f"{detto} {chiesto} {mosse} {c.rec.get('esito')}")
    detto, chiesto, mosse = giro("Porta tre.", "Ada")
    verifica("…detta da Ada: la mossa, con il segno della sua voce e niente nome",
             mosse == [{"comando": "porta_3", "n": 4, "voce": va}] and not detto,
             f"{mosse} {detto}")
    detto, chiesto, mosse = giro("Porta uno.", None)
    verifica("…senza voce riconosciuta: la mossa per chi è di turno (il motore decide)",
             mosse == [{"comando": "porta_1", "n": 4}], str(mosse))
    detto, chiesto, mosse = giro("Che giocatore sono?", "Bruno")
    verifica("«Che giocatore sono?» da Bruno: «Sei Giocatore 2.», senza il modello",
             "Sei Giocatore 2." in " ".join(map(str, detto)) and not chiesto
             and c.rec.get("esito") == "gioco_stato", f"{detto} {chiesto}")
    detto, chiesto, mosse = giro("A chi tocca?", "Ada")
    verifica("«A chi tocca?» da Ada: «Tocca a te.»", "Tocca a te." in " ".join(map(str, detto)),
             str(detto))


# ═══════════════════════════ 5. «Gira il telefono» ═══════════════════════════

def tela_orientata(tmp: Path, orientamento="orizzontale") -> Path:
    """Un gioco con una tela che vuole un orientamento solo (dalla tela dei «segnali», per uno
    schermo)."""
    cart = tmp / f"tela_{orientamento}"
    cart.mkdir(parents=True, exist_ok=True)
    m = json.loads((GIOCHI / "segnali" / "manifesto.json").read_text(encoding="utf-8"))
    m["nome"], m["titolo"] = "tela_" + orientamento, "La tela larga"
    m["scheda"]["condivisa"] = False
    m["scheda"]["giocatori"] = {"min": 1, "max": 1}
    m["scheda"]["macchina"]["fasi"]["gioco"]["orientamento"] = orientamento
    (cart / "manifesto.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    shutil.copy(GIOCHI / "segnali" / "logica.js", cart / "logica.js")
    return cart


def prova_gira_manifesto():
    sezione("5. «Gira il telefono»: il manifesto")
    m, _ = file_gioco("segnali")
    g = json.loads(json.dumps(m))
    g["scheda"]["macchina"]["fasi"]["gioco"]["orientamento"] = "orizzontale"
    v = valida(g)["scheda"]["macchina"]["fasi"]["gioco"]
    verifica("una tela dichiara «orientamento»: orizzontale", v.get("orientamento") ==
             "orizzontale", str(v))
    for nome, cambia in (("un orientamento inventato", ("gioco", "obliquo", "tela")),
                         ("su una pagina che non è una tela", ("gioco", "verticale", "scelte"))):
        g = json.loads(json.dumps(m))
        f = g["scheda"]["macchina"]["fasi"][cambia[0]]
        f["orientamento"], f["pagina"] = cambia[1], cambia[2]
        if cambia[2] != "tela":
            f["comandi"] = {"vai": {"forme": ["vai"]}}
        try:
            valida(g)
            ok = False
        except Exception as e:  # noqa: BLE001
            ok = "orientamento" in str(e)
        verifica(f"contrario: {nome} è rifiutato", ok)


def prova_gira_motore(tmp: Path):
    sezione("5. «Gira il telefono»: il motore (Node)")
    cart = tela_orientata(tmp)
    file, opz = opzioni(cart)
    out = node(tmp / "gira", js(file, opz, """
const g = await apriGioco(F, { ...O, finestra: [390, 844], tocco: true });
await g.tocca("Inizia");
out.palco = g.trova(".palco").map((x) => x.className)[0];
out.fascia = g.trova(".gira-telefono").map((x) => x.textContent);
out.gire = g.calliope.gire();
await g.calliope.finestra(844, 390);
out.girato = { fascia: g.trova(".gira-telefono").length, palco: g.trova(".palco").map((x) => x.className)[0] };
await g.calliope.finestra(390, 844);
out.di_nuovo = { fascia: g.trova(".gira-telefono").length, gire: g.calliope.gire() };
await g.tocca("Tocca per mandare un segnale");
out.si_gioca = g.errori.length;
out.palco_difetti = g.palco();
const pc = await apriGioco(F, { ...O, finestra: [600, 900] });
await pc.tocca("Inizia");
out.pc = { fascia: pc.trova(".gira-telefono").length, gire: pc.calliope.gire() };
out.fumo = await fumo(F, O);
"""))
    if "_errore" in out:
        verifica("il motore nel DOM finto", False, out["_errore"])
        return
    verifica("telefono in verticale, tela orizzontale: il palco resta orizzontale",
             "orizzontale" in (out["palco"] or ""), str(out["palco"]))
    verifica("la fascia «Gira il telefono in orizzontale» sopra il gioco",
             out["fascia"] == ["Gira il telefono in orizzontale"], str(out["fascia"]))
    verifica("Calliope lo sa (per dirlo a voce)", out["gire"] == ["orizzontale"], str(out["gire"]))
    verifica("girato il telefono la fascia sparisce", out["girato"]["fascia"] == 0
             and "orizzontale" in out["girato"]["palco"], str(out["girato"]))
    verifica("rigirato: la fascia torna, ma a Calliope non si ridice (una volta sola)",
             out["di_nuovo"]["fascia"] == 1 and out["di_nuovo"]["gire"] == ["orizzontale"],
             str(out["di_nuovo"]))
    verifica("niente blocco: con il telefono storto si gioca lo stesso", out["si_gioca"] == 0)
    verifica("g.palco() misura la tela solo nel suo orientamento", out["palco_difetti"] == [],
             str(out["palco_difetti"]))
    verifica("contrario: un PC con la finestra alta (niente dito) non dice di girare niente",
             out["pc"] == {"fascia": 0, "gire": []}, str(out["pc"]))
    verifica("la prova di fumo passa con una tela orientata", out["fumo"] == [], str(out["fumo"]))


def prova_gira_server(tmp: Path):
    sezione("5. «Gira il telefono»: la frase a voce una volta per schermo")
    a = Ambiente(tmp / "srv")
    m, _ = file_gioco("segnali")
    mac = json.loads(json.dumps(m["scheda"]["macchina"]))
    mac["fasi"]["gioco"]["orientamento"] = "orizzontale"
    cambi = {"manifesto": {"nome": "tela_larga", "titolo": "La tela larga"},
             "scheda": {"condivisa": False, "giocatori": {"min": 1, "max": 1}, "macchina": mac}}
    mv, n = a.installa("segnali", **cambi)
    A = a.abbina("A", "studio")
    pid = a.chiama("est_tela_larga", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    regole = []
    vero = a.giochi._registra

    def registra(p, evento, **extra):
        if extra.get("regola"):
            regole.append(extra["regola"])
        return vero(p, evento, **extra)
    a.giochi._registra = registra
    r1 = a.pagina(A, {"partita": pid, "tipo": "gira", "orientamento": "orizzontale"})
    r2 = a.pagina(A, {"partita": pid, "tipo": "gira", "orientamento": "orizzontale"})
    frasi = []
    while not a.giochi.frasi.empty():
        frasi.append(a.giochi.frasi.get_nowait())
    verifica("la prima volta Calliope lo dice («…gira il telefono in orizzontale.», regola "
             "gioco_gira_telefono), la seconda no",
             r1.get("detto") is True and r2.get("detto") is False and len(frasi) == 1
             and "gira il telefono in orizzontale" in frasi[0]["messaggio"]
             and frasi[0].get("regola") == "gioco_gira_telefono"
             and regole == ["gioco_gira_telefono"], f"{r1} {r2} {frasi}")
    r = a.pagina(A, {"partita": pid, "tipo": "gira", "orientamento": "obliquo"})
    verifica("contrario: un orientamento inventato è rifiutato", r.get("_stato") == 400)
    pp = a.giochi.avvia_prova(a.chi("Dario", schermo=A), "tela_larga", n, mv)["partita"]
    a.pagina(A, {"partita": pp, "tipo": "pronto"})
    r = a.pagina(A, {"partita": pp, "tipo": "gira", "orientamento": "orizzontale"})
    verifica("anche in una partita di prova (una frase di Calliope, non un ponte)",
             r.get("detto") is True, str(r))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-gioco-giocatori-"))
    try:
        if shutil.which("node"):
            prova_due_schermi(radice / "due")
            prova_uno_schermo(radice / "uno")
            prova_entra(radice / "entra")
            prova_gira_motore(radice / "gira")
        else:
            print("SALTATA IN PARTE: node non c'è (il motore)")
        prova_server(radice / "server")
        prova_domande()
        prova_ciclo(radice / "ciclo")
        prova_gira_manifesto()
        prova_gira_server(radice / "gira_server")
    finally:
        from calliope import minori as M
        for s in ("regole", "avvisi", "gioco", "richieste"):
            x = M._SERVIZIO.get(s)
            if x is not None:
                try:
                    x.close()
                except Exception:  # noqa: BLE001
                    pass
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
