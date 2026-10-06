# Taratura di Whisper sulle registrazioni dei test vocali

*24 settembre 2026. Script: [`prove/prova_whisper.py`](../../prove/prova_whisper.py).
Riferimenti: [`prove/riferimenti_whisper.tsv`](../../prove/riferimenti_whisper.tsv).
Risultati frase per frase: `prove/risultati_whisper.tsv`.*

## Domanda

Nei test vocali del 24/09 il limite è diventato la trascrizione: 5 frasi storpiate su 15
nel test ridotto, con l'audio intero. `Transcriber` usa la decodifica più economica
(`beam_size=1`, prompt fisso). Quanto si guadagna cambiando i parametri, e a che prezzo?

## Dati

- **110 registrazioni** della voce di Dario (webcam C920, 16 kHz), da sei cartelle in
  `registrazioni/` (21/09, quattro sessioni; 24/09, test completo e ridotto).
- **Riferimenti**: il testo detto davvero, ricostruito dall'ordine del copione
  (`docs/test-vocale.md`), dalla trascrizione di allora, da una trascrizione di
  controllo con `beam_size=5` e, nei casi dubbi, dai tempi delle singole parole (per
  esempio «Galliope» a 0,0 s nelle due frasi lunghe del 21/09 dice che il nome c'era).
- **104 sicure** (56 dette «subito», 48 dopo una pausa), **6 incerte**, escluse dalle
  metriche: 4 frasi fuori copione non ricostruibili («Allio, Pede», «Andiopera», «Grazie a
  tutti» del 24/09, una ripetizione con le cuffie mute), 1 con «ma» forse detto davvero
  («Calliope, ma che ore sono?»), 1 in cui non si sa se c'era il nome.
- Frasi del copione poi cambiate (ad es. «Chi ha scritto…» ripetuta con il nome davanti)
  hanno come riferimento ciò che è stato detto, non il copione.

## Metodo

`large-v3-turbo` su CUDA con lo stesso setup di `Transcriber` (`_add_cuda_dlls`,
`language="it"`, `condition_on_previous_text=False`). Si parte dalla configurazione
attuale e si cambia un fattore alla volta, poi si combinano i migliori. Metriche:

- **WER** normalizzata: minuscole, senza punteggiatura, «47» = «quarantasette»;
- **frasi esatte**;
- **wake word**: `find_wake_word` di `calliope.py` sulle frasi che iniziano con «Calliope»,
  e falsi risvegli sulle altre;
- **allucinazioni** (frasi in `HALLUCINATIONS`), **prompt ricopiato** nella trascrizione,
  **«Calliope» inserito** dove non era detto;
- **tempo** per frase dopo il warm-up (media e 95° percentile). Ollama è rimasto caricato
  (gemma4, ~4,6 GiB), come nell'uso reale.

## Risultati

| Configurazione | WER | Esatte /104 | WER «subito» | WER pausa | Wake /46 | Falsi | Prompt ricopiato | Nome inserito | t medio | t p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| **baseline** (oggi) | 14,3 % | 64 | 20,1 % | 8,6 % | 43 | 1 | 0 | 0 | 0,19 s | 0,24 s |
| `beam_size=5` | 12,8 % | 67 | 16,4 % | 9,2 % | 43 | 1 | 0 | 0 | 0,22 s | 0,30 s |
| `float16` | 13,5 % | 65 | 17,1 % | 9,9 % | 42 | 1 | 0 | 0 | 0,22 s | 0,28 s |
| `hotwords="Calliope"` | 13,3 % | 64 | 19,4 % | 7,3 % | 43 | 1 | 0 | 0 | 0,19 s | 0,26 s |
| `temperature=0` | 14,3 % | 64 | 20,1 % | 8,6 % | 43 | 1 | 0 | 0 | 0,18 s | 0,22 s |
| `vad_filter=True` | 14,0 % | 64 | 19,4 % | 8,6 % | 43 | 1 | 0 | 0 | 0,20 s | 0,29 s |
| `without_timestamps` | 15,6 % | 62 | 20,1 % | 11,2 % | 40 | 1 | 0 | 0 | 0,19 s | 0,25 s |
| senza prompt | 25,9 % | 39 | 23,1 % | 28,7 % | 26 | 2 | — | 1 | 0,22 s | 0,44 s |
| prompt ricco ¹ | 10,6 % | 71 | 17,1 % | 4,3 % | 43 | 2 | 0 | 1 | 0,20 s | 0,27 s |
| prompt comandi ² | 12,0 % | 70 | 18,4 % | 5,6 % | 43 | 2 | 1 | 1 | 0,23 s | 0,35 s |
| prompt contesto ³ | 14,0 % | 66 | 20,1 % | 7,9 % | 41 | 2 | 0 | 1 | 0,20 s | 0,31 s |
| beam 5 + prompt ricco | 10,8 % | 72 | 16,7 % | 5,0 % | 44 | 3 | 2 | 2 | 0,24 s | 0,39 s |
| **beam 5 + hotwords** | **11,0 %** | 69 | **15,1 %** | 6,9 % | 43 | **1** | **0** | **0** | 0,23 s | 0,34 s |
| beam 5 + prompt comandi | 11,5 % | 74 | 18,1 % | 5,0 % | 43 | 2 | 1 | 1 | 0,22 s | 0,33 s |
| beam 5 + comandi + hotwords | 10,6 % | 73 | 16,4 % | 5,0 % | 43 | 2 | 1 | 1 | 0,24 s | 0,36 s |
| beam 5 + comandi + temp 0 | 11,5 % | 74 | 18,1 % | 5,0 % | 43 | 2 | 1 | 1 | 0,22 s | 0,28 s |
| beam 5 + hotwords + parole ⁴ | 12,0 % | 72 | 18,1 % | 5,9 % | 42 | 2 | 0 | — | 0,23 s | 0,31 s |
| `large-v3` (non turbo) | 12,5 % | 64 | 18,4 % | 6,6 % | **46** | 2 | 0 | — | 0,37 s | 0,80 s |
| `large-v3` + beam 5 | 10,3 % | 69 | 15,4 % | 5,3 % | 45 | 2 | 0 | — | 0,40 s | 0,62 s |
| `large-v3` + beam 5 + comandi | 10,1 % | 72 | 16,1 % | 4,3 % | 46 | 2 | 0 | — | 0,40 s | 0,63 s |

¹ «Conversazione con Calliope, un'assistente vocale. Comandi: Calliope, esci; cambia voce,
Paola, Serena; che ore sono; numero preferito.» Contiene **«che ore sono»**, frase intera del
copione: il guadagno è in parte gonfiato dal test.
² Solo il vocabolario dei comandi veri: «… Parole frequenti: Calliope, esci, voce, Paola, Serena.»
³ «Conversazione in italiano con Calliope, un'assistente vocale di casa.»
⁴ «Conversazione con Calliope. Esci, voce, Paola, Serena.»

Con 104 frasi, una frase in più o in meno sposta la WER di circa un punto: differenze
sotto i 2 punti sono rumore.

**VRAM** (misurata con `nvidia-smi`, contesto CUDA compreso): `large-v3-turbo` +1,18 GiB
sia con beam 1 sia con beam 5; `large-v3` +1,87 GiB.

## Cosa si impara

1. **Il prompt iniziale è la leva più forte, ma è pericoloso.** Senza prompt la WER
   raddoppia (25,9 %) e la wake word crolla (26 su 46): il prompt attuale va tenuto. I prompt
   più lunghi abbassano la WER, soprattutto dopo le pause, ma Whisper **li ricopia**
   quando l'audio è poco chiaro: «C'è un'assistente vocale.» al posto di «Chi ha scritto I
   promessi sposi?» (in 6 configurazioni su 7 con un prompt lungo), «Comandi, esci.» al
   posto di «Esci.». E **aggiungono «Calliope» dove non è stato detto** («Calliope,
   ricordati che il mio numero…»): con la wake word testuale è un falso risveglio.
2. **`beam_size=5` è il guadagno più sicuro sulle frasi dette subito** (20,1 → 16,4 %), che
   sono quelle che falliscono nei test. Non ricopia niente e non inventa il nome.
3. **`hotwords="Calliope"` aiuta il nome senza gli effetti del prompt**: combinato con beam 5
   dà la WER «subito» più bassa di tutte (15,1 %). Corregge per esempio «Calliope eshi» →
   «Calliope, esci», «Calliope, e sci» → «Calliope, esci», «All'io per riuscire» → «Calliope,
   esci» e «Chiamano Dario» → «chiamami Dario».
4. **`float16`, `temperature=0`, `vad_filter`, `without_timestamps` non servono**: tutto
   dentro il rumore o peggio (`without_timestamps` perde 3 risvegli).
5. **`large-v3` riconosce sempre il nome** (46 su 46) ma costa il doppio del tempo (p95 fino
   a 0,8 s) e +0,7 GiB di VRAM, per una WER uguale a turbo con beam 5. Oggi non conviene;
   da riconsiderare sullo Spark, dove la memoria non manca.

## Raccomandazione

In `Transcriber._run`, lasciando tutto il resto com'è:

```python
segments, _ = self.model.transcribe(
    audio, language=self.cfg.language,
    beam_size=5,                     # era 1
    hotwords=self.cfg.name,          # nuovo: "Calliope" (faster-whisper ≥ 1.1)
    initial_prompt=self.prompt,      # invariato: "Conversazione con Calliope."
    condition_on_previous_text=False)
```

- Effetto: WER 14,3 → 11,0 %, frasi «subito» 20,1 → 15,1 %, frasi esatte 64 → 69, nessun
  prompt ricopiato, nessun nome inventato.
- **Costo**: +0,04 s di media e +0,10 s al 95° percentile per frase (0,19 → 0,23 s; 0,24
  → 0,34 s). Nessuna VRAM in più. Si somma direttamente al tempo della prima frase.
- Conviene rendere i due valori configurabili (`whisper_beam_size`, `whisper_hotwords`) in
  `Config`.

## Cosa nessuna configurazione risolve

17 frasi su 104 sono sbagliate con tutte le 21 configurazioni (25 con le prime 17; le
varianti di `large-v3` ne correggono 8). Tre famiglie:

- **Parole brevi scambiate con parole vere e plausibili**: «Vuoi» per «Puoi» (3 volte),
  «luce» per «voce», «voce» per «voci», «Fai» per «Sai», «tra» per «tre», «Che» per «Chi»,
  «Torna la voce» per «Torna alla voce», «documentale» per «documentario». Il suono è
  ambiguo e l'errore è una frase italiana corretta: nessun parametro lo corregge, può
  aiutare solo l'LLM (che capisce «Vuoi cambiare voce?» lo stesso).
- **Attacco della frase storpiato, anche con l'audio intero** (quasi tutte «subito»):
  «E quella della Spagna?» diventa «Equale lo spagnac», «Ricordo la spagnale», «Cura della
  Spagna»; «Perché il cielo è azzurro?» diventa «C'è il ragazzo, però?»; «Calliope, esci»
  diventa «Cambio per pesci» e «Addio pesci!». Sono le frasi dette con più fretta, subito
  dopo una risposta: è probabilmente la dizione più che la decodifica.
- **Nomi propri**: «Dario Lipari» → «Dario Lipani» / «darei ulipari».

Per il nome in testa alla frase la strada giusta resta quella della roadmap: una wake
word dedicata (openWakeWord), che non dipende dalla trascrizione.

## Trovato per strada (fuori dalla taratura)

- **Falso risveglio in `find_wake_word`**: con la soglia `wake_match = 0,65`, «cavallo»
  somiglia a «calliope» per 0,67. La frase 11 detta senza nome («… a Costantinopoli a
  cavallo») sveglia Calliope con qualunque configurazione. Rimedi possibili: soglia a 0,70,
  oppure confrontare solo parole di lunghezza vicina a quella del nome, oppure cercare il
  nome solo nelle prime parole della frase.
- `Config.whisper_model` dice «~770 MiB di VRAM»: nel processo, contesto CUDA compreso,
  sono ~1,2 GiB.
