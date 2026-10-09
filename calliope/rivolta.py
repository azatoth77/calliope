"""
«La frase è rivolta a Calliope?» (09/10/2026, F2 della modalità compagnia,
docs/ricerche/2026-10-09-piu-persone.md § 3.6).

In compagnia, dentro la finestra d'ascolto e senza il nome, il significato della frase lo
decide il modello (principio 10): un giudizio separato con l'output strutturato
`{"per_calliope": true|false}` sul modello del rilevatore di pericolo (già caricato sulla DGX),
in parallelo alla risposta. Misura sul portatile (gemma4:e4b-it-qat, 56 frasi di fantasia,
prove/prova_rivolta_ollama.py): 26/27 rivolte e 27/29 non rivolte giuste, mediana 287 ms, con il
nome di chi ha la conversazione nel contesto (`etichetta`); l'indizio della voce non serve e non
va nel prompt. Una regola sulle parole («nomina un'altra persona») sbaglia proprio sui contrari
(«Ricorda che a Giulia piace la pizza»).

Interruttore `compagnia_rivolta`: «ombra» (predefinito per i primi giorni: registra il giudizio
e la regola `non_rivolta_ombra`, non tace), «attiva» (frase non rivolta → silenzio e niente
finestra nuova, regola `non_rivolta`), «spenta». Un giudizio guasto o scaduto vale «rivolta»:
il giudizio è una cortesia, non una protezione (al più Calliope risponde come prima).
"""
from __future__ import annotations

import dataclasses
import json
import time

PROMPT = ("Sei il filtro di un'assistente vocale di casa che si chiama Calliope. Dopo una sua "
          "risposta il microfono resta aperto qualche secondo e sente anche le persone che "
          "parlano tra loro. Decidi se l'ultima frase è rivolta a Calliope (una domanda, un "
          "comando, un seguito o una risposta a ciò che ha detto lei) oppure a un'altra persona "
          "presente (chiacchiere, commenti su Calliope in terza persona, frasi che nominano un "
          "altro come interlocutore). Nel dubbio, se la frase è un seguito plausibile della "
          "conversazione con Calliope, è rivolta a lei. "
          'Rispondi solo con JSON {"per_calliope": true|false}.')
SCHEMA = {"type": "object", "properties": {"per_calliope": {"type": "boolean"}},
          "required": ["per_calliope"]}


@dataclasses.dataclass
class Giudizio:
    per_calliope: bool | None          # None: guasto (vale «rivolta»)
    ms: float = 0.0
    guasto: str | None = None

    def per_registro(self, modo: str) -> dict:
        d = {"per_calliope": self.per_calliope, "ms": round(self.ms), "modo": modo}
        if self.guasto:
            d["guasto"] = self.guasto
        return d

    @property
    def rivolta(self) -> bool:
        return self.per_calliope is not False


def dove(cfg) -> tuple[str, str] | None:
    """(url, modello) del giudizio: `compagnia_rivolta_modello`, altrimenti il rilevatore di
    pericolo (`guardiano_pericolo_modello`), altrimenti il modello della voce se è su Ollama."""
    m = str(getattr(cfg, "compagnia_rivolta_modello", "") or "")
    url = ""
    if not m:
        m = str(getattr(cfg, "guardiano_pericolo_modello", "") or "")
        url = str(getattr(cfg, "guardiano_pericolo_url", "") or "")
    if not m:
        if str(getattr(cfg, "llm_backend", "ollama")) != "ollama":
            return None
        m = str(getattr(cfg, "llm_model", "") or "")
    url = url or str(getattr(cfg, "llm_native_url", "") or "http://127.0.0.1:11434")
    return (url.rstrip("/"), m) if m else None


def _opzioni(cfg, url: str, modello: str) -> tuple[int, object]:
    """num_ctx e keep_alive: quelli della voce se è lo stesso modello (cambiare num_ctx ricarica
    il modello), altrimenti quelli del guardiano (come il rilevatore: nessun ricaricamento)."""
    stesso = modello == str(getattr(cfg, "llm_model", "")) and url == str(
        getattr(cfg, "llm_native_url", "")).rstrip("/")
    try:
        from .config import keep_alive_valido
        from .contesto import finestra
        if stesso:
            return finestra(cfg), keep_alive_valido(getattr(cfg, "llm_keep_alive", "-1m"))
        return int(getattr(cfg, "guardiano_num_ctx", 2048)), getattr(
            cfg, "guardiano_keep_alive", "-1m")
    except Exception:  # noqa: BLE001
        return int(getattr(cfg, "guardiano_num_ctx", 2048) or 2048), "-1m"


def etichetta(nome: str | None) -> str:
    """Come si chiama nel contesto chi parlava con Calliope: il nome di chi ha la conversazione,
    se è registrato («Carlo (registrato)»), altrimenti «Persona». Misura del 09/10 (gemma4 e4b,
    prove/prova_rivolta_ollama.py): con il nome 26/27 rivolte e 27/29 non rivolte giuste, con
    «Persona» 27/27 e 24/29 («Questa era terribile, Marco.» si capisce solo col nome)."""
    return f"{nome} (registrato)" if nome else "Persona"


def righe_contesto(history, massimo: int = 4,
                   persona: str = "Persona") -> list[tuple[str, str]]:
    """Gli ultimi scambi (persona / Calliope) della conversazione, solo testo, dal più vecchio."""
    out = []
    for m in reversed(list(history or [])):
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        c = m.get("content")
        if not isinstance(c, str) or not c.strip() or m.get("tool_calls"):
            continue
        out.append((persona if m["role"] == "user" else "Calliope", c.strip()[:400]))
        if len(out) >= massimo:
            break
    return list(reversed(out))


def messaggi(contesto: list[tuple[str, str]], frase: str) -> list[dict]:
    righe = [f"{chi}: {t}" for chi, t in contesto]
    righe.append(f"Frase nuova: {frase.strip()[:400]}")
    return [{"role": "system", "content": PROMPT}, {"role": "user", "content": "\n".join(righe)}]


class Giudice:
    """Il giudizio su Ollama (API nativa, output strutturato), con un client httpx come il
    guardiano; `chiama` sostituibile nelle prove."""

    def __init__(self, cfg, chiama=None):
        self.cfg = cfg
        self._chiama = chiama
        self._sessione = None

    def _http(self):
        if self._sessione is None:
            import httpx
            self._sessione = httpx.Client()
        return self._sessione

    def giudica(self, contesto: list[tuple[str, str]], frase: str,
                timeout: float | None = None) -> Giudizio:
        t0 = time.perf_counter()
        timeout = float(timeout or getattr(self.cfg, "compagnia_rivolta_timeout_s", 2.0) or 2.0)
        try:
            if self._chiama is not None:
                testo = self._chiama(messaggi(contesto, frase), timeout)
            else:
                testo = self._ollama(messaggi(contesto, frase), timeout)
            per = json.loads(testo).get("per_calliope")
            if not isinstance(per, bool):
                raise ValueError("risposta senza per_calliope")
        except Exception as e:  # noqa: BLE001 — guasto: vale «rivolta»
            return Giudizio(None, (time.perf_counter() - t0) * 1000, type(e).__name__)
        return Giudizio(per, (time.perf_counter() - t0) * 1000)

    def _ollama(self, msgs: list[dict], timeout: float) -> str:
        d = dove(self.cfg)
        if d is None:
            raise RuntimeError("nessun modello")
        url, modello = d
        num_ctx, keep = _opzioni(self.cfg, url, modello)
        body = {"model": modello, "stream": False, "think": False, "keep_alive": keep,
                "messages": msgs, "format": SCHEMA,
                "options": {"temperature": 0, "num_predict": 20, "num_ctx": num_ctx}}
        r = self._http().post(url + "/api/chat", json=body, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return (r.json().get("message") or {}).get("content") or ""
