"""
Il comando unico dal portatile (06/10/2026): copia sulla DGX il codice della prova e le
registrazioni vere scelte in voce_reale.tsv (in `~/calliope-e2e/`, permessi 700/600), lancia
il runner in secondo piano con la versione di Calliope in uso, aspetta e stampa il rapporto.

    python -m prove.e2e.lancia [--aree casa,minori] [--copioni id,…] [--senza-lenti]
                               [--senza-voce-vera] [--non-aspettare] [--stato] [--pulisci]
                               [--stt A|B|B2|C] [--codice-qui]

`--stt` sceglie la variante della trascrizione (07/10, `istanza.VARIANTI_STT`: A correzione
spenta, B parole incerte al modello della voce, B2 frase capita scritta in testa e trattenuta,
C correzione con un tetto di 1 s);
`--codice-qui` prova il package calliope/ di questa cartella (un ramo non ancora installato),
con setup/ (Dockerfile della sandbox), invece di quello della versione in uso, con il venv
della versione.
`--stato` stampa la coda del log di una prova in corso; `--pulisci` ferma un'istanza rimasta e
cancella tutto tranne i risultati. Solo l'OpenSSH di Windows con l'alias della DGX (mai
utenti, indirizzi o chiavi in questo file).
"""
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path

QUI = Path(__file__).resolve().parent
RADICE = QUI.parent.parent
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe" if sys.platform == "win32" else "ssh"
DATI = "calliope-e2e"                 # relativo alla home sulla DGX


def principale() -> Path:
    """La radice del repository principale (in un worktree è un'altra cartella)."""
    r = subprocess.run(["git", "-C", str(RADICE), "rev-parse", "--git-common-dir"],
                       capture_output=True, text=True)
    comune = Path(r.stdout.strip())
    if not comune.is_absolute():
        comune = RADICE / comune
    return comune.resolve().parent


def registrazioni() -> Path:
    """La cartella registrazioni/ del repository principale (fuori da git: in un worktree
    non c'è)."""
    if (RADICE / "registrazioni").is_dir():
        return RADICE / "registrazioni"
    return principale() / "registrazioni"


def _alias() -> str:
    """L'alias SSH della DGX (06/10, pubblicazione: mai scritto qui): CALLIOPE_DGX_ALIAS,
    altrimenti `ssh_alias` di dgx.yaml (fuori da git, accanto a calliope.yaml), altrimenti
    «dgx»."""
    import os
    if os.environ.get("CALLIOPE_DGX_ALIAS"):
        return os.environ["CALLIOPE_DGX_ALIAS"]
    for cartella in (RADICE, principale()):
        f = cartella / "dgx.yaml"
        if f.is_file():
            try:
                import yaml
                dati = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                valore = (dati.get("dgx") or {}).get("ssh_alias")
            except Exception:
                valore = None
            if valore:
                return str(valore)
    return "dgx"


ALIAS = _alias()


AIUTANTI = ("ha_finto.py", "pc_finto.py", "immagini_finte.py", "allegati_finti.py")


def ssh(cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([SSH, "-o", "BatchMode=yes", ALIAS, cmd], **kw)


def copia(voce_vera: bool, codice_qui: bool = False) -> int:
    """Codice della prova e registrazioni in un tar sullo stdin di ssh; con `codice_qui` anche
    il package calliope/ e calliope.yaml di questa cartella, in `codice-calliope/`."""
    p = subprocess.Popen([SSH, "-o", "BatchMode=yes", ALIAS,
                          f"umask 077 && mkdir -p ~/{DATI} && chmod 700 ~/{DATI} && "
                          f"rm -rf ~/{DATI}/codice-e2e ~/{DATI}/voce-reale "
                          f"~/{DATI}/codice-calliope && "
                          f"tar -xf - -C ~/{DATI}"], stdin=subprocess.PIPE)
    n = 0
    with tarfile.open(fileobj=p.stdin, mode="w|") as tar:
        def metti(src: Path, arc: str):
            info = tar.gettarinfo(str(src), arc)
            info.mode = 0o600
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(src, "rb") as f:
                tar.addfile(info, f)
        for d in ("codice-e2e", "codice-e2e/prove", "codice-e2e/prove/e2e"):
            info = tarfile.TarInfo(d)
            info.type, info.mode = tarfile.DIRTYPE, 0o700
            tar.addfile(info)
        for f in QUI.glob("*.py"):
            metti(f, f"codice-e2e/prove/e2e/{f.name}")
        metti(QUI / "voce_reale.tsv", "codice-e2e/prove/e2e/voce_reale.tsv")
        metti(RADICE / "prove" / "__init__.py", "codice-e2e/prove/__init__.py")
        for a in AIUTANTI:
            metti(RADICE / "prove" / a, f"codice-e2e/prove/{a}")
        if codice_qui:
            # Anche setup/ (07/10): la sandbox trova il suo Dockerfile in setup/linux/sandbox
            # accanto al package (agenti/sandbox.py, linguaggi.py) e da lì il nome
            # dell'immagine già costruita; senza, l'istanza non eseguiva il codice dell'agente
            # né le estensioni («manca setup/linux/sandbox/Dockerfile»)
            cartelle = {"codice-calliope"}
            sorgenti = [f for d in ("calliope", "setup") for f in (RADICE / d).rglob("*")]
            sorgenti += [RADICE / n for n in ("pyproject.toml", "uv.lock")
                         if (RADICE / n).is_file()]
            for f in sorted(sorgenti):
                if "__pycache__" in f.parts or not f.is_file():
                    continue
                arc = "codice-calliope/" + f.relative_to(RADICE).as_posix()
                for i in range(1, arc.count("/") + 1):
                    d = "/".join(arc.split("/")[:i])
                    if d not in cartelle:
                        cartelle.add(d)
                        info = tarfile.TarInfo(d)
                        info.type, info.mode = tarfile.DIRTYPE, 0o700
                        tar.addfile(info)
                metti(f, arc)
            metti(RADICE / "calliope.yaml", "codice-calliope/calliope.yaml")
        if voce_vera:
            info = tarfile.TarInfo("voce-reale")
            info.type, info.mode = tarfile.DIRTYPE, 0o700
            tar.addfile(info)
            sys.path.insert(0, str(RADICE))
            from prove.e2e.voci import elenco_reale
            for r in elenco_reale().values():
                src = registrazioni() / r["cartella"] / f"{r['stem']}.wav"
                if src.is_file():
                    metti(src, f"voce-reale/{r['cartella']}__{r['stem']}.wav")
                    n += 1
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("copia sulla DGX non riuscita")
    return n


def comando_runner(args: list[str], codice_qui: bool = False) -> str:
    """Il runner in secondo piano, staccato da ssh: solo il comando finale va in background
    (con «a && b &» la shell intera resterebbe legata al canale di ssh fino alla fine)."""
    v = "~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)"
    if codice_qui:
        args = args + ["--calliope", f"~/{DATI}/codice-calliope"]
    a = " ".join(shlex.quote(x) for x in args)
    src = f"$HOME/{DATI}/codice-calliope" if codice_qui else "$V"
    return (f"V={v}; cd ~/{DATI}/codice-e2e || exit 1; mkdir -p ~/{DATI}/risultati; "
            f"PYTHONPATH=$PWD:{src} setsid nohup $V/.venv/bin/python -u -m prove.e2e "
            f"--codice $V {a} > ~/{DATI}/risultati/ultimo.out 2>&1 < /dev/null & "
            f"sleep 2; echo avviato")


def in_corso() -> bool:
    r = ssh(f"test -f ~/{DATI}/runner.pid && kill -0 $(cat ~/{DATI}/runner.pid) 2>/dev/null "
            f"&& echo si", capture_output=True, text=True)
    return "si" in r.stdout


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--aree", default="")
    ap.add_argument("--copioni", default="")
    ap.add_argument("--senza-lenti", action="store_true")
    ap.add_argument("--senza-voce-vera", action="store_true")
    ap.add_argument("--non-aspettare", action="store_true")
    ap.add_argument("--telefono", action="store_true",
                    help="alla fine anche la pagina del telefono in Edge, da qui (tunnel SSH)")
    ap.add_argument("--tieni", action="store_true", help="lascia l'istanza (per il debug)")
    ap.add_argument("--stato", action="store_true")
    ap.add_argument("--pulisci", action="store_true")
    ap.add_argument("--stt", choices=["A", "B", "B2", "C"], default=None,
                    help="variante della trascrizione: A spenta, B parole incerte al modello, "
                         "B2 frase capita trattenuta, C correzione con tetto 1 s")
    ap.add_argument("--codice-qui", action="store_true",
                    help="prova il package calliope/ di questa cartella (ramo non installato)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if a.stato:
        ssh(f"tail -n 40 ~/{DATI}/risultati/ultimo.out")
        return 0
    if a.pulisci:
        ssh(f"cd ~/{DATI}/codice-e2e 2>/dev/null && V=~/.local/share/calliope/versioni/"
            f"$(cat ~/.local/share/calliope/attuale) && PYTHONPATH=$PWD:$V $V/.venv/bin/python "
            f"-m prove.e2e.istanza --pulisci ~/{DATI}; ls ~/{DATI}")
        return 0
    if in_corso():
        raise SystemExit("una prova è già in corso (--stato per vederla)")
    n = copia(not a.senza_voce_vera, a.codice_qui)
    print(f"Copiati il codice della prova e {n} registrazioni in ~/{DATI}")
    args = []
    if a.aree:
        args += ["--aree", a.aree]
    if a.copioni:
        args += ["--copioni", a.copioni]
    if a.senza_lenti:
        args.append("--senza-lenti")
    if a.tieni:
        args.append("--tieni")
    if a.stt:
        args += ["--stt", a.stt]
    if a.telefono and not a.non_aspettare:
        args += ["--telefono", "600"]
    ssh(comando_runner(args, a.codice_qui))
    if a.non_aspettare:
        return 0
    for _ in range(60):                    # il runner scrive il suo pid appena parte
        if in_corso():
            break
        time.sleep(2)
    visto = 0
    while in_corso():
        time.sleep(30)
        r = ssh(f"tail -n +{visto + 1} ~/{DATI}/risultati/ultimo.out", capture_output=True,
                text=True, encoding="utf-8", errors="replace")
        righe = r.stdout.splitlines()
        visto += len(righe)
        for x in righe:
            print(re.sub(r"/home/[^/\s]+/", "~/", x))
            m = re.search(r"TELEFONO PRONTO porta (\d+)", x)
            if m and a.telefono:
                from prove.e2e import telefono
                telefono.main(int(m.group(1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
