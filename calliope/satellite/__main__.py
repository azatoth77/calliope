"""
`python -m calliope.satellite`: il satellite e la sua gestione.

Sul portatile (il satellite):
    python -m calliope.satellite [--server wss://IP:8771]
                                  avvia il satellite; la prima volta mostra un codice di
                                  abbinamento e aspetta che lo si scriva sul server

Sul server (dove gira Calliope; sulla DGX: calliope satellite …):
    python -m calliope.satellite --abbina 123456 --stanza studio [--personale Dario] [--pc]
                                  abbina il satellite che mostra quel codice; con
                                  --personale il suo schermo è personale di Dario (riceve
                                  promemoria, appuntamenti e documenti suoi); con --pc
                                  comanda il PC su cui gira (volume, file, documenti):
                                  senza, è solo voce (03/10)
    python -m calliope.satellite --modifica studio --personale Dario | --condiviso | --pc | --solo-voce
                                  rende personale (o della stanza) un satellite già
                                  abbinato e il suo schermo, senza rifare l'abbinamento
    python -m calliope.satellite --elenco         satelliti abbinati, impronta del server e,
                                  per un PC nuovo, la chiave e il comando da incollare in
                                  PowerShell (la stessa pagina: https://<server>:8771/installa
                                  o /satellite sul server degli schermi)
    python -m calliope.satellite --revoca studio  scollega (stanza, nome o numero)
    python -m calliope.satellite --certificato [--forza]
                                  crea certificato e chiave del server (openssl) e stampa
                                  l'impronta da confrontare con quella del satellite

Il codice non finisce nel registro dei turni. Il token non si stampa mai: sul server c'è solo
il suo SHA-256, sul satellite sta in satellite.json (fuori da git).
"""

import shutil
import subprocess
import sys
from pathlib import Path


def _arg(argv, nome):
    if nome in argv:
        i = argv.index(nome)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1]
        return ""
    return None


def _openssl() -> str | None:
    exe = shutil.which("openssl")
    if exe:
        return exe
    if sys.platform == "win32":                 # quello di Git per Windows
        for p in (r"C:\Program Files\Git\usr\bin\openssl.exe",
                  r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
            if Path(p).is_file():
                return p
    return None


def certificato(cfg, forza: bool = False, out=print) -> int:
    """Certificato autofirmato (EC P-256, 10 anni) e chiave del server, con openssl: niente
    `cryptography` (codice nativo da verificare su ARM). Il satellite non usa CA: fissa
    l'impronta SHA-256, vista all'abbinamento o scritta in satellite_impronta."""
    from . import protocollo as P
    from .server import percorso
    import ssl
    cert, chiave = percorso(cfg, cfg.satellite_tls_cert), percorso(cfg, cfg.satellite_tls_chiave)
    if cert.is_file() and chiave.is_file() and not forza:
        der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
        out(f"Il certificato c'è già ({cert}). Impronta SHA-256:\n  {P.impronta_der(der)}")
        out("Per rifarlo: --certificato --forza (poi i satelliti vanno abbinati di nuovo).")
        return 0
    exe = _openssl()
    if exe is None:
        out("Manca openssl: " + ("sudo apt install openssl." if sys.platform != "win32" else
                                 "installa Git per Windows (lo contiene) o OpenSSL."))
        return 1
    r = subprocess.run([exe, "req", "-x509", "-newkey", "ec", "-pkeyopt",
                        "ec_paramgen_curve:prime256v1", "-nodes", "-days", "3650",
                        "-subj", "/CN=calliope", "-keyout", str(chiave), "-out", str(cert)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not cert.is_file():
        out(f"openssl non è riuscito: {(r.stderr or r.stdout).strip()[-300:]}")
        return 1
    if sys.platform != "win32":
        chiave.chmod(0o600)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
    out(f"Creati {cert.name} e {chiave.name} in {cert.parent}.")
    out(f"Impronta SHA-256 (il satellite la mostra quando chiede l'abbinamento):\n"
        f"  {P.impronta_der(der)}")
    out("Ora in calliope.locale.yaml: satellite_indirizzo: 0.0.0.0, poi riavvia Calliope.")
    return 0


def _impronta(cfg) -> str:
    from .server import contesto_tls
    try:
        return contesto_tls(cfg)[1]
    except ValueError:
        return ""


def gestione(argv, out=print, cfg=None) -> int:
    from ..stato import _config
    from .archivio import ArchivioSatelliti
    cfg = cfg or _config(quiet=True)
    if "--certificato" in argv:
        return certificato(cfg, "--forza" in argv, out)
    if not cfg.memory_db:
        out("La memoria è spenta (memory_db vuoto): i satelliti non hanno dove stare.")
        return 1
    arch = ArchivioSatelliti(cfg.memory_db, cfg.satellite_codice_min)
    try:
        persona = None
        if _arg(argv, "--personale"):
            from ..schermi.__main__ import _persona
            persona = _persona(cfg, _arg(argv, "--personale"))
            if persona is None:
                out(f"Non conosco «{_arg(argv, '--personale')}»: deve avere la voce registrata "
                    f"(speakers.json).")
                return 1
        if "--modifica" in argv:
            via = arch.trova(_arg(argv, "--modifica") or "")
            if len(via) != 1:
                out("Nessun satellite con quel nome o in quella stanza." if not via else
                    "Più satelliti corrispondono: usa il nome o il numero (--elenco).")
                return 1
            if "--pc" in argv or "--solo-voce" in argv:
                s = arch.imposta_ruolo(via[0]["id"], "pc" if "--pc" in argv else None)
                out(f"Fatto: il satellite «{s['nome']}» "
                    + ("comanda il PC (volume, file, documenti)." if "--pc" in argv
                       else "è solo voce: non comanda il PC.")
                    + " Vale dal prossimo collegamento.")
                if persona is None and "--condiviso" not in argv:
                    return 0
            if persona is None and "--condiviso" not in argv:
                out("Dimmi --personale <nome> oppure --condiviso (o --pc, --solo-voce).")
                return 1
            s = arch.imposta_proprietario(via[0]["id"], *(persona or (None, None)))
            out(f"Fatto: lo schermo del satellite «{s['nome']}» è "
                + (f"personale di {s['proprietario_nome']}." if persona else "della stanza.")
                + " Se è collegato, cambia entro qualche secondo.")
            return 0
        if "--abbina" in argv:
            res = arch.abbina(_arg(argv, "--abbina") or "", _arg(argv, "--stanza") or "",
                              *(persona or (None, None)), ruolo="pc" if "--pc" in argv else None)
            msg = {"abbinato": "Abbinato: {nome} (stanza {stanza}).",
                   "sbagliato": "Nessun satellite in attesa con questo codice.",
                   "troppi": "Troppi codici sbagliati: annullati tutti, i satelliti ne "
                             "chiedono uno nuovo.",
                   "formato": "Il codice ha 6 cifre.",
                   "stanza": "Manca la stanza: --stanza studio."}[res["esito"]]
            out(msg.format(**res.get("satellite", res.get("schermo", {}))) if res["ok"] else msg)
            chiesto = res.get("personale_chiesto")
            if res["ok"]:
                out("Comanda il PC su cui gira (volume, file, documenti)." if "--pc" in argv
                    else "È solo voce: per fargli comandare il PC su cui gira, --modifica "
                         f"{res['schermo']['nome']} --pc.")
            if res["ok"] and persona is not None:
                out(f"Lo schermo del satellite sarà personale di {persona[1]}.")
            elif res["ok"] and chiesto:
                # La richiesta del satellite non vale da sola: la conferma chi amministra
                out(f"Il satellite chiede uno schermo personale di {chiesto}: non l'ho fatto. "
                    f"Per confermarlo: python -m calliope.satellite --modifica "
                    f"{res['schermo']['nome']} --personale {chiesto}")
            imp = _impronta(cfg)
            if res["ok"] and imp:
                out(f"Impronta di questo server: {imp[:23]}… (deve coincidere con quella "
                    f"stampata dal satellite accanto al codice)")
            return 0 if res["ok"] else 1
        if "--revoca" in argv:
            via = arch.revoca(_arg(argv, "--revoca") or "")
            if not via:
                out("Nessun satellite con quel nome o in quella stanza.")
                return 1
            out("Revocato: " + ", ".join(s["nome"] for s in via) + ". Se è collegato, la "
                "connessione si chiude entro qualche secondo.")
            schermi = [n for s in via for n in s.get("schermi", [])]
            if schermi:
                out("Revocato anche il suo schermo: " + ", ".join(schermi) + ".")
            return 0
        rows = arch.elenco()
        if not rows:
            out("Nessun satellite abbinato. Sul portatile: python -m calliope.satellite, poi "
                "qui: python -m calliope.satellite --abbina <codice> --stanza <stanza>.")
        else:
            from ..schermi.archivio import avviso_inattivi, quando
            giorni = float(getattr(cfg, "schermi_inattivi_giorni", 7.0) or 0)
            vecchi = {s["id"] for s in arch.inattivi(giorni)}
            out(f"{'N.':4}{'NOME':24}{'STANZA':16}ULTIMA CONNESSIONE")
            for r in rows:
                out(f"{r['id']:<4}{r['nome']:24}{r['stanza']:16}{quando(r.get('visto'))}"
                    + ("  <- inattivo" if r["id"] in vecchi else ""))
            riga = avviso_inattivi([r for r in rows if r["id"] in vecchi], "satelliti",
                                   giorni, "calliope satellite --revoca")
            if riga:
                out("\n" + riga)
        imp = _impronta(cfg)
        out(f"\nModo audio: {cfg.audio_modo}; server su {cfg.satellite_indirizzo}:"
            f"{cfg.satellite_porta}" + (f"; impronta TLS {imp}" if imp else "; senza TLS"))
        nuovo_pc(cfg, out)
        return 0
    finally:
        arch.close()


def nuovo_pc(cfg, out=print):
    """Le righe per un PC nuovo (pagina /satellite, calliope/satellite/web.py): la chiave da
    confrontare con quella della pagina e il comando, da copiare anche da una sessione ssh."""
    from ..schermi import ip_lan
    from .web import comando_powershell, problema
    motivo = problema(cfg)
    if motivo:
        out(f"PC nuovi come satellite: non ancora ({motivo})")
        return
    from .web import chiave
    k = chiave(cfg)
    host = ip_lan() or "<indirizzo del server>"
    porta = int(cfg.satellite_porta)
    out(f"Chiave per i PC nuovi: {k}")
    out(f"  (deve essere identica a quella della pagina https://{host}:{porta}/installa o "
        f"https://{host}:{getattr(cfg, 'schermi_porta', 8770)}/satellite)")
    out("  Comando per PowerShell sul PC nuovo:")
    out("  " + comando_powershell(host, porta, k))


def scegli_dispositivi(cfg, out=print, query=None) -> dict:
    """Microfono e uscita del satellite: quelli scelti (satellite_microfono e satellite_casse,
    già copiati in input_device e output_device da config.dispositivi_satellite; anche per
    nome, come «C920 MME» di avvia_satellite.py) se ci sono, altrimenti i predefiniti del sistema, come
    main.check_audio_devices. Il 02/10, senza la webcam, il satellite ripeteva all'infinito
    «microfono non disponibile: riprovo tra 2 secondi». Stampa cosa usa e restituisce
    {etichetta: nome}. `query` è sounddevice.query_devices (le prove ne passano uno finto)."""
    if query is None:
        try:
            import sounddevice as sd
        except (ImportError, OSError):
            return {}
        query = sd.query_devices
    nomi = {}
    for kind, attr, label in (("input", "input_device", "microfono"),
                              ("output", "output_device", "uscita")):
        dev = getattr(cfg, attr)
        nota = ""
        if dev is not None:
            try:
                nomi[label] = query(dev, kind)["name"]
                out(f"[AUDIO] {label}: {nomi[label]}")
                continue
            except Exception:  # noqa: BLE001 — spento, scollegato, nome sbagliato
                nota = f" («{dev}» non trovato: spento o scollegato?)"
                setattr(cfg, attr, None)
        try:
            nomi[label] = query(kind=kind)["name"]
            out(f"[AUDIO] {label}: {nomi[label]}, quello predefinito{nota}")
        except Exception:  # noqa: BLE001 — nessun predefinito: lo dirà l'apertura del flusso
            out(f"[AUDIO] {label}: nessuno predefinito{nota}")
    return nomi


def avvia_satellite(argv, out=print, predefiniti: dict | None = None) -> int:
    """`predefiniti`: microfono, casse e webcam se la configurazione non li sceglie
    ({"satellite_microfono": "C920 MME", …}, da avvia_satellite.py)."""
    from ..config import dispositivi_satellite, load_config
    cfg = load_config()
    server = _arg(argv, "--server")
    if server:
        cfg.satellite_server = server
    dispositivi_satellite(cfg, predefiniti)
    scegli_dispositivi(cfg, out)
    try:
        from .client import Satellite
        sat = Satellite(cfg, log=lambda m: out(m))
    except FileNotFoundError as e:
        out(f"Manca un modello: {e}. La wake word serve sul satellite (wakeword/modelli/: "
            f"calliope.onnx, melspectrogram.onnx, embedding_model.onnx).")
        return 1
    except ImportError as e:
        out(f"Manca una libreria ({e.name}): sul satellite bastano numpy, sounddevice, "
            f"onnxruntime, websockets e pyyaml (setup/satellite/installa.ps1).")
        return 1
    out(f"Satellite di {cfg.name}: server {cfg.satellite_server}. Ctrl+C per chiudere.")
    try:
        sat.esegui()
    except KeyboardInterrupt:
        sat.ferma()
        out("\nSatellite spento.")
    if sat.riavvio:
        from .aggiorna import RIAVVIA
        return RIAVVIA              # avvio.py passa alla versione nuova (in prova)
    return 0


def main(argv=None, predefiniti: dict | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if {"-h", "--help", "/?"} & set(argv):
        print(__doc__.strip())
        return 0
    if {"--abbina", "--revoca", "--elenco", "--certificato", "--modifica"} & set(argv):
        return gestione(argv)
    return avvia_satellite(argv, predefiniti=predefiniti)


if __name__ == "__main__":
    sys.exit(main())
