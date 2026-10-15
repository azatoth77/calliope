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
5. **La partita condivisa con il motore** su due pagine: una tiene la partita (il primo
   riquadro pronto), l'altra (uno specchio) disegna lo stesso stato; un tocco vero sullo
   specchio («2 giocatori», poi «Porta 1») è una mossa del motore che la tiene, e le due pagine
   mostrano la stessa pagina.
6. **Chi è quale giocatore** (15/10): «Gioco anch'io» toccato su ogni pagina lega un giocatore
   a ogni schermo; il tocco sulla pagina dell'altro giocatore non muove (lo dice sul palco),
   sulla propria sì.
7. **«Gira il telefono»** (15/10): un telefono finto in verticale (390×844, tocco) e una tela
   orizzontale: la pagina dice al riquadro che è al tocco (il riquadro, in un processo suo, non
   vede l'emulazione), la fascia nel riquadro vero, il messaggio passa dalla pagina al server e
   Calliope lo dice una volta.

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
    a.installa("porte_fasi", scheda={"condivisa": True})
    srv = ServerSchermi(a.hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    pg = pg2 = None
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
        PG.clic(pg, *PG.centro(pg, "article.modo-gioco .gioco-chiudi"))
        # 5. la partita condivisa con il motore su due pagine
        r2 = a.hub.archivio.nuova_richiesta()
        sb = a.hub.abbina(r2["codice"], "cucina", None, None)["schermo"]
        pg2 = psp.Pagina(exe, f"{base}/#t={r2['richiesta']}", opzioni=["--window-size=900,800"],
                         profilo="prof-stato-2")
        PG.aspetta(lambda: len(a.hub.collegati()) == 2, 25)
        pc = a.chiama("est_porte_fasi", {"partita": "nuova"}, "Dario", schermo=sa)["partita"]
        a.chiama("est_porte_fasi", {}, "Elena", schermo=sb)
        p = a.giochi.partite[pc]
        ok = PG.aspetta(lambda: len(p.posti) == 2 and all(x.aperto for x in p.posti.values())
                        and p.autorevole is not None
                        and p.posti[p.autorevole].istantanea is not None, 25)
        # La tiene il primo riquadro che dice «pronto» (qui l'una o l'altra pagina)
        tiene = p.posti.get(p.autorevole)
        pagine = {sa["id"]: pg, sb["id"]: pg2}
        specchio = pagine.get(next((k for k in p.posti if k != p.autorevole), None))
        verifica("5. due pagine nella stessa partita: una la tiene, l'altra è uno specchio",
                 ok is not None and p.motore_condiviso and specchio is not None,
                 f"{p.autorevole} {[(k, x.aperto) for k, x in p.posti.items()]}")
        PG.aspetta(lambda: nel_palco(specchio, '.palco button[data-comando="giocatori"]'
                                               '[data-valore="2"]'), 10)
        xy = nel_palco(specchio, '.palco button[data-comando="giocatori"][data-valore="2"]')
        if xy:
            PG.clic(specchio, *xy)
        ok = PG.aspetta(lambda: (tiene.istantanea or {}).get("fase") == "turno", 10)
        verifica("5. «2 giocatori» toccato sullo specchio: la partita la cambia il motore che la "
                 "tiene", ok is not None and len(tiene.istantanea["giocatori"]) == 2,
                 str(tiene.istantanea))
        PG.aspetta(lambda: nel_palco(specchio, '.palco button[data-comando="porta"]'
                                               '[data-valore="1"]'), 10)
        xy = nel_palco(specchio, '.palco button[data-comando="porta"][data-valore="1"]')
        if xy:
            PG.clic(specchio, *xy)
        ok = PG.aspetta(lambda: (tiene.istantanea or {}).get("fase") == "esito", 10)
        uguale = PG.aspetta(lambda: (PG.nel_riquadro(pg, "document.getElementById('gioco')"
                                                    ".innerText") or "1")
                            == (PG.nel_riquadro(pg2, "document.getElementById('gioco')"
                                                ".innerText") or "2"), 10)
        testo = PG.nel_riquadro(specchio, "document.getElementById('gioco').innerText") or ""
        verifica("5. «Porta 1» toccata sullo specchio: l'esito sulle due pagine, uguale",
                 ok is not None and uguale is not None and "porta 1" in testo.lower(), testo[:200])
        # 6. chi è quale giocatore (15/10): «Gioco anch'io» toccato su ogni pagina
        pn = a.chiama("est_porte_fasi", {"partita": "nuova"}, "Dario", schermo=sa)["partita"]
        a.chiama("est_porte_fasi", {}, "Elena", schermo=sb)
        q = a.giochi.partite[pn]
        ok = PG.aspetta(lambda: len(q.posti) == 2 and all(x.aperto for x in q.posti.values())
                        and q.autorevole is not None
                        and q.posti[q.autorevole].istantanea is not None, 25)
        tq = q.posti.get(q.autorevole)
        p_tiene = pagine.get(q.autorevole)
        p_spec = pagine.get(next((k for k in q.posti if k != q.autorevole), None))

        def tocca(pagina, sel):
            PG.aspetta(lambda: nel_palco(pagina, sel), 10)
            xy_ = nel_palco(pagina, sel)
            if xy_:
                PG.clic(pagina, *xy_)
            return xy_
        tocca(p_tiene, '.palco button[data-comando="anchio"]')
        PG.aspetta(lambda: len((tq.istantanea or {}).get("comandi") or []) and tq.ripresa
                   and len(tq.ripresa.get("iscritti") or []) == 1, 8)
        tocca(p_spec, '.palco button[data-comando="anchio"]')
        PG.aspetta(lambda: tq.ripresa and len(tq.ripresa.get("iscritti") or []) == 2, 8)
        tocca(p_tiene, '.palco button[data-comando="inizia"]')
        ok = PG.aspetta(lambda: (tq.istantanea or {}).get("fase") == "turno", 10)
        gs = (tq.istantanea or {}).get("giocatori") or []
        verifica("6. «Gioco anch'io» toccato sulle due pagine: due giocatori, ognuno legato al suo "
                 "schermo", ok is not None and len(gs) == 2 and gs[0].get("schermo")
                 and gs[1].get("schermo") and gs[0]["schermo"] != gs[1]["schermo"], str(gs))
        n0 = (tq.istantanea or {}).get("n")
        tocca(p_spec, '.palco button[data-comando="porta"][data-valore="1"]')
        time.sleep(1.0)
        testo = PG.nel_riquadro(p_spec, "document.getElementById('gioco').innerText") or ""
        verifica("6. tocca al giocatore dell'altra pagina: il tocco sullo specchio non muove, e "
                 "lo dice sul palco", (tq.istantanea or {}).get("n") == n0
                 and "sull'altro schermo" in testo, testo[:200])
        tocca(p_tiene, '.palco button[data-comando="porta"][data-valore="1"]')
        ok = PG.aspetta(lambda: (tq.istantanea or {}).get("fase") == "esito", 10)
        verifica("6. dalla pagina del suo giocatore sì", ok is not None)
        # 7. «Gira il telefono» (15/10): un telefono in verticale, una tela orizzontale
        from prova_giochi import file_gioco
        ms, _ = file_gioco("segnali")
        mac = json.loads(json.dumps(ms["scheda"]["macchina"]))
        mac["fasi"]["gioco"]["orientamento"] = "orizzontale"
        a.installa("segnali", manifesto={"nome": "tela_larga", "titolo": "La tela larga"},
                   scheda={"condivisa": False, "giocatori": {"min": 1, "max": 1},
                           "macchina": mac})
        PG.cdp(pg, "Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844,
                                                          "deviceScaleFactor": 2,
                                                          "mobile": True})
        PG.cdp(pg, "Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
        pt = a.chiama("est_tela_larga", {}, "Dario", schermo=sa)["partita"]
        pos = a.giochi.partite[pt].posti[sa["id"]]
        PG.aspetta(lambda: (pos.istantanea or {}).get("fase") == "preparazione", 20)
        a.giochi.comando(pt, sa["id"], "inizia")
        detto = PG.aspetta(lambda: pos.gira_detto, 10)
        fascia = PG.nel_riquadro(pg, "(document.querySelector('.gira-telefono') || {})"
                                     ".textContent || ''") or ""
        frasi = []
        while not a.giochi.frasi.empty():
            frasi.append(a.giochi.frasi.get_nowait().get("messaggio"))
        verifica("7. telefono in verticale, tela orizzontale: la fascia «Gira il telefono» nel "
                 "riquadro vero, e Calliope lo dice una volta",
                 detto is not None and "Gira il telefono in orizzontale" in fascia
                 and any("gira il telefono" in str(f) for f in frasi), f"{fascia!r} {frasi}")
        PG.cdp(pg, "Emulation.setTouchEmulationEnabled", {"enabled": False})
        PG.cdp(pg, "Emulation.clearDeviceMetricsOverride", {})
    finally:
        for x in (pg, pg2):
            if x is not None:
                x.chiudi()
        srv.ferma()
    print("\nTutto bene." if not ERRORI else f"\n{ERRORI} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
