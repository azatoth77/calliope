"""Dagli alberi UIA ai candidati: filtro degli elementi azionabili, etichette leggibili e
ordinamento per pertinenza rispetto allo scopo detto a voce (lessicale + embedding leggero).

Solo lettura di file in dati/alberi/: nessun accesso al PC.
"""

import json
import os
import math
import re
import time
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

QUI = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(QUI / "modelli" / "hf"))  # modelli fuori da git
ALBERI = QUI / "dati" / "alberi"

AZIONI = {"Invoke", "Toggle", "SelectionItem", "ExpandCollapse", "RangeValue"}
TIPI_SCARTATI = {"TextControl", "ImageControl", "StatusBarControl", "HeaderControl",
                 "ScrollBarControl", "WindowControl", "TitleBarControl", "MenuBarControl",
                 "ListControl", "TreeControl", "ToolBarControl", "TabControl", "PaneControl",
                 "AppBarControl", "DocumentControl_"}
COLONNE = {"Nome", "Stato", "Ultima modifica", "Tipo", "Dimensione", "Data acquisizione",
           "Data creazione", "Autori", "Titolo", "Posizione originale", "Data eliminazione"}
TIPI_TESTO = {"EditControl", "ComboBoxControl", "DocumentControl"}

TIPO_IT = {
    "ButtonControl": "pulsante", "SplitButtonControl": "pulsante", "ListItemControl": "voce",
    "TreeItemControl": "voce dell'albero", "TabItemControl": "scheda", "MenuItemControl": "menu",
    "HyperlinkControl": "collegamento", "EditControl": "casella di testo",
    "ComboBoxControl": "menu a tendina", "SliderControl": "cursore",
    "RadioButtonControl": "opzione", "CheckBoxControl": "casella di spunta",
    "DocumentControl": "area del documento", "GroupControl": "gruppo",
}

STOP = set("""il lo la i gli le un uno una di a da in con su per tra fra del dello della dei degli
delle al allo alla ai agli alle dal dallo dalla dai dagli dalle nel nello nella nei negli nelle
col sul sullo sulla sui sugli sulle e o che mi ti ci si me te ce se ne questo questa questi
queste quel quella sta sto po un' l' d' dell' all' nell' sull' mio mia tuo tua per favore
calliope""".split())


def normalizza(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def parole(s):
    return [w for w in re.findall(r"[a-z0-9]+", normalizza(s)) if w not in STOP and len(w) > 1]


def carica(schermata):
    return json.loads((ALBERI / f"{schermata}.json").read_text(encoding="utf-8"))


def _contesto(e):
    """Il nome dell'antenato più vicino che ne ha uno (gruppo, elenco, dispositivo…)."""
    for p in reversed(e["percorso"][1:]):
        tipo, _, nome = p.partition(":")
        if tipo == "TreeItem":  # l'albero di navigazione annida male le voci
            return ""
        if nome.strip() and tipo not in ("Window", "Pane", "Button", "MenuItem", "SplitButton"):
            return nome.strip()
    return ""


def etichetta(e):
    nome = re.sub(r"\s+", " ", e["nome"]).strip()
    if len(nome) > 90:
        nome = nome[:90] + "…"
    tipo = TIPO_IT.get(e["tipo"], (e.get("tipo_locale") or e["tipo"]).lower())
    stato = []
    if e.get("toggle") is not None:
        stato.append("attivo" if e["toggle"] == 1 else "disattivato")
    if e.get("range") is not None:
        stato.append(f"valore {e['range']:g}")
    if e.get("selezionato"):
        stato.append("selezionato")
    s = f"{tipo} «{nome}»"
    if stato:
        s += f" ({', '.join(stato)})"
    ctx = _contesto(e)
    if ctx and normalizza(ctx) != normalizza(nome):
        s += f" in «{ctx[:50]}»"
    return s


def pulisci_etichetta(s):
    """Variante v2: toglie le parole che ingannano il modello. Nella barra delle applicazioni
    «bloccato» vuol dire «aggiunto alla barra» (pinned), non «bloccato»."""
    s = re.sub(r" - (\d+) finestr[ae] in esecuzione", r" (aperto)", s)
    s = re.sub(r"\s+bloccato»", "»", s)
    return s


def azionabili(elementi):
    """Visibili, abilitati, con nome e con un'azione possibile; senza doppioni."""
    per_id = {e["id"]: e for e in elementi}
    out, visti, gruppi = [], {}, set()
    for e in elementi:
        if not (e["abilitato"] and e["visibile"] and e["nome"].strip()):
            continue
        if e["tipo"] in TIPI_SCARTATI:
            continue
        pat = set(e["pattern"])
        ok = bool(pat & AZIONI) or bool(e.get("legacy_azione")) or \
            ("Value" in pat and e["tipo"] in TIPI_TESTO)
        if not ok:
            continue
        # colonne dei file in Esplora file: «Nome», «Tipo»… figli di ogni voce
        genitore = e["percorso"][-1].split(":")[0] if e["percorso"] else ""
        if e["tipo"] == "EditControl" and genitore in ("ListItem", "Group") and                 e["nome"] in COLONNE:
            continue
        if genitore == "ScrollBar":
            continue
        # gruppi dentro una voce (VS Code: il percorso completo del file) e gruppi ripetuti
        if e["tipo"] == "GroupControl" and (genitore in ("TreeItem", "ListItem", "Button")
                                            or normalizza(e["nome"]) in gruppi):
            continue
        if e["tipo"] == "GroupControl":
            gruppi.add(normalizza(e["nome"]))
        chiave = (normalizza(e["nome"]), _contesto(e))
        if chiave in visti:
            prec = visti[chiave]
            # a parità di nome si tiene il pulsante, non il gruppo che lo contiene
            if prec["tipo"] == "GroupControl" and e["tipo"] != "GroupControl":
                out[out.index(prec)] = e
                visti[chiave] = e
            continue
        visti[chiave] = e
        out.append(e)
    _ = per_id
    return out


# --- elementi sempre inclusi e glossario (variante «v2») ------------------------------
# I comandi della finestra valgono per quasi ogni app: li si tiene sempre tra i candidati.
FISSI = ("chiudi", "close", "riduci a icona", "minimize", "ingrandisci", "maximize",
         "ripristin", "restore", "indietro", "back", "fino a")

# Glossario voce → interfaccia: sinonimi italiani e termini delle app in inglese.
# Scritto DOPO aver visto i mancati del filtro v1: i numeri della v2 sono ottimistici.
GLOSSARIO = {
    "chiudi": "close", "cerca": "search find", "cercare": "search find", "apri": "open",
    "impostazioni": "settings", "estensioni": "extensions", "terminale": "terminal",
    "muto": "disattiva audio mute", "silenzia": "disattiva audio mute",
    "nascondi": "hide toggle", "mostra": "show", "indietro": "back", "avanti": "forward",
    "salva": "save file", "nuovo": "new", "nuova": "new", "scheda": "tab", "finestra": "window",
    "laterale": "side bar", "modifiche": "changes source control", "ingrandisci": "maximize",
    "riduci": "minimize", "sopra": "fino a su", "superiore": "fino a su", "volume": "audio",
    "file": "files explorer", "progetto": "files", "commit": "source control",
    "posta": "outlook mail", "browser": "edge", "wifi": "rete internet",
}


def espandi(scopo):
    extra = [GLOSSARIO[w] for w in parole(scopo) if w in GLOSSARIO]
    return scopo + (" " + " ".join(extra) if extra else "")


def fisso(e):
    n = normalizza(e["nome"])
    return any(n == f or n.startswith(f + " ") or n.startswith(f) and f == "fino a"
               or (f == "ripristin" and n.startswith(f)) for f in FISSI)


# --- pertinenza lessicale -------------------------------------------------------------

def _sim(a, b):
    if a == b:
        return 1.0
    n = min(len(a), len(b))
    if n >= 4 and a[:4] == b[:4]:  # radice comune: scura/scuro, collega/collegamento
        return 0.8
    r = SequenceMatcher(None, a, b).ratio()
    return r if r >= 0.75 else 0.0


def punteggio_lessicale(scopo, testo):
    q = parole(scopo)
    t = parole(testo)
    if not q or not t:
        return 0.0
    tot = sum(max(_sim(w, x) for x in t) for w in q)
    return tot / math.sqrt(len(q))


# --- embedding leggero su CPU (multilingual-e5-small) ---------------------------------

class Embedder:
    def __init__(self, nome="intfloat/multilingual-e5-small"):
        import torch
        from transformers import AutoModel, AutoTokenizer
        torch.set_num_threads(8)
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(nome)
        self.mod = AutoModel.from_pretrained(nome).eval()

    def __call__(self, testi):
        t = self.torch
        with t.inference_mode():
            b = self.tok(testi, padding=True, truncation=True, max_length=64,
                         return_tensors="pt")
            h = self.mod(**b).last_hidden_state
            m = b["attention_mask"].unsqueeze(-1).float()
            v = (h * m).sum(1) / m.sum(1)
            return t.nn.functional.normalize(v, dim=-1)


@lru_cache(maxsize=None)
def _embedder():
    return Embedder()


class Schermata:
    """Una schermata letta: candidati azionabili, etichette, embedding in cache."""

    def __init__(self, nome, con_embedding=True):
        self.nome = nome
        d = carica(nome)
        self.titolo = d["titolo"]
        self.programma = d["programma"]
        self.elementi = d["elementi"]
        t = time.perf_counter()
        self.candidati = azionabili(self.elementi)
        self.etichette = [etichetta(e) for e in self.candidati]
        self.ms_filtro = (time.perf_counter() - t) * 1000
        self.emb = None
        self.ms_emb_schermata = 0.0
        if con_embedding:
            t = time.perf_counter()
            self.emb = _embedder()(["passage: " + s for s in self.etichette])
            self.ms_emb_schermata = (time.perf_counter() - t) * 1000

    def ordina(self, scopo, modo="misto", peso_lex=0.35, v2=False, k=20):
        """Restituisce [(indice candidato, punteggio)], dal più pertinente; e i ms spesi.

        v2: glossario sulla parte lessicale e comandi della finestra sempre nei primi k."""
        t = time.perf_counter()
        scopo_lex = espandi(scopo) if v2 else scopo
        lex = [punteggio_lessicale(scopo_lex, s) for s in self.etichette]
        if modo == "lessicale" or self.emb is None:
            pun = lex
        else:
            q = _embedder()(["query: " + scopo])
            cos = (self.emb @ q[0]).tolist()
            pun = cos if modo == "embedding" else [c + peso_lex * l for c, l in zip(cos, lex)]
        ordine = sorted(range(len(pun)), key=lambda i: -pun[i])
        if v2:
            fissi = [i for i in ordine if fisso(self.candidati[i])]
            altri = [i for i in ordine if i not in fissi]
            testa = altri[:max(0, k - len(fissi))]
            ordine = testa + fissi + [i for i in altri if i not in testa]
        return [(i, pun[i]) for i in ordine], (time.perf_counter() - t) * 1000


if __name__ == "__main__":
    import sys
    for f in sorted(ALBERI.glob("*.json")):
        s = Schermata(f.stem, con_embedding=False)
        print(f"## {f.stem}: {len(s.elementi)} elementi, {len(s.candidati)} candidati, "
              f"filtro {s.ms_filtro:.1f} ms")
        if len(sys.argv) > 1:
            for e, lab in zip(s.candidati, s.etichette):
                print(f"  {e['id']:>4} {lab}")
