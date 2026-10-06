"""
Banco di prova: molti tool con un LLM piccolo (ricerca del 26/09/2026).

Per ogni richiesta di richieste.py e per ogni strategia fa girare un ciclo di tool
calling come quello di brain.py (API nativa /api/chat, streaming, TextCallGuard vera,
risultati finti), poi assegna il punteggio: tool giusto, argomenti giusti, falsi,
mancati, chiamate scritte come testo, tempi e token.

Uso (dalla radice del progetto):
  .venv\\Scripts\\python.exe -u docs\\ricerche\\banchi\\ricerca_tool\\banco.py --strategie piatto10,piatto40 [--modello M]
      [--limite N] [--solo tipo] [--etichetta X]
Strategie: piatto5/10/20/40 · rag-<emb>-k<K> (emb = bge|nomic) · cat-emb · cat-llm ·
meta · formato · piatto40-think · rag-bge-k5-think · piatto40-esempi · cerca
I risultati vanno in ricerca_tool/risultati/<modello>__<strategia>.jsonl.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import unicodedata

import httpx

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(QUI, "..", "..", "..", "..")))   # radice del repository
sys.path.insert(0, QUI)

from calliope.brain import TextCallGuard                       # noqa: E402  (solo import, nessuna modifica)
import catalogo as K                                  # noqa: E402
from richieste import RICHIESTE                       # noqa: E402

URL = "http://127.0.0.1:11434"
NUM_CTX = 16384
TEMPERATURA = 0.3
RISULTATI = os.path.join(QUI, "risultati")
HTTP = httpx.Client(base_url=URL, timeout=httpx.Timeout(300.0, connect=5.0))

# ─────────────────────────────── PROMPT ───────────────────────────────
_BASE = (
    "Sei Calliope, un'assistente vocale che gira in locale. Il tuo nome viene dalla musa "
    "dell'eloquenza. Parli di te al femminile. Dai del tu a chi ti parla; non ne conosci il "
    "genere, quindi non usare aggettivi o participi riferiti a chi parla. Rispondi in "
    "italiano, in modo caldo e naturale, da una a tre frasi, senza markdown, elenchi, emoji "
    "o URL: il testo va letto ad alta voce. {nomi} Per le altre richieste usa il tool adatto, "
    "se ce l'hai. Chiama il tool, non annunciarlo, poi rispondi con il risultato. Per cultura "
    "generale, geografia, storia, scienza, consigli, barzellette e storie rispondi con quello "
    "che sai, subito e senza premesse. Se ti chiedono di ricordare qualcosa su di sé, o ti "
    "dicono qualcosa di importante e duraturo su di sé, chiama {ricorda}, se ce l'hai. Se "
    "nessuno dei tuoi tool fa quello che ti chiedono, dillo in breve e non dire mai di averlo "
    "fatto. Vai dritta al punto e non offrire altro aiuto.")
SYSTEM = _BASE.format(nomi="Per l'ora chiama ora_attuale, per la data data_oggi, per sapere chi "
                           "ti parla chi_parla.", ricorda="ricorda")
SYSTEM_META = _BASE.format(nomi="Per l'ora e la data chiama orologio, per sapere chi ti parla "
                                "persone con azione chi_parla.", ricorda="memoria")
ISTR = (" Per usare un tool emetti sempre una chiamata di funzione vera, mai il suo nome "
        "scritto nel testo.")
ESEMPI = (" Esempi di scelta: «fai luce in bagno» → luce_accendi con stanza bagno; "
          "«conto alla rovescia di cinque minuti» → timer_imposta con minuti 5; «quanto fa 12 per 4» "
          "→ calcola con espressione 12*4; «ricordami di chiamare Luca» → promemoria_crea; "
          "«tieni a mente che mi piace il jazz» → ricorda; «chi era Napoleone?» → nessun tool, "
          "rispondi tu; «prenota un volo» → nessun tool, di' che non puoi.")


def compatto(names) -> str:
    """Schemi in forma compatta, per lo stadio con formato vincolato."""
    righe = []
    for n in names:
        t = K.BY_NAME[n]
        props = t["params"]["properties"]
        req = set(t["params"].get("required", []))
        args = ", ".join(a + ("" if a in req else "?") for a in props)
        desc = t["desc"].split(". ")[0].rstrip(".")
        righe.append(f"- {n}({args}): {desc}")
    return "\n".join(righe)


# ─────────────────────────────── OLLAMA ───────────────────────────────
def _native(m: dict) -> dict:
    if m["role"] == "assistant" and m.get("tool_calls"):
        return {"role": "assistant", "content": m.get("content", ""),
                "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                               for c in m["tool_calls"]]}
    if m["role"] == "tool":
        return {"role": "tool", "tool_name": m["name"], "content": m["content"]}
    return {"role": m["role"], "content": m["content"]}


def corpo(model, messages, tools=None, think=False, stream=True, fmt=None, **options):
    body = {"model": model, "messages": [_native(m) for m in messages], "stream": stream,
            "think": think, "keep_alive": "30m",
            "options": {"num_ctx": NUM_CTX, "temperature": TEMPERATURA, **options}}
    if tools:
        body["tools"] = tools
    if fmt is not None:
        body["format"] = fmt
    return body


def turno(model, messages, tools, guard_schemas, think=False):
    """Una passata in streaming. Tempi misurati da qui."""
    t0 = time.perf_counter()
    guard = TextCallGuard(guard_schemas)
    out, calls, stats = [], [], {}
    t_evento = t_testo = None
    with HTTP.stream("POST", "/api/chat", json=corpo(model, messages, tools, think)) as r:
        if r.status_code >= 400:
            r.read()
            raise RuntimeError(f"Ollama {r.status_code}: {r.text}")
        for line in r.iter_lines():
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("error"):
                raise RuntimeError(obj["error"])
            msg = obj.get("message") or {}
            content = msg.get("content") or ""
            if (content.strip() or msg.get("tool_calls")) and t_evento is None:
                t_evento = time.perf_counter() - t0
            piece = guard.feed(content) if content else ""
            if piece:
                if piece.strip() and t_testo is None:
                    t_testo = time.perf_counter() - t0
                out.append(piece)
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                calls.append({"name": fn.get("name", ""), "arguments": args if isinstance(args, dict) else {}})
            if obj.get("done"):
                stats = {k: obj.get(k) for k in ("prompt_eval_count", "prompt_eval_duration",
                                                  "eval_count", "eval_duration", "load_duration")}
                break
    piece = guard.flush()
    if piece:
        if piece.strip() and t_testo is None:
            t_testo = time.perf_counter() - t0
        out.append(piece)
    da_testo = False
    if not calls and guard.call:
        calls, da_testo = [{"name": guard.call["name"], "arguments": guard.call["arguments"]}], True
    return {"testo": "".join(out).strip(), "calls": calls, "da_testo": da_testo,
            "t_evento": t_evento, "t_testo": t_testo, "t_tot": time.perf_counter() - t0,
            "stats": stats}


def chiamata_json(model, messages, fmt, **options):
    """Chiamata non in streaming con formato vincolato. → (oggetto, secondi, stats)"""
    t0 = time.perf_counter()
    r = HTTP.post("/api/chat", json=corpo(model, messages, stream=False, fmt=fmt, **options))
    r.raise_for_status()
    d = r.json()
    dt = time.perf_counter() - t0
    try:
        obj = json.loads(d["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        obj = None
    return obj, dt, {k: d.get(k) for k in ("prompt_eval_count", "prompt_eval_duration", "eval_count")}


# ─────────────────────────────── EMBEDDING ───────────────────────────────
class Embedder:
    MODELLI = {"bge": "bge-m3", "nomic": "nomic-embed-text"}

    def __init__(self, sigla: str, esempi=True, cpu=False):
        self.model = self.MODELLI[sigla]
        self.cpu = cpu
        self.nomic = sigla == "nomic"
        docs = [K.doc(t, esempi) for t in K.TOOLS]
        if self.nomic:
            docs = ["search_document: " + d for d in docs]
        self.tool_vec, _ = self.embed(docs)

    def embed(self, texts):
        body = {"model": self.model, "input": texts, "keep_alive": "30m"}
        if self.cpu:
            body["options"] = {"num_gpu": 0}
        t0 = time.perf_counter()
        r = HTTP.post("/api/embed", json=body)
        r.raise_for_status()
        vecs = r.json()["embeddings"]
        dt = time.perf_counter() - t0
        out = []
        for v in vecs:
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out, dt

    def punteggi(self, query: str):
        q = ("search_query: " + query) if self.nomic else query
        (v,), dt = self.embed([q])
        sc = [(sum(a * b for a, b in zip(v, tv)), t["name"]) for tv, t in zip(self.tool_vec, K.TOOLS)]
        sc.sort(reverse=True)
        return sc, dt


def query_di(req) -> str:
    """Testo da cercare: la richiesta, più quella dell'utente al turno prima (seguiti)."""
    prima = [m["content"] for m in req["storia"] if m["role"] == "user"]
    return (prima[-1] + " → " + req["testo"]) if prima else req["testo"]


# ─────────────────────────────── STRATEGIE ───────────────────────────────
class Strategia:
    """Decide quali tool mostrare (e con quale prompt) per ogni richiesta."""
    nome = ""
    system = SYSTEM
    think = False
    meta = False

    def prepara(self, req) -> dict:
        """→ {"tools": [schemi], "offerti": [nomi fini], "pre_s": secondi, ...}"""
        raise NotImplementedError


class Piatto(Strategia):
    def __init__(self, n, think=False, esempi=False, istr=False):
        self.names = K.SOTTOINSIEMI[n]
        self.nome = f"piatto{n}" + ("-think" if think else "") + ("-esempi" if esempi else "")
        self.think = think
        self.system = SYSTEM + (ESEMPI if esempi else "") + (ISTR if istr else "")

    def prepara(self, req):
        return {"tools": K.schemas(self.names), "offerti": self.names, "pre_s": 0.0}


class Rag(Strategia):
    def __init__(self, sigla, k, think=False, esempi=True):
        self.emb = Embedder(sigla, esempi)
        self.k = k
        self.think = think
        self.nome = f"rag-{sigla}-k{k}" + ("-think" if think else "")

    def prepara(self, req):
        sc, dt = self.emb.punteggi(query_di(req))
        altri = [n for _, n in sc if n not in K.NUCLEO][: self.k]
        # Ordine del catalogo: stessi tool → stesso prefisso
        names = [t["name"] for t in K.TOOLS if t["name"] in K.NUCLEO or t["name"] in altri]
        return {"tools": K.schemas(names), "offerti": names, "pre_s": dt}


class CatEmb(Strategia):
    """Categorie dei 2 tool più simili → tutti i tool di quelle categorie + nucleo."""
    nome = "cat-emb"

    def __init__(self, sigla="bge", top=3):
        self.emb = Embedder(sigla, True)
        self.top = top
        self.nome = f"cat-emb-{sigla}"

    def prepara(self, req):
        sc, dt = self.emb.punteggi(query_di(req))
        cats = []
        for _, n in sc[: self.top]:
            cat = K.BY_NAME[n]["cat"]
            if cat not in cats:
                cats.append(cat)
        names = [t["name"] for t in K.TOOLS if t["name"] in K.NUCLEO or t["cat"] in cats]
        return {"tools": K.schemas(names), "offerti": names, "pre_s": dt, "categorie": cats}


ROUTER_SYS = ("Sei il centralino di un'assistente vocale di casa. Leggi la richiesta e scegli "
              "le categorie di strumenti che servono per soddisfarla (al massimo due), oppure "
              "nessuna se basta rispondere a parole (chiacchiere, cultura generale, consigli). "
              "Categorie:\n" + "\n".join(f"- {k}: {v}" for k, v in K.CATEGORIE.items()))
ROUTER_FMT = {"type": "object", "properties": {"categorie": {
    "type": "array", "maxItems": 2, "items": {"type": "string", "enum": list(K.CATEGORIE)}}},
    "required": ["categorie"]}


class CatLlm(Strategia):
    def __init__(self, model):
        self.model = model
        self.nome = "cat-llm"

    def prepara(self, req):
        msgs = [{"role": "system", "content": ROUTER_SYS}]
        prima = [m["content"] for m in req["storia"] if m["role"] == "user"]
        if prima:
            msgs.append({"role": "user", "content": "Richiesta precedente: " + prima[-1]})
        msgs.append({"role": "user", "content": req["testo"]})
        obj, dt, st = chiamata_json(self.model, msgs, ROUTER_FMT, num_predict=40)
        cats = [c for c in (obj or {}).get("categorie", []) if c in K.CATEGORIE]
        names = [t["name"] for t in K.TOOLS if t["name"] in K.NUCLEO or t["cat"] in cats]
        return {"tools": K.schemas(names), "offerti": names, "pre_s": dt, "categorie": cats,
                "pre_stats": st}


class Meta(Strategia):
    nome = "meta"
    system = SYSTEM_META
    meta = True

    def prepara(self, req):
        return {"tools": [K.meta_schema(m) for m in K.META], "offerti": [t["name"] for t in K.TOOLS],
                "pre_s": 0.0}


class Cerca(Strategia):
    """«Tool search»: nucleo + un tool cerca_strumenti che aggiunge gli schemi trovati.

    Il modello chiama cerca_strumenti(bisogno); il risultato elenca i tool trovati (top 5
    con embedding) e questi vengono aggiunti all'elenco per il giro dopo.
    """
    nome = "cerca"
    system = SYSTEM + (" Se tra i tuoi tool non vedi quello adatto a un'azione o a un dato, chiama "
                       "prima cerca_strumenti: non dire che non puoi prima di averlo cercato.")
    CERCA = {"type": "function", "function": {
        "name": "cerca_strumenti",
        "description": ("Trova gli strumenti per fare un'azione o leggere un dato che non vedi tra i "
                        "tuoi tool (casa, musica, timer, promemoria, meteo, messaggi, liste, file, "
                        "calcoli…). Dopo, chiama lo strumento trovato."),
        "parameters": {"type": "object", "properties": {"bisogno": {"type": "string",
                       "description": "cosa serve, in poche parole"}}, "required": ["bisogno"]}}}

    def __init__(self, sigla="bge", k=5):
        self.emb = Embedder(sigla, True)
        self.k = k

    def prepara(self, req):
        return {"tools": K.schemas(K.NUCLEO) + [self.CERCA], "offerti": list(K.BY_NAME), "pre_s": 0.0,
                "cerca": self}

    def trova(self, bisogno):
        sc, dt = self.emb.punteggi(bisogno)
        return [n for _, n in sc if n not in K.NUCLEO][: self.k], dt


FORMATO_SYS = ("Sei il modulo che sceglie gli strumenti di Calliope, un'assistente vocale di casa. "
               "Per la richiesta dell'utente restituisci le chiamate agli strumenti che servono, "
               "con gli argomenti; una lista vuota se basta rispondere a parole (chiacchiere, "
               "cultura generale, consigli) o se nessuno strumento fa ciò che chiede. Strumenti:\n")


class Formato(Strategia):
    """Scelta con formato vincolato (grammatica dallo schema JSON), poi risposta senza tool."""
    nome = "formato"

    def __init__(self, model):
        self.model = model
        names = K.S40
        self.sys = FORMATO_SYS + compatto(names)
        self.fmt = {"type": "object", "properties": {"chiamate": {
            "type": "array", "maxItems": 3, "items": {
                "type": "object", "properties": {"tool": {"type": "string", "enum": names},
                                                 "argomenti": {"type": "object"}},
                "required": ["tool", "argomenti"]}}}, "required": ["chiamate"]}

    def prepara(self, req):
        msgs = [{"role": "system", "content": self.sys}] + req["storia"] + \
               [{"role": "user", "content": req["testo"]}]
        obj, dt, st = chiamata_json(self.model, msgs, self.fmt, num_predict=120)
        calls = []
        for ch in (obj or {}).get("chiamate", []):
            if ch.get("tool") in K.BY_NAME:
                calls.append({"name": ch["tool"], "arguments": ch.get("argomenti") or {}})
        return {"tools": [], "offerti": K.S40, "pre_s": dt, "decise": calls, "pre_stats": st}


def crea(nome: str, model: str) -> Strategia:
    m = re.fullmatch(r"piatto(\d+)(-think)?(-esempi)?(-istr)?", nome)
    if m:
        s = Piatto(int(m.group(1)), bool(m.group(2)), bool(m.group(3)), bool(m.group(4)))
        s.nome = nome
        return s
    m = re.fullmatch(r"rag-(bge|nomic)-k(\d+)(-think)?(-noes)?(-istr)?", nome)
    if m:
        s = Rag(m.group(1), int(m.group(2)), bool(m.group(3)), esempi=not m.group(4))
        s.nome = nome
        if m.group(5):
            s.system = SYSTEM + ISTR
        return s
    if nome.startswith("cat-emb"):
        return CatEmb(nome.split("-")[2] if nome.count("-") >= 2 else "bge")
    return {"cat-llm": lambda: CatLlm(model), "meta": Meta, "formato": lambda: Formato(model),
            "cerca": Cerca}[nome]()


# ─────────────────────────────── ESECUZIONE ───────────────────────────────
TUTTI_SCHEMI = K.schemas(K.S40) + [K.meta_schema(m) for m in K.META] + [Cerca.CERCA]
_FUGA = re.compile(r"\b[a-z]+_[a-z_]+\s*[\(\{]|call:|\b(" + "|".join(
    n for n in K.BY_NAME if "_" in n) + r")\b|<\|")


def risultato_finto(nome, args):
    t = K.BY_NAME.get(nome)
    if not t:
        return json.dumps({"errore": f"tool sconosciuto: {nome}"}, ensure_ascii=False)
    try:
        return json.dumps(t["risultato"](args or {}), ensure_ascii=False)
    except Exception as e:                              # argomenti strani
        return json.dumps({"errore": str(e)}, ensure_ascii=False)


def esegui(model: str, strat: Strategia, req: dict, max_giri=3) -> dict:
    t0 = time.perf_counter()
    prep = strat.prepara(req)
    tools = list(prep["tools"])
    system = strat.system
    messages = [{"role": "system", "content": system}] + req["storia"] + \
               [{"role": "user", "content": req["testo"]}]
    fini, grezze, da_testo, testi = [], [], 0, []
    primo_turno, t_decisione, t_testo = None, None, None
    cercati = []

    if "decise" in prep:                                # strategia «formato»
        t_decisione = prep["pre_s"]
        calls = prep["decise"]
        if calls:
            messages.append({"role": "assistant", "content": "", "tool_calls": calls})
            for c in calls:
                fini.append((c["name"], c["arguments"]))
                grezze.append(c)
                messages.append({"role": "tool", "name": c["name"],
                                 "content": risultato_finto(c["name"], c["arguments"])})
            messages[0] = {"role": "system", "content": SYSTEM}
        else:
            messages[0] = {"role": "system", "content": SYSTEM}
        r = turno(model, messages, None, TUTTI_SCHEMI)
        primo_turno = r
        if r["t_testo"] is not None:
            t_testo = time.perf_counter() - t0 - r["t_tot"] + r["t_testo"]
        testi.append(r["testo"])
    else:
        for giro in range(max_giri + 1):
            last = giro == max_giri
            ts = time.perf_counter()
            r = turno(model, messages, None if last else tools, TUTTI_SCHEMI,
                      think=strat.think and giro == 0)
            base = ts - t0
            if primo_turno is None:
                primo_turno = r
                t_decisione = base + (r["t_evento"] if r["t_evento"] is not None else r["t_tot"])
            if r["t_testo"] is not None and t_testo is None:
                t_testo = base + r["t_testo"]
            if r["testo"]:
                testi.append(r["testo"])
            calls = r["calls"]
            da_testo += bool(r["da_testo"])
            if not calls or last:
                break
            messages.append({"role": "assistant", "content": r["testo"], "tool_calls": calls})
            for c in calls:
                grezze.append(c)
                nome, args = c["name"], c["arguments"]
                if nome == "cerca_strumenti" and "cerca" in prep:
                    trovati, dt = prep["cerca"].trova(str(args.get("bisogno", "")))
                    cercati += trovati
                    nuovi = [n for n in trovati if n not in [s["function"]["name"] for s in tools]]
                    tools = tools + K.schemas(nuovi)
                    res = json.dumps({"strumenti_trovati": trovati,
                                      "cosa_fare": "ora chiama lo strumento adatto"}, ensure_ascii=False)
                    messages.append({"role": "tool", "name": nome, "content": res})
                    continue
                if strat.meta:
                    nome, args = K.meta_to_fine(nome, args)
                    nome = nome or c["name"]
                fini.append((nome, args))
                messages.append({"role": "tool", "name": c["name"], "content": risultato_finto(nome, args)})

    detto = " ".join(testi).strip()
    st = primo_turno["stats"] if primo_turno else {}
    return {"chiamate": fini, "grezze": grezze, "da_testo": da_testo, "detto": detto,
            "fuga": bool(_FUGA.search(detto)), "offerti": prep["offerti"], "categorie": prep.get("categorie"),
            "cercati": cercati,
            "pre_ms": round(prep["pre_s"] * 1000, 1),
            "t_decisione": round(t_decisione, 3) if t_decisione is not None else None,
            "t_testo": round(t_testo, 3) if t_testo is not None else None,
            "t_tot": round(time.perf_counter() - t0, 3),
            "prompt_tok": st.get("prompt_eval_count"),
            "prompt_ms": round((st.get("prompt_eval_duration") or 0) / 1e6, 1),
            "pre_stats": prep.get("pre_stats")}


# ─────────────────────────────── PUNTEGGIO ───────────────────────────────
def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def val_ok(exp, act) -> bool:
    if act is None or act == "":
        return False
    if isinstance(exp, list):
        return any(val_ok(e, act) for e in exp)
    if isinstance(exp, (int, float)):
        try:
            return abs(float(act) - exp) < 1e-6
        except (TypeError, ValueError):
            return any(abs(float(x) - exp) < 1e-6 for x in re.findall(r"\d+(?:[.,]\d+)?", str(act).replace(",", ".")))
    if exp.startswith("re:"):
        return re.search(exp[3:], norm(act)) is not None
    return norm(exp) in norm(act)


def esiti_effettivi(req, offerti) -> tuple[list, str]:
    """Gli esiti possibili con i tool offerti. Se il catalogo non ha il tool: nessun tool."""
    # Un esito con tool che mancano si riduce a quelli disponibili: con «che ore sono e che
    # tempo fa?» e senza meteo, la risposta giusta è chiamare l'ora e dire che il meteo no.
    fatt = []
    for e in req["esiti"]:
        rid = [(n, a) for n, a in e if n in offerti]
        if rid not in fatt:
            fatt.append(rid)
    if req["tipo"] in ("senza", "assente"):
        return fatt, "senza"
    if all(e == [] for e in fatt):
        return [[]], "fuori"
    return fatt, "catalogo"


def punteggio(req, rec, catalogo_intero) -> dict:
    """catalogo_intero: i tool che la strategia *potrebbe* usare (per il recupero: tutti)."""
    esiti, gruppo = esiti_effettivi(req, catalogo_intero)
    chiamati = [(n, a if isinstance(a, dict) else {}) for n, a in rec["chiamate"]]
    nomi = {n for n, _ in chiamati}
    tool_ok = args_ok = False
    for e in esiti:
        if {n for n, _ in e} == nomi:
            tool_ok = True
            ok = all(any(n2 == n and all(val_ok(v, a.get(k)) for k, v in exp.items())
                         for n2, a in chiamati) for n, exp in e)
            args_ok = args_ok or ok
    vuoto_ok = any(e == [] for e in esiti)
    if tool_ok:
        classe = "giusto"
    elif not nomi:
        classe = "mancato"
    elif vuoto_ok and all(e == [] for e in esiti):
        classe = "falso"
    else:
        classe = "sbagliato"
    richiede = not vuoto_ok
    # il tool atteso era tra quelli offerti al modello? (recupero)
    offerto = any(all(n in rec["offerti"] for n, _ in e) for e in esiti)
    return {"gruppo": gruppo, "tool_ok": tool_ok, "args_ok": args_ok and tool_ok, "classe": classe,
            "richiede_tool": richiede, "offerto": offerto}


# ─────────────────────────────── MAIN ───────────────────────────────
def riassumi(righe) -> dict:
    n = len(righe)
    g = sum(r["tool_ok"] for r in righe)
    a = sum(r["args_ok"] for r in righe)
    cat = [r for r in righe if r["gruppo"] == "catalogo"]
    senza = [r for r in righe if r["gruppo"] != "catalogo"]
    td = sorted(r["t_decisione"] for r in righe if r["t_decisione"] is not None)
    tt = sorted(r["t_testo"] for r in righe if r["t_testo"] is not None)
    q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None
    return {"n": n, "giusti": g, "args": a,
            "cat_n": len(cat), "cat_giusti": sum(r["tool_ok"] for r in cat),
            "cat_args": sum(r["args_ok"] for r in cat),
            "senza_n": len(senza), "falsi": sum(r["classe"] == "falso" for r in senza),
            "mancati": sum(r["classe"] == "mancato" for r in righe),
            "sbagliati": sum(r["classe"] == "sbagliato" for r in righe),
            "da_testo": sum(r["da_testo"] for r in righe), "fughe": sum(r["fuga"] for r in righe),
            "non_offerto": sum(1 for r in cat if not r["offerto"]),
            "t_dec_med": q(td, .5), "t_dec_p90": q(td, .9), "t_testo_med": q(tt, .5),
            "t_testo_p90": q(tt, .9),
            "prompt_tok_med": statistics.median([r["prompt_tok"] or 0 for r in righe]) if righe else None,
            "prompt_ms_med": statistics.median([r["prompt_ms"] for r in righe]) if righe else None,
            "pre_ms_med": statistics.median([r["pre_ms"] for r in righe]) if righe else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modello", default="gemma4:e4b-it-qat")
    ap.add_argument("--strategie", default="piatto10")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--solo", default="")
    ap.add_argument("--etichetta", default="")
    args = ap.parse_args()
    os.makedirs(RISULTATI, exist_ok=True)
    reqs = [dict(r, id=i) for i, r in enumerate(RICHIESTE)]
    if args.solo:
        reqs = [r for r in reqs if r["tipo"] in args.solo.split(",")]
    if args.limite:
        reqs = reqs[: args.limite]
    # carica il modello con lo stesso num_ctx di Calliope
    t = time.perf_counter()
    HTTP.post("/api/chat", json=corpo(args.modello, [{"role": "user", "content": "ciao"}],
                                      stream=False, num_predict=1)).raise_for_status()
    print(f"{args.modello}: pronto in {time.perf_counter() - t:.1f}s, {len(reqs)} richieste", flush=True)

    for nome in args.strategie.split(","):
        strat = crea(nome, args.modello)
        intero = K.S40 if not nome.startswith("piatto") else strat.names
        # riscaldamento: stesso prefisso della prima richiesta
        esegui(args.modello, strat, reqs[0])
        file = os.path.join(RISULTATI, f"{args.modello.replace(':', '_')}__{nome}{args.etichetta}.jsonl")
        righe = []
        with open(file, "w", encoding="utf-8") as f:
            for req in reqs:
                rec = esegui(args.modello, strat, req)
                rec.update(punteggio(req, rec, intero))
                rec.update({"id": req["id"], "testo": req["testo"], "tipo": req["tipo"],
                            "strategia": nome, "modello": args.modello})
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                righe.append(rec)
                segno = {"giusto": "ok " if rec["args_ok"] else "ok~", "falso": "FAL",
                         "mancato": "MAN", "sbagliato": "SBA"}[rec["classe"]]
                print(f"{segno} {rec['t_decisione'] or 0:5.2f}s {rec['t_testo'] or 0:5.2f}s "
                      f"{'T' if rec['da_testo'] else ' '}{'F' if rec['fuga'] else ' '} "
                      f"[{req['tipo'][:5]}] {req['testo'][:50]!r} → "
                      f"{','.join(n for n, _ in rec['chiamate']) or '—'} "
                      f"{json.dumps([a for _, a in rec['chiamate']], ensure_ascii=False)[:80]}", flush=True)
        s = riassumi(righe)
        print(f"\n### {args.modello} · {nome}: " + json.dumps(s, ensure_ascii=False), flush=True)
        with open(os.path.join(RISULTATI, "riassunti.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"modello": args.modello, "strategia": nome + args.etichetta,
                                "quando": time.strftime("%Y-%m-%d %H:%M"), **s}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
