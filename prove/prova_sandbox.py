import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova della sandbox con il motore «docker» (calliope/agenti/sandbox.py, 03/10/2026).

A secco (predefinito, anche su Windows), con il docker FINTO di prove/docker_finto.py:
- nome dell'immagine dal Dockerfile; scelta del motore: auto con e senza immagine, Docker
  assente, senza permessi, muto (tempo massimo), Windows, «processo» e «docker» espliciti
  (docker non pronto = niente esecuzione);
- il comando `docker run`: niente rete, disco in sola lettura, niente capability,
  no-new-privileges, utente non root, memoria, processi, CPU, _avvio.py in sola lettura,
  timeout dentro il container, nessuna variabile dell'host;
- esecuzioni attraverso il docker finto: script, test con l'esito, attacchi fermati
  dall'audit hook (seconda linea), tempo scaduto con `docker kill`, annullo con `docker kill`;
- registro delle capacità: la capacità «agenti» dice quale isolamento è attivo.

Con `--docker` (sulla DGX, con l'immagine costruita: calliope motore sandbox costruisci),
Docker vero:
- gli attacchi di prova_agenti dentro il container (rete, file fuori, processi, ctypes,
  sottointerpreti, fork, memoria, tempo), openpyxl e i test;
- senza audit hook (python -c nel container, lo stesso `docker run`): rete davvero
  irraggiungibile (solo loopback), disco in sola lettura, nessuna capability, utente non
  root, file dell'host invisibili, socket di Docker assente, fork bomb fermata dal tetto dei
  processi, memoria;
- costo d'avvio: mediana di 10 esecuzioni contro il motore «processo».
"""

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from calliope import capacita
from calliope.agenti.sandbox import (ErroreSandbox, Isolamento, Sandbox, immagine_predefinita,
                                     scegli_isolamento)
from calliope.config import Config

RADICE = Path(__file__).resolve().parent.parent
FINTO = [sys.executable, str(Path(__file__).with_name("docker_finto.py"))]
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def ultima(out: str) -> str:
    righe = out.strip().splitlines()
    return righe[-1][:140] if righe else ""


# Gli attacchi di prova_agenti, nella versione Linux (dentro il container)
def attacchi_linux(fuori_leggi: Path, fuori_scrivi: Path, cartella_host: Path) -> dict:
    return {
        "rete": "import socket\nsocket.socket()\n",
        "rete_http": "import urllib.request\nurllib.request.urlopen('http://1.1.1.1')\n",
        "leggi_fuori": f"print(open(r'{fuori_leggi}').read()[:20])\n",
        "scrivi_fuori": f"open(r'{fuori_scrivi}', 'w').write('x')\n",
        "elenca_fuori": f"import os\nprint(os.listdir(r'{cartella_host}'))\n",
        "processi": "import subprocess\nsubprocess.run(['echo', 'x'])\n",
        "os_system": "import os\nos.system('echo x')\n",
        "ctypes_mem": "import ctypes\nctypes.string_at(id(1), 8)\n",
        "ctypes_dll": "import ctypes\nctypes.CDLL(None).getpid()\n",
        "sottointerprete": "from concurrent import interpreters\ninterpreters.create()\n",
        "chdir_fuori": "import os\nos.chdir('..')\n",
        "fork": "import os\nos.fork()\n",
        "fork_bomb": "import os\nwhile True:\n    os.fork()\n",
        "posix_spawn": "import os\nos.posix_spawn('/bin/echo', ['echo', 'x'], {})\n",
        "execv": "import os\nos.execv('/bin/echo', ['echo', 'x'])\n",
    }


# ═══════════════════════════ a secco ═══════════════════════════
def a_secco():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-sandbox-"))
    dfin = tmp / "docker"
    os.environ["DOCKER_FINTO_DIR"] = str(dfin)
    img = immagine_predefinita()

    sezione("immagine e scelta del motore")
    sha = hashlib.sha256((RADICE / "setup/linux/sandbox/Dockerfile").read_bytes()).hexdigest()
    verifica("nome dell'immagine dallo SHA-256 del Dockerfile (come sandbox.sh)",
             img == f"calliope-sandbox:{sha[:12]}", str(img))
    sh = (RADICE / "setup/linux/motore/sandbox.sh").read_text(encoding="utf-8")
    verifica("sandbox.sh usa lo stesso nome (sha256sum, 12 cifre) e chiede conferma",
             "sha256sum" in sh and "cut -c1-12" in sh and "calliope-sandbox:" in sh
             and "chiedi" in sh)
    verifica("immagine assente se manca il Dockerfile",
             immagine_predefinita(tmp / "non-c-e") is None)

    os.environ["DOCKER_FINTO_MODO"] = "ok"
    os.environ["DOCKER_FINTO_IMMAGINI"] = img
    iso = scegli_isolamento("auto", docker=FINTO, posix=True)
    verifica("auto con l'immagine: docker", iso.motore == "docker" and iso.pronto
             and iso.immagine == img and "senza rete" in iso.descrizione, iso.descrizione)
    verifica("descrizione senza il nome tecnico dell'immagine (si legge a voce)",
             "calliope-sandbox" not in iso.descrizione and not re.search(r"[0-9a-f]{12}",
                                                                          iso.descrizione))
    os.environ["DOCKER_FINTO_IMMAGINI"] = "altra:1"
    iso = scegli_isolamento("auto", docker=FINTO, posix=True)
    # Dal 03/10 (analisi di sicurezza): senza container il codice non si esegue
    verifica("auto senza immagine: niente esecuzione, con il passo «costruisci»",
             not iso.pronto and "manca l'immagine" in iso.descrizione
             and "calliope motore sandbox costruisci" in iso.passo, f"{iso.descrizione} | {iso.passo}")
    iso = scegli_isolamento("docker", docker=FINTO, posix=True)
    verifica("docker esplicito senza immagine: non pronto", iso.motore == "docker"
             and not iso.pronto and "costruisci" in iso.passo, iso.descrizione)
    try:
        Sandbox(tmp / "np", isolamento=iso)
        verifica("docker non pronto: la sandbox rifiuta di partire", False)
    except ErroreSandbox as e:
        verifica("docker non pronto: la sandbox rifiuta di partire", "non posso eseguire" in str(e),
                 str(e))
    os.environ["DOCKER_FINTO_MODO"] = "permessi"
    iso = scegli_isolamento("auto", docker=FINTO, posix=True)
    verifica("Docker senza permessi: niente esecuzione, passo con il gruppo docker",
             not iso.pronto and "permessi" in iso.descrizione and "docker" in iso.passo,
             iso.descrizione)
    os.environ["DOCKER_FINTO_MODO"] = "muto"
    t0 = time.perf_counter()
    iso = scegli_isolamento("auto", docker=FINTO, posix=True, timeout=1.0)
    dt = time.perf_counter() - t0
    verifica("Docker muto: niente esecuzione entro il tempo massimo", not iso.pronto
             and "non risponde" in iso.descrizione and dt < 3, f"{dt:.1f}s")
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = scegli_isolamento("auto", docker=[str(tmp / "non-esiste")], posix=True)
    verifica("docker che non si avvia: niente esecuzione", not iso.pronto, iso.descrizione)
    iso = scegli_isolamento("auto", docker=FINTO, posix=False)
    verifica("Windows: niente esecuzione senza container, con il passo",
             not iso.pronto and "motore «processo»" in iso.passo, iso.descrizione)
    iso = scegli_isolamento("processo", docker=FINTO, posix=True)
    verifica("processo esplicito: mai docker, con l'avviso", iso.motore == "processo"
             and iso.pronto and "scelto" in iso.descrizione and "NON isola" in iso.descrizione)
    iso = scegli_isolamento("boh", docker=FINTO, posix=False)
    verifica("valore sconosciuto: come auto", not iso.pronto)

    sezione("comando docker run")
    os.environ["DOCKER_FINTO_IMMAGINI"] = img
    iso = scegli_isolamento("auto", docker=FINTO, posix=True)
    sb = Sandbox(tmp / "lavoro", tempo_s=4, memoria_mb=512, isolamento=iso, cpu=1.5)
    cmd = sb._comando_docker("calliope-sandbox-prova", "script", "ciao.py", ["a"])
    s = " ".join(cmd)
    attesi = ["run --rm -i", "--network none", "--read-only", "--cap-drop ALL",
              "--security-opt no-new-privileges", "--pull never", "--memory 512m",
              "--memory-swap 512m", f"--ulimit data={512 * 1024 * 1024}", "--pids-limit 32",
              "--cpus 1.5", "--log-driver none", "noexec", f"{img} timeout -s KILL 9 python -I -B"]
    mancano = [a for a in attesi if a not in s]
    verifica("docker run: rete, disco, capability, memoria, processi, CPU, tempo dentro",
             not mancano, str(mancano))
    i = cmd.index("--user")
    verifica("utente non root", not cmd[i + 1].startswith("0:"), cmd[i + 1])
    mounts = [cmd[j + 1] for j, a in enumerate(cmd) if a == "--mount"]
    verifica("montate solo la cartella del lavoro e _avvio.py (in sola lettura)",
             len(mounts) == 2 and mounts[0].endswith("dst=/lavoro") and "readonly" not in mounts[0]
             and mounts[1].endswith(",readonly") and "_avvio.py" in mounts[1], str(mounts))
    envs = [cmd[j + 1] for j, a in enumerate(cmd) if a == "-e"]
    verifica("solo variabili scelte, nessuna dell'host",
             all(e.split("=")[0] in {"HOME", "TMPDIR", "TEMP", "TMP", "PYTHONIOENCODING", "LANG",
                                     "NO_PROXY", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS",
                                     "MKL_NUM_THREADS"} for e in envs)
             and "--env-file" not in cmd and not any("CALLIOPE" in a for a in cmd), str(envs))
    try:
        Sandbox(tmp / "con,virgola", isolamento=iso)
        verifica("cartella con una virgola rifiutata (romperebbe --mount)", False)
    except ErroreSandbox:
        verifica("cartella con una virgola rifiutata (romperebbe --mount)", True)

    sezione("esecuzioni con il docker finto")
    sb.scrivi("ciao.py", "import os, sys\nprint('ciao', 2 + 2, sys.argv[1:], os.environ['HOME'])\n")
    r = sb.esegui("ciao.py", ["x"])
    verifica("esegue nel «container»", r["codice_uscita"] == 0 and "ciao 4 ['x']" in r["uscita"],
             r["uscita"][-200:])
    log = [json.loads(x) for x in (dfin / "comandi.jsonl").read_text().splitlines()]
    verifica("passa da docker run", any(c[:1] == ["run"] for c in log))
    sb.scrivi("mod.py", "def somma(a, b):\n    return a + b\n")
    sb.scrivi("test_mod.py", "from mod import somma\n\ndef test_uno():\n    assert somma(1, 2) == 3\n"
                             "\ndef test_due():\n    assert somma(2, 2) == 5\n")
    r = sb.test()
    verifica("test: esito dal programma", r["esito"] == {"eseguiti": 2, "falliti": 1, "errori": 0,
                                                         "saltati": 0}, str(r.get("esito")))
    for nome, codice in {"rete": "import socket\nsocket.socket()\n",
                         "processi": "import subprocess\nsubprocess.run(['x'])\n",
                         "leggi_fuori": f"open(r'{RADICE / 'CLAUDE.md'}').read()\n"}.items():
        sb.scrivi(f"{nome}.py", codice)
        r = sb.esegui(f"{nome}.py")
        verifica(f"audit hook dentro il container: {nome}", r["codice_uscita"] != 0
                 and "Bloccato dalla sandbox" in r["uscita"], ultima(r["uscita"]))
    sb.scrivi("ciclo.py", "while True:\n    pass\n")
    n_kill = sum(c[:1] == ["kill"] for c in log)
    t0 = time.perf_counter()
    r = sb.esegui("ciclo.py")
    dt = time.perf_counter() - t0
    log = [json.loads(x) for x in (dfin / "comandi.jsonl").read_text().splitlines()]
    kills = [c for c in log if c[:1] == ["kill"]]
    verifica("tempo scaduto: docker kill del container giusto", r["scaduto"] and dt < 9
             and len(kills) == n_kill + 1 and kills[-1][1].startswith("calliope-sandbox-"),
             f"{dt:.1f}s {r.get('errore')}")
    # Annullo durante l'esecuzione
    out = {}
    th = threading.Thread(target=lambda: out.update(sb.esegui("ciclo.py")))
    th.start()
    time.sleep(1.0)
    t0 = time.perf_counter()
    sb.termina()
    th.join(8)
    dt = time.perf_counter() - t0
    log = [json.loads(x) for x in (dfin / "comandi.jsonl").read_text().splitlines()]
    verifica("annullo: docker kill e fine subito", not th.is_alive() and dt < 3
             and sum(c[:1] == ["kill"] for c in log) == n_kill + 2
             and out.get("codice_uscita") not in (0, None), f"{dt:.1f}s")
    verifica("nessun «container» rimasto", not list(dfin.glob("*.pid")))
    # «Fermalo» dalla voce (06/10, analisi complessiva): termina non aspetta `docker kill` nel
    # thread di chi chiama, nemmeno con un client docker lento ad avviarsi
    vero_ferma, fermate = sb._ferma_container, []

    def ferma_lento(nome, aspetta=True):
        time.sleep(1.0)
        fermate.append(threading.current_thread() is not threading.main_thread())
        vero_ferma(nome, aspetta)
    sb._ferma_container = ferma_lento
    out = {}
    th = threading.Thread(target=lambda: out.update(sb.esegui("ciclo.py")))
    th.start()
    time.sleep(1.0)
    t0 = time.perf_counter()
    sb.termina()
    dt = time.perf_counter() - t0
    th.join(8)
    sb._ferma_container = vero_ferma
    verifica("annullo con docker lento: termina torna subito (< 50 ms), kill in un altro thread",
             dt < 0.05 and not th.is_alive() and fermate == [True]
             and out.get("codice_uscita") not in (0, None), f"{dt * 1000:.1f} ms, {fermate}")
    verifica("nessun «container» rimasto (docker lento)", not list(dfin.glob("*.pid")))

    sezione("registro delle capacità")
    cfg = Config()
    cfg.agenti_config_file = str(tmp / "nessun-dgx.yaml")
    cfg.agenti_url = "http://127.0.0.1:9"
    cfg.agenti_modello = "qwen3.6:35b"
    cfg.agenti_sandbox_motore = "processo"
    d = capacita.check_agenti(cfg)
    verifica("da terminale: l'isolamento nei dettagli e nel motivo",
             d["dettagli"].get("sandbox_motore") == "processo" and "il codice gira in un processo"
             in d["motivo"], d["motivo"])

    class Finto:
        diagnosi = {"codice": "ok"}
        isolamento = Isolamento("docker", "container Docker usa-e-getta, senza rete e con il "
                                "disco in sola lettura", True, "", img, FINTO)

        def descrizione(self):
            return "qwen3.6:35b su un server"
    d = capacita.check_agenti(cfg, Finto())
    verifica("dentro Calliope: container Docker nel motivo, immagine nei dettagli",
             d["stato"] == "attiva" and "container Docker" in d["motivo"]
             and d["dettagli"].get("sandbox_immagine") == img, d["motivo"])
    Finto.isolamento = Isolamento("docker", "container Docker non pronto: manca l'immagine della "
                                  "sandbox", False, "Per isolare il codice in un container: "
                                  "calliope motore sandbox costruisci.", img)
    d = capacita.check_agenti(cfg, Finto())
    verifica("docker esplicito non pronto: lo dice, con il passo",
             "non si esegue" in d["motivo"] and "costruisci" in d["prossimo_passo"]
             and d["dettagli"].get("sandbox_motore") == "nessuno", d["motivo"])


# ═══════════════════════════ Docker vero (DGX) ═══════════════════════════
def docker_vero():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-sandbox-"))
    iso = scegli_isolamento("docker")
    verifica("Docker e l'immagine pronti", iso.pronto and iso.motore == "docker",
             f"{iso.descrizione} {iso.passo}")
    if not iso.pronto:
        return
    sb = Sandbox(tmp / "lavoro", tempo_s=5, memoria_mb=512, isolamento=iso)
    segreto = tmp / "segreto.txt"
    segreto.write_text("segreto")

    sezione("attacchi con l'audit hook, dentro il container")
    for nome, codice in attacchi_linux(segreto, tmp / "fuori.txt", tmp).items():
        sb.scrivi(f"{nome}.py", codice)
        r = sb.esegui(f"{nome}.py")
        verifica(f"bloccato: {nome}", r["codice_uscita"] != 0 and not (tmp / "fuori.txt").exists()
                 and "segreto" not in r["uscita"].replace("segreto.txt", ""),
                 ultima(r["uscita"]))
    sb.scrivi("memoria.py", "x = bytearray(3_000_000_000)\n")
    r = sb.esegui("memoria.py")
    verifica("memoria: MemoryError", r["codice_uscita"] != 0 and "MemoryError" in r["uscita"],
             ultima(r["uscita"]))
    sb.scrivi("ciclo.py", "while True:\n    pass\n")
    t0 = time.perf_counter()
    r = sb.esegui("ciclo.py")
    dt = time.perf_counter() - t0
    rimasti = subprocess.run(["docker", "ps", "-aq", "--filter", "label=calliope.sandbox=1"],
                             capture_output=True, text=True).stdout.split()
    verifica("tempo scaduto: container fermato e rimosso", r["scaduto"] and dt < 12
             and not rimasti, f"{dt:.1f}s, rimasti {len(rimasti)}")
    sb.scrivi("ambiente.py", "import os\nprint(sorted(os.environ))\n")
    envs = sb.esegui("ambiente.py")["uscita"]
    verifica("ambiente ripulito", "CALLIOPE" not in envs and "TOKEN" not in envs.upper()
             and "SSH" not in envs, envs[:200])
    sb.scrivi("xl.py", "import openpyxl, docx, numpy\nwb = openpyxl.Workbook()\n"
                       "wb.active['A1'] = 3\nwb.save('a.xlsx')\nprint('ok', numpy.ones(3).sum())\n")
    r = sb.esegui("xl.py")
    verifica("openpyxl, python-docx e numpy nel container; il file resta nella cartella",
             "ok 3.0" in r["uscita"] and (sb.root / "a.xlsx").is_file(), ultima(r["uscita"]))
    st = (sb.root / "a.xlsx").stat()
    verifica("i file scritti sono dell'utente di Calliope", st.st_uid == os.getuid())
    sb.scrivi("mod.py", "def somma(a, b):\n    return a + b\n")
    sb.scrivi("test_mod.py", "from mod import somma\n\ndef test_uno():\n    assert somma(1, 2) == 3\n")
    r = sb.test()
    verifica("test nel container", r["passano"], str(r.get("esito")))

    sezione("senza audit hook: il confine è il container")

    def grezzo(codice: str, tempo=20) -> tuple[int, str]:
        cmd = sb._comando_docker("calliope-sandbox-grezzo", "script", "x.py", [])
        j = cmd.index(iso.immagine)
        cmd = cmd[:j + 1] + ["timeout", "-s", "KILL", str(tempo), "python", "-c", codice]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo + 15)
        return p.returncode, (p.stdout + p.stderr).strip()

    rc, out = grezzo(
        "import socket, os\n"
        "print('interfacce', sorted(os.listdir('/sys/class/net')))\n"
        "for h, p in [('1.1.1.1', 53), ('8.8.8.8', 443), ('172.17.0.1', 2375), ('10.0.0.1', 22)]:\n"
        "    s = socket.socket(); s.settimeout(2)\n"
        "    try:\n        s.connect((h, p)); print('RAGGIUNTO', h)\n"
        "    except OSError as e:\n        print('no', h, e.errno)\n"
        "try:\n    socket.getaddrinfo('example.com', 80); print('RISOLTO')\n"
        "except OSError as e:\n    print('dns no')\n")
    verifica("rete irraggiungibile: solo loopback, nessuna connessione, niente DNS",
             "interfacce ['lo']" in out and "RAGGIUNTO" not in out and "RISOLTO" not in out
             and "dns no" in out, out.replace("\n", " | "))
    rc, out = grezzo(
        "import os\n"
        "for p in ['/usr/x', '/etc/x', '/x', '/opt/calliope/_avvio.py', '/tmp/x.sh']:\n"
        "    try:\n        open(p, 'a').write('x'); print('SCRITTO', p)\n"
        "    except OSError as e:\n        print('no', p, e.errno)\n"
        "open('/lavoro/dentro.txt', 'w').write('x'); print('lavoro ok')\n"
        "os.chmod('/tmp/x.sh', 0o755)\n"
        "try:\n    os.execv('/tmp/x.sh', ['x']); print('ESEGUITO')\n"
        "except OSError as e:\n    print('noexec', e.errno)\n")
    verifica("disco in sola lettura (anche _avvio.py), /tmp senza esecuzione, /lavoro scrivibile",
             "SCRITTO /usr" not in out and "SCRITTO /etc" not in out and "SCRITTO /x" not in out
             and "SCRITTO /opt" not in out and "lavoro ok" in out and "ESEGUITO" not in out,
             out.replace("\n", " | "))
    home = str(Path.home())
    rc, out = grezzo(
        "import os\n"
        f"print('home', os.path.exists({home!r}))\n"
        "print('sock', os.path.exists('/var/run/docker.sock'), os.path.exists('/run/docker.sock'))\n"
        "print('uid', os.getuid())\n"
        "st = open('/proc/self/status').read()\n"
        "print([l for l in st.splitlines() if l.startswith(('CapEff', 'CapBnd', 'NoNewPrivs', 'Seccomp:'))])\n")
    verifica("file dell'host e socket di Docker invisibili", "home False" in out
             and "sock False False" in out, out.replace("\n", " | "))
    verifica("non root, nessuna capability, no-new-privileges, seccomp attivo",
             "uid 0" not in out and "CapEff:\\t0000000000000000" in out
             and "CapBnd:\\t0000000000000000" in out and "NoNewPrivs:\\t1" in out
             and "Seccomp:\\t2" in out, out.replace("\n", " | "))
    t0 = time.perf_counter()
    rc, out = grezzo(
        "import os, time\nn = 0\n"
        "try:\n    while True:\n        if os.fork() == 0:\n            time.sleep(20); os._exit(0)\n"
        "        n += 1\nexcept OSError as e:\n    print('fermata a', n, e.errno)\n", tempo=30)
    m = re.search(r"fermata a (\d+)", out)
    verifica("fork bomb fermata dal tetto dei processi", bool(m) and int(m.group(1)) < 40
             and time.perf_counter() - t0 < 30, out[-120:])
    rc, out = grezzo("import numpy as np\na = np.ones(400_000_000)\nprint('PRESA')\n")
    verifica("memoria oltre il tetto senza hook: rifiutata", "PRESA" not in out
             and ("MemoryError" in out or rc == 137), f"rc={rc} {out[-100:]}")

    sezione("costo d'avvio")
    sb.scrivi("vuoto.py", "print('x')\n")
    tempi_d = []
    for _ in range(10):
        r = sb.esegui("vuoto.py")
        tempi_d.append(r["secondi"])
    sp = Sandbox(tmp / "processo", tempo_s=5, memoria_mb=512)
    sp.scrivi("vuoto.py", "print('x')\n")
    tempi_p = [sp.esegui("vuoto.py")["secondi"] for _ in range(10)]
    sb.scrivi("test_t.py", "def test_a():\n    assert True\n")
    tempi_t = [sb.test("test_t.py")["secondi"] for _ in range(5)]
    md, mp = statistics.median(tempi_d), statistics.median(tempi_p)
    print(f"   docker: mediana {md:.3f} s (max {max(tempi_d):.3f}); processo: mediana {mp:.3f} s; "
          f"test nel container: mediana {statistics.median(tempi_t):.3f} s")
    verifica("costo d'avvio accettabile per i test ripetuti (< 0,6 s in più)", md - mp < 0.6,
             f"+{md - mp:.3f} s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prova della sandbox con il motore docker")
    ap.add_argument("--docker", action="store_true",
                    help="Docker vero (DGX, con l'immagine costruita) invece del docker finto")
    a = ap.parse_args()
    if a.docker:
        docker_vero()
    else:
        a_secco()
    print(f"{errori} errori" if errori else "Tutto a posto.")
    sys.exit(1 if errori else 0)
