"""
Misura dell'archivio con il modello vero (03/10/2026): OCR ed estrazione dei documenti finti
di prove/archivio_finto.py, con lo stesso codice di Calliope (`Archivio.giro`), poi il
confronto delle schede con i valori attesi.

Non è una prova del runner: serve un server del modello che legga le immagini (qwen3.6 su
vLLM sulla DGX). Dal portatile, con un tunnel (`ssh -N -L 18000:127.0.0.1:8000 <alias>`):

    python prove/archivio_misura.py --url http://127.0.0.1:18000/v1 --modello qwen3.6-35b [--giri 2]

Stampa per documento: secondi (OCR + estrazione), tipo, campi giusti sui valori attesi, valori
scartati dal controllo contro il testo (inventati o letti male), e il riassunto.
"""

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import archivio_finto as af  # noqa: E402

from calliope.agenti.impostazioni import Impostazioni  # noqa: E402
from calliope.agenti.remoto import crea_cliente  # noqa: E402
from calliope.archivio import Archivio, Grafo  # noqa: E402
from calliope.archivio import normalizza as nz  # noqa: E402
from calliope.archivio.estrattore import Estrattore  # noqa: E402
from calliope.archivio.testo import OcrVisivo  # noqa: E402
from calliope.config import Config  # noqa: E402


def confronta(atteso: dict, tipo_atteso: str, tipo: str, s: dict) -> list[tuple[str, bool, str]]:
    out = [("tipo", tipo == tipo_atteso, tipo)]
    for k, v in atteso.items():
        if k == "totale":
            got = s.get("importo_totale") if s.get("importo_totale") is not None else \
                s.get("premio") if s.get("premio") is not None else s.get("canone")
            out.append((k, got is not None and abs(got - v) < 0.005, str(got)))
        elif k == "data":
            got = s.get("data_documento") or s.get("data_esame")
            out.append((k, got == v, str(got)))
        elif k == "scadenza":
            got = [x["data"] for x in s.get("scadenze") or []]
            out.append((k, v in got, str(got)))
        elif k == "emittente":
            got = (s.get("emittente") or {}).get("nome", "")
            out.append((k, nz.nome_ente(got) == nz.nome_ente(v), got))
        elif k in ("intestatario", "persona"):
            got = [p["nome"] for p in s.get("intestatari") or []]
            out.append((k, any(nz.nome_persona(g) == nz.nome_persona(v) for g in got), str(got)))
        elif k == "categoria":
            out.append((k, s.get("categoria") == v, str(s.get("categoria"))))
        elif k == "numero":
            out.append((k, nz.compatto(s.get("numero")) == nz.compatto(v), str(s.get("numero"))))
        elif k == "bene":
            got = s.get("prodotto") or ""
            out.append((k, nz.piatto(v) in nz.piatto(got) or nz.piatto(got) in nz.piatto(v), got))
    return out


DOMANDE = [
    ("quanto ho speso di luce nel 2026 rispetto al 2025?", ("84,5", "97,2")),
    ("quali garanzie ho e quando scadono, e di cosa?", ("lavatrice", "2027")),
    ("quali documenti scadono entro la fine del 2026 e quanto devo pagare in tutto?",
     ("62,3", "84,5")),
]


def agente(cfg, imp, svc):
    """Le domande complesse delegate: il ciclo di ricerca dell'agente con gli strumenti
    grafo_* e il modello vero (con il ragionamento, come i lavori veri)."""
    from calliope.agenti.arbitro import Arbitro
    from calliope.agenti.ciclo import Agente, Lavoro
    cli = crea_cliente(imp)
    ag = Agente(cfg, imp, cli, Arbitro(False))
    ag.archivio = svc
    for i, (domanda, attese) in enumerate(DOMANDE, 1):
        lav = Lavoro(f"L{i}", "ricerca", domanda, "mario-id", "Mario", "amministra")
        t0 = time.perf_counter()
        strumenti = []
        vecchio = cli.chat

        def spia(body, su_pezzo=None, controlla=None):
            out = vecchio(body, su_pezzo, controlla)
            strumenti.extend(c["name"] for c in out["tool_calls"])
            return out
        cli.chat = spia
        try:
            r = ag.ricerca(lav)
        except Exception as e:  # noqa: BLE001
            r = {"riassunto": f"ERRORE {type(e).__name__}: {e}", "testo": ""}
        cli.chat = vecchio
        tutto = (r.get("riassunto") or "") + " " + (r.get("testo") or "")
        norm = tutto.replace(".", ",")
        ok = all(x in norm or x.replace(",5", ",50") in norm for x in attese)
        print(f"\n[agente] {domanda}\n  {time.perf_counter() - t0:.1f} s, {lav.passi} passate, "
              f"{lav.token} token, strumenti {strumenti}\n  {'ok' if ok else 'DA GUARDARE'}: "
              f"{r.get('riassunto')!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18000/v1")
    ap.add_argument("--modello", default="qwen3.6-35b")
    ap.add_argument("--ocr-modello", default="")
    ap.add_argument("--giri", type=int, default=1)
    ap.add_argument("--agente", action="store_true",
                    help="poi tre domande delegate all'agente, che esplora il grafo")
    a = ap.parse_args()
    motore = "openai" if a.url.rstrip("/").endswith("/v1") else "ollama"
    imp = Impostazioni("diretto", a.url.rstrip("/"), a.modello, motore=motore)
    tot_ok = tot = 0
    secondi = []
    for giro in range(a.giri):
        tmp = Path(tempfile.mkdtemp(prefix="archivio-misura-"))
        root = tmp / "documenti"
        docs = af.genera(root)
        cfg = Config()
        cfg.archivio_cartella = str(root)
        g = Grafo(str(tmp / "a.db"))
        est = Estrattore(crea_cliente(imp), a.modello)
        ocr = OcrVisivo(a.url, a.ocr_modello or a.modello, motore)
        svc = Archivio(cfg, g, root, est, ocr, log=print)
        print(f"\n== giro {giro + 1}")
        for d in docs:
            p = Path(d["percorso"])
            t0 = time.perf_counter()
            esito = svc.elabora_file(p)
            s_ = time.perf_counter() - t0
            secondi.append(s_)
            row = g.leggi("SELECT s.tipo, s.scheda, s.scartati, s.metodo FROM file f JOIN schede s "
                          "ON s.nodo = f.nodo WHERE f.percorso = ?", (p.name,))
            if esito != "ok" or not row:
                print(f"{p.name[:28]:28} {s_:6.1f} s  ESITO {esito}")
                tot += 1
                continue
            import json
            s = json.loads(row[0]["scheda"])
            ris = confronta(d["atteso"], d["tipo"], row[0]["tipo"], s)
            ok = sum(x[1] for x in ris)
            tot_ok += ok
            tot += len(ris)
            sbagliati = [f"{k}={v}" for k, good, v in ris if not good]
            scart = json.loads(row[0]["scartati"])
            print(f"{p.name[:28]:28} {s_:6.1f} s  {row[0]['metodo']:5} {row[0]['tipo']:13} "
                  f"{ok}/{len(ris)}" + (f"  sbagliati: {sbagliati}" if sbagliati else "")
                  + (f"  scartati: {[(x['campo'], x['valore']) for x in scart]}" if scart else ""))
        c = g.conteggi()
        print("nodi:", c["nodi"])
        if a.agente and giro == 0:
            agente(cfg, imp, svc)
        g.close()
        shutil.rmtree(tmp, ignore_errors=True)
    ss = sorted(secondi)
    print(f"\nCampi giusti: {tot_ok}/{tot}; secondi per documento: mediana {ss[len(ss) // 2]:.1f}, "
          f"massimo {ss[-1]:.1f}")


if __name__ == "__main__":
    main()
