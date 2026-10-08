"""
La casa comandata e letta a voce (direzione «Calliope → Home Assistant»).

- base.py: l'interfaccia di capacità `HomeBackend` (entità, comando, diagnosi);
- homeassistant.py: l'adattatore Home Assistant (WebSocket, TLS, verifica a secco);
- regole.py: cosa Calliope non comanda mai (domini delicati, ospiti, non esposte);
- parole.py: stati e risposte in italiano, ricerca locale per casa_stato;
- nomi.py: il dispositivo detto, cercato tra le esposte quando HA capisce il comando ma non
  trova i dispositivi (nome dell'entità in un'area diversa dalla stanza detta, 08/10);
- guida.py: come si collega, a voce e per iscritto.

I tool vocali sono in calliope/tools/casa.py. La direzione opposta (Home Assistant che usa
Calliope come agente per i satelliti) non è fatta: l'interfaccia resta indipendente da HA
e non lo impedisce.

Il token si legge solo dalla variabile d'ambiente CALLIOPE_HA_TOKEN o dal file dei segreti
(`segreti_file`, predefinito segreti.yaml accanto al file di configurazione, fuori da
git):

    home_assistant:
      token: "…"

Mai da calliope.yaml, mai nei log.
"""

import os

from .base import CasaNonRisponde, Diagnosi, Entita, Esito, HomeBackend, Interpretazione
from .guida import MOTIVI, STATI, passo

__all__ = ["CasaNonRisponde", "Diagnosi", "Entita", "Esito", "HomeBackend", "Interpretazione",
           "diagnose", "load_casa", "read_token", "secrets_path"]

TOKEN_ENV = "CALLIOPE_HA_TOKEN"


def secrets_path(cfg) -> str:
    """Il file dei segreti: assoluto così com'è, relativo alla cartella del file di
    configurazione in uso (calliope.yaml o CALLIOPE_CONFIG)."""
    name = getattr(cfg, "segreti_file", None) or "segreti.yaml"
    if os.path.isabs(name):
        return name
    base = getattr(cfg, "config_dir", None) or os.getcwd()
    return os.path.join(base, name)


def read_token(cfg) -> tuple[str | None, str, dict | None]:
    """(token, da dove, errore). La variabile d'ambiente vince sul file. L'errore dice
    solo file e riga: il messaggio di PyYAML può contenere il testo della riga, cioè il
    token, e non si stampa."""
    env = (os.environ.get(TOKEN_ENV) or "").strip()
    if env:
        return env, f"variabile d'ambiente {TOKEN_ENV}", None
    path = secrets_path(cfg)
    if not os.path.exists(path):
        return None, path, None
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001
        mark = getattr(e, "problem_mark", None)
        return None, path, {"file": path, "riga": (mark.line + 1) if mark else None}
    section = data.get("home_assistant") if isinstance(data, dict) else None
    token = section.get("token") if isinstance(section, dict) else None
    if token is not None and not isinstance(token, str):
        return None, path, {"file": path, "riga": None}
    token = (token or "").strip()
    return (token or None), path, None


def _static(cfg) -> Diagnosi | None:
    """I controlli che non hanno bisogno della rete: configurazione, librerie, token."""
    if not getattr(cfg, "casa_enabled", False):
        return Diagnosi("spenta")
    try:
        import websockets  # noqa: F401
    except ImportError:
        return Diagnosi("mancante", {"libreria": "websockets"})
    if not (getattr(cfg, "casa_url", None) or "").strip():
        return Diagnosi("senza_indirizzo")
    token, where, err = read_token(cfg)
    if err:
        return Diagnosi("segreti_illeggibili", err)
    if not token:
        return Diagnosi("senza_token", {"file": where})
    return None


def diagnose(cfg, backend: HomeBackend | None = None, riprova: bool = False,
             esempio: str = "") -> dict:
    """A che punto è l'integrazione con la casa. Funzione pura e riusabile (il registro
    delle capacità): campi stabili
      stato           "attiva" | "da_configurare" | "mancante" | "guasta"
      codice          il caso preciso (guida.STATI)
      motivo          breve, per i log
      prossimo_passo  frase per la voce, per chi amministra
      dettagli        per chi amministra (mai il token)
    Senza backend rilegge configurazione e segreti: dopo aver creato segreti.yaml dice
    «riavviami» invece di «manca il token»."""
    if backend is None:
        d = _static(cfg) or Diagnosi("riavvio")
    else:
        d = backend.diagnosi(riprova=riprova)
    details = dict(d.dettagli)
    if getattr(cfg, "casa_url", None):
        details.setdefault("url", cfg.casa_url)
    return {"funzione": "casa", "stato": STATI.get(d.codice, "guasta"), "codice": d.codice,
            "motivo": MOTIVI.get(d.codice, d.codice), "prossimo_passo":
            passo(d.codice, d.dettagli, esempio), "dettagli": details}


def _print(msg: str):
    print(msg, flush=True)


def load_casa(cfg, log=_print) -> tuple[HomeBackend | None, dict]:
    """L'adattatore della casa (già in collegamento in secondo piano) e la diagnosi
    iniziale. Senza indirizzo o token è None: i tool casa_comando e casa_stato non ci
    sono, resta casa_integrazione per spiegare cosa manca. Calliope parte comunque."""
    from .. import capacita
    d = _static(cfg)
    if d is not None:
        # Lo stato va nel registro delle capacità: il riassunto dell'avvio lo dice
        diag = diagnose(cfg)
        capacita.REGISTRO.da_dict(capacita.check_casa(cfg))
        return None, diag
    token, where, _ = read_token(cfg)
    from .homeassistant import HomeAssistantBackend
    try:
        backend = HomeAssistantBackend(
            cfg.casa_url, token, agente=cfg.casa_agente, lingua=cfg.language,
            timeout_s=cfg.casa_timeout_s, connessione_s=cfg.casa_connessione_s,
            tls_nome=cfg.casa_tls_nome, tls_impronta=cfg.casa_tls_impronta,
            tls_verifica=cfg.casa_tls_verifica, tls_ca=cfg.casa_tls_ca,
            aggiorna_s=cfg.casa_aggiorna_s, log=log)
    except ValueError as e:
        capacita.segnala("casa", "da_configurare", str(e), passo("senza_indirizzo"))
        return None, {"funzione": "casa", "stato": "da_configurare", "codice": "senza_indirizzo",
                      "motivo": str(e), "prossimo_passo": passo("senza_indirizzo"),
                      "dettagli": {"url": cfg.casa_url}}
    if backend.tls and not cfg.casa_tls_verifica and not cfg.casa_tls_impronta:
        log("[CASA] ATTENZIONE: verifica del certificato di Home Assistant spenta "
            "(casa_tls_verifica: false). Meglio casa_tls_nome o casa_tls_impronta.")
    if not backend.tls:
        log("[CASA] ATTENZIONE: Home Assistant in http, senza cifratura: il token viaggia in "
            "chiaro sulla rete di casa.")
    log(f"[CASA] Home Assistant: mi collego in secondo piano a {backend.url}"
        + (f" (certificato per {cfg.casa_tls_nome})" if cfg.casa_tls_nome else "")
        + f"; token da {where if where.startswith('variabile') else os.path.basename(where)}.")
    backend.avvia()
    # Il collegamento va avanti in secondo piano: le viste a voce e da terminale chiedono lo
    # stato fresco; il prompt resta quello dell'avvio (i tool della casa ci sono)
    capacita.REGISTRO.da_dict(capacita.check_casa(cfg, backend))
    capacita.REGISTRO.dinamica("casa", lambda: capacita.check_casa(cfg, backend))
    return backend, diagnose(cfg, backend)
