"""
Analisi statica del codice di un'estensione (04/10/2026), per la revisione prima
dell'approvazione. Non è un confine di sicurezza (il confine è il container senza rete e la
porta stretta): dice a chi approva quali parti sono a rischio, con la riga. Un errore di
sintassi blocca l'approvazione; il resto informa.
"""

from __future__ import annotations

import ast
import re

# Moduli che un'estensione non dovrebbe importare: nel container non funzionano (niente rete,
# niente processi, audit hook) e importarli è un segnale
MODULI = {
    "socket": "rete", "ssl": "rete", "http": "rete", "urllib": "rete", "requests": "rete",
    "httpx": "rete", "ftplib": "rete", "smtplib": "rete", "asyncio": "rete o processi",
    "subprocess": "processi", "multiprocessing": "processi", "pty": "processi",
    "ctypes": "codice nativo", "cffi": "codice nativo", "importlib": "import dinamico",
    "pickle": "dati che eseguono codice", "marshal": "dati che eseguono codice",
    "shutil": "file", "tempfile": "file", "glob": "file", "pathlib": "file",
    "base64": "testo codificato", "codecs": "testo codificato", "zlib": "testo compresso",
    "sys": "interprete", "builtins": "interprete", "inspect": "interprete",
    "threading": "thread", "signal": "processi", "resource": "limiti",
}
CHIAMATE = {
    "eval": "esegue testo come codice", "exec": "esegue testo come codice",
    "compile": "compila testo come codice", "__import__": "import dinamico",
    "open": "apre file", "getattr": "attributo calcolato", "setattr": "attributo calcolato",
    "globals": "spazio dei nomi", "vars": "spazio dei nomi", "breakpoint": "debugger",
}
_OS = {"system", "popen", "spawnl", "spawnv", "execv", "execl", "fork", "kill", "remove",
       "unlink", "rmdir", "rename", "chmod", "environ", "getenv", "putenv"}
_CODIFICATO = re.compile(r"^[A-Za-z0-9+/=]{120,}$|^(?:[0-9a-fA-F]{2}){60,}$")


def analizza(sorgenti: dict[str, str]) -> dict:
    """{file: testo} → {"sintassi": [errori], "rischi": [{file, riga, cosa, perche}]}."""
    sintassi, rischi = [], []
    for nome, testo in sorted(sorgenti.items()):
        if not nome.endswith(".py"):
            continue
        try:
            albero = ast.parse(testo, filename=nome)
        except SyntaxError as e:
            sintassi.append(f"{nome}, riga {e.lineno}: {e.msg}")
            continue
        test = nome.rsplit("/", 1)[-1].startswith("test")
        for n in ast.walk(albero):
            riga = getattr(n, "lineno", 0)
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                mods = ([a.name for a in n.names] if isinstance(n, ast.Import)
                        else [n.module or ""])
                for m in mods:
                    top = m.split(".")[0]
                    if top in MODULI and not (test and top in ("sys", "unittest")):
                        rischi.append({"file": nome, "riga": riga, "cosa": f"import {m}",
                                       "perche": MODULI[top]})
                    if top == "os":
                        rischi.append({"file": nome, "riga": riga, "cosa": "import os",
                                       "perche": "file, processi e ambiente"})
            elif isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in CHIAMATE:
                    if f.id == "open" and test:
                        continue
                    if f.id in ("getattr", "setattr") and len(n.args) > 1 and isinstance(
                            n.args[1], ast.Constant):
                        continue
                    rischi.append({"file": nome, "riga": riga, "cosa": f"{f.id}(…)",
                                   "perche": CHIAMATE[f.id]})
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                    and n.value.id == "os" and n.attr in _OS:
                rischi.append({"file": nome, "riga": riga, "cosa": f"os.{n.attr}",
                               "perche": "file, processi e ambiente"})
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and _CODIFICATO.match(n.value.strip()):
                rischi.append({"file": nome, "riga": riga, "cosa": "stringa lunga codificata",
                               "perche": "testo nascosto (base64 o esadecimale)"})
    # Un riscontro per riga e cosa
    visti, unici = set(), []
    for r in rischi:
        k = (r["file"], r["riga"], r["cosa"])
        if k not in visti:
            visti.add(k)
            unici.append(r)
    return {"sintassi": sintassi, "rischi": unici}


def in_parole(esito: dict, massimo: int = 3) -> str:
    """«nessuna parte a rischio» o «2 parti a rischio: import socket (rete), …»."""
    r = esito.get("rischi") or []
    if not r:
        return "nessuna parte a rischio"
    cose = [f"{x['cosa']} ({x['perche']})" for x in r[:massimo]]
    altre = f" e altre {len(r) - massimo}" if len(r) > massimo else ""
    n = "una parte a rischio" if len(r) == 1 else f"{len(r)} parti a rischio"
    return f"{n}: {', '.join(cose)}{altre}"
