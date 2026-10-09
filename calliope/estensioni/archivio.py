"""
Le estensioni su disco (04/10/2026): versioni, stato, impronte, permessi «sempre».

    <cartella>/indice.json                  stato di tutte (scritto in modo atomico)
    <cartella>/<nome>/v<N>/                 codice, test e manifesto di una versione
    <cartella>/<nome>/dati/                 i dati dell'estensione (solo dalla porta stretta)
    <cartella>/decisioni.jsonl              ogni decisione del guardrail

Una versione approvata è **congelata**: i file diventano di sola lettura e l'impronta SHA-256
(di nomi e contenuti, in ordine) va nell'indice. Prima di ogni esecuzione l'impronta si
ricalcola (`verifica`): se non torna, l'estensione non parte e si disattiva.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import threading
import time
from pathlib import Path

from ..persistenza import leggi_json, scrivi_json

# I file che un'estensione può avere (codice, test, manifesto, dati di testo)
# Dal 05/10 anche le pagine d'esempio scaricate dall'agente (esempi/*.html, .xml): i test del
# parser girano offline su quelle, e chi approva le ritrova nella versione
# Dal 05/10 anche le schede interattive (scheda.py): script .js, stile .css, disegni .svg
ESTENSIONI_FILE = (".py", ".json", ".txt", ".csv", ".md", ".html", ".htm", ".xml", ".js",
                   ".css", ".svg")
# Il runtime lo dà Calliope (montato nel container): non fa parte dell'estensione
RUNTIME = "calliope_estensione.py"
MAX_FILE = 30
MAX_BYTE = 4_000_000


def impronta(cartella: Path) -> str:
    """SHA-256 di nomi e contenuti dei file della cartella, in ordine."""
    h = hashlib.sha256()
    for p in sorted(Path(cartella).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            rel = p.relative_to(cartella).as_posix()
            h.update(rel.encode("utf-8") + b"\0")
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def _sola_lettura(cartella: Path, si: bool = True):
    for p in sorted(Path(cartella).rglob("*"), reverse=True) + [Path(cartella)]:
        try:
            m = os.stat(p).st_mode
            if p.is_dir():
                os.chmod(p, (m & ~0o222) | 0o500 if si else m | 0o700)
            else:
                os.chmod(p, (m & ~0o222) if si else m | 0o600)
        except OSError:
            pass


def _scrivibile(p: Path):
    """Rende scrivibile `p` e ogni cartella sotto, dall'alto (09/10): su Linux si cancella un
    file solo se la sua **cartella** è scrivibile, e le versioni approvate hanno cartelle
    r-x (`_sola_lettura`); una cartella si apre prima di leggerne il contenuto."""
    try:
        os.chmod(p, stat.S_IMODE(os.lstat(p).st_mode) | stat.S_IRWXU)
    except OSError:
        pass
    for radice, cartelle, file in os.walk(p):
        for x in [radice] + [os.path.join(radice, c) for c in cartelle]:
            try:
                os.chmod(x, stat.S_IMODE(os.lstat(x).st_mode) | stat.S_IRWXU)
            except OSError:
                pass
        for f in file:
            q = os.path.join(radice, f)
            try:
                if not os.path.islink(q):
                    os.chmod(q, stat.S_IMODE(os.lstat(q).st_mode) | stat.S_IWRITE
                             | stat.S_IREAD)
            except OSError:
                pass


def _riprova(f, q, *_):
    """Per rmtree: un file o una cartella che non si toglie (sola lettura, anche la cartella
    che lo contiene) si rende scrivibile e si riprova una volta."""
    for x in (os.path.dirname(q), q):
        try:
            os.chmod(x, stat.S_IMODE(os.lstat(x).st_mode) | stat.S_IWRITE | stat.S_IREAD
                     | (stat.S_IXUSR if os.path.isdir(x) else 0))
        except OSError:
            pass
    f(q)


def _togli_cartella(p: Path):
    """Cancella la cartella con tutto dentro, anche i file approvati in sola lettura (su
    Windows l'attributo dei file, su Linux i permessi delle cartelle)."""
    if p.exists() or p.is_symlink():
        if p.is_symlink() or not p.is_dir():
            p.unlink()
            return
        _scrivibile(p)
        if sys.version_info >= (3, 12):
            shutil.rmtree(p, onexc=_riprova)
        else:  # pragma: no cover — Python 3.11
            shutil.rmtree(p, onerror=_riprova)


class Archivio:
    def __init__(self, cartella):
        self.cartella = Path(cartella)
        self.cartella.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.indice_path = self.cartella / "indice.json"
        dati, _ = leggi_json(self.indice_path)
        self.indice: dict = dati if isinstance(dati, dict) else {}

    # ── indice ──
    def _salva(self):
        scrivi_json(self.indice_path, self.indice, copia=True)

    def voce(self, nome: str) -> dict | None:
        with self._lock:
            return self.indice.get(nome)

    def nomi(self) -> list[str]:
        with self._lock:
            return sorted(self.indice)

    def attive(self) -> list[dict]:
        with self._lock:
            return [dict(v, nome=n) for n, v in sorted(self.indice.items())
                    if v.get("stato") == "attiva" and v.get("attiva")]

    def versione(self, nome: str, n: int | None = None) -> dict | None:
        """La voce di una versione (quella attiva se `n` è None)."""
        with self._lock:
            v = self.indice.get(nome)
            if v is None:
                return None
            n = v.get("attiva") if n is None else n
            return (v.get("versioni") or {}).get(str(n)) if n else None

    def cartella_versione(self, nome: str, n: int) -> Path:
        return self.cartella / nome / f"v{n}"

    def cartella_dati(self, nome: str) -> Path:
        return self.cartella / nome / "dati"

    def manifesto(self, nome: str, n: int | None = None) -> dict | None:
        """Il manifesto della versione (quella attiva se `n` è None), con il titolo dato dalla
        persona se l'ha rinominata (`rinomina`, 08/10): vale per tutte le versioni."""
        ver = self.versione(nome, n)
        m = (ver or {}).get("manifesto")
        with self._lock:
            titolo = (self.indice.get(nome) or {}).get("titolo")
        if m is not None and titolo:
            m = dict(m, titolo=titolo)
        return m

    def rinomina(self, nome: str, titolo: str):
        """Il titolo detto a voce, scelto dalla persona (08/10): solo nell'indice, i file delle
        versioni (e la loro impronta) non cambiano; il nome interno e il tool restano."""
        with self._lock:
            self.indice[nome]["titolo"] = str(titolo).strip()
            self._salva()

    # ── candidate ──
    def nuova_candidata(self, manifesto: dict, file: dict[str, bytes], chi: str | None,
                        test: dict | None = None, analisi: dict | None = None,
                        lavoro: str | None = None, test_passano: bool = False) -> int:
        """Salva una versione nuova «da approvare» e ne restituisce il numero."""
        nome = manifesto["nome"]
        file = {k: v for k, v in file.items() if k not in (RUNTIME, "CAPACITA.md")}
        if not file or len(file) > MAX_FILE or sum(len(v) for v in file.values()) > MAX_BYTE:
            raise ValueError("troppi file o troppo grandi")
        for k in file:
            if not k.endswith(ESTENSIONI_FILE) or ".." in k or k.startswith("/"):
                raise ValueError(f"file non ammesso: {k}")
        with self._lock:
            voce = self.indice.setdefault(nome, {"stato": "da_approvare", "attiva": None,
                                                 "versioni": {}, "sempre": []})
            n = max([int(x) for x in voce["versioni"]] or [0]) + 1
            dest = self.cartella_versione(nome, n)
            if dest.exists():
                _togli_cartella(dest)
            for rel, dati in file.items():
                q = dest / rel
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(dati)
            (dest / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False,
                                                            indent=1), encoding="utf-8")
            voce["versioni"][str(n)] = {
                "stato": "da_approvare", "manifesto": manifesto, "creata": _ora(),
                "chi": chi, "lavoro": lavoro, "test": test, "test_passano": bool(test_passano),
                "analisi": analisi,
                "impronta": impronta(dest)}
            if voce.get("stato") != "attiva":
                voce["stato"] = "da_approvare"
            voce["candidata"] = n
            self._salva()
            return n

    def candidata(self, nome: str) -> int | None:
        with self._lock:
            v = self.indice.get(nome) or {}
            n = v.get("candidata")
            ver = (v.get("versioni") or {}).get(str(n)) if n else None
            return n if ver and ver.get("stato") == "da_approvare" else None

    # ── approvazione, versioni ──
    def approva(self, nome: str, n: int, chi: str | None) -> dict:
        """Congela la versione `n` e la rende attiva. ValueError se l'impronta non torna."""
        with self._lock:
            v = self.indice[nome]
            ver = v["versioni"][str(n)]
            dest = self.cartella_versione(nome, n)
            if impronta(dest) != ver["impronta"]:
                raise ValueError("i file sono cambiati dopo la revisione")
            _sola_lettura(dest)
            ver.update(stato="approvata", approvata=_ora(), approvata_da=chi)
            v.update(stato="attiva", attiva=n, candidata=None)
            # I «sempre» valgono per una versione: con una nuova si richiedono
            v["sempre"] = [s for s in v.get("sempre") or [] if s.get("versione") == n]
            self._salva()
            return ver

    def precedente(self, nome: str) -> int | None:
        """L'ultima versione approvata prima di quella attiva."""
        with self._lock:
            v = self.indice.get(nome) or {}
            att = v.get("attiva") or 0
            ok = [int(k) for k, x in (v.get("versioni") or {}).items()
                  if x.get("approvata") and int(k) < att]
            return max(ok) if ok else None

    def disattiva(self, nome: str):
        with self._lock:
            v = self.indice[nome]
            v["stato"] = "disattivata"
            self._salva()

    def riattiva(self, nome: str) -> bool:
        with self._lock:
            v = self.indice[nome]
            if not v.get("attiva"):
                return False
            v["stato"] = "attiva"
            self._salva()
            return True

    def rifiuta(self, nome: str, n: int):
        with self._lock:
            v = self.indice[nome]
            v["versioni"][str(n)]["stato"] = "rifiutata"
            if v.get("candidata") == n:
                v["candidata"] = None
            if not v.get("attiva"):
                v["stato"] = "rifiutata"
            self._salva()

    def rimuovi(self, nome: str):
        with self._lock:
            # Prima i file (un'esecuzione appena finita può tenerli aperti un attimo), poi
            # l'indice: mai un indice senza cartella o il contrario
            for i in range(15):
                try:
                    _togli_cartella(self.cartella / nome)
                    break
                except OSError:
                    if i == 14:
                        raise
                    time.sleep(0.2)
            self.indice.pop(nome, None)
            self._salva()

    def verifica(self, nome: str) -> bool:
        """L'impronta dei file della versione attiva è quella approvata?"""
        ver = self.versione(nome)
        if not ver or ver.get("stato") != "approvata":
            return False
        n = self.voce(nome)["attiva"]
        try:
            return impronta(self.cartella_versione(nome, n)) == ver["impronta"]
        except OSError:
            return False

    # ── «sì, sempre» ──
    def sempre(self, nome: str, persona, regola: str, bersaglio: str) -> bool:
        with self._lock:
            v = self.indice.get(nome) or {}
            return any(s.get("persona") == persona and s.get("regola") == regola
                       and s.get("bersaglio") == bersaglio and s.get("versione") == v.get("attiva")
                       for s in v.get("sempre") or [])

    def concedi_sempre(self, nome: str, persona, regola: str, bersaglio: str):
        with self._lock:
            v = self.indice[nome]
            v.setdefault("sempre", []).append({"persona": persona, "regola": regola,
                                               "bersaglio": bersaglio,
                                               "versione": v.get("attiva"), "quando": _ora()})
            self._salva()

    def revoca_sempre(self, nome: str) -> int:
        with self._lock:
            v = self.indice[nome]
            n = len(v.get("sempre") or [])
            v["sempre"] = []
            self._salva()
            return n

    # ── contaminazione dei dati propri (05/10) ──
    def contaminazione(self, nome: str) -> list[str]:
        """Le categorie di dati personali scritte nei dati propri dell'estensione: chi li
        rilegge (anche in un'esecuzione dopo) è contaminato come se avesse letto quelle."""
        with self._lock:
            return list((self.indice.get(nome) or {}).get("contaminazione") or [])

    def contamina(self, nome: str, categorie) -> None:
        categorie = {c for c in categorie or () if c}
        with self._lock:
            v = self.indice.get(nome)
            if v is None or not categorie or categorie <= set(v.get("contaminazione") or []):
                return
            v["contaminazione"] = sorted(set(v.get("contaminazione") or []) | categorie)
            self._salva()

    def pulisci_contaminazione(self, nome: str) -> None:
        """Dati propri vuoti: niente più da portare (dopo dati_cancella dell'ultimo)."""
        with self._lock:
            v = self.indice.get(nome)
            if v is not None and v.get("contaminazione"):
                v["contaminazione"] = []
                self._salva()

    # ── registro delle decisioni ──
    def registra(self, riga: dict):
        try:
            with open(self.cartella / "decisioni.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"quando": _ora(), **riga}, ensure_ascii=False,
                                   default=str) + "\n")
        except OSError:
            pass


def _ora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
