"""
Il filtro dell'eco della stanza (14/10, conversazione di stanza, **passo 5**: ascolto durante la
voce; progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 5.3, decisione 0029).

Con `stanza_durante_voce` il satellite e il telefono mandano i segmenti della stanza anche mentre
Calliope parla, segnati con le frasi che stavano suonando (`durante_voce`). La cancellazione
dell'eco del telefono (browser) e del microfono MME del portatile (Windows) toglie quasi tutta
la sua voce; ciò che resta è l'**eco residua**, e Calliope sa parola per parola che cosa stava
dicendo. Questa è la regola `eco_stanza` (principio 10: riguarda la trascrizione, che il modello
non vede, e il suo effetto è solo togliere una riga della stanza o parte di essa):

- le parole della riga e quelle delle frasi dette in quell'intervallo si normalizzano (minuscole,
  senza accenti né punteggiatura, apostrofo come spazio, cifre in lettere: Piper dice
  «diciannove», Whisper scrive «19») e si allineano con difflib, in ordine;
- un tratto di **almeno `FILA` parole di fila** uguali è eco e si toglie;
- se le parole che combaciano sono **almeno `QUOTA` della riga**, è eco tutta la riga, anche le
  parole che non combaciano (l'eco
  storpiata da Whisper: «domani torino c'è sole con 19 gradi» contro «Domani a Torino ci sarà il
  sole con diciannove gradi»);
- una parola storpiata da Whisper vale come la sua se le somiglia abbastanza (almeno
  `SIMILE_MIN` lettere e somiglianza ≥ `SIMILE`: «divario» vale «binario», «macchiare» non vale
  «innaffiare»);
- una riga fatta **solo del nome** (o della wake word) durante la sua voce è eco: Whisper senza
  prompt lo inventa sulla sua voce (misura a secco del 14/10), e chi la chiama davvero passa
  dal flusso dei comandi (barge-in), non dalla stanza;
- conta solo una parola che combacia **nel tempo**: detta da Calliope (tempo stimato dentro la
  frase, in proporzione alla posizione) entro `TOLLERANZA_S` dall'intervallo del segmento. Chi
  ripete «Torino?» tre secondi dopo che lei l'ha detto non è eco;
- il resto resta come riga di una persona; una riga senza parole che restano è scartata con il
  motivo «eco».

L'impronta CAM++ della voce di Calliope **non** decide (misura a secco del 14/10 sull'eco
simulata, in docs/aree/stt-tts.md): l'eco passata dalle casse e dalla cancellazione perde
l'impronta (similitudine alla frase stessa p50 0,38), le persone stanno fino a 0,32 e una persona
che parla sopra l'eco fino a 0,56: un taglio lì butterebbe le persone. Si rimisura con l'eco vera
(prove/manuali/misura_eco_stanza.py).

Solo libreria standard (più `calliope.numeri.in_lettere`, puro Python).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

FILA = 3                 # parole di fila uguali: eco
QUOTA = 0.6              # parte della riga che combacia oltre la quale è eco tutta
TOLLERANZA_S = 1.5       # ritardo dell'uscita, della rete e stima del tempo dentro la frase
CODA_S = 1.0             # dopo la fine di una frase l'eco può durare ancora (riverbero, buffer)
SIMILE = 0.7             # somiglianza (difflib) di una parola storpiata a una sua
SIMILE_MIN = 6           # lettere minime perché una parola storpiata conti

_PAROLA = re.compile(r"[^\W_]+", re.UNICODE)


def _senza_accenti(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _lettere(n: str) -> str:
    try:
        v = int(n)
    except ValueError:
        return n
    if v > 999_999:
        return n
    try:
        from ..numeri import in_lettere
        return _senza_accenti(in_lettere(v))
    except Exception:  # noqa: BLE001 — senza la conversione resta la cifra
        return n


def parole(testo: str) -> list[tuple[str, str]]:
    """[(forma normalizzata, forma originale)] delle parole di `testo`."""
    out = []
    t = str(testo or "").replace("’", "'").replace("`", "'")
    for m in _PAROLA.finditer(t):
        orig = m.group(0)
        norm = _senza_accenti(orig.lower())
        if norm.isdigit():
            norm = _lettere(norm)
        out.append((norm, orig))
    return out


@dataclass
class Detta:
    """Una frase di Calliope suonata vicino al satellite: testo e intervallo (epoch; `durata`
    0 se non si sa)."""
    testo: str
    inizio: float | None = None
    durata: float = 0.0


@dataclass
class Esito:
    testo: str                       # ciò che resta (vuoto: tutta eco)
    parole: int                      # parole della riga trascritta
    tolte: int                       # parole tolte come eco
    residua: int                     # parole rimaste che combaciano con lei (stima dell'eco
    #                                   residua: comprende chi ripete una sua parola)
    detto: int                       # parole delle frasi di Calliope confrontate
    motivo: str | None = None        # «eco» se la riga è tutta eco
    regole: list = field(default_factory=list)

    @property
    def tutta_eco(self) -> bool:
        return self.motivo == "eco"


def _tempi(dette: list[Detta]) -> list[tuple[str, float | None]]:
    """Le parole di Calliope in ordine, ciascuna col suo istante stimato (o None)."""
    out = []
    for d in dette:
        pp = parole(d.testo)
        n = len(pp)
        for j, (w, _o) in enumerate(pp):
            t = None
            if d.inizio is not None:
                t = d.inizio + (d.durata * (j + 0.5) / n if d.durata > 0 else 0.0)
            out.append((w, t))
    return out


def _storpiata(w: str, sue: set) -> str:
    """La sua parola a cui `w` somiglia abbastanza (Whisper sull'eco), o `w`."""
    if w in sue or len(w) < SIMILE_MIN:
        return w
    meglio, r_meglio = w, SIMILE
    for x in sue:
        if len(x) >= SIMILE_MIN and abs(len(x) - len(w)) <= 3:
            r = difflib.SequenceMatcher(None, w, x).ratio()
            if r >= r_meglio:
                meglio, r_meglio = x, r
    return meglio


def filtra(testo: str, dette: list[Detta], inizio: float | None = None,
           fine: float | None = None, tolleranza_s: float = TOLLERANZA_S,
           nomi=()) -> Esito:
    """La riga `testo` trascritta fra `inizio` e `fine` (epoch) contro le frasi `dette` da
    Calliope in quell'intervallo: ciò che resta, e i numeri (mai parole) per le misure.
    `nomi`: il nome e le wake word (una riga fatta solo di loro è eco)."""
    riga = parole(testo)
    lei = _tempi(dette)
    if not riga or not lei:
        return Esito(str(testo or "").strip(), len(riga), 0, 0, len(lei))
    b = [w for w, _t in lei]
    nn = {_senza_accenti(str(n).lower()) for n in nomi or () if str(n).strip()}
    if nn and all(w in nn for w, _o in riga):
        return Esito("", len(riga), len(riga), 0, len(b), "eco", ["eco_stanza_nome"])
    sue = set(b)
    a = [_storpiata(w, sue) for w, _o in riga]

    def nel_tempo(j: int) -> bool:
        t = lei[j][1]
        if t is None or inizio is None or fine is None:
            return True                       # tempi ignoti: vale il testo
        return inizio - tolleranza_s <= t <= fine + tolleranza_s

    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    combaciano: set[int] = set()              # indici della riga che combaciano nel tempo
    di_fila: set[int] = set()
    for blk in sm.get_matching_blocks():
        if not blk.size:
            continue
        idx = [blk.a + k for k in range(blk.size) if nel_tempo(blk.b + k)]
        combaciano.update(idx)
        # Una fila conta se le sue parole nel tempo sono ancora almeno FILA di seguito
        corsa: list[int] = []
        for k in range(blk.size):
            if nel_tempo(blk.b + k):
                corsa.append(blk.a + k)
            else:
                if len(corsa) >= FILA:
                    di_fila.update(corsa)
                corsa = []
        if len(corsa) >= FILA:
            di_fila.update(corsa)
    regole = []
    if combaciano and len(combaciano) >= QUOTA * len(a):
        tolte = set(range(len(a)))            # eco storpiata: le parole che restano sono sue
        regole.append("eco_stanza_quota")
    else:
        tolte = di_fila
        if tolte:
            regole.append("eco_stanza_fila")
    resto = [o for i, (_w, o) in enumerate(riga) if i not in tolte]
    residua = len(combaciano - tolte)
    if not resto:
        return Esito("", len(a), len(a), 0, len(b), "eco", regole)
    return Esito(" ".join(resto) if tolte else str(testo).strip(), len(a), len(tolte), residua,
                 len(b), None, regole)
