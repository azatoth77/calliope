"""
Le pause di chi parla (07/10/2026, decisione di Dario: per ora **solo misura**).

Oggi il turno si chiude dopo `silence_ms` (700 ms) di silenzio, uguale per tutti: in
`audio.Listener.listen` (anche sul satellite in Python, che riceve gli stessi parametri dal
server con `protocollo.PARAMETRI`) e nel telefono (`voce.js`). In futuro la soglia si adatterà
per persona, età e canale, con una partenza anticipata (docs/aree/stt-tts.md, «Pause e fine
del turno»). Qui c'è ciò che serve a misurare, senza cambiare nessun comportamento:

- `MisuraPause`: le pause **dentro** la frase (silenzi tra `PAUSA_MIN_MS` e `silence_ms`) e la
  durata del parlato, dal conteggio dei frame silenziosi dello stesso VAD che chiude il turno.
  La misura sta dove sta il VAD: in locale e sul satellite in Python qui, nel telefono la stessa
  logica in `voce.js`; satellite e telefono le mandano al server con `frase_finita`
  (`pause_ms`, `parlato_ms`, `chiusura`: campi facoltativi, un server vecchio li ignora).
- `OsservaRipresa`: dopo che il VAD ha chiuso la frase, per `RIPRESA_S` dalla fine della voce,
  si guarda se qualcuno ricomincia a parlare (il **taglio probabile**: la persona non aveva
  finito). Il microfono è già aperto; si ferma appena Calliope parla, ascolta o veglia.
- `inizio_ripresa`: la frase comincia con «aspetta», «non ho finito», «stavo dicendo»… Solo un
  segnale nel registro dei turni, nessuna regola di comportamento.
- `riassunto` e `testo`: per persona e canale, p50/p90/p95 delle pause interne, frasi, tagli
  probabili e la soglia che si sceglierebbe (p95 + margine, tra `SOGLIA_MIN_MS` e
  `SOGLIA_MAX_MS`), **come stima**: non si applica (`calliope stato --turni --pause`).

Solo libreria standard (e il VAD che c'è già): gira anche sul satellite.
"""
from __future__ import annotations

import queue
import re
import threading
import time

PAUSA_MIN_MS = 120        # sotto: respiro o consonante, non una pausa
MAX_PAUSE = 60            # pause tenute per frase (una frase lunga ne ha decine al massimo)
RIPRESA_S = 2.0           # voce entro questo dalla fine della frase: taglio probabile
RIPRESA_FRAME = 3         # frame di voce di fila (~96 ms) per dire che è ripresa
MARGINE_MS = 150          # soglia stimata = p95 delle pause + margine
SOGLIA_MIN_MS = 400
SOGLIA_MAX_MS = 1300
MIN_PAUSE_STIMA = 20      # sotto, la stima della soglia non è affidabile
TAGLI_FREQUENTI = 0.05    # oltre questa quota di frasi tagliate le pause misurate sono
#                           troncate dalla soglia in uso: la stima sale oltre la soglia
CHIUSURE = ("silenzio", "lunga", "rilascio", "muta")


class MisuraPause:
    """Le pause interne di una frase, frame per frame, dal VAD che chiude il turno.

    `frame(silenzioso)` per ogni frame della frase dopo l'inizio della voce: una serie di
    frame silenziosi seguita da voce è una pausa interna (se dura almeno `PAUSA_MIN_MS`); la
    serie con cui il VAD chiude la frase non si conta (è la soglia stessa)."""

    def __init__(self, frame_ms: float, min_ms: int = PAUSA_MIN_MS):
        self.frame_ms = float(frame_ms)
        self.min_ms = min_ms
        self.pause: list[int] = []
        self.frame_voce = 0           # frame dalla prima voce, silenzio finale compreso
        self._corsa = 0               # frame silenziosi di fila adesso

    def frame(self, silenzioso: bool):
        self.frame_voce += 1
        if silenzioso:
            self._corsa += 1
            return
        if self._corsa:
            ms = self._corsa * self.frame_ms
            if ms >= self.min_ms and len(self.pause) < MAX_PAUSE:
                self.pause.append(int(round(ms)))
            self._corsa = 0

    def parlato_ms(self, silenzio_finale: int = 0) -> int:
        """Dalla prima voce all'ultima: senza pre-roll e senza il silenzio di chiusura."""
        return int(round(max(0, self.frame_voce - silenzio_finale) * self.frame_ms))


def campi_frase(pause, parlato_ms, chiusura) -> dict:
    """I campi controllati di una frase misurata altrove (satellite, telefono): dati del
    satellite, mai istruzioni. Valori fuori misura scartati; {} se non c'è niente."""
    out = {}
    if isinstance(pause, list):
        p = [int(x) for x in pause[:MAX_PAUSE]
             if isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 10_000]
        out["pause_ms"] = p
    if isinstance(parlato_ms, (int, float)) and not isinstance(parlato_ms, bool) \
            and 0 <= parlato_ms <= 600_000:
        out["parlato_ms"] = int(parlato_ms)
    if chiusura in CHIUSURE:
        out["chiusura"] = chiusura
    return out


class OsservaRipresa:
    """Dopo la frase: qualcuno ricomincia a parlare entro `RIPRESA_S` dalla fine della voce?

    Un thread legge i frame che il microfono manda comunque (Listener._callback) e li passa a
    un VAD suo (non quello di `listen`: watch_for_name lo usa intanto). `muto()` vero (un suono di Calliope sulle casse) sospende la misura.
    `vad`: il modello (prob, reset_states) o una funzione senza argomenti che lo restituisce.
    `ripresa_s`: secondi dalla fine della voce all'inizio della ripresa, o None."""

    def __init__(self, vad, soglia: float, frame_ms: float, fine_voce: float,
                 muto=None, finestra_s: float = RIPRESA_S, avvisa=None):
        self.vad = vad
        self.soglia = soglia
        self.frame_ms = frame_ms
        self.fine_voce = fine_voce            # monotonic
        self.fino = fine_voce + finestra_s
        self.muto = muto
        self.avvisa = avvisa                  # funzione(ripresa_s), dal thread: il satellite
        self.q: queue.Queue = queue.Queue(maxsize=200)
        self.ripresa_s: float | None = None
        self.finita = threading.Event()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._gira, daemon=True, name="ripresa")
        self._t.start()

    def frame(self, f):
        try:
            self.q.put_nowait(f)
        except queue.Full:
            pass

    def ferma(self, attesa: float = 0.5):
        self._stop.set()
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass
        if threading.current_thread() is not self._t:
            self._t.join(attesa)

    def _gira(self):
        try:
            # Il VAD, o la funzione che lo dà (caricato la prima volta: Listener)
            vad = self.vad if hasattr(self.vad, "prob") else self.vad()
            if vad is None:
                return
            try:
                vad.reset_states()
            except Exception:  # noqa: BLE001
                pass
            fila = 0
            while not self._stop.is_set() and time.monotonic() < self.fino:
                try:
                    f = self.q.get(timeout=0.05)
                except queue.Empty:
                    continue
                if f is None or self._stop.is_set():
                    break
                try:
                    if self.muto is not None and self.muto():
                        fila = 0
                        continue
                except Exception:  # noqa: BLE001
                    pass
                fila = fila + 1 if vad.prob(f) >= self.soglia else 0
                if fila >= RIPRESA_FRAME:
                    inizio = time.monotonic() - (fila - 1) * self.frame_ms / 1000
                    self.ripresa_s = round(max(0.0, inizio - self.fine_voce), 2)
                    if self.avvisa is not None:
                        try:
                            self.avvisa(self.ripresa_s)
                        except Exception:  # noqa: BLE001 — una misura non ferma nulla
                            pass
                    break
        except Exception:  # noqa: BLE001 — una misura non ferma mai l'ascolto
            pass
        finally:
            self.finita.set()


# ── la frase comincia dicendo che non aveva finito (solo un segnale nel registro) ──
_INIZI = (
    # «aspetta,» «aspetta un attimo»; non «aspetta che arrivi la pizza» (una richiesta vera)
    ("aspetta", r"aspett[aio](?:\s+(?:un\s+(?:attimo|momento|secondo)|che\s+finisco))?\s*"
                r"(?:[,.!?…;:]|$)"),
    # «non ho finito», «non ho ancora finito di parlare»; non «non ho finito i compiti»
    ("non_ho_finito", r"non\s+ho\s+(?:ancora\s+)?finito(?:\s+di\s+(?:parlare|dire))?\s*"
                      r"(?:[,.!?…;:]|$)"),
    ("stavo_dicendo", r"stavo\s+dicendo\b"),
    ("fammi_finire", r"fammi\s+finire\b"),
)


def inizio_ripresa(testo: str, nomi=()) -> str | None:
    """Il nome del segnale se la frase **comincia** con una delle forme (dopo il nome di
    Calliope e la punteggiatura), altrimenti None. Non cambia nulla del turno: è solo una
    voce del registro, per contare i tagli che la persona dice a parole."""
    t = (testo or "").strip().lower()
    for n in nomi or ():
        n = str(n or "").strip().lower()
        if n and t.startswith(n):
            t = t[len(n):]
            break
    t = re.sub(r"^[\W_]+", "", t)
    t = re.sub(r"^(?:(?:no|ehm|eh|ma)\b[\W_]*)+", "", t)
    for nome, forma in _INIZI:
        if re.match(forma, t):
            return nome
    return None


# ── riassunto dal registro dei turni ──
def _q(valori, p: float):
    v = sorted(valori)
    if not v:
        return None
    return v[min(len(v) - 1, int(p * len(v)))]


def soglia_stimata(pause: list[int], frasi: int, tagli: int, soglia_in_uso: int | None):
    """(ms, motivo) della soglia che si sceglierebbe, o (None, motivo). Solo una stima."""
    if len(pause) < MIN_PAUSE_STIMA:
        return None, f"meno di {MIN_PAUSE_STIMA} pause"
    p95 = _q(pause, .95)
    s = p95 + MARGINE_MS
    motivo = "p95 + margine"
    if frasi and soglia_in_uso and tagli / frasi > TAGLI_FREQUENTI:
        # Le pause misurate sono tutte sotto la soglia in uso (quelle più lunghe hanno chiuso
        # il turno): con tanti tagli la soglia giusta è più alta di quanto dicono
        s = max(s, int(soglia_in_uso) + 300)
        motivo = "tagli frequenti: pause troncate dalla soglia in uso"
    return int(min(SOGLIA_MAX_MS, max(SOGLIA_MIN_MS, s))), motivo


def _canale(t: dict, a: dict) -> str:
    c = a.get("canale") or "locale"
    sat = a.get("satellite") or t.get("satellite")
    return f"{c}:{sat}" if sat and c != "locale" else c


def _persona(t: dict) -> str:
    v = t.get("voce") if isinstance(t.get("voce"), dict) else {}
    nome = v.get("nome")
    a = t.get("ascolto") or {}
    base = nome or "ospite"
    return f"{base} ({a['fascia']})" if a.get("fascia") else base


def riassunto(turni: list[dict]) -> dict:
    """Per persona e canale: frasi, pause interne (p50/p90/p95), parlato, tagli probabili,
    riprese, segnali a parole e soglia stimata. Solo i turni con «ascolto» (dal 07/10)."""
    gruppi: dict[tuple[str, str], dict] = {}
    for t in turni:
        a = t.get("ascolto")
        if not isinstance(a, dict):
            continue
        k = (_persona(t), _canale(t, a))
        g = gruppi.setdefault(k, {"frasi": 0, "pause": [], "parlato": [], "tagli": 0,
                                  "riprese": 0, "segnali": 0, "soglie": set(),
                                  "chiusure": {}})
        g["frasi"] += 1
        g["pause"].extend(x for x in a.get("pause_ms") or [] if isinstance(x, (int, float)))
        if isinstance(a.get("parlato_ms"), (int, float)):
            g["parlato"].append(a["parlato_ms"])
        if a.get("taglio_probabile"):
            g["tagli"] += 1
        if a.get("ripresa_dopo_s") is not None:
            g["riprese"] += 1
        if a.get("inizio_ripresa"):
            g["segnali"] += 1
        if a.get("soglia_ms"):
            g["soglie"].add(int(a["soglia_ms"]))
        ch = a.get("chiusura") or "?"
        g["chiusure"][ch] = g["chiusure"].get(ch, 0) + 1
    out = []
    for (persona, canale), g in sorted(gruppi.items()):
        p = g["pause"]
        in_uso = max(g["soglie"]) if g["soglie"] else None
        stima, motivo = soglia_stimata(p, g["frasi"], g["tagli"], in_uso)
        out.append({
            "persona": persona, "canale": canale, "frasi": g["frasi"],
            "pause": {"n": len(p), "p50": _q(p, .5), "p90": _q(p, .9), "p95": _q(p, .95),
                      "per_frase": round(len(p) / g["frasi"], 2) if g["frasi"] else 0},
            "parlato_ms_mediana": _q(g["parlato"], .5),
            "tagli_probabili": g["tagli"], "riprese_turno_dopo": g["riprese"],
            "segnali_a_parole": g["segnali"], "chiusure": g["chiusure"],
            "soglia_in_uso_ms": in_uso, "soglia_stimata_ms": stima, "motivo": motivo,
        })
    return {"gruppi": out}


def testo(r: dict) -> str:
    """La tabella per il terminale (`calliope stato --turni --pause`)."""
    gr = r.get("gruppi") or []
    if not gr:
        return "Pause: nessun turno con le misure dell'ascolto (dal 07/10)."
    righe = ["Pause dentro la frase e fine del turno (solo misura: la soglia stimata non si "
             "applica)", ""]
    for g in gr:
        p = g["pause"]

        def ms(x):
            return "—" if x is None else f"{int(x)} ms"
        righe.append(f"{g['persona']} · {g['canale']}: {g['frasi']} frasi, {p['n']} pause "
                     f"({p['per_frase']} a frase) p50 {ms(p['p50'])}, p90 {ms(p['p90'])}, "
                     f"p95 {ms(p['p95'])}")
        righe.append(f"    tagli probabili {g['tagli_probabili']}, riprese al turno dopo "
                     f"{g['riprese_turno_dopo']}, «aspetta»/«non ho finito» "
                     f"{g['segnali_a_parole']}; parlato mediano {ms(g['parlato_ms_mediana'])}")
        stima = (ms(g["soglia_stimata_ms"]) + f" ({g['motivo']})"
                 if g["soglia_stimata_ms"] is not None else f"— ({g['motivo']})")
        righe.append(f"    soglia in uso {ms(g['soglia_in_uso_ms'])}, si sceglierebbe {stima}")
    return "\n".join(righe)
