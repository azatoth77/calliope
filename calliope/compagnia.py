"""
Più persone che parlano vicino allo stesso satellite: la «modalità compagnia» (09/10/2026,
docs/ricerche/2026-10-09-piu-persone.md, decisione di Dario dopo la rilettura dei momenti veri).

Il caso vero (DGX, telefono in un locale con un amico, 08–09/10): dopo ogni risposta la finestra
d'ascolto resta aperta `followup_s` senza il nome, e chiunque parli in quegli 8 s riceve una
risposta che riapre la finestra (66 frasi su 75 dei due episodi); l'amico, con la voce vicina a
quella del ragazzo, valeva il minore e ha fatto partire un avviso al tutore.

Una corsia (un satellite, o l'audio di questo computer) tiene **solo in memoria**, per
`compagnia_finestra_s` (5 minuti), le impronte CAM++ delle sue ultime frasi: mai su disco né
nel registro dei turni (lì solo numeri: quante voci, la prova, la distanza). Tre prove, sulle
frasi di quella finestra (regola sull'audio, principio 10: «ciò che il modello non vede»):

- **profilo** (misura B del documento): una persona è stata riconosciuta dalla voce e una frase
  di almeno `compagnia_voce_min_s` di nessuno (non riconosciuta) sta sotto `compagnia_soglia_profilo` (0,20) sul suo
  profilo. Stessa persona sotto 0,20: ≤ 0,5 % delle frasi (corpus) e 0 % di Dario tra microfoni e
  giorni diversi; un'altra voce: 66–90 %. In qualunque ordine;
- **gruppi** (misura C): le frasi di almeno `compagnia_gruppi_min_s` si raggruppano in linea
  (coseno col centroide ≥ `compagnia_soglia_gruppi`), partendo dai profili di chi è stato
  riconosciuto; un gruppo conta se ha due frasi o una di almeno `compagnia_gruppo_lungo_s`. Serve
  **tra ospiti** (due voci senza profilo, oggi entrambe «nessuno»). Due gruppi della stessa
  persona riconosciuta contano una voce sola (la voce variabile di chi è registrato);
- **due profili**: due persone registrate diverse riconosciute dalla voce (in auto con il
  minore).

Lo stato dice quante voci, la prova che ha deciso, la distanza e se tra le voci ce n'è una
**sconosciuta**: allora (con `compagnia_nome_obbligatorio`) la finestra d'ascolto senza il nome
si chiude finché le prove non escono dalla finestra (calliope/ciclo.py). Gli altri effetti (F1:
niente frase breve, continuità né zona grigia per le azioni; per i minori «voce non sicura» nei
due cancelli) valgono con `compagnia_enabled: attiva`; «ombra» registra soltanto.

`riassunto`/`testo`: la sezione di `calliope stato --turni` (solo numeri e regole).
"""
from __future__ import annotations

import dataclasses
import threading
import time

import numpy as np

SPENTA, OMBRA, ATTIVA = "spenta", "ombra", "attiva"


def modo(cfg) -> str:
    """`compagnia_enabled`: «attiva», «ombra» o «spenta» (un valore sconosciuto vale attiva, la
    scelta di Dario; False/True dal YAML valgono spenta/attiva)."""
    v = getattr(cfg, "compagnia_enabled", ATTIVA)
    if v is False:
        return SPENTA
    if v is True or v is None:
        return ATTIVA
    v = str(v).strip().lower()
    return v if v in (SPENTA, OMBRA, ATTIVA) else ATTIVA


def modo_rivolta(cfg) -> str:
    """`compagnia_rivolta`: il giudizio «la frase è rivolta a Calliope?» (F2)."""
    v = getattr(cfg, "compagnia_rivolta", OMBRA)
    if v is False:
        return SPENTA
    if v is True:
        return ATTIVA
    v = str(v or "").strip().lower()
    return v if v in (SPENTA, OMBRA, ATTIVA) else OMBRA


def _unit(v) -> np.ndarray | None:
    if v is None:
        return None
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else None


@dataclasses.dataclass
class Frase:
    """Una frase della corsia, solo in memoria: l'impronta, la durata della voce e la persona
    riconosciuta dalla voce sopra soglia (None: nessuno, o non sicura)."""
    ora: float
    emb: np.ndarray
    voce_s: float
    nome: str | None


class Compagnia:
    """Lo stato «in compagnia» di una corsia. `osserva` dopo il riconoscimento di ogni frase
    detta; `stato` legge senza aggiungere niente. Thread: la corsia è una, ma lo schermo può
    chiedere lo stato da un altro thread (lock breve)."""

    def __init__(self, cfg, registry=None, orologio=time.monotonic):
        self.cfg = cfg
        self.registry = registry
        self.orologio = orologio
        self._frasi: list[Frase] = []
        self._lock = threading.Lock()
        self._ultimo: dict | None = None        # l'ultimo stato calcolato (per i cambi)

    # ── configurazione ──
    def _f(self, nome: str, predefinito: float) -> float:
        try:
            return float(getattr(self.cfg, nome, predefinito))
        except (TypeError, ValueError):
            return predefinito

    @property
    def finestra_s(self) -> float:
        return self._f("compagnia_finestra_s", 300.0)

    @property
    def acceso(self) -> bool:
        return modo(self.cfg) != SPENTA

    # ── memoria ──
    def _pulisci(self, ora: float):
        w = self.finestra_s
        self._frasi = [f for f in self._frasi if ora - f.ora <= w]

    def dimentica(self):
        """Via tutte le impronte (riavvio della corsia, prove)."""
        with self._lock:
            self._frasi.clear()
            self._ultimo = None

    def __len__(self):
        with self._lock:
            return len(self._frasi)

    def osserva(self, emb, voce_s: float, nome: str | None) -> dict | None:
        """Una frase detta su questa corsia: la tiene in memoria (se c'è l'impronta) e
        restituisce lo stato (None: una voce sola, o spenta)."""
        if not self.acceso:
            return None
        v = _unit(emb)
        ora = self.orologio()
        with self._lock:
            self._pulisci(ora)
            if v is not None:
                self._frasi.append(Frase(ora, v, float(voce_s or 0.0), nome or None))
            st = self._calcola()
            self._ultimo = st
            return st

    def stato(self) -> dict | None:
        """Lo stato adesso (le frasi uscite dalla finestra non contano più)."""
        if not self.acceso:
            return None
        with self._lock:
            self._pulisci(self.orologio())
            st = self._calcola()
            self._ultimo = st
            return st

    # ── le prove ──
    def _profilo(self, nome: str):
        reg = self.registry
        prof = reg.get(nome) if reg is not None and nome else None
        return _unit(getattr(prof, "voiceprint", None)) if prof is not None else None

    def _calcola(self) -> dict | None:
        frasi = self._frasi
        if not frasi:
            return None
        nomi = list(dict.fromkeys(f.nome for f in frasi if f.nome))
        profili = {n: p for n in nomi if (p := self._profilo(n)) is not None}
        # 1. Contro il profilo di chi è stato riconosciuto: una frase non sua, abbastanza lunga,
        #    lontanissima dal suo profilo
        soglia_p = self._f("compagnia_soglia_profilo", 0.20)
        min_p = self._f("compagnia_voce_min_s", 1.0)
        dist_p = None
        for n, vp in profili.items():
            for f in frasi:
                # Solo le frasi di nessuno: una persona registrata riconosciuta dalla voce è la
                # prova «due profili», non una voce sconosciuta (in auto Carlo e Luca stanno a
                # 0,17 tra loro)
                if f.nome is not None or f.voce_s < min_p:
                    continue
                c = float(np.dot(f.emb, vp))
                if c < soglia_p and (dist_p is None or c < dist_p):
                    dist_p = c
        # 2. Gruppi tra frasi (le voci senza profilo), dai profili di chi è stato riconosciuto
        tau = self._f("compagnia_soglia_gruppi", 0.25)
        min_g = self._f("compagnia_gruppi_min_s", 1.5)
        lungo = self._f("compagnia_gruppo_lungo_s", 3.0)
        gruppi = [{"somma": vp.copy(), "n": 2, "lunga": True, "nomi": {n}}
                  for n, vp in profili.items()]
        for f in frasi:
            if f.voce_s < min_g:
                continue
            migliore, sim = None, -2.0
            for g in gruppi:
                c = float(np.dot(_unit(g["somma"]), f.emb))
                if c > sim:
                    migliore, sim = g, c
            if migliore is not None and sim >= tau:
                migliore["somma"] = migliore["somma"] + f.emb
                migliore["n"] += 1
                migliore["lunga"] |= bool(lungo > 0 and f.voce_s >= lungo)
                if f.nome:
                    migliore["nomi"].add(f.nome)
            else:
                gruppi.append({"somma": f.emb.copy(), "n": 1,
                               "lunga": bool(lungo > 0 and f.voce_s >= lungo),
                               "nomi": {f.nome} if f.nome else set()})
        confermati = [g for g in gruppi if g["n"] >= 2 or g["lunga"]]
        senza_nome = [g for g in confermati if not g["nomi"]]
        etichette = set(nomi)
        for g in confermati:
            etichette |= g["nomi"]
        sconosciute = len(senza_nome) + (1 if dist_p is not None and not senza_nome else 0)
        voci = len(etichette) + sconosciute
        if voci < 2:
            return None
        if dist_p is not None:
            prova, dist = "profilo", dist_p
        elif senza_nome:
            prova = "gruppi"
            # Quanto si somigliano le due voci più vicine tra i gruppi contati
            cent = [_unit(g["somma"]) for g in confermati]
            dist = max((float(np.dot(a, b)) for i, a in enumerate(cent) for b in cent[i + 1:]),
                       default=None)
        else:
            prova, dist = "due_profili", None
        return {"voci": int(voci), "prova": prova,
                "distanza": None if dist is None else round(dist, 3),
                "sconosciute": bool(sconosciute)}


# ─────────────────────────── calliope stato --turni ───────────────────────────

REGOLE = ("voci_compagnia", "compagnia_nome", "compagnia_senza_breve",
          "compagnia_voce_nella_frase", "pericolo_compagnia", "non_rivolta_ombra", "non_rivolta")


def riassunto(turni: list[dict]) -> dict:
    """Per giorno: frasi con la voce, quante in compagnia (per prova, con voci sconosciute), le
    regole della compagnia e i giudizi «rivolta a Calliope» (quanti, quanti no, tempo, guasti).
    Solo numeri: nessun testo."""
    giorni: dict[str, dict] = {}
    for t in turni:
        v = t.get("voce") if isinstance(t.get("voce"), dict) else None
        r = t.get("rivolta") if isinstance(t.get("rivolta"), dict) else None
        regole = [x for x in (t.get("regole") or ()) if x in REGOLE]
        if v is None and r is None and not regole:
            continue
        data = str(t.get("inizio") or "")[:10] or "?"
        d = giorni.setdefault(data, {"frasi": 0, "in_compagnia": 0, "sconosciute": 0,
                                     "prove": {}, "regole": {}, "giudizi": 0, "no": 0,
                                     "guasti": 0, "ms": []})
        if v is not None and "punteggio" in v:
            d["frasi"] += 1
        c = v.get("compagnia") if v is not None and isinstance(v.get("compagnia"), dict) else None
        if c:
            d["in_compagnia"] += 1
            d["sconosciute"] += bool(c.get("sconosciute"))
            p = str(c.get("prova") or "?")
            d["prove"][p] = d["prove"].get(p, 0) + 1
        for x in regole:
            d["regole"][x] = d["regole"].get(x, 0) + 1
        if r is not None:
            d["giudizi"] += 1
            if r.get("per_calliope") is False:
                d["no"] += 1
            if r.get("guasto"):
                d["guasti"] += 1
            if isinstance(r.get("ms"), (int, float)):
                d["ms"].append(float(r["ms"]))
    for d in giorni.values():
        ms = sorted(d.pop("ms"))
        d["ms_mediana"] = round(ms[len(ms) // 2]) if ms else None
    return dict(sorted(giorni.items()))


def testo(giorni: dict) -> str:
    if not giorni:
        return "Compagnia (più voci vicino a un satellite): nessun turno nel registro."
    righe = ["Compagnia (più voci vicino allo stesso satellite; giudizio «rivolta a Calliope»)",
             ""]
    for data, d in giorni.items():
        riga = f"{data}  {d['frasi']} frasi con la voce, in compagnia {d['in_compagnia']}"
        if d["in_compagnia"]:
            riga += (f" (con voci sconosciute {d['sconosciute']}; "
                     + ", ".join(f"{k} {v}" for k, v in d["prove"].items()) + ")")
        righe.append(riga)
        if d["regole"]:
            righe.append("    regole: " + ", ".join(f"{k} {v}" for k, v in d["regole"].items()))
        if d["giudizi"]:
            righe.append(f"    giudizi «rivolta a Calliope»: {d['giudizi']}, non rivolte "
                         f"{d['no']}, guasti {d['guasti']}"
                         + (f", mediana {d['ms_mediana']} ms" if d["ms_mediana"] is not None
                            else ""))
    return "\n".join(righe)
