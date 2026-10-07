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

## Dal testo alla voce: la prima frase a pezzi (07/10)

Il 07/10 mattina sulla DGX (21 risposte, 20 dal satellite «studio», il portatile in Python con
le cuffie Bluetooth in MME): prima frase pronta mediana 1,24 s, **prima voce sentita 2,20 s**.
Dal registro dei turni, `prima_voce_s − prima_frase_s` nei turni senza frase d'attesa:

| | studio 06/10 pomeriggio (41) | studio 07/10 mattina (20) |
|---|---|---|
| distacco mediano | 0,64 s | 0,89 s |
| p90 | 1,07 s | 1,45 s |
| frasi brevi («Non ho lavori in corso.», 23 caratteri) | 0,37–0,44 s | 0,36–0,44 s |

Il distacco cresce con la lunghezza della prima frase (0,4 s con 23 caratteri, 1,3–1,6 s con
200–450 caratteri di risposta): è la **sintesi di Piper della prima frase intera**. Piper (VITS)
non dà campioni prima di aver sintetizzato tutta la frase, e `Speaker._pcm` la manda al
satellite solo dopo. Misure sulla DGX (serena-high, CPU, onnxruntime con le opzioni di Piper):
23 caratteri 0,16 s, 100 → 0,65 s, 151 → 0,91 s (RTF 0,11–0,13, ~6 ms a carattere; aurora-medium
5 volte più veloce: 151 caratteri 0,20 s). Il 07/10 gemma ha dato prime frasi più lunghe del
06/10 (150–250 caratteri, con virgole e due punti): da lì il distacco salito da 0,64 a 0,89 s.
Il resto, ~0,25 s fisso: rete e pezzi (pochi ms in VPN), il buffer di MME del satellite (0,18 s
con `latency="high"`, quella che il satellite dichiara in `uscita_s`) e le cuffie Bluetooth
(non misurabili da qui, non dichiarate). Il **telefono** non mandava `suona`: `prima_voce_s`
mancava in tutti i suoi turni (05–07/10), il confronto con lo studio non si poteva fare.

Correzioni (prova `prova_latenza.prova_voce_a_pezzi`):
- **Prima frase a pezzi** (`tts.primo_pezzo`, `tts_spezza_prima` 60): la prima frase del turno
  più lunga di 60 caratteri si manda a Piper in due pezzi, tagliata dopo una virgola, i due
  punti o il punto e virgola seguiti da uno spazio (mai i decimali, mai a metà senza pausa), con
  il primo pezzo lungo almeno un terzo del resto e 12 caratteri: il suo audio (~55 ms a
  carattere) copre la sintesi del resto. *(Storico: il criterio del terzo è stato sostituito
  il 07/10 pomeriggio dalla velocità misurata, sezione sotto.)* La punteggiatura resta nel primo pezzo: espeak gli dà
  l'intonazione sospesa della virgola. Pausa tra i pezzi sulla DGX 0,23–0,38 s, contro 0,23–0,39
  s delle virgole nella frase intera. Le frasi dopo la prima restano intere (si sintetizzano
  mentre suona quella prima). In `played` e nelle frasi dette dal satellite entrano i due
  pezzi; la storia e il registro (`t.said`) hanno la frase intera. Con `tts_spezza_prima: 0`
  si torna a prima. Non è una regola sul testo (principio 10): non cambia cosa si dice, solo come
  lo si dà a Piper.
- **Thread di Piper** (`tts.carica_voce`, `tts_thread` 8): Piper apre onnxruntime con un thread
  per core; sulla DGX (10 Cortex-X925 + 10 A725) è più lento che con 8. Una frase di 100
  caratteri: 20 thread 0,61 s, 8 → 0,36 s, 10 → 0,35, 12 → 0,69 (mediana di 5); sul portatile
  (24 core, carico di altri agenti) 1,46 → 0,77 s. Se la sessione non si rifà resta quella di
  Piper.
- **Misura**: nel registro `voce_pronta_s` (da `t0`, il primo audio del turno uscito da Piper,
  anche quello della frase d'attesa sintetizzata al momento: `Speaker.voce_pronta`) e
  `sintesi_s` (quanto è costato). `calliope stato --turni` aggiunge la riga «dal testo alla
  voce» con la mediana e il p90 di `prima_voce_s − prima_frase_s` (esclusi i turni con la frase
  d'attesa, dove la voce arriva prima del testo) e la scomposizione in **sintesi** (coda e
  Piper) e **rete e uscita** (rete, buffer e uscita del satellite).
- **Telefono**: `suona` come il satellite (vedi schermi-telefono).

Banco «da `say()` al primo audio mandato al satellite» (le prime frasi vere del 07/10 più una
breve; `Speaker` con un'uscita remota finta), sulla DGX con serena-high:

| | mediana | frase di 143 caratteri |
|---|---|---|
| prima (frase intera, thread di Piper) | 0,66 s | 0,92 s |
| solo 8 thread | 0,39 s | 0,54 s |
| solo pezzi | 0,31 s | 0,39 s |
| pezzi + 8 thread | **0,19 s** | 0,23 s |

Nessun buco tra i pezzi sulla DGX; sul portatile carico, con i thread predefiniti e il primo
pezzo lungo un quarto del resto, un buco di 0,24 s («Ho salvato tutto:»): da lì un terzo. Ci si
aspetta un distacco sullo studio di ~0,45 s invece di 0,89 (resta il buffer di MME e il
Bluetooth): da rimisurare dopo l'aggiornamento con un giorno d'uso (`calliope stato --turni`).
Possibili passi dopo, non fatti: `latency="low"` per l'uscita del satellite (MME 0,09 s invece
di 0,18, rischio di buchi con il keepalive a 20 ms e le cuffie Bluetooth: da provare a orecchio);
una voce medium (5 volte più veloce, ma serena-high è una scelta di qualità); Piper sulla GPU
della DGX (nel venv c'è solo onnxruntime per CPU: ruote CUDA per aarch64 da verificare).

## Il primo pezzo dalla velocità misurata, e la taratura della voce (07/10 pomeriggio)

Misura vera dopo l'aggiornamento (DGX, 07/10 11:25, satellite studio, tre risposte senza tool):
distacco prima frase → voce sentita 0,58 / 0,73 / 0,67 s (la mattina 0,89), ma la sintesi del
primo pezzo era 0,39 / 0,53 / 0,47 s, non i ~0,19 s del banco. La regola «primo pezzo almeno un
terzo del resto» spostava il taglio a una virgola lontana: «Per dormire meglio,» (19 caratteri)
scartato, taglio a 64; «Visto che hai lo smoker,» scartato, taglio a 101; «Un motore elettrico
trasforma … magnetici.» senza virgole, intera (116).

**Criterio nuovo** (`tts.primo_pezzo`): si taglia alla prima virgola, due punti o punto e
virgola dopo cui il primo pezzo ha almeno `tts_primo_pezzo_min` caratteri (15) e due parole, e
la sua voce stimata (caratteri ÷ velocità di parlato) dura almeno 1,5 volte (`PRUDENZA`) la
sintesi stimata del resto (caratteri × costo a carattere). Le frasi senza pause restano intere.
Misure di serena-high sulla DGX (73 frasi e pezzi veri, mediana di 3): sintesi 0,026 s +
3,35 ms a carattere con 8 thread (3,6 ms a carattere sopra i 40 caratteri), voce 0,24 s +
50 ms a carattere (~19 caratteri al secondo; nei pezzi corti di più, per il silenzio che Piper
mette in fondo: la stima è prudente).

**I due numeri non si tarano a mano** (Calliope andrà su macchine che nessuno ha provato):
`calliope/taratura_voce.py`, per voce e numero di thread, in `voce_taratura.json` accanto a
calliope.yaml (atomico, `persistenza.scrivi_json`; senza `config_dir` solo in memoria):

1. **predefiniti prudenti** (15 caratteri al secondo, 10 ms a carattere: una macchina lenta,
   il primo pezzo esce più lungo);
2. **taratura all'avvio** (`Speaker._tara`, in un thread): aspetta che la voce sia libera da 2 s
   (il saluto non rallenta), sintetizza tre volte una frase fissa di 59 caratteri e tiene la più
   veloce. Con `tts_thread: auto` (il nuovo predefinito) e nessuna scelta salvata prova prima 2,
   4, 8 e i core fisici, una sessione di onnxruntime alla volta su una copia della voce, e tiene
   il più veloce (a parità entro il 5 % il numero più basso); un numero scritto in
   `tts_thread` vince. Se intanto parte una sintesi vera la misura si butta. Sulla DGX la prima
   volta 14 s in secondo piano (2 thread 11,7 ms a carattere, 4 → 11,7, 8 → **3,8**, 20 → 5,7:
   scelti 8), poi solo la frase fissa; sul portatile carico 2 → 25, 4 → 19, 8 → **12**, 24 → 51 ms;
3. **l'uso** (`Taratura.osserva`, da `Speaker._synth`): ogni sintesi vera di almeno 20
   caratteri, mediana delle ultime 200, scartati i valori oltre 4 volte (o sotto un quarto) la
   mediana; vale da 30 sintesi. Sulla DGX dopo 112 sintesi: 3,9 ms a carattere, 18,5 caratteri
   al secondo.

La stima si vede in `calliope stato` («Voce it_IT-serena-high: sintesi 3,9 ms a carattere, 18
caratteri al secondo (dall'uso, 112 sintesi); 8 thread, scelti dalla taratura.»), in `--json`
(`voce`) e nella nota della capacità «voce». `tts_taratura: false` (o `CALLIOPE_TTS_TARATURA=0`)
spegne la misura all'avvio, l'uso continua. Il runner delle prove la spegne: con Calliope vera
proverebbe i thread a ogni prova, togliendo CPU alle altre in parallelo (il primo `--completo`
con la taratura accesa ha perso `prova_scritto_calliope`, passata da sola).

Banco sulla DGX (tredici prime frasi vere del 06–07/10, `Speaker` vero con serena-high e 8
thread, un'uscita remota finta; da `say()` al primo audio pronto, mediana di 3; «buco» = il
resto arriva dopo la fine del primo pezzo, il peggiore di 3):

| prima frase (caratteri) | prima: pezzo, primo audio | dopo: pezzo, primo audio |
|---|---|---|
| «Per dormire meglio, …» (145) | 64, 0,26 s | **19, 0,08 s** |
| «Un motore elettrico …» (116, senza virgole) | 116, 0,43 s | 116, 0,42 s |
| «Visto che hai lo smoker, …» (133) | 101, 0,34 s | **24, 0,10 s** |
| altre dieci (136–287) | 38–129, mediana 0,27 s | 38–90, mediana 0,20 s |
| **mediana delle tredici** | **0,27 s** | **0,20 s** |

Nessun buco tra i pezzi, prima e dopo. Dove resta lento è per le pause: «Hai ragione,», «Se
vuoi,», «Allora,» sono sotto i 15 caratteri e si va alla pausa dopo (64–90 caratteri);
«Ho fatto una ricerca,» (21) non copre i 212 del resto con il margine 1,5 per poco. Da
rimisurare con un giorno d'uso (`calliope stato --turni`, riga «dal testo alla voce»).

Prove (`prova_latenza.prova_voce_a_pezzi`): i casi veri (si taglia a «Per dormire meglio,» e «Visto
che hai lo smoker,»; con i numeri del portatile carico lo stesso taglio non basta e si va alla
pausa dopo); i contrari (frase senza virgole, decimali, «Hai ragione,» e «Beh,» sotto il minimo,
resto corto, sintesi lentissima: frase intera); la stima (predefiniti → avvio → uso con 30
sintesi, anomali e frasi corte scartati, separata per voce e per thread, salvata e riletta, file
rovinato), `tts_thread` scritto contro «auto», e uno `Speaker` con un Piper finto lento (1 ms a
carattere, 15 caratteri al secondo) a cui la stima converge.

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
