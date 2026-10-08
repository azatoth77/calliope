"""Il giro 4 della modalità sviluppo con il modello vero della voce (Ollama locale,
`llm_model`), il docker FINTO e un servizio dei lavori finto (08/10/2026). Dal giro vero della
DGX dell'08/10 sera, con nomi di fantasia (prove/prova_sviluppo_giro4.py per il resto):

1. «modifichiamo l'estensione Meteocittà aggiungendo i giorni…», con «Meteo città»
   disattivata accanto → la versione nuova di Meteocittà (con `modifica` = il nome, o
   ricondotta da `estensione_modifica_dal_nome`), mai la domanda «Meteo città o Meteocittà?»;
2. al collaudo della versione con `citta` e `giorni`, «prova Pratofiorito per 3 giorni» →
   citta = Pratofiorito e giorni = 3 (con `argomenti` o dai dati);
3. in analisi, a offerta scaduta, «l'analisi è corretta e voglio implementarla così» → il
   lavoro parte, senza ripetere la domanda.

    python prove\\prova_sviluppo_giro4_ollama.py      # 3 giri
    python prove\\prova_sviluppo_giro4_ollama.py 1    # 1 giro
"""

import json
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
import prova_sviluppo_v2 as V  # noqa: E402
from calliope.brain import Brain  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}
tempi: list = []


def conta(chiave, ok, giro, frase, tools, r, extra=""):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:50]}» → {', '.join(tools) or '—'}"
          f" {r[:170]!r} {extra}", flush=True)


def nuovo(tmp, iso):
    web = []
    cfg, reg, ctx, est, svc = SO.ambiente(tmp, iso, web)
    est.archivio.disattiva("meteo_citta")         # M1 delle prove: qui la vecchia, disattivata
    P.installa(est, G.M_COD, G.S.CODICE2)
    est.archivio.rinomina("meteo_codificato", "Meteocittà")
    est.aggiorna_tool()
    svc.cfg, svc.imp = cfg, V.SimpleNamespace(modello="agente-finto")
    svc.cliente = V.AgenteFinto({"voce": "Va.", "serve_correzione": False})
    ctx.registro = reg
    b = Brain(cfg, reg, ctx)
    b.conv_owner = "u1"
    return cfg, reg, ctx, est, svc, b


def parla(b, voce, frase):
    r, tools, s = SO.parla(b, voce, frase)
    tempi.append(s)
    return r, tools


def sessione(giro, tmp, iso):
    dario = SO.Voce("Dario", "amministra")
    # 1. la modifica con i giorni
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "modifica", iso)
    frase = ("Modifichiamo l'estensione Meteocittà aggiungendo i giorni di meteo di cui voglio "
             "fare le previsioni.")
    r, tools = parla(b, dario, frase)
    lav = (svc.offerte.get("u1") or {}).get("lavoro") or next(iter(svc.lavori), None)
    regole = list(b.last_rules or [])
    conta("1 modifica con i giorni → versione nuova di Meteocittà",
          lav is not None and lav.estensione == "meteo_codificato"
          and "o Meteocittà" not in r and "Meteo città o" not in r, giro, frase, tools, r,
          "(dal nome)" if "estensione_modifica_dal_nome" in regole else "")

    # 2. il collaudo con citta e giorni
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "collaudo", iso)
    b.tool_ctx.speaker_ctx = dario
    G.al_collaudo(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    b.record_announcement("Dario, il lavoro di «Meteocittà» è pronto: siamo al collaudo. La "
                          "versione 2 non è ancora attiva: prima la proviamo. Con cosa provo?",
                          fonte="agente")
    for chiave, frase, attesi in (
            ("2a «Pratofiorito per 3 giorni» → citta e giorni",
             "Proviamola subito con il meteo di Pratofiorito per i prossimi 3 giorni.",
             {"citta": "Pratofiorito", "giorni": 3}),
            ("2b «Borgoverde, cinque giorni» → citta e giorni",
             "Adesso prova Borgoverde per cinque giorni.",
             {"citta": "Borgoverde", "giorni": 5})):
        k = len(sv.collaudi)
        r, tools = parla(b, dario, frase)
        nuovi = sv.collaudi[k:]
        arg = (nuovi[-1].get("argomenti") or {}) if nuovi else {}
        giusti = (str(arg.get("citta", "")).strip().lower() == attesi["citta"].lower()
                  and str(arg.get("giorni")) == str(attesi["giorni"]))
        conta(chiave, giusti, giro, frase, tools, r, json.dumps(arg, ensure_ascii=False))

    # 3. «avanti» in analisi a offerta scaduta
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "analisi", iso)
    b.tool_ctx.speaker_ctx = dario
    G.al_collaudo(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    ctx.turno = 10
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche il vento"})
    b.turn_number = ctx.turno = 14
    k = len(svc.lavori)
    frase = "Ok, direi che l'analisi è corretta e voglio implementarla così."
    r, tools = parla(b, dario, frase)
    conta("3 «l'analisi è corretta, implementala» → il lavoro parte",
          len(svc.lavori) > k and sv.fase == "sviluppo", giro, frase, tools, r)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro4-ollama-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    for giro in range(1, GIRI + 1):
        sessione(giro, tmp0 / f"g{giro}", iso)
    print("\nRiepilogo (riusciti / casi):")
    for chiave, (k, n) in sorted(conteggi.items()):
        print(f"  {chiave:70} {k}/{n}")
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
