"""
I tool casa_*: la casa comandata e letta a voce (calliope/casa/).

- casa_comando(comando): il modello riscrive la richiesta in una frase breve nella forma
  che l'agente integrato di Home Assistant capisce («accendi la luce della cucina»).
  L'adattatore la interpreta senza eseguirla, le regole di Calliope (casa/regole.py)
  decidono, poi si esegue. La risposta di HA è la `risposta_finale`: si dice così com'è,
  senza un'altra passata del modello (~0,3–0,5 s in meno). Se HA non capisce, il modello
  riceve i nomi e le stanze più vicini e riprova una volta.
  Se HA capisce ma non trova i dispositivi (08/10, la luce «Soggiorno» nell'area Ingresso),
  Calliope cerca tra le esposte quella detta e riprova con il suo nome (casa/nomi.py).
- casa_stato(cosa): letture locali dagli stati già in memoria (nessuna richiesta a HA),
  con una frase pronta. Gli intent di lettura di HA non bastano: la temperatura di una
  stanza la leggono solo dai termostati, e «cosa c'è acceso?» non lo capiscono.
- casa_integrazione: a che punto è il collegamento e il prossimo passo; esiste anche
  quando la casa non è collegata (è proprio il caso in cui serve).

Permessi: comandare e leggere = familiare o chi amministra; l'ospite niente, salvo i
domini di `casa_ospite_domini`. La diagnosi con i dettagli solo a chi amministra. I
rifiuti dicono «NON è stata eseguita», come gli altri tool.
"""

import re

from ..casa import CasaNonRisponde, diagnose
from ..casa.guida import frase_familiare, guida_scritta
from ..casa import nomi
from ..casa.parole import categorie, descrivi, norm, riscrivi, suggerimenti, trova_per_nome
from ..casa.regole import FRASI, Regole
from .spec import ToolContext, ToolSpec, note_rule
from ..testi import ALL, FAMILY, NIENTE


_GIU = "La casa non risponde: Home Assistant sembra spento o non raggiungibile. Riprova tra poco."

# Una domanda (non un ordine): «cosa c'è acceso?», «com'è la temperatura?»
_DOMANDA = re.compile(r"\?|^\W*(cosa|che|quale|quali|quanto|quanti|quante|com['e ]|come|"
                      r"c'è|ci sono|dimmi|sai|è|sono)\b", re.I)
# Parole dei domini delicati in un ordine che HA non ha capito
_DELICATE = re.compile(r"\b(allarm\w*|antifurto|serratur\w*|cancell\w*|garage|"
                       r"(s)?blocca\w*\s+(la\s+)?porta|chiav\w*)\b", re.I)


def _level(ctx: ToolContext) -> str:
    return getattr(ctx.speaker_ctx, "current_level", "ospite") or "ospite"


def _final(text: str, **extra) -> dict:
    return {**extra, "conferma": text, "risposta_finale": text}


def _giu(e: Exception) -> dict:
    print(f"   [CASA] non risponde: {e}", flush=True)
    return _final(_GIU, ok=False, fatto=NIENTE, errore="la casa non risponde")


def _ospite() -> dict:
    # La stessa frase pronta del registro (ToolRegistry.call): gentile, e niente seconda
    # passata del modello
    from .registry import REFUSAL
    return _final(REFUSAL["ospite"], ok=False, fatto=NIENTE,
                  motivo="chi sta parlando non ha il permesso (voce non riconosciuta)")


def _pulisci(testo: str) -> str:
    """Il nome di Calliope e la punteggiatura finale non servono a Home Assistant."""
    t = re.sub(r"^\W*calliope\W+", "", str(testo or "").strip(), flags=re.I)
    return t.strip(" .!;:,\"'«»")


def _tentativo(ctx: ToolContext, tool: str) -> int:
    """Quante volte questo tool non ha capito nella stessa frase dell'utente."""
    key = (tool, getattr(ctx, "user_text", ""))
    seen = getattr(ctx, "_casa_falliti", None)
    if not isinstance(seen, dict) or seen.get("_frase") != key[1]:
        seen = {"_frase": key[1]}
        ctx._casa_falliti = seen
    seen[tool] = seen.get(tool, 0) + 1
    return seen[tool]


def _non_trovato(ctx: ToolContext, tool: str, testo: str, entita, perche: str) -> dict:
    nomi, stanze = suggerimenti(testo, entita)
    if _tentativo(ctx, tool) >= 2:
        some = ", ".join(nomi[:3])
        return _final(f"Non trovo quel dispositivo. In casa ci sono, per esempio, {some}: "
                      f"dimmi quale." if some else "Non trovo quel dispositivo in casa.",
                      ok=False, fatto=NIENTE, errore=perche)
    forme = ("«accendi la luce della cucina», «spegni le luci in sala», «abbassa le "
             "tapparelle in camera», «imposta il termostato a 21 gradi»"
             if tool == "casa_comando" else "«temperatura in camera», «luce cucina»")
    return {"ok": False, "fatto": NIENTE, "errore": perche, "nomi_vicini": nomi,
            "stanze": stanze,
            "cosa_fare": (f"Richiama {tool} UNA volta con una frase breve come {forme}, "
                          f"usando un nome di nomi_vicini o una stanza di stanze. Se nessuno "
                          f"corrisponde, chiedi a chi parla quale dispositivo intende.")}


def _riferimento(ids, entita, comando: str) -> dict | None:
    """L'ultimo dispositivo comandato o letto, per «accendila», «spegnilo» nei turni dopo
    (Brain.set_reference, 01/10). Il nome come lo conosce la casa, con la stanza se è una."""
    by_id = {e.id: e for e in entita}
    ents = [by_id[i] for i in ids if i in by_id]
    if not ents:
        return None
    names = list(dict.fromkeys(e.nome for e in ents if e.nome))
    cosa = ", ".join(names[:3]) + (f" e altri {len(names) - 3}" if len(names) > 3 else "")
    areas = {e.area for e in ents if e.area}
    if len(areas) == 1 and len(names) > 1:
        cosa = f"{cosa} (in {next(iter(areas)).lower()})"
    # Come chiamarlo in un comando nuovo: il nome se è uno solo, altrimenti l'oggetto del
    # comando detto («spegni le luci in cucina» → «le luci in cucina»)
    parts = str(comando or "").split(" ", 1)
    nome = names[0] if len(names) == 1 else (parts[1] if len(parts) == 2 else cosa)
    return {"cosa": cosa, "nome": nome, "comando": comando}


def _aree(be) -> dict:
    try:
        return be.aree()
    except Exception:  # noqa: BLE001
        return {}


_ARTICOLO = re.compile(r"^(il|lo|la|i|gli|le|l['’])\s*", re.I)


def _per_nome(ctx, be, rules, level, testo, entita, esito, autorizza):
    """HA ha capito il comando ma non trova i dispositivi: si cerca tra le esposte che chi
    parla vede quella detta (casa/nomi.py). (risultato finale | None, esito nuovo | None,
    comando riprovato). Un esito nuovo è solo un rifiuto delle regole sulla riprova (ospite,
    minore, delicata): lo dice il flusso normale."""
    interp = esito.interpretazione
    if interp is not None and interp.capito and interp.azione != "comando":
        return None, None, None
    visible = [e for e in entita if rules.visibile(e, level)]
    aree = _aree(be)
    c = nomi.candidate(testo, visible, aree,
                       lambda e: not rules.delicata(e) and not rules.da_elenco(e))
    if c is None or not c["trovate"]:
        return None, None, None          # la frase d'errore di HA, già giusta
    note_rule(ctx, "casa_nome_entita")
    trovate = c["trovate"]
    if len(trovate) > 1:
        print(f"   [CASA] «{testo}»: {esito.codice}, più candidate "
              f"{[e.id for e in trovate]}: chiedo quale", flush=True)
        return _final(nomi.frase_quale(trovate), ok=False, fatto=NIENTE, errore=esito.codice,
                      candidate=[e.nome for e in trovate]), None, None
    e = trovate[0]
    ids = set(c["stesso_nome"].get(norm(e.nome)) or [e.id])
    alt = nomi.comando_esatto(c["verbo"], e)

    def solo_lei(i):
        # Mai allargare: la riprova deve toccare solo la candidata (o i suoi omonimi)
        if i.azione == "comando" and (not i.bersagli or not set(i.bersagli) <= ids):
            return "fuori_candidata"
        return autorizza(i)

    again = be.comando(alt, solo_lei)
    interp2 = again.interpretazione
    print(f"   [CASA] «{testo}»: {esito.codice}, riprovo con «{alt}» → "
          f"{interp2.intento if interp2 else '?'} {interp2.bersagli if interp2 else []}: "
          f"{again.tipo} {again.codice}", flush=True)
    if again.tipo == "fatto" and again.ok:
        frase = nomi.frase_fatto(c["verbo"], e, c["stanza"], aree)
        detto = _ARTICOLO.sub("", re.sub(r"^\W*\w+\s+", "", testo).strip())
        consiglio = nomi.segna_consiglio(e, detto, c["stanza"], aree)
        if consiglio:
            print(f"   [CASA] consiglio per chi amministra: {consiglio}", flush=True)
            if level == "amministra":
                frase += " " + consiglio
                nomi.segna_detto(consiglio)
        ref = _riferimento(again.bersagli or [e.id], entita, alt)
        return _final(frase, ok=True, fatto="eseguito", **({"riferimento": ref} if ref
                                                            else {})), None, None
    if again.tipo == "rifiuto" and again.codice != "fuori_candidata":
        return None, again, alt
    return None, None, None


# ─────────────────────────── casa_comando ───────────────────────────

def _casa_comando(ctx: ToolContext, comando: str = "") -> dict:
    be = getattr(ctx, "casa", None)
    if be is None:
        return {"ok": False, "fatto": NIENTE, "errore": "la casa non è collegata",
                "cosa_fare": "chiama casa_integrazione"}
    level = _level(ctx)
    testo = _pulisci(comando) or _pulisci(getattr(ctx, "user_text", ""))
    if not testo:
        return {"ok": False, "fatto": NIENTE, "errore": "manca il comando",
                "cosa_fare": "chiedi cosa fare in casa"}
    rules = Regole(ctx.cfg)
    seen: dict = {}

    from .. import minori
    prof = minori.profilo(ctx)

    def autorizza(interp):
        seen.update({e.id: e for e in be.entita()})
        motivo = rules.controlla(interp, seen, level)
        # Un minore (05/10): solo ciò che il suo preset permette (luci della sua stanza, luci
        # e tapparelle, niente clima…); le letture restano
        if motivo is None and interp.azione == "comando" and prof is not None and any(
                not minori.casa_consentita(prof, seen[eid]) for eid in interp.bersagli
                if eid in seen):
            return "minore"
        return motivo

    try:
        esito = be.comando(testo, autorizza)
        entita = list(seen.values()) or be.entita()
        # Non capito: un tentativo locale con il nome esatto o la forma delle percentuali
        # («spegni la presa della TV» → «spegni la presa TV»), prima di tornare al modello
        if esito.codice == "non_capito":
            for alt in riscrivi(testo, [e for e in entita if rules.visibile(e, level)])[:1]:
                print(f"   [CASA] «{testo}» non capito, riprovo con «{alt}»", flush=True)
                note_rule(ctx, "casa_riscrittura")
                again = be.comando(alt, autorizza)
                if again.codice != "non_capito":
                    esito, testo = again, alt
        # Capito ma senza dispositivi (08/10, «spegni la luce in soggiorno» con la luce
        # «Soggiorno» nell'area Ingresso): si cerca tra le esposte quella detta
        if esito.tipo == "errore" and esito.codice in ("no_valid_targets", "no_intent_match"):
            fixed, again, alt = _per_nome(ctx, be, rules, level, testo, entita, esito,
                                          autorizza)
            if fixed is not None:
                return fixed
            if again is not None:
                esito, testo = again, alt
    except CasaNonRisponde as e:
        return _giu(e)
    interp = esito.interpretazione
    tempi = " + ".join(f"{v:.2f}".replace(".", ",") for v in esito.tempi.values())
    print(f"   [CASA] «{testo}» → {interp.intento if interp else '?'} "
          f"{interp.bersagli if interp else []}: {esito.tipo} {esito.codice} ({tempi} s)",
          flush=True)

    if esito.tipo in ("fatto", "risposta"):
        if esito.ok:
            ref = _riferimento(esito.bersagli or (interp.bersagli if interp else []),
                               entita, testo)
            return _final(esito.frase, ok=True, fatto="eseguito" if esito.tipo == "fatto"
                          else "risposta della casa", **({"riferimento": ref} if ref else {}))
        return _final(esito.frase or "Non ci sono riuscita.", ok=False, fatto=NIENTE,
                      errore="la casa non ha eseguito il comando", non_riusciti=esito.falliti)
    if esito.tipo == "rifiuto":
        if esito.codice == "ospite":
            return _ospite()
        if esito.codice == "minore":
            note_rule(ctx, "minore_casa")
            return _final(minori.FRASI["casa"], ok=False, fatto=NIENTE, motivo="minore")
        if esito.codice == "non_casa":
            return {"ok": False, "fatto": NIENTE,
                    "errore": "non è un comando per i dispositivi della casa",
                    "cosa_fare": "usa il tool adatto (ora_attuale, timer_imposta, "
                                 "lista_aggiungi, pc_*…) o rispondi tu"}
        return _final(FRASI.get(esito.codice) or "Questo non lo posso fare.", ok=False,
                      fatto=NIENTE, motivo=esito.codice)
    # Errori
    if esito.codice == "non_capito":
        # «Disattiva l'allarme», «apri il cancello» non capiti da HA: la risposta è comunque
        # quella dei domini delicati, non «non trovo il dispositivo»
        if _DELICATE.search(testo) or any(rules.delicata(e) for e in trova_per_nome(testo, entita)):
            note_rule(ctx, "casa_delicata")
            return _final(FRASI["delicata"], ok=False, fatto=NIENTE, motivo="delicata")
        # Una domanda finita qui per sbaglio («cosa c'è acceso?») si prova a leggere
        if _DOMANDA.search(str(comando or "")):
            visible = [e for e in entita if rules.visibile(e, level)]
            res = descrivi(testo, visible, _aree(be))
            if res.get("ok"):
                note_rule(ctx, "casa_domanda_letta")
                return _final(res["frase"], ok=True, fatto="letto dagli stati")
        return _non_trovato(ctx, "casa_comando", testo, entita,
                            f"Home Assistant non ha capito «{testo}»")
    if esito.codice == "lento":
        return _final("Home Assistant è lento a rispondere: il comando potrebbe essere partito "
                      "lo stesso. Controlla tra un attimo.", ok=False,
                      fatto="NON confermato: forse eseguito", errore="tempo scaduto")
    if esito.codice in ("agente_assente", "verifica_assente"):
        return _final("Non posso comandare la casa: in Home Assistant manca qualcosa. Chiedimi "
                      "come va il collegamento con la casa.", ok=False, fatto=NIENTE,
                      errore=esito.codice)
    if esito.frase:
        return _final(esito.frase, ok=False, fatto=NIENTE, errore=esito.codice)
    return _non_trovato(ctx, "casa_comando", testo, entita,
                        f"la casa ha risposto con un errore ({esito.codice})")


# ─────────────────────────── casa_stato ───────────────────────────

def _casa_stato(ctx: ToolContext, cosa: str = "") -> dict:
    be = getattr(ctx, "casa", None)
    if be is None:
        return {"ok": False, "errore": "la casa non è collegata",
                "cosa_fare": "chiama casa_integrazione"}
    level = _level(ctx)
    rules = Regole(ctx.cfg)
    try:
        entita = be.entita()
    except CasaNonRisponde as e:
        return _giu(e)
    visible = [e for e in entita if rules.visibile(e, level)]
    if not visible:
        return _ospite() if level == "ospite" else _final(
            "In casa non vedo nessun dispositivo esposto.", ok=False,
            errore="nessuna entità esposta")
    aree = _aree(be)
    detto = _pulisci(getattr(ctx, "user_text", ""))
    tries = [t for t in (_pulisci(cosa), detto) if t] or [""]
    # Se il modello ha perso il tipo di cosa chiesta («quali luci sono accese?» → cosa=«cosa
    # c'è acceso», 01/10: luci e termostati mescolati), prima la frase detta
    if detto and set(categorie(detto)) - set(categorie(tries[0])):
        tries = [detto] + [t for t in tries if t != detto]
    res = None
    for t in dict.fromkeys(tries):
        res = descrivi(t, visible, aree)
        if res.get("ok"):
            break
    if res and res.get("ok"):
        print(f"   [CASA] stato «{tries[0]}» → {len(res['entita'])} entità", flush=True)
        # Una lettura di pochi dispositivi («la luce dello studio è accesa?») è anche il
        # riferimento di «spegnila» subito dopo
        ref = _riferimento(res["entita"], visible, tries[0]) if len(res["entita"]) <= 3 else None
        out = _final(res["frase"], ok=True, **({"riferimento": ref} if ref else {}))
        # Sullo schermo i dispositivi letti, con lo stato (scheda «casa»: solo familiari)
        if getattr(ctx, "schermi", None) is not None:
            try:
                from ..schermi import schede
                by_id = {e.id: e for e in visible}
                ents = [by_id[i] for i in res["entita"] if i in by_id]
                if ents:
                    out["scheda"] = schede.casa(ents)
            except Exception as e:  # noqa: BLE001 — la scheda non cambia la risposta
                print(f"   [SCHERMI] scheda della casa non costruita: {e}", flush=True)
        return out
    return _non_trovato(ctx, "casa_stato", tries[0], visible, (res or {}).get("motivo", ""))


# ─────────────────────────── meteo_leggi ───────────────────────────

def _meteo_leggi(ctx: ToolContext, quando: str = "") -> dict:
    """Il meteo di casa dall'entità weather esposta in Home Assistant (casa/meteo.py, 09/10).
    Senza entità esposta: la città di casa (luogo.py) o la domanda «dove si trova la casa?»,
    detto al modello in `cosa_fare`."""
    from .. import luogo
    from ..casa.meteo import MeteoCasa
    be = getattr(ctx, "casa", None)
    citta = luogo.citta_casa(ctx.cfg)
    altrimenti = (f"Home Assistant non ha il meteo di casa: chiama subito l'estensione del "
                  f"meteo, se c'è, altrimenti web_cerca con la domanda «meteo {citta}», senza "
                  f"chiedere niente a chi parla (la casa è a {citta})." if citta else
                  "Home Assistant non ha il meteo di casa e non sai dove si trova la casa: "
                  "chiedi a chi parla in che città è.")
    if be is None:
        return {"ok": False, "errore": "la casa non è collegata", "cosa_fare": altrimenti}
    # Uno per adattatore (la cache delle previsioni vale tra un turno e l'altro)
    meteo = getattr(be, "_meteo_casa", None)
    if meteo is None:
        meteo = MeteoCasa(be)
        try:
            be._meteo_casa = meteo
        except AttributeError:
            pass
    try:
        res = meteo.leggi(quando)
    except CasaNonRisponde as e:
        print(f"   [CASA] meteo: Home Assistant non risponde ({e})", flush=True)
        return {"ok": False, "errore": "Home Assistant non risponde", "cosa_fare": altrimenti}
    if not res.get("ok"):
        print(f"   [CASA] meteo «{quando}»: {res.get('errore')}", flush=True)
        # Con l'entità meteo che risponde manca solo quel giorno: niente internet per casa
        senza_entita = res.get("entita") is False
        return {**{k: v for k, v in res.items() if k != "entita"}, "cosa_fare": (
            altrimenti if senza_entita else
            "Di' in breve che per quel giorno Home Assistant non ha previsioni"
            + (", e il meteo di adesso." if "frase_adesso" in res else "."))}
    print(f"   [CASA] meteo «{quando or 'adesso'}» → {res['frase']}", flush=True)
    return {**res, "cosa_fare": ("È il meteo di casa. Rispondi alla domanda in 1–2 frasi da "
                                 "questi dati, senza nominare Home Assistant.")}


# ─────────────────────────── citta_casa_salva ───────────────────────────

def _citta_casa_salva(ctx: ToolContext, citta: str = "", conferma=False) -> dict:
    """La città di casa detta a voce (luogo.py, 09/10). Senza `conferma`: a chi amministra
    propone di ricordarla (azione in sospeso, il «sì» lo decide il modello); con `conferma`
    la salva in luogo.json. Familiari e ospiti non la salvano. Mai calliope.yaml."""
    from .. import luogo
    c = luogo.valida(citta)
    if not c:
        return {"ok": False, "fatto": NIENTE, "errore": "manca la città, o non sembra una città",
                "cosa_fare": "chiedi in che città si trova la casa"}
    gia = luogo.da_config(ctx.cfg)
    if gia:
        same = norm(gia) == norm(c)
        return {"ok": same, "fatto": NIENTE, "citta_di_casa": gia,
                "nota": ("è già la città di casa" if same else
                         f"la città di casa è {gia}, scritta nella configurazione: si cambia "
                         f"lì, non a voce"),
                "cosa_fare": "non proporre di ricordarla"}
    per_ora = (f"Rispondi alla richiesta di prima per {c}: per il meteo chiama web_cerca (o "
               f"l'estensione del meteo, se c'è) con {c}, senza inventare.")
    if _level(ctx) != "amministra":
        note_rule(ctx, "citta_casa_solo_admin")
        return {"ok": False, "fatto": NIENTE,
                "nota": "la città di casa la salva solo chi amministra: vale solo per questa "
                        "richiesta",
                "cosa_fare": "Non proporre di ricordarla. " + per_ora}
    if luogo.salvata(ctx.cfg) and norm(luogo.salvata(ctx.cfg)) == norm(c):
        return {"ok": True, "fatto": NIENTE, "nota": "è già la città di casa",
                "cosa_fare": "non proporre di ricordarla"}
    # Si salva solo dopo il «sì» alla proposta (la proposta in sospeso è di questo tool): una
    # conferma alla prima chiamata vale come proposta (09/10, col 4B: «A Borgoverde.» →
    # conferma=true subito). Regola `citta_casa_proposta`
    confermata = str(conferma).strip().lower() in ("true", "1", "sì", "si", "yes")
    if confermata and getattr(ctx, "tool_in_sospeso", None) != "citta_casa_salva":
        note_rule(ctx, "citta_casa_proposta")
        confermata = False
    if not confermata:
        domanda = f"Vuoi che mi ricordi che la casa è a {c}?"
        return {"ok": True, "fatto": "NIENTE ancora: è una proposta, non è salvata",
                "cosa_fare": f"{per_ora} Poi chiudi la risposta con questa domanda: "
                             f"«{domanda}»",
                "in_sospeso": {"domanda": domanda, "cosa": f"ricordare che la casa è a {c}",
                               "tool": "citta_casa_salva",
                               "argomenti": {"citta": c, "conferma": True}}}
    chi = getattr(getattr(ctx, "speaker_ctx", None), "current_speaker", None)
    try:
        salvata = luogo.salva(ctx.cfg, c, chi)
    except (ValueError, OSError) as e:
        print(f"   [LUOGO] città di casa non salvata: {e}", flush=True)
        return _final("Non sono riuscita a salvarla: vale solo per adesso.", ok=False,
                      fatto=NIENTE, errore=str(e))
    print(f"   [LUOGO] città di casa salvata a voce: {salvata}" + (f" (da {chi})" if chi else ""),
          flush=True)
    return _final(f"Fatto: da adesso so che la casa è a {salvata}.", ok=True,
                  fatto="salvata", citta=salvata)


def meteo_spec() -> ToolSpec:
    """meteo_leggi: per tutti, anche gli ospiti (il meteo non è un dato della famiglia). Si
    registra solo con un'entità meteo esposta (allinea_meteo): col 4B, presente ma non
    nominato dal prompt, veniva chiamato lo stesso e dopo il suo «non c'è» non cercava più
    su internet (09/10)."""
    return ToolSpec(
        name="meteo_leggi",
        description=("Il meteo di casa (dove sei) da Home Assistant: cielo, temperatura, "
                     "umidità, vento e previsioni. Solo quando chiedono il meteo senza "
                     "nominare un altro posto; non per la temperatura delle stanze "
                     "(casa_stato). quando: «adesso» (o vuoto), «oggi», «stasera», «domani», "
                     "«domani mattina», «dopodomani», un giorno della settimana, «weekend», "
                     "«prossimi giorni»."),
        parameters={"type": "object",
                    "properties": {"quando": {"type": "string"}}, "required": []},
        func=_meteo_leggi, risk="lettura", levels=ALL)


def allinea_meteo(reg, be) -> bool:
    """meteo_leggi c'è se e solo se un'entità meteo è esposta in Home Assistant (l'elenco
    dell'ultimo caricamento: non aspetta HA). Lo chiama Brain prima di costruire il prompt:
    tool e prompt cambiano insieme, di rado (il prefisso nuovo si scalda). True se è
    cambiato qualcosa."""
    try:
        esposta = be is not None and bool(be.meteo_esposte())
    except Exception:  # noqa: BLE001 — un adattatore senza meteo
        esposta = False
    presente = reg.get("meteo_leggi") is not None
    if esposta and not presente:
        reg.register(meteo_spec())
        return True
    if presente and not esposta:
        reg.unregister("meteo_leggi")
        return True
    return False


def luogo_spec() -> ToolSpec:
    """citta_casa_salva: c'è sempre (anche senza Home Assistant), uguale per tutti i livelli;
    chi non amministra riceve «vale solo per questa richiesta»."""
    return ToolSpec(
        name="citta_casa_salva",
        description=("Ricorda in che città si trova la casa, per il meteo e ciò che dipende "
                     "dal luogo. Chiamalo quando chi parla ti dice dove si trova la casa, dopo "
                     "che gliel'hai chiesto: citta = la città detta; conferma=true solo dopo "
                     "il suo «sì» alla tua domanda «vuoi che mi ricordi…»."),
        parameters={"type": "object",
                    "properties": {"citta": {"type": "string"},
                                   "conferma": {"type": "boolean"}},
                    "required": ["citta"]},
        func=_citta_casa_salva, risk="azione", levels=ALL)


# ─────────────────────────── casa_integrazione ───────────────────────────

def _esempio(be) -> str:
    try:
        ents = be.entita()
    except Exception:  # noqa: BLE001
        return ""
    for e in ents:
        if e.dominio == "light" and e.area:
            return f"accendi le luci in {e.area.lower()}"
    for e in ents:
        if e.dominio == "sensor" and e.classe == "temperature" and e.area:
            return f"che temperatura c'è in {e.area.lower()}?"
    return "cosa c'è acceso?" if ents else ""


def _casa_integrazione(ctx: ToolContext, per_iscritto=False, formato: str = "") -> dict:
    level = _level(ctx)
    if level not in ("familiare", "amministra"):
        return _ospite()
    be = getattr(ctx, "casa", None)
    diag = diagnose(ctx.cfg, be, riprova=True)
    if diag["codice"] == "ok" and be is not None:
        diag = diagnose(ctx.cfg, be, esempio=_esempio(be))
    if level != "amministra":
        return _final(frase_familiare(diag["codice"]), ok=True, stato=diag["stato"])
    # I consigli sui nomi e sulle aree raccolti dai comandi (08/10, casa/nomi.py): una volta
    consigli = nomi.consigli_da_dire()
    if consigli:
        diag["prossimo_passo"] = (diag["prossimo_passo"] + " Un consiglio: "
                                  + " ".join(consigli))
    text = diag["prossimo_passo"]
    extra = {}
    if str(per_iscritto).strip().lower() in ("true", "1", "sì", "si", "yes"):
        written = _scrivi_guida(ctx, diag, formato)
        text = written if written else text
        if text.endswith("La apro?"):
            # «sì» al turno dopo: decide il modello, con l'azione proposta davanti (Brain)
            extra["in_sospeso"] = {"domanda": "La apro?", "cosa": "la guida appena scritta",
                                   "tool": "pc_apri_file", "argomenti": {"risultato": 1}}
    return _final(text, ok=True, stato=diag["stato"], codice=diag["codice"], **extra)


def _scrivi_guida(ctx: ToolContext, diag: dict, formato: str) -> str:
    """La guida completa in PDF o Word, con il testo fisso di casa/guida.py: niente LLM."""
    svc = getattr(ctx, "documenti", None)
    if svc is None:
        return ("Non posso preparare documenti, quindi te lo dico a voce: " +
                diag["prossimo_passo"])
    fmt = str(formato or "").strip().lower()
    fmt = {"documento": "word", "docx": "word"}.get(fmt, fmt)
    if fmt not in svc.formati:
        fmt = "pdf" if "pdf" in svc.formati else svc.formati[0]
    if fmt == "excel":
        fmt = next((f for f in ("pdf", "word") if f in svc.formati), "excel")
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    prof = ctx.speakers.get(name) if name and ctx.speakers else None
    try:
        r = svc.scrivi_fisso(prof.id if prof else "amministra", fmt,
                             guida_scritta(diag, getattr(ctx.cfg, "casa_url", None)))
    except Exception as e:  # noqa: BLE001
        print(f"   [CASA] guida scritta non riuscita: {e}", flush=True)
        return "Non sono riuscita a preparare la guida scritta. " + diag["prossimo_passo"]
    kind = {"pdf": "in PDF", "word": "in Word"}.get(fmt, "")
    return (f"Ti ho preparato la guida {kind} {r['dove']}." + (" La apro?" if r["apribile"]
                                                               else ""))


# ─────────────────────────── registro ───────────────────────────

def casa_specs(collegata: bool, ospite: bool = False, pc_nome: str | None = None,
               integrazione: bool = True) -> list[ToolSpec]:
    """I tool della casa. `collegata`: indirizzo e token ci sono (anche se HA ora è giù:
    i tool restano, e dicono «la casa non risponde»). `ospite`: casa_ospite_domini non è
    vuoto. `pc_nome`: con il PC, la descrizione dice cosa resta ai tool pc_*."""
    specs = []
    levels = ALL if ospite else FAMILY
    if collegata:
        not_pc = (f" Non per il {pc_nome}: volume, musica e schermo del {pc_nome} sono dei "
                  f"tool pc_*." if pc_nome else "")
        specs += [
            ToolSpec(
                name="casa_comando",
                description=("Comanda i dispositivi della casa tramite Home Assistant: luci, "
                             "interruttori, prese, tapparelle, termostato, ventilatori. "
                             "comando: la richiesta in una frase breve all'imperativo, con il "
                             "dispositivo e la stanza come detti: «accendi la luce della "
                             "cucina», «spegni tutte le luci al piano di sopra», «abbassa le "
                             "tapparelle in sala», «imposta il termostato a 21 gradi», «imposta "
                             "la luminosità della luce bagno al 30%». Per un interruttore o una "
                             "presa usa il suo nome senza la parola interruttore: «spegni "
                             "Taverna», «accendi Bagno 1». Una chiamata per ogni "
                             "azione. Serrature, allarme, cancello e porta del garage non si "
                             "comandano." + not_pc),
                parameters={"type": "object",
                            "properties": {"comando": {"type": "string"}},
                            "required": ["comando"]},
                func=_casa_comando, risk="azione", levels=levels,
                # Il comando contiene il nome del dispositivo (calliope/argomenti_incerti.py:
                # solo misura, il «non trovato» ha già nomi_vicini)
                nomi={"comando": "casa"}),
            ToolSpec(
                name="casa_stato",
                description=("Dice com'è la casa adesso, dagli stati di Home Assistant. "
                             "cosa: il dispositivo o la stanza come detti: «temperatura in "
                             "camera», «temperatura fuori», «cosa c'è acceso», «porta del "
                             "garage», «tapparelle», «allarme», «finestre aperte»; vuoto per "
                             "un riassunto."),
                parameters={"type": "object",
                            "properties": {"cosa": {"type": "string"}}, "required": []},
                func=_casa_stato, risk="lettura", levels=levels, nomi={"cosa": "casa"}),
        ]
    if integrazione:
        specs.append(ToolSpec(
            name="casa_integrazione",
            description=("Dice a che punto è il collegamento con Home Assistant e il prossimo "
                         "passo per completarlo. Chiamalo subito, senza chiedere altro, se "
                         "chiedono «puoi collegarti alla domotica?», come collegare o "
                         "collegarti alla casa, alla domotica o a Home Assistant, se funziona, "
                         "o perché non riesci a comandare luci e dispositivi. "
                         "per_iscritto=true se vogliono i passi per iscritto (formato pdf o "
                         "word)."),
            parameters={"type": "object",
                        "properties": {"per_iscritto": {"type": "boolean"},
                                       "formato": {"type": "string", "enum": ["pdf", "word"]}},
                        "required": []},
            func=_casa_integrazione, risk="lettura", levels=FAMILY))
    return specs
