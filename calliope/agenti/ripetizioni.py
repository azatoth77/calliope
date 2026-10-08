"""
Il giro a vuoto nel ragionamento dell'agente (08/10/2026 sera, giro 5 della modalità
sviluppo; docs/aree/agenti-estensioni.md).

Caso vero della DGX: nella correzione di un'estensione qwen3.6 (vLLM) ha ripetuto per
centinaia di righe gli stessi paragrafi («La soluzione più semplice è: 1. Aggiungere il
parametro paese… Ma il compito non specifica…», la stessa riga 58 volte in una passata); il
registro del lavoro è arrivato a 160 kB in 12 passate, e sullo schermo sembrava un difetto
del pannello. La guardia dei token senza strumenti (05/10) scatta solo tra una passata e
l'altra, quando la passata è già finita.

`Ripetizioni` legge il flusso (ragionamento e testo, mai gli argomenti delle chiamate) e
conta le frasi di prosa: una frase lunga (almeno PAROLE_MIN parole) ripetuta `soglia` volte
nella stessa passata è il segnale. Non contano: i blocchi di codice tra ```, le righe delle
tabelle («| … |»), le righe che sembrano codice (assegnazioni, chiamate, parentesi graffe,
parole chiave di Python in testa), le frasi corte («Leggo il file.»). Il ciclo
(`Agente.passata`) allora chiude lo stream e restituisce la passata come «giro a vuoto»: chi
la chiama aggiunge la spinta («stai ripetendo lo stesso ragionamento: decidi e chiama uno
strumento»).
"""

from __future__ import annotations

import re

PAROLE_MIN = 6
CARATTERI_MIN = 30

# Una riga che sembra codice: un'assegnazione, una chiamata «nome(», graffe, punto e virgola
# in fondo, una parola chiave in testa, un commento di codice
_CODICE = re.compile(
    r"(?:[\w\])]\s*(?:==|!=|<=|>=|\+=|-=|=)\s*\S|\w\(|[{}]|;\s*$"
    r"|^\s*(?:def|class|import|from|return|if|elif|else|for|while|try|except|with|assert|"
    r"raise|print|async|await|const|let|var|function|public|private|using|namespace)\b"
    r"|^\s*(?:#|//|>>>))")
_SPAZI = re.compile(r"\s+")
_INLINE = re.compile(r"`[^`]*`")
_FRASI = re.compile(r"(?<=[.!?:])\s+")


class Ripetizioni:
    """Il rilevatore di una passata. `aggiungi(testo)` a ogni pezzo del flusso; `scattato`
    diventa la frase ripetuta (troncata) appena una frase arriva a `soglia` volte."""

    def __init__(self, soglia: int = 8):
        self.soglia = max(2, int(soglia or 8))
        self.conti: dict[str, int] = {}
        self.resto = ""
        self.in_codice = False
        self.caratteri = 0
        self.scattato = ""

    def aggiungi(self, testo: str) -> str:
        if not testo:
            return self.scattato
        self.caratteri += len(testo)
        if self.scattato:
            return self.scattato
        self.resto += testo
        *righe, self.resto = self.resto.split("\n")
        for r in righe:
            self._riga(r)
            if self.scattato:
                break
        # Una riga lunghissima senza a capo (le frasi ripetute di seguito): si guardano le
        # frasi già chiuse e si tiene l'ultima a metà
        if not self.scattato and len(self.resto) > 2000:
            pezzi = _FRASI.split(self.resto)
            self.resto = pezzi[-1]
            for p in pezzi[:-1]:
                self._frase(p)
                if self.scattato:
                    break
        return self.scattato

    def _riga(self, riga: str):
        s = riga.strip()
        if s.startswith("```") or s.startswith("~~~"):
            self.in_codice = not self.in_codice
            return
        if self.in_codice or not s or s.startswith("|") or riga.startswith(("    ", "\t")):
            return
        for f in _FRASI.split(s):
            self._frase(f)
            if self.scattato:
                return

    def _frase(self, frase: str):
        if _CODICE.search(frase):
            return
        t = _SPAZI.sub(" ", _INLINE.sub("`…`", frase)).strip().lower()
        t = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", t)       # il segno dell'elenco non conta
        if len(t) < CARATTERI_MIN or len(re.findall(r"[^\W\d_]{2,}", t)) < PAROLE_MIN:
            return
        n = self.conti.get(t, 0) + 1
        self.conti[t] = n
        if n >= self.soglia:
            self.scattato = frase.strip()[:160]


def spinta(frase: str) -> str:
    """Il messaggio per l'agente dopo una passata fermata per giro a vuoto."""
    return ("Ti ho fermato: stai ripetendo lo stesso ragionamento"
            + (f" («{frase[:120]}»)" if frase else "") + ". Non ripensarci: decidi adesso e "
            "chiama uno strumento (leggi o scrivi un file, esegui i test, oppure consegna). Se "
            "sei incerto tra due strade, scegli la più semplice e provala con un test.")
