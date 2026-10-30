import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Lo Studio nella pagina vera del telefono (29/10, passo 4.2, issue #281, epic #251;
schermi/pagina/studio.js e bordi.js, POST /api/studio/pagina).

Nel browser vero (Edge o Chromium senza finestra, DevTools; senza si salta), server degli schermi
e dei satelliti veri su 127.0.0.1, telefono abbinato di una persona di fantasia (Dario, adulto),
`studio_modo: attivo`, fotocamera finta del browser:
- Le mie cose › Studio: la tessera apre la pagina dello Studio (niente schede del server), con la
  verifica da scegliere;
- «scatto finto con un file di prova»: dalla «Galleria o PDF» una foto storta di fantasia
  (studio_immagini.py, in una cartella temporanea), una in ombra e un PDF di due pagine; i bordi
  trovati da bordi.js sulle foto (miniatura col quadrilatero), il PDF come file;
- la fotocamera finta: «Fotocamera», due «Scatta» (pagine senza bordi, con l'avviso), «Fatto»;
- ordine: «↓» e «↑» spostano, «Togli» toglie, «Rifai» su una foto della galleria la sostituisce
  con un'altra;
- misure a 390×844 e a 320×693 (iPhone 13 mini con lo «Zoom schermo»): niente di lato, tocchi
  ≥ 44 px, testo ≥ 16 px, il mirino dentro lo schermo;
- «Manda»: le pagine arrivano al server nell'ordine scelto (le foto in un materiale, il PDF diviso
  in un altro), nello stato «da leggere», e l'elenco si svuota;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot (390×844 e 320×693). ~20 s.

    python prove/prova_studio_pagina_telefono.py
"""

import base64
import datetime
import io
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-tel-"))
ERRORI = []
SALTATA = 77
QUI = Path(__file__).resolve().parent


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


def aspetta(cond, max_s=8.0, passo=0.05):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None, tutori=()):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, None


class Registro:
    def __init__(self, *p):
        self.users = {x.name: x for x in p}

    def by_id(self, pid):
        return next((x for x in self.users.values() if x.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


DARIO = Prof("dario", "Dario")
REG = Registro(DARIO)


class Servizi:
    studio = None


def immagini() -> dict:
    sys.path.insert(0, str(QUI / "manuali"))
    import studio_immagini as SI
    SI.genera(TMP / "img", varianti=("storta", "ombra", "pulita"), solo=["storia"], log=lambda m: None)
    from PIL import Image
    pag = [Image.open(TMP / "img" / "storia" / f"{p}-pulita.jpg").convert("RGB").resize((595, 842))
           for p in ("p116", "p117")]
    pdf = TMP / "capitolo.pdf"
    pag[0].save(pdf, "PDF", save_all=True, append_images=pag[1:], resolution=72)
    return {"storta": TMP / "img" / "storia" / "p112-storta.jpg",
            "ombra": TMP / "img" / "storia" / "p113-ombra.jpg",
            "altra": TMP / "img" / "storia" / "p114-storta.jpg", "pdf": pdf}


class T:
    def __init__(self, pagina):
        self.p = pagina

    def v(self, js):
        return self.p.valuta(js)

    def tocca(self, sel):
        r = self.v(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null;"
                   f" e.scrollIntoView({{block: 'nearest'}}); const b = e.getBoundingClientRect();"
                   f" return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
        if not r:
            return False
        for t in ("mousePressed", "mouseReleased"):
            self.p._chiama("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1],
                                                         "button": "left", "clickCount": 1})
        return True

    def file(self, percorsi):
        doc = self.p._chiama("DOM.getDocument", {"depth": 1})["result"]["root"]["nodeId"]
        n = self.p._chiama("DOM.querySelector", {"nodeId": doc, "selector": "#studio-file"})["result"]["nodeId"]
        self.p._chiama("DOM.setFileInputFiles", {"nodeId": n, "files": [str(p) for p in percorsi]})

    def stato(self):
        return self.v("window.CalliopeStudio.stato()") or {}

    def ordine(self):
        return [p["id"] for p in self.stato().get("pagine", [])]


def dimensione(t, w, h):
    t.p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2,
                                                       "mobile": True})
    aspetta(lambda: t.v(f"innerWidth === {w} && innerHeight === {h}"), 5)
    t.v("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")


MISURA = r"""(() => {
  const s = document.getElementById('studio');
  const vis = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const fuori = [];
  for (const e of s.querySelectorAll('*')) {
    if (!vis(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.right > innerWidth + 0.5 || r.left < -0.5) fuori.push((e.id || e.className || e.tagName) + ':' + Math.round(r.left) + '-' + Math.round(r.right));
  }
  const tocchi = [...s.querySelectorAll('button, select')].filter(vis)
    .map((b) => { const r = b.getBoundingClientRect(); return [b.id || b.dataset.azione || b.className, Math.round(r.width), Math.round(r.height)]; })
    .filter(([, w, h]) => w < 44 || h < 44);
  const piccoli = [...s.querySelectorAll('b, span, p, button, label, select, h3')].filter(vis)
    .filter((e) => e.childNodes.length && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()))
    .map((e) => [e.id || e.className || e.tagName, parseFloat(getComputedStyle(e).fontSize)])
    .filter(([, f]) => f < 16);
  return {fuori: fuori.slice(0, 6), tocchi: tocchi.slice(0, 6), piccoli: piccoli.slice(0, 6),
          lato: document.scrollingElement.scrollWidth > innerWidth + 1,
          mirino: (() => { const v = document.getElementById('studio-video'); if (!vis(v)) return null;
                           const r = v.getBoundingClientRect(); return r.bottom <= innerHeight + 1 && r.right <= innerWidth + 1; })()};
})()"""


def foto(t, nome):
    cartella = os.environ.get("CALLIOPE_FOTO")
    if not cartella:
        return
    r = t.p._chiama("Page.captureScreenshot", {"format": "png"})
    Path(cartella).mkdir(parents=True, exist_ok=True)
    (Path(cartella) / nome).write_bytes(base64.b64decode(r["result"]["data"]))


def misure(t, etichetta):
    m = t.v(MISURA) or {}
    verifica(f"{etichetta}: niente fuori dallo schermo né di lato", not m.get("fuori") and not m.get("lato"),
             json.dumps(m.get("fuori")))
    verifica(f"{etichetta}: tocchi ≥ 44 px", not m.get("tocchi"), json.dumps(m.get("tocchi")))
    verifica(f"{etichetta}: testo ≥ 16 px", not m.get("piccoli"), json.dumps(m.get("piccoli")))
    return m


def scenario(t, hub, st, vid, file):
    T_ = "window.calliopeTelefono"
    ok = aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)
    verifica("pagina caricata e collegata", bool(ok))
    if not ok:
        return
    t.v("location.hash = '#/cose'; 1")
    ok = aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    verifica("Le mie cose: la tessera Studio apre una pagina (Studio attivo)", bool(ok))
    t.tocca('#tessere [data-tessera="studio"]')
    # Dal passo 4.5 (#284) la tessera apre la home: le pagine sono la vista «Pagine» della verifica
    ok = aspetta(lambda: t.v(f"!!document.querySelector('#studio-home [data-pagine=\"{vid}\"]')"), 8)
    verifica("Studio: la tessera apre la home, con «Pagine» sulla verifica", bool(ok))
    t.tocca(f'#studio-home [data-pagine="{vid}"]')
    ok = aspetta(lambda: t.v("!document.getElementById('studio-materiali').hidden && "
                             "document.getElementById('studio-verifica').options.length === 1"), 8)
    verifica("Studio: la pagina si apre, con la verifica da scegliere e senza schede del server",
             bool(ok) and t.v("document.getElementById('pagina-schede').hidden && location.hash === '#/cose/studio'"),
             t.v("location.hash"))
    verifica("Studio: il riquadro della pagina tiene i suoi pezzi (esito e ricerca delle altre pagine)",
             t.v("!!document.getElementById('pagina-esito') && !!document.getElementById('pagina-cerca')"
                 " && document.getElementById('pagina-cerca').hidden"))
    verifica("Studio: la verifica dice materia e data",
             "Storia" in (t.v("document.getElementById('studio-verifica').options[0].textContent") or ""))

    # Dalla galleria: due foto e un PDF
    t.file([file["storta"], file["ombra"], file["pdf"]])
    ok = aspetta(lambda: len(t.stato().get("pagine", [])) == 3, 15)
    s = t.stato()
    tipi = [p["tipo"] for p in s.get("pagine", [])]
    verifica("galleria: due foto e un PDF nell'elenco, nell'ordine scelto", ok and tipi == ["foto", "foto", "pdf"], tipi)
    verifica("galleria: i bordi trovati da bordi.js sulla foto storta e su quella in ombra",
             ok and all(p["angoli"] for p in s["pagine"][:2]), json.dumps(s.get("pagine"))[:300])
    verifica("galleria: la miniatura col quadrilatero (canvas) e il PDF col suo segno",
             t.v("document.querySelectorAll('#studio-elenco canvas.studio-mini').length === 2 && "
                 "!!document.querySelector('#studio-elenco .studio-pdf')"))

    # La fotocamera finta: due scatti
    t.tocca("#studio-camera-apri")
    ok = aspetta(lambda: t.v("(() => { const v = document.getElementById('studio-video');"
                             " return !document.getElementById('studio-camera').hidden && v.videoWidth > 0; })()"), 10)
    verifica("fotocamera: si apre col mirino (fotocamera finta del browser)", bool(ok))
    dimensione(t, 390, 844)
    if ok:
        time.sleep(0.6)
        misure(t, "390×844 col mirino")
        t.tocca("#studio-scatta")
        aspetta(lambda: len(t.stato().get("pagine", [])) == 4, 8)
        t.tocca("#studio-scatta")
        aspetta(lambda: len(t.stato().get("pagine", [])) == 5, 8)
        t.tocca("#studio-camera-fine")
    s = t.stato()
    verifica("fotocamera: due scatti, due pagine in fondo; «Fatto» chiude e spegne la fotocamera",
             len(s.get("pagine", [])) == 5 and not s.get("camera")
             and t.v("document.getElementById('studio-camera').hidden"), json.dumps(s)[:200])
    verifica("fotocamera: lo scatto finto (senza pagina) ha l'avviso dei bordi",
             all("bordi" in p["avvisi"] for p in s["pagine"][3:]), json.dumps(s.get("pagine", [])[3:]))

    # Ordine, togli, rifai
    prima = t.ordine()
    t.tocca(f'#studio-elenco button[data-pagina="{prima[0]}"][data-azione="giu"]')
    dopo = t.ordine()
    verifica("ordine: «↓» sposta la prima pagina al secondo posto", dopo == [prima[1], prima[0]] + prima[2:], dopo)
    t.tocca(f'#studio-elenco button[data-pagina="{prima[4]}"][data-azione="su"]')
    dopo2 = t.ordine()
    verifica("ordine: «↑» sposta l'ultima pagina su di uno", dopo2 == dopo[:3] + [prima[4], prima[3]], dopo2)
    verifica("ordine: «↑» della prima e «↓» dell'ultima spenti",
             t.v(f"document.querySelector('#studio-elenco li:first-child button[data-azione=\"su\"]').disabled && "
                 f"document.querySelector('#studio-elenco li:last-child button[data-azione=\"giu\"]').disabled"))
    t.tocca(f'#studio-elenco button[data-pagina="{prima[3]}"][data-azione="togli"]')
    verifica("togli: la pagina esce dall'elenco", prima[3] not in t.ordine() and len(t.ordine()) == 4, t.ordine())
    # Rifai la foto in ombra (dalla galleria): il selettore dei file intercettato, poi un'altra foto
    t.p._chiama("Page.setInterceptFileChooserDialog", {"enabled": True})
    pos = t.ordine().index(prima[1])
    t.tocca(f'#studio-elenco button[data-pagina="{prima[1]}"][data-azione="rifai"]')
    t.file([file["altra"]])
    ok = aspetta(lambda: prima[1] not in t.ordine() and len(t.ordine()) == 4, 10)
    verifica("rifai: la pagina è sostituita al suo posto, l'elenco resta di 4", bool(ok)
             and t.stato()["pagine"][pos]["tipo"] == "foto" and t.stato()["pagine"][pos]["angoli"], t.ordine())
    t.p._chiama("Page.setInterceptFileChooserDialog", {"enabled": False})

    # Le misure e gli screenshot
    t.v("document.getElementById('pagina-racc').scrollIntoView({block: 'start'}); 1")
    misure(t, "390×844")
    foto(t, "studio-390x844.png")
    dimensione(t, 320, 693)
    misure(t, "320×693")
    foto(t, "studio-320x693.png")

    # Manda: nell'ordine scelto
    attese = [p["tipo"] for p in t.stato()["pagine"]]
    t.tocca("#studio-invia")
    ok = aspetta(lambda: not t.stato().get("pagine") and not t.stato().get("invio"), 30)
    esito = t.v("document.getElementById('studio-esito').textContent") or ""
    verifica("manda: l'elenco si svuota e la pagina lo dice", bool(ok) and "Mandate" in esito, esito)
    righe = st.dati.tutti("SELECT p.*, m.origine FROM studio_pagine p JOIN studio_materiali m ON "
                          "m.id = p.materiale WHERE m.verifica = ? ORDER BY p.ordine", (vid,))
    da_server = []
    for r in righe:
        if r["origine"] == "file":
            if not da_server or da_server[-1] != "pdf":
                da_server.append("pdf")
        else:
            da_server.append("foto")
    verifica("manda: le pagine al server nell'ordine scelto (il PDF diviso in due), tutte «da_leggere»",
             da_server == attese and len(righe) == len(attese) + 1
             and all(r["stato"] == "da_leggere" for r in righe), f"{attese} {da_server}")
    mats = {r["materiale"] for r in righe if r["origine"] == "foto"}
    verifica("manda: le foto di un giro nello stesso materiale", len(mats) == 1, mats)
    verifica("manda: niente nella conversazione", hub.ingresso.vuoto())
    conto = t.v("document.getElementById('studio-verifica').options[0].textContent") or ""
    verifica("manda: la verifica dice le pagine nuove", f"{len(righe)} pag." in conto, conto)
    # Indietro: la pagina dello Studio si chiude
    t.tocca("#pagina-indietro")
    ok = aspetta(lambda: t.v("document.getElementById('studio').hidden && !window.CalliopeStudio.stato().aperta"), 5)
    verifica("indietro: lo Studio si chiude e torna alle tessere", bool(ok))


def main() -> int:
    import prova_telefono_pagina as PTP
    import prova_telefono_schermo as PTS
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        exe = PTP.browser()
        if exe is None:
            print("Nessun Edge né Chromium: prova saltata.")
            return SALTATA
        file = immagini()
        cfg, srv, hub, web = PTS.avvia(TMP / "server")
        from calliope import minori
        from calliope import studio as S
        cfg.studio_modo = "attivo"
        cfg.studio_cartella = "studio"
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        serv = Servizi()
        serv.studio = st
        hub.servizi = serv
        hub.profilo = REG.by_id
        vid = st.crea_verifica(DARIO, "Storia", datetime.date.today() + datetime.timedelta(days=7),
                               argomento="Le scoperte geografiche")
        _, token = srv.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        url = f"http://127.0.0.1:{web.port}/telefono/"
        pagina = PTP.Pagina(exe, url, profilo="profilo-studio",
                            opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                     "--window-size=390,844"))
        t = T(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            dimensione(t, 390, 844)
            scenario(t, hub, st, vid, file)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica("nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
            web.ferma()
            srv.ferma()
            st.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
