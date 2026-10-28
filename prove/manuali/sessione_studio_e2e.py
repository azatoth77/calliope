"""Una sessione di studio vera nell'istanza di prova della DGX (28/10/2026, #293; passo manuale
prove/manuali/studio.md, copione prove/manuali/studio/copione_leo.json).

Calliope vera, coi modelli veri della DGX (voce gemma4 26B su Ollama, qwen3.6 su vLLM), ma
nell'**istanza di prova** di `prove/e2e/` (cartella `~/calliope-e2e`, porte sue, mai il servizio
di casa). In più alle persone della prova c'è **Leo**, un ragazzo di fantasia di seconda media
(nato nel 2014, voce di Piper «miro», tutore Andrea), con il suo schermo personale nello
studio: parla a voce dal satellite dello studio per aprire la conversazione e poi scrive e manda
le foto delle pagine dal suo schermo, come farebbe dal telefono.

Due modi:

- `--copione FILE --sessione ID`: esegue i passi del copione uno dopo l'altro (per rilanciarlo
  dopo lo Studio nuovo e confrontare);
- `--comandi CARTELLA`: aspetta i passi uno alla volta come file `NNN.json` nella cartella
  (`{"tipo": "voce"|"scrivi"|"foto", "testo": …, "immagine": percorso}`; `{"tipo": "fine"}`
  chiude) e scrive la risposta in `NNN.risposta.json`: così chi fa lo studente decide la battuta
  dopo guardando la risposta di prima.

Le foto vanno da `/api/immagine` dello schermo di Leo, come una foto della conversazione di oggi
(lo Studio nuovo, con `/api/studio/pagina`, non c'è ancora: 4.2). Prima di ogni passo la guardia
della prova (la Calliope vera tace da 180 s). Alla fine si ferma tutto e la cartella dell'istanza
si cancella; restano `~/calliope-e2e/risultati/<data>/` (passi.jsonl, runner.log, istanza.log).

Si lancia sulla DGX dalla cartella della versione installata (o di un clone), con le immagini di
`studio_immagini.py`:

    V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
    cd $V && PYTHONPATH=$V .venv/bin/python <percorso>/sessione_studio_e2e.py \\
        --immagini /tmp/banco-studio/immagini --copione <percorso>/studio/copione_leo.json \\
        --sessione storia-breve
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import traceback
from pathlib import Path


def _radice() -> Path:
    for p in [Path.cwd()] + list(Path(__file__).resolve().parents):
        if (p / "prove" / "e2e" / "__main__.py").is_file() and (p / "calliope").is_dir():
            return p
    raise SystemExit("lancia dalla cartella di una versione di Calliope (serve prove/e2e)")


RADICE = _radice()
for p in (str(RADICE), str(RADICE / "prove")):
    if p not in sys.path:
        sys.path.insert(0, p)

from prove.e2e import __main__ as M  # noqa: E402
from prove.e2e import copioni as C  # noqa: E402
from prove.e2e import istanza as I  # noqa: E402
from prove.e2e import voci as VO  # noqa: E402

LEO = VO.Persona("Leo", "it_IT-miro-medium.onnx", genere="m", nascita="2014-03-20",
                 tutori=["Andrea"])


def _abbina_con_leo(self):
    """Come Istanza._abbina, più uno schermo personale di Leo nello studio."""
    _abbina_di_prima(self)
    from calliope.schermi.archivio import ArchivioSchermi
    sch = ArchivioSchermi(str(self.ist / "memoria.db"))
    r = sch.nuova_richiesta()
    if "Leo" in self.profili:
        sch.abbina(r["codice"], "studio", self.profili["Leo"], "Leo")
        self.richiesta_schermo["studio-leo"] = r["richiesta"]
    sch.close()


_abbina_di_prima = I.Istanza._abbina


class RunnerStudio(M.Runner):
    def _accedi_schermo(self):
        """Lo schermo di Leo al posto di quello di Andrea (lo scritto e le foto sono suoi)."""
        r = self.ist.richiesta_schermo.pop("studio", None)
        self.ist.richiesta_schermo["studio"] = self.ist.richiesta_schermo.get("studio-leo") or r
        super()._accedi_schermo()

    def _schermo(self, passo, rec):
        if passo.tipo != "foto_file":
            return super()._schermo(passo, rec)
        h = {"X-Calliope-Sessione": self.sessione}
        d = passo.dati
        dati = Path(d["immagine"]).read_bytes()
        url = "data:image/jpeg;base64," + base64.b64encode(dati).decode()
        t0 = time.monotonic()
        rr = self.http.post("/api/immagine", headers=h,
                            json={"immagine": url, "testo": d.get("domanda") or ""})
        rec["detto"] = f"[foto {Path(d['immagine']).name}] {d.get('domanda') or ''}"
        if rr.status_code != 200:
            rec.update(esito_passo="fallito", errori=[f"schermo: {rr.status_code} {rr.text[:200]}"])
            return None
        return t0


def passo_da(d: dict, immagini: Path | None) -> C.Passo:
    tipo = d.get("tipo", "scrivi")
    attese = d.get("attese") or {}
    if tipo == "foto":
        img = Path(d["immagine"])
        if not img.is_absolute() and immagini:
            img = immagini / img
        return C.Passo("Leo", None, tipo="foto_file", attese=attese, max_s=d.get("max_s", 90),
                       dati={"immagine": str(img), "domanda": d.get("testo") or ""})
    if tipo == "voce":
        return C.Passo("Leo", d["testo"], tipo="voce", attese=attese, max_s=d.get("max_s", 60))
    return C.Passo("Leo", None, tipo="scrivi", attese=attese, max_s=d.get("max_s", 90),
                   dati={"testo": d["testo"]})


def esegui_uno(run, cop, i, d, prec, immagini, uscita: Path):
    run.ist.aspetta_silenzio(run.a.guardia, motivo="prima del passo")
    if i:
        run.sat["studio"].aspetta_zitta(120)
        time.sleep(0.6)
    passo = passo_da(d, immagini)
    try:
        rec = run.esegui_passo(cop, i, passo, prec)
    except Exception as e:  # noqa: BLE001
        rec = {"passo": i, "esito_passo": "errore", "errori": [f"{type(e).__name__}: {e}"],
               "traccia": traceback.format_exc()[-1500:]}
    # Fuori dalla conversazione lo scritto è rifiutato (403): Leo saluta a voce e riprova
    if any("senza_conversazione" in str(x) or "403" in str(x) for x in rec.get("errori") or []):
        run.log("   (conversazione scaduta: Leo saluta a voce e riprova)")
        run.esegui_passo(cop, i, C.Passo("Leo", "Calliope, sono di nuovo io.", tipo="voce"), prec)
        run.sat["studio"].aspetta_zitta(120)
        rec = run.esegui_passo(cop, i, passo, prec)
    rec["battuta"] = d
    run.passi.append(rec)
    with open(run.out / "passi.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    run.log(f"   {i}. Leo: {rec.get('detto')!r} → {rec.get('esito_passo')} "
            f"[{','.join(rec.get('tool') or [])}] {rec.get('lat_s')} s | "
            f"{(rec.get('risposta') or '')[:160]!r}")
    if uscita:
        (uscita).write_text(json.dumps({k: rec.get(k) for k in (
            "detto", "risposta", "tool", "regole", "esito", "livello", "lat_s", "prima_frase_s",
            "trascritto", "esito_passo", "errori", "annuncio")}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dati", default="~/calliope-e2e")
    ap.add_argument("--vera", default="~/calliope")
    ap.add_argument("--guardia", type=float, default=180.0)
    ap.add_argument("--immagini", type=Path, default=None)
    ap.add_argument("--copione", type=Path, default=None)
    ap.add_argument("--sessione", default=None, help="id della sessione nel copione")
    ap.add_argument("--comandi", type=Path, default=None)
    ap.add_argument("--attesa-comando-s", type=float, default=1800.0)
    ap.add_argument("--voce-leo", default=LEO.voce,
                    help="voce di Piper di Leo (il 28/10 «leonardo» non faceva scattare la wake "
                         "word)")
    ap.add_argument("--tieni", action="store_true")
    a = ap.parse_args(argv)
    a.codice, a.calliope, a.stt, a.telefono = None, None, None, 0.0
    LEO.voce = a.voce_leo
    VO.PERSONE["Leo"] = LEO
    I.Istanza._abbina = _abbina_con_leo
    pidf = Path(a.dati).expanduser() / "runner.pid"
    pidf.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    import os
    pidf.write_text(str(os.getpid()))
    run = RunnerStudio(a)
    cop = C.Copione("studio-leo", "studio", "Sessione di studio di Leo", [], richiede=("schermo",))
    try:
        run.prepara()
        if not run.sessione:
            raise RuntimeError("lo schermo di Leo non si è collegato")
        prec = None
        if a.copione:
            copione = json.loads(a.copione.read_text(encoding="utf-8"))
            sess = next(s for s in copione["sessioni"] if s["id"] == a.sessione)
            for i, d in enumerate(sess["passi"]):
                prec = esegui_uno(run, cop, i, d, prec, a.immagini, None)
        if a.comandi:
            a.comandi.mkdir(parents=True, exist_ok=True)
            i = len(run.passi)
            (a.comandi / "PRONTO").write_text("ok")
            while True:
                f = a.comandi / f"{i:03d}.json"
                t0 = time.monotonic()
                while not f.is_file():
                    if time.monotonic() - t0 > a.attesa_comando_s:
                        raise TimeoutError("nessun comando: chiudo")
                    time.sleep(1.0)
                time.sleep(0.3)
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("tipo") == "fine":
                    break
                prec = esegui_uno(run, cop, i, d, prec, a.immagini,
                                  a.comandi / f"{i:03d}.risposta.json")
                i += 1
    except Exception as e:  # noqa: BLE001
        run.log(f"[studio] errore: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        try:
            log = run.ist.log_testo() if getattr(run, "ist", None) else ""
            (run.out / "istanza.log").write_text(M.anonimo(log[-400000:]), encoding="utf-8")
            turni = run.ist.turni() if getattr(run, "ist", None) else []
            (run.out / "turni.jsonl").write_text("\n".join(json.dumps(t, ensure_ascii=False)
                                                           for t in turni), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            run.log(f"[studio] registro non copiato: {e}")
        run.chiudi()
        if not a.tieni:
            I.pulisci(run.dati)
        pidf.unlink(missing_ok=True)
        if a.comandi:
            (a.comandi / "FINITO").write_text(str(run.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
