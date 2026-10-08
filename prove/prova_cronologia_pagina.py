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
- telefono di Dario: «La nostra conversazione» nel menu la apre a schermo intero, in una colonna
  senza testo che esce di lato; «Pulisci le mie schede» c'è;
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
ERRORI = []
SALTATA = 77
aspetta = PCP.aspetta
tocca = PCP.tocca
foto = PCP.foto


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
    studio = PTP.Pagina(exe, base + f"#t={t_studio}", profilo="profilo-cr-studio",
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
        camera = PTP.Pagina(exe, base + f"#t={t_camera}", profilo="profilo-cr-camera",
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
        # Lo schermo di stanza
        cucina = PTP.Pagina(exe, base + f"#t={t_cucina}", profilo="profilo-cr-cucina",
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
    p = PTP.Pagina(exe, f"http://127.0.0.1:{amb.porta}/telefono/", profilo="profilo-cr-tel",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: p.valuta("!!window.calliopeTelefono && window.calliopeTelefono.st.collegato"), 15)
        verifica("telefono di Dario: collegato", bool(ok))
        ok = aspetta(lambda: p.valuta("!document.getElementById('chat-tel').hidden"), 10)
        verifica("telefono personale: «La nostra conversazione» e «Pulisci le mie schede» nel menu",
                 bool(ok) and p.valuta("!document.getElementById('pulisci-tel').hidden"))
        tocca(p, "#menu-apri")
        aspetta(lambda: p.valuta("!document.getElementById('menu').hidden"), 3)
        foto(p, "conversazione-telefono-menu.png", 390, 844, mobile=True)
        tocca(p, "#chat-tel")
        ok = aspetta(lambda: p.valuta("document.querySelectorAll('#intera-posto .conv-turno').length") == 4, 10)
        verifica("dal menu la conversazione si apre a schermo intero, con i turni", bool(ok),
                 p.valuta("document.querySelectorAll('#intera-posto .conv-turno').length"))
        verifica("…e c'è anche nel carosello",
                 p.valuta("!!document.querySelector('#binario .tipo-chat')"))
        fuori = p.valuta("(() => { const s = document.querySelector('#intera-posto .conv-chat');"
                         " return s.scrollWidth > s.clientWidth + 1; })()")
        verifica("in una colonna, niente testo che esce di lato", fuori is False, fuori)
        larghe = p.valuta("(() => { const b = document.querySelector('#intera-posto .conv-chat')"
                          ".getBoundingClientRect(); return b.width <= window.innerWidth; })()")
        verifica("la conversazione sta nella larghezza del telefono", larghe is True, larghe)
        time.sleep(0.4)
        foto(p, "conversazione-telefono.png", 390, 844, mobile=True)
        e = errori_js(p)
        verifica("telefono: nessun errore JavaScript né violazione della CSP", not e,
                 "; ".join(e)[:300])
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
