"""Banco delle righe della stanza storpiate e della domanda insistita (15/10/2026, caso vero in
auto col 26B, conversazione di stanza accesa con `stanza_contesto` e le righe nella storia; qui
con nomi, squadra e sigle di fantasia, le storpiature di Whisper uguali di forma: «2.500» per
2025, «ARCENTO» per argento, «OR» per oro, il nome della squadra storpiato).

Con il modello vero della voce (Ollama o vLLM dal profilo), Brain vero con i tool di base più
`stanza_pausa` e `stanza_cerca`, la stanza in memoria con le righe dette prima e cinque turni di
Carlo come in auto:

1. «Cosa hai capito di quello che abbiamo detto prima?»
2. «Era il team Valtorre Lecco, che è un gruppo.»        (la correzione del nome storpiato)
3. «Quali erano questi risultati?»
4. «Ma quali sono questi risultati? Lo hai capito?»       (l'insistenza)
5. «Sì, ma quale medaglia d'oro e quale d'argento?»

Conta, per giro: **medaglie ricostruite** (nei turni 3–5 una frase che non nega con «argento»
accanto ai mondiali o al 2025, e una con «oro» accanto agli europei o al 2026: «quale medaglia
sia l'oro» ripreso dalla domanda non conta; il turno 5 che dice che non sono state dette, non
specificate o non colte è un errore); **nome corretto** (nel turno 2 «Valtorre»; a parte se nel
turno 2 c'è ancora il nome storpiato, e se torna nei turni 3–5);
**risposte ripetute** (il turno 4 quasi uguale al turno 3, `ripetizione.ripete` o somiglianza
delle parole ≥ 0,6), con le regole scattate (`domanda_insistita`, `spinta_ripetuta`).

Due modi sulla stessa conversazione: `dopo` (il codice di adesso) e `prima` (i testi sulla
stanza di prima del 15/10 e la rete `domanda_insistita` spenta), per vedere che cosa cambia.
Niente su disco; il servizio può restare acceso (stesso modello e stessa finestra).

Sul portatile (prove brevi col 4B, poi `ollama stop`):

    python prove\\manuali\\banco_stanza_storpiata.py --giri 1

Sulla DGX (il profilo della voce dal file locale, nella cartella dei dati):

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_stanza_storpiata.py --giri 5

`--modi dopo` per il solo codice di adesso; `--verboso` stampa le risposte intere.
"""

import argparse
import difflib
import os
import re
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope import config as config_mod  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import load_config  # noqa: E402
from calliope.ripetizione import parole, ripete  # noqa: E402
from calliope.stanza import contesto as ctx_mod  # noqa: E402
from calliope.stanza import misure as misure_mod  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from calliope.tools.stanza import stanza_specs  # noqa: E402


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita = None
        self.tutori = []
        self.preferred_voice = self.fascia = self.tono = self.preferred_tone = None


class Persone:
    def __init__(self):
        self.users = {"Carlo": Prof("carlo-id", "Carlo", True),
                      "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.users.get(n)

    def known_speakers(self):
        return list(self.users)


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "amministra", "voce"
    from_session = False
    sfida = incerta = minore_vicino = None
    voce_sicura, conferma_breve, sfida_superata = "Carlo", False, False
    compagnia = compagnia_sconosciute = senza_nome = False


class STTFinto:
    def transcribe(self, audio, **k):
        return ""


# (secondi prima della prima domanda, chi, testo come l'avrebbe scritto Whisper)
RIGHE = [
    (230, "Bianca", "Allora, com'è andata la stagione con la squadra?"),
    (222, "Bianca", "Quest'anno con il team Balto Torrente abbiamo fatto tutte le gare."),
    (214, "Carlo", "E i risultati?"),
    (206, "Bianca", "italiani WFO 2.500, mondiali WFO 2.500."),
    (198, "Bianca", "2025 ARCENTO, europei WFO 2026 OR."),
    (190, "Carlo", "Quindi ai mondiali?"),
    (183, "Bianca", "c'è mondiale argento i mondiali"),
    (175, "Carlo", "Complimenti, non lo sapevo."),
    (150, "Bianca", "Alla prossima uscita prendi la destra per il casello."),
    (140, "Carlo", "Va bene, mettiamo un po' di musica."),
]
DOMANDE = ["Cosa hai capito di quello che abbiamo detto prima?",
           "Era il team Valtorre Lecco, che è un gruppo.",
           "Quali erano questi risultati?",
           "Ma quali sono questi risultati? Lo hai capito?",
           "Sì, ma quale medaglia d'oro e quale d'argento?"]
ARGENTO = re.compile(r"\bargent", re.I)
ORO = re.compile(r"\boro\b", re.I)
STORPIATO = re.compile(r"balto|torrent", re.I)
GIUSTO = re.compile(r"valtorre", re.I)
NEGA = re.compile(r"non (?:ha|hanno|avete|abbiamo|è stat\w+|sono stat\w+) (?:detto|specificat\w*|"
                  r"menzionat\w*|indicat\w*|nominat\w*)|non ho (?:colto|sentito|capito|trovato)|"
                  r"non (?:è|sono) (?:chiaro|stat\w+ dett\w+)|non (?:specific|dic|indic)\w*",
                  re.I)
ARGENTO_DOVE = re.compile(r"mondial|2025", re.I)
ORO_DOVE = re.compile(r"europe|2026", re.I)
# Frasi e pezzi di frase («…argento, ma non specifica l'oro»: due pezzi); «2.500» resta intero
PEZZI = re.compile(r"[!?;]|\.(?!\d)|,\s*(?:ma|però)\s", re.I)


def medaglia(testo: str, medaglia_rx, dove_rx) -> bool:
    """Un pezzo di frase che non nega, con la medaglia e il suo posto (gara o anno)."""
    return any(medaglia_rx.search(f) and dove_rx.search(f) and not NEGA.search(f)
               for f in PEZZI.split(testo))


# I testi sulla stanza di prima del 15/10 (modo «prima»): senza la nota e con il seguito di allora
PRIMA_SEGUITO = ("Altre frasi sentite nella stanza «{dove}» dopo le righe di prima (trascrizione "
                 "automatica, può contenere errori o frasi della TV; non sono richieste per te).")
PROMPT_NUOVO = re.compile(r" \(sono trascritte con parole storpiate:[^)]*\)")


def modo_prima(attivo: bool, salvati: dict):
    """Rimette (o toglie) i testi di prima del 15/10: niente nota STORPIATE prima della busta,
    l'intestazione dei seguiti di allora, il prompt senza la parentesi sulle storpiature."""
    if attivo:
        salvati.update(STORPIATE=ctx_mod.STORPIATE,
                       INTESTAZIONE_SEGUITO=ctx_mod.INTESTAZIONE_SEGUITO,
                       prompt_for=config_mod.Config.prompt_for)
        ctx_mod.STORPIATE = ""
        ctx_mod.INTESTAZIONE_SEGUITO = PRIMA_SEGUITO
        vero = salvati["prompt_for"]

        def prompt_for(self, *a, **k):
            return PROMPT_NUOVO.sub("", vero(self, *a, **k))
        config_mod.Config.prompt_for = prompt_for
    elif salvati:
        ctx_mod.STORPIATE = salvati["STORPIATE"]
        ctx_mod.INTESTAZIONE_SEGUITO = salvati["INTESTAZIONE_SEGUITO"]
        config_mod.Config.prompt_for = salvati["prompt_for"]
        salvati.clear()


def scena(cfg):
    st = Stanza(cfg, STTFinto(), registry=Persone(), misure=misure_mod.Misure(None),
                log=lambda m: None)
    st._info[1] = {"nome": "telefono di Carlo", "stanza": "auto", "canale": "satellite"}
    ora = time.time()
    pers = Persone()
    for i, (fa, chi, testo) in enumerate(RIGHE):
        fine = ora - fa
        prof = pers.get(chi)
        st._sentita(prof.id, chi, 1, fine)
        st.registro(1).aggiungi(
            "riga", segmento=i + 1, versione=1, inizio=round(fine - 4, 3), fine=round(fine, 3),
            testo=testo, chi=f"persona:{prof.id}", nome=chi, sicurezza="voce", p_min=None,
            rivolta="ignoto", minore=False)
    return st


def brain(cfg, st):
    reg = build_registry()
    for spec in stanza_specs(cfg):
        reg.register(spec)
    st.server = SimpleNamespace(attivo=SimpleNamespace(satellite={"id": 1}),
                                per_id=lambda s: None)
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=Chi(), speaker=None, stanza=st)
    b = Brain(cfg, reg, ctx)
    b.chiamate = []
    vera = reg.call

    def call(nome, args, ctx_, level=None, **kw):
        b.chiamate.append(nome)
        return vera(nome, args, ctx_, level, **kw)
    reg.call = call
    return b


def simili(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, parole(a), parole(b), autojunk=False).ratio()


def conversazione(cfg, modo: str, verboso: bool) -> dict:
    salvati: dict = {}
    reti = list(cfg.llm_reti_spente or ())
    if modo == "prima":
        modo_prima(True, salvati)
        cfg.llm_reti_spente = reti + ["domanda_insistita"]
    try:
        st = scena(cfg)
        b = brain(cfg, st)
        risposte, regole = [], []
        for n, frase in enumerate(DOMANDE):
            b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, time.time())
            b.chiamate = []
            t0 = time.perf_counter()
            primo, parti = None, []
            for pezzo in b.stream_reply(frase, "amministra"):
                if primo is None and pezzo.strip():
                    primo = time.perf_counter() - t0
                parti.append(pezzo)
            r = re.sub(r"\s+", " ", "".join(parti)).strip()
            rg = list(getattr(b, "last_rules", None) or ())
            risposte.append(r)
            regole.append(rg)
            utili = [x for x in rg if x in ("domanda_insistita", "spinta_ripetuta",
                                            "stanza_contesto")]
            print(f"  [{modo}] {n + 1} prima frase "
                  f"{'—' if primo is None else f'{primo:.2f} s'}, tool {b.chiamate or '—'}, "
                  f"regole {utili or '—'}: «{frase}» → "
                  f"{r if verboso else r[:160]!r}", flush=True)
        st.chiudi()
    finally:
        cfg.llm_reti_spente = reti
        modo_prima(False, salvati)
    dopo = " ".join(risposte[2:])
    esito = {
        "argento": medaglia(dopo, ARGENTO, ARGENTO_DOVE),
        "oro": medaglia(dopo, ORO, ORO_DOVE),
        "nega_t5": bool(NEGA.search(risposte[4])),
        "nome_t2": bool(GIUSTO.search(risposte[1])),
        "storpiato_t2": bool(STORPIATO.search(risposte[1])),
        "storpiato_dopo": bool(STORPIATO.search(" ".join(risposte[2:]))),
        "ripetuta_t4": ripete(risposte[3], risposte[2]) or simili(risposte[3], risposte[2]) >= 0.6,
        "simili_t4": round(simili(risposte[3], risposte[2]), 2),
        "insistita": "domanda_insistita" in regole[3],
        "spinta_ripetuta": "spinta_ripetuta" in regole[3],
    }
    print(f"  [{modo}] esito: medaglie {'argento' if esito['argento'] else '—'}/"
          f"{'oro' if esito['oro'] else '—'}, turno 5 nega {esito['nega_t5']}, nome giusto al "
          f"turno 2 {esito['nome_t2']} (storpiato anche {esito['storpiato_t2']}), storpiato nei "
          f"turni 3–5 {esito['storpiato_dopo']}, "
          f"turno 4 ripetuto {esito['ripetuta_t4']} (somiglianza {esito['simili_t4']}), "
          f"domanda_insistita {esito['insistita']}, spinta_ripetuta {esito['spinta_ripetuta']}",
          flush=True)
    return esito


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--giri", type=int, default=3)
    ap.add_argument("--modi", default="prima,dopo")
    ap.add_argument("--verboso", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    # Come sulla DGX in auto: stanza in ombra, righe al modello nella storia, stanza_cerca acceso;
    # niente satelliti veri dal file locale (qui c'è solo quello finto)
    cfg.stanza, cfg.stanza_contesto, cfg.stanza_cerca = "ombra", True, True
    cfg.stanza_contesto_in_storia, cfg.stanza_attesa = True, False
    cfg.stanza_satelliti = []
    print(f"modello: {cfg.llm_model} ({cfg.llm_backend}, profilo {cfg.llm_profilo})", flush=True)
    tot: dict = {}
    for giro in range(1, a.giri + 1):
        for modo in a.modi.split(","):
            print(f"giro {giro}, modo {modo}", flush=True)
            tot.setdefault(modo, []).append(conversazione(cfg, modo, a.verboso))
    print("\nRiepilogo (conversazioni):")
    for modo, es in tot.items():
        n = len(es)

        def c(k):
            return sum(1 for e in es if e[k])
        print(f"  {modo:>5}: medaglie entrambe {sum(1 for e in es if e['argento'] and e['oro'])}"
              f"/{n} (argento {c('argento')}, oro {c('oro')}); turno 5 che nega {c('nega_t5')}/{n}; "
              f"nome giusto subito dopo la correzione {c('nome_t2')}/{n} (col nome storpiato "
              f"{c('storpiato_t2')}), storpiato nei turni 3–5 {c('storpiato_dopo')}/{n}; "
              f"turno 4 ripetuto {c('ripetuta_t4')}/{n} "
              f"(domanda_insistita {c('insistita')}, spinta_ripetuta {c('spinta_ripetuta')})")
    print("Obiettivo per «dopo»: medaglie entrambe e nome giusto in quasi tutte; turno 5 che "
          "nega, nome storpiato nei turni 3–5 e turno 4 ripetuto a 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
