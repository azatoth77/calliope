"""
Il conto della memoria e le classi delle attività, in sola lettura (14/10/2026, passo 1
dell'arbitro unico delle attività e della memoria: docs/ricerche/2026-10-14-arbitro-memoria.md).

    python -m calliope.stato --memoria [--json] [--inventario FILE]

Cosa tiene la memoria della macchina adesso, chi lo tiene e di che **classe** è:

    tempo reale   serve al turno di voce mentre qualcuno parla: voce, Whisper dei turni,
                  guardiano e rilevatore (minori e ospiti), Piper, CAM++, VAD, wake word.
                  Non si scarica mai.
    vicino        un turno lo può aspettare per qualche secondo (oggi nessun modello a sé:
                  lo scrittore dell'ufficio usa l'agente, vedi la ricerca § 2).
    sfondo        lavora quando la voce è ferma: agente (vLLM), embedding delle conversazioni,
                  guardiano a posteriori e corsia lenta della stanza (che usano modelli già
                  caricati per il tempo reale o un Whisper suo).
    a richiesta   si carica quando serve e si scarica dopo: immagini (FLUX), il secondo
                  Whisper della corsia lenta (futuro, come servizio a richiesta).

e, per ogni modello a richiesta non caricato, **cosa farebbe l'arbitro adesso** (in ombra, non
lo fa): ci sta nella memoria libera meno il margine, oppure quali modelli di sfondo scaricherebbe
prima (i meno usati, mai uno del tempo reale) e quanto mancherebbe ancora.

**Non scarica, non carica, non scrive niente.** `conto()` e `proposta()` sono funzioni pure (si
provano a secco con macchine finte, `prove/prova_arbitro_memoria.py`); i dati vengono da
`macchina.inventario` (memoria libera vera: MemAvailable sulla memoria unificata, nvidia-smi su una
GPU dedicata; `/api/ps` di Ollama, che **sottostima**: si aggiunge il buffer di calcolo del piano
finché `prove/manuali/misura_memoria_dgx.py` non dà il fattore vero; vLLM dalla
`gpu_memory_utilization` di `/metrics`).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import modelli as cat

TEMPO_REALE, VICINO, SFONDO, A_RICHIESTA = "tempo_reale", "vicino", "sfondo", "a_richiesta"
CLASSI = (TEMPO_REALE, VICINO, SFONDO, A_RICHIESTA)
NOMI_CLASSI = {TEMPO_REALE: "tempo reale", VICINO: "vicino", SFONDO: "sfondo",
               A_RICHIESTA: "a richiesta", "fuori": "non di Calliope"}
# Chi si scarica prima quando un modello a richiesta non ci sta (§ 4.2 della ricerca): gli
# sfondi, poi gli altri a richiesta già caricati e fermi, poi i vicini. Mai il tempo reale.
ORDINE_SCARICO = (SFONDO, A_RICHIESTA, VICINO)

# Memoria libera da non toccare mai caricando un modello a richiesta (§ 3.3 della ricerca) [D]:
# sulla memoria unificata il sistema, la cache dei file e i picchi di Calliope e dei container
# vicini stanno qui (il playbook NVIDIA della Spark avverte di errori «out of memory» anche
# sotto la capacità); su una GPU dedicata basta il margine del contesto.
MARGINE_LIBERO_GB = {"unificata": 8.0, "dedicata": 0.5, "cpu": 2.0}
# /api/ps sottostima (trappola di CLAUDE.md): il buffer di calcolo per modello del piano finché
# la misura non dà il fattore vero
BUFFER_OLLAMA_GB = 0.35
# Il secondo Whisper e le immagini (catalogo): tempi di caricamento stimati, da misurare
STIME_CARICO_S = {"whisper_lento": "~2–5 s [S]", "immagini": "5–15 s dal disco [S, ricerca 06/10]",
                  "agente": "~1 min a container rifatto con la cache di compilazione [M 04/10]; "
                            "sonno: da misurare",
                  "embedding": "1,5 s [M DGX 14/10]"}
# Le misure vere sulla DGX del 14/10 (prove/manuali/misura_memoria_dgx.py, memoria unificata):
# qwen3-embedding da caricato tiene ~6,7 GB di MemAvailable (non gli 0,6 di /api/ps: il
# contesto e i buffer sulla CPU), whisper-server dei turni ne rende 2,6 quando si ferma (il
# catalogo diceva 2,1); vLLM prenota 0,4 × 128,4 = 51,4 GB, cioè il conto di sempre in GB
# (i 47,8 della ricerca erano GiB). Valgono solo sulla memoria unificata: sul portatile
# l'embedding è sulla CPU e non tocca la VRAM
MISURE_UNIFICATA_GB = {"embedding": 6.7, "whisper": 2.6}
# Quanto chiederebbe un modello a richiesta (in ombra, passo 2): il secondo Whisper e FLUX.2
# [klein] 4B (ricerca del 06/10). Il secondo Whisper è la variante q5_0 di whisper-lento.sh
# (scelta del 14/10 sera), dal catalogo come il piano: ~2,0 GB [S] = pesi ggml-large-v3-q5_0
# 1,08 GB (1 081 140 203 byte, Hugging Face) + la cache incrociata dei 32 strati del decoder
# (1500 × 1280 × K,V × f16 ≈ 0,25 GB) + quella del beam 5 e il calcolo (il turbo: 2,1 GB
# misurati con 1,62 di pesi). Fino al 15/10 qui c'erano 3,6 GB, la variante f16 (pesi 3,1 GB),
# che whisper-lento.sh usa solo con VARIANTE=f16 (issue #2). Con VARIANTE=f16 questo conto
# sottostima di ~1,9 GB: chi la sceglie aggiorni il catalogo (modelli.WHISPER["cpp-lenta"])
A_RICHIESTA_GB = {"whisper_lento": cat.WHISPER["cpp-lenta"].memoria_gb,
                  "immagini": cat.IMMAGINI_GB}


@dataclass
class Occupante:
    ruolo: str                    # voce, whisper, guardiano, rilevatore, embedding, agente…
    cosa: str                     # modello o servizio
    classe: str                   # una di CLASSI, o «fuori» (non di Calliope)
    motore: str                   # ollama, vllm, whisper.cpp, processo, servizio
    gb: float = 0.0               # memoria tenuta adesso (0 se non caricato)
    gb_pieno: float = 0.0         # memoria da caricato
    caricato: bool | None = None  # None: non si sa (non sondato)
    fonte: str = ""               # da dove viene il numero
    scarica: str = ""             # come si scarica (o «mai»)
    ricarica: str = ""            # come si ricarica
    tempi: str = ""               # caricamento noto o stimato
    dal_passo: int = 2            # da quale passo dell'arbitro si potrà scaricare
    ultimo_uso_s: float | None = None   # secondi fa (None: non si sa = il meno usato)
    note: str = ""


@dataclass
class Proposta:
    """Cosa farebbe l'arbitro per caricare `gb` adesso (in ombra)."""
    per: str
    gb: float
    ci_sta: bool
    spazio_gb: float              # liberi meno il margine, prima di scaricare
    scaricherebbe: list[str] = field(default_factory=list)
    liberati_gb: float = 0.0
    mancano_gb: float = 0.0
    note: str = ""


@dataclass
class Conto:
    macchina: str
    tipo: str                     # unificata | dedicata | cpu
    pool_gb: float
    libera_gb: float | None       # adesso (MemAvailable o nvidia-smi)
    fonte_libera: str
    margine_gb: float
    occupanti: list[Occupante] = field(default_factory=list)
    proposte: list[Proposta] = field(default_factory=list)
    avvisi: list[str] = field(default_factory=list)

    @property
    def usata_gb(self) -> float | None:
        return None if self.libera_gb is None else max(0.0, self.pool_gb - self.libera_gb)

    @property
    def di_calliope_gb(self) -> float:
        return round(sum(o.gb for o in self.occupanti if o.classe != "fuori"), 2)

    @property
    def altri_gb(self) -> float | None:
        """Tutto il resto: sistema, cache dei file non recuperabile, container di altri progetti,
        il processo di Calliope se non è stato misurato."""
        u = self.usata_gb
        if u is None:
            return None
        return round(max(0.0, u - self.di_calliope_gb), 2)

    @property
    def spazio_gb(self) -> float | None:
        """Quanto si può caricare adesso senza scaricare niente: libera meno il margine."""
        return None if self.libera_gb is None else round(self.libera_gb - self.margine_gb, 2)

    def per_classe(self) -> dict[str, float]:
        out = {c: 0.0 for c in (*CLASSI, "fuori")}
        for o in self.occupanti:
            out[o.classe] = round(out.get(o.classe, 0.0) + o.gb, 2)
        return out

    def as_json(self) -> dict:
        d = asdict(self)
        d.update(usata_gb=self.usata_gb, di_calliope_gb=self.di_calliope_gb,
                 altri_gb=self.altri_gb, spazio_gb=self.spazio_gb, per_classe=self.per_classe())
        return d


# ─────────────────────────── cosa usa Calliope (dalla configurazione) ───────────────────────────
@dataclass
class Uso:
    """I modelli e i servizi che Calliope usa su questa macchina (da `da_config`)."""
    voce: str = ""
    voce_backend: str = "ollama"
    guardiano: str = ""                 # "" = spento (né minori né ospiti col guardiano)
    rilevatore: str = ""                # "" = spento o la voce stessa
    embedding: str = ""
    whisper: str = "server"             # server | locale
    piper_gpu: bool | None = None       # None: auto (la taratura decide)
    agente: str = ""                    # nome servito da vLLM, "" = niente agente locale
    stanza_lenta: str = ""              # "" spenta | "stesso" | "server"
    immagini: bool = True               # S6 della roadmap: non installate, contate come futuro
    processo_gb: float | None = None    # memoria del processo di Calliope (RSS), se letta


def da_config(cfg) -> Uso:
    u = Uso()
    u.voce_backend = str(getattr(cfg, "llm_backend", "ollama") or "ollama")
    u.voce = str(getattr(cfg, "llm_model", "") or "")
    guard = bool(getattr(cfg, "guardiano_enabled", True)) and bool(
        getattr(cfg, "minori_enabled", True) or getattr(cfg, "guardiano_ospiti", True))
    if guard:
        u.guardiano = str(getattr(cfg, "guardiano_modello", "") or "")
        if getattr(cfg, "guardiano_pericolo", True):
            r = str(getattr(cfg, "guardiano_pericolo_modello", "") or "")
            u.rilevatore = "" if not r or r == u.voce else r
    if getattr(cfg, "conversazioni_enabled", True):
        u.embedding = str(getattr(cfg, "conversazioni_embedding", "") or "")
    u.whisper = "server" if getattr(cfg, "stt_motore", "locale") == "server" else "locale"
    disp = str(getattr(cfg, "tts_dispositivo", "auto") or "auto").lower()
    u.piper_gpu = None if disp == "auto" else disp in ("cuda", "gpu")
    if getattr(cfg, "agenti_enabled", True):
        u.agente = cat.AGENTE_VLLM
    if bool(getattr(cfg, "stanza_lenta", False)) and str(
            getattr(cfg, "stanza", "spenta") or "spenta").lower() != "spenta":
        u.stanza_lenta = "server" if str(getattr(cfg, "stanza_lenta_stt_url", "") or "").strip() \
            else "stesso"
    return u


def processo_servizio_gb() -> float | None:
    """La memoria residente del servizio `calliope` (Linux, sola lettura: `systemctl --user show`
    e /proc), None altrove o se non si legge. Non conta la memoria CUDA (Piper sulla GPU)."""
    import re
    import subprocess
    import sys
    if not sys.platform.startswith("linux"):
        return None
    try:
        out = subprocess.run(["systemctl", "--user", "show", "calliope", "--property=MainPID"],
                             capture_output=True, text=True, timeout=2,
                             stdin=subprocess.DEVNULL).stdout
        pid = int((re.search(r"MainPID=(\d+)", out or "") or [0, 0])[1])
        if pid <= 0:
            return None
        with open(f"/proc/{pid}/status", encoding="ascii", errors="replace") as fh:
            m = re.search(r"^VmRSS:\s*(\d+)\s*kB", fh.read(), re.M)
        return round(int(m.group(1)) * 1024 / 1e9, 2) if m else None
    except (OSError, ValueError, subprocess.SubprocessError, TypeError):
        return None


# ─────────────────────────── il conto ───────────────────────────
def _nome(m: str) -> str:
    m = str(m or "").strip()
    return m if ":" in m else m + ":latest"


def _gb(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def conto(inv: dict, uso: Uso | None = None) -> Conto:
    """Il conto della memoria della macchina `inv` (macchina.inventario o una finta)."""
    u = uso or Uso()
    g = inv.get("gpu") or None
    if not g or not g.get("memoria_gb"):
        tipo, pool, libera = "cpu", float(inv.get("ram_gb") or 0), inv.get("ram_libera_gb")
        fonte = "RAM libera del sistema"
    elif g.get("unificata"):
        tipo, pool, libera = "unificata", float(g["memoria_gb"]), g.get("libera_gb")
        fonte = "MemAvailable (memoria unificata: nvidia-smi dice [N/A])"
    else:
        tipo, pool, libera = "dedicata", float(g["memoria_gb"]), g.get("libera_gb")
        fonte = "nvidia-smi"
    nome = (g or {}).get("nome") or "nessuna GPU"
    c = Conto(macchina=f"{nome}, {inv.get('sistema') or inv.get('os') or ''} "
                       f"{inv.get('arch') or ''}".strip(),
              tipo=tipo, pool_gb=round(pool, 2),
              libera_gb=None if libera is None else round(float(libera), 2),
              fonte_libera=fonte, margine_gb=MARGINE_LIBERO_GB[tipo])
    motori = inv.get("motori") or {}
    o = motori.get("ollama") or {}
    caricati = {_nome(m.get("nome")): m for m in o.get("caricati") or [] if m.get("nome")}
    usati: set[str] = set()

    def da_ollama(ruolo, modello, classe, scarica, ricarica, tempi="da misurare", dal=2,
                  note=""):
        k = _nome(modello)
        usati.add(k)
        m = caricati.get(k)
        ps = None if m is None else float(m.get("gb") or 0)
        if m is not None and tipo == "dedicata" and m.get("gb_gpu") is not None:
            ps = float(m["gb_gpu"])             # sulla GPU dedicata conta solo la parte lì
        cat_m = cat.MODELLI.get(modello) or cat.MODELLI.get(k.removesuffix(":latest"))
        stima = (ps + BUFFER_OLLAMA_GB) if ps else             (round(cat_m.pesi_gb + BUFFER_OLLAMA_GB, 2) if cat_m else 0.0)
        tenuto = round(ps + BUFFER_OLLAMA_GB, 2) if ps else 0.0
        misura = MISURE_UNIFICATA_GB.get(ruolo) if tipo == "unificata" else None
        if misura:
            # La misura vera della DGX vince sulla sottostima di /api/ps (15/10)
            stima = max(stima, misura)
            tenuto = max(tenuto, misura) if ps else 0.0
        c.occupanti.append(Occupante(
            ruolo, modello, classe, "ollama",
            gb=tenuto, gb_pieno=round(stima, 2),
            caricato=m is not None if o else None,
            fonte=(("misura della DGX 14/10" if misura else
                    "/api/ps + buffer (sottostima: da misurare)") if m is not None else
                   "misura della DGX 14/10" if misura else
                   "catalogo" if cat_m else "—") + (f", contesto {m.get('contesto')}"
                                                    if m is not None and m.get("contesto")
                                                    else ""),
            scarica=scarica, ricarica=ricarica, tempi=tempi, dal_passo=dal, note=note))

    # Tempo reale
    if u.voce and u.voce_backend == "ollama":
        da_ollama("voce", u.voce, TEMPO_REALE, "mai",
                  "/api/generate con num_ctx e keep_alive della voce (stessi valori, o Ollama "
                  "la ricarica al turno dopo)", dal=0)
    elif u.voce:
        v = _vllm(motori, porta="8001")
        gbv = round((v or {}).get("gpu_memory_utilization", 0) * pool, 2) if v else 0.0
        c.occupanti.append(Occupante("voce", u.voce, TEMPO_REALE, "vllm", gb=gbv, gb_pieno=gbv,
                                     caricato=bool(v), fonte="gpu_memory_utilization × pool",
                                     scarica="mai", ricarica="container", dal_passo=0))
    w = cat.WHISPER["cpp-gpu" if u.whisper == "server" else "fw-gpu"]
    ws = motori.get("whisper_server") or {}
    # Nel processo: c'è se il processo di Calliope gira (misurato), altrimenti non si sa
    attivo = ws.get("attivo") if u.whisper == "server" else (
        True if u.processo_gb is not None else None)
    gbw, fontew = w.memoria_gb, f"catalogo: {w.fonte}"
    if u.whisper == "server" and tipo == "unificata":
        gbw = max(gbw, MISURE_UNIFICATA_GB["whisper"])
        fontew = "misura della DGX 14/10 (memoria resa alla fermata)"
    c.occupanti.append(Occupante(
        "whisper", f"{w.nome}, {w.motore}" + (" (servizio calliope-whisper)"
                                               if u.whisper == "server" else " (nel processo)"),
        TEMPO_REALE, "whisper.cpp" if u.whisper == "server" else "processo",
        gb=gbw if attivo else 0.0, gb_pieno=gbw, caricato=attivo,
        fonte=fontew, scarica="mai", ricarica="systemctl --user start "
        "calliope-whisper" if u.whisper == "server" else "con Calliope", dal_passo=0))
    if u.guardiano:
        da_ollama("guardiano", u.guardiano, TEMPO_REALE, "mai (minori e ospiti)",
                  "/api/generate con guardiano_num_ctx e guardiano_keep_alive", dal=0)
    if u.rilevatore:
        da_ollama("rilevatore", u.rilevatore, TEMPO_REALE, "mai (minori)",
                  "/api/generate con guardiano_num_ctx e guardiano_keep_alive", dal=0,
                  note="lo usa anche il guardiano a posteriori della stanza (sfondo)")
    piper = 0.0
    if u.piper_gpu or (u.piper_gpu is None and motori.get("onnxruntime_cuda")
                       and tipo != "cpu"):
        piper = cat.PIPER_GPU_GB
    c.occupanti.append(Occupante(
        "calliope", "processo: Piper, CAM++, VAD, wake word, biblioteca", TEMPO_REALE, "processo",
        gb=round((u.processo_gb or 0.0) + piper, 2),
        gb_pieno=round((u.processo_gb or 0.0) + piper, 2),
        caricato=True if u.processo_gb else None,
        fonte=("RSS del servizio" if u.processo_gb else "processo non misurato")
        + (f" + Piper sulla GPU {_gb(piper)} GB (catalogo)" if piper else ""),
        scarica="mai", ricarica="—", dal_passo=0))

    # Sfondo
    if u.embedding:
        da_ollama("embedding", u.embedding, SFONDO, "keep_alive 0 (lo fa già: lotti a "
                  "Calliope inattiva, calliope/conversazioni.py)", "/api/embed a richiesta",
                  tempi=STIME_CARICO_S["embedding"], dal=2,
                  note="sulla CPU, ma sulla memoria unificata conta lo stesso")
    if u.agente:
        v = _vllm(motori, porta="8000")
        if v:
            util = float(v.get("gpu_memory_utilization") or 0.4)
            gbv = round(util * pool, 2)
            agente_m = cat.MODELLI.get(cat.AGENTE_VLLM)
            pesi = agente_m.pesi_gb if agente_m else 24.0
            c.occupanti.append(Occupante(
                "agente", f"{(v.get('modelli') or [{}])[0].get('id') or u.agente} su vLLM "
                          f"{v.get('versione') or ''}".strip(),
                SFONDO, "vllm", gb=gbv, gb_pieno=gbv, caricato=True,
                fonte=f"gpu_memory_utilization {util} × pool (prenotata all'avvio)",
                scarica=f"sonno di vLLM: livello 1 libera la sola cache (~{_gb(gbv - pesi)} GB: "
                        f"sulla memoria unificata i pesi «sulla CPU» restano nella stessa "
                        f"memoria), livello 2 anche i pesi (~{_gb(gbv)} GB); serve "
                        "--enable-sleep-mode e la modalità sviluppo",
                ricarica="POST /wake_up (livello 2: wake_up?tags=weights, collective_rpc "
                         "reload_weights, wake_up?tags=kv_cache)",
                tempi=STIME_CARICO_S["agente"], dal_passo=4,
                note="lo scrittore dell'ufficio lo usa da un turno: mai a dormire con un "
                     "lavoro in corso"))
    # A richiesta
    if u.stanza_lenta == "server":
        wl = cat.WHISPER["cpp-lenta"]
        c.occupanti.append(Occupante(
            "whisper_lento", f"{wl.nome}, {wl.motore} (secondo server)", A_RICHIESTA,
            "whisper.cpp", gb=wl.memoria_gb, gb_pieno=wl.memoria_gb, caricato=None,
            fonte=f"catalogo: {wl.fonte}; oggi sempre acceso, non sondato",
            scarica="fermare il servizio (passo 3)", ricarica="avviare il servizio",
            tempi=STIME_CARICO_S["whisper_lento"], dal_passo=3))
    else:
        wl = cat.WHISPER["cpp-lenta"]
        c.occupanti.append(Occupante(
            "whisper_lento", f"{wl.nome}, {wl.motore} (secondo server, futuro)", A_RICHIESTA,
            "whisper.cpp", gb=0.0, gb_pieno=wl.memoria_gb, caricato=False,
            fonte=f"catalogo: {wl.fonte}", scarica="fermare il servizio",
            ricarica="avviare il servizio (passo 3)", tempi=STIME_CARICO_S["whisper_lento"],
            dal_passo=3, note="la corsia lenta oggi usa " + (
                "lo stesso Whisper dei turni" if u.stanza_lenta == "stesso" else
                "niente (spenta)")))
    if u.immagini and tipo != "cpu":
        c.occupanti.append(Occupante(
            "immagini", "FLUX.2 [klein] 4B (non installato)", A_RICHIESTA, "servizio",
            gb=0.0, gb_pieno=cat.IMMAGINI_GB, caricato=False,
            fonte="catalogo (ricerca del 06/10)", scarica="immagini_keep_alive scaduto: il "
            "servizio scarica i pesi", ricarica="alla prima richiesta",
            tempi=STIME_CARICO_S["immagini"], dal_passo=3))

    # Modelli caricati in Ollama che Calliope non usa: contano, ma l'arbitro non li tocca
    for k, m in caricati.items():
        if k in usati:
            continue
        gb_ = round(float(m.get("gb") or 0) + BUFFER_OLLAMA_GB, 2)
        c.occupanti.append(Occupante(
            "altro su Ollama", m.get("nome") or k, "fuori", "ollama", gb=gb_, gb_pieno=gb_,
            caricato=True, fonte="/api/ps + buffer", scarica="non è di Calliope: non si tocca",
            note="caricato da qualcun altro sullo stesso Ollama"))
        c.avvisi.append(f"{m.get('nome') or k} è caricato in Ollama ma Calliope non lo usa "
                        f"({_gb(gb_)} GB).")
    for m in caricati.values():
        if m.get("in_parte_cpu"):
            c.avvisi.append(f"{m.get('nome')} è in parte sulla CPU: la sua memoria vera è più "
                            "di quella che dice /api/ps sulla GPU.")
    if c.libera_gb is None:
        c.avvisi.append("La memoria libera non si legge su questa macchina: niente proposte.")
    if u.processo_gb is None:
        c.avvisi.append("Il processo di Calliope non è misurato (servizio non trovato): la sua "
                        "memoria finisce tra «altri».")

    # Le proposte per i modelli a richiesta non caricati (in ombra)
    for x in c.occupanti:
        if x.classe == A_RICHIESTA and x.caricato is False:
            c.proposte.append(proposta(c, x.gb_pieno, x.ruolo))
    return c


def _vllm(motori: dict, porta: str) -> dict | None:
    for v in motori.get("vllm") or []:
        if f":{porta}" in str(v.get("url") or ""):
            return v
    return None


def scaricabili(c: Conto, per: str = "", passo: int = 99) -> list[Occupante]:
    """Chi si potrebbe scaricare, nell'ordine della politica: classe (sfondo, poi a richiesta
    fermi, poi vicini), poi il meno usato (senza un ultimo uso: prima). Mai il tempo reale, mai
    i modelli che non sono di Calliope, mai quello che si vuole caricare; solo chi si può
    scaricare entro il passo `passo` dell'arbitro."""
    cand = [o for o in c.occupanti if o.classe in ORDINE_SCARICO and o.gb > 0
            and o.caricato is not False and o.ruolo != per and o.dal_passo <= passo]
    return sorted(cand, key=lambda o: (ORDINE_SCARICO.index(o.classe),
                                       -(o.ultimo_uso_s if o.ultimo_uso_s is not None
                                         else float("inf"))))


def proposta(c: Conto, gb: float, per: str = "", passo: int = 99) -> Proposta:
    """Cosa farebbe l'arbitro per caricare `gb` adesso, senza farlo."""
    spazio = c.spazio_gb
    if spazio is None:
        return Proposta(per, gb, False, 0.0, note="memoria libera non letta")
    if gb <= spazio + 1e-9:
        return Proposta(per, gb, True, spazio, note="ci sta senza scaricare niente")
    p = Proposta(per, gb, False, spazio)
    serve = gb - spazio
    for o in scaricabili(c, per, passo):
        p.scaricherebbe.append(o.ruolo)
        p.liberati_gb = round(p.liberati_gb + o.gb, 2)
        if p.liberati_gb >= serve - 1e-9:
            p.ci_sta = True
            break
    p.mancano_gb = round(max(0.0, serve - p.liberati_gb), 2)
    if not p.ci_sta:
        p.note = "non ci sta neanche scaricando tutto lo sfondo: niente (mai il tempo reale)"
    return p


def tempo_reale_toccato(c: Conto, p: Proposta) -> list[str]:
    """I ruoli del tempo reale (o non di Calliope) che la proposta scaricherebbe: deve essere
    sempre vuoto (§ 4.1). È il controllo del criterio del passo 2, non una regola nuova."""
    vietati = {o.ruolo for o in c.occupanti if o.classe in (TEMPO_REALE, "fuori")}
    return [r for r in p.scaricherebbe if r in vietati]


# ─────────────────────────── una sola «voce ferma» (passo 2) ───────────────────────────
class Quiete:
    """La definizione unica di «voce ferma» (§ 4.4 della ricerca, passo 2 dell'arbitro, 15/10):
    nessuno che parla a Calliope (il VAD della corsia locale, `voce_occupata`/`voce_libera`, e
    un satellite che ha appena mandato un comando), nessuna risposta del modello in corso (il
    varco delle corsie), nessuna frase di un turno che aspetta Whisper, la coda della stanza
    vuota. `quiete(secondi)`: tutto questo è vero adesso **e** da almeno `secondi`.

    I segnali sono funzioni senza argomenti (True = occupata) messe da main.py: si chiamano a
    ogni `quiete()` e a ogni `campiona()` (il thread dell'arbitro in ombra, ogni secondo), che
    tengono l'ultimo momento in cui qualcosa era occupato. Costo: qualche lettura di attributi e
    un lock breve, niente rete né programmi: si può chiamare anche dai thread dei lavori.

    In ombra (passo 2) nessuno decide con questa funzione: guardia, corsia lenta, embedding e
    arbitro dell'agente decidono come prima e l'arbitro in ombra conta quando le risposte
    divergono (`calliope stato --memoria --storia`).

    La voce del VAD (18/10, issue #157): il VAD dice «libera» solo per una frase buttata (in
    locale come dal satellite); una frase accettata la libera la corsia all'inizio del giro dopo
    (`Ciclo._inizio_giro`, come l'arbitro dell'agente). Rete di sicurezza: la voce tenuta oltre
    `tenuta_max_s` senza un segno torna libera da sé (come la tenuta massima dell'arbitro
    dell'agente), con una riga nel log e il conto in `tenute` (nella riga del minuto
    dell'arbitro in ombra e in `calliope stato --memoria --storia`). Un segno è un «occupata»
    (l'inizio del parlato, e l'inizio della risposta: `Ciclo._prepara_risposta`) oppure un
    segnale occupato (la risposta del modello coi suoi tool, Whisper): la tenuta conta solo
    dall'ultimo, così un turno lungo vero (l'ultimo pezzo al tetto, un tool lento, una risposta
    lunga) non la fa scattare."""

    # Più della frase più lunga (max_utterance_s, 120 s di serie; main.py la rifà dalla
    # configurazione) e della coda di frasi ancora da dire quando il modello ha finito
    TENUTA_MAX_S = 180.0

    def __init__(self, orologio=None, tenuta_max_s: float | None = None, log=None):
        import threading
        import time
        self._ora = orologio or time.monotonic
        self._lock = threading.Lock()
        self.segnali: list[tuple[str, object]] = []
        self._voce = False
        self._voce_dal = 0.0
        self._ultimo_occupato = self._ora()     # all'avvio: si conta come appena occupata
        self.ultimo_motivo = "avvio"
        self.tenuta_max_s = float(self.TENUTA_MAX_S if tenuta_max_s is None else tenuta_max_s)
        self.tenute = 0
        self.log = log or (lambda m: print(m, flush=True))

    # ── il VAD (come l'arbitro dell'agente e la compressione) ──
    def voce_occupata(self, *a, **k):
        with self._lock:
            self._voce = True
            self._voce_dal = self._ultimo_occupato = self._ora()
            self.ultimo_motivo = "voce"

    def voce_libera(self, *a, **k):
        with self._lock:
            if self._voce:
                self._ultimo_occupato = self._ora()
            self._voce = False

    def segna(self, motivo: str = "turno"):
        """Un fatto della voce senza durata (un turno appena finito): conta come occupata."""
        with self._lock:
            self._ultimo_occupato = self._ora()
            self.ultimo_motivo = motivo

    def occupata(self) -> str:
        """Il motivo per cui la voce è occupata adesso ("" se libera). Nel dubbio occupata."""
        if self._voce:
            tenuta = None
            if self._segnale():
                with self._lock:          # il turno è ancora aperto (risposta, Whisper): un segno
                    self._voce_dal = self._ora()
                return "voce"
            with self._lock:
                ora = self._ora()
                if self._voce and ora - self._voce_dal > self.tenuta_max_s:
                    tenuta = ora - self._voce_dal       # nessuno l'ha liberata (#157)
                    self._voce = False
                    self._ultimo_occupato = ora
                    self.ultimo_motivo = "tenuta"
                    self.tenute += 1
            if tenuta is None:
                return "voce"
            try:
                self.log(f"[ARBITRO] voce occupata da {tenuta:.0f} s senza un segno: oltre la "
                         f"tenuta massima ({self.tenuta_max_s:.0f} s), la libero")
            except Exception:  # noqa: BLE001 — il log non cambia la risposta
                pass
        return self._segnale()

    def _segnale(self) -> str:
        for nome, f in list(self.segnali):
            try:
                if f():
                    return nome
            except Exception:  # noqa: BLE001 — come guardia e corsia lenta: nel dubbio occupata
                return nome
        return ""

    def campiona(self) -> str:
        motivo = self.occupata()
        if motivo:
            with self._lock:
                self._ultimo_occupato = self._ora()
                self.ultimo_motivo = motivo
        return motivo

    def ferma_da(self) -> float:
        """Secondi di voce ferma adesso (0 se occupata)."""
        if self.campiona():
            return 0.0
        with self._lock:
            return max(0.0, self._ora() - self._ultimo_occupato)

    def __call__(self, secondi: float = 0.0) -> bool:
        if self.campiona():
            return False
        with self._lock:
            return self._ora() - self._ultimo_occupato >= float(secondi or 0.0)


# La «voce ferma» del processo: main.py le dà i segnali con l'arbitro in ombra acceso
QUIETE = Quiete()


def quiete(secondi: float = 0.0) -> bool:
    """La voce è ferma da almeno `secondi`? (la definizione unica, § 4.4)"""
    return QUIETE(secondi)


# ─────────────────────────── testo per il terminale ───────────────────────────
def testo(c: Conto) -> str:
    r = [f"Memoria di {c.macchina} (sola lettura, passo 1 dell'arbitro della memoria)",
         f"Pool {_gb(c.pool_gb)} GB ({c.tipo}); liberi adesso {_gb(c.libera_gb)} "
         f"({c.fonte_libera}); margine da non toccare {_gb(c.margine_gb)}",
         f"Calliope {_gb(c.di_calliope_gb)} GB; altri (sistema, cache, altri container) "
         f"{_gb(c.altri_gb)} GB; caricabile adesso senza scaricare niente {_gb(c.spazio_gb)} GB",
         ""]
    pc = c.per_classe()
    r.append("Per classe: " + ", ".join(f"{NOMI_CLASSI[k]} {_gb(v)} GB" for k, v in pc.items()
                                        if v or k in CLASSI))
    r.append("")
    for cl in (*CLASSI, "fuori"):
        righe = [o for o in c.occupanti if o.classe == cl]
        if not righe:
            continue
        r.append(f"{NOMI_CLASSI[cl].capitalize()}:")
        for o in righe:
            stato = ("" if o.caricato else "  (non caricato)" if o.caricato is False
                     else "  (non sondato)")
            r.append(f"  {o.ruolo:15}{o.cosa[:48]:48} {_gb(o.gb):>6} GB{stato}")
            r.append(f"  {'':15}fonte: {o.fonte}")
            if o.classe != TEMPO_REALE:
                r.append(f"  {'':15}si scarica: {o.scarica}; si ricarica: {o.ricarica}"
                         + (f"; tempi: {o.tempi}" if o.tempi else "")
                         + (f" (dal passo {o.dal_passo})" if o.dal_passo > 2 else ""))
            if o.note:
                r.append(f"  {'':15}{o.note}")
    if c.proposte:
        r += ["", "Cosa farebbe l'arbitro adesso (in ombra: non lo fa):"]
        for p in c.proposte:
            testa = f"  {p.per} ({_gb(p.gb)} GB): "
            if p.ci_sta and not p.scaricherebbe:
                r.append(testa + f"ci sta ({_gb(p.spazio_gb)} GB caricabili)")
            elif p.ci_sta:
                r.append(testa + f"scaricherebbe {', '.join(p.scaricherebbe)} "
                         f"({_gb(p.liberati_gb)} GB)")
            else:
                r.append(testa + "non ci sta" + (f": scaricando {', '.join(p.scaricherebbe)} "
                                                 f"mancherebbero {_gb(p.mancano_gb)} GB"
                                                 if p.scaricherebbe else
                                                 f": mancano {_gb(p.mancano_gb)} GB"))
    if c.avvisi:
        r += ["", "Avvisi:"] + [f"  - {a}" for a in c.avvisi]
    r += ["", "Niente si scarica né si carica: misure sulla DGX con "
              "prove/manuali/misura_memoria_dgx.py; progetto in "
              "docs/ricerche/2026-10-14-arbitro-memoria.md."]
    return "\n".join(r)
