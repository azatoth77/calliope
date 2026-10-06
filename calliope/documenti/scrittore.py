"""
Lo scrittore: la chiamata all'LLM che produce il JSON del documento.

È una richiesta separata da quella della conversazione: il tool vocale riceve solo una
richiesta breve (formato e cosa scrivere, come detto), qui il modello scrive il contenuto.
Negli argomenti di un tool il testo di una lettera verrebbe generato mentre la voce
aspetta, senza schema e senza possibilità di riprovare.

- Stesso modello e stessi `num_ctx`, `think`, `keep_alive` del Brain (OllamaBackend._body):
  se cambiassero, Ollama ricaricherebbe il modello (secondi).
- `format` con lo schema JSON (output strutturati di Ollama): il JSON è sempre ben
  formato e con i campi giusti; la validazione (formato.py) controlla il resto.
- Non in streaming, con un tetto ai token. JSON compatto: con il rientro i token
  raddoppiavano (lettera: 447 contro 222, 7,5 contro 3,5 s, misura del 27/09).
- JSON invalido: un solo nuovo tentativo con gli errori, poi DocumentoNonValido.
Con `llm_backend = "openai"` si usa `response_format` di tipo json_schema su /v1.
"""

import datetime
import json
import time

from .formato import (DocumentoNonValido, FUNZIONI, is_letter, schema_for, shrunk, validate)
from ..testi import MESI

_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


def today_text(now: datetime.datetime | None = None, with_day: bool = True) -> str:
    now = now or datetime.datetime.now()
    date = f"{now.day} {MESI[now.month - 1]} {now.year}"
    return f"{_DAYS[now.weekday()]} {date}" if with_day else date


_COMMON = (
    "Scrivi il contenuto di un documento per una persona di casa. Rispondi solo con JSON "
    "compatto secondo lo schema, su una riga, senza rientri. Italiano corretto e naturale, "
    "niente markdown (niente asterischi, cancelletti o tabelle con le barre). Usa tutti i "
    "dati detti (nomi, cifre, date) esattamente come detti. Non inventare dati personali: "
    "cognomi, indirizzi, numeri di contratto, di telefono o di conto che non conosci vanno "
    "tra parentesi quadre come segnaposto, per esempio [indirizzo della palestra]. "
    "La data di oggi e il nome di chi lo chiede servono solo dove il documento li vuole "
    "(la data e la firma di una lettera): non aggiungere righe come «Data:», «A cura di» "
    "o «Richiesto da». "
    "titolo: breve e chiaro, al massimo 60 caratteri, senza la data di oggi; diventa il "
    "nome del file. ")

# «Importo (€)» come esempio faceva scrivere a gemma4 «Importocosto (€)» e «Importuale
# (€)» (27/09, anche senza schema): l'esempio ora è «Spesa (€)»
_TEXT = (
    "blocchi, in ordine: {\"tipo\":\"titolo\",\"testo\":…} per un titolo visibile; "
    "{\"tipo\":\"paragrafo\",\"testo\":…} (allinea \"destra\" per luogo e data o firma), "
    "un paragrafo per blocco; {\"tipo\":\"elenco\",\"voci\":[…],\"numerato\":false} per "
    "un elenco di cose (compiti, invitati, punti), una voce per cosa; "
    "{\"tipo\":\"tabella\",\"colonne\":[…],\"righe\":[[…],…],\"totale\":true se chiede il "
    "totale}: ogni riga ha un valore per colonna, gli importi come numeri (800, 12.5); la "
    "riga del totale la aggiunge il programma, non scriverla. Se sono euro scrivilo nel "
    "nome della colonna, per esempio «Spesa (€)». Se non è una lettera, di solito si "
    "comincia con un blocco titolo. ")

_LETTER = (
    "È una lettera: niente blocco titolo; paragrafi separati, in quest'ordine: luogo e data "
    "(a destra, «[luogo], {oggi}»), destinatario, «Oggetto: …», corpo (2–3 paragrafi brevi "
    "e formali), saluti, firma con il nome di chi la chiede (a destra). ")

_SHEET = (
    "fogli: di solito uno. nome del foglio (breve); colonne: i nomi delle colonne; righe: "
    "una riga per voce, un valore per colonna, gli importi come numeri (800, 12.5); "
    "totale: true se chiede il totale o la somma, e la riga del totale con le formule la "
    "aggiunge il programma, non scriverla. Se sono euro scrivilo nel nome della colonna, "
    "per esempio «Spesa (€)». Formule solo se chieste o davvero utili, in inglese con "
    "riferimenti A1: la riga 1 sono le colonne, i dati partono dalla riga 2. "
    f"Funzioni ammesse: {', '.join(sorted(FUNZIONI))}; nient'altro. ")

# La bozza degli agenti è testo senza markdown: senza questa frase i titoli delle sezioni
# finivano come prima riga di un paragrafo («INTRODUZIONE\nLa presente…») e i punti come
# righe con il trattino dentro un paragrafo (banco con qwen3.6 su vLLM, 02/10)
_BOZZA = (
    "\n\nUsa questa bozza, completa, divisa in blocchi: ogni titolo di sezione della bozza "
    "diventa un blocco titolo (mai la prima riga di un paragrafo), ogni serie di punti un "
    "blocco elenco con una voce per punto e senza trattini, ogni paragrafo un blocco "
    "paragrafo:\n")

_EDIT = (
    "Ti do un documento in JSON e una modifica chiesta a voce. Restituisci il documento "
    "INTERO aggiornato, nello stesso schema: cambia solo quello che la modifica chiede e "
    "lascia tutto il resto identico, parola per parola. Per «aggiungi una riga» aggiungi "
    "la riga alla tabella (il totale lo ricalcola il programma); per una data cambia la "
    "data dov'è scritta. ")


def empty_sections(doc: dict) -> list[str]:
    """I titoli seguiti subito da un altro titolo o dalla fine: sezioni senza contenuto. Il
    02/10 qwen3.6 su vLLM ha scritto la scaletta di 8 diapositive con il contenuto solo
    nelle prime due e gli altri sei titoli in fila. Il primo titolo in cima, seguito da un
    altro titolo, è un titolo del documento con un sottotitolo: non conta."""
    blocchi = doc.get("blocchi") or []
    out = []
    for i, b in enumerate(blocchi):
        if b.get("tipo") != "titolo":
            continue
        dopo = blocchi[i + 1] if i + 1 < len(blocchi) else None
        if (dopo is None or dopo.get("tipo") == "titolo") and not (i == 0 and dopo):
            out.append(str(b.get("testo") or ""))
    return out


class Writer:
    """Genera e modifica il JSON dei documenti con l'LLM della configurazione."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.max_tokens = int(getattr(cfg, "documenti_max_token", 2048) or 2048)
        if cfg.llm_backend == "ollama":
            from ..brain import OllamaBackend
            self._native = OllamaBackend(cfg)
            self._openai = None
        else:
            from openai import OpenAI
            self._native = None
            self._openai = OpenAI(base_url=cfg.llm_base_url, api_key="ollama")
        self.last_stats: dict = {}

    # ── chiamata al modello ──
    def _ask(self, messages: list[dict], schema: dict) -> str:
        t0 = time.perf_counter()
        if self._native is not None:
            body = self._native._body(messages, stream=False, num_predict=self.max_tokens)
            body["format"] = schema
            r = self._native.http.post("/api/chat", json=body)
            if r.status_code >= 400:
                raise RuntimeError(f"Ollama {r.status_code}: {r.text[:200]}")
            data = r.json()
            self.last_stats = {"s": round(time.perf_counter() - t0, 2),
                               "token": data.get("eval_count"),
                               "prompt": data.get("prompt_eval_count")}
            return (data.get("message") or {}).get("content") or ""
        extra = ({"reasoning_effort": self.cfg.llm_reasoning_effort}
                 if self.cfg.llm_reasoning_effort else {})
        if getattr(self.cfg, "llm_chat_template_kwargs", None):     # vLLM: vedi brain.py
            extra["extra_body"] = {"chat_template_kwargs":
                                   dict(self.cfg.llm_chat_template_kwargs)}
        r = self._openai.chat.completions.create(
            model=self.cfg.llm_model, messages=messages, temperature=self.cfg.llm_temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_schema",
                             "json_schema": {"name": "documento", "schema": schema}}, **extra)
        self.last_stats = {"s": round(time.perf_counter() - t0, 2),
                           "token": getattr(r.usage, "completion_tokens", None)}
        return r.choices[0].message.content or ""

    def _generate(self, formato: str, messages: list[dict], check=None) -> dict:
        """Chiede, valida, e se non va riprova una volta sola con gli errori."""
        schema = schema_for(formato)
        total = 0.0
        tokens = 0
        for attempt in (1, 2):
            raw = self._ask(messages, schema)
            total += self.last_stats.get("s") or 0
            tokens += self.last_stats.get("token") or 0
            try:
                doc = validate(formato, raw)
                if check:
                    check(doc)
                self.last_stats = {"s": round(total, 2), "token": tokens, "tentativi": attempt}
                return doc
            except DocumentoNonValido as e:
                if attempt == 2:
                    self.last_stats = {"s": round(total, 2), "token": tokens, "tentativi": 2}
                    raise
                print(f"   [DOCUMENTI] JSON non valido, riprovo: {e}", flush=True)
                messages = messages + [
                    {"role": "assistant", "content": raw[:6000]},
                    {"role": "user", "content": "Il JSON non va bene: " + "; ".join(e.errors)
                     + ". Correggilo e restituisci il documento intero."}]
        raise AssertionError("non raggiungibile")

    # ── documento nuovo ──
    def write(self, formato: str, richiesta: str, detto: str = "", persona: str | None = None,
              titolo: str = "", bozza: str = "") -> dict:
        # La bozza (agenti) non decide se è una lettera: «la domanda di prodotti freschi»
        # nella bozza di un business plan lo faceva diventare una lettera con «Spett.le»
        # e «Cordiali saluti» (banco con qwen3.6 su vLLM, 02/10)
        letter = formato != "excel" and is_letter(richiesta, detto, titolo)
        system = (_COMMON + (_SHEET if formato == "excel" else _TEXT)
                  + (_LETTER.format(oggi=today_text(with_day=False)) if letter else "")
                  + f"Oggi è {today_text()}. "
                  + (f"Chi lo chiede si chiama {persona}. " if persona else ""))
        kind = {"word": "un documento Word", "excel": "un foglio Excel",
                "pdf": "un documento PDF"}[formato]
        user = f"Prepara {kind}. Richiesta: {richiesta.strip()}"
        if detto and detto.strip() and detto.strip() not in richiesta:
            user += f"\nFrase detta a voce: «{detto.strip()}»"
        if titolo:
            user += f"\nTitolo: {titolo.strip()}"
        if bozza and bozza.strip():
            user += _BOZZA + bozza.strip()[:12000]

        def check(doc):
            # Il 27/09 una lettera su otto era solo «[Nome della Palestra]»: il modello si
            # fermava dopo il primo blocco
            if letter and sum(b["tipo"] == "paragrafo" for b in doc["blocchi"]) < 4:
                raise DocumentoNonValido(["la lettera è incompleta: servono luogo e data, "
                                          "destinatario, oggetto, corpo, saluti e firma"])
            if formato != "excel":
                vuote = empty_sections(doc)
                if len(vuote) >= 2:
                    raise DocumentoNonValido([
                        "queste sezioni hanno il titolo ma nessun contenuto: "
                        + "; ".join(f"«{t}»" for t in vuote[:6])
                        + ". Scrivi il contenuto di ognuna (paragrafi o elenchi)"])
        return self._generate(formato, [{"role": "system", "content": system},
                                        {"role": "user", "content": user}], check=check)

    # ── modifica ──
    def edit(self, formato: str, doc: dict, modifica: str, detto: str = "") -> dict:
        system = (_COMMON + (_SHEET if formato == "excel" else _TEXT) + _EDIT
                  + f"Oggi è {today_text()}. ")
        user = (f"Documento attuale: {json.dumps(doc, ensure_ascii=False)}\n"
                f"Modifica: {modifica.strip()}")
        if detto and detto.strip() and detto.strip() not in modifica:
            user += f"\nFrase detta a voce: «{detto.strip()}»"
        cancel = any(w in f"{modifica} {detto}".lower()
                     for w in ("togli", "elimina", "cancella", "rimuovi", "accorcia",
                               "riassumi", "abbrevia", "lascia solo"))

        def check(new):
            # Un modello piccolo a volte restituisce solo la parte cambiata: si perderebbe
            # il resto del documento
            if not cancel and shrunk(formato, doc, new):
                raise DocumentoNonValido(["hai restituito solo una parte del documento: "
                                          "serve il documento INTERO con la modifica"])
        return self._generate(formato, [{"role": "system", "content": system},
                                        {"role": "user", "content": user}], check=check)
