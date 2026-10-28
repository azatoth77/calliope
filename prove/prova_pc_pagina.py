import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Lo schermo personale del PC a sezioni nella pagina vera (27/10/2026, passo 1b di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, issue #239; decisioni del 27/10 sera:
solo sugli schermi personali, con «Parla»).

Nel browser vero (Edge o Chromium senza finestra, DevTools; senza si salta), server degli
schermi e dei satelliti veri su 127.0.0.1, un satellite finto legato allo schermo del PC.
- schermo di stanza: niente sezioni (né barra né colonne), la scheda grande e la fila come prima;
- schermo personale del PC: sezioni accese, lo stesso smistamento del telefono (sezioni.js): lista,
  timer, programma e documento nelle raccolte di Le mie cose e, vivi, in Adesso; il calcolo in
  Conversazione; la barra porta alle sezioni (#/cose) e il gesto indietro torna;
- «Parla»: c'è sullo schermo legato al satellite; un clic fa arrivare «tocco» al satellite e il
  pulsante dice «Ti ascolto»;
- la casella per scrivere sotto la conversazione, a destra; un file trascinato sulla pagina arriva
  nella casella (con la conversazione a voce aperta);
- disposizione a 1440×900 e 1100×800 (tre colonne), 1000×760 (la conversazione dietro il suo
  pulsante, che la apre sopra la pagina; Esc la chiude), 700×900 (la barra in basso): la pagina
  non scorre, parti che non si sovrappongono, niente testo fuori dai contenitori della barra e
  della voce, contrasto AA, clic ≥ 44 px;
- con la configurazione di serie (revisioni della PR #255): la conversazione a destra con i turni
  dell'archivio resta anche dopo otto schede e prende i turni nuovi; il «Cruscotto» della testa
  porta in Io con la scheda, e il suo ridisegno periodico non ci riporta; «Schermo intero» della
  conversazione apre lo strato coi turni; «Pulisci le mie schede» in Io con due clic;
- Le mie cose (28/10, passo 2a): le tessere coi conti, più di due per riga; la pagina Liste dalla
  tessera; la spunta manda il tocco giusto; contrasto e clic ≥ 44 px a 1440×900 e 700×900;
  la pagina Agenda (28/10, passo 2b) con «+1 minuto» e «Ferma» che mandano il tocco giusto;
- nessun errore JavaScript né violazione della CSP. Con CALLIOPE_FOTO=<cartella> gli screenshot.
"""

import base64
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_telefono_pagina as PTP
import prova_telefono_schermo as PTS
from prova_parla_pc import CollFinto

TMP = Path(tempfile.mkdtemp(prefix="calliope-pc-pagina-"))
ERRORI = []
SALTATA = 77


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


def foto(p, nome):
    cartella = os.environ.get("CALLIOPE_FOTO")
    if not cartella:
        return
    r = p._chiama("Page.captureScreenshot", {"format": "png"})
    Path(cartella).mkdir(parents=True, exist_ok=True)
    (Path(cartella) / nome).write_bytes(base64.b64decode(r["result"]["data"]))


def dimensione(p, w, h):
    p._chiama("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
    aspetta(lambda: p.valuta(f"innerWidth === {w} && innerHeight === {h}"), 5)
    p.valuta("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")


def clic(p, sel):
    r = p.valuta(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null;"
                 f" if (e.closest('.sezione')) e.scrollIntoView({{block: 'nearest'}});"
                 f" const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }})()")
    if not r:
        return False
    for t in ("mousePressed", "mouseReleased"):
        p._chiama("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1], "button": "left", "clickCount": 1})
    return True


MISURA = r"""(() => {
  const W = innerWidth, H = innerHeight;
  const vis = (e) => e && !e.hidden && e.getClientRects().length > 0 && getComputedStyle(e).display !== 'none';
  const nome = (e) => e.id || e.className || e.tagName;
  const fuori = [];
  const dentro = (r, c) => r.left >= c.left - 1 && r.right <= c.right + 1 && r.top >= c.top - 1 && r.bottom <= c.bottom + 1;
  const aree = ['testa', 'barra', 'pc-voce', 'pc', 'pc-conv'].map((id) => document.getElementById(id)).filter(vis)
    .filter((e) => getComputedStyle(e).position !== 'fixed').map((e) => [e.id, e.getBoundingClientRect()]);
  for (let i = 0; i < aree.length; i++) {
    if (!dentro(aree[i][1], {left: 0, top: 0, right: W, bottom: H})) fuori.push(aree[i][0] + ' fuori dallo schermo');
    for (let j = i + 1; j < aree.length; j++) {
      const a = aree[i][1], b = aree[j][1];
      if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1)
        fuori.push(aree[i][0] + ' sopra ' + aree[j][0]);
    }
  }
  const scatole = [...document.querySelectorAll('#barra a, #pc-parla, #pc-conv-apri, #sez-titolo, #tessere .tessera, #pc button.spunta, #pc button.tasto-timer, #pagina-indietro')].filter(vis);
  for (const e of scatole) if (e.scrollWidth > e.clientWidth + 1) fuori.push(nome(e) + ' trabocca');
  const clic = scatole.filter((e) => e.id !== 'sez-titolo').map((e) => { const r = e.getBoundingClientRect(); return [nome(e), Math.round(Math.min(r.width, r.height))]; })
    .filter(([, m]) => m < 44);
  const lum = (c) => { const m = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => v / 255)
    .map((v) => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
  // un fondo quasi trasparente (la tinta dell'accento sulla sezione aperta) vale quello sotto
  const alfa = (c) => { const m = c.match(/[\d.]+/g); return m.length > 3 ? Number(m[3]) : 1; };
  const contrasto = (e) => { const cs = getComputedStyle(e); let b = e, bg = 'rgba(0, 0, 0, 0)';
    while (b && alfa(bg = getComputedStyle(b).backgroundColor) < 0.5) b = b.parentElement;
    const l1 = lum(cs.color), l2 = lum(b ? bg : 'rgb(0, 0, 0)'); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const bassi = [...document.querySelectorAll('#barra *, #pc-voce *, #pc *, #pc-conv *')].filter(vis)
    .filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()))
    .filter((e) => { const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < H && r.right > 0 && r.left < W; })
    .map((e) => [nome(e) + ' «' + e.textContent.trim().slice(0, 16) + '»', contrasto(e)]).filter(([, c]) => c < 4.5).map(([n, c]) => n + ' ' + c.toFixed(2)).slice(0, 6);
  const se = document.scrollingElement;
  return {scorre: se.scrollHeight > H + 1 || se.scrollWidth > W + 1, fuori, clic, bassi,
          conv: vis(document.getElementById('pc-conv')), apri: vis(document.getElementById('pc-conv-apri')),
          barraSotto: (() => { const b = document.getElementById('barra').getBoundingClientRect(); return b.bottom >= H - 2 && b.width > W * 0.8; })()};
})()"""


def avvia_server():
    # Quello del cruscotto (chi amministra, il cruscotto vero) con le sezioni accese, com'è di
    # serie, e l'archivio delle conversazioni per la colonna a destra
    import prova_cruscotto_pagina as PCP
    from calliope.conversazioni import ArchivioConversazioni
    PCP.TMP = TMP
    cfg, srv, hub, web = PCP.avvia()
    cfg.schermi_sezioni = True
    arch_conv = ArchivioConversazioni(TMP / "conversazioni.db", giorni=30, avvia=False, log=lambda m: None)
    hub.chat_fonte = arch_conv
    arch_conv.su_turni[:] = [hub.chat_nuovi]
    hub.arch_conv = arch_conv
    pc = CollFinto(5, "studio")
    srv.collegati.append(pc)
    arch = hub.archivio
    s_pc, t_pc = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    arch.lega_satellite(s_pc["id"], 5)
    # Le tessere e la pagina Liste (28/10, passo 2a): le liste di casa e il profilo di Dario
    PTS.prepara_raccolte(cfg, hub, TMP)
    _, t_stanza = arch.crea_con_token("cucina")
    hub._rinfresca()
    return cfg, srv, hub, web, pc, t_pc, t_stanza


def stanza(exe, web, t_stanza):
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_stanza}", profilo="profilo-pc-stanza",
                   opzioni=("--window-size=1280,800",))
    try:
        ok = aspetta(lambda: p.valuta("!!window.calliopeSchermo && !!window.calliopePC && document.getElementById('stato').className.includes('ok')"), 15)
        time.sleep(0.5)
        s = p.valuta("({sezioni: document.body.classList.contains('con-sezioni'), barra: document.getElementById('barra').hidden,"
                     " pc: document.getElementById('pc').hidden, principale: getComputedStyle(document.getElementById('principale')).display,"
                     " stato: window.calliopePC.stato()})") or {}
        verifica("schermo di stanza: niente sezioni, la pagina di prima (scheda grande e fila)",
                 bool(ok) and s.get("sezioni") is False and s.get("barra") and s.get("pc") and s.get("principale") != "none"
                 and s.get("stato") is None, json.dumps(s))
        p.pompa(0.2)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("schermo di stanza: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()


def personale(exe, srv, hub, web, pc, t_pc):
    P = "window.calliopePC"
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-pc-personale",
                   opzioni=("--window-size=1440,900",))
    try:
        dimensione(p, 1440, 900)
        ok = aspetta(lambda: p.valuta(f"!!{P} && !!{P}.stato() && document.body.classList.contains('con-sezioni')"), 15)
        verifica("schermo personale del PC: le sezioni accese", bool(ok))
        if not ok:
            return
        aspetta(lambda: hub.collegati(), 10)
        S = PTS.schede_prova()
        for k in ("lista", "timer", "esecuzione", "documento"):
            PTS.tutti(hub, S[k])
            time.sleep(0.15)
        from calliope.schermi import schede
        calc = schede.calcolo("17 × 6", "102")
        PTS.tutti(hub, calc)
        ok = aspetta(lambda: ((p.valuta(f"{P}.stato()") or {}).get("posti") or {}).get("cose/liste") == ["lista:spesa"]
                     and calc["id"] in ((p.valuta(f"{P}.stato()") or {}).get("posti") or {}).get("conversazione", []), 5)
        st = p.valuta(f"{P}.stato()") or {}
        posti = st.get("posti", {})
        verifica("smistamento: le raccolte di Le mie cose, le vive in Adesso, il calcolo in Conversazione",
                 bool(ok) and posti.get("cose/agenda") == [S["timer"]["chiave"]] and posti.get("cose/lavori") == ["esecuzione:7"]
                 and posti.get("cose/documenti") == ["documento:5"] and "documento:5" in posti.get("adesso/corso", []),
                 json.dumps(posti)[:300])
        verifica("smistamento: niente fila delle schede recenti (la pagina di stanza)",
                 p.valuta("getComputedStyle(document.getElementById('cronologia')).display") == "none")
        clic(p, '#barra a[data-sezione="cose"]')
        ok = aspetta(lambda: (p.valuta(f"{P}.stato()") or {}).get("sezione") == "cose"
                     and p.valuta("location.hash") == "#/cose" and p.valuta("!document.getElementById('sez-cose').hidden"), 3)
        verifica("barra: Le mie cose (#/cose)", bool(ok))
        p.valuta("history.back(); 1")
        ok = aspetta(lambda: (p.valuta(f"{P}.stato()") or {}).get("sezione") == "adesso", 3)
        verifica("barra: il gesto indietro torna ad Adesso", bool(ok))
        raccolte_pc(p, hub)
        foto(p, "pc-1440x900.png")
        # «Parla»: il satellite riceve «tocco»
        ok = aspetta(lambda: p.valuta("!document.getElementById('pc-parla').hidden"), 3)
        prima = len(pc.ricevuti)
        clic(p, "#pc-parla")
        ok2 = aspetta(lambda: any(m.get("tipo") == "tocco" for m in pc.ricevuti[prima:]), 5)
        testo = aspetta(lambda: "ascolto" in (p.valuta("document.querySelector('#pc-parla .parla-testo').textContent") or ""), 3)
        verifica("«Parla»: c'è, il satellite del PC riceve «tocco», il pulsante dice «Ti ascolto»",
                 bool(ok) and bool(ok2) and bool(testo), json.dumps(pc.ricevuti[prima:]))
        # La casella per scrivere a destra; un file trascinato arriva nella casella
        verifica("la casella per scrivere sotto la conversazione, a destra",
                 p.valuta("!!document.querySelector('#pc-conv #scrivi')"))
        hub.conversazioni.voce("dario", "voce", stanza="studio")
        aspetta(lambda: not p.valuta("document.getElementById('scrivi-testo').disabled"), 3)
        p.valuta("""(() => { const dt = new DataTransfer();
          dt.items.add(new File(['un file di prova'], 'appunti.txt', {type: 'text/plain'}));
          document.body.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
          document.body.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); return 1; })()""")
        ok = aspetta(lambda: "appunti.txt" in (p.valuta("(document.querySelector('#pc-conv .allegato-info')||{}).textContent") or ""), 3)
        verifica("un file trascinato sulla pagina arriva nella casella", bool(ok))
        hub.conversazioni.chiudi()
        conversazione_a_destra(p, hub)
        cruscotto_e_pulisci(p, hub)
        # Le disposizioni
        for w, h, cosa in ((1440, 900, "tre colonne"), (1100, 800, "tre colonne"), (1000, 760, "conversazione dietro il pulsante"),
                           (700, 900, "barra in basso")):
            dimensione(p, w, h)
            time.sleep(0.3)
            m = p.valuta(MISURA) or {}
            foto(p, f"pc-{w}x{h}.png")
            d = f"{w}×{h} ({cosa})"
            verifica(f"{d}: la pagina non scorre, parti separate, niente testo fuori", not m.get("scorre") and not m.get("fuori"),
                     json.dumps(m.get("fuori"))[:240])
            verifica(f"{d}: contrasto AA e clic ≥ 44 px", not m.get("bassi") and not m.get("clic"),
                     json.dumps([m.get("bassi"), m.get("clic")])[:240])
            if w >= 1100:
                verifica(f"{d}: la conversazione aperta a destra, senza pulsante", m.get("conv") and not m.get("apri"))
            else:
                verifica(f"{d}: la conversazione chiusa, il pulsante c'è", not m.get("conv") and m.get("apri"))
            if w < 760:
                verifica(f"{d}: la barra in basso, larga", m.get("barraSotto"))
        dimensione(p, 1000, 760)
        clic(p, "#pc-conv-apri")
        ok = aspetta(lambda: p.valuta("getComputedStyle(document.getElementById('pc-conv')).display !== 'none'"), 2)
        foto(p, "pc-1000x760-conversazione.png")
        verifica("1000×760: il pulsante apre la conversazione sopra la pagina", bool(ok)
                 and p.valuta("getComputedStyle(document.getElementById('pc-conv')).position") == "fixed")
        p._chiama("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        p._chiama("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        ok = aspetta(lambda: p.valuta("getComputedStyle(document.getElementById('pc-conv')).display === 'none'"), 2)
        verifica("1000×760: Esc la chiude", bool(ok))
        p.pompa(0.3)
        errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
        verifica("schermo personale: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()


def raccolte_pc(p, hub):
    """Le mie cose sul PC personale (28/10, passo 2a): le tessere coi conti (più di due per riga),
    la pagina Liste dalla tessera, la spunta che manda il tocco giusto, clic ≥ 44 px e contrasto
    AA a 1440×900 e 700×900; il gesto indietro torna alle tessere."""
    P = "window.calliopePC"
    S = f"({P}.stato() || {{}})"
    p.valuta(f"{P}.vai('#/cose'); 1")
    ok = aspetta(lambda: len(p.valuta(f"{S}.tessere") or []) == 8, 5)
    tes = {x["id"]: x for x in p.valuta(f"{S}.tessere") or []}
    colonne = p.valuta("getComputedStyle(document.getElementById('tessere')).gridTemplateColumns.split(' ').length")
    verifica("PC: otto tessere in cima a Le mie cose, coi conti, più di due per riga",
             bool(ok) and tes.get("liste", {}).get("conto") == "1" and "ufficio" in tes and (colonne or 0) >= 3,
             f"{colonne} {json.dumps(tes)[:200]}")
    clic(p, '#tessere [data-tessera="liste"]')
    ok = aspetta(lambda: p.valuta("location.hash") == "#/cose/liste" and p.valuta(f"{S}.vistaCose") == "pagina"
                 and p.valuta(f"{S}.pagina") == ["lista:spesa"], 5)
    spunte = p.valuta("[...document.querySelectorAll('#pagina-schede button.spunta')].map((b) => b.dataset.voce)") or []
    verifica("PC: la pagina Liste dalla tessera, con le voci da spuntare",
             bool(ok) and spunte[:2] == ["latte", "uova"], json.dumps(spunte))
    while hub.ingresso.prendi() is not None:
        pass
    clic(p, '#pagina-schede button.spunta[data-voce="uova"]')
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() or {}
    verifica("PC: la spunta manda il tocco giusto (lista_togli con le uova, a nome di Dario)",
             bool(ok) and item.get("tipo") == "tocco" and item.get("tool") == "lista_togli"
             and item.get("argomenti") == {"cose": "uova", "lista": "spesa"} and item.get("persona") == "dario",
             json.dumps(item, ensure_ascii=False)[:300])
    for w, h in ((1440, 900), (700, 900)):
        dimensione(p, w, h)
        time.sleep(0.3)
        m = p.valuta(MISURA) or {}
        foto(p, f"pc-{w}x{h}-liste.png")
        verifica(f"PC {w}×{h} pagina Liste: contrasto AA, clic ≥ 44 px, niente fuori",
                 not m.get("bassi") and not m.get("clic") and not m.get("fuori") and not m.get("scorre"),
                 json.dumps([m.get("bassi"), m.get("clic"), m.get("fuori")])[:240])
    dimensione(p, 1440, 900)
    agenda_pc(p, hub, S)
    p.valuta("history.back(); 1")
    ok = aspetta(lambda: p.valuta("location.hash") == "#/cose" and p.valuta(f"{S}.vistaCose") == "tessere", 3)
    m = p.valuta(MISURA) or {}
    verifica("PC: il gesto indietro torna alle tessere; contrasto e clic delle tessere",
             bool(ok) and not m.get("bassi") and not m.get("clic"), json.dumps([m.get("bassi"), m.get("clic")])[:240])
    p.valuta(f"{P}.vai('#/adesso'); 1")


def agenda_pc(p, hub, S):
    """La pagina Agenda sul PC personale (28/10, passo 2b, #257): dalla tessera (passando dalle
    tessere), il timer di casa con «+1 minuto» e «Ferma» che mandano il tocco giusto; clic ≥ 44 px
    e contrasto AA a 1440×900 e 700×900."""
    from calliope.schermi import schede
    P = "window.calliopePC"
    agenda = hub.tool_ctx.agenda
    timer = next(it for it in agenda.items("dario") if it["kind"] == "timer")
    chiave = schede.chiave_timer(timer)
    p.valuta("history.back(); 1")
    aspetta(lambda: p.valuta("location.hash") == "#/cose", 3)
    clic(p, '#tessere [data-tessera="agenda"]')
    ok = aspetta(lambda: p.valuta("location.hash") == "#/cose/agenda" and p.valuta(f"{S}.vistaCose") == "pagina"
                 and (p.valuta(f"{S}.pagina") or [None])[0] == chiave, 5)
    tasti = p.valuta("[...document.querySelectorAll('#pagina-schede button.tasto-timer')].map((b) => b.dataset.tocco)") or []
    verifica("PC: la pagina Agenda dalla tessera, con i tasti del timer",
             bool(ok) and tasti == ["timer_piu", "timer_ferma"]
             and "messo da Bianca" in (p.valuta("document.querySelector('#pagina-schede .scheda').textContent") or ""),
             json.dumps([p.valuta(f"{S}.pagina"), tasti]))
    while hub.ingresso.prendi() is not None:
        pass
    clic(p, '#pagina-schede button.tasto-timer[data-tocco="timer_ferma"]')
    ok = aspetta(lambda: not hub.ingresso.vuoto(), 5)
    item = hub.ingresso.prendi() or {}
    verifica("PC: «Ferma» manda il tocco giusto (agenda_annulla su quel timer, a nome di Dario)",
             bool(ok) and item.get("tocco") == "timer_ferma" and item.get("tool") == "agenda_annulla"
             and item.get("bersaglio") == {"timer": timer["id"], "chiave": chiave} and item.get("persona") == "dario",
             json.dumps(item, ensure_ascii=False)[:300])
    hub.evento_a(item.get("schermo_id"), "tocco", {"tocco": "timer_ferma", "ok": True, "pagina": item.get("pagina")})
    for w, h in ((1440, 900), (700, 900)):
        dimensione(p, w, h)
        time.sleep(0.3)
        m = p.valuta(MISURA) or {}
        foto(p, f"pc-{w}x{h}-agenda.png")
        verifica(f"PC {w}×{h} pagina Agenda: contrasto AA, clic ≥ 44 px, niente fuori",
                 not m.get("bassi") and not m.get("clic") and not m.get("fuori") and not m.get("scorre"),
                 json.dumps([m.get("bassi"), m.get("clic"), m.get("fuori")])[:240])
    dimensione(p, 1440, 900)


def turno(domanda, risposta, t):
    return [{"role": "user", "content": domanda, "_turno": {"t": t, "luogo": "Studio", "canale": "voce"}},
            {"role": "assistant", "content": risposta}]


def conversazione_a_destra(p, hub):
    """La conversazione resta nella sua colonna anche quando dalla cronologia (al più 6 schede)
    escono le schede vecchie, e prende i turni nuovi."""
    from calliope.conversazione import Conversazione, turni
    from calliope.schermi import Mittente, schede
    dario = Mittente(persona="dario", nome="Dario", livello="amministra", certo=True)
    conv = Conversazione("persona:dario")
    conv.luogo = "studio"
    t0 = time.time() - 120
    hub.arch_conv.archivia(conv, turni(turno("Che ore sono?", "Sono le sei.", t0)), "dario", "Dario", ospite=False)
    conta = "document.querySelectorAll('#pc-chat .conv-turno').length"
    ok = aspetta(lambda: (p.valuta(conta) or 0) >= 1, 8)
    verifica("conversazione: i turni dell'archivio nella colonna a destra", bool(ok), str(p.valuta(conta)))
    for i in range(8):
        hub.invia(schede.calcolo(f"{i} + 1", str(i + 1)), dario)
        time.sleep(0.08)
    time.sleep(0.5)
    verifica("conversazione: resta a destra dopo otto schede", (p.valuta(conta) or 0) >= 1, str(p.valuta(conta)))
    hub.arch_conv.archivia(conv, turni(turno("Che ore sono?", "Sono le sei.", t0) + turno("E domani?", "Domani piove.", t0 + 30)),
                           "dario", "Dario", ospite=False)
    ok = aspetta(lambda: (p.valuta(conta) or 0) >= 2, 8)
    verifica("conversazione: prende i turni nuovi", bool(ok), str(p.valuta(conta)))
    # «Schermo intero» della conversazione: lo strato con i turni (seconda revisione della #255)
    clic(p, "#pc-chat [data-intero]")
    ok = aspetta(lambda: p.valuta("!!document.getElementById('strato-intero') && !document.getElementById('strato-intero').hidden"
                                  " && document.querySelectorAll('#intero-posto .conv-turno').length >= 2"), 3)
    verifica("conversazione: «Schermo intero» apre lo strato con i turni", bool(ok))
    p.valuta("document.getElementById('intero-chiudi').click(); 1")


def cruscotto_e_pulisci(p, hub):
    P = "window.calliopePC"
    ok = aspetta(lambda: p.valuta("!!document.getElementById('cruscotto-apri')"), 8)
    clic(p, "#cruscotto-apri")
    ok2 = aspetta(lambda: (p.valuta(f"{P}.stato()") or {}).get("sezione") == "io"
                  and p.valuta("!!document.querySelector('#sez-io .tipo-cruscotto')"), 10)
    verifica("cruscotto: il pulsante della testa porta in Io, con la scheda", bool(ok) and bool(ok2))
    # Il ridisegno periodico (ogni 30 s, «mostra» con segnale false) non riporta in Io
    p.valuta(f"{P}.vai('#/cose'); 1")
    aspetta(lambda: (p.valuta(f"{P}.stato()") or {}).get("sezione") == "cose", 2)
    p.valuta("(() => { const c = window.calliopeSchermo.cronologia().find((x) => x.tipo === 'cruscotto');"
             " document.dispatchEvent(new CustomEvent('calliope:mostra', {detail: {scheda: c, segnale: false}})); return 1; })()")
    time.sleep(0.4)
    verifica("cruscotto: il ridisegno periodico non riporta la pagina in Io",
             (p.valuta(f"{P}.stato()") or {}).get("sezione") == "cose")
    p.valuta(f"{P}.vai('#/io'); 1")
    verifica("pulisci: «Pulisci le mie schede» in Io", p.valuta("!document.getElementById('pc-pulisci').hidden"))
    clic(p, "#pc-pulisci")
    aspetta(lambda: "nuovo" in (p.valuta("document.getElementById('pc-pulisci').textContent") or ""), 2)
    clic(p, "#pc-pulisci")
    ok = aspetta(lambda: (p.valuta("document.getElementById('pc-pulisci-esito').textContent") or "") != "", 6)
    verifica("pulisci: due clic, l'esito detto", bool(ok), p.valuta("document.getElementById('pc-pulisci-esito').textContent"))
    p.valuta(f"{P}.vai('#/adesso'); 1")


def main() -> int:
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        exe = PTP.browser()
        if exe is None:
            print("Nessun Edge né Chromium: prova saltata.")
            return SALTATA
        cfg, srv, hub, web, pc, t_pc, t_stanza = avvia_server()
        try:
            stanza(exe, web, t_stanza)
            personale(exe, srv, hub, web, pc, t_pc)
        finally:
            web.ferma()
            srv.ferma()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
