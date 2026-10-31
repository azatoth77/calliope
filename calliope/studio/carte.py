"""
Le carte dello Studio e il loro ripasso dilazionato (30/10, passo 6, issue #246, epic #251,
decisione 0035 punto 33; progetto § «Studio 5 · Ripasso con le carte»). Funzioni pure: il servizio
(`servizio.Studio`) legge e scrive il db.

**Il ripasso: Leitner a cinque scatole**, tutto nel codice, mai il modello:
- una carta nuova è nella scatola 1 e si ripassa subito;
- «La sapevo»: scatola + 1 (al più `SCATOLE`), la prossima volta fra `INTERVALLI[scatola]` giorni;
- «Quasi»: la scatola resta, la prossima volta domani;
- a tarda sera «domani» non è fra pochi minuti (31/10, #356): la scadenza a giorni è la più tarda
  fra la mezzanotte di quel giorno e adesso più l'intervallo meno `MARGINE_ORE` ore (per «domani»
  adesso + 12 ore);
- «Non la sapevo»: scatola 1, di nuovo fra `DI_NUOVO_MIN` minuti (nella stessa sessione);
- prima della verifica nessuna scadenza va oltre la **vigilia** (il giorno di ripasso del piano).
Le soglie sono iniziali, da tarare in ombra sulle risposte vere (decisione 4 del 27/10): si
cambiano qui, le prove le leggono da qui. Alternative scartate nell'analisi della #246: SM-2 (una
facilità per carta che in poche settimane non si stabilizza) e FSRS (vuole storie lunghe).

**L'esito** lo decidono la persona (i tre tasti, o a voce una forma chiusa breve detta per intero:
`autovalutazione`, principio 10) o il codice per le risposte chiuse (`risposta_giusta`: un
numero, un anno, al più tre parole, e solo il «giusto»). Mai il modello. Ogni esito è un tentativo
di tipo «carta» sull'argomento (`ESITO_TENTATIVO`, la padronanza del passo 5).

**Il testo di una carta è un dato** (decisione 0035 punto 6), chiunque l'abbia scritto: sullo
schermo solo textContent, al modello solo in busta (`tools/studio.py`, `studio_carte`), mai nelle
frasi pronte né nel registro.
"""

from __future__ import annotations

import datetime
import re
import unicodedata

# Le scatole di Leitner e gli intervalli in giorni dopo «La sapevo» (la scatola nuova)
SCATOLE = 5
INTERVALLI = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
# «Non la sapevo»: di nuovo nella stessa sessione
DI_NUOVO_MIN = 10
# «Quasi»: domani
QUASI_GIORNI = 1
# Una scadenza a giorni non arriva prima di tanti giorni meno queste ore (#356): alle 23:50 «quasi»
# tornava a mezzanotte, dopo 10 minuti come «non la sapevo»
MARGINE_ORE = 12

SAPEVO, QUASI, NON_SAPEVO = "sapevo", "quasi", "non_sapevo"
ESITI = (SAPEVO, QUASI, NON_SAPEVO)
# L'esito di una carta come tentativo della padronanza (padronanza.ESITI)
ESITO_TENTATIVO = {SAPEVO: "giusto", QUASI: "indizio", NON_SAPEVO: "sbagliato"}

# «ombra» (seconda parte del passo 6): una carta generata con `studio_carte_genera: ombra`, che
# si misura e non va mai alla persona; «proposta»: generata, aspetta la persona o il tutore
STATI = ("attiva", "proposta", "tolta", "ombra")
# «mappa» (revisione della PR #330): le carte di «Fanne carte», scritte dalla persona dagli errori
# della mappa; con la mappa libera aperta non si vedono (servizio._carte_di, _carta)
# «libreria» (31/10, #297): le carte di un mazzo della libreria, aggiunte dalla persona o dal tutore
# con «Aggiungi le carte» (studio/libreria/studio.py, `aggiungi_mazzo`)
ORIGINI = ("persona", "modello", "mappa", "libreria")
DOMANDA_MAX = 240
RISPOSTA_MAX = 240
# Una risposta «chiusa» (la controlla il codice): un numero o al più tante parole
CHIUSA_PAROLE = 3
# La frase detta con la risposta: oltre tante parole non si confronta (una spiegazione lunga può
# contenere la risposta per caso)
FRASE_MAX_PAROLE = 10
# Le carte di una verifica
CARTE_MAX = 300


def _dt(x) -> datetime.datetime:
    if isinstance(x, datetime.datetime):
        return x
    if isinstance(x, datetime.date):
        return datetime.datetime.combine(x, datetime.time())
    return datetime.datetime.fromisoformat(str(x))


def testo_normale(testo, massimo: int) -> str:
    """Una domanda o una risposta: una riga, senza caratteri di controllo né di direzione, al più
    `massimo` caratteri. Vuota → ValueError."""
    t = re.sub(r"[\x00-\x1f\x7f ​-‏‪-‮⁦-⁩]", " ",
               str(testo or ""))
    t = " ".join(t.split())[:massimo].strip()
    if not t:
        raise ValueError("manca il testo")
    return t


# ─────────────────────────── il ripasso ───────────────────────────

def prossima(scatola: int, esito: str, adesso, vigilia=None) -> tuple[int, str]:
    """(scatola nuova, scadenza AAAA-MM-GGTHH:MM:SS) dopo un esito. `vigilia`: il giorno prima
    della verifica; se è dopo oggi nessuna scadenza va oltre (la vigilia è di ripasso)."""
    if esito not in ESITI:
        raise ValueError("esito sconosciuto")
    adesso = _dt(adesso).replace(microsecond=0)
    oggi = adesso.date()
    s = max(1, min(SCATOLE, int(scatola or 1)))
    if esito == NON_SAPEVO:
        return 1, (adesso + datetime.timedelta(minutes=DI_NUOVO_MIN)).isoformat()
    if esito == QUASI:
        giorni = QUASI_GIORNI
    else:
        s = min(SCATOLE, s + 1)
        giorni = INTERVALLI[s]
    # La più tarda fra la mezzanotte del giorno e adesso + giorni − MARGINE_ORE (31/10, #356)
    scadenza = max(datetime.datetime.combine(oggi + datetime.timedelta(days=giorni),
                                             datetime.time()),
                   adesso + datetime.timedelta(days=giorni, hours=-MARGINE_ORE))
    if vigilia is not None:
        v = _dt(vigilia).date()
        tetto = datetime.datetime.combine(v, datetime.time())
        if v > oggi and scadenza > tetto:
            scadenza = tetto
    return s, scadenza.isoformat()


def da_ripassare(carta: dict, adesso) -> bool:
    """La carta è attiva e scaduta (la scadenza vuota vale subito)."""
    if carta.get("stato") != "attiva":
        return False
    sc = carta.get("scadenza")
    if not sc:
        return True
    try:
        return _dt(sc) <= _dt(adesso)
    except (TypeError, ValueError):
        return True


def fra_quanto(scadenza, adesso) -> str:
    """«fra 10 minuti», «domani», «fra 4 giorni», «adesso» (per i tasti e la voce, dal codice)."""
    s, a = _dt(scadenza), _dt(adesso)
    if s <= a:
        return "adesso"
    giorni = (s.date() - a.date()).days
    # Entro un'ora sono minuti anche oltre la mezzanotte (revisione della PR #324, nota 4: alle
    # 23:55 «non la sapevo» torna alle 00:05, «fra 10 minuti», non «domani»)
    if giorni <= 0 or (s - a) < datetime.timedelta(hours=1):
        m = max(1, int(round((s - a).total_seconds() / 60)))
        return f"fra {m} minut{'o' if m == 1 else 'i'}"
    return "domani" if giorni == 1 else f"fra {giorni} giorni"


# ─────────────────────────── le risposte ───────────────────────────

def normale(testo) -> list[str]:
    """Le parole di un testo per il confronto: minuscole, senza accenti né punteggiatura, gli
    apostrofi come spazi, i numeri in lettere (la trascrizione scrive «1861», la carta può dire
    «milleottocentosessantuno»), «e» e gli articoli tolti solo se il testo ha altro."""
    from ..numeri import in_lettere
    t = unicodedata.normalize("NFKD", str(testo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", t)          # «1.861», «1 861»
    out = []
    for w in re.findall(r"[a-z0-9]+", t):
        if w.isdecimal() and len(w) <= 6:
            w = in_lettere(int(w)).replace(" ", "")
        out.append(w)
    return out


# Articoli e preposizioni: non contano né nella forma chiusa né nella frase («Nel 1453» e «il
# 1453» valgono «1453»)
_ARTICOLI = frozenset("il lo la i gli le l un uno una di del dello della dei degli delle a al "
                      "allo alla ai agli alle da dal dallo dalla dai dagli dalle in nel nello "
                      "nella nei negli nelle con col su sul sullo sulla sui sugli sulle per tra "
                      "fra".split())


def chiusa(risposta) -> str | None:
    """La forma chiusa di una risposta, se il codice la può controllare: un numero (anche con
    l'unità) o al più `CHIUSA_PAROLE` parole senza gli articoli. Altrimenti None (vale solo
    l'autovalutazione)."""
    ps = [w for w in normale(risposta) if w not in _ARTICOLI]
    if not ps or len(ps) > CHIUSA_PAROLE:
        return None
    return " ".join(ps)


_NEGAZIONI = frozenset({"non", "no", "nemmeno", "neanche", "mica"})


_PICCOLI = None


def corta(chiusa_: str | None) -> bool:
    """Una risposta chiusa che sta facilmente dentro una frase detta per altro (revisione della
    PR #324, nota 2): una forma dell'autovalutazione («sì», «no», «quasi»), una parola di al più
    tre lettere, o un numero fino a venti. Per queste vale solo la frase intera."""
    global _PICCOLI
    if not chiusa_:
        return False
    if _PICCOLI is None:
        from ..numeri import in_lettere
        _PICCOLI = {in_lettere(n).replace(" ", "") for n in range(21)}
    ps = chiusa_.split()
    return (autovalutazione(chiusa_) is not None
            or (len(ps) == 1 and (len(ps[0]) <= 3 or ps[0] in _PICCOLI)))


def risposta_giusta(chiusa_: str | None, detto) -> bool:
    """La frase detta contiene la risposta chiusa (le sue parole di fila), non negata subito prima
    e in una frase corta. Solo il «giusto»: il contrario non vuol dire sbagliato (la trascrizione
    può sbagliare un nome), e allora vale l'autovalutazione. Una risposta `corta` vale solo se è
    la frase intera («sì, accendi la luce» non è la risposta «sì»)."""
    if not chiusa_:
        return False
    cerca = chiusa_.split()
    ps = [w for w in normale(detto) if w not in _ARTICOLI]
    while ps and ps[0] in _INTORNO:
        ps = ps[1:]
    while ps and ps[-1] in _INTORNO:
        ps = ps[:-1]
    if corta(chiusa_):
        return ps == cerca
    if not ps or len(ps) > FRASE_MAX_PAROLE:
        return False
    n = len(cerca)
    for i in range(len(ps) - n + 1):
        if ps[i:i + n] == cerca and not (i and ps[i - 1] in _NEGAZIONI) and not (
                i > 1 and ps[i - 2] in _NEGAZIONI and ps[i - 1] in ("e", "era", "e'")):
            return True
    return False


# L'autovalutazione a voce: la frase intera, dopo il nome, i saluti e la punteggiatura, deve
# essere una di queste forme chiuse (principio 10: una forma breve riconosciuta per intero, mai
# una parola dentro la frase). Ognuna coi suoi contrari nelle prove (prova_studio_carte.py)
_FORME = {
    SAPEVO: ("si", "sì", "sapevo", "la sapevo", "lo sapevo", "si la sapevo", "si lo sapevo",
             "si sapevo", "giusto", "giusta", "esatto", "esatta", "la so", "lo so",
             "si la so", "si lo so", "la sapevo bene", "lo sapevo bene", "la sapevo si",
             "ce l ho fatta", "indovinata", "l ho indovinata", "presa"),
    QUASI: ("quasi", "piu o meno", "in parte", "quasi giusta", "quasi giusto", "la sapevo quasi",
            "lo sapevo quasi", "abbastanza", "cosi cosi", "mezza", "a meta", "quasi si"),
    NON_SAPEVO: ("no", "non la sapevo", "non lo sapevo", "non sapevo", "no non la sapevo",
                 "no non lo sapevo", "sbagliata", "sbagliato", "non la so", "non lo so",
                 "non me la ricordavo", "non me lo ricordavo", "non ricordavo", "non mi ricordavo",
                 "no non me la ricordavo", "boh", "non ne ho idea", "nessuna idea", "dimmela",
                 "non lo so dimmela", "non la so dimmela", "no dimmela"),
}
_INDICE = {" ".join(normale(f)): e for e, forme in _FORME.items() for f in forme}
_INTORNO = frozenset({"calliope", "allora", "beh", "mah", "ok", "okay", "ehm", "uhm", "eh",
                      "ah", "oh"})


def autovalutazione(frase) -> str | None:
    """L'esito detto dalla persona a voce, se la frase intera è una forma chiusa (`_FORME`); il
    nome e le interiezioni ai bordi non contano. Altrimenti None."""
    ps = normale(frase)
    while ps and ps[0] in _INTORNO:
        ps = ps[1:]
    while ps and ps[-1] in _INTORNO:
        ps = ps[:-1]
    if not ps or len(ps) > 6:
        return None
    return _INDICE.get(" ".join(ps))
