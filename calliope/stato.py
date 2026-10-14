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
                                              (calliope/argomenti_incerti.py); compagnia: frasi
                                              con più voci vicino a un satellite, regole e
                                              giudizi «rivolta a Calliope» (calliope/compagnia.py);
                                              stato del dialogo in ombra: proposte aperte,
                                              proposta_rispondi chiamato o no, accordo con la
                                              decisione di oggi (calliope/stato_dialogo.py);
                                              una voce sola: parlato diverso dalla storia,
                                              domande non registrate e il registro degli
                                              eventi in ombra (calliope/eventi/misura.py);
                                              scelta dei tool: nomi inventati, correzioni,
                                              ripieghi, richieste ripetute, con un avviso
                                              (calliope/scelta_tool.py); frasi pronte:
                                              ripetizioni ogni 100 risposte, pronte e
                                              modello, e la stima con le varianti in ombra
                                              (calliope/frasi.py); stanza: ore di parlato
                                              per satellite, ritardo della coda, banda,
                                              scartate, presenze e cambi di stanza, copertura
                                              all'interpellazione, stt e prima frase con e senza
                                              stanza (calliope/stanza/misure.py, 13/10);
                                              guardiano a posteriori della stanza: segnali
                                              per ora di chiacchiera con un minore, livelli,
                                              acuti falsi a settimana (stanza/guardia.py);
                                              fine del turno System 1: ms risparmiati, frasi
                                              che avrebbe tagliato, attese più lunghe
                                              (calliope/system1/fine_turno.py, 14/10)
    python -m calliope.stato --guardia [--giorni N] [--falso ID | --vero ID]
                                              i segnali del guardiano a posteriori (14/10):
                                              giorno, ora, stanza, minore, livello e
                                              categoria, mai le parole; --falso e --vero li
                                              segnano per la misura degli acuti falsi
    python -m calliope.stato --avvisi [--giorni N] [--falso ID]
                                              gli avvisi ai tutori (14/10): quando sono
                                              nati, tipo, minore, origine, consegna; --falso
                                              ferma un avviso non ancora arrivato
    python -m calliope.stato --eventi [--json]
                                              il registro degli eventi (10/10, in ombra:
                                              calliope/eventi/): MB per giorno, registri,
                                              «dimentica» con i residui (solo conteggi)
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
    python -m calliope.stato --memoria [--json] [--inventario FILE]
                                              il conto della memoria adesso (14/10, sola
                                              lettura, calliope/arbitro_memoria.py): chi la
                                              tiene, di che classe (tempo reale, vicino,
                                              sfondo, a richiesta), cosa farebbe l'arbitro
                                              per caricare un modello a richiesta; non
                                              scarica né carica niente
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


def guardia_main(cfg, argv: list[str], as_json: bool) -> int:
    """`--guardia` (14/10, passo 6 della conversazione di stanza): i segnali del guardiano a
    posteriori per la lettura di chi amministra, senza parole; `--falso ID` / `--vero ID` li
    segnano (una riga `guardia_lettura` nelle misure della stanza)."""
    from .stanza import guardia as g
    from .stanza import misure as m
    for flag, esito in (("--falso", "falso"), ("--vero", "vero")):
        if flag in argv:
            i = argv.index(flag)
            try:
                ident = argv[i + 1]
            except IndexError:
                print(f"{flag} vuole l'id del segnale (calliope stato --guardia)")
                return 1
            r = g.riassunto(m.leggi(cfg.turn_log_dir))
            if not any(str(s.get("id")) == ident for s in r["elenco"]):
                print(f"Nessun segnale con id {ident}.")
                return 1
            if not cfg.turn_log_dir:
                print("Nessuna cartella del registro dei turni (turn_log_dir).")
                return 1
            m.Misure(cfg.turn_log_dir, cfg.turn_log_days).scrivi("guardia_lettura",
                                                                 segnale=ident, esito=esito)
            print(f"Segnale {ident} segnato come {esito}.")
            if esito == "falso":
                # 14/10: l'avviso di quel segnale, se non è ancora arrivato, non arriva più
                n = _avviso_falso(cfg, f"guardia:{ident}")
                if n:
                    print(f"Il suo avviso non si consegna più ({n} tutori).")
            return 0
    giorni = None
    if "--giorni" in argv:
        try:
            giorni = max(1, int(argv[argv.index("--giorni") + 1]))
        except (IndexError, ValueError):
            print("--giorni vuole un numero")
            return 1
    r = g.riassunto(m.leggi(cfg.turn_log_dir, giorni))
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        return 0
    nomi = {}
    try:
        from .minori import _carica_profili
        nomi = {d.get("id"): d.get("name") for d in _carica_profili() if d.get("id")}
    except Exception:  # noqa: BLE001 — senza i profili, gli id
        pass
    print(g.elenco(r, nomi))
    print()
    print(g.testo(r, g.modo(cfg)))
    return 0


def _avviso_falso(cfg, rif: str) -> int:
    """Segna falso l'avviso con quel riferimento nel file della memoria (le righe di tutti i
    tutori). Quante righe; 0 senza file o senza avviso."""
    from pathlib import Path
    db = str(getattr(cfg, "memory_db", "") or "")
    if not db or not Path(db).exists():
        return 0
    from .minori import Avvisi
    av = Avvisi(db, log=lambda m: None, cfg=cfg)
    try:
        return av.segna_falso(rif)
    finally:
        av.close()


def avvisi_main(cfg, argv: list[str], as_json: bool) -> int:
    """`--avvisi` (14/10): gli avvisi ai tutori degli ultimi giorni, con id, quando sono nati,
    tipo, minore, origine, come e quando sono stati consegnati e se sono falsi; `--falso ID`
    segna falso un avviso (tutte le righe dei tutori): se non è ancora arrivato non arriva più.
    Il testo degli avvisi non ha mai le parole del minore."""
    import datetime
    from pathlib import Path
    from .minori import Avvisi, _carica_profili
    db = str(getattr(cfg, "memory_db", "") or "")
    if not db or not Path(db).exists():
        print("Nessun file della memoria: nessun avviso.")
        return 0
    av = Avvisi(db, log=lambda m: None, cfg=cfg)
    try:
        if "--falso" in argv:
            i = argv.index("--falso")
            d = av.leggi(argv[i + 1]) if i + 1 < len(argv) else None
            if d is None:
                print("--falso vuole l'id di un avviso (AV12: calliope stato --avvisi)")
                return 1
            n = av.segna_falso(d["rif"]) if d["rif"] else av.segna_falso_id(d["id"])
            print(f"Avviso AV{d['id']} segnato falso ({n} righe): se non è ancora arrivato non "
                  f"arriva più.")
            return 0
        giorni = 7
        if "--giorni" in argv:
            try:
                giorni = max(1, int(argv[argv.index("--giorni") + 1]))
            except (IndexError, ValueError):
                print("--giorni vuole un numero")
                return 1
        righe = av.recenti(giorni)
    finally:
        av.close()
    if as_json:
        print(json.dumps(righe, ensure_ascii=False, indent=2, default=str))
        return 0
    nomi = {}
    try:
        nomi = {x.get("id"): x.get("name") for x in _carica_profili() if x.get("id")}
    except Exception:  # noqa: BLE001 — senza i profili, gli id
        pass
    if not righe:
        print(f"Nessun avviso ai tutori negli ultimi {giorni} giorni.")
        return 0
    print(f"Avvisi ai tutori negli ultimi {giorni} giorni (il più recente prima):")
    for d in righe:
        stato = ("FALSO" if d["falso"] else "da consegnare" if not d["detto"] else
                 f"consegnato ({d['come'] or 'voce'}) {str(d['detto']).replace('T', ' ')[:16]}")
        print(f"  AV{d['id']}  {str(d['creato']).replace('T', ' ')[:16]}  {d['tipo']:<16} "
              f"{nomi.get(d['minore'], d['minore'])} -> {nomi.get(d['tutore'], d['tutore'])}"
              f"{'  urgente' if d['urgente'] else ''}  {stato}"
              + (f"  ({d['origine']})" if d["origine"] else ""))
    print("Per segnarne uno falso: calliope stato --avvisi --falso AV12")
    return 0


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


def memoria_main(cfg, argv: list[str], as_json: bool) -> int:
    """`--memoria`: il conto della memoria e le classi delle attività, in sola lettura (14/10,
    passo 1 dell'arbitro della memoria)."""
    from . import arbitro_memoria as am, macchina
    uso = am.da_config(cfg)
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
        uso.processo_gb = am.processo_servizio_gb()
    c = am.conto(inv, uso)
    if as_json:
        print(json.dumps({"inventario": inv, "memoria": c.as_json()}, ensure_ascii=False,
                         indent=2, default=str))
    else:
        print(am.testo(c))
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
        # Più voci vicino a un satellite (09/10, calliope/compagnia.py)
        from . import compagnia
        comp = compagnia.riassunto(turni)
        # Lo stato del dialogo in ombra (10/10, calliope/stato_dialogo.py): il modello chiama
        # proposta_rispondi? accordo con la decisione di oggi
        from . import stato_dialogo
        dialogo = stato_dialogo.riassunto(turni)
        # Una voce sola (10/10, calliope/eventi/misura.py): passo 0 e registro in ombra
        from .eventi import misura as misura_eventi
        voce_sola = misura_eventi.riassunto(turni)
        soglia_ms = float(getattr(cfg, "eventi_contesto_ms_avviso", 20.0) or 20.0)
        # La scelta dei tool come metrica (12/10, calliope/scelta_tool.py)
        from . import scelta_tool
        scelta = scelta_tool.per_giorno(turni)
        # Le frasi pronte ripetute (12/10, calliope/frasi.py, fase 0)
        from . import frasi
        pronte = frasi.riassunto(turni)
        # La conversazione di stanza (13/10, calliope/stanza/misure.py, passo 1): solo numeri
        from .stanza import misure as misure_stanza
        stanza = misure_stanza.riassunto(misure_stanza.leggi(cfg.turn_log_dir, giorni), turni)
        # La tenuta su disco (14/10, calliope/stanza/tenuta.py): righe, persone e MB dal file
        try:
            from .stanza.tenuta import conta_file
            stanza["tenuta"] = conta_file(cfg)
            # I conoscenti salvati (14/10, decisione 0030): quanti, dal file
            from .stanza.conoscenti import conta_file as conta_conoscenti
            stanza["conoscenti_salvati"] = conta_conoscenti(cfg)
            # L'audio del banco del passo 3 (eccezione del 14/10 sera): acceso, scaduto, file
            from .stanza.banco import stato_file as banco_file
            stanza["banco"] = banco_file(cfg)
        except Exception:  # noqa: BLE001 — i conteggi non fermano lo stato
            stanza["tenuta"] = None
        # Il guardiano a posteriori della stanza (14/10, passo 6): solo categorie e numeri
        from .stanza import guardia as guardia_stanza
        guardia_r = guardia_stanza.riassunto(misure_stanza.leggi(cfg.turn_log_dir, giorni))
        # La fine del turno System 1 (14/10, calliope/system1/fine_turno.py): ombra e attiva
        from .system1 import fine_turno as fine_turno_s1
        fine_r = fine_turno_s1.riassunto(turni)
        if as_json:
            print(json.dumps({"giorni": dati, "soglia_s": getattr(cfg, "latenza_avviso_s", None),
                              "attrito": sicurezza, "attrito_soglia": soglia_a,
                              "argomenti": argomenti, "compagnia": comp,
                              "dialogo": dialogo, "voce_sola": voce_sola,
                              "scelta_tool": scelta, "frasi_pronte": pronte,
                              "stanza": stanza, "fine_turno": fine_r,
                              "guardia": {k: v for k, v in guardia_r.items()
                                          if k not in ("elenco", "letture")}},
                             ensure_ascii=False, indent=2))
        else:
            print(latenza.testo(dati, soglia))
            print()
            print(attrito.testo(sicurezza, soglia_a))
            print()
            print(argomenti_incerti.testo(argomenti))
            print()
            print(compagnia.testo(comp))
            print()
            print(stato_dialogo.testo(dialogo))
            print()
            print(misura_eventi.testo(voce_sola, soglia_ms))
            print()
            print(scelta_tool.testo(scelta))
            print()
            print(frasi.testo(pronte))
            print()
            print(misure_stanza.testo(stanza))
            print()
            print(guardia_stanza.testo(guardia_r, guardia_stanza.modo(cfg)))
            print()
            print(fine_turno_s1.testo(fine_r))
        return 0
    if "--guardia" in argv:
        return guardia_main(cfg, argv, as_json)
    if "--avvisi" in argv:
        return avvisi_main(cfg, argv, as_json)
    if "--eventi" in argv:
        d = _eventi_disco(cfg)
        if as_json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            from .eventi.registro import testo_stato
            print(testo_stato(d, float(getattr(cfg, "eventi_avviso_mb", 50.0) or 0))
                  or "Registro degli eventi: nessuna tabella (spento, o mai partito).")
            for g in (d or {}).get("per_giorno") or ():
                print(f"    {g['giorno']}  {g['eventi']} eventi  {g['mb']:.3f} MB")
        return 0
    if "--piano" in argv:
        return piano_main(cfg, argv, as_json)
    if "--memoria" in argv:
        return memoria_main(cfg, argv, as_json)
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
        # La scelta dei tool oggi o ieri (12/10, calliope/scelta_tool.py)
        try:
            from . import scelta_tool
            avviso = scelta_tool.avviso_recente(cfg)
        except Exception:  # noqa: BLE001
            avviso = None
        if avviso:
            print()
            print(f"{avviso} Dettagli: --turni")
        # Quanto è conservato per le misure (12/10, calliope/conserva.py): solo conteggi
        try:
            from .conserva import Conservazione, testo_stato as conserva_testo
            riga = conserva_testo(Conservazione(cfg).stato())
        except Exception:  # noqa: BLE001 — lo stato non cade per la conservazione
            riga = None
        if riga:
            print()
            print(riga + " (dettagli: python -m calliope.conserva)")
        # Il registro degli eventi (10/10): crescita e «dimentica» (§ 10 del progetto)
        try:
            from .eventi.registro import testo_stato
            riga = testo_stato(_eventi_disco(cfg),
                               float(getattr(cfg, "eventi_avviso_mb", 50.0) or 0))
        except Exception:  # noqa: BLE001 — lo stato non cade per il registro
            riga = None
        if riga:
            print()
            print(riga + " Dettagli: --eventi")
    return 0


def _eventi_disco(cfg) -> dict | None:
    """Le guardie del registro degli eventi (crescita, dimentica), dal file dell'archivio."""
    from .conversazioni import percorso_db
    from .eventi.registro import stato_disco
    return stato_disco(percorso_db(cfg), 7, float(getattr(cfg, "eventi_avviso_mb", 50.0) or 0))


if __name__ == "__main__":
    sys.exit(main())
