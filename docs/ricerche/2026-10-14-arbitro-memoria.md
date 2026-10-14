# Un arbitro unico delle attività e della memoria sulla DGX (14/10/2026)

*Richiesta di Dario del 14/10 sera. Questo documento è il **passo 1**: progetto e misure, senza
cambiare il comportamento. Il codice del passo è `calliope/arbitro_memoria.py` (conto e classi in
sola lettura, `calliope stato --memoria`) e lo script di misura
`prove/manuali/misura_memoria_dgx.py` (da lanciare sulla DGX). Sulla DGX non si è toccato niente:
i numeri «[D]» sono di Dario (14/10), quelli «[M]» misure nostre di prima, «[S]» stime da
verificare con lo script, «[V]» documentazione verificata.*

## 0. In breve

- **Il problema.** Sulla DGX la memoria unificata è una sola (119 GiB): oggi ne sono usati 97 e ne
  restano ~21 [D]. La voce, Whisper, il guardiano, l'agente, gli embedding, la stanza e domani le
  immagini e un secondo Whisper se la contendono, e ognuno oggi decide da sé quando partire e
  quanto tenere. Non c'è un posto che sappia quanta memoria c'è, chi la tiene e chi può cederla:
  FLUX da 13 GB oggi ci starebbe a malapena, e un picco sbagliato sulla Spark fa cadere vLLM o
  Ollama (OOM, ricerca del 06/10 sulle immagini).
- **La scelta di Dario.** I modelli di **sfondo** si possono scaricare e ricaricare, anche a costo di
  un po' di lentezza nei lavori di sfondo; il **turno di voce non paga mai**.
- **La proposta.** Un arbitro unico con quattro classi (tempo reale, vicino, sfondo, a richiesta), un
  conto della memoria fatto sulla memoria vera (MemAvailable, non `/api/ps`), una sola definizione di
  «voce ferma», una coda di caricamenti con precedenza e tetti, e un modo noto e misurato di scaricare
  e ricaricare ogni modello (Ollama `keep_alive`, unità systemd utente, **modalità sonno di vLLM**).
- **I passi.** 1 (questo) conto e misure; 2 arbitro **in ombra** che registra cosa avrebbe messo in coda
  o scaricato; 3 i primi modelli a richiesta (secondo Whisper, poi FLUX); 4 il sonno di vLLM, solo
  dopo le misure.

## 1. Cosa c'è oggi: pezzi separati

| Pezzo | Dove | Cosa fa | Cosa non sa |
|---|---|---|---|
| Precedenza di Whisper | `stanza/coda.py` (`Precedenza`: TURNO, RECUPERO, STANZA, LENTA), `corsie.STTCondiviso` | una trascrizione alla volta, il turno passa davanti | niente della memoria; vale solo per Whisper |
| «DGX libera» della stanza | `stanza/guardia.py` (`libera`, `stanza_guardia_quiete_s`), `stanza/lenta.py` (`libera`, `stanza_lenta_libera_s`) | il guardiano a posteriori e la corsia lenta lavorano solo a voce ferma da qualche secondo | due definizioni di «ferma», scritte due volte, con funzioni `occupato` diverse |
| Embedding a Calliope inattiva | `conversazioni.py` (`inattiva`, 10 minuti), `ollama_carico.py` (`puo_caricare`, `residente`) | vettori a lotti con `keep_alive: 0`; la domanda di una ricerca solo se c'è posto | una terza definizione di «ferma»; conta i posti di Ollama, non la memoria |
| Arbitro dell'agente | `agenti/arbitro.py` (`Arbitro`, `PausaServer`, `ClienteCedevole`) | la voce sveglia → stream chiusi o vLLM in pausa (`/pause?mode=keep`, ~22 ms), ripresa garantita | la pausa ferma il **calcolo**, non libera memoria |
| Piano dei modelli | `piano.py`, `calliope stato --piano` | cosa sta su questa macchina, con la riserva e i liberi «di adesso» | è un piano statico: non dice chi cedere quando serve posto |
| Immagini | ricerca del 06/10 (FLUX.2 [klein] 4B, ~13 GB, a richiesta con `immagini_keep_alive`) | progetto, non codice | aspetta il piano della memoria (S6 della roadmap, decisione 0028 § 2) |
| Servizi di Linux | `setup/linux/gestore.py`, `calliope-whisper.service`, `motore/vllm.sh` | avvio, aggiornamento, lavori vivi prima di fermare | nessuno li accende o spegne a richiesta |

Quello che manca davvero: **un conto unico** (chi tiene cosa, adesso, sulla memoria vera), **una
definizione unica di voce ferma**, **un solo posto che carica e scarica** (oggi Ollama scaccia da sé
con `OLLAMA_MAX_LOADED_MODELS`, gli embedding si caricano da soli, la corsia lenta userebbe un servizio
sempre acceso), e i **tempi** di ogni caricamento, che non sono mai stati misurati.

## 2. Le classi

| Classe | Chi (DGX di oggi) | Regola |
|---|---|---|
| **Tempo reale** | voce (gemma4 26B su Ollama, «Forever»), Whisper dei turni (whisper-server turbo), guardiano (llama-guard3 8B) e rilevatore (gemma4 e4b) per minori e ospiti, nel processo Piper, CAM++, VAD, wake word | **mai scaricato**; la memoria è sua per prima. Un caricamento non comincia mentre serve (voce occupata) |
| **Vicino** | nessun modello a sé oggi. Lo **scrittore dell'ufficio** usa l'agente da un turno (`ClienteCedevole(dalla_voce=True)`); SearXNG (CPU, piccolo) | un turno lo può aspettare qualche secondo: si scarica per ultimo, e prima di un uso dalla voce va svegliato con la frase d'attesa |
| **Sfondo** | agente (vLLM, Qwen3.6-35B NVFP4), embedding delle conversazioni, guardiano a posteriori e corsia lenta della stanza (usano modelli già caricati: costano calcolo, non memoria) | lavora a voce ferma; si può scaricare quando serve posto, prima il meno usato |
| **A richiesta** | immagini (FLUX, non installato), secondo Whisper della corsia lenta (in arrivo: qui lo si tratta come servizio a richiesta futuro) | si carica quando serve, dentro il budget, e si scarica dopo un `keep_alive`; se non ci sta neanche scaricando lo sfondo, non si carica e si dice |

Due note. Il guardiano e il rilevatore restano tempo reale anche se servono solo ai turni di minori
e ospiti: in una casa con minori registrati possono servire a qualunque turno, e ricaricarli costa
proprio al turno del minore. Il guardiano a posteriori usa il rilevatore **già caricato** con le
stesse opzioni (stanza/lenta.py, riassunti): è sfondo per il calcolo, tempo reale per la memoria.

## 3. Il conto della memoria

### 3.1 Oggi sulla DGX [D, 14/10]

| Chi | Classe | GiB | Come si legge |
|---|---|---|---|
| vLLM agente (Qwen3.6-35B NVFP4, `gpu_memory_utilization` 0,4) | sfondo | 47,8 | prenotata all'avvio: 0,4 × 119,5 |
| gemma4 26B (voce) | tempo reale | 15 | `/api/ps` (sottostima) |
| llama-guard3 8B | tempo reale | 5,3 | `/api/ps` |
| gemma4 e4b (rilevatore) | tempo reale | 3,1 | `/api/ps` |
| qwen3-embedding 0,6B (CPU) | sfondo | 0,6 quando c'è | `/api/ps`; sulla CPU, ma la memoria è la stessa |
| whisper-server turbo | tempo reale | 2,1 | [M 05–07/10] |
| Piper sulla GPU, CAM++, VAD, processo | tempo reale | ~1,5 + RSS | [M 07/10] per Piper; il processo da misurare |
| **Calliope** | | **~75–78** | |
| sistema, cache dei file non recuperabile, altri container (open-webui, database, CRM…) | — | ~19–22 | il resto: 97 usati − Calliope |
| **Disponibili** | | **~21** | MemAvailable |
| FLUX.2 [klein] 4B, a richiesta | a richiesta | 13 | [V] scheda, ricerca del 06/10 |
| secondo Whisper (large-v3) | a richiesta | ~3,6 | [S] pesi ggml 3,1 GB + calcolo |

Un FLUX da 13 GiB con 21 liberi **ci sta, ma senza margine** (la ricerca del 06/10: «un picco di
13–22 GB non è sicuro» con 14 disponibili). FLUX e il secondo Whisper insieme no.

### 3.2 Come si conta

- **La memoria libera vera** è `MemAvailable` (`/proc/meminfo`): sul GB10 `nvidia-smi` dice `[N/A]` per
  la memoria (lo legge già `macchina.inventario`). È l'unico numero che vede tutto: Ollama, vLLM, i
  processi, la cache dei file recuperabile.
- **`/api/ps` sottostima** (trappola di CLAUDE.md: e4b 4,7 GB con `nvidia-smi` contro ~3,3 di `/api/ps`
  sul portatile). Finché non c'è la misura, il conto aggiunge il buffer di calcolo del piano (0,35 GB a
  modello, `BUFFER_OLLAMA_GB`). Lo script misura il fattore vero: delta di MemAvailable al
  caricamento contro `/api/ps` (`vero_su_ps`).
- **vLLM** prenota `gpu_memory_utilization × memoria` all'avvio, pesi e cache insieme (`/metrics`,
  `vllm:cache_config_info`).
- **Il processo di Calliope**: RSS del servizio (`systemctl --user show calliope -p MainPID`,
  `/proc/PID/status`); la memoria CUDA (Piper sulla GPU) non è nell'RSS e si aggiunge dal catalogo.
- **Gli altri**: tutto il resto (usata − Calliope). Se crescono, il budget di Calliope si restringe:
  l'arbitro lo vede adesso, il piano no.
- **Il margine** da non toccare mai caricando un modello a richiesta: **8 GB** sulla memoria unificata
  (`MARGINE_LIBERO_GB`) [D]: il sistema, i picchi di Calliope (Whisper che alloca a ogni frase, Piper),
  la cache dei file, i container vicini; il playbook NVIDIA della Spark avverte di OOM anche sotto la
  capacità. 0,5 GB su una GPU dedicata (come `contesto_margine_gb`). Da ritarare con le misure.

`calliope stato --memoria` fa questo conto adesso e mostra, per ogni modello a richiesta non caricato,
**cosa farebbe l'arbitro** (ci sta; oppure chi scaricherebbe e quanto mancherebbe ancora). Con i
numeri di oggi: immagini e secondo Whisper ci stanno ciascuno (21 − 8 = 13); con 10 GB liberi per le
immagini l'arbitro metterebbe a dormire l'agente (dal passo 4) e niente altro.

## 4. Le politiche

### 4.1 Mai il tempo reale

Nessuna richiesta, di nessuna classe, scarica un modello del tempo reale. Se un modello a richiesta
non ci sta neanche scaricando tutto lo sfondo, **non si carica** e Calliope lo dice («adesso non ho
memoria per le immagini: riprova tra poco»), invece di rischiare l'OOM. I modelli che non sono di
Calliope (un altro programma sullo stesso Ollama) si contano ma non si toccano mai.

### 4.2 Chi si scarica prima

Nell'ordine: **sfondo** (il meno usato per primo; senza un uso noto, prima di tutti), poi gli altri
**a richiesta** già caricati e fermi, poi i **vicini**. Ci si ferma appena basta. Chi si vuole caricare
non è mai candidato. Ogni candidato dichiara da quale passo dell'arbitro si può scaricare: l'agente su
vLLM solo dal passo 4 (sonno misurato), il resto dal passo 2–3. È `arbitro_memoria.scaricabili` e
`proposta` (provate a secco: `prove/prova_arbitro_memoria.py`).

### 4.3 La coda dei caricamenti: precedenza e tetti

Un solo posto carica e scarica (l'arbitro); gli altri chiedono. Le richieste vanno in una coda con la
stessa idea di `stanza/coda.Precedenza`: tempo reale (un ricaricamento dopo un guasto) > vicino > a
richiesta (una persona aspetta l'immagine) > sfondo. Tetti:

- **un caricamento alla volta** su tutta la macchina: due caricamenti insieme sommano i picchi e la
  banda di lettura dal disco;
- **memoria**: mai sotto il margine dopo il caricamento (conto fatto prima, con il `gb_pieno`
  misurato, e ricontrollato su MemAvailable a caricamento finito);
- **tempo**: ogni a richiesta ha il suo `keep_alive` (immagini ~10 minuti, come la ricerca del 06/10);
  scaduto, si scarica;
- **isteresi**: lo stesso modello non si scarica e ricarica più di N volte l'ora (N da misurare: se
  succede, il budget è sbagliato e lo si dice in `calliope stato --memoria`);
- **attesa massima**: una richiesta di sfondo che aspetta troppo si butta e si conta (come
  `stanza_guardia` con `CODA_MAX_S`).

### 4.4 Quando: una sola «voce ferma»

Un caricamento o uno scaricamento comincia solo a voce ferma da qualche secondo: nessuno che parla a
Calliope, nessuna risposta in corso, nessuna frase che aspetta Whisper, la coda della stanza vuota.
Oggi le stesse condizioni sono scritte in tre posti (`stanza/guardia.libera`, `stanza/lenta.libera`,
`conversazioni.inattiva`) più l'arbitro dell'agente (`voce_occupata`/`voce_libera`). Il passo 2 le
riunisce in una funzione dell'arbitro (`quiete(secondi)`) che gli altri chiamano; finché è in ombra
non cambia niente. Un caricamento già cominciato **non si interrompe** (Ollama e whisper-server non
lo permettono): per questo si comincia solo con la voce ferma, e un caricamento lungo (il livello 2 di
vLLM) solo se nessun turno è arrivato negli ultimi minuti.

### 4.5 Il vicino

Un uso dalla voce di un modello che dorme (lo scrittore dell'ufficio con vLLM a dormire) dice la frase
d'attesa e sveglia il modello con la precedenza del vicino; se la sveglia dura troppo (soglia dalle
misure), il lavoro passa al modello della voce o diventa un lavoro dell'agente. Per questo il sonno di
vLLM si decide solo dopo le misure (passo 4).

## 5. Come si scarica e si ricarica ogni modello

| Motore | Scaricare | Ricaricare | Note |
|---|---|---|---|
| **Ollama** (voce, guardiano, rilevatore, embedding) | `POST /api/generate {"model": M, "keep_alive": 0}` (per un modello di embedding `/api/embed` con un `input`), oppure `ollama stop M` | `POST /api/generate {"model": M, "keep_alive": K, "options": {"num_ctx": N}}` senza prompt; embedding con `/api/embed` | **lo stesso `num_ctx` e `keep_alive` di Calliope**: un `num_ctx` diverso fa ricaricare il modello al turno dopo (trappola). Lo script lo rilegge da `/api/ps` (`context_length`) e controlla il ripristino. Il guardiano usa `guardiano_num_ctx`/`guardiano_keep_alive`, il rilevatore uguale |
| **whisper.cpp** (turni) | — (tempo reale) | — | servizio `calliope-whisper`, sempre acceso |
| **whisper.cpp** (secondo, corsia lenta) | `systemctl --user stop` della sua unità | `systemctl --user start`; pronto quando `GET /` risponde | futuro: un'unità sua a richiesta (l'altro ramo la sta facendo come servizio acceso); lo script misura un whisper-server suo sulla porta 8091 |
| **vLLM** (agente) | **sonno**: `POST /sleep?level=1|2` | livello 1 `POST /wake_up`; livello 2 `POST /wake_up?tags=weights`, `POST /collective_rpc {"method":"reload_weights"}`, `POST /wake_up?tags=kv_cache` | vedi 5.1 |
| **FLUX** | `immagini_keep_alive` scaduto: il servizio libera i pesi | alla prima richiesta | progetto del 06/10: servizio `calliope-immagini` su 127.0.0.1, con `/stato` e il controllo della memoria **prima** di caricare |
| Piper, CAM++, VAD, wake word | mai (nel processo, tempo reale) | — | |

### 5.1 La modalità sonno di vLLM [V]

- **Versione**: sulla DGX `vllm/vllm-openai:v0.29.0` (`setup/linux/motore/vllm.sh`). La modalità sonno c'è
  dalla 0.7 ed è nella documentazione stabile (docs.vllm.ai, «Sleep Mode»), con il server: si accende
  con `--enable-sleep-mode` **all'avvio** e gli endpoint `/sleep`, `/wake_up`, `/is_sleeping`,
  `/collective_rpc` esistono solo con `VLLM_SERVER_DEV_MODE=1`. Supportata su CUDA e ROCm.
- **Oggi non è accesa**: `vllm.sh` non passa `--enable-sleep-mode`. La modalità sviluppo può esserci
  già (`PAUSA=1`, per la pausa dell'arbitro): l'esposizione degli endpoint senza chiave è la stessa
  (solo 127.0.0.1, rete Docker sua). Accenderla vuol dire **rifare il container** (`vllm.sh agente
  rifai` con un'opzione nuova, `SONNO=1`: passo 4, non ora perché `setup/linux/` lo sta toccando un
  altro ramo).
- **Livello 1**: i pesi vanno nella memoria «della CPU» e la cache KV si butta. **Sulla memoria
  unificata della Spark la memoria della CPU è la stessa**: si libera solo la cache, ~47,8 − ~24 (pesi
  NVFP4) ≈ **20–24 GiB** [S]; la sveglia ricopia i pesi (veloce). Rischio: lo spostamento dei pesi
  può chiedere memoria in più per un momento (lo script vuole almeno 10 GB liberi per provarlo).
- **Livello 2**: pesi e cache buttati, restano i buffer piccoli: si libera quasi tutto, **~45 GiB** [S].
  La sveglia rilegge i pesi dalla cache di Hugging Face (`reload_weights`): da misurare, stima
  10–60 s [S] secondo la cache dei file. È il livello che serve per far posto a FLUX.
- **Dopo la sveglia** la cache del prefisso è vuota: il primo passo dell'agente rilegge il suo prompt.
  Le richieste che arrivano mentre dorme non vanno mandate: l'arbitro dell'agente le fa aspettare
  (`attendi`) come oggi con la pausa.
- **Stabilità sulla Spark**: nessuna conferma trovata per il GB10 (né problemi noti, né prove): è il
  motivo del comando separato nello script. Da misurare anche: la velocità dell'agente con la modalità
  sonno accesa (l'allocatore cambia: banco codice 11/12 da rifare), la sveglia dopo ore, un ciclo
  dorme/sveglia ripetuto (perdite di memoria).

## 6. Rischi

- **La prima frase della voce.** Un caricamento in parallelo legge GB dal disco e li scrive in memoria
  con la stessa banda (273 GB/s) che la voce usa per generare: la prima frase può rallentare anche
  senza contesa di memoria. Si misura (`misura_memoria_dgx.py voce --durante embedding|whisper`); la
  regola è comunque «si comincia solo a voce ferma» (4.4).
- **Caricamenti concorrenti.** Ollama carica un modello alla volta per sé, ma Ollama, vLLM, whisper e FLUX
  sono server diversi: due picchi insieme. Un solo caricamento alla volta su tutta la macchina (4.3).
- **OOM sulla memoria unificata.** L'OOM killer del kernel sceglie il processo più grosso: vLLM o Ollama,
  cioè l'agente o **la voce**. Per questo il margine, il conto prima e il controllo dopo, e il rifiuto
  invece del tentativo.
- **Frammentazione e cache dei file.** Il playbook NVIDIA della Spark avverte di errori di memoria
  anche sotto la capacità e consiglia di svuotare la cache dei file (serve sudo: non lo facciamo). Lo
  script toglie dalla cache solo i file dei modelli che misura (`posix_fadvise(DONTNEED)`, senza sudo):
  è anche il modo di misurare un caricamento «a freddo».
- **`num_ctx` che ricarica il modello.** Ogni ricaricamento con le opzioni esatte di Calliope; lo script
  controlla che `context_length` torni uguale.
- **Ollama che scaccia da sé.** Con `OLLAMA_MAX_LOADED_MODELS=4` Ollama scaccia il meno usato quando ne
  arriva un quinto: l'arbitro deve essere l'unico a caricare su quell'Ollama (oggi lo sono quasi gli
  embedding, con `ollama_carico`).
- **`/api/ps` che sottostima** e il processo di Calliope non misurato: il conto si corregge con le
  misure (`vero_su_ps`, RSS).
- **La sveglia di vLLM che non riesce**: l'agente è giù finché non si rifà il container (~1 minuto con la
  cache di compilazione). Lo script garantisce la sveglia su errore, Ctrl+C e SIGTERM e stampa i comandi
  a mano; l'arbitro del passo 4 farà lo stesso all'avvio (come `PausaServer` riprende un vLLM rimasto in
  pausa).
- **Gli altri container crescono**: il budget di Calliope si restringe senza che nessuno lo dica. Il
  conto «di adesso» lo mostra; il passo 2 lo registra nel tempo.

## 7. Passi

1. **Conto e misure** (questo, 14/10): classi, conto in sola lettura (`calliope stato --memoria`), script di
   misura. Nessun comportamento cambiato.
2. **Arbitro in ombra**: un thread che a ogni richiesta di carico (embedding, corsia lenta, guardiano a
   posteriori, lavori dell'agente) e a ogni minuto scrive nel registro cosa **avrebbe** messo in coda,
   quando l'avrebbe fatto partire e chi avrebbe scaricato; la funzione unica `quiete()`; in
   `calliope stato --memoria --storia` la memoria libera minima del giorno e quante volte un a richiesta
   non sarebbe stato possibile. Criterio per andare avanti: una settimana di registro senza «avrebbe
   scaricato il tempo reale» (deve essere 0) e la memoria minima vera sopra il margine.
3. **I primi modelli a richiesta**: il secondo Whisper come unità systemd utente avviata e fermata
   dall'arbitro (si comincia da quello: piccolo, ~3,6 GB, ricaricabile in secondi), poi FLUX (S6) con il
   suo `immagini_keep_alive`. Gli embedding passano dall'arbitro invece che da `ollama_carico`.
4. **Il sonno di vLLM**, solo dopo le misure del livello 1 e 2 sulla DGX: `SONNO=1` in `vllm.sh`
   (container rifatto), l'arbitro mette a dormire l'agente quando serve posto a un a richiesta e nessun
   lavoro è in corso, lo sveglia prima del lavoro dopo; lo scrittore dell'ufficio come vicino (4.5).

## 8. Le misure da fare sulla DGX

Con il servizio acceso e Calliope inattiva (lo script controlla il journal come il deploy: nessun turno
da 10 minuti, nessun lavoro dell'agente; si ferma se un turno arriva a metà):

| Comando | Cosa dice | Durata |
|---|---|---|
| `misura_memoria_dgx.py stato` | la memoria adesso, `/api/ps`, vLLM, RSS, se `nvidia-smi` dà la memoria per processo | secondi |
| `misura_memoria_dgx.py ollama` | embedding: scaricamento, carico a freddo e a caldo, memoria vera contro `/api/ps` | ~1 min |
| `misura_memoria_dgx.py ollama --modelli gemma4:e4b-it-qat,llama-guard3:8b --anche-tempo-reale` | gli stessi numeri per rilevatore e guardiano (con conferma; tornano com'erano) | ~2–3 min |
| `misura_memoria_dgx.py whisper` | secondo Whisper (large-v3 se c'è): pronto a freddo e a caldo, prima trascrizione, memoria presa e resa | ~1–2 min |
| `misura_memoria_dgx.py voce --durante whisper` e `--durante embedding` | prima parola e prima frase della voce e STT, a macchina ferma e con il caricamento in parallelo | ~2 min ciascuno |
| `misura_memoria_dgx.py vllm-sonno --livello 1 --conferma calliope-vllm` (poi `--livello 2`) | memoria liberata, tempi di sonno e sveglia, prima richiesta dopo; **solo dopo** il container con la modalità sonno (passo 4) | ~1–3 min |

## 9. Nella taglia ridotta da 8 GB

Lo stesso codice: GPU dedicata, margine 0,5 GB, la voce (e4b) e Whisper riempiono la GPU, il guardiano
è sulla CPU o piccolo (piano dei modelli). Nessun a richiesta ci sta: `calliope stato --memoria` lo dice
(«immagini: mancano 6,8 GB»), e l'arbitro in ombra registrerà solo rifiuti. Non c'è niente di sfondo da
scaricare (l'agente non c'è): le classi restano, le politiche non hanno niente da fare.

## Fonti

- vLLM, «Sleep Mode» (documentazione stabile, letta il 14/10): <https://docs.vllm.ai/en/stable/features/sleep_mode/>
- vLLM sulla DGX Spark (blog vLLM, 01/06/2026): <https://vllm.ai/blog/2026-06-01-vllm-dgx-spark>
- Forum NVIDIA, un LLM grande e ComfyUI insieme sulla Spark: <https://forums.developer.nvidia.com/t/running-a-large-llm-on-dgx-spark-cluster-while-keeping-comfyui-usable/376650>
- Ricerche nostre: [`2026-10-06-generazione-immagini.md`](2026-10-06-generazione-immagini.md) (§ 2.3, § 3.1),
  [`2026-10-07-taratura-macchina.md`](2026-10-07-taratura-macchina.md) (§ 4.3, § 7.1), decisione
  [0028](../decisioni/0028-decisioni-roadmap-12-10.md) § 2.
