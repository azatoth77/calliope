"""
Il giudizio «la frase è rivolta a Calliope?» con il modello vero (09/10/2026, F2 della modalità
compagnia, calliope/rivolta.py; docs/ricerche/2026-10-09-piu-persone.md § 3.6 e § 6).

Lo stesso codice di Calliope (`rivolta.Giudice` con l'output strutturato, sul modello del
rilevatore di pericolo, `guardiano_pericolo_modello`, o quello dato) sulle 56 frasi di fantasia
di `misura_rivolta.py`: 27 rivolte a Calliope (seguiti, conferme, un ospite che le parla, terze
persone dentro un comando) e 29 no (chiacchiere, Calliope in terza persona, un altro nominato
come interlocutore). Soglie del documento: almeno 25/27 rivolte e 26/29 non rivolte giuste; il
tempo mediano si stampa. Senza Ollama o senza il modello si salta (77). Alla fine il modello si
scarica (keep_alive 0).

    .venv\\Scripts\\python prove\\prova_rivolta_ollama.py [giri] [modello]
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import rivolta
from calliope.config import Config

SALTATA = 77


def casi():
    """Le frasi di misura_rivolta (contesto, frase, attesa), senza l'indizio della voce."""
    argv, sys.argv = sys.argv, sys.argv[:1]            # misura_rivolta legge il modello da argv
    try:
        import misura_rivolta as M
    finally:
        sys.argv = argv
    out = []
    for ctx, _voce, frase, atteso in M.C:
        # Chi parla con Calliope è registrato (Marco): nel contesto il suo nome, come nel ciclo
        righe = [("Calliope" if chi == M.A else rivolta.etichetta("Marco"), t) for chi, t in ctx]
        out.append((righe, frase, atteso))
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    giri = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    cfg = Config()
    if len(sys.argv) > 2:
        cfg.compagnia_rivolta_modello = sys.argv[2]
    dove = rivolta.dove(cfg)
    if dove is None:
        print("Nessun modello per il giudizio: prova saltata.")
        return SALTATA
    url, modello = dove
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=3) as r:
            nomi = {m.get("name") for m in json.loads(r.read()).get("models", [])}
    except Exception as e:  # noqa: BLE001
        print(f"Ollama non risponde su {url} ({type(e).__name__}): prova saltata.")
        return SALTATA
    if modello not in nomi:
        print(f"Il modello {modello} non c'è: prova saltata.")
        return SALTATA
    print(f"Giudizio su {modello} ({url}), {giri} giro/i", flush=True)
    giudice = rivolta.Giudice(cfg)
    elenco = casi()
    n_si = sum(1 for c in elenco if c[2])
    n_no = len(elenco) - n_si
    giudice.giudica([], "Ciao.", timeout=120)              # carica il modello
    errori = 0
    try:
        for g in range(giri):
            giusti = {True: 0, False: 0}
            tempi, sbagliate, guasti = [], [], 0
            for righe, frase, atteso in elenco:
                r = giudice.giudica(righe, frase, timeout=10)
                tempi.append(r.ms)
                guasti += r.guasto is not None
                if r.rivolta == atteso:
                    giusti[atteso] += 1
                else:
                    sbagliate.append(frase)
            tempi.sort()
            med = tempi[len(tempi) // 2]
            ok = giusti[True] >= 25 and giusti[False] >= 26
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} giro {g + 1}: rivolte giuste {giusti[True]}/{n_si} "
                  f"(soglia 25), non rivolte giuste {giusti[False]}/{n_no} (soglia 26), "
                  f"guasti {guasti}; mediana {med:.0f} ms, p90 "
                  f"{tempi[int(0.9 * len(tempi))]:.0f} ms", flush=True)
            if sbagliate:
                print("    sbagliate:", "; ".join(sbagliate), flush=True)
    finally:
        try:
            body = json.dumps({"model": modello, "keep_alive": 0}).encode()
            urllib.request.urlopen(urllib.request.Request(
                url + "/api/generate", body, {"Content-Type": "application/json"}), timeout=30)
        except Exception:  # noqa: BLE001
            pass
    print("\nTutto bene." if not errori else f"\n{errori} giri sotto soglia.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
