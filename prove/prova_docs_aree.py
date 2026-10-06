"""
I documenti d'area dicono il vero sul codice (06/10, Q8 della seconda analisi,
docs/ricerche/2026-10-06-analisi-2.md § 3.5): nelle tabelle «Moduli» di `docs/aree/*.md` ogni
nome tra backtick della colonna «Dove» deve esistere. La seconda analisi ci ha trovato funzioni
tolte da giorni (`guardrail.valuta_tool`, `sicurezza.needs_guard`, `brain.DOPO_WEB`,
`_guardia_immagini`).

- un percorso (con «/» o un'estensione) deve essere un file del repository, anche relativo
  alla cartella del modulo (`agenti/ciclo.py`, `pagina/`);
- un nome (anche puntato: `modulo.funzione`, `Classe.metodo`) deve essere definito nel codice
  di `calliope/`, `setup/` o `wakeword/`, letto con l'AST: funzioni, classi, assegnazioni
  (anche `self.x = …`), argomenti con nome, campi di Config, nomi dei tool (`ToolSpec(name=…)`
  e quelli dell'agente), chiavi dei dizionari, rotte del server, moduli e pacchetti; o nel
  JavaScript delle pagine (funzioni, classi, costanti); oppure essere tra le ECCEZIONI;
- i nomi con spazi (comandi), le chiavi YAML puntate e i segnaposto non si controllano.

    python prove/prova_docs_aree.py
"""

import ast
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
errori = 0

# Nomi che non sono definizioni Python, con il perché
ECCEZIONI = {
    # tabelle SQLite (nomi nelle stringhe SQL)
    "minori_regole": "tabella SQLite", "avvisi_tutori": "tabella SQLite",
    "compiti_giorno": "tabella SQLite", "meta_schema": "tabella SQLite",
    # eventi della pagina e attributi HTML (JavaScript, non Python)
    "calliope:*": "eventi della pagina (JavaScript)",
    "data-carosello": "attributo HTML della pagina",
    # file fuori da git o generati
    "memoria.db": "file dei dati, fuori da git", "conversazioni.db": "file dei dati",
    "personalita.json": "file dei dati", "contesto.json": "file dei dati",
    "uscite.jsonl": "file dei dati delle estensioni", "CAPACITA.md": "file generato",
    "calliope.yaml": "file di configurazione", "dgx.yaml": "file locale, fuori da git",
    "speakers.json": "file dei dati", "registro/": "cartella dei dati",
    "biblioteca/indici/": "cartella dei dati, fuori da git",
    "~/calliope-motore/": "cartella sulla DGX",
    ".calliope/passo-N.txt": "file creato dall'agente nella cartella del lavoro",
    "calliope_estensione": "modulo del container delle estensioni (estensioni/_ospite.py)",
    "WW_PAROLA": "variabile d'ambiente dell'addestramento (wakeword/parole.py)",
}
PERCORSO = re.compile(r"\.(py|md|yaml|yml|sh|js|json|ps1|service|onnx|svg|txt|css|html|"
                      r"toml|lock|db|jsonl)$")


def definiti() -> set[str]:
    """Tutti i nomi definiti nel codice Python del repository (AST)."""
    nomi: set[str] = set()
    import warnings
    for cartella in ("calliope", "setup", "wakeword"):
        for f in (RADICE / cartella).rglob("*.py"):
            if ".venv" in f.parts:
                continue
            nomi.add(f.stem)
            nomi.update(f.parent.relative_to(RADICE).parts)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")      # escape nelle stringhe di altri file
                    albero = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for n in ast.walk(albero):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    nomi.add(n.name)
                    if not isinstance(n, ast.ClassDef):
                        for a in n.args.args + n.args.kwonlyargs:
                            nomi.add(a.arg)
                elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    bersagli = n.targets if isinstance(n, ast.Assign) else [n.target]
                    for t in bersagli:
                        for x in ast.walk(t):
                            if isinstance(x, ast.Name):
                                nomi.add(x.id)
                            elif isinstance(x, ast.Attribute):
                                nomi.add(x.attr)
                elif isinstance(n, ast.keyword) and n.arg == "name" and isinstance(
                        n.value, ast.Constant) and isinstance(n.value.value, str):
                    nomi.add(n.value.value)               # ToolSpec(name="…")
                elif isinstance(n, ast.Call) and getattr(n.func, "id", "") in (
                        "ToolSpec", "_fn") and n.args and isinstance(n.args[0], ast.Constant):
                    nomi.add(str(n.args[0].value))       # tool di Calliope e dell'agente
                elif isinstance(n, ast.Dict):
                    for k in n.keys:                     # chiavi di RETI, PROFILI_LLM…
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            nomi.add(k.value)
                elif (isinstance(n, ast.Constant) and isinstance(n.value, str)
                      and re.fullmatch(r"/[\w/{}.-]+", n.value)):
                    nomi.add(n.value)                    # rotte del server: «/api/immagine»
    return nomi


def tabelle_moduli(md: Path) -> list[tuple[int, str]]:
    """(riga, testo della colonna «Dove») delle tabelle sotto «## Moduli»."""
    out, dentro = [], False
    for i, r in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        if r.startswith("## "):
            dentro = r.strip().lower().startswith("## moduli")
            continue
        if dentro and r.startswith("|") and not r.startswith("|---"):
            celle = [c.strip() for c in r.strip().strip("|").split("|")]
            if len(celle) >= 3 and celle[0].lower() != "stadio":
                out.append((i, celle[-1]))
    return out


def da_controllare(cella: str) -> list[str]:
    return re.findall(r"`([^`]+)`", cella)


def tracciati() -> list[str]:
    """I file del repository (git ls-files; fuori da git, quelli sul disco)."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(RADICE), "ls-files", "-z"], capture_output=True,
                           timeout=30)
        if r.returncode == 0 and r.stdout:
            return [x for x in r.stdout.decode("utf-8", "replace").split("\0") if x]
    except (OSError, subprocess.SubprocessError):
        pass
    return [p.relative_to(RADICE).as_posix() for p in RADICE.rglob("*") if p.is_file()
            and ".venv" not in p.parts and ".git" not in p.parts]


def nomi_js(files: list[str]) -> set[str]:
    """Gli identificatori delle pagine (JavaScript): funzioni, classi, costanti, metodi."""
    out: set[str] = set()
    pat = re.compile(r"\b(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)|"
                     r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{|"
                     r"\b([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s+)?(?:function|\()", re.M)
    for f in files:
        if f.endswith(".js"):
            try:
                testo = (RADICE / f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in pat.finditer(testo):
                out.update(x for x in m.groups() if x)
    return out


def esiste(nome: str, nomi: set[str], files: list[str]) -> bool:
    nome = nome.strip()
    if nome in ECCEZIONI:
        return True
    if " " in nome or "<" in nome or "=" in nome or nome.startswith("-"):
        return True                                       # comandi, segnaposto, opzioni
    if nome.startswith(("~", "%", "\\")) or re.match(r"[A-Za-z]:", nome):
        return True                                       # cartelle della DGX o di Windows
    if nome.startswith("/") and nome in nomi:
        return True                                       # rotta del server
    p = nome.rstrip("/")
    if "/" in nome or PERCORSO.search(nome):
        # Un percorso, anche relativo alla cartella del modulo (`agenti/ciclo.py`,
        # `pagina/`, `scarica.sh`): un file del repository che finisce così
        if any(f == p or f.endswith("/" + p) or f"/{p}/" in f"/{f}" for f in files):
            return True
        # `tools/spec.serve_la_voce`: modulo con il percorso, poi un nome
        if "/" in p and "." in p.rsplit("/", 1)[1]:
            mod, attr = p.rsplit(".", 1)
            if any(f.endswith(mod + ".py") for f in files) and attr in nomi:
                return True
        return False
    parti = [x for x in re.split(r"[.()]", nome.replace("…", "")) if x]
    return bool(parti) and all(x in nomi for x in parti)


def main() -> int:
    global errori
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    files = tracciati()
    nomi = definiti() | nomi_js(files)
    mancanti = []
    tot = 0
    for md in sorted((RADICE / "docs" / "aree").glob("*.md")):
        for riga, cella in tabelle_moduli(md):
            for nome in da_controllare(cella):
                tot += 1
                if not esiste(nome, nomi, files):
                    mancanti.append(f"{md.name}:{riga}: `{nome}`")
    ok = not mancanti
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} nomi delle tabelle «Moduli» di docs/aree/ ({tot} "
          f"controllati): tutti nel codice" + ("" if ok else "\n    " + "\n    ".join(mancanti)))
    # Il controllo stesso: un nome inventato si trova, uno vero no
    finto = "| x | y | `calliope/brain.py` → `Brain.stream_reply`, `funzione_che_non_esiste` |"
    trovati = [n for n in da_controllare(finto.split("|")[3]) if not esiste(n, nomi, files)]
    ok = trovati == ["funzione_che_non_esiste"]
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} il controllo trova il nome inventato e non quelli veri "
          f"{trovati}")
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
