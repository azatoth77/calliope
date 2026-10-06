import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Una scheda a schermo intero sul telefono (06/10/2026: dall'iPhone 13 mini il cruscotto e le
schede lunghe del carosello non si leggevano, e non c'era modo di aprirle più grandi).

Nel browser vero (Edge o Chromium senza finestra, DevTools; senza si salta), server degli
schermi e dei satelliti veri su 127.0.0.1, telefono di chi amministra già abbinato, cruscotto
con il registro dei turni finto (come `prova_cruscotto_pagina`).
- «Espandi» sulle schede lunghe (lavoro con il codice, documento con una tabella larga), non su
  un timer; un tocco sulla scheda o su «Espandi» la apre in uno strato sopra la vista;
- il cruscotto dal menu si apre direttamente a schermo intero (e resta nel carosello);
- nello strato: testo ≥ 16 px, contrasto AA, codice e tabelle che scorrono di lato nel loro
  riquadro e mai la pagina, «Chiudi» in alto e ≥ 64 px, strato alto quanto lo schermo, nessuna
  animazione; a 375×812, 320×568 e 812×375;
- lo strato scorre in verticale; un aggiornamento con la stessa chiave («Aggiorna» del
  cruscotto, il lavoro in diretta) lo ridisegna al suo posto (stesso elemento) senza perdere lo
  scorrimento; una scheda nuova va nel carosello e lo strato resta;
- chiusura con «Chiudi», Esc e il gesto indietro (history.back); il «Chiudi» del cruscotto
  dentro lo strato è nascosto (resta quello dello strato);
- col microfono acceso «Chiudi» è un tocco e poi «Parla» è lì;
- nessun errore JavaScript né violazione della CSP. Con CALLIOPE_FOTO=<cartella> salva gli
  screenshot. ~25 s.
"""

import base64
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_cruscotto as PC
import prova_cruscotto_pagina as PCP
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-scheda-intera-"))
ERRORI = []
SALTATA = 77
DIMENSIONI = [(375, 812, "iphone13mini"), (320, 568, "piccolo"), (812, 375, "orizzontale")]
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
    r = p._chiama("Page.captureScreenshot", {"format": "png"})
    Path(cartella).mkdir(parents=True, exist_ok=True)
    (Path(cartella) / nome).write_bytes(base64.b64decode(r["result"]["data"]))


def dimensione(p, w, h):
    p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2,
                                                     "mobile": True})
    aspetta(lambda: p.valuta(f"innerWidth === {w} && innerHeight === {h}"), 5, 0.05)
    p.valuta("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")


def tocca(p, sel):
    """Un tocco vero (gesto del browser) al centro dell'elemento, senza scorrere la pagina."""
    r = p.valuta(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null;"
                 f" const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
    if not r:
        return False
    for t in ("mousePressed", "mouseReleased"):
        p._chiama("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1], "button": "left",
                                               "clickCount": 1})
    return True


def tasto(p, key, code, vk):
    for t in ("keyDown", "keyUp"):
        p._chiama("Input.dispatchKeyEvent", {"type": t, "key": key, "code": code, "windowsVirtualKeyCode": vk})


# Le misure dello strato: testo ≥ 16 px, niente di lato (salvo dentro un riquadro che scorre di
# lato), contrasto AA, «Chiudi» in alto e ≥ 64 px, strato alto quanto lo schermo, niente animazioni
MISURA = r"""(() => {
  const s = document.getElementById('strato-scheda'), posto = document.getElementById('intera-posto');
  const W = innerWidth, H = innerHeight;
  const vis = (e) => e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
  const nome = (e) => e.id || (typeof e.className === 'string' && e.className) || e.tagName;
  const piccoli = [];
  const w = document.createTreeWalker(s, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    if (!n.textContent.trim() || !vis(n.parentElement)) continue;
    const fs = parseFloat(getComputedStyle(n.parentElement).fontSize);
    if (fs < 15.95) piccoli.push(nome(n.parentElement) + ' ' + fs.toFixed(1));
  }
  const scorreDiLato = (e) => { for (let x = e.parentElement; x && x !== s; x = x.parentElement) {
      const o = getComputedStyle(x).overflowX;
      if ((o === 'auto' || o === 'scroll') && x !== posto) return true; } return false; };
  const fuori = [...s.querySelectorAll('*')].filter(vis).filter((e) => { const r = e.getBoundingClientRect();
    return r.width > 0 && (r.left < -1 || r.right > W + 1) && !scorreDiLato(e); }).map(nome);
  const lum = (c) => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => v / 255)
    .map((v) => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
  const contrasto = (e) => { const cs = getComputedStyle(e);
    let b = e, bg = 'rgba(0, 0, 0, 0)';
    while (b && (bg = getComputedStyle(b).backgroundColor) === 'rgba(0, 0, 0, 0)') b = b.parentElement;
    const l1 = lum(cs.color), l2 = lum(b ? bg : 'rgb(0, 0, 0)');
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const bassi = [...s.querySelectorAll('*')].filter(vis).filter((e) =>
      [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()))
    .map((e) => [nome(e), contrasto(e)]).filter(([, c]) => c < 4.5).map(([n, c]) => n + ' ' + c.toFixed(2));
  const ch = document.getElementById('intera-chiudi').getBoundingClientRect();
  const sr = s.getBoundingClientRect();
  const animati = [s, ...s.querySelectorAll('*')].filter((e) => getComputedStyle(e).animationName !== 'none').map(nome);
  return {
    aperto: !s.hidden && vis(s), piccoli: piccoli.slice(0, 6), fuori: fuori.slice(0, 6), bassi: bassi.slice(0, 6),
    chiudi: [Math.round(ch.top), Math.round(ch.bottom), Math.round(ch.height)],
    pieno: Math.abs(sr.top) < 1 && Math.abs(sr.bottom - H) < 1 && Math.abs(sr.left) < 1 && Math.abs(sr.right - W) < 1,
    pagina: document.scrollingElement.scrollWidth > W + 1 || document.scrollingElement.scrollHeight > H + 1,
    postoDiLato: posto.scrollWidth > posto.clientWidth + 1,
    scorre: posto.scrollHeight > posto.clientHeight + 1,
    animati: animati.slice(0, 4), titolo: document.getElementById('intera-titolo').textContent,
  };
})()"""


def misura_strato(p, cosa, etichetta):
    m = p.valuta(MISURA) or {}
    ok = (m.get("aperto") and not m.get("piccoli") and not m.get("fuori") and not m.get("bassi")
          and m.get("pieno") and not m.get("pagina") and not m.get("postoDiLato")
          and not m.get("animati") and m["chiudi"][0] >= 0 and m["chiudi"][2] >= 64)
    verifica(f"{etichetta} {cosa}: testo ≥ 16 px, niente di lato, contrasto AA, «Chiudi» in alto ≥ 64 px, "
             "tutto lo schermo, niente animazioni", bool(ok), json.dumps(m, ensure_ascii=False)[:400])
    return m


def schede_lunghe():
    from calliope.schermi import schede
    codice = "\n".join(
        [f"def passo_{i}(dati, soglia=0.{i}, nome_molto_lungo_per_andare_di_lato_{i}='valore'):  "
         f"# commento lungo che esce dalla larghezza del telefono" for i in range(40)])
    lavoro = schede.lavoro("Conta le parole nei documenti", "codice", "fatto",
                           "Ho scritto il programma e i test: conta le parole di ogni file.",
                           file=[{"nome": "conta.py", "testo": codice},
                                 {"nome": "test_conta.py", "testo": codice[:800]}],
                           test={"eseguiti": 3}, cartella="Lavori/conta", ident=11)
    righe = [["Gennaio", "120,00", "35,50", "Luce e gas di casa", "pagata", "bonifico"]] * 14
    doc = schede.documento({"titolo": "Spese di casa", "blocchi": [
        {"tipo": "paragrafo", "testo": "Il riepilogo delle spese del primo semestre."},
        {"tipo": "tabella", "colonne": ["Mese", "Luce", "Gas", "Descrizione delle voci", "Stato",
                                        "Pagamento"], "righe": righe}]}, "word", "Spese.docx", ident=12)
    timer = schede.timer({"id": 13, "label": "per la pasta", "due": time.time() + 600})
    return lavoro, doc, timer


def tutti(hub, scheda):
    return [hub.invia_a(s["id"], scheda) for s in hub.abbinati()]


def prova(exe, srv, hub, web):
    _, token = srv.archivio.crea_con_token("telefono-dario", proprietario="dario", proprietario_nome="Dario")
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-intera",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        dimensione(p, 375, 812)
        ok = aspetta(lambda: p.valuta(f"!!window.calliopeTelefono && {T}.st.collegato"), 15)
        verifica("telefono di chi amministra: collegato", bool(ok))
        aspetta(lambda: p.valuta("!!window.calliopeSchermo && document.getElementById('stato')"
                                 ".className.includes('ok')"), 10)
        aspetta(lambda: hub.collegati(), 10)
        aspetta(lambda: p.valuta("!document.getElementById('cruscotto-tel').hidden"), 5)
        lavoro, doc, timer = schede_lunghe()
        for s in (timer, doc, lavoro):
            tutti(hub, s)
            time.sleep(0.15)
        ok = aspetta(lambda: len((p.valuta(f"{T}.carosello()") or {}).get("ordine", [])) >= 3, 5)
        verifica("le tre schede nel carosello", bool(ok), json.dumps(p.valuta(f"{T}.carosello()")))
        time.sleep(0.4)                                      # segnaTagli (ogni 250 ms)
        esp = p.valuta("Object.fromEntries([...document.querySelectorAll('#binario > [data-chiave]')]"
                       ".map(e => [e.dataset.chiave, !!e.querySelector('.espandi') && "
                       "getComputedStyle(e.querySelector('.espandi')).display !== 'none']))") or {}
        verifica("«Espandi» sul lavoro e sul documento, non sul timer",
                 esp.get("lavoro:11") is True and esp.get("documento:12") is True
                 and esp.get(timer["chiave"]) is False, json.dumps(esp))
        h = p.valuta("document.querySelector('#binario [data-chiave=\"lavoro:11\"] .espandi').getBoundingClientRect().height")
        verifica("«Espandi» si tocca bene (≥ 44 px)", (h or 0) >= 44, h)
        foto(p, "carosello-espandi-375x812.png")

        # ── il cruscotto dal menu: subito a schermo intero ──
        tocca(p, "#menu-apri")
        aspetta(lambda: p.valuta("!document.getElementById('menu').hidden"), 3)
        tocca(p, "#cruscotto-tel")
        ok = aspetta(lambda: p.valuta("!document.getElementById('strato-scheda').hidden && "
                                      "!!document.querySelector('#intera-posto .tipo-cruscotto .cr-sezione')"), 10)
        verifica("cruscotto dal menu: si apre direttamente a schermo intero", bool(ok))
        verifica("il menu si chiude e il cruscotto resta anche nel carosello",
                 p.valuta("document.getElementById('menu').hidden && "
                          "!!document.querySelector('#binario .tipo-cruscotto')"))
        verifica("nello strato c'è solo «Aggiorna» del cruscotto (il suo «Chiudi» è quello dello strato)",
                 p.valuta("[...document.querySelectorAll('#intera-posto [data-cruscotto]')]"
                          ".filter(b => getComputedStyle(b).display !== 'none').map(b => b.textContent)") == ["Aggiorna"])
        for w, hh, nome in DIMENSIONI:
            dimensione(p, w, hh)
            misura_strato(p, "cruscotto", f"{w}×{hh}")
            foto(p, f"cruscotto-intero-{nome}-{w}x{hh}.png")
        dimensione(p, 375, 812)
        # scorrimento, poi «Aggiorna»: stesso elemento, scorrimento rimasto
        sc = p.valuta("(() => { const x = document.getElementById('intera-posto'); x.scrollTop = 260;"
                      " window.__cr = x.firstElementChild; return x.scrollTop; })()")
        verifica("il cruscotto scorre in verticale nello strato", (sc or 0) > 100, sc)
        hub.cruscotto._quando = 0.0
        prima = hub.cruscotto.calcoli
        p.valuta("document.querySelector('#intera-posto [data-cruscotto=\"aggiorna\"]').click(); 1")
        ok = aspetta(lambda: hub.cruscotto.calcoli > prima, 5)
        time.sleep(0.5)
        dopo = p.valuta("[document.getElementById('intera-posto').scrollTop,"
                        " window.__cr === document.getElementById('intera-posto').firstElementChild]") or [0, False]
        verifica("aggiornamento del cruscotto: al suo posto (stesso elemento), scorrimento conservato",
                 bool(ok) and dopo[1] and abs(dopo[0] - sc) <= 2, json.dumps(dopo))
        # una scheda nuova: va nel carosello, lo strato resta
        from calliope.schermi import schede
        tutti(hub, schede.calcolo("17 × 6", "102"))
        ok = aspetta(lambda: len((p.valuta(f"{T}.carosello()") or {}).get("ordine", [])) >= 5, 5)
        c = p.valuta(f"{T}.carosello()") or {}
        verifica("una scheda nuova va nel carosello e lo strato resta aperto sul cruscotto",
                 bool(ok) and c.get("intera") == "cruscotto"
                 and p.valuta("!document.getElementById('strato-scheda').hidden"), json.dumps(c))
        tocca(p, "#intera-chiudi")
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
        verifica("«Chiudi»: lo strato si chiude", bool(ok)
                 and p.valuta(f"{T}.carosello().intera") is None)
        aspetta(lambda: p.valuta("!(history.state && history.state.calliopeStrato)"), 2)
        verifica("«Chiudi» toglie anche la voce nella cronologia del browser",
                 p.valuta("!(history.state && history.state.calliopeStrato)"))

        # ── il lavoro con il codice lungo: un tocco sulla scheda ──
        p.valuta(f"{T}.vaiA('lavoro:11'); 1")
        time.sleep(0.2)
        tocca(p, "#binario [data-chiave=\"lavoro:11\"] .riassunto-lavoro")
        ok = aspetta(lambda: p.valuta(f"{T}.carosello().intera") == "lavoro:11", 3)
        verifica("un tocco sulla scheda del lavoro la apre a schermo intero", bool(ok))
        di_lato = p.valuta("(() => { const pre = document.querySelector('#intera-posto pre.codice');"
                           " return [pre.scrollWidth > pre.clientWidth + 1, getComputedStyle(pre).overflowX]; })()")
        verifica("il codice scorre di lato nel suo riquadro", bool(di_lato and di_lato[0])
                 and di_lato[1] in ("auto", "scroll"), json.dumps(di_lato))
        for w, hh, nome in DIMENSIONI:
            dimensione(p, w, hh)
            misura_strato(p, "lavoro", f"{w}×{hh}")
            foto(p, f"lavoro-intero-{nome}-{w}x{hh}.png")
        dimensione(p, 375, 812)
        sc = p.valuta("(() => { const x = document.getElementById('intera-posto'); x.scrollTop = 500;"
                      " window.__lv = x.firstElementChild; return x.scrollTop; })()")
        aggiornato = dict(lavoro, sposta=False, riassunto="Ho scritto il programma e i test: aggiornato in diretta.")
        tutti(hub, aggiornato)
        ok = aspetta(lambda: "aggiornato in diretta" in (p.valuta(
            "document.querySelector('#intera-posto .riassunto-lavoro').textContent") or ""), 5)
        dopo = p.valuta("[document.getElementById('intera-posto').scrollTop,"
                        " window.__lv === document.getElementById('intera-posto').firstElementChild]") or [0, False]
        verifica("lavoro in diretta: aggiornato al suo posto, scorrimento conservato",
                 bool(ok) and dopo[1] and abs(dopo[0] - sc) <= 2, json.dumps([sc] + dopo))
        tasto(p, "Escape", "Escape", 27)
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
        verifica("Esc chiude lo strato", bool(ok))

        # ── il documento con «Espandi», poi il gesto indietro ──
        p.valuta(f"{T}.vaiA('documento:12'); 1")
        time.sleep(0.2)
        tocca(p, "#binario [data-chiave=\"documento:12\"] .espandi")
        ok = aspetta(lambda: p.valuta(f"{T}.carosello().intera") == "documento:12", 3)
        verifica("«Espandi» apre il documento a schermo intero", bool(ok))
        tab = p.valuta("(() => { const t = document.querySelector('#intera-posto table');"
                       " return [t.scrollWidth > t.clientWidth + 1, getComputedStyle(t).overflowX]; })()")
        verifica("la tabella larga scorre di lato nel suo riquadro", bool(tab and tab[0])
                 and tab[1] in ("auto", "scroll"), json.dumps(tab))
        misura_strato(p, "documento", "375×812")
        foto(p, "documento-intero-iphone13mini-375x812.png")
        p.valuta("history.back(); 1")
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
        verifica("il gesto indietro chiude lo strato (e la pagina resta)", bool(ok)
                 and p.valuta("location.pathname") == "/telefono/")

        # ── il microfono acceso: «Chiudi» è un tocco, poi «Parla» è lì ──
        p.valuta(f"{T}.st.mic = true; 1")
        aspetta(lambda: p.valuta("document.getElementById('vista').classList.contains('mic-acceso')"), 2)
        p.valuta(f"{T}.apriIntera('lavoro:11'); 1")
        for w, hh, nome in DIMENSIONI:
            dimensione(p, w, hh)
            misura_strato(p, "lavoro, microfono acceso", f"{w}×{hh}")
        foto(p, "lavoro-intero-mic-acceso-812x375.png")
        tocca(p, "#intera-chiudi")
        ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
        parla = p.valuta("(() => { const r = document.getElementById('parla').getBoundingClientRect();"
                         " const e = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);"
                         " return !!e && !!e.closest('#parla') && r.bottom <= innerHeight + 1; })()")
        verifica("microfono acceso: un tocco su «Chiudi» e «Parla» è lì", bool(ok) and parla is True, parla)
        p.valuta(f"{T}.st.mic = false; 1")
        dimensione(p, 375, 812)

        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
    finally:
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
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    shutil.rmtree(PC.TMP, ignore_errors=True)
    shutil.rmtree(PCP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    PCP.TMP = TMP
    try:
        cfg, srv, hub, web = PCP.avvia()
        try:
            prova(exe, srv, hub, web)
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
