"""Prova a secco del telefono a sezioni (27/10/2026, passo 1 di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md; area docs/aree/schermi-telefono.md).

Le schede non cambiano: cambia solo dove stanno sul telefono. La casa di ogni tipo è scritta
due volte, in `schede.SEZIONE_DI_TIPO` (il server la mette nella scheda, `sezione`) e in
`SEZIONE_DI_TIPO` di schermo.js (per le schede che non passano da `schede.nuova`: chat,
cruscotto); le due tabelle devono restare uguali.

1. **Le tabelle**: quella di schede.py e quella di schermo.js uguali; ogni tipo di `NOMI_TIPO` ha
   la sua casa; ogni sezione è una delle cinque; ogni raccolta ha il suo elenco in index.html.
2. **Il server**: `schede.nuova` scrive la sezione (lista, timer, documento, calcolo, casa,
   conoscente, cruscotto); un tipo sconosciuto va nella conversazione; la scheda dello
   sviluppo (un documento in Markdown diventato «sviluppo») sta in Lavori, non in Documenti.
3. **La regola «viva»** (schermo.js, con node): il gioco chiuso su questa pagina (✕) no, un altro
   gioco sì; il timer che corre sì, scaduto o annullato no; il
   promemoria entro un'ora sì, fra due ore no; il lavoro in coda, in corso o in attesa sì, finito
   no; il programma in corso; lo sviluppo aperto; il modulo aperto sì, inviato no; il gioco non
   chiuso; la voce nuova aperta; lista, documento e
   casa appena cambiati sì, dopo due minuti no; risposta e calcolo mai (sono l'ultima risposta,
   non vive). `sezioneDi`: vale la sezione del server; una sezione inventata va nella
   conversazione.
4. **Il router** (sezioni.js `percorsoDa`, comune a telefono e PC dal passo 1b, con node): #/cose/liste, il frammento vuoto e uno
   sconosciuto (Adesso), la chiave di una scheda con i due punti nel percorso; una sezione
   nascosta sul telefono di un minore (passo 1c) è Adesso. In Adesso le schede con uno stato o
   dei campi (gioco, sviluppo, cassetto, chat, voce nuova) sono solo un rimando.
5. **Il layout compatto** (28/10, #277, misurato nella pagina vera da prova_telefono_schermo e
   prova_cronologia_pagina): la media query di telefono.css vale in verticale a 375×812, 375×667,
   320×568 e 320×693 (iPhone 13 mini con lo «Zoom schermo»), non a 390×844 né a 412×915 né in
   orizzontale; dentro, niente regole per «In auto», tocchi ≥ 44 px anche col testo ingrandito del
   20 % (in rem), la riga dello stato ritagliata per i lettori; «Parla» descritto dal suggerimento
   e lo stato piccolo nascosto ai lettori (lo dice già la riga dello stato).

    python prove/prova_sezioni.py
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RADICE = Path(__file__).resolve().parent.parent
PAGINA = RADICE / "calliope" / "schermi" / "pagina"
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def oggetto_js(testo: str, nome: str) -> dict:
    """Un oggetto letterale semplice di schermo.js ({chiave: "valore", …}) come dizionario."""
    m = re.search(r"const " + nome + r" = \{(.*?)\};", testo, re.S)
    return dict(re.findall(r"(\w+): \"([^\"]*)\"", m.group(1))) if m else {}


def tabelle():
    from calliope.schermi import schede
    js = (PAGINA / "schermo.js").read_text(encoding="utf-8")
    sez_js = oggetto_js(js, "SEZIONE_DI_TIPO")
    nomi = oggetto_js(js, "NOMI_TIPO")
    verifica("tabelle: SEZIONE_DI_TIPO uguale in schede.py e in schermo.js",
             sez_js == schede.SEZIONE_DI_TIPO and len(sez_js) >= 20,
             json.dumps({k: (sez_js.get(k), schede.SEZIONE_DI_TIPO.get(k))
                         for k in set(sez_js) ^ set(schede.SEZIONE_DI_TIPO)
                         | {k for k in sez_js if sez_js[k] != schede.SEZIONE_DI_TIPO.get(k)}}))
    mancano = [t for t in nomi if t not in schede.SEZIONE_DI_TIPO]
    verifica("tabelle: ogni tipo di NOMI_TIPO ha la sua sezione", not mancano and len(nomi) >= 20, str(mancano))
    fuori = {t: s for t, s in schede.SEZIONE_DI_TIPO.items() if s.split("/")[0] not in schede.SEZIONI}
    verifica("tabelle: ogni sezione è una delle cinque", not fuori, str(fuori))
    html = (PAGINA / "telefono" / "index.html").read_text(encoding="utf-8")
    posti = set(re.findall(r'data-posto="([^"]+)"', html))
    senza = sorted({s for s in schede.SEZIONE_DI_TIPO.values() if s not in posti})
    verifica("tabelle: ogni sezione e raccolta ha il suo elenco nella pagina del telefono", not senza, str(senza))
    sezioni = set(re.findall(r'<section id="sez-(\w+)"', html))
    barra = re.findall(r'<a href="#/(\w+)" data-sezione="(\w+)"', html)
    verifica("pagina: cinque sezioni e la barra con le cinque, nello stesso ordine",
             sezioni == set(schede.SEZIONI) and [a for a, _ in barra] == list(schede.SEZIONI)
             and all(a == b for a, b in barra), json.dumps([sorted(sezioni), barra]))


def server():
    from calliope.schermi import schede
    casi = {
        "lista": schede.lista("spesa", ["latte"]),
        "timer": schede.timer({"id": 1, "label": "pasta", "due": 2e9}),
        "calcolo": schede.calcolo("2 + 2", "4"),
        "casa": schede.nuova("casa", "Cucina", schede.CASA, righe=[]),
        "documento": schede.documento_markdown("Relazione", "# Relazione\n\nTesto."),
        "conoscente": schede.nuova("conoscente", "Una voce nuova", schede.PERSONALE),
        "cruscotto": schede.nuova("cruscotto", "Stato", schede.PERSONALE),
    }
    attese = {"lista": "cose/liste", "timer": "cose/agenda", "calcolo": "conversazione", "casa": "casa",
              "documento": "cose/documenti", "conoscente": "casa", "cruscotto": "io"}
    viste = {k: c.get("sezione") for k, c in casi.items()}
    verifica("server: schede.nuova scrive la sezione di ogni tipo", viste == attese, json.dumps(viste))
    verifica("server: un tipo sconosciuto va nella conversazione",
             schede.nuova("boh", "Boh", schede.PUBBLICA)["sezione"] == "conversazione")
    verifica("server: la sezione si può dare a mano (vale quella passata)",
             schede.nuova("testo", "Da leggere", schede.PUBBLICA, sezione="cose/documenti")["sezione"] == "cose/documenti")
    # La scheda dello sviluppo nasce come documento in Markdown e cambia tipo (sviluppo.py)
    from calliope.sviluppo import Sviluppi
    src = (RADICE / "calliope" / "sviluppo.py").read_text(encoding="utf-8")
    i = src.index('card["tipo"] = "sviluppo"')
    verifica("server: la scheda dello sviluppo (documento diventato «sviluppo») sta in Lavori",
             'card["sezione"] = schede.sezione_di("sviluppo")' in src[i:i + 200]
             and schede.sezione_di("sviluppo") == "cose/lavori" and hasattr(Sviluppi, "scheda"))


# Il pezzo di schermo.js con le tabelle e `viva`, da SEZIONE_DI_TIPO alla tabella che viene dopo
PROVA_VIVA = r"""
const ora = 1800000000;
const casi = [
  ["timer che corre", {tipo: "timer", timer: [{fine: ora + 60}]}, true],
  ["timer scaduto", {tipo: "timer", timer: [{fine: ora + 60, stato: "scaduto"}]}, false],
  ["timer passato", {tipo: "timer", timer: [{fine: ora - 1}]}, false],
  ["promemoria fra 30 minuti", {tipo: "promemoria", voci: [{ts: ora + 1800}]}, true],
  ["promemoria fra due ore", {tipo: "promemoria", voci: [{ts: ora + 7200}]}, false],
  ["lavoro in attesa", {tipo: "lavoro", stato: "in_attesa"}, true],
  ["lavoro in coda", {tipo: "lavoro", stato: "in_coda"}, true],
  ["lavoro finito", {tipo: "lavoro", stato: "fatto"}, false],
  ["programma in corso", {tipo: "esecuzione", stato: "in_corso"}, true],
  ["programma finito", {tipo: "esecuzione", stato: "fatto"}, false],
  ["sviluppo aperto", {tipo: "sviluppo", sviluppo: {stato: "aperta"}}, true],
  ["sviluppo chiuso", {tipo: "sviluppo", sviluppo: {stato: "chiusa"}}, false],
  ["modulo aperto", {tipo: "modulo", stato: "aperto"}, true],
  ["modulo inviato", {tipo: "modulo", stato: "inviato"}, false],
  ["gioco aperto", {tipo: "gioco"}, true],
  ["gioco chiuso", {tipo: "gioco", stato: "chiuso"}, false],
  ["gioco chiuso su questa pagina (✕)", {tipo: "gioco", partita: "p1"}, false, (p) => p === "p1"],
  ["un altro gioco aperto", {tipo: "gioco", partita: "p2"}, true, (p) => p === "p1"],
  ["voce nuova aperta", {tipo: "conoscente", aperta: true}, true],
  ["voce nuova decisa", {tipo: "conoscente", aperta: false}, false],
  ["lista appena cambiata", {tipo: "lista", creata: ora - 30}, true],
  ["lista di dieci minuti fa", {tipo: "lista", creata: ora - 600}, false],
  ["casa appena cambiata", {tipo: "casa", creata: ora - 10}, true],
  ["documento di ieri", {tipo: "documento", creata: ora - 86400}, false],
  ["calcolo appena fatto", {tipo: "calcolo", creata: ora - 5}, false],
  ["risposta appena data", {tipo: "risposta", creata: ora - 5}, false],
];
const out = casi.map(([n, c, atteso, chiusa]) => [n, viva(c, ora, chiusa) === atteso]);
const sez = [
  ["sezione del server", sezioneDi({tipo: "testo", sezione: "cose/documenti"}) === "cose/documenti"],
  ["sezione dalla tabella", sezioneDi({tipo: "lista"}) === "cose/liste"],
  ["sezione inventata", sezioneDi({tipo: "lista", sezione: "cantina"}) === "conversazione"],
  ["tipo sconosciuto", sezioneDi({tipo: "boh"}) === "conversazione"],
];
console.log(JSON.stringify(out.concat(sez)));
"""

PROVA_ROUTER = r"""
const vis = { nascoste: { sezioni: [], raccolte: [] } };
const casi = [
  ["#/cose/liste", ["cose", "liste"]],
  ["", ["adesso"]],
  ["#", ["adesso"]],
  ["#/boh", ["adesso"]],
  ["#/io", ["io"]],
  ["#/cose/liste/lista%3Aspesa", ["cose", "liste", "lista:spesa"]],
  ["#cose", ["cose"]],
];
const out = casi.map(([h, atteso]) => [h, JSON.stringify(percorsoDa(h)) === JSON.stringify(atteso)]);
// Sul telefono di un minore (27/10, passo 1c): una sezione nascosta è Adesso
vis.nascoste.sezioni = ["casa"];
out.push(["#/casa nascosta", JSON.stringify(percorsoDa("#/casa")) === JSON.stringify(["adesso"])]);
out.push(["#/cose con Casa nascosta", JSON.stringify(percorsoDa("#/cose")) === JSON.stringify(["cose"])]);
console.log(JSON.stringify(out));
"""


def node(codice: str):
    with tempfile.TemporaryDirectory(prefix="calliope-sezioni-") as d:
        f = Path(d) / "prova.js"
        f.write_text(codice, encoding="utf-8")
        r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode != 0:
        return None, r.stderr[-400:]
    return json.loads(r.stdout.strip().splitlines()[-1]), ""


def viva():
    js = (PAGINA / "schermo.js").read_text(encoding="utf-8")
    i = js.index("  const SEZIONE_DI_TIPO = {")
    j = js.index("  // Il programma di un lavoro mentre gira")
    out, err = node(js[i:j] + PROVA_VIVA)
    verifica("viva: il pezzo di schermo.js gira da solo in node", out is not None, err)
    for nome, ok in out or []:
        verifica(f"viva: {nome}", ok)


def router():
    # Dal passo 1b il router sta in sezioni.js, comune al telefono e al PC personale
    js = (PAGINA / "sezioni.js").read_text(encoding="utf-8")
    titoli = re.search(r"const TITOLI_SEZIONE = \{.*?\};", js).group(0)
    m = re.search(r"    function percorsoDa\(hash\) \{.*?\n    \}\n", js, re.S)
    out, err = node(titoli + "\n" + m.group(0) + PROVA_ROUTER)
    verifica("router: percorsoDa di sezioni.js gira da solo in node", out is not None, err)
    tel = (PAGINA / "telefono" / "telefono.js").read_text(encoding="utf-8")
    verifica("router: il telefono usa sezioni.js, senza un router suo",
             "CalliopeSezioni.crea(" in tel and "function percorsoDa" not in tel
             and '<script src="/sezioni.js"' in (PAGINA / "telefono" / "index.html").read_text(encoding="utf-8"))
    for h, ok in out or []:
        verifica(f"router: «{h}»", ok)
    # In Adesso un rimando, mai una seconda copia, per le schede con uno stato o dei campi
    m = re.search(r"const TIPI_RIMANDO = new Set\(\[(.*?)\]\)", js, re.S)
    rimandi = set(re.findall(r'"(\w+)"', m.group(1))) if m else set()
    verifica("rimandi: gioco, sviluppo, cassetto, chat e voce nuova in Adesso solo come rimando",
             {"gioco", "sviluppo", "cassetto", "chat", "conoscente"} <= rimandi,
             str(sorted(rimandi)))


def compatto():
    css = (PAGINA / "telefono" / "telefono.css").read_text(encoding="utf-8")
    m = re.search(r"@media \(orientation: portrait\) and \(max-width: (\d+)px\), "
                  r"\(orientation: portrait\) and \(max-height: (\d+)px\) \{", css)
    verifica("compatto: la media query in telefono.css", m is not None)
    if not m:
        return
    larg, alt = int(m.group(1)), int(m.group(2))

    def vale(w, h):
        return h > w and (w <= larg or h <= alt)
    for w, h, atteso in ((375, 812, True), (375, 667, True), (320, 568, True), (320, 693, True),
                         (390, 844, False), (412, 915, False), (812, 375, False), (667, 375, False)):
        verifica(f"compatto: a {w}×{h} {'sì' if atteso else 'no'}", vale(w, h) == atteso)
    # il blocco, con le graffe bilanciate
    i, prof = m.end(), 1
    j = i
    while prof and j < len(css):
        prof += {"{": 1, "}": -1}.get(css[j], 0)
        j += 1
    blocco = css[i:j - 1]
    verifica("compatto: niente regole per «In auto» (lì i bersagli grandi)", 'data-modo="auto"' not in blocco)
    minimi = [float(x) for x in re.findall(r"min-(?:height|width): ([\d.]+)rem", blocco)]
    # 44 px col testo di base (17 px) e col testo ingrandito del 20 % (i rem crescono con lui)
    verifica("compatto: tocchi ≥ 44 px (min-height e min-width ≥ 2,6rem)",
             minimi and min(minimi) * 17 >= 44, str(minimi))
    verifica("compatto: la riga dello stato resta per i lettori, ritagliata",
             re.search(r"\.voce-riga \.voce \{[^}]*clip: rect\(0 0 0 0\)", blocco) is not None)
    html = (PAGINA / "telefono" / "index.html").read_text(encoding="utf-8")
    tel = (PAGINA / "telefono" / "telefono.js").read_text(encoding="utf-8")
    # «Parla» descritto dal suggerimento solo quando non si vede (29/10, #287: VoiceOver lo leggeva
    # due volte): niente aria-describedby fisso nella pagina, lo mette descriviParla; la media query
    # di telefono.js è quella del CSS
    verifica("compatto: «Parla» descritto dal suggerimento solo quando è nascosto, lo stato piccolo nascosto ai lettori",
             'id="parla" type="button" class="parla">' in html and 'aria-describedby="tel-dove"' not in html
             and 'class="parla-stato" aria-hidden="true"' in html
             and 'attr(b, "aria-describedby", "tel-dove")' in tel and 'removeAttribute("aria-describedby")' in tel)
    mq = re.search(r'matchMedia\("([^"]+)"\)', tel)
    verifica("compatto: la media query di telefono.js è uguale a quella del CSS",
             mq is not None and css[m.start() + len("@media "):m.end() - 2] == mq.group(1),
             mq.group(1) if mq else None)
    # Il testo fermo al 100 % solo su iOS (29/10, #287): su Android i Chrome di prima perdevano il
    # «Ridimensionamento testo»
    senza_commenti = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    fuori_ios = re.sub(r"@supports \(-webkit-touch-callout: none\) \{[^{}]*\{[^{}]*\}\s*\}", "", senza_commenti)
    verifica("text-size-adjust solo dentro @supports (-webkit-touch-callout: none), cioè solo su iOS",
             "text-size-adjust" in css and "text-size-adjust" not in fuori_ios)
    verifica("compatto: il suggerimento segnato «ovvio» e lo stato breve scritto in «Parla»",
             'attr(d, "data-ovvio"' in tel and 'querySelector(".parla-stato")' in tel)


def scrittura():
    """Scrivere nella Conversazione (28/10, #301), a secco: la tastiera non ridimensiona la pagina
    (interactive-widget), la barra si nasconde solo con la tastiera aperta, la casella a 16 px, la
    pagina apposta non c'è più, in auto niente casella."""
    html = (PAGINA / "telefono" / "index.html").read_text(encoding="utf-8")
    css = (PAGINA / "telefono" / "telefono.css").read_text(encoding="utf-8")
    tel = (PAGINA / "telefono" / "telefono.js").read_text(encoding="utf-8")
    verifica("scrittura: la tastiera non ridimensiona la pagina (interactive-widget=resizes-visual, #287)",
             re.search(r'<meta name="viewport" content="[^"]*interactive-widget=resizes-visual', html) is not None)
    verifica("scrittura: la pagina apposta e «Allega» nella riga della voce non ci sono più",
             'id="strato-scrivi"' not in html and 'id="foto-apri"' not in html and "strato-scrivi" not in tel)
    verifica("scrittura: la casella al posto della riga della voce, la barra nascosta solo con la tastiera",
             'id="scrivi-posto" class="scrivi-riga"' in html
             and re.search(r"\.vista\[data-scrittura\] \.voce-riga \{ display: none; \}", css) is not None
             and re.search(r"\.vista\.tastiera \.barra \{ display: none; \}", css) is not None
             and "visualViewport" in tel)
    m = re.search(r"\.telefono \.scrivi textarea \{[^}]*font-size: max\(16px", css)
    verifica("scrittura: il testo della casella mai sotto i 16 px (iOS non ingrandisce la pagina)", m is not None)
    verifica("scrittura: in auto niente casella", '.vista[data-modo="auto"] .scrivi-riga' in css)
    # le regole del compatto non guardano la tastiera: la media query resta su larghezza e altezza
    i = css.index("@media (orientation: portrait) and (max-width: ")
    i, prof, j = css.index("{", i) + 1, 1, css.index("{", i) + 1
    while prof and j < len(css):
        prof += {"{": 1, "}": -1}.get(css[j], 0)
        j += 1
    verifica("scrittura: il compatto non dipende dalla tastiera (nessuna regola .tastiera nel compatto)",
             ".tastiera" not in css[i:j] and ".invia-icona" in css[i:j])


def main() -> int:
    tabelle()
    server()
    compatto()
    scrittura()
    if shutil.which("node"):
        viva()
        router()
    else:
        print("SALTATA IN PARTE: node non c'è (regola «viva» e router)")
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
