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

# Il taglio al «; » nello streaming (17/10, issue #132): col 26B le notizie arrivavano in una
# frase sola di 476 e 644 caratteri, coi fatti uniti da «;», e la voce aspettava la
# generazione intera (prima voce a 3,7 e 4,3 s). Una frase più lunga di PAUSA_OLTRE caratteri
# (`tts_spezza_streaming`) va al TTS anche a pezzi, dopo un «; »; mai dopo la virgola, troppo
# frequente: la voce sarebbe sospesa ogni 20–30 caratteri. È una conversione della forma
# (principio 10, regola `taglio_punto_e_virgola`): il testo resta uguale, cambia solo dove
# comincia la sintesi.
PAUSA_OLTRE = 120
PAUSA_CLAUSOLA_MIN = 40     # sotto, fra due «;» c'è un elenco («cose: farina; uova; latte»)
_PUNTO_E_VIRGOLA = re.compile(r";\s+")


def _aperta(testo: str) -> bool:
    """Il testo finisce dentro una citazione o una parentesi ancora aperta."""
    return (testo.count("«") > testo.count("»") or testo.count('"') % 2 == 1
            or testo.count("“") > testo.count("”") or testo.count("(") > testo.count(")"))


def taglio_voce(buf: str, min_chars: int = 25, pausa_oltre: int = PAUSA_OLTRE
                ) -> tuple[int, bool] | None:
    """Dove finisce il primo pezzo di `buf` da mandare al TTS: (posizione, al «;»), oppure
    None (si aspetta altro testo). È la fine di una frase (SENTENCE_END) dopo almeno
    `min_chars` caratteri; se non c'è, o arriva oltre `pausa_oltre` caratteri, il primo «; »
    che va bene: almeno `min_chars` caratteri prima; una clausola di almeno
    PAUSA_CLAUSOLA_MIN caratteri dal «;» o dai due punti di prima, così un elenco
    («servono queste cose: farina; uova; latte») non si spezza; fuori da virgolette e
    parentesi; non fra due cifre («3; 4»). Il «;» resta nel pezzo, come in tts.primo_pezzo:
    la voce ha l'intonazione sospesa e non quella di fine frase. `pausa_oltre` 0 = solo la
    fine della frase.

    Guarda solo il testo prima del taglio: le reti di Brain che trattengono il testo
    (ClaimHold, FraseTolta) lo lasciano passare negli stessi punti, e la stessa frase si
    taglia uguale in streaming e tutta in una volta (Ciclo._storia_come_detta la ridivide)."""
    fine = next((m.end() for m in SENTENCE_END.finditer(buf) if m.end() >= min_chars), None)
    limite = fine if fine is not None else len(buf)
    if pausa_oltre > 0 and limite > pausa_oltre:
        da = 0
        for m in _PUNTO_E_VIRGOLA.finditer(buf, 0, limite):
            clausola, da = buf[da:m.start()], m.end()
            clausola = clausola[clausola.rfind(":") + 1:].strip()
            if (m.end() < min_chars or len(clausola) < PAUSA_CLAUSOLA_MIN
                    or _aperta(buf[:m.start()])):
                continue
            if buf[m.start() - 1:m.start()].isdigit():
                if m.end() == len(buf):
                    return None             # «3; » e la cifra dopo può ancora arrivare
                if buf[m.end()].isdigit():
                    continue
            return m.end(), True
    return (fine, False) if fine is not None else None


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
