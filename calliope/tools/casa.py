"""
I tool casa_*: la casa comandata e letta a voce (calliope/casa/).

- casa_comando(comando): il modello riscrive la richiesta in una frase breve nella forma
  che l'agente integrato di Home Assistant capisce («accendi la luce della cucina»).
  L'adattatore la interpreta senza eseguirla, le regole di Calliope (casa/regole.py)
  decidono, poi si esegue. La risposta di HA è la `risposta_finale`: si dice così com'è,
  senza un'altra passata del modello (~0,3–0,5 s in meno). Se HA non capisce, il modello
  riceve i nomi e le stanze più vicini e riprova una volta.
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
from ..casa.parole import categorie, descrivi, riscrivi, suggerimenti, trova_per_nome
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
                func=_casa_comando, risk="azione", levels=levels),
            ToolSpec(
                name="casa_stato",
                description=("Dice com'è la casa adesso, dagli stati di Home Assistant. "
                             "cosa: il dispositivo o la stanza come detti: «temperatura in "
                             "camera», «temperatura fuori», «cosa c'è acceso», «porta del "
                             "garage», «tapparelle», «allarme», «finestre aperte»; vuoto per "
                             "un riassunto."),
                parameters={"type": "object",
                            "properties": {"cosa": {"type": "string"}}, "required": []},
                func=_casa_stato, risk="lettura", levels=levels),
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
