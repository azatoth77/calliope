"""
La latenza vera della voce come metrica (06/10/2026, proposta P4 di
docs/ricerche/2026-10-06-analisi-complessiva.md).

Dal 02 al 05/10 la prima frase sulla DGX è passata da 0,78 a 2,05 s di mediana e nessuno l'ha
visto finché non l'ha sentito: i banchi misurano la richiesta al modello con il prefisso in
cache, i turni veri hanno anche STT, correzione, guardiano, tool e riletture senza cache. Qui,
dal registro dei turni (calliope/turnlog.py), per ogni giorno:

- **prima frase** (`prima_frase_s`, da `t0`: audio già chiuso dal VAD) mediana, p75, p90;
- **dalla fine del parlato** (`fine_parlato_s`, dal 06/10: comprende il silenzio con cui il VAD
  chiude la frase);
- la **prima voce sentita** (`prima_voce_s`, dal 06/10: quando il satellite, o le casse locali,
  cominciano davvero a suonare la prima frase, anche quella d'attesa; da `t0` come la prima
  frase), e la stessa dalla fine del parlato: la latenza che si sente, con sintesi, rete e
  riproduzione;
- il **distacco** tra il testo pronto e la voce sentita (07/10: `prima_voce_s − prima_frase_s`
  nei turni senza frase d'attesa), scomposto con `voce_pronta_s` (il primo audio uscito da
  Piper) in **sintesi** (coda e Piper) e **consegna** (rete, buffer e uscita del satellite);
- le **cause**: STT, correzione della trascrizione (`stt_correzione_ms`, scadute), guardiano
  (minori e ospiti), tool nel turno, rilettura del prompt (`lettura_s`, dal 06/10: oltre 1 s
  la cache del prefisso non è servita), contesto (token), coda delle risposte;
- la **base**: la prima frase dei turni senza tool, guardiano né correzione;
- la **generazione** (`generazione_tps`, dal 08/10, fase 0 della taratura): token al secondo
  del modello nel turno (Ollama `eval_count / eval_duration`; vLLM dal primo all'ultimo
  pezzo), mediana e p10 (i turni più lenti: contesa con l'agente, modello in parte sulla CPU);
- la **cache del prefisso** (16/10, issue #95): turni in cui il motore ha riletto molto più
  della stima della guardia (`cache.riletti` oltre `CACHE_PERSA_VOLTE` × `riletti_stimati` +
  `CACHE_PERSA_MARGINE`: la cache si è persa, anche se la lettura resta sotto 1 s) e i **dati
  del turno** (`dati_turno_token`: ciò che il motore deve riavvolgere alla richiesta dopo), coi
  turni oltre `dati_turno_tetto_token`;
- un **avviso** se la mediana del giorno supera `latenza_avviso_s` (1,2 s) con almeno
  `MIN_RISPOSTE` risposte: all'avvio di Calliope e in `calliope stato`.

Solo lettura del registro, solo libreria standard: gira anche su una macchina appena installata.

    python -m calliope.stato --turni [--giorni N]
"""
from __future__ import annotations

import datetime
from pathlib import Path

MIN_RISPOSTE = 10          # sotto, un giorno non fa statistica (e non dà avvisi)
LETTURA_LENTA_S = 1.0      # rilettura del prompt oltre questo: cache del prefisso persa
# Riletti dal motore oltre questo multiplo della stima della guardia (più un margine per le
# passate con un tool e il modo di contare di Ollama): la cache del prefisso si è persa
CACHE_PERSA_VOLTE = 1.3
CACHE_PERSA_MARGINE = 300


def _q(valori: list[float], p: float) -> float | None:
    """Quantile «del più vicino» (come nel rapporto del 06/10): niente interpolazioni."""
    v = sorted(x for x in valori if isinstance(x, (int, float)))
    if not v:
        return None
    return v[min(len(v) - 1, int(p * len(v)))]


def _med(valori) -> float | None:
    v = sorted(x for x in valori if isinstance(x, (int, float)))
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _num(t: dict, k: str) -> float | None:
    x = t.get(k)
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _tool(t: dict) -> bool:
    return bool(t.get("tool"))


def _lettura(t: dict) -> float | None:
    x = t.get("lettura_s")
    if x is None and isinstance(t.get("contesto"), dict):
        x = t["contesto"].get("lettura_s")
    return float(x) if isinstance(x, (int, float)) else None


def cache_persa(t: dict) -> bool | None:
    """La cache del prefisso si è persa in questo turno (16/10, issue #95): il motore ha riletto
    molto più dei messaggi cambiati dalla richiesta di prima. None se il turno non lo dice (il
    primo della conversazione, niente misura)."""
    c = t.get("cache") if isinstance(t.get("cache"), dict) else {}
    r, st = c.get("riletti"), c.get("riletti_stimati")
    if c.get("prima") or not isinstance(r, int) or not isinstance(st, int):
        return None
    return r > CACHE_PERSA_VOLTE * st + CACHE_PERSA_MARGINE


def giorno(turni: list[dict]) -> dict:
    """Le misure di un gruppo di turni (di solito un giorno)."""
    r = [t for t in turni if _num(t, "prima_frase_s") is not None]
    pf = [_num(t, "prima_frase_s") for t in r]
    fp = [_num(t, "fine_parlato_s") for t in r if _num(t, "fine_parlato_s") is not None]
    pv = [_num(t, "prima_voce_s") for t in r if _num(t, "prima_voce_s") is not None]
    # Dal testo alla voce (07/10): solo i turni in cui la prima voce è la prima frase (con la
    # frase d'attesa la voce arriva prima del testo e il distacco non ha senso)
    dist, sint, cons = [], [], []
    for t in r:
        f, v, p = (_num(t, "prima_frase_s"), _num(t, "prima_voce_s"),
                   _num(t, "voce_pronta_s"))
        if v is None or v < f:
            continue
        dist.append(v - f)
        if p is not None and f <= p <= v:
            sint.append(p - f)
            cons.append(v - p)
    # Dalla fine del parlato: prima voce + il silenzio finale (fine_parlato_s − prima_frase_s)
    sentita = [_num(t, "prima_voce_s") + _num(t, "fine_parlato_s") - _num(t, "prima_frase_s")
               for t in r if _num(t, "prima_voce_s") is not None
               and _num(t, "fine_parlato_s") is not None]
    stt = [_num(t, "stt_s") for t in r if _num(t, "stt_s") is not None]
    corr = [t for t in r if _num(t, "stt_correzione_ms") is not None]
    guard = [t for t in r if t.get("guardiano")]
    con_tool = [t for t in r if _tool(t)]
    senza_tool = [t for t in r if not _tool(t)]
    letture = [x for x in (_lettura(t) for t in r) if x is not None]
    gen = [_num(t, "generazione_tps") for t in r if _num(t, "generazione_tps")]
    token = [t["contesto"].get("token") for t in r if isinstance(t.get("contesto"), dict)]
    coda = [_num(t, "coda_s") for t in r if _num(t, "coda_s")]
    persa = [x for x in (cache_persa(t) for t in r) if x is not None]
    dati = [t["dati_turno_token"] for t in r if isinstance(t.get("dati_turno_token"), int)]
    base = [_num(t, "prima_frase_s") for t in r
            if not _tool(t) and not t.get("guardiano") and _num(t, "stt_correzione_ms") is None]
    # Quanto le schede trattenute hanno aspettato il giudizio del guardiano (06/10, il costo
    # dei minori sugli schermi: Brain.rilascia_schede, nel registro dentro «guardiano»)
    attese = [x for x in (t["guardiano"].get("schede_attesa_ms") for t in guard
                          if isinstance(t["guardiano"], dict))
              if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return {
        "turni": len(turni), "risposte": len(r),
        "prima_frase": {"mediana": _med(pf), "p75": _q(pf, .75), "p90": _q(pf, .9)},
        "fine_parlato": {"n": len(fp), "mediana": _med(fp), "p90": _q(fp, .9)},
        "prima_voce": {"n": len(pv), "mediana": _med(pv), "p90": _q(pv, .9),
                       "sentita": _med(sentita), "sentita_p90": _q(sentita, .9),
                       "distacco": _med(dist), "distacco_p90": _q(dist, .9),
                       "sintesi": _med(sint), "consegna": _med(cons), "n_scomposti": len(sint)},
        "stt": {"mediana": _med(stt), "p90": _q(stt, .9)},
        "correzione": {"n": len(corr),
                       "ms_mediana": _med([_num(t, "stt_correzione_ms") for t in corr]),
                       "scadute": sum(1 for t in corr if t.get("stt_correzione_scaduta")),
                       "cambiate": sum(1 for t in r if t.get("stt_corretta"))},
        "guardiano": {"n": len(guard),
                      "prima_frase": _med([_num(t, "prima_frase_s") for t in guard]),
                      # Guardiano o rilevatore di pericolo senza giudizio sulla domanda (Q3
                      # dell'analisi del 06/10): per i minori la risposta è la frase di guasto
                      "guasti": sum(1 for t in guard if isinstance(t["guardiano"], dict)
                                    and t["guardiano"].get("guasto")),
                      "pericolo_ms": _med([t["guardiano"].get("pericolo_ms") for t in guard
                                           if isinstance(t["guardiano"], dict)])},
        "tool": {"n": len(con_tool),
                 "con": _med([_num(t, "prima_frase_s") for t in con_tool]),
                 "senza": _med([_num(t, "prima_frase_s") for t in senza_tool])},
        "lettura": {"n": len(letture), "mediana": _med(letture),
                    "lente": sum(1 for x in letture if x > LETTURA_LENTA_S)},
        "generazione": {"n": len(gen), "mediana": _med(gen), "p10": _q(gen, .1)},
        "contesto": {"token_mediana": _med(token)},
        "coda": {"n": len(coda), "mediana": _med(coda)},
        "cache": {"n": len(persa), "perse": sum(persa)},
        "dati_turno": {"n": len(dati), "mediana": _med(dati), "p90": _q(dati, .9),
                       "oltre": sum(1 for t in r if t.get("dati_turno_oltre"))},
        "base": {"n": len(base), "mediana": _med(base)},
        "schede_attesa": {"n": len(attese), "ms_mediana": _med(attese),
                          "ms_p90": _q(attese, .9), "ms_max": max(attese) if attese else None},
    }


def per_giorno(turni: list[dict]) -> dict[str, dict]:
    gruppi: dict[str, list] = {}
    for t in turni:
        d = str(t.get("inizio") or "")[:10]
        if d:
            gruppi.setdefault(d, []).append(t)
    return {d: giorno(g) for d, g in sorted(gruppi.items())}


def avviso(d: dict, soglia: float = 1.2, data: str = "") -> str | None:
    """La frase d'avviso se la mediana della prima frase supera `soglia` (con abbastanza
    risposte), con le cause più grandi; None altrimenti."""
    med = d["prima_frase"]["mediana"]
    if d["risposte"] < MIN_RISPOSTE or med is None or med <= soglia:
        return None
    cause = []
    c = d["correzione"]
    if c["n"]:
        cause.append(f"correzione della trascrizione su {c['n']} frasi "
                     f"({_s(c['ms_mediana'] / 1000 if c['ms_mediana'] else None)})")
    if d["guardiano"]["n"]:
        cause.append(f"guardiano su {d['guardiano']['n']} turni "
                     f"(prima frase {_s(d['guardiano']['prima_frase'])})")
    if d["tool"]["n"]:
        cause.append(f"tool in {d['tool']['n']} turni ({_s(d['tool']['con'])} contro "
                     f"{_s(d['tool']['senza'])})")
    if d["lettura"]["lente"]:
        cause.append(f"rilettura oltre {_s(LETTURA_LENTA_S)} in {d['lettura']['lente']} turni")
    ca = d.get("cache") or {}
    if ca.get("perse"):
        cause.append(f"cache del prefisso persa in {ca['perse']} turni su {ca['n']}")
    dt = d.get("dati_turno") or {}
    if dt.get("oltre"):
        cause.append(f"dati del turno oltre il tetto in {dt['oltre']} turni")
    quando = f" del {data}" if data else ""
    return (f"La prima frase{quando} ha mediana {_s(med)} (soglia {_s(soglia)}, p90 "
            f"{_s(d['prima_frase']['p90'])}, base {_s(d['base']['mediana'])})"
            + (": " + "; ".join(cause) if cause else "") + ".")


def avviso_guasti(d: dict, data: str = "") -> str | None:
    """La frase d'avviso se guardiano o rilevatore di pericolo non hanno giudicato la domanda
    in qualche turno (anche uno solo: per i minori è una risposta mancata, e un rilevatore
    spento per ore il 05/10 non si era visto)."""
    n = (d.get("guardiano") or {}).get("guasti") or 0
    if not n:
        return None
    quando = f" del {data}" if data else ""
    return (f"il guardiano o il rilevatore di pericolo non hanno giudicato la domanda in {n} "
            f"turni{quando} su {d['guardiano']['n']}: per i minori la risposta è stata la frase "
            f"di guasto. Controlla i modelli su Ollama (ollama ps).")


def _s(x) -> str:
    return "—" if x is None else f"{x:.2f} s".replace(".", ",")


def _tps(x) -> str:
    return "—" if x is None else str(round(x))


def testo(giorni: dict[str, dict], soglia: float = 1.2) -> str:
    """La tabella per il terminale (`calliope stato --turni`)."""
    if not giorni:
        return "Latenza: nessun turno nel registro."
    righe = ["Latenza della voce dal registro dei turni (prima frase da quando il VAD chiude "
             "la frase; «dalla fine» comprende il silenzio finale)", ""]
    for data, d in giorni.items():
        pf, fp = d["prima_frase"], d["fine_parlato"]
        righe.append(f"{data}  {d['risposte']} risposte  prima frase {_s(pf['mediana'])} "
                     f"(p75 {_s(pf['p75'])}, p90 {_s(pf['p90'])})"
                     + (f"  dalla fine {_s(fp['mediana'])} (p90 {_s(fp['p90'])})"
                        if fp["n"] else ""))
        pv = d.get("prima_voce") or {}
        if pv.get("n"):
            righe.append(f"    prima voce sentita {_s(pv['mediana'])} (p90 {_s(pv['p90'])})"
                         + (f", dalla fine del parlato {_s(pv['sentita'])} (p90 "
                            f"{_s(pv['sentita_p90'])})" if pv.get("sentita") is not None
                            else ""))
            if pv.get("distacco") is not None:
                righe.append(f"    dal testo alla voce {_s(pv['distacco'])} (p90 "
                             f"{_s(pv['distacco_p90'])})"
                             + (f": sintesi {_s(pv['sintesi'])}, rete e uscita "
                                f"{_s(pv['consegna'])}" if pv.get("n_scomposti") else ""))
        c, g, t, le = d["correzione"], d["guardiano"], d["tool"], d["lettura"]
        righe.append(f"    STT {_s(d['stt']['mediana'])} (p90 {_s(d['stt']['p90'])})"
                     f"  base senza tool, guardiano e correzione {_s(d['base']['mediana'])} "
                     f"su {d['base']['n']}")
        cause = []
        if c["n"]:
            ms = c["ms_mediana"]
            cause.append(f"correzione {c['n']} frasi, {_s(ms / 1000 if ms else None)}, "
                         f"{c['scadute']} scadute, {c['cambiate']} cambiate")
        if g["n"]:
            cause.append(f"guardiano {g['n']} turni, prima frase {_s(g['prima_frase'])}"
                         + (f", rilevatore {_s(g['pericolo_ms'] / 1000)}"
                            if g.get("pericolo_ms") else ""))
        if t["n"]:
            cause.append(f"tool {t['n']} turni, {_s(t['con'])} contro {_s(t['senza'])}")
        if le["n"]:
            cause.append(f"rilettura {_s(le['mediana'])}, {le['lente']} oltre "
                         f"{_s(LETTURA_LENTA_S)}")
        ge = d.get("generazione") or {}
        if ge.get("n"):
            cause.append(f"generazione {_tps(ge['mediana'])} token/s (i più lenti "
                         f"{_tps(ge['p10'])})")
        if d["contesto"]["token_mediana"]:
            cause.append(f"contesto {int(d['contesto']['token_mediana'])} token")
        if d["coda"]["n"]:
            cause.append(f"in coda {d['coda']['n']} volte")
        ca = d.get("cache") or {}
        if ca.get("n"):
            cause.append(f"cache del prefisso persa in {ca['perse']} turni su {ca['n']}")
        dt = d.get("dati_turno") or {}
        if dt.get("n"):
            cause.append(f"dati del turno {int(dt['mediana'])} token (p90 {int(dt['p90'])}"
                         + (f", oltre il tetto in {dt['oltre']} turni" if dt["oltre"] else "")
                         + ")")
        sa = d.get("schede_attesa") or {}
        if sa.get("n"):
            cause.append(f"schede trattenute {sa['n']} volte, {int(sa['ms_mediana'])} ms "
                         f"(massimo {int(sa['ms_max'])})")
        if cause:
            righe.append("    " + "; ".join(cause))
        a = avviso(d, soglia)
        if a:
            righe.append("    ATTENZIONE: " + a)
        a = avviso_guasti(d)
        if a:
            righe.append("    ATTENZIONE: " + a)
    return "\n".join(righe)


LUNGA_CAR = 300          # una risposta più lunga, detta in un pezzo solo: la voce ha aspettato


def _nomi_tool(t: dict) -> set[str]:
    """I tool del turno; `notizie` con `fatto` (un seguito: «dimmi di più sulla seconda») a
    parte, «notizie (seguito)»: la frase d'attesa parte anche lì e va misurata da sola (issue
    #132). Solo nomi e chiavi degli argomenti, nessun valore. Per ospiti e voci incerte
    `conserva.togli_testo` toglie gli argomenti dal registro: i loro seguiti restano in
    «notizie»."""
    nomi = set()
    for x in t.get("tool") if isinstance(t.get("tool"), list) else ():
        if not isinstance(x, dict) or not x.get("nome"):
            continue
        n = str(x["nome"])
        arg = x.get("argomenti") if isinstance(x.get("argomenti"), dict) else {}
        nomi.add(f"{n} (seguito)" if n == "notizie" and arg.get("fatto") not in (None, "")
                 else n)
    return nomi


def per_tool(turni: list[dict]) -> dict[str, dict]:
    """La prima voce sentita per tool (17/10, issue #132: le notizie a 2,91 s di mediana contro
    1,62 di web_cerca, contate a mano dal registro). Per ogni tool chiamato nel turno: turni con
    la misura, mediana e p90 di `prima_voce_s`, e le risposte più lunghe di LUNGA_CAR caratteri
    mandate alla voce in un pezzo solo (`frasi_voce` e `risposta_car`, dal 17/10: due numeri,
    mai il testo della risposta, che per ospiti e voci incerte non resta)."""
    gruppi: dict[str, list] = {}
    for t in turni:
        if not isinstance(t, dict) or _num(t, "prima_voce_s") is None:
            continue
        for n in _nomi_tool(t):
            gruppi.setdefault(n, []).append(t)
    out = {}
    for n, g in gruppi.items():
        pv = [_num(t, "prima_voce_s") for t in g]
        out[n] = {"turni": len(g), "mediana": _med(pv), "p90": _q(pv, .9),
                  "lunghe_un_pezzo": sum(1 for t in g if t.get("frasi_voce") == 1
                                         and (_num(t, "risposta_car") or 0) > LUNGA_CAR)}
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["turni"], kv[0])))


def testo_per_tool(r: dict[str, dict], massimo: int = 10) -> str:
    """La riga per `calliope stato --turni`: i tool più chiamati, con la prima voce sentita."""
    if not r:
        return "Prima voce sentita per tool: nessun turno con un tool e la misura della voce."
    pezzi = [f"{n} {d['turni']} turni, {_s(d['mediana'])} (p90 {_s(d['p90'])})"
             + (f", {d['lunghe_un_pezzo']} lunghe in un pezzo" if d["lunghe_un_pezzo"] else "")
             for n, d in list(r.items())[:massimo]]
    return "Prima voce sentita per tool: " + "; ".join(pezzi) + "."


def leggi(cartella, giorni: int | None = None) -> list[dict]:
    """I turni degli ultimi `giorni` file (righe rotte saltate: il registro si scrive mentre
    Calliope gira)."""
    if not cartella:
        return []
    files = sorted(Path(cartella).glob("turni-*.jsonl"))
    if giorni is not None:
        files = files[-giorni:]
    out = []
    for f in files:
        out.extend(leggi_file(f))
    return out


def leggi_file(f) -> list[dict]:
    """I turni di un file del registro (righe rotte saltate; file illeggibile: nessuno)."""
    import json
    try:
        righe = Path(f).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for riga in righe:
        try:
            t = json.loads(riga)
        except ValueError:
            continue
        if isinstance(t, dict):
            out.append(t)
    return out


def avviso_recente(cfg, oggi: datetime.date | None = None) -> str | None:
    """All'avvio: l'avviso dell'ultimo giorno con abbastanza risposte, oggi o ieri; e quello
    dei giudizi mancati del guardiano (anche con poche risposte: avviso_guasti)."""
    soglia = float(getattr(cfg, "latenza_avviso_s", 1.2) or 0)
    oggi = oggi or datetime.date.today()
    out = []
    try:
        giorni = per_giorno(leggi(getattr(cfg, "turn_log_dir", None), 2))
        date = (oggi.isoformat(), (oggi - datetime.timedelta(days=1)).isoformat())
        if soglia > 0:
            for data in date:
                d = giorni.get(data)
                if d and d["risposte"] >= MIN_RISPOSTE:
                    a = avviso(d, soglia, data)
                    if a:
                        out.append(a)
                    break
        for data in date:
            a = avviso_guasti(giorni[data], data) if data in giorni else None
            if a:
                out.append(a[0].upper() + a[1:])
                break
    except Exception:  # noqa: BLE001 — un registro strano non ferma l'avvio
        pass
    return " ".join(out) or None


def scalda_ripresa(brain, conversazioni, log=print) -> dict | None:
    """Dopo un riavvio (P3): la conversazione ripresa più recente si mette in cache del motore
    (`Brain.scalda_conversazione`), così il suo primo turno non rilegge tutta la storia. Una
    sola: Ollama con uno slot tiene in cache solo l'ultima richiesta. Da un thread a parte:
    il saluto non aspetta. Non solleva mai."""
    try:
        tutte = [c for c in conversazioni if getattr(c, "history", None)
                 or getattr(c, "riassunto", None)]
        if not tutte:
            return None
        conv = max(tutte, key=lambda c: getattr(c, "last_turn_at", None) or 0.0)
        res = brain.scalda_conversazione(conv)
        if res:
            n = sum(1 for m in conv.history if m.get("role") == "user")
            tok = f", {res['token']} token" if res.get("token") else ""
            log(f"[STORIA] Conversazione ripresa ({n} turni) già in cache: {res['s']:.1f} s"
                f"{tok}", flush=True)
        return res
    except Exception as e:  # noqa: BLE001 — il riscaldamento non ferma niente
        log(f"[STORIA] Conversazione ripresa non scaldata: {type(e).__name__}: {e}", flush=True)
        return None
