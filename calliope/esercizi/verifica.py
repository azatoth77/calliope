"""
I controlli degli esercizi d'italiano (08/10/2026, decisione di Dario del 07/10: al posto
della revisione di un adulto).

- **Wikizionario della biblioteca** (`Wikizionario`): la parte del discorso che il lessico dà a
  ogni parola della frase deve comparire tra quelle della sua voce (sezione «Italiano»:
  Sostantivo, Aggettivo, Voce verbale…). Senza il file ZIM il controllo si salta e si scrive.
- **Secondo modello** (`SecondoParere`): un modello risolve l'esercizio da solo, con la sola
  domanda e le opzioni chiuse (output strutturato, enum), senza vedere la risposta. Se non dà
  la stessa risposta, l'esercizio si scarta. Di predefinito è il modello della voce sullo
  stesso Ollama (nessun modello in più da tenere caricato); `esercizi_verifica_modello` ne
  sceglie un altro (sulla DGX qwen3.6 o il 26B).

Il controllo si fa una volta per esercizio (per firma): l'esito resta in `esercizi_banco`
(registro.py), e un esercizio buono si riusa senza rifare la domanda al modello.
"""

from __future__ import annotations

import re
import threading
import time
from html.parser import HTMLParser

from .modello import Esercizio
from . import italiano as IT

# Intestazione del Wikizionario → parte del discorso degli esercizi
_SEZIONI = (("sostantivo", "nome"), ("nome", "nome"), ("aggettivo", "aggettivo"),
            ("articolo", "articolo"), ("pronome", "pronome"), ("voce verbale", "verbo"),
            ("verbo", "verbo"), ("avverbio", "avverbio"), ("preposizione", "preposizione"),
            ("congiunzione", "congiunzione"), ("interiezione", "interiezione"))


class _Intestazioni(HTMLParser):
    """Le intestazioni h3 della sezione «Italiano» di una voce."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        # Alcune voci («lungo») non hanno l'intestazione «Italiano»: prima di un h2 vale
        self.italiano = True
        self.tag = None
        self.buf = ""
        self.sezioni: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3"):
            self.tag, self.buf = tag, ""

    def handle_endtag(self, tag):
        if tag != self.tag:
            return
        t = re.sub(r"\s+", " ", self.buf).strip().lower()
        if tag == "h2":
            self.italiano = t.startswith("italiano")
        elif self.italiano:
            self.sezioni.append(t)
        self.tag = None

    def handle_data(self, data):
        if self.tag:
            self.buf += data


def parti_da_html(html_text: str) -> set[str]:
    p = _Intestazioni()
    p.feed(html_text)
    out = set()
    for s in p.sezioni:
        for pref, parte in _SEZIONI:
            if s.startswith(pref):
                out.add(parte)
                break
    return out


class Wikizionario:
    """Le parti del discorso di una forma secondo il Wikizionario (file ZIM della biblioteca).
    `archivio`: un oggetto con `has_entry_by_path` e `get_entry_by_path` (calliope.zim)."""

    def __init__(self, archivio=None, path: str | None = None):
        self._arch = archivio
        if self._arch is None and path:
            from ..zim import ZimFile
            self._arch = ZimFile(path)
        self._cache: dict[str, set[str] | None] = {}
        self._lock = threading.Lock()

    @property
    def pronto(self) -> bool:
        return self._arch is not None

    @staticmethod
    def da_config(cfg, biblioteca=None) -> "Wikizionario | None":
        diz = getattr(biblioteca, "dizionario", None)
        if diz is not None:
            return Wikizionario(diz.archive)
        try:
            from pathlib import Path
            from ..installa.catalogo import risolvi_zim
            p = risolvi_zim(getattr(cfg, "biblioteca_dizionario", None))
            if p and Path(p).exists():
                return Wikizionario(path=str(p))
        except Exception:  # noqa: BLE001 — senza dizionario il controllo si salta
            return None
        return None

    def parti(self, forma: str) -> set[str] | None:
        """Le parti del discorso della voce (None se la voce non c'è)."""
        if self._arch is None:
            return None
        with self._lock:
            if forma in self._cache:
                return self._cache[forma]
        out = None
        for path in dict.fromkeys((forma.lower(), forma)):
            try:
                if not self._arch.has_entry_by_path(path):
                    continue
                e = self._arch.get_entry_by_path(path)
                hops = 0
                while e.is_redirect and hops < 5:
                    e, hops = e.get_redirect_entry(), hops + 1
                out = parti_da_html(bytes(e.get_item().content).decode("utf-8", "replace"))
                break
            except Exception:  # noqa: BLE001 — una voce illeggibile vale «assente»
                continue
        with self._lock:
            self._cache[forma] = out
        return out

    def controlla_frase(self, parole: list) -> tuple[bool, list[str]]:
        """(tutte le parole tornano, [problemi]). Una parola assente dal Wikizionario o con
        una parte che la sua voce non ha è un problema."""
        problemi = []
        for forma, parte in parole:
            p = self.parti(forma)
            if p is None:
                problemi.append(f"«{forma}» non è nel Wikizionario")
            elif parte not in p:
                problemi.append(f"«{forma}»: {parte} non è tra {sorted(p)}")
        return not problemi, problemi


# ─────────────────────────── secondo modello ───────────────────────────

PROMPT_GRAMMATICA = ("Analisi grammaticale di una frase italiana semplice.\nFrase: «{frase}»\n"
                     "Che parte del discorso è la parola «{parola}» in questa frase? Rispondi "
                     "con una sola delle parti del discorso possibili.")
PROMPT_RUOLO = ("Analisi logica di una frase italiana semplice.\nFrase: «{frase}»\nChe "
                "funzione logica ha «{gruppo}» in questa frase? Rispondi con una sola delle "
                "opzioni.")
PROMPT_GRUPPO = ("Analisi logica di una frase italiana semplice.\nFrase: «{frase}»\nQual è il "
                 "{ruolo} di questa frase? Rispondi con una sola delle parti della frase "
                 "elencate (scritta esattamente così).")


class SecondoParere:
    """Il secondo modello su Ollama (API nativa, output strutturato). Senza modello (backend
    non Ollama e nessun modello configurato) `pronto` è False."""

    def __init__(self, cfg, client=None):
        self.cfg = cfg
        self.modello = str(getattr(cfg, "esercizi_verifica_modello", "") or "")
        url = str(getattr(cfg, "esercizi_verifica_url", "") or "")
        if not self.modello and str(getattr(cfg, "llm_backend", "ollama")) == "ollama":
            self.modello = str(getattr(cfg, "llm_model", "") or "")
        self.url = (url or str(getattr(cfg, "llm_native_url", "") or
                               "http://127.0.0.1:11434")).rstrip("/")
        self.timeout_s = float(getattr(cfg, "esercizi_verifica_timeout_s", 20.0) or 20.0)
        self._client = client
        self.ultimo_ms = None
        self.ultimo_errore = ""

    @property
    def pronto(self) -> bool:
        return bool(self.modello)

    def _http(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=self.timeout_s)
        return self._client

    def chiedi(self, prompt: str, opzioni: list[str]) -> str | None:
        """Una delle opzioni secondo il modello, o None (guasto, tempo scaduto)."""
        cfg = self.cfg
        stesso = self.modello == str(getattr(cfg, "llm_model", ""))
        try:
            from .. import contesto
            num_ctx = contesto.finestra(cfg) if stesso else 2048
            from ..config import keep_alive_valido
            keep = keep_alive_valido(getattr(cfg, "llm_keep_alive", "-1m")) if stesso else "5m"
        except Exception:  # noqa: BLE001
            num_ctx, keep = int(getattr(cfg, "llm_num_ctx", 16384) or 16384), "-1m"
        body = {"model": self.modello, "stream": False, "think": False, "keep_alive": keep,
                "messages": [{"role": "user", "content": prompt}],
                "format": {"type": "object", "properties": {"risposta": {
                    "type": "string", "enum": list(opzioni)}}, "required": ["risposta"]},
                "options": {"temperature": 0, "num_predict": 40, "num_ctx": num_ctx}}
        t0 = time.perf_counter()
        try:
            r = self._http().post(self.url + "/api/chat", json=body, timeout=self.timeout_s)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            import json
            testo = (r.json().get("message") or {}).get("content") or ""
            v = json.loads(testo).get("risposta")
        except Exception as e:  # noqa: BLE001
            self.ultimo_errore = type(e).__name__
            self.ultimo_ms = round((time.perf_counter() - t0) * 1000, 1)
            return None
        self.ultimo_ms = round((time.perf_counter() - t0) * 1000, 1)
        return v if v in opzioni else None

    def risolvi(self, es: Esercizio) -> str | None:
        """La risposta del secondo modello, nella stessa forma di `es.risposta` (per i
        gruppi: il testo del gruppo)."""
        d = es.dati
        if es.argomento == "analisi_grammaticale":
            return self.chiedi(PROMPT_GRAMMATICA.format(frase=d["frase"], parola=d["parola"]),
                               list(IT.PARTI))
        if es.tipo == "scelta":
            return self.chiedi(PROMPT_RUOLO.format(frase=d["frase"], gruppo=d["gruppo"]),
                               list(IT.RUOLI) + ["altro complemento"])
        gruppi = [" ".join(d["parole"][i][0] for i in idx) for idx, _ in d["gruppi"]]
        nome = "predicato" if d["ruolo"].startswith("predicato") else d["ruolo"]
        return self.chiedi(PROMPT_GRUPPO.format(frase=d["frase"], ruolo=nome), gruppi)


def attesa(es: Esercizio) -> str:
    """La risposta giusta nella forma del secondo parere."""
    if es.argomento == "analisi_logica" and es.tipo == "parole":
        return es.dati["gruppo"]
    return str(es.risposta)


def verifica_italiano(es: Esercizio, diz: Wikizionario | None,
                      parere: SecondoParere | None) -> dict:
    """{"esito": "buono"|"scartato"|"non_verificato", "wikizionario": …, "modello": …,
    "problemi": […]}. «non_verificato»: il secondo modello non ha risposto (guasto)."""
    out: dict = {"tipo": "linguistico"}
    problemi: list[str] = []
    if diz is not None and diz.pronto:
        ok, prob = diz.controlla_frase([tuple(p) for p in es.dati.get("parole", [])])
        out["wikizionario"] = "ok" if ok else "no"
        problemi += prob
    else:
        out["wikizionario"] = "assente"
    if problemi:
        out.update(esito="scartato", problemi=problemi)
        return out
    if parere is None or not parere.pronto:
        out.update(esito="non_verificato", modello="assente")
        return out
    r = parere.risolvi(es)
    out["modello"] = parere.modello
    out["modello_ms"] = parere.ultimo_ms
    if r is None:
        out.update(esito="non_verificato", errore=parere.ultimo_errore or "risposta non valida")
        return out
    out["parere"] = r
    out["esito"] = "buono" if r == attesa(es) else "scartato"
    if out["esito"] == "scartato":
        out["problemi"] = [f"il secondo modello dice «{r}», il generatore «{attesa(es)}»"]
    return out
