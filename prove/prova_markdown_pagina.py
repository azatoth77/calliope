import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il lettore Markdown nella scheda del documento, nel browser vero (07/10/2026: i testi
dell'agente in Markdown; Edge o Chromium senza finestra, DevTools; senza si salta).

Server degli schermi e dei satelliti veri su 127.0.0.1 (come `prova_scheda_intera`), il
telefono e lo schermo dello studio di chi amministra. Una scheda con un testo dell'agente
ostile:
- `<script>`, HTML grezzo con attributi (`onerror`, `onclick`), `javascript:` in un
  collegamento, un'immagine da fuori: nessuno esegue niente (`window.__pwn` resta vuoto),
  nessun elemento script, img, iframe, a, style, svg, form nella scheda, nessun attributo oltre
  a class e data-md-*; il testo si legge com'è;
- una tabella di 300 righe: 200 disegnate e la nota delle altre; elenchi annidati 20 volte: al
  più 6 livelli; citazioni annidate 20 volte: al più 4;
- titoli, sommario in alto che porta al titolo toccato, grassetto, corsivo e codice;
- «Scarica PDF», «Scarica Word», «Scarica Markdown»: il file arriva davvero (scaricamenti del
  browser) e la scheda dice il nome; sullo schermo di un'altra persona la scheda non c'è;
- sul telefono la scheda a schermo intero: testo ≥ 16 px, niente di lato (la tabella scorre
  nel suo riquadro), contrasto AA (le misure di `prova_scheda_intera`);
- nessun errore JavaScript né violazione della CSP. ~25 s.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_cruscotto as PC
import prova_cruscotto_pagina as PCP
import prova_scheda_intera as PSI
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-markdown-pagina-"))
SCARICATI = TMP / "scaricati"
ERRORI = []
SALTATA = 77
T = "window.calliopeTelefono"
aspetta = PCP.aspetta

RIGHE = "\n".join(f"| riga {i} | {i * 3} |" for i in range(300))
ANNIDATI = "\n".join("  " * i + f"- livello {i}" for i in range(20))
OSTILE = f"""# Relazione sulle api <script>window.__pwn = 1</script>

<img src=x onerror="window.__pwn = 2">
<div onclick="window.__pwn = 3" style="position:fixed;inset:0">copre tutto</div>

Un testo con **grassetto**, *corsivo*, `codice <b>non grassetto</b>` e un
[collegamento](javascript:window.__pwn=4) e un'immagine ![grafico](http://192.0.2.1/x.png).

## Tabella grande

| Voce | Valore |
|---|---:|
{RIGHE}

## Annidati

{ANNIDATI}

{">" * 20} citazione profonda

### Una sottosezione

```html
<script>window.__pwn = 5</script>
```
"""


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({str(dettaglio)[:300]})" if dettaglio else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


CONTROLLI = r"""((sel) => {
  const s = document.querySelector(sel);
  if (!s) return null;
  const md = s.querySelector('.markdown');
  const vietati = [...s.querySelectorAll('script,img,iframe,a,object,embed,style,link,svg,form,input,video,audio')].map(e => e.tagName);
  const attr = new Set();
  s.querySelectorAll('.markdown *, .sommario-md *').forEach(e => [...e.attributes].forEach(a => attr.add(a.name)));
  const prof = (e, tag) => { let n = 0; for (let x = e; x && x !== md; x = x.parentElement) if (x.tagName === tag) n++; return n; };
  const lis = [...md.querySelectorAll('li')];
  const qs = [...md.querySelectorAll('blockquote')];
  return {
    pwn: window.__pwn === undefined ? null : window.__pwn,
    vietati, attributi: [...attr].sort(),
    testo: md.innerText.slice(0, 400),
    righe: md.querySelectorAll('.tabella-md tbody tr').length,
    nota: [...md.querySelectorAll('p.nota')].map(p => p.textContent),
    ul: Math.max(0, ...lis.map(li => prof(li, 'UL'))),
    citazioni: Math.max(0, ...qs.map(q => prof(q, 'BLOCKQUOTE'))),
    titoli: [...md.querySelectorAll('.md-titolo')].map(h => h.tagName + ' ' + h.textContent),
    sommario: [...s.querySelectorAll('.sommario-md button')].map(b => b.textContent),
    forti: [...md.querySelectorAll('strong,em,code')].map(e => e.tagName + ' ' + e.textContent),
    scarica: [...s.querySelectorAll('button[data-scarica]')].map(b => b.dataset.scarica),
  };
})"""


def controlla(p, sel, dove):
    c = p.valuta(CONTROLLI + f"({json.dumps(sel)})") or {}
    verifica(f"{dove}: niente eseguito (window.__pwn vuoto)", c.get("pwn") is None, c.get("pwn"))
    verifica(f"{dove}: nessun elemento pericoloso nella scheda", c.get("vietati") == [],
             c.get("vietati"))
    verifica(f"{dove}: solo gli attributi del lettore (class, data-md-*, type)",
             set(c.get("attributi") or []) <= {"class", "data-md-ancora", "data-md-vai", "type"},
             c.get("attributi"))
    t = c.get("testo", "")
    verifica(f"{dove}: l'HTML si legge come testo", "<script>window.__pwn = 1</script>" in t
             and 'onerror="window.__pwn = 2"' in t, t[:200])
    verifica(f"{dove}: collegamento come testo, indirizzo tra parentesi; immagine segnaposto",
             "collegamento (javascript:window.__pwn=4)" in t and "[immagine: grafico]" in t, t)
    verifica(f"{dove}: tabella di 300 righe → 200 e la nota delle altre",
             c.get("righe") == 200 and any("altre 100 righe" in n for n in c.get("nota", [])),
             (c.get("righe"), c.get("nota")))
    verifica(f"{dove}: elenchi annidati al più 6, citazioni al più 4",
             c.get("ul") == 6 and c.get("citazioni") == 4, (c.get("ul"), c.get("citazioni")))
    verifica(f"{dove}: titoli e sommario", c.get("titoli", [])[:2] == [
        "H2 Relazione sulle api <script>window.__pwn = 1</script>", "H3 Tabella grande"]
        and len(c.get("sommario", [])) == 4, (c.get("titoli"), c.get("sommario")))
    verifica(f"{dove}: grassetto, corsivo e codice", c.get("forti", [])[:3] == [
        "STRONG grassetto", "EM corsivo", "CODE codice <b>non grassetto</b>"], c.get("forti"))
    verifica(f"{dove}: «Scarica» in Markdown, PDF e Word", c.get("scarica") == ["md", "pdf", "word"],
             c.get("scarica"))
    return c


def scarica(p, sel, formato, inizio: bytes):
    cartella = SCARICATI / p.cartella
    prima = set(cartella.glob("*"))
    p.valuta(f"document.querySelector({json.dumps(sel + f' button[data-scarica={formato}]')}).click(); 1")
    ok = aspetta(lambda: [f for f in cartella.glob("*") if f not in prima
                          and not f.name.endswith((".crdownload", ".tmp"))], 15)
    nuovi = [f for f in cartella.glob("*") if f not in prima and not f.name.endswith(".crdownload")]
    dati = nuovi[0].read_bytes() if nuovi else b""
    esito = p.valuta(f"(document.querySelector({json.dumps(sel + ' .esito-scarica')}) || {{}}).textContent")
    verifica(f"«Scarica {formato}»: il file arriva negli scaricamenti", bool(ok)
             and dati.startswith(inizio) and (esito or "").startswith("Scaricato:"),
             ([f.name for f in nuovi], esito))


def prova(exe, srv, hub, web):
    from calliope.schermi import schede
    from calliope.schermi.hub import Mittente
    _, t_tel = srv.archivio.crea_con_token("telefono-dario", proprietario="dario",
                                           proprietario_nome="Dario")
    _, t_studio = hub.archivio.crea_con_token("studio", proprietario="dario",
                                              proprietario_nome="Dario")
    _, t_bianca = hub.archivio.crea_con_token("camera", proprietario="bianca",
                                              proprietario_nome="Bianca")
    hub._rinfresca()
    SCARICATI.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{web.port}/"
    tel = PTP.Pagina(exe, base + "telefono/", profilo="profilo-md-tel",
                     opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                              "--window-size=390,844"))
    studio = PTP.Pagina(exe, base + f"#t={t_studio}", profilo="profilo-md-studio",
                        opzioni=("--window-size=1280,800",))
    bianca = PTP.Pagina(exe, base + f"#t={t_bianca}", profilo="profilo-md-bianca",
                        opzioni=("--window-size=1280,800",))
    try:
        for p, nome in ((tel, "telefono"), (studio, "studio")):
            p.cartella = nome
            (SCARICATI / nome).mkdir(parents=True, exist_ok=True)
            p._chiama("Page.setDownloadBehavior", {"behavior": "allow",
                                                   "downloadPath": str(SCARICATI / nome)})
        aspetta(lambda: tel.valuta("document.readyState") == "complete", 10)
        tel.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(t_tel)}); 1")
        tel._chiama("Page.reload")
        time.sleep(0.5)
        PSI.dimensione(tel, 375, 812)
        ok = aspetta(lambda: tel.valuta(f"!!window.calliopeTelefono && {T}.st.collegato"), 15)
        verifica("telefono collegato", bool(ok))
        aspetta(lambda: tel.valuta("!!window.calliopeSchermo && document.getElementById('stato')"
                                   ".className.includes('ok')"), 10)
        for p in (studio, bianca):
            aspetta(lambda p=p: p.valuta("document.getElementById('stato-testo').textContent")
                    == "collegato", 10)
        aspetta(lambda: len(hub.collegati()) >= 3, 10)
        card = schede.documento_markdown("Relazione sulle api", OSTILE, ident="L9",
                                         riassunto="Ho trovato tre fonti sulle api.",
                                         nome_file="risultato.md", cartella="2026-10-07 api")
        r = hub.invia(card, Mittente(persona="dario", nome="Dario", livello="amministra",
                                     certo=True), forza=True)
        verifica("la scheda va agli schermi personali di Dario (telefono e studio)",
                 len(r["destinatari"]) == 2, r)
        sel_s = '#principale article.scheda[data-chiave="lavoro:L9"]'
        ok = aspetta(lambda: studio.valuta(f"!!document.querySelector({json.dumps(sel_s)} + ' .markdown')"), 10)
        verifica("schermo dello studio: la scheda con il lettore Markdown", bool(ok))
        controlla(studio, sel_s, "studio")
        # Il sommario porta al titolo
        studio.valuta(f"document.querySelector({json.dumps(sel_s)} + ' .corpo').scrollTop = 0; 1")
        studio.valuta(f"document.querySelectorAll({json.dumps(sel_s)} + ' .sommario-md button')[2].click(); 1")
        time.sleep(0.3)
        vis = studio.valuta(f"(() => {{ const h = document.querySelector({json.dumps(sel_s)} + ' [data-md-ancora=\"2\"]');"
                            " const r = h.getBoundingClientRect(); return [h.textContent, r.top >= 0 && r.top < innerHeight / 2]; })()")
        verifica("il sommario porta al titolo toccato", vis and vis[0] == "Annidati" and vis[1], vis)
        scarica(studio, sel_s, "pdf", b"%PDF-")
        scarica(studio, sel_s, "word", b"PK")
        scarica(studio, sel_s, "md", b"# Relazione sulle api")
        PSI.foto(studio, "markdown-studio-1280x800.png")
        verifica("sullo schermo di un'altra persona la scheda non c'è",
                 not bianca.valuta("!!document.querySelector('.markdown')"))

        # ── il telefono: carosello e schermo intero ──
        ok = aspetta(lambda: tel.valuta("!!document.querySelector('#binario [data-chiave=\"lavoro:L9\"] .markdown')"), 10)
        verifica("telefono: la scheda nel carosello", bool(ok))
        sel_t = '#binario [data-chiave="lavoro:L9"]'
        controlla(tel, sel_t, "telefono (carosello)")
        scarica(tel, sel_t, "pdf", b"%PDF-")
        tel.valuta(f"{T}.vaiA('lavoro:L9'); 1")
        time.sleep(0.2)
        PSI.tocca(tel, sel_t + " .espandi")
        ok = aspetta(lambda: tel.valuta(f"{T}.carosello().intera") == "lavoro:L9", 3)
        verifica("telefono: «Espandi» apre il documento a schermo intero", bool(ok))
        controlla(tel, "#intera-posto article.scheda", "telefono (schermo intero)")
        for w, hh, nome in PSI.DIMENSIONI:
            PSI.dimensione(tel, w, hh)
            PSI.misura_strato(tel, "documento in Markdown", f"{w}×{hh}")
            PSI.foto(tel, f"markdown-intero-{nome}-{w}x{hh}.png")
        PSI.dimensione(tel, 375, 812)
        for p, nome in ((tel, "telefono"), (studio, "studio"), (bianca, "camera")):
            p.pompa(0.3)
            errori = [x for x in p.log if x.startswith("ECCEZIONE") or "Content Security" in x]
            verifica(f"{nome}: nessun errore JavaScript né violazione della CSP", not errori,
                     "; ".join(errori)[:300])
    finally:
        for p in (tel, studio, bianca):
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
    for x in (PTP.TMP, PC.TMP, PCP.TMP, PSI.TMP):
        shutil.rmtree(x, ignore_errors=True)
    PTP.TMP = TMP
    PCP.TMP = TMP
    try:
        cfg, srv, hub, web = PCP.avvia()
        try:
            prova(exe, srv, hub, web)
        finally:
            web.ferma()
            srv.ferma()
            hub.archivio.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
