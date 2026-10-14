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
4. **Le domande standard** (calliope/gioco_stato.py, passo 5): le risposte composte dal codice
   dall'istantanea (a chi tocca, i punti di chi parla o di tutti, chi vince con i pari, cosa si
   può dire con i valori degli slot insieme), mai l'esito; la riga dei dati del turno, in busta
   solo con un nome scritto; un gioco non può dichiarare una domanda come comando.
5. **Nel ciclo** (calliope/ciclo.py con ascolto, Whisper, voce e Brain finti): «A chi tocca?»
   senza il nome nella finestra del gioco riceve la risposta senza il modello (regola
   gioco_stato_detto, niente testo nel registro); contrari: dentro una frase più lunga (senza
   il nome ignorata, con il nome al modello con l'istantanea nei dati del turno), una domanda
   di Calliope in sospeso, nessun gioco aperto, il gioco sullo schermo di un altro satellite.
6. **Il giudice di fase** (calliope/gioco_giudice.py, passo 6) con un modello finto: il prompt
   scritto da Calliope dai comandi attivi (enum con «nessuno» in testa, i valori che adesso non
   valgono, l'ordinale), la scelta vincolata (fuori elenco, guasto e «nessuno» non muovono); nel
   ciclo «Calliope, apri la terza» → mossa con l'etichetta detta («Porta 3.», regola
   gioco_giudice), «nessuno» → al modello della voce; contrari: senza il nome nella finestra
   del gioco il giudice non parte (`giochi_giudice_senza_nome` spento), con l'interruttore
   acceso sì; domanda in sospeso; giudice spento (`giochi_giudice: false`).
7. **«Gioco anch'io» e i nomi scritti** (passo 4): nel motore «gioco anch'io» con il nome dalla
   voce prende un posto (la stessa voce due volte no, senza nome «Giocatore N»), la partita
   parte con quei nomi e li tiene ad «ancora»; il nome nella fascia dei punti si tocca e si
   scrive (forma chiusa; cifre e doppioni rifiutati con un avviso, la partita non cambia).
   Sul server il nome mandato da Calliope dalla voce si dice, quello scritto passa dai
   controlli (con un minore nella partita il guardiano: fermato → «Giocatore N»), mai in una
   partita di prova; nel ciclo «Gioco anch'io, sono Pippo» manda il nome detto, che vale come
   uno scritto (regola gioco_anchio_nome), e con la voce riconosciuta il suo nome.
8. **La ripresa dopo «Riapri»** (decisione 7): il motore manda con l'istantanea lo stato intero;
   il server lo tiene solo se accompagna l'ultima istantanea valida (stesso numero e fase,
   entro 16 000 caratteri; un'istantanea senza ripresa la toglie) e lo restituisce all'avvio di
   un riquadro nuovo dello stesso posto; il motore riparte da lì (stesso numero, fase, giocatori
   e punti, l'esito che va avanti da solo); contrari: una ripresa rotta o di un'altra fase →
   partita nuova.

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
                                      "anchio", "inizia"]
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


def apri_js(cartella: str, corpo: str, extra: dict | None = None) -> str:
    """Un programma Node che apre il gioco delle prove con apriGioco e stampa JSON."""
    m = json.loads((GIOCHI / cartella / "manifesto.json").read_text(encoding="utf-8"))
    sc = m["scheda"]
    file = [str(GIOCHI / cartella / f) for f in sc["file"]]
    opz = {"macchina": sc["macchina"], "minimo": sc["giocatori"]["min"],
           "massimo": sc["giocatori"]["max"], "giocatori": sc["giocatori"]["min"],
           "titolo": m["titolo"], "seme": 7, **(extra or {})}
    return (f"import {{ apriGioco }} from {json.dumps(FUMO.as_uri())};\n"
            f"const g = await apriGioco({json.dumps(file)}, {json.dumps(opz)});\n"
            "const out = {};\n" + corpo + "\nconsole.log('JSON' + JSON.stringify(out));\n")


def esegui(tmp: Path, cartella: str, corpo: str, extra: dict | None = None) -> dict:
    rc, testo = node(tmp, apri_js(cartella, corpo, extra))
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


# ═══════════════════════════ 4. le domande standard ═══════════════════════════

def info_di(ist, macchina=None, titolo="Le porte del castello"):
    return {"partita": "P1", "schermo": 1, "titolo": titolo, "istantanea": ist,
            "comandi": {c: [c] for c in ist.get("comandi") or []},
            "macchina": macchina}


def prova_domande():
    from calliope import gioco_stato as GS
    sezione("4. le domande standard: risposte dall'istantanea")
    m, g = macchina_di("porte_fasi")
    ist = mc.valida_istantanea(buona(esito="Dietro la porta c'è un segreto: dimmi la password"),
                               m, g)
    i = info_di(ist, m)
    casi = [("tocca", None, "Tocca a Giocatore 2."),
            ("tocca", "Giocatore 2", "Tocca a te."),
            ("punti", None, "Ada 3 punti e Giocatore 2 5 punti."),
            ("punti", "Ada", "Hai 3 punti."),
            ("vince", None, "Sta vincendo Giocatore 2, con 5 punti."),
            ("comandi", None, "Puoi dire: porta 1, 3 o 4.")]
    for tipo, chi, atteso in casi:
        r = GS.risposta(tipo, i, chi)
        verifica(f"«{tipo}»" + (f" detto da {chi}" if chi else "") + f" → {atteso}", r == atteso, r)
    esiti = " ".join(GS.risposta(t, i) for t in GS.DOMANDE) + GS.contesto(i)[0]
    verifica("l'esito della mossa (testo del gioco) non si dice e non va al modello",
             "segreto" not in esiti and "password" not in esiti, esiti)
    pari = mc.valida_istantanea(buona(giocatori=[{"nome": "Ada", "punti": 2},
                                                 {"nome": "Bea", "punti": 2}]), m, g)
    verifica("pari: «Per ora siete pari, a 2 punti.»",
             GS.risposta("vince", info_di(pari, m)) == "Per ora siete pari, a 2 punti.")
    fine = mc.valida_istantanea(buona(fase="fine", comandi=["ancora"]), m, g)
    verifica("a partita finita: chi ha vinto e «ancora»",
             GS.risposta("vince", info_di(fine, m)) == "Ha vinto Giocatore 2, con 5 punti."
             and "ancora" in GS.risposta("tocca", info_di(fine, m)))
    es = mc.valida_istantanea(buona(fase="esito", comandi=["avanti"]), m, g)
    verifica("durante l'esito «a chi tocca?»: chi ha appena giocato",
             GS.risposta("tocca", info_di(es, m)) == "Ha appena giocato Giocatore 2.")
    prep = mc.valida_istantanea(buona(n=0, fase="preparazione", tocca=None, giocatori=[],
                                      comandi=["giocatori_2", "giocatori_3", "inizia"]), m, g)
    r = GS.risposta("comandi", info_di(prep, m))
    verifica("in preparazione: non è cominciata; cosa posso dire con i numeri insieme",
             "non è ancora cominciata" in GS.risposta("tocca", info_di(prep, m))
             and r == "Puoi dire: 2 o 3 giocatori, oppure inizia.", r)
    uno = mc.valida_istantanea(buona(tocca=0, giocatori=[{"nome": "Giocatore 1", "punti": 1}]),
                               m, g)
    verifica("da solo: «tocca sempre a te», «Giocatore 1 ha 1 punto»",
             GS.risposta("tocca", info_di(uno, m)) == "Giochi da solo: tocca sempre a te."
             and GS.risposta("punti", info_di(uno, m)) == "Giocatore 1 ha 1 punto.")
    vuoto = mc.valida_istantanea(buona(comandi=[]), m, g)
    verifica("nessun comando attivo: lo dice", GS.risposta("comandi", info_di(vuoto, m))
             == "Adesso il gioco non aspetta comandi a voce.")
    riga, busta = GS.contesto(i)
    verifica("la riga dei dati del turno: fase, a chi tocca, punti, comandi (fuori busta senza "
             "nomi scritti)", not busta and riga == "Sullo schermo c'è il gioco «Le porte del "
             "castello», fase turno. Tocca a Giocatore 2. Punti: Ada 3, Giocatore 2 5. Comandi "
             "a voce adesso: porta 1, 3 o 4.", riga)
    scritto = json.loads(json.dumps(ist))
    scritto["giocatori"][0]["scritto"] = True
    verifica("con un nome scritto sullo schermo: in busta", GS.contesto(info_di(scritto, m))[1])
    # Un gioco non può dichiarare una domanda standard come comando
    mm, _ = file_gioco("porte_fasi")
    mm["scheda"]["macchina"]["fasi"]["turno"]["comandi"]["chi"] = {"forme": ["a chi tocca"]}
    try:
        valida(mm)
        verifica("rifiutato: un comando «a chi tocca»", False, "accettato")
    except Exception as e:  # noqa: BLE001
        verifica("rifiutato: un comando «a chi tocca»", "domanda di Calliope" in str(e), str(e))


# ═══════════════════════════ 5. nel ciclo ═══════════════════════════

def gioco_regola(c) -> bool:
    return "gioco_stato_detto" in ((c.rec or {}).get("regole") or [])


def prova_ciclo(tmp: Path):
    import prova_gioco_voce as PV
    sezione("5. nel ciclo: la regola gioco_stato_detto e i suoi contrari")
    a = Ambiente(tmp)
    a.installa("porte_fasi")
    A, B = a.abbina("A", "studio"), a.abbina("B", "cucina")
    sat = a.hub.satelliti = PV.Satelliti({7: PV.Coll(id=7, schermo_id=A["id"], stanza="studio"),
                                          8: PV.Coll(id=8, schermo_id=B["id"], stanza="cucina")})
    turni = []
    c, stt, voce, cervello, ascolto = PV.nuovo_ciclo(a, sat, 7, turni)
    a.cfg.giochi_ascolto_s = 60.0
    a.cfg.giochi_giudice = True
    giudicate = []
    c.giudice_gioco = GiudiceFinto(a.cfg, giudicate)

    def giro(frase, k=None):
        k = k or (c, stt, voce, cervello)
        k[0].awake_until = 0.0
        k[1].frasi.append(frase)
        n, m_ = len(k[2].detto), len(k[3].richieste)
        k[0].giro()
        return k[2].detto[n:], k[3].richieste[m_:]

    detto, chiesto = giro("Calliope, a chi tocca?")
    verifica("contrario: nessun gioco aperto → al modello, niente risposta dal codice",
             chiesto and not gioco_regola(c), str(detto))
    pid = a.chiama("est_porte_fasi", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    stato_msg(a, A, pid, buona(n=1))
    detto, chiesto = giro("A chi tocca?")
    verifica("«A chi tocca?» senza il nome nella finestra del gioco: risponde il codice, niente "
             "modello, niente testo nel registro",
             "Tocca a Giocatore 2." in " ".join(map(str, detto)) and not chiesto
             and c.rec.get("esito") == "gioco_stato" and c.rec.get("testo") is None
             and gioco_regola(c), f"{detto} {chiesto} {c.rec}")
    detto, chiesto = giro("Calliope, cosa posso dire?")
    verifica("«Calliope, cosa posso dire?»: i comandi della fase con i valori insieme",
             "Puoi dire: porta 1, 3 o 4." in " ".join(map(str, detto)) and not chiesto,
             str(detto))
    detto, chiesto = giro("A chi tocca adesso secondo te?")
    verifica("contrario: dentro una frase più lunga, senza il nome, nella finestra → ignorata",
             not detto and not chiesto and c.rec.get("esito") == "ignorato")
    detto, chiesto = giro("Calliope, chi sta perdendo?")
    contesto = (chiesto[0][1] if chiesto else "") or ""
    verifica("contrario: «Calliope, chi sta perdendo?» va al modello con l'istantanea nei dati "
             "del turno (punti e a chi tocca, non l'esito)", chiesto and "Punti: Ada 3, "
             "Giocatore 2 5" in contesto and "Tocca a Giocatore 2" in contesto,
             str(chiesto)[:300])
    cervello.has_pending = lambda: True
    detto, chiesto = giro("Calliope, a chi tocca?")
    del cervello.has_pending
    verifica("contrario: con una domanda di Calliope in sospeso va al modello",
             chiesto and not gioco_regola(c))
    k8 = PV.nuovo_ciclo(a, sat, 8, turni)
    detto, chiesto = giro("Calliope, a chi tocca?", k8[:4])
    verifica("contrario: dal satellite della cucina il gioco dello studio non risponde",
             chiesto and not gioco_regola(k8[0]))

    sezione("6. il giudice di fase nel ciclo (modello finto)")
    a.cfg.giochi_giudice = True              # (nuovo_ciclo lo spegne per le prove dell'11/10)
    giudicate.clear()
    a.eventi.clear()
    detto, chiesto = giro("Calliope, apri la terza.")
    mosse = [x[2]["dati"] for x in a.eventi if x[1] == "gioco" and x[2].get("tipo") == "comando"]
    verifica("«Calliope, apri la terza.» → il giudice sceglie porta 3: la mossa parte con il "
             "numero dell'istantanea, Calliope dice l'etichetta breve, niente modello della voce",
             giudicate == ["Calliope, apri la terza."] and mosse == [{"comando": "porta_3", "n": 1}]
             and "Porta 3." in " ".join(map(str, detto)) and not chiesto
             and c.rec.get("esito") == "gioco_giudice"
             and "gioco_giudice" in (c.rec.get("regole") or [])
             and c.rec["gioco"]["comando"] == "porta_3" and c.rec.get("testo") is None,
             f"{giudicate} {mosse} {detto} {chiesto} {c.rec}")
    giudicate.clear()
    detto, chiesto = giro("Calliope, che bello questo gioco.")
    verifica("«nessuno» dal giudice: la frase va al modello della voce, il giudizio nel registro",
             giudicate and chiesto and c.rec.get("gioco_giudice", {}).get("comando") is None,
             str(c.rec.get("gioco_giudice")))
    giudicate.clear()
    detto, chiesto = giro("Apri la terza.")
    verifica("contrario: senza il nome nella finestra del gioco il giudice non parte (spento "
             "senza nome): la frase si ignora", not giudicate and not chiesto
             and c.rec.get("esito") == "ignorato")
    a.cfg.giochi_giudice_senza_nome = True
    detto, chiesto = giro("Apri la terza.")
    a.cfg.giochi_giudice_senza_nome = False
    verifica("…con giochi_giudice_senza_nome acceso il giudice parte anche senza il nome",
             giudicate == ["Apri la terza."] and c.rec.get("esito") == "gioco_giudice")
    giudicate.clear()
    cervello.has_pending = lambda: True
    detto, chiesto = giro("Calliope, apri la terza.")
    del cervello.has_pending
    verifica("contrario: con una domanda di Calliope in sospeso niente giudice (al modello)",
             not giudicate and chiesto)
    a.cfg.giochi_giudice = False
    detto, chiesto = giro("Calliope, apri la terza.")
    a.cfg.giochi_giudice = True
    verifica("contrario: con il giudice spento la frase va al modello della voce",
             not giudicate and chiesto)


class GiudiceFinto:
    """Il giudice di fase con il modello finto: «apri la terza» → porta 3, il resto nessuno.
    Usa il Giudice vero (prompt, schema, vincolo), solo la chiamata al modello è finta."""

    def __init__(self, cfg, giudicate):
        from calliope.gioco_giudice import Giudice
        self.giudicate = giudicate
        self.vero = Giudice(cfg, chiama=self._chiama)

    def _chiama(self, msgs, schema, timeout):
        frase = msgs[-1]["content"].lower()
        enum = schema["properties"]["scelta"]["enum"]
        s = "porta 3" if "terza" in frase and "porta 3" in enum else "nessuno"
        return json.dumps({"scelta": s})

    def scegli(self, frase, info, timeout=None):
        self.giudicate.append(frase)
        return self.vero.scegli(frase, info, timeout)


def prova_giudice():
    from calliope import gioco_giudice as GG
    sezione("6. il giudice di fase: prompt e scelta vincolata")
    m, g = macchina_di("porte_fasi")
    a = valida(file_gioco("porte_fasi")[0])["scheda"]["ascolta"]["comandi"]
    info = {"titolo": "Le porte del castello", "macchina": m,
            "comandi": {c: a[c] for c in ("porta_1", "porta_3", "porta_4")},
            "istantanea": mc.valida_istantanea(buona(), m, g)}
    sistema, scelte = GG.prompt(info)
    verifica("le scelte: «nessuno» in testa, poi i comandi attivi come si dicono",
             scelte == ["nessuno", "porta 1", "porta 3", "porta 4"], str(scelte))
    verifica("il prompt dice il significato, i valori che adesso non valgono, l'ordinale, gli "
             "esempi e «vale l'ultima scelta»",
             "adesso non valgono 2, 5, 6" in sistema and "«l'ultima» è il 6" in sistema
             and "vale l'ultima scelta" in sistema and "«che tempo fa?» → nessuno" in sistema
             and "«Le porte del castello»" in sistema, sistema)
    info2 = dict(info, comandi={"avanti": ["avanti", "continua"]})
    s2, e2 = GG.prompt(info2)
    verifica("nell'esito: «avanti» con il suo significato", e2 == ["nessuno", "avanti"]
             and "va avanti dopo l'esito" in s2, s2)
    for nome, risposta, atteso, guasto in [
            ("una mossa", '{"scelta": "porta 3"}', "porta_3", None),
            ("nessuno", '{"scelta": "nessuno"}', None, None),
            ("fuori elenco (non può, ma se succede)", '{"scelta": "porta 9"}', None, "fuori elenco"),
            ("JSON rotto", "porta 3", None, "JSONDecodeError"),
            ("senza scelta", '{"x": 1}', None, "ValueError")]:
        gg = GG.Giudice(None, chiama=lambda msgs, schema, t, r=risposta: r)
        sc = gg.scegli("apri la terza", info)
        verifica(f"scelta: {nome} → {atteso}", sc.comando == atteso and sc.guasto == guasto,
                 f"{sc}")

    def lento(msgs, schema, t):
        raise TimeoutError("scaduto")
    sc = GG.Giudice(None, chiama=lento).scegli("apri la terza", info)
    verifica("un giudice scaduto vale «nessuno» (la frase va al modello)",
             sc.comando is None and sc.guasto == "TimeoutError")
    verifica("l'etichetta detta: «Porta 3.»", GG.frase_detta("porta 3") == "Porta 3.")
    verifica("contrario: senza comandi attivi il giudice non chiama il modello",
             GG.Giudice(None, chiama=lento).scegli("x", dict(info, comandi={})).guasto is None)


# ═══════════════════════════ 7. «gioco anch'io» e i nomi scritti ═══════════════════════════

def prova_nomi_motore(tmp: Path):
    sezione("7. «gioco anch'io» e i nomi scritti nel motore")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    out = esegui(tmp / "nomi", "porte_fasi", """
out.prep0 = g.calliope.istantanee().slice(-1)[0];
await g.calliope.comando({ comando: "anchio", n: 0, giocatore: "Ada" });
out.prep1 = g.calliope.istantanee().slice(-1)[0];
out.testo1 = g.testo();
await g.calliope.comando({ comando: "anchio", n: out.prep1.n, giocatore: "Ada" });
await g.calliope.comando({ comando: "anchio", n: g.calliope.istantanee().slice(-1)[0].n });
await g.tocca("Inizia");
out.inizio = g.stato();
out.ist = g.calliope.istantanee().slice(-1)[0];
await g.tocca("Giocatore 2: 0");
out.campo = g.trova(".scrivi-nome").length;
await g.scrivi(".scrivi-nome", "Bea");
out.dopo_nome = g.stato();
out.ist_nome = g.calliope.istantanee().slice(-1)[0];
await g.tocca("Bea: 0");
await g.scrivi(".scrivi-nome", "Bea123");
out.cifre = g.stato().giocatori.map((x) => x.nome);
out.avviso = g.testo();
await g.tocca("Bea: 0");
await g.scrivi(".scrivi-nome", "ada");
out.doppio = g.stato().giocatori.map((x) => x.nome);
out.errori = g.errori.length;
""")
    if "_errore" in out:
        verifica("il motore nel DOM finto", False, out["_errore"])
        return
    verifica("in preparazione «gioco anch'io» è attivo (e «inizia»)",
             "anchio" in out["prep0"]["comandi"] and "inizia" in out["prep0"]["comandi"],
             str(out["prep0"]))
    verifica("«gioco anch'io» con il nome dalla voce: un posto per Ada, sullo schermo",
             "Ada" in out["testo1"] and "Giocano: Ada" in out["testo1"], out["testo1"][:200])
    nomi = [x["nome"] for x in out["inizio"]["giocatori"]]
    verifica("la stessa voce due volte non prende due posti; senza nome «Giocatore 2»; «inizia» "
             "parte con quei nomi", nomi == ["Ada", "Giocatore 2"], str(nomi))
    verifica("il campo per scrivere il nome si apre toccando il nome nella fascia",
             out["campo"] == 1)
    nomi = [x["nome"] for x in out["dopo_nome"]["giocatori"]]
    g2 = out["ist_nome"]["giocatori"][1]
    verifica("il nome scritto: «Bea» nella partita e nell'istantanea per Calliope, segnato "
             "«scritto»", nomi == ["Ada", "Bea"] and g2 == {"nome": "Bea", "punti": 0,
                                                            "scritto": True}, f"{nomi} {g2}")
    verifica("contrario: un nome con le cifre è rifiutato con un avviso, la partita non cambia",
             out["cifre"] == ["Ada", "Bea"] and "solo lettere" in out["avviso"], out["avviso"][:200])
    verifica("contrario: lo stesso nome di un altro giocatore è rifiutato",
             out["doppio"] == ["Ada", "Bea"], str(out["doppio"]))
    verifica("nessun errore del gioco (gli avvisi sui nomi non sono errori)", out["errori"] == 0)
    m, g = macchina_di("porte_fasi")
    v = mc.valida_istantanea(out["ist_nome"], m, g)
    verifica("andata e ritorno: l'istantanea con il nome scritto passa la validazione",
             v["giocatori"][1].get("scritto") is True)


def prova_nomi_server(tmp: Path):
    sezione("7. i nomi detti da Calliope: voce, scritti, minori, prova")
    from calliope import gioco_stato as GS
    a = Ambiente(tmp)
    a.installa("porte")
    A = a.abbina("A", "studio")
    pid = a.chiama("est_porte", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    stato_msg(a, A, pid, buona(n=0, fase="preparazione", tocca=None, giocatori=[],
                               comandi=["anchio", "inizia"]))
    a.giochi.comando(pid, A["id"], "anchio", "Elena")
    gs = [{"nome": "Elena", "punti": 0}, {"nome": "Pippo", "punti": 2, "scritto": True},
          {"nome": "Giocatore 3", "punti": 0}]
    m = valida(file_gioco("porte")[0])["scheda"]
    gs1 = [gs[0]]
    r = stato_msg(a, A, pid, {"n": 1, "fase": "turno", "tocca": 0, "turno": 1, "giocatori": gs1,
                              "esito": None, "comandi": ["porta_1"]})
    info = a.giochi.ascolto([A["id"]])
    g0 = info["istantanea"]["giocatori"][0]
    verifica("il nome mandato da Calliope dalla voce («gioco anch'io» di Elena) si dice, non è "
             "scritto", r.get("ok") and g0["detto"] == "Elena" and not g0.get("scritto"), str(g0))
    # Il gioco delle porte è per un giocatore: per gli altri casi la macchina a 3
    a.giochi.partite[pid].scheda = dict(m, giocatori={"min": 1, "max": 3})
    r = stato_msg(a, A, pid, {"n": 2, "fase": "turno", "tocca": 1, "turno": 1, "giocatori": gs,
                              "esito": None, "comandi": ["porta_1"]})
    info = a.giochi.ascolto([A["id"]])
    gg = info["istantanea"]["giocatori"]
    verifica("il nome scritto «Pippo» passa i controlli e si dice; «Giocatore 3» com'è",
             r.get("ok") and gg[1]["detto"] == "Pippo" and gg[1]["scritto"] is True
             and gg[2]["detto"] == "Giocatore 3", str(gg))
    verifica("«a chi tocca?» con il nome scritto: «Tocca a Pippo.»; i dati del turno in busta",
             GS.risposta("tocca", info) == "Tocca a Pippo." and GS.contesto(info)[1])
    # Con un minore nella partita: il guardiano (qui assente: per un minore si blocca)
    a.giochi.partite[pid].posti[A["id"]].minore = True
    stato_msg(a, A, pid, {"n": 3, "fase": "turno", "tocca": 1, "turno": 1,
                          "giocatori": [gs[0], {"nome": "Topolino", "punti": 0, "scritto": True}],
                          "esito": None, "comandi": ["porta_1"]})
    gg = a.giochi.ascolto([A["id"]])["istantanea"]["giocatori"]
    verifica("con un minore nella partita il nome scritto passa dal guardiano: senza guardiano "
             "non si dice («Giocatore 2»), sullo schermo resta",
             gg[1]["detto"] == "Giocatore 2" and gg[1]["nome"] == "Topolino", str(gg))

    class Guardiano:
        def giudica(self, domanda, testo, att=None):
            from types import SimpleNamespace
            return SimpleNamespace(esito="ok" if testo == "Lilla" else "vietato")
    a.giochi.guardiano = Guardiano()
    stato_msg(a, A, pid, {"n": 4, "fase": "turno", "tocca": 1, "turno": 1,
                          "giocatori": [gs[0], {"nome": "Lilla", "punti": 0, "scritto": True},
                                        {"nome": "Brutto Nome", "punti": 0, "scritto": True}],
                          "esito": None, "comandi": ["porta_1"]})
    gg = a.giochi.ascolto([A["id"]])["istantanea"]["giocatori"]
    verifica("…con il guardiano: «Lilla» sì, «Brutto Nome» fermato → «Giocatore 3»",
             gg[1]["detto"] == "Lilla" and gg[2]["detto"] == "Giocatore 3", str(gg))
    a.giochi.partite[pid].posti[A["id"]].minore = False
    # In una partita di prova i nomi scritti non si dicono
    mp, _ = file_gioco("porte")
    pp = a.giochi.avvia_prova(a.chi("Dario", schermo=A), "porte", 1, valida(mp))["partita"]
    a.pagina(A, {"partita": pp, "tipo": "pronto"})
    stato_msg(a, A, pp, {"n": 1, "fase": "turno", "tocca": 0, "turno": 1,
                         "giocatori": [{"nome": "Pippo", "punti": 0, "scritto": True}],
                         "esito": None, "comandi": ["porta_1"]})
    g0 = a.giochi.partite[pp].posti[A["id"]].istantanea["giocatori"][0]
    verifica("partita di prova: il nome scritto non si dice («Giocatore 1»)",
             g0["detto"] == "Giocatore 1", str(g0))
    stato_msg(a, A, pid, {"n": 5, "fase": "turno", "tocca": 0, "turno": 1,
                          "giocatori": [gs[0], {"nome": "Furbo", "punti": 0}],
                          "esito": None, "comandi": ["porta_1"]})
    gg = a.giochi.ascolto([A["id"]])["istantanea"]["giocatori"]
    verifica("contrario: un nome non segnato «scritto» dal motore ma mai mandato da Calliope "
             "vale come scritto (il server non si fida del motore)", gg[1].get("scritto") is True,
             str(gg))


def prova_nomi_ciclo(tmp: Path):
    import prova_gioco_voce as PV
    sezione("7. «gioco anch'io, sono Pippo» nel ciclo")
    a = Ambiente(tmp)
    a.installa("porte")
    A = a.abbina("A", "studio")
    sat = a.hub.satelliti = PV.Satelliti({7: PV.Coll(id=7, schermo_id=A["id"], stanza="studio")})
    c, stt, voce, cervello, ascolto = PV.nuovo_ciclo(a, sat, 7, [])
    a.cfg.giochi_ascolto_s = 60.0
    pid = a.chiama("est_porte", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    stato_msg(a, A, pid, buona(n=0, fase="preparazione", tocca=None, giocatori=[],
                               comandi=["anchio", "inizia"]))

    def giro(frase):
        c.awake_until = 0.0
        stt.frasi.append(frase)
        a.eventi.clear()
        n = len(cervello.richieste)
        c.giro()
        return ([x[2]["dati"] for x in a.eventi if x[1] == "gioco"
                 and x[2].get("tipo") == "comando"], cervello.richieste[n:])
    mosse, chiesto = giro("Gioco anch'io, sono Pippo.")
    verifica("«Gioco anch'io, sono Pippo.» senza il nome nella finestra: un posto con il nome "
             "detto, senza il modello (regola gioco_anchio_nome)",
             mosse == [{"comando": "anchio", "n": 0, "giocatore": "Pippo"}] and not chiesto
             and "gioco_anchio_nome" in (c.rec.get("regole") or []), f"{mosse} {chiesto}")
    verifica("…il nome detto non è della voce riconosciuta: Calliope lo dirà solo dopo i "
             "controlli", "Pippo" not in a.giochi.partite[pid].nomi_voce)
    mosse, chiesto = giro("Anch'io sono pronto.")
    verifica("contrario: «Anch'io sono pronto.» non è un nome (ignorata nella finestra)",
             not mosse and not chiesto)
    mosse, chiesto = giro("Anch'io.")
    verifica("«Anch'io.» da solo: il posto, senza nome (la voce qui non è riconosciuta)",
             mosse == [{"comando": "anchio", "n": 0}], str(mosse))


# ═══════════════════════════ 8. la ripresa dopo «Riapri» ═══════════════════════════

def prova_ripresa_motore(tmp: Path):
    sezione("8. la ripresa dopo «Riapri» nel motore")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    out = esegui(tmp / "prima", "porte_fasi", """
await g.tocca("2 giocatori");
await g.tocca("Porta 2");
out.esito_ist = g.calliope.istantanee().slice(-1)[0];
out.esito_rip = g.calliope.riprese().slice(-1)[0];
await g.avanza(4500);
out.ist = g.calliope.istantanee().slice(-1)[0];
out.rip = g.calliope.riprese().slice(-1)[0];
out.stato = g.stato();
""")
    if "_errore" in out:
        verifica("il motore nel DOM finto", False, out["_errore"])
        return
    verifica("con l'istantanea il motore manda lo stato intero (stesso numero e fase)",
             out["rip"] and out["rip"]["n"] == out["ist"]["n"]
             and out["rip"]["fase"] == out["ist"]["fase"] == "turno", str(out["ist"]))
    dopo = esegui(tmp / "dopo", "porte_fasi", """
out.ist = g.calliope.istantanee()[0];
out.stato = g.stato();
await g.tocca("Porta 1");
out.mossa = g.calliope.istantanee().slice(-1)[0];
""", {"ripresa": out["rip"]})
    verifica("«Riapri»: il riquadro nuovo riparte dall'ultima istantanea (stesso numero, fase, a "
             "chi tocca, giocatori e punti, comandi)", dopo.get("ist") == out["ist"]
             and dopo.get("stato") == out["stato"], f"{dopo.get('ist')} | {out['ist']}")
    verifica("…e la partita continua da lì (la mossa dopo ha il numero dopo)",
             dopo.get("mossa", {}).get("n") == out["ist"]["n"] + 1
             and dopo["mossa"]["fase"] == "esito", str(dopo.get("mossa")))
    es = esegui(tmp / "esito", "porte_fasi", """
out.prima = g.calliope.istantanee()[0];
await g.avanza(4500);
out.dopo = g.calliope.istantanee().slice(-1)[0];
""", {"ripresa": out["esito_rip"]})
    verifica("ripresa nell'esito: riprende l'esito e poi va avanti da solo",
             es.get("prima", {}).get("fase") == "esito" and es.get("dopo", {}).get("fase")
             == "turno" and es["dopo"]["tocca"] == 1, f"{es.get('prima')} {es.get('dopo')}")
    rotta = dict(out["rip"], fase="bonus")
    r1 = esegui(tmp / "rotta", "porte_fasi", "out.ist = g.calliope.istantanee()[0];",
                {"ripresa": rotta})
    punti = dict(out["rip"], giocatori=[{"nome": "Ada", "punti": "tanti"}])
    r2 = esegui(tmp / "punti", "porte_fasi", "out.ist = g.calliope.istantanee()[0];",
                {"ripresa": punti})
    verifica("contrario: una ripresa rotta (fase che non c'è, punti non numeri) → partita nuova",
             r1.get("ist", {}).get("fase") == "preparazione" and r1["ist"]["n"] == 0
             and r2.get("ist", {}).get("fase") == "preparazione",
             f"{r1.get('ist')} {r2.get('ist')} {r1.get('_errore', '')[:200]}")


def prova_ripresa_server(tmp: Path):
    sezione("8. la ripresa sul server")
    a = Ambiente(tmp)
    a.installa("porte_fasi")
    A = a.abbina("A", "studio")
    pid = a.chiama("est_porte_fasi", {}, "Dario", schermo=A)["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    posto = a.giochi.partite[pid].posti[A["id"]]

    def manda(ist, ripresa):
        posto.messaggi.clear()
        return a.pagina(A, {"partita": pid, "tipo": "stato", "istantanea": ist,
                            "ripresa": ripresa})
    R = {"n": 3, "fase": "turno", "dati": {"porte": 4}, "giocatori": [{"nome": "Ada", "punti": 1}]}
    manda(buona(), R)
    verifica("la ripresa che accompagna un'istantanea valida si tiene", posto.ripresa == R)
    r = a.pagina(A, {"partita": pid, "tipo": "pronto"})
    verifica("«Riapri» (un pronto nuovo dello stesso posto): l'avvio la restituisce",
             r["avvio"].get("ripresa") == R, str(r.get("avvio"))[:200])
    manda(buona(n=4, comandi=["porta_9"]), dict(R, n=4))
    verifica("un'istantanea non valida non cambia la ripresa (resta l'ultima valida)",
             posto.ripresa == R)
    manda(buona(n=5), dict(R, n=4))
    verifica("contrario: una ripresa con un altro numero non si tiene", posto.ripresa is None)
    manda(buona(n=6), dict(R, n=6, fase="esito"))
    verifica("contrario: una ripresa con un'altra fase non si tiene", posto.ripresa is None)
    manda(buona(n=7), dict(R, n=7, dati={"x": "y" * 16500}))
    verifica("contrario: una ripresa oltre 16 000 caratteri non si tiene", posto.ripresa is None)
    manda(buona(n=8), dict(R, n=8))
    posto.messaggi.clear()
    a.pagina(A, {"partita": pid, "tipo": "stato", "istantanea": buona(n=9)})
    verifica("contrario: un'istantanea senza ripresa la toglie (mai una partita vecchia)",
             posto.ripresa is None)
    pid2 = a.chiama("est_porte_fasi", {"partita": "nuova"}, "Dario", schermo=A)["partita"]
    r = a.pagina(A, {"partita": pid2, "tipo": "pronto"})
    verifica("contrario: una partita nuova parte da capo", "ripresa" not in r["avvio"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-gioco-stato-"))
    try:
        prova_valida()
        prova_server(radice / "server")
        prova_motore(radice / "motore")
        prova_domande()
        prova_ciclo(radice / "ciclo")
        prova_giudice()
        prova_nomi_motore(radice / "nomi")
        prova_nomi_server(radice / "nomi_server")
        prova_nomi_ciclo(radice / "nomi_ciclo")
        prova_ripresa_motore(radice / "ripresa")
        prova_ripresa_server(radice / "ripresa_server")
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
