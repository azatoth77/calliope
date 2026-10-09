"""
Nessun segno di conflitto di git nei file tracciati (09/10).

Il 09/10 un'unione ha lasciato nel CHANGELOG le righe `<<<<<<< HEAD`, `=======`,
`>>>>>>> main`, e il CHANGELOG lo legge `calliope_stato` per dire le novità a voce. Questa
prova, nell'hook (livello 1, sulla copia dell'indice), ferma il commit se un file di testo
tracciato contiene una riga che comincia con sette `<`, sette `>` o è fatta di soli sette
`=` (i segni di git). Prima controlla sé stessa su un testo finto con i casi contrari
(una tabella Markdown, un titolo sottolineato con «=====», una freccia «>>>» in un commento).
"""
import re
import subprocess
import sys
from pathlib import Path

SEGNI = re.compile(r"^(<{7}( .*)?|>{7}( .*)?|={7})\s*$")
TESTO = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".js", ".mjs", ".css", ".html",
         ".sh", ".ps1", ".cmd", ".toml", ".cfg", ".ini", ".tsv", ".csv", ".svg"}


def righe_sospette(testo: str) -> list[int]:
    return [i for i, r in enumerate(testo.splitlines(), 1) if SEGNI.match(r)]


def verifica(nome: str, ok: bool, dettaglio: str = ""):
    print(("ok  " if ok else "NO  ") + nome + (f" — {dettaglio}" if dettaglio and not ok else ""))
    if not ok:
        verifica.errori += 1


verifica.errori = 0

# ── la prova controlla sé stessa ──
finto = "\n".join(["# Titolo", "=======", "| a | b |", "|---|---|", "x >>>>>> y",
                   "<<<<<<< HEAD", "riga", "=======", "altra", ">>>>>>> main", "fine"])
trovate = righe_sospette(finto)
verifica("i tre segni di git trovati nel testo finto", trovate == [2, 6, 8, 10], str(trovate))
verifica("contrari: tabella, freccia nel testo, testo normale",
         not righe_sospette("| a | b |\n|---|---|\nx >>>>>> y\n<<<< corto\n======== otto"))

# ── i file tracciati ──
radice = Path(__file__).resolve().parent.parent
try:
    elenco = subprocess.run(["git", "ls-files", "-z"], cwd=radice, capture_output=True,
                            check=True).stdout.decode("utf-8", "replace").split("\0")
except (OSError, subprocess.CalledProcessError):
    # La copia dell'indice dell'hook non è un repository: lì ci sono solo i file tracciati
    elenco = [str(q.relative_to(radice)).replace("\\", "/") for q in radice.rglob("*")
              if q.is_file() and ".git" not in q.parts and ".venv" not in q.parts]
trovati = []
for nome in elenco:
    if not nome or Path(nome).suffix.lower() not in TESTO or nome == "prove/prova_conflitti.py":
        continue
    p = radice / nome
    try:
        testo = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    for n in righe_sospette(testo):
        trovati.append(f"{nome}:{n}")
verifica("nessun segno di conflitto nei file tracciati", not trovati, ", ".join(trovati[:10]))

if verifica.errori:
    print(f"\n{verifica.errori} controlli non superati.")
    sys.exit(1)
print("\nTutto a posto.")
