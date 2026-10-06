# Riconoscimento di chi parla: dall'MFCC agli embedding neurali

*24 settembre 2026. Script: [`prove/prova_speaker.py`](../../prove/prova_speaker.py).
Modelli, dati di prova e risultati grezzi (`risultati.json`, `latenza.json`,
`log_misura.txt`) in `models/speaker/`, ignorata da git. Decisione aperta E della
[visione](../visione.md).*

## In breve

- **L'MFCC attuale non distingue le persone.** Alla soglia di oggi (0,70) accetta come
  Dario **un estraneo su tre** (32,6 % delle frasi di 63 italiani reali) e **il 78 %
  delle frasi Piper**; EER 10 %, 13 % a parità di canale.
- **Un embedding neurale in ONNX risolve il problema** con un costo di pochi millisecondi
  di CPU e nessuna dipendenza nuova: EER dal 10 % allo **0,4 %** (impostori da altri
  microfoni) e dal 13 % al **2,0 %** (a parità di canale); le voci Piper non superano 0,32
  contro una soglia di 0,48.
- **Raccomandazione**: **3D-Speaker CAM++ `campplus_sv_zh_en_16k-common_advanced`** (28 MB,
  Apache 2.0) con **fbank in numpy + onnxruntime**, **soglia 0,48**, **5 frasi di
  arruolamento**, **aggiornamento dell'impronta** solo sopra **0,58**, con media mobile
  α = 0,1 e un'ancora a coseno ≥ 0,90 con l'impronta di partenza. Costo: circa 25 ms per
  una frase di 3 s (4 thread), da eseguire **in parallelo a Whisper**: sul percorso
  vocale non aggiunge nulla.
- **Alternativa più precisa sulle frasi corte**: 3D-Speaker **ERes2NetV2** (71 MB,
  soglia 0,62), da 3 a 4 volte più lento. Da riconsiderare sullo Spark.
- **I modelli WeSpeaker caricati con sherpa-onnx non funzionano così come sono**: sherpa
  non sottrae la media delle feature, e WeSpeaker CAM++ finisce a EER 45 %. Con la
  sottrazione, fatta a mano in numpy, tornano buoni.
- **Limite della misura**: una sola voce di casa. La soglia è tarata su parlanti di
  corpora pubblici registrati "nello stesso canale". Quando si arruolano altri familiari
  (genitori, figli, fratelli hanno voci più simili) va rimisurata con lo stesso script.

## Domanda

`speaker_id.py` calcola la media dei 13 MFCC della frase e la confronta con il profilo
tramite coseno. Nei test del 21–24/09 i punteggi di Dario contro sé stesso vanno da 0,64 a
0,97 con soglia 0,70, e una voce Piper femminile arriva già a 0,65. Serve un
riconoscimento molto più discriminante per preferenze, memoria per persona e livelli
(ospite / familiare / amministra), **non** per autorizzare azioni sensibili (principio 9 e
"Chi parla ≠ autorizzazione" della visione).

## Stato dell'arte (settembre 2026): modelli usabili offline in ONNX

Tutti i modelli sotto sono nella release `speaker-recongition-models` di sherpa-onnx
(file `.onnx` con i metadati di preprocessing; checksum SHA-256 verificati) e girano con il
solo onnxruntime. Ingresso: fbank a 80 bande a 16 kHz; uscita: un vettore da 192 a 512
valori. "EER dichiarato" è quello dei rispettivi autori, in inglese su VoxCeleb1-O salvo
dove indicato.

| Modello | File | Parametri | EER dichiarato | Addestramento | Licenza |
|---|---|---|---|---|---|
| 3D-Speaker **CAM++ zh_en advanced** | 28 MB | ~7,2 M | Vox1-O 1,16 %, CN-Celeb 5,98 % | "grande" dataset cinese + inglese | Apache 2.0 |
| 3D-Speaker **ERes2Net base 200k** | 40 MB | ~6,6 M | CN-Celeb ~4–5 % | ~200k parlanti cinesi | Apache 2.0 |
| 3D-Speaker **ERes2NetV2** (common) | 71 MB | ~17,8 M | CN-Celeb 3,81 % | ~200k parlanti cinesi | Apache 2.0 |
| WeSpeaker **ResNet34-LM** | 26,5 MB | 6,6 M | 0,72–0,80 % | VoxCeleb2 (inglese e altre lingue, YouTube) | CC BY 4.0 (come VoxCeleb) |
| WeSpeaker **CAM++-LM** | 29 MB | 7,2 M | 0,66 % | VoxCeleb2 | CC BY 4.0 |
| WeSpeaker **ResNet152-LM** | 79 MB | ~20 M | ~0,4–0,5 % | VoxCeleb2 | CC BY 4.0 |
| NVIDIA NeMo **TitaNet-small** | 40 MB | ~6 M | ~1 % | Vox1+2, Fisher, Switchboard, LibriSpeech, SRE | CC BY 4.0 |
| NVIDIA NeMo **TitaNet-large** | 101 MB | 23 M | 0,66 % | come sopra | CC BY 4.0 |

Altri, non misurati: **SpeechBrain ECAPA-TDNN** (VoxCeleb, EER ~0,8 %, Apache 2.0): non ha
un ONNX ufficiale e l'export richiede torch e le sue feature; **WeSpeaker ReDimNet** e
**SimAM-ResNet VoxBlink2** (multilingue, EER 0,2–0,4 %): pesi pubblicati, ONNX solo da
esportare. Nessuno di questi modelli è addestrato sull'italiano: i 3D-Speaker su cinese
(e inglese per CAM++ advanced), i WeSpeaker e NeMo su VoxCeleb, che contiene anche parlanti
italiani. Un embedding del parlante dipende poco dalla lingua, e le misure sotto lo
confermano.

**Runtime.** `onnxruntime` 1.30 ha wheel `win_arm64` per cp311–cp314 ed è già nel venv.
`sherpa-onnx` 1.13.8 ha wheel `win_arm64` per cp311–cp314 (più `sherpa-onnx-core`,
`py3-none-win_arm64`), porta con sé un proprio onnxruntime e calcola le fbank da solo. Qui
ha convissuto senza problemi con `onnxruntime` 1.30 nello stesso processo.

## Dati

- **Dario**: 124 registrazioni di `registrazioni/*/` (webcam C920, 16 kHz, 21/09 e
  24/09, 7 sessioni). **120 usate**; **4 escluse come incerte**: le prime quattro frasi
  dell'8° test (v03c), dette durante una conversazione con un'altra persona. I loro
  punteggi sono riportati a parte. Durata 1,6–11,4 s, silenzi del VAD compresi; il 49 %
  sotto 2,5 s. Nessuna frase sotto 1,5 s: le brevi sono state ricavate a parte (vedi
  "Durata").
- **Impostori umani reali, italiano** (scaricati in `models/speaker/dati/`, 190 MB di
  audio estratto):
  - **Multilingual LibriSpeech italiano**, split `test` + `dev` (Hugging Face
    `facebook/multilingual_librispeech`, file parquet da 83 + 81 MB): **20 lettori** di
    audiolibri LibriVox, 12 frasi ciascuno. Licenza **CC BY 4.0**.
  - **VoxPopuli italiano**, split `test`, solo il secondo row group del parquet (~150 MB
    letti a intervalli da `facebook/voxpopuli`): **43 parlanti** del Parlamento europeo
    con almeno 2 frasi, fino a 12 ciascuno. Licenza **CC0**.
  - Totale **63 parlanti, 384 frasi**. Common Voice non è stato usato: dal 2025 lo
    scaricamento passa da Mozilla Data Collective, con account.
  - Da ogni frase si ricavano due ritagli: uno con la durata estratta dalla distribuzione
    delle frasi di Dario, uno "breve" di 1,6–2,5 s. In più c'è il secondo più energico
    (1 s di parlato vero). Sono 768 prove di impostore più 384 da 1 s.
- **Impostori sintetici**: le 10 voci Piper di `voices/` (5 femminili, 5 maschili)
  × 18 frasi del copione, ricampionate a 16 kHz con 0,3 s di silenzio davanti. 180 prove
  più 180 da 1 s.

## Metodo

- **Arruolamento** con 3, 5 o 10 frasi di Dario (≥ 1,5 s), 30 estrazioni a caso;
  **verifica** su tutte le altre. Profilo = media degli embedding normalizzati (per l'MFCC
  la media grezza, come fa `speaker_id.py`); punteggio = coseno.
- **Altri canali**: Dario contro tutti gli impostori (umani + Piper). Qui gli impostori
  vengono da altri microfoni, e il canale da solo aiuta a scartarli: la misura è
  ottimista.
- **Stesso canale** (la misura che conta per la soglia): ogni parlante MLS o VoxPopuli con
  almeno 6 frasi viene arruolato con 3 frasi e confrontato con i suoi ritagli (di altre
  frasi) e con tutti gli altri parlanti dello stesso corpus. Sono 1.970 prove bersaglio e
  51.070 prove impostore. La **soglia a falsi accettati 1 %** calcolata qui si applica poi
  a Dario, alla famiglia simulata e all'aggiornamento.
- **Due sessioni**: arruolamento con le prime 3 frasi del 21/09, verifica sul 24/09.
- **Famiglia simulata**: Dario più 6 parlanti MLS/VoxPopuli arruolati con 3 frasi; tutti
  gli altri, Piper compresi, sono ospiti. Identificazione "a insieme aperto": vince il
  profilo più vicino, se supera la soglia. 5 estrazioni: 1.095 prove di familiari e
  4.050 di ospiti.
- **Aggiornamento dell'impronta**: profilo delle 3 frasi del 21/09, poi le altre frasi
  del 21/09 in ordine di tempo. Se il punteggio supera soglia + 0,10, il profilo diventa
  `norm(0,9·p + 0,1·e)`, ma solo se resta a coseno ≥ 0,90 dall'impronta di partenza.
  Poi si verifica sul 24/09. Prova di avvelenamento: le frasi dell'impostore umano più
  simile a Dario passano per tre volte nella stessa regola.
- **Latenza** per frase (mediana di 10), a 1 e 4 thread, su frasi vere di Dario da 1, 3 e
  8 s; **memoria** privata in più dopo il caricamento del modello e la prima frase.

## Risultati

### Tabella principale

"Dario rifiutato" = frasi di Dario sotto la soglia a FA 1 % stesso canale, con 3 / 5 / 10
frasi di arruolamento. Latenza per una frase di 3 s, 1 thread / 4 thread, con la CPU
occupata al 40–75 % da altri processi (vedi "Latenza").

| Modello (runtime) | EER altri canali (3 fr.) | EER stesso canale | Soglia FA 1 % | Dario rifiutato 3 / 5 / 10 fr. | Solo 1 s di parlato: Dario rifiutato 3 / 10 fr. | Piper, punteggio max | ms 3 s (1 t / 4 t) |
|---|---|---|---|---|---|---|---|
| **MFCC attuale** | 10,1 % | 13,4 % | 0,917 | 53 / 46 / 37 % | 99 / 99 % | 0,93 | 2 / 2 |
| WeSpeaker ResNet34-LM (sherpa) | 3,3 % | 16,5 % | 0,871 | — | — | 0,92 | — |
| WeSpeaker CAM++-LM (sherpa) | **45,3 %** | 43,8 % | — | inutilizzabile | — | — | — |
| WeSpeaker ResNet152-LM (sherpa) | 2,4 % | 18,4 % | 0,909 | — | — | 0,94 | — |
| WeSpeaker ResNet34-LM (numpy + CMN) | 0,29 % | 2,69 % | 0,469 | 10,6 / 5,7 / 3,5 % | 52 / 28 % | 0,28 | 138 / 39 |
| WeSpeaker CAM++-LM (numpy + CMN) | 1,06 % | 3,10 % | 0,501 | 13,6 / 7,6 / 4,6 % | 72 / 53 % | 0,25 | ~40 / 20 |
| **3D-Speaker CAM++ adv. (numpy)** | **0,40 %** | **2,03 %** | **0,477** | **8,1 / 4,0 / 2,0 %** | 49 / 29 % | **0,24** | **51 / 25** |
| 3D-Speaker CAM++ adv. (sherpa) | 0,40 % | 2,28 % | 0,507 | 10,3 / 5,4 / 3,6 % | 58 / 38 % | 0,30 | 54 / 24 |
| 3D-Speaker ERes2Net base 200k (sherpa) | 0,13 % | 2,44 % | 0,646 | 4,4 / 2,8 / 2,2 % | 49 / 32 % | 0,52 | 155 / 49 |
| 3D-Speaker ERes2NetV2 (sherpa) | 0,12 % | 2,28 % | 0,636 | 3,8 / 2,0 / 1,3 % | 37 / 21 % | 0,49 | ~315 / 92 |
| 3D-Speaker ERes2NetV2 (numpy) | 0,14 % | 2,38 % | 0,621 | 4,9 / 3,4 / 2,0 % | 32 / 21 % | 0,47 | 367 / 111 |
| NeMo TitaNet-small (sherpa) | 1,07 % | 2,59 % | 0,491 | 23 / 15 / 9,3 % | 64 / 42 % | 0,36 | 38 / 17 |
| NeMo TitaNet-large (sherpa) | 0,34 % | 2,44 % | 0,479 | 19 / 11 / 5,7 % | 76 / 58 % | 0,28 | ~139 / 46 |

Con 10 frasi, l'EER "altri canali" scende a 0,01–0,17 % per i modelli 3D-Speaker e per
ResNet34 con CMN. Le estrazioni casuali spostano i tassi di rifiuto di Dario di 1–2 punti
(la curva più sotto usa estrazioni diverse). "~": misura fatta con la CPU al 100 %,
valore ottimista rispetto alle altre righe.

**Come leggere la tabella.** Contro impostori di altri canali quasi tutti i modelli
neurali sembrano perfetti. La differenza vera sta nella colonna "stesso canale": lì i
tre WeSpeaker caricati con sherpa crollano (16–18 % e 44 %) e l'MFCC resta al 13 %. I
modelli ben usati stanno tutti tra 2,0 e 3,1 %. Il resto della scelta lo decidono il tasso
di rifiuto di Dario (quanto spesso lo tratta da ospite) e il costo.

### Il difetto di sherpa-onnx con WeSpeaker

WeSpeaker addestra i suoi modelli sottraendo a ogni fbank la media della frase (CMN).
L'export ONNX non la include, e sherpa-onnx (1.13.8) la applica solo ai modelli con
`feature_normalize_type = global-mean` nei metadati, cioè ai 3D-Speaker. Il risultato è
che con WeSpeaker tutte le voci si somigliano (punteggi di impostori fino a 0,95). Con la
sottrazione fatta in numpy, ResNet34 passa da EER 16,5 % a 2,7 % (stesso canale) e
CAM++ da 43,8 % a 3,1 %. Il comando `fbank` dello script lo verifica: senza CMN il
risultato numpy coincide con quello di sherpa (coseno 0,97), con la CMN no (0,07). Le fbank
numpy coincidono con `torchaudio.compliance.kaldi.fbank` (scarto massimo 2·10⁻⁴).

### Distribuzione dei punteggi (3 frasi di arruolamento, media su 30 estrazioni)

| Modello | Dario: minimo / 5° perc. / mediana | Umani: mediana / 99° perc. / massimo | Piper: mediana / massimo |
|---|---|---|---|
| MFCC attuale | 0,71 / 0,78 / 0,91 | 0,63 / 0,88 / 0,91 | 0,77 / 0,91 |
| CAM++ adv. (numpy) | 0,36 / 0,46 / 0,61 | 0,11 / 0,32 / 0,40 | 0,15 / 0,32 |
| ERes2NetV2 (numpy) | 0,55 / 0,62 / 0,76 | 0,30 / 0,49 / 0,56 | 0,24 / 0,51 |

Con l'MFCC i due gruppi si sovrappongono quasi del tutto: il 99° percentile degli
estranei (0,88) supera il 5° percentile di Dario (0,78), e la mediana delle voci Piper
(0,77) gli è praticamente uguale. Con CAM++ c'è uno spazio vuoto tra il massimo degli
estranei di altri canali (0,40) e il 5° percentile di Dario (0,46).

**MFCC alla soglia di oggi** (3 frasi, 30 estrazioni): a **0,70** Dario è rifiutato nello
0,9 % dei casi, ma sono accettati il **32,6 %** degli umani e il **78,5 %** delle frasi
Piper; a 0,75 i valori sono 3,5 %, 18,1 % e 50,6 %. È ciò che si vedeva nei test.

### Soglia: la curva per i due finalisti

Soglia scelta a diversi falsi accettati stesso canale; Dario rifiutato con 3 / 5 / 10 frasi;
famiglia simulata (7 profili) con i familiari riconosciuti, quelli scambiati per un altro
familiare e gli ospiti accettati come familiari.

**3D-Speaker CAM++ adv. (numpy)**

| FA stesso canale | Soglia | Dario rifiutato 3 / 5 / 10 | Famiglia: giusti | scambiati | ospiti accettati |
|---|---|---|---|---|---|
| 2 % | 0,418 | 2,4 / 1,0 / 0,4 % | 97,0 % | 0 | 6,2 % |
| **1 %** | **0,477** | **8,0 / 5,3 / 1,7 %** | **93,3 %** | **0** | **2,8 %** |
| 0,5 % | 0,548 | 24 / 17 / 8,6 % | 83,0 % | 0 | 1,6 % |
| 0,2 % | 0,613 | 50 / 36 / 22 % | 65,5 % | 0 | 0,6 % |
| 0,1 % | 0,656 | 71 / 54 / 39 % | 52,4 % | 0 | 0,3 % |

**3D-Speaker ERes2NetV2 (numpy)**

| FA stesso canale | Soglia | Dario rifiutato 3 / 5 / 10 | Famiglia: giusti | scambiati | ospiti accettati |
|---|---|---|---|---|---|
| 2 % | 0,583 | 2,3 / 0,8 / 0,1 % | 97,7 % | 0 | 4,9 % |
| **1 %** | **0,621** | **5,6 / 3,3 / 1,7 %** | **94,6 %** | **0** | **2,5 %** |
| 0,5 % | 0,673 | 13 / 7,5 / 6,4 % | 87,2 % | 0 | 1,4 % |
| 0,2 % | 0,719 | 30 / 16 / 11 % | 70,9 % | 0 | 0,6 % |

In nessuna configurazione un familiare è stato scambiato per un altro familiare: l'errore
possibile è "familiare trattato da ospite" oppure "ospite trattato da familiare". Con 7
profili gli ospiti accettati sono circa il doppio o il triplo del FA per singolo confronto:
un ospite ha più occasioni di somigliare a qualcuno.

### Durata della frase

- **Brevi** (< 2,5 s con i silenzi del VAD, come «Calliope.» o «Che ore sono?»), CAM++
  numpy: Dario rifiutato nel 14 % dei casi con 3 frasi, 7 % con 5, 4 % con 10 (sulle frasi
  lunghe circa la metà). EER altri canali 0,64 % contro 0,00 % delle lunghe.
- **Solo 1 s di parlato** (il secondo più energico della frase): Dario rifiutato nel 49 % dei casi con 3
  frasi e nel 29 % con 10. ERes2NetV2 fa meglio (32 % e 21 %); l'MFCC rifiuta il 99 %.
  Stesso canale, 1 s: EER 3,0 % (CAM++) e 4,5 % (ERes2NetV2).
- In pratica: sotto circa 1,5 s di voce il riconoscimento non è affidabile con nessun
  modello. La decisione giusta è **tenere l'identità della conversazione** (la finestra di
  follow-up) invece di rifarla da zero su ogni frase corta.

### Due sessioni e aggiornamento dell'impronta

| CAM++ adv. (numpy), soglia 0,477 | Profilo fermo | Profilo aggiornato |
|---|---|---|
| Arruolamento | 3 frasi del 21/09 | idem, più 21 aggiornamenti dalle altre frasi del 21/09 |
| Dario rifiutato sul 24/09 | 17,9 % | **3,6 %** |
| Impostori accettati | 0 % | 0 % |
| EER | 0,05 % | 0,00 % |
| Coseno con l'impronta di partenza | 1 | 0,90 (fermato dall'ancora) |
| Aggiornamenti accettati all'impostore più simile | — | **0** |

Per ERes2NetV2: da 5,4 % a 3,6 % (43 aggiornamenti). Per TitaNet-large: da 62 % a 16 %.
L'aggiornamento fa ciò che la visione chiede ("solo con campioni sopra soglia e conservando
quella di partenza"). Qui la "deriva" va verso la voce media di Dario: 3 frasi sono un
campione povero, e il profilo si allontana dall'impronta iniziale fino al limite
dell'ancora (0,90). Nessun impostore ha mai superato la soglia di aggiornamento. Il
rischio vero è un altro: un ospite con voce simile che parla a lungo **dentro una
conversazione già attribuita a un familiare**. Per questo si aggiorna solo con il
punteggio della frase stessa, mai con l'identità "ereditata" dalla conversazione.

### Frasi incerte (8° test, v03c)

Punteggi contro il profilo del 21/09, CAM++ numpy: 0,58, 0,40 («Ah, ah, ah, ah»: una
risata), 0,60 e 0,61. ERes2NetV2: 0,61, 0,49, 0,77 e 0,80. Sono coerenti con Dario (la
risata è il caso difficile), quindi l'altra persona della conversazione non è finita
nelle registrazioni come frase a sé. Nessun impostore di "stesso canale" è disponibile
dalle registrazioni di casa.

### Latenza e memoria (CPU Intel Core Ultra 9 275HX)

Durante la misura principale un altro lavoro teneva la CPU al 100 % (16 processi Python).
La tabella viene da una seconda misura con carico al 40–75 %. I valori assoluti sono quindi
per eccesso, mentre l'ordine tra i modelli è stabile in tutte e tre le misure fatte.

| Modello | 1 thread: 1 s / 3 s / 8 s | 4 thread: 1 s / 3 s / 8 s | Memoria in più |
|---|---|---|---|
| MFCC attuale | 1 / 2 / 3 ms | 1 / 2 / 4 ms | (torch già caricato) |
| **CAM++ adv. (numpy)** | **29 / 51 / 165 ms** | **16 / 25 / 68 ms** | ~100 MiB |
| CAM++ adv. (sherpa) | 29 / 54 / 156 ms | 16 / 24 / 66 ms | ~55 MiB |
| ERes2Net base 200k (sherpa) | 82 / 155 / 495 ms | 27 / 49 / 160 ms | ~65 MiB |
| ERes2NetV2 (numpy) | 192 / 367 / 1133 ms | 60 / 111 / 388 ms | ~145 MiB |
| ResNet34-LM (numpy) | 63 / 138 / 380 ms | 21 / 39 / 114 ms | ~50 MiB |
| TitaNet-small (sherpa) | 22 / 38 / 109 ms | 10 / 17 / 51 ms | ~70 MiB |

La memoria della variante numpy comprende l'arena di onnxruntime e le matrici delle fbank,
non ottimizzate. Nessun modello usa la GPU: la VRAM resta a Whisper e all'LLM.

## Raccomandazione

**Modello**: `3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx` (28,3 MB,
SHA-256 `aa3cfc16…ceba2`, Apache 2.0), eseguito con **onnxruntime** e le **fbank in numpy**
(80 bande, finestra povey, dither 0, campioni in [-1, 1], poi sottrazione della media per
frase): è la funzione `kaldi_fbank` di `prove/prova_speaker.py`, una trentina di righe.

Perché questo e non ERes2NetV2: ha la migliore EER stesso canale (2,0 %), il punteggio
massimo di Piper più basso e costa da 4 a 5 volte meno. Con 5 frasi di arruolamento e
l'aggiornamento automatico il suo svantaggio sulle poche frasi sparisce (sul 24/09 rifiuta
il 3,6 % con il profilo aggiornato, contro il 3,6 % di ERes2NetV2). ERes2NetV2 resta
l'alternativa se, dopo l'uso vero, i rifiuti su frasi corte danno fastidio. Si cambia
solo il file del modello e la soglia (0,62).

**Valori** (da mettere in `Config`, non nel codice):

| Parametro | Valore | Motivo |
|---|---|---|
| `speaker_model` | `models/speaker/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx` | |
| `speaker_threshold` | **0,48** | FA 1 % stesso canale; Dario rifiutato 4–5 % con 5 frasi, 2 % con 10; famiglia di 7: 2,8 % di ospiti accettati, 0 scambi |
| `speaker_threshold_confirm` | **0,42** | FA 2 %: zona grigia 0,42–0,48 in cui l'identità si può "confermare dalla conversazione" (come oggi), solo fino a *familiare* e mai ad *amministra* |
| `speaker_update_threshold` | **0,58** | soglia + 0,10: nessun impostore l'ha mai superata |
| `speaker_update_alpha` | **0,1** | media mobile sull'embedding normalizzato |
| `speaker_anchor_min` | **0,90** | coseno minimo con l'impronta di arruolamento |
| `speaker_enroll_phrases` | **5** (oggi 3), ciascuna ≥ 1,5 s di audio | da 8 % a 5 % di rifiuti; con 10 si arriva al 2 % ma l'arruolamento diventa noioso: il resto lo fa l'aggiornamento |
| `speaker_min_speech_s` | **1,0** s di voce | sotto questa durata non si decide: si tiene l'identità della conversazione |
| `speaker_threads` | **2** | ~30 ms per 3 s, lascia CPU a Piper e al resto |

Se la casa vorrà essere più prudente con gli ospiti (per esempio con 5–6 persone
arruolate), si sale a **0,55** (FA 0,5 %: 1,6 % di ospiti accettati), ma Dario è
rifiutato nell'8–17 % dei casi finché il profilo non si è arricchito.

### Integrazione in `speaker_id.py` (proposta, non applicata)

1. **Interfaccia invariata**: `mfcc_embedding(audio, sr)` diventa `speaker_embedding(audio, sr)`
   (con un alias per compatibilità) e restituisce l'embedding normalizzato del modello
   ONNX. La sessione onnxruntime si crea una volta sola, in modo pigro, dal percorso in
   `Config`. `cosine_similarity` resta com'è.
2. **Profili**: `UserProfile` salva `model` (nome del file) e `anchor` (l'impronta di
   arruolamento) accanto a `voiceprint`, e i `samples` dell'arruolamento. Il profilo è la
   media degli embedding **normalizzati** (non grezzi come oggi).
3. **Profili esistenti**: all'avvio, un profilo con `model` diverso (o con 13 valori,
   l'MFCC) viene marcato "da riarruolare". Nome, `admin`, `gender` e `preferred_voice`
   restano; `identify` non lo usa finché non è riarruolato. Il primo ad accorgersene è
   Dario: al primo turno Calliope chiede le 5 frasi. **Il flag `admin` va conservato**,
   altrimenti chi amministra torna ospite.
4. **Identificazione a insieme aperto**: vince il profilo migliore se ≥ 0,48. Nelle misure
   non sono mai serviti margini sul secondo profilo; un margine di 0,05 non costa nulla e
   si può aggiungere quando ci saranno davvero più familiari.
5. **Aggiornamento**: in `identify`, se il punteggio della frase è ≥ 0,58 e la frase ha
   almeno 1,5 s di voce, `p ← norm(0,9·p + 0,1·e)` solo se `cos(p_nuovo, anchor) ≥ 0,90`.
   Mai durante l'arruolamento di un'altra persona, mai sulla base dell'identità ereditata
   dalla conversazione, mai per gli ospiti. Il comando per svuotare i dati (visione,
   "Privacy") deve cancellare anche i campioni.
6. **In parallelo a Whisper**: nel ciclo principale l'embedding si lancia su un
   `ThreadPoolExecutor` appena il VAD chiude la frase, insieme alla trascrizione. onnxruntime
   rilascia il GIL e la parte numpy dura pochi millisecondi. Con Whisper a 0,17–0,29 s su
   GPU e l'embedding a 25–50 ms su CPU, **il costo sul percorso vocale è 0 ms**. In serie
   costerebbe 25–50 ms per frase (fino a ~70 ms per frasi di 8 s): accettabile anche così,
   ma non serve.
7. **Registro dei turni**: continuare a salvare il punteggio (ora su un'altra scala: 0,3–0,8
   per Dario invece di 0,64–0,97). `revisione.py` e `docs/test-vocale.md` vanno aggiornati
   di conseguenza (punteggio minimo atteso di Dario ≈ 0,45).
8. **Genere**: `estimate_gender` usa `torchaudio.functional.detect_pitch_frequency`. Non è
   toccato da questa scelta, ma è l'ultima ragione per cui `speaker_id.py` importa torch
   (vedi sotto).

### Dipendenze e download

- **Nessun pacchetto nuovo** per la soluzione raccomandata: `numpy` e `onnxruntime` ci sono già.
- **Download**: un file da 28,3 MB, `3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx`
  da `https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/`
  (la grafia "recongition" è quella del tag), da mettere in `models/speaker/` (ignorata da
  git; resta ignorato anche `*.onnx`).
- **Installato per la misura nel `.venv`**: `sherpa-onnx==1.13.8` (+ `sherpa-onnx-core`),
  servito per i modelli NeMo e per il confronto. **Non serve a Calliope** e si può
  disinstallare (`pip uninstall sherpa-onnx sherpa-onnx-core`).
- **venv separato** `models/speaker/.venv-dati` (pyarrow, soundfile, soxr, numpy,
  huggingface_hub, fsspec): serve solo a `prepara` per leggere i parquet.

### Compatibilità con Windows su ARM

- `onnxruntime` 1.30.0: wheel `win_arm64` cp311–cp314 su PyPI. `numpy` 2.5.3: `win_arm64`
  cp312–cp315. La soluzione raccomandata è quindi a posto.
- `sherpa-onnx` 1.13.8: `win_arm64` cp311–cp314. È un'alternativa valida, e utile anche
  per il TTS su ARM (ricerca sulle voci), ma qui non serve e con WeSpeaker sbaglia.
- **torch / torchaudio sono il rischio vero**: su PyPI torch 2.14 non ha wheel
  `win_arm64`; l'indice di PyTorch ha `torch` 2.9.1+cpu `win_arm64` solo per cp311–cp313
  (non 3.14) e **nessun `torchaudio` `win_arm64`**. Oggi `speaker_id.py` dipende da
  torchaudio per l'MFCC e per il genere. Con questa proposta l'MFCC sparisce. Resta
  `estimate_gender`, da riscrivere in numpy (autocorrelazione) o da spostare sul modello
  (fuori dallo scopo di questa ricerca). Anche il VAD in `calliope.py` usa torch: Silero
  VAD esiste in ONNX.

## Rischi e limiti

- **Una sola persona di casa.** Tutto il "stesso canale" viene da audiolibri (ogni lettore
  con il suo microfono) e dal Parlamento europeo (stesso impianto). In una casa vera i
  familiari parlano nello stesso microfono, e **i parenti hanno voci più simili** di due
  estranei. La soglia 0,48 è un punto di partenza: quando si arruola il secondo familiare
  si ripete `prova_speaker.py` con le sue frasi (basta aggiungerle ai dati) e si ritara.
- **Microfoni diversi tra arruolamento e uso** (satelliti XMOS, Voice PE, webcam) abbassano
  i punteggi dello stesso parlante: si vede già tra i due giorni di test con la stessa
  webcam (rifiuti dal 5 al 18 % con 3 frasi). L'aggiornamento aiuta; più avanti conviene un
  profilo per tipo di microfono o, meglio, arruolare dal satellite della stanza.
- **Voce clonata o registrata**: un embedding del parlante non distingue una registrazione
  dalla persona, e un clone ben fatto la imita. È il motivo per cui la voce non autorizza
  azioni sensibili (visione, principio 9): questa scelta non lo cambia.
- **Piper non è un buon test di clonazione**: le voci Piper sono di altre persone. Un TTS
  che clona la voce di Dario (Pocket TTS, Qwen3-TTS) quasi certamente supera la soglia.
- **Frasi sotto 1 s di voce**: non affidabili con nessun modello (29–49 % di rifiuti).
- **La misura della latenza** è stata fatta con la CPU condivisa con un altro lavoro: i
  tempi assoluti vanno riconfermati a macchina scarica. L'ordine tra i modelli è stabile.
- **Lingua**: nessun modello è addestrato sull'italiano, ma sui 63 parlanti italiani la
  qualità è in linea con quella dichiarata sui corpora originali (EER stesso canale
  ~2 %, contro l'1,2 % di CAM++ advanced su VoxCeleb).
- **Licenze dei pesi**: i 3D-Speaker sono Apache 2.0 senza vincoli. I WeSpeaker e NeMo
  seguono la CC BY 4.0 dei dati di addestramento (attribuzione), irrilevante per l'uso in
  casa.
- **Dati di prova**: le voci di MLS e VoxPopuli sono pubbliche ma restano voci di persone.
  Sono in `models/speaker/dati/`, fuori da git, e si possono cancellare dopo la misura
  (~190 MB di WAV più ~160 MB di parquet).

## Come ripetere

```powershell
$env:PYTHONUTF8=1
# una tantum: venv per leggere i parquet
python -m venv models\speaker\.venv-dati
models\speaker\.venv-dati\Scripts\pip install pyarrow soundfile soxr numpy huggingface_hub fsspec
# modelli: scaricare i .onnx dalla release sherpa-onnx "speaker-recongition-models" in models\speaker\
# dati: mls_it_test.parquet e mls_it_dev.parquet in models\speaker\dati\ (vedi docstring dello script)
models\speaker\.venv-dati\Scripts\python prove\prova_speaker.py prepara
.\.venv\Scripts\python -u prove\prova_speaker.py piper
.\.venv\Scripts\python -u prove\prova_speaker.py misura          # ~40 min la prima volta, poi embedding in cache
.\.venv\Scripts\python -u prove\prova_speaker.py misura --senza-latenza   # solo metriche, pochi minuti
.\.venv\Scripts\python -u prove\prova_speaker.py latenza
.\.venv\Scripts\python -u prove\prova_speaker.py fbank
```

## File

- `prove/prova_speaker.py`: lo script di misura (nuovo).
- `prove/LEGGIMI.md`: una riga nella tabella e i risultati principali (aggiornato).
- `.gitignore`: aggiunta `models/speaker/`.
- `models/speaker/`: 8 modelli ONNX (~410 MB), `dati/` (parquet MLS, WAV di impostori
  umani e Piper), `.venv-dati/`, `risultati/` (embedding in cache, `risultati.json`,
  `latenza.json`, `log_misura.txt`).

## Fonti

- sherpa-onnx, modelli di riconoscimento del parlante:
  <https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models>; PyPI
  `sherpa-onnx` 1.13.8 e `sherpa-onnx-core`.
- 3D-Speaker (Apache 2.0, tabella EER): <https://github.com/modelscope/3D-Speaker>;
  schede ModelScope `iic/speech_campplus_sv_zh_en_16k-common_advanced` (Vox1-O 1,16 %,
  CN-Celeb 5,98 %) e `iic/speech_eres2netv2_sv_zh-cn_16k-common` (~200k parlanti,
  CN-Celeb 3,81 %).
- WeSpeaker, modelli e risultati VoxCeleb: <https://github.com/wenet-e2e/wespeaker>
  (`docs/pretrained.md`, `examples/voxceleb/v2/README.md`).
- NVIDIA TitaNet-large: <https://huggingface.co/nvidia/speakerverification_en_titanet_large>.
- Multilingual LibriSpeech (CC BY 4.0): <https://huggingface.co/datasets/facebook/multilingual_librispeech>.
- VoxPopuli (CC0): <https://huggingface.co/datasets/facebook/voxpopuli>.
- Wheel: PyPI `onnxruntime` 1.30.0, `numpy` 2.5.3, `torch` 2.14.0, `torchaudio` 2.11.0;
  indice <https://download.pytorch.org/whl/cpu/>.
