"""
«Prova il microfono» della web app del telefono (03/10/2026): il server riceve due
registrazioni brevi fatte dal telefono, le salva come WAV con i metadati e risponde con un
riassunto leggibile.

Perché: dal telefono vero l'audio arrivava rovinato (Whisper trascriveva parole in
islandese, l'impronta vocale dava 0,11–0,24 contro 0,6–0,75 dal portatile) e da qui non si
vedeva il motivo. Ogni prova porta due segnali dello stesso momento: quello che entra nel
worklet (alla frequenza del contesto audio del browser) e l'uscita a 16 kHz che andrebbe a
Calliope, più frequenze (contesto, traccia, riproduzione), orologi (vero e del contesto),
blocchi persi, ripetuti o a zero e livelli. Il riassunto dice cosa non torna.

Formato del corpo (POST /telefono/api/diagnostica, application/octet-stream):
  «CDG1» · lunghezza del JSON (uint32 big-endian) · JSON dei metadati (UTF-8) ·
  i segmenti in int16 little-endian, nell'ordine di `segmenti` ({prova, tipo, rate, campioni}).

Le registrazioni sono la voce di chi parla: stanno in <config_dir>/diagnostica/telefono/
(fuori da git), al massimo DIAG_MAX cartelle e DIAG_GIORNI giorni, e si cancellano da sole.
"""

import json
import re
import shutil
import time
import wave
from pathlib import Path

import numpy as np

MAGIA = b"CDG1"
MAX_BYTE = 6 * 2 ** 20
MAX_JSON = 64 * 1024
MAX_SEGMENTI = 8
DIAG_GIORNI = 7
DIAG_MAX = 30
TOLLERANZA_RITMO = 0.06


class ErroreDiagnostica(ValueError):
    pass


def cartella(cfg) -> Path:
    base = Path(str(getattr(cfg, "config_dir", "") or "."))
    return base / "diagnostica" / "telefono"


def leggi_corpo(dati: bytes) -> tuple[dict, list[tuple[dict, np.ndarray]]]:
    """Metadati e segmenti (float32 in [-1, 1]); ErroreDiagnostica se il corpo non va."""
    if len(dati) < 8 or dati[:4] != MAGIA:
        raise ErroreDiagnostica("formato sconosciuto")
    n = int.from_bytes(dati[4:8], "big")
    if n <= 0 or n > MAX_JSON or 8 + n > len(dati):
        raise ErroreDiagnostica("metadati non validi")
    try:
        meta = json.loads(dati[8:8 + n].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ErroreDiagnostica("metadati non validi") from None
    if not isinstance(meta, dict) or not isinstance(meta.get("segmenti"), list):
        raise ErroreDiagnostica("metadati non validi")
    segs = meta["segmenti"]
    if not 1 <= len(segs) <= MAX_SEGMENTI:
        raise ErroreDiagnostica("numero di segmenti non valido")
    o = 8 + n
    out = []
    for s in segs:
        if not isinstance(s, dict):
            raise ErroreDiagnostica("segmento non valido")
        try:
            rate = int(s.get("rate"))
            campioni = int(s.get("campioni"))
            prova = int(s.get("prova"))
        except (TypeError, ValueError):
            raise ErroreDiagnostica("segmento non valido") from None
        tipo = str(s.get("tipo"))
        if tipo not in ("grezzo", "uscita") or not 3000 <= rate <= 192000 or campioni < 0 \
                or not 0 <= prova < MAX_SEGMENTI:
            raise ErroreDiagnostica("segmento non valido")
        fine = o + 2 * campioni
        if fine > len(dati):
            raise ErroreDiagnostica("dati troncati")
        x = np.frombuffer(dati[o:fine], dtype="<i2").astype(np.float32) / 32768.0
        out.append(({"prova": prova, "tipo": tipo, "rate": rate, "campioni": campioni}, x))
        o = fine
    if o != len(dati):
        raise ErroreDiagnostica("dati in più")
    return meta, out


# ───────────────────────────── misure ─────────────────────────────
def _db(v: float) -> float:
    return round(20 * float(np.log10(v)), 1) if v > 0 else -120.0


def ricampiona(x: np.ndarray, da: int, a: int) -> np.ndarray:
    """Ricampionamento con la FFT (solo numpy): per confrontare, non per l'ascolto."""
    if da == a or len(x) == 0:
        return x.astype(np.float32)
    n = int(round(len(x) * a / da))
    X = np.fft.rfft(x)
    m = n // 2 + 1
    Y = np.zeros(m, dtype=complex)
    k = min(m, len(X))
    Y[:k] = X[:k]
    return (np.fft.irfft(Y, n) * (n / len(x))).astype(np.float32)


def correlazione(a: np.ndarray, b: np.ndarray, max_lag: int) -> tuple[float, int]:
    """La correlazione normalizzata migliore tra a e b entro ±max_lag campioni."""
    n = min(len(a), len(b))
    if n < 1600:
        return 0.0, 0
    a = a[:n] - a[:n].mean()
    b = b[:n] - b[:n].mean()
    m = 1 << int(np.ceil(np.log2(2 * n)))
    c = np.fft.irfft(np.fft.rfft(a, m) * np.conj(np.fft.rfft(b, m)), m)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([c[:max_lag + 1], c[-max_lag:]])
    i = int(np.argmax(vals))
    lag = int(lags[i])
    if lag >= 0:
        aa, bb = a[lag:], b[:n - lag]
    else:
        aa, bb = a[:n + lag], b[-lag:]
    den = float(np.sqrt(np.dot(aa, aa) * np.dot(bb, bb)))
    return (float(np.dot(aa, bb)) / den if den > 0 else 0.0), lag


def tono(x: np.ndarray, sr: int = 16000) -> float | None:
    """Frequenza fondamentale mediana delle parti con voce (autocorrelazione, 60–500 Hz):
    una voce adulta sta tra ~85 e ~260 Hz; molto fuori, l'audio è accelerato o rallentato."""
    w = int(0.04 * sr)
    if len(x) < w * 3:
        return None
    rms = np.sqrt(np.convolve(x * x, np.ones(w) / w, mode="valid")[::w // 2])
    soglia = max(1e-3, float(np.percentile(rms, 80)) * 0.5)
    f0 = []
    lo, hi = int(sr / 500), int(sr / 60)
    for j, r in enumerate(rms):
        if r < soglia:
            continue
        seg = x[j * (w // 2): j * (w // 2) + w]
        if len(seg) < w:
            break
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode="full")[w - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.45:
            f0.append(sr / k)
    return round(float(np.median(f0)), 0) if len(f0) >= 5 else None


def acuti(x: np.ndarray, sr: int) -> float:
    """Quota di energia sopra 4 kHz (la voce ne ha poca: un audio accelerato ne ha molta)."""
    if len(x) < 512:
        return 0.0
    S = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    tot = float(S[f > 80].sum())
    return round(float(S[f > 4000].sum()) / tot, 3) if tot > 0 else 0.0


def voce_vad(x: np.ndarray, cfg) -> float | None:
    """Secondi di voce secondo Silero VAD (lo stesso del server), o None se non c'è."""
    try:
        from ..vad import SileroOnnx, modello_onnx
        p = modello_onnx(getattr(cfg, "vad_modello", None) or None)
        if p is None:
            return None
        v = SileroOnnx(p)
        soglia = float(getattr(cfg, "vad_threshold", 0.5))
        n = sum(1 for i in range(0, len(x) - 511, 512) if v.prob(x[i:i + 512]) >= soglia)
        return round(n * 512 / 16000, 2)
    except Exception:  # noqa: BLE001 — la diagnostica non deve cadere per il VAD
        return None


def impronta(x: np.ndarray, cfg, proprietario: str | None) -> float | None:
    """Somiglianza CAM++ tra questa registrazione e l'impronta del proprietario del telefono
    (in sola lettura: speakers.json non si tocca). None se non si può calcolare."""
    if not proprietario or len(x) < 16000:
        return None
    try:
        from ..speaker_id import SpeakerEmbedder, SpeakerRegistry, UserProfile
        path = Path(SpeakerRegistry.PATH)
        if not path.is_file() or not Path(str(cfg.speaker_model)).is_file():
            return None
        emb = SpeakerEmbedder(cfg.speaker_model, 1)
        for d in json.loads(path.read_text(encoding="utf-8")):
            if d.get("id") == proprietario:
                prof = UserProfile.from_dict(d, emb.model_name)
                if prof.voiceprint is None:
                    return None
                return round(float(np.dot(emb.embed(x, 16000), prof.voiceprint)), 3)
    except Exception:  # noqa: BLE001
        return None
    return None


def misura(meta: dict, segmenti: list[tuple[dict, np.ndarray]], cfg,
           proprietario: str | None = None) -> list[dict]:
    """Le misure di ogni prova (una per indice `prova`)."""
    prove = meta.get("prove") if isinstance(meta.get("prove"), list) else []
    out = []
    for i in sorted({s["prova"] for s, _ in segmenti}):
        pm = prove[i] if i < len(prove) and isinstance(prove[i], dict) else {}
        g = next(((s, x) for s, x in segmenti if s["prova"] == i and s["tipo"] == "grezzo"), None)
        u = next(((s, x) for s, x in segmenti if s["prova"] == i and s["tipo"] == "uscita"), None)
        m = {"prova": i, "etichetta": str(pm.get("etichetta") or f"prova {i + 1}")[:80]}
        vera = float(pm.get("durata_vera_s") or 0)
        ctxs = float(pm.get("durata_contesto_s") or 0)
        m["durata_vera_s"] = round(vera, 2)
        m["durata_contesto_s"] = round(ctxs, 2)
        m["ritmo"] = round(ctxs / vera, 3) if vera > 0 else None
        if g is not None:
            s, x = g
            m["rate_grezzo"] = s["rate"]
            m["durata_grezzo_s"] = round(len(x) / s["rate"], 2)
            m["picco_grezzo_db"] = _db(float(np.max(np.abs(x))) if len(x) else 0.0)
            m["rms_grezzo_db"] = _db(float(np.sqrt(np.mean(x * x))) if len(x) else 0.0)
            m["acuti_grezzo"] = acuti(x, s["rate"])
        if u is not None:
            s, x = u
            m["durata_uscita_s"] = round(len(x) / 16000, 2)
            m["picco_uscita_db"] = _db(float(np.max(np.abs(x))) if len(x) else 0.0)
            m["rms_uscita_db"] = _db(float(np.sqrt(np.mean(x * x))) if len(x) else 0.0)
            m["saturi_pct"] = round(100 * float(np.mean(np.abs(x) >= 0.999)), 3) if len(x) else 0.0
            m["acuti_uscita"] = acuti(x, 16000)
            m["tono_hz"] = tono(x)
            m["voce_s"] = voce_vad(x, cfg)
            m["impronta"] = impronta(x, cfg, proprietario)
        if g is not None and u is not None and len(g[1]) and len(u[1]):
            r = ricampiona(g[1], g[0]["rate"], 16000)
            c, lag = correlazione(u[1], r, 1600)
            m["uscita_uguale_grezzo"] = round(c, 3)
            m["scarto_campioni"] = lag
        q = int(pm.get("quanti") or 0)
        m["quanti_zero_pct"] = round(100 * int(pm.get("quanti_zero") or 0) / q, 2) if q else None
        m["quanti_doppi_pct"] = round(100 * int(pm.get("quanti_doppi") or 0) / q, 2) if q else None
        for k in ("persi", "fuori_ordine", "scartati_inferenza", "vuoti", "rate_contesto",
                  "rate_riproduzione", "ricostruito", "motivo_ricostruzione", "audio_session",
                  "stato_contesto"):
            m[k] = pm.get(k)
        tr = pm.get("traccia") if isinstance(pm.get("traccia"), dict) else {}
        m["rate_traccia"] = tr.get("sampleRate")
        m["correzioni"] = {k: tr.get(k) for k in ("echoCancellation", "noiseSuppression",
                                                   "autoGainControl")}
        out.append(m)
    return out


# ───────────────────────────── giudizio ─────────────────────────────
def _num(v, nd=2) -> str:
    return f"{v:.{nd}f}".replace(".", ",")


def problemi(m: dict, cfg=None) -> list[str]:
    """Cosa non torna in una prova, in parole."""
    p = []
    rt, rc = m.get("rate_traccia"), m.get("rate_contesto")
    if rt and rc and abs(float(rt) - float(rc)) > 1:
        p.append(f"il microfono registra a {rt} Hz ma il browser lo legge a {rc} Hz")
    r = m.get("ritmo")
    if r is not None and abs(r - 1) > TOLLERANZA_RITMO:
        p.append(f"l'audio scorre al ritmo sbagliato (×{_num(r)}: {_num(m['durata_contesto_s'], 1)} s "
                 f"di audio in {_num(m['durata_vera_s'], 1)} s veri)")
    du, dc = m.get("durata_uscita_s"), m.get("durata_contesto_s")
    if du is not None and dc and abs(du - dc) > max(0.15, 0.04 * dc):
        p.append(f"a 16 kHz escono {_num(du)} s su {_num(dc)} s di audio: blocchi persi o in più")
    for k, testo in (("persi", "blocchi persi"), ("fuori_ordine", "blocchi fuori ordine"),
                     ("scartati_inferenza", "blocchi scartati perché il telefono non sta dietro")):
        if m.get(k):
            p.append(f"{m[k]} {testo}")
    if (m.get("quanti_zero_pct") or 0) > 2:
        p.append(f"buchi nell'audio: {_num(m['quanti_zero_pct'], 1)} % di blocchi a zero")
    if (m.get("quanti_doppi_pct") or 0) > 1:
        p.append(f"blocchi ripetuti: {_num(m['quanti_doppi_pct'], 1)} %")
    if m.get("rms_uscita_db") is not None and m["rms_uscita_db"] < -55:
        p.append(f"segnale quasi muto ({_num(m['rms_uscita_db'], 0)} dB)")
    if (m.get("saturi_pct") or 0) > 0.1:
        p.append(f"segnale saturato ({_num(m['saturi_pct'], 1)} % dei campioni)")
    c = m.get("uscita_uguale_grezzo")
    if c is not None and c < 0.9 and (m.get("rms_grezzo_db") or -120) > -60:
        p.append(f"l'uscita a 16 kHz non somiglia al segnale d'ingresso (correlazione {_num(c)})")
    t = m.get("tono_hz")
    if t is not None and (t > 320 or t < 65):
        p.append(f"voce a {int(t)} Hz: troppo {'acuta' if t > 320 else 'grave'} per una voce "
                 f"vera, audio {'accelerato' if t > 320 else 'rallentato'}?")
    if m.get("voce_s") is not None and m["voce_s"] < 0.5 and (m.get("rms_uscita_db") or -120) > -55:
        p.append("il VAD di Calliope non sente voce")
    soglia = float(getattr(cfg, "speaker_id_threshold", 0.48)) if cfg is not None else 0.48
    if m.get("impronta") is not None and m["impronta"] < soglia and (m.get("voce_s") or 0) >= 1.0:
        p.append(f"impronta vocale {_num(m['impronta'])} (soglia {_num(soglia)}): non ti "
                 f"riconosco da questo microfono")
    if m.get("stato_contesto") not in (None, "running"):
        p.append(f"il contesto audio del browser è «{m['stato_contesto']}»")
    return p


def riassunto(meta: dict, misure: list[dict], cfg=None) -> list[str]:
    righe = []
    ua = str(meta.get("ua") or "")
    righe.append("Browser: " + (ua[:120] or "sconosciuto"))
    tutti = []
    for m in misure:
        righe.append("")
        righe.append(m["etichetta"])
        righe.append(f"  frequenze: microfono {m.get('rate_traccia') or '?'} Hz, contesto "
                     f"{m.get('rate_contesto') or '?'} Hz, riproduzione "
                     f"{m.get('rate_riproduzione') or '?'} Hz"
                     + (f" (contesto rifatto: {m['motivo_ricostruzione']})"
                        if m.get("motivo_ricostruzione") else ""))
        righe.append(f"  durata: {_num(m['durata_vera_s'])} s veri, {_num(m['durata_contesto_s'])} s "
                     f"di audio, {_num(m.get('durata_uscita_s') or 0)} s a 16 kHz"
                     + (f", ritmo ×{_num(m['ritmo'], 3)}" if m.get("ritmo") is not None else ""))
        righe.append(f"  livelli: picco {_num(m.get('picco_uscita_db', -120), 0)} dB, medio "
                     f"{_num(m.get('rms_uscita_db', -120), 0)} dB"
                     + (f", voce {_num(m['voce_s'], 1)} s" if m.get("voce_s") is not None else "")
                     + (f", tono {int(m['tono_hz'])} Hz" if m.get("tono_hz") else "")
                     + (f", impronta {_num(m['impronta'])}" if m.get("impronta") is not None else ""))
        corr = m.get("correzioni") or {}
        if any(v is not None for v in corr.values()):
            righe.append("  correzioni del browser: " + ", ".join(
                f"{n} {'sì' if corr.get(k) else 'no'}" for k, n in (
                    ("echoCancellation", "eco"), ("noiseSuppression", "rumore"),
                    ("autoGainControl", "guadagno"))))
        p = problemi(m, cfg)
        tutti += p
        righe += ["  ✗ " + x for x in p] or ["  ✓ audio a posto"]
    righe.append("")
    righe.append("Esito: " + ("qualcosa non va, i dettagli sono qui sopra." if tutti
                              else "l'audio arriva giusto."))
    return righe


# ───────────────────────────── salvataggio ─────────────────────────────
def _wav(path: Path, x: np.ndarray, rate: int):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def pulisci(base: Path, ora: float | None = None):
    """Via le prove più vecchie di DIAG_GIORNI giorni, e oltre le DIAG_MAX più recenti."""
    if not base.is_dir():
        return
    ora = time.time() if ora is None else ora
    cartelle = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    for i, p in enumerate(cartelle):
        try:
            vecchia = ora - p.stat().st_mtime > DIAG_GIORNI * 86400
        except OSError:
            continue
        if vecchia or i < len(cartelle) - DIAG_MAX:
            shutil.rmtree(p, ignore_errors=True)


def salva(cfg, nome: str, meta: dict, segmenti, misure: list[dict], righe: list[str]) -> Path:
    base = cartella(cfg)
    base.mkdir(parents=True, exist_ok=True)
    pulisci(base)
    slug = re.sub(r"[^a-z0-9]+", "-", (nome or "telefono").lower()).strip("-")[:30] or "telefono"
    dove = base / (time.strftime("%Y%m%d-%H%M%S") + "-" + slug)
    k = 1
    while dove.exists():
        k += 1
        dove = base / (time.strftime("%Y%m%d-%H%M%S") + f"-{slug}-{k}")
    dove.mkdir()
    for s, x in segmenti:
        _wav(dove / f"prova{s['prova'] + 1}-{s['tipo']}-{s['rate']}.wav", x, s["rate"])
    (dove / "meta.json").write_text(json.dumps({"meta": meta, "misure": misure}, indent=1,
                                               ensure_ascii=False, default=str), encoding="utf-8")
    (dove / "riassunto.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    return dove


def analizza(cfg, dati: bytes, nome: str = "telefono", proprietario: str | None = None) -> dict:
    """Dal corpo della richiesta al riassunto (e i file sul disco)."""
    meta, segs = leggi_corpo(dati)
    mis = misura(meta, segs, cfg, proprietario)
    righe = riassunto(meta, mis, cfg)
    dove = salva(cfg, nome, meta, segs, mis, righe)
    return {"ok": True, "riassunto": righe, "misure": mis, "cartella": dove.name}


__all__ = ["ErroreDiagnostica", "MAX_BYTE", "analizza", "cartella", "correlazione", "leggi_corpo",
           "misura", "problemi", "pulisci", "riassunto", "ricampiona", "tono"]
