# 0011. Un modello veloce davanti, agenti dietro

- **Stato**: accettata (visione del 21/09; architettura sulla DGX dal 02/10/2026; voce sul 26B dal
  06/10)
- **Area**: [agenti-estensioni](../aree/agenti-estensioni.md), [voce-e-regole](../aree/voce-e-regole.md)

## Contesto

La voce deve rispondere in meno di un secondo; un lavoro vero (scrivere un programma, un documento
lungo, una ricerca) richiede un modello più grande, il ragionamento acceso e minuti. Il 21/09 con
`qwen3:8b` la prima frase passava da 0,57 s a 4,96 s accendendo il ragionamento. Sulla DGX i due
mondi condividono la stessa GPU: un lavoro lungo in coda faceva arrivare la prima frase della voce
a 11 s (su Ollama) o a 32 s.

## Decisione

- **Davanti**, il modello della voce: `gemma4:26b-a4b-it-qat` su Ollama (MoE, 74–79 token/s, banco
  143/144, prima frase 0,68 / 1,18 s al p90), scelto con `llm_profilo`; il 4B
  (`gemma4:e4b-it-qat`) resta il profilo del portatile. Risponde subito oppure delega: «ci penso, ti
  faccio sapere».
- **Dietro**, gli agenti: `Qwen3.6-35B-A3B` (NVFP4) su **vLLM**, con finestra di 131 072 token e un
  tetto al ragionamento. Lavori in secondo piano che sopravvivono ai riavvii, domande a metà lavoro,
  codice nella sandbox ([0012](0012-sandbox-docker.md)).
- Il **ciclo dell'agente è scritto in proprio** (~500 righe), senza framework.
- Un **arbitro** dà la precedenza alla voce: quando qualcuno parla mette in **pausa** vLLM
  (`/pause?mode=keep`, 56 ms) e lo riprende dopo (5 ms). Con un agente al lavoro la prima frase passa
  da 2,02 s (p90 4,21) senza arbitro a 0,75 s (p90 1,48) con la pausa, e le generazioni dell'agente
  finiscono comunque.

## Alternative considerate

- **Un solo modello per tutto** (il 26B): il più debole su codice e documenti lunghi.
  **`gpt-oss:120b` come agente**: più debole sul codice, italiano non dichiarato, ragionamento non
  spegnibile.
- **Voce su vLLM** (26B NVFP4): 112/116 sul banco, ma 29 token/s e prima frase 0,90 s di mediana;
  scartata per la voce il 03/10.
- **Agente su Ollama o llama-server**: errori di memoria CUDA con i tool di qwen3.6 su Ollama, un bug
  noto del parser; superato il 02/10 con vLLM.
- **Framework per agenti** (OpenAI Agents SDK, LangGraph/LangChain, CrewAI, AutoGen/AG2, Pydantic
  AI, smolagents, LlamaIndex, Google ADK, Agno, Strands…): nessuno modella la convivenza di una
  richiesta vocale urgente e di un lavoro lungo sulla stessa GPU, quindi l'arbitro andava scritto
  comunque. In più: dipendenze senza wheel ARM (`tiktoken`, `cryptography` via `mcp`, LiteLLM),
  framework instabili o in manutenzione, prompt nascosti, quasi tutti asyncio mentre il percorso
  della voce è a thread. Piano B per il solo secondo piano: Pydantic AI o MAF.
- **Chiudere lo stream dell'agente** invece della pausa: la voce era veloce (0,73 s) ma l'agente non
  finiva mai (60 stream ceduti, 0 finiti).

## Conseguenze

- Memoria della DGX divisa: ~0,40 all'agente su vLLM, la voce su Ollama, restare sotto ~0,7 in tutto.
- La pausa di vLLM usa un endpoint senza chiave su 127.0.0.1; dopo un'uscita brusca va ripresa a mano
  (`calliope motore vllm agente riprendi`).
- Il dialogo tra la voce e l'agente passa da tool con errori strutturati ([0018](0018-errori-dei-tool-strutturati.md)).

## Fonti

- [`2026-09-21-orchestrazione-agenti.md`](../ricerche/2026-09-21-orchestrazione-agenti.md) § 1, § 7.1
- [`2026-09-26-tool-e-agenti.md`](../ricerche/2026-09-26-tool-e-agenti.md) § 5.2
- [`2026-10-02-llm-per-spark.md`](../ricerche/2026-10-02-llm-per-spark.md)
- [`2026-10-03-modello-davanti.md`](../ricerche/2026-10-03-modello-davanti.md)
- [`2026-10-05-contesto-agenti.md`](../ricerche/2026-10-05-contesto-agenti.md)
