"""La fotografia dei test dell'agente (22/10/2026, issue #223, n. 7 del § 3.1 di
docs/ricerche/2026-10-19-solidita-harness-sviluppo.md).

Un test indebolito non si vedeva: `ciclo.test_tolti` confronta i nomi solo con l'ultima tappa, e
dal 20/10 senza gli esempi. Al giro 1, prima di ogni tappa, l'agente poteva sostituire un
`assertEqual` con `assertTrue(True)` o aggiungere `skipTest`, e i test restavano verdi.

Qui, senza eseguire niente (lettura del testo: `ast` per Python, il testo per JavaScript), per
ogni file di test: quanti test, i loro nomi, quante asserzioni **vere** (un'asserzione con soli
valori scritti, `assertTrue(True)`, `assertEqual(1, 1)`, `assert.ok(true)`, non conta) e quanti
test saltati (`skipTest`, `@unittest.skip…`, `expectedFailure`, `test.skip`, `{ skip: true }`).
La fotografia si prende alla prima esecuzione dei test del lavoro, anche di un file solo (e dei
file iniziali di una correzione); un file nuovo entra alla sua prima esecuzione. A ogni
esecuzione il confronto: test in meno, asserzioni in meno, asserzioni che non controllano niente
(«banali»: soli valori scritti, dopo un `return`, sotto `if False`…) e test saltati in più sono
un fatto nel risultato dello strumento, e alla consegna nel rapporto. Il conto è per asserzioni
e per numero di test, non per nomi: un test rinominato o spostato con le stesse asserzioni non
dice niente; un ciclo su valori scritti e un parametrize contano le loro voci. A voce (dalla
prima revisione della PR #232) solo i segnali che una riscrittura onesta non spiega: test
spariti, salti veri, asserzioni banali; le asserzioni calate restano all'agente.

Mai un'eccezione: un file che non si legge (sintassi rotta) non si misura e non si confronta.
"""

from __future__ import annotations

import ast
import re

# Gli esempi di accettazione sono di Calliope, in sola lettura (agenti/accettazione.py)
_DI_CALLIOPE = ("test_accettazione.py", "accettazione.test.js")


def normale(percorso) -> str:
    """Il percorso come lo scrive la sandbox: barre in avanti, senza «./» in testa."""
    p = str(percorso or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def e_file_di_test(percorso: str) -> bool:
    """Un file di test dell'agente: test_*.py, *_test.py, *.test.js (come Sandbox.test e
    Agente._ha_test), fuori dalle cartelle nascoste e senza gli esempi di Calliope."""
    p = normale(percorso)
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


def _sempre_vero(n) -> bool:
    """`True or f(1) == 2`: un «o» con un valore scritto vero dentro."""
    return isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) and any(
        _costante(v) and _vero(v) for v in n.values)


def _vero(n) -> bool:
    try:
        return bool(ast.literal_eval(n))
    except (ValueError, TypeError, SyntaxError):
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


def _casi_parametrize(d) -> int:
    """@pytest.mark.parametrize("x", [1, 2, 3]): 3 casi; 1 per il resto."""
    if isinstance(d, ast.Call) and _nome_chiamata(d.func) == "parametrize" and len(d.args) >= 2 \
            and isinstance(d.args[1], (ast.List, ast.Tuple)):
        return max(1, len(d.args[1].elts))
    return 1


def _ingoia_asserzioni(t: ast.Try) -> bool:
    """`try: … except AssertionError: pass` (o un except nudo che non fa niente)."""
    for h in t.handlers:
        nome = _nome_chiamata(h.type) if h.type is not None else ""
        if (h.type is None or nome in ("AssertionError", "Exception", "BaseException")) \
                and all(isinstance(s, (ast.Pass, ast.Expr)) and not (
                    isinstance(s, ast.Expr) and isinstance(s.value, ast.Call))
                        for s in h.body):
            return True
    return False


class _Conto:
    def __init__(self):
        self.asserzioni = 0
        self.banali = 0
        self.salti = 0

    def chiamata(self, n: ast.Call, morto: bool, molt: int):
        nome = _nome_chiamata(n.func)
        if nome.startswith("assert"):
            argomenti = list(n.args) + [k.value for k in n.keywords]
            if not argomenti:
                return
            banale = (morto or all(_costante(a) for a in argomenti)
                      or any(_sempre_vero(a) for a in argomenti)
                      or (len(n.args) >= 2 and ast.dump(n.args[0]) == ast.dump(n.args[1])))
            if banale:
                self.banali += 1
            else:
                self.asserzioni += molt
        elif nome in ("skipTest", "skip"):
            self.salti += 1

    def espressione(self, nodo, morto: bool, molt: int):
        for x in ast.walk(nodo):
            if isinstance(x, ast.Call):
                self.chiamata(x, morto, molt)

    def blocco(self, corpo, morto: bool, molt: int):
        """Una lista di istruzioni: dopo un `return` (o un `raise`) il resto non gira."""
        fine = False
        for st in corpo:
            self.istruzione(st, morto or fine, molt)
            if isinstance(st, (ast.Return, ast.Raise)):
                fine = True

    def istruzione(self, st, morto: bool, molt: int):
        if isinstance(st, ast.Assert):
            if morto or _costante(st.test) or _sempre_vero(st.test):
                self.banali += 1
            else:
                self.asserzioni += molt
            self.espressione(st.test, morto, molt)
            return
        if isinstance(st, ast.Raise) and st.exc is not None:
            e = st.exc.func if isinstance(st.exc, ast.Call) else st.exc
            if _nome_chiamata(e) in ("SkipTest", "Skipped"):
                self.salti += 1
            return
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            m = 1
            for d in st.decorator_list:
                if _decoratore_salta(d):
                    self.salti += 1
                m *= _casi_parametrize(d)
            self.blocco(st.body, morto, molt * m)
            return
        if isinstance(st, ast.If) and _costante(st.test):
            vero = _vero(st.test)
            self.blocco(st.body, morto or not vero, molt)
            self.blocco(st.orelse, morto or vero, molt)
            return
        if isinstance(st, (ast.For, ast.AsyncFor)):
            self.espressione(st.iter, morto, molt)
            m = len(st.iter.elts) if isinstance(st.iter, (ast.List, ast.Tuple)) else 1
            self.blocco(st.body, morto, molt * max(1, m))
            self.blocco(st.orelse, morto, molt)
            return
        if isinstance(st, ast.Try):
            self.blocco(st.body, morto or _ingoia_asserzioni(st), molt)
            for h in st.handlers:
                self.blocco(h.body, morto, molt)
            self.blocco(st.orelse, morto, molt)
            self.blocco(st.finalbody, morto, molt)
            return
        for campo, valore in ast.iter_fields(st):
            if isinstance(valore, list) and valore and isinstance(valore[0], ast.stmt):
                self.blocco(valore, morto, molt)
            elif isinstance(valore, list):
                for v in valore:
                    if isinstance(v, ast.AST):
                        self.espressione(v, morto, molt)
            elif isinstance(valore, ast.AST):
                self.espressione(valore, morto, molt)


def misura_python(testo: str) -> dict | None:
    """Test (i casi di un parametrize contano uno per uno), asserzioni vere (in un ciclo su
    valori scritti tante quante le voci), asserzioni banali (soli valori scritti, `True or …`,
    lo stesso valore ai due lati, dopo un `return`, sotto `if False`, dentro un try che ingoia
    l'AssertionError) e salti."""
    try:
        albero = ast.parse(testo)
    except (SyntaxError, ValueError):
        return None
    nomi, n_test = [], 0

    def visita_funzioni(corpo, classe=""):
        nonlocal n_test
        for n in corpo:
            if isinstance(n, ast.ClassDef):
                visita_funzioni(n.body, n.name)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and n.name.startswith("test"):
                nomi.append(f"{classe}.{n.name}" if classe else n.name)
                casi = 1
                for d in n.decorator_list:
                    casi *= _casi_parametrize(d)
                n_test += casi
    visita_funzioni(albero.body)
    c = _Conto()
    c.blocco(albero.body, False, 1)
    return {"test": n_test, "nomi": nomi[:100], "asserzioni": c.asserzioni,
            "banali": c.banali, "skip": c.salti}


# ─────────────────────────── JavaScript ───────────────────────────

_TEST_JS = re.compile(r"(?<![\w.$])(?:test|it)\s*\(\s*([\"'`])(.*?)(?<!\\)\1", re.S)
# I sottotest di node:test (t.test("…")) contano come test
_SOTTOTEST_JS = re.compile(r"(?<![\w.$])(?:t|ctx|context)\s*\.\s*test\s*\(\s*([\"'`])(.*?)"
                           r"(?<!\\)\1", re.S)
# I salti veri del runner: test.skip / it.skip / describe.skip (e .todo), t.skip() / t.todo()
# nel test, e l'opzione { skip: … } o { todo: … } di una chiamata test/it/describe (seconda
# revisione della PR #232: non `mossa(stato(), { skip: true })` di un gioco)
_SALTO_JS = re.compile(r"(?<![\w$.])(?:test|it|describe)\s*\.\s*(?:skip|todo)\s*\(|"
                       r"(?<![\w$.])(?:t|ctx|context)\s*\.\s*(?:skip|todo)\s*\(")
_OPZIONI_JS = re.compile(r"(?<![\w$.])(?:(?:test|it|describe)|(?:t|ctx|context)\s*\.\s*test)"
                         r"\s*\(\s*([\"'`])(?:.*?)(?<!\\)\1\s*,\s*\{")
_SALTO_OPZIONE = re.compile(r"(?<![\w$])(?:skip|todo)\s*:\s*(?!false\b|0\b|\"\"|'')")
_ASSERT_JS = re.compile(r"(?<![\w$.])(?:assert(?:\s*\.\s*\w+)?|expect)\s*\(")
_LETTERALE_JS = re.compile(r"""^(?:true|false|null|undefined|-?\d+(?:\.\d+)?|"[^"\\]*"|"""
                           r"""'[^'\\]*'|`[^`$\\]*`|\[\s*\]|\{\s*\})$""")
_SEMPRE_VERO_JS = re.compile(r"\|\|\s*(?:true|1)\s*$|^\s*(?:true|1)\s*\|\|")
_IF_FALSO_JS = re.compile(r"(?<![\w$.])if\s*\(\s*(?:false|0)\s*\)\s*\{")
_CORPO_JS = re.compile(r"(?:=>|\bfunction\b[^{]*)\s*\{")


def senza_commenti_js(testo: str) -> str:
    """Il testo senza i commenti // e /* */, rispettando le stringhe («"a//b"» resta)."""
    out, i, n, apici = [], 0, len(testo), None
    while i < n:
        c = testo[i]
        if apici:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(testo[i + 1])
                i += 2
                continue
            if c == apici:
                apici = None
            i += 1
            continue
        if c in "\"'`":
            apici = c
            out.append(c)
            i += 1
            continue
        if testo.startswith("//", i):
            j = testo.find("\n", i)
            i = n if j < 0 else j
            continue
        if testo.startswith("/*", i):
            j = testo.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _argomenti_js(testo: str, inizio: int, chiude: str = ")") -> str | None:
    """Il testo fra le parentesi che si aprono prima di `inizio` (fino alla chiusa che le
    pareggia)."""
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


def _zone_morte_js(t: str) -> list[tuple[int, int]]:
    """Dove le asserzioni non girano: il corpo di un test che comincia con `return`, il blocco
    di un `if (false)`."""
    zone = []
    for m in list(_TEST_JS.finditer(t)) + list(_SOTTOTEST_JS.finditer(t)):
        c = _CORPO_JS.search(t, m.end())
        if c is None:
            continue
        corpo = _argomenti_js(t, c.end())
        if corpo is not None and re.match(r"\s*return\b", corpo):
            zone.append((c.end(), c.end() + len(corpo)))
    for m in _IF_FALSO_JS.finditer(t):
        corpo = _argomenti_js(t, m.end())
        if corpo is not None:
            zone.append((m.end(), m.end() + len(corpo)))
    return zone


def misura_js(testo: str) -> dict:
    t = senza_commenti_js(testo or "")
    nomi = [m.group(2).strip()[:120] for m in _TEST_JS.finditer(t)]
    nomi += [m.group(2).strip()[:120] for m in _SOTTOTEST_JS.finditer(t)]
    morte = _zone_morte_js(t)
    asserzioni = banali = 0
    for m in _ASSERT_JS.finditer(t):
        a = _argomenti_js(t, m.end())
        if a is None:
            continue
        pezzi = _pezzi(a)
        if not pezzi:
            continue
        if (any(i <= m.start() < f for i, f in morte)
                or all(_LETTERALE_JS.match(p) for p in pezzi)
                or any(_SEMPRE_VERO_JS.search(p) for p in pezzi)
                or (len(pezzi) >= 2 and pezzi[0] == pezzi[1])):
            banali += 1
        else:
            asserzioni += 1
    salti = len(_SALTO_JS.findall(t))
    for m in _OPZIONI_JS.finditer(t):
        opzioni = _argomenti_js(t, m.end())
        if opzioni is not None and _SALTO_OPZIONE.search(opzioni):
            salti += 1
    return {"test": len(nomi), "nomi": nomi[:100], "asserzioni": asserzioni,
            "banali": banali, "skip": salti}


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


def confronta(foto: dict | None, ora: dict[str, dict], solo: str | None = None) -> list[dict]:
    """I cambi che indeboliscono: [{file, tolto, test_meno, nomi, asserzioni_meno, skip_piu,
    banali_piu}]. `solo`: un file soltanto (un'esecuzione parziale)."""
    out = []
    for p, f in (foto or {}).items():
        if not isinstance(f, dict) or (solo is not None and p != solo):
            continue
        o = ora.get(p)
        if o is None:
            if int(f.get("test") or 0) or int(f.get("asserzioni") or 0):
                out.append({"file": p, "tolto": True, "test_meno": int(f.get("test") or 0),
                            "asserzioni_meno": int(f.get("asserzioni") or 0), "skip_piu": 0,
                            "banali_piu": 0, "nomi": list(f.get("nomi") or [])[:3]})
            continue
        tm = int(f.get("test") or 0) - int(o.get("test") or 0)
        am = int(f.get("asserzioni") or 0) - int(o.get("asserzioni") or 0)
        sp = int(o.get("skip") or 0) - int(f.get("skip") or 0)
        bp = int(o.get("banali") or 0) - int(f.get("banali") or 0)
        if tm > 0 or am > 0 or sp > 0 or bp > 0:
            spariti = [n for n in f.get("nomi") or [] if n not in (o.get("nomi") or [])]
            out.append({"file": p, "tolto": False, "test_meno": max(tm, 0),
                        "asserzioni_meno": max(am, 0), "skip_piu": max(sp, 0),
                        "banali_piu": max(bp, 0), "nomi": spariti[:3] if tm > 0 else []})
    return out


def _quanti(n: int, uno: str, molti: str) -> str:
    return uno if n == 1 else f"{n} {molti}"


def _e(parti: list[str]) -> str:
    return parti[0] if len(parti) == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]


def _parti(c: dict) -> list[str]:
    parti = []
    if c["test_meno"]:
        parti.append(_quanti(c["test_meno"], "un test in meno", "test in meno")
                     + (" (" + ", ".join(c["nomi"]) + ")" if c.get("nomi") else ""))
    if c["asserzioni_meno"]:
        parti.append(_quanti(c["asserzioni_meno"], "un'asserzione in meno",
                             "asserzioni in meno"))
    if c.get("banali_piu"):
        parti.append(_quanti(c["banali_piu"], "un'asserzione che non controlla niente in più",
                             "asserzioni che non controllano niente in più"))
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
            + ". Non controlla niente un'asserzione con soli valori scritti (assertTrue(True)), "
              "dopo un return o sotto un if False. Se hai solo raccolto i controlli in un ciclo "
              "o in un test parametrizzato, dillo nel riassunto della consegna; se no, rimetti i "
              "controlli: quello che provavano non è più controllato.")


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


def frase_voce(cambi, dopo_tolti: bool = False) -> str:
    """La frase a voce (annuncio e revisione), senza nomi di file: "" se niente. Solo i segnali
    che non si spiegano con una riscrittura onesta (seconda revisione della PR #232): test
    spariti senza un sostituto, salti aggiunti, asserzioni che non controllano niente. Le
    asserzioni calate (un ciclo, subTest, un parametrize) restano un fatto per l'agente.
    `dopo_tolti`: c'è già la frase dei test tolti dall'ultima tappa, che ha l'«Attenzione» e
    dice i test spariti: qui solo il resto, attaccato a lei."""
    if not isinstance(cambi, list) or not cambi:
        return ""
    c = [x for x in cambi if isinstance(x, dict)]
    t = 0 if dopo_tolti else sum(int(x.get("test_meno") or 0) for x in c)
    s = sum(int(x.get("skip_piu") or 0) for x in c)
    b = sum(int(x.get("banali_piu") or 0) for x in c)
    parti = []
    if t:
        parti.append(_quanti(t, "un test tolto", "test tolti"))
    if s:
        parti.append(_quanti(s, "un test saltato", "test saltati"))
    if b:
        parti.append(_quanti(b, "un controllo che non controlla niente",
                             "controlli che non controllano niente"))
    if not parti:
        return ""
    if dopo_tolti:
        return f"In più, da quando ha eseguito i test la prima volta: {_e(parti)}."
    return (f"Attenzione: da quando ha eseguito i test la prima volta, l'agente li ha "
            f"indeboliti: {_e(parti)}.")


def avvisi_voce(risultato) -> str:
    """Gli avvisi sui test detti a voce dal codice, con un solo «Attenzione»: i test spariti
    dall'ultima tappa (ciclo.frase_test_tolti) e quelli indeboliti dalla prima esecuzione."""
    from .ciclo import frase_test_tolti
    r = risultato if isinstance(risultato, dict) else {}
    tolti = frase_test_tolti(r.get("test_tolti"))
    deboli = frase_voce(r.get("test_indeboliti"), dopo_tolti=bool(tolti))
    return " ".join(x for x in (tolti, deboli) if x)
