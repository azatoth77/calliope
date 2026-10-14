# Setup sulla DGX Linux

*Installazione e aggiornamento sulla DGX Spark (Ubuntu 24.04 aarch64): uv, gestore `calliope`, systemd, motori. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 14/10.** Come al 09/10 (sotto): nessun cambio al gestore né ai motori dopo il 09/10. Dal 14/10 sera lo script di misura per l'arbitro della memoria (sotto, da lanciare). Il gestore passa a Calliope anche `calliope stato …` (tutte le opzioni in [capacita-installazioni](capacita-installazioni.md)), `calliope conserva [--svuota [--persona …]] [--json]` (dati conservati per le misure, dal 12/10), `calliope satellite …` e `calliope schermi …` (abbinamenti e certificati) ed `calliope esegui` (Calliope in primo piano); `calliope prova-e2e` e `calliope motore …` hanno il loro ramo. Comandi controllati sul codice il 14/10.

*Stato al 09/10 (storico):* Calliope gira sulla DGX dal 02/10 come servizio utente systemd, aggiornata con `calliope aggiorna` (ritorno automatico; dal 06/10 non interrompe in silenzio i lavori dell'agente). Voce su Ollama scelta con `llm_profilo`, Whisper con whisper.cpp, agente qwen3.6 su vLLM, SearXNG e sandbox Docker accanto. Dal 07/10 l'extra `voce-gpu` porta Piper sulla GPU (onnxruntime-gpu su aarch64). La prova end-to-end su un'istanza di prova c'è dal 06/10.

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Installazione e aggiornamento (Linux, DGX) | uv (lock universale), git, systemd utente; gestore in sola libreria standard | `pyproject.toml`, `uv.lock`; `setup/linux/` → `gestore.py` (comando `calliope`: `installa`, `aggiorna`, `torna`…), `installa.sh`, `calliope.service`, `calliope.locale.esempio.yaml`, `motore/vllm.sh` (voce e agente su vLLM; Whisper su vLLM provato e scartato il 02/10), `motore/whisper.sh` e `motore/calliope-whisper.service` (whisper.cpp), `motore/whisper-lento.sh` e `motore/calliope-whisper-lento.service` (il secondo Whisper della corsia lenta della stanza, dal 14/10 sera, facoltativo), `motore/sandbox.sh`, `motore/searxng.sh`, `motore/gemma4_template.py` |
| Prova end-to-end su un'istanza di prova (06/10) | solo libreria standard; satelliti veri con microfono e casse finti | `prove/e2e/` → `lancia.py`, `istanza.py`, `satelliti.py`, `copioni.py`, `verifica.py`; manuale [`prove/manuali/e2e-dgx.md`](../../prove/manuali/e2e-dgx.md) |

## Setup (DGX Linux)

Dal 02/10/2026 il target principale è la **DGX Spark con DGX OS** (Ubuntu 24.04 aarch64).
Scelte, matrice delle dipendenze verificata e passi della prima installazione vera in
[`docs/ricerche/2026-10-02-impacchettamento-dgx-linux.md`](../ricerche/2026-10-02-impacchettamento-dgx-linux.md).
Installata sulla DGX il 02/10 (servizio utente con linger, Whisper su whisper.cpp). Un comando per installare, uno per aggiornare, con
ritorno automatico alla versione di prima se quella nuova non parte:

```bash
sudo apt install libportaudio2            # l'unico pacchetto di sistema obbligatorio
git clone ~/calliope.git ~/calliope-sorgente   # o da dove sta il repository
sh ~/calliope-sorgente/setup/linux/installa.sh  # uv (chiede), venv dal lock, verifica, servizio

calliope stato            # cosa funziona e cosa manca, con i passi di Linux
calliope avvia | ferma | riavvia | log
calliope aggiorna         # versione nuova accanto, verifica, riavvio, ritorno automatico
                          # (--attendi-lavori / --forza con lavori dell'agente in corso)
calliope torna            # alla versione precedente (--con-dati: anche memoria e voci di allora)
calliope versioni | calliope extra casa | calliope sorgente <URL>
calliope extra voce-gpu   # Piper sulla GPU (07/10): CUDA 13 e cuDNN da pip, ~2,4 GB
loginctl enable-linger $USER              # una volta: parte all'accensione

# Whisper sulla GPU: whisper.cpp con CUDA, servizio utente calliope-whisper (porta 8003)
calliope motore whisper compila          # sorgente al commit fissato, build CUDA (chiede)
calliope motore whisper scarica          # ggml-large-v3-turbo.bin con SHA-256 (chiede)
calliope motore whisper installa         # unità systemd, avvio; poi stt_motore/stt_url
calliope stato --installa whisper_riserva   # faster-whisper su CPU se il server cade

# Facoltativo (14/10 sera): il secondo Whisper della corsia lenta della stanza, large-v3 q5_0,
# servizio utente calliope-whisper-lento (porta 8004); lo stesso whisper-server compilato sopra
calliope motore whisper-lento scarica    # ggml-large-v3-q5_0.bin con SHA-256 (chiede)
calliope motore whisper-lento installa   # unità systemd, avvio, memoria vera sulla GPU
calliope motore whisper-lento stato|memoria|ferma|avvia|disinstalla
```

- **Codice e dati separati**: il codice in `~/.local/share/calliope/versioni/<data>-<commit>/`
  (ognuna con il suo `.venv` di **uv**, `uv sync --frozen` da `uv.lock`), i dati in
  `~/calliope/` (`calliope.yaml`, `calliope.locale.yaml`, `segreti.yaml`, `dgx.yaml`,
  `memoria.db`, `speakers.json`, `registro/`, `biblioteca/`, `voices/`, `models/`,
  `wakeword/modelli/`), che è la cartella di lavoro di Calliope: i percorsi relativi
  (principio 3) bastano. Prima di ogni cambio di versione si copiano memoria.db,
  speakers.json e calliope.yaml in `~/.local/share/calliope/backup/`.
- **Gestore** `setup/linux/gestore.py` (solo libreria standard, installato come
  `~/.local/bin/calliope`) e **unità systemd utente** `setup/linux/calliope.service`
  (`Type=notify`: Calliope manda READY=1 dopo il saluto, `main.notifica_systemd`; è il
  segnale che l'aggiornamento è riuscito). Aggiornamenti dall'`origin` del clone: il
  portatile fa `git push` in un repository bare sulla DGX. Solo commit, mai il working tree.
- **pyproject.toml**: dipendenze di base + extra `documenti`, `modelli` (docxtpl e
  python-pptx, 03/10), `casa`, `schermi`, `pc` (solo Windows), `gpu` (DLL CUDA 12, solo
  Windows), `voce-gpu` (CUDA 13 e cuDNN per Piper sulla GPU, solo Linux aarch64, dal 07/10),
  `archivio` (pypdfium2, Pillow, python-docx), `prove`, `tutto`; `calliope installa` mette di
  serie `documenti`, `modelli`, `casa`, `schermi` (`EXTRA_PREDEFINITI`), gli altri con
  `calliope extra <nome>`; `calliope =
  calliope.__main__:cli`. `uv.lock` è universale (Windows e Linux): si rigenera con `uv lock`
  quando cambia pyproject.toml. Su Windows il venv con pip resta come prima.
- **onnxruntime-gpu su Linux aarch64** (07/10 sera): al posto di onnxruntime (stessa versione,
  stesso provider CPU; i due pacchetti installano lo stesso modulo, e un override di uv toglie
  onnxruntime anche dove lo chiedono piper-tts, faster-whisper e silero-vad). Senza l'extra
  `voce-gpu` lavora solo sulla CPU; con l'extra Piper sintetizza sulla GPU se la taratura lo
  sceglie (`tts_dispositivo`, misure in
  [contesto-conversazione](contesto-conversazione.md)). Il wheel vuole glibc 2.34 (Ubuntu
  24.04 ne ha 2.39) e pesa 206 MB invece di 17.
- **Senza torch su Linux**: torch di PyPI per aarch64 è quello con CUDA 13 (GB). Silero VAD
  usa il suo ONNX con onnxruntime (`calliope/vad.py`, `vad_motore: auto`; uguale a torch su
  32 464 finestre delle registrazioni vere, 0,55 ms contro 1,11); un override di uv tiene
  torch solo su Windows. Senza torchaudio la stima del genere all'arruolamento non c'è:
  Calliope chiede.
- **Whisper**: CTranslate2 per Linux aarch64 su PyPI (4.8.2) è **solo per CPU**. Sulla DGX
  Whisper sulla GPU lo serve **whisper.cpp** compilato con CUDA (`whisper-server`, servizio
  utente `calliope-whisper` su 127.0.0.1:8003, `-bs 5`, `--prompt "Conversazione con
  Calliope."`; script `setup/linux/motore/whisper.sh`, unità
  `setup/linux/motore/calliope-whisper.service`), e Calliope lo usa con `stt_motore:
  server`, `stt_url: http://127.0.0.1:8003/v1` (API OpenAI `/audio/transcriptions`,
  `ServerTranscriber`). Scelto all'installazione del 02/10 sulle 104 registrazioni con
  riferimento: **WER 12,4 %**, contro 21 % di vLLM con Whisper (niente beam search: immagine
  audio di vLLM scartata) e 11,0 % di faster-whisper sul portatile (che ha anche le
  hotwords). `calliope.service` ha `Wants=`/`After=calliope-whisper.service` nel modello
  del repository (un'aggiunta a mano spariva al primo `calliope aggiorna`). Se il server non
  risponde, faster-whisper su CPU (principio 7) con il **modello di riserva** in
  `models/whisper/large-v3-turbo/` (`whisper_cartella`), installato dal catalogo
  (`whisper_riserva`, 1,6 GB con SHA-256; `installa.sh` lo chiede): senza, il primo guasto
  lo farebbe scaricare con la voce ferma, e il registro delle capacità lo dice.
- **Il secondo Whisper della corsia lenta** (14/10 sera, facoltativo, **preparato e non
  acceso**): `setup/linux/motore/whisper-lento.sh` e l'unità `calliope-whisper-lento`
  (127.0.0.1:8004, `-bs 5`, nessun prompt fisso, `-t 2`, `Nice=10`), lo stesso `whisper-server`
  di `whisper.sh` (nessuna compilazione nuova) con **large-v3 q5_0** (1,08 GB di file, ~2 GB
  stimati; `VARIANTE=f16` per large-v3 intero, ~3,9 GB). Residente: con la memoria libera del
  14/10 (~21 GB) resta il posto per FLUX (13 GB) con ~6 GB di margine. `calliope.service` **non**
  lo aspetta: se è giù la corsia lenta tiene il testo della corsia veloce. Calliope lo usa solo
  con `stanza_lenta_stt_url: http://127.0.0.1:8004/v1` (sezione `conversazione_stanza` del
  locale), e solo dopo che il banco ha detto che fa meglio del Whisper dei turni (perché: la
  misura vera in [stt-tts](stt-tts.md); `stanza_lenta_ritrascrivi: auto` allora riaccende la
  ritrascrizione). `calliope stato --piano`, riga «Stanza lenta», mostra la sua memoria vera
  (nvidia-smi per processo) quando gira. I passi, dal portatile e sulla DGX:

  ```bash
  # 1. dopo l'unione: calliope aggiorna (sulla DGX), poi
  calliope motore whisper-lento scarica --si && calliope motore whisper-lento installa
  calliope motore whisper-lento memoria          # la memoria vera del processo
  calliope stato --piano                          # riga «Stanza lenta»: deve dire ✓
  # 2. le scelte della revisione sulla DGX (dal portatile, scp di OpenSSH di Windows; il .md
  #    è già in ~/calliope/privato/, dove lo ha scritto ritrascrivi_conservati.py)
  scp "$env:USERPROFILE\Downloads\scelte-ritrascrizione-20261014.json" DevLabDGX:calliope/privato/   # PowerShell
  # 3. il banco sulle 95 registrazioni (sulla DGX, dalla cartella dei dati): solo numeri
  V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
  cd ~/calliope && $V/.venv/bin/python $V/prove/manuali/banco_stanza_lenta.py \
      --conservati privato/ritrascrizione-conservati-20261014-1657.md \
      --scelte privato/scelte-ritrascrizione-20261014.json --ritrascrivi --salva privato
  # 4a. se un «lento*» ha la WER sotto «turni»: nel calliope.locale.yaml
  #       conversazione_stanza:
  #         stanza_lenta_stt_url: http://127.0.0.1:8004/v1
  #         stanza_lenta_prompt: no      # solo se ha vinto lento_senza_prompt
  #     poi calliope riavvia
  # 4b. altrimenti: calliope motore whisper-lento disinstalla (e, per provare f16,
  #     VARIANTE=f16 calliope motore whisper-lento scarica / installa, poi di nuovo il banco)
  ```
- **Voce**: `llm_profilo` in `calliope.locale.yaml` (03/10): `gemma4-e4b-ollama` (l'Ollama
  della DGX, il predefinito dell'esempio), `gemma4-26b-ollama` (stesso Ollama, modello
  `gemma4:26b-a4b-it-qat`) o `gemma4-26b-vllm` (Gemma 4 26B-A4B NVFP4,
  `calliope motore vllm voce avvia|ferma|stato`, container `calliope-vllm-voce` su
  127.0.0.1:8001, riavvio automatico, modello di chat corretto da `gemma4_template.py`).
  Cambiare la riga, poi `calliope riavvia`.
  L'agente è sulla stessa macchina: `agenti_url: http://127.0.0.1:8000/v1`, niente tunnel.
  Il suo container (`calliope-vllm`) dal 04/10 con `calliope motore vllm agente
  avvia|rifai|ferma|stato|riprendi` e, sulla DGX, `PAUSA=1` (modalità sviluppo di vLLM per la
  pausa dell'arbitro; rete Docker sua, solo 127.0.0.1: rischi in `prove/LEGGIMI.md`).
  `vllm.sh` non scarica pesi: dice il comando, da lanciare solo con il consenso.
- **Casa**: la DGX è in ufficio e Home Assistant di casa è già esposto con DuckDNS: lì
  `casa_url` è l'indirizzo DuckDNS (`https://<nome>.duckdns.org:8123`) con la verifica TLS
  normale, senza `casa_tls_nome`. In casa resta l'IP del Raspberry con `casa_tls_nome`.
- **PC a voce**: solo Windows; sulla DGX è spento nell'esempio
  `setup/linux/calliope.locale.esempio.yaml` (copiato in `~/calliope/calliope.locale.yaml`
  alla prima installazione).
- Da copiare dal portatile (non si scaricano): `wakeword/modelli/calliope.onnx`,
  `speakers.json`, `memoria.db`; voci, CAM++ e biblioteca anche dal catalogo.

## Aggiornare con un lavoro dell'agente in corso (06/10)

Il 06/10 alle 17:07 un `calliope aggiorna` ha ucciso in silenzio il lavoro «gioco memory»
partito alle 16:56. Ora `aggiorna`, `riavvia` e `torna` (solo libreria standard, in
`setup/linux/gestore.py`), prima di fermare il servizio, leggono lo stato dei lavori che
Calliope tiene in `~/calliope/lavori/in_corso.json` (calliope/agenti/ripresa.py; vale solo se il
processo che l'ha scritto è vivo, e solo con `agenti_sandbox` predefinito). Con lavori in coda o
in corso li elencano («L2 «gioco memory…» di Mario, in corso da 11 minuti») e:

```bash
calliope aggiorna                       # da terminale: «Li interrompo e aggiorno lo stesso? [s/N]»
calliope aggiorna --attendi-lavori      # aspetta che finiscano (al più 30 minuti, controllo ogni 10 s)
calliope aggiorna --attendi-lavori 60   # al più 60 minuti; oltre, non cambia niente (uscita 75)
calliope aggiorna --forza               # li interrompe: dopo il riavvio Calliope propone di rifarli
calliope riavvia --attendi-lavori       # lo stesso per riavvia e torna
```

Senza terminale (lo script via ssh) e senza opzioni non procede: uscita **75** («riprova più
tardi») e dice quale opzione usare. Per gli aggiornamenti non interattivi: `--attendi-lavori`
(con `--forza` se un aggiornamento non può aspettare). Un lavoro che aspetta una risposta non
blocca: sopravvive al riavvio. Con `aggiorna` il controllo viene dopo la preparazione e la
verifica della versione nuova (che resta pronta per la volta dopo), prima della copia dei dati.
Le opzioni ci sono dal primo aggiornamento con questa versione: il gestore si aggiorna solo
dopo un aggiornamento riuscito, quindi la prima volta `calliope aggiorna` è ancora quello
vecchio. Prova: `prova_gestore.py`, sezione 11.

## Prova end-to-end su un'istanza di prova (06/10)

`python -m prove.e2e.lancia` dal portatile (o `calliope prova-e2e` sulla DGX, senza la voce
vera) avvia una **seconda Calliope** dalla versione in uso con dati in `~/calliope-e2e/` e porte
sue (18770/18771), gli stessi Ollama (stesso `num_ctx` e `keep_alive`: niente ricariche), Whisper,
vLLM e SearXNG, HA e PC finti, due satelliti veri con microfono e casse finti; parla solo se la
Calliope vera tace da 180 s e alla fine lascia solo `~/calliope-e2e/risultati/`. Passi e cosa
prova: [`prove/manuali/e2e-dgx.md`](../../prove/manuali/e2e-dgx.md).

## Problemi noti

*Dalla divisione di CLAUDE.md (note fino al 06/10); dal 09/10 una sola sezione per area.*

  - **Impacchettamento per la DGX Linux** (02/10, [`docs/ricerche/2026-10-02-impacchettamento-dgx-linux.md`](../ricerche/2026-10-02-impacchettamento-dgx-linux.md)):
    `pyproject.toml` + `uv.lock`, gestore `calliope` (installa, aggiorna con verifica e
    ritorno automatico, torna), dati in `~/calliope` fuori dal codice, VAD senza torch,
    Whisper su un server con ripiego su CPU, voce su Ollama o vLLM. Provato a secco su
    Windows (`prova_linux.py`, `prova_gestore.py`): **la DGX vera non è stata toccata**. *[Storico (02/10): dalla sera del 02/10 Calliope gira sulla DGX come servizio; vedi «Setup (DGX Linux)» qui sopra.]*

## Misure per l'arbitro della memoria (14/10 sera, ramo `arbitro-memoria`)

Progetto in [`ricerche/2026-10-14-arbitro-memoria.md`](../ricerche/2026-10-14-arbitro-memoria.md),
conto in sola lettura con `calliope stato --memoria` ([capacita-installazioni](capacita-installazioni.md)).
Lo script `prove/manuali/misura_memoria_dgx.py` **non è ancora stato lanciato**: va sulla DGX, nella
cartella dei dati, con il servizio acceso e Calliope inattiva (controlla da sé il journal come il
deploy: nessun turno da 10 minuti, nessun lavoro dell'agente; si ferma se un turno arriva a metà).
Stampa solo numeri.

```bash
cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
P="$V/.venv/bin/python $V/prove/manuali/misura_memoria_dgx.py"
$P stato                                  # memoria adesso, /api/ps, vLLM, RSS
$P ollama --json ~/misura-ollama.json     # embedding: freddo, caldo, memoria vera contro /api/ps
$P ollama --modelli gemma4:e4b-it-qat,llama-guard3:8b --anche-tempo-reale   # con conferma
$P whisper                                # secondo Whisper suo sulla porta 8091 (large-v3 se c'è)
$P voce --durante whisper                 # prima frase e STT con un caricamento in parallelo
$P voce --durante embedding
# solo dopo il container dell'agente con --enable-sleep-mode (passo 4, oggi assente: esce con 77)
$P vllm-sonno --livello 1 --conferma calliope-vllm
$P vllm-sonno --livello 2 --conferma calliope-vllm
```

I modelli di Ollama tornano com'erano con lo stesso `num_ctx` (letto da `/api/ps`) e `keep_alive`;
il whisper-server della misura è suo (porta 8091), mai `calliope-whisper`. Il sonno di vLLM tocca il
container `calliope-vllm`: parte solo con `--conferma calliope-vllm` e un «sì» da tastiera, senza
richieste in corso (/metrics), senza pausa, senza lavori; la sveglia è garantita su errore, Ctrl+C e
SIGTERM, e se non riesce lo script stampa i comandi a mano (`/wake_up`, `reload_weights`, poi
`vllm.sh agente rifai`). Il primo turno vero dopo `voce` può rileggere il prefisso una volta.

## SearXNG tenuto aggiornato (09/10, ramo `searxng-aggiornamento`)

`calliope motore searxng controlla | aggiorna | novita | storia` gira in Python
(`calliope.web.motore`, dal gestore come `esegui`, nella cartella dei dati: stesso stato
`motore/searxng.json` e stesso blocco di Calliope); le altre azioni restano dello script
(`avvia`, `ferma`, `rimuovi`, `log`, `stato`, `prova`, `diagnosi` e le nuove `immagine`, `candidata`,
`togli-candidata`, `usa`, `dimentica`, `pausa <motori…>`, `pulisci-immagini`). Calliope chiama lo script con bash e docker (l'utente
è nel gruppo `docker`): la copia di prova `calliope-searxng-candidata` su 127.0.0.1:10004, il
container vero rifatto con `usa`. L'immagine scelta sta in `~/calliope-motore/searxng/immagine`
e vince su quella fissata nello script finché non è più vecchia. Niente sudo, nessun altro
container toccato. Procedura della prima prova vera e dettagli in [biblioteca](biblioteca.md).
