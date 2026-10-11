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


# La modalità gioco (11/10): geometria della scheda a tutta la finestra e dei comandi sopra il
# gioco; `libero`: un tocco al centro di ✕ arriva proprio a ✕
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
    sfondo: a ? getComputedStyle(a).backgroundColor : '',
  };
})()"""
DOPO_CHIUSO = r"""(() => { const a = document.querySelector('#principale article.scheda-gioco');
  return {riquadro: !!(a && a.querySelector('iframe')), riapri: !!(a && a.querySelector('.gioco-riapri')),
          fs: !!document.fullscreenElement, body: document.body.classList.contains('in-modo-gioco')}; })()"""


def pieno(m, margine=0.0):
    """La scheda copre tutta la finestra e il riquadro tutta la scheda (meno la cornice)."""
    a, f = m.get("articolo"), m.get("riquadro")
    if not a or not f:
        return False
    W, H = m["W"], m["H"]
    return (abs(a[0]) < 1 and abs(a[1]) < 1 and abs(a[2] - W) < 1 and abs(a[3] - H) < 1
            and f[2] >= W - 2 * margine - 2 and f[3] >= H - 2 * margine - 2)


def centro(pagina, sel):
    r = pagina.valuta(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null;"
                      f" const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
    return r or (-1, -1)


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

        # ── la modalità gioco (11/10) ──
        PRONTI = []
        pronto_vero = a.giochi._t_pronto
        a.giochi._t_pronto = lambda p_, posto, d: (PRONTI.append(p_.id), pronto_vero(p_, posto, d))[1]
        # Il tris qui sopra si è già giocato a tutta la finestra (le celle sono misurate sul
        # riquadro): qui la geometria, il pallino della voce, ⛶, ✕, «Riapri», Esc, la scheda
        # vuota della voce e la variante «collaudo»
        for nome_p, pg in (("prima", A), ("seconda", B)):
            m = pg.valuta(MISURA_GIOCO) or {}
            verifica(f"modalità gioco ({nome_p} pagina): il gioco arrivato prende tutta la finestra, "
                     "✕ in alto e niente lo copre",
                     m.get("fissa") and pieno(m) and m.get("libero") and m["chiudi"][1] < 80,
                     json.dumps(m)[:300])
        for stato, parola in (("ascolta", "ascolto"), ("pensa", "penso"), ("parla", "parlo"),
                              ("dorme", "dormo")):
            a.hub.voce(stato, fino=time.time() + 30 if stato == "ascolta" else None,
                       stanza="soggiorno")
            ok = aspetta(lambda: ((A.valuta(MISURA_GIOCO) or {}).get("voce") or "")
                         .endswith(" " + stato), 3)
            m = A.valuta(MISURA_GIOCO) or {}
            verifica(f"modalità gioco: il pallino segue la voce della stanza ({stato} → «{parola}»)",
                     ok is not None and m.get("voceTesto") == parola,
                     f"{m.get('voce')} {m.get('voceTesto')}")
        m = B.valuta(MISURA_GIOCO) or {}
        verifica("modalità gioco: la pagina della cucina (altra stanza) non mostra la voce del "
                 "soggiorno", not (m.get("voce") or "").endswith(" parla"), str(m.get("voce")))
        sel = "article.modo-gioco .gioco-tutto"
        if A.valuta(f"!!document.querySelector('{sel}') && "
                    f"!document.querySelector('{sel}').hidden"):
            clic(A, *centro(A, sel))
            ok = aspetta(lambda: A.valuta("!!document.fullscreenElement"), 3)
            verifica("⛶: un tocco porta allo schermo intero vero (requestFullscreen nel gesto)",
                     ok is not None)
        else:
            verifica("⛶: c'è quando il browser ha lo schermo intero", False,
                     str(A.valuta("document.fullscreenEnabled")))
        part = A.valuta("window.calliopeSchermo.gioco().partita")
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        ok = aspetta(lambda: not A.valuta("window.calliopeSchermo.gioco().partita"), 3)
        stato_a = A.valuta(DOPO_CHIUSO) or {}
        verifica("✕: modalità e schermo intero lasciati, riquadro tolto, «Riapri» sulla scheda",
                 ok is not None and stato_a.get("riapri") and not stato_a.get("riquadro")
                 and not stato_a.get("fs") and not stato_a.get("body"), json.dumps(stato_a))
        n0 = len(PRONTI)
        clic(A, *centro(A, "article.scheda-gioco .gioco-riapri"))
        ok = aspetta(lambda: A.valuta("window.calliopeSchermo.gioco().partita") == part, 3)
        verifica("«Riapri»: il gioco torna a tutta la finestra e riparte",
                 ok is not None and pieno(A.valuta(MISURA_GIOCO) or {})
                 and aspetta(lambda: len(PRONTI) > n0, 10) is not None)
        for _ in range(2):          # il primo Esc può servire al browser per lasciare lo schermo intero
            for t_ in ("keyDown", "keyUp"):
                cdp(A, "Input.dispatchKeyEvent", {"type": t_, "key": "Escape", "code": "Escape",
                                                  "windowsVirtualKeyCode": 27})
            if aspetta(lambda: not A.valuta("window.calliopeSchermo.gioco().partita"), 1.5):
                break
        stato_a = A.valuta(DOPO_CHIUSO) or {}
        verifica("Esc: chiude il gioco come ✕", stato_a.get("riapri") and not stato_a.get("body"),
                 json.dumps(stato_a))
        from calliope.schermi import schede as SCH
        a.chiama("est_tris", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        aspetta(lambda: A.valuta("window.calliopeSchermo.gioco().partita"), 5)
        a.hub.invia_a(schermi["A"]["id"], SCH.vuota())
        ok = aspetta(lambda: not A.valuta("window.calliopeSchermo.gioco().partita"), 3)
        verifica("«Calliope, chiudi il gioco» (la scheda vuota di schermo_mostra): modalità chiusa, "
                 "niente riquadro", ok is not None and not A.valuta(
                     "!!document.querySelector('iframe.riquadro-gioco')"))
        # la variante «collaudo»: la scheda con "prova": true (Giochi.avvia(prova=True))
        avvia_vero = a.giochi.avvia
        a.giochi.avvia = lambda *x, **k: avvia_vero(*x, **dict(k, prova=True))
        try:
            out = a.chiama("est_tris", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        finally:
            a.giochi.avvia = avvia_vero
        n0 = len(PRONTI)
        carta = a.giochi.partite[out["partita"]].carte.get(schermi["A"]["id"]) or {}
        ok = aspetta(lambda: (A.valuta(MISURA_GIOCO) or {}).get("prova"), 5)
        m = A.valuta(MISURA_GIOCO) or {}
        verifica("collaudo: la scheda porta \"prova\": true e la pagina mostra cornice arancio, "
                 "«PROVA», ✕ e pallino a tutta la finestra",
                 carta.get("prova") is True and ok is not None and pieno(m, 30)
                 and m.get("provaTesto") == "PROVA" and m.get("sfondo") == "rgb(243, 154, 46)"
                 and m.get("libero") and m.get("voce"), json.dumps(m)[:300])
        verifica("collaudo: il gioco in prova gira (pronto nel riquadro)",
                 aspetta(lambda: len(PRONTI) > n0, 10) is not None)
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
