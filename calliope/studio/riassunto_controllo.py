"""
Il controllo del copione del riassunto, frase per frase (04/11/2026, issue #386, epic #251, decisione
0035 punto 57). Solo codice, nessun modello: una frase scritta dal modello si dice con la voce di
Calliope solo se ciò che afferma di preciso sta nelle pagine.

**Il terreno** (`Terreno`) è il testo delle pagine **ripulito** con le stesse regole del ripasso
(`ascolta.scarto`, con gli ordini in testa su tutte le pagine): una frase ostile non è un terreno,
così un numero o un nome che sta solo lì non vale. Le pagine con «ISTRUZIONI: sì» non sono terreno
per niente. Una frase con un numero di telefono non lo è mai.

**Cosa si cerca:**
- i **numeri**, scritti in cifre o in lettere, con l'unità (`unita.leggi` e `unita.parola_numero`):
  «millequattrocentonovantadue» è 1492, «due virgola sette grammi» è 2,7 g, «mille metri» è 1 km,
  «tre milioni» è 3000000. Con due unità della stessa grandezza si converte; con grandezze diverse
  il numero non è trovato. Il numero 1 senza unità non si cerca («uno dei»), e «un», «una» non sono
  numeri («in un secondo momento»);
- le **date**: il giorno col suo mese, come coppia («dodici ottobre» con «3 agosto» e «12 maggio»
  nella pagina non vale), e il mese da solo;
- gli **ordinali**: i secoli e i sovrani («quindicesimo secolo» con «XV sec.», «Carlo quinto» con
  «Carlo V»), tutti quelli in «-esimo»;
- le **frazioni** («un terzo», «tre quarti» con «1/3», «3/4»);
- le **formule** e le **sigle**, uguali; una formula detta a lettere («acca due o») solo se è la forma
  detta di una formula della pagina;
- i **nomi**: ogni parola con la maiuscola dentro la frase (anche storpiata di una lettera dall'OCR o
  con la stessa radice: «Italia», «italiani») e la prima parola, se non è una parola comune.

**Cosa non si dice mai**, anche se sta nella pagina: indirizzi, numeri di telefono, ordini, domande,
la seconda persona, markdown e simboli. Le parole sensibili («assistente», «telefono», «sito»…) solo
se ci sono nel terreno. Il significato non si controlla (principio 10): due numeri veri della pagina
legati male passano, e per questo chi ascolta sente che il libro resta la fonte.

Gli esiti sono **conti e motivi, mai testo**: il registro e il banco sul materiale vero non vedono le
parole delle pagine. Solo libreria standard.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import argomenti as A
from . import ascolta as S
from . import unita as U

# Una frase non è un riassunto se è più lunga di così (si capisce male a orecchio)
FRASE_PAROLE_MAX = 40
FRASE_MIN_CAR = 15

_PEDICI = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre")
_MESE_RE = "|".join(_MESI)

# ─────────────────────────── ciò che non si dice mai ───────────────────────────
# Un telefono: 7 cifre o più di fila, anche staccate da spazi, trattini o punti; un codice lungo
_TELEFONO_CIFRE = re.compile(r"(?<![\d,.])(?:\+\s?)?\d(?:[ .\-]?\d){6,}(?![\d])")
# Una via col numero («via Roma 12», «piazza Duomo, 3»): «la via Appia» resta
_VIA = re.compile(r"\b(?:via|viale|piazza|corso|vicolo|largo)\s+(?:[A-ZÀ-Ý][\w'’]*\s*){1,4},?\s*"
                  r"(?:n\.?\s*)?\d", re.I)
# Le parole che in un copione non hanno ragione di esserci se la pagina pulita non le ha
_SENSIBILI = frozenset("""assistente chatbot intelligenza istruzioni istruzione prompt sistema tool
telefono telefonare telefona cellulare whatsapp telegram email mail posta indirizzo indirizzi sito
siti link pagamento pagare quota quote bonifico password account scarica scaricare installa installare clicca
cliccare""".split())
# La seconda persona: chi ascolta non riceve ordini né consigli dal materiale, in nessun punto
_SECONDA = re.compile(r"\b(?:devi|dovete|puoi|potete|sai|sapete|vuoi|volete|hai|avete|tuo|tua|tuoi|"
                      r"tue|vostro|vostra|vostri|vostre|ricordati|ricordatevi|preparati)\b", re.I)
# L'imperativo in testa, oltre agli ordini a un assistente di `argomenti._ORDINE`
_IMPERATIVO = re.compile(
    r"^\W*(?:ricorda|ricordate|nota|notate|osserva|osservate|pensa|pensate|immagina|immaginate|"
    r"studia|studiate|ripassa|ripassate|leggi|leggete|guarda|guardate|ascolta|ascoltate|prova|"
    r"provate|impara|imparate|porta|portate|vai|andate|apri|aprite|fai|fate|controlla|controllate|"
    r"telefona|telefonate|contatta|contattate|scarica|scaricate|clicca|cliccate|visita|visitate|"
    r"attenzione|importante)(?!\w)", re.I)
# Una comunicazione della scuola o un discorso sul testo, senza le parole che riconosce il ripasso
# (banco del 04/11: «La scuola ricorda che le famiglie versano la quota…», «Il professore ha comunicato
# che lo studio di questo capitolo non è più necessario»): non è materia, e nemmeno terreno. Un soggetto
# della scuola con un verbo che comunica o chiede, o il riferimento a chi legge. «La scuola di Atene
# insegnava» e «Galileo fu professore a Padova» restano
_COMUNICAZIONE = re.compile(
    r"\b(?:professor\w*|prof|insegnant\w*|maestr[ae]|preside|segreteria|scuola|famiglie|genitori|"
    r"bidell\w*|rappresentant\w*)\b[^.;:]{0,40}?\b(?:ha comunicato|hanno comunicato|comunica|comunicano|"
    r"ha detto|hanno detto|dice che|dicono che|ricorda che|ricordano che|avvisa|avvisano|chiede di|"
    r"chiedono di|versa\w*|paga\w*|consegna\w*|devono|deve)\b|"
    r"\bnon (?:è|e') più (?:necessari\w|obbligatori\w|richiest\w)|"
    r"\b(?:il tool|i tool|chatbot|prompt)\b|\bda ora in poi\b|\brispondi\b[^.;:]{0,20}\b(?:solo|in \w+)\b|"
    r"\b(?:chi legge|chi ascolta|allo studente|agli studenti|alla studentessa|questo testo|"
    r"questa pagina|questo capitolo)\b", re.I)
_MARKUP = re.compile(r"[*#_`|\[\]{}<>~^\\]|->|=>|→|⟶|⇌|⇄|\bhttp", re.I)
_SIMBOLI = re.compile(r"[^\w\s.,;:!?'’\"«»“”()\-–—%°/+=²³ªº€$£¹]")
_PRIMO_ELENCO = re.compile(r"^\s*(?:[-•·▪◦]|\d{1,2}[.)]\s|[a-z][.)]\s)")

# ─────────────────────────── la prima parola ───────────────────────────
# Le parole con cui comincia una frase e che non sono un nome: se la prima parola non è qui, non è
# nelle pagine e non ha la forma di una parola comune, è trattata come un nome da cercare (un errore
# qui fa uscire una frase buona, mai entrare una cattiva)
_COMUNI = frozenset("""il lo la i gli le l un una uno del della dello dei degli delle al alla allo ai
agli alle dal dalla dallo dai dagli dalle nel nella nello nei negli nelle sul sulla sullo sui sugli
sulle col con per tra fra su di da in a e ed o ma però anche ancora poi quindi dunque infatti inoltre
invece mentre quando dove come perché perche se che chi cui ciò cio questo questa questi queste quel
quello quella quelli quelle quei quegli ogni ogn ciascun ciascuna ciascuno alcuni alcune altri altre
altro altra tutti tutte tutto tutta molti molte molto molta pochi poche poco poca tanti tante tanto
tanta più piu meno non né ne si ci vi sono è e' era erano fu furono ha hanno aveva avevano ebbe ebbero
essa esso essi esse egli ella loro lui lei prima dopo durante oggi ieri allora così cosi qui qua lì
li là la già gia sempre mai spesso talvolta infine alla fine secondo grazie entro senza sopra sotto
dentro fuori verso contro presso oltre circa nello stesso stessa stessi stesse nessun nessuna nessuno
qualche qualcuno diversi diverse vari varie varia vario entrambi entrambe due tre quattro cinque sei
sette otto nove dieci primo prima secondo seconda terzo terza ultimo ultima ultimi ultime nuovo nuova
nuovi nuove grande grandi piccolo piccola piccoli piccole esistono esiste esistevano esisteva serve
servono bisogna occorre possono può puo devono deve dobbiamo sappiamo vediamo parliamo abbiamo siamo
tale tali simile simili questa stessa ecco""".split())
_FORMA_COMUNE = re.compile(r"(?:mente|ando|endo|zione|zioni|sione|sioni|ità|ita|tore|tori|trice|"
                           r"mento|menti|ismo|ista|isti|ante|anti|ente|enti|ato|ata|ati|ate|uto|"
                           r"uta|uti|ute|ito|ita|iti|ite|oso|osa|osi|ose|ale|ali|ica|ico|ici|iche|"
                           r"ano|ono|are|ere|ire)$")


def _norma(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


# ─────────────────────────── i numeri ───────────────────────────
# «un», «una», «un'» e «uno» come articoli: tolti prima di leggere, così «un metro» o «in un secondo
# momento» non sono misure. «uno» resta un numero solo in fondo o con un'unità: lo legge chi segue
_ARTICOLO = re.compile(r"\b(?:un|una)\b['’]?\s*|\bun['’]", re.I)
_FRAZIONE = re.compile(r"\b(un|una|due|tre|quattro|cinque|sei|sette|otto|nove)\s+"
                       r"(mezz[oi]|terz[oi]|quart[oi]|quint[oi]|sest[oi]|settim[oi]|ottav[oi]|"
                       r"non[oi]|decim[oi])\b", re.I)
_DIVISORE = {"mezz": 2, "terz": 3, "quart": 4, "quint": 5, "sest": 6, "settim": 7, "ottav": 8,
             "non": 9, "decim": 10}
_CARDINALI = {"un": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
              "otto": 8, "nove": 9}
_FRAZIONE_CIFRE = re.compile(r"(?<![\d,./])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")
_MIGLIAIA_SPAZIO = re.compile(r"(?<![\d,.])(\d{1,3})((?: \d{3})+)(?![\d])")
_GRANDI = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mila|milion[ei]|miliard[oi])\b")
_GRANDI_UN = re.compile(r"\b(?:un|un[ao]?\s+)?(milione|miliardo)\b")
_MEZZO_GRANDE = re.compile(r"\bmezzo\s+(milione|miliardo)\b")
_FATTORE = {"mila": 1e3, "milion": 1e6, "miliard": 1e9}
_SEGNI = re.compile(r"(?<!\d)[.,;:!?]|[.,;:!?](?!\d)|[()«»“”\"]")


def _fattore(parola: str) -> float:
    return next(v for k, v in _FATTORE.items() if parola.startswith(k))


def _via_formule(testo: str) -> str:
    """Il testo senza le formule e le sigle con una cifra: le loro cifre non sono numeri («H2O», «CO2»
    hanno il loro controllo), e senza i pezzi cifra-lettera delle formule («2H2O»)."""
    def sost(m: re.Match) -> str:
        tok = m.group(1)
        return " " if any(c.isdigit() for c in tok) else m.group(0)
    t = str(testo or "").translate(_PEDICI)
    t = re.sub(r"(?<![\w,.])\d+(?=[A-Z][a-z]?\d*(?:[A-Z]|\b))(?![A-Z]?[a-z]+\b)", " ", t)
    return _FORMULA.sub(sost, t)


def _frazioni(testo: str) -> tuple[str, set]:
    """Le frazioni dette («tre quarti») e scritte («3/4»), fuori dal testo: i loro valori."""
    out = set()

    def detta(m: re.Match) -> str:
        n = _CARDINALI.get(m.group(1).lower())
        d = next(v for k, v in _DIVISORE.items() if m.group(2).lower().startswith(k))
        out.add(round(n / d, 6))
        return " "

    def scritta(m: re.Match) -> str:
        if int(m.group(2)):
            out.add(round(int(m.group(1)) / int(m.group(2)), 6))
        return m.group(0)
    t = _FRAZIONE_CIFRE.sub(scritta, _FRAZIONE.sub(detta, testo))
    return t, out


def _normale(testo: str) -> str:
    """Il testo per `unita.leggi`: senza formule, senza articoli, senza punteggiatura che non sta
    dentro un numero, con le migliaia staccate unite e i grandi numeri a cifre."""
    t = _via_formule(testo)
    t = _MIGLIAIA_SPAZIO.sub(lambda m: m.group(1) + m.group(2).replace(" ", ""), t)
    t = _SEGNI.sub(" ", t)
    # L'intervallo «1490-1510» non è un numero negativo
    t = re.sub(r"(\d)\s*[-–—]\s*(\d)", r"\1 \2", t)
    t = U._semplice(t)
    t = _MEZZO_GRANDE.sub(lambda m: str(int(0.5 * _fattore(m.group(1)))), t)
    t = _GRANDI_UN.sub(lambda m: str(int(_fattore(m.group(1)))), t)
    t = _ARTICOLO.sub(" ", t)
    t = U._in_cifre(" ".join(t.split()))
    t = _GRANDI.sub(lambda m: ("%f" % (float(m.group(1).replace(",", ".")) * _fattore(m.group(2)))
                               ).rstrip("0").rstrip(".").replace(".", ","), t)
    return t


def numeri(testo) -> list[tuple[float, str | None]]:
    """I numeri di una frase, ognuno con l'unità detta subito dopo."""
    t, _f = _frazioni(str(testo or ""))
    return U.leggi(_normale(t))


def _base(v: float, u: str | None) -> tuple:
    """(grandezza, valore nell'unità di base) di una misura, per confrontare «mille metri» e «1 km»."""
    g, f = U.UNITA[u]
    return g, round(v * f, 9)


def _date(testo: str) -> set:
    """Le coppie (giorno, mese) di un testo: «12 ottobre», «il dodici di ottobre», «primo maggio»,
    «1° maggio» e, solo nelle pagine, «12/10/1492»."""
    t = U._in_cifre(" ".join(U._semplice(_SEGNI.sub(" ", str(testo or ""))).split()))
    out = set()
    for m in re.finditer(rf"\b(\d{{1,2}}|primo)°?\s+(?:di\s+)?({_MESE_RE})\b", t):
        out.add((1 if m.group(1) == "primo" else int(m.group(1)), m.group(2)))
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})/\d{2,4}(?![\d/])", str(testo or "")):
        if 1 <= int(m.group(2)) <= 12:
            out.add((int(m.group(1)), _MESI[int(m.group(2)) - 1]))
    return out


def _mesi(testo: str) -> set:
    t = _norma(testo)
    return {m for m in _MESI if re.search(rf"\b{m}\b", t)}


# ─────────────────────────── gli ordinali ───────────────────────────
def _tabella_ordinali() -> dict:
    from ..pronuncia import ordinale
    out = {}
    for n in range(1, 101):
        o = ordinale(n)
        for finale in ("o", "a", "i", "e"):
            out[o[:-1] + finale] = n
    return out


_ORDINALI: dict = {}
_DIECI_PRIMI = ("primo", "second", "terz", "quart", "quint", "sest", "settim", "ottav", "non",
                "decim")


def _ordinali(testo: str) -> set:
    """I valori degli ordinali che affermano qualcosa: quelli in «-esimo» dovunque, i primi dieci solo
    davanti a «secolo» o «millennio» e dopo un nome con la maiuscola; i romani passano da
    `pronuncia.romani_detti` e diventano queste parole."""
    from ..pronuncia import romani_detti
    if not _ORDINALI:
        _ORDINALI.update(_tabella_ordinali())
    t = romani_detti(str(testo or ""))
    out = set()
    for m in re.finditer(r"\b([A-Za-zÀ-ÿ']+)\b", t):
        w = _norma(m.group(1))
        n = _ORDINALI.get(w)
        if n is None:
            continue
        if n > 10:
            out.add(n)
            continue
        prima = t[:m.start()].rstrip()
        dopo = t[m.end():].lstrip()
        # «Carlo quinto» sì; «Colombo prima di», «Colombo secondo le fonti» no
        nome = (re.search(r"[A-ZÀ-Ý][a-zà-ÿ]+$", prima) and w.endswith("o")
                and w not in ("primo", "secondo") and not re.match(r"di\b", dopo))
        if re.match(r"(?:secolo|secoli|sec\.|millennio)", dopo, re.I) or nome:
            out.add(n)
    return out


# ─────────────────────────── formule, sigle, lettere dette, nomi ───────────────────────────
_FORMULA = re.compile(r"(?<![\w])((?:[A-Z][a-z]?\d*){1,8})(?![\w])")
_MAIUSCOLA = re.compile(r"(?<![\w])([A-ZÀ-Ý][a-zà-ÿ]{2,})(?![\w])")
_SIGLA_MAIUSCOLA = re.compile(r"(?<![\w.])([A-Z]{2,6})(?![\w.])")
# I nomi delle lettere che non sono parole: una loro fila è una formula o una sigla detta
_LETTERE_SOLE = "acca|effe|elle|emme|enne|erre|zeta|ics|vu|bi|cu|gi|kappa"
_LETTERE_TUTTE = _LETTERE_SOLE + "|a|ci|di|e|esse|i|o|pi|ti|u"
_NUMERI_PICCOLI = "uno|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|dodici"
_FILA_LETTERE = re.compile(
    rf"\b(?:{_LETTERE_SOLE}|ci\s+o)(?:\s+(?:{_LETTERE_TUTTE}|{_NUMERI_PICCOLI}))*\b", re.I)
_PICCOLE_DOPO = frozenset("a ci di e esse i o pi ti u".split())
_DIGIT_WORD_RUN = 5


def _fila_c_e(fila: str, detto: str) -> bool:
    """La fila di lettere dette è nella forma detta delle pagine; le parole piccole in fondo possono
    essere della frase («acca due o e un gas»), non della formula."""
    w = fila.split()
    while w:
        if " ".join(w) in detto:
            return True
        if w[-1] not in _PICCOLE_DOPO:
            return False
        w.pop()
    return False


def _formule(testo: str) -> set:
    from ..pronuncia import _formula_detta
    t = str(testo or "").translate(_PEDICI)
    return {m.group(1) for m in _FORMULA.finditer(t) if _formula_detta(m.group(1)) is not None}


def _sigle(testo: str) -> set:
    return {m.group(1) for m in _SIGLA_MAIUSCOLA.finditer(str(testo or ""))
            if m.group(1) not in _formule(testo)}


def _nomi(frase: str) -> tuple[set, str | None]:
    """(le parole con la maiuscola dentro la frase, la prima parola se sembra un nome): normalizzate.
    Un'elisione in testa («L'Europa») lascia alla parola dopo il suo controllo."""
    t = str(frase or "").strip()
    primo = re.match(r"\W*([A-ZÀ-Ý][a-zà-ÿ]+)(?![\w'’])", t)
    dentro = set()
    for m in _MAIUSCOLA.finditer(t):
        if primo is not None and m.start(1) == primo.start(1):
            continue
        dentro.add(_norma(m.group(1)))
    inizio = None
    if primo is not None:
        w = _norma(primo.group(1))
        if w not in _COMUNI and U.parola_numero(w) is None and not _FORMA_COMUNE.search(w):
            inizio = w
    return dentro, inizio


def _parole_tutte(testo: str) -> set:
    return set(re.findall(r"[a-z]+", _norma(testo)))


# ─────────────────────────── il terreno ───────────────────────────
def frasi_pulite(testo, nomi=()) -> list[str]:
    """Le frasi di una pagina che possono fare da terreno: quelle che il ripasso direbbe anche su una
    pagina con le istruzioni, senza indirizzi, senza telefoni, senza ordini in testa (anche quelli
    che non si rivolgono a un assistente: «Porta 20 euro alla bidella.»)."""
    out = []
    for p in S.paragrafi(testo):
        for f in S.frasi(p):
            if S.scarto(f, nomi, True) is None and not _vietata(f) and not _IMPERATIVO.search(f):
                out.append(f)
    return out


def _e_telefono(cifre: str) -> bool:
    """Una fila di cifre è un telefono, non due anni («1519-1521», banco del 04/11: gli appunti su quegli
    anni uscivano tutti dal terreno) né un numero con le migliaia («1.500.000»)."""
    gruppi = re.findall(r"\d+", cifre)
    if all(len(g) == 4 and 1000 <= int(g) <= 2100 for g in gruppi):
        return False
    return not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cifre.strip())


def _vietata(frase: str) -> str | None:
    """Ciò che non si dice mai, nemmeno se sta nella pagina. Il motivo o None."""
    if any(_e_telefono(m.group(0)) for m in _TELEFONO_CIFRE.finditer(frase)):
        return "telefono"
    # Una fila di cifre dette: «tre tre tre uno due tre quattro»
    run = 0
    for w in _parole_tutte_ordine(frase):
        if w in _CIFRE_DETTE:
            run += 1
            if run >= _DIGIT_WORD_RUN:
                return "telefono"
        else:
            run = 0
    if _VIA.search(frase):
        return "indirizzo"
    if _COMUNICAZIONE.search(frase):
        return "comunicazione"
    return None


_CIFRE_DETTE = frozenset("zero uno due tre quattro cinque sei sette otto nove".split())


def _parole_tutte_ordine(testo: str) -> list[str]:
    return re.findall(r"[a-z]+", _norma(testo))


@dataclass
class Terreno:
    """Ciò che si può cercare: i testi puliti per riferimento e i valori di tutte le pagine pulite."""
    testi: dict = field(default_factory=dict)           # «P1» → il testo pulito
    nudi: set = field(default_factory=set)              # i valori senza unità, e tutti i valori
    misure: set = field(default_factory=set)            # (grandezza, valore in base)
    frazioni: set = field(default_factory=set)
    date: set = field(default_factory=set)
    mesi: set = field(default_factory=set)
    ordinali: set = field(default_factory=set)
    formule: set = field(default_factory=set)
    sigle: set = field(default_factory=set)
    parole: set = field(default_factory=set)
    radici: set = field(default_factory=set)
    detto: str = ""                                     # la forma detta, per le lettere

    def valore_c_e(self, v: float, u: str | None) -> bool:
        if u is None:
            return round(v, 9) in self.nudi or round(v, 6) in self.frazioni
        return _base(v, u) in self.misure or round(v, 9) in self.nudi_senza_unita

    nudi_senza_unita: set = field(default_factory=set)


def terreno(pagine: dict, istruzioni=(), nomi=()) -> Terreno:
    """Il terreno da {riferimento: testo letto}; le pagine in `istruzioni` non contano."""
    from ..pronuncia import per_ripasso
    from ..provenienza import parole as P_parole
    T = Terreno()
    tutte: list[str] = []
    for r, testo in pagine.items():
        if r in istruzioni:
            continue
        ff = frasi_pulite(testo, nomi)
        if ff:
            T.testi[r] = " ".join(ff)
            tutte += ff
    detti = []
    for f in tutte:
        d = per_ripasso(f)
        detti.append(d)
        for x in (f, d):
            t, fr = _frazioni(x)
            T.frazioni |= fr
            for v, u in U.leggi(_normale(t)):
                T.nudi.add(round(v, 9))
                if u is None:
                    T.nudi_senza_unita.add(round(v, 9))
                else:
                    T.misure.add(_base(v, u))
            # Anche i numeri scritti fuori dai confini di `_normale`: «12 000» vale 12000, e 12 e 0
            for v, _u in U.leggi(" ".join(_SEGNI.sub(" ", _via_formule(x)).split())):
                T.nudi.add(round(v, 9))
            T.date |= _date(x)
            T.mesi |= _mesi(x)
            T.ordinali |= _ordinali(x)
        T.nudi |= {round(float(n), 9) for n in T.ordinali}
        T.formule |= _formule(f)
        T.sigle |= _sigle(f)
        T.parole |= _parole_tutte(f) | _parole_tutte(d)
    T.radici = {w[:A.RADICE] for w in T.parole if len(w) >= A.RADICE}
    T.detto = " ".join(_norma(d) for d in detti)
    return T


def _nome_c_e(w: str, T: Terreno) -> bool:
    from ..provenienza import vicina
    return w in T.parole or (len(w) >= A.RADICE and w[:A.RADICE] in T.radici) or vicina(w, T.parole)


# ─────────────────────────── una frase ───────────────────────────
def forma(frase: str, nomi=()) -> str | None:
    """Il motivo per cui la frase non si può dire, a prescindere dalle pagine; None se la forma va."""
    f = str(frase or "").strip()
    if len(f) < FRASE_MIN_CAR or len(f.split()) > FRASE_PAROLE_MAX:
        return "lunghezza"
    # Prima ciò che dice la frase, poi come è scritta: i conti delle voci ostili devono essere giusti
    motivo = S.scarto(f, nomi, True) or _vietata(f)
    if motivo is not None:
        return motivo
    if _PRIMO_ELENCO.match(f) or _MARKUP.search(f) or _SIMBOLI.search(f):
        return "forma"
    if not f.endswith(".") or f.endswith("..."):
        return "domanda" if f.endswith("?") else "forma"
    if _IMPERATIVO.search(f) or _SECONDA.search(f):
        return "seconda_persona"
    return None


def valori_mancanti(frase: str, T: Terreno) -> list[str]:
    """I tipi dei valori della frase che nelle pagine pulite non ci sono (una voce per valore)."""
    out: list[str] = []
    t, fr = _frazioni(frase)
    for x in fr:
        if x not in T.frazioni and x not in T.nudi:
            out.append("numero")
    for v, u in U.leggi(_normale(t)):
        if u is None and abs(v) == 1:
            continue                       # «uno dei», «uno a uno»: non afferma una quantità
        if not T.valore_c_e(v, u):
            out.append("numero")
    for d in _date(frase):
        if d not in T.date:
            out.append("data")
    for m in _mesi(frase):
        if m not in T.mesi:
            out.append("data")
    for n in _ordinali(frase):
        if n not in T.ordinali and float(n) not in T.nudi:
            out.append("numero")
    for x in _formule(frase):
        if x not in T.formule:
            out.append("formula")
    for x in _sigle(frase):
        if x not in T.sigle:
            out.append("sigla")
    nf = _norma(frase)
    for m in _FILA_LETTERE.finditer(nf):
        if not _fila_c_e(m.group(0), T.detto):
            out.append("formula")
    dentro, inizio = _nomi(frase)
    for w in sorted(dentro):
        if not _nome_c_e(w, T):
            out.append("nome")
    if inizio is not None and not _nome_c_e(inizio, T):
        out.append("nome")
    for w in _parole_tutte(frase) & _SENSIBILI:
        if w not in T.parole:
            out.append("sensibile")
    return out


def fondata(frase: str, citate, T: Terreno) -> bool:
    """Le parole della frase stanno nelle pagine citate e pulite (`argomenti.controlla`: la metà, con
    le formule di fila). I numeri in lettere non contano come parole: hanno il loro controllo."""
    validi = [A._rif(c) for c in citate or () if A._rif(c) in T.testi]
    if not validi:
        return False
    def e_valore(w: str) -> bool:
        x = _norma(w).strip(".,;:'’")
        return U.parola_numero(x) is not None or x in _PAROLE_DI_MISURA or x in _MESI
    senza = " ".join(w for w in re.split(r"\s+", frase) if not e_valore(w))
    _es, dentro = A.controlla(senza, validi, T.testi)
    return bool(dentro)


# I nomi delle unità e «virgola»: le pagine scrivono «g/cm³», il copione «grammi al centimetro cubo»
_PAROLE_DI_MISURA = frozenset(["virgola", "mezzo", "mezza", "milione", "milioni", "miliardo", "miliardi",
                               "mila"]) | frozenset(
    p for nome, _c, simbolo in U._VOCI if not simbolo for p in nome.split(" ") if len(p) >= 4)


def controlla(frase: str, citate, T: Terreno, nomi=()) -> dict:
    """{"ok": bool, "motivi": [...]}: i motivi sono solo nomi, mai testo. L'ordine conta per i conti:
    prima la forma, poi le pagine e i valori, tutti."""
    m = forma(frase, nomi)
    if m is not None:
        return {"ok": False, "motivi": [m]}
    motivi = valori_mancanti(frase, T)
    if not fondata(frase, citate, T):
        motivi.append("fuori_dalle_pagine")
    return {"ok": not motivi, "motivi": motivi}
