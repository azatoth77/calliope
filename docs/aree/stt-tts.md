# Audio: microfono, wake word, STT, TTS, chi parla

*Cattura e VAD, wake word acustica, Whisper (portatile e DGX), Piper, cuffie, impronta vocale CAM++. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 14/10.** Come al 09/10 (sotto), più: le forme chiuse storpiate da whisper.cpp (10/10), Whistle misurato e non adottato (10/10), la frase lunga che al tetto di 120 s si unisce al seguito (10/10), l'impronta che non si aggiorna in compagnia (12/10); la **conversazione di stanza** dal satellite e dal telefono (13–14/10, decisione 0029, spenta di serie): passo 0 (compagnia con le voci tutte riconosciute), passo 1 (sola trascrizione veloce in ombra, protocollo 3), il giudizio «rivolta a Calliope?» con le righe della stanza (passo 2), il taglio morbido dei segmenti e l'ascolto durante la voce di Calliope col filtro dell'eco (passo 5, `stanza_durante_voce`); i conoscenti (decisione 0030, sezioni in fondo); la **fine del turno System 1** (14/10 sera, Smart Turn sull'audio, spenta di serie, da misurare in ombra: sezione in fondo). Aperti come al 09/10.

*Stato al 09/10 (storico): Whisper con whisper.cpp sulla DGX e senza correzione (variante A, scelta il 07/10), Piper con la prima frase a pezzi e sulla GPU secondo la macchina (07/10), CAM++ con il margine tra i profili e la continuità delle frasi cortissime (07–08/10), pause e fine del turno solo misurate (07/10), parole incerte negli argomenti dei tool (F0 e F1, 08/10), modalità compagnia accesa con il giudizio «rivolta a Calliope?» in ombra (09/10). Aperti: whisper.cpp senza hotwords («Chiori sono»), le voci di famiglia al telefono da registrare di nuovo per canale, le cuffie Bluetooth mute.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Cattura + VAD | sounddevice + Silero VAD (PyTorch, oppure il suo ONNX con onnxruntime senza torch: Linux) | `calliope/audio.py` → `Listener` (`listen`, `watch_for_name`, `measure_echo`); `calliope/vad.py` → `carica_vad`, `SileroOnnx`, `SileroTorch`; pause e fine del turno (dal 07/10, solo misura) `calliope/pause.py` → `MisuraPause`, `OsservaRipresa`, `inizio_ripresa`, `riassunto` (sotto); la frase al tetto e il suo seguito nello stesso turno (dal 10/10, sotto) `Listener._dopo_il_tetto`, `Ciclo._seguito_del_tetto`, `pause.TETTO_ATTESA_S`; la fine del turno System 1 (dal 14/10, spenta di serie, sotto) `calliope/system1/` → `Decisione`, `Sorvegliato`, `fine_turno.SmartTurn`, `Politica`, `Anticipo` (attiva, nel `Listener`), `OmbraFineTurno` (ombra, sul server), `log_mel`, `simula`, `esito`, `riassunto` |
| Chi parla | CAM++ (3D-Speaker) in ONNX con onnxruntime | `calliope/speaker_id.py` → `SpeakerEmbedder`, `SpeakerRegistry`, `SpeakerContext`; `arruola.py`; margine tra i profili e voce incerta tra un adulto e un minore (07/10) `Ciclo._confronta_voce`, `Ciclo._chiedi_chi_parla`, `SpeakerContext.incerta`; continuità delle frasi cortissime (08/10) `Ciclo._per_continuita`; il nome da solo dopo lo scatto acustico `ciclo.solo_nome_acustico`; più voci vicino allo stesso satellite (dal 09/10, sotto) `calliope/compagnia.py` → `Compagnia`, `modo`, `riassunto`, e il giudizio «rivolta a Calliope» `calliope/rivolta.py` → `Giudice`, `etichetta` |
| Speech-to-Text | faster-whisper nel processo, oppure un server con l'API OpenAI (sulla DGX whisper.cpp con CUDA, servizio `calliope-whisper`; vLLM scartato) con ripiego su faster-whisper su CPU (modello di riserva dal catalogo, `whisper_riserva`) | `calliope/stt.py` → `Transcriber`, `ServerTranscriber`, `make_transcriber`, `modello_whisper`; server in `setup/linux/motore/whisper.sh`; correzione delle frasi incerte (spenta) `calliope/stt_correzione.py` → `Correttore`, `accettabile`, `min_utile`; a capo di whisper-server tolti `stt.unisci_righe`; parole incerte al modello (B, spenta) `stt_correzione.parole_incerte`, `Brain.STT_INCERTE_MSG`; frase capita trattenuta (B2, spenta) `Brain.CapitoHold`, `Brain._applica_capito`, `STT_RISCRIVI_MSG` (confronto A/B/B2/C in fondo); parole incerte negli argomenti dei tool (dal 08/10, F0 e F1, sotto) `calliope/argomenti_incerti.py` → `Ascolto`, `Misura`, `Vocabolario`, `allinea`, `esito`, `suggerimento`, `riassunto`, con le probabilità per parola `Transcriber.parole` e `ServerTranscriber.parole`; tempo massimo della richiesta in proporzione alla frase `ServerTranscriber.tempo_massimo` (10/10); frasi tipiche delle allucinazioni scartate per intero in `calliope/allucinazioni.py` (09/10) |
| Conversazione di stanza, passo 1 in ombra (13/10, sotto) | Silero VAD in ONNX (un secondo VAD, suo), Whisper con la precedenza, CAM++ | sul satellite `calliope/satellite/stanza.py` → `Segmentatore`, `AscoltoStanza`, rubinetto `Listener.rubinetto`; sul server `calliope/stanza/` → `Stanza` (`ascolto.py`: `copertura`, `turno_testo`, `pausa`, `riprendi`, `dimentica`, `presenti`, `presenze`, `durante_qui`, `pronto`), filtro dell'eco del passo 5 `filtra`, `Detta` (`eco.py`), `Riproduttore.voce_ora`, `Collegamento.frasi_voce`, `Copertura`, `Precedenza` (`coda.py`), `RegistroStanza` (`registro.py`), `Misure`, `riassunto` (`misure.py`), `load_stanza`; `STTCondiviso.transcribe(priorita=…, prompt=…)`; ganci `Ciclo._stanza_copertura`, `Ciclo._stanza_turno`; tool `stanza_pausa` (`calliope/tools/stanza.py`) |
| Corsia lenta della stanza (14/10 sera, passo 3, `stanza_lenta`, sotto; ritrascrizione solo con un Whisper suo o un beam che conta, `stanza_lenta_ritrascrivi`) | Whisper con la precedenza LENTA (o un Whisper suo, `stanza_lenta_stt_url`: `setup/linux/motore/whisper-lento.sh`, large-v3 q5_0), CAM++ a finestre, solo libreria standard | `calliope/stanza/lenta.py` → `Lenta` (`metti`, `dovuti`, `passo`, `giro`, `rivedi`, `prompt`, `finestre`, `pendente`), `allucinazione`, `dividi_testo`, `cambio_sostanziale`, `riassuntore_guardiano`; `calliope/stanza/banco.py` → `Banco` (eccezione dell'audio del banco); `Transcriber.transcribe(…, beam=)`; prova `prove/prova_stanza_lenta.py`, banco `prove/manuali/banco_stanza_lenta.py`, `prove/manuali/ritrascrivi_conservati.py` |
| Conoscenti (decisione 0030, 14/10, sotto) | CAM++ (impronte delle voci non riconosciute) | `calliope/stanza/conoscenti.py` → `Conoscenti`, `Conoscente`, `Gruppo`, `Proposta`, `Indizio`, `nomi_in`, `accesa`; tool `conoscenti` e `conoscente_livello` (`calliope/tools/conoscenti.py`); turni rivolti a Calliope `Ciclo._conoscente_turno`, frase breve `Ciclo._conoscente_breve` |
| Wake word acustica | classificatore addestrato in formato openWakeWord (ONNX) | `calliope/wakeword.py` → `WakeWordDetector`, `load_wake_detector`; usato da `Listener.listen(wake, awake_until)`. Modelli e addestramento in `wakeword/` |
| Text-to-Speech | Piper (voce `it_IT-serena-high`) | `calliope/tts.py` → `Speaker` (2 thread: sintesi e riproduzione, `_pcm`; la prima frase lunga a pezzi `primo_pezzo`, `tts_spezza_prima`, `tts_primo_pezzo_min`, e i thread di onnxruntime `carica_voce`, `tts_thread`, dal 07/10; velocità e costo della voce misurati all'avvio e con l'uso `calliope/taratura_voce.py` → `Taratura` (file voce_taratura.json), `tts_thread` «auto»; dal 07/10 sera Piper anche sulla GPU con onnxruntime-gpu, `tts_dispositivo` auto/cpu/cuda, scelta secondo la macchina e ripiego sulla CPU (`_su_gpu`, `prova_dispositivo`): [contesto-conversazione](contesto-conversazione.md)); inglesismi detti all'inglese `calliope/pronuncia.py` → `Pronuncia`, `LESSICO` (`tts_pronuncia`, `tts_pronuncia_extra`) |

## Problemi noti

*Fuse il 09/10 le due sezioni nate dalla divisione di CLAUDE.md (stato e problemi fino al
06/10): ogni voce una volta sola, le superate segnate come storiche.*

- **Barge-in con il nome** («Calliope, basta») mentre parla.

- **Cambio voce per utente.**

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

- **Unità di misura** (12/10, ramo `materie-calcolabili`, `calliope/unita.py`, prova
  `prova_pronuncia.py`): espeak legge i simboli lettera per lettera («3 kg» → «tre kappagì», «2,5
  m/s» → «… emme barra esse», «m/s²» → «… esse due», «°C» → «gradi ci»), legge bene i decimali con
  la virgola e male quelli col punto («due punto cinque»), e «joule» come «giòule». `Pronuncia`
  cambia un simbolo **subito dopo un numero** nel nome per esteso accordato al numero («36 km/h» →
  «36 chilometri all'ora», «1 kg» → «1 chilogrammo», «9,8 m/s²» → «9,8 metri al secondo
  quadrato»; elenco `unita.SIMBOLI_DETTI`, senza «h», «s» e «G» da soli: «5G» resta), «joule» →
  «giùl» nel lessico (fonemi `dʒˈul` controllati). Spento con `tts_pronuncia: false` come il resto;
  `Pronuncia(unita=False)` per spegnere solo le unità. Le frasi degli esercizi le scrivono già per
  esteso ([minori](minori.md)).
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

- **Finestra di follow-up**: dopo ogni risposta resta sveglia per `followup_s` secondi, e
  dentro questa finestra si trascrive senza bisogno del nome. È misurata sull'istante in cui
  inizia il parlato (`Listener.started_at`); prima si usava la fine della frase e le frasi
  lunghe venivano ignorate.

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
  Soglia da ritarare quando arriva il secondo familiare. Registrazione a voce (o
  `arruola.py`): al primo avvio il primo utente diventa «Primo/Prima» e amministra (`admin` in
  `speakers.json`).

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

## Piper sulla GPU (07/10 sera)

Sulla DGX con onnxruntime-gpu 1.30 (wheel aarch64 per CUDA 13 su PyPI, extra `voce-gpu`)
serena-high sintetizza 138 caratteri in 0,077 s invece di 0,47 (8 thread di CPU), 263 in 0,17
invece di 1,01; 0,63 ms a carattere sulle prime frasi vere invece di 3,7. Audio uguale (a
rumore spento correlazione 0,99998), 1,4 GiB di GPU, la voce che genera insieme rallenta del
~11 % con sintesi frequenti. Con `tts_dispositivo: auto` decide la taratura secondo la
macchina (portatile da 8 GB: sempre CPU; memoria unificata grande: GPU se 2 volte più veloce),
con ripiego sulla CPU a qualunque errore. Misure, regole e prove:
[contesto-conversazione](contesto-conversazione.md), «Piper sulla GPU, secondo la macchina».

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

## Frasi cortissime prese per un ospite: la continuità (08/10 sera, ramo `conversazioni-cronologiche`)

**Caso vero della DGX** (08/10 17:26, studio, registro dei turni): 13 minuti dopo l'ultima frase
di Dario, «Calliope.» con 0,5 s di voce (0,44, secondo profilo a 0,11) e la frase dopo con 0,6 s
(0,40, secondo a 0,08), sotto la soglia 0,48 → ospite; la seconda chiedeva le conversazioni
passate, rifiutata (`permesso_livello`). Dieci secondi dopo, con 1,4 s di voce, 0,71. La frase
breve «breve» (vale chi parlava) non c'entrava: la prima era fuori dalla finestra d'ascolto, la
seconda aveva un ospite prima. Sotto ~1 s il punteggio non è affidabile: sulla DGX (02–08/10)
le frasi «breve» di chi parlava stanno a 0,49 di mediana (p05 0,18), e 57 frasi corte su 266
non sono state riconosciute (ospite).

**Fatto** (`ciclo._per_continuita`, regola `voce_continuita`, principio 10: riguarda l'audio):
una frase più corta di `speaker_min_voice_s`, quando non vale già la frase breve, vale il
migliore se **su questo satellite** è stato riconosciuto dalla voce (sopra soglia, senza un
minore vicino) negli ultimi `speaker_continuita_s` (900 s), con almeno
`speaker_continuita_soglia` (0,36) e `speaker_continuita_margine` (0,20) sul secondo profilo.
- Vale **come la zona grigia** (`identified_by = "conversazione"`, `from_session`): al più
  familiare, niente conferma breve né voce sicura, e per ciò che vuole la voce di chi amministra
  la frase di sfida (registro dei tool, `conferme.admin_da_sentire`): politica e sicurezza per
  valore la trattano come prima trattavano la zona grigia, senza toccarle. Nel registro dei
  turni `voce.modo = "continuita"`, nella console «vale per continuità».
- La memoria è per corsia (`Ciclo._voce_recente`): un altro satellite non ne sa niente. Una
  frase lunga di nessun profilo o di un'altra persona la toglie (c'è un'altra voce).
- La corsia (`RegistroConversazioni.scegli`, come «continuita») continua la conversazione della
  persona se è l'ultima di questo satellite, o ne apre una nuova se non c'è (con la ripresa);
  se intanto l'ha usata un altro satellite, anonima.
- Minori: `minori.piu_protetto` resta dopo (un minore nella zona grigia vale lui); con il minore a
  meno di 0,20 il margine non basta e la continuità non scatta; un minore riconosciuto qui resta
  lui. Chi amministra con il minore vicino (`amministra_minore_vicino`) non viene ricordato.
  Sul telefono in auto i margini veri sono 0,07–0,16: lì la continuità non scatta (il problema
  dei canali resta quello delle «Voci di famiglia»).
- Misura di rischio (`prove/misura_conferma_breve.py`, stesso canale, senza la condizione del
  margine): a 0,35–0,38 passano l'1,4–0,7 % (0,5 s), 3,1–1,8 % (0,7 s), 3,6–2,4 % (0,9 s) delle
  frasi brevi di altre voci, e solo se la persona è stata riconosciuta lì da poco; le frasi
  brevi vere di Dario sotto 0,36 sono ~9 %.
- Prove: `prova_voci_famiglia` (il caso vero e i contrari: sotto 0,36, minore a meno di 0,20,
  frase lunga, un'altra persona migliore, finestra scaduta, satellite diverso, spenta, un'altra
  voce nel mezzo, il minore, chi amministra col minore vicino), `prova_corsie` (la scelta della
  conversazione). I casi di `prova_voci_famiglia` di prima passano tutti uguali.

## Pause e fine del turno: solo misura (07/10)

Decisione di Dario (07/10): oggi il turno si chiude dopo `silence_ms` = 700 ms di silenzio, uguale
per tutti e su ogni canale (`Listener.listen`; il satellite in Python con gli stessi parametri
via `protocollo.PARAMETRI`; il telefono in `voce.js`). Chi fa pause lunghe (un bambino che cerca
la parola, un anziano, chi detta un numero) viene tagliato; chi parla svelto aspetta 700 ms
per niente. In futuro la soglia si adatterà per persona, età e canale, con una partenza
anticipata. **Per ora solo misura: nessun comportamento cambiato** (stessa soglia, stessa
chiusura, nessuna regola sul testo). *Dal 10/10 una cosa cambia, il tetto `max_utterance_s`:
la frase che ci arriva non chiude più il turno (sotto, «La frase lunga»).*

Cosa si registra (campo `ascolto` del registro dei turni, nessun dato personale nuovo):

- **Pause dentro la frase** (`pause_ms`): i silenzi tra 120 ms e la soglia, contati sugli stessi
  frame silenziosi con cui il VAD chiude il turno (probabilità sotto `vad_threshold − 0,15`,
  frame da 32 ms: valori a passi di 32 ms); il silenzio di chiusura non si conta. **`parlato_ms`**
  dalla prima voce all'ultima (senza pre-roll né silenzio finale), **`chiusura`** («silenzio»,
  «lunga» per `max_utterance_s`, «rilascio» del tasto Parla sul telefono). La misura sta dove sta
  il VAD: in locale e sul satellite in Python `MisuraPause` dentro `Listener.listen`; sul telefono
  la stessa logica in `voce.js` (`MisuraPause`). Satellite e telefono la mandano con
  `frase_finita` (`pause_ms`, `parlato_ms`, `chiusura`: facoltativi; il server li controlla in
  `valida_evento` con `pause.campi_frase`; un server vecchio li ignora, un satellite vecchio non
  li manda e il turno ha l'`ascolto` senza pause).
- **Tagli probabili**: dopo la frase, per `RIPRESA_S` (2 s) dalla fine della voce, si guarda se
  qualcuno ricomincia a parlare (`OsservaRipresa`: tre frame di voce di fila). In half-duplex
  quella voce cade mentre Calliope pensa e non arriva a Whisper: è il segnale vero del taglio.
  Usa un VAD suo (Silero in onnxruntime, ~2 MB; quello di `listen` lo usa intanto
  `watch_for_name`), si sospende mentre le casse suonano (in locale `Speaker._progresso` negli
  ultimi 0,5 s, sul satellite `Riproduttore.occupato`: segnale di fine ascolto e risposta) e si
  ferma alla prima voce di Calliope (frase d'attesa o prima frase; sul satellite all'arrivo di
  «frase»). Nel turno troncato `ripresa_s` e `taglio_probabile`; il satellite lo manda con il
  messaggio nuovo `ripresa` (id dell'ascolto, `dopo_s`). La finestra utile va da `silence_ms`
  (0,7 s, già passati quando il VAD chiude) a 2 s. Sul telefono non c'è (il microfono del
  browser si ferma a fine frase: misurarla vorrebbe dire cambiarne il comportamento).
  Al turno dopo, se la frase comincia entro 2 s dalla fine di quella di prima sulla stessa
  corsia (non dal barge-in), `ripresa_dopo_s` e `stessa_persona`. E un segnale a parole:
  `inizio_ripresa` quando la frase **comincia** (dopo il nome) con «aspetta,»/«aspetta un
  attimo», «non ho (ancora) finito», «stavo dicendo», «fammi finire» (contrari: «aspetta che
  arrivi la pizza», «non ho finito i compiti»). Solo una voce del registro, nessun effetto.
- **Contesto**: `canale` (locale, satellite, telefono: il telefono passa dal ponte degli schermi,
  `PonteWs`), `satellite` (nome), `soglia_ms` in uso, `seme` se la frase parte da un barge-in,
  `fascia` d'età se chi parla è un minore; la persona è quella di `voce.nome`.

Riassunto: `calliope stato --turni --pause [--giorni N] [--json]` (`pause.riassunto`, `testo`):
per persona e canale frasi, pause (n, a frase, p50/p90/p95), parlato mediano, tagli probabili,
riprese al turno dopo, segnali a parole, chiusure, e **la soglia che si sceglierebbe** =
p95 + 150 ms tra 400 e 1300 ms, con almeno 20 pause. Le pause misurate sono tutte sotto la
soglia in uso (le più lunghe chiudono il turno): con più del 5 % di frasi tagliate la stima
sale ad almeno soglia + 300 ms («tagli frequenti»). È una stima: non si applica.

Limiti noti: la pausa dopo il nome («Calliope, … che ore sono») si conta come le altre (è
proprio una di quelle che tagliano); il VAD può dare un frame isolato di voce dentro una pausa
lunga, che la divide in due più corte; la ripresa non sa chi parla (nessuna impronta su quei
100 ms), la stessa persona si confronta solo al turno dopo; il turno si scrive all'inizio del
giro dopo, e una ripresa misurata più tardi (turno chiuso in meno di 2 s, per esempio una frase
ignorata) si perde. Prova a secco `prove/prova_pause.py` (frasi sintetiche con pause note,
satellite e server veri con un client finto, `voce.js` con node).

**Fasi successive (da decidere con i dati veri, almeno una settimana di turni):**

1. **Soglia per persona, età e canale.** Dal riassunto: partenza per fascia (piccoli e bambini più
   alta, ~1000 ms; adulti dalla stima) e per canale (il telefono in auto ha più rumore). Adattamento
   **asimmetrico**: dopo un taglio probabile la soglia di quella persona sale subito (+150 ms), con
   le frasi intere scende piano (−20 ms ogni 10 frasi, mai sotto il p95 + margine), così un errore
   costa una frase sola. Nel registro `soglia_ms` per turno e il nome della regola; la soglia va
   anche al satellite e al telefono (campo nuovo in `ascolta`, facoltativo). Chi parla si sa solo
   dopo la frase: si usa quello della conversazione in corso (finestra di follow-up) e, da
   addormentata, la soglia del canale.
2. **Partenza anticipata.** A ~300 ms di silenzio la frase già presa va a Whisper (e il modello
   può cominciare) mentre il VAD continua ad ascoltare; se la voce riprende prima della soglia
   piena si **annulla** (risultato buttato, frase che continua) e nessuno se ne accorge. Guadagno
   atteso ~400 ms sulla latenza sentita (`fine_parlato_s`), al costo di trascrizioni buttate (da
   contare nel registro); su whisper.cpp della DGX ~0,15–0,3 s a frase. Prima serve la fase 1:
   con le pause misurate si sa quante partenze si annullerebbero.

*14/10 sera: la fine del turno decisa da un modello piccolo sull'audio (System 1, Smart Turn) è
un'altra strada per lo stesso guadagno, senza trascrizioni buttate: sezione in fondo.*

## Parole incerte: chiedere e imparare le correzioni (08/10, analisi)

Rapporto: [`../ricerche/2026-10-08-parole-incerte.md`](../ricerche/2026-10-08-parole-incerte.md),
misure con `prove/misura_parole_incerte.py` e `prove/riferimenti_nomi.tsv` (40 frasi con nomi di
fantasia, tre voci di Piper). Nessuna modifica al codice.

- **whisper.cpp**: la probabilità per parola è un buon segnale **sui nomi negli argomenti** (a 0,5
  segnala 49 nomi sbagliati su 69 e 7 giusti su 39), non sulla frase intera (sulle 104 vere metà
  delle parole segnalate è giusta). faster-whisper molto meno (21/65). Un errore su tre o quattro
  ha p alta: le parole vere al posto di parole vere, «alla gente» per «all'agente» a 0,95–1,00,
  «Luca» per Lucca a 0,84.
- **Costo** del `verbose_json` sulla DGX: 0,222 → 0,372 s di mediana a ogni turno; con
  `token_timestamps=false` uguale (0,365), probabilità identiche. faster-whisper con
  `word_timestamps`: +0,04 s.
- **Vocabolario dei nomi noti** sull'argomento (lettere, somiglianza ≥ 0,7): ritrova 44 nomi
  sbagliati su 66 senza proposte sbagliate, qualunque sia la probabilità; sulle frasi intere darebbe
  16 «forse intendevi» spurii su 104.
- **Registro della DGX** (02–08/10): il 17,3 % dei turni ha un tool con un argomento che nomina
  qualcosa, 3,9 ogni 100 con quel tool fallito, 1 ogni 100 con lo stesso tool richiamato entro tre
  turni con il valore corretto.
- **Raccomandazione**: F0 misura in ombra (`stt_argomento`, `correzione_argomento`, confidenza
  chiesta solo per i turni con un tool che nomina), F1 «forse intendevi / ripetimelo» solo dopo un
  esito vuoto, F2 scheda di correzione sullo schermo personale senza fermare il tool, F3 dizionario
  per persona solo da correzioni confermate, come suggerimento e mai sostituzione nel testo.

## Parole incerte negli argomenti: misura (F0) e «forse intendeva» (F1) (08/10, ramo `parole-incerte-f01`)

Le fasi F0 e F1 del rapporto [`../ricerche/2026-10-08-parole-incerte.md`](../ricerche/2026-10-08-parole-incerte.md),
decise da Dario. Codice in `calliope/argomenti_incerti.py`; la parte di Brain (tool, registro,
regole) è in [voce-e-regole](voce-e-regole.md). Prova a secco `prove/prova_argomenti_incerti.py`
(nel livello 1), misura col modello `prove/misura_argomenti_forse.py` (manuale).

- **Argomenti che nominano qualcosa**: `ToolSpec.nomi` ({argomento: tipo}). Marcati: `dati` e
  `argomenti` di `sviluppo_collauda` (ogni valore di testo dell'oggetto, con il tipo dal nome
  dell'input: «citta» → luogo), `modifica` di `sviluppo_apri`, gli input di testo liberi di ogni
  `est_*` (`nomi_estensione`), `comando` e `cosa` della casa, `nome` di `estensione_gestisci`,
  `testo` di `anagrafica_cerca` (riservato: mai il valore nel registro) e di `pc_cerca_file`.
  **Non** `web_cerca` e `biblioteca_cerca`: il loro argomento è una domanda libera, il nome non
  si separa dal resto e l'esito non è mai «vuoto» (il rapporto sconsiglia la confidenza sulla
  frase intera).
- **Probabilità solo in questi turni, in parallelo al tool**: il ciclo passa a Brain l'audio della
  frase (`Ascolto`, attributo `ascolto_turno`); alla prima chiamata con un argomento marcato parte
  in secondo piano `stt.parole(audio)`: whisper-server con `verbose_json` e
  `token_timestamps=false`, faster-whisper con `word_timestamps`. Se la frase aveva già il
  `verbose_json` (correzione o varianti B/B2 accese) si usano quelle parole (`Confidenza.parole`).
  Il tool non aspetta: nella prova 0,25 s di tool e 0,2 s di Whisper finiscono in meno di 0,4 s.
- **Allineamento** (`allinea`): la finestra di parole della trascrizione (lunga quanto il valore,
  una in più o in meno) più simile lettera per lettera, almeno 0,5, il nome che sveglia escluso;
  dà minima e media della probabilità e se il valore è uguale alla trascrizione o il modello l'ha
  già corretto. Valore non nella frase (un «sì», un nome preso dalla storia) → «non allineato».
- **Vocabolario dei nomi noti** (`Vocabolario`): titoli e nomi delle estensioni, entità esposte,
  alias e stanze (per la casa sui pezzi di una, due, tre parole del comando), persone registrate,
  e i valori dei tool con **esito pieno** detti da chi vive in casa (solo se vengono dalle parole
  della frase, `nella_frase`: mai un nome preso da un risultato), ricaricati all'avvio dal
  registro dei turni. Somiglianza come nella misura del rapporto (lettere senza spazi, doppie
  ridotte); «forse» da 0,7 (`stt_argomenti_soglia_noto`).
- **Esito del tool** (`esito`): vuoto (campo d'errore o testo «non trovato», «nessun risultato»,
  risultati vuoti, `trovato: false`), errore, pieno, fermato (una domanda della politica o del tool
  al posto del tool). *Dal 09/10 sera* il testo conta solo se il «non trovato» riguarda un nome e
  senza dati accanto, e «NIENTE: l'azione NON è stata eseguita» è «fermato» (sezione più sotto).
- **F1**: dopo un esito vuoto, con un nome noto vicino il risultato del tool porta
  `nome_incerto` («chiudi con la domanda «Intendevi X?»»; fuori dalla busta dei dati non fidati) e
  una proposta in sospeso con il nome suggerito: il «sì» richiama il tool con quello, senza altre
  domande della politica (prova: anche il collaudo, classe pericolosa, dopo la domanda «C'è di
  mezzo il risultato di un'estensione»). Senza nome vicino e con una parola sotto 0,5
  (`stt_argomenti_soglia_p`): «chiedi di ripeterlo o di scriverlo». Mai il valore cambiato dal
  codice né il tool rilanciato da solo.
- **Costo**: sulla DGX una richiesta in più a whisper.cpp (0,37 s di mediana misurati, `verbose_json`)
  solo nei turni con un argomento marcato (17 % dei turni del 02–08/10), in secondo piano; la voce
  aspetta al più `stt_argomenti_attesa_s` (0,4 s) e solo dopo un esito vuoto, se la probabilità non
  è ancora arrivata. Sul portatile, faster-whisper vero (RTX 5070, 30 frasi di nomi): trascrizione
  0,332 s di mediana, `parole` 0,346 s; 27 nomi su 30 allineati (gli altri: frase vuota, un «sì»,
  una frase di conferma storpiata).

**Misura col modello** (`prove/misura_argomenti_forse.py 5`, gemma4 e4b su questo portatile,
estensione «Meteo città» finta): suggerimento acceso, «Patello Giugnasco» → «Non ho trovato
informazioni per Patello Giugnasco, forse intendevi Pradello Dugnasco?» **5/5**, proposta in
sospeso 5/5, «Sì.» → estensione richiamata con il nome giusto **5/5**; «Rocca Barba» (nessun nome
vicino, Whisper incerto) → chiede di ripeterlo o scriverlo 5/5, nessun nome inventato; esito pieno
→ nessun «intendevi» 5/5. Spento: 0/5 in tutti e tre (risponde solo «non ho trovato»). Con la prima
formulazione del messaggio («chiedi se intendeva…») la domanda finiva col punto 3 volte su 5 e la
proposta non restava: ora il messaggio chiede la domanda finale con il punto di domanda. Prima
frase 1,6–1,8 s col suggerimento contro 1,5–1,6 senza (qualche parola in più).

Limite: il collaudo che si ferma con un campo d'errore nel risultato (`_fallito` in
`tools/sviluppo.py`) risponde con la sua frase pronta «Lo faccio correggere?»: lì F1 non arriva al
modello (la misura resta). Da rimisurare sulla DGX con la voce vera: soglie, quanti esiti vuoti
hanno un nome noto vicino, quante correzioni spontanee (`calliope stato --turni`).

## «Forse intendevi…?» che non scattava nel collaudo (09/10 sera, ramo `sera-ricerca`)

Casi veri della DGX (09/10, collaudo di Meteocittà; qui nomi di fantasia al posto di quelli detti, le somiglianze sono misurate sui nomi veri). 20:47:47
«Prova con Cerro Maggiore e poi con Pradello Lugnasco» → l'estensione risponde come risultato
riuscito `{"da_dire": "Non ho trovato la città 'Pradello Lugnasco'. Controlla il nome e riprova."}`;
20:48:22 «Pradello Duniasco» → collaudo fermato dalla politica per valore
(`valore_non_ancorata`) e la risposta «anche per Pradello Duniasco non ho trovato nulla»; niente
«intendevi Pradello Dugnasco?» in nessuno dei due.

Dal registro (`stt_argomento`): alle 20:47 l'esito era già **vuoto** (il testo del da_dire
contava), ma il nome noto più vicino era «Cerro Maggiore» (0,40): **«Pradello Dugnasco» non era nel
vocabolario**. Era riuscito l'08/10 (15:44 e 20:11), ma prima che la misura F0 scrivesse
`stt_argomento` nel registro, e il vocabolario si ricarica solo da lì. C'è dal collaudo riuscito
delle 20:59 (esito pieno, valore dalla frase); al prossimo avvio si ricarica dal registro.
Verificato sul registro vero copiato in locale: `Vocabolario.carica_dal_registro` →
`Pradello Dugnasco, Cerro Maggiore, …`; «Pradello Lugnasco» e «Pradello Duniasco» → Pradello Dugnasco
0,93, «Patello Duniasco» 0,86, «Pradello Bluniasco» 0,83 (tutti sopra 0,7). Alle 20:48:22 l'esito
risultava **errore** invece di «fermato»: il rifiuto della politica non ha `motivo`, ha `fatto`
«NIENTE: l'azione NON è stata eseguita».

Correzioni (`calliope/argomenti_incerti.py`):
- **Esito vuoto dalle parole, con un criterio più stretto** (`dice_non_trovato`, `esito(res,
  argomenti)`, Brain passa gli argomenti): il «non trovato» in un risultato riuscito conta solo
  se riguarda un nome, cioè è seguito o preceduto da una cosa che si cerca per nome (città,
  località, comune, nome, contatto, file, voce, risultato, «nulla», «niente») o ha il valore
  passato **subito** accanto («non ho trovato 'Pradello Lugnasco'», «Pradello Lugnasco non è stato
  trovato»), e solo se accanto non ci sono dati (il valore passato ripetuto non è un dato). Si
  aggiunge «non riconosce». Contrari: «Non ho trovato pioggia, è sereno», «Non ho trovato
  pioggia a Milano» (con o senza temperatura e cielo), «Milano: non ci sono allerte meteo» → pieno.
- **Fermato**: un risultato con `fatto` «NIENTE: l'azione NON è stata eseguita» (politica,
  schema) senza «non trovato» è «fermato», non «errore».
- **Contratto delle estensioni** (`estensioni/contratto.py`, cioè CAPACITA.md, e
  `estensioni/prompt.py`): quando non trova quello che è stato chiesto, l'estensione restituisce
  anche `trovato: false` accanto al da_dire. Il campo vince sulle parole (lo leggeva già
  `esito`); le estensioni vecchie restano coperte dal testo.
- Prove a secco in `prova_argomenti_incerti`: 15 casi con gli argomenti (anche i contrari) e il
  collaudo con il da_dire che con Brain dà «intendevi Pradello Dugnasco?» e la proposta in sospeso.

Resta (non di quest'area): alle 20:48:22 il modello ha detto «non ho trovato nulla» dopo un
collaudo **non eseguito** dalla politica; e il vocabolario non conosce i nomi riusciti prima
dell'08/10 sera (nessun altro registro da cui ricavarli con l'esito).

## Più persone che parlano: la «modalità compagnia» (09/10, analisi, ramo `analisi-compagnia`)

Rapporto: [`../ricerche/2026-10-09-piu-persone.md`](../ricerche/2026-10-09-piu-persone.md).
Nessuna modifica al codice. Caso vero della DGX (08/10 sera e notte del 09/10, telefono in un
locale con un amico): l'amico preso per il minore (0,43–0,47 sul suo profilo) con un falso allarme
del guardiano, e Calliope che risponde a frasi non rivolte a lei. Misure:

- **La causa principale è la finestra d'ascolto**: in compagnia ogni risposta riapre gli 8 s di
  `followup_s` e la frase di chiunque arriva senza il nome. Nei due episodi 66 frasi su 75 sono
  arrivate nella finestra, 20 delle 23 frasi di ospiti lì dentro hanno avuto una risposta.
- **Frase contro il profilo di chi è stato riconosciuto da poco** (segnale migliore, costo zero:
  l'impronta c'è già): sotto 0,20 con almeno 1 s di voce, Dario 0 % (sei giorni, tre microfoni),
  altre voci dello stesso canale prese 2 volte su 3. Sul registro vero (02–09/10, solo numeri)
  14 % delle frasi sarebbe stato in compagnia; entrambi gli episodi presi prima del danno.
- **Gruppi tra frasi** (anche senza profilo): falsa compagnia ≤ 2,6 % delle sessioni di una voce,
  due voci prese nel 46–82 % (un amico che dice tre frasi). Utile tra ospiti.
- **Due voci dentro una frase** (finestre di 1,5 s): 6–8 frasi miste su 10, 0,7–3 % di falsi su voce
  pulita, 37–52 ms di CPU per finestra: non ora.
- **«È rivolta a me?»** col modello piccolo, giudizio separato: 26/27 rivolte e 27/29 no su frasi di
  fantasia, ~0,28 s in parallelo alla risposta; dentro la risposta stessa sbaglia di più.

Raccomandazione a fasi: F0 in ombra (registro `voce.compagnia`, regola `voci_compagnia`, giudizio
in ombra), poi niente frase breve né continuità in compagnia e la compagnia come «voce non sicura»
per i due cancelli dei minori, poi il giudizio sulla finestra d'ascolto (regola `non_rivolta`).
Impronte delle frasi solo in memoria per corsia, 5 minuti, mai su disco.

## La modalità compagnia accesa (09/10, ramo `compagnia`)

Decisione di Dario dopo la rilettura dei momenti veri (quelli segnati dal «profilo recente» avevano
davvero altre persone): il § 6 del [rapporto](../ricerche/2026-10-09-piu-persone.md), con F0 e F1
accesi e F2 in ombra. Di base il modello giudica se la frase è rivolta a Calliope; con una voce
sconosciuta in compagnia serve il nome a ogni frase.

- **Stato per corsia** (`calliope/compagnia.py`, `Ciclo.compagnia`): le impronte CAM++ delle frasi
  dell'ultima `compagnia_finestra_s` (300 s) **solo in memoria**, per satellite, mai su disco né nel
  registro. Tre prove: **profilo** (una frase di almeno 1 s di nessuno sotto 0,20 sul profilo di chi è
  stato riconosciuto lì, in qualunque ordine), **gruppi** tra frasi di almeno 1,5 s (coseno 0,25,
  gruppo valido con due frasi o una di 3 s; serve tra ospiti, due gruppi della stessa persona
  riconosciuta valgono una voce), **due profili** (due persone registrate riconosciute). La frase
  entra nella memoria prima della decisione su chi parla: la voce che rivela la compagnia vale già
  per la sua frase. Nel registro `voce.compagnia = {voci, prova, distanza, sconosciute}` e la regola
  `voci_compagnia`; in console una riga quando cambia. `calliope stato --turni` ha la sezione
  «Compagnia» (frasi in compagnia per prova, con voci sconosciute, regole, giudizi).
- Correzione rispetto al rapporto: nella prova del profilo contano solo le frasi **di nessuno**;
  una frase riconosciuta come un'altra persona registrata è la prova «due profili», non una voce
  sconosciuta (in auto Carlo e il minore stanno a 0,17 tra loro: altrimenti la famiglia
  riconosciuta avrebbe chiesto il nome a ogni frase).
- **Effetti con `compagnia_enabled: attiva`** (predefinito; «ombra» registra soltanto, «spenta»):
  una frase sotto `speaker_min_voice_s` non eredita chi parlava, non vale per continuità né per la
  conferma breve (regola `compagnia_senza_breve`: ospite, il minore resta solo sopra la soglia
  piena); la zona grigia resta per la conversazione ma le azioni vogliono la voce nella frase
  (`tools/registry.py`, regola `compagnia_voce_nella_frase`: per chi amministra la frase di sfida,
  per gli altri «ripetimelo con una frase un po' più lunga, cominciando con il mio nome»); per i
  minori la voce non è mai sicura nei due cancelli ([minori](minori.md)).
- **Nome a ogni frase** con una voce sconosciuta (`compagnia_nome_obbligatorio`, regola
  `compagnia_nome`): la finestra d'ascolto senza il nome si chiude in cima al giro e una frase senza
  il nome presa nella finestra non va al modello e non si conserva (`Ciclo._compagnia_senza_nome`).
  Passano sempre il nome (anche storpiato, tolleranza larga), la domanda dopo il nome da solo, lo
  scritto e la registrazione della voce. Torna normale quando le frasi dell'altra voce escono dai 5
  minuti. Segno sugli schermi della stanza e sul telefono ([schermi-telefono](schermi-telefono.md)).
- **Contrari** (`prove/prova_compagnia.py`, impronte sintetiche): una voce sola, la voce variabile
  della stessa persona (0,25–0,35, anche su un altro microfono), frasi sotto 1 s, finestra scaduta,
  altro satellite, lo stesso ospite tre volte, spenta; la TV crea compagnia (giusto: non va
  ascoltata). Famiglia tutta riconosciuta: compagnia sì (niente frase breve), nome obbligatorio no,
  decide il giudizio. **Telefono in auto** con il minore: è compagnia vera («due profili»), costo
  più sfide per chi amministra nella zona grigia; i margini stretti del canale restano quelli delle
  «Voci di famiglia». La falsa compagnia della persona sola resta quella misurata (≤ 0,5 % delle
  frasi sul profilo, ≤ 2 % delle sessioni coi gruppi); il punto debole è il telefono (p5 0,37).
- **I due episodi veri** riscritti in numeri nella prova: l'08/10 la frase di 0,57 s dell'amico
  resta ospite (niente guardiano del minore né avviso), la frase a 0,433 sul minore vale ancora il
  minore ma con la voce non sicura; il 09/10 le frasi lunghe dell'ospite a 0,22–0,33 accendono la
  compagnia dai gruppi alla seconda e le frasi senza nome nella finestra non si prendono.

## Allucinazioni di Whisper scartate per intero (09/10 sera, ramo `sera-voce-conversazione`)

**Caso vero della DGX** (registro dei turni): «e con il nostro corso gratuito
www.mesmerism.info.it», identica l'08/10 alle 17:03 e il 09/10 alle 20:41, su 1,7 s di rumore
nella finestra d'ascolto dello studio; presa per una frase di Dario (0,59 e 0,54) e mandata al
modello con un'azione in sospeso. È una riga dei titoli di coda dei video: Whisper è addestrato
anche sui sottotitoli e su rumore breve li ricopia. La lista di prima (`config.HALLUCINATIONS`,
24/09) aveva solo sei frasi esatte.

**Fatto** (`calliope/allucinazioni.py`, regola `allucinazione_whisper`, principio 10: riguarda la
trascrizione): la frase si scarta solo **per intero** (minuscole, punteggiatura e nome a parte),
per famiglie prese dalle liste note (discussioni di openai/whisper, soppressioni di
faster-whisper e whisper.cpp) e dai registri: `sottotitoli` («Sottotitoli creati dalla comunità
Amara.org», «… a cura di …»), `saluti_video` («Grazie per la visione», «Ciao a tutti», «Thanks
for watching»), `canale` («Iscriviti al canale»), `promozione` (corso/canale «gratuito/online» con
un indirizzo in fondo, «seguici su …»), `indirizzo` (solo un sito), `suoni` ([Musica], (applausi),
♪♪). Con il nome davanti restano rumore solo sottotitoli, canale e promozione: «Calliope, ciao a
tutti» o «Calliope, www.ilpost.it» possono essere frasi vere. Il trascrittore restituisce la frase
vuota e dice la famiglia (`ultima_scartata`, per corsia in `STTCondiviso`); il ciclo la scrive
nel registro (`allucinazione`) e il turno vale «vuoto», come prima per la lista vecchia.
- Contrari (in `prova_testo`): «Grazie.», «Grazie per la cena di ieri.», «Ho trovato un corso
  gratuito di inglese.», «Mi iscrivi al corso gratuito online www.esempio.it?», «Apri
  www.ilpost.it», «Visita www.esempio.com» (può essere una richiesta), «Attiva i sottotitoli.»,
  «Calliope, silenzio!» e «Musica.» senza parentesi.
- **Misura sui registri della DGX** (1437 turni dal 02/10, solo conteggi): 2 frasi scartate, i due
  casi veri; nessun'altra. Le frasi della lista vecchia non sono nel registro (erano già vuote).

## Il proprietario del telefono e il minore: la frase resta sua (09/10 sera, ramo `sera-voce-conversazione`)

**Caso vero della DGX** (09/10 18:48, telefono personale di Dario, registro dei turni): dopo otto
frasi di Dario riconosciute dalla voce (0,66–0,75, il minore a 0,25–0,40), «Sì, sì, grazie.»
(0,79 s: Dario 0,50, il minore 0,485 sopra soglia) e «Io volevo che tu facessi la ricerca in
realtà.» (3,0 s: Dario 0,61, il minore 0,54, margine 0,06) valevano il minore per
`minori.piu_protetto`: conversazione anonima nuova (`conversazione_altra_persona`), il contesto
della birra perso, «non ho capito a quale ricerca». Dodici secondi dopo Dario di nuovo a 0,72.

**Fatto** (`ciclo._proprietario_continua`, regola `voce_proprietario`, principio 10: riguarda
l'audio): quando la frase sarebbe del minore come profilo più protetto, resta del **proprietario
del satellite personale** (abbinato con `--personale`) se il più simile è lui (almeno
`speaker_continuita_soglia`, 0,36), se lì è stato riconosciuto dalla voce negli ultimi
`speaker_proprietario_s` (180 s, mai oltre `storia_inattiva_s`: i tempi incoerenti del § 3.12
di [`2026-10-09-regole-incongruenze`](../ricerche/2026-10-09-regole-incongruenze.md)) e se non
c'è compagnia. Segue il criterio delle corsie per «altra persona» (§ 3.11: una conversazione per
persona, mai chiusa da una frase incerta), senza aggiungerne uno. Il minore prende il posto solo
riconosciuto con sicurezza (sopra soglia e con il margine: modo «voce»).
- Vale come la continuità: al più familiare (`identified_by = "conversazione"`), nella
  conversazione del proprietario su quel satellite (corsie: «continuita»), nel registro
  `voce.modo = "proprietario"`. L'incertezza resta nota (`incerta = (proprietario, minore)`): per
  un'azione di chi amministra la frase di sfida e «non sono sicura di chi parla», come dal 07/10.
- La prudenza per il minore resta (`SpeakerContext.minore_incerto`, una frase): preset dei tool,
  contenuti e documenti guardano lui (`minori.profilo`), il guardiano giudica la frase come per lui
  e un pericolo avvisa i suoi tutori; nei due cancelli la voce vale «non sicura». Le risposte
  restano nel tono di chi amministra (il preset del minore nei dati del turno no).
- Contrari (`prova_voci_famiglia`): minore riconosciuto con sicurezza, minore più simile del
  proprietario, satellite di stanza, telefono di un'altra persona, finestra scaduta, compagnia,
  spenta (`speaker_proprietario_s: 0`), proprietario mai riconosciuto lì; la prudenza vale una
  frase. Le prove di prima (`prova_voci_famiglia`, `prova_corsie`, `prova_minori_cancelli`,
  `prova_compagnia`) passano uguali.
- Resta il problema di fondo del canale del telefono (vedi «Voci di famiglia»): da ritarare con
  le registrazioni per canale.

## Forme chiuse storpiate da whisper.cpp (10/10, ramo `forme-storpiate`)

Senza hotwords whisper.cpp storpia le forme chiuse brevi, e il nome davanti a loro: «Calliope
ricominciava.», «Calliope ricominciavo.», «E lì appena ricominciamo.», «Da lì poi ricominciamo.»,
«E lì è per ricominciare.» (tutti «Calliope, ricominciamo»), «Annullahi.», «Am nulla il lavoro.»,
«Nulla è lavoro.», «Chiudin.», «Giudino.», «Spendilo.» (sospendilo), «Alla ora, ok.» (Calliope, ok),
«Luipe. Stop.». Il nome storpiato in più parole non si riconosce con la somiglianza delle lettere
(«dalipoi» 0,53 contro «calliope», come «allora» 0,57), ma con lo scheletro delle consonanti c-l-p
(`wakeword.prefisso_nome`). Le regole e le misure (5 «ricominciamo» storpiati e 12 dati del turno
su 1299 frasi vere, nessun falso) sono in [voce-e-regole](voce-e-regole.md), «Forme chiuse
storpiate da Whisper». Il rimedio alla radice resta un'hotword o un prompt per whisper.cpp
(problema aperto «Chiori sono»).

## Whistle (Cactus Compute) misurato sulla voce vera (10/10, ramo `misura-whistle`)

Rapporto: [`../ricerche/2026-10-10-whistle.md`](../ricerche/2026-10-10-whistle.md), script
`prove/manuali/misura_whistle.py` (fuori dal runner). Whistle (`cactus-needle`, 16,9 MB, solo CPU,
italiano tra sette lingue, `keywords`, tempi e probabilità per parola) sulle 350 registrazioni vere,
contro faster-whisper come sul portatile. Sulle 104 frasi verificate a mano: **WER 62 %** (con le
keyword dei nomi 58,7 %) contro 11,9 % di large-v3-turbo, 35,3 % di small e 58,0 % di base; il nome
in testa 28–38 frasi su 172 (turbo 160), «che ore sono» 0 su 9, frasi inventate («grazie a tutti»)
16 su 344; lingua da riconoscere giusta solo in 210 su 350. Velocissimo (0,05–0,07 s a frase su CPU,
~40 MB; turbo su CPU 6,6 s), ma inutilizzabile: **nessun uso** (né sostituto, né ripiego su CPU o
ARM, né parole suggerite contro «Chiori sono», né F0/F1: a p < 0,5 segnala il 24 % delle parole
sbagliate, turbo il 47 %). Il pacchetto ha la telemetria accesa di serie e scarica il motore nativo da
Hugging Face al primo uso (ruote anche per win_arm64 e manylinux aarch64). Aggiungere i nomi alle
hotwords di faster-whisper peggiora turbo (11,9 → 14,1 %): la sola «Calliope» resta giusta. Restano
le 40 frasi dubbie da correggere a mano (`privato/misura-whistle/dubbie.html`) e 28 frasi mirate da
registrare (`prove/manuali/registra_whistle.py`, `frasi_whistle.tsv`), utili anche per whisper.cpp.

## La frase lunga: il tetto non chiude il turno (10/10, ramo `frase-lunga`)

**Caso vero della DGX, 10/10 17:32:17, satellite «studio».** Dario detta le specifiche di un gioco
parlando spedito; il turno ha `voce_s` 29,02 e il testo finisce a metà («…queste porte possono
aumentare o diminuire troppo»); Calliope parte subito con lo sviluppo mentre lui parla ancora, e il
resto diventa un turno nuovo («Vince 15 turni, ha la fortuna di beccare più.»).

**Causa confermata: il tetto, non una pausa.** `voce_s` è la durata della frase meno pre-roll e
silenzio di chiusura (300 + 700 ms): 29,02 s vuol dire 30,02 s di frase, cioè esattamente 938 frame
da 32 ms, il primo multiplo oltre `max_utterance_s` = 30 s (`Listener.listen`: `too_long`). Una
chiusura per silenzio darebbe una durata qualsiasi. Lo stesso tetto valeva sul satellite (stesso
`Listener`, parametro mandato dal server con `protocollo.PARAMETRI`) e sul telefono (`voce.js`,
riserva 20 s finché il server non manda il suo). **`silence_ms` resta 700**: il giro dice tetto, e
la fine del turno intelligente è la fase 1 qui sopra. Nella dettatura sintetica (pause di respiro
250–500 ms) nessuna pausa ha chiuso il turno.

**Correzione.**

1. **Tetto a 120 s** (`max_utterance_s`, intervallo ammesso 5–600; `calliope.yaml` rigenerato; nel
   telefono la riserva 120). Resta un tetto contro il rumore continuo (la TV).
2. **Il tetto non chiude il turno** (regola `frase_tetto`). Scelta la soluzione più semplice che non
   perde parole: quando la frase arriva al tetto `Ciclo._seguito_del_tetto` ascolta **subito** di
   nuovo, senza dire niente né suonare, e se la voce continua entro `pause.TETTO_ATTESA_S` (2 s)
   l'audio si unisce **prima di Whisper** (una trascrizione, una richiesta al modello). Dire
   «continua pure» avrebbe perso, in half-duplex, proprio le parole dette mentre Calliope parla.
   Perché l'unione sia pulita, al tetto `Listener._dopo_il_tetto` riparte il pre-roll dai frame non
   ancora letti: l'ascolto dopo comincia dal frame seguente, senza la coda della frase (doppioni) e
   senza buchi fino a `preroll_ms` tra un ascolto e l'altro (la prova a secco lo controlla con frame
   numerati; senza la correzione 8 frame si ripetevano). Lo stesso nel telefono (`voce.js`: al
   tetto `recenti` riparte dai blocchi non letti; provato con node). Sul satellite il seguito è un `ascolta`
   nuovo con `sveglia_per_s` = 2 s, il buco è il giro di rete coperto dal pre-roll; se nessuno
   continua il server manda `sveglia` e la frase vale com'è. Al più `TETTO_SEGUITI` (2) seguiti per
   turno, cioè 6 minuti: poi la frase vale com'è («tagliata»). Al tetto né il satellite in Python
   né il telefono suonano la fine ascolto (la persona parla ancora); in locale il suono arriva una
   volta, a frase intera. Il registro dei turni ha la regola e `ascolto.tetto` = `{"pezzi": n,
   "tagliata": …}`; `ascolto.chiusura` è quella dell'ultimo pezzo, `pause_ms` e `parlato_ms` sono
   della frase intera, l'inizio è quello del primo pezzo. Principio 10: non è una regola sul testo,
   riguarda l'audio che il modello non vede. `frase_finita` accetta `fa_s` fino a 600 s (era 120).
3. **Tempo massimo di whisper-server in proporzione** (`ServerTranscriber.tempo_massimo`):
   `stt_timeout_s` (5 s) vale fino a 15 s di frase, oltre cresce in proporzione (30 s → 10 s,
   120 s → 40 s, 360 s → 120 s). Con i 5 s fissi una dettatura lunga sarebbe finita su CPU
   (molto più lenta) e il server segnato giù per 30 s. Le frasi normali usano il client com'è.

**Whisper oltre i 30 s: funziona, misurato il 10/10** su una dettatura sintetica (Piper
`it_IT-giorgio-medium`, 12 frasi con pause di 250–500 ms, 70 s; script in scratchpad, non nel
repository). faster-whisper (large-v3-turbo) e whisper.cpp scorrono l'audio a finestre di 30 s da
soli: il testo arriva intero fino all'ultima frase, senza ripetizioni.

| Audio | faster-whisper GPU (RTX 5070 Laptop, int8_float16) | faster-whisper CPU (int8, ripiego) | whisper-server CPU (whisper.cpp b5130, ggml-base, -bs 5, 8 thread) |
|---|---|---|---|
| 10 s | 0,43 s | 8,9 s | 1,9 s |
| 30 s | 0,85 s | 18,8 s | 2,7 s |
| 70 s | 1,93 s | 31,5 s | 5,4 s |
| 211 s | 6,0 s | 80,0 s | 15,2 s |

Crescita quasi lineare (~0,03 s per secondo di voce sulla GPU). Con il tetto di 30 s di prima, il
pezzo di 30 s finiva su «…vince chi ha la fortuna di beccare più» come nel caso vero. Sulla DGX
(whisper.cpp large-v3-turbo su CUDA) non misurato: la DGX non si tocca da questo ramo; atteso nello
stesso ordine della GPU del portatile (0,18 s mediana per una frase breve). Il ggml-base sul
portatile è servito solo a provare il server con l'audio lungo (con il tempo massimo di prima il
70 s sarebbe andato su CPU).

Prove: `prove/prova_frase_lunga.py` (livello 2, a secco: tetto, tempo massimo, Listener con frame
numerati, `voce.js` con node, seguito unito con i contrari, giro del ciclo, satellite finto su
server vero, suoni) e
`prove/prova_frase_lunga_voce.py` (livello 3: la dettatura sintetica in un Listener con Silero VAD
vero e il tetto a 30 s raggiunto due volte, pezzi uniti e trascritti da faster-whisper: le frasi
intorno al primo taglio intere, la parola proprio sull'unione a volte storpiata da Whisper,
«paemi» per «premi»; STT 1,8–2,6 s per 70 s). Da guardare sulla DGX nel registro dei
turni: `frase_tetto` e `ascolto.tetto` (quante dettature arrivano a 120 s), `tagliata` (deve restare
rarissima).

## L'impronta non si aggiorna in compagnia (12/10 sera, ramo `compagnia-guardia`)

**Caso vero** (DGX, 12/10 sera, in auto, satellite telefono; nomi di fantasia: chi amministra
Carlo, il ragazzo Nicola, tutti e due registrati): due turni lunghi (16 s e 14 s) in cui parlavano
insieme Carlo e Nicola, riconosciuti come Nicola sopra `speaker_adapt_threshold`, hanno aggiornato
l'impronta di Nicola (`SpeakerRegistry.adapt`, media mobile): con due voci nell'audio l'impronta
della frase è un miscuglio e la sposta verso l'altra persona, cioè verso le frasi incerte tra i due
che si vedevano già quella sera (Carlo 0,508, Nicola 0,445).

**Correzione** (`Ciclo._riconosci_voce`): quando il turno è in compagnia (`t.compagnia`, lo stato
della corsia con questa frase dentro, o `SpeakerContext.compagnia`) l'impronta non si aggiorna, per
nessuno (adulti compresi); regola `impronta_compagnia` e in console «· impronta non aggiornata: in
compagnia», nel registro dei turni `voce.aggiornata: false`. Vale anche con `compagnia_enabled:
ombra` (riguarda il dato dell'impronta, non una decisione sulla voce); con `spenta` tutto come
prima. Un turno con più voci dentro rende la corsia «in compagnia» già per sé (la frase entra nella
memoria prima della decisione, sezione «La modalità compagnia accesa»), quindi è compreso. Prova
`prova_compagnia` (`prova_impronta`: da solo aggiornata, in compagnia no per il minore e per chi
amministra, con la regola e la riga; contrario compagnia spenta).

Resta: l'impronta di Nicola sulla DGX è già stata spostata da quei due turni; va **rifatta** (o
ripristinata dall'impronta dell'arruolamento) prima di ritarare: vedi il problema aperto «Voci di
famiglia al telefono».


## Passo 0 della conversazione di stanza: la compagnia con le voci tutte riconosciute (13/10, ramo `stanza-passo-0`)

**Caso vero** (12/10 sera, in auto, telefono come satellite, Carlo e Nicola registrati: nomi di
fantasia). Con due profili riconosciuti la compagnia c'era, ma il nome obbligatorio scatta solo con
una voce sconosciuta: le chiacchiere negli 8 s dopo una risposta arrivavano al modello **con i
tool**, la conversazione anonima del telefono si chiudeva a ogni passaggio tra i due, e una frase
breve storpiata del ragazzo è stata presa dal rilevatore per un pericolo. È il passo 0 del progetto
[`2026-10-13-conversazione-di-stanza.md`](../ricerche/2026-10-13-conversazione-di-stanza.md)
(decisione [0029](../decisioni/0029-conversazione-di-stanza.md)), utile già senza la stanza. Tre
punti, un interruttore ciascuno, accesi di serie:

- **Azioni col nome** (`compagnia_azioni_col_nome`, regola omonima,
  `tools/registry.senza_nome_in_compagnia`): in compagnia (`SpeakerContext.compagnia`) una frase
  presa nella finestra d'ascolto **senza il nome** (`SpeakerContext.senza_nome`, scritto dal ciclo
  nella fase del nome: non dopo il nome da solo, non per lo scritto né per il barge-in) può avere
  risposte e letture (classe d'effetto E0, `valore.effetto`), mai un'azione: «Dimmi pure
  «Calliope, …» e lo faccio.» («Computer» in modalità startrek; catalogo
  `permesso.compagnia_nome`). Il «sì» della stessa persona alla proposta in sospeso passa
  (`tool_in_sospeso` c'è solo se la domanda era per chi parla).
- **Conversazione anonima condivisa** (`compagnia_anonima_condivisa`, regola
  `compagnia_anonima_continua`): dettagli in [contesto-conversazione](contesto-conversazione.md).
- **Rilevatore solo sulle frasi rivolte** (`compagnia_pericolo_solo_rivolte`, regola
  `pericolo_non_rivolta`): dettagli in [minori](minori.md). Il giudizio «rivolta» resta in ombra:
  qui conta il suo esito, non la sua modalità.

`SpeakerContext.compagnia_sconosciute` dice per la frase se tra le voci ce n'è una che nessun
profilo riconosce (serve alla conversazione condivisa). Le tre regole sono contate nella sezione
della compagnia di `calliope stato --turni` (`compagnia.REGOLE`). Prova a secco
`prove/prova_compagnia_passo0.py` (fallisce su cd49f11), con i contrari: una persona sola, col nome,
dopo il nome da solo, voce sconosciuta di mezzo, giudizio guasto, interruttori spenti.

**Da provare a voce** (in auto con il telefono, Carlo e Nicola): dopo una risposta, Nicola dice
senza il nome «metti un timer di cinque minuti» → «Dimmi pure «Calliope, …» e lo faccio.» e niente
timer; «che ore sono?» senza il nome → risposta; nel journal nessun «conversazione chiusa: parla
un'altra persona» tra i due, e `compagnia_anonima_continua` nelle regole.

## La conversazione di stanza, passo 1: in ombra, sola trascrizione veloce (13/10, ramo `stanza-passo-1`)

Il passo 1 del progetto [`2026-10-13-conversazione-di-stanza.md`](../ricerche/2026-10-13-conversazione-di-stanza.md)
§ 6 (decisione [0029](../decisioni/0029-conversazione-di-stanza.md)): Calliope **ascolta e trascrive
la stanza** vicino ai satelliti che lo sanno fare, sa chi ha detto cosa e chi è presente, e **non lo
usa ancora**: niente arriva al modello, si misura soltanto. Di serie `stanza: spenta` (nessun flusso,
niente caricato); si accende nel file locale con `stanza: ombra` e, se si vuole, `stanza_satelliti`
(per nome; vuoto = tutti). La protezione del turno è la misura più importante: `stt_s` e prima frase
non devono cambiare.

- **Sul satellite** (Python e telefono, protocollo 3: [satelliti](satelliti.md)): un rubinetto
  copia ogni frame del microfono (`Listener.rubinetto`, non blocca) verso un thread con **il suo**
  Silero VAD (`AscoltoStanza`; sul telefono `AscoltoStanza` di `voce.js` con una sessione ONNX sua).
  `Segmentatore`, uguale nei due linguaggi (la prova lo confronta con Node): segmenti chiusi dal
  silenzio (`silence_ms`) o dal tetto corto `stanza_segmento_max_s` (20 s), nulla sotto
  `min_speech_ms`, poi a gruppi di 8 frame (256 ms) mentre si parla. **Half-duplex** come i comandi:
  con le casse occupate il segmento in corso si butta (chiusura «voce») e non se ne aprono altri
  (il passo 5 lo cambierà). Un segmento sovrapposto all'audio dei comandi porta l'id di
  quell'ascolto (`ascolto`).
- **Sul server** (`calliope/stanza/`): `Stanza` riceve i segmenti (audio **solo in RAM**, buttato a
  trascrizione fatta), li trascrive in una corsia veloce **senza il prompt col nome** (§ 5.4:
  «Conversazione con Calliope.» farebbe inserire il nome; da misurare la WER) e attribuisce chi parla
  con CAM++ con le regole di sempre (soglia e margine: «voce»; poco sotto: «grigia»; altrimenti
  «ignoto»), mai verso l'alto (niente permessi, niente impronte aggiornate). Un segmento legato a un
  turno non si trascrive: la riga la scrive il ciclo con il testo del turno, «rivolta: sì»
  (`Ciclo._stanza_turno`). Le righe di un minore sono segnate (`minore`).
- **Whisper con la precedenza** (`stanza/coda.py`, `Precedenza` dentro `corsie.STTCondiviso`, che
  con la stanza accesa avvolge Whisper anche con una corsia sola): **turno > recupero > stanza >
  lenta**. La stanza non comincia un segmento mentre qualcuno parla a Calliope (audio b"A" negli
  ultimi 0,6 s) né mentre una frase di un turno aspetta Whisper; una trascrizione già in corso non si
  interrompe (un segmento da 20 s costa ~0,6 s sulla GPU, la misura dirà).
- **All'interpellazione si recupera prima** (§ 3.11): al primo audio dei comandi di un satellite, i
  suoi segmenti detti prima passano davanti agli altri della stanza (dopo la frase del turno). A
  frase trascritta il ciclo chiede la **copertura** (`Stanza.copertura`): le righe chiuse prima
  dell'inizio della domanda negli ultimi 120 s, quante già pronte, e a turno scritto il tempo per
  finirle; nel registro dei turni `stanza.copertura` = {`dette`, `pronte`, `recupero_ms`, `oltre`
  (più di `stanza_recupero_max_s`, 1,5 s), `in_coda`}.
- **Presenza per persona** (§ 3.5 ter, chiesto da chi amministra il 13/10): la voce sopra soglia su
  un satellite apre o allunga la presenza lì; sentita su un altro, quella di prima si chiude (evento
  `presenza` con inizio e fine nel registro della stanza) e si conta il cambio di stanza
  (`cambio_stanza` nelle misure, con i secondi dall'ultima volta di là); dopo `stanza_presenza_s`
  (600 s) senza sentirla si chiude da sola. `Stanza.presenze(persona)` dà gli intervalli (satellite,
  inizio, fine) per i passi 2 e 4.
- **Pausa e ospiti** (§ 3.10, risposta 6): tool `stanza_pausa` (azioni `ospiti`, `pausa`,
  `riprendi`, `stato`). «Calliope, abbiamo ospiti» la può dire chiunque (spegne): la stanza di quel
  satellite si ferma per `stanza_ospiti_ore` (4 h); «smetti di ascoltare la stanza (per mezz'ora)»
  per i minuti detti o `stanza_pausa_min`; **riprendere solo un adulto riconosciuto dalla voce**
  (mai un ospite, un minore, la zona grigia, lo scritto). Il satellite riceve subito il messaggio
  `stanza`, gli schermi il segno ([schermi-telefono](schermi-telefono.md)). Classe «sicuro» nella
  politica (il tool controlla da sé chi riaccende), effetto E1.
- **«Dimentica»**: `conversazioni_dimentica`, al «sì», svuota anche il registro della stanza del
  satellite da cui si parla e butta i suoi segmenti in coda (regola `stanza_dimenticata`).

Registro e misure: [contesto-conversazione](contesto-conversazione.md). Prove: `prove/prova_stanza.py`
(livello 1, server vero e satelliti finti, contrari: versione 2, satellite fuori elenco, stanza
spenta) e `prove/prova_stanza_voce.py` (livello 3: satellite Python vero e telefono nel browser).
Misure a secco (portatile): sulla riga di prova del satellite vero una frase di 1,9 s porta 70 kB
di stanza; il telefono nel browser ~52 kB per secondo di parlato (voce del VAD, cioè ~180 MB per ora
di parlato contando pre-roll e silenzio di chiusura: più dei 115 MB del conto del § 3.1, da rivedere
sulla DGX con `calliope stato --turni`). **Da misurare sulla DGX**: `stt_s` e prima frase dei turni
con e senza stanza (la sezione «Stanza» li mette accanto), ritardo della coda (p90 < 10 s), ore di
parlato per satellite, recupero oltre 1,5 s, banda del telefono in auto.

## Il giudizio «rivolta a Calliope?» con le righe della stanza (14/10, ramo `stanza-passo-2`)

Passo 2 della conversazione di stanza (§ 2.4 e § 3.4 del
[progetto](../ricerche/2026-10-13-conversazione-di-stanza.md)): il giudizio sbagliava sui blocchi
brevi perché vedeva solo gli scambi **con Calliope**. Con `stanza_contesto: true` il ciclo gli
passa anche le ultime righe della stanza del satellite (al più 6 negli ultimi 120 s, con chi le ha
dette, «→ Calliope» per quelle dette a lei, senza la frase del turno: `stanza/contesto.righe_rivolta`),
sotto «Nella stanza, poco prima (trascrizione automatica, con chi parlava…)» e prima di «Ultimi
scambi con Calliope:» (`rivolta.messaggi(contesto, frase, stanza)`). Il prompt è lo stesso e senza
righe i messaggi sono quelli di prima (contrario nella prova). **Resta in ombra**
(`compagnia_rivolta`): nel registro dei turni `rivolta.stanza` dice quante righe ha visto; si
accende solo dopo la rilettura di chi amministra su un giorno vero (obiettivo ≥ 90 % giusti sui
brevi). Una frase ignorata o non rivolta resta nella stanza con «rivolta: no» (evento `analisi`),
dettagli e blocco nei dati del turno in [contesto-conversazione](contesto-conversazione.md).
Prova: `prove/prova_stanza_contesto.py`.

## Il taglio morbido dei segmenti della stanza (14/10, ramo `stanza-durante-voce`)

Chiesto da Dario: il tetto `stanza_segmento_max_s` (20 s) chiudeva il segmento **di netto**
(`_chiudi("lunga")`), anche a metà di una parola, e Whisper e CAM++ ricevevano due pezzi storpiati.
Ora il tetto è morbido, uguale nel `Segmentatore` del satellite (`calliope/satellite/stanza.py`) e in
quello del telefono (`voce.js`):

- negli ultimi `stanza_taglio_zona_s` (4 s) prima del tetto il segmento si chiude alla **prima
  micro-pausa**: VAD sotto soglia per `stanza_pausa_breve_ms` (160 ms, contro i 700 di
  `silence_ms`), chiusura **«pausa_breve»**;
- senza pause si chiude comunque `stanza_tetto_duro_s` (5 s) dopo il tetto, chiusura «lunga»;
- il pezzo dopo riparte dal pre-roll (300 ms), quindi nessun frame di parlato si perde (la pausa
  è già nel pezzo di prima); `stanza_taglio_zona_s: 0` torna al taglio netto di prima.

Il server manda i tre valori nello stato della stanza (`taglio_zona_s`, `pausa_breve_ms`,
`tetto_duro_s`, campi facoltativi del protocollo 3, [satelliti](satelliti.md)); accetta la chiusura
«pausa_breve» come «silenzio» e «lunga», e stima la fine del parlato togliendo la micro-pausa (non
più i 700 ms del silenzio anche per i tagli). Un segmento che finisce da sé dentro la zona si chiude
anch'esso alla micro-pausa (prima dei 700 ms): conta come «pausa_breve». Nelle misure ogni segmento
porta la sua `chiusura`, e la sezione «Stanza» di `calliope stato --turni` dice per satellite
«chiusure: silenzio N, taglio morbido alla pausa breve N, tetto duro N».
Prove in `prove/prova_stanza.py` (a secco, con Node per il telefono): parlato continuo → tetto duro a
15 s; pausa breve prima della zona → nessun taglio; micro-pausa nella zona → taglio lì e nessun
frame di parlato perso; buco di 96 ms → nessun taglio; voce.js uguale al Python; con la zona a 0 il
taglio netto di prima.

## Passo 5 della stanza: ascolto durante la voce di Calliope, con il filtro dell'eco (14/10, ramo `stanza-durante-voce`)

Il passo 5 del [progetto](../ricerche/2026-10-13-conversazione-di-stanza.md) (§ 5.3, decisione
[0029](../decisioni/0029-conversazione-di-stanza.md)): fino a ieri, mentre Calliope parlava, il
segmento della stanza in corso si buttava (chiusura «voce») e non se ne aprivano altri, e ciò che
le persone dicevano sopra la sua voce era perso. Con **`stanza_durante_voce: true`** (di serie
`false`, nel file locale) la stanza ascolta anche mentre lei parla. **Solo la stanza**: i comandi
restano half-duplex (principio 8), la wake word acustica e il barge-in non cambiano, e un
«Calliope, basta» detto sopra la voce è un segmento legato al turno, non trascritto due volte.

- **Satellite e telefono**: il `Segmentatore` con `durante` acceso non butta il segmento quando le
  casse suonano e porta in `stanza_fine` gli id delle frasi che suonavano (`durante_voce`), dalla
  frase che il `Riproduttore` sta riproducendo o ha finito da meno di 1 s (l'eco dura un po' dopo;
  0 per il saluto e i segnali). Il pre-roll con la sua voce non si svuota più. Spento, i messaggi
  sono identici a prima ([satelliti](satelliti.md) per i campi del protocollo).
- **Server** (`Stanza`): le frasi di quell'intervallo sono quelle segnate dal satellite più quelle
  che, per l'ora del loro `suona` e la durata, cadono nel segmento (± 1,5 s, più la coda di 1 s): il
  testo è esattamente quello mandato a Piper (`Collegamento.frasi_voce`).
- **Filtro dell'eco** (`calliope/stanza/eco.py`, regola `eco_stanza`, ammessa dal principio 10: è
  sulla trascrizione, che il modello non vede, e toglie soltanto). Le parole della riga e le sue,
  normalizzate (minuscole, senza accenti, apostrofo come spazio, cifre in lettere: Piper dice
  «diciannove», Whisper scrive «19»), si allineano in ordine con difflib: una fila di **3 parole**
  uguali si toglie (`eco_stanza_fila`); se combacia almeno il **60 %** della riga è eco tutta
  (`eco_stanza_quota`: l'eco storpiata); una parola storpiata conta come la sua se ha almeno 6
  lettere e somiglia per almeno 0,7 («divario» per «binario»; «grazie» e «gradi» no); una riga fatta
  **solo del nome** è eco (`eco_stanza_nome`: Whisper senza prompt lo inventa sulla sua voce, e chi
  la chiama davvero passa dal flusso dei comandi). Conta solo una parola **nel tempo**: il suo
  istante stimato in proporzione dentro la frase, entro 1,5 s dal segmento. Il resto resta come riga
  di una persona, segnata `durante_voce` con le `eco_tolte`; la riga senza niente che resta è
  scartata «eco». Contrari nella prova: una sua parola ripetuta dentro la frase di una persona,
  «grazie» sopra la sua voce, «Torino?» ripetuto tre secondi dopo, la sua frase citata quando non la
  diceva. Limite noto: una parola sola detta nello stesso istante in cui la dice lei è eco.
- **Cancello per satellite** (§ 5.3 c): con l'eco misurata sul saluto oltre `barge_in_echo_max`
  (0,05: casse senza cancellazione) quel satellite resta half-duplex anche per la stanza (stato
  `durante_voce: false` mandato dopo il «pronto»; un segmento segnato si butta «eco_cancello»).
  L'eco non misurata (niente saluto, il telefono) lo lascia aperto.
- **CAM++ non decide** (segnale b del § 5.3, valutato senza dipendenze nuove). Misura a secco del
  14/10 sulle 18 frasi di serena-high dei dati di `models/speaker/` con un'eco simulata (banda
  250–3800 Hz, riverbero breve, saturazione, da −12 a −30 dB): similitudine dell'eco con la stessa
  frase pulita p10 0,29, p50 0,38, max 0,60; contro il profilo medio della voce p50 0,34; 80
  persone vere (MLS, VoxPopuli) contro il profilo p50 0,15, p90 0,27, max 0,32; una persona con
  l'eco sotto di 6 dB fino a 0,56. Le due nuvole si sovrappongono: un taglio sull'impronta
  butterebbe persone. Si rimisura con l'eco vera (`--campp` della misura manuale).
- **Misure** (senza parole): ogni segmento detto durante la voce porta `durante`, le frasi
  confrontate, le parole nuove dette da lei, le parole della riga, le tolte e la `residua` (parole
  rimaste che combaciano con lei). In `calliope stato --turni`, sezione «Stanza», per satellite:
  «durante la voce (passo 5): N segmenti, righe tenute (parole recuperate), scartate per eco,
  parole di Calliope tolte; eco residua stimata X ogni 100 parole dette (obiettivo < 2)», con ⚠
  oltre 2. La stima è per eccesso (conta anche chi ripete una sua parola); le **righe false** si
  contano solo nella misura manuale (scenario «nessuno parla»).

**Misura a secco del giro intero** (`prove/manuali/misura_eco_stanza.py --a-secco`, sul portatile:
Riproduttore, VAD, Whisper large-v3-turbo vero e filtro; eco **simulata**, non una misura di
cancellazione vera; 20 risposte del copione, 227 parole dette):

| Eco simulata | Scenario | Senza filtro | Con il filtro | Righe false | Note |
|---|---|---|---|---|---|
| −35 e −40 dB | nessuno parla | 0 | 0 | 0 | il VAD della stanza non scatta sull'eco: nessun segmento |
| −30 dB | nessuno parla (due giri) | 33,5 e 37,0 parole ogni 100 dette | 9,3 e 20,7 | 7 e 6 | tolte le righe di sola eco (4–6 per giro) e i tratti di 3 parole; restano l'eco storpiata oltre il riconoscibile («il preco che va in fondo…») e le parole inventate da Whisper sulla sua voce («Calliope», tolte dal giro col nome; «Grazie») |
| −30 dB | una persona legge 100 parole sopra la voce | — | eco residua 0–0,4 | — | WER della lettura 0,03, uguale alla stessa lettura a Calliope muta (0,03): le parole della persona si recuperano tutte |
| −30 dB | due persone chiacchierano | — | eco residua stimata 1,3 | — | le 6 frasi delle persone tenute intere, 2–3 righe di sola eco scartate; restano 2–3 «Grazie» inventati da Whisper e 2 frasi d'eco storpiata |

Lettura: il filtro sul testo serve (dimezza o più l'eco che passa) ma **non basta da solo** quando
l'eco residua è forte (−30 dB, il VAD scatta): l'obiettivo < 2 ogni 100 parole e 0 righe false si
regge solo se la cancellazione vera tiene l'eco sotto la soglia del VAD, come nella simulazione a
−35 dB. Le righe false che restano sono parole che Whisper inventa o storpia sull'eco: la misura
vera dirà se servono il segnale CAM++ (b) o una soglia del VAD più alta durante la voce.

**Misura vera sul portatile (14/10 sera, satellite «studio»: microfono interno in MME con la
cancellazione dell'eco di Windows, casse interne; `prove/manuali/misura_eco_stanza.py`, numeri in
`privato/eco-stanza`)**: 20 frasi di Calliope, 227 parole, ~88 s per prova.

| Prova | Volume | Segmenti durante la voce | Righe false | Eco residua /100 | Lettura (WER) |
|---|---|---|---|---|---|
| muto | 50 % | 1 (una parola) | 1 | 0,44 | — |
| muto | 80 % | 0 | 0 | 0,0 | — |
| lettura sopra la voce | 80 % | 3 | — | 2,2 (stima per eccesso) | 0,10 su 100 parole lette |
| lettura, Calliope muta | — | — | — | 0,44 (coincidenze col copione) | 0,37 (riferimento rovinato: lettura iniziata prima che lo script ascoltasse) |

Lettura: sul portatile la cancellazione di Windows tiene l'eco sotto la soglia del VAD (il caso
«−35 dB» della simulazione): all'80 % nessun segmento nasce, a metà volume una sola parola. La
stima dell'eco nella lettura conta anche le parole della persona che coincidono col copione (0,44
anche a Calliope muta), quindi l'eco vera è sotto 2. Una persona che legge sopra la voce è
trascritta con WER 0,10. CAM++ (segnale b): similitudine dei segmenti con le frasi di Calliope
p50 0,12, max 0,22, quindi qui non serve. Non misurata la chiacchiera a due (una persona sola).

**Da misurare sul vero** (passi in [`prove/manuali/misura-eco-stanza.md`](../../prove/manuali/misura-eco-stanza.md)):
telefono in auto (motore acceso e spento, volume medio e alto) e in casa, portatile col microfono
interno in MME, e il contrario delle casse esterne senza cancellazione (cancello chiuso). Si accende
sulla DGX solo se l'eco residua resta sotto 2 ogni 100 parole e le righe false a 0. Prove:
`prove/prova_stanza_eco.py` (livello 1, ~3 s).

## I conoscenti: voci sconosciute di adulti col nome dedotto (14/10, ramo `stanza-conoscenti`)

Decisione [0030](../decisioni/0030-conoscenti.md) (passo 7 del
[progetto](../ricerche/2026-10-13-conversazione-di-stanza.md), § 3.10), dietro
**`stanza_conoscenti: true`** (di serie `false`, nel file locale; vale solo con la stanza accesa).
Codice in `calliope/stanza/conoscenti.py`; per quest'area conta come cambia **chi parla** nelle
righe della stanza (`Stanza._chi`):

- **Ordine**: prima la famiglia come sempre (sopra soglia e con il margine → «persona:<id>»); poi,
  se la voce non è della famiglia sopra soglia, i **conoscenti** salvati (`conoscenti.json`):
  sopra `speaker_id_threshold` e con `speaker_id_margine` sia dal secondo conoscente sia dal
  familiare più vicino → riga «conoscente:<id>» con `nome` («Marco Rossi»), `nota` («collega di
  Carlo») e sicurezza «voce». Un conoscente **non è in `speakers.json`**: i comandi
  (`SpeakerContext`, compagnia, conferme) non lo vedono mai, resta ospite.
- **Gruppi in memoria**: una voce di nessuno («nessuna», con almeno `speaker_min_voice_s`) entra nel
  gruppo più somigliante (centro = media normalizzata delle ultime 30 impronte, sopra
  `speaker_id_threshold`) o ne apre uno; la riga ha `gruppo` (solo in memoria). Al più 60 gruppi,
  via dopo 24 h senza sentirli; la zona grigia non fa gruppi (potrebbe essere di famiglia).
- **Il nome** (regola `conoscente_nome`, forme chiuse, effetto solo una proposta): un vocativo o un
  saluto («Ciao Marco!», «Marco, tu che dici?», «…, Marco?») vale 1 punto per il gruppo della
  **prima riga di un'altra voce** dopo, entro 15 s (se risponde il familiare con quel nome non conta
  per nessuno); «sono Marco», «mi chiamo Marco» detti dal gruppo valgono 2; il nome detto dal gruppo
  in terza persona −1; la terza persona degli altri niente. Proposta con almeno
  `conoscenti_soglia` (3) punti da due righe, il secondo nome sotto la metà (indizi discordi:
  niente, misura «discordi»), e almeno tre segmenti e `conoscenti_min_voce_s` (6 s) di voce.
- **La proposta** va solo agli schermi personali di chi amministra (scheda `conoscente`, fuori
  dalla cronologia su disco), con un pezzo di trascrizione (le due righe del vocativo, o la
  presentazione) e gli avvisi: omonimo di un familiare («In famiglia c'è già Bianca…»), di un
  conoscente («un altro Marco, non Marco Rossi?»), età non stimata. Senza uno schermo collegato
  aspetta e si riprova ogni 5 s. Sì (nome, cognome, nota) → il conoscente con l'impronta del
  centro del gruppo; No → il gruppo e l'impronta fra le rifiutate (in memoria: un gruppo nuovo
  della stessa voce nasce già rifiutato).
- **Età**: un gruppo che uno stimatore giudica di un bambino (due voti e la maggioranza) non si
  propone mai; lo stimatore non c'è ancora (`Conoscenti.eta = None`) e la proposta lo dice.
- **Sentito** e **scadenza**: l'ultima volta che si è sentito si salva al più una volta all'ora; dopo
  `conoscenti_scadenza_giorni` (180) il conoscente si dimentica con le sue righe (le righe in
  memoria tornano «ignoto», `RegistroStanza.riscrivi_chi`).

Misura a secco (impronte finte): la prova copre la logica, non la somiglianza vera delle voci.
**Da misurare sulla DGX** prima di accenderlo: quanti gruppi per ospite vero (una voce spezzata in
due gruppi divide gli indizi), quante proposte confermate, quante voci simili finite nello stesso
gruppo. Prova: `prove/prova_stanza_conoscenti.py` (livello 1, ~3 s).

### 14/10 sera: il conoscente anche nei turni rivolti a Calliope (ramo `conoscenti-avvisi-2`)

Fino a qui il conoscente era riconosciuto solo nelle righe della stanza: quando parlava a Calliope
(turno col nome) era «un ospite, non riconosciuto dalla voce». Ora `Ciclo._conoscente_turno`
(chiamata da `_riconosci_voce`) riconosce la sua impronta anche nel turno, **solo come
etichetta**:

- **Quando**: la frase non vale nessun profilo della famiglia (né per la voce, né per la frase
  breve, la zona grigia nella conversazione, la continuità o il profilo più protetto), ha almeno
  `speaker_min_voice_s` di voce, il profilo della famiglia più vicino è **sotto la zona grigia**
  (`speaker_id_threshold − speaker_id_session_margin`: anche fuori conversazione, dove la frase
  vale comunque ospite, un familiare nella zona grigia vince sul conoscente) e
  `Conoscenti.riconosci` lo trova sopra soglia con `speaker_id_margine` dal secondo conoscente e
  dal familiare più vicino. Più stretta della stanza (`Stanza._chi`, dove la zona grigia di un
  familiare cede a un conoscente netto): qui la frase decide chi parla a Calliope.
- **Cosa cambia**: `SpeakerContext.conoscente` = {id, nome, nota} per una frase (azzerato in
  `_chi_parla`); nei dati del turno «persona: Marco Rossi (conoscente, collega di Carlo),
  riconosciuto dalla voce: non è della famiglia, è un ospite.» (`brain.conoscente_detto`), e
  nella conversazione anonima condivisa `_chi` «Marco Rossi (conoscente)»; la frase del turno
  entra nella stanza come riga «conoscente:<id>» con il nome, la nota e «→ Calliope» (su disco con
  la tenuta, come le sue righe della stanza) e apre la sua presenza.
- **Cosa non cambia**: `current_speaker` resta None, quindi livello **ospite**, nessuna azione di
  chi amministra, nessun dato della famiglia, nessuna ricerca nella stanza; `rec["voce"]["nome"]`
  resta None (un omonimo di casa non viene mai cercato fra i profili). *Storico (fino al 14/10
  sera)*: nel registro dei turni solo `voce.conoscente: true`, mai il nome né l'id, e in console
  «[VOCE] è un conoscente: resta ospite» senza il nome. Dal 14/10 sera (sotto) come un adulto.
- **Contrari nella prova** (`prova_turni_e_presenze`): la voce netta di Carlo, Carlo nella zona
  grigia fuori e dentro la sua conversazione, il conoscente a meno del margine da Bianca, la
  frase breve, una voce di nessuno, l'etichetta che vale una frase sola, senza stanza, e una
  conoscente omonima di Bianca di casa (resta conoscente; la voce di Bianca resta Bianca).

#### Più tardi, il 14/10 sera: conservato come un adulto (ramo `conoscenti-turni`)

Decisione di Dario (0030 punto 9, dettagli in [contesto-conversazione](contesto-conversazione.md)):
per la conservazione il conoscente vale come un adulto, i permessi restano da ospite. Per
quest'area: nel registro dei turni `voce` ha `conoscente: true`, il suo `id`, `nome_conoscente` e
il `modo`, con le parole; in console «[VOCE] Marco Rossi (conoscente): resta ospite». Una **frase
breve** (sotto `speaker_min_voice_s`) non riconosce un conoscente, ma nella finestra d'ascolto e
nella sua conversazione su quel satellite (`persona:<id>`) vale ancora lui
(`ciclo._conoscente_breve`, regola sull'audio `conoscente_breve`, `modo: breve`, nei dati del
turno «riconosciuto dalla conversazione»); la famiglia nella zona grigia vince anche qui. La riga
della stanza di quella frase ha sicurezza «grigia» (non va su disco con la tenuta). Prova:
`prove/prova_conoscenti_conserva.py`.

## L'ascolto apre la coda prima di azzerare la wake word (14/10 sera, ramo `giochi-pagina-stabile`)

Caso trovato dalle prove instabili (`prova_stanza_voce`, 6 giri su 12 caduti sotto carico): «Calliope»
detto subito all'apertura dell'ascolto non svegliava il satellite (punteggio 0,01–0,15) e la frase finiva
nella stanza. `Listener.listen` (`calliope/audio.py`) azzerava i rilevatori della wake word **prima** di
aprire la coda dei frame; il reset riscalda i modelli (~50 ms a riposo, oltre i 300 ms del pre-roll sotto
carico) e l'attacco della frase si perdeva. Ora la coda si apre prima e i rilevatori si azzerano dopo:
12 giri su 12 verdi con la CPU occupata. Vale anche per l'ascolto vero (satellite e locale): sul vero il
difetto poteva far perdere la prima sillaba del nome quando la macchina era carica. Caso nuovo in
`prove/prova_frase_lunga.py` (reset lento di 0,6 s), che cade col codice di prima.

## La fine del turno System 1: Smart Turn sull'audio, in ombra (14/10 sera, ramo `system1-fine-turno`)

Richiesta di Dario: modelli «System 1» piccoli e velocissimi per le scelte chiuse che pesano sulla
latenza, con il modello grande quando il piccolo è incerto; primo caso la fine del turno. Ricerca e
scelta in [`../ricerche/2026-10-14-system1-fine-turno.md`](../ricerche/2026-10-14-system1-fine-turno.md).

**Scelta: Smart Turn v3.2 di Pipecat** (BSD-2, encoder di Whisper Tiny + classificatore, ONNX int8
da 8,7 MB, 23 lingue con l'italiano: 94,5 % sul loro banco). Guarda gli ultimi 8 s di **audio** e
dà la probabilità che il turno sia finito; niente trascrizione parziale (sulla DGX costerebbe
~0,18 s, sul satellite non c'è Whisper). Il turn detector di LiveKit (testo, 396 MB) è escluso
dalla licenza (solo dentro LiveKit Agents). Nessuna dipendenza nuova: onnxruntime c'è, il log-mel
di Whisper è in numpy (uguale a quello di `transformers` e di faster-whisper). Si scarica dal
catalogo: `python -m calliope.stato --installa modello_fine_turno` (`models/fine_turno/`, fuori
da git, revisione fissa e SHA-256).

**Tre modi** (`fine_turno`, sezione audio; di serie **spenta**):
- **ombra**: il turno si chiude come sempre; il server rigioca ogni frase in un thread suo (VAD
  suo, sonda a `fine_turno_sonda_ms` = 250 ms di ogni pausa) e scrive in `ascolto.fine_turno`,
  solo numeri, cosa avrebbe deciso: «anticipo» con `risparmio_ms`, «taglio» (una pausa dentro la
  frase presa per la fine), «anticipo_ripresa» («finito» ma la persona ha ripreso: dato di
  `OsservaRipresa`), «taglio_evitato» e «attesa» con `costo_ms` (dove avrebbe aspettato di più),
  «come_prima». Riga in `calliope stato --turni`. Vale per tutti i canali, telefono compreso.
- **attiva**: nel `Listener` (in locale e sul satellite in Python che ha il modello; modo e soglie
  arrivano dal server con PARAMETRI) a 250 ms di silenzio la frase va al decisore senza fermare
  l'ascolto: «finito» con sicurezza ≥ `fine_turno_soglia` (0,9) chiude subito (chiusura
  «anticipata», nuova in `pause.CHIUSURE`), «non finito» ≥ `fine_turno_soglia_attesa` (0,8)
  aspetta fino a `fine_turno_attesa_max_ms` (1500 ms). Sotto `fine_turno_min_parlato_ms` (800 ms
  di voce) mai prima: il nome da solo con la pausa prima della domanda esce «finito» (0,92 con
  Piper). Costa l'anticipo sulle frasi brevi senza il nome («Che ore sono?» detta nella finestra
  d'ascolto, ~0,7 s di voce): la griglia dello script della DGX prova 0, 800 e 1200 ms. Incerto, lento (risposta dopo il silenzio fisso), guasto (spento dopo 5 errori di fila)
  o senza modello: silenzio fisso. Il satellite manda l'esito in `frase_finita.fine_turno`
  (controllato). Il telefono resta al silenzio fisso (domani con onnxruntime-web).
- Principio 10: non è una regola sul testo; decide sull'audio, che il modello della voce non vede,
  solo **quando** la frase va a Whisper. Di serie il silenzio fisso; un anticipo sbagliato in
  half-duplex perde il seguito, per questo soglia alta, parlato minimo e prima l'ombra.

**Misure sul portatile (frasi di Piper deterministiche).** Frasi complete «finito» 0,98–0,99; pause
di 400 ms dopo «e poi,» e «poi,» «non finito» (0,03 e 0,06). Le altre sospese («in», «e», un
numero, un elenco) Piper le pronuncia come frasi finite e il modello le prende per finite (0,92–0,99):
sono un limite della voce sintetica, non una misura del modello; la valutazione vera è sulla voce
conservata. `Listener` in «attiva» a tempo reale: «Accendi la luce in cucina.» chiusa dopo **320
ms** di silenzio invece di 700. Decisore: 31 ms con 2 thread di onnxruntime + 7 ms di log-mel sul
portatile (50 ms con un thread), p50 25–58 ms secondo il carico.

**Da fare (Dario).** Sulla DGX: il modello e lo script a secco sulle ~95 frasi conservate di chi
amministra (`prove/manuali/fine_turno_dgx.py`, comando in testa: accordo, griglia di soglie e
parlato minimo, ms del decisore, solo numeri); poi `fine_turno: ombra` nel file locale per almeno
una settimana. Criteri proposti per «attiva» su un satellite: tagli sotto l'1 % a soglia 0,9,
almeno metà delle frasi chiuse prima, decisore p90 sotto 100 ms sul satellite.

Prove: `prove/prova_fine_turno.py` (livello 2, a secco: decisore finto, frase completa, sospesa
con «e»/«in»/«poi», numeri dettati, elenco, ripresa dopo una pausa lunga, il nome da solo,
decisore guasto o lento → silenzio fisso, Listener in «attiva», protocollo, catalogo, ciclo) e
`prove/prova_fine_turno_voce.py` (livello 3: modello e Piper veri; si salta senza il modello).

## Passo 3 della stanza: la corsia lenta (14/10 sera, ramo `stanza-passo-3`)

Il passo 3 del [progetto](../ricerche/2026-10-13-conversazione-di-stanza.md) (§ 3.2, § 5.1, § 5.2,
§ 5.4, § 6 riga 3; decisione [0029](../decisioni/0029-conversazione-di-stanza.md)), dietro
**`stanza_lenta`** (di serie `false`). `calliope/stanza/lenta.py` (`Lenta`), caricata da
`stanza.load_lenta` in `main._guardia_stanza`. Registro, versioni, tenuta, storia, guardiano e
riassunto: [contesto-conversazione](contesto-conversazione.md). Qui l'audio.

- **L'audio resta in RAM** (`Stanza._trascrivi` → `Lenta.metti`, int16) al più `stanza_audio_min`
  (15 min, ~1,9 MB al minuto) per satellite, finché la corsia lenta non l'ha rivisto; poi si butta
  (decisione 0029 punto 1). Spenta, si butta a trascrizione fatta come prima.
- **Mai davanti ai turni né alla corsia veloce**: si parte solo a DGX libera (nessuna risposta,
  nessuna frase che aspetta Whisper, nessuno che parla a Calliope, coda della stanza vuota, da
  `stanza_lenta_libera_s`); Whisper con la precedenza **LENTA** (`stanza/coda.py`, dentro
  `STTCondiviso`), un segmento alla volta (≤ 20 s), e fra un segmento e l'altro si ricontrolla:
  un turno che arriva aspetta al più quel segmento.
- **Ritrascrizione**: lo stesso Whisper dei turni (con faster-whisper nel processo il beam
  `stanza_lenta_beam`, 8, invece di 5: `Transcriber.transcribe(…, beam=)`, il server lo ignora)
  oppure **un Whisper suo** (`stanza_lenta_stt_url`, `stanza_lenta_stt_modello`: per esempio un
  secondo whisper-server con large-v3 non turbo), che il piano propone solo se ci sta dopo tutto il
  resto e la macchina non è della taglia ridotta (`calliope stato --piano`, riga «Stanza lenta»:
  sulla DGX «large-v3, whisper.cpp (secondo server)» ~3,6 GB stimati; a 8 GB «lo stesso Whisper
  dei turni»). Il **prompt** con i nomi di chi parla nello scambio («Parlano Carlo e Nicola.») e la
  coda delle parole di prima (`stanza_lenta_prompt_caratteri`, 160) si accende di serie solo con
  un Whisper suo (`stanza_lenta_prompt: auto`): vedi le misure sotto.
- **Chi parla sullo scambio** (§ 3.2, § 5.1): finestre CAM++ da `stanza_lenta_finestra_s` (1,5 s)
  sovrapposte a metà, sotto il 30 % dell'energia mediana sono pause; ogni finestra contro i profili
  **e** la voce media di ciascuno nello scambio (dalle sue frasi riconosciute ancora in RAM: stesso
  canale), soglia `stanza_lenta_soglia_finestra` (0,40) con 0,05 di margine; una finestra isolata
  fra due uguali si assorbe, le file più corte di `stanza_lenta_parte_min_s` (2 s) vanno con la
  vicina. Due voci con file lunghe → il segmento **si spezza** (al più 3 parti): il testo della
  ritrascrizione intera diviso in proporzione al tempo, al confine di frase più vicino
  (`dividi_testo`; le parti ritrascritte da sole perdevano o ripetevano le parole ai tagli: banco
  qui sotto), e chi per parte con l'impronta della parte; voci che si alternano a pezzi corti o più
  di 3 file → una riga «più voci (Carlo, Nicola?)», sicurezza «nessuna». La riga intera si rivede
  con le voci dello scambio (una zona grigia diventa «voce» se somiglia alla voce della stessa
  persona nello scambio). Un conoscente o un gruppo della corsia veloce restano com'erano.
- **Allucinazioni** (§ 5.4, regola `allucinazione_lenta`): le famiglie di `allucinazioni.py`
  sulla ritrascrizione, la stessa parola o coppia quattro volte di fila, il rapporto di
  compressione oltre 2,4, la confidenza (avg_logprob < −1 e no_speech > 0,6) quando il server la
  dà; una riga corta (≤ 3 parole) vuota alla ritrascrizione è scartata, una lunga resta.
- **TV e radio** (§ 5.2, regola `tv_stanza`), solo su righe di voci non riconosciute, a punti:
  fila di ≥ 3 segmenti e ≥ 30 s di parlato senza persone di casa in mezzo e con pause ≤ 3 s (+1),
  per lo più chiusi dal tetto (+1), nessuna persona di casa sentita lì entro `stanza_presenza_s`
  (+1), la stessa frase di ≥ 6 parole già sentita da una voce sconosciuta nelle ultime 24 ore
  (+2), il `media_player` di Home Assistant acceso (+2) o spento (−1) con l'aggancio `media(sat)`
  (oggi nessuno collegato). Con 2 punti la riga è `tv`. Il classificatore audio (voce registrata,
  musica) **non** c'è: niente modello nuovo (principio 4); il giudizio sul contenuto col modello
  nemmeno.

**Banco sintetico** (portatile, RTX 5070, faster-whisper large-v3-turbo per i turni, 14/10 sera,
`prove/manuali/banco_stanza_lenta.py --sintetico --cache …`): 21 segmenti in 4 scambi di fantasia
con voci di Piper (Carlo giorgio, Bianca paola, Nicola riccardo; un ospite leonardo; TV miro e
aurora), impronte CAM++ vere da altre 5 frasi delle stesse voci, riverbero breve e rumore; lo
stesso audio per ogni riga della tabella (Piper non è deterministico: si salva la prima volta).

| Rumore | Corsia lenta | WER veloce | WER lenta | Whisper della lenta |
|---|---|---|---|---|
| 20 dB | turbo, senza prompt (`auto`) | 11,2 % | **9,7 %** | 7,7 s |
| 20 dB | turbo, col prompt | 11,2 % | 10,2 % | 7,8 s |
| 20 dB | large-v3, col prompt (`auto`) | 11,2 % | 10,2 % | 16–20 s |
| 20 dB | large-v3, senza prompt | 11,2 % | 9,7 % | 18,5 s |
| 10 dB | turbo, senza prompt (`auto`) | 19,4 % | 18,9 % | ~9 s |
| 10 dB | turbo, col prompt (nomi, o nomi e parole di prima) | 19,4 % | 21,9 % | ~9 s |
| 10 dB | large-v3, col prompt (`auto`) | 19,4 % | **16,8 %** | ~19 s |
| 10 dB | large-v3, senza prompt | 19,4 % | 18,4 % | ~19 s |

Chi parla: una voce giusta 10/14 veloce → 11/14 lenta a 20 dB (10/14 a 10 dB); i tre blocchi con due
voci spezzati 3/3 a 20 dB e 2/3 a 10 dB (le voci giuste in 1 su 3: la voce di riccardo x_low nelle
finestre corte resta «ignota»); TV 4/4 prese, **persone prese come TV 0/17**; CAM++ ~3–5 s per 21 segmenti sulla CPU. Un
limite che il banco mostra e la corsia lenta non corregge: l'ospite (leonardo) è riconosciuto come
Nicola (riccardo) sopra soglia già dalla corsia veloce (voci di Piper maschili vicine per CAM++).
**Lettura**: col Whisper dei turni la corsia lenta guadagna poco (beam più largo) e il prompt
peggiora sull'audio rumoroso; con un modello più accurato il prompt aiuta. Da qui `auto`. Il set è
piccolo (196 parole senza la TV): i numeri veri li darà la DGX.

**Sulla DGX** (da fare al 14/10 pomeriggio; *fatto la sera, misura qui sotto*): `prove/manuali/ritrascrivi_conservati.py`
ritrascrive come la corsia lenta le registrazioni conservate (voce degli adulti col consenso, 95 di
chi amministra al 14/10) e scrive in `privato/` i soli casi diversi da segnare (originale / lenta /
scelta): è il primo riferimento vero per la WER (`banco_stanza_lenta.py --conservati`). Poi, con
l'eccezione dell'audio del banco accesa per 7 giorni, `banco_stanza_lenta.py --banco` sui segmenti
veri della stanza (riferimento scritto a mano in `riferimento.tsv`). Registrazioni dedicate di
adulti che lo sanno, quando ci saranno: `--cartella privato/banco-stanza` (formato nel file).

### La misura vera sulla DGX e la ritrascrizione solo se serve (14/10 sera, ramo `stanza-lenta-2`)

**La misura** (14/10 sera, `ritrascrivi_conservati.py` sulla DGX, poi la revisione a mano di chi
amministra): le **95 registrazioni conservate** di chi amministra, ritrascritte come faceva la
corsia lenta accesa sulla DGX (lo stesso whisper-server dei turni, large-v3-turbo, che **ignora il
beam**, e senza il prompt dei turni perché `stanza_lenta_prompt: auto` lo spegne col Whisper dei
turni). 56 uguali, 39 diverse; per ognuna delle 39 chi amministra ha scelto l'originale, la lenta o
ha scritto la frase giusta (il JSON delle scelte resta fuori dal repository, come i testi).

| Conto | Whisper dei turni (originale) | Corsia lenta | Casi vinti |
|---|---|---|---|
| Set intero, 95 (le uguali giuste) | **3,0 %** | 4,8 % | — |
| Le sole 39 diverse | **4,5 %** | 7,1 % | originale 24, lenta 12, pari 3 |

(Il conto di `banco_stanza_lenta.py --conservati … --scelte …`, con la sua normalizzazione delle
parole: 2,86 % contro 4,70 % sul set, 4,23 % contro 6,94 % sulle diverse, gli stessi 24/12/3.)

**Lettura**: senza un Whisper diverso la ritrascrizione **peggiora** le righe: è lo stesso modello
con meno contesto (niente «Conversazione con Calliope.»), e il beam più largo non arriva al server.
Il banco sintetico del portatile (sopra) lo faceva vedere appena (faster-whisper rispetta il beam);
il vero lo dice chiaro.

**L'interruttore** `stanza_lenta_ritrascrivi: auto | si | no` (`calliope/stanza/lenta.py`,
`Lenta.ritrascrive`, `whisper_proprio`, `beam_effettivo`): con **auto** (di serie) la
ritrascrizione si fa solo se la corsia lenta ha un Whisper suo (`stanza_lenta_stt_url`) o un beam
che conta (faster-whisper nel processo, `device` cuda o cpu, con `stanza_lenta_beam` più largo di
`whisper_beam_size`; un server o un trascrittore che non dice il dispositivo: no). Senza
ritrascrizione la corsia lenta fa tutto il resto sul **testo della corsia veloce**: chi parla sullo
scambio (zona grigia corretta, blocchi con due voci spezzati sul testo v1, «più voci»), TV,
allucinazioni (ripetizione e compressione sul testo v1), riassunto. Una **versione 2 nasce solo da
un cambio vero** (attribuzione, TV, allucinazione); il resto è l'evento «uguale». Se il Whisper suo
è giù, con `auto` il segmento resta col testo v1 (prima ripiegava su quello dei turni, cioè sul
caso misurato peggiore); con `si` detto a mano ripiega come prima. Misure: `ritrascritto` (false
senza), «senza ritrascrizione N» nella riga di `calliope stato --turni`, nessun tempo di Whisper per
quei segmenti. Il «no» di YAML (false) è accettato. Prova `prova_stanza_lenta.py` (con i contrari:
lo stesso beam dei turni non conta, «no» vince sul Whisper suo).

**Il secondo Whisper**, preparato e **non acceso** (`setup/linux/motore/whisper-lento.sh`, unità
`calliope-whisper-lento`, porta 8004, `calliope motore whisper-lento …`): lo stesso
`whisper-server` compilato per i turni, con **large-v3 non turbo**. La scelta del modello, con la
memoria della DGX del 14/10 (liberi ~21 GB su 119: vLLM 47,8, Ollama 26B 15, e4b 3,1, llama-guard
5,3, Whisper turbo 2,1; FLUX a richiesta 13):

| Variante | File | Memoria (stima) | Margine con FLUX acceso |
|---|---|---|---|
| **large-v3 q5_0** (scelta) | 1,08 GB | ~2,0 GB | ~6 GB |
| large-v3 f16 | 3,1 GB | ~3,9 GB (README di whisper.cpp) | ~4 GB |
| large-v3 q8_0 | — | — | non c'è nel repository ufficiale di whisper.cpp |

La stima di q5_0: i pesi più il calcolo e le cache del beam (~0,9 GB: il turbo misura 2,1 GB con
1,6 di pesi, ma ha 4 strati di decoder invece di 32). La quantizzazione q5_0 di Whisper large
perde poco (da verificare sul banco qui sotto: se perde, `VARIANTE=f16`). **Residente** e non
avviato e fermato a DGX libera: 2 GB non valgono un caricamento a ogni passo e una gara con FLUX
per la stessa memoria; `whisper-lento.sh ferma` resta a mano se servisse. Il piano dei modelli
(`calliope stato --piano`, riga «Stanza lenta») lo propone solo se resta il posto per FLUX, con la
**memoria vera** del processo quando gira (nvidia-smi per processo, dal PID dell'unità:
`macchina._whisper_lento`); senza posto e col whisper-server dei turni dice «senza
ritrascrizione». Catalogo: `modelli.WHISPER["cpp-lenta"]` (e `cpp-lenta-f16`).

**Il banco per decidere** (`banco_stanza_lenta.py --conservati FILE.md --scelte FILE.json
--ritrascrivi`, sulla DGX): le 95 registrazioni (fino all'ora nel nome del file; riferimento la
scelta per le 39 diverse, l'originale per le 56 uguali) ritrascritte da `turni` (col suo prompt),
`turni_senza_prompt` (deve rifare la misura di sopra), `lento_senza_prompt`, `lento_nomi`,
`lento_nomi_parole`, `lento_prompt_turni`; stampa solo numeri (WER sul set e sulle diverse, casi
vinti/persi/pari contro `turni`, tempo mediano). **Obiettivo per riaccendere la ritrascrizione**:
un `lento*` con la WER sotto quella di `turni`; allora `stanza_lenta_stt_url` nel locale (e, se
vince senza prompt, `stanza_lenta_prompt: no`). Comandi in [setup-dgx](setup-dgx.md).
