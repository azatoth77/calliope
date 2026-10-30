"""
Il resoconto di una sessione e il riepilogo di una verifica dello Studio (30/10, passo 4b, issue
#244, epic #251, decisione 0035 punto 31): **proiezioni** dei dati salvati in `memoria.db` (gli
eventi `studio_eventi`, il piano, le pagine, gli argomenti, le misure), senza modello e senza testo
scritto da un modello. Qui le funzioni pure: le sessioni giorno per giorno dagli eventi, le righe
per lo schermo e le frasi per la voce. Il servizio (`servizio.Studio.resoconto`, `riepilogo`)
legge il db e le chiama.

**Le frasi per la voce** (principio 5, 0035 punto 24) hanno solo ciò che è della persona o del
codice: la materia e la data della verifica (dette da lei o dal tutore), conti, giorni e ore, e i
numeri di pagina **solo se sono cifre** (vengono dall'OCR: una sigla letta come «ESEGUI» non entra
mai, al suo posto «2 pagine»). Mai i titoli degli argomenti né il testo delle pagine. Mai lo stato
d'animo né la conoscenza detta «da 1 a 5»: non sono su disco (0035 punto 27).

**Le righe per lo schermo** possono avere l'attività intera del piano («Leggi le pagine IV–V di
«Libro»»): la pagina le scrive con textContent.
"""

from __future__ import annotations

import datetime

from . import piano as P

GIORNI = P.GIORNI_SETTIMANA
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")
# Una sessione dura al più 3 ore (come le due domande, servizio.SESSIONE_S): oltre, il tempo fra
# «Inizia» e «Fatto» non è una misura
DURATA_MAX_S = 3 * 3600

# Gli stati di un giorno nel resoconto
FATTO, SALTATO, MANCATO, INIZIATO, DA_FARE, NIENTE = (
    "fatto", "saltato", "mancato", "iniziato", "da_fare", "niente")


def _d(x) -> datetime.date:
    if isinstance(x, datetime.datetime):
        return x.date()
    if isinstance(x, datetime.date):
        return x
    return datetime.date.fromisoformat(str(x)[:10])


def _t(x) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(str(x))
    except (TypeError, ValueError):
        return None


def detta(d) -> str:
    """«giovedì 5 novembre»."""
    d = _d(d)
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def quando(d, oggi) -> str:
    """«oggi», «ieri», «domani» o «giovedì 5 novembre»."""
    n = (_d(d) - _d(oggi)).days
    return {0: "oggi", -1: "ieri", 1: "domani"}.get(n) or detta(d)


def ora_detta(t) -> str:
    t = _t(t)
    return f"{t.hour}:{t.minute:02d}" if t else ""


def durata_detta(minuti) -> str:
    """«35 minuti», «1 ora», «1 ora e 20 minuti», «2 ore e 5 minuti»."""
    m = max(0, int(minuti or 0))
    h, r = divmod(m, 60)
    min_ = "1 minuto" if r == 1 else f"{r} minuti"
    if not h:
        return min_
    ore = "1 ora" if h == 1 else f"{h} ore"
    return ore if not r else f"{ore} e {min_}"


def conta(n: int, uno: str, molti: str) -> str:
    return f"1 {uno}" if n == 1 else f"{n} {molti}"


def pagine_dette(numeri: list) -> str:
    """Le pagine per la voce: «la pagina 114», «le pagine 112–113 e 115» solo se tutti i numeri
    sono cifre (`numeri`: interi o None, da `piano.numero_pagina`); altrimenti il conto, «3
    pagine». Mai una sigla letta dall'OCR."""
    if not numeri:
        return "le pagine"
    if all(isinstance(n, int) for n in numeri):
        voci = P._intervalli(sorted(set(numeri)))
        una = len(set(numeri)) == 1
        return ("la pagina " if una else "le pagine ") + P._elenco(voci)
    return conta(len(numeri), "pagina", "pagine")


# ─────────────────────────── le sessioni dagli eventi ───────────────────────────

def sessioni(eventi: list[dict], righe_passate=(), oggi=None) -> list[dict]:
    """Un giorno per elemento, in ordine di giorno, dagli eventi di una verifica (`eventi`:
    righe di `studio_eventi` con `dati` già letto) e dalle righe del piano passate senza «fatto»
    (`righe_passate`: un giorno passato rimasto nel piano, per esempio di una verifica ormai
    passata, vale «mancato» anche senza l'evento). Per ogni giorno: lo stato (fatto, saltato,
    mancato, iniziato), l'ora d'inizio e di fine, i minuti misurati (solo fra «inizio» e «fatto»
    dello stesso giorno, entro `DURATA_MAX_S`), i minuti previsti, la fase e le pagine (id)."""
    per_giorno: dict = {}
    for e in sorted(eventi, key=lambda e: (str(e.get("ora") or ""), e.get("id") or 0)):
        if e.get("tipo") == "spostata":
            continue
        per_giorno.setdefault(str(e["giorno"]), []).append(e)
    for r in righe_passate:
        g = str(r["giorno"])
        if g not in per_giorno:
            per_giorno[g] = [{"tipo": MANCATO, "giorno": g, "ora": None,
                              "dati": {"pagine": list(r.get("pagine") or ()),
                                       "minuti": r.get("minuti"), "fase": r.get("fase")}}]
    out = []
    for g in sorted(per_giorno):
        ev = per_giorno[g]
        chiusura = [e for e in ev if e["tipo"] in (FATTO, "non_fatto")]
        ultimo = chiusura[-1] if chiusura else None
        s = {"giorno": g, "stato": None, "inizio": None, "fine": None, "minuti": None,
             "previsti": None, "fase": None, "pagine": []}
        base = None
        if ultimo is not None and ultimo["tipo"] == FATTO:
            s["stato"], base = FATTO, ultimo
            s["fine"] = ultimo.get("ora")
        elif any(e["tipo"] == SALTATO for e in ev):
            s["stato"] = SALTATO
            base = [e for e in ev if e["tipo"] == SALTATO][-1]
        elif any(e["tipo"] == MANCATO for e in ev):
            s["stato"] = MANCATO
            base = [e for e in ev if e["tipo"] == MANCATO][-1]
        elif any(e["tipo"] == "inizio" for e in ev):
            s["stato"] = INIZIATO
        else:
            continue
        if base is not None:
            d = base.get("dati") or {}
            s["pagine"] = [int(x) for x in d.get("pagine") or () if str(x).isdecimal()]
            s["previsti"] = int(d["minuti"]) if str(d.get("minuti") or "").isdecimal() else None
            s["fase"] = d.get("fase")
        # L'inizio: l'ultimo «inizio» prima della fine (o l'ultimo, se il giorno non è chiuso)
        fine = _t(s["fine"]) if s["fine"] else None
        inizi = [e for e in ev if e["tipo"] == "inizio" and _t(e.get("ora"))
                 and (fine is None or _t(e["ora"]) <= fine)]
        if inizi and s["stato"] in (FATTO, INIZIATO):
            s["inizio"] = inizi[-1]["ora"]
            # Le pause (revisione della PR #321, nota 2): il tempo va dall'ultimo «inizio» prima
            # del «fatto»; se nel mezzo c'è un «non_fatto» il giorno è stato riaperto e chiuso di
            # nuovo, e la differenza conterebbe la pausa: niente tempo, che è la scelta onesta
            riaperto = fine is not None and any(
                e["tipo"] == "non_fatto" and _t(e.get("ora"))
                and _t(s["inizio"]) <= _t(e["ora"]) <= fine for e in ev)
            if fine is not None and not riaperto:
                secondi = (fine - _t(s["inizio"])).total_seconds()
                if 0 <= secondi <= DURATA_MAX_S:
                    s["minuti"] = max(1, int(round(secondi / 60)))
        out.append(s)
    return out


# ─────────────────────────── le frasi per la voce ───────────────────────────

def _resta(resta: dict, oggi, data) -> str:
    """«Restano 6 pagine in 4 giorni; domani le pagine 114–115.»"""
    p, g = int(resta.get("pagine") or 0), int(resta.get("giorni") or 0)
    pross = resta.get("prossimo")
    if p and g:
        frase = f"Restano {conta(p, 'pagina', 'pagine')} in {conta(g, 'giorno', 'giorni')}"
    elif p:
        frase = (f"Restano {conta(p, 'pagina', 'pagine')} e prima della verifica non ci sono "
                 "altri giorni nel piano")
    elif g:
        frase = (f"Le pagine sono tutte lette: {'resta' if g == 1 else 'restano'} "
                 f"{conta(g, 'giorno', 'giorni')} di ripasso")
    else:
        return f"Il piano è finito: la verifica è {quando(data, oggi)}."
    if resta.get("oggi_compreso") and g:
        frase += ", oggi compreso"
    if pross:
        cosa = ("il ripasso" if pross.get("fase") == P.RIPASSO
                else pagine_dette(pross.get("numeri") or []))
        frase += f"; {quando(pross['giorno'], oggi)} {cosa}"
    return frase + "."


def frase_resoconto(r: dict, oggi, nome: str | None = None) -> str:
    """La frase del resoconto di un giorno, dai soli dati (`Studio.resoconto`). Con `nome` (chi
    chiede o chi segna non è la persona della verifica: il tutore, revisione della PR #321) la
    frase è alla terza persona col nome del minore: «Oggi Leo ha letto…», mai «hai letto». Con
    `nome` vuoto (un profilo senza nome, #322) una forma impersonale: «Oggi è segnato fatto il
    giorno del piano…», «lo studio è stato saltato», «la sessione è cominciata…»."""
    q = quando(r["giorno"], oggi)
    Q = q[:1].upper() + q[1:]
    stato = r.get("stato")
    cosa = pagine_dette(r.get("numeri") or [])
    verbo = "ripassato" if r.get("fase") == P.RIPASSO else "letto"
    impersonale = nome is not None and not nome
    chi_ha = f"{nome} ha" if nome else "hai"
    di = f" di {nome}" if nome else ""
    tempo = f", in {durata_detta(r['minuti'])}" if r.get("minuti") else ""
    if stato == FATTO:
        prima = (f"{Q} è segnato fatto il giorno del piano: {cosa}{tempo}." if impersonale else
                 f"{Q} {chi_ha} {verbo} {cosa}{tempo}.")
    elif stato == SALTATO:
        prima = (f"{Q} {nome} ha saltato lo studio" if nome else
                 f"{Q} lo studio è stato saltato" if impersonale else
                 f"{Q} lo studio l'hai saltato") + ": le pagine sono passate ai giorni dopo."
    elif stato == MANCATO:
        prima = f"{Q} il giorno del piano{di} non è segnato fatto."
    elif stato == INIZIATO:
        prima = ((f"{Q} la sessione è cominciata" if impersonale else f"{Q} {chi_ha} cominciato")
                 + f" alle {ora_detta(r.get('inizio'))}, ma il giorno non è ancora segnato fatto.")
    elif stato == DA_FARE:
        da = "ripassare" if r.get("fase") == P.RIPASSO else "leggere"
        prima = (f"{Q} {nome} ha da {da} {cosa}" if nome else f"{Q} c'è da {da} {cosa}") + \
            f", {conta(int(r.get('previsti') or 0), 'minuto', 'minuti')}: non è ancora fatto."
    else:
        prima = f"{Q} nel piano{di} non c'era niente."
    return prima + " " + _resta(r.get("resta") or {}, oggi, r["data"])


def frase_riepilogo(r: dict, oggi, nome: str | None = None) -> str:
    """La frase del riepilogo di una verifica, dai soli dati (`Studio.riepilogo`): al più tre
    frasi brevi (principio 5)."""
    gg = r["giorni"]
    pezzi = [conta(gg["fatti"], "giorno fatto", "giorni fatti") if gg["fatti"]
             else "nessun giorno fatto"]
    if gg["saltati"]:
        pezzi.append(conta(gg["saltati"], "saltato", "saltati"))
    if gg["mancati"]:
        pezzi.append(conta(gg["mancati"], "non fatto", "non fatti"))
    pg, ar = r["pagine"], r["argomenti"]
    # Al tutore la materia col nome del minore (revisione della PR #321): «Storia di Leo, …»
    prima = (f"{r['materia']}{' di ' + nome if nome else ''}, {detta(r['data'])}: "
             f"{', '.join(pezzi)}; "
             f"pagine lette {pg['lette']} su {pg['totali']}")
    if ar["totali"]:
        prima += f", argomenti finiti {ar['finiti']} su {ar['totali']}"
    prima += "."
    m = int(r.get("giorni_mancanti") or 0)
    resto = pg["totali"] - pg["lette"]
    if m < 0:
        seconda = "La verifica è passata."
    elif m == 0:
        seconda = "La verifica è oggi."
    else:
        manca = "Manca 1 giorno" if m == 1 else f"Mancano {m} giorni"
        seconda = (f"{manca} e {conta(resto, 'pagina', 'pagine')}." if resto
                   else f"{manca} e le pagine sono tutte lette.")
    # Le lacune («mostrata», passo 5, #245) per numero nell'elenco, mai col titolo (0035 p. 24)
    lac = [int(x) for x in r.get("lacune") or () if isinstance(x, int)]
    if lac:
        seconda = seconda[:-1] + "; sotto l'obiettivo " + (
            f"l'argomento {lac[0]}." if len(lac) == 1 else
            "gli argomenti " + P._elenco([str(x) for x in lac]) + ".")
    frasi = [prima, seconda]
    pr = r.get("previsione")
    if pr:
        frasi.append(f"La previsione è fra {pr[0]} e {pr[1]}%.")
    elif r.get("ultima") is not None:
        frasi.append(f"L'ultima prova: {r['ultima']}%.")
    return " ".join(frasi)


# ─────────────────────────── le righe per lo schermo ───────────────────────────

STATI_SCHERMO = {FATTO: "fatto", SALTATO: "saltato", MANCATO: "non fatto",
                 INIZIATO: "cominciato, non segnato fatto"}


def riga_sessione(s: dict, attivita: str | None) -> str:
    """«giovedì 29 ottobre · 16:10–16:45, 35 min · Leggi le pagine 112–113.»"""
    parti = [detta(s["giorno"])]
    if s["stato"] == FATTO:
        if s.get("minuti"):
            parti.append(f"{ora_detta(s['inizio'])}–{ora_detta(s['fine'])}, {s['minuti']} min")
        else:
            parti.append(f"fatto alle {ora_detta(s['fine'])}"
                         + (f" (tempo non misurato, previsti {s['previsti']} min)"
                            if s.get("previsti") else " (tempo non misurato)"))
    elif s["stato"] == INIZIATO:
        parti.append(f"cominciato alle {ora_detta(s['inizio'])}, non segnato fatto")
    else:
        parti.append(STATI_SCHERMO.get(s["stato"], str(s["stato"])))
    if attivita:
        parti.append(attivita)
    return " · ".join(parti)


def righe_riepilogo(r: dict) -> list[str]:
    gg, pg, ar = r["giorni"], r["pagine"], r["argomenti"]
    out = []
    if gg["fatti"] or gg["saltati"] or gg["mancati"]:
        out.append("Giorni del piano: " + " · ".join(
            [f"{gg['fatti']} fatti" if gg["fatti"] != 1 else "1 fatto"]
            + ([f"{gg['saltati']} saltati" if gg["saltati"] != 1 else "1 saltato"]
               if gg["saltati"] else [])
            + ([f"{gg['mancati']} non fatti" if gg["mancati"] != 1 else "1 non fatto"]
               if gg["mancati"] else [])))
    else:
        out.append("Nessun giorno del piano ancora fatto.")
    riga = f"Pagine lette {pg['lette']} di {pg['totali']}"
    if ar["totali"]:
        riga += f" · argomenti finiti {ar['finiti']} di {ar['totali']}"
    out.append(riga + ".")
    m = int(r.get("giorni_mancanti") or 0)
    resto = pg["totali"] - pg["lette"]
    if m > 0:
        out.append(("Manca 1 giorno" if m == 1 else f"Mancano {m} giorni")
                   + (f" e {conta(resto, 'pagina', 'pagine')}." if resto
                      else ": le pagine sono tutte lette."))
    t = r.get("tempo") or {}
    if t.get("sessioni"):
        out.append(f"Tempo misurato: {durata_detta(t['minuti'])} in "
                   f"{conta(t['sessioni'], 'sessione', 'sessioni')}"
                   + (f"; {conta(t['senza'], 'giorno fatto', 'giorni fatti')} senza «Inizia», "
                      "il tempo lì non c'è." if t.get("senza") else "."))
    elif gg["fatti"]:
        out.append("Il tempo si misura quando la sessione comincia con «Inizia».")
    sp = r.get("spostata") or []
    if sp:
        out.append(f"Data spostata {conta(len(sp), 'volta', 'volte')}: all'inizio era "
                   f"{detta(sp[0]['da'])}.")
    return out
