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
   chiuso; gli esercizi aperti o in pausa, finiti no; la voce nuova aperta; lista, documento e
   casa appena cambiati sì, dopo due minuti no; risposta e calcolo mai (sono l'ultima risposta,
   non vive). `sezioneDi`: vale la sezione del server; una sezione inventata va nella
   conversazione.
4. **Il router** (telefono.js `percorsoDa`, con node): #/cose/liste, il frammento vuoto e uno
   sconosciuto (Adesso), la chiave di una scheda con i due punti nel percorso. In Adesso le
   schede con uno stato o dei campi (gioco, esercizi, sviluppo, cassetto, chat, voce nuova) sono
   solo un rimando.

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
  ["esercizi aperti", {tipo: "esercizio", stato: "aperta"}, true],
  ["esercizi in pausa", {tipo: "esercizio", stato: "pausa"}, true],
  ["esercizi finiti", {tipo: "esercizio", stato: "finita"}, false],
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
const casi = [
  ["#/cose/liste", ["cose", "liste"]],
  ["", ["adesso"]],
  ["#", ["adesso"]],
  ["#/boh", ["adesso"]],
  ["#/io", ["io"]],
  ["#/cose/liste/lista%3Aspesa", ["cose", "liste", "lista:spesa"]],
  ["#cose", ["cose"]],
];
console.log(JSON.stringify(casi.map(([h, atteso]) => [h, JSON.stringify(percorsoDa(h)) === JSON.stringify(atteso)])));
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
    js = (PAGINA / "telefono" / "telefono.js").read_text(encoding="utf-8")
    titoli = re.search(r"const TITOLI_SEZIONE = \{.*?\};", js).group(0)
    m = re.search(r"function percorsoDa\(hash\) \{.*?\n\}\n", js, re.S)
    out, err = node(titoli + "\n" + m.group(0) + PROVA_ROUTER)
    verifica("router: percorsoDa di telefono.js gira da solo in node", out is not None, err)
    for h, ok in out or []:
        verifica(f"router: «{h}»", ok)
    # In Adesso un rimando, mai una seconda copia, per le schede con uno stato o dei campi
    m = re.search(r"const TIPI_RIMANDO = new Set\(\[(.*?)\]\)", js, re.S)
    rimandi = set(re.findall(r'"(\w+)"', m.group(1))) if m else set()
    verifica("rimandi: gioco, esercizi, sviluppo, cassetto, chat e voce nuova in Adesso solo come rimando",
             {"gioco", "esercizio", "esercizi_riepilogo", "sviluppo", "cassetto", "chat", "conoscente"} <= rimandi,
             str(sorted(rimandi)))


def main() -> int:
    tabelle()
    server()
    if shutil.which("node"):
        viva()
        router()
    else:
        print("SALTATA IN PARTE: node non c'è (regola «viva» e router)")
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
