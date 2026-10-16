import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La risposta alla domanda di un tool in sospeso è la richiesta (16/10/2026, issue #98). A
secco, con Brain vero, la politica per valore accesa, la stanza accesa e un modello finto (nomi
di fantasia).

Caso vero della DGX del 15/10 alle 19:58: chi amministra registra Bianca con la stanza accesa;
la frase di sfida è giusta, `registra_utente` chiede la data di nascita, chi amministra la dice
e la politica per valore rifiutava (`valore_non_ancorata`, «la persona non ha chiesto azioni»):
la data non ha le parole del tool. Poi una seconda frase di sfida, a pochi secondi dalla prima.

1. **Il caso vero**: la data detta dalla stessa persona, con la stanza accesa, è la risposta alla
   domanda del tool (regola `valore_risposta_sospeso`) e la sfida superata nella frase che ha
   aperto la domanda vale anche per lei (`valore_sfida_sospeso`): eseguito senza seconda sfida.
2. **Contrari**: la data solo in una riga della stanza; un'altra persona che risponde; un tool
   diverso da quello in sospeso; oltre `azione_in_sospeso_s`; gli argomenti della domanda
   cambiati; nessun valore nuovo; un valore nuovo senza parole (un booleano); la domanda della
   politica (vuole un sì); una foto arrivata con la frase. La sfida non si porta: con la voce
   non riconosciuta in questa frase, con una domanda nata senza sfida, e la sfida superata non
   resta dopo la chiamata.
3. **pc_guarda** (20:23 dello stesso giorno): «fai una foto a questo dispositivo» e «scatta una
   foto» lo chiedono; «la foto di ieri era bella», «è scattato l'allarme», «non fare foto» no.

    python prove\\prova_risposta_sospeso.py
"""

import dataclasses
import time
from types import SimpleNamespace

from calliope import politica as pol
from calliope import valore
from calliope.conferme import chiedi_conferma

from prove.prova_politica import ChiParla, Prof, chiama, testo, turno
from prove.prova_valore import prepara

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


STANZA = "Carlo: domani andiamo al lago con la macchina nuova."
DOMANDA = ("Quando è nato o nata Bianca? Mi serve la data di nascita per sapere come parlarci e "
           "cosa può fare; se è maggiorenne, dimmi solo che è maggiorenne.")
NOME = {"nome": "Bianca"}
CON_DATA = {"nome": "Bianca", "nascita": "2015-10-12"}


def stanza(righe=STANZA):
    """Il blocco della stanza di un turno (calliope/stanza/contesto.py): un dato non fidato."""
    return SimpleNamespace(testo=f"[Conversazione nella stanza]\n{righe}", esterno=righe,
                           riassunto="", righe=1)


def prepara_registra():
    """Brain con registra_utente finto ma con i controlli del vero (tools/builtin.py,
    _nuovo_profilo): senza data chiede la data con una proposta in sospeso; con la data vuole la
    frase di sfida superata in questa frase (SpeakerContext.sfida_superata)."""
    b, eseguiti, _ = prepara(True)
    visti = []

    def registra(ctx, nome, nascita="", maggiorenne=None, tutori=""):
        sc = ctx.speaker_ctx
        if not str(nascita or "").strip() and not maggiorenne:
            return {"ok": False, "fatto": "NON è partita la registrazione: manca la data",
                    "conferma": DOMANDA, "risposta_finale": DOMANDA,
                    "in_sospeso": {"tool": "registra_utente", "argomenti": {"nome": nome},
                                   "domanda": DOMANDA,
                                   "messaggio": "Messaggio di sistema: hai chiesto la data."}}
        args = {"nome": nome, "nascita": nascita}
        if not getattr(sc, "sfida_superata", False):
            return chiedi_conferma(ctx, "registra_utente", args, f"registrare {nome}")
        visti.append(("registra_utente", args))
        return {"ok": True, "risposta_finale": f"Ho registrato {nome}."}

    b.tools.register(dataclasses.replace(b.tools.get("registra_utente"), func=registra))
    sc = ChiParla("Dario", "amministra")
    b.tool_ctx.speaker_ctx = sc
    return b, visti, eseguiti, sc


def frase(b, sc, testo_frase, *risposte, righe=STANZA):
    """Una frase detta con la stanza accesa; come il ciclo, la sfida superata vale una frase."""
    sc.sfida_superata = False
    b.stanza_turno = stanza(righe)
    return turno(b, testo_frase, *risposte, chi=sc)


def fino_alla_domanda():
    """«Registra Bianca» con la stanza accesa → frase di sfida → superata → la domanda della
    data. Restituisce Brain pronto per la risposta."""
    b, visti, eseguiti, sc = prepara_registra()
    r1 = frase(b, sc, "Calliope, registra Bianca.", chiama("registra_utente", NOME))
    s = sc.sfida
    r2 = frase(b, sc, s.testo) if s is not None else ""
    return b, visti, eseguiti, sc, (r1, s is not None), r2


def regole(b):
    return b.rules_fired()


# ─────────────────────────── 1. il caso vero ───────────────────────────
def prova_caso_vero():
    b, visti, _, sc, (r1, chiesta), r2 = fino_alla_domanda()
    verifica("19:58:28: con la stanza accesa «registra Bianca» chiede la frase di sfida",
             chiesta and not visti, r1)
    verifica("19:58:28: sfida giusta → registra_utente chiede la data, proposta in sospeso",
             "Quando è nato o nata Bianca?" in r2 and b.pending
             and b.pending.get("tool") == "registra_utente", f"{r2} {b.pending}")
    verifica("la proposta ricorda la sfida della stessa persona (sfida_di)",
             (b.pending or {}).get("sfida_di") == "dario", str(b.pending))
    r3 = frase(b, sc, "È nata il 12 ottobre 2015.", chiama("registra_utente", CON_DATA),
               testo("Ho registrato Bianca."))
    rr = regole(b)
    verifica("19:58:37: la data detta da chi amministra con la stanza accesa → eseguito",
             visti == [("registra_utente", CON_DATA)], f"{visti} {r3} {rr}")
    verifica("senza seconda frase di sfida e senza «non me l'hai chiesto»",
             "valore_non_ancorata" not in rr and "sfida_voce" not in rr
             and "valore_e4_sfida" not in rr, str(rr))
    verifica("le regole nel registro: valore_risposta_sospeso e valore_sfida_sospeso",
             "valore_risposta_sospeso" in rr and "valore_sfida_sospeso" in rr, str(rr))
    verifica("la sfida superata non resta dopo la chiamata (vale solo per lei)",
             sc.sfida_superata is False and not pol.sfida_portata(b.tool_ctx))
    # Data detta col mese a parole e scritta dal modello in cifre, o «come detta»
    b, visti, _, sc, _, _ = fino_alla_domanda()
    frase(b, sc, "Il tre marzo del 2016.", chiama("registra_utente",
                                                   {"nome": "Bianca", "nascita": "3 marzo 2016"}))
    verifica("la data «come detta» (il tre marzo del 2016) vale", len(visti) == 1, str(visti))
    # La risposta che comincia con un consenso: il «sì» non è alla domanda della politica
    for f in ("Sì, è nata il 12 ottobre 2015.", "Ok, il 12 ottobre 2015."):
        b, visti, _, sc, _, _ = fino_alla_domanda()
        frase(b, sc, f, chiama("registra_utente", CON_DATA), testo("Ho registrato Bianca."))
        verifica(f"«{f}» → eseguito senza altre domande", visti == [("registra_utente", CON_DATA)]
                 and "valore_sfida_sospeso" in regole(b), f"{visti} {regole(b)}")


# ─────────────────────────── 2. contrari ───────────────────────────
def prova_contrari():
    # a. la data solo in una riga della stanza, non nella frase
    b, visti, _, sc, _, _ = fino_alla_domanda()
    frase(b, sc, "Te l'ha detto Carlo, guarda lì.", chiama("registra_utente", CON_DATA),
          testo("Va bene."),
          righe="Carlo: Bianca è nata il 12 ottobre 2015, segnatelo.")
    rr = regole(b)
    verifica("contrario: la data solo nella riga della stanza → rifiuto, niente eseguito",
             not visti and "valore_risposta_sospeso" not in rr
             and "valore_non_ancorata" in rr, f"{visti} {rr}")
    # b. un'altra persona che amministra risponde: la proposta non è sua (una conversazione
    # per persona; Brain._take_pending)
    b, visti, _, sc, _, _ = fino_alla_domanda()
    b.tool_ctx.speakers.p["Elio"] = Prof("elio", "Elio", True)
    altra = ChiParla("Elio", "amministra")
    b.stanza_turno = stanza()
    turno(b, "È nata il 12 ottobre 2015.", chiama("registra_utente", CON_DATA),
          testo("Va bene."), chi=altra)
    rr = regole(b)
    verifica("contrario: un'altra persona che risponde → niente ancora, niente eseguito",
             not visti and "valore_risposta_sospeso" not in rr
             and "valore_sfida_sospeso" not in rr, f"{visti} {rr}")
    # c. un tool diverso da quello in sospeso
    b, visti, eseguiti, sc, _, _ = fino_alla_domanda()
    frase(b, sc, "È nata il 12 ottobre 2015.",
          chiama("lista_aggiungi", {"lista": "spesa", "voci": ["12 ottobre 2015"]}),
          testo("Va bene."))
    rr = regole(b)
    verifica("contrario: un tool diverso da quello in sospeso → niente ancora",
             not eseguiti and "valore_risposta_sospeso" not in rr, f"{eseguiti} {rr}")
    # d. oltre azione_in_sospeso_s
    b, visti, _, sc, _, _ = fino_alla_domanda()
    b.pending["scade"] = time.monotonic() - 1
    frase(b, sc, "È nata il 12 ottobre 2015.", chiama("registra_utente", CON_DATA),
          testo("Va bene."))
    rr = regole(b)
    verifica("contrario: oltre azione_in_sospeso_s → niente ancora, niente eseguito",
             not visti and "valore_risposta_sospeso" not in rr
             and "valore_non_ancorata" in rr, f"{visti} {rr}")
    # e. la voce non riconosciuta in questa frase: l'ancora sì, la sfida no (si richiede)
    b, visti, _, sc, _, _ = fino_alla_domanda()
    sc.identified_by, sc.from_session = "conversazione", True
    frase(b, sc, "È nata il 12 ottobre 2015.", chiama("registra_utente", CON_DATA),
          testo("Va bene."))
    rr = regole(b)
    verifica("contrario: voce non riconosciuta in questa frase → la sfida non si porta",
             not visti and "valore_sfida_sospeso" not in rr, f"{visti} {rr}")
    # f. la domanda della data nata senza frase di sfida (la conversazione pulita) e poi la
    # stanza: l'ancora vale, la sfida no
    b, visti, _, sc = prepara_registra()
    sc.sfida_superata = False
    b.stanza_turno = None
    turno(b, "Calliope, registra Bianca.", chiama("registra_utente", NOME), chi=sc)
    verifica("senza stanza la domanda della data arriva senza sfida",
             b.pending and not b.pending.get("sfida_di"), str(b.pending))
    frase(b, sc, "È nata il 12 ottobre 2015.", chiama("registra_utente", CON_DATA),
          testo("Va bene."))
    rr = regole(b)
    verifica("contrario: domanda nata senza sfida → ancorata ma con la sua frase di sfida",
             not visti and "valore_risposta_sospeso" in rr
             and "valore_sfida_sospeso" not in rr and sc.sfida is not None, f"{visti} {rr}")


def _t(testo_frase, **k):
    base = dict(testo=testo_frase, contaminazione=frozenset({"stanza"}),
                esterni=[("stanza", STANZA)], in_sospeso="registra_utente",
                args_sospeso=dict(NOME), persona_txt="registra Bianca")
    base.update(k)
    return pol.Turno(**base)


def prova_unita():
    r = valore.risposta_al_sospeso
    verifica("unità: la data detta, gli argomenti della domanda più la data → risposta",
             r("registra_utente", CON_DATA, _t("È nata il 12 ottobre 2015.")))
    verifica("unità: la data solo nella stanza → no",
             not r("registra_utente", CON_DATA, _t(
                 "Te l'ha detto Carlo.", esterni=[("stanza", "Bianca è nata il 12/10/2015")])))
    verifica("unità: la data in parte nella frase e in parte nella stanza → no",
             not r("registra_utente", CON_DATA, _t(
                 "È nata nel 2015.", esterni=[("stanza", "il 12 ottobre")])))
    verifica("unità: un altro tool → no",
             not r("ricorda", {"fatto": "Bianca è nata il 12 ottobre 2015"},
                   _t("È nata il 12 ottobre 2015.")))
    verifica("unità: nessuna proposta in sospeso (altra persona, scaduta) → no",
             not r("registra_utente", CON_DATA, _t("È nata il 12 ottobre 2015.",
                                                    in_sospeso=None)))
    verifica("unità: il nome cambiato → no",
             not r("registra_utente", {"nome": "Bianca Neri", "nascita": "2015-10-12"},
                   _t("È nata il 12 ottobre 2015.")))
    verifica("unità: nessun valore nuovo → no",
             not r("registra_utente", dict(NOME), _t("Sì, lei.")))
    verifica("unità: un valore nuovo senza parole (maggiorenne=true) → no",
             not r("registra_utente", {"nome": "Bianca", "maggiorenne": True},
                   _t("È maggiorenne.")))
    verifica("unità: la domanda della politica (vuole un sì) → no",
             not r("registra_utente", CON_DATA, _t("È nata il 12 ottobre 2015.",
                                                    sospeso_politica=True)))
    verifica("unità: una foto arrivata con la frase → no",
             not r("registra_utente", CON_DATA, _t("È nata il 12 ottobre 2015.",
                                                    dato_nuovo=True)))
    verifica("unità: proposta senza argomenti in forma di dizionario → no",
             not r("registra_utente", CON_DATA, _t("È nata il 12 ottobre 2015.",
                                                    args_sospeso=None)))


# ─────────────────────────── 3. pc_guarda ───────────────────────────
def prova_pc_guarda():
    cl = pol.classe_di("pc_guarda")
    for f in ("Fai una foto a questo dispositivo", "Scatta una foto al router",
              "Fammi una foto della lavagna", "Fotografa la scrivania"):
        verifica(f"pc_guarda chiesto: «{f}»", pol.chiesto_con_verbi(cl, f, {"cosa": "webcam"}))
    for f in ("La foto di ieri era bella", "È scattato l'allarme stanotte",
              "Non fare foto, per favore", "Ho messo le foto nella cartella"):
        verifica(f"contrario pc_guarda: «{f}»",
                 not pol.chiesto_con_verbi(cl, f, {"cosa": "webcam"}))
    t = _t("Fai una foto a questo dispositivo", in_sospeso=None, args_sospeso=None)
    verifica("20:23:24: «fai una foto a questo dispositivo» con la stanza → ancorata",
             valore.ancorata(cl, "pc_guarda", {"cosa": "webcam"}, t))
    t = _t("La foto di ieri era bella", in_sospeso=None, args_sospeso=None)
    verifica("contrario: «la foto di ieri era bella» non diventa una chiamata ancorata",
             not valore.ancorata(cl, "pc_guarda", {"cosa": "webcam"}, t))


if __name__ == "__main__":
    prova_unita()
    prova_caso_vero()
    prova_contrari()
    prova_pc_guarda()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)
