"""La fotografia dei test dell'agente (22/10/2026, issue #223, n. 7 del § 3.1 di
docs/ricerche/2026-10-19-solidita-harness-sviluppo.md).

Un test indebolito non si vedeva: `ciclo.test_tolti` confronta i nomi solo con l'ultima tappa, e
dal 20/10 senza gli esempi. Al giro 1, prima di ogni tappa, l'agente poteva sostituire un
`assertEqual` con `assertTrue(True)` o aggiungere `skipTest`, e i test restavano verdi.

Qui, senza eseguire niente (lettura del testo: `ast` per Python, il testo per JavaScript), per
ogni file di test e per ogni test: quante asserzioni **vere**, quante **banali** (soli valori
scritti, `True or …`, dopo un `return`, sotto `if False`, dentro un try che ingoia
l'AssertionError) e se è saltato da un salto vero del runner (`self.skipTest`, `pytest.skip`,
`@unittest.skip…`, `@pytest.mark.skip…`, `test.skip`, `{ skip: true }` di `test`, `t.skip()` sul
contesto del test).

**La fotografia** (seconda revisione della PR #232) parte dai test **scritti dall'agente**: un
file entra quando l'agente lo scrive e poi i test girano. I file di partenza messi dal codice (lo
scheletro di un gioco con i test del gioco d'esempio) non ci sono finché l'agente non li
riscrive; in una **correzione** ci sono i test della versione di prima (i file iniziali).

**Cosa se ne fa.** Il confronto con la fotografia è un fatto per l'agente (nel risultato di
`esegui_test`, una nota in `scrivi_file`/`modifica_file`) e una riga neutra sulla scheda della
revisione («Test cambiati rispetto alla prima esecuzione: …»): test in meno, file tolti,
asserzioni calate, salti. Test uniti, divisi, spostati e una modifica chiesta dalla persona che
toglie una funzione cambiano i conti in buona fede: non si dicono mai a voce come un sospetto.
A voce va solo un fatto neutro, e solo quando è senza ambiguità su uno **stesso test** (stesso
nome, nello stesso file o spostato): prima controllava qualcosa e ora non controlla niente, o
prima girava e ora ha un salto vero.

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
    """Un file di test dell'agente: test_*.py, *_test.py, *.test.js, *.spec.js (come Sandbox.test
    e Agente._ha_test), fuori dalle cartelle nascoste e senza gli esempi di Calliope."""
    p = normale(percorso)
    if not p or any(x.startswith(".") for x in p.split("/")[:-1]):
        return False
    nome = p.rsplit("/", 1)[-1]
    if nome in _DI_CALLIOPE:
        return False
    return ((nome.startswith("test") and nome.endswith(".py")) or nome.endswith("_test.py")
            or nome.endswith((".test.js", ".spec.js")))


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


def _vero(n) -> bool:
    try:
        return bool(ast.literal_eval(n))
    except (ValueError, TypeError, SyntaxError):
        return False


def _sempre_vero(n) -> bool:
    """`True or f(1) == 2`: un «o» con un valore scritto vero dentro."""
    return isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) and any(
        _costante(v) and _vero(v) for v in n.values)


def _nome_chiamata(f) -> str:
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _puntato(n) -> str:
    """«pytest.mark.skip» di un decoratore o di una chiamata."""
    parti = []
    while isinstance(n, ast.Attribute):
        parti.append(n.attr)
        n = n.value
    if isinstance(n, ast.Name):
        parti.append(n.id)
    return ".".join(reversed(parti))


def _decoratore_salta(d) -> bool:
    """Un salto vero del runner: @unittest.skip/skipIf/skipUnless/expectedFailure (anche
    importati da soli), @pytest.mark.skip/skipif/xfail."""
    nome = _puntato(d.func if isinstance(d, ast.Call) else d)
    ultimo = nome.rsplit(".", 1)[-1]
    if nome.startswith("pytest.mark."):
        return ultimo in ("skip", "skipif", "xfail")
    if nome.startswith("unittest.") or "." not in nome:
        return ultimo in ("skip", "skipIf", "skipUnless", "expectedFailure")
    return False


def _decoratore_certo(d) -> bool:
    """Un salto senza condizione (terza revisione della PR #232: `@skipIf(sys.platform == …)`
    sulla DGX può girare, e a voce non si dice): @unittest.skip, @expectedFailure,
    @pytest.mark.skip, @pytest.mark.xfail senza la condizione."""
    if not _decoratore_salta(d):
        return False
    ultimo = _puntato(d.func if isinstance(d, ast.Call) else d).rsplit(".", 1)[-1]
    if ultimo in ("skipIf", "skipUnless", "skipif"):
        return False
    if ultimo == "xfail" and isinstance(d, ast.Call) and d.args:
        return False
    return True


def _chiamata_salta(n: ast.Call) -> bool:
    """`self.skipTest(…)` o `pytest.skip(…)`: non un `p.skip()` di una partita."""
    f = n.func
    if not isinstance(f, ast.Attribute) or not isinstance(f.value, ast.Name):
        return False
    return (f.attr == "skipTest" and f.value.id == "self") or (
        f.attr == "skip" and f.value.id == "pytest")


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
        self.salti_certi = 0          # fuori da ogni if: il test non gira di sicuro
        self.cond = 0

    def chiamata(self, n: ast.Call, morto: bool, molt: int):
        nome = _nome_chiamata(n.func)
        if nome.startswith("assert"):
            argomenti = list(n.args) + [k.value for k in n.keywords]
            if not argomenti:
                return
            if morto or all(_costante(a) for a in argomenti) or any(
                    _sempre_vero(a) for a in argomenti):
                self.banali += 1
            else:
                self.asserzioni += molt
        elif _chiamata_salta(n):
            self.salti += 1
            self.salti_certi += self.cond == 0

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
                self.salti_certi += self.cond == 0
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
        if isinstance(st, (ast.If, ast.While)):
            # Sotto una condizione un salto può non scattare (sulla DGX il test gira)
            self.espressione(st.test, morto, molt)
            self.cond += 1
            self.blocco(st.body, morto, molt)
            self.blocco(st.orelse, morto, molt)
            self.cond -= 1
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
        for _, valore in ast.iter_fields(st):
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
    valori scritti tante quante le voci), banali e salti; e per ogni test (per nome) le sue
    asserzioni vere, banali e se è saltato."""
    try:
        albero = ast.parse(testo)
    except (SyntaxError, ValueError):
        return None
    nomi, per_test, n_test = [], {}, 0

    def visita_funzioni(corpo, classe=""):
        nonlocal n_test
        salta_classe = False
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
                c = _Conto()
                c.blocco(n.body, False, 1)
                # «s»: un salto senza condizione (per la voce); i condizionali restano nei
                # conti per l'agente
                per_test[n.name] = {"a": c.asserzioni, "b": c.banali,
                                    "s": salta_classe or c.salti_certi > 0 or any(
                                        _decoratore_certo(d) for d in n.decorator_list)}
    visita_funzioni(albero.body)
    for n in albero.body:
        # una classe saltata intera: tutti i suoi test sono saltati
        if isinstance(n, ast.ClassDef) and any(_decoratore_certo(d) for d in n.decorator_list):
            for f in n.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name in per_test:
                    per_test[f.name]["s"] = True
    c = _Conto()
    c.blocco(albero.body, False, 1)
    return {"test": n_test, "nomi": nomi[:100], "asserzioni": c.asserzioni,
            "banali": c.banali, "skip": c.salti, "per_test": per_test}


# ─────────────────────────── JavaScript ───────────────────────────

_TEST_JS = re.compile(r"(?<![\w.$])(?:test|it)\s*\(\s*([\"'`])(.*?)(?<!\\)\1", re.S)
# I sottotest di node:test (t.test("…")) contano come test
_SOTTOTEST_JS = re.compile(r"(?<![\w.$])(?:t|ctx|context)\s*\.\s*test\s*\(\s*([\"'`])(.*?)"
                           r"(?<!\\)\1", re.S)
# I test saltati dal runner per nome: test.skip("…"), it.todo("…")
_TEST_SALTATO_JS = re.compile(r"(?<![\w.$])(?:test|it)\s*\.\s*(?:skip|todo)\s*\(\s*([\"'`])"
                              r"(.*?)(?<!\\)\1", re.S)
_DESCRIBE_SALTATO_JS = re.compile(r"(?<![\w$.])describe\s*\.\s*(?:skip|todo)\s*\(")
# Un salto senza condizione: { skip: true } o { skip: "motivo" }, non { skip: !process.env.X }
_SALTO_OPZIONE_CERTO = re.compile(r"(?<![\w$])(?:skip|todo)\s*:\s*(?:true\b|[\"'`])")
_SALTO_OPZIONE = re.compile(r"(?<![\w$])(?:skip|todo)\s*:(?!\s*(?:false\b|0\b|\"\"|''))")
_ASSERT_JS = re.compile(r"(?<![\w$.])(?:(?:t|ctx|context)\s*\.\s*)?"
                        r"(?:assert(?:\s*\.\s*\w+)?|expect)\s*\(")
_LETTERALE_JS = re.compile(r"""^(?:true|false|null|undefined|-?\d+(?:\.\d+)?|"[^"\\]*"|"""
                           r"""'[^'\\]*'|`[^`$\\]*`|\[\s*\]|\{\s*\})$""")
_SEMPRE_VERO_JS = re.compile(r"\|\|\s*(?:true|1)\s*$|^\s*(?:true|1)\s*\|\|")
_IF_FALSO_JS = re.compile(r"(?<![\w$.])if\s*\(\s*(?:false|0)\s*\)\s*\{")
_CORPO_JS = re.compile(r"(?:=>|\bfunction\b[^{]*)\s*\{")
# Il parametro della callback del test (il contesto di node:test): «(t) => {», «t => {»,
# «async (t) => {», «function (t) {»
_PARAMETRO_JS = re.compile(r"(?:\(\s*([A-Za-z_$][\w$]*)\s*\)|([A-Za-z_$][\w$]*))\s*=>\s*\{$|"
                           r"function\s*[\w$]*\s*\(\s*([A-Za-z_$][\w$]*)[^)]*\)\s*\{$")


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


def _argomenti_js(testo: str, inizio: int) -> str | None:
    """Il testo fra la parentesi aperta prima di `inizio` e quella che la pareggia."""
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


def _test_js(t: str) -> list[dict]:
    """I test del file: nome, inizio e fine del corpo della callback, il parametro (il
    contesto), se ha l'opzione di salto o il nome saltato dal runner."""
    out = []
    for saltato, regex in ((False, _TEST_JS), (False, _SOTTOTEST_JS), (True, _TEST_SALTATO_JS)):
        for m in regex.finditer(t):
            voce = {"nome": m.group(2).strip()[:120], "saltato": saltato, "inizio": None,
                    "fine": None, "param": None, "per_nome": saltato, "certo": saltato}
            c = _CORPO_JS.search(t, m.end())
            prima = t[m.end():c.end()] if c is not None else ""
            # La callback è di questo test solo se fra il nome e lei c'è al più un oggetto di
            # opzioni (niente altre chiamate di test in mezzo)
            if c is not None and not _TEST_JS.search(prima) and len(prima) < 400:
                corpo = _argomenti_js(t, c.end())
                if corpo is not None:
                    voce["inizio"], voce["fine"] = c.end(), c.end() + len(corpo)
                p = _PARAMETRO_JS.search(prima)
                if p is not None:
                    voce["param"] = p.group(1) or p.group(2) or p.group(3)
                if _SALTO_OPZIONE.search(prima):
                    voce["saltato"] = True
                    voce["certo"] = bool(_SALTO_OPZIONE_CERTO.search(prima))
            out.append(voce)
    return out


def _profondita_js(testo: str, fino: int) -> int:
    """Le graffe aperte prima di `fino`, fuori dalle stringhe."""
    prof, i, apici = 0, 0, None
    while i < fino:
        c = testo[i]
        if apici:
            if c == "\\":
                i += 2
                continue
            if c == apici:
                apici = None
        elif c in "\"'`":
            apici = c
        elif c == "{":
            prof += 1
        elif c == "}":
            prof -= 1
        i += 1
    return prof


def _zone_morte_js(t: str, test: list[dict]) -> list[tuple[int, int]]:
    """Dove le asserzioni non girano: il corpo di un test che comincia con un `return` nudo
    (`return;`: non `return carica().then(…)`, una promessa restituita), il blocco di un
    `if (false)`."""
    zone = []
    for v in test:
        if v["inizio"] is not None and re.match(r"\s*return\s*(?:;|$)", t[v["inizio"]:v["fine"]]):
            zone.append((v["inizio"], v["fine"]))
    for m in _IF_FALSO_JS.finditer(t):
        corpo = _argomenti_js(t, m.end())
        if corpo is not None:
            zone.append((m.end(), m.end() + len(corpo)))
    return zone


def misura_js(testo: str) -> dict:
    t = senza_commenti_js(testo or "")
    test = _test_js(t)
    morte = _zone_morte_js(t, test)
    asserzioni = banali = 0
    posti = []                                   # (posizione, vera?)
    for m in _ASSERT_JS.finditer(t):
        a = _argomenti_js(t, m.end())
        if a is None:
            continue
        pezzi = _pezzi(a)
        if not pezzi:
            continue
        banale = (any(i <= m.start() < f for i, f in morte)
                  or all(_LETTERALE_JS.match(p) for p in pezzi)
                  or any(_SEMPRE_VERO_JS.search(p) for p in pezzi))
        posti.append((m.start(), not banale))
        if banale:
            banali += 1
        else:
            asserzioni += 1
    salti = len(_DESCRIBE_SALTATO_JS.findall(t))
    per_test = {}
    for v in test:
        s, certo = v["saltato"], v["certo"]
        if v["param"] and v["inizio"] is not None:
            # t.skip() / t.todo() sul contesto del test, non un metodo «skip» di un gioco; senza
            # condizione solo al primo livello del corpo (non dentro un if)
            corpo = t[v["inizio"]:v["fine"]]
            for m2 in re.finditer(r"(?<![\w$.])" + re.escape(v["param"])
                                  + r"\s*\.\s*(?:skip|todo)\s*\(", corpo):
                s = True
                certo = certo or _profondita_js(corpo, m2.start()) == 0
        salti += s
        dentro = [vera for pos, vera in posti
                  if v["inizio"] is not None and v["inizio"] <= pos < v["fine"]]
        per_test[v["nome"]] = {"a": sum(dentro), "b": len(dentro) - sum(dentro),
                               "s": bool(s and certo)}
    # Un test.skip("…") non conta fra i test che girano (com'era dal 22/10)
    nomi = [v["nome"] for v in test if not v.get("per_nome")]
    return {"test": len(nomi), "nomi": nomi[:100], "asserzioni": asserzioni, "banali": banali,
            "skip": salti, "per_test": per_test}


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
            out[normale(p)] = m
    return out


def aggiorna(seg: dict, ora: dict[str, dict], iniziali: dict | None = None,
             scritti=None) -> dict:
    """La fotografia in `seg["foto_test"]`: con i file iniziali di una correzione (i test della
    versione di prima) e poi, alla loro prima esecuzione, i file di test che l'agente ha scritto
    (`scritti`; None: tutti quelli di `ora`). I file di partenza messi dal codice non entrano
    finché l'agente non li scrive. Mai sovrascritta: è il riferimento."""
    foto = seg.get("foto_test")
    if not isinstance(foto, dict):
        foto = dict(misura_file(iniziali))
        seg["foto_test"] = foto
    ammessi = None if scritti is None else {normale(x) for x in scritti}
    for p, m in ora.items():
        if p not in foto and (ammessi is None or p in ammessi):
            foto[p] = m
    return foto


def confronta(foto: dict | None, ora: dict[str, dict], solo: str | None = None) -> list[dict]:
    """I cambi rispetto alla fotografia, file per file: [{file, tolto, test_meno, nomi,
    asserzioni_meno, skip_piu, banali_piu}]. `solo`: un file soltanto (un'esecuzione parziale).
    Per l'agente e per la scheda: possono venire da una riscrittura onesta."""
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


def segnali(foto: dict | None, ora: dict[str, dict], solo: str | None = None) -> list[dict]:
    """I soli segnali senza ambiguità, su uno **stesso test**: prima controllava qualcosa e
    girava; ora non controlla niente (solo asserzioni banali) o ha un salto senza condizione.
    [{test, cosa: «banale» | «saltato»}]. Il test si abbina nello stesso file per nome (terza
    revisione della PR #232: `test_base` si ripete fra file diversi); se nel suo file non c'è più,
    vale lo spostamento solo se il nome compare in un solo altro file, dove prima non c'era. Un
    test tolto, unito o rinominato non è qui: è un cambio per l'agente e per la scheda."""
    ora = ora or {}
    out, visti = [], set()
    for p, f in (foto or {}).items():
        if solo is not None and p != solo:
            continue
        stessi = (ora.get(p) or {}).get("per_test") or {}
        for n, v in ((f or {}).get("per_test") or {}).items():
            o = stessi.get(n)
            if o is None:
                altrove = [q for q, oq in ora.items() if q != p
                           and n in ((oq or {}).get("per_test") or {})
                           and n not in (((foto or {}).get(q) or {}).get("per_test") or {})]
                if len(altrove) != 1:
                    continue
                o = ora[altrove[0]]["per_test"][n]
            if v.get("s") or int(v.get("a") or 0) <= 0:
                continue
            cosa = ("saltato" if o.get("s") else "banale" if int(o.get("a") or 0) == 0
                    and int(o.get("b") or 0) > 0 else "")
            if cosa and (n, cosa) not in visti:
                visti.add((n, cosa))
                out.append({"test": n, "cosa": cosa})
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


def _righe(cambi: list[dict]) -> list[str]:
    righe = []
    for c in cambi[:6]:
        if c["tolto"]:
            righe.append(f"{c['file']} non c'è più (aveva {c['test_meno']} test e "
                         f"{c['asserzioni_meno']} asserzioni)")
        else:
            righe.append(f"{c['file']}: " + ", ".join(_parti(c)))
    return righe


def fatto_per_agente(cambi: list[dict]) -> str:
    """Il fatto nel risultato di esegui_test (e alla consegna): file per file, con i conti."""
    if not cambi:
        return ""
    return ("Rispetto alla prima esecuzione dei test di questo lavoro: " + "; ".join(_righe(cambi))
            + ". Non controlla niente un'asserzione con soli valori scritti (assertTrue(True)), "
              "dopo un return o sotto un if False. Se hai solo diviso, unito o spostato i test, o "
              "tolto quelli di una funzione che non c'è più, dillo nel riassunto della consegna; "
              "se no, rimetti i controlli: quello che provavano non è più controllato.")


def riga_scheda(cambi) -> str:
    """La riga neutra per la scheda della revisione: "" se niente."""
    if not isinstance(cambi, list) or not cambi:
        return ""
    return "Test cambiati rispetto alla prima esecuzione: " + "; ".join(
        _righe([c for c in cambi if isinstance(c, dict)])) + "."


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
            + ". Se il codice è sbagliato correggi il codice, non il test; se il test è cambiato "
              "per una ragione, dillo nel riassunto.")


def leggibile(nome: str) -> str:
    """Il nome di un test com'è da dire (principio 5): un identificatore Python come
    `test_somma_zero` diventa «somma zero»; i nomi di JavaScript sono già frasi. "" se non resta
    niente da dire."""
    n = str(nome or "").strip()
    if re.fullmatch(r"[A-Za-z_]\w*", n):
        n = re.sub(r"^test_?", "", n).replace("_", " ").strip()
    return n[:60]


def _chi(nomi: list[str], verbo_uno: str, verbo_molti: str) -> str:
    detti = [leggibile(n) for n in nomi]
    if len(nomi) == 1:
        return (f"il test «{detti[0]}» {verbo_uno}" if detti[0] else f"un test {verbo_uno}")
    if all(detti) and len(nomi) <= 3:
        return "i test " + _e([f"«{d}»" for d in detti]) + f" {verbo_molti}"
    return f"{len(nomi)} test {verbo_molti}"


def frase_voce(segnali_test) -> str:
    """Il fatto neutro a voce (annuncio e revisione), solo per i segnali senza ambiguità su uno
    stesso test, con i nomi resi leggibili: "" se niente. Mai «indebolito»: lo dice il codice,
    giudica la persona."""
    if not isinstance(segnali_test, list):
        return ""
    banali = [s["test"] for s in segnali_test if isinstance(s, dict) and s.get("cosa") == "banale"]
    saltati = [s["test"] for s in segnali_test if isinstance(s, dict)
               and s.get("cosa") == "saltato"]
    parti = []
    if banali:
        parti.append(_chi(banali, "adesso non controlla niente", "adesso non controllano niente"))
    if saltati:
        parti.append(_chi(saltati, "adesso è saltato", "adesso sono saltati"))
    if not parti:
        return ""
    return "Sui test dell'agente: " + "; ".join(parti) + "."


def avvisi_voce(risultato) -> str:
    """Gli avvisi sui test detti a voce dal codice: i test spariti dall'ultima tappa
    (ciclo.frase_test_tolti, di prima) e il fatto neutro sugli stessi test di questo lavoro."""
    from .ciclo import frase_test_tolti
    r = risultato if isinstance(risultato, dict) else {}
    return " ".join(x for x in (frase_test_tolti(r.get("test_tolti")),
                                frase_voce(r.get("test_segnali"))) if x)
