import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Abbinamento del telefono che riprende (03/10/2026, prova vera con un iPhone: per dire il
codice la persona esce da Edge, iOS sospende la pagina e chiude il WebSocket, e il token
mandato a una connessione morta si perdeva).

A secco (server degli schermi e dei satelliti veri su 127.0.0.1, client WebSocket finti con
l'Origin della pagina):
- `abbina` con `ripresa: true` → codice e ripresa; né la ripresa né il token in chiaro nel file;
- connessione chiusa, abbinamento «da terminale» senza nessuno collegato, connessione nuova con
  `riprendi` → il token, che vale; la stessa ripresa una seconda volta → «scaduto»;
- `riprendi` prima dell'abbinamento → lo stesso codice, poi il token sulla stessa connessione;
  «ricevuto» cancella la ripresa;
- ripresa a caso, il token di un'altra pagina come ripresa, ripresa scaduta → «scaduto», mai
  un token;
- abbinamento orfano (token mai consegnato): passata la scadenza sparisce da elenco e token;
  dopo la prima sessione non scade più; un satellite senza ripresa (il portatile) come prima;
- archivio di prima (schema 1): la migrazione aggiunge le colonne, i satelliti di prima non
  scadono.

Nel browser vero (Edge o Chromium senza finestra, DevTools; senza si salta): la pagina chiede
il codice, mostra «Puoi cambiare app…», la pagina «va in background» (visibilityState emulato
e WebSocket chiuso come fa iOS), l'abbinamento arriva sul server, la pagina torna in primo
piano e si collega da sola come satellite; pagina ricaricata con un codice in attesa → lo
stesso codice e poi il collegamento; dopo un ritorno in primo piano la sessione si riapre
subito. ~15 s.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="calliope-telabbina-"))
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


def porta_libera() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def avvia(cartella: Path):
    from calliope.config import Config
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
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
    web = ServerSchermi(hub, "127.0.0.1", porta_libera(), attesa_porta_s=5).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    return cfg, srv, hub, web


def invecchia(arch, tabella: str, colonna: str):
    """Porta nel passato le scadenze (niente attese di 10 minuti)."""
    with arch._lock:
        arch.db.execute(f"UPDATE {tabella} SET {colonna} = ? WHERE {colonna} IS NOT NULL",
                        (time.time() - 1,))
        arch.db.commit()


# ───────────────────────────── a secco ─────────────────────────────
def a_secco():
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    cfg, srv, hub, web = avvia(TMP / "secco")
    arch = srv.archivio
    ws_url = f"ws://127.0.0.1:{web.port}/telefono/ws/abbina"
    origine = {"Origin": f"http://127.0.0.1:{web.port}"}

    def apri():
        return connect(ws_url, additional_headers=origine, open_timeout=5)

    def riprendi(r, attendi_abbinato=False):
        with apri() as ws:
            ws.send(P.testo(tipo="riprendi", versione=2, ripresa=r))
            m = P.leggi(ws.recv(timeout=5))
            return m

    try:
        # 1. codice e ripresa; la connessione si chiude (pagina sospesa)
        with apri() as ws:
            ws.send(P.testo(tipo="abbina", versione=2, nome="telefono", personale="Dario",
                            ripresa=True))
            m = P.leggi(ws.recv(timeout=5))
        codice, rip = str(m.get("codice") or ""), str(m.get("ripresa") or "")
        verifica("codice di 6 cifre e una ripresa lunga", m.get("tipo") == "codice"
                 and len(codice) == 6 and len(rip) >= 40)
        time.sleep(0.3)
        # 2. abbinamento sul server mentre la pagina è sospesa
        res = arch.abbina(codice, "telefono")
        verifica("abbinato «da terminale» con la pagina scollegata", res["ok"])
        verifica("abbinamento in attesa di consegna", arch.in_consegna() == 1)
        # 3. ritorno: la ripresa ritira il token
        m = riprendi(rip)
        token = m.get("token")
        verifica("ripresa dopo l'abbinamento → il token", m.get("tipo") == "abbinato"
                 and bool(token) and m.get("satellite", {}).get("stanza") == "telefono")
        verifica("il token ritirato vale", arch.per_token(token) is not None)
        dati = Path(cfg.memory_db).read_bytes().decode("latin-1")
        wal = Path(cfg.memory_db + "-wal")
        if wal.exists():
            dati += wal.read_bytes().decode("latin-1")
        verifica("né la ripresa né il token in chiaro nel file", rip not in dati
                 and token not in dati)
        # 4. una volta sola
        m = riprendi(rip)
        verifica("la stessa ripresa una seconda volta → scaduto, niente token",
                 m.get("tipo") == "scaduto" and "token" not in m)
        # 5. prima sessione: consegnato, non scade più
        with connect(f"ws://127.0.0.1:{web.port}/telefono/ws/sessione",
                     additional_headers=origine) as s:
            s.send(P.testo(tipo="ciao", versione=2, token=token, primo=False, nome="telefono"))
            verifica("sessione con il token ritirato", P.leggi(s.recv(timeout=5)).get("tipo")
                     == "benvenuto")
        verifica("dopo la prima sessione non è più in consegna", arch.in_consegna() == 0)
        invecchia(arch, "satelliti", "consegna")
        verifica("e non scade", arch.per_token(token) is not None)

        # 6. ripresa prima dell'abbinamento: stesso codice, poi il token sulla stessa
        #    connessione; «ricevuto» cancella la ripresa
        with apri() as ws:
            ws.send(P.testo(tipo="abbina", versione=2, nome="telefono", ripresa=True))
            m = P.leggi(ws.recv(timeout=5))
        codice2, rip2 = m["codice"], m["ripresa"]
        with apri() as ws:
            ws.send(P.testo(tipo="riprendi", versione=2, ripresa=rip2))
            m = P.leggi(ws.recv(timeout=5))
            verifica("ripresa in attesa → lo stesso codice, senza una ripresa nuova",
                     m.get("tipo") == "codice" and m.get("codice") == codice2
                     and "ripresa" not in m and 0 < m.get("scade_s", 0) <= 600)
            arch.abbina(codice2, "cucina")
            m = P.leggi(ws.recv(timeout=5))
            verifica("abbinamento sulla connessione ripresa → token", m.get("tipo") == "abbinato"
                     and arch.per_token(m.get("token")) is not None)
            ws.send(P.testo(tipo="ricevuto"))
            try:
                ws.recv(timeout=5)
            except Exception:  # noqa: BLE001 — il server chiude
                pass
        verifica("dopo «ricevuto» la ripresa non vale più", riprendi(rip2).get("tipo") == "scaduto")
        verifica("e il token conta come consegnato", aspetta(lambda: arch.in_consegna() == 0, 3)
                 is True)

        # 7. riprese di altri: a caso, il token di un'altra pagina, scaduta
        import secrets
        verifica("ripresa a caso → scaduto", riprendi(secrets.token_urlsafe(32)).get("tipo")
                 == "scaduto")
        verifica("il token di un'altra pagina come ripresa → scaduto, niente token",
                 riprendi(token).get("tipo") == "scaduto")
        verifica("ripresa vuota → scaduto", riprendi("").get("tipo") == "scaduto")
        with apri() as ws:
            ws.send(P.testo(tipo="abbina", versione=2, nome="telefono", ripresa=True))
            m = P.leggi(ws.recv(timeout=5))
        codice3, rip3 = m["codice"], m["ripresa"]
        invecchia(arch, "satelliti_ripresa", "scade")
        verifica("ripresa scaduta → scaduto", riprendi(rip3).get("tipo") == "scaduto")
        with arch._lock:
            arch.db.execute("UPDATE satelliti_attesa SET scade = ?", (time.time() - 1,))
            arch.db.commit()
        verifica("e il suo codice non si abbina più", not arch.abbina(codice3, "studio")["ok"])

        # 8. abbinamento orfano: token mai consegnato
        with apri() as ws:
            ws.send(P.testo(tipo="abbina", versione=2, nome="telefono", ripresa=True))
            m = P.leggi(ws.recv(timeout=5))
        res = arch.abbina(m["codice"], "bagno")
        verifica("orfano: abbinato e in consegna", res["ok"] and arch.in_consegna() == 1)
        n_prima = len(arch.elenco())
        invecchia(arch, "satelliti", "consegna")
        verifica("orfano scaduto: tolto da solo", len(arch.elenco()) == n_prima - 1
                 and not any(s["stanza"] == "bagno" for s in arch.elenco())
                 and arch.in_consegna() == 0)
        verifica("e la sua ripresa non dà più il token", riprendi(m["ripresa"]).get("tipo")
                 == "scaduto")

        # 9. il portatile (senza ripresa): codice senza ripresa, token sulla connessione
        with connect(f"ws://127.0.0.1:{srv.port}" + P.PERCORSO_ABBINA, open_timeout=5) as ws:
            ws.send(P.testo(tipo="abbina", versione=2, nome="portatile"))
            m = P.leggi(ws.recv(timeout=5))
            verifica("satellite senza ripresa: nessuna ripresa nel codice",
                     m.get("tipo") == "codice" and "ripresa" not in m)
            arch.abbina(m["codice"], "studio")
            m = P.leggi(ws.recv(timeout=5))
            verifica("satellite senza ripresa: token sulla connessione",
                     m.get("tipo") == "abbinato" and arch.per_token(m["token"]) is not None)
    finally:
        web.ferma()
        srv.ferma()


def migrazione():
    """Un archivio dei satelliti di prima (schema 1): si apre, le colonne arrivano, i satelliti
    di prima restano e non scadono."""
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.schermi.archivio import ArchivioSchermi

    class Vecchio(ArchivioSchermi):
        TABELLA = "satelliti"

    db = str(TMP / "vecchio.db")
    v = Vecchio(db)
    _, token = v.crea_con_token("studio", ruolo="pc")
    v.close()
    a = ArchivioSatelliti(db)
    cols = {r[1] for r in a.db.execute("PRAGMA table_info(satelliti)")}
    verifica("migrazione: colonna consegna e tabella delle riprese", "consegna" in cols
             and a.db.execute("SELECT name FROM sqlite_master WHERE name='satelliti_ripresa'"
                              ).fetchone() is not None and a.scrivibile)
    verifica("migrazione: il satellite di prima vale e non è in consegna",
             a.per_token(token) is not None and a.in_consegna() == 0)
    a.close()


# ───────────────────────────── browser ─────────────────────────────
def nel_browser():
    import prova_telefono_pagina as PTP
    shutil.rmtree(PTP.TMP, ignore_errors=True)        # la sua cartella: i profili vanno qui
    PTP.TMP = TMP
    exe = PTP.browser()
    if exe is None:
        print("SALTATA IN PARTE: Nessun Edge né Chromium: parte nel browser saltata.")
        return
    if True:
        cfg, srv, hub, web = avvia(TMP / "browser")
        arch = srv.archivio
        url = f"http://127.0.0.1:{web.port}/telefono/"
        pagina = PTP.Pagina(exe, url, profilo="profilo-abbina")
        try:
            browser_scenari(pagina, srv, arch)
        finally:
            pagina.chiudi()
            web.ferma()
            srv.ferma()


# Visibilità emulata: document.visibilityState non si cambia dal DevTools senza finestra,
# quindi si ridefinisce e si manda l'evento, come fa il browser
EMULA = """(() => {
  if (!window.__vis) {
    window.__vis = 'visible';
    Object.defineProperty(document, 'visibilityState', { get: () => window.__vis, configurable: true });
    Object.defineProperty(document, 'hidden', { get: () => window.__vis === 'hidden', configurable: true });
  }
})(); 1"""


def visibilita(pagina, stato):
    pagina.valuta(EMULA)
    pagina.valuta(f"window.__vis = '{stato}'; document.dispatchEvent(new Event('visibilitychange')); 1")


def browser_scenari(pagina, srv, arch):
    T = "window.calliopeTelefono"
    ok = aspetta(lambda: pagina.valuta(f"!!{T}"), 15)
    verifica("browser: pagina caricata", bool(ok))
    if not ok:
        return
    testo = lambda id_: pagina.valuta(f"(document.getElementById('{id_}')||{{}}).textContent || ''")
    pagina.valuta("document.getElementById('tel-nome').value='Dario';"
                  "document.getElementById('tel-chiedi').click(); 1")
    cod = aspetta(lambda: testo("tel-codice-cifre").replace(" ", ""), 10)
    verifica("browser: codice mostrato", bool(cod) and len(cod) == 6)
    salvato = pagina.valuta(f"{T}.abbinamento().salvato") or {}
    verifica("browser: ripresa e codice in localStorage", salvato.get("codice") == cod
             and len(salvato.get("ripresa") or "") >= 40)
    verifica("browser: il messaggio «Puoi cambiare app…» è visibile",
             "Puoi cambiare app per dire il codice" in testo("tel-cambia-app")
             and pagina.valuta("!document.getElementById('tel-codice').hidden") is True)

    # La persona passa a un'altra app: pagina nascosta e WebSocket chiuso (iOS)
    visibilita(pagina, "hidden")
    pagina.valuta(f"{T}.chiudiAbbina(); 1")
    time.sleep(0.5)
    verifica("browser: in background nessuna connessione riaperta",
             pagina.valuta(f"{T}.abbinamento().aperto") is False)
    res = arch.abbina(cod, "telefono", proprietario="dario", proprietario_nome="Dario")
    verifica("browser: abbinato sul server con la pagina sospesa", res["ok"])
    collegati_prima = srv.collegati_in_tutto
    t0 = time.monotonic()
    visibilita(pagina, "visible")
    ok = aspetta(lambda: pagina.stato().get("collegato"), 10)
    verifica("browser: tornata in primo piano si abbina e si collega da sola", bool(ok),
             f"{time.monotonic() - t0:.2f} s")
    verifica("browser: token salvato, ripresa tolta", pagina.valuta(
        f"{T}.abbinamento().token && !{T}.abbinamento().salvato") is True)
    verifica("browser: token consegnato (nessun abbinamento orfano)",
             aspetta(lambda: arch.in_consegna() == 0, 5) is True
             and srv.collegati_in_tutto > collegati_prima)
    stato = pagina.valuta("document.getElementById('tel-stato-testo').textContent")
    verifica("browser: lo stato dice «collegata»", stato == "collegata", stato)

    # Sessione che riprende: nascosta per più di 3 s, al ritorno si riapre subito
    visibilita(pagina, "hidden")
    pagina.valuta(f"{T}.chiudiSessione(); 1")
    time.sleep(3.3)
    n = srv.collegati_in_tutto
    t0 = time.monotonic()
    visibilita(pagina, "visible")
    stato = pagina.valuta("document.getElementById('tel-stato-testo').textContent")
    verifica("browser: al ritorno lo stato dice che riprende", "ripren" in stato
             or stato == "collegata", stato)
    ok = aspetta(lambda: srv.collegati_in_tutto > n and pagina.stato().get("collegato"), 5)
    verifica("browser: sessione riaperta subito al ritorno in primo piano", bool(ok),
             f"{time.monotonic() - t0:.2f} s")

    # Pagina ricaricata con un codice in attesa: lo stesso codice, poi il collegamento
    pagina.valuta(f"localStorage.removeItem('calliope.telefono.token'); 1")
    pagina._chiama("Page.reload")
    time.sleep(0.5)
    aspetta(lambda: pagina.valuta(f"!!{T}"), 15)
    pagina.valuta("document.getElementById('tel-chiedi').click(); 1")
    cod2 = aspetta(lambda: testo("tel-codice-cifre").replace(" ", ""), 10)
    pagina._chiama("Page.reload")
    time.sleep(0.5)
    aspetta(lambda: pagina.valuta(f"!!{T}"), 15)
    cod3 = aspetta(lambda: testo("tel-codice-cifre").replace(" ", ""), 10)
    verifica("browser: ricaricata, mostra lo stesso codice", bool(cod2) and cod2 == cod3,
             f"{cod2} / {cod3}")
    aspetta(lambda: pagina.valuta(f"{T}.abbinamento().aperto"), 5)
    arch.abbina(cod3, "salotto")
    ok = aspetta(lambda: pagina.stato().get("collegato"), 10)
    verifica("browser: e si collega appena abbinata", bool(ok))
    pagina.pompa(0.3)
    errori = [r for r in pagina.log if r.startswith("ECCEZIONE") or "Content Security" in r]
    verifica("browser: nessun errore JavaScript né violazione della CSP", not errori,
             "; ".join(errori)[:300])


def main() -> int:
    try:
        a_secco()
        migrazione()
        nel_browser()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
