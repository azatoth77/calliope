# Il modello davanti: meno reti, un modello più forte? (03/10/2026)

*Lavoro della notte tra il 2 e il 3 ottobre 2026. Decisione dell'utente del 02/10: Calliope
regge su `gemma4:e4b-it-qat` (4B) circondato da reti e spinte (TextCallGuard, spinte sulle
azioni promesse e dichiarate, azione in sospeso, riferimento della casa…); va corretto il
difetto architetturale. Domande: quali reti servono davvero; se un modello davanti più forte
sulla DGX è chiaramente migliore senza rovinare la prima frase; se conviene vincolare le
chiamate ai tool. Misure sulla DGX Spark (GB10, vLLM 0.29.0, Ollama 0.35.0) con il codice del
ramo `modello-davanti`; script di misura temporanei fuori dal repository, numeri qui.*

*Legenda: **[M]** misurato qui · **[D]** deduzione.*

## In breve

- **Il cambio si fa con una riga** (fatto): `llm_profilo` in `calliope.locale.yaml`
  sceglie backend, indirizzo, modello, thinking **e le reti adatte a quel modello**
  (`config.PROFILI_LLM`). Profili: `gemma4-e4b-ollama` (il 4B, tutte le reti accese) e
  `gemma4-26b-vllm` (Gemma 4 26B-A4B NVFP4 su vLLM, porta 8001). Le reti si spengono una per
  una con `llm_reti_spente` (predefinito: tutte accese, così il portatile non cambia).
  Provato sulla DGX con la configurazione vera, avanti e indietro (§6).
- **Gemma 4 26B-A4B è chiaramente più bravo** [M]: sul banco di regressione nuovo
  (`prove/prova_regressione.py`, 58 frasi vere × 2 giri) **112/116 contro 98–100/116** del
  4B, **zero chiamate scritte come testo** (il 4B 23–30 su 116 turni, tutte salvate da
  TextCallGuard), e risolve quasi tutti gli errori della sera del 02/10 (l'ora vecchia presa
  dalla storia, «chi sono?», «che giorno è domani?», «mostramela sullo schermo»).
- **Ma è troppo lento per la voce, così com'è servito** [M]: prima frase **0,90 s di mediana,
  1,84–1,90 s al p90** (obiettivo 0,7 e 1,5); con un tool 0,99 / 1,9–2,2 s. Il 4B: 0,48 /
  1,33 s. La causa è la generazione: **29 token/s** per il checkpoint NVIDIA NVFP4 su vLLM
  (solo gli esperti sono in FP4, attenzione e parti dense restano in BF16; MoE marlin o
  CUTLASS danno lo stesso), contro 60–71 del 4B su Ollama e 76 di Qwen3.6-35B-A3B NVFP4 sullo
  stesso vLLM.
- **Decisione: la voce della DGX resta sul 4B** (`gemma4-e4b-ollama`). Il 26B non passa il
  criterio della prima frase. Il profilo `gemma4-26b-vllm` e lo script del server sono
  pronti; il container è spento (`calliope motore vllm voce avvia` lo riaccende).
- **Le reti servono al 4B e solo a lui** [M]: senza reti il 4B scende da 98–100 a **67/116**
  (le chiamate scritte come testo finiscono nel nulla); il 26B fa 112/116 con e senza
  spinte, e le spinte gli costano ~0,04 s di mediana (0,94 contro 0,90). Nel profilo del 26B
  restano accesi solo i contesti (`riferimento_casa`: senza, «Scendila» non va più,
  `azione_in_sospeso`) e la conferma al posto del vuoto.
- **Vincolare le chiamate non serve** [M]: con il parser `gemma4` di vLLM il 26B fa 40/40
  tool giusti e 40/40 argomenti validi sia con `tool_choice: auto` sia con `required`
  (decodifica vincolata), negli stessi tempi (0,77 contro 0,76 s). `required` non si può
  usare per la voce (obbliga a un tool anche per «ciao»); Ollama non vincola i tool.
- **Trovato e corretto un difetto del modello di chat di Gemma 4** [M]: con il thinking
  spento il canale di pensiero vuoto si mette solo all'inizio del turno; dopo il risultato di
  un tool il 26B a volte apre lui il canale e ragiona in inglese, in silenzio, per 10–18 s
  (una volta fino al limite del contesto: 971 s). `setup/linux/motore/gemma4_template.py`
  corregge il modello e `vllm.sh` lo passa con `--chat-template`: 16 seconde passate su 16
  pulite (prima 2 su 8 andavano in ragionamento).
- **Prompt**: «per l'ora chiama ora_attuale e per la data data_oggi ogni volta che servono,
  anche se le hai già dette (quelle nella conversazione sono vecchie)». Il 26B passa da 0/2 a
  2/2 su «No, intendevo che ore sono»; il 4B no (resta una debolezza nota).
- **Aggiornamento, stessa notte: `gemma4:26b-a4b-it-qat` su Ollama** (§9) [M]. Q4 su tutti i
  pesi, 15 GB, genera a **74–79 token/s** (più del 4B). Banco: **109–110/116** (4B 101),
  zero chiamate come testo; prima frase **0,72–0,73 s di mediana**, p90 1,8–2,1 s, ma il p90
  viene quasi tutto dai cambi di livello del banco (ospite, familiare, amministra hanno tool
  diversi, quindi prefisso nuovo da rileggere: ~2 s); a livello costante **0,70 s di mediana e
  1,05–1,19 s al p90** (4B: 0,45 / 0,87). Le prove di sempre: 29/29, 17/17, 18/19, 20/20,
  21/21, 31/31, 17/17. Un difetto nuovo: «scrivimi uno script Python…» lo scrive a voce
  (10 s) invece di delegarlo. Profilo `gemma4-26b-ollama` pronto, **non attivato**: la
  qualità migliora nettamente, la latenza no (è più lento del 4B). Decide l'utente.
- **Aggiornamento del pomeriggio** (§11): corretti l'eco del contesto («Chi ti parla è
  Dario.» detto in testa alle risposte del 4B), le offerte di cercare invece di cercare e il
  codice scritto a voce dal 26B (10/10 delegati); `llm_keep_alive` validato. Sulla DGX: 26B
  **143/144**, prima frase 0,68 / 1,18 s; 4B 139/144, 0,47 / 0,88 s. **Raccomandazione:
  passare la DGX al 26B** (decide l'utente).

## 1. Che cosa dice il registro dei turni

Fonti: il registro del portatile (`registro/`, 24/09–01/10: 226 turni, 162 risposte, 80
chiamate di tool) e quello della DGX (`~/calliope/registro/`, sera del 02/10: 83 turni, 65
risposte, 27 chiamate). Il campo `regole` c'è solo dal 01/10. Letti sul posto, nessun dato
personale copiato nel repository.

| Regola | Portatile (01/10) | DGX (02/10) | Esito |
|---|---|---|---|
| `textcallguard` (chiamata scritta come testo, eseguita) | 4; in tutto 16 chiamate su 80 «da testo» dal 24/09 (20 %) | 5 su 27 chiamate (19 %) | tutte giuste: senza la guardia il TTS avrebbe letto «ora_attuale()» |
| `riferimento_casa` (contesto «l'ultimo dispositivo») | — | 11 | è un contesto: una volta decisivo, nelle altre inerte |
| `spinta_promessa` | — | 2 | «Vado a controllare la temperatura…» → `casa_stato`: giuste, ma la frase d'annuncio era già detta |
| `spinta_dichiarata` + `dichiarata_taciuta` | — | 1 | «Anzi, annulla» (trascritto «Anzi, no a nulla») → «Non ci sono riuscita»: evitato un «fatto» falso, ma il promemoria non è stato annullato |
| `spinta_richiesta` | 1 | — | «apri il PDF della spesa»: giusta |
| `azione_in_sospeso` | 2 | — | «Sì.» dopo «Lo apro?»: giuste |
| `stop`, `stop_interruzione`, `uscita_*`, `nome_tool_taciuto`, `schermo_personale` | 4 | 8 | audio, permessi, forma: non dipendono dal modello, restano |

**Gli errori veri della sera del 02/10 non li ha presi nessuna rete:**
- «Ciao, dimmi, ma che ore sono?» → «Sono le 15:33.» alle 23:28, **senza tool** (ora
  inventata), e poi ancora «Sono le 15:34»;
- «No, intendevo che ore sono.» → «Sono le 21:50.»: l'ora di due minuti prima, dalla storia;
- «Calliope di Michisono» («dimmi chi sono») → «Ti chiamo Michisono.» senza tool;
  «Calliope e chiamo risonò» → `chi_parla` e poi «Ti chiamo Risonò»; «Intendevo chi sono
  io» → «Non ho accesso a informazioni personali»;
- «Sono le 23:29.» → «Ho registrato che per te sono le 23:29.» (falso; «registrato» non è
  nell'elenco della rete);
- «Riesci a mostrarmi il documento sul video?» → «Non ho la possibilità di mostrare
  contenuti su un video»; «Non puoi dedurla [la data di domani]?» → «non ho accesso al
  calendario».

Le reti correggono la *forma* delle chiamate del 4B; gli errori che contano sono di
*giudizio* (quando chiamare un tool, che cosa vuol dire la frase), e lì una regola sul testo
non arriva (principio 10).

## 2. Il banco di regressione

`prove/prova_regressione.py` (registrato tra le prove con il modello). 58 frasi in sessioni,
dalle frasi vere riscritte senza dati personali, con le storpiature di Whisper com'erano:
l'ora (anche con una storia che contiene un'ora vecchia o inventata), «chi sono?» (vietato
rinominare), timer e promemoria con l'annullo, date, casa con l'HA finto (pronomi con il
riferimento seminato come dopo un comando vero), schermi, documenti, biblioteca, conti,
liste, memoria, voci, delega, e i casi contrari (racconto, «grazie, va bene così» che non deve
diventare un racconto, «ciao», spiegazioni brevi da non delegare, internet e meteo che non ci
sono, l'ospite). Un'azione dichiarata («ho acceso», «ho registrato»…) senza un tool riuscito
è sempre un errore. Configurazione come sulla DGX (biblioteca, documenti, casa, schermi,
agenti; niente PC). La prima frase è quella di `main.py`: la prima frase intera che va al TTS
(`split_sentences`), non il primo pezzo di testo.

Ogni misura qui sotto è partita con la GPU ferma da 20 s (gli altri lavori della notte usano
la stessa DGX: con l'agente qwen3.6 che genera, il 26B scende a 14 token/s e la mediana
raddoppia, §5).

### 2.1 Risultati (2 giri, 116 turni)

| Modello e reti | Riuscite | Prima frase mediana | p90 | senza tool (med/p90) | con tool (med/p90) | Chiamate scritte come testo |
|---|---|---|---|---|---|---|
| 4B Ollama, reti accese (profilo `gemma4-e4b-ollama`) | **98–100** | **0,48 s** | **1,33 s** | 0,34–0,37 / 0,52–0,56 | 0,69–0,72 / 1,41–1,43 | 23–30 (salvate) |
| 4B Ollama, reti spente | 67 | 0,43 | 1,33 | 0,38 / 0,83 | 0,49 / 1,40 | 0 (non intercettate: niente tool) |
| 26B vLLM, reti accese | 112 | 0,94 | 1,89 | 0,62 / 1,23 | 1,00 / 1,95 | 0 |
| 26B vLLM, profilo (spinte e guardia spente) | **112** (3 volte) | **0,90** | **1,84–1,90** | 0,59 / 1,23–1,26 | 0,99 / 1,87–2,17 | 0 |
| Qwen3.6-35B vLLM (porta 8000, reti spente) | 94 (10 errori 400) | 0,55* | 0,95* | — | — | 0 |

\* Qwen misurato con la metrica vecchia (primo pezzo di testo) e prima della correzione del
modello di chat di Gemma: solo indicativo.

Errori del **26B**: «Che ore sono?» con nella storia «Sono le 15:33» detto senza tool (copia
l'ora inventata, 2/2) e «Calliope di Michisono» (cerca «Michisono» nella biblioteca dopo
`chi_parla`). Errori del **4B** con le reti: l'ora vecchia o inventata (4 sessioni), «chi
sono io?» senza tool, «che giorno è domani / era ieri?» («devo prima sapere che giorno è
oggi»), «Che ore sono?» dopo un racconto interrotto («Ora sono 15:42», una volta «Ora sono
ora_attuale»), «mostrami il documento sullo schermo», e una volta «grazie, va bene così» che
diventa un racconto.

Con la metrica vecchia (primo pezzo di testo, prima della correzione del modello di chat) e 3
giri sul 26B: reti accese 168/174, tutte spente 165/174 (perde «Scendila»: serve il
riferimento della casa), solo spinte e guardia spente 168/174. Da qui il profilo.

### 2.2 Le prove di sempre con il 26B (1 giro)

`prova_casa_ha_ollama` 28/29 («Quanti gradi ci sono fuori?» → «non ho accesso al meteo»),
`prova_stato_ollama` 17/17, `prova_schermi_ollama` 18/19 («Mettimi sullo schermo i miei
appuntamenti» → `appuntamenti_elenca` + `schermo_mostra(risposta)` prima di avere la
risposta), `prova_agenti_ollama` 20/20, `prova_casa` 21/21, `prova_pc_ollama` 31/31,
`prova_documenti_ollama` 17/17. Accettano il profilo con `CALLIOPE_LLM_PROFILO` (vale per
`Config()`); `prova_documenti_ollama` riscaldava lo scrittore solo con Ollama: corretta. I
tempi di questi giri non valgono (GPU condivisa con altri lavori). Le lettere del 26B si
generano in ~10 s contro 3–4 del 4B: stessa causa, la velocità di generazione.

## 3. Perché il 26B è lento qui

| Modello | Motore | Token/s (GPU ferma) | Note |
|---|---|---|---|
| gemma4:e4b-it-qat | Ollama | 60–71 | il 4B di oggi |
| nvidia/Gemma-4-26B-A4B-NVFP4 | vLLM, MoE marlin | 25–30 | `nvfp4_experts_only`: attenzione e parti dense in BF16 |
| idem | vLLM, MoE CUTLASS | 29 | nessun guadagno |
| idem + decodifica speculativa n-gram | vLLM | peggio (misura disturbata da altri carichi) | scartata |
| nvidia/Qwen3.6-35B-A3B-NVFP4 | vLLM (agente) | 76 | 3B attivi, tutto FP4 |

- Il 26B ha 3,8B parametri attivi; con le parti dense in BF16 ogni token legge parecchi GB
  in più del 4B quantizzato. vLLM forza l'attenzione Triton (teste da 256 e 512 dimensioni:
  FlashAttention 4 non c'è).
- Le misure pubblicate di 52–70 token/s sul GB10 sono di GGUF Q4 (llama.cpp, Ollama) con
  *tutti* i pesi quantizzati (ricerca del 02/10, §2.1).
- Con tool la prima frase paga due passate (la chiamata, ~20–40 token nel formato di Gemma,
  e la risposta): a 29 token/s è ~1 s.

## 4. Vincolare le chiamate ai tool

Sonda: il prompt e i 40 tool veri (livello amministra), 20 frasi × 2, una passata non in
streaming, `tool_choice` `auto` contro `required` (vLLM usa la decodifica vincolata dello
schema per `required` e per il tool nominato).

| | Tool giusto | Argomenti validi rispetto allo schema | Tempo della chiamata med / p90 |
|---|---|---|---|
| 26B, `auto` | 40/40 | 40/40 | 0,77 / 1,59 s |
| 26B, `required` | 40/40 | 40/40 | 0,76 / 1,58 s |

- Con il parser `gemma4` di vLLM le chiamate del 26B sono già tutte native e valide:
  vincolarle non aggiunge niente, e `required` obbligherebbe a un tool anche dove non serve.
  Il nome nominato (`tool_choice: {function}`) servirebbe solo con una regola che decide il
  tool prima del modello: contro il principio 10.
- Il 4B su Ollama non si può vincolare (Ollama non ha `tool_choice` né grammatiche per i
  tool; l'API `/v1` ignora anche `num_ctx`, e con 6k token di prompt tronca). Sul 4B la via
  resta TextCallGuard.

## 5. Contesa sulla DGX

Durante la notte altri lavori hanno usato l'agente (qwen3.6, stesso vLLM della porta 8000) e
l'Ollama della DGX. Con l'agente che genera, il 26B scende da 29 a ~14 token/s e la mediana
della prima frase va a 1,47 s; anche il 4B su Ollama sale (1,22 s in un giro con la GPU
occupata). Sulla DGX l'arbitro non ferma vLLM (ricerca del 02/10, §4.5): **la contesa colpisce
qualunque modello davanti**, ma un modello più lento ne soffre di più.

## 6. Il cambio di modello: una riga

```yaml
# ~/calliope/calliope.locale.yaml, sezione llm
llm:
  llm_profilo: gemma4-e4b-ollama     # oppure gemma4-26b-vllm
```

- Il profilo vince sulle singole chiavi `llm_*` che imposta (anche quelle di
  `calliope.yaml`, che il gestore rigenera); `llm_profilo: null` torna alle chiavi. Un nome
  sbagliato si segnala con il nome più vicino e non ferma l'avvio. All'avvio Calliope stampa
  `[CONFIG] Modello della voce: profilo «…» (modello, backend; reti spente: …)`.
- Le reti stanno nel profilo: tornando al 4B si riaccendono da sole.
- Il server del 26B: `calliope motore vllm voce avvia|ferma|stato` (`setup/linux/motore/
  vllm.sh`, container `calliope-vllm-voce` su 127.0.0.1:8001, `--restart unless-stopped`,
  `--gpu-memory-utilization 0.24` ≈ 28 GiB, contesto 32k, cache fp8, il modello di chat
  corretto). Primo avvio ~4 minuti (lettura dei pesi e compilazione), poi ~3.
- **Provato sulla DGX** con il codice del ramo e la configurazione vera (`~/calliope`):
  `calliope stato` con `llm_profilo: gemma4-26b-vllm` → «modello linguistico attiva» e la
  riga del profilo; una richiesta vera «Che ore sono?» → `ora_attuale` con il 26B (0,8–1,1
  s), poi con `gemma4-e4b-ollama` → Ollama (0,86 s), poi di nuovo il 26B. Il servizio non è
  stato riavviato con il codice nuovo: la versione installata non conosce ancora
  `llm_profilo` (la ignorerebbe con un avviso); il riavvio vero va fatto dopo l'unione.

## 7. Decisione

- **La voce della DGX resta su `gemma4:e4b-it-qat`** (profilo `gemma4-e4b-ollama`, tutte le
  reti accese). Il 26B è chiaramente più bravo (+12 riuscite su 116, nessuna chiamata come
  testo, gli errori di giudizio della sera del 02/10 risolti), ma la prima frase (0,90 s di
  mediana, ~1,9 s al p90) supera l'obiettivo (0,7 / 1,5 s): in una conversazione a voce si
  sente.
- Il container `calliope-vllm-voce` è **spento** (libera ~28 GiB); si riaccende con
  `calliope motore vllm voce avvia` e si usa cambiando una riga.
- **Da provare** (serve il consenso per il download): `ollama pull gemma4:26b-a4b-it-qat`
  (~17 GB) e un profilo `gemma4-26b-ollama` (backend `ollama`, `llm_model:
  gemma4:26b-a4b-it-qat`, reti come `gemma4-26b-vllm`). Stesso banco: se la prima frase sta
  entro 0,7 / 1,5 s, si passa. Attenzione anche lì al modello di chat dopo i tool (§8).
- Le reti restano nel codice: il portatile e il 4B ne hanno bisogno (67 → 98–100 su 116).

## 8. Cose non verificate

- Il modello di chat di Gemma 4 dentro **Ollama** (renderer suo, non il jinja di Hugging
  Face): se dopo un tool il 26B su Ollama apre il canale di pensiero, serve l'equivalente di
  `gemma4_template.py` (o `think: false` lo copre: da misurare).
- Il 26B con l'audio vero (Whisper sbaglia di più delle frasi del banco).
- La qualità a voce delle risposte lunghe (racconti, spiegazioni): il banco guarda i tool,
  non lo stile.

## 9. Gemma 4 26B-A4B QAT su Ollama (03/10, notte)

`ollama pull gemma4:26b-a4b-it-qat` (14,4 GB, Q4_0, Ollama 0.35.0), stesso Ollama della voce:
i due modelli restano caricati insieme (15 + 3,2 GB). Dopo ogni prova Ollama rispondeva e il
4B chiamava `ora_attuale` («VOCE OK», 10 controlli su 10); nessun errore CUDA. Alla fine il
26B è stato scaricato dalla memoria (`keep_alive: 0`).

| | Token/s | Banco (116) | Prima frase med / p90 | A livello costante med / p90 (n=96) | Al cambio di livello med (n=20) |
|---|---|---|---|---|---|
| 4B Ollama, reti accese | 67–72 | 101 | 0,48 / 1,40 | 0,45 / 0,87 | 1,47 |
| 26B Ollama, profilo (spinte spente) | 74–79 | **110** | 0,73 / 2,06 | **0,70 / 1,19** | 2,14 |
| 26B Ollama, reti accese | 74–79 | 109 | 0,72 / 1,79 | 0,70 / 1,05 | 1,82 |
| 26B vLLM NVFP4, profilo | 29 | 112 | 0,90 / 1,84–1,90 | — | — |

- **Più veloce del 26B su vLLM** (Q4 su tutti i pesi contro esperti FP4 e resto BF16), quasi
  la stessa qualità. Senza tool la prima frase è 0,43 / 0,73 s; con un tool 0,81 / 2,14 (due
  passate, e il prefill più lento del 4B quando il prefisso cambia).
- **Cambio di livello**: nel banco le sessioni passano da amministra a familiare e ospite, e
  ogni livello ha il suo elenco di tool; Ollama tiene una sola cache del prefisso per
  modello, quindi ~6k token da rileggere: 2 s sul 26B, 1,5 sul 4B. In casa capita quando
  parla un'altra persona. Si potrebbe evitare dando a tutti lo stesso elenco di tool (il
  registro rifiuta già nel codice) o con `OLLAMA_NUM_PARALLEL` per un secondo slot: da
  misurare.
- **Errori del 26B su Ollama**: l'ora inventata copiata dalla storia (come su vLLM),
  «Michisono» cercato in biblioteca, e «scrivimi uno script Python…» scritto a voce invece di
  `delega_lavoro` (2/2; su vLLM delegava). Prove di sempre (1 giro): `prova_casa_ha_ollama`
  29/29 (0,59 s), `prova_stato_ollama` 17/17 (0,59), `prova_schermi_ollama` 18/19 (0,89; lo
  stesso caso del 26B su vLLM), `prova_agenti_ollama` 20/20 (0,85), `prova_casa` 21/21
  (0,77), `prova_pc_ollama` 31/31 (0,75), `prova_documenti_ollama` 17/17 (lettere in ~3,5 s,
  come il 4B).
- **Decisione**: profilo `gemma4-26b-ollama` (reti come `gemma4-26b-vllm`) pronto e **non
  attivato**. A livello costante rispetta l'obiettivo (0,70 / 1,19 s) e sbaglia molto meno
  del 4B; però è più lento del 4B (+0,25 s di mediana, +0,3 s al p90, ~+0,6 s al cambio di
  persona) e ha il difetto della delega del codice. Non è un miglioramento netto su
  entrambi i fronti: decide l'utente. Per provarlo: `llm_profilo: gemma4-26b-ollama` in
  `~/calliope/calliope.locale.yaml`, poi `calliope riavvia` (il modello è già scaricato;
  nessun server in più).

## 10. Stessi tool per tutti i livelli (03/10, mattina)

Il salto al cambio di livello (§9) veniva dall'elenco dei tool diverso per ospite, familiare e
chi amministra. Dal 03/10 il modello vede **lo stesso elenco** (`ToolRegistry.schemas`):
prompt di sistema e schemi sono identici byte per byte (prova a secco in `prova_brain.py`), e
il permesso lo controlla solo `ToolRegistry.call`, con una frase pronta come `risposta_finale`
(«Mi dispiace, questo posso farlo solo per chi vive in casa, e la tua voce non la
riconosco.»). Misura sull'Ollama della DGX dal portatile, via tunnel SSH (quindi tempi un po'
più alti di §9, misurati sulla DGX), banco con 7 casi in più (l'ospite che chiede lista,
ricorda e promemoria e subito dopo ora, conti e timer; un familiare dopo l'ospite), 2 giri × 65:

| | Riuscite | Prima frase med / p90 | A livello costante med / p90 (n=109) | Al cambio di livello med / p90 (n=21) | Ospite |
|---|---|---|---|---|---|
| 4B, prima | 111/130 | 0,88 / 1,85 | 0,73 / 1,34 | **1,85** / 2,17 | 14/14 |
| 4B, dopo | 115/130 | 0,71 / 1,22 | 0,71 / 1,33 | **0,63** / 1,16 | 14/14 |
| 26B, prima | 125/130 | 1,14 / 2,29 | 1,05 / 1,47 | **2,47** / 2,81 | 14/14 |
| 26B, dopo | 125/130 | 1,03 / 1,42 | 1,03 / 1,43 | **0,79** / 1,37 | 14/14 |

- **Il salto sparisce**: al cambio di livello la prima frase è come (o meno di) quella a livello
  costante; il p90 complessivo scende di 0,6–0,9 s. Gli errori restano quelli di sempre (l'ora
  dalla storia e «chi sono» col 4B, «Michisono» e lo script a voce col 26B).
- **Rifiuti**: già prima l'ospite chiamava i tool che non vedeva (scritti come testo e salvati
  da `TextCallGuard`, perché il prompt li nomina): rifiutati, con una seconda passata che
  diceva «Non posso … perché non ho riconosciuto…» in 1,1–2,3 s. Ora la frase è fissa, in
  0,4–1,0 s, e nella stessa sessione l'ora, i conti e il timer vanno come prima (nessun
  avvelenamento). Regola `permesso_livello` nel registro dei turni.
- **Prove con il modello** (1 giro, prima → dopo; 4B / 26B): `prova_memoria` 13/13 → 13/13
  (l'ospite non salva e sente la frase fissa), `prova_pc_ollama` 31/31 → 31/31,
  `prova_documenti_ollama` 17/17 → 17/17, `prova_stato_ollama` 17/17 → 16/17 e 17/17 →
  17/17, `prova_agenti_ollama` 15/20 → 20/20 e 18/20 → 18/20, `prova_schermi_ollama` 29/29 →
  28/29 e 25/29 → 28/29: le differenze sono casi di chi amministra, il cui elenco non è
  cambiato (rumore del modello).
- **Un caso peggiorato e corretto**: «Puoi collegarti alla domotica di casa?» detto da un
  familiare con la casa non configurata. Col 4B era 10/10 per il familiare ma solo 3/10 per
  chi amministra: con più tool davanti il modello risponde «non posso collegarmi…» senza
  chiamare `casa_integrazione`. Con l'elenco unico il familiare scendeva a 4/10. La
  descrizione di `casa_integrazione` ora dice «chiamalo subito, senza chiedere altro, se
  chiedono «puoi collegarti alla domotica?»»: 10/10 per entrambi (e «Come collego Home
  Assistant?» 10/10).
- **Descrizioni dei tool**: nessun dato personale (esempi generici: «Rossi», «Giulia»). Gli enum
  che vengono dall'installazione (app del catalogo del PC, modelli di documento dell'ufficio e
  dell'agente) li vede ora anche l'ospite: sono nomi di configurazione, non dati di una
  persona, ma chi aggiunge un modello di documento con il nome di un cliente lo rende
  visibile nel prompt di tutti.

## 11. Pronti per il 26B: eco del contesto, delega del codice, keep_alive (03/10, pomeriggio)

Ramo `pronti-26b`. Sonde dal portatile all'Ollama della DGX via tunnel SSH (andata e ritorno
del tunnel 0,14 s a richiesta, a connessione tenuta: solo confronti tra varianti); banco e prove
**sulla DGX**, con il codice del ramo in una cartella temporanea e l'interprete del servizio,
mentre la voce restava sul 4B.

- **Eco del contesto** (prova vera dal telefono, 14:38: «Dammi informazioni sulle balene.» →
  «Chi ti parla è Dario. Posso cercare informazioni sulle balene nella mia biblioteca
  offline.»). Sonda con 8 richieste d'informazioni × 4 (con e senza una storia breve), 4B:
  | Variante | Eco | `biblioteca_cerca` | Offerte di cercare |
  |---|---|---|---|
  | contesto «Chi ti parla è Dario (riconosciuto dalla voce).» (com'era) | 17/32 | 13/32 | 7/32 |
  | contesto come «Dati del turno (non ripeterli…)» | 5/32 | 19/32 | 5/32 |
  | prompt senza «chi ti parla è scritto nel messaggio…» | 6/32 | 21/32 | 1/32 |
  | le due insieme | 0/32 | 22/32 | 1/32 |
  | le due + «quando ti chiedono informazioni su un argomento… senza offrirti di cercarlo» | **0/32** | **27/32** | **0/32** |
  L'eco veniva da tutte e due le frasi («Chi ti parla è…» nel contesto e nel prompt). Scelta
  l'ultima riga. Se l'eco capita lo stesso, `brain.ContextEcho` toglie la frase del contesto
  dalla testa della risposta (regola di forma `eco_contesto`, rete spegnibile; resta se è
  tutta la risposta, cioè la risposta a «chi sono?»). Le domande di controllo (saluti,
  barzellette, opinioni) restano senza tool. Banco: 5 casi nuovi (3 con la biblioteca, 2
  senza: risposta dal modello, nessuna offerta) e l'eco come errore su ogni risposta.
- **Codice a voce col 26B**: sonda con 5 richieste di codice e 5 domande brevi × 2.
  | | 26B delegati | 26B a voce giusti | 4B delegati | 4B a voce giusti |
  |---|---|---|---|---|
  | prima | 1/10 | 10/10 | 8/10 | 10/10 |
  | descrizione di `delega_lavoro` («anche uno script breve…») | 4/10 | 10/10 | — | — |
  | prompt: «il codice non lo detti mai…» dentro la frase delle domande brevi | 8/10 | 10/10 | — | — |
  | prompt: «uno script, un programma o una pagina web da scrivere non li detti a voce: chiami delega_lavoro» dopo la frase delle domande brevi | **10/10** | **10/10** | **30/30** | **29/30** |
  Prima il 26B leggeva fino a 15 s di codice («Ecco uno script Python che utilizza…»).
- **Conferma implicita del codice**: col 4B «Sì, vai.» dopo «Procedo?» richiamava
  `delega_lavoro` con il compito invece dell'id; il controllo della voce del codice veniva
  prima della conferma implicita e rispondeva «non ti ho riconosciuto bene dalla voce».
  Corretto (`tools/agenti.py`): `prova_agenti_ollama` col 4B da 17/20 a 40/40 in 2 giri.
- **`llm_keep_alive`**: `"-1"` come testo faceva rispondere 400 a ogni richiesta e Calliope
  aspettava 11 minuti. Ora numeri e durate con l'unità passano, «-1» diventa -1, il resto si
  segnala; un 400 all'avvio è un errore di configurazione detto subito (`RichiestaRifiutata`).
  Il profilo `gemma4-26b-ollama` mette keep_alive -1 (sempre caricato) se i file non dicono
  niente. Attenzione nelle misure: una prova con il profilo del 4B sulla DGX manda il
  keep_alive predefinito (30m) e accorcia quello della voce viva; ripristinato a mano alla fine.

### 11.1 Misure sulla DGX (codice del ramo, 2 giri del banco, 72 casi × 2)

| | 4B (`gemma4-e4b-ollama`) | 26B (`gemma4-26b-ollama`) |
|---|---|---|
| Banco, riuscite | 139/144 | **143/144** |
| Prima frase mediana / p90 | **0,47 / 0,88 s** | 0,68 / 1,18 s |
| A livello costante (n=117) | 0,48 / 0,90 s | 0,69 / 1,23 s |
| Al cambio di livello (n=27) | 0,40 / 0,78 s | 0,59 / 1,15 s |
| Chiamate scritte come testo | 46 (salvate da TextCallGuard) | 0 |
| Errori del banco | l'ora dalla storia (3), «Calliope, chi sono?» → «Calliope.», «mostrami il documento sullo schermo» → chiede quale | «chiamami Davide» → chiede conferma (1 volta su 2) |
| `prova_casa_ha_ollama` | 29/29 (0,45 s) | 29/29 (0,59 s) |
| `prova_pc_ollama` | 31/31 (0,52 s) | 31/31 (0,77 s) |
| `prova_stato_ollama` | 16/17 (0,39 s) | 16/17 (0,56 s) |
| `prova_agenti_ollama` (2 giri, con la correzione) | 40/40 (0,61 s) | 39/40 (0,84 s) |
| `prova_documenti_ollama` (generazione PDF) | 17/17 (0,9 s) | 16/17 (1,5 s) |
| `prova_schermi_ollama` | 1 errore (0,56 s) | 27/28 frasi (0,63–0,73 s) |
| `prova_web_ollama` | 24/24 (web 0,65 s, altro 0,52) | 24/24 (web 1,11 s, altro 0,83) |

Gli errori delle prove sono quelli già visti (§9–10): «Perché non riesci a cercare su
Wikipedia?» → `calliope_stato(capacita=web)` con tutti e due, «Fammelo vedere sullo schermo»
senza contesto col 4B, «Mettimi sullo schermo i miei appuntamenti» → `appuntamenti_elenca`
col 26B, «Aprilo.» → il file sbagliato una volta col 26B. Il banco col 4B dal portatile (stesso
codice, tunnel) dava 68/72 in un giro: stessi errori.

### 11.2 Raccomandazione

**Passare la DGX al 26B** (`llm_profilo: gemma4-26b-ollama`), per tre ragioni misurate:
sbaglia meno (143/144 contro 139/144; gli errori del 4B sono di giudizio, l'ora vecchia presa
dalla storia, che nessuna rete corregge), non scrive mai chiamate come testo (0 contro 46 su
144 turni) e, con le correzioni di oggi, non ha più il difetto che lo fermava (il codice a voce:
10/10 delegati). La prima frase è dentro l'obiettivo (0,68 s di mediana, 1,18 s al p90; 0,7 /
1,5 s), anche al cambio di persona, ma resta più lenta del 4B di ~0,2 s di mediana e ~0,3 s al
p90: si sente poco, e va riprovata a voce vera. Costi: ~15 GB in più di memoria sulla DGX (ci
stanno: ~54 GB liberi con l'agente acceso), e lo stesso Ollama tra voce e scrittore dei
documenti (un PDF breve in 1,5 s contro 0,9 s del 4B). Per tornare
indietro basta la riga del profilo. Il portatile resta sul 4B.
