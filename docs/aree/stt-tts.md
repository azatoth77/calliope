# Audio: microfono, wake word, STT, TTS, chi parla

*Cattura e VAD, wake word acustica, Whisper (portatile e DGX), Piper, cuffie, impronta vocale CAM++. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Cattura + VAD | sounddevice + Silero VAD (PyTorch, oppure il suo ONNX con onnxruntime senza torch: Linux) | `calliope/audio.py` → `Listener` (`listen`, `watch_for_name`, `measure_echo`); `calliope/vad.py` → `carica_vad`, `SileroOnnx`, `SileroTorch` |
| Chi parla | CAM++ (3D-Speaker) in ONNX con onnxruntime | `calliope/speaker_id.py` → `SpeakerEmbedder`, `SpeakerRegistry`, `SpeakerContext`; `arruola.py` |
| Speech-to-Text | faster-whisper nel processo, oppure un server con l'API OpenAI (sulla DGX whisper.cpp con CUDA, servizio `calliope-whisper`; vLLM scartato) con ripiego su faster-whisper su CPU (modello di riserva dal catalogo, `whisper_riserva`) | `calliope/stt.py` → `Transcriber`, `ServerTranscriber`, `make_transcriber`, `modello_whisper`; server in `setup/linux/motore/whisper.sh`; correzione delle frasi incerte (spenta) `calliope/stt_correzione.py` → `Correttore`, `accettabile`, `min_utile`; a capo di whisper-server tolti `stt.unisci_righe`; parole incerte al modello (B, spenta) `stt_correzione.parole_incerte`, `Brain.STT_INCERTE_MSG`; frase capita trattenuta (B2, spenta) `Brain.CapitoHold`, `Brain._applica_capito`, `STT_RISCRIVI_MSG` (confronto A/B/B2/C in fondo) |
| Wake word acustica | classificatore addestrato in formato openWakeWord (ONNX) | `calliope/wakeword.py` → `WakeWordDetector`, `load_wake_detector`; usato da `Listener.listen(wake, awake_until)`. Modelli e addestramento in `wakeword/` |
| Text-to-Speech | Piper (voce `it_IT-serena-high`) | `calliope/tts.py` → `Speaker` (2 thread: sintesi e riproduzione, `_pcm`); inglesismi detti all'inglese `calliope/pronuncia.py` → `Pronuncia`, `LESSICO` (`tts_pronuncia`, `tts_pronuncia_extra`) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Riconoscimento di chi parla** con impronta neurale CAM++ e registrazione a voce
    (o `arruola.py`): al primo avvio il primo utente diventa «Primo/Prima» e amministra
    (`admin` in `speakers.json`).

  - **Wake word acustica** dedicata: da addormentata Whisper non trascrive nulla.

  - **Barge-in con il nome** («Calliope, basta») mentre parla.

  - **Cambio voce per utente.**

- Dopo ogni risposta resta sveglia per `followup_s` secondi: dentro questa finestra si
  trascrive senza bisogno del nome.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Confronto STT e correzione delle frasi incerte** (05/10, [`docs/ricerche/2026-10-05-stt-confronto.md`](../ricerche/2026-10-05-stt-confronto.md),
  `prove/misura_stt.py`): whisper.cpp resta il migliore (WER 13,4 % sulle 104 vere, 20,6 % su 150
  frasi di dominio sintetiche); Voxtral Mini 25,5 %, Parakeet v3 29,2 %, gemma4 e4b con l'audio
  37,8 % (e risponde invece di trascrivere). `stt_correzione` (spenta): con `verbose_json` le frasi
  con una parola sotto 0,5 vanno al modello della voce con il vocabolario della casa e le ultime
  frasi; vale solo se cambia parole storpiate in parole simili (`accettabile`, regola
  `stt_corretta` con prima e dopo). Col 26B: 11,4 % e 17,4 %, nessuna peggiorata, +0,4 s sul ~40 %
  delle frasi; col 4B rovina («voce» → «luce»): solo col 26B, da provare a voce.
  **Provata a voce il 05/10 sera** (DGX, 26B, 25 turni): 15 frasi al secondo passaggio, 0,84–1,50
  s l'una (STT 1,1–1,9 s invece di 0,25–0,5; una forse al tempo massimo), 3 cambiate. Cause:
  frasi vere più lunghe (più parole sotto 0,5), il modello ricopiava ogni volta la frase intera, e
  le risposte lunghe di Calliope nel prompt. Corretto: `verbose_json` di whisper-server spezza il
  testo a 60 caratteri anche a metà parola («fis\nica», «Gra\nzie», arrivati al modello e al
  registro: `stt.unisci_righe`; sulle 104 la WER senza correzione era 13,4 % per questo, 12,1 %
  senza a capo); soglia 0,4 senza contare il nome (`min_utile`: sul banco col 26B frasi al
  secondo passaggio 41 → 28 % e 44 → 35 %, migliorate 6 → 5 e 19 → 18, nessuna peggiorata);
  risposta `{"giusta": true}` senza ricopiare (e4b in locale: frasi lunghe 0,87 → 0,43 s, mediana
  0,53 → 0,44; qualità del 26B col formato nuovo da rimisurare con `misura_stt.py correggi`);
  risposte di Calliope a 120 caratteri. Nel registro `stt_confidenza` (parola più debole, quante
  sotto 0,5). La cache della voce resta (misurata in locale: nessuna rilettura dopo una correzione).

- **whisper.cpp sulla DGX** (02/10, misure in
  [`docs/ricerche/2026-10-02-impacchettamento-dgx-linux.md`](../ricerche/2026-10-02-impacchettamento-dgx-linux.md), §1.1):
  `whisper-server` legge `prompt`, `beam_size`, `temperature` a ogni richiesta (partendo dai
  valori della riga di comando, niente resta tra una richiesta e l'altra), ma **non ha le
  hotwords**: è il punto e mezzo di WER che manca rispetto al portatile. Calliope manda
  sempre il suo prompt («Conversazione con Calliope.»), che quindi vince su `--prompt`.
  Senza prompt la WER sale al 22,6 %, con il solo «Calliope.» al 19,1 %: il prompt corto
  con il nome resta il migliore. «Che ore sono» detto subito dopo il nome diventa ancora
  «Calliope. Chiori sono.» con ogni parametro.

- **RTX 5070 (Blackwell) e CTranslate2**: verificato, Whisper gira su GPU con
  ctranslate2 4.8.2 e le DLL `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` da pip. Resta
  il fallback su CPU. Se la DLL cuDNN manca, il processo su Windows può anche
  chiudersi senza sollevare un'eccezione.

- **Whisper `small` contro `large-v3-turbo`**: nel primo test `small` ha storpiato alcune
  frasi ("Io entro a posto così" per "io sono a posto così"). `large-v3-turbo` costa
  +769 MiB di VRAM contro +477, trascrive negli stessi tempi (0,17–0,29 s) ed è ora il
  predefinito. Con `llama3.1:8b` la VRAM arriva a ~7,5 GB su 8: funziona ma è al limite;
  con un LLM da 4B ci sta comoda. Qualità sulla voce reale ancora da confrontare.

- **Primo download di un modello Whisper su Windows**: la cache di Hugging Face può
  fallire con `WinError 1314` (symlink senza Modalità sviluppatore). Il codice lo scambia
  per un problema di GPU e ripiega sulla CPU (~5 s a trascrizione). Basta riavviare: al
  secondo avvio il modello è in cache e va su GPU. Controllare sempre la riga `[STT]`.

- **API di Piper**: cambia tra le versioni. `Speaker._synth` gestisce sia la vecchia
  (`synthesize_stream_raw`) sia la nuova (`synthesize` → chunk).

- **Inglesismi** (04/10, `calliope/pronuncia.py`, prove `prova_pronuncia.py`, misura
  `misura_pronuncia.py`): espeak italiano leggeva «fìle» (anche per i file del computer),
  «èmail», «uìfi», «bekàp», «pipèr»… Il suo dizionario conosce già computer, mouse, timer,
  weekend, download, password, YouTube, Spotify: nel lessico solo le 23 parole che sbaglia,
  riscritte all'italiana («fàil», «imèil», «uàifài»), più `tts_pronuncia_extra` in
  `calliope.locale.yaml`. Cambia solo il testo dato a Piper (`Speaker._pcm`, anche frasi
  d'attesa e saluto del satellite; satelliti e telefono ricevono l'audio del server), non
  `played`, la storia né gli schermi. I fonemi `[[ ]]` di piper 1.8 per una parola sola sono
  peggio: espeak legge ogni pezzo da solo («Il [[…]]» → «ˈiːl», la punteggiatura dopo il
  blocco si perde e la frase suona come una domanda); restano per le voci dell'utente, con la
  punteggiatura dentro il blocco. «file» resta «fìle» come plurale di «fila» («le file di
  sedie», «nelle prime file», «in file ordinate»). Costo 2–7 µs a frase. Whisper (CPU, una
  sintesi per frase): «Il file è…» prima «filler», «filo», dopo «file» 3/3; «OneDrive»,
  «Chrome», «Raspberry» giusti dopo (una sintesi sola: rumore). In italiano Whisper scrive «file» per
  entrambe le pronunce: le parole da sole si misurano in inglese (`--parole`). Zoom tolto
  («sùm» → «Sun»). Da ascoltare a voce.

- **Allucinazioni di Whisper** su silenzio o rumore: c'è un elenco in
  `HALLUCINATIONS`, da estendere se ne compaiono altre.

- La **finestra di follow-up** ora è misurata sull'istante in cui inizia il parlato
  (`Listener.started_at`); prima si usava la fine della frase e le frasi lunghe venivano
  ignorate.

- **Il flusso del microfono resta sempre aperto** (`Listener.__init__`); mentre Calliope
  parla l'audio viene scartato (half-duplex). Riaprirlo a ogni turno tagliava l'attacco
  delle frasi dette subito dopo una risposta. Non tornare a `with sd.InputStream` in
  `listen()`.

- **Test vocale**: il copione fisso è in `docs/test-vocale.md` (privato, fuori dal repository), con
  lo storico dei risultati. `CALLIOPE_DEBUG_AUDIO=<cartella>` registra ogni frase captata
  (WAV + trascrizione), `CALLIOPE_INPUT_DEVICE=<n>` sceglie il microfono.

- **Impronta vocale: da MFCC a CAM++** (24/09, [`docs/ricerche/2026-09-24-riconoscimento-parlante.md`](../ricerche/2026-09-24-riconoscimento-parlante.md)).
  L'MFCC accettava come Dario il 33 % delle frasi di italiani sconosciuti. Ora si usa
  CAM++ di 3D-Speaker in ONNX (28 MB, fbank in numpy, niente torch), da scaricare in
  `models/speaker/`. Con la soglia 0,48: 0,7 % di sconosciuti accettati, 0 % di voci
  Piper, Dario rifiutato 0 % sopra i 3 s e 33 % sotto i 2 s. Sotto ~1 s di voce
  l'impronta non decide e vale chi parlava nella conversazione. La zona grigia
  0,42–0,48 conferma solo fino a "familiare". L'impronta si aggiorna con le frasi sicure,
  ma non può allontanarsi da quella iniziale. **Punteggi su scala nuova**: Dario
  ~0,45–0,9, non più 0,7–0,97. Cambiando modello le impronte vecchie si scartano: si
  registra di nuovo la voce con `python arruola.py <nome>` (microfono o `--da <cartelle>`).
  Soglia da ritarare quando arriva il secondo familiare.

- **Cuffie Bluetooth** (I52):
  - tengono un buffer loro oltre a quello di PortAudio: chiudendo l'uscita si perde la
    coda della frase (si scrive `tts_tail_s` di silenzio, poi `stop()`, non `close()` da solo);
  - all'apertura e dopo qualche secondo di vuoto perdono l'attacco («iao»): si scrive
    `tts_lead_s` di silenzio all'apertura e silenzio continuo tra i turni (`tts_keepalive`);
  - dopo un riavvio delle cuffie Windows rinumera i dispositivi: si scelgono **per nome**
    con l'API (`CALLIOPE_OUTPUT_DEVICE="I52 MME"`, vedi `avvia_calliope.py`);
  - ogni tanto restano collegate ma mute (21/09 e due volte il 24/09): non è Calliope,
    un tono di `sounddevice` non si sente. Si spengono e riaccendono, poi si riavvia Calliope.
  - Il cambio voce passa dalle code di `Speaker`, così avviene tra una frase e l'altra, e
    le voci restano in memoria dopo il primo caricamento (~1,2 s l'una, precaricate all'avvio).

- **Taratura di Whisper** (24/09, [`docs/ricerche/2026-09-24-taratura-whisper.md`](../ricerche/2026-09-24-taratura-whisper.md),
  104 registrazioni con riferimento): `beam_size=5` + `hotwords="Calliope"` portano la
  WER da 14,3 a 11,0 % per +0,04 s. **Non allungare il prompt iniziale**: Whisper lo ricopia
  sull'audio incerto e inserisce «Calliope» dove non è stato detto (falsi risvegli).
  Restano 17 frasi su 104 che nessuna configurazione risolve (parole brevi, attacco
  detto in fretta, cognomi). Il warm-up usa rumore, non silenzio: sul silenzio la ricerca
  beam non si inizializza e la prima frase costava 1,17 s.

- **Wake word acustica** (`wake_mode="modello"`, predefinita). Da addormentata una frase
  senza scatto viene buttata in memoria dentro `Listener.listen`: niente Whisper, niente
  registro, niente file. Allo scatto (0,5 per 2 blocchi da 80 ms) la frase passa intera,
  con il nome, a Whisper. Il secondo stadio scarta in silenzio i risvegli in cui il nome
  non compare nel testo e il punteggio è sotto 0,9. Sulle registrazioni: 48/52 risvegli,
  0/69 falsi, ~1 falso all'ora su audiolibri; costa 1,3 ms ogni 80 ms di CPU. Il
  classificatore usa feature ACAV100M (CC-BY-NC-SA): va bene per l'uso in casa, non per
  distribuirlo. I dati di addestramento sono in `wakeword/dati/`, ~6,6 GB fuori da git.
  Se il modello manca si torna da soli alla wake word testuale.

## Confronto della trascrizione: A / B / B2 / C (07/10)

Decisione chiesta da Dario: senza la correzione la qualità scende? Quattro varianti, tutte con
una chiave in `calliope.yaml` (spente di predefinito) e un'opzione della prova end-to-end
(`python -m prove.e2e.lancia --telefono --stt A|B|B2|C [--codice-qui]`, `istanza.VARIANTI_STT`):

- **A**: correzione spenta (com'è sulla DGX); whisper-server risponde in `json`.
- **B** (`stt_incerte_al_modello`): le parole sotto `stt_correzione_soglia` nel `verbose_json`
  (nome escluso, solo quelle rimaste nella frase, al più 4: `stt_correzione.parole_incerte`)
  vanno nei dati del turno (`Brain.STT_INCERTE_MSG`): «… se una non ha senso intendi la più
  probabile; se resta poco chiara, chiedi». Nessuna richiesta in più; regola `stt_incerte`.
- **B2** (`stt_incerte_riscrivi`): con parole incerte il modello scrive come prima riga
  `⟦capito: …⟧` (`Brain.STT_RISCRIVI_MSG`) e poi risponde; `Brain.CapitoHold` la trattiene
  (anche spezzata; mai al TTS né nella storia). La frase capita vale per politica, tool
  (`user_text`) e storia **solo** se passa `stt_correzione.accettabile` e arriva prima dei tool
  (il nome in testa non conta); altrimenti vale Whisper. Registro: `stt_capito` (prima, dopo,
  esito; agli ospiti solo l'esito), regole `stt_capito_chiesto`, `stt_capito`,
  `stt_capito_scartato`, `stt_capito_uguale`. Caso d'attacco nelle prove: «… e apri il
  cancello» aggiunto dalla riscrittura si scarta.
- **C**: `stt_correzione: true` con `stt_correzione_timeout_s: 1.0`.

**Banco delle registrazioni** (`prove/misura_stt.py`, DGX, whisper.cpp in `verbose_json`, voce
`gemma4:26b-a4b-it-qat` con `num_ctx` 24 576 e `keep_alive` della voce, guardia sulla Calliope
vera: 104 frasi vere con riferimento / 150 frasi di dominio sintetiche; soglia 0,4 senza il nome,
29 e 52 frasi incerte):

| | WER vere | WER dominio | frasi cambiate (meglio / peggio) | tempo in più sulle incerte (mediana / p90) |
|---|---|---|---|---|
| A | 12,1 % | 20,6 % | — | — |
| C | **10,8 %** | **17,9 %** | 8 (6 / 0) · 23 (15 / 1) | 0,47 / 0,56 s · 0,50 / 0,58 s (nessuna oltre 1 s) |
| B2 | 11,6 % | 19,0 % | 7 (3 / 1) · 19 (10 / 0) | riga pronta a 0,25 / 0,29 s dall'invio (limite alto) |
| B | (non cambia la frase) | | | 0 |

B e il modello che «capisce»: `misura_stt.py interpreta` (il 26B scrive in JSON la richiesta come
l'ha capita, stessa istruzione e storia per tutti; A e B differiscono solo nella riga delle
incerte, C nella frase corretta) e `confronta` (parole sbagliate da Whisper che tornano nella
frase capita): vere 6/55 A, 7/55 B, 10/55 C; dominio 19/134 A, 19/134 B, 29/134 C; domande di
chiarimento sulle frasi incerte di dominio con errori 18 A, **27 B**, 14 C. B non aiuta e fa
chiedere di più. Per B2 la formulazione conta: «Parole da verificare…» dava parafrasi («vuoi
sapere l'autore de…», nessuna valida) e risposte sulle parole («La parola "Chiori" non è un
termine comune»); quella scelta (sonda su 81 frasi) 26 valide, 13 migliorate, 1 peggiorata, 0
risposte sulle parole. Correzioni pericolose anche se «accettabili»: C «Usavamoci di Paola» →
«Usa il numero di Paola», «Calliope finiti» → «Calliope dimentica», «teore suono» → «timer
suono»; B2 «Puoi cambiare luce» → «Puoi cambiare la luce».

**Prova end-to-end** (DGX, 97 passi, satelliti con le registrazioni vere e Piper; un giro per
riga; i giri senza sandbox avevano la sandbox mancante nell'istanza, difetto dell'harness
corretto: `--codice-qui` ora porta anche `setup/`):

| giro | passi riusciti | falliti per la trascrizione | falliti per altro | prima voce sentita (mediana / p90) | turni senza tool, `prima_frase_s` | STT (mediana / p90) |
|---|---|---|---|---|---|---|
| A (senza sandbox) | 89/97 | 1 | 7 (5 sandbox) | 1,96 / 2,95 s | 0,77 s | 0,15 / 0,19 s |
| A | 94/97 | 3 | 0 | 2,05 / 3,14 s | 0,81 s | 0,15 / 0,18 s |
| B (senza sandbox) | 87/97 | 3 (2 per colpa di B) | 7 (5 sandbox) | 2,05 / 3,03 s | 0,88 s | 0,25 / 0,30 s |
| B | 93/97 | 3 (1 per colpa di B) | 1 | 2,13 / 3,48 s | 0,85 s | 0,25 / 0,29 s |
| B2 | 95/97 | 1 | 1 | 2,12 / 3,33 s | 1,12 s | 0,25 / 0,29 s |
| B2 (riga senza nome, solo prima dei tool) | 94/97 | 2 | 1 | 2,10 / 3,33 s | 0,97 s | 0,25 / 0,28 s |
| C | 93/97 | 3 | 1 | 2,28 / 3,52 s | 1,07 s | 0,25 / **1,25 s** |

- **Rumore**: la stessa frase si trascrive diversa da un giro all'altro (VAD e satelliti in tempo
  reale): 1–3 passi falliti per la trascrizione in ogni variante, A compresa (A: «O no è il mio
  numero preferito», «quando è Napoli Sandro Manzoni», l'ospite «teore sonodo»). Con un giro per
  variante nessuna differenza nei passi riusciti è fuori dal rumore.
- **B peggiora**: «Computer, che un esogono» → «non ho capito cosa intendi con un esogono»,
  l'ospite «che ore sono?» → «mi sono confusa con la trascrizione», «fiore sono» → «Non ho capito
  cosa intendi»: con l'elenco delle parole nel contesto il modello commenta la trascrizione.
- **B2 non nuoce ma quasi non agisce**: con il prompt vero il modello scrive la riga in 7 frasi
  incerte su 14 e 5 su 13, quasi sempre uguale alla trascrizione; nessuna frase capita è valsa
  (nel primo giro per il nome in testa e per una riga scritta dopo un tool: corretti).
- **C costa e scade**: 21 frasi al secondo passaggio, **13 al tetto di 1 s** (nel banco nessuna:
  con la conversazione vera il prompt della correzione è più lungo e Ollama è lo stesso della
  voce), 2 cambiate («Eisenberg» → «Heisenberg», «Talliope» → «Calliope»); +0,23 s sulla mediana
  della prima voce, +0,4 s sul p90.
- **`verbose_json` costa 0,10 s a ogni turno** (STT 0,15 → 0,25 s di mediana): lo pagano B, B2
  e C su tutte le frasi, non solo sulle incerte.

**Raccomandazione (decide Dario)**: restare su **A**. C è l'unica che migliora la WER del banco
(−1,3 e −2,7 punti), ma dal vivo scade al tetto 6 volte su 10 e aggiunge latenza a tutti; B
peggiora; B2 è sicura ma con il prompt vero non corregge. Se si vuole riprovare C, prima la
latenza: un secondo posto in Ollama (o un modello dedicato) per la correzione, e misurare di
nuovo il tetto.

Altro trovato nei giri: nel passo «minore in pericolo» del primo giro A la frase di Sofia si è
spezzata in due (pausa dopo «a casa sua»), la seconda parte ha interrotto la risposta protettiva
(barge-in di livello B con la voce di Sofia) e l'avviso «sicurezza» ai tutori è partito **due
volte**; negli altri giri il passo è riuscito. «richesta_tutore» (nome del tool storpiato dal
modello) in un giro B2.

## Il nome da solo dopo lo scatto acustico (06/10, DGX in modalità startrek)

Registro dei turni della DGX: 17:20:20 «Come più tardi.» (voce 0,76 s, `risveglio` 1,0) mandato
al modello come domanda; 17:22:54 e 17:22:57 due frasi di 0,70 e 0,63 s con testo vuoto, esito
«vuoto» (il controllo del testo vuoto in `_conversazione_del_turno` veniva prima del nome, e il
punteggio del risveglio non finiva nemmeno nel registro). Erano tutti «Computer» da solo.

Ora (regola `nome_da_solo_acustico`, `ciclo.solo_nome_acustico`, principio 10: riguarda
l'audio e le storpiature del nome): a Calliope addormentata, con la wake word acustica scattata
e il punteggio sopra `wake_confirm_score` (0,9), se il nome non è nel testo e il testo è vuoto
(allucinazione o eco del prompt, già tolte in `stt.py`) oppure la voce dura al più
`wake_solo_nome_s` (0,9 s, nuovo campo: «Calliope» da solo dura 0,5–0,65 s sulla DGX) la frase
è il nome da solo: saluto (o suono d'inizio con i suoni) e finestra aperta. Il risveglio va nel
registro anche col testo vuoto. Contrari in `prova_nome_da_solo`: scatto debole col testo vuoto
(scartato in silenzio, come prima), frase vuota nella finestra («vuoto»), frase lunga senza il
nome e scatto sicuro (tutta al modello, come prima), il nome trascritto con la domanda.

Prompt e hotwords di Whisper dopo il cambio di modalità a voce: già letti da `Config.wake_names`
a ogni frase dal 05/10 (`stt.prompt_whisper`, `hotwords_whisper`; anche `ServerTranscriber`
verso whisper.cpp, che non ha hotwords). Misura sul portatile, faster-whisper large-v3-turbo, 6
voci di Piper (aurora, giorgio e leonardo sono rumorose: le frasi brevi vengono male con
qualunque prompt):

| | normale («Conversazione con Calliope.») | startrek («… con Computer.», hotwords «Calliope Computer») |
|---|---|---|
| «Computer.» con il nome trascritto | 3/6 | 4/6 (una «Calliope Computer.») |
| «Computer!» | 0/6 | 1/6 |
| «Computer, che ore sono?» con il nome | 4/6 | 5/6 |
| «Calliope, che ore sono?» con nome e domanda giusti | 3/6 | 3/6 (giorgio: «Calliope Computer suono.») |

Il resto del nome da solo è testo corto e storpiato («Ok.», «Rovemo, rovemo.», «Grazie.»,
vuoto): esattamente il caso che la regola sopra prende per durata. Il prompt non va allungato.

## Voci di famiglia: adulto e ragazzo al telefono in auto (07/10)

Sulla DGX, 06–07/10, satellite telefono in auto: più volte la voce di chi amministra è valsa
come quella di un minore registrato. Quattro casi: tre frasi con chi amministra
**primo** (0,489, 0,547, 0,534; una era la frase di sfida, rifiutata con «solo chi ha fatto la
richiesta»; una «Sì, procedi.» di 0,82 s, con l'azione proposta persa) e una con il **minore
primo sopra soglia** (0,483, 1,46 s, modo «voce»). Misure (dati veri nella scratchpad, qui solo
numeri aggregati):

- **Impronte lontane**: coseno 0,17 tra le due impronte (0,04 tra quelle dell'arruolamento). Il
  problema è il canale, non la somiglianza delle voci.
- **Sul portatile le voci si separano bene**: 345 frasi registrate di chi amministra contro le due
  impronte: margine sul minore p05 0,19, mediana 0,47; nessuna frase ≥ 1 s a meno di 0,10. Le 9
  frasi del minore registrate al portatile il 26/09: 0,44–0,70 contro di lui, ≤ 0,20 contro
  l'adulto. Corpus (22 voci MLS e VoxPopuli, 5 frasi d'impronta, stesso canale): nessuna frase
  vera sotto 0,10 di margine; 0,37 % delle frasi prese per l'altro nelle 20 coppie più vicine,
  0 % col margine 0,05.
- **Al telefono no**: chi amministra in modo «voce» ha mediana 0,641 sul telefono contro 0,746
  sul satellite dello studio; il minore è stato registrato dal telefono, quindi l'impronta del
  minore contiene il canale del telefono e le frasi dell'adulto in auto le si avvicinano. Nei
  tre casi con l'adulto primo, il minore era a meno di 0,05 (è la condizione di
  `minori.piu_protetto`).
- **L'impronta dell'adulto non può più adattarsi**: coseno 0,900 con quella dell'arruolamento,
  esattamente `speaker_adapt_max_drift`. Le frasi sicure del telefono non la spostano più.
- Il registro dei turni non aveva il secondo profilo: il margine dei turni veri non si poteva
  misurare. Dal 07/10 c'è (`voce.secondo`, `secondo_punteggio`, `margine`, e `incerta` o
  `minore_vicino` quando servono).

**Perché i primi tre casi andavano al minore: voluto.** `minori.piu_protetto` (05/10): voce di un
adulto con un minore almeno in zona grigia e a meno di `minori_margine_ambiguo` (0,05) → vale il
minore, mai un adulto per una voce dubbia. Con quei punteggi la voce era davvero ambigua.
Sbagliato era il resto: il modo «voce» per il minore a 0,483 col secondo vicino, la sfida chiusa
come se fosse un'altra persona, il «sì» perso senza dirlo.

Correzioni (07/10, `ciclo._confronta_voce`, `conferme.py`, `brain._sfida`):

- **Margine** `speaker_id_margine` (0,08): sopra soglia ma a meno del margine dal secondo profilo,
  la voce non decide (regola `voce_margine`): zona grigia se era chi parlava, poi il profilo più
  protetto, altrimenti ospite. Costo misurato: 0 % sul portatile e nel corpus.
- **Chi amministra con un minore vicino** (`minori_margine_amministra`, 0,12; il verso pericoloso:
  il minore preso per chi amministra): riconosciuto, la sua conversazione, ma al più familiare
  (regola `amministra_minore_vicino`); per le sue azioni la frase di sfida.
- **Voce incerta tra un adulto e un minore**: vale il minore (prudente) e si sa tra chi
  (`SpeakerContext.incerta`). Solo se serve per un'azione, la frase chiede chi parla («Non sono
  sicura di chi parla: Carlo o Luca? Se sei Carlo…»): un tool di chi amministra (sfida per
  l'adulto), la risposta alla sfida (parole nuove, una volta), un «sì» mentre un'azione proposta
  all'adulto è in sospeso su quel satellite (`ciclo._chiedi_chi_parla`, l'azione resta).
  Regola `voce_incerta_chiede`. Negli altri turni nessuna domanda.
- **Conferma breve**: un «sì» breve non conferma più se un altro profilo somiglia alla frase
  almeno quanto chi amministra (il 07/10 «Sì, riproviamoci.» con il minore primo confermava).
- Prova a secco: `prove/prova_voci_famiglia.py` (impronte sintetiche con lo stesso coseno, nomi di
  fantasia, i quattro casi e i contrari).

**Più impronte per persona (valutato, non fatto).** La struttura lo consente: `UserProfile` ha
`voiceprint` e `initial_voiceprint`; un dizionario `impronte_canale` (telefono, satellite,
portatile) con il punteggio = massimo sui canali, ciascuna adattata solo dalle frasi sicure del
suo canale e con la deriva misurata dalla propria impronta d'arruolamento, risolve due problemi:
l'adulto senza un'impronta del telefono e l'impronta bloccata dalla deriva. Il satellite sa già
il suo tipo (telefono o altro). Da fare insieme alla nuova registrazione del minore, per non
introdurre un'asimmetria: con un'impronta del telefono solo per l'adulto, il verso pericoloso
peggiora.

**Da provare con il minore presente**: 5 frasi d'arruolamento (≥ 2 s ciascuna, le frasi-guida)
**per canale**, telefono in auto, telefono in casa, satellite dello studio, per entrambi; poi 10
frasi brevi e 10 lunghe a testa per canale, lette alternandosi, per misurare con il registro
nuovo margine e scambi nei due versi e ritarare `speaker_id_margine` e
`minori_margine_amministra`.
