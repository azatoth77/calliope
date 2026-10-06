"""I giochi nella pagina vera degli schermi (05/10/2026): Edge o Chromium senza finestra,
comandati con il protocollo DevTools, il server degli schermi vero su 127.0.0.1 e un server
«cattivo» su 127.0.0.2 che conta ogni richiesta che gli arriva.

- un gioco OSTILE (prove/giochi/ostile) nel riquadro prova a leggere la pagina madre, i suoi
  cookie e il localStorage (dove sta il token dello schermo), a fare fetch, XHR, immagini,
  WebSocket e WebRTC verso il server cattivo (anche da un iframe figlio), a mandare messaggi
  falsi alla pagina, a salvare fuori dalla sua cartella e a chiedere un'azione non
  dichiarata: tutto bloccato, il server cattivo non riceve niente, la pagina continua;
- cane da guardia: un gioco in un ciclo infinito si chiude (e la pagina resta viva), uno che
  prova a navigare verso un altro sito si chiude senza che la richiesta parta, uno che manda
  troppi messaggi si chiude; ogni chiusura arriva al server come guasto;
- partita condivisa di Tris tra due pagine (due schermi): un tocco vero sulla prima arriva
  alla seconda, che può rispondere.

Senza Edge né Chromium la prova si salta (esce con 0 e lo dice).

    python prove/prova_giochi_pagina.py
"""

import http.server
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_schermi_pagina as psp  # noqa: E402
from prova_giochi import Ambiente  # noqa: E402

from calliope.schermi.server import ServerSchermi  # noqa: E402

ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


class Cattivo:
    """Un server HTTP su 127.0.0.2 che conta le richieste (non ne deve arrivare nessuna)."""

    def __init__(self):
        self.richieste = []
        fuori = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                fuori.richieste.append(self.path)
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"ok")

            do_POST = do_GET

            def log_message(self, *a):
                pass
        s = socket.socket()
        s.bind(("127.0.0.2", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.2", self.port), H)
        self.srv.handle_error = lambda *a: None       # connessioni chiuse dal browser
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.2:{self.port}"

    def ferma(self):
        self.srv.shutdown()


def cdp(pagina, metodo, parametri):
    pagina.n += 1
    pagina.ws.send(json.dumps({"id": pagina.n, "method": metodo, "params": parametri}))
    while True:
        m = json.loads(pagina.ws.recv(timeout=10))
        if m.get("id") == pagina.n:
            return m


def clic(pagina, x, y):
    for t in ("mousePressed", "mouseReleased"):
        cdp(pagina, "Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left",
                                                 "clickCount": 1})


def cella(pagina, i):
    """Le coordinate della cella i del tris dentro il riquadro (stessa geometria di gioco.css)."""
    r = pagina.valuta("(() => { const f = document.querySelector('iframe.riquadro-gioco'); "
                      "if (!f) return null; const b = f.getBoundingClientRect(); "
                      "return [b.left, b.top, b.width, b.height]; })()")
    if not r:
        return None
    x0, y0, w, h = r
    vmin = min(w, h) / 100
    lato = min(70 * vmin, 0.9 * w)
    titolo = 6 * vmin * 1.2
    alto = titolo + 4 * vmin + lato
    top = y0 + (h - alto) / 2 + titolo + 4 * vmin
    left = x0 + (w - lato) / 2
    c = lato / 3
    return left + c * (i % 3) + c / 2, top + c * (i // 3) + c / 2


def aspetta(cond, s):
    return psp.aspetta(cond, s, 0.2)


def dati(a, nome, chiave):
    f = a.est.archivio.cartella_dati(nome) / f"gioco_{chiave}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def metti_dato(a, nome, chiave, valore):
    cart = a.est.archivio.cartella_dati(nome)
    cart.mkdir(parents=True, exist_ok=True)
    (cart / f"gioco_{chiave}.json").write_text(json.dumps(valore), encoding="utf-8")


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main() -> int:
    exe = psp.browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="calliope-giochi-pagina-"))
    cattivo = Cattivo()
    a = Ambiente(tmp, {"giochi_watchdog_s": 3.0})
    a.installa("tris")
    a.installa("ostile", sost={"__CATTIVO__": cattivo.url})
    srv = ServerSchermi(a.hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    schermi, pagine = {}, {}
    try:
        for nome, stanza, chi in (("A", "soggiorno", None), ("B", "cucina", "Elena")):
            r = a.hub.archivio.nuova_richiesta()
            p = a.reg_voci.get(chi) if chi else None
            schermi[nome] = a.hub.abbina(r["codice"], stanza, getattr(p, "id", None),
                                         getattr(p, "name", None))["schermo"]
            pagine[nome] = psp.Pagina(exe, f"{base}/#t={r['richiesta']}",
                                      opzioni=["--window-size=900,800"], profilo=f"prof-{nome}")
        verifica("due pagine collegate", aspetta(lambda: len(a.hub.collegati()) == 2, 25)
                 is not None)
        A, B = pagine["A"], pagine["B"]
        token_a = A.valuta("localStorage.getItem('calliope.schermo.token')")

        # ── gioco ostile: attacchi ──
        metti_dato(a, "ostile", "modo", "attacchi")
        a.chiama("est_ostile", {}, "Dario", schermo=schermi["A"])
        t = aspetta(lambda: dati(a, "ostile", "esiti") is not None, 25)
        esiti = dati(a, "ostile", "esiti") or {}
        verifica("il gioco ostile ha girato e salvato gli esiti", t is not None and esiti,
                 json.dumps(esiti, ensure_ascii=False)[:300])
        passati = {k: v for k, v in esiti.items() if not v.startswith("bloccato")
                   and k != "frase"}
        for k, v in sorted(esiti.items()):
            print(f"     {k}: {v}")
        verifica("ogni tentativo di uscire dal riquadro è bloccato", not passati,
                 json.dumps(passati, ensure_ascii=False))
        time.sleep(1.0)
        verifica("il server cattivo non ha ricevuto niente", not cattivo.richieste,
                 str(cattivo.richieste))
        verifica("il token della pagina è intatto e la pagina vive",
                 A.valuta("localStorage.getItem('calliope.schermo.token')") == token_a
                 and A.stato() == "collegato", A.stato())
        cart = a.est.archivio.cartella_dati("ostile")
        verifica("i messaggi falsi non scrivono fuori dalla cartella",
                 not (tmp / "segreto").exists() and all(x.parent == cart
                                                        for x in cart.rglob("*")))

        # ── cane da guardia ──
        for modo, motivo, attesa in (("blocca", "non risponde", 20), ("naviga", "navigazione", 15),
                                     ("inonda", "troppi messaggi", 15)):
            a.giochi.guasti.clear()
            metti_dato(a, "ostile", "modo", modo)
            out = a.chiama("est_ostile", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
            t0 = time.monotonic()
            ok = aspetta(lambda: any(g["motivo"] == motivo for g in a.giochi.guasti), attesa)
            vivo = A.valuta("1 + 1") == 2
            chiuso = A.valuta("!document.querySelector('iframe.riquadro-gioco') && "
                              "!!document.querySelector('.gioco-chiuso')")
            verifica(f"cane da guardia: «{modo}» chiuso ({motivo}), pagina viva",
                     ok is not None and vivo and chiuso,
                     f"{time.monotonic() - t0:.1f} s, guasti {list(a.giochi.guasti)[-1:]}"
                     f" {out.get('risposta_finale')}")
        verifica("nemmeno navigando il server cattivo riceve qualcosa", not cattivo.richieste,
                 str(cattivo.richieste))

        # ── partita condivisa tra due pagine ──
        out = a.chiama("est_tris", {}, "Dario", schermo=schermi["A"])
        p = a.giochi.partite[out["partita"]]
        a.chiama("est_tris", {}, "Elena", schermo=schermi["B"])
        verifica("riquadri pronti sulle due pagine",
                 aspetta(lambda: all(x.giocatore for x in p.posti.values())
                         and len(p.posti) == 2, 20) is not None)
        time.sleep(0.8)
        xy = cella(A, 4)
        if xy:
            clic(A, *xy)
        verifica("il tocco sulla prima pagina diventa una mossa per tutti",
                 aspetta(lambda: any((m.get("dati") or {}).get("mossa") == 4
                                     for m in p.storia), 8) is not None, str(list(p.storia)))
        time.sleep(0.5)
        xy = cella(B, 0)
        if xy:
            clic(B, *xy)
        verifica("la seconda pagina l'ha ricevuta e risponde",
                 aspetta(lambda: any((m.get("dati") or {}).get("mossa") == 0
                                     and m.get("da") == 2 for m in p.storia), 8) is not None,
                 str(list(p.storia)))
    finally:
        for pg in pagine.values():
            pg.chiudi()
        srv.ferma()
        cattivo.ferma()
        from calliope import minori as M
        for s in ("regole", "avvisi", "gioco", "richieste"):
            x = M._SERVIZIO.get(s)
            if x is not None:
                x.close()
        a.hub.archivio.close()
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(psp.TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
