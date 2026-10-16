"""
Le parole dei minori nel terminale come quelle degli adulti (16/10/2026, decisione 0031, issue
#104; dal 12/10 sera al 16/10 erano nascoste, decisione 0028 T1).

    python prove/prova_console_minori.py

La console sulla DGX finisce nel journal di systemd, che resta: è conservazione anche lei. Dal
12/10 sera per un minore (e per una frase nel dubbio tra un adulto e un minore) si stampava come
per un ospite: «Tu: (una frase di un minore)», la risposta «…», i tool con i soli nomi degli
argomenti. Dal 16/10 chi amministra ha deciso che ciò che dice un minore di casa si conserva come
per un adulto: nel journal le sue frasi in chiaro; gli ospiti restano nascosti.

- `Ciclo`: `_mostra_richiesta` e `_rispondi` (con un modello finto che ripete la frase) per un
  minore riconosciuto, per una frase incerta tra un adulto e un minore e per un adulto (le parole
  si vedono); contrario: un ospite («(una frase di un ospite)», la risposta «…»);
- `Brain` con un backend finto: una dichiarazione trattenuta, una chiamata con un argomento di
  testo e il suo risultato, una risposta ripetuta; con un minore le parole si vedono come con un
  adulto, gli argomenti veri in memoria e nel registro dei turni; contrario: un ospite;
- `conserva.console_riservata`: ospite sì; minore, dubbio, adulto no; `minori.parla_minore`
  (la scelta di forma della frase dopo il tool) sì per minore e dubbio;
- `brain.tools_per_registro` (13/10): il meccanismo resta (argomenti a parte per il registro dei
  turni), anche se dal 16/10 nessuna chiamata lo usa.
Niente audio, modelli né rete: ~1 s.
"""
import contextlib
import io
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prova_minori_cancelli as MC  # noqa: E402

from calliope import conserva, corsie, minori  # noqa: E402
from calliope.brain import ARGOMENTI_REGISTRO, Brain, tools_per_registro  # noqa: E402
from calliope.ciclo import Ciclo, Servizi, Turno  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402

errori = 0
SEGRETO = "zucchero filato nascosto sotto il letto"


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(("ok  " if ok else "ERR ") + nome + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


def cattura(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn()
    return out.getvalue()


def prova_ciclo():
    import queue
    import tempfile
    import threading
    import time
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.uscita_controllo = False
    cfg.debug_audio_dir = None
    cfg.memory_db = os.path.join(tempfile.mkdtemp(prefix="calliope-console-"), "memoria.db")
    persone = MC.Persone()
    minori.prepara(cfg, registry=persone, log=lambda m: None)
    voce, cervello, chi = MC.Voce(), MC.Cervello(), MC.ChiParla()
    ascolto = types.SimpleNamespace(started_at=0.0, ended_at=0.0, on_speech_start=None,
                                    on_speech_end=None)
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=persone, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None),
                  attiva_minori=lambda: True, guardiano=MC.Guardia(cfg), wake=object(),
                  barge_in=False, barge_voice=False)
    srv.controllo_impronte[0] = time.monotonic()
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("sat:telefono"), ascolto, voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())

    def turno(nome, testo, come="voce", incerta=None):
        chi.current_speaker, chi.identified_by = nome, come
        chi.incerta = incerta
        t = Turno(text=testo, speaker_name=nome, prof_turno=persone.get(nome))
        c.rec = {}

        def giro():
            c._mostra_richiesta(t)
            c._rispondi(t)
        return cattura(giro), voce.detto[-1:]

    out, detto = turno("Tommaso", f"Calliope, ho {SEGRETO}.")
    verifica("minore: la frase e la risposta nel terminale (16/10, decisione 0031)",
             out.count(SEGRETO) >= 2 and "(una frase di un minore)" not in out, out[-300:])
    verifica("minore: la risposta detta per intero",
             detto and SEGRETO in detto[0] and "Calliope: " in out, out[-200:])
    out, _ = turno("Carlo", f"Calliope, ho {SEGRETO}.", come="conversazione",
                   incerta=("Carlo", "Tommaso"))
    verifica("dubbio tra un adulto e un minore: le parole nel terminale",
             SEGRETO in out and "(una frase di un minore)" not in out, out[-300:])
    out, _ = turno("Carlo", f"Calliope, ho {SEGRETO}.")
    verifica("un adulto → la frase e la risposta nel terminale come prima",
             out.count(SEGRETO) >= 2, out[-300:])
    chi.incerta = None
    out, _ = turno(None, f"Calliope, ho {SEGRETO}.", come=None)
    verifica("contrario: ospite, come prima: «(una frase di un ospite)» e la risposta «…»",
             SEGRETO not in out and "(una frase di un ospite)" in out, out[-300:])
    # Il registro dei turni (13/10): dalla lista in memoria di Brain, con gli argomenti veri;
    # con la chiave ARGOMENTI_REGISTRO quelli per il disco (dal 16/10 nessuno la mette: il
    # meccanismo resta); la lista in memoria non cambia
    vero = {"nome": "esercizi", "argomenti": {"azione": "piu_difficile"}, "ok": True,
            ARGOMENTI_REGISTRO: {"azione": "…"}}
    adulto = {"nome": "ricorda", "argomenti": {"fatto": SEGRETO}, "ok": True}
    cervello.last_tools = [vero, adulto]
    t = Turno(text="Calliope, più difficile.", speaker_name="Tommaso",
              prof_turno=persone.get("Tommaso"))
    c.rec = {}

    def registra():
        try:
            c._registra_risposta(t)
        except AttributeError:
            pass    # i controlli dopo (uscita, guardiano) vogliono un turno vero: qui non servono
    cattura(registra)
    scritti = c.rec.get("tool") or []
    verifica("registro dei turni: con la chiave, gli argomenti a parte",
             len(scritti) == 2 and scritti[0].get("argomenti") == {"azione": "…"}
             and ARGOMENTI_REGISTRO not in scritti[0], scritti)
    verifica("registro dei turni: le altre chiamate come sono",
             len(scritti) == 2 and scritti[1] == adulto, scritti)
    verifica("registro dei turni: in memoria gli argomenti veri restano",
             cervello.last_tools[0]["argomenti"] == {"azione": "piu_difficile"})
    cervello.last_tools = [adulto]
    verifica("senza la chiave la lista stessa, come prima",
             tools_per_registro(cervello.last_tools) is cervello.last_tools)
    minori.avvisi().close()


class _Backend:
    """Il backend finto di prova_brain: un copione di risposte (testo o chiamate)."""

    def __init__(self, copione):
        self.copione, self.visti = list(copione), []

    def stream(self, messages, tools, **k):
        self.visti.append(list(messages))
        yield from (self.copione.pop(0) if self.copione else [("text", "")])


def brain_per(nome, livello):
    cfg = Config()
    persone = MC.Persone()
    sc = MC.ChiParla()
    sc.current_speaker, sc.identified_by = nome, "voce"
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.tool_ctx = types.SimpleNamespace(speaker_ctx=sc, speakers=persone)
    b.backend = _Backend([
        [("text", f"Ho salvato che hai {SEGRETO}.")],
        [("calls", [{"id": "call_0", "name": "ricorda", "arguments": {"fatto": SEGRETO}}])],
        [("text", f"Va bene, {SEGRETO}.")],
    ])
    b.tools.call = lambda *a, **k: json.dumps({"ok": True, "conferma": f"Ricordo: {SEGRETO}."})
    return b


def prova_brain():
    b = brain_per("Tommaso", "familiare")
    out = cattura(lambda: "".join(b.stream_reply(f"Ricorda che ho {SEGRETO}.", "familiare")))
    # Dal 16/10 (decisione 0031) come un adulto: le parole, gli argomenti e il risultato
    verifica("Brain, minore: le parole sue e del modello nel terminale",
             SEGRETO in out and ("[TOOL] ricorda({'fatto': '" + SEGRETO + "'})") in out
             and "(riservato)" not in out, out[-400:])
    fatte = [x for x in b.last_tools if x.get("nome") == "ricorda"]
    verifica("Brain, minore: in memoria gli argomenti veri, nessun argomento a parte",
             bool(fatte) and fatte[0].get("argomenti") == {"fatto": SEGRETO}
             and ARGOMENTI_REGISTRO not in fatte[0], fatte and fatte[0])
    verifica("Brain, minore: per il registro dei turni gli argomenti veri",
             tools_per_registro(b.last_tools) is b.last_tools)
    b = brain_per("Carlo", "amministra")
    out = cattura(lambda: "".join(b.stream_reply(f"Ricorda che ho {SEGRETO}.", "amministra")))
    verifica("Brain, adulto → si vedono come prima", SEGRETO in out, out[-300:])
    fatte = [x for x in b.last_tools if x.get("nome") == "ricorda"]
    verifica("Brain, adulto → nessun argomento a parte per il registro",
             bool(fatte) and ARGOMENTI_REGISTRO not in fatte[0]
             and fatte[0].get("argomenti") == {"fatto": SEGRETO})
    b = brain_per(None, "ospite")
    out = cattura(lambda: "".join(b.stream_reply(f"Ricorda che ho {SEGRETO}.", "ospite")))
    verifica("contrario: Brain, ospite → niente argomenti né frasi del modello",
             SEGRETO not in out, out[-400:])


def prova_decisione():
    p = MC.Persone()
    sc = MC.ChiParla()
    casi = [((None, None), "ospite", False), (("Tommaso", "voce"), None, True),
            (("Carlo", "voce"), None, False)]
    for (nome, come), atteso, minore in casi:
        sc.current_speaker, sc.identified_by, sc.incerta = nome, come, None
        verifica(f"console_riservata {nome or 'ospite'} → {atteso}",
                 conserva.console_riservata(sc, p) == atteso)
        verifica(f"parla_minore {nome or 'ospite'} → {minore}",
                 minori.parla_minore(sc, p) is minore)
    sc.current_speaker, sc.identified_by, sc.incerta = "Carlo", "conversazione", ("Carlo",
                                                                                   "Tommaso")
    verifica("incerta tra Carlo e un minore: console in chiaro, parla_minore sì",
             conserva.console_riservata(sc, p) is None and minori.parla_minore(sc, p))
    sc.incerta, sc.minore_incerto = None, "Tommaso"
    verifica("minore_incerto: console in chiaro, parla_minore sì",
             conserva.console_riservata(sc, p) is None and minori.parla_minore(sc, p))
    sc.minore_incerto = None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    prova_decisione()
    prova_ciclo()
    prova_brain()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    sys.exit(1 if errori else 0)
