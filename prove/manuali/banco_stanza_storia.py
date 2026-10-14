"""Banco della latenza con la conversazione di stanza (14/10/2026 sera, dopo la prova vera in
auto: «Turni con la stanza: prima frase p50 2,81 s (senza 1,3 s)», «Con il blocco: token riletti
p50 3908»). Con il modello vero della voce (Ollama), Brain vero con i tool di base, una
conversazione di più turni con righe della stanza che arrivano fra un turno e l'altro, tre modi
sulla stessa conversazione:

- `senza`: `stanza_contesto: false` (niente righe al modello: il riferimento);
- `blocco`: `stanza_contesto_in_storia: false` (il blocco intero ricostruito a ogni turno nei dati
  del turno, come il 14/10 mattina);
- `storia`: le righe nella storia in sola aggiunta (di serie dal 14/10 sera).

Per turno: prima frase, token riletti dal motore (`prompt_eval_count` meno la parte in cache) e
tempo di lettura; le mediane dal secondo turno (il primo legge il prefisso nuovo). Obiettivo del
progetto: `storia` entro +0,1 s da `senza`. Le righe hanno l'orologio finto (un turno ogni 150 s,
12 righe in mezzo, la finestra di 8 minuti piena come in auto). Nomi di fantasia. Non scrive
niente su disco; il servizio può restare acceso (stesso modello e stessa finestra).

Sul portatile:

    python prove\\manuali\\banco_stanza_storia.py --turni 10

Sulla DGX (il profilo della voce dal file locale, nella cartella dei dati):

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_stanza_storia.py --turni 10 --giri 2
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
from calliope.stanza import contesto as ctx_mod  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.preferred_voice = self.nascita = self.fascia = self.tono = None
        self.preferred_tone = None
        self.tutori = []


class Persone:
    P = {"Carlo": Prof("carlo-id", "Carlo", True), "Nicola": Prof("nicola-id", "Nicola"),
         "Bianca": Prof("bianca-id", "Bianca")}

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


class STTFinto:
    def transcribe(self, audio, **k):
        return ""


RIGHE = [("Nicola", "Sono arrivate due notifiche della scuola sul telefono."),
         ("Carlo", "Di cosa parlano?"),
         ("Nicola", "Una è sul programma della gita di primavera."),
         ("Nicola", "L'altra sui colloqui di venerdì pomeriggio."),
         ("Bianca", "Venerdì esco prima dal lavoro, ci vado io."),
         ("Carlo", "Allora io prendo Nicola agli allenamenti."),
         (None, "Traffico intenso sulla tangenziale in direzione nord."),
         ("Bianca", "Ricordatevi che stasera viene la nonna a cena."),
         ("Nicola", "Possiamo fare la pizza?"),
         ("Carlo", "Pizza va bene, la prendiamo alla piazzetta."),
         ("Bianca", "Allora prendo anche le bibite al supermercato."),
         ("Nicola", "E il gelato per dopo.")]
DOMANDE = ["Calliope, a cosa si riferiscono le notifiche?", "Calliope, che ore sono?",
           "Calliope, chi va ai colloqui?", "Calliope, tu che ne pensi della pizza?",
           "Calliope, cosa diceva Bianca?", "Calliope, quanto fa diciassette per tre?",
           "Calliope, cosa prendiamo per cena?", "Calliope, e il gelato chi lo prende?",
           "Calliope, riassumimi di cosa abbiamo parlato.", "Calliope, grazie."]


def conversazione(cfg, modo: str, turni: int, righe_per_turno: int):
    cfg.stanza, cfg.stanza_contesto = "ombra", modo != "senza"
    cfg.stanza_contesto_in_storia = modo == "storia"
    cfg.stanza_satelliti = []
    st = Stanza(cfg, STTFinto(), registry=Persone(), log=lambda m: None)
    st._info[1] = {"nome": "auto", "stanza": "auto", "canale": "satellite"}
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=Chi(), speaker=None)
    ctx.stanza = st
    b = Brain(cfg, build_registry(), ctx)
    t0 = time.time() - turni * 150 - 60
    out = []
    k = 0
    for n in range(turni):
        base = t0 + n * 150
        for j in range(righe_per_turno):
            chi, testo = RIGHE[k % len(RIGHE)]
            k += 1
            st.registro(1).aggiungi(
                "riga", segmento=k, versione=1, inizio=round(base + j * 10, 3),
                fine=round(base + j * 10 + 3, 3), testo=testo,
                chi=f"persona:{chi}" if chi else "ignoto", nome=chi,
                sicurezza="voce" if chi else "nessuna", p_min=None, rivolta="ignoto",
                minore=False)
        inizio = base + righe_per_turno * 10 + 5
        b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, inizio)
        frase = DOMANDE[n % len(DOMANDE)]
        t1 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, "amministra"):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t1
            parti.append(pezzo)
        risposta = re.sub(r"\s+", " ", "".join(parti)).strip()
        stt = getattr(b, "last_stanza_storia", None) or {}
        out.append({"turno": n + 1, "prima": primo, "riletti": getattr(b, "last_riletti", None),
                    "lettura": getattr(b, "last_lettura_s", None),
                    "nuove": stt.get("nuove"), "righe": stt.get("righe"),
                    "tool": [t.get("nome") for t in getattr(b, "last_tools", None) or ()]})
        print(f"  [{modo}] {n + 1:>2} prima frase "
              f"{'—' if primo is None else f'{primo:.2f} s'}, riletti {out[-1]['riletti']}, "
              f"lettura {out[-1]['lettura']} s, righe nuove {stt.get('nuove', '—')}, nella "
              f"storia {stt.get('righe', '—')}, tool {out[-1]['tool'] or '—'}: "
              f"«{frase}» → {risposta[:90]!r}", flush=True)
        th = getattr(b, "scalda_thread", None)
        if th is not None and th.is_alive():
            th.join(30)
    st.chiudi()
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
    ap.add_argument("--turni", type=int, default=10)
    ap.add_argument("--righe", type=int, default=12, help="righe nuove fra un turno e l'altro")
    ap.add_argument("--giri", type=int, default=1)
    ap.add_argument("--modi", default="senza,blocco,storia")
    a = ap.parse_args()
    cfg = load_config()
    print(f"modello: {cfg.llm_model} ({cfg.llm_backend}, profilo {cfg.llm_profilo})", flush=True)
    tutti: dict = {}
    for giro in range(1, a.giri + 1):
        for modo in a.modi.split(","):
            print(f"giro {giro}, modo {modo}", flush=True)
            tutti.setdefault(modo, []).extend(conversazione(cfg, modo, a.turni, a.righe)[1:])
    print("\nMediane dal secondo turno di ogni conversazione:")
    base = _med(m["prima"] for m in tutti.get("senza", []))
    for modo, ms in tutti.items():
        p = _med(m["prima"] for m in ms)
        delta = (f", {p - base:+.2f} s su «senza»" if base is not None and p is not None
                 and modo != "senza" else "")
        print(f"  {modo:>6}: prima frase {p} s{delta}; token riletti "
              f"{_med(m['riletti'] for m in ms)}; lettura {_med(m['lettura'] for m in ms)} s "
              f"({len(ms)} turni)")
    print("Obiettivo: «storia» entro +0,1 s da «senza».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
