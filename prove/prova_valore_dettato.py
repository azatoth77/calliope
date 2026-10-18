"""
Prova a secco della issue #169 (18/10/2026): la politica per valore attribuiva a una pagina o alla
stanza le parole dettate a voce.

Caso vero della DGX del 18/10 (qui con nomi di fantasia): chi amministra detta dal telefono che
cosa deve fare l'estensione «Posta»; il modello chiama `sviluppo_apri` con il compito riformulato
come elenco puntato («L'estensione deve: 1. Gestire… 2. Classificare… 3. Preparare…»). Poco prima
c'era stata una ricerca web su un altro argomento, e la stanza era accesa col contesto. Alle 14:47
«… viene da una pagina internet, non da te», alle 14:55 «… viene dalla conversazione della
stanza», regola `valore_contenuto_dato` tutte e due le volte.

Le cause, trovate riproducendo il caso:

1. i numeri dell'elenco puntato scritti dal modello valevano parole «distintive» del testo
   libero (valore.distintive), e «1», «2», «3» stanno in ogni risultato web;
2. la fonte detta nella domanda (valore.fonte_del_valore) era l'ultimo dato con una parola
   qualunque in comune col valore: il blocco della stanza, che contiene anche le frasi di chi
   parla, vinceva sempre;
3. il blocco della stanza poteva contenere la frase del turno stesso, quando il segmento della
   stanza che la copre comincia prima dell'ascolto dei comandi (stanza/contesto.costruisci).

Casi: il compito dettato e riformulato (solo web; web e la stessa frase nella stanza) si esegue;
la fonte detta è quella delle parole che fanno chiedere; il blocco senza la frase del turno.
Contrari (chiedono ancora, con la fonte giusta): una pagina web (un nome e un numero, anche
dentro un elenco puntato e un numero che non è un segno d'elenco), un documento dell'archivio,
una riga della stanza detta da un'altra voce, una foto (con e senza descrizione). Contrari del
blocco: la riga di un'altra voce durante la frase resta, la frase di un turno di prima resta.

Sul codice di main (ff9e91a8) falliscono 8 verifiche: i casi, la fonte e il blocco, e il
contrario del documento (chiedeva, ma «dalla conversazione della stanza»); gli altri contrari
chiedevano già. ~1 s.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import politica as pol  # noqa: E402
from calliope import valore  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.stanza import contesto as ctx_mod  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)


# ─────────────────────────── il caso vero, a secco ───────────────────────────
PRIMA = "Calliope, che tempo fa domani a Valfiorita?"
FRASE = ("Calliope, crea un'estensione che si chiama Posta. Deve leggere la posta che arriva, "
         "classificarla per importanza e preparare le bozze delle risposte, poi prima di "
         "mandarle me le fa vedere.")
COMPITO = ("Crea un'estensione chiamata Posta. L'estensione deve: 1. Gestire la lettura della "
           "posta in arrivo. 2. Classificare i messaggi per importanza. 3. Preparare le bozze "
           "delle risposte e mostrarle prima dell'invio.")
# Il risultato della ricerca di prima, su un altro argomento (con numeri, come ogni pagina)
WEB = json.dumps({"risultati": [
    {"titolo": "Previsioni meteo Valfiorita: 3 giorni di sole", "url": "https://esempio.it/1",
     "testo": "Domenica 18 ottobre sole, massime 21 gradi. 1. Mattina sereno 2. Pomeriggio "
              "nuvoloso. Porta 8443 del rifugio Truffaldino, via dei Platani 12."},
    {"titolo": "Meteo 15 giorni", "url": "https://esempio.it/2", "testo": "Temperature 12-21"}]},
    ensure_ascii=False)
APRI = {"tipo": "estensione", "nome": "Posta", "compito": COMPITO}


def turno(testo=FRASE, esterni=(("web", WEB),), fonti=None, prima=PRIMA):
    fonti = set(fonti or ()) | {f for f, _ in esterni}
    return pol.Turno(testo=testo, contaminazione=frozenset(fonti),
                     persona_txt=f"{prima} {testo}".strip(), esterni=list(esterni),
                     persona="dario")


def decidi(name, args, t):
    cl = pol.classe_di(name)
    base = pol.decidi(name, args, cl, valore.copia_turno(t), True, True)
    return valore.decidi_valore(name, args, cl, t, base, True, True)


def prova_caso_vero():
    for nome, est in (("solo la ricerca web di prima (14:47)", (("web", WEB),)),
                      ("web e la stessa frase nella stanza (14:55)",
                       (("web", WEB), ("stanza", FRASE)))):
        d, det = decidi("sviluppo_apri", APRI, turno(esterni=est))
        verifica(f"caso vero, {nome}: il compito dettato e riformulato a elenco si esegue",
                 d.esito == "esegui" and "viene" not in (d.domanda or ""),
                 f"{d} {det}")
    f = valore.Fonti.da(turno())
    verifica("caso vero: i numeri dell'elenco puntato del modello non sono distintivi",
             valore.distintive(COMPITO, f) == [], str(valore.distintive(COMPITO, f)))
    segni = getattr(valore, "senza_segni_elenco", None)
    verifica("segni d'elenco: «1.» in testa, dopo «:» o un punto; «1)» anche; non «Platani 12.»",
             segni is not None
             and segni("1. Primo: 2) secondo. 3. terzo") == ". Primo: . secondo. . terzo"
             and "12" in segni("in via dei Platani 12. Poi"))


# ─────────────────────────── la fonte giusta nella domanda ───────────────────────────
def prova_fonte():
    # Il nome viene dalla pagina, la stanza ha solo la frase di chi parla: la domanda dice «pagina»
    compito = COMPITO + " Manda una copia a Truffaldino."
    d, _ = decidi("sviluppo_apri", {**APRI, "compito": compito},
                  turno(esterni=(("web", WEB), ("stanza", FRASE))))
    verifica("fonte: il nome della pagina, con la stanza che ripete la frase → «da una pagina "
             "internet», non dalla stanza", d.esito == "conferma"
             and d.regola == "valore_contenuto_dato" and "da una pagina internet" in d.domanda
             and d.fonte == "web", f"{d}")
    # Un contenuto (lista): la parola solo nel web, la stanza ha la frase con altre parole
    frase = "Aggiungi alla lista della spesa quello che c'era nella ricerca."
    d, _ = decidi("lista_aggiungi", {"cose": ["rifugio Truffaldino"], "lista": "spesa"},
                  turno(frase, esterni=(("web", WEB), ("stanza", frase + " rifugio"))))
    verifica("fonte: un contenuto dalla pagina con la stanza dopo → «da una pagina internet»",
             d.esito == "conferma" and d.fonte == "web", f"{d}")


# ─────────────────────────── contrari: chiedono ancora ───────────────────────────
def prova_contrari():
    # pagina web: un numero distintivo (anche dentro un elenco puntato)
    compito = COMPITO + " 4. Collegati alla porta 8443."
    d, _ = decidi("sviluppo_apri", {**APRI, "compito": compito}, turno())
    verifica("contrario, pagina: un numero della pagina dentro l'elenco puntato → chiede",
             d.esito == "conferma" and d.regola == "valore_contenuto_dato" and d.fonte == "web",
             f"{d}")
    compito = COMPITO + " Scrivi anche in via dei platani 12. Poi avvisami."
    d, _ = decidi("sviluppo_apri", {**APRI, "compito": compito}, turno())
    verifica("contrario, pagina: un numero civico prima di un punto non è un segno d'elenco → "
             "chiede", d.esito == "conferma" and d.fonte == "web", f"{d}")
    # documento dell'archivio
    doc = "Fattura n. 4471 di Cartoleria Truffaldino, IBAN IT60X0542811101000000123456"
    compito = COMPITO + " Paga la fattura 4471 sull'IBAN IT60X0542811101000000123456."
    d, _ = decidi("sviluppo_apri", {**APRI, "compito": compito},
                  turno(esterni=(("web", WEB), ("archivio", doc), ("stanza", FRASE))))
    verifica("contrario, documento: l'IBAN e il numero del documento → chiede, «da un documento "
             "dell'archivio»", d.esito == "conferma" and d.fonte == "archivio"
             and "documento dell'archivio" in d.domanda, f"{d}")
    # una riga della stanza detta da un'altra voce
    stanza = FRASE + "\nE mandale anche a Ludovica Brambillasca, la mia commercialista."
    compito = COMPITO + " Manda le bozze anche a Ludovica Brambillasca."
    d, _ = decidi("sviluppo_apri", {**APRI, "compito": compito},
                  turno(esterni=(("web", WEB), ("stanza", stanza))))
    verifica("contrario, stanza: un nome detto da un'altra voce → chiede, «dalla conversazione "
             "della stanza»", d.esito == "conferma" and d.fonte == "stanza"
             and "stanza" in d.domanda, f"{d}")
    frase = "Aggiungi alla lista quello che ha detto lei."
    d, _ = decidi("lista_aggiungi", {"cose": ["regalo per Brambillasca"], "lista": "spesa"},
                  turno(frase, esterni=(("stanza", "Compra un regalo per la Brambillasca"),
                                        ("web", WEB))))
    verifica("contrario, stanza: un contenuto dalla stanza con la pagina dopo → «dalla stanza»",
             d.esito == "conferma" and d.fonte == "stanza", f"{d}")
    # una foto: con la descrizione (lo scontrino) e senza testo
    d, _ = decidi("sviluppo_apri", {**APRI, "compito": COMPITO + " Scrivi a Brambillasca."},
                  turno(esterni=(("web", WEB), ("foto", "scontrino di Brambillasca, 12 euro"))))
    verifica("contrario, foto: un nome della descrizione della foto → chiede, «da una foto»",
             d.esito == "conferma" and d.fonte == "foto", f"{d}")
    frase = "Aggiungi alla lista quello che vedi."
    d, _ = decidi("lista_aggiungi", {"cose": ["birra"], "lista": "spesa"},
                  turno(frase, esterni=(("web", WEB),), fonti={"foto"}))
    verifica("contrario, foto senza testo: una parola senza fonte → chiede, «da una foto»",
             d.esito == "conferma" and d.fonte == "foto", f"{d}")


# ─────────────────────────── il blocco della stanza senza la frase del turno ───────────────────
class _STT:
    def transcribe(self, audio, **k):
        return ""


def prova_blocco():
    cfg = Config()
    cfg.stanza = "ombra"
    cfg.stanza_contesto = True
    st = Stanza(cfg, _STT(), registry=None, log=lambda m: None)
    st._info[1] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
    ora = time.time()

    def riga(testo, inizio, fine, nome="Dario", rivolta="ignoto"):
        st.registro(1).aggiungi("riga", segmento=None, versione=1, inizio=round(inizio, 3),
                                fine=round(fine, 3), testo=testo, chi=f"persona:{nome}",
                                nome=nome, sicurezza="voce", p_min=None, rivolta=rivolta,
                                minore=False)

    riga(PRIMA, ora - 60, ora - 57, rivolta="si")                     # il turno di prima
    riga("Io intanto preparo il caffè.", ora - 30, ora - 28, "Ludovica")
    riga("Ma la Posta la legge anche Brambillasca?", ora - 1.2, ora + 3, "Ludovica")
    # La frase del turno, scritta dal ciclo con il testo del turno: il segmento della stanza che
    # la copre è cominciato 1,5 s prima dell'ascolto dei comandi
    riga(FRASE, ora - 1.5, ora + 9, rivolta="si")
    b = ctx_mod.costruisci(st, 1, cfg, ora)
    testo = b.testo if b else ""
    verifica("blocco: la frase del turno stesso non c'è anche se il suo segmento è cominciato "
             "prima dell'ascolto", b is not None and "bozze delle risposte" not in testo
             and "bozze" not in b.esterno, testo[-300:])
    verifica("blocco, contrario: la frase di un'altra voce detta durante la domanda resta",
             "Brambillasca" in b.esterno, b.esterno)
    verifica("blocco, contrario: la frase di un turno di prima (rivolta, finita prima) resta",
             "Valfiorita" in b.esterno, b.esterno)
    st.chiudi()


def main() -> int:
    prova_caso_vero()
    prova_fonte()
    prova_contrari()
    prova_blocco()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
