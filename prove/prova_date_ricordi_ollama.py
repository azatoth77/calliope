import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Difetti della conversazione vera del 05/10 18:10 sulla DGX, con il modello vero.

1. **Date**: «quanti anni ho?» con la nascita detta, giorni a una data, giorno della settimana
   (data_calcola; prima calcola('2026-07-04-1977-07-04') e 2026−1977 = 49 invece di 48).
2. **Ricordi pertinenti**: gli interessi salvati (barbecue, smoker) non entrano nelle risposte
   su altro (fisica), e restano quando servono («cosa potrei cucinare sabato?»).
3. **Stato inventato**: «fermati con l'ordine» senza nessun lavoro non diventa «ordine
   sospeso»; «annulla il lavoro» con un lavoro vero resta un'azione.

    python prove\\prova_date_ricordi_ollama.py [giri] [--solo date|ricordi|stato]
        [--variante tool|calcola|base]   (solo per le date: per la misura del 05/10)

`--solo ricordi_toni` ripete i ricordi con i toni ironico e amichevole (il difetto era con un
tono personale). CALLIOPE_PROVA_MEMORY_USE=<testo> prova un altro testo per l'uso dei ricordi
(brain.MEMORY_USE). Database temporaneo, niente memoria.db. Una riga RIGA per caso; esce con 1
se una data o uno stato non va, o se i ricordi sono sotto l'85 %.
"""

import datetime
import re
import tempfile
import time
from pathlib import Path

from calliope.brain import Brain
from calliope.config import Config
from calliope.memory import Memory
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
import calliope.brain as _brain

# Per la misura: un altro testo per l'uso dei ricordi (CALLIOPE_PROVA_MEMORY_USE)
if os.environ.get("CALLIOPE_PROVA_MEMORY_USE"):
    _brain.MEMORY_USE = " " + os.environ["CALLIOPE_PROVA_MEMORY_USE"].strip()

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
SOLO = sys.argv[sys.argv.index("--solo") + 1] if "--solo" in sys.argv else None
VARIANTE = sys.argv[sys.argv.index("--variante") + 1] if "--variante" in sys.argv else "tool"
OGGI = datetime.date.today()


class Prof:
    def __init__(self, pid, name):
        self.id, self.name, self.preferred_tone = pid, name, None


class Speakers:
    def __init__(self, tono=None):
        self.p = {"Dario": Prof("dario-id", "Dario")}
        self.p["Dario"].preferred_tone = tono

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level
        self.identified_by = "voce"


cfg = Config()
esiti: dict[str, list[bool]] = {}


def conta(sezione, ok):
    esiti.setdefault(sezione, []).append(bool(ok))


def brain(mem, registro=None, tono=None):
    ctx = ToolContext(cfg=cfg, speakers=Speakers(tono), speaker_ctx=SpeakerCtx("Dario", "amministra"),
                      speaker=None, memory=mem)
    return Brain(cfg, registro or build_registry(), ctx)


def turno(b, frase):
    t0 = time.perf_counter()
    primo, pezzi = None, []
    for p in b.stream_reply(frase, "amministra"):
        if primo is None and p.strip():
            primo = time.perf_counter() - t0
        pezzi.append(p)
    testo = "".join(pezzi).strip()
    tool = [(t["nome"], t.get("argomenti")) for t in b.last_tools]
    return testo, tool, primo


# ─────────────────────────────── 1. DATE ───────────────────────────────
def anni(nascita):
    return OGGI.year - nascita.year - ((OGGI.month, OGGI.day) < (nascita.month, nascita.day))


def prossimo(m, g):
    d = datetime.date(OGGI.year, m, g)
    return d if d >= OGGI else datetime.date(OGGI.year + 1, m, g)


GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def numero_in(n, testo):
    return re.search(rf"(?<![\d.,]){n}(?![\d,])", testo.replace(".", "")) is not None


def registro_variante():
    reg = build_registry()
    if VARIANTE == "tool":
        return reg
    reg.unregister("data_calcola")
    if VARIANTE == "calcola":
        # Variante della misura: le date dentro calcola, con funzioni (stessa logica)
        from calliope import tempi
        spec = reg._tools["calcola"]
        orig = spec.func

        def calcola_date(ctx, espressione):
            m = re.fullmatch(r"\s*(eta|giorni|giorno_settimana)\(\s*[\"'](.+?)[\"']\s*\)\s*",
                             espressione or "")
            if not m:
                return orig(ctx, espressione)
            p = tempi.parse_date(m[2], OGGI)
            if not p:
                return {"ok": False, "errore": f"data non capita: {m[2]}"}
            d, con_anno = p
            if m[1] == "eta":
                n = tempi.anni_compiuti(d, OGGI)
                return {"ok": True, "risultato": str(n), "da_dire": f"{n} anni"}
            if m[1] == "giorni":
                d = d if con_anno else tempi.prossima(d, OGGI)
                n = (d - OGGI).days
                return {"ok": True, "risultato": str(n), "da_dire": f"{n} giorni"}
            g = GIORNI[d.weekday()]
            return {"ok": True, "risultato": g, "da_dire": g}
        spec.func = calcola_date
        spec.description += (" Per le date, con la data come detta tra virgolette: "
                             "eta(\"4 luglio 1977\") = anni compiuti oggi, giorni(\"25 dicembre\")"
                             " = giorni che mancano, giorno_settimana(\"4 luglio 1977\").")
    return reg


def prova_date():
    nascita = datetime.date(1977, 7, 4)
    natale = prossimo(12, 25)
    casi = [
        # (frasi, controllo sull'ultima risposta, descrizione)
        (["Sono nato il 4 luglio del 1977. Quanti anni ho?"],
         lambda t: numero_in(anni(nascita), t) and not numero_in(anni(nascita) + 1, t)
         or (numero_in(anni(nascita), t) and "compi" in t.lower()), "età con la nascita detta"),
        (["E dimmi anche quanti anni ho?",
          "Sì, non so come la mia età possa incidere, ma comunque sono nato il 4 luglio del 1977."],
         lambda t: numero_in(anni(nascita), t), "età al turno dopo (caso vero)"),
        (["Quanti giorni mancano a Natale?"],
         lambda t: numero_in((natale - OGGI).days, t), "giorni a Natale"),
        (["Che giorno della settimana era il 4 luglio 1977?"],
         lambda t: GIORNI[nascita.weekday()] in t.lower(), "giorno della settimana"),
        (["Quanti anni ha oggi una persona nata il 12 marzo 1990?"],
         lambda t: numero_in(anni(datetime.date(1990, 3, 12)), t), "età di un'altra data"),
        (["Mia figlia è nata il 20 dicembre 2015: quanti anni ha?"],
         lambda t: numero_in(anni(datetime.date(2015, 12, 20)), t), "età, compleanno non ancora"),
        # Contrari: conti senza date restano a calcola
        (["Quanto fa 17 per 6?"], lambda t: numero_in(102, t), "contrario: calcola"),
        (["Quanto fa 2026 meno 1977?"], lambda t: numero_in(49, t), "contrario: sottrazione di numeri"),
    ]
    for frasi, ok, nome in casi:
        mem = Memory(str(Path(tempfile.mkdtemp()) / "m.db"))
        b = brain(mem, registro_variante())
        for f in frasi:
            testo, tool, primo = turno(b, f)
        esito = ok(testo)
        conta(f"date/{VARIANTE}", esito)
        print(f"RIGA\tdate\t{'ok' if esito else 'NO'}\t{nome}\t{tool}\t{primo or 0:.2f}s\t{testo[:160]!r}")


# ─────────────────────────────── 2. RICORDI PERTINENTI ───────────────────────────────
INTERESSI = re.compile(r"\b(barbecue|smoker|affumic\w*|brisket|brace|grigli\w*|costin\w*|"
                       r"cottur\w*|cucin\w*|carne|fumo)\b", re.I)
FATTI = ["Dario è appassionato di astronomia, astrofisica e fisica.",
         "Dario ama il barbecue e possiede uno smoker per la cucina."]


STORIA_VERA = [
    {"role": "user", "content": "Guarda, aggiungi anche che mi piace tantissimo il barbecue "
     "perché non è vero che per la cucina non puoi parlarmi, però barbecue soprattutto, ho uno "
     "smoker che mi permette di fare un sacco di cose."},
    {"role": "assistant", "content": "Accidenti, allora il mio profilo su di te si sta "
     "arricchendo di dettagli molto più appetitosi! Ho aggiunto alla tua scheda l'amore per il "
     "barbecue e il possesso di uno smoker, così la prossima volta che parliamo di fisica potrei "
     "magari provare a spiegarti la termodinamica applicata alla cottura lenta di una costina."},
    {"role": "user", "content": "Interessantissimo argomento."},
    {"role": "assistant", "content": "Vero, passare dai buchi neri alla cottura lenta di una "
     "brisket è un salto che richiede una certa elasticità mentale, ma è proprio questo che rende "
     "la conversazione stimolante. Da quale dei due mondi vogliamo iniziare il nostro prossimo "
     "viaggio?"},
    {"role": "user", "content": "Ah sì, parliamo di un po' di meccanica quantistica."},
    {"role": "assistant", "content": "Un salto decisivo: dalla cottura lenta del barbecue alla "
     "velocità della luce e all'indeterminazione. Da dove preferisci iniziare: dal principio di "
     "indeterminazione di Heisenberg o dal paradosso del gatto di Schrödinger?"},
    {"role": "user", "content": "Partiamo dall'indeterminazione di Heisenberg."},
    {"role": "assistant", "content": "Il principio di indeterminazione ci dice che non puoi "
     "conoscere contemporaneamente, con precisione assoluta, la posizione e la quantità di moto "
     "di una particella. È un po' come cercare di capire esattamente dove si trova il punto "
     "perfetto della temperatura nel tuo smoker mentre il fumo si muove."},
]
STORIA_DOMANDE = ["Velocità e quantità di moto sono due concetti un po' diversi, vero?",
                  "Invece Schrödinger che dice?",
                  "Precisamente meno rassicurante, anche se l'ansia che ne consegue penso sia "
                  "la stessa."]


def prova_ricordi(tono=None):
    fuori = ["Parliamo un po' di meccanica quantistica: cos'è il principio di indeterminazione?",
             "La velocità e la quantità di moto sono due concetti diversi, vero?",
             "Cosa dice il paradosso del gatto di Schrödinger?",
             "Spiegami in breve cos'è un buco nero.",
             "Chi era Giulio Cesare?",
             "Mi consigli un modo per dormire meglio?"]
    dentro = [("Cosa potrei cucinare sabato per gli amici?", INTERESSI),
              ("Cosa sai di me?", re.compile(r"barbecue|smoker", re.I)),
              ("Che regalo potrei farmi per il mio compleanno?",
               re.compile(r"barbecue|smoker|affumic|telescop|astronom|griglia", re.I))]
    # Solo informativo, non contato: chiede i gusti di Calliope, e con il testo di adesso e4b
    # non li usa più (0/6, prima 9/9)
    info = [("Che argomento ti piacerebbe affrontare con me stasera?",
             re.compile(r"astronom|fisic|barbecue|smoker|stelle|cosmo|universo", re.I))]
    mem = Memory(str(Path(tempfile.mkdtemp()) / "m.db"))
    for f in FATTI:
        mem.remember("dario-id", f)
    for frase in fuori:
        b = brain(mem, tono=tono)
        testo, tool, primo = turno(b, frase)
        esito = not INTERESSI.search(testo)
        conta(f"ricordi fuori tema ({tono or 'normale'})", esito)
        print(f"RIGA\tfuori\t{'ok' if esito else 'NO'}\t{frase}\t{[t[0] for t in tool]}\t"
              f"{primo or 0:.2f}s\t{testo!r}")
    # Come nella conversazione vera: gli interessi detti nella conversazione stessa, poi la fisica
    b = brain(mem, tono=tono)
    for f in ["Guarda, aggiungi anche che mi piace tantissimo il barbecue, ho uno smoker che mi "
              "permette di fare un sacco di cose.",
              "Ah sì, parliamo di un po' di meccanica quantistica.",
              "Partiamo dall'indeterminazione di Heisenberg.",
              "Velocità e quantità di moto sono due concetti un po' diversi, vero?"]:
        testo, tool, primo = turno(b, f)
    esito = not INTERESSI.search(testo)
    conta(f"ricordi fuori tema ({tono or 'normale'})", esito)
    print(f"RIGA\tfuori\t{'ok' if esito else 'NO'}\tconversazione vera, 4° turno\t"
          f"{[t[0] for t in tool]}\t{primo or 0:.2f}s\t{testo!r}")
    # La storia vera della DGX (05/10 18:13–18:16, risposte del 26B): il barbecue era già
    # entrato in tre risposte sulla fisica, e il modello continuava (la «battuta» si ripete)
    for domanda in STORIA_DOMANDE:
        b = brain(mem, tono=tono)
        b.history = [dict(m) for m in STORIA_VERA]
        testo, tool, primo = turno(b, domanda)
        esito = not INTERESSI.search(testo)
        conta(f"ricordi fuori tema, storia vera ({tono or 'normale'})", esito)
        print(f"RIGA\tstoria\t{'ok' if esito else 'NO'}\t{domanda}\t{[t[0] for t in tool]}\t"
              f"{primo or 0:.2f}s\t{testo!r}")
    for frase, attesi in dentro + info:
        b = brain(mem, tono=tono)
        testo, tool, primo = turno(b, frase)
        esito = bool(attesi.search(testo))
        if (frase, attesi) in dentro:
            conta(f"ricordi pertinenti ({tono or 'normale'})", esito)
        print(f"RIGA\t{'dentro' if (frase, attesi) in dentro else 'info'}\t"
              f"{'ok' if esito else 'NO'}\t{frase}\t{[t[0] for t in tool]}\t"
              f"{primo or 0:.2f}s\t{testo!r}")


# ─────────────────────────────── 3. STATO INVENTATO ───────────────────────────────
INVENTATO = re.compile(r"\b(ho|l'ho)\s+(fermat|sospes|interrott|annullat|bloccat)|"
                       r"\b(ordine|lavoro|tutto)\s+(sospes|fermat|annullat|interrott)", re.I)


class PrimaFinta:
    """Il backend vero, ma la prima passata dice la frase del 26B sulla DGX: così si prova la
    rete (spinta) con il modello vero anche quando e4b da solo non la dice."""

    def __init__(self, backend, testo):
        self.backend, self.testo, self.usata = backend, testo, False

    def __getattr__(self, nome):
        return getattr(self.backend, nome)

    def stream(self, messages, tools):
        if not self.usata:
            self.usata = True
            yield "text", self.testo
            return
        yield from self.backend.stream(messages, tools)


def prova_stato():
    # La frase vera del 26B come prima passata: la rete la trattiene e il modello rifà
    for frasi, finta, nome in [
            (["Creiamo un'estensione per tenere traccia delle mie cotture al barbecue.",
              "No, per il momento fermati con l'ordine."],
             "Ricevuto, ordine sospeso. Resto in attesa di un tuo segnale.", "ordine sospeso (26B)"),
            (["Se volessimo costruire un piccolo videogioco da mostrare su una scheda?",
              "Allora fermati."], "Ho fermato tutto. Dimmi pure come vuoi procedere.",
             "ho fermato tutto (26B)")]:
        mem = Memory(str(Path(tempfile.mkdtemp()) / "m.db"))
        b = brain(mem)
        for f in frasi[:-1]:
            turno(b, f)
        b.backend = PrimaFinta(b.backend, finta)
        testo, tool, primo = turno(b, frasi[-1])
        nomi = [t[0] for t in tool]
        esito = (not INVENTATO.search(testo) and "Non ci sono riuscita" not in testo
                 and "spinta_dichiarata" in b.last_rules)
        conta("stato inventato, frase del 26B", esito)
        print(f"RIGA\tstato\t{'ok' if esito else 'NO'}\t{nome}\t{nomi}\t{primo or 0:.2f}s\t"
              f"{testo[:160]!r}")
    casi = [
        (["Se volessimo costruire un piccolo videogioco da mostrare su una scheda?",
          "Allora fermati."], "fermati dopo una proposta"),
        (["Creiamo un'estensione per tenere traccia delle mie cotture al barbecue.",
          "No, per il momento fermati con l'ordine."], "fermati con l'ordine"),
        (["Sospendi l'ordine."], "sospendi l'ordine senza niente in corso"),
        (["Annulla il lavoro che stavi facendo."], "annulla il lavoro senza lavori"),
    ]
    for frasi, nome in casi:
        mem = Memory(str(Path(tempfile.mkdtemp()) / "m.db"))
        b = brain(mem)
        for f in frasi:
            testo, tool, primo = turno(b, f)
        nomi = [t[0] for t in tool]
        esito = not INVENTATO.search(testo) or any(n.startswith("lavori_") for n in nomi)
        conta("stato inventato", esito)
        print(f"RIGA\tstato\t{'ok' if esito else 'NO'}\t{nome}\t{nomi}\t{primo or 0:.2f}s\t"
              f"{testo[:160]!r}")


for g in range(GIRI):
    print(f"\n=== giro {g + 1} ===")
    if SOLO in (None, "date"):
        prova_date()
    if SOLO in (None, "ricordi"):
        prova_ricordi()
    if SOLO in ("ricordi_toni",):
        for tono in ("ironico", "amichevole"):
            prova_ricordi(tono)
    if SOLO in (None, "stato"):
        prova_stato()

print()
tot_ok = tot = 0
for k, v in esiti.items():
    print(f"{k}: {sum(v)}/{len(v)}")
    tot_ok, tot = tot_ok + sum(v), tot + len(v)
print(f"TOTALE {tot_ok}/{tot}")
# Date e stati inventati: tutti; i ricordi dipendono dallo stile del modello (le frasi con il
# barbecue «fuori tema» oscillano tra i giri): almeno l'85 %
rigide = [v for k, v in esiti.items() if not k.startswith("ricordi")]
morbide = [x for k, v in esiti.items() if k.startswith("ricordi") for x in v]
ok = all(all(v) for v in rigide) and (not morbide or sum(morbide) >= 0.85 * len(morbide))
sys.exit(0 if ok else 1)
