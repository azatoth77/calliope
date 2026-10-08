"""Il giro 3 della modalità sviluppo con il modello vero della voce (Ollama locale,
`llm_model`), il docker FINTO e un servizio dei lavori finto (08/10/2026). Dal giro vero della
DGX dell'08/10 pomeriggio, con nomi di fantasia:

1. «Modifica l'estensione Meteocittà: fai codificare il nome…» → una versione nuova di quella
   che c'è (subito con `modifica`, o dopo la scelta restituita da `estensione_simile_scelta`),
   mai un'estensione nuova accanto;
2. con due estensioni attive, «adesso abbiamo due estensioni, giusto?» → sì, due (l'elenco vero
   nei dati del turno), mai «una»;
3. «Rinomina l'estensione Meteo città codificata, chiamala Meteo Valfiorita» →
   estensione_gestisci rinomina, senza agente;
4. al collaudo, la frase di sfida superata → l'esito del collaudo detto dal modello, senza
   richiamare il tool né «Fatto.»;
5. al collaudo con il lavoro dell'agente di mezzo, «Prova con Bergamo, Cerno Maggiore e
   Fontalba» (trascrizione storpiata; «Cerro Maggiore» nell'annuncio) → nessuna domanda
   «viene dal lavoro di un agente».

    python prove\\prova_sviluppo_giro3_ollama.py      # 3 giri
    python prove\\prova_sviluppo_giro3_ollama.py 1    # 1 giro
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
import prova_sviluppo_ollama as SO  # noqa: E402
import prova_sviluppo_v2 as V  # noqa: E402
from calliope import conferme as C  # noqa: E402
from calliope.brain import Brain  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}
tempi: list = []


def conta(chiave, ok, giro, frase, tools, r):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:50]}» → {', '.join(tools) or '—'}"
          f" {r[:170]!r}", flush=True)


def nuovo(tmp, iso):
    web = []
    cfg, reg, ctx, est, svc = SO.ambiente(tmp, iso, web)
    svc.cfg, svc.imp = cfg, V.SimpleNamespace(modello="agente-finto")
    svc.cliente = V.AgenteFinto({"voce": "Va.", "serve_correzione": False})
    b = Brain(cfg, reg, ctx)
    b.conv_owner = "u1"
    return cfg, reg, ctx, est, svc, b


def parla(b, voce, frase):
    r, tools, s = SO.parla(b, voce, frase)
    tempi.append(s)
    return r, tools


def sessione(giro, tmp, iso):
    dario = SO.Voce("Dario", "amministra")
    # 1. la modifica di un'estensione che c'è (M1: meteo_citta, «Meteo Borgoverde e
    # Valfiorita»; la persona la chiama «Meteocittà», come sulla DGX)
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "modifica", iso)
    P.installa(est, P.manifesto("meteo_citta", "Meteo città", "Dice il meteo di una città."),
               S.CODICE2)
    frase = ("Modifica l'estensione Meteocittà: fai codificare il nome della città prima di "
             "mandarlo nell'URL.")
    r, tools = parla(b, dario, frase)
    lav = next(iter(svc.lavori), None) or (svc.offerte.get("u1") or {}).get("lavoro")
    nuove = [n for n in est.archivio.nomi() if n != "meteo_citta"]
    conta("1 modifica → versione nuova di quella che c'è", lav is not None
          and lav.estensione == "meteo_citta" and not nuove, giro, frase, tools, r)
    conta("1b …senza «quale API vuoi usare?»", "API" not in r and "analisi_vaga"
          not in (b.last_rules or []), giro, frase, tools, r)

    # 2. due estensioni attive
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "elenco", iso)
    P.installa(est, P.manifesto("meteo_codificato", "Meteo città codificata",
                                "Dice il meteo di una città."), S.CODICE2)
    frase = "Ringrazio. Senti, quindi adesso abbiamo due estensioni, giusto?"
    r, tools = parla(b, dario, frase)
    conta("2 «abbiamo due estensioni?» → due", ("due" in r.lower() or "Borgoverde" in r)
          and "solo una" not in r.lower() and "una sola" not in r.lower(), giro, frase, tools, r)
    frase = "Quindi la vecchia non c'è più?"
    r, tools = parla(b, dario, frase)
    falso = any(k in r.lower() for k in ("ritirat", "non c'è più", "sostituit", "solo una",
                                          "una sola", "rimoss"))
    conta("2b «la vecchia non c'è più?» → niente di falso (DGX: «è stata ritirata»)",
          not falso, giro, frase, tools, r)
    conta("2c …e dice che c'è ancora", not falso and any(
        k in r.lower() for k in ("c'è ancora", "ancora attiva", "è attiva", "esiste",
                                 "sono attive", "ancora", "entrambe", "tutte e due")),
          giro, frase, tools, r)

    # 3. rinomina
    frase = ("E allora rinominiamo quella nuova, Meteo città codificata non mi piace: chiamala "
             "Meteo Valfiorita.")
    r, tools = parla(b, dario, frase)
    titolo = (est.archivio.manifesto("meteo_codificato") or {}).get("titolo")
    conta("3 «chiamala Meteo Valfiorita» → rinominata, senza agente",
          titolo == "Meteo Valfiorita" and "sviluppo_apri" not in tools, giro, frase, tools, r)

    # 4. l'esito dopo la sfida, al collaudo
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "sfida", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "estensione", "il meteo per città", titolo="Meteo per città")
    sv.specifica = "dice il meteo di una città qualunque"
    n = S.candidata(est)
    sv.estensione, sv.versione = "meteo_citta", n
    svs.passa(sv, "collaudo")
    b.tool_ctx.speaker_ctx = dario
    dario.sfida = C.nuova_sfida(cfg, b._speaker_key(), "sviluppo_collauda", {"dati": "Bergamo"})
    dario.sfida.scade = time.monotonic() + 60
    frase = dario.sfida.testo.replace(",", "")
    r, tools = parla(b, dario, frase)
    conta("4 sfida superata → l'esito del collaudo detto, una sola esecuzione",
          "18 gradi" in r and r != "Fatto." and tools.count("sviluppo_collauda") == 1,
          giro, frase, tools, r)

    # 5. la storpiatura con il lavoro dell'agente di mezzo
    cfg, reg, ctx, est, svc, b = nuovo(tmp / "storpiatura", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "estensione", "il meteo per città", titolo="Meteo per città")
    sv.specifica = "dice il meteo di una città qualunque"
    n = S.candidata(est)
    sv.estensione, sv.versione = "meteo_citta", n
    svs.passa(sv, "collaudo")
    b.record_announcement("Dario, il lavoro di «Meteo per città» è pronto: siamo al collaudo. "
                          "Con cosa provo? Per esempio di nuovo con «Bergamo, Cerro Maggiore e "
                          "Fontalba», che prima non andava.", fonte="agente")
    frase = "Direi che possiamo continuare con Bergamo e Cerno Maggiore e aggiungiamo Fontalba."
    r, tools = parla(b, dario, frase)
    conta("5 «Cerno Maggiore» detto → collaudo senza «viene dal lavoro di un agente»",
          "sviluppo_collauda" in tools and r.strip() and "non da te" not in r
          and "politica_argomento_esterno" not in (b.last_rules or []), giro, frase, tools, r)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro3-ollama-"))
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
    print(json.dumps(conteggi, ensure_ascii=False))
    # Misura, non soglia: esce con errore solo se un passo non riesce mai
    mai = [k for k, (ok, n) in conteggi.items() if ok == 0 and not k.startswith("2c")]
    print("\nTutto bene." if not mai else f"\nMai riusciti: {mai}")
    sys.exit(1 if mai else 0)


if __name__ == "__main__":
    main()
