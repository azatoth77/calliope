"""
La conversazione di stanza a voce (13/10, passo 1: decisione 0029, progetto § 3.10, § 4.3).

stanza_pausa(azione, minuti):
- «ospiti»: «Calliope, abbiamo ospiti» ferma l'ascolto della stanza su questo satellite per
  `stanza_ospiti_ore` (4 h, risposta 6 di chi amministra). **Chiunque** può dirlo: spegne, non
  accende;
- «pausa»: «smetti di ascoltare la stanza (per mezz'ora)», per `minuti` o `stanza_pausa_min`;
  anche questa da chiunque;
- «riprendi»: «ascolta di nuovo la stanza», solo un adulto riconosciuto dalla voce (accende);
- «stato»: la stanza ascolta? (lettura).

C'è solo con la stanza accesa (`stanza: ombra`, main.py). Il satellite è quello da cui si
parla (la corsia del turno).
"""

import datetime

from ..testi import ALL, NIENTE, RANK
from .spec import ToolContext, ToolSpec, note_rule


def _final(frase: str, ok: bool = True, **extra) -> dict:
    return {"ok": ok, **({} if ok else {"fatto": NIENTE}), "conferma": frase,
            "risposta_finale": frase, **extra}


def satellite_del_turno(ctx):
    """L'id del satellite da cui si parla: la corsia del thread, o il satellite attivo."""
    from .. import corsie
    c = corsie.corrente()
    sid = getattr(c, "satellite_id", None) if c is not None else None
    if sid is not None:
        return sid
    stanza = getattr(ctx, "stanza", None)
    srv = getattr(stanza, "server", None)
    coll = getattr(srv, "attivo", None) if srv is not None else None
    return coll.satellite.get("id") if coll is not None else None


def _ora(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch).strftime("%H:%M")


def _stanza_pausa(ctx: ToolContext, azione: str = "", minuti: float | None = None) -> dict:
    stanza = getattr(ctx, "stanza", None)
    if stanza is None:
        return _final("Qui non ascolto la conversazione della stanza.", ok=False)
    sat = satellite_del_turno(ctx)
    if sat is None or not stanza.accesa_per({"id": sat, "nome": (stanza._info.get(sat) or {})
                                             .get("nome")}) or sat not in stanza._info:
        return _final("Su questo dispositivo non ascolto la conversazione della stanza.",
                      ok=False)
    a = str(azione or "").strip().lower()
    cfg = ctx.cfg
    if a == "stato":
        p = stanza.stato_pausa(sat)
        if p is None:
            return _final("Sì, qui ascolto la conversazione della stanza, e la tengo solo in "
                          "memoria. Per fermarmi dimmi «abbiamo ospiti» o «smetti di ascoltare "
                          "la stanza».")
        return _final("Adesso non ascolto la stanza" + (f", fino alle {_ora(p['fino'])}."
                                                       if p.get("fino") else "."))
    if a == "ospiti":
        ore = float(getattr(cfg, "stanza_ospiti_ore", 4.0) or 4.0)
        r = stanza.pausa(sat, "ospiti", ore * 60)
        note_rule(ctx, "stanza_ospiti")
        return _final(f"Va bene, smetto di ascoltare la stanza fino alle {_ora(r['fino'])}. "
                      "Mi chiamate per nome come sempre.")
    if a == "pausa":
        try:
            m = float(minuti) if minuti else float(getattr(cfg, "stanza_pausa_min", 60.0))
        except (TypeError, ValueError):
            m = float(getattr(cfg, "stanza_pausa_min", 60.0))
        m = min(24 * 60.0, max(1.0, m))
        r = stanza.pausa(sat, "pausa", m)
        note_rule(ctx, "stanza_pausa")
        return _final(f"Va bene, non ascolto la stanza fino alle {_ora(r['fino'])}.")
    if a == "riprendi":
        sc = getattr(ctx, "speaker_ctx", None)
        livello = getattr(sc, "current_level", "ospite") or "ospite"
        minore = False
        try:
            from ..minori import e_minore
            prof = ctx.speakers.get(getattr(sc, "current_speaker", None) or "")
            minore = bool(prof is not None and e_minore(prof))
        except Exception:  # noqa: BLE001
            minore = False
        if (RANK.get(livello, 0) < RANK.get("familiare", 1) or minore
                or getattr(sc, "identified_by", None) != "voce"):
            return _final("Ascolto di nuovo la stanza solo se me lo chiede a voce una persona "
                          "di casa che riconosco.", ok=False)
        if not stanza.riprendi(sat):
            return _final("Sto già ascoltando la stanza.")
        note_rule(ctx, "stanza_riprendi")
        return _final("Va bene, ascolto di nuovo la conversazione della stanza.")
    return {"ok": False, "fatto": NIENTE, "motivo": f"azione «{a}» sconosciuta",
            "cosa_fare": "usa ospiti, pausa, riprendi o stato"}


def stanza_specs() -> list[ToolSpec]:
    return [ToolSpec(
        name="stanza_pausa",
        description=(
            "L'ascolto della conversazione della stanza su questo dispositivo (Calliope la "
            "trascrive, solo in memoria). azione=ospiti quando dicono che ci sono ospiti "
            "(«abbiamo ospiti», «sono arrivati degli amici»): smette per qualche ora. "
            "azione=pausa per «smetti di ascoltare la stanza», «non ascoltarci per mezz'ora» "
            "(minuti se li dice). azione=riprendi per «ascolta di nuovo la stanza». azione=stato "
            "per «stai ascoltando quello che diciamo?». Non serve per fermare la risposta "
            "(«basta») né per spegnere Calliope."),
        parameters={"type": "object",
                    "properties": {"azione": {"type": "string",
                                              "enum": ["ospiti", "pausa", "riprendi", "stato"]},
                                   "minuti": {"type": "number"}},
                    "required": ["azione"]},
        func=_stanza_pausa, risk="azione", levels=ALL, classe="sicuro")]
