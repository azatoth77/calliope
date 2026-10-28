import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La cronologia delle schede per persona e la scheda «Conversazione» nella pagina vera
(08/10/2026, calliope/schermi/cronologia.py): Edge o Chromium senza finestra comandato con
DevTools (senza browser si salta), server degli schermi e dei satelliti veri su 127.0.0.1,
archivio delle conversazioni in una cartella temporanea.

- schede personali di Dario e turni della sua conversazione; poi il server **si riavvia**
  (hub, cronologia e server nuovi sulla stessa cartella e la stessa porta);
- la pagina aperta prima si ricollega da sola e non ha doppioni; uno schermo personale
  **nuovo** ritrova le schede (mai quella della stanza) e la conversazione: frasi dette e
  scritte con l'ora e il luogo, mai i turni di Bianca né degli ospiti; un turno nuovo arriva in
  fondo senza riscrivere quelli di prima, e la vista resta in fondo; «Scarica» la trascrizione;
- lo schermo di stanza non ha né il pulsante né le schede delle persone;
- «Pulisci» con due tocchi: le schede spariscono da tutti gli schermi personali di Dario;
- un altro riavvio con uno sviluppo aperto: lo schermo rientra subito nella vista dello sviluppo;
- telefono di Dario: la conversazione dentro la sezione Conversazione (28/10, #242): ora e canale
  (a voce, scritto, con un tocco), il tocco come gesto, le schede piccole dentro la risposta che
  aprono la copia del turno a schermo intero (senza spunta) e il rimando che porta alla sezione;
  Oggi, Ieri, Solo schede e la ricerca (anche con testo ostile, che resta testo); niente fuori di
  lato, contrasto AA e tocchi ≥ 44 px a 375×812 e 320×568; «Pulisci le mie schede» c'è;
- nessun errore JavaScript né violazione della CSP. Con CALLIOPE_FOTO=<cartella> salva gli
  screenshot. ~40 s.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import prova_cruscotto_pagina as PCP
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-cronologia-pagina-"))
# I file di «Scarica» in una cartella della prova, mai nei Download veri di chi la lancia (13/10)
SCARICATI = TMP / "scaricati"
ERRORI = []
SALTATA = 77
aspetta = PCP.aspetta
tocca = PCP.tocca
foto = PCP.foto


def pagina(exe, url, profilo, opzioni=()):
    """Una scheda del browser con i download nella cartella della prova (`SCARICATI/<profilo>`):
    senza, «Scarica» salvava il file nella cartella Download vera di chi lancia la prova. La
    cartella sta nelle preferenze del profilo temporaneo, scritte prima di avviare il browser
    (`download.default_directory`): `Page.setDownloadBehavior` sulla scheda Edge lo ignora."""
    cartella = SCARICATI / profilo
    cartella.mkdir(parents=True, exist_ok=True)
    pref = PTP.TMP / profilo / "Default" / "Preferences"
    pref.parent.mkdir(parents=True, exist_ok=True)
    pref.write_text(json.dumps({"download": {"default_directory": str(cartella),
                                             "prompt_for_download": False,
                                             "directory_upgrade": True},
                                "savefile": {"default_directory": str(cartella)}}),
                    encoding="utf-8")
    p = PTP.Pagina(exe, url, profilo=profilo, opzioni=opzioni)
    p.scaricati = cartella
    return p


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({str(dettaglio)[:300]})" if dettaglio else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


def turno(domanda, risposta, luogo, canale="voce", t=None):
    return [{"role": "user", "content": domanda,
             "_turno": {"t": t or time.time(), "luogo": luogo, "canale": canale}},
            {"role": "assistant", "content": risposta}]


class Ambiente:
    def __init__(self):
        from calliope.config import Config
        from calliope.conversazioni import ArchivioConversazioni
        from calliope.satellite.archivio import ArchivioSatelliti
        from calliope.satellite.server import ServerSatelliti
        from calliope.sviluppo import Sviluppi
        cfg = self.cfg = Config()
        cfg.config_dir = str(TMP)
        # Il contenuto delle schede sulla pagina del PC si prova con la vista di prima (la scheda
        # grande): la disposizione a sezioni dello schermo personale la prova prova_pc_pagina (27/10)
        cfg.schermi_sezioni = False
        cfg.memory_db = str(TMP / "memoria.db")
        cfg.turn_log_dir = str(TMP / "registro")
        cfg.satellite_porta = 0
        cfg.audio_modo = "satellite"
        cfg.telefono_web = str(TMP / "web")
        self.srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
        self.srv.avviato.set()
        self.arch = ArchivioConversazioni(TMP / "conversazioni.db", giorni=30, avvia=False,
                                          log=lambda m: None)
        self.svs = Sviluppi(cfg, TMP / "sviluppi", log=lambda m: None)
        self.porta = PTP.porta_libera()
        self.hub = self.web = None
        self.avvii = 0
        self.accendi()

    def accendi(self):
        from calliope.schermi import ArchivioSchermi, Schermi
        from calliope.schermi.cronologia import CronologiaSchede
        from calliope.schermi.server import ServerSchermi
        self.avvii += 1
        hub = Schermi(self.cfg, ArchivioSchermi(self.cfg.memory_db), log=lambda m: None)
        hub.cronologia = CronologiaSchede(TMP / "schede", log=lambda m: None,
                                          avvio=f"avvio{self.avvii}")
        hub.chat_fonte = self.arch
        self.arch.su_turni[:] = [hub.chat_nuovi]
        self.arch.su_dimentica[:] = [hub.chat_dimenticata]
        svs = self.svs
        svs.schermi = hub
        hub.lavori = SimpleNamespace(lavori=[], sviluppi=svs)
        hub.ricostruttori.append(lambda p: [svs.scheda(x) for x in [svs.corrente(p)] if x])
        hub.satelliti = self.srv
        self.srv.schermi = hub
        hub.stanza_corrente = self.srv.stanza
        self.web = ServerSchermi(hub, "127.0.0.1", self.porta, attesa_porta_s=10).avvia()
        hub.server = self.web
        self.hub = hub

    def riavvia(self):
        """Il servizio si riavvia: tutto in memoria si perde, il disco resta."""
        self.web.ferma()
        self.hub.cronologia.close()
        self.hub.archivio.close()
        self.accendi()

    def chiudi(self):
        self.web.ferma()
        self.hub.cronologia.close()
        self.hub.archivio.close()
        self.srv.ferma()
        self.arch.close()


def collegata(p, max_s=15):
    return aspetta(lambda: p.valuta("document.getElementById('stato-testo').textContent")
                   == "collegato", max_s)


CRON = "[...document.querySelectorAll('#cronologia button:not(.pulisci-schede)')].map(b => b.querySelector('.t-titolo').textContent)"
TURNI = ("[...document.querySelectorAll('#principale .tipo-chat .conv-turno')].map(t => ({"
         "meta: t.querySelector('.conv-meta').textContent,"
         "tu: (t.querySelector('.conv-tu .conv-x') || {}).textContent || '',"
         "calliope: (t.querySelector('.conv-calliope .conv-x') || {}).textContent || ''}))")


def errori_js(p):
    p.pompa(0.3)
    return [x for x in p.log if x.startswith("ECCEZIONE") or "Content Security" in x]


def prova(exe, amb):
    from calliope.conversazione import Conversazione, turni
    from calliope.schermi import Mittente, schede
    from calliope.sviluppo import Sviluppo
    hub = amb.hub
    _, t_studio = hub.archivio.crea_con_token("studio", proprietario="dario",
                                              proprietario_nome="Dario")
    _, t_cucina = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()
    base = f"http://127.0.0.1:{amb.porta}/"
    pagine = []
    studio = pagina(exe, base + f"#t={t_studio}", profilo="profilo-cr-studio",
                        opzioni=("--window-size=1280,800",))
    pagine.append(studio)
    try:
        verifica("la pagina dello studio si collega", bool(collegata(studio)))
        dario = Mittente("dario", "Dario", "amministra", True)
        hub.invia(schede.documento_markdown("Relazione sul giardino", "# Giardino\n\nPotare a "
                                            "marzo.", chiave="lavoro:L3"), dario)
        hub.invia(schede.testo("Lista dei regali", "Libro per Bianca, sciarpa per Teo.",
                               schede.PERSONALE), dario)
        hub.invia(schede.calcolo("12*3", "36"), dario)            # di stanza: non resta
        conv = Conversazione("persona:dario")
        conv.luogo = "studio"
        t0 = time.time() - 300
        amb.arch.archivia(conv, turni(turno("Che tempo fa domani a Pisa?", "Domani sole e 22 "
                                            "gradi.", "Studio", t=t0)
                                      + turno("Ricordami di potare le rose", "Va bene, te lo "
                                              "ricordo sabato.", "Telefono", "scritto", t0 + 60)
                                      + turno("Grazie", "Prego!", "Studio", t=t0 + 90)),
                          "dario", "Dario", ospite=False)
        b = Conversazione("persona:bianca")
        amb.arch.archivia(b, turni(turno("Frase di Bianca", "Risposta a Bianca", "Cucina")),
                          "bianca", "Bianca", ospite=False)
        g = Conversazione("ospite:locale")
        amb.arch.archivia(g, turni(turno("Frase di un ospite", "Ciao ospite", "Cucina")), None,
                          None, ospite=True)
        aspetta(lambda: len(studio.valuta(CRON) or []) >= 3, 8)
        hub.cronologia.scrivi_ora()

        # ── riavvio del servizio ──
        amb.riavvia()
        hub = amb.hub
        ok = aspetta(lambda: studio.valuta("document.getElementById('stato-testo').textContent")
                     == "collegato" and studio.valuta(
                         "!!document.getElementById('chat-apri')"), 25)
        cron = studio.valuta(CRON) or []
        verifica("la pagina di prima si ricollega da sola dopo il riavvio, senza doppioni",
                 bool(ok) and len(cron) == len(set(cron)) and "Relazione sul giardino" in cron,
                 cron)
        _, t_camera = hub.archivio.crea_con_token("camera", proprietario="dario",
                                                  proprietario_nome="Dario")
        hub._rinfresca()
        camera = pagina(exe, base + f"#t={t_camera}", profilo="profilo-cr-camera",
                            opzioni=("--window-size=1280,800",))
        pagine.append(camera)
        verifica("uno schermo personale nuovo si collega", bool(collegata(camera)))
        ok = aspetta(lambda: len(camera.valuta(CRON) or []) >= 2, 8)
        cron = camera.valuta(CRON) or []
        verifica("lo schermo nuovo ritrova le schede di Dario dopo il riavvio",
                 bool(ok) and cron[:2] == ["Lista dei regali", "Relazione sul giardino"], cron)
        verifica("…ma non quella della stanza (il calcolo)", "Calcolo" not in cron, cron)
        verifica("il pulsante «Conversazione» c'è",
                 camera.valuta("!document.getElementById('chat-apri').hidden"))
        tocca(camera, "#chat-apri")
        ok = aspetta(lambda: len(camera.valuta(TURNI) or []) == 3, 8)
        tt = camera.valuta(TURNI) or []
        verifica("la conversazione ricaricata: le tre frasi di Dario con le risposte",
                 bool(ok) and [x["tu"] for x in tt] == ["Che tempo fa domani a Pisa?",
                                                       "Ricordami di potare le rose", "Grazie"]
                 and tt[0]["calliope"] == "Domani sole e 22 gradi.", tt)
        verifica("con l'ora, il satellite e «scritto»",
                 "Studio" in tt[0]["meta"] and "Telefono · scritto" in tt[1]["meta"]
                 and ":" in tt[0]["meta"], [x["meta"] for x in tt])
        testo = camera.valuta("document.querySelector('#principale .tipo-chat').innerText") or ""
        verifica("mai i turni di Bianca né degli ospiti",
                 "Bianca" not in testo and "ospite" not in testo)
        camera.pompa(0.6)
        foto(camera, "conversazione-1280x800.png", 1280, 800)
        # Un turno nuovo: in fondo, senza riscrivere i turni di prima
        camera.valuta("window.__primo = document.querySelector('#principale .conv-turno'); 1")
        conv2 = Conversazione("persona:dario")
        amb.arch.archivia(conv2, turni(turno("E domenica?", "Domenica pioggia leggera.",
                                             "Camera")), "dario", "Dario", ospite=False)
        ok = aspetta(lambda: len(camera.valuta(TURNI) or []) == 4, 8)
        tt = camera.valuta(TURNI) or []
        verifica("turno nuovo in diretta, in fondo",
                 bool(ok) and tt[-1]["tu"] == "E domenica?", [x["tu"] for x in tt])
        verifica("…senza riscrivere i turni di prima (stesso elemento)", camera.valuta(
            "window.__primo === document.querySelector('#principale .conv-turno')"))
        fondo = camera.valuta("(() => { const b = document.querySelector('#principale "
                              ".conv-chat'); return b.scrollHeight - b.scrollTop - b.clientHeight; })()")
        verifica("…e la vista resta in fondo", fondo is not None and fondo < 30, fondo)
        verifica("anche la pagina di prima riceve il turno nuovo (nella sua scheda, chiusa)",
                 aspetta(lambda: studio.valuta("(() => { const s = window.calliopeSchermo; "
                                               "s.chat(); return document.querySelectorAll("
                                               "'#principale .conv-turno').length; })()") == 4, 6))
        # «Scarica» la trascrizione
        tocca(camera, "#principale .tipo-chat button[data-scarica='md']")
        ok = aspetta(lambda: (camera.valuta("(document.querySelector('#principale .tipo-chat "
                                            ".esito-scarica') || {}).textContent") or ""
                              ).startswith("Scaricato"), 8)
        verifica("«Scarica» della trascrizione in Markdown", bool(ok),
                 camera.valuta("(document.querySelector('#principale .tipo-chat .esito-scarica')"
                               " || {}).textContent"))
        def scaricato():
            return [f for f in camera.scaricati.glob("*.md")
                    if "Pisa" in f.read_text(encoding="utf-8", errors="replace")]
        ok = aspetta(lambda: bool(scaricato()), 8)
        verifica("…il file nella cartella dei download della prova, non nei Download veri",
                 bool(ok), [f.name for f in camera.scaricati.iterdir()])
        # Lo schermo di stanza
        cucina = pagina(exe, base + f"#t={t_cucina}", profilo="profilo-cr-cucina",
                            opzioni=("--window-size=1280,800",))
        pagine.append(cucina)
        collegata(cucina)
        cucina.pompa(0.5)
        verifica("schermo di stanza: niente pulsante «Conversazione», niente schede delle persone",
                 cucina.valuta("!document.getElementById('chat-apri')")
                 and not cucina.valuta(CRON)
                 and not cucina.valuta("!!document.querySelector('#cronologia .pulisci-schede')"))
        # «Pulisci» con due tocchi
        camera.valuta("window.calliopeSchermo.chat(); 1")
        tocca(camera, "#cronologia .pulisci-schede")
        camera.pompa(0.3)
        primo = camera.valuta("document.querySelector('#cronologia .pulisci-schede').textContent")
        verifica("«Pulisci»: il primo tocco chiede il secondo e non toglie niente",
                 primo == "Tocca di nuovo per pulire" and len(hub.cronologia.ultime("dario")) >= 2,
                 primo)
        foto(camera, "pulisci-armato-1280x800.png", 1280, 800)
        tocca(camera, "#cronologia .pulisci-schede")
        ok = aspetta(lambda: camera.valuta(CRON) == ["La nostra conversazione"]
                     and studio.valuta(CRON) == ["La nostra conversazione"], 8)
        verifica("al secondo tocco: le schede spariscono da tutti gli schermi di Dario (la "
                 "conversazione resta)", bool(ok) and hub.cronologia.ultime("dario") == [],
                 (camera.valuta(CRON), studio.valuta(CRON)))

        # ── un altro riavvio con uno sviluppo aperto ──
        sv = Sviluppo(id="S2", persona="dario", persona_nome="Dario", titolo="Meteo per città",
                      aperta=time.time(), ultimo=time.time(), richiesta="Il meteo di una città")
        amb.svs.sviluppi.append(sv)
        amb.riavvia()
        ok = aspetta(lambda: camera.valuta("document.body.classList.contains('in-vista-sviluppo')"
                                           " && !!document.querySelector('#principale .vista-svil')"),
                     25)
        verifica("dopo il riavvio lo schermo rientra subito nella vista dello sviluppo aperto",
                 bool(ok))
        camera.pompa(0.5)
        foto(camera, "sviluppo-dopo-riavvio-1280x800.png", 1280, 800)
        for p, nome in ((studio, "studio"), (camera, "camera"), (cucina, "cucina")):
            e = errori_js(p)
            verifica(f"{nome}: nessun errore JavaScript né violazione della CSP", not e,
                     "; ".join(e)[:300])
    finally:
        for p in pagine:
            p.chiudi()


def telefono(exe, amb):
    _, token = amb.srv.archivio.crea_con_token("telefono-dario", proprietario="dario",
                                               proprietario_nome="Dario")
    amb.svs.sviluppi.clear()
    p = pagina(exe, f"http://127.0.0.1:{amb.porta}/telefono/", profilo="profilo-cr-tel",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: p.valuta("!!window.calliopeTelefono && window.calliopeTelefono.st.collegato"), 15)
        verifica("telefono di Dario: collegato", bool(ok))
        ok = aspetta(lambda: p.valuta("!document.getElementById('conv-tel').hidden"
                                      " && !!document.querySelector('#conv-tel .tipo-chat')"), 10)
        verifica("telefono personale: la conversazione dentro la sezione Conversazione e «Pulisci le mie schede» in Io",
                 bool(ok) and p.valuta("!document.getElementById('pulisci-tel').hidden"
                                       " && !!document.querySelector('#sez-conversazione #conv-tel .tipo-chat')"
                                       " && !!document.querySelector('#sez-io #pulisci-tel')"))
        tocca(p, '#barra a[data-sezione="conversazione"]')
        aspetta(lambda: p.valuta("!document.getElementById('sez-conversazione').hidden"), 3)
        ok = aspetta(lambda: p.valuta("document.querySelectorAll('#conv-tel .conv-turno').length") == 4, 10)
        verifica("in Conversazione i turni, senza aprire niente", bool(ok),
                 p.valuta("document.querySelectorAll('#conv-tel .conv-turno').length"))
        fondo = aspetta(lambda: p.valuta("(() => { const b = document.querySelector('#conv-tel .conv-chat');"
                                         " return b.scrollHeight - b.scrollTop - b.clientHeight < 30; })()"), 3)
        verifica("…con l'ultimo turno in vista (disegnata mentre la sezione era nascosta)", bool(fondo))
        foto(p, "conversazione-telefono-sezione.png", 390, 844, mobile=True)
        conversazione_tel(p, amb)
        e = errori_js(p)
        verifica("telefono: nessun errore JavaScript né violazione della CSP", not e,
                 "; ".join(e)[:300])
    finally:
        p.chiudi()


# Le misure della conversazione nella sua sezione (28/10, #242): niente fuori di lato (in
# verticale scorre la conversazione), contrasto AA del testo visibile, tocchi ≥ 44 px
MISURA_CONV = r"""((sel) => {
  const box = document.querySelector(sel);
  const W = innerWidth, H = innerHeight;
  const vis = (e) => e && !e.closest('[hidden]') && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
  const nome = (e) => (e.className && typeof e.className === 'string' ? e.className : e.tagName).slice(0, 40);
  const br = box.getBoundingClientRect();
  const log = box.querySelector('.conv-chat'), lr = log ? log.getBoundingClientRect() : br;
  const fuori = [];
  for (const e of [...box.querySelectorAll('*')].filter(vis)) {
    const r = e.getBoundingClientRect();
    if (r.width && (r.left < br.left - 1 || r.right > br.right + 1)) fuori.push(nome(e) + ' esce di lato');
  }
  if (br.left < -1 || br.right > W + 1) fuori.push('la conversazione esce dallo schermo');
  if (log && log.scrollWidth > log.clientWidth + 1) fuori.push('la conversazione scorre di lato');
  const lum = (c) => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => v / 255)
    .map((v) => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
  const alfa = (c) => { const m = c.match(/[\d.]+/g); return m.length > 3 ? Number(m[3]) : 1; };
  const contrasto = (e) => { const cs = getComputedStyle(e); let b = e, bg = 'rgba(0, 0, 0, 0)';
    while (b && alfa(bg = getComputedStyle(b).backgroundColor) < 0.5) b = b.parentElement;
    const l1 = lum(cs.color), l2 = lum(b ? bg : 'rgb(0, 0, 0)'); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const inVista = (e) => { const r = e.getBoundingClientRect();
    return e.closest('.conv-chat') ? r.bottom > Math.max(0, lr.top) && r.top < Math.min(H, lr.bottom) : r.bottom > 0 && r.top < H; };
  const bassi = [...box.querySelectorAll('*')].filter(vis).filter((e) => !e.closest('.piccola-anteprima'))
    .filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())).filter(inVista)
    .map((e) => [nome(e) + ' «' + e.textContent.trim().slice(0, 14) + '»', contrasto(e)]).filter(([, c]) => c < 4.5)
    .map(([n, c]) => n + ' ' + c.toFixed(2)).slice(0, 6);
  const tocchi = [...box.querySelectorAll('.chat-chip, .chat-cerca input, .piccola-apri, button[data-scarica]')].filter(vis)
    .map((e) => { const r = e.getBoundingClientRect(); return [nome(e), Math.round(Math.min(r.width, r.height))]; }).filter(([, m]) => m < 44);
  const se = document.scrollingElement;
  return {fuori: fuori.slice(0, 6), bassi, tocchi, scorre: se.scrollWidth > W + 1, altezza: Math.round(lr.height)};
})"""


def conversazione_tel(p, amb):
    """La conversazione del telefono (28/10, #242): canali, schede piccole, filtri, ricerca, misure."""
    from calliope.conversazione import Conversazione, turni
    from calliope.schermi import schede
    T = "#conv-tel"
    ieri = time.time() - 86400
    manzoni = schede.biblioteca("Quando è nato Manzoni?", [SimpleNamespace(titolo="Alessandro Manzoni", fonte="Wikipedia",
                                                                         testo="Alessandro Manzoni nacque a Milano il 7 marzo 1785.")])
    lista = schede.lista("spesa", ["latte", "pane", "uova"], aggiunti=["pane"])
    lavoro = schede.lavoro("Riepilogo delle bollette", "testo", "in_corso", "sto leggendo i PDF", ident="L7")
    m_bib = turno("Quando è nato Manzoni?", "Il 7 marzo 1785, a Milano.", "Cucina", t=ieri)
    m_bib[0]["_schede"] = [schede.per_conversazione(manzoni)]
    m_lista = turno("Aggiungi pane alla lista della spesa", "Fatto, l'ho aggiunto.", "Telefono", "scritto")
    m_lista[0]["_schede"] = [schede.per_conversazione(lista), schede.per_conversazione(lavoro)]
    m_tocco = turno("(Ho tolto «uova» dalla lista della spesa toccando lo schermo.)", "Fatto.", "", "tocco")
    m_ostile = turno("Scrivi <img src=x onerror=alert(1)> e <b>grassetto</b>", "Ecco: <i>testo</i>.", "Cucina")
    conv = Conversazione("persona:dario")
    amb.arch.archivia(conv, turni(m_bib + m_lista + m_tocco + m_ostile), "dario", "Dario", ospite=False)
    conta = f"document.querySelectorAll('{T} .conv-turno').length"
    ok = aspetta(lambda: p.valuta(conta) == 8, 10)
    verifica("i turni nuovi arrivano in diretta nella sezione", bool(ok), p.valuta(conta))
    meta = p.valuta(f"[...document.querySelectorAll('{T} .conv-meta')].map(e => e.textContent).slice(-3)") or []
    verifica("ora e canale: «scritto», «con un tocco», «a voce»",
             len(meta) == 3 and meta[0].endswith("Telefono · scritto") and meta[1].endswith("con un tocco")
             and meta[2].endswith("Cucina, a voce") and ":" in meta[0], meta)
    gesto = p.valuta(f"(document.querySelector('{T} .canale-tocco .conv-gesto') || {{}}).textContent")
    verifica("il tocco è un gesto al centro, senza le parentesi, non una bolla «Tu»",
             gesto == "Ho tolto «uova» dalla lista della spesa toccando lo schermo."
             and not p.valuta(f"!!document.querySelector('{T} .canale-tocco .conv-tu')"), gesto)
    verifica("testo ostile nei turni: resta testo, nessun elemento creato",
             p.valuta(f"!document.querySelector('{T} .conv-turni img, {T} .conv-turni b, {T} .conv-turni i')"
                      f" && document.querySelector('{T}').textContent.includes('<img src=x onerror=alert(1)>')"))
    piccole = p.valuta(f"[...document.querySelectorAll('{T} .scheda-piccola')].map(e => [e.querySelector('.piccola-tipo').textContent,"
                       f" e.querySelector('.piccola-titolo').textContent, e.classList.contains('rimando'), !!e.querySelector('.piccola-anteprima[inert]')])") or []
    verifica("le schede piccole dentro le risposte: tipo, titolo, anteprima inerte; il lavoro è un rimando",
             piccole == [["Biblioteca", manzoni["titolo"], False, True], ["Lista", "Lista della spesa", False, True],
                         ["Lavoro", "Riepilogo delle bollette", True, False]], piccole)
    verifica("l'anteprima della lista senza spunta (è la lista di allora)",
             p.valuta(f"!document.querySelector('{T} .scheda-piccola button.spunta')"
                      f" && document.querySelector('{T} .scheda-piccola.tipo-lista .piccola-anteprima').textContent.includes('pane')"))
    # Un tocco sulla scheda piccola: la copia del turno a schermo intero, senza spunta
    tocca(p, f"{T} .scheda-piccola.tipo-lista .piccola-apri")
    ok = aspetta(lambda: p.valuta("!document.getElementById('strato-scheda').hidden"
                                  " && !!document.querySelector('#intera-posto .tipo-lista')"), 5)
    verifica("un tocco sulla scheda piccola apre la scheda intera com'era allora",
             bool(ok) and p.valuta("document.getElementById('intera-titolo').textContent") == "Lista della spesa"
             and p.valuta("[...document.querySelectorAll('#intera-posto .voci li')].map(e => e.textContent).join(',')")
             == "latte,pane,uova" and not p.valuta("!!document.querySelector('#intera-posto button.spunta')"),
             p.valuta("document.getElementById('intera-titolo').textContent"))
    foto(p, "conversazione-telefono-scheda.png", 390, 844, mobile=True)
    p.valuta("history.back(); 1")
    ok = aspetta(lambda: p.valuta("document.getElementById('strato-scheda').hidden"), 3)
    verifica("il gesto indietro chiude la scheda e torna alla conversazione",
             bool(ok) and p.valuta("!document.getElementById('sez-conversazione').hidden"))
    # Il rimando: porta alla sua sezione
    tocca(p, f"{T} .scheda-piccola.rimando .piccola-apri")
    ok = aspetta(lambda: p.valuta("location.hash").startswith("#/cose/lavori"), 3)
    verifica("il rimando del lavoro porta a Le mie cose › Lavori", bool(ok), p.valuta("location.hash"))
    tocca(p, '#barra a[data-sezione="conversazione"]')
    aspetta(lambda: p.valuta("!document.getElementById('sez-conversazione').hidden"), 3)

    # I filtri
    def domande():
        return p.valuta(f"[...document.querySelectorAll('{T} .conv-turno')].map(t => (t.querySelector('.conv-tu .conv-x, .conv-gesto') || {{}}).textContent || '')") or []
    tocca(p, f"{T} [data-chat-filtro='ieri']")
    ok = aspetta(lambda: domande() == ["Quando è nato Manzoni?"], 5)
    verifica("Ieri: solo il turno di ieri, il filtro segnato",
             bool(ok) and p.valuta(f"document.querySelector('{T} [data-chat-filtro=ieri]').getAttribute('aria-pressed')") == "true",
             domande())
    tocca(p, f"{T} [data-chat-filtro='oggi']")
    ok = aspetta(lambda: len(domande()) == 7 and "Quando è nato Manzoni?" not in domande(), 5)
    verifica("Oggi al posto di Ieri: i turni di oggi", bool(ok), domande())
    tocca(p, f"{T} [data-chat-filtro='schede']")
    ok = aspetta(lambda: domande() == ["Aggiungi pane alla lista della spesa"], 5)
    verifica("Oggi e Solo schede: il turno con le schede", bool(ok), domande())
    foto(p, "conversazione-telefono-schede.png", 390, 844, mobile=True)
    tocca(p, f"{T} .chat-cerca-via")
    ok = aspetta(lambda: len(domande()) == 8, 5)
    verifica("«Tutto» toglie i filtri", bool(ok) and p.valuta(f"document.querySelectorAll('{T} [aria-pressed=true]').length") == 0,
             domande())

    # La ricerca, anche con testo ostile
    def cerca(testo):
        p.valuta(f"(() => {{ const i = document.querySelector('{T} .chat-cerca input'); i.value = {json.dumps(testo)};"
                 f" i.form.requestSubmit(); return 1; }})()")
    verifica("la casella della ricerca è chiusa finché non si tocca «Cerca»",
             p.valuta(f"document.querySelector('{T} .chat-cerca').hidden"))
    tocca(p, f"{T} .chat-cerca-apri")
    ok = aspetta(lambda: p.valuta(f"!document.querySelector('{T} .chat-cerca').hidden"
                                  f" && document.activeElement === document.querySelector('{T} .chat-cerca input')"), 3)
    verifica("«Cerca» apre la casella col cursore dentro", bool(ok))
    cerca("manzoni")
    ok = aspetta(lambda: domande() == ["Quando è nato Manzoni?"], 5)
    verifica("cerca: trova il turno di ieri per parola", bool(ok), domande())
    cerca('"><img src=x onerror=alert(2)> OR NEAR(')
    ok = aspetta(lambda: domande() == [] and "Nessun turno" in (p.valuta(f"document.querySelector('{T} .chat-esito').textContent") or ""), 5)
    verifica("cerca con testo ostile: nessun turno, lo dice, niente elementi nuovi",
             bool(ok) and not p.valuta("!!document.querySelector('#conv-tel img')"),
             p.valuta(f"document.querySelector('{T} .chat-esito').textContent"))
    foto(p, "conversazione-telefono-cerca.png", 390, 844, mobile=True)
    tocca(p, f"{T} .chat-cerca-via")
    aspetta(lambda: len(domande()) == 8, 5)
    verifica("«Tutto» svuota anche la casella",
             p.valuta(f"document.querySelector('{T} .chat-cerca input').value") == "")
    # Le misure
    for w, h in ((375, 812), (320, 568)):
        p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2, "mobile": True})
        aspetta(lambda: p.valuta(f"innerWidth === {w}"), 5)
        time.sleep(0.4)
        foto(p, f"conversazione-telefono-{w}x{h}.png", w, h, mobile=True)
        m = p.valuta(f"({MISURA_CONV})({json.dumps(T)})") or {}
        verifica(f"{w}×{h}: niente fuori di lato, la pagina non scorre di lato", not m.get("fuori") and not m.get("scorre"),
                 json.dumps(m.get("fuori")))
        verifica(f"{w}×{h}: contrasto AA e tocchi ≥ 44 px", not m.get("bassi") and not m.get("tocchi"),
                 json.dumps([m.get("bassi"), m.get("tocchi")]))
        verifica(f"{w}×{h}: la conversazione ha posto per i turni", (m.get("altezza") or 0) >= 190, m.get("altezza"))
    # La casella resta spenta fuori da una conversazione a voce
    stato = p.valuta("({spento: document.getElementById('scrivi-apri').classList.contains('spento'),"
                     " visibile: !document.getElementById('scrivi-apri').hidden})") or {}
    verifica("Scrivi resta spento in Conversazione senza una conversazione a voce",
             stato.get("spento") is True or stato.get("visibile") is False, stato)


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
    PTP.TMP = TMP
    amb = None
    try:
        amb = Ambiente()
        prova(exe, amb)
        telefono(exe, amb)
    finally:
        if amb is not None:
            amb.chiudi()
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
