"""
L'attrito della sicurezza come metrica (08/10/2026, fase 1 del progetto «sicurezza per
valore», docs/ricerche/2026-10-07-sicurezza-per-valore.md § 2.7).

Come la latenza (calliope/latenza.py): un numero per giorno dal registro dei turni
(calliope/turnlog.py), una soglia e un avviso. Il 07/10 la politica aveva fatto 15,8 domande di
sicurezza ogni 100 turni, 28 su 41 falsi positivi trovati a mano, e nessuno se n'era accorto
finché la persona non ha detto «quante volte te lo devo ripetere?».

Per ogni giorno:

- **`attrito`**: domande di sicurezza ogni 100 turni con una frase. Domanda di sicurezza = un
  turno in cui la risposta l'ha decisa una regola di sicurezza (`DOMANDE`: conferme, sfide e
  «Non me l'hai chiesto» della politica, blocchi dopo un dato letto; `RIFERIRE`: una frase
  fermata da ciò che dice; una frase di sfida chiesta). Le sfide d'identità della voce (senza un
  dato di mezzo: la frase non dice «c'è di mezzo…») si contano a parte (`voce`): dipendono
  dall'impronta, non dalla politica;
- **`ripetute`**: domande della politica per lo stesso tool e la stessa persona entro 5 minuti,
  dopo la prima. Con la memoria dell'intento (fase 2) deve essere 0;
- **`accettate`**: domande della politica seguite, entro 3 turni della stessa persona,
  dall'esecuzione riuscita dello stesso tool. È l'indizio automatico di un falso positivo (la
  persona voleva l'azione); sottostima, perché una volta in cui poi il tool fallisce o la
  persona rinuncia conta come «non accettata» (§ 2.7: 56 % automatico contro 68 % a mano);
- **`gia_detto`**: frasi della persona del tipo «te l'ho già detto», «quante volte». La cerca
  un'espressione solo per contare: non è una regola e non decide niente;
- **`ombra`** (fase 3): per le chiamate con il campo `politica_ombra` (la decisione che avrebbe
  preso la politica per valore, calliope/valore.py), le domande che non avrebbe fatto, quelle in
  più e le esecuzioni in più con un bersaglio preso da un dato (devono essere 0 per attivarla),
  e l'attrito simulato. Dal 09/10 (fase 4) la politica per valore è accesa e l'ombra è **al
  contrario** (`attiva` nel campo): `vera` è ciò che avrebbe deciso la politica di prima e
  `nuova` ciò che è successo davvero. Le domande evitate restano quelle che la politica di
  prima avrebbe fatto, le esecuzioni con un bersaglio dal dato sono **vere** (da guardare una
  per una), e `attrito_prima` è l'attrito che avrebbe avuto la politica di prima.

**Avviso** (decisione D6 di Dario, 08/10): `attrito` oltre `attrito_avviso` (3) ogni 100 turni
in un giorno con almeno `MIN_TURNI` (50) turni, oppure una domanda ripetuta. Obiettivo ≤ 2.

Solo lettura del registro, solo libreria standard, nessun testo nell'uscita.

    python -m calliope.stato --turni [--giorni N]
"""
from __future__ import annotations

import datetime
import re

MIN_TURNI = 50            # sotto, un giorno non fa statistica per l'avviso dell'attrito
RIPETUTA_S = 300          # stessa domanda per lo stesso tool e la stessa persona entro 5 minuti
ACCETTATA_TURNI = 3       # eseguito lo stesso tool entro 3 turni della stessa persona

DOMANDE = frozenset({
    "politica_conferma", "politica_sfida", "politica_azione_non_chiesta",
    "politica_azione_non_giustificata", "politica_argomento_esterno",
    "politica_argomento_non_detto", "politica_delega", "politica_cancellazione_non_chiesta",
    "politica_cambio_non_chiesto", "politica_azione_incoerente",
    # le guardie di prima del 06/10 (registri vecchi)
    "azione_non_chiesta", "immagine_azione_non_chiesta",
    "web_azione_bloccata",
    # la politica per valore, accesa dal 09/10 (calliope/valore.py): le regole che chiedono,
    # rifiutano o sfidano (valore_esegue, valore_voce e valore_lettura eseguono)
    "valore_non_ancorata", "valore_bersaglio_dato", "valore_contenuto_dato",
    "valore_contenuto_non_detto", "valore_dati_personali", "valore_e3_chiede",
    "valore_e4_sfida", "valore_consenso_sfida", "valore_sfida_classe"})
RIFERIRE = frozenset({"uscita_istruzione", "uscita_contatto", "uscita_segreti", "uscita_soldi",
                      "uscita_numero_pagamento"})
# «Te l'ho già detto», «quante volte», «ti ho detto di sì», «me lo chiedi ancora?»
GIA_DETTO = re.compile(r"quante volte|già detto|gia detto|ti ho detto|te l.ho detto|"
                       r"ho detto di s[iì]|me lo chiedi", re.I)


def _con_frase(t: dict) -> bool:
    """Un turno con una frase a cui Calliope ha risposto (anche di un ospite: senza testo, con
    il numero di parole)."""
    return t.get("esito") == "risposta" and bool(
        (isinstance(t.get("testo"), str) and t["testo"].strip()) or t.get("testo_parole"))


def _chi(t: dict):
    v = t.get("voce")
    return v.get("nome") if isinstance(v, dict) else None


def _tool(t: dict) -> list[dict]:
    return [x for x in (t.get("tool") or []) if isinstance(x, dict)]


def _quando(t: dict):
    try:
        return datetime.datetime.fromisoformat(str(t.get("inizio")))
    except ValueError:
        return None


def domanda(t: dict) -> str | None:
    """Il tipo di domanda di sicurezza del turno: "politica", "riferire", "voce" (sfida
    d'identità senza dato di mezzo) o None."""
    regole = set(t.get("regole") or ())
    risposta = str(t.get("risposta") or "")
    if regole & DOMANDE:
        return "politica"
    if "sfida_voce" in regole and "ripeti" in risposta.lower():
        return "politica" if "di mezzo" in risposta else "voce"
    if regole & RIFERIRE:
        return "riferire"
    return None


def giorno(turni: list[dict]) -> dict:
    """Le misure dell'attrito di un gruppo di turni (di solito un giorno), in ordine."""
    con_frase = [t for t in turni if _con_frase(t)]
    tipi = {"politica": 0, "riferire": 0, "voce": 0}
    ripetute = accettate = fermate = gia_detto = 0
    per_tool: dict[str, int] = {}
    ultima: dict[tuple, datetime.datetime] = {}
    for i, t in enumerate(turni):
        if isinstance(t.get("testo"), str) and GIA_DETTO.search(t["testo"]):
            gia_detto += 1
        tipo = domanda(t)
        if tipo is None:
            continue
        tipi[tipo] += 1
        if tipo != "politica":
            continue
        fermati = [x.get("nome") for x in _tool(t) if not x.get("ok")]
        if not fermati:
            continue
        tool = fermati[-1]
        fermate += 1
        per_tool[tool] = per_tool.get(tool, 0) + 1
        chi, quando = _chi(t), _quando(t)
        k = (tool, chi)
        if quando is not None and k in ultima and (quando - ultima[k]).total_seconds() < RIPETUTA_S:
            ripetute += 1
        if quando is not None:
            ultima[k] = quando
        dopo = [x for x in turni[i + 1:] if _chi(x) == chi][:ACCETTATA_TURNI]
        if any(e.get("nome") == tool and e.get("ok") for x in dopo for e in _tool(x)):
            accettate += 1
    n = len(con_frase)
    domande = tipi["politica"] + tipi["riferire"]
    ombra = _ombra(turni)
    # Con la politica per valore per tutto il giorno (le chiamate in ombra spenta cambiano) e
    # con quella di prima per tutto il giorno (cambiano quelle con la politica per valore attiva)
    simulate = max(0, domande - ombra["evitate_ombra"] + ombra["in_piu_ombra"])
    prima = max(0, domande + ombra["evitate_attiva"] - ombra["in_piu_attiva"])
    return {
        "turni": n, "domande": domande, **tipi,
        "attrito": round(100 * domande / n, 1) if n else None,
        "ripetute": ripetute, "fermate": fermate, "accettate": accettate,
        "accettate_quota": round(accettate / fermate, 2) if fermate else None,
        "gia_detto": gia_detto, "per_tool": dict(sorted(per_tool.items(), key=lambda x: -x[1])),
        "ombra": {**ombra, "attrito_simulato": (round(100 * simulate / n, 1)
                                                if n and ombra["chiamate"] else None),
                  "attrito_prima": (round(100 * prima / n, 1)
                                    if n and ombra["attive"] else None)},
    }


def _ombra(turni: list[dict]) -> dict:
    """Il confronto tra la decisione vera e quella della politica per valore (campo
    `politica_ombra` di ogni chiamata, calliope/valore.py). Per turno: una domanda evitata se
    la vera chiedeva e la nuova esegue; una in più se la vera eseguiva e la nuova chiedeva.
    Con `attiva` (dal 09/10) la «vera» è la politica di prima e la «nuova» quella che ha
    deciso: i conti restano gli stessi, divisi per sapere quale attrito simulare."""
    out = {"chiamate": 0, "attive": 0, "diverse": 0, "evitate": 0, "in_piu": 0,
           "dato_eseguite": 0, "evitate_ombra": 0, "in_piu_ombra": 0, "evitate_attiva": 0,
           "in_piu_attiva": 0}
    for t in turni:
        evitata = in_piu = attiva = False
        for e in _tool(t):
            o = e.get("politica_ombra")
            if not isinstance(o, dict):
                continue
            out["chiamate"] += 1
            if o.get("attiva"):
                out["attive"] += 1
                attiva = True
            # `finale` (dal 09/10 sera): la decisione dopo le correzioni a valle (sviluppo,
            # domanda non ripetuta); senza, la nuova della matrice
            vera, nuova = o.get("vera"), o.get("finale") or o.get("nuova")
            if vera != nuova:
                out["diverse"] += 1
            if vera in CHIEDE and nuova == "esegui":
                evitata = True
            if vera == "esegui" and nuova in CHIEDE:
                in_piu = True
            # Esecuzione in più con un bersaglio preso dal dato: il criterio per non attivarla
            if nuova == "esegui" and vera != "esegui" and "dato" in (o.get("bersagli") or ()):
                out["dato_eseguite"] += 1
        out["evitate"] += evitata
        out["in_piu"] += in_piu
        modo = "attiva" if attiva else "ombra"
        out["evitate_" + modo] += evitata
        out["in_piu_" + modo] += in_piu
    return out


CHIEDE = frozenset({"conferma", "sfida", "rifiuta"})


def per_giorno(turni: list[dict]) -> dict[str, dict]:
    gruppi: dict[str, list] = {}
    for t in turni:
        d = str(t.get("inizio") or "")[:10]
        if d:
            gruppi.setdefault(d, []).append(t)
    return {d: giorno(g) for d, g in sorted(gruppi.items())}


def avviso(d: dict, soglia: float = 3.0, data: str = "") -> str | None:
    """La frase d'avviso (D6): attrito oltre `soglia` ogni 100 turni con almeno MIN_TURNI
    turni, o una domanda ripetuta per lo stesso tool e la stessa persona. None altrimenti."""
    quando = f" del {data}" if data else ""
    parti = []
    if soglia > 0 and d["turni"] >= MIN_TURNI and d["attrito"] is not None \
            and d["attrito"] > soglia:
        parti.append(f"{_n(d['attrito'])} domande di sicurezza ogni 100 turni (soglia "
                     f"{_n(soglia)}), {d['accettate']} su {d['fermate']} poi eseguite")
    if d["ripetute"]:
        parti.append(f"{d['ripetute']} domande ripetute per la stessa azione entro 5 minuti")
    if not parti:
        return None
    return f"Attrito della sicurezza{quando}: " + "; ".join(parti) + "."


def _n(x) -> str:
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def testo(giorni: dict[str, dict], soglia: float = 3.0) -> str:
    """La tabella per il terminale (`calliope stato --turni`)."""
    if not giorni:
        return "Attrito della sicurezza: nessun turno nel registro."
    righe = ["Attrito della sicurezza (domande di sicurezza ogni 100 turni con una frase; "
             "le sfide d'identità della voce a parte)", ""]
    for data, d in giorni.items():
        riga = (f"{data}  {d['turni']} turni  {d['domande']} domande, attrito "
                f"{_n(d['attrito'])}  (politica {d['politica']}, ciò che dice {d['riferire']}"
                f", voce {d['voce']})")
        righe.append(riga)
        if d["fermate"] or d["gia_detto"]:
            q = d["accettate_quota"]
            righe.append(f"    poi eseguite {d['accettate']} su {d['fermate']}"
                         + (f" ({int(round(q * 100))} %)" if q is not None else "")
                         + f", ripetute entro 5 minuti {d['ripetute']}, «già detto» "
                         f"{d['gia_detto']}")
        if d["per_tool"]:
            righe.append("    per tool: " + ", ".join(f"{k} {v}" for k, v in
                                                     list(d["per_tool"].items())[:6]))
        o = d["ombra"]
        if o["attive"]:
            # Fase 4 (09/10): la politica per valore decide, l'ombra dice la politica di prima
            righe.append(f"    politica per valore attiva: {o['chiamate']} chiamate con un dato "
                         f"di mezzo, {o['diverse']} diverse dalla politica di prima, domande "
                         f"evitate {o['evitate']}, in più {o['in_piu']}, ESEGUITE con un "
                         f"bersaglio dal dato {o['dato_eseguite']}, attrito con la politica di "
                         f"prima {_n(o['attrito_prima'])}")
        elif o["chiamate"]:
            righe.append(f"    in ombra (politica per valore): {o['chiamate']} chiamate, "
                         f"{o['diverse']} diverse, domande evitate {o['evitate']}, in più "
                         f"{o['in_piu']}, eseguite con un bersaglio dal dato "
                         f"{o['dato_eseguite']}, attrito simulato {_n(o['attrito_simulato'])}")
        a = avviso(d, soglia)
        if a:
            righe.append("    ATTENZIONE: " + a)
    return "\n".join(righe)


def avviso_recente(cfg, oggi: datetime.date | None = None) -> str | None:
    """All'avvio e in `calliope stato`: l'avviso di oggi o di ieri. Non solleva mai."""
    try:
        from .latenza import leggi
        soglia = float(getattr(cfg, "attrito_avviso", 3.0) or 0)
        oggi = oggi or datetime.date.today()
        giorni = per_giorno(leggi(getattr(cfg, "turn_log_dir", None), 2))
        for data in (oggi.isoformat(), (oggi - datetime.timedelta(days=1)).isoformat()):
            if data in giorni:
                a = avviso(giorni[data], soglia, data)
                if a:
                    return a
    except Exception:  # noqa: BLE001 — un registro strano non ferma l'avvio
        pass
    return None
