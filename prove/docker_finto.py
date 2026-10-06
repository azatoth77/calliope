"""
Un `docker` FINTO per le prove della sandbox con il motore «docker» (calliope/agenti/
sandbox.py, 03/10/2026). Non crea nessun container: capisce i tre comandi che usa Calliope
e li simula sulla macchina delle prove (anche Windows).

  docker image inspect --format … <immagine>   0 se l'immagine è in DOCKER_FINTO_IMMAGINI
  docker run … <immagine> timeout -s KILL N python <argomenti>
                                               esegue python sull'host, con /lavoro e
                                               /opt/calliope/_avvio.py sostituiti dalle
                                               cartelle dei --mount, l'ambiente dei soli -e
  docker run … <immagine> timeout -s KILL N sh /opt/calliope/esegui_cs.sh <cartella> …
                                               il C# finto (_csharp, 04/10)
  docker kill <nome>                           uccide il processo del «container»

Si lancia come [sys.executable, docker_finto.py, …]. Variabili d'ambiente:
  DOCKER_FINTO_IMMAGINI  immagini presenti, separate da virgole
  DOCKER_FINTO_MODO      ok | permessi | muto
  DOCKER_FINTO_DIR       cartella per i pid dei «container» e il registro (comandi.jsonl)
  DOCKER_FINTO_AVVIO_S   secondi d'attesa prima di avviare il processo (un container lento a
                         partire: immagine fredda, disco occupato)
L'isolamento vero (rete, sola lettura, utenti) si prova solo sulla DGX:
prove/prova_sandbox_docker.py.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _dir() -> Path:
    d = Path(os.environ.get("DOCKER_FINTO_DIR") or ".")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(args):
    with open(_dir() / "comandi.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")


def _inspect(args) -> int:
    modo = os.environ.get("DOCKER_FINTO_MODO", "ok")
    if modo == "muto":
        time.sleep(60)
        return 1
    if modo == "permessi":
        print("permission denied while trying to connect to the Docker daemon socket at "
              "unix:///var/run/docker.sock", file=sys.stderr)
        return 1
    img = args[-1]
    presenti = [x for x in os.environ.get("DOCKER_FINTO_IMMAGINI", "").split(",") if x]
    if img in presenti:
        print("sha256:" + "0" * 64)
        return 0
    print(f"Error response from daemon: No such image: {img}", file=sys.stderr)
    return 1


# Opzioni di `docker run` con un valore (quelle che usa Calliope)
_CON_VALORE = {"--name", "--label", "--pull", "--log-driver", "--network", "--hostname",
               "--tmpfs", "--cap-drop", "--security-opt", "--user", "--memory",
               "--memory-swap", "--ulimit", "--pids-limit", "--cpus", "--cpu-shares",
               "--mount", "-w", "-e"}


def _run(args) -> int:
    i, mounts, env, nome = 0, {}, {}, None
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        if opt in _CON_VALORE:
            val = args[i + 1]
            if opt == "--mount":
                parti = dict(p.split("=", 1) for p in val.split(",") if "=" in p)
                mounts[parti["dst"]] = parti["src"]
            elif opt == "-e":
                k, v = val.split("=", 1)
                env[k] = v
            elif opt == "--name":
                nome = val
            i += 2
        else:
            i += 1
    immagine, resto = args[i], args[i + 1:]
    if immagine not in os.environ.get("DOCKER_FINTO_IMMAGINI", "").split(","):
        print(f"Unable to find image '{immagine}' locally", file=sys.stderr)
        return 125
    # timeout -s KILL N python … (oppure sh /opt/calliope/esegui_cs.sh … per il C#)
    assert resto[:3] == ["timeout", "-s", "KILL"] and resto[4] in ("python", "sh", "node"), resto
    lavoro = mounts["/lavoro"]
    if resto[4] == "sh":
        return _csharp(lavoro, resto[6], resto[7:], nome)

    def mappa(a: str) -> str:
        for dst, src in sorted(mounts.items(), key=lambda kv: -len(kv[0])):
            if a == dst or a.startswith(dst + "/"):
                return src + a[len(dst):]
        return a
    if resto[4] == "node":
        # I test JavaScript dei giochi (05/10): il Node della macchina delle prove, se c'è
        import shutil
        nodo = shutil.which("node")
        if not nodo:
            print("docker finto: node non c'è su questa macchina", file=sys.stderr)
            return 127
        cmd = [nodo] + [mappa(a) for a in resto[5:]]
    else:
        cmd = [sys.executable] + [mappa(a) for a in resto[5:]]
    avvio = float(os.environ.get("DOCKER_FINTO_AVVIO_S") or 0)
    if avvio > 0:
        time.sleep(avvio)
    pulito = {k: mappa(v) for k, v in env.items()}
    for k in ("SYSTEMROOT", "WINDIR", "PATH"):
        if os.environ.get(k):
            pulito.setdefault(k, os.environ[k])
    p = subprocess.Popen(cmd, cwd=lavoro, env=pulito)
    if nome:
        (_dir() / f"{nome}.pid").write_text(str(p.pid))
    try:
        code = p.wait()
    finally:
        if nome:
            try:
                (_dir() / f"{nome}.pid").unlink()
            except OSError:
                pass
    return code


def _csharp(lavoro: str, cartella: str, args: list, nome) -> int:
    """Il C# FINTO (04/10): nessun compilatore. I file .cs della cartella «si compilano» se
    nessuno contiene FINTO_ERRORE_COMPILAZIONE; il «programma» è il Python scritto in un
    commento /* FINTO_PY … */ (le prove decidono così uscita, errori, tempi e codice), e senza
    quel commento stampa quanti file ha compilato e gli argomenti. Stdin e uscite sono quelli
    del «container»."""
    base = Path(lavoro) / cartella
    files = sorted(base.glob("*.cs"))
    if not files:
        print("— nessun file .cs da compilare —", file=sys.stderr)
        return 2
    testo = "\n".join(f.read_text(encoding="utf-8") for f in files)
    if "FINTO_ERRORE_COMPILAZIONE" in testo:
        print(f"{files[0].name}(3,5): error CS1002: ; expected", file=sys.stderr)
        print("— compilazione non riuscita —", file=sys.stderr)
        return 1
    import re
    m = re.search(r"/\* FINTO_PY\n(.*?)\*/", testo, re.S)
    out = Path(lavoro) / ".tmp" / "cs"
    out.mkdir(parents=True, exist_ok=True)
    prog = out / "programma_finto.py"
    prog.write_text(m.group(1) if m else
                    f"import sys\nprint('compilati {len(files)} file C#')\n"
                    "print('argomenti:', ' '.join(sys.argv[1:]))\n", encoding="utf-8")
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "PATH") if os.environ.get(k)}
    p = subprocess.Popen([sys.executable, "-u", str(prog), *args], cwd=lavoro, env=env)
    if nome:
        (_dir() / f"{nome}.pid").write_text(str(p.pid))
    try:
        return p.wait()
    finally:
        if nome:
            try:
                (_dir() / f"{nome}.pid").unlink()
            except OSError:
                pass


def _kill(args) -> int:
    f = _dir() / f"{args[-1]}.pid"
    try:
        pid = int(f.read_text())
    except (OSError, ValueError):
        print(f"Error response from daemon: No such container: {args[-1]}", file=sys.stderr)
        return 1
    import signal
    try:
        os.kill(pid, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
    except OSError:
        pass
    print(args[-1])
    return 0


def main(argv) -> int:
    _log(argv)
    if argv[:2] == ["image", "inspect"]:
        return _inspect(argv[2:])
    if argv[:1] == ["run"]:
        code = _run(argv[1:])
        # Come Docker: un processo ucciso con SIGKILL esce con 137 (su Windows os.kill
        # chiama TerminateProcess con il numero del segnale come codice d'uscita)
        if code == -9 or (os.name == "nt" and code == 15):
            return 137
        return code
    if argv[:1] == ["kill"]:
        return _kill(argv[1:])
    print(f"docker finto: comando non previsto {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
