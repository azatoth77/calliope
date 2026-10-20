"""Il revisore a contesto pulito nel ciclo dell'agente (20/10/2026, issue #190; banco #182,
ricerca docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.6 e § 4, passo 6 del § 5;
area agenti-estensioni).

Nei giri a vuoto del 18/10 (#174) il giudizio «è il test o il codice?» lo dava l'agente su sé
stesso, o la persona alla tappa. Il banco del 19/10 (qwen3.6-35B-A3B, `prove/manuali/
banco_revisore.py`) ha misurato una passata dello **stesso modello** a **contesto pulito**: 24
volte su 25 il giudizio giusto su test, codice o consegna; male sulle etichette di processo
(«cambia strada», «chiedi alla persona»). Decisione di chi amministra del 20/10: il revisore si
costruisce con il menu ridotto `test_sbagliato` / `codice_sbagliato` / `consegna`, più una
`domanda` facoltativa per la persona; il giro in tondo lo decide il codice. La sera del 20/10
(da #197) gli esempi di accettazione non bloccano più da soli: un esempio rosso, quando il
lavoro vorrebbe consegnare o chiudersi, va al revisore, che dice se è sbagliato l'esempio o il
codice (gli esempi del tris scritti a mente erano sbagliati 11 su 11).

**Il pacchetto** (l'unica cosa che il revisore vede, lo stesso del banco): il contratto, i
requisiti, i file senza commenti (le righe al loro posto), l'esito vero dei test con i
fallimenti in breve, il registro dei tentativi, quali test sono esempi di accettazione. Mai la
trascrizione, il diario o il riassunto dell'agente.

**Quando entra** (lo decide il codice, `ciclo.Agente`), sempre sull'esito dei test appena
eseguito e solo se è rosso (non li rifà): alla consegna dell'agente e quando il lavoro si
chiuderebbe da sé (tetto, tappa, prosa, giro a vuoto) con degli esempi di accettazione rossi, una
passata sola per tutti quelli non ancora giudicati nel giro (al più MAX_ESEMPI_PASSATA), con un
verdetto per esempio che vale per l'esempio che nomina (`abbina`); a ogni tappa con i test
dell'agente rossi (anche la consegna rossa e dopo due giri uguali, prima della domanda alla
persona); quando lo stesso errore torna `STESSO_ERRORE_N` volte di fila. Al più una volta per
giro per i momenti dei test, una per esempio, al più `agenti_revisore_passate_giro` passate nel
giro, mai mentre la voce ha la precedenza (l'arbitro), con il suo tempo (`agenti_revisore_s`,
che non conta nel tempo del giro dell'agente) e i suoi token (non quelli dell'agente).

**Cosa ne fa il codice** (`agenti_revisore: attivo`): l'esempio giudicato sbagliato si toglie
dagli esempi del lavoro (il file lo riscrive il codice, l'agente non lo cambia mai; tolto
l'ultimo, il nome resta in sola lettura), con la regola nel registro, il rapporto e la scheda di
revisione; il codice sbagliato è un fatto per l'agente con file e causa; con `consegna` un
esempio resta (il revisore non ha detto che è sbagliato) e alla tappa vale solo con lo stato
consegnabile, altrimenti si ignora e si scrive. Con `ombra` (di serie) il verdetto va solo nel
registro e nella riga del banco: all'agente niente, e gli esempi rossi bloccano come prima.
"""

from __future__ import annotations

import ast
import io
import json
import re
import time
import tokenize
from pathlib import Path
from types import SimpleNamespace

MODI = ("spento", "ombra", "attivo")
# Il menu del ciclo (decisione del 20/10) e quello misurato sul banco del 19/10 (#182)
VERDETTI = ("test_sbagliato", "codice_sbagliato", "consegna")
VERDETTI_BANCO = ("continua", "cambia_strada", "test_sbagliato", "codice_sbagliato", "consegna",
                  "chiedi_persona")
STESSO_ERRORE_N = 3         # lo stesso errore (firma) tante volte di fila nel giro
CODA_USCITA = 2500          # caratteri della coda dell'uscita dei test nel pacchetto
MAX_FILE = 12_000           # caratteri al più per file nel pacchetto…
MAX_FILE_TOTALE = 60_000    # …e in tutto (un messaggio oltre num_ctx, o prove diluite)
MAX_VERDETTI = 30           # quanti verdetti restano nei segnali del lavoro
MAX_ESEMPI_PASSATA = 16     # gli esempi rossi al più in una passata (gli altri alla prossima)
ESCLUSI = {"lavoro.json", "CAPACITA.md", "calliope_estensione.py", "risultato.md"}
# Cartelle eseguite con i test ma non mostrate (le risposte vere delle sonde, fino a 8000
# caratteri l'una: diluiscono le prove)
CARTELLE_ESCLUSE = ("esempi_veri",)
TAGLIATO = "…[tagliato dal banco]"


# ═══════════════════════════ il prompt e lo schema ═══════════════════════════

_TESTA = """Sei il revisore di un lavoro di sviluppo per Calliope, un'assistente di casa. Un \
agente ha scritto il codice e i test; tu non scrivi codice e non hai strumenti. Giudichi solo \
dalle prove che ricevi: il contratto (cosa offre l'ambiente e come si scrivono i test), i \
requisiti della persona, i file del lavoro (senza commenti), l'esito vero dei test e, se c'è, \
il registro dei tentativi dell'agente. Dai il verdetto che darebbe una persona esperta che \
guarda il lavoro.
"""
_SPIEGAZIONI = {
    "continua": "il lavoro va nella direzione giusta e l'agente ha già quello che serve per "
                "andare avanti; nessun intervento.",
    "cambia_strada": "il registro mostra che l'agente gira in tondo (torna a versioni già "
                     "provate, lo stesso errore a ogni tentativo): la strada presa non porta da "
                     "nessuna parte. Vale anche se sai dov'è l'errore vero: dillo in causa e "
                     "azione.",
    "test_sbagliato": "un test chiede qualcosa che il contratto o i requisiti non dicono (o il "
                      "contrario di quello che dicono), e il codice è giusto: va corretto il "
                      "test.",
    "codice_sbagliato": "il test è giusto e il codice no: va corretto il codice.",
    "consegna": "i test passano tutti e i file coprono i requisiti: si può consegnare.",
    "chiedi_persona": "quello che decide dipende da una scelta che i requisiti lasciano alla "
                      "persona: né il test né il codice possono saperla.",
}
_CODA = """
In «file» e «riga» il punto da cambiare (vuoto e 0 se non serve), in «test» il nome del test \
che conta (vuoto se nessuno), in «causa» il perché in breve, in «azione» una sola frase con \
la prossima cosa da fare. Rispondi solo con il JSON dello schema."""
_ESEMPI = """
Gli esempi di accettazione (i file indicati come tali) li ha scritti un'altra passata dai \
requisiti, prima del codice e a mente: possono essere sbagliati (una fase, una parola o un \
punteggio che le regole non danno dopo quelle mosse). Se il test che conta è un esempio di \
accettazione, test_sbagliato vuol dire che è sbagliato l'esempio; consegna vuol dire che il \
lavoro va bene così anche senza quell'esempio."""
_DOMANDA = """
Se una cosa la può decidere solo la persona (una scelta che i requisiti lasciano a lei), \
scegli lo stesso il verdetto più probabile e metti in «domanda» una sola domanda breve per \
lei; altrimenti lascia «domanda» vuota."""


def sistema(verdetti=VERDETTI) -> str:
    """Il prompt del revisore con il menu `verdetti`. Con VERDETTI_BANCO è il testo del banco
    del 19/10 (#182), parola per parola; con VERDETTI (il ciclo) in più gli esempi di
    accettazione e la domanda facoltativa."""
    righe = [_TESTA, "Verdetti:"] + [f"- {v}: {_SPIEGAZIONI[v]}" for v in verdetti]
    testo = "\n".join(righe) + "\n" + _CODA
    if tuple(verdetti) != VERDETTI_BANCO:
        testo += "\n" + _ESEMPI + "\n" + _DOMANDA
    return testo


SISTEMA = sistema(VERDETTI)
SISTEMA_BANCO = sistema(VERDETTI_BANCO)


def schema(verdetti=VERDETTI, domanda: bool | None = None) -> dict:
    """Lo schema chiuso dell'uscita. `domanda` (di serie solo con il menu del ciclo): il campo
    facoltativo per la persona."""
    if domanda is None:
        domanda = tuple(verdetti) != VERDETTI_BANCO
    prop = {"verdetto": {"type": "string", "enum": list(verdetti)},
            "file": {"type": "string", "maxLength": 120},
            "riga": {"type": "integer"},
            "test": {"type": "string", "maxLength": 200},
            "causa": {"type": "string", "maxLength": 400},
            "azione": {"type": "string", "maxLength": 300}}
    if domanda:
        prop["domanda"] = {"type": "string", "maxLength": 300}
    return {"type": "object", "properties": prop,
            "required": ["verdetto", "file", "riga", "test", "causa", "azione"]}


# ═══════════════════════════ i file senza commenti ═══════════════════════════

_PRIMA_REGEX = set("(,=:[!&|?{};+-*%<>~^") | {""}
_PAROLE_REGEX = ("return", "typeof", "case", "in", "of", "delete", "void", "throw", "new")


def senza_commenti_js(testo: str) -> str:
    """Il JavaScript senza commenti // e /* */, con le stringhe, i template e le espressioni
    regolari intatti, e le righe al loro posto (i file:riga dell'uscita dei test restano
    giusti)."""
    s, out, i, n = str(testo or ""), [], 0, len(str(testo or ""))
    ultimo = ""             # l'ultimo carattere significativo, per riconoscere una regex

    def prima_parola():
        m = re.search(r"([A-Za-z_$][\w$]*)\s*$", "".join(out[-40:]))
        return m.group(1) if m else ""
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * s.count("\n", i, j))
            i = j
            continue
        if c in "'\"`":
            j = i + 1
            while j < n and s[j] != c:
                if s[j] == "\\":
                    j += 1
                elif s[j] == "\n" and c != "`":
                    break
                j += 1
            out.append(s[i:j + 1])
            i, ultimo = j + 1, c
            continue
        if c == "/" and (ultimo in _PRIMA_REGEX or prima_parola() in _PAROLE_REGEX):
            j, classe = i + 1, False
            while j < n and s[j] != "\n":
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == "[":
                    classe = True
                elif s[j] == "]":
                    classe = False
                elif s[j] == "/" and not classe:
                    break
                j += 1
            j += 1
            while j < n and (s[j].isalpha()):
                j += 1
            out.append(s[i:j])
            i, ultimo = j, "a"
            continue
        out.append(c)
        if not c.isspace():
            ultimo = c
        i += 1
    return "\n".join(r.rstrip() for r in "".join(out).split("\n"))


def senza_commenti_py(testo: str) -> str:
    """Il Python senza commenti né docstring (una stringa da sola su una riga), con le righe al
    loro posto. Se non si riesce a leggerlo, solo le righe che cominciano con #."""
    s = str(testo or "")
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(s).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "\n".join("" if r.lstrip().startswith("#") else r for r in s.split("\n"))
    righe = s.split("\n")
    via: list[tuple] = []        # (riga, colonna, riga fine, colonna fine) da svuotare
    prima = tokenize.NEWLINE
    for k, t in enumerate(toks):
        if t.type == tokenize.COMMENT:
            via.append((*t.start, *t.end))
        elif (t.type == tokenize.STRING and prima in (tokenize.NEWLINE, tokenize.INDENT,
                                                      tokenize.DEDENT, tokenize.NL)
              and k + 1 < len(toks) and toks[k + 1].type in (tokenize.NEWLINE,
                                                              tokenize.ENDMARKER)):
            via.append((*t.start, *t.end, "docstring"))
        if t.type not in (tokenize.COMMENT, tokenize.NL):
            prima = t.type
    for v in reversed(via):
        r0, c0, r1, c1 = v[:4]
        segnaposto = '""' if len(v) > 4 else ""
        if r0 == r1:
            riga = righe[r0 - 1]
            righe[r0 - 1] = riga[:c0] + segnaposto + riga[c1:]
        else:
            righe[r0 - 1] = righe[r0 - 1][:c0] + segnaposto
            for r in range(r0, r1 - 1):
                righe[r] = ""
            righe[r1 - 1] = righe[r1 - 1][c1:]
    return "\n".join(r.rstrip() for r in righe)


def senza_commenti(nome: str, testo: str) -> str:
    n = nome.lower()
    if n.endswith((".js", ".mjs", ".cjs", ".ts", ".cs")):
        return senza_commenti_js(testo)
    if n.endswith(".py"):
        return senza_commenti_py(testo)
    return str(testo or "")


def precedenza(nome: str) -> tuple:
    """L'ordine dei file sotto il tetto: il manifesto, il codice, i test, poi il resto."""
    b = Path(nome).name.lower()
    test = b.endswith((".test.js", "_test.py")) or (b.startswith("test") and b.endswith(".py"))
    codice = b.endswith((".js", ".mjs", ".cjs", ".ts", ".py", ".cs"))
    return (0 if b == "manifesto.json" else 2 if test else 1 if codice else 3, nome)


def per_revisore(file: dict) -> tuple[dict, list[str]]:
    """I file da mostrare, già senza commenti: senza CARTELLE_ESCLUSE, al più MAX_FILE
    caratteri per file e MAX_FILE_TOTALE in tutto, prima il manifesto, il codice e i test
    (`precedenza`). I commenti si tolgono prima di tagliare, così il marcatore del taglio non
    finisce dentro un commento; gli avvisi dicono cosa è stato tagliato o tolto."""
    out, avvisi, totale = {}, [], 0
    for n in sorted(file, key=precedenza):
        if n.split("/")[0] in CARTELLE_ESCLUSE or Path(n).name in ESCLUSI:
            continue
        t = senza_commenti(n, file[n])
        if totale >= MAX_FILE_TOTALE:
            avvisi.append(f"{n} tolto: il pacchetto ha già {MAX_FILE_TOTALE} caratteri di file")
            continue
        tetto = min(MAX_FILE, MAX_FILE_TOTALE - totale)
        if len(t) > tetto:
            avvisi.append(f"{n} tagliato a {tetto} caratteri su {len(t)}")
            t = t[:tetto] + "\n" + TAGLIATO
        out[n] = t
        totale += len(t)
    return out, avvisi


# ═══════════════════════════ il pacchetto ═══════════════════════════

def _manifesto(file: dict) -> dict:
    try:
        m = json.loads(file.get("manifesto.json") or "")
        return m if isinstance(m, dict) else {}
    except ValueError:
        return {}


def tipo_di(file: dict) -> str:
    m = _manifesto(file)
    if (m.get("scheda") or {}).get("tipo") == "gioco":
        return "gioco"
    return "estensione" if m else "codice"


def pacchetto(cfg, requisiti: list, file: dict, r: dict, registro: list | None = None,
              richiesta: str = "", mostrati: dict | None = None,
              avvisi: list | None = None, accettazione=(), in_esame: str = "") -> dict:
    """Le sezioni che il revisore vede, e nient'altro: contratto, requisiti, file senza
    commenti, esito dei test, registro dei tentativi. `accettazione`: i file che sono esempi di
    accettazione (gli altri test sono dell'agente); `in_esame`: il test da giudicare, se il
    momento ne dice uno (un esempio rosso). Senza, il pacchetto è quello del banco del 19/10."""
    from . import diagnosi
    from ..estensioni import contratto
    u = str(r.get("uscita") or "")
    fall = "" if r.get("passano") else diagnosi.da_uscita(u)
    out = {
        "contratto": contratto.testo(cfg, tipo_di(file)),
        "requisiti": ("\n".join(f"{i}. {x}" for i, x in enumerate(requisiti, 1)) if requisiti
                      else f"(requisiti non trovati; la richiesta: «{richiesta}»)"
                      if richiesta else "(requisiti non trovati)"),
        # `mostrati` (da un lavoro) è già senza commenti e tagliato: non si tocca di nuovo
        "file": ({n: senza_commenti(n, t) for n, t in sorted(file.items()) if n not in ESCLUSI}
                 if mostrati is None else dict(sorted(mostrati.items()))),
        "test": {"esito": diagnosi.conto_detto(r) + ("" if r.get("passano") else
                                                     ", non passano tutti"),
                 "passano": bool(r.get("passano")), "fallimenti": fall,
                 "uscita": u[-CODA_USCITA:]},
        "registro": list(registro or []),
        "avvisi": list(avvisi or []),
    }
    if accettazione:
        out["accettazione"] = [str(x) for x in accettazione]
    if in_esame:
        out["in_esame"] = str(in_esame)
    return out


def messaggio(p: dict) -> str:
    """Il pacchetto come messaggio dell'utente della passata."""
    parti = ["# CONTRATTO (quello che vede l'agente)", p["contratto"], "",
             "# REQUISITI DELLA PERSONA", p["requisiti"], "", "# FILE DEL LAVORO"]
    for n, t in p["file"].items():
        righe = t.split("\n")
        parti += [f"## {n}", "\n".join(f"{i:>3}| {x}" for i, x in enumerate(righe, 1)), ""]
    if p.get("accettazione"):
        parti += ["# QUALI TEST SONO DI CHI",
                  "Esempi di accettazione (scritti prima del codice da un'altra passata, in sola "
                  "lettura per l'agente): " + ", ".join(p["accettazione"])
                  + ". Gli altri test sono dell'agente.", ""]
    t = p["test"]
    parti += ["# ESITO DEI TEST (eseguiti adesso)", t["esito"]]
    if t["fallimenti"]:
        parti += ["Fallimenti in breve:", t["fallimenti"]]
    parti += ["Coda dell'uscita:", t["uscita"], ""]
    if p.get("avvisi"):
        parti += ["# AVVISI DEL BANCO (file tagliati o tolti dal pacchetto)"]
        parti += [f"- {a}" for a in p["avvisi"]] + [""]
    if p["registro"]:
        parti += ["# REGISTRO DEI TENTATIVI DELL'AGENTE (dal più vecchio)"]
        for i, x in enumerate(p["registro"], 1):
            parti.append(f"{i}. {x}" if isinstance(x, str) else
                         f"{i}. {x.get('file')}: {x.get('cosa')} → test: {x.get('esito')}")
    else:
        parti += ["# REGISTRO DEI TENTATIVI", "(nessun registro per questo lavoro)"]
    if p.get("in_esame"):
        parti += ["", "# IL TEST DA GIUDICARE", p["in_esame"]]
    return "\n".join(parti)


def schema_esempi(verdetti=VERDETTI) -> dict:
    """Lo schema di una passata sugli esempi di accettazione rossi di un momento (revisione
    della PR #202): un verdetto per esempio, nella lista «esempi», e la domanda facoltativa."""
    voce = schema(verdetti, domanda=False)
    voce = {"type": "object", "properties": voce["properties"],
            "required": list(voce["required"])}       # «test» c'è già
    return {"type": "object",
            "properties": {"esempi": {"type": "array", "items": voce,
                                      "maxItems": MAX_ESEMPI_PASSATA},
                           "domanda": {"type": "string", "maxLength": 300}},
            "required": ["esempi"]}


def passata(svc, p: dict, ragionamento: int, temperatura: float, tempo_s: float,
            verdetti=VERDETTI, dalla_voce: bool = False, per_esempi: int = 0) -> dict:
    """Una passata del revisore con `requisiti.chiama` (schema chiuso, senza strumenti):
    {risposta (dict o None), esito, s, token, prompt, ragionamento_token,
    ragionamento_caratteri}. `per_esempi` (quanti esempi rossi): lo schema con un verdetto per
    esempio. Mai un'eccezione."""
    from ..requisiti import chiama
    uso: dict = {}
    t0 = time.monotonic()
    dati, esito = chiama(svc, sistema(verdetti), messaggio(p),
                         schema_esempi(verdetti) if per_esempi else schema(verdetti), tempo_s,
                         dalla_voce=dalla_voce,
                         num_predict=min(2400, 400 + 250 * per_esempi) if per_esempi else 700,
                         ragionamento=ragionamento, uso=uso, temperatura=temperatura)
    if per_esempi and isinstance(dati, dict):
        voci = dati.get("esempi")
        if not isinstance(voci, list):
            dati, esito = None, "errore: manca la lista «esempi»"
        else:
            dati["esempi"] = [v for v in voci if isinstance(v, dict)
                              and v.get("verdetto") in verdetti]
    elif isinstance(dati, dict) and dati.get("verdetto") not in verdetti:
        dati, esito = None, f"errore: verdetto fuori dal menu ({dati.get('verdetto')!r})"
    return {"risposta": dati, "esito": esito, "s": round(uso.get("s") or
                                                          (time.monotonic() - t0), 1),
            "token": int(uso.get("eval") or 0), "prompt": int(uso.get("prompt") or 0),
            "ragionamento_token": int(uso.get("ragionamento_token") or 0),
            "ragionamento_caratteri": int(uso.get("ragionamento") or 0)}


# ═══════════════════════════ gli esempi di accettazione ═══════════════════════════

def modo(cfg) -> str:
    m = str(getattr(cfg, "agenti_revisore", "ombra") or "spento").strip().lower()
    return m if m in MODI else "spento"


def file_esempi(lav, sandbox) -> str | None:
    """Il file degli esempi di accettazione del lavoro: quello dell'analisi prima del codice o,
    in una correzione, quello in sola lettura venuto con la versione. None senza."""
    from . import accettazione as acc
    a = getattr(lav, "accettazione", None) or {}
    nomi = []
    if a.get("stato") == "pronta" and a.get("file"):
        nomi.append(a.get("nome_file") or acc.FILE)
    sola = getattr(sandbox, "sola_lettura", None) or set()
    nomi += [n for n in (acc.FILE_GIOCO, acc.FILE) if n in sola]
    for n in nomi:
        try:
            if (sandbox.root / n).is_file():
                return n
        except Exception:  # noqa: BLE001
            continue
    return None


_JS_ESEMPIO = re.compile(r"^FALLITO R(\d+) esempio (\d+)\b[^\n]*", re.M)
_JS_ALTRO = re.compile(r"^FALLITO [^\n]*", re.M)
_PY = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)\n]*)\)[^\n]*", re.M)


def fallimenti_divisi(uscita: str, nome_file: str | None, passano: bool) -> tuple[list, int]:
    """([(indice dell'esempio, nome, riga)], quanti altri fallimenti): gli esempi rossi del file
    `nome_file` e i fallimenti che non sono esempi (test dell'agente, prova di fumo, sintassi).
    Un'uscita rossa senza fallimenti riconosciuti conta come un fallimento altro."""
    u = str(uscita or "")
    esempi, altri = [], 0
    js = bool(nome_file) and str(nome_file).endswith(".js")
    for m in _JS_ALTRO.finditer(u):
        e = _JS_ESEMPIO.match(m.group(0)) if js else None
        if e and int(e.group(2)) > 0:
            esempi.append((int(e.group(2)), f"R{e.group(1)} esempio {e.group(2)}", m.group(0)))
        else:
            altri += 1
    if re.search(r"^errore di sintassi", u, re.M):
        altri += 1
    stem = Path(str(nome_file or "")).stem
    for m in _PY.finditer(u):
        nome, dove = m.group(1), m.group(2)
        k = re.fullmatch(r"test_r(\d+)_(\d+)", nome)
        if stem and not js and k and (dove.startswith(stem + ".") or dove == stem):
            esempi.append((int(k.group(2)), nome, m.group(0)))
        else:
            altri += 1
    if not passano and not esempi and not altri:
        altri = 1
    visti, uniche = set(), []
    for x in esempi:
        if x[0] not in visti:
            visti.add(x[0])
            uniche.append(x)
    return uniche, altri


def _letterale(testo: str, nome: str):
    """(inizio, fine, valore) della lista `nome` nel file degli esempi scritto dal codice
    (accettazione.test_js, test_python, test_programma…): `const ESEMPI = [...];` in
    JavaScript, `ESEMPI = json.loads('…')` in Python. None se non c'è."""
    m = re.search(rf"^const {nome} = ", testo, re.M)
    if m:
        try:
            valore, fine = json.JSONDecoder().raw_decode(testo, m.end())
        except ValueError:
            return None
        return m.end(), fine, valore, "js"
    m = re.search(rf"^{nome} = json\.loads\((.*)\)$", testo, re.M)
    if m:
        try:
            valore = json.loads(ast.literal_eval(m.group(1)))
        except (ValueError, SyntaxError):
            return None
        return m.start(1), m.end(1), valore, "py"
    return None


def esempi_del_file(testo: str) -> tuple[list, list]:
    """(esempi, riconosciuti) del file degli esempi; liste vuote se non si leggono."""
    e = _letterale(testo, "ESEMPI")
    r = _letterale(testo, "RICONOSCIUTI")
    return (list(e[2]) if e else []), (list(r[2]) if r else [])


def senza_esempio(testo: str, indice: int) -> tuple[str, dict] | None:
    """(il file senza l'esempio numero `indice`, 1 come nei nomi dei test; l'esempio tolto).
    Il resto del file resta com'è, byte per byte. None se l'indice non c'è."""
    e = _letterale(testo, "ESEMPI")
    if e is None:
        return None
    esempi = list(e[2])
    nome, k = "ESEMPI", indice - 1
    if not 0 <= k < len(esempi):
        r = _letterale(testo, "RICONOSCIUTI")
        k -= len(esempi)
        if r is None or not 0 <= k < len(r[2]):
            return None
        e, esempi, nome = r, list(r[2]), "RICONOSCIUTI"
    tolto = esempi.pop(k)
    nuovo = json.dumps(esempi, ensure_ascii=False, indent=1)
    if e[3] == "py":
        nuovo = repr(nuovo)
    return testo[:e[0]] + nuovo + testo[e[1]:], tolto


def togli_esempio(lav, sandbox, nome_file: str, indice: int, nome: str, causa: str,
                  log=None) -> dict | None:
    """Toglie dagli esempi del lavoro l'esempio `indice` giudicato sbagliato dal revisore: il
    file lo riscrive il codice (resta in sola lettura per l'agente), il segno resta in
    `lav.accettazione["tolti_revisore"]`. Senza più esempi il file si toglie e il lavoro non ha
    più esempi (`file` false). Il record dell'esempio tolto, o None se non si è potuto."""
    try:
        p = sandbox.root / nome_file
        testo = p.read_text(encoding="utf-8")
        r = senza_esempio(testo, indice)
        if r is None:
            return None
        nuovo, tolto = r
        restano = sum(len(x) for x in esempi_del_file(nuovo))
        sola = getattr(sandbox, "sola_lettura", None)
        if restano:
            if isinstance(sola, set):
                sola.discard(nome_file)
            try:
                sandbox.scrivi(nome_file, nuovo)
            finally:
                if isinstance(sola, set):
                    sola.add(nome_file)
        else:
            # Il nome resta in sola lettura (revisione della PR #202): l'agente non ne scrive
            # uno suo con quel nome
            p.unlink()
            if isinstance(sola, set):
                sola.add(nome_file)
    except Exception as e:  # noqa: BLE001 — l'esempio resta, come prima
        if log is not None:
            log(f"[AGENTI] {getattr(lav, 'id', '?')}: esempio {nome} non tolto: {e}")
        return None
    a = getattr(lav, "accettazione", None)
    if not isinstance(a, dict):
        a = {}
        lav.accettazione = a
    rec = {"nome": nome, "requisito": (tolto or {}).get("requisito"),
           "giro": int(getattr(lav, "giro", 1) or 1), "causa": str(causa or "")[:300],
           "esempio": json.dumps(tolto, ensure_ascii=False)[:300]}
    a.setdefault("tolti_revisore", []).append(rec)
    # Non è un test tolto dall'agente (revisione della PR #202): l'ultima tappa ne conta uno meno
    seg = lav.segnali if isinstance(getattr(lav, "segnali", None), dict) else None
    if seg is not None and isinstance(seg.get("test_tappa"), dict):
        seg["test_tappa"]["eseguiti"] = max(0, int(seg["test_tappa"].get("eseguiti") or 0) - 1)
    if a.get("stato") == "pronta":
        a["esempi"] = max(0, int(a.get("esempi") or 0) - 1)
        rimasti = esempi_del_file(nuovo)
        numeri = sorted({x.get("requisito") for x in rimasti[0] + rimasti[1]
                         if isinstance(x, dict) and x.get("requisito")})
        coppie = list(zip(a.get("requisiti_provati") or [], a.get("testi_provati") or []))
        a["requisiti_provati"] = [n for n, _ in coppie if n in numeri]
        a["testi_provati"] = [t for n, t in coppie if n in numeri]
        if not restano:
            a["file"] = False
    return rec


# ═══════════════════════════ nel ciclo ═══════════════════════════

def _cfg(ag, nome: str, serie):
    v = getattr(ag.cfg, nome, serie)
    return serie if v is None or isinstance(v, bool) else v


def _stato_giro(lav) -> dict:
    """Il conto del revisore per il giro: chiavi già giudicate e passate fatte."""
    seg = lav.segnali if isinstance(getattr(lav, "segnali", None), dict) else {}
    lav.segnali = seg
    giro = int(getattr(lav, "giro", 1) or 1)
    st = seg.get("revisore_giro")
    if not isinstance(st, dict) or st.get("giro") != giro:
        st = {"giro": giro, "chiavi": [], "passate": 0}
        seg["revisore_giro"] = st
    return st


def secondi_giro(lav) -> float:
    """I secondi del revisore nel giro di adesso (per `Agente.trascorso`); 0 senza."""
    seg = lav.segnali if isinstance(getattr(lav, "segnali", None), dict) else {}
    st = seg.get("revisore_giro")
    if not isinstance(st, dict) or st.get("giro") != int(getattr(lav, "giro", 1) or 1):
        return 0.0
    return float(st.get("s") or 0.0)


def _voce_occupata(ag) -> bool:
    arb = getattr(ag, "arbitro", None)
    try:
        f = getattr(arb, "occupata_ora", None)
        return bool(f()) if callable(f) else False
    except Exception:  # noqa: BLE001
        return False


def puo_entrare(ag, lav, chiave: str) -> str | None:
    """None se il revisore può fare una passata per `chiave` adesso; altrimenti il perché
    («spento», «già nel giro», «budget del giro», «voce»)."""
    if modo(ag.cfg) == "spento":
        return "spento"
    st = _stato_giro(lav)
    if chiave in st["chiavi"]:
        return "già nel giro"
    if st["passate"] >= int(_cfg(ag, "agenti_revisore_passate_giro", 3) or 0):
        return "budget del giro"
    if _voce_occupata(ag):
        return "voce"
    return None


def _requisiti(ag, lav) -> tuple[list, str]:
    try:
        _, sv, _ = ag._sviluppo_di(lav)
        if sv is not None:
            from ..requisiti import da_fare
            req = [str(r.get("testo") or "") + (f" — {r['dettaglio']}" if r.get("dettaglio")
                                                else "")
                   for r in da_fare(list(getattr(sv, "requisiti", None) or []))
                   if r.get("testo")]
            if req:
                return req, ""
    except Exception:  # noqa: BLE001 — resta la richiesta
        pass
    return [], str(getattr(lav, "compito", "") or "")[:1500]


def _file_sandbox(sandbox) -> dict:
    out = {}
    for f in sandbox.elenca():
        rel = f["percorso"]
        if any(x.startswith(".") or x == "__pycache__" for x in rel.split("/")):
            continue
        try:
            out[rel] = (sandbox.root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return out


def _registro(lav) -> list[str]:
    seg = lav.segnali if isinstance(getattr(lav, "segnali", None), dict) else {}
    return [f"esegui_test → {x}" for x in list(seg.get("errori_test") or [])[-8:]]


def pacchetto_lavoro(ag, lav, sandbox, test: dict, in_esame: str = "") -> dict:
    """Il pacchetto del revisore da un lavoro nel ciclo: i file della sandbox (senza le cartelle
    nascoste: niente .calliope, cioè niente trascrizione né diario), i requisiti dello sviluppo
    o la richiesta, l'esito dei test dato, il registro delle firme degli errori del giro."""
    file = _file_sandbox(sandbox)
    mostrati, avvisi = per_revisore(file)
    req, richiesta = _requisiti(ag, lav)
    nome = file_esempi(lav, sandbox)
    return pacchetto(ag.cfg, req, file, test, _registro(lav), richiesta, mostrati, avvisi,
                     accettazione=[nome] if nome else (), in_esame=in_esame)


def _una(ag, lav, chiavi, momento: str, p: dict, per_esempi: int = 0):
    """Una passata del revisore per `chiavi` (segnate come giudicate nel giro), contata nel
    giro: (risposta o None, la riga della passata). I secondi della passata non sono tempo
    dell'agente (revisioni della PR #202): vanno in `segnali["revisore_s"]` (in tutto: il ciclo
    li toglie dalla guardia senza strumenti) e nel conto del giro (`revisore_giro["s"]`, che
    `Agente.trascorso` sottrae come l'attesa), non in `lav.attesa_s`: le misure del lavoro
    (secondi, minuti, scheda) restano com'erano. Il passo del lavoro torna com'era."""
    st = _stato_giro(lav)
    st["chiavi"] += list(chiavi)
    st["passate"] += 1
    svc = SimpleNamespace(cliente=ag.cliente, imp=ag.imp, cfg=ag.cfg,
                          arbitro=getattr(ag, "arbitro", None), agente=ag)
    passo = getattr(lav, "passo", "")
    lav.passo = "il revisore guarda le prove"
    t0 = time.monotonic()
    try:
        r = passata(svc, p, int(_cfg(ag, "agenti_revisore_ragionamento", 4096) or 0),
                    float(_cfg(ag, "agenti_temperatura", 0.4) or 0.0),
                    float(_cfg(ag, "agenti_revisore_s", 90.0) or 90.0), per_esempi=per_esempi)
    finally:
        secondi = time.monotonic() - t0
        st["s"] = round(float(st.get("s") or 0.0) + secondi, 3)
        seg = lav.segnali
        seg["revisore_s"] = round(float(seg.get("revisore_s") or 0.0) + secondi, 3)
        lav.passo = passo
    seg["revisore_token"] = int(seg.get("revisore_token") or 0) + r["token"]
    d = r["risposta"]
    if not isinstance(d, dict):
        from ..sonde import nota as nota_regola
        nota_regola(lav, "agente_revisore_errore", ag.log, f"{momento}: {r['esito']}")
        _segna(lav, {"momento": momento, "chiave": ", ".join(chiavi)[:200], "verdetto": None,
                     "esito": r["esito"], "s": r["s"], "token": r["token"]})
        return None, r
    return d, r


def _verdetto(ag, lav, momento: str, d: dict, r: dict, chiave: str) -> dict:
    """Un verdetto letto: la regola nel registro, la riga nel log."""
    from ..sonde import nota as nota_regola
    v = {k: d.get(k) for k in ("verdetto", "file", "riga", "test", "causa", "azione",
                               "domanda")}
    v["domanda"] = str(v.get("domanda") or "").strip()
    nota_regola(lav, f"agente_revisore_{v['verdetto']}", ag.log,
                f"{momento}: {str(v.get('test') or v.get('file') or '')[:80]}")
    ag.log(f"[AGENTI] {lav.id}: revisore ({modo(ag.cfg)}, {momento}): {v['verdetto']}"
           + (f" {v.get('file')}" + (f":{v.get('riga')}" if v.get("riga") else "")
              if v.get("file") else "")
           + f", {r['s']} s, {r['token']} token: {str(v.get('causa') or '')[:160]}")
    return {**v, "momento": momento, "chiave": chiave, "s": r["s"], "token": r["token"]}


def _segna(lav, rec: dict) -> None:
    seg = lav.segnali
    lista = seg.setdefault("revisore", [])
    lista.append({"giro": int(getattr(lav, "giro", 1) or 1), "modo": rec.get("modo"), **rec})
    del lista[:-MAX_VERDETTI]


def _dove(v: dict) -> str:
    f = str(v.get("file") or "").strip()
    try:
        riga = int(v.get("riga") or 0)
    except (TypeError, ValueError):
        riga = 0
    return f + (f":{riga}" if f and riga > 0 else "")


def fatto_codice(v: dict) -> str:
    dove = _dove(v)
    return ("Il revisore (un'altra passata a contesto pulito, con le sole prove) dice che è "
            "sbagliato il codice, non il test"
            + (f" «{v['test']}»" if v.get("test") else "") + (f", in {dove}" if dove else "")
            + f": {str(v.get('causa') or '').rstrip('.')}."
            + (f" {str(v.get('azione') or '').strip()}" if v.get("azione") else ""))


def fatto_test(v: dict) -> str:
    dove = _dove(v)
    return ("Il revisore (un'altra passata a contesto pulito, con le sole prove) dice che è "
            "sbagliato il test" + (f" «{v['test']}»" if v.get("test") else "")
            + (f" ({dove})" if dove else "") + f": {str(v.get('causa') or '').rstrip('.')}."
            + (f" {str(v.get('azione') or '').strip()}" if v.get("azione") else ""))


def fatto_tolto(rec: dict) -> str:
    return (f"L'esempio di accettazione «{rec['nome']}» è sbagliato secondo il revisore "
            f"({str(rec.get('causa') or '').rstrip('.')}): l'ho tolto dagli esempi del lavoro, "
            "non va fatto passare.")


def _esito(**kw) -> dict:
    out = {"tolti": [], "fatti": [], "domande": [], "verdetti": []}
    out.update(kw)
    return out


_NOME_RICONOSCIBILE = re.compile(r"\bR\d+ esempio \d+\b|\btest_r\d+_\d+\b")


def abbina(voci: list, da_giudicare: list, nome_file: str) -> dict:
    """I verdetti della passata sugli esempi, uno per esempio (seconda revisione della PR #202):
    un verdetto vale per l'esempio che nomina; la posizione conta solo per i verdetti senza un
    nome riconoscibile, e solo se i verdetti sono tanti quanti gli esempi; ogni verdetto si usa
    una volta. Un nome che non è fra gli esempi giudicati, o due verdetti per lo stesso esempio,
    non toccano nessun esempio. {"per_esempio": {indice: voce}, "scartati": [(voce, perché)]}."""
    indici = [x[0] for x in da_giudicare]
    nomi = {x[1]: x[0] for x in da_giudicare}
    per_nome: dict = {}
    senza_nome, scartati, doppi = [], [], set()
    for pos, v in enumerate(voci):
        t = str(v.get("test") or "").strip()
        i = nomi.get(t)
        if i is None and _NOME_RICONOSCIBILE.search(t):
            i = esempio_nel_test(nome_file, t)
            if i not in indici:
                scartati.append((v, f"«{t}» non è fra gli esempi rossi giudicati"))
                continue
        if i is None:
            senza_nome.append((pos, v))
            continue
        if i in per_nome or i in doppi:
            doppi.add(i)
            continue
        per_nome[i] = v
    for i in doppi:
        v = per_nome.pop(i, None)
        for x in [v] + [w for w in voci if w is not v and (
                nomi.get(str(w.get("test") or "").strip()) == i
                or esempio_nel_test(nome_file, w.get("test")) == i)]:
            if x is not None:
                scartati.append((x, "più verdetti per lo stesso esempio"))
    per_esempio = dict(per_nome)
    if senza_nome and len(voci) == len(da_giudicare):
        for pos, v in senza_nome:
            i = indici[pos]
            if i in per_esempio or i in doppi:
                scartati.append((v, "senza nome, e il suo posto è di un altro esempio"))
            else:
                per_esempio[i] = v
    else:
        scartati += [(v, "senza un nome riconoscibile") for _, v in senza_nome]
    return {"per_esempio": per_esempio, "scartati": scartati}


def rivedi_esempi(ag, lav, sandbox, momento: str, test: dict | None = None) -> dict:
    """Gli esempi di accettazione rossi quando il lavoro vorrebbe consegnare o chiudersi
    (consegna dell'agente, tetto, tappa, prosa). `test`: l'esito dei test appena eseguiti dal
    ciclo (revisione della PR #202: il revisore non li rifà; senza, niente revisore). Una
    passata sola per tutti gli esempi rossi non ancora giudicati nel giro, con un verdetto per
    esempio (revisione della PR #202: con una passata per esempio il tetto del giro lasciava
    esempi che bloccavano). {tolti, fatti, domande, verdetti}; con «ombra» solo i verdetti."""
    out = _esito()
    m = modo(ag.cfg)
    if m == "spento" or not isinstance(test, dict) or test.get("passano"):
        return out
    nome = file_esempi(lav, sandbox)
    if not nome:
        return out
    rossi, _ = fallimenti_divisi(test.get("uscita"), nome, bool(test.get("passano")))
    rossi.sort(key=lambda x: x[0])
    if not rossi:
        return out
    try:
        testo = (sandbox.root / nome).read_text(encoding="utf-8")
    except OSError:
        testo = ""
    esempi, ric = esempi_del_file(testo)
    tutti = esempi + ric
    st = _stato_giro(lav)
    da_giudicare = []
    for indice, nome_test, riga in rossi:
        # La chiave è l'esempio com'è scritto: dopo un esempio tolto i numeri dei test cambiano
        esempio = tutti[indice - 1] if 0 < indice <= len(tutti) else None
        chiave = "esempio:" + (json.dumps(esempio, sort_keys=True, ensure_ascii=False)
                               if esempio is not None else nome_test)
        if chiave not in st["chiavi"]:
            da_giudicare.append((indice, nome_test, riga, esempio, chiave))
    # Al più MAX_ESEMPI_PASSATA in una passata: gli altri non si segnano come giudicati e
    # restano per la prossima (seconda revisione della PR #202)
    da_giudicare = da_giudicare[:MAX_ESEMPI_PASSATA]
    if not da_giudicare:
        return out
    perche = puo_entrare(ag, lav, da_giudicare[0][4])
    if perche:
        if perche == "voce":
            from ..sonde import nota as nota_regola
            nota_regola(lav, "agente_revisore_saltato", ag.log, f"{momento}: voce")
        return out
    righe = []
    for indice, nome_test, riga, esempio, _ in da_giudicare:
        righe.append(f"- «{nome_test}»: {riga.strip()}"
                     + (f"\n  com'è scritto: {json.dumps(esempio, ensure_ascii=False)}"
                        if esempio is not None else ""))
    in_esame = (f"Gli esempi di accettazione rossi in {nome}:\n" + "\n".join(righe)
                + "\nPer ognuno, in «esempi», un verdetto con il suo nome esatto in «test»: "
                  "sbagliato l'esempio (test_sbagliato), il codice (codice_sbagliato), o il "
                  "lavoro va consegnato così (consegna).")
    d, r = _una(ag, lav, [x[4] for x in da_giudicare], momento,
                pacchetto_lavoro(ag, lav, sandbox, test, in_esame), per_esempi=len(da_giudicare))
    if d is None:
        return out
    voci = list(d.get("esempi") or [])
    domanda = str(d.get("domanda") or "").strip()
    scelte = abbina(voci, da_giudicare, nome)
    for voce, perche in scelte["scartati"]:
        _segna(lav, {"momento": momento, "test": str(voce.get("test") or "")[:200],
                     "verdetto": voce.get("verdetto"), "esito": f"scartato: {perche}",
                     "modo": m})
    tolti_ora = 0
    for k, (indice, nome_test, riga, esempio, chiave) in enumerate(da_giudicare):
        voce = scelte["per_esempio"].get(indice)
        if voce is None:
            _segna(lav, {"momento": momento, "chiave": chiave, "test": nome_test,
                         "verdetto": None, "esito": "senza verdetto per l'esempio", "modo": m})
            continue
        v = _verdetto(ag, lav, momento, {**voce, "test": voce.get("test") or nome_test}, r,
                      chiave)
        effetto = "ombra" if m == "ombra" else "nessuno"
        if m == "attivo":
            f = Path(str(v.get("file") or "")).name
            if v["verdetto"] == "test_sbagliato" and (not f or f == Path(nome).name):
                rec = togli_esempio(lav, sandbox, nome, indice - tolti_ora, nome_test,
                                    v.get("causa"), ag.log)
                if rec is not None:
                    tolti_ora += 1
                    from ..sonde import nota as nota_regola
                    nota_regola(lav, "agente_revisore_esempio_tolto", ag.log, nome_test)
                    lav.nota("flusso", tipo="esito",
                             testo=f"il revisore ha giudicato sbagliato l'esempio {nome_test}: "
                                   "l'ho tolto")
                    out["tolti"].append(rec)
                    out["fatti"].append(fatto_tolto(rec))
                    effetto = "esempio tolto"
            elif v["verdetto"] == "consegna":
                # «consegna» non dice che l'esempio è sbagliato (revisione della PR #202): resta,
                # come in rivedi_test
                from ..sonde import nota as nota_regola
                nota_regola(lav, "agente_revisore_consegna_ignorata", ag.log,
                            f"{momento}: {nome_test}")
                effetto = "ignorato: con «consegna» l'esempio resta"
            elif v["verdetto"] == "codice_sbagliato":
                out["fatti"].append(fatto_codice(v))
                effetto = "fatto all'agente"
            elif v["verdetto"] == "test_sbagliato":
                out["fatti"].append(fatto_test(v))
                effetto = "fatto all'agente"
        _segna(lav, {**v, "modo": m, "effetto": effetto})
        out["verdetti"].append(v)
    if m == "attivo" and domanda:
        out["domande"].append(domanda)
    if tolti_ora:
        seg = lav.segnali
        seg["test_verde"] = None
        seg.pop("ultimo_test", None)
    return out


def esempio_nel_test(nome_file: str | None, test: str) -> int | None:
    """L'indice dell'esempio nominato in `test` («R3 esempio 2…», «test_r3_2»), o None."""
    if not nome_file:
        return None
    t = str(test or "")
    m = re.search(r"\bR\d+ esempio (\d+)\b", t) or re.search(r"\btest_r\d+_(\d+)\b", t)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def rivedi_test(ag, lav, sandbox, momento: str, test: dict, pronto=None) -> dict:
    """I test rossi in uno dei momenti dei test (una tappa con i test rossi, anche dopo la
    consegna rossa e dopo due giri uguali; lo stesso errore STESSO_ERRORE_N volte di fila): una
    passata, al più una nel giro. Il verdetto: un esempio di accettazione sbagliato si toglie;
    un test dell'agente sbagliato o il codice sbagliato sono fatti per l'agente; `consegna` solo
    con lo stato consegnabile; la domanda per la persona. Con «ombra» solo il verdetto."""
    out = _esito()
    m = modo(ag.cfg)
    if m == "spento" or not isinstance(test, dict) or test.get("passano"):
        return out
    perche = puo_entrare(ag, lav, "test")
    if perche:
        if perche == "voce":
            from ..sonde import nota as nota_regola
            nota_regola(lav, "agente_revisore_saltato", ag.log, f"{momento}: voce")
        return out
    nome = file_esempi(lav, sandbox)
    d, r = _una(ag, lav, ["test"], momento, pacchetto_lavoro(ag, lav, sandbox, test))
    if d is None:
        return out
    v = _verdetto(ag, lav, momento, d, r, "test")
    effetto = "ombra"
    if m == "attivo":
        f = Path(str(v.get("file") or "")).name
        indice = (esempio_nel_test(nome, v.get("test"))
                  if nome and f == Path(nome).name else None)
        if v["verdetto"] == "test_sbagliato" and indice is not None:
            rossi, _ = fallimenti_divisi(test.get("uscita"), nome, False)
            rosso = next((x for x in rossi if x[0] == indice), None)
            rec = (togli_esempio(lav, sandbox, nome, indice, rosso[1], v.get("causa"), ag.log)
                   if rosso else None)
            if rec is not None:
                from ..sonde import nota as nota_regola
                nota_regola(lav, "agente_revisore_esempio_tolto", ag.log, rec["nome"])
                out["tolti"].append(rec)
                out["fatti"].append(fatto_tolto(rec))
                effetto = "esempio tolto"
                lav.segnali["test_verde"] = None
                lav.segnali.pop("ultimo_test", None)
            else:
                effetto = "esempio non trovato"
        elif v["verdetto"] == "test_sbagliato" and nome and f == Path(nome).name:
            # Un esempio senza nome riconoscibile: non si tocca, decide la persona
            out["domande"].append(f"Il revisore dice che un esempio di accettazione è "
                                  f"sbagliato: {str(v.get('causa') or '').rstrip('.')}. "
                                  "Lo tolgo?")
            effetto = "alla persona"
        elif v["verdetto"] == "test_sbagliato":
            out["fatti"].append(fatto_test(v))
            effetto = "fatto all'agente"
        elif v["verdetto"] == "codice_sbagliato":
            out["fatti"].append(fatto_codice(v))
            effetto = "fatto all'agente"
        elif v["verdetto"] == "consegna":
            rossi, altri = fallimenti_divisi(test.get("uscita"), nome, False)
            if not (altri == 0 and (pronto is None or bool(pronto()))):
                from ..sonde import nota as nota_regola
                nota_regola(lav, "agente_revisore_consegna_ignorata", ag.log, momento)
                effetto = "ignorato: non consegnabile"
            else:
                effetto = "consegnabile"
        if v.get("domanda"):
            out["domande"].append(v["domanda"])
    _segna(lav, {**v, "modo": m, "effetto": effetto})
    out["verdetti"].append(v)
    return out


FATTI_TAPPA = "Dalla tappa di prima, un fatto da sapere:"


def stesso_errore(seg: dict, n: int = STESSO_ERRORE_N) -> bool:
    """Lo stesso errore (firma) le ultime `n` esecuzioni dei test di fila."""
    e = list((seg or {}).get("errori_test") or [])
    return n > 0 and len(e) >= n and len(set(e[-n:])) == 1 and bool(e[-1])


def frase_esempi_tolti(tolti) -> str:
    """Per il rapporto a voce: gli esempi tolti dal revisore."""
    tolti = [t for t in (tolti or []) if isinstance(t, dict)]
    if not tolti:
        return ""
    if len(tolti) == 1:
        return (f"Il revisore ha giudicato sbagliato l'esempio di accettazione {tolti[0]['nome']}: "
                "l'ho tolto, è sulla scheda di revisione.")
    return (f"Il revisore ha giudicato sbagliati {len(tolti)} esempi di accettazione: li ho "
            "tolti, sono sulla scheda di revisione.")


def righe_esempi_tolti(tolti) -> list[str]:
    """Per la scheda di revisione: un esempio tolto per riga, con la causa."""
    return [f"{t.get('nome')} (giro {t.get('giro')}): {t.get('causa') or 'senza causa'}"
            + (f" — {t['esempio']}" if t.get("esempio") else "")
            for t in (tolti or []) if isinstance(t, dict)]
