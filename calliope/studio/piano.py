"""
Il piano a giorni dello Studio (29/10, passo 4.1, issue #280, decisione 0035): calcolato solo
dal codice, senza modello, deterministico e provabile a secco.

Ingressi: oggi, la data della verifica, le pagine da leggere (quelle degli argomenti tenuti,
nell'ordine delle pagine), i minuti liberi di ogni giorno (`minuti_liberi`: la fascia dello
studio meno gli orari di riposo di un minore, i giorni senza piano, i giorni saltati, i minuti
divisi fra più verifiche) e le pagine e i giorni già fatti. Uscita: un giorno per riga, con la
fase («studio» o «ripasso»), le pagine e l'attività del giorno, «Leggi le pagine 112–113»
(risposta 1 di chi amministra del 28/10: le carte arrivano dopo il passo 4).

Regole:
- si studia da oggi al giorno prima della verifica; il giorno della verifica no;
- un giorno con meno minuti di una pagina (`minuti_pagina`) non ha piano;
- con almeno due giorni liberi l'ultimo è solo ripasso; con uno solo quel giorno si legge
  tutto, senza ripasso (avviso «senza_ripasso»);
- le pagine si distribuiscono in proporzione ai minuti dei giorni, nell'ordine, senza superare
  i minuti di nessun giorno quando ci stanno; se non ci stanno si distribuiscono lo stesso e
  ogni giorno oltre i suoi minuti ha il segno `oltre` (avviso «troppe_pagine»);
- un giorno di studio rimasto senza pagine nuove (meno pagine che giorni) ripassa quelle lette;
- le pagine e i giorni già fatti restano fatti: il ricalcolo distribuisce solo il resto.

Niente nomi né testi delle pagine: l'attività la scrive il codice dai numeri di pagina e dai
titoli dei materiali, che sceglie la persona.
"""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass, field

# Fasi di un giorno del piano
STUDIO = "studio"
RIPASSO = "ripasso"

# Gli avvisi del piano (codici; le frasi le scrive chi li dice, dal passo 4.5)
PASSATA = "passata"                 # la data della verifica è passata
OGGI = "oggi"                       # la verifica è oggi: niente piano
NESSUN_GIORNO = "nessun_giorno"     # nessun giorno con minuti liberi prima della verifica
NESSUNA_PAGINA = "nessuna_pagina"   # nessun argomento tenuto con delle pagine
SENZA_RIPASSO = "senza_ripasso"     # un giorno solo: si legge tutto, il ripasso non ci sta
TROPPE_PAGINE = "troppe_pagine"     # le pagine non stanno nei minuti dei giorni

GIORNI_SETTIMANA = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


@dataclass(frozen=True)
class Pagina:
    """Una pagina da leggere: l'id nel db, l'ordine nel materiale, il numero letto (o None) e
    l'etichetta per le pagine senza numero (il titolo del materiale, «Appunti»)."""
    id: int
    ordine: int
    numero: str | None = None
    etichetta: str | None = None


@dataclass
class Giorno:
    giorno: datetime.date
    fase: str
    pagine: list[int]
    minuti: int
    attivita: str
    oltre: bool = False             # più pagine dei minuti del giorno


@dataclass
class Piano:
    giorni: list[Giorno] = field(default_factory=list)
    avvisi: list[str] = field(default_factory=list)
    giorni_mancanti: int = 0
    pagine_totali: int = 0
    pagine_fatte: int = 0


# ─────────────────────────── minuti liberi ───────────────────────────

def _minuti(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fascia_valida(testo) -> tuple[int, int] | None:
    """«15:00-20:00» → (900, 1200); None se scritta male o vuota (inizio dopo la fine compreso:
    lo studio non passa la mezzanotte)."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})\s*", str(testo or ""))
    if not m:
        return None
    a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
    if not (int(m[1]) < 24 and int(m[3]) <= 24 and int(m[2]) < 60 and int(m[4]) < 60) or a >= b:
        return None
    return a, b


def _intervalli_riposo(orari) -> list[tuple[int, int]]:
    """Gli orari di riposo di un minore («21:00-07:30») come intervalli dentro un giorno,
    spezzati a mezzanotte."""
    out = []
    for o in orari or ():
        try:
            a, b = (_minuti(x) for x in str(o).split("-"))
        except (ValueError, TypeError):
            continue
        if a <= b:
            out.append((a, b))
        else:
            out += [(a, 24 * 60), (0, b)]
    return out


def minuti_liberi(fascia: tuple[int, int], orari=(), da_minuto: int | None = None) -> int:
    """I minuti della fascia dello studio non coperti dagli orari di riposo; con `da_minuto`
    (oggi, adesso) solo quelli che devono ancora venire."""
    a, b = fascia
    if da_minuto is not None:
        a = max(a, da_minuto)
    if a >= b:
        return 0
    liberi = [(a, b)]
    for ra, rb in _intervalli_riposo(orari):
        nuovi = []
        for x, y in liberi:
            if rb <= x or ra >= y:
                nuovi.append((x, y))
                continue
            if ra > x:
                nuovi.append((x, ra))
            if rb < y:
                nuovi.append((rb, y))
        liberi = nuovi
    return sum(y - x for x, y in liberi)


def giorno_della_settimana(nome: str) -> int | None:
    """«domenica» → 6; None per un nome sconosciuto."""
    n = str(nome or "").strip().lower().replace("lunedi", "lunedì").replace("martedi", "martedì")
    n = n.replace("mercoledi", "mercoledì").replace("giovedi", "giovedì").replace(
        "venerdi", "venerdì")
    return GIORNI_SETTIMANA.index(n) if n in GIORNI_SETTIMANA else None


# ─────────────────────────── l'attività del giorno ───────────────────────────

def _intervalli(numeri: list[int]) -> list[str]:
    out, i = [], 0
    while i < len(numeri):
        j = i
        while j + 1 < len(numeri) and numeri[j + 1] == numeri[j] + 1:
            j += 1
        out.append(str(numeri[i]) if i == j else f"{numeri[i]}–{numeri[j]}")
        i = j + 1
    return out


def _elenco(parti: list[str]) -> str:
    return parti[0] if len(parti) == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]


def descrivi_pagine(pagine: list[Pagina]) -> str:
    """«le pagine 112–113 e 115», «la pagina 114», «le pagine 140–141 e «Appunti»». I numeri
    letti che non sono numeri («IV», «12a») restano come sono."""
    numeri, altri, etichette = [], [], []
    for p in pagine:
        n = str(p.numero or "").strip()
        if n.isdigit():
            numeri.append(int(n))
        elif n:
            altri.append(n)
        else:
            e = f"«{(p.etichetta or 'foglio senza numero').strip()[:40]}»"
            if e not in etichette:
                etichette.append(e)
    numeri = sorted(set(numeri))
    voci = _intervalli(numeri) + altri
    parti = []
    if voci:
        una = len(numeri) + len(altri) == 1
        parti.append(("la pagina " if una else "le pagine ") + _elenco(voci))
    parti += etichette
    return _elenco(parti) if parti else "le pagine"


def attivita(fase: str, pagine: list[Pagina]) -> str:
    cosa = descrivi_pagine(pagine)
    return f"Leggi {cosa}." if fase == STUDIO else f"Ripassa {cosa}."


# ─────────────────────────── il piano ───────────────────────────

def calcola(oggi: datetime.date, data: datetime.date, pagine: list[Pagina],
            minuti: dict, minuti_pagina: int, fatte=(), giorni_fatti=()) -> Piano:
    """Il piano da `oggi` al giorno prima di `data`. `pagine`: tutte le pagine della verifica
    (degli argomenti tenuti), anche quelle già lette; `minuti`: giorno → minuti liberi (un
    giorno che manca vale 0); `fatte`: gli id delle pagine già lette nei giorni fatti;
    `giorni_fatti`: i giorni già segnati fatti, che il ricalcolo non riempie di nuovo."""
    minuti_pagina = max(1, int(minuti_pagina))
    pagine = sorted(pagine, key=lambda p: (p.ordine, p.id))
    fatte = set(fatte)
    piano = Piano(giorni_mancanti=(data - oggi).days, pagine_totali=len(pagine),
                  pagine_fatte=sum(p.id in fatte for p in pagine))
    if data < oggi:
        piano.avvisi.append(PASSATA)
        return piano
    if data == oggi:
        piano.avvisi.append(OGGI)
        return piano
    if not pagine:
        piano.avvisi.append(NESSUNA_PAGINA)
        return piano
    giorni_fatti = set(giorni_fatti)
    tutti = [oggi + datetime.timedelta(days=i) for i in range((data - oggi).days)]
    liberi = [g for g in tutti if g not in giorni_fatti
              and int(minuti.get(g, 0) or 0) >= minuti_pagina]
    if not liberi:
        piano.avvisi.append(NESSUN_GIORNO)
        return piano
    da_leggere = [p for p in pagine if p.id not in fatte]
    if len(liberi) >= 2:
        studio, ripasso = liberi[:-1], liberi[-1]
    else:
        studio, ripasso = liberi, None
        if da_leggere:
            piano.avvisi.append(SENZA_RIPASSO)
    if not da_leggere:
        # Tutto letto: resta il ripasso, nei giorni che restano
        for g in liberi:
            piano.giorni.append(Giorno(g, RIPASSO, [p.id for p in pagine],
                                       int(minuti[g]), attivita(RIPASSO, pagine)))
        return piano
    cap = {g: int(minuti[g]) // minuti_pagina for g in studio}
    tot = sum(cap.values())
    n = len(da_leggere)
    if n > tot:
        piano.avvisi.append(TROPPE_PAGINE)
    # In proporzione ai minuti: dopo il giorno i, ceil(n · capacità fin lì / capacità totale)
    # pagine. Con n ≤ tot nessun giorno supera la sua capacità
    lette = [p for p in pagine if p.id in fatte]
    cumul, prima = 0, 0
    for g in studio:
        cumul += cap[g]
        fino = math.ceil(n * cumul / tot)
        quante = da_leggere[prima:fino]
        prima = fino
        if quante:
            oltre = len(quante) > cap[g]
            piano.giorni.append(Giorno(
                g, STUDIO, [p.id for p in quante],
                len(quante) * minuti_pagina if oltre else min(int(minuti[g]),
                                                              len(quante) * minuti_pagina),
                attivita(STUDIO, quante), oltre=oltre))
            lette += quante
        elif lette:
            piano.giorni.append(Giorno(g, RIPASSO, [p.id for p in lette], int(minuti[g]),
                                       attivita(RIPASSO, sorted(lette, key=lambda p: p.ordine))))
    if ripasso is not None:
        piano.giorni.append(Giorno(ripasso, RIPASSO, [p.id for p in pagine],
                                   int(minuti[ripasso]), attivita(RIPASSO, pagine)))
    return piano


# ─────────────────────────── tappe e previsione ───────────────────────────

def tappe(argomenti: list[dict], ordine_pagine: dict, fatte=()) -> list[dict]:
    """Le tappe del percorso: gli argomenti tenuti nell'ordine della loro prima pagina, ognuno
    «fatta» (tutte le sue pagine lette), «aperta» (la prima non fatta) o «chiusa» (si sblocca
    dopo). `argomenti`: dict con `id`, `titolo`, `pagine` (id); `ordine_pagine`: id → ordine."""
    fatte = set(fatte)
    con_pagine = [a for a in argomenti if [p for p in a.get("pagine") or ()
                                            if p in ordine_pagine]]
    con_pagine.sort(key=lambda a: (min(ordine_pagine[p] for p in a["pagine"]
                                       if p in ordine_pagine), a.get("id") or 0))
    out, aperta = [], False
    for a in con_pagine:
        pag = [p for p in a["pagine"] if p in ordine_pagine]
        if all(p in fatte for p in pag):
            stato = "fatta"
        elif not aperta:
            stato, aperta = "aperta", True
        else:
            stato = "chiusa"
        out.append({"argomento": a.get("id"), "titolo": a.get("titolo"), "pagine": pag,
                    "stato": stato})
    return out


MISURE_MIN = 2      # la previsione compare solo dopo almeno due misure vere (spunto del 28/10)


def previsione(misure: list[tuple[datetime.date, float]], data: datetime.date) -> int | None:
    """La padronanza prevista il giorno della verifica, in %: la retta dei minimi quadrati
    sulle misure (giorno, %) portata alla data, fra 0 e 100. None con meno di `MISURE_MIN`
    misure; misure tutte dello stesso giorno → la loro media."""
    pts = [(d, float(v)) for d, v in misure if v is not None]
    if len(pts) < MISURE_MIN:
        return None
    base = min(d for d, _ in pts)
    xs = [(d - base).days for d, _ in pts]
    ys = [v for _, v in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        y = my
    else:
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        y = my + b * ((data - base).days - mx)
    return int(round(min(100.0, max(0.0, y))))
