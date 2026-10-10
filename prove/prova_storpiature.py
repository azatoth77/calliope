import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Le forme chiuse brevi storpiate da Whisper (10/10/2026, casi veri della DGX con whisper.cpp,
satellite «studio», giri delle 06:09–06:18 e 07:11–07:21). A secco.

1. **«Ricominciamo» storpiato** vale come la forma chiusa (wakeword.nuova_conversazione_come,
   regola `nuova_conversazione_storpiata`): «Calliope ricominciava.» (il modello aveva RIPRESO
   uno sviluppo sospeso), «Calliope ricominciavo.», e con il nome storpiato in più parole
   davanti: «E lì appena ricominciamo.» (il modello aveva FATTO PARTIRE il lavoro dell'agente),
   «Da lì poi ricominciamo.», «E lì è per ricominciare.» (09/10).
2. **Le altre storpiature** («Annullahi.», «Am nulla il lavoro.», «Nulla è lavoro.»,
   «Chiudin.», «Giudino.», «Spendilo.», «Alla ora, ok.») sono un dato del turno per il modello
   (calliope/storpiature.py, regola `forma_storpiata`), e «annulla» da solo vale «no» nella
   corsia veloce (in ombra).
3. **La rete generale** (politica `politica_avvio_non_chiesto`): un lavoro dell'agente che parte
   o riparte (sviluppo_passo avanti, rifai, riprendi; lavoro_affida) da una frase breve senza le
   parole dell'azione né un consenso chiede conferma; il «sì» lo esegue.

Ogni regola con i suoi contrari: frasi normali con le stesse parole («ricomincia da capo il
programma», «annulla la sveglia delle 7», «chiudi la finestra», «spendi meno»…).

    python prove\\prova_storpiature.py
"""

import dataclasses

from calliope import politica as pol
from calliope.brain import Brain
from calliope.config import Config
from calliope.risposte import forma_chiusa
from calliope.storpiature import STORPIATA_MSG, suggerisci
from calliope.tools.spec import ToolContext
from calliope.wakeword import nuova_conversazione_come, prefisso_nome

import prove.prova_politica as pp
from prove.prova_politica import ChiParla, Persone, chiama, testo

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


# ─────────────────────────── 1. «ricominciamo» storpiato ───────────────────────────

def prova_ricominciamo():
    for frase, atteso in [
            # i casi veri
            ("Calliope ricominciava.", "storpiata"), ("Calliope ricominciavo.", "storpiata"),
            ("E lì appena ricominciamo.", "storpiata"), ("Da lì poi ricominciamo.", "storpiata"),
            ("E lì è per ricominciare.", "storpiata"),
            # altre forme e storpiature vicine
            ("Calliope, ricominciammo.", "storpiata"), ("Calliope ricominciavamo!", "storpiata"),
            ("Calliope, ricomincio da capo.", "storpiata"), ("Calliope, ri cominciamo.", "storpiata"),
            ("Calliope, riccominciamo.", "storpiata"), ("Calliope ricominchiamo.", "storpiata"),
            # le forme giuste restano «esatte»
            ("Calliope. Ricominciamo.", "esatta"), ("Ricominciamo da capo, grazie.", "esatta"),
            ("Allora, ricominciamo.", "esatta"), ("Nuova conversazione.", "esatta"),
            # contrari: un oggetto, un'altra parola, una frase vera con «ricomincia»
            ("Ricomincia da capo il programma.", None), ("Ricominciamo il timer.", None),
            ("Ricominciava a piovere.", None), ("Calliope, ricominciava a piovere.", None),
            ("Domani ricominciamo.", None), ("E poi ricominciamo.", None),
            ("Dall'inizio ricominciamo.", None), ("Calliope, riconosciamo.", None),
            ("Calliope, ricomponiamo.", None), ("Calliope, ricordiamo.", None),
            ("Ricominciali.", None), ("Ricominciamo da dove eravamo.", None),
            ("Ricominciamo il collaudo.", None), ("Calliope, cominciamo.", None),
            ("La lista ricomincia.", None), ("Calliope, che ore sono?", None)]:
        verifica(f"ricominciamo «{frase}» → {atteso}", nuova_conversazione_come(frase, "Calliope")
                 == atteso, str(nuova_conversazione_come(frase, "Calliope")))
    # Il nome storpiato in più parole (lo scheletro delle consonanti di «Calliope»)
    for parole, atteso in [
            (["e", "li", "appena"], True), (["da", "li", "poi"], True), (["li", "e", "per"], True),
            (["alla", "ora"], True), (["luipe"], True),
            (["allora"], False), (["e", "poi"], False), (["dall", "inizio"], False),
            (["la", "lista"], False), (["il", "gioco"], False), (["domani"], False),
            (["al", "piu", "tardi"], False), (["napoli"], False), (["colpa"], False),
            (["lupo"], False), (["alpi"], False)]:
        verifica(f"nome storpiato {parole} → {atteso}", prefisso_nome(parole) == atteso)


# ─────────────────────────── 2. dato del turno e corsia veloce ───────────────────────────

def prova_suggerimenti():
    for frase, forse in [
            # i casi veri
            ("Annullahi.", "annulla"), ("Am nulla il lavoro.", "annulla il lavoro"),
            ("Nulla è lavoro.", "annulla il lavoro"), ("Anzi, no a nulla.", "annulla"),
            ("No, niente a nulla.", "annulla"), ("Calliope. Chiudin.", "chiudilo"),
            ("Giudino.", "chiudilo"), ("Chiudino sviluppo.", "chiudi lo sviluppo"),
            ("Spendilo.", "sospendilo"), ("Spendilo pure.", "sospendilo"),
            ("Alla ora, ok.", "Calliope, ok"), ("Luipe. Stop.", "Calliope, stop"),
            # vicine
            ("An nulla.", "annulla"), ("Spendi lo sviluppo.", "sospendi lo sviluppo"),
            ("Giudilo.", "chiudilo"),
            # contrari: frasi normali, forme vere, parole dentro frasi lunghe
            ("Annulla la sveglia delle 7.", None), ("Annulla.", None), ("Annullato.", None),
            ("Chiudi la finestra.", None), ("Chiudi.", None), ("Chiudilo.", None),
            ("Chiudi lo sviluppo.", None), ("Chiudi tutto.", None), ("Spendi meno.", None),
            ("Spendi tutto.", None), ("Quanto spendo?", None), ("Sospendilo.", None),
            ("Non serve a nulla.", None), ("Nulla.", None), ("No, nulla.", None),
            ("Non fa nulla.", None), ("Il giudice ha deciso.", None), ("Giudizio.", None),
            ("Allora, ok.", None), ("Ok.", None), ("Calliope, ok.", None),
            ("Spendilo per la spesa della settimana.", None),
            ("Am nulla il lavoro di oggi, quello delle sette.", None), ("", None)]:
        s = suggerisci(frase, "Calliope")
        verifica(f"storpiata «{frase}» → {forse}", (s or {}).get("forse") == forse, str(s))
    s = suggerisci("Spendilo.", "Calliope")
    verifica("il dato del turno: un dato, chiede se non è chiaro",
             "«Spendilo» potrebbe essere «sospendilo»" in STORPIATA_MSG.format(**s)
             and "chiedilo" in STORPIATA_MSG)
    # La corsia veloce (in ombra): solo «annulla» senza oggetto vale «no»
    for frase, atteso in [
            ("Annullahi.", "no"), ("Anzi, no a nulla.", "no"), ("No, niente a nulla.", "no"),
            ("Am nulla il lavoro.", None), ("Spendilo.", None), ("Chiudin.", None),
            ("Alla ora, ok.", None), ("Annulla.", "no"), ("Annulla la sveglia delle 7.", None)]:
        verifica(f"corsia veloce «{frase}» → {atteso}", forma_chiusa(frase) == atteso,
                 str(forma_chiusa(frase)))
    for frase in ("Calliope ricominciava.", "E lì appena ricominciamo."):
        verifica(f"corsia veloce «{frase}» → nuova", forma_chiusa(frase) == "nuova")


# ─────────────────────────── 3. la rete della politica ───────────────────────────

def _decidi(nome, args, frase, **k):
    cl = pol.classe_di(nome)
    return pol.decidi(nome, args, cl, pol.Turno(testo=frase, **k))


def prova_rete():
    AV, RI, RP = {"azione": "avanti"}, {"azione": "rifai"}, {"azione": "riprendi"}
    LA = {"compito": "una ricerca sulle batterie", "tipo": "ricerca"}
    # I casi veri: chiede conferma
    for nome, args, frase in [
            ("sviluppo_passo", RI, "Am nulla il lavoro."),
            ("sviluppo_passo", AV, "E lì appena ricominciamo."),
            ("sviluppo_passo", AV, "Spendilo."),
            ("sviluppo_passo", RP, "Calliope ricominciava."),
            ("sviluppo_passo", AV, "Szi, vogliati várla!"),
            ("sviluppo_passo", AV, "Rifallo così com'è."),     # il modello sceglie avanti
            ("sviluppo_passo", RI, "Nulla è lavoro."),
            ("lavoro_affida", LA, "Giudino."),
            ("sviluppo_passo", AV, "Spendilo.", )]:
        d = _decidi(nome, args, frase)
        verifica(f"rete: {nome}({args.get('azione', '')}) da «{frase}» chiede conferma",
                 d.esito == "conferma" and d.regola == "politica_avvio_non_chiesto"
                 and d.domanda.startswith("Non sono sicura di aver capito: vuoi che"),
                 f"{d.esito} {d.regola} {d.domanda}")
    # Alla proposta dello stesso tool: solo una forma storpiata nota («Spendilo.» a «vuoi che
    # vada avanti?», 07:14:44); il resto lo legge il modello («Non c'è problema.», 06:12:47)
    sosp = {"in_sospeso": "sviluppo_passo", "args_sospeso": AV}
    d = _decidi("sviluppo_passo", AV, "Spendilo.", **sosp)
    verifica("rete: «Spendilo.» alla proposta di andare avanti chiede conferma",
             d.regola == "politica_avvio_non_chiesto", f"{d.esito} {d.regola}")
    for frase in ("Non c'è problema.", "Mi sta bene.", "No, lascia stare."):
        d = _decidi("sviluppo_passo", AV, frase, **sosp)
        verifica(f"contrario: «{frase}» alla proposta dello stesso tool: decide il modello",
                 d.regola != "politica_avvio_non_chiesto", f"{d.esito} {d.regola}")
    # Contrari: le parole dell'azione, un consenso, un avvio generico, frase lunga, altre azioni
    for nome, args, frase, k in [
            ("sviluppo_passo", AV, "Vai avanti.", {}), ("sviluppo_passo", AV, "Procedi.", {}),
            ("sviluppo_passo", AV, "Ok.", {}), ("sviluppo_passo", AV, "Sì, vai.", {}),
            ("sviluppo_passo", AV, "Continua.", {}), ("sviluppo_passo", AV, "Approvo.", {}),
            ("sviluppo_passo", AV, "Fallo partire.", {}), ("sviluppo_passo", AV, "Parti pure.", {}),
            ("sviluppo_passo", AV, "Cominciamo.", {}), ("sviluppo_passo", AV, "Inizia.", {}),
            ("sviluppo_passo", AV, "Passiamo alla revisione.", {}),
            ("sviluppo_passo", AV, "Riprendiamo lo sviluppo.", {}),
            ("sviluppo_passo", AV, "Va bene così.", {}),
            ("sviluppo_passo", AV, "Attivala.", {}),
            ("sviluppo_passo", AV, "Direi che ci siamo, secondo me è a posto davvero.", {}),
            ("sviluppo_passo", AV, "Spendilo.", {"sfida": True}),
            ("sviluppo_passo", AV, "Sì.", {"in_sospeso": "sviluppo_passo", "args_sospeso": AV}),
            ("sviluppo_passo", RI, "Rifallo.", {}), ("sviluppo_passo", RI, "Riprova.", {}),
            ("sviluppo_passo", RI, "Ricominciamo il lavoro.", {}),
            ("sviluppo_passo", RI, "Di nuovo.", {}), ("sviluppo_passo", RI, "Sì, rifallo.", {}),
            ("sviluppo_passo", RP, "Riprendi lo sviluppo.", {}),
            ("sviluppo_passo", RP, "Riprendiamo.", {}), ("sviluppo_passo", RP, "Torniamo allo sviluppo.", {}),
            ("sviluppo_passo", RP, "Continua pure.", {}),
            ("lavoro_affida", LA, "Fai una ricerca sulle batterie.", {}),
            ("lavoro_affida", LA, "Cerca le batterie.", {}),
            ("lavoro_affida", LA, "Sì, grazie.", {}),
            # azioni che non fanno partire un lavoro: la rete non guarda
            ("sviluppo_passo", {"azione": "sospendi"}, "Spendilo.", {}),
            ("sviluppo_passo", {"azione": "chiudi"}, "Giudino.", {}),
            ("sviluppo_passo", {"azione": "ferma"}, "Am nulla il lavoro.", {}),
            ("sviluppo_passo", {"azione": "stato"}, "Spendilo.", {}),
            ("casa_comando", {"comando": "spegni la luce"}, "Spendilo.", {})]:
        d = _decidi(nome, args, frase, **k)
        verifica(f"contrario: {nome}({args.get('azione', '')}) da «{frase}» non è la rete",
                 d.regola != "politica_avvio_non_chiesto", f"{d.esito} {d.regola}")


# ─────────────────────────── 4. con Brain vero e un modello finto ───────────────────────────

class Copione:
    def __init__(self):
        self.risposte, self.visti = [], []

    def stream(self, messages, tools):
        self.visti.append(list(messages))
        if not self.risposte:
            yield ("text", "Va bene.")
            return
        yield from self.risposte.pop(0)


def prova_brain():
    cfg = Config()
    cfg.storia_inattiva_s = 0
    reg = pp.registro_completo()
    eseguiti = []

    def finto(nome):
        def f(ctx, **a):
            eseguiti.append((nome, dict(a)))
            return {"ok": True, "risposta_finale": "Rifaccio il lavoro."}
        return f

    reg.register(dataclasses.replace(reg.get("sviluppo_passo"), func=finto("sviluppo_passo")))
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=ChiParla("Dario", "amministra",
                                                                         "voce"), speaker=None)
    b = Brain(cfg, reg, ctx)
    b.backend = Copione()

    def turno(frase, *risposte, storpiata=None):
        b.backend.risposte = list(risposte)
        b.storpiata_turno = storpiata
        return "".join(b.stream_reply(frase, "amministra"))

    frase = "Am nulla il lavoro."
    r = turno(frase, chiama("sviluppo_passo", {"azione": "rifai"}),
              testo("Non sono sicura, vuoi che lo rifaccia?"),
              storpiata=suggerisci(frase, "Calliope"))
    dati = " ".join(str(m.get("content") or "") for m in b.backend.visti[0]
                    if m.get("role") == "system")
    verifica("caso vero: «Am nulla il lavoro.» → il modello riceve «annulla il lavoro»",
             "potrebbe essere «annulla il lavoro»" in dati and "forma_storpiata" in b.rules_fired(),
             str(b.rules_fired()))
    verifica("…e sviluppo_passo(rifai) non parte: la domanda",
             not eseguiti and "politica_avvio_non_chiesto" in b.rules_fired()
             and b.has_pending(), f"{eseguiti} {r} {b.rules_fired()}")
    r = turno("Sì.", chiama("sviluppo_passo", {"azione": "rifai"}))
    verifica("il «sì» lo esegue", eseguiti == [("sviluppo_passo", {"azione": "rifai"})]
             and "politica_avvio_non_chiesto" not in b.rules_fired(), f"{eseguiti} {r}")
    r = turno("Rifallo così com'è.", chiama("sviluppo_passo", {"azione": "rifai"}))
    verifica("contrario: «Rifallo così com'è.» → rifai subito", len(eseguiti) == 2
             and "forma_storpiata" not in b.rules_fired(), f"{eseguiti} {b.rules_fired()}")
    turno("Che tempo fa?", testo("Sole."))
    dati = " ".join(str(m.get("content") or "") for m in b.backend.visti[-1]
                    if m.get("role") == "system")
    verifica("il dato del turno vale una risposta sola", "potrebbe essere" not in dati)


def main():
    prova_ricominciamo()
    prova_suggerimenti()
    prova_rete()
    prova_brain()
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
