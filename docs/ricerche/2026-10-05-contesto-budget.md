# La finestra di contesto dal setup: budget e misure (05/10/2026)

*Fase 1 del progetto «Contesto di Calliope» approvato da Dario il 05/10 (scelte A e B
consigliate, ricerca per significato da subito, voce su vLLM da misurare con il motore
configurabile, archivio di 30 giorni, ospiti archiviati solo per chi amministra). Questa fase
**misura e calcola, senza cambiare il comportamento della voce**. Ramo `contesto-1`. Misure sul
portatile (RTX 5070 Laptop, 8 GB, Ollama 0.35.0) e sulla DGX Spark (GB10, 119 GB unificati,
Ollama 0.35.0, vLLM 0.29.0) con `prove/misura_contesto.py`.*

*Legenda: **[M]** misurato qui · **[D]** deduzione.*

## In breve

- **`llm_num_ctx: auto`** è il nuovo predefinito (`calliope/contesto.py`). All'avvio, dopo il
  riscaldamento, Calliope prende il minimo di tre limiti: **il modello** (Ollama `/api/show`,
  vLLM `max_model_len`), **la memoria** (nvidia-smi sul portatile, MemAvailable sulla DGX,
  diviso per il costo di un token della cache calcolato dalla forma del modello; con vLLM i
  token della cache da `/metrics`), **il tempo di rilettura** (prefisso + velocità di lettura
  misurata × `contesto_rilettura_max_s` + la riserva del turno). Multipli di 4096, mai sotto
  8192, mai sopra il massimo. Un numero scritto vince sempre, anche sul profilo (prima un
  profilo **sovrascriveva** il numero di `calliope.locale.yaml`: corretto, i profili non hanno
  più `llm_num_ctx`).
- **Risultato: 16 384 su tutte e due le macchine, limitata dal tempo** [M]. Con 1,5 s di
  rilettura la storia che si rilegge è ~4 000 token sul portatile (2 670 token/s) e ~4 900
  sulla DGX (3 265 token/s, 26B su Ollama): con il prefisso vero (~7 300 token) e la riserva
  fanno **14 278 e 15 176 token**, cioè 12 288 arrotondati. **La finestra di oggi è già al
  limite del tempo.** Per non togliere storia in questa fase, il tempo non scende sotto
  `contesto_ripiego` (16 384) e lo dice; la memoria e il modello sono limiti duri.
- **La memoria non è il problema** [M]: sul portatile la cache costa **17,0 KiB a token**
  (e4b, nvidia-smi da 16k a 128k; la formula dà 16 KiB, ×1,1 nel calcolo) e c'è posto per
  ~100k token (~40k con Whisper caricato); sulla DGX il 26B costa 20 KiB a token e ci starebbero
  oltre 2 milioni di token: il limite è il modello (262 144).
- **Il conteggio vero** arriva a ogni turno dal motore (Ollama `prompt_eval_count` +
  `eval_count`, che contano anche la parte in cache; API OpenAI con
  `stream_options.include_usage`): nel registro dei turni (`contesto`: token, finestra,
  percento), in console (`[CONTESTO] 9.012 token su 16.384 (55 %)`), in `calliope stato` (la
  finestra e perché) e come barra discreta nella testa degli schermi personali di chi parla
  (non sul telefono).
- **vLLM contro Ollama per la voce (26B sulla DGX)** [M]: fino a 32k vLLM risponde un po' prima
  con la storia in cache (0,13 / 0,23 s contro 0,24 / 0,34 s al primo token) e legge alla stessa
  velocità; da 64k in su è peggio in tutto (lettura 1 461 e 778 token/s contro 2 509 e 1 844;
  primo token in cache 0,71 e 2,49 s contro 0,44 e 0,74). **Genera sempre alla metà** (28–33
  token/s contro 38–66) e tiene **~32 GB** prenotati (contro ~15 di Ollama). Per la fase 3
  conviene misurare prima **più posti in Ollama** (vedi sotto).

## 1. Cosa c'è nel codice

| Pezzo | Dove |
|---|---|
| Calcolo, scelta, salvataggio, `finestra(cfg)` per tutti | `calliope/contesto.py` (`prepara`, `calcola`, `scegli`, `kv_ollama`, `token_cache_vllm`, `memoria_libera`, `finestra`, `testo_stato`) |
| Configurazione | `llm_num_ctx: auto`, `contesto_ripiego` (16 384), `contesto_rilettura_max_s` (1,5), `contesto_conversazioni` (1), `contesto_margine_gb` (0,5) in `Config` |
| Prefisso e velocità di lettura | `Brain.warmup` (token del prefisso), `Brain.measure_prefill` (prefisso vero cambiato in testa: niente cache), `OllamaBackend/OpenAIBackend.measure_prefill` |
| Token veri | `("usage", …)` dallo stream dei due backend → `Brain._note_usage` → `Brain.last_context` |
| Registro, console, schermi | `main.py` (dopo la risposta), `Schermi.contesto` / `contesto_per` (evento SSE `contesto`, solo schermi personali, fuori dalla cronologia), barra in `schermo.js` / `index.html` |
| Stato | `calliope stato` legge `contesto.json` (accanto a calliope.yaml): finestra, motivo, i tre limiti |
| Prove | `prove/prova_contesto.py` (a secco, 61 verifiche), `prove/misura_contesto.py` (manuale) |

**Stesso `num_ctx` ovunque.** Con Ollama un `num_ctx` diverso ricarica il modello. Tutti lo
chiedono a `contesto.finestra(cfg)`: la voce, lo scrittore dei documenti (che usa
`OllamaBackend._body`), gli agenti e l'archivio sullo stesso Ollama
(`agenti/impostazioni.opzioni_voce`, `agenti/ciclo._opzioni`) e le prove con Ollama. Gli altri
processi (prove, terminale) leggono la scelta di Calliope da `contesto.json`. Se il calcolo
cambia la finestra rispetto al riscaldamento, Calliope **riscalda di nuovo** prima del saluto
(una ricarica sola all'avvio, mai durante una conversazione).

**Velocità di lettura.** Si misura una volta (prefisso vero con una riga diversa in testa,
così niente è in cache: ~2,7 s sul portatile, ~2,3 s sulla DGX) e si tiene in
`contesto.json` per 7 giorni o finché non cambia il modello; poi il riscaldamento rimette in
cache il prefisso vero. Dai turni normali non si ricava: `prompt_eval_count` conta tutto il
prompt, anche la parte già in cache [M], mentre il tempo è solo quello della parte nuova.

**Memoria con Ollama.** Il costo di un token viene dalla forma del modello in `model_info`:
strati con cache propria (Gemma 4 e4b: gli ultimi 18 dei 42 strati riusano la cache dei
precedenti), teste KV per strato (anche come elenco, 26B), dimensioni di chiavi e valori, e gli
strati «sliding» che tengono solo `sliding_window` token. e4b: 4 strati globali × 2 teste ×
(512 + 512) × 2 byte = **16 KiB**; 26B: 5 × 2 × 1 024 × 2 = **20 KiB** (più ~220 MB fissi
degli strati sliding). Si moltiplica per 1,1 (misurato 17,0 KiB sul portatile). La memoria
per la cache è quella libera adesso meno `contesto_margine_gb`, sopra la finestra con cui il
modello è già caricato (`/api/ps`, `context_length`): così Whisper e il resto, già caricati,
sono contati. Con Ollama su un'altra macchina la memoria di qui non conta: ripiego, detto.

## 2. Le misure

Prefisso vero di Calliope (configurazione della DGX: biblioteca, documenti, casa, schermi,
agenti, archivio; 40 tool; **7 258 token** con gemma4), più una storia finta di turni con la
biblioteca (domanda, chiamata, passaggio, risposta: 359 token l'uno) fino a ~4k dalla fine
della finestra. «A freddo» = tutto da rileggere (una riga diversa in testa: il caso di un
cambio di conversazione o di satellite); «in cache» = un turno normale, due messaggi nuovi
in fondo. Domanda che si risponde dalla storia; 60 token generati.

### Portatile, gemma4 e4b su Ollama (RTX 5070 Laptop, 8 GB)

| Finestra | VRAM in più (nvidia-smi) | Prompt | Lettura | Primo token a freddo | Primo token in cache | Prima frase in cache | Generazione |
|---|---|---|---|---|---|---|---|
| 16 384 | 4 457 MiB | 12 340 | 2 655 t/s | 4,90 s | 0,19 s | 0,47 s | 63,9 t/s |
| 32 768 | 4 729 MiB | 28 765 | 2 297 t/s | 12,89 s | 0,34 s | 0,66 s | 57,3 t/s |
| 65 536 | 5 274 MiB | 62 280 | 1 832 t/s | 34,41 s | 0,51 s | 0,89 s | 46,6 t/s |
| 131 072 | 6 363 MiB | 130 529 | 1 285 t/s | 102,61 s | 0,84 s | 1,33 s | 36,2 t/s |

VRAM di partenza 890 MiB (desktop) senza modello; con Whisper `large-v3-turbo` (~1,2 GiB) la
finestra di 131 072 non ci sta (890 + 6 363 + 1 230 ≈ 8 480 MiB contro 8 151):
**sul portatile il massimo pratico è ~64k** [D], e il calcolo lo trova da sé (memoria libera
dopo Whisper). La memoria cresce di 17,0 KiB a token
(da 16k a 128k: 1 906 MiB per 114 688 token).

### DGX, gemma4 26B-A4B QAT su Ollama (la voce di adesso)

| Finestra | Prompt | Lettura | Primo token a freddo | Primo token in cache | Prima frase in cache | Generazione |
|---|---|---|---|---|---|---|
| 16 384 | 12 344 | 3 230 t/s | 4,34 s | 0,24 s | 0,43 s | 64,3 t/s |
| 32 768 | 28 769 | 3 012 t/s | 10,91 s | 0,34 s | — | 65,6 t/s |
| 65 536 | 62 284 | 2 509 t/s | 26,52 s | 0,44 s | — | 51,6 t/s |
| 131 072 | 130 533 | 1 844 t/s | 73,13 s | 0,74 s | 1,05 s | 38,2 t/s |

(«—»: il 26B ha risposto con una chiamata alla biblioteca, nessuna frase nei 60 token.) La
memoria unificata della DGX non si misura bene da MemAvailable (cache del disco, altri
container: gli scarti tra una ricarica e l'altra erano di gigabyte, anche negativi); vale la
formula, 20 KiB a token: 128k ≈ 2,8 GB di cache [D]. Ricarica del modello a ogni cambio di
finestra: ~10 s. Alla fine rimesso a 16 384 con `keep_alive -1m` (verificato con
`/api/ps`); il servizio `calliope` non è stato toccato.

### DGX, Gemma 4 26B-A4B NVFP4 su vLLM (profilo `gemma4-26b-vllm`)

Container `calliope-vllm-voce` avviato per la misura con `CONTESTO=131072` (MEM 0,24), poi
fermato. All'avvio MemAvailable è sceso da 42,6 a 10,7 GB: **~32 GB prenotati**; cache fp8 di
**684 374 token** (`/metrics`, 5,2 conversazioni da 128k).

| Finestra | Prompt | Lettura | Primo token a freddo | Primo token in cache | Prima frase in cache | Generazione |
|---|---|---|---|---|---|---|
| 16 384 | 11 980 | 2 827 t/s | 4,24 s | 0,13 s | 0,52 s | 28,4 t/s |
| 32 768 | 28 770 | 2 639 t/s | 10,90 s | 0,23 s | — | 30,1 t/s |
| 65 536 | 62 285 | 1 461 t/s | 42,63 s | 0,71 s | — | 32,9 t/s |
| 131 072 | 130 534 | 778 t/s | 167,76 s | 2,49 s | 2,86 s | 28,6 t/s |

### La finestra «auto» che risulta

| | Modello | Memoria | Tempo (1,5 s) | Scelta |
|---|---|---|---|---|
| Portatile, e4b (calcolo vero, senza Whisper) | 131 072 | 106 226 (2,1 GB liberi) | 14 278 (2 670 t/s) | **16 384**, tempo col pavimento |
| DGX, 26B su Ollama (calcolo vero, Ollama vivo) | 262 144 | 2 178 636 (49,2 GB liberi) | 15 176 (3 265 t/s) | **16 384**, tempo col pavimento |
| DGX, 26B su vLLM (dalla tabella) | 131 072 (`--max-model-len`) | 684 374 | ~14 500 (2 830 t/s) | **16 384** |

Sulla DGX oggi `~/calliope/calliope.yaml` ha ancora `llm_num_ctx: 16384` (versione di
prima): dopo `calliope aggiorna` il file si rigenera con «auto». Il risultato è lo stesso.

## 3. Cosa vuol dire per le fasi 2 e 3

**Il tempo, non la memoria, decide la finestra** [D]. A freddo la storia si rilegge a
~2 700–3 200 token/s fino a 32k e sempre più piano dopo (attenzione quadratica): 16k di storia
costano ~5 s, 32k ~11 s, 64k 27–43 s. Tre casi rileggono tutta la storia: il cambio di
conversazione (fase 3, due satelliti su un posto solo), un riavvio di Ollama o un altro
servizio che usa lo stesso Ollama in mezzo (archivio, agenti sullo stesso modello), e oggi il
taglio a blocchi di `_trim_history` (si rilegge da lì in poi). Quindi:

- **Fase 2 (compressione).** Con la compressione la rilettura dopo un taglio è solo
  riassunto + ultimi turni (~800 + 4 × 400 token: < 1 s). Il limite di tempo allora va
  ridefinito come «quanto storia può accumularsi senza che un cambio di conversazione costi
  più di N secondi», e conviene tenerlo basso: **finestra 24–32k sulla DGX, 16–24k sul
  portatile**, con le soglie del progetto (75 % e 90 %) misurate sui token veri che ora
  arrivano a ogni turno. Oltre 32k la generazione rallenta comunque (26B su Ollama: 66 → 52
  token/s a 64k) e il primo token in cache sale (0,34 → 0,44 s). Il pavimento
  `contesto_ripiego` si potrà togliere: sarà la compressione a non perdere storia.
- **Fase 3 (più satelliti).** Tre strade misurabili:
  1. **Più posti in Ollama** (`OLLAMA_NUM_PARALLEL=2–4`): ogni posto è una finestra intera di
     cache, ma per il 26B sono **~0,35 GB a posto a 16k** (20 KiB × 16 384 + ~0,2 GB fissi),
     e ognuno tiene in cache la sua conversazione; generazione a 64 token/s. Costa niente in
     memoria; va cambiata la configurazione del servizio Ollama della DGX (decisione di Dario).
  2. **Voce su vLLM**: la cache condivisa tra le conversazioni (prompt e schemi una volta sola)
     e niente posti fissi; a ≤ 32k il primo token è più svelto, ma genera a 28–33 token/s (la
     metà: una risposta di 3 frasi, ~60 token, dura ~2 s invece di ~1) e prenota ~32 GB. Il
     motore è già configurabile con il profilo (`llm_profilo: gemma4-26b-vllm`).
  3. **Una alla volta** su un posto: ogni cambio di satellite rilegge la storia (a 16k ~5 s):
     va bene solo con un satellite.

  Proposta: per la fase 3 misurare **due satelliti che si alternano** sia con Ollama a 2 posti
  sia con vLLM (con `prove/misura_contesto.py` esteso a due conversazioni), e decidere sui
  numeri. Dai dati di oggi la strada 1 è la più promettente [D].

## 4. Limiti

- La memoria della DGX (MemAvailable) cambia con la cache del disco e con gli altri container
  di casa: il calcolo usa il valore all'avvio, e lì il limite è comunque il modello.
- La cache f16 è un'ipotesi: con `OLLAMA_KV_CACHE_TYPE=q8_0` costerebbe la metà (stima
  prudente). Non si legge da fuori il server.
- La velocità di lettura dipende dalla lunghezza (2 655 t/s a 12k, 1 285 a 130k sul
  portatile): quella misurata al riscaldamento (~7k) è ottimista per finestre grandi; con il
  pavimento di oggi non conta, nella fase 2 conviene una curva (o la misura a 2–3 lunghezze).
- Con l'API compatibile OpenAI su Ollama (`/v1`) il contesto resta 4096 (noto): il conteggio
  dei token lo mostra (2 051 token di prefisso invece di 7 258).
