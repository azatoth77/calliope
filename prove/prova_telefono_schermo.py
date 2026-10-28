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
- la vista (dal 27/10 a sezioni, docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md): fondo
  nero, nessuna animazione, niente menu né carosello, l'ultima risposta in Adesso, «Parla» ridotto
  col microfono acceso, avviso dello schermo in alto; Io dalla barra (schermo acceso, gesto
  indietro);
- sezioni: 4 schede (lista, timer, programma, documento) nelle loro raccolte di Le mie cose e,
  vive, anche in Adesso, la più recente per prima; un aggiornamento resta al suo posto (stesso
  elemento); il timer scaduto esce da Adesso e resta in Agenda; il calcolo è l'ultima risposta
  (Conversazione e Adesso); novità sulla barra solo per ciò che non si vede, tolte guardando;
  router sul frammento (barra, #/cose/lavori, indirizzo sconosciuto → Adesso, gesto indietro);
  «In auto» a mano (niente barra, salvata) ed «Esci»;
- Le mie cose (28/10, passo 2a): otto tessere coi conti dai servizi (Ufficio per chi amministra), due
  colonne, il pallino dopo un cambiamento; la pagina Liste dalla tessera (schede del server al posto
  delle tessere, il gesto indietro); la spunta manda il tocco giusto all'ingresso, resta in attesa,
  si aggiorna con la lista del tool, un rifiuto (evento «tocco») o un 409 lo dice accanto;
- modulo da compilare: si apre da solo nel suo strato, controlli mentre si scrive, «Invia»,
  «Compila» in Adesso sotto «Aspetta te»; «Scrivi» apre la casella col fuoco, la frase arriva e
  lo strato si chiude; Io ha prova del microfono, schermo acceso, certificato, «dimentica»;
- misure a 375×812, 320×568, 812×375 con 0 e 6 schede, microfono spento, «Penso…», acceso, in
  ogni sezione e in auto: tutto in uno schermo (la sezione scorre da sé), niente testo fuori dai
  contenitori, schede dentro la sezione, contrasto AA, tocchi ≥ 44 px (≥ 64 in auto), in auto col
  microfono acceso «Parla» più basso e la risposta più alta; modulo e casella aperti: niente di
  lato, tasti ≥ 64 px (CALLIOPE_FOTO=<cartella> per gli screenshot);
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


# La Screen Wake Lock API finta, come WebKit: gesto in corso per la prima richiesta.
# Page.addScriptToEvaluateOnNewDocument la mette in OGNI riquadro dello stesso processo, anche
# nel gioco (<iframe sandbox="allow-scripts">, origine opaca), dove leggere localStorage è un
# SecurityError. Chromium isola di solito i riquadri sandbox in un altro processo, e lì lo script
# non arriva; sotto carico (troppi processi) li tiene nello stesso, e la prova falliva con
# «nessun errore JavaScript» (12/10, riprodotto con --disable-features=IsolateSandboxedIframes).
# Solo la pagina in cima, e localStorage protetto
FINTA = r"""(() => {
  if (window.top !== window) return;
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
  let assente = false;
  try { assente = localStorage.getItem("__wl_assente") === "1"; } catch (e) { /* niente */ }
  if (assente) { delete Navigator.prototype.wakeLock; return; }
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
                   f" if (!e.closest('#vista') || e.closest('.sezione')) e.scrollIntoView({{block: 'nearest'}});"
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
    t.tocca_sel('#barra a[data-sezione="io"]')
    verifica("Io: si apre dalla barra (#/io)", bool(aspetta(lambda: t.v(
        "location.hash === '#/io' && !document.getElementById('sez-io').hidden"), 2)))
    t.tocca("schermo-tieni")
    ok = aspetta(lambda: t.wl().get("n") == 0 and not t.schermo().get("tieni"), 3)
    ind = t.indicatore()
    verifica("opzione spenta: schermo lasciato e avviso che può spegnersi", bool(ok)
             and "smetterà di ascoltare" in ind.get("testo", "") and t.mic(), ind.get("testo", "")[:80])
    verifica("opzione salvata", t.v("localStorage.getItem('calliope.telefono.schermo_acceso')") == "0")
    t.tocca("schermo-tieni")
    ok = aspetta(lambda: t.wl().get("n") == 1 and t.schermo().get("stato") == "acceso", 3)
    verifica("opzione riaccesa: schermo di nuovo tenuto acceso", bool(ok))
    t.v("history.back(); 1")
    verifica("Io: il gesto indietro torna ad Adesso", bool(aspetta(lambda: t.v(
        "location.hash === '#/adesso' && document.getElementById('sez-io').hidden"
        " && !document.getElementById('sez-adesso').hidden"), 2)))

    # 7. la vista (27/10: a sezioni; la vista da guida è la modalità In auto)
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
        vecchi: ['guida', 'guida-apri', 'guida-esci', 'voce-tel', 'principale', 'cronologia', 'menu', 'menu-apri',
                 'carosello', 'binario', 'punti'].filter((id) => document.getElementById(id)),
        parla: document.getElementById('parla').getBoundingClientRect().height,
        mic: document.getElementById('microfono').getAttribute('aria-checked'),
        acceso: vista.classList.contains('mic-acceso'),
      };
    })()""") or {}
    verifica("vista: fondo nero, niente vista normale, menu né carosello",
             g.get("sfondo") == "rgb(0, 0, 0)" and g.get("body") == "rgb(0, 0, 0)" and g.get("vecchi") == [],
             json.dumps(g.get("vecchi")))
    verifica("vista: nessuna animazione (anche nello stato «ascolto»)", g.get("anim") == [], json.dumps(g.get("anim")))
    verifica("vista: l'ultima risposta intera in Adesso (le frasi del turno)",
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


def sezioni(t: Tel, hub):
    """Le schede nelle sezioni (27/10): ognuna nella sua raccolta, quelle vive anche in Adesso,
    aggiornate al loro posto; l'ultima risposta; le novità sulla barra; il router; In auto."""
    T = "window.calliopeTelefono"
    ok = aspetta(lambda: hub.collegati(), 10)
    verifica("schede: il telefono è collegato anche come schermo", bool(ok))
    S = schede_prova()
    for k in ("lista", "timer", "esecuzione", "documento"):
        tutti(hub, S[k])
        time.sleep(0.15)
    chiavi = ["documento:5", "esecuzione:7", S["timer"]["chiave"], "lista:spesa"]
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("adesso/corso") == chiavi, 5)
    c = t.v(f"{T}.sezioni()") or {}
    p = c.get("posti", {})
    verifica("sezioni: ogni scheda nella sua raccolta di Le mie cose (liste, agenda, lavori, documenti)",
             p.get("cose/liste") == ["lista:spesa"] and p.get("cose/agenda") == [S["timer"]["chiave"]]
             and p.get("cose/lavori") == ["esecuzione:7"] and p.get("cose/documenti") == ["documento:5"],
             json.dumps(p)[:300])
    verifica("sezioni: le quattro vive anche in Adesso, la più recente per prima",
             bool(ok) and c.get("sezione") == "adesso", json.dumps(p.get("adesso/corso")))
    verifica("sezioni: niente novità per ciò che si vede già in Adesso", c.get("novita", {}).get("cose") == 0,
             json.dumps(c.get("novita")))
    gruppi = t.v("[...document.querySelectorAll('#sez-cose .raccolta')].filter((r) => !r.hidden)"
                 ".map((r) => r.dataset.raccolta)") or []
    verifica("sezioni: in Le mie cose solo le raccolte con qualcosa", gruppi == ["liste", "agenda", "lavori", "documenti"],
             json.dumps(gruppi))
    # aggiornamento al suo posto: stesso elemento in Le mie cose e in Adesso, ordine uguale
    t.v("window.__el = document.querySelector('#sez-cose [data-chiave=\"esecuzione:7\"]');"
        " window.__el2 = document.querySelector('#sez-adesso [data-chiave=\"esecuzione:7\"]'); 1")
    from calliope.schermi import schede
    righe = [{"tipo": "out", "testo": f"riga {i}\n"} for i in range(20)]
    tutti(hub, schede.esecuzione("Conta le parole", "conta.py", "python", "in_corso", [], righe, 0, None,
                                 time.time() - 5, 5.0, 60, ident=7, sposta=False))
    ok = aspetta(lambda: t.v("(document.querySelector('#sez-cose [data-chiave=\"esecuzione:7\"] pre')||{}).textContent||''")
                 .count("riga") == 20, 5)
    c2 = t.v(f"{T}.sezioni()") or {}
    verifica("sezioni: scheda aggiornata al suo posto (stessi elementi, stesso ordine)",
             bool(ok) and t.v("window.__el === document.querySelector('#sez-cose [data-chiave=\"esecuzione:7\"]')"
                              " && window.__el2 === document.querySelector('#sez-adesso [data-chiave=\"esecuzione:7\"]')")
             and c2.get("posti", {}).get("adesso/corso") == chiavi, json.dumps(c2.get("posti", {}).get("adesso/corso")))
    timer = t.v("(document.querySelector('#sez-adesso .tipo-timer .resto')||{}).textContent||''") or ""
    verifica("sezioni: il timer conta in Adesso", ":" in timer, timer)
    # il timer scaduto non è più vivo: esce da Adesso, resta in Agenda
    scaduto = dict(schede.timer({"id": 4, "label": "per la pasta", "due": time.time() - 1}, "scaduto"),
                   chiave=S["timer"]["chiave"])
    tutti(hub, scaduto)
    ok = aspetta(lambda: S["timer"]["chiave"] not in (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("adesso/corso", []), 5)
    c3 = t.v(f"{T}.sezioni()") or {}
    verifica("sezioni: il timer scaduto esce da Adesso e resta in Agenda",
             bool(ok) and c3.get("posti", {}).get("cose/agenda") == [S["timer"]["chiave"]], json.dumps(c3.get("posti"))[:300])
    # la risposta del turno e il calcolo: l'ultima risposta in Adesso, il calcolo anche in Conversazione
    t.v(f"{T}.comando({{tipo: 'frase', turno: 30, id: 300, testo: 'Fa 102.', rate: 22050, byte: 0}}); 1")
    calc = schede.calcolo("17 × 6", "102")
    tutti(hub, calc)
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("adesso/risposta") == [calc["id"]], 5)
    c4 = t.v(f"{T}.sezioni()") or {}
    verifica("sezioni: il calcolo è l'ultima risposta (in Adesso sotto il testo) e sta in Conversazione",
             bool(ok) and c4.get("posti", {}).get("conversazione") == [calc["id"]]
             and t.v("document.getElementById('risposta-testo').textContent") == "Fa 102.", json.dumps(c4.get("posti"))[:300])
    # le novità: una scheda della conversazione arrivata mentre si guarda Io; guardando si tolgono
    t.tocca_sel('#barra a[data-sezione="io"]')
    aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("sezione") == "io", 2)
    tutti(hub, schede.testo("Da leggere", "Un testo da leggere con calma.", schede.PUBBLICA))
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("novita", {}).get("conversazione") == 1, 5)
    segno = t.v("(() => { const b = document.querySelector('#barra a[data-sezione=\"conversazione\"] .novita');"
                " return !b.hidden && b.textContent; })()")
    verifica("novità: il pallino col numero su Conversazione", bool(ok) and segno == "1", str(segno))
    t.tocca_sel('#barra a[data-sezione="conversazione"]')
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("novita", {}).get("conversazione") == 0
                 and t.v("document.querySelector('#barra a[data-sezione=\"conversazione\"] .novita').hidden"), 3)
    verifica("novità: guardando la sezione si tolgono", bool(ok))
    # il router: un indirizzo per raccolta, uno sconosciuto torna ad Adesso, il gesto indietro
    t.v(f"{T}.vai('#/cose/lavori'); 1")
    ok = aspetta(lambda: t.v("location.hash === '#/cose/lavori' && !document.getElementById('sez-cose').hidden"), 2)
    verifica("router: #/cose/lavori apre Le mie cose", bool(ok))
    t.v("history.back(); 1")
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("sezione") == "conversazione", 2)
    verifica("router: il gesto indietro torna alla sezione di prima", bool(ok))
    t.v("location.hash = '#/boh'; 1")
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("sezione") == "adesso", 2)
    verifica("router: un indirizzo sconosciuto è Adesso", bool(ok))
    t.v(f"{T}.vai('#/adesso'); 1")
    titolo = t.v("document.getElementById('sez-titolo').textContent")
    verifica("router: il titolo è quello della sezione", titolo == "Adesso", titolo)
    # In auto: a mano, niente barra, salvata; «Esci» torna ad Adesso
    t.tocca("auto-apri")
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("modo") == "auto", 2)
    a = t.v("({barra: getComputedStyle(document.getElementById('barra')).display,"
            " salvata: localStorage.getItem('calliope.telefono.auto'),"
            " esci: !document.getElementById('auto-esci').hidden,"
            " altre: [...document.querySelectorAll('#sezioni .pagina-car')].filter((e) => e.getClientRects().length && e.id !== 'risposta').length})") or {}
    verifica("In auto: a mano, niente barra né schede, solo la risposta; salvata",
             bool(ok) and a.get("barra") == "none" and a.get("salvata") == "1" and a.get("esci") and a.get("altre") == 0,
             json.dumps(a))
    t.tocca("auto-esci")
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("modo") == "sezioni"
                 and t.v("localStorage.getItem('calliope.telefono.auto')") is None, 2)
    verifica("In auto: «Esci» torna alle sezioni", bool(ok))
    aspetto(t, hub)
    nascoste(t, hub)


ACCENTO = "getComputedStyle(document.documentElement).getPropertyValue('--accento').trim()"


def aspetto(t: Tel, hub):
    """Io › Aspetto (27/10, passo 1c): lilla di serie, le scelte dal server, un tocco cambia
    l'accento (variabile CSS, scelta segnata), salvata per la persona."""
    T = "window.calliopeTelefono"
    t.tocca_sel('#barra a[data-sezione="io"]')
    # Io visibile prima di toccare «Rosa» (revisione della PR #254: con Io ancora nascosta il tocco
    # finiva su (0, 0) e la prova cadeva a caso)
    aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("sezione") == "io"
            and t.v("!document.getElementById('sez-io').hidden"), 3)
    ok = aspetta(lambda: t.v("document.querySelectorAll('#accenti .accento-scelta').length") >= 3, 3)
    a = t.v("({accento: " + ACCENTO + ", segnata: (document.querySelector('#accenti [aria-pressed=\"true\"]')||{dataset: {}}).dataset.accento || '',"
            " nomi: [...document.querySelectorAll('#accenti .accento-scelta')].map((b) => b.textContent)})") or {}
    verifica("Aspetto: in Io le scelte con il nome, il lilla di serie segnato",
             bool(ok) and a.get("accento") == "#b9a3e3" and a.get("segnata") == "lilla"
             and "Lilla" in (a.get("nomi") or []), json.dumps(a))
    t.tocca_sel('#accenti [data-accento="rosa"]')
    ok = aspetta(lambda: t.v(ACCENTO) == "#e8a6c8"
                 and t.v("document.querySelector('#accenti [data-accento=\"rosa\"]').getAttribute('aria-pressed')") == "true", 3)
    verifica("Aspetto: un tocco su «Rosa» cambia l'accento della pagina e lo segna", bool(ok),
             f"{t.v(ACCENTO)} esito «{t.v('document.getElementById(\"accento-esito\").textContent')}»"
             f" {t.v('JSON.stringify(window.calliopeSchermo.aspetto())')[:120]}")
    verifica("Aspetto: salvato per la persona sul server", hub.aspetto.accento("dario") == "rosa",
             hub.aspetto.accento("dario"))
    barra = t.v("getComputedStyle(document.querySelector('#barra a[aria-current]')).color")
    verifica("Aspetto: la sezione aperta nella barra col nuovo accento", barra == "rgb(232, 166, 200)", barra)
    t.tocca_sel('#accenti [data-accento="lilla"]')
    aspetta(lambda: t.v(ACCENTO) == "#b9a3e3", 3)
    t.v(f"{T}.vai('#/adesso'); 1")


def nascoste(t: Tel, hub):
    """Le sezioni nascoste sul telefono di un minore (27/10, passo 1c): la barra perde Casa,
    #/casa porta ad Adesso, una scheda della casa va in Conversazione; tolte, tutto torna."""
    T = "window.calliopeTelefono"
    from calliope.schermi import schede
    evento = "document.dispatchEvent(new CustomEvent('calliope:nascoste', {detail: %s})); 1"
    t.v(evento % json.dumps({"sezioni": ["casa"], "raccolte": ["ufficio"]}))
    tutti(hub, schede.nuova("casa", "Cucina", schede.CASA, chiave="casa:cucina",
                            righe=[{"nome": "Luce cucina", "stato": "accesa", "acceso": True}]))
    ok = aspetta(lambda: "casa:cucina" in (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("conversazione", []), 5)
    n = t.v("({casa: getComputedStyle(document.querySelector('#barra a[data-sezione=\"casa\"]')).display,"
            " voci: [...document.querySelectorAll('#barra a')].filter((a) => getComputedStyle(a).display !== 'none').length})") or {}
    verifica("minore: niente Casa nella barra (4 voci), la scheda della casa in Conversazione",
             bool(ok) and n.get("casa") == "none" and n.get("voci") == 4, json.dumps(n))
    t.v("location.hash = '#/casa'; 1")
    ok = aspetta(lambda: (t.v(f"{T}.sezioni()") or {}).get("sezione") == "adesso", 2)
    verifica("minore: #/casa porta ad Adesso", bool(ok))
    t.v(evento % json.dumps({"sezioni": [], "raccolte": []}))
    ok = aspetta(lambda: "casa:cucina" in (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("casa", []), 3)
    verifica("tolte le sezioni nascoste: Casa torna, con la sua scheda", bool(ok)
             and t.v("document.querySelectorAll('#barra a').length") == 5
             and t.v("getComputedStyle(document.querySelector('#barra a[data-sezione=\"casa\"]')).display") != "none")


def prepara_raccolte(cfg, hub, cartella: Path):
    """Le tessere e la pagina Liste (28/10, passo 2a): le liste di casa su disco e il profilo di
    chi ha il telefono (amministra: anche la tessera Ufficio); gli altri servizi mancano."""
    import types
    from calliope.liste import Liste
    from calliope.tools.spec import ToolContext
    liste = Liste(str(cartella / "liste.db"))
    liste.add("spesa", ["latte", "uova", "pane", "pomodori", "caffè"], "Dario")
    hub.profilo = lambda pid: (types.SimpleNamespace(id="dario", name="Dario", admin=True, nascita=None, fascia=None)
                               if pid == "dario" else None)
    hub.tool_ctx = ToolContext(cfg=cfg, speakers=None, speaker_ctx=None, speaker=None, liste=liste)
    return liste


def raccolte(t: Tel, hub, liste):
    """Le mie cose (28/10, passo 2a): le tessere coi conti dai servizi e il pallino; la pagina
    Liste dalla tessera (le schede dal server, il gesto indietro); la spunta manda il tocco giusto,
    resta in attesa, si aggiorna con la lista che manda il tool, e un rifiuto si dice accanto."""
    from calliope.schermi import schede
    T = "window.calliopeTelefono"
    S = f"({T}.sezioni() || {{}})"
    t.v(f"{T}.vai('#/cose'); 1")
    ok = aspetta(lambda: len(t.v(f"{S}.tessere") or []) == 8, 5)
    tes = {x["id"]: x for x in t.v(f"{S}.tessere") or []}
    verifica("raccolte: otto tessere in cima a Le mie cose (Ufficio per chi amministra)",
             bool(ok) and list(tes) == ["liste", "agenda", "lavori", "cassetto", "documenti", "giochi", "studio", "ufficio"]
             and t.v("document.getElementById('sez-cose').firstElementChild.id === 'tessere'"), json.dumps(tes)[:300])
    verifica("raccolte: la tessera Liste col conto vero, senza pallino alla prima visita",
             tes.get("liste", {}).get("conto") == "1" and not tes.get("liste", {}).get("novita"), json.dumps(tes.get("liste")))
    stato = t.v("document.querySelector('#tessere [data-tessera=\"agenda\"] .tessera-stato').textContent")
    verifica("raccolte: un servizio che manca dice «non disponibile» e la pagina «presto»",
             tes.get("agenda", {}).get("conto") == "—" and "non disponibile" in stato and "presto" in stato, stato)
    colonne = t.v("getComputedStyle(document.getElementById('tessere')).gridTemplateColumns.split(' ').length")
    verifica("raccolte: due colonne sul telefono", colonne == 2, str(colonne))
    # Un cambiamento della lista dopo la visita: il pallino
    time.sleep(1.1)                              # «created» ha i secondi interi
    liste.add("spesa", ["burro"], "Bianca")
    t.v(f"{T}.aggiornaRaccolte(); 1")
    ok = aspetta(lambda: any(x["id"] == "liste" and x["novita"] for x in t.v(f"{S}.tessere") or []), 5)
    etichetta = t.v("document.querySelector('#tessere [data-tessera=\"liste\"]').getAttribute('aria-label')") or ""
    verifica("raccolte: il pallino sulla tessera cambiata, detto anche a chi non vede", bool(ok) and "novità" in etichetta,
             etichetta)
    # La pagina Liste dalla tessera
    t.tocca_sel('#tessere [data-tessera="liste"]')
    ok = aspetta(lambda: t.v("location.hash") == "#/cose/liste" and t.v(f"{S}.vistaCose") == "pagina"
                 and t.v(f"{S}.pagina") == ["lista:spesa"], 5)
    v = t.v("({titolo: document.getElementById('pagina-titolo').textContent,"
            " tessere: getComputedStyle(document.getElementById('tessere')).display,"
            " gruppo: getComputedStyle(document.querySelector('#sez-cose .raccolta[data-raccolta=\"liste\"]')).display})") or {}
    verifica("pagina Liste: dalla tessera, con la lista del server, al posto delle tessere e dei gruppi",
             bool(ok) and v.get("titolo") == "Liste" and v.get("tessere") == "none" and v.get("gruppo") == "none",
             json.dumps(v))
    verifica("pagina Liste: guardata, il pallino si toglie",
             not any(x["id"] == "liste" and x["novita"] for x in t.v(f"{S}.tessere") or []))
    spunte = t.v("[...document.querySelectorAll('#pagina-schede button.spunta')].map((b) => [b.dataset.voce,"
                 " b.getAttribute('role'), b.getAttribute('aria-checked'), Math.round(b.getBoundingClientRect().height)])") or []
    verifica("spunta: ogni voce è un tasto «checkbox» non spuntato, alto ≥ 44 px",
             [s[0] for s in spunte] == ["latte", "uova", "pane", "pomodori", "caffè", "burro"]
             and all(s[1] == "checkbox" and s[2] == "false" and s[3] >= 44 for s in spunte), json.dumps(spunte))
    verifica("spunta: la regione per l'esito c'è già (role=status)",
             t.v("!!document.querySelector('#pagina-schede .esito-tocco[role=\"status\"]')"))
    while hub.ingresso.prendi() is not None:
        pass
    t.tocca_sel('#pagina-schede button.spunta[data-voce="latte"]')
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() or {}
    verifica("spunta: il tocco giusto nell'ingresso (lista_togli col latte, a nome di chi ha il telefono)",
             bool(ok) and item.get("tipo") == "tocco" and item.get("tool") == "lista_togli"
             and item.get("argomenti") == {"cose": "latte", "lista": "spesa"} and item.get("persona") == "dario"
             and item.get("pagina") == {"lista": "spesa", "voce": "latte"}, json.dumps(item, ensure_ascii=False)[:300])
    b = t.v("(() => { const b = document.querySelector('#pagina-schede button.spunta[data-voce=\"latte\"]');"
            " return {c: b.getAttribute('aria-checked'), busy: b.getAttribute('aria-busy'),"
            " esito: b.closest('.scheda').querySelector('.esito-tocco').textContent}; })()") or {}
    verifica("spunta: la voce resta segnata in attesa, detto nella regione di stato",
             b.get("c") == "true" and b.get("busy") == "true" and "latte" in (b.get("esito") or ""), json.dumps(b))
    # Il ciclo (qui finto): la voce tolta, la lista aggiornata dal tool e l'esito allo schermo
    liste.remove("spesa", ["latte"])
    tutti(hub, schede.lista("spesa", liste.read("spesa")[1], tolti=["latte"]))
    hub.evento_a(item["schermo_id"], "tocco", {"tocco": "spunta_lista", "ok": True, "pagina": item["pagina"]})
    ok = aspetta(lambda: t.v("[...document.querySelectorAll('#pagina-schede button.spunta')].map((b) => b.dataset.voce)")
                 == ["uova", "pane", "pomodori", "caffè", "burro"]
                 and t.v("document.querySelector('#pagina-schede .esito-tocco').textContent") == "", 5)
    verifica("spunta: la lista aggiornata dal tool sostituisce quella della pagina, al suo posto", bool(ok))
    # Un rifiuto dal ciclo (evento «tocco»): la voce torna com'era, il motivo accanto
    t.tocca_sel('#pagina-schede button.spunta[data-voce="uova"]')
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() or {}
    hub.evento_a(item.get("schermo_id"), "tocco", {"tocco": "spunta_lista", "ok": False,
                                                    "errore": "Non hai il permesso per farlo.", "pagina": item.get("pagina")})
    ok = aspetta(lambda: t.v("(() => { const b = document.querySelector('#pagina-schede button.spunta[data-voce=\"uova\"]');"
                             " return b.getAttribute('aria-checked') === 'false' && !b.hasAttribute('aria-busy')"
                             " && b.closest('.scheda').querySelector('.esito-tocco').textContent === 'Non hai il permesso per farlo.'; })()"), 5)
    verifica("spunta: un rifiuto del ciclo la toglie e lo dice accanto", bool(ok))
    # Un errore HTTP (la voce tolta nel frattempo da un'altra parte): 409 col motivo
    liste.remove("spesa", ["pane"])
    t.tocca_sel('#pagina-schede button.spunta[data-voce="pane"]')
    ok = aspetta(lambda: t.v("(() => { const b = document.querySelector('#pagina-schede button.spunta[data-voce=\"pane\"]');"
                             " return b.getAttribute('aria-checked') === 'false'"
                             " && b.closest('.scheda').querySelector('.esito-tocco').textContent.includes('non c\\'è più'); })()"), 5)
    verifica("spunta: una voce che non c'è più (409) torna com'era, col motivo", bool(ok) and hub.ingresso.vuoto(),
             t.v("document.querySelector('#pagina-schede .esito-tocco').textContent"))
    # Riuscito senza la lista aggiornata (SSE perso, schede automatiche spente in un hub vecchio):
    # la voce resta spuntata e non si ritocca, invece di tornare libera
    sel = lambda v: f"document.querySelector('#pagina-schede button.spunta[data-voce=\"{v}\"]')"  # noqa: E731
    t.tocca_sel('#pagina-schede button.spunta[data-voce="pomodori"]')
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() or {}
    hub.evento_a(item.get("schermo_id"), "tocco", {"tocco": "spunta_lista", "ok": True, "pagina": item.get("pagina")})
    ok = aspetta(lambda: t.v(f"{sel('pomodori')}.getAttribute('aria-disabled') === 'true'"
                             f" && {sel('pomodori')}.getAttribute('aria-checked') === 'true'"
                             f" && !{sel('pomodori')}.hasAttribute('aria-busy')"), 5)
    verifica("spunta: riuscita senza la lista nuova, la voce resta spuntata (non torna libera)", bool(ok))
    # Una lista più recente che contiene ancora la voce («rimettilo» a voce): si tocca di nuovo
    tutti(hub, schede.lista("spesa", liste.read("spesa")[1]))
    ok = aspetta(lambda: t.v(f"{sel('pomodori')}.getAttribute('aria-checked') === 'false'"
                             f" && !{sel('pomodori')}.hasAttribute('aria-disabled')"), 5)
    verifica("spunta: la voce rimessa in una lista nuova si tocca di nuovo", bool(ok))
    # Nessun esito entro l'attesa (un turno a voce in corso): la pagina lo dice com'è, e un
    # secondo tocco della stessa voce non rimanda niente
    t.v("window.calliopeSchermo.spunta.attesaMs = 1500; 1")
    t.tocca_sel('#pagina-schede button.spunta[data-voce="caffè"]')
    aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() or {}
    esito = f"{sel('caffè')}.closest('.scheda').querySelector('.esito-tocco').textContent"
    ok = aspetta(lambda: "occupata" in (t.v(esito) or "") and t.v(f"{sel('caffè')}.getAttribute('aria-checked')") == "true", 5)
    verifica("spunta: senza esito la pagina dice che Calliope è occupata (il tocco è in coda)", bool(ok), t.v(esito))
    t.tocca_sel('#pagina-schede button.spunta[data-voce="caffè"]')
    time.sleep(0.5)
    verifica("spunta: un secondo tocco della stessa voce non rimanda il tocco", hub.ingresso.vuoto()
             and "occupata" in (t.v(esito) or ""))
    hub.evento_a(item.get("schermo_id"), "tocco", {"tocco": "spunta_lista", "ok": True, "pagina": item.get("pagina")})
    ok = aspetta(lambda: t.v(f"{sel('caffè')}.getAttribute('aria-disabled')") == "true" and t.v(esito) == "", 5)
    verifica("spunta: l'esito che arriva dopo chiude l'attesa", bool(ok))
    t.v("window.calliopeSchermo.spunta.attesaMs = 30000; 1")
    # Il gesto indietro torna alle tessere; una tessera senza pagina porta al suo gruppo
    t.v("history.back(); 1")
    ok = aspetta(lambda: t.v("location.hash") == "#/cose" and t.v(f"{S}.vistaCose") == "tessere"
                 and t.v("getComputedStyle(document.getElementById('tessere')).display") != "none", 3)
    verifica("pagina Liste: il gesto indietro torna alle tessere", bool(ok))
    t.tocca_sel('#tessere [data-tessera="agenda"]')
    ok = aspetta(lambda: t.v("location.hash") == "#/cose/agenda" and t.v(f"{S}.vistaCose") == "tessere", 3)
    verifica("raccolte: una tessera senza pagina resta sulle tessere e porta al suo gruppo", bool(ok))
    # Una scheda della lista da Adesso («Apri») porta alla pagina, con la scheda in vista
    t.v(f"{T}.vaiA('lista:spesa'); 1")
    ok = aspetta(lambda: t.v("location.hash") == "#/cose/liste/lista%3Aspesa" and t.v(f"{S}.vistaCose") == "pagina", 3)
    verifica("raccolte: la scheda della lista porta alla pagina Liste", bool(ok), t.v("location.hash"))
    t.v(f"{T}.vai('#/adesso'); 1")


def modulo_e_scrivi(t: Tel, hub):
    """Il modulo da compilare si apre da solo in uno strato; la casella per scrivere si apre
    da «Scrivi»; Io ha tutto il resto."""
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
    verifica("modulo: in Adesso sotto «Aspetta te» c'è la sua scheda con «Compila»",
             bool(t.v("!!document.querySelector('#sez-adesso [data-posto=\"adesso/aspetta\"] .modulo-car .apri-modulo')"
                      " && !document.querySelector('#sez-adesso h2[data-gruppo=\"aspetta\"]').hidden")))
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
    # Io: tutto il resto
    t.tocca_sel('#barra a[data-sezione="io"]')
    aspetta(lambda: t.v("!document.getElementById('sez-io').hidden"), 2)
    m = t.v("""(() => { const m = document.getElementById('sez-io'); const q = (s) => m.querySelector(s);
      return {aperto: !m.hidden, diag: !!q('#diag-prova'), tieni: !!q('#schermo-tieni'), ca: !!q('#link-ca'),
              dimentica: !!q('#dimentica'), auto: !!q('#auto-io'), stato: (q('#tel-collegamento-testo')||{}).textContent,
              schede: (q('#stato-testo')||{}).textContent}; })()""") or {}
    verifica("Io: prova del microfono, schermo acceso, In auto, certificato, dimentica, collegamento",
             m.get("aperto") and m.get("diag") and m.get("tieni") and m.get("ca") and m.get("dimentica") and m.get("auto")
             and m.get("stato") == "collegata" and m.get("schede") == "collegato", json.dumps(m))
    t.tocca_sel('#barra a[data-sezione="adesso"]')
    verifica("Io: la barra torna ad Adesso", bool(aspetta(lambda: t.v("document.getElementById('sez-io').hidden"), 2)))


# Misure della vista (04/10, a sezioni dal 27/10): per ogni dimensione, stato e sezione la pagina
# non scorre (scorre la sezione), nessun testo fuori dal suo contenitore, parti che non si
# sovrappongono, schede dentro la sezione, tocchi ≥ 44 px (≥ 64 in auto), contrasto AA. Con
# CALLIOPE_FOTO=<cartella> salva anche gli screenshot.
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
  // il testo solo per i lettori (ritagliato a 1 px: la parola sotto un'icona) non si vede
  const nascosto = (n) => { for (let e = n.parentElement; e; e = e.parentElement) {
    const cs = getComputedStyle(e); if (cs.clip !== 'auto' && cs.position === 'absolute') return true; } return false; };
  const testiDentro = (e, r, solo_x) => {
    const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (!n.textContent.trim() || nascosto(n)) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const q of rg.getClientRects()) {
        const ok = solo_x ? q.left >= r.left - 1 && q.right <= r.right + 1 : dentro(q, r);
        if (!ok) fuori.push(nome(e) + ': «' + n.textContent.trim().slice(0, 20) + '» esce');
      }
    }
  };
  const auto = g.dataset.modo === 'auto';
  // contenitori il cui testo deve starci tutto
  const scatole = ['tel-voce', 'tel-dove', 'avviso-tel', 'schermo-avviso', 'parla', 'microfono', 'scrivi-apri',
    'foto-apri', 'auto-apri', 'auto-esci', 'sez-titolo'].map((id) => document.getElementById(id))
    .concat([...document.querySelectorAll('#barra a')]).filter(vis);
  for (const e of scatole) {
    if (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1) fuori.push(nome(e) + ' trabocca');
    const r = e.getBoundingClientRect();
    if (!dentro(r, gr)) fuori.push(nome(e) + ' fuori dalla vista');
    testiDentro(e, r, false);
  }
  // le schede: dentro la sezione di lato, niente testo fuori di lato (in verticale scorre la sezione)
  const sez = [...document.querySelectorAll('#sezioni .sezione')].find(vis);
  const br = sez.getBoundingClientRect();
  const pagine = [...sez.querySelectorAll('.pagina-car')].filter(vis);
  const inVista = [];
  for (const p of pagine) {
    const r = p.getBoundingClientRect();
    if (r.left < br.left - 1 || r.right > br.right + 1) fuori.push(p.dataset.chiave + ' esce dalla sezione di lato');
    if (p.scrollWidth > p.clientWidth + 1) fuori.push(p.dataset.chiave + ' trabocca di lato');
    if (r.bottom > br.top && r.top < br.bottom) { inVista.push(p.dataset.chiave); testiDentro(p, r, true); }
  }
  const aree = ['.vista-testa', '#sezioni', '.voce-riga', '#barra']
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
  // ogni elemento con del testo proprio che si vede (nella sezione: dentro il suo riquadro)
  const conTesto = [...g.querySelectorAll('*')].filter(vis).filter((e) =>
    [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
    && (!e.closest('.sezione') || (() => { const r = e.getBoundingClientRect(); return r.bottom > br.top && r.top < br.bottom; })()));
  const bassi = conTesto.map((e) => [nome(e), contrasto(e)]).filter(([, c]) => c < 4.5)
    .map(([n, c]) => n + ' ' + c.toFixed(2));
  const tocchi = ['parla', 'microfono', 'scrivi-apri', 'foto-apri', 'auto-apri', 'auto-esci'].map((id) => document.getElementById(id))
    .concat([...document.querySelectorAll('#barra a, #tessere .tessera, #sezioni button.spunta, #pagina-indietro')]).filter(vis)
    .map((e) => e.getBoundingClientRect()).map((r) => Math.min(r.width, r.height));
  return {
    scorre: se.scrollHeight > H + 1 || se.scrollWidth > W + 1 || g.scrollHeight > g.clientHeight + 1,
    fuori, bassi, tocchi, H, W, auto, inVista,
    spazio: br.height, parla: document.getElementById('parla').getBoundingClientRect().height,
    voce: document.querySelector('#tel-voce .voce-testo').textContent,
    // quante righe prende lo stato (27/10, iPhone: andava a capo a ogni sillaba)
    voceRighe: (() => { const v = document.querySelector('#tel-voce .voce-testo'); const r = document.createRange();
      r.selectNodeContents(v); return new Set([...r.getClientRects()].map((q) => Math.round(q.top))).size; })(),
    dove: document.getElementById('tel-dove').hidden ? '' : document.getElementById('tel-dove').textContent,
    sezione: window.calliopeTelefono.sezioni().sezione,
  };
})()"""

# Gli strati (modulo, scrivi): lo strato scorre da sé, i suoi tasti ≥ 64 px, niente di lato
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


def misure(t, etichetta):
    """La vista nelle tre dimensioni: in Adesso e in auto col microfono spento (il posto è dello
    studio), mentre pensa e col microfono acceso; le altre sezioni col microfono spento."""
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

    def misura(d, parola, minimo):
        ok = aspetta(lambda: (t.v(MISURA) or {}).get("voce") == parola, 2)
        time.sleep(0.35)                     # la dissolvenza si decide al giro dopo
        m = t.v(MISURA) or {}
        verifica(f"{d}: tutto in uno schermo, la pagina non scorre",
                 bool(ok) and not m.get("scorre"), f"{m.get('W')}×{m.get('H')}")
        verifica(f"{d}: nessun testo fuori dai contenitori, parti separate, schede nella sezione",
                 not m.get("fuori"), "; ".join(m.get("fuori", []))[:240])
        verifica(f"{d}: contrasto AA e tocchi ≥ {minimo} px",
                 not m.get("bassi") and min(m.get("tocchi") or [0]) >= minimo,
                 f"{m.get('bassi')} {[round(x) for x in m.get('tocchi') or []]}")
        verifica(f"{d}: la sezione ha spazio (≥ 120 px)", m.get("spazio", 0) >= 120, f"{m.get('spazio', 0):.0f} px")
        verifica(f"{d}: lo stato della voce su al più due righe", m.get("voceRighe", 9) <= 2, str(m.get("voceRighe")))
        return m

    alti = {}
    for w, h, nome_d in DIMENSIONI:
        dimensione(t, w, h)
        for modo in ("sezioni", "auto"):
            t.v(f"{T}.impostaAuto({'true' if modo == 'auto' else 'false'}); 1")
            for nome_s, fai, parola, dove in stati:
                fai()
                d = f"{etichetta} {w}×{h} {'in auto' if modo == 'auto' else 'Adesso'} «{parola}»"
                m = misura(d, parola, 64 if modo == "auto" else 44)
                foto(t, f"telefono-{etichetta}-{nome_d}-{modo}-{nome_s}.png")
                if dove:
                    verifica(f"{d}: il microfono di un altro satellite in una riga piccola",
                             dove in m.get("dove", ""), m.get("dove"))
                alti[(nome_d, modo, nome_s)] = (m.get("parla", 0), m.get("spazio", 0))
            if h > w and modo == "auto":
                p_sp, c_sp = alti[(nome_d, modo, "spento")]
                p_ac, c_ac = alti[(nome_d, modo, "acceso")]
                verifica(f"{etichetta} {w}×{h} in auto: col microfono acceso «Parla» più basso e la risposta più alta",
                         p_ac < p_sp and c_ac > c_sp, f"Parla {p_sp:.0f} → {p_ac:.0f}, risposta {c_sp:.0f} → {c_ac:.0f}")
        t.v(f"{T}.impostaAuto(false); 1")
        spento()
        for sez in ("conversazione", "cose", "casa", "io"):
            t.v(f"{T}.vai('#/{sez}'); 1")
            m = misura(f"{etichetta} {w}×{h} {sez}", "Microfono spento", 44)
            foto(t, f"telefono-{etichetta}-{nome_d}-{sez}.png")
        t.v(f"{T}.vai('#/adesso'); 1")
    # Un font più largo (27/10: sull'iPhone il font di sistema è più largo di Segoe UI e
    # «Conversazione» usciva dalla sua voce della barra): Verdana, nelle sezioni, ai due telefoni
    t.v("document.documentElement.style.setProperty('font-family', 'Verdana, sans-serif'); "
        "document.body.style.fontFamily = 'Verdana, sans-serif'; 1")
    spento()
    for w, h, nome_d in DIMENSIONI[:2]:
        dimensione(t, w, h)
        largo = t.v("getComputedStyle(document.body).fontFamily")
        verifica(f"{w}×{h}: il font largo è applicato", "Verdana" in (largo or ""), largo)
        for sez in ("adesso", "conversazione", "cose", "io"):
            t.v(f"{T}.vai('#/{sez}'); 1")
            spento()
            misura(f"{etichetta} {w}×{h} {sez} col font largo", "Microfono spento", 44)
            foto(t, f"telefono-{etichetta}-{nome_d}-{sez}-font-largo.png")
            # la frase vista sull'iPhone: «Dormo · di' «Calliope»» col microfono acceso
            acceso()
            misura(f"{etichetta} {w}×{h} {sez} col font largo e «Dormo»", "Dormo · di' «Calliope»", 44)
    t.v("document.documentElement.style.removeProperty('font-family'); document.body.style.fontFamily = ''; 1")
    spento()
    t.v(f"{T}.vai('#/adesso'); 1")
    mic(False)
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


def una_per_una(t):
    """Ogni scheda nella sua sezione, portata in vista, a 375×812 e 320×568: dentro la sezione,
    niente testo fuori di lato, contrasto AA (le foto: una per tipo)."""
    T = "window.calliopeTelefono"
    for w, h, nome_d in DIMENSIONI[:2]:
        dimensione(t, w, h)
        posti = (t.v(f"{T}.sezioni()") or {}).get("posti", {})
        chiavi = [k for p, ks in posti.items() if not p.startswith("adesso") for k in ks]
        for k in chiavi:
            t.v(f"{T}.vaiA({json.dumps(k)}); 1")
            time.sleep(0.3)
            m = t.v(MISURA) or {}
            tipo = k.split(":")[0].strip("_")
            foto(t, f"telefono-scheda-{nome_d}-{tipo}.png")
            verifica(f"{nome_d} scheda {tipo}: in vista nella sua sezione, testo dentro, contrasto AA",
                     k in m.get("inVista", []) and not m.get("fuori") and not m.get("bassi") and not m.get("scorre"),
                     f"{m.get('sezione')} {m.get('inVista')} {m.get('fuori')} {m.get('bassi')}"[:240])
        t.v(f"{T}.vai('#/adesso'); 1")
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


def misure_strati(t, hub, spec):
    """Modulo aperto e casella per scrivere, nelle tre dimensioni (Io è una sezione: misure)."""
    from calliope.schermi import Mittente
    T = "window.calliopeTelefono"
    dario = Mittente(persona="dario", nome="Dario", livello="amministra", certo=True)
    hub.moduli.apri(dict(spec, chiave="prova2"), lambda v, tt: None, dario, "prova", "amministra")
    aspetta(lambda: t.v("!document.getElementById('strato-modulo').hidden"), 5)
    for w, h, nome_d in DIMENSIONI:
        dimensione(t, w, h)
        for id_, apri in (("strato-modulo", None), ("strato-scrivi", "scrivi-apri")):
            if apri:
                t.v(f"{T}.apriStrato({json.dumps(id_)}); document.activeElement.blur(); 1")
            else:
                t.v(f"{T}.apriModulo({T}.sezioni().modulo || [...document.querySelectorAll('#sezioni .modulo-car')]"
                    f".map((e) => e.dataset.chiave)[0]); document.activeElement.blur(); 1")
            time.sleep(0.2)
            m = t.v(f"({MISURA_STRATO})({json.dumps(id_)})") or {}
            foto(t, f"telefono-{nome_d}-{id_}.png")
            verifica(f"{nome_d} {id_}: aperto, niente di lato, tasti ≥ 64 px, la pagina sotto non scorre",
                     m.get("aperto") and not m.get("fuori") and not m.get("tocchi") and not m.get("pagina"),
                     json.dumps(m)[:200])
            t.v(f"{T}.chiudiStrato({json.dumps(id_)}); 1")
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


# La geometria della modalità gioco (11/10): la scheda e il riquadro rispetto alla finestra, i
# comandi sopra il gioco e se un tocco al centro di ✕ arriva proprio a ✕ (niente lo copre)
MISURA_GIOCO = r"""(() => {
  const a = document.querySelector('article.scheda-gioco.modo-gioco');
  const f = a && a.querySelector('iframe.riquadro-gioco');
  const r = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; };
  const ch = a && a.querySelector('.gioco-chiudi');
  const v = a && a.querySelector('.gioco-voce');
  let libero = false;
  if (ch) { const b = ch.getBoundingClientRect(); libero = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2) === ch; }
  const pr = a && a.querySelector('.gioco-prova-etichetta');
  return {
    W: innerWidth, H: innerHeight, articolo: r(a), riquadro: r(f), fissa: !!a && getComputedStyle(a).position === 'fixed',
    chiudi: r(ch), libero, voce: v && !v.hidden ? v.className : null, voceTesto: v ? v.textContent : '',
    prova: !!a && a.classList.contains('gioco-prova'), provaTesto: pr && getComputedStyle(pr).display !== 'none' ? pr.textContent : '',
    sfondo: a ? getComputedStyle(a).backgroundColor : '', body: document.body.classList.contains('in-modo-gioco'),
  };
})()"""


def pieno(m, margine=0.0):
    """La scheda copre tutta la finestra e il riquadro tutta la scheda (meno la cornice)."""
    a, f = m.get("articolo"), m.get("riquadro")
    if not a or not f:
        return False
    W, H = m["W"], m["H"]
    return (abs(a[0]) < 1 and abs(a[1]) < 1 and abs(a[2] - W) < 1 and abs(a[3] - H) < 1
            and f[2] >= W - 2 * margine - 2 and f[3] >= H - 2 * margine - 2)


def gioco(t: Tel, hub):
    """La modalità gioco sul telefono (11/10): un gioco che arriva prende tutta la finestra,
    il pallino segue lo stato del telefono ed è anche «Parla», ✕ chiude e «Riapri» rimette;
    il microfono resta acceso; la variante «collaudo» ("prova": true) ha la cornice e «PROVA».
    Il documento del gioco qui non esiste (il riquadro carica un 404): bastano la scheda e il
    riquadro, la prova vera dei giochi è prova_giochi_pagina."""
    from calliope.schermi import schede
    T = "window.calliopeTelefono"
    G = "window.calliopeSchermo.gioco()"
    dimensione(t, 390, 844)
    if not t.mic():
        t.tocca("microfono")
        aspetta(lambda: t.mic(), 5)
    mic_prima = t.mic()

    def carta(pid, **extra):
        return schede.nuova("gioco", "Memory", schede.PUBBLICA, durata_s=None, chiave=f"gioco:{pid}",
                            partita=pid, doc="/gioco/" + "x" * 24, condivisa=False, giocatori=1,
                            watchdog_s=6.0, **extra)

    def voce():
        return (t.v(MISURA_GIOCO) or {}).get("voce") or ""

    tutti(hub, carta("finta1"))
    ok = aspetta(lambda: (t.v(G) or {}).get("partita") == "finta1", 5)
    time.sleep(0.2)
    m = t.v(MISURA_GIOCO) or {}
    foto(t, "telefono-gioco.png")
    verifica("modalità gioco: il gioco arrivato prende tutta la finestra (scheda fissa, riquadro pieno)",
             bool(ok) and m.get("fissa") and pieno(m) and m.get("body"), json.dumps(m)[:300])
    verifica("modalità gioco: ✕ in alto, ≥ 44 px, niente lo copre",
             bool(m.get("chiudi")) and m["chiudi"][2] >= 44 and m["chiudi"][1] < 80 and m.get("libero"),
             json.dumps(m.get("chiudi")))
    verifica("modalità gioco: il microfono resta acceso entrando", mic_prima and t.mic())
    verifica("modalità gioco: la scheda sta in Le mie cose › Giochi (aperta da sola)",
             t.v("location.hash === '#/cose/giochi' && !!document.querySelector('#sez-cose [data-posto=\"cose/giochi\"] article.scheda-gioco')"))
    # il pallino segue lo stato di questo telefono
    t.v(f"{T}.st.pensa = true; {T}.st.attivo = true; 1")
    ok = aspetta(lambda: "pensa" in voce(), 2)
    verifica("modalità gioco: il pallino dice «penso» quando Calliope pensa", bool(ok), voce())
    t.v(f"{T}.st.pensa = false; {T}.st.L = null; 1")
    ok = aspetta(lambda: "dorme" in voce(), 2)
    m = t.v(MISURA_GIOCO) or {}
    verifica("modalità gioco: poi torna «dormo» (a disposizione, serve la wake word)",
             bool(ok) and m.get("voceTesto") == "dormo", f"{m.get('voce')} {m.get('voceTesto')}")
    # il pallino è anche «Parla»: un tocco apre la frase senza il nome
    t.tocca_sel("article.modo-gioco .gioco-voce")
    ok = aspetta(lambda: t.v(f"!!({T}.st.forza || {T}.st.reg)") or "ascolta" in voce(), 3)
    verifica("modalità gioco: toccare il pallino è come «Parla» (la frase comincia senza il nome)",
             bool(ok), voce())
    t.v(f"{T}.st.forza = false; 1")
    t.v(f"if ({T}.st.reg) {T}.st.reg.finisci = true; 1")
    time.sleep(0.5)
    # ✕ chiude: la scheda resta in Giochi con «Riapri», il microfono resta
    t.tocca_sel("article.modo-gioco .gioco-chiudi")
    ok = aspetta(lambda: not (t.v(G) or {}).get("partita"), 3)
    stato = t.v("(() => { const a = document.querySelector('#sez-cose article.scheda-gioco');"
                " return {riquadro: !!(a && a.querySelector('iframe')), riapri: !!(a && a.querySelector('.gioco-riapri')),"
                " fissa: !!a && getComputedStyle(a).position === 'fixed',"
                " body: document.body.classList.contains('in-modo-gioco')}; })()") or {}
    verifica("✕: modalità gioco chiusa, il riquadro sparisce, «Riapri» sulla scheda",
             bool(ok) and not stato.get("riquadro") and stato.get("riapri") and not stato.get("fissa")
             and not stato.get("body"), json.dumps(stato))
    verifica("✕: il microfono resta acceso", t.mic() == mic_prima)
    ok = aspetta(lambda: "gioco:finta1" not in (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("adesso/corso", []), 3)
    verifica("✕: il gioco chiuso esce da Adesso e resta in Giochi", bool(ok)
             and "gioco:finta1" in (t.v(f"{T}.sezioni()") or {}).get("posti", {}).get("cose/giochi", []))
    t.v(f"{T}.vaiA('gioco:finta1'); 1")
    t.tocca_sel("#sez-cose article.scheda-gioco .gioco-riapri")
    ok = aspetta(lambda: (t.v(G) or {}).get("partita") == "finta1", 3)
    m = t.v(MISURA_GIOCO) or {}
    verifica("«Riapri»: di nuovo a tutta la finestra", bool(ok) and pieno(m), json.dumps(m.get("articolo")))
    # la scheda vuota (schermo_mostra niente: «Calliope, chiudi il gioco») la chiude
    tutti(hub, schede.vuota())
    ok = aspetta(lambda: not (t.v(G) or {}).get("partita"), 3)
    verifica("«chiudi il gioco» a voce (scheda vuota): modalità gioco chiusa", bool(ok)
             and not t.v("document.body.classList.contains('in-modo-gioco')"))
    # la variante «collaudo»
    tutti(hub, carta("finta2", prova=True))
    ok = aspetta(lambda: (t.v(G) or {}).get("partita") == "finta2", 5)
    time.sleep(0.2)
    m = t.v(MISURA_GIOCO) or {}
    foto(t, "telefono-gioco-prova.png")
    verifica("collaudo: a tutta la finestra con la cornice arancio e «PROVA», ✕ e pallino",
             bool(ok) and pieno(m, 14) and m.get("prova") and m.get("provaTesto") == "PROVA"
             and m.get("sfondo") == "rgb(243, 154, 46)" and m.get("libero") and m.get("voce"),
             json.dumps(m)[:300])
    t.tocca_sel("article.modo-gioco .gioco-chiudi")
    aspetta(lambda: not (t.v(G) or {}).get("partita"), 3)
    verifica("dopo il gioco: modalità gioco chiusa, il microfono acceso",
             t.mic() == mic_prima and not t.v("document.body.classList.contains('in-modo-gioco')"))
    if t.mic():
        t.tocca("microfono")
        aspetta(lambda: not t.mic(), 3)
    t.p._chiama("Emulation.clearDeviceMetricsOverride")


def senza_api(t: Tel):
    T = "window.calliopeTelefono"
    t.v("localStorage.setItem('__wl_assente', '1'); 1")
    t.p._chiama("Page.reload")
    time.sleep(0.5)
    ok = aspetta(lambda: t.v(f"!!{T} && {T}.st.collegato"), 15)
    verifica("senza l'API: pagina ricaricata e collegata", bool(ok)
             and t.v("'wakeLock' in navigator") is False)
    # La cronologia ripresa al ricollegamento non è una novità (revisione della PR #252)
    aspetta(lambda: len([k for ks in (t.v(f"{T}.sezioni()") or {}).get("posti", {}).values() for k in ks]) > 3, 5)
    time.sleep(0.5)
    nov = (t.v(f"{T}.sezioni()") or {}).get("novita", {})
    verifica("ricaricata: le schede riprese dal server non accendono novità", nov and not any(nov.values()),
             json.dumps(nov))
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
        liste = prepara_raccolte(cfg, hub, TMP / "server")
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
            sezioni(t, hub)
            raccolte(t, hub, liste)
            misure(t, "schede")
            una_per_una(t)
            _, spec = modulo_e_scrivi(t, hub)
            compila(t, hub)
            misure_strati(t, hub, spec)
            gioco(t, hub)
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
