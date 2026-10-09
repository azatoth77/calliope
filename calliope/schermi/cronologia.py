"""
La cronologia delle schede per persona, su disco (08/10/2026, richiesta di Dario).

Fino all'08/10 la cronologia stava solo in memoria, per schermo (`hub.Schermi._storia`, le
ultime `schermi_cronologia`): si perdeva a ogni riavvio, e uno schermo personale nuovo (un
satellite o un telefono appena abbinati) partiva vuoto. Qui ogni scheda **personale** destinata
agli schermi personali di una persona, con l'identità certa (mai la zona grigia, mai un
ospite), si salva nella cronologia di quella persona: un file JSON per persona in
`schermi_cronologia_cartella` (vuota = «schede» accanto a conversazioni.db), permessi 700/600
fuori da Windows come il cassetto, scritto in modo atomico da un thread suo un attimo dopo
(la voce e i tool non aspettano mai il disco). Tenuta `schermi_cronologia_giorni` (7), tetto
`schermi_cronologia_max` schede e `schermi_cronologia_mb` MB per persona: oltre escono le più
vecchie.

Le chiavi uniche valgono come nella cronologia degli schermi: una scheda con la stessa
`chiave` sostituisce quella di prima (al suo posto con `sposta: false`, altrimenti in fondo).
Si salva la scheda come resta nella cronologia (`hub.per_storia`: il flusso di un lavoro con
l'ultima finestra) più la sorgente di «Scarica» (`_scarica`, `_registro`), che resta sul
server: a uno schermo nuovo si registra di nuovo (il gettone lo chiede la pagina al tocco, ed è
sempre nuovo). Mai salvate: «vuota», le partite (`gioco`: legate a uno schermo e a una
partita viva) e il cruscotto (solo della pagina).

Quando uno schermo personale si collega, `rivedi` (chiamata da hub.Schermi.ripresa) controlla
ogni scheda contro lo stato vero: un modulo chiuso, un timer finito si saltano; l'avanzamento
di un lavoro che non lavora più diventa la scheda finale («interrotto», «finito»), senza il
flusso; gli esercizi chiusi diventano il loro riepilogo; uno sviluppo si ricostruisce da
`Sviluppi` (la vista dello sviluppo torna subito dopo un riavvio); il cassetto tiene solo i
file che ci sono ancora; un programma che girava prima di un riavvio è fermato.

Solo libreria standard.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

FORMATO = 1
# Una scheda salvata (JSON) al più: oltre si salva senza la sorgente di «Scarica», poi niente
MAX_SCHEDA = 512_000
# Mai su disco
NON_SALVATE = frozenset({"vuota", "gioco", "cruscotto", "chat"})
# Chiavi legate all'oggetto in memoria (id() di una foto, di un file, di una frase scritta):
# dopo un riavvio lo stesso numero è un'altra cosa, quindi valgono solo nello stesso avvio
EFFIMERE = ("foto:", "allegato:", "risposta:")
# Le chiavi private che restano (sul server, mai alle pagine)
PRIVATE = ("_scarica", "_registro")
# Debounce della scrittura: le schede in diretta (avanzamento) arrivano anche più volte al
# secondo, il disco una volta ogni tanto (un riavvio brusco perde al più questi secondi)
ATTESA_S = 2.0


def nome_file(persona: str) -> str:
    """Il file di una persona: l'id se è semplice, altrimenti un'impronta (come il cassetto)."""
    p = str(persona or "")
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", p):
        return p + ".json"
    return "p" + hashlib.sha256(p.encode()).hexdigest()[:24] + ".json"


def _privata(p: Path, cartella: bool):
    if os.name != "nt":
        try:
            os.chmod(p, 0o700 if cartella else 0o600)
        except OSError:
            pass


def _misura(voce: dict) -> int:
    return len(json.dumps(voce, ensure_ascii=False, default=str).encode("utf-8"))


def _peso(voce: dict) -> int:
    """I byte di una voce, calcolati una volta (`b`): la potatura gira a ogni aggiornamento
    in diretta, e ridurre in JSON tutta la cronologia ogni volta costerebbe."""
    b = voce.get("b")
    if not isinstance(b, int):
        b = voce["b"] = _misura(voce)
    return b


def da_salvare(scheda: dict, storia: dict) -> dict:
    """La scheda come si salva: quella della cronologia (`storia`, senza le chiavi private) con
    le sorgenti di «Scarica» della scheda intera."""
    out = {k: v for k, v in storia.items() if not str(k).startswith("_")}
    for k in PRIVATE:
        if k in scheda:
            out[k] = scheda[k]
    return out


class CronologiaSchede:
    """Le schede personali di ogni persona, su disco. Thread-safe: i tool, il server degli
    schermi e il thread di scrittura la usano insieme."""

    def __init__(self, cartella, giorni: float = 7.0, massimo: int = 40, mb: float = 4.0,
                 log=print, avvio: str | None = None, scrivi_subito: bool = False):
        self.cartella = Path(cartella)
        self.giorni = max(0.001, float(giorni))
        self.massimo = max(1, int(massimo))
        self.tetto = max(10_000, int(float(mb) * 1_000_000))
        self.log = log
        # L'avvio di questo processo: una scheda salvata da un avvio di prima si rivede di più
        # (un lavoro in diretta non può essere ancora vivo)
        self.avvio = avvio or uuid.uuid4().hex[:12]
        self.ora = time.time
        self.scritture = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        # La scrittura dei file ha un lock suo: chi aggiunge una scheda non aspetta mai il disco
        self._io = threading.Lock()
        self._dati: dict[str, list[dict]] = {}
        self._sporche: set[str] = set()
        self._fermo = False
        self._thread = None
        self._subito = scrivi_subito                 # prove: niente thread, scrive subito
        self.cartella.mkdir(parents=True, exist_ok=True)
        _privata(self.cartella, True)

    # ── lettura e potatura ──
    def _percorso(self, persona: str) -> Path:
        return self.cartella / nome_file(persona)

    def _leggi(self, persona: str) -> list[dict]:
        from ..persistenza import FileRovinato, leggi_json
        try:
            dati, _ = leggi_json(self._percorso(persona))
        except FileRovinato as e:
            self.log(f"[SCHERMI] cronologia di una persona illeggibile ({e}): riparte vuota")
            return []
        if (not isinstance(dati, dict) or dati.get("formato") != FORMATO
                or dati.get("persona") != persona):
            return []
        voci = [v for v in dati.get("schede") or ()
                if isinstance(v, dict) and isinstance(v.get("scheda"), dict)]
        return self._pota(voci)

    def _lista(self, persona: str) -> list[dict]:
        """Con il lock: le voci di `persona` (lette dal file la prima volta)."""
        if persona not in self._dati:
            self._dati[persona] = self._leggi(persona)
        return self._dati[persona]

    def _pota(self, voci: list[dict]) -> list[dict]:
        limite = self.ora() - self.giorni * 86400.0
        voci = [v for v in voci if float(v.get("t") or 0) >= limite][-self.massimo:]
        misure = [_peso(v) for v in voci]
        tot = sum(misure)
        while voci and tot > self.tetto:
            voci.pop(0)
            tot -= misure.pop(0)
        return voci

    def _stessa(self, v: dict, chiave: str) -> bool:
        if (v.get("scheda") or {}).get("chiave") != chiave:
            return False
        return not chiave.startswith(EFFIMERE) or v.get("avvio") == self.avvio

    # ── scrittura ──
    def aggiungi(self, persona: str | None, scheda: dict, storia: dict | None = None) -> bool:
        """La scheda (intera, con le chiavi private) nella cronologia di `persona`. `storia`: la
        forma della cronologia (hub.per_storia); senza, la scheda stessa. True se salvata."""
        if not persona or not isinstance(scheda, dict) or scheda.get("tipo") in NON_SALVATE:
            return False
        voce = {"t": self.ora(), "avvio": self.avvio,
                "scheda": da_salvare(scheda, storia if isinstance(storia, dict) else scheda)}
        if _misura(voce) > MAX_SCHEDA:
            voce["scheda"] = {k: v for k, v in voce["scheda"].items() if k not in PRIVATE}
            if _misura(voce) > MAX_SCHEDA:
                return False
        _peso(voce)
        k = voce["scheda"].get("chiave")
        with self._lock:
            lst = list(self._lista(persona))
            i = next((j for j, v in enumerate(lst) if self._stessa(v, k)), None) if k else None
            if i is not None and scheda.get("sposta") is False:
                lst[i] = voce                        # aggiornamento automatico: al suo posto
            else:
                if k:
                    lst = [v for v in lst if not self._stessa(v, k)]
                lst.append(voce)
            self._dati[persona] = self._pota(lst)
            self._sporca(persona)
        if self._subito:
            self.scrivi_ora()
        return True

    def ultime(self, persona: str | None) -> list[dict]:
        """Le voci di `persona` ({"t", "avvio", "scheda"}), dalla più vecchia, già potate."""
        if not persona:
            return []
        with self._lock:
            lst = self._pota(self._lista(persona))
            self._dati[persona] = lst
            return [dict(v) for v in lst]

    def pulisci(self, persona: str | None) -> int:
        """«Pulisci le mie schede»: la cronologia di `persona` vuota, anche su disco. Quante."""
        if not persona:
            return 0
        with self._lock:
            n = len(self._lista(persona))
            self._dati[persona] = []
            self._sporca(persona)
        if self._subito:
            self.scrivi_ora()
        return n

    def persone(self) -> list[str]:
        """Le persone con una cronologia, in memoria o su disco."""
        with self._lock:
            out = {p for p, v in self._dati.items() if v}
        for f in self.cartella.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and isinstance(d.get("persona"), str) and d["persona"]:
                out.add(d["persona"])
        return sorted(out)

    def togli(self, togliere) -> int:
        """Le schede per cui `togliere(scheda)` è vero escono dalla cronologia di tutte le
        persone, anche su disco (09/10: un'estensione eliminata non lascia schede che rimandano
        a lei). Quante."""
        n = 0
        for persona in self.persone():
            with self._lock:
                lst = list(self._lista(persona))
                tieni = [v for v in lst if not togliere(v.get("scheda") or {})]
                if len(tieni) != len(lst):
                    n += len(lst) - len(tieni)
                    self._dati[persona] = tieni
                    self._sporca(persona)
        if n and self._subito:
            self.scrivi_ora()
        return n

    def _sporca(self, persona: str):
        """Con il lock: il file di `persona` va riscritto (dal thread; con `scrivi_subito` lo
        scrive chi ha chiamato, appena lasciato il lock)."""
        self._sporche.add(persona)
        if self._subito:
            return
        if self._thread is None:
            self._thread = threading.Thread(target=self._ciclo, name="schermi-cronologia",
                                            daemon=True)
            self._thread.start()
        self._cond.notify_all()

    def _ciclo(self):
        while True:
            with self._lock:
                while not self._fermo and not self._sporche:
                    self._cond.wait()
                if self._fermo:
                    return
                self._cond.wait(ATTESA_S)     # gli aggiornamenti vicini insieme
            self.scrivi_ora()

    def scrivi_ora(self):
        """I file delle persone cambiate. La copia si prende con il lock delle schede, la
        scrittura (fsync) solo con quello dei file: in ordine, e senza far aspettare chi aggiunge."""
        from ..persistenza import scrivi_json
        with self._io:
            with self._lock:
                lavoro = [(p, list(self._dati.get(p) or [])) for p in self._sporche]
                self._sporche.clear()
            for persona, voci in lavoro:
                self._scrivi(scrivi_json, persona, voci)

    def _scrivi(self, scrivi_json, persona: str, voci: list[dict]):
        p = self._percorso(persona)
        try:
            if not voci:
                for x in (p, p.with_name(p.name + ".bak")):
                    x.unlink(missing_ok=True)
            else:
                scrivi_json(p, {"formato": FORMATO, "persona": persona, "schede": voci},
                            indent=None)
                _privata(p, False)
            self.scritture += 1
        except OSError as e:
            self.log(f"[SCHERMI] cronologia delle schede non salvata: {e}")

    def close(self):
        self.scrivi_ora()
        with self._lock:
            self._fermo = True
            self._cond.notify_all()


# ─────────────────────────── ripresa: le schede contro lo stato vero ───────────────────────────
def _lavoro(hub, ident: str):
    lavori = getattr(hub, "lavori", None)
    if lavori is None or not ident:
        return None
    try:
        return next((lv for lv in list(getattr(lavori, "lavori", None) or ())
                     if getattr(lv, "id", None) == ident), None)
    except Exception:  # noqa: BLE001
        return None


FRASE_INTERROTTO = "Si è interrotto per un riavvio di Calliope: chiedimi di rifarlo."


def lavoro_finale(c: dict, stato) -> dict:
    """L'avanzamento di un lavoro che non lavora più, come scheda finale: lo stato vero (o
    «interrotto»), senza il flusso e l'anteprima; i tetti e gli ultimi passi restano."""
    out = dict(c)
    st = stato if stato in ("fatto", "errore", "annullato", "scaduto", "interrotto",
                            "mancano_dati", "ripreso") else "interrotto"
    out["stato"] = "interrotto" if st == "ripreso" else st
    av = dict(out.get("avanzamento") or {})
    for k in ("flusso", "anteprima", "pausa"):
        av.pop(k, None)
    out["avanzamento"] = av
    if not out.get("riassunto"):
        out["riassunto"] = (FRASE_INTERROTTO if out["stato"] == "interrotto"
                            else "Finito: chiedimi il risultato." if out["stato"] == "fatto"
                            else "")
    out.pop("sposta", None)
    return out


def rivedi(hub, voce: dict, persona: str) -> dict | None:
    """La scheda salvata come va rimandata adesso, o None se non ha più senso."""
    c = dict(voce.get("scheda") or {})
    cron = getattr(hub, "cronologia", None)
    vecchia = voce.get("avvio") != getattr(cron, "avvio", None)
    tipo = c.get("tipo")
    ora = time.time()
    k = str(c.get("chiave") or "")
    if tipo in NON_SALVATE:
        return None
    if vecchia and k.startswith(EFFIMERE):
        c["chiave"] = f"{k}@{voce.get('avvio')}"
    if tipo == "modulo":
        moduli = getattr(hub, "moduli", None)
        aperto = moduli.aperto(c.get("modulo")) if moduli is not None else None
        return c if aperto is not None else None
    if tipo == "timer":
        vivi = [t for t in c.get("timer") or () if isinstance(t, dict)
                and (t.get("stato") or "attivo") == "attivo" and float(t.get("fine") or 0) > ora]
        return c if vivi else None
    if tipo == "sviluppo":
        svs = getattr(getattr(hub, "lavori", None), "sviluppi", None)
        ident = (c.get("sviluppo") or {}).get("id") or k.removeprefix("sviluppo:")
        sv = next((s for s in list(getattr(svs, "sviluppi", None) or ())
                   if s.id == ident and s.persona == persona), None) if svs else None
        if sv is None:
            return None
        try:
            return svs.scheda(sv)
        except Exception:  # noqa: BLE001
            return None
    if tipo == "esercizio":
        srv = getattr(hub, "esercizi", None)
        s = None
        try:
            s = srv.sessione(persona) if srv is not None else None
        except Exception:  # noqa: BLE001
            s = None
        if s is not None and k == f"esercizi:{persona}":
            try:
                return srv.scheda(s)
            except Exception:  # noqa: BLE001
                pass
        # Chiusi: il loro riepilogo, senza la domanda
        for x in ("domanda", "scelte", "esercizio", "tipo_risposta", "campo"):
            c.pop(x, None)
        if c.get("stato") == "aperta":
            c["stato"] = "finita"
            c["esito"] = {"testo": "Esercizi chiusi."}
        return c
    if tipo == "lavoro" and c.get("avanzamento") and c.get("stato") in ("in_coda", "in_corso",
                                                                       "in_attesa"):
        lv = _lavoro(hub, k.removeprefix("lavoro:"))
        st = getattr(lv, "stato", None)
        if st in ("in_coda", "in_corso") and not vecchia:
            return c
        if st == "in_attesa":
            c["stato"] = "in_attesa"
            return c
        return lavoro_finale(c, st)
    if tipo == "esecuzione" and c.get("stato") == "in_corso" and vecchia:
        c.update(stato="fermato", dal=None)
        return c
    if tipo == "cassetto":
        cas = getattr(hub, "cassetto", None)
        voci = [v for v in c.get("voci") or () if isinstance(v, dict)]
        if cas is not None:
            try:
                voci = [v for v in voci if cas.proprietario(v.get("id")) is not None]
            except Exception:  # noqa: BLE001
                pass
        if not voci and c.get("voci"):
            return None
        c["voci"] = voci
        return c
    return c
