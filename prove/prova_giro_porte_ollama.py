"""
Il giro vero della DGX del 12/10 (il gioco delle porte magiche) con il modello vero della voce
(Ollama locale, `llm_model`), il docker finto e il modello dell'agente finto di
prova_giro_porte (nomi di fantasia). Le frasi vere dei punti 2, 4 e 5 delle correzioni del 12/10
sera:

- **A** (punto 5, 12:20): alla revisione, con «Vuoi attivarla così com'è, o faccio continuare
  l'agente con quello che manca?» in sospeso, «No, farlo continuare con quello che manca.» e
  «Assolutamente deve continuare con quello che manca e fixare tutto quello che è rotto.» →
  sviluppo_passo completa (il lavoro riparte); contrario: «Va bene così, attivala.» → mai
  completa.
- **B** (punto 2, 08:38): al collaudo «Vorrei modificare le porte magiche di Borgofiore.» → una
  domanda, nessun lavoro né correzione.
- **C** (punto 4, 11:11): al collaudo, dopo la prova sullo schermo, «Scegliere la prima porta mi
  sembra che non porti a nulla.» → sviluppo_correggi (non sviluppo_chiedi).

Si contano i casi giusti; fallisce se A (le due frasi) non va almeno 2 volte su 3 per giro o se
B fa partire un lavoro.

    python prove\\prova_giro_porte_ollama.py      # 3 giri
    python prove\\prova_giro_porte_ollama.py 1    # 1 giro
    python prove\\prova_giro_porte_ollama.py 3 --prima   # A com'era prima, per confronto

Misura del 12/10 sera con gemma4 e4b (3 giri): A 5/6 (prima 6/6: l'e4b sceglieva già bene; il
caso vero era del 26B, che qui non c'è), «attivala» → la sfida 3/3 (prima 0/3: calliope_stato),
B 3/3 senza nessun lavoro partito, C 3/3.
"""

import os
import sys
import tempfile
from pathlib import Path

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_giro_porte as G  # noqa: E402
import prova_sviluppo_ollama as SO  # noqa: E402
from calliope.brain import Brain  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
# --prima: com'era prima del 12/10 sera per A (il messaggio di sempre, il blocco dello stato
# senza gli argomenti, nessuna spinta_sviluppo): il confronto
PRIMA = "--prima" in sys.argv
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def brain(cfg, reg, ctx):
    dario = SO.Voce("Dario", "amministra")
    ctx.speaker_ctx = dario
    b = Brain(cfg, reg, ctx)
    b.conv_owner = "u1"
    return b, dario


def caso(conteggi, chiave, ok, giro, frase, tools, r, sv):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] «{frase[:60]}» → {', '.join(tools) or '—'} "
          f"[{getattr(sv, 'fase', '—')}] {r[:180]!r}", flush=True)


def revisione(tmp, frase):
    cfg, reg, ctx, est, svc, sv, out = G.alla_revisione(tmp)
    b, dario = brain(cfg, reg, ctx)
    b.history += [{"role": "user", "content": "Possiamo passare alla revisione."},
                  {"role": "assistant", "content": G.detta(out)}]
    sosp = dict(out["in_sospeso"])
    if PRIMA:
        sosp.pop("messaggio", None)
        b._net_prima = b._net
        b._net = lambda nome: nome != "spinta_sviluppo" and b._net_prima(nome)
    b.set_pending(sosp)
    if PRIMA:
        b.pending["args_testo"] = False
    n = len(svc.lavori)
    r, tools, _ = SO.parla(b, dario, frase)
    return r, tools, sv, len(svc.lavori) > n, b


def sessione(giro, tmp, conteggi):
    for i, frase in enumerate(("No, farlo continuare con quello che manca.",
                               "Assolutamente deve continuare con quello che manca e fixare "
                               "tutto quello che è rotto.")):
        r, tools, sv, nuovo, b = revisione(tmp / f"a{i}", frase)
        caso(conteggi, "A seconda strada → completa", nuovo and sv.fase == "sviluppo", giro,
             frase, tools, r, sv)
        if "spinta_sviluppo" in (b.last_rules or []):
            conteggi.setdefault("A …con la spinta", [0, 0])[0] += 1
    r, tools, sv, nuovo, b = revisione(tmp / "a_contrario", "Va bene così, attivala.")
    caso(conteggi, "A contrario: «attivala» → mai completa", not nuovo, giro,
         "Va bene così, attivala.", tools, r, sv)

    agente = G.agente_chiedi()
    cfg, reg, ctx, est, svc, sv = G.al_collaudo(tmp / "b", agente)
    b, dario = brain(cfg, reg, ctx)
    n = len(svc.lavori)
    frase = "Vorrei modificare le porte magiche di Borgofiore."
    r, tools, _ = SO.parla(b, dario, frase)
    # Una domanda, o «dimmi cosa vorresti cambiare»: conta che niente parta
    caso(conteggi, "B «vorrei modificare» → niente parte, chiede cosa",
         len(svc.lavori) == n and "correggere" not in r,
         giro, frase, tools, r, sv)
    if "sviluppo_modifica_riempitivo" in (b.last_rules or []):
        conteggi.setdefault("B …con la regola del riempitivo", [0, 0])[0] += 1

    cfg, reg, ctx, est, svc, sv = G.al_collaudo(tmp / "c", G.agente_chiedi())
    from calliope.tools.sviluppo import ANTEPRIMA
    svc.sviluppi.collaudo(sv, ANTEPRIMA, True, "aperto in prova sullo schermo", anteprima=True)
    b, dario = brain(cfg, reg, ctx)
    b.history += [{"role": "user", "content": "Sì, aprilo in prova."},
                  {"role": "assistant", "content": f"Ecco «{sv.titolo}» in prova sullo schermo. "
                                                   "Quando l'hai provato, dimmi se va bene o "
                                                   "cosa cambiare."}]
    frase = "Scegliere la prima porta mi sembra che non porti a nulla."
    r, tools, _ = SO.parla(b, dario, frase)
    caso(conteggi, "C segnalazione → sviluppo_correggi", "sviluppo_correggi" in tools
         and "sviluppo_chiedi" not in tools, giro, frase, tools, r, sv)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-porte-ollama-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    conteggi: dict = {}
    for giro in range(1, GIRI + 1):
        sessione(giro, tmp0 / f"g{giro}", conteggi)
    print("\nRiepilogo (riusciti / casi):")
    for chiave, (k, n) in sorted(conteggi.items()):
        print(f"  {chiave:50} {k}/{n}")
    ka, na = conteggi.get("A seconda strada → completa", [0, 0])
    kb, nb = conteggi.get("B «vorrei modificare» → niente parte, chiede cosa", [0, 0])
    verifica("A: la seconda strada detta va a completa almeno 2 volte su 3", na and ka * 3 >= na * 2,
             f"{ka}/{na}")
    verifica("B: «vorrei modificare» non fa mai partire niente", kb == nb, f"{kb}/{nb}")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
