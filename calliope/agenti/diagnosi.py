"""
Dove e perché: l'errore di un controllo detto in breve all'agente (11/10/2026,
docs/aree/agenti-estensioni.md, «Ogni controllo dice dove e perché»).

Caso vero della DGX (11/10): sviluppando un gioco, qwen3.6 ha girato a vuoto per 45 minuti.
La prova di fumo diceva solo «tocco (click): Error: Devi inserire da 1 a 4 giocatori», senza
elemento, riga né tocchi: l'agente ha riscritto gioco.js intero nove volte con ipotesi
sbagliate. Il registro del lavoro diceva «21 test su 22 passano», senza l'errore.

Qui si legge l'uscita di un controllo (test Python con unittest, test JavaScript e prova di
fumo, compilazione ed esecuzione del C#, un programma Python che si ferma) e se ne ricava
l'elenco dei fallimenti: quale test, l'errore (l'asserzione con i valori) e dove (file:riga
nel codice dell'agente, mai nella libreria standard). Il testo è corto apposta: va nel
risultato di esegui_test prima dell'uscita intera (che il contesto accorcia), nel registro
del lavoro, nel diario e nella spinta quando l'agente gira a vuoto (ripetizioni.spinta).
"""

from __future__ import annotations

import re

MAX_FALLIMENTI = 4          # quanti fallimenti si dicono (gli altri si contano)
MAX_ERRORE = 360           # caratteri del messaggio d'errore di un fallimento
MAX_TESTO = 900             # caratteri del testo intero

# Python: un blocco di unittest («FAIL: test_x (mod.Classe.test_x)»), il traceback, un frame
_BLOCCO_PY = re.compile(r"^(FAIL|ERROR): (.+?)\s*$", re.M)
_SEPARATORE = re.compile(r"^(?:=|-){20,}\s*$", re.M)
_FRAME_PY = re.compile(r'^\s*File "([^"]+)", line (\d+)(?:, in (\S+))?', re.M)
_ECCEZIONE = re.compile(r"^((?:[A-Za-z_][\w.]*\.)?[A-Z]\w*(?:Error|Exception|Exit|Interrupt|"
                        r"Warning)|AssertionError|StopIteration|KeyboardInterrupt)(?::\s?(.*))?$")
_IMPORT_PY = re.compile(r"^ERRORE nell'import di (\S+?):?\s*$", re.M)
_TRACEBACK = "Traceback (most recent call last):"
# Le cartelle della libreria e del runner: i frame lì dentro non dicono dove correggere
_NON_SUOI = re.compile(r"[\\/](?:unittest|importlib|lib[\\/]python[\d.]*|Lib|site-packages|"
                       r"dist-packages|node:internal|node_modules)[\\/]|_avvio\.py$|^<frozen|"
                       r"^node:|calliope_estensione\.py$|_ospite\.py$", re.I)
# JavaScript (test_js.mjs): una riga per test fallito, la sintassi, la prova di fumo
_FALLITO_JS = re.compile(r"^FALLITO (.+)$", re.M)
_SINTASSI_JS = re.compile(r"^errore di sintassi in (.+)$", re.M)
# C#: «Program.cs(12,5): error CS1002: ; expected» e l'eccezione non gestita con lo stack
_ERRORE_CS = re.compile(r"^(?:.*[\\/])?([^\\/\s(]+\.cs)\((\d+),(\d+)\): error (CS\d+): (.+)$",
                        re.M)
_ECCEZIONE_CS = re.compile(r"^Unhandled exception\. ([\w.]+(?:Exception|Error))?:?\s*(.*)$",
                           re.M)
_FRAME_CS = re.compile(r"^\s*at (.+?) in (?:.*[\\/])?([^\\/]+\.cs):line (\d+)", re.M)


def _breve(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _file(percorso: str) -> str:
    """Il percorso come lo vede l'agente: relativo alla cartella del lavoro (/lavoro nel
    container), altrimenti il nome del file."""
    p = str(percorso).replace("\\", "/")
    for radice in ("/lavoro/",):
        if radice in p:
            return p.split(radice, 1)[1]
    return p.rsplit("/", 1)[-1]


def _frame_suoi(testo: str) -> list[str]:
    """«file:riga» dei frame di un traceback Python nel codice dell'agente, dal più esterno."""
    out = []
    for m in _FRAME_PY.finditer(testo):
        if _NON_SUOI.search(m.group(1).replace("\\", "/")):
            continue
        out.append(f"{_file(m.group(1))}:{m.group(2)}")
    return out


def _dove_py(testo: str) -> str:
    """Il punto da guardare: il frame più interno nel codice dell'agente e, se è un altro file,
    il test che l'ha chiamato («estensione.py:30 ← test_estensione.py:12»)."""
    fr = _frame_suoi(testo)
    if not fr:
        return ""
    interno, esterno = fr[-1], fr[0]
    if esterno.split(":")[0] != interno.split(":")[0]:
        return f"{interno} ← {esterno}"
    return interno


def _eccezione_py(testo: str) -> str:
    """L'ultima riga d'eccezione di un traceback («AssertionError: 2 != 3»), con le righe che
    la seguono se l'asserzione è su più righe (assertEqual di liste e dizionari)."""
    righe = [r.rstrip() for r in testo.splitlines()]
    for i in range(len(righe) - 1, -1, -1):
        m = _ECCEZIONE.match(righe[i].strip())
        if m and not righe[i].startswith(" "):
            # Le righe sotto (assertEqual di liste e dizionari), senza il confronto riga per
            # riga di difflib («- …», «+ …», «? ^»), che ripete i valori
            resto = [r.strip() for r in righe[i + 1:i + 6] if r.strip()
                     and not _SEPARATORE.match(r) and not re.match(r"[-+?] ", r)][:3]
            return " ".join([righe[i].strip()] + resto)
    return ""


def _python(uscita: str) -> list[dict]:
    out = []
    blocchi = list(_BLOCCO_PY.finditer(uscita))
    for i, m in enumerate(blocchi):
        fine = blocchi[i + 1].start() if i + 1 < len(blocchi) else len(uscita)
        corpo = uscita[m.end():fine]
        # Il blocco finisce al separatore dopo il traceback («----…» e «Ran N tests»)
        k = corpo.find("\nRan ")
        if k >= 0:
            corpo = corpo[:k]
        nome = re.sub(r"\s*\(.*\)$", "", m.group(2)).strip() or m.group(2)
        if "FunctionTestCase" in m.group(2):
            # «unittest.case.FunctionTestCase (test_d)» e sotto «test_x.py::test_d»
            sotto = re.search(r"^\s*(\S+::\S+)\s*$", corpo, re.M)
            nome = sotto.group(1) if sotto else m.group(2).rsplit("(", 1)[-1].rstrip(")")
        out.append({"test": nome, "errore": _eccezione_py(corpo) or m.group(1),
                    "dove": _dove_py(corpo)})
    for m in _IMPORT_PY.finditer(uscita):
        corpo = uscita[m.end():m.end() + 4000]
        k = corpo.find("\n\n")
        corpo = corpo if k < 0 else corpo[:k]
        out.append({"test": f"import di {m.group(1)}", "errore": _eccezione_py(corpo),
                    "dove": _dove_py(corpo)})
    if not out and _TRACEBACK in uscita:
        # Un programma (esegui_python) o il runner che si ferma: l'ultimo traceback
        corpo = uscita[uscita.rfind(_TRACEBACK):]
        out.append({"test": "", "errore": _eccezione_py(corpo), "dove": _dove_py(corpo)})
    return out


def _javascript(uscita: str) -> list[dict]:
    out = []
    for m in _SINTASSI_JS.finditer(uscita):
        out.append({"test": "sintassi", "errore": m.group(1).strip(), "dove": ""})
    for m in _FALLITO_JS.finditer(uscita):
        riga = m.group(1).strip()
        nome, _, errore = riga.partition(": ")
        errore = errore.split(" — la prova carica", 1)[0]     # la spiegazione della prova
        dove = ""
        d = re.search(r"\[in ([^\]]+)\]", errore)
        if d:
            dove = d.group(1).strip()
        out.append({"test": nome.strip(), "errore": errore.strip(), "dove": dove})
    return out


def _csharp(uscita: str) -> list[dict]:
    out = [{"test": "compilazione", "errore": f"{m.group(4)}: {m.group(5).strip()}",
            "dove": f"{m.group(1)}:{m.group(2)}"} for m in _ERRORE_CS.finditer(uscita)]
    m = _ECCEZIONE_CS.search(uscita)
    if m:
        frame = _FRAME_CS.search(uscita, m.end())
        out.append({"test": "", "errore": " ".join(x for x in m.groups() if x).strip(),
                    "dove": f"{frame.group(2)}:{frame.group(3)}" if frame else ""})
    return out


def fallimenti(uscita: str) -> list[dict]:
    """[{test, errore, dove}] dall'uscita di un controllo; vuoto se non si riconosce niente."""
    u = str(uscita or "")
    out = _python(u) + _javascript(u) + _csharp(u)
    visti, unici = set(), []
    for f in out:
        k = (f["test"], f["errore"], f["dove"])
        if k not in visti and (f["errore"] or f["dove"]):
            visti.add(k)
            unici.append(f)
    return unici


def riga(f: dict, max_errore: int = MAX_ERRORE) -> str:
    """Un fallimento in una riga: «test_a: AssertionError: 2 != 3 (in test_x.py:4)»."""
    dove = f.get("dove") or ""
    # La prova di fumo lo dice dentro il messaggio: si toglie da lì e va in fondo, così il
    # taglio della riga non lo perde mai
    testo = _breve(str(f.get("errore") or "").replace(f" [in {dove}]", ""), max_errore)
    return ((f"{f['test']}: " if f.get("test") else "") + testo
            + (f" (in {dove})" if dove else ""))


def testo(fall: list[dict], max_caratteri: int = MAX_TESTO) -> str:
    """I fallimenti detti per l'agente, uno per riga, al più MAX_FALLIMENTI."""
    if not fall:
        return ""
    righe = [riga(f) for f in fall[:MAX_FALLIMENTI]]
    if len(fall) > MAX_FALLIMENTI:
        righe.append(f"…e altri {len(fall) - MAX_FALLIMENTI}")
    t = "\n".join(righe)
    return t if len(t) <= max_caratteri else t[: max_caratteri - 1].rstrip() + "…"


def da_uscita(uscita: str, max_caratteri: int = MAX_TESTO) -> str:
    return testo(fallimenti(uscita), max_caratteri)


def ultimo(fall: list[dict]) -> dict | None:
    """L'errore da ricordare per la spinta: il primo fallimento con un punto preciso."""
    for f in fall:
        if f.get("dove") or re.search(r"\[in [^\]]+\]", f.get("errore") or ""):
            return f
    return fall[0] if fall else None
