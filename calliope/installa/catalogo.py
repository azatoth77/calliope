"""
Il catalogo delle installazioni: le sole cose che Calliope può scaricare (01/10/2026).

Ogni azione ha un'origine fissa (scritta qui, mai scelta dal modello), una dimensione, un
checksum SHA-256, una cartella di destinazione e dei prerequisiti. Il modello sceglie solo
l'id dell'azione (un enum nel tool); URL, nomi dei file e checksum vengono da qui o dalle
fonti ufficiali indicate qui.

Fuori dal catalogo, sempre: pacchetti Python (pip), calliope.yaml e calliope.locale.yaml.
Per quelli Calliope dice cosa fare, non lo fa.

Origini:
- biblioteca: i file ZIM italiani di Kiwix. Versione, nome, dimensione e checksum NON sono
  scritti qui: si risolvono a ogni proposta, in modo deterministico, dall'indice di
  download.kiwix.org/zim/<cartella>/ (elenco Apache): tra i nomi che corrispondono
  esattamente a <prefisso>_AAAA-MM.zim vince la data più alta. Il checksum è il file
  ufficiale <nome>.sha256 accanto, la dimensione il Content-Length sul mirror. Si scarica
  dal mirror ftp.fau.de (~10 MB/s: 9 GB in 13 minuti il 26/09, biblioteca/scarica.log;
  download.kiwix.org diretto è lento). Kiwix tiene solo le ultime due versioni di ogni
  file: una versione scritta nel codice prima o poi non si troverebbe più;
- voci: il catalogo ufficiale di Piper (rhasspy/piper-voices su Hugging Face), le quattro
  voci italiane; SHA-256 dei file scaricati il 21/09 (voices/LEGGIMI.md: coincidono con
  quelli pubblicati da Hugging Face);
- chi parla: CAM++ di 3D-Speaker convertito da sherpa-onnx (release
  «speaker-recongition-models», con il refuso del tag), SHA-256 della ricerca del 24/09
  (docs/ricerche/2026-09-24-riconoscimento-parlante.md, models/speaker/checksum.txt);
- Whisper di riserva (02/10): il modello di faster-whisper per la trascrizione su CPU quando
  il server di trascrizione (whisper.cpp sulla DGX) non risponde. Gli stessi file che
  faster-whisper scaricherebbe da sé al primo guasto (dal repository di Hugging Face che
  usa, a una revisione fissa), con lo SHA-256 dei file in cache sul portatile, in
  models/whisper/<modello>/: `whisper_locale` li trova lì prima della cache di Hugging Face;
- modello linguistico: solo il nome in llm_model, con /api/pull dell'Ollama locale, che
  scarica dal suo registro e verifica da sé i digest SHA-256 dei pezzi.

Un file ZIM si attiva solo a checksum verificato: allora l'installatore scrive accanto
<nome>.verificato, e `risolvi_zim` sceglie il file verificato più recente della stessa
famiglia al posto di quello scritto in calliope.yaml, che non si tocca. Per le famiglie in
cui si cerca per parole (Fonte.indice: Wikipedia ridotta, Vikidia) serve anche l'indice
SQLite FTS5 completo in biblioteca/indici/ (calliope/biblioteca_indice.py): l'installatore lo
costruisce subito dopo la verifica (passo «indice»), e l'azione `biblioteca_indice` lo rifà
se manca o è vecchio.

Le fonti oltre alle quattro della ricerca (Wikisource, Wikiquote, Gutenberg…) si scaricano
e si verificano, ma `calliope/biblioteca.py` oggi non le legge: il registro delle capacità
le mostra come «scaricate, non ancora usate nella ricerca» (`fonti_scaricate`). Il punto
d'integrazione è `Config.biblioteca_fonti_extra`.
"""

import re
from dataclasses import dataclass
from pathlib import Path

KIWIX_MIRROR = "https://ftp.fau.de/kiwix/zim"
KIWIX_MAIN = "https://download.kiwix.org/zim"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT"
SHERPA = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
          "speaker-recongition-models")

# Host ammessi, anche dopo un reindirizzamento: download.kiwix.org rimanda al bilanciatore
# (lb.download.kiwix.org), Hugging Face e GitHub ai loro server di file
HOST_KIWIX = ("ftp.fau.de", "download.kiwix.org", "lb.download.kiwix.org")
HOST_HF = ("huggingface.co", "cdn-lfs.huggingface.co", "cdn-lfs.hf.co", "cdn-lfs-us-1.hf.co",
           "cas-bridge.xethub.hf.co",
           # 02/10: i file grandi (Xet) arrivano da qui (model.bin di Whisper, curl -IL)
           "us.aws.cdn.hf.co", "eu.aws.cdn.hf.co")
HOST_GITHUB = ("github.com", "objects.githubusercontent.com",
               "release-assets.githubusercontent.com")
HOST_JSDELIVR = ("cdn.jsdelivr.net",)

# Web app del telefono (03/10, calliope/schermi/telefono.py): onnxruntime-web 1.30.0 (gli
# stessi file del pacchetto npm, da jsDelivr: solo WebAssembly, un thread) e i due modelli
# generici della wake word (openWakeWord v0.5.1, Apache 2.0, gli stessi di
# wakeword/scarica_modelli.py). Dimensioni e SHA-256 misurati il 03/10 sul pacchetto npm e
# sulla release di GitHub. Il classificatore «Calliope» non si scarica: è addestrato qui
ORT_WEB = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist"
ORT_WEB_FILE = (
    ("ort.wasm.min.mjs", 50126,
     "219e6a1fc8a9938268d18efca3c91d310bd2f4a59bbd13744df5b2b7fc6cee3b"),
    ("ort-wasm-simd-threaded.mjs", 24381,
     "e13f7f94fc51b4ca72b12faeb1ee95f4ace6dfbc8939bc718aabdc0a27c4299b"),
    ("ort-wasm-simd-threaded.wasm", 14239897,
     "3398c10d07d229bd91b364548e130e0e51a8e5704b88c7c083ebbeb78842dee2"))
OWW = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
OWW_FILE = (
    ("melspectrogram.onnx", 1087958,
     "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f"),
    ("embedding_model.onnx", 1326578,
     "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f"))


@dataclass(frozen=True)
class FileCat:
    url: str
    dest: str                 # percorso del file (relativo alla cartella di Calliope)
    size: int | None          # byte
    sha256: str | None


@dataclass(frozen=True)
class Fonte:
    """Una famiglia di file ZIM di Kiwix: <prefisso>_AAAA-MM.zim nella cartella di Kiwix."""
    id: str                   # id dell'azione
    prefisso: str             # wikiquote_it_all_nopic
    cartella: str             # cartella sul sito di Kiwix
    titolo: str               # per la voce: «Wikiquote, le citazioni»
    attr: str | None = None   # campo di Config, per le quattro fonti usate nella ricerca
    nota: str = ""            # detta nella proposta (es. la versione con le immagini)
    indice: bool = False      # la ricerca per parole la usa: serve l'indice FTS5
    # Fonti in più: quando la ricerca le usa. "" = mai (non ancora integrata); altrimenti
    # il tipo di domanda che le chiama (biblioteca.RICHIESTE: "citazioni"…)
    richiesta: str = ""


# Le quattro fonti che calliope/biblioteca.py usa nella ricerca, poi le altre italiane di
# Kiwix (docs/ricerche/2026-09-21-biblioteca-offline.md, §1.2–1.6), nopic dove esiste: alla
# voce il testo basta
FONTI = (
    Fonte("biblioteca_mini", "wikipedia_it_all_mini", "wikipedia",
          "Wikipedia ridotta, con introduzioni e schede delle voci", "biblioteca_mini",
          indice=True),
    Fonte("biblioteca_completa", "wikipedia_it_all_nopic", "wikipedia",
          "Wikipedia completa, solo testo", "biblioteca_completa"),
    Fonte("biblioteca_ragazzi", "vikidia_it_all_nopic", "vikidia",
          "Vikidia, l'enciclopedia per ragazzi", "biblioteca_ragazzi", indice=True),
    Fonte("biblioteca_dizionario", "wiktionary_it_all_nopic", "wiktionary",
          "il Wikizionario, il dizionario", "biblioteca_dizionario"),
    Fonte("fonte_wikisource", "wikisource_it_all_nopic", "wikisource",
          "Wikisource, i testi classici"),
    Fonte("fonte_wikibooks", "wikibooks_it_all_nopic", "wikibooks", "Wikibooks, i manuali"),
    # Wikiquote (01/10): solo quando si chiede una citazione o chi ha detto una frase
    Fonte("fonte_wikiquote", "wikiquote_it_all_nopic", "wikiquote", "Wikiquote, le citazioni",
          indice=True, richiesta="citazioni"),
    Fonte("fonte_wikivoyage", "wikivoyage_it_all_nopic", "wikivoyage",
          "Wikivoyage, le guide di viaggio"),
    Fonte("fonte_wikiversita", "wikiversity_it_all_nopic", "wikiversity",
          "Wikiversità, le lezioni"),
    Fonte("fonte_wikimed", "wikipedia_it_medicine_nopic", "wikipedia",
          "WikiMed, le voci di medicina"),
    Fonte("fonte_gutenberg", "gutenberg_it_all", "gutenberg",
          "Gutenberg, i libri in italiano"),
    Fonte("fonte_wikipedia_immagini", "wikipedia_it_all_maxi", "wikipedia",
          "Wikipedia completa con le immagini",
          nota="È facoltativa: alla voce le immagini non servono, e Wikipedia completa "
               "solo testo ha le stesse voci."),
)
RICERCA = tuple(f for f in FONTI if f.attr)          # quelle che la ricerca usa oggi
CON_INDICE = tuple(f for f in FONTI if f.indice)     # quelle con l'indice FTS5
ALTRE = tuple(f for f in FONTI if not f.attr)

# Voci italiane del catalogo ufficiale di Piper: (id, nome, qualità, onnx, json)
VOCI = (
    ("voce_serena_alta", "serena", "high", (114204024,
     "7462fbdf03727fb4c0c161286ad538fe6436b7e4b1c3059ef52930032475955f"),
     (5252, "60597bac737a20766591fe24d1315df9a3811dc3509e69bc394cdee19eccbae7")),
    ("voce_serena", "serena", "medium", (63516051,
     "fe4e26b2c1236e2a44d2e295cad564d94a0d8b0a9fca1ccdfd70dd4af3116eb5"),
     (5254, "14cb4995874138b2792ae07753b5540942124761af9ae6609f9b520f28837881")),
    ("voce_paola", "paola", "medium", (63511038,
     "6fc918b5a0ea6137382833dddfa567bffbe6a5060c02043c87192ee59c04210c"),
     (7099, "aea19c0a7fce29fbc359b93f10e7902854401e4c95ae2ea328ae516b15d296cf")),
    ("voce_riccardo", "riccardo", "x_low", (28130791,
     "1368de15f123275a7ef951c9e5e30be0f58a032daa14a0da44037443c1d1d21b"),
     (4161, "146ab9c634afe524e9fb7530f2510df7a42fb1db56b52658ca1fb3d98001a62a")),
)
# Whisper di riserva per faster-whisper: modello → (repository, revisione, [(file, byte,
# SHA-256)]). Il repository è quello di faster_whisper.utils._MODELS (Hugging Face lo rimanda
# a dropbox-dash/…, stesso contenuto); revisione e checksum dalla cache del portatile, che
# trascrive con questi file dal 21/09. model.bin è in float16: su CPU diventa int8 al
# caricamento.
WHISPER = {
    "large-v3-turbo": ("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                       "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf", (
        ("config.json", 2263,
         "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e"),
        ("preprocessor_config.json", 340,
         "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
        ("tokenizer.json", 2710337,
         "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd"),
        ("vocabulary.json", 1068114,
         "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1"),
        ("model.bin", 1617884929,
         "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"))),
}
HF = "https://huggingface.co"


def cartella_whisper(cfg) -> Path:
    """Dove l'installazione mette il modello di riserva: <whisper_cartella>/<modello>."""
    return Path(getattr(cfg, "whisper_cartella", None) or "models/whisper") / str(
        cfg.whisper_model)


def whisper_locale(cfg) -> Path | None:
    """La cartella del modello Whisper installato dal catalogo, se completa, altrimenti
    None: allora faster-whisper usa il nome e la cache di Hugging Face, come prima. Ogni file
    prende il suo nome solo dopo il checksum, e model.bin è l'ultimo: se c'è, ci sono tutti."""
    d = cartella_whisper(cfg)
    return d if (d / "model.bin").is_file() and (d / "config.json").is_file() else None


CAMPP = ("3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx", 28281164,
         "aa3cfc16963a10586a9393f5035d6d6b57e98d358b347f80c2a30bf4f00ceba2")


@dataclass(frozen=True)
class Azione:
    id: str
    titolo: str               # per la voce: «Wikiquote, le citazioni», «la voce Paola»
    tipo: str                 # file | kiwix | ollama | aggiorna_zim | pulizia
    capacita: str             # capacità che sistema (calliope/capacita.py)
    files: tuple[FileCat, ...] = ()      # tipo file: i file fissi
    fonti: tuple[Fonte, ...] = ()        # tipo kiwix, aggiorna_zim, pulizia
    librerie: tuple[str, ...] = ()       # moduli che devono importarsi su questa macchina
    attivazione: str = "subito"          # subito | riavvio | nessuna (fonti non usate)
    origine: str = ""                    # detta nella proposta
    hosts: tuple[str, ...] = ()


def cartella_biblioteca(cfg) -> Path:
    """La cartella dei file ZIM: quella del Wikipedia ridotto in configurazione."""
    for attr in ("biblioteca_mini", "biblioteca_completa"):
        p = getattr(cfg, attr, None)
        if p:
            return Path(p).parent
    return Path("biblioteca")


def catalogo(cfg, origini: dict | None = None) -> dict[str, Azione]:
    """Le azioni installabili per questa configurazione. `origini` sostituisce le basi degli
    URL solo nelle prove (server HTTP finto in locale): il tool non lo può passare."""
    o = {"kiwix_mirror": KIWIX_MIRROR, "kiwix_main": KIWIX_MAIN, "piper": PIPER,
         "sherpa": SHERPA, "hf": HF, "ort_web": ORT_WEB, "oww": OWW, **(origini or {})}
    finto = bool(origini)
    h_kiwix = ("127.0.0.1",) if finto else HOST_KIWIX
    h_hf = ("127.0.0.1",) if finto else HOST_HF
    h_gh = ("127.0.0.1",) if finto else HOST_GITHUB
    out: dict[str, Azione] = {}
    # Niente librerie da controllare: dal 01/10 i file ZIM si leggono in puro Python
    # (calliope/zim.py) e la ricerca usa SQLite FTS5 (calliope/biblioteca_indice.py)
    kiwix = dict(origine="dal mirror di Kiwix", hosts=h_kiwix, capacita="biblioteca")
    for f in FONTI:
        out[f.id] = Azione(id=f.id, titolo=f.titolo, tipo="kiwix", fonti=(f,),
                           attivazione="subito" if f.attr else "nessuna", **kiwix)
    out["biblioteca"] = Azione(id="biblioteca", titolo="la biblioteca offline", tipo="kiwix",
                               fonti=RICERCA, **kiwix)
    out["biblioteca_aggiorna"] = Azione(id="biblioteca_aggiorna",
                                        titolo="l'aggiornamento della biblioteca",
                                        tipo="aggiorna_zim", fonti=FONTI, **kiwix)
    # Solo lavoro locale: l'indice FTS5 dei file che ne hanno bisogno (dopo un download lo
    # prepara già l'azione che scarica; questa serve se manca, è a metà o è di una versione
    # vecchia dell'estrattore)
    out["biblioteca_indice"] = Azione(id="biblioteca_indice",
                                      titolo="l'indice di ricerca della biblioteca",
                                      tipo="indice", capacita="biblioteca", fonti=CON_INDICE,
                                      origine="su questo computer, senza internet")
    from ..config import VOICE_MAP
    folder = Path(next(iter(VOICE_MAP.values()))).parent
    for vid, name, quality, onnx, js in VOCI:
        base = f"{o['piper']}/{name}/{quality}/it_IT-{name}-{quality}"
        dest = str(folder / f"it_IT-{name}-{quality}")
        title = f"la voce {name.capitalize()}" + (" in alta qualità" if quality == "high"
                                                    else "")
        out[vid] = Azione(
            id=vid, titolo=title, tipo="file", capacita="voce",
            files=(FileCat(base + ".onnx", dest + ".onnx", *onnx),
                   FileCat(base + ".onnx.json", dest + ".onnx.json", *js)),
            librerie=("piper",), origine="dal catalogo ufficiale delle voci di Piper",
            hosts=h_hf)
    speaker = getattr(cfg, "speaker_model", None) or f"models/speaker/{CAMPP[0]}"
    out["modello_chi_parla"] = Azione(
        id="modello_chi_parla", titolo="il modello per riconoscere le voci", tipo="file",
        capacita="chi_parla",
        files=(FileCat(f"{o['sherpa']}/{CAMPP[0]}", str(Path(speaker).parent / CAMPP[0]),
                       CAMPP[1], CAMPP[2]),),
        librerie=("onnxruntime",), attivazione="riavvio",
        origine="dalle release di sherpa-onnx su GitHub", hosts=h_gh)
    w = WHISPER.get(str(getattr(cfg, "whisper_model", "")))
    if w:
        repo, rev, files = w
        dest = cartella_whisper(cfg)
        out["whisper_riserva"] = Azione(
            id="whisper_riserva", titolo=f"il modello di riserva di Whisper ({cfg.whisper_model})",
            tipo="file", capacita="stt",
            files=tuple(FileCat(f"{o['hf']}/{repo}/resolve/{rev}/{name}", str(dest / name),
                                size, sha) for name, size, sha in files),
            librerie=("faster_whisper",),
            origine="da Hugging Face, gli stessi file che usa faster-whisper", hosts=h_hf)
    web = Path(str(getattr(cfg, "telefono_web", "") or "models/web"))
    wake = Path(str(getattr(cfg, "wake_model", "") or "wakeword/modelli/calliope.onnx")).parent
    out["telefono"] = Azione(
        id="telefono", titolo="i file della web app del telefono", tipo="file",
        capacita="schermi",
        files=tuple(FileCat(f"{o['ort_web']}/{n}", str(web / n), size, sha)
                    for n, size, sha in ORT_WEB_FILE)
        + tuple(FileCat(f"{o['oww']}/{n}", str(wake / n), size, sha)
                for n, size, sha in OWW_FILE),
        origine="da npm (onnxruntime-web, via jsDelivr) e dalle release di openWakeWord su "
                "GitHub",
        hosts=("127.0.0.1",) if finto else HOST_JSDELIVR + HOST_GITHUB)
    out["modello_llm"] = Azione(
        id="modello_llm", titolo=f"il modello linguistico {cfg.llm_model}", tipo="ollama",
        capacita="llm", origine="dal registro di Ollama, tramite l'Ollama di questo computer")
    out["pulizia"] = Azione(
        id="pulizia", titolo="la pulizia dei file vecchi della biblioteca", tipo="pulizia",
        capacita="biblioteca", fonti=FONTI)
    return out


# Descrizioni brevi per il tool (l'enum delle azioni), senza dimensioni: le dice la proposta
DESCRIZIONI = {
    "biblioteca": "la biblioteca offline (Wikipedia, Vikidia, Wikizionario: i file che mancano)",
    "biblioteca_mini": "Wikipedia ridotta",
    "biblioteca_completa": "Wikipedia completa, solo testo",
    "biblioteca_ragazzi": "Vikidia, enciclopedia per ragazzi",
    "biblioteca_dizionario": "Wikizionario, il dizionario",
    "fonte_wikisource": "Wikisource, testi classici",
    "fonte_wikibooks": "Wikibooks, manuali",
    "fonte_wikiquote": "Wikiquote, citazioni",
    "fonte_wikivoyage": "Wikivoyage, guide di viaggio",
    "fonte_wikiversita": "Wikiversità, lezioni",
    "fonte_wikimed": "WikiMed, medicina",
    "fonte_gutenberg": "Gutenberg, libri in italiano",
    "fonte_wikipedia_immagini": "Wikipedia con le immagini (facoltativa, molto grande)",
    "biblioteca_aggiorna": "aggiorna i file della biblioteca all'ultima versione",
    "biblioteca_indice": "prepara l'indice di ricerca della biblioteca (se manca o è vecchio)",
    "voce_serena_alta": "voce Serena alta qualità",
    "voce_serena": "voce Serena",
    "voce_paola": "voce Paola",
    "voce_riccardo": "voce Riccardo (maschile)",
    "modello_chi_parla": "modello per riconoscere le voci",
    "whisper_riserva": "modello di Whisper per trascrivere su CPU se il server non risponde",
    "modello_llm": "il modello linguistico della configurazione",
    "telefono": "i file della web app del telefono (wake word e VAD nel browser)",
    "pulizia": "cancella i file vecchi della biblioteca dopo un aggiornamento",
}

# ─────────────────────────── versioni della biblioteca ───────────────────────────
_ZIM_RE = re.compile(r"^(?P<fam>.+)_(?P<ver>\d{4}-\d{2})\.zim$")
MARCATORE = ".verificato"


def versione_zim(path: str) -> tuple[str, str] | None:
    """(famiglia, versione) dal nome del file, o None."""
    m = _ZIM_RE.match(Path(path).name)
    return (m["fam"], m["ver"]) if m else None


def verificato(path: str | Path) -> bool:
    return Path(str(path) + MARCATORE).is_file()


def versioni_locali(folder: Path, prefisso: str) -> list[tuple[str, Path]]:
    """Le versioni di una famiglia presenti nella cartella, in ordine di data."""
    out = []
    try:
        candidates = list(Path(folder).glob(f"{prefisso}_*.zim"))
    except OSError:
        return []
    for q in candidates:
        qv = versione_zim(str(q))
        if qv and qv[0] == prefisso:
            out.append((qv[1], q))
    return sorted(out)


_FAMIGLIE: dict[str, Fonte] = {f.prefisso: f for f in FONTI}


def serve_indice(path: str | Path | None) -> bool:
    """Il file appartiene a una famiglia in cui si cerca per parole (indice FTS5)?"""
    fv = versione_zim(str(path)) if path else None
    f = _FAMIGLIE.get(fv[0]) if fv else None
    return bool(f and f.indice)


def risolvi_zim(path: str | None) -> str | None:
    """Il file da aprire per un percorso della configurazione: quello configurato, oppure
    il più recente della stessa famiglia nella stessa cartella che l'installatore ha
    verificato con il checksum (marcatore .verificato). Così un aggiornamento, o un primo
    scaricamento con un nome diverso da quello in calliope.yaml, si attiva senza toccare
    la configurazione.

    Per le famiglie con l'indice di ricerca (Wikipedia ridotta, Vikidia) si passa a un file
    nuovo solo quando anche il suo indice è completo (calliope/biblioteca_indice.py): mentre
    si costruisce resta in uso il vecchio. Se un file più vecchio non c'è, va bene anche
    senza indice (la ricerca è ridotta, ma meglio di niente)."""
    if not path:
        return path
    p = Path(path)
    fv = versione_zim(path)
    if fv is None:
        return path
    needs = serve_indice(path)
    best = (fv[1], path) if p.is_file() else None
    for ver, q in versioni_locali(p.parent, fv[0]):
        if verificato(q) and (best is None or ver > best[0]):
            if best is not None and needs and not _indice_pronto(q):
                continue
            best = (ver, str(q))
    return best[1] if best else path


def _indice_pronto(path) -> bool:
    from ..biblioteca_indice import pronto
    return pronto(path)


def file_fonte(cfg, fonte: Fonte) -> Path | None:
    """Il file in uso di una fonte: per le quattro della ricerca quello che risolve la
    configurazione; per le altre la versione verificata più recente nella cartella."""
    if fonte.attr:
        configured = getattr(cfg, fonte.attr, None)
        if configured:
            got = risolvi_zim(configured)
            if got and Path(got).is_file():
                return Path(got)
    found = [q for _, q in versioni_locali(cartella_biblioteca(cfg), fonte.prefisso)
             if fonte.attr or verificato(q)]
    return found[-1] if found else None


def fonte_attiva(cfg, fonte: Fonte) -> bool:
    """Una fonte in più che la ricerca sa usare (`richiesta`) ed è accesa in
    Config.biblioteca_fonti_extra."""
    return bool(fonte.richiesta) and fonte.prefisso in (
        getattr(cfg, "biblioteca_fonti_extra", None) or ())


def fonti_usate(cfg) -> list[tuple[Fonte, Path]]:
    """Le fonti in più che la ricerca usa: integrate, accese e già scaricate e verificate."""
    out = []
    for f in ALTRE:
        if fonte_attiva(cfg, f):
            p = file_fonte(cfg, f)
            if p is not None:
                out.append((f, p))
    return out


def fonti_scaricate(cfg) -> list[tuple[Fonte, Path]]:
    """Le fonti in più già scaricate e verificate che la ricerca NON usa (non ancora
    integrate, o spente in Config.biblioteca_fonti_extra)."""
    out = []
    for f in ALTRE:
        if fonte_attiva(cfg, f):
            continue
        p = file_fonte(cfg, f)
        if p is not None:
            out.append((f, p))
    return out


def file_indicizzati(cfg, fonti=None) -> list[Path]:
    """I file ZIM in uso che hanno bisogno dell'indice di ricerca (Wikipedia ridotta,
    Vikidia; le fonti in più solo se la ricerca le usa)."""
    out = []
    for fonte in (fonti or CON_INDICE):
        if not fonte.indice or not (fonte.attr or fonte_attiva(cfg, fonte)):
            continue
        p = file_fonte(cfg, fonte)
        if p is not None and p not in out:
            out.append(p)
    return out


def indici_mancanti(cfg, fonti=None) -> list[Path]:
    """I file in uso il cui indice manca, è a metà o è di un'altra versione o file."""
    return [p for p in file_indicizzati(cfg, fonti) if not _indice_pronto(p)]


def candidati_indice(cfg, fonti=None) -> list[Path]:
    """I file a cui preparare l'indice: quelli in uso senza indice e le versioni più nuove
    già verificate che aspettano il loro indice per entrare in uso (aggiornamento a metà)."""
    out = indici_mancanti(cfg, fonti)
    for fonte in (fonti or CON_INDICE):
        current = (file_fonte(cfg, fonte) if fonte.indice and (fonte.attr
                                                                or fonte_attiva(cfg, fonte))
                   else None)
        cv = versione_zim(str(current)) if current else None
        if not cv:
            continue
        newer = [q for ver, q in versioni_locali(current.parent, fonte.prefisso)
                 if ver > cv[1] and verificato(q)]
        # Solo la versione più nuova: indicizzare quelle in mezzo non serve
        if newer and not _indice_pronto(newer[-1]) and newer[-1] not in out:
            out.append(newer[-1])
    return out


def indici_superflui(cfg) -> list[Path]:
    """Gli indici che non servono più: dei file ZIM superati o cancellati, e quelli a metà
    di una costruzione interrotta (più vecchi di un'ora: uno recente può essere in corso)."""
    from ..biblioteca_indice import CARTELLA, SUFFISSO, percorso_indice
    folder = cartella_biblioteca(cfg) / CARTELLA
    if not folder.is_dir():
        return []
    old = {percorso_indice(q) for q in versioni_vecchie(cfg)}
    out = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    import time as _t
    for q in entries:
        if q.name.endswith(SUFFISSO):
            zim = folder.parent / (q.name[:-len(SUFFISSO)] + ".zim")
            if q in old or not zim.exists():
                out.append(q)
        elif q.name.endswith(SUFFISSO + ".tmp"):
            try:
                if _t.time() - q.stat().st_mtime > 3600:
                    out.append(q)
            except OSError:
                pass
    return sorted(out)


def versioni_vecchie(cfg) -> list[Path]:
    """I file ZIM superati: per ogni famiglia, le versioni più vecchie di quella in uso,
    solo se quella in uso è stata verificata dall'installatore (il file nuovo è integro)."""
    out = []
    for fonte in FONTI:
        current = file_fonte(cfg, fonte)
        if current is None or not verificato(current):
            continue
        cv = versione_zim(str(current))
        for ver, q in versioni_locali(current.parent, fonte.prefisso):
            if ver < cv[1]:
                out.append(q)
    return sorted(out)
