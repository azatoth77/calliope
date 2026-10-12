"""
Il giro vero della DGX del 10/10/2026 sera (17:32–17:33, versione 040317d, cioè dopo la
correzione del pomeriggio sui giochi), riscritto con nomi di fantasia: un gioco di Halloween per
più giocatori chiesto con `sviluppo_apri(tipo="estensione")` senza il flag del gioco.

Il turno vero: il 26B chiama sviluppo_apri con tipo «estensione» e il compito «Crea un gioco di
Halloween per schermi dove i giocatori devono scegliere tra diverse porte…» (nessun gioco=true).
La regola `sviluppo_gioco_schermi` valeva solo per il tipo programma: il compito è andato
all'analisi delle estensioni, che prima ha chiesto (vaga) e poi, dopo «la partita dura 15 turni,
vince chi ha più punti», ha risposto «impossibile: un gioco interattivo con grafica e logica
complessa richiede JavaScript nel browser, ma la richiesta non specifica di usare la sezione
'scheda' del manifesto» → sviluppo chiuso. Il titolo dello sviluppo era l'inizio del compito
troncato a 80 caratteri («…devono scegliere tra div»).

1. **Il flag del gioco anche con tipo estensione** (tools/sviluppo.py): la stessa regola, e
   l'analisi delle estensioni non parte. Dal 12/10 (M4) un gioco ha la sua analisi, con la lista
   di controllo del gioco e «cosa si può fare» del gioco: l'analizzatore qui è quello vero con un
   client finto che darebbe le stesse risposte dell'agente, chiamato una volta con il prompt del
   gioco, e mai «impossibile». Contrari: un gioco per Windows con una finestra, un'estensione che
   conta i punti del gioco di carte (analisi, niente flag), gioco=true già detto (niente
   regola).
2. **L'analisi delle estensioni sa dei giochi** (agenti/richiesta.py): «Cosa si può fare qui»
   dice che un gioco si fa con una scheda che sceglie l'agente, e la nota dell'impossibile che
   un dettaglio tecnico non detto (scheda, JavaScript, manifesto) non rende impossibile niente.
   L'esito «impossibile» della risposta vera resta un esito (lo decide il modello): la prova
   guarda il testo che il modello riceve.
3. **Il titolo** (agenti/servizio.titolo_da, sviluppo.titolo_richiesta): «gioco di Halloween»,
   senza peggiorare i titoli buoni (Celsius in Fahrenheit, numero di vocali, foto per data).

A secco, ~2 s.

    python prove\\prova_giro_sera_gioco.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


# Il compito come l'ha scritto il 26B (fantasia: la stessa forma, parole nostre dopo l'inizio)
COMPITO = ("Crea un gioco di Halloween per schermi dove i giocatori devono scegliere tra diverse "
           "porte. Dietro ogni porta ci può essere un mostro, un dolcetto o una cosa buffa; i "
           "mostri tolgono punti, i dolcetti li danno, e a ogni turno le porte possono aumentare "
           "o diminuire.")
DETTO = ("Calliope, voglio un gioco di Halloween per tutta la famiglia: ognuno sceglie una porta, "
         "dietro ci sono mostri, dolcetti o cose buffe, si fanno punti e le porte a volte "
         "aumentano e a volte diminuiscono.")
RISPOSTA = "La partita dura 15 turni, vince chi ha più punti."

# Le risposte vere dell'agente (qwen3.6) all'analisi delle 17:32 e 17:33
VAGA = {"impossibile": "", "punti": {"input": "detto", "output": "detto", "fonte":
                                     "scelta_ragionevole", "non_trovato": "scelta_ragionevole",
                                     "permessi": "manca"},
        "dal_contesto": [], "domande": [{"domanda": "Quanto dura una partita e come si vince?",
                                         "senza_risposta": "sbaglia"}],
        "specifica": "", "nome": "porte di halloween", "fonte_url": "", "gia_fatto": "",
        "come_chiederlo": ""}
IMPOSSIBILE = dict(VAGA, domande=[], impossibile=(
    "un gioco interattivo con grafica e logica complessa richiede JavaScript nel browser, ma la "
    "richiesta non specifica di usare la sezione 'scheda' del manifesto per renderlo "
    "compatibile con le funzionalità di Calliope."))


class ClienteCopione:
    """Il client dell'agente per l'analisi: dà le risposte vere, in ordine, e le conta."""

    def __init__(self, *risposte):
        self.risposte = [json.dumps(r, ensure_ascii=False) for r in risposte]
        self.chiamate = []

    def chat(self, body):
        self.chiamate.append(body)
        testo = self.risposte.pop(0) if self.risposte else json.dumps(VAGA)
        return {"content": testo}


def analizzatore(cfg, *risposte):
    from calliope.agenti import richiesta as ar
    cliente = ClienteCopione(*risposte)
    lav = SimpleNamespace(cliente=cliente, imp=SimpleNamespace(modello="agente-finto"),
                          isolamenti={}, agente=None, arbitro=None)
    return ar.Analizzatore(cfg, lav, log=lambda *_: None), cliente


def frase_di(out):
    return str(out.get("risposta_finale") or out.get("conferma") or "")


# ═══════════════════════════ 1. il flag del gioco con tipo estensione ═══════════════════════════

def prova_flag(tmp: Path):
    print("— 1. un gioco con tipo estensione riceve il flag del gioco")
    import prova_sviluppo_v2 as V
    import prova_estensioni as P

    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)

    # Prima la riprova del difetto: la stessa analisi, senza la regola, dichiarava impossibile
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "prima", iso)
    svc.analizzatore, cliente = analizzatore(cfg, VAGA, IMPOSSIBILE)
    from calliope.tools import estensioni as te
    ctx.regole = []
    ctx.user_text = DETTO
    ctx.turno = 1
    out1 = te._estensione_crea(ctx, compito=COMPITO)          # come prima: niente flag
    ctx.turno = 2
    ctx.user_text = RISPOSTA
    out2 = te._estensione_crea(ctx, compito=COMPITO)
    verifica("riprova del turno vero senza flag: vaga, poi impossibile (l'esito del modello)",
             "analisi_vaga" in ctx.regole and "analisi_impossibile" in ctx.regole
             and "non posso farlo" in frase_di(out2) and len(cliente.chiamate) == 2,
             f"{ctx.regole} {frase_di(out1)} | {frase_di(out2)}")

    # Il turno vero, con la correzione
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "vero", iso)
    svc.analizzatore, cliente = analizzatore(cfg, VAGA, IMPOSSIBILE)
    ctx.regole = []
    ctx.user_text = DETTO
    out = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": COMPITO},
                   turno=1)
    sv = svc.sviluppi.corrente("u1")
    frase = frase_di(out)
    verifica("17:32, tipo estensione senza flag → sviluppo_gioco_schermi, sviluppo di un gioco",
             "sviluppo_gioco_schermi" in ctx.regole and sv is not None and sv.gioco
             and sv.tipo == "estensione" and sv.fase == "analisi", f"{ctx.regole} {out}")
    sistema = cliente.chiamate[0]["messages"][0]["content"] if cliente.chiamate else ""
    verifica("l'analisi delle estensioni non parte: quella del gioco sì (12/10), niente "
             "«impossibile»", len(cliente.chiamate) == 1 and "giocatori = quanti giocano"
             in sistema and "Un'estensione è un piccolo programma Python" not in sistema
             and "analisi_impossibile" not in ctx.regole, f"{ctx.regole}")
    verifica("la proposta dice «Lo faccio come gioco sugli schermi», non è un rifiuto",
             "Lo faccio come gioco sugli schermi" in frase and "non posso" not in frase.lower(),
             frase)
    lav = svc.offerte["u1"]["lavoro"]
    verifica("il lavoro è un gioco (scheda, gioco puro)", lav.gioco and "GIOCO" in lav.vincoli,
             lav.vincoli)
    verifica("il titolo dello sviluppo è breve (il nome dell'analisi), non il compito troncato",
             sv.titolo == "porte di halloween" and lav.titolo == "porte di halloween",
             f"{sv.titolo!r} {lav.titolo!r}")
    verifica("lo sviluppo resta aperto (non chiuso come impossibile)",
             sv.stato == "aperta" and "chiuso" not in json.dumps(sv.storia), sv.stato)

    # Contrari
    casi = [
        ("un gioco per Windows con una finestra sul desktop", "estensione",
         "Fammi un gioco per Windows con una finestra.", "contrario: un gioco per Windows con "
         "una finestra, tipo estensione → niente flag, l'analisi c'è"),
        ("un'estensione che conta i punti del gioco di carte", "estensione",
         "Fammi un'estensione che conta i punti a scopa.", "contrario: un'estensione che conta "
         "i punti del gioco di carte → niente flag, l'analisi c'è"),
    ]
    for compito, tipo, detto, nome in casi:
        cfg, reg, ctx, est, svc = V.ambiente(tmp / f"c{len(nome)}", iso)
        svc.analizzatore, cliente = analizzatore(cfg, dict(VAGA, punti=dict(
            VAGA["punti"], permessi="scelta_ragionevole"), domande=[]))
        ctx.regole = []
        ctx.user_text = detto
        P.chiama(reg, ctx, "sviluppo_apri", {"tipo": tipo, "compito": compito}, turno=1)
        sv = svc.sviluppi.corrente("u1")
        verifica(nome, "sviluppo_gioco_schermi" not in ctx.regole and len(cliente.chiamate) == 1
                 and (sv is None or not sv.gioco), f"{ctx.regole} {len(cliente.chiamate)}")
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "flag", iso)
    svc.analizzatore, cliente = analizzatore(cfg)
    ctx.regole = []
    ctx.user_text = DETTO
    P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": COMPITO,
                                         "gioco": True}, turno=1)
    sv = svc.sviluppi.corrente("u1")
    verifica("contrario: gioco=true già detto dal modello → un gioco, senza la regola (e la "
             "sua analisi)", "sviluppo_gioco_schermi" not in ctx.regole and sv is not None
             and sv.gioco and len(cliente.chiamate) == 1, f"{ctx.regole}")
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "modifica", iso)
    svc.analizzatore, cliente = analizzatore(cfg)
    ctx.regole = []
    ctx.user_text = "Cambia l'estensione del meteo: un gioco di quiz sul tempo."
    P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": "un gioco di quiz",
                                         "modifica": "meteo_citta"}, turno=1)
    verifica("contrario: la modifica di un'estensione che c'è non diventa un gioco nuovo",
             "sviluppo_gioco_schermi" not in ctx.regole, f"{ctx.regole}")


# ═══════════════════════════ 2. il testo dell'analisi ═══════════════════════════

def prova_analisi():
    print("— 2. l'analisi delle estensioni sa che un gioco si fa")
    from calliope.agenti import richiesta as ar
    from calliope.config import Config
    cfg = Config()
    cap = ar.capacita(cfg, "estensione")
    verifica("«Cosa si può fare qui» dice che un gioco si fa, con la scheda scelta dall'agente",
             "un gioco" in cap and "la scheda e il JavaScript li sceglie l'agente" in cap
             and "non deve chiederli" in cap, cap)
    verifica("…e non dice più «con la sezione «scheda» del manifesto» (la frase che "
             "l'analista ha preso per un requisito)", "sezione «scheda» del manifesto" not in cap,
             cap)
    verifica("gli impossibili veri restano (email, rete di casa, file del PC)",
             "mandare email" in cap and "rete di casa" in cap and "file del PC" in cap, cap)
    msgs = ar.messaggi(cfg, "estensione", COMPITO, detto=DETTO)
    sistema = msgs[0]["content"]
    verifica("la nota dell'impossibile per le estensioni: un dettaglio tecnico non detto non "
             "rende impossibile niente, un gioco NON è impossibile",
             "dettaglio tecnico" in sistema and "Un gioco sugli schermi NON è impossibile"
             in sistema, sistema[:600])
    cod = ar.messaggi(cfg, "codice", "un programma con una finestra per il desktop")[0]["content"]
    verifica("contrario: il lavoro di codice tiene la sua nota (ESTENSIONE) e il programma con "
             "le finestre resta impossibile", "ESTENSIONE" in cod and "finestre per il desktop"
             in cod and "dettaglio tecnico" not in cod)
    e = ar.interpreta(json.dumps(IMPOSSIBILE), "estensione")
    verifica("la risposta vera resta un esito del modello (impossibile): il codice non la "
             "riscrive", e.esito == "impossibile", e.esito)


# ═══════════════════════════ 3. il titolo ═══════════════════════════

def prova_titoli():
    print("— 3. il titolo di un compito lungo")
    from calliope.agenti.servizio import titolo_da
    from calliope.sviluppo import titolo_richiesta
    casi = [
        (COMPITO, "gioco di Halloween"),
        ("Crea un gioco di Halloween per schermi dove i giocatori devono scegliere tra div",
         "gioco di Halloween"),
        ("Crea un gioco di memoria con le carte per due giocatori dove vince chi trova più "
         "coppie", "gioco di memoria con le carte"),
        ("Crea un'estensione per Calliope che dice il meteo di una città",
         "estensione che dice il meteo"),
        # i titoli buoni di prima, uguali
        ("Scrivi un programma in Python che converte i gradi Celsius in Fahrenheit",
         "programma in Python che converte i gradi Celsius in Fahrenheit"),
        ("Scrivi un programma in Python che conti il numero di vocali presenti in una stringa",
         "programma in Python che conti il numero di vocali"),
        ("Scrivi uno script che rinomina le foto per data", "script che rinomina le foto per "
         "data"),
        ("Crea un'estensione che dice dove si trova la farmacia di turno",
         "estensione che dice dove si trova"),
        ("un gioco", "gioco"),
        # «sullo schermo» in fondo, senza «che» né relativa, resta (prova_lavori_riavvio)
        ("Fammi un gioco memory da giocare sullo schermo",
         "gioco memory da giocare sullo schermo"),
        ("Crea un gioco di Halloween per più giocatori con delle porte da scegliere",
         "gioco di Halloween per più giocatori con delle porte da scegliere"),
    ]
    for compito, atteso in casi:
        verifica(f"titolo_da «{compito[:50]}…» → «{atteso}»", titolo_da(compito) == atteso,
                 titolo_da(compito))
    verifica("contrario: «gioco per gli schermi di Calliope dove…» non resta «gioco» da solo",
             titolo_da("Crea un gioco per gli schermi di Calliope dove si indovinano le parole")
             != "gioco")
    verifica("titolo_richiesta: dal compito lungo, non l'inizio troncato; «programma» per un "
             "programma; «sviluppo» senza richiesta",
             titolo_richiesta("estensione", COMPITO) == "gioco di Halloween"
             and titolo_richiesta("programma", "Crea un'estensione che somma due numeri")
             == "programma che somma due numeri"
             and titolo_richiesta("estensione", "") == "sviluppo")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-giro-sera-gioco-"))
    os.environ.setdefault("DOCKER_FINTO_DIR", str(tmp / "docker"))
    import prova_estensioni as P
    os.environ.setdefault("DOCKER_FINTO_IMMAGINI", P.IMMAGINE)
    os.environ.setdefault("DOCKER_FINTO_MODO", "ok")
    prova_flag(tmp)
    prova_analisi()
    prova_titoli()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
