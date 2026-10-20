"""
Costanti e piccole funzioni comuni a più moduli (06/10, proposta P10 dell'analisi
complessiva): prima ognuna aveva la sua copia, e una correzione andava fatta in 10–17 posti.

Solo libreria standard: lo importa anche il pacchetto del satellite.
"""

import re

# Il campo «fatto» dei risultati dei tool rifiutati: con un semplice «non permesso» il
# modello diceva «ho registrato…» (vedi la memoria in CLAUDE.md)
NIENTE = "NIENTE: l'azione NON è stata eseguita"

# Il motore del gioco nei test dell'agente (20/10, issue #192): nel contratto del gioco, nei
# vincoli e nel rimando di una correzione. Dopo #186 la frase stava solo in gioco.test.js di
# partenza, che una correzione non riceve, e nelle porte del banco del 20/10 l'agente ha scritto
# un apriGioco suo (un motore finto, che copre quello vero di agenti/test_js.mjs)
APRI_GIOCO_C_E = ("apriGioco e creaCaso ci sono già in gioco.test.js, senza require: non "
                  "scriverli tu")

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


class Pezzo(str):
    """Un pezzo della risposta per la voce (tts.split_sentences, 17/10, issue #132): il testo, e
    in più `aperta` (la frase continua nel pezzo dopo: tagliata a un «; ») e `prima` (i pezzi
    della stessa frase già mandati, uniti da uno spazio). Le reti che giudicano una frase alla
    volta (riferire, guardiano, l'annuncio di un tool) giudicano `intera()`: mai meno testo di
    quando la frase arrivava tutta insieme.

    Si salva e si confronta come una stringa (json, sqlite, pickle, «==»); non va scritto con
    yaml.safe_dump, che non conosce le sottoclassi: prima `str(pezzo)`.
    """

    aperta: bool
    prima: str

    def __new__(cls, testo: str, aperta: bool = False, prima: str = ""):
        p = super().__new__(cls, testo)
        p.aperta, p.prima = bool(aperta), str(prima or "")
        return p

    def intera(self) -> str:
        """La frase fino a questo pezzo compreso."""
        return f"{self.prima} {self}" if self.prima else str(self)

    def con(self, testo: str) -> "Pezzo":
        """Lo stesso pezzo con un altro testo (una rete l'ha cambiato), stessa frase."""
        return Pezzo(testo, self.aperta, self.prima)


def di_frase(x) -> tuple[bool, str]:
    """(aperta, prima) di un elemento qualunque dello stream: una stringa semplice è una frase
    intera."""
    return bool(getattr(x, "aperta", False)), str(getattr(x, "prima", "") or "")


def _aperta(testo: str) -> bool:
    """Il testo finisce dentro una citazione o una parentesi ancora aperta."""
    return (testo.count("«") > testo.count("»") or testo.count('"') % 2 == 1
            or testo.count("“") > testo.count("”") or testo.count("(") > testo.count(")")
            or testo.count("[") > testo.count("]"))


def taglio_voce(buf: str, min_chars: int = 25, pausa_oltre: int = PAUSA_OLTRE,
                inizio: int = 0) -> tuple[int, bool] | None:
    """Dove finisce il prossimo pezzo di `buf` da mandare al TTS: (posizione, al «;»), oppure
    None (si aspetta altro testo). `buf` comincia dove comincia la frase, `inizio` è la fine
    del pezzo già mandato (un taglio a un «;» di prima).

    È la fine di una frase (SENTENCE_END) dopo almeno `min_chars` caratteri; se non c'è, il
    primo «; » dopo `inizio` che va bene: la frase (dall'ultima fine di frase, anche breve,
    o dall'inizio di `buf`) supera `pausa_oltre` caratteri; una clausola di almeno
    PAUSA_CLAUSOLA_MIN caratteri dal «;», dai due punti o dalla fine di frase di prima, così
    un elenco («servono queste cose: farina; uova; latte») non si spezza; fuori da virgolette,
    parentesi e quadre; non fra due cifre («3; 4»). Il «;» resta nel pezzo, come in
    tts.primo_pezzo: la voce ha l'intonazione sospesa e non quella di fine frase.
    `pausa_oltre` 0 = solo la fine della frase.

    Guarda solo il testo prima del taglio, misurato dalla frase: tts.split_sentences e le reti
    di Brain che trattengono il testo (ClaimHold, FraseTolta) tagliano negli stessi punti
    anche se cominciano il loro buffer da frasi diverse, e la stessa frase si taglia uguale in
    streaming e tutta in una volta (Ciclo._storia_come_detta la ridivide)."""
    fine = next((m.end() for m in SENTENCE_END.finditer(buf, inizio) if m.end() >= min_chars),
                None)
    limite = fine if fine is not None else len(buf)
    if pausa_oltre > 0 and limite - inizio > 0:
        fini = [m.end() for m in SENTENCE_END.finditer(buf, 0, limite)]
        for m in _PUNTO_E_VIRGOLA.finditer(buf, inizio, limite):
            base = max((e for e in fini if e <= m.start()), default=0)
            # La frase senza gli spazi intorno: una di 120 caratteri esatti non si taglia
            if len(buf[base:limite].strip()) <= pausa_oltre:
                continue
            da = max([base] + [x.end() for x in _PUNTO_E_VIRGOLA.finditer(buf, base, m.start())])
            clausola = buf[da:m.start()]
            clausola = clausola[clausola.rfind(":") + 1:].strip()
            if len(clausola) < PAUSA_CLAUSOLA_MIN or _aperta(buf[base:m.start()]):
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
