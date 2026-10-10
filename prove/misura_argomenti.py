"""
Misura: la forma dell'esito «argomento» (10/10/2026, § 13 del registro degli eventi). Tool
`argomento` o un campo di `proposta_rispondi`? Con il modello locale (gemma4 e4b su Ollama), con
il prompt e gli schemi veri di Calliope, `eventi: attivo`, i turni prima a copione e quello
misurato al modello.

    python prove/misura_argomenti.py [giri] [--forma tool|campo|tutte]

I casi vengono dai giri della DGX del 10/10 (Celsius → chilometri con e senza «ricominciamo»,
«ricominciamo» per «riprendiamo», «torniamo a…») e dai contrari (stesso argomento, «e poi?», la
risposta a una proposta, l'ora durante lo sviluppo). Per ogni caso e giro: i tool chiamati nella
prima passata, se la decisione sull'argomento è quella attesa, il tempo. Con la forma «campo» il
tool `argomento` non c'è e `proposta_rispondi` ha i campi `argomento` e `titolo`: vale solo con
una proposta aperta (gli altri casi non la possono esprimere). Nomi di fantasia. Alla fine
`ollama stop` del modello.
"""
import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope.brain import Brain, OllamaBackend  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.sviluppo import Sviluppi  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

from prova_eventi_attivo import GiroAttivo  # noqa: E402
from prova_politica import ChiParla, Persone  # noqa: E402

CELSIUS = "programma in Python che converte i gradi Celsius in Fahrenheit"


class Copione:
    def __init__(self):
        self.risposte = []

    def stream(self, messages, tools):
        yield from (self.risposte.pop(0) if self.risposte else [("text", "Va bene.")])


def chiama(nome, **a):
    return [("calls", [{"id": f"c-{nome}", "name": nome, "arguments": a}])]


class Registra:
    """Il backend vero che ricorda le chiamate della prima passata."""

    def __init__(self, be):
        self.be, self.passate = be, []

    def stream(self, messages, tools):
        chiamate = []
        for k, p in self.be.stream(messages, tools):
            if k == "calls":
                chiamate += [(c["name"], c.get("arguments") or {}) for c in p]
            yield k, p
        self.passate.append(chiamate)


def prepara(forma: str):
    cfg = Config()
    cfg.llm_num_ctx = 16384
    cfg.storia_inattiva_s = 0
    cfg.eventi = "attivo"
    tmp = tempfile.mkdtemp(prefix="misura-arg-")
    reg = build_registry(agenti=True)
    svs = Sviluppi(cfg, tmp, log=lambda m: None)
    fatti = []

    def sviluppo_apri(ctx, compito="", tipo="programma", **a):
        fatti.append(("sviluppo_apri", compito))
        sv = svs.corrente("dario")
        if sv is not None:
            return {"ok": False, "fatto": "NIENTE", "risposta_finale":
                    f"Adesso stiamo sviluppando «{sv.titolo}» e siamo all'analisi: «{compito}» "
                    f"è un altro programma, e ne seguo uno per volta. Vuoi sospendere il primo?"}
        sv = svs.apri("dario", "Dario", "programma", compito, compito)
        sv.specifica = compito
        d = "Va bene così, o la cambiamo?"
        return {"ok": True, "risposta_finale": f"Entriamo in modalità sviluppo per il "
                f"programma «{sv.titolo}». Ho capito così: {compito}. {d}",
                "in_sospeso": {"domanda": d, "tool": "sviluppo_apri", "cosa": "avviare il "
                               "lavoro", "argomenti": {"proposta": "L1"}}}

    def sviluppo_passo(ctx, azione="", quale="", cambia="", **a):
        fatti.append(("sviluppo_passo", azione, cambia))
        return {"ok": True, "risposta_finale": f"Ho capito così, con questa modifica: {cambia}. "
                                               f"Va bene così?"}
    for n, f in (("sviluppo_apri", sviluppo_apri), ("sviluppo_passo", sviluppo_passo)):
        reg.register(dataclasses.replace(reg.get(n), func=f))
    if forma == "campo":
        # proposta_rispondi con l'argomento come campo; il tool argomento non c'è
        p = reg.get("proposta_rispondi")
        props = dict(p.parameters["properties"])
        props["argomento"] = {"type": "string", "enum": ["stesso", "nuovo", "ripreso"],
                              "description": "se la frase cambia argomento (nuovo), torna a uno "
                                             "messo da parte (ripreso) o resta (stesso)"}
        props["titolo"] = {"type": "string", "description": "con nuovo o ripreso: il titolo "
                                                            "breve dell'argomento"}
        reg.register(dataclasses.replace(p, parameters={**p.parameters, "properties": props}))
        import calliope.brain as cb
        cb.SVILUPPO_ARGOMENTO = (" Se invece chi parla passa a un'altra cosa che non è questo "
                                 "sviluppo, rispondi alla proposta con proposta_rispondi esito "
                                 "altro e argomento nuovo, insieme ai tool della richiesta: "
                                 "questo sviluppo va in pausa da solo.")
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=ChiParla("Dario", "amministra"),
                      speaker=None, lavori=types.SimpleNamespace(sviluppi=svs, lavori=[]))
    b = Brain(cfg, reg, ctx)
    if forma == "campo":
        schemi = b.schemi
        b.schemi = lambda: [s for s in schemi() if s["function"]["name"] != "argomento"]
    b.backend = Copione()
    g = GiroAttivo(b)
    return b, g, svs, fatti, cfg


def turno(b, g, frase, *risposte):
    b.backend.risposte = list(risposte)
    return g.turno(frase, "amministra")


# Ogni caso: (nome, preparazione, frase, atteso) — atteso: "nuovo", "riprendi" o None (nessun
# cambio d'argomento); con la proposta aperta il caso vale anche per la forma «campo»
def celsius(b, g):
    turno(b, g, f"Scrivimi un {CELSIUS}.", chiama("sviluppo_apri", compito=CELSIUS,
                                                    tipo="programma"))


def celsius_poi_chilometri(b, g):
    celsius(b, g)
    b.backend.risposte = [chiama("argomento", azione="nuovo", titolo="chilometri in miglia"),
                          chiama("sviluppo_apri", compito="programma in Python che converte i "
                                 "chilometri in miglia", tipo="programma")]
    g.turno("Scrivimi un programma in Python che converte i chilometri in miglia.",
            "amministra")


def consigli_poi_meteo(b, g):
    turno(b, g, "Dimmi tre consigli per dormire meglio.",
          [("text", "Orari regolari, niente caffè la sera e una stanza buia.")])
    b.backend.risposte = [chiama("argomento", azione="nuovo", titolo="meteo di domani"),
                          [("text", "Domani sole a Borgoverde.")]]
    g.turno("Lasciamo perdere, che tempo farà domani?", "amministra")


CASI = [
    ("chilometri durante l'analisi di Celsius (giro 4, 11:47)", celsius,
     "Scrivimi un programma in Python che converte i chilometri in miglia.", "nuovo", True),
    ("«ricominciamo» durante l'analisi di Celsius (giro 3, 10:39)", celsius,
     "Ricominciamo.", "nuovo", True),
    ("«ricominciamo da capo» e una cosa nuova", celsius,
     "Ricominciamo da capo: scrivimi un programma che converte i chilometri in miglia.",
     "nuovo", True),
    ("«ricominciamo» per «riprendiamo» (i consigli messi da parte)", consigli_poi_meteo,
     "Ricominciamo da dove eravamo con i consigli per dormire.", "riprendi", False),
    ("«torniamo a…» (Celsius messo da parte)", celsius_poi_chilometri,
     "Torniamo al programma dei gradi.", "riprendi", False),
    # contrari
    ("contrario: dettaglio sullo stesso sviluppo", celsius,
     "Deve accettare anche i numeri decimali.", None, True),
    ("contrario: «sì» alla proposta aperta", celsius, "Sì, va bene così.", None, True),
    ("contrario: l'ora durante lo sviluppo", celsius, "Che ore sono?", None, True),
    ("contrario: «e poi?» dopo i consigli", lambda b, g: turno(
        b, g, "Dimmi tre consigli per dormire meglio.",
        [("text", "Orari regolari e niente caffè la sera.")]), "E poi?", None, False),
]


# «Ripeti il secondo» dopo un'interruzione e uno stop (giro 3, 10:43–10:44): con il promemoria
# della parte non detta la risposta ha il secondo consiglio
CONSIGLI = [("text", "Per dormire meglio ti consiglio tre cose. Primo, orari regolari anche nel "
                     "fine settimana. Secondo, niente caffè dopo le quattro del pomeriggio. "
                     "Terzo, la stanza buia e fresca.")]


def ripeti_secondo(giri: int) -> int:
    from prova_eventi_attivo import stop
    ok = 0
    for _ in range(giri):
        b, g, svs, fatti, cfg = prepara("tool")
        g.voce.interrompi_dopo = 2
        b.backend.risposte = [CONSIGLI]
        g.turno("Dimmi tre consigli per dormire meglio.", "amministra")
        g.voce.interrompi_dopo = None
        stop(g)
        b.backend = OllamaBackend(cfg)
        r = g.turno("Ripeti il secondo consiglio.", "amministra")
        bene = "caff" in r.lower()
        ok += bene
        print(f"  ripeti il secondo: {'sì' if bene else 'no'} «{r.strip()[:120]}»", flush=True)
    return ok


def decisione(chiamate, forma):
    for nome, a in chiamate:
        if forma == "tool" and nome == "argomento":
            az = str(a.get("azione") or "").lower()
            return "riprendi" if az.startswith("ripr") else "nuovo" if az else "?"
        if forma == "campo" and nome == "proposta_rispondi":
            v = str(a.get("argomento") or "stesso").lower()
            if v in ("nuovo", "ripreso"):
                return "riprendi" if v == "ripreso" else "nuovo"
    return None


def misura(forma, giri):
    righe = []
    for nome, prep, frase, atteso, con_proposta in CASI:
        if forma == "campo" and not con_proposta:
            righe.append((nome, None, "non esprimibile senza una proposta aperta", 0.0))
            continue
        ok = 0
        dettagli = []
        tempi = []
        for _ in range(giri):
            b, g, svs, fatti, cfg = prepara(forma)
            prep(b, g)
            rec = Registra(OllamaBackend(cfg))
            b.backend = rec
            t0 = time.perf_counter()
            g.turno(frase, "amministra")
            tempi.append(time.perf_counter() - t0)
            prima = rec.passate[0] if rec.passate else []
            d = decisione(prima, forma)
            ok += d == atteso
            dettagli.append(",".join(n for n, _ in prima) or "testo")
        righe.append((nome, ok, "; ".join(dettagli), sum(tempi) / len(tempi)))
        print(f"  [{forma}] {nome}: {ok}/{giri} ({'; '.join(dettagli)}) "
              f"{sum(tempi) / len(tempi):.1f} s", flush=True)
    return righe


def main():
    giri = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    forme = ["tool", "campo"]
    if "--forma" in sys.argv:
        f = sys.argv[sys.argv.index("--forma") + 1]
        forme = forme if f == "tutte" else [f]
    risultati = {}
    try:
        for forma in forme:
            print(f"— forma «{forma}», {giri} giri per caso", flush=True)
            risultati[forma] = misura(forma, giri)
    finally:
        subprocess.run(["ollama", "stop", Config().llm_model], capture_output=True)
    print(json.dumps(risultati, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
