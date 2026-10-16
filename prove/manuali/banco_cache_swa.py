"""Banco del motore: quanto si può «riavvolgere» la cache del prefisso di Ollama con gemma4
(16/10/2026, issue #95; sezione «La cache del prefisso e la finestra scorrevole» di
docs/aree/contesto-conversazione.md).

Gemma 4 ha strati ad attenzione con finestra scorrevole (SWA): Ollama (motore di llama.cpp) ne
tiene solo gli ultimi `n_swa + n_ubatch` token e, per tornare più indietro, i *context checkpoint*,
creati alla fine di ogni lettura del prompt. Se la richiesta nuova differisce da quella di prima a
più di ~n_ubatch (512) token dalla fine, i checkpoint dopo il punto di differenza si cancellano e si
riparte dal primo rimasto: si rilegge tutta la storia («ripresi» fermi a un punto fisso).

Il banco simula una conversazione come quella di Calliope: un prompt di sistema lungo, poi
`--turni` turni; in ogni richiesta, subito prima della domanda, un blocco «dati del turno» di
`--dati` caratteri che alla richiesta dopo sparisce (come i dati del turno di Brain) e, con
`--stabili`, un blocco che resta:

- `--modo vecchio`: anche il blocco `--stabili` sta nei dati del turno e sparisce (Calliope fino
  al 15/10: ricordi, avvisi, riassunto della stanza a ogni turno);
- `--modo nuovo`: il blocco `--stabili` entra nella storia al primo turno e resta lì, uguale
  (Calliope dal 16/10, `dati_stabili_in_storia`).

Per ogni turno: token del prompt (`prompt_eval_count`), ripresi dalla cache
(`prompt_eval_cached_count`), riletti (prompt meno ripresi) e la lettura in ms. Con `--serie`
più valori di `--dati` uno dopo l'altro (la serie dell'analisi del 16/10: 600,2000,4000,6000
caratteri ≈ 150/500/1 000/1 500 token). I token veri del
blocco si misurano prima, una volta, con due richieste brevi senza cache.

Da usare su un **Ollama di prova** su un'altra porta, mai su quello della voce (sposta la sua
cache), con lo stesso `OLLAMA_NUM_PARALLEL` del servizio e `OLLAMA_DEBUG=1` per leggere nel log
«restored context checkpoint» e «erased invalidated context checkpoint». Portatile (PowerShell):

    $env:OLLAMA_HOST="127.0.0.1:11500"; $env:OLLAMA_NUM_PARALLEL="2"; $env:OLLAMA_DEBUG="1"
    ollama serve 2> $env:TEMP\\ollama-prova.log      # in un'altra finestra; poi chiuderlo per PID
    python prove\\manuali\\banco_cache_swa.py --url http://127.0.0.1:11500 --modello gemma4:e4b-it-qat --serie 600,2000,4000,6000
    python prove\\manuali\\banco_cache_swa.py --url http://127.0.0.1:11500 --modello gemma4:e4b-it-qat --dati 900 --stabili 3000 --modo vecchio,nuovo

DGX (26B, un Ollama di prova su un'altra porta con `OLLAMA_MODELS` uguale; non fermare quello del
servizio):

    OLLAMA_HOST=127.0.0.1:11500 OLLAMA_NUM_PARALLEL=2 OLLAMA_DEBUG=1 nohup ollama serve > /tmp/ollama-prova.log 2>&1 &
    V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
    $V/.venv/bin/python $V/prove/manuali/banco_cache_swa.py --url http://127.0.0.1:11500 \\
        --modello gemma4:26b-a4b-it-qat --sistema 60000 --serie 600,2000,4000,6000
    kill <pid>   # quello stampato da $!

Solo libreria standard. Non cambia la configurazione di nessuno.
"""

import argparse
import json
import statistics
import time
import urllib.request

PAROLE = ("la casa il giardino una lampada accesa il pomeriggio di ottobre la cucina profuma di "
          "pane mentre fuori piove piano sul tetto e i bambini leggono un libro di storie antiche "
          "sul divano del soggiorno vicino alla finestra che guarda il cortile con gli alberi "
          "gialli e rossi").split()

DOMANDE = ["Che tempo fa domani?", "Raccontami una cosa curiosa sui gatti.",
           "Quanto fa diciassette per tre?", "Mi consigli un libro per l'autunno?",
           "Come si fa il pane in casa?", "Cosa vuol dire resilienza?",
           "Dimmi un proverbio sulla pioggia.", "Qual è la capitale del Portogallo?",
           "Perché le foglie cambiano colore?", "Come si dice grazie in tedesco?",
           "Mi ricordi di bere acqua?", "Qual è il fiume più lungo d'Italia?"]


def testo(caratteri: int, seme: int) -> str:
    """Testo italiano finto di `caratteri` caratteri, diverso per `seme`."""
    out, i = [], seme * 7
    n = 0
    while n < caratteri:
        w = PAROLE[i % len(PAROLE)]
        if i % 13 == 0:
            w = f"{w}{seme % 97}"
        out.append(w)
        n += len(w) + 1
        i += 1 + (seme % 3)
    return " ".join(out)[:caratteri]


def chat(url, modello, messaggi, num_ctx, predict=24):
    corpo = {"model": modello, "messages": messaggi, "stream": False, "think": False,
             "keep_alive": "10m",
             "options": {"num_ctx": num_ctx, "num_predict": predict, "temperature": 0,
                         "seed": 1}}
    req = urllib.request.Request(url.rstrip("/") + "/api/chat",
                                 data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def token_veri(url, modello, num_ctx, caratteri: int) -> int:
    """I token veri di un blocco di `caratteri` caratteri: due richieste senza cache (un numero
    diverso in testa), con e senza il blocco."""
    nonce = str(time.time_ns())
    base = [{"role": "system", "content": f"[{nonce}] Rispondi breve."},
            {"role": "user", "content": "Ciao."}]
    con = [base[0], {"role": "system", "content": testo(caratteri, 999)}, base[1]]
    a = chat(url, modello, base, num_ctx, predict=1).get("prompt_eval_count") or 0
    con[0] = {"role": "system", "content": f"[{nonce}x] Rispondi breve."}
    b = chat(url, modello, con, num_ctx, predict=1).get("prompt_eval_count") or 0
    return max(0, b - a)


def giro(url, modello, num_ctx, sistema: int, dati: int, stabili: int, modo: str, turni: int,
         seme: int) -> list[dict]:
    nonce = f"[giro {time.time_ns()}] "
    sys_msg = {"role": "system", "content": nonce + "Sei un'assistente vocale. Rispondi in una "
               "frase. " + testo(sistema, seme)}
    storia: list[dict] = []
    stab = {"role": "system", "content": "Dati che restano: " + testo(stabili, seme + 1)} \
        if stabili else None
    righe = []
    for k in range(turni):
        domanda = {"role": "user", "content": DOMANDE[(k + seme) % len(DOMANDE)]}
        volatili = [{"role": "system", "content": f"Dati del turno {k}: "
                     + testo(dati, seme * 31 + k)}] if dati else []
        if stab is not None and modo == "vecchio":
            volatili = [stab] + volatili
        nuovi = [stab] if (stab is not None and modo == "nuovo" and k == 0) else []
        msgs = [sys_msg] + storia + nuovi + volatili + [domanda]
        t0 = time.perf_counter()
        r = chat(url, modello, msgs, num_ctx)
        dt = time.perf_counter() - t0
        prompt = r.get("prompt_eval_count") or 0
        cached = r.get("prompt_eval_cached_count")
        risposta = (r.get("message") or {}).get("content") or "Va bene."
        # `prompt_eval_count` è il prompt intero; `prompt_eval_cached_count` la parte trovata in
        # cache (Ollama 0.35 e 0.40): i riletti sono la differenza
        ripresi = cached if isinstance(cached, int) else None
        righe.append({"turno": k + 1, "prompt": prompt, "riletti": prompt - (ripresi or 0),
                      "ripresi": ripresi,
                      "lettura_ms": round((r.get("prompt_eval_duration") or 0) / 1e6),
                      "s": round(dt, 2)})
        storia += nuovi + [domanda, {"role": "assistant", "content": risposta}]
    return righe


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:11500")
    ap.add_argument("--modello", default="gemma4:e4b-it-qat")
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--sistema", type=int, default=9000, help="caratteri del prompt di sistema")
    ap.add_argument("--dati", type=int, default=600, help="caratteri dei dati del turno")
    ap.add_argument("--serie", default="", help="più valori di --dati, separati da virgole")
    ap.add_argument("--stabili", type=int, default=0, help="caratteri dei dati che cambiano di rado")
    ap.add_argument("--modo", default="vecchio", help="vecchio, nuovo o entrambi (vecchio,nuovo)")
    ap.add_argument("--turni", type=int, default=6)
    a = ap.parse_args()
    serie = [int(x) for x in a.serie.split(",") if x.strip()] or [a.dati]
    modi = [m.strip() for m in a.modo.split(",") if m.strip()]
    print(f"modello {a.modello}, num_ctx {a.num_ctx}, sistema {a.sistema} caratteri, "
          f"stabili {a.stabili}", flush=True)
    for i, d in enumerate(serie):
        veri = token_veri(a.url, a.modello, a.num_ctx, d) if d else 0
        for modo in modi:
            righe = giro(a.url, a.modello, a.num_ctx, a.sistema, d, a.stabili, modo, a.turni,
                         seme=i * 10 + len(modo))
            print(f"\n== dati {d} caratteri (~{veri} token veri), modo {modo}", flush=True)
            for r in righe:
                tot = r["prompt"]
                print(f"  turno {r['turno']}: riletti {r['riletti']:6d}  ripresi "
                      f"{r['ripresi'] if r['ripresi'] is not None else '—':>6}  prompt "
                      f"{tot if tot is not None else '—':>6}  lettura {r['lettura_ms']} ms",
                      flush=True)
            dopo = [r["riletti"] for r in righe[1:]]
            if dopo:
                print(f"  riletti dal secondo turno: mediana {statistics.median(dopo):.0f}, "
                      f"massimo {max(dopo)}", flush=True)


if __name__ == "__main__":
    main()
