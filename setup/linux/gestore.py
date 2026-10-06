#!/usr/bin/env python3
"""
`calliope`: installa, aggiorna, riporta indietro e avvia Calliope su Linux (DGX Spark con
DGX OS, 02/10/2026). Solo libreria standard: gira con il python3 di sistema, prima che
esista un venv, e non dipende dalla versione di Calliope che sta gestendo.

    calliope installa [--sorgente URL|CARTELLA] [--ramo main] [--segui ramo|tag]
                      [--extra documenti,modelli,casa,schermi] [--python 3.12] [--dati CARTELLA]
                      [--senza-servizio]
    calliope aggiorna [--rif TAG|COMMIT] [--controlla]
    calliope torna [VERSIONE] [--con-dati]
    calliope versioni | calliope stato [--dettagli|--json] | calliope extra NOME…
    calliope satellite --abbina CODICE --stanza STANZA | --elenco | --revoca X | --certificato
    calliope schermi [--abbina CODICE --stanza STANZA | --revoca X | --certificato --host IP]
    calliope avvia | ferma | riavvia | log | esegui [argomenti]
    calliope motore whisper|vllm [argomenti]   gli script dei server dei modelli della
                                               versione in uso (setup/linux/motore/)
    calliope sorgente URL

Come è fatta un'installazione (nessun percorso personale nel codice: tutto parte dalla home):

    ~/.local/share/calliope/          il codice, gestito da qui (CALLIOPE_APP)
        repo.git/                     copia «bare» della sorgente (da qui si aggiorna)
        versioni/<data>-<commit>/     una cartella per versione, con il suo .venv di uv
        attuale, precedente           l'id della versione in uso e di quella di prima
        gestione.json                 sorgente, ramo, extra, Python, storia
        backup/<data>-da-<versione>/  memoria.db, speakers.json, calliope.yaml prima di
                                      ogni aggiornamento
    ~/calliope/                       i DATI di questa casa (CALLIOPE_DATI): calliope.yaml,
                                      calliope.locale.yaml, segreti.yaml, dgx.yaml,
                                      memoria.db, speakers.json, registro/, biblioteca/,
                                      voices/, models/, wakeword/modelli/, lavori/
    ~/.local/bin/calliope             questo file
    ~/.config/systemd/user/calliope.service

Calliope gira con la cartella dei dati come cartella di lavoro: tutti i suoi percorsi sono
relativi (principio 3), quindi i dati non stanno mai nella cartella del codice e un
aggiornamento o un ritorno indietro non li tocca.

Aggiornamento (`calliope aggiorna`):
 1. `git fetch` dalla sorgente; il bersaglio è la cima del ramo (predefinito) o l'ultimo
    tag `v*` (`--segui tag`);
 2. il commit si estrae in una cartella **nuova** (`git archive`), e `uv sync --frozen`
    gli crea il suo venv dal lock: la versione in uso resta intatta;
 3. verifica a secco con il Python nuovo: si importano `calliope.main` e
    `calliope.stato`, e `python -m calliope.stato --json` deve rispondere. Se non va, la
    versione nuova si butta e non è cambiato niente;
 4. copia dei dati piccoli (memoria.db con l'API di backup di SQLite), calliope.yaml
    rigenerato dalla versione nuova (resta uguale al file d'esempio, principio 3; se era
    stato cambiato a mano se ne tiene una copia);
 5. cambio del puntatore `attuale` (os.replace: atomico) e riavvio del servizio. L'unità
    è `Type=notify`: `systemctl restart` torna solo quando Calliope ha caricato i modelli e
    detto il saluto (READY=1, `main.notifica_systemd`), o con un errore;
 6. se il riavvio non riesce, o il servizio cade nei secondi dopo, si torna da soli alla
    versione di prima, con i dati copiati al punto 4 (quelli scritti dalla versione
    nuova restano accanto, `memoria.db.dopo-<versione>`).
Il gestore stesso si aggiorna solo dopo un aggiornamento riuscito.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from pathlib import Path

SERVIZIO = "calliope"
EXTRA_PREDEFINITI = ["documenti", "modelli", "casa", "schermi"]
# Dati copiati prima di un cambio di versione e rimessi da «torna --con-dati» o dal ritorno
# automatico. I .db con l'API di backup (coerenti anche a Calliope accesa, WAL compreso);
# archivio.db dal 03/10 (prima restava fuori)
# conversazioni.db dal 05/10 (archivio delle conversazioni)
DATI_PICCOLI = ("memoria.db", "archivio.db", "conversazioni.db", "speakers.json",
                "calliope.yaml")
# I file che SQLite tiene accanto a un database: si spostano sempre insieme a lui
SQLITE_ACCANTO = ("-wal", "-shm", "-journal")
VERSIONI_TENUTE = 3
BACKUP_TENUTI = 5


class Errore(Exception):
    """Un errore da dire così com'è, senza traccia."""


def trova_uv(bin_dir: Path) -> str:
    """uv nel PATH, altrimenti dove lo mette l'installatore ufficiale (~/.local/bin, la
    cartella del gestore). Sulla DGX (02/10) `~/.local/bin/calliope aggiorna` da una shell
    ssh non di login, o da systemd, non aveva ~/.local/bin nel PATH: «comando non trovato:
    uv», mentre installa.sh lo aggiunge da sé."""
    trovato = shutil.which("uv")
    if trovato:
        return trovato
    for cartella in (bin_dir, Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        c = Path(cartella) / ("uv.exe" if os.name == "nt" else "uv")
        if c.is_file():
            return str(c)
    return "uv"


def _ora() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _scrivi_atomico(path: Path, testo: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(testo, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


class Gestore:
    def __init__(self, app: Path, dati: Path | None = None, bin_dir: Path | None = None,
                 unit_dir: Path | None = None, uv=None, git=None, systemctl=None,
                 journalctl=None, out=print, attesa_stabile_s: float = 5.0):
        self.app = Path(app)
        self.repo = self.app / "repo.git"
        self.versioni = self.app / "versioni"
        self.backup = self.app / "backup"
        self.f_imp = self.app / "gestione.json"
        self.f_attuale = self.app / "attuale"
        self.f_precedente = self.app / "precedente"
        self.bin_dir = Path(bin_dir) if bin_dir else Path.home() / ".local" / "bin"
        self.unit_dir = (Path(unit_dir) if unit_dir
                         else Path.home() / ".config" / "systemd" / "user")
        self.uv = list(uv or [trova_uv(self.bin_dir)])
        self.git = list(git or ["git"])
        self.systemctl = list(systemctl or ["systemctl", "--user"])
        self.journalctl = list(journalctl or ["journalctl", "--user"])
        self.out = out
        self.attesa_stabile_s = attesa_stabile_s
        self.imp = self._leggi_impostazioni()
        self._dati = Path(dati) if dati else None

    # ── impostazioni e puntatori ──
    def _leggi_impostazioni(self) -> dict:
        try:
            return json.loads(self.f_imp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salva_impostazioni(self):
        _scrivi_atomico(self.f_imp, json.dumps(self.imp, ensure_ascii=False, indent=2) + "\n")

    @property
    def dati(self) -> Path:
        if self._dati:
            return self._dati
        if self.imp.get("dati"):
            return Path(self.imp["dati"])
        return Path(os.environ.get("CALLIOPE_DATI") or Path.home() / "calliope")

    def attuale(self) -> str | None:
        try:
            return self.f_attuale.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def precedente(self) -> str | None:
        try:
            return self.f_precedente.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def _attiva(self, vid: str):
        """Cambia la versione in uso: un file scritto e rinominato (atomico), niente
        collegamenti simbolici (l'unità systemd passa da `calliope esegui`)."""
        vecchia = self.attuale()
        if vecchia and vecchia != vid:
            _scrivi_atomico(self.f_precedente, vecchia + "\n")
        _scrivi_atomico(self.f_attuale, vid + "\n")

    def _storia(self, **voce):
        self.imp.setdefault("storia", []).append({"quando": _ora(), **voce})
        self.imp["storia"] = self.imp["storia"][-50:]
        self._salva_impostazioni()

    # ── comandi esterni ──
    def _run(self, cmd, cwd=None, env=None, timeout=None, check=True, capture=True,
             input_bytes=None) -> subprocess.CompletedProcess:
        try:
            r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, timeout=timeout,
                               input=input_bytes, capture_output=capture)
        except FileNotFoundError:
            raise Errore(f"comando non trovato: {cmd[0]}") from None
        except subprocess.TimeoutExpired:
            raise Errore(f"tempo scaduto: {' '.join(map(str, cmd[:3]))}…") from None
        if check and r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            raise Errore(f"{' '.join(map(str, cmd[:3]))} non è riuscito"
                         + (f": {err[-1]}" if err else ""))
        return r

    def _git(self, *args, **kw) -> str:
        r = self._run(self.git + ["--git-dir", str(self.repo), *args], **kw)
        return (r.stdout or b"").decode("utf-8", "replace").strip()

    # ── versioni ──
    def cartella(self, vid: str) -> Path:
        return self.versioni / vid

    def python_di(self, cartella: Path) -> Path:
        sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
        return cartella / ".venv" / sub[0] / sub[1]

    def ambiente(self, cartella: Path) -> dict:
        env = dict(os.environ, PYTHONUTF8="1", CALLIOPE_GESTITA="1")
        env.pop("VIRTUAL_ENV", None)
        return env

    def info(self, vid: str) -> dict:
        try:
            return json.loads((self.cartella(vid) / "VERSIONE.json").read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def completa(self, vid: str) -> bool:
        d = self.cartella(vid)
        return (d / "VERSIONE.json").is_file() and not (d / ".incompleta").exists() \
            and (d / ".venv").is_dir()

    def _bersaglio(self, rif: str | None) -> str:
        """Il commit da installare: `rif` (tag, ramo o commit), altrimenti la cima del ramo
        o l'ultimo tag v* (impostazione `segui`)."""
        if rif:
            for cand in (f"refs/tags/{rif}", f"refs/remotes/origin/{rif}", rif):
                try:
                    return self._git("rev-parse", "--verify", "--quiet", cand + "^{commit}")
                except Errore:
                    continue
            raise Errore(f"«{rif}» non c'è nella sorgente")
        if self.imp.get("segui") == "tag":
            tags = self._git("tag", "-l", "v*", "--sort=-v:refname").splitlines()
            if not tags:
                raise Errore("nessun tag v* nella sorgente (oppure: --segui ramo)")
            return self._git("rev-parse", tags[0] + "^{commit}")
        ramo = self.imp.get("ramo") or "main"
        return self._git("rev-parse", f"refs/remotes/origin/{ramo}^{{commit}}")

    def _id_di(self, sha: str) -> str:
        data = self._git("show", "-s", "--format=%cd", "--date=format:%Y%m%d-%H%M", sha)
        return f"{data}-{sha[:8]}"

    def _estrai(self, sha: str, dest: Path):
        """Il commit in una cartella nuova, senza working tree (git archive | tar)."""
        r = self._run(self.git + ["--git-dir", str(self.repo), "archive", "--format=tar",
                                  sha], timeout=300)
        dest.mkdir(parents=True)
        (dest / ".incompleta").write_text(_ora(), encoding="utf-8")
        with tarfile.open(fileobj=__import__("io").BytesIO(r.stdout)) as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(dest, filter="data")
            else:                                          # pragma: no cover
                tar.extractall(dest)
        if not (dest / "pyproject.toml").is_file() or not (dest / "uv.lock").is_file():
            raise Errore("questa versione non ha pyproject.toml e uv.lock: è precedente "
                         "all'impacchettamento del 02/10 e non si installa così")
        desc = self._git("describe", "--tags", "--always", sha)
        info = {"id": dest.name, "commit": sha, "descrizione": desc, "installata": _ora()}
        _scrivi_atomico(dest / "VERSIONE.json", json.dumps(info, indent=2) + "\n")

    def _sync(self, dest: Path):
        """Il venv della versione, dal lock: `uv sync --frozen` (niente risoluzione nuova,
        stesse versioni provate su Windows)."""
        cmd = self.uv + ["sync", "--frozen", "--no-dev", "--python",
                         self.imp.get("python") or "3.12"]
        for e in self.imp.get("extra") or []:
            cmd += ["--extra", e]
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)
        env.pop("UV_PROJECT_ENVIRONMENT", None)
        self.out("  ambiente Python (uv sync)…")
        self._run(cmd, cwd=dest, env=env, timeout=1800)

    def verifica(self, dest: Path) -> tuple[bool, str]:
        """Prova a secco della versione con i dati veri, prima di usarla."""
        py = self.python_di(dest)
        env = self.ambiente(dest)
        self.dati.mkdir(parents=True, exist_ok=True)
        try:
            r = self._run([py, "-c", "import calliope.main, calliope.stato"], cwd=self.dati,
                          env=env, timeout=300, check=False)
        except Errore as e:
            return False, str(e)
        if r.returncode != 0:
            righe = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            return False, "non si importa: " + (righe[-1] if righe else "errore")
        try:
            r = self._run([py, "-m", "calliope.stato", "--json"], cwd=self.dati, env=env,
                          timeout=180, check=False)
            stato = json.loads((r.stdout or b"").decode("utf-8", "replace"))
        except (Errore, ValueError) as e:
            return False, f"il registro delle capacità non risponde ({e})"
        if r.returncode != 0:
            return False, "python -m calliope.stato è uscito con un errore"
        return True, stato.get("riassunto", "")

    def _config(self, dest: Path):
        """calliope.yaml rigenerato dalla versione (principio 3). Se era stato cambiato a
        mano rispetto all'ultimo scritto da qui, se ne tiene una copia: i valori di casa
        vanno in calliope.locale.yaml."""
        f = self.dati / "calliope.yaml"
        if f.is_file() and self.imp.get("config_sha") and _sha(f) != self.imp["config_sha"]:
            copia = f.with_name(f"calliope.yaml.{datetime.datetime.now():%Y%m%d-%H%M%S}.bak")
            shutil.copy2(f, copia)
            self.out(f"  calliope.yaml era stato cambiato a mano: copia in {copia.name} "
                     f"(i valori di casa vanno in calliope.locale.yaml)")
        self._run([self.python_di(dest), "-m", "calliope.config", "--esempio", "--scrivi",
                   f], cwd=self.dati, env=self.ambiente(dest), timeout=120)
        self.imp["config_sha"] = _sha(f)
        self._salva_impostazioni()

    def _locale_esempio(self, dest: Path):
        f = self.dati / "calliope.locale.yaml"
        esempio = dest / "setup" / "linux" / "calliope.locale.esempio.yaml"
        if not f.exists() and esempio.is_file():
            shutil.copy2(esempio, f)
            self.out(f"  creato {f} dall'esempio per la DGX: rivedilo")

    # ── dati ──
    def istantanea(self, da: str | None) -> Path | None:
        """Copia dei dati piccoli prima di un cambio di versione. memoria.db con l'API di
        backup di SQLite: copia coerente anche con Calliope accesa."""
        presenti = [n for n in DATI_PICCOLI if (self.dati / n).is_file()]
        if not presenti:
            return None
        ora = f"{datetime.datetime.now():%Y%m%d-%H%M%S}"
        dest = self.backup / f"{ora}-da-{da or 'nessuna'}"
        n = 1
        while dest.exists():
            # Due cambi nello stesso secondo (sulla DGX la prova del gestore ci riesce):
            # «.1» viene dopo «-da» nell'ordine dei nomi, e il nome finisce ancora con
            # «-da-<versione>» per `torna --con-dati`
            dest = self.backup / f"{ora}.{n}-da-{da or 'nessuna'}"
            n += 1
        dest.mkdir(parents=True)
        for n in presenti:
            src = self.dati / n
            if n.endswith(".db"):
                a, b = sqlite3.connect(src, timeout=30), sqlite3.connect(dest / n)
                try:
                    a.backup(b)
                finally:
                    a.close()
                    b.close()
            else:
                shutil.copy2(src, dest / n)
        vecchi = sorted(p for p in self.backup.iterdir() if p.is_dir())[:-BACKUP_TENUTI]
        for p in vecchi:
            shutil.rmtree(p, ignore_errors=True)
        return dest

    def ripristina(self, copia: Path, perche: str):
        """Rimette i dati di `copia`; quelli di adesso restano accanto (.dopo-<perche>).

        Dal 03/10 (analisi di robustezza): prima si ferma il servizio (una versione che non
        parte resta in auto-restart, e un'istanza in partenza poteva aprire memoria.db mentre
        lo si copiava); ogni file si copia in un temporaneo e si mette al suo posto con
        os.replace (mai un file a metà); i file accanto a un database (-wal, -shm, -journal)
        vanno via insieme a lui: un journal caldo della versione nuova lasciato accanto al
        database ripristinato SQLite lo riapplicherebbe al file sbagliato, rovinandolo."""
        self.ferma_servizio()
        for n in DATI_PICCOLI:
            src = copia / n
            if not src.is_file():
                continue
            cur = self.dati / n
            tmp = cur.with_name(f"{n}.ripristino.tmp")
            shutil.copy2(src, tmp)
            with open(tmp, "rb+") as f:
                os.fsync(f.fileno())
            dopo = cur.with_name(f"{n}.dopo-{perche}")
            if cur.exists():
                os.replace(cur, dopo)
            for suff in SQLITE_ACCANTO:
                acc = cur.with_name(n + suff)
                if acc.exists():
                    os.replace(acc, dopo.with_name(dopo.name + suff))
            os.replace(tmp, cur)

    def ferma_servizio(self):
        """Ferma Calliope (anche se è in auto-restart) prima di toccare i suoi dati."""
        try:
            self._run(self.systemctl + ["stop", SERVIZIO], check=False, timeout=60)
        except Errore as e:
            self.out(f"  servizio non fermato ({e}): proseguo")

    # ── servizio ──
    def servizio_attivo(self) -> bool:
        try:
            r = self._run(self.systemctl + ["is-active", SERVIZIO], check=False, timeout=30)
        except Errore:
            return False
        return (r.stdout or b"").decode().strip() == "active"

    def riavvia_e_controlla(self) -> tuple[bool, str]:
        """Riavvio con Type=notify: torna quando Calliope è pronta (o fallisce); poi
        qualche secondo per vedere che non cada subito."""
        self.out("  riavvio di Calliope (attendo che carichi i modelli)…")
        try:
            r = self._run(self.systemctl + ["restart", SERVIZIO], check=False, timeout=420)
        except Errore as e:
            return False, str(e)
        if r.returncode != 0:
            return False, "il servizio non è partito"
        time.sleep(self.attesa_stabile_s)
        if not self.servizio_attivo():
            return False, "il servizio è caduto subito dopo l'avvio"
        return True, ""

    def installa_unita(self, dest: Path, abilita: bool):
        mod = dest / "setup" / "linux" / "calliope.service"
        if not mod.is_file():
            return
        testo = (mod.read_text(encoding="utf-8")
                 .replace("@GESTORE@", str(self.bin_dir / "calliope"))
                 .replace("@DATI@", str(self.dati)))
        _scrivi_atomico(self.unit_dir / "calliope.service", testo)
        try:
            self._run(self.systemctl + ["daemon-reload"], timeout=60)
            if abilita:
                self._run(self.systemctl + ["enable", SERVIZIO], timeout=60)
        except Errore as e:
            self.out(f"  systemd utente non disponibile ({e}): il servizio si attiva dopo")

    def installa_gestore(self, dest: Path):
        """Questo file in ~/.local/bin/calliope: solo da una versione verificata."""
        src = dest / "setup" / "linux" / "gestore.py"
        if not src.is_file():
            return
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        tgt = self.bin_dir / "calliope"
        tmp = tgt.with_name("calliope.tmp")
        shutil.copy2(src, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, tgt)

    # ── pulizia ──
    def pulisci(self):
        tieni = {self.attuale(), self.precedente()}
        if not self.versioni.is_dir():
            return
        tutte = sorted(p.name for p in self.versioni.iterdir() if p.is_dir())
        complete = [v for v in tutte if self.completa(v)]
        for v in complete[::-1]:
            if len(tieni - {None}) >= VERSIONI_TENUTE:
                break
            tieni.add(v)
        for v in tutte:
            if v not in tieni:
                shutil.rmtree(self.cartella(v), ignore_errors=True)

    # ── preparazione di una versione ──
    def prepara(self, sha: str) -> str:
        """Estrae e prepara la versione del commit; restituisce l'id. Non cambia niente
        dell'installazione in uso."""
        vid = self._id_di(sha)
        dest = self.cartella(vid)
        if self.completa(vid):
            self.out(f"  versione {vid} già pronta")
            info = self.info(vid)                 # un tag nuovo cambia la descrizione
            info["descrizione"] = self._git("describe", "--tags", "--always", sha)
            _scrivi_atomico(dest / "VERSIONE.json", json.dumps(info, indent=2) + "\n")
            return vid
        if dest.exists():
            shutil.rmtree(dest)
        try:
            self.out(f"  estraggo {vid}…")
            self._estrai(sha, dest)
            self._sync(dest)
            (dest / ".incompleta").unlink()
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        return vid

    # ── comandi ──
    def installa(self, sorgente: str, ramo="main", segui="ramo", extra=None, python="3.12",
                 servizio=True) -> int:
        if self.repo.exists():
            raise Errore(f"Calliope è già installata in {self.app}: per una versione nuova "
                         f"«calliope aggiorna»")
        self.app.mkdir(parents=True, exist_ok=True)
        self.out(f"Copia della sorgente da {sorgente}…")
        self._run(self.git + ["clone", "--bare", "--quiet", sorgente, str(self.repo)],
                  timeout=600)
        self._git("config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        self._git("fetch", "--quiet", "--tags", "--prune", "origin", timeout=600)
        self.imp.update({"sorgente": sorgente, "ramo": ramo, "segui": segui,
                         "extra": list(EXTRA_PREDEFINITI if extra is None else extra),
                         "python": python, "dati": str(self.dati), "servizio": servizio})
        self._salva_impostazioni()
        sha = self._bersaglio(None)
        vid = self.prepara(sha)
        dest = self.cartella(vid)
        self.dati.mkdir(parents=True, exist_ok=True)
        ok, msg = self.verifica(dest)
        if not ok:
            raise Errore(f"la versione {vid} non supera la verifica: {msg}")
        self._config(dest)
        self._locale_esempio(dest)
        self._attiva(vid)
        self.installa_gestore(dest)
        if servizio:
            self.installa_unita(dest, abilita=True)
        self._storia(azione="installa", a=vid, esito="ok")
        self.out(f"\nCalliope {self.info(vid).get('descrizione', vid)} installata.")
        self.out(f"  dati: {self.dati}")
        self.out(f"  stato: {msg}")
        return 0

    def aggiorna(self, rif: str | None = None, solo_controllo=False) -> int:
        if not self.repo.exists():
            raise Errore("Calliope non è installata qui: prima setup/linux/installa.sh")
        self._git("fetch", "--quiet", "--tags", "--prune", "origin", timeout=600)
        sha = self._bersaglio(rif)
        cur = self.attuale()
        if cur and self.info(cur).get("commit") == sha:
            self.out(f"Calliope è già aggiornata ({self.info(cur).get('descrizione', cur)}).")
            return 0
        desc = self._git("describe", "--tags", "--always", sha)
        if solo_controllo:
            self.out(f"C'è una versione nuova: {desc} (ora {cur or 'nessuna'}). "
                     f"Per installarla: calliope aggiorna")
            return 0
        self.out(f"Aggiornamento a {desc}…")
        vid = self.prepara(sha)
        dest = self.cartella(vid)
        ok, msg = self.verifica(dest)
        if not ok:
            shutil.rmtree(dest, ignore_errors=True)
            self._storia(azione="aggiorna", da=cur, a=vid, esito="verifica fallita",
                         motivo=msg)
            self.out(f"La versione nuova non supera la verifica ({msg}): resta in uso "
                     f"{cur}. Niente è cambiato.")
            return 1
        attivo = self.servizio_attivo()
        prec = self.precedente()
        copia = self.istantanea(cur)
        self._config(dest)
        self._attiva(vid)
        if attivo:
            ok, motivo = self.riavvia_e_controlla()
            if not ok:
                self.out(f"La versione nuova non parte ({motivo}): torno a {cur}.")
                self._torna_a(cur, copia, perche=vid)
                if prec:                     # la versione nuova non conta come «precedente»
                    _scrivi_atomico(self.f_precedente, prec + "\n")
                self._storia(azione="aggiorna", da=cur, a=vid, esito="tornata indietro",
                             motivo=motivo)
                return 1
        self.installa_gestore(dest)
        if self.imp.get("servizio", True):
            self.installa_unita(dest, abilita=False)
        self._storia(azione="aggiorna", da=cur, a=vid, esito="ok")
        self.pulisci()
        self.out(f"Calliope aggiornata a {desc}" + ("" if attivo else
                 " (il servizio non era acceso: «calliope avvia»)") + f". {msg}")
        return 0

    def _torna_a(self, vid: str | None, copia: Path | None, perche: str):
        if not vid:
            return
        if copia is not None:
            self.ripristina(copia, perche)
            self.imp["config_sha"] = _sha(self.dati / "calliope.yaml")
            self._salva_impostazioni()
        else:
            self._config(self.cartella(vid))
        _scrivi_atomico(self.f_attuale, vid + "\n")
        # Si arriva qui solo se il servizio era acceso: si riaccende con la versione di prima
        ok, motivo = self.riavvia_e_controlla()
        if not ok:
            self.out(f"Attenzione: anche la versione {vid} non riparte ({motivo}). "
                     f"Guarda «calliope log».")

    def torna(self, vid: str | None = None, con_dati=False) -> int:
        vid = vid or self.precedente()
        cur = self.attuale()
        if not vid or not self.completa(vid):
            raise Errore("non c'è una versione precedente da usare: «calliope versioni»")
        if vid == cur:
            self.out(f"{vid} è già in uso.")
            return 0
        copia = None
        if con_dati:
            cand = sorted(p for p in self.backup.glob(f"*-da-{vid}") if p.is_dir())
            copia = cand[-1] if cand else None
            if copia is None:
                raise Errore(f"nessuna copia dei dati presa dalla versione {vid}")
        attivo = self.servizio_attivo()
        if copia is None:
            self._config(self.cartella(vid))
        else:
            self.ripristina(copia, perche=cur or "corrente")
        self._attiva(vid)
        if attivo:
            ok, motivo = self.riavvia_e_controlla()
            if not ok:
                self.out(f"La versione {vid} non riparte ({motivo}): guarda «calliope log».")
                self._storia(azione="torna", da=cur, a=vid, esito="non riparte")
                return 1
        self._storia(azione="torna", da=cur, a=vid, esito="ok", con_dati=bool(copia))
        self.out(f"In uso la versione {self.info(vid).get('descrizione', vid)}"
                 + (" con i dati di allora" if copia else "") + ".")
        return 0

    def elenco(self) -> int:
        cur, prec = self.attuale(), self.precedente()
        if not self.versioni.is_dir():
            self.out("Nessuna versione installata.")
            return 0
        for p in sorted(self.versioni.iterdir()):
            if not p.is_dir():
                continue
            i = self.info(p.name)
            segno = "*" if p.name == cur else ("<" if p.name == prec else " ")
            stato = "" if self.completa(p.name) else "  (incompleta)"
            self.out(f"{segno} {p.name}  {i.get('descrizione', '?')}{stato}")
        self.out("\n* in uso   < precedente («calliope torna»)")
        return 0

    def extra(self, nomi: list[str]) -> int:
        cur = self.attuale()
        if not cur:
            raise Errore("Calliope non è installata")
        nuovi = sorted(set(self.imp.get("extra") or []) | set(nomi))
        self.imp["extra"] = nuovi
        self._salva_impostazioni()
        dest = self.cartella(cur)
        self._sync(dest)
        ok, msg = self.verifica(dest)
        self.out(f"Extra: {', '.join(nuovi)}. " + (msg if ok else f"Verifica: {msg}"))
        if ok and self.servizio_attivo():
            self.riavvia_e_controlla()
        return 0 if ok else 1

    def python_attuale(self) -> Path:
        cur = self.attuale()
        if not cur or not self.completa(cur):
            raise Errore("nessuna versione in uso: «calliope installa» o «calliope torna»")
        return self.python_di(self.cartella(cur))

    def motore(self, args: list[str]) -> int:
        """`calliope motore whisper installa`: lo script dei server dei modelli
        (setup/linux/motore/<nome>.sh) della versione in uso, così segue gli aggiornamenti
        senza un clone da tenere allineato a mano."""
        cur = self.attuale()
        if not cur or not self.completa(cur):
            raise Errore("nessuna versione in uso: «calliope installa» o «calliope torna»")
        cartella = self.cartella(cur) / "setup" / "linux" / "motore"
        nomi = sorted(p.stem for p in cartella.glob("*.sh"))
        if not args or args[0] not in nomi:
            raise Errore(f"uso: calliope motore {'|'.join(nomi) or '…'} [argomenti]")
        return subprocess.call(["bash", str(cartella / f"{args[0]}.sh"), *args[1:]])

    def prova_e2e(self, args: list[str]) -> int:
        """`calliope prova-e2e [--aree casa,minori] [--senza-lenti]`: la prova end-to-end
        (prove/e2e/) su una Calliope di prova separata, dalla versione in uso, con i dati in
        ~/calliope-e2e/ e le sue porte; la Calliope vera non si ferma né si tocca. Le
        registrazioni vere le copia solo `python -m prove.e2e.lancia` dal portatile."""
        py = self.python_attuale()
        radice = py.parent.parent.parent
        env = self.ambiente(radice)
        env["PYTHONPATH"] = str(radice)
        return subprocess.call([str(py), "-m", "prove.e2e", "--codice", str(radice), *args],
                               env=env, cwd=str(radice))

    def esegui(self, args: list[str], modulo="calliope"):
        py = self.python_attuale()
        env = self.ambiente(py.parent.parent.parent)
        self.dati.mkdir(parents=True, exist_ok=True)
        os.chdir(self.dati)
        cmd = [str(py), "-m", modulo, *args]
        if os.name == "nt":                                   # pragma: no cover
            return subprocess.call(cmd, env=env)
        os.execve(str(py), cmd, env)                          # systemd vede Python


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="calliope", description="Gestione di Calliope su Linux")
    sub = p.add_subparsers(dest="cmd")
    i = sub.add_parser("installa", help="prima installazione")
    i.add_argument("--sorgente", required=True)
    i.add_argument("--ramo", default="main")
    i.add_argument("--segui", choices=("ramo", "tag"), default="ramo")
    i.add_argument("--extra", default=",".join(EXTRA_PREDEFINITI))
    i.add_argument("--python", default="3.12")
    i.add_argument("--dati")
    i.add_argument("--senza-servizio", action="store_true")
    a = sub.add_parser("aggiorna", help="installa l'ultima versione, con ritorno automatico")
    a.add_argument("--rif")
    a.add_argument("--controlla", action="store_true")
    t = sub.add_parser("torna", help="torna alla versione precedente (o a quella data)")
    t.add_argument("versione", nargs="?")
    t.add_argument("--con-dati", action="store_true")
    sub.add_parser("versioni")
    e = sub.add_parser("extra", help="aggiunge extra (documenti, casa, schermi…)")
    e.add_argument("nomi", nargs="+")
    s = sub.add_parser("sorgente", help="cambia da dove si aggiorna")
    s.add_argument("url")
    for nome in ("avvia", "ferma", "riavvia", "log"):
        sub.add_parser(nome)
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    app = Path(os.environ.get("CALLIOPE_APP")
               or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
               / "calliope")
    # Comandi che passano gli argomenti a Calliope così come sono (satellite: abbinamento e
    # certificato dei satelliti, calliope/satellite/__main__.py, nella cartella dei dati;
    # schermi: elenco, abbinamento e certificato per i telefoni, calliope/schermi/__main__.py)
    moduli = {"esegui": "calliope", "stato": "calliope.stato", "satellite": "calliope.satellite",
              "schermi": "calliope.schermi"}
    if argv and argv[0] in moduli:
        g = Gestore(app)
        try:
            return g.esegui(argv[1:], modulo=moduli[argv[0]]) or 0
        except Errore as e:
            print(f"Errore: {e}", file=sys.stderr)
            return 1
    if argv and argv[0] == "prova-e2e":
        try:
            return Gestore(app).prova_e2e(argv[1:])
        except Errore as e:
            print(f"Errore: {e}", file=sys.stderr)
            return 1
    if argv and argv[0] == "motore":
        try:
            return Gestore(app).motore(argv[1:])
        except Errore as e:
            print(f"Errore: {e}", file=sys.stderr)
            return 1
    args = _parser().parse_args(argv)
    if not args.cmd:
        _parser().print_help()
        return 0
    g = Gestore(app, dati=Path(args.dati).expanduser().resolve()
                if getattr(args, "dati", None) else None)
    try:
        if args.cmd == "installa":
            extra = [x.strip() for x in args.extra.split(",") if x.strip()]
            return g.installa(args.sorgente, args.ramo, args.segui, extra, args.python,
                              servizio=not args.senza_servizio)
        if args.cmd == "aggiorna":
            return g.aggiorna(args.rif, solo_controllo=args.controlla)
        if args.cmd == "torna":
            return g.torna(args.versione, con_dati=args.con_dati)
        if args.cmd == "versioni":
            return g.elenco()
        if args.cmd == "extra":
            return g.extra(args.nomi)
        if args.cmd == "sorgente":
            g._git("remote", "set-url", "origin", args.url)
            g.imp["sorgente"] = args.url
            g._salva_impostazioni()
            print(f"Sorgente: {args.url}")
            return 0
        if args.cmd == "log":
            return subprocess.call(g.journalctl + ["-u", SERVIZIO, "-f", "-n", "100"])
        verbo = {"avvia": "start", "ferma": "stop", "riavvia": "restart"}[args.cmd]
        return subprocess.call(g.systemctl + [verbo, SERVIZIO])
    except Errore as e:
        print(f"Errore: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
