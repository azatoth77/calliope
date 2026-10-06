"""
Avvio del codice scritto dall'agente, dentro la sandbox (02/10/2026). Non si importa: lo
lancia sandbox.py in un processo a parte, con l'interprete di base in modalità isolata:

    python -I -B -X utf8 _avvio.py <cartella> script <file.py> [argomenti…]
    python -I -B -X utf8 _avvio.py <cartella> test [<file di test>]

La prima riga dello stdin è JSON: {"nonce", "siti", "leggibili"} (cartelle dei pacchetti
da aggiungere e da poter leggere, e un segno per riconoscere l'esito dei test, che il codice
non conosce).

Prima di eseguire una sola riga del codice dell'agente si installa un **audit hook** (PEP
578) che rifiuta con PermissionError:
- la rete: ogni socket (`socket.__new__`, connect, bind, risoluzione dei nomi…) e i client
  di rete della libreria standard;
- i processi: subprocess, os.system, exec/spawn, os.startfile, `_winapi.*`, os.kill;
- le operazioni di ctypes (caricare DLL, chiamare funzioni, leggere la memoria: il modulo
  si importa perché numpy lo vuole), winreg, i sottointerpreti (non erediterebbero l'hook)
  e le estensioni native scritte nella cartella;
- la scrittura, la cancellazione, lo spostamento e il cambio di cartella fuori dalla
  cartella del lavoro;
- la lettura e l'elenco di file fuori dalla cartella del lavoro e dalle cartelle di Python
  (così segreti.yaml, la memoria, i documenti dell'utente restano fuori).

Un audit hook **non è un confine di sicurezza** (lo dice la PEP 578): è una difesa in
profondità sopra il job object di Windows (un solo processo, memoria limitata, niente
appunti né finestre: winjob.py), l'ambiente ripulito e la cartella dedicata. I limiti che
restano sono scritti in sandbox.py.
"""

import os
import sys


def main() -> int:
    work = os.path.realpath(sys.argv[1])
    modo = sys.argv[2]
    target = sys.argv[3] if len(sys.argv) > 3 else ""
    args = sys.argv[4:]
    import json
    try:
        conf = json.loads(sys.stdin.readline() or "{}")
    except ValueError:
        conf = {}
    nonce = str(conf.get("nonce") or "")
    import site
    for d in conf.get("siti") or []:
        if os.path.isdir(d):
            site.addsitedir(d)
    roots_read = [work] + [os.path.realpath(p) for p in
                           {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix,
                            *(conf.get("leggibili") or [])} if p]
    roots_write = [work]
    # La cartella del lavoro entra in sys.path solo dopo l'hook (vedi sotto): prima, un file
    # «ctypes.py» scritto dall'agente verrebbe importato al posto di quello vero, senza
    # nessun controllo. Con -I la cartella corrente non è in sys.path.
    os.chdir(work)
    # Tutto quello che serve dopo, importato prima dell'hook. ctypes si importa qui perché
    # su Windows all'import carica kernel32 (numpy e openpyxl lo vogliono): dopo, ogni
    # chiamata a funzione, DLL nuova o lettura di memoria passa da un evento bloccato
    try:
        import ctypes  # noqa: F401
    except ImportError:
        pass
    import importlib.util
    import inspect
    import io  # noqa: F401
    # mimetypes legge /etc/mime.types e simili al primo uso (openpyxl lo usa all'import): si
    # legge qui, prima dell'hook, che dopo rifiuterebbe la lettura fuori dalla cartella (sulla
    # DGX, motore «processo», openpyxl non si importava: 03/10)
    import mimetypes
    mimetypes.init()
    import runpy
    import threading
    import traceback
    import unittest

    devnull = os.path.normcase(os.path.realpath(os.devnull))
    norm_roots_r = [os.path.normcase(r).rstrip("\\/") for r in roots_read]
    norm_roots_w = [os.path.normcase(r).rstrip("\\/") for r in roots_write]
    local = threading.local()

    def inside(path, roots) -> bool:
        try:
            p = os.fsdecode(path) if isinstance(path, bytes) else os.fspath(path)
        except TypeError:
            return False
        if not p:
            return False
        full = os.path.normcase(os.path.realpath(os.path.join(work, p)))
        if full == devnull:
            return True
        for r in roots:
            if full == r or full.startswith(r + os.sep):
                return True
        return False

    write_flags = (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
                   | getattr(os, "O_TEMPORARY", 0))
    blocked_prefixes = (
        "socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
        "os.fork", "os.forkpty", "os.startfile", "os.kill", "os.killpg", "os.setuid", "os.setgid", "_winapi.", "ctypes.", "winreg.", "webbrowser.",
        "urllib.Request", "http.client.", "ftplib.", "smtplib.", "imaplib.", "poplib.",
        "nntplib.", "telnetlib.", "sys.remote_exec", "_posixsubprocess.", "resource.setrlimit",
        "resource.prlimit", "cpython.PyInterpreterState_New", "pdb.", "sys.monitoring",
        "os.chroot", "os.mkfifo", "os.mknod", "os.setns", "os.unshare", "os.pidfd_open")
    # ctypes si importa (numpy e openpyxl lo vogliono), ma ogni sua operazione pericolosa
    # (caricare una DLL, chiamare una funzione, leggere a un indirizzo) è un evento «ctypes.*»
    # bloccato qui sotto
    blocked_modules = {"winreg", "_winreg", "_interpreters", "_interpqueues",
                       "_interpchannels", "_xxsubinterpreters", "_xxinterpchannels"}
    # Lettura (e cartelle delle DLL dei pacchetti installati, come lxml per openpyxl): solo
    # nella cartella del lavoro e in quelle di Python
    read_events = {"os.listdir", "os.scandir", "glob.glob", "glob.glob/2", "os.walk",
                   "os.fwalk", "pathlib.Path.glob", "pathlib.Path.rglob",
                   "os.add_dll_directory"}
    write_events = {"os.mkdir", "os.rmdir", "os.remove", "os.rename", "os.link", "os.symlink",
                    "os.truncate", "os.utime", "os.chmod", "os.chown", "os.chflags",
                    "os.lchmod", "os.lchown", "os.chdir", "shutil.copyfile", "shutil.copymode",
                    "shutil.copystat", "shutil.copytree", "shutil.move", "shutil.rmtree",
                    "shutil.chown", "shutil.make_archive", "shutil.unpack_archive",
                    "tempfile.mkstemp", "tempfile.mkdtemp", "sqlite3.connect",
                    "sqlite3.connect/handle", "os.listxattr", "os.setxattr", "os.removexattr"}

    def deny(event, imp: bool = False):
        # Per gli import un ImportError: i pacchetti che provano un modulo facoltativo
        # («try: import numpy») vanno avanti senza
        raise (ImportError if imp else PermissionError)(
            f"Bloccato dalla sandbox di Calliope: {event}")

    def paths(args):
        for a in args:
            if isinstance(a, (str, bytes)) or hasattr(a, "__fspath__"):
                yield a

    def check(event, args):
        if event == "open":
            path, mode, flags = (list(args) + [None, None, None])[:3]
            if path is None or isinstance(path, int):
                return
            write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                mode is None and isinstance(flags, int) and flags & write_flags)
            if not inside(path, norm_roots_w if write else norm_roots_r):
                deny(f"open {'in scrittura' if write else 'in lettura'} fuori dalla cartella")
            return
        if event == "import":
            name = str(args[0] or "")
            if name.split(".")[0] in blocked_modules or name == "concurrent.interpreters":
                deny(f"import {name}", imp=True)
            filename = args[1] if len(args) > 1 else None
            if filename:
                if not inside(filename, norm_roots_r):
                    deny(f"import {name} da fuori", imp=True)
                fn = os.fsdecode(filename).lower() if isinstance(filename, bytes) else \
                    str(filename).lower()
                if inside(filename, norm_roots_w) and fn.endswith((".pyd", ".dll", ".so")):
                    deny(f"estensione nativa {name}", imp=True)
            return
        if event in read_events:
            for p in paths(args):
                if not inside(p, norm_roots_r):
                    deny(f"{event} fuori dalla cartella")
            return
        if event in write_events:
            for p in paths(args):
                if isinstance(p, str) and p == ":memory:":
                    continue
                if not inside(p, norm_roots_w):
                    deny(f"{event} fuori dalla cartella")
            return
        if event.startswith(blocked_prefixes):
            deny(event)

    def hook(event, args):
        if getattr(local, "busy", False):
            return
        local.busy = True
        try:
            check(event, args)
        finally:
            local.busy = False

    sys.addaudithook(hook)
    sys.path.insert(0, work)

    if modo == "script":
        sys.argv = [target] + list(args)
        try:
            runpy.run_path(os.path.join(work, target), run_name="__main__")
        except SystemExit as e:
            code = e.code
            if code is None:
                return 0
            if isinstance(code, int):
                return code
            print(code, file=sys.stderr)
            return 1
        except BaseException:   # noqa: BLE001 — il traceback è l'uscita che serve all'agente
            traceback.print_exc()
            return 1
        return 0

    # Test: unittest, più le funzioni test_* in stile pytest (senza fixture)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    errors_import = 0
    if target:
        files = [target]
    else:
        files = []
        for base, dirs, names in os.walk(work):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
            for n in sorted(names):
                if n.endswith(".py") and (n.startswith("test") or n.endswith("_test.py")):
                    files.append(os.path.relpath(os.path.join(base, n), work))
    for rel in files:
        modname = os.path.splitext(rel)[0].replace(os.sep, ".").replace("/", ".")
        try:
            spec = importlib.util.spec_from_file_location(modname, os.path.join(work, rel))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
        except BaseException:   # noqa: BLE001
            errors_import += 1
            print(f"ERRORE nell'import di {rel}:")
            traceback.print_exc(file=sys.stdout)
            continue
        suite.addTests(loader.loadTestsFromModule(mod))
        for name, obj in list(vars(mod).items()):
            if (name.startswith("test") and inspect.isfunction(obj)
                    and obj.__module__ == mod.__name__):
                params = [p for p in inspect.signature(obj).parameters.values()
                          if p.default is p.empty]
                if not params:
                    suite.addTest(unittest.FunctionTestCase(obj, description=f"{rel}::{name}"))
    res = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    sys.stdout.flush()
    esito = {"eseguiti": res.testsRun, "falliti": len(res.failures),
             "errori": len(res.errors) + errors_import, "saltati": len(res.skipped)}
    print(f"\n{nonce} {json.dumps(esito)}", flush=True)
    return 0 if res.wasSuccessful() and not errors_import else 1


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:   # noqa: BLE001
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code if isinstance(code, int) else 1)
