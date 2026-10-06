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


def _plurale_di_fila(text: str, start: int, end: int) -> bool:
    return bool(_FILA_PRIMA.search(text[max(0, start - 24):start])
                or _FILA_DOPO.match(text[end:end + 40]))


class Pronuncia:
    """Il lessico compilato in una sola espressione regolare (~7 µs a frase).
    `extra` (da `Config.tts_pronuncia_extra`) aggiunge o sostituisce voci: il valore è la
    grafia all'italiana («pòdcast») oppure i fonemi di espeak tra doppie quadre
    («[[pˈɔdkast]]»); un valore vuoto toglie una voce predefinita."""

    def __init__(self, extra: dict[str, str] | None = None, attiva: bool = True):
        self.attiva = attiva
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
        if not self.attiva or self._re is None or not text:
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
