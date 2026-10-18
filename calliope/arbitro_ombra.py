"""
L'arbitro della memoria **in ombra** (15/10/2026, passo 2 dell'arbitro unico delle attività e
della memoria: docs/ricerche/2026-10-14-arbitro-memoria.md § 4.3, § 4.4, § 7 punto 2).

Con `arbitro_memoria: ombra` un thread leggero registra cosa **avrebbe fatto** l'arbitro, senza
farlo: **nessun caricamento né scaricamento vero**, nessun lavoro rallentato o fermato.

- **A ogni richiesta di carico** (lotti di vettori delle conversazioni e domanda di una ricerca,
  un passo della corsia lenta della stanza, un giudizio del guardiano a posteriori, un lavoro
  dell'agente) chi chiede chiama `richiesta(chi)`: un `append` su una coda in memoria, niente di
  più (la domanda di una ricerca arriva dal turno). Il thread poi scrive cosa l'arbitro avrebbe
  messo in coda (classe e precedenza), se l'avrebbe fatto partire subito o a voce ferma, quanta
  memoria avrebbe chiesto e chi avrebbe scaricato per farle posto (`arbitro_memoria.proposta`),
  con la memoria vera di quel momento (MemAvailable). La coda in ombra fa partire una richiesta
  alla volta quando `quiete(QUIETE_CARICO_S)`, la più importante prima (tempo reale > vicino > a
  richiesta > sfondo), e butta quella che aspetta oltre `ATTESA_MAX_S` (§ 4.3).
- **A ogni minuto**: la memoria vera, il conto, e per ogni modello a richiesta (secondo Whisper
  q5_0 ~2 GB, FLUX 13 GB) se adesso ci starebbe, solo scaricando qualcuno, o per niente; e quante
  volte una proposta **avrebbe scaricato il tempo reale** (deve restare 0: è il criterio).
- **La voce ferma**: guardia, corsia lenta, embedding e arbitro dell'agente decidono come prima;
  a ogni loro decisione `confronta(fonte, vecchia, secondi)` la mette accanto a quella della
  definizione unica (`arbitro_memoria.quiete`) e conta le divergenze (episodi e secondi, nelle
  due direzioni: «la vecchia diceva libera, quiete no» e il contrario).

Il registro è un file al giorno `arbitro-AAAA-MM-GG.jsonl` accanto a quello dei turni
(`turn_log_dir`, stessa tenuta `turn_log_days`), **solo numeri**: niente parole né persone. Righe:

    avvio      modo, memoria (unificata | dedicata | cpu), pool_gb, margine_gb
    minuto     libera_gb, spazio_gb, margine_gb, ferma_s, a_richiesta {ruolo: ci_sta,
               senza_scaricare, scaricherebbe, mancano_gb}, tempo_reale (ruoli del tempo reale
               nelle proposte: deve essere 0), divergenze {fonte: vecchia_si, vecchia_no, s}
               (dal minuto prima), richieste {chi: n}, coda, buttate
    richiesta  chi, classe, gb (memoria da caricare: 0 se usa modelli già caricati), libera_gb,
               ci_sta, scaricherebbe, mancano_gb, tempo_reale, partirebbe («subito» |
               «in_coda» | «rifiutata»: non ci sta neanche scaricando lo sfondo), occupata (il motivo, se la voce non è ferma)
    partita    chi, classe, attesa_s (quando la coda in ombra l'avrebbe fatta partire)
    buttata    chi, classe, attesa_s
    divergenza fonte, direzione («vecchia_si» | «vecchia_no»), secondi

`calliope stato --memoria --storia` li riassume per giorno (`storia`, `criterio`, `testo_storia`).
"""
from __future__ import annotations

import collections
import re
import sys
import threading
import time

from . import arbitro_memoria as am

SPENTO, OMBRA = "spento", "ombra"
MODI = (SPENTO, OMBRA)
PREFISSO = "arbitro-"
PASSO_S = 1.0                    # il giro del thread: campiona la voce, svuota le richieste
MINUTO_S = 60.0
INVENTARIO_OGNI_S = 900.0        # l'inventario intero (vLLM, nvidia-smi, servizi): raro
LIBERA_OGNI_S = 5.0              # MemAvailable: al più così spesso
OLLAMA_OGNI_S = 10.0             # /api/ps (chi è caricato): al più così spesso
# Un caricamento comincia solo a voce ferma da così (come stanza_guardia_quiete_s, § 4.4)
QUIETE_CARICO_S = 5.0
PRECEDENZA = {am.TEMPO_REALE: 0, am.VICINO: 1, am.A_RICHIESTA: 2, am.SFONDO: 3}
# Attesa massima nella coda in ombra, poi la richiesta si butta e si conta (§ 4.3)
ATTESA_MAX_S = {am.TEMPO_REALE: 60.0, am.VICINO: 30.0, am.A_RICHIESTA: 120.0,
                am.SFONDO: 3600.0}
# Quanto terrebbe occupato il posto del caricamento (uno alla volta su tutta la macchina)
CARICO_S = {"embedding": 1.5, "whisper_lento": 5.0, "immagini": 15.0}
CODA_MAX = 500
RIGHE_MINUTO_MAX = 60            # righe «richiesta» e «divergenza» al minuto, poi solo conteggi
# Il criterio per andare al passo 3 (§ 7 punto 2)
CRITERIO_GIORNI = 7


def modo(cfg) -> str:
    m = str(getattr(cfg, "arbitro_memoria", SPENTO) or SPENTO).strip().lower()
    return m if m in MODI else SPENTO


def chi_classe(cfg, chi: str) -> tuple[str, str | None]:
    """(classe, ruolo della memoria) di chi chiede: il ruolo è il modello che dovrebbe essere
    caricato (None: usa modelli già caricati per il tempo reale o prenotati, costa calcolo e non
    memoria)."""
    if chi == "embedding":
        return am.SFONDO, "embedding"
    if chi == "embedding_ricerca":
        return am.VICINO, "embedding"          # la domanda di una ricerca, dal turno
    if chi == "corsia_lenta":
        if str(getattr(cfg, "stanza_lenta_stt_url", "") or "").strip():
            return am.A_RICHIESTA, "whisper_lento"
        return am.SFONDO, None                  # lo stesso Whisper dei turni
    if chi in ("guardia", "agente"):
        return am.SFONDO, None                  # rilevatore già caricato, vLLM già prenotato
    return am.SFONDO, None


class _Confronto:
    __slots__ = ("stato", "ultimo", "vecchia_si", "vecchia_no", "secondi", "chiamate")

    def __init__(self):
        self.stato = None
        self.ultimo = 0.0
        self.vecchia_si = self.vecchia_no = self.chiamate = 0
        self.secondi = 0.0

    def numeri(self) -> dict:
        return {"vecchia_si": self.vecchia_si, "vecchia_no": self.vecchia_no,
                "s": round(self.secondi, 1)}


def _rss_proprio_gb() -> float | None:
    """La memoria residente di questo processo (Linux: /proc/self/status), None altrove."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        with open("/proc/self/status", encoding="ascii", errors="replace") as fh:
            m = re.search(r"^VmRSS:\s*(\d+)\s*kB", fh.read(), re.M)
        return round(int(m.group(1)) * 1024 / 1e9, 2) if m else None
    except (OSError, ValueError):
        return None


class Ombra:
    """L'arbitro in ombra. `inventario()`, `libera()` e `caricati()` si possono passare finti
    (prove): di serie l'inventario vero (`macchina.inventario`, ogni 15 minuti), MemAvailable o
    nvidia-smi per la memoria libera (al più ogni 5 s) e /api/ps per chi è caricato in Ollama
    (al più ogni 10 s). `misure`: chi scrive le righe (di serie il file del giorno)."""

    def __init__(self, cfg, quiete: am.Quiete | None = None, *, inventario=None, libera=None,
                 caricati=None, misure=None, orologio=None, log=print, avvia: bool = True):
        self.cfg = cfg
        self.quiete = quiete if quiete is not None else am.QUIETE
        self.log = log
        self._ora = orologio or time.monotonic
        self._fn_inventario, self._fn_libera, self._fn_caricati = inventario, libera, caricati
        if misure is None:
            from .stanza.misure import Misure
            misure = Misure(getattr(cfg, "turn_log_dir", None),
                            int(getattr(cfg, "turn_log_days", 60) or 60), prefisso=PREFISSO)
        self.misure = misure
        self._lock = threading.Lock()
        self._richieste: collections.deque = collections.deque(maxlen=2000)
        self._eventi: collections.deque = collections.deque(maxlen=2000)
        self._confronti: dict[str, _Confronto] = {}
        self._confronti_minuto: dict[str, dict] = {}
        self._coda: list[dict] = []
        self._carico_fino = 0.0
        self._inv: dict | None = None
        self._inv_t = self._libera_t = self._ollama_t = -1e18
        self._prossimo_minuto = 0.0
        self._righe_minuto = 0
        self._conti_minuto: dict[str, int] = {}
        self.buttate = 0
        self._tenute_minuto = int(getattr(self.quiete, "tenute", 0) or 0)
        self.richieste_viste = 0
        # L'arbitro dell'agente (agenti/arbitro.py): la sua «voce libera» si confronta qui, dal
        # thread (occupata_ora: un flag sotto il suo lock, senza effetti)
        self.arbitro_agente = None
        self._fermo = threading.Event()
        self._thread = None
        if avvia:
            self._thread = threading.Thread(target=self._lavora, name="arbitro-ombra",
                                            daemon=True)
            self._thread.start()

    # ─────────────────────────── dagli altri thread: costo minimo ───────────────────────────
    def richiesta(self, chi: str, **dettagli):
        """Una richiesta di carico (dal thread di chi la fa, anche dal turno): solo un append."""
        self._richieste.append((self._ora(), str(chi), dettagli))

    def confronta(self, fonte: str, vecchia: bool, secondi: float) -> bool:
        """La decisione «voce ferma» di `fonte` (True = libera per la vecchia definizione)
        accanto a `quiete(secondi)`. Restituisce `vecchia` (chi chiama decide con quella)."""
        try:
            nuova = self.quiete(secondi)
        except Exception:  # noqa: BLE001 — l'ombra non cambia mai la decisione
            return vecchia
        ora = self._ora()
        with self._lock:
            c = self._confronti.get(fonte)
            if c is None:
                c = self._confronti[fonte] = _Confronto()
            c.chiamate += 1
            if c.stato is not None:
                c.secondi += max(0.0, ora - c.ultimo)
            c.ultimo = ora
            d = None if bool(vecchia) == bool(nuova) else (
                "vecchia_si" if vecchia else "vecchia_no")
            if d is not None and d != c.stato:
                setattr(c, d, getattr(c, d) + 1)
                self._eventi.append({"fonte": fonte, "direzione": d,
                                     "secondi": round(float(secondi or 0), 1)})
            c.stato = d
        return vecchia

    def divergenze(self) -> dict:
        with self._lock:
            return {k: v.numeri() for k, v in self._confronti.items()}

    # ─────────────────────────── il thread ───────────────────────────
    def _lavora(self):
        try:
            self._scrivi("avvio", modo=OMBRA, **self._testa())
        except Exception as e:  # noqa: BLE001
            self.log(f"[ARBITRO] avvio in ombra: {type(e).__name__}: {e}")
        while not self._fermo.wait(PASSO_S):
            try:
                self.passo()
            except Exception as e:  # noqa: BLE001 — l'ombra non ferma niente
                self.log(f"[ARBITRO] giro in ombra: {type(e).__name__}: {e}")

    def chiudi(self):
        self._fermo.set()

    def passo(self, ora: float | None = None):
        """Un giro (le prove lo chiamano a mano): la voce, l'arbitro dell'agente, le richieste
        arrivate, la coda in ombra e, ogni minuto, la riga del minuto."""
        ora = self._ora() if ora is None else ora
        self.quiete.campiona()
        arb = self.arbitro_agente
        if arb is not None and getattr(arb, "condiviso", False) and callable(
                getattr(arb, "occupata_ora", None)):
            try:
                # Senza effetti: in_pausa() libera la voce oltre la tenuta massima, e
                # chiamarlo da qui cambierebbe il conto dei turni dell'arbitro
                self.confronta("agente", not arb.occupata_ora(),
                               float(getattr(arb, "ripresa_s", 3.0) or 0.0))
            except Exception:  # noqa: BLE001
                pass
        while self._richieste:
            t, chi, d = self._richieste.popleft()
            self._registra_richiesta(t, chi, d)
        self._avanza_coda(ora)
        while self._eventi:
            e = self._eventi.popleft()
            if self._sotto_tetto("divergenza"):
                self._scrivi("divergenza", **e)
        if ora >= self._prossimo_minuto:
            self._prossimo_minuto = ora + MINUTO_S
            self.minuto()

    # ─────────────────────────── memoria ───────────────────────────
    def _inventario(self, forza: bool = False) -> dict:
        ora = self._ora()
        if self._inv is None or forza or ora - self._inv_t >= INVENTARIO_OGNI_S:
            if self._fn_inventario is not None:
                inv = self._fn_inventario()
            else:
                from . import macchina
                inv = macchina.inventario(self.cfg)
            self._inv, self._inv_t = inv, ora
            self._libera_t = self._ollama_t = ora
        return self._inv

    def _leggi_libera(self, inv: dict) -> float | None:
        if self._fn_libera is not None:
            return self._fn_libera()
        from . import macchina
        s = macchina.Sonde()
        g = inv.get("gpu") or {}
        if g and g.get("memoria_gb") and not g.get("unificata"):
            n = macchina._gpu_nvidia(s)
            return (n or {}).get("libera_gb")
        if s.os == "linux":
            return macchina._meminfo(s)[1]
        return s.libera_windows()

    def _leggi_caricati(self, inv: dict) -> list | None:
        if self._fn_caricati is not None:
            return self._fn_caricati()
        o = (inv.get("motori") or {}).get("ollama") or {}
        if not o.get("url"):
            return None
        from . import macchina
        ps = macchina._json(macchina.Sonde().get(o["url"].rstrip("/") + "/api/ps"))
        if not isinstance(ps, dict):
            return None
        out = []
        for m in ps.get("models") or []:
            size, vram = m.get("size") or 0, m.get("size_vram")
            out.append({"nome": m.get("name") or m.get("model"), "gb": round(size / 1e9, 2),
                        "gb_gpu": round(vram / 1e9, 2) if isinstance(vram, int) else None,
                        "contesto": m.get("context_length"),
                        "in_parte_cpu": isinstance(vram, int) and 0 < size and vram < size})
        return out

    def _aggiorna(self, forza: bool = False) -> dict:
        """L'inventario in memoria con la memoria libera e /api/ps di adesso (con i tetti)."""
        inv = self._inventario()
        ora = self._ora()
        if forza or ora - self._libera_t >= LIBERA_OGNI_S:
            self._libera_t = ora
            lib = self._leggi_libera(inv)
            if lib is not None:
                lib = round(float(lib), 2)
                g = inv.get("gpu")
                if not (g and g.get("memoria_gb") and not g.get("unificata")):
                    inv["ram_libera_gb"] = lib       # memoria unificata o solo CPU
                if g:
                    g["libera_gb"] = lib
        if forza or ora - self._ollama_t >= OLLAMA_OGNI_S:
            self._ollama_t = ora
            car = self._leggi_caricati(inv)
            o = (inv.get("motori") or {}).get("ollama")
            if car is not None and isinstance(o, dict):
                o["caricati"] = car
        return inv

    def _uso(self) -> am.Uso:
        u = am.da_config(self.cfg)
        u.processo_gb = _rss_proprio_gb()
        return u

    def conto(self, forza: bool = False) -> am.Conto:
        return am.conto(self._aggiorna(forza), self._uso())

    def _testa(self) -> dict:
        c = self.conto(forza=True)
        return {"memoria": c.tipo, "pool_gb": c.pool_gb, "margine_gb": c.margine_gb}

    # ─────────────────────────── le richieste ───────────────────────────
    def _sotto_tetto(self, tipo: str) -> bool:
        self._conti_minuto[tipo] = self._conti_minuto.get(tipo, 0) + 1
        return self._conti_minuto[tipo] <= RIGHE_MINUTO_MAX

    def _registra_richiesta(self, t: float, chi: str, d: dict):
        self.richieste_viste += 1
        classe, ruolo = chi_classe(self.cfg, chi)
        self._conti_minuto["r:" + chi] = self._conti_minuto.get("r:" + chi, 0) + 1
        c = self.conto()
        gb = 0.0
        if ruolo is not None:
            o = next((x for x in c.occupanti if x.ruolo == ruolo), None)
            if o is None or o.caricato is not True:
                gb = float(am.A_RICHIESTA_GB.get(ruolo) or (o.gb_pieno if o else 0.0) or 0.0)
            if ruolo == "embedding" and c.tipo == "dedicata" and getattr(
                    self.cfg, "conversazioni_embedding_cpu", True):
                gb = 0.0                       # sulla CPU: non tocca la VRAM (portatile)
        riga = {"chi": chi, "classe": classe, "gb": round(gb, 2), "libera_gb": c.libera_gb}
        rifiutata = False
        if gb > 0:
            p = am.proposta(c, gb, ruolo or chi, passo=4)
            riga.update(ci_sta=p.ci_sta, scaricherebbe=p.scaricherebbe,
                        mancano_gb=p.mancano_gb, tempo_reale=am.tempo_reale_toccato(c, p))
            # Non ci sta neanche scaricando lo sfondo: non si carica e si dice (§ 4.1)
            rifiutata = not p.ci_sta
        occ = self.quiete.occupata()
        subito = classe in (am.TEMPO_REALE, am.VICINO) or (
            self.quiete(QUIETE_CARICO_S) and not self._caricando(t))
        riga["partirebbe"] = "rifiutata" if rifiutata else "subito" if subito else "in_coda"
        if occ:
            riga["occupata"] = occ
        if d:
            riga.update({k: v for k, v in d.items() if isinstance(v, (int, float, bool))})
        if rifiutata:
            pass
        elif subito:
            if gb > 0:
                self._carico_fino = max(self._carico_fino, t) + CARICO_S.get(ruolo or "", 5.0)
        else:
            if len(self._coda) >= CODA_MAX:
                self._coda.pop(0)
                self.buttate += 1
            self._coda.append({"t": t, "chi": chi, "classe": classe, "gb": gb,
                               "ruolo": ruolo})
        if self._sotto_tetto("richiesta"):
            self._scrivi("richiesta", **riga)

    def _caricando(self, ora: float) -> bool:
        return ora < self._carico_fino

    def _avanza_coda(self, ora: float):
        if not self._coda:
            return
        tenute = []
        for r in self._coda:
            if ora - r["t"] > ATTESA_MAX_S.get(r["classe"], 3600.0):
                self.buttate += 1
                self._scrivi("buttata", chi=r["chi"], classe=r["classe"],
                             attesa_s=round(ora - r["t"], 1))
            else:
                tenute.append(r)
        self._coda = tenute
        # Una alla volta, la più importante (poi la più vecchia), a voce ferma e senza un
        # caricamento in corso
        while self._coda and self.quiete(QUIETE_CARICO_S) and not self._caricando(ora):
            r = min(self._coda, key=lambda x: (PRECEDENZA.get(x["classe"], 9), x["t"]))
            self._coda.remove(r)
            self._scrivi("partita", chi=r["chi"], classe=r["classe"],
                         attesa_s=round(max(0.0, ora - r["t"]), 1))
            if r["gb"] > 0:
                self._carico_fino = ora + CARICO_S.get(r["ruolo"] or "", 5.0)

    # ─────────────────────────── il minuto ───────────────────────────
    def minuto(self) -> dict:
        c = self.conto(forza=True)
        ar: dict = {}
        tr: list[str] = []
        for ruolo, gb in am.A_RICHIESTA_GB.items():
            o = next((x for x in c.occupanti if x.ruolo == ruolo), None)
            if c.tipo == "cpu" and ruolo == "immagini":
                continue
            if o is not None and o.caricato is True:
                ar[ruolo] = {"caricato": True}
                continue
            p = am.proposta(c, gb, ruolo, passo=4)
            tr += am.tempo_reale_toccato(c, p)
            ar[ruolo] = {"gb": gb, "ci_sta": p.ci_sta,
                         "senza_scaricare": p.ci_sta and not p.scaricherebbe,
                         "scaricherebbe": p.scaricherebbe, "mancano_gb": p.mancano_gb}
        with self._lock:
            ora_div = {k: v.numeri() for k, v in self._confronti.items()}
        delta = {}
        for k, v in ora_div.items():
            prima = self._confronti_minuto.get(k, {"vecchia_si": 0, "vecchia_no": 0, "s": 0.0})
            dd = {"vecchia_si": v["vecchia_si"] - prima["vecchia_si"],
                  "vecchia_no": v["vecchia_no"] - prima["vecchia_no"],
                  "s": round(v["s"] - prima["s"], 1)}
            if any(dd.values()):
                delta[k] = dd
        self._confronti_minuto = ora_div
        richieste = {k[2:]: n for k, n in self._conti_minuto.items() if k.startswith("r:")}
        riga = {"libera_gb": c.libera_gb, "spazio_gb": c.spazio_gb, "margine_gb": c.margine_gb,
                "ferma_s": round(self.quiete.ferma_da(), 1), "a_richiesta": ar,
                "tempo_reale": len(tr), "divergenze": delta, "richieste": richieste,
                "coda": len(self._coda), "buttate": self.buttate}
        if tr:
            riga["tempo_reale_ruoli"] = sorted(set(tr))
        # La voce liberata dalla tenuta massima in questo minuto (#157): deve restare 0
        tenute = int(getattr(self.quiete, "tenute", 0) or 0)
        if tenute > self._tenute_minuto:
            riga["tenute_voce"] = tenute - self._tenute_minuto
        self._tenute_minuto = tenute
        self._conti_minuto = {}
        self.buttate = 0
        self._scrivi("minuto", **riga)
        return riga

    def _scrivi(self, tipo: str, **campi):
        try:
            self.misure.scrivi(tipo, **campi)
        except Exception as e:  # noqa: BLE001 — una riga persa non ferma niente
            self.log(f"[ARBITRO] riga non scritta: {type(e).__name__}")


def load_ombra(cfg, log=print) -> Ombra | None:
    """L'arbitro in ombra con `arbitro_memoria: ombra`; None se spento."""
    if modo(cfg) != OMBRA:
        return None
    o = Ombra(cfg, log=log)
    log("[ARBITRO] Arbitro della memoria in ombra: registra cosa farebbe (code, scaricamenti, "
        "memoria vera), non carica né scarica niente (calliope stato --memoria --storia)")
    return o


# ─────────────────────────── la storia (calliope stato --memoria --storia) ───────────────────
def leggi(cartella: str | None, giorni: int | None = None) -> list[dict]:
    from .stanza.misure import leggi as leggi_righe
    return leggi_righe(cartella, giorni, prefisso=PREFISSO)


def storia(righe: list[dict]) -> dict:
    """Per giorno: memoria libera minima vera, minuti in cui un a richiesta non ci sarebbe
    stato (o solo scaricando), «avrebbe scaricato il tempo reale», divergenze di quiete(),
    richieste per chi, partite, buttate e attese della coda in ombra, voce liberata dalla
    tenuta massima (`tenute_voce`, dal 18/10: #157)."""
    giorni: dict = {}
    for r in righe:
        g = giorni.setdefault(str(r.get("t", ""))[:10], {
            "minuti": 0, "libera_min_gb": None, "margine_gb": None, "sotto_margine": 0,
            "non_possibile": {}, "solo_scaricando": {}, "tempo_reale": 0, "divergenze": {},
            "richieste": {}, "rifiuti": 0, "partite": 0, "buttate": 0, "attesa_max_s": 0.0,
            "tenute_voce": 0})
        tipo = r.get("tipo")
        if tipo == "minuto":
            g["minuti"] += 1
            lib = r.get("libera_gb")
            if lib is not None:
                g["libera_min_gb"] = lib if g["libera_min_gb"] is None else min(
                    g["libera_min_gb"], lib)
            if r.get("margine_gb") is not None:
                g["margine_gb"] = r["margine_gb"]
                if lib is not None and lib < r["margine_gb"]:
                    g["sotto_margine"] += 1
            for ruolo, a in (r.get("a_richiesta") or {}).items():
                if a.get("caricato"):
                    continue
                if not a.get("ci_sta"):
                    g["non_possibile"][ruolo] = g["non_possibile"].get(ruolo, 0) + 1
                elif not a.get("senza_scaricare"):
                    g["solo_scaricando"][ruolo] = g["solo_scaricando"].get(ruolo, 0) + 1
            g["tempo_reale"] += int(r.get("tempo_reale") or 0)
            g["tenute_voce"] += int(r.get("tenute_voce") or 0)
            for f, d in (r.get("divergenze") or {}).items():
                x = g["divergenze"].setdefault(f, {"vecchia_si": 0, "vecchia_no": 0, "s": 0.0})
                x["vecchia_si"] += int(d.get("vecchia_si") or 0)
                x["vecchia_no"] += int(d.get("vecchia_no") or 0)
                x["s"] = round(x["s"] + float(d.get("s") or 0), 1)
            for chi, n in (r.get("richieste") or {}).items():
                g["richieste"][chi] = g["richieste"].get(chi, 0) + int(n or 0)
        elif tipo == "richiesta":
            if r.get("gb") and r.get("ci_sta") is False:
                g["rifiuti"] += 1
            g["tempo_reale"] += len(r.get("tempo_reale") or [])
        elif tipo == "partita":
            g["partite"] += 1
            g["attesa_max_s"] = max(g["attesa_max_s"], float(r.get("attesa_s") or 0))
        elif tipo == "buttata":
            g["buttate"] += 1
    return {k: giorni[k] for k in sorted(giorni) if k}


def criterio(st: dict, margine_gb: float | None = None) -> dict:
    """Si va al passo 3 dopo `CRITERIO_GIORNI` giorni di registro senza «avrebbe scaricato il
    tempo reale» e con la memoria libera minima vera sopra il margine (§ 7 punto 2)."""
    ultimi = list(st.items())[-CRITERIO_GIORNI:]
    motivi = []
    con_dati = [(k, g) for k, g in ultimi if g["minuti"] > 0]
    if len(con_dati) < CRITERIO_GIORNI:
        motivi.append(f"giorni di registro: {len(con_dati)} su {CRITERIO_GIORNI}")
    tr = [k for k, g in ultimi if g["tempo_reale"]]
    if tr:
        motivi.append("avrebbe scaricato il tempo reale: " + ", ".join(tr))
    sotto = [k for k, g in con_dati if g["libera_min_gb"] is not None and (
        g["libera_min_gb"] < (g["margine_gb"] if g["margine_gb"] is not None
                              else margine_gb if margine_gb is not None else 0.0))]
    if sotto:
        motivi.append("memoria minima sotto il margine: " + ", ".join(sotto))
    return {"ok": not motivi, "motivi": motivi, "giorni": len(con_dati),
            "tempo_reale": sum(g["tempo_reale"] for _, g in ultimi)}


def _gb(x) -> str:
    return "—" if x is None else f"{float(x):.1f}".replace(".", ",")


def testo_storia(st: dict, modo_: str = OMBRA) -> str:
    r = [f"Arbitro della memoria in ombra (passo 2): {modo_}"]
    if not st:
        r.append("  Nessuna riga nel registro" + (" (arbitro_memoria: spento: si accende con "
                                                  "«arbitro_memoria: ombra» nel file locale)"
                                                  if modo_ == SPENTO else "") + ".")
    for giorno, g in st.items():
        np_ = ", ".join(f"{k} {n} min" for k, n in sorted(g["non_possibile"].items())) or "mai"
        ss = ", ".join(f"{k} {n} min" for k, n in sorted(g["solo_scaricando"].items()))
        r.append(f"  {giorno}  libera minima {_gb(g['libera_min_gb'])} GB (margine "
                 f"{_gb(g['margine_gb'])}), {g['minuti']} minuti")
        r.append(f"              a richiesta non possibile: {np_}"
                 + (f"; solo scaricando: {ss}" if ss else ""))
        r.append(f"              avrebbe scaricato il tempo reale: {g['tempo_reale']}"
                 + ("  ← AVVISO: deve essere 0" if g["tempo_reale"] else ""))
        if g["richieste"]:
            r.append("              richieste: " + ", ".join(
                f"{k} {n}" for k, n in sorted(g["richieste"].items()))
                + f"; partite {g['partite']}, attesa massima {_gb(g['attesa_max_s'])} s, "
                  f"buttate {g['buttate']}, rifiuti per memoria {g['rifiuti']}")
        if g["divergenze"]:
            r.append("              quiete() diversa: " + "; ".join(
                f"{f} {d['vecchia_si']}× libera solo per la vecchia, {d['vecchia_no']}× solo "
                f"per quiete ({_gb(d['s'])} s)" for f, d in sorted(g["divergenze"].items())))
        if g["sotto_margine"]:
            r.append(f"              minuti sotto il margine: {g['sotto_margine']}")
        if g.get("tenute_voce"):
            r.append(f"              voce liberata dalla tenuta massima: {g['tenute_voce']}"
                     "  ← AVVISO: deve essere 0 (un posto occupa la voce e non la libera)")
    c = criterio(st)
    tot_tr = sum(g["tempo_reale"] for g in st.values())
    if tot_tr:
        r.append(f"AVVISO: in {sum(1 for g in st.values() if g['tempo_reale'])} giorni l'arbitro "
                 f"avrebbe scaricato il tempo reale ({tot_tr} volte): la politica è sbagliata, "
                 "non andare avanti.")
    r.append(f"Criterio per il passo 3: {CRITERIO_GIORNI} giorni senza scaricare il tempo reale "
             "e memoria libera minima sopra il margine — "
             + ("soddisfatto." if c["ok"] else "non ancora (" + "; ".join(c["motivi"]) + ")."))
    return "\n".join(r)
