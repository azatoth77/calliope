"""Misure della preselezione dei tool System 1 sulla DGX (15/10/2026,
calliope/system1/preselezione.py; progetto docs/ricerche/2026-10-15-preselezione-tool.md).

Da lanciare **sulla DGX**, nella cartella dei dati, con l'interprete di Calliope:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/preselezione_dgx.py --registro [--giorni 14] \\
        && $V/.venv/bin/python $V/prove/manuali/preselezione_dgx.py --latenza [--limite 24]

**--registro** (sola lettura, nessun modello): rigioca il decisore sui turni veri del registro
(le frasi degli adulti, decisione 0028) con gli schemi del registro completo delle prove; la
frase di prima e i tool usati vengono dai turni precedenti della stessa voce entro
`storia_inattiva_s`. Stampa, **solo numeri e nomi di tool**: richiamo sui turni con tool
(l'insieme scelto contiene tutti i tool usati), quota a «nucleo», i tool mancati per nome, il
richiamo della variante «nucleo + i più vicini», i cambi d'insieme fra turni vicini della
stessa persona (ognuno rompe la cache del prefisso), per margine (griglia) e codifica.
Dal 16/10 (issue #25) è il modo di rimisurare la preselezione: l'ombra nel ciclo è tolta e
non ci sono più campi `preselezione_*` nella configurazione (il nucleo si prova con
`--nucleo ora_attuale,calcola,…`).

**--latenza** (usa il modello della voce su Ollama: **a Calliope ferma o inattiva**, perché
ogni richiesta sposta la cache del prefisso della voce; al turno dopo Calliope la rifà da sé,
una volta). Il prompt di sistema vero (Brain con il registro completo delle prove), una storia
finta di `--storia` scambi, `num_ctx` uguale a quello del modello già caricato (niente
ricaricamento: `/api/ps`), think spento. Per ogni frase del banco
(prove/banco_preselezione.py) quattro richieste di fila, nell'ordine che avrebbe un turno vero:

1. «tutti, caldo»: l'elenco di oggi, cache del prefisso calda (la richiesta prima è uguale);
2. «nucleo, cambio»: l'insieme piccolo subito dopo (i tool in testa: si rilegge tutto?);
3. «nucleo, caldo»: lo stesso insieme piccolo con la frase dopo;
4. «tutti, ritorno»: di nuovo tutti (Ollama tiene la cache di prima in un altro posto?).

Per ognuna: tempo al primo pezzo (testo o chiamata), token del prompt e quanti in cache, ms di
lettura, ms del server fuori dal modello (totale − caricamento − lettura − generazione: il
lavoro del server sul prompt, che la cache non nasconde) e il tool chiamato (giusto o no col
banco). Alla fine mediane per scenario. Non cambia la configurazione né i file di nessuno.
"""

import argparse
import datetime
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope.system1 import preselezione as ps  # noqa: E402


def _schemi_completi():
    from prove.prova_politica import registro_completo
    return registro_completo()


# ─────────────────────────────── --registro ───────────────────────────────
def _quando(t):
    try:
        return datetime.datetime.fromisoformat(str(t.get("inizio"))).timestamp()
    except (TypeError, ValueError):
        return None


def _chi(t):
    v = t.get("voce") if isinstance(t.get("voce"), dict) else {}
    return v.get("id") or v.get("nome")


def richieste_dal_registro(turni, pausa_s: float):
    """(Richiesta, tool usati, chi) per ogni risposta con le parole, con la frase di prima e i
    tool usati dalla stessa persona entro `pausa_s` (la conversazione di Brain)."""
    out, ultimo = [], {}
    for t in sorted(turni, key=lambda x: str(x.get("inizio") or "")):
        testo = t.get("testo")
        if t.get("esito") != "risposta" or not isinstance(testo, str) or not testo.strip():
            continue
        chi, q = _chi(t), _quando(t)
        prec = ultimo.get(chi)
        prima, recenti = None, ()
        if prec and q is not None and prec["q"] is not None and q - prec["q"] <= pausa_s:
            prima, recenti = prec["testo"], tuple(prec["tool"])
        usati = [x.get("nome") for x in t.get("tool") or () if isinstance(x, dict)
                 and x.get("nome") and not x.get("sconosciuto")]
        out.append((ps.Richiesta(testo=testo, prima=prima, recenti=recenti), usati, chi))
        tool = (list(recenti) if prima else []) + [u for u in usati if u not in recenti]
        ultimo[chi] = {"q": q, "testo": testo, "tool": tool}
    return out


def registro(args, cfg):
    from calliope import latenza
    turni = latenza.leggi(cfg.turn_log_dir, args.giorni)
    reg = _schemi_completi()
    rr = richieste_dal_registro(turni, float(getattr(cfg, "storia_inattiva_s", 300) or 300))
    print(f"{len(rr)} risposte con le parole negli ultimi {args.giorni} giorni, "
          f"{sum(1 for _, u, _ in rr if u)} con tool; {len(reg._tools)} schemi")
    codifiche = ["parole"] + (["embedding"] if args.embedding else [])
    for cod in codifiche:
        if cod == "embedding":
            from calliope.conversazioni import Embedder
            url = cfg.conversazioni_embedding_url or cfg.llm_native_url
            c = ps.CodificaEmbedding(Embedder(url, cfg.conversazioni_embedding, cpu=True))
        else:
            c = ps.CodificaParole()
        p = ps.Preselettore(c, nucleo=args.nucleo or None)
        p.aggiorna(reg.all_schemas())
        # I punteggi una volta per frase, poi la griglia del margine
        righe, ms = [], []
        for r, usati, chi in rr:
            p.margine = 99.0       # niente «nucleo» qui: serve solo il calcolo
            s = p.decide(r)
            ms.append(s.ms)
            righe.append((r, usati, chi, s))
        ms.sort()
        print(f"\nCodifica {cod}: decisore p50 {ms[len(ms) // 2] if ms else '—'} ms, "
              f"p90 {ms[int(.9 * len(ms))] if ms else '—'} ms")
        for m in args.margini:
            n = nuc = con = presi = presi_top = cambi = 0
            mancati, prec = {}, {}
            for r, usati, chi, s in righe:
                strutt = (any(x in p._nomi and x not in p.nucleo for x in r.recenti)
                          or r.foto)
                insieme = (ps.TUTTI if strutt or s.fuori_max >= s.nucleo_max - m
                           else ps.NUCLEO_SCELTA)
                nomi = set(p._nomi) if insieme == ps.TUTTI else set(p.nucleo)
                n += 1
                nuc += insieme == ps.NUCLEO_SCELTA
                if chi in prec and prec[chi] != insieme and r.prima:
                    cambi += 1
                prec[chi] = insieme
                if usati:
                    con += 1
                    mm = [u for u in usati if u not in nomi]
                    presi += not mm
                    presi_top += all(u in p.nucleo or u in s.top for u in usati)
                    for u in mm:
                        mancati[u] = mancati.get(u, 0) + 1
            top = sorted(mancati.items(), key=lambda kv: -kv[1])[:6]
            print(f"  margine {m:+.2f}: «nucleo» {nuc}/{n} ({100 * nuc / max(1, n):.0f} %), "
                  f"richiamo {presi}/{con} ({100 * presi / max(1, con):.1f} %), "
                  f"variante dei {ps.TOP} più vicini {100 * presi_top / max(1, con):.1f} %, "
                  f"cambi {cambi}" + (f"; mancati {top}" if top else ""))


# ─────────────────────────────── --latenza ───────────────────────────────
def _ctx_caricato(http, url, modello):
    try:
        for m in http.get(url + "/api/ps").json().get("models") or ():
            if m.get("name") == modello or m.get("model") == modello:
                return m.get("context_length")
    except Exception:  # noqa: BLE001
        pass
    return None


def _storia(n):
    temi = ["la storia di Roma", "come si fa il pane", "i pianeti", "le api", "il violino",
            "la Sicilia", "i dinosauri", "la pizza", "il calcio", "i vulcani", "la musica jazz",
            "il mare"]
    out = []
    for i in range(n):
        tema = temi[i % len(temi)]
        out += [{"role": "user", "content": f"Raccontami qualcosa su {tema}."},
                {"role": "assistant", "content": f"Su {tema} ci sarebbe molto da dire: ti racconto "
                 f"la cosa che mi piace di più, in breve, e poi se vuoi andiamo avanti. " * 2}]
    return out


def chiedi(http, url, modello, msgs, tools, num_ctx, temperatura):
    body = {"model": modello, "messages": msgs, "stream": True, "think": False,
            "keep_alive": "30m",
            "options": {"num_ctx": num_ctx, "temperature": temperatura, "num_predict": 96}}
    if tools:
        body["tools"] = tools
    t0 = time.perf_counter()
    primo, chiamate, fine = None, [], {}
    with http.stream("POST", url + "/api/chat", json=body, timeout=300) as r:
        for riga in r.iter_lines():
            if not riga.strip():
                continue
            o = json.loads(riga)
            m = o.get("message") or {}
            if primo is None and (m.get("content") or m.get("tool_calls")):
                primo = time.perf_counter() - t0
            for c in m.get("tool_calls") or ():
                chiamate.append((c.get("function") or {}).get("name"))
            if o.get("done"):
                fine = o
    ms = lambda k: (fine.get(k) or 0) / 1e6  # noqa: E731
    fuori = ms("total_duration") - ms("load_duration") - ms("prompt_eval_duration") \
        - ms("eval_duration")
    return {"primo_s": round(primo or (time.perf_counter() - t0), 3),
            "prompt": fine.get("prompt_eval_count"),
            "in_cache": fine.get("prompt_eval_cached_count"),
            "lettura_ms": round(ms("prompt_eval_duration")), "fuori_ms": round(fuori),
            "carico_ms": round(ms("load_duration")), "tool": chiamate}


def latenza(args, cfg):
    import httpx
    from calliope.brain import Brain
    from calliope.config import apply_llm_profile
    from calliope.tools.spec import ToolContext
    from prove.banco_preselezione import CASI
    apply_llm_profile(cfg)
    url, modello = cfg.llm_native_url.rstrip("/"), cfg.llm_model
    http = httpx.Client(timeout=httpx.Timeout(300, connect=5))
    num_ctx = _ctx_caricato(http, url, modello)
    if not num_ctx:
        print(f"Il modello {modello} non è caricato su Ollama: si misura col num_ctx che "
              f"carica Calliope, non a caso. Avvia Calliope (o aspetta un turno) e riprova.")
        return 77
    reg = _schemi_completi()
    brain = Brain(cfg, reg, ToolContext(cfg=cfg, speakers=None, speaker_ctx=None, speaker=None))
    sistema = brain._system_messages()
    tutti = brain.schemi()
    p = ps.Preselettore()
    p.aggiorna(tutti)
    nucleo = [s for s in tutti if s["function"]["name"] in p.nucleo]
    storia = _storia(args.storia)
    print(f"Modello {modello}, num_ctx {num_ctx}, {len(tutti)} schemi contro {len(nucleo)} del "
          f"nucleo, storia di {args.storia} scambi")
    casi = [c for c in CASI if not c[1] or any(a in p.nucleo for a in c[1])][:args.limite]
    risultati = {k: [] for k in ("tutti_caldo", "nucleo_cambio", "nucleo_caldo", "tutti_ritorno")}
    giusti = {k: 0 for k in risultati}
    avvisato = False
    for i, (frase, acc, prima, rec) in enumerate(casi):
        dopo = casi[(i + 1) % len(casi)][0]
        q = lambda f: sistema + storia + [{"role": "user", "content": f}]  # noqa: E731
        chiedi(http, url, modello, q(frase), tutti, num_ctx, cfg.llm_temperature)   # scalda
        for nome, f, tools in (("tutti_caldo", frase, tutti), ("nucleo_cambio", frase, nucleo),
                               ("nucleo_caldo", dopo, nucleo), ("tutti_ritorno", dopo, tutti)):
            r = chiedi(http, url, modello, q(f), tools, num_ctx, cfg.llm_temperature)
            # Un prompt tagliato dal server (sul portatile il 15/10: 8195 token con num_ctx
            # 16384, la finestra divisa fra due posti) falsa tutto: lo si dice
            stima = len(json.dumps(q(f) + tools, ensure_ascii=False)) / 3.5
            if isinstance(r["prompt"], int) and r["prompt"] < 0.6 * stima and not avvisato:
                avvisato = True
                print(f"  ATTENZIONE: il server ha letto {r['prompt']} token su ~{stima:.0f} "
                      f"stimati: il prompt è tagliato (finestra per posto più piccola di "
                      f"num_ctx?), le misure non valgono")
            risultati[nome].append(r)
            accettati = acc if f == frase else casi[(i + 1) % len(casi)][1]
            ok = (not accettati and not r["tool"]) or any(a in r["tool"] for a in accettati)
            giusti[nome] += ok
        print(f"  {i + 1}/{len(casi)} " + "  ".join(
            f"{k} {v[-1]['primo_s']:.2f}s ({v[-1]['in_cache']}/{v[-1]['prompt']})"
            for k, v in risultati.items()), flush=True)
    print("\nScenario        primo pezzo (mediana / p90)  prompt  in cache  lettura ms  "
          "fuori dal modello ms  tool giusto")
    for k, v in risultati.items():
        if not v:
            continue
        primi = sorted(x["primo_s"] for x in v)
        med = lambda key: statistics.median([x[key] or 0 for x in v])  # noqa: E731
        print(f"{k:15s} {statistics.median(primi):6.2f} / {primi[int(.9 * len(primi))]:5.2f} s"
              f"      {med('prompt'):6.0f}  {med('in_cache'):8.0f}  {med('lettura_ms'):10.0f}  "
              f"{med('fuori_ms'):20.0f}  {giusti[k]}/{len(v)}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"modello": modello, "num_ctx": num_ctx, "risultati": risultati}, f)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--registro", action="store_true")
    ap.add_argument("--latenza", action="store_true")
    ap.add_argument("--giorni", type=int, default=14)
    ap.add_argument("--margini", type=lambda s: [float(x) for x in s.split(",")],
                    default=[0.0, 0.05, 0.10, 0.15, 0.20])
    ap.add_argument("--embedding", action="store_true",
                    help="anche la codifica «embedding» (carica il modello di embedding)")
    # Il nucleo da provare (nomi di tool separati da virgole); vuoto = preselezione.NUCLEO.
    # Fino al 15/10 veniva da `preselezione_nucleo` della configurazione, tolto il 16/10 (#25)
    ap.add_argument("--nucleo", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                    default=[])
    ap.add_argument("--limite", type=int, default=24)
    ap.add_argument("--storia", type=int, default=10)
    ap.add_argument("--json")
    args = ap.parse_args()
    from calliope.config import load_config
    cfg = load_config()
    if not (args.registro or args.latenza):
        ap.print_help()
        return 2
    if args.registro:
        registro(args, cfg)
    if args.latenza:
        return latenza(args, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
