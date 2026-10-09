"""
Le frasi che Whisper «allucina» su rumore o silenzio (09/10/2026, regola
`allucinazione_whisper`).

Whisper è addestrato anche sui sottotitoli dei video: su un rumore breve, o sul silenzio dopo
una frase, scrive le righe che chiudono i sottotitoli («Sottotitoli creati dalla comunità
Amara.org», «Grazie per la visione», «Iscriviti al canale») o un indirizzo di siti visti nei
titoli di coda. Caso vero della DGX: «e con il nostro corso gratuito www.mesmerism.info.it»,
identica l'08/10 alle 17:03 e il 09/10 alle 20:41, su 1,7 s di rumore nella finestra
d'ascolto, presa per una frase di chi amministra e mandata al modello con un'azione in
sospeso. Le liste note (le discussioni di openai/whisper sulle allucinazioni, le liste di
soppressione di faster-whisper e whisper.cpp, i registri di Calliope) sono quasi tutte di
queste famiglie.

Principio 10: riguarda la trascrizione, che il modello non vede come tale, e si scarta solo
la frase **per intero** (nome, punteggiatura e maiuscole a parte): «grazie per la visione»
da sola è rumore, «grazie per la cena» no; «corso gratuito www.…» da solo è rumore, «ho
trovato un corso gratuito di inglese» no; un indirizzo detto per aprirlo («apri
www.ilpost.it») passa. L'effetto è reversibile: la frase vale come vuota, e chi parlava
davvero la ripete. Il nome della famiglia va nel registro dei turni (`allucinazione`).

Solo libreria standard.
"""
from __future__ import annotations

import re

# Frasi intere, già normalizzate (`normalizza`): minuscole, senza punteggiatura, spazi
# singoli. Le prime sono quelle di config.HALLUCINATIONS (dal 24/09), con le varianti viste
FRASI: dict[str, str] = {}
for _famiglia, _frasi in {
    "sottotitoli": (
        "sottotitoli", "sottotitoli in italiano", "sottotitoli creati dalla comunità amara org",
        "sottotitoli creati dalla comunità amara", "sottotitoli e revisione a cura di qtss",
        "sottotitoli a cura di qtss", "sottotitoli revisione a cura di qtss",
        "a cura di qtss", "qtss", "amara org", "subtitles by the amara org community",
        "sottotitoli a cura della redazione"),
    "saluti_video": (
        "grazie per la visione", "grazie a tutti per la visione", "grazie per la visione e "
        "alla prossima", "grazie per aver guardato", "grazie per averci seguito",
        "grazie per l ascolto", "grazie a tutti per l ascolto", "grazie a tutti",
        "ciao a tutti", "ci vediamo nel prossimo video", "ci vediamo al prossimo video",
        "al prossimo video", "alla prossima puntata", "thank you", "thank you pep",
        "thanks for watching", "thank you for watching", "thank you so much for watching"),
    "canale": (
        "iscriviti al canale", "iscrivetevi al canale", "iscriviti", "iscrivetevi",
        "iscriviti al mio canale", "non dimenticare di iscriverti al canale",
        "non dimenticate di iscrivervi al canale", "iscriviti al canale e attiva la campanella",
        "lascia un like e iscriviti al canale", "metti mi piace e iscriviti al canale"),
}.items():
    for _f in _frasi:
        FRASI[_f] = _famiglia

# Un indirizzo nella frase com'è scritta (con i punti): www.qualcosa, qualcosa.org/.com/.it…
_URL = re.compile(r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:org|com|it|info|net|"
                  r"tv|eu)\b(?:/\S*)?", re.I)
# Dopo `normalizza` l'indirizzo è questa parola
URL = "indirizzoweb"
# Famiglie con una parte variabile (sempre sulla frase intera, già normalizzata)
FAMIGLIE: list[tuple[str, re.Pattern]] = [
    # «Sottotitoli a cura di …», «Sottotitoli creati da …» (nomi di gruppi)
    ("sottotitoli", re.compile(r"(?:sottotitoli|sottotitolato|sottotitolazione|traduzione "
                               r"e sottotitoli)(?: e revisione)? (?:a cura|creati|realizzati|"
                               r"fatti)(?: d[aei]\w*)?(?: \w+){0,5}")),
    # Il caso vero: «e con il nostro corso gratuito www.mesmerism.info.it» e le varianti
    # promozionali dei titoli di coda, sempre con un indirizzo in fondo
    ("promozione", re.compile(r"(?:e )?(?:con |per )?(?:il |i )?(?:nostro |nostri )?"
                              r"(?:corso|corsi|video|canale)(?: \w+){0,3} "
                              r"(?:gratuit[oi]|online|completo) (?:su |a |al sito )?" + URL)),
    ("promozione", re.compile(r"(?:seguici su|seguiteci su|per maggiori informazioni(?: visitate)?)"
                              r"(?: il sito)? " + URL)),
    # («visita www.…» no: può essere una richiesta). Solo un indirizzo, senza nient'altro
    ("indirizzo", re.compile(URL)),
]
# Le famiglie che restano rumore anche con il nome davanti o dietro: il nome lo sente la wake
# word acustica, il resto è la coda di un video. «Calliope, ciao a tutti» o «Calliope,
# www.ilpost.it» invece possono essere frasi vere
CON_IL_NOME = ("sottotitoli", "canale", "promozione")
# Suoni tra parentesi: [Musica], (applausi), *risate*, ♪♪. Senza parentesi «musica» e
# «silenzio» sono parole vere («Calliope, silenzio!» è uno stop)
_SUONI = re.compile(r"\W*(?:[\[(*]\s*(?:musica|applausi|risate|sospiro|silenzio|rumore|"
                    r"blank_audio|music|applause|laughter|sound|noise)\s*[\])*]\W*)+|"
                    r"[\s♪♫🎵🎶.…*-]+", re.I)


def normalizza(testo: str) -> str:
    """Minuscole, l'apostrofo tipografico come quello semplice, gli indirizzi come una parola
    sola (URL), senza punteggiatura, spazi singoli."""
    t = (testo or "").lower().replace("’", "'").replace("`", "'")
    t = _URL.sub(" " + URL + " ", t)
    t = re.sub(r"[^\w]+", " ", t)
    return " ".join(t.split())


def _senza_nome(t: str, nomi) -> str:
    """Il nome di Calliope in testa o in coda non conta («Calliope, grazie per la visione»
    sarebbe comunque rumore se il resto lo è: il nome lo sente anche la wake word acustica)."""
    parole = t.split()
    nomi = {normalizza(n) for n in (nomi or ()) if n}
    while parole and parole[0] in nomi:
        parole.pop(0)
    while parole and parole[-1] in nomi:
        parole.pop()
    return " ".join(parole)


def allucinazione(testo: str, nomi=()) -> str | None:
    """La famiglia dell'allucinazione se **tutta** la frase è una frase tipica delle
    allucinazioni di Whisper («sottotitoli», «saluti_video», «canale», «promozione»,
    «indirizzo», «suoni»), altrimenti None. La stringa vuota non è un'allucinazione (è già
    vuota)."""
    if not (testo or "").strip():
        return None
    if _SUONI.fullmatch(testo.strip()):
        return "suoni"
    t = normalizza(testo)
    for prova in (t, _senza_nome(t, nomi)):
        if not prova:
            continue
        f = FRASI.get(prova)
        if f is None:
            f = next((fam for fam, rx in FAMIGLIE if rx.fullmatch(prova)), None)
        if f is not None and (prova == t or f in CON_IL_NOME):
            return f
    return None
