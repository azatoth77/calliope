"""
Gli scatti delle reti del modello, per rete e per profilo (15/10/2026, roadmap 2.11, E11).

Le reti e le spinte di Brain (config.RETI, categoria «modello») aiutano un modello debole a usare
i tool e a non dire cose false. Dal 20/10 quelle **mai scattate** si potranno spegnere nel
profilo del 26B (decisione 0028, § 3: non nel profilo ridotto da 8 GB), ma prima serve il
rapporto: per ogni rete, dal registro dei turni (calliope/turnlog.py), quante volte è scattata,
su quanti turni era accesa, con quale profilo, l'ultima volta e com'è finito il turno.

Una rete non scrive il proprio nome nel registro: scrive le **regole** dei suoi casi (campo
`regole` del turno), e una rete ne ha più d'una (`spinta_dichiarata` → anche
`dichiarata_taciuta`, `dichiarata_onesta`, `dichiarata_tool_fallito`). L'inventario sta qui,
in REGOLE_RETE; `prove/prova_reti_scatti.py` controlla che ogni rete del modello ci sia e che
ogni regola elencata sia scritta davvero nel codice (un nome cambiato si vedrebbe come «mai
scattata»).

- **scatti**: i turni in cui c'è almeno una regola della rete;
- **osservati**: i turni con una risposta del modello (`esito: risposta`) in cui la rete era
  accesa, dal giorno in cui è entrata nel codice (NEL_CODICE_DAL; l'installazione può essere
  arrivata dopo: è un massimo). Accesa: dal campo `reti_spente` del turno (dal 15/10) o, nei
  turni di prima, da quelle del profilo (PROFILI_LLM: le aggiunte del locale non si vedono,
  e il rapporto lo dice);
- **esito dopo lo scatto**, il segnale che c'è: il turno è finito con un ripiego («Non ci sono
  riuscita…», scelta_tool), con una regola di esito cattivo della rete (giri di correzione
  esauriti), oppure la stessa persona ha ripetuto o riformulato la frase entro 90 s o ha
  interrotto la risposta: «dubbio». Altrimenti «bene». Senza le parole (minori, ospiti) la
  ripetizione non si vede: quei turni si contano a parte. Per qualche rete c'è anche un segno
  che il suo aiuto è servito (SEGUITI: «forse intendeva X» usato al turno dopo) e, per le
  spinte, se dopo lo scatto un tool è riuscito nello stesso turno.

Solo lettura del registro, nessun modello. `calliope stato --reti [--giorni N] [--json]`.
"""
from __future__ import annotations

import datetime

from .config import MODELLO, PROFILI_LLM, RETI, SICUREZZA, reti_di
from .scelta_tool import RIPETUTA_S, SOMIGLIANZA, _chi, _quando, _ripiego, somiglianza

# Sotto questi turni osservati «mai scattata» non dice ancora molto (scritto accanto)
MIN_OSSERVATI = 200

# rete → le regole che scrive quando scatta (nomi nel campo `regole` del turno)
REGOLE_RETE: dict[str, tuple[str, ...]] = {
    "textcallguard": ("textcallguard",),
    "chiamata_in_mezzo": ("chiamata_in_mezzo", "spinta_nome_tool", "nome_tool_ripetuto"),
    "spinta_promessa": ("spinta_promessa",),
    "spinta_richiesta": ("spinta_richiesta", "richiesta_trattenuta"),
    "spinta_dichiarata": ("spinta_dichiarata", "dichiarata_taciuta", "dichiarata_onesta",
                          "dichiarata_detta", "dichiarata_trattenuta", "azione_non_fatta",
                          "azione_non_fatta_onesta", "azione_non_fatta_attesa",
                          "dichiarata_tool_fallito"),
    "riferimento_casa": ("riferimento_casa",),
    "riferimento_agenda": ("riferimento_agenda",),
    "riferimento_lavoro": ("riferimento_lavoro",),
    "estensione_nominata": ("estensione_nominata", "estensioni_elenco_turno",
                            "estensioni_limiti_turno", "estensioni_limiti_tetto"),
    "modalita_sviluppo": ("sviluppo_modalita", "sviluppo_riga_fuori_tema",
                          "sviluppo_promemoria_giorno"),
    "conferma_al_posto_del_vuoto": ("conferma_al_posto_del_vuoto", "vuoto_ripiego"),
    "vuoto_seconda_passata": ("vuoto_seconda_passata",),
    "ricerca_promessa": ("ricerca_promessa",),
    "citazione_tolta": ("citazione_tolta",),
    "nome_tool_parlato": ("nome_tool_parlato", "annuncio_tool_taciuto"),
    "eco_contesto": ("eco_contesto",),
    "spinta_archivio": ("spinta_archivio",),
    "spinta_stanza": ("spinta_stanza", "stanza_dopo_ricerca_vuota"),
    "spinta_rinuncia": ("spinta_rinuncia",),
    "spinta_sviluppo": ("spinta_sviluppo", "sviluppo_testo_taciuto"),
    "spinta_esercizi": ("spinta_esercizi", "esercizi_domanda_inventata",
                        "esercizi_promessa_taciuta"),
    "scrivo_qui_a_voce": ("scrivo_qui_tolto",),
    "argomento_forse": ("argomento_forse",),
    "correzione_tool": ("correzione_tool", "correzione_avviso"),
    "ricerca_recente": ("ricerca_recente", "ricerca_elenco", "ricerca_recente_spenta",
                        "spinta_ricerca"),
    "risposta_ripetuta": ("spinta_ripetuta",),
    "domanda_insistita": ("domanda_insistita",),
    "ciclo_ripetuto": ("ciclo_ripetuto",),
}

# rete → regole che dicono che il suo aiuto è stato usato (anche in un turno dopo)
SEGUITI: dict[str, tuple[str, ...]] = {
    "argomento_forse": ("argomento_forse_usato",),
}

# rete → regole che, nello stesso turno, dicono che lo scatto non è bastato
ESITO_CATTIVO: dict[str, tuple[str, ...]] = {
    "correzione_tool": ("correzioni_esaurite",),
}

# rete → dove sta nel codice (per l'inventario e il rapporto)
DOVE: dict[str, str] = {
    "textcallguard": "brain.py, TextCallGuard in Brain._turn",
    "chiamata_in_mezzo": "brain.py, ToolNameHold in Brain._turn e la spinta in Brain.chat",
    "spinta_promessa": "brain.py, ACTION_PROMISE in Brain.chat",
    "spinta_richiesta": "brain.py, TOOL_REQUEST e hold_request in Brain.chat",
    "spinta_dichiarata": "brain.py, ClaimHold e ACTION_CLAIM in Brain.chat",
    "riferimento_casa": "brain.py, Brain._take_reference (REFERENCE_MSG)",
    "riferimento_agenda": "brain.py, Brain._take_agenda_reference (AGENDA_MSG)",
    "riferimento_lavoro": "brain.py, Brain._lavoro_turno (LAVORO_MSG)",
    "estensione_nominata": "brain.py, Brain._estensioni_nominate (EST_NOMINATA_MSG)",
    "modalita_sviluppo": "brain.py, Brain._sviluppo_turno e la riga in coda (SVILUPPO_MSG)",
    "conferma_al_posto_del_vuoto": "brain.py, Brain.chat (risposta vuota)",
    "vuoto_seconda_passata": "brain.py, Brain.chat (EMPTY_NUDGE)",
    "ricerca_promessa": "ciclo.py, SEARCH_PROMISE dopo la risposta",
    "citazione_tolta": "ciclo.py, strip_false_citation nella resa della frase",
    "nome_tool_parlato": "ciclo.py, Brain.speak_tool_names nella resa della frase",
    "eco_contesto": "brain.py, ContextEcho in Brain._turn",
    "spinta_archivio": "brain.py, Brain.chat (conversazione_cerca, ARCHIVIO_NOTA)",
    "spinta_stanza": "brain.py, Brain.chat (stanza_cerca, STANZA_NOTA)",
    "spinta_rinuncia": "brain.py, Brain.chat e politica.rinuncia (RINUNCIA_NUDGE)",
    "spinta_sviluppo": "brain.py, Brain.chat (SVILUPPO_NUDGE)",
    "spinta_esercizi": "brain.py, Brain.chat (ESERCIZI_NUDGE, esercizi/sessione.py)",
    "scrivo_qui_a_voce": "brain.py, FraseTolta(SCRIVO_QUI) in Brain._turn",
    "argomento_forse": "brain.py e argomenti_incerti.py, dopo un esito vuoto",
    "correzione_tool": "brain.py, Brain._correzione_aperta (CORREZIONE_NUDGE)",
    "ricerca_recente": "brain.py, Brain._ricerca_turno (RICERCA_MSG, RICERCA_NUDGE)",
    "risposta_ripetuta": "brain.py e ripetizione.py (RIPETUTA_NUDGE)",
    "domanda_insistita": "brain.py e ripetizione.py (INSISTE_MSG)",
    "ciclo_ripetuto": "ciclo_ripetuto.py, CicloRipetuto in Brain._turn",
}

# rete → il giorno in cui è entrata nel codice (git log -S, primo commit con il suo nome). Le
# reti del 06/10 c'erano da prima (il package è nato quel giorno): tutto il registro le vede.
# I turni di prima non contano come «osservati»
NEL_CODICE_DAL: dict[str, str] = {
    "riferimento_lavoro": "2026-10-07",
    "estensione_nominata": "2026-10-08",
    "modalita_sviluppo": "2026-10-08",
    "spinta_esercizi": "2026-10-08",
    "argomento_forse": "2026-10-08",
    "correzione_tool": "2026-10-09",
    "ricerca_recente": "2026-10-09",
    "risposta_ripetuta": "2026-10-09",
    "spinta_sviluppo": "2026-10-12",
    "scrivo_qui_a_voce": "2026-10-12",
    "spinta_stanza": "2026-10-14",
    "ciclo_ripetuto": "2026-10-14",
    "domanda_insistita": "2026-10-15",
}

SENZA_PROFILO = "(nessun profilo)"


def _spente(t: dict) -> tuple[set, bool]:
    """Le reti spente in questo turno e se il turno lo dice (True) o si deduce dal profilo."""
    if isinstance(t.get("reti_spente"), list):
        return set(t["reti_spente"]), True
    prof = PROFILI_LLM.get(t.get("profilo") or "") or {}
    return set(prof.get("llm_reti_spente") or ()), False


def accesa(t: dict, rete: str) -> bool:
    """La rete era accesa in questo turno? (le reti di sicurezza sempre)."""
    r = RETI.get(rete)
    if r is not None and r.categoria == SICUREZZA:
        return True
    spente, _ = _spente(t)
    return rete not in spente and "tutte" not in spente


def _profilo(t: dict) -> str:
    return str(t.get("profilo") or SENZA_PROFILO)


def _dubbio(t: dict, dopo: dict | None, rete: str) -> str | None:
    """Perché il turno dello scatto non è finito bene, o None. `dopo`: il turno seguente
    della stessa persona entro RIPETUTA_S (o None)."""
    if _ripiego(t):
        return "ripiego"
    if set(t.get("regole") or ()) & set(ESITO_CATTIVO.get(rete, ())):
        return "esito"
    if dopo is not None:
        if dopo.get("esito") == "interruzione" or "stop_interruzione" in (dopo.get("regole")
                                                                          or ()):
            return "interrotta"
        if isinstance(t.get("testo"), str) and isinstance(dopo.get("testo"), str) \
                and somiglianza(t["testo"], dopo["testo"]) >= SOMIGLIANZA:
            return "ripetuta"
    return None


def _successivi(turni: list[dict]) -> dict[int, dict]:
    """Per ogni turno (indice) il turno dopo della stessa persona entro RIPETUTA_S."""
    out: dict[int, dict] = {}
    ultimo: dict = {}                  # chi → (indice, quando)
    for i, t in enumerate(turni):
        chi, q = _chi(t), _quando(t)
        if not chi or q is None:
            continue
        if chi in ultimo:
            j, qj = ultimo[chi]
            if 0 <= q - qj <= RIPETUTA_S:
                out[j] = t
        ultimo[chi] = (i, q)
    return out


def _vuota() -> dict:
    return {"scatti": 0, "volte": 0, "osservati": 0, "ultima": None, "bene": 0,
            "dubbi": {"ripiego": 0, "esito": 0, "ripetuta": 0, "interrotta": 0},
            "senza_parole": 0, "tool_riuscito": 0, "seguiti": 0, "regole": {},
            "spenta_turni": 0}


def riassunto(turni: list[dict], cfg=None) -> dict:
    """Il rapporto: per profilo e per rete del modello. `cfg` (facoltativa): la configurazione
    di adesso, per dire quali reti sono spente dal profilo in uso e quali nel locale."""
    turni = sorted((t for t in turni if isinstance(t, dict)),
                   key=lambda x: str(x.get("inizio") or ""))
    dopo = _successivi(turni)
    reti = reti_di(MODELLO)
    profili: dict[str, dict] = {}
    dedotti = registrati = 0
    for i, t in enumerate(turni):
        prof = _profilo(t)
        p = profili.setdefault(prof, {"turni": 0, "risposte": 0, "reti": {}})
        p["turni"] += 1
        risposta = t.get("esito") == "risposta"
        p["risposte"] += int(risposta)
        if risposta:
            if isinstance(t.get("reti_spente"), list):
                registrati += 1
            else:
                dedotti += 1
        regole = list(t.get("regole") or ())
        giorno = str(t.get("inizio") or "")[:10]
        for rete in reti:
            mie = [r for r in regole if r in REGOLE_RETE.get(rete, ())]
            seguiti = [r for r in regole if r in SEGUITI.get(rete, ())]
            nato = NEL_CODICE_DAL.get(rete, "")
            if not mie and not seguiti and (not risposta or (nato and giorno and giorno < nato)):
                continue
            d = p["reti"].setdefault(rete, _vuota())
            d["seguiti"] += len(seguiti)
            on = accesa(t, rete) or bool(mie)
            if risposta and not (nato and giorno and giorno < nato):
                if on:
                    d["osservati"] += 1
                else:
                    d["spenta_turni"] += 1
            if not mie:
                continue
            d["scatti"] += 1
            d["volte"] += len(mie)
            for r in mie:
                d["regole"][r] = d["regole"].get(r, 0) + 1
            if str(t.get("inizio") or "") > str(d["ultima"] or ""):
                d["ultima"] = t.get("inizio")
            if any(isinstance(x, dict) and x.get("ok") for x in t.get("tool") or ()):
                d["tool_riuscito"] += 1
            perche = _dubbio(t, dopo.get(i), rete)
            if perche:
                d["dubbi"][perche] += 1
            else:
                d["bene"] += 1
                if not isinstance(t.get("testo"), str) or not t["testo"].strip():
                    d["senza_parole"] += 1
    # Lo stato di ogni rete nel profilo
    for p in profili.values():
        for rete in reti:
            d = p["reti"].setdefault(rete, _vuota())
            if d["scatti"]:
                d["stato"] = "scattata"
            elif d["osservati"]:
                d["stato"] = "mai scattata" + (" (pochi turni)" if d["osservati"] < MIN_OSSERVATI
                                               else "")
            elif d["spenta_turni"]:
                d["stato"] = "spenta"
            else:
                d["stato"] = "nessun turno"
    adesso = None
    if cfg is not None:
        prof_ora = getattr(cfg, "llm_profilo", None)
        dal_profilo = list((PROFILI_LLM.get(prof_ora or "") or {}).get("llm_reti_spente") or ())
        tutte = list(getattr(cfg, "llm_reti_spente", None) or ())
        adesso = {"profilo": prof_ora, "modello": getattr(cfg, "llm_model", None),
                  "spente_dal_profilo": dal_profilo,
                  "spente_nel_locale": [r for r in tutte if r not in dal_profilo]}
    giorni = sorted({str(t.get("inizio") or "")[:10] for t in turni if t.get("inizio")})
    return {"turni": len(turni), "dal": giorni[0] if giorni else None,
            "al": giorni[-1] if giorni else None, "profili": profili,
            "accese_registrate": registrati, "accese_dedotte": dedotti,
            "adesso": adesso, "min_osservati": MIN_OSSERVATI,
            "sicurezza": reti_di(SICUREZZA)}


def mai_scattate(r: dict, profilo: str, minimo: int | None = None) -> list[str]:
    """Le reti accese e mai scattate in un profilo, con almeno `minimo` turni osservati."""
    m = MIN_OSSERVATI if minimo is None else minimo
    p = r["profili"].get(profilo) or {"reti": {}}
    return [n for n, d in p["reti"].items() if not d["scatti"] and d["osservati"] >= m]


def _ora(s) -> str:
    try:
        return datetime.datetime.fromisoformat(str(s)).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return "—"


def testo(r: dict) -> str:
    """Le righe per `calliope stato --reti`."""
    righe = ["Reti del modello: scatti per rete e per profilo (E11, dal registro dei turni)"]
    if not r["turni"]:
        righe.append("Nessun turno nel registro.")
        return "\n".join(righe)
    righe.append(f"{r['turni']} turni dal {r['dal']} al {r['al']}.")
    a = r.get("adesso")
    if a:
        righe.append(f"Adesso: profilo {a['profilo'] or 'nessuno'} ({a['modello']}); spente dal "
                     f"profilo: {', '.join(a['spente_dal_profilo']) or 'nessuna'}; spente nel "
                     f"locale: {', '.join(a['spente_nel_locale']) or 'nessuna'}.")
    if r["accese_dedotte"]:
        righe.append(f"Accese o spente: in {r['accese_dedotte']} risposte dedotto dal profilo "
                     f"(turni di prima del 15/10, senza `reti_spente`: le reti spente nel locale "
                     f"non si vedono), in {r['accese_registrate']} scritto nel turno.")
    for prof, p in sorted(r["profili"].items(), key=lambda kv: -kv[1]["risposte"]):
        righe += ["", f"Profilo {prof}: {p['turni']} turni, {p['risposte']} risposte del modello"]
        righe.append(f"  {'rete':<28} {'scatti':>6} {'osserv.':>8}  {'ultima':<11} "
                     f"{'bene':>4} {'dubbi':>5}  stato")
        ordine = sorted(p["reti"].items(), key=lambda kv: (kv[1]["scatti"] > 0, -kv[1]["osservati"]
                                                           if not kv[1]["scatti"] else -kv[1]["scatti"],
                                                           kv[0]))
        for nome, d in ordine:
            dubbi = sum(d["dubbi"].values())
            stato = d["stato"].replace("mai scattata", "MAI SCATTATA")
            extra = []
            if dubbi:
                extra.append(", ".join(f"{k} {v}" for k, v in d["dubbi"].items() if v))
            if d["senza_parole"]:
                extra.append(f"{d['senza_parole']} bene senza parole")
            if d["tool_riuscito"]:
                extra.append(f"tool riuscito {d['tool_riuscito']}")
            if d["seguiti"]:
                extra.append(f"aiuto usato {d['seguiti']}")
            if d["scatti"] and len(d["regole"]) > 1:
                extra.append(" ".join(f"{k} {v}" for k, v in sorted(d["regole"].items(),
                                                                       key=lambda kv: -kv[1])))
            righe.append(f"  {nome:<28} {d['scatti']:>6} {d['osservati']:>8}  "
                         f"{_ora(d['ultima']) if d['ultima'] else '—':<11} "
                         f"{d['bene'] if d['scatti'] else '':>4} "
                         f"{dubbi if d['scatti'] else '':>5}  {stato}"
                         + (f"  ({'; '.join(extra)})" if extra else ""))
        mai = mai_scattate(r, prof)
        if mai:
            righe.append(f"  Mai scattate con almeno {r['min_osservati']} risposte osservate: "
                         + ", ".join(mai) + ".")
    righe += ["", "Bene: niente ripiego, nessuna ripetizione o interruzione della stessa persona "
                  "entro 90 s; dubbi: il contrario (le ripetizioni si vedono solo con le parole). "
                  "Osservate: risposte del modello con la rete accesa da quando è nel codice.",
              "Reti di sicurezza (sempre accese, non si contano qui): "
              + ", ".join(r["sicurezza"]) + ". Spegnere una rete lo decide chi amministra "
              "(llm_reti_spente nel profilo, decisione 0028)."]
    return "\n".join(righe)
