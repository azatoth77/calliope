"""
I tool degli schermi (calliope/schermi/, 02/10/2026).

Le schede partono da sole dai tool (lista, timer, biblioteca, documento, casa, calcolo):
qui ci sono solo le richieste esplicite e la gestione.

- schermo_mostra(cosa): «mostramelo sullo schermo», «metti la lista sullo schermo»,
  «fammelo leggere», «togli dallo schermo». La scheda la costruisce il codice (il modello
  sceglie solo `cosa`); la frase è pronta (`risposta_finale`) e dice cosa è successo davvero:
  «è sullo schermo del soggiorno», «qui non c'è uno schermo», «è personale: la mostro solo
  sul tuo schermo». Così la voce non promette «te lo mostro» quando non succede.
- schermo_gestisci(azione, codice, stanza, personale, persona): abbinare, scollegare ed
  elencare gli schermi. Solo chi amministra (come le installazioni). Il codice non si scrive
  mai nei log (ToolSpec.segreti) e non si ripete a voce. Dal 03/10 anche «questo schermo è
  mio» (azione personale) e «rendilo condiviso» (condiviso): lo schermo del satellite da cui
  si parla, o quello nominato; chi amministra riconosciuto dalla voce in quella frase; si fa
  solo dopo il «sì» (domanda con azione in sospeso, proposta valida nella risposta dopo).

Regole (principio 10): il codice detto si prende dalla frase solo se l'argomento del modello
non ha 6 cifre («codice_dalla_frase», correzione della forma di una scelta già fatta), la
stanza si normalizza («al soggiorno» → «soggiorno»). Le visibilità sono permessi, nel codice.
"""

import re
import time
from pathlib import Path

from ..schermi import cifre, norm_stanza, schede
from ..conferme import proposta_valida, secondi_validi
from .spec import ToolContext, ToolSpec, note_rule
from ..testi import ADMIN, ALL, NIENTE

# La persona detta come «io» («il mio schermo»): vale chi parla
_IO = frozenset({"me", "io", "mio", "mia", "il mio", "la mia", "me stesso", "me stessa",
                 "chi parla", "myself", "me stess"})


def _io(persona) -> bool:
    """«me», «io», «chi_parla» (03/10: il modello scrive anche così)."""
    return str(persona or "").strip().lower().replace("_", " ") in _IO


# «promemoria» e non «agenda»: con «agenda» il modello sceglieva timer per «fammi vedere i
# miei promemoria sullo schermo» (prova del 02/10)
COSE = ("ultima", "risposta", "lista", "timer", "promemoria", "documento", "casa", "niente")
# I tool che toccano cose personali: la loro risposta, riletta sullo schermo, è personale
_PERSONALI = {"promemoria_imposta", "appuntamento_aggiungi", "appuntamenti_elenca",
              "agenda_elenca", "ricorda", "dimentica", "documento_crea", "documento_modifica",
              "pc_cerca_file", "pc_apri_file", "pc_programmi", "chi_parla"}


def _final(text: str, ok: bool = True, **extra) -> dict:
    return {"ok": ok, **extra, "conferma": text, "risposta_finale": text}


def _person(ctx: ToolContext):
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _level(ctx) -> str:
    return getattr(ctx.speaker_ctx, "current_level", "ospite") or "ospite"


def _di(nome) -> str:
    """«del soggiorno», «della cucina», «dello studio», «dell'ingresso». Il genere dalla
    vocale finale della prima parola: basta per i nomi delle stanze."""
    n = str(nome or "").strip()
    first = n.split(" ")[0].lower()
    if n[:1].lower() in "aeiouàèéìòù":
        return f"dell'{n}"
    if first.endswith("a"):
        return f"della {n}"
    if re.match(r"(s[bcdfgklmnpqrtvz]|z|gn|ps|x|y)", first):
        return f"dello {n}"
    return f"del {n}"


def _dove(nomi: list[str]) -> str:
    """«sullo schermo del soggiorno», «sugli schermi del soggiorno e della cucina»."""
    nomi = list(dict.fromkeys(nomi))
    if len(nomi) == 1:
        return f"sullo schermo {_di(nomi[0])}"
    return "sugli schermi " + ", ".join(_di(n) for n in nomi[:-1]) + f" e {_di(nomi[-1])}"


# ─────────────────────────── schermo_mostra ───────────────────────────

def _scheda_per(ctx: ToolContext, cosa: str, lista: str, hub, sender):
    """(scheda, frase d'errore): la scheda da mostrare per `cosa`, costruita dal codice."""
    prof = _person(ctx)
    if cosa == "niente":
        return schede.vuota(), ""
    if cosa == "ultima":
        card = hub.ultima(sender)
        if card is not None:
            return card, ""
        cosa = "risposta"                     # nessuna scheda: la risposta di prima
    if cosa == "risposta":
        prev = getattr(ctx, "risposta_precedente", None) or {}
        text = (prev.get("testo") or "").strip()
        if not text:
            return None, "Non ho ancora niente da mostrarti: chiedimi prima qualcosa."
        # Chi ha usato tool personali nella risposta di prima la rilegge solo sul suo schermo
        vis = (schede.PERSONALE if set(prev.get("tool") or ()) & _PERSONALI
               else schede.CASA if prof else schede.PUBBLICA)
        return schede.testo("Ultima risposta", text, vis), ""
    if cosa == "lista":
        if ctx.liste is None:
            return None, "Le liste non sono disponibili."
        key, items = ctx.liste.read(lista or "spesa")
        return schede.lista(key, items), ""
    if cosa == "timer":
        if ctx.agenda is None:
            return None, "L'agenda non è disponibile."
        return schede.timer_attivi(ctx.agenda), ""
    if cosa in ("promemoria", "agenda", "appuntamenti"):
        if prof is None or ctx.agenda is None:
            return None, "Non so chi sei, quindi non posso mostrarti la tua agenda."
        return schede.promemoria(ctx.agenda, prof.id, prof.name), ""
    if cosa == "documento":
        svc = getattr(ctx, "documenti", None)
        if prof is None or svc is None:
            return None, "Non trovo un tuo documento da mostrare."
        last = svc.archive.last(prof.id)
        if last is None:
            return None, "Non trovo un tuo documento da mostrare: prima dimmi cosa preparare."
        return schede.documento(last["contenuto"], last["formato"],
                                Path(str(last.get("nome_file") or "")).name,
                                ident=last.get("id")), ""
    if cosa == "casa":
        be = getattr(ctx, "casa", None)
        if be is None:
            return None, "La casa non è collegata, quindi non ho niente da mostrare."
        from ..casa.regole import Regole
        try:
            ents = be.entita()
        except Exception:  # noqa: BLE001 — CasaNonRisponde e simili
            return None, "La casa non risponde: riprova tra poco."
        rules = Regole(ctx.cfg)
        visible = [e for e in ents if rules.visibile(e, _level(ctx))]
        # Le cose che si accendono o si aprono e le temperature: il resto è rumore
        utili = [e for e in visible if e.dominio in ("light", "switch", "fan", "cover",
                                                     "climate", "media_player")
                 or (e.dominio == "sensor" and e.classe in ("temperature", "humidity"))]
        if not utili:
            return None, "In casa non vedo dispositivi da mostrare."
        return schede.casa(utili, "Com'è la casa"), ""
    return None, "Non so cosa mostrare: dimmi se la lista, i timer, l'agenda o l'ultima risposta."


def _schermo_mostra(ctx: ToolContext, cosa: str = "ultima", lista: str = "") -> dict:
    hub = getattr(ctx, "schermi", None)
    if hub is None:
        return _final("Gli schermi non sono attivi in questa installazione.", ok=False,
                      fatto=NIENTE)
    cosa = str(cosa or "ultima").strip().lower()
    if cosa in ("agenda", "appuntamenti"):          # sinonimi dello stesso valore
        cosa = "promemoria"
    if cosa not in COSE:
        cosa = "ultima"
    sender = hub.mittente(ctx)
    card, why = _scheda_per(ctx, cosa, str(lista or ""), hub, sender)
    if card is None:
        return _final(why, ok=False, fatto=NIENTE)
    # Una scheda o più (i timer: una per timer, ognuna con la sua identità)
    reached, dest, motivo = [], [], None
    for c in (card if isinstance(card, list) else [card]):
        r = hub.invia(c, sender, forza=True)
        reached += r.get("schermi") or []
        dest += r.get("destinatari") or []
        motivo = motivo or r.get("motivo")
    reached, dest = list(dict.fromkeys(reached)), list(dict.fromkeys(dest))
    if dest:
        if cosa == "niente":
            return _final("Fatto, ho tolto tutto dallo schermo.", fatto="schermo libero")
        if reached:
            return _final(f"Ecco, è {_dove(reached)}.", fatto="mostrato")
        # Abbinato ma spento: la scheda resta nella sua cronologia e arriva alla riaccensione
        spento = (f"Lo schermo {_di(dest[0])} sembra spento" if len(dest) == 1
                  else "Gli schermi sembrano spenti")
        return _final(f"{spento}: lo vedrai appena si riaccende.",
                      fatto="in attesa dello schermo")
    if motivo == "nessuno_schermo":
        if _level(ctx) == "amministra":
            return _final(f"Non c'è ancora nessuno schermo abbinato: apri {hub.url} sul "
                          f"computer o sul tablet e dimmi il codice che compare.", ok=False,
                          fatto=NIENTE)
        return _final("Non c'è ancora nessuno schermo abbinato: chiedi a chi amministra di "
                      "abbinarne uno.", ok=False, fatto=NIENTE)
    if motivo == "personale":
        return _final("È una cosa tua: la mostro solo su uno schermo personale, e non ne hai "
                      "uno abbinato.", ok=False, fatto=NIENTE)
    if motivo == "zona_grigia":
        return _final("Non ho riconosciuto bene la tua voce: le cose personali non le mostro. "
                      "Ripetilo dopo avermi chiamata per nome.", ok=False, fatto=NIENTE)
    if motivo == "ospite":
        return _final("Questo lo mostro solo a chi riconosco dalla voce.", ok=False,
                      fatto=NIENTE)
    if motivo == "stanza":
        return _final("In questa stanza non c'è uno schermo.", ok=False, fatto=NIENTE)
    return _final("Non sono riuscita a mostrarlo.", ok=False, fatto=NIENTE)


# ─────────────────────────── schermo_gestisci ───────────────────────────

def _elenco_frase(hub) -> str:
    st = hub.stato()
    if not st["abbinati"]:
        return (f"Non c'è nessuno schermo abbinato. Per abbinarne uno apri {hub.url} sul "
                f"computer o sul tablet e dimmi il codice che compare.")
    parti = []
    for s in st["schermi"]:
        p = s["nome"]
        if s.get("personale_di") and s["personale_di"].lower() not in p:
            p += f", personale di {s['personale_di']}"
        p += " (acceso)" if s["collegato"] else " (spento)"
        parti.append(p)
    n = st["abbinati"]
    elenco = parti[0] if n == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]
    return (f"C'è uno schermo: {elenco}." if n == 1 else f"Ci sono {n} schermi: {elenco}.")


def _bersaglio(ctx: ToolContext, hub, stanza: str) -> tuple[dict | None, str]:
    """(schermo, frase d'errore). Con la stanza: prima un satellite con quel nome o in quella
    stanza (il suo schermo segue il satellite: cambiare solo lo schermo non durerebbe), poi
    uno schermo abbinato. Senza: il satellite da cui si parla."""
    srv = getattr(hub, "satelliti", None)
    q = norm_stanza(stanza)
    if q:
        for tipo, arch in (("satellite", getattr(srv, "archivio", None)),
                           ("schermo", hub.archivio)):
            via = arch.trova(q) if arch is not None else []
            if len(via) == 1:
                return dict(via[0], tipo=tipo), ""
            if len(via) > 1:
                return None, f"Ci sono più schermi «{q}»: dimmi quale, con il suo nome."
        return None, f"Non trovo uno schermo «{q}». {_elenco_frase(hub)}"
    coll = getattr(srv, "attivo", None) if srv is not None else None
    if coll is not None:
        via = srv.archivio.trova(coll.satellite.get("id"))
        if via:
            return dict(via[0], tipo="satellite"), ""
    return None, ""


def _nome_schermo(s: dict) -> str:
    return f"lo schermo {_di(s.get('stanza') or s.get('nome'))}"


def _maiuscola(t: str) -> str:
    return t[:1].upper() + t[1:]


def _proposta_ok(ctx, prop: dict, turno: int) -> bool:
    """La proposta di uno schermo (personale, condiviso, abbinamento personale) vale ancora:
    nei turni dopo, per `azione_in_sospeso_turni` turni ed entro `azione_in_sospeso_s`."""
    return (proposta_valida(ctx.cfg, prop.get("turno", 0), turno)
            and time.monotonic() - prop.get("quando", time.monotonic()) <= secondi_validi(ctx.cfg))


def _proprietario(ctx: ToolContext, hub, azione: str, stanza: str, persona: str) -> dict:
    """«Questo schermo è mio» / «rendilo condiviso» (03/10). Solo chi amministra (il registro
    lo controlla già), riconosciuto dalla voce nella frase della richiesta; si fa solo dopo
    il «sì», nella risposta dopo la domanda (come le installazioni: `hub.proposte`)."""
    chi = _person(ctx)
    if _level(ctx) != "amministra" or chi is None:
        note_rule(ctx, "schermo_proprietario_permesso")
        return _final("Rendere personale o condiviso uno schermo lo può chiedere solo chi "
                      "amministra.", ok=False, fatto=NIENTE)
    s, why = _bersaglio(ctx, hub, stanza)
    if s is None:
        if why:
            return _final(why, ok=False, fatto=NIENTE)
        return {"ok": False, "fatto": NIENTE, "errore": "manca quale schermo",
                "cosa_fare": "chiedi di quale schermo si tratta (la stanza), poi richiama "
                             "schermo_gestisci con la stanza"}
    # Di chi: chi parla, a meno di un altro nome registrato; condiviso = di nessuno
    owner = owner_name = None
    if azione == "personale":
        if _io(persona):
            note_rule(ctx, "persona_io")
            persona = ""
        prof = (ctx.speakers.get(str(persona).strip().title()) if persona and ctx.speakers
                else chi)
        if prof is None:
            return _final(f"Non conosco {persona}: uno schermo personale è di una persona "
                          f"registrata.", ok=False, fatto=NIENTE)
        owner, owner_name = prof.id, prof.name
    suo = "tuo" if owner == chi.id else f"di {owner_name}"
    nome = _nome_schermo(s)
    if s.get("proprietario") == owner:
        hub.proposte.pop(chi.id, None)
        return _final(f"{_maiuscola(nome)} è già "
                      + (f"personale {suo}." if owner else "condiviso."),
                      fatto="nessun cambiamento")
    chiave = {"tipo": s["tipo"], "id": s["id"], "proprietario": owner}
    prima = hub.proposte.get(chi.id)
    turno = int(getattr(ctx, "turno", 0) or 0)
    # Valida nei turni dopo la proposta, per più turni (04/10, conferme.py)
    confermata = (prima is not None and prima["chiave"] == chiave
                  and _proposta_ok(ctx, prima, turno))
    # La richiesta vuole la voce riconosciuta in quella frase; il «sì» può essere breve
    how = getattr(ctx.speaker_ctx, "identified_by", None)
    if how != "voce":       # anche il «sì» (03/10): una frase breve vale al più familiare
        note_rule(ctx, "schermo_proprietario_permesso")
        return _final("In questa frase non ti ho riconosciuto bene dalla voce: ripeti la "
                      "richiesta con una frase un po' più lunga.", ok=False, fatto=NIENTE)
    if not confermata:
        hub.proposte[chi.id] = {"chiave": chiave, "turno": turno, "quando": time.monotonic()}
        if owner:
            domanda = f"lo rendo personale {suo}?"
            frase = (f"{_maiuscola(nome)} riceverà anche promemoria, appuntamenti e documenti"
                     + ("" if owner == chi.id else f" di {owner_name}") + f": {domanda}")
        else:
            di_chi = ("tuoi" if s.get("proprietario") == chi.id
                      else f"di {s['proprietario_nome']}" if s.get("proprietario_nome")
                      else "personali")
            domanda = "lo rendo condiviso?"
            frase = (f"{_maiuscola(nome)} non riceverà più promemoria, appuntamenti e "
                     f"documenti {di_chi}: {domanda}")
        args = {"azione": azione, "stanza": s.get("stanza") or s.get("nome")}
        if owner and owner != chi.id:
            args["persona"] = owner_name
        cosa = (f"rendere {nome} personale "
                + ("di chi parla" if owner == chi.id else suo) if owner
                else f"rendere {nome} condiviso")
        return _final(frase, fatto="proposta: NIENTE è stato ancora cambiato",
                      in_sospeso={"domanda": _maiuscola(domanda), "cosa": cosa,
                                  "tool": "schermo_gestisci", "argomenti": args})
    hub.proposte.pop(chi.id, None)
    if s["tipo"] == "satellite":
        fatto = hub.satelliti.imposta_proprietario(s["id"], owner, owner_name)
    else:
        fatto = hub.archivio.imposta_proprietario(s["id"], owner, owner_name)
        hub._rinfresca()
    if fatto is None:
        return _final(f"Non trovo più {nome}: forse è stato scollegato.", ok=False,
                      fatto=NIENTE)
    if owner:
        return _final(f"Fatto: {nome} è personale {suo}, e lì mostro anche promemoria, "
                      f"appuntamenti e documenti.", fatto="personale")
    return _final(f"Fatto: {nome} è di nuovo condiviso.", fatto="condiviso")


def _schermo_gestisci(ctx: ToolContext, azione: str = "elenca", codice: str = "",
                      stanza: str = "", personale=False, persona: str = "") -> dict:
    hub = getattr(ctx, "schermi", None)
    if hub is None:
        return _final("Gli schermi non sono attivi in questa installazione.", ok=False,
                      fatto=NIENTE)
    azione = str(azione or "elenca").strip().lower()
    if azione == "elenca":
        return _final(_elenco_frase(hub))
    # Il «sì» a un abbinamento personale proposto nella risposta prima (03/10): si abbina
    # con il codice e la stanza della proposta, anche se il modello non li ripete
    chi = _person(ctx)
    turno = int(getattr(ctx, "turno", 0) or 0)
    prop = hub.proposte.get(chi.id) if chi is not None else None
    if (prop is not None and prop.get("abbina") and azione in ("abbina", "personale")
            and _proposta_ok(ctx, prop, turno)
            and cifre(codice) in ("", prop["abbina"]["codice"])):
        if getattr(ctx.speaker_ctx, "identified_by", None) != "voce":
            # La proposta resta: un «sì» che non basta non la perde (04/10)
            note_rule(ctx, "schermo_proprietario_permesso")
            return _final("In questa frase non ti ho riconosciuto bene dalla voce: chiedimelo "
                          "di nuovo.", ok=False, fatto=NIENTE)
        hub.proposte.pop(chi.id, None)
        a = prop["abbina"]
        return _esito_abbina(hub.abbina(a["codice"], a["stanza"], a["owner"], a["owner_name"]),
                             a["owner_name"])
    # «Questo satellite è il mio schermo personale» con azione=abbina ma senza nessun codice
    # (né negli argomenti né nella frase): non c'è niente da abbinare, e il modello ha già
    # scelto «personale» (forma di una scelta già fatta, principio 10)
    vuole_personale = personale is True or str(personale).strip().lower() in ("true", "1")
    if (azione == "abbina" and (vuole_personale or persona) and not cifre(codice)
            and not cifre(getattr(ctx, "user_text", ""))):
        note_rule(ctx, "schermo_personale_senza_codice")
        azione = "personale"
    # Il caso opposto: «abbina lo schermo 123 456 come mio schermo personale» con
    # azione=personale e le cifre del codice: è un abbinamento personale (02/10 andava così;
    # con l'azione nuova il modello a volte sceglie «personale», 03/10)
    elif azione == "personale" and (len(cifre(codice)) == 6
                                    or len(cifre(getattr(ctx, "user_text", ""))) == 6):
        note_rule(ctx, "schermo_personale_con_codice")
        azione, personale = "abbina", True
    if azione in ("personale", "condiviso"):
        return _proprietario(ctx, hub, azione, stanza, persona)
    if azione == "scollega":
        q = norm_stanza(stanza or persona)
        if not q:
            return {"ok": False, "fatto": NIENTE, "errore": "manca quale schermo",
                    "cosa_fare": "chiedi quale schermo scollegare (la stanza)"}
        via = hub.revoca(q)
        if not via:
            return _final(f"Non trovo uno schermo «{q}». {_elenco_frase(hub)}", ok=False,
                          fatto=NIENTE)
        nomi = [s["nome"] for s in via]
        cosa = (f"lo schermo {_di(nomi[0])}" if len(nomi) == 1
                else f"{len(nomi)} schermi {_di(q)}")
        return _final(f"Fatto, ho scollegato {cosa}: non riceverà più niente."
                      if len(nomi) == 1 else f"Fatto, ho scollegato {cosa}: non riceveranno "
                      f"più niente.", fatto="scollegato")
    if azione != "abbina":
        return {"ok": False, "fatto": NIENTE, "errore": f"azione sconosciuta: {azione}"}
    # Abbinare
    code = cifre(codice)
    if len(code) != 6:
        # Il modello ha perso o storpiato le cifre: si prendono dalla frase detta, se lì ce
        # ne sono esattamente 6 (correzione della forma, principio 10)
        said = cifre(getattr(ctx, "user_text", ""))
        if len(said) == 6:
            code = said
            note_rule(ctx, "codice_dalla_frase")
    if len(code) != 6:
        return _final("Mi servono le 6 cifre che vedi sullo schermo: dimmele una per una.",
                      ok=False, fatto=NIENTE)
    room = norm_stanza(stanza)
    if not room:
        return {"ok": False, "fatto": NIENTE, "errore": "manca la stanza",
                "cosa_fare": "chiedi in che stanza è lo schermo, poi richiama schermo_gestisci "
                             "con lo stesso codice"}
    owner = owner_name = None
    personale = personale is True or str(personale).strip().lower() in ("true", "1", "sì",
                                                                         "si")
    # «come mio schermo personale» → il modello a volte manda persona="me": è chi parla
    # (forma di una scelta già fatta dal modello, 02/10: 2 volte su 8 in prova_schermi_ollama)
    if _io(persona):
        note_rule(ctx, "persona_io")
        persona = ""
    if personale or persona:
        prof = (ctx.speakers.get(str(persona).strip().title()) if persona and ctx.speakers
                else _person(ctx))
        if prof is None:
            return _final(f"Non conosco {persona}: lo schermo personale va abbinato a una "
                          f"persona registrata.", ok=False, fatto=NIENTE)
        owner, owner_name = prof.id, prof.name
        # Abbinare subito come personale ha lo stesso effetto di «questo schermo è mio»
        # (il browser riceve promemoria, appuntamenti e documenti): stesse regole, voce
        # riconosciuta in questa frase e un «sì» nella risposta dopo. Prima bastava il
        # livello, anche con una chiamata indotta da un «fatto della casa» (analisi del
        # 03/10, S3: 8 volte su 10 lo schermo di Bianca diventava personale di Dario)
        if getattr(ctx.speaker_ctx, "identified_by", None) != "voce" or chi is None:
            note_rule(ctx, "schermo_proprietario_permesso")
            return _final("Per abbinare uno schermo personale devo riconoscerti dalla voce: "
                          "ripeti la richiesta con una frase un po' più lunga.", ok=False,
                          fatto=NIENTE)
        hub.proposte[chi.id] = {"abbina": {"codice": code, "stanza": room, "owner": owner,
                                           "owner_name": owner_name}, "turno": turno,
                                "chiave": None, "quando": time.monotonic()}
        suo = "tuo" if owner == chi.id else f"di {owner_name}"
        domanda = f"Lo abbino come schermo personale {suo}?"
        args = {"azione": "abbina", "stanza": room, "personale": True}
        if owner != chi.id:
            args["persona"] = owner_name
        return _final(f"Lo schermo {_di(room)} riceverà anche promemoria, appuntamenti e "
                      f"documenti {'tuoi' if owner == chi.id else 'di ' + owner_name}. "
                      f"{domanda}", fatto="proposta: NIENTE è stato ancora abbinato",
                      in_sospeso={"domanda": domanda, "cosa": f"abbinare lo schermo {_di(room)}"
                                  f" come personale {suo}", "tool": "schermo_gestisci",
                                  "argomenti": args})
    return _esito_abbina(hub.abbina(code, room, owner, owner_name), owner_name)


def _esito_abbina(res: dict, owner_name) -> dict:
    """La frase dell'esito di `Schermi.abbina`."""
    esito = res.get("esito")
    if esito == "abbinato":
        s = res["schermo"]
        extra = (f" È personale di {owner_name}: lì mostro anche documenti, promemoria e "
                 f"appuntamenti." if owner_name else "")
        return _final(f"Fatto: lo schermo {_di(s['stanza'])} è abbinato.{extra}",
                      fatto="abbinato", schermo=s["nome"])
    if esito == "troppi":
        return _final("Troppi codici sbagliati: per sicurezza li ho annullati tutti. Sullo "
                      "schermo ne compare uno nuovo tra un attimo.", ok=False, fatto=NIENTE)
    return _final("Questo codice non corrisponde a nessuno schermo in attesa: controlla le 6 "
                  "cifre sullo schermo e ripetile.", ok=False, fatto=NIENTE)


def schermi_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="schermo_mostra",
            description=("Mostra qualcosa su uno schermo di casa, quando lo chiedono: "
                         "«mostramelo sullo schermo», «fammelo vedere», «fammelo leggere», "
                         "«metti la lista sullo schermo», «togli dallo schermo». cosa: "
                         "ultima (quello di cui si parla adesso), risposta (il testo della "
                         "tua ultima risposta), lista, timer, promemoria (i promemoria, gli "
                         "appuntamenti e l'agenda di chi parla: «mettimi sullo schermo i miei "
                         "appuntamenti»), documento (l'ultimo preparato), casa (luci e "
                         "temperature), niente (pulisci lo schermo). lista: il nome della "
                         "lista, se cosa=lista."),
            parameters={"type": "object",
                        "properties": {"cosa": {"type": "string", "enum": list(COSE)},
                                       "lista": {"type": "string"}},
                        "required": ["cosa"]},
            func=_schermo_mostra, risk="lettura", levels=ALL),
        ToolSpec(
            name="schermo_gestisci",
            description=("Abbina, scollega o elenca gli schermi di Calliope (pagine aperte su "
                         "PC, tablet o TV, anche quello del satellite da cui si parla), o li "
                         "rende personali o condivisi. abbina: codice = le 6 cifre che lo "
                         "schermo mostra, stanza = dove si trova («soggiorno», «cucina»), "
                         "personale = true se è lo schermo di una persona (persona = il suo "
                         "nome, se non è chi parla). scollega: stanza dello schermo. elenca: "
                         "quali schermi ci sono. personale: rende personale uno schermo già "
                         "abbinato, senza codice («questo schermo è mio», «questo satellite è il mio schermo "
                         "personale»; stanza vuota = quello da cui si parla; persona = di chi, "
                         "se non è chi parla). condiviso: lo rende di nuovo di tutti («rendilo "
                         "condiviso»). personale e condiviso chiedono conferma: dopo il sì "
                         "richiamalo con gli stessi argomenti."),
            parameters={"type": "object",
                        "properties": {"azione": {"type": "string",
                                                  "enum": ["abbina", "scollega", "elenca",
                                                           "personale", "condiviso"]},
                                       "codice": {"type": "string"},
                                       "stanza": {"type": "string"},
                                       "personale": {"type": "boolean"},
                                       "persona": {"type": "string"}},
                        "required": ["azione"]},
            func=_schermo_gestisci, risk="azione", levels=ADMIN, segreti=("codice",)),
    ]
