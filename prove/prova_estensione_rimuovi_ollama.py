"""L'eliminazione di un'estensione con il modello vero della voce (Ollama locale, `llm_model`),
il docker FINTO e un servizio dei lavori finto (09/10/2026). Nomi di fantasia: «Meteo città»
disattivata e «Meteocittà» attiva, che a voce si dicono uguali (il caso della DGX; il resto a
secco in prove/prova_estensione_rimuovi.py):

1. «rimuovi l'estensione Meteo città» → la domanda è sulla disattivata, niente eliminato;
   al «sì» si elimina quella e l'attiva resta;
2. contrario: «disattiva l'estensione Meteocittà» → si spegne l'attiva, niente eliminato;
3. contrario: con la sola attiva, «elimina l'estensione Meteocittà» → niente eliminato, «prima
   la disattivo?».

    python prove\\prova_estensione_rimuovi_ollama.py      # 3 giri
    python prove\\prova_estensione_rimuovi_ollama.py 1    # 1 giro
"""

import os
import sys
import tempfile
from pathlib import Path

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo_giro4 as G  # noqa: E402
import prova_sviluppo_ollama as SO  # noqa: E402
from calliope.brain import Brain  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}
tempi: list = []


def conta(chiave, ok, giro, frase, tools, r, extra=""):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:50]}» → {', '.join(tools) or '—'}"
          f" {r[:200]!r} {extra}", flush=True)


def nuovo(tmp, iso):
    cfg, reg, ctx, est, svc = SO.ambiente(tmp, iso, [])
    est.archivio.rinomina("meteo_citta", "Meteo città")
    est.archivio.disattiva("meteo_citta")
    P.installa(est, G.M_COD, G.S.CODICE2)
    est.archivio.rinomina("meteo_codificato", "Meteocittà")
    est.aggiorna_tool()
    ctx.registro = reg
    b = Brain(cfg, reg, ctx)
    b.conv_owner = "u1"
    return cfg, reg, ctx, est, svc, b


def parla(b, voce, frase):
    r, tools, s = SO.parla(b, voce, frase)
    tempi.append(s)
    return r, tools


def offerta(est, nome) -> bool:
    return any(isinstance(k, tuple) and k[-1:] == (nome,) and "rimuovi" in k
               for k in est._offerte)


def sessione(giro, tmp, iso):
    dario = SO.Voce("Dario", "amministra")
    # 1. «rimuovi l'estensione Meteo città» → la disattivata
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "rimuovi", iso)
    a = est.archivio
    frase = "Calliope, rimuovi l'estensione Meteo città."
    r, tools = parla(b, dario, frase)
    conta("1a «rimuovi Meteo città» → la domanda sulla disattivata",
          offerta(est, "meteo_citta") and not offerta(est, "meteo_codificato")
          and a.voce("meteo_citta") is not None and a.voce("meteo_codificato") is not None,
          giro, frase, tools, r)
    frase = "Sì, procedi."
    r, tools = parla(b, dario, frase)
    conta("1b «sì» → eliminata la disattivata, l'attiva resta",
          a.voce("meteo_citta") is None and (a.voce("meteo_codificato") or {}).get("stato")
          == "attiva" and reg.get("est_meteo_codificato") is not None, giro, frase, tools, r)

    # 2. contrario: disattivare va sull'attiva
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "disattiva", iso)
    a = est.archivio
    frase = "Calliope, disattiva l'estensione Meteocittà."
    r, tools = parla(b, dario, frase)
    conta("2 contrario: «disattiva Meteocittà» → l'attiva spenta, niente eliminato",
          (a.voce("meteo_codificato") or {}).get("stato") == "disattivata"
          and a.voce("meteo_citta") is not None and not offerta(est, "meteo_codificato"),
          giro, frase, tools, r)

    # 3. contrario: la sola attiva non si elimina
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "attiva", iso)
    a = est.archivio
    a.rimuovi("meteo_citta")
    frase = "Calliope, elimina l'estensione Meteocittà."
    r, tools = parla(b, dario, frase)
    conta("3 contrario: «elimina Meteocittà» attiva → niente eliminato, prima disattivarla",
          (a.voce("meteo_codificato") or {}).get("stato") == "attiva"
          and "prima la disattivo" in r, giro, frase, tools, r)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-rimuovi-ollama-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    for giro in range(1, GIRI + 1):
        sessione(giro, tmp0 / f"g{giro}", iso)
    print("\nRiepilogo (riusciti / casi):")
    for chiave, (k, n) in sorted(conteggi.items()):
        print(f"  {chiave:75} {k}/{n}")
    if tempi:
        t = sorted(tempi)
        print(f"  prima frase: mediana {t[len(t) // 2]:.2f} s, massimo {t[-1]:.2f} s "
              f"({len(t)} turni)")
    # Misura, non soglia: esce con errore solo se un passo non riesce mai
    mai = [k for k, (ok, n) in conteggi.items() if ok == 0]
    print("\nTutto bene." if not mai else f"\nMai riusciti: {mai}")
    sys.exit(1 if mai else 0)


if __name__ == "__main__":
    main()
