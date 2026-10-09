import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il cruscotto di chi amministra nella pagina vera (06/10/2026, calliope/schermi/cruscotto.py):
Edge o Chromium senza finestra comandato con DevTools (senza browser si salta), server degli
schermi e dei satelliti veri su 127.0.0.1, registro dei turni finto.

- pagina degli schermi, schermo personale di chi amministra: il pulsante «Cruscotto» c'è, il
  tocco apre la scheda con le sezioni (versione, capacità, latenza, satelliti e schermi,
  regole, errori, in attesa), «Aggiorna» la ridisegna al suo posto (stesso elemento), «Chiudi»
  la toglie; nessun testo di persone nella pagina;
- schermo personale di un familiare e schermo di stanza: niente pulsante, e la scheda non si
  apre nemmeno chiamandola a mano;
- telefono di chi amministra: la voce del menu c'è, apre la scheda nel carosello (in vista);
  telefono di un familiare: niente voce;
- la ricerca web (09/10, calliope/web/motore.py, con SearXNG e docker finti): con il motore la
  sezione «Ricerca web (SearXNG)» e i pulsanti «Controlla» e «Aggiorna»; il primo tocco chiede
  la conferma («Tocca ancora…»), il secondo fa partire il controllo e l'esito arriva sulla
  scheda; uno schermo di un familiare non ha né scheda né pulsanti;
- nessun errore JavaScript né violazione della CSP. Con CALLIOPE_FOTO=<cartella> salva gli
  screenshot (pagina 1280×800, telefono 390×844). ~25 s.
"""

import base64
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_cruscotto as PC
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-cruscotto-pagina-"))
ERRORI = []
SALTATA = 77


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def aspetta(cond, max_s=8.0, passo=0.1):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        try:
            v = cond()
        except Exception:  # noqa: BLE001
            v = None
        if v:
            return v
        time.sleep(passo)
    return None


def foto(p, nome, w=None, h=None, mobile=False):
    cartella = os.environ.get("CALLIOPE_FOTO")
    if not cartella:
        return
    if w:
        p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h,
                                                         "deviceScaleFactor": 1 if not mobile else 2,
                                                         "mobile": mobile})
        time.sleep(0.4)
    r = p._chiama("Page.captureScreenshot", {"format": "png"})
    Path(cartella).mkdir(parents=True, exist_ok=True)
    (Path(cartella) / nome).write_bytes(base64.b64decode(r["result"]["data"]))


def tocca(p, sel):
    r = p.valuta(f"(() => {{ const e = document.querySelector({json.dumps(sel)});"
                 f" if (!e) return null; e.scrollIntoView({{block: 'center'}});"
                 f" const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
    if not r:
        return False
    for t in ("mousePressed", "mouseReleased"):
        p._chiama("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1], "button": "left",
                                               "clickCount": 1})
    return True


def avvia():
    from calliope.config import Config
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.cruscotto import Cruscotto
    from calliope.schermi.server import ServerSchermi
    from calliope import capacita
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    cfg.turn_log_dir = str(TMP / "registro")
    cfg.estensioni_cartella = str(TMP / "estensioni")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    cfg.telefono_web = str(TMP / "web")
    PC.registro_turni(TMP / "registro", 3, 200)
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    web = ServerSchermi(hub, "127.0.0.1", PTP.porta_libera(), attesa_porta_s=5).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    reg = PC.Registro(PC.Profilo("dario", "Dario", admin=True), PC.Profilo("bianca", "Bianca"))
    servizi = PC.Servizi(reg)
    servizi.satelliti = srv
    capreg = capacita.Registro()
    capreg.segnala("llm", "attiva", "gemma4")
    capreg.segnala("casa", "guasta", "Home Assistant non risponde", "Controlla il Raspberry.")
    capreg.segnala("web", "da_configurare", "SearXNG spento", "calliope motore searxng avvia")
    hub.cruscotto = Cruscotto(cfg, hub, servizi=servizi, registro_capacita=capreg)
    return cfg, srv, hub, web


SEZIONI = ["Versione", "Capacità", "Latenza della voce", "Satelliti e schermi",
           "Regole scattate", "Errori del ciclo", "In attesa"]


def schermo(exe, hub, web):
    arch = hub.archivio
    _, t_admin = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, t_fam = arch.crea_con_token("camera", proprietario="bianca", proprietario_nome="Bianca")
    _, t_stanza = arch.crea_con_token("cucina")
    hub._rinfresca()
    base = f"http://127.0.0.1:{web.port}/"
    p = PTP.Pagina(exe, base + f"#t={t_admin}", profilo="profilo-admin",
                   opzioni=("--window-size=1280,800",))
    try:
        ok = aspetta(lambda: p.valuta("!!document.getElementById('cruscotto-apri') && "
                                      "!document.getElementById('cruscotto-apri').hidden"), 10)
        verifica("schermo di chi amministra: pulsante «Cruscotto» nella testa", bool(ok))
        tocca(p, "#cruscotto-apri")
        ok = aspetta(lambda: p.valuta("document.querySelectorAll('#principale .tipo-cruscotto .cr-sezione').length"), 10)
        verifica("tocco: la scheda del cruscotto si apre", bool(ok))
        titoli = p.valuta("[...document.querySelectorAll('#principale .cr-titolo')].map(e => e.textContent)")
        verifica("le sezioni ci sono tutte", titoli == SEZIONI, titoli)
        testo = p.valuta("document.querySelector('#principale .tipo-cruscotto').innerText") or ""
        verifica("capacità guaste con motivo e passo", "Home Assistant non risponde" in testo
                 and "Controlla il Raspberry." in testo, "")
        verifica("latenza con l'avviso e le schede trattenute", "prima frase" in testo
                 and "La prima frase" in testo and "schede trattenute" in testo, "")
        verifica("schermi con chi li ha e lo stato", "personale di Dario" in testo
                 and "collegato" in testo, "")
        verifica("regole ed errori (solo il tipo)", "textcallguard" in testo and "ValueError" in testo)
        verifica("niente testi di persone nella pagina", PC.SEGNO not in testo)
        verifica("nessun pulsante che cambia qualcosa (solo Aggiorna e Chiudi)",
                 p.valuta("[...document.querySelectorAll('#principale .tipo-cruscotto button')]"
                          ".map(b => b.textContent)") == ["Aggiorna", "Chiudi"])
        foto(p, "cruscotto-schermo.png", 1280, 800)
        # «Aggiorna»: stessa scheda, aggiornata al suo posto
        p.valuta("window.__el = document.querySelector('#principale .tipo-cruscotto'); 1")
        hub.cruscotto._quando = 0.0
        prima = hub.cruscotto.calcoli
        tocca(p, "[data-cruscotto='aggiorna']")
        ok = aspetta(lambda: hub.cruscotto.calcoli > prima, 5)
        time.sleep(0.4)
        verifica("«Aggiorna»: ricalcolo e scheda al suo posto (stesso elemento)", bool(ok) and
                 p.valuta("window.__el === document.querySelector('#principale .tipo-cruscotto')"))
        tocca(p, "[data-cruscotto='chiudi']")
        ok = aspetta(lambda: p.valuta("!document.querySelector('#principale .tipo-cruscotto') && "
                                      "![...document.querySelectorAll('#cronologia button')].some(b => b.textContent.includes('Cruscotto'))"), 5)
        verifica("«Chiudi»: la scheda sparisce, anche dalla cronologia", bool(ok))
        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("schermo di chi amministra: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()
    for nome, tok, prof in (("familiare", t_fam, "profilo-fam"), ("di stanza", t_stanza, "profilo-stanza")):
        p = PTP.Pagina(exe, base + f"#t={tok}", profilo=prof)
        try:
            aspetta(lambda: p.valuta("document.getElementById('stato-testo').textContent") == "collegato", 10)
            verifica(f"schermo {nome}: nessun pulsante",
                     p.valuta("!document.getElementById('cruscotto-apri') || "
                              "document.getElementById('cruscotto-apri').hidden"))
            # Neanche chiamandolo a mano: il server risponde 403
            r = p.valuta("(async () => { const s = await fetch('/api/cruscotto', {headers: "
                         "{'X-Calliope-Sessione': 'x'}}); return s.status; })()")
            verifica(f"schermo {nome}: /api/cruscotto con una sessione falsa → 401", r == 401, r)
            p.valuta("window.calliopeSchermo.cruscotto && window.calliopeSchermo.cruscotto(); 1")
            time.sleep(0.5)
            verifica(f"schermo {nome}: la scheda non si apre",
                     not p.valuta("!!document.querySelector('.tipo-cruscotto')"))
            p.pompa(0.2)
            errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica(f"schermo {nome}: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
        finally:
            p.chiudi()


def motore_pagina(exe, hub, web):
    """I pulsanti della ricerca web nella pagina vera (09/10)."""
    import prova_searxng_aggiorna as PS
    h = PS.HttpFinto(PS._registro_hub(time.time()))
    h.profili["http://127.0.0.1:8004"] = PS.BUONO
    PS.TMP = TMP / "motore"
    m = PS.motore("pagina", h, PS.ScriptFinto(in_uso=PS.VECCHIA))
    hub.cruscotto.motore = m
    m.avvisa = hub.cruscotto.avvisa
    arch = hub.archivio
    _, t_admin = arch.crea_con_token("ufficio", proprietario="dario", proprietario_nome="Dario")
    _, t_fam = arch.crea_con_token("cameretta", proprietario="bianca", proprietario_nome="Bianca")
    hub._rinfresca()
    base = f"http://127.0.0.1:{web.port}/"
    p = PTP.Pagina(exe, base + f"#t={t_admin}", profilo="profilo-admin-motore",
                   opzioni=("--window-size=1280,800",))
    try:
        aspetta(lambda: p.valuta("!!document.getElementById('cruscotto-apri') && "
                                 "!document.getElementById('cruscotto-apri').hidden"), 10)
        tocca(p, "#cruscotto-apri")
        ok = aspetta(lambda: p.valuta("[...document.querySelectorAll('#principale .cr-titolo')]"
                                      ".some(e => e.textContent === 'Ricerca web (SearXNG)')"), 10)
        verifica("ricerca web: la sezione c'è", bool(ok))
        bottoni = p.valuta("[...document.querySelectorAll('#principale [data-motore]')].map(b => b.textContent)")
        verifica("ricerca web: «Controlla» e «Aggiorna»", bottoni == ["Controlla", "Aggiorna"], bottoni)
        tocca(p, "[data-motore='controlla']")
        ok = aspetta(lambda: p.valuta("(document.querySelector(\"#principale [data-motore='controlla']\") || {}).textContent")
                     == "Tocca ancora: controlla", 5)
        verifica("primo tocco: chiede la conferma, niente parte", bool(ok) and m.giudizio()["stato"] == "mai")
        foto(p, "cruscotto-motore-conferma.png", 1280, 800)
        tocca(p, "[data-motore='controlla']")
        ok = aspetta(lambda: m.giudizio()["stato"] == "buona", 10)
        verifica("secondo tocco: il controllo parte", bool(ok))
        ok = aspetta(lambda: "va bene" in (p.valuta("document.querySelector('#principale .tipo-cruscotto').innerText") or ""), 10)
        verifica("l'esito arriva sulla scheda", bool(ok))
        testo = p.valuta("document.querySelector('#principale .tipo-cruscotto').innerText") or ""
        verifica("la scheda dice le prove e i motori", "meteo Roma domani" in testo
                 and "motori che rispondono" in testo, "")
        foto(p, "cruscotto-motore.png", 1280, 800)
        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("ricerca web: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()
    p = PTP.Pagina(exe, base + f"#t={t_fam}", profilo="profilo-fam-motore")
    try:
        aspetta(lambda: p.valuta("document.getElementById('stato-testo').textContent") == "collegato", 10)
        p.valuta("window.calliopeSchermo.cruscotto && window.calliopeSchermo.cruscotto(); 1")
        time.sleep(0.5)
        verifica("familiare: nessun pulsante della ricerca web",
                 p.valuta("document.querySelectorAll('[data-motore]').length") == 0)
        r = p.valuta("(async () => { const s = await fetch('/api/motore', {method: 'POST', headers: "
                     "{'X-Calliope-Sessione': 'x', 'Content-Type': 'application/json'}, body: '{}'}); return s.status; })()")
        verifica("familiare: /api/motore con una sessione falsa → 401", r == 401, r)
    finally:
        p.chiudi()
    shutil.rmtree(PS.TMP, ignore_errors=True)


def telefono(exe, srv, web, proprietario, admin):
    nome = "Dario" if admin else "Bianca"
    _, token = srv.archivio.crea_con_token("telefono-" + proprietario, proprietario=proprietario,
                                           proprietario_nome=nome)
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-tel-" + proprietario,
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: p.valuta("!!window.calliopeTelefono && window.calliopeTelefono.st.collegato"), 15)
        verifica(f"telefono di {nome}: collegato", bool(ok))
        aspetta(lambda: p.valuta("!!window.calliopeSchermo && document.getElementById('stato')"
                                 ".className.includes('ok')"), 10)
        time.sleep(0.5)
        voce = p.valuta("!document.getElementById('cruscotto-tel').hidden")
        if not admin:
            verifica("telefono di un familiare: nessuna voce «cruscotto» nel menu", voce is False, voce)
            return
        verifica("telefono di chi amministra: la voce del menu c'è", voce is True, voce)
        tocca(p, "#menu-apri")
        aspetta(lambda: p.valuta("!document.getElementById('menu').hidden"), 3)
        foto(p, "cruscotto-telefono-menu.png", 390, 844, mobile=True)
        tocca(p, "#cruscotto-tel")
        ok = aspetta(lambda: p.valuta("!!document.querySelector('#binario .tipo-cruscotto .cr-sezione')"), 10)
        verifica("il cruscotto si apre nel carosello", bool(ok))
        verifica("il menu si chiude", p.valuta("document.getElementById('menu').hidden"))
        vista = p.valuta("window.calliopeTelefono.carosello().vista")
        verifica("ed è la scheda in vista", vista == "cruscotto", vista)
        fuori = p.valuta("(() => { const s = document.querySelector('#binario .tipo-cruscotto');"
                         " const c = s.querySelector('.corpo'); return c.scrollWidth > c.clientWidth + 1; })()")
        verifica("niente testo che esce di lato", fuori is False, fuori)
        time.sleep(0.3)
        foto(p, "cruscotto-telefono.png", 390, 844, mobile=True)
        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("telefono: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
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
    PTP.TMP = TMP
    try:
        cfg, srv, hub, web = avvia()
        try:
            schermo(exe, hub, web)
            telefono(exe, srv, web, "dario", True)
            telefono(exe, srv, web, "bianca", False)
            motore_pagina(exe, hub, web)
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
