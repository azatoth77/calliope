"""
Lo stato del dialogo come macchina a stati: passo 1, **in ombra** (10/10/2026).

Progetto: docs/ricerche/2026-10-10-macchina-stati.md (§ 3 la macchina, § 3.4 l'interprete,
§ 3.5 il consenso, § 6 il piano). Due decisioni di Dario del 10/10 ne sono la base: la macchina
**non interpreta il linguaggio** (tiene lo stato e i vincoli; il significato della risposta lo
dà il modello con `proposta_rispondi`, o la corsia veloce per le forme chiuse dette per intero,
calliope/risposte.py), e gli scambi fra macchina e modello **non inquinano la conversazione**
(lo stato è un blocco effimero del turno, mai nella storia).

Cosa c'è in questo passo, e solo questo:

- l'**ossatura** (`Proposta`, `Chi`, `StatoPersona`, `StatoCorsia`) e gli **adattatori in sola
  lettura** sugli stati di oggi (`Conversazione.pending` con il tool del turno, la domanda della
  politica, la frase di sfida di `SpeakerContext`, lo sviluppo aperto, il cancello dei minori):
  la macchina è una facciata, non una copia, e non scrive niente;
- il **blocco dello stato** per il turno (`blocco`, ≤ 520 caratteri) che in ombra prende il posto
  di `PENDING_MSG` per le proposte sì/no: proposta aperta, gravità E1–E4, chi parla e quanto è
  sicura la voce, e l'invito a rispondere con `proposta_rispondi`;
- la **decisione che prenderebbe la macchina** (`decidi`), con il **consenso del progetto**
  (`consenso_progetto`, la tabella del § 3.5) calcolato solo per il confronto;
- il **confronto nel registro dei turni** (`confronto`, campo `dialogo_ombra`): cosa avrebbero
  deciso corsia veloce, modello e consenso del progetto, cosa è successo davvero, accordo o
  disaccordo per tipo. Nessun testo, nessun valore degli argomenti;
- il riassunto per `calliope stato --turni` (`riassunto`, `testo`).

**Non decide niente.** Con `dialogo_interprete: ombra` (predefinito) l'esito `si` di
`proposta_rispondi` diventa la chiamata che il modello avrebbe fatto oggi (il tool proposto con i
suoi argomenti, attraverso `ToolRegistry.call` e la politica di oggi, che decide); gli altri esiti
non fanno niente (oggi il modello, senza un sì, non chiama il tool e la proposta resta com'è).
`spento` toglie lo schema, il blocco e il confronto: il percorso di prima, identico. `acceso` (la
macchina che esegue la proposta, passo 2) non è ancora realizzato: la configurazione lo rifiuta e
vale `ombra`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import politica, valore
from .risposte import GRAZIE, NO, NUOVA, SI, STOP, USCITA, forma_chiusa

SPENTO, OMBRA, ACCESO = "spento", "ombra", "acceso"
MODI = (SPENTO, OMBRA, ACCESO)
TOOL = "proposta_rispondi"
ESITI = ("si", "no", "correzione", "rinvio", "altro")


def modo(cfg) -> str:
    """Il modo dell'interprete: "spento" o "ombra". «acceso» è un segnaposto (passo 2 del
    progetto): finché non c'è, vale l'ombra (la configurazione lo segnala all'avvio)."""
    m = str(getattr(cfg, "dialogo_interprete", OMBRA) or OMBRA).strip().lower()
    return SPENTO if m == SPENTO else OMBRA


# ─────────────────────────── l'ossatura (§ 3.2) ───────────────────────────

@dataclass
class Chi:
    """Chi parla adesso e quanto è sicuro (§ 3.6, solo quanto serve al passo 1)."""
    chiave: object = None            # Brain._speaker_key: id del profilo, None = ospite
    come: str | None = None          # identified_by: voce, breve, conversazione, schermo…
    sicurezza: str = "incerta"       # sicura | probabile | incerta | scritta
    livello: str | None = None       # il livello del profilo (non della frase)
    compagnia: bool = False
    incerta_admin: bool = False      # voce incerta fra chi amministra e un minore
    sfida_superata: bool = False


@dataclass
class Proposta:
    """La sola proposta parlata e aperta di una persona (letta da `Conversazione.pending`)."""
    id: str
    tool: str
    argomenti: dict | None
    cosa: str
    domanda: str
    origine: str                     # tool | politica | forse
    effetto: int                     # valore.E0..E4
    sfida_classe: bool
    tipo: str                        # si_no | dato
    chi: object
    satellite: object
    turno: int
    turni: int                       # da quanti turni è aperta (1 = l'ultima risposta)


@dataclass
class StatoPersona:
    conversazione: str = "aperta"
    turno: int = 0
    proposta: Proposta | None = None
    sfida: dict | None = None        # {"tool", "stessa_persona", "stesso_tool"}
    attivita: str | None = None      # sviluppo | esercizi
    rifiuti: int = 0
    chiusa_da: str | None = None     # la proposta di prima, persa con la conversazione


@dataclass
class StatoCorsia:
    satellite: object = None
    persona: Chi = field(default_factory=Chi)
    cancello: int | None = None      # 2: la frase è passata dal secondo cancello dei minori


# ─────────────────────────── adattatori in sola lettura ───────────────────────────

def sicurezza_voce(sc, cfg=None) -> str:
    """La sicurezza della voce in tre parole (più «scritta»): sicura, probabile, incerta."""
    if sc is None or not getattr(sc, "current_speaker", None):
        return "incerta"
    come = getattr(sc, "identified_by", None)
    if getattr(sc, "incerta", None):
        return "incerta"
    if come == "schermo":
        return "scritta"
    if getattr(sc, "compagnia", False) and come != "voce":
        return "incerta"
    if come == "voce" and not getattr(sc, "from_session", False):
        return "sicura"
    if come == "breve":
        soglia = float(getattr(cfg, "speaker_conferma_breve_soglia", 0.40) or 0.40)
        p = getattr(sc, "punteggio", None)
        ok = (getattr(sc, "voce_sicura", None) == getattr(sc, "current_speaker", None)
              and isinstance(p, (int, float)) and p >= soglia)
        return "probabile" if ok else "incerta"
    if come in ("conversazione", "voce"):
        return "probabile"           # zona grigia, continuità, proprietario
    return "incerta"


def chi_da_oggi(sc, chiave, cfg=None, admin_incerta: bool = False) -> Chi:
    return Chi(chiave=chiave, come=getattr(sc, "identified_by", None),
               sicurezza=sicurezza_voce(sc, cfg),
               livello=getattr(sc, "profile_level", None) or getattr(sc, "current_level", None),
               compagnia=bool(getattr(sc, "compagnia", False)), incerta_admin=admin_incerta,
               sfida_superata=bool(getattr(sc, "sfida_superata", False)))


def proposta_da_oggi(p, tool_turno: str | None, turno_ora: int, tools=None) -> Proposta | None:
    """La proposta di oggi (`Conversazione.pending`) **valida per questo turno**: quella che
    `Brain._take_pending` ha lasciato (il tool del turno è il suo). Sola lettura."""
    if not isinstance(p, dict) or not p.get("tool") or tool_turno != p.get("tool"):
        return None
    tool = p["tool"]
    spec = tools.get(tool) if tools is not None and hasattr(tools, "get") else None
    args = p.get("args") if isinstance(p.get("args"), dict) else None
    try:
        eff = valore.effetto(tool, args or {}, spec)
    except Exception:  # noqa: BLE001 — nel dubbio, E3 (come valore.effetto)
        eff = valore.E3
    cl = politica.classe_di(tool, spec)
    domanda = str(p.get("domanda") or "")
    origine = ("politica" if p.get("politica") else
               "forse" if domanda.startswith("Intendevi") else "tool")
    # «dato»: un testo proprio, una domanda non sì/no, o una domanda a cui si risponde con
    # il tool del dato (`risposta`, passo 0: la domanda dell'agente, il «no» passa al servizio)
    tipo = ("dato" if p.get("su_misura") or p.get("risposta")
            or not politica.domanda_si_no(domanda) else "si_no")
    nata = int(p.get("turno", turno_ora) or 0)
    return Proposta(id=f"p{nata}", tool=tool, argomenti=args, cosa=str(p.get("cosa") or ""),
                    domanda=domanda, origine=origine, effetto=int(eff),
                    sfida_classe=bool(cl.sfida), tipo=tipo, chi=p.get("chi"),
                    satellite=p.get("satellite"), turno=nata,
                    turni=max(1, turno_ora + 1 - nata))


def proposta_valida(p, chiave, cfg, turno_ora: int, ora: float | None = None) -> bool:
    """Una proposta di oggi ancora valida per `chiave` (tempo **e** turni, la persona): quello
    che `_take_pending` controllerebbe al turno dopo, senza consumarla (per le frasi che il
    ciclo decide prima di Brain)."""
    from .conferme import turni_validi
    if not isinstance(p, dict) or not p.get("tool"):
        return False
    ora = time.monotonic() if ora is None else ora
    if ora > float(p.get("scade", 0) or 0):
        return False
    if turno_ora + 1 - int(p.get("turno", turno_ora) or 0) > turni_validi(cfg):
        return False
    return "chi" not in p or p.get("chi") == chiave


def sfida_da_oggi(sc, chiave, proposta: Proposta | None) -> dict | None:
    s = getattr(sc, "sfida", None)
    if s is None:
        return None
    try:
        if s.scaduta():
            return None
    except Exception:  # noqa: BLE001
        pass
    tool = getattr(s, "tool", None)
    return {"tool": tool, "stessa_persona": getattr(s, "persona", None) == chiave,
            "stesso_tool": proposta is not None and proposta.tool == tool}


# ─────────────────────────── il blocco dello stato (§ 3.4) ───────────────────────────

BLOCCO_MSG = ("Stato del dialogo: proposta aperta {id}, «{domanda}»{per} ({tool}{argomenti}, "
              "gravità {effetto}), chiesta {quando}. Chi parla l'ha ricevuta, voce {sicurezza}. Se la "
              "frase risponde alla proposta, chiama proposta_rispondi con l'esito (si, no, "
              "correzione, rinvio, altro): il sì lo esegue il sistema. Se chiede altro, rispondi "
              "a quello.")


def _corto(t: str, n: int) -> str:
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def blocco(stato: StatoPersona, corsia: StatoCorsia) -> str | None:
    """Il blocco effimero del turno (≤ 520 caratteri; dopo la parte stabile, subito prima della
    frase; mai nella storia), o None: solo con una proposta sì/no aperta per chi parla. Le domande che chiedono
    un dato tengono il loro messaggio di oggi."""
    p = stato.proposta
    if p is None or p.tipo != "si_no":
        return None
    # La cosa proposta solo se la domanda da sola non la dice («Lo apro?», «Procedo?»)
    per = (f" per {_corto(p.cosa, 50)}" if p.cosa and len(p.domanda) < 30
           and p.cosa != "l'azione proposta" else "")
    # Gli argomenti restano (come in PENDING_MSG): in ombra il modello che chiama direttamente
    # il tool proposto è il percorso di oggi, e alcuni servono a riconoscere l'offerta (l'id
    # `proposta` di lavoro_affida, prova_lavori_riavvio)
    import json
    arg = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}"
                    for k, v in (p.argomenti or {}).items())
    argomenti = f" con {_corto(arg, 110)}" if arg else ""
    return BLOCCO_MSG.format(
        id=p.id, domanda=_corto(p.domanda, 80), per=per, tool=p.tool, argomenti=argomenti, effetto=valore.NOMI_EFFETTO.get(p.effetto, "E3"),
        quando="nell'ultima risposta" if p.turni <= 1 else f"{p.turni} turni fa",
        sicurezza=corsia.persona.sicurezza)


# ─────────────────────────── il consenso del progetto (§ 3.5, solo ombra) ───────────────────────────

ESEGUE, SFIDA, CHI_PARLA, A_VOCE, NO_CONSENSO = "esegue", "sfida", "chi_parla", "a_voce", "no"


def consenso_progetto(chi: Chi, p: Proposta, livelli=None) -> str:
    """`consenso.basta` del progetto (§ 3.5), **in ombra**: esegue | sfida | chi_parla | a_voce |
    no. Una tabella sola: come parla × gravità. Le righe:

    - la proposta non è di chi parla (o chi parla è un ospite e la proposta era di una persona):
      no; la proposta di un ospite vale per l'ospite solo per E0–E2;
    - il livello della **persona** non basta per il tool: no;
    - voce incerta fra chi amministra e un minore: «chi parla?»;
    - compagnia senza la voce nella frase: sfida;
    - scritto dallo schermo personale: E0–E2 esegue, oltre «a voce»;
    - voce sicura in questa frase: E0–E3 esegue, E4 o sfida della classe sfida (salvo superata);
    - breve probabile (voce sicura nella finestra, impronta ≥ soglia): E0–E2 esegue, oltre sfida;
    - zona grigia, continuità, proprietario: E0–E2 esegue, oltre sfida;
    - breve incerta o altro: sfida.
    """
    e = p.effetto
    alta = e >= valore.E4 or p.sfida_classe
    if p.chi is not None and chi.chiave != p.chi:
        return NO_CONSENSO
    if chi.chiave is None:
        return ESEGUE if p.chi is None and e <= valore.E2 else NO_CONSENSO
    if livelli is not None and chi.livello is not None and chi.livello not in livelli:
        return NO_CONSENSO
    if chi.sfida_superata:
        return ESEGUE
    if chi.incerta_admin:
        return CHI_PARLA
    if chi.compagnia and chi.come != "voce":
        return SFIDA
    if chi.sicurezza == "scritta":
        return ESEGUE if e <= valore.E2 else A_VOCE
    if chi.sicurezza == "sicura":
        return SFIDA if alta else ESEGUE
    if chi.sicurezza == "probabile":
        return ESEGUE if e <= valore.E2 else SFIDA
    return SFIDA


# ─────────────────────────── la decisione della macchina (§ 3.3) ───────────────────────────

def decidi(stato: StatoPersona, corsia: StatoCorsia, forma: str | None,
           risposta: str | None = None, diretta: bool = False, livelli=None) -> dict:
    """Cosa deciderebbe la macchina con le priorità del § 3.3: {"macchina", "consenso", "via"}.
    `forma` è la corsia veloce, `risposta` l'esito valido di `proposta_rispondi`, `diretta` il
    modello che ha chiamato direttamente il tool proposto (sì implicito)."""
    p = stato.proposta
    out = {"macchina": None, "consenso": None, "via": None}
    if corsia.cancello:
        out["macchina"] = "proposta_persa_cancello" if p is not None else "cancello"
        out["via"] = "pavimento"
        return out
    s = stato.sfida
    if s is not None and s.get("stessa_persona"):
        out["macchina"], out["via"] = "sfida_in_corso", "sfida"
        return out
    if p is not None and p.tipo == "si_no":
        si = None
        if forma == SI:
            si, out["via"] = True, "corsia"
        elif forma in (NO, STOP, USCITA, NUOVA):
            out["via"] = "corsia"
            out["macchina"] = {NO: "chiude_no", STOP: "chiude_stop", USCITA: "proposta_persa_uscita",
                               NUOVA: "proposta_persa_nuova"}[forma]
            return out
        elif risposta is not None:
            out["via"] = "modello"
            if risposta == "si":
                si = True
            else:
                out["macchina"] = {"no": "chiude_no", "correzione": "chiude_correzione",
                                   "rinvio": "chiude_rinvio", "altro": "resta"}.get(risposta, "resta")
                return out
        elif diretta:
            si, out["via"] = True, "diretta"
        if si:
            c = consenso_progetto(corsia.persona, p, livelli)
            # Sì implicito (il tool proposto chiamato direttamente) per E3–E4: serve in più la
            # forma chiusa, il giudice isolato o la sfida (§ 3.4, regola proposta_si_implicito)
            if out["via"] == "diretta" and c == ESEGUE and p.effetto >= valore.E3:
                c = SFIDA
            out["consenso"] = c
            out["macchina"] = c
            return out
        out["macchina"] = "resta"
        return out
    if p is not None:                         # una domanda che chiede un dato
        if forma == NO:
            out["macchina"], out["via"] = "avvisa_servizio_no", "corsia"
        else:
            out["macchina"] = "al_servizio" if diretta else "resta"
            out["via"] = "diretta" if diretta else None
        return out
    if forma in (STOP, USCITA, NUOVA, GRAZIE):
        out["macchina"] = {STOP: "stop", USCITA: "uscita", NUOVA: "nuova",
                           GRAZIE: "cortesia"}[forma]
        if stato.attivita and forma == GRAZIE:
            out["macchina"] = "al_modello"    # cortesia solo senza attività aperta (§ 3.3)
        out["via"] = "corsia"
        return out
    out["macchina"] = "al_modello"
    return out


# ─────────────────────────── cosa è successo oggi, e il confronto ───────────────────────────

def esito_oggi(p: Proposta | None, regole, tools_turno, pending_dopo, sfida_dopo,
               turno: int) -> str:
    """Cosa è successo alla proposta in questo turno, con le regole di oggi: eseguita | sfida |
    domanda | fermata | rifiutata | resta | sostituita | chiusa | nessuna."""
    if p is None:
        return "nessuna"
    regole = set(regole or ())
    if "proposta_rifiutata" in regole:
        return "rifiutata"
    vere = [x for x in tools_turno or () if isinstance(x, dict) and x.get("nome") == p.tool]
    if any(x.get("ok") for x in vere):
        return "eseguita"
    if sfida_dopo is not None and getattr(sfida_dopo, "tool", None) == p.tool:
        return "sfida"
    if vere and isinstance(pending_dopo, dict) and pending_dopo.get("tool") == p.tool \
            and pending_dopo.get("turno") == turno:
        return "domanda"
    if vere:
        return "fermata"
    if isinstance(pending_dopo, dict) and pending_dopo.get("tool"):
        return "resta" if pending_dopo.get("turno") == p.turno else "sostituita"
    return "chiusa"


# Le categorie per l'accordo: esegue, chiede (sfida, «chi parla?», a voce, una domanda), chiude,
# resta
_CAT_MACCHINA = {"esegue": "esegue", "sfida": "chiede", "chi_parla": "chiede", "a_voce": "chiede",
                 "sfida_in_corso": "chiede", "no": "chiude", "chiude_no": "chiude",
                 "chiude_stop": "chiude", "chiude_correzione": "chiude", "chiude_rinvio": "chiude",
                 "proposta_persa_uscita": "chiude", "proposta_persa_nuova": "chiude",
                 "proposta_persa_cancello": "chiude", "avvisa_servizio_no": "chiude",
                 "resta": "resta", "al_modello": "resta", "al_servizio": "esegue"}
_CAT_OGGI = {"eseguita": "esegue", "sfida": "chiede", "domanda": "chiede", "fermata": "chiude",
             "rifiutata": "chiude", "chiusa": "chiude", "sostituita": "chiude", "resta": "resta",
             "stop": "chiude", "uscita": "chiude", "cortesia": "resta",
             "stop_interruzione": "chiude", "cancello": "resta"}


def accordo(macchina: str | None, oggi: str) -> tuple[bool | None, str | None]:
    a, b = _CAT_MACCHINA.get(macchina or ""), _CAT_OGGI.get(oggi)
    if a is None or b is None:
        return None, None
    return a == b, (None if a == b else f"{a}_vs_{b}")


def _proposta_reg(p: Proposta | None) -> dict | None:
    if p is None:
        return None
    return {"id": p.id, "origine": p.origine, "tipo": p.tipo,
            "effetto": valore.NOMI_EFFETTO.get(p.effetto, "E3"), "sfida_classe": p.sfida_classe,
            "turni": p.turni}


def lessico_oggi(testo: str, p: Proposta | None) -> str | None:
    """Come leggono la frase i lessici di oggi (politica.consenso / rifiuto): "si", "no" o None."""
    if not testo:
        return None
    try:
        if politica.consenso(testo):
            return "si"
        verbi = politica.verbi_di(politica.classe_di(p.tool), p.argomenti) if p else None
        if politica.rifiuto(testo, verbi):
            return "no"
    except Exception:  # noqa: BLE001
        return None
    return None


def confronto(d: dict, regole, tools_turno, pending_dopo, sfida_dopo, turno: int,
              livelli=None, interrotta: bool = False) -> dict | None:
    """Il campo `dialogo_ombra` del registro dei turni (nessun testo, nessun valore), o None se
    nel turno non c'era niente da confrontare (né proposta, né sfida, né attività con una forma
    chiusa, né una chiamata a proposta_rispondi, né una proposta persa o sostituita)."""
    stato: StatoPersona = d["stato"]
    corsia: StatoCorsia = d["corsia"]
    p = stato.proposta
    risposte = d.get("risposte") or []
    valida = next((r for r in risposte if not r.get("scartata")), None)
    offerte = int(d.get("offerte") or 0)
    if not (p or stato.sfida or stato.chiusa_da or risposte or corsia.cancello or offerte > 1
            or (stato.attivita and d.get("forma"))):
        return None
    dec = decidi(stato, corsia, d.get("forma"), valida.get("esito") if valida else None,
                 bool(d.get("diretta")), livelli)
    oggi = esito_oggi(p, regole, tools_turno, pending_dopo, sfida_dopo, turno)
    if p is None and stato.chiusa_da:
        dec["macchina"] = ("resta_altra_persona" if stato.chiusa_da == "conversazione_altra_persona"
                           else "proposta_persa_" + stato.chiusa_da.replace("conversazione_", ""))
    ok, tipo = accordo(dec["macchina"], oggi) if p is not None else (None, None)
    out = {"proposta": _proposta_reg(p),
           "chi": {"come": corsia.persona.come, "sicurezza": corsia.persona.sicurezza},
           "forma_chiusa": d.get("forma"), "lessico": d.get("lessico"),
           "modello": valida.get("esito") if valida else None,
           "diretta": bool(d.get("diretta")),
           "consenso": dec["consenso"], "macchina": dec["macchina"], "via": dec["via"],
           "oggi": oggi, "accordo": ok}
    if tipo:
        out["disaccordo"] = tipo
    scartate = [r.get("scartata") for r in risposte if r.get("scartata")]
    if scartate:
        out["scartate"] = scartate
    if stato.sfida:
        out["sfida"] = {"stesso_tool": stato.sfida.get("stesso_tool"),
                        "stessa_persona": stato.sfida.get("stessa_persona")}
    if stato.attivita:
        out["attivita"] = stato.attivita
    if stato.chiusa_da:
        out["chiusa_da"] = stato.chiusa_da
    if corsia.cancello:
        out["cancello"] = corsia.cancello
    if offerte > 1:
        out["proposte_risposta"] = offerte       # due domande nella stessa risposta (§ 5.2)
    if interrotta:
        out["interrotta"] = True
    return out


def istantanea(brain) -> tuple | None:
    """(proposta di oggi, chi parla, turno) prima che il ciclo decida la frase: un'uscita chiude
    la conversazione e la proposta con lei. None con lo stato del dialogo spento."""
    try:
        if modo(brain.cfg) == SPENTO:
            return None
        return (getattr(brain, "pending", None), brain._speaker_key(),
                int(getattr(brain, "turn_number", 0) or 0))
    except Exception:  # noqa: BLE001
        return None


def confronto_prima_di_brain(brain, testo: str, fase: str, foto: tuple | None) -> dict | None:
    """Una frase decisa dal ciclo **prima** di Brain (uscite, stop, cortesia, interruzione,
    cancello 2) con una proposta di oggi ancora valida per chi parla (`foto`: `istantanea`
    presa prima della fase): cosa avrebbe fatto la macchina (§ 3.3: la proposta prima delle
    uscite e dello stop). Sola lettura, o None."""
    try:
        if foto is None:
            return None
        cfg = brain.cfg
        p, chiave, turno = foto
        if not proposta_valida(p, chiave, cfg, turno):
            return None
        prop = proposta_da_oggi(p, p.get("tool"), turno, getattr(brain, "tools", None))
        sc = getattr(getattr(brain, "tool_ctx", None), "speaker_ctx", None)
        stato = StatoPersona(turno=turno, proposta=prop)
        corsia = StatoCorsia(persona=chi_da_oggi(sc, chiave, cfg),
                             cancello=2 if fase == "secondo_cancello" else None)
        forma = forma_chiusa(testo)
        dec = decidi(stato, corsia, forma)
        oggi = {"uscite": "uscita", "chiusure": "stop", "richiamo": "stop_interruzione",
                "secondo_cancello": "cancello"}.get(fase, fase)
        ok, tipo = accordo(dec["macchina"], oggi)
        out = {"proposta": _proposta_reg(prop),
               "chi": {"come": corsia.persona.come, "sicurezza": corsia.persona.sicurezza},
               "forma_chiusa": forma, "lessico": lessico_oggi(testo, prop), "modello": None,
               "diretta": False, "consenso": dec["consenso"], "macchina": dec["macchina"],
               "via": dec["via"], "oggi": oggi, "accordo": ok, "prima_di_brain": fase}
        if tipo:
            out["disaccordo"] = tipo
        return out
    except Exception:  # noqa: BLE001 — l'ombra non ferma mai il turno
        return None


# ─────────────────────────── calliope stato --turni ───────────────────────────

def riassunto(turni: list[dict]) -> dict:
    """Per giorno, dai campi `dialogo_ombra` del registro: proposte aperte, quante volte il
    modello chiama proposta_rispondi (e quante no), le chiamate scartate, la corsia veloce,
    accordo e disaccordi con la decisione di oggi per tipo."""
    giorni: dict[str, dict] = {}
    for t in turni:
        o = t.get("dialogo_ombra")
        if not isinstance(o, dict):
            continue
        g = giorni.setdefault(str(t.get("inizio") or "")[:10] or "?", {
            "turni": 0, "con_proposta": 0, "modello_chiama": 0, "modello_non_chiama": 0,
            "diretta": 0, "corsia": 0, "scartate": 0, "accordo": 0, "disaccordo": 0,
            "prima_di_brain": 0, "disaccordi": {}, "esiti_modello": {}, "consenso": {}})
        g["turni"] += 1
        p = o.get("proposta")
        if o.get("prima_di_brain"):
            g["prima_di_brain"] += 1
        if isinstance(p, dict) and p.get("tipo") == "si_no" and not o.get("prima_di_brain"):
            g["con_proposta"] += 1
            if o.get("modello"):
                g["modello_chiama"] += 1
            else:
                g["modello_non_chiama"] += 1
        if o.get("diretta"):
            g["diretta"] += 1
        if o.get("forma_chiusa"):
            g["corsia"] += 1
        g["scartate"] += len(o.get("scartate") or ())
        if o.get("modello"):
            g["esiti_modello"][o["modello"]] = g["esiti_modello"].get(o["modello"], 0) + 1
        if o.get("consenso"):
            g["consenso"][o["consenso"]] = g["consenso"].get(o["consenso"], 0) + 1
        if o.get("accordo") is True:
            g["accordo"] += 1
        elif o.get("accordo") is False:
            g["disaccordo"] += 1
            k = o.get("disaccordo") or "?"
            g["disaccordi"][k] = g["disaccordi"].get(k, 0) + 1
    return dict(sorted(giorni.items()))


def testo(r: dict) -> str:
    """La sezione per il terminale (`calliope stato --turni`)."""
    if not r:
        return "Stato del dialogo (in ombra): nessun turno con una proposta nel registro."
    righe = ["Stato del dialogo, interprete in ombra (proposte sì/no: il modello chiama "
             "proposta_rispondi? accordo con la decisione di oggi)", ""]
    for data, g in r.items():
        righe.append(f"{data}  {g['turni']} turni  proposte aperte {g['con_proposta']}: il "
                     f"modello chiama {g['modello_chiama']}, non chiama {g['modello_non_chiama']}"
                     f" (tool proposto chiamato direttamente {g['diretta']}), corsia veloce "
                     f"{g['corsia']}, scartate {g['scartate']}")
        righe.append(f"    accordo {g['accordo']}, disaccordo {g['disaccordo']}"
                     + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(
                         g["disaccordi"].items(), key=lambda x: -x[1])) + ")"
                        if g["disaccordi"] else "")
                     + (f"; decise prima di Brain {g['prima_di_brain']}"
                        if g["prima_di_brain"] else ""))
        if g["esiti_modello"] or g["consenso"]:
            righe.append("    esiti del modello: " + (", ".join(
                f"{k} {v}" for k, v in sorted(g["esiti_modello"].items())) or "—")
                + "; consenso del progetto: " + (", ".join(
                    f"{k} {v}" for k, v in sorted(g["consenso"].items())) or "—"))
    return "\n".join(righe)
