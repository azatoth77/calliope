"""
Il giro vero della DGX del 12/10 (il gioco delle porte magiche), riscritto con nomi di fantasia:
le correzioni dai log del 12/10 sera (docs/aree/agenti-estensioni.md, giochi.md,
voce-e-regole.md).

1. **Una modifica dello stesso gioco non è «un'altra estensione»** (07:38, 08:47): «…tra un
   giocatore e l'altro» faceva scattare `_COSA_NUOVA` («gioc\\w*»). Contrari: un altro gioco,
   un programma, un'estensione nuova detti come modifica.

A secco, ~3 s.

    python prove\\prova_giro_porte.py
"""

import json
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


def detta(out) -> str:
    return str((out or {}).get("risposta_finale") or (out or {}).get("conferma") or "")


TITOLO = "Le porte magiche di Borgofiore"
COMPITO = ("Crea il gioco delle porte magiche di Borgofiore: da 2 a 4 giocatori a turno scelgono "
           "una porta, dietro c'è un mostro che vale dei punti; vince chi arriva prima al "
           "punteggio deciso dal gioco.")
REQ = [
    {"testo": "da 2 a 4 giocatori a turno", "nucleo": True, "si_puo": True},
    {"testo": "si sceglie una porta", "nucleo": True, "si_puo": True},
    {"testo": "dietro la porta un mostro che vale punti", "nucleo": True, "si_puo": True},
    {"testo": "vince chi arriva prima al punteggio", "nucleo": True, "si_puo": True},
]


# La scheda di un gioco puro come la normalizza estensioni/scheda.py (per la revisione); dal 14/10
# sempre con la macchina a stati (i comandi a voce piatti vengono da lì)
def _macchina(*comandi):
    return {"inizio": "turno", "esito_s": 4.0, "fasi": {"turno": {
        "pagina": "scelte", "turni": True, "verso": ["fine"],
        "comandi": {c: {"forme": [c]} for c in comandi}}}}


SCHEDA = {"titolo": TITOLO, "giocatori": {"min": 2, "max": 4}, "condivisa": False, "chat": False,
          "salva": True, "voce": False, "azioni": [], "macchina": _macchina("apri")}


def ambiente_gioco(tmp: Path, agente):
    import prova_specifica_viva as S
    cfg, reg, ctx, est, svc = S.ambiente(tmp, agente)
    out = S.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "gioco": True,
                                               "compito": COMPITO, "nome": TITOLO}, 1,
                   "Voglio un gioco.")
    sv = svc.sviluppi.corrente("u1")
    return cfg, reg, ctx, est, svc, sv, out


def al_collaudo(tmp: Path, agente):
    """Il gioco consegnato e al collaudo (versione candidata con la scheda)."""
    import prova_specifica_viva as S
    from calliope.tools import sviluppo as ts
    ts._COSA_CHIESTA.clear()          # le domande di un'altra prova (stessa persona «u1»)
    cfg, reg, ctx, est, svc, sv, out = ambiente_gioco(tmp, agente)
    lav = S.ultimo(svc)
    S.chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id, "tappe": False}, 2, "Sì.")
    S.consegna(svc, est, sv)
    return cfg, reg, ctx, est, svc, sv


# ═══════════════════════════ 1. la modifica dello stesso gioco ═══════════════════════════

def prova_stesso_gioco(tmp: Path):
    print("— 1. una modifica dello stesso gioco non è «un'altra estensione»")
    from calliope.sviluppo import altro_compito_in_cambia, cosa_nuova
    sv = SimpleNamespace(titolo="Halloween - Le Porte Magiche", richiesta=COMPITO,
                         specifica=COMPITO, gioco=True)
    # Le modifiche vere del 12/10 (07:38, 08:47, 11:51), con le parole dette
    vere = [
        "le porte devono essere un numero fisso di 3, 4 o 5 (scelto all'inizio) e rimangono le "
        "stesse per tutti i turni; il gioco continua tra un giocatore e l'altro finché uno non "
        "raggiunge il punteggio massimo",
        "le porte non devono sparire dopo la scelta di un giocatore; devono rimanere abilitate "
        "per il giocatore successivo, permettendo a un giocatore di scegliere la stessa porta",
        "mostrare un'animazione del mostro dietro la porta dopo il clic e i punti vinti da un "
        "giocatore con quel mostro",
        "deve diventare un gioco a squadre",
        "fallo diventare un giochino più veloce, con una giocata a testa",
    ]
    for c in vere:
        verifica(f"contrario: «{c[:60]}…» è una modifica dello stesso gioco",
                 not altro_compito_in_cambia(c, sv), c)
    verifica("«un giocatore», «un programmatore», «una giocata» non sono cose nuove",
             not cosa_nuova("tocca a un giocatore") and not cosa_nuova("come un programmatore")
             and not cosa_nuova("una giocata a testa") and not cosa_nuova("uno scripting"))
    nuovi = [
        "scrivi un altro gioco che fa il memory con le carte degli animali",
        "un nuovo gioco di carte con i semi napoletani",
        "un programma in Python che converte i chilometri in miglia",
        "crea un'estensione che dica le maree di Portoverde",
    ]
    for c in nuovi:
        verifica(f"«{c[:50]}…» resta un altro compito", altro_compito_in_cambia(c, sv), c)
    sv_prog = SimpleNamespace(titolo="programma che conta le vocali", richiesta="conta le vocali",
                              specifica="conta le vocali", gioco=False)
    verifica("in uno sviluppo che non è un gioco «un gioco di carte» è una cosa nuova",
             altro_compito_in_cambia("un gioco di carte con i semi napoletani", sv_prog))

    # Col tool: lo sviluppo del gioco al collaudo, la modifica vera delle 08:47
    import prova_specifica_viva as S
    agente = S.AgenteVivo(requisiti=REQ, stima="piccolo", modifiche=[
        {"tipo": "cambia", "operazioni": [
            {"op": "aggiungi", "testo": "la porta resta per il giocatore dopo", "nucleo": True,
             "si_puo": True}]}])
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "stesso", agente)
    out = S.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": vere[1]}, 4,
                   "La porta non deve sparire, deve restare per il giocatore 2.")
    verifica("08:47: la modifica vera diventa un cambio dei requisiti, non «un'altra estensione»",
             "sviluppo_analisi_altro" not in ctx.regole and "un'altra estensione" not in detta(out)
             and "sviluppo_modifica_requisiti" in ctx.regole and sv.fase == "analisi",
             f"{ctx.regole} {detta(out)}")
    out = S.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": nuovi[0]}, 5,
                   "Scrivi un altro gioco, il memory con le carte degli animali.")
    verifica("contrario: un altro gioco detto come modifica → la domanda «sospendo e apro?», "
             "detto «un altro gioco»", "sviluppo_analisi_altro" in ctx.regole
             and "è un altro gioco" in detta(out), detta(out))


# ═══════════════════════════ 2. «vorrei modificarlo» senza dire cosa ═══════════════════════════

def prova_modifica_vaga(tmp: Path):
    print("— 2. una modifica che non dice cosa cambiare → «cosa vuoi cambiare?»")
    from calliope.sviluppo import senza_contenuto
    sv = SimpleNamespace(titolo="Halloween - Le Porte Magiche")
    vuote = ["modifica le regole o il funzionamento come desideri",
             "modifica Halloween le porte magiche", "cambialo come preferisci",
             "vorrei modificare il gioco", "gestiscilo meglio"]
    for c in vuote:
        verifica(f"«{c}» non dice niente di concreto", senza_contenuto(c, sv), c)
    piene = ["metti sette porte", "tre porte", "le porte non devono sparire",
             "i mostri danno punti", "più porte", "aggiungi la musica",
             "cambia le porte, falle strane", "il gioco decide il numero di porte",
             "mostra un'animazione del mostro"]
    for c in piene:
        verifica(f"contrario: «{c}» è una modifica concreta", not senza_contenuto(c, sv), c)
    verifica("contrario: vuoto (lo gestisce «D'accordo: cosa vuoi cambiare?»)",
             not senza_contenuto("", sv))

    import prova_specifica_viva as S
    agente = S.AgenteVivo(requisiti=REQ, stima="piccolo", modifiche=[
        {"tipo": "cambia", "operazioni": [
            {"op": "aggiungi", "testo": "la porta resta per il giocatore dopo", "nucleo": True,
             "si_puo": True}]},
        {"tipo": "difetto", "operazioni": []}])
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "vaga", agente)
    n_lavori = len(svc.lavori)
    out = S.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": vuote[0]}, 4,
                   "Vorrei modificare le porte magiche.")
    verifica("08:38: il riempitivo → «Cosa vuoi cambiare, di preciso?», niente al modello "
             "dell'agente, niente cambia", detta(out) == "Cosa vuoi cambiare, di preciso?"
             and agente.quante("operazioni") == 0 and sv.fase == "collaudo"
             and len(svc.lavori) == n_lavori and "sviluppo_modifica_vaga" in ctx.regole
             and "sviluppo_modifica_riempitivo" in ctx.regole
             and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_passo",
             f"{ctx.regole} {detta(out)}")
    out = S.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "le porte"}, 5,
                   "Le porte.")
    verifica("la risposta alla domanda non si richiede: va al modello dell'agente",
             agente.quante("operazioni") == 1 and "sviluppo_modifica_riempitivo" not in ctx.regole,
             f"{ctx.regole} {detta(out)}")
    # Un difetto: la frase corretta (prima «Questo la richiesta lo dice già…»)
    agente2 = S.AgenteVivo(requisiti=REQ, stima="piccolo",
                           modifiche=[{"tipo": "difetto", "operazioni": []}])
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "difetto", agente2)
    out = S.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi",
                   "cambia": "dietro la porta deve esserci un mostro che vale punti"}, 4,
                   "Dietro la porta ci deve essere un mostro che vale punti.")
    verifica("c'era già ed è un difetto: «La richiesta lo dice già: se il gioco non lo fa, va "
             "corretto il codice. Lo faccio correggere?»",
             detta(out) == "La richiesta lo dice già: se il gioco non lo fa, va corretto il "
                           "codice. Lo faccio correggere?", detta(out))


# ═══════════════════════════ 3. una correzione che non dice cosa ═══════════════════════════

def prova_correzione_vaga(tmp: Path):
    print("— 3. una correzione che non descrive niente → «Cosa non va?»")
    from calliope.sviluppo import senza_contenuto
    sv = SimpleNamespace(titolo="Halloween - Le Porte Magiche")
    for c in ("va modificato Calliope", "non funziona", "correggilo", "c'è un problema",
              "non va bene niente", "è rotto, sistemalo"):
        verifica(f"«{c}» non descrive niente", senza_contenuto(c, sv, correzione=True), c)
    for c in ("non si vedono i mostri dietro le porte",
              "non vengono assegnati punti e vince uno senza motivo", "si blocca dopo tre turni",
              "la porta scelta sparisce"):
        verifica(f"contrario: «{c}» descrive il problema",
                 not senza_contenuto(c, sv, correzione=True), c)

    import prova_specifica_viva as S
    agente = S.AgenteVivo(requisiti=REQ, stima="piccolo",
                          modifiche=[{"tipo": "difetto", "operazioni": []}])
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "corr_vaga", agente)
    n = len(svc.lavori)
    out = S.chiama(reg, ctx, "sviluppo_correggi", {"problema": "va modificato Calliope"}, 4,
                   "Calliope va modificato Calliope.")
    verifica("08:46: «va modificato Calliope» → «Cosa non va?», nessun lavoro parte",
             detta(out).startswith("Cosa non va?") and len(svc.lavori) == n
             and "sviluppo_correggi_vago" in ctx.regole and agente.quante("operazioni") == 0,
             f"{ctx.regole} {detta(out)}")
    ctx.tool_in_sospeso = "sviluppo_correggi"
    import prova_estensioni as P
    ctx.regole, ctx.user_text = [], "Non si vedono i mostri dietro le porte."
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": "non si vedono i mostri dietro le "
                                                         "porte"}, turno=5)
    verifica("…la risposta descrive il problema: la correzione parte",
             len(svc.lavori) == n + 1 and "sviluppo_correzione" in ctx.regole, str(ctx.regole))
    # Contrario: il «sì» a «Lo faccio correggere?» con un problema breve non passa dal criterio
    agente2 = S.AgenteVivo(requisiti=REQ, stima="piccolo")
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "corr_si", agente2)
    n = len(svc.lavori)
    ctx.tool_in_sospeso, ctx.regole, ctx.user_text = "sviluppo_correggi", [], "Sì."
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": "non funziona"}, turno=4)
    verifica("contrario: il «sì» a «Lo faccio correggere?» è una correzione",
             len(svc.lavori) == n + 1 and "sviluppo_correggi_vago" not in ctx.regole,
             str(ctx.regole))


# ═══════════════════════════ 4. sviluppo_chiedi con una risposta vecchia ═══════════════════════════

VECCHIA = ("Il lavoro si è fermato perché stava per finire le sue passate. Il codice fa scegliere "
           "da 2 a 4 giocatori.")
NUOVA = "Il tocco sulla porta non chiama la funzione che apre la porta: per questo non succede niente."


def agente_chiedi(requisiti=REQ):
    """Il modello dell'agente che, con le domande di prima nel contesto, ripete la risposta
    vecchia (come qwen3.6 il 12/10); senza, risponde alla domanda."""
    import prova_specifica_viva as S

    class Agente(S.AgenteVivo):
        def chat(self, body, **kw):
            props = ((body.get("format") or {}).get("properties") or {})
            if "serve_correzione" in props:
                self.richieste.append(body)
                testo = body["messages"][-1]["content"]
                voce = VECCHIA if "Domanda già fatta" in testo else NUOVA
                return {"content": json.dumps({"voce": voce, "serve_correzione": False})}
            return super().chat(body, **kw)
    return Agente(requisiti=requisiti, stima="piccolo")


def prova_chiedi(tmp: Path):
    print("— 4. sviluppo_chiedi: niente risposte vecchie ridette, le segnalazioni a correggi")
    import prova_specifica_viva as S
    agente = agente_chiedi()
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "chiedi", agente)
    # Una domanda fatta su una versione di prima (11:11, versione 7 contro la 11 delle 12:06)
    sv.chiesti.append({"quando": 1.0, "domanda": "scrivere", "voce": VECCHIA, "dettagli": VECCHIA,
                       "versione": (sv.versione or 1) - 1, "lavoro": "L0",
                       "correzione": True, "cosa_correggere": "fermarsi prima"})
    out = S.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Secondo te perché è bloccato?"}, 4,
                   "Secondo te perché è bloccato?")
    contesto = agente.richieste[-1]["messages"][-1]["content"]
    verifica("12:06: la domanda di una versione di prima non è nel contesto, e la risposta è "
             "nuova", "Domanda già fatta" not in contesto and NUOVA.rstrip(".") in detta(out)
             and VECCHIA[:30] not in detta(out), detta(out))
    verifica("…e la sua diagnosi non va alla correzione",
             svc.sviluppi.diagnosi(sv) is not None
             and svc.sviluppi.diagnosi(sv)["voce"] == NUOVA, str(svc.sviluppi.diagnosi(sv)))
    # Sulla stessa versione: la risposta di prima ridetta a una domanda diversa → di nuovo,
    # senza le domande di prima
    sv.chiesti[-1]["voce"] = VECCHIA
    n = len(agente.richieste)
    out = S.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Come si assegnano i punti?"}, 5,
                   "Come si assegnano i punti?")
    verifica("11:11:59: la stessa risposta a una domanda diversa → chiesta di nuovo senza le "
             "domande di prima (`sviluppo_chiedi_ripetuta`)",
             len(agente.richieste) == n + 2 and "sviluppo_chiedi_ripetuta" in ctx.regole
             and NUOVA.rstrip(".") in detta(out), f"{ctx.regole} {detta(out)}")
    sv.chiesti = [dict(sv.chiesti[-1], voce=VECCHIA)]
    n = len(agente.richieste)
    S.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Come si assegnano i punti?"}, 6,
             "Come si assegnano i punti?")
    verifica("contrario: la stessa domanda rifatta può avere la stessa risposta (una chiamata)",
             len(agente.richieste) == n + 1 and "sviluppo_chiedi_ripetuta" not in ctx.regole,
             str(ctx.regole))
    # Una correzione con una diagnosi vecchia: non va all'agente
    sv.chiesti = [dict(sv.chiesti[0], versione=-5, voce="DIAGNOSI VECCHIA",
                       dettagli="DIAGNOSI VECCHIA")]
    agente.modifiche.append({"tipo": "difetto", "operazioni": []})
    n_lav = len(svc.lavori)
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": "non si vedono i mostri dietro le "
                                                         "porte"}, 7, "Non si vedono i mostri.")
    lav = svc.lavori[-1]
    verifica("la correzione non riceve la diagnosi di una versione di prima",
             len(svc.lavori) == n_lav + 1 and "DIAGNOSI VECCHIA" not in (lav.vincoli or "") and "non si vedono i mostri"
             in (lav.vincoli or ""), lav.vincoli)
    # I dati del turno e le descrizioni: una segnalazione va a sviluppo_correggi
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "chiedi_riga", agente_chiedi())
    riga = svc.sviluppi.riga_fase(sv)
    spec = reg.get("sviluppo_chiedi").description
    verifica("dati del turno: «non porta a nulla» → sviluppo_correggi, «perché?» → "
             "sviluppo_chiedi", "«non porta a nulla»" in riga and "sviluppo_correggi" in riga
             and "Se un risultato è sbagliato" not in riga, riga)
    verifica("…e la descrizione di sviluppo_chiedi lo dice", "è sviluppo_correggi" in spec, spec)
    from calliope.sviluppo import SISTEMA_CHIEDI
    verifica("…e il sistema dell'agente: una segnalazione si risponde su quella, niente "
             "risposte di prima", "non ripetere la risposta a una domanda di prima"
             in SISTEMA_CHIEDI and "serve_correzione = true" in SISTEMA_CHIEDI)


# ═══════════════════════════ 5. la scelta alla revisione, detta senza tool ═══════════════════════════

class BackendFinto:
    def __init__(self, copione):
        self.copione, self.visti = list(copione), []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from self.copione.pop(0)


def brain_finto(cfg, reg, ctx, copione):
    from calliope.brain import Brain
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, reg, []
    b.tool_ctx = ctx
    b.backend = BackendFinto(copione)
    b.turn_number = 0
    return b


def alla_revisione(tmp: Path):
    import prova_specifica_viva as S
    agente = S.AgenteVivo(requisiti=REQ, stima="piccolo", voci=lambda n: [{"stato": "fatto"}] * (
        n - 1) + [{"stato": "manca", "nota": "Non dà punti."}])
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp, agente)
    out = S.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, 4,
                   "Possiamo passare alla revisione.")
    return cfg, reg, ctx, est, svc, sv, out


COMPLETA = [{"id": "c1", "name": "sviluppo_passo", "arguments": {"azione": "completa"}}]


def prova_scelta(tmp: Path):
    print("— 5. la seconda strada della revisione detta per intero → completa")
    cfg, reg, ctx, est, svc, sv, out = alla_revisione(tmp / "scelta")
    sosp = out.get("in_sospeso") or {}
    verifica("la revisione chiede le due strade, con un messaggio suo per il modello",
             detta(out).endswith("Vuoi attivarla così com'è, o faccio continuare l'agente con "
                                 "quello che manca?")
             and "anche con un «no» davanti" in str(sosp.get("messaggio")), str(sosp))
    from calliope import stato_dialogo
    ctx.regole, ctx.user_text = [], "No, farlo continuare con quello che manca."
    promessa = ("D'accordo, allora faccio continuare l'agente per completare quello che manca. "
                "Ti avviso quando è pronto.")
    b = brain_finto(cfg, reg, ctx, [[("text", promessa)], [("calls", COMPLETA)]])
    b.set_pending(sosp)
    p = stato_dialogo.proposta_da_oggi(b.pending, "sviluppo_passo", 1, reg)
    verifica("per lo stato del dialogo non è un sì/no (il blocco non toglie le strade)",
             p is not None and p.tipo == "dato", str(p))
    n = len(svc.lavori)
    detto = "".join(b.stream_reply("No, farlo continuare con quello che manca.", "amministra"))
    verifica("12:20: la promessa senza tool non si dice; la spinta, e la completa parte",
             "Ti avviso quando è pronto" not in detto.split("D'accordo: l'agente")[0]
             and "spinta_sviluppo" in b.rules_fired() and len(svc.lavori) == n + 1
             and detto.strip().startswith("D'accordo: l'agente continua con quello che manca"),
             f"{b.rules_fired()} «{detto}»")
    verifica("…il primo giro ha visto il messaggio delle due strade",
             any("È una scelta tra due strade" in (m.get("content") or "")
                 for m in b.backend.visti[0]))

    # 6c: il testo del modello prima del tool con la sua frase non si dice
    cfg, reg, ctx, est, svc, sv, out = alla_revisione(tmp / "taciuto")
    ctx.regole = []
    b = brain_finto(cfg, reg, ctx, [[("text", "Ho capito, procedo con la fase successiva."),
                                     ("calls", COMPLETA)]])
    b.set_pending(out["in_sospeso"])
    detto = "".join(b.stream_reply("Assolutamente deve continuare con quello che manca.",
                                   "amministra"))
    verifica("11:13: il testo prima del tool non si dice né si attacca alla frase del tool",
             "procedo" not in detto and detto.startswith("D'accordo: l'agente continua")
             and "sviluppo_testo_taciuto" in b.rules_fired(), f"{b.rules_fired()} «{detto}»")

    # Contrari
    b = brain_finto(cfg, reg, ctx, [[("text", "Sono le dieci.")]])
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("contrario: senza una domanda dello sviluppo in sospeso nessuna spinta",
             detto == "Sono le dieci." and "spinta_sviluppo" not in b.rules_fired()
             and len(b.backend.visti) == 1, detto)
    cfg, reg, ctx, est, svc, sv, out = alla_revisione(tmp / "altro")
    ctx.regole = []
    b = brain_finto(cfg, reg, ctx, [[("text", "È l'ultimo esame prima dell'attivazione.")]])
    b.set_pending(out["in_sospeso"])
    n = len(svc.lavori)
    detto = "".join(b.stream_reply("Cosa vuol dire revisione?", "amministra"))
    verifica("contrario: una risposta a parole che non promette niente si dice com'è (una "
             "passata, niente parte)", detto == "È l'ultimo esame prima dell'attivazione."
             and len(svc.lavori) == n and len(b.backend.visti) == 1
             and "spinta_sviluppo" not in b.rules_fired(), detto)
    from calliope.brain import SVILUPPO_PROMESSA
    for f, atteso in (("Faccio continuare l'agente.", True), ("Ti avviso quando è pronto.", True),
                      ("Procedo con la fase successiva.", True), ("Lo faccio correggere.", True),
                      ("Siamo ancora all'analisi.", False), ("Vuoi che lo apra?", False),
                      ("La revisione dice cosa manca.", False)):
        verifica(f"promessa dello sviluppo: «{f}» → {atteso}",
                 bool(SVILUPPO_PROMESSA.search(f)) == atteso)
    b = brain_finto(cfg, reg, ctx, [[("text", "Sono le dieci.")]])
    b._net = lambda nome: nome != "spinta_sviluppo"
    b.set_pending(out["in_sospeso"])
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("contrario: con la rete spenta il testo si dice com'è", detto == "Sono le dieci."
             and len(b.backend.visti) == 1, detto)


# ═══════════════════════════ 6. i testi della voce ═══════════════════════════

def prova_testi(tmp: Path):
    print("— 6. i testi della voce: la prova sullo schermo, i giocatori, i comandi, il fuori tema")
    import prova_specifica_viva as S
    from calliope.estensioni.scheda import in_parole
    agente = S.AgenteVivo(requisiti=REQ, stima="piccolo",
                          modifiche=[{"tipo": "difetto", "operazioni": []}])
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "testi", agente)
    from calliope.tools.sviluppo import ANTEPRIMA
    svc.sviluppi.collaudo(sv, ANTEPRIMA, True, "aperto in prova sullo schermo", anteprima=True)
    out = S.chiama(reg, ctx, "sviluppo_correggi", {"problema": "non si vedono i mostri dietro "
                                                               "le porte"}, 4,
                   "Non si vedono i mostri dietro le porte.")
    f = detta(out)
    verifica("(a) la correzione di un gioco: «…la prova sullo schermo», mai «con «in prova "
             "sullo schermo»»", "sullo schermo" in f and "«in prova sullo schermo»" not in f, f)
    p = in_parole({"scheda": SCHEDA})
    verifica("(b) «è un gioco sullo schermo, da 2 a 4 giocatori» e «con un comando»",
             p[0] == "è un gioco sullo schermo, da 2 a 4 giocatori"
             and "si gioca a voce o toccando, con una fase e un comando" in p, str(p))
    p = in_parole({"scheda": dict(SCHEDA, giocatori={"min": 1, "max": 1},
                                  macchina=_macchina("apri", "chiudi"))})
    verifica("…un giocatore solo e due comandi", p[0] == "è un gioco sullo schermo per un "
             "giocatore" and "si gioca a voce o toccando, con una fase e 2 comandi" in p, str(p))
    p = in_parole({"scheda": dict(SCHEDA, giocatori={"min": 2, "max": 2})})
    verifica("…2 giocatori", p[0] == "è un gioco sullo schermo per 2 giocatori", str(p))
    svs = svc.sviluppi
    sv.fuori_tema = {}
    sv.fase = "sviluppo"
    r = svs.riga_fuori_tema(sv)
    verifica("(d) la riga del fuori tema allo sviluppo dice cosa succede, non «siamo allo "
             "sviluppo»", r.startswith(f"Lo sviluppo di «{sv.titolo}» resta aperto: ")
             and "siamo allo sviluppo" not in r and "Intanto restiamo" not in r, r)
    sv.fuori_tema, sv.fase = {}, "collaudo"
    r = svs.riga_fuori_tema(sv)
    verifica("…al collaudo «siamo al collaudo»", r.endswith("resta aperto: siamo al collaudo."),
             r)


# ═══════════════════════════ 7. le correzioni che non correggono ═══════════════════════════

def prova_correzioni(tmp: Path):
    print("— 7. la seconda correzione sa che la prima non ha funzionato")
    import prova_specifica_viva as S
    from calliope.tools.sviluppo import VINCOLO_CORREZIONE_GIOCO
    agente = S.AgenteVivo(requisiti=REQ, stima="piccolo",
                          modifiche=[{"tipo": "difetto", "operazioni": []}] * 2)
    cfg, reg, ctx, est, svc, sv = al_collaudo(tmp / "correzioni", agente)
    problema = ("non si vedono i mostri dietro le porte, non vengono assegnati punti e il "
                "vincitore viene indicato senza spiegazione")
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 4,
             "Non ho trovato nessun mostro dietro le porte, nessun punto, e a un certo punto "
             "vince uno dei due senza motivo.")
    primo = svc.lavori[-1]
    verifica("la prima correzione di un gioco: il vincolo del gioco (gioco.js, un test sulle "
             "mosse dette), niente «la correzione di prima»",
             primo.correzione and VINCOLO_CORREZIONE_GIOCO.strip() in primo.vincoli
             and "NON ha funzionato" not in primo.vincoli, primo.vincoli)
    item = S.consegna(svc, est, sv)
    verifica("08:46: la correzione che consegna il codice uguale a prima non è «pronto»: "
             "l'esito onesto e «Lo rimando all'agente?»",
             "il codice è uguale a prima" in item["messaggio"]
             and (item.get("in_sospeso") or {}).get("tool") == "sviluppo_correggi"
             and "mostri" in str((item.get("in_sospeso") or {}).get("argomenti")),
             item["messaggio"])
    detto = ("È sempre esattamente uguale a prima: quando un giocatore clicca su una porta non "
             "si vede nessun mostro e la partita finisce senza punti.")
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 6, detto)
    secondo = svc.lavori[-1]
    verifica("11:42: la seconda correzione dice all'agente che la prima non ha funzionato",
             secondo is not primo and "GIÀ una correzione" in secondo.vincoli
             and "NON ha funzionato" in secondo.vincoli, secondo.vincoli)
    verifica("…con le parole dette adesso (il problema passato era lo stesso di prima)",
             "esattamente uguale a prima" in secondo.vincoli, secondo.vincoli)
    # Contrario: una correzione che cambia il codice si annuncia come sempre
    import prova_estensioni as P
    import prova_sviluppo as SS
    import prova_sviluppo_v2 as V
    n = est.archivio.nuova_candidata(P.valida(SS.M2), {"estensione.py": (
        V.CODICE_GEO + "# corretto" + chr(10)).encode()}, "Dario", {"eseguiti": 4, "falliti": 0},
        {"rischi": [], "sintassi": []}, secondo.id, True)
    item = svc.finisci(secondo, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       test={"eseguiti": 4, "falliti": 0}, messaggio="ho corretto il gioco.")
    verifica("contrario: la correzione che cambia il codice si annuncia come sempre",
             "uguale a prima" not in item["messaggio"] and sv.fase == "collaudo",
             item["messaggio"])
    from calliope.tools.sviluppo import _detto_adesso
    verifica("contrario: le parole uguali al problema non si ripetono",
             _detto_adesso(SimpleNamespace(user_text=problema), problema) == ""
             and _detto_adesso(SimpleNamespace(user_text="Sì."), problema) == "")


# ═══════════════════════════ 8. l'avviso di fine giro in uno sviluppo ═══════════════════════════

def prova_avviso_giro():
    print("— 8. l'avviso vicino al tetto: in uno sviluppo è la fine del giro, non del lavoro")
    from calliope.agenti.ciclo import Agente

    class Lav:
        avvisato = False
        id = "L1"

        def __init__(self, tappe):
            self.tappe = tappe

        def nota(self, *a, **k):
            pass
    finto = SimpleNamespace(tetto_token=lambda lav: 100_000, trascorso=lambda lav: 10,
                            passi_giro=lambda lav: 22, max_passi=24, token_giro=lambda lav: 10,
                            tempo_max_s=1800, log=lambda *a: None)
    m = [{"role": "user", "content": "compito"}]
    Agente._avviso_fine(finto, Lav(True), m)
    testo = m[-1]["content"]
    verifica("sviluppo: un'azione («il passo concreto», «non consegnare a metà»), niente conto "
             "alla rovescia né «sta per finire»",
             "passo concreto" in testo and "non consegnare a metà" in testo
             and "sta per finire" not in testo and "2" not in testo, testo)
    m = [{"role": "user", "content": "compito"}]
    Agente._avviso_fine(finto, Lav(False), m)
    verifica("contrario: fuori da uno sviluppo «Adesso chiudi… chiama consegna», anche lì senza "
             "numeri", "Adesso chiudi" in m[-1]["content"] and "chiama consegna" in m[-1]["content"]
             and "sta per finire" not in m[-1]["content"], m[-1]["content"])


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        prova_stesso_gioco(tmp)
        prova_modifica_vaga(tmp)
        prova_correzione_vaga(tmp)
        prova_chiedi(tmp)
        prova_scelta(tmp)
        prova_testi(tmp)
        prova_correzioni(tmp)
        prova_avviso_giro()
    print()
    print("Tutto bene." if not errori else f"{errori} errori.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
