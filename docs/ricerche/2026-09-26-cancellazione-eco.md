# Cancellazione dell'eco software per il barge-in («livello B»)

*26 settembre 2026. Prova di fattibilità: non modifica Calliope. Script in `docs/ricerche/banchi/aec/` e
`prove/prova_aec.py`; dati generati in `docs/ricerche/banchi/aec/dati/`, ignorati da git.*

## In breve

- **Conviene, ma solo per decidere se l'utente ha parlato.** Non serve a ripulire
  l'audio per Whisper. Con un AEC buono i falsi barge-in sulla voce di Calliope passano
  da **~11 al minuto a 0–0,7** e la voce dell'utente viene rilevata 30 volte su 30 in
  0,28 s. La trascrizione invece peggiora: la frase detta sopra Calliope va trascritta
  dall'audio **grezzo**, dopo aver fermato la voce. Nella condizione realistica
  (Calliope si ferma 0,4 s dopo l'inizio della voce) la WER è del 18 % sul grezzo,
  27 % dopo DTLN e 48 % dopo AEC3.
- **Motore consigliato: DTLN-aec 512 (rete neurale, MIT) con il riferimento allineato
  da GCC-PHAT.** È l'unico motore rimasto a 0 falsi al minuto e 30/30 rilevazioni in
  tutte le condizioni tranne quella a volume molto alto. Sull'eco vera toglie 44–47 dB.
  Costa 2,3 ms di CPU ogni 10 ms di audio, cioè ~23 % di un core. Va convertito in ONNX
  prima di andare su ARM.
- **Seconda scelta: WebRTC AEC3 tramite `livekit`.** Si installa con pip, non chiede di
  stimare il ritardo e costa quasi nulla (0,05 ms ogni 10 ms). Però durante il doppio
  parlato sopprime la voce: la rileva più tardi (0,4 s) e, con l'eco forte, ne perde un
  terzo. Inoltre **non ha wheel per Windows ARM**.
- **Da scartare:** speexdsp (solo 17–19 dB, falsi quasi come senza AEC) e i binding
  Python di WebRTC fermi o non installabili.
- **Scoperta sulla misura reale:** il C920 non era collegato, quindi ho usato i
  microfoni del portatile. Con il microfono interno aperto in MME, come fa Calliope,
  **Windows cancella già l'eco** (elaborazione di piattaforma Realtek/Intel SST): la voce
  di Calliope arriva al livello del rumore e il VAD non scatta. Lo stesso microfono
  aperto «grezzo» (WDM-KS) sente l'eco a −20 dBFS, forte quanto una voce, con un ritardo
  di **294–298 ms** dal `write()`.
- **Stima dell'integrazione: 4–6 giorni**, in parte in comune con il livello A
  (interruzione di `Speaker` e `Brain`).

## 1. Librerie disponibili (verificate il 26/09/2026)

Installate davvero in un venv separato (`docs\ricerche\banchi\aec\.venv`, Python 3.14.6, Windows x64).

| Libreria | Motore | Ultima versione | Licenza | Wheel win x64 | Wheel win_arm64 | Py 3.14 | API | Esito |
|---|---|---|---|---|---|---|---|---|
| **livekit 1.1.20** (`rtc.AudioProcessingModule`) | WebRTC AEC3 + NS/AGC/HPF | 23/09/2026, molto attiva | Apache-2.0 (libwebrtc BSD) | sì (`py3-none-win_amd64`) | **no** (solo linux aarch64 e macOS arm64) | sì | `process_reverse_stream(frame)` (riferimento) e `process_stream(frame)` (microfono, modificato sul posto), blocchi da 10 ms, `set_stream_delay_ms()` facoltativo | **Funziona**. All'uscita stampa un `AssertionError` innocuo nel distruttore FFI |
| **pyaec 1.0.1** (binding di `aec-rs`) | speexdsp (MDF + preprocessore) | 12/2024 | MIT (speexdsp BSD) | sì | **sì** | sì (ctypes, `py3-none`) | `Aec(frame, filter_len, sr, preprocess)`, `cancel_echo(mic, ref)` | Funziona, ma è debole (vedi misure) |
| DTLN-aec (breizhn) | rete LSTM, 2 stadi, modelli 128/256/512 | repository fermo dal 2022 | MIT | modelli TF-Lite: servono `ai-edge-litert 2.2.0` (wheel cp314 win_amd64) oppure la conversione in ONNX | LiteRT no; **onnxruntime 1.30 sì** (cp311–cp314 win_arm64), dopo la conversione | sì con LiteRT | finestra 512, passo 128 (8 ms); ingressi: modulo dello spettro del microfono e del riferimento, più il riferimento nel tempo | **Funziona con LiteRT**. `tflite2onnx` fallisce (operatore SQUARE non supportato); `tf2onnx` richiede TensorFlow, che non ha wheel per Python 3.14 (serve un venv 3.13 una tantum) |
| speexdsp 0.1.1 | speexdsp | 2018 | BSD | no (solo sorgenti) | no | **non compila** (servono SWIG e libspeexdsp) | — | Scartata (pyaec usa lo stesso motore) |
| webrtc-audio-processing 0.1.3 | WebRTC AEC vecchio (non AEC3) | 2019 | BSD | no (solo armv7 Linux) | no | **non compila** | — | Scartata, abbandonata |
| aec-audio-processing 1.0.1 | WebRTC APM | 09/2025 | BSD-3 | solo cp311–cp313 | no | **non compila** (servono SWIG e meson) | `AudioProcessor.process_stream` / `process_reverse_stream` | Da riconsiderare solo se esce il wheel cp314 |
| webrtc-apm 0.1.6 | WebRTC APM | 10/2025 | MIT (dichiarata) | solo cp311 | no | no | — | Scartata. La homepage è un segnaposto (`github.com/youruser/…`) |

Latenza algoritmica: AEC3 e speex lavorano a blocchi da 10 ms senza ritardo aggiuntivo
apprezzabile. DTLN ha finestra di 32 ms e passo di 8 ms, cioè **24 ms** di ritardo.

## 2. Misura offline con eco simulata

### Come

`docs/ricerche/banchi/aec/simula.py` costruisce per ogni condizione una linea temporale continua di ~8,8
minuti a 16 kHz. Contiene 30 frasi vere dell'utente (C920, da `registrazioni/`, con i
riferimenti «sicuri» di `prove/riferimenti_whisper.tsv`) e 10 risposte di Calliope
sintetizzate da Piper (`it_IT-serena-high`, 22050 Hz). Per ogni frase ci sono tre
segmenti:

- **eco**: Calliope parla e l'utente tace;
- **doppio**: l'utente parla sopra Calliope;
- **utente**: l'utente parla da solo.

Il percorso dell'eco comprende:

- deriva di clock (ricampionamento a 22050·(1+ppm) → 16000);
- saturazione `tanh` dell'altoparlantino;
- passa-alto a 200 Hz;
- risposta all'impulso sintetica (percorso diretto, prime riflessioni, coda esponenziale);
- ritardo, con salti per il Bluetooth;
- rumore a −62 dBFS.

All'AEC arriva invece il ricampionamento esatto 22050 → 16000 di ciò che è stato
riprodotto, come in un'integrazione vera. Il flusso è continuo e lo stato dell'AEC resta
tra un segmento e l'altro. Il primo segmento misura l'avvio a freddo.

| Condizione | Ritardo | Deriva | Eco rispetto alla voce | Altro |
|---|---|---|---|---|
| cassa | 300 ms (misurato) | 30 ppm | 0 dB | RT60 0,35 s |
| forte | 300 ms | 30 ppm | **+10 dB**, saturazione forte | RT60 0,45 s |
| bluetooth | 250 ms | 50 ppm | 0 dB | salti di +40 ms e −25 ms del buffer |
| cassa-stop, forte-stop | come sopra | | | nel doppio parlato Calliope **smette di parlare 0,4 s dopo** l'inizio della voce, come con un barge-in vero |

Le metriche, calcolate da `docs/ricerche/banchi/aec/valuta.py` con il .venv principale:

- **ERLE** sui segmenti di sola eco: primo segmento / mediana / 10° percentile.
- **Falsi barge-in al minuto** di voce di Calliope: frasi che `Listener` restituirebbe
  (Silero, soglia 0,5, minimo 250 ms). Tra parentesi la stessa misura con un minimo
  di 500 ms.
- **Doppio parlato**: utente rilevato, falsi scatti *prima* che l'utente parli,
  latenza mediana del rilevamento.
- **WER** di Whisper large-v3-turbo, con i parametri di `Transcriber`, sulla finestra
  della frase dell'utente. Sulle stesse 30 frasi pulite la WER è **13,7 %**.

«+allin» vuol dire riferimento ritardato della stima GCC-PHAT (sui primi 20 s) meno
30 ms di margine. Senza margine AEC3 perdeva 20 dB sull'eco vera, perché il filtro
diventava non causale.

### Risultati principali

Condizione **cassa** (quella di tutti i giorni con l'altoparlante):

| Motore | ERLE 1°/med/p10 (dB) | Falsi/min (≥500 ms) | Doppio: rilevati, anticipati, latenza | WER doppio | WER utente solo | CPU ms/10 ms |
|---|---|---|---|---|---|---|
| nessuno | 0/0/0 | 10,9 (10,9) | 30/30, **30 anticipati** | 42 % | 11 % | — |
| speex (filtro 512 ms) | 3/17/12 | 7,3 (6,2) | 30/30, 18, 0,28 s | 31 % | 14 % | 0,35 |
| speex+allin (200 ms) | 7/19/16 | 10,6 (8,4) | 30/30, 24 | 29 % | 10 % | 0,20 |
| AEC3 | 20/39/28 | **0,0** | 27/30, 0, 0,40 s | 73 % | 14 % | **0,05** |
| AEC3+NS | 20/42/28 | 0,4 | 26/30, 0, 0,41 s | 74 % | 18 % | 0,05 |
| AEC3+allin | 27/39/34 | 0,4 (0,0) | 29/30, 0, 0,41 s | 77 % | 13 % | 0,05 |
| DTLN 512 senza allineamento | 3/2/0 | 10,9 | 30/30, 30 | 33 % | 14 % | 2,3 |
| DTLN 128+allin | 42/34/29 | 3,3 (1,1) | 30/30, 1, 0,28 s | 42 % | 14 % | 0,23 |
| DTLN 256+allin | 40/34/29 | 0,7 | 30/30, 2, 0,28 s | 32 % | 16 % | 0,52 |
| **DTLN 512+allin** | **50/42/36** | **0,0** | **30/30, 0, 0,28 s** | 31 % | 15 % | 2,3 |

Le condizioni difficili per i due motori migliori, più il riferimento senza AEC:

| Condizione | Motore | ERLE med/p10 | Falsi/min (≥500) | Rilevati, anticipati, latenza | WER doppio |
|---|---|---|---|---|---|
| forte | nessuno | 0/0 | 10,9 | 30/30, 30 | 403 % (trascrive Calliope) |
| forte | AEC3 | 33/26 | 2,6 (1,5) | **19/30**, 1, **1,15 s** | 81 % |
| forte | DTLN 512+allin | 41/33 | 0,7 (0,4) | 30/30, 0, 0,28 s | 72 % |
| bluetooth | nessuno | 0/0 | 11,0 | 30/30, 30 | 45 % |
| bluetooth | AEC3 | 37/21 | 0,4 | 29/30, 4, 0,35 s | 71 % |
| bluetooth | DTLN 512+allin | 41/33 | 0,0 | 30/30, 0, 0,28 s | 45 % |
| cassa-stop | nessuno | 0/0 | 10,9 | 30/30, 30 | **18 %** |
| cassa-stop | AEC3 | 39/23 | 0,7 | 30/30, 0, 0,37 s | 48 % |
| cassa-stop | DTLN 512+allin | 42/36 | 0,0 | 30/30, 0, 0,28 s | 27 % |
| forte-stop | nessuno | 0/0 | 10,9 | 30/30, 30 | 46 % |
| forte-stop | AEC3 | 32/24 | 0,7 (0,4) | 30/30, 1, 0,86 s | 57 % |
| forte-stop | DTLN 512+allin | 35/27 | 3,3 (1,8) | 30/30, 10, 0,27 s | 38 % |

Tabelle complete: `docs/ricerche/banchi/aec/dati/sim/erle.json` e `docs/ricerche/banchi/aec/dati/valutazione.json`.

### Cosa se ne ricava

1. **Senza AEC il barge-in con il VAD è impossibile.** Ogni risposta di Calliope fa
   scattare il VAD (11 volte al minuto) e in 30 doppi parlati su 30 lo scatto arriva
   sull'eco, prima che l'utente parli.
2. **Come rilevatore, AEC3 e DTLN 512+allin funzionano.** Nelle condizioni normali
   hanno 0–0,7 falsi al minuto. DTLN rileva l'utente prima (0,28 s contro 0,40 s) e non
   lo perde mai. AEC3, per non lasciar passare l'eco, attenua anche la voce vicina:
   con l'eco a +10 dB perde 11 frasi su 30 e le altre le rileva dopo 1,15 s.
3. **Per la trascrizione l'AEC fa più danno che bene.** Whisper tollera bene qualche
   centinaio di millisecondi di eco sotto la voce: in cassa-stop ha il 18 % di WER
   sull'audio grezzo, il 27 % dopo DTLN e il 48 % dopo AEC3. La strategia giusta è
   **rilevare sull'audio ripulito e trascrivere quello grezzo**, dopo aver fermato
   Calliope. Solo con l'eco molto forte (forte-stop) DTLN aiuta anche Whisper
   (38 % contro 46 %).
4. **DTLN senza allineamento non funziona** con 250–300 ms di ritardo (2–10 dB): è
   addestrato su ritardi piccoli. Con l'allineamento regge anche i salti del
   Bluetooth simulati (±40 ms), perché la LSTM tollera qualche decina di millisecondi
   di errore. AEC3 invece ha un suo stimatore del ritardo e l'allineamento esterno non
   cambia quasi nulla.
5. **speexdsp non basta**: 17–19 dB a regime e pochi dB all'avvio, con falsi al
   minuto quasi come senza AEC.
6. Sulla voce dell'utente da sola i motori non fanno danni: la WER resta tra l'11 e
   il 18 %, con differenze di 1–3 parole su 153, cioè rumore statistico.

## 3. Misura reale (26/09, 4 riproduzioni brevi)

`docs/ricerche/banchi/aec/misura_reale.py` imita `Speaker` e `Listener`: uscita `RawOutputStream` int16 a
22050 Hz con 0,3 s di silenzio iniziale e keepalive, ingresso a 16 kHz a blocchi di
512 sempre aperto. Il ritardo si misura dal momento in cui la frase viene passata a
`write()` fino all'arrivo dell'eco nella callback del microfono: è il ritardo che
vedrebbe un'integrazione.

**Il C920 non era collegato**, e nemmeno le cuffie I52. Ho usato l'altoparlante del
portatile («Speakers (Realtek(R) Audio)», MME, volume di sistema al 90 %) con i
microfoni del portatile.

| Prova | Microfono | Eco (dBFS) | Rumore (dBFS) | Ritardo | Frasi del VAD senza AEC |
|---|---|---|---|---|---|
| A_0, A_1 | «Microphone (Realtek(R) Audio)», **MME** (quello che userebbe Calliope) | −64 / −75: al livello del rumore | −67 / −72 | non misurabile | **0** |
| B_0 (1,9 s), C_0 (7,2 s) | «Realtek Digital Microphone», **WDM-KS grezzo**, 48 kHz ricampionato | **−23 / −20** | −46 | **298 / 294 ms** | 1 / 1 |

In MME, durante la riproduzione, il livello del microfono **scende** di 10–15 dB. È il
segno di una cancellazione dell'eco con soppressione già nel percorso di Windows
(driver Realtek e Intel Smart Sound). Sul percorso grezzo l'eco è forte quanto la voce
dell'utente nelle registrazioni del C920 (mediana −21,5 dBFS). Il ritardo di ~300 ms è
formato dai 183 ms della latenza di uscita di PortAudio più driver e aria. Da qui il
ritardo usato nella simulazione.

I motori sull'eco vera (B_0 e C_0):

| Motore | ERLE (dB) | Uscita (dBFS) | Frasi del VAD | CPU ms/10 ms |
|---|---|---|---|---|
| nessuno | 0 / 0 | −23 / −20 | 1 / 1 | — |
| speex | 1 / 5 | −24 / −25 | 1 / 2 | 0,31 |
| speex+allin | 7 / 9 | −30 / −29 | 1 / 1 | 0,19 |
| AEC3 | 16 / 26 | −39 / −46 (rumore −46) | **0 / 0** | 0,05 |
| AEC3+NS | 18 / 28 | −41 / −48 | 0 / 0 | 0,05 |
| DTLN 256+allin | 39 / 45 | −62 / −65 | 0 / 0 | 0,53 |
| DTLN 512+allin | **44 / 47** | −67 / −67 | 0 / 0 | 2,4 |
| DTLN 512 senza allineamento | 7 / 21 | −29 / −42 | 1 / 1 | 2,3 |

AEC3 porta l'eco fino al rumore di fondo, e la sua ERLE è limitata proprio dal rumore.
DTLN toglie anche il rumore (è pure un soppressore), per questo la sua ERLE supera il
margine eco/rumore. La simulazione e la misura reale sono coerenti.

Sul portatile c'è dunque un **livello B «gratis»**: si usa il microfono interno in MME
e si lascia fare a Windows. Resta da verificare quanto rovini la voce nel doppio
parlato e come trascrive Whisper da quel microfono. Per il C920, Windows 11 offre
**Voice Clarity** (AEC, soppressione del rumore e dereverberazione, anche su ARM64) ai
flussi aperti in «Communications signal processing mode», cioè WASAPI con categoria
Communications. `sounddevice` non espone quel parametro: servirebbe un piccolo
intervento con ctypes su `PaWasapiStreamInfo`. Vale mezza giornata di prova prima di
scrivere codice AEC. Resta però una soluzione solo Windows e non si porta sui satelliti.

## 4. Integrazione in Calliope (stima)

### Flusso del riferimento

- In `Speaker._play_worker`, ogni blocco scritto in `stream.write()` (anche il silenzio
  del keepalive) si passa a un `ReferenceTap`. Il tap lo ricampiona 22050 → 16000 con
  `soxr.ResampleStream`, già nel .venv principale, e lo scrive in un buffer circolare
  indicizzato **con il contatore dei campioni del microfono** letto al momento del
  write. `Listener` deve esporre il contatore, incrementato nella callback. Se la voce
  cambia frequenza (voci a 16 kHz), il ricampionatore si ricrea insieme a
  `_open_stream`.
- `Listener.listen` resta attivo anche mentre Calliope parla. Per ogni frame da 512
  campioni si prende il frame di riferimento con lo stesso indice e si passa all'AEC
  (DTLN: 4 passi da 128; AEC3: blocchi da 160, con un piccolo accumulatore perché 512
  non è multiplo di 160). Il frame ripulito va al VAD e al rilevatore della wake word.
  Quello grezzo si tiene per Whisper.
- **Ritardo e deriva**:
  - AEC3 li gestisce da solo (stimatore interno), anche con il riferimento in anticipo
    di 300 ms.
  - Per DTLN si stima il ritardo con GCC-PHAT sugli ultimi 2–3 s di ogni risposta di
    Calliope e si tiene una media mobile, con 30 ms di margine.
  - La deriva tra C920 (clock USB) e Realtek (±50 ppm) vale ~3 ms al minuto e la
    ristima a ogni turno la assorbe.
  - Un salto grande (ricollegamento Bluetooth, riapertura dello stream al cambio voce)
    si riconosce da un crollo dell'ERLE e fa ripartire la stima.
- **Barge-in**: al VAD sull'audio ripulito (≥ 250–500 ms di parlato) si chiama
  `Speaker.interrompi()`, che svuota le code e fa `abort()` dell'uscita, poi si
  interrompe lo streaming di `Brain`. Questa parte è in comune con il livello A. La
  frase continua a essere raccolta e va a Whisper **grezza**, pre-roll compreso. Una
  guardia utile: la frase deve passare dal riconoscimento del parlante o dalla wake
  word testuale, così la TV non interrompe Calliope.

### Costo di CPU (CPU del portatile, un thread)

- AEC3: 0,05 ms ogni 10 ms, ~0,5 % di un core.
- DTLN 512: 2,3 ms, ~23 % di un core: il ciclo è in Python e LiteRT usa XNNPACK.
- DTLN 256: 0,5 ms, ~5 %. È una buona via di mezzo, ma con l'eco forte scende a 5–8
  falsi al minuto.

In ONNX e con i frame raggruppati il costo dovrebbe scendere. Non l'ho misurato.

### Dove fallisce

- **Volume alto e saturazione**: con l'eco a +10 dB sulla voce AEC3 perde un terzo
  degli interventi e DTLN arriva a 0,7–3,3 falsi al minuto. Se il microfono va in
  clipping, nessun AEC recupera. Anche l'AGC del C920 e gli «enhancement» audio di
  Windows sull'uscita (loudness, Dolby) sono non lineari o variabili nel tempo.
- **Bluetooth**: ritardo più lungo e variabile, con salti a ogni ritrasmissione. La
  simulazione con salti di ±40 ms regge; salti di 100 ms e oltre richiedono la ristima
  continua. Con le **cuffie** I52, però, l'eco al C920 è trascurabile: in cuffia
  l'AEC non serve, basta abilitare l'ascolto durante la risposta.
- **Suoni che non passano da `Speaker`**: notifiche, musica di un'altra app, TV. Non
  sono nel riferimento e restano rumore. Per la musica servirebbe come riferimento il
  loopback WASAPI dell'uscita, che `sounddevice` oggi non espone.
- **Windows su ARM**: livekit non ha il wheel e andrebbe compilato (Rust più
  libwebrtc). pyaec ce l'ha, ma è debole. DTLN funziona con onnxruntime win_arm64 dopo
  una conversione una tantum in ONNX (TensorFlow su Python ≤ 3.13); in alternativa si
  riscrive l'inferenza in numpy (due LSTM e un paio di strati densi per stadio).
- **Generalizzazione**: DTLN è stato provato su eco simulata e su due frasi reali di
  un solo microfono. Prima di fidarsi serve il test vocale con il C920 e con una
  persona che parla sopra Calliope.

### Confronto con i satelliti XMOS della visione

Sui satelliti XMOS (Voice PE, ReSpeaker XVF3800, Satellite1) l'AEC è in hardware. Il
riferimento è il segnale che va al DAC della scheda stessa: stesso clock, ritardo
fisso, nessuna deriva, nessuna stima. In più ci sono beamforming e dereverberazione, e
la CPU del server non lavora. È la soluzione giusta per le stanze, a patto che l'audio
esca dal satellite (vedi `2026-09-21-musica-e-hardware-audio.md`).

L'AEC software serve dove l'XMOS non c'è: il portatile di oggi come primo satellite, i
PC di casa come satelliti e le casse del server. Il codice va scritto dietro
un'interfaccia `EchoCanceller.process(mic, ref) → mic` (principio 2), così su un
satellite XMOS si sostituisce con un passaggio che non fa nulla.

### Giorni di lavoro stimati: 4–6

| Lavoro | Giorni |
|---|---|
| Conversione di DTLN-aec in ONNX (venv 3.13 una tantum) e classe in streaming con onnxruntime; in alternativa AEC3 con livekit per partire subito su x64 | 0,5–1 |
| `ReferenceTap` in `Speaker`, contatore dei campioni in `Listener`, stima del ritardo GCC-PHAT in linea con ristima | 1,5 |
| Barge-in: `Listener` attivo durante la risposta, regola del VAD, stop di `Speaker` e `Brain` (in parte fatto dal livello A), Whisper sul grezzo | 1 |
| Test vocale con C920, altoparlante, cuffie e volume alto; taratura della soglia; misura dei falsi con TV e musica | 1–1,5 |
| Prova preliminare facoltativa: Voice Clarity / microfono interno in MME, prima di scrivere l'AEC | 0,5 |

## File

- `docs/ricerche/banchi/aec/genera_riferimenti.py`: voce di Calliope con Piper (.venv principale).
- `docs/ricerche/banchi/aec/motori.py`: i motori (nessuno, speex, AEC3, DTLN) e la stima GCC-PHAT.
- `docs/ricerche/banchi/aec/simula.py`: eco simulata, 5 condizioni, ERLE.
- `docs/ricerche/banchi/aec/misura_reale.py`: riproduzione e registrazione reale (fa rumore).
- `docs/ricerche/banchi/aec/reale_aec.py`: i motori sulle registrazioni reali.
- `docs/ricerche/banchi/aec/valuta.py`: VAD come `Listener` e Whisper come `Transcriber` (.venv principale).
- `prove/prova_aec.py`: lancia i passi con il venv giusto.
- Ignorati da git: `docs/ricerche/banchi/aec/.venv/` (livekit, pyaec, ai-edge-litert, sounddevice…),
  `docs/ricerche/banchi/aec/modelli/` (DTLN-aec TF-Lite, 64 MB), `docs/ricerche/banchi/aec/dati/`.

## Fonti

- livekit su PyPI: https://pypi.org/project/livekit/ (1.1.20; wheel verificati via API JSON)
- pyaec / aec-rs: https://pypi.org/project/pyaec/, https://github.com/thewh1teagle/aec-rs
- DTLN-aec: https://github.com/breizhn/DTLN-aec (licenza MIT, modelli in `pretrained_models/`)
- ai-edge-litert: https://pypi.org/project/ai-edge-litert/ (2.2.0); onnxruntime 1.30.0 (wheel win_arm64)
- speexdsp 0.1.1, webrtc-audio-processing 0.1.3, aec-audio-processing 1.0.1, webrtc-apm 0.1.6: pagine PyPI
- Voice Clarity su tutti i PC Windows 11 x64 e Arm64, tramite Communications mode:
  https://www.windowscentral.com/software-apps/windows-11/all-windows-11-pcs-will-soon-support-this-ai-feature-once-exclusive-to-surface-no-npu-required,
  https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-signal-processing-modes
