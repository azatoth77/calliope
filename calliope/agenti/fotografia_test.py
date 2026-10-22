"""La fotografia dei test dell'agente (22/10/2026, issue #223, n. 7 del § 3.1 di
docs/ricerche/2026-10-19-solidita-harness-sviluppo.md).

Un test indebolito non si vedeva: `ciclo.test_tolti` confronta i nomi solo con l'ultima tappa, e
dal 20/10 senza gli esempi. Al giro 1, prima di ogni tappa, l'agente poteva sostituire un
`assertEqual` con `assertTrue(True)` o aggiungere `skipTest`, e i test restavano verdi.

Qui, senza eseguire niente (lettura del testo: `ast` per Python, il testo per JavaScript), per
ogni file di test: quanti test, i loro nomi, quante asserzioni **vere** (un'asserzione con soli
valori scritti, `assertTrue(True)`, `assertEqual(1, 1)`, `assert.ok(true)`, non conta) e quanti
test saltati (`skipTest`, `@unittest.skip…`, `expectedFailure`, `test.skip`, `{ skip: true }`).
La fotografia si prende alla prima esecuzione dei test del lavoro (e dei file iniziali di una
correzione); un file nuovo entra alla sua prima esecuzione. A ogni esecuzione il confronto: test
in meno, asserzioni in meno e test saltati in più sono un fatto nel risultato dello strumento,
e alla consegna nel rapporto. Il conto è per asserzioni e per numero di test, non per nomi: un
test rinominato o spostato con le stesse asserzioni non dice niente.

Mai un'eccezione: un file che non si legge (sintassi rotta) non si misura e non si confronta.
"""

from __future__ import annotations

import ast
import re

# Gli esempi di accettazione sono di Calliope, in sola lettura (agenti/accettazione.py)
_DI_CALLIOPE = ("test_accettazione.py", "accettazione.test.js")


def e_file_di_test(percorso: str) -> bool:
    """Un file di test dell'agente: test_*.py, *_test.py, *.test.js (come Sandbox.test e
    Agente._ha_test), fuori dalle cartelle nascoste e senza gli esempi di Calliope."""
    p = str(percorso or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or any(x.startswith(".") for x in p.split("/")[:-1]):
        return False
    nome = p.rsplit("/", 1)[-1]
    if nome in _DI_CALLIOPE:
        return False
    return ((nome.startswith("test") and nome.endswith(".py")) or nome.endswith("_test.py")
            or nome.endswith(".test.js"))


# ─────────────────────────── Python ───────────────────────────

def _costante(n) -> bool:
    """Un valore scritto: 1, "a", True, None, (1, 2), -3, {"a": 1}."""
    if isinstance(n, ast.Constant):
        return True
    if isinstance(n, ast.UnaryOp):
        return _costante(n.operand)
    if isinstance(n, (ast.Tuple, ast.List, ast.Set)):
        return all(_costante(x) for x in n.elts)
    if isinstance(n, ast.Dict):
        return all(k is None or _costante(k) for k in n.keys) and all(
            _costante(v) for v in n.values)
    return False


def _nome_chiamata(f) -> str:
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _decoratore_salta(d) -> bool:
    """@unittest.skip(…), @skipIf, @skipUnless, @pytest.mark.skip, @expectedFailure."""
    ultimo = _nome_chiamata(d.func if isinstance(d, ast.Call) else d)
    return ultimo.lower().startswith("skip") or ultimo in ("expectedFailure", "xfail")


def misura_python(testo: str) -> dict | None:
    try:
        albero = ast.parse(testo)
    except (SyntaxError, ValueError):
        return None
    nomi, asserzioni, salti = [], 0, 0

    def visita_funzioni(corpo, classe=""):
        nonlocal salti
        for n in corpo:
            if isinstance(n, ast.ClassDef):
                if any(_decoratore_salta(d) for d in n.decorator_list):
                    salti += 1
                visita_funzioni(n.body, n.name)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and n.name.startswith("test"):
                nomi.append(f"{classe}.{n.name}" if classe else n.name)
                if any(_decoratore_salta(d) for d in n.decorator_list):
                    salti += 1
    visita_funzioni(albero.body)
    # Un @unittest.skip(…) è anche una chiamata nell'albero: contato già come decoratore
    decoratori = {id(d) for n in ast.walk(albero)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  for d in n.decorator_list}
    for n in ast.walk(albero):
        if isinstance(n, ast.Assert):
            asserzioni += not _costante(n.test)
        elif isinstance(n, ast.Call) and id(n) not in decoratori:
            nome = _nome_chiamata(n.func)
            if nome.startswith("assert"):
                argomenti = list(n.args) + [k.value for k in n.keywords]
                asserzioni += bool(argomenti) and not all(_costante(a) for a in argomenti)
            elif nome in ("skipTest", "skip"):
                salti += 1
        elif isinstance(n, ast.Raise) and n.exc is not None:
            e = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
            if _nome_chiamata(e) in ("SkipTest", "Skipped"):
                salti += 1
    return {"test": len(nomi), "nomi": nomi[:100], "asserzioni": asserzioni, "skip": salti}


# ─────────────────────────── JavaScript ───────────────────────────

_COMMENTI_JS = re.compile(r"/\*.*?\*/|(?<![:\"'\\])//[^\n]*", re.S)
_TEST_JS = re.compile(r"(?<![\w.$])(?:test|it)\s*\(\s*([\"'`])(.*?)(?<!\\)\1", re.S)
_SALTO_JS = re.compile(r"(?<![\w$])(?:test|it|describe)\s*\.\s*(?:skip|todo)\s*\(|"
                       r"(?<![\w$])\w+\s*\.\s*skip\s*\(|(?<![\w$])(?:skip|todo)\s*:\s*"
                       r"(?!false\b|0\b)")
_ASSERT_JS = re.compile(r"(?<![\w$.])(?:assert(?:\s*\.\s*\w+)?|expect)\s*\(")
_LETTERALE_JS = re.compile(r"""^(?:true|false|null|undefined|-?\d+(?:\.\d+)?|"[^"\\]*"|"""
                           r"""'[^'\\]*'|`[^`$\\]*`|\[\s*\]|\{\s*\})$""")


def _argomenti_js(testo: str, inizio: int) -> str | None:
    """Il testo fra le parentesi della chiamata che si apre in `inizio` (dopo «(»)."""
    prof, i, apici = 1, inizio, None
    while i < len(testo):
        c = testo[i]
        if apici:
            if c == "\\":
                i += 2
                continue
            if c == apici:
                apici = None
        elif c in "\"'`":
            apici = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
            if prof == 0:
                return testo[inizio:i]
        i += 1
    return None


def _pezzi(argomenti: str) -> list[str]:
    out, prof, apici, cur = [], 0, None, ""
    for c in argomenti:
        if apici:
            cur += c
            if c == apici:
                apici = None
            continue
        if c in "\"'`":
            apici = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
        elif c == "," and prof == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += c
    if cur.strip():
        out.append(cur.strip())
    return out


def misura_js(testo: str) -> dict:
    t = _COMMENTI_JS.sub("", testo or "")
    nomi = [m.group(2).strip()[:120] for m in _TEST_JS.finditer(t)]
    asserzioni = 0
    for m in _ASSERT_JS.finditer(t):
        a = _argomenti_js(t, m.end())
        if a is None:
            continue
        pezzi = _pezzi(a)
        asserzioni += bool(pezzi) and not all(_LETTERALE_JS.match(p) for p in pezzi)
    return {"test": len(nomi), "nomi": nomi[:100], "asserzioni": asserzioni,
            "skip": len(_SALTO_JS.findall(t))}


def misura(percorso: str, testo: str | None) -> dict | None:
    """La misura di un file di test, o None (non è un test, non si legge)."""
    if testo is None or not e_file_di_test(percorso):
        return None
    try:
        if str(percorso).endswith(".js"):
            return misura_js(testo)
        return misura_python(testo)
    except Exception:  # noqa: BLE001 — una misura non ferma il lavoro
        return None


def misura_cartella(sandbox) -> dict[str, dict]:
    """{percorso: misura} dei file di test dell'agente nella cartella; mai un'eccezione."""
    out = {}
    try:
        sola = set(getattr(sandbox, "sola_lettura", None) or ())
        for f in sandbox.elenca():
            p = f["percorso"]
            if p in sola or not e_file_di_test(p):
                continue
            try:
                m = misura(p, sandbox.leggi(p, 2_000_000))
            except Exception:  # noqa: BLE001
                m = None
            if m is not None:
                out[p] = m
    except Exception:  # noqa: BLE001
        pass
    return out


def misura_file(file: dict | None) -> dict[str, dict]:
    """La misura dei file iniziali di un lavoro ({percorso: testo})."""
    out = {}
    for p, testo in (file or {}).items():
        if isinstance(testo, bytes):
            testo = testo.decode("utf-8", "replace")
        m = misura(p, testo) if isinstance(testo, str) else None
        if m is not None:
            out[p] = m
    return out


def aggiorna(seg: dict, ora: dict[str, dict], iniziali: dict | None = None) -> dict:
    """La fotografia in `seg["foto_test"]`: alla prima esecuzione, con i file iniziali del lavoro
    (una correzione parte dai test di prima); un file nuovo entra quando compare. Mai
    sovrascritta: è il riferimento."""
    foto = seg.get("foto_test")
    if not isinstance(foto, dict):
        foto = {}
        for p, m in misura_file(iniziali).items():
            foto[p] = m
        seg["foto_test"] = foto
    for p, m in ora.items():
        if p not in foto:
            foto[p] = m
    return foto


def confronta(foto: dict | None, ora: dict[str, dict]) -> list[dict]:
    """I cambi che indeboliscono: [{file, test_meno, nomi, asserzioni_meno, skip_piu,
    tolto}]."""
    out = []
    for p, f in (foto or {}).items():
        if not isinstance(f, dict):
            continue
        o = ora.get(p)
        if o is None:
            if int(f.get("test") or 0) or int(f.get("asserzioni") or 0):
                out.append({"file": p, "tolto": True, "test_meno": int(f.get("test") or 0),
                            "asserzioni_meno": int(f.get("asserzioni") or 0), "skip_piu": 0,
                            "nomi": list(f.get("nomi") or [])[:3]})
            continue
        tm = int(f.get("test") or 0) - int(o.get("test") or 0)
        am = int(f.get("asserzioni") or 0) - int(o.get("asserzioni") or 0)
        sp = int(o.get("skip") or 0) - int(f.get("skip") or 0)
        if tm > 0 or am > 0 or sp > 0:
            spariti = [n for n in f.get("nomi") or [] if n not in (o.get("nomi") or [])]
            out.append({"file": p, "tolto": False, "test_meno": max(tm, 0),
                        "asserzioni_meno": max(am, 0), "skip_piu": max(sp, 0),
                        "nomi": spariti[:3] if tm > 0 else []})
    return out


def _quanti(n: int, uno: str, molti: str) -> str:
    return uno if n == 1 else f"{n} {molti}"


def _parti(c: dict) -> list[str]:
    parti = []
    if c["test_meno"]:
        parti.append(_quanti(c["test_meno"], "un test in meno", "test in meno")
                     + (" (" + ", ".join(c["nomi"]) + ")" if c.get("nomi") else ""))
    if c["asserzioni_meno"]:
        parti.append(_quanti(c["asserzioni_meno"], "un'asserzione in meno",
                             "asserzioni in meno"))
    if c["skip_piu"]:
        parti.append(_quanti(c["skip_piu"], "un test saltato in più", "test saltati in più"))
    return parti


def fatto_per_agente(cambi: list[dict]) -> str:
    """Il fatto nel risultato di esegui_test (e alla consegna): file per file, con i conti."""
    if not cambi:
        return ""
    righe = []
    for c in cambi[:6]:
        if c["tolto"]:
            righe.append(f"{c['file']} non c'è più (aveva {c['test_meno']} test e "
                         f"{c['asserzioni_meno']} asserzioni)")
        else:
            righe.append(f"{c['file']}: " + ", ".join(_parti(c)))
    return ("Rispetto alla prima esecuzione dei test di questo lavoro: " + "; ".join(righe)
            + ". Un'asserzione con soli valori scritti (assertTrue(True)) non conta. Quello che "
              "controllavano non è più controllato: rimetti i controlli, o nel riassunto della "
              "consegna di' perché li hai cambiati.")


def nota_scrittura(percorso: str, prima: str | None, dopo: str | None) -> str:
    """La nota nel risultato di scrivi_file o modifica_file su un file di test che toglie
    test o asserzioni o aggiunge un salto, rispetto a com'era subito prima. "" altrimenti."""
    a, b = misura(percorso, prima), misura(percorso, dopo)
    if a is None or b is None:
        return ""
    cambi = confronta({percorso: a}, {percorso: b})
    if not cambi:
        return ""
    return (f"Con questa scrittura {percorso} ha " + ", ".join(_parti(cambi[0]))
            + ". Un test più debole non prova niente: se il codice è sbagliato correggi il "
              "codice, non il test.")


def frase_voce(cambi) -> str:
    """La frase a voce alla consegna, senza nomi di file: "" se niente."""
    if not isinstance(cambi, list) or not cambi:
        return ""
    t = sum(int(c.get("test_meno") or 0) for c in cambi if isinstance(c, dict))
    a = sum(int(c.get("asserzioni_meno") or 0) for c in cambi if isinstance(c, dict))
    s = sum(int(c.get("skip_piu") or 0) for c in cambi if isinstance(c, dict))
    parti = []
    if t:
        parti.append(_quanti(t, "un test in meno", "test in meno"))
    if a:
        parti.append(_quanti(a, "un controllo in meno", "controlli in meno"))
    if s:
        parti.append(_quanti(s, "un test saltato", "test saltati"))
    if not parti:
        return ""
    elenco = parti[0] if len(parti) == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]
    return f"Attenzione: dalla prima prova l'agente ha indebolito i suoi test: {elenco}."
