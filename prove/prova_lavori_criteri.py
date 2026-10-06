import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Prova a secco dei criteri del banco dei documenti (prove/prova_lavori.py): titoli di
sezione nelle forme equivalenti, dati detti in cifre e scritti in lettere, numeri ricavati
con un calcolo semplice contro numeri inventati. Con i casi contrari, presi dal banco del
02/10 con qwen3.6 su vLLM («118» per la babysitter, la relazione impaginata come lettera)."""

from prova_lavori import (DOCUMENTI, dato_presente, derivabili, in_lettere, numeri_inventati,
                          valuta_documento, _derivato, _sezioni, _titoli_testi, valore)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

errori = 0


def verifica(nome, cond, extra=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  ({extra})" if extra and not cond else ""))


def compito(did):
    return next(x[1] for x in DOCUMENTI if x[0] == did)


def par(t):
    return {"tipo": "paragrafo", "testo": t}


# ── valori e lettere ──
verifica("valore: 2.400 = 2400, 14,3, 12.5, 1.050,75", valore("2.400") == 2400
         and valore("14,3") == 14.3 and valore("12.5") == 12.5 and valore("1.050,75") == 1050.75)
verifica("in lettere: trenta, ventuno, ventotto, ventitré, cento, sette",
         [in_lettere(n) for n in (30, 21, 28, 23, 100, 7)]
         == ["trenta", "ventuno", "ventotto", "ventitré", "cento", "sette"])
verifica("dato «30» presente come «trenta giorni»", dato_presente("30", "entro trenta giorni"))
verifica("contrario: «30» non è «trentasei»", not dato_presente("30", "trentasei giorni"))
verifica("contrario: «30» non è in «nessun termine»", not dato_presente("30", "nessun termine"))

# ── numeri ricavati ──
c08 = derivabili(compito("d08"))
verifica("d08: 55 = 100 − 45 (autoconsumo 45 per cento)", _derivato("55", c08) is not None)
verifica("d08: 3.510 kWh autoconsumati = 7.800 × 45 / 100", _derivato("3.510", c08) is not None)
verifica("d08: 4.290 kWh immessi = 7.800 × 55 / 100", _derivato("4.290", c08) is not None)
verifica("d08 contrario: 24 non si ricava", _derivato("24", c08) is None)
verifica("d08: 1.300 ore equivalenti = 7.800 / 6", _derivato("1.300", c08) is not None)
verifica("d08 contrario: 429 W per pannello (6 kW in watt / 14) resta inventato",
         _derivato("429", c08) is None)
c01 = derivabili(compito("d01"))
verifica("d01: 150 m³ di gas risparmiati = 1.050 − 900", _derivato("150", c01) is not None)
verifica("d01: variazione 14,3 % del gas", _derivato("14,3", c01) is not None)
verifica("d01: 11,1 % di risparmio sulla luce", _derivato("11,1", c01) is not None)
verifica("d01 contrario: 14,9 non è la variazione", _derivato("14,9", c01) is None)
c04 = derivabili(compito("d04"))
verifica("d04: 18.500 = somma degli investimenti elencati", _derivato("18.500", c04) is not None)
verifica("d04: utile 25.000 = 85.000 − 60.000", _derivato("25.000", c04) is not None)
verifica("d04 contrario: 30.000 euro di prestito inventato", _derivato("30.000", c04) is None)
c06 = derivabili(compito("d06"))
verifica("d06 contrario: «118» (numero d'emergenza non detto) resta inventato",
         _derivato("118", c06) is None)
c02 = derivabili(compito("d02"))
verifica("d02 contrario: con «8 diapositive» e «2–4 punti» i numeri piccoli non fanno calcoli",
         _derivato("24", c02) is None and _derivato("32", c02) is None)
verifica("d02 contrario: senza «per cento» dopo il numero niente complemento",
         _derivato("92", c02) is None)
der = []
inv = numeri_inventati({"titolo": "x", "blocchi": [par(
    "Produzione 7.800 kWh: il 45 per cento in autoconsumo e il restante 55 per cento in "
    "rete. Assistenza al numero 800 123 456.")]}, compito("d08"), der)
verifica("numeri_inventati: 55 accettato con la spiegazione, 800/123/456 inventati",
         inv == ["123", "456", "800"] and der == ["55 = 100 − 45"], f"{inv} {der}")

inv = numeri_inventati({"titolo": "x", "blocchi": [par(
    "Autoconsumo al quarantacinque per cento, il restante cinquanta per cento in rete; "
    "quattordici pannelli.")]}, compito("d08"))
verifica("numeri in lettere: «cinquanta» (era 55) inventato, 45 e 14 detti, «per cento» no",
         inv == ["50"], str(inv))
inv = numeri_inventati({"titolo": "x", "blocchi": [par(
    "Il restante cinquantacinque per cento va in rete; eventi e ventilazione.")]}, compito("d08"))
verifica("numeri in lettere contrario: «cinquantacinque» è ricavato, «eventi» non è venti",
         inv == [], str(inv))

# ── titoli di sezione ──
doc_blocchi = {"titolo": "R", "blocchi": [{"tipo": "titolo", "testo": "Introduzione"},
                                          par("Testo.")]}
doc_riga = {"titolo": "R", "blocchi": [par("INTRODUZIONE\nLa presente relazione…"),
                                       par("Luce:\nNel 2025 2.400 kWh.")]}
doc_solo = {"titolo": "R", "blocchi": [par("Diapositiva 1: Perché separare"),
                                       {"tipo": "elenco", "voci": ["a", "b"]}]}
verifica("titolo come blocco", _titoli_testi(doc_blocchi) == ["Introduzione"])
verifica("titolo come prima riga del paragrafo (maiuscolo o con «:»)",
         _titoli_testi(doc_riga) == ["INTRODUZIONE", "Luce:"])
verifica("titolo come paragrafo breve seguito da un elenco",
         _titoli_testi(doc_solo) == ["Diapositiva 1: Perché separare"])
contrari = {"titolo": "R", "blocchi": [
    par("La presente relazione illustra i consumi."),            # frase con il punto
    par("con la presente si richiede\nla manutenzione"),          # minuscola
    par("- prima voce\n- seconda voce"),                          # elenco col trattino
    par("[Città], 2 ottobre 2026\naltro"),                        # segnaposto
    par("Un paragrafo lungo che non è un titolo perché ha troppe parole per esserlo davvero "
        "e continua\nancora"),
    par("Cordiali saluti")]}                                      # ultimo blocco, niente dopo
verifica("contrari: frasi, minuscole, trattini, segnaposto, righe lunghe, ultimo blocco",
         _sezioni(contrari) == 0, str(_titoli_testi(contrari)))

# ── documenti interi (forme viste nel banco del 02/10) ──
d01 = {"titolo": "Relazione Consumi Domestici 2025", "blocchi": [
    par("INTRODUZIONE\nLa presente relazione illustra i consumi domestici del 2025."),
    par("LUCE\nNel 2025 la luce è stata di 2.400 kWh, contro i 2.700 del 2024: un risparmio "
        "di 300 kWh, pari all'11,1 per cento."),
    par("GAS\nIl gas è sceso a 900 metri cubi dai 1.050 del 2024, cioè 150 in meno."),
    par("ACQUA\nL'acqua è stata di 110 metri cubi."),
    par("CONCLUSIONI\nI consumi sono diminuiti.")]}
r = valuta_documento("d01", d01, "fatto")
verifica("d01 con i titoli nel testo e i numeri ricavati: giusto", r["ok"], str(r))
r = valuta_documento("d01", {"titolo": "R", "blocchi": [par("Luce 2.400, 2.700, 300 kWh; gas "
                                                          "900 e 1.050; acqua 110.")]}, "fatto")
verifica("d01 contrario: senza sezioni non passa", not r["ok"] and r["struttura"] is False)
lettera = {"titolo": "Business plan", "blocchi": [
    par("[luogo], 2 ottobre 2026"), par("Spett.le [Destinatario]"),
    par("Oggetto: Business plan breve per apertura forno di quartiere"),
    par("Con la presente si sottopone il progetto. Ricavi 85.000 euro, costi 60.000."),
    {"tipo": "tabella", "colonne": ["Voce", "Importo (€)"],
     "righe": [["Forno", 12000], ["Arredi", 5000], ["Licenze", 1500]], "totale": True},
    par("Cordiali saluti")]}
r = valuta_documento("d04", lettera, "fatto")
verifica("d04 contrario: business plan impaginato come lettera (senza sezioni) non passa",
         not r["ok"] and r["struttura"] is False, str(r))
lettera["blocchi"][1:3] = [{"tipo": "titolo", "testo": "Descrizione"}, par("Un forno."),
                           {"tipo": "titolo", "testo": "Mercato"}, par("Il quartiere.")]
r = valuta_documento("d04", lettera, "fatto")
verifica("d04 con le sezioni e il totale: giusto", r["ok"], str(r))
r = valuta_documento("d06", {"titolo": "Babysitter", "blocchi": [
    par("Luca ha 6 anni e va a letto alle 21; Sara ha 3 anni, è allergica alle arachidi e va "
        "a letto alle 20. Cena alle 19:30."), par("Emergenze: chiama il 118."),
    par("Pediatra: [numero]."), par("Genitori: [numero].")]}, "fatto")
verifica("d06 contrario: «118» è inventato", not r["ok"] and r["inventati"] == ["118"], str(r))
r = valuta_documento("d03", {"titolo": "Lettera", "blocchi": [
    par("Spett.le Comune"), par("Oggetto: marciapiede di via Roma 12"),
    par("Segnalazione del 3 marzo, protocollo 4521."), par("Risposta entro trenta giorni."),
    par("Distinti saluti"), par("Banco")]}, "fatto")
verifica("d03: «trenta giorni» vale per il dato 30", r["ok"], str(r))

# ── sezioni vuote (scrittore e banco) ──
from calliope.documenti.scrittore import empty_sections  # noqa: E402


def tit(t):
    return {"tipo": "titolo", "testo": t}


scaletta = {"titolo": "Scaletta", "blocchi": [tit("Diapositiva 1"), par("Testo."),
            tit("Diapositiva 2"), {"tipo": "elenco", "voci": ["a", "b"]}]
            + [tit(f"Diapositiva {i}") for i in range(3, 9)]}
verifica("sezioni vuote: 6 titoli in fila senza contenuto",
         len(empty_sections(scaletta)) == 6, str(empty_sections(scaletta)))
r = valuta_documento("d02", scaletta, "fatto")
verifica("d02 contrario: 8 titoli ma contenuto solo in 2 non passa la struttura",
         r["struttura"] is False, str(r))
verifica("sezioni vuote contrario: titolo e sottotitolo in cima, poi contenuto",
         empty_sections({"blocchi": [tit("Relazione"), tit("Introduzione"), par("x")]}) == [])

print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
