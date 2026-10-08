"""
`python -m calliope.stato`: cosa funziona in questa installazione di Calliope, cosa manca e
il prossimo passo (registro delle capacità, calliope/capacita.py).

    python -m calliope.stato                  tabella con stato, motivo e passi
    python -m calliope.stato --dettagli       anche i dettagli di ogni capacità
    python -m calliope.stato --json           lo stesso in JSON, per gli script
    python -m calliope.stato --catalogo       cosa si può installare
    python -m calliope.stato --turni [--giorni N]
                                              latenza vera della voce per giorno (prima frase,
                                              mediana e p90) con le cause, dal registro dei
                                              turni (calliope/latenza.py); attrito della
                                              sicurezza per giorno (calliope/attrito.py);
                                              argomenti che nominano qualcosa: probabilità di
                                              Whisper, nomi noti vicini, esiti vuoti
                                              (calliope/argomenti_incerti.py)
    python -m calliope.stato --turni --pause [--giorni N]
                                              pause dentro la frase per persona e canale,
                                              tagli probabili e la soglia che si sceglierebbe
                                              (solo stima, calliope/pause.py)
    python -m calliope.stato --piano [--json] [--inventario FILE]
                                              il piano dei modelli per questa macchina, in
                                              sola lettura (calliope/piano.py): voce, Whisper,
                                              guardiano, rilevatore, embedding, contesto,
                                              agente, Piper, con stime e motivi; non applica
                                              niente. --inventario: una macchina salvata (JSON
                                              di --piano --json) invece di questa
    python -m calliope.stato --installa <azione>
                                              proposta, conferma da tastiera, scaricamento
                                              con avanzamento (stesso codice della voce)

Deve funzionare anche su una macchina appena installata (lo Spark su ARM): una libreria
assente è «mancante», non un crash. Controlli in sola lettura; Ollama locale con un tempo
massimo breve, nessuna rete esterna (tranne --installa, verso le origini del catalogo).
"""

import contextlib
import json
import platform
import sys
import threading
import time


def _config(quiet: bool):
    """La configurazione, anche senza PyYAML o con il file rovinato: allora i predefiniti."""
    from .config import Config
    sink = sys.stderr if quiet else sys.stdout
    try:
        from .config import load_config
        with contextlib.redirect_stdout(sink):
            return load_config()
    except Exception as e:  # noqa: BLE001 — PyYAML assente, file illeggibile
        print(f"[CONFIG] Configurazione non letta ({type(e).__name__}: {e}): uso i "
              f"predefiniti.", file=sink)
        return Config()


def tabella(reg, dettagli: bool = False) -> str:
    rows = reg.tutte(fresche=True)
    w = max(len(c.definizione.breve) for c in rows) + 2
    out = [f"Calliope: capacità di questa installazione ({platform.system()} "
           f"{platform.machine()}, Python {platform.python_version()})", "",
           f"{'CAPACITÀ':{w}}{'STATO':16}MOTIVO"]
    for c in rows:
        out.append(f"{c.definizione.breve:{w}}{c.stato:16}{c.motivo}")
        if dettagli:
            out.append(f"{'':{w}}dipende da: {', '.join(c.definizione.dipende)}")
            for k, v in c.dettagli.items():
                out.append(f"{'':{w}}{k}: {v}")
    passi = [(c.definizione.breve, c.prossimo_passo) for c in rows if c.prossimo_passo]
    if passi:
        out += ["", "Prossimi passi:"]
        out += [f"  - {n}: {p}" for n, p in passi]
    attive = sum(c.attiva for c in rows)
    out += ["", f"{attive} attive su {len(rows)}."]
    return "\n".join(out)


def catalogo_testo(cfg) -> str:
    from .installa.catalogo import DESCRIZIONI, catalogo
    cat = catalogo(cfg)
    out = ["Azioni installabili (python -m calliope.stato --installa <azione>):"]
    for k, v in DESCRIZIONI.items():
        if k in cat:
            out.append(f"  {k:28} {v}")
    out.append("Fuori dal catalogo: pacchetti Python (pip), calliope.yaml e "
               "calliope.locale.yaml.")
    return "\n".join(out)


def installa(cfg, azione: str, inst=None, input_fn=input, out=print) -> int:
    """Da terminale: stesso piano, stessi prerequisiti e stesso scaricamento della voce,
    con la conferma da tastiera al posto del «sì»."""
    from .installa import Installazioni
    from .installa.servizio import parla_byte
    inst = inst or Installazioni(cfg, log=out)
    p = inst.piano(azione)
    out(p.frase)
    if not p.ok:
        return 0 if p.codice == "gia_fatto" else 1
    try:
        answer = input_fn("Procedo? [s/N] ")
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ("s", "si", "sì", "y", "yes"):
        out("Va bene, non scarico niente.")
        return 0
    cancel = threading.Event()
    last = [0.0]

    def avanz(fase, n, totale=None):
        now = time.monotonic()
        if now - last[0] < 1.0:
            return
        last[0] = now
        if fase == "indice":          # voci indicizzate, non byte
            pct = f" {min(100, int(n * 100 / totale))}%" if totale else ""
            sys.stdout.write(f"\r  indice di ricerca{pct} ({n} voci)" + " " * 10)
            sys.stdout.flush()
            return
        tot = totale or p.byte
        pct = f" {min(100, int(n * 100 / tot))}%" if tot and fase == "scarico" else ""
        sys.stdout.write(f"\r  {fase}{pct} {parla_byte(n)}" + " " * 10)
        sys.stdout.flush()

    t0 = time.time()
    try:
        res = inst.esegui(p, cancel, avanz)
    except KeyboardInterrupt:
        cancel.set()
        res = {"esito": "annullato", "frase": "Interrotto: la prossima volta riprendo da dove "
               "ero arrivata.", "byte": 0}
    out("")
    _log(cfg, azione, res, t0)
    if res["esito"] != "ok":
        out(res["frase"])
        return 1
    how = res.get("attiva")
    if p.azione.tipo == "indice":
        out("Fatto: indice di ricerca pronto. Se Calliope è accesa, riavviala per usarlo.")
        return 0
    out("Fatto: installato e verificato." + {
        "riavvio": " Riavvia Calliope per usarlo.",
        "subito": " Se Calliope è accesa, riavviala per usarlo.",
        "nessuna": " La fonte resta da parte: la ricerca non la usa ancora."}.get(how, ""))
    return 0


def _log(cfg, azione: str, res: dict, t0: float):
    """Anche le installazioni da terminale vanno nel registro dei turni."""
    try:
        import datetime
        from .turnlog import TurnLog
        TurnLog(cfg.turn_log_dir, cfg.turn_log_days).write({
            "inizio": datetime.datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
            "esito": "installazione", "livello": "amministra", "origine": "terminale",
            "installazione": {"azione": azione, "esito": res["esito"],
                              "codice": res.get("codice"), "byte": res.get("byte", 0)}})
    except Exception:  # noqa: BLE001 — il registro non deve fermare l'installazione
        pass


def piano_main(cfg, argv: list[str], as_json: bool) -> int:
    """`--piano`: inventario della macchina, piano proposto, nessuna applicazione (08/10)."""
    from . import macchina, piano
    if "--inventario" in argv:
        i = argv.index("--inventario")
        try:
            with open(argv[i + 1], encoding="utf-8") as fh:
                inv = json.load(fh)
            inv = inv.get("inventario", inv)
        except (IndexError, OSError, ValueError) as e:
            print(f"--inventario vuole un file JSON leggibile ({e})")
            return 1
    else:
        inv = macchina.inventario(cfg)
    p = piano.piano(inv, piano.da_config(cfg, inv))
    if as_json:
        print(json.dumps({"inventario": inv, "piano": p.as_json()}, ensure_ascii=False,
                         indent=2, default=str))
    else:
        print(piano.testo(p))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if {"-h", "--help", "/?"} & set(argv):
        print(__doc__.strip())
        return 0
    as_json = "--json" in argv
    cfg = _config(quiet=as_json)
    from . import capacita
    capacita.PROVA_COLLEGAMENTI = True       # da terminale la casa si prova davvero
    if "--catalogo" in argv:
        print(catalogo_testo(cfg))
        return 0
    if "--turni" in argv:
        from . import latenza
        giorni = None
        if "--giorni" in argv:
            i = argv.index("--giorni")
            try:
                giorni = max(1, int(argv[i + 1]))
            except (IndexError, ValueError):
                print("--giorni vuole un numero")
                return 1
        if "--pause" in argv:
            from . import pause
            r = pause.riassunto(latenza.leggi(cfg.turn_log_dir, giorni))
            print(json.dumps(r, ensure_ascii=False, indent=2) if as_json else pause.testo(r))
            return 0
        from . import attrito
        turni = latenza.leggi(cfg.turn_log_dir, giorni)
        dati = latenza.per_giorno(turni)
        soglia = float(getattr(cfg, "latenza_avviso_s", 1.2) or 0) or float("inf")
        # L'attrito della sicurezza (08/10, calliope/attrito.py): domande di sicurezza ogni 100
        # turni, ripetute, poi eseguite, e la politica per valore in ombra
        sicurezza = attrito.per_giorno(turni)
        soglia_a = float(getattr(cfg, "attrito_avviso", 3.0) or 0)
        # Gli argomenti che nominano qualcosa (08/10, F0: calliope/argomenti_incerti.py)
        from . import argomenti_incerti
        argomenti = argomenti_incerti.riassunto(turni)
        if as_json:
            print(json.dumps({"giorni": dati, "soglia_s": getattr(cfg, "latenza_avviso_s", None),
                              "attrito": sicurezza, "attrito_soglia": soglia_a,
                              "argomenti": argomenti},
                             ensure_ascii=False, indent=2))
        else:
            print(latenza.testo(dati, soglia))
            print()
            print(attrito.testo(sicurezza, soglia_a))
            print()
            print(argomenti_incerti.testo(argomenti))
        return 0
    if "--piano" in argv:
        return piano_main(cfg, argv, as_json)
    if "--installa" in argv:
        i = argv.index("--installa")
        if i + 1 >= len(argv):
            print(catalogo_testo(cfg))
            return 1
        return installa(cfg, argv[i + 1])
    from . import capacita
    reg = capacita.controlla(cfg)
    # La finestra di contesto scelta da Calliope all'ultimo avvio, e perché (05/10)
    from . import contesto
    try:
        ctx_testo, ctx_dati = contesto.testo_stato(cfg), contesto.leggi_salvato(cfg)
    except Exception:  # noqa: BLE001 — lo stato non deve cadere per questo
        ctx_testo, ctx_dati = None, None
    # Quanto costa la voce su questa macchina (07/10, calliope/taratura_voce.py)
    try:
        from . import taratura_voce
        voce_testo = taratura_voce.testo_stato(cfg)
        voce_dati = taratura_voce.per(cfg).stima(
            cfg.piper_voice, taratura_voce.sessione_in_uso(cfg, cfg.piper_voice))
        voce_dati["dispositivo"], voce_dati["motivo"] = taratura_voce.dispositivo_in_uso(
            cfg, cfg.piper_voice, controlla_posto=False)
    except Exception:  # noqa: BLE001
        voce_testo, voce_dati = None, None
    if as_json:
        print(json.dumps({"capacita": reg.as_json(), "riassunto": reg.riassunto(),
                          "contesto": ctx_dati, "voce": voce_dati,
                          "macchina": {"sistema": platform.system(),
                                       "architettura": platform.machine(),
                                       "python": platform.python_version()}},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(tabella(reg, dettagli="--dettagli" in argv))
        if ctx_testo:
            print()
            print(ctx_testo)
        if voce_testo:
            print(voce_testo)
        # La latenza vera di oggi o di ieri, se supera latenza_avviso_s (06/10, P4)
        try:
            from . import latenza
            avviso = latenza.avviso_recente(cfg)
        except Exception:  # noqa: BLE001
            avviso = None
        if avviso:
            print()
            print(f"Latenza: {avviso} Dettagli: --turni")
        # Troppe domande di sicurezza oggi o ieri, o una ripetuta (08/10, calliope/attrito.py)
        try:
            from . import attrito
            avviso = attrito.avviso_recente(cfg)
        except Exception:  # noqa: BLE001
            avviso = None
        if avviso:
            print()
            print(f"{avviso} Dettagli: --turni")
    return 0


if __name__ == "__main__":
    sys.exit(main())
