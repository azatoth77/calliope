# Trascrizione: Whisper contro le alternative, e la correzione delle frasi incerte (05/10/2026)

Richiesta di Dario del 05/10: trovare qualcosa di meglio di Whisper per l'italiano, in
particolare sulle parole della casa. Errori veri di quel giorno, da whisper.cpp sulla DGX:
«lo schermo del mio **seppellito**» (satellite), «riprendere un porto», «Calliope **di
Michisono**» (dimmi chi sono), «Calliope e Milostrato delle Luci» (dimmi lo stato delle luci).

## Cosa si è misurato

Tutto sulla DGX (richieste locali, niente VPN nei tempi), con `prove/misura_stt.py`.

- **rif**: le 104 registrazioni vere con riferimento sicuro della taratura del 24/09
  (`prove/riferimenti_whisper.tsv`; webcam C920 e microfono del portatile).
- **dominio**: 50 frasi con le parole della casa (satelliti, schermi, stanze di HA, persone,
  tool, gli errori veri qui sopra; `prove/riferimenti_dominio.tsv`) dette da tre voci di Piper
  (giorgio, paola, riccardo x_low) con rumore rosa a 20 dB (`prove/sintetizza_dominio.py`):
  150 frasi. Sono voci sintetiche: servono a confrontare i motori sulle parole, non danno la
  WER assoluta della voce vera.
- Metriche: WER (sostituzioni, cancellazioni, inserimenti), frasi esatte, **parole di
  dominio** ritrovate (le parole del vocabolario della casa presenti nel riferimento),
  **parafrasi** (frasi con ≥ 2 parole nuove e somiglianza < 0,6: invenzioni), tempo per frase.

## Risultati

| Motore | WER rif | esatte rif | dominio rif | WER dominio | esatte dom. | dominio dom. | parafrasi | tempo med / p90 | memoria | dipendenze, ARM | licenza |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1. whisper.cpp** (large-v3-turbo, oggi) | 13,4 % | 67/104 | 66/78 | 20,6 % | 68/150 | 183/237 | 4 + 5 | 0,28 / 0,30 s | ~2,1 GB | già in uso (CUDA, aarch64) | MIT |
| **2. + correzione, gemma4 26B** (soglia 0,5) | **11,4 %** | 73 | 69/78 | **17,4 %** | 84 | 196/237 | 0 peggiorate | +0,40 / 0,47 s sul 41 % delle frasi | 0 (è la voce) | nessuna | Gemma |
| 2. + correzione, 26B (soglia 0,7) | 10,9 % | 75 | 69/78 | 16,4 % | 88 | 202/237 | 0 peggiorate | +0,40 / 0,50 s sul 70 % | 0 | nessuna | Gemma |
| 2. + correzione, qwen3.6 su vLLM (0,5) | 11,6 % | 71 | 68/78 | 17,5 % | 83 | 196/237 | 0 peggiorate | +0,34 / 0,42 s | 0 (agente), ma in coda col lavoro | nessuna | Apache 2.0 |
| 2. + correzione, gemma4 e4b (0,5) | 12,6 % | 68 | 67/78 | 18,9 % | 76 | 192/237 | 3 peggiorate | +0,40 / 0,47 s | 0 se è la voce | nessuna | Gemma |
| 2. + correzione 26B **senza vocabolario** (0,5) | 11,9 % | 71 | 66/78 | 18,9 % | 76 | 188/237 | 1 peggiorata | +0,36 / 0,42 s | 0 | nessuna | Gemma |
| 3. gemma4 e4b con l'audio | 37,8 % | 22 | 19/78 | 36,4 % | 47 | 170/237 | 15 + 12 | 0,23 / 0,35 s | ~4,6 GB | Ollama | Gemma |
| 3. … con vocabolario e storia nel prompt | 80,8 % | 27 | 57/78 | 72,9 % | 41 | 164/237 | 47 + 63 | 0,27 / 0,41 s | ~4,6 GB | Ollama | Gemma |
| 4. Voxtral Mini 3B (vLLM, /audio/transcriptions) | 25,5 % | 33 | 22/78 | 24,6 % | 60 | 167/237 | 11 + 6 | 1,03 / 1,54 s | 8,8 GB di pesi, ~17 GB riservati da vLLM | immagine vLLM con l'audio (22 GB) | Apache 2.0 |
| 4. Voxtral, chat con vocabolario e storia | 104 % | 36 | 28/78 | 63,7 % | 59 | 179/237 | 25 + 22 | 0,56 / 1,75 s | come sopra | come sopra | Apache 2.0 |
| 5. Parakeet TDT 0.6B v3 (onnx-asr, CPU) | 29,2 % | 32 | 22/78 | 23,9 % | 58 | 168/237 | 8 + 5 | 0,17 / 0,30 s (rif), 0,30 / 0,38 (dom.) | 640 MB | onnxruntime + numpy, aarch64 sì | CC-BY-4.0 |

Le tempistiche della correzione sono **in più**, e solo sulle frasi incerte; con il 26B il
modello è quello della voce (stessa finestra di 28 672 token e stesso keep_alive: niente
ricarica). WER rif senza il nome «Calliope»: whisper.cpp 14,6 %, Voxtral 27,5 %, Parakeet 27,5 %
(Parakeet perde quasi sempre il nome: 86 cancellazioni), gemma4 audio 40,8 %.

### Le alternative

- **gemma4 e4b con l'audio** non trascrive, **risponde o riassume**: «Cerca nella biblioteca
  chi ha scritto I promessi sposi» → «Il promesso espose è stato scritto da John Calvin».
  Con il vocabolario nel prompt è peggio (WER 73–81 %): inserisce le parole della lista.
- **Voxtral Mini** ha l'encoder di Whisper e ne ripete molti errori parola per parola
  («Affida alla gente uno schippa», «Fai in una foto con la Weddan»), ma con il nome sbaglia di
  più («All'iope che ore sono?», «Che li ho bevvi?» per «Calliope.») ed è 3–4 volte più lento.
  Il prompt di /audio/transcriptions viene ignorato (uscita identica). In chat con il contesto
  inventa frasi intere: «Calliope, dimmi chi sono.» → «Dario, il tuo studio è a 100 metri da
  casa tua…», «A che punto è il lavoro?» → «Dario, ti do uno script Python…». Scartato.
- **Parakeet v3**: leggero, solo CPU, veloce, ma sulle registrazioni vere è al doppio della WER
  di Whisper e perde il nome. Senza prompt né hotwords non c'è modo di insegnargli le parole
  della casa. Scartato.
- **Canary**: non provato. Il modello multilingue con l'italiano richiede NeMo (torch) o una
  conversione ONNX non pronta: fuori dai vincoli (dipendenze pesanti, ARM). Parakeet v3, della
  stessa famiglia e con lo stesso encoder FastConformer, dice già dove si colloca.

### La correzione delle frasi incerte (variante 2)

`calliope/stt_correzione.py`: whisper-server restituisce con `verbose_json` la probabilità di
ogni token (stessi tempi del `json`, 0,28 s); se la parola più debole è sotto la soglia, il
modello di testo riceve la trascrizione, le parole incerte, il **vocabolario della casa**
(nome, persone, satelliti, schermi e stanze, entità e aree di HA, i tool detti a parole) e le
ultime frasi, e risponde con lo schema `{"testo": …}`. Poi `accettabile` tiene la proposta
solo se cambia **parole storpiate in parole che suonano simili** (somiglianza lettera per
lettera ≥ 0,5, lunghezza tra 0,6 e 1,6 volte, al più il 40 % delle parole, mai negazioni,
sì/no, numeri, aggiunte o tolte di parole lunghe). Se il modello tarda oltre
`stt_correzione_timeout_s` (1,5 s) resta Whisper.

- **26B**: rif 13,4 → 11,4 %, dominio 20,6 → 17,4 %, **nessuna frase peggiorata** a nessuna
  soglia (fino al 100 % delle frasi al secondo passaggio). Esempi: «Calliope di Michisono» →
  «Calliope dimmi chi sono», «Di mikro sonu» → «Dimmi chi sono», «Calliope e Milostrato delle
  Luci» → «Calliope dimmi lo stato delle luci», «da Wikicode» → «da Wikiquote», «Spiegamelo in
  modo semplice e convicidio» → «… con Vikidia». Sui 10 errori veri del 05/10: 5 corretti, 0
  sbagliati accettati; «seppellito» → «telefono» (sbagliata) e «Pessere di un timer» →
  «Imposta un timer» (giusta) sono fermate dal controllo del suono.
- **qwen3.6**: quasi uguale (11,6 / 17,5 %), un po' più veloce, ma sugli errori veri una
  proposta sbagliata passa il controllo («Di mikro sonu» → «Di microfono sono») e il vLLM
  dell'agente ha la sua coda: con un lavoro in corso la correzione aspetterebbe.
- **e4b**: aiuta meno e **rovina**: «Puoi cambiare voce?» → «Puoi cambiare luce?», «Perché il
  cielo è azzurro?» → «… è al suo?», «Calliope ti ha scritto i promessi sposi» → «… i
  promemoria». Con il 4B come voce la correzione va lasciata spenta.
- **Il vocabolario conta**: senza (solo il nome e i tool) il 26B scende meno (dominio 18,9 %
  invece di 17,4 %) e una frase peggiora («Perturale, io.» → «Per l'amore, io.»).
- La soglia 0,5 manda al secondo passaggio ~40 % delle frasi (43/104 vere); 0,7 il ~70 % per
  mezzo punto in più. Il costo, 0,4 s, si paga solo lì.

## Raccomandazione

1. **Restare su whisper.cpp** come trascrittore: nessuna alternativa locale è migliore per
   l'italiano su queste frasi; Voxtral, Parakeet e gemma4 audio sono tutti al doppio della WER
   o peggio, e i due modelli con l'audio inventano.
2. **Accendere la correzione delle frasi incerte con il 26B come voce** (profilo
   `gemma4-26b-ollama`, oggi sulla DGX): `stt_correzione: true` in `calliope.locale.yaml`,
   soglia 0,5 (0,7 se il mezzo punto vale +0,4 s su un'altra frase su tre). Prima una prova a
   voce: il registro dei turni scrive `stt_corretta` con prima e dopo, da guardare dopo qualche
   giorno. Con il 4B come voce lasciarla spenta.
3. Le registrazioni con il riferimento vanno allargate con frasi vere di dominio (satellite,
   schermo, Vikidia…): oggi le frasi di dominio sono sintetiche.

## Cosa resta sulla DGX

`~/stt-prova` (9,6 GB): pesi di Voxtral Mini 3B (8,8 GB) e Parakeet v3 ONNX (640 MB) in
`hf/`, il venv delle misure (149 MB), i WAV delle due serie (24 MB), i risultati (`ris/`,
1,5 MB). Container `stt-voxtral` fermato e tolto; l'immagine `calliope-vllm-audio:v0.29.0`
(22 GB) c'era già dal 02/10. Ollama come prima (26B con keep_alive infinito); gemma4 e4b era già
scaricato. Per liberare lo spazio: `rm -rf ~/stt-prova/hf` (o tutta la cartella).
