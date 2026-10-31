import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La condivisione dal telefono allo Studio a secco (31/10, issue #298 parte 3, epic #251, decisione
0035; share_target nel manifest della PWA, telefono/sw.js, telefono/condividi.js, POST
/telefono/condividi).

1. **Il manifest**: `share_target` con l'azione dentro lo scope della PWA, POST multipart, un campo
   «file» che accetta i formati dell'importazione (PDF, immagini, Office, OpenDocument, testo, ZIP) e
   non altri (niente eseguibili, niente «*/*»).
2. **Il service worker**: intercetta solo il POST di `/telefono/condividi` dalla sua origine, tiene i
   file in IndexedDB sul telefono (al più 10, la condivisione nuova sostituisce la vecchia) e manda la
   pagina a «?condividi=1»; nella cache c'è condividi.js; la versione della cache è quella della
   pagina.
3. **La pagina** (condividi.js): manda i file solo con `studioImporta` (la stessa importazione di
   «Aggiungi materiali»), dopo la scelta della verifica fatta dalla persona (il tasto spento senza
   scelta, nessuna verifica scelta da sola), nomi solo con textContent, nessun innerHTML, i file tolti
   dal telefono dopo l'invio e dopo un'ora.
4. **Il server**: un POST a `/telefono/condividi` che arriva al server (service worker non attivo)
   torna 303 a «?condividi=0» senza leggere il corpo e senza creare niente; condividi.js è servito.

    python prove/prova_studio_condividi.py
"""

import json
import re
import shutil
import socket
import tempfile
import time
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

ERRORI = []
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-condividi-"))
TEL = QUI.parent / "calliope" / "schermi" / "pagina" / "telefono"


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


def prova_manifest():
    print("— il manifest")
    m = json.loads((TEL / "manifest.webmanifest").read_text("utf-8"))
    s = m.get("share_target") or {}
    verifica("share_target: azione dentro lo scope, POST multipart",
             s.get("action") == "/telefono/condividi" and s["action"].startswith(m["scope"])
             and s.get("method") == "POST" and s.get("enctype") == "multipart/form-data")
    f = (s.get("params") or {}).get("files") or []
    acc = set(f[0].get("accept") or []) if f else set()
    verifica("un campo «file» coi formati dell'importazione",
             len(f) == 1 and f[0].get("name") == "file"
             and {".pdf", "image/jpeg", ".docx", ".pptx", ".xlsx", ".odt", ".txt", ".md", ".zip"} <= acc)
    verifica("niente eseguibili, script né «tutto»",
             not any(x in acc for x in ("*/*", "application/*", ".exe", ".apk", ".js", ".bat",
                                        "application/octet-stream")), sorted(acc))


def prova_sw_e_pagina():
    print("— il service worker e la pagina")
    sw = (TEL / "sw.js").read_text("utf-8")
    tel = (TEL / "telefono.js").read_text("utf-8")
    v_sw = re.search(r'const CACHE = "(calliope-telefono-pagina-v\d+)"', sw)
    v_tel = re.search(r'const PAGINA_VERSIONE = "(calliope-telefono-pagina-v\d+)"', tel)
    verifica("la versione della cache è quella della pagina (v39)",
             v_sw and v_tel and v_sw.group(1) == v_tel.group(1) == "calliope-telefono-pagina-v39")
    verifica("il service worker prende solo il POST di /telefono/condividi dalla sua origine",
             'ev.request.method === "POST" && u.origin === location.origin && u.pathname === '
             '"/telefono/condividi"' in sw)
    verifica("i file in IndexedDB, al più 10, la nuova condivisione sostituisce la vecchia, poi "
             "«?condividi=1»", "CONDIVISI_MAX = 10" in sw and "s.clear()" in sw
             and "indexedDB.open" in sw and '"/telefono/?condividi="' in sw
             and "fetch(" not in sw.split("async function condividi")[1].split("self.addEventListener")[0])
    verifica("condividi.js nella cache della pagina", '"/telefono/condividi.js"' in sw)
    c = (TEL / "condividi.js").read_text("utf-8")
    verifica("la pagina manda solo con studioImporta (la stessa importazione), mai con fetch suo",
             "studioImporta(" in c and "fetch(" not in c and "XMLHttpRequest" not in c)
    verifica("niente innerHTML né insertAdjacentHTML: i nomi solo con textContent",
             "innerHTML" not in c and "insertAdjacentHTML" not in c and "textContent" in c)
    verifica("la verifica la sceglie la persona: la prima scelta è vuota e il tasto è spento senza",
             'new Option("Scegli la verifica…", "")' in c and '!sel.value' in c
             and "Number($(\"condividi-verifica\").value)" in c)
    verifica("i file tolti dal telefono dopo l'invio e dopo un'ora",
             "await svuota()" in c and "DURATA_MS = 3600 * 1000" in c)
    # Revisione della PR #369
    verifica("il service worker prende solo la condivisione del sistema: una navigazione senza "
             "referrer", 'ev.request.mode !== "navigate" || ev.request.referrer' in sw)
    verifica("la pulizia dei file vecchi anche nel service worker, all'«activate» e a ogni apertura",
             "CONDIVISI_DURATA_MS = 3600 * 1000" in sw and ".then(() => pulisciCondivisi())" in sw
             and "ev.waitUntil(pulisciCondivisi())" in sw)
    verifica("la pagina chiede di controllare che siano i file condivisi dalla persona",
             "controlla che siano i file che hai condiviso tu" in c)
    verifica("la pagina controlla il tetto prima di mandare (importa_max_mb)",
             "importa_max_mb" in c and "f.dim) > mb * 1000000" in c)
    idx = (TEL / "index.html").read_text("utf-8")
    verifica("la pagina carica condividi.js e ha il riquadro in Le mie cose, sotto le tessere",
             '<script src="/telefono/condividi.js" defer></script>' in idx
             and 'id="condividi"' in idx and idx.index('id="condividi"') > idx.index('id="tessere"') > idx.index('id="sez-cose"'))


def prova_server():
    print("— il server")
    import prova_telefono_schermo as PTS
    import urllib.request
    cfg, srv, hub, web = PTS.avvia(TMP / "server")
    try:
        port = web.port
        # Un POST grande dichiarato e mai mandato: la risposta arriva subito, senza leggere il corpo
        t0 = time.monotonic()
        s = socket.create_connection(("127.0.0.1", port), timeout=10)
        s.sendall(b"POST /telefono/condividi HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                  b"Content-Type: multipart/form-data; boundary=x\r\nContent-Length: 50000000\r\n\r\n"
                  b"--x\r\n")
        risposta = b""
        while b"\r\n\r\n" not in risposta:
            pezzo = s.recv(4096)
            if not pezzo:
                break
            risposta += pezzo
        s.close()
        testa = risposta.split(b"\r\n\r\n")[0].decode("latin-1")
        verifica("POST arrivato al server: 303 a «?condividi=0» entro il tempo per buttare il "
                 "corpo, senza tenerlo", testa.startswith("HTTP/1.1 303")
                 and "/telefono/?condividi=0" in testa and time.monotonic() - t0 < 5, testa[:200])
        # Un file vero mandato davvero (revisione della PR #369): il 303 arriva, non un RST
        import threading
        s = socket.create_connection(("127.0.0.1", port), timeout=10)
        corpo = (b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
                 + b"z" * 3_000_000 + b"\r\n--x--\r\n")
        s.sendall(b"POST /telefono/condividi HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                  b"Content-Type: multipart/form-data; boundary=x\r\n"
                  + f"Content-Length: {len(corpo)}\r\n\r\n".encode())
        threading.Thread(target=lambda: s.sendall(corpo), daemon=True).start()
        risposta = b""
        try:
            while b"\r\n\r\n" not in risposta:
                pezzo = s.recv(4096)
                if not pezzo:
                    break
                risposta += pezzo
        except ConnectionResetError:
            risposta += b"RST"
        s.close()
        verifica("un file vero di 3 MB mandato al server: arriva il 303, non un RST",
                 risposta.startswith(b"HTTP/1.1 303"), risposta[:80])
        verifica("niente salvato nella cartella del server", not list((TMP / "server").rglob("*.pdf")))

        class NoRedir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedir)
        try:
            op.open(f"http://127.0.0.1:{port}/telefono/condividi")
            st_ = 200
        except urllib.error.HTTPError as e:
            st_ = e.code
        verifica("GET di /telefono/condividi: 303 anche lui", st_ == 303, st_)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/telefono/condividi.js") as r:
            verifica("condividi.js servito come script", r.status == 200
                     and "javascript" in r.headers.get("content-type", ""))
        verifica("niente nell'ingresso del ciclo", hub.ingresso.vuoto())
    finally:
        web.ferma()
        srv.ferma()


def main() -> int:
    try:
        prova_manifest()
        prova_sw_e_pagina()
        prova_server()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
