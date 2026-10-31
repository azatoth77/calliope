"""
Pronuncia degli inglesismi nella voce di Calliope (04/10/2026).

Piper legge il testo con espeak-ng italiano: «file» diventava «fìle» anche parlando dei file
del computer, «email» «èmail», «wifi» «uìfi», «backup» «bekàp». Il dizionario italiano di
espeak conosce già molti inglesismi (computer, mouse, timer, weekend, download, Wi-Fi con il
trattino…): qui ci sono solo le parole che sbaglia, misurate con `prove/misura_pronuncia.py`.

Come: la parola si riscrive all'italiana («fàil», «imèil», «uàifài») e espeak la legge
dentro la frase. piper-tts ≥ 1.3 accetterebbe anche i fonemi IPA tra `[[ ]]` per una parola
sola (`PiperVoice.phonemize` divide il testo sui blocchi e manda il resto a espeak), ma
misurato è peggio: ogni pezzo va a espeak da solo, quindi la parola prima del blocco diventa
la fine di una frase e prende l'accento («Il file» → «ˈiːl fˈaɪl», «su Zoom» → «sˈu»,
Whisper sente «i backup», «oreggi») e la punteggiatura subito dopo il blocco si perde (il
punto finale, la virgola: «OneDrive, in Windows.» suonava come una domanda). La grafia
all'italiana dà a espeak gli stessi fonemi (la prova lo controlla) senza questi difetti. I
blocchi `[[ ]]` restano possibili per le voci aggiunte dall'utente, quando nessuna grafia
basta: la punteggiatura che segue entra nel blocco.

Vale solo per il testo che va al sintetizzatore (`tts.Speaker`): la storia del modello, il
registro dei turni e gli schermi vedono il testo com'è. La sintesi è sul server anche con i
satelliti e il telefono, quindi la correzione vale anche lì.

**Unità di misura** (12/10; fino al 28/10 in `calliope/unita.py`, degli esercizi tolti con la
#279): espeak legge i simboli lettera per lettera
(«3 kg» → «tre kappagì», «2,5 m/s» → «… emme barra esse», «m/s²» → «… esse due», «°C» →
«gradi ci»). Un simbolo **subito dopo un numero** («36 km/h», «9,8 m/s²», «1 kg») diventa il
nome per esteso, accordato al numero («1 chilogrammo», «2,5 metri al secondo»):
`SIMBOLI_DETTI`, solo simboli che dopo una cifra non possono voler dire altro (niente
«h», «s», «G» delle reti come «5G»); senza un numero davanti nulla cambia. «joule» lo legge
«giòule»: nel lessico come «giùl».

È una conversione di forma (principio 10): non cambia il significato e riguarda solo il suono.
L'unico caso ambiguo è «file», che in italiano è anche il plurale di «fila»: resta «fìle»
dopo un articolo o un aggettivo femminile («le file di sedie», «nelle prime file») e prima
di un aggettivo femminile o di «di sedie», «di persone»… («in file ordinate»). Calliope
dice quasi sempre «il file», «i file», «un file», «del file», «tipo di file»: in quei casi
(e in ogni altro) è «fàil».
"""
from __future__ import annotations

import re

# parola (minuscola; varianti separate da «|») → grafia all'italiana. `FONEMI_ATTESI` in
# prove/prova_pronuncia.py dice cosa ne fa espeak (fˈaɪl, imˈɛjl, wˈaɪfˈaɪ…): se cambia
# espeak, la prova lo vede.
LESSICO: dict[str, str] = {
    "file": "fàil",
    "files": "fàils",
    "email|e-mail": "imèil",
    "emails|e-mails": "imèils",
    "wifi|wi-fi": "uàifài",
    "backup|back-up": "bèkap",
    "screenshot": "scrìnsciot",
    "playlist": "plèilist",
    "meeting": "mìting",
    "cookie|cookies": "cùki",
    "notebook": "nòtbuk",
    "outlook": "àutluk",
    "windows": "uìndous",
    "powerpoint": "pàuerpoint",
    "onedrive": "uandràiv",
    "chrome": "kròm",
    "headset": "èdset",
    "raspberry": "rèsberri",
    "whisper": "uìsper",
    "piper": "pàiper",
    "docker": "dòker",
    "wikiquote": "uikikuòt",
    "duckdns": "dàk di ènne èsse",
    "joule": "giùl",
}

# «file» = plurale di «fila»: articoli, preposizioni articolate e aggettivi femminili prima,
# aggettivi e participi femminili dopo
_FILA_PRIMA = re.compile(
    r"(?:\b(?:le|delle|dalle|nelle|alle|sulle|colle|tra le|fra le|per le|queste|quelle|"
    r"tante|poche|molte|alcune|diverse|varie|prime|ultime|lunghe|interminabili)\s+)$", re.I)
_FILA_DOPO = re.compile(
    r"^\s+(?:ordinate|serrate|indiane|parallele|lunghe|intere|compatte|disposte|allineate|"
    r"schierate|di (?:sedie|persone|banchi|alberi|auto|macchine|gente|soldati|case|"
    r"poltrone|posti|piante|viti|mattoni))\b", re.I)

_PARENTESI = re.compile(r"\[\[|\]\]")

# Simbolo scritto dopo un numero → parole (singolare, plurale). Solo simboli che in una frase
# dopo una cifra non possono voler dire altro: niente «h», «s», «t», «u» da soli (ore e secondi
# si scrivono per esteso), niente «G» maiuscola («5G», «3G» delle reti) e niente «K». Dal
# 12/10 al 28/10 stava in `calliope/unita.py`, con le misure degli esercizi (tolti, #279).
SIMBOLI_DETTI: dict[str, tuple[str, str]] = {
    "km/h": ("chilometro all'ora", "chilometri all'ora"),
    "m/s²": ("metro al secondo quadrato", "metri al secondo quadrato"),
    "m/s2": ("metro al secondo quadrato", "metri al secondo quadrato"),
    "m/s": ("metro al secondo", "metri al secondo"),
    "km/s": ("chilometro al secondo", "chilometri al secondo"),
    "g/cm³": ("grammo al centimetro cubo", "grammi al centimetro cubo"),
    "g/cm3": ("grammo al centimetro cubo", "grammi al centimetro cubo"),
    "kg/m³": ("chilogrammo al metro cubo", "chilogrammi al metro cubo"),
    "kg/m3": ("chilogrammo al metro cubo", "chilogrammi al metro cubo"),
    "g/mol": ("grammo per mole", "grammi per mole"),
    "mol/L": ("mole al litro", "moli al litro"),
    "mol/l": ("mole al litro", "moli al litro"),
    "N/kg": ("newton al chilogrammo", "newton al chilogrammo"),
    "g/L": ("grammo al litro", "grammi al litro"),
    "m²": ("metro quadrato", "metri quadrati"),
    "m³": ("metro cubo", "metri cubi"),
    "cm²": ("centimetro quadrato", "centimetri quadrati"),
    "cm³": ("centimetro cubo", "centimetri cubi"),
    "km²": ("chilometro quadrato", "chilometri quadrati"),
    "kWh": ("chilowattora", "chilowattora"),
    "kW": ("chilowatt", "chilowatt"),
    "kJ": ("chilojoule", "chilojoule"),
    "kg": ("chilogrammo", "chilogrammi"),
    "mg": ("milligrammo", "milligrammi"),
    "km": ("chilometro", "chilometri"),
    "cm": ("centimetro", "centimetri"),
    "mm": ("millimetro", "millimetri"),
    "ml": ("millilitro", "millilitri"),
    "mL": ("millilitro", "millilitri"),
    "mol": ("mole", "moli"),
    "°C": ("grado", "gradi"),
    "g": ("grammo", "grammi"),
    "m": ("metro", "metri"),
    "N": ("newton", "newton"),
    "J": ("joule", "joule"),
    "W": ("watt", "watt"),
    "Pa": ("pascal", "pascal"),
    "Hz": ("hertz", "hertz"),
}


def _regex_simboli() -> re.Pattern:
    alternative = "|".join(re.escape(k) for k in sorted(SIMBOLI_DETTI, key=len, reverse=True))
    # Un numero (con la virgola o il punto decimale), uno spazio al più, il simbolo intero
    return re.compile(rf"(?<![\w.,])(\d+(?:[.,]\d+)?)\s?({alternative})(?![\w/²³])")


_SIMBOLI = _regex_simboli()


def unita_dette(text: str) -> str:
    """«36 km/h» → «36 chilometri all'ora», «1 kg» → «1 chilogrammo», «9,8 m/s²» → «9,8 metri
    al secondo quadrato». Solo dopo un numero; il resto del testo non cambia."""

    def sostituisci(m: re.Match) -> str:
        singolare, plurale = SIMBOLI_DETTI[m.group(2)]
        return f"{m.group(1)} {singolare if m.group(1) == '1' else plurale}"
    return _SIMBOLI.sub(sostituisci, text)


def _plurale_di_fila(text: str, start: int, end: int) -> bool:
    return bool(_FILA_PRIMA.search(text[max(0, start - 24):start])
                or _FILA_DOPO.match(text[end:end + 40]))


class Pronuncia:
    """Il lessico compilato in una sola espressione regolare (~7 µs a frase).
    `extra` (da `Config.tts_pronuncia_extra`) aggiunge o sostituisce voci: il valore è la
    grafia all'italiana («pòdcast») oppure i fonemi di espeak tra doppie quadre
    («[[pˈɔdkast]]»); un valore vuoto toglie una voce predefinita."""

    def __init__(self, extra: dict[str, str] | None = None, attiva: bool = True,
                 unita: bool = True):
        self.attiva = attiva
        self.unita = unita
        voci: dict[str, str] = {}
        for chiavi, grafia in LESSICO.items():
            for k in chiavi.split("|"):
                voci[k.lower()] = grafia
        for k, v in (extra or {}).items():
            k = str(k).strip().lower()
            v = str(v or "").strip()
            if not k:
                continue
            if v:
                voci[k] = v
            else:
                voci.pop(k, None)
        self.voci = voci
        if voci:
            alternative = "|".join(re.escape(k) for k in sorted(voci, key=len, reverse=True))
            # Mai a metà parola («profile», «filet», «emailing»), anche con il trattino;
            # l'apostrofo prima va bene («l'email», «un'email»). La punteggiatura subito
            # dopo serve ai blocchi di fonemi
            self._re = re.compile(rf"(?<![\w-])({alternative})(?![\w-])([.,;:!?…]*)", re.I)
        else:
            self._re = None

    def applica(self, text: str, fonemi: bool = True) -> str:
        """Il testo da dare a Piper. `fonemi` False (Piper < 1.3, senza blocchi `[[ ]]`):
        le voci con i fonemi restano come sono scritte."""
        if not self.attiva or not text:
            return text
        if self.unita:
            text = unita_dette(text)
        if self._re is None:
            return text
        text = _PARENTESI.sub("", text)

        def sostituisci(m: re.Match) -> str:
            parola, punti = m.group(1), m.group(2)
            if parola.lower() == "file" and _plurale_di_fila(m.string, m.start(), m.end(1)):
                return m.group()
            nuova = self.voci[parola.lower()]
            if nuova.startswith("[[") and nuova.endswith("]]"):
                if not fonemi:
                    return m.group()
                # Dentro il blocco anche la punteggiatura: dopo un blocco espeak la perde
                return f"[[{nuova[2:-2].strip()}{punti}]]"
            if parola[:1].isupper():
                nuova = nuova[:1].upper() + nuova[1:]
            return nuova + punti

        return self._re.sub(sostituisci, text)


# ─────────────────── formule, sigle e simboli del ripasso (31/10, #249) ───────────────────
# Il ripasso da ascoltare dello Studio (calliope/studio/ascolta.py) legge le pagine dei libri:
# formule chimiche, simboli matematici, sigle e numeri romani che espeak legge male («CO₂»,
# «DNA» come una parola, «XV secolo» lettera per lettera). Queste conversioni valgono **solo**
# per il testo del ripasso (`per_ripasso`): la voce dal vivo non cambia. Come le unità, sono
# conversioni di forma (principio 10): non cambiano il significato, solo il suono.

LETTERE = {"a": "a", "b": "bi", "c": "ci", "d": "di", "e": "e", "f": "effe", "g": "gi",
           "h": "acca", "i": "i", "j": "i lunga", "k": "cappa", "l": "elle", "m": "emme",
           "n": "enne", "o": "o", "p": "pi", "q": "cu", "r": "erre", "s": "esse", "t": "ti",
           "u": "u", "v": "vu", "w": "doppia vu", "x": "ics", "y": "ipsilon", "z": "zeta"}
# I simboli degli elementi: una formula è fatta solo di questi (con i numeri)
ELEMENTI = frozenset("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni
Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm
Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu
Am Cm Bk Cf Es Fm Md No Lr""".split())
_PEDICI = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_FORMULA = re.compile(r"(?<![\w])((?:[A-Z][a-z]?\d*){1,8})(?![\w])")
_PEZZO_FORMULA = re.compile(r"([A-Z][a-z]?)(\d*)")
_ROMANO = re.compile(r"^M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")
_ROMANO_SECOLO = re.compile(r"\b([IVXLCDM]{1,8})(\s+(?:secolo|sec\.|millennio))")
_ROMANO_NOME = re.compile(r"\b([A-Z][a-zà-ù]+) ([IVX]{1,6})\b")
_SIGLA = re.compile(r"(?<![\w.])([A-Z]{2,5})(?![\w.])")
_ATTACCO = r"(?:[BCDFGPTV][LR]|S[BCDFGLMNPRTV]|GN|CH|GH|[BCDFGLMNPRSTVZ])"
_PRONUNCIABILE = re.compile(rf"^(?:{_ATTACCO}?[AEIOU]+(?:[LMNRS](?=[BCDFGLMNPRSTVZ]))?)+"
                            r"[BCDFGLMNPRSTVZ]?$")
_ORDINALI = ("primo", "secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo",
             "nono", "decimo")


def _romano(s: str) -> int | None:
    if not s or not _ROMANO.match(s):
        return None
    val = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    n = 0
    for i, c in enumerate(s):
        v = val[c]
        n += -v if i + 1 < len(s) and val[s[i + 1]] > v else v
    return n or None


def ordinale(n: int) -> str:
    """1 → «primo», 15 → «quindicesimo», 23 → «ventitreesimo» (maschile)."""
    from .numeri import in_lettere
    if 1 <= n <= 10:
        return _ORDINALI[n - 1]
    p = in_lettere(n)
    return p + "esimo" if p.endswith(("tre", "sei")) else p[:-1] + "esimo"


def _formula_detta(tok: str) -> str | None:
    """«CO2» → «ci o due», «NaCl» → «enne a ci elle»; None se non è una formula: solo simboli di
    elementi, con almeno un numero o un simbolo di due lettere («PC», «USA», «CO» sono sigle)."""
    pezzi = _PEZZO_FORMULA.findall(tok)
    if "".join(a + b for a, b in pezzi) != tok or any(a not in ELEMENTI for a, _ in pezzi):
        return None
    if not any(b for _a, b in pezzi) and not (len(pezzi) >= 2
                                              and any(len(a) == 2 for a, _ in pezzi)):
        return None
    from .numeri import in_lettere
    parole = []
    for a, b in pezzi:
        parole.append(" ".join(LETTERE[c.lower()] for c in a))
        if b:
            parole.append(in_lettere(int(b)) if len(b) <= 3 else b)
    return " ".join(parole)


def formule_dette(testo: str) -> str:
    """Le formule chimiche lettera per lettera all'italiana, coi pedici e le cariche."""
    t = testo.translate(_PEDICI).replace("⁺", " più").replace("⁻", " meno")

    def sost(m: re.Match) -> str:
        d = _formula_detta(m.group(1))
        return d if d is not None else m.group(0)
    return _FORMULA.sub(sost, t)


def romani_detti(testo: str) -> str:
    """«XV secolo» → «quindicesimo secolo», «Luigi XIV» → «Luigi quattordicesimo»: solo davanti
    a «secolo» e «millennio», o dopo un nome con la maiuscola (I, V e X soli: «vitamina C» resta)."""
    def secolo(m: re.Match) -> str:
        n = _romano(m.group(1))
        return ordinale(n) + m.group(2) if n and n <= 40 else m.group(0)

    def nome(m: re.Match) -> str:
        n = _romano(m.group(2))
        return f"{m.group(1)} {ordinale(n)}" if n and n <= 39 else m.group(0)
    return _ROMANO_NOME.sub(nome, _ROMANO_SECOLO.sub(secolo, testo))


def sigle_dette(testo: str) -> str:
    """Una sigla in maiuscole che non si legge come una parola si compita («DNA» → «di enne a»,
    «TV» → «ti vu»); quelle che si leggono restano («ONU», «USA», «ISTAT»)."""
    def sost(m: re.Match) -> str:
        s = m.group(1)
        if _PRONUNCIABILE.match(s):
            return s
        return " ".join(LETTERE[c.lower()] for c in s)
    return _SIGLA.sub(sost, testo)


_SIMBOLI_MAT = [
    (re.compile(r"√\s*"), "radice di "),
    (re.compile(r"\s*π\s*"), " pi greco "),
    (re.compile(r"(?<=[\w)])\s*²"), " al quadrato"),
    (re.compile(r"(?<=[\w)])\s*³"), " al cubo"),
    (re.compile(r"(?<=[\w)])\^\s*2\b"), " al quadrato"),
    (re.compile(r"(?<=[\w)])\^\s*3\b"), " al cubo"),
    (re.compile(r"(?<=[\w)])\^\s*(\w+)"), r" alla \1"),
    (re.compile(r"\s*≤\s*"), " minore o uguale a "),
    (re.compile(r"\s*≥\s*"), " maggiore o uguale a "),
    (re.compile(r"\s*≠\s*"), " diverso da "),
    (re.compile(r"\s*≈\s*"), " circa uguale a "),
    (re.compile(r"\s*[→⟶]\s*"), " dà "),
    (re.compile(r"\s*=\s*"), " uguale "),
    (re.compile(r"\s+<\s+"), " minore di "),
    (re.compile(r"\s+>\s+"), " maggiore di "),
    (re.compile(r"\s*\+\s*"), " più "),
    (re.compile(r"\s*−\s*"), " meno "),
    (re.compile(r"(?<=\d)\s+-\s+(?=\d)"), " meno "),
    (re.compile(r"\s+[-–—]\s+"), ", "),
    (re.compile(r"(?<=[\w)])\s*[×·]\s*(?=[\w(])"), " per "),
    (re.compile(r"(?<=\d)\s+x\s+(?=\d)"), " per "),
    (re.compile(r"\s*÷\s*"), " diviso "),
    (re.compile(r"(?<=\d)\s+:\s+(?=\d)"), " diviso "),
    (re.compile(r"(?<![\d/])(\d+)/(\d+)(?![\d/])"), r"\1 fratto \2"),
    (re.compile(r"(?<=\d)\s*%"), " per cento"),
    (re.compile(r"(?<=\d)\s*°(?![CF])"), " gradi"),
]


def simboli_detti(testo: str) -> str:
    """I simboli matematici a parole, solo fra due termini o dopo un numero: «a² + b² = c²» →
    «a al quadrato più b al quadrato uguale c al quadrato»; «5 - 3» → «5 meno 3», ma il trattino
    fra due parole («Capitolo 7 - Le scoperte») è una pausa."""
    t = testo
    for rx, a in _SIMBOLI_MAT:
        t = rx.sub(a, t)
    return t


def per_ripasso(testo: str) -> str:
    """Il testo di una pagina pronto per Piper nel ripasso da ascoltare (31/10, #249): le unità
    dopo un numero (prima dei simboli, così «m²» resta «metri quadrati»), i numeri romani, le
    formule, le sigle e i simboli. I blocchi di fonemi `[[ ]]` non passano mai: un materiale non
    sceglie i fonemi di Piper."""
    t = _PARENTESI.sub(" ", str(testo or ""))
    t = unita_dette(t)
    t = romani_detti(t)
    t = formule_dette(t)
    t = sigle_dette(t)
    t = simboli_detti(t)
    return " ".join(t.split())


def supporta_fonemi(voice) -> bool:
    """True se la voce di Piper accetta i fonemi tra `[[ ]]` (piper-tts ≥ 1.3)."""
    return not hasattr(voice, "synthesize_stream_raw") and hasattr(voice, "phonemize")
