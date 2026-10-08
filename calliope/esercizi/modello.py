"""
Il formato di un esercizio e della correzione (08/10/2026), comune a tutte le materie.

Un esercizio nasce da un generatore (matematica.py, italiano.py) con un seme: stesso seme,
stesso esercizio. La risposta attesa sta nell'oggetto e resta sul server: alla scheda va solo
`pubblico()`, mai `risposta` né `spiegazione` prima del tempo.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from fractions import Fraction

# Scuole e anni (classi): le classi vanno da 1 a 5, da 1 a 3 alle medie
SCUOLE = {"elementari": 5, "medie": 3, "superiori": 5}
ORDINE_SCUOLE = ("elementari", "medie", "superiori")


@dataclass(frozen=True, order=True)
class Classe:
    scuola: str            # elementari | medie | superiori
    anno: int              # 1–5 (1–3 alle medie)

    @property
    def indice(self) -> int:
        """Un numero solo, da 1 (prima elementare) a 13 (quinta superiore)."""
        base = {"elementari": 0, "medie": 5, "superiori": 8}[self.scuola]
        return base + self.anno

    def detta(self) -> str:
        ordinali = {1: "prima", 2: "seconda", 3: "terza", 4: "quarta", 5: "quinta"}
        nome = {"elementari": "elementare", "medie": "media", "superiori": "superiore"}
        return f"{ordinali[self.anno]} {nome[self.scuola]}"

    def __str__(self) -> str:
        return f"{self.scuola}-{self.anno}"

    @staticmethod
    def da_indice(i: int) -> "Classe":
        i = max(1, min(13, int(i)))
        if i <= 5:
            return Classe("elementari", i)
        if i <= 8:
            return Classe("medie", i - 5)
        return Classe("superiori", i - 8)

    @staticmethod
    def da_testo(s: str) -> "Classe | None":
        try:
            sc, a = str(s).split("-")
            return Classe(sc, int(a)) if sc in SCUOLE and 1 <= int(a) <= SCUOLE[sc] else None
        except ValueError:
            return None


@dataclass
class Esercizio:
    materia: str                   # matematica | italiano
    argomento: str                 # chiave di ARGOMENTI della materia
    livello: int                   # 1 facile, 2 medio, 3 difficile
    seme: int
    testo: str                     # per la scheda (con i simboli: «3/4 + 1/4 = ?»)
    voce: str                      # per la voce, senza simboli («Quanto fa 3 quarti più un quarto?»)
    tipo: str                      # valore | frazione_ridotta | scelta | parole
    risposta: object               # Fraction | str (scelta) | list[str] (parole)
    risposta_detta: str            # la risposta come va detta («un intero», «aggettivo»)
    suggerimenti: list = field(default_factory=list)   # graduati, dal più vago
    spiegazione: str = ""          # la soluzione spiegata (dopo i tentativi)
    scelte: list = field(default_factory=list)         # per «scelta»: le opzioni mostrate
    espressione: str = ""          # matematica: il conto che il codice ricalcola da sé
    dati: dict = field(default_factory=dict)            # il resto (frase, parola, ruoli…)
    verifica: dict = field(default_factory=dict)        # come è stato controllato

    @property
    def firma(self) -> str:
        """Impronta del contenuto (testo e risposta): lo stesso esercizio ha la stessa firma
        anche se il generatore cambia seme; un esercizio cambiato ne ha un'altra."""
        r = self.risposta
        r = f"{r.numerator}/{r.denominator}" if isinstance(r, Fraction) else r
        s = json.dumps([self.materia, self.argomento, self.testo, r], ensure_ascii=False)
        return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]

    def pubblico(self) -> dict:
        """Ciò che può andare alla scheda: niente risposta, niente spiegazione."""
        return {"id": self.firma, "materia": self.materia, "argomento": self.argomento,
                "livello": self.livello, "testo": self.testo, "tipo": self.tipo,
                "scelte": list(self.scelte)}

    def a_dict(self) -> dict:
        d = asdict(self)
        if isinstance(self.risposta, Fraction):
            d["risposta"] = {"frazione": [self.risposta.numerator, self.risposta.denominator]}
        return d

    @staticmethod
    def da_dict(d: dict) -> "Esercizio":
        d = dict(d)
        r = d.get("risposta")
        if isinstance(r, dict) and "frazione" in r:
            d["risposta"] = Fraction(*r["frazione"])
        return Esercizio(**d)


@dataclass
class Esito:
    giusta: bool | None            # None = non si capisce la risposta (nessun tentativo contato)
    letta: str = ""                # la risposta come l'ha capita il codice («3/4»)
    nota: str = ""                 # per il ragazzo: «quasi: si può semplificare ancora»
    conta: bool = True             # vale come tentativo sbagliato
