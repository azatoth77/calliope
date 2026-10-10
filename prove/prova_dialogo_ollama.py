import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Lo stato del dialogo in ombra con il modello vero (10/10/2026): gemma4 e4b sull'Ollama di
questo PC (il 4B; il 26B della DGX si misura là). Mai l'Ollama della DGX.
prova_stato_dialogo.py è la stessa a secco.

Per ogni proposta aperta (tre tipi: «La apro?» di un tool, E1; «Vuoi che accenda la luce della
taverna?» di un tool, E1; «vuoi che registri la voce di Ettore?» della politica, E4) e per ogni
frase della persona (le frasi strane del registro e del § 3.5 dell'analisi delle regole del 09/10,
con l'esito che ci si aspetta), in due modi:

- **ombra** (`dialogo_interprete: ombra`, il predefinito): il blocco dello stato e il tool
  `proposta_rispondi`; si conta quante volte il modello lo chiama, con quale esito, quante volte
  chiama direttamente il tool proposto (il sì implicito di oggi) e quante nessuno dei due;
- **spento**: il percorso di prima (PENDING_MSG, nessuno schema in più).

Poi: l'accordo fra i due modi (stessa esecuzione per la stessa frase: in ombra decide ancora la
politica di oggi), l'esito giusto del modello, e la latenza della prima frase (prima risposta
detta) e della lettura del prompt con e senza. Le soglie non bloccano: è una misura (esce con 1
solo se un «no» esegue).

    python prove\\prova_dialogo_ollama.py [giri]        # 1 giro: ~3–5 minuti
"""

import dataclasses
import statistics
import time

from calliope import stato_dialogo as sd
from calliope.brain import make_backend
from prove.prova_politica import chiama
from prove.prova_stato_dialogo import DARIO, ETTORE, prepara

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1

FRASI = [
    ("Sì.", "si"), ("Sì, grazie.", "si"), ("Ok, vai.", "si"), ("Ma sì dai, perché no?", "si"),
    ("Calliope, ok.", "si"), ("No, mi va bene.", "si"), ("Sì, non c'è problema.", "si"),
    ("Sì, certo, non preoccuparti.", "si"),
    ("No.", "no"), ("No, lascia stare.", "no"), ("Per ora no, grazie.", "no"),
    ("Sì, però fallo dopo.", "rinvio"), ("Magari stasera.", "rinvio"),
    ("Giusto per sapere, che ore sono?", "altro"),
    ("Sì, però ascolta, stiamo uscendo a cena.", "altro"), ("Sicuro?", "altro"),
]
TOOL_DI = {"apri": "pc_apri_file", "luce": "casa_comando", "registra": "registra_utente"}
CORREZIONE = {"apri": ("No, quella di settembre.", "correzione"),
              "luce": ("No, quella del bagno.", "correzione")}


def apri_proposta(b, tipo):
    """La proposta aperta, con la domanda già detta nella storia; il modello vero dopo."""
    if tipo == "registra":
        b.backend.risposte = [chiama("registra_utente", ETTORE)]
        "".join(b.stream_reply("Un mio amico qua con me si chiama Ettore.", "amministra"))
    else:
        domanda, offerta = {
            "apri": ("Ho trovato la bolletta di agosto. La apro?",
                     {"tool": "pc_apri_file", "domanda": "Ho trovato la bolletta di agosto. "
                      "La apro?", "cosa": "aprire la bolletta di agosto",
                      "argomenti": {"risultato": 1}}),
            "luce": ("Vuoi che accenda la luce della taverna?",
                     {"tool": "casa_comando", "domanda": "Vuoi che accenda la luce della "
                      "taverna?", "cosa": "accenda la luce della taverna",
                      "argomenti": {"comando": "accendi la luce della taverna"}})}[tipo]
        richiesta = {"apri": "Cercami la bolletta di agosto.",
                     "luce": "Fa buio giù in taverna."}[tipo]
        b.history.extend([{"role": "user", "content": richiesta},
                          {"role": "assistant", "content": domanda}])
        b._c().turn_number = 1
        b.set_pending(offerta)
        b.pending["turno"] = 1
    b.last_turn_at = time.monotonic()
    return b.has_pending()


def caso(modo, tipo, frase):
    b, eseguiti = prepara(modo)
    b.tool_ctx.speaker_ctx = DARIO()

    def apri(ctx, **a):
        eseguiti.append(("pc_apri_file", dict(a)))
        return {"ok": True, "risposta_finale": "Apro la bolletta."}
    b.tools.register(dataclasses.replace(b.tools.get("pc_apri_file"), func=apri))
    if not apri_proposta(b, tipo):
        return None
    prima = len(eseguiti)
    b.backend = make_backend(b.cfg)
    t0 = time.perf_counter()
    primo = None
    detto = []
    for pezzo in b.stream_reply(frase, "amministra"):
        if primo is None and pezzo.strip():
            primo = time.perf_counter() - t0
        detto.append(pezzo)
    o = b.last_dialogo_ombra or {}
    tool = [t["nome"] for t in b.last_tools]
    return {"modello": o.get("modello"), "scartate": o.get("scartate"),
            "diretta": (bool(o.get("diretta")) if modo == "ombra" else TOOL_DI[tipo] in tool),
            "eseguito": len(eseguiti) > prima, "primo": primo,
            "lettura": getattr(b, "last_lettura_s", None), "detto": "".join(detto)[:120],
            "tool": tool, "oggi": o.get("oggi"), "accordo": o.get("accordo")}


def main():
    t_inizio = time.perf_counter()
    risultati = {"ombra": [], "spento": []}
    for g in range(1, GIRI + 1):
        for modo in ("ombra", "spento"):
            for tipo in ("apri", "luce", "registra"):
                frasi = FRASI + ([CORREZIONE[tipo]] if tipo in CORREZIONE else [])
                for frase, atteso in frasi:
                    r = caso(modo, tipo, frase)
                    if r is None:
                        print(f"   [{modo} {tipo}] proposta non aperta: salto «{frase}»")
                        continue
                    r.update(tipo=tipo, frase=frase, atteso=atteso, giro=g)
                    risultati[modo].append(r)
                    print(f"   [{modo} {tipo}] «{frase}» → modello={r['modello']} "
                          f"diretta={r['diretta']} eseguito={r['eseguito']} tool={r['tool']} "
                          f"primo={r['primo'] or 0:.2f}s «{r['detto']}»", flush=True)
    om, sp = risultati["ombra"], risultati["spento"]
    n = len(om)
    chiama_n = sum(1 for r in om if r["modello"])
    diretta_n = sum(1 for r in om if not r["modello"] and r["diretta"])
    nessuno = n - chiama_n - diretta_n
    giusto = sum(1 for r in om if r["modello"] == r["atteso"])
    print(f"\nOMBRA: {n} risposte a una proposta; proposta_rispondi chiamato {chiama_n} "
          f"({100 * chiama_n / max(1, n):.0f} %), tool proposto chiamato direttamente {diretta_n}, "
          f"nessuno dei due {nessuno}; esito uguale a quello atteso {giusto}/{chiama_n}")
    # Corsia veloce o modello: quante risposte avrebbero un esito strutturato (per il passo 2)
    from calliope.risposte import forma_chiusa
    coperte = sum(1 for r in om if r["modello"] or forma_chiusa(r["frase"]))
    print(f"   con la corsia veloce: esito strutturato per {coperte}/{n} risposte "
          f"({100 * coperte / max(1, n):.0f} %); il resto resta al percorso di oggi")
    per_atteso = {}
    for r in om:
        d = per_atteso.setdefault(r["atteso"], {"n": 0, "chiama": 0, "giusto": 0, "eseguito": 0})
        d["n"] += 1
        d["chiama"] += bool(r["modello"])
        d["giusto"] += r["modello"] == r["atteso"]
        d["eseguito"] += r["eseguito"]
    for k, d in per_atteso.items():
        print(f"   atteso «{k}»: {d['n']} frasi, chiama {d['chiama']}, esito giusto "
              f"{d['giusto']}, eseguite {d['eseguito']}")
    for tipo in ("apri", "luce", "registra"):
        xs = [r for r in om if r["tipo"] == tipo]
        print(f"   proposta «{tipo}»: chiama {sum(bool(r['modello']) for r in xs)}/{len(xs)}, "
              f"diretta {sum(bool(r['diretta']) and not r['modello'] for r in xs)}")
    # Accordo fra i due modi: la stessa frase esegue (o no) nei due modi
    chiave = lambda r: (r["giro"], r["tipo"], r["frase"])  # noqa: E731
    sp_d = {chiave(r): r for r in sp}
    coppie = [(r, sp_d[chiave(r)]) for r in om if chiave(r) in sp_d]
    uguali = sum(1 for a, b in coppie if a["eseguito"] == b["eseguito"])
    print(f"ACCORDO ombra/spento (stessa esecuzione per la stessa frase): {uguali}/{len(coppie)}")
    for a, b in coppie:
        if a["eseguito"] != b["eseguito"]:
            print(f"   diversa: [{a['tipo']}] «{a['frase']}» ombra eseguito={a['eseguito']} "
                  f"(modello={a['modello']}) spento eseguito={b['eseguito']}")
    no_eseguiti = [r for r in om + sp if r["atteso"] == "no" and r["eseguito"]]
    print(f"«no» eseguiti: {len(no_eseguiti)}")

    def mediana(xs, k):
        v = [x[k] for x in xs[1:] if isinstance(x.get(k), (int, float))]  # il primo scalda
        return statistics.median(v) if v else None
    for k, nome in (("primo", "prima frase"), ("lettura", "lettura del prompt")):
        a, b = mediana(om, k), mediana(sp, k)
        print(f"LATENZA {nome}: ombra {a or 0:.2f} s, spento {b or 0:.2f} s, differenza "
              f"{(a or 0) - (b or 0):+.2f} s")
    print(f"{time.perf_counter() - t_inizio:.0f} s")
    return 1 if no_eseguiti else 0


if __name__ == "__main__":
    sys.exit(main())
