"""
I tool dello stato e delle installazioni (01/10/2026).

- calliope_stato(capacita): «cosa sai fare?», «cosa manca?», «perché non riesci a cercare
  su Wikipedia?». Dal registro delle capacità (calliope/capacita.py), filtrato per livello:
  chi amministra sente motivo e prossimo passo, i familiari cosa funziona («chiedi a chi
  amministra» per il resto), gli ospiti solo cosa possono chiedere loro. La frase è pronta
  (`risposta_finale`): il modello non la riformula e non inventa capacità.
- installa_proponi(azione): una proposta con dimensione, spazio libero, tempo e uso di
  internet, che finisce con una domanda. Non scarica niente.
- installa_avvia(azione): parte solo se nel turno prima la stessa persona ha ricevuto la
  proposta per la stessa azione (calliope/installa/servizio.py). Il «sì» lo interpreta il
  modello, con l'azione in sospeso davanti; il resto è nel codice.
- installa_gestisci(azione): «a che punto è?», «annulla il download».

Permessi: installare e annullare solo chi amministra, riconosciuto dalla voce nel turno
della richiesta (non nella zona grigia: allora il livello è già «familiare»). Per il «sì»,
troppo breve per l'impronta, vale l'identità della conversazione appena verificata
(«breve» in main.py): il controllo vero è l'offerta, legata al profilo di chi l'ha chiesta.
"""

from .. import capacita as _cap
from ..installa.catalogo import DESCRIZIONI
from ..conferme import admin_confermato, chiedi_conferma, e_admin
from .spec import ToolContext, ToolSpec, note_rule, serve_la_voce
from ..testi import ADMIN, ALL, FAMILY, NIENTE


def _final(text: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": text, "risposta_finale": text}


def _level(ctx) -> str:
    return getattr(ctx.speaker_ctx, "current_level", "ospite") or "ospite"


def _registro(ctx) -> "_cap.Registro":
    reg = getattr(ctx, "capacita", None)
    if reg is None or not len(reg):
        reg = _cap.REGISTRO if len(_cap.REGISTRO) else _cap.controlla(ctx.cfg)
    return reg


def _plurale(titolo: str) -> bool:
    t = titolo.lower()
    return t.startswith(("i ", "gli ", "le ")) or " e " in t


def _cap1(s: str) -> str:
    return s[:1].upper() + s[1:]


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " e " + items[-1]


def _ospite(ctx, reg) -> str:
    cfg = ctx.cfg
    can = ["l'ora", "la data", "i conti"]
    for c in reg.tutte():
        if c.attiva and c.definizione.ospite:
            can.append(c.definizione.ospite)
    pc = reg.get("pc")
    if pc and pc.attiva and getattr(cfg, "pc_ospite_volume_media", False):
        can.append("il volume e la musica del computer")
    casa = reg.get("casa")
    if casa and casa.attiva and getattr(cfg, "casa_ospite_domini", None):
        can.append("alcuni comandi della casa")
    return f"Puoi chiedermi {_join(can)}."


def _aggiunte(ctx, reg, level: str, dettaglio: bool, solo: str = "") -> str:
    """Cosa si può ancora installare dal catalogo (01/10: a «cosa manca?» Calliope diceva solo
    «funziona tutto quello che è installato»). Chi amministra sente cosa e come chiederlo
    (`dettaglio`: le fonti una per una, altrimenti una frase sola); i familiari un cenno.
    `solo`: «biblioteca» o «voce», per la domanda su una capacità sola."""
    add = _cap.aggiungibili(ctx.cfg)
    bib = reg.get("biblioteca")
    utili = [(a, f) for a, f in add["utili"]
             # la biblioteca intera è già nel «non funziona ancora»
             if not (a == "biblioteca" and bib is not None and not bib.attiva)]
    voci, altre = [n for _, n in add["voci"]], add["altre"]
    if solo == "biblioteca":
        voci = []
    elif solo == "voce":
        utili, altre = [], []
    if not (utili or voci or altre):
        return ""
    if level != "amministra":
        cosa = _join((["altre fonti alla biblioteca"] if utili or altre else [])
                     + (["altre voci"] if voci else []))
        return f" Chi amministra può aggiungere {cosa}."
    voci_frase = ("la voce " + voci[0] if len(voci) == 1 else "le voci " + _join(voci)) \
        if voci else ""
    if dettaglio:
        items = [f for _, f in utili[:3]]
        if voci_frase:
            items.append(voci_frase)
        if altre:
            # La ricerca non le usa ancora: si dicono, ma senza venderle come utili
            n = len(altre)
            items.append((f"{'altre ' if items else ''}{n} fonti della biblioteca, come "
                          f"{_join(altre[:2])}, che per ora non uso nelle risposte") if n > 1
                         else f"{altre[0]}, che per ora non uso nelle risposte")
        frase = " Posso ancora aggiungere: " + "; ".join(items) + "."
    else:
        nomi = [f.split(",")[0] for _, f in utili[:2]]
        rest = len(utili) - len(nomi) + len(altre)
        if rest:
            nomi.append((f"altre {rest} fonti" if nomi else f"{rest} fonti per la biblioteca")
                        if rest > 1 else ("un'altra fonte" if nomi else altre[0]))
        if voci_frase:
            nomi.append(voci_frase)
        frase = " Posso ancora aggiungere " + _join(nomi) + "."
    first = (utili[0][1].split(",")[0] if utili else voci_frase or altre[0])
    if getattr(ctx, "installazioni", None) is not None and getattr(ctx.cfg, "online", True):
        frase += f" Dimmi quale installare, per esempio «scarica {first}»."
    else:
        frase += " Si installano da terminale: python -m calliope.stato --installa."
    return frase


def _panoramica(ctx, reg, level: str, cosa: str = "") -> str:
    caps = reg.tutte(fresche=True)
    manca = cosa == "manca"
    can = ["dirti l'ora e la data", "fare conti"]
    can += [c.definizione.sa_fare for c in caps if c.attiva and c.definizione.utente
            and c.definizione.sa_fare]
    # «Cosa manca?»: prima cosa non va e cosa si può aggiungere, senza l'elenco intero
    frase = "" if manca else f"Posso {_join(can)}."
    if level == "amministra":
        bad = [c for c in caps if not c.attiva]
        if bad:
            parts = [f"{c.definizione.breve}, " + (f"perché {_cap.a_voce(c.motivo)}" if c.motivo else
                                                    c.stato.replace("_", " ")) for c in bad[:3]]
            frase += " Non funzionano ancora: " + "; ".join(parts) + "."
            if len(bad) > 3:
                frase += f" E altre {len(bad) - 3}."
            frase += " Chiedimi di una per sapere come sistemarla."
        else:
            frase += " Funziona tutto quello che è installato."
    else:
        missing = [c.definizione.breve for c in caps if not c.attiva and c.definizione.utente]
        if missing:
            frase += (f" Qui non ci sono ancora: {_join(missing)}; per queste chiedi a chi "
                      f"amministra.")
        elif manca:
            frase += " Funziona tutto quello che è installato."
    frase += _aggiunte(ctx, reg, level, dettaglio=manca)
    return frase.strip()


def _una(ctx, reg, nome: str, level: str) -> str:
    c = reg.get(nome, fresca=True)
    d = _cap.DEFINIZIONI.get(nome)
    if d is None:
        return "Non so niente di questa capacità."
    if c is None:
        # Definita ma non controllata in questa installazione (04/10, 26B: «Perché non riesci
        # a cercare su Wikipedia?» → capacita=web → «Non so niente di questa capacità.»)
        non_ce = "non ci sono" if _plurale(d.titolo) else "non c'è"
        frase = f"{_cap1(d.titolo)} in questa installazione {non_ce}."
        if nome == "web" and reg.get("biblioteca") is not None:
            # Wikipedia è nella biblioteca offline: si dice anche lei, con il suo perché
            frase += " Wikipedia invece è nella biblioteca offline. " + _una(
                ctx, reg, "biblioteca", level)
        return frase
    verb = "funzionano" if _plurale(d.titolo) else "funziona"
    if c.attiva:
        frase = f"{_cap1(d.titolo)} {verb}."
        if level == "amministra" and c.motivo:
            frase += f" Nota: {_cap.a_voce(c.motivo)}."
            if c.prossimo_passo:
                frase += f" {_cap.a_voce(c.prossimo_passo)}"
        elif d.sa_fare and level != "amministra":
            frase += f" Puoi chiedermi di {d.sa_fare}." if not d.sa_fare.startswith(
                ("timer", "volume")) else f" Puoi chiedermi {d.sa_fare}."
        # Biblioteca e voci: cosa si può ancora aggiungere (se il passo non lo dice già)
        if nome in ("biblioteca", "voce") and level != "ospite" and not (
                level == "amministra" and c.prossimo_passo):
            frase += _aggiunte(ctx, reg, level, dettaglio=True, solo=nome)
        return frase
    if level != "amministra":
        return (f"{_cap1(d.titolo)} in questa installazione non {verb} ancora: chiedi a chi "
                f"amministra.")
    perche = _cap.a_voce(c.motivo) or {"da_configurare": "va configurata", "mancante": "manca qualcosa",
                          "guasta": "qualcosa si è rotto"}.get(c.stato, c.stato)
    frase = f"{_cap1(d.titolo)} non {verb} ancora: {perche}."
    if c.prossimo_passo:
        frase += f" {_cap.a_voce(c.prossimo_passo)}"
    return frase


# ─────────────────────────── aree, novità, chi sei (09/10) ───────────────────────────

def _tool_names(ctx, level: str):
    """I tool che chi parla può usare (None se il registro non c'è: prove a mano)."""
    reg = getattr(ctx, "strumenti", None)
    if reg is None or not hasattr(reg, "schemas_for"):
        return None
    try:
        return [s["function"]["name"] for s in reg.schemas_for(level)]
    except Exception:  # noqa: BLE001 — l'elenco serve solo a scegliere le aree
        return None


def _sullo_schermo(ctx) -> bool:
    """C'è uno schermo personale di chi parla, collegato adesso? Solo allora si dice «è
    sullo schermo» (la scheda è personale: altrove non arriva)."""
    hub = getattr(ctx, "schermi", None)
    if hub is None:
        return False
    try:
        from ..schermi.hub import destinatari
        from ..schermi.schede import PERSONALE
        m = hub.mittente(ctx)
        dest, _ = destinatari(PERSONALE, m, hub.collegati(), m.stanza)
        return bool(dest)
    except Exception:  # noqa: BLE001 — la scheda non deve rompere il tool
        return False


def _con_scheda(ctx, out: dict, titolo: str, testo: str, chiave: str) -> dict:
    """La scheda personale in Markdown, con «Scarica» (schede.documento_markdown)."""
    if getattr(ctx, "schermi", None) is None or not testo:
        return out
    try:
        from ..schermi import schede
        out["scheda"] = schede.documento_markdown(titolo, testo, chiave=chiave)
    except Exception as e:  # noqa: BLE001
        print(f"   [SCHERMI] scheda non costruita: {type(e).__name__}: {e}", flush=True)
    return out


def _azione(cosa: str) -> str:
    """«timer, promemoria…» e «volume, musica…» non sono verbi: «gestire timer…»."""
    return f"gestire {cosa}" if cosa.startswith(("timer", "volume")) else cosa


def _md_aree(aree: list[dict], level: str) -> str:
    righe = ["# Cosa so fare", ""]
    for a in aree:
        if not a["attiva"] and not (level == "amministra" and a["mancano"]):
            continue
        righe += [f"## {a['titolo']}", ""]
        righe += [f"- {_cap1(_azione(x))}" for x in a["sa_fare"]]
        if a["mancano"]:
            nomi = _join([_cap.DEFINIZIONI[n].breve for n in a["mancano"]])
            righe.append(f"- Non funziona ancora: {nomi}")
        righe.append("")
    righe.append("Chiedimi di un'area per il dettaglio, per esempio «cosa sai fare con la "
                 "casa?».")
    return "\n".join(righe)


def _sa_fare_aree(ctx, reg, level: str) -> dict:
    """«Cosa sai fare?»: solo le grandi aree (09/10, caso vero: l'elenco intero era così
    lungo che la persona l'ha interrotta); il dettaglio sulla scheda e con `area`."""
    aree = _cap.aree(reg, _tool_names(ctx, level))
    attive = [a for a in aree if a["attiva"]]
    frase = f"Posso aiutarti con {_join([a['nome'] for a in attive])}."
    if level == "amministra":
        bad = [c for c in reg.tutte(fresche=True) if not c.attiva]
        if bad:
            nomi = [c.definizione.breve for c in bad[:3]]
            if len(bad) > 3:
                nomi.append(f"altre {len(bad) - 3}")
            verb = "funziona" if len(nomi) == 1 else "funzionano"
            frase += f" Non {verb} ancora: {_join(nomi)}; il perché con «cosa manca?»."
    else:
        missing = [c.definizione.breve for c in reg.tutte(fresche=True)
                   if not c.attiva and c.definizione.utente]
        if missing:
            frase += (f" Qui non ci sono ancora: {_join(missing)}; per queste chiedi a chi "
                      f"amministra.")
    esempio = next((a["nome"] for a in attive if a["chiave"] in ("casa", "documenti", "pc")),
                   attive[0]["nome"] if attive else "")
    if esempio:
        frase += (f" Chiedimi di un'area per il dettaglio, per esempio «cosa sai fare con "
                  f"{esempio}?».")
    if _sullo_schermo(ctx):
        frase += " L'elenco completo è sullo schermo."
    return _con_scheda(ctx, _final(frase, aree=[a["chiave"] for a in attive]),
                       "Cosa so fare", _md_aree(aree, level), "calliope:sa_fare")


def _una_area(ctx, reg, chiave: str, level: str) -> dict:
    """«Cosa sai fare con la casa?»: le capacità di quell'area."""
    a = {x["chiave"]: x for x in _cap.aree(reg, _tool_names(ctx, level))}[chiave]
    pezzi = []
    if a["sa_fare"]:
        pezzi.append(f"{a['con']} posso {_join([_azione(x) for x in a['sa_fare']])}.")
    for nome in a["mancano"]:
        d = _cap.DEFINIZIONI[nome]
        if level == "amministra":
            pezzi.append(_una(ctx, reg, nome, level))
        elif d.utente:
            verb = "funzionano" if _plurale(d.titolo) else "funziona"
            pezzi.append(f"{_cap1(d.titolo)} qui non {verb} ancora: chiedi a chi amministra.")
    if not pezzi:
        pezzi.append(f"Con {a['nome']} in questa installazione non posso aiutarti.")
    return _final(" ".join(pezzi), area=chiave)


def _novita(ctx, periodo: str) -> dict:
    from .. import novita
    r = novita.novita(periodo)
    frase = r["frase"]
    if r["fuori"] and _sullo_schermo(ctx):
        frase += " Il resto è sullo schermo."
    return _con_scheda(ctx, _final(frase), "Novità di Calliope", r["markdown"],
                       "calliope:novita")


def _calliope_stato(ctx: ToolContext, capacita: str = "", domanda: str = "",
                    cosa: str = "", area: str = "", periodo: str = "") -> dict:
    level = _level(ctx)
    cosa = str(cosa or "").strip().lower()
    if cosa == "macchina":
        # «Su che hardware giri?» (04/10): la macchina e i modelli, non le capacità. Niente
        # dati sensibili (calliope/macchina.py), quindi per tutti i livelli
        from ..macchina import descrivi
        return _final(descrivi(ctx.cfg, getattr(ctx, "lavori", None)))
    if not cosa and str(periodo or "").strip():
        # Solo il periodo («cosa è cambiato da ieri?» → periodo=da_ieri, 09/10 col modello
        # locale): il periodo c'è solo per le novità, la forma della scelta si completa qui
        note_rule(ctx, "stato_periodo_novita")
        cosa = "novita"
    if cosa == "novita":
        # «Cosa c'è di nuovo?», «che versione sei?» (09/10): CHANGELOG.md della versione
        # installata (calliope/novita.py). Il registro è pubblico: per tutti i livelli
        return _novita(ctx, str(periodo or "").strip().lower())
    reg = _registro(ctx)
    if cosa == "chi_sei":
        # «Chi sei?», «dove giri?», «chi ti ha fatta?» (09/10): fatti veri, niente host
        from ..novita import chi_sei
        return _final(chi_sei(ctx.cfg, getattr(ctx, "lavori", None), reg))
    nome = str(capacita or "").strip().lower()
    area = str(area or "").strip().lower()
    if level == "ospite":
        frase = _ospite(ctx, reg)
    elif area in _cap.AREE and cosa != "manca":
        return _una_area(ctx, reg, area, level)
    elif nome in _cap.DEFINIZIONI:
        frase = _una(ctx, reg, nome, level)
    elif cosa != "manca":
        return _sa_fare_aree(ctx, reg, level)
    else:
        frase = _panoramica(ctx, reg, level, cosa)
    return _final(frase)


# ─────────────────────────── installazioni ───────────────────────────

def _persona(ctx):
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _chi_amministra(ctx, rigido: bool, tool: str = "", args: dict | None = None
                    ) -> tuple[object | None, object]:
    """(profilo, "") se chi parla amministra ed è riconosciuto dalla voce in questo turno;
    altrimenti (None, frase di rifiuto) o (None, risultato con la frase di sfida). Il «sì»
    breve di chi amministra lo fa passare il registro, solo per il tool proposto
    (conferme.py); a chi amministra con una frase che non basta si chiede la frase di sfida,
    mai «chiedi a chi amministra» (04/10)."""
    how = getattr(ctx.speaker_ctx, "identified_by", None)
    if (tool and e_admin(ctx) and how in ("breve", "conversazione")
            and not (how == "breve" and not rigido and admin_confermato(ctx))):
        return None, chiedi_conferma(ctx, tool, args, "installare qualcosa")
    level = _level(ctx)
    if level == "ospite":
        return None, "Non posso: installare qualcosa lo può chiedere solo chi amministra."
    if level != "amministra":
        return None, ("Solo chi amministra può installare o annullare qualcosa: chiedi a chi "
                      "amministra.")
    how = getattr(ctx.speaker_ctx, "identified_by", None)
    if how != "voce":     # dal 03/10 anche il «sì»: una frase breve non vale come chi amministra
        return None, ("In questa frase non ti ho riconosciuto bene dalla voce: ripeti la "
                      "richiesta con una frase un po' più lunga.")
    prof = _persona(ctx)
    if prof is None:
        return None, "Non so chi sei: installare qualcosa lo può chiedere solo chi amministra."
    return prof, ""


def _rifiuto(ctx, frase, regola: str) -> dict:
    if isinstance(frase, dict):
        return frase                    # la frase di sfida, già pronta (conferme.py)
    note_rule(ctx, regola)
    return _final(frase, ok=False, fatto=NIENTE)


def _non_disponibili(ctx):
    inst = getattr(ctx, "installazioni", None)
    if inst is None:
        return None, _final("Le installazioni sono spente in questa configurazione.",
                            ok=False, fatto=NIENTE)
    return inst, None


def _installa_proponi(ctx: ToolContext, azione: str = "") -> dict:
    inst, err = _non_disponibili(ctx)
    if err:
        return err
    # Scritta da uno schermo personale: le installazioni vogliono la voce (03/10)
    voce = serve_la_voce(ctx, "installa_proponi", {"azione": azione}, "installare qualcosa")
    if voce is not None:
        return voce
    prof, why = _chi_amministra(ctx, rigido=True, tool="installa_proponi",
                                args={"azione": azione})
    if prof is None:
        return _rifiuto(ctx, why, "installa_permesso")
    azione = str(azione or "").strip()
    res = inst.proponi(azione, prof.id, int(getattr(ctx, "turno", 0) or 0))
    if not res["ok"]:
        return _final(res["frase"], ok=False, fatto=NIENTE, codice=res["codice"])
    a = inst.catalogo[azione]
    domanda = res["frase"].rsplit(". ", 1)[-1] if res["frase"].endswith("?") else "Procedo?"
    return _final(res["frase"], fatto="proposta: NIENTE è stato ancora scaricato",
                  codice="proposta",
                  in_sospeso={"domanda": domanda, "cosa": f"installare {a.titolo}",
                              "tool": "installa_avvia", "argomenti": {"azione": azione}})


def _installa_avvia(ctx: ToolContext, azione: str = "") -> dict:
    inst, err = _non_disponibili(ctx)
    if err:
        return err
    prof, why = _chi_amministra(ctx, rigido=False, tool="installa_avvia",
                                args={"azione": azione})
    if prof is None:
        return _rifiuto(ctx, why, "installa_permesso")
    res = inst.avvia(str(azione or "").strip(), prof.id, int(getattr(ctx, "turno", 0) or 0),
                     chi_nome=getattr(prof, "name", None))
    if res["codice"] == "senza_offerta":
        return _rifiuto(ctx, res["frase"], "installa_senza_offerta")
    if not res["ok"]:
        return _final(res["frase"], ok=False, fatto=NIENTE, codice=res["codice"])
    return _final(res["frase"], fatto="avviato in secondo piano", codice=res["codice"])


def _installa_gestisci(ctx: ToolContext, azione: str = "stato") -> dict:
    inst, err = _non_disponibili(ctx)
    if err:
        return err
    if str(azione or "").strip().lower() == "annulla":
        voce = serve_la_voce(ctx, "installa_gestisci", {"azione": "annulla"},
                             "annullare un'installazione")
        if voce is not None:
            return voce
        prof, why = _chi_amministra(ctx, rigido=False, tool="installa_gestisci",
                                    args={"azione": "annulla"})
        if prof is None:
            return _rifiuto(ctx, why, "installa_permesso")
        res = inst.annulla()
        return _final(res["frase"], ok=res["ok"])
    return _final(inst.stato()["frase"])


SPECS = [
    ToolSpec(
        name="calliope_stato",
        # Accorciata il 03/10 (analisi del comportamento: prefisso −14 % con le altre): la
        # capacità è nell'enum, qui non si ripete. 09/10: aree, novità e chi sei
        description=("Dice cosa sai fare, cosa manca, perché qualcosa non funziona, e chi sei. "
                     "cosa: sa_fare per «cosa sai fare?»; con area per «cosa sai fare con la "
                     "casa?», «cosa puoi fare per i promemoria?» (sempre, mai a memoria); manca per «cosa manca?», «funziona tutto?», «cosa si può "
                     "aggiungere?»; macchina per «su che hardware giri?», «che modello usi?»; "
                     "novita per «cosa c'è di nuovo?», «che versione sei?», «quando ti hanno "
                     "aggiornata?» (periodo per «da ieri», «questa settimana»); chi_sei per "
                     "«chi sei?», «dove gira il tuo codice?», «chi ti ha fatta?». capacita: "
                     "quella chiesta, per «perché non riesci a…?» (Wikipedia = biblioteca, "
                     "offline; web = internet). Nella risposta usa la frase del risultato."),
        parameters={"type": "object",
                    "properties": {"capacita": {"type": "string",
                                                "enum": ["tutte"] + list(_cap.DEFINIZIONI)},
                                   "cosa": {"type": "string",
                                            "enum": ["sa_fare", "manca", "macchina", "novita",
                                                     "chi_sei"]},
                                   "area": {"type": "string", "enum": list(_cap.AREE)},
                                   "periodo": {"type": "string",
                                               "enum": ["ultimo_aggiornamento", "oggi",
                                                        "da_ieri", "settimana", "mese"]}},
                    "required": []},
        func=_calliope_stato, risk="lettura", levels=ALL),
    ToolSpec(
        name="installa_proponi",
        description=("Propone di scaricare e installare un componente dal catalogo "
                     "(biblioteca e sue fonti, voci, modelli, pulizia dei file vecchi): dice "
                     "peso e tempo e chiede conferma, non scarica niente. Per «scarica la "
                     "biblioteca», «installa Wikiquote», «aggiorna la biblioteca», «scarica "
                     "la voce di Paola», «pulisci i file vecchi». biblioteca = i file che "
                     "mancano; biblioteca_ragazzi = Vikidia; biblioteca_dizionario = "
                     "Wikizionario."),
        parameters={"type": "object",
                    "properties": {"azione": {"type": "string", "enum": list(DESCRIZIONI)}},
                    "required": ["azione"]},
        # Internet (principio 5): senza rete (Config.online false) i tool spariscono
        func=_installa_proponi, risk="lettura", levels=FAMILY, requires_internet=True),
    ToolSpec(
        name="installa_avvia",
        # Senza enum (03/10): il codice accetta comunque solo l'azione proposta
        description=("Avvia l'installazione appena proposta con installa_proponi, solo dopo il "
                     "sì di chi parla; azione = la stessa della proposta."),
        parameters={"type": "object",
                    "properties": {"azione": {"type": "string"}},
                    "required": ["azione"]},
        func=_installa_avvia, risk="sensibile", levels=ADMIN, requires_internet=True),
    ToolSpec(
        name="installa_gestisci",
        description=("Per un'installazione in corso: azione=stato per «a che punto è il "
                     "download?», azione=annulla per «annulla il download»."),
        parameters={"type": "object",
                    "properties": {"azione": {"type": "string", "enum": ["stato", "annulla"]}},
                    "required": ["azione"]},
        func=_installa_gestisci, risk="azione", levels=FAMILY),
]


def stato_specs(installa: bool = True) -> list[ToolSpec]:
    """calliope_stato sempre; i tool d'installazione se `installa`."""
    return SPECS if installa else SPECS[:1]
