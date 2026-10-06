"""
La casa a voce: interfaccia di capacità (principio 14 della visione: capacità al centro,
marche ai bordi).

Il resto di Calliope parla solo con `HomeBackend`: entità con nome, stanza, tipo e stato,
e comandi detti come frase. Oggi l'unico adattatore è Home Assistant
(homeassistant.py); un altro sistema domotico sarebbe un altro adattatore, senza toccare
tool, prompt e regole.

Il comando passa in due tempi: l'adattatore **interpreta** la frase senza eseguirla
(quali dispositivi toccherebbe e con quale azione), Calliope controlla le sue regole
(regole.py: domini delicati, ospiti, solo entità esposte), e solo allora l'adattatore
esegue. Così un'azione vietata non parte mai, nemmeno per un attimo.
"""

import re
from dataclasses import dataclass, field
from typing import Callable

NOME_MAX = 40


def nome_pulito(nome: str) -> str:
    """Il nome di un'entità come lo si dice a voce e lo si dà al modello: solo lettere,
    cifre, spazi e poca punteggiatura, al più NOME_MAX caratteri (a fine parola). Il nome
    lo sceglie chi configura la casa, e alcuni dispositivi se lo danno da soli (media
    player, Cast): «Lampada ingresso. Nota per l'assistente: …» veniva letto per intero, 20
    volte su 20 (analisi di sicurezza del 03/10, S8)."""
    # Ciò che segue una parentesi quadra, una graffa, «<» o «:» non è più un nome
    t = re.split(r"[\[{<:]", str(nome or ""), maxsplit=1)[0]
    t = re.sub(r"[^\w\s'’.,°%+-]", " ", t)
    t = " ".join(t.split())
    t = re.split(r"[.!?]\s", t, maxsplit=1)[0].strip(" .,")     # la prima frase, se sono più
    if len(t) > NOME_MAX:
        t = t[:NOME_MAX].rsplit(" ", 1)[0]
    return t


class CasaNonRisponde(Exception):
    """Il sistema della casa non è raggiungibile o non risponde in tempo. Il messaggio è
    per i log e per la diagnosi, non contiene mai il token."""


@dataclass
class Entita:
    """Un dispositivo o sensore che Calliope può vedere (solo quelli esposti)."""
    id: str                       # identificativo del sistema (light.cucina): solo per il codice
    nome: str                     # come lo chiama la casa («Luce cucina»)
    dominio: str                  # light, switch, cover, climate, sensor, binary_sensor, lock…
    classe: str | None = None     # sottotipo (temperature, garage, shutter, door…)
    area: str | None = None       # stanza
    piano: str | None = None
    alias: list[str] = field(default_factory=list)
    stato: str | None = None      # on, off, open, closed, locked, 20.5…
    unita: str | None = None      # °C, %, W…
    attributi: dict = field(default_factory=dict)   # posizione, temperatura impostata…


@dataclass
class Interpretazione:
    """Cosa farebbe un comando, prima di eseguirlo."""
    capito: bool
    azione: str = "altro"         # "comando" | "lettura" | "altro" (non è della casa)
    intento: str = ""             # nome dell'adattatore, solo per i log
    bersagli: list[str] = field(default_factory=list)    # id delle entità toccate
    # "predefinita": frasi standard del sistema; "propria": frasi o automazioni scritte da
    # chi gestisce la casa, che Calliope non conosce e non esegue
    origine: str = "predefinita"
    # Non capito: le parole che non corrispondono a niente («luce cucna»), per suggerire
    non_trovati: list[str] = field(default_factory=list)


@dataclass
class Esito:
    ok: bool
    tipo: str                     # "fatto" | "risposta" | "errore" | "rifiuto"
    frase: str = ""               # da dire (già in italiano)
    codice: str = ""              # errore: non_capito, nessun_bersaglio, fallito…
    bersagli: list[str] = field(default_factory=list)
    falliti: list[str] = field(default_factory=list)
    interpretazione: Interpretazione | None = None
    tempi: dict = field(default_factory=dict)


# Funzione di Calliope che decide se un comando interpretato si può eseguire: restituisce
# il motivo del rifiuto, o None se va bene
Autorizza = Callable[[Interpretazione], "str | None"]


@dataclass
class Diagnosi:
    """A che punto è l'integrazione: un codice stabile (per il tool casa_integrazione e
    le prove) e i dettagli che servono a spiegare il passo successivo. Nessun dettaglio
    contiene il token."""
    codice: str                   # vedi DIAGNOSI in guida.py
    dettagli: dict = field(default_factory=dict)


class HomeBackend:
    """Interfaccia di capacità della casa."""

    # Come si chiama il sistema nelle frasi di diagnosi («Home Assistant»)
    nome_sistema = "la casa"

    def entita(self) -> list[Entita]:
        """Le entità esposte, con lo stato aggiornato. Solleva CasaNonRisponde."""
        raise NotImplementedError

    def comando(self, testo: str, autorizza: Autorizza) -> Esito:
        """Interpreta la frase, chiede ad `autorizza` se si può, poi la esegue.
        Solleva CasaNonRisponde."""
        raise NotImplementedError

    def diagnosi(self, riprova: bool = False) -> Diagnosi:
        """Lo stato del collegamento; con `riprova` tenta subito di collegarsi."""
        raise NotImplementedError

    def attendi_primo_tentativo(self, max_s: float) -> bool:
        """Aspetta al più `max_s` la fine del primo tentativo di collegamento (per il
        riassunto dell'avvio). True se è finito, comunque sia andato."""
        return True

    def close(self):
        pass
