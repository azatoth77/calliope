# Emozioni dalla voce nella simulazione d'interrogazione (07/10/2026)

*Ramo `ricerca-emozioni`. Solo ricerca: niente codice, nessun modello né dataset scaricato,
nessuna azione sulla DGX. Fonti primarie consultate il 06–07/10/2026 (elenco con le date in
fondo): testo italiano del Reg. (UE) 2024/1689 (Gazzetta ufficiale, versione consolidata del
12/07/2024), linee guida della Commissione sulle pratiche vietate (C(2025) 5052 final del
29/07/2025), legge 132/2025, Commento generale n. 25 del Comitato ONU sui diritti dell'infanzia,
schede dei modelli su Hugging Face, articoli di emotion2vec, EmoBox, audEERING, FAU-Aibo
rivisitato e la classifica della sfida Interspeech 2025. Contesto:
[`../aree/minori.md`](../aree/minori.md), idea «Simulazione interrogazione» nella pagina dei
lavori (P2), [`2026-10-05-minori.md`](2026-10-05-minori.md),
[`2026-10-07-kolibri.md`](2026-10-07-kolibri.md). Non è un parere legale.*

## 1. In breve

- **Tecnica.** I modelli aperti esistono e girano in locale su CPU (emotion2vec+, i modelli
  dimensionali di audEERING, WavLM/HuBERT con una testa): 90–300 M di parametri, nessuna libreria
  nativa nuova oltre a onnxruntime (che c'è già). Ma la **precisione sul nostro caso non è
  dimostrata da nessuno**: italiano, ragazzi, parlato naturale, microfono di un telefono. I numeri
  pubblicati crollano passo dopo passo: dataset recitati in italiano 58–77 % (7 classi, anche gli
  ascoltatori umani si fermano al 66 %), parlato naturale in inglese 0,43 di macro-F1 (8 classi,
  il migliore di 93 squadre), bambini tedeschi in parlato naturale 0,45 di UAR su 5 classi (15
  anni di progresso: quasi niente). Tra le dimensioni, **l'«attivazione» (arousal) è la sola
  misurabile con una certa affidabilità**; la «sicurezza» corrisponde alla «dominanza», la più
  debole (CCC ~0,5 in inglese sugli adulti); la valenza dei modelli audio si appoggia al lessico
  inglese.
- **Misure oggettive.** Pause, tempi, velocità d'eloquio, ripartenze, variazione del tono e del
  volume si misurano bene con quello che Calliope ha già (Silero VAD, tempi di Whisper, numpy) e,
  se serve, librosa (ISC, puro Python, ma `soxr` non ha la wheel win_arm64: sulla DGX va bene).
  Parselmouth è GPL-3 e non ha la wheel aarch64; openSMILE ha una licenza solo non commerciale.
  Jitter e shimmer qui non servono (misure cliniche, rovinate dal microfono del telefono).
- **Norma.** Il divieto dell'AI Act (art. 5(1)(f)) vale **sul luogo di lavoro e negli istituti di
  istruzione**: le linee guida della Commissione dicono esplicitamente che un'app che usa le
  emozioni per studiare **fuori** da un istituto non è vietata, ma lo diventa se è la scuola a
  imporla. «Agitazione», «ansia», «arousal» e «sicurezza» contano come emozioni (le linee guida
  citano «emotional arousal and anxiousness» e vietano di aggirare il divieto chiamandole
  «atteggiamenti»). In casa i genitori sono esenti dagli obblighi del deployer (art. 2(10)), ma
  il sistema resta **ad alto rischio** (allegato III, 1(c), dal 2/12/2027): chi lo fa e lo
  distribuisce ha gli obblighi del fornitore. Il GDPR quasi non si applica a un uso familiare
  (art. 2(2)(c)); la legge italiana 132/2025 chiede il consenso dei genitori sotto i 14 anni e
  lascia decidere il ragazzo dai 14.
- **Raccomandazione.** Partire **senza** riconoscimento delle emozioni: misure oggettive
  confrontate con la storia del ragazzo stesso («pause più lunghe del tuo solito») più una domanda
  a lui («come ti sei sentito?»). È quasi tutto il valore, ed è fuori dalla definizione di
  «sistema di riconoscimento delle emozioni» (considerando 18). Se Dario vuole comunque la parte
  emotiva: **solo l'attivazione, per sessione, rispetto al proprio solito, in prova chiusa** sulle
  voci vere della famiglia con una soglia decisa prima; visibile **prima di tutto al ragazzo**, al
  tutore solo come andamento e con il ragazzo che lo sa (e, dai 14 anni, che è d'accordo). Mai
  nella versione pubblicata di Calliope, mai su richiesta della scuola.

## 2. Tecnica: riconoscimento delle emozioni dalla voce (SER)

### 2.1 Modelli aperti

| Modello | Uscita | Parametri / file | Licenza del modello | Dati di addestramento | CPU / ONNX | Note |
|---|---|---|---|---|---|---|
| **emotion2vec+ base / large** (Alibaba, 05/2024) | 9 classi (rabbia, disgusto, paura, gioia, neutro, tristezza, sorpresa, altro, sconosciuto) + vettore | ~90 M / ~300 M (`model.pt` large 1,95 GB) | FunASR Model License 1.1: uso commerciale ammesso con attribuzione | 4 788 h (base), 42 526 h (large) pseudo-etichettate, multilingue | PyTorch (FunASR); ONNX non ufficiale, da esportare | La base più forte tra quelle aperte; nessun numero pubblicato sull'italiano per la versione «+» |
| **emotion2vec** (12/2023) | vettore (sonda lineare sopra) | ~90 M | MIT (codice) | 262 h inglesi (auto-supervisionato) | come sopra | EMOVO 61 % WA (10 fold casuali: parlanti in comune tra addestramento e prova) |
| **audEERING w2v2-L-robust-12 MSP-dim** (2022, agg. 09/2024) | arousal, dominanza, valenza 0–1 + vettore | ~200 M | **CC-BY-NC-SA 4.0**: solo non commerciale; licenza commerciale da audEERING | MSP-Podcast 1.7 (inglese, parlato naturale) | **ONNX ufficiale** (Zenodo) | Valenza CCC 0,638 su MSP-Podcast, ma la valenza si appoggia a informazione linguistica implicita (inglese) |
| **3loi SER-Odyssey WavLM** (06/2024) | 8 classi o 3 attributi | ~300 M | MIT sui pesi; addestrato su MSP-Podcast (licenza accademica) | MSP-Podcast | PyTorch, esportabile | Licenza dei dati più stretta di quella dei pesi |
| **Vox-Profile** (USC, 2025: `tiantiaf/...`) | arousal/valenza, categorie, anche «flusso del parlato» | WavLM-L / Whisper-L | OpenRAIL | MSP-Podcast e altri | PyTorch | Interessante il «flusso» (scioltezza) |
| **SpeechBrain wav2vec2-IEMOCAP** | 4 classi | ~95 M | Apache-2.0 (pesi); IEMOCAP solo per ricerca | IEMOCAP (inglese recitato) | PyTorch | Vecchio, dati recitati |
| **SenseVoice Small** | trascrizione + etichetta d'emozione | come Whisper small | FunASR Model License | — | ONNX ufficiale | L'italiano non è tra le lingue dichiarate |

Gli LLM con l'audio (gemma4 con l'audio, Qwen-Omni…) sono più grandi e su EMOVO/parlato naturale
non hanno numeri migliori pubblicati e verificabili; il confronto STT del 05/10 ha già visto
gemma4 e4b rispondere invece di trascrivere. Non li considero.

### 2.2 Quanto sono precisi (numeri pubblicati)

| Condizione | Dato | Risultato | Caso | Fonte |
|---|---|---|---|---|
| Italiano recitato, 6 attori | EMOVO, 7 classi, 588 frasi, lascia-fuori-un-parlante | UA 57,8 % (Whisper-large-v3 encoder + testa), WavLM-L 48,8 % | 14 % | EmoBox, Interspeech 2024 |
| Italiano recitato, 431 attori amatoriali | Emozionalmente, 7 classi, divisione per parlante | UA 76,9 % (Whisper-L), WavLM-L 75,0 % | 14 % | EmoBox |
| **Ascoltatori umani** sullo stesso | Emozionalmente, 829 valutatori | **UAR 66 %** | 14 % | scheda OpenSLR 161 |
| Inglese, parlato **naturale** (podcast), 8 classi | MSP-Podcast, sfida Interspeech 2025, 93 squadre | macro-F1 **0,43** (1°), base 0,33 | — | classifica ufficiale |
| Stesso, dimensioni | idem | CCC valenza 0,68, **arousal 0,64, dominanza 0,50** (1°) | — | classifica ufficiale |
| Tra dataset diversi (4 classi bilanciate) | EmoBox cross-corpus | 15–67 %, per lo più 30–50 % | 25 % | EmoBox |
| **Bambini** 10–13 anni, tedesco, parlato naturale | FAU-Aibo, 5 classi | UAR 0,38 (2009) → **0,45** (2024, wav2vec2/Whisper); 2 classi 0,68 → 0,72 | 0,20 / 0,50 | Triantafyllopoulos et al., 2024 |
| Stress da prova sociale (TSST) | 50 persone | «parzialmente prevedibile», sopra la base | — | arXiv 2607.00986 (07/2026) |
| Ansia (GAD-7) e voce, 2 000 persone | parlato spontaneo | correlazione più forte: quantità di parlato, r = −0,12 | — | JMIR Mental Health 2022 |

Lettura onesta:

1. **Recitato ≠ naturale.** I numeri alti vengono da attori che esagerano l'emozione. Un ragazzo
   che risponde a un'interrogazione simulata produce emozioni lievi e miste: il caso di
   MSP-Podcast e FAU-Aibo, dove i modelli migliori sono a 0,43–0,45.
2. **Italiano.** Non esiste un dataset italiano di parlato naturale con emozioni; quelli recitati
   (EMOVO, Emozionalmente) e quello indotto (DEMoS, accesso ristretto) sono di adulti.
3. **Ragazzi.** Nessun corpus italiano di bambini con emozioni (c'è CHILDIT2, ma è lettura senza
   emozioni). Il riferimento è FAU-Aibo (tedesco), dove quindici anni di modelli non hanno quasi
   mosso il risultato. Le voci dei bambini hanno F0 più alta e articolazione diversa; i modelli
   auto-supervisionati sono addestrati su adulti.
4. **Categorie contro dimensioni.** Le categorie («ansioso», «triste») su parlato naturale
   sbagliano più spesso di quanto indovinino. Le dimensioni continue sono più oneste ma
   diseguali: arousal discreto, dominanza (≈ «sicurezza») debole, valenza in buona parte dovuta
   al lessico inglese che il modello ha imparato: su un'interrogazione in italiano, dove le parole
   sono di storia o di scienze, non c'è da fidarsi.
5. **Microfono e stanza.** Le prove tra dataset diversi perdono 20–40 punti; ogni corpus è un
   «canale». Calliope ha già visto quanto pesa il canale: l'audio dell'iPhone accelerato o
   ripulito dal browser faceva scendere l'impronta CAM++ da 0,64–0,69 a 0,16–0,22
   ([`../aree/schermi-telefono.md`](../aree/schermi-telefono.md)). Controllo automatico del
   guadagno e soppressione del rumore cambiano proprio volume e dinamica, cioè quello che i
   modelli usano per l'arousal.
6. **La persona.** audEERING stesso segnala un effetto del parlante che resta: lo stesso valore
   assoluto vuol dire cose diverse in voci diverse. L'unico confronto sensato è **con sé stessi**.

### 2.3 Farne uno nostro

Classificatore leggero (regressione ridge o logistica, o due strati) sopra le rappresentazioni
congelate di un modello (emotion2vec+ base, WavLM o l'encoder di Whisper, che su EmoBox è il
migliore tra dataset diversi). Il lavoro vero non è il modello, sono le **etichette**:

| Fonte di etichette | Pro | Contro |
|---|---|---|
| Emozionalmente (CC-BY 4.0, adulti, recitato) | italiano, licenza libera, 6 902 frasi | recitato, adulti, categorie |
| MSP-Podcast (dimensioni, naturale) | dimensioni, naturale | inglese, licenza accademica (niente uso commerciale) |
| **Autovalutazione del ragazzo** dopo ogni sessione («quanto ti sentivi sicuro, da 1 a 5») | è il dato che conta, nella sua voce, sul suo microfono | poche centinaia di punti per persona, rumorosa |

Conclusione: un modello «nostro» per ragazzi italiani di qualità pubblicabile non è alla portata
(servirebbero centinaia di parlanti etichettati). È fattibile una **taratura personale**: modello
pronto per l'arousal + base del ragazzo stesso + controllo contro la sua autovalutazione.

**Come misurarlo onestamente** (prima di mostrare qualsiasi cosa):

1. Dati: sessioni vere dei ragazzi di casa, con il loro accordo (e dei genitori), audio tenuto
   solo per la prova; dopo ogni risposta un'autovalutazione di un tasto (1–5: «quanto eri
   sicuro?», «quanto eri agitato?») e, a parte, il giudizio di un adulto che ascolta **senza**
   vedere l'uscita del modello.
2. Metriche dentro la persona: Spearman/CCC tra punteggio del modello (sottratta la media della
   persona) e autovalutazione, con intervalli di confidenza (bootstrap per sessione); stessa cosa
   contro l'ascoltatore; accordo tra ragazzo e ascoltatore come tetto.
3. Stabilità: la stessa risposta registrata **insieme** dal telefono e dal portatile (differenza
   dovuta al solo canale) e la stessa risposta ripetuta due volte; il canale deve pesare meno
   della differenza tra sessioni che si vuole mostrare.
4. Confondenti: correlazione tra arousal e risposta giusta/sbagliata, lunghezza, volume medio,
   stanchezza a fine sessione (il modello potrebbe misurare solo «parla più forte»).
5. Soglia decisa **prima**: per esempio Spearman dentro la persona ≥ 0,4 con l'intervallo sopra
   0,2, e differenza di canale < metà dell'escursione tra sessioni; sotto soglia la parte emotiva
   non si accende.

## 3. Misure prosodiche oggettive

Nell'interrogazione servono misure **descrittive** e confrontate con il proprio solito, non
norme di popolazione (le velocità tipiche cambiano con l'età e il compito).

| Misura | Come | Con cosa | Affidabilità | Utile per |
|---|---|---|---|---|
| Tempo di latenza (domanda → prima parola) | inizio del parlato | Silero VAD (c'è già) | alta | esitazione iniziale |
| Pause silenziose: numero, durata, % del tempo | silenzi > 250 ms dentro la risposta (soglia classica, da tarare) | Silero VAD, registrazione intera senza tagli | alta | scioltezza |
| Velocità d'eloquio e d'articolazione | sillabe (o parole) / tempo totale e / tempo parlato | tempi per token di whisper.cpp (`verbose_json`), conteggio sillabe italiano a regole | media–alta | ritmo |
| Ripartenze, ripetizioni, riempitivi («ehm») | dalla trascrizione | Whisper tende a **togliere** i riempitivi: un prompt con riempitivi li fa scrivere (da verificare in italiano) | media | sicurezza nell'esposizione, senza inferire emozioni |
| F0 media, escursione in semitoni, variazione | pYIN/YIN con F0 tra 120 e 500 Hz (voci di ragazzi) | numpy (YIN in poche decine di righe) o `librosa.pyin` | media; soffre di rumore e compressione | intonazione piatta / variata |
| Volume relativo e variazione | RMS in dB, solo **dentro** la sessione | numpy | bassa in assoluto (distanza dal microfono, guadagno automatico) | calo di voce a fine frase |
| Jitter, shimmer, HNR | periodo per periodo | Praat/parselmouth | bassa su telefono; sono indici clinici di qualità vocale | **non servono** qui |

Librerie:

| Libreria | Licenza | Wheel aarch64 / win_arm64 | Note |
|---|---|---|---|
| numpy, Silero VAD ONNX, onnxruntime | BSD / MIT | sì / sì (già in Calliope) | basta per pause, tempi, volume, YIN |
| librosa 1.0.0 (08/2026) | ISC, puro Python | dipende da numba/llvmlite (sì/sì), scipy e scikit-learn (sì/sì), **soxr (sì / no)** | ok sulla DGX; sul portatile ARM no senza soxr |
| praat-parselmouth 0.4.7 | **GPL-3.0** | **no** aarch64 (solo x86) / no | da escludere |
| opensmile 2.6.0 (eGeMAPS) | **audEERING Research License**: non commerciale («personal home use» ammesso) | sì / no | riferimento utile (eGeMAPS è l'elenco minimo standard), non come dipendenza |
| amfm_decompy (YAAPT) | puro Python, licenza non dichiarata su PyPI | — | da evitare finché la licenza non è chiara |

Registrazione: per questo strumento la pagina del telefono dovrebbe chiedere il microfono con
`autoGainControl`, `noiseSuppression` ed `echoCancellation` spenti (la «Prova il microfono» del
telefono registra già le due versioni): con il guadagno automatico acceso volume e dinamica non
vogliono dire niente.

## 4. Norma

### 4.1 AI Act (Reg. UE 2024/1689)

**Testo certo** (italiano, GU L del 12/07/2024):

- **Art. 5(1)(f)**, vietati: «l'immissione sul mercato, la messa in servizio per tale finalità
  specifica o l'uso di sistemi di IA per inferire le emozioni di una persona fisica nell'ambito
  del luogo di lavoro e degli istituti di istruzione, tranne laddove l'uso del sistema di IA sia
  destinato a essere messo in funzione o immesso sul mercato per motivi medici o di sicurezza».
  Si applica dal **2/02/2025**.
- **Art. 3(39)**: «sistema di riconoscimento delle emozioni»: «un sistema di IA finalizzato
  all'identificazione o all'inferenza di emozioni o intenzioni di persone fisiche sulla base dei
  loro dati biometrici». **Art. 3(34)** «dati biometrici»: dati personali ottenuti da un
  trattamento tecnico specifico relativi alle caratteristiche fisiche, fisiologiche o
  comportamentali. Il considerando 15 elenca tra queste «la voce, la prosodia».
- **Considerando 18**: emozioni «quali felicità, tristezza, rabbia, sorpresa, disgusto,
  imbarazzo, eccitazione, vergogna, disprezzo, soddisfazione e divertimento»; non comprende stati
  fisici (dolore, affaticamento) né «la semplice individuazione di espressioni, gesti o movimenti
  immediatamente evidenti, a meno che non siano utilizzati per identificare o inferire emozioni»,
  per esempio «caratteristiche della voce di una persona, ad esempio una voce alta o un
  sussurro».
- **Considerando 44**: «serie preoccupazioni in merito alla base scientifica»; «limitata
  affidabilità, la mancanza di specificità e la limitata generalizzabilità»; il divieto nasce
  dallo «squilibrio di potere nel contesto del lavoro o dell'istruzione».
- **Art. 2(10)**: il regolamento «non si applica agli obblighi dei deployer che sono persone
  fisiche che utilizzano sistemi di IA nel corso di un'attività non professionale puramente
  personale».
- **Art. 50(3)**: i deployer di un sistema di riconoscimento delle emozioni «informano le persone
  fisiche che vi sono esposte in merito al funzionamento del sistema» e trattano i dati secondo il
  GDPR; per l'art. 50(5) l'informazione va data in modo chiaro «al più tardi al momento della
  prima interazione o esposizione». Si applica dal **2/08/2026**.
- **Allegato III, punto 1(c)**: alto rischio i sistemi «destinati a essere utilizzati per il
  riconoscimento delle emozioni». Con l'Omnibus digitale sull'IA (Reg. UE 2026/1744, in vigore dal
  27/07/2026, secondo fonti secondarie: testo in GU non letto) gli obblighi dell'allegato III
  slittano al **2/12/2027**; art. 5 e art. 50(3) non cambiano.

**Linee guida della Commissione** (C(2025) 5052 final, 29/07/2025; la bozza approvata il
4/02/2025 era C(2025) 884), § 7 e § 2.5.4:

| Punto | Cosa dicono | Per noi |
|---|---|---|
| (255) istituti di istruzione | pubblici e privati, ogni età, anche online; di solito accreditati, rilasciano un titolo | casa non è un istituto |
| (255) esempio | «Un'app che usa il riconoscimento delle emozioni per imparare una lingua online **fuori da un istituto di istruzione non è vietata**. Se invece è l'istituto a richiederne l'uso, è vietata.» | Calliope a casa, scelta dalla famiglia: fuori dal divieto; **se la scuola lo chiede o ne riceve i risultati: dentro** |
| (255) esempio | un sistema d'esame che rileva «emotional arousal and anxiousness» è vietato | arousal/agitazione = emozione |
| (248) | il divieto non si aggira parlando di «atteggiamenti» | «sicurezza» non è un nome neutro |
| (249) | osservare un sorriso non è riconoscimento; concludere «è felice» sì | «pause più lunghe del solito» no; «eri agitato» sì |
| (251) | il testo scritto non è biometrico (non è riconoscimento); la voce sì | l'analisi del solo contenuto della risposta resta fuori |
| (254) analogia | sul lavoro, per **addestramento personale** è ammesso «se i risultati non sono condivisi» con chi valuta e non incidono sul rapporto | la stessa logica del potere: al ragazzo sì, a chi lo giudica è il punto delicato |
| (257) | benessere generale, stress, motivazione non rientrano nell'eccezione medica | niente «per il suo bene» come scappatoia |
| § 2.5.4, (35) | un sistema per uso personale **resta ad alto rischio** e deve rispettare l'AI Act; esente è solo il deployer privato | i genitori sono esenti; chi fornisce il sistema no |
| § 2.5.5, (36) | l'esenzione dell'open source non vale per i sistemi ad alto rischio, art. 5 e art. 50 | pubblicare Calliope con questo modulo = obblighi da fornitore |

**Interpretazione** (incerta, da far verificare se si pubblica):

- In casa, scelto dai genitori, **non è vietato**. L'art. 50(3) non obbliga i genitori (art.
  2(10)), ma la trasparenza verso il ragazzo è comunque la scelta giusta (GDPR, ONU, fiducia).
- Dario non è solo «utente»: scrive il sistema e lo mette in servizio. Per un uso solo della sua
  famiglia è difficile immaginare chi gli chieda la conformità di un sistema ad alto rischio, ma
  il testo non lo esclude. **Pubblicato** (la pubblicazione su GitHub è nella pagina dei lavori)
  lo è a tutti gli effetti, dal 2/12/2027, open source o no: va tenuto fuori dalla versione
  pubblica o non fatto.
- Restare sulle **misure oggettive** (considerando 18: caratteristiche evidenti della voce non
  usate per inferire emozioni) toglie il problema alla radice.

### 4.2 GDPR e diritto italiano

| Norma | Testo / punto | Lettura |
|---|---|---|
| GDPR art. 2(2)(c), cons. 18 | non si applica al trattamento «per l'esercizio di attività a carattere esclusivamente personale o domestico» | Calliope in famiglia: in gran parte fuori. Attenzione: Calliope gira sulla DGX **in ufficio**; l'esenzione guarda alla natura dell'attività, non al luogo, ma se l'azienda avesse accesso a dati o macchina diventerebbe discutibile |
| GDPR art. 4(14), art. 9 | biometrici solo se «consentono o confermano l'identificazione univoca» | l'inferenza d'emozione in sé non è biometrica per il GDPR (le linee guida AI Act lo notano, nota 160); un'«ansia» dedotta potrebbe essere letta come dato sulla salute (art. 9) |
| EDPB, linee guida 02/2021 sugli assistenti vocali (07/07/2021) | l'impronta vocale è dato biometrico; cita i brevetti che deducono «stato di salute ed emotivo» dalla voce come esempio di uso oltre le attese | trasparenza e scopo limitato |
| GDPR art. 8; Codice privacy art. 2-quinquies | consenso ai servizi della società dell'informazione dai 14 anni in Italia | non è un servizio offerto, ma la soglia è la stessa della legge 132 |
| **Legge 132/2025, art. 4(4)** (in vigore dal 10/10/2025) | sotto i 14 anni accesso all'IA e trattamento dei dati «richiedono il consenso di chi esercita la responsabilità genitoriale»; **dai 14 anni** il minore «può esprimere il proprio consenso» se le informazioni sono «facilmente accessibili e comprensibili» | per gli adolescenti la parte emotiva va accettata **da loro** |
| Garante, provv. n. 342 del 14/05/2026 (riportato dalla stampa specializzata, testo non letto) | avvertimento a un'azienda che deduceva stress ed emozioni dei lavoratori **dal testo** delle chat | il Garante richiama l'AI Act anche per il testo; mostra l'attenzione alla materia |
| Linee guida MIM sull'IA a scuola con parere del Garante (09/2025) | vietate le pratiche di riconoscimento delle emozioni dall'analisi di volti ed espressioni degli studenti | conferma: niente collegamenti con la scuola |
| ONU, Commento generale n. 25 (2021), § 75–76 | sorveglianza digitale dei bambini non «routinaria, indiscriminata o all'insaputa del bambino»; il monitoraggio dei genitori «proporzionato e conforme allo sviluppo delle capacità del bambino»; § 68 elenca le **emozioni** tra i dati da proteggere | il ragazzo deve sapere; più grande è, più decide |

## 5. Proposta per Calliope

### 5.1 Al ragazzo o al tutore

| | **A. Al ragazzo** (riscontro suo) | **B. Solo al tutore** (report delle sessioni) | **C. Mista** (raccomandata, se si fa) |
|---|---|---|---|
| Chi vede | il ragazzo, a fine prova | il genitore, andamento per sessione e per domanda | il ragazzo tutto il suo; il tutore solo l'andamento per sessione |
| AI Act | non vietato; 50(3) non obbliga la famiglia; è il caso «addestramento personale, risultati non condivisi» (254) | non vietato in casa, ma riproduce lo **squilibrio di potere** che motiva il divieto (cons. 44) | come A per il ragazzo; il tutore vede meno |
| GDPR / L. 132 / ONU | ok con l'informativa; dai 14 anni il suo consenso | dai 14 anni serve il suo consenso; sotto, deve **saperlo** (CG 25 § 75) | stesse condizioni, più facili da rispettare |
| Pro | autonomia, nessuna sorveglianza, utile subito («la prossima volta respira prima di rispondere») | un adulto contestualizza; vede tendenze lunghe | il ragazzo resta padrone del suo dato; il genitore ha un segnale senza dettaglio |
| Contro | un errore del modello può ferire («sei ansioso») o diventare un'etichetta; sotto i 10–11 anni difficile da capire | **sorveglianza percepita**, fiducia; errori presi per veri («il computer dice che è ansioso»); il ragazzo potrebbe recitare la calma | più lavoro d'interfaccia |
| Rischio di danno | medio (autostima) | alto (rapporto genitore–figlio, ansia da controllo) | basso–medio |

**Raccomandazione: C**, e solo dopo la fase 1. Il tutore non vede mai valori per frase né per
domanda nella parte emotiva (per domanda solo le misure oggettive, che il ragazzo vede uguali);
l'adolescente vede **lo stesso** report del tutore, sempre; sotto i 14 anni il ragazzo sa che
c'è e cosa misura (frase detta da Calliope prima della prima prova e un riquadro fisso nella
scheda); dai 14 anni si accende solo con il suo «sì», revocabile da lui.

### 5.2 Come dirlo senza fare danni

- **Mai** etichette d'emozione né diagnosi: niente «ansioso», «insicuro», «stressato».
- **Mai** voti o punteggi della parte emotiva; niente classifiche tra fratelli.
- **Sempre** rispetto al proprio solito e con l'incertezza: «La tua voce era più tesa del tuo
  solito in questa prova (misura approssimativa).» invece di «Agitazione 7/10».
- Prima le misure oggettive e il contenuto, poi, se c'è, una frase sola sulla voce.
- Preferire la domanda: «Come ti sei sentito? Le pause sono state più lunghe del solito nelle
  domande di storia.» La sua risposta vale più del modello e va accanto nel report.
- Per il tutore: andamento su più sessioni («nelle ultime 4 prove la voce è più distesa»), con
  l'avvertenza fissa «misura sperimentale, sbaglia spesso, non è una valutazione di tuo figlio».
- Nessun avviso automatico al tutore basato sulle emozioni (il rilevatore di pericolo dei minori
  resta quello sul contenuto, già esistente).

### 5.3 Dati

Audio intero tenuto solo fino alla valutazione (come già nell'idea dello strumento), poi
cancellato; delle emozioni restano solo i numeri aggregati per sessione; niente nel registro dei
turni né in `conversazioni.db`; mai all'agente né fuori casa; tutto sulla macchina di casa, senza
cloud; cancellabili dal ragazzo (dai 14) e dal tutore. Mai trasmessi a scuola.

### 5.4 Piano a fasi

| Fase | Cosa | Costo | Uscita |
|---|---|---|---|
| **0** | Strumento con contenuti + misure oggettive (§ 3) rispetto alla base personale + autovalutazione «come ti sei sentito?» a fine prova. Niente modelli d'emozione | piccolo, nessuna dipendenza nuova (numpy, VAD, tempi di Whisper) | il grosso del valore, fuori dalla definizione dell'AI Act |
| **1** | Prova chiusa sulle voci vere (solo se Dario decide): emotion2vec+ base e audEERING (ONNX, solo arousal) sulle sessioni registrate con accordo, autovalutazioni e un ascoltatore cieco; metriche del § 2.3, soglia fissata prima. Niente mostrato a nessuno | ~1 settimana con 20–30 sessioni; download di ~0,4–2 GB di modelli (da autorizzare) | numeri: si accende o no |
| **2** | Solo se la fase 1 passa: arousal per sessione, variante C, frasi del § 5.2, interruttore del tutore + consenso dai 14 | piccolo | parte emotiva attiva in casa |
| — | Mai: categorie, valenza, «sicurezza» dalla dominanza, valori per frase, versione pubblicata, uso chiesto dalla scuola | | |

## 6. Decisioni per Dario

1. **Si fa la parte emotiva?** Raccomando di partire dalla fase 0 (senza) e decidere dopo.
2. Se sì: **solo arousal** («attivazione/tensione della voce») o anche «sicurezza»? Raccomando
   solo arousal: la dominanza è la dimensione più debole anche in inglese sugli adulti.
3. **Chi vede**: variante C (raccomandata), A o B.
4. **Età minima**: suggerisco dagli 11 anni (fascia «ragazzi»), con il consenso del ragazzo dai 14
   come da legge 132.
5. Autorizzare la **fase 1** (registrazioni con accordo, download di un modello, ~1 settimana) e
   la soglia di successo.
6. **Pubblicazione**: il modulo emotivo resta fuori dalla versione pubblica di Calliope.
7. Registrazione senza guadagno automatico né soppressione del rumore per lo strumento (vale
   anche per le misure oggettive).

## Fonti (consultate il 06–07/10/2026)

- Reg. (UE) 2024/1689, testo italiano, GU L del 12/07/2024 (Ufficio delle pubblicazioni, cellar
  `dc8116a1-3fe6-11ef-865a-01aa75ed71a1`): art. 2(10), 3(34), 3(39), 5(1)(f), 50(3), 50(5),
  allegato III; considerando 14, 15, 18, 44.
- Commissione europea, *Guidelines on prohibited AI practices*, C(2025) 5052 final, 29/07/2025,
  [ai-act-service-desk.ec.europa.eu](https://ai-act-service-desk.ec.europa.eu/sites/default/files/2025-08/guidelines_on_prohibited_artificial_intelligence_practices_established_by_regulation_eu_20241689_ai_act_english_ied3r5nwo50xggpcfmwckm3nuc_112367-1.PDF), § 2.5.4–2.5.5, § 7.
- Omnibus digitale sull'IA, Reg. (UE) 2026/1744 (in vigore 27/07/2026): fonti secondarie
  [euaiact.com](https://www.euaiact.com/digital-omnibus-ai) e
  [usercentrics.com](https://usercentrics.com/knowledge-hub/eu-ai-act-high-risk-delay-article-50-transparency-consent/);
  testo in GU non letto.
- Legge 23/09/2025 n. 132, art. 4 (GU n. 223 del 25/09/2025, in vigore dal 10/10/2025), PDF della
  GU via [dirittobancario.it](https://www.dirittobancario.it/wp-content/uploads/2025/09/Legge-23-settembre-2025-n.-132.pdf).
- EDPB, *Guidelines 02/2021 on virtual voice assistants*, v2.0, 07/07/2021,
  [edpb.europa.eu](https://www.edpb.europa.eu/system/files/2021-07/edpb_guidelines_202102_on_vva_v2.0_adopted_en.pdf).
- Garante privacy, provv. n. 342 del 14/05/2026 (stress dei lavoratori), da
  [ecnews.it](https://www.ecnews.it/lavoro/rapporto-di-lavoro/gestione-del-rapporto/ia-e-stress-dei-lavoratori-interviene-il-garante-privacy/)
  e [fiscal-focus.it](https://www.fiscal-focus.it/quotidiano/il-quotidiano/articoli-lavoro/stop-del-garante-all-ia-che-analizza-lo-stress-dei-dipendenti,3,185043) (30/05/2026); linee guida MIM sull'IA a scuola,
  [lentepubblica.it](https://lentepubblica.it/scuola/uso-ia-scuole-garante-privacy-linee-guida-ministeriali/) (25/09/2025).
- Comitato ONU sui diritti dell'infanzia, Commento generale n. 25 (2021), CRC/C/GC/25, § 68,
  75–76 (copia [unicef.dk](https://www.unicef.dk/wp-content/uploads/2026/08/gc-no.-25.pdf)).
- Ma et al., *emotion2vec*, arXiv 2312.15185 (12/2023; ACL Findings 2024), tab. 4;
  [repository](https://github.com/ddlBoJack/emotion2vec) (MIT; emotion2vec+ 05/2024);
  [scheda emotion2vec_plus_large](https://huggingface.co/emotion2vec/emotion2vec_plus_large)
  (ultima modifica 24/06/2024); [FunASR MODEL_LICENSE](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) v1.1.
- Ma et al., *EmoBox*, Interspeech 2024, tab. 4–5,
  [isca-archive.org](https://www.isca-archive.org/interspeech_2024/ma24b_interspeech.pdf).
- Wagner et al., *Dawn of the transformer era in SER*, IEEE TPAMI 09/2023, arXiv 2203.07378;
  [scheda audEERING](https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim)
  (CC-BY-NC-SA 4.0, ONNX su Zenodo 10.5281/zenodo.6221127).
- Sfida *SER in Naturalistic Conditions*, Interspeech 2025, [classifica](https://lab-msp.com/MSP-Podcast_Competition/IS2025/)
  e [articolo riassuntivo](https://www.isca-archive.org/interspeech_2025/naini25_interspeech.html).
- Triantafyllopoulos et al., *INTERSPEECH 2009 Emotion Challenge Revisited*, arXiv 2406.06401
  (06/2024), tab. 2.
- Feng et al., *Vox-Profile*, arXiv 2505.14648 (05/2025); schede HF di `3loi/…`, `tiantiaf/…`,
  `speechbrain/emotion-recognition-wav2vec2-IEMOCAP`, `FunAudioLLM/SenseVoiceSmall` (API HF,
  06/10/2026).
- Catania, Wilke, Garzotto, *Emozionalmente*, IEEE TASLP 2025; [OpenSLR 161](https://openslr.org/161/)
  (CC-BY 4.0); Zenodo 6569824. Costantini et al., *EMOVO*, LREC 2014. *DEMoS*, Zenodo 2544829
  (accesso ristretto).
- *Automatic Detection of Stress from Speech in the TSST*, arXiv 2607.00986 (07/2026);
  Teferra et al., JMIR Mental Health 2022;9(7):e36828.
- PyPI JSON (06/10/2026): librosa 1.0.0, numba 0.68.0, llvmlite 0.50.0, soxr 1.1.0, scipy 1.18.1,
  scikit-learn 1.9.1, praat-parselmouth 0.4.7, opensmile 2.6.0 (con la
  [licenza audEERING](https://github.com/audeering/opensmile/blob/master/LICENSE)), soundfile
  0.14.0.
