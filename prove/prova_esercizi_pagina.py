import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La scheda degli esercizi nella pagina vera (08/10/2026, calliope/esercizi/): Edge o Chromium
senza finestra comandato con DevTools (senza browser si salta), server degli schermi e dei
satelliti veri su 127.0.0.1, secondo parere finto.

- schermo personale di una bambina: la sessione cominciata (come dal tool a voce) manda la
  scheda con la domanda grande e il campo; una risposta sbagliata scritta → esito «sbagliata»
  con l'indizio, nessuna soluzione nella pagina; quella giusta → esito «giusta» e domanda
  nuova; «Un indizio» e «Secondo me è sbagliato» rispondono al loro posto; «Basta così» →
  scheda finita con il conto;
- italiano: le scelte come pulsanti, il tocco risponde;
- la risposta attesa non è mai nel DOM né nei dati della scheda;
- telefono della stessa bambina: la scheda nel carosello, il campo e «Rispondi» funzionano,
  niente testo che esce di lato;
- nessun errore JavaScript né violazione della CSP. Con CALLIOPE_FOTO=<cartella> salva gli
  screenshot (pagina 1280×800, telefono 390×844). ~25 s.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_telefono_pagina as PTP
from prova_cruscotto_pagina import aspetta, foto, tocca

TMP = Path(tempfile.mkdtemp(prefix="calliope-esercizi-pagina-"))
ERRORI = []
SALTATA = 77


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


class Profilo:
    def __init__(self, pid, nome, nascita=None, tutori=(), gender="f", admin=False):
        self.id, self.name, self.nascita, self.tutori = pid, nome, nascita, list(tutori)
        self.gender, self.admin, self.fascia = gender, admin, None


class Reg:
    def __init__(self, *p):
        self.users = {x.name: x for x in p}

    def get(self, n):
        return self.users.get(n)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)


class ParereFinto:
    modello, ultimo_ms, ultimo_errore = "finto", 1.0, ""
    pronto = True

    def risolvi(self, es):
        from calliope.esercizi.verifica import attesa
        return attesa(es)


def avvia():
    import datetime
    from calliope import minori as M
    from calliope.config import Config
    from calliope.esercizi import sessione as SE
    from calliope.esercizi.registro import Registro
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    cfg.turn_log_dir = str(TMP / "registro")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    cfg.telefono_web = str(TMP / "web")
    cfg.esercizi_pronti = 0
    d = datetime.date.today() - datetime.timedelta(days=30)
    bianca = Profilo("bianca", "Bianca", d.replace(year=d.year - 9).isoformat(), ["dario"])
    reg = Reg(Profilo("dario", "Dario", admin=True, gender="m"), bianca)
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    web = ServerSchermi(hub, "127.0.0.1", PTP.porta_libera(), attesa_porta_s=5).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    M.prepara(cfg, schermi=hub, registry=reg, log=lambda *a: None)
    es = SE.Servizio(cfg, Registro(cfg.memory_db), schermi=hub, log=lambda *a: None,
                     parere=ParereFinto(), wikizionario=None, registry=reg)
    hub.esercizi = es
    return cfg, srv, hub, web, es, bianca


def mittente(bianca):
    from calliope.schermi.hub import Mittente
    return Mittente(persona=bianca.id, nome=bianca.name, livello="familiare", certo=True)


def scrivi_e_invia(p, valore):
    p.valuta("(() => { const i = document.querySelector('.tipo-esercizio .risposta-esercizio input');"
             f" i.value = {json.dumps(valore)}; return 1; }})()")
    return tocca(p, ".tipo-esercizio .risposta-esercizio button")


def dom_senza(p, testo):
    """Il testo non è nel DOM della pagina (né visibile né negli attributi)."""
    return not p.valuta(f"document.documentElement.outerHTML.includes({json.dumps(testo)})")


def schermo(exe, hub, web, es, bianca):
    from calliope.esercizi.numeri import frazione_scritta
    _, tok = hub.archivio.crea_con_token("camera", proprietario=bianca.id,
                                         proprietario_nome=bianca.name)
    hub._rinfresca()
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={tok}", profilo="profilo-bianca",
                   opzioni=("--window-size=1280,800",))
    try:
        aspetta(lambda: p.valuta("document.getElementById('stato-testo').textContent") == "collegato", 10)
        out = es.inizia(bianca, "bambini", 9, "matematica", "sottrazioni", "", mittente(bianca))
        verifica("sessione cominciata (come dal tool a voce)", out.get("ok") is True, out)
        s = es.sessione(bianca.id)
        dom = aspetta(lambda: p.valuta("(document.querySelector('#principale .domanda-esercizio') "
                                       "|| {}).textContent"), 10)
        verifica("la scheda arriva con la domanda grande", dom == s.es.testo, dom)
        verifica("campo per scrivere e «Rispondi»", p.valuta(
            "!!document.querySelector('#principale .risposta-esercizio input') && "
            "!!document.querySelector('#principale .risposta-esercizio button')"))
        foto(p, "esercizi-schermo-domanda.png", 1280, 800)
        attesa = frazione_scritta(s.es.risposta)
        spieg = s.es.spiegazione
        verifica("la spiegazione non è nella pagina", dom_senza(p, spieg))
        sbagliata = frazione_scritta(s.es.risposta + 5)
        prima = s.es.firma
        scrivi_e_invia(p, sbagliata)
        ok = aspetta(lambda: p.valuta("!!document.querySelector('#principale .esito-esercizio.sbagliata')"), 8)
        verifica("risposta sbagliata scritta → esito «sbagliata» con l'indizio", bool(ok) and
                 "indizio" in (p.valuta("document.querySelector('#principale .esito-esercizio').textContent") or "").lower())
        verifica("stesso esercizio, nessuna soluzione", es.sessione(bianca.id).es.firma == prima
                 and dom_senza(p, spieg))
        foto(p, "esercizi-schermo-sbagliata.png", 1280, 800)
        tocca(p, "#principale [data-azione='aiuto']")
        ok = aspetta(lambda: es.sessione(bianca.id).aiuti >= 2, 5)
        verifica("«Un indizio» dalla scheda", bool(ok))
        scrivi_e_invia(p, attesa)
        ok = aspetta(lambda: p.valuta("!!document.querySelector('#principale .esito-esercizio.giusta')"), 8)
        verifica("risposta giusta scritta → esito «giusta» e domanda nuova", bool(ok) and
                 p.valuta("document.querySelector('#principale .domanda-esercizio').textContent")
                 == es.sessione(bianca.id).es.testo and es.sessione(bianca.id).es.firma != prima)
        foto(p, "esercizi-schermo-giusta.png", 1280, 800)
        nuova = es.sessione(bianca.id).es
        verifica("la risposta della domanda nuova non è nei dati della scheda", p.valuta(
            "JSON.stringify(window.calliopeSchermo.corrente())").find('"risposta"') < 0)
        tocca(p, "#principale [data-azione='segnala']")
        ok = aspetta(lambda: es.registro.segnalazioni(bianca.id), 5)
        verifica("«Secondo me è sbagliato» dalla scheda: segnalazione registrata", bool(ok))
        tocca(p, "#principale [data-azione='fine']")
        ok = aspetta(lambda: p.valuta("!document.querySelector('#principale .domanda-esercizio') && "
                                      "(document.querySelector('#principale .tipo-esercizio') || {}).innerText"), 8)
        verifica("«Basta così» → scheda finita con il conto", bool(ok) and "giust" in ok, ok)
        # Italiano: le scelte come pulsanti
        es.inizia(bianca, "bambini", 9, "italiano", "analisi grammaticale", "", mittente(bianca))
        s = es.sessione(bianca.id)
        n = aspetta(lambda: p.valuta("document.querySelectorAll('#principale .scelta-esercizio').length"), 8)
        verifica("italiano: le parti del discorso come pulsanti", n == len(s.es.scelte), n)
        foto(p, "esercizi-schermo-italiano.png", 1280, 800)
        giusta = s.es.risposta
        prima = s.es.firma
        p.valuta("(() => { const b = [...document.querySelectorAll('#principale .scelta-esercizio')]"
                 f".find(x => x.textContent === {json.dumps(giusta)}); b.scrollIntoView(); "
                 "b.click(); return 1; })()")
        ok = aspetta(lambda: es.sessione(bianca.id) and es.sessione(bianca.id).es.firma != prima, 8)
        verifica("italiano: il tocco sulla scelta giusta → esercizio nuovo", bool(ok))
        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("schermo: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()


def telefono(exe, srv, web, es, bianca):
    from calliope.esercizi.numeri import frazione_scritta
    _, token = srv.archivio.crea_con_token("telefono-bianca", proprietario=bianca.id,
                                           proprietario_nome=bianca.name)
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-tel-bianca",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: p.valuta("!!window.calliopeTelefono && window.calliopeTelefono.st.collegato"), 15)
        verifica("telefono: collegato", bool(ok))
        aspetta(lambda: p.valuta("!!window.calliopeSchermo && document.getElementById('stato')"
                                 ".className.includes('ok')"), 10)
        es.inizia(bianca, "bambini", 9, "matematica", "moltiplicazioni", "", mittente(bianca))
        s = es.sessione(bianca.id)
        dom = aspetta(lambda: p.valuta("(document.querySelector('#binario .tipo-esercizio .domanda-esercizio') "
                                       "|| {}).textContent"), 10)
        verifica("telefono: la scheda nel carosello con la domanda", dom == s.es.testo, dom)
        time.sleep(0.4)
        foto(p, "esercizi-telefono.png", 390, 844, mobile=True)
        prima = s.es.firma
        p.valuta("(() => { const i = document.querySelector('#binario .tipo-esercizio input');"
                 f" i.value = {json.dumps(frazione_scritta(s.es.risposta))}; return 1; }})()")
        tocca(p, "#binario .tipo-esercizio .risposta-esercizio button")
        ok = aspetta(lambda: es.sessione(bianca.id).es.firma != prima, 8)
        verifica("telefono: «Rispondi» con la risposta giusta → esercizio nuovo", bool(ok))
        ok = aspetta(lambda: p.valuta("!!document.querySelector('#binario .tipo-esercizio .esito-esercizio.giusta')"), 8)
        verifica("telefono: esito «giusta» nella scheda", bool(ok))
        fuori = p.valuta("(() => { const s = document.querySelector('#binario .tipo-esercizio');"
                         " const c = s.querySelector('.corpo'); return c.scrollWidth > c.clientWidth + 1; })()")
        verifica("telefono: niente testo che esce di lato", fuori is False, fuori)
        foto(p, "esercizi-telefono-giusta.png", 390, 844, mobile=True)
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
    PTP.TMP = TMP
    try:
        cfg, srv, hub, web, es, bianca = avvia()
        try:
            schermo(exe, hub, web, es, bianca)
            telefono(exe, srv, web, es, bianca)
        finally:
            web.ferma()
            srv.ferma()
            es.close()
            hub.archivio.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
