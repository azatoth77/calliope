"""
Il «sì» breve per le azioni importanti, in ombra (15/10/2026, roadmap 2.6, voce E6).

La domanda della revisione del 12/10: per un'azione importante (classe d'effetto E3–E4, un tool
con la frase di sfida nella classe, un tool pericoloso) basta un «sì» breve, o serve sempre la
voce riconosciuta in una frase intera o la frase di sfida? Oggi il «sì» breve di chi amministra
conferma il tool proposto se l'impronta è compatibile (conferme.admin_confermato, soglia
`speaker_conferma_breve_soglia`), e il «sì» breve di un familiare conferma le azioni del suo
livello. La decisione si prende con i numeri: qui **solo la misura**, nessun effetto sul
comportamento.

Per ogni chiamata che `ToolRegistry.call` sta per eseguire (permessi e politica già passati),
se è un'azione importante o la conferma di una proposta (il «sì» alla domanda in sospeso o la
sfida superata), una riga nel campo `si_breve` del turno:

- `tool`, `effetto` (E0–E4), `importante`, `sfida_classe`, `solo_amministra`;
- `conferma`: la frase acconsente a una proposta per questo tool (politica.consenso_turno) o
  ha superato la sfida;
- `modo`: con che cosa si è saputo chi parla in questa frase. `voce` (riconosciuta sopra
  soglia, frase intera), `breve_compatibile` (il «sì» breve di chi amministra con l'impronta
  compatibile, regola `conferma_breve`; non il «sì» breve di un tutore che non amministra, che
  in `SpeakerContext` si chiama `breve_impronta_ok`: issue #114), `breve` (frase sotto
  `speaker_min_voice_s` che vale la conversazione), `zona_grigia` (anche la continuità e la
  voce incerta con un minore), `sfida`, `scritto` (uno schermo personale), `nessuno`;
- `parole` (quante, mai quali) e `forma_chiusa` (la frase è tutta un consenso: «sì», «vai»);
- `rischi`: `compagnia` (più voci vicino al satellite), `voci_sconosciute` (in compagnia, voci
  che nessun profilo riconosce: anche la TV, che un filtro suo non ce l'ha ancora), `incerta`
  (incerta tra chi amministra e un minore, o minore vicino), `senza_nome` (presa nella finestra
  d'ascolto senza il nome);
- `punteggio`: l'impronta della frase contro il profilo di chi parla, se c'è.

`riassunto` e `testo` (per `calliope stato --turni`) contano le conferme delle azioni importanti
per modo, quanti «sì» brevi avevano un rischio, e quanto costerebbe l'alternativa «per le azioni
importanti il "sì" breve non basta»: una domanda (la sfida) in più per ogni conferma breve, con
il tempo mediano di una sfida vera misurato dal registro (dall'inizio della frase che la riceve
all'inizio della risposta, stesso satellite). Il verso opposto («basta anche dove oggi c'è la
sfida») si legge dalle sfide superate. Solo numeri, solo libreria standard.
"""
from __future__ import annotations

import datetime

CAMPO = "si_breve"
MODI = ("voce", "breve_compatibile", "breve", "zona_grigia", "sfida", "scritto", "nessuno")
BREVI = ("breve_compatibile", "breve", "zona_grigia")      # le conferme senza frase intera
RISCHI = ("compagnia", "voci_sconosciute", "incerta", "senza_nome")
SFIDA_MAX_S = 120.0        # oltre, la risposta alla sfida non è più quella


def modo(sc, breve: bool) -> str:
    """Con che cosa si è saputo chi parla in questa frase (vedi il docstring del modulo)."""
    if sc is None:
        return "nessuno"
    if getattr(sc, "sfida_superata", False):
        return "sfida"
    if breve:
        return "breve_compatibile"
    how = getattr(sc, "identified_by", None)
    if getattr(sc, "current_speaker", None) is None and how != "schermo":
        return "nessuno"
    if how == "voce":
        return "zona_grigia" if getattr(sc, "from_session", False) else "voce"
    return {"breve": "breve", "conversazione": "zona_grigia", "schermo": "scritto"}.get(
        how, "nessuno")


def rischi(sc) -> list[str]:
    if sc is None:
        return []
    out = []
    if getattr(sc, "compagnia", False):
        out.append("compagnia")
        if getattr(sc, "compagnia_sconosciute", False):
            out.append("voci_sconosciute")
    if getattr(sc, "incerta", None) or getattr(sc, "minore_vicino", None):
        out.append("incerta")
    if getattr(sc, "senza_nome", False):
        out.append("senza_nome")
    return out


def misura(spec, name: str, args: dict | None, ctx, breve: bool = False) -> dict | None:
    """La riga di questa chiamata, o None (né importante né una conferma). Non solleva mai:
    una misura non ferma un tool."""
    try:
        from . import politica as pol
        from . import valore
        args = dict(args or {})
        cl = pol.classe_di(name, spec)
        e = valore.effetto(name, args, spec)
        sc = getattr(ctx, "speaker_ctx", None)
        importante = bool(e >= valore.E3 or cl.sfida or cl.classe == pol.PERICOLOSO)
        conferma = bool(getattr(sc, "sfida_superata", False))
        t = getattr(ctx, "politica", None)
        if not conferma and t is not None:
            conferma = bool(pol.consenso_turno(name, args, cl, t)[0])
        if not conferma and breve:
            conferma = True                  # la conferma breve vale solo per il tool proposto
        if not (importante or conferma):
            return None
        testo = str(getattr(ctx, "user_text", "") or "")
        livelli = set(getattr(spec, "levels", None) or ())
        riga = {"tool": name, "effetto": valore.NOMI_EFFETTO.get(e, "E3"),
                "importante": importante, "sfida_classe": bool(cl.sfida),
                "solo_amministra": livelli == {"amministra"},
                "conferma": conferma, "modo": modo(sc, breve),
                "parole": len(testo.split()), "forma_chiusa": bool(pol.consenso_chiuso(testo))}
        r = rischi(sc)
        if r:
            riga["rischi"] = r
        p = getattr(sc, "punteggio", None)
        if isinstance(p, (int, float)):
            riga["punteggio"] = round(float(p), 3)
        return riga
    except Exception:  # noqa: BLE001 — la misura non ferma niente
        return None


def annota(spec, name: str, args: dict | None, ctx, breve: bool = False):
    """Mette la riga nel ToolContext (`si_breve`, con il numero della risposta): la legge il
    ciclo quando scrive il turno (`del_turno`)."""
    riga = misura(spec, name, args, ctx, breve)
    if riga is None:
        return
    lista = getattr(ctx, "si_breve", None)
    if not isinstance(lista, list):
        return
    riga["_turno"] = getattr(ctx, "turno", 0)
    lista.append(riga)


def del_turno(ctx) -> list[dict]:
    """Le righe della risposta in corso (stesso `turno` del ToolContext), e svuota l'elenco:
    quelle di una risposta finita senza registro non passano alla dopo."""
    lista = getattr(ctx, "si_breve", None)
    if not isinstance(lista, list) or not lista:
        return []
    n = getattr(ctx, "turno", 0)
    out = [{k: v for k, v in r.items() if k != "_turno"} for r in lista
           if r.get("_turno") == n]
    lista.clear()
    return out


# ─────────────────────────── calliope stato --turni ───────────────────────────

def _quando(t: dict) -> float | None:
    try:
        return datetime.datetime.fromisoformat(str(t.get("inizio"))).timestamp()
    except (TypeError, ValueError):
        return None


def tempi_sfida(turni: list[dict]) -> list[float]:
    """Quanto è costata ogni sfida vera: dall'inizio della frase che l'ha ricevuta (regola
    `sfida_voce`) all'inizio della risposta (regola `sfida_risposta`) sullo stesso satellite,
    entro SFIDA_MAX_S."""
    ordinati = sorted((t for t in turni if _quando(t) is not None), key=_quando)
    out = []
    for i, t in enumerate(ordinati):
        if "sfida_voce" not in (t.get("regole") or ()):
            continue
        q, sat = _quando(t), t.get("satellite")
        for u in ordinati[i + 1:]:
            dq = _quando(u) - q
            if dq > SFIDA_MAX_S:
                break
            if u.get("satellite") != sat:
                continue
            if "sfida_risposta" in (u.get("regole") or ()):
                out.append(round(dq, 1))
            break
    return out


def _mediana(xs: list[float]) -> float | None:
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2, 1)


def riassunto(turni: list[dict]) -> dict:
    """I numeri della misura su tutti i turni dati (di solito `--giorni N`)."""
    righe = [(t, r) for t in turni for r in (t.get(CAMPO) or ()) if isinstance(r, dict)]
    imp_conf = [r for _t, r in righe if r.get("importante") and r.get("conferma")]
    per_modo = {m: sum(1 for r in imp_conf if r.get("modo") == m) for m in MODI}
    brevi = [r for r in imp_conf if r.get("modo") in BREVI]
    rischio = {k: sum(1 for r in brevi if k in (r.get("rischi") or ())) for k in RISCHI}
    tool: dict[str, int] = {}
    for r in brevi:
        tool[str(r.get("tool"))] = tool.get(str(r.get("tool")), 0) + 1
    sfide = tempi_sfida(turni)
    med = _mediana(sfide)
    chieste = sum(1 for t in turni if "sfida_voce" in (t.get("regole") or ()))
    return {
        "turni_misurati": sum(1 for t in turni if CAMPO in t),
        "importanti": sum(1 for _t, r in righe if r.get("importante")),
        "conferme": sum(1 for _t, r in righe if r.get("conferma")),
        "conferme_importanti": len(imp_conf),
        "per_modo": per_modo,
        "brevi": len(brevi),
        "brevi_forma_chiusa": sum(1 for r in brevi if r.get("forma_chiusa")),
        "brevi_rischi": rischio,
        "brevi_con_rischio": sum(1 for r in brevi if r.get("rischi")),
        "brevi_tool": dict(sorted(tool.items(), key=lambda kv: -kv[1])[:6]),
        "sfide_chieste": chieste,
        "sfide_superate_importanti": per_modo["sfida"],
        "sfida_s_mediana": med, "sfide_misurate": len(sfide),
        # L'alternativa: per le azioni importanti il «sì» breve non basta, si chiede la sfida
        "alternativa_domande": len(brevi),
        "alternativa_s": round(len(brevi) * med, 1) if med is not None else None,
    }


def testo(r: dict) -> str:
    """Le righe per `calliope stato --turni`."""
    titolo = "«Sì» breve per le azioni importanti (in ombra dal 15/10, roadmap 2.6)"
    if not r or not r.get("turni_misurati"):
        return f"{titolo}: nessun turno con la misura."
    pm = r["per_modo"]
    nomi = {"voce": "voce", "breve_compatibile": "sì breve compatibile", "breve": "sì breve",
            "zona_grigia": "zona grigia", "sfida": "sfida", "scritto": "scritto",
            "nessuno": "senza voce"}
    modi = ", ".join(f"{nomi[m]} {pm[m]}" for m in MODI if pm.get(m))
    righe = [titolo,
             f"    azioni importanti eseguite {r['importanti']}, conferme {r['conferme']}; "
             f"conferme di azioni importanti {r['conferme_importanti']}"
             + (f" ({modi})" if modi else "")]
    if r["brevi"]:
        rs = r["brevi_rischi"]
        dett = ", ".join(f"{k.replace('_', ' ')} {rs[k]}" for k in RISCHI if rs.get(k))
        righe.append(f"    senza frase intera {r['brevi']} ({r['brevi_forma_chiusa']} solo «sì»"
                     f"), con un rischio {r['brevi_con_rischio']}" + (f": {dett}" if dett else "")
                     + "; tool: " + ", ".join(f"{k} {v}" for k, v in r["brevi_tool"].items()))
    med = r["sfida_s_mediana"]
    sfida = (f"sfida mediana {med:.1f} s su {r['sfide_misurate']}" if med is not None
             else "tempo della sfida non ancora misurato")
    righe.append(f"    sfide chieste {r['sfide_chieste']}, superate per azioni importanti "
                 f"{r['sfide_superate_importanti']}; {sfida}")
    costo = (f", circa {r['alternativa_s']:.0f} s" if r["alternativa_s"] is not None else "")
    righe.append(f"    se il «sì» breve non bastasse: {r['alternativa_domande']} domande in più"
                 + costo)
    return "\n".join(righe)
