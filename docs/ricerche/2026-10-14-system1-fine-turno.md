# System 1: la fine del turno decisa da un modello piccolo (14/10/2026)

*Richiesta di Dario (14/10 sera): modelli «System 1» piccoli e velocissimi per le decisioni chiuse
che pesano sulla latenza, con il modello grande («System 2») quando il piccolo è incerto. Primo
caso: **hai finito di parlare?** Ramo `system1-fine-turno`. Codice: `calliope/system1/`.*

## 1. Il problema

Oggi la frase si chiude dopo `silence_ms` = 700 ms di silenzio, uguale per tutti
(`audio.Listener.listen`, il satellite in Python con gli stessi parametri, il telefono in
`voce.js`). Dal 07/10 le pause e i tagli si misurano (`calliope/pause.py`, docs/aree/stt-tts.md,
«Pause e fine del turno»): chi parla svelto aspetta 700 ms per niente a ogni frase, chi fa pause
lunghe (un bambino, chi detta un numero, «accendi la luce in… cucina») viene tagliato. La fase 2
già scritta lì, la «partenza anticipata», stimava ~400 ms di latenza sentita in meno.

Un silenzio fisso non sa distinguere «Che ore sono?» seguito dal silenzio da «Ricordami di
comprare il latte, e poi…» seguito da una pausa di respiro. Un modello piccolo che sente
l'intonazione e la forma del discorso sì: è quello che fanno da un anno i sistemi vocali in
tempo reale («semantic VAD», «turn detection»).

## 2. I candidati (ottobre 2026)

Fonti verificate il 14/10 dove è scritto; il resto è dalla mia conoscenza (fino a metà 2026) ed
è segnato **[c]**, da verificare prima di usarlo.

| | Smart Turn v3.2 (Pipecat) | Turn detector di LiveKit (multilingue) | Classificatore piccolo addestrato da noi (MiniLM, Ettin, ModernBERT) | VAP (voice activity projection) |
|---|---|---|---|---|
| Ingresso | **audio** (ultimi 8 s, 16 kHz) | testo (la trascrizione fin lì e la storia) | testo | audio, a due canali (le due persone) |
| Italiano | **sì** (23 lingue; italiano 94,5 % di accuratezza, falsi «finito» 3,6 % a 0,5 sul loro banco v3.2) | sì (14 lingue) | da addestrare: nessun insieme italiano pronto | no: addestrato su Switchboard (inglese) e su dati giapponesi **[c]** |
| Dimensione | ~8 M parametri (encoder di Whisper Tiny + classificatore), ONNX int8 **8,7 MB** | Qwen2.5-0.5B distillato, **396 MB**, ~400 MB di RAM | 15–150 M parametri, 30–300 MB **[c]** | ~20 M, PyTorch con encoder CPC **[c]** |
| Latenza su CPU | 10–65 ms dichiarati; **misurati qui**: 31 ms con 2 thread (50 con 1, 22 con 4) + 7 ms di log-mel, portatile carico; 25 ms sul banco a secco | 50–160 ms (documentazione), ~25 ms (pacchetto) | 5–30 ms **[c]**, ma prima serve la trascrizione parziale | continua, a ogni frame **[c]** |
| Licenza | **BSD-2-Clause** (codice, pesi e dati) | pesi con la «LiveKit Model License»: **solo dentro il framework LiveKit Agents**, vietato l'uso a sé | MIT / Apache-2.0 per i modelli base **[c]** | codice di ricerca **[c]** |
| ONNX | sì, file pronti (CPU int8, GPU fp32) | sì (dentro il plugin) | esportabile | no, pronto solo in PyTorch **[c]** |
| ARM (principio 4) | solo onnxruntime e numpy, già di base: wheel di onnxruntime 1.30.0 per win_amd64, **win_arm64**, manylinux aarch64 (onnxruntime-gpu 1.30.0 per manylinux aarch64 sulla DGX) verificati su PyPI il 14/10; il log-mel in numpy (niente `transformers`) | onnxruntime + tokenizer di HF | onnxruntime + tokenizer | PyTorch |
| Dove girerebbe | DGX (ombra, per ogni frase), satellite (attiva, dove c'è il VAD che chiude), telefono domani con onnxruntime-web (c'è già per la wake word) | DGX, dopo una trascrizione parziale | DGX | — |

Altri, solo per completezza: il turn detector di **TEN** (Qwen2.5-7B, troppo grande per una
decisione da millisecondi) **[c]**; **Namo** (VideoSDK, classificatori di testo multilingui) **[c]**;
un rilevatore di turno di Scicom su Qwen3-4B (Apache-2.0, marzo 2026, centri di chiamata: troppo
grande); Krisp (chiuso). Nessuno cambia la scelta.

**Il costo nascosto dei modelli di testo**: per decidere a 250 ms di silenzio serve il testo della
frase fin lì, cioè una trascrizione parziale. whisper.cpp sulla DGX fa ~0,18 s di mediana per una
frase breve: si mangerebbe metà del guadagno, e sul satellite non c'è Whisper. Inoltre la
trascrizione non ha l'intonazione: «accendi la luce in cucina» e «accendi la luce in» differiscono
di una parola, mentre la voce che resta su o scende lo dice subito.

## 3. La scelta: Smart Turn v3.2 per CPU, sull'audio

- È l'unico con l'italiano, piccolo abbastanza per un satellite, licenza libera e file ONNX pronti.
- Lavora sull'audio che il VAD ha già: nessuna trascrizione in più, gira sul satellite dove si
  chiude la frase, oppure sulla DGX in ombra per tutti i canali.
- Nessuna dipendenza nuova: onnxruntime c'è (wake word, CAM++, Piper, Silero), il log-mel di
  Whisper è scritto in numpy (`fine_turno.log_mel`) e coincide con
  `transformers.WhisperFeatureExtractor(chunk_length=8, do_normalize=True)` (differenza massima
  1e-5 su tre segnali, controllata il 14/10 in un ambiente a parte) e con quello di faster-whisper
  (nella prova a secco).
- File: `smart-turn-v3.2-cpu.onnx` di `pipecat-ai/smart-turn-v3` alla revisione
  `f766f81d3cfdf7737ac64aad813d91bbfd56bf93` (07/01/2026), 8 679 182 byte, SHA-256
  `2bb02631…967e4f`; si scarica dal catalogo (`python -m calliope.stato --installa
  modello_fine_turno`), in `models/fine_turno/`, fuori da git.

La versione v3.2 è la stessa architettura della v3.0–3.1 con più dati e una quantizzazione
migliore: si cambia solo il file.

## 4. Principio 10

Il principio 10 ammette una regola sul testo solo in casi ristretti, e lascia il significato al
modello. Qui **non c'è testo**: il decisore guarda l'audio (prosodia, ritmo, respiro), cioè ciò
che il modello della voce non vede, e decide soltanto **quando** la frase va a Whisper, mai cosa
vuol dire. È la stessa famiglia della wake word acustica e del tetto della frase (regola
`frase_tetto`, 10/10). In più:

- di serie resta il silenzio fisso; l'anticipo vale solo sopra una soglia alta (0,9) e mai per una
  frase cortissima (sotto 800 ms di voce: il nome da solo); l'attesa più lunga ha un tetto
  (1500 ms);
- incerto, lento, guasto o senza modello: il silenzio fisso, sempre;
- in «attiva» la chiusura si scrive nel registro (`ascolto.chiusura` «anticipata» e
  `ascolto.fine_turno`), come il nome di una regola.

Un errore non è reversibile come una regola sul testo: in half-duplex la parte detta dopo una
chiusura sbagliata si perde (resta la misura della ripresa). Per questo si comincia in ombra.

## 5. Come è fatto (14/10)

- `calliope/system1/__init__.py`: l'interfaccia comune `decide(dati) -> Decisione(scelta,
  sicurezza, ms)` e `Sorvegliato` (un thread suo; lento o ancora occupato → None, guasto → None
  e spento dopo 5 errori di fila). Ogni decisore futuro usa la stessa forma (principio 2).
- `calliope/system1/fine_turno.py`: `SmartTurn`, `Politica` (sonda, soglie, tetto, parlato
  minimo), `Anticipo` (attiva, nel `Listener`), `OmbraFineTurno` (ombra, sul server), `simula`,
  `esito`, `riassunto`.
- **Ombra**: dopo ogni frase il server la rigioca in un thread suo, con un Silero VAD suo e la
  stessa regola del silenzio di `listen`; a 250 ms di ogni pausa chiede al decisore. Le pause
  **interne** sono quelle dopo cui la persona ha continuato (un «finito» lì è un **taglio** che
  avrebbe fatto); la **chiusura** si confronta con la ripresa misurata da `OsservaRipresa` (dal
  07/10). Nel registro, solo numeri: `ascolto.fine_turno` = esito («anticipo» con `risparmio_ms`,
  «taglio», «anticipo_ripresa», «taglio_evitato», «attesa» con `costo_ms`, «come_prima»,
  «nessuna», «in_ritardo»), probabilità alla chiusura, sonde, ms del decisore. Riga nuova in
  `calliope stato --turni`. Vale per ogni canale (anche telefono e satelliti), perché il server ha
  l'audio di tutti.
- **Attiva**: nel `Listener` (in locale e sul satellite in Python che ha il modello) a 250 ms di
  silenzio la frase va al decisore in un altro thread, senza fermare l'ascolto: «finito» ≥ 0,9
  chiude subito (chiusura «anticipata»), «non finito» ≥ 0,8 sposta la soglia a 1500 ms; la voce
  che riprende annulla la domanda. Il satellite riceve modo e soglie dal server (PARAMETRI) e
  manda l'esito in `frase_finita.fine_turno` (controllato da `campi_esito`). Il telefono resta al
  silenzio fisso: si potrà fare con onnxruntime-web, ma `schermi/` non si toccava in questo ramo.
- Configurazione (sezione audio): `fine_turno` (spenta|ombra|attiva, di serie spenta),
  `fine_turno_modello`, `fine_turno_sonda_ms` 250, `fine_turno_soglia` 0,9,
  `fine_turno_soglia_attesa` 0,8, `fine_turno_attesa_max_ms` 1500, `fine_turno_min_parlato_ms`
  800.

## 6. Prime misure sul portatile (frasi di Piper, 14/10)

Voce `it_IT-riccardo-x_low` deterministica, un filo di rumore, Silero in ONNX, sonda a 250 ms.

| Frase | Pausa interna (p «finito») | Chiusura (p) |
|---|---|---|
| «Accendi la luce in cucina.» / «Che ore sono?» / «Metti il pane nella lista.» | — | 0,98–0,99 |
| «Ricordami di comprare il latte, e poi, … il pane.» (400 ms) | **0,03** | 0,77 |
| «Spegni tutto, poi, … accendi la radio.» (400 ms) | **0,06** | 0,99 |
| «Accendi la luce in … cucina.» | 0,98 | 0,97 |
| «Il numero è tre quattro sette, … due nove uno.» | 0,95 | 0,61 |
| «Metti nella lista pane, latte, … uova e biscotti.» | 0,99 | 0,99 |
| «Calliope, … che ore sono?» | 0,92 | 0,92 |

- Le frasi complete sono «finito» sicure; le pause dopo «e poi,» e «poi,» (dove Piper fa salire
  la voce) sono «non finito» sicure.
- **Le altre sospese non dicono niente sul modello**: Piper sintetizza ogni pezzo come una frase
  finita (l'intonazione scende anche su «accendi la luce in»), e il modello giustamente sente una
  fine. Una persona vera che si ferma a metà tiene la voce su, o dice «ehm». La valutazione vera
  è sulla voce conservata (sotto).
- Il nome da solo con una pausa esce «finito» (0,92): da qui il parlato minimo di 800 ms, sotto
  cui non si chiude mai prima. Il prezzo: «Che ore sono?» detta da sola nella finestra d'ascolto
  (~0,7 s di voce, «finito» 0,98) resta al silenzio fisso; «Calliope, che ore sono?» d'un fiato si
  chiude prima. La griglia della DGX dice quanto costa (0, 800, 1200 ms).
- `Listener` in «attiva» con microfono a tempo reale: «Accendi la luce in cucina.» chiusa dopo
  **320 ms** di silenzio invece di 700 (decisore 62 ms): ~380 ms in meno sulla latenza sentita.
- Decisore sul portatile (CPU sotto carico di altri agenti): p50 58 ms nell'ombra (un thread per
  la simulazione + 2 di onnxruntime), 25 ms a portatile più libero.

## 7. Valutazione sulla DGX (da lanciare)

`prove/manuali/fine_turno_dgx.py` rigioca le frasi conservate (decisione 0028: voce dei soli adulti
riconosciuti che hanno detto sì; ~95 registrazioni di chi amministra al 14/10) e stampa, solo
numeri: accordo a 0,5 per canale (pause interne «non finito», chiusure senza ripresa «finito»,
riprese «non finito»), una griglia di soglie (0,5–0,98) e parlato minimo (0, 800, 1200 ms) con
frasi chiuse prima, secondi risparmiati, tagli, attese più lunghe e tagli evitati, e i ms del
decisore sulla CPU della DGX. Comando in testa al file. **Criteri per accendere «attiva»**
(proposta): tagli (interni + «finito» con ripresa) sotto l'1 % delle frasi a soglia 0,9, almeno
metà delle frasi chiuse prima, decisore p90 sotto 100 ms sul satellite.

## 8. Il piano

1. Installare il modello sulla DGX e lanciare lo script (sopra).
2. `fine_turno: ombra` nel file locale della DGX per almeno una settimana: `calliope stato
   --turni` dà la riga della fine del turno su tutti i canali, telefono compreso.
3. Scegliere soglie e parlato minimo dai numeri; accendere «attiva» su un satellite solo (lo
   studio), con il modello installato lì.
4. Il telefono con onnxruntime-web (stesso file ONNX, log-mel in JavaScript) se l'attiva regge.
5. Più avanti la soglia per persona e fascia (fase 1 delle pause) si combina con questa: il
   silenzio fisso da cui si parte è quello della persona.

## 9. System 1: i casi successivi

Tutti con la stessa interfaccia (`decide → scelta, sicurezza`) e la stessa regola: si decide da
soli solo sopra una soglia alta, altrimenti decide chi decideva prima.

- **Comandi semplici con FunctionGemma** (Gemma 3 270M per le chiamate di funzione **[c]**): «accendi
  la luce in cucina», «che ore sono», «metti il timer a 10 minuti» senza il modello grande; il
  modello grande quando il piccolo è incerto o il comando non è nell'elenco chiuso.
- **Preselezione dei tool**: un classificatore piccolo sceglie i 5–10 tool probabili tra i 78, il
  modello della voce vede solo quelli (prompt più corto, prima frase prima); misura già pronta in
  `scelta_tool.py`. *[Storico; 15/10: fatta con due insiemi stabili e misurata sulla DGX, non
  conviene (richiamo 84 %, +0,4–0,5 s a ogni cambio d'insieme:
  [`2026-10-15-preselezione-tool.md`](2026-10-15-preselezione-tool.md), § 7); 16/10 (issue #25):
  ombra tolta dal ciclo, resta il decisore come misura.]*
- **Giudizio «rivolta a Calliope?»** (`rivolta.py`, oggi in ombra con il modello della voce): un
  classificatore piccolo sul testo e sulla voce, il grande solo nella zona grigia.
- **Primo filtro di pericolo** per i minori: un classificatore piccolo davanti al guardiano (oggi
  un LLM), che fa passare al guardiano solo le frasi dubbie; mai «sicuro» da solo sotto soglia.

## Fonti

- Repository di Smart Turn (Pipecat): https://github.com/pipecat-ai/smart-turn (v3.2, BSD-2, 23
  lingue, `inference.py`, `audio_utils.py`), letto il 14/10.
- Modello e banco: https://huggingface.co/pipecat-ai/smart-turn-v3 (file, revisione, banco
  `benchmarks/smart-turn-v3.2-cpu.md` del 07/01/2026: italiano 94,50 %, FPR 3,58 %).
- Annuncio della v3 (CPU in 12 ms): https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/
- Annuncio della v3.1: https://www.daily.co/blog/improved-accuracy-in-smart-turn-v3-1/
- Turn detector di LiveKit: https://docs.livekit.io/agents/logic/turns/turn-detector e licenza
  https://huggingface.co/livekit/turn-detector/blob/main/LICENSE («can only use them together with
  the LiveKit Agents framework»).
- Pacchetto del plugin: https://simple-repository.app.cern.ch/project/livekit-plugins-turn-detector
- Rilevatore di Scicom su Qwen3-4B: https://featherless.ai/models/Scicom-intl/turn-detector-Qwen3-4B
- onnxruntime 1.30.0 e onnxruntime-gpu 1.30.0 su PyPI (JSON), 14/10.
