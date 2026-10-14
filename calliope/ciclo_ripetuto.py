"""
La risposta che gira in tondo (14/10/2026, rete del modello `ciclo_ripetuto`).

Caso vero in auto, la sera del 14/10 (gemma4 26b-a4b su Ollama, conversazione di stanza accesa):
a una spiegazione lunga di chi parlava il modello ha risposto «Grazie per l'aggiornamento, ora ho
capito! Allora allora, allora... allora... allora...» per centinaia di ripetizioni, e la voce le
ha lette finché la persona non l'ha interrotta col nome. Un ciclo degenerato della generazione:
non è una scelta del modello, è un guasto della sua forma.

`CicloRipetuto` sta nello streaming di Brain._turn, subito dopo il filtro del ragionamento, e
guarda le parole mentre arrivano. Riconosce una **sequenza periodica in coda**: la stessa
parola, lo stesso gruppo di parole o la stessa frase ripetuti uno dopo l'altro (minuscole,
senza punteggiatura: «allora... allora,» sono la stessa parola). Quando la coda comincia a
ripetersi, quel pezzo non va avanti (la voce non lo sente) finché non si sa se è un ciclo:
- se la ripetizione si interrompe sotto la soglia, si rilascia tutto com'era («no no no»,
  «dormi tu? dormi tu?»): costa solo l'attesa delle parole ripetute, pochi token;
- se supera la soglia, è un ciclo: la rete si ferma (`fermata`), Brain chiude lo stream verso il
  motore (Ollama smette di generare quando il client chiude), la parte ripetuta non si dice e non
  entra nella storia. Resta la parte sana: se finisce con una frase compiuta basta quella,
  altrimenti Brain aggiunge la frase pronta `scusa.incartata` (calliope/frasi.py).

Le soglie (ripetizioni consecutive dell'unità, contando la prima):
- una parola sola: 10 (le cifre e i numeri a parole 16: un IBAN dettato ha «zero» sette volte);
- due o tre parole: 6 («e poi e poi e poi…»);
- quattro parole o più: 4 (una frase intera detta quattro volte di fila).
I contrari (prove/prova_ciclo_ripetuto.py): «no no no», «sì sì», una parola ripetuta tre volte
per enfasi, numeri dettati, un ritornello chiesto («Fra Martino», «tanti auguri a te» due
volte), «ripeti tre volte…», elenchi con la stessa forma («un chilo di mele, un chilo di
pere…»), «la la la» di una canzone.

È una correzione della forma dell'uscita del modello (principio 10): non decide nessun
significato, scrive il suo nome nel registro dei turni (regola `ciclo_ripetuto`) e si spegne
col profilo (`llm_reti_spente: [ciclo_ripetuto]`).

Profilo ridotto da 8 GB (decisione 0028): uguale, niente modello e pochi µs a token.
Solo libreria standard.
"""
from __future__ import annotations

import re

SOGLIA_PAROLA = 10          # una parola sola ripetuta di fila
SOGLIA_NUMERO = 16          # una cifra o un numero a parole (IBAN, telefoni dettati)
SOGLIA_GRUPPO = 6           # due o tre parole
SOGLIA_FRASE = 4            # quattro parole o più
PERIODO_MAX = 40            # la frase ripetuta più lunga che si cerca (parole)
CODA_MAX = 600              # parole guardate in coda (il costo resta fisso)

_PAROLA = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_FINE = re.compile(r"[.!?…:;]\s*[\"»)\]]?\s*$")
_FRASE_COMPIUTA = re.compile(r"[.!?…][\"»)\]]?\s*$")

NUMERI = frozenset(
    "zero uno una due tre quattro cinque sei sette otto nove dieci undici dodici tredici "
    "quattordici quindici sedici diciassette diciotto diciannove venti trenta quaranta "
    "cinquanta sessanta settanta ottanta novanta cento mille".split())


def _numerica(unita: list[str]) -> bool:
    return all(w.isdigit() or w in NUMERI for w in unita)


def soglia(unita: list[str]) -> int:
    """Quante ripetizioni consecutive di `unita` (contando la prima) fanno un ciclo."""
    p = len(unita)
    if p == 1:
        return SOGLIA_NUMERO if _numerica(unita) else SOGLIA_PAROLA
    if p <= 3:
        return SOGLIA_NUMERO if _numerica(unita) else SOGLIA_GRUPPO
    return SOGLIA_FRASE


def coda_periodica(parole: list[str], periodo_max: int = PERIODO_MAX):
    """Le sequenze periodiche in coda: per ogni periodo p, (p, ripetizioni, inizio) con
    ripetizioni ≥ 2 (anche non intere: «a b a b a» è 2,5 volte «a b»). `inizio` è l'indice della
    prima parola della prima copia."""
    n = len(parole)
    out = []
    for p in range(1, min(periodo_max, n // 2) + 1):
        lung = 0
        i = n - 1
        while i - p >= 0 and parole[i] == parole[i - p]:
            lung += 1
            i -= 1
        if lung >= p:
            out.append((p, (lung + p) / p, n - lung - p))
    return out


class CicloRipetuto:
    """Il filtro dello streaming (vedi la docstring del modulo). `feed` restituisce il testo da
    passare avanti; dopo `fermata` non passa più niente. `sana` è il testo rilasciato in tutto,
    `ciclo` la descrizione del ciclo trovato (per la console e le prove: mai nel registro)."""

    def __init__(self, active: bool = True):
        self.active = active
        self.testo = ""             # tutto il testo arrivato
        self.dato = 0               # caratteri già rilasciati
        self.fermata = False
        self.ciclo: dict | None = None

    @property
    def sana(self) -> str:
        return self.testo[:self.dato]

    def _rilascia(self, fino: int) -> str:
        if fino <= self.dato:
            return ""
        out, self.dato = self.testo[self.dato:fino], fino
        return out

    def feed(self, text: str) -> str:
        if not self.active:
            return text
        if self.fermata or not text:
            return ""
        self.testo += text
        # Le parole complete: l'ultima conta solo se dopo c'è già qualcosa (spazio, segno)
        base = max(0, self.dato - 2000)
        spans = [m.span() for m in _PAROLA.finditer(self.testo, base)]
        if spans and spans[-1][1] == len(self.testo):
            spans.pop()
        spans = spans[-CODA_MAX:]
        parole = [self.testo[a:b].lower().replace("’", "'") for a, b in spans]
        trattieni = len(self.testo)
        if spans:
            # Una parola di ritardo: la prima copia di una parola ripetuta non è ancora detta
            # quando arriva la seconda. Una frase che finisce col suo segno va avanti subito
            trattieni = spans[-1][0]
        if not parole:
            return self._rilascia(len(self.testo) if _FINE.search(self.testo) else 0)
        sospetta = False
        for p, volte, inizio in coda_periodica(parole):
            unita = parole[len(parole) - p:]
            if volte >= soglia(unita):
                self.fermata = True
                self.ciclo = {"periodo": p, "volte": int(volte), "unita": " ".join(unita)}
                # Si dice ciò che precede la prima copia del ciclo, non il ciclo
                return self._rilascia(spans[inizio][0])
            sospetta = True
            trattieni = min(trattieni, spans[inizio][0])
        if not sospetta and _FINE.search(self.testo):
            trattieni = len(self.testo)
        return self._rilascia(trattieni)

    def flush(self) -> str:
        if not self.active:
            return ""
        if self.fermata:
            return ""
        return self._rilascia(len(self.testo))

    def compiuta(self) -> bool:
        """La parte sana finisce con una frase compiuta di almeno due parole: basta quella."""
        s = self.sana.strip()
        return len(_PAROLA.findall(s)) >= 2 and bool(_FRASE_COMPIUTA.search(s))
