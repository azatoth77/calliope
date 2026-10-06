"""
Registra (o registra di nuovo) la voce di una persona, da riga di comando.

Serve dopo un cambio di modello dell'impronta (il 24/09 dall'MFCC a CAM++: le vecchie
impronte non valgono più) o per aggiungere qualcuno senza passare dal tool vocale.
Farlo dalla tastiera vuol dire avere accesso fisico al PC: nome, admin e voce preferita
di un profilo esistente restano come sono.

Uso:
    python arruola.py Dario                     # frasi dette al microfono
    python arruola.py Dario --da registrazioni\\2026-09-24-v03 [altre cartelle] [--max 10]
    python arruola.py Giulia --admin            # nuovo profilo che amministra
    python arruola.py Bianca --nascita 2017-05-12 --tutore Dario [--tutore Elena]
                                                # minorenne (05/10, calliope/minori.py): la
                                                # fascia d'età si ricalcola dalla data
    python arruola.py Matteo --giovane        # vecchio modo: fascia «ragazzi» senza data

Con --da usa i WAV già registrati (16 kHz mono): solo quelli con abbastanza voce, e solo
se sono sicuramente della persona indicata.
"""

import sys
import wave
from pathlib import Path

import numpy as np

from calliope.config import Config, load_config
from calliope.speaker_id import SpeakerRegistry, estimate_gender


def _voiced(cfg: Config, audio: np.ndarray) -> float:
    """Durata della voce senza pre-roll e silenzio finale (come in calliope/main.py)."""
    return max(0.0, len(audio) / cfg.sample_rate - (cfg.preroll_ms + cfg.silence_ms) / 1000)


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def from_recordings(cfg: Config, folders: list[str], limit: int) -> list[np.ndarray]:
    """Le frasi più lunghe delle cartelle indicate, distribuite tra le cartelle."""
    per_folder = []
    for f in folders:
        clips = [_read_wav(p) for p in sorted(Path(f).glob("*.wav"))]
        clips = [a for a in clips if _voiced(cfg, a) >= cfg.speaker_enroll_min_s]
        per_folder.append(sorted(clips, key=len, reverse=True))
    chosen = []
    while len(chosen) < limit and any(per_folder):
        for clips in per_folder:                       # una per cartella a turno
            if clips and len(chosen) < limit:
                chosen.append(clips.pop(0))
    return chosen


def from_microphone(cfg: Config, count: int) -> list[np.ndarray]:
    """Frasi dette al microfono, una alla volta, con il VAD di Calliope."""
    from calliope.audio import Listener
    listener = Listener(cfg)
    phrases = ["Buongiorno, oggi vorrei sapere che tempo farà nel pomeriggio.",
               "Ricordami di comprare il pane e il latte quando esco.",
               "Mi piacerebbe ascoltare un po' di musica tranquilla stasera.",
               "Quanto tempo ci vuole per andare in treno da Milano a Roma?",
               "Accendi la luce in cucina e abbassa quella del salotto.",
               "Raccontami qualcosa di interessante sulla storia di Venezia.",
               "Domani mattina devo alzarmi presto, svegliami alle sette.",
               "Qual è la differenza tra un vulcano attivo e uno spento?"]
    clips = []
    while len(clips) < count:
        text = phrases[len(clips) % len(phrases)]
        print(f"\n[{len(clips) + 1}/{count}] Leggi ad alta voce: «{text}»")
        audio = listener.listen()
        v = _voiced(cfg, audio)
        if v < cfg.speaker_enroll_min_s:
            print(f"   troppo breve ({v:.1f} s di voce): ripeti")
            continue
        print(f"   ok ({v:.1f} s di voce)")
        clips.append(audio)
    return clips


def main(argv: list[str]):
    if not argv or argv[0].startswith("--"):
        sys.exit(__doc__)
    cfg = load_config()
    name, args = argv[0], argv[1:]
    limit = cfg.speaker_enroll_phrases
    if "--max" in args:
        i = args.index("--max")
        limit = int(args[i + 1])
        del args[i:i + 2]
    admin = True if "--admin" in args else None
    # Minori (05/10): data di nascita e tutori (nomi di profili registrati)
    nascita, tutori = None, []
    if "--nascita" in args:
        from calliope.minori import leggi_data
        i = args.index("--nascita")
        nascita = leggi_data(args[i + 1]) if i + 1 < len(args) else None
        if nascita is None:
            sys.exit("--nascita vuole una data passata, come 2017-05-12")
        del args[i:i + 2]
    while "--tutore" in args:
        i = args.index("--tutore")
        tutori.append(args[i + 1] if i + 1 < len(args) else "")
        del args[i:i + 2]
    folders = []
    if "--da" in args:
        folders = [a for a in args[args.index("--da") + 1:] if not a.startswith("--")]

    registry = SpeakerRegistry(cfg)
    ids_tutori = []
    for t in tutori:
        trovato = registry.find(t)
        if trovato is None:
            sys.exit(f"Tutore «{t}» non registrato: registra prima la sua voce")
        ids_tutori.append(registry.get(trovato).id)
    existing = registry.get(name)
    print(f"{'Aggiorno' if existing else 'Creo'} il profilo «{name}» "
          f"con {registry.embedder.model_name}")

    clips = from_recordings(cfg, folders, limit) if folders else from_microphone(cfg, limit)
    if len(clips) < cfg.speaker_enroll_phrases:
        sys.exit(f"Servono almeno {cfg.speaker_enroll_phrases} frasi con "
                 f"{cfg.speaker_enroll_min_s} s di voce: trovate {len(clips)}.")

    embs = [registry.embed(a, cfg.sample_rate) for a in clips]
    gender = existing.gender if existing and existing.gender else estimate_gender(
        np.concatenate(clips), cfg.sample_rate)
    prof = registry.set_voiceprint(name, embs, gender=gender, admin=admin)
    from calliope import minori
    if nascita is not None:
        prof.nascita, prof.fascia = nascita.isoformat(), None
    elif "--giovane" in args and not prof.nascita:
        prof.fascia = "ragazzi"           # il vecchio «giovane»: fascia senza data
    if ids_tutori:
        prof.tutori = ids_tutori
    if minori.e_minore(prof) and not prof.tutori:
        prof.tutori = [u.id for u in registry.users.values() if u.admin and u is not prof]
    if prof.admin and minori.e_minore(prof):
        prof.admin = False                # un minore non amministra
    registry.save()

    # Coerenza interna: ogni frase contro la media delle altre
    scores = []
    for i, e in enumerate(embs):
        rest = np.mean([x for j, x in enumerate(embs) if j != i], axis=0)
        scores.append(float(np.dot(e, rest / np.linalg.norm(rest))))
    print(f"Fatto: {len(embs)} frasi, coerenza {min(scores):.2f}–{max(scores):.2f} "
          f"(soglia di riconoscimento {cfg.speaker_id_threshold:.2f}). "
          f"admin={prof.admin}, fascia={minori.fascia(prof)}, nascita={prof.nascita}, "
          f"genere={prof.gender}, "
          f"voce={prof.preferred_voice}")


if __name__ == "__main__":
    main(sys.argv[1:])
