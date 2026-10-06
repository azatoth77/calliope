"""
`python -m calliope.schermi`: gli schermi da terminale (stesso file della memoria, anche
mentre Calliope è accesa).

    python -m calliope.schermi                       elenco degli schermi abbinati
    python -m calliope.schermi --abbina 123456 --stanza soggiorno [--personale Dario]
                                                     abbina lo schermo che mostra quel codice
    python -m calliope.schermi --revoca cucina       scollega (stanza, nome o numero)
    python -m calliope.schermi --kiosk soggiorno [--personale Dario]
                                                     schermo nuovo già abbinato, con il comando
                                                     per Edge in kiosk (il token si vede solo
                                                     qui, una volta)
    python -m calliope.schermi --certificato [--host IP] [--host nome] [--forza]
                                                     CA di casa e certificato della pagina
                                                     per i telefoni (web app /telefono):
                                                     la CA si installa una volta sul telefono.
                                                     Più --host (o «IP1,IP2»): tutti gli
                                                     indirizzi da cui il telefono apre la
                                                     pagina, anche quello del satellite che
                                                     fa da inoltro (satellite_inoltro)

Il codice non finisce nel registro dei turni né altrove. Con --kiosk il token si stampa una
volta sola, perché va scritto nel collegamento di avvio di Edge (in kiosk Edge è InPrivate e
dimentica tutto a ogni avvio): chi lo vede può fingersi quello schermo, e si revoca con
--revoca.
"""

import sys


def _arg(argv, nome):
    if nome in argv:
        i = argv.index(nome)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1]
        return ""
    return None


def _persona(cfg, nome):
    """(id, nome) del profilo in speakers.json, letto senza numpy né modelli."""
    import json
    from pathlib import Path
    p = Path(getattr(cfg, "config_dir", ".")) / "speakers.json"
    if not p.is_file():
        p = Path("speakers.json")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for d in data if isinstance(data, list) else []:
        if str(d.get("name", "")).lower() == str(nome).strip().lower():
            return d.get("id"), d.get("name")
    return None


def telefono_stato(cfg, out=print):
    """Una riga sulla web app del telefono: dove aprirla, o cosa manca."""
    try:
        from .telefono import stato
    except ImportError:                    # starlette non c'è: niente pagina del telefono
        return
    from . import url_schermi
    st = stato(cfg)
    if st["pronto"]:
        out(f"Telefono: {url_schermi(cfg)}/telefono" + ("" if st["ca"] else
            " (per installarla bene sul telefono: --certificato, la CA di casa)"))
    else:
        out("Telefono: " + "; ".join(st["manca"]))


def main(argv=None, out=print) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if {"-h", "--help", "/?"} & set(argv):
        out(__doc__.strip())
        return 0
    from ..stato import _config
    from . import url_schermi
    from .archivio import ArchivioSchermi
    cfg = _config(quiet=True)
    if "--certificato" in argv:
        from .tls import certificato_telefono
        # Più indirizzi: --host ripetuto o separati da virgole (IP della DGX in VPN e IP del
        # portatile di casa che fa da inoltro per il telefono: satellite_inoltro)
        hosts = [h.strip() for i, a in enumerate(argv[:-1]) if a == "--host"
                 for h in argv[i + 1].split(",") if h.strip()]
        return certificato_telefono(cfg, hosts, "--forza" in argv, out)
    if not cfg.memory_db:
        out("La memoria è spenta (memory_db vuoto): gli schermi non hanno dove stare.")
        return 1
    arch = ArchivioSchermi(cfg.memory_db, cfg.schermi_codice_min)
    owner = owner_name = None
    who = _arg(argv, "--personale")
    if who:
        found = _persona(cfg, who)
        if not found:
            out(f"Non trovo «{who}» tra le persone registrate (speakers.json).")
            return 1
        owner, owner_name = found
    try:
        if "--abbina" in argv:
            code, room = _arg(argv, "--abbina") or "", _arg(argv, "--stanza") or ""
            res = arch.abbina(code, room, owner, owner_name)
            msg = {"abbinato": "Abbinato: {nome} (stanza {stanza}).",
                   "sbagliato": "Nessuno schermo in attesa con questo codice.",
                   "troppi": "Troppi codici sbagliati: annullati tutti, gli schermi ne "
                             "mostrano uno nuovo.",
                   "formato": "Il codice ha 6 cifre.",
                   "stanza": "Manca la stanza: --stanza soggiorno."}[res["esito"]]
            out(msg.format(**res.get("schermo", {})) if res["ok"] else msg)
            if res["ok"]:
                out("Se Calliope è accesa, lo schermo si collega da solo entro pochi secondi.")
            return 0 if res["ok"] else 1
        if "--revoca" in argv:
            via = arch.revoca(_arg(argv, "--revoca") or "")
            if not via:
                out("Nessuno schermo con quel nome o in quella stanza.")
                return 1
            out("Scollegato: " + ", ".join(s["nome"] for s in via) + ". Se la sua pagina è "
                "aperta torna all'abbinamento entro qualche secondo.")
            if any(s.get("satellite") is not None for s in via):
                out("È lo schermo di un satellite: quando si ricollega ne riceve uno nuovo. "
                    "Per non averlo più: satellite_schermo: no sul satellite, oppure revoca il "
                    "satellite (calliope satellite --revoca), che toglie anche il suo schermo.")
            return 0
        if "--kiosk" in argv:
            room = _arg(argv, "--kiosk") or _arg(argv, "--stanza") or ""
            s, token = arch.crea_con_token(room, owner, owner_name)
            url = f"{url_schermi(cfg)}/#t={token}"
            out(f"Schermo «{s['nome']}» abbinato. Collegamento di avvio (tienilo per te: "
                f"chi lo ha può fingersi questo schermo; si revoca con --revoca):")
            if sys.platform == "win32":
                out(f'  msedge.exe --kiosk "{url}" --edge-kiosk-type=fullscreen '
                    f'--no-first-run')
            else:                     # Linux (DGX OS, 02/10): Chromium o Chrome
                out(f'  chromium --kiosk --incognito --no-first-run "{url}"')
            if url.startswith("https"):
                # Certificato autofirmato (schermi/tls.py): il kiosk InPrivate non ricorda
                # l'eccezione. Meglio un satellite (ponte TLS) o un profilo normale
                out("  In HTTPS con il certificato autofirmato il browser chiede di accettarlo "
                    "(in kiosk InPrivate a ogni avvio): meglio aprirla da un satellite, che "
                    "verifica l'impronta da sé.")
            return 0
        rows = arch.elenco()
        if not rows:
            out(f"Nessuno schermo abbinato. Apri {url_schermi(cfg)} sul PC o sul tablet e "
                f"di' a Calliope il codice che compare, oppure: python -m calliope.schermi "
                f"--abbina <codice> --stanza <stanza>.")
            telefono_stato(cfg, out)
            return 0
        # Con l'ultimo collegamento e il satellite che lo apre (05/10): gli abbinamenti doppi
        # o abbandonati si vedono, e chi amministra decide cosa revocare
        from .archivio import avviso_inattivi, quando
        giorni = float(getattr(cfg, "schermi_inattivi_giorni", 7.0) or 0)
        vecchi = {s["id"] for s in arch.inattivi(giorni)}
        out(f"{'N.':4}{'NOME':28}{'STANZA':16}{'PERSONALE DI':14}{'SATELLITE':11}"
            f"ULTIMO COLLEGAMENTO")
        for r in rows:
            sat = f"n. {r['satellite']}" if r.get("satellite") is not None else "-"
            out(f"{r['id']:<4}{r['nome']:28}{r['stanza']:16}"
                f"{(r.get('proprietario_nome') or '-'):14}{sat:11}{quando(r.get('visto'))}"
                + ("  <- inattivo" if r["id"] in vecchi else ""))
        riga = avviso_inattivi([r for r in rows if r["id"] in vecchi], "schermi", giorni,
                               "calliope schermi --revoca")
        if riga:
            out("\n" + riga)
        out(f"\nPagina: {url_schermi(cfg)}")
        telefono_stato(cfg, out)
        return 0
    except ValueError as e:
        out(f"Errore: {e}")
        return 1
    finally:
        arch.close()


if __name__ == "__main__":
    sys.exit(main())
