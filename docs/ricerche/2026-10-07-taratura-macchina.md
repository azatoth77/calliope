# Calliope si tara sulla macchina: piano dei modelli, del contesto e delle funzioni (07/10/2026)

*Ricerca del 7 ottobre 2026, niente codice. Richiesta di Dario: «Pensa a un PC con una GPU da
32 GB di VRAM: è una signora macchina domestica, ma non è niente rispetto a una DGX Spark. Mi
piacerebbe che Calliope si tarasse e suggerisse quali modelli usare in base alle performance
dichiarate dai modelli (che resterebbero da provare) e/o alle feature da abilitare. Anche la
dimensione del contesto e il numero di modelli da usare.» La logica «misura all'avvio,
adattamento con l'uso, stato salvato» è appena stata scritta per la sintesi della voce (ramo
`primo-pezzo`, `calliope/taratura_voce.py`, in corso): qui la si generalizza a tutta la
macchina.*

*Fonti: il codice di `main` al commit 8413235, i documenti d'area e le ricerche citate, due
letture in sola lettura della DGX (`/api/ps`, `/api/show`, `/proc/meminfo`, `contesto.json`,
`calliope stato --turni`, `/metrics` di vLLM) e del portatile (`nvidia-smi`, `/api/show` dei
modelli già installati), la ricerca sul web del 07/10 per i dati dichiarati (fonte e data
accanto a ogni numero). Nessun modello scaricato, nessun banco lanciato.*

*Legenda: **[M]** misurato da noi (portatile o DGX; tra parentesi dove e quando) · **[V]**
verificato su fonte primaria (scheda del modello, config.json su Hugging Face, libreria
Ollama, scheda tecnica del produttore) · **[A]** dichiarato dal produttore, non verificato da
altri · **[Agg]** aggregatori, blog, forum · **[D]** deduzione o stima mia, da misurare.*

## 0. In breve

- **Si può fare, ed è in buona parte già lì.** `contesto.py` è già una taratura (misura la
  lettura, legge la forma della cache, sceglie la finestra, la salva in `contesto.json`, un
  numero scritto vince), come il ramo `primo-pezzo` per Piper. Mancano un **inventario** con i
  numeri che contano (memoria veloce per pool, banda, motori), un **catalogo dei modelli** con
  dati dichiarati e misurati, le **regole** del piano e la **velocità di generazione** nel
  registro dei turni (oggi non c'è: si vede solo la lettura).
- **Due numeri decidono quasi tutto**: la memoria veloce (cosa ci sta insieme) e la banda
  (quanti token al secondo: `η × banda / byte letti a token`, η 0,45–0,68 nelle nostre misure,
  0,65–0,85 con llama.cpp nei banchi pubblicati). Il terzo, la lettura del prompt, dipende dal
  calcolo e va **misurato**: il prefisso di Calliope è di 6–12k token, e sulla CPU basta da
  solo a escludere la macchina come server.
- **Una 5090 (32 GB, 1792 GB/s) e la DGX (128 GB, 273 GB/s) sono macchine opposte.** La 5090
  fa una voce più veloce della DGX con lo stesso modello (26B-A4B), più guardiano e rilevatore,
  ma non tiene un agente separato: i lavori lunghi li farebbe la voce stessa su un secondo
  posto. La DGX ha poca banda e tanta memoria: voce, guardiano, rilevatore, agente su vLLM e
  immagini a richiesta. Il portatile da 8 GB tiene solo voce 4B e Whisper.
- **Il piano segue un ordine fisso**: riserva, voce (sotto la soglia della prima frase), Whisper,
  guardiano (mai spento in silenzio), rilevatore, embedding, contesto, agente, funzioni a
  richiesta; ogni ruolo ha una scala di ripieghi. Solo i modelli **provati col nostro banco**
  (oggi gemma4 e2b, e4b, 26B-A4B) si scelgono da soli; gli altri sono «da provare».
- **Verifica e adattamento** come per la voce: dichiarato → prova breve dopo l'accettazione
  (memoria vera con `size_vram` di `/api/ps`, lettura, generazione, prima frase, Whisper su un
  file sintetizzato) → uso (registro dei turni). Si regolano da sole solo cose reversibili e mai
  la sicurezza; modelli, download, licenze e variabili di Ollama con proposta e «sì». Stato in
  `taratura.json`; il piano decide solo i campi che valgono «auto».
- **Cosa raccomando**: fasi 0–2 (~5–6 giorni): generazione nel registro, inventario e catalogo,
  `calliope stato --piano` in sola lettura, provato con macchine finte e con la DGX vera, che il
  piano deve ritrovare uguale a com'è oggi. Il resto (prova, applicazione, adattamento, voce,
  installatori) dopo, ~7–9 giorni.

### Decisioni per Dario

1. **Il piano applica o propone?** Proposta: il piano accettato si applica ai soli campi «auto»
   (§5.3); prima dell'accettazione solo `calliope stato --piano`. Va bene che i predefiniti di
   `llm_profilo`, Whisper, guardiano e agente diventino «auto» (senza piano accettato = i valori
   di oggi)?
2. **Quali modelli entrano nel catalogo come scelte automatiche** oltre ai tre Gemma 4 provati?
   Proposta: nessuno finché non passa il banco su una macchina nostra; `gemma4:12b` e
   `qwen3.5:9b` i primi da provare per la classe 12–16 GB.
3. **Guardiano senza posto** (8 GB): 1B sulla CPU con avviso, oppure guardiano 1B sulla GPU
   togliendo Whisper alla GPU? Proposta: 1B sulla CPU (Whisper sulla CPU costa ~5 s a ogni
   frase di tutti, il guardiano solo ai minori), da misurare (§7.2, punto 4).
4. **Agente sulla 5090**: la voce stessa su un secondo posto (proposta), oppure un agente con
   gli esperti nella RAM di sistema, lento e solo di notte?
5. **Calliope ridotta per la sola CPU**, o «questa macchina va bene come satellite»? Proposta:
   la seconda, finché non si misura una Calliope con pochi tool sulla CPU.
6. **Variabili di Ollama**: il piano le propone come comando (sudo) e non le tocca, come oggi
   `ollama_carico`. Confermi?

---

## 1. Cosa c'è già e cosa manca

Calliope sa già tarare **un** numero dal setup (la finestra di contesto) e, nel ramo in corso,
la sintesi della voce. Il resto delle scelte (quale modello, Whisper dove, guardiano sì o no,
quanti modelli insieme) è scritto a mano in `calliope.locale.yaml` da chi conosce la macchina.

### 1.1 Mappa

| Pezzo | Dove | Cosa fa oggi | Cosa manca per un piano |
|---|---|---|---|
| **Inventario** | `calliope/macchina.py` → `dati()` (cache per processo) | Modello del computer, processore, core, RAM totale, nomi delle GPU, sistema, architettura. Windows: registro e `GlobalMemoryStatusEx`; la VRAM dal registro (`HardwareInformation.qwMemorySize`). Linux: `/proc`, `/sys`, `/proc/driver/nvidia/gpus/*/information` (solo il **nome** della GPU). Usato solo per la frase «su che hardware giri?» (`descrivi`). | **VRAM su Linux** (nvidia-smi, che sul GB10 dice `[N/A]`); **memoria unificata** sì/no (GB10, RTX Spark, Strix Halo, Apple); **banda di memoria** (non si legge da nessuna parte: va da una tabella per nome di GPU/SoC, o misurata); memoria **libera** per pool; motori disponibili (Ollama, vLLM, whisper.cpp, CUDA per CTranslate2); GPU non NVIDIA (AMD, Apple). |
| **Finestra di contesto** | `calliope/contesto.py` → `prepara`, `calcola`, `scegli`, `kv_ollama`, `memoria_libera`; `contesto.json` | Minimo di tre limiti: **modello** (`context_length` da `/api/show`, `max_model_len` di vLLM), **memoria** (memoria libera adesso − `contesto_margine_gb`, divisa per il costo di un token della cache calcolato dalla forma del modello, anche gli strati «sliding»; vLLM: `kv_cache_size_tokens` da `/metrics`), **tempo** (velocità di lettura misurata con `Brain.measure_prefill`, rimisurata ogni 7 giorni o al cambio di modello). Arrotondata a 4096, mai sotto 8192, pavimento `contesto_ripiego`. Un numero in `llm_num_ctx` vince. Stato in `contesto.json` (chiave `backend|url|modello`). È già il modello giusto: **misura, decide, salva, una scritta vince**. | Considera la memoria libera **adesso**, non quella dei modelli che il piano vuole residenti ma non sono ancora caricati (guardiano, rilevatore, embedding caricati dopo: possono non starci più). Non misura la **velocità di generazione** (token/s), che decide la prima frase. Prudente su `OLLAMA_KV_CACHE_TYPE` (sempre 2 byte). `kv_ollama` non riconosce lo schema «sliding» di Gemma 3 (Ollama non espone `sliding_window_pattern` per `gemma3`): sovrastima la cache di 6 volte (vedi §3.4). |
| **Carico di Ollama** | `calliope/ollama_carico.py` → `residenti`, `limite`, `usati`, `avviso`, `puo_caricare` | Conta i modelli che Calliope usa su ogni Ollama (voce, guardiano, rilevatore, embedding) contro `OLLAMA_MAX_LOADED_MODELS` (configurazione, ambiente, servizio systemd, o 3 «assunto») e avvisa; gli embedding aspettano Calliope inattiva. | Conta i **modelli**, non la **memoria**: non sa se i quattro ci stanno insieme, né quale togliere. Non conosce `OLLAMA_NUM_PARALLEL` (ogni posto in più moltiplica la cache) né `size_vram < size` di `/api/ps`, cioè **un modello finito in parte sulla CPU** (il segno più chiaro di un piano sbagliato). |
| **Registro delle capacità** | `calliope/capacita.py` → `DEFINIZIONI` (18), `check_*`, `aggiungibili`, `testo_prompt` | Per ogni capacità: attiva, da configurare, mancante, guasta, con motivo e prossimo passo, anche a voce (`calliope_stato`). `check_llm` dice la dimensione del modello e l'avviso di Ollama pieno. `aggiungibili` dice cosa del catalogo non è installato (biblioteca, voci). | Nessuna nozione di **sostenibile su questa macchina**: «agenti» è «da configurare» anche dove non ci starebbero mai. `aggiungibili` non propone modelli. |
| **Catalogo delle installazioni** | `calliope/installa/catalogo.py`, `servizio.py` | Solo cose con origine fissa e checksum: biblioteca, voci, CAM++, `whisper_riserva`, file del telefono e **`modello_llm`: solo il modello già scritto in `llm_model`**, con `/api/pull` dell'Ollama locale. Proposta e «sì» in due turni, solo chi amministra. | Nessun modello **alternativo** (voce più grande o più piccola, guardiano, embedding, agente): oggi guardiano e embedding si scaricano a mano con `ollama pull`. Nessun dato dichiarato (memoria, velocità attesa, licenza) accanto alle azioni. |
| **Profili del modello** | `config.PROFILI_LLM`, `llm_profilo` | Una riga sceglie backend, indirizzo, modello, thinking e reti (quattro profili: e4b e 26B su Ollama, 26B e qwen3.6 su vLLM). | Nessun dato sul **costo** del profilo (memoria, token/s attesi) né sulla sua qualità misurata (banco), e nessun «auto». |
| **Latenza come metrica** | `calliope/latenza.py`, `turnlog.py`; `calliope stato --turni` | Per giorno: prima frase (mediana, p75, p90), dalla fine del parlato, prima voce sentita, distacco testo-voce, STT, cause (correzione, guardiano, tool, riletture oltre 1 s, contesto, coda), la base senza tool; avviso oltre `latenza_avviso_s` (1,2 s, almeno 10 risposte). | Solo **diagnosi**, nessuna azione. Nel registro manca la **velocità di generazione** del turno: `OllamaBackend` passa a `_note_usage` `prompt_eval_count`, `eval_count` e `prompt_eval_duration`, non `eval_duration` (con vLLM servirebbe il tempo dal primo all'ultimo token). Manca il **modello** con cui è stato fatto il turno accanto alla latenza (c'è `profilo`, non i token/s). |
| **Sintesi della voce** (ramo `primo-pezzo`, in corso) | `calliope/taratura_voce.py`, `voce_taratura.json` | Tre fonti dalla più debole alla più forte: predefiniti prudenti, **taratura all'avvio** (una frase fissa; con `tts_thread: auto` prova 2, 4, 8 e i core fisici e tiene il più veloce, a parità meno thread), **l'uso** (mediana robusta delle ultime 200 sintesi, scarti oltre 4 volte, vale da 30 in su). Stato per voce e numero di thread, scrittura atomica, salvato al più ogni 30 s. Un numero scritto vince. | È lo schema da generalizzare (§5). |

### 1.2 Cosa si legge già oggi su questa DGX (07/10, sola lettura) [M]

- RAM 119,6 GiB, **MemAvailable 21,3 GiB** (con vLLM dell'agente, Ollama con tre modelli,
  whisper.cpp, SearXNG e altri container non di Calliope); nvidia-smi: `[N/A]`.
- Ollama 0.35.0 con `OLLAMA_MAX_LOADED_MODELS=4` e `OLLAMA_NUM_PARALLEL=2` nel servizio
  (il problema aperto del 06/10 risulta sistemato). Residenti: `gemma4:26b-a4b-it-qat` 16,6
  GB a 28 672 token (la voce, profilo `gemma4-26b-ollama`), `gemma4:e4b-it-qat` 3,1 GB e
  `llama-guard3:8b` 5,3 GB a 2 048 (rilevatore e guardiano).
- `contesto.json`: finestra 28 672 decisa dal **tempo** (modello 262 144, memoria 1 056 915
  token: sulla DGX la memoria non è mai il limite), lettura 3 164 token/s, **prefisso 12 425
  token**, 22 528 byte a token (20 KiB × 1,1).
- vLLM dell'agente (`nvidia/Qwen3.6-35B-A3B-NVFP4`): `max_model_len` 131 072,
  `gpu_memory_utilization` 0,4, cache **fp8 da 2 116 147 token**.
- Latenza (registro dei turni): 06/10 prima frase 1,02 s di mediana (p90 2,09; base 0,93),
  07/10 1,27 s (p90 2,42; base 1,15), prima voce sentita 1,78–1,85 s.

Sul portatile (07/10) [M]: RTX 5070 Laptop, 8 151 MiB di VRAM, **7 604 occupati** al momento
della lettura da altri lavori sulla stessa macchina. Un piano che leggesse la memoria libera in
quel momento sceglierebbe un modello da 0,5 GB: la memoria libera va letta **con Calliope
ferma**, o stimata dal totale meno ciò che il sistema tiene sempre (§5.1).

### 1.3 In sintesi: cosa manca davvero

1. **Un inventario con i numeri che contano**: VRAM e memoria unificata, banda, memoria
   libera per pool, motori.
2. **Un catalogo dei modelli con dati dichiarati e misurati** (memoria dei pesi, cache per
   token, attivi, licenza, banco), invece di quattro profili senza costi.
3. **Le regole** che dalla macchina e dalle funzioni volute fanno un piano, con le priorità
   (voce prima di tutto).
4. **La verifica** del piano su questa macchina (prova breve) e **l'adattamento** con l'uso,
   con uno stato salvato, come `contesto.json` e `voce_taratura.json`.
5. **La velocità di generazione nel registro dei turni**, senza la quale l'adattamento è
   cieco sulla parte più grande della prima frase.

---

## 2. Classi di macchine

Due numeri decidono quasi tutto: **quanta memoria veloce** c'è (VRAM dedicata, o la quota di
memoria unificata che la GPU può usare) e **quanta banda** ha (la generazione dei token è
limitata dalla banda, §3.5). Il terzo è il calcolo della GPU, che decide la **lettura** del
prompt (prefill): conta perché il prefisso di Calliope è grande (6–12k token, §1.2).

Bande dichiarate (consultate il 07/10/2026):

| Classe | Esempi | Memoria veloce | Banda | Fonte |
|---|---|---|---|---|
| **Solo CPU** | desktop o mini PC senza GPU NVIDIA | RAM, 16–64 GB | DDR5-5600 dual channel 89,6 GB/s teorici (6400: 102,4) | [D] 2 canali × 8 byte × MT/s |
| **GPU 8 GB** | RTX 5070 Laptop (il portatile di sviluppo), RTX 4060/5060 | 8 GB | 5070 Laptop **384 GB/s** (128 bit GDDR7) | [Agg] notebookcheck, laptopmedia |
| **GPU 12–16 GB** | RTX 4060 Ti 16 GB · 5060 Ti 16 GB · 4070 Ti Super · 5070 Ti | 16 GB | 288 · 448 · 672 · 896 GB/s | [Agg] Wikipedia RTX 40/50, kitguru, pcper; nvidia.com per la memoria |
| **GPU 24 GB** | RTX 3090 · RTX 4090 | 24 GB | 936 · 1008 GB/s | [Agg] Wikipedia, schede dei produttori |
| **GPU 32 GB** | RTX 5090 | 32 GB GDDR7, 512 bit | **1792 GB/s** | [Agg] Wikipedia RTX 50 |
| **GPU 48 GB e oltre** | RTX 6000 Ada 48 GB · RTX PRO 6000 Blackwell 96 GB | 48 · 96 GB | 960 · 1792 GB/s | [V] Lenovo Press LP1940, nvidia.com |
| **Unificata 64 GB** | Mac M4 Pro / M5 Pro, Strix Halo da 64 GB | ~48 GB per la GPU [D] | 273 / 307 · 256 GB/s | [V] Apple; [Agg] AMD |
| **Unificata 128 GB** | **DGX Spark (GB10)** · Strix Halo (Ryzen AI Max+ 395) · Mac M4 Max / M5 Max | ~100–120 GB per la GPU | **273** · 256 (≈215 misurati dalla GPU) · 546 / 460–614 GB/s | [V] docs.nvidia.com DGX Spark; [Agg] level1techs; [V] Apple |
| **Windows su ARM** | RTX Spark (N1X), il target futuro | fino a 128 GB unificati; la GPU ne vede ~80 % del resto dopo la riserva (ricerca del 02/10) | **~300 GB/s, non ufficiali** (la pagina NVIDIA non la dice; i 600 GB/s citati altrove sono NVLink-C2C) | [V] nvidia.com/rtx-spark per CPU, GPU e memoria; [Agg] per la banda |

Cosa ci sta e cosa vuol dire per Calliope (pesi da §3, cache da §3.4, Whisper large-v3-turbo
1,2–2,1 GB, riserva del sistema da §4.3; velocità da §3.5 con η 0,55 e tetto 250 token/s):

| Classe | Voce possibile (token/s) | Whisper | Guardiano | Agente | Note |
|---|---|---|---|---|---|
| Solo CPU | e2b ~30, e4b ~19 [D] | CPU: `small` int8 (faster-whisper su i7-12700K, 8 thread: 13 min di audio in 1 min 42 s [V, README]) | 1B sulla CPU | no | **decide la lettura**: sulla CPU il prefill è 10–50 volte più lento che sulla GPU [D], e 6–12k token di prefisso a freddo costano minuti. Come server **non è raccomandabile**: va bene come satellite, o con una Calliope ridotta (pochi tool, un livello) da misurare |
| GPU 8 GB | e4b **64–88 [M]**; e2b | GPU (1,2 GB) | 1B sulla CPU (il 1B sulla GPU non ci sta con voce e Whisper; l'8B nemmeno: «sul portatile da 8 GB i due modelli non stanno insieme», 06/10) | remoto | il portatile di oggi: nessuno spazio per il resto |
| GPU 12–16 GB | e4b (61–190 secondo la scheda); `gemma4:12b` denso 24–76 [D, da provare] | GPU | **8B** sulla GPU | remoto | il 26B (16,6 GB) non ci sta; il 12B denso passerebbe la soglia solo da 672 GB/s in su (§4.2) |
| GPU 24 GB | **26B-A4B** (~220–240 [D]) | GPU | 1B sulla GPU (l'8B non ci sta accanto al 26B) | il 26B stesso, su un secondo posto | oppure e4b + guardiano 8B + rilevatore separato |
| GPU 32 GB | **26B-A4B** (tetto ~250 [D]; gpt-oss-20b sulla 5090 205 token/s [Agg, LMSYS]) | GPU | **8B** | il 26B stesso, secondo posto; separato no | §4.8, esempio 2 |
| GPU 48 GB | 26B-A4B | GPU | 8B | separato: `gpt-oss:20b` (14 GB), o `qwen3.6:35b` stretto | con 96 GB tutto, immagini comprese |
| Unificata 64 GB | 26B-A4B (~60, come la DGX) | GPU (whisper.cpp; Metal su Mac, Vulkan su AMD) | 8B | `qwen3.6:35b` su Ollama (24 GB), stretto | su AMD e Apple nessun faster-whisper con GPU |
| Unificata 128 GB | 26B-A4B **74–79 [M, DGX]** | GPU (whisper.cpp sulla DGX [M]) | 8B | separato: Qwen3.6-35B-A3B (vLLM NVFP4 sulla DGX, 76 token/s [M]) | §4.8, esempio 3 |
| Windows su ARM | 26B-A4B (~65 [D]) | whisper.cpp con CUDA, o CPU: faster-whisper non c'è (ctranslate2 senza wheel `win_arm64`, ricerca del 02/10) | 8B | Ollama (vLLM solo in WSL2) | ogni dipendenza nativa va verificata (principio 4); Piper con onnxruntime `win_arm64` o sherpa-onnx |

La DGX è un caso speciale: **tanta memoria, poca banda**. Una RTX 5090 ha 6,5 volte la banda
della DGX e un quarto della memoria: genera il 26B più in fretta (e probabilmente lo legge più
in fretta), ma non tiene insieme voce, guardiano, rilevatore e un agente separato. È il senso
della domanda di Dario: la «signora macchina» domestica fa una voce migliore della DGX e un
secondo piano molto più povero.

---

## 3. Catalogo dei modelli: dichiarato e misurato

Dati dichiarati letti il 07/10/2026 su ollama.com/library (tag e dimensioni dei file),
Hugging Face (scheda e `config.json`) e le pagine dei produttori; la forma della cache dai
`/api/show` dei modelli già installati da noi (portatile e DGX). Le dimensioni di Ollama sono
quelle del file: in memoria si aggiungono cache e buffer (§4.3).

### 3.1 Voce

Requisiti: italiano, chiamate ai tool affidabili, thinking spegnibile, generazione veloce
(MoE con pochi attivi o densi piccoli).

| Modello (tag Ollama) | Parametri (attivi) | File Ollama | Contesto | Licenza | Dichiarato | **Misurato da noi** |
|---|---|---|---|---|---|---|
| `gemma4:e2b-it-qat` | 5,1B (2,3B effettivi) | 4,3 GB (con visione e audio); q4_K_M 4,6 | 128K | Apache 2.0 | 35+ lingue, tool, visione, audio [V] | delega 15/22 contro 22/22 del 4B, prima frase 0,23 s sul portatile (02/10) |
| **`gemma4:e4b-it-qat`** | 8B (4,5B effettivi) | 6,1 GB; ~3,1 GB caricati [M] | 128K | Apache 2.0 | MMMLU 76,6, τ² 42,2 [A] | **portatile 64–88 token/s, 4,2–4,6 GiB a 4–16k, banco 98–101/116 e 139/144 con le reti, prima frase 0,45–0,48 s; DGX 60–71 token/s** (02–03/10) |
| `gemma4:12b-it-qat` | 11,95B denso | 7,2 GB; q4_K_M 8,0 | 256K | Apache 2.0 | — | mai provato |
| **`gemma4:26b-a4b-it-qat`** | 25,2B (3,8B attivi; 128 esperti, 8 + 1 condiviso) | 16 GB; 16,6 GB caricati a 28 672 [M] | 256K | Apache 2.0 | MMMLU 86,3, τ² 68,2 [A] | **DGX 74–79 token/s, banco 110/116 e 143/144, prima frase 0,68–0,73 s (banco), 0,93–1,15 s di base nei turni veri; voce della DGX dal 06/10** |
| `gemma4:31b` | 30,7B denso | 19 GB | 256K | Apache 2.0 | τ² 76,9 [A] | escluso: ~11 token/s sulla DGX [Agg, 02/10] |
| `qwen3.5:4b` / `:9b` | 4,7B / 9,7B, ibridi DeltaNet | 3,3 / 6,6 GB | 256K | Apache 2.0 | 201 lingue, tool, thinking acceso di serie [V] | 4B: delega 17/22, prima frase 0,96 s sul portatile (02/10); 9B mai provato |
| `qwen3.6:35b` (35B-A3B) | 35B (3B) | 24 GB (q4_K_M) | 256K | Apache 2.0 | — | come voce solo misure (03/10); come agente: §3.2 |
| `gpt-oss:20b` | 21B (3,6B) | 14 GB (MXFP4) | 128K | Apache 2.0 | thinking **non** spegnibile (tre livelli) [V] | mai come voce |
| `ministral-3:8b` | 8,4B + 0,4B visione | 6,0 GB | 256K | Apache 2.0 | italiano esplicito, function calling [V] | mai provato |
| `granite4:tiny-h` | 7B (1B attivi), Mamba ibrido | 4,2 GB | 128K | Apache 2.0 | italiano esplicito, tool [V] | mai provato |

Velvet (Almawave, 2B e 14B) e Minerva 7B (Sapienza) sono modelli italiani, ma senza tool
calling dichiarato né tag Ollama verificati: fuori dal catalogo finché non lo si verifica.

**Per il piano contano solo e2b, e4b e 26B-A4B**: sono gli unici provati col banco e con le
reti (`PROFILI_LLM`). Gli altri sono «da provare»: il piano li mostra come candidati con la
stima, non li sceglie da solo (§4.2).

### 3.2 Agente, guardiano, rilevatore, embedding, immagini

| Ruolo | Modello | Parametri | Memoria | Licenza | Misurato da noi |
|---|---|---|---|---|---|
| Agente | **Qwen3.6-35B-A3B** (vLLM `nvidia/…-NVFP4`, o Ollama `qwen3.6:35b`) | 35B (3B attivi), 40 strati = 10 × (3 DeltaNet + 1 attenzione) | Ollama q4_K_M 24 GB, nvfp4 24 GB; vLLM sulla DGX 0,4 × 128 GB con 2,1 M token di cache fp8 [M] | Apache 2.0 | 76 token/s (vLLM, DGX), banco codice 11/12, documenti 10–11/12 (02/10); su Ollama errore 500 del parser nelle conversazioni lunghe (issue #16383, 02/10) |
| Agente (alternativa) | `gpt-oss:20b` | 21B (3,6B) | 14 GB | Apache 2.0 | DGX: llama.cpp 79,7–83,4 token/s, Ollama 49,7 [Agg: jetsonhacks, llama.cpp, LMSYS] |
| Agente (alternativa) | `gpt-oss:120b` | 117B (5,1B) | 65 GB | Apache 2.0 | DGX 52,9–58,7 token/s [Agg] |
| Guardiano | **`llama-guard3:8b`** | 8B denso | 4,9 GB (q4_K_M); 5,3 GB caricati a 2048 [M] | Llama 3.1 Community | 0 falsi su 33 frasi giuste, 12/14 vietate fermate (05/10) |
| Guardiano (ripiego) | `llama-guard3:1b` | 1,5B | 1,6 GB (q8_0) | Llama 3.2 Community | italiano tra le 8 lingue dichiarate [V]; e4b + 1B da freddi in locale 3,1 · 3,0 · 0,33 · 0,34 s (06/10); qualità sul banco dei minori **non misurata** |
| Guardiano (altri) | ShieldGemma 2B/9B, Qwen3Guard-Gen 0,6B/4B (su Ollama solo upload di utenti), Granite Guardian 2B | — | 0,5–5 GB | varie | installati sul portatile per il banco del 05/10 (`misura_guardiano.py`): scelto l'8B |
| Rilevatore di pericolo | `gemma4:e4b-it-qat` (output strutturato) | — | 3,1 GB a 2048 | Apache 2.0 | 9/10 sul banco, nessun falso allarme; 0,34–0,46 s di mediana sulla DGX (06–07/10) |
| Embedding | **`qwen3-embedding:0.6b`** | 0,6B | 639 MB (q8_0), contesto 32K | Apache 2.0 | MTEB multilingue 64,33 [A]; 17/18 contro 15/18 con le sole parole (05/10), sulla CPU |
| Embedding (alternativa) | `embeddinggemma:300m` | 0,3B | 239–622 MB, contesto **2K** | Gemma | mai provato |
| Immagini | **FLUX.2 [klein] 4B** | 4B + encoder Qwen3-4B | **~13 GB** [V, scheda] | Apache 2.0 | non provato; il 9B sulla DGX 3,3–4,4 s a 1024² [Agg, ricerca del 06/10] |
| Immagini (no) | FLUX.2 [klein] 9B | 9B + Qwen3 8B | ~29 GB [V] | **non commerciale** | — |
| OCR dell'archivio | il modello dell'agente (qwen3.6 legge le immagini), oppure `glm-ocr` (2,2 GB, già sulla DGX) | — | — | — | archivio provato con qwen3.6 (03/10) |

### 3.3 Whisper e Piper

| Modello | Parametri | ggml fp16 / quantizzato | Memoria dichiarata | **Misurato da noi** |
|---|---|---|---|---|
| `small` | 244M | 488 MB / q5_1 190 MB | ~2 GB (OpenAI), ~852 MB con whisper.cpp [V] | — |
| `medium` | 769M | 1,53 GB / q5_0 539 MB | ~5 GB, ~2,1 GB con whisper.cpp | — |
| **`large-v3-turbo`** | 809M (decoder da 4 strati) | 1,62 GB / q8_0 874 MB | ~6 GB (OpenAI, PyTorch) | **faster-whisper GPU +1,18 GiB, 0,19–0,24 s a frase, WER 10,6–11,5 % (24/09, portatile); whisper.cpp CUDA ~2,1 GB, 0,28 s, WER 12,4–13,4 % (DGX); faster-whisper sulla CPU ~5 s a frase (portatile)** |
| `large-v3` | 1550M | 3,1 GB / q5_0 1,08 GB | ~10 GB, ~3,9 GB con whisper.cpp | +1,87 GiB, 0,37–0,40 s, il nome 46/46 (24/09) |

Il README di faster-whisper misura solo large-v2 (GPU) e small (CPU: i7-12700K, 8 thread,
int8, 13 minuti di audio in 1 min 42 s, 1,5 GB): nessun dato dichiarato per turbo [V].

Piper: VITS in ONNX sulla CPU; `medium` 63,5 MB, `high` ~110 MB. Misurato (07/10): serena-high
sulla DGX ~6 ms a carattere con i thread di Piper, 3,5 con 8 (ramo `primo-pezzo`); una medium
~5 volte più veloce. La tara già il ramo `primo-pezzo`.

### 3.4 La cache per token, dalla forma del modello [M]

`contesto.kv_ollama` sui modelli già installati (portatile e DGX, `/api/show`, nessun download;
f16, senza il fattore 1,1). Byte per token = Σ sugli strati con attenzione globale di 2 × teste
KV × dimensione della testa × 2 byte; gli strati «sliding» costano una quantità fissa (la
finestra), gli strati lineari (DeltaNet, Mamba) uno stato fisso piccolo.

| Modello | Strati (con attenzione globale) | Teste KV × dim. | KiB a token (calcolo di oggi) | KiB a token veri [D dalla forma] | 32k token di finestra |
|---|---|---|---|---|---|
| `gemma4:e2b-it-qat` | 35 (gli ultimi 20 condividono la cache) | 1 × 512 | 6 (+6 MiB fissi) | 6 | 0,2 GB |
| `gemma4:e4b-it-qat` | 42 (18 condivisi; 4 globali) | 2 × 512 | 16 (+20 MiB) | 16 | 0,5 GB |
| `gemma4:26b-a4b-it-qat` | 30 (5 globali, 25 sliding da 1024) | 2 × 512 globali, 8 × 256 sliding | 20 (+200 MiB) | 20 | 0,85 GB |
| `qwen3.5:4b` / `qwen3.5:9b` | 32 (8 con attenzione, 24 DeltaNet) | 4 × 256 | 32 | 32 | 1,0 GB |
| `nemotron-3-nano` (30B-A3B, Mamba ibrido) | 52 (6 con attenzione) | 2 × 128 | 6 | 6 | 0,2 GB |
| `qwen3.6:35b` (35B-A3B) | 41 (1 su 4 con attenzione: `full_attention_interval` 4) | 2 × 256 | **82** | ~20 | 0,65 GB (il calcolo di oggi: 2,7) |
| `gpt-oss:20b` | 24 (metà sliding da 128) | 8 × 64 | **48** | ~24 | 0,8 GB (il calcolo: 1,6) |
| `qwen3-coder:30b` (30B-A3B) | 48 | 4 × 128 | 96 | 96 | 3,1 GB |
| `qwen3:8b` | 36 | 8 × 128 | 144 | 144 | 4,7 GB |
| `llama3.1:8b`, `llama-guard3:8b` | 32 | 8 × 128 | 128 | 128 | 4,2 GB |
| `llama-guard3:1b` | 16 | 8 × 64 | 32 | 32 | 1,0 GB |
| `gemma3:4b` | 34 (5 su 6 sliding da 1024) | 4 × 256 | **136** | ~23 (+~110 MiB) | 0,8 GB (il calcolo: 4,5) |
| `qwen3-embedding:0.6b` | 28 | 8 × 128 | 112 | 112 | (contesti corti) |

Cosa se ne ricava:
- **Gemma 4 e i modelli ibridi (Qwen3.5/3.6, Nemotron) hanno una cache minuscola**: con loro
  la finestra non la limita la memoria ma il tempo di rilettura (come sulla DGX: limite di
  memoria 1 056 915 token). Con i densi classici (Qwen3 8B, Llama) la memoria conta: 32k di
  finestra costano più di 4 GB, cioè su una GPU da 8 GB non stanno accanto ai pesi.
- **Tre difetti di `kv_ollama`**, tutti nel senso prudente (sovrastima): non conosce
  `full_attention_interval` quando le teste KV sono un numero solo (qwen3.6: 4 volte troppo),
  né lo schema alternato di gpt-oss e Gemma 3, che Ollama non espone (2 e 6 volte troppo).
  Per la voce di oggi (Gemma 4) è giusto; per un piano su altri modelli va corretto (fase 1).
- Il guardiano gira con `guardiano_num_ctx` 2 048: la sua cache non pesa (0,25 GB per l'8B).
- La `config.json` di Gemma 4 26B-A4B su Hugging Face dice 24 strati locali e 6 globali, e
  `attention_k_eq_v` (chiavi e valori uguali: la cache potrebbe valere la metà); il GGUF di
  Ollama ne segna 5 globali. 20 KiB è quanto conta Ollama e torna con la memoria della DGX
  (`contesto.json`: 22 528 byte a token col fattore 1,1); come llama.cpp tratti
  `attention_k_eq_v` non è verificato.
- **Un modello denso con una finestra lunga non sta su 8 GB**: sul portatile, il 07/10, un
  `qwen3:8b` caricato da altri a 32 768 token pesava 10,36 GB (`size` di `/api/ps`: 5,23 di
  file + 4,83 di cache + buffer) con `size_vram` 6,14 GB, cioè il 59 % sulla GPU e il resto
  sulla CPU [M]. È il caso che la prova (§5.1) deve riconoscere.

### 3.5 La velocità attesa: la formula e i suoi limiti

La generazione di un token legge una volta i pesi **attivi** e la cache fin lì: è limitata
dalla banda di memoria, non dal calcolo.

```
token/s (generazione) ≈ η × B / (W_attivi + KV_token × n_contesto)

B          banda di memoria del pool dove sta il modello (GB/s, §2)
W_attivi   byte dei pesi letti a ogni token: pesi totali per un denso, attivi per un MoE
           (≈ parametri attivi × bit per peso / 8; Q4_0 ≈ 4,5 bit, Q4_K_M ≈ 4,8, MXFP4 ≈ 4,25)
KV_token   §3.4; con 4k token di contesto pesa poco, a 28k sul 26B è +0,6 GB a token letto
η          efficienza del motore sulla macchina: 0,5–0,75
```

Taratura sulle nostre misure:

| Modello e macchina | B | W (stima) | Misurato | η implicito |
|---|---|---|---|---|
| gemma4 e4b, RTX 5070 Laptop, Ollama | 384 GB/s | ~2,6 GB | 64–88 token/s [M 02/10] | 0,45–0,6 |
| gemma4 e4b, DGX, Ollama | 273 | ~2,6 | 60–71 [M 03/10] | 0,57–0,68 |
| gemma4 26B-A4B Q4_0, DGX, Ollama | 273 | ~2,3 (3,8B attivi + parti comuni) | 74–79 [M 03/10] | 0,62–0,67 |
| gemma4 26B-A4B NVFP4 esperti + BF16, DGX, vLLM | 273 | ~4–5 (attenzione e parti dense in BF16) | 29 [M 03/10] | 0,45–0,5 |
| Qwen3.6-35B-A3B NVFP4, DGX, vLLM | 273 | ~1,8 | 76 [M 03/10] | 0,5 |

Per e4b, W è la parte del modello letta davvero: dei 3,1 GB caricati, le tabelle degli
embedding per strato (Per-Layer Embeddings) si leggono a righe, non intere [D].

Banchi pubblicati (llama.cpp, batch 1) danno η più alti: sullo scoreboard CUDA con Llama 2 7B
Q4_0 (3,56 GiB) RTX 4060 Ti 64 token/s (η ~0,85), 5070 Ti 182 (~0,78), 4090 189 (~0,72), 5090
300 (~0,64); sulla DGX gemma3 4B QAT 81, gpt-oss-20b 80–83, Qwen3-30B-A3B Q8_0 60–61; Strix
Halo Qwen3 30B-A3B 66–86 [Agg: discussioni #15013 e #16578 di llama.cpp, jetsonhacks,
level1techs; η calcolati da me]. Con 32k di contesto la generazione cala del 30–55 % (gpt-oss-20b
da 79,7 a 56,0; Qwen3-30B-A3B da 60,0 a 27,8 sulla DGX). Ollama sta sotto llama.cpp (gpt-oss-20b
sulla DGX 49,7 su Ollama secondo LMSYS contro 80 di llama.cpp).

Limiti della formula:
- **η dipende da motore, quantizzazione e GPU** (0,45 con NVFP4 su vLLM, 0,65 con Q4 su Ollama
  sulla stessa DGX). Il piano usa 0,55 finché la macchina non ha una misura, poi la sua.
- **Tetto per token**: sopra ~250–300 token/s il costo fisso di Ollama per token (lancio dei
  kernel, campionamento) conta più della banda [D]: su una 5090 un modello da 2 GB non va a
  1792 × 0,6 / 2 = 540 token/s. Il piano tiene un tetto di 250 token/s finché non misura.
- **MoE**: gli esperti scelti cambiano a ogni token; il valore medio regge, i singoli token no.
- **Lettura (prefill)**: è limitata dal calcolo, non dalla banda, e la formula non la dice. Si
  stima per rapporto con una macchina misurata (TFLOPS dichiarati) e si misura sempre alla
  prova (`measure_prefill` esiste già). Misure nostre: e4b 4 600 token/s a freddo sul
  portatile (02/10) e 2 670 con la storia (05/10); 26B 3 164–3 265 sulla DGX.
- **Contesa**: con l'agente che genera sulla stessa DGX il 26B è sceso da 29 a 14 token/s
  (vLLM, 03/10): la stima vale a GPU ferma, e il piano mette l'arbitro tra le condizioni.
- **CPU**: la stessa formula con la banda della RAM (§2), η 0,5–0,7; ma la lettura sulla CPU è
  10–50 volte più lenta che sulla GPU, ed è lei a decidere (§2, classe «solo CPU»).

---

## 4. Le regole del piano

Il piano è una funzione pura (si prova a secco con macchine finte, come `contesto.calcola`):

```
piano(macchina, funzioni_volute, catalogo, misure_salvate) → assegnazioni + stime + cosa non regge
```

- `macchina`: pool di memoria (VRAM dedicata; memoria unificata con la quota che la GPU può
  usare; RAM di sistema), banda di ogni pool, η misurato se c'è (§3.5), core, architettura e
  sistema, motori disponibili (Ollama sì/no e versione, vLLM, whisper.cpp, CUDA per
  CTranslate2), memoria che il sistema tiene sempre (desktop, altri servizi).
- `funzioni_volute`: dalla configurazione e dalle persone registrate, non chieste ogni volta:
  minori registrati (o `minori_enabled` con ospiti) → guardiano; `agenti`; archivio con OCR;
  immagini; numero di satelliti che parlano insieme (`satelliti_insieme`,
  `conversazioni_parallele`); biblioteca e ricerca semantica delle conversazioni.
- `catalogo`: §3, con le misure salvate che sostituiscono il dichiarato quando ci sono.

### 4.1 Priorità (la voce prima di tutto)

L'ordine in cui le risorse si assegnano. Una voce più in basso non toglie mai memoria o banda
a una più in alto; se non ci sta, si ridimensiona o si sposta (CPU, altra macchina, a
richiesta) e il piano lo dice.

1. **Riserva**: memoria del sistema (§4.3) e `contesto_margine_gb`.
2. **Voce**: il modello più bravo (banco) che rispetta la soglia di latenza (§4.2) e ci sta
   con una finestra di almeno 16 384 token.
3. **Whisper** sulla GPU se ci sta accanto alla voce; altrimenti sulla CPU con un modello più
   piccolo (§4.5). Il controllo è congiunto: se la voce migliore lascia Whisper sulla CPU e la
   seconda no, si sceglie la seconda quando la differenza di STT (≥ 1 s sulla CPU) supera
   quella di qualità.
4. **Guardiano** se ci sono minori o ospiti (`guardiano_ospiti`): è sicurezza, viene prima di
   tutto ciò che è comodità. Ordine dei ripieghi: 8B sulla GPU → 1B sulla GPU → 1B sulla CPU
   → nessun modello, con avviso fisso all'avvio e regole fisse (il comportamento di
   `guardiano_se_guasto: blocca` per i minori). Mai spento in silenzio.
5. **Rilevatore di pericolo**: un modello separato se ci sta (in parallelo, nessun costo sulla
   voce), altrimenti la voce stessa (in serie: il giudizio si aspetta prima della risposta, perché in
   parallelo sullo stesso modello rovinerebbe la cache del prefisso; costa quanto il giudizio,
   0,34–0,46 s di mediana col rilevatore separato sulla DGX il 06–07/10).
6. **Embedding** delle conversazioni: sulla CPU (0,6B, già così), a Calliope inattiva.
7. **Finestra di contesto oltre il minimo** (fino a quella che il tempo di rilettura permette:
   `contesto.prepara`, con la memoria dei residenti già tolta).
8. **Agente** (§4.6).
9. **Funzioni a richiesta**: OCR dell'archivio, immagini, più satelliti insieme (§4.7).

### 4.2 La soglia della voce

`latenza_avviso_s` (1,2 s) è la mediana della **prima frase vera**, che comprende STT, riletture,
memoria, contesto del turno, tool e guardiano. Le stime della §3 sono di una prima frase
«pulita». Dal registro della DGX (06–07/10) il rapporto tra base vera (0,93–1,15 s) e stima
pulita dello stesso modello (~0,7 s, §3.5) è **~1,4** [M/D]. Quindi:

- **stima pulita ≤ 0,8 s** (= 1,2 / 1,4 − margine): il modello passa;
- con un tool la stima si rifà con due passate (chiamata ~30 token + risposta): **≤ 1,4 s**;
- **rilettura a freddo** del prefisso (oggi 6–12k token secondo tool e livello): ≤ 4 s, perché
  è il p90 a ogni cambio di persona o di livello (06/10, analisi complessiva);
- la stima pulita è `T_stt + n_nuovi / v_lettura + t_primo_token + n_frase / v_generazione`,
  con `n_nuovi` ≈ 400 token (domanda, memoria, contesto del turno), `n_frase` ≈ 25 token,
  `t_primo_token` ≈ 0,1 s (Ollama, prefisso in cache);
- tra i modelli che passano, il più bravo **sul nostro banco** (`prova_regressione.py`,
  `prova_*_ollama`); un modello mai provato da noi vale «da provare» e non scavalca uno
  provato senza un banco fatto su questa macchina.

### 4.3 La memoria: cosa si somma

```
residenti = Σ pesi caricati (misurati con /api/ps quando ci sono, altrimenti file GGUF × 1,05)
          + Σ cache: finestra × posti × byte per token (§3.4) + fissi degli strati «sliding»
          + Whisper + buffer di calcolo (~0,3–0,5 GB a modello su Ollama [M: 4,6 GiB misurati
            contro 3,1 + 0,3 di pesi e cache per e4b a 16k])
          ≤ memoria del pool − riserva del sistema − contesto_margine_gb
```

- **Riserva del sistema** [D]: GPU dedicata con il desktop di Windows sopra 0,6–1,0 GB; GPU
  dedicata su Linux senza desktop 0,3 GB; memoria unificata: 12–16 GB per sistema, Calliope
  (Piper, CAM++, VAD, biblioteca, SQLite) e servizi accanto (sulla DGX, con vLLM e i container,
  la memoria disponibile è 21 GiB su 120).
- **Windows su memoria unificata** (RTX Spark): la GPU vede al più ~80 % della memoria
  restante dopo la riserva dedicata (ricerca del 02/10, porting guide NVIDIA).
- **vLLM** prenota `gpu_memory_utilization` × memoria all'avvio, pesi e cache insieme: per il
  piano è un blocco fisso (sulla DGX 0,4 × 128 GB ≈ 48 GB).
- **`OLLAMA_NUM_PARALLEL`**: ogni posto ha la sua cache della finestra intera; con la voce
  Gemma 4 costa poco (20 KiB a token: 0,6 GB a posto per 28 672 token), con un modello denso
  classico tanto (144 KiB a token per Qwen3 8B: 4 GB a posto).
- `OLLAMA_MAX_LOADED_MODELS` = numero dei residenti del piano sullo stesso Ollama (oggi
  `ollama_carico` lo controlla solo dopo). Predefinito di Ollama: 3 per GPU, «se ci stanno»
  [V, FAQ di Ollama].
- `OLLAMA_KV_CACHE_TYPE`: `q8_0` dimezza la cache rispetto a f16, `q4_0` la riduce a un quarto
  [V, FAQ]. Con Gemma 4 non serve (la cache è già piccola); con un denso classico su una GPU
  piccola è la prima leva, da proporre, non da imporre (qualità da misurare).
- Ollama sceglie da sé una finestra predefinita secondo la VRAM (meno di 24 GiB 4K, 24–48 GiB
  32K, da 48 GiB 256K [V, docs.ollama.com]): Calliope manda sempre `num_ctx`, quindi non la
  subisce, ma un altro programma sullo stesso Ollama sì (e ricarica il modello).

### 4.4 Il ripiego per gradini

Ogni ruolo ha una scala di candidati nel catalogo, dalla più bella alla più piccola (§3). Il
piano parte dall'alto e scende finché tutto sta in memoria e la voce passa la soglia;
alla verifica (§5.1) scende ancora se la misura lo chiede, **solo tra i modelli installati**.
Scale proposte:

- voce: `gemma4:26b-a4b-it-qat` → `gemma4:e4b-it-qat` → `gemma4:e2b-it-qat` (gli unici tre
  provati col banco e con le reti; altri candidati della §3 entrano solo dopo un banco);
- Whisper: `large-v3-turbo` GPU → `large-v3-turbo` CPU int8 (solo se la CPU è veloce) →
  `small` CPU int8 → `base` CPU (e il registro delle capacità lo dice);
- guardiano: `llama-guard3:8b` → `llama-guard3:1b` → 1B sulla CPU → solo regole;
- rilevatore: `gemma4:e4b-it-qat` separato → la voce stessa;
- agente: §4.6.

### 4.5 Whisper: GPU o CPU

- GPU se c'è un motore: faster-whisper con CUDA (Windows e Linux x86-64), **whisper.cpp con
  CUDA** su Linux aarch64 (CTranslate2 per aarch64 è solo CPU: setup-dgx); su Windows ARM
  faster-whisper non c'è (ctranslate2 senza wheel `win_arm64`, ricerca del 02/10): whisper.cpp
  o la CPU. Su AMD e Apple: whisper.cpp (Vulkan, Metal), non faster-whisper.
- Memoria: large-v3-turbo +1,18 GiB con faster-whisper (24/09), ~2,1 GB con whisper.cpp
  (05/10); 0,2–0,3 s a frase sulla GPU.
- CPU: large-v3-turbo ~5 s a frase sul portatile (ripiego visto davvero, stt-tts): fuori
  soglia. Sulla CPU il piano sceglie `small` int8 con beam 1 se il processore lo regge entro
  ~1 s a frase (da misurare alla prova: è l'unico modo serio, la velocità della CPU varia
  troppo) e lo dice («capisco peggio: WER attesa ~+10 punti» [D, da misurare con
  `misura_stt.py`]).
- Il ripiego su CPU (principio 7) resta sempre, con il modello di riserva più piccolo che il
  piano ha scelto per quella CPU.

### 4.6 L'agente: sì, no, dove

| Situazione | Agente |
|---|---|
| Memoria per un MoE da agente accanto a voce, Whisper e guardiano (≥ ~25 GB liberi in più, banda ≥ 250 GB/s) | **separato**: `qwen3.6:35b-a3b` (Ollama, 23–24 GB) o su vLLM NVFP4 dove c'è (Linux) |
| La voce è il 26B-A4B e il resto non ci sta | **lo stesso modello della voce**, con il thinking acceso e un secondo posto (`OLLAMA_NUM_PARALLEL=2`): costa solo la cache del secondo posto, l'arbitro ferma l'agente quando qualcuno parla. Più debole sul codice (AA Coding Index 39 contro 54 di Qwen3.6-27B, ricerca del 02/10) |
| La voce è il 4B o il 2B | agente locale **no** (il 4B scrive codice e documenti male, e una seconda passata lunga sulla stessa GPU blocca la voce); **remoto** se c'è un'altra macchina (`dgx.yaml`, `agenti_url`), come oggi il portatile |
| RAM di sistema grande (≥ 64 GB) e GPU piccola | possibile un MoE con gli esperti in RAM (pochi parametri attivi: 3B) [D, da misurare]: lento (stima 10–25 token/s su DDR5), solo per lavori notturni; mai mentre la voce lavora (stessa banda di PCIe e CPU) |
| Nessuno dei casi | agenti «da configurare» con il motivo: «su questa macchina non c'è posto per un agente; si può usare quello di un altro computer» |

### 4.7 Funzioni sostenibili

| Funzione | Serve | Regola |
|---|---|---|
| OCR dell'archivio | un modello che legge le immagini (oggi quello degli agenti; Gemma 4 e4b e 26B vedono le immagini) | con l'agente separato: l'agente; senza: la voce **solo a Calliope inattiva** (di notte, come gli embedding), a lotti |
| Immagini (FLUX.2 klein 4B, ~13 GB, ricerca del 06/10) | ~13 GB liberi per qualche secondo | residente solo se avanza memoria dopo l'agente; altrimenti **a richiesta** (carica, genera, scarica) se il pool è unificato o la VRAM libera a voce ferma basta; altrimenti no |
| Più satelliti insieme | un posto di Ollama per conversazione (`conversazioni_parallele`) | posti = min(satelliti attivi, memoria / cache per posto); sulla DGX Ollama 0.35 ne faceva comunque una alla volta (06/10): da rimisurare con `NUM_PARALLEL=2` |
| Ricerca semantica delle conversazioni | embedding 0,6B | sempre (CPU); su una macchina senza memoria: solo per parole (FTS5), già previsto |
| Correzione della trascrizione | una passata del modello sulle frasi incerte | solo se la stima della passata (≈ 0,4 s con il 4B sulla DGX) sta nel tempo massimo (`stt_correzione_timeout_s`) |

### 4.8 Tre piani completi

Numeri: pesi caricati misurati dove li abbiamo (e4b, 26B, guardiano), altrimenti file + 5 %;
cache da §3.4; velocità da §3.5 (η 0,55, tetto 250) o misurate; prima frase «pulita» con la
formula della §4.2.

**Esempio 1 — il portatile (RTX 5070 Laptop 8 GB, 384 GB/s, 32 GB di RAM, Windows 11), con un
minore registrato, agente sulla DGX**

| Ruolo | Scelta | Memoria GPU | Velocità | Perché |
|---|---|---|---|---|
| Riserva | desktop di Windows + margine | 0,8 + 0,5 GB | | |
| Voce | `gemma4:e4b-it-qat`, finestra ~20k | 4,7 GB [M] | 64–88 token/s [M], prima frase pulita ~0,45 s | il 26B non ci sta; e2b passa ma è peggiore (delega 15/22) |
| Whisper | large-v3-turbo, GPU | 1,2 GB [M] | 0,2 s [M] | ci sta: 7,2 GB in tutto |
| Guardiano | `llama-guard3:1b` **sulla CPU** | 0 | ~1 s a giudizio [D, da misurare] | sulla GPU non ci stanno né l'8B né l'1B (0,8 GB liberi); avviso all'avvio: «il guardiano gira sul processore: i turni dei minori sono più lenti» |
| Rilevatore | la voce stessa (in serie) | 0 | +0,3–0,5 s sui turni dei minori | nessun posto per un secondo modello |
| Embedding | qwen3-embedding 0.6b, CPU, a Calliope inattiva | 0 | | come oggi |
| Agente | remoto (`dgx.yaml`) | 0 | | qui non ci sta |
| Contesto | dal tempo: ~20 480 (come oggi con la compressione) | | | |
| `OLLAMA_MAX_LOADED_MODELS` | 2 (voce, guardiano sulla CPU) | | | |
| Non sostenibile | agente locale, immagini, OCR locale, due satelliti insieme | | | «Le immagini no: servono 13 GB e la scheda video ne ha 8.» |

**Esempio 2 — la «signora macchina» di Dario (RTX 5090 32 GB, 1792 GB/s, 64 GB di RAM,
Windows 11 o Linux), due minori, archivio, due satelliti**

| Ruolo | Scelta | Memoria GPU | Velocità | Perché |
|---|---|---|---|---|
| Riserva | desktop + margine | 0,8 + 0,5 GB | | |
| Voce | `gemma4:26b-a4b-it-qat`, finestra ~28k, **due posti** (`OLLAMA_NUM_PARALLEL=2`) | 16,6 + 0,6 GB | ~200–250 token/s [D] (gpt-oss-20b, 3,6B attivi, 205 sulla 5090 [Agg, LMSYS]); prima frase pulita ~0,4 s [D] | il migliore provato; la soglia passa largamente |
| Whisper | large-v3-turbo, GPU (o `large-v3`: il nome 46/46, +0,7 GB) | 1,2–1,9 GB | ~0,1–0,2 s [D] | c'è posto |
| Guardiano | `llama-guard3:8b` | 5,3 GB | | i minori lo vogliono |
| Rilevatore | `gemma4:e4b-it-qat` separato, in parallelo | 3,1 GB | | ci sta: niente attesa sui turni dei minori |
| Embedding | CPU | 0 | | |
| Totale | | **~28–29 GB su 32** | | |
| Agente | **il 26B stesso**, thinking acceso, sul secondo posto, con l'arbitro | 0 in più | | Qwen3.6-35B-A3B (24 GB) non ci sta; in alternativa, solo con un sì: agente con gli esperti nella RAM di sistema (64 GB), lavori lenti e notturni [D, da misurare] |
| Archivio (OCR) | la voce (Gemma 4 vede le immagini), a Calliope inattiva | | | |
| Immagini | **no** con i minori in casa (13 GB non ci sono); senza minori, a richiesta togliendo guardiano e rilevatore (8,4 GB) dalla memoria: da decidere | | | |
| Satelliti insieme | 2 (i due posti della voce) | | | |
| Contesto | dal tempo; la memoria non limita (20 KiB a token) | | | |
| `OLLAMA_MAX_LOADED_MODELS` | 3 | | | |

Cosa direbbe a Dario: «Su questa macchina la voce va più veloce che sulla DGX, ma i lavori
lunghi li fa la voce stessa, con un modello più debole sul codice. Per un agente separato
serve un'altra macchina o una GPU da 48 GB.»

**Esempio 3 — la DGX Spark (128 GB unificati, 273 GB/s, Linux aarch64), com'è oggi**

| Ruolo | Scelta | Memoria | Velocità | Stato |
|---|---|---|---|---|
| Riserva | sistema, Calliope, SearXNG, container non di Calliope | ~15 GB + margine | | |
| Voce | `gemma4:26b-a4b-it-qat`, 28 672 token, due posti | 16,6 GB [M] | 74–79 token/s [M] | **come oggi** |
| Whisper | large-v3-turbo su whisper.cpp CUDA, ripiego faster-whisper CPU | ~2,1 GB [M] | 0,16–0,17 s di mediana [M, 06–07/10] | come oggi |
| Guardiano | `llama-guard3:8b` | 5,3 GB [M] | | come oggi |
| Rilevatore | `gemma4:e4b-it-qat` separato | 3,1 GB [M] | 0,34–0,46 s [M] | come oggi |
| Embedding | qwen3-embedding 0.6b | 0,6 GB | | come oggi |
| Agente | Qwen3.6-35B-A3B NVFP4 su vLLM, `gpu_memory_utilization` 0,4 | ~48 GB [M] | 76 token/s [M] | come oggi |
| Immagini | FLUX.2 klein 4B **a richiesta** (13 GB; MemAvailable oggi 21 GiB) | | | proposta del 06/10 |
| `OLLAMA_MAX_LOADED_MODELS` | 4 (impostato) | | | |
| Contesto | 28 672 dal tempo (memoria: 1 M token) | | | |

Il piano qui non cambierebbe niente: deve **ritrovare** le scelte fatte a mano in una
settimana di misure. È la prova più semplice che le regole sono giuste (diventa un caso di
`prova_piano`). Le proposte che farebbe sono quelle già aperte: la correzione della
trascrizione è già spenta (`stt_correzione: false`), restano i due posti di Ollama da misurare
e le immagini a richiesta.

---

## 5. Verifica e adattamento

Lo schema è quello della voce (`taratura_voce.py`), applicato a ogni scelta del piano:
**dichiarato** (catalogo, il più debole) → **misurato alla prova** (dopo l'accettazione, e a
ogni cambio di modello o di macchina) → **misurato con l'uso** (registro dei turni, il più
forte). Una scelta scritta in `calliope.locale.yaml` o nell'ambiente vince sempre.

### 5.1 La prova breve (dopo l'accettazione, ~1–2 minuti)

Gira con Calliope senza turni in corso (all'avvio, prima del saluto, o da `calliope stato
--piano --prova`), un modello alla volta, nell'ordine del piano:

| Cosa | Come | Con che cosa esiste già |
|---|---|---|
| Memoria di partenza | nvidia-smi (`memory.used`, per processo con `--query-compute-apps`) o `/proc/meminfo` (MemAvailable) **prima** di caricare i modelli di Calliope; su Windows anche la memoria dedicata usata dal desktop | `contesto.memoria_libera` (solo la libera) |
| Carico e memoria vera di ogni modello | `/api/generate` vuoto con `keep_alive` e `num_ctx` del piano, poi `/api/ps`: `size` e **`size_vram`**. `size_vram < size` = parte del modello sulla CPU: il piano **non regge** (generazione 3–10 volte più lenta), si passa al ripiego. Poi di nuovo nvidia-smi/meminfo: la differenza è la memoria vera (`ollama ps` sottostima, trappola nota) | `contesto.leggi_ollama` legge `/api/ps` solo per la finestra |
| Lettura (prefill) | il prefisso vero del livello «amministra», come oggi | `Brain.measure_prefill` |
| **Generazione (decode)** | 128 token da un prompt fisso, `eval_count / eval_duration` (Ollama); con vLLM i tempi dei pezzi in streaming | **manca** |
| Prima frase | due domande fisse col prefisso in cache: una senza tool («Calliope, raccontami in una frase cos'è un arcobaleno.»), una con un tool di sola lettura («che ore sono?»); tempo fino alla prima frase completa, come `prima_frase_s` | i banchi (`prova_regressione.py`) lo fanno con 58 frasi; qui ne bastano 2 × 3 |
| Whisper | un file fisso **sintetizzato da Piper** al momento (niente registrazioni vere nel repository: una frase con il nome e una lunga), sul dispositivo del piano; tempo e trascrizione esatta sì/no | `misura_stt.py` (con le registrazioni private) |
| Guardiano e rilevatore | un giudizio su una frase innocua, tempo | `Guardiano.prepara` li carica già all'avvio |
| Voce | la frase fissa di `taratura_voce` | fatto nel ramo `primo-pezzo` |

Confronto con il dichiarato e ripiego automatico:
- **Memoria**: misurata > dichiarata + 15 % o `size_vram < size` → il piano si ricalcola con
  le misure vere (non con quelle dichiarate) e scende di un gradino **tra i modelli già
  installati** (§4.4); mai un download senza «sì».
- **Generazione**: misurata < 0,6 × stimata → la formula è sbagliata per questa macchina:
  si salva η misurato (§3.5) e si ricalcolano le stime di tutti i candidati (anche quelli non
  installati: è così che il piano «impara» la macchina).
- **Prima frase** stimata dalla prova (prima frase misurata + STT misurato) oltre la soglia
  (§4.2) → ripiego della voce, oppure, se nessun modello installato ci sta, si tiene il
  migliore e lo si dice («la voce risponderà in circa 1,6 secondi; con il modello X, da
  scaricare, circa 0,8»).
- Ogni ripiego si scrive nello stato con il motivo, e `calliope stato --piano` lo dice.

### 5.2 Adattamento con l'uso

Dai tempi veri del registro dei turni (`latenza.giorno`), una volta al giorno e all'avvio,
con abbastanza turni (`MIN_RISPOSTE`, 10) e con isteresi (una regolazione resta almeno un
giorno; si torna indietro solo se la mediana peggiora del 15 %):

| Si regola da sola (reversibile, nessun download, nessuna funzione tolta) | Segnale | Effetto |
|---|---|---|
| Finestra di contesto | lettura misurata e riletture oltre 1 s (`lettura`), memoria | già fatto (`contesto.prepara`); in più: riservare la memoria dei residenti del piano |
| Thread di Piper, primo pezzo | `sintesi_s`, distacco testo-voce | fatto nel ramo `primo-pezzo` |
| Posti di Ollama per la voce (`OLLAMA_NUM_PARALLEL`) | riletture a freddo al cambio di persona | **solo proposta**: è una variabile del servizio (sudo) |
| Rilevatore di pericolo separato o la voce stessa | `guardiano.pericolo_ms` e prima frase dei minori | sì se entrambi sono già installati |
| `keep_alive` dei modelli secondari | ricariche viste in `/api/ps` | sì |
| Cessione all'agente (arbitro: pausa di vLLM, pezzi di prefill) | prima frase con un lavoro in corso contro senza | sì, entro i limiti in `Config` |
| Correzione della trascrizione | correzioni scadute (il 05/10 sulla DGX col 26B non arrivava quasi mai in 0,4 s) | spegnerla sì (è un ripiego di qualità, non di sicurezza); riaccenderla solo con proposta |
| Beam di Whisper sulla CPU | `stt_s` oltre 1 s | 5 → 1 sì (WER +3–4 punti, taratura del 24/09) |
| Frase d'attesa | prima frase oltre la soglia | già c'è; il piano ne abbassa la soglia sulle macchine lente |

| Solo con proposta e «sì» (chi amministra, due turni come `installa_proponi`) | Perché |
|---|---|
| Cambio del modello della voce, dell'agente, del guardiano, di Whisper | cambia cosa dice Calliope, non solo quanto ci mette: va provato col banco |
| Ogni download (`ollama pull`, Whisper, voci) | spazio, tempo, rete |
| Licenze diverse da Apache/MIT (Gemma, Llama, CC-BY-NC…) | decisione di chi installa |
| Variabili di Ollama nel servizio (`OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_FLASH_ATTENTION`) | sudo: Calliope dice il comando, non lo fa (come oggi in `ollama_carico.avviso`) |
| **Spegnere una funzione di sicurezza** (guardiano, rilevatore, frase di sfida) | mai da sola, nemmeno se è lenta: lo dice e propone un modello più piccolo |

### 5.3 Dove si salva e cosa vince

- **`taratura.json`** accanto a `calliope.yaml` (scrittura atomica con
  `persistenza.scrivi_json`, copia `.bak`, letto con `leggi_json` come `voce_taratura.json`):
  - `macchina`: l'impronta (processore, GPU, VRAM, RAM, sistema, architettura, versione di
    Ollama): se cambia, il piano si rifà (è un'altra macchina, o una GPU nuova);
  - `misure`: per modello e motore (`ollama|url|modello`, la stessa chiave di
    `contesto.json`): memoria vera, `size_vram`, lettura, generazione, prima frase, quando;
    η della macchina; Whisper per modello e dispositivo;
  - `piano`: le scelte, con fonte (`dichiarato`, `prova`, `uso`) e motivo, chi l'ha accettato e
    quando, i ripieghi fatti;
  - `regolazioni`: le manopole della §5.2 con il valore, il segnale che le ha mosse e la data
    (per tornare indietro e per `calliope stato --piano`).
- `contesto.json` e `voce_taratura.json` restano come sono (sono già tarature): il piano li
  legge, non li assorbe.
- **Precedenza**: il piano decide **solo i campi che valgono «auto» dopo tutti i file**
  (predefinito < `calliope.yaml` < `calliope.locale.yaml` < `CALLIOPE_*`), come oggi
  `llm_num_ctx` e `tts_thread`. `calliope.yaml` resta uguale all'esempio (principio 3) e
  contiene tutti i campi: se il piano stesse «sotto» `calliope.yaml` non vincerebbe mai, se
  stesse «sopra» scavalcherebbe chi amministra. Quindi i predefiniti dei campi del piano
  diventano «auto»: `llm_profilo: auto` (oggi `None` + `llm_model`), `whisper_model` e
  `whisper_device: auto`, `guardiano_modello: auto`, `guardiano_pericolo_modello: auto`,
  `agenti_modello: auto`. Un valore scritto in `calliope.locale.yaml` vince: il piano lo
  rispetta, lo misura lo stesso e, se non regge, lo **dice** senza cambiarlo. Con «auto» e
  nessun piano accettato valgono i predefiniti di oggi (il portatile non cambia).
- Calliope non scrive mai `calliope.yaml` né `calliope.locale.yaml` (regola del 01/10): il
  piano accettato vive in `taratura.json`.

---

## 6. Interfaccia

### 6.1 Terminale

```
calliope stato --piano              # la macchina, il piano, stime e misure, cosa non regge
calliope stato --piano --json       # per gli script e l'installatore
calliope stato --piano --prova      # la prova breve (§5.1) e il confronto dichiarato/misurato
calliope stato --piano --accetta    # accetta il piano proposto (download con s/N, uno alla volta)
calliope stato --piano --funzioni agenti,immagini,minori   # il piano con queste funzioni volute
```

Esempio di uscita sul portatile (stime da §3, misure di oggi):

```
Macchina: RTX 5070 Laptop 8 GB (384 GB/s), 32 GB di RAM, Windows 11 x86-64 — classe «GPU 8 GB»
Voce        gemma4:e4b-it-qat      4,6 GB   64–88 token/s (misurati)   prima frase ~0,5 s   ✓
Whisper     large-v3-turbo, GPU    1,2 GB   0,2 s a frase (misurato)                       ✓
Guardiano   llama-guard3:1b, GPU   1,6 GB   non ci sta con la voce e Whisper: CPU, ~1 s   ⚠
Embedding   qwen3-embedding:0.6b   CPU                                                     ✓
Agente      sulla DGX (dgx.yaml)   —        qui non ci sta                                 ✓
Contesto    20 480 token (tempo)
Non sostenibile qui: immagini (13 GB), agente locale, due satelliti insieme.
Per andare più veloce: niente da fare qui; la voce è già la più veloce che ci sta.
```

### 6.2 A voce

`calliope_stato` con `cosa=piano` (solo chi amministra sente proposte e passi; i familiari
«chiedi a chi amministra»; gli ospiti niente), risposte brevi per la voce:
- «Come posso andare più veloce?» → la causa più grande dal registro dei turni (oggi lo sa già
  `latenza.avviso`) e **una** proposta: «La prima frase oggi arriva in 1,3 secondi; il tempo
  va quasi tutto nei tool. Con un secondo posto in Ollama il cambio di persona costerebbe 2
  secondi in meno: serve un comando da terminale.»
- «Cosa posso abilitare su questa macchina?» → le funzioni sostenibili non accese, e quelle
  che non reggono con il perché in una frase («Le immagini no: servono 13 GB e ne restano 2.»).
- «Quale modello mi consigli?» → il piano, con il dichiarato detto come tale («secondo i dati
  del produttore… da provare»).
- Il «sì» passa da `installa_proponi`/`installa_avvia`, come oggi: proposta in un turno,
  consenso nel successivo, stessa persona, riconosciuta dalla voce.

### 6.3 Registro delle capacità e catalogo

- Una capacità nuova **«macchina»** (`utente=False`): attiva se il piano è accettato e
  verificato; «da configurare» se c'è un piano proposto non accettato; nota con la classe e
  il primo problema («il guardiano gira sulla CPU»). Le capacità che il piano dichiara non
  sostenibili (agenti, immagini) diventano «da configurare» con il motivo del piano, non
  «mancante».
- `capacita.aggiungibili` aggiunge i modelli del piano non installati.
- Il catalogo (`installa/catalogo.py`) passa da `modello_llm` (solo `llm_model`) a
  un'azione per **ruolo**: `modello_voce`, `modello_guardiano`, `modello_rilevatore`,
  `modello_embedding`, `modello_agente`, ognuna con il tag che dice il piano, la dimensione
  dichiarata e la licenza nella proposta. L'origine resta `/api/pull` dell'Ollama locale (i
  digest li verifica Ollama). I pesi di vLLM restano fuori: `vllm.sh` dice il comando.

### 6.4 Prima installazione

- **Linux** (`setup/linux/installa.sh`): dopo la verifica dell'ambiente, `calliope stato
  --piano --json` e la proposta a terminale («Su questa macchina: voce X, Whisper Y,
  guardiano Z; scarico 21 GB? [s/N]»), poi `--prova`. Come oggi per `whisper_riserva`:
  chiede, non fa da sé.
- **Windows** (`docs/aree/setup-windows.md`): il primo comando dopo il venv diventa
  `python -m calliope.stato --piano`, al posto di `ollama pull gemma4:e4b-it-qat` scritto nel
  documento.
- **Satellite**: niente piano dei modelli (non ne usa), solo la parte audio; ma se la macchina
  è sotto la soglia della classe «solo CPU» l'installatore lo dice: «questa macchina va bene
  come satellite, non come server».

---

## 7. Proposta di implementazione a fasi

Niente codice in questo ramo. Stime in giorni di lavoro di un agente, prove comprese.

| Fase | Cosa | Dove | Prove | Stima |
|---|---|---|---|---|
| **0. Misurare prima** | Velocità di generazione nel registro dei turni (`eval_count`/`eval_duration` di Ollama in `_note_usage`; con vLLM tempo tra primo e ultimo pezzo) e in `calliope stato --turni`; `size_vram` contro `size` di `/api/ps` all'avvio (riga d'avviso se un modello è in parte sulla CPU); banco `prove/misura_macchina.py`: lettura, generazione e prima frase pulita per i modelli già installati, su portatile e DGX, a GPU ferma | `brain.py`, `latenza.py`, `ollama_carico.py`, `prove/` | `prova_latenza` (campo nuovo), `prova_ollama_carico` | 1–1,5 |
| **1. Inventario e catalogo** | `macchina.py` con pool di memoria (VRAM anche su Linux con nvidia-smi, unificata sì/no, quota della GPU su Windows ARM), memoria libera, motori; tabella delle bande per nome di GPU/SoC (con fonte e data, come le versioni nel catalogo); `calliope/modelli.py`: il catalogo della §3 come dati (dichiarati con fonte e data, misure nostre, banco), con la forma della cache letta da `/api/show` quando il modello è installato | `macchina.py`, `modelli.py` (nuovo), `contesto.kv_ollama` (schema di Gemma 3 e strati ibridi) | `prova_macchina` a secco con registri e `/proc` finti | 2 |
| **2. Il piano, in sola lettura** | `calliope/piano.py`: la funzione pura della §4 (priorità, somma della memoria, soglia della voce, gradini) e `calliope stato --piano [--json] [--funzioni …]`; il piano **non applica niente** | `piano.py` (nuovo), `stato.py` | `prova_piano`: macchine finte (solo CPU, 8, 16, 32, 128 GB unificati, Windows ARM), con i tre esempi della §4.8 come casi attesi e i casi contrari (guardiano mai tolto in silenzio, voce mai sotto un modello secondario) | 2–3 |
| **3. Verifica e stato** | `--piano --prova` (§5.1), `taratura.json` atomico, confronto dichiarato/misurato, η salvato, ripiego tra i modelli installati; `contesto.prepara` toglie dalla memoria i residenti del piano non ancora caricati | `piano.py`, `contesto.py`, `persistenza.py` | `prova_piano` (prova con Ollama finto che risponde con `size_vram` ridotto: deve scendere di gradino), `prova_contesto` | 2 |
| **4. Applicazione** | I campi «auto» (§5.3) e il loro passaggio in `config.py` (il piano accettato si applica dopo i file, solo dove vale «auto»); i passi per le variabili di Ollama (comandi, mai sudo); catalogo per ruolo (`modello_voce`, `modello_guardiano`…) con dimensione e licenza nella proposta | `config.py`, `installa/catalogo.py`, `servizio.py`, `capacita.py` (capacità «macchina») | `prova_config` (l'esempio rigenerato resta uguale; «auto» senza piano = predefiniti di oggi), `prova_installa`, `prova_capacita` | 2–3 |
| **5. Adattamento con l'uso e voce** | Le manopole della §5.2 con isteresi e nome nel registro (`regolazioni`), `calliope_stato(cosa=piano)` per «come posso andare più veloce?» e «cosa posso abilitare?» | `latenza.py`, `piano.py`, `tools/stato.py` | `prova_piano` (registri finti: la regolazione scatta, torna indietro, non spegne mai la sicurezza), `prova_stato_ollama` (il modello sceglie `cosa=piano`) | 2–3 |
| **6. Installatori** | `installa.sh` e il documento di Windows propongono il piano e la prova | `setup/linux/`, `docs/aree/setup-windows.md` | `prova_linux`, `prova_gestore` | 1 |

**Totale: ~12–15 giorni.** Le fasi 0–2 da sole (5–6 giorni) danno già il valore principale
per chi installa su un'altra macchina: un piano proposto a terminale, con stime oneste. La
fase 0 serve comunque, anche senza il resto: oggi la generazione non si vede nel registro.

### 7.1 Rischi

- **Dati dichiarati sbagliati o vecchi.** Le dimensioni di Ollama cambiano tra versioni dei
  tag (il `latest` di un modello si sposta), le schede dei modelli non dicono la velocità, e
  per l'italiano e i tool nessun benchmark dichiarato predice il nostro banco (il 26B a 74–79
  token/s su Ollama e 29 su vLLM NVFP4: stesso modello, motore diverso). Rimedio: ogni dato
  con fonte e data; appena il modello è installato valgono `/api/show` e `/api/ps`; la qualità
  si decide solo col banco, e un modello «da provare» non scavalca uno provato.
- **I modelli cambiano ogni mese.** Il catalogo invecchia come le versioni di Kiwix: come
  là, il codice tiene solo ciò che non si può ricavare (ruolo, scala, banco), e il resto si
  legge dal motore. Una revisione del catalogo a ogni cambio di modello della voce.
- **Ollama, vLLM, llama.cpp diversi.** vLLM prenota la memoria all'avvio, legge la sua cache
  da `/metrics` e con NVFP4 può essere più lento di Ollama Q4 (26B: 29 contro 77 token/s);
  Ollama non vincola i tool e ricarica il modello se `num_ctx` cambia. Il piano tratta ogni
  motore come una «classe» con le sue regole (già oggi `contesto.calcola` ha due rami).
- **Memoria condivisa con altro.** Sulla DGX altri container non di Calliope; sul portatile
  altri agenti (7,6 GB su 8 occupati alla lettura del 07/10). La prova deve leggere la memoria
  prima di caricare i modelli e il piano deve dire «con quello che gira adesso non ci sta»
  invece di scegliere un modello minuscolo.
- **Variabilità della GPU** (64 contro 88 token/s sullo stesso portatile, clock e
  temperatura): mediane su più giri e isteresi; mai decidere da una misura sola.
- **Classi non provate** (AMD, Apple, Windows ARM): il piano le riconosce ma le marca «non
  provate qui», e i motori (whisper.cpp con Vulkan o Metal, Ollama con ROCm) vanno verificati
  prima di dichiararle sostenibili. Calliope oggi non gira su macOS (PC a voce solo Windows,
  servizio solo Linux): la classe Apple è un riferimento per la banda, non un obiettivo.
- **Prova lunga all'avvio**: la verifica completa carica ogni modello; si fa solo dopo
  l'accettazione o un cambio di macchina, mai a ogni avvio (all'avvio bastano le misure che
  già si fanno: lettura ogni 7 giorni, voce).

### 7.2 Cosa misurare prima di scrivere il piano

1. **η della formula** (§3.5) su portatile e DGX con i modelli già installati (e4b, e2b,
   26B, qwen3.5 4B/9B, qwen3:8b, gpt-oss 20B, qwen3.6 35B, llama-guard3 1B/8B), a GPU ferma,
   a finestra corta e a 16–28k: dice se basta un η per macchina o serve un η per famiglia
   (denso, MoE, Gemma con gli embedding per strato).
2. **Il rapporto tra prima frase vera e pulita** (oggi 1,4 da un giorno di DGX): con la
   generazione nel registro (fase 0) si calcola per ogni giorno.
3. **Whisper sulla CPU** del portatile e della DGX: `small`, `medium`, `large-v3-turbo` int8,
   beam 1 e 5, sulle 104 registrazioni (`misura_stt.py`): tempo e WER, per la scala della
   §4.4.
4. **Il guardiano 1B** contro l'8B sul banco dei minori (`misura_guardiano.py`): oggi il
   ripiego sul portatile è il 1B, ma la sua qualità sul nostro banco non è nel documento dei
   minori.
5. **`OLLAMA_NUM_PARALLEL=2`** sulla DGX (già impostato): riletture al cambio di persona e
   due satelliti insieme, prima di contarlo nel piano come posto per conversazione.
