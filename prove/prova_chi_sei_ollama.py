import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Chi è Calliope, le sue novità e «cosa sai fare?» per aree, con il modello vero (09/10/2026).

Caso vero della DGX (09/10): «Hai modo di sapere quali sono state le ultime novità sul tuo
aggiornamento?» → l'elenco intero delle capacità, «non ho un registro delle versioni», «il mio
codice è distribuito su diversi server». Qui le frasi come dette a voce: il tool giusto con gli
argomenti giusti (cosa=novita, periodo, chi_sei, area) e la risposta senza invenzioni; i
contrari («chi sono?», «che ore sono?», «cosa c'è nella lista della spesa?», «chi ha inventato
il telefono?») non chiamano calliope_stato per sé.

    python prove\\prova_chi_sei_ollama.py        # 2 giri
    python prove\\prova_chi_sei_ollama.py 1      # 1 giro
"""

import re
import time

from calliope import capacita
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.pc_finto import FakePC

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario"), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


def registro_finto() -> capacita.Registro:
    reg = capacita.Registro()
    for nome in ("llm", "stt", "voce", "wake", "chi_parla", "audio", "memoria", "pc",
                 "documenti", "casa", "schermi", "agenti"):
        reg.segnala(nome, "attiva")
    reg.segnala("biblioteca", "mancante", "mancano i file di Wikipedia",
                "Dimmi «scarica la biblioteca».")
    return reg


# Invenzioni su di sé del caso vero e simili
INVENTA = re.compile(r"divers[ie] server|nel cloud(?! *:)|non ho (un|accesso a( un)?) "
                     r"registro|server remot|data ?center|OpenAI|Google", re.I)


def args(tools, nome="calliope_stato"):
    return [t["argomenti"] for t in tools if t["nome"] == nome]


def novita(t, r, periodo=None):
    a = args(t)
    # Solo il periodo vale come novità (regola stato_periodo_novita, tools/stato.py)
    return (any((x.get("cosa") == "novita" or (not x.get("cosa") and x.get("periodo"))) and (periodo is None or x.get("periodo") == periodo)
                for x in a) and "versione" in r.lower() and not INVENTA.search(r))


def chi_sei(t, r):
    return (any(x.get("cosa") == "chi_sei" for x in args(t)) and not INVENTA.search(r)
            and "AGPL" in r)


def solo_aree(t, r):
    return (any(x.get("cosa") in (None, "", "sa_fare") and not x.get("area") for x in args(t))
            and r.startswith("Posso aiutarti con") and "luci" not in r and len(r.split()) < 70)


def area(chiave, parola):
    return lambda t, r: (any(x.get("area") == chiave for x in args(t))
                         and parola in r.lower())


def non_stato(t, r):
    return not any(x.get("cosa") in ("novita", "chi_sei") for x in args(t))


# (sessione, chi, livello, frase, controllo(tools, risposta), contrario?)
CASI = [
    ("n1", "Dario", "amministra", "Hai modo di sapere quali sono state le ultime novità sul "
     "tuo aggiornamento?", lambda t, r: novita(t, r), False),
    ("n2", "Dario", "amministra", "Quali sono le novità?", lambda t, r: novita(t, r), False),
    ("n3", "Bianca", "familiare", "Cosa è cambiato da ieri?",
     lambda t, r: novita(t, r, "da_ieri"), False),
    ("n4", "Dario", "amministra", "Che versione sei?",
     lambda t, r: any(x.get("cosa") in ("novita", "chi_sei") for x in args(t))
     and "versione" in r.lower() and not INVENTA.search(r), False),
    ("c1", "Dario", "amministra", "Dove gira il tuo codice?", chi_sei, False),
    ("c2", "Bianca", "familiare", "Chi ti ha programmato?", chi_sei, False),
    # «Chi sei?» con una frase sola vera va bene anche senza tool (niente invenzioni)
    ("c3", "Dario", "amministra", "Chi sei?",
     lambda t, r: chi_sei(t, r) or (not t and "Calliope" in r and not INVENTA.search(r)
                                    and len(r.split()) < 30), False),
    ("s1", "Dario", "amministra", "Cosa sai fare?", solo_aree, False),
    ("s1", "Dario", "amministra", "E cosa sai fare con la casa?", area("casa", "luci"), False),
    ("s2", "Bianca", "familiare", "Cosa sai fare con i documenti?",
     area("documenti", "word"), False),
    ("s3", "Dario", "amministra", "Cosa puoi fare con il computer?", area("pc", "volume"), False),
    ("s4", "Bianca", "familiare", "Cosa puoi fare per i miei appuntamenti e i promemoria?",
     area("agenda", "promemoria"), False),
    # Contrari: niente novità né chi sei
    ("x1", "Dario", "amministra", "Chi sono?", non_stato, True),
    ("x2", "Dario", "amministra", "Che ore sono?", non_stato, True),
    ("x3", "Bianca", "familiare", "Cosa c'è nella lista della spesa?", non_stato, True),
    ("x4", "Dario", "amministra", "Chi ha inventato il telefono?", non_stato, True),
]

righe = []
for giro in range(1, GIRI + 1):
    cfg = Config()
    pcs = {"portatile": FakePC(volume=40, luminosita=80)}
    reg = build_registry(pc=pcs, documenti=FORMATI, casa=True, schermi=True, agenti=True)
    registro = registro_finto()
    brains = {}
    for sessione, chi, livello, frase, controllo, contrario in CASI:
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, pc=pcs, capacita=registro)
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        b.tool_ctx.speaker_ctx = SpeakerCtx(chi, livello)
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        tools = list(b.last_tools)
        try:
            ok = bool(controllo(tools, risposta))
        except Exception as e:  # noqa: BLE001
            ok, risposta = False, f"{risposta} [controllo: {e}]"
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in tools) or "—"
        verifica(f"[{giro}] {'contrario ' if contrario else ''}{chi}: «{frase}» → {argomenti}",
                 ok, f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:220]!r}")
        righe.append((giro, frase, ok, primo or 0, totale))

prime = sorted(r[3] for r in righe)
print(f"\nprima frase mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
