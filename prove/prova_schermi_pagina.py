import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La pagina degli schermi in un browser vero (Edge o Chromium senza finestra, comandato con
il protocollo DevTools): dopo un riavvio del server deve tornare collegata da sola (02/10).

Sulla DGX, dopo «calliope aggiorna», la pagina aperta dal satellite non si è più
ricollegata («1 schermo abbinato, 0 collegati ora») finché non si è riavviato il satellite.
Qui: pagina abbinata e collegata → schede con identità (un timer annullato
è la stessa scheda, spostata in cima; un aggiornamento automatico resta al suo posto; al
riaggancio niente doppioni) → server fermato (come un processo che esce) → dopo
qualche secondo un server nuovo sulla stessa porta e con lo stesso archivio (le sessioni,
in memoria, non valgono più) → la pagina deve ricollegarsi da sola, mostrare
«riconnessione…» mentre aspetta, e disegnare la scheda mandata dopo.

    python prove/prova_schermi_pagina.py            server giù 5 s
    python prove/prova_schermi_pagina.py --lungo    anche giù 60 s (più di un minuto in tutto)

Senza Edge né Chromium la prova si salta (esce con 0 e lo dice). Usa websockets (già nelle
dipendenze del satellite) per il protocollo DevTools. Tutto in una cartella temporanea.
"""

import json
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Mittente, Schermi, schede
from calliope.schermi.server import ServerSchermi

TMP = Path(tempfile.mkdtemp(prefix="calliope-pagina-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def browser() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).is_file():
            return c
    for e in ("msedge", "chromium", "chromium-browser", "google-chrome"):
        if shutil.which(e):
            return shutil.which(e)
    return None


def porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Pagina:
    """Una scheda del browser comandata con Runtime.evaluate."""

    def __init__(self, exe: str, url: str, opzioni=(), profilo="profilo"):
        # Porta di DevTools scelta dal browser e chiusura dell'albero intero (cdp.py, 06/10)
        from cdp import Browser
        self.browser = Browser(exe, TMP / profilo, opzioni, url)
        self.dbg = self.browser.porta
        self.proc = self.browser.proc
        try:
            # Solo la scheda della pagina: Edge apre a volte anche le sue (finestra
            # della sincronizzazione al primo avvio di un profilo nuovo)
            ws_url = self.browser.ws_pagina(url.split("#")[0])
        except RuntimeError:
            self.browser.chiudi()
            raise
        from websockets.sync.client import connect
        self._cm = connect(ws_url, max_size=2 ** 24)
        self.ws = self._cm.__enter__()
        self.n = 0

    def valuta(self, espressione: str):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": "Runtime.evaluate",
                                 "params": {"expression": espressione, "returnByValue": True}}))
        while True:
            m = json.loads(self.ws.recv(timeout=10))
            if m.get("id") == self.n:
                return m.get("result", {}).get("result", {}).get("value")

    def stato(self) -> str:
        return self.valuta("(document.getElementById('stato-testo')||{}).textContent||''") or ""

    def titolo_scheda(self) -> str:
        return self.valuta("(document.querySelector('.scheda .titolo')||{}).textContent||''") or ""

    def chiudi(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass
        self.browser.chiudi()


def aspetta(cond, max_s: float, passo: float = 0.25) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        if cond():
            return time.monotonic() - t0
        time.sleep(passo)
    return None


def cronologia(pagina: Pagina) -> list[str]:
    """I titoli dei bottoni della cronologia, dall'alto (la più recente) in giù."""
    return pagina.valuta("[...document.querySelectorAll('#cronologia button .t-titolo')]"
                         ".map(e => e.textContent)") or []


def identita(pagina: Pagina, hub):
    """Schede con identità nella pagina vera: aggiornata = stessa scheda spostata in cima;
    aggiornamento automatico (sposta: false) = al suo posto e non in primo piano; al
    riaggancio niente doppioni."""
    io = Mittente(persona="p1", nome="Dario", livello="amministra", certo=True)
    item = {"id": 9, "label": "per la pasta", "due": time.time() + 300}
    hub.invia(schede.timer(item), io)
    hub.invia(schede.calcolo("2+2", "4"), io)
    hub.invia(schede.timer(item, "annullato"), io)
    aspetta(lambda: "annullato" in (pagina.valuta(
        "(document.querySelector('.scheda .resto')||{}).textContent||''") or ""), 5)
    cr = cronologia(pagina)
    verifica("pagina: timer annullato = la stessa scheda, in cima, una volta sola",
             cr[:1] == ["Timer per la pasta"] and cr.count("Timer per la pasta") == 1, str(cr))
    verifica("pagina: mostra «annullato alle …»", "annullato alle" in (pagina.valuta(
        "(document.querySelector('.scheda .resto')||{}).textContent||''") or ""))
    doc = {"titolo": "Disdetta", "blocchi": [{"tipo": "paragrafo", "testo": "x"}]}
    # Pubblica solo qui: lo schermo della prova non è personale
    hub.invia(dict(schede.documento(doc, "word", "Disdetta.docx", ident=5),
                   visibilita=schede.PUBBLICA), io)
    aspetta(lambda: pagina.titolo_scheda() == "Disdetta", 5)
    hub.invia(schede.aggiornamento(schede.timer(dict(item, label="per la pasta lunga"))), io)
    # Si aspetta che l'aggiornamento arrivi (sotto carico più di 1 s), poi si guarda dov'è
    aspetta(lambda: "Timer per la pasta lunga" in cronologia(pagina), 10)
    cr2 = cronologia(pagina)
    verifica("pagina: aggiornamento automatico al suo posto, il documento resta in primo piano",
             pagina.titolo_scheda() == "Disdetta" and cr2[0] == "Disdetta"
             and "Timer per la pasta lunga" in cr2 and "Timer per la pasta" not in cr2, str(cr2))
    hub.chiudi_tutte()                    # flusso chiuso: la pagina si ricollega
    t = aspetta(lambda: not hub.collegati(), 5)
    aspetta(lambda: hub.collegati(), 20)
    # La cronologia rimandata al riaggancio arriva dopo il collegamento: si aspetta che sia
    # tornata quella di prima (un doppione resterebbe e la prova lo vedrebbe dopo 10 s)
    aspetta(lambda: cronologia(pagina) == cr2, 10)
    time.sleep(0.3)
    cr3 = cronologia(pagina)
    verifica("pagina: dopo il riaggancio la cronologia è la stessa, senza doppioni",
             cr3 == cr2, f"{cr3} (scollegata in {t})")


def lavoro(pagina: Pagina, hub):
    """L'avanzamento di un lavoro dell'agente (03/10) nella pagina vera: la scheda in corso
    con il passo, i tetti, il testo in arrivo e i file; gli aggiornamenti al loro posto (anche
    quando in primo piano c'è un'altra scheda), il tempo che conta da solo, la finale che la
    sostituisce; una sola voce nella cronologia; nessun errore JavaScript."""
    io = Mittente(persona="p1", nome="Dario", livello="amministra", certo=True)
    pagina.valuta("window.__errori = []; window.addEventListener('error', "
                  "(e) => window.__errori.push(String(e.message)))")

    def av(passo, flusso=None, file=(), pausa=False, passate=1, trascorso=4.0):
        return {"passo": passo, "pausa": pausa, "passi": [{"ora": time.time(), "testo": passo}],
                "file": [{"nome": n, "righe": 3} for n in file],
                "anteprima": {"nome": file[0], "testo": "def somma(a, b):\n    return a + b"}
                if file else None, "flusso": flusso, "test": None, "passate": passate,
                "max_passate": 24, "token": 1200 * passate, "max_token": 60000,
                "trascorso_s": trascorso, "max_s": 1800, "dal": time.time() - trascorso,
                "ora_server": time.time()}

    def manda(card):
        hub.invia(dict(card, visibilita=schede.PUBBLICA), io)

    manda(schede.lavoro_avanzamento("script delle foto", "codice", "in_coda", av(""),
                                    ident="L7", sposta=True))
    aspetta(lambda: pagina.titolo_scheda() == "script delle foto", 5)
    manda(schede.lavoro_avanzamento("script delle foto", "codice", "in_corso", av(
        "sta pensando al codice", {"tipo": "pensiero", "testo": "Guardo i file e poi"}),
        ident="L7"))
    passo = lambda: pagina.valuta(  # noqa: E731
        "(document.querySelector('.passo-lavoro')||{}).textContent||''") or ""
    verifica("pagina: lavoro in corso, aggiornato al suo posto con il passo",
             aspetta(lambda: passo() == "Adesso: sta pensando al codice", 5) is not None, passo())
    verifica("pagina: il testo in arrivo (ragionamento)", "Guardo i file" in (pagina.valuta(
        "(document.querySelector('pre.flusso.pensiero')||{}).textContent||''") or ""))
    tempo = lambda: pagina.valuta(  # noqa: E731
        "(document.querySelector('.tetto-valore[data-dal]')||{}).textContent||''") or ""
    t1 = tempo()
    aspetta(lambda: tempo() != t1, 10)
    verifica("pagina: il tempo conta da solo, con il suo massimo («di 30 min al massimo»)",
             t1 != tempo() and "di 30 min al massimo" in tempo(), f"{t1} → {tempo()}")
    # Un'altra scheda in primo piano: l'aggiornamento non la scavalca
    hub.invia(schede.calcolo("2+2", "4"), io)
    aspetta(lambda: pagina.valuta("!!document.querySelector('.scheda.tipo-calcolo')"), 5)
    manda(schede.lavoro_avanzamento("script delle foto", "codice", "in_corso", av(
        "scrive rinomina.py", file=("rinomina.py",), passate=3), ident="L7"))
    time.sleep(0.8)
    cr = cronologia(pagina)
    verifica("pagina: con un calcolo davanti l'aggiornamento resta dietro, una voce sola",
             pagina.valuta("!!document.querySelector('.scheda.tipo-calcolo')") is True
             and cr.count("script delle foto") == 1 and cr[0] != "script delle foto", str(cr))
    pagina.valuta("[...document.querySelectorAll('#cronologia button')].find(b => "
                  "b.textContent.includes('script delle foto')).click()")
    aspetta(lambda: passo() == "Adesso: scrive rinomina.py", 5)
    verifica("pagina: i file scritti finora e l'anteprima del codice",
             "rinomina.py" in (pagina.valuta(
                 "(document.querySelector('.elenco-file')||{}).textContent||''") or "")
             and "return a + b" in (pagina.valuta(
                 "(document.querySelector('pre.codice.anteprima')||{}).textContent||''") or ""))
    manda(schede.lavoro_avanzamento("script delle foto", "codice", "in_corso", av(
        "scrive rinomina.py", pausa=True), ident="L7"))
    verifica("pagina: «in pausa: sto rispondendo a voce»", aspetta(lambda: "in pausa" in (
        pagina.valuta("(document.querySelector('.badge.pausa')||{}).textContent||''") or ""), 5)
        is not None)
    fin = schede.lavoro("script delle foto", "codice", "fatto", "Ho scritto lo script.",
                        [{"nome": "rinomina.py", "testo": "print(1)\n"}],
                        {"eseguiti": 3, "falliti": 0}, "2026-10-03 lavoro", ident="L7")
    fin["avanzamento"] = av("controlla i test", passate=5)
    manda(fin)
    verifica("pagina: la finale sostituisce la scheda in corso e va in primo piano",
             aspetta(lambda: "finito" in (pagina.valuta(
                 "(document.querySelector('.scheda.tipo-lavoro .sotto')||{}).textContent||''")
                 or ""), 5) is not None and cronologia(pagina)[0] == "script delle foto"
             and cronologia(pagina).count("script delle foto") == 1, str(cronologia(pagina)))
    errori = pagina.valuta("window.__errori") or []
    verifica("pagina: nessun errore JavaScript", not errori, str(errori))


def aggiornamenti(pagina: Pagina, hub):
    """Aggiornamenti frequenti della stessa scheda (04/10: la scheda dell'avanzamento
    lampeggiava, ricostruita due volte al secondo): l'elemento resta lo stesso, l'animazione di
    entrata non riparte, l'uscita in fondo resta in fondo e chi è risalito non viene riportato
    giù; il cambio di stato dà solo un segno leggero; una scheda nuova entra con l'animazione."""
    io = Mittente(persona="p1", nome="Dario", livello="amministra", certo=True)
    pagina.valuta("window.__entra = 0; document.addEventListener('animationstart', (e) => {"
                  " if (e.animationName === 'entra') window.__entra++; }, true)")
    righe = []

    def manda(stato="in_corso", sposta=False, n=0):
        base = len(righe)
        righe.extend([f"riga {base + i}: {i} x {i} = {i * i}\n" for i in range(n)])
        card = schede.esecuzione("calcolo", "Program.cs", "C#", stato, ["3"],
                                 [{"tipo": "out", "testo": "".join(righe)}], 0,
                                 0 if stato != "in_corso" else None, time.time() - 2, 2.0, 60,
                                 ident="L9-1", sposta=sposta)
        hub.invia(dict(card, visibilita=schede.PUBBLICA), io)

    uscita = lambda: pagina.valuta(  # noqa: E731
        "(document.querySelector('pre.uscita-esecuzione')||{}).textContent||''") or ""
    manda(sposta=True, n=3)
    aspetta(lambda: pagina.titolo_scheda() == "calcolo", 5)
    time.sleep(0.5)                       # l'animazione di entrata della scheda nuova finisce
    pagina.valuta("window.__art = document.querySelector('#principale > article.scheda');"
                  "window.__entra = 0")
    for _ in range(20):
        manda(n=4)
        time.sleep(0.05)
    aspetta(lambda: f"riga {len(righe) - 1}:" in uscita(), 5)
    verifica("pagina: 20 aggiornamenti della stessa scheda, lo stesso elemento",
             pagina.valuta("document.querySelector('#principale > article.scheda') === "
                           "window.__art") is True and f"riga {len(righe) - 1}:" in uscita())
    verifica("pagina: nessuna animazione di entrata ripartita", pagina.valuta("window.__entra")
             == 0, str(pagina.valuta("window.__entra")))
    in_fondo = ("(p => p.scrollHeight - p.scrollTop - p.clientHeight < 24)"
                "(document.querySelector('pre.uscita-esecuzione'))")
    verifica("pagina: l'uscita resta in fondo mentre arriva", pagina.valuta(in_fondo) is True)
    pagina.valuta("document.querySelector('pre.uscita-esecuzione').scrollTop = 0")
    manda(n=4)
    aspetta(lambda: f"riga {len(righe) - 1}:" in uscita(), 5)
    verifica("pagina: chi è risalito nell'uscita non viene riportato giù",
             pagina.valuta("document.querySelector('pre.uscita-esecuzione').scrollTop") == 0)
    manda("fatto", sposta=True)
    aspetta(lambda: "finito" in (pagina.valuta(
        "(document.querySelector('.scheda .sotto')||{}).textContent||''") or ""), 5)
    verifica("pagina: cambio di stato = la stessa scheda con un segno leggero, niente entrata",
             pagina.valuta("window.__art.isConnected && window.__art.classList.contains("
                           "'cambiata')") is True and pagina.valuta("window.__entra") == 0)
    hub.invia(schede.calcolo("3+3", "6"), io)
    aspetta(lambda: pagina.valuta("!!document.querySelector('.scheda.tipo-calcolo')"), 5)
    time.sleep(0.2)
    verifica("pagina: una scheda nuova entra con la sua animazione",
             (pagina.valuta("window.__entra") or 0) >= 1, str(pagina.valuta("window.__entra")))
    errori = pagina.valuta("window.__errori") or []
    verifica("pagina: nessun errore JavaScript negli aggiornamenti", not errori, str(errori))


def avvia(db: str, port: int) -> tuple[Schermi, ServerSchermi]:
    cfg = Config()
    cfg.config_dir = str(TMP)
    hub = Schermi(cfg, ArchivioSchermi(db), log=lambda m: None)
    srv = ServerSchermi(hub, "127.0.0.1", port, attesa_porta_s=5).avvia()
    hub.server = srv
    return hub, srv


def giro(pagina: Pagina, db: str, port: int, hub, srv, giu_s: float, n: int):
    srv.ferma()
    hub.archivio.close()
    visto = aspetta(lambda: "riconnessione" in pagina.stato(), 20)
    verifica(f"[{n}] server fermato: la pagina dice «riconnessione…»", visto is not None,
             pagina.stato())
    time.sleep(max(0.0, giu_s - (visto or 0)))
    verifica(f"[{n}] dopo {giu_s:.0f} s ancora in riconnessione (mai ferma)",
             "riconnessione" in pagina.stato(), pagina.stato())
    hub, srv = avvia(db, port)
    t = aspetta(lambda: hub.collegati(), 25)
    verifica(f"[{n}] server nuovo (sessioni vecchie non valide): la pagina si ricollega da sola",
             t is not None, f"in {t:.1f} s" if t is not None else "")
    titolo = f"Scheda dopo il riavvio {n}"
    hub.invia(dict(schede.nuova("testo", titolo, schede.PUBBLICA), testo="ciao"),
              Mittente(persona="p1", nome="Dario", livello="amministra", certo=True))
    t = aspetta(lambda: pagina.titolo_scheda() == titolo, 10)
    verifica(f"[{n}] e mostra la scheda mandata dopo", t is not None, pagina.titolo_scheda())
    verifica(f"[{n}] stato «collegato»", pagina.stato() == "collegato", pagina.stato())
    return hub, srv


def https(exe: str):
    """La pagina in HTTPS con il certificato autofirmato dei satelliti (02/10): aperta
    direttamente il browser si ferma all'errore del certificato; attraverso il ponte TLS del
    satellite (http://127.0.0.1, impronta verificata) si collega, mostra le schede ed è un
    contesto sicuro. Il 02/10 si era provato anche --ignore-certificate-errors-spki-list
    con un profilo dedicato: Edge 154 lo ignora («Errore di privacy»)."""
    from calliope.schermi.ponte import PonteTLS
    from calliope.satellite.__main__ import _openssl, certificato
    from calliope.schermi import tls
    if _openssl() is None:
        print("SALTATA IN PARTE: openssl non c'è: salto la parte in HTTPS")
        return
    cartella = TMP / "https"
    cartella.mkdir(exist_ok=True)
    cfg = Config()
    cfg.config_dir = str(cartella)
    cfg.schermi_indirizzo = "0.0.0.0"           # solo per scegliere https (non si apre qui)
    certificato(cfg, out=lambda m: None)
    modo, t = tls.modo(cfg)
    hub = Schermi(cfg, ArchivioSchermi(str(cartella / "m.db")), log=lambda m: None)
    port = porta_libera()
    srv = ServerSchermi(hub, "127.0.0.1", port, attesa_porta_s=5, tls=t).avvia()
    hub.server, hub.tls = srv, t
    r = hub.archivio.nuova_richiesta()
    hub.archivio.abbina(r["codice"], "studio")
    url = f"https://127.0.0.1:{port}/#t={r['richiesta']}"
    senza = Pagina(exe, url, profilo="profilo-https-senza")
    try:
        t_senza = aspetta(lambda: hub.collegati(), 6)
    finally:
        senza.chiudi()
    verifica("HTTPS senza l'impronta: il browser non si collega (certificato non fidato)",
             modo == "https" and t_senza is None)
    ponte = PonteTLS("127.0.0.1", port, t["impronta"], log=lambda m: None)
    con = Pagina(exe, f"{ponte.url}/#t={r['richiesta']}", profilo="profilo-https")
    try:
        t_con = aspetta(lambda: hub.collegati(), 20)
        verifica("HTTPS attraverso il ponte TLS del satellite: collegata", t_con is not None,
                 f"in {t_con:.1f} s" if t_con is not None else "")
        hub.invia(dict(schede.nuova("testo", "Scheda in HTTPS", schede.PUBBLICA), testo="ok"),
                  Mittente(persona="p1", nome="Dario", livello="amministra", certo=True))
        verifica("HTTPS: la scheda arriva",
                 aspetta(lambda: con.titolo_scheda() == "Scheda in HTTPS", 10) is not None,
                 con.titolo_scheda())
        verifica("HTTPS: contesto sicuro (serve al microfono della futura web app)",
                 con.valuta("window.isSecureContext") is True)
    finally:
        con.chiudi()
        ponte.ferma()
        srv.ferma()
        hub.archivio.close()


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main() -> int:
    exe = browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    db = str(TMP / "memoria.db")
    port = porta_libera()
    hub, srv = avvia(db, port)
    r = hub.archivio.nuova_richiesta()
    hub.archivio.abbina(r["codice"], "studio")
    pagina = Pagina(exe, f"http://127.0.0.1:{port}/#t={r['richiesta']}")
    try:
        t = aspetta(lambda: hub.collegati(), 20)
        verifica("pagina abbinata e collegata", t is not None)
        identita(pagina, hub)
        lavoro(pagina, hub)
        aggiornamenti(pagina, hub)
        hub, srv = giro(pagina, db, port, hub, srv, 5.0, 1)
        if "--lungo" in sys.argv:
            hub, srv = giro(pagina, db, port, hub, srv, 60.0, 2)
        https(exe)
    finally:
        pagina.chiudi()
        srv.ferma()
        hub.archivio.close()
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
