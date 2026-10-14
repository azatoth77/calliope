"""
I conoscenti a voce (14/10, decisione 0030; calliope/stanza/conoscenti.py). Solo chi amministra,
con la voce riconosciuta sopra soglia (lo scritto chiede la voce; il «sì» breve vale con
l'impronta compatibile, come le conferme di chi amministra).

conoscenti(azione, chi):
- `elenco`: chi conosco (nome, cognome, nota) e quante voci nuove aspettano una risposta sullo
  schermo; lettura;
- `dimentica`: «Calliope, dimentica Marco»: impronta, profilo e le sue righe della stanza su
  disco, dopo la domanda e il «sì». Più conoscenti con quel nome: Calliope chiede quale, con
  cognome e nota.

Le classi per la politica sono in calliope/politica.py (CLASSI), gli argomenti e gli effetti in
calliope/valore.py.

conoscente_livello(azione, chi, nascita, tutori) — la stessa via sicura dei cambi di livello di
oggi (registra_utente: pericoloso, chiesto in questo turno, frase di sfida con dati di mezzo),
più la domanda e il «sì»:
- `promuovi`: il conoscente diventa familiare (stesso id e impronta; con `nascita` di un minore
  servono i `tutori`, adulti di casa); poi Calliope propone di rifare la registrazione della
  voce, senza obbligo;
- `declassa`: un familiare (non chi amministra, non un minore) torna conoscente.

Ci sono solo con `stanza_conoscenti: true` e la stanza accesa (main.py).
"""

from __future__ import annotations

import datetime
import re

from ..testi import ADMIN, NIENTE
from .spec import ToolContext, ToolSpec, note_rule, serve_la_voce

_TURNI_PER_IL_SI = 3


def _final(frase: str, ok: bool = True, **extra) -> dict:
    return {"ok": ok, **({} if ok else {"fatto": NIENTE}), "conferma": frase,
            "risposta_finale": frase, **extra}


def _con(ctx):
    st = getattr(ctx, "stanza", None)
    return getattr(st, "conoscenti", None) if st is not None else None


def _chi_parla(ctx):
    sc = getattr(ctx, "speaker_ctx", None)
    nome = getattr(sc, "current_speaker", None)
    reg = getattr(ctx, "speakers", None)
    prof = reg.get(nome) if (reg is not None and nome) else None
    return sc, prof


def _verifica(ctx, tool: str, args: dict, cosa: str) -> dict | None:
    """None se chi parla è chi amministra con la voce (o il «sì» breve compatibile); altrimenti
    il rifiuto, o la richiesta della voce per lo scritto."""
    sc, prof = _chi_parla(ctx)
    scritta = serve_la_voce(ctx, tool, args, cosa)
    if scritta is not None:
        return scritta
    come = getattr(sc, "identified_by", None)
    voce_ok = come == "voce" or (come == "breve" and getattr(sc, "conferma_breve", False))
    if prof is None or not getattr(prof, "admin", False) or not voce_ok:
        return _final("I conoscenti li gestisce solo chi amministra, a voce.", ok=False)
    return None


def _proposta(con, chiave: str, turno: int) -> bool:
    """True (e la consuma) se la domanda è aperta: questo è il «sì»; altrimenti la apre."""
    p = con.domande.get(chiave)
    if p is not None and 0 < turno - p <= _TURNI_PER_IL_SI:
        con.domande.pop(chiave, None)
        return True
    con.domande[chiave] = turno
    return False


def _elenco_detto(cs) -> str:
    nomi = [c.descrizione() for c in cs]
    if len(nomi) == 1:
        return nomi[0]
    return "; ".join(nomi[:-1]) + " e " + nomi[-1]


def _uno(con, chi: str):
    """(conoscente, None) o (None, risultato): nessuno, o più d'uno con quel nome (omonimi)."""
    chi = " ".join(str(chi or "").split())
    if not chi:
        return None, {"ok": False, "fatto": NIENTE, "correggibile": True,
                      "errore": "manca chi", "cosa_fare": "richiama con chi=il nome"}
    trovati = con.trova(chi)
    if not trovati:
        return None, _final(f"Non conosco nessun conoscente che si chiami {chi}.", ok=False)
    if len(trovati) > 1:
        frase = (f"Conosco {len(trovati)} persone che si chiamano {trovati[0].nome}: "
                 f"{_elenco_detto(trovati)}. Quale?")
        return None, _final(frase, ok=False, omonimi=[c.descrizione() for c in trovati],
                            cosa_fare="richiama con chi=nome e cognome, o nome e nota")
    return trovati[0], None


def _conoscenti(ctx: ToolContext, azione: str = "", chi: str = "") -> dict:
    con = _con(ctx)
    if con is None:
        return _final("Qui non tengo i conoscenti.", ok=False)
    azione = str(azione or "").strip().lower()
    args = {"azione": azione, "chi": chi}
    no = _verifica(ctx, "conoscenti", args, "i conoscenti")
    if no is not None:
        note_rule(ctx, "conoscenti_negato")
        return no
    if azione == "elenco":
        cs = con.elenco()
        aperte = len(con.proposte_aperte())
        attesa = (f" {aperte} voci nuove aspettano la tua risposta sul tuo schermo."
                  if aperte > 1 else " Una voce nuova aspetta la tua risposta sul tuo schermo."
                  if aperte == 1 else "")
        if not cs:
            return _final("Non ho ancora conoscenti salvati." + attesa)
        return _final(f"Conosco {len(cs)} {'persona' if len(cs) == 1 else 'persone'} fuori "
                      f"dalla famiglia: {_elenco_detto(cs)}." + attesa, conoscenti=len(cs))
    if azione == "dimentica":
        c, no = _uno(con, chi)
        if c is None:
            return no
        turno = int(getattr(ctx, "turno", 0) or 0)
        if _proposta(con, f"dimentica:{c.id}", turno) or getattr(ctx, "politica_accettata",
                                                                  False):
            con.domande.pop(f"dimentica:{c.id}", None)
            con.dimentica(c.id)
            note_rule(ctx, "conoscente_dimenticato")
            return _final(f"Fatto: ho dimenticato {c.descrizione()}, la sua voce e le sue frasi.")
        domanda = (f"Dimentico {c.descrizione()}: la sua voce e quello che ha detto nelle "
                   "stanze? Non si recupera.")
        return _final(domanda, ok=False, in_sospeso={
            "domanda": domanda, "cosa": f"dimenticare {c.descrizione()}", "tool": "conoscenti",
            "argomenti": {"azione": "dimentica", "chi": c.descrizione()}})
    return {"ok": False, "fatto": NIENTE, "correggibile": True,
            "errore": f"azione sconosciuta: {azione!r}", "cosa_fare": "usa elenco o dimentica"}


def _data(nascita: str) -> str | None:
    n = str(nascita or "").strip()
    if not n:
        return None
    try:
        return datetime.date.fromisoformat(n).isoformat()
    except ValueError:
        return ""


def _conoscente_livello(ctx: ToolContext, azione: str = "", chi: str = "", nascita: str = "",
                        tutori: str = "") -> dict:
    con = _con(ctx)
    if con is None:
        return _final("Qui non tengo i conoscenti.", ok=False)
    azione = str(azione or "").strip().lower()
    args = {"azione": azione, "chi": chi, **({"nascita": nascita} if nascita else {}),
            **({"tutori": tutori} if tutori else {})}
    cosa = "cambiare chi è di famiglia"
    no = _verifica(ctx, "conoscente_livello", args, cosa)
    if no is not None:
        note_rule(ctx, "conoscente_livello_negato")
        return no
    turno = int(getattr(ctx, "turno", 0) or 0)
    reg = ctx.speakers
    if azione == "promuovi":
        c, no = _uno(con, chi)
        if c is None:
            return no
        data = _data(nascita)
        if data == "":
            return {"ok": False, "fatto": NIENTE, "correggibile": True,
                    "errore": "nascita non valida", "cosa_fare": "nascita come AAAA-MM-GG"}
        from .. import minori
        ids_tutori = []
        minore = bool(data and minori.e_minore(type("P", (), {"nascita": data,
                                                               "fascia": None})()))
        if minore:
            nomi = [n for n in re.split(r"[,;]| e ", str(tutori or "")) if n.strip()]
            for n in nomi:
                vero = reg.find(n.strip()) if hasattr(reg, "find") else n.strip()
                p = reg.get(vero) if vero else None
                if p is None or minori.e_minore(p):
                    return _final(f"Non trovo un adulto di casa che si chiami {n.strip()}: i "
                                  "tutori devono essere adulti della famiglia.", ok=False)
                ids_tutori.append(p.id)
            if not ids_tutori:
                return _final(f"{c.nome} è minorenne: dimmi chi gli fa da genitore, fra gli "
                              "adulti di casa.", ok=False,
                              cosa_fare="richiama con tutori=i nomi")
        chiave = f"promuovi:{c.id}"
        if not (_proposta(con, chiave, turno) or getattr(ctx, "politica_accettata", False)):
            domanda = (f"Rendo {c.descrizione()} una persona di famiglia, con i permessi dei "
                       "familiari" + (" e le regole dei ragazzi" if minore else "") + "?")
            return _final(domanda, ok=False, in_sospeso={
                "domanda": domanda, "cosa": f"rendere {c.nome_pieno()} di famiglia",
                "tool": "conoscente_livello", "argomenti": dict(args, chi=c.descrizione())})
        con.domande.pop(chiave, None)
        try:
            prof = con.promuovi(c.id, nascita=data or None, tutori=ids_tutori)
        except ValueError as e:
            return _final(str(e), ok=False)
        note_rule(ctx, "conoscente_promosso")
        return _final(f"Fatto: {prof.name} adesso è di famiglia. Se vuoi, rifacciamo la "
                      f"registrazione della sua voce per riconoscerlo meglio: basta dirmi "
                      f"«registra di nuovo la voce di {prof.name}».")
    if azione == "declassa":
        nome = " ".join(str(chi or "").split())
        vero = reg.find(nome) if hasattr(reg, "find") else nome
        prof = reg.get(vero) if vero else None
        if prof is None:
            return _final(f"In famiglia non c'è nessuno che si chiami {nome}.", ok=False)
        _, io = _chi_parla(ctx)
        if prof is io:
            return _final("Non posso togliere dalla famiglia chi me lo chiede.", ok=False)
        chiave = f"declassa:{prof.id}"
        if not (_proposta(con, chiave, turno) or getattr(ctx, "politica_accettata", False)):
            domanda = (f"{prof.name} non sarà più di famiglia ma un conoscente, con i permessi "
                       "di un ospite. Procedo?")
            return _final(domanda, ok=False, in_sospeso={
                "domanda": domanda, "cosa": f"togliere {prof.name} dalla famiglia",
                "tool": "conoscente_livello", "argomenti": {"azione": "declassa",
                                                            "chi": prof.name}})
        con.domande.pop(chiave, None)
        try:
            c = con.declassa(prof)
        except ValueError as e:
            return _final(str(e), ok=False)
        note_rule(ctx, "conoscente_declassato")
        return _final(f"Fatto: {c.nome_pieno()} adesso è un conoscente.")
    return {"ok": False, "fatto": NIENTE, "correggibile": True,
            "errore": f"azione sconosciuta: {azione!r}", "cosa_fare": "usa promuovi o declassa"}


def conoscenti_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="conoscenti",
            description=(
                "Le persone fuori dalla famiglia che riconosco dalla voce (i conoscenti, "
                "salvati da chi amministra). azione=elenco per «chi conosci?», «quali "
                "conoscenti hai?»; azione=dimentica per «dimentica Marco» detto di un "
                "conoscente (chi: nome, con cognome o nota se ce ne sono più d'uno). Non per "
                "i ricordi (dimentica) né per le conversazioni."),
            parameters={"type": "object",
                        "properties": {"azione": {"type": "string",
                                                  "enum": ["elenco", "dimentica"]},
                                       "chi": {"type": "string"}},
                        "required": ["azione"]},
            func=_conoscenti, risk="azione", levels=ADMIN),
        ToolSpec(
            name="conoscente_livello",
            description=(
                "Cambia chi è di famiglia: azione=promuovi per «Marco adesso è di famiglia» "
                "(un conoscente diventa familiare; se è minorenne nascita AAAA-MM-GG e tutori), "
                "azione=declassa per «Luca non è più di famiglia, è un conoscente». chi: il "
                "nome."),
            parameters={"type": "object",
                        "properties": {"azione": {"type": "string",
                                                  "enum": ["promuovi", "declassa"]},
                                       "chi": {"type": "string"},
                                       "nascita": {"type": "string"},
                                       "tutori": {"type": "string"}},
                        "required": ["azione", "chi"]},
            func=_conoscente_livello, risk="azione", levels=ADMIN),
    ]
