"""Mini-banco del ragionamento nella passata dell'analisi prima del codice (17/10/2026, issue #10;
ricerca docs/ricerche/2026-10-12-flusso-agente-fasi.md § 4.4 e § 5.1 passo 4; area
agenti-estensioni).

La passata del «progettista dei test» (calliope/agenti/accettazione.py) gira dal 13/10 senza
ragionamento e a temperatura 0, come i requisiti. La ricerca consiglia il ragionamento per
trovare i buchi della richiesta; il rischio è il tempo (oltre `agenti_accettazione_s`, 90 s, la
passata salta e il lavoro parte senza esempi) e, con l'uscita vincolata dallo schema, un giro a
vuoto. Qui la stessa passata, sulle stesse richieste, N volte con il ragionamento spento e N
acceso (`thinking_token_budget`, come i lavori: `--budget`, di serie 2048), e si conta:

- contraddizioni trovate (le domande che si farebbero a voce), e su quale richiesta: sulla
  richiesta contraddittoria devono esserci, su quelle chiare no;
- esempi scritti, e quelli tolti dal codice perché contro la richiesta (valore non nominato,
  conto che non torna, risultato uguale a un dato);
- secondi, token generati e caratteri di ragionamento; le passate saltate (tempo o JSON rotto).

Le richieste: le tre del banco della temperatura (convertitore, porte, media voti a riga di
comando) e due dal genere di quelle vere del 12/10, con nomi di fantasia: il gioco con più
giocatori che porte (la contraddizione «giocatori» / «porte»), e una richiesta chiara. I
requisiti si estraggono una volta per richiesta (come in uno sviluppo) e restano uguali per
le due varianti.

**Sulla DGX quando vLLM è libero** (nessun lavoro dell'agente in corso), con l'interprete di
Calliope; non cambia la configurazione di nessuno:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_analisi_ragionamento.py \\
           [--ripetizioni 5] [--budget 2048] [--uscita ~/banco-analisi-ragionamento]

Durata: 5 richieste × 2 varianti × 5 ripetizioni = 50 passate da 5–60 s, 10–30 minuti.

A secco (cliente finto, nessun modello), per controllare il banco stesso:

    python prove/manuali/banco_analisi_ragionamento.py --secco
"""

import argparse
import datetime
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove" / "manuali"))
sys.path.insert(0, str(RADICE / "prove"))

# Le richieste del banco: (nome, tipo, gioco, programma, compito, contraddittoria)
CONTRADDITTORIA = (
    "Il gioco «Le porte di Valfiorita» da 2 a 5 giocatori: sullo schermo ci sono 3 porte, ogni "
    "giocatore nel suo turno apre una porta che nessun altro ha aperto, e tutti i giocatori "
    "devono aprire una porta prima della fine. Dietro ogni porta c'è un premio o un mostro.")
CHIARA = (
    "Un programma Python che riceve una temperatura in gradi Celsius come argomento e stampa "
    "quanto vale in Fahrenheit, con un decimale; senza argomento usa 20 gradi.")


def richieste() -> list[dict]:
    import banco_temperatura as B
    return [
        {"nome": "convertitore", "tipo": "estensione", "gioco": False, "programma": False,
         "compito": B.COMPITO_CONVERTITORE, "contraddittoria": False},
        {"nome": "porte", "tipo": "estensione", "gioco": True, "programma": False,
         "compito": B.COMPITO_PORTE, "contraddittoria": False},
        {"nome": "media", "tipo": "codice", "gioco": False, "programma": True,
         "compito": B.COMPITO_MEDIA, "contraddittoria": False},
        {"nome": "valfiorita", "tipo": "estensione", "gioco": True, "programma": False,
         "compito": CONTRADDITTORIA, "contraddittoria": True},
        {"nome": "fahrenheit", "tipo": "codice", "gioco": False, "programma": True,
         "compito": CHIARA, "contraddittoria": False},
    ]


def una_passata(svc, r: dict, requisiti: list[dict], budget: int, tempo_s: float) -> dict:
    """Una passata dell'analisi: la riga con le misure."""
    from calliope.agenti import accettazione as acc
    uso: dict = {}
    t0 = time.monotonic()
    an, esito = acc.analizza(svc, r["compito"], requisiti, r["compito"],
                             estensione=r["tipo"] == "estensione" and not r["gioco"],
                             gioco=r["gioco"], tempo_s=tempo_s, programma=r["programma"],
                             linguaggi=("python",), ragionamento=budget, uso=uso)
    riga = {"richiesta": r["nome"], "ragionamento": budget, "esito": esito,
            "secondi": round(time.monotonic() - t0, 1), "token": uso.get("eval", 0),
            "caratteri_ragionamento": uso.get("ragionamento", 0)}
    if an is None:
        return {**riga, "saltata": True, "contraddizioni": 0, "esempi": 0, "tolti": 0}
    tolti = sum(int(v) for v in (an.get("tolti") or {}).values())
    return {**riga, "saltata": False, "contraddizioni": len(an["contraddizioni"]),
            "domande": [c["domanda"] for c in an["contraddizioni"]],
            "esempi": len(an.get("esempi") or []), "tolti": tolti,
            "programma": an.get("programma"), "senza_esempi": an.get("senza_esempi")}


def tabella(righe: list[dict]) -> str:
    """Per richiesta e variante: contraddizioni, esempi, tolti, secondi e token (mediane)."""
    out = ["richiesta     ragion.  passate  saltate  contraddiz.  esempi  tolti  secondi  token"]
    chiavi = sorted({(x["richiesta"], x["ragionamento"]) for x in righe},
                    key=lambda k: ([x["richiesta"] for x in righe].index(k[0]), k[1]))
    for nome, budget in chiavi:
        rr = [x for x in righe if x["richiesta"] == nome and x["ragionamento"] == budget]
        fatte = [x for x in rr if not x["saltata"]] or [{"contraddizioni": 0, "esempi": 0,
                                                         "tolti": 0}]

        def med(k, xs=None):
            return statistics.median([x.get(k) or 0 for x in (xs or fatte)])
        out.append(f"{nome:<13} {('sì ' + str(budget)) if budget else 'no':<8} {len(rr):>7}  "
                   f"{sum(x['saltata'] for x in rr):>7}  "
                   f"{sum(x['contraddizioni'] for x in fatte) / max(1, len(rr)):>11.1f}  "
                   f"{med('esempi'):>6g}  {med('tolti'):>5g}  {med('secondi', rr):>7.1f}  "
                   f"{med('token', rr):>5g}")
    return "\n".join(out)


def gira(svc, cfg, ripetizioni: int, budget: int, uscita: Path, log=print) -> list[dict]:
    from calliope.requisiti import estrai
    tempo_s = float(getattr(cfg, "agenti_accettazione_s", 90.0))
    righe = []
    for r in richieste():
        req, _, esito = estrai(svc, cfg, r["compito"], r["compito"], r["tipo"], r["gioco"],
                               tempo_s=60.0, dalla_voce=False)
        log(f"— {r['nome']}: {len(req)} requisiti ({esito})")
        for rip in range(ripetizioni):
            for b in (0, budget):
                riga = una_passata(svc, r, req, b, tempo_s)
                riga["ripetizione"] = rip + 1
                righe.append(riga)
                log(f"   {'con' if b else 'senza'} ragionamento, {rip + 1}: "
                    f"{riga['contraddizioni']} contraddizioni, {riga['esempi']} esempi "
                    f"({riga['tolti']} tolti), {riga['secondi']} s, {riga['token']} token"
                    + (" — SALTATA " + riga["esito"] if riga["saltata"] else ""))
                (uscita / "righe.json").write_text(json.dumps(righe, ensure_ascii=False,
                                                              indent=1), encoding="utf-8")
    return righe


class ClienteFinto:
    """Il modello per il controllo a secco: requisiti e analisi preparati, «eval» e
    «thinking» come i client veri."""

    def __init__(self):
        self.corpi = []

    def chat(self, body, **_):
        self.corpi.append(body)
        props = body["format"]["properties"]
        if "requisiti" in props:
            r = {"requisiti": [{"testo": "fa quello che chiede", "dettaglio": ""}],
                 "stima": "piccolo"}
        else:
            r = {"contraddizioni": [{"requisiti": [1], "domanda": "Le porte bastano"}]
                 if body.get("think") else [], "scelte": [], "al_collaudo": []}
            if "programma" in props:
                r.update(programma={"linguaggio": "python", "file": "media_voti.py",
                                    "interfaccia": "riga_di_comando"},
                         esempi=[{"requisito": 1, "argomenti": ["5", "8", "9"],
                                  "calcolo": "(5 + 8 + 9) / 3"}])
        return {"content": json.dumps(r), "eval": 300 if body.get("think") else 100,
                "thinking": "x" * 50 if body.get("think") else ""}


def secco() -> int:
    from calliope.config import Config
    cfg = Config()
    cli = ClienteFinto()
    svc = SimpleNamespace(cfg=cfg, cliente=cli, imp=SimpleNamespace(modello="finto"),
                          arbitro=None)
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} {nome}" + ("" if ok else f"  {dettaglio}"))
    with tempfile.TemporaryDirectory() as d:
        righe = gira(svc, cfg, 1, 1024, Path(d), log=lambda *_: None)
    verifica("una passata per richiesta e variante", len(righe) == 10, str(len(righe)))
    analisi = [c for c in cli.corpi if "contraddizioni" in c["format"]["properties"]]
    verifica("senza ragionamento think spento; con, think e il suo tetto, i token in più",
             all(c["think"] is False and "thinking_budget" not in c for c in analisi[0::2])
             and all(c["think"] is True and c["thinking_budget"] == 1024
                     and c["options"]["num_predict"] == 2000 + 1024 for c in analisi[1::2]),
             str([(c["think"], c.get("thinking_budget")) for c in analisi]))
    media = [x for x in righe if x["richiesta"] == "media"]
    verifica("le misure: token, caratteri di ragionamento, esempi del programma",
             [x["token"] for x in media] == [100, 300]
             and [x["caratteri_ragionamento"] for x in media] == [0, 50]
             and all(x["esempi"] == 1 for x in media)
             and [x["contraddizioni"] for x in media] == [0, 1], str(media))
    t = tabella(righe)
    verifica("la tabella per richiesta e variante", "valfiorita" in t and "sì 1024" in t
             and len(t.splitlines()) == 11, t)
    print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
    return 1 if errori else 0


def main(argv) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Mini-banco del ragionamento nell'analisi")
    ap.add_argument("--secco", action="store_true")
    ap.add_argument("--ripetizioni", type=int, default=5)
    ap.add_argument("--budget", type=int, default=2048, help="token di ragionamento della "
                    "variante accesa (agenti_accettazione_ragionamento)")
    ap.add_argument("--uscita")
    args = ap.parse_args(argv)
    if args.secco:
        return secco()
    from calliope.agenti import Lavori, carica
    from calliope.config import load_config
    cfg = load_config()
    imp = carica(cfg)
    if imp is None:
        print("Nessun agente configurato in questa cartella.")
        return 1
    uscita = Path(args.uscita).expanduser() if args.uscita else Path(
        tempfile.mkdtemp(prefix="banco-analisi-ragionamento-"))
    uscita.mkdir(parents=True, exist_ok=True)
    svc = Lavori(cfg, imp, log=lambda m: print(f"   {m}", flush=True))
    try:
        d = svc.verifica()
        if d["codice"] != "ok":
            print(f"L'agente non è raggiungibile: {d['motivo']}. {d['passo']}")
            return 1
        print(f"Mini-banco del ragionamento: agente {imp.modello}, {args.ripetizioni} "
              f"ripetizioni, budget {args.budget}; risultati in {uscita}", flush=True)
        t0 = time.time()
        righe = gira(svc, cfg, args.ripetizioni, args.budget, uscita,
                     log=lambda m: print(m, flush=True))
    finally:
        svc.close()
    t = tabella(righe)
    print("\n" + t)
    (uscita / "riepilogo.json").write_text(json.dumps(
        {"agente": imp.modello, "data": datetime.datetime.now().isoformat(timespec="seconds"),
         "ripetizioni": args.ripetizioni, "budget": args.budget,
         "minuti": round((time.time() - t0) / 60, 1), "tabella": t, "righe": righe},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRiepilogo in {uscita / 'riepilogo.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
