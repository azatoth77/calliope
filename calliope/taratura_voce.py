"""Quanto costa la voce su questa macchina (07/10): sintesi per carattere e velocità di parlato.

Il taglio della prima frase (tts.primo_pezzo) ha bisogno di due numeri: quanti caratteri al
secondo dice la voce in uso e quanti secondi costa a Piper sintetizzarne uno. Dipendono dalla
voce (serena-high è 5 volte più lenta di una medium) e dalla macchina (DGX con 8 thread 3,5 ms a
carattere, portatile carico ~8 ms): non si tarano a mano, perché altri installeranno Calliope su
hardware che nessuno ha provato. Tre fonti, dalla più debole alla più forte:

1. **predefiniti prudenti** (PREDEFINITI): una macchina lenta, il primo pezzo esce più lungo;
2. **taratura all'avvio** (`Speaker._tara`, in un thread dopo il caricamento della voce,
   quando tutte le voci, anche quelle delle corsie, sono ferme da 20 s; si ferma e si riprova
   se intanto riparte una conversazione): una frase fissa sintetizzata tre volte (vale la più
   veloce); con `tts_thread: auto` e nessuna scelta salvata prova anche pochi numeri di thread (2, 4, 8, i core fisici) e tiene il più
   veloce;
3. **l'uso** (`Taratura.osserva`, ogni sintesi vera di almeno MIN_CARATTERI): la mediana delle
   ultime FINESTRA, scartati i valori anomali (oltre ANOMALO volte la mediana: la CPU presa da
   altro, un'altra corsia che sintetizza insieme). Vale da MIN_USO sintesi in su.

Tutto per voce e per numero di thread (cambiare i thread cambia il costo), salvato in
`voce_taratura.json` accanto a calliope.yaml (scrittura atomica, `persistenza.scrivi_json`),
così sopravvive ai riavvii. Senza `config_dir` (le prove, `Config()` nudo) resta in memoria."""
from __future__ import annotations

import copy
import os
import statistics
import threading
import time
from pathlib import Path

FILE = "voce_taratura.json"
PREDEFINITI = {"parlato_car_s": 15.0, "sintesi_s_car": 0.010}
MIN_USO = 30                # sintesi vere prima di fidarsi dell'uso
FINESTRA = 200              # ultime sintesi tenute per voce
MIN_CARATTERI = 20          # sotto, il costo fisso di Piper pesa troppo sul costo a carattere
ANOMALO = 4.0               # un valore oltre 4 volte (o sotto un quarto) la mediana si scarta
SALVA_OGNI_S = 30.0         # l'uso si salva al più ogni 30 s (e alla taratura)
FRASE = "Buongiorno, oggi il cielo è sereno e fuori c'è un bel sole."


def chiave(voce: str, thread) -> str:
    return f"{Path(str(voce or '?')).stem}@{thread or 'predefiniti'}"


def thread_di(voice) -> int | None:
    """I thread con cui la voce è stata aperta (tts.carica_voce li scrive sull'oggetto)."""
    n = getattr(voice, "calliope_thread", None)
    return n if isinstance(n, int) and n > 0 else None


def core_fisici() -> int:
    try:
        import psutil
        n = psutil.cpu_count(logical=False)
        if n:
            return int(n)
    except Exception:  # noqa: BLE001 — psutil c'è solo su Windows
        pass
    return max(1, os.cpu_count() or 1)


def candidati_thread() -> list[int]:
    logici = max(1, os.cpu_count() or 1)
    return sorted({n for n in (2, 4, 8, core_fisici()) if 1 <= n <= logici}) or [1]


class Taratura:
    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._salvata = 0.0
        self.dati: dict = {"voci": {}, "thread": {}}
        if path is not None:
            try:
                from .persistenza import leggi_json
                d, _ = leggi_json(path)
                if isinstance(d, dict):
                    self.dati["voci"] = d.get("voci") if isinstance(d.get("voci"), dict) else {}
                    self.dati["thread"] = (d.get("thread") if isinstance(d.get("thread"), dict)
                                           else {})
            except Exception as e:  # noqa: BLE001 — un file rovinato: si riparte da capo
                print(f"   [TTS] Taratura della voce non letta ({e}): riparto dai predefiniti",
                      flush=True)

    # ── lettura ──
    def _voce(self, k: str) -> dict:
        v = self.dati["voci"].setdefault(k, {})
        v.setdefault("uso", {"sintesi": [], "parlato": []})
        return v

    def stima(self, voce: str, thread=None) -> dict:
        """{"parlato_car_s", "sintesi_s_car", "fonte" ("uso"/"avvio"/"predefiniti"), "n"}."""
        with self._lock:
            v = self.dati["voci"].get(chiave(voce, thread)) or {}
            uso = v.get("uso") or {}
            s, p = uso.get("sintesi") or [], uso.get("parlato") or []
            if len(s) >= MIN_USO and len(p) >= MIN_USO:
                return {"parlato_car_s": statistics.median(p),
                        "sintesi_s_car": statistics.median(s), "fonte": "uso", "n": len(s)}
            a = v.get("avvio")
            if isinstance(a, dict) and a.get("sintesi_s_car") and a.get("parlato_car_s"):
                return {"parlato_car_s": float(a["parlato_car_s"]),
                        "sintesi_s_car": float(a["sintesi_s_car"]), "fonte": "avvio",
                        "n": len(s)}
            return {**PREDEFINITI, "fonte": "predefiniti", "n": len(s)}

    def thread_scelto(self, voce: str) -> int | None:
        """Il numero di thread scelto dalla taratura per questa voce (o per un'altra: la
        macchina è la stessa)."""
        t = self.dati.get("thread") or {}
        n = t.get(Path(str(voce or "?")).stem)
        if not isinstance(n, int):
            n = next((x for x in t.values() if isinstance(x, int)), None)
        return n if isinstance(n, int) and n > 0 else None

    # ── scrittura ──
    def osserva(self, voce: str, thread, caratteri: int, sintesi_s: float, audio_s: float):
        """Una sintesi vera: aggiorna la stima dall'uso (mediana robusta) e ogni tanto salva."""
        if caratteri < MIN_CARATTERI or sintesi_s <= 0 or audio_s <= 0:
            return
        s, p = sintesi_s / caratteri, caratteri / audio_s
        with self._lock:
            uso = self._voce(chiave(voce, thread))["uso"]
            for nome, x in (("sintesi", s), ("parlato", p)):
                serie = uso.setdefault(nome, [])
                if len(serie) >= 5:
                    m = statistics.median(serie)
                    if m > 0 and not (m / ANOMALO <= x <= m * ANOMALO):
                        return          # anomalo: la sintesi intera non conta
            uso["sintesi"].append(round(s, 6))
            uso["parlato"].append(round(p, 3))
            for nome in ("sintesi", "parlato"):
                del uso[nome][:-FINESTRA]
            dovuto = time.monotonic() - self._salvata >= SALVA_OGNI_S
        if dovuto:
            self.salva()

    def segna_avvio(self, voce: str, thread, parlato_car_s: float, sintesi_s_car: float,
                    thread_misure: dict | None = None):
        with self._lock:
            v = self._voce(chiave(voce, thread))
            v["avvio"] = {"parlato_car_s": round(parlato_car_s, 3),
                          "sintesi_s_car": round(sintesi_s_car, 6),
                          "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if thread_misure:
                self.dati["thread"][Path(str(voce)).stem] = int(thread)
                v["avvio"]["thread_misure"] = thread_misure
        self.salva()

    def salva(self):
        self._salvata = time.monotonic()
        if self.path is None:
            return
        from .persistenza import scrivi_json
        with self._lock:
            dati = copy.deepcopy(self.dati)
        try:
            scrivi_json(self.path, dati)
        except OSError as e:
            print(f"   [TTS] Taratura della voce non salvata ({e})", flush=True)


# ── una per cartella della configurazione ──
_TARATURE: dict[str, Taratura] = {}
_TARATURE_LOCK = threading.Lock()


def percorso(cfg) -> Path | None:
    forzato = os.environ.get("CALLIOPE_TARATURA_VOCE")
    if forzato:
        return Path(forzato)
    base = getattr(cfg, "config_dir", None)
    return Path(base) / FILE if base else None


def per(cfg) -> Taratura:
    p = percorso(cfg)
    k = str(p) if p is not None else f"memoria:{id(cfg)}"
    with _TARATURE_LOCK:
        t = _TARATURE.get(k)
        if t is None:
            t = _TARATURE[k] = Taratura(p)
        return t


# ── la taratura all'avvio ──
class Interrotta(Exception):
    """Una conversazione è ripartita durante la taratura: la si butta (07/10)."""


def _controlla(interrompi):
    if interrompi is not None and interrompi():
        raise Interrotta()


def misura(sintetizza, voice, rate: int, volte: int = 3,
           interrompi=None) -> tuple[float, float]:
    """(secondi di sintesi a carattere, caratteri al secondo di voce) della FRASE: la migliore
    di `volte` (la prima scalda la sessione). `sintetizza(voice, testo) → PCM int16`.
    `interrompi()` vero prima di una sintesi di prova → Interrotta (la voce prima di tutto)."""
    migliore, audio_s = float("inf"), 0.0
    for _ in range(max(1, volte)):
        _controlla(interrompi)
        t0 = time.perf_counter()
        pcm = sintetizza(voice, FRASE)
        migliore = min(migliore, time.perf_counter() - t0)
        audio_s = len(pcm) / 2 / max(1, rate)
    n = len(FRASE)
    return migliore / n, (n / audio_s if audio_s > 0 else PREDEFINITI["parlato_car_s"])


def prova_thread(voice, voice_path: str, sintetizza, rate: int,
                 candidati: list[int], interrompi=None) -> tuple[int, object, dict]:
    """Prova la voce con pochi numeri di thread (una sessione di onnxruntime per numero, su
    una copia della voce: quella in uso non si tocca). (migliore, sua sessione, misure).
    `interrompi` come in `misura`, controllato anche prima di ogni sessione."""
    import onnxruntime
    misure, tenuta = {}, (None, None)      # una sessione sola tenuta: la migliore finora
    for n in candidati:
        _controlla(interrompi)
        o = onnxruntime.SessionOptions()
        o.intra_op_num_threads = n
        o.inter_op_num_threads = 1
        sess = onnxruntime.InferenceSession(
            str(voice_path), sess_options=o,
            providers=voice.session.get_providers() or ["CPUExecutionProvider"])
        prova = copy.copy(voice)
        prova.session = sess
        misure[n] = round(misura(sintetizza, prova, rate, volte=3,
                                  interrompi=interrompi)[0], 6)
        # A parità (entro il 5 %) meno thread: lasciano CPU al resto (i candidati crescono)
        if tenuta[0] is None or misure[n] < misure[tenuta[0]] / 1.05:
            tenuta = (n, sess)
        del prova, sess
    return tenuta[0], tenuta[1], {str(k): v for k, v in misure.items()}


def thread_in_uso(cfg, voce: str) -> int:
    """I thread con cui si apre la voce (lo stesso criterio di tts.numero_thread): il numero
    scritto in `tts_thread`, con «auto» la scelta della taratura o 8, mai più dei processori
    logici. 0 = quelli di Piper."""
    n = getattr(cfg, "tts_thread", "auto")
    if isinstance(n, int) and not isinstance(n, bool):
        return max(0, n)
    return per(cfg).thread_scelto(voce) or min(8, os.cpu_count() or 8)


def testo_stato(cfg) -> str | None:
    """Per `calliope stato` e il registro delle capacità: la stima della voce in uso."""
    t = per(cfg)
    voce = getattr(cfg, "piper_voice", "")
    scritto = getattr(cfg, "tts_thread", "auto")
    thread = thread_in_uso(cfg, voce)
    s = t.stima(voce, thread)
    fonte = {"uso": f"dall'uso, {s['n']} sintesi", "avvio": "dalla taratura all'avvio",
             "predefiniti": "predefiniti prudenti, non ancora tarata"}[s["fonte"]]
    if not thread:
        quanti = "thread di Piper"
    elif isinstance(scritto, int):
        quanti = f"{thread} thread, scritti in tts_thread"
    elif t.thread_scelto(voce):
        quanti = f"{thread} thread, scelti dalla taratura"
    else:
        quanti = f"{thread} thread, da scegliere alla taratura"
    ms = f"{s['sintesi_s_car'] * 1000:.1f}".replace(".", ",")
    return (f"Voce {Path(str(voce)).stem}: sintesi {ms} ms a carattere, "
            f"{s['parlato_car_s']:.0f} caratteri al secondo ({fonte}); {quanti}.")
