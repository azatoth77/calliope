"""
La correzione parte da un test che fallisce (12/10/2026 sera, parte 1 del flusso a fasi;
ricerca docs/ricerche/2026-10-12-flusso-agente-fasi.md § 5.1, passo 1; area agenti-estensioni).

Caso vero del 12/10 (il gioco delle porte, DGX): tre «correzioni» finite «fatto» con i test
verdi e il gioco uguale. Alle 08:46 i file del codice erano identici a prima; alle 11:37 una
riga cambiata per ipotesi; alle 11:42 `gioco.js` riscritto con lo stesso errore. Nessuna
riproduceva il problema segnalato: i test riguardavano la logica, il difetto stava nel disegno.
La letteratura dice lo stesso (SWT-bench, TDD-Bench, Agentless): una correzione vale se un test
che prima falliva adesso passa.

Qui il codice lo controlla sugli artefatti, alla consegna di una correzione:
- i file del codice (tolti manifesto, test, esempi e i file di prova dell'agente) devono essere
  **cambiati** rispetto alla versione di partenza (`lav.file_iniziali`): altrimenti «uguale»;
- ci deve essere un file di test **nuovo o cambiato**: altrimenti «nessun_test»;
- quei test, eseguiti sulla **versione di prima** in una sandbox nuova accanto (stesso
  isolamento, stesso container, come il ricollaudo), devono **fallire**: altrimenti
  «passa_prima» (non riproducono il problema). Che passino sulla versione nuova lo dice già il
  controllo dei test alla consegna (`Agente._test_falliti`).

La prova di fumo dei giochi non conta come riproduzione (non l'ha scritta l'agente): sulla
versione di prima si eseguono solo i test nuovi o cambiati, senza la prova di fumo.

Quando non si può dire (nessun file di partenza, solo C# senza esegui_test, il container di Node
che manca) l'esito è «saltato» e la consegna va avanti come prima. Solo libreria standard.
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

# I file che non cambiano ciò che il codice fa: il manifesto, il contratto e il runtime, i test,
# gli esempi, i file di prova dell'agente (esegui_js, esegui_python su un pezzo: prova_*.js/.py)
NON_CODICE = re.compile(r"(^|/)(manifesto\.json|CAPACITA\.md|calliope_estensione\.py)$|"
                        r"(^|/)test[^/]*\.py$|_test\.py$|\.test\.js$|(^|/)esempi(_veri)?/|"
                        r"(^|/)prova_[^/]*\.(js|py)$")
# I file di test (come Agente._ha_test e sandbox.test)
TEST = re.compile(r"(^|/)test[^/]*\.py$|_test\.py$|\.test\.js$")

# Gli esiti che non valgono come correzione
NON_RIPRODOTTO = ("uguale", "nessun_test", "passa_prima")


def codice(file: dict) -> dict:
    """I soli file di codice di {percorso: testo}."""
    return {k: v for k, v in (file or {}).items() if not NON_CODICE.search(k)}


def _testi(sandbox) -> dict[str, str]:
    out = {}
    for f in sandbox.elenca():
        rel = f["percorso"]
        if rel in getattr(sandbox, "sola_lettura", ()):
            continue
        try:
            out[rel] = (Path(sandbox.root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def _norm(t: str) -> str:
    return "\n".join(r.rstrip() for r in str(t or "").replace("\r\n", "\n").strip().split("\n"))


def test_nuovi(prima: dict, ora: dict) -> list[str]:
    """I file di test nuovi o cambiati rispetto alla versione di partenza."""
    return sorted(k for k, v in ora.items()
                  if TEST.search(k) and (k not in prima or _norm(prima[k]) != _norm(v)))


def codice_cambiato(prima: dict, ora: dict) -> bool:
    a = {k: _norm(v) for k, v in codice(prima).items()}
    b = {k: _norm(v) for k, v in codice(ora).items()}
    return a != b


def _sandbox_prima(sandbox, prima: dict, nuovi: list[str]):
    """Una sandbox accanto con la versione di prima e i soli test nuovi o cambiati."""
    from .sandbox import ESTENSIONI_DATI, Sandbox
    root = Path(sandbox.root).parent / f"{Path(sandbox.root).name}-prima"
    shutil.rmtree(root, ignore_errors=True)
    sb = Sandbox(root, getattr(sandbox, "tempo_s", 30.0), getattr(sandbox, "memoria_mb", 1024),
                 isolamento=sandbox.isolamento, cpu=getattr(sandbox, "cpu", 2.0),
                 max_processi=getattr(sandbox, "max_processi", 32),
                 linguaggi=getattr(sandbox, "linguaggi", None))
    sola = set(getattr(sandbox, "sola_lettura", ()) or ())
    for f in sandbox.elenca():
        rel = f["percorso"]
        sorgente = Path(sandbox.root) / rel
        if rel in nuovi or rel in sola or Path(rel).suffix.lower() in ESTENSIONI_DATI:
            dest = sb.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(sorgente.read_bytes())
    for rel, testo in (prima or {}).items():
        if TEST.search(rel) or rel in sola:
            continue                  # i test di prima non contano: solo quelli nuovi
        dest = sb.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(testo, encoding="utf-8", newline="\n")
    return sb


def _togli(root: Path):
    for _ in range(5):
        shutil.rmtree(root, ignore_errors=True)
        if not root.exists():
            return
        time.sleep(0.2)


def controlla(lav, sandbox, log=print) -> dict:
    """L'esito della riproduzione di una correzione: {"stato": riprodotto | uguale |
    nessun_test | passa_prima | saltato, "test": [file], "uscita": coda dell'esecuzione sulla
    versione di prima, "perche": per «saltato»}."""
    prima = dict(getattr(lav, "file_iniziali", None) or {})
    if not prima:
        return {"stato": "saltato", "perche": "nessun file della versione di prima"}
    ora = _testi(sandbox)
    if not codice_cambiato(prima, ora):
        return {"stato": "uguale", "test": test_nuovi(prima, ora)}
    nuovi = test_nuovi(prima, ora)
    if not nuovi:
        if not any(k.endswith((".py", ".js")) for k in codice(ora)):
            # Solo C# (niente esegui_test): la regola non si può chiedere
            return {"stato": "saltato", "perche": "nessun linguaggio con i test"}
        return {"stato": "nessun_test", "test": []}
    sb = None
    try:
        sb = _sandbox_prima(sandbox, prima, nuovi)
        r = sb.test(fumo=False)
    except Exception as e:  # noqa: BLE001 — nel dubbio la consegna va avanti come prima
        log(f"[AGENTI] {getattr(lav, 'id', '?')}: riproduzione non eseguita: "
            f"{type(e).__name__}: {e}")
        return {"stato": "saltato", "perche": f"{type(e).__name__}"}
    finally:
        if sb is not None:
            _togli(Path(sb.root))
    if r.get("errore") and "container" in str(r.get("errore")):
        return {"stato": "saltato", "perche": str(r.get("errore"))[:120]}
    uscita = str(r.get("uscita") or "")[-1500:]
    if r.get("passano"):
        return {"stato": "passa_prima", "test": nuovi, "uscita": uscita}
    return {"stato": "riprodotto", "test": nuovi, "uscita": uscita,
            "esito": r.get("esito")}


def messaggio_agente(esito: dict, problema: str = "", gioco: bool = False) -> str:
    """Il rimando all'agente quando la correzione non riproduce il problema."""
    p = f" («{str(problema).strip()[:200]}»)" if str(problema or "").strip() else ""
    come = (" Per un gioco il test va in gioco.test.js e tocca il gioco vero, perché il "
            "problema l'ha visto la persona sullo schermo: const g = await apriGioco(); await "
            "g.tocca(\"testo del pulsante\"); poi g.testo() per leggere cosa compare (non solo "
            "logica.js)." if gioco else "")
    stato = esito.get("stato")
    if stato == "uguale":
        return ("La correzione non è valida: i file del codice sono uguali a quelli di prima, "
                f"quindi il problema segnalato{p} c'è ancora. Prima scrivi un test che lo "
                "riproduce ed eseguilo: deve FALLIRE sul codice di adesso. Poi correggi il "
                "codice finché quel test passa, e consegna." + come)
    if stato == "nessun_test":
        return ("La correzione non è valida: non hai scritto né cambiato un test. In una "
                f"correzione prima scrivi un test che riproduce il problema segnalato{p} e lo "
                "vedi fallire sul codice di prima; poi correggi finché passa. Alla consegna "
                "rieseguo quel test sulla versione di prima: lì deve fallire." + come)
    test = ", ".join(esito.get("test") or []) or "i tuoi test"
    return (f"Ho rieseguito i test nuovi o cambiati ({test}) sulla versione di PRIMA della "
            f"correzione e passano anche lì: non riproducono il problema segnalato{p}. Scrivi "
            "un test che controlla proprio ciò che la persona dice che non va e che sulla "
            "versione di prima fallisce, poi correggi il codice finché passa." + come)
