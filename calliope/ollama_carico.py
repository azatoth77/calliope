"""
Quanti modelli tiene Ollama e quanti ne usa Calliope (06/10/2026, prova end-to-end sulla DGX).

Sulla DGX lo stesso Ollama serve la voce (gemma4 26B), il guardiano dei minori
(llama-guard3), il rilevatore di pericolo (gemma4 e4b) e gli embedding dell'archivio delle
conversazioni (qwen3-embedding): quattro modelli, e Ollama ne tiene residenti al più
`OLLAMA_MAX_LOADED_MODELS` (3 di predefinito per GPU). Il primo embedding scacciava il
guardiano o la voce: turni di minori e ospiti da 10–17 s e «guardiano guasto».

Qui:
- `residenti(url)`: i modelli caricati adesso (`/api/ps`, con una cache di pochi secondi);
- `limite(cfg)`: il limite di Ollama, da `ollama_max_modelli`, dalla variabile
  OLLAMA_MAX_LOADED_MODELS di questo processo o dal servizio systemd di Ollama
  (`systemctl show`, in sola lettura, senza sudo); se non si legge, 3 («assunto»);
- `usati(cfg)`: i modelli che Calliope usa su ogni Ollama (voce, guardiano, rilevatore,
  embedding);
- `avviso(cfg)`: la frase per l'avvio e per `calliope stato` quando i modelli che Calliope usa
  su un Ollama sono più del suo limite;
- `puo_caricare(url, modello)`: un modello si può usare senza scacciarne un altro (è già
  residente, o c'è posto). Lo usano gli embedding (calliope/conversazioni.py).

Solo libreria standard e httpx (già una dipendenza di base).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time

LIMITE_PREDEFINITO = 3          # quello di Ollama con una GPU (3 × GPU)
CACHE_S = 3.0

_cache: dict[str, tuple[float, list[str] | None]] = {}
_lock = threading.Lock()
_sistema: list = []             # [(quando, (limite, fonte) | None)]: letto ogni 5 minuti


def _nome(m: str) -> str:
    m = str(m or "").strip()
    return m if ":" in m else m + ":latest"


def residenti(url: str, timeout: float = 1.0, fresca: bool = False) -> list[str] | None:
    """I modelli caricati in Ollama adesso (`/api/ps`), o None se non risponde."""
    url = (url or "").rstrip("/")
    ora = time.monotonic()
    with _lock:
        t, v = _cache.get(url, (0.0, None))
        if not fresca and ora - t < CACHE_S and v is not None:
            return list(v)
    try:
        import httpx
        r = httpx.get(url + "/api/ps", timeout=timeout)
        r.raise_for_status()
        v = [_nome(m.get("name") or m.get("model") or "") for m in r.json().get("models") or []]
    except Exception:  # noqa: BLE001 — Ollama giù o un altro server: non si sa
        v = None
    with _lock:
        _cache[url] = (time.monotonic(), v)
    return list(v) if v is not None else None


def dimentica_cache():
    with _lock:
        _cache.clear()
        _sistema.clear()


def _da_servizio() -> int | None:
    """OLLAMA_MAX_LOADED_MODELS dal servizio systemd di Ollama (Linux), in sola lettura."""
    if not sys.platform.startswith("linux"):
        return None
    for unita in (["systemctl", "show", "ollama.service", "--property=Environment"],
                  ["systemctl", "--user", "show", "ollama.service", "--property=Environment"]):
        try:
            out = subprocess.run(unita, capture_output=True, text=True, timeout=2,
                                 stdin=subprocess.DEVNULL).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        m = re.search(r"OLLAMA_MAX_LOADED_MODELS=(\d+)", out or "")
        if m:
            return int(m.group(1))
    return None


def limite(cfg) -> tuple[int, str]:
    """(limite, da dove): «configurazione», «ambiente», «servizio» o «assunto»."""
    n = int(getattr(cfg, "ollama_max_modelli", 0) or 0)
    if n > 0:
        return n, "configurazione"
    with _lock:
        if _sistema and time.monotonic() - _sistema[0][0] < 300:
            letto = _sistema[0][1]
        else:
            letto = None
            v = os.environ.get("OLLAMA_MAX_LOADED_MODELS", "").strip()
            if v.isdigit() and int(v) > 0:
                letto = (int(v), "ambiente")
            else:
                s = _da_servizio()
                if s:
                    letto = (s, "servizio")
            _sistema[:] = [(time.monotonic(), letto)]
    return letto or (LIMITE_PREDEFINITO, "assunto")


def usati(cfg) -> dict[str, list[tuple[str, str]]]:
    """{url di Ollama: [(a cosa serve, modello)]} dei modelli che Calliope usa (distinti)."""
    out: dict[str, list[tuple[str, str]]] = {}

    def metti(url, chi, modello):
        url, modello = str(url or "").rstrip("/"), str(modello or "").strip()
        if not url or not modello or url.endswith("/v1"):
            return
        lista = out.setdefault(url, [])
        if _nome(modello) not in {_nome(m) for _, m in lista}:
            lista.append((chi, modello))

    voce_url = str(getattr(cfg, "llm_native_url", "") or "http://127.0.0.1:11434")
    if str(getattr(cfg, "llm_backend", "ollama")) == "ollama":
        metti(voce_url, "voce", getattr(cfg, "llm_model", ""))
    if getattr(cfg, "minori_enabled", True) and getattr(cfg, "guardiano_enabled", True):
        g_url = getattr(cfg, "guardiano_url", "") or voce_url
        metti(g_url, "guardiano", getattr(cfg, "guardiano_modello", ""))
        if getattr(cfg, "guardiano_pericolo", True):
            m = getattr(cfg, "guardiano_pericolo_modello", "") or (
                getattr(cfg, "llm_model", "") if str(getattr(cfg, "llm_backend", "ollama"))
                == "ollama" else "")
            metti(getattr(cfg, "guardiano_pericolo_url", "") or voce_url, "rilevatore di "
                  "pericolo", m)
    if getattr(cfg, "conversazioni_enabled", True):
        m = getattr(cfg, "conversazioni_embedding", "") or ""
        if m:
            from .conversazioni import url_embedding
            metti(url_embedding(cfg), "embedding delle conversazioni", m)
    return out


def avviso(cfg, timeout: float = 1.0) -> dict | None:
    """Se su un Ollama Calliope usa più modelli del limite: {frase, passo, dettagli}."""
    n, fonte = limite(cfg)
    for url, modelli in usati(cfg).items():
        if len(modelli) <= n:
            continue
        res = residenti(url, timeout=timeout)
        quali = ", ".join(f"{m} ({chi})" for chi, m in modelli)
        lim = (f"{n}" + (" (assunto: il limite di Ollama non si legge da qui)"
                         if fonte == "assunto" else ""))
        frase = (f"Ollama tiene al più {lim} modelli ma Calliope ne usa {len(modelli)}: "
                 f"{quali}. Uno scaccia l'altro e i turni rallentano; gli embedding delle "
                 f"conversazioni aspettano che Calliope sia inattiva")
        passo = (f"Imposta OLLAMA_MAX_LOADED_MODELS={len(modelli)} nel servizio di Ollama "
                 f"(sudo systemctl edit ollama, poi sudo systemctl restart ollama), o "
                 f"ollama_max_modelli in calliope.locale.yaml se il limite è già più alto.")
        return {"frase": frase, "passo": passo,
                "dettagli": {"limite": n, "fonte": fonte, "usati": len(modelli),
                             "residenti": res, "url": url}}
    return None


def puo_caricare(url: str, modello: str, cfg=None, timeout: float = 1.0) -> bool:
    """Il modello si può usare senza scacciarne un altro: è già residente, oppure Ollama ha
    un posto libero. Se Ollama non risponde: no (non si sa)."""
    res = residenti(url, timeout=timeout)
    if res is None:
        return False
    if _nome(modello) in res:
        return True
    n = limite(cfg)[0] if cfg is not None else LIMITE_PREDEFINITO
    return len(res) < n


def residente(url: str, modello: str, timeout: float = 1.0) -> bool:
    res = residenti(url, timeout=timeout)
    return bool(res) and _nome(modello) in res
