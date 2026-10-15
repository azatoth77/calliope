"""
Costanti e piccole funzioni comuni a più moduli (06/10, proposta P10 dell'analisi
complessiva): prima ognuna aveva la sua copia, e una correzione andava fatta in 10–17 posti.

Solo libreria standard: lo importa anche il pacchetto del satellite.
"""

import re

# Il campo «fatto» dei risultati dei tool rifiutati: con un semplice «non permesso» il
# modello diceva «ho registrato…» (vedi la memoria in CLAUDE.md)
NIENTE = "NIENTE: l'azione NON è stata eseguita"

# Livelli di chi parla (docs/architettura-tool.md)
ALL = frozenset({"ospite", "familiare", "amministra"})
FAMILY = frozenset({"familiare", "amministra"})
ADMIN = frozenset({"amministra"})
RANK = {"ospite": 0, "familiare": 1, "amministra": 2}
# I livelli ammessi «da questo livello in su»
LIVELLI_DA = {"ospite": ALL, "familiare": FAMILY, "amministra": ADMIN}

MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")

# Fine di una frase per lo streaming verso il TTS (tts.split_sentences, Brain)
SENTENCE_END = re.compile(r"[.!?…]+[\"»)\]]?\s+|\n+")

# Gli indirizzi che restano su questo computer
LOCALI = ("127.0.0.1", "localhost", "::1")


def solo_locale(host: str) -> bool:
    """L'indirizzo d'ascolto non esce da questo computer."""
    return str(host or "").strip() in LOCALI


def iban_ok(iban: str) -> bool:
    """IBAN con il controllo mod 97 (ISO 13616), senza spazi e in maiuscolo."""
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban or ""):
        return False
    n = "".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])
    return int(n) % 97 == 1


# Un ruolo, un titolo o una parentela non sono un nome (15/10, regressione col 26B sulla DGX):
# «Scusa, io sono chi amministra» → rinomina_interlocutore(nome="Amministratore"). Elenco
# chiuso, confrontato con l'argomento **per intero** (principio 10: mai una parola dentro il
# nome), senza accenti e maiuscole, togliendo articoli e possessivi davanti («la mia mamma») e
# un complemento con «di» dopo («padrone di casa», «mamma di Bianca»). «Mamo», «Capotondi»,
# «Admira» restano nomi. Usato da rinomina_interlocutore e da wakeword.risposta_al_nome.
RUOLI_NON_NOME = frozenset({
    "amministratore", "amministratrice", "amministratori", "chi amministra", "admin",
    "administrator", "sysadmin", "colui che amministra", "colei che amministra",
    "quello che amministra", "quella che amministra",
    "che amministro", "che amministra", "amministrazione",
    # Il verbo preso come nome (15/10, 26B: «io sono chi amministra» → nome="Amministra")
    "amministra", "amministro", "amministrare", "amministrante",
    "quello che comanda", "quella che comanda", "chi comanda",
    "padrone", "padrona", "proprietario", "proprietaria", "capofamiglia", "capo famiglia",
    "capo", "capa", "boss", "titolare", "responsabile", "gestore", "gestrice",
    "mamma", "mammina", "madre", "papa", "papi", "babbo", "padre", "genitore", "genitori",
    "nonno", "nonna", "nonnino", "nonnina", "figlio", "figlia", "fratello", "sorella",
    "marito", "moglie", "zio", "zia", "cugino", "cugina", "nipote", "suocero", "suocera",
    "compagno", "compagna", "fidanzato", "fidanzata", "tutore", "tutrice",
    "bambino", "bambina", "ragazzo", "ragazza",
    "ospite", "ospiti", "utente", "user", "guest", "familiare", "persona", "visitatore",
    "visitatrice", "signore", "signora", "signorina", "signor",
})
_RUOLO_TESTA = re.compile(
    r"^(?:(?:il|lo|la|l|i|gli|le|un|uno|una|mio|mia|miei|mie|tuo|tua|suo|sua|nostro|nostra|"
    r"vostro|vostra|io|sono|solo|semplicemente)\s+)+")
_RUOLO_CODA = re.compile(r"\s+(?:di|del|dello|della|dei|degli|delle|d)\s+.*$")


def ruolo_non_nome(nome: str) -> str | None:
    """Il ruolo o la parentela se `nome`, per intero, non è un nome ma uno di
    RUOLI_NON_NOME («Amministratore», «La Mamma», «Padrone Di Casa»); altrimenti None."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z]+", " ", t.casefold()).strip()
    if not t:
        return None
    t = _RUOLO_TESTA.sub("", t)
    for forma in (t, _RUOLO_CODA.sub("", t)):
        if forma in RUOLI_NON_NOME:
            return forma
    return None
