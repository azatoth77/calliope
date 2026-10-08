import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La vista dello sviluppo e il lavoro in diretta a schermo intero, nella pagina vera (08/10/2026:
richieste di Dario dopo il giro della DGX delle 14:36–15:30; schermo.js, telefono.js,
calliope/agenti/avanzamento.py, calliope/sviluppo.py). Edge o Chromium senza finestra (DevTools;
senza si salta), server degli schermi e dei satelliti veri su 127.0.0.1, lo sviluppo e il lavoro
con le classi vere (Sviluppi, Avanzamento) e un flusso finto dell'agente. Nomi di fantasia.

Schermo del computer (1280×800 e 1920×1080):
- lo sviluppo che si apre fa entrare lo schermo personale di chi sviluppa nella vista dello
  sviluppo: barra delle fasi con quella di adesso, nome, versione e giro; al centro due colonne
  (riepilogo del lavoro con i tetti, a destra il flusso dell'agente); sezioni del collaudo e delle
  domande; comandi a tocco;
- il flusso si accumula (gli elementi di prima restano gli stessi), per sezioni (ragionamento,
  testo, codice, chiamata, esito, separatore di passata), senza buchi né doppioni anche dopo una
  riconnessione con pezzi arrivati mentre la pagina era giù;
- lo scorrimento segue la coda, si ferma se chi guarda torna indietro («In fondo» compare) e
  riprende con «In fondo»;
- «Vista normale»: la scheda del lavoro senza il codice, con «Schermo intero» (due colonne, Esc
  chiude), e «Torna allo sviluppo» nella testa;
- al giro 2 i tetti sono di 48 passate e 60 minuti; il riepilogo dice «correzione 1, riparte
  dalla versione provata» e i numeri dello sviluppo intero;
- comandi: «A che punto siamo?» manda la frase come scritta (solo con la conversazione aperta),
  «Prova con…» la mette nella casella; nessun pulsante per approvare o attivare;
- sviluppo chiuso: lo schermo esce dalla vista; uno schermo di un'altra persona non cambia.
Telefono (375×812): la vista si apre a schermo intero da sola, in una colonna, con testo ≥ 16 px
e niente di lato; il carosello resta; chiusa con «Chiudi», un tocco sulla scheda la riapre; il
lavoro a schermo intero con il flusso; sviluppo chiuso: lo strato si chiude.
Nessun errore JavaScript né violazione della CSP. Con CALLIOPE_FOTO=<cartella> gli screenshot.
"""

import base64
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import prova_cruscotto as PC
import prova_cruscotto_pagina as PCP
import prova_scheda_intera as PSI
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-vista-sviluppo-"))
ERRORI = []
SALTATA = 77
T = "window.calliopeTelefono"


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


aspetta = PCP.aspetta


def foto(p, nome):
    cartella = os.environ.get("CALLIOPE_FOTO")
    if not cartella:
        return
    time.sleep(0.3)
    r = p._chiama("Page.captureScreenshot", {"format": "png"})
    Path(cartella).mkdir(parents=True, exist_ok=True)
    (Path(cartella) / nome).write_bytes(base64.b64decode(r["result"]["data"]))


def finestra(p, w, h, mobile=False):
    p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h,
                                                     "deviceScaleFactor": 2 if mobile else 1,
                                                     "mobile": mobile})
    aspetta(lambda: p.valuta(f"innerWidth === {w} && innerHeight === {h}"), 5, 0.05)
    p.valuta("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")


def clic(p, sel):
    r = p.valuta(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null;"
                 f" e.scrollIntoView({{block: 'nearest'}}); const b = e.getBoundingClientRect();"
                 f" return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
    if not r:
        return False
    for t in ("mousePressed", "mouseReleased"):
        p._chiama("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1], "button": "left",
                                               "clickCount": 1})
    return True


class Agente:
    """Un lavoro dello sviluppo con il flusso finto: gli eventi come li manda il ciclo vero
    (Lavoro.nota), e il testo atteso nella colonna del flusso."""

    def __init__(self, svs, hub, ident, correzione=False):
        from calliope.agenti.avanzamento import Avanzamento
        from calliope.agenti.ciclo import Lavoro
        from calliope.schermi.hub import Mittente
        self.lav = Lavoro(ident, "estensione", "meteo per città", "dario", "Dario",
                          titolo="Meteo città")
        self.lav.cartella = str(TMP / f"lavoro-{ident}")
        if correzione:
            self.lav.correzione = True
        dario = Mittente("dario", "Dario", "amministra", True)
        self.lav.on_scheda = lambda card: hub.invia(card, dario)
        self.av = Avanzamento(lambda lav=None: (24, 150000, 1800), sviluppo=svs.riepilogo_lavoro,
                              intervallo=0.2, log=lambda m: None)
        self.atteso = ""
        self.av.segui(self.lav)
        self.lav.stato, self.lav.inizio = "in_corso", time.time()

    def passata(self):
        self.lav.nota("passata")
        self.lav.passi += 1
        self.lav.token += 900

    def scrive(self, tipo, testo, pezzi=4):
        n = max(1, len(testo) // pezzi)
        for i in range(0, len(testo), n):
            self.lav.nota("flusso", tipo=tipo, testo=testo[i:i + n])
            time.sleep(0.01)
        self.atteso += testo

    def codice(self, percorso, testo):
        grezzo = json.dumps({"percorso": percorso, "contenuto": testo}, ensure_ascii=False)
        for i in range(0, len(grezzo), 7):
            self.lav.nota("flusso", tipo="chiamata", testo=grezzo[i:i + 7])
        self.atteso += testo
        self.lav.nota("strumento", nome="scrivi_file", argomenti={"percorso": percorso,
                                                                  "contenuto": testo})
        self.lav.nota("file", nome=percorso, testo=testo)
        self.lav.nota("esito", nome="scrivi_file", esito={"ok": True})

    def test(self, eseguiti, falliti):
        self.lav.nota("strumento", nome="esegui_test", argomenti={})
        e = {"eseguiti": eseguiti, "falliti": falliti, "errori": 0}
        self.lav.nota("test", esito=e)
        self.lav.nota("esito", nome="esegui_test", esito={"esito": e, "passano": not falliti})

    def chiudi(self):
        self.av.chiudi()




def testo_pagina(p, radice):
    return p.valuta(f"(() => {{ const r = document.querySelector({json.dumps(radice)}); if (!r) return null;"
                    " return [...r.querySelectorAll('.flusso-chat .fl-x')].map(e => e.textContent).join(''); })()")


def pc(exe, srv, hub, web, svs, lavori):
    arch = hub.archivio
    _, t_dario = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, t_bianca = arch.crea_con_token("camera", proprietario="bianca", proprietario_nome="Bianca")
    hub._rinfresca()
    base = f"http://127.0.0.1:{web.port}/"
    p = PTP.Pagina(exe, base + f"#t={t_dario}", profilo="profilo-svil-pc",
                   opzioni=("--window-size=1280,800",))
    q = PTP.Pagina(exe, base + f"#t={t_bianca}", profilo="profilo-svil-bianca",
                   opzioni=("--window-size=1280,800",))
    agenti = []
    try:
        for x in (p, q):
            aspetta(lambda x=x: x.valuta("document.getElementById('stato').className.includes('ok')"), 15)
        finestra(p, 1280, 800)
        # ── apertura: la vista ──
        sv = svs.apri("dario", "Dario", "estensione", "Crea un'estensione che dica il meteo di una "
                                                      "città", "meteo città")
        ok = aspetta(lambda: p.valuta("document.body.classList.contains('in-vista-sviluppo') && "
                                      "document.querySelector('#principale .vista-svil .fase.adesso .fase-nome')"
                                      ".textContent"), 8)
        verifica("sviluppo aperto: lo schermo di chi sviluppa entra nella vista, fase «analisi»",
                 ok == "analisi", ok)
        time.sleep(0.5)
        verifica("lo schermo di un'altra persona non cambia",
                 q.valuta("!document.body.classList.contains('in-vista-sviluppo') && "
                          "!document.querySelector('.scheda-sviluppo')"))
        foto(p, "vista-analisi-1280x800.png")
        # ── il lavoro parte: due colonne, flusso che si accumula ──
        a = Agente(svs, hub, "L1")
        agenti.append(a)
        lavori.lavori.append(a.lav)
        svs.avviato(a.lav)
        a.passata()
        a.scrive("pensiero", "Guardo cosa serve: una funzione che cerca le coordinate e poi il "
                             "meteo. Comincio dal manifesto. ")
        a.scrive("testo", "Scrivo prima il manifesto e poi il codice, con i test. ")
        ok = aspetta(lambda: (testo_pagina(p, "#principale") or "") == a.atteso, 8)
        verifica("il flusso compare nella colonna di destra", bool(ok), testo_pagina(p, "#principale"))
        col = p.valuta("(() => { const g = document.querySelector('#principale .vista-svil .due-colonne');"
                       " return g && [getComputedStyle(g).gridTemplateColumns.split(' ').length,"
                       " !!g.querySelector('.col-riepilogo .tetti-lavoro'),"
                       " !!g.querySelector('.col-flusso .flusso-chat')]; })()")
        verifica("due colonne: a sinistra il riepilogo con i tetti, a destra il flusso",
                 col == [2, True, True], col)
        p.valuta("window.__primo = document.querySelector('#principale .flusso-chat .fl-x'); 1")
        a.codice("estensione.py", "def esegui(dati, calliope):\n    citta = dati.get(\"citta\")\n"
                                  "    return {\"da_dire\": \"A \" + citta + \" c'è il sole.\"}\n")
        a.test(3, 1)
        a.passata()
        a.scrive("testo", "Un test non passa: correggo la ricerca della città. ")
        ok = aspetta(lambda: (testo_pagina(p, "#principale") or "") == a.atteso, 8)
        verifica("si accumula: tutto il testo, nell'ordine, senza doppioni", bool(ok),
                 (testo_pagina(p, "#principale") or "")[-160:])
        verifica("…e gli elementi di prima restano gli stessi (niente riscrittura da zero)",
                 p.valuta("window.__primo === document.querySelector('#principale .flusso-chat .fl-x')"))
        sez = p.valuta("[...document.querySelectorAll('#principale .flusso-chat > *')].map(e => e.className)")
        verifica("sezioni per tipo: ragionamento, testo, codice, chiamata, esito, separatore",
                 all(any(k in c for c in sez) for k in ("fl-passata", "fl-pensiero", "fl-testo",
                                                         "fl-codice", "fl-strumento", "fl-esito")),
                 str(sez))
        esiti = p.valuta("[...document.querySelectorAll('#principale .fl-esito')].map(e => e.textContent)")
        verifica("l'esito in breve dei test", any("2 test su 3 passano" in e for e in esiti or []),
                 str(esiti))
        foto(p, "vista-sviluppo-1280x800.png")
        # ── scorrimento ──
        a.scrive("testo", "Riga di prova per lo scorrimento. " * 40)
        aspetta(lambda: (testo_pagina(p, "#principale") or "") == a.atteso, 8)
        p.valuta("(() => { const c = document.querySelector('#principale .flusso-chat'); c.scrollTop = 0;"
                 " c.dispatchEvent(new Event('scroll')); })()")
        time.sleep(0.2)
        a.scrive("testo", "Altro testo mentre si legge sopra. " * 10)
        aspetta(lambda: (testo_pagina(p, "#principale") or "") == a.atteso, 8)
        st = p.valuta("(() => { const c = document.querySelector('#principale .flusso-chat');"
                      " const f = c.querySelector('.fl-fondo'); return [c.scrollTop,"
                      " c.classList.contains('staccato'), getComputedStyle(f).display]; })()")
        verifica("chi torna indietro a leggere resta lì, e compare «In fondo»",
                 st and st[0] < 5 and st[1] is True and st[2] != "none", st)
        foto(p, "flusso-in-fondo-1280x800.png")
        dov = p.valuta("(() => { const f = document.querySelector('#principale .fl-fondo');"
                       " const b = f.getBoundingClientRect(); const e = document.elementFromPoint(b.x + b.width / 2,"
                       " b.y + b.height / 2); return [b.x, b.y, b.width, b.height, e && e.className]; })()")
        clic(p, "#principale .fl-fondo")
        time.sleep(0.2)
        print("   «In fondo» toccato a", dov, p.valuta("(() => { const c = document.querySelector("
              "'#principale .flusso-chat'); return [c.scrollHeight - c.scrollTop - c.clientHeight,"
              " c.classList.contains('staccato')]; })()"))
        a.scrive("testo", "Di nuovo in fondo: lo scorrimento riprende. " * 5)
        aspetta(lambda: (testo_pagina(p, "#principale") or "") == a.atteso, 8)
        time.sleep(0.3)
        st = p.valuta("(() => { const c = document.querySelector('#principale .flusso-chat');"
                      " return [c.scrollHeight - c.scrollTop - c.clientHeight, c.classList.contains('staccato')]; })()")
        verifica("«In fondo»: lo scorrimento riprende a seguire la coda",
                 st and st[0] < 24 and st[1] is False, st)
        # ── riconnessione: pezzi arrivati mentre la pagina era giù ──
        hub.chiudi_tutte()
        time.sleep(0.15)
        a.scrive("testo", "Scritto mentre lo schermo era scollegato. ")
        a.codice("test_estensione.py", "def test_bergamo():\n    assert True\n")
        ok = aspetta(lambda: p.valuta("document.getElementById('stato').className.includes('ok')")
                     and (testo_pagina(p, "#principale") or "") == a.atteso, 15)
        verifica("riconnessione: ripresa senza buchi né doppioni", bool(ok),
                 (testo_pagina(p, "#principale") or "")[-120:])
        # ── correzione e giro 2 ──
        sv.correzioni += 1
        a.lav.correzione = True
        for v in sv.lavori:
            v["correzione"] = 1
        a.lav.giro, a.lav.passi0 = 2, a.lav.passi
        a.scrive("testo", "Secondo giro. ")
        ok = aspetta(lambda: "60 min al massimo" in (p.valuta(
            "document.querySelector('#principale .tetti-lavoro').textContent") or ""), 8)
        rie = p.valuta("document.querySelector('#principale .col-riepilogo').textContent") or ""
        verifica("giro 2: tetti cumulativi (60 minuti, 48 passate) e «giro 2»",
                 bool(ok) and "di 48 al massimo" in rie and "giro 2" in rie, rie[:300])
        verifica("«correzione 1, riparte dalla versione provata» e lo sviluppo intero",
                 "Correzione 1, riparte dalla versione provata" in rie and "Sviluppo intero" in rie,
                 rie[:400])
        # ── vista normale, schermo intero, torna allo sviluppo ──
        clic(p, "#principale [data-svil-esci]")
        ok = aspetta(lambda: p.valuta("!document.body.classList.contains('in-vista-sviluppo') && "
                                      "!!document.querySelector('#principale .tipo-lavoro')"), 5)
        verifica("«Vista normale»: la scheda del lavoro", bool(ok))
        verifica("nella scheda normale il codice non si vede",
                 p.valuta("!document.querySelector('#principale .flusso-chat') && "
                          "!document.querySelector('#principale pre.anteprima')"))
        verifica("«Torna allo sviluppo» nella testa", p.valuta("!document.getElementById('torna-svil').hidden"))
        clic(p, "#principale [data-intero]")
        ok = aspetta(lambda: p.valuta("!document.getElementById('strato-intero').hidden && "
                                      "!!document.querySelector('#intero-posto .due-colonne .flusso-chat')"), 5)
        verifica("«Schermo intero» del lavoro: lo strato con le due colonne e il flusso", bool(ok))
        ok = aspetta(lambda: (testo_pagina(p, "#intero-posto") or "") == a.atteso, 5)
        verifica("…con tutto il flusso accumulato", bool(ok))
        a.scrive("testo", "Aggiornato a schermo intero. ")
        ok = aspetta(lambda: (testo_pagina(p, "#intero-posto") or "") == a.atteso, 8)
        verifica("lo schermo intero si aggiorna al suo posto", bool(ok))
        foto(p, "lavoro-schermo-intero-1280x800.png")
        finestra(p, 1920, 1080)
        foto(p, "lavoro-schermo-intero-1920x1080.png")
        finestra(p, 1280, 800)
        PSI.tasto(p, "Escape", "Escape", 27)
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-intero').hidden"), 3)
        verifica("Esc chiude lo schermo intero", bool(ok))
        clic(p, "#torna-svil")
        ok = aspetta(lambda: p.valuta("document.body.classList.contains('in-vista-sviluppo')"), 3)
        verifica("«Torna allo sviluppo»: di nuovo nella vista", bool(ok))
        # ── collaudo, domande, comandi ──
        a.lav.stato, a.lav.fine = "fatto", time.time()
        a.av.finale(a.lav)
        svs.lavoro_finito(a.lav, {"messaggio": "fatto"})
        sv.versione, sv.estensione = 2, "meteo_citta"
        svs.collaudo(sv, "Bergamo", True, "A Bergamo c'è il sole.")
        svs.collaudo(sv, "Valfiorita Maggiore", False, "Impossibile cercare la città")
        svs.chiesto(sv, "Perché Valfiorita Maggiore non va?", {
            "voce": "Il geocoder non trova i nomi di due parole.",
            "dettagli": "La ricerca usa solo la prima parola.", "serve_correzione": True})
        ok = aspetta(lambda: p.valuta("document.querySelectorAll('#principale .prove-svil li').length") == 2
                     and p.valuta("document.querySelector('#principale .fase.adesso .fase-nome').textContent") == "collaudo", 8)
        verifica("collaudo: lo storico delle prove (dati, esito, versione) e la fase", bool(ok))
        verifica("le domande a chi l'ha scritto, con i dettagli",
                 "Il geocoder non trova" in (p.valuta("document.querySelector('#principale .domanda-svil').textContent") or ""))
        tit = p.valuta("document.querySelector('#principale .svil-titolo').textContent") or ""
        verifica("nome dell'estensione e versione nella testa della vista",
                 "meteo_citta" in tit and "versione 2" in tit, tit)
        tasti = p.valuta("[...document.querySelectorAll('#principale .comandi-svil button')].map(b => [b.textContent, b.disabled])")
        verifica("comandi senza conversazione: spenti (tranne «Vista normale»), nessuno per approvare",
                 tasti and all(d for t, d in tasti if t != "Vista normale")
                 and not any("pprov" in t or "ttiv" in t for t, _ in tasti), str(tasti))
        foto(p, "vista-collaudo-1280x800.png")
        finestra(p, 1920, 1080)
        foto(p, "vista-collaudo-1920x1080.png")
        finestra(p, 1280, 800)
        hub.conversazioni.voce("dario", "voce")
        ok = aspetta(lambda: p.valuta("[...document.querySelectorAll('#principale [data-svil-invia]')].every(b => !b.disabled)"), 5)
        verifica("con la conversazione aperta i comandi si accendono", bool(ok))
        while hub.ingresso.prendi() is not None:
            pass
        clic(p, "#principale [data-svil-invia]")
        arr = aspetta(lambda: hub.ingresso.prendi(), 5)
        verifica("«A che punto siamo?» manda la frase come scritta",
                 bool(arr) and "A che punto è lo sviluppo?" in json.dumps(arr, ensure_ascii=False),
                 json.dumps(arr, ensure_ascii=False)[:200])
        clic(p, "#principale [data-svil-scrivi='Prova con ']")
        val = aspetta(lambda: p.valuta("document.getElementById('scrivi-testo').value"), 3)
        verifica("«Prova con…»: la frase da finire nella casella dello scritto", val == "Prova con ", val)
        # ── chiusura ──
        svs.chiudi(sv, "uscita")
        ok = aspetta(lambda: p.valuta("!document.body.classList.contains('in-vista-sviluppo') && "
                                      "(document.querySelector('#principale .svil-chiuso') || {}).textContent"), 5)
        verifica("sviluppo chiuso: lo schermo esce dalla vista", bool(ok), ok)
        verifica("…e «Torna allo sviluppo» sparisce", p.valuta("document.getElementById('torna-svil').hidden"))
        # Lo schema chiaro del sistema: la pagina resta scura (ha un tema solo), leggibile
        p._chiama("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": "light"}]})
        foto(p, "chiusa-chiaro-1280x800.png")
        p._chiama("Emulation.setEmulatedMedia", {"features": []})
        for x, chi in ((p, "computer"), (q, "altro schermo")):
            x.pompa(0.3)
            errori = [r for r in x.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica(f"{chi}: nessun errore JavaScript né violazione della CSP", not errori,
                     "; ".join(errori)[:300])
    finally:
        for a in agenti:
            a.chiudi()
        p.chiudi()
        q.chiudi()


def telefono(exe, srv, hub, web, svs, lavori):
    _, token = srv.archivio.crea_con_token("telefono-dario", proprietario="dario", proprietario_nome="Dario")
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-svil-tel",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    agenti = []
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        PSI.dimensione(p, 375, 812)
        ok = aspetta(lambda: p.valuta(f"!!window.calliopeTelefono && {T}.st.collegato"), 15)
        verifica("telefono di chi sviluppa: collegato", bool(ok))
        aspetta(lambda: p.valuta("!!window.calliopeSchermo && document.getElementById('stato').className.includes('ok')"), 10)
        hub._rinfresca()
        sv = svs.apri("dario", "Dario", "estensione", "Un'estensione per le maree", "maree")
        k = f"sviluppo:{sv.id}"
        ok = aspetta(lambda: p.valuta(f"{T}.carosello().intera") == k, 8)
        verifica("sviluppo aperto: il telefono apre la vista a schermo intero da solo", bool(ok),
                 p.valuta(f"{T}.carosello()"))
        a = Agente(svs, hub, "L2")
        agenti.append(a)
        lavori.lavori.append(a.lav)
        svs.avviato(a.lav)
        a.passata()
        a.scrive("pensiero", "Cerco le tabelle delle maree e scrivo il codice. ")
        a.codice("estensione.py", "def esegui(dati, calliope):\n" + "".join(
            f"    riga_{i} = 'un codice piuttosto lungo che esce dalla larghezza del telefono {i}'\n"
            for i in range(12)))
        ok = aspetta(lambda: (testo_pagina(p, "#intera-posto") or "") == a.atteso, 10)
        verifica("telefono: il flusso nella vista, accumulato", bool(ok),
                 (testo_pagina(p, "#intera-posto") or "")[-100:])
        col = p.valuta("(() => { const g = document.querySelector('#intera-posto .due-colonne');"
                       " return g && getComputedStyle(g).gridTemplateColumns.split(' ').length; })()")
        verifica("telefono: una colonna sola", col == 1, col)
        for w, h, nome in PSI.DIMENSIONI:
            PSI.dimensione(p, w, h)
            PSI.misura_strato(p, "vista dello sviluppo", f"{w}×{h}")
            foto(p, f"telefono-vista-{nome}-{w}x{h}.png")
        PSI.dimensione(p, 375, 812)
        st = p.valuta("(() => { const c = document.querySelector('#intera-posto .flusso-chat');"
                      " return [c.scrollHeight - c.scrollTop - c.clientHeight, c.classList.contains('staccato')]; })()")
        verifica("telefono girato e rimesso dritto: il flusso resta in fondo", st and st[0] < 24
                 and st[1] is False, st)
        p.valuta("document.getElementById('intera-posto').scrollTop = 10000; 1")
        foto(p, "telefono-vista-sotto-375x812.png")
        PSI.tocca(p, "#intera-chiudi")
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
        car = p.valuta(f"{T}.carosello()") or {}
        verifica("«Chiudi»: torna il carosello, con la scheda dello sviluppo e quella del lavoro",
                 bool(ok) and k in car.get("ordine", []) and "lavoro:L2" in car.get("ordine", []),
                 json.dumps(car))
        verifica("nel carosello il codice non si vede",
                 p.valuta("!document.querySelector('#binario .flusso-chat')"))
        p.valuta(f"{T}.vaiA('lavoro:L2'); 1")
        time.sleep(0.2)
        PSI.tocca(p, "#binario [data-chiave=\"lavoro:L2\"] h1.titolo")
        ok = aspetta(lambda: p.valuta(f"{T}.carosello().intera") == "lavoro:L2"
                     and (testo_pagina(p, "#intera-posto") or "") == a.atteso, 5)
        verifica("telefono: il lavoro a schermo intero, con il flusso", bool(ok))
        PSI.misura_strato(p, "lavoro con il flusso", "375×812")
        foto(p, "telefono-lavoro-intero-375x812.png")
        PSI.tocca(p, "#intera-chiudi")
        aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
        p.valuta(f"{T}.vaiA({json.dumps(k)}); 1")
        time.sleep(0.2)
        PSI.tocca(p, f"#binario [data-chiave=\"{k}\"] .svil-titolo")
        ok = aspetta(lambda: p.valuta(f"{T}.carosello().intera") == k, 3)
        verifica("un tocco sulla scheda dello sviluppo riapre la vista", bool(ok))
        svs.chiudi(sv, "uscita")
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 5)
        verifica("sviluppo chiuso: lo strato si chiude", bool(ok))
        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori,
                 "; ".join(errori)[:300])
    finally:
        for a in agenti:
            a.chiudi()
        p.chiudi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    exe = PTP.browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    for m in (PTP, PC, PCP):
        shutil.rmtree(m.TMP, ignore_errors=True)
    PTP.TMP = TMP
    PCP.TMP = TMP
    from calliope.sviluppo import Sviluppi
    try:
        cfg, srv, hub, web = PCP.avvia()
        lavori = SimpleNamespace(lavori=[])
        svs = Sviluppi(cfg, TMP, lavori=lavori, log=lambda m: None)
        svs.schermi = hub
        try:
            pc(exe, srv, hub, web, svs, lavori)
            telefono(exe, srv, hub, web, svs, lavori)
        finally:
            web.ferma()
            srv.ferma()
            hub.archivio.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
