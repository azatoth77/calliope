"""
Modalità sviluppo (08/10/2026, docs/ricerche/2026-10-08-modalita-sviluppo.md).

Per chi amministra lo sviluppo di un'estensione (o di un programma) è uno **stato** con fasi,
invece di frasi sparse nella conversazione normale:

    analisi → sviluppo e test → collaudo → revisione → attivazione   (estensione)
    analisi → sviluppo e test → collaudo → revisione                 (programma)

- uno sviluppo è legato alla richiesta che l'ha aperto (quell'estensione, quel programma) e
  alla persona; uno aperto per persona, le sospese possono essere più d'una;
- da qualunque fase si torna all'analisi (`sviluppo(analisi, cambia)` in tools/sviluppo.py);
- il modello lo vede nei dati del turno (`dati_turno`, Brain: SVILUPPO_MSG); le transizioni le
  fa il codice quando un tool riesce (proposta, avvio, lavoro finito, avanti, approvazione);
- dopo `sviluppo_sospendi_min` minuti senza parlarne si sospende (non mentre l'agente lavora),
  e una volta al giorno chi amministra sente quali sono sospesi (`promemoria_giorno`);
- stato su disco (`sviluppi.json` accanto a `in_corso.json` dei lavori): sopravvive ai
  riavvii.

Qui solo lo stato e le frasi; i tool sono in calliope/tools/sviluppo.py, la sicurezza dei passi
interni in politica.controlla (regola `sviluppo_intento`). Solo libreria standard.
"""

from __future__ import annotations

import datetime
import difflib
import re
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

FILE = "sviluppi.json"
FASI_ESTENSIONE = ("analisi", "sviluppo", "collaudo", "revisione", "attivazione")
FASI_PROGRAMMA = ("analisi", "sviluppo", "collaudo", "revisione")
NOMI = {"analisi": "analisi", "sviluppo": "sviluppo e test", "collaudo": "collaudo",
        "revisione": "revisione", "attivazione": "attivazione"}
ALLA = {"analisi": "all'analisi", "sviluppo": "allo sviluppo", "collaudo": "al collaudo",
        "revisione": "alla revisione", "attivazione": "all'attivazione"}
MAX_COLLAUDI = 20
MAX_STORIA = 60
TENUTA_CHIUSE_S = 30 * 86400
# I tool che fanno parte di uno sviluppo: una risposta che ne usa uno è «parlarne»
TOOL_SVILUPPO = frozenset({"sviluppo", "sviluppo_prova", "estensione_crea", "delega_lavoro",
                           "estensioni_gestisci", "lavori_esegui", "lavori_rispondi",
                           "lavori_stato", "lavori_annulla", "risultato_lavoro"})


def _oggi() -> str:
    return datetime.date.today().isoformat()


def _ora(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def _e(cose: list[str]) -> str:
    cose = [c for c in cose if c]
    if len(cose) <= 1:
        return "".join(cose)
    return ", ".join(cose[:-1]) + " e " + cose[-1]


@dataclass
class Sviluppo:
    id: str
    persona: str
    persona_nome: str = ""
    tipo: str = "estensione"          # «estensione» o «programma»
    titolo: str = ""
    richiesta: str = ""               # la richiesta come detta, la prima volta
    specifica: str = ""               # la specifica confermata (o proposta)
    fase: str = "analisi"
    stato: str = "aperta"             # aperta, sospesa, chiusa
    motivo: str = ""                  # perché è chiusa o sospesa
    lavoro: str | None = None         # il lavoro dell'agente (in corso o finito)
    proposto: str | None = None       # il lavoro proposto, in attesa del «sì»
    cartella: str = ""                # la cartella dei risultati del lavoro
    estensione: str | None = None     # il nome interno dell'estensione
    versione: int | None = None       # la versione candidata
    gioco: bool = False
    da_programma: str = ""            # la cartella del programma da cui nasce (promuovi)
    collaudi: list = field(default_factory=list)
    storia: list = field(default_factory=list)
    revisione: str = ""               # il testo della revisione (per la scheda)
    nota: str = ""                    # l'ultimo evento del lavoro detto (un errore)
    aperta: float = 0.0
    ultimo: float = 0.0
    chiusa: float | None = None
    proposta_estensione: bool = False  # la proposta di farne un'estensione è già stata fatta

    def fasi(self) -> tuple[str, ...]:
        return FASI_PROGRAMMA if self.tipo == "programma" else FASI_ESTENSIONE

    def cosa(self) -> str:
        if self.tipo == "programma":
            return "il programma"
        return "il gioco" if self.gioco else "l'estensione"

    def di(self) -> str:
        """«di «Meteo per città»», per «lo sviluppo di …»."""
        return f"di «{self.titolo}»"

    def numero_fase(self) -> int:
        try:
            return self.fasi().index(self.fase) + 1
        except ValueError:
            return 1

    def fatte(self) -> list[str]:
        return list(self.fasi()[: self.numero_fase() - 1])

    def mancano(self) -> list[str]:
        return list(self.fasi()[self.numero_fase():])


class Sviluppi:
    """Gli sviluppi di tutti, su disco. Thread: la voce (tool e Brain) e il thread dei lavori
    (lavoro_finito); un lock solo, mai preso durante una rete."""

    def __init__(self, cfg, cartella, lavori=None, log=print):
        self.cfg = cfg
        self.lavori = lavori
        self.log = log
        self.percorso = Path(cartella) / FILE
        self._lock = threading.RLock()
        self.sviluppi: list[Sviluppo] = []
        self.ricordati: dict[str, str] = {}
        self._n = 0
        # La cartella di un programma che diventa estensione, per la modalità che si apre subito
        # dopo (tools/sviluppo.py: promuovi → estensione_crea)
        self.da_programma: dict = {}
        self.sospendi_s = max(0.0, float(getattr(cfg, "sviluppo_sospendi_min", 30.0) or 0)) * 60
        self._carica()

    # ─────────────────────────── disco ───────────────────────────
    def _carica(self):
        from .persistenza import FileRovinato, leggi_json
        try:
            dati, _ = leggi_json(self.percorso)
        except FileRovinato as e:
            self.log(f"[SVILUPPO] {self.percorso.name} illeggibile: {e}: riparto senza")
            dati = None
        if not isinstance(dati, dict):
            return
        nomi = {f.name for f in fields(Sviluppo)}
        adesso = time.time()
        for d in dati.get("sviluppi") or []:
            if not isinstance(d, dict) or not d.get("id") or not d.get("persona"):
                continue
            sv = Sviluppo(**{k: v for k, v in d.items() if k in nomi})
            if sv.stato == "chiusa" and adesso - float(sv.chiusa or 0) > TENUTA_CHIUSE_S:
                continue
            if sv.stato != "chiusa" and sv.fase == "sviluppo" and sv.lavoro:
                # Il lavoro dell'agente non sopravvive a un riavvio (agenti/ripresa.py: diventa
                # «interrotto», e gli id dei lavori ripartono): lo sviluppo resta allo sviluppo,
                # senza lavoro, e lo dice; un lavoro rifatto si riconosce dal titolo
                sv.lavoro, sv.nota = None, "interrotto da un riavvio di Calliope"
            sv.proposto = None                # le proposte non sopravvivono a un riavvio
            self.sviluppi.append(sv)
        self.ricordati = {str(k): str(v) for k, v in (dati.get("ricordati") or {}).items()}
        self._n = max([int(dati.get("n") or 0)] + [int(re.sub(r"\D", "", s.id) or 0)
                                                   for s in self.sviluppi])

    def _salva(self):
        from .persistenza import scrivi_json
        with self._lock:
            dati = {"n": self._n, "ricordati": dict(self.ricordati),
                    "sviluppi": [asdict(s) for s in self.sviluppi]}
        try:
            self.percorso.parent.mkdir(parents=True, exist_ok=True)
            scrivi_json(self.percorso, dati)
        except OSError as e:
            self.log(f"[SVILUPPO] stato non salvato: {e}")

    # ─────────────────────────── chi e quale ───────────────────────────
    def _lavoro(self, ident):
        """Il lavoro (agenti/servizio.Lavoro) con questo id, o None."""
        if not ident or self.lavori is None:
            return None
        try:
            return next((lv for lv in list(getattr(self.lavori, "lavori", None) or ())
                         if lv.id == ident), None)
        except Exception:  # noqa: BLE001
            return None

    def lavoro_attivo(self, sv: Sviluppo) -> bool:
        """L'agente sta lavorando per questo sviluppo (in coda o in corso)."""
        lv = self._lavoro(sv.lavoro)
        return lv is not None and getattr(lv, "stato", "") in ("in_coda", "in_corso")

    def _da_sospendere(self, sv: Sviluppo) -> bool:
        return (self.sospendi_s > 0 and time.time() - float(sv.ultimo or sv.aperta or 0)
                > self.sospendi_s and not self.lavoro_attivo(sv))

    def corrente(self, persona) -> Sviluppo | None:
        """Lo sviluppo aperto di `persona`, o None. Dopo `sviluppo_sospendi_min` minuti senza
        parlarne si sospende qui (pigro: nessun thread)."""
        if persona is None:
            return None
        with self._lock:
            sv = next((s for s in self.sviluppi if s.persona == persona and s.stato == "aperta"),
                      None)
            if sv is not None and self._da_sospendere(sv):
                self._cambia_stato(sv, "sospesa", "trenta minuti senza parlarne")
                self.log(f"[SVILUPPO] {sv.id} «{sv.titolo}» sospeso: "
                         f"{int(self.sospendi_s // 60)} minuti senza parlarne")
                self._salva()
                return None
            return sv

    def sospesi(self, persona) -> list[Sviluppo]:
        with self._lock:
            self.corrente(persona)          # una scadenza appena passata conta già
            return [s for s in self.sviluppi if s.persona == persona and s.stato == "sospesa"]

    def trova(self, persona, quale: str = "", stati=("sospesa",)) -> list[Sviluppo]:
        """Gli sviluppi di `persona` negli `stati`, quello detto per primo: per id («S2») o
        parole del titolo («il meteo»), altrimenti dal più recente."""
        with self._lock:
            tutti = [s for s in self.sviluppi if s.persona == persona and s.stato in stati]
        tutti.sort(key=lambda s: -float(s.ultimo or 0))
        q = str(quale or "").strip().lower()
        if not q or not tutti:
            return tutti
        if re.fullmatch(r"s\d+", q):
            return [s for s in tutti if s.id.lower() == q] or tutti

        def parole(t):
            return {w for w in re.findall(r"[a-zà-ù0-9]{3,}", t.lower())
                    if w not in ("sviluppo", "estensione", "programma", "della", "dello")}
        qp = parole(q)

        def punti(s):
            tp = parole(f"{s.titolo} {s.estensione or ''}")
            comuni = sum(1 for w in qp if any(w[:5] == x[:5] for x in tp))
            return comuni + difflib.SequenceMatcher(None, q, s.titolo.lower()).ratio()
        return sorted(tutti, key=punti, reverse=True)

    def di_lavoro(self, ident, persona=None) -> Sviluppo | None:
        """Lo sviluppo (non chiuso) del lavoro `ident`, o di quello proposto."""
        if not ident:
            return None
        with self._lock:
            return next((s for s in self.sviluppi if s.stato != "chiusa"
                         and ident in (s.lavoro, s.proposto)
                         and (persona is None or s.persona == persona)), None)

    def dell_estensione(self, nome) -> Sviluppo | None:
        if not nome:
            return None
        with self._lock:
            return next((s for s in self.sviluppi if s.stato != "chiusa"
                         and s.estensione == nome), None)

    # ─────────────────────────── transizioni ───────────────────────────
    def apri(self, persona, persona_nome: str, tipo: str, richiesta: str, titolo: str = "",
             gioco: bool = False, estensione: str | None = None) -> Sviluppo:
        with self._lock:
            self._n += 1
            adesso = time.time()
            sv = Sviluppo(f"S{self._n}", persona, persona_nome or "", tipo,
                          titolo=(titolo or richiesta or "sviluppo")[:80],
                          richiesta=str(richiesta or "")[:600], aperta=adesso, ultimo=adesso,
                          gioco=bool(gioco), estensione=estensione)
            sv.da_programma = str(self.da_programma.pop(persona, "") or "")
            sv.storia.append({"quando": adesso, "a": "analisi", "perche": "aperto"})
            self.sviluppi.append(sv)
        self.log(f"[SVILUPPO] {sv.id} aperto: {tipo} «{sv.titolo}» per {persona_nome or persona}")
        self._salva()
        return sv

    def tocca(self, sv: Sviluppo):
        """Se ne è parlato adesso (il conto dei minuti per la sospensione riparte)."""
        sv.ultimo = time.time()
        self._salva()

    def passa(self, sv: Sviluppo, fase: str, perche: str = ""):
        with self._lock:
            if fase != sv.fase:
                sv.storia.append({"quando": time.time(), "da": sv.fase, "a": fase,
                                  "perche": str(perche or "")[:160]})
                sv.storia = sv.storia[-MAX_STORIA:]
                self.log(f"[SVILUPPO] {sv.id} «{sv.titolo}»: {sv.fase} → {fase}"
                         + (f" ({perche})" if perche else ""))
            sv.fase = fase
            sv.ultimo = time.time()
        self._salva()

    def _cambia_stato(self, sv: Sviluppo, stato: str, motivo: str):
        sv.storia.append({"quando": time.time(), "stato": stato, "perche": motivo})
        sv.storia = sv.storia[-MAX_STORIA:]
        sv.stato, sv.motivo = stato, motivo
        if stato == "chiusa":
            sv.chiusa = time.time()

    def sospendi(self, sv: Sviluppo, motivo: str = "chiesto"):
        with self._lock:
            self._cambia_stato(sv, "sospesa", motivo)
        self.log(f"[SVILUPPO] {sv.id} «{sv.titolo}» sospeso ({motivo})")
        self._salva()

    def riprendi(self, sv: Sviluppo) -> Sviluppo | None:
        """Riapre `sv`; restituisce quello che era aperto (ora sospeso) o None."""
        with self._lock:
            prima = next((s for s in self.sviluppi if s.persona == sv.persona
                          and s.stato == "aperta" and s is not sv), None)
            if prima is not None:
                self._cambia_stato(prima, "sospesa", f"ripreso {sv.id}")
            self._cambia_stato(sv, "aperta", "ripreso")
            sv.ultimo = time.time()
        self.log(f"[SVILUPPO] {sv.id} «{sv.titolo}» ripreso")
        self._salva()
        return prima

    def chiudi(self, sv: Sviluppo, motivo: str):
        with self._lock:
            self._cambia_stato(sv, "chiusa", motivo)
        self.log(f"[SVILUPPO] {sv.id} «{sv.titolo}» chiuso ({motivo})")
        self._salva()

    # ─────────────────────────── eventi dei lavori ───────────────────────────
    def proposto(self, lav) -> Sviluppo | None:
        """Un lavoro proposto («Procedo?») per lo sviluppo aperto di chi l'ha chiesto, in
        analisi: la specifica è quella che la persona sta per confermare."""
        sv = self.corrente(getattr(lav, "persona", None))
        if sv is None or sv.fase != "analisi" or not self._stesso_tipo(sv, lav):
            return None
        with self._lock:
            sv.proposto = lav.id
            spec = str(getattr(lav, "specifica", "") or "").strip()
            sv.specifica = (spec or str(getattr(lav, "compito", "") or "")).strip()[:1200]
            if getattr(lav, "estensione", None):
                sv.estensione = lav.estensione
            titolo = str(getattr(lav, "titolo", "") or "").strip()
            if titolo and (not sv.titolo or sv.titolo == sv.richiesta[:80]):
                sv.titolo = titolo[:80]
            sv.ultimo = time.time()
            if sv.da_programma and getattr(lav, "tipo", "") == "estensione":
                self._file_del_programma(sv, lav)
        self._salva()
        return sv

    def avviato(self, lav) -> Sviluppo | None:
        """Il lavoro è partito (il «sì» alla specifica): fase sviluppo."""
        persona = getattr(lav, "persona", None)
        sv = self.di_lavoro(lav.id, persona) or self.corrente(persona)
        if sv is None or sv.stato != "aperta" or not self._stesso_tipo(sv, lav) or \
                sv.fase not in ("analisi", "sviluppo"):
            return None
        with self._lock:
            sv.lavoro, sv.proposto, sv.nota = lav.id, None, ""
            if not sv.specifica:
                sv.specifica = str(getattr(lav, "specifica", "") or getattr(lav, "compito", "")
                                   or "")[:1200]
            titolo = str(getattr(lav, "titolo", "") or "").strip()
            if titolo:
                sv.titolo = titolo[:80]
            if getattr(lav, "estensione", None):
                sv.estensione = lav.estensione
            if sv.da_programma and getattr(lav, "tipo", "") == "estensione":
                self._file_del_programma(sv, lav)
        self.passa(sv, "sviluppo", f"lavoro {lav.id}")
        return sv

    @staticmethod
    def _stesso_tipo(sv: Sviluppo, lav) -> bool:
        tipo = getattr(lav, "tipo", "")
        return (sv.tipo == "estensione" and tipo == "estensione") or (
            sv.tipo == "programma" and tipo == "codice")

    def _file_del_programma(self, sv: Sviluppo, lav):
        """Il programma da cui nasce l'estensione (promuovi): i suoi file nella cartella
        dell'agente, sotto programma/, e un vincolo che lo dice. Una volta."""
        file = file_di_codice(sv.da_programma)
        if not file:
            return
        iniziali = dict(getattr(lav, "file_iniziali", None) or {})
        for k, v in file.items():
            iniziali.setdefault(f"programma/{k}", v)
        lav.file_iniziali = iniziali
        lav.vincoli = ((getattr(lav, "vincoli", "") or "") + " Nasce dal programma che c'è "
                       "nella cartella programma/: riusane la logica (le sue funzioni, i "
                       "test), adattandola a esegui(dati, calliope).").strip()
        sv.da_programma = ""

    def lavoro_finito(self, lav, item: dict) -> dict:
        """L'annuncio di un lavoro di uno sviluppo (dal thread dei lavori, Lavori._annuncia):
        la fase cambia e la frase dice dove siamo. Restituisce l'annuncio (cambiato)."""
        sv = self.di_lavoro(getattr(lav, "id", None), getattr(lav, "persona", None))
        if sv is None:
            sv = self._rifatto(lav)
        if sv is None:
            return item
        stato = getattr(lav, "stato", "")
        r = getattr(lav, "risultato", None) or {}
        msg = str(item.get("messaggio") or "")
        if stato == "in_attesa":
            return item                      # una domanda dell'agente: si risponde e basta
        if stato == "annullato":
            if sv.fase == "analisi":
                return item                  # fermato per tornare all'analisi: già detto
            with self._lock:
                sv.lavoro, sv.nota = None, "annullato"
            self._salva()
            return item
        if stato == "fatto":
            with self._lock:
                sv.cartella = str(r.get("cartella") or sv.cartella or "")
                c = r.get("estensione") or {}
                if sv.tipo == "estensione" and c.get("nome"):
                    sv.estensione, sv.versione = c["nome"], c.get("versione")
                    # Il titolo dell'estensione, quello che dicono annuncio, elenco e revisione
                    # (prima il nome dato alla richiesta: «MeteoSì» e «Meteo per città»)
                    titolo = self._titolo_estensione(sv.estensione, sv.versione)
                    if titolo:
                        sv.titolo = titolo[:80]
                sv.nota = ""
            self.passa(sv, "collaudo", f"lavoro {lav.id} finito")
            msg = re.sub(r"\s*Vuoi approvarla\?\s*$", ".", msg).rstrip()
            msg = re.sub(r"\.\.$", ".", msg)
            if sv.tipo == "estensione":
                if (r.get("estensione") or {}).get("in_sospeso"):
                    riga = (f" Siamo al collaudo: la versione {sv.versione or 'nuova'} non è "
                            "ancora attiva, e prima di approvarla la puoi provare. Dimmi per "
                            "esempio «prova con…» e i dati.")
                else:
                    riga = (" Siamo al collaudo: puoi provarla lo stesso, oppure dirmi cosa "
                            "correggere.")
                # Niente «Vuoi approvarla?» in sospeso: prima si prova
                item.pop("in_sospeso", None)
            else:
                riga = (" Siamo al collaudo: puoi provarlo con dati tuoi, per esempio «provalo "
                        "con…»; quando va bene, dimmi di andare avanti.")
            if sv.stato == "sospesa":
                riga = (f" Lo sviluppo {sv.di()} è sospeso: quando vuoi, dimmi «riprendiamo lo "
                        f"sviluppo»; saremo al collaudo.")
            item["messaggio"] = msg.rstrip() + riga
            item["sviluppo"] = sv.id
            self._manda_scheda(sv, getattr(lav, "on_scheda", None))
            return item
        # errore, scaduto, fermato da un tetto: lo sviluppo resta, senza lavoro
        with self._lock:
            sv.nota = str(r.get("motivo") or stato or "non riuscito")[:200]
            sv.lavoro = None
        self._salva()
        item["messaggio"] = (msg.rstrip() + f" Lo sviluppo {sv.di()} resta aperto: se vuoi, "
                             "torniamo all'analisi e cambiamo qualcosa, oppure lo rifaccio.")
        item["sviluppo"] = sv.id
        return item

    def _rifatto(self, lav) -> Sviluppo | None:
        """Lo sviluppo, rimasto allo sviluppo senza lavoro (un riavvio), di un lavoro rifatto
        dopo «Lo rifaccio?» (agenti/ripresa.py): stessa persona, stesso tipo, stessa estensione
        o stesso titolo."""
        persona = getattr(lav, "persona", None)
        with self._lock:
            for sv in self.sviluppi:
                if sv.persona != persona or sv.stato == "chiusa" or sv.fase != "sviluppo"                         or sv.lavoro or not self._stesso_tipo(sv, lav):
                    continue
                stessa = (sv.estensione and getattr(lav, "estensione", None) == sv.estensione)
                if stessa or str(getattr(lav, "titolo", "")).strip() == sv.titolo:
                    sv.lavoro = lav.id
                    return sv
        return None

    def estensione_approvata(self, nome: str, n) -> Sviluppo | None:
        """L'estensione dello sviluppo è stata approvata (Estensioni._approva): l'iter è finito
        e lo sviluppo si chiude."""
        sv = self.dell_estensione(nome)
        if sv is None:
            return None
        self.passa(sv, "attivazione", f"versione {n} approvata")
        self.chiudi(sv, "attivata")
        return sv

    # ─────────────────────────── frasi ───────────────────────────
    def dove(self, sv: Sviluppo) -> str:
        """«siamo al collaudo (3 di 5): fatte analisi e sviluppo e test; mancano revisione e
        attivazione»."""
        fatte, mancano = sv.fatte(), sv.mancano()
        out = f"siamo {ALLA.get(sv.fase, sv.fase)} ({sv.numero_fase()} di {len(sv.fasi())})"
        parti = []
        if fatte:
            parti.append(("fatta " if len(fatte) == 1 else "fatte ")
                         + _e([NOMI[f] for f in fatte]))
        if mancano:
            parti.append(("manca " if len(mancano) == 1 else "mancano ")
                         + _e([NOMI[f] for f in mancano]))
        return out + (": " + "; ".join(parti) if parti else "")

    def riga_fuori_tema(self, sv: Sviluppo) -> str:
        return f"Intanto restiamo sullo sviluppo {sv.di()}: siamo {ALLA.get(sv.fase, sv.fase)}."

    def promemoria_giorno(self, persona) -> str | None:
        """Gli sviluppi sospesi di chi amministra, una volta al giorno (alla prima risposta del
        giorno che lo permette: Brain), o None. Non segna niente: lo fa `ricordato`."""
        if not getattr(self.cfg, "sviluppo_promemoria", True) or persona is None:
            return None
        if self.ricordati.get(str(persona)) == _oggi():
            return None
        sospesi = self.sospesi(persona)
        if not sospesi:
            return None
        if len(sospesi) == 1:
            sv = sospesi[0]
            return (f"A proposito: lo sviluppo {sv.di()} è sospeso, eravamo "
                    f"{ALLA.get(sv.fase, sv.fase)}. Quando vuoi, dimmi «riprendiamo lo sviluppo "
                    f"di {sv.titolo[:1].lower() + sv.titolo[1:]}».")
        voci = [f"«{s.titolo}» ({ALLA.get(s.fase, s.fase)})" for s in sospesi[:4]]
        return (f"A proposito: hai {len(sospesi)} sviluppi sospesi: {_e(voci)}. Quando vuoi, "
                f"dimmi quale riprendere.")

    def ricordato(self, persona):
        with self._lock:
            self.ricordati[str(persona)] = _oggi()
        self._salva()

    def riga_fase(self, sv: Sviluppo) -> str:
        """La riga dei dati del turno che dice al modello cosa si fa in questa fase."""
        if sv.fase == "analisi":
            if sv.proposto:
                return ("La specifica è stata proposta (lavoro " + sv.proposto + "): se chi parla "
                        "la conferma («sì», «va bene»), richiama il tool come dice la domanda in "
                        "sospeso; se vuole cambiarla, sviluppo con azione analisi e cambia = la "
                        "modifica.")
            return ("Si sta scrivendo la specifica: se chi parla risponde a una domanda di "
                    "Calliope, richiama il tool che l'ha fatta come dice la domanda in sospeso.")
        if sv.fase == "sviluppo":
            if self.lavoro_attivo(sv):
                return (f"L'agente sta lavorando (lavoro {sv.lavoro}): se chiede a che punto è, "
                        "sviluppo con azione stato.")
            return (f"Il lavoro dell'agente non è andato ({sv.nota or 'si è fermato'}): se vuole "
                    "riprovare o cambiare qualcosa, sviluppo con azione analisi.")
        if sv.fase == "collaudo":
            if sv.tipo == "programma":
                return ("Il programma è pronto: se chiede di provarlo («provalo con 3 e 5»), "
                        "chiama sviluppo_prova con dati = i dati come detti. Se dice che va bene "
                        "o di andare avanti, sviluppo con azione avanti (la revisione).")
            return (f"La versione {sv.versione or 'nuova'} è pronta ma NON è ancora attiva: si "
                    "prova prima di approvarla. Se chiede di provarla («prova con Bergamo», "
                    "«prova una città che non esiste»), chiama sviluppo_prova con dati = i dati "
                    "come detti" + self._input_detto(sv) + "; NON il suo tool est_ né "
                    "internet. Se dice che va bene o di andare avanti, sviluppo con azione "
                    "avanti (la revisione).")
        if sv.fase == "revisione":
            if sv.tipo == "programma":
                return ("Hai detto la revisione del programma. Se dice che va bene, sviluppo "
                        "con azione avanti (chiude lo sviluppo); se vuole farne un'estensione, "
                        "sviluppo con azione promuovi.")
            return ("Hai detto la revisione (permessi, rete, analisi del codice, differenze). "
                    "Se dice di attivarla o che va bene, sviluppo con azione avanti: chiederà la "
                    "frase di conferma. Può ancora provarla con sviluppo_prova.")
        return ("Manca la frase di conferma per approvarla: se chiede di attivarla, sviluppo "
                "con azione avanti.")

    def _titolo_estensione(self, nome, n) -> str:
        arch = getattr(getattr(self.lavori, "estensioni", None), "archivio", None)
        if arch is None or not nome:
            return ""
        try:
            return str((arch.manifesto(nome, n) or {}).get("titolo") or "")
        except Exception:  # noqa: BLE001
            return ""

    def _input_detto(self, sv: Sviluppo) -> str:
        est = getattr(getattr(self.lavori, "estensioni", None), "archivio", None)
        if est is None or not sv.estensione:
            return ""
        try:
            n = est.candidata(sv.estensione) or (est.voce(sv.estensione) or {}).get("attiva")
            m = est.manifesto(sv.estensione, n) or {}
            nomi = sorted((m.get("input") or {}).get("properties") or {})
        except Exception:  # noqa: BLE001 — sono solo dati del turno
            return ""
        return f" (input: {', '.join(nomi)})" if nomi else ""

    def dati_turno(self, sv: Sviluppo) -> str:
        spec = re.sub(r"\s+", " ", sv.specifica or sv.richiesta or "da definire").strip()
        return SVILUPPO_MSG.format(cosa=sv.cosa(), titolo=sv.titolo, id=sv.id,
                                   dove=self.dove(sv), spec=spec[:600].rstrip("."),
                                   riga=self.riga_fase(sv), alla=ALLA.get(sv.fase, sv.fase))

    def dati_sospesi(self, persona) -> str | None:
        sospesi = self.sospesi(persona)
        if not sospesi:
            return None
        voci = [f"«{s.titolo}» ({s.id}, {ALLA.get(s.fase, s.fase)})" for s in sospesi[:4]]
        return SOSPESI_MSG.format(voci=_e(voci))

    # ─────────────────────────── scheda ───────────────────────────
    def testo_scheda(self, sv: Sviluppo) -> str:
        """La scheda dello sviluppo in Markdown (il lettore della pagina, senza JavaScript
        nuovo): fasi, specifica, collaudi, revisione, cosa manca."""
        righe = [f"# Sviluppo: {sv.titolo}", "",
                 f"{sv.cosa()[0].upper() + sv.cosa()[1:]} · {sv.id} · "
                 + {"aperta": "aperto", "sospesa": "sospeso", "chiusa": "chiuso"}.get(
                     sv.stato, sv.stato) + (f" ({sv.motivo})" if sv.stato != "aperta"
                                            and sv.motivo else ""), "", "## Fasi", ""]
        k = sv.numero_fase()
        for i, f in enumerate(sv.fasi(), 1):
            if (sv.stato == "chiusa" and sv.motivo == "attivata") or i < k:
                righe.append(f"- fatta: {NOMI[f]}")
            elif i == k:
                righe.append(f"- **adesso: {NOMI[f]}**")
            else:
                righe.append(f"- manca: {NOMI[f]}")
        righe += ["", "## Specifica", "", sv.specifica or sv.richiesta or "da definire"]
        if sv.collaudi:
            righe += ["", "## Collaudi", ""]
            for c in sv.collaudi[-10:]:
                dati = c.get("dati") or "senza dati"
                righe.append(f"- {_ora(float(c.get('quando') or 0))}, «{dati}»: "
                             f"{'riuscito' if c.get('ok') else 'non riuscito'}"
                             + (f" — {c['esito']}" if c.get("esito") else ""))
        if sv.revisione:
            righe += ["", "## Revisione", "", sv.revisione]
        if sv.nota and sv.fase == "sviluppo":
            righe += ["", f"Il lavoro dell'agente non è andato: {sv.nota}."]
        if sv.stato != "chiusa":
            righe += ["", "## Cosa si può dire", "", *[f"- {x}" for x in self._esempi(sv)]]
        return "\n".join(righe)

    @staticmethod
    def _esempi(sv: Sviluppo) -> list[str]:
        out = []
        if sv.fase == "collaudo":
            out.append("«prova con…» e i dati, per provarla" if sv.tipo == "estensione"
                       else "«provalo con…» e i dati")
            out.append("«va bene, andiamo avanti», per la revisione")
        elif sv.fase == "revisione":
            out.append("«attivala»" if sv.tipo == "estensione" else "«va bene così»")
        elif sv.fase == "attivazione":
            out.append("«attivala», e la frase di conferma")
        out += ["«cambia…», per tornare all'analisi", "«sospendi lo sviluppo»",
                "«esci dallo sviluppo»"]
        return out

    def scheda(self, sv: Sviluppo) -> dict:
        from .schermi import schede
        return schede.documento_markdown(f"Sviluppo: {sv.titolo}", self.testo_scheda(sv),
                                         chiave=f"sviluppo:{sv.id}",
                                         stato=sv.fase if sv.stato == "aperta" else sv.stato)

    def _manda_scheda(self, sv: Sviluppo, on_scheda):
        if on_scheda is None:
            return
        try:
            on_scheda(self.scheda(sv))
        except Exception as e:  # noqa: BLE001 — lo schermo non ferma niente
            self.log(f"[SVILUPPO] scheda non inviata: {type(e).__name__}: {e}")

    def collaudo(self, sv: Sviluppo, dati: str, ok: bool, esito: str):
        with self._lock:
            sv.collaudi.append({"quando": time.time(), "dati": str(dati or "")[:120],
                                "ok": bool(ok), "esito": re.sub(r"\s+", " ", str(esito or ""))
                                .strip()[:200]})
            sv.collaudi = sv.collaudi[-MAX_COLLAUDI:]
            sv.ultimo = time.time()
        self._salva()


# Dati del turno (Brain): la modalità e la fase, prima della domanda. Un contesto: decide il
# modello (principio 10); le transizioni le fa il codice
SVILUPPO_MSG = ("Modalità sviluppo aperta con chi parla (dati del turno, non ripeterli): "
                "{cosa} «{titolo}» ({id}); {dove}. Specifica: {spec}. {riga} Se chiede di "
                "cambiare cosa deve fare, in qualunque fase: sviluppo con azione analisi e "
                "cambia = la modifica come detta. Se chiede altro (l'ora, il meteo, la casa, le "
                "liste…), rispondi come sempre con i tuoi tool e chiudi con una frase breve che "
                "ricorda che siete {alla} di «{titolo}». Niente sviluppi nuovi (estensioni, "
                "programmi, lavori dell'agente) finché questo è aperto. Per fermarsi: sviluppo "
                "con azione sospendi (si riprende quando vuole) o esci (lo chiude).")
SOSPESI_MSG = ("Dati del turno: chi parla ha degli sviluppi sospesi: {voci}. Se chiede di "
               "riprenderne uno, sviluppo con azione riprendi e quale = le parole del titolo.")

CODICE = (".py", ".cs", ".js", ".mjs", ".html", ".css", ".ps1", ".sh", ".json", ".txt", ".md",
          ".csv")


def file_di_codice(cartella, max_file: int = 30, max_byte: int = 400_000) -> dict[str, str]:
    """I file di testo di un programma finito (la cartella dei risultati), per l'agente."""
    out: dict[str, str] = {}
    if not cartella:
        return out
    radice = Path(cartella)
    if not radice.is_dir():
        return out
    totale = 0
    for p in sorted(radice.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in CODICE or "__pycache__" in p.parts \
                or p.name in ("lavoro.json",) or any(x.startswith(".") for x in
                                                     p.relative_to(radice).parts):
            continue
        try:
            testo = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        totale += len(testo)
        if totale > max_byte or len(out) >= max_file:
            break
        out[p.relative_to(radice).as_posix()] = testo
    return out


def misura_programma(cartella) -> dict:
    """Righe di codice e file sorgente di un programma (i test esclusi), per la revisione e per
    la proposta di farne un'estensione."""
    file = file_di_codice(cartella)
    sorgenti = {k: v for k, v in file.items()
                if k.endswith((".py", ".cs", ".js", ".mjs", ".ps1", ".sh"))
                and not k.rsplit("/", 1)[-1].startswith("test")
                and not k.endswith(("_test.py", ".test.js"))}
    righe = sum(1 for v in sorgenti.values() for r in v.splitlines()
                if r.strip() and not r.strip().startswith(("#", "//")))
    return {"file": len(sorgenti), "righe": righe, "test": len(file) - len(sorgenti)}


def servizio(ctx) -> Sviluppi | None:
    """Gli sviluppi, attaccati al servizio dei lavori (agenti/__init__.load_agenti)."""
    return getattr(getattr(ctx, "lavori", None), "sviluppi", None)


def chi(ctx):
    """L'id del profilo di chi parla, o None."""
    sc = getattr(ctx, "speaker_ctx", None)
    nome = getattr(sc, "current_speaker", None)
    if not nome:
        return None
    try:
        prof = ctx.speakers.get(nome) if getattr(ctx, "speakers", None) is not None else None
    except Exception:  # noqa: BLE001
        prof = None
    return getattr(prof, "id", None) or nome


def _nome_estensione(ctx, nome) -> str:
    est = getattr(ctx, "estensioni", None)
    if est is None or not str(nome or "").strip():
        return ""
    try:
        from .estensioni.servizio import _nome
        return _nome(nome, est.archivio)
    except Exception:  # noqa: BLE001
        return str(nome)


def estraneo(name: str, args: dict, ctx) -> Sviluppo | None:
    """Lo sviluppo aperto di chi parla se questa chiamata è una richiesta NUOVA che non gli
    appartiene (un'altra estensione, un programma, una ricerca: decisione di Dario dell'08/10,
    niente sviluppi nuovi finché uno è aperto); None altrimenti. Lo usano il tool (che rifiuta
    e propone di sospendere) e la politica (che allora non fa la sua domanda prima del
    rifiuto). Il «sì» a una proposta (`proposta`) non è una richiesta nuova."""
    if name not in ("estensione_crea", "delega_lavoro"):
        return None
    a = args if isinstance(args, dict) else {}
    if str(a.get("proposta") or "").strip():
        return None
    svs = servizio(ctx)
    sv = svs.corrente(chi(ctx)) if svs is not None else None
    if sv is None:
        return None
    if name == "estensione_crea" and sv.tipo == "estensione":
        mod = str(a.get("modifica") or "").strip()
        if mod and sv.estensione and _nome_estensione(ctx, mod) == sv.estensione:
            return None
        if not mod and sv.fase == "analisi" and sv.lavoro is None:
            return None                     # le risposte alle domande dell'analisi
    if name == "delega_lavoro" and sv.tipo == "programma" and sv.fase == "analisi"             and sv.lavoro is None and str(a.get("tipo") or "").lower() == "codice":
        return None
    return sv


def passo_interno(name: str, args: dict, ctx) -> bool:
    """La chiamata è un passo interno dello sviluppo aperto di chi parla (politica.controlla,
    regola `sviluppo_intento`): l'intento è lo sviluppo stesso, aperto con la voce da chi
    amministra, e il bersaglio è il suo (quell'estensione, quel lavoro)."""
    svs = servizio(ctx)
    if svs is None:
        return False
    sv = svs.corrente(chi(ctx))
    if sv is None:
        return False
    a = args if isinstance(args, dict) else {}
    if name in ("sviluppo", "sviluppo_prova"):
        return True
    if name == "estensione_crea" and sv.tipo == "estensione":
        mod = str(a.get("modifica") or "").strip()
        if mod:
            return bool(sv.estensione) and _nome_estensione(ctx, mod) == sv.estensione
        # le risposte alle domande dell'analisi, prima del lavoro
        return sv.fase == "analisi" and sv.lavoro is None
    if name == "delega_lavoro":
        prop = str(a.get("proposta") or "").strip()
        if prop:
            return prop == sv.proposto
        return (sv.tipo == "programma" and sv.fase == "analisi" and sv.lavoro is None
                and str(a.get("tipo") or "").lower() == "codice" and not a.get("file")
                and a.get("allegato") in (None, ""))
    if name == "estensioni_gestisci":
        return (str(a.get("azione") or "").lower() in ("approva", "rifiuta")
                and bool(sv.estensione) and _nome_estensione(ctx, a.get("nome")) == sv.estensione)
    if name in ("lavori_esegui", "lavori_rispondi"):
        lav = str(a.get("lavoro") or "").strip()
        return bool(sv.lavoro) and lav in ("", sv.lavoro)
    return False
