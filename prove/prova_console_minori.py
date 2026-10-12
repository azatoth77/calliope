"""
Le parole dei minori non vanno nel terminale (12/10/2026 sera, decisione 0028 T1).

    python prove/prova_console_minori.py

Il registro dei turni non tiene il testo dei minori (calliope/conserva.py), ma la console, che
sulla DGX finisce nel journal di systemd e resta, stampava «Tu: <frase> (Nicola)», la risposta
di Calliope (che può ripetere ciò che ha detto il ragazzo), gli argomenti dei tool e le frasi del
modello trattenute dalle reti («[LLM] risposta uguale alla precedente…», «[TOOL] azione
dichiarata…»). Ora per un minore (e per una frase nel dubbio tra un adulto e un minore) come per
un ospite: «Tu: (una frase di un minore)», la risposta «…» frase per frase, i tool con i soli
nomi degli argomenti, le frasi del modello «…».

- `Ciclo`: `_mostra_richiesta` e `_rispondi` (con un modello finto che ripete la frase) per un
  minore riconosciuto, per una frase incerta tra un adulto e un minore e, come contrario, per un
  adulto (le parole restano);
- `Brain` con un backend finto: una dichiarazione trattenuta, una chiamata con un argomento di
  testo e il suo risultato, una risposta ripetuta; nessuna parola del minore in tutto l'output;
  contrario: con un adulto si vedono;
- `conserva.console_riservata`: ospite, minore, dubbio, adulto.
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
from calliope.brain import Brain  # noqa: E402
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
    verifica("minore: nessuna parola sua nel terminale", SEGRETO not in out, out[-300:])
    verifica("minore: «Tu: (una frase di un minore)»",
             "Tu: (una frase di un minore)" in out, out[:200])
    verifica("minore: la risposta detta per intero, nel terminale «…»",
             detto and SEGRETO in detto[0] and "Calliope: " in out and "…" in out, out[-200:])
    out, _ = turno("Carlo", f"Calliope, ho {SEGRETO}.", come="conversazione",
                   incerta=("Carlo", "Tommaso"))
    verifica("dubbio tra un adulto e un minore: come per il minore",
             SEGRETO not in out and "(una frase di un minore)" in out, out[-300:])
    out, _ = turno("Carlo", f"Calliope, ho {SEGRETO}.")
    verifica("contrario: un adulto → la frase e la risposta nel terminale come prima",
             out.count(SEGRETO) >= 2, out[-300:])
    chi.incerta = None
    out, _ = turno(None, f"Calliope, ho {SEGRETO}.", come=None)
    verifica("ospite: come prima", SEGRETO not in out and "(una frase di un ospite)" in out,
             out[-300:])
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
    verifica("Brain, minore: nessuna parola sua né del modello nel terminale",
             SEGRETO not in out and "[TOOL] ricorda(" in out, out[-400:])
    verifica("Brain, minore: gli argomenti con il solo nome", "'fatto': '…'" in out, out[-400:])
    b = brain_per("Carlo", "amministra")
    out = cattura(lambda: "".join(b.stream_reply(f"Ricorda che ho {SEGRETO}.", "amministra")))
    verifica("contrario: Brain, adulto → si vedono come prima", SEGRETO in out, out[-300:])


def prova_decisione():
    p = MC.Persone()
    sc = MC.ChiParla()
    casi = [((None, None), "ospite"), (("Tommaso", "voce"), "minore"),
            (("Carlo", "voce"), None)]
    for (nome, come), atteso in casi:
        sc.current_speaker, sc.identified_by, sc.incerta = nome, come, None
        verifica(f"console_riservata {nome or 'ospite'} → {atteso}",
                 conserva.console_riservata(sc, p) == atteso)
    sc.current_speaker, sc.identified_by, sc.incerta = "Carlo", "conversazione", ("Carlo",
                                                                                   "Tommaso")
    verifica("console_riservata: incerta tra Carlo e un minore → minore",
             conserva.console_riservata(sc, p) == "minore")
    sc.incerta, sc.minore_incerto = None, "Tommaso"
    verifica("console_riservata: minore_incerto → minore",
             conserva.console_riservata(sc, p) == "minore")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    prova_decisione()
    prova_ciclo()
    prova_brain()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    sys.exit(1 if errori else 0)
