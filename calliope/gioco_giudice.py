"""
Il giudice di fase dei giochi (14/10/2026, passo 6 del progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md § 3.5; area docs/aree/giochi.md).

Quando una frase rivolta a Calliope non è una forma chiusa del gioco aperto sullo schermo («apri
la terza», «proviamo con la prima», «uno, no aspetta, la cinque»), il **significato** lo decide
il modello (principio 10), ma non quello della voce con tutta la conversazione: una chiamata
breve e separata allo stesso modello già in memoria (o al rilevatore e4b sulla DGX, come il
giudizio «rivolta a Calliope», calliope/rivolta.py), con l'**uscita vincolata** da uno schema
JSON: un `enum` con i comandi a voce attivi adesso (dall'istantanea validata del motore) più
«nessuno». Non può inventare un comando né un valore fuori dominio. Vede solo il titolo del
gioco, i comandi della fase e la frase: né la conversazione né dati di casa.

Misura del progetto (portatile, gemma4 e4b, 22 frasi, prompt B): 21/22 giuste, mediana 357 ms,
p90 386 ms, nessuna VRAM in più, la cache del prompt della voce intatta (stesso `num_ctx`). Il
prompt è quello B del prototipo, scritto in generale da Calliope dai comandi della macchina
(comandi con il loro significato, «nessuno» in testa, esempi, «vale l'ultima scelta»), mai
dall'agente; con il modello in `prove/prova_gioco_giudice_ollama.py`.

Interruttori (calliope.yaml, sezione estensioni): `giochi_giudice` (acceso; spento si torna al
tool `gioco_comando` del modello della voce), `giochi_giudice_senza_nome` (spento: decisione 2
di chi amministra del 12/10, nella finestra del gioco senza il nome ogni frase della stanza
diventerebbe una chiamata al modello e una chiacchiera una mossa). Un giudizio guasto o scaduto
vale «nessuno»: la frase va al modello della voce come prima.
"""
from __future__ import annotations

import dataclasses
import json
import time

NESSUNO = "nessuno"
REGOLA = "gioco_giudice"

# Il significato dei comandi standard di Calliope (macchina.COMANDI_STANDARD)
SIGNIFICATI = {
    "inizia": "comincia la partita",
    "avanti": "va avanti dopo l'esito della mossa",
    "ancora": "una partita nuova da capo",
    "fine_partita": "finisce la partita",
}


@dataclasses.dataclass
class Scelta:
    comando: str | None            # il comando a voce piatto («porta_3»), None per «nessuno»
    etichetta: str = ""            # come si dice («porta 3»)
    ms: float = 0.0
    guasto: str | None = None

    def per_registro(self) -> dict:
        d = {"comando": self.comando, "ms": round(self.ms)}
        if self.guasto:
            d["guasto"] = self.guasto
        return d


def dove(cfg) -> tuple[str, str] | None:
    """(url, modello) del giudice: `giochi_giudice_modello`, altrimenti quello del giudizio
    «rivolta» (il rilevatore e4b già residente sulla DGX, o il modello della voce su Ollama)."""
    m = str(getattr(cfg, "giochi_giudice_modello", "") or "")
    if m:
        url = str(getattr(cfg, "llm_native_url", "") or "http://127.0.0.1:11434")
        return url.rstrip("/"), m
    from .rivolta import dove as dove_rivolta
    return dove_rivolta(cfg)


def _etichette(info: dict) -> dict[str, str]:
    """{etichetta detta: comando piatto}: la prima forma di ogni comando attivo, espansa
    (le forme sono uniche dopo la normalizzazione, gioco_voce.valida_elenco)."""
    out = {}
    for c, forme in (info.get("comandi") or {}).items():
        e = str((forme or [c])[0]).strip() or c
        if e.lower() == NESSUNO or e in out:
            e = c.replace("_", " ")
        out[e] = c
    return out


def prompt(info: dict) -> tuple[str, list[str]]:
    """(il prompt di sistema, l'enum delle scelte con «nessuno» in testa), scritti da Calliope
    dai comandi attivi della fase (Giochi.ascolto: comandi espansi, macchina, istantanea)."""
    from .estensioni import macchina as mc
    etichette = _etichette(info)
    m = info.get("macchina") or {}
    titolo = str(info.get("titolo") or "")[:60]
    # I comandi raggruppati come nel manifesto: «porta 1, porta 3, porta 4: …»
    gruppi: dict[tuple, list] = {}
    ordine: list[tuple] = []
    for e, c in etichette.items():
        d = mc.da_piatto(m, c) or (c, None, None)
        k = (d[0], d[2])
        if k not in gruppi:
            gruppi[k] = []
            ordine.append(k)
        gruppi[k].append((e, d[1]))
    righe = []
    esempi = []
    for k in ordine:
        nome, fase = k
        voci = gruppi[k]
        lista = ", ".join(e for e, _ in voci)
        if nome in SIGNIFICATI:
            righe.append(f"- {lista}: {SIGNIFICATI[nome]}.")
            continue
        if nome == "giocatori":
            righe.append(f"- {lista}: quante persone giocano.")
            continue
        c = (((m.get("fasi") or {}).get(fase) or {}).get("comandi") or {}).get(nome) or {}
        forme = c.get("forme") or [nome]
        detto = c.get("etichetta") or forme[0]
        riga = f"- {lista}: il comando «{detto}» del gioco (si dice anche " \
               + ", ".join(f"«{f}»" for f in forme[:4]) + ")"
        dom = c.get("n") or {}
        if "da" in dom:
            riga += (f"; il numero si può dire anche come ordinale (la prima = 1, la terza = 3) "
                     f"e «l'ultima» è il {dom['a']}")
            valori = [v for _, v in voci]
            dichiarati = list(range(dom["da"], dom["a"] + 1))
            fuori = [str(v) for v in dichiarati if v not in valori]
            if fuori:
                riga += f"; adesso non valgono {', '.join(fuori[:12])}"
        righe.append(riga + ".")
        if len(esempi) < 2:
            e0, v0 = voci[-1]
            esempi.append(f"«{forme[0].replace('{n}', str(v0)) if v0 is not None else forme[0]} "
                          f"per favore» → {e0}")
    righe.append(f"- {NESSUNO}: la frase non chiede uno di questi comandi (domande, chiacchiere, "
                 "altre richieste, un valore che adesso non c'è, più comandi insieme).")
    esempi += [f"«che tempo fa?» → {NESSUNO}", f"«chiudi la finestra» → {NESSUNO}",
               f"«a chi tocca?» → {NESSUNO}"]
    sistema = (f"Traduci la frase di un giocatore in un comando del gioco «{titolo}» sullo "
               "schermo.\nComandi possibili adesso:\n" + "\n".join(righe)
               + "\nEsempi: " + "; ".join(esempi) + ".\n"
               "Se la persona cambia idea nella frase, vale l'ultima scelta. "
               'Rispondi solo con JSON {"scelta": "<una delle scelte>"}.')
    return sistema, [NESSUNO] + list(etichette)


class Giudice:
    """Il giudice su Ollama (API nativa, output strutturato), con un client httpx come il
    giudizio «rivolta»; `chiama(messaggi, schema, timeout) -> testo` sostituibile nelle prove."""

    def __init__(self, cfg, chiama=None):
        self.cfg = cfg
        self._chiama = chiama
        self._sessione = None

    def _http(self):
        if self._sessione is None:
            import httpx
            self._sessione = httpx.Client()
        return self._sessione

    def scegli(self, frase: str, info: dict, timeout: float | None = None) -> Scelta:
        t0 = time.perf_counter()
        etichette = _etichette(info)
        if not etichette or not str(frase or "").strip():
            return Scelta(None)
        sistema, scelte = prompt(info)
        schema = {"type": "object", "properties": {"scelta": {"type": "string", "enum": scelte}},
                  "required": ["scelta"]}
        msgs = [{"role": "system", "content": sistema},
                {"role": "user", "content": str(frase).strip()[:300]}]
        timeout = float(timeout or getattr(self.cfg, "giochi_giudice_timeout_s", 2.0) or 2.0)
        try:
            testo = (self._chiama(msgs, schema, timeout) if self._chiama is not None
                     else self._ollama(msgs, schema, timeout))
            s = json.loads(testo).get("scelta")
            if not isinstance(s, str):
                raise ValueError("risposta senza scelta")
        except Exception as e:  # noqa: BLE001 — guasto: vale «nessuno», la frase va al modello
            return Scelta(None, ms=(time.perf_counter() - t0) * 1000, guasto=type(e).__name__)
        ms = (time.perf_counter() - t0) * 1000
        if s == NESSUNO or s not in etichette:
            # Fuori elenco non può succedere con l'uscita vincolata; se succede, «nessuno»
            return Scelta(None, ms=ms, guasto=None if s == NESSUNO else "fuori elenco")
        return Scelta(etichette[s], s, ms)

    def _ollama(self, msgs: list[dict], schema: dict, timeout: float) -> str:
        d = dove(self.cfg)
        if d is None:
            raise RuntimeError("nessun modello")
        url, modello = d
        from .rivolta import _opzioni
        num_ctx, keep = _opzioni(self.cfg, url, modello)
        body = {"model": modello, "stream": False, "think": False, "keep_alive": keep,
                "messages": msgs, "format": schema,
                "options": {"temperature": 0, "num_predict": 24, "num_ctx": num_ctx}}
        r = self._http().post(url + "/api/chat", json=body, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return (r.json().get("message") or {}).get("content") or ""


def frase_detta(etichetta: str) -> str:
    """Decisione 5 di chi amministra (12/10): dopo una mossa capita dal giudice Calliope dice
    l'etichetta breve («Porta 3.»), perché è un'interpretazione delle parole."""
    e = str(etichetta or "").strip().rstrip(".!?")
    return (e[:1].upper() + e[1:] + ".") if e else "Fatto."


__all__ = ["Giudice", "Scelta", "prompt", "frase_detta", "dove", "NESSUNO", "REGOLA"]
