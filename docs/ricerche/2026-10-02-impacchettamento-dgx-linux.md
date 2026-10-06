# Impacchettamento per la DGX Spark con Linux (02/10/2026)

*Lavoro del 2 ottobre 2026, dopo la decisione dell'utente: il **target principale è la DGX
Spark con DGX OS** (Ubuntu 24.04 aarch64, GPU GB10 Blackwell sm_121, ~119 GB di memoria
unificata, CUDA 13), e l'**impacchettamento è la priorità**. Requisito aggiunto a metà
lavoro: installare e **aggiornare** deve essere facilissimo (un comando per installare, uno
per aggiornare, ritorno alla versione di prima se l'aggiornamento non parte), con i dati
dell'utente fuori dalla cartella del codice.*

*Vincoli rispettati: nessun collegamento alla DGX, nessun modello scaricato, niente
installato a livello di sistema, niente commit. Tutto ciò che riguarda la DGX vera è in
§7, «da provare».*

*Legenda: **[V]** verificato su fonte primaria (PyPI JSON API, GitHub, documentazione di
vLLM, NVIDIA, Astral) il 02/10 · **[M]** misurato qui sul portatile · **[D]** deduzione.*

## In breve

- **Tutto ciò che serve a Calliope ha un wheel per Linux aarch64** [V], con due eccezioni
  vere:
  - **CTranslate2 4.8.2 per aarch64 è solo per CPU**: lo script di build abilita CUDA solo
    su x86-64, il wheel aarch64 pesa 16,9 MB contro 39,6, e l'issue speaches #620 riporta
    «not compiled with CUDA support» proprio su DGX Spark. faster-whisper sulla GPU della
    DGX con i wheel di PyPI non va.
  - **torch su PyPI per aarch64 è quello con CUDA 13** (2.14.1: 454 MB più `cuda-toolkit`
    e cuDNN), e silero-vad lo dichiara obbligatorio. Per il solo VAD sarebbero GB.
- **Scelte**:
  - **VAD senza torch** (`calliope/vad.py`): il file ONNX che sta già dentro silero-vad,
    letto con onnxruntime e un involucro in numpy. Misurato [M] sulle 350 registrazioni
    vere (32 464 finestre): differenza massima 6,9·10⁻⁶, **decisioni uguali 32 464/32 464**,
    0,55 ms a finestra contro 1,11 di torch. Su Windows resta torch («auto»), su Linux
    torch non si installa (override di uv con il marcatore).
  - **Whisper sulla DGX come server** (`stt_motore: server`, `ServerTranscriber`): un
    server con l'API compatibile OpenAI (`/v1/audio/transcriptions`) e **faster-whisper su
    CPU come ripiego** automatico (principio 7). La prima scelta era vLLM con
    `openai/whisper-large-v3-turbo`; all'installazione vera (02/10 sera) ha dato WER 21 %
    e si è passati a **whisper.cpp con CUDA** (`-bs 5`): **12,4 %**, contro 11,0 % di
    faster-whisper sul portatile. Vedi §1.1.
  - **La voce**: prima Ollama della DGX (nessuna modifica: stesso backend del portatile);
    se va in errore CUDA come con l'agente, **vLLM** con il backend `openai` e il parser dei
    tool `gemma4` (provato a secco contro un vLLM finto).
  - **Impacchettamento: git + uv + systemd utente**, con un gestore in Python puro
    (`setup/linux/gestore.py`, comando `calliope`): `sh setup/linux/installa.sh` installa,
    `calliope aggiorna` aggiorna con verifica e **ritorno automatico**, `calliope torna`
    torna indietro. Una cartella per versione con il suo venv, dati in `~/calliope`.
  - **Docker solo per i server dei modelli** (vLLM per l'agente, la voce e Whisper), come
    già oggi per l'agente; Calliope stessa no (audio, dimensione, aggiornamento più
    semplice senza registro d'immagini): confronto in §3.
- **Prove** [M]: `python -m prove` **22/22** su Windows; due prove nuove,
  `prova_linux.py` (DGX simulata) e `prova_gestore.py` (installazione, aggiornamento,
  ritorno automatico e a mano con git vero, uv e systemctl finti).

---

## 1. Matrice delle dipendenze su Linux aarch64

Fonte: `https://pypi.org/pypi/<pacchetto>/json`, letta il 02/10/2026; per cp312 (Python di
Ubuntu 24.04). `uv.lock` è stato generato su Windows con `required-environments` =
linux aarch64: uv ha rifiutato in anticipo qualunque pacchetto senza wheel per la DGX, e il
lock è passato [M].

| Pacchetto | Versione (data) | Wheel aarch64 cp312 | Note |
|---|---|---|---|
| ctranslate2 | 4.8.2 (31/08) | `ctranslate2-4.8.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` | **solo CPU** (script `prepare_build_environment_linux.sh`: CUDA solo su x86_64) |
| faster-whisper | 1.2.1 (31/10/2025) | `py3-none-any` | dipende da ctranslate2, onnxruntime, av |
| onnxruntime | 1.30.0 (10/09) | `onnxruntime-1.30.0-cp312-cp312-manylinux_2_28_aarch64.whl` | CPU: basta per wake word, CAM++, Piper, VAD |
| onnxruntime-gpu | 1.30.0 | `…manylinux_2_34_aarch64.whl` (205 MB, CUDA 13) | nuovo; sm_121 non verificato; non serve |
| torch | 2.14.1 (30/09) | `torch-2.14.1-cp312-cp312-manylinux_2_28_aarch64.whl` (454 MB) | su PyPI aarch64 **è CUDA 13** (`cuda-toolkit==13.0.3`, cuDNN): non lo installiamo |
| silero-vad | 6.2.3 (23/09) | `py3-none-any` | chiede torch; contiene `data/silero_vad.onnx` |
| piper-tts | 1.8.0 (04/09) | `piper_tts-1.8.0-cp39-abi3-manylinux_2_17_aarch64…whl` (34 MB) | **espeak-ng incorporato** (statico, dati nel pacchetto): niente apt |
| sounddevice | 0.5.6 (17/08) | `py3-none-any` | su Linux serve `libportaudio2` di sistema |
| numpy | 2.5.3 (06/09) | `…manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` | vuole Python ≥ 3.12 |
| httpx 0.28.1, openai 3.23.0, starlette 1.7.0, uvicorn 0.54.0, python-docx 1.2.0, openpyxl 3.1.5, fpdf2 2.8.9 | — | `py3-none-any` | puro Python |
| pyyaml 6.0.3, websockets 17.1, lxml 6.1.3, pillow 12.3.0, psutil 7.2.2 | — | manylinux aarch64 | |
| zstandard | 0.25.0 | manylinux aarch64 | serve: Python 3.12 non ha `compression.zstd` (marcatore `python_version < '3.14'`) |
| uv | 0.12.22 (02/10) | binario `uv-aarch64-unknown-linux-gnu.tar.gz` | installatore ufficiale `astral.sh/uv/install.sh` |
| vllm | 0.30.0 (22/09) | `vllm-0.30.0-cp38-abi3-manylinux_2_28_aarch64.whl` | non nel venv di Calliope: in container |

Pacchetti di sistema (Ubuntu 24.04): **`libportaudio2`** (obbligatorio), `git`, `curl`,
`python3` (3.12, solo per il gestore: il venv lo crea uv, che non ha bisogno di
`python3-venv`); facoltativi `openssh-client` (tunnel), `fonts-dejavu-core` (PDF con «€»).
Non servono `espeak-ng`, `ffmpeg`, compilatori.

Solo Windows (extra `pc`, marcatore `sys_platform == 'win32'`): pycaw, comtypes, pywin32,
screen_brightness_control, winrt. Extra `gpu`: le DLL CUDA 12 di Whisper, solo Windows x86-64.

### 1.1 Whisper sulla DGX: le strade

| Strada | GPU | Latenza attesa | Taratura del 24/09 (beam 5 + hotwords) | Costo | Giudizio |
|---|---|---|---|---|---|
| faster-whisper da PyPI | no (CPU) | large-v3-turbo int8 su 20 core ARM: secondi a frase [D] | sì | zero | **ripiego** (principio 7) |
| CTranslate2 compilato con CUDA 13 per sm_121 | sì | come il portatile [D] | sì | compilazione da sorgente con CUDA 13 (non documentata da nessuno per GB10; una build di comunità fa passare sm_121 per sm_90) | da tentare solo se il server non basta |
| vLLM con `openai/whisper-large-v3-turbo` | sì | — | prompt sì, beam no | un container in più, e un'immagine derivata con l'extra audio (l'ufficiale rispondeva 400 «Please install vllm[audio]») | **scartata** (02/10): WER 21 % |
| **whisper.cpp `whisper-server` con CUDA** (`-DGGML_CUDA=ON`, architettura `native` = sm_121 con CUDA 13.0.88) | sì | 0,28 s di media dal portatile via tunnel e VPN (p95 0,44) | beam sì (`-bs 5`), prompt sì, hotwords no | una compilazione (`setup/linux/motore/whisper.sh compila`) | **in uso** (02/10): WER 12,4 % |
| Parakeet TDT 0.6B v3 (NVIDIA, italiano compreso) | sì | — | — | altro modello, altra WER da rifare | da valutare dopo |

**Com'è installato sulla DGX** (02/10, `setup/linux/motore/whisper.sh`, anche come
`calliope motore whisper …`): sorgente di whisper.cpp al commit `60c0be6ac8fa` (master del
02/10) in `~/calliope-motore/whispercpp/src`, compilato con `cmake -B build -DGGML_CUDA=ON
-DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=native` (nvcc 13.0.88 di DGX OS; nel
log del server `CUDA : ARCHS = 1210`, `BLACKWELL_NATIVE_FP4 = 1`); modello
`ggml-large-v3-turbo.bin` (1 624 555 275 byte, SHA-256 `1fc70f77…e2bc69`, revisione fissa di
`ggerganov/whisper.cpp` su Hugging Face) in `modelli/`; servizio utente
`calliope-whisper.service` (`whisper-server -m modelli/ggml-large-v3-turbo.bin --host
127.0.0.1 --port 8003 -l it -bs 5 --prompt "Conversazione con Calliope." --inference-path
/v1/audio/transcriptions -t 4`, `Restart=on-failure`), abilitato con il linger. L'unità di
Calliope ha `Wants=` e `After=calliope-whisper.service` nel modello del repository
(`setup/linux/calliope.service`): scritte a mano nell'unità installata erano sparite al primo
`calliope aggiorna`, che la riscrive. Il modello di riserva per la CPU
(`models/whisper/large-v3-turbo/`, 5 file con SHA-256 e revisione fissa di
`mobiuslabsgmbh/faster-whisper-large-v3-turbo`) è l'azione `whisper_riserva` del catalogo
delle installazioni; `installa.sh` lo propone alla fine, e il registro delle capacità dice
«senza ripiego su CPU» se manca.

**Misure di whisper.cpp sulla DGX** (02/10, 23:00) [M]: `prove/prova_whisper.py --server`
dal portatile, attraverso un tunnel SSH temporaneo (`-L 18003:127.0.0.1:8003`) e la VPN,
contro il servizio vero; le 104 registrazioni con riferimento sicuro, nessun file lasciato
sulla DGX (l'audio viaggia nella richiesta), nessuna modifica al servizio. `whisper-server`
legge `prompt`, `beam_size`, `temperature`, `temperature_inc` dal modulo di ogni richiesta e
riparte ogni volta dai valori della riga di comando (`server.cpp`: `whisper_params params =
default_params`), quindi le varianti si provano per richiesta senza toccare il servizio. Il
tempo comprende tunnel e VPN.

| Variante (per richiesta) | WER | Esatte | Wake word | Allucinazioni | t medio / p95 |
|---|---|---|---|---|---|
| **com'è ora** (beam 5, «Conversazione con Calliope.») | **12,4 %** | **69/104** | 43/47 | 1 | 0,28 / 0,44 s |
| stessa, ripetuta alla fine | 12,4 % (identica) | 69/104 | 43/47 | 1 | 0,45 / 0,91 s |
| beam 1 | 13,9 % | 65 | 42/47 | 1 | 0,25 / 0,36 s |
| beam 8 | 12,9 % | 69 | 44/47 | 0 | 0,27 / 0,43 s |
| `temperature_inc` 0 (niente ripiego di temperatura) | 12,6 % | 69 | 43/47 | 1 | 0,28 / 0,43 s |
| prompt «Conversazione in italiano con Calliope, un'assistente vocale di casa.» | 13,1 % | 67 | 41/47 | 1 | 0,26 / 0,41 s |
| prompt «Calliope.» | 19,1 % | 50 | 30/47 | 5 | 0,27 / 0,42 s |
| senza prompt | 22,6 % | 43 | 24/47 | 3 | 0,27 / 0,42 s |

`suppress_nst=true` non si è potuto misurare: il server chiude la connessione senza risposta
(il valore non si converte; il servizio non è ripartito, `NRestarts=0`). Frasi pausa/subito
con i parametri attuali: 8,3 % e 16,7 %.

«Che ore sono»: «Calliope, che ore sono?» detto di seguito diventa «Calliope. Chiori sono.»
con **tutte** le varianti con il prompt (senza: «Caldiope, chi ori sono?»); «Che ore sono?»
da solo, dopo una risposta, è giusto. È la stessa frase che dal satellite diventava «che
sono» (attacco tagliato, corretto a parte il 02/10): qui l'audio è intero e l'errore è del
modello. Altri errori ricorrenti: «esci» → «eshi», «pesci», «è così»; «Puoi cambiare voce»
→ «Vuoi cambiare voce»; «E quella della Spagna?» → «Grazie a tutti.» (allucinazione nota).

**Proposta**: lasciare il servizio com'è (`-bs 5`, `--prompt "Conversazione con Calliope."`):
nessuna variante lo batte; beam 8 costa uguale ma sbaglia di più sulle frasi dette subito
(18,7 % contro 16,7 %), il prompt più lungo peggiora la wake word, senza il prompt col nome
la WER quasi raddoppia. Il prompt che conta è quello che Calliope manda a ogni richiesta
(`ServerTranscriber.prompt`), non `--prompt` della riga di comando. Il punto e mezzo che
manca rispetto al portatile (11,0 %) è delle hotwords, che `whisper-server` non ha: per
recuperarlo servirebbe faster-whisper sulla GPU (CTranslate2 compilato con CUDA per sm_121,
§1.1) o un server che le accetti.

Il client è uno solo (`ServerTranscriber`, API OpenAI multipart: file WAV, `model`,
`language`, `prompt`, `temperature` 0): vale per vLLM, whisper.cpp con
`--inference-path /v1/audio/transcriptions` e speaches. Se il server non risponde entro
`stt_timeout_s` (5 s) la frase si trascrive su CPU, e il server si riprova dopo 30 s; il
registro delle capacità dice «guasta: trascrivo su CPU» e il passo. All'avvio, con il
server già giù, il modello CPU si carica subito (non alla prima frase).

### 1.2 La voce sulla DGX: Ollama o vLLM

- **Ollama** (0.35.0 sulla DGX): nessuna modifica, `num_ctx` rispettato, è ciò che è
  misurato sul portatile. Rischio noto: lo stesso Ollama è andato in «CUDA error: an
  illegal memory access» con le richieste dell'agente che hanno i tool (qwen3.6). Con
  gemma4 e i 40 tool della voce non è provato.
- **vLLM** (`setup/linux/motore/vllm.sh voce`, porta 8001): backend `openai` di Calliope,
  già tenuto in piedi per il principio 1. Verificato [V] e provato a secco [M]:
  - tool calling: `--enable-auto-tool-choice --tool-call-parser gemma4` (il parser esiste e
    funziona in streaming, documentazione di vLLM);
  - le chiamate arrivano a pezzi per `index` (id e nome, poi gli argomenti): le ricompone
    `merge_tool_deltas`, provato contro il vLLM finto di `prove/ollama_finto.py`;
  - **thinking**: su Gemma 4 in vLLM è spento di predefinito; si governa con
    `chat_template_kwargs.enable_thinking`. `reasoning_effort: "none"` (il predefinito di
    Calliope per Ollama) **non è garantito** su vLLM (accetta low/medium/high): nuovo campo
    `llm_chat_template_kwargs` (passato in `extra_body`, solo backend openai) e, sulla DGX,
    `llm_reasoning_effort: null`. Con Ollama il corpo della richiesta resta identico
    (provato);
  - `num_ctx` non esiste: il contesto lo fissa `--max-model-len` (16384 come sul portatile);
  - lo scrittore dei documenti usa già `response_format` `json_schema`, che vLLM supporta
    (xgrammar); passa anche lui `chat_template_kwargs`.
- Il nome del modello cambia (`gemma4-e4b`, il `--served-model-name`): è l'unica cosa da
  cambiare oltre all'URL (principio 1).

---

## 2. Portabilità del codice: cosa era solo Windows

| Punto | Prima | Ora su Linux |
|---|---|---|
| VAD | torch + silero-vad | onnxruntime (`calliope/vad.py`, `vad_motore: auto`) |
| Whisper GPU | CTranslate2 CUDA | server (`stt_motore: server`) + ripiego CPU; passo per la GPU per piattaforma (`capacita.passo_gpu`) |
| Stima del genere all'arruolamento | torchaudio | senza torch dà None: Calliope chiede (comportamento della zona grigia) |
| PC a voce (`calliope/pc/`) | pycaw, WinRT, pywin32 | **degrada**: «mancante, non è Windows» o, nell'esempio della DGX, spento; nessun esecutore Linux |
| Cartella documenti | FOLDERID_Documents via ctypes | `xdg_documents`: `~/.config/user-dirs.dirs` (con il desktop in italiano «~/Documenti»), poi `~/Documents` |
| Tunnel SSH | OpenSSH di Windows in un job object | OpenSSH di Linux, stesse opzioni; muore con il servizio (cgroup di systemd, `KillMode=control-group`). **PR_SET_PDEATHSIG non va usato qui**: scatta alla fine del *thread* che ha creato il figlio, e il tunnel nasce in un thread breve |
| Sandbox | job object | `resource` (memoria, niente figli), **nice 10** e PR_SET_PDEATHSIG (il thread dei lavori aspetta il processo), gruppo di processi |
| Indice della biblioteca | BELOW_NORMAL_PRIORITY_CLASS | `os.nice(10)` |
| Kiosk degli schermi | `msedge.exe --kiosk` | `chromium --kiosk --incognito` |
| Messaggi | `.ssh\config`, «Funzionalità facoltative», `pip install nvidia-cublas-cu12` | `~/.ssh/config`, `sudo apt install openssh-client`, `sudo apt install libportaudio2`, «calliope extra documenti» nell'installazione gestita (venv di uv: niente pip) |
| Server del modello giù (backend openai) | «Ollama non risponde» | «il server del modello non risponde» con il passo per vLLM |
| Avvio sotto systemd | — | `main.notifica_systemd("READY=1")` dopo il saluto (sd_notify senza libsystemd) |
| Lucchetto d'istanza | porta 47913 | uguale (su Linux una porta legata e non in ascolto vale lo stesso) |
| Sezione YAML con tutte le chiavi commentate | «sezione sconosciuta» | ignorata in silenzio (serve all'esempio per la DGX) |

Nessuna dipendenza nativa nuova. I percorsi dei dati erano già tutti relativi alla cartella
di lavoro (principio 3): è questo che permette di tenere i dati fuori dal codice senza
toccare Calliope.

---

## 3. Come installare e aggiornare: le alternative

Criteri dell'utente: un comando per installare, uno per aggiornare, ritorno indietro se
l'aggiornamento non parte, dati che sopravvivono a tutto. In più: GPU, audio, dimensione,
ARM.

| | (a) git + uv + systemd utente (**scelta**) | (b) Docker / Compose | (c) pacchetto .deb / apt | (d) snap, AppImage, pipx |
|---|---|---|---|---|
| Installare | `sh setup/linux/installa.sh` | `docker compose up -d` (dopo aver costruito o scaricato l'immagine) | `sudo apt install ./calliope.deb` | `snap install`, file AppImage |
| Aggiornare | `calliope aggiorna`: fetch, versione nuova in una cartella sua, `uv sync --frozen`, verifica a secco, riavvio con READY, ritorno automatico | `docker compose pull && up -d`; il ritorno automatico va scritto (healthcheck + script) | `apt upgrade`: nessun ritorno automatico; il ritorno è `apt install calliope=<vecchia>` se il .deb vecchio è ancora in un repository | snap: `refresh` e `revert` sì; AppImage no |
| Ritorno indietro | `calliope torna` (istantaneo: la versione di prima è ancora lì con il suo venv), con o senza i dati di allora | tag precedente dell'immagine | a mano | snap sì |
| Dati | `~/calliope`, mai toccati; copia di memoria.db, speakers.json, calliope.yaml a ogni cambio | volume montato | `/var/lib` o home: da progettare | confinamento: la home è limitata (snap) |
| Audio | diretto (PipeWire/ALSA della sessione utente) | `/dev/snd` o il socket di PipeWire montato, `PULSE_SERVER`, utente e gruppo `audio` nel container: fragile, e ogni satellite futuro lo richiede di nuovo | diretto | snap: interfacce `audio-record`/`audio-playback` da dichiarare |
| GPU | non serve a Calliope (i modelli sono nei container) | NVIDIA Container Toolkit, preinstallato su DGX OS [V] | non serve | snap: complicato |
| Dimensione | venv ~1 GB senza torch (stima [D]) | immagine Python + le stesse librerie, ~1,5–2 GB, più i livelli a ogni versione | come (a) | snap grande; AppImage con Python dentro |
| ARM | wheel aarch64 verificati, lock universale | immagine arm64 da costruire (sulla DGX stessa o con buildx) | .deb arm64 da costruire | snapcraft/AppImage arm64 da costruire |
| Sudo | no (solo `apt install libportaudio2` una volta) | gruppo docker | sì, a ogni aggiornamento | snap: sì per installare |
| Sviluppo | la stessa forma del portatile (sorgenti, `python -m prove`) | ricostruire l'immagine a ogni prova | ricostruire il pacchetto | ricostruire |
| Lavoro per noi | ~600 righe (gestore, installatore, unità) + prove | Dockerfile, compose, registro o build locale, script di ritorno, audio | packaging Debian, postinst, repository | snapcraft.yaml, interfacce |

**Perché (a).** È l'unica che dà ritorno automatico vero senza infrastruttura (registro
d'immagini, repository apt): la versione nuova si prepara accanto a quella in uso, si
verifica, si attiva con un puntatore atomico e, se `systemctl restart` non arriva al
READY=1 di Calliope, si torna indietro da soli. L'audio resta quello della sessione
dell'utente, che è il punto più fragile dei container. uv risolve il lock universale una
volta sul portatile e installa sulla DGX esattamente le stesse versioni (`--frozen`), in
pochi secondi con la cache (hard link). Niente sudo dopo il primo `apt install`.

**Perché non (b) per Calliope**, ma sì per i modelli: vLLM ha bisogno di CUDA, di un'immagine
NVIDIA e di nient'altro dalla sessione dell'utente: è già un container sulla DGX e ci
restano anche la voce e Whisper. Calliope invece vuole microfono, altoparlante, `~/.ssh` per
il tunnel, la cartella documenti dell'utente, e gira in Python puro su wheel che esistono:
il container aggiungerebbe solo passaggi. Quando i satelliti porteranno l'audio in rete,
un'immagine di Calliope diventerà più semplice: il gestore non lo impedisce.

**Perché non (c) e (d)**: richiedono sudo a ogni aggiornamento (.deb) o un confinamento
che complica audio, `~/.ssh` e i file (snap), e nessuno dei due dà il ritorno automatico
dopo un avvio fallito. AppImage non ha aggiornamenti né ritorno.

**uv contro pip + venv**: uv 0.12.22 ha il binario aarch64 [V]; il lock è universale (uno
per Windows e Linux, provato: `uv lock` 1,2 s, `uv sync --frozen` di un venv completo su
Windows in 47 s a cache vuota [M]); `override-dependencies` con marcatore toglie torch su
Linux senza toccare Windows; `required-environments` fa fallire il lock sul portatile se un
pacchetto non ha il wheel per la DGX; non serve `python3-venv`. pip non ha un lock nativo:
la DGX installerebbe versioni diverse da quelle provate.

### 3.1 Come funziona il gestore (`setup/linux/gestore.py`)

```
~/.local/share/calliope/          il codice (CALLIOPE_APP)
    repo.git/                     copia «bare» della sorgente
    versioni/<AAAAMMGG-HHMM>-<commit>/   codice estratto (git archive) + .venv di uv
    attuale, precedente           l'id della versione in uso e di quella di prima
    gestione.json                 sorgente, ramo o tag, extra, Python, storia
    backup/<data>-da-<versione>/  memoria.db (API di backup di SQLite), speakers.json,
                                  calliope.yaml prima di ogni cambio (ne restano 5)
~/calliope/                       i dati (CALLIOPE_DATI): calliope.yaml, calliope.locale.yaml,
                                  segreti.yaml, dgx.yaml, memoria.db, speakers.json, registro/,
                                  biblioteca/, voices/, models/, wakeword/modelli/, lavori/
~/.local/bin/calliope             il gestore stesso
~/.config/systemd/user/calliope.service
```

- `calliope aggiorna`: fetch → commit bersaglio (cima del ramo, o ultimo tag `v*` con
  `--segui tag`, o `--rif`) → estrazione in una cartella nuova → `uv sync --frozen` →
  **verifica a secco** con i dati veri (import di `calliope.main` e `calliope.stato`,
  `python -m calliope.stato --json`) → copia dei dati → `calliope.yaml` rigenerato dalla
  versione nuova (`python -m calliope.config --esempio --scrivi`; se era stato cambiato a
  mano, copia `.bak`) → puntatore atomico → `systemctl --user restart` (aspetta READY=1,
  `TimeoutStartSec=300`) e 5 s di controllo → se fallisce: puntatore indietro, dati e
  `calliope.yaml` di prima (quelli scritti dalla versione nuova restano come
  `.dopo-<versione>`), riavvio. Il gestore in `~/.local/bin` si sostituisce solo dopo un
  aggiornamento riuscito. Restano al più 3 versioni.
- `calliope torna [versione] [--con-dati]`, `calliope versioni`, `calliope extra casa`,
  `calliope stato`, `calliope avvia|ferma|riavvia|log`, `calliope esegui` (lo usa systemd:
  exec del Python della versione in uso, nella cartella dei dati), `calliope sorgente URL`.
- Una versione senza `pyproject.toml` e `uv.lock` (i commit prima di questo lavoro) non si
  installa: il ritorno indietro vale tra versioni installate dal gestore.

**Da dove si aggiorna** (il repository non ha un remoto): la sorgente è quella da cui si è
installato (`--sorgente`; `installa.sh` usa l'`origin` del clone da cui si lancia, o il
clone stesso). Il flusso consigliato: un repository «bare» sulla DGX (`git init --bare
~/calliope.git`), dal portatile `git push <alias>:calliope.git main`, sulla DGX un clone da
lì per lanciare `installa.sh` e poi, a ogni push, `calliope aggiorna`. Oppure un
repository privato in rete (`calliope sorgente <URL>`). Si installano solo commit, mai il
working tree.

---

## 4. Modelli e memoria sulla DGX

| Servizio | Dove | Porta | Memoria (`--gpu-memory-utilization`) |
|---|---|---|---|
| Agente (qwen3.6-35b NVFP4) | container `calliope-vllm` (già c'è) | 8000 | 0,40 (~48 GB) |
| Voce (gemma 4 E4B) | `vllm.sh voce` → `calliope-voce`, oppure Ollama | 8001 (Ollama 11434) | 0,20 |
| Whisper large-v3-turbo | whisper.cpp, servizio `calliope-whisper` (`vllm.sh stt` scartato) | 8003 | fuori da vLLM (~1,6 GB del modello ggml) |

Stessa immagine dell'agente (`vllm/vllm-openai:v0.29.0`, provata su questa DGX con il driver
di DGX OS: le immagini NVIDIA ≥ 26.03 vogliono il driver ≥ 595 [V, forum NVIDIA]). Totale
0,66: le note NVIDIA per Spark consigliano di stare sotto ~0,7. Lo script non scarica
nulla: se i pesi mancano dice il comando (`hf download …`), da lanciare solo con il
consenso. Con l'agente sulla stessa macchina niente tunnel: `agenti_url:
http://127.0.0.1:8000/v1`.

**Casa**: la DGX è in ufficio, e Home Assistant di casa è già esposto con DuckDNS. Sulla DGX
`casa_url` è l'indirizzo **DuckDNS** (`https://<nome>.duckdns.org:8123`), con la verifica
TLS normale (il certificato è proprio per quel nome): niente `casa_tls_nome` né impronta.
Quando la DGX sarà in casa si torna all'IP del Raspberry con `casa_tls_nome`, come sul
portatile.

---

## 5. File nuovi e cambiati

- Nuovi: `pyproject.toml`, `uv.lock`, `calliope/vad.py`, `setup/linux/gestore.py`,
  `setup/linux/installa.sh`, `setup/linux/calliope.service`,
  `setup/linux/calliope.locale.esempio.yaml`, `setup/linux/motore/vllm.sh`,
  `prove/prova_linux.py`, `prove/prova_gestore.py`, questo rapporto.
- Cambiati: `calliope/audio.py` (VAD), `calliope/stt.py` (`ServerTranscriber`,
  `make_transcriber`), `calliope/main.py` (`notifica_systemd`), `calliope/brain.py` e
  `documenti/scrittore.py` (`llm_chat_template_kwargs`), `calliope/config.py` (campi
  `vad_motore`, `vad_modello`, `stt_motore`, `stt_url`, `stt_modello`, `stt_timeout_s`,
  `llm_chat_template_kwargs`; `--esempio --scrivi`; sezioni vuote), `calliope/capacita.py`
  (Whisper su server, passi per piattaforma, `comando_libreria`), `documenti/consegna.py`
  (XDG), `agenti/` (messaggi, nice, PR_SET_PDEATHSIG nella sandbox), `installa/servizio.py`
  (nice), `schermi/__main__.py` (kiosk), `casa/guida.py`, `documenti/__init__.py`,
  `schermi/__init__.py` (passi), `calliope/__main__.py` (`cli`), `calliope.yaml`
  (rigenerato), `prove/__main__.py`, `prove/LEGGIMI.md`, `CLAUDE.md`.

---

## 6. Rischi

1. **Whisper sul server**: vLLM, senza beam search, dava 21 % e si è passati a whisper.cpp
   con `-bs 5` (12,4 %). Le hotwords non ci sono nemmeno lì: il punto e mezzo che manca
   rispetto al portatile (11,0 %).
2. **Audio sotto systemd**: il servizio utente con `enable-linger` deve vedere PipeWire anche
   senza nessuno collegato; i dispositivi USB vanno scelti per nome (`input_device`). Da
   provare.
3. **vLLM ≥ 3 container sulla stessa GPU**: la somma delle frazioni non è garantita sulla
   memoria unificata; le immagini NVIDIA nuove vogliono un driver più recente di quello di
   DGX OS.
4. **gemma4 su Ollama della DGX con i tool**: possibile lo stesso errore CUDA dell'agente.
5. **Sandbox su Linux**: `RLIMIT_AS` con OpenBLAS e thread può impedire l'avvio di numpy
   (su Windows era successo con il tetto del job); `RLIMIT_NPROC=0` conta i processi di
   tutto l'utente: va provato che non blocchi il primo processo. Un isolamento vero su
   Linux è a portata (utente dedicato, `unshare -n` senza rete, container): da fare.
6. **Wake word**: il modello addestrato (`wakeword/modelli/calliope.onnx`) non si scarica:
   va copiato dal portatile insieme a `speakers.json` e `memoria.db`.
7. **uv.lock** va rigenerato (`uv lock`) quando cambia `pyproject.toml`; la prova a secco
   controlla solo che torch resti fuori da Linux e che i pacchetti principali abbiano il
   wheel aarch64.

---

## 7. Da provare sulla DGX vera (in ordine)

Prima installazione (nessun modello scaricato senza conferma):

1. `sudo apt install libportaudio2` (e, se mancano, `git curl fonts-dejavu-core`).
2. Portare il codice: dal portatile `git push` verso un repository bare sulla DGX (`git
   init --bare ~/calliope.git` una volta), poi sulla DGX `git clone ~/calliope.git
   ~/calliope-sorgente`.
3. `sh ~/calliope-sorgente/setup/linux/installa.sh` → uv (chiede), copia della sorgente,
   versione, venv, verifica, `~/calliope/calliope.yaml`, `calliope.locale.yaml`
   dall'esempio, unità systemd. La sorgente degli aggiornamenti è l'`origin` del clone
   (`~/calliope.git`); `calliope sorgente` la cambia.
   *Misurare*: tempo di `uv sync` a cache vuota e piena, dimensione del venv.
4. Copiare i dati dal portatile in `~/calliope/`: `speakers.json`, `memoria.db`,
   `wakeword/modelli/calliope.onnx`, `voices/`, `models/speaker/`, `biblioteca/` (o
   riscaricarla con `calliope stato --installa biblioteca`), `segreti.yaml`.
5. `calliope.locale.yaml`: `casa_url` con il nome DuckDNS, `agenti_url`
   `http://127.0.0.1:8000/v1`, microfono e altoparlante per nome.
6. `calliope stato`: deve dire «audio» attivo con i dispositivi giusti, «trascrizione» su
   CPU con il passo del server.
7. Modello della voce (**con conferma**): `ollama pull gemma4:e4b-it-qat` e prova con
   `calliope esegui` in primo piano. *Misurare*: prima frase (mediana e p90) e se Ollama
   regge i tool senza errori CUDA. Se no: pesi di `google/gemma-4-E4B-it`,
   `setup/linux/motore/vllm.sh voce avvia`, la sezione vLLM di `calliope.locale.yaml`.
   *Misurare*: prima frase con e senza tool, `prova_brain_ollama` e `prova_pc_ollama`
   adattate al backend openai.
8. Whisper (**con conferma**): ~~vLLM~~ (21 %, scartato) → `calliope motore whisper
   compila`, `scarica`, `installa`, `stt_motore: server`, `stt_url:
   http://127.0.0.1:8003/v1`; `calliope stato --installa whisper_riserva` per il ripiego.
   *Fatto il 02/10*: WER 12,4 % (§1.1).
9. `calliope avvia`, `loginctl enable-linger $USER`, riavvio della DGX: Calliope deve
   ripartire da sola e dire il saluto. *Misurare*: tempo all'avvio fino a READY.
10. Un aggiornamento vero: un commit innocuo, `git push`, `calliope aggiorna` (deve
    riavviare e restare accesa); poi un commit che rompe l'avvio di proposito su un ramo di
    prova (`calliope aggiorna --rif prova-rotta`): deve tornare da sola alla versione di
    prima. Infine `calliope torna` e di nuovo `calliope aggiorna`.
11. Sandbox degli agenti su Linux: `prova_agenti.py` sulla DGX (la parte della sandbox gira
    con i limiti POSIX veri), `prove/arm/` per la biblioteca.
12. `python -m prove` nel venv della versione in uso (con l'extra `prove`) sulla DGX.
