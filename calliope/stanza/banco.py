"""
L'audio della stanza per il banco del passo 3 (14/10 sera, **eccezione temporanea** alla decisione
0029 punto 1, «mai l'audio su disco»: decisa da chi amministra, scritta nella decisione 0029).

Con `stanza_audio_banco_giorni: N` (di serie 0 = mai) e la corsia lenta accesa (`stanza_lenta`),
per N giorni dalla **prima accensione** l'audio dei segmenti della stanza va su disco, con le
trascrizioni della corsia veloce (v1) e della lenta (v2), per misurare WER e attribuzione sul
banco `prove/manuali/banco_stanza_lenta.py` (il riferimento lo scrive a mano chi amministra).

**Solo** quando **tutte** le voci del segmento sono persone di casa riconosciute dalla voce
sopra soglia: la riga (o le righe, se la corsia lenta l'ha spezzato) di una persona di casa con
`sicurezza: voce` in **tutte e due** le versioni (una zona grigia corretta dalla corsia lenta resta
fuori), e nessuna finestra CAM++ del segmento di una voce non riconosciuta. Adulti di
casa e minori della famiglia (autorizzati dal tutore per questo banco); **mai** ospiti, conoscenti,
zona grigia, voci sconosciute, «più voci», TV; mai in pausa («abbiamo ospiti»).

- **Dove**: `<turn_log_dir>/stanza_banco/<satellite>/<AAAA-MM-GG>/<ora>-<segmento>.wav` (μ-law
  16 kHz come la voce conservata, `conserva.wav_mulaw`) e accanto `.json` (satellite, stanza,
  tempi, v1, v2, persone, finestre: niente altro), file 600 e cartelle 700; `acceso.json` dice da
  quando vale l'eccezione.
- **Scadenza**: dopo N giorni dalla prima accensione smette da sé (lo dice nel log una volta e in
  `calliope stato --turni`); per ricominciare si cancella la cartella (`calliope conserva
  --svuota`). I file restano per `turn_log_days` (la rotazione a ogni giorno nuovo).
- **Cancellazione**: «dimentica» toglie i file del satellite; `calliope conserva --svuota` tutto
  (anche da un altro processo); `--persona` i segmenti in cui c'è la sua voce.

Solo libreria standard e `conserva` (μ-law, scrittura privata).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

CARTELLA = "stanza_banco"
ACCESO = "acceso.json"
GIORNO_S = 86400.0


def cartella(cfg) -> Path | None:
    d = getattr(cfg, "turn_log_dir", None)
    return Path(d) / CARTELLA if d else None


def giorni(cfg) -> int:
    try:
        return max(0, int(getattr(cfg, "stanza_audio_banco_giorni", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _nome_file(x) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(x))[:60] or "_"


class Banco:
    def __init__(self, cfg, log=print):
        self.cfg, self.log = cfg, log
        self.dir = cartella(cfg)
        self._lock = threading.Lock()
        self._detto_scaduto = False
        self._ultima_rotazione = None
        self.salvati = 0
        self.saltati: dict = {}

    # ── l'eccezione: accesa, scaduta ──
    def _marcatore(self, crea: bool) -> dict | None:
        if self.dir is None:
            return None
        p = self.dir / ACCESO
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not crea:
            return None
        from ..conserva import _scrivi_privato
        m = {"dal": time.time(), "giorni": giorni(self.cfg)}
        _scrivi_privato(p, json.dumps(m).encode("utf-8"))
        self.log(f"   [STANZA] Audio della stanza per il banco su disco per {m['giorni']} giorni "
                 f"(solo voci di casa riconosciute), fino al "
                 f"{datetime.date.fromtimestamp(m['dal'] + m['giorni'] * GIORNO_S).isoformat()}")
        return m

    def fino(self) -> float | None:
        m = self._marcatore(False)
        if not m:
            return None
        return float(m.get("dal") or 0) + giorni(self.cfg) * GIORNO_S

    def attivo(self, ora: float | None = None) -> bool:
        """Vale adesso l'eccezione? Accesa nel file, con la corsia lenta, e non scaduta (la prima
        volta segna l'accensione)."""
        if giorni(self.cfg) <= 0 or self.dir is None or not getattr(self.cfg, "stanza_lenta",
                                                                    False):
            return False
        ora = time.time() if ora is None else float(ora)
        with self._lock:
            m = self._marcatore(True)
        if m is None:
            return False
        if ora > float(m.get("dal") or 0) + giorni(self.cfg) * GIORNO_S:
            if not self._detto_scaduto:
                self._detto_scaduto = True
                self.log("   [STANZA] Audio del banco: eccezione scaduta, non salvo più niente "
                         "(i file fatti restano per il banco fino alla rotazione)")
            return False
        return True

    # ── chi si può salvare ──
    @staticmethod
    def ammesso(righe: list[dict], finestre_ignote: int, registry=None) -> tuple[bool, str]:
        """(sì/no, motivo): tutte le righe del segmento di persone di casa riconosciute dalla
        voce sopra soglia, nessuna finestra di una voce non riconosciuta."""
        if not righe:
            return False, "nessuna_riga"
        for r in righe:
            chi = str(r.get("chi") or "")
            if chi.startswith("conoscente:"):
                return False, "conoscente"
            if not chi.startswith("persona:"):
                return False, "voce_ignota" if chi in ("ignoto", "") else chi
            if r.get("sicurezza") != "voce":
                return False, "zona_grigia"
        if finestre_ignote:
            return False, "finestre_ignote"
        return True, ""

    def salva(self, sat, info: dict | None, seg: dict, pcm_int16: bytes, sr: int,
              v1: dict | None, v2: list[dict], finestre_ignote: int = 0,
              in_pausa: bool = False, ora: float | None = None) -> str | None:
        """Il segmento su disco se vale l'eccezione e le voci lo permettono: il percorso
        relativo, o None (contato in `saltati` per motivo)."""
        def salta(m):
            self.saltati[m] = self.saltati.get(m, 0) + 1
            return None
        if not self.attivo(ora):
            return None
        if in_pausa:
            return salta("pausa")
        # Le righe di tutte e due le versioni: una zona grigia della corsia veloce corretta
        # dalla lenta resta fuori (nel dubbio no)
        righe = ([v1] if v1 else []) + list(v2 or [])
        ok, motivo = self.ammesso(righe, finestre_ignote)
        if not ok:
            return salta(motivo)
        import numpy as np
        from ..conserva import _scrivi_privato, wav_mulaw
        audio = np.frombuffer(pcm_int16, dtype="<i2").astype(np.float32) / 32768.0
        ini = float(seg.get("inizio") or time.time())
        quando = datetime.datetime.fromtimestamp(ini)
        rel = (f"{_nome_file(sat)}/{quando.date().isoformat()}/"
               f"{quando.strftime('%H%M%S')}-{_nome_file(seg.get('segmento'))}")
        persone = sorted({str(r.get("persona") or str(r.get("chi"))[len("persona:"):])
                          for r in righe})
        meta = {"sat": str(sat), "stanza": (info or {}).get("stanza"),
                "satellite": (info or {}).get("nome"), "segmento": seg.get("segmento"),
                "scambio": seg.get("scambio"), "inizio": ini, "fine": seg.get("fine"),
                "voce_s": seg.get("voce_s"), "persone": persone,
                # «uguale»: la corsia lenta ha dato lo stesso testo (v2 vuota qui)
                "esito_lenta": seg.get("esito"),
                "v1": _pulita(v1), "v2": [_pulita(r) for r in v2]}
        try:
            _scrivi_privato(self.dir / (rel + ".wav"), wav_mulaw(audio, sr))
            _scrivi_privato(self.dir / (rel + ".json"),
                            json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
        except OSError as e:
            self.log(f"   [STANZA] audio del banco non salvato: {type(e).__name__}")
            return salta("errore")
        self.salvati += 1
        self._ruota_se_serve()
        return rel

    # ── cancellare ──
    def dimentica(self, sat) -> int:
        if self.dir is None:
            return 0
        d = self.dir / _nome_file(sat)
        n = sum(1 for _ in d.rglob("*.wav")) if d.exists() else 0
        shutil.rmtree(d, ignore_errors=True)
        return n

    def _ruota_se_serve(self):
        oggi = datetime.date.today()
        if self._ultima_rotazione == oggi:
            return
        self._ultima_rotazione = oggi
        ruota(self.cfg)


def _pulita(r: dict | None) -> dict | None:
    if not r:
        return None
    return {k: r.get(k) for k in ("testo", "chi", "nome", "persona", "sicurezza", "inizio",
                                  "fine", "parte", "versione", "minore") if k in r}


def ruota(cfg) -> int:
    """Via le cartelle dei giorni oltre `turn_log_days`."""
    d = cartella(cfg)
    if d is None or not d.exists():
        return 0
    limite = datetime.date.today() - datetime.timedelta(
        days=int(getattr(cfg, "turn_log_days", 60) or 60))
    n = 0
    for g in d.glob("*/*"):
        try:
            if g.is_dir() and datetime.date.fromisoformat(g.name) < limite:
                n += sum(1 for _ in g.glob("*.wav"))
                shutil.rmtree(g, ignore_errors=True)
        except ValueError:
            continue
    return n


def svuota(cfg, persona=None) -> int:
    """`calliope conserva --svuota` (anche da un altro processo): tutto, compreso il segno
    dell'accensione (si ricomincia solo riaccendendo), o i segmenti con la voce di `persona`.
    Quanti file audio."""
    d = cartella(cfg)
    if d is None or not d.exists():
        return 0
    if persona is None:
        n = sum(1 for _ in d.rglob("*.wav"))
        shutil.rmtree(d, ignore_errors=True)
        return n
    n = 0
    for j in d.rglob("*.json"):
        if j.name == ACCESO:
            continue
        try:
            meta = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(persona) in [str(p) for p in meta.get("persone") or ()]:
            w = j.with_suffix(".wav")
            n += w.exists()
            w.unlink(missing_ok=True)
            j.unlink(missing_ok=True)
    return n


def stato_file(cfg) -> dict | None:
    """Per `calliope stato --turni`: None se l'eccezione non è mai stata accesa; altrimenti
    accesa/scaduta, fino a quando, quanti file e MB (mai parole)."""
    d = cartella(cfg)
    n_g = giorni(cfg)
    if d is None or (not d.exists() and n_g <= 0):
        return None
    m = None
    try:
        m = json.loads((d / ACCESO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        m = None
    wav = list(d.rglob("*.wav")) if d.exists() else []
    mb = 0.0
    for w in wav:
        try:
            mb += w.stat().st_size / 1e6
        except OSError:
            pass
    fino = float(m["dal"]) + n_g * GIORNO_S if m and n_g > 0 else None
    return {"giorni": n_g, "dal": m.get("dal") if m else None, "fino": fino,
            "scaduta": bool(fino is not None and time.time() > fino),
            "file": len(wav), "mb": round(mb, 1),
            "senza_lenta": n_g > 0 and not getattr(cfg, "stanza_lenta", False)}


def testo_stato(d: dict | None) -> str | None:
    if not d:
        return None
    if d["giorni"] <= 0:
        stato = "spenta nel file"
    elif d.get("senza_lenta"):
        stato = "accesa ma senza stanza_lenta: non salva niente"
    elif d.get("fino") is None:
        stato = f"accesa per {d['giorni']} giorni, non ancora partita"
    elif d.get("scaduta"):
        stato = (f"SCADUTA il {datetime.date.fromtimestamp(d['fino']).isoformat()}: non salva "
                 "più niente")
    else:
        stato = f"accesa fino al {datetime.date.fromtimestamp(d['fino']).isoformat()}"
    return (f"  Audio della stanza per il banco (eccezione del 14/10, solo voci di casa): "
            f"{stato}; {d['file']} segmenti, {d['mb']:.1f} MB")


__all__ = ["Banco", "giorni", "ruota", "stato_file", "svuota", "testo_stato"]
