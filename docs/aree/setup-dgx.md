# Setup sulla DGX Linux

*Installazione e aggiornamento sulla DGX Spark (Ubuntu 24.04 aarch64): uv, gestore `calliope`, systemd, motori. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 09/10.** Calliope gira sulla DGX dal 02/10 come servizio utente systemd, aggiornata con `calliope aggiorna` (ritorno automatico; dal 06/10 non interrompe in silenzio i lavori dell'agente). Voce su Ollama scelta con `llm_profilo`, Whisper con whisper.cpp, agente qwen3.6 su vLLM, SearXNG e sandbox Docker accanto. Dal 07/10 l'extra `voce-gpu` porta Piper sulla GPU (onnxruntime-gpu su aarch64). La prova end-to-end su un'istanza di prova c'è dal 06/10.

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Installazione e aggiornamento (Linux, DGX) | uv (lock universale), git, systemd utente; gestore in sola libreria standard | `pyproject.toml`, `uv.lock`; `setup/linux/` → `gestore.py` (comando `calliope`: `installa`, `aggiorna`, `torna`…), `installa.sh`, `calliope.service`, `calliope.locale.esempio.yaml`, `motore/vllm.sh` (voce e agente su vLLM; Whisper su vLLM provato e scartato il 02/10), `motore/whisper.sh` e `motore/calliope-whisper.service` (whisper.cpp), `motore/sandbox.sh`, `motore/searxng.sh`, `motore/gemma4_template.py` |
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
- **pyproject.toml**: dipendenze di base + extra `documenti`, `casa`, `schermi`, `pc` (solo
  Windows), `gpu` (DLL CUDA 12, solo Windows), `voce-gpu` (CUDA 13 e cuDNN per Piper sulla
  GPU, solo Linux aarch64, dal 07/10), `prove`, `tutto`; `calliope =
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

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Impacchettamento per la DGX Linux** (02/10, [`docs/ricerche/2026-10-02-impacchettamento-dgx-linux.md`](../ricerche/2026-10-02-impacchettamento-dgx-linux.md)):
    `pyproject.toml` + `uv.lock`, gestore `calliope` (installa, aggiorna con verifica e
    ritorno automatico, torna), dati in `~/calliope` fuori dal codice, VAD senza torch,
    Whisper su un server con ripiego su CPU, voce su Ollama o vLLM. Provato a secco su
    Windows (`prova_linux.py`, `prova_gestore.py`): **la DGX vera non è stata toccata**. *[Storico (02/10): dalla sera del 02/10 Calliope gira sulla DGX come servizio; vedi «Setup (DGX Linux)» qui sopra.]*
