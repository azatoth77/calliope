import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Scrivere invece di parlare nella pagina vera (Edge o Chromium senza finestra, protocollo
DevTools, come prova_schermi_pagina.py): uno schermo personale abbinato riceve un modulo con
partita IVA, codice fiscale, IBAN, data, importo e righe; si scrive una partita IVA con la
cifra di controllo sbagliata e la pagina lo dice **mentre si scrive**; si corregge, si
compila il resto e si invia: al server arrivano i valori esatti. Poi la casella «scrivi a
Calliope» manda una frase, e una scheda che arriva mentre si scrive in un modulo non lo
cancella. Nessun errore JavaScript.

Senza Edge né Chromium la prova si salta (esce con 0 e lo dice).
"""

import shutil
import time

from prova_schermi_pagina import TMP, Pagina, aspetta, browser, porta_libera  # noqa: E402

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Mittente, Schermi, schede
from calliope.schermi.moduli import campo
from calliope.schermi.server import ServerSchermi

ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def scrivi(pagina, selettore, valore):
    """Come una persona: il valore nel campo e l'evento «input» (poi «change»)."""
    pagina.valuta(
        f"(() => {{ const i = document.querySelector({selettore!r}); i.focus();"
        f" i.value = {valore!r}; i.dispatchEvent(new Event('input', {{bubbles: true}}));"
        f" i.dispatchEvent(new Event('change', {{bubbles: true}})); }})()")


def errore(pagina, nome):
    return pagina.valuta(
        f"(document.querySelector('.campo-modulo[data-nome=\"{nome}\"] .errore-campo')||{{}})"
        f".textContent||''") or ""


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main() -> int:
    exe = browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    cfg = Config()
    cfg.memory_db = str(TMP / "scritto.db")
    cfg.config_dir = str(TMP)
    port = porta_libera()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    srv = ServerSchermi(hub, "127.0.0.1", port).avvia()
    r = hub.archivio.nuova_richiesta()
    hub.archivio.abbina(r["codice"], "studio", "dario-id", "Dario")
    pagina = Pagina(exe, f"http://127.0.0.1:{port}/#t={r['richiesta']}", profilo="scritto")
    dario = Mittente(persona="dario-id", nome="Dario", livello="amministra", certo=True)
    try:
        verifica("pagina personale collegata", aspetta(lambda: hub.collegati(), 20) is not None)
        pagina.valuta("window.__errori = []; window.addEventListener('error', "
                      "(e) => window.__errori.push(String(e.message)))")
        verifica("casella «scrivi a Calliope» visibile", aspetta(lambda: pagina.valuta(
            "!!document.getElementById('scrivi') && !document.getElementById('scrivi').hidden"),
            5) is not None)
        # Senza conversazione a voce (05/10): casella spenta, con la parola da dire
        verifica("senza conversazione: casella spenta con «Di' «Calliope» per scrivermi»",
                 aspetta(lambda: pagina.valuta(
                     "document.getElementById('scrivi-testo').disabled && document"
                     ".getElementById('scrivi-testo').placeholder.includes('Calliope')"
                     " && !document.querySelector('#scrivi .nota-scrittura').hidden"), 15)
                 is not None)
        spec = {"chiave": "prova", "titolo": "Dati per la fattura",
                "domanda": "Mi servono questi dati.",
                "campi": [campo("piva", "Partita IVA", "partita_iva"),
                          campo("cf", "Codice fiscale", "codice_fiscale", False),
                          campo("iban", "IBAN", "iban"),
                          campo("data", "Data", "data"),
                          campo("importo", "Importo", "importo"),
                          campo("righe", "Voci", "righe")]}
        ricevuti = []
        res = hub.moduli.apri(spec, lambda v, t: ricevuti.append(v), dario, "prova",
                              "amministra")
        verifica("modulo consegnato alla pagina", res["mostrato"])
        verifica("modulo disegnato", aspetta(lambda: pagina.valuta(
            "document.querySelectorAll('.modulo .campo-modulo').length") == 6, 15) is not None)
        verifica("senza conversazione: «Invia» del modulo spento, i campi no", pagina.valuta(
            "document.querySelector('.invia-modulo').disabled && !document.querySelector("
            "'.campo-modulo input').disabled"))
        hub.conversazioni.voce("dario-id", "voce")       # Dario parla a Calliope
        verifica("conversazione: casella e «Invia» si riaccendono da soli", aspetta(
            lambda: pagina.valuta("!document.getElementById('scrivi-testo').disabled && "
                                  "!document.querySelector('.invia-modulo').disabled"), 15)
            is not None)
        # Partita IVA con l'ultima cifra sbagliata: l'errore appena si arriva a 11 cifre
        scrivi(pagina, '.campo-modulo[data-nome="piva"] input', "1234567890")
        verifica("10 cifre mentre si scrive: ancora nessun errore", errore(pagina, "piva") == "")
        scrivi(pagina, '.campo-modulo[data-nome="piva"] input', "12345678904")
        verifica("cifra di controllo sbagliata: mostrata mentre si scrive",
                 errore(pagina, "piva") == "La cifra di controllo non torna",
                 errore(pagina, "piva"))
        scrivi(pagina, '.campo-modulo[data-nome="piva"] input', "12345678903")
        verifica("corretta: l'errore sparisce", errore(pagina, "piva") == "")
        scrivi(pagina, '.campo-modulo[data-nome="cf"] input', "RSSMRA80A01H501V")
        verifica("codice fiscale: carattere di controllo sbagliato",
                 errore(pagina, "cf") == "Il carattere di controllo non torna", errore(pagina, "cf"))
        scrivi(pagina, '.campo-modulo[data-nome="cf"] input', "rssmra80a01h501u")
        scrivi(pagina, '.campo-modulo[data-nome="iban"] input', "IT61 X054 2811 1010 0000 0123 456")
        pagina.valuta("document.querySelector('.campo-modulo[data-nome=\"iban\"] input')"
                      ".dispatchEvent(new Event('focusout', {bubbles: true}))")
        verifica("IBAN: controllo mod 97", errore(pagina, "iban") == "Il codice di controllo "
                 "non torna", errore(pagina, "iban"))
        # Una scheda che arriva mentre si scrive non cancella il modulo
        hub.invia(schede.calcolo("2+2", "4"), dario)
        time.sleep(0.6)
        verifica("una scheda nuova non sostituisce il modulo in corso", pagina.valuta(
            "document.querySelectorAll('.modulo .campo-modulo').length") == 6 and pagina.valuta(
            "document.querySelector('.campo-modulo[data-nome=\"piva\"] input').value")
            == "12345678903")
        # Invio con un errore: non parte
        pagina.valuta("document.querySelector('.invia-modulo').click()")
        time.sleep(0.5)
        verifica("invio con errori: bloccato nella pagina", not ricevuti and hub.ingresso.vuoto()
                 and "Controlla" in (pagina.valuta(
                     "document.querySelector('.esito-modulo').textContent") or ""))
        scrivi(pagina, '.campo-modulo[data-nome="iban"] input', "IT60 X054 2811 1010 0000 0123 456")
        scrivi(pagina, '.campo-modulo[data-nome="data"] input', "2026-10-03")
        scrivi(pagina, '.campo-modulo[data-nome="importo"] input', "1.234,50")
        scrivi(pagina, '.campo-modulo[data-nome="righe"] [data-k="descrizione"]', "Consulenza")
        scrivi(pagina, '.campo-modulo[data-nome="righe"] [data-k="quantita"]', "2")
        scrivi(pagina, '.campo-modulo[data-nome="righe"] [data-k="prezzo"]', "500")
        pagina.valuta("document.querySelector('.invia-modulo').click()")
        t = aspetta(lambda: not hub.ingresso.vuoto(), 15)
        item = hub.ingresso.prendi()
        attesi = {"piva": "12345678903", "cf": "RSSMRA80A01H501U",
                  "iban": "IT60X0542811101000000123456", "data": "2026-10-03",
                  "importo": 1234.5, "righe": [{"descrizione": "Consulenza", "quantita": 2,
                                                "prezzo": 500, "aliquota": None}]}
        verifica("invio: al server i valori esatti, già controllati",
                 t is not None and item and item["valori"] == attesi, str(item and item["valori"]))
        verifica("la pagina dice «inviato»", aspetta(lambda: "Inviato" in (pagina.valuta(
            "document.querySelector('.esito-modulo').textContent") or ""), 15) is not None)
        # La casella
        scrivi(pagina, "#scrivi-testo", "Calliope, che ore sono?")
        pagina.valuta("document.querySelector('#scrivi button').click()")
        t = aspetta(lambda: not hub.ingresso.vuoto(), 15)
        item = hub.ingresso.prendi()
        verifica("casella: la frase arriva in coda con la persona dello schermo",
                 t is not None and item["tipo"] == "scritto" and item["persona"] == "dario-id"
                 and item["testo"] == "Calliope, che ore sono?", str(item))
        # La pagina svuota la casella quando arriva la risposta HTTP, che può arrivare dopo
        # la frase in coda: si aspetta (06/10; prima un controllo solo, falliva sotto carico)
        verifica("casella svuotata e «inviato»", aspetta(lambda: pagina.valuta(
            "document.getElementById('scrivi-testo').value") == "" and "Inviato" in (
            pagina.valuta("document.querySelector('.esito-scrivi').textContent") or ""),
            15) is not None)
        # Parla un'altra persona: lo scritto di Dario si spegne (e un modulo aperto si chiude)
        hub.moduli.apri(dict(spec, chiave="prova2"), lambda v, t: None, dario, "prova",
                        "amministra")
        aspetta(lambda: pagina.valuta("!!document.querySelector('.modulo .invia-modulo')"), 15)
        hub.conversazioni.voce("bianca-id", "voce")
        verifica("parla un'altra persona: casella spenta, modulo chiuso con la nota", aspetta(
            lambda: pagina.valuta("document.getElementById('scrivi-testo').disabled") and
            "conversazione è finita" in (pagina.valuta(
                "(document.querySelector('.nota-modulo') || {}).textContent") or ""), 15)
            is not None)
        err = pagina.valuta("window.__errori") or []
        verifica("nessun errore JavaScript", not err, str(err))
    finally:
        pagina.chiudi()
        srv.ferma()
        hub.archivio.close()
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
