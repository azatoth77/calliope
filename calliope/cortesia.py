"""
Risposte di cortesia senza il modello (05/10, segnalazione di Dario: «quando dico "ok,
grazie" o semplicemente "Perfetto", Calliope non risponde mai»).

Una frase intera di sola chiusura (wakeword.closing_kind) ha tre forme: l'ordine di
silenzio («basta», «stop», «lascia stare») resta muto come prima; il ringraziamento
(«grazie», «ok, grazie», «gentilissima») e la conferma («perfetto», «va bene così», «ok»)
ricevono una frase breve, scelta qui a rotazione e sintetizzata all'avvio
(Speaker.prepare → say_cached: latenza ~0, nessuna passata del modello).

Per la conferma una frase, non il suono di fine ascolto: il suono c'è solo con
`suoni_ascolto` (modalità startrek) e con un satellite lo suona lui, quindi con i valori
predefiniti «Perfetto» resterebbe ancora senza risposta, che è proprio il difetto.

Le frasi seguono il tono di chi parla (profilo) o quello della casa (config.TONI), con il
«lei» nel tono formale; Calliope parla di sé al femminile. Niente «Fatto.» o «Eseguito.»:
sarebbero dichiarazioni d'azione (ACTION_CLAIM) senza un'azione.
"""
from __future__ import annotations

from .config import nome_tono

# tono → forma → frasi (la prima è la più neutra)
RISPOSTE: dict[str, dict[str, tuple[str, ...]]] = {
    "normale": {"grazie": ("Prego!", "Figurati.", "Di niente.", "A disposizione."),
                "conferma": ("Bene!", "Ottimo.", "D'accordo.")},
    "formale": {"grazie": ("Prego, è un piacere.", "Si figuri.", "Sono a sua disposizione."),
                "conferma": ("Molto bene.", "D'accordo.", "Bene.")},
    "amichevole": {"grazie": ("Figurati, è un piacere!", "Ma di che!", "Quando vuoi!"),
                   "conferma": ("Benissimo!", "Ottimo!", "Che bello!")},
    "ironico": {"grazie": ("Prego, lo metto in conto.", "Dovere, ogni tanto.",
                           "Figurati, è il mio lavoro."),
                "conferma": ("Lo prendo come un complimento.", "Bene, ne sono felice.",
                             "Ottimo, segno un punto per me.")},
    "essenziale": {"grazie": ("Prego.",), "conferma": ("Bene.",)},
    "computer_di_bordo": {"grazie": ("Prego.", "A disposizione."),
                          "conferma": ("Ricevuto.", "Confermato.")},
}


class Cortesia:
    """Sceglie la risposta a rotazione, per tono e forma: mai la stessa due volte di fila
    (se ce n'è più d'una)."""

    def __init__(self):
        self._giro: dict[tuple[str, str], int] = {}

    @staticmethod
    def tono(tono_persona: str | None, tono_casa: str | None) -> str:
        t = nome_tono(tono_persona) or nome_tono(tono_casa) or "normale"
        return t if t in RISPOSTE else "normale"

    def risposta(self, forma: str, tono_persona: str | None = None,
                 tono_casa: str | None = None) -> str | None:
        """La frase per la forma "grazie" o "conferma"; None per le altre ("silenzio")."""
        frasi = RISPOSTE[self.tono(tono_persona, tono_casa)].get(forma)
        if not frasi:
            return None
        chiave = (self.tono(tono_persona, tono_casa), forma)
        i = self._giro.get(chiave, 0)
        self._giro[chiave] = i + 1
        return frasi[i % len(frasi)]

    @staticmethod
    def frasi(toni) -> list[str]:
        """Tutte le frasi dei toni dati, da preparare all'avvio (Speaker.prepare)."""
        out: list[str] = []
        for t in toni:
            t = nome_tono(t) or "normale"
            for frasi in RISPOSTE.get(t, RISPOSTE["normale"]).values():
                out.extend(frasi)
        return list(dict.fromkeys(out))
