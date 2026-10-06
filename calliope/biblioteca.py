"""
Biblioteca offline di Calliope: Wikipedia italiana in file ZIM di Kiwix, letti in puro
Python (calliope/zim.py) con un indice SQLite FTS5 accanto (calliope/biblioteca_indice.py).

Serve alle domande sui fatti (date, numeri, persone, luoghi, definizioni), dove un
modello da 4B inventa. Interfaccia minima e sostituibile (principio 2):

    Biblioteca(cfg).cerca(domanda, k=3) → [Passaggio(testo, titolo, fonte, punteggio)]

Pipeline (docs/ricerche/2026-09-21-biblioteca-offline.md, §4; misure in
docs/ricerche/2026-09-26-biblioteca-prova.md):
  1. parole chiave: la domanda parlata senza stopword e parole di richiesta;
  2. voci candidate: suggerimenti sui titoli (l'entità della domanda, «Monte Bianco»)
     più la ricerca full-text nell'indice FTS5, che è in AND: se non trova nulla si
     riprova togliendo una parola alla volta;
  3. lettura delle voci nel file «mini» (introduzione + infobox: il fatto è quasi
     sempre lì) e, se nel mini non c'è niente di convincente, nel file completo;
  4. i paragrafi e le righe dell'infobox si ordinano per parole chiave in comune
     (più peso alle parole rare e al titolo), e si tagliano attorno alle frasi utili.
Tutto su CPU in poche decine di millisecondi. Fino al 01/10/2026 i file si leggevano con
libzim (con Xapian), che non ha wheel per Windows su ARM: ora solo libreria standard
(docs/ricerche/2026-10-01-biblioteca-senza-libzim.md). Se libzim è installata non si usa.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

# Parole senza contenuto nelle domande dette a voce: si tolgono prima della ricerca
# (la ricerca full-text è in AND: una parola che non compare azzera i risultati)
_STOP = set("""
a ad al allo alla ai agli alle anche avere ha hanno ho hai c ci che chi cosa come con
contro cui da dal dallo dalla dai dagli dalle del dello della dei degli delle di dove
e ed è era erano essere fa fanno fu furono gli ha i il in io l la le lei lo loro lui ma
me mi mia mio ne negli nei nel nello nella nelle no noi non o per perché più poi qual
quale quali quando quanto quanta quanti quante quello quella questo questa se si sia
sono su sul sullo sulla sui sugli sulle ti tra fra tu tua tuo un una uno vi voi
dimmi dirmi sai sapresti puoi potresti vorrei voglio mi spieghi spiegami raccontami
dici calliope senti ciao grazie per favore esattamente circa proprio ancora già
dell dall nell sull all coll quest quell cos cosè d un
funziona funzionano succede spiega spieghi fatto fatta fatti serve servono
parlami parlarmi parla parlare raccontare spiegare
""".split())
# Parole che dicono COSA si cerca, non DI CHI («simbolo chimico del sodio»: l'entità è
# «sodio»). Restano utili sui paragrafi («alto» → «altezza») ma non per scegliere la voce.
# Alcune richiamano più etichette delle infobox: «dista» → «Semiasse maggiore: 384400 km»
# della Luna; «grande» → «Superficie totale».
_DATA_HINTS = {
    "alto": ("altezza", "altitudine", "elevata"), "alta": ("altezza", "altitudine", "elevata"),
    "altezza": ("altezza", "altitudine"), "lungo": "lunghezza",
    "lunga": "lunghezza", "lunghezza": "lunghezza", "grande": ("superficie", "area"),
    "superficie": "superficie", "profondo": "profondità", "abitanti": ("abitanti", "popolazione"),
    "popolazione": ("abitanti", "popolazione"), "nato": ("nato", "nascita"), "nata": ("nata", "nascita"), "nascita": ("nato", "nascita"),
    "morto": ("morto", "morte"), "morta": ("morta", "morte"), "morte": ("morto", "morte"), "capitale": "capitale",
    "anno": "anno", "data": "data", "quando": "anno", "simbolo": "simbolo",
    "chimico": "chimico", "formula": "formula", "scoperto": "scoperto",
    "scoperta": "scoperta", "scoprì": "scoperto", "inventato": "inventato",
    "inventore": "inventato", "scritto": "scritto", "autore": "scritto", "fondato": ("fondato", "fondazione"),
    "fondata": ("fondata", "fondazione"), "costruito": "costruito", "dipinto": "dipinto", "distanza": ("distanza", "semiasse", "perigeo"),
    "dista": ("distanza", "semiasse", "perigeo"), "peso": "peso", "pesa": "peso", "massa": "massa", "significa": "significato",
    "significato": "significato", "definizione": "definizione", "lingua": "lingua",
    "moneta": "valuta", "valuta": "valuta", "temperatura": "temperatura", "velocità": "velocità",
    "presidente": "presidente", "sindaco": "sindaco", "regione": "regione",
}


# Fonti in più chiamate solo da un tipo di domanda (catalogo.Fonte.richiesta, 01/10):
# Wikiquote per «una citazione di Einstein», «chi ha detto "…"?», «un proverbio sul…»
RICHIESTE = {
    "citazioni": re.compile(
        r"\b(citazion[ei]|aforism[aio]|frase (?:famosa|celebre|di)|frasi (?:famose|celebri|di)"
        r"|chi (?:ha detto|disse|diceva|l'ha detto)|chi è che (?:ha detto|diceva)"
        r"|detto (?:famoso|celebre)|massim[ae] (?:di|famos[ae]|celebr[ei])|proverbi[oa]?)\b",
        re.I),
}
# Vantaggio dei passaggi della fonte chiamata (come Vikidia per le spiegazioni semplici):
# a «una citazione di Einstein» risponde Wikiquote, non la biografia di Wikipedia
_RICHIESTA_VANTAGGIO = 5.0
# Righe di Wikiquote che non sono citazioni: fonti bibliografiche (con il nome dell'autore,
# vincevano su «una citazione di Einstein»: 01/10) e rimandi agli altri progetti
_NON_CITAZIONE = re.compile(
    r"^\[[^\]]*\]$|\btraduzione di\b|\ba cura di\b|\braccolt[ie] da\b|\bISBN\b"
    r"|\bWikipedia contiene\b|, (?:1[5-9]|20)\d\d\.?$"
    r"|\bCommons contiene\b|\bWikisource contiene\b|\bpp?\. \d"
    r"|\b(?:Editore|Editori|Mondadori|Einaudi|"
    r"Feltrinelli|Rizzoli|Garzanti|Newton Compton|Laterza|Bompiani|Adelphi|BUR|UTET|Sansoni|"
    r"Le Monnier|Zanichelli)\b[^.]*\b1[5-9]\d\d|\b(?:Editore|Editori|Mondadori|Einaudi|"
    r"Feltrinelli|Rizzoli|Garzanti|Newton Compton|Laterza|Bompiani|Adelphi|BUR|UTET)\b[^.]*"
    r"\b20\d\d", re.I)
# Attribuzione in fondo alla citazione: «… (Jules Renard)». Sulla voce di un autore è una
# frase su di lui, detta da un altro
_ATTRIBUZIONE = re.compile(r"\((?:[A-ZÀ-Ý][\w'.-]*\s?){1,5}\)\s*$")
# Parole della richiesta, da togliere dalla ricerca: dicono che cosa si vuole, non di chi
_RICHIESTA_PAROLE = {"citazioni": set("""citazione citazioni aforisma aforismi frase frasi
famosa famose celebre celebri detto disse diceva massima massime""".split())}


@dataclass
class Passaggio:
    testo: str
    titolo: str
    fonte: str          # «Wikipedia», «Vikidia»…
    punteggio: float
    # Da dove viene (file ZIM e percorso della voce): per il testo più lungo da mostrare su
    # uno schermo (Biblioteca.testo_voce). Vuoti per definizioni e significati.
    archivio: str = ""
    percorso: str = ""


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'")
    return re.sub(r"[^\w\s']", " ", text)


def _stem(word: str) -> str:
    """Radice rozza per il confronto lessicale: via le vocali finali, così «vulcani» e
    «vulcano», «caduto» e «caduta» coincidono (non serve uno stemmer vero)."""
    if word.isdigit():
        return word
    s = word.rstrip("aeiouàèéìòù")
    if s.endswith(("ch", "gh")):
        s = s[:-1]                  # laghi/lago, parchi/parco
    return (s if len(s) >= 3 else word)[:9]


def keywords(domanda: str) -> list[str]:
    """Parole chiave della domanda, nell'ordine, senza stopword né doppioni."""
    words = []
    for w in _norm(domanda).replace("'", " ").split():
        if w not in _STOP and (len(w) > 1 or w.isdigit()) and w not in words:
            words.append(w)
    return words


# Parole che non cambiano il soggetto della domanda (Biblioteca.opzioni): quelle di attributo
# (_DATA_HINTS) e quelle di richiesta («parlami di…», «dimmi qualcosa su…»)
_NOT_SUBJECT = {_stem(w) for w in list(_DATA_HINTS) + """parlami dimmi raccontami spiegami
spiega qualcosa cosa vuol dire significa significato definizione intende intendi""".split()}


class _TextExtractor(HTMLParser):
    """Testo pulito di una voce: paragrafi, voci di elenco e righe dell'infobox."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.infobox: list[str] = []
        self._buf: list[str] = []
        self._in_p = 0
        self._skip_tag: str | None = None   # tag che si sta saltando (note, script…)
        self._skip = 0                      # profondità dentro quel tag
        self._table = 0                     # profondità nelle tabelle
        self._infobox = False
        self._cell: list[str] | None = None
        self._row: list[str] = []
        self._group = ""                    # intestazione di sezione dell'infobox

    def handle_starttag(self, tag, attrs):
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip += 1
            return
        cls = dict(attrs).get("class", "") or ""
        void = tag in ("img", "br", "hr", "meta", "link", "input", "wbr", "source")
        if not void and (tag in ("script", "style", "sup") or "reference" in cls
                         or "noprint" in cls or "mw-editsection" in cls):
            self._skip_tag, self._skip = tag, 1
            return
        if tag == "table":
            self._table += 1
            if "infobox" in cls or "sinottico" in cls:
                self._infobox = True
        elif tag == "tr" and self._infobox:
            self._row = []
        elif tag in ("th", "td") and self._infobox:
            self._cell = []
        elif tag in ("p", "li") and not self._table:
            self._in_p += 1
            self._buf = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(", ")

    def handle_endtag(self, tag):
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip -= 1
                if not self._skip:
                    self._skip_tag = None
            return
        if tag == "table" and self._table:
            self._table -= 1
            if not self._table:
                self._infobox = False
        elif tag in ("th", "td") and self._cell is not None:
            cell = re.sub(r"\s+", " ", "".join(self._cell)).strip(" ,")
            if cell:
                self._row.append(cell)
            self._cell = None
        elif tag == "tr" and self._infobox:
            if len(self._row) == 2 and len(self._row[1]) < 200:
                key = self._row[0]
                # «Totale: 302 069 km²» sotto l'intestazione «Superficie»: senza
                # l'intestazione la riga non dice di che cosa è il totale
                if self._group and key.lower() in ("totale", "densità", "massima", "minima",
                                                   "media", "fonte", "foce", "nome", "data"):
                    key = f"{self._group} {key.lower()}"
                self.infobox.append(f"{key}: {self._row[1]}")
            elif len(self._row) == 1 and len(self._row[0]) < 40:
                self._group = self._row[0]           # intestazione di sezione
            self._row = []
        elif tag in ("p", "li") and self._in_p:
            self._in_p -= 1
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if len(text) > 40:
                self.paragraphs.append(text)
            self._buf = []

    def handle_data(self, data):
        if self._skip_tag:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._in_p:
            self._buf.append(data)


def _plurals(word: str) -> list[str]:
    """Plurali probabili di un nome o aggettivo italiano (lago → laghi, montagna →
    montagne, fiume → fiumi, alta → alte); si prova quello che esiste come titolo."""
    w = word.lower()
    out = []
    if w.endswith(("co", "go")):
        out += [w[:-1] + "hi", w[:-1] + "i"]
    elif w.endswith(("ca", "ga")):
        out += [w[:-1] + "he"]
    elif w.endswith("o") or w.endswith("e"):
        out += [w[:-1] + "i"]
    elif w.endswith("a"):
        out += [w[:-1] + "e", w[:-1] + "i"]
    return out + [w]


def extract(html_text: str) -> tuple[list[str], list[str]]:
    """(paragrafi, righe dell'infobox) di una voce ZIM."""
    body = html_text[html_text.find("<body"):]
    p = _TextExtractor()
    try:
        p.feed(body)
    except Exception:
        pass
    return p.paragraphs, p.infobox


# ─────────────────────────────── WIKIZIONARIO ───────────────────────────────
# Le definizioni stanno in elenchi numerati (<ol><li>) sotto la parte del discorso
# (Aggettivo, Sostantivo, Verbo…) della sezione «Italiano»; sinonimi e contrari in
# sezioni proprie. L'estrattore di Wikipedia legge solo i paragrafi: ne serve uno suo.

_DEF_QUESTION = [
    r"(?:cosa|che cosa|che)\s+(?:significa|vuol\s+dire|vuole\s+dire)\s+(?:la\s+parola\s+)?[«\"']?(?P<w>[\wàèéìòù'-]+)",
    r"[«\"']?(?P<w>[\wàèéìòù'-]+)[»\"']?\s+(?:cosa|che cosa|che)\s+(?:significa|vuol\s+dire)",
    r"significato\s+(?:della\s+parola\s+|di\s+|del\s+|dello\s+|della\s+|dell'\s*)[«\"']?(?P<w>[\wàèéìòù'-]+)",
    r"definizione\s+(?:della\s+parola\s+|di\s+|del\s+|della\s+|dell'\s*)[«\"']?(?P<w>[\wàèéìòù'-]+)",
    r"(?P<kind>sinonim[oi]|contrari[oi])\s+(?:di\s+|del\s+|della\s+|dell'\s*)[«\"']?(?P<w>[\wàèéìòù'-]+)",
    # «Cos'è un'iperbole?»: il dizionario dà la definizione, Wikipedia aggiunge il resto
    # (la voce «Iperbole» di Wikipedia è una disambiguazione, 26/09)
    r"^\W*(?:cos'è|cosa è|che cos'è|cos'e)\s+(?P<kind>un'|una |un |uno |il |lo |la |l'|i |gli |le )\s*(?P<w>[\wàèéìòù-]+)\W*$",
]


def definition_word(domanda: str) -> tuple[str, str] | None:
    """(parola, tipo) se la domanda chiede un significato, un sinonimo o un contrario:
    «cosa significa effimero?» → ("effimero", "significato")."""
    q = domanda.lower().replace("’", "'")
    for pattern in _DEF_QUESTION:
        m = re.search(pattern, q)
        if m and m.group("w") not in _STOP:
            kind = (m.groupdict().get("kind") or "significato").strip()
            kind = "sinonimi" if kind.startswith("sinonim") else (
                "contrari" if kind.startswith("contrari") else (
                    "significato" if kind == "significato" else "cosè"))
            return m.group("w").strip("'-"), kind
    return None


class _WiktionaryExtractor(HTMLParser):
    """Definizioni (per parte del discorso), sinonimi e contrari della sezione Italiano."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.italian = False
        self.heading: str | None = None     # "h2"/"h3" mentre se ne legge il titolo
        self.section = ""                   # ultima intestazione h3 (Aggettivo, Sinonimi…)
        self.head_text = ""
        self.list_depth = 0                 # profondità di ol/ul
        self.li_depth = 0
        self.skip = 0                       # dentro dl/ul annidati (esempi) o sup
        self.buf = ""
        self.defs: list[tuple[str, list[str]]] = []
        self.synonyms: list[str] = []
        self.antonyms: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "h4"):
            self.heading, self.head_text = tag, ""
        elif not self.italian:
            return
        elif tag in ("ol", "ul"):
            self.list_depth += 1
            if self.li_depth:               # elenco dentro una definizione: esempi
                self.skip += 1
        elif tag == "li":
            self.li_depth += 1
            if self.li_depth == 1:
                self.buf = ""
        elif tag in ("dl", "sup", "table"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag == self.heading:
            text = re.sub(r"\s+", " ", self.head_text).strip()
            if tag == "h2":
                self.italian = text.lower().startswith("italiano")
            elif self.italian:
                self.section = text
            self.heading = None
            return
        if not self.italian:
            return
        if tag in ("ol", "ul"):
            self.list_depth = max(0, self.list_depth - 1)
            if self.li_depth:
                self.skip = max(0, self.skip - 1)
        elif tag in ("dl", "sup", "table"):
            self.skip = max(0, self.skip - 1)
        elif tag == "li":
            if self.li_depth == 1:
                text = re.sub(r"\s+", " ", html.unescape(self.buf)).strip(" ;,")
                sec = self.section.lower()
                if text:
                    if sec.startswith("sinonim"):
                        self.synonyms += [t.strip() for t in re.split(r"[,;]", text) if t.strip()]
                    elif sec.startswith("contrar"):
                        self.antonyms += [t.strip() for t in re.split(r"[,;]", text) if t.strip()]
                    elif sec and not sec.startswith(("pronuncia", "etimologia", "citazion",
                                                     "parole derivate", "termini correlati",
                                                     "varianti", "alterati", "proverbi",
                                                     "traduzione", "note", "sillabazione",
                                                     "iponimi", "iperonimi", "meronimi",
                                                     "olonimi", "locuzioni")):
                        if not self.defs or self.defs[-1][0] != self.section:
                            self.defs.append((self.section, []))
                        self.defs[-1][1].append(text)
            self.li_depth = max(0, self.li_depth - 1)

    def handle_data(self, data):
        if self.heading:
            self.head_text += data
        elif self.italian and self.li_depth and not self.skip:
            self.buf += data


def _clean_definition(d: str) -> str | None:
    """Via le etichette iniziali («(filosofia) (psicologia)»: a voce non servono) e le
    righe di servizio («casa (approfondimento) f sing»)."""
    if re.search(r"\b(approfondimento|citazioni)\b|\b[mf] (sing|pl)\b", d):
        return None
    d = re.sub(r"^(\([^)]*\)\s*)+", "", d).strip(" .;")
    return d if len(d) >= 8 else None


def _clean_words(items: list[str]) -> list[str]:
    """Sinonimi e contrari: solo parole o espressioni brevi, senza note tra parentesi."""
    out = []
    for it in items:
        it = re.sub(r"\([^)]*\)?", "", it).strip(" .:")
        if it and ":" not in it and len(it.split()) <= 3 and it not in out:
            out.append(it)
    return out


def extract_definitions(html_text: str):
    """(definizioni per parte del discorso, sinonimi, contrari) di una voce, puliti."""
    p = _WiktionaryExtractor()
    p.feed(html_text)
    defs = []
    for pos, items in p.defs:
        clean = [c for c in (_clean_definition(i) for i in items) if c]
        if clean:
            defs.append((pos, clean))
    return defs, _clean_words(p.synonyms), _clean_words(p.antonyms)


class _Archivio:
    """Un file ZIM aperto una volta sola (calliope/zim.py, puro Python), con la ricerca
    full-text e sui titoli nel suo indice SQLite FTS5 (calliope/biblioteca_indice.py).
    Senza indice (Wikipedia completa, Wikizionario, o indice non ancora pronto) si legge
    per percorso e per titolo; la ricerca full-text è vuota e i suggerimenti ripiegano sui
    titoli che cominciano con la domanda, come libzim senza Xapian."""

    def __init__(self, path: str, fonte: str, peso_titolo: float = 1.0):
        from . import biblioteca_indice
        from .zim import ZimFile
        self.path, self.fonte = path, fonte
        self.archive = ZimFile(path)
        self.indice = biblioteca_indice.apri(path)
        self.peso_titolo = peso_titolo
        self._titolo = biblioteca_indice.parole_titolo
        self._cache: dict[str, tuple[str, list[str], list[str]]] = {}

    def close(self):
        if self.indice is not None:
            self.indice.close()
        self.archive.close()

    def fulltext(self, words: list[str], n: int) -> list[str]:
        """Percorsi delle voci con tutte le parole (radici), per bm25; se non trova nulla
        toglie una parola alla volta, la più corta (spesso la meno informativa)."""
        if self.indice is None or not words:
            return []
        out = []
        for rowid in self.indice.fulltext(words, n, self.peso_titolo):
            try:
                out.append(self.archive.dirent(rowid).path)
            except Exception:  # noqa: BLE001 — indice e file non allineati: si salta
                continue
        return out

    def suggest(self, q: str, n: int = 3) -> list[str]:
        """Come i suggerimenti di libzim: titoli con tutte le parole (l'ultima come
        prefisso); prima il titolo identico, poi quello che comincia con la domanda, poi
        bm25 e i titoli più corti."""
        if self.indice is None:
            q = q.strip()
            return [e.path for e in self.archive.titles_with_prefix(q[:1].upper() + q[1:], n)]
        rows = self.indice.titoli(q, 30)
        want = self._titolo(q)
        scored = []
        for rowid, score in rows:
            try:
                d = self.archive.dirent(rowid)
            except Exception:  # noqa: BLE001
                continue
            t = self._titolo(d.shown_title)
            scored.append(((t != want, not t.startswith(want), score, len(t)), d.path))
        scored.sort()
        return [p for _, p in scored[:n]]

    def titles(self, words: list[str], n: int) -> list[str]:
        """Voci il cui titolo corrisponde alle parole della domanda («monte bianco»)."""
        out = []
        for size in (len(words), 3, 2, 1):
            if size < 1 or size > len(words):
                continue
            for i in range(len(words) - size + 1):
                q = " ".join(words[i:i + size])
                for path in self.suggest(q, 3):
                    if path not in out:
                        out.append(path)
                if len(out) >= n:
                    return out
        return out

    def exact(self, domanda: str) -> list[str]:
        """Voci il cui titolo è un pezzo della domanda: «il Po», «del sodio», «muro di
        Berlino». Con i soli suggerimenti «Po» si perdeva tra centinaia di titoli."""
        words = _norm(domanda).replace("'", " ").split()
        with_entity, only_hints = [], []
        for size in (4, 3, 2, 1):
            for i in range(len(words) - size + 1):
                span = words[i:i + size]
                # niente pezzi che iniziano o finiscono con una parola vuota
                if span[0] in _STOP or span[-1] in _STOP:
                    continue
                content = [w for w in span if w not in _STOP]
                # «Velocità della luce» sì (c'è un'entità); «Simbolo chimico» in coda,
                # dopo «Sodio», perché è fatto solo di parole di attributo
                target = only_hints if all(w in _DATA_HINTS for w in content) else with_entity
                text = " ".join(span)
                for title in (text[:1].upper() + text[1:], text.title()):
                    path = title.replace(" ", "_")
                    if path not in with_entity + only_hints and self.archive.has_entry_by_path(path):
                        target.append(path)
                        break
        return with_entity + only_hints

    def superlative(self, domanda: str) -> list[str]:
        """Voci-elenco per i superlativi: «il lago più grande d'Italia» → «Laghi d'Italia»,
        «il fiume più lungo del mondo» → «Fiumi più lunghi del mondo». Il primato sta
        lì, non nella voce di un lago qualunque."""
        m = re.search(r"\b(\w+)\s+(?:più|meno)\s+(\w+)(?:\s+(?:d'|del|della|dell'|dei|in)\s*(\w+))?",
                      domanda.lower().replace("’", "'"))
        if not m:
            return []
        noun, adj, where = m.group(1), m.group(2), m.group(3)
        nouns, adjs = _plurals(noun), _plurals(adj)
        titles = []
        for n in nouns:
            n = n[:1].upper() + n[1:]
            if where in ("italia",):
                titles += [f"{n} d'Italia", f"{n} italiani", f"{n} italiane"]
            if where in ("mondo", "terra"):
                titles += [f"{n} del mondo"]
            for a in adjs:
                titles += [f"{n} più {a} del mondo", f"{n} più {a} d'Italia", f"{n} più {a}"]
        return [t.replace(" ", "_") for t in dict.fromkeys(titles)
                if self.archive.has_entry_by_path(t.replace(" ", "_"))]

    def disambiguation(self, path: str) -> list[tuple[str, str]]:
        """Se la voce `path` è una pagina di disambiguazione, i suoi significati:
        [(descrizione, voce collegata)], nell'ordine della pagina. Altrimenti []."""
        try:
            entry = self.archive.get_entry_by_path(path)
            hops = 0
            while entry.is_redirect and hops < 5:
                entry, hops = entry.get_redirect_entry(), hops + 1
            raw = bytes(entry.get_item().content).decode("utf-8", "replace")
        except Exception:
            return []
        # Wikipedia marca le disambiguazioni: <meta property="mw:PageProp/disambiguation">
        if "mw:PageProp/disambiguation" not in raw:
            return []
        # Via gli stili del riquadro «avviso-disambigua»: finivano dentro il primo <li> e
        # si perdeva il primo significato («Iperbole – in geometria…», 26/09)
        raw = re.sub(r"<(style|script)\b.*?</\1>", "", raw, flags=re.S)
        items, seen = [], set()
        # \b: senza, «<li» prendeva anche i «<link» dell'intestazione e il primo
        # significato finiva inghiottito
        for li in re.findall(r"<li\b[^>]*>(.*?)</li>", raw, re.S):
            li = re.split(r"<(?:ul|ol)\b", li)[0]      # via i sotto-elenchi («Venere ericina…»)
            link = re.search(r'href="([^"#?]+)"', li)
            text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", li))).strip()
            m = re.match(r"^(.{1,60}?)\s+[–—-]\s+(.+)$", text)     # anche con spazi speciali
            if m and link:
                target = unquote(link.group(1)).replace(" ", "_").lstrip("./")
                if target not in seen:                  # «in astrologia» e «pianeta» → Venere
                    seen.add(target)
                    items.append((m.group(2).strip(), target))
        return items if len(items) >= 2 else []


    def read(self, path: str) -> tuple[str, list[str], list[str]] | None:
        """(titolo, paragrafi, infobox) della voce, seguendo i redirect."""
        if path in self._cache:
            return self._cache[path]
        try:
            entry = self.archive.get_entry_by_path(path)
            hops = 0
            while entry.is_redirect and hops < 5:
                entry, hops = entry.get_redirect_entry(), hops + 1
            item = entry.get_item()
            if not item.mimetype.startswith("text/html"):
                return None
            paragraphs, infobox = extract(bytes(item.content).decode("utf-8", "replace"))
            # Pagina di disambiguazione («Vulcano (vulcano) – …», «Isola di Vulcano – …»):
            # un elenco di rimandi, non una spiegazione. Il 26/09 su Vikidia «come funziona
            # un vulcano?» rispondeva con quell'elenco.
            listing = sum(1 for p in paragraphs if re.match(r"^[^.]{1,80} – ", p))
            if "disambigua" in path.lower() or (paragraphs and listing >= max(2, len(paragraphs) // 2)):
                out = None
            else:
                out = (entry.title, paragraphs, infobox)
        except Exception:
            out = None
        if len(self._cache) > 500:
            self._cache.clear()
        self._cache[path] = out
        return out


class Biblioteca:
    def __init__(self, cfg):
        self.cfg = cfg
        self.archivi: list[_Archivio] = []
        self.completa: _Archivio | None = None
        # Fonti in più, usate solo quando servono: Vikidia (enciclopedia per ragazzi) per
        # le spiegazioni semplici, il Wikizionario per significati, sinonimi e contrari
        self.ragazzi: _Archivio | None = None
        self.dizionario: _Archivio | None = None
        t0 = time.perf_counter()
        # Il file verificato più recente della stessa famiglia vince su quello scritto in
        # calliope.yaml: un aggiornamento a voce si attiva senza toccare la configurazione
        from .installa.catalogo import risolvi_zim
        for path, fonte, ruolo in ((risolvi_zim(cfg.biblioteca_mini), "Wikipedia", "mini"),
                                   (risolvi_zim(cfg.biblioteca_completa), "Wikipedia", "completa"),
                                   (risolvi_zim(cfg.biblioteca_ragazzi), "Vikidia", "ragazzi"),
                                   (risolvi_zim(cfg.biblioteca_dizionario), "Wikizionario",
                                    "dizionario")):
            if not path or not Path(path).exists():
                continue
            try:
                a = _Archivio(path, fonte, float(getattr(cfg, "biblioteca_peso_titolo", 1.0)))
            except Exception as e:
                print(f"[BIBLIOTECA] non riesco ad aprire {path}: {e}")
                continue
            if ruolo == "completa":
                self.completa = a
            elif ruolo == "ragazzi":
                self.ragazzi = a
            elif ruolo == "dizionario":
                self.dizionario = a
            else:
                self.archivi.append(a)
        if not self.archivi and self.completa:
            self.archivi.append(self.completa)     # c'è solo il file completo
        # Fonti in più (Config.biblioteca_fonti_extra), ciascuna con il suo indice e usata
        # solo per il suo tipo di domanda: senza indice non si aprono (le cercheremmo male)
        self.extra: list[tuple[_Archivio, str]] = []
        from .biblioteca_indice import pronto
        from .installa.catalogo import fonti_usate
        for fonte, path in fonti_usate(cfg):
            if not pronto(path):
                continue
            try:
                self.extra.append((_Archivio(str(path), fonte.titolo.split(",")[0],
                                             float(getattr(cfg, "biblioteca_peso_titolo",
                                                           1.0))), fonte.richiesta))
            except Exception as e:
                print(f"[BIBLIOTECA] non riesco ad aprire {path}: {e}")
        self.open_ms = (time.perf_counter() - t0) * 1000

    def richieste(self, domanda: str) -> set[str]:
        """I tipi di domanda delle fonti in più aperte che la domanda chiama
        («una citazione di…» → {"citazioni"})."""
        kinds = {k for _, k in self.extra}
        return {k for k in kinds if k in RICHIESTE and RICHIESTE[k].search(domanda)}

    @property
    def citazioni(self) -> bool:
        """C'è Wikiquote: il tool lo dice nella descrizione."""
        return any(k == "citazioni" for _, k in self.extra)

    @property
    def disponibile(self) -> bool:
        return bool(self.archivi)

    def _tutti(self) -> list[_Archivio]:
        out = list(self.archivi)
        for extra in (self.completa, self.ragazzi, self.dizionario,
                      *(a for a, _ in getattr(self, "extra", ()))):
            if extra and extra not in out:
                out.append(extra)
        return out

    def close(self):
        """Chiude file e indici (su Windows un file aperto non si cancella: la pulizia dopo
        un aggiornamento ha bisogno che la biblioteca vecchia sia chiusa)."""
        for a in self._tutti():
            try:
                a.close()
            except Exception:  # noqa: BLE001
                pass

    def descrizione(self) -> str:
        return ", ".join(Path(a.path).name for a in self._tutti())

    # Significati poco utili da proporre a voce: opere omonime, personaggi di fumetti…
    _MINOR = re.compile(r"\b(film|album|singolo|brano|canzone|brano musicale|personaggio|"
                        r"fumett|videogioco|serie televisiva|episodio|romanzo|rivista|"
                        r"nave|sommergibile|dipinto|scultura|gruppo musicale|cognome|"
                        r"asteroide|stazione|frazione|comune|ghiacciaio|nome proprio|"
                        r"vescovo|satelliti|in astrologia|araldic|spugna|genere di|statua|"
                        r"simbolo planetario|varietà|fregata|corazzata|incrociatore|"
                        r"cacciatorpediniere|area a governo locale)\b", re.I)

    def opzioni(self, domanda: str, max_opzioni: int = 3) -> list[Passaggio]:
        """I significati tra cui scegliere, se la domanda nomina qualcosa che Wikipedia
        stessa considera ambiguo: la sua voce principale è una pagina di disambiguazione
        («Iperbole», «Venere», «Mercurio»). Se invece la voce principale è un articolo
        (Colosseo, Tevere, Vulcano) il significato prevalente esiste e non si chiede nulla:
        quasi ogni nome ha una disambiguazione («Tevere»: fiume, dipartimento, nave…).
        Ogni opzione è un passaggio: descrizione + inizio della voce collegata.
        Vuoto se la domanda contiene già una parola che sceglie il significato
        («l'iperbole in geometria»)."""
        arch = self.completa or (self.archivi[0] if self.archivi else None)
        if arch is None:
            return []
        q_words = {_stem(w) for w in _norm(domanda).replace("'", " ").split()
                   if w not in _STOP and len(w) > 3}
        # Solo l'entità principale della domanda (il pezzo più lungo con un nome): con i
        # pezzi minori «quanto è lungo il Tevere» diventava ambiguo per «Lungo» e
        # «Alessandro Manzoni» per «Alessandro»
        tried: list[set[str]] = []
        for path in arch.exact(domanda)[:3]:
            words = set(_norm(path.replace("_", " ")).split())
            # niente pezzi di un candidato già visto («Alessandro» di «Alessandro Manzoni»)
            # né parole che dicono solo cosa si chiede («Lungo» in «quanto è lungo…»)
            if any(words <= t for t in tried) or all(w in _DATA_HINTS for w in words):
                continue
            tried.append(words)
            # Solo se la domanda è proprio su quel nome («cos'è un'iperbole?», «parlami di
            # Venere», «quanto è grande Venere?»): oltre al nome solo parole di richiesta o
            # di attributo. Il 01/10 il modello riformulava e una parola qualunque della
            # domanda diventava ambigua: «caduta del muro di Berlino» (Muro), «profondità
            # del lago di Garda», «chi ha composto la Traviata», «punto più profondo»,
            # «fine della seconda guerra mondiale» → «la parola ha più significati»
            rest = ({_stem(w) for w in keywords(domanda)} - {_stem(w) for w in words}
                    - _NOT_SUBJECT)
            if rest:
                continue
            items = [(d, t) for d, t in arch.disambiguation(path) if not self._MINOR.search(d)]
            if len(items) < 2:
                continue
            # La domanda sceglie già? (una parola distintiva di una descrizione)
            entity = {_stem(w) for w in _norm(path.replace("_", " ")).split()}
            for desc, _ in items:
                d_words = {_stem(w) for w in _norm(desc).replace("'", " ").split()
                           if w not in _STOP and len(w) > 3} - entity
                if d_words & q_words:
                    return []
            out = []
            for desc, target in items[:max_opzioni]:
                data = arch.read(target) or (self.archivi[0].read(target) if self.archivi else None)
                intro = data[1][0] if data and data[1] else ""
                # Nome breve dell'opzione, da dire a voce: «figura retorica», non la frase intera
                short = re.split(r"[,;(]| in cui | che ", desc)[0].strip()
                short = " ".join(short.split()[:5]) or desc
                out.append(Passaggio(self._trim(intro, {}, 250) if intro else desc,
                                     short, "Wikipedia", 0.0))
            return out
        return []

    def definisci(self, parola: str, kind: str = "significato") -> Passaggio | None:
        """La voce del Wikizionario come passaggio: «effimero (aggettivo): che dura
        solamente un giorno; …». Prova anche la forma minuscola e quella con la
        maiuscola (nomi propri e inizio frase)."""
        if not self.dizionario:
            return None
        arch = self.dizionario.archive
        for path in dict.fromkeys((parola.lower(), parola, parola.capitalize())):
            if not arch.has_entry_by_path(path):
                continue
            try:
                entry = arch.get_entry_by_path(path)
                hops = 0
                while entry.is_redirect and hops < 5:
                    entry, hops = entry.get_redirect_entry(), hops + 1
                defs, syn, ant = extract_definitions(
                    bytes(entry.get_item().content).decode("utf-8", "replace"))
            except Exception:
                continue
            parts = []
            if kind == "sinonimi" and syn:
                parts.append(f"sinonimi di {parola}: {', '.join(syn[:6])}")
            elif kind == "contrari" and ant:
                parts.append(f"contrari di {parola}: {', '.join(ant[:5])}")
            for pos, items in defs[:2]:
                parts.append(f"{parola} ({pos.lower()}): " + "; ".join(items[:2]))
            if kind == "significato" and syn:
                parts.append(f"sinonimi: {', '.join(syn[:4])}")
            if parts:
                text = ". ".join(parts)
                return Passaggio(self._trim(text, {}, self.cfg.biblioteca_max_caratteri),
                                 parola, "Wikizionario", 100.0)
        return None

    # ── punteggi ──
    @staticmethod
    def _score(text: str, stems: dict[str, float], title_stems: set[str]) -> float:
        words = {_stem(w) for w in _norm(text).replace("'", " ").split()}
        score = sum(weight for s, weight in stems.items() if s in words)
        score += 0.5 * sum(1 for s in title_stems if s in words)
        # un numero nel testo aiuta per le domande su date e misure
        if re.search(r"\d", text):
            score += 0.2
        return score

    def _weights(self, words: list[str]) -> dict[str, float]:
        """Peso delle parole chiave: le più lunghe e i numeri sono più informativi."""
        # (Provato il 26/09: far pesare poco la parola generica, «alto», e molto le
        # etichette collegate peggiorava i superlativi, «il fiume più lungo», 49 → 47.)
        out = {}
        for w in words:
            out[_stem(w)] = 1.0 + min(len(w), 10) / 10 + (0.5 if w.isdigit() else 0)
            hint = _DATA_HINTS.get(w)
            for h in ((hint,) if isinstance(hint, str) else hint or ()):
                out.setdefault(_stem(h), 1.0)
        return out

    def _trim(self, text: str, stems: dict[str, float], limit: int) -> str:
        """Taglia un paragrafo lungo tenendo le frasi con più parole chiave."""
        if len(text) <= limit:
            return text
        sentences = re.split(r"(?<=[.;!?])\s+", text)
        ranked = sorted(range(len(sentences)),
                        key=lambda i: (-self._score(sentences[i], stems, set()), i))
        keep, size = set(), 0
        for i in ranked:
            if size + len(sentences[i]) > limit and keep:
                break
            keep.add(i)
            size += len(sentences[i]) + 1
        out = " ".join(sentences[i] for i in sorted(keep))
        return out[:limit].rsplit(" ", 1)[0] + ("…" if len(out) > limit else "")

    def cerca(self, domanda: str, k: int | None = None,
              semplice: bool = False) -> list[Passaggio]:
        """I passaggi più utili per rispondere alla domanda (vuoto se non trova nulla).

        Domande sul significato di una parola («cosa significa effimero?», «sinonimi di
        felice») → la voce del Wikizionario. `semplice` (chi parla è un ragazzo, o ha
        chiesto una spiegazione semplice) → anche Vikidia, con la precedenza.
        """
        cfg = self.cfg
        k = k or cfg.biblioteca_k
        definition = definition_word(domanda)
        lead: list[Passaggio] = []
        if definition:
            word, kind = definition
            p = self.definisci(word, "significato" if kind == "cosè" else kind)
            if p and kind != "cosè":
                return [p]
            if p:                               # «cos'è un X»: definizione + Wikipedia
                lead, k = [p], k - 1
        words = keywords(domanda)
        asked = self.richieste(domanda)          # «una citazione di…»: anche Wikiquote
        for kind in asked:
            words = [w for w in words if w not in _RICHIESTA_PAROLE.get(kind, ())]
        if not words or not self.archivi:
            return lead
        stems = self._weights(words)
        entity = [w for w in words if w not in _DATA_HINTS]
        # «quanto è alto», «quanti abitanti», «in che anno»: si chiede un dato
        asks_data = len(entity) < len(words) or bool(
            re.search(r"\b(quant[oaie]|che anno|quando)\b", domanda.lower()))
        passages: list[Passaggio] = []

        entity_stems = {_stem(w) for w in entity}

        def title_fit(title: str) -> float:
            """Quanto il titolo coincide con l'entità cercata (Jaccard): «Monte Bianco»
            vale 1, «Traforo del Monte Bianco» 2/3, «Università di Milano-Bicocca» per
            «Milano» 1/4. La parte tra parentesi è una disambiguazione e non conta: il
            26/09 «Lago (Italia)», un comune calabrese, vinceva per «il lago più grande
            d'Italia»."""
            title = re.sub(r"\s*\(.*?\)", "", title)
            t = {_stem(w) for w in _norm(title).replace("'", " ").split() if w not in _STOP}
            return len(t & entity_stems) / max(1, len(t | entity_stems))

        def collect(archivio: _Archivio, paths: list[tuple[str, float]]):
            for path, prior in paths:
                data = archivio.read(path)
                if not data:
                    continue
                title, paragraphs, infobox = data
                title_stems = {_stem(w) for w in _norm(title).split()}
                # Conta anche il titolo del redirect: «Giulio Cesare» → «Gaio Giulio Cesare»
                fit = max(title_fit(title), title_fit(path.replace("_", " ")))
                bonus = prior + 3.0 * fit
                units = []
                if infobox:
                    units.append((0, "; ".join(infobox)))
                units += [(i + 1, p) for i, p in enumerate(paragraphs[:cfg.biblioteca_paragrafi])]
                for pos, text in units:
                    # Il titolo fa parte del passaggio: «Lunghezza: 651,8 km» parla del Po
                    s = (self._score(f"{title} {text}", stems, title_stems)
                         + bonus - 0.05 * pos)
                    if pos == 0 and asks_data:
                        s += 1.0   # la domanda chiede un dato: l'infobox è il posto giusto
                    if pos == 1:
                        s += 0.4           # la prima frase della voce di solito definisce
                    passages.append(Passaggio(text, title, archivio.fonte, s,
                                              archivio.path, path))

        n = cfg.biblioteca_voci
        sources = ([self.ragazzi] if semplice and self.ragazzi else []) + self.archivi
        for archivio in sources:
            # Vikidia, quando la spiegazione dev'essere semplice, passa davanti a Wikipedia
            boost = cfg.biblioteca_ragazzi_vantaggio if archivio is self.ragazzi else 0.0
            paths: list[tuple[str, float]] = []
            # Titoli esatti presi dalla frase: i più lunghi prima («Muro di Berlino» prima
            # di «Berlino»), con un vantaggio che decresce
            for p in archivio.superlative(domanda)[:2]:
                paths.append((p, 3.5))       # il primato sta nella voce-elenco
            for rank, p in enumerate(archivio.exact(domanda)[:4]):
                if p not in {q for q, _ in paths}:
                    paths.append((p, 1.8 - rank * 0.3))
            for rank, p in enumerate(archivio.titles(entity or words, n)):
                if p not in {q for q, _ in paths}:
                    paths.append((p, 1.0 - rank * 0.1))
            for rank, p in enumerate(archivio.fulltext(words, n)):
                if p not in {q for q, _ in paths}:
                    paths.append((p, 0.6 - rank * 0.05))
            collect(archivio, [(p, prior + boost) for p, prior in paths[:n + 4]])

        def collect_quotes(archivio: _Archivio):
            """Wikiquote: ogni voce è un elenco di citazioni (il primo paragrafo presenta
            l'autore). Si guardano tutte, non solo le prime: «chi ha detto "…"?» cerca
            proprio quella frase; per «una citazione di Einstein» vincono le brevi."""
            paths: list[tuple[str, float]] = []
            for rank, p in enumerate(archivio.exact(domanda)[:3]):
                paths.append((p, 2.0 - rank * 0.3))
            for rank, p in enumerate(archivio.titles(entity or words, 4)):
                if p not in {q for q, _ in paths}:
                    paths.append((p, 1.2 - rank * 0.1))
            for rank, p in enumerate(archivio.fulltext(words, n)):
                if p not in {q for q, _ in paths}:
                    paths.append((p, 1.0 - rank * 0.1))
            for path, prior in paths[:n + 2]:
                data = archivio.read(path)
                if not data:
                    continue
                title, paragraphs, _ = data
                title_stems = {_stem(w) for w in _norm(title).split()}
                fit = max(title_fit(title), title_fit(path.replace("_", " ")))
                # «Citazioni su Einstein» sono di altri: per «una citazione di Einstein»
                # vale la voce dell'autore
                about = 1.5 if "citazioni su" in title.lower() else 0.0
                # Sulla voce dell'autore cercato il suo nome nel testo non aiuta: una sua
                # frase non lo nomina, una che lo nomina parla di lui (o è una fonte)
                author = fit >= 0.5
                own = ({s: w for s, w in stems.items() if s not in entity_stems}
                       if author else stems)
                for pos, text in enumerate(paragraphs[1:2000], start=1):
                    if _NON_CITAZIONE.search(text):
                        continue
                    penalty = 0.0
                    if author:
                        tw = {_stem(w) for w in _norm(text).replace("'", " ").split()}
                        penalty += 1.5 if entity_stems & tw else 0.0
                        penalty += 2.0 if _ATTRIBUZIONE.search(text) else 0.0
                    s = (self._score(text, own, set()) + prior + 3.0 * fit
                         + _RICHIESTA_VANTAGGIO - 0.002 * pos - about - penalty
                         - (0.8 if len(text) > 300 else 0.0))
                    passages.append(Passaggio(text, title, archivio.fonte, s))

        quote_sources = set()
        for archivio, kind in self.extra:
            if kind in asked:
                quote_sources.add(archivio.fonte)
                collect_quotes(archivio)

        passages.sort(key=lambda p: -p.punteggio)
        # Voci complete se nel mini non c'è niente di convincente, oppure se la domanda
        # chiede un dato e nei passaggi migliori manca l'etichetta collegata: la torre di
        # Pisa nel mini non ha l'altezza, la voce completa sì.
        hint_stems = set()
        for w in words:
            h = _DATA_HINTS.get(w)
            for x in ((h,) if isinstance(h, str) else h or ()):
                hint_stems.add(_stem(x))
        top_words = {_stem(x) for p in passages[:k]
                     for x in _norm(p.testo).replace("'", " ").split()}
        missing_data = bool(hint_stems) and not (hint_stems & top_words)
        if self.completa and self.completa not in self.archivi and (
                not passages or missing_data
                or passages[0].punteggio < cfg.biblioteca_soglia_completa):
            top_titles = []
            for p in passages:
                if p.titolo not in top_titles:
                    top_titles.append(p.titolo)
            paths = [(t.replace(" ", "_"), 1.0) for t in top_titles[:3]]
            for rank, p in enumerate(self.completa.fulltext(words, 4)):
                paths.append((p, 0.6 - rank * 0.05))
            collect(self.completa, paths)
            passages.sort(key=lambda p: -p.punteggio)

        # Domanda con superlativo («il lago più grande d'Italia»): valgono solo i passaggi
        # che esprimono davvero un primato. Il 26/09 la superficie di Lago, un comune
        # calabrese, diventava «il lago più grande»: meglio nessun passaggio, così il
        # modello risponde con quello che sa.
        sup = re.search(r"\b(?:più|meno)\s+(\w+)(?:\s+(?:d'|del|della|dell'|dei|in)\s*(\w+))?",
                        domanda.lower().replace("’", "'"))
        if sup:
            adj = _stem(sup.group(1))
            # (niente «maggiore»: coincide con il nome del Lago Maggiore)
            record = re.compile(rf"\b(?:più|meno)\s+{re.escape(adj)}\w*|\bprimo per\b", re.I)
            # Il primato deve valere dove chiede la domanda: «il più grande lago delle
            # valli di Lanzo» non risponde a «il lago più grande d'Italia» (26/09)
            where = _stem(sup.group(2)) if sup.group(2) else None
            passages = [p for p in passages if p.fonte in quote_sources or (
                record.search(p.testo) and (
                    not where or where in {_stem(w) for w in
                                           _norm(f"{p.titolo} {p.testo}").replace("'", " ")
                                           .split()}))]

        # Al massimo due passaggi per voce, poi i migliori k
        out, per_title = [], {}
        for p in passages:
            if per_title.get(p.titolo, 0) >= 2 or any(p.testo == q.testo for q in out):
                continue
            per_title[p.titolo] = per_title.get(p.titolo, 0) + 1
            out.append(Passaggio(self._trim(p.testo, stems, cfg.biblioteca_max_caratteri),
                                 p.titolo, p.fonte, round(p.punteggio, 2), p.archivio,
                                 p.percorso))
            if len(out) >= k:
                break
        return lead + out

    def testo_voce(self, passaggio: Passaggio, max_caratteri: int = 2500) -> str:
        """I primi paragrafi della voce del passaggio, per leggerla sullo schermo (la voce
        dice 1–3 frasi). La lettura è già in cache dalla ricerca: ~0 ms."""
        if not passaggio.archivio or not passaggio.percorso:
            return ""
        archivio = next((a for a in self._tutti() if a.path == passaggio.archivio), None)
        data = archivio.read(passaggio.percorso) if archivio else None
        if not data:
            return ""
        out, n = [], 0
        for p in data[1]:
            if n + len(p) > max_caratteri and out:
                break
            out.append(p)
            n += len(p) + 2
        return "\n\n".join(out)[:max_caratteri]


def load_biblioteca(cfg) -> Biblioteca | None:
    """La biblioteca se ci sono i file, altrimenti None (Calliope va avanti). Lo
    stato va nel registro delle capacità (calliope/capacita.py), non in stampe sue: il
    motivo e il prossimo passo sono quelli del controllo `check_biblioteca`."""
    from . import capacita
    check = capacita.controlla_una(cfg, "biblioteca")
    if not cfg.biblioteca_enabled or check["stato"] != "attiva":
        capacita.REGISTRO.da_dict(check)
        return None
    b = Biblioteca(cfg)
    if not b.disponibile:
        capacita.segnala("biblioteca", "guasta", "i file ZIM non si aprono",
                         "Riscarica la biblioteca: dimmi «scarica la biblioteca».",
                         check["dettagli"])
        return None
    motivo = f"{b.descrizione()}, aperti in {b.open_ms:.0f} ms"
    if check["motivo"]:
        motivo += f"; {check['motivo']}"
    capacita.segnala("biblioteca", "attiva", motivo, check["prossimo_passo"], check["dettagli"])
    return b
