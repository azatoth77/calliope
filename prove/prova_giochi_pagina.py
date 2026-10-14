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
- partita condivisa tra due pagine (due schermi): un tocco vero sulla prima arriva alla
  seconda, che può rispondere (dal 14/10 con «segnali», un gioco con una tela: le partite
  condivise del motore sono rimandate);
- il palco fisso (14/10): ogni modello di pagina del gioco «pagine» misurato dal motore sullo
  schermo vero (getBoundingClientRect, scrollHeight) senza difetti, anche a 390×844 in
  verticale; un tema che allarga il titolo → «testo tagliato» arriva a Calliope; un tocco vero
  su una casella del tris, nella posizione che l'impaginazione pura calcola.

Senza Edge né Chromium la prova si salta (esce con 0 e lo dice).

    python prove/prova_giochi_pagina.py
"""

import http.server
import json
import shutil
import socket
import subprocess
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
T0 = time.monotonic()
# I messaggi dei riquadri arrivati al server (istante, tipo, gioco, schermo): stampati solo se
# qualcosa non va, per capire una caduta sotto carico senza rifarla (14/10)
DIARIO = []


def verifica(nome, ok, dettaglio=""):
    print(f"[{time.monotonic() - T0:6.1f}] " + ("ok  " if ok else "NO  ") + nome
          + (f"  {dettaglio}" if dettaglio else ""), flush=True)
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


def cdp(pagina, metodo, parametri, sessione=None):
    pagina.n += 1
    m = {"id": pagina.n, "method": metodo, "params": parametri}
    if sessione:
        m["sessionId"] = sessione
    pagina.ws.send(json.dumps(m))
    while True:
        m = json.loads(pagina.ws.recv(timeout=10))
        if m.get("id") == pagina.n:
            return m


def clic(pagina, x, y):
    for t in ("mousePressed", "mouseReleased"):
        cdp(pagina, "Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left",
                                                 "clickCount": 1})


def riquadro(pagina):
    """[left, top, width, height] del riquadro del gioco nella pagina, o None."""
    return pagina.valuta("(() => { const f = document.querySelector('iframe.riquadro-gioco'); "
                         "if (!f) return null; const b = f.getBoundingClientRect(); "
                         "return [b.left, b.top, b.width, b.height]; })()")


def centro_riquadro(pagina):
    r = riquadro(pagina)
    return (r[0] + r[2] / 2, r[1] + r[3] / 2) if r else None


def nel_riquadro(pagina, espressione):
    """Il valore di un'espressione nel documento del riquadro del gioco, o None. Il riquadro
    (sandbox senza allow-same-origin) gira in un processo suo, fuori dall'albero dei frame della
    pagina: ci si attacca al suo bersaglio di DevTools (sessione «flatten») e si valuta lì."""
    bers = (cdp(pagina, "Target.getTargets", {}).get("result") or {}).get("targetInfos") or []
    bers = [t for t in bers if t.get("type") == "iframe" and "/gioco/" in str(t.get("url"))]
    if not bers:
        return None
    s = (cdp(pagina, "Target.attachToTarget", {"targetId": bers[-1]["targetId"], "flatten": True})
         .get("result") or {}).get("sessionId")
    if not s:
        return None
    try:
        r = cdp(pagina, "Runtime.evaluate", {"expression": espressione, "returnByValue": True}, s)
        return ((r.get("result") or {}).get("result") or {}).get("value")
    finally:
        cdp(pagina, "Target.detachFromTarget", {"sessionId": s})


RADICE = Path(__file__).resolve().parent.parent
SCATOLA_JS = r"""
import { readFileSync } from "node:fs";
import vm from "node:vm";
const [motore, logica, manifesto, mosse, orient, tipo, valore] = JSON.parse(process.argv[2]);
const ctx = vm.createContext({ console, JSON, Math });
vm.runInContext(readFileSync(motore, "utf8"), ctx);
vm.runInContext(readFileSync(logica, "utf8") + "\nthis.GIOCO = GIOCO;", ctx);
const m = JSON.parse(readFileSync(manifesto, "utf8"));
const nu = ctx.CalliopeMotore.crea(ctx.GIOCO, m.scheda.macchina, m.scheda.giocatori, { titolo: m.titolo });
let S = nu.nuovo();
for (const [c, v] of mosse) S = nu.applica(S, c, v);
const imp = ctx.CalliopeMotore.impagina(nu.pagina(S), orient);
const b = imp.scatole.find((x) => x.tipo === tipo && x.valore === valore);
console.log(JSON.stringify(b ? { x: b.x, y: b.y, w: b.w, h: b.h, W: imp.W, H: imp.H } : null));
"""


def punto_sul_palco(pagina, gioco, mosse, tipo, valore):
    """Dove toccare sullo schermo una scatola del palco (14/10): l'impaginazione pura del
    motore (la stessa del riquadro) dice dove sta sul palco, il palco è scalato e centrato
    nel riquadro."""
    r = riquadro(pagina)
    if not r:
        return None
    x0, y0, w, h = r
    orient = "verticale" if h > w else "orizzontale"
    cart = RADICE / "prove" / "giochi" / gioco
    arg = json.dumps([str(RADICE / "calliope" / "estensioni" / "motore_gioco.js"),
                      str(cart / "logica.js"), str(cart / "manifesto.json"), mosse, orient, tipo,
                      valore])
    f = psp.TMP / "scatola.mjs"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(SCATOLA_JS, encoding="utf-8")
    p = subprocess.run(["node", str(f), arg], capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    try:
        b = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    if not b:
        return None
    s = min(w / b["W"], h / b["H"])
    left, top = x0 + (w - b["W"] * s) / 2, y0 + (h - b["H"] * s) / 2
    return left + (b["x"] + b["w"] / 2) * s, top + (b["y"] + b["h"] / 2) * s


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
    a.installa("segnali")
    a.installa("ostile", sost={"__CATTIVO__": cattivo.url})
    for _n in ("_t_guasto", "_t_pronto", "_t_chiuso", "_t_comandi", "_t_manda"):
        _v = getattr(a.giochi, _n, None)
        if _v is None:
            continue

        def _avvolto(p_, posto_, d_, _v=_v, _n=_n):
            DIARIO.append((round(time.monotonic() - T0, 1), _n[3:], p_.nome, posto_.sid,
                           str(d_)[:60]))
            return _v(p_, posto_, d_)
        setattr(a.giochi, _n, _avvolto)
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
        # Da qui nessun gioco sano va chiuso dal cane da guardia (ancora a 3 s fino al palco):
        # il limite conta dal primo ping senza risposta (14/10, schermo.js), non dall'ultimo pong
        guasti_prima = len(a.giochi.guasti)

        # ── partita condivisa tra due pagine (dal 14/10: la tela dei «segnali») ──
        out = a.chiama("est_segnali", {}, "Dario", schermo=schermi["A"])
        p = a.giochi.partite[out["partita"]]
        a.chiama("est_segnali", {}, "Elena", schermo=schermi["B"])
        verifica("riquadri pronti sulle due pagine",
                 aspetta(lambda: all(x.giocatore for x in p.posti.values())
                         and len(p.posti) == 2, 20) is not None)
        # la preparazione (due giocatori, «Inizia») a voce su tutte e due: poi la tela
        for nome in ("A", "B"):
            aspetta(lambda n=nome: "inizia" in list((a.giochi.ascolto([schermi[n]["id"]]) or {})
                                                    .get("comandi") or {}), 10)
            a.giochi.comando(p.id, schermi[nome]["id"], "inizia")
        # La tela è disegnata quando il motore, dopo averla messa, dice a Calliope i comandi a
        # voce della fase nuova (senza «inizia»). Il numero del giocatore lo dà il «pronto» in
        # ordine d'arrivo: la prima pagina non è sempre il giocatore 1 (sotto carico il riquadro
        # della seconda arriva a volte prima)
        tele = aspetta(lambda: all("inizia" not in (p.posti[schermi[n]["id"]].attivi or ["inizia"])
                                   for n in "AB"), 10)
        g_a = p.posti[schermi["A"]["id"]].giocatore
        g_b = p.posti[schermi["B"]["id"]].giocatore
        xy = centro_riquadro(A)
        if xy:
            clic(A, *xy)
        verifica("il tocco sulla prima pagina diventa un messaggio per tutti",
                 tele is not None and aspetta(lambda: any(
                     (m.get("dati") or {}).get("segnale") == 1 and m.get("da") == g_a
                     for m in p.storia), 8) is not None, str(list(p.storia)))
        # Il messaggio passa dal server alla seconda pagina (SSE) e al suo riquadro: si tocca
        # quando la tela della seconda pagina dice di averlo ricevuto
        ricevuto = aspetta(lambda: "segnale 1" in str(nel_riquadro(
            B, "(document.querySelector('button.segnale') || {}).textContent")), 8)
        xy = centro_riquadro(B)
        if xy:
            clic(B, *xy)
        verifica("la seconda pagina l'ha ricevuto e risponde",
                 ricevuto is not None and aspetta(lambda: any(
                     (m.get("dati") or {}).get("visto") == 1 and m.get("da") == g_b
                     for m in p.storia), 8) is not None,
                 f"ricevuto {ricevuto}, giocatori {g_a} {g_b}, {list(p.storia)}"
                 f" guasti {list(a.giochi.guasti)}")

        # ── la modalità gioco (11/10) ──
        PRONTI = []
        pronto_vero = a.giochi._t_pronto
        a.giochi._t_pronto = lambda p_, posto, d: (PRONTI.append(p_.id), pronto_vero(p_, posto, d))[1]
        # La partita condivisa qui sopra si è già giocata a tutta la finestra (il tocco al
        # centro del riquadro): qui la geometria, il pallino della voce, ⛶, ✕, «Riapri», Esc,
        # la scheda vuota della voce e la variante «collaudo»
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
        # (dal 14/10 anche il tris ha i comandi a voce: chiuso, non ascolta più)
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        sa = schermi["A"]["id"]

        def attivi():
            return list((a.giochi.ascolto([sa]) or {}).get("comandi") or [])

        def attivi_di(pid):
            """I comandi a voce attivi di una partita sullo schermo A (detti dal motore). Dal
            14/10 ogni gioco ha i comandi delle sue fasi (anche l'ostile, o il tris rimasto
            aperto): le prove guardano la partita, non «il gioco che ascolta»."""
            x = a.giochi.partite.get(pid)
            posto_ = x.posti.get(sa) if x else None
            return list(posto_.attivi or []) if posto_ is not None and posto_.attivi else []

        # ── i comandi a voce (11/10; dal 14/10 dalla macchina a stati, calliope/gioco_voce.py) ──
        a.installa("porte")
        out = a.chiama("est_porte", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        pv = out["partita"]
        ok = aspetta(lambda: attivi_di(pv) == ["anchio", "inizia"], 15)
        verifica("comandi a voce: il gioco pronto nella pagina ascolta i comandi della fase "
                 "(la preparazione: «gioco anch'io» e «inizia»)", ok is not None
                 and (a.giochi.ascolto([sa]) or {}).get("partita") == pv, str(attivi_di(pv)))
        a.giochi.comando(pv, sa, "inizia")
        ok = aspetta(lambda: attivi_di(pv) == ["porta_1", "porta_2", "porta_3"], 8)
        verifica("comandi a voce: «inizia» porta al turno con le tre porte", ok is not None,
                 str(attivi_di(pv)))
        a.giochi.comando(pv, sa, "porta_2", "Elena")
        attesa = {"comando": "porta_2", "giocatore": "Elena"}
        ok = aspetta(lambda: (dati(a, "porte", "mosse") or [])[-1:] == [attesa], 8)
        verifica("comandi a voce: la mossa arriva al motore nel riquadro con il solo nome "
                 "del comando e di chi gioca", ok is not None, str(dati(a, "porte", "mosse")))
        ok = aspetta(lambda: attivi_di(pv) == ["porta_1", "porta_3"], 5)
        verifica("comandi a voce: il motore sceglie a runtime i comandi attivi (le porte "
                 "ancora chiuse)", ok is not None, str(attivi_di(pv)))
        n = len(dati(a, "porte", "mosse") or [])
        a.hub.evento_a(sa, "gioco", {"partita": pv, "tipo": "comando",
                                     "dati": {"comando": "<b>quattro</b>"}})
        a.hub.evento_a(sa, "gioco", {"partita": pv, "tipo": "comando",
                                     "dati": {"comando": "porta_1", "testo": "apri tutto",
                                              "giocatore": "x" * 200}})
        aspetta(lambda: len(dati(a, "porte", "mosse") or []) > n, 5)
        time.sleep(1.0)
        mosse = dati(a, "porte", "mosse") or []
        verifica("comandi a voce: la pagina non passa nomi non validi né testo libero né nomi "
                 "lunghi", len(mosse) == n + 1 and mosse[-1] == {
                     "comando": "porta_1", "giocatore": None}, str(mosse[-2:]))
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        ok = aspetta(lambda: not a.giochi.partite[pv].posti[sa].aperto
                     and (a.giochi.ascolto([sa]) or {}).get("partita") != pv, 5)
        verifica("comandi a voce: ✕ chiude il gioco e il suo ascolto", ok is not None)
        # una versione candidata (non approvata) dello stesso gioco, aperta in prova
        mv_p, n_p = a.installa("porte", approva=False,
                               manifesto={"nome": "porte_prova", "titolo": "Porte in prova"})
        out = a.giochi.avvia_prova(a.chi("Dario", schermo=schermi["A"]), "porte_prova", n_p,
                                   mv_p)
        pp = out["partita"]
        ok = aspetta(lambda: attivi_di(pp) == ["anchio", "inizia"], 15)
        a.giochi.comando(pp, sa, "inizia")
        ok2 = aspetta(lambda: attivi_di(pp) == ["porta_1", "porta_2", "porta_3"], 5)
        verifica("comandi a voce nella partita di prova: arrivano (il gioco cambia i suoi "
                 "comandi attivi), anche senza ponte", ok is not None and ok2 is not None
                 and a.giochi.partite[pp].prova, str(attivi_di(pp)))

        # ── la macchina a stati di Calliope (13/10, estensioni/motore_gioco.js) ──
        # Il motore gira nel riquadro vero (sandbox, CSP con le impronte) e dice a Calliope i
        # comandi di ogni fase: preparazione, turno con le porte chiuse, esito, di nuovo turno
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        a.installa("porte_fasi")
        out = a.chiama("est_porte_fasi", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        pm = out.get("partita")
        prep = ["giocatori_1", "giocatori_2", "giocatori_3", "giocatori_4", "anchio", "inizia"]
        ok = aspetta(lambda: attivi_di(pm) == prep, 15)
        verifica("macchina a stati: il motore parte nel riquadro e chiede quanti giocatori",
                 pm and ok is not None, str(attivi_di(pm)))
        a.giochi.comando(pm, sa, "giocatori_2")
        ok = aspetta(lambda: attivi_di(pm) == ["porta_1", "porta_2", "porta_3", "porta_4"], 5)
        verifica("macchina a stati: «siamo in due» → il turno con le quattro porte", ok is not None,
                 str(attivi_di(pm)))
        a.giochi.comando(pm, sa, "porta_3")
        ok = aspetta(lambda: attivi_di(pm) == ["avanti"], 5)
        ok2 = aspetta(lambda: attivi_di(pm) == ["porta_1", "porta_2", "porta_4"], 8)
        verifica("macchina a stati: la porta 3 → l'esito, che va avanti da solo; la porta 3 non "
                 "vale più", ok is not None and ok2 is not None, str(attivi_di(pm))
                 + f" {ok} guasti {list(a.giochi.guasti)}")
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))

        # ── il palco fisso (14/10, motore_gioco.js) ──
        # Il motore misura ogni pagina sullo schermo vero e lo dice a Calliope (tipo «palco»):
        # [] = ci sta. Ogni modello di pagina del gioco «pagine», poi in verticale (telefono).
        # Il cane da guardia stretto serviva sopra: qui, con la macchina carica (--completo), un
        # «ping» lento non deve chiudere il gioco a metà
        a.cfg.giochi_watchdog_s = 10.0
        a.installa("pagine")
        out = a.chiama("est_pagine", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        pg = a.giochi.partite[out["partita"]]
        posto = pg.posti[sa]
        palchi = []
        giro = ["giocatori_2", "parti", "colore_rosso", "avanti", "casella_7", "prosegui",
                "vediamo", "fine_partita"]
        ok = aspetta(lambda: posto.palco is not None, 15)
        palchi.append(("preparazione", posto.palco))
        for c in giro:
            aspetta(lambda c_=c: c_ in attivi_di(pg.id), 8)
            a.giochi.comando(pg.id, sa, c)
            time.sleep(0.5)
            palchi.append((c, posto.palco))
        verifica("palco: ogni modello di pagina misurato sullo schermo vero (900×800), nessun "
                 "difetto", ok is not None and all(x == [] for _, x in palchi)
                 and attivi_di(pg.id) == ["ancora"], str(palchi) + " " + str(attivi_di(pg.id)))
        n0 = posto.palco_n
        cdp(A, "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        # girato lo schermo il motore ridisegna in verticale e rimanda la misura
        girato = aspetta(lambda: posto.palco_n > n0, 8)
        r = riquadro(A) or [0, 0, 0, 0]
        a.giochi.comando(pg.id, sa, "ancora")
        verticale = []
        for c in giro[:-1]:
            aspetta(lambda c_=c: c_ in attivi_di(pg.id), 8)
            a.giochi.comando(pg.id, sa, c)
            time.sleep(0.5)
            verticale.append((c, posto.palco))
        verifica("palco: a 390×844 (verticale, telefono) il motore ridisegna e rimisura, e ogni "
                 "pagina ci sta", girato is not None and r[3] > r[2]
                 and all(x == [] for _, x in verticale) and posto.palco == [],
                 f"{r} {posto.palco_n - n0} misure {verticale}")
        cdp(A, "Emulation.clearDeviceMetricsOverride", {})
        time.sleep(0.8)
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        # Un tema che allarga il titolo oltre la sua scatola: la misura del motore non lo
        # prevede (le misure sono sue), lo schermo vero sì → «testo tagliato» a Calliope
        a.installa("pagine", manifesto={"nome": "pagine_larghe", "titolo": "Pagine larghe"},
                   aggiungi={"tema.css": ".palco .titolo{letter-spacing:200px}"},
                   scheda={"stile": "tema.css"})
        out = a.chiama("est_pagine_larghe", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        pl = a.giochi.partite[out["partita"]].posti[sa]
        ok = aspetta(lambda: pl.palco, 15)
        verifica("palco: un tema che allarga il titolo → «testo tagliato sullo schermo» arriva "
                 "a Calliope", ok is not None and "testo tagliato sullo schermo" in str(pl.palco)
                 and "titolo" in str(pl.palco), str(pl.palco))
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        # Un tocco vero su una casella del tris: dove la dice l'impaginazione pura
        out = a.chiama("est_tris", {"partita": "nuova"}, "Dario", schermo=schermi["A"])
        pt = out["partita"]
        aspetta(lambda: "giocatori_2" in attivi_di(pt), 15)
        a.giochi.comando(pt, sa, "giocatori_2")
        aspetta(lambda: "casella_5" in attivi_di(pt), 8)
        time.sleep(0.5)
        xy = punto_sul_palco(A, "tris", [["giocatori", 2]], "casella", 5)
        if xy:
            clic(A, *xy)
        ok = aspetta(lambda: attivi_di(pt) and "casella_5" not in attivi_di(pt), 5)
        verifica("palco: il tocco sulla casella 5 del tris, dove la mette l'impaginazione pura, "
                 "fa la mossa (la casella non vale più)", xy is not None and ok is not None
                 and "casella_1" in attivi_di(pt), f"{xy} {attivi_di(pt)}")
        clic(A, *centro(A, "article.modo-gioco .gioco-chiudi"))
        dopo = list(a.giochi.guasti)[guasti_prima:]
        verifica("nessun gioco sano chiuso dal cane da guardia dopo le sue prove", not dopo,
                 str(dopo))
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
    if ERRORI:
        print("DIARIO", {k: v["id"] for k, v in schermi.items()})
        for r in DIARIO:
            print("   ", r)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
