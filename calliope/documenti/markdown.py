"""
Il Markdown dei testi dell'agente (07/10/2026): ricerche, relazioni e riassunti si consegnano
come `risultato.md` (titoli, sezioni, elenchi, tabelle). Il formato a blocchi (formato.py)
resta per lettere, fatture, modelli e per la conversione.

Un sottoinsieme, scritto qui (niente librerie: principio 4), uguale a quello del lettore della
pagina (schermi/pagina/schermo.js, `leggiMarkdown`):
  titoli (# … ######, e le sottolineature === e ---), paragrafi, elenchi puntati e numerati
  (anche annidati, per rientro), tabelle con la riga dei trattini, codice tra ``` o ~~~,
  citazioni (>), righe orizzontali; dentro le righe grassetto, corsivo, barrato, codice e
  collegamenti. Niente HTML: un tag scritto nel testo resta testo. I collegamenti restano testo
  (con l'indirizzo tra parentesi nei file, senza a voce), le immagini diventano «[immagine: …]».

- `analizza(md)` → i blocchi (dizionari), con i limiti contro i testi ostili: lunghezza,
  numero di blocchi, righe e colonne delle tabelle, rientri e citazioni annidate;
- `a_blocchi(md, titolo)` → il documento nel formato a blocchi, per il PDF e il Word del
  pulsante «Scarica» e di «fammene un PDF» (render.py, senza i limiti di un documento detto
  a voce: un rapporto dell'agente è più lungo);
- `da_blocchi(doc)` → il Markdown di un documento a blocchi (il «Scarica» MD di una lettera);
- `per_voce(md)` → testo semplice da dire (prima di Piper: niente cancelletti, asterischi,
  barre di tabella, indirizzi);
- `descrivi(md)` → cosa contiene, in poche parole («3 sezioni, un elenco e una tabella»).
"""

from __future__ import annotations

import re

MAX_CARATTERI = 200_000      # oltre si taglia: un rapporto vero è molto più corto
MAX_BLOCCHI = 2_000
MAX_RIGHE = 500              # righe di una tabella
MAX_COLONNE = 20
MAX_LIVELLO = 6              # rientri di un elenco
MAX_CITAZIONI = 4            # citazioni dentro citazioni

# Formato a blocchi: limiti di render (formato.MAX_COLONNE, pagine leggibili)
_COLONNE_DOC = 12
_RIGHE_DOC = 200
_CELLA_DOC = 300

_CONTROLLO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_TITOLO = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_RIGA_ORIZZ = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_RECINTO = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_VOCE = re.compile(r"^([ \t]*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$")
_SEP_TABELLA = re.compile(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_CITAZIONE = re.compile(r"^ {0,3}>[ ]?(.*)$")
_SOTTO1 = re.compile(r"^ {0,3}=+[ \t]*$")
_SOTTO2 = re.compile(r"^ {0,3}-+[ \t]*$")


def normalizza(md: str) -> str:
    """A capo uniformi, niente caratteri di controllo né di direzione del testo, al più
    MAX_CARATTERI."""
    t = str(md or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    t = _CONTROLLO.sub("", t)
    return t[:MAX_CARATTERI]


def _celle(riga: str) -> list[str]:
    r = riga.strip()
    if r.startswith("|"):
        r = r[1:]
    if r.endswith("|") and not r.endswith("\\|"):
        r = r[:-1]
    celle, cur, i = [], "", 0
    while i < len(r):
        ch = r[i]
        if ch == "\\" and i + 1 < len(r) and r[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "|":
            celle.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    celle.append(cur.strip())
    return celle


def _inizia_blocco(riga: str, dopo: str | None) -> bool:
    """La riga apre un blocco diverso da un paragrafo (chiude il paragrafo in corso)."""
    return bool(_TITOLO.match(riga) or _RIGA_ORIZZ.match(riga) or _RECINTO.match(riga)
                or _VOCE.match(riga) or _CITAZIONE.match(riga)
                or ("|" in riga and dopo is not None and _SEP_TABELLA.match(dopo)
                    and "-" in dopo))


def analizza(md: str, _livello: int = 0) -> list[dict]:
    """I blocchi del testo: {"tipo": "titolo", "livello", "testo"} | {"tipo": "paragrafo",
    "testo"} | {"tipo": "elenco", "voci": [{"testo", "livello", "numerato"}]} |
    {"tipo": "tabella", "colonne", "righe", "altre"} | {"tipo": "codice", "testo", "lingua"} |
    {"tipo": "citazione", "blocchi"} | {"tipo": "riga"}. Il testo dentro le righe resta
    Markdown (si toglie con `in_linea`)."""
    righe = normalizza(md).split("\n") if _livello == 0 else str(md).split("\n")
    out: list[dict] = []
    i, n = 0, len(righe)
    while i < n and len(out) < MAX_BLOCCHI:
        r = righe[i]
        if not r.strip():
            i += 1
            continue
        m = _RECINTO.match(r)
        if m:
            recinto, lingua = m[1], m[2].strip()[:20]
            corpo = []
            i += 1
            while i < n and not re.match(r"^ {0,3}" + re.escape(recinto[0]) + "{"
                                         + str(len(recinto)) + r",}[ \t]*$", righe[i]):
                corpo.append(righe[i])
                i += 1
            i += 1
            out.append({"tipo": "codice", "testo": "\n".join(corpo), "lingua": lingua})
            continue
        m = _TITOLO.match(r)
        if m:
            out.append({"tipo": "titolo", "livello": len(m[1]), "testo": (m[2] or "").strip()})
            i += 1
            continue
        if _RIGA_ORIZZ.match(r):
            out.append({"tipo": "riga"})
            i += 1
            continue
        dopo = righe[i + 1] if i + 1 < n else None
        if "|" in r and dopo is not None and _SEP_TABELLA.match(dopo) and "-" in dopo:
            colonne = _celle(r)[:MAX_COLONNE]
            corpo, altre = [], 0
            i += 2
            while i < n and righe[i].strip() and "|" in righe[i]:
                if len(corpo) < MAX_RIGHE:
                    c = _celle(righe[i])[:len(colonne)]
                    corpo.append(c + [""] * (len(colonne) - len(c)))
                else:
                    altre += 1
                i += 1
            out.append({"tipo": "tabella", "colonne": colonne, "righe": corpo, "altre": altre})
            continue
        if _CITAZIONE.match(r):
            dentro = []
            while i < n and righe[i].strip():
                mq = _CITAZIONE.match(righe[i])
                if not mq and not dentro:
                    break
                dentro.append(mq[1] if mq else righe[i])
                i += 1
            if _livello + 1 >= MAX_CITAZIONI:
                testo = " ".join(re.sub(r"^(?:\s*>)+\s?", "", x) for x in dentro).strip()
                out.append({"tipo": "citazione", "blocchi": [{"tipo": "paragrafo",
                                                              "testo": testo}]})
            else:
                out.append({"tipo": "citazione",
                            "blocchi": analizza("\n".join(dentro), _livello + 1)})
            continue
        if _VOCE.match(r):
            voci = []
            base = None
            while i < n:
                riga = righe[i]
                mv = _VOCE.match(riga)
                if mv:
                    rientro = len(mv[1])
                    if base is None:
                        base = rientro
                    livello = max(0, min(MAX_LIVELLO - 1, (rientro - base) // 2))
                    if livello == 0 and voci and voci[0]["numerato"] != mv[2][0].isdigit():
                        break                                  # da puntato a numerato: altro elenco
                    voci.append({"testo": mv[3].strip(), "livello": livello,
                                 "numerato": mv[2][0].isdigit()})
                    i += 1
                    continue
                if riga.strip() and voci and riga.startswith((" ", "\t")) and not \
                        _inizia_blocco(riga.strip(), None):
                    voci[-1]["testo"] += " " + riga.strip()     # la voce continua a capo
                    i += 1
                    continue
                if not riga.strip() and i + 1 < n and _VOCE.match(righe[i + 1]):
                    i += 1                                     # elenco «largo»
                    continue
                break
            out.append({"tipo": "elenco", "voci": voci})
            continue
        # Paragrafo (e titolo sottolineato con === o ---)
        testo = [r.strip()]
        i += 1
        while i < n and righe[i].strip():
            if _SOTTO1.match(righe[i]) or (_SOTTO2.match(righe[i]) and len(testo) == 1):
                break
            if _inizia_blocco(righe[i], righe[i + 1] if i + 1 < n else None):
                break
            testo.append(righe[i].strip())
            i += 1
        if i < n and righe[i].strip() and (_SOTTO1.match(righe[i]) or _SOTTO2.match(righe[i])):
            out.append({"tipo": "titolo", "livello": 1 if _SOTTO1.match(righe[i]) else 2,
                        "testo": " ".join(testo)})
            i += 1
            continue
        out.append({"tipo": "paragrafo", "testo": "\n".join(testo)})
    return out


# ─────────────────────────── dentro le righe ───────────────────────────

_IMMAGINE = re.compile(r"!\[([^\]\n]{0,300})\]\(((?:[^()\[\]\s]|\([^()\[\]\s]{0,100}\)){0,600})(?:\s+\"[^\"\n]{0,120}\")?\)")
_LINK = re.compile(r"\[([^\]\n]{0,500})\]\(((?:[^()\[\]\s]|\([^()\[\]\s]{0,100}\)){0,600})(?:\s+\"[^\"\n]{0,120}\")?\)")
_AUTOLINK = re.compile(r"<((?:https?|mailto|ftp|javascript|data|file|vbscript):[^>\s]{0,600})>",
                       re.I)
# Le parti in evidenza sono brevi e su una riga: con `.+?` senza limiti un testo ostile («*a »
# ripetuto 60 000 volte) costava un tempo quadratico, minuti (misura del 07/10)
_ENFASI = [re.compile(r"\*\*(?=\S)([^\n]{1,400}?)(?<=\S)\*\*"),
           re.compile(r"(?<![\w\\])__(?=\S)([^\n]{1,400}?)(?<=\S)__(?!\w)"),
           re.compile(r"~~(?=\S)([^\n]{1,400}?)(?<=\S)~~"),
           re.compile(r"(?<![\w*\\])\*(?=[^\s*])([^\n]{1,400}?)(?<=[^\s*\\])\*(?![\w*])"),
           re.compile(r"(?<![\w\\])_(?=[^\s_])([^\n]{1,400}?)(?<=[^\s_\\])_(?!\w)")]
_FUGA = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~>])")


def in_linea(testo: str, indirizzi: bool = True, apici: bool = False) -> str:
    """Il testo di una riga senza il Markdown: grassetto, corsivo, barrato e codice tolti,
    collegamenti come testo (con l'indirizzo tra parentesi se `indirizzi`), immagini come
    «[immagine: …]» (o niente a voce). Con `apici` il codice resta tra apici inversi (chi lo
    riconosce come codice lo vede ancora)."""
    t = str(testo or "")
    pezzi = re.split(r"(`+[^`\n]*?`+)", t)      # il codice resta com'è
    out = []
    for p in pezzi:
        if p.startswith("`") and p.endswith("`") and len(p) >= 2:
            out.append(p if apici or not p.strip("`") else p.strip("`").strip())
            continue
        p = _IMMAGINE.sub(lambda m: (f"[immagine: {m[1]}]" if m[1] else "[immagine]")
                          if indirizzi else "", p)
        p = _LINK.sub(lambda m: (f"{m[1]} ({m[2]})" if m[2] and m[2] != m[1] else m[1])
                      if indirizzi else m[1], p)
        p = _AUTOLINK.sub(lambda m: m[1] if indirizzi else "", p)
        for rx in _ENFASI:
            for _ in range(3):                 # annidati: **_così_**
                nuovo = rx.sub(r"\1", p)
                if nuovo == p:
                    break
                p = nuovo
        out.append(_FUGA.sub(r"\1", p))
    return "".join(out)


# ─────────────────────────── per la voce ───────────────────────────

_URL = re.compile(r"https?://\S+|www\.\S+", re.I)


def per_voce(md: str, codice: bool = False, tieni_codice: bool = False) -> str:
    """Il testo da dire: titoli come frasi, voci degli elenchi come frasi, niente tabelle né
    codice (o il codice com'è con `codice`), niente indirizzi, niente simboli del Markdown.
    `tieni_codice`: il codice dentro le righe resta tra apici inversi (agenti/ciclo.per_la_voce
    poi scarta le frasi che ne hanno)."""
    frasi = []

    def frase(s: str):
        s = _URL.sub("", in_linea(s, indirizzi=False, apici=tieni_codice))
        s = re.sub(r"[*#|>~]+" if tieni_codice else r"[*_#`|>~]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            frasi.append(s if s[-1] in ".!?:;…" else s + ".")

    def giro(blocchi):
        for b in blocchi:
            if b["tipo"] in ("titolo", "paragrafo"):
                frase(b["testo"])
            elif b["tipo"] == "elenco":
                for v in b["voci"]:
                    frase(v["testo"])
            elif b["tipo"] == "citazione":
                giro(b["blocchi"])
            elif b["tipo"] == "codice" and codice:
                frasi.append(b["testo"])
    giro(analizza(md))
    return " ".join(frasi)


def sembra_markdown(testo: str) -> bool:
    """Il testo ha forme del Markdown (titoli, elenchi, tabelle, grassetto, recinti)."""
    t = str(testo or "")
    return bool(re.search(r"(?m)^ {0,3}(#{1,6} |[-*+] |\d{1,3}[.)] |>|```|\|.*\|)", t)
                or re.search(r"\*\*\S|__\S", t))


# ─────────────────────────── descrizione ───────────────────────────

def _n(n: int, uno: str, tanti: str, art: str = "un") -> str:
    return f"{art} {uno}" if n == 1 else f"{n} {tanti}"


def descrivi(md: str) -> str:
    """Cosa contiene, per la voce: «3 sezioni, un elenco e una tabella» (mai il contenuto)."""
    blocchi = analizza(md)
    sezioni = sum(1 for b in blocchi if b["tipo"] == "titolo" and b["livello"] >= 2)
    if not sezioni:
        sezioni = max(0, sum(1 for b in blocchi if b["tipo"] == "titolo") - 1)
    elenchi = sum(1 for b in blocchi if b["tipo"] == "elenco")
    tabelle = sum(1 for b in blocchi if b["tipo"] == "tabella")
    paragrafi = sum(1 for b in blocchi if b["tipo"] == "paragrafo")
    parti = []
    if sezioni:
        parti.append(_n(sezioni, "sezione", "sezioni", "una"))
    elif paragrafi:
        parti.append(_n(paragrafi, "paragrafo", "paragrafi"))
    if elenchi:
        parti.append(_n(elenchi, "elenco", "elenchi"))
    if tabelle:
        parti.append(_n(tabelle, "tabella", "tabelle", "una"))
    if not parti:
        return ""
    return parti[0] if len(parti) == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]


def titolo_di(md: str) -> str:
    """Il primo titolo di primo livello (o il primo titolo), senza Markdown; "" se non c'è."""
    blocchi = analizza(md)
    primo = next((b for b in blocchi if b["tipo"] == "titolo" and b["livello"] == 1), None) or \
        next((b for b in blocchi if b["tipo"] == "titolo"), None)
    return in_linea(primo["testo"], indirizzi=False).strip() if primo else ""


def con_titolo(md: str, titolo: str) -> str:
    """Il testo con un titolo di primo livello in cima, se non ce l'ha già."""
    t = normalizza(md).strip()
    if any(b["tipo"] == "titolo" and b["livello"] == 1 for b in analizza(t)[:3]):
        return t + "\n"
    return f"# {str(titolo or 'Risultato').strip()}\n\n{t}\n"


# ─────────────────────────── conversioni ───────────────────────────

def _taglia(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def a_blocchi(md: str, titolo: str = "") -> dict:
    """Il documento a blocchi (formato.py, forma «testo») per render.py: titoli, paragrafi,
    elenchi (i livelli annidati con «– » davanti), tabelle (al più 12 colonne: le altre unite
    nell'ultima; oltre 200 righe in più tabelle), codice e citazioni come paragrafi."""
    blocchi = analizza(md)
    titolo = str(titolo or "").strip() or titolo_di(md) or "Documento"
    out: list[dict] = []

    def giro(bb, cit=False):
        for b in bb:
            k = b["tipo"]
            if k == "titolo":
                t = in_linea(b["testo"]).strip()
                if t:
                    out.append({"tipo": "titolo", "testo": _taglia(t, 200)})
            elif k == "paragrafo":
                t = in_linea(b["testo"]).strip()
                if t:
                    out.append({"tipo": "paragrafo", "testo": f"«{t}»" if cit else t})
            elif k == "codice":
                if b["testo"].strip():
                    out.append({"tipo": "paragrafo", "testo": b["testo"].rstrip()})
            elif k == "citazione":
                giro(b["blocchi"], True)
            elif k == "elenco":
                voci = [("– " * v["livello"]) + in_linea(v["testo"]).strip() for v in b["voci"]]
                voci = [_taglia(v, 2000) for v in voci if v.strip(" –")]
                if voci:
                    num = bool(b["voci"][0]["numerato"])
                    for j in range(0, len(voci), 100):
                        out.append({"tipo": "elenco", "voci": voci[j:j + 100], "numerato": num})
            elif k == "tabella":
                cols = [in_linea(c).strip() for c in b["colonne"]]
                righe = [[in_linea(c).strip() for c in r] for r in b["righe"]]
                if len(cols) > _COLONNE_DOC:
                    taglio = _COLONNE_DOC - 1
                    cols = cols[:taglio] + [" · ".join(c for c in cols[taglio:] if c)]
                    righe = [r[:taglio] + [" · ".join(c for c in r[taglio:] if c)] for r in righe]
                righe = [[_taglia(c, _CELLA_DOC) for c in r] for r in righe]
                cols = [_taglia(c, 80) for c in cols]
                for j in range(0, max(1, len(righe)), _RIGHE_DOC):
                    out.append({"tipo": "tabella", "colonne": cols,
                                "righe": righe[j:j + _RIGHE_DOC], "totale": False})
                if b.get("altre"):
                    out.append({"tipo": "paragrafo",
                                "testo": f"(altre {b['altre']} righe non riportate)"})
    giro(blocchi)
    if not out:
        out = [{"tipo": "paragrafo", "testo": "(documento vuoto)"}]
    return {"titolo": _taglia(in_linea(titolo, indirizzi=False), 120), "blocchi": out}


def _fuga(s: str) -> str:
    """Il testo dentro una riga di Markdown: i caratteri che aprirebbero qualcosa restano
    testo."""
    s = re.sub(r"([\\`*_\[\]|<>])", r"\\\1", str(s))
    return re.sub(r"^(\s*)([#>+-]|\d+[.)])", r"\1\\\2", s)


def da_blocchi(doc: dict) -> str:
    """Il Markdown di un documento a blocchi (o di un foglio): per «Scarica» in MD."""
    righe = [f"# {_fuga(doc.get('titolo') or 'Documento')}", ""]

    def tabella(cols, rr, totale=None):
        cols = [str(c) for c in cols] or [""]
        righe.append("| " + " | ".join(_fuga(c) for c in cols) + " |")
        righe.append("|" + "|".join(" --- " for _ in cols) + "|")
        for r in list(rr) + ([totale] if totale else []):
            celle = [str(c) for c in r] + [""] * (len(cols) - len(r))
            righe.append("| " + " | ".join(_fuga(c).replace("\n", " ") for c in celle) + " |")
        righe.append("")

    from .formato import table_total
    for b in doc.get("blocchi") or []:
        k = b.get("tipo")
        if k == "titolo":
            righe += [f"## {_fuga(b.get('testo', ''))}", ""]
        elif k == "paragrafo":
            righe += ["  \n".join(_fuga(x) for x in str(b.get("testo", "")).split("\n")), ""]
        elif k == "elenco":
            for j, v in enumerate(b.get("voci") or [], 1):
                righe.append((f"{j}. " if b.get("numerato") else "- ") + _fuga(v))
            righe.append("")
        elif k == "tabella":
            tot = (table_total(b["colonne"], b["righe"]) if b.get("totale") else None)
            tabella(b.get("colonne") or [], b.get("righe") or [], tot)
    for f in doc.get("fogli") or []:
        righe += [f"## {_fuga(f.get('nome', ''))}", ""]
        tot = table_total(f["colonne"], f["righe"]) if f.get("totale") else None
        tabella(f.get("colonne") or [], f.get("righe") or [], tot)
    return "\n".join(righe).rstrip() + "\n"
