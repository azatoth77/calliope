"""
Il ripasso da ascoltare dello Studio (31/10/2026, passo 9, issue #249, epic #251, decisione 0035
punto 42; progetto § 5, Studio 6, § 5.10; decisione 7 del 27/10: Piper con le voci italiane).

**Il testo lo compone il codice, senza modello.** Un copione a parti, da ciò che la persona ha
già confermato:
- le **pagine** degli argomenti del piano (tenuti e aggiunti, nell'ordine dell'elenco): il testo
  letto (passo 4.3), un dato non fidato, ripulito per la voce (`frasi_pagina`): via i numeri di
  pagina e di paragrafo, il markdown, i `[[ ]]`; formule, sigle, simboli e numeri romani a parole
  (`pronuncia.per_ripasso`); mai le frasi con un indirizzo, col nome di Calliope, gli annunci della
  scuola e, sulle pagine con «ISTRUZIONI: sì», gli ordini a un assistente (al loro posto una frase
  del codice). Un argomento lungo si divide in più parti (`PARTE_MAX_CAR`);
- le **carte** attive del piano: «Domanda», la domanda, `PAUSA_CARTA_S` per pensare, «Risposta»,
  la risposta.
Il riassunto scritto dal lettore (qwen3.6 in ombra, con la guardia e i controlli) è per una
seconda parte del passo: un errore detto con sicurezza a voce mentre si ripassa è il più difficile
da accorgersene (analisi nella #249).

**Due voci di Piper.** Le frasi del codice (la parte, le pagine, «Domanda»…) nella voce di
Calliope; il materiale nella «voce del libro» (`studio_ascolta_voce`). Chi ascolta distingue
sempre ciò che dice Calliope da ciò che dice la pagina, e nessuna frase del codice contiene testo
delle pagine (niente frasi pronte con testo non fidato).

**A voce** (`leggi`, chiamata dal ciclo dopo la risposta che ha chiamato `studio_ascolta`): a
pezzi di `PEZZO_FRASI`, ognuno in un turno della voce suo (`Uscita.turno_lettura`, `leggi`): fuori
dalla conversazione, dagli eventi e dallo schermo. Prima di ogni pezzo `controlla()` (una prova
aperta, gli orari, lo Studio spento, un annuncio in coda) può fermare la lettura. Le frasi sentite
per intero (`played`, anche dal satellite) danno la posizione, che il servizio tiene in memoria
`RIPRENDI_S` per «riprendi» e «ripeti».

**Sullo schermo** (`Sintesi`): il WAV di una parte, preparato in un thread che cede alla voce dal
vivo, in `studio_cartella/ascolta/<verifica>/<firma>-<parte>.wav`: una cache del testo, tenuta
`studio_ascolta_giorni` dall'ultimo ascolto e mai oltre la verifica (`dati.cancella`).

Durante una prova aperta della verifica il ripasso si blocca per tutti (l'audio si sente nella
stanza). Solo libreria standard (e le voci di Piper che ha già lo Speaker).
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import time
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path

from . import dati as D

# ─────────────────────────── soglie (iniziali, prudenti: analisi nella #249) ───────────────────
PARTE_MAX_CAR = 6000          # una parte al più (~7 minuti a 15 caratteri al secondo)
FRASE_MAX_CAR = 280           # una frase più lunga si taglia su «;» e «,»
PEZZO_FRASI = 3               # le frasi di un pezzo della voce: i controlli fra un pezzo e l'altro
RIPRENDI_S = 2 * 3600         # la posizione per «riprendi» resta in memoria tanto
PAUSA_CARTA_S = 4.0           # i secondi per pensare fra la domanda di una carta e la risposta
PAUSA_FRASE_S = 0.35          # nel file: fra due frasi
PAUSA_PARAGRAFO_S = 0.8       # nel file: fra due paragrafi
PAUSA_PARTE_S = 1.2           # nel file: dopo la frase della parte
CARATTERI_AL_SECONDO = 15.0   # la stima della durata prima del file (la taratura della voce)
VOCE_FERMA_S = 1.5            # la sintesi per lo schermo aspetta la voce dal vivo ferma da tanto
VOCE_ATTESA_MAX_S = 60.0      # …ma al più tanto per frase
CARTELLA = "ascolta"
COSE = ("oggi", "tutto", "argomento", "carte")
CALLIOPE, LIBRO, PAUSA = "calliope", "libro", "pausa"
MODI = ("spenta", "attiva")

# Le frasi del codice (mai testo delle pagine)
MESSAGGIO_SALTATO = "Qui c'è un messaggio per un assistente: lo salto."
INDIRIZZO_SALTATO = "Qui c'è un indirizzo: non lo leggo."
FINE = "Il ripasso è finito."
CARTE_INTRO = ("Prima la domanda, poi qualche secondo per pensare, poi la risposta.")


def modo(cfg) -> str:
    m = str(getattr(cfg, "studio_ascolta", "attiva") or "spenta").strip().lower()
    return m if m in MODI else "spenta"


@dataclass
class Voce:
    """Un pezzo del copione: una frase di Calliope (`calliope`, scritta dal codice), una frase
    del materiale (`libro`, un dato) o un silenzio (`pausa`)."""
    tipo: str
    testo: str
    parte: int
    par: int
    secondi: float = 0.0

    def per_firma(self):
        return [self.tipo, self.testo, round(self.secondi, 2)]


# ─────────────────────────── il testo di una pagina per la voce ───────────────────────────
_CONTROLLO = re.compile(r"[\x00-\x09\x0b-\x1f\x7f ​-‏‪-‮⁦-⁩]")
_NUMERO_SOLO = re.compile(r"^\s*(?:p(?:ag)?\.?\s*)?(\d{1,4}|[ivxlcdm]{1,6})\s*$", re.I)
_PARAGRAFO_NUM = re.compile(r"^\s*\d{1,3}(?:\.\d{1,3})+\.?\s+")
_PUNTO_ELENCO = re.compile(r"^\s*(?:[-*•·▪◦>]+\s+|#{1,6}\s*|\d{1,2}[.)]\s+|[a-z][.)]\s+)")
_SEPARATORE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
_MARKDOWN = re.compile(r"\*\*|__|`|~~")
_FINE_FRASE = re.compile(r"[.!?…:;»”\")]\s*$")
_ABBREV = ("a.C.", "d.C.", "ecc.", "es.", "pag.", "pagg.", "fig.", "cap.", "sec.", "vol.",
           "n.", "p.", "art.", "S.", "sig.", "dott.", "prof.", "ca.")
_TAGLIO = re.compile(r"(?<=[.!?…])\s+(?=[«\"“(]?[A-ZÀ-Ý0-9])")


def _numero_solo(r: str) -> bool:
    """Una riga col solo numero di pagina («112», «pag. 12», «xiv»: un numero romano valido)."""
    m = _NUMERO_SOLO.match(r)
    if not m:
        return False
    x = m.group(1)
    if x.isdigit():
        return True
    from ..pronuncia import _romano
    return _romano(x.upper()) is not None


def _pulisci_riga(r: str) -> str:
    r = _MARKDOWN.sub("", r)
    if r.strip().startswith("|") or r.count("|") >= 2:
        r = ", ".join(c.strip() for c in r.strip().strip("|").split("|") if c.strip())
    r = _PARAGRAFO_NUM.sub("", r)
    r = _PUNTO_ELENCO.sub("", r)
    return " ".join(r.split())


def paragrafi(testo) -> list[str]:
    """Il testo letto di una pagina diviso in paragrafi per la voce: senza i numeri di pagina, i
    numeri dei paragrafi in testa («7.1 »), i segni dell'elenco e del markdown, le tabelle a righe;
    le parole spezzate a fine riga ricucite; i titoli (una riga corta senza punto) col punto."""
    t = unicodedata.normalize("NFC", str(testo or "")).replace("\r", "\n")
    t = _CONTROLLO.sub(" ", t).replace("[[", " ").replace("]]", " ").replace("[?]", " ")
    righe = []                     # (testo, marcata: un elemento d'elenco, un titolo, una tabella)
    for r in t.split("\n"):
        if _SEPARATORE.match(r) or _numero_solo(r):
            continue
        marcata = bool(_PUNTO_ELENCO.match(r) or _PARAGRAFO_NUM.match(r) or r.count("|") >= 2)
        r = _pulisci_riga(r)
        if r:
            righe.append((r, marcata))
    out: list[str] = []

    def chiudi(p: str):
        # Un titolo o una riga che finisce senza punto: un paragrafo suo, col punto
        p = p.strip()
        if p:
            out.append(p if _FINE_FRASE.search(p) else p.rstrip(",") + ".")

    corrente = ""
    for i, (r, marcata) in enumerate(righe):
        dopo, dopo_m = righe[i + 1] if i + 1 < len(righe) else ("", False)
        if corrente and not marcata and corrente.endswith("-") and r[:1].islower():
            corrente = corrente[:-1] + r
        elif corrente and not marcata and not _FINE_FRASE.search(corrente) and r[:1].islower():
            corrente += " " + r
        else:
            chiudi(corrente)
            corrente = r
        fine = bool(_FINE_FRASE.search(corrente))
        if not dopo or dopo_m or (not fine and (dopo[:1].isupper() or dopo[:1].isdigit())) \
                or (fine and not dopo[:1].islower()):
            chiudi(corrente)
            corrente = ""
    chiudi(corrente)
    return [p for p in out if re.search(r"\w", p)]


def _taglia(frase: str) -> list[str]:
    """Una frase oltre `FRASE_MAX_CAR` divisa su «;», poi su «,» vicino al mezzo."""
    if len(frase) <= FRASE_MAX_CAR:
        return [frase]
    for sep in ("; ", ", ", " "):
        i = frase.rfind(sep, 0, FRASE_MAX_CAR)
        if i > FRASE_MAX_CAR // 3:
            testa = frase[:i + (1 if sep != " " else 0)].strip()
            return [testa] + _taglia(frase[i + len(sep):].strip())
    return [frase[:FRASE_MAX_CAR]] + _taglia(frase[FRASE_MAX_CAR:])


def frasi(paragrafo: str) -> list[str]:
    """Un paragrafo in frasi (senza tagliare dopo «a.C.», «pag.», «fig.»…)."""
    pezzi, corrente = [], ""
    for p in _TAGLIO.split(paragrafo):
        corrente = f"{corrente} {p}".strip() if corrente else p
        if not corrente.endswith(_ABBREV):
            pezzi.append(corrente)
            corrente = ""
    if corrente:
        pezzi.append(corrente)
    out = []
    for p in pezzi:
        out += _taglia(p)
    return [f for f in out if f.strip()]


# Un messaggio rivolto a un assistente dentro una pagina («NOTA PER L'ASSISTENTE: ignora le regole
# precedenti…», la pagina ostile del banco): su tutte le pagine, non solo su quelle con
# «ISTRUZIONI: sì» (la lettura può non accorgersene). Forme strette: «l'assistente di laboratorio»
# resta
_MESSAGGIO = re.compile(
    r"\b(?:per|all?)\s+l['’]\s*assistente\b|\bassistente\s+(?:vocale|virtuale|digitale)\b|"
    r"\bintelligenza artificiale\b.{0,30}\b(?:ignora|rispondi|scrivi|di['’]|dì)\b|"
    r"\bignora\s+(?:le|tutte\s+le|ogni)\s+(?:regole|istruzioni)\b|"
    r"\b(?:regole|istruzioni)\s+precedenti\b", re.I)


def scarto(frase: str, nomi, istruzioni: bool) -> str | None:
    """Perché una frase del materiale non si dice (None: si dice): «indirizzo» (URL, email:
    principio 5), «nome» (il nome di Calliope: la voce si interromperebbe da sola, ed è un ordine
    rivolto a lei), «messaggio» (rivolto a un assistente), «annuncio» («verifica annullata») e,
    sulle pagine con «ISTRUZIONI: sì», «ordine» (comincia con un ordine a un assistente: sulle
    altre pagine «Scrivi…», «Rispondi…» sono gli esercizi). Forma, non significato (principio 10)."""
    from . import argomenti as A
    if A._INDIRIZZO.search(frase):
        return "indirizzo"
    low = frase.lower()
    if any(n and re.search(rf"(?<!\w){re.escape(str(n).lower())}(?!\w)", low) for n in nomi):
        return "nome"
    if _MESSAGGIO.search(frase):
        return "messaggio"
    if A._ANNUNCIO.search(frase):
        return "annuncio"
    if istruzioni and A._ORDINE.search(frase):
        return "ordine"
    return None


def frasi_pagina(testo, nomi=(), istruzioni: bool = False) -> tuple[list[list[str]], dict]:
    """([[frase per la voce, …] per paragrafo], {motivo: quante saltate})."""
    from ..pronuncia import per_ripasso
    out, saltate = [], {}
    for p in paragrafi(testo):
        par = []
        for f in frasi(p):
            m = scarto(f, nomi, istruzioni)
            if m is not None:
                saltate[m] = saltate.get(m, 0) + 1
                continue
            detta = per_ripasso(f)
            if re.search(r"\w", detta):
                par.append(detta)
        if par:
            out.append(par)
    return out, saltate


# ─────────────────────────── il copione ───────────────────────────
def _etichetta(p: dict, i: int) -> str:
    """Il numero di una pagina per la voce di Calliope: il numero stampato solo se è fatto di
    cifre (viene dall'OCR: PR #317), altrimenti «P3» scritto dal codice."""
    from . import piano as P
    n = P.numero_pagina(p.get("numero"))
    return str(n) if n is not None else f"P{i}"


def _pagine_dette(etichette: list[str]) -> str:
    if not etichette:
        return ""
    if len(etichette) == 1:
        return f"pagina {etichette[0]}"
    return "pagine " + ", ".join(etichette[:-1]) + " e " + etichette[-1]


def _durata(caratteri: int, pause: float = 0.0) -> int:
    return int(round(caratteri / CARATTERI_AL_SECONDO + pause))


class Copione:
    """Le voci del ripasso di una verifica, divise in parti, con la firma."""

    def __init__(self, cosa: str):
        self.cosa = cosa
        self.voci: list[Voce] = []
        self.parti: list[dict] = []
        self.saltate: dict = {}
        self._par = 0

    def nuovo_par(self) -> int:
        self._par += 1
        return self._par

    @property
    def firma(self) -> str:
        righe = [self.cosa, [v.per_firma() for v in self.voci]]
        return hashlib.sha256(json.dumps(righe, ensure_ascii=False).encode()).hexdigest()[:16]

    def inizio_parte(self, n: int) -> int:
        return next((i for i, v in enumerate(self.voci) if v.parte == n), 0)

    def secondi(self, parte: int | None = None) -> int:
        voci = [v for v in self.voci if parte is None or v.parte == parte]
        return _durata(sum(len(v.testo) for v in voci if v.tipo != PAUSA),
                       sum(v.secondi for v in voci if v.tipo == PAUSA))


def _gruppi_argomenti(args: list[dict], pagine: list[dict], solo: set | None = None) -> list:
    """[(argomento, [pagine]) …]: ogni pagina al primo argomento che la cita, nell'ordine delle
    pagine; `solo`: gli id delle pagine da tenere (oggi)."""
    per_id = {p["id"]: p for p in pagine}
    viste, out = set(), []
    for a in args:
        mie = [per_id[x] for x in a["pagine"] if x in per_id and x not in viste
               and (solo is None or x in solo)]
        mie.sort(key=lambda p: (p["ordine"], p["id"]))
        viste.update(p["id"] for p in mie)
        if mie:
            out.append((a, mie))
    return out


def componi(args: list[dict], pagine: list[dict], carte: list[dict], cosa: str,
            nomi=(), solo_pagine: set | None = None, con_carte: bool = True) -> Copione:
    """Il copione: `args` gli argomenti del piano numerati ({id, numero, titolo, pagine}),
    `pagine` tutte quelle della verifica (le tolte escluse), `carte` le attive del piano."""
    cp = Copione(cosa)
    indici = {p["id"]: i for i, p in enumerate(pagine, 1)}
    blocchi = []                   # [(tipo, argomento, [(etichetta, paragrafi)…]), …]
    for a, mie in _gruppi_argomenti(args, pagine, solo_pagine):
        corrente, car = [], 0
        for p in mie:
            et = _etichetta(p, indici[p["id"]])
            if p.get("stato") != "letta" or not str(p.get("testo") or "").strip():
                pars, salt = None, {}
            else:
                istr = "istruzioni" in D.da_j(p.get("avvisi"))
                pars, salt = frasi_pagina(p["testo"], nomi, istr)
            for k, n in salt.items():
                cp.saltate[k] = cp.saltate.get(k, 0) + n
            lung = sum(len(f) for par in (pars or []) for f in par)
            if corrente and car + lung > PARTE_MAX_CAR:
                blocchi.append(("argomento", a, corrente))
                corrente, car = [], 0
            corrente.append((et, pars, salt))
            car += lung
        if corrente:
            blocchi.append(("argomento", a, corrente))
    if con_carte and carte:
        blocchi.append(("carte", None, carte))
    tot = len(blocchi)
    visti: dict = {}
    for n, (tipo, a, cont) in enumerate(blocchi, 1):
        inizio = len(cp.voci)
        par = cp.nuovo_par()
        if tipo == "carte":
            cp.voci.append(Voce(CALLIOPE, f"Parte {n} di {tot}: le carte. {CARTE_INTRO}", n, par))
            for i, c in enumerate(cont, 1):
                par = cp.nuovo_par()
                dom, _s1 = frasi_pagina(c.get("domanda"), nomi)
                ris, _s2 = frasi_pagina(c.get("risposta"), nomi)
                if not dom or not ris:
                    cp.saltate["carta"] = cp.saltate.get("carta", 0) + 1
                    continue
                cp.voci.append(Voce(CALLIOPE, f"Domanda {i}.", n, par))
                cp.voci += [Voce(LIBRO, f, n, par) for pp in dom for f in pp]
                cp.voci.append(Voce(PAUSA, "", n, par, PAUSA_CARTA_S))
                cp.voci.append(Voce(CALLIOPE, "Risposta.", n, par))
                cp.voci += [Voce(LIBRO, f, n, par) for pp in ris for f in pp]
            cp.parti.append({"n": n, "tipo": "carte", "carte": len(cont)})
        else:
            etichette = [et for et, _p, _s in cont]
            seguito = visti.get(a["id"], 0)
            visti[a["id"]] = seguito + 1
            cp.voci.append(Voce(CALLIOPE, f"Parte {n} di {tot}: argomento {a['numero']}"
                                + (", continua" if seguito else "")
                                + f", {_pagine_dette(etichette)}.", n, par))
            if not seguito:
                titolo, _s = frasi_pagina(a.get("titolo"), nomi)
                cp.voci += [Voce(LIBRO, f, n, par) for pp in titolo for f in pp]
            for et, pars, salt in cont:
                if pars is None:
                    cp.voci.append(Voce(CALLIOPE, f"La pagina {et} non l'ho ancora letta: la "
                                                  "salto.", n, cp.nuovo_par()))
                    continue
                if any(salt.get(k) for k in ("nome", "messaggio", "annuncio", "ordine")):
                    cp.voci.append(Voce(CALLIOPE, MESSAGGIO_SALTATO, n, cp.nuovo_par()))
                if salt.get("indirizzo"):
                    cp.voci.append(Voce(CALLIOPE, INDIRIZZO_SALTATO, n, cp.nuovo_par()))
                for pp in pars:
                    par = cp.nuovo_par()
                    cp.voci += [Voce(LIBRO, f, n, par) for f in pp]
            cp.parti.append({"n": n, "tipo": "argomento", "argomento": a["numero"],
                             "argomento_id": a["id"], "titolo": a.get("titolo") or "",
                             "pagine": etichette, "continua": bool(seguito)})
        frasi_n = sum(1 for v in cp.voci[inizio:] if v.tipo != PAUSA)
        cp.parti[-1]["frasi"] = frasi_n
    if cp.voci:
        cp.voci.append(Voce(CALLIOPE, FINE, tot, cp.nuovo_par()))
    for p in cp.parti:
        p["secondi"] = cp.secondi(p["n"])
    return cp


# ─────────────────────────── la posizione: riprendi e ripeti ───────────────────────────
def da_ripetere(voci: list[Voce], pos: int) -> int:
    """L'inizio del paragrafo da ripetere: quello della frase interrotta, o quello prima se del
    paragrafo non si era sentito niente."""
    if not voci:
        return 0
    pos = max(0, min(pos, len(voci) - 1))
    par = voci[pos].par
    inizio = pos
    while inizio > 0 and voci[inizio - 1].par == par:
        inizio -= 1
    if inizio == pos and pos > 0:
        par = voci[pos - 1].par
        inizio = pos - 1
        while inizio > 0 and voci[inizio - 1].par == par:
            inizio -= 1
    return inizio


def pezzi(voci: list[Voce], da: int) -> list[list[int]]:
    """Gli indici delle voci da `da` in pezzi di al più `PEZZO_FRASI` frasi, senza staccare un
    silenzio dalla frase prima (le pause non contano)."""
    out, corrente, n = [], [], 0
    for i in range(max(0, da), len(voci)):
        if voci[i].tipo != PAUSA and n >= PEZZO_FRASI:
            out.append(corrente)
            corrente, n = [], 0
        corrente.append(i)
        n += voci[i].tipo != PAUSA
    if corrente:
        out.append(corrente)
    return out


def sentite(voci: list[Voce], pezzo: list[int], dette: list[str]) -> int:
    """Quante voci del pezzo si sono sentite per intero, di fila dall'inizio (`dette`: `played`,
    nell'ordine; le frasi d'inizio, come «Riprendo dalla parte 2», non contano). Un silenzio vale
    sentito se la frase dopo lo è."""
    j, n = 0, 0
    dette = [str(d).strip() for d in dette or ()]
    for k in pezzo:
        v = voci[k]
        if v.tipo == PAUSA:
            n += 1
            continue
        while j < len(dette) and dette[j] != v.testo.strip():
            j += 1
        if j >= len(dette):
            # Il silenzio prima di una frase non sentita non conta
            while n > 0 and voci[pezzo[n - 1]].tipo == PAUSA:
                n -= 1
            return n
        j += 1
        n += 1
    return n


def leggi(lettura: dict, uscita, speaker, controlla=None, voce_libro: str | None = None,
          log=print) -> dict:
    """La lettura a voce (dal ciclo, dopo la risposta): i pezzi da `lettura["da"]`, ognuno in un
    turno della voce suo, con le frasi d'inizio (`lettura["intro"]`) davanti al primo. Prima di
    ogni pezzo `controlla()` (None per andare avanti, o il motivo della fermata con la frase da
    dire). Restituisce {"pos": la prima voce non sentita, "motivo": finito | interrotta | <motivo>,
    "frasi", "sentite"}."""
    voci: list[Voce] = lettura["voci"]
    pos = int(lettura.get("da", 0))
    intro = list(lettura.get("intro") or ())
    motivo, dette_tot, mandate = "finito", 0, 0
    for pezzo in pezzi(voci, pos):
        if controlla is not None:
            ferma = controlla()
            if ferma:
                motivo, frase = ferma if isinstance(ferma, tuple) else (ferma, None)
                if frase:
                    uscita.turno_lettura()
                    uscita.leggi(frase)
                    uscita.aspetta()
                break
        uscita.turno_lettura()
        for f in intro:
            uscita.leggi(f)
        intro = []
        for k in pezzo:
            v = voci[k]
            if v.tipo == PAUSA:
                uscita.pausa(v.secondi)
            else:
                uscita.leggi(v.testo, voce=voce_libro if v.tipo == LIBRO else None)
                mandate += 1
        uscita.aspetta()
        dette = list(getattr(speaker, "played", None) or ())
        if getattr(speaker, "interrupted", False):
            n = sentite(voci, pezzo, dette)
            dette_tot += sum(1 for k in pezzo[:n] if voci[k].tipo != PAUSA)
            pos = pezzo[0] + n
            motivo = "interrotta"
            break
        dette_tot += sum(1 for k in pezzo if voci[k].tipo != PAUSA)
        pos = pezzo[-1] + 1
    uscita.turno_lettura()          # chiude: `played` vuoto, l'interruzione azzerata
    return {"pos": pos, "motivo": motivo, "frasi": mandate, "sentite": dette_tot}


# ─────────────────────────── l'audio per lo schermo ───────────────────────────
def cartella_audio(cfg, vid) -> Path | None:
    base = D.cartella_di(cfg)
    return base / CARTELLA / str(int(vid)) if base is not None else None


def nome_file(firma: str, parte: int) -> str:
    return f"{re.sub(r'[^0-9a-f]', '', firma)[:16]}-{int(parte)}.wav"


class Sintesi:
    """L'audio delle parti per lo schermo, in un thread solo, una frase alla volta, che cede alla
    voce dal vivo: aspetta che le voci (`attivita`, `tts.AttivitaVoce`) siano ferme da
    `VOCE_FERMA_S` (al più `VOCE_ATTESA_MAX_S` per frase). `voce_per(path)` dà una voce di Piper
    già caricata dallo Speaker; `pronuncia` la stessa della voce."""

    def __init__(self, voce_per, voce_calliope: str, voce_libro: str | None = None,
                 pronuncia=None, attivita=None, log=print):
        self.voce_per = voce_per
        self.voce_calliope = voce_calliope
        self.voce_libro = voce_libro or voce_calliope
        self.pronuncia = pronuncia
        self.attivita = attivita
        self.log = log
        self._q: queue.Queue = queue.Queue()
        self._stato: dict = {}             # percorso → frazione fatta, o "errore"
        self._lock = threading.Lock()
        self._thread = None
        self.fatti = 0
        self.secondi = 0.0

    def firma_voci(self) -> str:
        return f"{Path(str(self.voce_calliope)).name}|{Path(str(self.voce_libro)).name}"

    def stato(self, path: Path):
        with self._lock:
            return self._stato.get(str(path))

    def chiedi(self, path: Path, voci: list[Voce], ancora=None) -> float:
        """Prepara il file `path` (se non c'è e non è già in coda); la frazione fatta (0 in coda).
        `ancora()`: la verifica c'è ancora? Si chiede prima di tenere il file, così un file finito
        dopo «dimentica» o la tenuta non resta (il resto lo toglie la rotazione)."""
        k = str(path)
        with self._lock:
            s = self._stato.get(k)
            if isinstance(s, float):
                return s
            self._stato[k] = 0.0
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._lavora, daemon=True,
                                                name="studio-ascolta")
                self._thread.start()
        self._q.put((path, list(voci), ancora))
        return 0.0

    def ferma(self, attesa_s: float = 10.0) -> bool:
        """Aspetta che la coda sia vuota (le prove, la chiusura). True se è vuota."""
        fine = time.monotonic() + attesa_s
        while time.monotonic() < fine:
            with self._lock:
                vuota = self._q.empty() and not any(isinstance(x, float)
                                                     for x in self._stato.values())
            if vuota:
                return True
            time.sleep(0.05)
        return False

    def _aspetta_voce(self):
        a = self.attivita
        if a is None:
            return
        fine = time.monotonic() + VOCE_ATTESA_MAX_S
        while time.monotonic() < fine:
            if getattr(a, "in_sintesi", 0) == 0 and \
                    time.monotonic() - getattr(a, "ultima", 0.0) >= VOCE_FERMA_S:
                return
            time.sleep(0.2)

    def _voci(self):
        cal = self.voce_per(self.voce_calliope)
        lib = cal
        if self.voce_libro and self.voce_libro != self.voce_calliope:
            try:
                altra = self.voce_per(self.voce_libro)
                if altra.config.sample_rate == cal.config.sample_rate:
                    lib = altra
            except Exception as e:  # noqa: BLE001 — tutto nella voce di Calliope
                self.log(f"   [STUDIO] voce del libro non caricata ({type(e).__name__}): uso "
                         f"quella di Calliope")
        return cal, lib

    def _lavora(self):
        from ..tts import sintesi_pcm
        while True:
            try:
                path, voci, ancora = self._q.get(timeout=60)
            except queue.Empty:
                with self._lock:
                    if self._q.empty():
                        self._thread = None
                        return
                continue
            k = str(path)
            tmp = path.with_name(path.name + ".tmp")
            try:
                cal, lib = self._voci()
                rate = int(cal.config.sample_rate)
                path.parent.mkdir(parents=True, exist_ok=True)
                tot = max(1, len(voci))
                with wave.open(str(tmp), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    prima = None
                    for i, v in enumerate(voci):
                        if v.tipo == PAUSA:
                            w.writeframes(b"\0\0" * int(rate * v.secondi))
                            continue
                        if prima is not None:
                            pausa = PAUSA_FRASE_S if prima.par == v.par else (
                                PAUSA_PARTE_S if prima.tipo == CALLIOPE else PAUSA_PARAGRAFO_S)
                            w.writeframes(b"\0\0" * int(rate * pausa))
                        self._aspetta_voce()
                        w.writeframes(sintesi_pcm(lib if v.tipo == LIBRO else cal, v.testo,
                                                  self.pronuncia))
                        prima = v
                        with self._lock:
                            self._stato[k] = round((i + 1) / tot, 3)
                    secondi = w.getnframes() / rate
                if ancora is not None and not ancora():
                    # La verifica è andata via intanto («dimentica», la tenuta): niente file
                    tmp.unlink()
                    with self._lock:
                        self._stato.pop(k, None)
                    continue
                os.replace(tmp, path)
                self.fatti += 1
                self.secondi += secondi
                with self._lock:
                    self._stato.pop(k, None)
                self.log(f"   [STUDIO] audio del ripasso pronto: {len(voci)} voci, "
                         f"{secondi:.0f} s")
            except Exception as e:  # noqa: BLE001 — lo schermo lo dice, la voce non si ferma
                with self._lock:
                    self._stato[k] = "errore"
                try:
                    tmp.unlink()
                except OSError:
                    pass
                self.log(f"   [STUDIO] audio del ripasso non preparato: {type(e).__name__}")


def durata_wav(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, wave.Error, EOFError):
        return None


def togli_audio(cartella, verifiche_vive: set | None = None, piu_vecchi_di_s: float = 0.0,
                solo: list | None = None) -> int:
    """I file del ripasso sotto `cartella/ascolta`: di tutte le verifiche (`svuota`), di quelle in
    `solo` (cancellate), di quelle che non sono in `verifiche_vive` e quelli non ascoltati da più
    di `piu_vecchi_di_s` (la rotazione). Mai fuori dalla cartella, mai seguendo un link."""
    if not cartella:
        return 0
    base = Path(cartella).resolve()
    radice = base / CARTELLA
    if radice.is_symlink() or not radice.is_dir() or base not in radice.resolve().parents:
        return 0
    n = 0
    adesso = time.time()
    for d in list(radice.iterdir()):
        try:
            if d.is_symlink() or not d.is_dir() or base not in d.resolve().parents:
                continue
            vid = int(d.name) if d.name.isdecimal() else None
            if solo is not None:
                if vid not in solo:
                    continue
                tutta = True                         # le verifiche cancellate
            elif verifiche_vive is not None and vid not in verifiche_vive:
                tutta = True                         # una verifica che non c'è più
            else:
                tutta = verifiche_vive is None and not piu_vecchi_di_s     # «svuota»
            for f in list(d.iterdir()):
                if f.is_symlink() or not f.is_file():
                    continue
                if tutta or (piu_vecchi_di_s and adesso - f.stat().st_mtime > piu_vecchi_di_s):
                    f.unlink()
                    n += 1
            if not any(d.iterdir()):
                d.rmdir()
        except (OSError, ValueError):
            continue
    return n


# ─────────────────────────── nel servizio dello Studio ───────────────────────────
class ProvaAperta(ValueError):
    """Una prova aperta sulla verifica: il ripasso si blocca per tutti (le risposte sono lì)."""


class Ascolti:
    """Il ripasso da ascoltare nel servizio dello Studio (mixin di `servizio.Studio`). Le letture
    e le scritture dei dati stanno dentro `self.dati.lock`; la posizione a voce sta in memoria, per
    persona (chi ascolta), al più `RIPRENDI_S`."""

    # La sintesi per lo schermo (`Sintesi`): la crea main.py con le voci dello Speaker; None =
    # niente audio per lo schermo (lo dice la pagina)
    sintesi = None

    def ascolto_acceso(self) -> bool:
        return modo(self.cfg) == "attiva"

    def _ascolti_mem(self) -> dict:
        return self.__dict__.setdefault("_ascolti", {})

    def _misure_ascolto(self) -> dict:
        return self.misure.setdefault("ascolta", {
            "letture": 0, "frasi": 0, "sentite": 0, "interrotte": 0, "riprese": 0, "ripetute": 0,
            "fermate": {}, "bloccate_prova": 0, "parti_schermo": 0, "audio_serviti": 0,
            "saltate": {}})

    def _nomi_ascolto(self) -> list[str]:
        return [str(getattr(self.cfg, "name", "") or "Calliope")]

    def _carte_ascolto(self, v: dict, chi) -> list[dict]:
        carte = [c for c in self._carte_di(v, chi) if c["stato"] == "attiva" and c["nel_piano"]]
        carte.sort(key=lambda c: (not c["da_ripassare"], c["scatola"], c["id"]))
        return carte

    def _copione(self, chi, v: dict, cosa: str, numero=None) -> Copione:
        """Il copione di una verifica (dentro il lock). ValueError «niente» se non c'è niente da
        ascoltare, «argomento» se l'argomento detto non è nel piano."""
        from . import piano as P
        args = self._argomenti_numerati(v["id"])
        pagine = [p for p in self.dati.tutti(
            "SELECT p.* FROM studio_pagine p JOIN studio_materiali m ON m.id = p.materiale "
            "WHERE m.verifica = ? ORDER BY p.ordine, p.id", (v["id"],)) if p["stato"] != "tolta"]
        carte = self._carte_ascolto(v, chi)
        solo, con_carte = None, True
        if cosa == "oggi":
            r = self._oggi_del_piano(v)
            if r is not None and r["fase"] == P.STUDIO and r["pagine"]:
                solo, con_carte = set(r["pagine"]), False
            else:
                args = []                 # un giorno di ripasso, o niente pagine oggi: le carte
        elif cosa == "argomento":
            args = [a for a in args if a["numero"] == numero]
            if not args:
                raise ValueError("argomento")
            con_carte = False
        elif cosa == "carte":
            args = []
        cp = componi(args, pagine, carte, cosa, self._nomi_ascolto(), solo, con_carte)
        if not cp.voci:
            raise ValueError("niente")
        return cp

    def _oggi_del_piano(self, v: dict) -> dict | None:
        if v["stato"] != "aperta":
            return None
        giorni, _avvisi, stato = self._piano_vivo(v)
        oggi = self._oggi().isoformat()
        return next((g for g in giorni if g["giorno"] == oggi), None) if stato == "aperta" \
            else None

    def _ascoltabile(self, chi, vid) -> dict:
        """La verifica (coi permessi: NonTrovata), o ProvaAperta con una prova aperta."""
        v = self._verifica(chi, vid)
        if self._prova_aperta(v["id"]) is not None:
            self._misure_ascolto()["bloccate_prova"] += 1
            raise ProvaAperta("prova")
        return v

    # ── a voce ──
    def ascolto_prepara(self, chi, vid=None, cosa: str = "tutto", numero=None,
                        come: str = "inizia") -> dict:
        """La lettura da passare al ciclo: {chi, verifica, cosa, numero, firma, voci, da, intro,
        parti, parte, secondi}. `come`: «inizia» (da capo), «riprendi» (dalla frase interrotta) o
        «ripeti» (dall'inizio del paragrafo). LookupError «nessuno» senza un ripasso in pausa per
        «riprendi» e «ripeti»; ValueError «niente» o «argomento»; ProvaAperta; NonTrovata."""
        cosa = cosa if cosa in COSE else "tutto"
        m = self._misure_ascolto()
        with self.dati.lock:
            intro: list[str] = []
            if come in ("riprendi", "ripeti"):
                s = self.ascolto_in_pausa(getattr(chi, "id", None))
                if s is None:
                    raise LookupError("nessuno")
                v = self._ascoltabile(chi, s["verifica"])
                cp = self._copione(chi, v, s["cosa"], s["numero"])
                if cp.firma == s["firma"]:
                    pos = min(s["pos"], len(cp.voci) - 1)
                else:
                    n = min(s["parte"], len(cp.parti)) or 1
                    pos = cp.inizio_parte(n)
                    intro.append(f"Il ripasso è cambiato: riparto dalla parte {n}.")
                if come == "ripeti":
                    pos = da_ripetere(cp.voci, pos)
                    intro.append("Ripeto.")
                    m["ripetute"] += 1
                else:
                    m["riprese"] += 1
                    if not intro and pos > 0:
                        intro.append(f"Riprendo dalla parte {cp.voci[pos].parte}.")
                cosa, numero = s["cosa"], s["numero"]
            else:
                v = self._ascoltabile(chi, vid)
                cp = self._copione(chi, v, cosa, numero)
                pos = 0
            for k, n in cp.saltate.items():
                m["saltate"][k] = m["saltate"].get(k, 0) + n
        resto = cp.voci[pos:]
        return {"chi": str(getattr(chi, "id", "")), "verifica": v["id"], "cosa": cosa,
                "numero": numero, "firma": cp.firma, "voci": cp.voci, "da": pos, "intro": intro,
                "parti": len(cp.parti), "parte": cp.voci[pos].parte if resto else len(cp.parti),
                "secondi": _durata(sum(len(x.testo) for x in resto if x.tipo != PAUSA),
                                   sum(x.secondi for x in resto if x.tipo == PAUSA))}

    def ascolto_vale(self, lettura: dict):
        """Prima di ogni pezzo della lettura a voce: None per andare avanti, o (motivo, frase del
        codice) per fermarla. La posizione resta."""
        if not self.per_modello() or not self.ascolto_acceso():
            return ("spento", "Il ripasso da ascoltare adesso è spento: mi fermo qui.")
        with self.dati.lock:
            if self._prova_aperta(lettura["verifica"]) is not None:
                self._misure_ascolto()["bloccate_prova"] += 1
                return ("prova", "C'è una prova in corso: il ripasso si ferma, lo riprendiamo "
                                 "dopo la consegna.")
        prof = self._profilo(lettura["chi"])
        if prof is not None:
            from .. import minori
            try:
                fuori = minori.fuori_orario(prof)
            except Exception:  # noqa: BLE001
                fuori = None
            if fuori:
                return ("orario", "Adesso è l'ora di riposo: il ripasso si ferma qui.")
        return None

    def ascolto_fermo(self, lettura: dict, esito: dict):
        """La lettura a voce è finita o si è fermata: la posizione per «riprendi» (in memoria) e
        le misure (solo conti)."""
        import datetime
        m = self._misure_ascolto()
        m["letture"] += 1
        m["frasi"] += int(esito.get("frasi") or 0)
        m["sentite"] += int(esito.get("sentite") or 0)
        motivo = str(esito.get("motivo") or "finito")
        m["fermate"][motivo] = m["fermate"].get(motivo, 0) + 1
        if motivo == "interrotta":
            m["interrotte"] += 1
        voci, pos = lettura["voci"], int(esito.get("pos") or 0)
        mem = self._ascolti_mem()
        if motivo == "finito" or pos >= len(voci):
            mem.pop(lettura["chi"], None)
        else:
            mem[lettura["chi"]] = {
                "verifica": lettura["verifica"], "cosa": lettura["cosa"],
                "numero": lettura["numero"], "firma": lettura["firma"], "pos": pos,
                "parte": voci[pos].parte, "parti": lettura["parti"],
                "fino": self.adesso() + datetime.timedelta(seconds=RIPRENDI_S)}
        self._registra(f"ripasso a voce della verifica {lettura['verifica']}: {motivo}, "
                       f"{esito.get('sentite', 0)} frasi sentite di {esito.get('frasi', 0)}")

    def ascolto_in_pausa(self, persona) -> dict | None:
        mem = self._ascolti_mem()
        s = mem.get(str(persona or ""))
        if s is None:
            return None
        if self.adesso() > s["fino"]:
            mem.pop(str(persona), None)
            return None
        return dict(s)

    def ascolto_chiudi(self, persona) -> bool:
        return self._ascolti_mem().pop(str(persona or ""), None) is not None

    def nota_ascolto(self, persona) -> str:
        """La riga dei dati del turno con un ripasso in pausa (solo numeri, frase del codice)."""
        if not self.per_modello() or not self.ascolto_acceso():
            return ""
        s = self.ascolto_in_pausa(persona)
        if s is None:
            return ""
        return (f"Studio, ripasso da ascoltare in pausa alla parte {s['parte']} di {s['parti']}: "
                "se chi parla lo chiede, studio_ascolta con azione «riprendi», «ripeti» o "
                "«ferma».")

    # ── sullo schermo ──
    def _firma_audio(self, cp: Copione) -> str:
        s = self.sintesi
        voci = s.firma_voci() if s is not None else ""
        return hashlib.sha256(f"{cp.firma}|{voci}".encode()).hexdigest()[:16]

    def ascolto_parti(self, chi, vid) -> dict:
        """Le parti del ripasso di una verifica per lo schermo: {verifica, prova, firma, parti:
        [{n, tipo, argomento, titolo (un dato: textContent), pagine, frasi, secondi, oggi,
        pronta, fatto, errore}], secondi, audio}. Con una prova aperta nessuna parte."""
        m = self._misure_ascolto()
        vuoto = {"prova": False, "parti": [], "firma": None, "secondi": 0,
                 "audio": self.sintesi is not None}
        with self.dati.lock:
            v = self._verifica(chi, vid)
            if self._prova_aperta(v["id"]) is not None:
                return {**vuoto, "verifica": v["id"], "prova": True}
            try:
                cp = self._copione(chi, v, "tutto")
            except ValueError:
                return {**vuoto, "verifica": v["id"]}
            oggi = self._oggi_del_piano(v)
            oggi_pag = set(oggi["pagine"]) if oggi and oggi["fase"] == "studio" else set()
            ids_parte = {a["id"]: set(a["pagine"]) for a in self._argomenti_numerati(v["id"])}
        firma = self._firma_audio(cp)
        cartella = cartella_audio(self.cfg, v["id"])
        parti = []
        for p in cp.parti:
            path = cartella / nome_file(firma, p["n"]) if cartella is not None else None
            pronta = bool(path is not None and path.exists())
            stato = self.sintesi.stato(path) if (self.sintesi is not None and path is not None
                                                 and not pronta) else None
            x = {k: p.get(k) for k in ("n", "tipo", "argomento", "titolo", "pagine", "frasi",
                                       "carte", "continua")}
            durata = durata_wav(path) if pronta else None
            x["secondi"] = int(round(durata)) if durata is not None else p["secondi"]
            x["oggi"] = bool(oggi_pag and p["tipo"] == "argomento"
                             and ids_parte.get(p.get("argomento_id"), set()) & oggi_pag)
            x["pronta"] = pronta
            x["fatto"] = stato if isinstance(stato, float) else None
            x["errore"] = stato == "errore"
            parti.append(x)
        m["parti_schermo"] += 1
        return {"verifica": v["id"], "prova": False, "firma": firma, "parti": parti,
                "secondi": sum(x["secondi"] for x in parti), "audio": self.sintesi is not None}

    def ascolto_audio(self, chi, vid, parte: int, firma: str | None) -> dict:
        """Il file di una parte: {"file": Path} se è pronto; {"pronto": False, "fatto": x} se si
        prepara adesso (e intanto la parte dopo); {"cambiato": True} se il copione è cambiato;
        {"senza_voce": True} senza la sintesi. ProvaAperta, NonTrovata, ValueError «parte»."""
        with self.dati.lock:
            v = self._ascoltabile(chi, vid)
            cp = self._copione(chi, v, "tutto")
        fa = self._firma_audio(cp)
        if firma and firma != fa:
            return {"cambiato": True, "firma": fa}
        voci = [x for x in cp.voci if x.parte == int(parte)]
        if not voci:
            raise ValueError("parte")
        cartella = cartella_audio(self.cfg, v["id"])
        if cartella is None:
            return {"senza_voce": True}
        path = cartella / nome_file(fa, parte)
        if path.exists():
            try:
                os.utime(path)              # l'ultimo ascolto: la cache scade da qui
            except OSError:
                pass
            self._misure_ascolto()["audio_serviti"] += 1
            # Intanto la parte dopo, così il passaggio è senza attesa
            dopo = [x for x in cp.voci if x.parte == int(parte) + 1]
            nxt = cartella / nome_file(fa, int(parte) + 1)
            if dopo and self.sintesi is not None and not nxt.exists():
                self.sintesi.chiedi(nxt, dopo, self._ancora(v["id"]))
            return {"file": path, "firma": fa}
        if self.sintesi is None:
            return {"senza_voce": True}
        return {"pronto": False, "fatto": self.sintesi.chiedi(path, voci, self._ancora(v["id"])),
                "firma": fa}

    def _ancora(self, vid):
        def ancora() -> bool:
            try:
                return self.dati.uno("SELECT id FROM studio_verifiche WHERE id = ?",
                                     (int(vid),)) is not None
            except Exception:  # noqa: BLE001 — nel dubbio il file non si tiene
                return False
        return ancora
