"""Lo stato della partita che Calliope conosce (14/10/2026, passi 2, 5 e la ripresa del progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md; area docs/aree/giochi.md), a secco.

1. **L'istantanea validata dal server** (calliope/estensioni/macchina.py, valida_istantanea):
   quella buona passa pulita; il banco d'attacco (campi sconosciuti, tipi sbagliati, «n» che
   cala, fase non dichiarata, comandi di un'altra fase o inventati, troppi giocatori, punti NaN o
   enormi, «tocca» fuori, esito lungo) la scarta; un nome fuori dalla forma chiusa resta sullo
   schermo e per Calliope diventa «Giocatore N».
2. **Il server** (calliope/schermi/giochi.py, con l'hub vero): `stato` dà i comandi a voce
   attivi, una non valida li toglie (regola gioco_stato_non_valido) finché non ne arriva una
   buona, il comando a voce porta il numero dell'istantanea, `rifiutato` va nel registro
   (gioco_comando_vecchio), il tetto del messaggio.
3. **Il motore** (motore_gioco.js nel DOM finto di fumo_js.mjs, Node): manda un'istantanea dopo
   ogni disegno, e ognuna passa la validazione del server (andata e ritorno tra JavaScript e
   Python); un comando a voce su un'istantanea vecchia è rifiutato e la partita non cambia;
   quello con il numero giusto è una mossa.

    python prove/prova_gioco_stato.py
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


def macchina_di(cartella: str) -> tuple[dict, dict]:
    """(macchina normalizzata, giocatori) di un gioco delle prove."""
    m = valida(file_gioco(cartella)[0])
    return m["scheda"]["macchina"], m["scheda"]["giocatori"]


def buona(**altro) -> dict:
    ist = {"n": 3, "fase": "turno", "tocca": 1, "turno": 1,
           "giocatori": [{"nome": "Ada", "punti": 3}, {"nome": "Giocatore 2", "punti": 5}],
           "esito": None, "comandi": ["porta_1", "porta_3", "porta_4"]}
    ist.update(altro)
    return ist


# ═══════════════════════════ 1. la validazione ═══════════════════════════

def prova_valida():
    sezione("1. l'istantanea validata contro il manifesto")
    m, g = macchina_di("porte_fasi")
    v = mc.valida_istantanea(buona(), m, g)
    verifica("l'istantanea buona passa pulita", v == buona(), str(v))
    fasi = mc.per_fase(m, g)
    verifica("i comandi che ogni fase può avere: preparazione, turno, esito, fine",
             fasi["preparazione"] == ["giocatori_1", "giocatori_2", "giocatori_3", "giocatori_4",
                                      "inizia"]
             and fasi["turno"] == [f"porta_{i}" for i in range(1, 7)]
             and fasi["esito"] == ["avanti"] and fasi["fine"] == ["ancora"], str(fasi))
    verifica("da_piatto: «porta_3» → porta 3 nella fase turno; standard; sconosciuto",
             mc.da_piatto(m, "porta_3") == ("porta", 3, "turno")
             and mc.da_piatto(m, "giocatori_2") == ("giocatori", 2, None)
             and mc.da_piatto(m, "avanti") == ("avanti", None, None)
             and mc.da_piatto(m, "porta_9") is None)
    v = mc.valida_istantanea(buona(n=0, fase="preparazione", tocca=None, turno=0, giocatori=[],
                                   comandi=["giocatori_2", "inizia"]), m, g)
    verifica("la preparazione senza giocatori passa", v["fase"] == "preparazione", str(v))
    v = mc.valida_istantanea(buona(giocatori=[{"nome": "<b>Ada</b>", "punti": 1},
                                              {"nome": "Bea 123", "punti": 2.5}]), m, g)
    verifica("un nome fuori dalla forma chiusa per Calliope diventa «Giocatore N» (sullo schermo "
             "resta), i punti con la virgola restano",
             [x["nome"] for x in v["giocatori"]] == ["Giocatore 1", "Giocatore 2"]
             and v["giocatori"][0].get("fuori_forma") and v["giocatori"][1]["punti"] == 2.5,
             str(v["giocatori"]))
    for nome, ist, ultimo in [
            ("non un oggetto", ["n", 1], -1),
            ("un campo sconosciuto", buona(dati={"x": 1}), -1),
            ("«n» testo", buona(n="3"), -1),
            ("«n» booleano", buona(n=True), -1),
            ("«n» che cala", buona(n=2), 3),
            ("fase non dichiarata", buona(fase="bonus"), -1),
            ("comando inventato", buona(comandi=["porta_1", "apri_tutto"]), -1),
            ("valore fuori dal dominio", buona(comandi=["porta_7"]), -1),
            ("comando di un'altra fase", buona(comandi=["porta_1", "ancora"]), -1),
            ("comandi non elenco", buona(comandi="porta_1"), -1),
            ("comandi numeri", buona(comandi=[1, 2]), -1),
            ("troppi giocatori", buona(giocatori=[{"nome": "A", "punti": 0}] * 5), -1),
            ("giocatore con un campo in più", buona(giocatori=[{"nome": "A", "punti": 0,
                                                                "voce": "x"}]), -1),
            ("punti NaN", buona(giocatori=[{"nome": "A", "punti": float("nan")}]), -1),
            ("punti enormi", buona(giocatori=[{"nome": "A", "punti": 10 ** 12}]), -1),
            ("punti testo", buona(giocatori=[{"nome": "A", "punti": "3"}]), -1),
            ("«tocca» fuori dai giocatori", buona(tocca=2), -1),
            ("«tocca» testo", buona(tocca="Ada"), -1),
            ("«turno» negativo", buona(turno=-1), -1),
            ("esito lungo", buona(esito="x" * 161), -1),
            ("esito non testo", buona(esito={"testo": "x"}), -1)]:
        try:
            mc.valida_istantanea(ist, m, g, ultimo)
            verifica(f"scartata: {nome}", False, "passata")
        except mc.IstantaneaNonValida as e:
            verifica(f"scartata: {nome}", True, str(e)[:90])
    v = mc.valida_istantanea(buona(n=3), m, g, 3)
    verifica("contrario: la stessa istantanea mandata di nuovo (un ridisegno) passa", v["n"] == 3)


# ═══════════════════════════ 2. il server ═══════════════════════════

def stato_msg(a, S, pid, ist):
    a.giochi.partite[pid].posti[S["id"]].messaggi.clear()
    return a.pagina(S, {"partita": pid, "tipo": "stato", "istantanea": ist})


def prova_server(tmp: Path):
    sezione("2. il server tiene l'istantanea come stato della partita")
    a = Ambiente(tmp)
    a.installa("porte_fasi")
    A = a.abbina("A", "studio")
    regole = []
    vero = a.giochi._registra

    def registra(p, evento, **extra):
        if extra.get("regola"):
            regole.append(extra["regola"])
        return vero(p, evento, **extra)
    a.giochi._registra = registra
    pid = a.chiama("est_porte_fasi", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    verifica("dopo «pronto» e prima dell'istantanea niente comandi a voce",
             a.giochi.ascolto([A["id"]]) is None)
    r = stato_msg(a, A, pid, buona())
    info = a.giochi.ascolto([A["id"]]) or {}
    verifica("l'istantanea buona: i comandi a voce sono i suoi, e Calliope la legge",
             r.get("ok") and list(info.get("comandi") or {}) == ["porta_1", "porta_3", "porta_4"]
             and info["istantanea"]["giocatori"][1]["punti"] == 5, str(info)[:200])
    a.eventi.clear()
    a.giochi.comando(pid, A["id"], "porta_3")
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco"]
    verifica("il comando a voce porta il numero dell'istantanea su cui è riconosciuto",
             e == [{"comando": "porta_3", "n": 3}], str(e))
    r = stato_msg(a, A, pid, buona(n=4, comandi=["porta_9"]))
    verifica("una non valida si scarta: il gioco non ascolta finché non ne arriva una buona, "
             "regola gioco_stato_non_valido",
             r.get("_stato") == 400 and a.giochi.ascolto([A["id"]]) is None
             and "gioco_stato_non_valido" in regole, str(r))
    r = stato_msg(a, A, pid, buona(n=2))
    verifica("contrario: dopo una scartata vale ancora il numero dell'ultima buona (2 < 3)",
             r.get("_stato") == 400 and "cala" in r.get("errore", ""), str(r))
    r = stato_msg(a, A, pid, buona(n=5, comandi=["porta_1"]))
    verifica("…poi una buona e ascolta di nuovo",
             r.get("ok") and list(a.giochi.ascolto([A["id"]])["comandi"]) == ["porta_1"])
    r = a.pagina(A, {"partita": pid, "tipo": "rifiutato", "comando": "porta_1",
                     "motivo": "vecchio", "n": 4})
    verifica("«rifiutato» (un comando su un'istantanea vecchia) va nel registro",
             r.get("ok") and "gioco_comando_vecchio" in regole
             and a.giochi.partite[pid].posti[A["id"]].rifiutati == 1)
    grande = buona(n=6, esito="x" * 150)
    r = a.pagina(A, {"partita": pid, "tipo": "stato", "istantanea": grande,
                     "ripresa": {"dati": "y" * 30000}})
    verifica("contrario: un messaggio «stato» oltre il tetto (ripresa troppo grande) è rifiutato",
             r.get("_stato") == 413, str(r))
    # La partita di prova: «stato» e «rifiutato» passano (sono un ingresso, non un ponte)
    mp, _ = file_gioco("porte_fasi")
    pp = a.giochi.avvia_prova(a.chi("Dario", schermo=A), "porte_fasi", 1, valida(mp))["partita"]
    a.pagina(A, {"partita": pp, "tipo": "pronto"})
    r = stato_msg(a, A, pp, buona(n=0, fase="preparazione", tocca=None, giocatori=[],
                                  comandi=["inizia"]))
    r2 = a.pagina(A, {"partita": pp, "tipo": "rifiutato", "comando": "x", "motivo": "vecchio"})
    verifica("partita di prova: «stato» e «rifiutato» passano", r.get("ok") and r2.get("ok"),
             f"{r} {r2}")
    return a


# ═══════════════════════════ 3. il motore ═══════════════════════════

def node(tmp: Path, codice: str) -> tuple[int, str]:
    tmp.mkdir(parents=True, exist_ok=True)
    f = tmp / "prova.mjs"
    f.write_text(codice, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def apri_js(cartella: str, corpo: str) -> str:
    """Un programma Node che apre il gioco delle prove con apriGioco e stampa JSON."""
    m = json.loads((GIOCHI / cartella / "manifesto.json").read_text(encoding="utf-8"))
    sc = m["scheda"]
    file = [str(GIOCHI / cartella / f) for f in sc["file"]]
    opz = {"macchina": sc["macchina"], "minimo": sc["giocatori"]["min"],
           "massimo": sc["giocatori"]["max"], "giocatori": sc["giocatori"]["min"],
           "titolo": m["titolo"], "seme": 7}
    return (f"import {{ apriGioco }} from {json.dumps(FUMO.as_uri())};\n"
            f"const g = await apriGioco({json.dumps(file)}, {json.dumps(opz)});\n"
            "const out = {};\n" + corpo + "\nconsole.log('JSON' + JSON.stringify(out));\n")


def esegui(tmp: Path, cartella: str, corpo: str) -> dict:
    rc, testo = node(tmp, apri_js(cartella, corpo))
    riga = next((x for x in testo.splitlines() if x.startswith("JSON")), None)
    if rc != 0 or riga is None:
        return {"_errore": testo[-800:]}
    return json.loads(riga[4:])


def prova_motore(tmp: Path):
    sezione("3. il motore manda l'istantanea e rifiuta i comandi vecchi")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    out = esegui(tmp / "porte", "porte_fasi", """
out.all_avvio = g.calliope.istantanee();
await g.tocca("2 giocatori");
out.dopo_scelta = g.calliope.istantanee().slice(-1)[0];
const n = out.dopo_scelta.n;
await g.calliope.comando({ comando: "porta_2", n: n - 1 });
out.rifiutati = g.calliope.rifiutati();
out.fase_dopo_vecchio = g.stato().fase;
await g.calliope.comando({ comando: "porta_2", n });
out.dopo_mossa = g.calliope.istantanee().slice(-1)[0];
await g.avanza(4500);
out.dopo_esito = g.calliope.istantanee().slice(-1)[0];
await g.calliope.comando({ comando: "porta_2", n: out.dopo_esito.n });
out.rifiutati2 = g.calliope.rifiutati();
out.tutte = g.calliope.istantanee();
""")
    if "_errore" in out:
        verifica("il motore nel DOM finto", False, out["_errore"])
        return
    a0 = out["all_avvio"][-1] if out["all_avvio"] else {}
    verifica("all'avvio l'istantanea della preparazione: n 0, nessun giocatore, i comandi del "
             "numero dei giocatori e «inizia»",
             a0.get("n") == 0 and a0.get("fase") == "preparazione" and a0.get("giocatori") == []
             and a0.get("tocca") is None and "giocatori_2" in a0.get("comandi", [])
             and "inizia" in a0.get("comandi", []), str(a0))
    d = out["dopo_scelta"]
    verifica("dopo «2 giocatori»: fase turno, tocca al primo, due giocatori, le porte",
             d["fase"] == "turno" and d["tocca"] == 0 and len(d["giocatori"]) == 2
             and d["giocatori"][0] == {"nome": "Giocatore 1", "punti": 0}
             and d["comandi"] == ["porta_1", "porta_2", "porta_3", "porta_4"], str(d))
    verifica("un comando su un'istantanea vecchia: rifiutato («vecchio») e la partita non cambia",
             out["rifiutati"] == [{"comando": "porta_2", "motivo": "vecchio", "n": d["n"] - 1}]
             and out["fase_dopo_vecchio"] == "turno", str(out["rifiutati"]))
    mo = out["dopo_mossa"]
    verifica("con il numero giusto è una mossa: l'esito, n che cresce, «avanti»",
             mo["fase"] == "esito" and mo["n"] == d["n"] + 1 and mo["comandi"] == ["avanti"]
             and mo["esito"] and "porta 2" in mo["esito"], str(mo))
    de = out["dopo_esito"]
    verifica("l'esito va avanti da solo: tocca al secondo, la porta 2 non c'è più",
             de["fase"] == "turno" and de["tocca"] == 1 and "porta_2" not in de["comandi"],
             str(de))
    verifica("contrario: un comando non più attivo («porta_2» già aperta) è rifiutato",
             out["rifiutati2"][-1:] == [{"comando": "porta_2", "motivo": "non_attivo",
                                         "n": de["n"]}], str(out["rifiutati2"]))
    m, g = macchina_di("porte_fasi")
    ultimo, scartate = -1, []
    for ist in out["tutte"]:
        try:
            v = mc.valida_istantanea(ist, m, g, ultimo)
            ultimo = v["n"]
        except mc.IstantaneaNonValida as e:
            scartate.append(f"{ist.get('n')}: {e}")
    verifica(f"andata e ritorno: tutte le {len(out['tutte'])} istantanee del motore passano la "
             "validazione del server", not scartate and len(out["tutte"]) >= 4, str(scartate))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-gioco-stato-"))
    try:
        prova_valida()
        prova_server(radice / "server")
        prova_motore(radice / "motore")
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
