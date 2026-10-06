# Molti tool e agenti con un LLM piccolo: stato dell'arte e misure (26/09/2026)

*Ricerca del 26 settembre 2026. Domanda: Calliope usa `gemma4:e4b-it-qat` (4B effettivi,
thinking spento, temperatura 0,3, `num_ctx` 16384) con 10 tool nativi; la visione ne prevede
molti di più (calcoli, timer, promemoria, meteo, Home Assistant, musica, biblioteca, memoria,
file, PC) e agenti in secondo piano. Come si gestiscono molti tool e gli agenti mantenendo la
prima frase sotto ~0,7 s e l'affidabilità? Parte dalle conclusioni di
[`2026-09-21-orchestrazione-agenti.md`](2026-09-21-orchestrazione-agenti.md) e
[`2026-09-21-confronto-llm.md`](2026-09-21-confronto-llm.md), che qui non si ripetono.
Codice, dati e risultati grezzi in [`docs/ricerche/banchi/ricerca_tool/`](banchi/ricerca_tool/).*

## In breve

- **Con 40 tool piatti gemma4:e4b non sbaglia di più.** Su 100 richieste vocali che
  richiedono un tool sceglie quello giusto nel 99 % dei casi, con gli argomenti giusti nel 98 %.
  Non fa falsi sulle 19 richieste senza tool. La soglia di «5–10 tool» della ricerca del 21/09
  (dai benchmark in inglese e da modelli più vecchi) **per questo modello e questo catalogo
  non vale**: 5, 10, 20 e 40 tool danno lo stesso 100 % sulle 16 richieste risolvibili già
  con 5.
- **Il vero costo di molti tool è la cache del prefisso, non l'accuratezza.** Il renderer di
  gemma4 mette i tool in testa al prompt. Con un elenco fisso i 3400 token di 40 tool stanno in
  cache e costano ~60–90 ms di prompt eval a turno. Con il **recupero top-k** l'elenco cambia a
  ogni turno e si rivaluta tutto: 0,2 s senza storia, **0,6 s con 30 turni**. La prima frase
  con tool passa da 0,63 a 0,90 s (mediane), a parità di accuratezza (96–97 %).
- **Il recupero funziona, ma oggi non serve.** bge-m3 con descrizioni arricchite da due frasi
  d'esempio (parafrasi, non le richieste di prova) trova il tool giusto nei primi 5 nel 98 %
  dei casi e nei primi 8 nel 100 %. Costa 21 ms su GPU e 34 ms su CPU, con 0 VRAM su CPU.
  nomic-embed-text è nettamente peggiore (87 % a k=5). Serve **solo quando il catalogo
  supera ciò che il modello regge**: probabilmente decine di entità di casa e i tool MCP.
- **Meta-tool, «tool search», due stadi e formato vincolato vanno tutti peggio del piatto.**
  - meta-tool per categoria: 90 %; il modello fa i conti a mente e inventa nomi composti come
    `musica_alza_volume`;
  - `cerca_strumenti` alla Anthropic: 47 %; un 4B dice «non posso» invece di cercare;
  - categoria scelta dall'LLM: 94 %, +0,48 s;
  - scelta con grammatica JSON: 96 % ma argomenti all'87 % e +1,3 s.
  - Il thinking dà il 100 % ma la prima frase va a 4 s (mediana), 7,6 s al p90.
  - Gli esempi few-shot nel prompt fanno **peggio**: 86 chiamate su 100 scritte come testo e
    argomenti giusti al 47 %.
- **Le chiamate scritte come testo crescono con il numero di tool** (8 su 29 con 10 tool,
  49 su 101 con 40). Sono quasi tutte `nome(arg=…)` in stile Python: è una scelta del
  modello, non un difetto del parser di Ollama. `TextCallGuard` le salva quasi tutte (0–2 fughe
  su 119) e non costano latenza. Una frase nel prompt («emetti sempre una chiamata di funzione
  vera, mai il suo nome scritto nel testo») le riduce del 30 % (da 49 a 35).
- **Altri modelli**:
  - gemma4:e2b sbaglia metà delle scelte (54 % a 40 tool): non è un instradatore
    utilizzabile;
  - qwen3.5:4b arriva al 95 % a 40 tool senza chiamate come testo, ma sbaglia i tool di
    voce e identità;
  - qwen3:8b arriva al 90 % ed è più lento (1,2 s).
  - Con qwen3:8b bge-m3 su GPU non ci sta: Ollama alterna i due modelli a ogni richiesta,
    8,5 s l'una. **gemma4:e4b resta la scelta.**
- **Agente come tool (casa, 26 entità):** 12 su 12 sia diretto sia con l'agente.
  - Diretto: prima frase a 0,81 s.
  - Con l'agente: 1,61 s. Scende a 1,29 s se la frase dell'agente va dritta al TTS, con una
    frase fissa («Un attimo») già a 0,52 s.
  - **Con 26 entità conviene ancora il diretto**; l'agente serve quando il lavoro è a più passi.
- **Secondo piano:** la coda di Ollama è FIFO (`NUM_PARALLEL=1`). Una generazione di 900
  token davanti alla voce porta la prima frase da 0,3 a **11 s**. Un **arbitro** che chiude lo
  stream in secondo piano la riporta a **0,27 s**: su Windows con Ollama 0.34.4 la chiusura
  ferma davvero la generazione. La ripresa costa poco (prompt in cache, 40–60 ms).
  **Ma un prefill già iniziato non si interrompe**: con un prompt nuovo di 8k token la voce
  aspetta comunque ~2,2 s. I prompt lunghi in secondo piano vanno spezzati.
- **Raccomandazione.** Oggi niente recupero: un elenco **fisso per livello** di 25–40 tool
  nativi, con la frase anti-testo nel prompt e `TextCallGuard` com'è. Il recupero (bge-m3 su
  CPU, k=8 più il nucleo) si prepara nel registro ma si accende solo sopra ~40–50 tool, o
  per le entità di casa. Per Home Assistant: comandi deterministici prima dell'LLM, poi tool
  con entità in `enum`. Agenti solo per lavori a più passi, dietro l'arbitro. Dettagli nella
  sezione 6.

---

## 1. Stato dell'arte (settembre 2026)

Ricerca sul web del 26/09/2026. [V] = fonte primaria, [S] = secondaria, [D] = deduzione.

### Benchmark e degrado con il numero di tool

- **BFCL** è alla V4 (classifica aggiornata il 12/04/2026, [leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html),
  [paper ICML 2025](https://proceedings.mlr.press/v267/patil25a.html)). Numeri dichiarati dai
  produttori [V]:
  - Qwen3.5: 4B 50,3, 9B 66,1, 35B-A3B 67,3 ([4B](https://huggingface.co/Qwen/Qwen3.5-4B),
    [35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B));
  - xLAM-2-8b-fc-r: 72,8 su BFCL v3, con licenza non commerciale
    ([APIGen-MT](https://arxiv.org/html/2504.03601));
  - Gemma 4 dichiara solo τ2: E2B 24,5 %, **E4B 42,2 %**, 26B-A4B 68,2 %
    ([model card](https://huggingface.co/google/gemma-4-E4B)).
  - Per E4B non esiste un BFCL ufficiale.
- **When2Call** (NVIDIA, NAACL 2025) misura quando *non* chiamare e quando chiedere
  chiarimenti. Nessun modello è vicino al massimo e la taglia non aiuta in modo affidabile
  ([paper](https://arxiv.org/html/2504.18851)) [V]. È il nostro problema delle «capacità
  inventate».
- **NESTFUL** (chiamate annidate): il migliore arriva al 25 % di sequenze esatte
  ([arXiv](https://arxiv.org/abs/2409.03797)) [V]. Le catene di tool restano difficili per tutti.
- **Troppi tool**:
  - RAG-MCP: filtrare i tool porta la selezione dal 13,6 al 43,1 %
    ([arXiv](https://arxiv.org/abs/2505.03275)) [V];
  - LongFuncEval: cali dal 7,6 all'85,6 % allargando il catalogo, con effetto della
    posizione ([arXiv](https://arxiv.org/html/2505.10570v1)) [V];
  - MCP-Bench: llama-3.1-8b scende da 0,438 a 0,415 con più server
    ([arXiv](https://arxiv.org/abs/2508.20453)) [V];
  - Less-is-More (DATE 2025, dispositivi edge): far dichiarare al modello i tool che gli
    servono e poi filtrarli riduce del 70 % il tempo ([arXiv](https://arxiv.org/abs/2411.15399)) [V].
  - Questi studi usano centinaia di tool MCP in inglese, spesso con descrizioni lunghe.
    **Il nostro banco (40 tool italiani con descrizioni brevi) non mostra il degrado**
    (sezione 3.1).

### Tecniche per molti tool

- **Recupero dei tool.**
  - TinyAgent (Berkeley, [arXiv 2409.00608](https://arxiv.org/abs/2409.00608)) è il caso più
    vicino al nostro. Un classificatore DeBERTa da 16 tool raggiunge un richiamo di 0,998,
    contro 0,949 di un RAG a embedding. Il fine-tuning porta TinyLlama-1.1B dal 12,7 al 78,9 %
    e un 7B dal 41 all'83 %.
  - Toolshed ([HF](https://huggingface.co/papers/2410.14594)) e Re-Invoke
    ([arXiv](https://arxiv.org/abs/2408.01875)) arricchiscono i documenti dei tool con domande
    sintetiche: da +20 a +56 punti di richiamo.
  - ToolRet (ACL 2025): gli embedder generici non sono esperti di tool
    ([ACL](https://aclanthology.org/2025.findings-acl.1258/)) [V].
  - Da noi le frasi d'esempio valgono +4 punti con bge-m3 e +9 con nomic (sezione 3.2).
- **Tool search nei prodotti** [V]:
  - Anthropic `defer_loading` con tool search ([engineering](https://www.anthropic.com/engineering/advanced-tool-use)):
    Opus 4 passa dal 49 al 74 %. Consigli: usarlo oltre 10 tool, lasciare sempre caricati i 3–5
    più usati, e gli esempi d'uso portano i parametri complessi dal 72 al 90 %.
  - OpenAI `tool_search` ([docs](https://developers.openai.com/api/docs/guides/tools-tool-search))
    carica gli schemi trovati **in fondo al contesto**, per non invalidare la cache del prompt;
    `allowed_tools` restringe i tool chiamabili senza cambiare l'elenco.
  - Sono pensati per modelli grandi. **Con un 4B il meta-tool di ricerca non funziona**
    (sezione 3.4).
- **Home Assistant e LLM locali** [V]:
  - con i modelli locali consiglia di esporre meno di 25 entità
    ([integrazione Ollama](https://www.home-assistant.io/integrations/ollama/));
  - suggerisce due agenti distinti, uno per la chiacchiera e uno per il controllo;
  - «Preferisci gestire i comandi localmente» prova prima gli intenti a regole e passa all'LLM
    solo se falliscono;
  - `GetLiveContext` legge lo stato su richiesta invece di metterlo nel prompt
    ([MCP server](https://www.home-assistant.io/integrations/mcp_server/)).
- **Decodifica vincolata**: `format` di Ollama compila uno JSON Schema in grammatica
  ([blog](https://ollama.com/blog/structured-outputs), [docs](https://docs.ollama.com/capabilities/structured-outputs)) [V].
  È utile per stadi di classificazione, ma non si combina con lo streaming del testo parlato.
- **Few-shot e schemi compatti**: gli esempi aiutano i modelli grandi (Anthropic, sopra). Su
  gemma4:e4b, messi come testo nel prompt, **peggiorano** (sezione 3.7).

### Fine-tuning e modelli specializzati

- TinyAgent, APIGen/xLAM, **Hammer 2.1** (0,5–7B, *function masking*,
  [arXiv](https://arxiv.org/html/2410.04587v2)) e ToolACE mostrano che un LoRA su dati
  sintetici porta un 1–7B sopra i modelli generalisti sui *propri* tool [V].
- **FunctionGemma** (Gemma 3 da 270M, dicembre 2025): passa dal 58 all'85 % su «Mobile
  Actions» dopo il fine-tuning ([HF](https://huggingface.co/google/functiongemma-270m-it),
  [InfoQ](https://www.infoq.com/news/2026/01/functiongemma-edge-function-call/)). È su Ollama
  come `functiongemma`; senza fine-tuning fa 9,4 % su HA assist-mini (ricerca del 21/09).
- Su Ollama ci sono anche `granite4` (350m–32b-a9b, Apache 2.0). xLAM c'è solo come upload
  della community (`allenporter/xlam`) e ha licenza non commerciale. Hammer non c'è (import da HF).
- Un blog riporta oltre il 95 % sui propri tool per Qwen3-4B e Gemma 4 E4B dopo un QLoRA su
  ~600 esempi ([ertas.ai](https://www.ertas.ai/blog/on-device-tool-calling-2026-qwen3-gemma4-phi4)).
  Fonte secondaria, non verificata.

### Ollama (v0.34.4 stabile, 0.40.0-rc0 uscita il 25/09)

- Il renderer gemma4 mette `<|think|>`, prompt di sistema **e dichiarazioni dei tool** nel
  turno di sistema iniziale ([gemma4.go](https://github.com/ollama/ollama/blob/main/model/renderers/gemma4.go)) [V].
  Misurato qui: cambiare l'elenco dei tool rivaluta tutta la storia (sezione 3.9).
- Bug aperti su gemma4 da conoscere:
  - [#18468](https://github.com/ollama/ollama/issues/18468): i parametri chiamati
    `description`, `type`, `properties`, `required` e `nullable` vengono scartati. Nei nostri
    schemi non ci sono: **da evitare anche in futuro**;
  - [#18649](https://github.com/ollama/ollama/issues/18649): chiamate rifiutate per
    spazzatura dopo le graffe.
- `OLLAMA_NUM_PARALLEL` vale 1, la coda è FIFO, `OLLAMA_MAX_LOADED_MODELS` vale 3 per GPU
  ([FAQ](https://docs.ollama.com/faq)) [V].

---

## 2. Il banco di prova

In `docs/ricerche/banchi/ricerca_tool/`. Nessun file di Calliope è stato modificato: `banco.py` importa solo
`TextCallGuard` da `brain.py`.

- **`catalogo.py`**: 40 tool finti in 13 categorie, con descrizioni nello stile di
  `tools/builtin.py`, due frasi d'esempio ciascuno (parafrasi, mai le frasi di prova) e un
  risultato finto costruito dagli argomenti.
  - Categorie: tempo e calcoli, timer, agenda, meteo e notizie, casa (9 tool con `stanza` in
    `enum`), musica (5), biblioteca, memoria, persone, voce, messaggi, liste, PC e file.
  - I 10 tool di oggi ci sono tutti con le loro descrizioni.
  - Sottoinsiemi annidati 5 ⊂ 10 ⊂ 20 ⊂ 40: il 10 è esattamente il Calliope di oggi.
  - Ci sono anche 12 meta-tool (uno per categoria, con `azione` in `enum`).
- **`richieste.py`**: 119 richieste vocali italiane, 21 prese dalle registrazioni reali
  (`prove/riferimenti_whisper.tsv`). Per tipo:
  - 56 dirette e 24 colloquiali;
  - 5 con errori di trascrizione («Che ore so», «Alliope», «Accendi la lucina cucina», «Tymer»);
  - 14 senza tool: cultura, chiacchiere, «Oggi è proprio una bella giornata»;
  - 5 capacità assenti: pizza, taxi, «Disattiva l'allarme», che **non ha** un tool;
  - 4 ambigue, per esempio «Ricordami di comprare il latte», che è promemoria o lista ma
    non `ricorda`;
  - 6 doppie;
  - 5 seguiti con storia («E in camera?», «Più forte», «Spegnila»).
  - Ogni richiesta ha gli esiti accettati (tool e argomenti chiave); per le domande di cultura
    è accettata anche `biblioteca_cerca`.
- **`banco.py`**: ciclo di tool calling come `brain.py`.
  - API nativa `/api/chat` in streaming, `num_ctx` 16384 (lo stesso di Calliope, quindi nessun
    ricaricamento), `think=false`, temperatura 0,3, fino a 3 giri, risultati finti;
    `TextCallGuard` vera.
  - Misure:
    - **tool giusto**: stesso insieme di tool di un esito accettato;
    - **argomenti**: i valori chiave sono contenuti, senza accenti né maiuscole;
    - **falsi**: tool chiamato quando non serviva;
    - **mancati**;
    - **scritte come testo**: salvate dalla guardia;
    - **fughe**: sintassi di tool finita nel testo parlato;
    - **decisione**: primo token o chiamata completa;
    - **primo testo**: primo pezzo di testo rilasciato al TTS, dopo i giri di tool.
  - Con un sottoinsieme piatto, le richieste il cui tool non c'è diventano «fuori catalogo»
    e la risposta giusta è non chiamare nulla. Per le doppie vale il sottoinsieme disponibile.
- **Condizioni**: portatile con Calliope **accesa** (Whisper e gemma4 in VRAM) e un lavoro di
  cancellazione dell'eco sulla CPU. Una sola ripetizione per strategia.
  - I tempi hanno rumore: in un tratto del giro con nomic la prompt eval è salita a 1–2 s per
    contesa esterna; lì valgono solo le accuratezze.
  - Differenze di latenza sotto ~0,1 s tra giri diversi non sono significative.
  - Differenze di 1–2 richieste su 100 nemmeno.

---

## 3. Risultati su gemma4:e4b-it-qat

Tabella completa: `docs/ricerche/banchi/ricerca_tool/riassunto.py e4b`. «Con tool atteso» = richieste per cui
esiste un tool nel catalogo della strategia; «comuni» = le 16 risolvibili già con 5 tool.
Tempi in secondi (mediana / p90); «primo testo» sulle sole richieste con tool.

| Strategia | Tool giusto | + argomenti | Comuni | Falsi senza tool | Falsi fuori catalogo | Mancati | Scritte come testo | Fughe | Decisione | Primo testo | Token prompt | Prompt ms | Stadio prima |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| piatto5 | 16/16 | 100 % | 100 % | 0/19 | 10/84 | 0 | 11 | 1 | 0,10 / 0,33 | 0,51 / 0,73 | 583 | 72 | — |
| piatto10 (oggi) | 24/24 | 100 % | 100 % | 0/19 | 6/76 | 0 | 8 | 0 | 0,11 / 0,37 | 0,56 / 0,78 | 878 | 67 | — |
| piatto20 | 63/65 (97 %) | 95 % | 100 % | 0/19 | 2/35 | 2 | 28 | 0 | 0,14 / 0,55 | 0,64 / 0,91 | 1983 | 73 | — |
| **piatto40** | **99/100** | **98 %** | 100 % | 0/19 | — | 1 | 49 | 0 | 0,22 / 0,63 | 0,63 / 0,91 | 3376 | 89 | — |
| **piatto40 + frase anti-testo** | **99/100** | **98 %** | 100 % | 0/19 | — | 0 | **35** | 1 | 0,20 / 0,45 | 0,41 / 0,64 | 3397 | 64 | — |
| rag bge-m3 k=3 (+4 nucleo) | 96 % | 95 % | 100 % | 1/19 | — | 2 | 49 | 1 | 0,26 / 0,49 | 0,50 / 0,65 | 778 | 131 | 23 ms |
| rag bge-m3 k=5 | 96 % | 95 % | 100 % | 1/19 | — | 1 | 47 | 0 | 0,48 / 0,90 | 0,90 / 1,26 | 938 | 294 | 31 ms |
| rag bge-m3 k=5 + frase anti-testo | 97 % | 96 % | 100 % | 0/19 | — | 1 | 26 | 2 | 0,35 / 0,59 | 0,54 / 0,78 | 959 | 167 | 23 ms |
| rag bge-m3 k=8 | 97 % | 96 % | 100 % | 1/19 | — | 3 | 51 | 0 | 0,51 / 0,96 | 0,95 / 1,30 | 1191 | 333 | 31 ms |
| rag nomic k=5 | 87 % | 86 % | 100 % | 1/19 | — | 11 | 41 | 1 | (rumore) | (rumore) | 915 | — | 23 ms |
| categoria da embedding (top 3) | 96 % | 95 % | 88 % | 0/19 | — | 2 | 44 | 1 | 0,39 / 0,75 | 0,75 / 1,10 | 932 | 187 | 29 ms |
| categoria dall'LLM (formato) | 94 % | 93 % | 94 % | 0/19 | — | 2 | 46 | 0 | 0,89 / 1,25 | 1,20 / 1,59 | 672 | 188 | 483 ms |
| meta-tool (12) | 90 % | 83 % | 100 % | 0/19 | — | 6 | 52 | 1 | 0,14 / 0,73 | 0,66 / 1,01 | 1618 | 82 | — |
| `cerca_strumenti` + nucleo | 47 % | 47 % | 75 % | 0/19 | — | 47 | 14 | 0 | 0,09 / 0,40 | 0,23 / 1,04 | 656 | 56 | — |
| scelta con formato JSON vincolato | 96 % | 87 % | 88 % | 0/19 | — | 3 | 0 | 0 | 1,31 / 1,75 | 1,55 / 2,12 | 334 | 113 | 1315 ms |
| piatto40 + esempi nel prompt | 92 % | **47 %** | 100 % | 1/19 | — | 8 | **86** | 0 | 0,09 / 0,11 | 0,33 / 0,51 | 3502 | 58 | — |
| piatto40 + thinking (solo 1° giro) | 100 % | 99 % | 100 % | 0/19 | — | 0 | 0 | 0 | 3,69 / 7,59 | 3,96 / 5,64 | 3378 | 159 | — |
| rag bge-m3 k=5 + thinking | 96 % | 95 % | 100 % | 0/19 | — | 2 | 0 | 0 | 2,19 / 5,37 | 2,48 / 5,47 | 940 | 186 | 23 ms |

Per tipo di richiesta (piatto40): ambigue 4/4, ASR 5/5, assenti 5/5, colloquiali 24/24,
dirette 55/56, doppie 6/6, seguiti 5/5, senza tool 14/14.

### 3.1 Numero di tool piatti

- **Nessun degrado di scelta da 5 a 40**: 100 % sulle comuni in tutti e quattro i casi. Su
  tutte quelle con tool: 16/16, 24/24, 63/65, 99/100.
- L'unico errore a 40 è «Metti il riscaldamento a ventuno gradi»: chiede la stanza. Gli
  errori a 20 sono di questo tipo o di tool vicini («Passa alla prossima canzone» →
  `musica_pausa`, perché a 20 `musica_successiva` non c'è).
- **Con meno tool aumentano i falsi fuori catalogo**: 10 a 5 tool, 6 a 10. Il modello usa il
  tool più vicino che ha («Ricordami di comprare il latte» → `ricorda`, «Ho salvato…»,
  anche a 10 tool con la frase anti-testo) oppure **ripesca dalla storia** un tool che non
  vede più («E in camera?» → `luce_accendi`).
  - Conferma pratica di due regole già nel codice: il ricontrollo del permesso in
    `ToolRegistry.call` e l'errore «tool sconosciuto».
  - Un elenco di tool che cambia a metà conversazione è pericoloso proprio per questo.
- **Latenza**: a elenco fisso il prefisso è in cache e 40 tool (3400 token) costano ~20–30 ms
  di prompt eval in più rispetto a 10.
  - La decisione sale da 0,11 a 0,22 s di mediana, ma la prima frase con tool resta
    0,56–0,63 s.
  - Il primo turno freddo (tool nuovi, cache vuota) costa ~0,6 s per 2100 token (sonda
    `sonda_cache.py`): succede solo al primo turno dopo un cambio di elenco.

### 3.2 Recupero per similarità

`recupero.py`, senza LLM, 100 richieste con tool atteso. Il nucleo fisso è `ora_attuale`,
`data_oggi`, `chi_parla` e `ricorda`; k = tool recuperati in più.

| Embedding | Esempi nei documenti | Con il turno prima | r@3 | r@5 | r@8 | r@12 | categorie dei top 3 | ms (med / p90) |
|---|---|---|---|---|---|---|---|---|
| nomic-embed-text | no | no | 0,73 | 0,78 | 0,82 | 0,87 | 0,81 | 18 / 55 |
| nomic-embed-text | sì | sì | 0,83 | 0,87 | 0,89 | 0,91 | 0,87 | 18 / 52 |
| bge-m3 | no | no | 0,92 | 0,95 | 0,96 | 0,98 | 0,96 | 22 / 71 |
| bge-m3 | sì | no | 0,96 | 0,97 | **1,00** | 1,00 | 0,96 | 22 / 71 |
| **bge-m3** | **sì** | **sì** | **0,98** | **0,98** | **1,00** | 1,00 | 0,98 | 21 / 69 |
| bge-m3 su CPU (`num_gpu 0`) | sì | — | | | | | | **34 / 45** |
| nomic su CPU | sì | — | | | | | | 25 / 31 |

- **bge-m3 è nettamente migliore** di nomic sull'italiano, e le **frasi d'esempio** aiutano
  (+4 punti). Per i seguiti («E a Roma?») serve accodare **la richiesta precedente** alla query.
- **Su CPU costa 34 ms e zero VRAM**: è la collocazione giusta per l'8 GB. Su GPU bge-m3
  occupa ~0,5–0,8 GiB oltre a gemma4 e Whisper (lettura di `nvidia-smi` incerta su WDDM). Ci
  sta (gemma4 non è stato sfrattato: `load_duration` 0,07 s dopo gli embedding), ma è VRAM
  tolta alla biblioteca. Con un LLM da 5 GB (qwen3:8b) invece **non ci sta**: Ollama scarica e
  ricarica a turno LLM ed embedding e ogni richiesta costa ~8,5 s (sezione 4).
- Nel ciclo completo il recupero dà **96–97 %, cioè quanto il piatto**, e costa di più: la
  prompt eval sale da ~70 a ~300 ms perché l'elenco dei tool cambia a ogni richiesta. Gli
  errori propri del recupero sono 2 richieste su 100 a k=5 (atteso non offerto: «Metti
  qualcosa di Lucio Dalla» → biblioteca; «Anzi, facciamo dodici»), 0 a k=8.
- La **categoria da embedding** (tutti i tool delle categorie dei primi 3) non aggiunge nulla
  e perde le doppie tra categorie diverse.

### 3.3 Due stadi con l'LLM (categoria, poi i tool)

Primo stadio con `format` JSON (enum di 13 categorie, al massimo 2):
- costa **0,48 s** di mediana e porta la prima frase a 1,2 s;
- sbaglia categoria in 5 casi su 100 («Chiamami Dario» → memoria, «Inserisci l'allarme» →
  nessuna).

È il classico router LLM da 200–500 ms della ricerca del 21/09: da non mettere sul percorso
vocale. Nota positiva dalla sonda sulla cache: la chiamata del router con un altro prompt
**non sfratta** la cache della conversazione (Ollama 0.34.4 conserva più prefissi).

### 3.4 Meta-tool e «tool search»

- **Meta-tool** (`casa(azione, stanza, valore)`, `musica(azione, …)`, …) arrivano al 90 %,
  con argomenti all'83 %. Gli errori tipici:
  - non chiama `orologio(azione=calcola)` e fa i conti a mente;
  - chiede la stanza invece di agire;
  - inventa nomi composti (`musica_alza_volume`, `timer_annulla_timer`);
  - una volta scrive `computer:cerca_file{…}` come testo.
  - Il parametro `valore` generico («percentuale o gradi o posizione») è più difficile dei
    parametri con nome. **Da evitare**: i tool fini con nomi parlanti sono più facili per un 4B.
- **`cerca_strumenti`** (nucleo + un tool che aggiunge gli schemi trovati) arriva al 47 %.
  Anche con l'istruzione esplicita «non dire che non puoi prima di averlo cercato», il
  modello risponde «Non ho la possibilità di controllare gli apparecchi di casa» in 47 casi
  su 100 e fa i conti a mente. Il meccanismo di Anthropic e OpenAI presuppone un modello che
  ragiona sul proprio catalogo: **non adatto a un 4B senza thinking**.

### 3.5 Formato vincolato (grammatica)

La scelta con uno schema JSON (`tool` in `enum` dei 40 nomi, argomenti liberi, elenco
compatto dei tool nel prompt), seguita da una risposta senza tool:
- non produce mai chiamate scritte come testo;
- sceglie bene (96 %) ma sbaglia gli argomenti: 87 %, con `stanza: "salotto"` fuori dall'enum
  perché gli argomenti non erano vincolati, e chiavi come `cosa?` ricopiate dall'elenco
  compatto;
- aggiunge 1,3 s: il JSON si genera tutto prima di parlare, e per le richieste senza tool
  serve una seconda chiamata.

Vincolare anche gli argomenti (`anyOf` per tool) migliorerebbe la validità, non la latenza.
**Utile per classificatori in secondo piano, non per la voce.**

### 3.6 Thinking solo per la scelta

- Acceso al primo giro dà il 100 % e zero chiamate come testo, ma la decisione sale a 3,7 s di
  mediana e 7,6 s al p90 (a 40 tool; 2,2 s con k=5).
- Conferma la ricerca del 21/09: il thinking resta per gli agenti in secondo piano.

### 3.7 Esempi few-shot nel prompt

Sei esempi scritti come «frase → tool con argomenti» nel prompt di sistema:
- il modello **imita il formato** e risponde a voce «calcola con espressione 17*6»;
- 86 chiamate su 100 sono scritte come testo e gli argomenti giusti scendono al 47 %.

Gli esempi, se servono, vanno nelle **descrizioni dei tool** (lì aiutano il recupero) o come
turni finti con chiamate vere nella storia, non come testo nel prompt.

### 3.8 Chiamate scritte come testo

`sonda_testo.py`: rifà il primo turno delle 101 richieste con tool di piatto40, senza streaming.

| Variante | Chiamate native | Nel testo: `nome(…)` | `nome{…}` | token speciali gemma | nome nudo |
|---|---|---|---|---|---|
| prompt del banco, T 0,3 | 49/101 | 40 | 7 | 2 | 1 |
| prompt del banco, T 0 | 54/101 | 39 | 5 | 2 | 0 |
| + «emetti sempre una chiamata di funzione vera, mai il suo nome scritto nel testo» | **72/101** | 27 | 1 | 0 | 0 |

- Quasi tutte sono **Python** (`timer_imposta(minuti=90, nome="timer")`, `calcola(80*0.15)`):
  il modello sceglie di scrivere codice. Solo 2 su 101 sono token nativi di gemma non
  riconosciuti dal parser.
- **Crescono con il numero di tool**: 8 su 29 chiamate a 10 tool, 28 a 20, 49 a 40.
- La temperatura non conta; la frase nel prompt sì (−30 %; nel banco completo da 49 a 35).
- **Non costano latenza**: a 40 tool la prima frase è 0,60 s con le chiamate come testo e
  0,70 s con quelle native. Le native aspettano la chiamata intera.
- Il rischio è la guardia: 0–2 fughe su 119, per esempio
  «calliope.cambia_voce(voce="paola")» con un prefisso che la guardia non conosce e
  «call_cambia_voce(…)».
  - «Chiamerò ora_attuale per sapere che ora è» detto a voce è un annuncio, non una chiamata.
- **Due estensioni semplici di `TextCallGuard`**: accettare un prefisso `parola.` o `call_`
  davanti al nome, e scartare dal parlato le frasi che contengono il nome di un tool.

### 3.9 Cache del prefisso: quanto costa cambiare i tool

`cache.py`: storia di 0–30 turni finti, 10 tool, `num_predict=1`, mediana di 3.

| Turni di storia | Token | A: tool fissi, domanda nuova | B: tool diversi | C: tool fissi + suggerimento variabile in coda | D: dopo un router con altro prompt |
|---|---|---|---|---|---|
| 0 | ~900 | 53 ms | 211 ms | 58 ms | 61 ms |
| 5 | ~1450 | 47 ms | 312 ms | 180 ms | 61 ms |
| 15 | ~2600 | 49 ms | 438 ms | 179 ms | 58 ms |
| 30 | ~4300 | 51 ms | **618 ms** | 176 ms | 56 ms |

(prompt eval; il tempo totale della chiamata aggiunge 20–190 ms)

- **B cresce con la storia**: il recupero ingenuo paga tutta la conversazione a ogni turno.
- **C** (i tool restano fissi, un messaggio variabile va dopo la storia) costa una quota
  fissa di ~0,18 s. È la via di OpenAI (schemi caricati in coda) resa con i mezzi di Ollama.
  Con gemma4 però i tool veri non si possono mettere in coda.
- **D**: un'altra richiesta con un prompt diverso non distrugge la cache della conversazione.

**Come ordinare prompt e tool** (vale anche per il resto del codice):
1. prompt di sistema fisso, senza ora, data, nome o livello di chi parla (già così);
2. tool **fissi per livello** e in ordine stabile (già così in `ToolRegistry`);
3. storia tagliata a blocchi (già così in `Brain._trim_history`);
4. tutto ciò che varia (ricordi, stato della casa, suggerimenti) in un messaggio di sistema
   **subito prima della domanda** (già così per la memoria);
5. se un giorno serve il recupero, **cambiare l'elenco solo a inizio conversazione** (dopo
   il risveglio) o al cambio di livello, non a ogni turno.

---

## 4. Altri modelli

Stesso banco, stesso prompt, `think=false`, una ripetizione. Tool giusto sulle richieste con
tool atteso; tra parentesi gli argomenti giusti. «Primo testo» = mediana sulle richieste con
tool. Chiamate come testo = salvate da `TextCallGuard`.

| Modello (VRAM reale) | piatto10 | piatto40 | rag bge-m3 k=5 | meta-tool | Primo testo a 40 tool | Chiamate come testo a 40 |
|---|---|---|---|---|---|---|
| **gemma4:e4b-it-qat** (~4,6 GiB a 16k) | **100 %** (100) | **99 %** (98) | 96 % (95) | 90 % (83) | **0,63 s** | 49 |
| gemma4:e2b-it-qat (~2,7 GiB) | 38 % (38) | 54 % (45) | 37 % (36) | 22 % (17) | 0,09 s | 37 |
| qwen3.5:4b (3,5 GB) | 67 % (67) | 95 % (94) | 92 % (91) | 94 % (90) | 0,70 s | 0 |
| qwen3:8b (5,2 GB) | 83 % (83) | 90 % (89) | 93 % (92)* | 87 % (85) | 1,22 s | 0 |

\* con qwen3:8b bge-m3 **non sta in VRAM insieme al modello**: Ollama scarica e ricarica i due
modelli a ogni richiesta (~8,5 s a richiesta, `ollama ps` vuoto tra una e l'altra). Solo
l'accuratezza è valida. Per confronto, ricaricare gemma4:e4b da zero (a fine prove) ha
misurato `load_duration` 8,5 s: il dato che la ricerca del 21/09 stimava in 3–6 s. Ogni
cambio di modello sul percorso vocale costa quindi circa 8 s.

- **gemma4:e2b non è un instradatore di tool utilizzabile**, contro l'ipotesi «riserva» della
  ricerca del 21/09:
  - fa i conti a mente («diciassette per sei fa diciotto»);
  - scrive «timer imposta 10 minuti» come testo senza sintassi, che nessuna guardia recupera;
  - chiama senza argomenti.
  - È velocissimo (0,06–0,09 s alla decisione) ma sbaglia una richiesta su due.
- **qwen3.5:4b** con 40 tool è vicino a e4b (95 %) e **non scrive mai le chiamate come
  testo**. Però:
  - sbaglia proprio i tool di Calliope (voce e identità): «usa la voce di Paola» →
    `elenca_voci` e poi dice «Va bene, sono tornata alla voce di Serena», un'azione
    dichiarata ma non fatta;
  - a 10 tool scende al 67 %;
  - il suo italiano era già stato giudicato scadente il 21/09.
- **qwen3:8b** non scrive chiamate come testo ma è più lento (1,2 s alla prima frase con
  tool) e meno preciso di e4b (90 %); occupa 5,2 GB.
- I meta-tool vanno meglio sui qwen (94 %) che su gemma4 (90 %), ma nessuno supera il piatto
  di e4b.
- **Conclusione**: per la scelta dei tool in italiano **gemma4:e4b resta il migliore dei
  modelli che stanno in 8 GB**, e il suo unico difetto (le chiamate in stile Python) è già
  coperto da `TextCallGuard`.

---

## 5. Agenti

### 5.1 Agente come tool: la casa (26 entità in stile Home Assistant)

`agenti.py casa`, 12 richieste: «la piantana in soggiorno», «il sottopensile della cucina»,
«tutte le tapparelle», «il comodino di Dario», sensori, prese, termostato.

- **diretto**: Calliope vede `casa_comando(entita, azione, valore)` e `casa_stato(entita)`,
  con `entita` in `enum` dei 26 id e l'elenco «id = nome (stanza)» nella descrizione;
- **agente**: Calliope vede `chiedi_alla_casa(richiesta)`. L'agente è lo stesso modello
  con prompt proprio (l'elenco con lo stato attuale, stile `GetLiveContext`), gli stessi due
  tool e una storia propria, e restituisce una frase.

| Modo | Giusti | Decisione | Primo testo a voce | Totale | Passate LLM |
|---|---|---|---|---|---|
| diretto | 12/12 | 0,49 s | **0,81 s** | 0,97 s | 2 |
| agente, Calliope riformula | 12/12 | 0,52 s | 1,61 s | 1,76 s | 4 |
| agente, frase fissa + frase dell'agente dritta al TTS | 12/12 | frase fissa a 0,52 s | 1,29 s | ~1,45 s | 3 |

(mediane; «Chiudi tutte le tapparelle»: 4 chiamate, 2,8 s diretto e 2,5 s con l'agente)

- Con 26 entità **il diretto è più veloce di 0,5–0,8 s e altrettanto preciso**. L'agente
  costa due passate LLM in più anche per un comando banale.
- Conviene quando le entità sono troppe per l'elenco di Calliope (centinaia) o il lavoro ha
  più passi (scenari, «prepara la casa per la notte»).
- Se l'agente c'è, la sua frase va **dritta al TTS**: la seconda passata di Calliope ripete
  solo quello che l'agente ha già detto.
- La stima vale per Home Assistant: con 25 entità esposte (il consiglio di HA per i modelli
  locali) si può fare a meno dell'agente.

### 5.2 Lavori in secondo piano e voce sulla stessa GPU

`agenti.py contesa`, 3 ripetizioni.
- La voce è «Che ore sono?» con 10 tool: due passate.
- Lo sfondo è un agente che scrive una relazione (900 token), oppure riassume un documento
  di 18k caratteri.

| Scenario | Prima frase della voce | Note |
|---|---|---|
| voce da sola | **0,30 s** | |
| generazione lunga in corso, voce in coda | **11,07 s** | aspetta che lo sfondo finisca (900 token, 12,3 s) |
| generazione lunga, **arbitro**: chiude lo stream, poi la voce | **0,27 s** | lo sfondo si ferma a ~100 token; la chiusura della connessione interrompe davvero la generazione su Windows |
| ripresa dello sfondo dopo la voce | primo token 0,12 s | prompt dello sfondo ancora in cache (38 ms) |
| prompt lungo (18k caratteri), voce in coda | 3,26 s | |
| prompt lungo **nuovo** (8k token), arbitro dopo 0,3 s | **2,23–2,27 s** | **il prefill non si interrompe**: la voce aspetta la fine dei ~2,2 s di prompt eval (`prefill_annullato.txt`) |
| prompt lungo **nuovo**, voce in coda | 2,94–3,09 s | |

- **FIFO confermato**: senza arbitro un qualunque lavoro in secondo piano rende la voce
  inutilizzabile.
- **L'arbitro funziona** per la generazione: basta chiudere lo stream (httpx) quando parte
  una richiesta vocale. Meglio ancora all'inizio del parlato rilevato dal VAD, come proposto
  il 21/09: la frase più l'STT danno 0,5–2 s di margine. Ollama tiene il prefisso dello
  sfondo e la ripresa costa ~0,1 s.
- **Il prefill no**: un prompt lungo e nuovo occupa la GPU per tutta la sua prompt eval
  (~3700 token/s: 8k token ≈ 2,2 s). Quindi:
  1. i lavori in secondo piano **leggono a pezzi** (≤1000–1500 token nuovi per richiesta,
     ≈0,3–0,4 s), sfruttando la cache per il prefisso già letto;
  2. un nuovo pezzo parte solo se il VAD non sente parlato;
  3. nel caso peggiore la voce aspetta un pezzo (~0,4 s).
- La ripresa dopo l'interruzione riparte dal prompt, non dal punto interrotto. Conviene
  rimandare il testo già generato come messaggio assistant da continuare (da verificare con
  gemma4) oppure spezzare anche l'output in passi brevi.

---

## 6. Raccomandazione per Calliope

### Architettura

```
richiesta trascritta
  │
  ├─ 0. regole (già in calliope.py: esci, basta, conferme) — e in futuro i comandi di casa
  │     più frequenti in forma chiusa («accendi/spegni la luce in <stanza>»), < 10 ms
  │
  ├─ 1. Brain: UN elenco di tool FISSO per livello (ospite / familiare / amministra),
  │     25–40 tool nativi con nomi parlanti e parametri con nome, enum dove si può;
  │     il variabile (ricordi, stato casa) nel messaggio prima della domanda
  │     → TextCallGuard (estesa) → esecuzione nel registro, con ricontrollo del livello
  │
  ├─ 2. [dopo, sopra ~40–50 tool] ToolRegistry.select(query, livello, k):
  │     nucleo fisso + top-k da bge-m3 su CPU con documenti arricchiti,
  │     scelto UNA volta a inizio conversazione, ricalcolato solo se manca un tool
  │
  └─ 3. agenti come tool (chiedi_alla_casa, chiedi_alla_bibliotecaria, …) solo per lavori
        a più passi; la loro frase va dritta al TTS; in secondo piano dietro l'arbitro
```

- **Dove**:
  - la scelta dei tool sta nel **registro** (`ToolRegistry.schemas_for` oggi, un domani
    `select`), non in `Brain`: il registro conosce già livelli, rete e rischio, e `Brain`
    resta un ciclo generico;
  - il recupero ha bisogno di un indice (vettori dei documenti dei tool) costruito
    all'avvio, anche questo nel registro;
  - l'**arbitro** sta sopra `Brain`, dove si possono chiudere gli stream: è il pezzo della
    fase 2 (ciclo a eventi).
- **Valori**:
  - **nucleo sempre presente**: `ora_attuale`, `data_oggi`, `chi_parla`, `ricorda`,
    `dimentica`, `calcola`, `timer_imposta`;
  - **k = 8** se si accende il recupero: richiamo 1,00 contro 0,98 a k=5, e il costo dei
    tool in più è nullo quando l'elenco è in cache;
  - query = richiesta + richiesta precedente;
  - documenti = nome + descrizione + 2–3 frasi d'esempio;
  - nessuna soglia di similarità: sempre k tool;
  - modello di embedding: **bge-m3 su CPU**, 34 ms (già scelto per la biblioteca, quindi
    nessuna dipendenza nuova).
- **Prompt**:
  - aggiungere la frase «Per usare un tool emetti sempre una chiamata di funzione vera, mai
    il suo nome scritto nel testo» (−30 % di chiamate come testo);
  - togliere dal prompt i limiti che diventeranno falsi: «non comandi luci o dispositivi»
    va tolto quando arriva la casa;
  - niente esempi few-shot nel prompt.
- **`TextCallGuard`**: accettare prefissi `parola.` e `call_` davanti al nome. Resta
  indispensabile: con 40 tool un terzo delle chiamate passa di lì.

### Impatto atteso

- **Latenza**, dal 10 al 40 in cache:
  - +0,1 s di decisione, prima frase con tool ~0,6 s (0,4 s con la frase anti-testo);
  - il primo turno dopo un cambio di elenco costa ~0,2–0,6 s una volta;
  - il recupero, se usato a ogni turno, costerebbe 0,2–0,6 s: per questo si sceglie una
    volta a conversazione.
- **VRAM**:
  - 40 tool = ~2500 token in più nel contesto, trascurabile con `num_ctx` 16384 (prompt
    ~3400 su 16384);
  - bge-m3 su CPU non occupa VRAM;
  - nessun modello in più: agenti e router sono lo stesso gemma4 con altri prompt, e
    `num_ctx` deve restare identico.

### Piano per i tool della visione

1. **`calcola`** subito, nativo:
   - valutatore sicuro con `ast` (niente `eval`), `espressione` in cifre;
   - nel banco è stato chiamato 4 volte su 4 con 20 e 40 tool piatti e con il recupero, per
     esempio `calcola(80*0.15)`; con i meta-tool 2 su 4 e con `cerca_strumenti` 0 su 4 (conti
     a mente);
   - aggiungere al prompt «per i conti chiama calcola».
2. **Timer e promemoria** (fase 1 della visione):
   - nativi, con `minuti`/`secondi` interi e `quando` a parole interpretato in Python;
   - attenzione alla confusione **«ricordami di…» (promemoria) contro «ricordati che…»
     (memoria)**: con i due tool presenti il modello li separa (esito giusto nel piatto40);
     con il solo `ricorda` usa quello e dice «Ho salvato».
   - Errore di argomento da gestire nel codice: «avvisami tra mezz'ora» → `minuti=60` in
     **tutte** le strategie che hanno chiamato il timer, anche con il thinking. È un errore
     sistematico del modello («mezz'ora» letto come un'ora), che nessuna scelta dei tool
     corregge. Serve un parametro `durata` a parole («mezz'ora», «un'ora e mezza»)
     convertito in Python con regole.
3. **Casa** (Home Assistant, decisione A):
   - comandi chiusi a regole prima dell'LLM;
   - poi `casa_comando`/`casa_stato` con le entità **esposte** in `enum` (≤25–40, come
     consiglia HA), stato letto su richiesta;
   - **nessun tool di disinserimento dell'allarme**: nel banco «Disattiva l'allarme» non ha
     mai chiamato `allarme_inserisci`.
4. **Musica, biblioteca, messaggi, liste, file, PC**: tool fini con nomi parlanti (`musica_*`,
   `biblioteca_cerca`…), non meta-tool con `azione`.
5. **Oltre ~40–50 tool** (MCP, entità di casa in più): accendere `select` con bge-m3 su CPU
   e rifare `prove/prova_tool_scala.py` con il catalogo vero.
6. **Agenti** solo per il livello 3 della visione (lavori a più passi), dietro l'arbitro, con
   pezzi di prompt ≤1500 token.

### Modello diverso o fine-tuning?

- **Modello**: nessun cambio.
  - Tra i candidati che stanno in 8 GB, gemma4:e4b è il più preciso sui tool italiani (99 % a
    40 tool) e anche il più rapido a 40 tool.
  - qwen3.5:4b è l'unica alternativa sensata sui tool (e non scrive chiamate come testo), ma
    sbaglia i tool di identità e voce e ha un italiano peggiore.
  - granite4 e i modelli specializzati (xLAM, Hammer) non sono stati provati: xLAM ha licenza
    non commerciale; Hammer e granite4.1 si possono aggiungere al banco con una riga
    (`--modello`).
- **Fine-tuning**: **non ora**.
  - Il problema che risolverebbe (scelta del tool) oggi non c'è: 99 %.
  - Gli errori che restano non sono di scelta: «mezz'ora» → 60 minuti, stanza chiesta invece
    di presumere, chiamate in stile Python. Si risolvono meglio nel codice (argomenti a parole
    convertiti in Python, guardia) e nel prompt.
  - Un LoRA andrebbe rifatto a ogni cambio di modello (e lo Spark ne porterà uno nuovo) e
    costerebbe il riaddestramento a ogni tool nuovo.
  - Diventa interessante in due casi:
    1. un **instradatore minuscolo** (FunctionGemma 270M o un classificatore stile TinyAgent)
       se un giorno i tool diventano centinaia e il recupero non basta;
    2. far emettere a gemma4 sempre chiamate native.
  - Il banco di `docs/ricerche/banchi/ricerca_tool/` è già il set di valutazione per entrambi. Per il punto 2 conta
    di più passare a una versione di Ollama o di gemma4 che non scriva chiamate come testo:
    da riprovare con Ollama 0.40.

### Sullo Spark

- Con 128 GB unificati e MoE da 3–4B attivi (`gemma4:26b`: τ2 68 % contro 42 % di E4B;
  `qwen3.5:35b-a3b`) la scelta dei tool migliora, e soprattutto un modello più grande regge il
  «tool search» e il thinking breve.
- Ma la prompt eval pesa di più (più parametri totali da attraversare per token di prompt,
  banda di memoria condivisa): **la regola «elenco fisso, variabile in coda» vale ancora di
  più**. Da misurare lì con lo stesso banco.
- Più modelli residenti permettono un agente in secondo piano su un modello diverso da
  quello della voce, ma la banda è comune: l'arbitro resta.

---

## 7. Rischi e cose non verificate

- **Catalogo e richieste scritti da me**:
  - le descrizioni sono chiare e i tool ben separati;
  - un catalogo MCP vero (descrizioni lunghe, nomi simili, 100+ tool) potrebbe degradare
    come nei benchmark;
  - gli esempi dei tool sono parafrasi delle richieste, non copie, ma vengono dalla stessa
    mano.
  - Da ripetere con i tool veri quando esistono.
- **Una sola ripetizione per strategia**, a temperatura 0,3: differenze di 1–3 richieste
  non sono significative.
- **Tempi rumorosi**: Calliope accesa e un lavoro AEC in parallelo. La colonna di nomic è
  inutilizzabile per i tempi.
- **Solo testo**: nessuna prova a voce, gli errori di trascrizione sono simulati (5 frasi).
- **Seguiti**: solo 5, con storie brevi. La conversazione lunga (dove gemma scriveva
  `chi_parla{}` a metà) è coperta da `prova_prompt_conversazione.py`, non da questo banco.
- **VRAM di bge-m3 su GPU**: le letture di `nvidia-smi` su WDDM sono incoerenti
  (0,5–0,8 GiB); non importa se si usa la CPU.
- **Prefill interrotto**: provato solo con Ollama 0.34.4 su Windows. La 0.40 (in RC) potrebbe
  cambiare lo scheduler.
- **Cache multipla** (la sonda D e la ripresa dello sfondo): comportamento osservato, non
  documentato; potrebbe dipendere dalla RAM libera per la cache dei prompt di llama-server.

## 8. File

| File | Cosa |
|---|---|
| `docs/ricerche/banchi/ricerca_tool/catalogo.py` | 40 tool finti, sottoinsiemi 5/10/20/40, nucleo, 12 meta-tool |
| `docs/ricerche/banchi/ricerca_tool/richieste.py` | 119 richieste vocali con esiti accettati |
| `docs/ricerche/banchi/ricerca_tool/banco.py` | il banco: strategie, ciclo di tool calling, punteggio |
| `docs/ricerche/banchi/ricerca_tool/recupero.py` | richiamo@k degli embedding, tempi GPU/CPU, VRAM |
| `docs/ricerche/banchi/ricerca_tool/cache.py`, `sonda_cache.py` | costo della cache del prefisso |
| `docs/ricerche/banchi/ricerca_tool/sonda_testo.py` | forma delle chiamate scritte come testo |
| `docs/ricerche/banchi/ricerca_tool/agenti.py` | agente casa e contesa della GPU |
| `docs/ricerche/banchi/ricerca_tool/riassunto.py` | tabelle dai risultati (`--errori` per l'elenco degli sbagli) |
| `docs/ricerche/banchi/ricerca_tool/giro_modelli.sh` | il confronto tra modelli |
| `docs/ricerche/banchi/ricerca_tool/risultati/` | JSONL per richiesta e strategia, log |
| `prove/prova_tool_scala.py` | rifà in breve la misura (modello, strategie, limite) |
