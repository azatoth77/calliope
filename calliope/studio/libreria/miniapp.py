"""
Le mini-app della libreria dello Studio (31/10, issue #297, parte 2; decisione 0035 punto 46):
giochi con la macchina a stati di Calliope e il palco fisso (calliope/estensioni/macchina.py,
motore_gioco.js), scritti e rivisti da noi, nel repository. JavaScript deterministico, senza
modello: logica pura (`GIOCO`) e un elenco di dati (`DATI`) che la prova di verità controlla.

Ogni mini-app è una cartella `miniapp/<estensione>/` con:
- `manifesto.json`: il manifesto di un'estensione con la scheda (nome `libreria_<estensione>`,
  un gioco **puro**: niente permessi, niente azioni, niente dati salvati);
- `logica.js`: `const GIOCO = {…}` e `const DATI = {…}`, esportati per Node;
- `gioco.test.js`: i test del gioco con `apriGioco` (le pagine nel palco, le strade principali),
  che girano con la prova di fumo (`calliope/agenti/fumo_js.mjs`) nelle prove.

La scheda della libreria (`tipo: miniapp` in `contenuti/<materia>/`) dice tipo («esplora»,
«quiz», «percorso»), schede servite e comandi a voce; qui si controlla che quei comandi siano
forme vere della macchina. I file si leggono una volta e se ne tiene l'impronta: il riquadro si
compone da questi byte (schermi/giochi.py), mai dall'archivio delle estensioni, e mai da file
cambiati dopo il caricamento.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent / "miniapp"
PREFISSO = "libreria_"


@dataclass
class MiniApp:
    """Una mini-app caricata: il manifesto normalizzato, i file del riquadro e l'impronta."""
    estensione: str
    manifesto: dict
    file: dict[str, bytes] = field(default_factory=dict)
    impronta: str = ""
    cartella: Path | None = None

    @property
    def nome(self) -> str:
        return self.manifesto["nome"]

    @property
    def titolo(self) -> str:
        return self.manifesto.get("titolo") or self.nome

    def forme(self) -> set[str]:
        """Tutte le forme a voce della macchina (quelle del gioco e le standard)."""
        com = ((self.manifesto.get("scheda") or {}).get("ascolta") or {}).get("comandi") or {}
        out = set()
        for v in com.values():
            out.update(v.get("forme") if isinstance(v, dict) else v)
        return {str(f).lower() for f in out}

    def intatta(self) -> bool:
        """I file su disco sono ancora quelli caricati (l'impronta)."""
        if self.cartella is None:
            return True
        try:
            return _impronta({n: (self.cartella / n).read_bytes() for n in self.file}) == \
                self.impronta
        except OSError:
            return False


def _impronta(file: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for n in sorted(file):
        h.update(n.encode("utf-8") + b"\0" + file[n] + b"\0")
    return h.hexdigest()


def nome_di(estensione: str) -> str:
    return PREFISSO + estensione.replace("-", "_")


def carica(estensione: str, comandi=(), cartella: Path | None = None) -> tuple[MiniApp | None,
                                                                                  list[str]]:
    """(mini-app, errori) della cartella `estensione`: il manifesto valido, un gioco puro con la
    macchina, il nome `libreria_<estensione>`, i file .js senza i rischi dell'analisi statica, i
    `comandi` della scheda della libreria tutti forme della macchina."""
    from ...estensioni import manifesto as MF
    from ...estensioni.scheda import analizza_js, e_gioco_puro, ha_macchina
    base = (cartella or CARTELLA) / estensione
    try:
        dati = json.loads((base / "manifesto.json").read_text("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as ex:
        return None, [f"manifesto.json non si legge: {type(ex).__name__}"]
    try:
        m = MF.valida(dati)
    except MF.ManifestoNonValido as ex:
        return None, [f"manifesto: {ex}"]
    errori = []
    if m["nome"] != nome_di(estensione):
        errori.append(f"il nome del manifesto è «{m['nome']}», serve «{nome_di(estensione)}»")
    if not ha_macchina(m) or not e_gioco_puro(m):
        errori.append("una mini-app è un gioco puro con la macchina a stati (niente permessi né "
                      "azioni)")
    sch = m.get("scheda") or {}
    if sch.get("salva") or sch.get("condivisa") or sch.get("chat"):
        errori.append("una mini-app non salva dati, non è condivisa e non ha la chat")
    file = {}
    for n in sch.get("file") or []:
        try:
            file[n] = (base / n).read_bytes()
        except OSError:
            errori.append(f"manca il file {n}")
    rischi = analizza_js({n: b.decode("utf-8", "replace") for n, b in file.items()})["rischi"]
    errori += [f"{r['file']}:{r['riga']}: {r['cosa']}" for r in rischi[:5]]
    app = MiniApp(estensione, m, file, _impronta(file), base)
    forme = app.forme()
    fuori = [c for c in comandi if str(c).lower() not in forme]
    if fuori:
        errori.append("comandi che la macchina non ha: " + ", ".join(fuori))
    return (app if not errori else None), errori
