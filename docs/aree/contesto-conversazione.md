# Contesto e conversazione

*Finestra di contesto, compressione e archivio delle conversazioni, una conversazione per persona (corsie). Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Conversazione per persona, satelliti insieme (dal 06/10) | thread per satellite («corsie»), solo libreria standard | `calliope/corsie.py` → `Corsia`, `RegistroConversazioni` (`scegli`, `occupa`, `doppione`, `pulisci`, `riprendi`), `Varco` (`conversazioni_parallele`), `Smistatore`; il ciclo di ogni corsia `calliope/ciclo.py` → `Ciclo` (dal 06/10, P8), `Servizi`, `Turno`; `main.Corsie` (una corsia per satellite), `main.Avvio`; `ServerSatelliti.insieme`; rapporto [`docs/ricerche/2026-10-06-conversazione-persona.md`](../ricerche/2026-10-06-conversazione-persona.md) |
| Finestra di contesto (dal 05/10) | — (Ollama `/api/show` e `/api/ps`, vLLM `/v1/models` e `/metrics`, nvidia-smi, /proc/meminfo) | `calliope/contesto.py` → `prepara`, `calcola`, `finestra` (il num_ctx di tutti), `testo_stato`; `llm_num_ctx: auto`, scelta in `contesto.json`; token veri in `Brain.last_context`; barra `Schermi.contesto`; misure `prove/misura_contesto.py` |
| Conversazione, compressione e archivio delle conversazioni (dal 05/10) | SQLite in WAL con FTS5 (`conversazioni.db`), vettori da Ollama `/api/embed` sulla CPU (`qwen3-embedding:0.6b`) o `/v1/embeddings`, coseno in numpy, RRF | `calliope/conversazione.py` → `Conversazione` (Brain la espone con `history`, `pending`…, `brain.conv`), `turni`; `calliope/compressione.py` → `Compressore` (soglie 75/90 %, `avvia`, `comprimi_ora`, `applica`, `chiudi`), `RiassuntoreLLM` (agente o voce), `RiassuntoreTagli`, `crea_riassuntori`; `calliope/conversazioni.py` → `ArchivioConversazioni` (`archivia`, `cerca`, `ultima`, `dimentica`, conversazione corrente), `Embedder`, `load_conversazioni`; tool `conversazione_cerca`, `conversazioni_dimentica` in `calliope/tools/conversazioni.py`; «ricominciamo» `wakeword.nuova_conversazione`; terminale `python -m calliope.conversazioni`; misure `prove/misura_conversazioni.py` |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Una conversazione per persona, satelliti insieme** (06/10, `calliope/corsie.py`, rapporto
  [`docs/ricerche/2026-10-06-conversazione-persona.md`](../ricerche/2026-10-06-conversazione-persona.md),
  prove `prova_corsie.py`, `prova_corsie_satelliti.py`): ogni satellite ascolta e parla per
  conto suo (una corsia, cioè un suo `Ciclo` con i suoi oggetti, in un thread;
  `satelliti_insieme`), e ogni persona riconosciuta dalla voce sopra la soglia ha la
  sua conversazione da qualunque satellite (storia, azione in sospeso, riferimenti, foto,
  allegati, turni). Frase breve e zona grigia continuano solo quella di chi ha parlato su
  quel satellite; un «sì» breve altrove non raccoglie la proposta (`sospeso_altro_satellite`);
  ospiti e voci incerte una conversazione anonima per satellite. Anche in locale: chi torna
  dopo un'altra persona ritrova la sua (si chiude con «esci» o dopo `storia_inattiva_s`).
  Risposte del modello insieme fino a `conversazioni_parallele` (1: sulla DGX Ollama 0.35 ne fa
  comunque una alla volta, misurato con 1/2/3 persone), oltre «Sto rispondendo anche a
  un'altra persona: dammi un attimo.» (0,5–1,1 s) e la coda; la stessa frase da due satelliti
  della stessa stanza ha una risposta sola (`doppione_altro_satellite`); annunci e frasi
  scritte alla corsia del satellite giusto. Registro dei turni con `satellite` e
  `conversazione`. Dal 06/10 anche lo stato della voce sugli schermi è per corsia (P9, sotto).

- **Il ciclo della voce come classe** (06/10, P8 dell'[analisi complessiva](../ricerche/2026-10-06-analisi-complessiva.md),
  ramo `ciclo-classe`, prove `prova_ciclo.py`, `prova_corsie.py`): `main.giro`, una chiusura di
  ~1 130 righe dentro `main()`, e `corsie.clona`, che la ricopiava per ogni satellite rifacendo
  le celle delle variabili libere (`types.FunctionType`/`CellType`: una variabile dimenticata
  restava condivisa senza errori, il difetto P9), non ci sono più. `calliope/ciclo.py`:
  - `Servizi` (dataclass): ciò che le corsie condividono (configurazione, registro delle voci,
    Whisper, agenda, schermi, instradamento, agenti, compressione, guardiano, registro dei
    turni…), con i valori che cambiano a voce letti da lì (`wake`, `suoni`, `barge_in`,
    `barge_voice`, `biblioteca`, `enroll_pending`);
  - `Ciclo`: una corsia con i suoi oggetti come attributi (`listener`, `speaker`,
    `speaker_ctx`, `brain`, `tool_ctx`, `annunci`, `ingresso`, `sveglia`) e il suo stato
    (`rec`, `awake_until`, `barge_seed`, `last_question`, `pending_real_name`,
    `annunci_rinviati`, `errori_ciclo`, `attesa_voce`); `esegui` (il ciclo protetto da
    `errore_nel_giro`), `giro` che chiama le fasi: `_inizio_giro`, annunci (`_annuncia_*`),
    `_prendi_scritto` e `_scritto_senza_domanda` (file, foto, moduli), `_ascolta`,
    `_trascrivi`, `_chi_parla` (`_confronta_voce`, `_riconosci_voce`),
    `_conversazione_del_turno`, `_arruolamento`, `_nome_reale`, `_richiamo` (wake word),
    `_primo_avvio`, `_mostra_richiesta`, `_uscite`, `_chiusure`, `_fuori_orario`,
    `_contesto_e_allegati`, `_rispondi` (`_prepara_risposta`, `_ascolta_il_nome`,
    `_frase_da_dire`), `_registra_risposta`, `_dopo_la_risposta`. Ogni fase restituisce None
    (avanti), `_FINE` (il vecchio «return») o "esci"; le variabili del giro stanno in `Turno`
    (slots: un nome sbagliato è un errore). Il metodo più lungo è di 50 righe.
  - `main.py`: `Avvio` (il corpo di `main()` diviso in passi: chi parla, audio, voce, servizi,
    schermi, agenti, tool, minori, estensioni, Brain e compressione, corsia locale, modello e
    saluto, barge-in, `applica_modalita`, `activate_library`) e `Corsie` (smistatore, ponte
    delle sveglie, `crea` di un `Ciclo` per satellite). La funzione più lunga è di 53 righe.
  - Accoppiamento: il ciclo usa di Brain solo metodi e attributi pubblici
    (`Brain.rileggi_tool` e `Brain.manda_schede` al posto di `_tool_re` e `_send_cards`);
    restano quattro accessi privati ad altri oggetti, scritti da sempre così (conto della
    seconda analisi del 06/10, § 3.5): `registry._da_salvare` (media del riconoscimento dei
    minori), `speaker._current_voice_path` (voce preferita) e `minori._per_id` in `ciclo.py`;
    `satelliti._cond` in `main.py` (classe `Corsie`).
  - Le prove che leggevano `main.py` (sicurezza, politica, immagini, config) leggono
    `ciclo.py`; quella del ramo «chi parla» chiama `Ciclo._confronta_voce`.
  - `Ciclo.esegui` (06/10, Q10 della seconda analisi): in una corsia di satellite «esci» da
    un giro addormenta e il ciclo continua (`_dormi_invece_di_uscire`), come prima di P8;
    solo la corsia locale esce. Caso in `prova_ciclo`.

- **Finestra di contesto dal setup** (05/10, fase 1 del progetto «Contesto di Calliope»,
  [`docs/ricerche/2026-10-05-contesto-budget.md`](../ricerche/2026-10-05-contesto-budget.md),
  prova `prova_contesto.py`): `llm_num_ctx: auto` (predefinito; un numero vince, anche sul
  profilo, che non ha più `llm_num_ctx`) = minimo di modello, memoria (forma della cache da
  `/api/show`, nvidia-smi o MemAvailable; vLLM `/metrics`) e tempo di rilettura
  (`contesto_rilettura_max_s` 1,5 s × lettura misurata una volta, + prefisso e riserva); a
  multipli di 4096, ricarica prima del saluto se cambia. Token veri a ogni turno (Ollama
  `prompt_eval_count` + `eval_count`, OpenAI `include_usage`) nel registro (`contesto`), in
  console, in `calliope stato` e come barra sugli schermi personali (non sul telefono).
  Risultato: **16 384 su portatile e DGX**, limitata dal tempo (14,3k e 15,2k, tenuta a
  `contesto_ripiego` per non cambiare la voce: la finestra di oggi è già al limite). vLLM voce
  contro Ollama (26B): ≤ 32k primo token in cache 0,13–0,23 contro 0,24–0,34 s, ma genera a
  28–33 token/s contro 38–66, legge peggio da 64k e prenota ~32 GB.

- **Compressione e archivio delle conversazioni** (05/10, fase 2 del contesto,
  [`docs/ricerche/2026-10-05-contesto-compressione.md`](../ricerche/2026-10-05-contesto-compressione.md),
  prova `prova_conversazioni.py`): la conversazione è un oggetto (`Conversazione`, una per
  satellite nella fase 3). Ogni turno finito va in `conversazioni.db` (30 giorni, regole di
  sempre su riservati e personali, mai gli argomenti dei tool), così ogni taglio della storia
  toglie solo turni archiviati. Oltre il 75 % della finestra (token veri) la compressione parte
  a risposta finita e cede alla voce; oltre il 90 % prima di rispondere («Un attimo, riordino
  le idee.», tagli se il riassunto tarda 8 s). Restano gli ultimi 4 turni e l'azione in
  sospeso; il riassunto strutturato sta dopo il prompt, fermo fino alla compressione dopo.
  Riassume l'agente (qwen3.6 su vLLM: 4–5 s, 12/12 fatti), altrimenti la voce con **la sua
  stessa conversazione** (cache: la domanda dopo rilegge 0,16 s), altrimenti i tagli.
  `conversazione_cerca` (FTS5 + `qwen3-embedding:0.6b` sulla CPU, RRF: 17/18 contro 15/18 delle
  sole parole; ognuno le sue, gli ospiti mai, `ospiti=true` solo a chi amministra dalla voce),
  `conversazioni_dimentica`, «ricominciamo» (regola `nuova_conversazione`), fine con il
  riassunto in secondo piano e la riga «l'ultima volta…» entro 4 ore, conversazione salvata a
  ogni turno (un riavvio non la perde). Banco con gemma4 e4b: domande sul passato 30/34 senza
  compressione, 24/34 con la compressione (il 4B non cercava mai), **46/51** (3 giri) con la
  ricerca fatta da Brain quando dice «non lo so» dopo una compressione (`spinta_archivio`) e i
  risultati senza domande rimaste senza risposta; ospite e istruzione archiviata a posto in
  tutti i giri. Finestra: con la compressione il tempo è la
  rilettura della storia alla soglia morbida (`contesto_rilettura_max_s` 4 s): **20 480 sul
  portatile, 24 576 sulla DGX**, prima frase in cache invariata (0,51 / 0,49 / 0,52 s a 16k /
  20k / 24k). `max_history_turns` 40 (limite di sicurezza).

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Contesto di Ollama**: l'endpoint `/v1` ignora `num_ctx` e usa 4096 token; per questo
  il backend predefinito è quello nativo. `ollama ps` **sottostima la VRAM**: va misurata
  con `nvidia-smi`. Con gemma4:e4b-it-qat: 4096 → ~4,2 GiB, 16384 → ~4,6 (predefinito *[storico: dal 05/10 `llm_num_ctx: auto`]*),
  131072 → ~6,4 (con Whisper supera gli 8 GB); il 05/10 17,0 KiB a token (dal 05/10 la
  finestra la sceglie `calliope/contesto.py`, e ogni richiesta allo stesso Ollama la prende
  da `contesto.finestra`). Se `num_ctx` cambia tra una richiesta e
  l'altra, Ollama ricarica il modello: il warmup usa lo stesso valore. Dal 02/10 il warmup manda anche il
  prefisso vero (prompt di sistema e tool del livello «amministra», ~4 600 token): con un
  «ciao» nudo la prima domanda li elaborava da capo (DGX: prima frase di «che ore sono?»
  1,89 s, poi 0,81 e 0,39; sul portatile 2,35 s contro 0,49 s, avvio +1,5 s).

## Latenza vera come metrica (06/10)

Dal rapporto [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)
(P1–P4, P11): la prima frase nei turni veri era 2,05 s di mediana il 05/10 (0,78 s il 02/10).
- `calliope/latenza.py` (`per_giorno`, `testo`, `avviso`, `avviso_recente`, `scalda_ripresa`):
  `calliope stato --turni [--giorni N] [--json]` dà per giorno la prima frase (mediana, p75,
  p90), il tempo dalla fine del parlato, lo STT e le cause (correzione e scadute, guardiano,
  tool, riletture oltre 1 s, contesto, coda) con la base senza tool, guardiano né correzione.
  Con la mediana di oggi o di ieri oltre `latenza_avviso_s` (1,2 s, almeno 10 risposte) la
  riga `[LATENZA]` all'avvio e in `calliope stato`. Nel registro dei turni `fine_parlato_s`
  (da `Listener.ended_at`; sul satellite una stima) e `lettura_s` (rilettura del prompt nella
  prima passata su Ollama: oltre ~1 s la cache non è servita).
- **Correzione della trascrizione**: `stt_correzione_timeout_s` 0,4 s, tempo massimo vero
  (oltre vale Whisper, regola `stt_correzione_scaduta`). Il 05/10 sulla DGX: 44 frasi su 112,
  1,00 s di mediana, 10 cambiate; prima frase 2,73 s con la correzione contro 1,35 s senza.
  Col 26B a 0,4 s non arriva quasi mai: proposta di spegnerla sulla DGX.
- **Guardiano**: i ~3 s dei minori venivano dal rilevatore di pericolo (`gemma4:e4b-it-qat`)
  mai caricato sulla DGX: ogni richiesta chiusa a 3 s (499 nel log di Ollama) faceva
  ripartire il caricamento. Ora `prepara` carica guardiano e rilevatore all'avvio
  (`AVVIO_S` 120 s), un giudizio scaduto ricarica quel modello in secondo piano (`_riscalda`,
  uno alla volta, mai quello della voce), la domanda si giudica con `Guardiano.in_parallelo`
  mentre il modello risponde e nessuna frase va alla voce prima del giudizio. In locale
  (e4b + llama-guard3:1b da freddi): 3,1 · 3,0 · 0,33 · 0,34 s. Sul portatile da 8 GB i due
  modelli non stanno insieme in memoria.
- **Cache dopo un riavvio**: `Brain.scalda_conversazione` legge in anticipo la conversazione
  ripresa (stesso prefisso del primo turno), lanciata da `latenza.scalda_ripresa` all'avvio:
  11 000 token riletti in 2,85 s senza, 0,07 s con. Resta freddo il cambio di persona:
  proposti `OLLAMA_NUM_PARALLEL=2` sulla DGX (~0,65 GB per slot a 28 672) oppure
  `contesto_rilettura_max_s: 3` (finestra 24 576, rilettura a freddo ~2,1 s invece di ~3,1).
  Dal 06/10 (Q5 della seconda analisi) si scalda la storia **già compattata** come la vedrà il
  primo turno (`brain._compatta_storia`, la stessa di `_compact_old_results`, su copie): con un
  tool nella storia il prefisso scaldato coincideva per 3 messaggi su 9–11, ora per tutti (prova
  `prova_ripresa_con_tool`, un Ollama finto che registra i messaggi come `OllamaBackend._native`).
  `contesto_rilettura_max_s: 3` è nell'esempio della DGX (`setup/linux/calliope.locale.esempio.yaml`).
- **Riassunti**: `contesto_riassunto_attesa_s` (10 s): se il riassunto dell'agente non
  comincia, lo scrive la voce o si comprime con i tagli (prima fino a 560 s in coda). Dal 06/10
  (Q11 della seconda analisi) anche un tetto in tutto, `contesto_riassunto_max_s` (60 s, dal
  primo tentativo anche se cede alla voce e riparte): oltre, `TroppoLungo` e la voce o i tagli
  (riassunto più corto, mai la storia piena per minuti).
- Prova `prova_latenza.py`.

## Ollama pieno: embedding solo a Calliope inattiva (06/10, prova e2e sulla DGX)

Nella prova end-to-end sulla DGX voce (26B), guardiano (llama-guard3), rilevatore di pericolo
(e4b) ed embedding delle conversazioni (qwen3-embedding) stavano su un Ollama che ne tiene 3:
il primo embedding dell'archivio scacciava il guardiano o la voce (turni di minori e ospiti
10–17 s, «guardiano guasto»). Ora:

- `calliope/ollama_carico.py` → `residenti` (`/api/ps`, cache 3 s), `limite` (`ollama_max_modelli`,
  poi `OLLAMA_MAX_LOADED_MODELS` dell'ambiente o del servizio systemd di Ollama, in sola
  lettura; altrimenti 3 «assunto»), `usati` (voce, guardiano, rilevatore, embedding per Ollama),
  `avviso`, `puo_caricare`;
- la capacità «llm» lo dice all'avvio e in `calliope stato` quando Calliope usa più modelli del
  limite, con il passo (`OLLAMA_MAX_LOADED_MODELS` nel servizio di Ollama, `sudo systemctl edit
  ollama`);
- `ArchivioConversazioni._vettori_mancanti`: su Ollama solo con Calliope inattiva da
  `conversazioni_vettori_inattivita_s` (600 s; attività = turno archiviato o ricerca), a lotti da
  64 con `keep_alive: 0`, oppure subito se il modello è già caricato (sempre `keep_alive: 0`);
- `cerca`: la domanda diventa un vettore solo con il modello caricato o un posto libero
  (`keep_alive` 2m), altrimenti per parole (FTS5; `ricerche_per_parole`).

Embedding fuori da Ollama: non fatto (servirebbe un runtime nuovo; onnxruntime c'è già, ma il
modello ONNX di qwen3-embedding e il suo tokenizer sono da verificare su ARM). Prova
`prova_ollama_carico.py`.
