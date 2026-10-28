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


def supporta_fonemi(voice) -> bool:
    """True se la voce di Piper accetta i fonemi tra `[[ ]]` (piper-tts ≥ 1.3)."""
    return not hasattr(voice, "synthesize_stream_raw") and hasattr(voice, "phonemize")
