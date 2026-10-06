# Calliope — orchestrazione di più agenti in locale: stato al 21 settembre 2026

*Ricerca svolta da un agente il 21 settembre 2026 per la decisione C di docs/visione.md.*

**Metodo.**
- Ho ripartito la ricerca web su tre sotto-agenti: framework, Ollama e runtime, modelli.
- Ho coperto io MCP, gli schemi per la voce e lo strato fatto in casa.
- Versioni e date dei framework vengono dalle API JSON di PyPI e GitHub.
- Molte altre pagine sono state lette tramite WebFetch, che riassume con un modello piccolo. Qualche cifra può contenere errori di trascrizione e va ricontrollata sulla fonte prima di basarci una decisione.
- Nessun test su hardware.

---

## 0. Sintesi

- **Raccomandazione:**
  - Strato proprio, circa 450–550 righe, sopra il client `openai`.
  - MCP come confine dei tool.
  - Nessun framework nel percorso vocale.
  - Piano B solo per gli agenti in secondo piano: Pydantic AI slim oppure Microsoft Agent Framework (pacchetti core + openai).
- **Motivo principale:**
  - Il problema centrale di Calliope è far passare una richiesta vocale urgente davanti a un lavoro in secondo piano sulla stessa GPU.
  - Nessun framework lo risolve.
  - Nessun server disponibile su Windows lo risolve: Ollama e llama-server hanno coda FIFO, senza priorità né preemption.
  - La priorità va quindi scritta nel client in ogni caso.
- **Sorprese:**
  1. Dalla v0.30 Ollama lancia `llama-server` di llama.cpp come sottoprocesso.
  2. Ollama forza `numParallel=1` per alcune famiglie di modelli, tra cui qwen3.5, qwen3-next, lfm2 e nemotron_h. Due agenti sullo stesso modello vengono serializzati.
  3. `cryptography` non ha più wheel per Windows ARM64 dalla 46.0.4. Il pacchetto `mcp` la richiede, tramite `pyjwt[crypto]`. Ogni framework con `mcp` obbligatorio eredita il blocco.
  4. `tiktoken` e `grpcio` non hanno mai avuto wheel win_arm64.
  5. AutoGen è in manutenzione. AG2 1.0 è una riscrittura. Pydantic AI è passato alla v2 nove mesi dopo la v1. Google ADK 2.0 ha cambi non retrocompatibili.
  6. La specifica MCP 2026-07-28 è senza stato (niente handshake né sessioni). Un client scritto a mano diventa banale.
  7. RTX Spark (chip N1X) è stato annunciato il 31/5/2026 e i PC sono attesi per ottobre 2026. CUDA 13.4 per Windows ARM64 è uscito il 9/9/2026. Ollama (≥0.32.3) e llama.cpp hanno binari CUDA ufficiali per Windows ARM64.
- **Numeri chiave:**
  - Ollama 0.34.2. `OLLAMA_NUM_PARALLEL` vale 1 di default. Il contesto di default è 4k sotto i 24 GiB di VRAM.
  - `num_ctx` non si imposta via `/v1`, e un `num_ctx` diverso tra richieste forza il ricaricamento del modello.
  - `reasoning_effort:"none"` su `/v1` spegne il thinking senza ricaricare. `tool_choice` non è supportato.
  - Gemma 3 su Ollama non ha il tag tools (confermato oggi sulla libreria).
  - Un router LLM separato costa 200–500 ms. Le regole costano meno di 10 ms. La delega come tool dell'agente vocale costa zero chiamate extra.
  - Oltre 10–15 tool per agente l'accuratezza dei modelli piccoli cala.
- **Non verificato (principali):**
  - il tempo reale di ricaricamento di un modello, stimato in 3–6 s per 5 GB;
  - la cancellazione della generazione alla chiusura della connessione su Windows;
  - la banda di memoria reale di RTX Spark;
  - la qualità dell'italiano dei modelli 2026 (nessuna valutazione trovata);
  - un vero `pip install` su Windows ARM64.

---

## 1. Framework multi-agente con endpoint compatibile OpenAI (Ollama)

### Tabella comparativa

| Framework | Versione (data PyPI) | Vitalità | Dipendenze / Windows ARM64 | Ollama via Chat Completions | Streaming dei token | Deleghe e handoff | Async | Client MCP | Telemetria di default | Licenza |
|---|---|---|---|---|---|---|---|---|---|---|
| OpenAI Agents SDK | 0.22.3 (17/9/2026) | 29,6k stelle. Ancora 0.x, minor frequenti: da 0.19 a 0.22 in circa 7 settimane | ~38. `mcp` è obbligatorio, quindi c'è il blocco `cryptography` su ARM64 | Sì, ma il default è la Responses API. Servono `set_default_openai_api("chat_completions")` oppure `OpenAIChatCompletionsModel` | `Runner.run_streamed()` | Handoff nativi, agenti usati come tool | asyncio nativo | Integrato | **Attiva**: tracing verso OpenAI. Si spegne con `set_tracing_disabled(True)` o `OPENAI_AGENTS_DISABLE_TRACING=1` | MIT |
| LangGraph + LangChain | 1.2.11 (11/8/2026) e 1.4.2 (18/9/2026) | 42k e 147k stelle. 1.0 da ottobre 2025, stabile | ~37. Il core è pulito, ma **`langchain-openai` richiede `tiktoken`**, che non ha wheel ARM64 | `ChatOpenAI(base_url=…/v1)`. `langchain-ollama` usa l'API nativa e viola il principio 1 del progetto | `stream_mode="messages"` | `Command(goto)`, supervisor, swarm | sync e async | Pacchetto separato (`langchain-mcp-adapters`, richiede mcp<2) | `langsmith` è sempre installato, ma resta inattivo senza variabili d'ambiente | MIT |
| CrewAI | 1.15.22 (16/9/2026) | 59k stelle, 23 rilasci in 90 giorni | **~133**: chromadb, lancedb, pyarrow, grpcio… Di fatto non installabile su ARM64 | `LLM(base_url=…/v1)` | Sì | Delega tra agenti, processo gerarchico, Flows | `kickoff_async` | Integrato | **Attiva** (anonima). Si spegne con `CREWAI_DISABLE_TELEMETRY=true` | MIT |
| AutoGen (Microsoft) | 0.7.5 (**30/9/2025**) | **In manutenzione**. Il README invita a migrare a MAF | 10–26. `tiktoken` nell'extra openai | Sì | Sì | Sì | Sì | Sì | Non verificato | MIT |
| AG2 | 1.0.5 (11/9/2026) | 4,9k stelle. La 1.0 del 27/7/2026 è una **riscrittura non retrocompatibile** | ~19, pulito su ARM64 | Extra `ag2[openai]` | Non verificato | Modello "Network" con Hub e canali | "async throughout" | Non verificato | Non verificato | Apache-2.0 |
| Microsoft Agent Framework (MAF) | 1.19.0 (18/9/2026) | 13,7k stelle. GA da aprile 2026, con impegno LTS e rilasci settimanali | core + openai ~19, **pulito su ARM64**. `mcp` è opzionale | **`OpenAIChatCompletionClient`**. Attenzione: `OpenAIChatClient` usa la Responses API | `run(..., stream=True)` | Pacchetto orchestrations: sequential, concurrent, handoff, magentic. Più Workflows a grafo | asyncio nativo | Extra opzionale | OpenTelemetry solo su richiesta | MIT |
| Pydantic AI | 2.46.0 (19/9/2026) | 20k stelle. 61 rilasci in 90 giorni. **La v2 è uscita 9 mesi dopo la v1** | slim ~25. L'extra `[openai]` trascina `tiktoken`, l'extra `[mcp]` trascina `cryptography` | `OllamaProvider(base_url=…/v1)`, che usa esplicitamente `/v1/chat/completions`. Il prefisso `openai:` porta invece alla Responses API | `run_stream()`, `iter()` | Delega tramite tool, pydantic-graph, SubAgents | asyncio nativo | `MCPToolset` (extra) | **Nessuna** | MIT |
| smolagents | 1.26.0 (29/5/2026) | 29k stelle. **Rallentato**: nessun rilascio da maggio, 817 issue aperte | ~36, pulito su ARM64 | `OpenAIModel(api_base=…/v1)` | `generate_stream` | Solo `managed_agents` (gerarchico) | **Solo sincrono** | Extra (mcpadapt) | Nessuna | Apache-2.0 |
| LlamaIndex (AgentWorkflow) | core 0.14.24 (19/8/2026), workflows 2.24.1 (20/9/2026) | 52k stelle. Il core non è mai arrivato alla 1.0. Il progetto si sposta verso il "document processing" | Il core ha ~60 dipendenze, con `tiktoken`. `llama-index-workflows` da solo ne ha 8 ed è pulito | `OpenAILike` | Eventi `AgentStream` | `can_handoff_to` | async-first | Pacchetto separato | Non verificato | MIT |
| Google ADK | 2.9.2 (18/9/2026) | 21,6k stelle. La 2.0 del 19/5/2026 ha cambi non retrocompatibili | ~47, **più LiteLLM**, che è nativo, senza wheel ARM64 e con un incidente di supply chain a marzo 2026 | In Python, **solo tramite LiteLLM** | SSE | `sub_agents` con transfer | async | `McpToolset` | Telemetria della CLI spenta di default | Apache-2.0 |
| Agno | 3.0.10 (16/9/2026) | 42k stelle. Tre major in 20 mesi | ~31, pulito su ARM64 | Sì (non verificato nel dettaglio) | Sì | Team e Workflow | sync e async | Sì | **Attiva** (os-api.agno.com). Si spegne con `AGNO_TELEMETRY=false` | Apache-2.0 |
| Strands (AWS) | 1.56.0 (15/9/2026) | 7,4k stelle | ~52: boto3, SDK OTel e `mcp` sono obbligatori. Blocco `cryptography` | `OpenAIModel(client_args=…)` | Sì | Swarm, graph | async | Integrato | OTel su richiesta | Apache-2.0 |
| Apache Burr | 0.43.0 (25/8/2026) | 2,6k stelle, incubating | **0 dipendenze obbligatorie** | È una macchina a stati, non un framework LLM | — | — | — | — | — | Apache-2.0 |

Letta e Mastra sono fuori bersaglio: la prima è una piattaforma con server, la seconda è solo TypeScript. Atomic Agents ha l'idea giusta ma dipendenze pesanti (circa 87, con litellm).

### Wheel Windows ARM64 delle dipendenze native

- **Hanno il wheel win_arm64:** pydantic-core, jiter, orjson, aiohttp, rpds-py, pywin32, websockets, onnxruntime, tokenizers. Anche numpy, ma solo da cp312: su ARM64 conviene Python 3.12 o successivo.
- **Non lo hanno:**
  - `tiktoken` e `grpcio`, che non l'hanno mai avuto.
  - **`cryptography`**: aveva i wheel nelle versioni 46.0.0–46.0.3, poi sono stati rimossi con la PR #14216. Il maintainer ha scritto "no timeline for re-enabling". L'ultima versione, la 50.0.1, non li ha: l'ho verificato anch'io sulla pagina PyPI.
  - litellm, chromadb, lancedb, pyarrow.
  - `libzim`, che ha solo win_amd64.
- **Catena critica:** `mcp` richiede `pyjwt[crypto]`, che richiede `cryptography`. I ripieghi sono tre:
  - bloccare `cryptography==46.0.3`, rinunciando alle patch di sicurezza successive;
  - compilare da sorgente;
  - non usare l'SDK `mcp` lato client (vedi la sezione 3).

### Indicazioni per Calliope

- Ogni handoff aggiunge una chiamata LLM completa prima della prima frase parlata. Nel percorso vocale non vanno usati.
- Quasi tutti i framework sono asyncio. Calliope è a thread. Servirebbe un event loop in un thread dedicato.
- I più compatibili con i principi del progetto sono Pydantic AI slim e MAF (core + openai).

---

## 2. Lo strato sottile fatto in casa

Anthropic, in "Building effective agents", consiglia di partire dalle chiamate dirette all'API. Molti schemi si scrivono in poche righe, e i framework "possono oscurare prompt e risposte". Hugging Face mostra un agente con MCP in circa 70 righe: un ciclo `while` sopra un client MCP, con uscita quando il modello non chiede più tool o quando si raggiunge il tetto di turni.

### Stima delle righe per Calliope

Questa è una mia stima, non una misura.

| Componente | Righe |
|---|---|
| `AgentSpec` (dataclass): modello, prompt di sistema, `reasoning_effort`, temperatura, tool ammessi, numero massimo di turni | ~30 |
| Registro dei tool: da funzione a schema JSON, con allowlist e classe di rischio | ~50 |
| Ciclo di tool calling in streaming: accumulo dei `tool_calls` sui chunk, testo inviato subito al divisore di frasi, tetto di iterazioni, errori restituiti al modello | ~80–100 |
| Gestore dei lavori: id, stato, annullamento, coda dei risultati, log JSONL | ~100 |
| Tool `delega(agente, compito)`, `stato_lavori`, `annulla_lavoro`, più l'annuncio differito | ~50 |
| Arbitro della GPU (la voce passa davanti al secondo piano) | ~60 |
| Ponte MCP: `tools/list` convertito in schema OpenAI, più `tools/call` | ~60 con l'SDK, ~100 scritto a mano |
| Politica di conferma per le azioni rischiose | ~40 |
| **Totale** | **~450–550** |

### Pro

- Pieno controllo della latenza. Lo streaming frase per frase resta intatto e nessun prompt è nascosto.
- La priorità voce/secondo piano va scritta comunque: nessun framework la offre. Tanto vale che sia il cuore del proprio strato.
- Nessuna dipendenza nuova oltre a `openai`, che c'è già. Si evitano i blocchi su ARM64.
- Si è immuni ai cambi non retrocompatibili dei framework.
- È coerente con i principi 1, 2 e 4 del progetto.

### Contro

- I bug sono tuoi: argomenti JSON malformati dai modelli piccoli, tool call stampate come testo, ritentativi.
- Non hai tracing né sessioni già pronti. Un log JSONL però basta.
- Devi seguire da solo i cambiamenti di Ollama.
- Servono test con risposte registrate.
- L'SDK MCP è solo async, il che spinge verso un thread con un event loop.

### Se si vuole comunque un framework

Usarlo solo per gli agenti in secondo piano, mai nel percorso vocale.
- **Pydantic AI slim**, installato senza extra: `pip install pydantic-ai-slim openai`. Da provare su ARM64.
- **MAF** nella forma core + openai.
- `llama-index-workflows` o Burr vanno bene come motore a eventi minimo, se serve.

---

## 3. MCP come standard per i tool

### Stato della specifica

- La specifica corrente è la **2026-07-28**, ed è senza stato:
  - Sono stati eliminati l'handshake `initialize` e l'header `Mcp-Session-Id`.
  - Ogni richiesta è autodescritta nel campo `_meta`.
  - `server/discover` è opzionale.
  - Le liste portano `ttlMs` e `cacheScope`.
- Roots, Sampling, Logging e il vecchio trasporto HTTP+SSE sono deprecati, con 12 mesi di tolleranza.
- I Tasks (lavori lunghi) sono diventati un'estensione ufficiale.
- I risultati `input_required` (multi round-trip) permettono al server di chiedere un input, per esempio una conferma.
- La specifica dice che ci "SHOULD" essere sempre un umano in grado di negare l'invocazione di un tool.
- Le annotazioni dei tool esistono ancora, ma vanno considerate non fidate se il server non è fidato.

### SDK Python

- `mcp` **2.2.0**, del 7/9/2026, per Python ≥3.10.
- Cambi della v2:
  - `FastMCP` rinominato `MCPServer`.
  - Nuovo oggetto `Client`, che si collega via URL, stdio o in memoria.
  - Compatibilità con i client dell'era 2025.
- La linea v1.x è in manutenzione.
- Dipendenze: anyio, httpx2, pydantic, starlette, uvicorn, sse-starlette, jsonschema, `pywin32` (che ha il wheel ARM64), **`pyjwt[crypto]` (blocco su ARM64)**, opentelemetry-api.
- Le note di rilascio dicono "OpenTelemetry tracing enabled by default". Tra le dipendenze c'è però solo l'API OTel, senza exporter. Presumo che non comporti traffico di rete, ma non l'ho verificato.

### Solo rete locale

Sì. I trasporti stdio e Streamable HTTP funzionano su localhost o in LAN, e l'autorizzazione OAuth è opzionale.

Con la specifica senza stato, un client minimale è fattibile senza l'SDK: bastano richieste JSON-RPC via POST per `tools/list` e `tools/call`, usando solo un client HTTP. Questo aggirerebbe il blocco di `cryptography` su ARM64. È una mia deduzione e non l'ho provata.

### Server pronti utili per una casa

| Server | Stato | Note |
|---|---|---|
| **Home Assistant `mcp_server`** (ufficiale) | Da HA 2025.2. Streamable HTTP su `/api/mcp`. Accetta token a lunga durata o OAuth | Espone l'Assist API, **solo per le entità esposte**. Offre tools, prompts e resources. È locale |
| Home Assistant `mcp` (client, ufficiale) | — | Fa il contrario: HA usa tool MCP esterni |
| **ha-mcp** (community) | 4,8k stelle, MIT, **87 tool** | Configura e fa il debug di HA. Funziona in LAN. Sono troppi tool per un modello piccolo: vanno filtrati |
| **openzim-mcp** | v3.3.4 (18/9/2026), MIT, 133 stelle | Legge i file ZIM direttamente, senza kiwix-serve. Trasporti stdio e Streamable HTTP, 8 tool. Dipende da `libzim` 3.13.0, che ha wheel win_amd64 ma **non win_arm64** |
| kiwix-mcp (roanpy) | 1 stella, GPL-3 | **Non supporta Windows**, perché usa lock POSIX |
| **Windows-MCP** (CursorTouch) | v0.8.1 (19/5/2026), Python ≥3.12 | Automazione della UI di Windows senza visione artificiale |
| MCP nativo di Windows (ODR) | **Anteprima** | Registro on-device, contenimento, consenso, `odr.exe`. Connettori per Esplora file e Impostazioni, oggi su build Insider e PC Copilot+. MAF è citato come framework host |
| Server di riferimento (filesystem, fetch, memory…) | — | Sono in larga parte Node. Non li ho approfonditi |

### Attenzione al numero di tool

- Oltre 10–15 tool l'accuratezza cala.
- Un Llama 3.1 8B degrada all'aumentare del numero di server (fonte: MCP-Bench).
- Secondo RAG-MCP, filtrare i tool porta la selezione corretta dal 13,6% al 43,1%.

Questo è un argomento a favore degli agenti specializzati: ognuno vede solo i propri 5–10 tool.

---

## 4. Ollama: più modelli e richieste in parallelo

### Stato del progetto

- Versione stabile **v0.34.2**, del 15/9/2026.
- Dalla v0.30 Ollama lancia `llama-server` come sottoprocesso per i modelli GGUF. Slot, batching continuo e cache del prefisso sono quindi quelli di llama.cpp.
- Dalla v0.33 il tempo al primo token è "circa la metà", grazie ai punti di ripristino del prefill.
- La variabile `OLLAMA_NO_CLOUD` disattiva l'inferenza remota e la ricerca web.
- Windows ARM64 con CUDA è supportato dalla v0.32.3.

### Variabili d'ambiente

Fonte: `envconfig/config.go` e la FAQ di Ollama.

| Variabile | Default | Note |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | automatico, pari a 3 × numero di GPU | Vale solo se i modelli entrano in memoria |
| `OLLAMA_NUM_PARALLEL` | **1** | La cache KV cresce in proporzione (`-c NumCtx*N -np N`). I pesi non vengono duplicati. **È forzato a 1** per le famiglie mllama, qwen3vl, qwen35, qwen35moe, qwen3next, lfm2, lfm2moe e nemotron_h* |
| `OLLAMA_MAX_QUEUE` | 512 | Oltre questo numero il server risponde 503 |
| `OLLAMA_KEEP_ALIVE` | 5m | Un valore negativo tiene il modello sempre caricato. Si può impostare anche per richiesta |
| `OLLAMA_CONTEXT_LENGTH` | automatico: **4k sotto 24 GiB**, 32k tra 24 e 48 GiB, 256k da 48 GiB | Sullo Spark il default salirebbe a 256k: va fissato a mano |
| `OLLAMA_KV_CACHE_TYPE` | f16 | `q8_0` dimezza la memoria della cache. Richiede flash attention, che è automatica |
| `OLLAMA_GPU_OVERHEAD` | 0 | Circa 2e9 byte per tenere libero lo spazio di Whisper |

### Con 8 GB di VRAM

- Se due modelli non stanno insieme, la nuova richiesta attende. Il runner inattivo viene scaricato e il nuovo modello viene caricato. Non c'è preemption.
- Due agenti che alternano due modelli provocano un ricaricamento a ogni turno.
- Non esiste un dato ufficiale sul costo del ricaricamento. La stima non verificata è di **circa 3–6 s** per 5 GB da NVMe, e di 1,5–3 s dalla cache di pagina in RAM. Va misurato con il campo `load_duration` della risposta. È comunque incompatibile con 0,5 s per la prima frase.

### Stessi pesi, prompt di sistema diversi

Queste conclusioni vengono dalla lettura del codice, non da test.

- La chiave del runner è il percorso del blob GGUF.
- `think`, temperatura e prompt di sistema **non** provocano il ricaricamento.
- Lo provocano invece differenze in `NumCtx`, `NumBatch` e `NumGPU`. Tutti gli agenti sullo stesso modello devono quindi usare lo stesso `num_ctx`.
- Su `/v1` il parametro `num_ctx` **non si può impostare**. Si fissa con un Modelfile o con `OLLAMA_CONTEXT_LENGTH`.

### Cache del prefisso

- Ollama invia sempre `cache_prompt: true`.
- Viene scelto lo slot con il prefisso comune più lungo.
- Quando uno slot viene riassegnato, il suo stato finisce nella cache del prompt in RAM di llama-server, che di default è di 8 GiB. Da verificare se Ollama la lascia attiva.
- Con un solo slot, due agenti che si alternano scambiano lo stato a ogni turno.
- Con due o più slot, ogni agente tende a restare sul proprio.

### API `/v1`

- `reasoning_effort` accetta i valori `none`, `low`, `medium`, `high` e `max`.
- `tools` è supportato, anche in streaming. La tool call arriva intera in un chunk, mentre il testo resta in streaming.
- **`tool_choice` non è supportato.**
- gpt-oss non spegne il thinking: si può solo abbassare a `low`.

### Priorità

- Non esiste alcuna priorità: la coda è FIFO.
- Alla chiusura della connessione la generazione si interrompe. È affidabile da Ollama ≥0.33, secondo un test di terzi, ma non ho trovato conferme su Windows.
- Con il batching continuo, un prefill lungo in secondo piano ritarda comunque il primo token della voce.

### Alternative con API OpenAI

| Runtime | Concorrenza | Priorità / preemption | Più modelli | Windows x64 | Windows ARM64 | Licenza |
|---|---|---|---|---|---|---|
| Ollama 0.34.2 | Slot di llama-server, default 1 | No | Sì, con sfratto automatico | Sì | **Sì, con CUDA dalla 0.32.3** | MIT* |
| llama.cpp `llama-server` | `-np`, batching continuo, `--cache-ram`, salvataggio e ripristino degli slot | No, ma si può fissare **`id_slot` per richiesta** | Modalità router: `--models-dir`, `--models-max` (default 4). C'è una race condition nota | Sì | **Sì, binari ufficiali `win-cuda-13.4-arm64`** | MIT |
| llama-swap v256 | Proxy | No | Gruppi, matrice, TTL | Sì | Nessun binario windows_arm64 | MIT |
| vLLM | PagedAttention | **Sì**, con `--scheduling-policy priority` | Un modello per processo | **No, solo WSL** | No | Apache-2.0* |
| SGLang | RadixAttention | **Sì**, con `--enable-priority-scheduling` | Un modello per processo | Non trovato | No | Apache-2.0* |
| LM Studio 0.4.x | Richieste parallele da gennaio 2026, 4 di default | No | Caricamento su richiesta e TTL | Sì | App ARM64. CUDA su Spark non verificato | Proprietaria* |
| TensorRT-LLM / NIM | — | — | — | Supporto Windows deprecato, solo WSL2 | No | — |

\* Licenze non riverificate oggi.

Altri runtime (Lemonade, KoboldCpp, Jan, mistral.rs, TabbyAPI): non ho trovato nulla di utile per Windows ARM64 con CUDA.

### RTX Spark

- Annuncio il 31/5/2026, in vendita da ottobre 2026.
- Il chip N1X esiste in due configurazioni: 20 core + 6144 core CUDA con 24–128 GB, oppure 18 core + 5120 core CUDA con 24–32 GB.
- NVIDIA non ha pubblicato la banda di memoria. I 273 GB/s sono il dato del GB10.
- Runtime indicati da NVIDIA per Windows on Arm: Ollama, llama.cpp, PyTorch, TensorRT for RTX.
- Riferimenti misurati su DGX Spark (Linux):
  - gpt-oss-20b a 58–63 token/s;
  - gpt-oss-120b a 35–61 token/s;
  - un modello denso da 27–32B a circa 10 token/s.
  - Questo conferma la convenienza dei MoE.

---

## 5. Tool calling nei modelli piccoli su Ollama

### Modelli fino a 9B

Le dimensioni sono quelle del tag predefinito su Ollama, di solito Q4_K_M.

| Modello (tag Ollama) | Dim. | Tag tools | Thinking | Italiano ufficiale | Punteggi trovati | Note |
|---|---|---|---|---|---|---|
| `qwen3.5:4b` | 3,4 GB | Sì | Ibrido, acceso di default | Generico ("201 lingue") | BFCL-V4 50,3. TAU2 79,9. HA assist 81,1% | Miglior rapporto qualità/VRAM. **Ollama lo forza a parallel=1.** `/no_think` non è supportato: serve `reasoning_effort:"none"` |
| `qwen3.5:9b` | 6,6 GB | Sì | Ibrido | Come sopra | BFCL-V4 66,1 | Non convive con Whisper in 8 GB |
| `qwen3:8b` | 5,2 GB | Sì | Ibrido | "100+ lingue" | BFCL V4 42,6 (FC, con thinking). HA 82,8% | Contesto 40K. Al limite con Whisper in VRAM. Non è tra le famiglie forzate a parallel=1 |
| `qwen3:4b-instruct-2507` | 2,5 GB | Sì | No | "100+ lingue" | BFCL V4 35,7. HA 71,7% | Latenza prevedibile. Usare il tag esplicito |
| `gemma3` (tutte le taglie) | 4b: 3,3 GB | **No**, solo vision | No | 140+ lingue | BFCL V4 in modalità prompt: 19,6 (4B) | **Confermato oggi**: nessun tag tools. Lo stesso vale per `gemma3n` |
| `gemma4:e2b` / `e4b` / `12b` | 7,2 / 9,6 / 7,6 GB (QAT: 4,3 / 6,1 GB) | Sì | Sì | "35+ lingue", elenco non trovato | Tau2: 24,5 / 42,2 / 69,0%. HA assist: 45 / 67 / 83,5% | Pesanti. **Il parser delle tool call ha bug aperti** (issue #18275 del 6/9/2026) |
| `functiongemma` | 301 MB | Sì | No | — | HA assist-mini 9,4% | Richiede fine-tuning. Inutile così com'è |
| `granite4.1:3b` / `:8b` | 2,1 / 5,3 GB | Sì | No | **Sì** (12 lingue) | BFCL v3 60,8 / 68,3 (fonte IBM) | Apache 2.0, contesto 128K, latenza prevedibile |
| `granite4.2:3b` / `:8b` | 2,2 / 5,3 GB | Oggi **senza badge tools** sulla libreria, anche se il README li dichiara | Ibrido | **Sì** | BFCL v4 52,4 (8B, fonte IBM) | Uscito il 25/8/2026. Da verificare con `ollama show` |
| `ministral-3:3b` / `:8b` | 3,0 / 6,0 GB | Sì | No | **Sì** (11 lingue) | HA assist 72 / 78% | La variante 8B è stretta in 8 GB |
| `lfm2.5:8b` (MoE, 1,5B attivi) | 5,2 GB | Sì | Sì | **Sì** | BFCLv3 64,8, v4 49,7 (fonte Liquid) | Licenza propria. Non ho trovato come spegnere il thinking. Forzato a parallel=1 |
| `nemotron-3-nano:4b` | 2,8 GB | Sì | Ibrido | Principalmente inglese | BFCL v3 61,1 con thinking spento | Forzato a parallel=1 |
| `llama3.1:8b` | 4,9 GB | Sì | No | Sì, secondo la model card di Meta | BFCL V4 ~25,6. Multi-turn 11% | Datato |
| `llama3.2:3b` | 2,0 GB | Sì | No | **Sì** | BFCL V4 22,0 | Debole |
| `phi4-mini` | 2,5 GB | Sì | No | Non elencato | 57,5% (test jdhodges) | Phi-5 non verificabile |
| `gpt-oss:20b` | 14 GB | Sì | **Non disattivabile** | Non dichiarato | HA 87,6% | Non sta in 8 GB |
| Altri: `olmo-3:7b` (solo inglese), SmolLM3, xLAM-2, EuroLLM, Minerva (solo upload della community), Velvet (nessun function calling dichiarato) | — | — | — | — | — | Scartati |

Avvertenze sui benchmark:
- Il BFCL V4 ufficiale (aggiornato al 12/4/2026) non include Qwen3.5, Gemma 4, Granite 4.x, Ministral 3, LFM, gpt-oss né Nemotron 3. Per questi modelli i punteggi sono quelli dichiarati dai produttori.
- Lo "Home LLM Leaderboard" di Allen Porter esiste ed è aggiornato al 2026, ma i test sono in inglese.
- Non ho trovato alcuna valutazione in italiano dei modelli del 2026. Serve un test in italiano fatto in casa.

### MoE candidati per lo Spark

Le velocità sono misurate su DGX Spark / GB10.

| Modello | Totali / attivi | Q4 su Ollama | Tools | Thinking spegnibile | Italiano | Tool calling | Token/s |
|---|---|---|---|---|---|---|---|
| `gemma4:26b` | 25,2B / 3,8B | 18 GB | Sì | Sì | Generico | Tau2 68,2%. HA 86,3%, il migliore tra i locali | 52,7 |
| `qwen3.5:35b-a3b` | 35B / 3B | 24 GB | Sì | Sì | 201 lingue | BFCL-V4 67,3. TAU2 81,2 | 48,2 |
| `qwen3.6:35b` | 35B / 3B | 23 GB | Sì | Sì | — | TAU3 67,2 | 86 (vLLM NVFP4). **Issue #16383 aperta** sulle tool call in Ollama |
| `qwen3:30b-a3b-instruct-2507` | 30,5B / 3,3B | 19 GB | Sì | Non pensa | 100+ lingue | BFCL V4 41,4. HA 83,9% | 74 (NVFP4) |
| `nemotron-3-nano:30b` | 30B / 3,5B | 24 GB | Sì | Sì | **Ufficiale** | BFCL v4 53,8 | 64,7 |
| `glm-4.7-flash` | 30B / 3B | 19 GB | Sì | Sì | — | τ² 79,5. HA 82,6% | Non trovato |
| `gpt-oss:20b` / `:120b` | 21B / 3,6B e 117B / 5,1B | 14 / 65 GB | Sì | **No** | Non dichiarato | tau retail 54,8 / 67,8 | 61 / 35–42 |
| `qwen3.5:122b-a10b` | 122B / 10B | 81 GB | Sì | Sì | 201 lingue | BFCL-V4 72,2 | 20 (Ollama). 28–51 con vLLM |
| `nemotron-3-super:120b` | 120B / 12B | 87 GB | Sì | Sì | **Ufficiale** | 17/17 nel test Exxact | 16,4 |
| `granite4:small-h` | 32B / 9B | 19 GB | Sì | Non pensa | **Ufficiale** | Non trovato | Non trovato |
| `llama4:scout` | 109B / 17B | 67 GB | Sì | No | Ufficiale | BFCL V4 28,1 (debole) | Lento |

Da scartare per la voce perché densi (circa 10 token/s): `qwen3.5:27b`, `gemma4:31b`, `mistral-medium-3.5`. Mistral Small 4 e GLM-4.5-Air su Ollama esistono solo come upload della community.

---

## 6. Schemi di progetto per assistenti vocali con agenti

### "Ci penso e ti faccio sapere"

Il riferimento è LiveKit Agents 1.6 (11/6/2026), con i suoi "async tools":
- Il tool restituisce subito un risultato sintetico, per esempio "ho avviato la ricerca". Il modello lo verbalizza e la conversazione prosegue.
- Il lavoro continua in background.
- Gli aggiornamenti e il risultato finale emergono **solo quando utente e agente sono entrambi in silenzio**.
- Il risultato viene inserito nel contesto del modello. Così una domanda di seguito come "dimmi di più" funziona.
- Pipecat ha lo stesso schema con `cancel_on_interruption=False`.

### Talker e reasoner

Lo schema viene da DeepMind (2024) e da LiveKit:
- I due agenti hanno contesti separati.
- Il talker ha l'istruzione esplicita di **non tirare a indovinare** la risposta che ha delegato.
- È da evitare quando la risposta va verificata prima di essere detta, oppure quando il talker non ha nulla di utile con cui riempire l'attesa.

### Annullamento e duplicati

- I tool sono annullabili, con due tool ausiliari per elencare i lavori in corso e per annullarli.
- Politica sui duplicati, configurabile per tool: `allow`, `reject`, `replace`, `confirm`.
- Un lavoro delegato sopravvive alle interruzioni della conversazione, salvo richiesta esplicita di annullarlo.

### Conferme per le azioni rischiose

Lo schema viene dall'articolo "Speculative Interaction Agents" e dalla specifica MCP.
- I tool vanno classificati per rischio:
  - **Sola lettura:** si esegue, anche in modo speculativo.
  - **Reversibile:** si esegue e si annuncia.
  - **Irreversibile:** serve una conferma verbale. Calliope ripete l'azione e riconosce "sì" o "no" con regole, non con l'LLM. Il silenzio oltre il timeout vale come "no".
- La classe di rischio sta nella configurazione di Calliope. Le annotazioni MCP servono solo come suggerimento.
- Gli agenti in secondo piano non eseguono mai azioni distruttive. Restituiscono una proposta, che l'agente vocale conferma con l'utente.
- Il risultato `input_required` di MCP si presta bene a questo flusso.

### Router

| Approccio | Latenza | Note |
|---|---|---|
| Regole, regex, parole chiave | meno di 10 ms (p95 sotto 8 ms in un caso reale) | In quel caso il p50 complessivo è passato da 1,4 s a 620 ms dopo l'introduzione delle regole. Home Assistant fa lo stesso con "prefer handling commands locally" |
| Embedding (router semantico) | ~10–100 ms | Richiede un modello di embedding, cioè una dipendenza in più |
| LLM classificatore separato | 200–500 ms | Da evitare nel percorso vocale |
| **L'agente vocale stesso, con il tool `delega(...)`** | **zero chiamate extra** | La decisione arriva con i primi token della stessa risposta. `tool_choice` su Ollama manca, quindi la scelta si guida solo con il prompt |

### Costo del routing

- Se il modello vocale chiama `delega`, la frase di presa in carico può essere una frase fissa, per esempio "Ci penso e ti faccio sapere". Costa zero latenza.
- In alternativa può essere una seconda chiamata LLM, che costa circa 0,5 s.
- Un handoff vero costerebbe una chiamata completa in più prima della prima frase.

---

## 7. Raccomandazione finale

### 1. Strato proprio, non un framework

Il motivo decisivo non è il numero di righe. Il problema centrale di Calliope è far convivere sulla stessa GPU una richiesta vocale urgente e un lavoro lungo in secondo piano. Nessun framework lo modella. Nessun server disponibile su Windows x64 o ARM64 lo risolve: non c'è priorità né preemption. L'arbitro va scritto comunque, quindi conviene che sia il cuore del proprio strato.

Motivi secondari:
- **Igiene delle dipendenze su ARM64.** I blocchi sono `mcp` con `cryptography`, `tiktoken` e LiteLLM.
- **Instabilità dei framework.** Agents SDK è ancora 0.x. Pydantic AI ha avuto la v2 in nove mesi. ADK è passato alla 2.0. AG2 è una riscrittura. AutoGen è in manutenzione.
- **Trasparenza dei prompt.**

Forma suggerita:
- La pipeline audio resta a thread, com'è oggi.
- Un solo thread aggiuntivo ospita un event loop asyncio per gli agenti, con `AsyncOpenAI` e un client MCP.
- I lavori comunicano con la pipeline audio tramite code.

Piano B: Pydantic AI slim oppure MAF (core + openai), solo per gli agenti in secondo piano.

### 2. Tool via MCP, ma con parsimonia

- Ogni agente vede al massimo 5–10 tool.
- Home Assistant si collega con l'integrazione ufficiale `mcp_server`, che espone l'Assist API solo per le entità esposte.
- La biblioteca offline usa openzim-mcp. `libzim` non ha il wheel per ARM64, quindi sullo Spark l'uso va verificato.
- I tool interni semplici (ora, timer, stato dei lavori) restano funzioni Python: non serve un server MCP.
- Su ARM64 conviene valutare un client MCP minimale scritto a mano, per evitare `cryptography`.

### 3. Oggi, con 8 GB di VRAM

- **Un solo modello residente, condiviso da tutti gli agenti.**
  - Gli agenti si distinguono per prompt di sistema, `reasoning_effort` e temperatura: nessuno di questi provoca ricaricamenti.
  - `keep_alive=-1`.
  - **Stesso `num_ctx` per tutti**, fissato con `OLLAMA_CONTEXT_LENGTH`, tra 8k e 16k.
  - `OLLAMA_KV_CACHE_TYPE=q8_0`.
  - `OLLAMA_GPU_OVERHEAD` per lasciare spazio a Whisper.
  - Stima mia per qwen3:8b: circa 147 KB per token in f16, quindi 8k di contesto occupano circa 0,6 GB con q8_0.
- **Candidati, da provare in italiano:**
  - `qwen3:8b`: ibrido, e il progetto l'ha già misurato a 0,5 s per la prima frase.
  - `qwen3.5:4b`: più leggero, con i migliori numeri di tool calling, ma forzato a parallel=1.
  - `granite4.1:8b`: italiano ufficiale, niente thinking.
- **`gemma3:4b`, indicato nel CLAUDE.md, va abbandonato per gli agenti:** su Ollama non ha il tag tools.
- **La priorità è lato client.** Serve un arbitro della GPU:
  - Il segnale di preemption conviene farlo partire **dall'inizio del parlato rilevato dal VAD**, non dalla richiesta all'LLM. La durata della frase più il tempo dell'STT danno al server il tempo di liberarsi.
  - L'arbitro chiude lo stream del lavoro in secondo piano (serve Ollama ≥0.33), serve la voce e poi rilancia il lavoro, sfruttando la cache del prefisso.
  - I lavori lunghi vanno spezzati in passi brevi.
- **Alternativa da misurare:** `NUM_PARALLEL=2` con il batching continuo. La voce ha subito uno slot, ma la velocità si divide e un prefill lungo in secondo piano ritarda il primo token. Vale solo per i modelli non forzati a 1.
- **Niente secondo modello su GPU.** Lo scambio costa secondi. Se serve un modello più capace, l'idea da provare è tenerlo solo su CPU e RAM (`num_gpu 0` nel Modelfile), in modo che non sfratti mai il modello vocale. Non ho dati sulle velocità.

### 4. Domani, sullo Spark

- Più modelli residenti insieme:
  - un MoE vocale veloce con 3–4B attivi: `gemma4:26b`, `qwen3.5:35b-a3b`, oppure `nemotron-3-nano:30b`, che ha l'italiano ufficiale;
  - un ragionatore grande: `gpt-oss:120b`, `qwen3.5:122b-a10b` o `nemotron-3-super:120b`.
- Non serve più lo scambio dei modelli. La banda di memoria però è condivisa, quindi l'arbitro resta necessario: si mette in pausa il lavoro in secondo piano mentre la voce genera.
- Conviene valutare `llama-server` diretto, con i binari ufficiali ARM64 e CUDA:
  - `id_slot` dedicato alla voce;
  - `--cache-ram`;
  - modalità router per più modelli.
  - Grazie al principio "solo API OpenAI", il passaggio è un cambio di URL.
- Fissare `OLLAMA_CONTEXT_LENGTH` a mano: il default automatico salirebbe a 256k.
- Usare Python 3.12 o successivo.

### 5. Routing a tre livelli

1. **Regole** per il sottoinsieme chiuso di comandi: stop, esci, conferme, annulla, timer.
2. **Agente vocale** con pochi tool, tra cui `delega`, `stato_lavori` e `annulla_lavoro`.
3. **Agenti in secondo piano.** L'annuncio del risultato arriva solo quando c'è silenzio. L'half-duplex aiuta, perché Calliope controlla il microfono. Il risultato viene inserito nel contesto dell'agente vocale.

---

## 8. Cose NON verificate

- Non è stato fatto alcun test su hardware, né alcun `pip install` reale su Windows ARM64. I conteggi delle dipendenze sono stime calcolate da uno script.
- Il tempo reale di ricaricamento di un modello: ho solo stime di terzi. Va misurato con `load_duration`.
- Se Ollama lascia attiva la cache del prompt in RAM di llama-server (`--cache-ram`).
- Se due tag creati da Modelfile diversi, ma con la stessa base, condividono lo stesso processo: è dedotto dal codice (`schedulerModelKey`).
- La cancellazione della generazione alla chiusura della connessione. Sembra funzionare su Ollama ≥0.33 secondo un solo test di terzi. Su llama-server diretto o tramite llama-swap le fonti si contraddicono. Non ho conferme su Windows.
- La banda di memoria di RTX Spark: NVIDIA non l'ha pubblicata.
- CUDA dentro applicazioni x64 emulate da Prism.
- LM Studio, llama-swap e KoboldCpp su Windows ARM64 con CUDA.
- L'installer di Ollama su ARM64: ho la conferma solo dello zip.
- La qualità dell'italiano di Qwen3.5, Gemma 4, Granite 4.x e Ministral 3: non ho trovato valutazioni.
- L'elenco puntuale delle lingue di Qwen3.5 e Gemma 4.
- Se `granite4.2` su Ollama espone davvero i tools.
- A quale variante punta l'alias `qwen3:4b`.
- Come si spegne il thinking di LFM2.5.
- L'esistenza di Phi-5.
- I punteggi BFCL dei modelli del 2026 sono dichiarati dai produttori, non tratti dal leaderboard ufficiale.
- Le velocità su Spark di GLM-4.7-Flash, Qwen3-Next, Granite small-h e Llama 4 Scout.
- Per AG2 1.0: streaming, MCP e telemetria.
- Per Agno: classi dei modelli e MCP.
- I parametri esatti di `OpenAIChatCompletionClient` (MAF) e di `OpenAILike` (LlamaIndex).
- Se `ChatOpenAI` di langchain-openai usa Chat Completions di default.
- L'assenza totale di chiamate di rete di default in LangChain, LlamaIndex e smolagents.
- Se la voce "OpenTelemetry tracing enabled by default" dell'SDK `mcp` v2 comporta traffico di rete. Presumo di no, perché c'è solo l'API OTel.
- Se il server MCP di Home Assistant è già allineato alla specifica 2026-07-28.
- La fattibilità del client MCP minimale scritto a mano: è una mia deduzione dalla specifica.
- Le licenze contrassegnate con * nella tabella dei runtime.
- I metadati di licenza su PyPI sono vuoti per crewai, agent-framework, google-adk e smolagents. Le licenze riportate vengono da GitHub.
- I benchmark di terzi sull'overhead dei framework (dev.to e blog).
- Tutte le stime contrassegnate come mie: righe di codice, memoria della cache KV, idea del secondo modello su CPU, preemption dall'inizio del parlato rilevato dal VAD.

---

## 9. Fonti

**Framework**
- https://pypi.org/pypi/openai-agents/json
- https://raw.githubusercontent.com/openai/openai-agents-python/main/docs/config.md
- https://raw.githubusercontent.com/openai/openai-agents-python/main/docs/tracing.md
- https://raw.githubusercontent.com/openai/openai-agents-python/main/docs/models/index.md
- https://pypi.org/pypi/langgraph/json
- https://pypi.org/pypi/langchain-openai/json
- https://docs.langchain.com/oss/python/langgraph/streaming
- https://pypi.org/pypi/crewai/json
- https://docs.crewai.com/en/telemetry
- https://github.com/microsoft/autogen
- https://pypi.org/pypi/ag2/json
- https://raw.githubusercontent.com/ag2ai/ag2/main/README.md
- https://pypi.org/pypi/agent-framework-core/json
- https://github.com/microsoft/agent-framework
- https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- https://learn.microsoft.com/en-us/agent-framework/overview/
- https://pypi.org/pypi/pydantic-ai-slim/json
- https://raw.githubusercontent.com/pydantic/pydantic-ai/main/docs/models/ollama.md
- https://pydantic.dev/articles/pydantic-ai-v2
- https://pypi.org/pypi/smolagents/json
- https://pypi.org/pypi/llama-index-core/json
- https://pypi.org/pypi/llama-index-workflows/json
- https://pypi.org/pypi/google-adk/json
- https://raw.githubusercontent.com/google/adk-docs/main/docs/agents/models/ollama.md
- https://docs.litellm.ai/blog/security-update-march-2026
- https://pypi.org/pypi/agno/json
- https://docs.agno.com/telemetry
- https://github.com/agno-agi/agno/issues/6236
- https://pypi.org/pypi/strands-agents/json
- https://pypi.org/pypi/apache-burr/json
- https://pypi.org/pypi/atomic-agents/json

**Wheel Windows ARM64**
- https://pypi.org/project/cryptography/#files
- https://github.com/pyca/cryptography/pull/14216
- https://github.com/pyca/cryptography/issues/14249
- https://github.com/pyca/cryptography/issues/14168
- https://github.com/openai/tiktoken/issues/403
- https://pypi.org/pypi/grpcio/json
- https://pypi.org/project/jiter/#files
- https://pypi.org/project/pywin32/#files
- https://pypi.org/project/libzim/#files
- https://pypi.org/project/openai/

**Strato fatto in casa**
- https://www.anthropic.com/engineering/building-effective-agents
- https://huggingface.co/blog/python-tiny-agents
- https://dev.to/gabrielanhaia/your-first-tool-calling-agent-with-no-framework-just-the-bare-sdk-3ip3
- https://www.aibuilderclub.com/blog/how-to-build-ai-agent-from-scratch

**MCP**
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://modelcontextprotocol.io/specification/2026-07-28/changelog
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://www.theregister.com/devops/2026/07/23/model-context-protocol-prepares-to-break-with-its-stateful-past/5276722
- https://pypi.org/project/mcp/
- https://github.com/modelcontextprotocol/python-sdk/releases
- https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/pyproject.toml
- https://www.home-assistant.io/integrations/mcp_server/
- https://www.home-assistant.io/integrations/mcp/
- https://github.com/homeassistant-ai/ha-mcp
- https://github.com/cameronrye/openzim-mcp
- https://pypi.org/project/openzim-mcp/
- https://github.com/roanpy/kiwix-mcp
- https://github.com/CursorTouch/Windows-MCP
- https://learn.microsoft.com/en-us/windows/ai/mcp/overview
- https://www.thurrott.com/windows/330450/new-windows-11-insider-build-brings-file-explorer-and-settings-connectors-for-ai-agents
- https://arxiv.org/pdf/2508.20453 (MCP-Bench)
- https://tianpan.co/blog/2026-04-19-over-tooled-agent-problem
- https://arxiv.org/pdf/2605.24660

**Ollama e runtime**
- https://github.com/ollama/ollama/releases
- https://github.com/ollama/ollama/releases/tag/v0.30.0
- https://raw.githubusercontent.com/ollama/ollama/main/envconfig/config.go
- https://raw.githubusercontent.com/ollama/ollama/main/server/sched.go
- https://raw.githubusercontent.com/ollama/ollama/main/llm/llama_server.go
- https://docs.ollama.com/faq
- https://docs.ollama.com/context-length
- https://docs.ollama.com/api/openai-compatibility
- https://docs.ollama.com/capabilities/thinking
- https://docs.ollama.com/capabilities/tool-calling
- https://ollama.com/blog/streaming-tool
- https://ollama.com/blog/new-model-scheduling
- https://ollama.com/blog/nvidia-spark-performance
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md
- https://huggingface.co/blog/ggml-org/model-management-in-llamacpp
- https://github.com/ggml-org/llama.cpp/pull/16391
- https://github.com/ggml-org/llama.cpp/issues/24496
- https://github.com/ggml-org/llama.cpp/discussions/16578
- https://github.com/mostlygeek/llama-swap
- https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html
- https://docs.vllm.ai/en/latest/cli/serve.html
- https://github.com/vllm-project/vllm/issues/40004
- https://lmstudio.ai/blog/0.4.0
- https://lmstudio.ai/docs/app/advanced/parallel-requests
- https://nvidia.github.io/TensorRT-LLM/release-notes.html
- https://docs.nvidia.com/nim/wsl2/latest/

**RTX Spark e CUDA su Windows ARM**
- https://nvidianews.nvidia.com/news/nvidia-microsoft-windows-pcs-agents-rtx-spark
- https://blogs.windows.com/windowsexperience/2026/05/31/introducing-a-powerful-new-chapter-for-windows-pcs-accelerated-by-nvidia-rtx-spark/
- https://blogs.nvidia.com/blog/local-ai-ifa-next-gen-agents-nv-pair-rtx-spark/
- https://developer.nvidia.com/topics/ai/local-ai/port-apps
- https://en.wikipedia.org/wiki/Nvidia_RTX_Spark
- https://wccftech.com/nvidia-rtx-spark-pcs-launch-october-two-n1x-configurations-specs/
- https://wccftech.com/nvidia-cuda-13-4-support-windows-on-arm-ahead-of-rtx-spark-launch/
- https://blog.conan.io/cuda/gpu/armv8/arm64/windows/conan/nvidia/jetson/jetpack/2026/07/30/CUDA-Meets-Windows-On-Arm64-NVIDIA-RTX-Spark.html
- https://lecompute.fr/en/silicon/rtx-spark-vs-dgx-spark/

**Modelli**
- https://ollama.com/search?c=tools
- https://ollama.com/library/gemma3
- https://ollama.com/library/gemma3n
- https://ollama.com/library/gemma4/tags
- https://ollama.com/library/qwen3.5
- https://ollama.com/library/qwen3/tags
- https://ollama.com/library/qwen3.6/tags
- https://ollama.com/library/granite4.1
- https://ollama.com/library/granite4.2
- https://ollama.com/library/ministral-3
- https://ollama.com/library/lfm2.5
- https://ollama.com/library/nemotron-3-nano
- https://ollama.com/library/nemotron-3-super
- https://ollama.com/library/glm-4.7-flash
- https://ollama.com/library/gpt-oss
- https://ollama.com/library/phi4-mini
- https://ollama.com/library/llama3.1
- https://ollama.com/library/llama3.2
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/Qwen/Qwen3.5-9B
- https://huggingface.co/Qwen/Qwen3.5-35B-A3B
- https://ai.google.dev/gemma/docs/core/model_card_4
- https://huggingface.co/ibm-granite/granite-4.1-8b
- https://research.ibm.com/blog/introducing-granite-4-2
- https://huggingface.co/LiquidAI/LFM2.5-8B-A1B
- https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512
- https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16
- https://gorilla.cs.berkeley.edu/leaderboard.html
- https://gorilla.cs.berkeley.edu/data_overall.csv
- https://raw.githubusercontent.com/allenporter/home-assistant-datasets/main/reports/README.md
- https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/
- https://www.jdhodges.com/blog/local-llms-on-tool-calling-2026-pt1-local-lm/
- https://github.com/ollama/ollama/issues/18275
- https://github.com/ollama/ollama/issues/16383
- https://github.com/ollama/ollama/issues/14745
- https://github.com/ollama/ollama/issues/12557
- https://www.exxactcorp.com/blog/benchmarks/benchmarking-local-ai-agents-on-nvidia-dgx-spark
- https://sparkbench.dev/
- https://tokenstead.ai/guides/dgx-spark-benchmarks-2026
- https://huggingface.co/spaces/evalitahf/evalita_llm_leaderboard
- https://arxiv.org/abs/2512.04759

**Schemi per la voce**
- https://livekit.com/blog/async-tools-voice-agents
- https://livekit.com/blog/talker-reasoner-pattern-voice-agents
- https://livekit.com/blog/supervisor-pattern-voice-agents
- https://docs.pipecat.ai/pipecat/learn/function-calling
- https://github.com/pipecat-ai/pipecat/issues/5779
- https://www.theorydelta.com/findings/pipecat-voice-framework/
- https://arxiv.org/html/2605.13360v2
- https://arxiv.org/pdf/2410.08328
- https://dev.to/romiteld/my-voice-router-that-refuses-to-think-pattern-first-multi-agent-orchestration-for-sub-second-1j8k
- https://blog.vllm.ai/2025/09/11/semantic-router.html
- https://community.home-assistant.io/t/why-prefer-handling-commands-locally-increases-the-time-from-2-5s-to-52s/947662
- https://www.home-assistant.io/actions/assist_satellite.start_conversation/
