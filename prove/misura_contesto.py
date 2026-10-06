"""Misura della finestra di contesto (05/10/2026, fase 1 del rapporto «Contesto di Calliope»,
docs/ricerche/2026-10-05-contesto-budget.md): per ogni finestra (16k, 32k, 64k, 128k) la
memoria occupata e la prima frase con il prefisso vero di Calliope (prompt di sistema e
schemi dei tool) e una storia lunga, sia con la storia già in cache (un turno normale) sia
da rileggere tutta (dopo un cambio di conversazione o una compressione: la velocità di
lettura, «prefill»). Anche la velocità di generazione.

Solo libreria standard: gira anche con il python3 di sistema della DGX. Il prefisso lo
prende da Calliope se è importabile, altrimenti da un file (--prefisso, fatto con --scrivi):

    python prove\\misura_contesto.py --scrivi prefisso.json            # solo il prefisso
    python prove\\misura_contesto.py ollama http://127.0.0.1:11434 gemma4:e4b-it-qat
    python3 misura_contesto.py ollama http://127.0.0.1:11434 gemma4:26b-a4b-it-qat \\
        --prefisso prefisso.json --finestre 16384,32768,65536 --rimetti 16384 --keep -1m
    python3 misura_contesto.py openai http://127.0.0.1:8001/v1 gemma4-26b --prefisso …

Con Ollama cambiare num_ctx ricarica il modello: con --rimetti alla fine lo si ricarica
con quella finestra (e --keep, il keep_alive della voce), così la voce ritrova il suo.
Con vLLM la finestra massima è quella del server (--max-model-len): si misura fin lì.
Memoria: nvidia-smi se dà i numeri (portatile), altrimenti MemAvailable di /proc/meminfo
(memoria unificata della DGX). Mai `ollama ps`, che sottostima.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

argv = sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


if "--scrivi" in argv:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from calliope.brain import Brain
    from calliope.config import Config
    from calliope.documenti.formato import FORMATI
    from calliope.tools.builtin import build_registry
    reg = build_registry(biblioteca=True, citazioni=True, documenti=FORMATI, casa=True,
                         schermi=True, agenti=True, archivio=True)
    with open(opt("--scrivi"), "w", encoding="utf-8") as f:
        json.dump({"system": Brain(Config(), reg, None)._system_messages(),
                   "tools": reg.schemas(online=True)}, f, ensure_ascii=False)
    sys.exit(0)

MOTORE, URL, MODELLO = argv[0], argv[1].rstrip("/"), argv[2]
FINESTRE = [int(x) for x in (opt("--finestre") or "16384,32768,65536,131072").split(",")]
RIMETTI = opt("--rimetti")
KEEP = opt("--keep", "30m")
RIMETTI_KEEP = opt("--rimetti-keep", KEEP)
GENERA = int(opt("--genera", "60"))
if opt("--prefisso"):
    with open(opt("--prefisso"), encoding="utf-8") as f:
        PREF = json.load(f)
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from calliope.brain import Brain
    from calliope.config import Config
    from calliope.documenti.formato import FORMATI
    from calliope.tools.builtin import build_registry
    reg = build_registry(biblioteca=True, citazioni=True, documenti=FORMATI, casa=True,
                         schermi=True, agenti=True, archivio=True)
    PREF = {"system": Brain(Config(), reg, None)._system_messages(),
            "tools": reg.schemas(online=True)}


def keep(v):
    try:
        return int(v)
    except ValueError:
        return v


def post(path, body, timeout=900):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def get(path):
    with urllib.request.urlopen(URL + path, timeout=10) as r:
        return r.read().decode()


def memoria_mib() -> tuple[str, float | None]:
    """(fonte, MiB usati): nvidia-smi se dà numeri, altrimenti MemTotal − MemAvailable."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"], capture_output=True,
                             text=True, timeout=10).stdout.strip().splitlines()
        return "nvidia-smi", float(out[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for riga in f:
                k, v = riga.split(":", 1)
                info[k] = int(v.split()[0])
        return "meminfo", (info["MemTotal"] - info["MemAvailable"]) / 1024
    except (OSError, KeyError, ValueError):
        return "nessuna", None


# Una storia finta ma realistica: domande, risposte brevi, chiamate di tool e risultati
# della biblioteca (testo lungo), come nelle conversazioni vere
def turno(i):
    domanda = {"role": "user", "content": f"Calliope, parlami della città numero {i}: "
               f"quanti abitanti ha e per cosa è famosa?"}
    chiamata = {"role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "biblioteca_cerca",
                                             "arguments": {"domanda": f"città numero {i}"}}}]}
    passaggio = (f"La città numero {i} è un comune italiano di {1000 + 37 * i} abitanti, "
                 f"capoluogo dell'omonima provincia. Sorge lungo il fiume, a {120 + i} metri "
                 "sul livello del mare, ed è nota per il centro storico medievale, le "
                 "chiese romaniche, il mercato del sabato e una tradizione artigiana di "
                 "ceramiche e tessuti che risale al Quattrocento. ") * 3
    risultato = {"role": "tool", "tool_name": "biblioteca_cerca",
                 "content": json.dumps({"ok": True, "fonte": "Wikipedia",
                                        "passaggi": [passaggio]}, ensure_ascii=False)}
    risposta = {"role": "assistant", "content": f"La città numero {i} ha circa "
                f"{1000 + 37 * i} abitanti ed è famosa per il centro storico medievale e le "
                "ceramiche, secondo Wikipedia."}
    return [domanda, chiamata, risultato, risposta]


def storia(n):
    out = []
    for i in range(n):
        out += turno(i)
    return out


def openai_msg(m):
    if m.get("tool_calls"):
        return {"role": "assistant", "content": "",
                "tool_calls": [{"id": f"c{j}", "type": "function",
                                "function": {"name": c["function"]["name"],
                                             "arguments": json.dumps(c["function"]["arguments"])}}
                               for j, c in enumerate(m["tool_calls"])]}
    if m["role"] == "tool":
        return {"role": "tool", "tool_call_id": "c0", "content": m["content"]}
    return {"role": m["role"], "content": m["content"]}


def chiama(messaggi, finestra, nonce="", genera=GENERA):
    """Una richiesta in streaming: (secondi al primo testo, alla prima frase, token del
    prompt, token generati, token/s di generazione, token/s di lettura o None)."""
    msgs = [dict(m) for m in messaggi]
    if nonce:
        msgs[0] = {"role": "system", "content": nonce + "\n" + msgs[0]["content"]}
    t0 = time.perf_counter()
    primo = frase = None
    testo, fine = "", {}
    if MOTORE == "ollama":
        body = {"model": MODELLO, "messages": msgs, "tools": PREF["tools"], "stream": True,
                "think": False, "keep_alive": keep(KEEP),
                "options": {"num_ctx": finestra, "temperature": 0.3, "num_predict": genera}}
        with post("/api/chat", body) as r:
            for riga in r:
                if not riga.strip():
                    continue
                obj = json.loads(riga)
                pezzo = (obj.get("message") or {}).get("content") or ""
                if (pezzo or (obj.get("message") or {}).get("tool_calls")) and primo is None:
                    primo = time.perf_counter() - t0
                testo += pezzo
                if frase is None and len(testo) >= 25 and any(c in testo for c in ".!?"):
                    frase = time.perf_counter() - t0
                if obj.get("done"):
                    fine = obj
        pe, pd = fine.get("prompt_eval_count"), fine.get("prompt_eval_duration") or 0
        ec, ed = fine.get("eval_count") or 0, fine.get("eval_duration") or 0
        return (primo, frase, pe, ec, ec / (ed / 1e9) if ed else None,
                (pe / (pd / 1e9)) if pd and nonce else None)
    body = {"model": MODELLO, "messages": [openai_msg(m) for m in msgs],
            "tools": PREF["tools"], "stream": True, "max_tokens": genera, "temperature": 0.3,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}}
    usage, t_primo = {}, None
    with post("/chat/completions", body) as r:
        for riga in r:
            riga = riga.decode().strip()
            if not riga.startswith("data:") or riga == "data: [DONE]":
                continue
            obj = json.loads(riga[5:])
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices") or []:
                d = ch.get("delta") or {}
                pezzo = d.get("content") or ""
                if (pezzo or d.get("tool_calls")) and primo is None:
                    primo = t_primo = time.perf_counter() - t0
                testo += pezzo
                if frase is None and len(testo) >= 25 and any(c in testo for c in ".!?"):
                    frase = time.perf_counter() - t0
    tot = time.perf_counter() - t0
    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens") or 0
    gen = (ct - 1) / (tot - t_primo) if t_primo and ct > 1 and tot > t_primo else None
    return primo, frase, pt, ct, gen, (pt / t_primo if nonce and t_primo and pt else None)


def r2(x):
    return None if x is None else round(x, 2)


# Domande a cui si risponde dalla storia, senza tool: la prima frase è testo
DOMANDA = "Grazie. Tra le città di cui abbiamo parlato, quale ha più abitanti? Una frase."
righe = []
if "--scarica" in argv and MOTORE == "ollama":
    # Solo dove la voce non lo usa (il portatile senza Calliope accesa): la memoria di base
    # senza il modello
    post("/api/generate", {"model": MODELLO, "keep_alive": 0}).read()
    time.sleep(3)
fonte, base = memoria_mib()
print(f"{MOTORE} {MODELLO} su {URL}; memoria ({fonte}) all'inizio: {base and round(base)} MiB",
      flush=True)
prefisso = PREF["system"] + [{"role": "user", "content": "ciao"}]
# Token veri del prefisso e di un turno della storia (dal server, con la prima finestra)
TOK_FISSI = chiama(prefisso, FINESTRE[0], genera=1)[2] or 7000
TOK_TURNO = max(50, ((chiama(PREF["system"] + storia(10) + [{"role": "user", "content": "ciao"}],
                            FINESTRE[0], genera=1)[2] or 0) - TOK_FISSI) / 10)
print(f"prefisso {TOK_FISSI} token, un turno della storia {TOK_TURNO:.0f}", flush=True)
for n in FINESTRE:
    # Carico con questa finestra (Ollama ricarica) e misuro la memoria
    t = time.perf_counter()
    try:
        chiama(prefisso, n, genera=1)
    except Exception as e:  # noqa: BLE001
        print(f"{n}: non va ({e})", flush=True)
        continue
    carica = time.perf_counter() - t
    time.sleep(2)
    _, mem = memoria_mib()
    # La storia che riempie la finestra fino a ~4k token dalla fine (risposta e margine)
    obiettivo = n - 4096
    k = max(0, int((obiettivo - TOK_FISSI) / TOK_TURNO))
    msgs = PREF["system"] + storia(k) + [{"role": "user", "content": DOMANDA}]
    # Lettura completa (nonce in testa: niente cache), poi un turno con tutto in cache
    freddo = chiama(msgs, n, nonce=f"[misura {time.time():.0f}]")
    chiama(msgs, n, genera=1)                       # mette in cache esattamente questo
    caldo = chiama(msgs + [{"role": "assistant", "content": "La città numero 3."},
                           {"role": "user", "content": "E quale ne ha di meno? Dimmelo con "
                                                       "una frase."}], n)
    riga = {"finestra": n, "carica_s": r2(carica), "memoria_mib": mem and round(mem),
            "delta_mib": (round(mem - base) if mem is not None and base is not None else None),
            "token_prompt": freddo[2], "lettura_tok_s": freddo[5] and round(freddo[5]),
            "freddo_primo_s": r2(freddo[0]), "freddo_frase_s": r2(freddo[1]),
            "caldo_primo_s": r2(caldo[0]), "caldo_frase_s": r2(caldo[1]),
            "genera_tok_s": caldo[4] and round(caldo[4], 1)}
    righe.append(riga)
    print(json.dumps(riga, ensure_ascii=False), flush=True)

if RIMETTI and MOTORE == "ollama":
    KEEP = RIMETTI_KEEP
    chiama(prefisso, int(RIMETTI), genera=1)
    print(f"rimesso: num_ctx {RIMETTI}, keep_alive {KEEP}", flush=True)
    print(get("/api/ps"), flush=True)
if opt("--json"):
    with open(opt("--json"), "w", encoding="utf-8") as f:
        json.dump(righe, f, ensure_ascii=False, indent=1)
