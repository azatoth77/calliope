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

AZIONI = ["inizia", "interroga", "rispondi", "aiuto", "salta", "ripeti", "segnala",
          "soluzione", "pausa", "continua", "preferenze", "a_che_punto", "piu_difficile",
          "piu_facile", "fine", "argomenti", "riepilogo"]
MODI = ["giocoso", "punti", "tappe", "normale"]


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


def _azione(ctx, srv, prof, azione, materia, argomento, risposta, modo="", blocco="",
            punto: bool = False) -> str:
    """L'azione chiamata. Senza azione (banco del 12/10, chimica: 11 chiamate su 17 con soli
    materia, argomento e risposta; il registro dei tool le lascia passare perché `azione`
    ha un valore predefinito) prima valeva «inizia», che a sessione aperta ricominciava da
    un esercizio nuovo a ogni risposta. Ora,
    con una sessione aperta: con la risposta è «rispondi», senza un argomento diverso
    «ripeti»; altrimenti «inizia» come prima. Correzione della forma di una chiamata già
    fatta (principio 10), regola `esercizi_azione_dedotta`."""
    a = str(azione or "").strip().lower()
    s = srv.sessione(prof.id)
    if s is not None and a == "continua" and s.attesa_punto and punto:
        # 4B del 12/10 sera: «siamo alle addizioni col riporto, fino a cento» → continua con
        # entro=100. Con i dati del punto è la risposta (correzione della forma)
        note_rule(ctx, "esercizi_azione_dedotta")
        return "a_che_punto"
    if a:
        return a
    if s is None:
        return "inizia"
    from ..esercizi import argomento_da_testo, materia_da_testo
    if s.attesa_punto and (punto or str(argomento or "").strip()):
        # La risposta a «a che punto siete» senza azione (12/10 sera)
        note_rule(ctx, "esercizi_azione_dedotta")
        return "a_che_punto"
    if str(materia or "").strip() and materia_da_testo(materia) not in (None, s.materia):
        return "inizia"
    if str(risposta or "").strip():
        note_rule(ctx, "esercizi_azione_dedotta")
        return "rispondi"
    if str(modo or "").strip() or str(blocco or "").strip():
        note_rule(ctx, "esercizi_azione_dedotta")
        return "preferenze"
    altro = argomento_da_testo(argomento) if str(argomento or "").strip() else None
    if altro is None or altro == s.argomento:
        note_rule(ctx, "esercizi_azione_dedotta")
        return "ripeti"
    return "inizia"


def _pagina(ctx) -> bool:
    """C'è una pagina del libro nella conversazione: una foto o un file (calliope/immagini.py,
    allegati.py)? Il contenuto resta un dato non fidato."""
    try:
        if len(getattr(ctx, "immagini", None) or ()) > 0:
            return True
        return len(getattr(ctx, "allegati", None) or ()) > 0
    except TypeError:
        return False


def _bool(v):
    """true/false anche come testo («sì», «no»), None se non c'è."""
    if isinstance(v, bool):
        return v
    t = str(v or "").strip().lower()
    if t in ("true", "si", "sì", "yes"):
        return True
    if t in ("false", "no"):
        return False
    return None


def _esercizi(ctx: ToolContext, azione: str = "", materia: str = "", argomento: str = "",
              classe: str = "", risposta: str = "", nota: str = "", nome: str = "",
              modo: str = "", blocco: str = "", entro: str = "", riporto=None,
              oltre=None, giudizio: str = "", sicurezza: str = "", domande=None) -> dict:
    from ..esercizi import classe_da_eta, classe_da_testo, elenco_materie, materia_da_testo
    from ..esercizi import sessione as S
    srv = S.servizio()
    if srv is None:
        return _final("Gli esercizi qui non ci sono.", ok=False, fatto=NIENTE)
    prof = M.profilo(ctx)
    speakers = getattr(ctx, "speakers", None)
    if prof is None:
        note_rule(ctx, "esercizi_ospite")
        return _final("Gli esercizi sono per i ragazzi di casa.", ok=False, fatto=NIENTE)
    azione = _azione(ctx, srv, prof, azione, materia, argomento, risposta, modo, blocco,
                     punto=bool(str(entro or "").strip()) or _bool(riporto) is not None)
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
    if azione == "a_che_punto" and not minore and str(nome or "").strip():
        # Un tutore che dice a che punto è il suo ragazzo («Nina in matematica è alle
        # sottrazioni col prestito»): vale per il ragazzo
        t = speakers.find(nome) if speakers is not None else None
        bersaglio = speakers.get(t) if t else None
        if bersaglio is None or not M.e_minore(bersaglio):
            return {"ok": False, "fatto": NIENTE, "errore": "di quale ragazzo?",
                    "cosa_fare": "chiedi di quale ragazzo parla"}
        if not (M.e_tutore(prof, bersaglio) or getattr(prof, "admin", False)):
            note_rule(ctx, "esercizi_punto_permesso")
            return _final(f"A che punto è {bersaglio.name} me lo può dire lui o un suo "
                          f"tutore.", ok=False, fatto=NIENTE)
        out = srv.a_che_punto(prof, str(materia or ""), str(argomento or ""), str(entro or ""),
                              _bool(riporto), str(classe or ""), minore=bersaglio)
        regola = out.pop("regola", None)
        if regola:
            note_rule(ctx, regola)
        return out
    if not minore and not _segue_qualcuno(prof, speakers):
        note_rule(ctx, "esercizi_permesso")
        return _final("Gli esercizi sono per i ragazzi di casa e per chi li segue.", ok=False,
                      fatto=NIENTE)
    if azione == "argomenti":
        eta = M.eta(getattr(prof, "nascita", None)) if minore else None
        cl = classe_da_testo(classe) or classe_da_eta(eta)
        el = srv.elenco_argomenti(cl, materia_da_testo(materia))
        return _final(f"Posso farti esercizi di {el}." if el else
                      f"Ho esercizi di {elenco_materie()}.")
    if azione == "inizia" and not str(argomento or "").strip() and str(materia or "").strip():
        from ..esercizi import materia_da_testo
        from ..esercizi.sessione import argomento_unico
        mat = materia_da_testo(materia)
        dalla_frase = argomento_unico(str(getattr(ctx, "user_text", "") or ""), mat) if mat else None
        if dalla_frase:
            # Il modello ha scelto inizia e la materia, ma non l'argomento che la frase nomina:
            # correzione della forma, con un argomento solo nella frase (contrari in prova)
            argomento = dalla_frase
            note_rule(ctx, "esercizi_argomento_dalla_frase")
    if azione in ("inizia", "interroga"):
        hub = getattr(ctx, "schermi", None)
        mitt = None
        if hub is not None:
            try:
                mitt = hub.mittente(ctx)
            except Exception:  # noqa: BLE001
                mitt = None
        note_rule(ctx, "esercizi_inizio")
        if azione == "interroga":
            lista = domande if isinstance(domande, list) else (
                [x for x in str(domande or "").split("\n") if x.strip()])
            out = srv.interroga(prof, M.fascia(prof), M.eta(getattr(prof, "nascita", None)),
                                str(materia or ""), str(argomento or ""), str(classe or ""),
                                mitt, domande=lista, pagina=_pagina(ctx),
                                detto=str(getattr(ctx, "user_text", "") or ""))
        else:
            out = srv.inizia(prof, M.fascia(prof), M.eta(getattr(prof, "nascita", None)),
                             str(materia or ""), str(argomento or ""), str(classe or ""), mitt,
                             modo=str(modo or ""), blocco=str(blocco or ""),
                             entro=str(entro or ""), oltre=bool(_bool(oltre)))
        regola = out.pop("regola", None) if isinstance(out, dict) else None
        if regola:
            note_rule(ctx, regola)
        extra = out.pop("regola_extra", None) if isinstance(out, dict) else None
        if extra:
            note_rule(ctx, extra)
        return out
    if azione == "rispondi":
        if not str(risposta or "").strip():
            return {"ok": False, "errore": "manca la risposta",
                    "cosa_fare": "passa in risposta ciò che ha detto, così com'è"}
        note_rule(ctx, "esercizi_corretto_dal_codice")
        # La frase della persona e l'ultima cosa detta da Calliope (12/10): il numero deve
        # venire da ciò che ha detto, e la domanda deve essere quella del programma
        detto = str(getattr(ctx, "user_text", "") or "")
        ultima = next((c for r, c in reversed(getattr(ctx, "storia", None) or ())
                       if r == "assistant"), "")
        out = srv.rispondi(prof, str(risposta), "voce", detto=detto, ultima=ultima,
                           giudizio=str(giudizio or ""), sicurezza=str(sicurezza or ""))
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
    elif azione == "pausa":
        out = srv.pausa(prof)
    elif azione == "continua":
        out = srv.continua(prof)
    elif azione == "preferenze":
        out = srv.preferenze(prof, str(modo or ""), str(blocco or ""))
    elif azione == "a_che_punto":
        out = srv.a_che_punto(prof, str(materia or ""), str(argomento or ""), str(entro or ""),
                              _bool(riporto), str(classe or ""))
    elif azione == "piu_difficile":
        out = srv.piu_difficile(prof)
    elif azione == "piu_facile":
        out = srv.piu_facile(prof)
    elif azione == "fine":
        out = srv.fine(prof)
    else:
        return {"ok": False, "errore": f"azione sconosciuta: {azione}", "azioni": AZIONI}
    regola = out.pop("regola", None) if isinstance(out, dict) else None
    if regola:
        note_rule(ctx, regola)
    extra = out.pop("regola_extra", None) if isinstance(out, dict) else None
    if extra:
        note_rule(ctx, extra)
    for r in (out.pop("regole", None) or ()) if isinstance(out, dict) else ():
        note_rule(ctx, r)
    return out


def esercizi_spec() -> ToolSpec:
    return ToolSpec(
        name="esercizi",
        description=("Esercizi di studio preparati da Calliope per i ragazzi di casa "
                     "(matematica: operazioni, tabelline, frazioni, problemi, potenze, "
                     "equazioni; italiano: analisi grammaticale e logica; logica: sequenze, "
                     "insiemi, vero o falso; fisica: velocità, densità, forze, peso e lavoro; "
                     "chimica: massa molare, moli, bilanciamento). «Facciamo esercizi di "
                     "frazioni»: azione=inizia con materia e argomento se lo dice, classe solo "
                     "se la dice («terza elementare»), entro («fino a 100», «tre cifre») o "
                     "oltre=true solo se chiede più del programma. «Interrogami sulle "
                     "addizioni», «simuliamo un'interrogazione», anche di storia, scienze o su "
                     "un capitolo: interroga con l'argomento (con una pagina del libro nella "
                     "conversazione, domande prese solo da lì). A «a che punto "
                     "siete?»: a_che_punto con argomento, entro, riporto. Durante gli "
                     "esercizi: rispondi con la risposta così come l'ha detta (la corregge il "
                     "programma, tu non dire se è giusta; a una domanda aperta aggiungi "
                     "giudizio e sicurezza), piu_difficile, piu_facile, aiuto, salta, ripeti, "
                     "segnala («secondo "
                     "me è sbagliato»), soluzione, pausa, continua (dopo una pausa), fine; "
                     "preferenze con modo (giocoso, punti, tappe, normale) o blocco («3», «più "
                     "corti») quando li vuole in un altro modo: resta salvato. Le domande le fa "
                     "solo il programma. argomenti: cosa si può fare. riepilogo: "
                     "come sono andati (un adulto: nome del ragazzo). Non per i compiti portati "
                     "da scuola: quelli sono compiti_aiuto."),
        parameters={"type": "object", "properties": {
            "azione": {"type": "string", "enum": AZIONI},
            "materia": {"type": "string", "enum": ["matematica", "italiano", "logica",
                                                   "fisica", "chimica"]},
            "argomento": {"type": "string",
                          "description": "con le sue parole, se lo dice: «densità», «analisi "
                                         "logica», «sequenze», «le moli»"},
            "classe": {"type": "string"}, "risposta": {"type": "string"},
            "nota": {"type": "string"}, "nome": {"type": "string"},
            "modo": {"type": "string", "enum": MODI},
            "blocco": {"type": "string",
                       "description": "esercizi prima di una pausa: un numero, «più corti» o "
                                      "«più lunghi»"},
            "entro": {"type": "string", "description": "fino a che numero: «100», «tre cifre»"},
            "riporto": {"type": "boolean",
                        "description": "col riporto o prestito (true) o senza (false)"},
            "oltre": {"type": "boolean"},
            "giudizio": {"type": "string", "enum": ["giusta", "in_parte", "sbagliata"]},
            "sicurezza": {"type": "string", "enum": ["alta", "bassa"]},
            "domande": {"type": "array", "items": {"type": "string"}}},
            "required": ["azione"]},
        func=_esercizi, risk="lettura", levels=FAMILY, classe="sicuro")
