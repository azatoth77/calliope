"""
Gli argomenti (10/10/2026, § 13 del registro degli eventi) con il modello vero della voce
(Ollama locale, `llm_model`), `eventi: attivo`: i giri della DGX del 10/10 e i contrari, con il
prompt e gli schemi veri e i turni prima a copione (prove/misura_argomenti.py).

- «Ricominciamo.» durante l'analisi di Celsius (giro 3, 10:39) → argomento nuovo;
- «Ricominciamo da capo: scrivimi … chilometri in miglia» → argomento nuovo e lo sviluppo
  nuovo, non una modifica di Celsius (giro 4, 11:50);
- «Ricominciamo da dove eravamo con i consigli…» → argomento ripreso;
- «Torniamo al programma dei gradi.» → argomento ripreso;
- contrari: un dettaglio dello stesso sviluppo, il «sì» alla proposta, l'ora durante lo
  sviluppo, «e poi?»: mai un cambio d'argomento.

Soglia: i contrari tutti; i cambi almeno 2 giri su 3 (il modello varia). «Chilometri» detto
senza nessuna parola di cambio (giro 4, 11:47) resta una misura: lì risponde lo sviluppo
(«ne seguo uno per volta: vuoi sospendere il primo?»).

    python prove\\prova_argomenti_ollama.py      # 3 giri
    python prove\\prova_argomenti_ollama.py 1    # 1 giro
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import misura_argomenti as ma  # noqa: E402
from calliope.config import Config  # noqa: E402


def ollama_pronto() -> bool:
    try:
        import httpx
        r = httpx.get(Config().llm_native_url + "/api/tags", timeout=3)
        nomi = {m.get("name") for m in r.json().get("models") or ()}
        return Config().llm_model in nomi
    except Exception:  # noqa: BLE001
        return False


def main():
    giri = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    if not ollama_pronto():
        print("Ollama o il modello della voce non ci sono: prova saltata")
        return 77
    errori = 0
    try:
        righe = ma.misura("tool", giri)
        sec = ma.ripeti_secondo(giri)
    finally:
        subprocess.run(["ollama", "stop", Config().llm_model], capture_output=True)
    for (nome, prep, frase, atteso, _p), (_n, ok, dettagli, s) in zip(ma.CASI, righe):
        if nome.startswith("chilometri durante"):
            print(f"misura  {nome}: {ok}/{giri} ({dettagli})")
            continue
        soglia = giri if atteso is None else max(1, (2 * giri + 2) // 3)
        bene = ok >= soglia
        errori += not bene
        print(f"{'ok ' if bene else 'ERR'} {nome}: {ok}/{giri} (soglia {soglia}; {dettagli})",
              flush=True)
    soglia = max(1, (2 * giri + 2) // 3)
    bene = sec >= soglia
    errori += not bene
    print(f"{'ok ' if bene else 'ERR'} «ripeti il secondo consiglio» dopo un'interruzione e lo "
          f"stop: il secondo detto {sec}/{giri} (soglia {soglia}; promemoria della parte non "
          f"detta)")
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
