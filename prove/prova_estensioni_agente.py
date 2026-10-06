"""Estensioni scritte dall'agente VERO (04/10/2026): sulla DGX, con la configurazione di
Calliope (agente = qwen3.6 su vLLM) e il container vero della sandbox. Non tocca i dati del
servizio: estensioni, sandbox e risultati vanno in una cartella temporanea.

Dal 05/10 con `--compito "<testo>"` un compito qualunque (per esempio un parser di una pagina
pubblica: l'agente la scarica con scarica_esempio) e con `--non-approvare` si ferma alla
versione da approvare (la sfida resta a chi amministra). Stampa quando arriva il piano (la
passata) e i token di ragionamento prima del primo strumento.

Per ogni compito: lavoro «estensione» → codice, test e manifesto dell'agente → consegna
controllata → versione da approvare (frase dell'annuncio) → approvazione (la sfida qui è
data per superata: la sfida a voce è in prova_estensioni_ollama) → uso del tool attraverso
la porta stretta, nel container. Con `--casa` la casa vera (solo letture: casa_stato), senza
una casa finta.

    cd <copia del ramo> && CALLIOPE_CONFIG=~/calliope/calliope.yaml \\
        <python di Calliope> prove/prova_estensioni_agente.py [--casa]
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prova_estensioni as P  # noqa: E402

COMPITI = [
    ("convertitore", "Una funzione che converte le unità di misura: lunghezze (km, miglia, "
     "metri, piedi), pesi (kg, libbre, grammi, once) e temperature (Celsius, Fahrenheit). "
     "Riceve il valore, l'unità di partenza e quella di arrivo.",
     [{"valore": 10, "da": "km", "a": "miglia"}, {"valore": 25, "da": "celsius",
                                                 "a": "fahrenheit"}]),
    ("temperatura", "Una funzione che legge dalla casa la temperatura di una stanza (la stanza "
     "la dice chi chiede; se non la dice, la cucina) e dice anche se è sotto i 19 gradi, "
     "cioè se fa freddo. Deve solo leggere, mai comandare niente.",
     [{"stanza": "cucina"}, {"stanza": "camera"}, {}]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casa", action="store_true", help="la casa vera (solo letture)")
    ap.add_argument("--solo", default="", help="solo questo compito (convertitore, temperatura)")
    ap.add_argument("--compito", default="", help="un compito qualunque al posto di quelli fissi")
    ap.add_argument("--gioco", action="store_true",
                    help="un gioco sullo schermo (05/10: scheda interattiva, test con Node)")
    ap.add_argument("--non-approvare", action="store_true",
                    help="fermati alla versione da approvare")
    a = ap.parse_args()
    from calliope.agenti import Lavori, carica
    from calliope.agenti.sandbox import scegli_isolamento
    from calliope.config import load_config
    from calliope.estensioni import Estensioni
    from calliope.estensioni.servizio import runtime_testo
    from calliope.tools.estensioni import estensioni_specs
    tmp = Path(tempfile.mkdtemp(prefix="calliope-est-agente-"))
    cfg = load_config()
    cfg.agenti_conferma = "mai"
    cfg.agenti_risultati = str(tmp / "risultati")
    cfg.agenti_sandbox = str(tmp / "sandbox")
    imp = carica(cfg)
    if imp is None:
        sys.exit("Nessun agente configurato.")
    iso = scegli_isolamento("docker", getattr(cfg, "agenti_sandbox_immagine", None))
    print(f"agente {imp.modello} ({imp.motore}); sandbox: {iso.descrizione}", flush=True)
    svc = Lavori(cfg, imp, log=lambda m: print(f"   {m}", flush=True))
    cfg2, reg, ctx, est, casa, liste = P.ambiente(tmp / "casa", iso)
    if a.casa:
        from calliope.casa import load_casa
        from calliope.tools.casa import casa_specs
        be, _ = load_casa(cfg)
        if be is None:
            sys.exit("La casa non è configurata.")
        time.sleep(3)
        for s in casa_specs(be is not None, ospite=False):
            if s.name == "casa_stato":
                reg.register(s)
        ctx.casa = be
        ctx.cfg = cfg
    est = Estensioni(cfg, tmp / "estensioni", registry=reg, tool_ctx=ctx, isolamento=iso)
    ctx.estensioni = est
    for s in estensioni_specs(crea=False):
        reg.register(s)
    svc.estensioni = est
    svc.agente.rete = est.rete            # registro delle uscite nella cartella temporanea
    arrivi = []
    piano_vero = svc.agente._piano

    def piano_osservato(lav, sandbox, args, prima):
        arrivi.append((lav.passi, lav.token, json.dumps(args, ensure_ascii=False)[:400]))
        return piano_vero(lav, sandbox, args, prima)
    svc.agente._piano = piano_osservato
    compiti = [("libero", a.compito, [])] if a.compito else COMPITI
    for nome, compito, prove in compiti:
        if a.solo and a.solo != nome:
            continue
        print(f"\n═══ {nome}: {compito}", flush=True)
        t0 = time.perf_counter()
        lav = svc.nuovo("estensione", compito, "u1", "Dario", "amministra")
        lav.estensione = None
        lav.gioco = a.gioco
        lav.file_iniziali = ({} if a.gioco else
                             {"calliope_estensione.py": runtime_testo()})
        svc.avvia(lav)
        item = svc.done.get(timeout=cfg.agenti_tempo_max_min * 60 + 60)
        dt = time.perf_counter() - t0
        print(f"[{dt / 60:.1f} min, {lav.passi} passi, {lav.token} token] {item['messaggio']}",
              flush=True)
        for passi, token, args in arrivi:
            print(f"   piano alla passata {passi} (token generati fin lì: {token}): {args}",
                  flush=True)
        arrivi.clear()
        c = lav.risultato.get("estensione")
        if not c:
            print("   nessuna versione da approvare:", lav.risultato.get("motivo"), flush=True)
            continue
        print("   scheda di revisione:\n      " + c["scheda_testo"].replace("\n", "\n      "))
        v = est.archivio.versione(c["nome"], c["versione"])
        dest = est.archivio.cartella_versione(c["nome"], c["versione"])
        print("   manifesto:", json.dumps(v["manifesto"], ensure_ascii=False)[:600])
        print("   file:", sorted(p.name for p in dest.iterdir()))
        if v["manifesto"].get("scheda"):
            from calliope.estensioni.scheda import documento
            from calliope.estensioni.servizio import approvabile_da_familiare
            print("   gioco puro, approvabile da un familiare:", approvabile_da_familiare(v),
                  "| test:", v.get("test"), "| rischi:", (v.get("analisi") or {}).get("rischi"),
                  flush=True)
            html, csp = documento(v["manifesto"]["scheda"], est.file_versione(c["nome"],
                                                                              c["versione"]))
            print(f"   documento del riquadro: {len(html)} caratteri", flush=True)
        if a.non_approvare:
            print(f"   versione da approvare in {est.archivio.cartella}", flush=True)
            continue
        ctx.speaker_ctx = P.speaker("Dario", "amministra")
        ctx.speaker_ctx.sfida_superata = True            # la sfida: prova_estensioni_ollama
        ctx.turno = 1
        r = json.loads(reg.call("estensioni_gestisci", {"azione": "approva", "nome": c["nome"]},
                                ctx, "amministra"))
        print("   approvazione:", r.get("risposta_finale"), flush=True)
        ctx.speaker_ctx.sfida_superata = False
        props = list((v["manifesto"].get("input") or {}).get("properties") or {})
        for i, args in enumerate(prove):
            ctx.turno = 2 + i
            if any(k not in props for k in args):
                # I nomi dei campi li ha scelti l'agente: gli stessi valori, nell'ordine
                args = dict(zip(props, args.values()))
            t = time.perf_counter()
            r = json.loads(reg.call("est_" + c["nome"], args, ctx, "amministra"))
            print(f"   uso {args} → {time.perf_counter() - t:.2f}s "
                  f"{json.dumps(r, ensure_ascii=False)[:400]}", flush=True)
            for d in (est.esecuzioni.get(r.get("esecuzione") or "") or SimpleNamespace(
                    decisioni=[])).decisioni:
                print("      porta:", d, flush=True)
        dec = est.archivio.cartella / "decisioni.jsonl"
        if dec.exists():
            righe = [json.loads(x) for x in dec.read_text(encoding="utf-8").splitlines()]
            print("   decisioni della porta:", [(x.get("azione"), x.get("classe"), x.get("esito"))
                                                 for x in righe if x.get("estensione") ==
                                                 c["nome"] and x.get("azione")], flush=True)
    svc.close()
    print(f"\ncartella: {tmp}")


if __name__ == "__main__":
    main()
