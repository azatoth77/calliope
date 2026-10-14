"""
Il giudice di fase dei giochi con il modello vero (14/10/2026, passo 6 del progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md § 3.5; calliope/gioco_giudice.py).

Lo stesso codice di Calliope (`gioco_giudice.Giudice`: il prompt scritto dai comandi della
macchina, l'uscita vincolata all'enum dei comandi attivi più «nessuno») sul modello del giudizio
«rivolta» (il rilevatore di pericolo, `guardiano_pericolo_modello`, altrimenti quello della voce)
o quello dato, con le 22 frasi del prototipo del 12/10: il gioco delle porte da 1 a 5 con la 2
già aperta. Otto frasi chiedono una porta con altre parole («apri la terza», «uno, no aspetta,
la cinque», «apriamo l'ultima»), quattordici no (la porta già aperta, una che non c'è, domande
sul gioco, chiacchiere, due porte insieme, «ricominciamo» che adesso non vale). Soglie del
progetto: almeno 20/22 giuste e **nessuna mossa** su «a chi tocca?» e «quanti punti ho?»; il
tempo mediano si stampa. Senza Ollama o senza il modello si salta (77). Alla fine il modello si
scarica (keep_alive 0).

    .venv\\Scripts\\python prove\\prova_gioco_giudice_ollama.py [giri] [modello]
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import gioco_giudice  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.estensioni import macchina as mc  # noqa: E402

SALTATA = 77
MACCHINA = mc.normalizza({"inizio": "turno", "fasi": {"turno": {
    "pagina": "scelte", "verso": ["esito", "fine"],
    "comandi": {"porta": {"forme": ["porta {n}", "la porta {n}", "{n}"], "n": {"da": 1, "a": 5},
                          "etichetta": "Porta {n}"}}}}}, {"min": 1, "max": 4})
ATTIVI = ["porta_1", "porta_3", "porta_4", "porta_5"]
CASI = [
    ("apri la terza", "porta_3"), ("voglio la porta numero quattro", "porta_4"),
    ("scelgo la cinque", "porta_5"), ("proviamo con la prima", "porta_1"),
    ("apri la porta tre", "porta_3"), ("dai, la quattro!", "porta_4"),
    ("uno, no aspetta, la cinque", "porta_5"), ("apriamo l'ultima", "porta_5"),
    # contrari: nessuno
    ("la porta due", None), ("apri la sei", None), ("che ore sono?", None),
    ("chiudi la porta che c'è corrente", None), ("mamma, hai visto le chiavi?", None),
    ("a chi tocca?", None), ("quanti punti ho?", None), ("tre gatti neri", None),
    ("apri la tre e poi la quattro", None), ("che bello questo gioco", None),
    ("metti un po' di musica", None), ("ho fame, cosa c'è per cena?", None),
    ("ricominciamo da capo", None), ("facciamo un'altra partita dall'inizio", None),
]
DOMANDE = ("a chi tocca?", "quanti punti ho?")


def info() -> dict:
    piatti = mc.ascolta(MACCHINA, {"min": 1, "max": 4})["comandi"]
    return {"partita": "P1", "schermo": 1, "titolo": "Apri le porte", "macchina": MACCHINA,
            "comandi": {c: piatti[c] for c in ATTIVI}}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    giri = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    cfg = Config()
    if len(sys.argv) > 2:
        cfg.giochi_giudice_modello = sys.argv[2]
    dove = gioco_giudice.dove(cfg)
    if dove is None:
        print("Nessun modello per il giudice: prova saltata.")
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
    print(f"Giudice di fase su {modello} ({url}), {giri} giro/i", flush=True)
    g = gioco_giudice.Giudice(cfg)
    i = info()
    print("Prompt:\n" + gioco_giudice.prompt(i)[0] + "\n", flush=True)
    g.scegli("prova", i, timeout=120)                      # carica il modello
    errori = 0
    try:
        for n in range(giri):
            giusti, tempi, sbagliate, guasti, mosse_domande = 0, [], [], 0, []
            for frase, atteso in CASI:
                s = g.scegli(frase, i, timeout=10)
                tempi.append(s.ms)
                guasti += s.guasto is not None
                if s.comando == atteso:
                    giusti += 1
                else:
                    sbagliate.append(f"{frase} → {s.comando or 'nessuno'}")
                if frase in DOMANDE and s.comando is not None:
                    mosse_domande.append(frase)
            tempi.sort()
            med = tempi[len(tempi) // 2]
            ok = giusti >= 20 and not mosse_domande
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} giro {n + 1}: giuste {giusti}/{len(CASI)} (soglia "
                  f"20), mosse su una domanda {len(mosse_domande)} (soglia 0), guasti {guasti}; "
                  f"mediana {med:.0f} ms, p90 {tempi[int(0.9 * len(tempi))]:.0f} ms", flush=True)
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
