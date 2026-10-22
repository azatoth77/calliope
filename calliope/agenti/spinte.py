"""
La scala delle spinte dell'agente (22/10/2026, issue #224, epic #86; analisi del 19/10,
docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.4 n. 23, 24, 27 e § 4 «La scala»).

Prima le spinte erano frasi sparse in ciclo.py e ripetizioni.py, scritte in giorni diversi. Si
sommavano nello stesso messaggio (l'avviso di chiusura in coda alla spinta delle riscritture),
si contraddicevano (la nota della terza lettura «scrivi la versione corretta con scrivi_file»,
le altre «usa modifica_file, non riscrivere»; la modifica inversa «riscrivi il file con
scrivi_file») e rimproveravano («Ti ho fermato… Non ripensarci», «riscriverlo non serve»,
«Smetti di pensare»): il modello rispondeva con le scuse invece che con una modifica.

Qui l'unica sorgente:

- ogni spinta è un gradino con un nome (`GRADINI`): la regola nel registro del lavoro e il
  posto nella scala (chi sale vince);
- la forma è una sola: **il fatto, poi i passi ammessi** («Passi possibili: …»), presi da un
  vocabolario chiuso (`PASSI`). Niente giudizi, niente imperativi sul pensiero, niente divieti;
- ogni spinta dichiara anche i passi che il suo fatto sconsiglia (`esclusi`, mai detti come
  divieto: sono il motivo per cui mancano tra i passi). Due testi sono incompatibili se uno
  ammette un passo che l'altro esclude (`incompatibili`): la prova li genera tutti, spinte e
  note nei risultati degli strumenti, e controlla che nessuna coppia lo sia;
- `Scala` tiene le proposte di una passata e ne dice **al più una**, la più alta. Le altre si
  lasciano: quelle «una volta per lavoro» (l'avviso di chiusura, la spinta a consegnare) tornano
  alla passata dopo, perché chi le propone segna di averle dette solo quando escono.

Le note nei risultati degli strumenti (gradino 1: la rilettura, la riscrittura piccola, la
modifica inversa, l'uscita troncata) hanno la stessa forma e lo stesso vocabolario, perché
stanno nella stessa passata della spinta e non devono dirle il contrario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ─────────────────────────── il vocabolario dei passi ───────────────────────────
# Chiave → come si dice. I passi che una spinta esclude stanno qui come gli altri, ma nessuna
# spinta li ammette (la prova lo controlla): «riscrivi» (scrivi_file di un file che c'è, intero,
# per cambiarne un punto), «rileggi» (lo stesso file invariato, di nuovo), «ricerche» (altre
# ricerche a fine lavoro)
PASSI = {
    "leggi_punto": "leggi_file su quel punto",
    "modifica": "modifica_file sul punto da cambiare",
    "modifica_altro": "modifica_file su un altro punto",
    "scrivi": "scrivi_file",
    "scrivi_pezzi": "scrivi_file in pezzi più corti",
    "modifica_righe": "modifica_file sulle sole righe che servono",
    "test": "esegui_test",
    "test_se_cambiato": "esegui_test se il codice è cambiato",
    "consegna": "consegna con cosa funziona e cosa manca",
    "consegna_se_finito": "consegna, se il lavoro è finito",
    "resta": "una riga su cosa resta da fare",
    "prossimo": "lo strumento del prossimo passo",
    "piano": "piano (se non l'hai ancora chiamato)",
    "scarica_esempio": "scarica_esempio",
    "piano_no": "piano con fattibile=false, se il compito non si può fare",
    "impossibile": "consegna con esito impossibile, se il compito non si può fare",
    "relazione": "consegna con la relazione su ciò che hai trovato, e ciò che non hai trovato "
                 "detto come tale",
    "relazione_breve": "consegna con una relazione più breve, con i fatti essenziali e le fonti",
    "chiamata_intera": "la stessa chiamata intera, con argomenti più brevi",
    # solo esclusi
    "riscrivi": "scrivi_file dello stesso file intero",
    "rileggi": "leggi_file dello stesso file",
    "ricerche": "altre ricerche",
}
# Chi non li ammette mai: la prova controlla che nessun testo li proponga
SOLO_ESCLUSI = frozenset(("riscrivi", "rileggi", "ricerche"))


@dataclass(frozen=True)
class Gradino:
    """Un gradino della scala: `posto` più alto vince nella passata. `registra`: la regola si
    conta quando la spinta esce (False dove la conta già il rilevatore: il giro a vuoto, la
    troncata, la prosa con lo stato consegnabile)."""
    nome: str
    posto: int
    motivo: str               # per la scheda del lavoro («spinta», motivo)
    registra: bool = True


# Dall'alto in basso. L'uscita troncata è un fatto del sistema (la chiamata non è partita): se
# non lo sa, l'agente crede di aver scritto il file. L'avviso di chiusura viene subito dopo: è
# una volta per lavoro, vicino al tetto, e la passata dopo potrebbe non esserci. Poi i giri a
# vuoto, dal più preciso (la frase ripetuta, il file riscritto) al più generico
GRADINI = {g.nome: g for g in (
    Gradino("agente_uscita_troncata", 90, "uscita troncata", registra=False),
    Gradino("agente_avviso_fine", 80, "vicino ai tetti del lavoro"),
    Gradino("agente_ragionamento_ripetuto", 70, "ragionamento ripetuto", registra=False),
    Gradino("agente_riscrittura_ripetuta", 60, "riscrive il file intero"),
    Gradino("agente_ragionamento_senza_strumenti", 50, "ragionamento senza strumenti"),
    Gradino("agente_senza_novita", 40, "passate di fila senza novità"),
    Gradino("agente_prosa_non_consegna", 35, "nessuno strumento chiamato", registra=False),
    Gradino("agente_spinta_strumenti", 30, "nessuno strumento chiamato"),
    Gradino("agente_spinta_consegna", 20, "i test passano"),
)}

# Le note nei risultati degli strumenti (gradino 1): stessa forma, nessuna scelta da fare (ogni
# nota sta nel suo risultato), ma lo stesso vocabolario delle spinte
NOTE = ("agente_rilettura", "agente_riscrittura_piccola", "agente_modifica_inversa",
        "agente_uscita_troncata_chiamata", "agente_manifesto_rifiutato")


@dataclass(frozen=True)
class Spinta:
    nome: str
    testo: str
    ammessi: tuple = ()
    esclusi: tuple = field(default=())

    @property
    def gradino(self) -> Gradino:
        return GRADINI.get(self.nome) or Gradino(self.nome, 0, self.nome)


def passi_detti(passi) -> str:
    """«Passi possibili: A, B o C.» I passi sono (chiave, testo) o chiavi di PASSI."""
    detti = [t if t else PASSI[k] for k, t in passi]
    if not detti:
        return ""
    elenco = detti[0] if len(detti) == 1 else ", ".join(detti[:-1]) + " o " + detti[-1]
    return f"Passi possibili: {elenco}."


def _fai(nome: str, fatto: str, passi, esclusi=()) -> Spinta:
    """Il fatto (una frase o due, col punto) e i passi ammessi, nel testo e nei campi."""
    passi = [(p, None) if isinstance(p, str) else p for p in passi]
    for k, _ in passi:
        if k not in PASSI:
            raise KeyError(f"passo fuori dal vocabolario: {k}")
    fatto = fatto.strip()
    testo = (fatto + " " + passi_detti(passi)).strip()
    return Spinta(nome, testo, tuple(k for k, _ in passi), tuple(esclusi))


def incompatibili(a: Spinta, b: Spinta) -> set:
    """I passi che una delle due ammette e l'altra esclude (vuoto: compatibili)."""
    return (set(a.ammessi) & set(b.esclusi)) | (set(b.ammessi) & set(a.esclusi))


# ─────────────────────────── l'errore e il suo punto ───────────────────────────

def errore_detto(errore: dict | None) -> str:
    """«l'ultimo errore è X in gioco.js:412» (diagnosi.py), o vuoto."""
    if not errore:
        return ""
    from .diagnosi import riga
    dove = errore.get("dove") or ""
    testo = riga(dict(errore, dove=""), 240)
    return f"l'ultimo errore è «{testo}»" + (f" in {dove}" if dove else "")


def primo_punto(errore: dict) -> tuple[str, str]:
    """(file, riga) del punto più interno di «dove» («logica.js:20 (crea) ← gioco.js:4»)."""
    m = re.match(r"\s*([\w./-]+\.\w+):(\d+)", str(errore.get("dove") or ""))
    return (m.group(1), m.group(2)) if m else ("", "")


def _fatto_errore(errore: dict | None) -> str:
    detto = errore_detto(errore)
    return f"{detto[:1].upper()}{detto[1:]}." if detto else ""


def _passi_errore(errore: dict | None) -> list:
    """Sul punto dell'ultimo errore: leggerlo, cambiarlo lì, rifare i test."""
    f, r = primo_punto(errore or {})
    leggi = (f"leggi_file con percorso «{f}» e riga {r}" if f
             else "leggi_file sul codice che lo produce")
    return [("leggi_punto", leggi), ("modifica", "modifica_file su quel punto"), "test"]


# ─────────────────────────── le spinte (gradino 2: un messaggio) ───────────────────────────

def ripetizioni(frase: str = "", errore: dict | None = None) -> Spinta:
    """Dopo una passata fermata per giro a vuoto (ripetizioni.py). Con l'ultimo errore noto
    (11/10, giro vero della DGX: un piano ripetuto una decina di volte, poi gioco.js riscritto
    intero) i passi sono sul punto dell'errore. *[storico: «Ti ho fermato: stai ripetendo lo
    stesso ragionamento… Non ripensarci: decidi adesso…» fino al 22/10]*"""
    frase = frase if isinstance(frase, str) else ""
    fatto = ("La passata si è fermata: il ragionamento ripeteva la stessa frase"
             + (f" («{frase[:120]}»)" if frase else "") + " e nessuno strumento è partito.")
    if errore_detto(errore):
        return _fai("agente_ragionamento_ripetuto", fatto + " " + _fatto_errore(errore),
                    _passi_errore(errore), esclusi=("riscrivi",))
    return _fai("agente_ragionamento_ripetuto", fatto,
                [("leggi_punto", "leggi_file"), "scrivi", "test", "consegna"])


def riscritture(percorso: str, volte: int, errore: dict | None = None) -> Spinta:
    """Dopo `volte` riscritture intere dello stesso file con lo stesso errore (11/10).
    *[storico: «…: riscriverlo non serve.» fino al 22/10]*"""
    fatto = (f"Hai riscritto {percorso} per intero {volte} volte e i test falliscono ancora "
             "con lo stesso errore.")
    if errore_detto(errore):
        return _fai("agente_riscrittura_ripetuta", fatto + " " + _fatto_errore(errore),
                    _passi_errore(errore), esclusi=("riscrivi",))
    return _fai("agente_riscrittura_ripetuta", fatto,
                [("leggi_punto", "leggi_file sulla riga che l'uscita dei test indica"),
                 ("modifica", "modifica_file su quella riga"), "test"], esclusi=("riscrivi",))


def senza_strumenti(token: int, nomi=None) -> Spinta:
    """Dopo il ragionamento a vuoto (05/10): tanti token senza chiamate. `nomi`: gli strumenti
    offerti nella passata (20/10, seconda revisione della PR #188: a un gioco scarica_esempio
    non si dà, a un programma nemmeno piano). None: tutti. *[storico: «Stai ragionando da N
    token senza usare gli strumenti. Smetti di pensare e agisci adesso…» fino al 22/10]*"""
    nomi = None if nomi is None else set(nomi)

    def c(n):
        return nomi is None or n in nomi
    passi = [p for p, ok in (("piano", c("piano")), ("scarica_esempio", c("scarica_esempio")),
                             ("scrivi", c("scrivi_file"))) if ok]
    passi += (["piano_no"] if c("piano") else []) + ["impossibile"]
    quanti = f"{int(token):,}".replace(",", ".")
    return _fai("agente_ragionamento_senza_strumenti",
                f"Da {quanti} token non è partita nessuna chiamata di funzione: il "
                "ragionamento da solo non cambia i file.", passi)


def prosa_consegnabile() -> Spinta:
    """Una passata senza chiamate con lo stato consegnabile (19/10, #180): un fatto, non una
    consegna."""
    return _fai("agente_prosa_non_consegna",
                "Nessuno strumento chiamato in questa passata: il testo da solo non chiude il "
                "lavoro. I file sono quelli dell'ultimo esegui_test, che passava.",
                ["consegna_se_finito", "prossimo"])


def prosa() -> Spinta:
    """Una passata senza chiamate. *[storico: «Usa gli strumenti con chiamate di funzione vere:
    scrivi i file con scrivi_file, prova con esegui_test, e alla fine chiama consegna.» fino al
    22/10]*"""
    return _fai("agente_spinta_strumenti",
                "Nessuno strumento chiamato in questa passata: il testo non scrive file e non "
                "esegue test, servono chiamate di funzione vere.",
                [("scrivi", "scrivi_file o modifica_file"), "test", "consegna"])


def consegna() -> Spinta:
    """Il primo esegui_test tutto verde, con i file che il lavoro chiede (13/10): una volta per
    lavoro, la consegna resta dell'agente."""
    return _fai("agente_spinta_consegna",
                "I tuoi test passano e i file che il lavoro chiede ci sono.",
                ["consegna_se_finito", ("resta", "altrimenti una riga su cosa manca e il "
                                                 "prossimo strumento")])


# L'avviso di chiusura (06/10), senza numeri (12/10 sera, ricerca 2026-10-12-flusso-agente-fasi
# § 5.1: il budget come azione, non come conto alla rovescia). Dal 22/10 nella forma della scala:
# «Adesso chiudi: non cominciare cose nuove…», «senza ragionare sul tempo o sulle passate», «non
# consegnare a metà», «Non riscrivere i file che funzionano» sono storici
def fine(tipo: str = "codice") -> Spinta:
    """`tipo`: codice, tappa (un lavoro di uno sviluppo: il tetto è una tappa, non la fine),
    ricerca, verde e verde_tappa (l'ultimo esegui_test era verde e da allora niente è cambiato:
    13/10, banco della temperatura, codice giusto e nessuna consegna)."""
    n = "agente_avviso_fine"
    if tipo == "tappa":
        return _fai(n, "Il lavoro continua da qui con i tuoi file, anche dopo questo giro.",
                    [("scrivi", "scrivi_file o modifica_file"), "test",
                     ("consegna_se_finito", "consegna con cosa funziona e cosa manca, se il "
                                            "lavoro è finito e i test passano"),
                     ("resta", "con il lavoro a metà, una riga su cosa resta da fare")])
    if tipo == "ricerca":
        return _fai(n, "È il momento di chiudere la ricerca con quello che c'è.", ["relazione"],
                    esclusi=("ricerche",))
    if tipo == "verde":
        return _fai(n, "I tuoi test passano e i file non sono cambiati da allora.",
                    ["consegna"], esclusi=("riscrivi",))
    if tipo == "verde_tappa":
        return _fai(n, "I tuoi test passano e i file non sono cambiati da allora.",
                    ["consegna_se_finito", ("resta", "altrimenti il prossimo passo e una riga "
                                                     "su cosa resta da fare")],
                    esclusi=("riscrivi",))
    return _fai(n, "È il momento di chiudere il lavoro con quello che c'è.",
                ["test_se_cambiato", "consegna"])


# Il conto di fila delle passate senza novità (22/10, #224, n. 27): al gradino la spinta, una
# volta per fila (la fila riparte con una novità). Le passate di sola lettura contano: sei di
# fila senza cambiare né file né esito dei test sono già un giro a vuoto
SENZA_NOVITA_FILA = 6


def senza_novita(n: int, errore: dict | None = None) -> Spinta:
    fatto = (f"Le ultime {n} passate non hanno cambiato i file né l'esito dei test: i "
             "contenuti scritti erano già visti, o niente è stato scritto.")
    if errore_detto(errore):
        return _fai("agente_senza_novita", fatto + " " + _fatto_errore(errore),
                    _passi_errore(errore) + ["consegna"], esclusi=("rileggi",))
    return _fai("agente_senza_novita", fatto, ["modifica", "test", "consegna"],
                esclusi=("rileggi",))


# L'uscita troncata (19/10, #185; 21/10, #189): il fatto è lo stesso nel codice e nella ricerca,
# i passi sono del ciclo
TRONCATA_CHIAMATA = ("la tua uscita è stata troncata (fermata a max_tokens): questa chiamata è "
                     "arrivata a metà e non l'ho eseguita.")
TRONCATA_TESTO = ("La tua uscita è stata troncata (fermata a max_tokens) prima di una chiamata "
                  "completa.")


def troncata(dove: str = "codice") -> Spinta:
    """`dove`: codice (il file in pezzi), ricerca_testo (un testo a metà non è una relazione),
    pensiero (fermato il solo ragionamento). *[storico: «Ragiona meno e chiama lo strumento…»
    fino al 22/10]*"""
    n = "agente_uscita_troncata"
    if dove == "ricerca_testo":
        return _fai(n, TRONCATA_TESTO + " Un testo a metà non è una relazione.",
                    ["relazione_breve"])
    if dove == "pensiero":
        return _fai(n, TRONCATA_TESTO, ["prossimo", ("consegna", "consegna")])
    return _fai(n, TRONCATA_TESTO, ["scrivi_pezzi", "modifica_righe"])


# ─────────────────────────── le note (gradino 1: nel risultato) ───────────────────────────

def nota_troncata(dove: str = "codice") -> Spinta:
    """L'errore della chiamata arrivata a metà: codice (un file), ricerca (la consegna con la
    relazione), strumento (un altro strumento della ricerca)."""
    n = "agente_uscita_troncata_chiamata"
    if dove == "ricerca":
        return _fai(n, TRONCATA_CHIAMATA, ["relazione_breve"])
    if dove == "strumento":
        return _fai(n, TRONCATA_CHIAMATA, ["chiamata_intera"])
    return _fai(n, TRONCATA_CHIAMATA, ["scrivi_pezzi", "modifica_righe"])


def nota_rilettura(volte: int) -> Spinta:
    """La terza lettura di un file invariato (06/10; per file e contenuto dal 19/10, #185).
    *[storico: «…non rileggerlo né rileggere gli altri file. Scrivi adesso la versione corretta
    con scrivi_file ed esegui i test» fino al 22/10: contro «usa modifica_file, non riscrivere»
    delle altre]*"""
    return _fai("agente_rilettura",
                f"hai letto questo file {volte} volte senza cambiarlo: il contenuto è qui.",
                ["modifica", "test", "consegna"], esclusi=("rileggi",))


def nota_riscrittura(nome: str, righe: int, cambiate: int) -> Spinta:
    """Un file lungo riscritto intero per cambiarne poche righe (13/10)."""
    return _fai("agente_riscrittura_piccola",
                f"Hai riscritto {nome} intero ({righe} righe) per cambiarne {cambiate}.",
                [("modifica", "modifica_file (vecchio → nuovo) per un pezzo, che lascia com'è "
                              "il resto del file")], esclusi=("riscrivi",))


def nota_modifica_inversa(quando: str, test: str = "") -> Spinta:
    """La modifica che rimette il testo tolto da una precedente, con la cartella com'era subito
    dopo quella (19/10, #185). *[storico: «Se vuoi davvero tornare a com'era, riscrivi il file
    con scrivi_file» fino al 22/10]*"""
    fatto = ("questa modifica rimette esattamente il testo che la tua modifica_file di "
             f"{quando} aveva tolto, e non l'ho fatta"
             + (f"; prima di quella modifica esegui_test dava: {test}" if test else "") + ".")
    return _fai("agente_modifica_inversa", fatto, ["modifica_altro", "test"],
                esclusi=("riscrivi",))


def nota_manifesto(errore: str) -> Spinta:
    """manifesto.json che la consegna rifiuterebbe (14/10 sera, banco L8)."""
    return _fai("agente_manifesto_rifiutato",
                f"manifesto.json così la consegna lo rifiuta: {str(errore).rstrip('. ')}.",
                [("modifica", "modifica_file su manifesto.json")])


# ─────────────────────────── la scala di una passata ───────────────────────────

class Scala:
    """Le spinte proposte in una passata; `scegli` dà la più alta (al più una) e le lasciate.
    La stessa spinta proposta due volte vale una (l'ultima)."""

    def __init__(self):
        self.proposte: dict[str, Spinta] = {}

    def proponi(self, s: Spinta | None) -> None:
        if s is not None:
            self.proposte[s.nome] = s

    def __bool__(self):
        return bool(self.proposte)

    def scegli(self) -> tuple[Spinta | None, list]:
        if not self.proposte:
            return None, []
        ordine = sorted(self.proposte.values(), key=lambda s: -s.gradino.posto)
        self.proposte = {}
        return ordine[0], ordine[1:]


# ─────────────────────────── per la prova ───────────────────────────
# Le parole che non stanno in nessun testo della scala (giudizi, rimproveri, imperativi sul
# pensiero): la prova le cerca in tutti i testi generati
PAROLE_VIETATE = (r"\bti ho fermato\b", r"\bripensar", r"\bsmetti\b", r"\bnon serve\b",
                  r"\bpensare\b", r"\bragiona\b", r"\bsenza ragionare\b", r"\bonest",
                  r"\bdevi\b", r"\bhai sbagliato\b", r"\badesso chiudi\b", r"\bdecidi\b",
                  r"\bnon riscrivere\b", r"\bnon rileggerlo\b", r"\bsei incerto\b")


def tutte(errore: dict | None = None) -> list[Spinta]:
    """Ogni testo della scala, con e senza errore, per la prova."""
    e = errore or {"test": "test_x", "errore": "AssertionError: 1 != 2", "dove": "a.py:3"}
    out = []
    for err in (None, e):
        out += [ripetizioni("una frase", err), ripetizioni("", err), riscritture("a.py", 3, err),
                senza_novita(SENZA_NOVITA_FILA, err)]
    out += [senza_strumenti(12000), senza_strumenti(12000, ["scrivi_file"]), prosa(),
            prosa_consegnabile(), consegna()]
    out += [fine(t) for t in ("codice", "tappa", "ricerca", "verde", "verde_tappa")]
    out += [troncata(d) for d in ("codice", "ricerca_testo", "pensiero")]
    out += [nota_troncata(d) for d in ("codice", "ricerca", "strumento")]
    out += [nota_rilettura(3), nota_riscrittura("a.py", 40, 1),
            nota_modifica_inversa("2 passate fa", "1 test su 1 non passavano"),
            nota_modifica_inversa("una passata fa"), nota_manifesto("manca il nome")]
    return out
