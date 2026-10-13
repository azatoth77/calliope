"""
Titoli e sommari dei feed pronti per il modello della voce (13/10/2026, ricerca del 13/10
§ 3.1). Il testo resta un dato non fidato: qui si cambia solo la **forma**, mai il senso
(principio 10: conversioni della forma, ognuna con il suo nome e i suoi casi contrari in
prove/prova_notizie.py). I nomi delle regole scattate restano sulla voce e, quando la voce
viene detta, vanno nel registro dei turni.

- `notizie_titolo_virgolette`: virgolette dritte, curve e apici usati come virgolette
  diventano «» (mai l'apostrofo: «dell'Irpef» resta);
- `notizie_titolo_agenzia`: le marcature d'agenzia «++ … ++» e «>ANSA-FOCUS/» in testa;
- `notizie_titolo_marcatore`: VIDEO, FOTO, LIVE, DIRETTA in maiuscolo, solo in testa o in
  coda (mai in mezzo, mai «Il video del ministro» o «Live Aid»);
- `notizie_titolo_doppio`: «… in diretta | Il fatto» → il fatto; «Il fatto | Rubrica» → il fatto;
- `notizie_titolo_troncato`: un titolo tagliato con «…» che è l'inizio del sommario (AGI)
  diventa la prima frase del sommario; un «…» voluto resta;
- `notizie_sommario_coda`: la coda «The post … appeared first on …» (WordPress);
- `notizie_sommario_sigla`: la testata in testa al sommario («AGI - »), mai una città
  («Roma - »);
- `notizie_non_notizia`: le voci che non sono notizie (episodi di podcast e newsletter dal
  link, «Puntata del…», le strisce): non entrano nell'indice. Un link /video/ di Rainews è una
  notizia vera e resta.
"""
from __future__ import annotations

import re

_MARCATORI = r"(?:VIDEO|FOTO|LIVE|DIRETTA|GALLERY|AUDIO|PODCAST|IL VIDEO|LE FOTO|LA DIRETTA)"
_AGENZIA_PIU = re.compile(r"^\s*\+\+\s*(.*?)\s*\+\+\s*$")
_AGENZIA_SIGLA = re.compile(r"^>?\s*[A-Z]{2,}-[A-Z]{2,}/\s*")
_MARC_FINE = re.compile(r"[\s.,:;–—-]*[(\[]?\b" + _MARCATORI + r"\b[)\]]?\s*$")
_MARC_TESTA = re.compile(r"^[(\[]?" + _MARCATORI + r"[)\]]?\s*[:|–—-]\s*")
_DIRETTA = re.compile(r"\b(?:in diretta|diretta|live|ultime notizie|ultim'ora|aggiornamenti)\b",
                      re.I)
_APICI = re.compile(r"(^|[\s:,(])'([^'\n]{3,}?)'(?=$|[\s.,:;)?!])")
_DRITTE = re.compile(r"[\"“”„]([^\"“”„\n]+)[\"“”„]")
_TRONCATO = re.compile(r"(?:\.\.\.|…)\s*$")
_CODA_WP = re.compile(r"\s*(?:The post|L'articolo)\s.{1,300}?\s(?:appeared first on|"
                      r"proviene da)\s.{1,120}$", re.I | re.S)
_NON_NOTIZIA_LINK = re.compile(r"/(?:episodes?|newsletters?|podcasts?)/", re.I)
_NON_NOTIZIA_TITOLO = re.compile(
    r"^(?:puntata del\b|peanuts\b|oroscopo\b|tg\s?\w*(?:\s\w+){0,3}\s+del\s+\d{1,2}[/.]\d{1,2})",
    re.I)


def non_notizia(titolo: str, link: str) -> bool:
    """La voce non è una notizia (podcast, newsletter, puntate, strisce)."""
    return bool(_NON_NOTIZIA_LINK.search(link or "")
                or _NON_NOTIZIA_TITOLO.search((titolo or "").strip()))


def virgolette(t: str) -> str:
    t2 = _APICI.sub(lambda m: f"{m.group(1)}«{m.group(2)}»", t)
    return _DRITTE.sub(lambda m: f"«{m.group(1)}»", t2)


def titolo_per_voce(titolo: str, sommario: str = "") -> tuple[str, list[str]]:
    """(titolo pulito, regole scattate)."""
    t, regole = str(titolo or "").strip(), []
    m = _AGENZIA_PIU.match(t)
    if m and m.group(1):
        t = m.group(1)
        regole.append("notizie_titolo_agenzia")
    n = _AGENZIA_SIGLA.sub("", t)
    if n != t and n:
        t = n
        if "notizie_titolo_agenzia" not in regole:
            regole.append("notizie_titolo_agenzia")
    if " | " in t:
        prima, _, dopo = t.partition(" | ")
        scelto = dopo if _DIRETTA.search(prima) and len(dopo) >= 15 else prima
        if scelto.strip():
            t = scelto.strip()
            regole.append("notizie_titolo_doppio")
    n = _MARC_TESTA.sub("", _MARC_FINE.sub("", t)).strip()
    if n != t and len(n) >= 10:
        t = n
        regole.append("notizie_titolo_marcatore")
    n = virgolette(t)
    if n != t:
        t = n
        regole.append("notizie_titolo_virgolette")
    if _TRONCATO.search(t):
        inizio = _TRONCATO.sub("", t).strip()
        s = str(sommario or "").strip()
        if len(inizio) >= 15 and s.lower().startswith(inizio.lower()[:max(15, len(inizio) - 3)]):
            frase = re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0].strip()
            if len(frase) <= 220:
                t = frase.rstrip(".")
                regole.append("notizie_titolo_troncato")
    return t.strip(" .,;:-–"), regole


def sommario_per_voce(sommario: str, titolo: str, testata: str) -> tuple[str, list[str]]:
    """(sommario pulito, regole): senza la coda di WordPress, senza la sigla della testata in
    testa, vuoto se ripete il titolo."""
    s, regole = str(sommario or "").strip(), []
    n = _CODA_WP.sub("", s).strip()
    if n != s:
        s = n
        regole.append("notizie_sommario_coda")
    if testata:
        sigla = re.compile(r"^\(?" + re.escape(testata) + r"\)?\s*[-–—]\s+", re.I)
        n = sigla.sub("", s)
        if n != s:
            s = n
            regole.append("notizie_sommario_sigla")
    if s and titolo and re.sub(r"\W", "", s.lower()) == re.sub(r"\W", "", titolo.lower()):
        s = ""
    return s, regole
