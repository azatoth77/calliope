"""
La conversazione corrente, come oggetto (05/10/2026, fase 2 del progetto «Contesto di
Calliope», docs/ricerche/2026-10-05-contesto-compressione.md).

Fino al 05/10 lo stato di una conversazione stava sparso in Brain (storia, azione in
sospeso, riferimenti della casa e dell'agenda, chi la possiede, ultimo turno). Qui è un
oggetto solo, `Conversazione`, che Brain usa attraverso proprietà con gli stessi nomi di
prima (`brain.history`, `brain.pending`…): il resto del codice non cambia. La fase 3 (una
conversazione per satellite) ne terrà più d'una e cambierà `brain.conv` a ogni turno.

In più rispetto a prima:
- `riassunto`: il riassunto dei turni compressi (calliope/compressione.py), o la riga
  «l'ultima volta avete parlato di…» di una conversazione nuova. Sta subito dopo il prompt
  di sistema e non cambia fino alla compressione dopo, così resta nella cache del prefisso;
- `archiviati`: quanti messaggi in testa alla storia sono già nell'archivio
  (calliope/conversazioni.py). Brain archivia i turni finiti all'inizio di ogni risposta,
  quindi ogni taglio della storia (compressione, `_trim_history`, `_trim_tokens`) toglie solo
  messaggi già salvati: niente va perso;
- `esporta` / `importa`: lo stato da salvare su disco a ogni turno (un riavvio di Calliope non
  la perde più) e da riprendere, se non è scaduta.

Accanto c'è `schermi/conversazione.py` (05/10): la conversazione **cominciata a voce** che
permette di scrivere dagli schermi. Non è la stessa cosa: quella vale solo con la voce
riconosciuta e scade con `storia_inattiva_s` dall'ultima frase riconosciuta, mentre questa è la
storia del modello. Le chiavi si corrispondono (`Conversazioni` usa `None` per tutta la casa,
qui `chiave` è "casa"; nella fase 3 tutte e due per satellite), e tutte e due si chiudono con
«esci» e quando parla un'altra persona.

Solo libreria standard.
"""
from __future__ import annotations

import json
import re
import time

# Nessuna conversazione aperta: la prossima persona la apre (prima era brain._UNSET)
UNSET = object()

# Versione del formato salvato su disco (importa rifiuta le versioni che non conosce)
FORMATO = 1


class Conversazione:
    """Lo stato di una conversazione. `chiave`: dove si svolge ("casa" oggi; il satellite
    nella fase 3)."""

    def __init__(self, chiave: str = "casa"):
        self.chiave = chiave
        self.history: list[dict] = []
        self.pending = None               # azione in sospeso (Brain.set_pending)
        self.reference = None             # ultimo dispositivo della casa (REFERENCE_MSG)
        self.agenda_reference = None      # ultima voce dell'agenda (AGENDA_MSG)
        self.owner = UNSET                # chi parla: id del profilo, None = ospite
        self.last_turn_at = None          # time.monotonic() dell'ultimo turno
        self.riassunto: dict | None = None    # {"testo", "dati", "tipo", "quando"}
        self.archiviati = 0               # messaggi in testa già archiviati
        self.id_archivio = None           # id della riga in conversazioni.db (dal worker)
        self.nome = None                  # nome di chi parla (per il riassunto)
        self.luogo = None                 # satellite o "locale" (ripresa entro qualche ora)
        self.inizio = time.time()
        self.compressioni = 0
        # I testi dei dati non fidati entrati in questa conversazione (05/10,
        # calliope/provenienza.py), solo in memoria: la provenienza degli argomenti li usa anche
        # dopo che la busta è uscita dalla storia. Non si salvano su disco
        self.esterni: list = []
        # Sicurezza per valore (08/10, calliope/valore.py), solo in memoria: le intenzioni
        # confermate dalla persona e non ancora riuscite (fase 2: la chiamata corretta dopo un
        # errore non chiede di nuovo), e i testi dei risultati dei tool interni fidati (fase 3:
        # provenienza «fidato» di un valore, per esempio il nome di un file trovato)
        self.intenzioni: list = []
        self.fidati: list = []
        # I «no» della persona alle proposte (09/10, calliope/politica.py `rifiuto`): il tool e
        # il bersaglio rifiutati non si richiamano finché lei non li chiede di nuovo
        self.rifiutate: list = []
        # Le foto della conversazione (calliope/immagini.py, Album): solo in memoria, mai su
        # disco (esporta non le salva); si svuotano con la conversazione. Lo crea Brain
        self.album = None
        # I file allegati (calliope/allegati.py, Allegati): come l'album, solo in memoria. Nella
        # storia resta solo `_all` (numeri) e `_all_info` («pdf, 240 kB»); esporta non salva
        # contenuti, e l'archivio delle conversazioni tiene al più «allegato: tipo, kB»
        self.allegati = None
        # Fase 3 (06/10, calliope/corsie.py): il numero della risposta (Brain.turn_number) e
        # l'uso del contesto dell'ultima risposta (Brain.uso_precedente) sono della
        # conversazione, non del satellite: la conversazione di una persona passa da un
        # satellite all'altro e le proposte «valide 3 turni» contano i suoi turni. Il
        # numero continua anche nella conversazione dopo della stessa persona (proposte di
        # una conversazione chiusa: mai «la risposta precedente» per sbaglio)
        self.turn_number = 0
        self.uso_precedente = None

    # ── stato ──
    def vuota(self) -> bool:
        return not (self.history or self.pending or self.reference
                    or self.agenda_reference or self.riassunto)

    def scambio(self, domanda: str, risposta: str):
        """Uno scambio chiuso detto senza il modello («grazie» → «Prego!», cortesia.py)."""
        self.history.append({"role": "user", "content": domanda})
        self.history.append({"role": "assistant", "content": risposta})

    def togli_in_testa(self, n: int):
        """Toglie i primi `n` messaggi della storia (già archiviati: Brain archivia prima)."""
        if n <= 0:
            return
        self.history = self.history[n:]
        self.archiviati = max(0, self.archiviati - n)

    def da_archiviare(self) -> list[dict]:
        """I messaggi finiti e non ancora archiviati, e li segna come archiviati."""
        nuovi = self.history[self.archiviati:]
        self.archiviati = len(self.history)
        return nuovi

    # ── su disco ──
    def esporta(self) -> dict:
        """Lo stato da salvare (JSON): storia, riassunto, chi la possiede, quando. Azione in
        sospeso e riferimenti no: durano un paio di minuti, meno di un riavvio."""
        owner = None if self.owner is UNSET else self.owner
        # Le foto della conversazione (calliope/immagini.py) non si riscrivono su disco a ogni
        # turno: dopo un riavvio resta il testo
        storia = [{k: v for k, v in m.items() if k != "images"} if m.get("images") else m
                  for m in self.history]
        return {"formato": FORMATO, "chiave": self.chiave, "history": storia,
                "riassunto": self.riassunto, "owner": owner,
                "owner_aperto": self.owner is UNSET, "nome": self.nome, "luogo": self.luogo,
                "id_archivio": self.id_archivio, "archiviati": self.archiviati,
                "inizio": self.inizio, "compressioni": self.compressioni,
                "ultimo": (time.time() - (time.monotonic() - self.last_turn_at)
                           if self.last_turn_at is not None else None)}

    @classmethod
    def importa(cls, dati: dict | None, scadenza_s: float = 0.0) -> "Conversazione | None":
        """La conversazione salvata, se il formato è noto e non è scaduta (`scadenza_s`:
        storia_inattiva_s; 0 = non scade). None altrimenti."""
        if not isinstance(dati, dict) or dati.get("formato") != FORMATO:
            return None
        ultimo = dati.get("ultimo")
        if not isinstance(ultimo, (int, float)):
            return None
        fa = time.time() - float(ultimo)
        if fa < 0 or (scadenza_s > 0 and fa > scadenza_s):
            return None
        hist = dati.get("history")
        if not isinstance(hist, list) or not all(isinstance(m, dict) and m.get("role")
                                                  for m in hist):
            return None
        c = cls(str(dati.get("chiave") or "casa"))
        c.history = hist
        c.riassunto = dati.get("riassunto") if isinstance(dati.get("riassunto"), dict) else None
        c.owner = UNSET if dati.get("owner_aperto") else dati.get("owner")
        c.nome, c.luogo = dati.get("nome"), dati.get("luogo")
        c.id_archivio = dati.get("id_archivio")
        c.archiviati = min(int(dati.get("archiviati") or 0), len(hist))
        c.inizio = float(dati.get("inizio") or time.time())
        c.compressioni = int(dati.get("compressioni") or 0)
        c.last_turn_at = time.monotonic() - fa
        return c


# ─────────────────────────── i turni, per l'archivio ───────────────────────────
RISERVATA = "(risposta con dati riservati: non archiviata)"

# Codici da non tenere nell'archivio: IBAN, codice fiscale, email, numeri lunghi (partita IVA,
# carte, telefoni). Più stretti di schermi.moduli.oscura, che lavora su testi scritti nei
# moduli: lì l'IBAN senza distinzione di maiuscole prendeva «il 12 ottobre col treno» (banco
# del 05/10: «Mia sorella Chiara arriva da Torino ******»)
_PRIVATI = [
    re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b"),                   # IBAN
    re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I),          # codice fiscale
    re.compile(r"[^\s@]+@[^\s@]+\.[a-z]{2,}", re.I),                          # email
    re.compile(r"(?<![\d])(?:\d[\s.\-]?){9,}\d(?![\d])"),                     # 10+ cifre
]


def oscura_archivio(testo: str) -> str:
    for r in _PRIVATI:
        testo = r.sub("******", testo)
    return testo


# La frase di sfida (conferme.py) non resta nell'archivio (08/10, come nel registro dei turni):
# al posto della frase ripetuta questo segno, e nella risposta che la chiede le parole tolte
SFIDA_DETTA = "(frase di conferma)"
_RIPETI = re.compile(r"(\b[Rr]ipeti\b[^:.!?\n]{0,40}:)[^.!?\n]*")


def senza_sfida(testo: str) -> str:
    """«Per conferma ripeti: girasole, treno.» → «Per conferma ripeti: ….»"""
    return _RIPETI.sub(r"\1 …", testo or "")


# Il tipo di una chiamata che si può tenere: una parola sola, breve (gli elenchi chiusi)
_TIPO = re.compile(r"[A-Za-zÀ-ÿ_]{2,20}")


def turni(messaggi: list[dict], riservati=frozenset(), segreti: dict | None = None,
          quando: float | None = None, redact=None) -> list[dict]:
    """I messaggi della storia divisi in turni da archiviare: {domanda, risposta, azioni,
    riservato, quando}. Un turno comincia con un messaggio dell'utente (un annuncio senza
    domanda è un turno con la domanda vuota). Gli argomenti dei tool non si salvano mai
    (codici degli schermi, dati scritti): solo il nome, l'esito e la frase già detta. Un turno
    con un tool `riservati` (documenti di casa, rubrica) non tiene la risposta. I testi
    passano da `oscura` (codici fiscali, IBAN, email), come il registro dei turni.

    Dall'08/10 il messaggio dell'utente può portare `_turno` (ciclo.py, a turno finito):
    l'istante del turno, il satellite o lo schermo e il canale (`meta` del turno, per la scheda
    «Conversazione»), e se era la frase di sfida (`sfida`: al suo posto SFIDA_DETTA) o se la
    risposta la chiedeva (`sfida_chiesta`: le parole tolte). `redact` (Brain.redact): i
    segreti detti nel turno (il codice di abbinamento di uno schermo). Dal 09/10 l'unica
    eccezione agli argomenti: il `tipo` della chiamata, se è una parola sola (web_cerca
    «notizie»), perché conversazione_cerca dica da quale fonte veniva il turno."""
    oscura = oscura_archivio
    out: list[dict] = []
    cur = None
    tipi: dict[str, str] = {}       # id della chiamata → tipo
    for m in messaggi:
        ruolo = m.get("role")
        if ruolo == "user" or cur is None:
            meta = m.get("_turno") if ruolo == "user" and isinstance(m.get("_turno"),
                                                                     dict) else {}
            t0 = meta.get("t")
            cur = {"domanda": "", "risposta": [], "azioni": [], "riservato": False,
                   "quando": float(t0) if isinstance(t0, (int, float)) else (quando
                                                                             or time.time()),
                   "_sfida": bool(meta.get("sfida")),
                   "_sfida_chiesta": bool(meta.get("sfida_chiesta"))}
            info = {k: str(meta[k])[:60] for k in ("luogo", "canale") if meta.get(k)}
            if info:
                cur["meta"] = info
            out.append(cur)
            if ruolo == "user":
                # Senza le buste dei dati non fidati (allegati: calliope/provenienza.py)
                from .provenienza import senza_buste
                cur["domanda"] = senza_buste(str(m.get("content") or ""))
                info = [str(x) for x in (m.get("_all_info") or ())][:8]
                if info:            # mai nome né contenuto dei file (05/10, allegati)
                    cur["domanda"] = (cur["domanda"] + " " + " ".join(
                        f"[allegato: {x}]" for x in info)).strip()
                continue
        if ruolo == "assistant":
            testo = str(m.get("content") or "").strip()
            if testo:
                cur["risposta"].append(testo)
            for c in m.get("tool_calls") or ():
                # Degli argomenti solo il «tipo» (09/10), un valore di un elenco chiuso
                # (web_cerca «notizie»): la fonte del turno ritrovato con conversazione_cerca
                if not isinstance(c, dict):
                    continue
                args = c.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = None
                tipo = args.get("tipo") if isinstance(args, dict) else None
                if c.get("id") and isinstance(tipo, str) and _TIPO.fullmatch(tipo):
                    tipi[str(c["id"])] = tipo.lower()
        elif ruolo == "tool":
            nome = str(m.get("name") or "")
            if nome in riservati:
                cur["riservato"] = True
            try:
                res = json.loads(m.get("content") or "{}")
            except (json.JSONDecodeError, TypeError):
                res = {}
            res = res if isinstance(res, dict) else {}
            ok = "errore" not in res and res.get("ok") is not False
            detto = ""
            for k in ("conferma", "risposta_finale", "da_dire"):
                if isinstance(res.get(k), str) and res[k].strip():
                    detto = res[k].strip()
                    break
            tipo = tipi.get(str(m.get("tool_call_id") or ""))
            cur["azioni"].append({"tool": nome, "ok": ok, **({"tipo": tipo} if tipo else {}),
                                  **({"detto": oscura(detto)[:300]} if detto
                                     and nome not in riservati else {})})
    def pulito(x: str) -> str:
        x = oscura(x)
        if redact is not None:
            try:
                x = redact(x)
            except Exception:  # noqa: BLE001 — l'archivio non si ferma per un segreto
                pass
        return x

    for t in out:
        sfida, chiesta = t.pop("_sfida", False), t.pop("_sfida_chiesta", False)
        t["domanda"] = SFIDA_DETTA if sfida and t["domanda"] else pulito(t["domanda"])
        t["risposta"] = (RISERVATA if t["riservato"] and t["risposta"]
                         else pulito(" ".join(t["risposta"])))
        if chiesta:
            t["risposta"] = senza_sfida(t["risposta"])
            for a in t["azioni"]:
                if a.get("detto"):
                    a["detto"] = senza_sfida(a["detto"])
        if redact is not None:
            for a in t["azioni"]:
                if a.get("detto"):
                    a["detto"] = pulito(a["detto"])
    return [t for t in out if t["domanda"] or t["risposta"] or t["azioni"]]


def testo_turno(t: dict) -> str:
    """Il testo di un turno per la ricerca (FTS5 e vettori)."""
    parti = []
    if t.get("domanda"):
        parti.append(f"Domanda: {t['domanda']}")
    if t.get("risposta"):
        parti.append(f"Risposta: {t['risposta']}")
    fatti = [a.get("detto") for a in t.get("azioni") or () if a.get("detto")]
    if fatti:
        parti.append("Fatto: " + " ".join(fatti))
    return "\n".join(parti)
