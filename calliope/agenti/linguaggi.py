"""
I linguaggi dei programmi dell'agente (04/10/2026): quale immagine della sandbox serve a
ognuno e se c'è.

Python gira nell'immagine di sempre (setup/linux/sandbox/Dockerfile) o, solo per scelta
esplicita, nel motore «processo». Gli altri linguaggi solo in un container, ognuno con la sua
immagine costruita dal repository con versioni fissate (`calliope motore sandbox costruisci
<linguaggio>`): stesse regole d'isolamento, nessun compilatore sull'host. Il C# si compila con
csc dentro il container (calliope/agenti/esegui_cs.sh), senza NuGet e quindi senza rete.

Misure sulla DGX (04/10, in CLAUDE.md): immagine C# 318 MB contro i 974
dell'SDK intero; compilazione ed esecuzione di un programma breve 0,52 s di mediana (Python 0,17).
JavaScript (Node) sarebbe un'altra immagine come questa (node:22-slim, da misurare): non c'è
ancora, e l'agente lo dice.

Chi chiede quali ci sono (l'agente, il registro delle capacità) usa `pronti`: mai dal thread
della voce, perché chiede a Docker (`docker image inspect`, qualche decina di ms).
"""

from dataclasses import dataclass
from pathlib import Path

_SANDBOX = Path(__file__).resolve().parents[2] / "setup" / "linux" / "sandbox"


@dataclass(frozen=True)
class Linguaggio:
    nome: str                 # «python», «csharp»: quello della configurazione e di sandbox.sh
    detto: str                # come si dice: «Python», «C#»
    estensioni: tuple
    dockerfile: Path
    prefisso: str             # nome dell'immagine senza il tag
    # Per il prompt dell'agente: cosa c'è e come si prova
    per_agente: str


LINGUAGGI = {
    "python": Linguaggio(
        "python", "Python", (".py",), _SANDBOX / "Dockerfile", "calliope-sandbox",
        "Python 3.12 con la libreria standard (e openpyxl, python-docx se servono file "
        "Office): file .py, si provano con esegui_python ed esegui_test"),
    "csharp": Linguaggio(
        "csharp", "C#", (".cs",), _SANDBOX / "Dockerfile.dotnet", "calliope-sandbox-dotnet",
        "C# con .NET 10 e la sola libreria di base (niente pacchetti NuGet): file .cs in una "
        "cartella, istruzioni di primo livello o un Main; esegui_csharp compila tutti i .cs "
        "della cartella e lo esegue. Niente esegui_test per il C#: prova il programma con "
        "argomenti noti e controlla l'uscita"),
}


def per_estensione(nome_file: str) -> Linguaggio | None:
    suf = Path(str(nome_file)).suffix.lower()
    return next((lg for lg in LINGUAGGI.values() if suf in lg.estensioni), None)


def immagine(nome: str) -> str | None:
    """«<prefisso>:<prime 12 cifre dello SHA-256 del Dockerfile>», come sandbox.sh."""
    from .sandbox import immagine_predefinita
    lg = LINGUAGGI.get(nome)
    if lg is None:
        return None
    img = immagine_predefinita(lg.dockerfile)
    return img and img.replace("calliope-sandbox:", lg.prefisso + ":", 1)


def scegli(cfg, iso_python, docker=None, timeout: float = 5.0) -> dict:
    """{nome: Isolamento} per i linguaggi di `agenti_linguaggi`. Python è `iso_python` (la
    scelta di sempre); gli altri un container con la loro immagine, solo se il motore di Python
    è Docker (o dove Docker c'è): mai il motore «processo»."""
    from .sandbox import Isolamento, scegli_isolamento
    voluti = [str(x).strip().lower() for x in (getattr(cfg, "agenti_linguaggi", None)
                                               or ["python"])]
    out = {}
    if iso_python is not None:
        out["python"] = iso_python
    for nome in dict.fromkeys(voluti):
        if nome == "python" or nome not in LINGUAGGI:
            continue
        lg = LINGUAGGI[nome]
        img = immagine(nome)
        costruisci = f"calliope motore sandbox costruisci {nome}"
        if iso_python is None or iso_python.motore != "docker" or not iso_python.docker:
            perche = ("su questa macchina il codice non gira in un container"
                      if iso_python is None or iso_python.motore != "docker"
                      else (iso_python.descrizione.split(": ", 1)[-1]))
            out[nome] = Isolamento("docker", f"{lg.detto} non disponibile: {perche}", False,
                                   f"Il {lg.detto} si esegue solo in un container, sul server "
                                   f"con Docker: {costruisci}.", img)
            continue
        iso = scegli_isolamento("docker", img, docker=iso_python.docker, timeout=timeout,
                                posix=True)
        if not iso.pronto:
            iso.passo = f"Per il {lg.detto}: {costruisci}."
            iso.descrizione = f"{lg.detto} non disponibile: " + iso.descrizione.split(": ", 1)[-1]
        out[nome] = iso
    # Node per i test della logica dei giochi (05/10, estensioni/scheda.py): non è un linguaggio
    # dei programmi dell'agente (niente esegui_javascript), solo il container dei *.test.js
    from .sandbox import immagine_node
    img = immagine_node()
    if iso_python is not None and iso_python.motore == "docker" and iso_python.docker and img:
        iso = scegli_isolamento("docker", img, docker=iso_python.docker, timeout=timeout,
                                posix=True)
        if not iso.pronto:
            iso.passo = "Per i test dei giochi: calliope motore sandbox costruisci javascript."
        out["javascript"] = iso
    return out


def pronti(isolamenti: dict | None) -> list[str]:
    """I nomi dei linguaggi che si possono eseguire adesso, nell'ordine di LINGUAGGI."""
    iso = isolamenti or {}
    return [n for n in LINGUAGGI if n in iso and getattr(iso[n], "pronto", False)]


def elenco_detto(nomi) -> str:
    detti = [LINGUAGGI[n].detto for n in nomi if n in LINGUAGGI]
    if not detti:
        return "nessuno"
    return detti[0] if len(detti) == 1 else ", ".join(detti[:-1]) + " e " + detti[-1]
