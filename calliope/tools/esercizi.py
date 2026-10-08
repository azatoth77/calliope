"""
Il tool degli esercizi (08/10/2026, calliope/esercizi/, docs/ricerche/2026-10-08-esercizi.md).

esercizi(azione, materia, argomento, classe, risposta, nota, nome): gli esercizi generati da
Calliope per i ragazzi di casa. Lo usano i minori per sé e chi li segue (un loro tutore, o chi
amministra) per provarli o per sentire il riepilogo; gli ospiti no (livelli), un adulto che non
segue nessun ragazzo nemmeno (qui). La risposta la corregge il codice: il modello passa solo
ciò che il ragazzo ha detto.

Registrato con i tool dei minori (solo con un minore in casa: il prefisso degli altri non
cambia).
"""

from __future__ import annotations

from .. import minori as M
from ..testi import FAMILY, NIENTE
from .spec import ToolContext, ToolSpec, note_rule

AZIONI = ["inizia", "rispondi", "aiuto", "salta", "ripeti", "segnala", "soluzione", "fine",
          "argomenti", "riepilogo"]


def _final(text: str, ok: bool = True, **extra) -> dict:
    return {"ok": ok, **extra, "conferma": text, "risposta_finale": text}


def _segue_qualcuno(prof, speakers) -> bool:
    """Chi parla è tutore di almeno un minore di casa (o amministra)."""
    if bool(getattr(prof, "admin", False)):
        return True
    for u in getattr(speakers, "users", {}).values():
        if M.e_minore(u) and M.e_tutore(prof, u):
            return True
    return False


def _esercizi(ctx: ToolContext, azione: str = "inizia", materia: str = "", argomento: str = "",
              classe: str = "", risposta: str = "", nota: str = "", nome: str = "") -> dict:
    from ..esercizi import classe_da_eta, classe_da_testo, materia_da_testo
    from ..esercizi import sessione as S
    srv = S.servizio()
    if srv is None:
        return _final("Gli esercizi qui non ci sono.", ok=False, fatto=NIENTE)
    prof = M.profilo(ctx)
    speakers = getattr(ctx, "speakers", None)
    if prof is None:
        note_rule(ctx, "esercizi_ospite")
        return _final("Gli esercizi sono per i ragazzi di casa.", ok=False, fatto=NIENTE)
    azione = str(azione or "inizia").strip().lower()
    minore = M.e_minore(prof)
    if azione == "riepilogo":
        bersaglio = prof if (minore and not str(nome or "").strip()) else None
        if bersaglio is None and str(nome or "").strip() and speakers is not None:
            t = speakers.find(nome)
            bersaglio = speakers.get(t) if t else None
        if bersaglio is None or not M.e_minore(bersaglio):
            return {"ok": False, "fatto": NIENTE, "errore": "di quale ragazzo?",
                    "cosa_fare": "chiedi di chi vuole il riepilogo"}
        if not (bersaglio is prof or getattr(bersaglio, "id", None) == prof.id
                or M.e_tutore(prof, bersaglio) or getattr(prof, "admin", False)):
            note_rule(ctx, "esercizi_riepilogo_permesso")
            return _final(f"Gli esercizi di {bersaglio.name} li può sentire lui o un suo "
                          f"tutore.", ok=False, fatto=NIENTE)
        mitt = None
        hub = getattr(ctx, "schermi", None)
        if hub is not None and bersaglio.id != prof.id:
            try:
                mitt = hub.mittente(ctx)
            except Exception:  # noqa: BLE001
                mitt = None
        try:
            giorni = int("".join(c for c in str(risposta or "") if c.isdigit()) or 1)
        except ValueError:
            giorni = 1
        note_rule(ctx, "esercizi_riepilogo")
        return _final(srv.riepilogo(bersaglio, min(giorni, 31), mitt)["frase"])
    if not minore and not _segue_qualcuno(prof, speakers):
        note_rule(ctx, "esercizi_permesso")
        return _final("Gli esercizi sono per i ragazzi di casa e per chi li segue.", ok=False,
                      fatto=NIENTE)
    if azione == "argomenti":
        eta = M.eta(getattr(prof, "nascita", None)) if minore else None
        cl = classe_da_testo(classe) or classe_da_eta(eta)
        el = srv.elenco_argomenti(cl, materia_da_testo(materia))
        return _final(f"Posso farti esercizi di {el}." if el else
                      "Per ora ho esercizi di matematica e di italiano.")
    if azione == "inizia":
        hub = getattr(ctx, "schermi", None)
        mitt = None
        if hub is not None:
            try:
                mitt = hub.mittente(ctx)
            except Exception:  # noqa: BLE001
                mitt = None
        note_rule(ctx, "esercizi_inizio")
        return srv.inizia(prof, M.fascia(prof), M.eta(getattr(prof, "nascita", None)),
                          str(materia or ""), str(argomento or ""), str(classe or ""), mitt)
    if azione == "rispondi":
        if not str(risposta or "").strip():
            return {"ok": False, "errore": "manca la risposta",
                    "cosa_fare": "passa in risposta ciò che ha detto, così com'è"}
        note_rule(ctx, "esercizi_corretto_dal_codice")
        out = srv.rispondi(prof, str(risposta), "voce")
    elif azione == "aiuto":
        out = srv.aiuto(prof)
    elif azione == "salta":
        out = srv.salta(prof)
    elif azione == "ripeti":
        out = srv.ripeti(prof)
    elif azione == "segnala":
        note_rule(ctx, "esercizi_segnalazione")
        out = srv.segnala(prof, str(nota or ""), str(risposta or ""))
    elif azione == "soluzione":
        p = M.preset(prof)
        libero = p is None or p.get("compiti") == "libero"
        if not libero:
            note_rule(ctx, "esercizi_soluzione_negata")
        out = srv.soluzione(prof, libero)
    elif azione == "fine":
        out = srv.fine(prof)
    else:
        return {"ok": False, "errore": f"azione sconosciuta: {azione}", "azioni": AZIONI}
    regola = out.pop("regola", None) if isinstance(out, dict) else None
    if regola:
        note_rule(ctx, regola)
    return out


def esercizi_spec() -> ToolSpec:
    return ToolSpec(
        name="esercizi",
        description=("Esercizi di studio preparati da Calliope per i ragazzi di casa "
                     "(matematica: operazioni, tabelline, frazioni, problemi, potenze, "
                     "equazioni; italiano: analisi grammaticale e logica). «Facciamo esercizi "
                     "di frazioni», «interrogami di analisi logica»: azione=inizia (materia, "
                     "argomento, classe solo se la dice, come «terza elementare»). Durante gli "
                     "esercizi: rispondi con la risposta così come l'ha detta (la corregge il "
                     "programma, tu non dire se è giusta), aiuto, salta, ripeti, segnala («secondo "
                     "me è sbagliato»), soluzione, fine. argomenti: cosa si può fare. riepilogo: "
                     "come sono andati (un adulto: nome del ragazzo). Non per i compiti portati "
                     "da scuola: quelli sono compiti_aiuto."),
        parameters={"type": "object", "properties": {
            "azione": {"type": "string", "enum": AZIONI},
            "materia": {"type": "string"}, "argomento": {"type": "string"},
            "classe": {"type": "string"}, "risposta": {"type": "string"},
            "nota": {"type": "string"}, "nome": {"type": "string"}},
            "required": ["azione"]},
        func=_esercizi, risk="lettura", levels=FAMILY, classe="sicuro")
