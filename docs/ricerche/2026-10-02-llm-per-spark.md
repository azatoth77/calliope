# Quale LLM sullo Spark, per la voce e per codice e documenti complessi (02/10/2026)

*Ricerca del 2 ottobre 2026. Domanda dell'utente: «Facciamo una stima di quale LLM potrebbe
funzionare meglio sullo Spark al fine di ottenere anche generazione di codice e di documenti
complessi, template compresi». Ipotesi di architettura data dall'utente: **«gemma davanti e
agenti LLM potenti dietro»**, cioè un modello piccolo e veloce sempre residente per la voce e
uno o più agenti con modelli grandi in secondo piano. Come confronto si valuta anche
l'alternativa con un solo modello.*

*Solo analisi: il codice di Calliope non è stato toccato e Calliope non è stata avviata. Gli
script di misura (`token_prompt.py`, `contesa.py`, `sonda_delega.py`) e i log sono nella
cartella temporanea della sessione (`scratchpad\llm_spark\`); i numeri essenziali sono
riportati qui. Nessun modello scaricato: si sono usati quelli già presenti in Ollama (0.35.0).
Le misure sul portatile servono a tarare le stime: lo Spark non c'è ancora, e nessuna misura
con LLM su RTX Spark è stata pubblicata.*

*Parte da [`2026-09-21-confronto-llm.md`](2026-09-21-confronto-llm.md),
[`2026-09-21-orchestrazione-agenti.md`](2026-09-21-orchestrazione-agenti.md),
[`2026-09-26-tool-e-agenti.md`](2026-09-26-tool-e-agenti.md) (arbitro),
[`2026-09-21-home-assistant-e-satelliti.md`](2026-09-21-home-assistant-e-satelliti.md) e
[`2026-10-01-biblioteca-senza-libzim.md`](2026-10-01-biblioteca-senza-libzim.md).*

*Legenda: **[M]** misurato qui, sul portatile (RTX 5070 Laptop 8 GB, Ollama 0.35.0) ·
**[V]** verificato su fonte primaria (NVIDIA, GitHub, PyPI, Hugging Face, libreria Ollama) ·
**[A]** dichiarato dal produttore del modello o dell'hardware · **[Agg]** aggregatori e blog,
attendibilità media · **[D]** mia deduzione o stima.*

## In breve

- **L'hardware.** RTX Spark (chip N1X: 20 core ARM, GPU Blackwell da 6.144 core CUDA, bus a
  256 bit) dichiara **300 GB/s** di banda [V, porting guide NVIDIA], contro i 273 GB/s del
  DGX Spark (GB10), che ha la stessa GPU. Esce a **ottobre 2026**, soprattutto in portatili
  (Surface Laptop Ultra, Dell XPS 16, ASUS ProArt, HP OmniBook, Lenovo Yoga, MSI), più
  avanti in PC compatti. La memoria arriva a 128 GB solo con la N1X; la N1 si ferma a 32 GB.
  Su Windows la GPU **non vede tutti i 128 GB**: oltre a una riserva dedicata, al massimo
  l'80 % della memoria restante, quindi circa 100 GB [D dalla porting guide].
- **Il runtime c'è**:
  - CUDA 13.4.1 per Windows ARM64 (GA a inizio settembre) [V];
  - **Ollama nativo con CUDA dalla 0.32.3** (lo zip ARM64 della 0.35.0 contiene le DLL
    `cuda_v13`) [V];
  - **llama.cpp con binari ufficiali `win-cuda-13.4-arm64`**, validati da NVIDIA su una RTX
    Spark [V];
  - WSL2 con la GPU funziona (issue NVIDIA NemoClaw #9000) [V];
  - vLLM, SGLang e TensorRT-LLM nativi su Windows: no.
  - Manca invece **faster-whisper**: ctranslate2 non ha wheel `win_arm64`, e cuDNN manca in
    CUDA 13.4. Il problema è Whisper, non l'LLM.
- **Lo Spark non rende la voce più veloce: le dà spazio.** La generazione dipende dalla banda,
  e 273–300 GB/s sono **meno** dei 384 GB/s della RTX 5070 Laptop. Sul DGX Spark:
  - gemma4 E4B genera a **63 token/s** [V], sul portatile 64–88 [M]: la prima frase della voce
    resta quella di oggi, ~0,4–0,5 s;
  - i MoE da 3–5B attivi vanno a **50–80 token/s** (gpt-oss-120b 59, gemma4 26B-A4B 53–70,
    Qwen3-Coder 30B-A3B 61) [V];
  - **i densi da 27–31B a ~11 token/s** [V]: 4.000 token di documento ≈ 6 minuti.
- **Il prompt vero di Calliope è grande** [M]: con tutti i tool e il livello «amministra»
  sono **6.176 token** (gemma4), 6.525–6.710 con i tokenizer di Llama e di Qwen; per
  l'ospite 2.286. A freddo, sullo Spark, gemma4 26B-A4B lo legge in ~2,3 s [D]. Va quindi
  tenuto in cache: elenco fisso dei tool e parti variabili in coda, come oggi.
- **«Gemma davanti» regge.** Sulla sonda nuova con il prompt e i 40 tool veri più
  `delega_lavoro`, `lavori_stato` e `lavori_annulla` [M], gemma4:e4b manda all'agente:
  - **tutti** i lavori chiari: 14 su 14 (script, pagina web, correzione di uno script,
    presentazione, relazione, business plan);
  - con la prima frase a 0,42 s di mediana;
  - **senza toccare** gli altri tool: 18 su 20 giusti;
  - due difetti: «come si scrive un ciclo for?» va all'agente (2 su 2), e una richiesta a più
    passi sui file («leggi le bollette e riassumi») parte con `pc_cerca_file`.
  - Le richieste con dati mancanti («compila il verbale con i punti di cui abbiamo parlato»)
    fanno chiedere i dati: è giusto.
  - Per confronto: gemma4:e2b 15 su 22, qwen3.5:4b 17 su 22 ma a 0,96 s.
- **La voce rallenta se un agente genera nello stesso momento** [M]:
  - **senza arbitro, con un solo slot**: la voce aspetta la fine del lavoro (**32 s**),
    o di un prefill da 8k token (**4,1 s**);
  - **due modelli in due runner**: la GPU si divide, la voce genera alla **metà della
    velocità** (88 → 41 token/s) e la prima frase passa da 0,09 a 0,21 s;
  - **stesso modello con due slot** (batching): la voce perde solo il **10 %** (88 → 80
    token/s, primo token 0,11 s), ma un prefill lungo dell'altro slot la ferma ancora per
    1,7 s.
  - Sullo Spark la banda è comune: **l'arbitro resta indispensabile**. Ferma l'agente quando
    il VAD sente parlare e lo riprende dopo; chi fa prefill lunghi li fa a pezzi di
    512–1.024 token.
- **Raccomandazione principale** [D]:
  - **davanti, `gemma4:26b-a4b-it-qat`** (16 GB, τ² 68 contro 42 di E4B [A]), se la prima
    frase sullo Spark resta sotto ~0,7 s; altrimenti `gemma4:e4b-it-qat`, che è il modello
    di oggi e il ripiego sicuro;
  - **dietro, un solo agente MoE generalista per codice e documenti, sempre residente:
    `qwen3.6:35b-a3b`** (24 GB, Apache 2.0, SWE-bench Verified 73,4 [A], ~50 token/s [D]);
  - in tutto **~50 GB residenti**, con Whisper e il resto.
  - Lo scrittore per i documenti «di qualità» (`qwen3.8:27b`, il migliore sotto i 130B per
    Artificial Analysis [V]) si carica solo a richiesta, per lavori notturni o non urgenti:
    è denso e lento.
- **Alternativa**: `gpt-oss:120b` come agente unico (65 GB, MXFP4, 55–59 token/s con
  llama.cpp [V]).
  - Pro: è il modello grande più veloce e il più pulito nelle chiamate ai tool.
  - Contro: è più debole sul codice (AA Coding Index 30 contro 54 di Qwen3.6-27B [Agg]),
    l'italiano non è dichiarato e il thinking non si spegne.
- **Un solo modello** (gemma4 26B-A4B per tutto, con il thinking acceso solo per i lavori):
  è la soluzione più semplice, ~20 GB, e la contesa è minima perché i due slot condividono
  i pesi. Ma è il più debole su codice e documenti lunghi. Va bene come primo passo sullo
  Spark, non come punto d'arrivo.
- **Prima dell'arrivo** si decidono:
  - la configurazione: **N1X con 128 GB**, e un PC che regga il servizio continuo (un
    portatile da 80–95 W acceso giorno e notte non è un server);
  - il motore di Whisper;
  - il runtime dell'agente: Ollama, oppure llama-server per l'agente (consigliato);
  - l'arbitro e il tool di delega, che si possono **scrivere e provare già oggi sul
    portatile**.

---

## 1. L'hardware: RTX Spark

### 1.1 Specifiche

| | RTX Spark N1X | RTX Spark N1 | DGX Spark GB10 (riferimento) |
|---|---|---|---|
| CPU | 20 core (10 X925 + 10 A725, Armv9.2) [V] | 18 core [Agg] | 10 X925 + 10 A725 [V] |
| GPU | Blackwell, 6.144 core CUDA, tensor core di 5ª generazione con FP4 [V] | 5.120 core CUDA [Agg] | 6.144 core CUDA [V] |
| Memoria | 24–128 GB LPDDR5X, 256 bit, **300 GB/s** [V porting guide 0.1.0] | 24–32 GB [Agg] | 128 GB LPDDR5X-8533, **273 GB/s** [V] |
| AI | «1 petaflop» FP4, con sparsità [A] | — | 1 PFLOP FP4 con sparsità [A] |
| Potenza | prototipo Surface: PL1 80 W, PL2 95 W [Agg, igor'sLAB 29/07] | fino a 80 W [Agg] | SoC 140 W [V] |
| Prezzo | nessun listino ufficiale; stime ~2.900 $ (N1X) [Agg] | ~1.800–2.000 $ [Agg] | 4.699 $ dal 23/02/2026 [V] |
| Uscita | spedizioni da ottobre 2026 (NVIDIA, 03/09) [Agg]; preordini al 02/10 non trovati | | in vendita |

Dopo il 01/10/2026 bisogna correggere due ricerche:
- la banda **è pubblicata**: la porting guide NVIDIA scrive «256 bits wide… 300 GB/s». Il
  21/09 risultava non pubblicata. Misure indipendenti (STREAM, AIDA64) non ce ne sono ancora;
- **quasi tutti i prodotti annunciati sono portatili**: ASUS ProArt P16/P14, Dell XPS 16
  Creator Edition, HP OmniBook Ultra 16, Lenovo Yoga Pro 9n, MSI Prestige N16, Surface Laptop
  Ultra. Acer (PC compatto) e Gigabyte arrivano dopo [Agg, Tom's Guide]. Per un server di casa
  sempre acceso questo conta più del modello di LLM: vedi §7.

**Memoria visibile alla GPU su Windows** [V, porting guide, capitolo UMA]. La memoria si divide in:
- una riserva **dedicata** alla GPU;
- una parte **condivisa**, pari a «memoria dopo la riserva − 16 GB», ma sempre tra il 50 % e
  l'80 % di quella memoria;
- il resto solo per la CPU.

Con 128 GB l'LLM può contare su **circa 95–105 GB** [D]. La guida sconsiglia
`cudaMallocManaged` e dice di non allocare tutto. TensorRT-RTX 1.6 segnala allocazioni che
falliscono con memoria libera (`cudaMallocAsync`). I budget di §4.4 restano quindi sotto
~80 GB di pesi e cache.

### 1.2 Runtime su Windows ARM64

| Componente | Stato al 02/10/2026 | Fonte |
|---|---|---|
| CUDA | 13.4 developer preview 16/07, **GA 13.4.1** a inizio settembre; driver ≥ 616.41 per la RTX Spark. cuDNN assente | [V] note di rilascio CUDA 13.4.1 |
| **Ollama** | CUDA su Windows ARM64 dalla **0.32.3** (23/07). Ultima stabile 0.35.0 (28/09), 0.35.1 del 29/09. Lo zip ARM64 contiene `lib/ollama/cuda_v13/ggml-cuda.dll` e un `llama-server.exe` | [V] release GitHub; zip aperto dal sotto-agente |
| **llama.cpp** | asset ufficiale «Windows arm64 (CUDA 13)», build b11337 del 02/10; NVIDIA lo cita come validato su RTX Spark (b10360) | [V] release; pagina NVIDIA «port apps» |
| MXFP4 / NVFP4 in GGUF | MXFP4 (gpt-oss) da tempo; NVFP4 da marzo–aprile 2026, kernel FP4 nativi per sm_120 dalla b8967 (29/04), correzione NVFP4 CUDA nella b11331. Ollama: nessuna nota su NVFP4; i tag `nvfp4` della libreria Ollama sono **MLX** (Apple) | [V] PR; [V] libreria Ollama |
| TensorRT for RTX | 1.6 supporta Windows on Arm su RTX Spark | [V] note di rilascio |
| TensorRT-LLM, vLLM, SGLang | **nessuna versione nativa per Windows**; vllm 0.30.0 senza wheel `win_arm64`. Solo in WSL2 aarch64, senza prove pubblicate | [V] PyPI |
| WSL2 con GPU | funziona: `nvidia-smi` sulla «RTX Spark N1X», Docker `--gpus all` PASSED | [V] NemoClaw #9000 |
| LM Studio | annunciato come supportato al lancio | [A] |
| PyTorch CUDA | wheel `win_arm64` cu134 solo dagli indici NVIDIA, nightly | [V] |
| onnxruntime | 1.30.0 `win_arm64` solo per CPU; **`onnxruntime-gpu` senza `win_arm64`** | [V] PyPI |
| ctranslate2 / faster-whisper | **nessun wheel `win_arm64`** | [V] PyPI |

**Conseguenze.**
- L'LLM ha due strade native: **Ollama** e **llama-server**. Per il principio 1, passare
  dall'uno all'altro vuol dire solo cambiare URL e backend (`ollama` o `openai`).
- vLLM e SGLang, gli unici con priorità vera tra richieste e con i motori NVFP4 più veloci,
  costerebbero WSL2: un sistema in più da tenere in piedi, contro il principio 4.
- Whisper va spostato: whisper.cpp con CUDA ARM64, oppure WSL2. Non è oggetto di questa
  ricerca, ma pesa sul budget di memoria (~1,5–2 GB).

---

## 2. Quanto va veloce

### 2.1 Misure pubblicate sul DGX Spark (GB10, Linux)

Per la RTX Spark non ci sono misure pubblicate. Con 300 contro 273 GB/s ci si aspetta al più
un +10 % in generazione, se Windows e la riserva di memoria non tolgono nulla [D].

| Modello | Quant. | Motore (fonte, data) | Prefill t/s | Generazione t/s |
|---|---|---|---|---|
| gemma4 E2B | Q8_0 | llama.cpp (shamily, 06/04/26) [V] | 8.089 (pp512) | 83,9 |
| gemma4 E4B | Q4_K_M | idem [V] | 4.696 (pp512) | **63,3** |
| **gemma4 26B-A4B** | Q4_K_M | idem [V] | 2.657–2.888 | **69,9**; con Ollama 52,7 [Agg, Exxact] |
| gemma4 31B (denso) | Q4_K_M | idem [V] | 743 | 11,0 |
| gpt-oss-20b | MXFP4 | llama.cpp ufficiale b7941 (05/02/26) [V] | 4.506 (pp2048) | 83,4 |
| **gpt-oss-120b** | MXFP4 | idem [V] | 2.444 | **58,7** (55,7 a 4k di contesto; 42,8 a 32k) |
| gpt-oss-120b | MXFP4 | Ollama 0.12.6 (blog Ollama, 23/10/25) [V] | 1.169 | 41,1 |
| Qwen3-Coder 30B-A3B | Q8_0 | llama.cpp ufficiale [V] | 2.987 | 61,1 |
| GLM-4.7-Flash 30B-A3B | Q8_0 | idem [V] | 2.364 | 48,7 (32,7 a 32k) |
| Qwen3.5-35B-A3B | Q4 | Ollama [Agg, Exxact] | — | 48,2 |
| Nemotron 3 Nano 30B-A3B | Q4 | Ollama [Agg] | — | 64,7 |
| Qwen3.5/3.6-27B (densi) | Q4_K_M | llama.cpp b8922 (25/04/26) [V] | ~820 | **11,9** |
| Qwen3.5-122B-A10B | INT4 | vLLM [Agg, forum NVIDIA] | — | 28 (51 con MTP; ~81 con DFlash) |
| Nemotron 3 Super 120B-A12B | NVFP4 | vLLM [Agg] | — | 16–23 |
| Qwen3.8-27B | NVFP4 | SGLang + spec. decoding DFlash2 [Agg] | — | 48 |

Due regole escono chiare:
1. **I MoE da 3–5B attivi generano a 50–70 token/s, i densi da 27–31B a ~11.** Per gli agenti
   su llama.cpp e Ollama servono i MoE. I densi vanno veloci solo con NVFP4 e speculative
   decoding su vLLM o SGLang, cioè in WSL2.
2. **E4B e 26B-A4B generano alla stessa velocità** (63 e 70 token/s): il 26B ha 3,8B attivi,
   E4B porta con sé le grandi tabelle di embedding per strato. Cambia il prefill: 2.700
   contro 4.700 token/s.

Lo speculative decoding sui MoE rende poco. Con Qwen3.6-35B-A3B su RTX 3090 nessuna delle 19
configurazioni batteva il riferimento; con MTP si ottiene ×1,17 sul MoE contro ×1,73 sul
denso 27B [Agg, hackmd e jarvislabs, 2026].

### 2.2 Taratura sul portatile [M]

- gemma4:e4b-it-qat genera a **64–88 token/s** sulla RTX 5070 Laptop: lo stesso modello e la
  stessa macchina danno 64 o 88 a seconda del giro (clock della GPU).
- Con 3,1 GB di pesi (`ollama ps`) fanno ~270 GB/s effettivi su 384 nominali, il 70 %.
- Sullo Spark il 70 % di 273–300 GB/s dà **~60 token/s**, coerente con i 63 misurati sul GB10.
- **La voce non sarà più veloce di oggi**: lo Spark serve a tenere residenti modelli più
  grandi, non ad accelerare quello piccolo.

### 2.3 I token del prompt di Calliope [M]

Lo script prende il corpo esatto della richiesta che `Brain` manda a Ollama (prompt di sistema
e schemi dei tool, con `Config` predefinita e PC finto) e lo rimanda a Ollama con
`num_predict=1`, per leggere `prompt_eval_count`.

| Configurazione | Livello | Tool | Caratteri | Token gemma4 | Token Qwen3.5 | Token Llama 3.1 |
|---|---|---|---|---|---|---|
| base (senza PC, documenti, casa) | ospite | 9 | 6.337 | 1.627 | — | — |
| base | familiare | 23 | 13.207 | 3.368 | — | — |
| base | amministra | 24 | 13.973 | 3.620 | — | — |
| completa (biblioteca, PC, documenti, casa, schermi) | ospite | 11 | 8.797 | 2.286 | 2.593 | 2.580 |
| completa | familiare | 38 | 22.218 | 5.735 | 6.271 | 6.119 |
| completa | amministra | 40 | 23.678 | **6.176** | **6.710** | **6.525** |

- Sul portatile, a freddo, gemma4:e4b legge i 5.735 token del familiare in 1,25 s
  (~4.600 token/s) [M].
- Sullo Spark, per i 6.200 token del prompt completo a freddo [D, dai prefill della tabella 2.1]:
  - E4B: ~1,3 s;
  - 26B-A4B: ~2,3 s;
  - gpt-oss-120b: ~2,5 s;
  - un denso da 27B: ~7,5 s.
- Con la cache del prefisso, a ogni turno si leggono solo i 100–400 token nuovi: domanda,
  memoria, risultato dei tool. Sono 0,05–0,15 s.
- **La regola «elenco fisso, parti variabili in coda» sullo Spark vale ancora di più.** Il
  messaggio dei ricordi prima della domanda e la storia vanno tenuti corti.

### 2.4 Cosa significa per la voce e per i lavori lunghi [D]

Ipotesi:
- prima frase di ~20 token;
- prefisso in cache;
- 300 token nuovi a turno;
- con un tool, due passate: la chiamata (~15 token) più la risposta.

| Ruolo e modello | Prima frase senza tool | Con un tool | Prompt a freddo (6,2k token) | Documento di 2.500 token + 1.500 di ragionamento |
|---|---|---|---|---|
| voce: gemma4 E4B | ~0,4 s (oggi sul portatile 0,40–0,51 s [M]) | ~0,65 s | ~1,3 s | — |
| voce: gemma4 26B-A4B | ~0,45 s | ~0,75 s | ~2,3 s | ~70 s (con il thinking acceso) |
| agente: Qwen3.6-35B-A3B | — | — | ~2,2 s | **~80 s** |
| agente: gpt-oss-120b (llama.cpp) | — | — | ~2,5 s | **~70 s** (Ollama ~100 s) |
| agente: Qwen3-Coder-Next 80B-A3B | — | — | non misurato | ~70–90 s (3B attivi; nessuna misura pubblicata) |
| scrittore: Qwen3.8-27B (denso) | — | — | ~7,5 s | **~5–6 min** |

- **Per la voce** solo E4B e 26B-A4B stanno nel budget di 0,5–0,7 s.
- **Per i lavori in secondo piano** vanno bene tutti, ma con pesi diversi:
  - un agente di codice fa 10–30 passate, ognuna con 1–3k token nuovi di contesto (file letti,
    output dei test);
  - con un MoE ogni passata costa 1–5 s, e un compito sta in 1–3 minuti;
  - con un denso da 27B il prefill da 800 token/s porta lo stesso compito a 10–20 minuti.
  - Il denso ha senso solo per la scrittura lunga una tantum, non per i cicli d'agente.

---

## 3. I modelli candidati (stato al 02/10/2026)

**Cosa è cambiato dopo il 21/09.**
- **Qwen3.8** (agosto) ha aperto i pesi solo del 27B denso, del Flash-Next 180B-A6B e del
  2.4T. **Non esiste un Qwen3.8 MoE medio**, per cui i MoE Qwen restano quelli della 3.6.
- gpt-oss non ha avuto successori.
- Nel frattempo sono usciti:
  - Laguna S/XS 2.1 di Poolside (luglio);
  - Nemotron 3.5 Lightning (agosto);
  - Muse Glimmer 30B di Meta (agosto);
  - Mistral Small 4 (marzo), che non è nella libreria Ollama.
- Sono troppo grandi per lo Spark: GLM-5.3 e 5.3-Flash (320B-A18B), Kimi K3, DeepSeek V4.x,
  MiniMax M3.

Tag e dimensioni della libreria Ollama ricontrollati oggi per gemma4, qwen3.6, qwen3.8,
qwen3-coder-next e laguna-xs-2.1 [V].

### 3.1 Tabella

| Modello (tag Ollama) | Uscita | Totali / attivi | Q4 su Ollama | Contesto | Licenza | Thinking spegnibile | Ruolo possibile |
|---|---|---|---|---|---|---|---|
| `gemma4:e4b-it-qat` | 04/2026 | 8B (4B effettivi) | 6,1 GB su disco, ~4,2 GiB reali [M] | 128k | Apache 2.0 | sì | voce (oggi) |
| `gemma4:26b-a4b-it-qat` | 04/2026 | 25,2B / 3,8B | **16 GB** [V] | 256k | Apache 2.0 | sì | **voce sullo Spark**; agente leggero |
| `gemma4:31b` | 04/2026 | 30,7B denso | 19–20 GB [V] | 256k | Apache 2.0 | sì | scrittore lento |
| `gemma4:12b` | 06/2026 | 12B denso | 7,7–8 GB [V] | 256k | Apache 2.0 | sì | voce intermedia (non misurato) |
| **`qwen3.6:35b`** (anche `35b-a3b-coding`) | 04/2026 | 35B / 3B | **23–24 GB** [V] | 256k | Apache 2.0 | sì | **agente unico codice + documenti** |
| `qwen3.6:27b` | 04/2026 | 27B denso | 18–19 GB [V] | 256k | Apache 2.0 | sì | scrittore lento |
| `qwen3.8:27b` | 14/08/2026 | 27B denso, multimodale | 18 GB, q8 30 GB [V] | 256k | Apache 2.0 | sì (`reasoning_effort`) | **scrittore di qualità a richiesta** |
| `qwen3-coder-next` | 02/2026 | 80B / 3B (ibrido DeltaNet) | **52 GB**, q8 85 GB [V] | 256k | Apache 2.0 [A] | non pensa | agente di codice specialista |
| `qwen3.5:122b` | 02/2026 | 122B / 10B | 81 GB [Agg] | 256k | Apache 2.0 | sì | troppo grande accanto al resto |
| **`gpt-oss:120b`** | 08/2025 | 117B / 5,1B | **65 GB** (MXFP4) | 128k | Apache 2.0 | **no** (low/medium/high) | agente generalista (alternativa) |
| `gpt-oss:20b` | 08/2025 | 21B / 3,6B | 14 GB | 128k | Apache 2.0 | no | agente leggero |
| `laguna-xs-2.1` | 07/2026 | 33B / 3B | 20 GB, q8 36 GB [V] | 256k | OpenMDW-1.1 | sì | agente di codice |
| `laguna-s-2.1` | 07/2026 | 118B / 8B | **96 GB** a q4_K_M [Agg]; NVFP4 ~66 GB solo MLX o vLLM | 1M | OpenMDW-1.1 | sì | escluso su Ollama per la memoria |
| `nemotron-3-super:120b` | 03/2026 | 120B / 12B | 87 GB [Agg] | 256k su Ollama | NVIDIA Open Model | sì | lento (16–23 t/s), italiano dichiarato |
| `glm-4.7-flash` | 01/2026 | 31B / 3B | ~19 GB [Agg] | 128k | MIT | sì | agente leggero; bug dei tool in Ollama |
| `devstral-small-2` | 12/2025 | 24B denso | ~15 GB | 256k | Apache 2.0 | — | codice, lento perché denso |
| Mistral Small 4 | 03/2026 | 119B / 6,5B | non in libreria | 256k | Apache 2.0 | sì | codice debole (AA Coding 26,6) |

### 3.2 Codice: benchmark

Quasi tutti sono **[A]**. L'unico riferimento indipendente solido è Artificial Analysis.

| Modello | SWE-bench Verified | SWE-bench Pro | LiveCodeBench v6 | AA Coding Index [Agg su dati AA, 01/10] | AA Intelligence Index v4.3 [V, 02/10] |
|---|---|---|---|---|---|
| Qwen3.8-27B | — (la scheda dà solo Pro) | 61,7 [A] | 90,3 [A] | **68,1** | **34** (primo sotto i 130B) |
| Qwen3.6-27B | 77,2 [A] | — | — | 53,7 | — |
| Qwen3.6-35B-A3B | **73,4** [A] | 49,5 [A] | 80,4 [A] | — | — |
| Qwen3.5-122B-A10B | 72,0 [A] | — | 78,9 [A] | — | — |
| Laguna XS 2.1 | 70,9 [A] | 47,6 [A] | — | — | — |
| Qwen3-Coder-Next | 70,6 [A] | 44,3 [A] | — | — | — |
| Devstral Small 2 | 68,0 [A] | — | — | — | — |
| gpt-oss-120b | 62,4 [A] (08/2025) | — | — | **30,4** | — |
| GLM-4.7-Flash | 59,2 [A] | — | — | — | — |
| Gemma 4 31B / 26B-A4B | — | 36,9 (31B) [A] | 80,0 / 77,1 [A] | 43,4 / 39,3 | — |
| Nemotron 3 Super | dati in conflitto, 46–60,5 [Agg] | — | 81,2 [A] | 37,7 | — |

- **Sul codice gpt-oss-120b è superato** dai Qwen del 2026, sia nei dati dichiarati sia
  nell'indice di AA.
- Aider polyglot è fermo dal 2025 e non serve più a confrontare i modelli del 2026.

### 3.3 Tool, istruzioni e italiano

- **τ²-bench** [A]:
  - Gemma 4: E4B 42,2, 26B-A4B 68,2, 31B 76,9;
  - Qwen3.5-122B 79,5;
  - GLM-4.7-Flash 79,5.
- **BFCL v4** lo pubblica quasi solo Qwen: 3.5-122B 72,2, 3.5-35B-A3B 67,3 [A].
- **MMMLU** (multilingue) [A]:
  - Gemma 4: E4B 76,6, 26B-A4B 86,3, 31B 88,4;
  - Qwen3.5-122B 86,7.
  - L'italiano è dichiarato esplicitamente solo da Nemotron 3 Super (e da Granite e Ministral
    tra i piccoli).
- **Scrittura lunga in italiano: nessuna misura indipendente recente.** Evalita-LLM e Calamita
  coprono modelli vecchi; EQ-Bench longform non si è potuto leggere. Il confronto va fatto in
  casa: §8.2.
- **Problemi di tool calling aperti in Ollama** [V, issue GitHub]:
  - gemma4:
    - #17562: chiamata troncata segnalata come completa;
    - #18649: rumore dopo la `}` finale;
    - #15539: chiamata come testo con `think:false`.
  - qwen3.6: **#16383** (errore 500 del parser in conversazioni lunghe, aperta dal 01/06) e
    #15857.
  - glm-4.7-flash: #13840 e #13820.
  - gpt-oss: il formato Harmony ha avuto problemi con gli output strutturati, ma oggi le sue
    chiamate ai tool sono considerate le più pulite.
  - In Ollama la `description` delle proprietà dello schema `format` viene ignorata: le
    istruzioni per lo scrittore vanno nel prompt, come già fa `scrittore.py`.
- **Osservazione nuova sul portatile** [M]: nella sonda di §4.2 (43 tool, Ollama 0.35.0)
  gemma4:e4b ha scritto **come testo 29 chiamate su 31**, e 16 su ~17 anche in streaming. Il
  26/09, con 40 tool su Ollama 0.34.x, erano 49 su 101. `TextCallGuard` le recupera, ma
  conviene rilanciare `prova_tool_scala.py` per capire se è un peggioramento della 0.35 o
  l'effetto dei tre tool in più. qwen3.5:4b non ne scrive mai come testo.

---

## 4. Architettura: «gemma davanti, agenti dietro»

```
microfono → VAD → STT → wake word → FRONT-END gemma4 (sempre residente, thinking spento)
                                       │  tool veloci (ora, casa, liste, PC, documento_crea…)
                                       │  delega_lavoro(tipo, compito, formato) ──┐
                                       ▼                                          ▼
                                     TTS ◄── annuncio a lavoro finito ◄── AGENTE (MoE grande,
                                                                         thinking acceso,
                                       ARBITRO: la voce prima di tutto   in secondo piano)
                                       (ferma l'agente quando il VAD     ├ codice (sandbox)
                                        sente parlare, lo riprende dopo) ├ documenti / template
                                                                         └ ricerche a più passi
```

### 4.1 Il front-end: quale gemma

| Variante | Memoria | Prima frase sullo Spark [D] | Tool (τ² [A]) | Pro | Contro |
|---|---|---|---|---|---|
| `gemma4:e4b-it-qat` (oggi) | ~4,2 GiB [M] | ~0,4 s; ~0,65 s con un tool | 42,2 | misurato a fondo; tutte le prove passano; prompt a freddo 1,3 s | ragiona poco; «museI»; molte chiamate scritte come testo |
| `gemma4:12b` | ~8–9 GB | ~0,5 s (denso da 12B: ~25 t/s [D]) | — | italiano probabilmente migliore | denso: genera a metà velocità; nessun dato sui tool |
| **`gemma4:26b-a4b-it-qat`** | 16 GB + 1–2 GB di contesto | ~0,45 s; ~0,75 s con un tool | **68,2** | stessa velocità di generazione di E4B, ragiona molto meglio; può fare anche da agente leggero con il thinking acceso | prefill a metà (2,3 s a freddo); va misurato con le prove vere |
| `gemma4:31b` | ~20 GB | ~2 s | 76,9 | il migliore dei Gemma | 11 token/s: escluso per la voce |

- **Consiglio**: arrivati sullo Spark si provano E4B e 26B-A4B con lo **stesso banco**.
- Si sceglie 26B-A4B se la mediana della prima frase con un tool resta ≤ 0,7 s e il p90
  ≤ 1,0 s. Altrimenti resta E4B.
- La famiglia non cambia: stesso renderer, stessi difetti noti, stesso `TextCallGuard`.
  Cambiano solo nome e memoria (principio 1).

### 4.2 Come il front-end passa il lavoro a un agente

**Sonda misurata** [M] (`sonda_delega.py`):
- il prompt di sistema e i 40 tool **veri** di Calliope, livello amministra;
- in più tre tool finti:
  - `delega_lavoro(tipo: codice|documento|ricerca, compito, formato?)`;
  - `lavori_stato`;
  - `lavori_annulla`;
- una riga in fondo al prompt: «Per i lavori lunghi (programmi e script, presentazioni,
  relazioni, documenti da un modello, ricerche a più passi) chiama delega_lavoro»;
- 22 frasi, 2 giri.

| Gruppo di frasi | gemma4:e4b (2 giri) | gemma4:e2b (1 giro) | qwen3.5:4b (1 giro) |
|---|---|---|---|
| codice chiaro (script, programma, correzione, pagina web) | **8/8**, con `tipo=codice` e formato giusto | 2/4 | 2/4 |
| documenti complessi (presentazione, relazione, business plan) | **6/6**, con `tipo=documento` e formato (powerpoint, word) | 3/3 | 3/3 |
| «compila il modello del verbale con i punti di cui abbiamo parlato», «usa il template della carta intestata e fammi il preventivo» | 0/4 delegati: in 3 casi chiede i dati che mancano (giusto), in 1 usa `documento_crea` | 0/2 | 0/2 (chiede i dati, oppure «non posso») |
| «leggi le bollette dell'ultimo anno e fammi un riassunto» | 0/2: parte con `pc_cerca_file` | 0/1 | 0/1 (`pc_cerca_file`) |
| stato e annullo dei lavori | 3/4 (una volta «lavoris_annulla» scritto come testo) | 1/2 | 2/2 |
| tool di sempre (ora, luce, calcolo, timer, lista, lettera in PDF, tabella Excel) | 14/14 | 5/7 | 7/7 |
| conversazione (saluto, «cos'è una funzione ricorsiva in due parole») | 4/4 | 2/2 | 2/2 |
| «come si scrive un ciclo for in Python, in breve?» (da **non** delegare) | **delegato 2/2** | 1/1 giusto | 1/1 giusto |
| prima frase o chiamata, mediana (p90) | **0,42 s (0,53)** | 0,23 s (0,40) | 0,96 s (1,72) |

**Che cosa se ne ricava.**
- **Un E4B sa riconoscere un lavoro lungo e scriverne il compito strutturato** senza perdere
  precisione sugli altri tool.
- Ci sono due limiti, e nessuno dei due chiede un modello più grande:
  1. troppa delega sulle domande brevi di programmazione;
  2. le richieste a più passi sui file partono dal primo passo invece che dall'agente.
- Si correggono con la descrizione del tool («solo se il risultato è un file o un programma;
  una spiegazione a voce la dai tu») e con una regola nel codice: se `pc_cerca_file` è chiamato
  con «riassumi / confronta / leggi tutte» nella frase, si propone la delega.
- I template con dati mancanti fanno chiedere i dati. È il comportamento voluto: l'agente
  deve partire con tutto ciò che gli serve.

**Proposta per il tool di delega** [D]. Ricalca ciò che già funziona per i documenti
(`risposta_finale`, `Documenti.done` + `due_event`, `Speaker.chime`,
`Brain.record_announcement`) e per le installazioni (proposta → «sì» → avvio):

1. `delega_lavoro(tipo, compito, formato?, file?)`:
   - `compito` è la frase detta, completata dai dati che il front-end conosce: chi chiede,
     l'ultimo documento, l'ultima ricerca di file;
   - **il front-end non scrive mai il contenuto**: lo scrive l'agente, come oggi lo scrittore
     dei documenti.
2. **Permessi nel codice, non nel prompt**:
   - delega solo dai familiari in su;
   - `tipo=codice` con esecuzione solo per chi amministra;
   - per tutti, l'agente vede solo la propria cartella di lavoro.
3. **Conferma a voce solo se il lavoro è costoso o ambiguo**:
   - il tool risponde con `risposta_finale`, per esempio «Ci lavoro, ci vorrà qualche minuto.
     Ti avviso quando è pronto.», senza un'altra passata del modello;
   - chiede conferma se il lavoro è stimato oltre ~10 minuti, se deve caricare un modello non
     residente («devo preparare lo scrittore, ci vuole un minuto in più: procedo?») o se c'è
     già un lavoro in corso. Altrimenti parte e basta.
4. **Domande dell'agente**:
   - se all'agente mancano dati, il lavoro si ferma in stato «in attesa»;
   - la domanda viene annunciata come un risultato: «Per il preventivo mi servono le voci e
     gli importi: me li dici?»;
   - la risposta torna all'agente con `lavori_rispondi`.
5. **Avviso a lavoro finito**:
   - si annuncia solo quando c'è silenzio, come in LiveKit Agents e Pipecat [V, docs
     2026] e come i documenti di oggi;
   - l'annuncio entra nella storia, così «aprilo» e «leggimi il riassunto» funzionano.
6. **Altri tool**: `lavori_stato` («a che punto è?»: passo corrente e stima) e
   `lavori_annulla`. Un solo lavoro per persona alla volta; gli altri vanno in coda.

### 4.3 Quale modello per l'agente: generalista o specialisti?

| Opzione | Modelli | Memoria | Pro | Contro |
|---|---|---|---|---|
| **A. Un MoE medio generalista** (consigliata) | `qwen3.6:35b` (o la variante `-coding`) | ~24 GB + cache | SWE-V 73,4 [A], 201 lingue [A], ~50 t/s, Apache; codice, documenti e ricerche con lo stesso modello; sempre residente | Il bug #16383 dei tool in Ollama; l'italiano lungo è da misurare |
| B. Un MoE grande generalista | `gpt-oss:120b` | ~65 GB + cache | il più veloce dei grandi (59 t/s), chiamate ai tool pulite, molto usato | codice superato (AA Coding 30); italiano non dichiarato; thinking sempre acceso; lascia poco spazio |
| C. Specialisti | codice `qwen3-coder-next` (52 GB) o `laguna-xs-2.1` (20 GB); scrittura `qwen3.8:27b` (18 GB) | 40–75 GB | il meglio per ciascun lavoro | più modelli da caricare; il 27B denso è lento; più casi da provare |
| D. Il front-end anche come agente | `gemma4:26b-a4b` con il thinking acceso in un secondo slot | 0 GB in più | nessuna memoria in più; il batching dei due slot costa alla voce solo il 10 % [M] | il più debole su codice e documenti (AA Coding 39) |

**Raccomandazione** [D]: **A come agente di base**, sempre residente. La qualità «di punta»
viene da `qwen3.8:27b`, caricato a richiesta per i documenti importanti o di notte: il codice
gli chiede la qualità più alta e accetta 5–10 minuti.
- **Specialisti di codice** (Coder-Next, Laguna XS) solo se il banco di §8.2 mostra un
  distacco netto rispetto a Qwen3.6-35B. Sui dati dichiarati sono allo stesso livello (SWE-V
  70,6 e 70,9 contro 73,4).
- **gpt-oss-120b** è l'alternativa se Qwen3.6 dà problemi di tool o di JSON che il runtime
  non risolve.

### 4.4 Memoria e caricamento

**Budget su 128 GB** [D], con circa 95–105 GB visibili alla GPU (§1.1):

| Voce | Oggi (portatile) | Spark, raccomandazione | Spark, alternativa gpt-oss |
|---|---|---|---|
| Windows, app, browser, servizi | ~10–14 GB RAM | ~14 GB | ~14 GB |
| Front-end | E4B ~4,2 GiB | 26B-A4B QAT 16 GB + ~2 GB di contesto (16k) | idem |
| Agente | — | Qwen3.6-35B q4 24 GB + ~3–5 GB di contesto (64k) | gpt-oss-120b 65 GB + ~3 GB (64k, finestra scorrevole) |
| Scrittore a richiesta | — | Qwen3.8-27B 18 GB + ~4 GB (32k) | — (non ci sta comodo) |
| Whisper large-v3-turbo | ~0,8 GiB (CTranslate2) | ~1,5–2 GB (whisper.cpp o WSL2) | idem |
| bge-m3 (se il recupero dei tool si accende) | — | ~1,2 GB | idem |
| Piper, VAD, wake word, chi parla | CPU, <0,5 GB | idem | idem |
| Biblioteca (FTS5 + ZIM) e mappe (PMTiles, SQLite) | su disco, mmap | 5–10 GB di cache dei file, utili ma non obbligatori | idem |
| **Totale residente** | ~7,5 GB di VRAM | **~65 GB, ~90 GB con lo scrittore** | **~100 GB: al limite** |

**Tempi di caricamento.**
- Sul portatile [M]: qwen3:8b (5,2 GB) si carica in **4,1 s a freddo** e 2,4 s dalla cache dei
  file; llama3.1:8b (4,9 GB) in 3,9 s. Sono ~1,2–2,2 GB/s effettivi, CUDA compreso.
- La velocità degli SSD dei prodotti RTX Spark non è pubblicata. Al ritmo del portatile [D]:
  - 24 GB: ~12–20 s;
  - 52 GB: ~25–45 s;
  - 65 GB: ~30–55 s.
- **Ciò che serve spesso resta residente**, con `keep_alive: -1` e
  `OLLAMA_MAX_LOADED_MODELS` ≥ 3. Lo scrittore a richiesta costa mezzo minuto: va bene per un
  lavoro di minuti, purché il codice lo dica a voce.
- Attenzione: su GB10 è stato segnalato Ollama che scarica e ricarica un modello nonostante
  `keep_alive` [Agg]. **Ricordarsi di fissare `OLLAMA_CONTEXT_LENGTH`**: oltre 48 GiB il
  predefinito diventa 256k (ricerca del 21/09).
- **Contesto lungo per i documenti**: i modelli Qwen3.6/3.8 e Gemma 4 arrivano a 256k [V], ma
  i lavori conviene tenerli entro 32–64k e procedere a pezzi:
  - la velocità cala con il contesto (gpt-oss-120b da 58,7 a 42,8 t/s tra 0 e 32k [V]);
  - il prefill lungo è ciò che l'arbitro non può interrompere (§4.5).

### 4.5 L'arbitro: la voce prima di tutto

**Misure sul portatile** [M] (`contesa.py`). Voce: gemma4:e4b con un prefisso di ~1,5k token
in cache e 5 domande da 80 token. Sfondo: una relazione di 3.000 token, poi un prompt
**nuovo** di 8.195 token.

| Scenario | Voce da sola: primo token / token al s | Voce con lo sfondo che genera: primo token (max) / token al s | Sfondo: token al s da solo → durante | Voce durante un prefill nuovo di 8k token |
|---|---|---|---|---|
| A. stesso modello, **1 slot** (Calliope oggi, nessun arbitro) | 0,12 s / 64 | **32,0 s** la prima: aspetta la fine dello sfondo | 68 → 84 | **4,13 s** |
| B. stesso modello, **2 slot** (`OLLAMA_NUM_PARALLEL=2`) | 0,09 s / 89 | **0,11 s (0,13)** / 80 (**−10 %**) | 92 → 85 | **1,71 s** |
| C. **due modelli** in due runner (sfondo: qwen2.5-coder 1,5B) | 0,09 s / 88 | **0,21 s (0,24)** / 41 (**−54 %**) | 237 → 156 | **0,27 s** |
| arbitro che chiude lo stream (misura del 26/09) | 0,30 s | **0,27 s** | ripresa: primo token 0,12 s | ~2,2 s (il prefill non si interrompe) |

Nota: la velocità della voce da sola cambia tra un giro e l'altro (64 contro 88 token/s) per
il clock della GPU. I confronti valgono all'interno della stessa riga.

**Che cosa significa** [D]:
- **Due modelli diversi si dividono la GPU a tempo.** Mentre l'agente genera, la voce va a
  circa metà velocità e la prima frase si allunga di 0,1–0,3 s. Un prefill dell'altro modello
  invece la blocca poco (0,27 s). Sullo Spark l'agente è più grosso dello sfondo provato qui,
  quindi la perdita può essere maggiore: va misurata là.
- **Due slot dello stesso modello costano quasi nulla in generazione**, perché il batching
  legge i pesi una volta per due sequenze. Un prefill lungo però li ferma comunque: llama.cpp
  issue #29175 (20/09) dice che un blocco di prefill ferma il decode di **tutti** gli slot,
  per ceil(prompt / n_batch) blocchi [V].
- **Nessun runtime nativo per Windows ha la priorità per richiesta**: né Ollama né
  llama-server. Solo vLLM e SGLang, e solo su Linux. I green context di CUDA (13.1+)
  valgono dentro un solo processo, e nessun runtime pubblico li espone [V]. L'arbitro va
  quindi scritto in Calliope.

**Progetto dell'arbitro** [D], sopra `Brain`, dove si chiudono gli stream:
1. Front-end e agente su **runtime separati**:
   - **Ollama per la voce** (backend `ollama` di oggi);
   - **llama-server per l'agente** (backend `openai`, già nel codice), con `-b`/`-ub` piccoli
     (512) così ogni blocco di prefill dura ~0,2 s;
   - così il bug #16383 di qwen3.6 nel parser di Ollama non si tocca (llama-server con
     `--jinja`), e un prefill dell'agente non ferma il decode della voce (scenario C).
2. **All'inizio del parlato rilevato dal VAD**, non quando arriva la trascrizione, l'arbitro
   **chiude lo stream dell'agente**: la generazione si ferma davvero (misurato il 26/09).
   L'STT dà 0,5–2 s di margine.
3. Finita la risposta della voce, e dopo `followup_s` di silenzio, l'agente riparte:
   - dalla cache del prefisso, mandando il testo già scritto come messaggio assistant da
     continuare (da verificare con Qwen3.6);
   - oppure con `/slots/{id}?action=save|restore` di llama-server.
4. I lavori leggono a pezzi: al massimo 1.000–1.500 token nuovi per richiesta, e un pezzo
   nuovo parte solo se il VAD non sente parlare (regola del 26/09).
5. Se si sceglie l'opzione D (stesso modello in due slot), l'arbitro serve solo per i
   prefill, e la voce non perde quasi nulla in generazione.

### 4.6 Thinking

- **Voce: spento**, come oggi. Il 26/09 il thinking dava il 100 % di tool giusti ma con la
  prima frase a 4 s.
- **Agenti: acceso**, a livello medio:
  - per il codice serve davvero (i benchmark dichiarati sono tutti con il ragionamento);
  - per i documenti aiuta la struttura;
  - gpt-oss non lo spegne in nessun caso.
- **Output strutturati con il thinking**: Ollama 0.34.4 applica `format` in una sola passata
  anche ai modelli che ragionano [V]. Resta però segnalato il JSON che finisce in
  `reasoning_content` [Agg]. Due vie:
  - con llama-server, `json_schema` sulla risposta finale;
  - oppure due passate: il modello ragiona e scrive una bozza libera, poi una seconda
    richiesta con lo schema e senza thinking la trasforma in JSON.
  - Per schemi grandi conviene comunque **un pezzo per volta** (una sezione o una tabella per
    richiesta). La grammatica di llama.cpp non supporta `$ref` annidati né `anyOf` insieme a
    `properties` nello stesso tipo, e ignora in silenzio ciò che non capisce [V].

### 4.7 Documenti complessi e template: come, in pratica

Il modello grande non deve **produrre il file**, ma **riempire uno schema**. È lo stesso
principio di `calliope/documenti/`, già misurato.
- **Template Word**: un `.docx` con segnaposto Jinja (`docxtpl`, puro Python; lxml ha il
  wheel `win_arm64` [V]).
  1. Calliope estrae dal template l'elenco dei campi e ne costruisce lo schema JSON;
  2. il modello riempie lo schema dai dati detti e dai file indicati;
  3. si fa la validazione (campi obbligatori, cifre, niente dati inventati: i segnaposto
     `[…]` come oggi);
  4. si genera il file.
  - Carta intestata, verbale di condominio e preventivo diventano tutti così. Il modello non
    tocca mai la formattazione.
- **Presentazioni**: `python-pptx` (puro Python; l'ultima versione è dell'08/2024) con un
  master `.pptx`. Lo schema dice «diapositive: titolo, punti, note, immagine facoltativa». Il
  modello scrive una scaletta, poi una diapositiva per richiesta.
- **Relazioni lunghe**: prima l'indice (JSON), poi una sezione per richiesta con l'indice e
  le sezioni precedenti riassunte nel contesto, poi la revisione finale. Ogni pezzo è un punto
  in cui l'arbitro può fermare il lavoro.
- **Codice**: un ciclo d'agente scritto in proprio (come `Brain`) con 4–5 tool:
  `leggi_file`, `scrivi_file`, `esegui` (Python o PowerShell in sottoprocesso, con tempo
  massimo, senza rete, nella cartella di lavoro), `test`, `consegna`.
  - Il codice si **esegue solo nella cartella del lavoro** e solo per chi amministra.
  - Gli agenti di codice già pronti non vanno bene così come sono [V]:
    - mini-swe-agent dipende da LiteLLM, bloccato su ARM;
    - OpenHands vuole Docker;
    - opencode vuole 64k di contesto e si rompe in silenzio quando è pieno;
    - Codex CLI `--oss` e Goose sono binari Rust: l'ARM64 per Windows è da verificare.

### 4.8 Framework per gli agenti

Situazione su PyPI il 02/10 [V]:
- **`cryptography` 50.0.2 non ha ancora wheel `win_arm64`**, e nemmeno `tiktoken` e
  `litellm` (tramite `fastuuid`).
- Hanno dipendenze di base tutte compatibili con ARM64:
  - `pydantic-ai-slim` 2.53.0;
  - `agent-framework-core` 1.19.0;
  - `agno` 3.1.0;
  - `langgraph` 1.2.12.
- **Consiglio** [D]: nessun framework. Il ciclo con i tool c'è già in `Brain`, e il pezzo
  difficile, l'arbitro, nessun framework lo modella (stessa conclusione del 21/09). Se un
  giorno servisse un framework, `pydantic-ai-slim` è il più leggero.

### 4.9 Confronto con «un solo modello»

| | Gemma davanti + agente Qwen3.6-35B (raccomandata) | Un solo modello (gemma4 26B-A4B, due slot) | Un solo modello grande (gpt-oss-120b anche per la voce) |
|---|---|---|---|
| Prima frase della voce | ~0,45–0,75 s [D] | uguale | ~0,6–1,0 s [D]; thinking non spegnibile («low») |
| Qualità su codice e documenti | buona (SWE-V 73 [A]) | media (AA Coding 39) | media sul codice, buona sui tool |
| Memoria | ~65 GB | ~20 GB | ~70 GB |
| Contesa | due runtime: la voce a metà velocità se l'agente non viene fermato; serve l'arbitro | batching: −10 %; restano i prefill | stesso modello, come la colonna a sinistra |
| Complessità | due runtime, due modelli | minima | minima, ma la voce peggiora |

---

## 5. Misure sul portatile in dettaglio

- **Token del prompt**: tabella §2.3. Script `token_prompt.py`.
- **Contesa**: tabella §4.5. Script `contesa.py`.
  - Gli scenari B e C sono girati su un **secondo server Ollama temporaneo** (porta 11435,
    `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_MAX_LOADED_MODELS=2`), fermato alla fine.
  - Il server Ollama dell'utente non è stato riconfigurato.
- **Delega**: tabella §4.2. Script `sonda_delega.py` e `sonda_delega_stream.py`; in streaming
  gemma4:e4b fa 19 su 22 con gli stessi errori.
- **Caricamento**: §4.4.
- Le prove esistenti `prova_casa.py`, `prova_pc_ollama.py` e `prova_documenti_ollama.py`
  **non sono state rilanciate**:
  - i candidati per la voce che stanno in 8 GB (E4B, E2B, qwen3.5:4b, qwen3:8b) sono già
    stati misurati il 21 e il 26/09;
  - quelli che contano per lo Spark (26B-A4B e gli agenti) non entrano nel portatile.
  - Nota: il modello non si cambia con una variabile d'ambiente. `ENV_OVERRIDES` non ha
    `llm_model`; si usa un `calliope.locale.yaml` di prova puntato con
    `CALLIOPE_CONFIG_LOCALE`, con `llm: {llm_model: …}`.
- Nessun download; nessun modello cancellato; GPU libera alla fine (~0,9 GB occupati dal
  desktop).

---

## 6. Rischi e incognite

1. **Runtime su Windows ARM64**:
   - Ollama e llama.cpp esistono e sono validati da NVIDIA, ma sui prototipi si sono visti
     carichi CUDA che non arrivano alla fine e blocchi dopo circa un'ora (driver 616.33,
     igor'sLAB 29/07) [Agg];
   - nessuna misura di LLM su RTX Spark sotto Windows è pubblicata;
   - i driver WDDM e la riserva di memoria potrebbero togliere qualcosa rispetto al DGX Spark
     su Linux.
2. **Memoria visibile alla GPU**: la formula della porting guide dà ~95–105 GB su 128 [D].
   Ogni budget va rifatto con `nvidia-smi`, che sul portatile si è già rivelato più affidabile
   di `ollama ps` (sottostima di ~1 GiB per i Gemma).
3. **Quantizzazioni**: MXFP4 (gpt-oss) è maturo. NVFP4 in llama.cpp è recente: da aprile, con
   correzioni ancora il 02/10. I tag `nvfp4` della libreria Ollama sono per MLX. Sullo Spark,
   con Ollama, si resta su Q4_K_M, QAT e MXFP4.
4. **Qualità in italiano**: nessun benchmark indipendente recente; solo MMMLU dichiarati. Le
   «parole malformate» di E4B sul 26B-A4B sono da verificare, come la scrittura lunga di
   Qwen3.6 e 3.8.
5. **Benchmark di codice quasi tutti [A]**. Solo l'indice di AA è indipendente. Molti
   aggregatori del 2026 si contraddicono (Nemotron 3 Super: SWE-V 46 o 60,5).
6. **Tool calling in Ollama**: issue aperte per gemma4 e qwen3.6 (§3.3). In più il numero di
   chiamate scritte come testo da E4B misurato oggi è molto alto. `TextCallGuard` resta
   indispensabile; per l'agente, llama-server con `--jinja`.
7. **Le stime di velocità sono [D]**: vengono dal DGX Spark (Linux, llama.cpp), non dalla
   RTX Spark con Windows. La contesa tra due runner è stata misurata sul portatile con uno
   sfondo minuscolo.
8. **La forma del prodotto**: un portatile da 80–95 W acceso giorno e notte come server di
   casa (calore, batteria sempre in carica, ventole) non è stato considerato nella visione.
9. **Whisper**: senza ctranslate2 né cuDNN su ARM64 serve un altro motore. È un rischio di
   latenza della voce, non dell'LLM.

---

## 7. Cosa decidere prima dell'acquisto o dell'arrivo

1. **Configurazione**:
   - N1X con 128 GB: con 32 GB, l'unica possibile sulla N1, il piano si riduce all'opzione D;
   - un prodotto adatto a stare sempre acceso: se possibile il PC compatto, non un portatile;
   - SSD veloce, per i caricamenti a richiesta.
2. **Runtime**: Ollama per la voce e **llama-server per l'agente** (consigliato), oppure tutto
   su Ollama. Entrambi sono già coperti dai backend `ollama` e `openai` (principio 1).
   Niente WSL2 per l'LLM, salvo che il banco dimostri un guadagno decisivo di vLLM con NVFP4.
3. **Motore di Whisper** sullo Spark (whisper.cpp CUDA o WSL2), con la sua quota di memoria.
4. **Da fare già sul portatile**, senza aspettare lo Spark:
   - l'**arbitro** (VAD → chiusura dello stream dell'agente → ripresa);
   - il tool **`delega_lavoro`** con stato, annullo, domande e annuncio;
   - il **ciclo dell'agente** per documenti e template (docxtpl, python-pptx).
   - Sul portatile l'«agente» può essere lo stesso E4B, oppure E2B in un secondo runner: i
     risultati saranno modesti, ma il meccanismo si prova tutto.
5. **Stabilire le soglie del banco prima di provarlo** (§8.2), come per la biblioteca, per non
   tarare sui risultati.

---

## 8. Raccomandazione

### 8.1 Principale e alternativa

- **Principale**:
  - **front-end `gemma4:26b-a4b-it-qat`**, sempre residente, thinking spento, con
    `gemma4:e4b-it-qat` come ripiego se la latenza non regge;
  - **agente unico `qwen3.6:35b`** (o `35b-a3b-coding`), sempre residente, thinking acceso,
    servito da llama-server;
  - **`qwen3.8:27b` a richiesta** per i documenti di qualità.
  - Memoria residente ~65 GB, ~90 GB con lo scrittore.
- **Alternativa**: stesso front-end, con **`gpt-oss:120b`** come agente unico (65 GB). È più
  veloce e più robusto sui tool, più debole sul codice; non lascia spazio per lo scrittore.
- **Primo passo minimo** (opzione D): solo `gemma4:26b-a4b` con due slot, thinking acceso per
  i lavori. Serve a mettere in funzione delega e arbitro dal primo giorno, e a misurare quanto
  manca.

### 8.2 Cosa provare per primo e con quale banco

**Ordine dei modelli**:
1. `gemma4:e4b-it-qat` (riferimento);
2. `gemma4:26b-a4b-it-qat`;
3. `qwen3.6:35b`;
4. `gpt-oss:120b`;
5. `qwen3.8:27b`;
6. se il codice delude, `qwen3-coder-next` e `laguna-xs-2.1`.

**Banco della voce** (esiste già), per E4B e 26B-A4B:
- `prove/prova_casa.py`, `prova_pc_ollama.py`, `prova_documenti_ollama.py`,
  `prova_casa_ha_ollama.py`, `prova_stato_ollama.py`, `prova_schermi_ollama.py` e
  `prova_tool_scala.py` (119 richieste, 40 tool);
- soglie: risultati non peggiori di E4B; prima frase con tool mediana ≤ 0,7 s, p90 ≤ 1,0 s;
  prompt a freddo ≤ 3 s; memoria reale da `nvidia-smi`;
- in più la sonda di delega di questa ricerca, portata in `prove/` con le 22 frasi e altre
  10 nuove.

**Banco nuovo «lavori»** (`prove/prova_lavori.py`, da scrivere), per gli agenti:
- **Codice, 12 compiti** con test già scritti, che decidono da soli:
  - script Python sui file (rinomina per data EXIF, deduplica, CSV → Excel);
  - uno script PowerShell;
  - una pagina web statica (lista della spesa);
  - correzione di un bug in un file dato;
  - aggiunta di una funzione a un modulo con test esistenti;
  - un piccolo tool di Calliope (schema + funzione).
  - Misure: test superati al primo colpo e dopo il ciclo, passate, token, minuti.
- **Documenti, 12 compiti**:
  - relazione di 4–6 sezioni da dati dati;
  - presentazione di 8–10 diapositive (schema JSON → pptx);
  - **3 template** (`docxtpl`): verbale di condominio, preventivo su carta intestata,
    curriculum. Ogni template ha un elenco di campi, con dati completi o con dati mancanti:
    l'agente deve chiedere, non inventare;
  - una lettera formale lunga;
  - un business plan con tabella e totali calcolati dal programma.
  - Misure:
    - schema valido;
    - dati detti presenti al 100 %;
    - nessun dato inventato (segnaposto `[…]`);
    - lunghezza;
    - italiano giudicato su una scala fissa da una persona (Dario), con un LLM giudice solo
      come prefiltro;
    - minuti.
- **Contesa**: la prima frase di `prova_casa.py` misurata **mentre** un lavoro del banco gira,
  con e senza arbitro, e con l'agente in un secondo runner o in un secondo slot. Soglia: con
  l'arbitro, prima frase al massimo +0,15 s rispetto alla voce da sola.

### 8.3 Fonti principali (consultate il 02/10/2026)

- NVIDIA:
  - RTX Spark Porting Guide 0.1.0:
    [overview](https://docs.nvidia.com/rtx-spark/rtx-spark-porting-guide/0.1.0/overview.html),
    [UMA](https://docs.nvidia.com/rtx-spark/rtx-spark-porting-guide/0.1.0/uma/index.html);
  - [comunicato del 31/05](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-and-Microsoft-Reinvent-Windows-PCs-for-the-Age-of-Personal-AI/default.aspx);
  - [note di rilascio CUDA 13.4.1](https://docs.nvidia.com/cuda/archive/13.4.1/cuda-toolkit-release-notes/index.html);
  - [TensorRT-RTX 1.6](https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/getting-started/release-notes-1/1.6.html);
  - [hardware del DGX Spark](https://docs.nvidia.com/dgx/dgx-spark/hardware.html);
  - [port apps](https://developer.nvidia.com/topics/ai/local-ai/port-apps);
  - [NemoClaw #9000 (WSL2)](https://github.com/NVIDIA/NemoClaw/issues/9000).
- Misure sul DGX Spark:
  - [llama.cpp benches/dgx-spark](https://github.com/ggml-org/llama.cpp/blob/master/benches/dgx-spark/dgx-spark.md);
  - [Gemma 4 su DGX Spark (shamily)](https://github.com/shamily/gemma4-llama-dgx-spark);
  - [densi 27B/31B (nabe2030)](https://github.com/nabe2030/dense-27b-31b-dgx-spark);
  - [blog Ollama](https://ollama.com/blog/nvidia-spark-performance);
  - [tokenstead, 19/08](https://tokenstead.ai/guides/dgx-spark-benchmarks-2026);
  - [igor'sLAB, prototipo Surface](https://www.igorslab.de/en/surface-laptop-ultra-rtx-spark-prototype-early-performance-software-issues/).
- Runtime:
  - [Ollama: release](https://github.com/ollama/ollama/releases), [FAQ](https://docs.ollama.com/faq);
  - issue Ollama
    [#16383](https://github.com/ollama/ollama/issues/16383),
    [#17562](https://github.com/ollama/ollama/issues/17562),
    [#18649](https://github.com/ollama/ollama/issues/18649);
  - [llama.cpp: release](https://github.com/ggml-org/llama.cpp/releases),
    [README del server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
    [grammatiche](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md),
    [#29175](https://github.com/ggml-org/llama.cpp/issues/29175);
  - [AgentServe, arXiv 2603.10342](https://arxiv.org/html/2603.10342).
- Modelli:
  - libreria Ollama, tag ricontrollati:
    [gemma4](https://ollama.com/library/gemma4/tags),
    [qwen3.6](https://ollama.com/library/qwen3.6/tags),
    [qwen3.8](https://ollama.com/library/qwen3.8/tags),
    [qwen3-coder-next](https://ollama.com/library/qwen3-coder-next),
    [laguna-xs-2.1](https://ollama.com/library/laguna-xs-2.1/tags);
  - schede HF:
    [Qwen3.5-122B-A10B](https://huggingface.co/Qwen/Qwen3.5-122B-A10B),
    [Gemma 4 26B-A4B](https://huggingface.co/google/gemma-4-26B-A4B-it),
    [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B);
  - [Artificial Analysis, modelli aperti](https://artificialanalysis.ai/models/open-source);
  - [AA Coding Index su BenchLM](https://benchlm.ai/benchmarks/aacodingindex).
- Agenti e voce:
  - [Pipecat, function calling](https://docs.pipecat.ai/pipecat/learn/function-calling);
  - [LiveKit async tools](https://docs.livekit.io/agents/logic/tools/async/);
  - [OpenHands con modelli locali](https://docs.openhands.dev/openhands/usage/llms/local-llms).
