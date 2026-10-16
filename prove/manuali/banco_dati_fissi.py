"""Banco della cache del prefisso con i dati del turno, col modello vero (16/10/2026, issue #95).

Brain vero con i tool di base e il modello della voce (Ollama), chi amministra con ricordi e
avvisi ai tutori come il 15/10 sulla DGX (nomi di fantasia), una conversazione di `--turni` turni
in due modi sulla stessa conversazione:

- `prima`: `dati_stabili_in_storia: false` (ricordi e avvisi nei dati del turno, come fino al
  15/10: spariscono alla richiesta dopo);
- `dopo`: i dati che cambiano di rado nella storia in sola aggiunta (di serie dal 16/10).

Per turno: prima frase, token riletti dal motore e ripresi dalla cache (`prompt_eval_count` e
`prompt_eval_cached_count` della prima passata), lettura, dati del turno stimati; le mediane dal
secondo turno. Con la cache persa i ripresi restano fermi (il primo checkpoint, ~prompt di sistema
e tool) e i riletti crescono col contesto; con la cache che regge i ripresi crescono e i riletti
restano poche centinaia.

**Sposta la cache del modello**: sulla DGX solo a Calliope ferma o inattiva (al turno dopo la
rifà da sé, una volta), o su un Ollama di prova (`--url`). Sul portatile, con un Ollama di prova
su un'altra porta (vedi `banco_cache_swa.py`):

    python prove\\manuali\\banco_dati_fissi.py --url http://127.0.0.1:11500 --turni 8

Sulla DGX (il profilo della voce dal file locale):

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_dati_fissi.py --turni 10 --giri 2

Non scrive niente su disco.
"""

import argparse
import os
import re
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope.brain import Brain  # noqa: E402
from calliope.config import load_config  # noqa: E402
from calliope.memory import HOUSE  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.preferred_voice = self.nascita = self.fascia = self.tono = None
        self.preferred_tone = None
        self.tutori = []


class Persone:
    P = {"Carlo": Prof("carlo-id", "Carlo", True)}

    def get(self, n):
        return self.P.get(n)

    def known_speakers(self):
        return list(self.P)


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "amministra", "voce"
    from_session = False
    sfida = incerta = minore_vicino = None
    voce_sicura, conferma_breve, sfida_superata = "Carlo", False, False
    compagnia = compagnia_sconosciute = senza_nome = False


class Memoria:
    F = {"carlo-id": ["a Carlo piace la pizza margherita", "Carlo corre il martedì mattina",
                      "il dentista di Carlo è il dottor Lanfranchi",
                      "Carlo preferisce il caffè senza zucchero",
                      "la macchina di Carlo va in revisione a novembre"],
         HOUSE: ["la password del wifi è sul frigorifero",
                 "la caldaia si resetta col pulsante rosso"]}

    def facts(self, pid):
        return list(self.F.get(pid, ()))


AVVISI = ("Avvisi consegnati di recente a te come tutore (testi di Calliope, mai le parole del "
          "minore; non inventare dettagli): ieri alle 17:40, avviso «parole forti» per Nicola dal "
          "satellite «camera», consegnato sul telefono, stato: letto; oggi alle 08:10, avviso "
          "«richiesta insolita» per Nicola dal satellite «studio», consegnato a voce, stato: non "
          "ancora letto; oggi alle 12:30, avviso «sito non adatto» per Nicola dal satellite "
          "«studio», consegnato sullo schermo, stato: non ancora letto. Se te ne chiedono, "
          "rispondi con questi dati e la data; per il resto chiama i tool come sempre.")

DOMANDE = ["Calliope, mi consigli un libro per l'autunno?", "Calliope, come si fa il pane?",
           "Calliope, cosa vuol dire resilienza?", "Calliope, dimmi un proverbio sulla pioggia.",
           "Calliope, perché le foglie cambiano colore?", "Calliope, come si dice grazie in "
           "tedesco?", "Calliope, qual è il fiume più lungo d'Italia?",
           "Calliope, raccontami una curiosità sui gatti.", "Calliope, cos'è un haiku?",
           "Calliope, grazie mille."]


def conversazione(cfg, modo: str, turni: int):
    cfg.dati_stabili_in_storia = modo == "dopo"
    cfg.stanza = "spento"
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=Chi(), speaker=None)
    ctx.memory = Memoria()
    b = Brain(cfg, build_registry(), ctx)
    out = []
    for n in range(turni):
        b.avvisi_turno = AVVISI
        frase = DOMANDE[n % len(DOMANDE)]
        t1 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, "amministra"):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t1
            parti.append(pezzo)
        risposta = re.sub(r"\s+", " ", "".join(parti)).strip()
        out.append({"turno": n + 1, "prima": primo, "riletti": getattr(b, "last_riletti", None),
                    "ripresi": getattr(b, "last_ripresi", None),
                    "lettura": getattr(b, "last_lettura_s", None),
                    "dati": getattr(b, "last_dati_turno_token", None),
                    "tool": [t.get("nome") for t in getattr(b, "last_tools", None) or ()]})
        o = out[-1]
        print(f"  [{modo}] {n + 1:>2} prima frase {'—' if primo is None else f'{primo:.2f} s'}, "
              f"riletti {o['riletti']}, ripresi {o['ripresi']}, lettura {o['lettura']} s, dati "
              f"del turno {o['dati']}, tool {o['tool'] or '—'}: → {risposta[:70]!r}", flush=True)
    return out


def _med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.median(xs), 2) if xs else None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--turni", type=int, default=8)
    ap.add_argument("--giri", type=int, default=1)
    ap.add_argument("--modi", default="prima,dopo")
    ap.add_argument("--url", default="", help="un altro Ollama (di prova) al posto di quello "
                                              "della configurazione")
    a = ap.parse_args()
    cfg = load_config()
    if a.url:
        cfg.llm_native_url = a.url
    print(f"modello: {cfg.llm_model} ({cfg.llm_backend}, {cfg.llm_native_url})", flush=True)
    tutti: dict = {}
    for giro in range(1, a.giri + 1):
        for modo in a.modi.split(","):
            print(f"giro {giro}, modo {modo}", flush=True)
            tutti.setdefault(modo, []).extend(conversazione(cfg, modo, a.turni)[1:])
    print("\nMediane dal secondo turno di ogni conversazione:")
    for modo, ms in tutti.items():
        print(f"  {modo:>5}: prima frase {_med(m['prima'] for m in ms)} s; riletti "
              f"{_med(m['riletti'] for m in ms)}; ripresi {_med(m['ripresi'] for m in ms)}; "
              f"lettura {_med(m['lettura'] for m in ms)} s; dati del turno "
              f"{_med(m['dati'] for m in ms)} ({len(ms)} turni)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
