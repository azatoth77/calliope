"""Il giro 6 della modalità sviluppo con il modello vero della voce (Ollama locale,
`llm_model`), il docker FINTO e un servizio dei lavori finto (08/10/2026). Dal giro vero della
DGX dell'08/10 sera (19:06–20:13), con nomi di fantasia (prove/prova_sviluppo_giro6.py per il
resto):

1. con l'agente al lavoro, «Fermo lo sviluppo.» e «Stoppa lo sviluppo, non deve più
   continuare.» → il lavoro si ferma (`ferma`, o `lavoro_annulla`); contrario: «Mettiamo in
   pausa lo sviluppo, ne riparliamo dopo.» → il lavoro continua; e «sospendi» seguito da «No,
   fermalo, non deve più continuare» → fermato;
2. dopo il lavoro fermato, «a che punto siamo?» e poi «Sì, rifallo.» / «Niente, partiamo così
   com'è.» → il lavoro riparte subito (mai la specifica riletta); contrario: «No, prima
   cambiamo: aggiungi anche il vento.» → nessun lavoro avviato;
3. al collaudo, «io direi di provare con Valfiorita e Borgo Alto» → un collaudo per città (una
   chiamata per valore, o una con l'elenco divisa da `collaudo_piu_valori`), mai «non ho ancora
   ricevuto i dati»; poi «E invece Pratofiorito Maggiore?» → un collaudo; contrario: «Prova
   con Bosco e Prato: è un paese solo» → un collaudo con il nome intero.

    python prove\\prova_sviluppo_giro6_ollama.py      # 3 giri
    python prove\\prova_sviluppo_giro6_ollama.py 1    # 1 giro
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


def al_lavoro(tmp, iso, dario):
    """Al collaudo, poi una correzione: l'agente al lavoro (servizio finto, `in_corso`)."""
    cfg, reg, ctx, est, svc, b = G4O.nuovo(tmp, iso)
    b.tool_ctx.speaker_ctx = dario
    ctx.speaker_ctx = dario
    G.al_collaudo(ctx, est, svc)
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": "con le città di due parole non va"},
             turno=3)
    sv = svc.sviluppi.corrente("u1")
    lav = svc.lavori[-1]
    b.turn_number = ctx.turno = 5
    return cfg, reg, ctx, est, svc, b, sv, lav


def fermato(svc, lav, tools) -> bool:
    return lav.stato == "annullato" or "lavoro_annulla" in tools


def sessione(giro, tmp, iso):
    dario = SO.Voce("Dario", "amministra")
    # 1. ferma / sospendi
    for i, (chiave, frase, atteso) in enumerate((
            ("1a «Fermo lo sviluppo.» → il lavoro si ferma", "Fermo lo sviluppo.", True),
            ("1b «Stoppa lo sviluppo…» → il lavoro si ferma",
             "Stoppa lo sviluppo, non deve più continuare.", True),
            ("1c contrario «mettiamo in pausa» → il lavoro continua",
             "Mettiamo in pausa lo sviluppo, ne riparliamo dopo.", False))):
        cfg, reg, ctx, est, svc, b, sv, lav = al_lavoro(tmp / f"ferma{i}", iso, dario)
        r, tools = G4O.parla(b, dario, frase)
        conta(chiave, fermato(svc, lav, tools) == atteso, giro, frase, tools, r)
    cfg, reg, ctx, est, svc, b, sv, lav = al_lavoro(tmp / "sospendi", iso, dario)
    r0, t0 = G4O.parla(b, dario, "Sospendi lo sviluppo, ne parliamo dopo.")
    frase = "Ma in che senso finisce il suo lavoro? Fermalo, non deve più continuare."
    r, tools = G4O.parla(b, dario, frase)
    conta("1d dopo «sospendi», «Fermalo, non deve più continuare» → fermato",
          fermato(svc, lav, tools), giro, frase, tools, r,
          f"(prima: {', '.join(t0) or '—'} {r0[:80]!r})")

    # 2. rifai
    for i, (chiave, frase, atteso) in enumerate((
            ("2a «Sì, rifallo.» → riparte subito", "Sì, rifallo.", True),
            ("2b «partiamo così com'è» → riparte subito",
             "Niente, partiamo con lo sviluppo esattamente così com'è.", True),
            ("2c contrario «cambiamo: aggiungi il vento» → nessun lavoro avviato",
             "No, prima cambiamo: aggiungi anche il vento.", False))):
        cfg, reg, ctx, est, svc, b, sv, lav = al_lavoro(tmp / f"rifai{i}", iso, dario)
        P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"})
        r1, t1 = G4O.parla(b, dario, "Calliope, a che punto siamo con lo sviluppo?")
        k = len(svc.lavori)
        r, tools = G4O.parla(b, dario, frase)
        partito = len(svc.lavori) > k and sv.lavoro == svc.lavori[-1].id \
            and svc.lavori[-1].stato == "in_corso"
        ok = partito == atteso and (not atteso or "Ho capito così" not in r)
        conta(chiave, ok, giro, frase, tools, r, f"(prima: {', '.join(t1) or '—'} {r1[:90]!r})")

    # 3. più collaudi
    cfg, reg, ctx, est, svc, b = G4O.nuovo(tmp / "collaudi", iso)
    b.tool_ctx.speaker_ctx = dario
    G.al_collaudo(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    b.record_announcement("Dario, il lavoro di «Meteo città» è pronto: siamo al collaudo. La "
                          "versione 2 non è ancora attiva: prima la proviamo. Con cosa provo?",
                          fonte="agente")
    frase = "Allora, io direi di provare con Valfiorita e Borgo Alto."
    k = len(sv.collaudi)
    r, tools = G4O.parla(b, dario, frase)
    citta = {str((c.get("argomenti") or {}).get("citta", "")).strip().lower()
             for c in sv.collaudi[k:]}
    attesa = any(x in r.lower() for x in ("ancora ricevuto", "in attesa", "aspett"))
    conta("3a «Valfiorita e Borgo Alto» → due collaudi", {"valfiorita", "borgo alto"} <= citta
          and not attesa, giro, frase, tools, r,
          json.dumps(sorted(citta)) + (" (divisi)" if "collaudo_piu_valori" in
                                       (b.last_rules or []) else ""))
    frase = "E invece Pratofiorito Maggiore?"
    k = len(sv.collaudi)
    r, tools = G4O.parla(b, dario, frase)
    citta = [str((c.get("argomenti") or {}).get("citta", "")).strip().lower()
             for c in sv.collaudi[k:]]
    conta("3b «E invece Pratofiorito Maggiore?» → un collaudo", "pratofiorito maggiore" in citta,
          giro, frase, tools, r, json.dumps(citta))
    cfg, reg, ctx, est, svc, b = G4O.nuovo(tmp / "bosco", iso)
    b.tool_ctx.speaker_ctx = dario
    G.al_collaudo(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    frase = "Prova con Bosco e Prato: è un paese solo, si chiama proprio così."
    r, tools = G4O.parla(b, dario, frase)
    citta = [str((c.get("argomenti") or {}).get("citta", "")).strip().lower()
             for c in sv.collaudi]
    conta("3c contrario «Bosco e Prato, un paese solo» → un collaudo col nome intero",
          citta == ["bosco e prato"], giro, frase, tools, r, json.dumps(citta))


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro6-ollama-"))
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
