"""
Modelli di documento (template): l'aggancio, non il motore completo (02/10/2026).

Un modello è un file JSON in `agenti_modelli` (predefinita: Documenti\\Calliope\\Modelli):

    {"nome": "preventivo", "titolo": "Preventivo su carta intestata", "formato": "word",
     "campi": {"cliente": {"descrizione": "nome del cliente", "tipo": "testo",
                           "obbligatorio": true},
               "voci": {"descrizione": "righe: descrizione e importo", "tipo": "tabella"},
               "note": {"tipo": "testo", "obbligatorio": false}},
     "documento": {"titolo": "Preventivo per {{cliente}}",
                   "blocchi": [{"tipo": "paragrafo", "testo": "Spett.le {{cliente}}"},
                               {"tipo": "tabella", "colonne": ["Voce", "Importo (€)"],
                                "righe": "{{voci}}", "totale": true}]}}

Il flusso è quello della ricerca del 02/10 (§4.7): **dal modello lo schema JSON dei campi**
(`schema`), il modello grande **riempie lo schema** (null per ciò che non sa: non inventa),
il codice controlla i campi obbligatori (`mancanti`) e **compila** il documento
(`compila`: segnaposto `{{campo}}` dentro i blocchi del formato di calliope/documenti, poi
la stessa validazione, lo stesso render e la stessa consegna). Il modello non tocca mai la
formattazione.

Cosa manca (lavoro successivo): i modelli `.docx` veri con docxtpl (carta intestata,
loghi), che avranno la stessa interfaccia (`campi`, `schema`, `mancanti`, `compila` → byte).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TIPI = {"testo": {"type": "string"}, "numero": {"type": "number"},
        "data": {"type": "string"}, "elenco": {"type": "array", "items": {"type": "string"}},
        "tabella": {"type": "array", "items": {"type": "array",
                                               "items": {"anyOf": [{"type": "string"},
                                                                   {"type": "number"}]}}}}
_SEGNAPOSTO = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)\s*\}\}")


class ModelloNonValido(Exception):
    pass


@dataclass
class Campo:
    nome: str
    descrizione: str = ""
    tipo: str = "testo"
    obbligatorio: bool = True


@dataclass
class Modello:
    nome: str
    titolo: str
    formato: str
    campi: dict[str, Campo]
    documento: dict
    descrizione: str = ""
    file: str = ""
    avvisi: list[str] = field(default_factory=list)

    def schema(self) -> dict:
        """Lo schema JSON per gli output strutturati di Ollama: ogni campo può essere null
        (il dato non è stato detto)."""
        props = {n: {"anyOf": [TIPI[c.tipo], {"type": "null"}]} for n, c in self.campi.items()}
        return {"type": "object", "properties": props, "required": list(self.campi)}

    def descrivi_campi(self) -> str:
        return "; ".join(f"{n} ({c.tipo}{', obbligatorio' if c.obbligatorio else ''})"
                         + (f": {c.descrizione}" if c.descrizione else "")
                         for n, c in self.campi.items())

    def mancanti(self, dati: dict) -> list[str]:
        out = []
        for n, c in self.campi.items():
            v = (dati or {}).get(n)
            if c.obbligatorio and (v is None or v == "" or v == []):
                out.append(n)
        return out

    def compila(self, dati: dict) -> dict:
        """Il documento nel formato di calliope/documenti, con i dati al posto dei
        segnaposto. Un valore che è tutto un segnaposto («{{voci}}») diventa il dato così
        com'è (elenco, tabella); dentro un testo diventa testo. Un campo facoltativo vuoto
        diventa «» (e un blocco rimasto vuoto si toglie)."""
        dati = dati or {}

        def valore(nome):
            v = dati.get(nome)
            return "" if v is None else v

        def sost(x):
            if isinstance(x, str):
                m = _SEGNAPOSTO.fullmatch(x.strip())
                if m and m.group(1) in self.campi:
                    return valore(m.group(1))
                return _SEGNAPOSTO.sub(lambda mm: _testo(valore(mm.group(1)))
                                       if mm.group(1) in self.campi else mm.group(0), x)
            if isinstance(x, list):
                return [sost(v) for v in x]
            if isinstance(x, dict):
                return {k: sost(v) for k, v in x.items()}
            return x
        doc = sost(self.documento)
        for key in ("blocchi",):
            if isinstance(doc.get(key), list):
                doc[key] = [b for b in doc[key] if not _vuoto(b)]
        return doc


def _testo(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, list):
        return ", ".join(_testo(x) for x in v)
    return str(v)


def _vuoto(b) -> bool:
    if not isinstance(b, dict):
        return False
    t = b.get("tipo")
    if t in ("titolo", "paragrafo"):
        return not str(b.get("testo") or "").strip()
    if t == "elenco":
        return not b.get("voci")
    if t == "tabella":
        return not b.get("righe")
    return False


def leggi_modello(path: Path) -> Modello:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ModelloNonValido(f"{Path(path).name} non si legge: {type(e).__name__}") from None
    if not isinstance(data, dict):
        raise ModelloNonValido(f"{Path(path).name}: serve un oggetto JSON")
    nome = str(data.get("nome") or Path(path).stem).strip()
    formato = str(data.get("formato") or "word").strip().lower()
    if formato not in ("word", "pdf", "excel"):
        raise ModelloNonValido(f"{nome}: formato {formato!r} sconosciuto")
    campi = {}
    for n, c in (data.get("campi") or {}).items():
        if not re.fullmatch(r"[a-zA-Z_]\w*", str(n)):
            raise ModelloNonValido(f"{nome}: nome di campo non valido {n!r}")
        c = c if isinstance(c, dict) else {"descrizione": str(c)}
        tipo = str(c.get("tipo") or "testo")
        if tipo not in TIPI:
            raise ModelloNonValido(f"{nome}: tipo {tipo!r} del campo {n} sconosciuto")
        campi[str(n)] = Campo(str(n), str(c.get("descrizione") or ""), tipo,
                              bool(c.get("obbligatorio", True)))
    if not campi:
        raise ModelloNonValido(f"{nome}: nessun campo")
    doc = data.get("documento")
    if not isinstance(doc, dict):
        raise ModelloNonValido(f"{nome}: manca «documento»")
    usati = set(_SEGNAPOSTO.findall(json.dumps(doc, ensure_ascii=False)))
    avvisi = [f"campo {n} non usato nel documento" for n in campi if n not in usati]
    avvisi += [f"segnaposto {{{{{u}}}}} senza campo" for u in sorted(usati - set(campi))]
    return Modello(nome, str(data.get("titolo") or nome), formato, campi, doc,
                   str(data.get("descrizione") or ""), str(path), avvisi)


def carica_modelli(cartella) -> dict[str, Modello]:
    """I modelli della cartella; quelli rovinati si saltano (il chiamante può dirlo)."""
    out = {}
    if not cartella:
        return out
    p = Path(cartella)
    if not p.is_dir():
        return out
    for f in sorted(p.glob("*.json")):
        try:
            m = leggi_modello(f)
        except ModelloNonValido:
            continue
        out[m.nome] = m
    return out
