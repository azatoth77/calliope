"""Comandi del flusso e ripresa con il modello vero della voce (Ollama locale, `llm_model`), il
docker FINTO e un servizio dei lavori finto (12/10/2026, lavoro 3; a secco il resto in
prove/prova_flusso_ripresa.py). Dai casi veri della DGX del 06–12/10, con nomi di fantasia:

1. **ripresa**: con il lavoro fermato, «Riprendiamo lo sviluppo di Meteocittà.» → una domanda
   sola (mai «è già aperto», mai «cosa vuoi cambiare?»), poi «Sì, rifallo.» → il lavoro riparte
   senza rileggere la specifica: 2 turni;
2. **storpiatura**: con l'agente al lavoro «Am nulla il lavoro.» non ferma il lavoro senza una
   domanda e non ne fa partire uno; contrario: «Ferma il lavoro dell'agente.» lo ferma;
3. **chiudi tutti**: con uno sviluppo aperto e uno sospeso, «Chiudi tutti gli sviluppi.» → una
   domanda con i due titoli, e «Sì.» li chiude tutti e due;
4. **lascia com'era**: con l'agente al lavoro, «Cambia: deve dire anche il vento.» non ferma il
   lavoro; poi «No, lascia com'era.» → lo sviluppo torna allo sviluppo con il lavoro di prima.

    python prove\\prova_flusso_ripresa_ollama.py      # 3 giri
    python prove\\prova_flusso_ripresa_ollama.py 1    # 1 giro
"""

import os
import sys
import tempfile
from pathlib import Path

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo_giro4_ollama as G4O  # noqa: E402
import prova_sviluppo_giro6_ollama as G6O  # noqa: E402
import prova_sviluppo_ollama as SO  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}


def conta(chiave, ok, giro, frase, tools, r, extra=""):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:50]}» → {', '.join(tools) or '—'}"
          f" {r[:200]!r} {extra}", flush=True)


def sessione(giro, tmp, iso):
    dario = SO.Voce("Dario", "amministra")

    # 1. ripresa in una domanda
    cfg, reg, ctx, est, svc, b, sv, lav = G6O.al_lavoro(tmp / "ripresa", iso, dario)
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"})
    frase = "Riprendiamo lo sviluppo di Meteocittà."
    r, tools = G4O.parla(b, dario, frase)
    ok = ("già aperto" not in r and "cosa vuoi cambiare" not in r.lower()
          and r.count("?") == 1 and "rifaccio" in r)
    conta("1a «Riprendiamo lo sviluppo di…» → una domanda sola", ok, giro, frase, tools, r)
    k = len(svc.lavori)
    frase = "Sì, rifallo."
    r, tools = G4O.parla(b, dario, frase)
    partito = len(svc.lavori) > k and sv.lavoro == svc.lavori[-1].id \
        and svc.lavori[-1].stato == "in_corso"
    conta("1b «Sì, rifallo.» → riparte (2 turni in tutto)", partito and "Ho capito così" not in r,
          giro, frase, tools, r)

    # 2. una storpiatura non ferma niente senza domanda
    cfg, reg, ctx, est, svc, b, sv, lav = G6O.al_lavoro(tmp / "storp", iso, dario)
    b.storpiata_turno = None
    frase = "Am nulla il lavoro."
    k = len(svc.lavori)
    # Il dato del turno della storpiatura, come lo mette il ciclo (calliope/storpiature.py)
    from calliope import storpiature
    b.storpiata_turno = storpiature.suggerisci(frase)
    r, tools = G4O.parla(b, dario, frase)
    b.storpiata_turno = None
    ok = lav.stato == "in_corso" and len(svc.lavori) == k
    conta("2a «Am nulla il lavoro.» → niente fermato né rifatto senza una domanda", ok, giro,
          frase, tools, r, "(domanda della politica)" if "politica_storpiatura_irreversibile"
          in (b.last_rules or []) else "")
    cfg, reg, ctx, est, svc, b, sv, lav = G6O.al_lavoro(tmp / "ferma", iso, dario)
    frase = "Ferma il lavoro dell'agente, non deve più continuare."
    r, tools = G4O.parla(b, dario, frase)
    conta("2b contrario «Ferma il lavoro dell'agente» → fermato", G6O.fermato(svc, lav, tools),
          giro, frase, tools, r)

    # 3. chiudi tutti
    cfg, reg, ctx, est, svc, b, sv, lav = G6O.al_lavoro(tmp / "tutti", iso, dario)
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"})
    altro = svc.sviluppi.apri("u1", "Dario", "programma", "conta le vocali",
                              titolo="programma che conta le vocali")
    svc.sviluppi.sospendi(altro)
    svc.sviluppi.riprendi(sv)
    frase = "Chiudi tutti gli sviluppi."
    r, tools = G4O.parla(b, dario, frase)
    ok = sv.stato != "chiusa" and altro.stato != "chiusa" and "conta le vocali" in r \
        and "Meteo" in r and r.rstrip().endswith("?")
    conta("3a «Chiudi tutti gli sviluppi.» → una domanda con i due titoli", ok, giro, frase,
          tools, r)
    frase = "Sì."
    r, tools = G4O.parla(b, dario, frase)
    conta("3b «Sì.» → chiusi tutti e due", sv.stato == "chiusa" and altro.stato == "chiusa",
          giro, frase, tools, r)

    # 4. la modifica non ferma il lavoro, e «lascia com'era» torna indietro
    cfg, reg, ctx, est, svc, b, sv, lav = G6O.al_lavoro(tmp / "indietro", iso, dario)
    frase = "Cambia una cosa: deve dire anche il vento."
    r, tools = G4O.parla(b, dario, frase)
    conta("4a la modifica con l'agente al lavoro → il lavoro continua", lav.stato == "in_corso",
          giro, frase, tools, r, f"(fase {sv.fase})")
    frase = "No, ci ho ripensato: lascia com'era."
    r, tools = G4O.parla(b, dario, frase)
    ok = lav.stato == "in_corso" and sv.fase == "sviluppo" and sv.lavoro == lav.id \
        and not sv.ritorno
    conta("4b «lascia com'era» → di nuovo allo sviluppo con il lavoro di prima", ok, giro, frase,
          tools, r, f"(fase {sv.fase})")


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-flusso-ollama-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    for giro in range(1, GIRI + 1):
        sessione(giro, tmp0 / f"g{giro}", iso)
    print("\nRiepilogo (riusciti / casi):")
    for chiave, (k, n) in sorted(conteggi.items()):
        print(f"  {chiave:70} {k}/{n}")
    t = sorted(G4O.tempi)
    if t:
        print(f"  prima frase: mediana {t[len(t) // 2]:.2f} s, massimo {t[-1]:.2f} s "
              f"({len(t)} turni)")
    # Misura, non soglia: esce con errore solo se un caso non riesce mai
    mai = [k for k, (ok, n) in conteggi.items() if ok == 0]
    print("\nTutto bene." if not mai else f"\nMai riusciti: {mai}")
    sys.exit(1 if mai else 0)


if __name__ == "__main__":
    main()
