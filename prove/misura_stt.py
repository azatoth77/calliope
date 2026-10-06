import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Confronto dei motori di trascrizione (05/10, docs/ricerche/2026-10-05-stt-confronto.md).

Gira sulla DGX (le richieste vanno ai server locali: i tempi non hanno la VPN dentro) o
ovunque ci sia un server raggiungibile. Solo libreria standard, numpy e httpx (Parakeet:
onnx-asr, in un venv a parte). Non tocca nessun servizio: solo richieste.

  misura_stt.py trascrivi --insieme rif|dominio --dati DIR --motore M --uscita F.jsonl
        [--url U] [--modello X] [--contesto]
     M = whispercpp (verbose_json, con la confidenza), gemma_audio (Ollama, audio nel campo
         images), voxtral (POST /audio/transcriptions), voxtral_chat (chat con l'audio e
         il contesto), parakeet (onnx-asr su CPU)
  misura_stt.py correggi --da F.jsonl --uscita G.jsonl --motore ollama|openai --url U
        --modello X [--num-ctx N] [--keep-alive K] [--senza-vocabolario] [--senza-storia]
     secondo passaggio di calliope/stt_correzione.py su TUTTE le frasi (la soglia si
     applica in «valuta»)
  misura_stt.py valuta F.jsonl [G.jsonl ...] [--soglia 0.5 ...] [--rivaluta] [--utile]
        [--tetto S]
     --rivaluta: rifà il controllo (accettabile) di adesso sulle proposte salvate
     --utile: la soglia sulla parola più debole senza il nome (stt_correzione.min_utile,
              come Calliope dal 05/10 sera); --tetto: una correzione oltre S secondi vale
              Whisper e costa S (stt_correzione_timeout_s)
  misura_stt.py interpreta --da F.jsonl --uscita G.jsonl --variante A|B|C --url U
        --modello X [--num-ctx N] [--keep-alive K] [--soglia 0.4] [--tetto S]
     confronto A/B/C del 07/10 (docs/aree/stt-tts.md): il modello della voce riceve la frase
     (A: di Whisper; B: di Whisper con le parole incerte nei dati del turno, come Calliope con
     stt_incerte_al_modello; C: corretta, da un file di «correggi») e scrive come l'ha capita
  misura_stt.py capisci --da F.jsonl --uscita G.jsonl --url U --modello X [--num-ctx N]
        [--keep-alive K] [--soglia 0.4]
     variante B2 (07/10): sulle frasi con parole incerte il modello della voce riceve
     l'istruzione vera dei dati del turno (Brain.STT_RISCRIVI_MSG) e risponde; la riga
     «⟦capito: …⟧» si legge con Brain.CapitoHold e vale se accettabile. Scrive i campi di
     «correggi» (corretta, cambiata, t_corr = attesa della riga), da leggere con valuta
  misura_stt.py confronta A.jsonl B.jsonl C.jsonl
     quante parole sbagliate da Whisper tornano nella frase capita, frasi capite, parole
     giuste perse, domande di chiarimento; tutte le frasi e solo le incerte
  --aspetta DIR (trascrivi, correggi, interpreta): prima di ogni richiesta la Calliope vera
     deve tacere da 180 s (data dell'ultima riga di DIR/turni-*.jsonl, il suo registro)

DIR contiene riferimenti_whisper.tsv + rif/<cartella>__<stem>.wav (le 104 registrazioni con
riferimento sicuro) e riferimenti_dominio.tsv + dominio/<voce>__<id>.wav (sintetizza_dominio.py).
"""
import base64
import csv
import difflib
import json
import re
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np

PROMPT_WHISPER = "Conversazione con Calliope."

# Il vocabolario della casa sulla DGX il 05/10 (satelliti, schermi, persone registrate,
# entità esposte e aree di Home Assistant): quello che Calliope saprebbe in quel momento
SATELLITI = ["studio", "telefono di Dario"]
SCHERMI = ["studio di Dario"]
PERSONE = ["Dario"]
CASA = ["Bagno", "Bagno 1", "Bagno Taverna", "Camera", "Cameretta", "Cucina", "Lavanderia",
        "Scala", "Soggiorno", "Taverna", "Temperatura esterna", "Corridoio", "Sala", "Salone",
        "Gioco", "Esterno", "Camera da letto", "Bagno servizio", "Sala Box"]


def vocabolario():
    from calliope.stt_correzione import vocabolario_casa
    return vocabolario_casa(None, SATELLITI, SCHERMI, PERSONE, CASA)


# ─────────────────────────────── NORMALIZZAZIONE ───────────────────────────────
_U = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove",
      "dieci", "undici", "dodici", "tredici", "quattordici", "quindici", "sedici",
      "diciassette", "diciotto", "diciannove"]
_D = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta",
      "novanta"]


def num_it(n: int) -> str:
    if n < 20:
        return _U[n]
    if n < 100:
        d, u = divmod(n, 10)
        t = _D[d]
        if u in (1, 8):
            t = t[:-1]
        return t + (_U[u] if u else "")
    if n < 1000:
        c, r = divmod(n, 100)
        return ("cento" if c == 1 else _U[c] + "cento") + (num_it(r) if r else "")
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        return ("mille" if m == 1 else num_it(m) + "mila") + (num_it(r) if r else "")
    return str(n)


def norm(text: str) -> list[str]:
    t = text.lower().replace("’", "'")
    t = re.sub(r"(\d)[.:](\d)", r"\1 \2", t)
    t = re.sub(r"[^\w'àèéìòù ]", " ", t)
    t = t.replace("'", " ")
    out = []
    for w in t.split():
        out.append(num_it(int(w)) if w.isdigit() and len(w) < 7 else w)
    return out


def allinea(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    """Sostituzioni, cancellazioni, inserimenti (Levenshtein sulle parole)."""
    n, m = len(ref), len(hyp)
    d = [[(0, 0, 0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = (i, 0, i, 0)
    for j in range(1, m + 1):
        d[0][j] = (j, 0, 0, j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c, s, de, ins = d[i - 1][j - 1]
            if ref[i - 1] == hyp[j - 1]:
                best = (c, s, de, ins)
            else:
                best = (c + 1, s + 1, de, ins)
            c, s, de, ins = d[i - 1][j]
            if c + 1 < best[0]:
                best = (c + 1, s, de + 1, ins)
            c, s, de, ins = d[i][j - 1]
            if c + 1 < best[0]:
                best = (c + 1, s, de, ins + 1)
            d[i][j] = best
    return d[n][m][1:]


# ─────────────────────────────── INSIEMI ───────────────────────────────
def frasi(insieme: str, dati: Path) -> list[dict]:
    out = []
    if insieme == "rif":
        with open(dati / "riferimenti_whisper.tsv", encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r["sicurezza"] != "sicura":
                    continue
                out.append(dict(id=f"{r['cartella']}__{r['stem']}", conv=r["cartella"],
                                rif=r["riferimento"], quando=r["quando"],
                                wav=str(dati / "rif" / f"{r['cartella']}__{r['stem']}.wav")))
        out.sort(key=lambda x: x["id"])
    else:
        with open(dati / "riferimenti_dominio.tsv", encoding="utf-8") as f:
            righe = list(csv.DictReader(f, delimiter="\t"))
        for voce in sorted({p.name.split("__")[0] for p in (dati / "dominio").glob("*.wav")}):
            for r in righe:
                out.append(dict(id=f"{voce}__{r['id']}", conv=f"{voce}/{r['conversazione']}",
                                rif=r["riferimento"], quando="dominio",
                                wav=str(dati / "dominio" / f"{voce}__{r['id']}.wav")))
    return out


def leggi_wav(path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


# ─────────────────────────────── MOTORI ───────────────────────────────
def istruzione(storia: list[str], contesto: bool) -> str:
    base = ("Trascrivi esattamente, in italiano, ciò che dice la persona in questo audio. "
            "Rispondi solo con la trascrizione, senza commenti.")
    if not contesto:
        return base
    st = "\n".join(f"- {s}" for s in storia[-2:] if s) or "(nessuna)"
    return (base + " La persona parla a Calliope, un'assistente vocale di casa. Parole "
            "che possono comparire: " + ", ".join(vocabolario()) +
            f".\nFrasi precedenti della conversazione:\n{st}")


def motore(nome: str, args) -> callable:
    import httpx
    http = httpx.Client(timeout=120)
    if nome == "whispercpp":
        url = (args.get("url") or "http://127.0.0.1:8003/v1") + "/audio/transcriptions"

        def f(wav, storia):
            data = {"model": "whisper", "language": "it", "prompt": PROMPT_WHISPER,
                    "temperature": "0", "response_format": "verbose_json"}
            r = http.post(url, files={"file": ("f.wav", open(wav, "rb").read(), "audio/wav")},
                          data=data)
            r.raise_for_status()
            v = r.json()
            from calliope.stt_correzione import confidenza
            c = confidenza(v)
            from calliope.stt import unisci_righe
            return unisci_righe(v.get("text", "")).strip(), dict(
                min_parola=c.min_parola, logprob=c.logprob, no_speech=c.no_speech,
                incerte=c.incerte, deboli=c.deboli)
        return f
    if nome == "gemma_audio":
        url = (args.get("url") or "http://127.0.0.1:11434") + "/api/chat"
        mod = args.get("modello") or "gemma4:e4b-it-qat"

        def f(wav, storia):
            body = {"model": mod, "stream": False, "think": False, "keep_alive": "5m",
                    "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 120},
                    "messages": [{"role": "user", "content": istruzione(storia, args["contesto"]),
                                  "images": [base64.b64encode(open(wav, "rb").read()).decode()]}]}
            r = http.post(url, json=body)
            r.raise_for_status()
            return r.json()["message"]["content"].strip().strip("«»\""), {}
        return f
    if nome == "voxtral":
        url = (args.get("url") or "http://127.0.0.1:8010/v1") + "/audio/transcriptions"

        def f(wav, storia):
            data = {"model": args.get("modello") or "voxtral", "language": "it",
                    "temperature": "0", "response_format": "json"}
            if args["contesto"]:
                data["prompt"] = PROMPT_WHISPER
            r = http.post(url, files={"file": ("f.wav", open(wav, "rb").read(), "audio/wav")},
                          data=data)
            r.raise_for_status()
            return r.json().get("text", "").strip(), {}
        return f
    if nome == "voxtral_chat":
        url = (args.get("url") or "http://127.0.0.1:8010/v1") + "/chat/completions"

        def f(wav, storia):
            b64 = base64.b64encode(open(wav, "rb").read()).decode()
            body = {"model": args.get("modello") or "voxtral", "temperature": 0,
                    "max_tokens": 120, "messages": [{"role": "user", "content": [
                        {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
                        {"type": "text", "text": istruzione(storia, args["contesto"])}]}]}
            r = http.post(url, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip().strip("«»\""), {}
        return f
    if nome == "parakeet":
        import onnx_asr
        m = onnx_asr.load_model(args.get("modello") or "nemo-parakeet-tdt-0.6b-v3",
                               quantization=args.get("quant"))

        def f(wav, storia):
            return str(m.recognize(leggi_wav(wav), sample_rate=16000)).strip(), {}
        return f
    raise SystemExit(f"motore sconosciuto: {nome}")


def aspetta_calliope(o: dict, soglia: float = 180.0):
    """La GPU della voce vera ha la precedenza: con --aspetta <registro> si aspetta che
    l'ultimo turno della Calliope vera sia più vecchio di `soglia` secondi."""
    d = o.get("aspetta")
    if not d:
        return
    avvisato = False
    while True:
        files = list(Path(d).expanduser().glob("turni-*.jsonl"))
        fa = time.time() - max((f.stat().st_mtime for f in files), default=0)
        if fa >= soglia:
            return
        if not avvisato:
            print(f"[guardia] la Calliope vera ha parlato {fa:.0f} s fa: aspetto", flush=True)
            avvisato = True
        time.sleep(min(30.0, soglia - fa + 1))


def opzioni(argv: list[str]) -> dict:
    o = {"contesto": "--contesto" in argv}
    for i, a in enumerate(argv):
        if a.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            o[a[2:].replace("-", "_")] = argv[i + 1]
    return o


def trascrivi(o: dict):
    dati = Path(o["dati"])
    elenco = frasi(o["insieme"], dati)
    f = motore(o["motore"], o)
    aspetta_calliope(o)
    f(elenco[0]["wav"], [])                                     # riscaldamento
    storie: dict[str, list[str]] = {}
    with open(o["uscita"], "w", encoding="utf-8") as out:
        for fr in elenco:
            aspetta_calliope(o)
            storia = storie.setdefault(fr["conv"], [])
            t0 = time.perf_counter()
            testo, conf = f(fr["wav"], list(storia))
            t = time.perf_counter() - t0
            storia.append(testo)
            out.write(json.dumps(dict(fr, testo=testo, t=round(t, 4), conf=conf,
                                      storia=storia[-3:-1]), ensure_ascii=False) + "\n")
            out.flush()
    print("fatto", o["uscita"], len(elenco))


def correggi(o: dict):
    from calliope.stt_correzione import Confidenza, Correttore
    righe = [json.loads(x) for x in open(o["da"], encoding="utf-8")]
    cfg = SimpleNamespace(name="Calliope", llm_model="-", llm_backend=o["motore"],
                          stt_correzione_timeout_s=60.0)
    c = Correttore(cfg, motore=o["motore"], url=o["url"], modello=o["modello"])
    c.num_ctx = int(o.get("num_ctx") or 4096)
    ka = o.get("keep_alive") or "5m"
    c.keep_alive = int(ka) if re.fullmatch(r"-?\d+", ka) else ka
    # --senza-vocabolario: solo il nome e i tool, per vedere quanto conta la casa
    voc = vocabolario() if "--senza-vocabolario" not in sys.argv else ["Calliope"]
    storia_si = "--senza-storia" not in sys.argv
    aspetta_calliope(o)
    c.correggi("Accendi la luce.", None, voc, [])               # riscaldamento
    with open(o["uscita"], "w", encoding="utf-8") as out:
        for r in righe:
            aspetta_calliope(o)
            k = r.get("conf") or {}
            conf = Confidenza(k.get("min_parola", 1.0), k.get("logprob", 0.0),
                              k.get("no_speech", 0.0), k.get("incerte", []),
                              [tuple(x) for x in k.get("deboli", [])])
            # I file trascritti prima del 05/10 sera hanno gli a capo di whisper-server a
            # metà parola: si tolgono come fa adesso ServerTranscriber
            from calliope.stt import unisci_righe
            r["testo"] = unisci_righe(r["testo"])
            storia = [unisci_righe(x) for x in (r.get("storia") or [])]
            es = c.correggi(r["testo"], conf, voc, storia if storia_si else [])
            r.update(corretta=es.testo, cambiata=es.cambiata, proposta=es.proposta,
                     motivo=es.motivo, t_corr=es.ms / 1000)
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
    print("fatto", o["uscita"])


# ─────────────────────────────── VALUTAZIONE ───────────────────────────────
def parole_dominio() -> set[str]:
    voc = set()
    for w in vocabolario():
        voc.update(x for x in norm(w) if len(x) > 3)
    return voc - {"della", "cose", "dimmi", "sono"}


def metriche(righe: list[dict], campo="testo") -> dict:
    dom = parole_dominio()
    s = d = i = n = esatte = dom_tot = dom_err = parafrasi = e_nome = n_nome = 0
    tempi = []
    for r in righe:
        ref, hyp = norm(r["rif"]), norm(r.get(campo) or "")
        ss, dd, ii = allinea(ref, hyp)
        s, d, i, n = s + ss, d + dd, i + ii, n + len(ref)
        # Senza il nome: Parakeet lo perde quasi sempre, e la wake word acustica lo sente
        # da sé; resta da vedere com'è il resto della frase
        rn, hn = [w for w in ref if w != "calliope"], [w for w in hyp if w != "calliope"]
        e_nome, n_nome = e_nome + sum(allinea(rn, hn)), n_nome + len(rn)
        esatte += ss + dd + ii == 0
        for w in set(ref) & dom:
            dom_tot += 1
            dom_err += w not in hyp
        nuove = [w for w in hyp if w not in ref]
        if len(nuove) >= 2 and difflib.SequenceMatcher(
                a=" ".join(ref), b=" ".join(hyp)).ratio() < 0.6:
            parafrasi += 1
        tempi.append(r.get("t", 0) + (r.get("_tc", 0) if campo == "_finale" else 0))
    t = np.array(tempi)
    return dict(wer=(s + d + i) / max(n, 1), wer_senza_nome=e_nome / max(n_nome, 1),
                sub=s, canc=d, ins=i, esatte=esatte,
                frasi=len(righe), dom=f"{dom_tot - dom_err}/{dom_tot}", parafrasi=parafrasi,
                t_med=float(np.median(t)), t_p90=float(np.percentile(t, 90)))


def valuta(argv: list[str]):
    soglie = [float(argv[i + 1]) for i, a in enumerate(argv) if a == "--soglia"] or [0.5]
    tetto = next((float(argv[i + 1]) for i, a in enumerate(argv) if a == "--tetto"), None)
    utile = "--utile" in argv
    for p in [a for a in argv if a.endswith(".jsonl")]:
        righe = [json.loads(x) for x in open(p, encoding="utf-8")]
        if "--rivaluta" in argv:            # il controllo di adesso sulle proposte salvate
            from calliope.stt_correzione import accettabile
            for r in righe:
                if "proposta" in r:
                    ok = bool(r["proposta"]) and accettabile(r["testo"], r["proposta"])[0]
                    r["cambiata"], r["corretta"] = ok, (r["proposta"] if ok else r["testo"])
        for insieme in sorted({r["quando"] == "dominio" for r in righe}):
            parte = [r for r in righe if (r["quando"] == "dominio") == insieme]
            nome = f"{Path(p).stem} [{'dominio' if insieme else 'rif'}]"
            m = metriche(parte)
            print(f"{nome}: WER {m['wer']:.1%} (S{m['sub']} C{m['canc']} I{m['ins']}; senza "
                  f"il nome {m['wer_senza_nome']:.1%}), "
                  f"esatte {m['esatte']}/{m['frasi']}, dominio {m['dom']}, parafrasi "
                  f"{m['parafrasi']}, t {m['t_med']:.2f}/{m['t_p90']:.2f} s")
            if "corretta" not in parte[0]:
                continue
            for soglia in soglie:
                corr = rov = inv = cambiate = 0
                agg = []
                scadute = 0
                for r in parte:
                    sotto = minimo(r, utile) < soglia
                    cambia = sotto and r["cambiata"]
                    tc = r["t_corr"]
                    if tetto is not None and sotto and tc > tetto:
                        cambia, tc, scadute = False, tetto, scadute + 1
                    fin = r["corretta"] if cambia else r["testo"]
                    r["_finale"] = fin
                    r["_tc"] = tc if sotto else 0
                    if sotto:
                        agg.append(tc)
                    if fin != r["testo"]:
                        cambiate += 1
                        e0 = sum(allinea(norm(r["rif"]), norm(r["testo"])))
                        e1 = sum(allinea(norm(r["rif"]), norm(fin)))
                        corr += e1 < e0
                        rov += e1 > e0
                        inv += e1 == e0
                        print(f"   {'+' if e1 < e0 else '-' if e1 > e0 else '='} "
                              f"«{r['testo']}» → «{fin}»  (rif «{r['rif']}»)")
                m = metriche(parte, "_finale")
                a = np.array(agg or [0])
                print(f"  soglia {soglia}: WER {m['wer']:.1%}, esatte {m['esatte']}, dominio "
                      f"{m['dom']}; frasi al secondo passaggio {len(agg)}/{len(parte)}, "
                      f"cambiate {cambiate}: migliorate {corr}, peggiorate {rov}, pari {inv}; "
                      f"{f'scadute oltre {tetto} s {scadute}; ' if tetto is not None else ''}"
                      f"tempo aggiunto {np.median(a):.2f}/{np.percentile(a, 90):.2f} s "
                      f"(solo frasi incerte)")


def minimo(r: dict, utile: bool) -> float:
    """La parola più debole della riga: tutte, o senza il nome (`min_utile`)."""
    k = r.get("conf") or {}
    if not utile:
        return k.get("min_parola", 1.0)
    from calliope.stt_correzione import Confidenza, min_utile
    conf = Confidenza(k.get("min_parola", 1.0), incerte=k.get("incerte", []),
                      deboli=[tuple(x) for x in k.get("deboli", [])])
    return min_utile(conf, SimpleNamespace(wake_names=["Calliope"]))


# ─────────────────────────────── INTERPRETAZIONE (07/10) ───────────────────────────────
# Il confronto A/B/C della correzione della trascrizione. Il modello della voce, con le sue
# opzioni (stesso modello, num_ctx e keep_alive: niente ricarica), riceve la frase come la
# riceverebbe Calliope nelle varianti e invece di rispondere scrive come l'ha capita. Le
# varianti differiscono solo nella frase (A e B: Whisper; C: corretta) e nella riga delle
# parole incerte (solo B, il testo di Brain.nota_incerte); istruzione, storia, opzioni uguali.
# Non è la risposta vera (tool, azioni): è quanto il modello capisce, che la prova
# end-to-end misura poi a voce.
ISTRUZIONE_INTERPRETA = (
    "Sei Calliope, un'assistente vocale di casa. Le frasi della persona ti arrivano dal "
    "riconoscimento vocale. In questa prova non rispondere alla persona: scrivi solo, in JSON, "
    "la sua richiesta come l'hai capita tu (\"capito\", con le parole della persona) e "
    "\"chiedi\": true se, per rispondere, dovresti prima chiederle cosa intendeva.")
SCHEMA_INTERPRETA = {"type": "object", "properties": {"capito": {"type": "string"},
                                                      "chiedi": {"type": "boolean"}},
                     "required": ["capito", "chiedi"]}


def interpreta(o: dict):
    import httpx
    from calliope.brain import nota_incerte
    from calliope.stt import unisci_righe
    from calliope.stt_correzione import Confidenza, parole_incerte
    var = o["variante"].upper()
    soglia = float(o.get("soglia") or 0.4)
    tetto = float(o["tetto"]) if o.get("tetto") else None
    cfg = SimpleNamespace(stt_correzione_soglia=soglia, wake_names=["Calliope"])
    ka = o.get("keep_alive") or "5m"
    ka = int(ka) if re.fullmatch(r"-?\d+", ka) else ka
    http = httpx.Client(timeout=120)
    url = o["url"].rstrip("/") + "/api/chat"

    def chiedi(testo, storia, nota):
        msgs = [{"role": "system", "content": ISTRUZIONE_INTERPRETA}]
        if storia:
            msgs.append({"role": "system", "content": "Frasi precedenti della persona: "
                         + " / ".join(f"«{x}»" for x in storia)})
        if nota:
            msgs.append({"role": "system", "content": "Dati del turno: " + nota})
        msgs.append({"role": "user", "content": testo})
        body = {"model": o["modello"], "stream": False, "think": False, "keep_alive": ka,
                "format": SCHEMA_INTERPRETA, "messages": msgs,
                "options": {"temperature": 0, "num_predict": 150,
                            "num_ctx": int(o.get("num_ctx") or 4096)}}
        t0 = time.perf_counter()
        r = http.post(url, json=body)
        r.raise_for_status()
        dato = json.loads(r.json()["message"]["content"] or "{}")
        return (str(dato.get("capito") or ""), bool(dato.get("chiedi")),
                round(time.perf_counter() - t0, 3))

    righe = [json.loads(x) for x in open(o["da"], encoding="utf-8")]
    aspetta_calliope(o)
    chiedi("Accendi la luce.", [], "")                          # riscaldamento
    with open(o["uscita"], "w", encoding="utf-8") as out:
        for r in righe:
            aspetta_calliope(o)
            r["testo"] = unisci_righe(r["testo"])
            storia = [unisci_righe(x) for x in (r.get("storia") or [])][-2:]
            k = r.get("conf") or {}
            conf = Confidenza(k.get("min_parola", 1.0), incerte=k.get("incerte", []),
                              deboli=[tuple(x) for x in k.get("deboli", [])])
            frase, nota = r["testo"], ""
            if var == "B":
                r["incerte"] = parole_incerte(conf, cfg, frase)
                nota = nota_incerte(r["incerte"])
            elif var == "C" and "corretta" in r:
                sotto = minimo(r, True) < soglia
                ok = sotto and r["cambiata"] and (tetto is None or r["t_corr"] <= tetto)
                frase = r["corretta"] if ok else r["testo"]
            r["frase_al_modello"], r["nota"] = frase, nota
            r["capito"], r["chiedi"], r["t_int"] = chiedi(frase, storia, nota)
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
    print("fatto", o["uscita"])


SISTEMA_CAPISCI = ("Sei Calliope, un'assistente vocale di casa: rispondi in italiano, in "
                   "una o due frasi brevi, senza elenchi.")


def capisci(o: dict):
    """B2: come Calliope con stt_incerte_riscrivi. Il nome in testa si toglie (Calliope riceve
    la frase senza, wake word tolta) e si rimette davanti alla frase finale per la WER."""
    import httpx
    from calliope.brain import CapitoHold, nota_incerte
    from calliope.stt import unisci_righe
    from calliope.stt_correzione import Confidenza, accettabile, parole_incerte
    soglia = float(o.get("soglia") or 0.4)
    cfg = SimpleNamespace(stt_correzione_soglia=soglia, wake_names=["Calliope"])
    ka = o.get("keep_alive") or "5m"
    ka = int(ka) if re.fullmatch(r"-?\d+", ka) else ka
    http = httpx.Client(timeout=120)
    url = o["url"].rstrip("/") + "/api/chat"
    nome_re = re.compile(r"^\s*[«\"]?\s*calliope\s*[,.!:]?\s*", re.I)

    def chiedi(testo, nota):
        body = {"model": o["modello"], "stream": True, "think": False, "keep_alive": ka,
                "messages": [{"role": "system", "content": SISTEMA_CAPISCI},
                             {"role": "system", "content": "Dati del turno: " + nota},
                             {"role": "user", "content": testo}],
                "options": {"temperature": 0, "num_predict": 120,
                            "num_ctx": int(o.get("num_ctx") or 4096)}}
        hold = CapitoHold(True)
        t0 = time.perf_counter()
        t_riga = None
        detto = ""
        with http.stream("POST", url, json=body) as r:
            r.raise_for_status()
            for riga in r.iter_lines():
                if not riga:
                    continue
                pezzo = (json.loads(riga).get("message") or {}).get("content") or ""
                fuori = hold.feed(pezzo)
                if t_riga is None and (hold.done or fuori):
                    t_riga = time.perf_counter() - t0
                detto += fuori
        detto += hold.flush()
        return hold.capito, detto.strip(), round(t_riga or (time.perf_counter() - t0), 3)

    righe = [json.loads(x) for x in open(o["da"], encoding="utf-8")]
    aspetta_calliope(o)
    chiedi("Accendi la luce.", nota_incerte(["luce"], True))      # riscaldamento
    with open(o["uscita"], "w", encoding="utf-8") as out:
        for r in righe:
            r["testo"] = unisci_righe(r["testo"])
            k = r.get("conf") or {}
            conf = Confidenza(k.get("min_parola", 1.0), incerte=k.get("incerte", []),
                              deboli=[tuple(x) for x in k.get("deboli", [])])
            m = nome_re.match(r["testo"])
            testa, resto = (r["testo"][:m.end()], r["testo"][m.end():]) if m else ("", r["testo"])
            incerte = parole_incerte(conf, cfg, resto) if resto.strip() else []
            r.update(corretta=r["testo"], cambiata=False, proposta="", motivo="", t_corr=0.0,
                     incerte=incerte)
            if incerte:
                aspetta_calliope(o)
                capito, detto, t_riga = chiedi(resto, nota_incerte(incerte, True))
                r.update(proposta=capito or "", risposta=detto, t_corr=t_riga,
                         scritta=capito is not None)
                if capito:
                    dopo = nome_re.sub("", capito.strip().strip("«»\"")) or capito
                    ok, motivo = accettabile(resto, dopo)
                    r["motivo"] = motivo
                    if ok:
                        r.update(corretta=(testa + dopo).strip(), cambiata=True)
                else:
                    r["motivo"] = "nessuna riga"
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
    print("fatto", o["uscita"])


def _senza_nome(ws: list[str]) -> list[str]:
    return [w for w in ws if w != "calliope"]


def confronta(argv: list[str]):
    """Per ogni file (una variante): parole sbagliate da Whisper (nel riferimento e non nella
    trascrizione) che tornano in ciò che il modello ha capito; frasi con errori capite tutte;
    parole giuste di Whisper perse nella frase capita (parafrasi o «correzioni» sbagliate);
    domande di chiarimento con e senza errori; WER di ciò che ha capito."""
    file = [a for a in argv if a.endswith(".jsonl")]
    for sottoinsieme in ("tutte", "incerte"):
        print(f"\n== frasi: {sottoinsieme} ==")
        for p in file:
            righe = [json.loads(x) for x in open(p, encoding="utf-8")]
            for dominio in sorted({r["quando"] == "dominio" for r in righe}):
                parte = [r for r in righe if (r["quando"] == "dominio") == dominio]
                if sottoinsieme == "incerte":
                    parte = [r for r in parte if minimo(r, True) < 0.4]
                err = rec = frasi_err = capite = perse = chiede_err = chiede_ok = 0
                e_wer = n_wer = 0
                for r in parte:
                    ref = _senza_nome(norm(r["rif"]))
                    hyp = set(_senza_nome(norm(r["testo"])))
                    cap = set(_senza_nome(norm(r["capito"])))
                    sbagliate = [w for w in set(ref) if w not in hyp]
                    err += len(sbagliate)
                    tornate = sum(w in cap for w in sbagliate)
                    rec += tornate
                    if sbagliate:
                        frasi_err += 1
                        capite += tornate == len(sbagliate)
                        chiede_err += r["chiedi"]
                    else:
                        chiede_ok += r["chiedi"]
                    perse += sum(1 for w in set(ref) & hyp if w not in cap and len(w) > 3)
                    e_wer += sum(allinea(ref, _senza_nome(norm(r["capito"]))))
                    n_wer += len(ref)
                t = np.array([r.get("t_int", 0) for r in parte] or [0])
                print(f"{Path(p).stem} [{'dominio' if dominio else 'rif'}] {len(parte)} frasi: "
                      f"parole sbagliate tornate {rec}/{err}, frasi con errori capite "
                      f"{capite}/{frasi_err}, parole giuste perse {perse}, chiede "
                      f"{chiede_err} (con errori) e {chiede_ok} (senza), WER del capito "
                      f"{e_wer / max(n_wer, 1):.1%}, t {np.median(t):.2f}/"
                      f"{np.percentile(t, 90):.2f} s")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd, argv = sys.argv[1], sys.argv[2:]
    if cmd == "trascrivi":
        trascrivi(opzioni(argv))
    elif cmd == "correggi":
        correggi(opzioni(argv))
    elif cmd == "valuta":
        valuta(argv)
    elif cmd == "interpreta":
        interpreta(opzioni(argv))
    elif cmd == "confronta":
        confronta(argv)
    elif cmd == "capisci":
        capisci(opzioni(argv))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
