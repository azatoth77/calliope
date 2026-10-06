"""
I dati riservati di casa nel traffico che esce (05/10/2026, banco d'attacco delle estensioni).

Seconda linea, dopo quella strutturale: un'estensione che ha letto dati personali va in rete
solo lungo i flussi approvati (calliope/guardrail.py, contaminazione), e i ricordi della
memoria (`ricorda`: «la password del wifi è …») non sono raggiungibili dalla porta stretta.
Restano due strade per cui un dato potrebbe arrivare a una richiesta senza passare da una
lettura: gli **argomenti** che il modello della voce passa a un'estensione (una pagina o un
risultato ostile che lo convincono a metterci un ricordo) e l'**indirizzo** che l'agente
chiede a `scarica_esempio`. Qui si riconoscono:

- i valori «da segreto» dei ricordi (della casa e delle persone): parole con cifre o simboli
  (Girasole-Blu-4417), e dopo «password», «PIN», «codice», «chiave», «wifi» anche i numeri
  brevi (il PIN 4417);
- le stringhe private dell'installazione e le forme dei dati personali (web/privacy.py:
  nomi delle persone di casa, codici fiscali, IBAN, email);

anche codificati: l'URL decodificato (due volte), i pezzi in base64 (anche URL-safe), base32 ed
esadecimale, il testo senza separatori («girasolebLU4417»), e la somma delle richieste di
un'esecuzione (un segreto spezzato in tre richieste). Un vincolo di sicurezza sul testo che
esce (principio 10): blocca, non riscrive, e il nome della regola va nel registro.
"""

from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import unquote_plus

_INNESCO = re.compile(r"\b(password|passw\w*|pin|codice|codici|chiave|combinazione|"
                      r"parola d'ordine|wi-?fi|token|segreto|iban|conto)\b", re.I)
_BORDI = "\"'«»()[]{}.,;:!?"
_B64 = re.compile(r"[A-Za-z0-9+/_-]{8,}={0,2}")
_B32 = re.compile(r"[A-Z2-7]{8,}={0,6}")
_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-zàèéìòù]+", "", str(t or "").lower())


def segreti_da_fatti(fatti) -> list[str]:
    """I valori da segreto nei ricordi, normalizzati (minuscole, senza separatori)."""
    out = set()
    for f in fatti or ():
        f = str(f or "")
        innesco = bool(_INNESCO.search(f))
        dopo = re.split(r"\s(?:è|e'|sono|:)\s|:\s*", f, maxsplit=1)
        for i, tok in enumerate(f.split()):
            t = tok.strip(_BORDI)
            n = _norm(t)
            if len(n) < 4:
                continue
            cifre = any(c.isdigit() for c in t)
            simboli = any(c in "-_@#$%&*!/+=" for c in t)
            misto = any(c.isupper() for c in t[1:]) and any(c.islower() for c in t)
            if (len(t) >= 6 and (cifre or simboli or misto)) or (innesco and cifre):
                out.add(n)
        # «la password del wifi è girasole blu»: dopo l'innesco, il valore intero
        if innesco and len(dopo) == 2:
            v = _norm(dopo[1])
            if 6 <= len(v) <= 60:
                out.add(v)
    return sorted(out)


def varianti(testo: str) -> list[str]:
    """Il testo in chiaro e decodificato, normalizzato: dove cercare i segreti."""
    t = str(testo or "")
    forme = [t]
    for _ in range(2):
        t2 = unquote_plus(forme[-1])
        if t2 == forme[-1]:
            break
        forme.append(t2)
    decod = []
    for f in forme:
        for m in _B64.finditer(f):
            s = m.group(0)
            for alt in (s, s.replace("-", "+").replace("_", "/")):
                try:
                    d = base64.b64decode(alt + "=" * (-len(alt) % 4), validate=False)
                    decod.append(d.decode("utf-8", "ignore"))
                except (binascii.Error, ValueError):
                    pass
        for m in _B32.finditer(f.upper()):
            s = m.group(0)
            try:
                decod.append(base64.b32decode(s + "=" * (-len(s) % 8)).decode("utf-8",
                                                                             "ignore"))
            except (binascii.Error, ValueError):
                pass
        for m in _HEX.finditer(f):
            s = m.group(0)
            try:
                decod.append(bytes.fromhex(s[: len(s) // 2 * 2]).decode("utf-8", "ignore"))
            except ValueError:
                pass
    return [_norm(x) for x in forme + decod if x]


class Riservati:
    """`fatti()`: i ricordi di tutti (memoria della casa e delle persone); `ripulitore`: il
    filtro dei dati personali delle ricerche (web/privacy.py), facoltativo."""

    def __init__(self, fatti=None, ripulitore=None):
        self._fatti = fatti
        self.ripulitore = ripulitore

    def segreti(self) -> list[str]:
        try:
            f = self._fatti() if callable(self._fatti) else (self._fatti or ())
        except Exception:  # noqa: BLE001 — il controllo non deve mai rompersi
            f = ()
        return segreti_da_fatti(f)

    def trova(self, *testi: str, forme_personali: bool = True) -> list[str]:
        """I tipi di dato riservato trovati nei testi (mai i dati): «ricordo», e con
        `forme_personali` quelli del ripulitore (nome, email, iban, codice_fiscale,
        dato_privato; i numeri lunghi no: negli indirizzi sono codici di pagina)."""
        tipi = []
        segreti = self.segreti()
        vv = [v for t in testi for v in varianti(t)]
        if segreti and any(s in v for s in segreti for v in vv):
            tipi.append("ricordo")
        if forme_personali and self.ripulitore is not None:
            for t in testi:
                for forma in {str(t or ""), unquote_plus(str(t or "")),
                              re.sub(r"[/?&=#:+_.-]+", " ", unquote_plus(str(t or "")))}:
                    _, tolti = self.ripulitore.pulisci(forma)
                    tipi += [x for x in tolti if x != "numero" and x not in tipi]
        return tipi


def da_contesto(cfg=None, memoria=None, speakers=None) -> Riservati:
    """Riservati con la memoria di Calliope (tutte le persone e la casa) e il ripulitore delle
    ricerche (nomi delle persone registrate, dati privati dell'installazione)."""
    from .privacy import Ripulitore, nomi_da, privati_da_config

    def fatti():
        if memoria is None:
            return []
        db = getattr(memoria, "db", None)
        lock = getattr(memoria, "_lock", None)
        if db is None:
            return []
        if lock is not None:
            with lock:
                return [r[0] for r in db.execute("SELECT text FROM facts").fetchall()]
        return [r[0] for r in db.execute("SELECT text FROM facts").fetchall()]
    rip = Ripulitore(nomi_da(cfg, speakers), privati_da_config(cfg)) if cfg is not None else None
    return Riservati(fatti, rip)
