"""
Passo 0 del registro degli eventi: la misura di oggi (10/10/2026, § 1 e § 8 del progetto
docs/ricerche/2026-10-10-registro-eventi.md).

Due contatori per turno, sul codice di oggi, da ciò che è andato alla voce (le frasi inviate e
`played`), dalla storia di Brain e dalle frasi dette:

- **parlato diverso** (`parlato_diverso`): la storia del modello non dice ciò che la persona ha
  sentito. I motivi sono i meccanismi del § 1.1: `filtri_frase` (la frase detta non è quella
  della storia), `claim_at` (una dichiarazione detta e tolta), `stop_non_detto` («Va bene, mi
  fermo.» scritto e mai detto), `interrotta_persa` (la frase a metà sentita e persa),
  `interrotta` (la storia ha di più dopo un'interruzione), `capito` (la frase della persona
  riscritta), `canale_scritto` (la storia non sa che la risposta era scritta),
  `non_in_storia:<atto>` (parole sentite in una conversazione viva che il modello non vede:
  agenda, avvisi ai tutori, registrazione della voce, «Sì?», «chi parla?»…),
  `storia_non_detta` (testo nella storia mai sentito). Le frasi d'attesa, il saluto
  dell'avvio, i giochi e le chiusure sono **voluti** e si contano a parte.
- **domande non registrate** (`domande_non_registrate`): frasi sentite che finiscono con «?»
  senza che si apra una proposta. Motivi del § 1.2: `testo_dopo_la_domanda`,
  `senza_in_sospeso`, `stato_a_parte` (cancello dei minori), `fuori_dalla_storia`,
  `annuncio_senza_proposta`, `ripeti`, `intendevi`. Il contenuto del modello che chiede senza
  un tool è un'offerta e si conta a parte (`offerte`).

Funzioni pure (nessun Brain, nessun ciclo): le chiama calliope/eventi/ombra.py con ciò che ha
osservato. Solo libreria standard.
"""
from __future__ import annotations

import re

# Le categorie degli atti (nome della fase del ciclo che ha parlato, eventi/ombra.py)
CONTENUTO = frozenset({"risposta"})
# Atti che oggi entrano nella storia (testuale, § 1.1 righe 3–8)
REGISTRATI = frozenset({"cortesia", "protezione_cancello", "annuncio", "richiesta_tutore",
                        "cassetto", "modulo"})
# Atti voluti fuori dalla conversazione del modello (si contano a parte)
VOLUTI = frozenset({"attesa", "saluto_avvio", "giochi", "chiusura"})
# Atti con una domanda che oggi vive fuori dalla storia (stati della corsia, § 1.2)
FUORI_STORIA = frozenset({"registrazione", "saluto", "chi_parla", "senza_domanda"})
ANNUNCI = frozenset({"annuncio", "agenda", "cassetto", "richiesta_tutore", "avviso_tutore"})

STOP = "Va bene, mi fermo. (argomento chiuso)"
RIPETI = re.compile(r"puoi ripetere la richiesta\?\s*$", re.I)
INTENDEVI = re.compile(r"^\s*intendevi\b", re.I)
_MARCHI = re.compile(r"\s*…?\s*\(interrotta\)\s*$")
# Le frasi dentro un pezzo detto (la voce riceve a volte due frasi brevi insieme)
_FRASI = re.compile(r"(?<=[.!?…])\s+")
_SPAZI = re.compile(r"\s+")


def norm(s: str) -> str:
    return _SPAZI.sub(" ", s or "").strip()


def senza_segno(s: str) -> str:
    return _MARCHI.sub("", norm(s)).strip()


def _resto_vuoto(s: str) -> bool:
    return not re.search(r"[^\W_]", s or "")


def motivi_parlato(sentite: list[tuple], storia: str, info: dict) -> list[str]:
    """I meccanismi per cui il testo dell'assistente nella storia (`storia`) non è ciò che si è
    sentito (`sentite`: [(testo, atto)], le frasi di una conversazione viva, voluti esclusi).
    `info`: esito del turno, interrotta, inviate e sentite del pezzo interrotto, regole,
    capito accettato, canale."""
    resto = senza_segno(storia)
    motivi: list[str] = []
    mancanti_contenuto = False
    for testo, atto in sentite:
        n = norm(testo)
        if not n:
            continue
        if n in resto:
            resto = resto.replace(n, " ", 1)
            continue
        if atto in CONTENUTO:
            mancanti_contenuto = True
            regole = set(info.get("regole") or ())
            motivi.append("claim_at" if {"spinta_dichiarata", "spinta_rinuncia"} & regole
                          else "filtri_frase")
        else:
            motivi.append(f"non_in_storia:{atto or 'altro'}")
    # Il resto della storia non sentito: solo per un turno nuovo (gli annunci fra un turno e
    # l'altro si attaccano a una risposta già contata), e non se è la frase del modello di cui
    # si è sentita la resa per la voce (già filtri_frase o claim_at)
    if not _resto_vuoto(resto) and info.get("turno_nuovo", True) and not mancanti_contenuto:
        if info.get("esito") == "interruzione" and STOP in (storia or ""):
            motivi.append("stop_non_detto")
        elif info.get("interrotta"):
            motivi.append("interrotta")
        else:
            motivi.append("storia_non_detta")
    if info.get("persa"):
        motivi.append("interrotta_persa")
    if info.get("capito"):
        motivi.append("capito")
    if info.get("canale") in ("scritto", "muta") and sentite:
        motivi.append("canale_scritto")
    return list(dict.fromkeys(motivi))


def motivo_domanda(testo: str, atto: str | None, info: dict) -> str | None:
    """Perché una frase sentita che finisce con «?» non è una proposta (None: è un'offerta del
    modello, contata a parte)."""
    if atto in FUORI_STORIA:
        return "fuori_dalla_storia"
    if atto in ANNUNCI:
        return "annuncio_senza_proposta"
    if atto not in CONTENUTO:
        return "fuori_dalla_storia" if atto in VOLUTI else "altro"
    if (info.get("cancello") or 0) == 1:
        return "stato_a_parte"
    if RIPETI.search(testo):
        return "ripeti"
    if INTENDEVI.search(testo):
        return "intendevi"
    n = norm(testo)
    for frase, sospeso in info.get("frasi_tool") or ():
        if n and n in norm(frase):
            return ("testo_dopo_la_domanda" if sospeso or info.get("offerta")
                    else "senza_in_sospeso")
    return None


def misura_finestra(pezzi: list[dict], storia: str, info: dict) -> dict:
    """Il passo 0 di un turno (o degli annunci fra un turno e l'altro).

    `pezzi`: i pezzi di voce della finestra, ognuno {"frasi": [(testo, atto, canale)],
    "sentite": k, "inviate": n, "interrotta": bool} (le prime k frasi sentite per intero);
    `storia`: il testo dell'assistente dell'ultimo turno nella storia di Brain;
    `info`: {"esito", "regole", "capito", "proposta_nuova", "frasi_tool", "cancello",
    "conversazione": False se la finestra non è in una conversazione viva}."""
    out: dict = {}
    sentite_conv: list[tuple] = []
    voluti: dict[str, int] = {}
    interrotta = persa = False
    canale = None
    ultime: list[tuple] = []          # (testo, atto) sentite, nell'ordine
    for p in pezzi:
        frasi = p.get("frasi") or []
        k = int(p.get("sentite", len(frasi)))
        if p.get("interrotta"):
            interrotta = True
            if k < len([f for f in frasi if f[1] not in VOLUTI]):
                persa = True
        for i, (testo, atto, can) in enumerate(frasi):
            if atto in VOLUTI:
                voluti[atto] = voluti.get(atto, 0) + 1
                continue
            if i >= k:
                continue
            if can in ("scritto", "muta"):
                canale = can
            sentite_conv.append((testo, atto))
            ultime.append((testo, atto))
    vive = info.get("conversazione", True)
    if voluti:
        out["voluti"] = voluti
    if not sentite_conv and info.get("esito") != "interruzione" and not info.get("capito"):
        return out
    out["sentite"] = len(sentite_conv)
    if vive:
        motivi = motivi_parlato(sentite_conv, storia,
                                {**info, "interrotta": interrotta, "persa": persa,
                                 "canale": canale})
    else:
        motivi = [f"non_in_storia:{a or 'altro'}" for _, a in sentite_conv]
        motivi = list(dict.fromkeys(motivi))
    if motivi:
        out["diverso"] = 1
        out["motivi"] = {m: 1 for m in motivi}
    # Domande
    registrate = non_reg = offerte = 0
    motivi_d: dict[str, int] = {}
    nuova = bool(info.get("proposta_nuova"))
    frasi = [(f, atto) for testo, atto in ultime for f in _FRASI.split(norm(testo)) if f]
    for i, (testo, atto) in enumerate(frasi):
        if not testo.endswith("?"):
            continue
        if nuova and i == len(frasi) - 1:
            registrate += 1
            continue
        m = motivo_domanda(testo, atto, info)
        if m is None:
            offerte += 1
        else:
            non_reg += 1
            motivi_d[m] = motivi_d.get(m, 0) + 1
    if registrate:
        out["domande_registrate"] = registrate
    if non_reg:
        out["domande_non_registrate"] = non_reg
        out["domande_motivi"] = motivi_d
    if offerte:
        out["offerte"] = offerte
    return out


# ─────────────────────────── riassunto per `calliope stato --turni` ───────────────────────────
def riassunto(turni: list[dict]) -> dict:
    """Per giorno, dai campi `parlato` (passo 0) ed `eventi_ombra` (passo 1) del registro dei
    turni."""
    giorni: dict[str, dict] = {}
    for t in turni:
        p, o = t.get("parlato"), t.get("eventi_ombra")
        if not isinstance(p, dict) and not isinstance(o, dict):
            continue
        g = giorni.setdefault(str(t.get("inizio") or "")[:10] or "?", {
            "turni": 0, "parlato_diverso": 0, "motivi": {}, "domande_non_registrate": 0,
            "domande_motivi": {}, "domande_registrate": 0, "offerte": 0, "voluti": {},
            "ombra": 0, "ombra_diversi": 0, "differenze": {}, "contesto_ms": [],
            "byte": [], "fughe": 0, "troncati": 0, "errori": 0, "porte": {},
            "dimentica": 0})
        if isinstance(p, dict):
            g["turni"] += 1
            g["parlato_diverso"] += int(p.get("diverso") or 0)
            for k, v in (p.get("motivi") or {}).items():
                g["motivi"][k] = g["motivi"].get(k, 0) + int(v or 0)
            g["domande_non_registrate"] += int(p.get("domande_non_registrate") or 0)
            for k, v in (p.get("domande_motivi") or {}).items():
                g["domande_motivi"][k] = g["domande_motivi"].get(k, 0) + int(v or 0)
            g["domande_registrate"] += int(p.get("domande_registrate") or 0)
            g["offerte"] += int(p.get("offerte") or 0)
            for k, v in (p.get("voluti") or {}).items():
                g["voluti"][k] = g["voluti"].get(k, 0) + int(v or 0)
        if isinstance(o, dict):
            g["ombra"] += 1
            diff = o.get("differenze") or {}
            if diff:
                g["ombra_diversi"] += 1
            for k, v in diff.items():
                g["differenze"][k] = g["differenze"].get(k, 0) + int(v or 0)
            if isinstance(o.get("contesto_ms"), (int, float)):
                g["contesto_ms"].append(float(o["contesto_ms"]))
            if isinstance(o.get("byte"), int):
                g["byte"].append(o["byte"])
            g["fughe"] += int(o.get("fughe") or 0)
            g["troncati"] += int(o.get("troncati") or 0)
            g["errori"] += int(o.get("errori") or 0)
            g["dimentica"] += int(o.get("dimentica") or 0)
            for k in o.get("porte") or ():
                g["porte"][k] = g["porte"].get(k, 0) + 1
    for g in giorni.values():
        ms = sorted(g.pop("contesto_ms"))
        g["contesto_ms"] = ({"n": len(ms), "mediana": ms[len(ms) // 2],
                             "p90": ms[min(len(ms) - 1, int(0.9 * len(ms)))], "max": ms[-1]}
                            if ms else {"n": 0})
        b = sorted(g.pop("byte"))
        g["byte_turno"] = ({"n": len(b), "mediana": b[len(b) // 2], "max": b[-1],
                            "totale": sum(b)} if b else {"n": 0})
    return dict(sorted(giorni.items()))


def _elenco(d: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])))


def testo(r: dict, contesto_ms_avviso: float = 20.0) -> str:
    """La sezione per il terminale (`calliope stato --turni`), con gli avvisi se non zero."""
    if not r:
        return ("Una voce sola (registro degli eventi, passi 0–1): nessun turno misurato nel "
                "registro.")
    righe = ["Una voce sola: ciò che si è sentito e la storia del modello (passo 0), registro "
             "degli eventi in ombra (passo 1)", ""]
    for data, g in r.items():
        righe.append(f"{data}  {g['turni']} turni  parlato diverso dalla storia "
                     f"{g['parlato_diverso']}  domande non registrate "
                     f"{g['domande_non_registrate']} (registrate {g['domande_registrate']}, "
                     f"offerte del modello {g['offerte']})")
        if g["motivi"]:
            righe.append(f"    parlato: {_elenco(g['motivi'])}")
        if g["domande_motivi"]:
            righe.append(f"    domande: {_elenco(g['domande_motivi'])}")
        if g["voluti"]:
            righe.append(f"    voluti fuori dalla storia: {_elenco(g['voluti'])}")
        if g["ombra"]:
            c, b = g["contesto_ms"], g["byte_turno"]
            righe.append(f"    ombra: {g['ombra']} turni confrontati, con differenze "
                         f"{g['ombra_diversi']}"
                         + (f"; contesto_ms mediana {c['mediana']:.2f}, p90 {c['p90']:.2f}, "
                            f"massimo {c['max']:.2f}" if c.get("n") else "")
                         + (f"; byte per turno mediana {b['mediana']}, massimo {b['max']}"
                            if b.get("n") else ""))
            if g["differenze"]:
                righe.append(f"    differenze per meccanismo: {_elenco(g['differenze'])}")
            extra = {k: g[k] for k in ("fughe", "troncati", "errori", "dimentica") if g[k]}
            if extra or g["porte"]:
                righe.append("    " + ", ".join(f"{k} {v}" for k, v in extra.items())
                             + (("; " if extra else "") + "porte: " + _elenco(g["porte"])
                                if g["porte"] else ""))
        if g["parlato_diverso"]:
            righe.append(f"    ATTENZIONE: in {g['parlato_diverso']} turni la storia del modello "
                         f"non dice ciò che la persona ha sentito (deve restare 0 dal passo 3)")
        if g["domande_non_registrate"]:
            righe.append(f"    ATTENZIONE: {g['domande_non_registrate']} domande dette senza "
                         f"una proposta (deve restare 0 dal passo 4)")
        c = g["contesto_ms"]
        if c.get("n") and c["max"] > contesto_ms_avviso:
            righe.append(f"    ATTENZIONE: la proiezione del contesto ha superato "
                         f"{contesto_ms_avviso:.0f} ms (massimo {c['max']:.1f} ms)")
        if g["fughe"]:
            righe.append(f"    ATTENZIONE: {g['fughe']} fughe nella proiezione (deve essere 0)")
    return "\n".join(righe)
