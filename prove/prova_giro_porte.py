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
    cfg, reg, ctx, est, svc, sv, out = ambiente_gioco(tmp, agente)
    lav = S.ultimo(svc)
    S.chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id, "tappe": False}, 2, "Sì.")
    S.consegna(svc, est, sv)
    vero = est.archivio.manifesto

    def con_scheda(nome, n=None):
        m = vero(nome, n)
        return dict(m, scheda={"titolo": TITOLO}) if m else m
    est.archivio.manifesto = con_scheda
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


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        prova_stesso_gioco(tmp)
        prova_modifica_vaga(tmp)
    print()
    print("Tutto bene." if not errori else f"{errori} errori.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
