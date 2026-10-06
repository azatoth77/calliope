"""
Il formato intermedio dei documenti: schema JSON, validazione, formule, numeri, nomi dei
file e le frasi brevi che dicono cosa contiene un documento.

L'LLM scrive solo questo JSON (con lo schema negli output strutturati di Ollama); il file
lo fa il codice (render.py). Due forme:

  testo (word, pdf):  {"titolo": str, "blocchi": [blocco, ...]}
      {"tipo": "titolo", "testo": str}
      {"tipo": "paragrafo", "testo": str, "allinea": "sinistra" | "destra"}
      {"tipo": "elenco", "voci": [str], "numerato": bool}
      {"tipo": "tabella", "colonne": [str], "righe": [[str]], "totale": bool}
  foglio (excel):     {"titolo": str, "fogli": [{"nome": str, "colonne": [str],
                                                 "righe": [[str | numero]], "totale": bool}]}

Il totale lo calcola il programma (formula SUM in Excel, somma in Word e PDF): un modello
piccolo sbaglia i conti e conta male le righe dei riferimenti.
"""

import difflib
import json
import re

FORMATI = ("word", "excel", "pdf")
ESTENSIONI = {"word": "docx", "excel": "xlsx", "pdf": "pdf"}
TIPI_BLOCCO = ("titolo", "paragrafo", "elenco", "tabella")

# Limiti: un documento a voce è breve. Oltre, è quasi sempre un modello che si ripete.
MAX_TITOLO = 120
MAX_BLOCCHI = 60
MAX_TESTO = 3000            # un paragrafo
MAX_VOCI = 100
MAX_VOCE = 500
MAX_COLONNE = 12            # word e pdf: oltre non ci stanno in una pagina
MAX_COLONNE_FOGLIO = 20
MAX_RIGHE = 200
MAX_RIGHE_FOGLIO = 500
MAX_CELLA = 300
MAX_FOGLI = 5
MAX_CARATTERI = 20000       # tutto il documento
MAX_FORMULA = 200


class DocumentoNonValido(ValueError):
    """Il JSON non va bene: `errors` sono frasi brevi, da rimandare al modello."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# ─────────────────────────── schema per Ollama ───────────────────────────

def _s():
    return {"type": "string"}


def _cell():
    # Testo o numero: con le sole stringhe il modello, che voleva scrivere 800, apriva la
    # stringa e ci metteva «},{» (27/09)
    return {"anyOf": [{"type": "string"}, {"type": "number"}]}


def _block(tipo: str, props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": {"tipo": {"type": "string", "enum": [tipo]}, **props},
            "required": ["tipo", *required]}


# Un anyOf per tipo di blocco: con uno schema piatto (tutti i campi facoltativi) il
# modello metteva la tabella in markdown dentro «testo» (misura del 27/09)
SCHEMA_TESTO = {
    "type": "object",
    "properties": {
        "titolo": _s(),
        "blocchi": {"type": "array", "items": {"anyOf": [
            _block("titolo", {"testo": _s()}, ["testo"]),
            _block("paragrafo", {"testo": _s(),
                                 "allinea": {"type": "string", "enum": ["sinistra", "destra"]}},
                   ["testo"]),
            _block("elenco", {"voci": {"type": "array", "items": _s()},
                              "numerato": {"type": "boolean"}}, ["voci"]),
            _block("tabella", {"colonne": {"type": "array", "items": _s()},
                               "righe": {"type": "array", "items": {"type": "array",
                                                                    "items": _cell()}},
                               "totale": {"type": "boolean"}}, ["colonne", "righe"]),
        ]}},
    },
    "required": ["titolo", "blocchi"],
}

SCHEMA_FOGLIO = {
    "type": "object",
    "properties": {
        "titolo": _s(),
        "fogli": {"type": "array", "items": {
            "type": "object",
            "properties": {"nome": _s(),
                           "colonne": {"type": "array", "items": _s()},
                           "righe": {"type": "array", "items": {"type": "array",
                                                                "items": _cell()}},
                           "totale": {"type": "boolean"}},
            "required": ["nome", "colonne", "righe"]}},
    },
    "required": ["titolo", "fogli"],
}


def schema_for(formato: str) -> dict:
    return SCHEMA_FOGLIO if formato == "excel" else SCHEMA_TESTO


# ─────────────────────────── numeri ───────────────────────────
# Come li scrive una persona (o il modello): «800», «1.200,50», «12.5», «€ 90», «90 euro».
_NUMBER = re.compile(r"^\s*(€\s*)?([+-]?)\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:([.,])(\d+))?\s*"
                     r"(€|euro|eur)?\s*$", re.I)


def parse_number(value) -> tuple[float | int, bool] | None:
    """(numero, è in euro) oppure None se non è un numero. I codici con lo zero davanti
    («007», un CAP) restano testo; il punto con tre cifre dopo è delle migliaia."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value, False
    m = _NUMBER.match(str(value or ""))
    if not m:
        return None
    euro, sign, whole, sep, dec, suffix = m.groups()
    digits = whole.replace(".", "")
    if len(digits) > 1 and digits.startswith("0") and not sep:
        return None                           # «007», «00123»: codici, non numeri
    if sep == "." and dec is not None and len(dec) == 3 and "." not in whole:
        digits, dec = digits + dec, None      # «1.200» = milleduecento
    elif sep == "." and "." in whole:
        return None                           # «1.200.5»: ambiguo
    text = digits + (f".{dec}" if dec else "")
    number = float(text) if dec else int(text)
    return (-number if sign == "-" else number), bool(euro or suffix)


def format_number(x, euro: bool = False) -> str:
    """All'italiana: 1.234,5 (e « €» se è in euro)."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    if isinstance(x, int):
        s = f"{x:,}".replace(",", ".")
    else:
        s = f"{x:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €" if euro else s


def _is_euro_header(name: str) -> bool:
    return bool(re.search(r"€|\beur(o|i)?\b", str(name or ""), re.I))


def numeric_columns(colonne: list, righe: list) -> dict[int, bool]:
    """Le colonne (tranne la prima, che di solito ha i nomi) con soli numeri: indice →
    in euro. Una formula conta come numero."""
    out = {}
    for c in range(1, len(colonne)):
        values = [r[c] for r in righe if c < len(r) and str(r[c]).strip() != ""]
        if not values:
            continue
        parsed = [parse_number(v) for v in values]
        formulas = [isinstance(v, str) and v.strip().startswith("=") for v in values]
        if all(p is not None or f for p, f in zip(parsed, formulas)) and any(parsed):
            out[c] = _is_euro_header(colonne[c]) or any(p and p[1] for p in parsed)
    return out


def table_total(colonne: list, righe: list) -> list[str]:
    """La riga del totale per Word e PDF: «Totale» nella prima colonna, la somma nelle
    colonne di soli numeri (calcolata qui, non dal modello)."""
    cols = numeric_columns(colonne, righe)
    row = ["Totale"] + [""] * (len(colonne) - 1)
    for c, euro in cols.items():
        total = sum(parse_number(r[c])[0] for r in righe
                    if c < len(r) and parse_number(r[c]) is not None)
        row[c] = format_number(round(total, 2), euro)
    return row


# ─────────────────────────── formule ───────────────────────────
# Solo funzioni di calcolo su celle dello stesso foglio. Niente HYPERLINK, WEBSERVICE,
# INDIRECT, DDE (=cmd|…), IMPORT…, niente riferimenti ad altri file o fogli.
FUNZIONI = {"SUM", "AVERAGE", "MIN", "MAX", "COUNT", "COUNTA", "ROUND", "IF", "ABS",
            "PRODUCT", "AND", "OR", "NOT"}
# Il modello a volte le scrive come nell'Excel italiano
_ALIAS = {"SOMMA": "SUM", "MEDIA": "AVERAGE", "CONTA.NUMERI": "COUNT", "CONTA.VALORI": "COUNTA",
          "ARROTONDA": "ROUND", "SE": "IF", "ASS": "ABS", "PRODOTTO": "PRODUCT", "E": "AND",
          "O": "OR", "NON": "NOT", "MINIMO": "MIN", "MASSIMO": "MAX"}
_TOKEN = re.compile(
    r"\s*(?:(?P<ref>\$?[A-Z]{1,2}\$?\d{1,4}(?::\$?[A-Z]{1,2}\$?\d{1,4})?)(?![\w(.])"
    r"|(?P<func>[A-Z][A-Z0-9.]*)\s*\("
    r"|(?P<num>\d+(?:\.\d+)?%?)"
    r"|(?P<str>\"[^\"]{0,60}\")"
    r"|(?P<op><>|<=|>=|[-+*/^&=<>(),;]))")


def col_letter(n: int) -> str:
    """1 → A, 27 → AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def check_formula(text: str, max_col: int, max_row: int) -> str:
    """La formula normalizzata («=SUM(B2:B4)») o ValueError con il motivo."""
    f = str(text or "").strip()
    if not f.startswith("="):
        raise ValueError("una formula comincia con =")
    if len(f) > MAX_FORMULA:
        raise ValueError("formula troppo lunga")
    body = f[1:]
    # Maiuscolo fuori dalle stringhe; «;» dell'Excel italiano → «,»
    parts = re.split(r"(\"[^\"]*\")", body)
    body = "".join(p if p.startswith('"') else p.upper().replace(";", ",") for p in parts)
    if re.search(r"[!\[\]|{}`'#@]", "".join(p for p in parts if not p.startswith('"'))):
        raise ValueError("riferimenti esterni o caratteri non ammessi")
    out, pos, depth = [], 0, 0
    while pos < len(body):
        if body[pos:].strip() == "":
            break
        m = _TOKEN.match(body, pos)
        if not m or m.end() == pos:
            raise ValueError(f"non capisco «{body[pos:pos + 12]}»")
        pos = m.end()
        if m["func"]:
            name = _ALIAS.get(m["func"], m["func"])
            if name not in FUNZIONI:
                raise ValueError(f"funzione {m['func']} non ammessa (ammesse: "
                                 f"{', '.join(sorted(FUNZIONI))})")
            out.append(name + "(")
            depth += 1
        elif m["ref"]:
            for cell in m["ref"].replace("$", "").split(":"):
                letters = re.match(r"[A-Z]+", cell).group()
                row = int(cell[len(letters):])
                if _col_index(letters) > max_col or not 1 <= row <= max_row:
                    raise ValueError(f"la cella {cell} è fuori dalla tabella")
            out.append(m["ref"])
        elif m["op"]:
            op = m["op"]
            depth += op == "("
            depth -= op == ")"
            if depth < 0:
                raise ValueError("parentesi sbagliate")
            out.append("," if op == ";" else op)
        else:
            out.append(m["num"] or m["str"])
    if depth != 0:
        raise ValueError("parentesi sbagliate")
    if not out:
        raise ValueError("formula vuota")
    return "=" + "".join(out)


def classify_cell(value, max_col: int, max_row: int):
    """Come va scritta una cella del foglio:
      ("vuota",) | ("formula", "=…") | ("numero", n, euro) | ("testo", s, protetto)
    `protetto` = il testo comincia con + - @ e va scritto come testo puro, perché Excel
    non lo interpreti come formula (formula injection). Una cella con «=» che non è una
    formula ammessa è un errore (ValueError)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return ("vuota",)
    if isinstance(value, bool):
        return ("testo", "sì" if value else "no", False)
    number = parse_number(value)
    if number is not None:
        return ("numero", number[0], number[1])
    s = str(value).strip()
    if s.startswith("="):
        return ("formula", check_formula(s, max_col, max_row))
    return ("testo", s, s[:1] in "+-@\t\r")


# ─────────────────────────── validazione ───────────────────────────

def _text(value, where: str, errors: list, limit: int, required=True) -> str:
    if value is None:
        if required:
            errors.append(f"{where}: manca il testo")
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        errors.append(f"{where}: deve essere un testo")
        return ""
    s = str(value).replace("\r\n", "\n").strip()
    if required and not s:
        errors.append(f"{where}: testo vuoto")
    if len(s) > limit:
        errors.append(f"{where}: testo troppo lungo ({len(s)} caratteri, massimo {limit})")
    return s


def _bool(value) -> bool:
    return value is True or str(value).strip().lower() in ("true", "1", "sì", "si", "yes")


def _rows(raw, ncols: int, where: str, errors: list, max_rows: int, keep_numbers: bool) -> list:
    if not isinstance(raw, list):
        errors.append(f"{where}: righe deve essere un elenco di righe")
        return []
    if len(raw) > max_rows:
        errors.append(f"{where}: troppe righe ({len(raw)}, massimo {max_rows})")
        return []
    rows = []
    for i, row in enumerate(raw, 1):
        if not isinstance(row, list):
            errors.append(f"{where}, riga {i}: deve essere un elenco di valori")
            continue
        cells = []
        for j, cell in enumerate(row, 1):
            if cell is None:
                cells.append("")
            elif isinstance(cell, bool) or not isinstance(cell, (str, int, float)):
                errors.append(f"{where}, riga {i}: il valore {j} non è un testo né un numero")
                cells.append("")
            elif isinstance(cell, str):
                s = cell.strip()
                if len(s) > MAX_CELLA:
                    errors.append(f"{where}, riga {i}: valore troppo lungo")
                cells.append(s)
            else:
                cells.append(cell if keep_numbers else format_number(cell))
        # Valori vuoti in fondo in più: si tolgono; valori veri in più sono un errore
        while len(cells) > ncols and cells[-1] in ("", None):
            cells.pop()
        if len(cells) > ncols:
            errors.append(f"{where}, riga {i}: {len(cells)} valori ma {ncols} colonne")
            continue
        rows.append(cells + [""] * (ncols - len(cells)))
    return rows


def _columns(raw, where: str, errors: list, max_cols: int) -> list[str]:
    if not isinstance(raw, list) or not raw:
        errors.append(f"{where}: servono le colonne (un elenco di nomi)")
        return []
    if len(raw) > max_cols:
        errors.append(f"{where}: troppe colonne ({len(raw)}, massimo {max_cols})")
        return []
    return [_text(c, f"{where}, colonna {i}", errors, 80, required=False)
            for i, c in enumerate(raw, 1)]


def _split_paragraphs(text: str) -> list[str]:
    """Un «paragrafo» con righe vuote dentro sono più paragrafi (il modello a volte mette
    oggetto, corpo e saluti in un blocco solo): separati, si contano e si modificano meglio."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [text]


def validate(formato: str, data) -> dict:
    """Il documento normalizzato, o DocumentoNonValido con tutti gli errori trovati."""
    if formato not in FORMATI:
        raise DocumentoNonValido([f"formato sconosciuto: {formato}"])
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise DocumentoNonValido([f"non è JSON valido: {e}"]) from None
    if not isinstance(data, dict):
        raise DocumentoNonValido(["il documento deve essere un oggetto JSON"])
    errors: list[str] = []
    title = _text(data.get("titolo"), "titolo", errors, MAX_TITOLO)
    doc = _validate_sheet(data, errors) if formato == "excel" else _validate_text(data, errors)
    doc = {"titolo": title, **doc}
    if len(json.dumps(doc, ensure_ascii=False)) > MAX_CARATTERI * 2:
        errors.append("documento troppo lungo")
    if errors:
        raise DocumentoNonValido(errors[:12])
    return doc


def _validate_text(data: dict, errors: list) -> dict:
    blocks = data.get("blocchi")
    if not isinstance(blocks, list) or not blocks:
        errors.append("blocchi: serve un elenco di blocchi non vuoto")
        return {"blocchi": []}
    if len(blocks) > MAX_BLOCCHI:
        errors.append(f"troppi blocchi ({len(blocks)}, massimo {MAX_BLOCCHI})")
        return {"blocchi": []}
    out, chars = [], 0
    for i, b in enumerate(blocks, 1):
        where = f"blocco {i}"
        if not isinstance(b, dict):
            errors.append(f"{where}: deve essere un oggetto")
            continue
        kind = b.get("tipo")
        if kind not in TIPI_BLOCCO:
            errors.append(f"{where}: tipo «{kind}» sconosciuto (ammessi: {', '.join(TIPI_BLOCCO)})")
            continue
        if kind == "titolo":
            text = _text(b.get("testo"), where, errors, 200)
            out.append({"tipo": "titolo", "testo": text})
            chars += len(text)
        elif kind == "paragrafo":
            text = _text(b.get("testo"), where, errors, MAX_TESTO)
            align = "destra" if str(b.get("allinea", "")).lower() == "destra" else "sinistra"
            for p in _split_paragraphs(text):
                block = {"tipo": "paragrafo", "testo": p}
                if align == "destra":
                    block["allinea"] = "destra"
                out.append(block)
            chars += len(text)
        elif kind == "elenco":
            items = b.get("voci")
            if isinstance(items, str):               # «a\nb\nc» invece di un elenco
                items = [v for v in re.split(r"\n+", items) if v.strip()]
            if not isinstance(items, list) or not items:
                errors.append(f"{where}: un elenco ha bisogno delle voci")
                continue
            if len(items) > MAX_VOCI:
                errors.append(f"{where}: troppe voci ({len(items)}, massimo {MAX_VOCI})")
                continue
            voci = [re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", _text(v, f"{where}, voce {j}", errors,
                                                                   MAX_VOCE))
                    for j, v in enumerate(items, 1)]
            out.append({"tipo": "elenco", "voci": voci, "numerato": _bool(b.get("numerato"))})
            chars += sum(map(len, voci))
        else:
            cols = _columns(b.get("colonne"), where, errors, MAX_COLONNE)
            rows = _rows(b.get("righe"), len(cols), where, errors, MAX_RIGHE, keep_numbers=False)
            out.append({"tipo": "tabella", "colonne": cols, "righe": rows,
                        "totale": _bool(b.get("totale"))})
            chars += sum(len(str(c)) for r in rows for c in r)
    if chars > MAX_CARATTERI:
        errors.append(f"documento troppo lungo ({chars} caratteri, massimo {MAX_CARATTERI})")
    return {"blocchi": out}


_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")


def _validate_sheet(data: dict, errors: list) -> dict:
    sheets = data.get("fogli")
    if isinstance(sheets, dict):
        sheets = [sheets]
    if not isinstance(sheets, list) or not sheets:
        errors.append("fogli: serve almeno un foglio")
        return {"fogli": []}
    if len(sheets) > MAX_FOGLI:
        errors.append(f"troppi fogli ({len(sheets)}, massimo {MAX_FOGLI})")
        return {"fogli": []}
    out, names = [], set()
    for i, s in enumerate(sheets, 1):
        where = f"foglio {i}"
        if not isinstance(s, dict):
            errors.append(f"{where}: deve essere un oggetto")
            continue
        name = _SHEET_BAD.sub(" ", _text(s.get("nome"), where, errors, 100, required=False))
        name = re.sub(r"\s+", " ", name).strip(" '")[:31] or f"Foglio{i}"
        base, n = name, 2
        while name.lower() in names:               # nomi dei fogli unici (Excel li vuole così)
            name = f"{base[:28]} {n}"
            n += 1
        names.add(name.lower())
        cols = _columns(s.get("colonne"), where, errors, MAX_COLONNE_FOGLIO)
        rows = _rows(s.get("righe"), len(cols), where, errors, MAX_RIGHE_FOGLIO,
                     keep_numbers=True)
        total = _bool(s.get("totale"))
        # Le formule si controllano ora: riferimenti dentro la tabella (riga 1 = colonne,
        # dati dalla riga 2, più la riga del totale), funzioni dall'elenco
        max_row = len(rows) + 1 + (1 if total else 0)
        for r, row in enumerate(rows, 2):
            for c, cell in enumerate(row, 1):
                try:
                    classify_cell(cell, len(cols), max_row)
                except ValueError as e:
                    errors.append(f"{where}, cella {col_letter(c)}{r}: {e}")
        out.append({"nome": name, "colonne": cols, "righe": rows, "totale": total})
    return {"fogli": out}


# ─────────────────────────── nomi dei file ───────────────────────────
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(title: str, limit: int = 80) -> str:
    """Il titolo come nome di file per Windows: senza \\ / : * ? " < > | e caratteri di
    controllo, spazi compattati, niente punto finale né nomi riservati (CON, NUL…)."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(title or ""))
    s = s.replace("«", "").replace("»", "").replace("“", "").replace("”", "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    s = s[:limit].rstrip(" .")
    if not s:
        return "Documento"
    if s.split(".")[0].upper() in _RESERVED:
        s = f"{s}_"
    return s


# ─────────────────────────── a voce ───────────────────────────

def _n(n: int, one: str, many: str, article: str = "un") -> str:
    return f"{article} {one}" if n == 1 else f"{n} {many}"


def is_letter(*texts: str) -> bool:
    return any(re.search(r"\blettera\b|\bdisdetta\b|\breclamo\b|\bdomanda di\b", t or "", re.I)
               for t in texts)


def summary(formato: str, doc: dict, lettera: bool = False) -> str:
    """Cosa contiene, in poche parole: «5 paragrafi», «una tabella di 3 righe con il
    totale», «un elenco di 4 voci». Mai il contenuto: non si legge a voce."""
    if formato == "excel":
        sheets = doc.get("fogli", [])
        parts = []
        for s in sheets[:2]:
            rows = len(s["righe"])
            parts.append(f"una tabella di {_n(rows, 'riga', 'righe', 'una')}"
                         + (" con il totale" if s.get("totale") else ""))
        text = " e ".join(parts)
        if len(sheets) > 2:
            text = f"{len(sheets)} fogli, il primo con {parts[0]}"
        elif len(sheets) == 2:
            text = f"2 fogli: {text}"
        return text
    blocks = doc.get("blocchi", [])
    paragraphs = sum(b["tipo"] == "paragrafo" for b in blocks)
    lists = [b for b in blocks if b["tipo"] == "elenco"]
    tables = [b for b in blocks if b["tipo"] == "tabella"]
    parts = []
    if paragraphs and (lettera or not (lists or tables)):
        parts.append(_n(paragraphs, "paragrafo", "paragrafi"))
    for b in lists[:2]:
        parts.append(f"un elenco di {_n(len(b['voci']), 'voce', 'voci', 'una')}")
    for b in tables[:2]:
        parts.append(f"una tabella di {_n(len(b['righe']), 'riga', 'righe', 'una')}"
                     + (" con il totale" if b.get("totale") else ""))
    if not parts:
        parts.append(_n(len(blocks), "titolo", "titoli"))
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]


def _size(formato: str, doc: dict) -> int:
    """Quanto contenuto c'è: serve a capire se una «modifica» ha buttato via mezzo documento."""
    return len(json.dumps(doc.get("fogli" if formato == "excel" else "blocchi"),
                          ensure_ascii=False))


def shrunk(formato: str, old: dict, new: dict) -> bool:
    """La nuova versione ha perso più di metà del contenuto?"""
    return _size(formato, new) < 0.5 * _size(formato, old)


def _delta(n: int, one: str, many: str, article: str) -> str:
    return f"{_n(abs(n), one, many, article)} in {'più' if n > 0 else 'meno'}"


def _edits(a: list, b: list) -> tuple[int, int, int]:
    """(cambiati, aggiunti, tolti) tra due sequenze, allineate con difflib."""
    changed = added = removed = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "insert":
            added += j2 - j1
        elif op == "delete":
            removed += i2 - i1
        elif op == "replace":
            common = min(i2 - i1, j2 - j1)
            changed += common
            added += (j2 - j1) - common
            removed += (i2 - i1) - common
    return changed, added, removed


def describe_change(formato: str, old: dict, new: dict) -> str:
    """Cosa è cambiato, in poche parole («una riga in più», «un paragrafo cambiato», «una
    voce in più»), o "" se niente. Serve alla conferma: il documento non si legge."""
    if old == new:
        return ""
    parts = []
    if old.get("titolo") != new.get("titolo"):
        parts.append("il titolo nuovo")        # «…: il titolo cambiato» suonava sgrammaticato
    if formato == "excel":
        so, sn = old.get("fogli", []), new.get("fogli", [])
        if len(so) != len(sn):
            parts.append(_delta(len(sn) - len(so), "foglio", "fogli", "un"))
        a = [json.dumps(r, ensure_ascii=False) for s in so for r in s["righe"]]
        b = [json.dumps(r, ensure_ascii=False) for s in sn for r in s["righe"]]
        changed, added, removed = _edits(a, b)
        if changed:
            parts.append(_n(changed, "riga cambiata", "righe cambiate", "una"))
        if added:
            parts.append(_n(added, "riga in più", "righe in più", "una"))
        if removed:
            parts.append(_n(removed, "riga in meno", "righe in meno", "una"))
        if [s["colonne"] for s in so] != [s["colonne"] for s in sn]:
            parts.append("le colonne cambiate")
        if [bool(s.get("totale")) for s in so] != [bool(s.get("totale")) for s in sn]:
            parts.append("il totale " + ("aggiunto" if any(s.get("totale") for s in sn)
                                         else "tolto"))
        return ", ".join(parts) or "qualche valore cambiato"
    bo, bn = old.get("blocchi", []), new.get("blocchi", [])

    def of(blocks, kind):
        return [b for b in blocks if b["tipo"] == kind]

    # Righe delle tabelle e voci degli elenchi: si contano, non si confrontano i blocchi
    for kind, key, one, many, article in (("tabella", "righe", "riga", "righe", "una"),
                                          ("elenco", "voci", "voce", "voci", "una")):
        xo, xn = of(bo, kind), of(bn, kind)
        a = [json.dumps(v, ensure_ascii=False) for x in xo for v in x[key]]
        b = [json.dumps(v, ensure_ascii=False) for x in xn for v in x[key]]
        changed, added, removed = _edits(a, b)
        if changed:
            parts.append(_n(changed, f"{one} cambiata", f"{many} cambiate", article))
        if added:
            parts.append(_n(added, f"{one} in più", f"{many} in più", article))
        if removed:
            parts.append(_n(removed, f"{one} in meno", f"{many} in meno", article))
        if not (changed or added or removed) and xo != xn:
            parts.append("una tabella cambiata" if kind == "tabella" else "un elenco cambiato")
    for kind, one, many in (("paragrafo", "paragrafo", "paragrafi"), ("titolo", "titolo", "titoli")):
        a = [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in of(bo, kind)]
        b = [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in of(bn, kind)]
        changed, added, removed = _edits(a, b)
        if changed:
            parts.append(_n(changed, f"{one} cambiato", f"{many} cambiati", "un"))
        if added:
            parts.append(_n(added, f"{one} in più", f"{many} in più", "un"))
        if removed:
            parts.append(_n(removed, f"{one} in meno", f"{many} in meno", "un"))
    return ", ".join(parts) or "l'ordine delle parti cambiato"
