"""Parti comuni degli script di prove/arm/ (18/10, #64, revisione della PR #164), a secco.

`prepara(--dati <cartella>)` legge calliope.yaml e calliope.locale.yaml di quella cartella anche
quando l'ambiente indica altri file (CALLIOPE_CONFIG, CALLIOPE_CONFIG_LOCALE: il runner imposta
il secondo); contrari: senza --dati la cartella del codice e il locale lasciato all'ambiente,
cartella assente, --dati senza valore. `memoria()` dà i tre campi numerici.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]

# Il figlio: prepara, poi load_config come gli script; stampa ciò che serve controllare
FIGLIO = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
from prove.arm.comune import memoria, prepara
argv = prepara(sys.argv[1:])[1:]   # sys.argv[1] è la radice del codice
from calliope.config import load_config
cfg = load_config()
print("RISULTATO " + json.dumps(dict(cwd=os.getcwd(), argv=argv, k=cfg.biblioteca_k,
      locale=os.environ.get("CALLIOPE_CONFIG_LOCALE"), config=os.environ.get("CALLIOPE_CONFIG"),
      memoria=memoria())))
"""

errori = 0


def check(cond, msg):
    global errori
    print(("ok  " if cond else "ERR ") + msg)
    errori += not cond


def lancia(args, env_extra, cwd):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CALLIOPE_CONFIG", "CALLIOPE_CONFIG_LOCALE")}
    env.update(env_extra)
    r = subprocess.run([sys.executable, "-c", FIGLIO, str(RADICE), *args], env=env, cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for riga in r.stdout.splitlines():
        if riga.startswith("RISULTATO "):
            return r.returncode, json.loads(riga[len("RISULTATO "):])
    return r.returncode, None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dati, altrove = tmp / "dati", tmp / "altrove"
        dati.mkdir()
        altrove.mkdir()
        (dati / "calliope.yaml").write_text("biblioteca:\n  biblioteca_k: 5\n", encoding="utf-8")
        (dati / "calliope.locale.yaml").write_text("biblioteca:\n  biblioteca_k: 9\n",
                                                   encoding="utf-8")
        (altrove / "calliope.yaml").write_text("biblioteca:\n  biblioteca_k: 2\n",
                                               encoding="utf-8")
        (altrove / "calliope.locale.yaml").write_text("biblioteca:\n  biblioteca_k: 4\n",
                                                      encoding="utf-8")
        sbagliati = {"CALLIOPE_CONFIG": str(altrove / "calliope.yaml"),
                     "CALLIOPE_CONFIG_LOCALE": str(altrove / "calliope.locale.yaml")}

        rc, r = lancia(["x", "--dati", str(dati), "y"], sbagliati, cwd=str(altrove))
        check(rc == 0 and r is not None, f"--dati con l'ambiente che indica altri file: esce 0 ({rc})")
        if r:
            check(Path(r["cwd"]).resolve() == dati.resolve(), "cartella di lavoro: quella dei dati")
            check(r["k"] == 9, f"il locale della cartella dei dati vince (biblioteca_k {r['k']}, atteso 9)")
            check(Path(r["locale"]) == dati.resolve() / "calliope.locale.yaml",
                  "CALLIOPE_CONFIG_LOCALE puntato al file della cartella dei dati")
            check(r["config"] is None, "CALLIOPE_CONFIG tolto dall'ambiente")
            check(r["argv"] == ["x", "y"], f"--dati tolto dagli argomenti ({r['argv']})")
            m = r["memoria"]
            check(set(m) == {"rss_mb", "privata_mb", "picco_mb"}
                  and all(isinstance(v, (int, float)) for v in m.values()),
                  f"memoria(): tre campi numerici ({m})")

        rc, r = lancia(["--dati", str(dati)], {}, cwd=str(altrove))
        check(r is not None and r["k"] == 9, "--dati senza variabili nell'ambiente: stesso esito")

        # Contrari: senza --dati la cartella del codice; il locale dell'ambiente resta
        rc, r = lancia(["x"], {"CALLIOPE_CONFIG_LOCALE": str(altrove / "calliope.locale.yaml")},
                       cwd=str(altrove))
        check(r is not None and Path(r["cwd"]).resolve() == RADICE.resolve()
              and Path(r["locale"]) == altrove / "calliope.locale.yaml",
              "senza --dati: cartella del codice, locale dell'ambiente lasciato com'è")
        rc, r = lancia([], {}, cwd=str(altrove))
        check(r is not None and r["locale"].endswith("nessun-file-locale.yaml"),
              "senza --dati e senza ambiente: niente file locale, come le altre prove")
        rc, r = lancia(["--dati", str(tmp / "manca")], {}, cwd=str(altrove))
        check(rc != 0 and r is None, "cartella dei dati assente: esce con errore")
        rc, r = lancia(["--dati"], {}, cwd=str(altrove))
        check(rc != 0 and r is None, "--dati senza cartella: esce con errore")

    print(f"\n{'OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
