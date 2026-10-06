import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova dell'esecuzione dimostrativa dei programmi dell'agente e dei linguaggi della sandbox
(calliope/agenti/esecuzione.py, linguaggi.py, 04/10/2026).

A secco (predefinito, anche su Windows), con il docker FINTO di prove/docker_finto.py (che
per il C# esegue il Python scritto in un commento /* FINTO_PY … */) e l'Ollama finto:
- linguaggi: immagine del C# dal suo Dockerfile, scelta con e senza immagine, mai fuori da un
  container; `docker run` del C# (immagine sua, esegui_cs.sh in sola lettura, niente _avvio.py,
  stesse regole di rete, disco, utente e tetti); «Random.cs» ammesso, «random.py» no;
- sandbox: stdout e stderr separati e in diretta (il primo pezzo arriva prima della fine),
  stdin dato al programma, C# con argomenti, errore di compilazione riconosciuto, C# assente;
- quale programma: indicato dall'agente, l'unico, main.py, `__main__`, un modulo di sole
  funzioni no, solo test no;
- esecuzione: scheda `esecuzione:<lavoro>-<n>` personale, prima in cima, aggiornamenti al loro
  posto al più ogni 0,3 s, tempo che scorre da `dal`, finale con il codice d'uscita; dati come
  argomenti e stdin; uscita troncata oltre il tetto (inizio e coda) anche nel file; tempo
  scaduto, «fermalo», errore con il codice e l'ultima riga dello stderr, C# che non si
  compila; la frase per la voce dice solo com'è finita e le ultime righe; i risultati del
  lavoro non si toccano; annuncio solo se la risposta non l'ha aspettata;
- tool: lavori_esegui (permessi, dati detti «3 e 5», risposta subito o «lo sto eseguendo»),
  lavori_annulla che ferma prima il programma;
- lavoro di codice con l'Ollama finto: a lavoro finito il programma si esegue sullo schermo,
  l'annuncio dice com'è andata e la scheda dell'esecuzione torna in cima; senza schermi no;
  l'agente vede esegui_csharp e i linguaggi solo se il C# c'è.

Con `--docker` (sulla DGX, con le immagini costruite: calliope motore sandbox costruisci
tutte): Python e C# veri nel container, con le misure (tempo d'avvio, compilazione, uscita in
diretta, rete assente nel C#, sola lettura, utente non root, tempo scaduto).
"""

import argparse
import json
import queue
import statistics
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from calliope.agenti import linguaggi
from calliope.agenti.esecuzione import Esecuzioni
from calliope.agenti.sandbox import ErroreSandbox, Sandbox, immagine_predefinita, scegli_isolamento
from calliope.config import Config

RADICE = Path(__file__).resolve().parent.parent
FINTO = [sys.executable, str(Path(__file__).with_name("docker_finto.py"))]
TMP = Path(tempfile.mkdtemp(prefix="calliope-esecuzione-"))
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def aspetta(cond, s=10.0):
    fine = time.monotonic() + s
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


class Registro:
    def __init__(self):
        self.schede, self.lock = [], threading.Lock()

    def __call__(self, card):
        with self.lock:
            self.schede.append((time.monotonic(), json.loads(json.dumps(card, default=str))))
        return {"destinatari": ["studio"], "schermi": ["studio"]}

    def tutte(self):
        with self.lock:
            return list(self.schede)


class LavoroFinto:
    """Un lavoro di codice finito, con i suoi file nella cartella dei risultati."""

    def __init__(self, lid, files: dict, persona="dario-id", nome="Dario", programma=""):
        self.id, self.tipo, self.titolo = lid, "codice", f"programma {lid}"
        self.persona, self.persona_nome, self.stato = persona, nome, "fatto"
        self.on_scheda, self.input, self.segui_schermi = None, None, True
        dest = TMP / "risultati" / lid
        dest.mkdir(parents=True, exist_ok=True)
        for k, v in files.items():
            (dest / k).parent.mkdir(parents=True, exist_ok=True)
            (dest / k).write_text(v, encoding="utf-8")
        self.risultato = {"cartella": str(dest), "file": sorted(files), "programma": programma}


class ServizioFinto:
    """Quello che Esecuzioni usa di Lavori."""

    def __init__(self, cfg, iso, isos):
        self.cfg, self.isolamento, self.isolamenti = cfg, iso, isos
        self._lock = threading.Lock()
        self.lavori, self.done, self.on_done = [], queue.Queue(), None


def cfg_base(**kw) -> Config:
    cfg = Config()
    cfg.agenti_sandbox = str(TMP / "sandbox")
    cfg.agenti_risultati = str(TMP / "risultati")
    cfg.agenti_dimostrazione_s = 8.0
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


PY_LENTO = ("import sys, time\nprint('primo', flush=True)\ntime.sleep(0.8)\n"
            "print('errore finto', file=sys.stderr, flush=True)\nprint('secondo')\n")
CS_ARGS = ("// Programma C# finto: il docker finto esegue il Python qui sotto\n"
           "/* FINTO_PY\nimport sys\nprint('argomenti:', ' '.join(sys.argv[1:]))\n"
           "print('stdin:', sys.stdin.read().split())\n*/\n"
           "Console.WriteLine(string.Join(\" \", args));\n")


# ═══════════════════════════ a secco ═══════════════════════════
def a_secco():
    os.environ["DOCKER_FINTO_DIR"] = str(TMP / "docker")
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    img_py = immagine_predefinita()
    img_cs = linguaggi.immagine("csharp")

    sezione("linguaggi e immagini")
    verifica("immagine del C# dal suo Dockerfile, con il suo prefisso",
             img_cs and img_cs.startswith("calliope-sandbox-dotnet:") and img_cs != img_py
             and len(img_cs.split(":")[1]) == 12, str(img_cs))
    df = (RADICE / "setup/linux/sandbox/Dockerfile.dotnet").read_text(encoding="utf-8")
    verifica("Dockerfile del C#: versioni fissate, runtime più compilatore, niente SDK intero",
             "sdk:10.0.401 AS sdk" in df and "runtime:10.0.12" in df and "USER 65534" in df
             and "COPY --from=sdk" in df, "")
    sh = (RADICE / "setup/linux/motore/sandbox.sh").read_text(encoding="utf-8")
    verifica("sandbox.sh costruisce anche il C# con lo stesso nome dell'immagine",
             "Dockerfile.dotnet" in sh and "calliope-sandbox-dotnet:" in sh and "csharp" in sh)
    os.environ["DOCKER_FINTO_IMMAGINI"] = f"{img_py},{img_cs}"
    iso = scegli_isolamento("auto", docker=FINTO, posix=True)
    cfg = cfg_base()
    isos = linguaggi.scegli(cfg, iso)
    verifica("con le due immagini: Python e C# pronti", linguaggi.pronti(isos) == ["python", "csharp"]
             and isos["csharp"].immagine == img_cs, str({k: v.descrizione for k, v in isos.items()}))
    os.environ["DOCKER_FINTO_IMMAGINI"] = img_py
    isos_senza = linguaggi.scegli(cfg, iso)
    verifica("senza l'immagine del C#: non pronto, con il passo «costruisci csharp»",
             linguaggi.pronti(isos_senza) == ["python"]
             and "calliope motore sandbox costruisci csharp" in isos_senza["csharp"].passo
             and "C# non disponibile" in isos_senza["csharp"].descrizione,
             isos_senza["csharp"].descrizione + " | " + isos_senza["csharp"].passo)
    iso_proc = scegli_isolamento("processo")
    isos_proc = linguaggi.scegli(cfg, iso_proc)
    verifica("motore «processo»: il C# mai fuori da un container",
             linguaggi.pronti(isos_proc) == ["python"] and not isos_proc["csharp"].pronto)
    verifica("agenti_linguaggi: solo Python → niente C#",
             # «javascript» (05/10) è il container dei test dei giochi, non un linguaggio dei
             # programmi: c'è sempre accanto a Python
             [k for k in linguaggi.scegli(cfg_base(agenti_linguaggi=["python"]), iso)
              if k != "javascript"] == ["python"])
    os.environ["DOCKER_FINTO_IMMAGINI"] = f"{img_py},{img_cs}"

    sezione("sandbox: docker run del C#, percorsi")
    sb = Sandbox(TMP / "sb1", tempo_s=5, memoria_mb=512, isolamento=iso, linguaggi=isos)
    cmd = sb._comando_docker("calliope-sandbox-prova", "csharp", ".", ["3", "5"],
                             isolamento=isos["csharp"])
    s = " ".join(cmd)
    attesi = ["run --rm -i", "--network none", "--read-only", "--cap-drop ALL",
              "--security-opt no-new-privileges", "--pull never", "--memory 512m",
              "--pids-limit", f"{img_cs} timeout -s KILL 10 sh /opt/calliope/esegui_cs.sh . 3 5"]
    mancano = [a for a in attesi if a not in s]
    mounts = [cmd[j + 1] for j, a in enumerate(cmd) if a == "--mount"]
    verifica("C#: stesso isolamento, la sua immagine, esegui_cs.sh in sola lettura",
             not mancano and len(mounts) == 2 and "esegui_cs.sh" in mounts[1]
             and mounts[1].endswith(",readonly") and "_avvio.py" not in s, str(mancano or mounts))
    i = cmd.index("--user")
    verifica("C#: utente non root", not cmd[i + 1].startswith("0:"), cmd[i + 1])
    cmd_py = " ".join(sb._comando_docker("x", "script", "a.py", []))
    verifica("Python: stessa immagine di prima, uscita senza buffer (-u) per la diretta",
             f"{img_py} timeout -s KILL 10 python -I -B -u" in cmd_py, "")
    for nome, ok in (("Random.cs", True), ("Program.cs", True), ("random.py", False),
                     ("json/x.cs", False)):
        try:
            sb.percorso(nome, scrittura=True)
            esito = True
        except ErroreSandbox:
            esito = False
        verifica(f"percorso «{nome}» {'ammesso' if ok else 'rifiutato'}", esito == ok)

    sezione("sandbox: uscita in diretta, stdin, C#")
    sb.scrivi("lento.py", PY_LENTO)
    pezzi, t_primo = [], [None]
    t0 = time.monotonic()

    def flusso(tipo, t):
        if t_primo[0] is None:
            t_primo[0] = time.monotonic() - t0
        pezzi.append((tipo, t))
    r = sb.esegui("lento.py", flusso=flusso)
    dt = time.monotonic() - t0
    verifica("il primo pezzo arriva prima della fine (uscita in diretta)",
             t_primo[0] is not None and t_primo[0] < dt - 0.5, f"primo {t_primo[0]:.2f} s, "
             f"fine {dt:.2f} s")
    err = "".join(v for k, v in pezzi if k == "err").replace("\r", "")
    out = "".join(v for k, v in pezzi if k == "out").replace("\r", "")
    verifica("stdout e stderr separati", err == "errore finto\n" and out == "primo\nsecondo\n",
             str(pezzi))
    sb.scrivi("leggi.py", "import sys\nprint('letto:', sys.stdin.read().split())\n")
    r = sb.esegui("leggi.py", stdin="3\n5\n")
    verifica("stdin dato al programma (dopo la riga di configurazione)",
             "letto: ['3', '5']" in r["uscita"], r["uscita"][-200:])
    sb.scrivi("Program.cs", CS_ARGS)
    r = sb.esegui("Program.cs", ["3", "5"], stdin="3\n5\n")
    verifica("C#: compilato ed eseguito nel suo container, con argomenti e stdin",
             r["codice_uscita"] == 0 and "argomenti: 3 5" in r["uscita"]
             and "stdin: ['3', '5']" in r["uscita"], r["uscita"][-200:])
    log = [json.loads(x) for x in (TMP / "docker" / "comandi.jsonl").read_text(
        encoding="utf-8").splitlines()]
    verifica("C#: passa da docker run con l'immagine del C#",
             any(c[:1] == ["run"] and img_cs in c for c in log))
    sb.scrivi("Rotto.cs", "// FINTO_ERRORE_COMPILAZIONE\nclass X {\n")
    r = sb.esegui_cs("", [])
    verifica("C#: errore di compilazione riconosciuto", r.get("compilazione") is False
             and r["codice_uscita"] != 0 and "CS1002" in r["uscita"], str(r)[:200])
    (sb.root / "Rotto.cs").unlink()
    sb2 = Sandbox(TMP / "sb2", tempo_s=5, isolamento=iso, linguaggi=isos_senza)
    sb2.scrivi("Program.cs", CS_ARGS)
    try:
        sb2.esegui("Program.cs")
        verifica("C# senza immagine: rifiutato con il motivo", False)
    except ErroreSandbox as e:
        verifica("C# senza immagine: rifiutato con il motivo", "C#" in str(e) and "Python" in str(e),
                 str(e))

    sezione("quale programma")
    casi = [
        ({"main.py": "print(1)\n", "utile.py": "def f():\n    pass\n", "test_utile.py": "x = 1\n"},
         "", "main.py"),
        ({"calcola.py": "import sys\nprint(sum(map(int, sys.argv[1:])))\n",
          "test_calcola.py": "def test_a():\n    assert True\n"}, "", "calcola.py"),
        ({"somma.py": "def somma(a, b):\n    return a + b\n",
          "test_somma.py": "def test_a():\n    assert True\n"}, "", None),
        ({"a.py": "def f():\n    pass\n\nif __name__ == '__main__':\n    f()\n",
          "b.py": "X = 1\n", "c.py": "print('c')\n"}, "", "a.py"),
        ({"a.py": "print('a')\n", "b.py": "print('b')\n"}, "b.py", "b.py"),
        ({"Program.cs": "Console.WriteLine(1);\n", "Calcolo.cs": "class C {}\n"}, "", "Calcolo.cs"),
        ({"test_x.py": "def test_a():\n    assert True\n"}, "", None),
    ]
    for i, (files, prog, atteso) in enumerate(casi):
        lav = LavoroFinto(f"Q{i}", files, programma=prog)
        got, perche = Esecuzioni.programma_di(lav)
        verifica(f"programma tra {sorted(files)} (indicato «{prog}»): {atteso}", got == atteso,
                 f"{got} {perche}")

    sezione("esecuzione in diretta sulla scheda")
    svc = ServizioFinto(cfg_base(), iso, isos)
    esec = Esecuzioni(svc, log=lambda *_: None)
    lav = LavoroFinto("L1", {"calcolo.py": "import sys, time\nfor i in range(6):\n"
                             "    print(f'{i} x {i} = {i*i}', flush=True)\n    time.sleep(0.15)\n"
                             "print('dati:', sys.argv[1:], sys.stdin.read().split())\n"})
    svc.lavori.append(lav)
    reg = Registro()
    t0 = time.perf_counter()
    es, frase = esec.avvia(lav, ["3", "5"], on_scheda=reg)
    dt_avvia = time.perf_counter() - t0
    verifica("avvia non aspetta Docker", es is not None and dt_avvia < 0.3,
             f"{dt_avvia * 1000:.0f} ms {frase}")
    finita = esec.attendi(es, 15)
    tutte = reg.tutte()
    chiavi = {c.get("chiave") for _, c in tutte}
    verifica("finita e senza annuncio (la risposta l'ha aspettata)",
             finita and es.stato == "fatto" and es.annuncia is False and svc.done.empty())
    verifica("una chiave sola, esecuzione:L1-1, personale", chiavi == {"esecuzione:L1-1"}
             and all(c["visibilita"] == "personale" for _, c in tutte), str(chiavi))
    verifica("la prima scheda va in cima, in corso, con il tempo da cui contare",
             tutte[0][1].get("sposta") is not False and tutte[0][1]["stato"] == "in_corso"
             and tutte[0][1]["dal"], str(tutte[0][1])[:200])
    agg = [(t, c) for t, c in tutte[1:-1]]
    gaps = [b[0] - a[0] for a, b in zip(agg, agg[1:])]
    verifica("aggiornamenti al loro posto, al più uno ogni 0,3 s",
             agg and all(c.get("sposta") is False for _, c in agg)
             and all(g >= 0.27 for g in gaps), f"{len(agg)} aggiornamenti, gap minimo "
             f"{min(gaps) if gaps else 0:.2f}")
    verifica("l'uscita cresce mentre il programma gira",
             any(c["stato"] == "in_corso" and "2 x 2" in "".join(r["testo"] for r in c["righe"])
                 for _, c in tutte), "")
    fin = tutte[-1][1]
    verifica("finale: finito, codice 0, niente tempo che scorre, dati mostrati, file d'uscita",
             fin["stato"] == "fatto" and fin["codice_uscita"] == 0 and fin["dal"] is None
             and fin["dati"] == ["3", "5"] and fin["file"] == "esecuzione-1.txt", str(fin)[:300])
    testo = "".join(r["testo"] for r in fin["righe"])
    verifica("dati come argomenti e come stdin", "dati: ['3', '5'] ['3', '5']" in testo, testo[-80:])
    fr = esec.frase(es)
    verifica("la voce: com'è finito e le ultime righe, non tutto",
             fr.startswith("Il programma ha finito in") and "«5 x 5 = 25»" in fr
             and "0 x 0" not in fr and "sullo schermo" in fr, fr)
    dest = Path(lav.risultato["cartella"])
    verifica("i risultati del lavoro restano com'erano (più il file d'uscita)",
             sorted(p.name for p in dest.iterdir()) == ["calcolo.py", "esecuzione-1.txt"])
    verifica("la cartella dell'esecuzione si cancella", not es.sandbox.root.exists())

    sezione("tetti: uscita lunga, tempo, fermalo, errori")
    lav2 = LavoroFinto("L2", {"molto.py": "for i in range(20000):\n    print('riga', i)\n"})
    es2, _ = esec.avvia(lav2, on_scheda=(reg2 := Registro()))
    esec.attendi(es2, 20)
    fin = reg2.tutte()[-1][1]
    testo = "".join(r["testo"] for r in fin["righe"])
    verifica("uscita oltre il tetto: tagliata, con i caratteri omessi e la coda",
             fin["omessi"] > 100_000 and "riga 19999" in testo and len(testo) <= 12_000
             and es2.caratteri > 200_000, f"omessi {fin['omessi']}, {len(testo)} sulla scheda")
    f2 = (Path(lav2.risultato["cartella"]) / "esecuzione-1.txt").read_text(encoding="utf-8")
    verifica("anche il file è troncato: l'inizio, il segno, la coda",
             "riga 0\n" in f2 and "caratteri omessi" in f2 and "riga 19999" in f2
             and len(f2) < 70 * 1024, f"{len(f2)} caratteri")
    fr = esec.frase(es2)
    verifica("la voce: solo le ultime righe", "«riga 19998», «riga 19999»" in fr and len(fr) < 200, fr)

    svc.cfg.agenti_dimostrazione_s = 1.5
    lav3 = LavoroFinto("L3", {"infinito.py": "import time\nwhile True:\n    time.sleep(0.1)\n"})
    es3, _ = esec.avvia(lav3)
    finita = esec.attendi(es3, 0.2)
    verifica("non finita in tempo: annuncio dopo", not finita and es3.annuncia)
    item = svc.done.get(timeout=15)
    verifica("tempo scaduto: fermato, annuncio a chi l'ha chiesto",
             es3.stato == "scaduto" and item["tipo"] == "esecuzione" and item["chi"] == "dario-id"
             and item["messaggio"].startswith("Dario, ho fermato il programma dopo"),
             item["messaggio"])
    svc.cfg.agenti_dimostrazione_s = 8.0
    lav4 = LavoroFinto("L4", {"lungo.py": "import time\nprint('parto', flush=True)\n"
                              "time.sleep(30)\n"})
    es4, _ = esec.avvia(lav4, on_scheda=(reg4 := Registro()))
    aspetta(lambda: "parto" in es4.testo(), 10)
    t0 = time.perf_counter()
    altri = esec.ferma("bianca-id")
    verifica("fermalo: una familiare non ferma il programma di un altro", not altri)
    fermate = esec.ferma("dario-id")
    dt_ferma = time.perf_counter() - t0
    esec.attendi(es4, 10)
    verifica("fermalo: subito, con docker kill", fermate == [es4] and es4.stato == "fermato"
             and dt_ferma < 0.3 and es4.fine - es4.inizio < 6,
             f"{dt_ferma * 1000:.0f} ms, durata {es4.fine - es4.inizio:.1f} s")
    verifica("fermalo: la scheda finale lo dice", reg4.tutte()[-1][1]["stato"] == "fermato")
    lav5 = LavoroFinto("L5", {"rotto.py": "import sys\nprint('calcolo…')\n"
                              "print('divisione per zero', file=sys.stderr)\nsys.exit(3)\n"})
    es5, _ = esec.avvia(lav5)
    esec.attendi(es5, 10)
    fr = esec.frase(es5)
    verifica("errore: il codice d'uscita e l'ultima riga dello stderr",
             es5.stato == "errore" and "codice 3" in fr and "divisione per zero" in fr, fr)
    lav6 = LavoroFinto("L6", {"Program.cs": "// FINTO_ERRORE_COMPILAZIONE\n"})
    es6, _ = esec.avvia(lav6)
    esec.attendi(es6, 10)
    fr = esec.frase(es6)
    verifica("C# che non si compila: lo dice con l'errore", es6.stato == "errore"
             and fr.startswith("Il programma non si compila") and "CS1002" in fr, fr)
    lav7 = LavoroFinto("L7", {"Program.cs": CS_ARGS})
    es7, _ = esec.avvia(lav7, ["7", "8"])
    esec.attendi(es7, 10)
    verifica("C#: eseguito con i dati", es7.stato == "fatto" and "argomenti: 7 8" in es7.testo(),
             es7.testo()[-100:])
    es8, frase = esec.avvia(lav7) if not esec.in_corso() else (None, "")
    esec.attendi(es8, 10)
    verifica("una seconda esecuzione ha il suo numero", es8 and es8.id == "L7-2", es8 and es8.id)
    svc_no = ServizioFinto(cfg_base(), iso, isos_senza)
    es9, frase = Esecuzioni(svc_no, log=lambda *_: None).avvia(LavoroFinto("L9", {"P.cs": CS_ARGS}))
    verifica("C# senza immagine: non parte, e dice il passo",
             es9 is None and "C#" in frase and "costruisci csharp" in frase, frase)
    lav10 = LavoroFinto("L10", {"somma.py": "def somma(a, b):\n    return a + b\n"})
    es10, frase = esec.avvia(lav10)
    verifica("un modulo di sole funzioni non si esegue, e lo dice", es10 is None
             and "solo funzioni" in frase, frase)

    sezione("tool lavori_esegui e lavori_annulla")
    tool_e_annulla(iso, isos)

    sezione("lavoro di codice: dimostrazione a lavoro finito")
    dimostrazione(iso, isos)

    sezione("agente: linguaggi nel prompt e negli strumenti")
    from calliope.agenti.ciclo import sistema_codice, strumenti_codice
    nomi = [t["function"]["name"] for t in strumenti_codice(["python", "csharp"])]
    verifica("con il C#: esegui_csharp tra gli strumenti", "esegui_csharp" in nomi)
    verifica("senza il C#: niente esegui_csharp",
             "esegui_csharp" not in [t["function"]["name"] for t in strumenti_codice(["python"])])
    p_cs, p_py = sistema_codice(["python", "csharp"]), sistema_codice(["python"])
    verifica("prompt con il C#: i due linguaggi, il «impossibile» per gli altri, le pagine web "
             "ammesse, il programma da eseguire senza input",
             "C# con .NET 10" in p_cs and "diverso da Python o C#" in p_cs
             and "pagine web" in p_cs and "programma = il file da eseguire" in p_cs
             and "senza input dalla tastiera" in p_cs, "")
    verifica("prompt senza il C#: solo Python", "C#" not in p_py and "solo Python" in p_py)
    from calliope.agenti.ciclo import STRUMENTI_CODICE
    cons = next(t for t in STRUMENTI_CODICE if t["function"]["name"] == "consegna")
    verifica("consegna ha «programma»", "programma" in cons["function"]["parameters"]["properties"])
    from calliope.agenti.ciclo import per_la_voce
    verifica("«C#» nel riassunto per la voce resta (il # di «#include» no)",
             per_la_voce("Qui posso eseguire solo Python e C#. Va bene?")
             == "Qui posso eseguire solo Python e C#. Va bene?"
             and per_la_voce("Uso #include. Fatto.") == "Fatto.")

    sezione("pagina")
    js = (RADICE / "calliope/schermi/pagina/schermo.js").read_text(encoding="utf-8")
    verifica("la pagina disegna la scheda «esecuzione» come testo, con il tempo che scorre",
             "DISEGNA.esecuzione" in js and "dalEsec" in js
             and "innerHTML" not in js)


def tool_e_annulla(iso, isos):
    from calliope.tools.builtin import build_registry
    from calliope.tools.spec import ToolContext
    from calliope.documenti.formato import FORMATI

    class Prof:
        def __init__(self, pid, name):
            self.id, self.name = pid, name

    class Speakers:
        p = {"Dario": Prof("dario-id", "Dario"), "Bianca": Prof("bianca-id", "Bianca")}

        def get(self, n):
            return self.p.get(n)

        def known_speakers(self):
            return list(self.p)

    class SpeakerCtx:
        def __init__(self, name, level):
            self.current_speaker, self.current_level, self.from_session = name, level, False
            self.identified_by = "voce"

    class Hub:
        automatiche = True

        def __init__(self):
            self.reg = Registro()

        def mittente(self, ctx):
            return ctx.speaker_ctx.current_speaker

        def invia(self, card, mitt, forza=False):
            return self.reg(card)

    class SvcConLavori(ServizioFinto):
        def annulla(self, persona=None, tutti_di_tutti=False, quale="ultimo"):
            return {"ok": False, "frase": "Non ho lavori in corso da fermare."}

    cfg = cfg_base(agenti_esecuzione_attesa_s=3.0)
    svc = SvcConLavori(cfg, iso, isos)
    svc.esecuzioni = Esecuzioni(svc, log=lambda *_: None)
    hub = Hub()
    reg = build_registry(documenti=FORMATI, agenti=True)

    def tool(name, args, chi, livello):
        ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                          speaker=None, lavori=svc, schermi=hub, turno=1, user_text="")
        t0 = time.perf_counter()
        out = json.loads(reg.call(name, args, ctx, livello))
        return out, time.perf_counter() - t0

    out, _ = tool("lavori_esegui", {}, "Dario", "amministra")
    verifica("nessun programma: lo dice", out.get("ok") is False and "Non ho programmi" in
             out["risposta_finale"], out.get("risposta_finale"))
    lav = LavoroFinto("L20", {"conti.py": "import sys\nn = [int(x) for x in sys.argv[1:]] or [2, 2]\n"
                              "print('somma', sum(n))\n"})
    svc.lavori.append(lav)
    out, _ = tool("lavori_esegui", {}, None, "ospite")
    verifica("ospite: il registro rifiuta", out.get("ok") is False)
    out, _ = tool("lavori_esegui", {}, "Bianca", "familiare")
    verifica("il programma di un altro: rifiutato", out.get("ok") is False
             and "un altro" in out["risposta_finale"], out.get("risposta_finale"))
    out, dt = tool("lavori_esegui", {"dati": "3 e 5"}, "Dario", "amministra")
    verifica("«eseguilo con 3 e 5»: i dati separati, la risposta con l'esito",
             out.get("ok") and "«somma 8»" in out["risposta_finale"]
             and "sullo schermo" in out["risposta_finale"], f"{out.get('risposta_finale')} "
             f"{dt:.2f} s")
    card = hub.reg.tutte()[-1][1]
    verifica("la scheda va allo schermo di chi l'ha chiesto, con la chiave della seconda "
             "esecuzione", card["chiave"] == "esecuzione:L20-1" and card["dati"] == ["3", "5"],
             card.get("chiave"))
    out, _ = tool("lavori_esegui", {"dati": ["10", "20", "30"], "lavoro": "L20"}, "Bianca",
                  "amministra")
    verifica("chi amministra esegue anche il programma di un altro, dati come elenco",
             out.get("ok") and "«somma 60»" in out["risposta_finale"], out.get("risposta_finale"))
    lav2 = LavoroFinto("L21", {"lento.py": "import time\nprint('vado', flush=True)\n"
                               "time.sleep(30)\n"})
    svc.lavori.append(lav2)
    cfg.agenti_esecuzione_attesa_s = 0.3
    out, dt = tool("lavori_esegui", {}, "Dario", "amministra")
    verifica("programma lungo: «lo sto eseguendo», subito", out.get("ok")
             and out["risposta_finale"].startswith("Lo sto eseguendo") and dt < 1.0,
             f"{out.get('risposta_finale')} {dt:.2f} s")
    out, dt = tool("lavori_annulla", {}, "Dario", "amministra")
    # `Sandbox.termina` lancia `docker kill` e lo aspetta: con il docker finto è un processo
    # Python, 0,1 s a vuoto e oltre 0,4 s con due runner insieme (06/10). Il tetto guarda che
    # non si aspetti la fine del programma (30 s), non l'avvio di un processo
    verifica("«fermalo»: ferma prima il programma", out.get("ok")
             and out["risposta_finale"] == "Ho fermato il programma." and dt < 1.5,
             f"{out.get('risposta_finale')} {dt * 1000:.0f} ms")
    try:
        item = svc.done.get(timeout=10)
    except queue.Empty:
        item = None
    verifica("fermato: l'annuncio lo dice", item and "ho fermato il programma" in
             item["messaggio"].lower(), str(item and item["messaggio"]))
    out, _ = tool("lavori_annulla", {}, "Dario", "amministra")
    verifica("«fermalo» senza programmi in corso: passa ai lavori", "Non ho lavori" in
             out["risposta_finale"], out.get("risposta_finale"))
    verifica("lavori_esegui per i familiari, non per gli ospiti",
             reg.allowed("lavori_esegui", "familiare") and not reg.allowed("lavori_esegui",
                                                                          "ospite"))


def dimostrazione(iso, isos):
    from calliope.agenti import Lavori, carica
    from prove.ollama_finto import FakeOllama
    fake = FakeOllama(modelli=("qwen3.6:35b",)).avvia()

    def call(name, args=None):
        return {"name": name, "arguments": args or {}}

    def servizio(**kw):
        cfg = cfg_base(agenti_url=fake.url, agenti_modello="qwen3.6:35b",
                       agenti_modelli=str(TMP / "modelli"), llm_native_url="http://127.0.0.1:9",
                       **kw)
        svc = Lavori(cfg, carica(cfg), log=lambda *_: None)
        svc.scegli_isolamento = lambda: (setattr(svc, "isolamento", iso),
                                         setattr(svc, "isolamenti", isos), iso)[-1]
        return svc
    prog = ("import random\nrandom.seed(4)\nfor _ in range(3):\n"
            "    a, b = random.randint(1, 9), random.randint(1, 9)\n"
            "    print(f'{a} + {b} = {a + b}')\n")
    copione = [
        {"tool_calls": [call("scrivi_file", {"percorso": "calcolo.py", "contenuto": prog})]},
        {"tool_calls": [call("esegui_python", {"percorso": "calcolo.py"})]},
        {"tool_calls": [call("consegna", {"riassunto": "Ho scritto il programma delle somme.",
                                          "esito": "fatto", "programma": "calcolo.py"})]},
    ]
    fake.copione = list(copione)
    svc = servizio()
    reg = Registro()
    lav = svc.nuovo("codice", "Scrivi un programma che fa somme con numeri casuali",
                    "dario-id", "Dario", "amministra")
    lav.on_scheda = reg
    svc.avvia(lav)
    item = svc.done.get(timeout=30)
    msg = item["messaggio"]
    verifica("l'annuncio del lavoro dice com'è andata l'esecuzione",
             item["stato"] == "fatto" and "Il programma ha finito in" in msg
             and "Le ultime righe dicono" in msg, msg)
    tutte = reg.tutte()
    chiavi = [c.get("chiave") for _, c in tutte]
    ultima_lav = max(i for i, k in enumerate(chiavi) if k == f"lavoro:{lav.id}")
    dopo = [c for _, c in tutte[ultima_lav + 1:]]
    verifica("dopo la scheda finale del lavoro torna in cima quella dell'esecuzione",
             dopo and dopo[-1]["chiave"] == f"esecuzione:{lav.id}-1"
             and dopo[-1].get("sposta") is not False and dopo[-1]["stato"] == "fatto",
             str([(c.get("chiave"), c.get("sposta")) for c in dopo]))
    verifica("il programma indicato dall'agente nel risultato", lav.risultato.get("programma")
             == "calcolo.py")
    verifica("nessun annuncio in più (l'esecuzione era finita)", svc.done.empty())
    # Senza schermi: niente esecuzione
    fake.copione = list(copione)
    lav2 = svc.nuovo("codice", "Lo stesso, senza schermi", "dario-id", "Dario", "amministra")
    svc.avvia(lav2)
    item = svc.done.get(timeout=30)
    verifica("senza schermi niente esecuzione dimostrativa",
             "Il programma ha finito" not in item["messaggio"] and not svc.esecuzioni.tutte[1:],
             item["messaggio"])
    # Programma lento: l'annuncio non aspetta oltre il tetto, poi un annuncio a parte
    fake.copione = [
        {"tool_calls": [call("scrivi_file", {"percorso": "lento.py", "contenuto":
                        "import time\nprint('inizio', flush=True)\ntime.sleep(2)\nprint('fine')\n"})]},
        {"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]},
    ]
    # Un altro servizio: un'altra cartella della sandbox (anche lui comincia da L1)
    svc2 = servizio(agenti_dimostrazione_attesa_s=0.3, agenti_sandbox=str(TMP / "sandbox2"))
    lav3 = svc2.nuovo("codice", "Programma lento", "dario-id", "Dario", "amministra")
    lav3.on_scheda = Registro()
    svc2.avvia(lav3)
    item = svc2.done.get(timeout=30)
    verifica("programma lento: «lo sto eseguendo» nell'annuncio",
             "Lo sto eseguendo" in item["messaggio"], item["messaggio"])
    item2 = svc2.done.get(timeout=20)
    verifica("poi l'annuncio dell'esecuzione", item2["tipo"] == "esecuzione"
             and "«fine»" in item2["messaggio"], item2["messaggio"])
    svc.close()
    svc2.close()


# ═══════════════════════════ Docker vero (DGX) ═══════════════════════════
def docker_vero():
    iso = scegli_isolamento("docker")
    cfg = cfg_base()
    isos = linguaggi.scegli(cfg, iso)
    verifica("Docker e le immagini di Python e del C# pronti",
             linguaggi.pronti(isos) == ["python", "csharp"],
             str({k: v.descrizione for k, v in isos.items()}))
    if linguaggi.pronti(isos) != ["python", "csharp"]:
        return
    for nome in ("calliope-sandbox", "calliope-sandbox-dotnet"):
        r = subprocess.run(["docker", "images", nome, "--format", "{{.Tag}} {{.Size}}"],
                           capture_output=True, text=True)
        print(f"   immagine {nome}: {r.stdout.strip()}")
    sb = Sandbox(TMP / "vero", tempo_s=20, memoria_mb=512, isolamento=iso, linguaggi=isos)
    sb.scrivi("ciao.py", "print('ciao')\n")
    sb.scrivi("Program.cs",
              "var rnd = new Random(7);\n"
              "for (int i = 0; i < 5; i++) {\n"
              "    int a = rnd.Next(1, 100), b = rnd.Next(1, 100);\n"
              "    Console.WriteLine($\"{a} x {b} = {a * b}\");\n"
              "    Thread.Sleep(300);\n}\n"
              "Console.Error.WriteLine(\"fine (stderr)\");\n"
              "Console.WriteLine(\"argomenti: \" + string.Join(\" \", args));\n"
              "var riga = Console.In.ReadLine();\nConsole.WriteLine(\"stdin: \" + riga);\n")
    tempi_py, tempi_cs = [], []
    for _ in range(5):
        tempi_py.append(sb.esegui("ciao.py")["secondi"])
    pezzi, t_primo = [], [None]
    t0 = time.monotonic()

    def flusso(tipo, t):
        if t_primo[0] is None:
            t_primo[0] = time.monotonic() - t0
        pezzi.append((tipo, t))
    r = sb.esegui("Program.cs", ["3", "5"], stdin="ciao\n", flusso=flusso)
    dt = time.monotonic() - t0
    uscita = "".join(t for _, t in pezzi)
    verifica("C# vero: compila, esegue, argomenti e stdin", r["codice_uscita"] == 0
             and "argomenti: 3 5" in uscita and "stdin: ciao" in uscita, uscita[-300:])
    verifica("C# vero: la prima riga arriva prima della fine (diretta)",
             t_primo[0] is not None and t_primo[0] < dt - 1.0,
             f"prima riga {t_primo[0]:.2f} s, fine {dt:.2f} s")
    verifica("C# vero: stderr separato", ("err", "fine (stderr)\n") in pezzi, str(pezzi[-4:]))
    sb.scrivi("Program.cs", "Console.WriteLine(\"ok\");\n")
    for _ in range(5):
        tempi_cs.append(sb.esegui("Program.cs")["secondi"])
    print(f"   Python: mediana {statistics.median(tempi_py):.3f} s; C# (compila ed esegue): "
          f"mediana {statistics.median(tempi_cs):.3f} s, max {max(tempi_cs):.3f}")
    attacchi = {
        "rete": ("try { new System.Net.Sockets.TcpClient(\"1.1.1.1\", 80); "
                 "Console.WriteLine(\"RETE APERTA\"); } catch (Exception e) "
                 "{ Console.WriteLine(\"rete bloccata: \" + e.GetType().Name); }\n"),
        "scrittura": ("try { File.WriteAllText(\"/opt/x\", \"x\"); Console.WriteLine(\"SCRITTO\"); }"
                      " catch (Exception e) { Console.WriteLine(\"sola lettura: \" + e.GetType().Name); }\n"),
        "utente": "Console.WriteLine(\"uid \" + Environment.GetEnvironmentVariable(\"HOME\") + \" \" + "
                  "System.Diagnostics.Process.GetCurrentProcess().Id);\n"
                  "Console.WriteLine(File.ReadAllText(\"/proc/self/status\").Split('\\n')"
                  ".First(l => l.StartsWith(\"Uid:\")));\n",
        "processi": ("try { System.Diagnostics.Process.Start(\"/bin/sh\", \"-c true\"); "
                     "Console.WriteLine(\"processo avviato\"); } catch (Exception e) "
                     "{ Console.WriteLine(\"processo: \" + e.GetType().Name); }\n"),
    }
    for nome, codice in attacchi.items():
        sb.scrivi("Program.cs", codice)
        r = sb.esegui("Program.cs")
        out = r["uscita"].strip()
        if nome == "rete":
            verifica("C#: rete irraggiungibile", "rete bloccata" in out, out[-200:])
        elif nome == "scrittura":
            verifica("C#: disco in sola lettura fuori dalla cartella", "sola lettura" in out,
                     out[-200:])
        elif nome == "utente":
            verifica("C#: utente non root", "Uid:" in out and "\t0\t" not in out, out[-200:])
        else:
            print(f"   processi nel container C# (limitati da --pids-limit): {out[-120:]}")
    sb.scrivi("Program.cs", "while (true) { }\n")
    sb.tempo_s = 3
    t0 = time.monotonic()
    r = sb.esegui("Program.cs")
    verifica("C#: tempo scaduto, container fermato", r["scaduto"] and time.monotonic() - t0 < 8,
             f"{time.monotonic() - t0:.1f} s")
    rimasti = subprocess.run(["docker", "ps", "-aq", "--filter", "label=calliope.sandbox=1"],
                             capture_output=True, text=True).stdout.split()
    verifica("nessun container rimasto", not rimasti, str(rimasti))
    # Esecuzione dimostrativa vera del caso dell'utente, con la scheda
    svc = ServizioFinto(cfg, iso, isos)
    esec = Esecuzioni(svc, log=print)
    lav = LavoroFinto("D1", {"Program.cs":
                             "var rnd = new Random();\n"
                             "for (int i = 0; i < 4; i++) {\n"
                             "    double a = rnd.Next(1, 50), b = rnd.Next(1, 50);\n"
                             "    Console.WriteLine($\"Input: a={a}, b={b} -> ipotenusa = "
                             "{Math.Sqrt(a * a + b * b):F2}\");\n    Thread.Sleep(250);\n}\n"})
    reg = Registro()
    es, _ = esec.avvia(lav, on_scheda=reg)
    esec.attendi(es, 30)
    print(f"   esecuzione dimostrativa C#: {es.stato} in {es.fine - es.inizio:.2f} s, "
          f"{len(reg.tutte())} schede; voce: {esec.frase(es)}")
    verifica("esecuzione dimostrativa C# vera: finita, schede in diretta",
             es.stato == "fatto" and len(reg.tutte()) >= 3, f"{len(reg.tutte())} schede")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prova dell'esecuzione dimostrativa e dei linguaggi")
    ap.add_argument("--docker", action="store_true",
                    help="Docker vero (DGX, con le immagini costruite) invece del docker finto")
    a = ap.parse_args()
    if a.docker:
        docker_vero()
    else:
        a_secco()
    print(f"\n{'Tutto a posto' if not errori else f'{errori} errori'} "
          f"({time.perf_counter() - T0:.1f} s)")
    sys.exit(1 if errori else 0)
