"""
Prova a secco della pronuncia degli inglesismi (04/10/2026, calliope/pronuncia.py).

Richiesta dell'utente: «sentire dire "file" invece di "fail", parlando dei file del
computer, è un po' ridicolo». Qui: le sostituzioni (maiuscole, plurali, apostrofi,
punteggiatura), i casi contrari («le file di sedie», «profile», «filet», «emailing»), le voci
dell'utente e i fonemi `[[ ]]`, che solo il testo per Piper cambia (`Speaker._pcm`, frasi
d'attesa, saluto del satellite) e non `played` né la storia, il costo (< 1 ms a frase) e,
con piper installato, che espeak legga ogni grafia del lessico con i fonemi attesi.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope.config import Config
from calliope.pronuncia import LESSICO, Pronuncia, supporta_fonemi

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


P = Pronuncia()

# ── sostituzioni ──
CASI = [
    ("Il file è nella cartella Documenti.", "Il fàil è nella cartella Documenti."),
    ("File salvato.", "Fàil salvato."),
    ("Ho trovato 2 file: chiavi csv e chiavi xlsx.", "Ho trovato 2 fàil: chiavi csv e chiavi xlsx."),
    ("Non ho trovato nessun file con quel nome.", "Non ho trovato nessun fàil con quel nome."),
    ("il tipo di file che cerchi", "il tipo di fàil che cerchi"),
    ("Dividilo in file separati.", "Dividilo in fàil separati."),
    ("Ci sono due file di testo.", "Ci sono due fàil di testo."),
    ("Ti ho mandato un'email.", "Ti ho mandato un'imèil."),
    ("Leggo l'e-mail e le emails.", "Leggo l'imèil e le imèils."),
    ("La password del wifi, quella del Wi-Fi e del WIFI.",
     "La password del uàifài, quella del Uàifài e del Uàifài."),
    ("Ho fatto il backup?", "Ho fatto il bèkap?"),
    ("Apro PowerPoint, poi Outlook.", "Apro Pàuerpoint, poi Àutluk."),
    ("Ho salvato uno screenshot…", "Ho salvato uno scrìnsciot…"),
    ("«file»", "«fàil»"),
]
for prima, attesa in CASI:
    out = P.applica(prima)
    verifica(f"sostituzione: {prima!r}", out == attesa, out)

# ── casi contrari: «file» = plurale di «fila», parole dentro altre parole, già giuste ──
CONTRARI = [
    "Ci sono tre file di sedie in sala.",
    "Siediti nelle prime file.",
    "Le file ordinate dei banchi.",
    "Mettetevi in file ordinate.",
    "Serrate le file!",
    "Alcune file erano vuote.",
    "Tra le file degli alberi.",
    "Apri il profile del filet, emailing e filetto.",
    "Il computer ha un mouse, un timer e il weekend libero.",
    "Ho messo un timer di 5 minuti.",
    "Home Assistant è collegato.",
    "pre-file e file-system",
]
for t in CONTRARI:
    out = P.applica(t)
    verifica(f"invariata: {t!r}", out == t, out)

# ── voci dell'utente, fonemi tra [[ ]], disattivata ──
U = Pronuncia({"podcast": "pòdcast", "Spotify": "[[spˈɔtifaɪ]]", "windows": ""})
verifica("voce aggiunta (grafia)", U.applica("Metto il podcast.") == "Metto il pòdcast.",
         U.applica("Metto il podcast."))
verifica("voce tolta («windows» vuoto)", U.applica("Apro Windows.") == "Apro Windows.")
out = U.applica("Su Spotify, poi basta.")
verifica("fonemi con la punteggiatura dentro il blocco", out == "Su [[spˈɔtifaɪ,]] poi basta.", out)
out = U.applica("Su Spotify.", fonemi=False)
verifica("fonemi con un Piper senza blocchi: parola com'è", out == "Su Spotify.", out)
verifica("le doppie quadre del testo non diventano fonemi",
         P.applica("[[kaboom]] file") == "kaboom fàil", P.applica("[[kaboom]] file"))
verifica("disattivata", Pronuncia(attiva=False).applica("il file") == "il file")
verifica("testo vuoto", P.applica("") == "")

# ── configurazione ──
cfg = Config()
verifica("Config.tts_pronuncia acceso di predefinito", cfg.tts_pronuncia is True)
verifica("Config.tts_pronuncia_extra vuoto di predefinito", cfg.tts_pronuncia_extra == {})

# ── Speaker: solo il testo per Piper cambia ──
from calliope.tts import Speaker  # noqa: E402


class VoceFinta:
    def __init__(self, vecchia=False):
        self.testi = []
        if vecchia:
            self.synthesize_stream_raw = lambda t: (self.testi.append(t), [b"\0\0"])[1]

    def phonemize(self, text):
        return [[text]]

    def synthesize(self, text):
        self.testi.append(text)

        class Ch:
            audio_int16_bytes = b"\0\0"
        return [Ch()]


sp = object.__new__(Speaker)
sp.pronuncia = Pronuncia({"spotify": "[[spˈɔtifaɪ]]"})
v = VoceFinta()
sp._pcm(v, "Il file è su Spotify.")
verifica("Speaker._pcm: a Piper la grafia e i fonemi", v.testi == ["Il fàil è su [[spˈɔtifaɪ.]]"],
         str(v.testi))
verifica("supporta_fonemi: piper ≥ 1.3", supporta_fonemi(v))
vv = VoceFinta(vecchia=True)
sp._pcm(vv, "Il file è su Spotify.")
verifica("Piper vecchio: grafia sì, fonemi no", vv.testi == ["Il fàil è su Spotify."],
         str(vv.testi))
verifica("supporta_fonemi: piper < 1.3", not supporta_fonemi(vv))
# played e storia: _play riceve il testo originale (la coda tiene (item, audio))
sp.voice = VoceFinta()
sp._fillers, sp._current_voice_path = {}, "x"
verifica("_synth usa la pronuncia", sp._synth("il file") == b"\0\0"
         and sp.voice.testi == ["il fàil"])

# ── costo ──
frasi = [a for a, _ in CASI] + CONTRARI
t0 = time.perf_counter()
for _ in range(500):
    for f in frasi:
        P.applica(f)
us = (time.perf_counter() - t0) / (500 * len(frasi)) * 1e6
verifica(f"costo {us:.1f} µs a frase (< 200)", us < 200)

# ── espeak: la grafia dà i fonemi attesi ──
FONEMI_ATTESI = {
    "fàil": "fˈaɪl", "fàils": "fˈaɪls", "imèil": "imˈɛjl", "imèils": "imˈɛjls",
    "uàifài": "wˈaɪfˈaɪ", "bèkap": "bˈɛkap", "scrìnsciot": "skɾˈinʃot",
    "plèilist": "plˈɛjlist", "mìting": "mˈitiŋɡ", "cùki": "kˈukɪ", "nòtbuk": "nˈɔtbʊk",
    "àutluk": "ˈaʊtlʊk", "uìndous": "wˈindoʊs", "pàuerpoint": "pˈaʊeɾpoint",
    "uandràiv": "wandɾˈaɪv", "kròm": "kɾˈɔm", "èdset": "ˈɛdset",
    "rèsberri": "ɾˈɛzberɾɪ", "uìsper": "wˈispeɾ", "pàiper": "pˈaɪpeɾ", "dòker": "dˈɔkeɾ",
    "uikikuòt": "wikikʊˈɔt", "dàk di ènne èsse": "dˈak dɪ ˈɛnne ˈɛsse",
}
verifica("ogni grafia del lessico ha i suoi fonemi attesi",
         set(LESSICO.values()) == set(FONEMI_ATTESI),
         str(set(LESSICO.values()) ^ set(FONEMI_ATTESI)))
try:
    import unicodedata

    from piper.phonemize_espeak import EspeakPhonemizer
    esp = EspeakPhonemizer()
except Exception as e:  # noqa: BLE001
    print(f"SALTATA IN PARTE: espeak non disponibile ({type(e).__name__}): controllo dei fonemi saltato")
else:
    for grafia, attesi in FONEMI_ATTESI.items():
        fon = "".join("".join(s) for s in esp.phonemize("it", grafia))
        fon = unicodedata.normalize("NFC", fon).strip()
        verifica(f"espeak: {grafia} → {attesi}", fon == unicodedata.normalize("NFC", attesi), fon)

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
