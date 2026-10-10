# 0002. LLM dietro un'API standard e intercambiabile

- **Stato**: accettata (21/09/2026); backend predefinito Ollama nativo dal 24/09; `llm_profilo`
  dal 03/10
- **Principi**: 1 di [`CLAUDE.md`](../../CLAUDE.md)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md)

## Contesto

Il progetto è nato su un portatile con 8 GB di VRAM e punta a una macchina con molta memoria
unificata (DGX Spark oggi, RTX Spark domani). I modelli locali cambiano ogni poche settimane.
Passare da una macchina all'altra, o da un modello all'altro, non deve voler dire riscrivere il
codice: deve bastare cambiare il nome del modello o l'indirizzo del server.

## Decisione

- Brain parla con il modello attraverso due backend: `OllamaBackend` (API nativa `/api/chat`) e
  `OpenAIBackend` (API compatibile OpenAI `/v1`, usata anche per vLLM).
- **Dal 24/09 il predefinito è l'API nativa di Ollama**: è l'unica che rispetta `num_ctx` (l'endpoint
  `/v1` lo ignora e usa 4096 token); con la nativa anche `think` e `keep_alive` si impostano a ogni
  richiesta e i `tool_calls` arrivano interi. Il backend OpenAI resta come ripiego e va tenuto
  funzionante.
- **Dal 03/10 il modello della voce si sceglie con una riga**, `llm_profilo`: backend, indirizzo,
  modello, thinking e reti di Brain adatte a quel modello insieme (`PROFILI_LLM` in
  `calliope/config.py`). Si torna indietro cambiando la stessa riga. Profili di oggi:
  `gemma4-e4b-ollama`, `gemma4-26b-ollama` (in uso sulla DGX), `gemma4-26b-vllm`,
  `qwen3.6-35b-vllm` (solo per misure).

## Alternative considerate

- **Solo API OpenAI**: più portabile, ma su Ollama perde il controllo della finestra di contesto.
  Tenuta come ripiego, non come predefinita.
- **Modelli scartati nel confronto del 21/09** (RTX 5070 8 GB): `gemma3:4b` (in Ollama non supporta
  i tool), `qwen3.5:4b` (fatti inventati, tool 3/4), `qwen3:8b` (non migliore, più lento, riempie la
  VRAM), `llama3.1:8b` (debole in italiano). Scelto `gemma4:e4b-it-qat`: tool 4/4, prima frase 0,46 s.
- **Modelli densi grandi sulla DGX** (`gemma4:31b`, 11 token/s): esclusi per la voce. Sullo Spark la
  generazione dipende dalla banda di memoria (273–300 GB/s), quindi davanti vanno modelli **MoE**
  con 3–5 miliardi di parametri attivi (50–80 token/s).
- **Voce su vLLM** (`gemma4-26b-vllm`, 03/10): banco 112/116, ma prima frase 0,90 s di mediana e
  ~1,9 s al p90; scelta Ollama (0,68 / 1,18 s, 143/144).
- **vLLM, SGLang, TensorRT-LLM su Windows**: non esistono in versione nativa (solo WSL2): su
  Windows ARM restano Ollama e llama-server.

## Conseguenze

- Il passaggio dal portatile alla DGX (02/10) e dal 4B al 26B (06/10) è stato un cambio di
  configurazione.
- Le «reti» di Brain (controlli che correggono la forma delle risposte di un modello, per esempio
  una chiamata di tool scritta come testo) dipendono dal modello: il profilo dice quali spegnere
  (`llm_reti_spente`).
- Ogni funzione nuova di Brain va provata su entrambi i backend.

## Fonti

- [`2026-09-21-confronto-llm.md`](../ricerche/2026-09-21-confronto-llm.md)
- [`2026-10-02-llm-per-spark.md`](../ricerche/2026-10-02-llm-per-spark.md)
- [`2026-10-03-modello-davanti.md`](../ricerche/2026-10-03-modello-davanti.md)
- [contesto-conversazione](../aree/contesto-conversazione.md) (finestra di contesto e `num_ctx`)
