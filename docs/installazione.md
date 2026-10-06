# Installazione e avvio, passo per passo

Procedura deterministica per una persona o per un agente di programmazione. Ogni passo ha il
comando, il risultato atteso e il controllo. I comandi vengono dal codice del repository
(`setup/linux/installa.sh`, `setup/linux/gestore.py`, `setup/linux/motore/*.sh`,
`calliope/stato.py`, `calliope/installa/catalogo.py`); i dettagli e il perché delle scelte
sono in [`aree/setup-dgx.md`](aree/setup-dgx.md) e [`aree/setup-windows.md`](aree/setup-windows.md).

Regole per chi automatizza:
- **Nessun download senza conferma.** Gli script che scaricano (uv, modelli, immagini Docker,
  pesi di vLLM) chiedono `[s/N]` o stampano il comando da lanciare: non aggirarli.
- **Mai sudo negli script di Calliope.** Dove serve (pacchetti di sistema, Ollama, Docker) il
  comando lo lancia l'amministratore della macchina.
- **Lo stato si legge, non si indovina**: `calliope stato` (Linux) o `python -m calliope.stato`
  (Windows) dicono per ogni capacità `attiva`, `da_configurare`, `mancante` o `guasta`, con il
  prossimo passo; `--json` per gli script, `--dettagli` per i motivi.
- **Configurazione**: mai modificare `calliope.yaml` (si rigenera); le chiavi di
  un'installazione vanno in `calliope.locale.yaml`, i segreti in `segreti.yaml`, tutti e due
  accanto a `calliope.yaml` e fuori da git.

## Indice

- [A. Server Linux con GPU NVIDIA (DGX Spark, Ubuntu 24.04 aarch64)](#a-server-linux-con-gpu-nvidia)
- [B. PC Windows 11 con GPU NVIDIA](#b-pc-windows-11-con-gpu-nvidia)
- [C. Linux x86-64](#c-linux-x86-64)
- [D. Satellite (un PC Windows come microfono e casse)](#d-satellite)
- [E. Telefono come satellite](#e-telefono)
- [F. Servizi facoltativi: ordine, porte, memoria](#f-servizi-facoltativi)
- [G. Problemi comuni](#g-problemi-comuni)

## A. Server Linux con GPU NVIDIA

Provato su DGX Spark (DGX OS, Ubuntu 24.04 aarch64, GPU Blackwell GB10, memoria unificata
~119 GB visibili). Codice in `~/.local/share/calliope/versioni/<data>-<commit>/` (un venv di
uv per versione), dati in `~/calliope/`, servizio **systemd utente** `calliope`.

### A.1 Prerequisiti

| Cosa | Controllo | Atteso |
|---|---|---|
| Driver NVIDIA | `nvidia-smi` | la GPU elencata |
| CUDA (solo per whisper.cpp) | `/usr/local/cuda/bin/nvcc --version` | presente (DGX OS: CUDA 13) |
| Python di sistema ≥ 3.10 (per il gestore) | `python3 --version` | Ubuntu 24.04: 3.12 |
| git, curl, PortAudio | `command -v git curl; ldconfig -p \| grep libportaudio.so.2` | tutti presenti |
| Per whisper.cpp: cmake e g++ | `command -v cmake g++` | presenti |
| Docker (facoltativo: sandbox, vLLM, SearXNG) | `docker info` senza sudo | risponde (utente nel gruppo `docker`) |
| Ollama | `curl -s http://127.0.0.1:11434/api/version` | `{"version":"…"}` |

Mancanze, lanciate dall'amministratore:

```bash
sudo apt install libportaudio2 git curl cmake g++     # l'unico obbligatorio per Calliope è libportaudio2
curl -fsSL https://ollama.com/install.sh | sh          # installatore ufficiale di Ollama
```

### A.2 Modello della voce

```bash
ollama pull gemma4:e4b-it-qat          # predefinito (profilo gemma4-e4b-ollama)
# facoltativo, più bravo con i tool:  ollama pull gemma4:26b-a4b-it-qat   (~15 GB)
ollama list                            # atteso: il modello elencato
```

### A.3 Installazione

```bash
git clone <URL del repository> ~/calliope-sorgente
sh ~/calliope-sorgente/setup/linux/installa.sh
```

Cosa fa (senza sudo): controlla i prerequisiti e, se ne manca uno, stampa il comando `apt` e
si ferma; chiede se scaricare **uv** (~20 MB, in `~/.local/bin`); copia la sorgente in un
repository bare, crea la versione con `uv sync --frozen` dal lock, la **verifica**
(import e `python -m calliope.stato --json`), scrive `~/calliope/calliope.yaml` e
`~/calliope/calliope.locale.yaml` (dall'esempio
[`setup/linux/calliope.locale.esempio.yaml`](../setup/linux/calliope.locale.esempio.yaml)),
installa il servizio utente e il comando `~/.local/bin/calliope`. Poi chiede (`[s/N]`) il
**Whisper di riserva** per la CPU (1,6 GB) e, se c'è Docker, l'immagine della **sandbox**
(~290 MB). Extra installati: `documenti, modelli, casa, schermi`.

Controllo:

```bash
calliope versioni                     # una versione, «in uso»
calliope stato                        # tabella delle capacità con il prossimo passo
```

### A.4 Modelli e file che Calliope non scarica da sola

```bash
calliope stato --catalogo                         # elenco delle azioni installabili
calliope stato --installa modello_chi_parla       # CAM++ (~28 MB): senza, Calliope non parte
calliope stato --installa voce_serena_alta        # la voce predefinita di Piper
calliope stato --installa biblioteca              # facoltativo: Wikipedia e altre fonti (~12 GB) + indice
```

Ogni azione mostra la proposta (dimensione, spazio libero) e chiede conferma; i file si
verificano con SHA-256.

**Wake word acustica**: il modello addestrato di «Calliope» **non è nel repository** (feature
derivate da ACAV100M, licenza non commerciale). Senza `wakeword/modelli/calliope.onnx` Calliope
usa la wake word **testuale** (ogni frase passa da Whisper) con l'audio locale; **i satelliti e
il telefono invece la richiedono**. Per addestrarne uno: [`../wakeword/`](../wakeword/) e
[`ricerche/2026-09-24-wake-word.md`](ricerche/2026-09-24-wake-word.md); i due modelli di feature
di openWakeWord si scaricano con `python wakeword/scarica_modelli.py`. Il file va in
`~/calliope/wakeword/modelli/`.

### A.5 Whisper sulla GPU (whisper.cpp)

CTranslate2 per Linux aarch64 è solo CPU: sulla GPU trascrive whisper.cpp, servizio utente
`calliope-whisper` su 127.0.0.1:8003.

```bash
calliope motore whisper compila       # sorgente al commit fissato, build CUDA (chiede conferma)
calliope motore whisper scarica       # ggml-large-v3-turbo.bin, 1,6 GB, SHA-256 (chiede conferma)
calliope motore whisper installa      # unità systemd utente, avvio
calliope motore whisper stato         # atteso: attivo e risponde
```

In `~/calliope/calliope.locale.yaml`:

```yaml
stt:
  stt_motore: server
  stt_url: http://127.0.0.1:8003/v1
```

### A.6 Configurazione minima (`~/calliope/calliope.locale.yaml`)

Stesse sezioni di `calliope.yaml`, solo le chiavi da cambiare:

```yaml
llm:
  llm_profilo: gemma4-e4b-ollama      # oppure gemma4-26b-ollama, gemma4-26b-vllm (PROFILI_LLM in calliope/config.py)
stt:
  stt_motore: server                  # whisper.cpp del passo A.5; senza: faster-whisper su CPU
  stt_url: http://127.0.0.1:8003/v1
server_satelliti:
  audio_modo: satellite               # microfono e casse sono dei satelliti (il server non ha audio)
  satellite_indirizzo: 0.0.0.0        # in rete: serve il certificato (passo D.1)
schermi:
  schermi_indirizzo: 0.0.0.0          # pagina degli schermi e del telefono in rete, in HTTPS
casa:
  casa_url: https://<indirizzo di Home Assistant>:8123     # facoltativo
web:
  web_searxng_url: http://127.0.0.1:8004                   # facoltativo (passo F)
agenti:
  agenti_url: http://127.0.0.1:8000/v1                     # facoltativo (passo F)
  agenti_modello: qwen3.6-35b
```

Segreti in `~/calliope/segreti.yaml` (permessi 600), mai nel file sopra:

```yaml
home_assistant:
  token: "<token di accesso a lungo termine di un utente amministratore di HA>"
```

### A.7 Avvio e controllo

```bash
calliope avvia                        # systemd utente; torna quando Calliope ha detto il saluto (READY=1)
calliope stato                        # le capacità attive
calliope log                          # journal del servizio
ss -ltn | grep -E ':(8770|8771|8003|11434)\b'   # schermi, satelliti, whisper.cpp, Ollama
ollama ps                             # il modello della voce caricato (VRAM: misurare con nvidia-smi)
loginctl enable-linger $USER          # una volta: parte all'accensione
```

Aggiornamento e ritorno indietro: `calliope aggiorna` (versione nuova accanto, verifica,
riavvio, **ritorno automatico** se non parte), `calliope torna`, `calliope versioni`.

## B. PC Windows 11 con GPU NVIDIA

Provato su un portatile con RTX 5070 Laptop (8 GB) e Python 3.14. Qui Calliope gira **in
locale** (microfono e casse del PC, `audio_modo: locale`) oppure il PC fa da satellite (D).

```powershell
# 1. Ollama (installatore da ollama.com), poi il modello
ollama pull gemma4:e4b-it-qat
# 2. Ambiente Python, dalla cartella del repository
python -m venv .venv
.venv\Scripts\activate
pip install faster-whisper silero-vad sounddevice numpy openai httpx piper-tts torchaudio pyyaml
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12        # Whisper sulla GPU
# facoltativi: documenti, casa, schermi, PC a voce
pip install python-docx openpyxl fpdf2 pypdf websockets starlette uvicorn
pip install pycaw comtypes pywin32 psutil screen_brightness_control winrt-Windows.Media.Control
# 3. Modelli dal catalogo (conferma e SHA-256)
python -m calliope.stato --installa modello_chi_parla
python -m calliope.stato --installa voce_serena_alta
# 4. Controllo e avvio
python -m calliope.stato
python -m calliope
```

Atteso all'avvio: le righe `[CONFIG]`, `[STT]` con il dispositivo (`cuda`; `cpu` vuol dire che
mancano le DLL CUDA o il primo download è fallito, vedi G), `[CAPACITÀ] Capacità: N attive su
M`, il saluto. Dispositivi audio: `python -m sounddevice` e poi `input_device` /
`output_device` (numero o parte del nome) in `calliope.locale.yaml`, sezione `audio`.
`llm_base_url` e simili: sempre `127.0.0.1`, mai `localhost` (su Windows ~2 s persi per
connessione).

## C. Linux x86-64

Il lock (`uv.lock`) è risolto anche per `linux x86_64` e l'installatore A.3 non dipende
dall'architettura, ma **questo percorso non è stato provato**. Da sapere: su x86-64
CTranslate2 di PyPI supporta CUDA (servono le librerie CUDA 12 di sistema), oppure si usa
whisper.cpp come in A.5; l'extra `gpu` è solo per Windows.

## D. Satellite

Un PC Windows con microfono e casse fa da satellite di Calliope sul server. **Serve il modello
della wake word** (A.4).

1. **Sul server**, certificato TLS dei satelliti (stampa l'impronta):
   ```bash
   calliope satellite --certificato
   ```
2. **PC nuovo, un comando**: aprire `https://<server>:8770/satellite` e lanciare il comando
   PowerShell mostrato (scarica con la chiave del certificato fissata, installa uv e Python
   con SHA-256 fissati, in `%LOCALAPPDATA%\Calliope\satellite`, senza amministratore). Il
   satellite poi si aggiorna da solo e torna indietro se non si ricollega.
   **In alternativa, dal repository**: in `calliope.locale.yaml` sul PC, sezione `satellite`,
   `satellite_server: wss://<server>:8771`, poi `python -m calliope.satellite`.
3. Il satellite stampa un **codice** e l'impronta del server (da confrontare). Sul server:
   ```bash
   calliope satellite --abbina <codice> --stanza studio [--pc] [--personale <nome>]
   calliope satellite --elenco
   ```
   `--pc`: questo satellite esegue i tool `pc_*` (volume, file, app); `--personale`: il suo
   schermo riceve le schede personali di quella persona.

## E. Telefono

Il telefono diventa un satellite nel browser (PWA). Serve `audio_modo: satellite` e la pagina
degli schermi in rete (A.6).

```bash
calliope stato --installa telefono                  # onnxruntime-web e i modelli generici (~14 MB)
calliope schermi --certificato --host <IP1>,<IP2>   # CA di casa + certificato della pagina
```

Installare la CA sul telefono, aprire `https://<IP>:8770/telefono`, «Aggiungi alla schermata
Home»; il codice mostrato si abbina come un satellite:
`calliope satellite --abbina <codice> --stanza telefono --personale <nome>`. Il telefono vuole
anche `calliope.onnx` (wake word nel browser). Passi completi:
[`../prove/manuali/telefono.md`](../prove/manuali/telefono.md).

## F. Servizi facoltativi

Ordine consigliato all'avvio della macchina: Ollama → `calliope-whisper` → vLLM (se usato) →
SearXNG (se usato) → `calliope`. I container hanno il riavvio automatico; Calliope aspetta il
modello all'avvio fino a `llm_attesa_avvio_s`.

| Servizio | Comandi | Porta (solo 127.0.0.1) | Chiave in `calliope.locale.yaml` |
|---|---|---|---|
| Ollama (voce) | `ollama pull …`, `ollama ps` | 11434 | `llm_profilo` |
| whisper.cpp | `calliope motore whisper compila\|scarica\|installa\|stato` | 8003 | `stt_motore: server`, `stt_url` |
| vLLM agente (Qwen3.6-35B-A3B NVFP4) | `calliope motore vllm agente avvia\|stato\|ferma` | 8000 | `agenti_url`, `agenti_modello` |
| vLLM voce (Gemma 4 26B-A4B NVFP4) | `calliope motore vllm voce avvia\|stato\|ferma` | 8001 | `llm_profilo: gemma4-26b-vllm` |
| SearXNG | `calliope motore searxng avvia\|stato\|prova` | 8004 | `web_searxng_url` |
| Sandbox Docker | `calliope motore sandbox costruisci [python\|csharp\|javascript]`, `… stato` | — | `agenti_sandbox_motore: auto` |

vLLM **non scarica i pesi da solo**: se mancano stampa il comando (`HF_HOME=… hf download
<modello>`). Memoria: lo script assegna all'agente 0,40 e alla voce 0,24 della memoria
unificata (`MEM`); le note NVIDIA per la DGX Spark consigliano di non superare ~0,7 in tutto.
Senza vLLM l'agente può usare lo stesso Ollama della voce (`agenti_url:
http://127.0.0.1:11434`). Senza Docker il codice degli agenti **non** si esegue.

## G. Problemi comuni

| Sintomo | Causa | Soluzione |
|---|---|---|
| `[STT]` su `cpu` al primo avvio su Windows, `WinError 1314` | la cache di Hugging Face non crea i link simbolici | riavviare: al secondo avvio il modello è in cache e va su GPU |
| ~2 s in più a ogni richiesta su Windows | `localhost` prova prima IPv6 | usare `127.0.0.1` negli URL |
| Ollama ricarica il modello a ogni domanda | `num_ctx` diverso tra le richieste | lasciare `llm_num_ctx: auto`; non mischiare client con contesti diversi sullo stesso modello |
| VRAM esaurita con Whisper | `ollama ps` sottostima | misurare con `nvidia-smi`; 4B + large-v3-turbo stanno in 8 GB |
| Calliope non parte, «chi parla» guasta | manca CAM++ o `speakers.json` illeggibile | `calliope stato --installa modello_chi_parla`; un `speakers.json` rotto non si sovrascrive mai (c'è la copia `.bak`) |
| Il satellite non parte | manca `calliope.onnx` | la wake word acustica è obbligatoria sui satelliti (A.4) |
| `calliope aggiorna` torna indietro da solo | la versione nuova non ha detto il saluto | `calliope log`; resta in uso la precedente con i suoi dati |
| Il server degli schermi non parte in rete | manca il certificato | `calliope satellite --certificato` (o `schermi_senza_tls: true`, sconsigliato) |
| Cuffie Bluetooth mute ma collegate | stato delle cuffie | spegnerle e riaccenderle, poi riavviare Calliope |
| La sandbox «non pronta» dopo un aggiornamento | il Dockerfile è cambiato | `calliope motore sandbox costruisci` |
