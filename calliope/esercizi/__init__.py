"""
Esercizi nativi di Calliope, generati al momento (08/10/2026, decisioni di Dario del 07/10;
progetto in docs/ricerche/2026-10-08-esercizi.md, area minori).

Pilota: matematica (operazioni, frazioni, problemi, potenze, equazioni di primo grado) e
italiano (analisi grammaticale, analisi logica di base), dalle elementari alle superiori.

- `matematica.py`, `italiano.py`: i generatori, deterministici dal seme, e la correzione;
- `numeri.py`: numeri e frazioni detti a voce e scritti;
- `verifica.py`: Wikizionario e secondo modello per gli esercizi linguistici;
- `registro.py`: tentativi, segnalazioni e banco degli esercizi controllati in memoria.db;
- `sessione.py`: il servizio (una sessione per persona, voce e scheda insieme, regola dei
  tentativi, avvisi e riepilogo ai tutori);
- il tool a voce è in `calliope/tools/esercizi.py`, la scheda in `schermi/pagina/schermo.js`.

Come si aggiunge una materia: un modulo con `MATERIA`, `ARGOMENTI` (nome, alias, classi),
`genera(argomento, livello, seme)`, `controlla(es, risposta)` e `livello_per(argomento,
classe)`, aggiunto a `MATERIE` qui sotto; il tipo di verifica (calcolata, linguistica,
fattuale) decide quali controlli fa `Servizio._verifica`.
"""

from __future__ import annotations

import re
import unicodedata

from . import italiano, matematica
from .modello import Classe, Esercizio, Esito

MATERIE = {"matematica": matematica, "italiano": italiano}
_ALIAS_MATERIE = {"matematica": ("matematic", "aritmetic", "conti", "algebra", "geometri"),
                  "italiano": ("italian", "grammatic", "analisi")}


def _semplice(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def argomenti(materia: str | None = None) -> dict[str, tuple[str, dict]]:
    """{argomento: (materia, scheda dell'argomento)}."""
    out = {}
    for m, mod in MATERIE.items():
        if materia and m != materia:
            continue
        for a, d in mod.ARGOMENTI.items():
            out[a] = (m, d)
    return out


def nome_argomento(argomento: str) -> str:
    for mod in MATERIE.values():
        if argomento in mod.ARGOMENTI:
            return mod.ARGOMENTI[argomento]["nome"]
    return str(argomento or "").replace("_", " ")


def materia_da_testo(testo: str) -> str | None:
    t = _semplice(testo)
    if not t:
        return None
    if t in MATERIE:
        return t
    for m, alias in _ALIAS_MATERIE.items():
        if any(a in t for a in alias):
            return m
    return None


def argomento_da_testo(testo: str, materia: str | None = None) -> str | None:
    """L'argomento chiesto («le frazioni», «tabelline», «analisi logica»), o None. Conversione
    di forma di una scelta già fatta dal modello (principio 10): il modello passa il nome."""
    t = _semplice(testo).replace("_", " ")
    if not t:
        return None
    cand = argomenti(materia)
    k = t.replace(" ", "_")
    if k in cand:
        return k
    # Prima i nomi interi («analisi logica»), poi gli alias
    for a, (_, d) in cand.items():
        if _semplice(d["nome"]) in t or a.replace("_", " ") in t:
            return a
    trovati = [a for a, (_, d) in cand.items()
               if any(re.search(rf"\b{re.escape(x)}", t) for x in d["alias"])]
    return trovati[0] if len(trovati) == 1 else None


_ORDINALI = {"prima": 1, "primo": 1, "seconda": 2, "secondo": 2, "terza": 3, "terzo": 3,
             "quarta": 4, "quarto": 4, "quinta": 5, "quinto": 5}


def classe_da_testo(testo: str) -> Classe | None:
    """«terza elementare», «3ª media», «primo superiore», «seconda liceo», «elementari»."""
    t = _semplice(testo)
    if not t:
        return None
    scuola = ("elementari" if re.search(r"\b(element|primaria)", t) else
              "medie" if re.search(r"\b(medi|secondaria di primo)", t) else
              "superiori" if re.search(r"\b(superior|liceo|istituto|tecnico|biennio|triennio)", t)
              else None)
    m = re.search(r"\b(\d)\s*[a°ªo]?\b", t)
    anno = int(m.group(1)) if m else next((v for k, v in _ORDINALI.items()
                                           if re.search(rf"\b{k}\b", t)), None)
    if scuola is None:
        return None
    if anno is None:
        anno = {"elementari": 3, "medie": 2, "superiori": 1}[scuola]
    from .modello import SCUOLE
    return Classe(scuola, anno) if 1 <= anno <= SCUOLE[scuola] else None


def classe_da_eta(anni: int | None) -> Classe | None:
    """La classe più probabile per l'età (6 anni: prima elementare; 14: prima superiore)."""
    if anni is None:
        return None
    return Classe.da_indice(int(anni) - 5)


def adatto(argomento: str, classe: Classe) -> bool:
    _, d = argomenti()[argomento]
    da, a = d["classi"]
    return da.indice <= classe.indice <= a.indice


def genera(argomento: str, livello: int, seme: int) -> Esercizio:
    materia, _ = argomenti()[argomento]
    return MATERIE[materia].genera(argomento, livello, seme)


def controlla(es: Esercizio, risposta) -> Esito:
    return MATERIE[es.materia].controlla(es, risposta)


def livello_per(argomento: str, classe: Classe) -> int:
    materia, _ = argomenti()[argomento]
    return MATERIE[materia].livello_per(argomento, classe)


__all__ = ["MATERIE", "Classe", "Esercizio", "Esito", "argomenti", "nome_argomento",
           "materia_da_testo", "argomento_da_testo", "classe_da_testo", "classe_da_eta",
           "adatto", "genera", "controlla", "livello_per"]
