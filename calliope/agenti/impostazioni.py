"""
Dove sta l'agente e come ci si arriva: le impostazioni di questa installazione (02/10/2026).

Due modi, scelti dalla configurazione:

- **file della DGX** (`agenti_config_file`, predefinito `dgx.yaml` accanto a calliope.yaml,
  fuori da git): sezione `dgx` con l'alias SSH, il collegamento («tunnel» o «diretto»), il
  motore («ollama», API nativa sulla 11434, oppure «openai», vLLM o llama.cpp sulla 8000:
  `remoto_openai.py`), le porte, i modelli e il tempo massimo. Utente, indirizzo e chiave **non** ci sono: stanno
  in `%USERPROFILE%\\.ssh\\config`, sotto l'alias, e Calliope non li legge mai;
- **indirizzo diretto** (`agenti_url`): un Ollama raggiungibile senza tunnel, per esempio
  una DGX in casa in LAN (`http://<IP>:11434`) o lo stesso Ollama della voce
  (`http://127.0.0.1:11434`, il caso «senza DGX» delle prove). Vince sul file. Un
  indirizzo che finisce con `/v1` è un server compatibile OpenAI (motore «openai»).

`carica(cfg)` restituisce un `Impostazioni` o None (nessun agente configurato), e non
solleva: un file rovinato diventa `errore` con la riga, mai il contenuto.

Le prove non leggono il dgx.yaml vero: il runner punta `CALLIOPE_AGENTI_CONFIG` a un file
che non c'è, e una `Config()` costruita a mano (senza `load_config`, quindi senza
`config_dir`) non cerca nessun file.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_SEZIONE = "dgx"


@dataclass
class Impostazioni:
    modo: str                         # "tunnel" | "diretto"
    url: str                          # dove parla il client HTTP (nel tunnel: 127.0.0.1:porta_locale)
    modello: str
    scrittore: str = ""               # modello dei documenti; vuoto = lo stesso dell'agente
    ssh_alias: str = ""
    porta_locale: int = 11435
    porta_remota: int = 11434
    timeout_s: float = 5.0
    origine: str = ""                 # «dgx.yaml» oppure «agenti_url»: per i messaggi
    nome: str = "la DGX"              # come si chiama a voce la macchina dell'agente
    avvisi: list[str] = field(default_factory=list)
    motore: str = "ollama"            # "ollama" (API nativa) | "openai" (vLLM, llama.cpp: /v1)

    @property
    def tunnel(self) -> bool:
        return self.modo == "tunnel"

    @property
    def modello_scrittore(self) -> str:
        return self.scrittore or self.modello

    @property
    def su_nome(self) -> str:
        """«sulla DGX», «su questo computer»: la preposizione giusta per la voce."""
        n = self.nome.strip()
        for art, prep in (("la ", "sulla "), ("il ", "sul "), ("lo ", "sullo "),
                          ("l'", "sull'")):
            if n.lower().startswith(art):
                return prep + n[len(art):]
        return "su " + n


class ConfigAgentiNonValida(Exception):
    """Il file della DGX c'è ma non si può usare: il messaggio dice perché (mai i valori)."""


def percorso_file(cfg) -> Path | None:
    """Il file della DGX, o None se non va cercato (Config costruita a mano: prove)."""
    name = getattr(cfg, "agenti_config_file", None)
    if not name:
        return None
    p = Path(name)
    if p.is_absolute():
        return p
    base = getattr(cfg, "config_dir", None)
    if base is None:
        return None
    return Path(base) / p


def _locale(url: str) -> bool:
    host = url.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0].strip("[]").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def carica(cfg) -> Impostazioni | None:
    """Le impostazioni dell'agente, o None se non ce n'è uno configurato. Solleva
    ConfigAgentiNonValida se il file c'è ma è rovinato o incompleto."""
    if not getattr(cfg, "agenti_enabled", True):
        return None
    url = (getattr(cfg, "agenti_url", None) or "").strip()
    modello_cfg = (getattr(cfg, "agenti_modello", None) or "").strip()
    if url:
        if not url.startswith(("http://", "https://")):
            raise ConfigAgentiNonValida("agenti_url deve cominciare con http:// o https://")
        modello = modello_cfg or getattr(cfg, "llm_model", "")
        nome = "questo computer" if _locale(url) else "il computer dell'agente"
        # Un indirizzo che finisce con /v1 è un server compatibile OpenAI (vLLM, llama.cpp)
        motore = "openai" if url.rstrip("/").endswith("/v1") else "ollama"
        return Impostazioni("diretto", url.rstrip("/"), modello, origine="agenti_url",
                            nome=nome, timeout_s=5.0, motore=motore)
    path = percorso_file(cfg)
    if path is None or not path.is_file():
        return None
    try:
        import yaml
    except ImportError as e:
        raise ConfigAgentiNonValida("manca PyYAML per leggere il file della DGX") from e
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        riga = f" alla riga {mark.line + 1}" if mark is not None else ""
        raise ConfigAgentiNonValida(f"{path.name} non si legge{riga}") from None
    except OSError as e:
        raise ConfigAgentiNonValida(f"{path.name} non si apre ({e.strerror})") from None
    sez = data.get(_SEZIONE) if isinstance(data, dict) else None
    if not isinstance(sez, dict):
        raise ConfigAgentiNonValida(f"in {path.name} manca la sezione «{_SEZIONE}:»")
    avvisi = []
    note = {"ssh_alias", "collegamento", "porta_remota", "porta_locale", "agente_modello",
            "scrittore_modello", "timeout_collegamento_s", "url_diretto", "nome", "motore"}
    for k in sez:
        if k not in note:
            avvisi.append(f"chiave sconosciuta «{k}» in {path.name}: ignorata")
    modo = str(sez.get("collegamento") or "tunnel").strip().lower()
    if modo not in ("tunnel", "diretto"):
        raise ConfigAgentiNonValida(f"collegamento in {path.name} deve essere «tunnel» o "
                                    f"«diretto»")
    motore = str(sez.get("motore") or "ollama").strip().lower()
    if motore not in ("ollama", "openai"):
        raise ConfigAgentiNonValida(f"motore in {path.name} deve essere «ollama» o «openai»")
    # La porta del server sulla macchina dell'agente: 11434 per Ollama, 8000 per vLLM
    porta_predef = 11434 if motore == "ollama" else 8000
    modello = modello_cfg or str(sez.get("agente_modello") or "").strip()
    if not modello:
        raise ConfigAgentiNonValida(f"in {path.name} manca agente_modello")

    def porta(nome, predef):
        v = sez.get(nome, predef)
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 65535:
            raise ConfigAgentiNonValida(f"{nome} in {path.name} deve essere un numero di porta")
        return v

    def secondi(nome, predef):
        v = sez.get(nome, predef)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise ConfigAgentiNonValida(f"{nome} in {path.name} deve essere un numero di secondi")
        return float(v)

    timeout = secondi("timeout_collegamento_s", 5.0)
    scrittore = str(sez.get("scrittore_modello") or "").strip()
    nome = str(sez.get("nome") or "la DGX").strip() or "la DGX"
    if modo == "tunnel":
        alias = str(sez.get("ssh_alias") or "").strip()
        # L'alias va passato a ssh come argomento: niente spazi né opzioni travestite
        if not alias or alias.startswith("-") or any(c.isspace() for c in alias):
            raise ConfigAgentiNonValida(f"ssh_alias in {path.name} manca o non è valido")
        lp, rp = porta("porta_locale", 11435), porta("porta_remota", porta_predef)
        if lp == 11434:
            avvisi.append("porta_locale 11434 è quella dell'Ollama locale: meglio 11435")
        return Impostazioni("tunnel", f"http://127.0.0.1:{lp}", modello, scrittore, alias,
                            lp, rp, timeout, path.name, nome, avvisi, motore)
    url = str(sez.get("url_diretto") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ConfigAgentiNonValida(f"con collegamento «diretto» serve url_diretto in "
                                    f"{path.name} (http://indirizzo:{porta_predef})")
    return Impostazioni("diretto", url.rstrip("/"), modello, scrittore, "", 0,
                        porta("porta_remota", porta_predef), timeout, path.name, nome, avvisi,
                        motore)


def stesso_ollama(cfg, imp: Impostazioni | None) -> bool:
    """L'agente usa lo stesso Ollama della voce? Allora si contendono la GPU e l'arbitro
    deve dare la precedenza alla voce."""
    if imp is None or imp.tunnel:
        return False
    voce = (getattr(cfg, "llm_native_url", "") or "").rstrip("/").lower()
    a = imp.url.rstrip("/").lower()
    norm = lambda u: u.replace("localhost", "127.0.0.1")   # noqa: E731
    return norm(voce) == norm(a)


def _host(url: str) -> str:
    h = (url or "").split("://", 1)[-1].split("/", 1)[0]
    h = h.rsplit("@", 1)[-1]
    h = h[1:].split("]", 1)[0] if h.startswith("[") else h.rsplit(":", 1)[0]
    h = h.lower()
    return "127.0.0.1" if h in ("localhost", "::1", "127.0.0.1") else h


def stessa_gpu(cfg, imp: Impostazioni | None = None, url: str | None = None) -> bool:
    """Il server dell'agente (o `url`) usa la GPU della voce? Allora l'arbitro gli fa cedere il
    passo quando si parla con Calliope (04/10). `agenti_arbitro`: «sempre», «mai» o «auto» =
    stesso Ollama della voce, oppure un server su questo computer o sullo stesso host della
    voce (sulla DGX: vLLM su 127.0.0.1:8000 e Ollama della voce su 127.0.0.1:11434). Con il
    tunnel SSH no: la porta è locale, la GPU no."""
    modo = str(getattr(cfg, "agenti_arbitro", "auto") or "auto").strip().lower()
    if modo in ("mai", "no", "false"):
        return False
    if modo in ("sempre", "si", "sì", "true"):
        return True
    if url is None:
        if imp is None or imp.tunnel:
            return False
        if stesso_ollama(cfg, imp):
            return True
        url = imp.url
    a = _host(url)
    if not a:
        return False
    voce = _host(getattr(cfg, "llm_native_url", "") or getattr(cfg, "llm_base_url", "") or "")
    return a == "127.0.0.1" or a == voce


def pausa_server(cfg, imp: Impostazioni | None, log=print):
    """La pausa del server dell'agente per l'arbitro (04/10, `arbitro.PausaServer`), o None:
    solo con `agenti_pausa_vllm`, un server compatibile OpenAI (vLLM) senza tunnel e **mai** il
    server della voce (la pausa ferma tutte le richieste di quel server). Se il server ha
    `/pause` lo scopre il thread dell'arbitro (404 → si chiudono gli stream come prima)."""
    if imp is None or imp.tunnel or imp.motore != "openai":
        return None
    if not getattr(cfg, "agenti_pausa_vllm", True):
        return None
    from .arbitro import PausaServer, radice
    a = radice(imp.url)
    for chiave in ("llm_base_url", "llm_native_url"):
        if radice(getattr(cfg, chiave, "") or "") == a:
            return None                      # lo stesso server della voce: mai in pausa
    return PausaServer(imp.url, log=log)


def opzioni_voce(cfg, url: str, modello: str, motore: str = "ollama") -> dict:
    """Le opzioni della voce per una richiesta all'API nativa di Ollama fatta da un altro
    servizio (OCR e schede dell'archivio, testi lunghi dell'ufficio) con **lo stesso Ollama e
    lo stesso modello della voce**: {"options": {"num_ctx": …}, "keep_alive": …}. Senza,
    Ollama ricarica il modello con il contesto predefinito (la voce perde secondi alla
    domanda dopo) e lo scarica dopo 5 minuti invece del keep_alive della voce (04/10). Con un
    altro server, un altro modello o il motore «openai»: {} (come prima)."""
    if motore != "ollama" or not url or not modello:
        return {}
    norm = lambda u: re.sub(r"/v1/?$", "", u.strip().rstrip("/").lower()).replace(  # noqa: E731
        "localhost", "127.0.0.1")
    if norm(url) != norm(getattr(cfg, "llm_native_url", "") or "") \
            or modello != getattr(cfg, "llm_model", None):
        return {}
    from ..contesto import finestra
    out = {"options": {"num_ctx": finestra(cfg)}}
    ka = getattr(cfg, "llm_keep_alive", None)
    if ka not in (None, ""):
        try:
            from ..config import keep_alive_valido
            out["keep_alive"] = keep_alive_valido(ka)
        except Exception:  # noqa: BLE001 — come Brain: il valore com'è
            out["keep_alive"] = ka
    return out


def ssh_eseguibile() -> str | None:
    """Il client ssh da usare: CALLIOPE_SSH (le prove: un ssh finto), altrimenti il primo
    nel PATH (su Windows di solito C:\\Windows\\System32\\OpenSSH\\ssh.exe)."""
    import shutil
    forced = os.environ.get("CALLIOPE_SSH")
    if forced:
        return forced if Path(forced).is_file() else None
    return shutil.which("ssh")
