"""Il giro 5 della modalità sviluppo con il modello vero della voce (Ollama locale,
`llm_model`), il docker FINTO e un servizio dei lavori finto (08/10/2026). Dal giro vero della
DGX dell'08/10 sera (18:23), con nomi di fantasia (prove/prova_sviluppo_giro5.py per il resto):
«chiedi all'agente» trascritto «chiedi alla gente», e il modello che chiama richiesta_tutore o
dice «ho registrato la tua domanda» senza chiamare niente.

1. sviluppo aperto, «puoi chiedere alla gente come sceglie la città quando ce ne sono due con
   lo stesso nome?» → sviluppo_chiedi;
2. sviluppo aperto, «volevo che lo chiedessi alla gente che sta sviluppando Meteocittà come
   fa a scegliere la città…» → sviluppo_chiedi;
3. contrario, sviluppo aperto: «la gente dice che domani pioverà: tu cosa ne pensi?» → NON
   sviluppo_chiedi;
4. contrario, senza sviluppo aperto: «chiedi alla gente come sceglie la città…» → NON
   sviluppo_chiedi riuscito.

    python prove\\prova_sviluppo_giro5_ollama.py      # 3 giri
    python prove\\prova_sviluppo_giro5_ollama.py 1    # 1 giro
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
import prova_sviluppo_giro4_ollama as G4O  # noqa: E402
import prova_sviluppo_ollama as SO  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}


def conta(chiave, ok, giro, frase, tools, r, extra=""):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:50]}» → {', '.join(tools) or '—'}"
          f" {r[:170]!r} {extra}", flush=True)


def sessione(giro, tmp, iso):
    dario = SO.Voce("Dario", "amministra")
    casi = (
        ("1 «chiedere alla gente come sceglie…» → sviluppo_chiedi", True,
         "Calliope, nel frattempo puoi chiedere alla gente come sceglie la città quando ce ne "
         "sono due con lo stesso nome?"),
        ("2 «lo chiedessi alla gente che sta sviluppando…» → sviluppo_chiedi", True,
         "No, volevo solo che lo chiedessi alla gente che sta sviluppando Meteocittà come fa a "
         "scegliere la città quando ce ne sono due con lo stesso nome."),
        ("3 contrario: «la gente dice che pioverà» → non sviluppo_chiedi", False,
         "La gente dice che domani pioverà: tu cosa ne pensi?"),
    )
    for i, (chiave, atteso, frase) in enumerate(casi):
        cfg, reg, ctx, est, svc, b = G4O.nuovo(tmp / f"aperto{i}", iso)
        b.tool_ctx.speaker_ctx = dario
        G.al_collaudo(ctx, est, svc)
        svc.cliente = G4O.V.AgenteFinto({"voce": "Prendo la prima, quella italiana.",
                                         "serve_correzione": False})
        r, tools = G4O.parla(b, dario, frase)
        chiesto = "sviluppo_chiedi" in tools
        conta(chiave, chiesto == atteso, giro, frase, tools, r)
    cfg, reg, ctx, est, svc, b = G4O.nuovo(tmp / "chiuso", iso)
    frase = ("Calliope, chiedi alla gente come sceglie la città quando ce ne sono due con lo "
             "stesso nome.")
    r, tools = G4O.parla(b, dario, frase)
    riuscito = any(t.get("nome") == "sviluppo_chiedi" and t.get("ok") for t in b.last_tools)
    conta("4 contrario senza sviluppo aperto → non sviluppo_chiedi riuscito", not riuscito,
          giro, frase, tools, r)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro5-ollama-"))
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
    mai = [k for k, (ok, n) in conteggi.items() if ok == 0]
    print("\nTutto bene." if not mai else f"\nMai riusciti: {mai}")
    sys.exit(1 if mai else 0)


if __name__ == "__main__":
    main()
