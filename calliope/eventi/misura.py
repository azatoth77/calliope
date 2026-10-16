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

**Il criterio di E1** (15/10, issue #11). In ombra `parlato.diverso` e `eventi_ombra.differenze`
non vanno a zero **per costruzione**: il primo misura la storia di Brain, che dei meccanismi del
§ 1.1 è fatta (`record_stop`, le frasi filtrate, gli atti `fuori_storia`…), il secondo conta
proprio le differenze fra la proiezione e quella storia. Il campo che si può misurare in ombra è
`eventi_ombra.proiezione_diversa`: lo stesso passo 0 fatto sulla proiezione degli eventi (ciò che
il modello vedrebbe con `attivo`, e vede dopo), senza i motivi dichiarati (`DICHIARATI`). Deve
valere 0 in ogni turno. Accanto, la **guardia dei riletti** (§ 10 punto 5): la mediana dei token
riletti dei turni con `attivo` contro quella dei giorni d'ombra (`guardia_riletti`).
"""
from __future__ import annotations

import re

from .tipi import ATTI, atti_di

# Le categorie degli atti: l'elenco chiuso di tipi.ATTI (dal passo 2 l'atto lo dice chi manda la
# frase all'uscita unica, calliope/eventi/uscita.py)
CONTENUTO = atti_di("risposta")
# Atti che oggi entrano nella storia (testuale, § 1.1 righe 3–8)
REGISTRATI = atti_di("registrato")
# Atti voluti fuori dalla conversazione del modello (si contano a parte)
VOLUTI = atti_di("voluto")
# Atti sentiti in una conversazione viva che oggi la storia non ha (§ 1.1): il loro
# `non_in_storia:<atto>` è atteso fino al passo 3
FUORI_STORIA = atti_di("fuori_storia")
ANNUNCI = frozenset(n for n, (_c, annuncio, _r) in ATTI.items() if annuncio)


# Motivi del passo 0 che non dicono una frase sentita diversa da quella della storia: la frase
# della persona riscritta e accettata (la proiezione usa quella capita, `trascrizione_capita`) e
# il canale scritto (né la storia né la proiezione dicono al modello che la risposta era scritta:
# limite dichiarato del § 1.1, non risolto dal passo 3). Si contano, fuori dal criterio di E1
DICHIARATI = frozenset({"capito", "canale_scritto"})


def proiezione_diversa(parlato: dict) -> tuple[int, dict]:
    """Dal passo 0 misurato sulla proiezione (`Ombra._parlato_attivo`): (1 se la proiezione non
    dice ciò che si è sentito, motivi). Il criterio di E1: 0 in ogni turno."""
    motivi = dict(parlato.get("motivi") or {})
    return (1 if any(m not in DICHIARATI for m in motivi) else 0), motivi


def atteso(motivo: str) -> bool:
    """Un motivo `non_in_storia:<atto>` è atteso (l'atto oggi non entra nella storia, § 1.1)
    o no (un atto che dovrebbe esserci, o un atto fuori dall'elenco: da guardare)."""
    if not motivo.startswith("non_in_storia:"):
        return True
    return motivo.split(":", 1)[1] in FUORI_STORIA

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
            motivi.append(f"non_in_storia:{atto or 'sconosciuto'}")
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
    if atto in ANNUNCI:
        return "annuncio_senza_proposta"
    if atto in FUORI_STORIA or atto in VOLUTI:
        return "fuori_dalla_storia"
    if atto in REGISTRATI:
        return "atto_senza_proposta"
    if atto not in CONTENUTO:
        return "atto_sconosciuto"
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
        motivi = [f"non_in_storia:{a or 'sconosciuto'}" for _, a in sentite_conv]
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
        ca = t.get("cache") if isinstance(t.get("cache"), dict) else None
        if not isinstance(p, dict) and not isinstance(o, dict) and ca is None:
            continue
        g = giorni.setdefault(str(t.get("inizio") or "")[:10] or "?", {
            "turni": 0, "parlato_diverso": 0, "motivi": {}, "domande_non_registrate": 0,
            "domande_motivi": {}, "domande_registrate": 0, "offerte": 0, "voluti": {},
            "ombra": 0, "ombra_diversi": 0, "differenze": {}, "contesto_ms": [],
            "byte": [], "fughe": 0, "troncati": 0, "errori": 0, "porte": {},
            "dimentica": 0, "attivo": 0, "riletti": [], "stimati": [], "cache_rotta": 0,
            "proiezione_ms": [], "proiezione": 0, "proiezione_diversa": 0,
            "proiezione_motivi": {}})
        if ca is not None:
            # La cache del prefisso (passo 3, § 10 punto 5): riletti dal motore e stimati
            if isinstance(ca.get("riletti"), int):
                g["riletti"].append(ca["riletti"])
            if isinstance(ca.get("riletti_stimati"), int):
                g["stimati"].append(ca["riletti_stimati"])
            g["cache_rotta"] += 1 if ca.get("rotta") else 0
            if isinstance(ca.get("proiezione_ms"), (int, float)):
                g["proiezione_ms"].append(float(ca["proiezione_ms"]))
            g["fughe"] += int(ca.get("fughe") or 0)
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
            g["attivo"] += 1 if o.get("modo") == "attivo" else 0
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
            # Il criterio di E1 (15/10): il passo 0 sulla proiezione, in ombra e con attivo
            if "proiezione_diversa" in o:
                g["proiezione"] += 1
                g["proiezione_diversa"] += 1 if o.get("proiezione_diversa") else 0
                for k, v in (o.get("proiezione_motivi") or {}).items():
                    g["proiezione_motivi"][k] = g["proiezione_motivi"].get(k, 0) + int(v or 0)
    for g in giorni.values():
        ms = sorted(g.pop("contesto_ms"))
        g["contesto_ms"] = ({"n": len(ms), "mediana": ms[len(ms) // 2],
                             "p90": ms[min(len(ms) - 1, int(0.9 * len(ms)))], "max": ms[-1]}
                            if ms else {"n": 0})
        b = sorted(g.pop("byte"))
        g["byte_turno"] = ({"n": len(b), "mediana": b[len(b) // 2], "max": b[-1],
                            "totale": sum(b)} if b else {"n": 0})
        for k in ("riletti", "stimati", "proiezione_ms"):
            v = sorted(g.pop(k))
            g[k] = ({"n": len(v), "mediana": v[len(v) // 2],
                     "p90": v[min(len(v) - 1, int(0.9 * len(v)))], "max": v[-1]}
                    if v else {"n": 0})
    return dict(sorted(giorni.items()))


# ─────────────────────── la guardia dei riletti (§ 10 punto 5, issue #11) ───────────────────────
RILETTI_MARGINE = 0.5        # «supera di metà» la mediana dei giorni d'ombra
RILETTI_MIN_BASE = 20        # turni d'ombra con i riletti perché la base valga
RILETTI_MIN_GIORNO = 10      # turni con `attivo` in un giorno perché la sua mediana conti


def _mediana(v: list):
    v = sorted(v)
    return v[len(v) // 2]


def guardia_riletti(turni: list[dict]) -> dict:
    """La guardia della cache del prefisso dopo l'accensione: la base è la mediana dei token
    riletti dei turni d'ombra (`eventi_ombra` senza `modo: attivo`, da tutti i giorni letti);
    per ogni giorno, la mediana dei turni con `attivo` contro base × (1 + RILETTI_MARGINE).
    I riletti veri dal motore (`cache.riletti`) se la base ne ha abbastanza, se no gli stimati
    (`cache.riletti_stimati`, il backend che non li dice). Pura."""
    base: dict[str, list] = {"riletti": [], "stimati": []}
    giorni_base: set = set()
    turni_base = 0
    attivi: dict[str, dict] = {}
    for t in turni:
        o, ca = t.get("eventi_ombra"), t.get("cache")
        if not isinstance(o, dict) or not isinstance(ca, dict):
            continue
        data = str(t.get("inizio") or "")[:10] or "?"
        if o.get("modo") == "attivo":
            dest = attivi.setdefault(data, {"riletti": [], "stimati": []})
        else:
            dest = base
            giorni_base.add(data)
            turni_base += 1
        for k, campo in (("riletti", "riletti"), ("stimati", "riletti_stimati")):
            v = ca.get(campo)
            if isinstance(v, int) and not isinstance(v, bool):
                dest[k].append(v)
    # I riletti del motore se bastano; se no gli stimati se bastano; se no quelli che sono di più
    nr, ns = len(base["riletti"]), len(base["stimati"])
    campo = ("riletti" if nr >= RILETTI_MIN_BASE or (ns < RILETTI_MIN_BASE and nr >= ns)
             else "stimati")
    b = base[campo]
    out: dict = {"campo": campo, "base": {"n": len(b), "turni": turni_base,
                                          "giorni": sorted(giorni_base)},
                 "giorni": {}, "avvisi": []}
    soglia = None
    if len(b) >= RILETTI_MIN_BASE:
        out["base"]["mediana"] = _mediana(b)
        soglia = out["soglia"] = round(out["base"]["mediana"] * (1 + RILETTI_MARGINE), 1)
    for data, d in sorted(attivi.items()):
        v = d[campo]
        voce: dict = {"n": len(v)}
        if v:
            voce["mediana"] = _mediana(v)
        if soglia is not None and len(v) >= RILETTI_MIN_GIORNO and voce["mediana"] > soglia:
            voce["avviso"] = True
            out["avvisi"].append(data)
        out["giorni"][data] = voce
    return out


def testo_guardia(gr: dict | None) -> list[str]:
    """Le righe della guardia dei riletti per `calliope stato --turni`."""
    if not gr:
        return []
    nome = "riletti dal motore" if gr["campo"] == "riletti" else "riletti stimati"
    b = gr["base"]
    if "mediana" not in b:
        righe = [f"Guardia dei riletti (§ 10 punto 5): base dei giorni d'ombra con "
                 f"{b.get('turni', b['n'])} turni, {b['n']} con i {nome} (ne servono "
                 f"{RILETTI_MIN_BASE}): ancora nessun confronto."]
    else:
        righe = [f"Guardia dei riletti (§ 10 punto 5): base dei giorni d'ombra mediana "
                 f"{b['mediana']} token ({nome}, {b['n']} turni, "
                 f"{len(b['giorni'])} giorni); avviso oltre {gr['soglia']:g} con eventi: attivo."]
    for data, v in gr["giorni"].items():
        righe.append(f"    {data}  con eventi: attivo {v['n']} turni"
                     + (f", mediana {v['mediana']} token" if "mediana" in v else "")
                     + (f" (ne servono {RILETTI_MIN_GIORNO} per il confronto)"
                        if v["n"] < RILETTI_MIN_GIORNO else ""))
        if v.get("avviso"):
            righe.append(f"    ATTENZIONE: con eventi: attivo la mediana dei token riletti "
                         f"({v['mediana']}) supera di più di metà quella dei giorni d'ombra "
                         f"({b['mediana']}): la cache del prefisso si rompe (tornare a "
                         f"`eventi: ombra` e guardare `cache_rotta` e le righe della stanza)")
    return righe


def avviso_riletti(cfg, oggi=None) -> str | None:
    """Per `calliope stato` senza opzioni, come gli altri avvisi della pagina: oggi o ieri (il
    primo dei due con almeno RILETTI_MIN_GIORNO turni con `attivo`), l'avviso della guardia dei
    riletti di quel giorno, o None. Si leggono i due file di oggi e ieri; il registro intero
    (per la base dei giorni d'ombra) solo se uno dei due ha abbastanza turni con `attivo`. Non
    solleva."""
    import datetime
    try:
        from .. import latenza
        cartella = getattr(cfg, "turn_log_dir", None)
        oggi = oggi or datetime.date.today()
        date = (oggi.isoformat(), (oggi - datetime.timedelta(days=1)).isoformat())
        if not cartella:
            return None
        from pathlib import Path
        recenti = [t for d in date
                   for t in latenza.leggi_file(Path(cartella) / f"turni-{d}.jsonl")
                   if str(t.get("inizio") or "")[:10] in date
                   and (t.get("eventi_ombra") or {}).get("modo") == "attivo"]
        per_data = {d: sum(1 for t in recenti if str(t.get("inizio"))[:10] == d) for d in date}
        data = next((d for d in date if per_data[d] >= RILETTI_MIN_GIORNO), None)
        if data is None:
            return None
        gr = guardia_riletti(latenza.leggi(cartella))
        if data in gr["avvisi"]:
            return (f"Registro degli eventi acceso: {'oggi' if data == date[0] else 'ieri'} la "
                    f"mediana dei token riletti ({gr['giorni'][data]['mediana']}) supera di più "
                    f"di metà quella dei giorni d'ombra ({gr['base']['mediana']}).")
    except Exception:  # noqa: BLE001 — un registro strano non ferma niente
        pass
    return None


def criterio_e1(turni: list[dict]) -> dict:
    """Il criterio di E1 su tutto il registro letto (non solo `--giorni`): quanti turni hanno
    il campo `eventi_ombra.proiezione_diversa`, quanti con un valore > 0, da che giorno."""
    con = [t for t in turni if isinstance(t.get("eventi_ombra"), dict)
           and "proiezione_diversa" in t["eventi_ombra"]]
    date = sorted(str(t.get("inizio") or "")[:10] for t in con)
    return {"turni": len(con),
            "diversi": sum(1 for t in con if t["eventi_ombra"]["proiezione_diversa"]),
            **({"dal": date[0]} if date else {})}


def testo_e1(e1: dict | None) -> list[str]:
    if not e1:
        return []
    riga = (f"Criterio di E1 su tutto il registro: {e1['turni']} turni col campo "
            f"eventi_ombra.proiezione_diversa" + (f" (dal {e1['dal']})" if e1.get("dal") else "")
            + f", di cui {e1['diversi']} con proiezione_diversa > 0 (servono almeno 200 turni, "
            f"tutti a 0).")
    return [riga]


def _elenco(d: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])))


def testo(r: dict, contesto_ms_avviso: float = 20.0, guardia: dict | None = None,
          e1: dict | None = None) -> str:
    """La sezione per il terminale (`calliope stato --turni`), con gli avvisi se non zero;
    in fondo `e1` (il criterio su tutto il registro, `criterio_e1`) e `guardia` (la guardia
    dei riletti, `guardia_riletti`)."""
    if not r:
        return "\n".join(["Una voce sola (registro degli eventi, passi 0–1): nessun turno "
                          "misurato nel registro."] + testo_e1(e1) + testo_guardia(guardia))
    righe = ["Una voce sola: ciò che si è sentito e la storia del modello (passo 0), registro "
             "degli eventi in ombra (passo 1)", ""]
    for data, g in r.items():
        righe.append(f"{data}  {g['turni']} turni  parlato diverso dalla storia "
                     f"{g['parlato_diverso']}  domande non registrate "
                     f"{g['domande_non_registrate']} (registrate {g['domande_registrate']}, "
                     f"offerte del modello {g['offerte']})")
        if g["motivi"]:
            righe.append(f"    parlato: {_elenco(g['motivi'])}")
            # Ogni non_in_storia è di un atto dell'elenco (passo 2): atteso se l'atto oggi non
            # entra nella storia (§ 1.1), altrimenti da guardare
            inattesi = {k: v for k, v in g["motivi"].items() if not atteso(k)}
            if inattesi:
                righe.append(f"    ATTENZIONE: parole sentite fuori dalla storia per atti che "
                             f"dovrebbero esserci: {_elenco(inattesi)}")
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
        if g["proiezione"]:
            righe.append(f"    criterio di E1: proiezione degli eventi diversa da ciò che si è "
                         f"sentito in {g['proiezione_diversa']} turni su {g['proiezione']}"
                         + (f" (motivi: {_elenco(g['proiezione_motivi'])})"
                            if g["proiezione_motivi"] else ""))
        if g["parlato_diverso"]:
            righe.append(f"    ATTENZIONE: in {g['parlato_diverso']} turni la storia del modello "
                         f"non dice ciò che la persona ha sentito (deve restare 0 dal passo 3)")
        if g["proiezione_diversa"]:
            righe.append(f"    ATTENZIONE: in {g['proiezione_diversa']} turni la proiezione degli "
                         f"eventi non dice ciò che la persona ha sentito "
                         f"(eventi_ombra.proiezione_diversa: deve restare 0 per accendere "
                         f"eventi: attivo, E1)")
        if g["domande_non_registrate"]:
            righe.append(f"    ATTENZIONE: {g['domande_non_registrate']} domande dette senza "
                         f"una proposta (deve restare 0 dal passo 4)")
        c = g["contesto_ms"]
        if c.get("n") and c["max"] > contesto_ms_avviso:
            righe.append(f"    ATTENZIONE: la proiezione del contesto ha superato "
                         f"{contesto_ms_avviso:.0f} ms (massimo {c['max']:.1f} ms)")
        r_, s_, pm = g["riletti"], g["stimati"], g["proiezione_ms"]
        if r_.get("n") or s_.get("n") or g["cache_rotta"]:
            righe.append("    cache del prefisso: "
                         + (f"riletti dal motore mediana {r_['mediana']} token (p90 {r_['p90']}); "
                            if r_.get("n") else "")
                         + (f"stimati mediana {s_['mediana']} (p90 {s_['p90']}); "
                            if s_.get("n") else "")
                         + f"cache_rotta {g['cache_rotta']}"
                         + (f"; contesto dagli eventi in {g['attivo']} turni, proiezione nella "
                            f"risposta mediana {pm['mediana']:.2f} ms, massimo {pm['max']:.2f}"
                            if pm.get("n") else ""))
        if g["cache_rotta"]:
            righe.append(f"    ATTENZIONE: in {g['cache_rotta']} turni la richiesta è cambiata "
                         f"dentro i turni definitivi (cache_rotta: deve restare 0)")
        if pm.get("n") and pm["max"] > contesto_ms_avviso:
            righe.append(f"    ATTENZIONE: la proiezione nella risposta ha superato "
                         f"{contesto_ms_avviso:.0f} ms (massimo {pm['max']:.1f} ms)")
        if g["fughe"]:
            righe.append(f"    ATTENZIONE: {g['fughe']} fughe nella proiezione (deve essere 0)")
    g_righe = testo_e1(e1) + testo_guardia(guardia)
    return "\n".join(righe + ([""] + g_righe if g_righe else []))
