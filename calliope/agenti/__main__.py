"""
`python -m calliope.agenti --prova`: prova il collegamento con l'agente e basta.

Fa SOLO questo: legge la configurazione (calliope.yaml, calliope.locale.yaml, dgx.yaml),
apre il tunnel SSH se il collegamento è «tunnel», chiede al server del modello la versione
e i modelli (Ollama: `/api/version` e `/api/tags`; motore «openai», vLLM: `/version` e
`/v1/models`), dice se il modello dell'agente c'è, chiude il tunnel. Non avvia Calliope, non
scarica niente, non manda prompt al modello. Non stampa mai l'indirizzo, l'utente o la
chiave della DGX (stanno in .ssh\\config, sotto l'alias).

    python -m calliope.agenti --prova
"""

import contextlib
import sys
import time


def prova(out=print) -> int:
    from ..config import load_config
    from .impostazioni import ConfigAgentiNonValida, carica, percorso_file, ssh_eseguibile
    from .remoto import ErroreOllama, crea_cliente
    from .servizio import MOTIVI
    from .tunnel import Tunnel, descrivi_comando

    with contextlib.redirect_stdout(sys.stderr):
        cfg = load_config()
    try:
        imp = carica(cfg)
    except ConfigAgentiNonValida as e:
        out(f"Configurazione dell'agente non valida: {e}.")
        return 2
    if imp is None:
        path = percorso_file(cfg)
        out("Nessun agente configurato: "
            + (f"non trovo {path}" if path else "manca il file della DGX")
            + " e agenti_url è vuoto.")
        return 2
    for a in imp.avvisi:
        out(f"Avviso: {a}")
    out(f"Agente: {imp.modello} ({imp.origine}), collegamento «{imp.modo}», motore "
        f"«{imp.motore}».")
    tunnel = None
    try:
        if imp.tunnel:
            ssh = ssh_eseguibile()
            if not ssh:
                motivo, passo = MOTIVI["ssh_mancante"]
                out(f"NO  {motivo}. {passo}")
                return 1
            tunnel = Tunnel(imp.ssh_alias, imp.porta_locale, imp.porta_remota, imp.timeout_s,
                            ssh=ssh, log=lambda m: None)
            out(f"Apro il tunnel: {descrivi_comando(tunnel)}")
            t0 = time.perf_counter()
            code = tunnel.assicura(imp.timeout_s)
            if code != "ok":
                motivo, passo = MOTIVI.get(code, MOTIVI["ssh_errore"])
                out(f"NO  tunnel non aperto ({code}): {motivo}. {passo}")
                return 1
            out(f"ok  tunnel aperto in {time.perf_counter() - t0:.1f} s sulla porta locale "
                f"{imp.porta_locale}")
        cliente = crea_cliente(imp)
        try:
            t0 = time.perf_counter()
            ver = cliente.versione(timeout=imp.timeout_s)
            chi = (f"Ollama {ver}" if imp.motore == "ollama"
                   else f"Il server OpenAI ({ver if ver != '?' else 'versione ignota'})")
            out(f"ok  {chi} risponde ({(time.perf_counter() - t0) * 1000:.0f} ms)")
            nomi = cliente.modelli(timeout=imp.timeout_s)
        except ErroreOllama as e:
            predef = "ollama_errore" if imp.motore == "ollama" else "motore_errore"
            motivo, passo = MOTIVI.get(e.codice, MOTIVI[predef])
            out(f"NO  {motivo}. {passo}")
            return 1
        finally:
            cliente.close()
        out(f"ok  {len(nomi)} modelli " + ("installati" if imp.motore == "ollama" else "serviti"))
        esito = 0
        for ruolo, m in (("agente", imp.modello), ("scrittore", imp.modello_scrittore)):
            if ruolo == "scrittore" and m == imp.modello:
                continue
            if cliente.ha(nomi, m):
                out(f"ok  il modello {ruolo} {m} c'è")
            elif imp.motore == "ollama":
                out(f"NO  manca il modello {ruolo} {m}: scaricalo sulla macchina dell'agente "
                    f"con ollama pull {m}")
                esito = 1
            else:
                out(f"NO  il server non serve il modello {ruolo} {m} (serve: "
                    f"{', '.join(nomi) or 'nessuno'}): avvialo con quel nome o correggi "
                    f"agente_modello")
                esito = 1
        if esito == 0:
            out("Tutto pronto: Calliope può delegare i lavori lunghi.")
        return esito
    finally:
        if tunnel is not None:
            tunnel.chiudi()
            out("Tunnel chiuso.")


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if "--prova" in argv:
        return prova()
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
