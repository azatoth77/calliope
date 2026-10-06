import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Schermo acceso e vista della web app del telefono (04/10/2026: in auto con
«Microfono acceso» lo schermo dell'iPhone si spegneva, iOS sospendeva la pagina e Calliope
smetteva di ascoltare).

Nel browser vero (Edge o Chromium senza finestra, DevTools; senza si salta), server degli
schermi e dei satelliti veri su 127.0.0.1, telefono già abbinato, microfono finto del browser.
La Screen Wake Lock API è sostituita da una finta che si comporta come WebKit: la prima
richiesta vale solo con un gesto in corso (finito appena il gestore aspetta qualcosa), dopo
una riuscita non serve più; i tocchi sono veri (Input.dispatchMouseEvent: gesto del browser).
- `diagnosi` di schermo-acceso.js: iOS 17.5 nella web app sulla Home (richiesta che riesce ma
  non tiene: avviso), Edge per iOS 17 senza l'API, iOS 18.4, iPad «da computer», Windows;
- toccando «Microfono acceso» lo schermo si chiede nel gesto (con la richiesta dopo
  l'apertura del microfono, come prima, WebKit diceva no) e l'indicatore dice «Schermo
  acceso»;
- il sistema toglie il blocco a pagina visibile → ripreso da solo; se il browser dice no,
  l'indicatore lo dice («Calliope smetterà di ascoltare») e il tocco dopo lo riprende;
- pagina nascosta → microfono spento, blocco tolto, nessuna richiesta da nascosta; microfono
  spento a mano → blocco tolto, indicatore nascosto; opzione «tengo acceso lo schermo» spenta →
  blocco tolto e avviso; riaccesa → richiesto;
- senza l'API: il microfono si accende lo stesso e l'avviso c'è;
- la vista (dal 04/10 la pagina è sempre quella che era la vista da guida): fondo nero, nessuna
  animazione, niente vista normale né «Vista da guida»/«Esci», l'ultima risposta nel carosello,
  «Parla» ridotto col microfono acceso, avviso dello schermo in alto;
- carosello: 4 schede (lista, timer, programma, documento), la più recente per prima e in
  vista, puntini; un aggiornamento resta al suo posto (stesso elemento, vista invariata); la
  risposta subito dopo una scheda non la copre, un turno senza schede mostra la risposta; chi
  scorre a mano non viene spostato; il timer conta;
- modulo da compilare: si apre da solo nel suo strato, controlli mentre si scrive, «Invia»,
  scheda «Compila» nel carosello; «Scrivi» apre la casella col fuoco, la frase arriva e lo
  strato si chiude; il menu ha prova del microfono, schermo acceso, certificato, «dimentica»;
- misure a 375×812, 320×568, 812×375 con 0 e 4+ schede, microfono spento, «Penso…», acceso:
  tutto in uno schermo, niente testo fuori dai contenitori, schede dentro il carosello,
  contrasto AA, tocchi ≥ 64 px, col microfono acceso «Parla» più basso e il carosello più alto;
  modulo, menu e casella aperti: niente di lato, tasti ≥ 64 px (CALLIOPE_FOTO=<cartella> per gli
  screenshot);
- nessun errore JavaScript né violazione della CSP. ~25 s.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="calliope-telschermo-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def aspetta(cond, max_s=5.0, passo=0.05):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


# La Screen Wake Lock API finta, come WebKit: gesto in corso per la prima richiesta
FINTA = r"""(() => {
  const W = window.__wl = { modo: "webkit", richieste: [], attivi: new Set(), sticky: false, gesto: false };
  for (const t of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "keydown", "touchend"]) {
    window.addEventListener(t, () => { W.gesto = true; setTimeout(() => { W.gesto = false; }, 0); }, true);
  }
  class Sentinella extends EventTarget {
    constructor() { super(); this.released = false; this.type = "screen"; }
    async release() {
      if (this.released) return;
      this.released = true;
      W.attivi.delete(this);
      this.dispatchEvent(new Event("release"));
    }
  }
  const api = {
    request(tipo) {
      W.richieste.push({ gesto: W.gesto, visibile: document.visibilityState, modo: W.modo });
      if (W.modo === "nega") return Promise.reject(new DOMException("risparmio energetico", "NotAllowedError"));
      if (W.modo === "webkit" && !W.gesto && !W.sticky)
        return Promise.reject(new DOMException("Permission was denied", "NotAllowedError"));
      W.sticky = true;
      const s = new Sentinella();
      W.attivi.add(s);
      return Promise.resolve(s);
    },
  };
  W.togli = () => { for (const s of [...W.attivi]) s.release(); };
  W.n = () => W.attivi.size;
  if (localStorage.getItem("__wl_assente") === "1") { delete Navigator.prototype.wakeLock; return; }
  Object.defineProperty(Navigator.prototype, "wakeLock", { get: () => api, configurable: true });
})();"""

EMULA = """(() => {
  if (!window.__vis) {
    window.__vis = 'visible';
    Object.defineProperty(document, 'visibilityState', { get: () => window.__vis, configurable: true });
    Object.defineProperty(document, 'hidden', { get: () => window.__vis === 'hidden', configurable: true });
  }
})(); 1"""


def avvia(cartella: Path):
    from calliope.config import Config
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
    import prova_telefono_abbina as PTA
    cartella.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.config_dir = str(cartella)
    cfg.memory_db = str(cartella / "memoria.db")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    cfg.telefono_web = str(cartella / "web")         # niente onnxruntime-web: non serve qui
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    web = ServerSchermi(hub, "127.0.0.1", PTA.porta_libera(), attesa_porta_s=5).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    return cfg, srv, hub, web


class Tel:
    """La pagina con le scorciatoie della prova."""

    def __init__(self, pagina):
        self.p = pagina

    def v(self, js):
        return self.p.valuta(js)

    def tocca(self, id_):
        """Un tocco vero (gesto del browser) al centro dell'elemento."""
        self.tocca_sel("#" + id_)

    def tocca_sel(self, sel):
        """Un tocco vero (gesto del browser) al centro del primo elemento del selettore."""
        r = self.v(f"(() => {{ const e = document.querySelector({json.dumps(sel)});"
                   f" if (!e.closest('#vista')) e.scrollIntoView({{block: 'center'}});"
                   f" const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
        for t in ("mousePressed", "mouseReleased"):
            self.p._chiama("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1],
                                                         "button": "left", "clickCount": 1})

    def schermo(self):
        return self.v("window.calliopeTelefono.schermoStato()") or {}

    def wl(self):
        return self.v("({n: window.__wl.n(), richieste: window.__wl.richieste})") or {}

    def indicatore(self):
        return self.v("(() => { const e = document.getElementById('schermo-stato');"
                      " return {visibile: !e.hidden, classe: e.className,"
                      " testo: e.textContent}; })()") or {}

    def visibilita(self, stato):
        self.v(EMULA)
        self.v(f"window.__vis = '{stato}'; document.dispatchEvent(new Event('visibilitychange')); 1")

    def mic(self):
        return bool(self.v("window.calliopeTelefono.st.mic"))

    def modelli_finti(self):
        """Niente onnxruntime-web qui: la wake word finta basta per accendere il microfono."""
        aspetta(lambda: self.v("window.calliopeTelefono.st.modelli") == "errore", 10)
        self.v("window.calliopeTelefono.st.modelli = 'pronti';"
               "window.calliopeTelefono.ascolto.wake = {reset() {}, async process() { return null; }}; 1")
        self.v("window.calliopeTelefono.st.micVoluto = false; 1")


def diagnosi(t: Tel):
    casi = t.v("""import('/telefono/schermo-acceso.js').then((m) => {
      const ios17 = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';
      const edge17 = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/129.0 Version/17.0 Mobile/15E148 Safari/604.1';
      const ios184 = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/135.0 Mobile/15E148 Safari/605.1.15';
      const ipad = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15';
      const win = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0';
      return {
        v17: m.versioneIOS(ios17), vipad: m.versioneIOS(ipad, true), vmac: m.versioneIOS(ipad, false), vwin: m.versioneIOS(win),
        home17: m.diagnosi({api: true, ua: ios17, standalone: true}),
        safari17: m.diagnosi({api: true, ua: ios17, standalone: false}),
        edge17: m.diagnosi({api: false, ua: edge17, standalone: false}),
        home184: m.diagnosi({api: true, ua: ios184, standalone: true}),
        ipadHome: m.diagnosi({api: true, ua: ipad, toccoMac: true, standalone: true}),
        win: m.diagnosi({api: true, ua: win}),
        winSenza: m.diagnosi({api: false, ua: win}),
      };
    })""") or {}
    verifica("diagnosi: versione di iOS dall'user agent (iPhone, iPad «da computer»; Mac e Windows no)",
             casi.get("v17") == [17, 5] and casi.get("vipad") == [18, 1] and casi.get("vmac") is None
             and casi.get("vwin") is None, json.dumps({k: casi.get(k) for k in ("v17", "vipad", "vmac")}))
    h = casi.get("home17") or {}
    verifica("diagnosi: web app sulla Home con iOS 17.5 → inaffidabile, con il perché e il rimedio",
             h.get("inaffidabile") is True and "18.4" in h.get("motivo", "")
             and "Blocco automatico" in h.get("motivo", ""), h.get("motivo", "")[:90])
    verifica("diagnosi: Safari 17.5 nel browser → affidabile",
             (casi.get("safari17") or {}).get("inaffidabile") is False)
    e = casi.get("edge17") or {}
    verifica("diagnosi: Edge per iOS 17 senza l'API → «solo da iOS 18.4», aggiorna o Safari",
             e.get("api") is False and "18.4" in e.get("motivo", "") and "Safari" in e.get("motivo", ""))
    verifica("diagnosi: web app con iOS 18.4 → affidabile",
             (casi.get("home184") or {}).get("inaffidabile") is False)
    verifica("diagnosi: iPad 18.1 «da computer» nella web app → inaffidabile",
             (casi.get("ipadHome") or {}).get("inaffidabile") is True)
    verifica("diagnosi: Windows → affidabile; senza l'API un motivo generico",
             (casi.get("win") or {}).get("inaffidabile") is False
             and "non sa tenere acceso" in (casi.get("winSenza") or {}).get("motivo", ""))


def scenari(t: Tel, srv):
    T = "window.calliopeTelefono"
    ok = aspetta(lambda: t.v(f"!!{T} && {T}.st.collegato"), 15)
    verifica("pagina caricata e collegata come satellite", bool(ok))
    if not ok:
        return
    diagnosi(t)
    t.modelli_finti()
    verifica("microfono spento: indicatore nascosto, nessuna richiesta",
             not t.indicatore().get("visibile") and not t.wl().get("richieste"))

    # 1. tocco vero su «Microfono acceso»: richiesta nel gesto
    t.tocca("microfono")
    ok = aspetta(lambda: t.mic() and t.schermo().get("stato") == "acceso", 5)
    w = t.wl()
    verifica("tocco su «Microfono acceso»: microfono acceso e schermo tenuto acceso", bool(ok),
             json.dumps(t.schermo().get("stato")))
    verifica("la richiesta parte nel gesto (WebKit vuole il gesto per la prima)",
             len(w.get("richieste", [])) == 1 and w["richieste"][0]["gesto"] is True
             and w.get("n") == 1, json.dumps(w.get("richieste")))
    ind = t.indicatore()
    verifica("indicatore: «Schermo acceso», discreto", ind.get("visibile") and "ok" in ind.get("classe", "")
             and ind.get("testo") == "Schermo acceso", ind.get("testo"))

    # 2. il sistema lo toglie a pagina visibile: ripreso da solo (dopo una riuscita non serve il gesto)
    t.v("window.__wl.togli(); 1")
    ok = aspetta(lambda: t.wl().get("n") == 1 and t.schermo().get("stato") == "acceso", 3)
    verifica("tolto dal sistema a pagina visibile → ripreso da solo", bool(ok),
             f"cadute {t.schermo().get('cadute')}")

    # 3. il browser dice no (risparmio energetico): l'avviso, poi il tocco dopo lo riprende
    t.v("window.__wl.modo = 'nega'; window.__wl.togli(); 1")
    ok = aspetta(lambda: t.schermo().get("stato") == "negato", 3)
    ind = t.indicatore()
    verifica("negato: l'indicatore dice che lo schermo può spegnersi e Calliope smetterà di ascoltare",
             bool(ok) and "avvisa" in ind.get("classe", "") and "smetterà di ascoltare" in ind.get("testo", "")
             and "tocca lo schermo" in ind.get("testo", ""), ind.get("testo", "")[:120])
    verifica("negato: il microfono resta acceso", t.mic())
    t.v("window.__wl.modo = 'webkit'; 1")
    n = len(t.wl().get("richieste", []))
    t.tocca("risposta-testo")                          # un tocco qualsiasi sulla pagina
    ok = aspetta(lambda: t.schermo().get("stato") == "acceso" and t.wl().get("n") == 1, 3)
    verifica("il tocco dopo lo riprende", bool(ok) and len(t.wl().get("richieste", [])) == n + 1)

    # 4. pagina nascosta: microfono spento, blocco tolto, niente richieste da nascosta
    t.visibilita("hidden")
    ok = aspetta(lambda: not t.mic() and t.wl().get("n") == 0, 3)
    verifica("pagina nascosta: microfono spento e schermo lasciato", bool(ok))
    n = len(t.wl().get("richieste", []))
    t.visibilita("visible")
    time.sleep(0.3)
    verifica("tornata visibile col microfono spento: nessuna richiesta, indicatore nascosto",
             len(t.wl().get("richieste", [])) == n and not t.indicatore().get("visibile"))
    w = t.wl()
    verifica("nessuna richiesta fatta a pagina nascosta",
             all(r.get("visibile") == "visible" for r in w.get("richieste", [])))

    # 5. riacceso e poi spento a mano
    t.tocca("microfono")
    aspetta(lambda: t.mic() and t.schermo().get("stato") == "acceso", 5)
    t.tocca("microfono")
    ok = aspetta(lambda: not t.mic() and t.wl().get("n") == 0, 3)
    verifica("microfono spento a mano: schermo lasciato, indicatore nascosto",
             bool(ok) and t.schermo().get("stato") == "spento" and not t.indicatore().get("visibile"))

    # 6. opzione «tengo acceso lo schermo» spenta e riaccesa
    t.tocca("microfono")
    aspetta(lambda: t.mic() and t.schermo().get("stato") == "acceso", 5)
    t.tocca("menu-apri")
    verifica("menu: si apre dall'icona in alto", bool(aspetta(lambda: t.v("!document.getElementById('menu').hidden"), 2)))
    t.tocca("schermo-tieni")
    ok = aspetta(lambda: t.wl().get("n") == 0 and not t.schermo().get("tieni"), 3)
    ind = t.indicatore()
    verifica("opzione spenta: schermo lasciato e avviso che può spegnersi", bool(ok)
             and "smetterà di ascoltare" in ind.get("testo", "") and t.mic(), ind.get("testo", "")[:80])
    verifica("opzione salvata", t.v("localStorage.getItem('calliope.telefono.schermo_acceso')") == "0")
    t.tocca("schermo-tieni")
    ok = aspetta(lambda: t.wl().get("n") == 1 and t.schermo().get("stato") == "acceso", 3)
    verifica("opzione riaccesa: schermo di nuovo tenuto acceso", bool(ok))
    t.tocca("menu-chiudi")
    verifica("menu: «Chiudi» lo chiude", bool(aspetta(lambda: t.v("document.getElementById('menu').hidden"), 2)))

    # 7. la vista (04/10: è sempre quella che era la vista da guida)
    t.v(f"{T}.comando({{tipo: 'frase', turno: 7, id: 70, testo: 'Sono le 18:42.', rate: 22050, byte: 0}});"
        f"{T}.comando({{tipo: 'frase', turno: 7, id: 71, testo: 'Domani piove.', rate: 22050, byte: 0}}); 1")
    g = t.v("""(() => {
      const cs = (e) => getComputedStyle(e);
      const vista = document.getElementById('vista');
      const v = document.getElementById('tel-voce');
      const prima = v.className;
      v.className = 'voce ascolta';                       // lo stato che di solito pulsa
      const anim = [...document.querySelectorAll('body *')].map((e) => cs(e).animationName).filter((n) => n && n !== 'none');
      v.className = prima;
      return {
        sfondo: cs(vista).backgroundColor, body: cs(document.body).backgroundColor, anim,
        risposta: document.getElementById('risposta-testo').textContent,
        vecchi: ['guida', 'guida-apri', 'guida-esci', 'voce-tel', 'principale', 'cronologia'].filter((id) => document.getElementById(id)),
        parla: document.getElementById('parla').getBoundingClientRect().height,
        mic: document.getElementById('microfono').getAttribute('aria-checked'),
        acceso: vista.classList.contains('mic-acceso'),
      };
    })()""") or {}
    verifica("vista: fondo nero, niente vista normale né «Vista da guida»/«Esci»",
             g.get("sfondo") == "rgb(0, 0, 0)" and g.get("body") == "rgb(0, 0, 0)" and g.get("vecchi") == [],
             json.dumps(g.get("vecchi")))
    verifica("vista: nessuna animazione (anche nello stato «ascolto»)", g.get("anim") == [], json.dumps(g.get("anim")))
    verifica("vista: l'ultima risposta intera nel carosello (le frasi del turno)",
             g.get("risposta") == "Sono le 18:42. Domani piove.", g.get("risposta"))
    verifica("vista: microfono acceso segnato, «Parla» ridotto (≤ 76 px)",
             g.get("mic") == "true" and g.get("acceso") and g.get("parla", 999) <= 76, f"{g.get('parla')}")
    t.v(f"{T}.comando({{tipo: 'frase', turno: 8, id: 80, testo: 'Fatto.', rate: 22050, byte: 0}}); 1")
    ok = aspetta(lambda: t.v("document.getElementById('risposta-testo').textContent") == "Fatto.", 2)
    verifica("vista: risposta nuova al turno dopo", bool(ok))
    # avviso dello schermo anche nella vista
    t.v("window.__wl.modo = 'nega'; window.__wl.togli(); 1")
    ok = aspetta(lambda: t.v("(() => { const e = document.getElementById('schermo-avviso');"
                             " return !e.hidden && e.textContent.includes('smetterà di ascoltare'); })()"), 3)
    verifica("vista: lo schermo negato si legge in alto", bool(ok))
    t.v("window.__wl.modo = 'webkit'; 1")
    t.tocca("risposta-testo")
    ok = aspetta(lambda: t.schermo().get("stato") == "acceso"
                 and t.v("document.getElementById('schermo-avviso').hidden"), 3)
    verifica("vista: un tocco lo riprende e l'avviso sparisce", bool(ok))


def schede_prova():
    from calliope.schermi import schede
    ora = time.time()
    lista = schede.lista("spesa", ["latte", "uova", "pane", "pomodori", "caffè"], aggiunti=["pane"])
    timer = schede.timer({"id": 4, "label": "per la pasta", "due": ora + 540})
    righe = [{"tipo": "out", "testo": f"riga {i}: elaboro il file\n"} for i in range(12)]
    esec = schede.esecuzione("Conta le parole", "conta.py", "python", "in_corso", [], righe, 0, None,
                             ora - 3, 3.0, 60, ident=7)
    doc = schede.documento({"titolo": "Disdetta della palestra", "blocchi": [
        {"tipo": "paragrafo", "testo": "Spettabile palestra, con la presente comunico la disdetta "
         "dell'abbonamento annuale a partire dal mese prossimo."},
        {"tipo": "paragrafo", "testo": "Cordiali saluti."}]}, "word", "Disdetta palestra.docx", ident=5)
    return {"lista": lista, "timer": timer, "esecuzione": esec, "documento": doc}


def tutti(hub, scheda):
    """La scheda a ogni schermo abbinato (il telefono è uno di loro)."""
    return [hub.invia_a(s["id"], scheda) for s in hub.abbinati()]


def carosello(t: Tel, hub):
    """Le schede nel carosello: la più recente per prima, aggiornate al loro posto, chi scorre
    a mano non viene spostato, la risposta dopo una scheda non la copre."""
    T = "window.calliopeTelefono"
    ok = aspetta(lambda: hub.collegati(), 10)
    verifica("schede: il telefono è collegato anche come schermo", bool(ok))
    S = schede_prova()
    for k in ("lista", "timer", "esecuzione", "documento"):
        tutti(hub, S[k])
        time.sleep(0.15)
    ok = aspetta(lambda: len((t.v(f"{T}.carosello()") or {}).get("ordine", [])) == 5, 5)
    c = t.v(f"{T}.carosello()") or {}
    verifica("carosello: risposta e 4 schede, la più recente per prima e in vista",
             bool(ok) and c.get("ordine", [""])[0] == "documento:5" and c.get("vista") == "documento:5",
             json.dumps(c))
    punti = t.v("document.querySelectorAll('#punti i').length")
    verifica("carosello: indicatore di posizione (5 puntini, uno segnato)", punti == 5
             and t.v("document.querySelectorAll('#punti i.qui').length") == 1, str(punti))
    # aggiornamento al suo posto: stesso elemento, stessa posizione, vista invariata, niente segno
    t.v("window.__el = document.querySelector('#binario [data-chiave=\"esecuzione:7\"]'); 1")
    from calliope.schermi import schede
    righe = [{"tipo": "out", "testo": f"riga {i}\n"} for i in range(20)]
    tutti(hub, schede.esecuzione("Conta le parole", "conta.py", "python", "in_corso", [], righe, 0, None,
                                 time.time() - 5, 5.0, 60, ident=7, sposta=False))
    ok = aspetta(lambda: t.v("(document.querySelector('#binario [data-chiave=\"esecuzione:7\"] pre')||{}).textContent||''")
                 .count("riga") == 20, 5)
    c2 = t.v(f"{T}.carosello()") or {}
    verifica("carosello: scheda aggiornata al suo posto (stesso elemento, ordine e vista uguali)",
             bool(ok) and t.v("window.__el === document.querySelector('#binario [data-chiave=\"esecuzione:7\"]')")
             and c2.get("ordine") == c.get("ordine") and c2.get("vista") == "documento:5", json.dumps(c2))
    # la risposta del turno arriva subito dopo la scheda: resta la scheda
    t.v(f"{T}.comando({{tipo: 'frase', turno: 30, id: 300, testo: 'Ecco la disdetta.', rate: 22050, byte: 0}}); 1")
    c3 = t.v(f"{T}.carosello()") or {}
    verifica("carosello: la risposta va in testa ma la scheda appena mostrata resta in vista",
             c3.get("ordine", [""])[0] == "__risposta" and c3.get("vista") == "documento:5", json.dumps(c3))
    # turno nuovo senza schede: si vede la risposta
    t.v(f"{T}.opzioniCarosello.schedaMs = 0; {T}.comando({{tipo: 'frase', turno: 31, id: 310, testo: 'Sono le sette.', rate: 22050, byte: 0}}); 1")
    c4 = t.v(f"{T}.carosello()") or {}
    verifica("carosello: turno nuovo senza schede → la risposta in vista", c4.get("vista") == "__risposta", json.dumps(c4))
    # scorrimento a mano (come un dito): poi una scheda nuova non la sposta
    t.v("(() => { const b = document.getElementById('binario'); b.dispatchEvent(new PointerEvent('pointerdown'));"
        " const p = [...b.children].filter((e) => !e.hidden); b.scrollTo({left: p[3].offsetLeft - p[0].offsetLeft, behavior: 'instant'}); })(); 1")
    ok = aspetta(lambda: (t.v(f"{T}.carosello()") or {}).get("vista") == c4["ordine"][3], 2)
    tutti(hub, schede.calcolo("17 × 6", "102"))
    aspetta(lambda: len((t.v(f"{T}.carosello()") or {}).get("ordine", [])) == 6, 5)
    c5 = t.v(f"{T}.carosello()") or {}
    verifica("carosello: chi scorre a mano non viene spostato da una scheda nuova",
             bool(ok) and c5.get("vista") == c4["ordine"][3] and len(c5.get("ordine", [])) == 6, json.dumps(c5))
    t.v(f"{T}.opzioniCarosello.manoMs = 0; 1")
    tutti(hub, schede.calcolo("2 + 2", "4"))
    # Si aspetta lo stato finale (06/10): la condizione di prima («vista» con un trattino)
    # era già vera con la vista vecchia, e sotto carico la verifica guardava troppo presto
    def mostrata():
        c = t.v(f"{T}.carosello()") or {}
        return (c.get("vista") == (c.get("ordine") or [""])[0]
                and c.get("vista") != "__risposta" and len(c.get("ordine", [])) == 7)
    ok = aspetta(mostrata, 15)
    c6 = t.v(f"{T}.carosello()") or {}
    verifica("carosello: passato il tempo, la scheda nuova si mostra (al più 7 cose)",
             c6.get("vista") == c6.get("ordine", [""])[0] and c6.get("vista") != "__risposta"
             and len(c6.get("ordine", [])) == 7, json.dumps(c6))
    t.v(f"{T}.opzioniCarosello.manoMs = 10000; {T}.opzioniCarosello.schedaMs = 12000; 1")
    timer = t.v("(document.querySelector('#binario .tipo-timer .resto')||{}).textContent||''") or ""
    verifica("carosello: il timer conta anche nel carosello", ":" in timer, timer)


def modulo_e_scrivi(t: Tel, hub):
    """Il modulo da compilare si apre da solo in uno strato; la casella per scrivere si apre
    da «Scrivi»; il menu ha tutto il resto."""
    from calliope.schermi import Mittente
    from calliope.schermi.moduli import campo
    T = "window.calliopeTelefono"
    dario = Mittente(persona="dario", nome="Dario", livello="amministra", certo=True)
    ricevuti = []
    spec = {"chiave": "prova", "titolo": "Dati per la fattura", "domanda": "Mi servono questi dati.",
            "campi": [campo("piva", "Partita IVA", "partita_iva"), campo("data", "Data", "data")]}
    res = hub.moduli.apri(spec, lambda v, tt: ricevuti.append(v), dario, "prova", "amministra")
    ok = aspetta(lambda: t.v("!document.getElementById('strato-modulo').hidden"
                             " && document.querySelectorAll('#strato-modulo .campo-modulo').length === 2"), 5)
    verifica("modulo: arriva e si apre da solo nel suo strato", res.get("mostrato") and bool(ok), json.dumps(res)[:120])
    verifica("modulo: nel carosello c'è la sua scheda con «Compila»",
             bool(t.v("!!document.querySelector('#binario .modulo-car .apri-modulo')")))
    return ricevuti, spec


def compila(t: Tel, hub, foto_cb=None):
    T = "window.calliopeTelefono"
    def scrivi(sel, val):
        t.v(f"(() => {{ const i = document.querySelector({sel!r}); i.focus(); i.value = {val!r};"
            f" i.dispatchEvent(new Event('input', {{bubbles: true}})); i.dispatchEvent(new Event('change', {{bubbles: true}})); }})()")
    scrivi('#strato-modulo .campo-modulo[data-nome="piva"] input', "12345678904")
    err = t.v("document.querySelector('#strato-modulo .campo-modulo[data-nome=\"piva\"] .errore-campo').textContent")
    verifica("modulo: i controlli mentre si scrive ci sono anche qui", err == "La cifra di controllo non torna", err)
    scrivi('#strato-modulo .campo-modulo[data-nome="piva"] input', "12345678903")
    scrivi('#strato-modulo .campo-modulo[data-nome="data"] input', "2026-10-04")
    if foto_cb:
        foto_cb()
    t.v("document.activeElement.blur(); 1")
    # Senza conversazione a voce (05/10): «Invia» spento, con la parola da dire; «Scrivi» attenuato
    spento = t.v("(() => { const b = document.querySelector('#strato-modulo .invia-modulo');"
                 " const n = document.querySelector('#strato-modulo .nota-scrittura');"
                 " return b.disabled && n && !n.hidden && n.textContent.includes('Calliope')"
                 " && document.getElementById('scrivi-apri').classList.contains('spento')"
                 " && document.getElementById('foto-apri').classList.contains('spento'); })()")
    verifica("senza conversazione: «Invia» del modulo spento, «Di' «Calliope»…», «Scrivi» e «Foto» attenuati",
             bool(spento))
    hub.conversazioni.voce("dario", "voce", stanza="telefono")      # Dario parla a Calliope
    ok = aspetta(lambda: t.v("!document.querySelector('#strato-modulo .invia-modulo').disabled"
                             " && document.querySelector('#strato-modulo .nota-scrittura').hidden"
                             " && !document.getElementById('scrivi-apri').classList.contains('spento')"), 3)
    verifica("conversazione cominciata: i comandi si riaccendono da soli (evento «scrittura»)", bool(ok))
    t.tocca_sel("#strato-modulo .invia-modulo")
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() if ok else {}
    verifica("modulo: «Invia» manda i valori al server",
             bool(ok) and item.get("valori") == {"piva": "12345678903", "data": "2026-10-04"}, str(item)[:160])
    t.tocca("modulo-chiudi")
    ok = aspetta(lambda: t.v("document.getElementById('strato-modulo').hidden"), 2)
    verifica("modulo: «Chiudi» torna alla vista", bool(ok))
    # la casella per scrivere
    ok = aspetta(lambda: t.v("!document.getElementById('scrivi-apri').hidden"), 5)
    verifica("scrivi: «Scrivi» c'è in fondo (telefono personale)", bool(ok))
    t.tocca("scrivi-apri")
    ok = aspetta(lambda: t.v("!document.getElementById('strato-scrivi').hidden"
                             " && document.activeElement === document.getElementById('scrivi-testo')"), 2)
    verifica("scrivi: si apre con la casella pronta (fuoco nel campo)", bool(ok))
    scrivi("#scrivi-testo", "Calliope, che ore sono?")
    t.tocca_sel("#scrivi button")
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() if ok else {}
    verifica("scrivi: la frase arriva in coda come scritta", bool(ok) and item.get("tipo") == "scritto"
             and item.get("testo") == "Calliope, che ore sono?", str(item)[:160])
    ok = aspetta(lambda: t.v("document.getElementById('strato-scrivi').hidden"), 3)
    verifica("scrivi: inviata, lo strato si chiude da solo", bool(ok))
    hub.conversazioni.chiudi()                                      # «esci»
    ok = aspetta(lambda: t.v("document.getElementById('scrivi-testo').disabled"
                             " && document.getElementById('scrivi-apri').classList.contains('spento')"), 3)
    verifica("conversazione chiusa: casella spenta di nuovo", bool(ok))
    # il menu: tutto il resto
    t.tocca("menu-apri")
    m = t.v("""(() => { const m = document.getElementById('menu'); const q = (s) => m.querySelector(s);
      return {aperto: !m.hidden, diag: !!q('#diag-prova'), tieni: !!q('#schermo-tieni'), ca: !!q('#link-ca'),
              dimentica: !!q('#dimentica'), stato: (q('#tel-collegamento-testo')||{}).textContent,
              schede: (q('#stato-testo')||{}).textContent}; })()""") or {}
    verifica("menu: prova del microfono, schermo acceso, certificato, dimentica, collegamento",
             m.get("aperto") and m.get("diag") and m.get("tieni") and m.get("ca") and m.get("dimentica")
             and m.get("stato") == "collegata" and m.get("schede") == "collegato", json.dumps(m))
    t.p._chiama("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    t.p._chiama("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    verifica("menu: Esc lo chiude", bool(aspetta(lambda: t.v("document.getElementById('menu').hidden"), 2)))


# Misure della vista (04/10): per ogni dimensione e stato niente scorrimento, nessun testo fuori
# dal suo contenitore, parti che non si sovrappongono, schede dentro il carosello, tocchi ≥ 64 px,
# contrasto AA. Con CALLIOPE_FOTO=<cartella> salva anche gli screenshot.
DIMENSIONI = [(375, 812, "iphone13mini"), (320, 568, "piccolo"), (812, 375, "orizzontale")]
RISPOSTA_LUNGA = ("Va bene, allora il file resta salvato nella cartella dei documenti del portatile, "
                  "con il nome che mi hai detto prima. Quando vuoi lo apro, oppure lo mando sullo schermo "
                  "dello studio. Fammi sapere se hai bisogno di altro, anche più tardi.")

MISURA = r"""(() => {
  const g = document.getElementById('vista');
  const H = innerHeight, W = innerWidth, gr = g.getBoundingClientRect();
  const se = document.scrollingElement;
  const fuori = [];
  const vis = (e) => e && !e.hidden && e.getClientRects().length > 0;
  const nome = (e) => e.id || e.className || e.tagName;
  const dentro = (r, c) => r.left >= c.left - 1 && r.right <= c.right + 1 && r.top >= c.top - 1 && r.bottom <= c.bottom + 1;
  const testiDentro = (e, r, solo_x) => {
    const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (!n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const q of rg.getClientRects()) {
        const ok = solo_x ? q.left >= r.left - 1 && q.right <= r.right + 1 : dentro(q, r);
        if (!ok) fuori.push(nome(e) + ': «' + n.textContent.trim().slice(0, 20) + '» esce');
      }
    }
  };
  // contenitori il cui testo deve starci tutto
  const scatole = ['tel-voce', 'tel-dove', 'avviso-tel', 'schermo-avviso', 'parla', 'microfono', 'scrivi-apri', 'menu-apri']
    .map((id) => document.getElementById(id)).filter(vis);
  for (const e of scatole) {
    if (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1) fuori.push(nome(e) + ' trabocca');
    const r = e.getBoundingClientRect();
    if (!dentro(r, gr)) fuori.push(nome(e) + ' fuori dalla vista');
    testiDentro(e, r, false);
  }
  // le schede: dentro il carosello, niente testo fuori di lato (in verticale scorrono dentro di sé)
  const bin = document.getElementById('binario'), br = bin.getBoundingClientRect();
  const pagine = [...bin.children].filter(vis);
  const quiPagina = pagine.find((p) => Math.abs(p.getBoundingClientRect().left - br.left) < 2);
  if (!quiPagina) fuori.push('nessuna scheda allineata al carosello');
  for (const p of pagine) {
    const r = p.getBoundingClientRect();
    if (r.top < br.top - 1 || r.bottom > br.bottom + 1) fuori.push(p.dataset.chiave + ' esce dal carosello in altezza');
    if (p.scrollWidth > p.clientWidth + 1) fuori.push(p.dataset.chiave + ' trabocca di lato');
    if (p === quiPagina) testiDentro(p, r, true);
  }
  const aree = ['.vista-testa', '#carosello', '#parla', '.vista-fondo']
    .map((s) => g.querySelector(s)).filter(vis).map((e) => [nome(e), e.getBoundingClientRect()]);
  for (let i = 0; i < aree.length; i++) {
    if (!dentro(aree[i][1], {left: 0, top: 0, right: W, bottom: H})) fuori.push(aree[i][0] + ' fuori dallo schermo');
    for (let j = i + 1; j < aree.length; j++) {
      const a = aree[i][1], b = aree[j][1];
      if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1)
        fuori.push(aree[i][0] + ' sopra ' + aree[j][0]);
    }
  }
  const lum = (c) => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => v / 255)
    .map((v) => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
  const contrasto = (e) => { const cs = getComputedStyle(e);
    let b = e, bg = 'rgba(0, 0, 0, 0)';
    while (b && (bg = getComputedStyle(b).backgroundColor) === 'rgba(0, 0, 0, 0)') b = b.parentElement;
    const l1 = lum(cs.color), l2 = lum(b ? bg : 'rgb(0, 0, 0)');
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  // ogni elemento con del testo proprio, nella vista e nella scheda in vista
  const conTesto = [...g.querySelectorAll('*')].filter(vis).filter((e) =>
    [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
    && (!e.closest('#binario') || (quiPagina && quiPagina.contains(e))));
  const bassi = conTesto.map((e) => [nome(e), contrasto(e)]).filter(([, c]) => c < 4.5)
    .map(([n, c]) => n + ' ' + c.toFixed(2));
  const tocchi = ['parla', 'microfono', 'scrivi-apri', 'menu-apri'].map((id) => document.getElementById(id)).filter(vis)
    .map((e) => e.getBoundingClientRect()).map((r) => Math.min(r.width, r.height));
  return {
    scorre: se.scrollHeight > H + 1 || se.scrollWidth > W + 1 || g.scrollHeight > g.clientHeight + 1,
    fuori, bassi, tocchi, H, W,
    carosello: br.height, parla: document.getElementById('parla').getBoundingClientRect().height,
    voce: document.querySelector('#tel-voce .voce-testo').textContent,
    dove: document.getElementById('tel-dove').hidden ? '' : document.getElementById('tel-dove').textContent,
    vista: window.calliopeTelefono.carosello().vista,
  };
})()"""

# Gli strati (modulo, menu, scrivi): lo strato scorre da sé, i suoi tasti ≥ 64 px, niente di lato
MISURA_STRATO = r"""((id) => {
  const s = document.getElementById(id), W = innerWidth;
  const vis = (e) => e && !e.hidden && e.getClientRects().length > 0;
  const fuori = [...s.querySelectorAll('*')].filter(vis).filter((e) => { const r = e.getBoundingClientRect();
    return r.width > 0 && (r.left < -1 || r.right > W + 1); }).map((e) => e.id || e.className || e.tagName);
  const tocchi = [...s.querySelectorAll('button')].filter(vis).filter((b) => !b.classList.contains('piccolo-bottone'))
    .map((b) => { const r = b.getBoundingClientRect(); return [b.id || b.className, Math.round(r.height)]; })
    .filter(([, h]) => h < 64);
  return {aperto: vis(s), fuori: fuori.slice(0, 5), tocchi,
          pagina: document.scrollingElement.scrollHeight > innerHeight + 1};
})"""


def foto(t, file):
    import base64
    cartella = os.environ.get("CALLIOPE_FOTO")
    if not cartella:
        return
    r = t.p._chiama("Page.captureScreenshot", {"format": "png"})
    Path(cartella).mkdir(parents=True, exist_ok=True)
    (Path(cartella) / file).write_bytes(base64.b64decode(r["result"]["data"]))


def dimensione(t, w, h):
    t.p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2,
                                                       "mobile": True})
    # Si aspetta che la pagina abbia la dimensione nuova e due fotogrammi disegnati (06/10:
    # 0,2 s fissi non bastavano sotto carico)
    aspetta(lambda: t.v(f"innerWidth === {w} && innerHeight === {h}"), 5, 0.05)
    t.v("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")
    t.v("window.calliopeTelefono.vaiA(window.calliopeTelefono.carosello().vista); 1")


def misure(t, etichetta):
    """La vista nelle tre dimensioni, col microfono spento (il posto è dello studio), mentre
    pensa e col microfono acceso."""
    T = "window.calliopeTelefono"
    t.v(f"{T}.comando({{tipo: 'frase', turno: {40 + len(etichetta)}, id: 400, testo: {json.dumps(RISPOSTA_LUNGA)}, rate: 22050, byte: 0}}); 1")

    def mic(acceso):
        if t.mic() != acceso:
            t.tocca("microfono")
            aspetta(lambda: t.mic() == acceso, 5)

    def spento():
        mic(False)
        t.v(f"{T}.st.attivo = false; {T}.st.altro = 'studio'; {T}.st.pensa = false; 1")

    def pensa():
        t.v(f"{T}.st.attivo = true; {T}.st.altro = null; {T}.st.pensa = true; 1")

    def acceso():
        t.v(f"{T}.st.pensa = false; 1")
        mic(True)
        t.v(f"{T}.st.L = null; 1")

    stati = [
        ("spento", spento, "Microfono spento", "studio"),
        ("pensa", pensa, "Penso…", ""),
        ("acceso", acceso, "Dormo · di' «Calliope»", ""),
    ]
    alti = {}
    for w, h, nome_d in DIMENSIONI:
        dimensione(t, w, h)
        for nome_s, fai, parola, dove in stati:
            fai()
            ok = aspetta(lambda: (t.v(MISURA) or {}).get("voce") == parola, 2)
            time.sleep(0.35)                     # la dissolvenza si decide al giro dopo
            m = t.v(MISURA) or {}
            foto(t, f"telefono-{etichetta}-{nome_d}-{nome_s}.png")
            d = f"{etichetta} {w}×{h} «{parola}»"
            verifica(f"{d}: tutto in uno schermo, niente scorrimento",
                     bool(ok) and not m.get("scorre"), f"{m.get('W')}×{m.get('H')}")
            verifica(f"{d}: nessun testo fuori dai contenitori, parti separate, schede nel carosello",
                     not m.get("fuori"), "; ".join(m.get("fuori", []))[:240])
            verifica(f"{d}: contrasto AA e tocchi ≥ 64 px",
                     not m.get("bassi") and min(m.get("tocchi") or [0]) >= 64,
                     f"{m.get('bassi')} {[round(x) for x in m.get('tocchi') or []]}")
            if dove:
                verifica(f"{d}: il microfono di un altro satellite in una riga piccola",
                         dove in m.get("dove", ""), m.get("dove"))
            verifica(f"{d}: il carosello ha spazio (≥ 120 px)", m.get("carosello", 0) >= 120,
                     f"{m.get('carosello', 0):.0f} px")
            alti[(nome_d, nome_s)] = (m.get("parla", 0), m.get("carosello", 0))
        if h > w:
            p_sp, c_sp = alti[(nome_d, "spento")]
            p_ac, c_ac = alti[(nome_d, "acceso")]
            verifica(f"{etichetta} {w}×{h}: col microfono acceso «Parla» più basso e il carosello più alto",
                     p_ac < p_sp and c_ac > c_sp, f"Parla {p_sp:.0f} → {p_ac:.0f}, carosello {c_sp:.0f} → {c_ac:.0f}")
    mic(False)
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


def una_per_una(t):
    """Ogni scheda del carosello in vista, una alla volta, a 375×812 e 320×568: dentro il
    carosello, niente testo fuori di lato, contrasto AA (le foto: una per tipo)."""
    T = "window.calliopeTelefono"
    for w, h, nome_d in DIMENSIONI[:2]:
        dimensione(t, w, h)
        for k in (t.v(f"{T}.carosello()") or {}).get("ordine", []):
            t.v(f"{T}.vaiA({json.dumps(k)}); 1")
            time.sleep(0.3)
            m = t.v(MISURA) or {}
            tipo = k.split(":")[0].strip("_")
            foto(t, f"telefono-scheda-{nome_d}-{tipo}.png")
            verifica(f"{nome_d} scheda {tipo}: in vista, dentro il carosello, testo dentro, contrasto AA",
                     m.get("vista") == k and not m.get("fuori") and not m.get("bassi") and not m.get("scorre"),
                     f"{m.get('vista')} {m.get('fuori')} {m.get('bassi')}"[:240])
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


def misure_strati(t, hub, spec):
    """Modulo aperto, menu aperto e casella per scrivere, nelle tre dimensioni."""
    from calliope.schermi import Mittente
    T = "window.calliopeTelefono"
    dario = Mittente(persona="dario", nome="Dario", livello="amministra", certo=True)
    hub.moduli.apri(dict(spec, chiave="prova2"), lambda v, tt: None, dario, "prova", "amministra")
    aspetta(lambda: t.v("!document.getElementById('strato-modulo').hidden"), 5)
    for w, h, nome_d in DIMENSIONI:
        dimensione(t, w, h)
        for id_, apri in (("strato-modulo", None), ("menu", "menu-apri"), ("strato-scrivi", "scrivi-apri")):
            if apri:
                t.v(f"{T}.apriStrato({json.dumps(id_)}); document.activeElement.blur(); 1")
            else:
                t.v(f"{T}.apriModulo({T}.carosello().modulo || [...document.querySelectorAll('#binario .modulo-car')]"
                    f".map((e) => e.dataset.chiave)[0]); document.activeElement.blur(); 1")
            if id_ == "menu":
                t.v("document.getElementById('diag-tel').open = false; 1")
            time.sleep(0.2)
            m = t.v(f"({MISURA_STRATO})({json.dumps(id_)})") or {}
            foto(t, f"telefono-{nome_d}-{id_}.png")
            verifica(f"{nome_d} {id_}: aperto, niente di lato, tasti ≥ 64 px, la pagina sotto non scorre",
                     m.get("aperto") and not m.get("fuori") and not m.get("tocchi") and not m.get("pagina"),
                     json.dumps(m)[:200])
            t.v(f"{T}.chiudiStrato({json.dumps(id_)}); 1")
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


def senza_api(t: Tel):
    T = "window.calliopeTelefono"
    t.v("localStorage.setItem('__wl_assente', '1'); 1")
    t.p._chiama("Page.reload")
    time.sleep(0.5)
    ok = aspetta(lambda: t.v(f"!!{T} && {T}.st.collegato"), 15)
    verifica("senza l'API: pagina ricaricata e collegata", bool(ok)
             and t.v("'wakeLock' in navigator") is False)
    t.modelli_finti()
    # il modulo ancora aperto sul server si riapre da solo con la pagina: lo si chiude
    aspetta(lambda: t.v("!document.getElementById('strato-modulo').hidden"), 3)
    t.v(f"{T}.chiudiStrato('strato-modulo'); 1")
    t.tocca("microfono")
    ok = aspetta(lambda: t.mic() and t.schermo().get("stato") == "manca", 5)
    ind = t.indicatore()
    verifica("senza l'API: microfono acceso lo stesso, l'indicatore dice che lo schermo può spegnersi",
             bool(ok) and "avvisa" in ind.get("classe", "") and "smetterà di ascoltare" in ind.get("testo", ""),
             json.dumps([ind, t.mic(), t.schermo().get("stato")])[:300])
    t.tocca("microfono")
    aspetta(lambda: not t.mic(), 3)
    t.v("localStorage.removeItem('__wl_assente'); 1")


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main() -> int:
    import prova_telefono_pagina as PTP
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        exe = PTP.browser()
        if exe is None:
            print("Nessun Edge né Chromium: prova saltata.")
            return SALTATA
        cfg, srv, hub, web = avvia(TMP / "server")
        _, token = srv.archivio.crea_con_token("telefono", proprietario="dario",
                                               proprietario_nome="Dario")
        url = f"http://127.0.0.1:{web.port}/telefono/"
        pagina = PTP.Pagina(exe, url, profilo="profilo-schermo",
                            opzioni=("--use-fake-ui-for-media-stream",
                                     "--use-fake-device-for-media-stream",
                                     "--window-size=390,844"))
        t = Tel(pagina)
        try:
            pagina._chiama("Page.addScriptToEvaluateOnNewDocument", {"source": FINTA})
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            scenari(t, srv)
            misure(t, "0schede")
            carosello(t, hub)
            misure(t, "schede")
            una_per_una(t)
            _, spec = modulo_e_scrivi(t, hub)
            compila(t, hub)
            misure_strati(t, hub, spec)
            senza_api(t)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica("nessun errore JavaScript né violazione della CSP", not errori,
                     "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
            web.ferma()
            srv.ferma()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
