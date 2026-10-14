"""Lo stato della partita nella pagina vera (14/10/2026, passi finali del progetto dei giochi,
docs/aree/giochi.md, «Lo stato della partita»): Edge o Chromium senza finestra, la pagina degli
schermi servita da Calliope, il gioco delle porte nel riquadro vero (sandbox, CSP, il motore).

1. **L'istantanea** arriva al server dal riquadro vero (pagina e runtime la lasciano passare) e
   il comando a voce con il numero è una mossa; uno con un numero vecchio è rifiutato dal motore
   e il rifiuto arriva al server.
2. **«Gioco anch'io»** con il nome dalla voce: «Ada» nella partita.
3. **Il nome scritto**: un tocco vero sul nome nella fascia dei punti, «Bea» scritta con la
   tastiera e Invio: nell'istantanea «Bea», scritto, e Calliope lo dice («Tocca a Bea.»).
4. **La ripresa dopo «Riapri»**: ✕ e «Riapri», il riquadro nuovo riparte dall'ultima istantanea
   (stesso numero, «Bea» con i suoi punti, le porte già aperte chiuse).

    python prove/prova_gioco_stato_pagina.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_giochi_pagina as PG  # noqa: E402
import prova_schermi_pagina as psp  # noqa: E402
from prova_giochi import Ambiente  # noqa: E402

from calliope import gioco_stato as GS  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402

SALTATA = 77
ERRORI = 0
T0 = time.monotonic()


def verifica(nome, ok, dettaglio=""):
    global ERRORI
    ERRORI += not ok
    print(f"[{time.monotonic() - T0:6.1f}] {'ok ' if ok else 'NO '} {nome}"
          + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def nel_palco(pagina, sel: str):
    """Il centro, in coordinate della pagina, del primo elemento `sel` dentro il riquadro."""
    r = PG.nel_riquadro(pagina, "(() => { const e = document.querySelector(" + json.dumps(sel)
                        + "); if (!e) return null; const b = e.getBoundingClientRect(); "
                        "return [b.left + b.width / 2, b.top + b.height / 2]; })()")
    f = PG.riquadro(pagina)
    if not r or not f:
        return None
    return f[0] + r[0], f[1] + r[1]


def main() -> int:
    exe = psp.browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="calliope-gioco-stato-pagina-"))
    a = Ambiente(tmp)
    a.installa("porte")
    srv = ServerSchermi(a.hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    pg = None
    try:
        r = a.hub.archivio.nuova_richiesta()
        sa = a.hub.abbina(r["codice"], "soggiorno", None, None)["schermo"]
        pg = psp.Pagina(exe, f"{base}/#t={r['richiesta']}", opzioni=["--window-size=900,800"],
                        profilo="prof-stato")
        verifica("la pagina degli schermi è collegata",
                 PG.aspetta(lambda: len(a.hub.collegati()) == 1, 25) is not None)
        rifiutati = []
        vero = a.giochi._t_rifiutato

        def rifiutato(p_, posto_, d_):
            rifiutati.append(dict(d_))
            return vero(p_, posto_, d_)
        a.giochi._t_rifiutato = rifiutato
        pid = a.chiama("est_porte", {}, "Dario", schermo=sa)["partita"]
        posto = a.giochi.partite[pid].posti[sa["id"]]

        def ist():
            return posto.istantanea or {}
        ok = PG.aspetta(lambda: ist().get("fase") == "preparazione", 20)
        verifica("1. l'istantanea della preparazione arriva dal riquadro vero al server",
                 ok is not None and ist().get("comandi") == ["anchio", "inizia"], str(ist()))
        # 2. «gioco anch'io» con il nome dalla voce (Calliope lo manda: la porte ha «giocatore»)
        a.giochi.comando(pid, sa["id"], "anchio", "Ada")
        PG.aspetta(lambda: ist().get("comandi") == ["inizia"], 8)
        a.giochi.comando(pid, sa["id"], "inizia")
        ok = PG.aspetta(lambda: ist().get("fase") == "turno", 8)
        g0 = (ist().get("giocatori") or [{}])[0]
        verifica("2. «gioco anch'io» di Ada e «inizia»: Ada gioca, e Calliope la dice",
                 ok is not None and g0.get("nome") == "Ada" and g0.get("detto") == "Ada",
                 str(ist()))
        # 1b. un comando con un numero vecchio: il motore lo rifiuta e lo dice
        n = ist().get("n")
        a.hub.evento_a(sa["id"], "gioco", {"partita": pid, "tipo": "comando",
                                           "dati": {"comando": "porta_1", "n": n - 1}})
        ok = PG.aspetta(lambda: rifiutati, 5)
        verifica("1. un comando con il numero di un'istantanea vecchia: il motore lo rifiuta, "
                 "il rifiuto arriva al server, la partita non cambia",
                 ok is not None and rifiutati[-1].get("motivo") == "vecchio"
                 and ist().get("n") == n, f"{rifiutati} {ist().get('n')}")
        a.giochi.comando(pid, sa["id"], "porta_1")
        ok = PG.aspetta(lambda: "porta_1" not in (ist().get("comandi") or ["porta_1"])
                        and ist().get("fase") == "turno", 8)
        verifica("1. il comando a voce con il numero giusto è una mossa (la porta 1 si apre)",
                 ok is not None, str(ist()))
        # 3. il nome scritto: un tocco vero sul nome nella fascia, la tastiera, Invio
        xy = nel_palco(pg, ".palco .giocatore.nome")
        if xy:
            PG.clic(pg, *xy)
        aperto = PG.aspetta(lambda: PG.nel_riquadro(pg, "!!document.querySelector('.scrivi-nome')"
                                                    " && document.activeElement === document"
                                                    ".querySelector('.scrivi-nome')"), 5)
        verifica("3. un tocco sul nome nella fascia apre il campo, con il cursore dentro",
                 xy is not None and aperto is not None, str(xy))
        PG.cdp(pg, "Input.insertText", {"text": "Bea"})
        for t_ in ("keyDown", "keyUp"):
            PG.cdp(pg, "Input.dispatchKeyEvent", {"type": t_, "key": "Enter", "code": "Enter",
                                                  "windowsVirtualKeyCode": 13})
        ok = PG.aspetta(lambda: (ist().get("giocatori") or [{}])[0].get("nome") == "Bea", 8)
        g0 = (ist().get("giocatori") or [{}])[0]
        info = a.giochi.ascolto([sa["id"]]) or {}
        verifica("3. «Bea» scritta con la tastiera: nell'istantanea, scritta, e Calliope la dice",
                 ok is not None and g0.get("scritto") is True and g0.get("detto") == "Bea"
                 and GS.risposta("punti", info) == "Bea ha 0 punti.", f"{g0} "
                 f"{GS.risposta('punti', info) if info else ''}")
        # 4. ✕ e «Riapri»: la partita riprende dall'ultima istantanea
        prima = json.loads(json.dumps(ist()))
        verifica("4. il server tiene lo stato per la ripresa con l'ultima istantanea",
                 posto.ripresa is not None and posto.ripresa.get("n") == prima.get("n"))
        PG.clic(pg, *PG.centro(pg, "article.modo-gioco .gioco-chiudi"))
        PG.aspetta(lambda: not posto.aperto, 5)
        PG.clic(pg, *PG.centro(pg, "article.scheda-gioco .gioco-riapri"))
        ok = PG.aspetta(lambda: posto.aperto and ist().get("n") == prima.get("n"), 15)
        dopo = ist()
        verifica("4. «Riapri»: il riquadro nuovo riparte dall'ultima istantanea (stesso numero, "
                 "Bea, la porta 1 ancora aperta)", ok is not None
                 and dopo.get("giocatori") == prima.get("giocatori")
                 and dopo.get("comandi") == prima.get("comandi"),
                 f"{dopo} | {prima}")
        testo = PG.nel_riquadro(pg, "document.getElementById('gioco').innerText") or ""
        verifica("4. sullo schermo: «Bea» nella fascia e niente «Porta 1»",
                 "Bea" in testo and "Porta 1" not in testo, testo[:200])
    finally:
        if pg is not None:
            pg.chiudi()
        srv.ferma()
    print("\nTutto bene." if not ERRORI else f"\n{ERRORI} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
