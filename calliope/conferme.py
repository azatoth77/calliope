"""
Conferme delle azioni proposte (04/10/2026): quanto resta valida una proposta, quando basta
un «sì» breve di chi amministra e la frase di sfida da ripetere.

Prova vera del 04/10 sulla DGX (26B): Dario, amministratore, chiede uno script, Calliope
propone e chiede «Procedo?». «Sì, procedi pure.» ha 0,9 s di voce, sotto la durata minima
dell'impronta: vale la conversazione, ma al più come familiare (analisi di sicurezza S4), e la
risposta era «chiedi a chi amministra», a chi amministra. Il turno dopo («Scusa, io sono chi
amministra») consumava la proposta, che valeva solo nella risposta subito dopo: un ciclo senza
uscita. Qui le tre correzioni, uguali per tutte le azioni con conferma (delega del codice,
installazioni, fatture, schermo personale, rinomina, guardia «non me l'hai chiesto»):

1. **Proposta valida per più turni** (`proposta_valida`): per la stessa persona, nei
   `azione_in_sospeso_turni` turni dopo (3) ed entro `azione_in_sospeso_s` secondi (120).
   Un'altra persona non la conferma mai (le offerte sono per persona; la conversazione si
   chiude quando cambia chi parla); una proposta nuova sostituisce la vecchia.
2. **«Sì» breve di chi amministra** (`admin_confermato`): vale se nella stessa conversazione
   chi parla è stato riconosciuto **dalla voce** come quella persona che amministra
   (`SpeakerContext.voce_sicura`: non scritto, non zona grigia) **e** l'impronta della frase
   breve non è incompatibile (punteggio contro il suo profilo ≥
   `speaker_conferma_breve_soglia`, 0,40: misura in prove/misura_conferma_breve.py, altre
   voci accettate ≤ 1,8 % stesso canale, 0 % Piper). Vale solo per il tool proposto
   (`ToolContext.tool_in_sospeso`), mai per una richiesta nuova.
3. **Frase di sfida** (`Sfida`): quando la frase non basta e chi parla è, per la
   conversazione, chi amministra (frase breve con l'impronta incerta, zona grigia, nessun
   riconoscimento sicuro nella conversazione), Calliope non dice «chiedi a chi amministra» e
   nemmeno solo «dimmelo più lungo»: chiede di ripetere tre parole comuni e un numero scelti
   in quel momento («Per conferma ripeti: girasole, treno, quarantadue»), validi
   `conferma_sfida_s` secondi. Passa se la trascrizione contiene tutte le parole (con
   tolleranza per piccoli errori di Whisper) **e** l'impronta della frase (2–3 s di voce) è di
   quella persona sopra la soglia normale. Due vantaggi: abbastanza audio per l'impronta, e
   una **prova di presenza**: una registrazione o la TV non possono contenere parole scelte un
   attimo prima. L'azione la esegue Brain (vincolo di sicurezza su un'azione già scelta dal
   modello, principio 10), regola `sfida_voce`.
"""

from __future__ import annotations

import difflib
import random
import re
import time
import unicodedata
from dataclasses import dataclass, field

# Se la frase non basta e la sfida è spenta (conferma_sfida: false)
SENTIRTI_MEGLIO = ("Per questa conferma mi serve sentirti meglio: dimmelo con una frase un po' "
                   "più lunga, per esempio «sì, procedi pure con il lavoro».")
SFIDA_MSG = "Per conferma ripeti: {testo}."
# La sfida dice sempre che cosa si conferma (05/10: «ripristina lo schermo» capito come
# «scollega» dal modello, e la sfida diceva solo «Per conferma ripeti…»: confermato senza saperlo)
SFIDA_COSA_MSG = "Per {cosa}, ripeti: {testo}."
SFIDA_PARZIALE = "Non ho sentito tutte le parole. Ripeti: {testo}."
SFIDA_VOCE_INCERTA = "Non ho riconosciuto bene la tua voce. Ripeti: {testo}."
SFIDA_ALTRA_VOCE = ("Questa conferma la può dare solo chi ha fatto la richiesta, con la sua "
                    "voce: non procedo.")
SFIDA_VOCE_FALLITA = ("Non ho riconosciuto la tua voce, quindi non procedo: chiedimelo di nuovo "
                      "più tardi.")
SFIDA_FALLITA = "Non ho sentito le parole giuste, quindi non procedo: chiedimelo di nuovo."
SFIDA_SCADUTA = "La frase di conferma è scaduta, quindi non procedo: chiedimelo di nuovo."

# Parole della sfida: nomi comuni concreti, 2–4 sillabe, facili da dire e da trascrivere,
# diversi tra loro (nessuna coppia simile), senza omofoni né parole vicine a comandi
# («basta», «esci», «stop»), al nome «Calliope» («cavallo», «calle» lo svegliavano) o a sì e no.
# Scelte con la misura del 04/10 (prove/misura_sfida.py: 60 candidate × 10 voci di Piper × 3,
# trascritte da Whisper large-v3-turbo): tenute solo quelle che il confronto ha mancato al più
# 2 volte su 30. Tolte, tra le altre: scoiattolo (10/30 mancate), fragola (9), treno (9),
# ombrello (8), farfalla (7), ciliegia (7), arcobaleno (6), mongolfiera, melograno; e cavallo.
PAROLE = (
    "girasole", "pomodoro", "castello", "foresta", "finestra", "pinguino", "carota", "delfino",
    "biscotto", "quaderno", "lanterna", "elefante", "papavero", "pennello", "cuscino", "gelato",
    "matita", "vulcano", "orologio", "tulipano", "mattone", "giraffa", "candela", "farina",
    "valigia", "tastiera", "conchiglia",
)
_UNITA = ("", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove")
_DECINE = {2: "venti", 3: "trenta", 4: "quaranta", 5: "cinquanta", 6: "sessanta",
           7: "settanta", 8: "ottanta", 9: "novanta"}


def numero_in_lettere(n: int) -> str:
    """21–99 in lettere, come si dice («ventuno», «quarantotto», «sessantatré»)."""
    d, u = divmod(int(n), 10)
    dec = _DECINE[d]
    if u in (1, 8):
        dec = dec[:-1]                      # «ventuno», «trentotto»
    return dec + ("tré" if u == 3 else _UNITA[u])


def _norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w]+", " ", t).split())


# ─────────────────────────── proposte valide per più turni ───────────────────────────

def turni_validi(cfg) -> int:
    return max(1, int(getattr(cfg, "azione_in_sospeso_turni", 3) or 1))


def secondi_validi(cfg) -> float:
    return float(getattr(cfg, "azione_in_sospeso_s", 120) or 120)


def proposta_valida(cfg, turno_proposta: int, turno: int) -> bool:
    """Il turno `turno` può confermare una proposta fatta nel turno `turno_proposta`? Mai nella
    stessa risposta (il modello non può proporre e confermare da solo), poi per
    `azione_in_sospeso_turni` turni. Il tempo lo controlla chi tiene la proposta."""
    return 1 <= int(turno) - int(turno_proposta) <= turni_validi(cfg)


# ─────────────────────────── chi conferma ───────────────────────────

def _profilo(ctx):
    sc = getattr(ctx, "speaker_ctx", None)
    name = getattr(sc, "current_speaker", None)
    speakers = getattr(ctx, "speakers", None)
    try:
        return speakers.get(name) if name and speakers is not None else None
    except Exception:  # noqa: BLE001
        return None


def e_admin(ctx) -> bool:
    """Chi parla è, per la conversazione, una persona che amministra (profilo admin)."""
    return bool(getattr(_profilo(ctx), "admin", False))


def admin_confermato(ctx) -> bool:
    """Questa frase basta per confermare un'azione di chi amministra: riconosciuto dalla voce
    in questa frase, una sfida superata, oppure un «sì» breve compatibile in una conversazione
    sicura (SpeakerContext.conferma_breve)."""
    sc = getattr(ctx, "speaker_ctx", None)
    if sc is None or not e_admin(ctx):
        return False
    if getattr(sc, "sfida_superata", False):
        return True
    how = getattr(sc, "identified_by", None)
    if how == "voce":
        return getattr(sc, "current_level", None) == "amministra"
    if how == "breve":
        return bool(getattr(sc, "conferma_breve", False))
    return False


def admin_da_sentire(ctx) -> bool:
    """Chi parla è chi amministra per la conversazione, ma questa frase non basta: frase breve
    con l'impronta incerta o senza un riconoscimento sicuro prima, oppure zona grigia."""
    sc = getattr(ctx, "speaker_ctx", None)
    return (sc is not None and e_admin(ctx)
            and getattr(sc, "identified_by", None) in ("breve", "conversazione")
            and not admin_confermato(ctx))


# ─────────────────────────── sfida ───────────────────────────

@dataclass
class Sfida:
    persona: str                     # id del profilo (o nome) di chi deve rispondere
    parole: tuple[str, ...]
    numero: int
    tool: str
    argomenti: dict = field(default_factory=dict)
    cosa: str = ""
    scade: float = 0.0
    tentativi: int = 0

    @property
    def testo(self) -> str:
        return ", ".join(self.parole + (numero_in_lettere(self.numero),))

    def scaduta(self) -> bool:
        return time.monotonic() > self.scade


def _chiave(ctx):
    prof = _profilo(ctx)
    if prof is not None:
        return getattr(prof, "id", None) or getattr(prof, "name", None)
    return getattr(getattr(ctx, "speaker_ctx", None), "current_speaker", None)


def nuova_sfida(cfg, persona, tool: str, argomenti: dict | None, cosa: str = "",
                rng: random.Random | None = None) -> Sfida:
    rng = rng or random.SystemRandom()
    n = int(getattr(cfg, "conferma_sfida_parole", 3) or 3)
    return Sfida(persona=persona, parole=tuple(rng.sample(PAROLE, max(2, min(4, n)))),
                 numero=rng.randint(21, 99), tool=tool, argomenti=dict(argomenti or {}),
                 cosa=cosa, scade=time.monotonic() + float(getattr(cfg, "conferma_sfida_s", 60)))


def _simile(a: str, b: str, soglia: float = 0.8) -> bool:
    return a == b or (len(a) >= 4 and difflib.SequenceMatcher(None, a, b).ratio() >= soglia)


def _parola_detta(parola: str, parole: list[str]) -> bool:
    """La parola è nella frase trascritta, anche con un piccolo errore («girasoli») o spezzata
    in due da Whisper («far falla», «piano forte»)."""
    w = _norm(parola)
    coppie = [a + b for a, b in zip(parole, parole[1:])]
    return any(_simile(p, w) for p in parole + coppie)


def _numero_detto(numero: int, testo: str) -> bool:
    """Il numero, in cifre («42») o in lettere, anche spezzato («quaranta due», «venti tre»)."""
    t = _norm(testo)
    if str(int(numero)) in re.findall(r"\d+", t):
        return True
    lett = _norm(numero_in_lettere(numero))
    parole = t.split()
    coppie = [a + b for a, b in zip(parole, parole[1:])]
    return lett in t.replace(" ", "") or any(_simile(p, lett, 0.85) for p in parole + coppie)


def confronta(sfida: Sfida, testo: str) -> str:
    """"ok" se nella frase ci sono tutte le parole e il numero (in cifre o in lettere, con
    piccoli errori di trascrizione), "parziale" se almeno metà, "no" altrimenti."""
    parole = _norm(testo).split()
    trovate = sum(_parola_detta(w, parole) for w in sfida.parole)
    trovate += _numero_detto(sfida.numero, testo)
    totale = len(sfida.parole) + 1
    if trovate == totale:
        return "ok"
    return "parziale" if trovate * 2 >= totale else "no"


def chiedi_conferma(ctx, tool: str, argomenti: dict | None, cosa: str) -> dict:
    """Il risultato da dare quando chi amministra non basta in questa frase: la sfida (o,
    spenta, la frase «mi serve sentirti meglio»). Mai «chiedi a chi amministra»."""
    from .tools.spec import note_rule
    cfg = getattr(ctx, "cfg", None)
    sc = getattr(ctx, "speaker_ctx", None)
    if not getattr(cfg, "conferma_sfida", True) or sc is None:
        note_rule(ctx, "conferma_sentirti_meglio")
        return {"ok": False, "fatto": "NIENTE: l'azione NON è stata eseguita: serve la voce",
                "conferma": SENTIRTI_MEGLIO, "risposta_finale": SENTIRTI_MEGLIO}
    chi = _chiave(ctx)
    s = getattr(sc, "sfida", None)
    if (s is None or s.scaduta() or s.persona != chi or s.tool != tool
            or s.argomenti != dict(argomenti or {})):
        s = nuova_sfida(cfg, chi, tool, argomenti, cosa)
        sc.sfida = s
    descr = (cosa or s.cosa or descrivi_azione(tool, argomenti)).strip().rstrip(".")
    frase = (SFIDA_COSA_MSG.format(cosa=descr, testo=s.testo) if descr
             else SFIDA_MSG.format(testo=s.testo))
    note_rule(ctx, "sfida_voce")
    return {"ok": False, "fatto": "NIENTE: l'azione NON è stata eseguita: chiedo la frase di "
                                  "conferma", "conferma": frase, "risposta_finale": frase}


def descrivi_azione(tool: str, argomenti: dict | None) -> str:
    """Una descrizione breve dell'azione da confermare quando il tool non ne dà una:
    «confermare schermo gestisci: scollega, studio» (meglio di niente: si capisce cosa)."""
    args = dict(argomenti or {})
    valori = [str(v) for k, v in args.items()
              if isinstance(v, (str, int, float)) and str(v).strip() and len(str(v)) <= 60]
    nome = tool.replace("_", " ")
    return f"confermare {nome}" + (f": {', '.join(valori[:4])}" if valori else "")


def serve_conferma(ctx, tool: str, argomenti: dict | None, cosa: str) -> dict | None:
    """Il risultato da dare se chi parla è chi amministra ma questa frase non basta per
    `tool` (sfida, la stessa se per quel tool ce n'è già una in corso); None altrimenti (frase
    sufficiente, oppure chi parla non amministra: vale il rifiuto di sempre). Una frase
    riconosciuta dalla voce dopo la sfida vale come sempre: la sfida serve quando la voce è
    incerta, e chiederla anche dopo porterebbe solo turni in più."""
    if admin_da_sentire(ctx):
        return chiedi_conferma(ctx, tool, argomenti, cosa)
    return None
