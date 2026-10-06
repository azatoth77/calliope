import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Le foto nella pagina vera degli schermi (05/10/2026; Edge o Chromium senza finestra, come
prova_scritto_pagina.py). Su uno schermo personale abbinato:

- il pulsante «Foto» c'è; un file scelto con l'input (accept image/*) diventa un'anteprima e,
  con la domanda scritta, arriva al server come JPEG ripulito con il testo;
- incollata con Ctrl+V (evento paste con un'immagine negli appunti) e trascinata sulla
  pagina (drop): stessa strada; da sola, senza testo, arriva come foto in attesa;
- una foto grande (3000×2000) si riduce già nella pagina (lato 1600) prima dell'invio;
- un SVG non parte («non è una foto»); «Togli» toglie l'anteprima;
- la scheda «foto» con la miniatura si disegna (img con data URL, permessa dalla CSP);
- su uno schermo di stanza il pulsante non c'è.
Nessun errore JavaScript. Senza Edge né Chromium la prova si salta.
"""

import shutil
import time

from prova_schermi_pagina import TMP, Pagina, aspetta, browser, porta_libera  # noqa: E402

from calliope.config import Config
from calliope.immagini import Immagine, prepara
from calliope.schermi import ArchivioSchermi, Mittente, Schermi, schede
from calliope.schermi.server import ServerSchermi
from prove import immagini_finte as F

ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


# Un File costruito nella pagina da un canvas (sincrono: niente promesse in Runtime.evaluate)
FILE_JS = """
window.__file = function (w, h, tipo, nome) {
  if (tipo === 'image/svg+xml') {
    return new File(['<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>'], nome, {type: tipo});
  }
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); g.fillStyle = '#c33'; g.fillRect(0, 0, w, h);
  g.fillStyle = '#fff'; g.font = '60px sans-serif'; g.fillText('TOTALE 14,10', 40, h / 2);
  const url = c.toDataURL(tipo); const b = atob(url.split(',')[1]);
  const a = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) a[i] = b.charCodeAt(i);
  return new File([a], nome, {type: tipo});
};
window.__dt = function (f) { const d = new DataTransfer(); d.items.add(f); return d; };
true;
"""


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main() -> int:
    exe = browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    cfg = Config()
    cfg.memory_db = str(TMP / "foto.db")
    cfg.config_dir = str(TMP)
    port = porta_libera()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    srv = ServerSchermi(hub, "127.0.0.1", port).avvia()
    r = hub.archivio.nuova_richiesta()
    hub.archivio.abbina(r["codice"], "studio", "dario-id", "Dario")
    pagina = Pagina(exe, f"http://127.0.0.1:{port}/#t={r['richiesta']}", profilo="foto")
    altra = None
    dario = Mittente(persona="dario-id", nome="Dario", livello="familiare", certo=True)
    try:
        verifica("pagina personale collegata", aspetta(lambda: hub.collegati(), 20) is not None)
        pagina.valuta("window.__errori = []; window.addEventListener('error', "
                      "(e) => window.__errori.push(String(e.message)))")
        pagina.valuta(FILE_JS)
        verifica("pulsante «Allega» visibile sullo schermo personale", aspetta(lambda: pagina.valuta(
            "!!document.getElementById('scrivi-foto') && !document.getElementById('scrivi-foto').hidden"
            " && document.getElementById('scrivi-foto').textContent === 'Allega'"),
            5) is not None)
        verifica("input senza «accept» (foto o qualsiasi file, 05/10)", pagina.valuta(
            "document.getElementById('scrivi-foto-file').accept") == "")
        # Senza conversazione a voce (05/10): «Foto» spento, una foto incollata non entra
        verifica("senza conversazione: «Foto» spento", aspetta(lambda: pagina.valuta(
            "document.getElementById('scrivi-foto').disabled"), 5) is not None)
        pagina.valuta("(() => { const i = document.getElementById('scrivi-foto-file');"
                      " i.files = __dt(__file(300, 300, 'image/png', 'a.png')).files;"
                      " i.dispatchEvent(new Event('change', {bubbles: true})); })()")
        verifica("senza conversazione: niente anteprima, la frase da dire", aspetta(
            lambda: "Calliope" in (pagina.valuta(
                "document.querySelector('.esito-scrivi').textContent") or ""), 5) is not None
            and pagina.valuta("document.getElementById('scrivi-anteprima').hidden"))
        hub.conversazioni.voce("dario-id", "voce")           # Dario parla a Calliope
        verifica("conversazione: «Foto» si riaccende da solo", aspetta(lambda: not pagina.valuta(
            "document.getElementById('scrivi-foto').disabled"), 5) is not None)

        def anteprima():
            return pagina.valuta("!document.getElementById('scrivi-anteprima').hidden && "
                                 "(document.querySelector('#scrivi-anteprima img').src||'')"
                                 ".startsWith('data:image/jpeg')")

        def manda(testo):
            pagina.valuta(f"document.getElementById('scrivi-testo').value = {testo!r}; "
                          "document.querySelector('#scrivi button[type=submit]').click()")
            t = aspetta(lambda: not hub.ingresso.vuoto(), 8)
            return hub.ingresso.prendi() if t is not None else None

        # 1. Scelta del file con l'input
        pagina.valuta("(() => { const i = document.getElementById('scrivi-foto-file');"
                      " i.files = __dt(__file(3000, 2000, 'image/png', 'scontrino.png')).files;"
                      " i.dispatchEvent(new Event('change', {bubbles: true})); })()")
        verifica("file scelto: anteprima JPEG", aspetta(anteprima, 5) is not None)
        item = manda("Cosa c'è qui?")
        img = item and item.get("immagine")
        verifica("inviata con la domanda: al server foto e testo dello schermo personale",
                 item is not None and item["tipo"] == "immagine" and item["testo"] == "Cosa c'è qui?"
                 and item["persona"] == "dario-id" and isinstance(img, Immagine),
                 str({k: v for k, v in (item or {}).items() if k != "immagine"}))
        verifica("ridotta (3000×2000 → lato 1280 sul server, JPEG)",
                 img is not None and img.larghezza == 1280 and abs(img.altezza - 853) <= 1
                 and img.jpeg[:3] == b"\xff\xd8\xff", img and (img.larghezza, img.altezza))
        verifica("fonte: schermo", img is not None and img.fonte == "schermo")
        verifica("dopo l'invio l'anteprima sparisce", aspetta(lambda: pagina.valuta(
            "document.getElementById('scrivi-anteprima').hidden"), 5) is not None)
        time.sleep(0.4)
        # 2. Incolla (Ctrl+V)
        pagina.valuta("document.dispatchEvent(new ClipboardEvent('paste', {clipboardData: "
                      "__dt(__file(800, 600, 'image/png', 'appunti.png')), bubbles: true, "
                      "cancelable: true}))")
        verifica("incollata con Ctrl+V: anteprima", aspetta(anteprima, 5) is not None)
        item = manda("")
        verifica("solo la foto, senza testo: arriva con il testo vuoto (aspetta la domanda)",
                 item is not None and item["tipo"] == "immagine" and item["testo"] == "",
                 str({k: v for k, v in (item or {}).items() if k != "immagine"}))
        verifica("la pagina dice di fare la domanda", "Foto inviata" in (pagina.valuta(
            "document.querySelector('.esito-scrivi').textContent") or ""))
        time.sleep(0.4)
        # 3. Trascina e rilascia
        pagina.valuta("(() => { const d = __dt(__file(640, 480, 'image/jpeg', 'foto.jpg'));"
                      " document.dispatchEvent(new DragEvent('dragover', {dataTransfer: d, "
                      "bubbles: true, cancelable: true}));"
                      " document.dispatchEvent(new DragEvent('drop', {dataTransfer: d, "
                      "bubbles: true, cancelable: true})); })()")
        verifica("trascinata sulla pagina: anteprima", aspetta(anteprima, 5) is not None)
        item = manda("E questa?")
        verifica("trascinata: arriva", item is not None and item["testo"] == "E questa?")
        # 4. Un file qualsiasi (05/10, allegati): anteprima con nome e dimensione, byte nudi
        #    a /api/allegato; un SVG non è una foto (niente canvas): parte come file di testo
        pagina.valuta("(() => { const i = document.getElementById('scrivi-foto-file');"
                      " i.files = __dt(new File(['Bolletta: totale 82,40 euro'], 'bolletta.txt',"
                      " {type: 'text/plain'})).files;"
                      " i.dispatchEvent(new Event('change', {bubbles: true})); })()")
        verifica("file di testo: anteprima con nome e dimensione (niente miniatura)", aspetta(
            lambda: pagina.valuta("!document.getElementById('scrivi-anteprima').hidden && "
                                  "document.querySelector('.allegato-info').textContent")
            == "bolletta.txt · 27 byte", 5) is not None)
        item = manda("Quanto devo pagare?")
        att = item and item.get("allegato")
        verifica("file inviato con la domanda: un Allegato letto dal server",
                 item is not None and item["tipo"] == "allegato" and att.categoria == "testo"
                 and "82,40" in att.testo and att.nome == "bolletta.txt"
                 and item["testo"] == "Quanto devo pagare?" and att.fonte == "schermo",
                 str({k: v for k, v in (item or {}).items() if k != "allegato"}))
        time.sleep(0.4)
        pagina.valuta("(() => { const d = __dt(new File([new Uint8Array([77,90,0,0,1,2,3])],"
                      " 'fattura.pdf', {type: 'application/pdf'}));"
                      " document.dispatchEvent(new DragEvent('drop', {dataTransfer: d, "
                      "bubbles: true, cancelable: true})); })()")
        aspetta(lambda: pagina.valuta("!document.getElementById('scrivi-anteprima').hidden"), 5)
        item = manda("")
        verifica("trascinato un .exe travestito da PDF: arriva come eseguibile, senza byte",
                 item is not None and item["allegato"].categoria == "eseguibile"
                 and item["allegato"].dati is None and item["testo"] == "")
        verifica("la pagina dice «File inviato»", "File inviato" in (pagina.valuta(
            "document.querySelector('.esito-scrivi').textContent") or ""))
        time.sleep(0.4)
        pagina.valuta("(() => { const i = document.getElementById('scrivi-foto-file');"
                      " i.files = __dt(__file(1, 1, 'image/svg+xml', 'x.svg')).files;"
                      " i.dispatchEvent(new Event('change', {bubbles: true})); })()")
        verifica("SVG: non diventa una foto, è un file", aspetta(lambda: pagina.valuta(
            "(document.querySelector('.allegato-info').textContent || '').startsWith('x.svg')"),
            5) is not None)
        pagina.valuta("(() => { const i = document.getElementById('scrivi-foto-file');"
                      " i.files = __dt(__file(300, 300, 'image/png', 'a.png')).files;"
                      " i.dispatchEvent(new Event('change', {bubbles: true})); })()")
        aspetta(anteprima, 5)
        pagina.valuta("document.querySelector('#scrivi-anteprima button').click()")
        verifica("«Togli»: anteprima tolta, niente invio", pagina.valuta(
            "document.getElementById('scrivi-anteprima').hidden") and hub.ingresso.vuoto())
        # Una foto pronta e non mandata, poi la conversazione finisce: si toglie
        pagina.valuta("(() => { const i = document.getElementById('scrivi-foto-file');"
                      " i.files = __dt(__file(300, 300, 'image/png', 'b.png')).files;"
                      " i.dispatchEvent(new Event('change', {bubbles: true})); })()")
        aspetta(anteprima, 5)
        hub.conversazioni.chiudi()
        verifica("conversazione chiusa: anteprima tolta e «Allega» spento", aspetta(
            lambda: pagina.valuta("document.getElementById('scrivi-anteprima').hidden && "
                                  "document.getElementById('scrivi-foto').disabled"), 5)
            is not None and hub.ingresso.vuoto())
        # 5. La scheda con la miniatura
        jpeg, w, h = prepara(F.jpeg(F.foto()), 1280)
        foto = Immagine(jpeg, w, h, fonte="telefono", persona="dario-id")
        foto.n = 1
        hub.invia(schede.foto(foto), dario)
        verifica("scheda «foto»: miniatura disegnata (data URL, CSP)", aspetta(lambda: pagina.valuta(
            "(() => { const i = document.querySelector('.scheda-foto img');"
            " return !!i && i.complete && i.naturalWidth > 100; })()"), 5) is not None)
        from calliope.allegati import prepara as prepara_file
        att = prepara_file("Riga uno\n<img src=x onerror=alert(1)>".encode(), "nota.txt",
                           persona="dario-id")
        att.n = 1
        hub.invia(schede.allegato(att), dario)
        verifica("scheda «allegato»: nome, tipo e anteprima come testo (niente HTML del file)",
                 aspetta(lambda: pagina.valuta(
                     "(() => { const s = document.querySelector('.scheda-allegato');"
                     " return !!s && s.textContent.includes('nota.txt')"
                     " && s.textContent.includes('<img') && !s.querySelector('img'); })()"), 5)
                 is not None)
        err = pagina.valuta("window.__errori") or []
        verifica("nessun errore JavaScript", not err, str(err))
        # 6. Schermo di stanza: niente pulsante
        r2 = hub.archivio.nuova_richiesta()
        hub.archivio.abbina(r2["codice"], "soggiorno", None, None)
        cfg.schermi_scritto_stanza = True
        altra = Pagina(exe, f"http://127.0.0.1:{port}/#t={r2['richiesta']}", profilo="foto2")
        verifica("schermo di stanza: casella sì, «Foto» no", aspetta(lambda: altra.valuta(
            "!!document.getElementById('scrivi') && !document.getElementById('scrivi').hidden"
            " && document.getElementById('scrivi-foto').hidden"), 10) is not None)
    finally:
        pagina.chiudi()
        if altra is not None:
            altra.chiudi()
        srv.ferma()
        hub.archivio.close()
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
