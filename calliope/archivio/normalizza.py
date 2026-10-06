"""
Forme normalizzate per l'archivio dei documenti di casa (03/10/2026): chiavi di
deduplicazione delle entità e controlli dei valori estratti contro il testo del documento.

Deduplicazione (regole, in quest'ordine; docs/ricerche/2026-10-03-documenti-grafo.md):
1. un identificativo forte e valido vince: partita IVA (11 cifre con la cifra di controllo)
   per gli enti, codice fiscale (16 caratteri nella forma giusta) per le persone, un codice
   (targa, matricola, POD, PDR) per i beni;
2. altrimenti il nome normalizzato: minuscole, senza accenti né punteggiatura, senza forme
   societarie («S.p.A.», «srl», «snc»…) e titoli («dott.ssa», «sig.»); per le persone le
   parole in ordine alfabetico («Bianchi Mario» = «Mario Bianchi»);
3. altrimenti un nome **molto** simile (rapporto ≥ 0,92, almeno 6 caratteri) dello stesso
   tipo, che diventa un alias con origine «simile»;
4. due identificativi forti diversi non si uniscono mai, anche con lo stesso nome.

Controlli contro il testo («mai inventare»): un importo, una data, un codice o un nome che il
modello restituisce si tiene solo se si ritrova nel testo del documento (in una delle forme
italiane); altrimenti diventa null e finisce tra gli scartati della scheda.
"""

import datetime
import difflib
import re
import unicodedata
from ..testi import MESI


# Forme societarie e parole che non distinguono un ente
_SOCIETA = re.compile(
    r"\b(?:s\s*p\s*a|s\s*r\s*l\s*s?|s\s*n\s*c|s\s*a\s*s|s\s*a\s*p\s*a|s\s*c\s*a\s*r\s*l|"
    r"s\s*c\s*r\s*l|soc(?:ieta)?\s+coop(?:erativa)?|coop|onlus|ltd|gmbh|inc|spa|srl|snc|sas|"
    r"societa\s+(?:per\s+azioni|a\s+responsabilita\s+limitata|in\s+nome\s+collettivo|"
    r"in\s+accomandita\s+semplice|cooperativa)|unipersonale|e\s+c|ditta|gruppo)\b")
_TITOLI = re.compile(r"\b(?:dott(?:\s*ssa|or|oressa)?|dr|dssa|sig(?:ra|na|nor|nora)?|"
                     r"prof(?:ssa|essore|essoressa)?|avv(?:ocato)?|ing(?:egnere)?|geom|rag|"
                     r"arch|on|egr|gent(?:ile|mo|ma)?|spett(?:abile|le)?|mr|mrs)\b")
_PAROLE_VUOTE = {"di", "del", "della", "dello", "dei", "degli", "delle", "e", "il", "lo", "la",
                 "i", "gli", "le", "l", "d", "ed", "a"}


def senza_accenti(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t or "")
                   if not unicodedata.combining(c))


def piatto(t: str) -> str:
    """Minuscole, senza accenti, solo lettere e cifre separate da uno spazio."""
    t = senza_accenti(str(t or "")).lower().replace("'", " ").replace("’", " ")
    t = re.sub(r"(?<=\b\w)\.(?=\w\.)", "", t)          # «s.p.a.» → «spa.»
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def compatto(t: str) -> str:
    """Solo lettere e cifre maiuscole: per codici, targhe, matricole."""
    return re.sub(r"[^A-Z0-9]", "", senza_accenti(str(t or "")).upper())


# ─────────────────────────── identificativi forti ───────────────────────────

def partita_iva(v) -> str | None:
    """Le 11 cifre di una partita IVA italiana valida (cifra di controllo), o None."""
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) != 11 or d == "0" * 11:
        return None
    s = 0
    for i, c in enumerate(d[:10]):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        s += n
    return d if (10 - s % 10) % 10 == int(d[10]) else None


_CF = re.compile(r"^[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-EHLMPRST][0-9LMNPQRSTUV]{2}[A-Z]"
                 r"[0-9LMNPQRSTUV]{3}[A-Z]$")


def codice_fiscale(v) -> str | None:
    """Un codice fiscale di persona nella forma giusta (anche con omocodia), o None."""
    c = compatto(v)
    return c if _CF.match(c) else None


# ─────────────────────────── chiavi ───────────────────────────

def nome_ente(nome: str) -> str:
    t = _SOCIETA.sub(" ", piatto(nome))
    parole = [w for w in t.split() if w not in _PAROLE_VUOTE]
    return " ".join(parole)


def nome_persona(nome: str) -> str:
    t = _TITOLI.sub(" ", piatto(nome))
    return " ".join(sorted(w for w in t.split() if len(w) > 1 and w not in _PAROLE_VUOTE))


def nome_luogo(indirizzo: str) -> str:
    t = piatto(indirizzo)
    t = re.sub(r"\b\d{5}\b", " ", t)                     # il CAP non distingue
    t = re.sub(r"\bv\b", "via", t)
    t = re.sub(r"\b(?:p zza|pza|p za|p\s*le)\b", "piazza", t)
    t = re.sub(r"\bc so\b", "corso", t)
    t = re.sub(r"\b(?:italia|it|mi|rm|to|na|ge|bo|fi)\b$", " ", t)   # sigla in fondo
    return " ".join(t.split())


def chiavi(tipo: str, nome: str = "", **ids) -> list[str]:
    """Le chiavi di deduplicazione di un'entità, dalla più forte. Vuota = non si può
    riconoscere (niente nome né identificativo)."""
    out = []
    if tipo == "ente":
        p = partita_iva(ids.get("partita_iva")) or partita_iva(ids.get("codice_fiscale"))
        if p:
            out.append("piva:" + p)
        n = nome_ente(nome)
    elif tipo == "persona":
        cf = codice_fiscale(ids.get("codice_fiscale"))
        if cf:
            out.append("cf:" + cf)
        n = nome_persona(nome)
    elif tipo == "bene":
        c = compatto(ids.get("identificativo"))
        if len(c) >= 5:
            out.append("id:" + c)
        n = piatto(nome)
    elif tipo == "luogo":
        n = nome_luogo(nome)
    else:
        n = piatto(nome)
    if n:
        out.append("nome:" + n)
    return out


def forte(chiave: str) -> bool:
    return not chiave.startswith("nome:")


def simile(a: str, b: str, soglia: float = 0.92) -> bool:
    """Due chiavi di nome quasi uguali (refuso dell'OCR, una parola in più)."""
    a, b = a.removeprefix("nome:"), b.removeprefix("nome:")
    if min(len(a), len(b)) < 6:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= soglia


# ─────────────────────────── valori nel testo ───────────────────────────

_NUM = re.compile(r"(?<![\w,.])(\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|"
                  r"\d+(?:[.,]\d+)?)(?![\w])")


def numeri(testo: str) -> set[float]:
    """Tutti i numeri del testo, nelle forme italiane e inglesi («1.234,56», «84,50»,
    «97.20», «520»)."""
    out = set()
    for m in _NUM.finditer(testo or ""):
        s = m.group(1)
        cands = []
        if re.fullmatch(r"\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?", s):
            cands.append(re.sub(r"[.\s]", "", s).replace(",", "."))
        elif re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
            cands.append(s.replace(",", ""))
            cands.append(s.replace(".", "").replace(",", "."))
        else:
            cands.append(s.replace(",", "."))
        for c in cands:
            try:
                out.add(round(float(c), 2))
            except ValueError:
                pass
    return out


def importo_nel_testo(valore, testo: str, nums: set[float] | None = None) -> bool:
    try:
        v = round(float(valore), 2)
    except (TypeError, ValueError):
        return False
    nums = numeri(testo) if nums is None else nums
    return any(abs(v - n) < 0.005 for n in nums)


def data_iso(v) -> str | None:
    """«2026-10-15» se è una data vera, altrimenti None."""
    try:
        return datetime.date.fromisoformat(str(v or "")[:10]).isoformat()
    except ValueError:
        return None


_DATA_NUM = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4}|\d{2})\b")
_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATA_LETTERE = re.compile(r"\b(\d{1,2})(?:°|º)?\s+(" + "|".join(MESI) + r")\s+(\d{4})\b")
_MESE_ANNO = re.compile(r"\b(" + "|".join(MESI) + r")\s+(\d{4})\b")


def date(testo: str) -> tuple[set[str], set[str]]:
    """(date complete ISO, mesi «AAAA-MM») che compaiono nel testo."""
    t = senza_accenti(testo or "").lower()
    giorni, mesi = set(), set()

    def add(y, m, d):
        try:
            giorni.add(datetime.date(y, m, d).isoformat())
        except ValueError:
            pass
    for d, m, y in _DATA_NUM.findall(t):
        y = int(y) + (2000 if len(y) == 2 and int(y) < 70 else 1900 if len(y) == 2 else 0)
        add(y, int(m), int(d))
    for y, m, d in _DATA_ISO.findall(t):
        add(int(y), int(m), int(d))
    for d, mese, y in _DATA_LETTERE.findall(t):
        add(int(y), MESI.index(mese) + 1, int(d))
    for mese, y in _MESE_ANNO.findall(t):
        mesi.add(f"{y}-{MESI.index(mese) + 1:02d}")
    mesi |= {g[:7] for g in giorni}
    return giorni, mesi


def codice_nel_testo(codice, testo: str) -> bool:
    c = compatto(codice)
    return len(c) >= 3 and c in compatto(testo)


def nome_nel_testo(nome, testo: str) -> bool:
    """Tutte le parole significative del nome compaiono nel testo (in qualunque ordine:
    «BIANCHI MARIO»)."""
    parole = [w for w in piatto(nome).split() if len(w) > 1 and w not in _PAROLE_VUOTE]
    if not parole:
        return False
    t = f" {piatto(testo)} "
    return all(f" {w} " in t for w in parole)


# ─────────────────────────── come si dice ───────────────────────────

def euro(v: float) -> str:
    """84.5 → «84,50 euro»; 520 → «520 euro»; 1234.5 → «1.234,50 euro»."""
    v = round(float(v), 2)
    intero = int(abs(v))
    cent = int(round((abs(v) - intero) * 100))
    s = f"{intero:,}".replace(",", ".")
    if cent:
        s += f",{cent:02d}"
    return ("meno " if v < 0 else "") + s + " euro"


def data_detta(iso: str, anno: bool = True) -> str:
    """«2026-10-15» → «15 ottobre 2026»."""
    d = datetime.date.fromisoformat(iso[:10])
    return f"{d.day} {MESI[d.month - 1]}" + (f" {d.year}" if anno else "")


def mese_detto(iso: str) -> str:
    d = datetime.date.fromisoformat(iso[:10])
    return f"{MESI[d.month - 1]} {d.year}"
