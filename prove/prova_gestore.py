"""
Prova a secco del gestore di Linux (setup/linux/gestore.py, 02/10/2026): installazione,
aggiornamento, verifica che rifiuta una versione rotta, ritorno automatico quando la
versione nuova non riparte, ritorno a mano, dati fuori dalla cartella del codice.

Gira anche su Windows: un repository git vero in una cartella temporanea con un progetto
finto (calliope/main.py, stato.py, config.py minimi), uv finto (crea solo .venv) e
systemctl finto (un file di stato; «restart» fallisce se la versione in uso ha il segno
ROTTA_AL_RIAVVIO, come un Calliope che non arriva a READY=1). Il Python di ogni versione è
quello delle prove con PYTHONPATH sulla cartella della versione. Niente rete, niente
systemd vero, niente uv vero.

    python prove/prova_gestore.py
"""

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gestore", RADICE / "setup/linux/gestore.py")
gestore = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gestore)

errori = 0


def ok(cond, msg):
    global errori
    print(("ok  " if cond else "ERR ") + msg)
    if not cond:
        errori += 1


UV_FINTO = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
assert args[0] == "sync" and "--frozen" in args, args
extra = [args[i + 1] for i, a in enumerate(args) if a == "--extra"]
Path(".venv").mkdir(exist_ok=True)
Path(".venv/extra.json").write_text(json.dumps(extra))
'''

SYSTEMCTL_FINTO = r'''
import os, sys
from pathlib import Path
stato = Path(os.environ["FINTO_STATO"])
app = Path(os.environ["FINTO_APP"])
args = [a for a in sys.argv[1:] if a != "--user"]
with open(stato / "log.txt", "a") as f:
    f.write(" ".join(args) + "\n")
if args[0] == "is-active":
    print("active" if (stato / "attivo").exists() else "inactive")
    sys.exit(0 if (stato / "attivo").exists() else 3)
if args[0] == "restart":
    vid = (app / "attuale").read_text().strip()
    if (app / "versioni" / vid / "ROTTA_AL_RIAVVIO").exists():
        (stato / "attivo").unlink(missing_ok=True)
        sys.exit(1)
    (stato / "attivo").write_text(vid)
sys.exit(0)
'''

STATO = 'import json\nif __name__ == "__main__":\n    print(json.dumps({"riassunto": "tutto bene"}))\n'
CONFIG = r'''
import sys
VERSIONE = "{v}"
if __name__ == "__main__" and "--scrivi" in sys.argv:
    open(sys.argv[sys.argv.index("--scrivi") + 1], "w").write("versione: " + VERSIONE + "\n")
'''


class GestoreProva(gestore.Gestore):
    """Il Python di una versione è quello delle prove, con la versione nel PYTHONPATH."""

    def python_di(self, cartella):
        return Path(sys.executable)

    def ambiente(self, cartella):
        env = super().ambiente(cartella)
        env["PYTHONPATH"] = str(cartella)
        return env


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    tmp = Path(tempfile.mkdtemp(prefix="calliope-gestore-"))
    try:
        prova(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto a posto." if not errori else f"\n{errori} errori.")
    return 1 if errori else 0


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="prova", GIT_AUTHOR_EMAIL="prova@example.invalid",
               GIT_COMMITTER_NAME="prova", GIT_COMMITTER_EMAIL="prova@example.invalid")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=env, text=True).stdout.strip()


def versione(repo: Path, v: str, main_py="VERSIONE = 1\n", rotta=False):
    (repo / "calliope").mkdir(exist_ok=True)
    (repo / "calliope/__init__.py").write_text("")
    (repo / "calliope/main.py").write_text(main_py)
    (repo / "calliope/stato.py").write_text(STATO)
    (repo / "calliope/config.py").write_text(CONFIG.replace("{v}", v))
    (repo / "pyproject.toml").write_text('[project]\nname = "calliope"\n')
    (repo / "uv.lock").write_text("version = 1\n")
    s = repo / "setup/linux"
    s.mkdir(parents=True, exist_ok=True)
    for f in ("gestore.py", "calliope.service", "calliope.locale.esempio.yaml"):
        shutil.copy2(RADICE / "setup/linux" / f, s / f)
    segno = repo / "ROTTA_AL_RIAVVIO"
    if rotta:
        segno.write_text("x")
    elif segno.exists():
        segno.unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"versione {v}")
    return git(repo, "rev-parse", "HEAD")


def memoria(dati: Path, valore: str | None = None) -> str:
    with sqlite3.connect(dati / "memoria.db") as c:
        c.execute("create table if not exists t (v text)")
        if valore is not None:
            c.execute("delete from t")
            c.execute("insert into t values (?)", (valore,))
        r = c.execute("select v from t").fetchone()
    c.close()
    return r[0] if r else ""


def prova(tmp: Path):
    repo, app, dati = tmp / "sorgente", tmp / "app", tmp / "dati"
    stato, bin_dir, unit = tmp / "stato", tmp / "bin", tmp / "unit"
    for d in (repo, stato):
        d.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (tmp / "uv_finto.py").write_text(UV_FINTO)
    (tmp / "systemctl_finto.py").write_text(SYSTEMCTL_FINTO)
    os.environ.update(FINTO_STATO=str(stato), FINTO_APP=str(app))
    righe = []

    def nuovo():
        return GestoreProva(app, dati=dati, bin_dir=bin_dir, unit_dir=unit,
                            uv=[sys.executable, tmp / "uv_finto.py"],
                            systemctl=[sys.executable, tmp / "systemctl_finto.py", "--user"],
                            out=righe.append, attesa_stabile_s=0.05)

    def log():
        p = stato / "log.txt"
        return p.read_text() if p.exists() else ""

    # 1. Installazione
    versione(repo, "1")
    g = nuovo()
    rc = g.installa(str(repo), extra=["documenti", "casa"])
    v1 = g.attuale()
    ok(rc == 0 and v1 and g.completa(v1), f"installazione: versione {v1}")
    ok((dati / "calliope.yaml").read_text() == "versione: 1\n",
       "calliope.yaml generato dalla versione installata, nella cartella dei dati")
    ok((dati / "calliope.locale.yaml").is_file(), "calliope.locale.yaml creato dall'esempio")
    ok(not any(app.rglob("calliope.locale.yaml")) and not (app / "memoria.db").exists(),
       "nessun dato dell'utente nella cartella del codice")
    extra = json.loads((g.cartella(v1) / ".venv/extra.json").read_text())
    ok(extra == ["documenti", "casa"], f"uv sync --frozen con gli extra scelti ({extra})")
    ok((bin_dir / "calliope").is_file(), "comando calliope installato")
    u = (unit / "calliope.service").read_text(encoding="utf-8")
    ok("@" not in u.split("[Unit]")[1] and str(dati) in u and "Type=notify" in u,
       "unità systemd con la cartella dei dati e Type=notify")
    ok("Wants=calliope-whisper.service" in u and "After=calliope-whisper.service" in u,
       "unità: aspetta il server di trascrizione (Wants/After calliope-whisper), anche dopo "
       "un aggiornamento che la riscrive")
    try:
        g.motore(["inesistente"])
        ok(False, "calliope motore con uno script che non c'è va rifiutato")
    except gestore.Errore as e:
        ok("uso: calliope motore" in str(e), f"calliope motore: script sconosciuto rifiutato ({e})")
    ok("enable calliope" in log(), "servizio abilitato")
    try:
        g.installa(str(repo))
        ok(False, "una seconda installazione va rifiutata")
    except gestore.Errore:
        ok(True, "una seconda installazione è rifiutata (si usa aggiorna)")

    # Il servizio è acceso e ci sono dati
    (stato / "attivo").write_text(v1)
    memoria(dati, "a")
    (dati / "speakers.json").write_text("[]")

    # 2. Niente di nuovo
    righe.clear()
    ok(nuovo().aggiorna() == 0 and any("già aggiornata" in r for r in righe),
       "aggiorna senza commit nuovi: già aggiornata")

    # 3. Versione che non si importa: rifiutata, niente cambia
    versione(repo, "2", main_py="def (:\n")
    g = nuovo()
    righe.clear()
    rc = g.aggiorna()
    ok(rc == 1 and g.attuale() == v1, "versione con un errore di sintassi: rifiutata, resta v1")
    ok(len([p for p in (app / "versioni").iterdir()]) == 1, "la versione rotta non resta su disco")
    ok("restart" not in log(), "nessun riavvio per una versione che non passa la verifica")
    ok(g.imp["storia"][-1]["esito"] == "verifica fallita", "nella storia: verifica fallita")

    # 4. Versione buona
    versione(repo, "3")
    g = nuovo()
    rc = g.aggiorna()
    v3 = g.attuale()
    ok(rc == 0 and v3 != v1 and g.precedente() == v1, f"aggiornata a {v3}, precedente v1")
    ok((dati / "calliope.yaml").read_text() == "versione: 3\n", "calliope.yaml rigenerato")
    ok("restart calliope" in log(), "servizio riavviato")
    copie = sorted((app / "backup").glob(f"*-da-{v1}"))
    ok(copie and memoria_in(copie[-1]) == "a", "copia dei dati prima dell'aggiornamento")
    ok(memoria(dati) == "a", "i dati restano dopo l'aggiornamento")
    ok((bin_dir / "calliope").read_bytes()
       == (g.cartella(v3) / "setup/linux/gestore.py").read_bytes(),
       "comando calliope preso dalla versione nuova, solo dopo l'aggiornamento riuscito")

    # 5. Versione che non riparte: ritorno automatico
    memoria(dati, "b")
    versione(repo, "4", rotta=True)
    g = nuovo()
    righe.clear()
    rc = g.aggiorna()
    ok(rc == 1 and g.attuale() == v3, "la versione 4 non riparte: si torna da soli a v3")
    ok(g.precedente() == v1, "dopo il ritorno la precedente resta v1")
    ok((stato / "attivo").exists(), "servizio di nuovo acceso con v3")
    ok((dati / "calliope.yaml").read_text() == "versione: 3\n", "calliope.yaml di v3")
    ok(memoria(dati) == "b" and list(dati.glob("memoria.db.dopo-*")),
       "dati di prima rimessi, quelli della versione nuova tenuti accanto")
    ok(g.imp["storia"][-1]["esito"] == "tornata indietro", "nella storia: tornata indietro")

    # 6. Ritorno a mano
    rc = nuovo().torna()
    g = nuovo()
    ok(rc == 0 and g.attuale() == v1 and g.precedente() == v3, "calliope torna: v1 in uso")
    ok((dati / "calliope.yaml").read_text() == "versione: 1\n", "calliope.yaml di v1")
    ok(memoria(dati) == "b", "torna senza --con-dati non tocca la memoria")

    # 7. calliope.yaml cambiato a mano: copia, poi rigenerato
    (dati / "calliope.yaml").write_text("versione: a mano\n")
    versione(repo, "5")
    g = nuovo()
    rc = g.aggiorna()
    v5 = g.attuale()
    ok(rc == 0 and list(dati.glob("calliope.yaml.*.bak")),
       "calliope.yaml cambiato a mano: tenuta una copia .bak")
    ok((dati / "calliope.yaml").read_text() == "versione: 5\n", "e rigenerato")

    # 8. Ritorno con i dati di allora
    memoria(dati, "z")
    rc = nuovo().torna(v1, con_dati=True)
    ok(rc == 0 and nuovo().attuale() == v1 and memoria(dati) == "b",
       "torna --con-dati: la memoria com'era quando si è lasciata v1")

    # 9. Pulizia e aggiornamento a un tag
    git(repo, "tag", "v9.0")
    versione(repo, "6")
    g = nuovo()
    g.imp["segui"] = "tag"
    ok(g.aggiorna() == 0 and g.info(g.attuale())["descrizione"] == "v9.0",
       "con segui=tag si installa l'ultimo tag v*, non la cima del ramo")
    ok(len(list((app / "versioni").iterdir())) <= gestore.VERSIONI_TENUTE,
       f"al più {gestore.VERSIONI_TENUTE} versioni su disco")
    righe.clear()
    nuovo().elenco()
    ok(any(r.startswith("* ") for r in righe) and any(r.startswith("< ") for r in righe),
       "calliope versioni segna quella in uso e la precedente")
    ok(v5 != v1, "id delle versioni diversi")

    # 10a. uv fuori dal PATH (DGX, 02/10: `~/.local/bin/calliope aggiorna` da una shell
    # non di login diceva «comando non trovato: uv»): si trova accanto al gestore
    finto_uv = bin_dir / ("uv.exe" if os.name == "nt" else "uv")
    finto_uv.write_text("")
    path = os.environ.get("PATH", "")
    try:
        os.environ["PATH"] = str(tmp / "vuota")
        trovato = gestore.trova_uv(bin_dir)
    finally:
        os.environ["PATH"] = path
        finto_uv.unlink()
    ok(trovato == str(finto_uv), f"uv fuori dal PATH trovato accanto al gestore ({trovato})")

    # 10. Due istantanee nello stesso secondo (sulla DGX la prova arrivava a farlo e
    # aggiorna cadeva con FileExistsError, 02/10)
    g = nuovo()
    a, b = g.istantanea("vx"), g.istantanea("vx")
    ok(a and b and a != b and a.is_dir() and b.is_dir() and b.name.endswith("-da-vx")
       and sorted([b.name, a.name]) == [a.name, b.name],
       f"due istantanee nello stesso secondo: cartelle diverse e in ordine ({a.name}, {b.name})")

    lavori_in_corso(nuovo, righe, repo, stato, dati, log)


def scrivi_lavori(dati: Path, righe: list, pid: int | None = None):
    """Lo stato dei lavori come lo scrive Calliope (calliope/agenti/ripresa.py)."""
    f = dati / gestore.FILE_LAVORI
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"versione": 1, "pid": os.getpid() if pid is None else pid,
                             "lavori": righe}), encoding="utf-8")


def lavori_in_corso(nuovo, righe, repo, stato, dati, log):
    """11. Lavori dell'agente in corso (06/10, caso vero della DGX: un aggiorna alle 17:07 ha
    ucciso in silenzio il lavoro «gioco memory» partito alle 16:56)."""
    import threading
    import time
    g = nuovo()
    g.imp["segui"] = "ramo"            # la 9 l'aveva messo a «tag»
    g._salva_impostazioni()
    (stato / "attivo").write_text(g.attuale())
    gioco = {"id": "L2", "titolo": "gioco memory da giocare sullo schermo", "stato": "in_corso",
             "persona_nome": "Mario", "inizio": time.time() - 660}
    scrivi_lavori(dati, [gioco])
    versione(repo, "7")
    g = nuovo()
    g.interattivo = lambda: False
    prima, restart_prima = g.attuale(), log().count("restart")
    righe.clear()
    rc = g.aggiorna()
    testo = "\n".join(righe)
    ok(rc == gestore.RINVIATO and g.attuale() == prima and log().count("restart") == restart_prima,
       f"aggiorna senza terminale con un lavoro in corso: non procede (uscita {rc}), nessun "
       f"riavvio")
    ok("«gioco memory da giocare sullo schermo» di Mario, in corso da 11 minuti" in testo
       and "--attendi-lavori" in testo and "--forza" in testo,
       "dice quale lavoro e come procedere (--attendi-lavori, --forza)")
    ok(g.imp["storia"][-1]["esito"] == "rinviato", "nella storia: rinviato")

    g = nuovo()
    g.interattivo, risposte = (lambda: True), []
    g.chiedi = lambda domanda: (risposte.append(domanda), "n")[1]
    ok(g.aggiorna() == gestore.RINVIATO and g.attuale() == prima and risposte
       and "[s/N]" in risposte[0], "da terminale chiede conferma; «n» → non aggiorna")
    ok(g.riavvia() == gestore.RINVIATO and log().count("restart") == restart_prima,
       "riavvia con un lavoro in corso, «n»: niente riavvio")
    ok(g.torna() == gestore.RINVIATO and g.attuale() == prima,
       "torna con un lavoro in corso, «n»: resta la versione in uso")
    g.chiedi = lambda domanda: "sì"
    ok(g.riavvia() == 0 and log().count("restart") == restart_prima + 1,
       "da terminale «sì»: riavvia")
    restart_prima += 1

    # --attendi-lavori: il lavoro finisce dopo un attimo (Calliope riscrive il file)
    g = nuovo()
    g.giro_lavori_s = 0.05
    t0 = []

    def out(riga):
        righe.append(riga)
        if "aspetto che finiscano" in riga:
            t0.append(time.monotonic())
            threading.Timer(0.3, lambda: scrivi_lavori(dati, [])).start()
    g.out = out
    righe.clear()
    rc = g.aggiorna(attendi_min=1.0)
    ok(rc == 0 and g.attuale() != prima and log().count("restart") == restart_prima + 1
       and t0 and time.monotonic() - t0[0] >= 0.3 and any("finiti: procedo" in r for r in righe),
       "--attendi-lavori: aspetta che il lavoro finisca, poi aggiorna e riavvia")
    v7 = g.attuale()

    # --attendi-lavori con un lavoro che non finisce: dopo il tempo massimo niente cambia
    scrivi_lavori(dati, [gioco, {"id": "L3", "titolo": "relazione", "stato": "in_coda"}])
    versione(repo, "8")
    g = nuovo()
    g.giro_lavori_s = 0.05
    righe.clear()
    rc = g.aggiorna(attendi_min=0.005)
    ok(rc == gestore.RINVIATO and g.attuale() == v7 and any("ancora lavori in corso" in r
                                                            for r in righe),
       "--attendi-lavori oltre il tempo massimo: non aggiorna (uscita 75)")
    ok(any("L3 «relazione», in coda" in r for r in righe), "anche i lavori in coda contano")

    # Un lavoro che aspetta una risposta sopravvive al riavvio: non blocca
    scrivi_lavori(dati, [{"id": "L4", "titolo": "verbale", "stato": "in_attesa"}])
    ok(nuovo().prima_di_fermare("riavvio") is True,
       "un lavoro in attesa di una risposta non blocca (sopravvive al riavvio)")
    # Un file rovinato non blocca
    (dati / gestore.FILE_LAVORI).write_text("{rotto", encoding="utf-8")
    ok(nuovo().prima_di_fermare("riavvio") is True, "file dei lavori rovinato: non blocca")
    if os.name == "posix":
        # Il file lasciato da un'istanza caduta (pid che non c'è più) non conta
        scrivi_lavori(dati, [gioco], pid=2 ** 22 + 12345)
        ok(nuovo().prima_di_fermare("riavvio") is True,
           "file di un processo che non c'è più: non blocca")

    # --forza: aggiorna lo stesso, e lo dice
    scrivi_lavori(dati, [gioco])
    g = nuovo()
    righe.clear()
    rc = g.aggiorna(forza=True)
    ok(rc == 0 and g.attuale() != v7 and any("propone di rifarli" in r for r in righe),
       "--forza: aggiorna interrompendo il lavoro, e dice che Calliope proporrà di rifarlo")
    # Servizio spento: nessun controllo
    (stato / "attivo").unlink()
    ok(nuovo().prima_di_fermare("riavvio") is True, "servizio spento: nessun lavoro da proteggere")
    p = gestore._parser().parse_args(["aggiorna", "--attendi-lavori"])
    ok(p.attendi_lavori == gestore.ATTESA_LAVORI_MIN and not p.forza,
       f"--attendi-lavori senza numero: {gestore.ATTESA_LAVORI_MIN:g} minuti")
    p = gestore._parser().parse_args(["riavvia", "--attendi-lavori", "5", "--forza"])
    ok(p.attendi_lavori == 5.0 and p.forza, "riavvia --attendi-lavori 5 --forza")
    (dati / gestore.FILE_LAVORI).unlink()


def memoria_in(cartella: Path) -> str:
    with sqlite3.connect(cartella / "memoria.db") as c:
        r = c.execute("select v from t").fetchone()
    c.close()
    return r[0] if r else ""


if __name__ == "__main__":
    sys.exit(main())
