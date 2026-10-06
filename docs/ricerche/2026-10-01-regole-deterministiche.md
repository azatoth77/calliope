# Regole deterministiche sul testo: inventario, misure, rischi e benefici (01/10/2026)

*Ricerca del 1° ottobre 2026. Domanda: Calliope ha accumulato regole a espressioni regolari e
confronti di stringhe che stanno prima, dopo o al posto del modello (`gemma4:e4b-it-qat`).
Quali conviene tenere, quali restringere, quali trasformare in spinta o lasciare al modello?
Ogni regola è stata chiamata davvero dal codice (non riscritta) sui dati reali e su frasi
costruite; le alternative con il modello sono state provate su Ollama con il prompt e i tool
veri di Calliope. Gli script di misura non sono nel repository (cartella temporanea della
sessione); i casi contrari da portare in `prove/` sono elencati alla fine.*

## In breve

- **Le regole che sostituiscono il modello (tipo A) sono quelle pericolose, e lo sono per
  pochi motivi ricorrenti**: cercano una parola *dentro* la frase invece di riconoscere la
  frase intera, o confrontano per somiglianza parole che non sono storpiature.
- **L'uscita è il rischio più grave.** `EXIT_WORDS` cerca «chiudi» ovunque: «chiudi le
  tapparelle», «chiudi Excel», «chiudi il cancello» **spengono Calliope**, e il processo
  termina (nessuno la riavvia a voce). `is_short_exit` prende per «esci» anche «spegnilo»,
  «spegnila», «spegni tutto», «senti», «ci riesci?», «alza audio», «togli audio», «esco» e,
  nei dati veri, «Calliope. Chiore sono.» (era «che ore sono»). Sui dati reali le uscite
  giuste sono 24, i falsi 1 (più 1 dubbio); sulle 72 frasi costruite le uscite false sono 14.
  Oggi in casa non succede solo perché la casa è collegata da stamattina.
- **Lo stop prende la prima parola, non la frase.** Con ≤ 3 parole «Ok, aprilo», «Va bene,
  aprilo», «Ok, continua», «Ferma la musica», «Basta musica», «Ferma il timer» vengono
  ignorate in silenzio. Dopo un'interruzione il limite di parole non c'è: «Calliope, grazie,
  e domani che tempo fa?» e «Calliope, basta parlare di Venezia, parlami di Roma» finiscono nel
  nulla. Con **«grazie» in fondo e il nome in mezzo** («Apri il documento, Calliope, grazie.»)
  vale solo «grazie», e la richiesta si perde. Sulle frasi costruite lo stop sbaglia 17 volte
  (9 da sveglia, 6 dopo un'interruzione, 2 con il nome in mezzo) e ne perde 2.
- **Nei dati reali lo stop è scattato 3 volte: 1 giusta, 2 dubbie**, e una è proprio il caso
  segnalato: «Grazie.» dopo «Lo apro?» (01/10) è stato zittito, e Dario ha dovuto risvegliare
  Calliope per dire «apri pure il documento. Grazie.».
- **L'azione in sospeso va data al modello come contesto, non eseguita da una regola.** Con il
  messaggio dei ricordi che Calliope mette prima della domanda, «Sì grazie.» dopo «La apro?»
  apre il file **0 volte su 8** (il modello risponde «Prego»), e «Sì.» fa dire **«Ho aperto il
  documento» senza aprirlo** 3 volte su 3: è il difetto visto a voce il 01/10. Con una riga di
  contesto «azione in sospeso» il modello apre **24 volte su 24** quando la persona acconsente
  e **0 su 27** quando rifiuta o chiede altro, senza nessun «ho aperto» falso. La regola
  «sì/ok/aprila → apri» fa 8/8 sui sì ma apre in 3 casi su 9 sbagliati («Sì, ma prima
  aggiungi la data», «Va bene così, non serve», «Perfetto, grazie»).
- **Le spinte (tipo C) funzionano e costano poco.** `ACTION_PROMISE` e `TOOL_REQUEST` sono
  scattate 2 volte, tutte e due a ragione. Vanno solo ristrette: `ACTION_PROMISE` riconosce
  anche le domande di consenso («Lo apro?», «La apro?»), e senza tool nel turno farebbe aprire
  un file che la persona non ha chiesto.
- **`TextCallGuard` è la regola più utile del progetto**: 8 chiamate su 57 nei dati reali, e
  75 su 88 nelle prove di oggi con ~36 tool. Non ha dato falsi su frasi normali. Da tenere.
- **`mentions_tool` non scatta mai**: gira dopo `clean_for_speech`, che toglie «_», e quindi
  «Uso biblioteca_cerca» arriva al TTS come «Uso bibliotecacerca». È un difetto, non una scelta.
- **Correzioni degli argomenti (tipo B) con falsi trovati a mano**:
  - `agenda.cancel` con «tutti» dentro la frase: «annulla il promemoria di salutare tutti»
    **cancella tutti e 3 i promemoria**;
  - il formato «detto» dei documenti: «una lettera su un foglio intestato» → Excel; «una
    tabella delle spese, non in PDF» → PDF;
  - `parse_amount`: «metti il volume a 30 e alza la luminosità di 30» → luminosità a 30
    invece di +30.
- **«Approfondisci» serve davvero** (senza la ricerca il modello inventa la sorgente del
  Tevere 4 volte su 4: «Monte Prati», «Monte Palmo», «Monte Panico»), ma «controlla» e
  «verifica» con un oggetto («controlla il volume», «verifica se la luce è accesa»)
  la attivano a torto. Il danno è contenuto: frase fissa «Controllo nella biblioteca.» detta
  a sproposito, tool giusto in 7 casi su 8.
- **Proposta di criterio** (sezione «Criteri»): regole deterministiche solo per sicurezza e
  permessi, conversioni, ciò che il modello non vede (audio, trascrizione) e forme chiuse
  riconosciute **per intero**; tutto il resto come spinta o come contesto.

## Dati e metodo

- **Dati reali**: registro dei turni (`registro/*.jsonl`, 24/09–01/10): 181 turni, 168 con
  testo, 114 risposte, 57 chiamate di tool; trascrizioni (`registrazioni/**/trascrizioni.tsv`,
  21/09–01/10): 292 frasi. Le due fonti si sovrappongono in parte. Ogni turno è stato
  **reinstradato con il codice di oggi** (stessa sequenza di `main.py`: nome, stop, uscita,
  approfondisci), per vedere cosa farebbero adesso le regole sulle stesse frasi. I giudizi
  giusto/sbagliato sono miei, leggendo il turno prima e quello dopo; i dubbi sono segnati.
- **Frasi costruite**: 72 frasi naturali di comando, cortesia e chiusura, con l'esito giusto
  scritto prima di provarle. Più 34 parole del lessico vero (dati e prove) che
  `is_short_exit` confonde con una parola d'uscita.
- **Modello**: `gemma4:e4b-it-qat` su Ollama, `num_ctx` 16384, temperatura 0,3, thinking
  spento, prompt di `Config.prompt_for` letto da `calliope.yaml`, tool veri (biblioteca,
  PC finto di `prove/pc_finto.py`, documenti, casa senza Home Assistant). Una passata sola,
  senza eseguire i tool. ~470 richieste in tutto.
- **Limiti**: i dati reali sono pochi e quasi tutti di Dario in prova; nessun turno con la casa
  collegata. Il messaggio dei ricordi nella prova «Lo apro?» usa fatti inventati, non quelli di
  `memoria.db`.

## Inventario

Scatti = sui dati reali, con il codice di oggi. G/S/? = giusti, sbagliati, dubbi. Costruite =
errori sulle frasi costruite che riguardano quella regola.

| # | Regola | Dove | Tipo | Scatti | G/S/? | Costruite | Raccomandazione |
|---|---|---|---|---|---|---|---|
| 1 | `EXIT_WORDS` (esci, arrivederci, addio, spegniti, **chiudi** ovunque nella frase) | `config.py:465`; `main.py:334`, `:482` | A | 15 | 15/0/0 | 8 falsi su 13 | **restringere**: parola d'uscita in testa alla richiesta, senza «chiudi»; uscita = dormire, non chiudere il processo |
| 2 | `is_short_exit` (1–2 parole simili a esci, spegniti, chiudere…) | `wakeword.py:151` | A | 25 | 23/1/1 | 6 falsi su 9; 34 parole del lessico a rischio | **restringere**: somiglianza solo con «esci» (e «addio»), elenco di parole escluse |
| 3 | `STOP_WORDS` da sveglia (≤ 3 parole, prima parola) | `config.py:462`; `main.py:476` | A | 3 | 1/0/2 | 9 falsi, 2 persi | **restringere**: tutte le parole della frase nel lessico di chiusura; mai dopo una domanda di Calliope; il nome non conta |
| 4 | `STOP_WORDS` dopo un'interruzione (nessun limite di parole) | `main.py:398` | A | 4 | 4/0/0 | 6 falsi su 9 | **restringere** come la 3 |
| 5 | Nome in mezzo o in fondo (`find_wake_word` prende ciò che segue il nome) | `wakeword.py:191`, `:216–222` | A | 3 | 1/0/2 | 2 falsi (grazie in fondo) | **restringere**: se dopo il nome ci sono solo parole di cortesia, vale la frase prima |
| 6 | Solo il nome → saluto («Sì?») | `main.py:429` | A | 13 | 13/0/0 | — | tenere |
| 7 | `DEEPEN_WORDS` (approfondisci, sei sicura, dimmi di più, **controlla, verifica**) | `config.py:453`; `main.py:493` | A+C | 0 | — | 6 falsi su 10 | **restringere**: «controlla/verifica» solo da soli o con «lo/la/il dato/bene/meglio» |
| 8 | `SEARCH_PROMISE` → ricerca fatta dal codice e finto «Cerca pure.» nella storia | `config.py:459`; `main.py:570` | B | 1 | 1/0/0 | 1 falso (offerta «posso fare una ricerca») | **trasformare in spinta** come la 9; escludere le offerte |
| 9 | `ACTION_PROMISE` → una spinta «chiama il tool» | `brain.py:103`, `:509` | C | 2 | 2/0/0 | prende «Lo apro?» | **tenere, restringere**: escludere le domande che finiscono con «?» |
| 10 | `TOOL_REQUEST` (apri/cerca/trova + file) → stessa spinta | `brain.py:115`, `:511` | C | 2 | 2/0/0 | — | tenere |
| 11 | `TextCallGuard` (chiamata scritta come testo → chiamata vera) | `brain.py:122`, `:457` | B (forma) | 8 su 57 chiamate | 8/0/0 (1 tool sbagliato scelto dal modello) | 0 falsi su 8 frasi normali | **tenere** |
| 12 | Risposta vuota dopo un tool → la sua `conferma` | `brain.py:519` | B | n.d. | — | — | tenere |
| 13 | `strip_tool_mentions` / `mentions_tool` | `brain.py:557`, `:564`; `main.py:531–536` | B | 0 | — | `mentions_tool` mai vero dopo la pulizia | **correggere**: controllare prima di `clean_for_speech` |
| 14 | `strip_false_citation` («secondo Wikipedia» senza biblioteca) | `tts.py:39`, `:43`; `main.py:539` | B | 3 | 3/0/0 | — | tenere |
| 15 | `parse_amount`: «a N» nella frase rende assoluto il valore del modello | `tools/pc.py:97`, `:111` | B | n.d. | — | 1 falso realistico su 7 | **restringere**: solo con un numero solo nella frase |
| 16 | Formato detto a voce che vince su quello del modello (anche «foglio») | `tools/documenti.py:39`, `:48` | B | 2 | 2/0/0 (uguali al modello) | 5 falsi su 7 | **restringere**: solo «pdf/excel/word» espliciti, non negati; una lettera mai Excel |
| 17 | `agenda.cancel`: «tutt[oie]» ovunque nella richiesta = cancella tutto | `agenda.py:91` | B | 0 | — | 1 falso grave | **restringere** a forma intera, come `liste.remove` |
| 18 | `is_letter` (lettera, disdetta, reclamo, «domanda di») | `documenti/formato.py:508` | B | 3 | 3/0/0 | 1 falso innocuo | tenere |
| 19 | Modifica che dimezza il documento senza «togli/elimina…» → riprova | `documenti/scrittore.py:184` | B → riprova | n.d. | — | — | tenere (è una validazione: il modello rifà) |
| 20 | Spiegazione semplice («in modo semplice», profilo giovane) | `tools/builtin.py:311` | C | 1 | 1/0/0 | — | tenere |
| 21 | Casa: `riscrivi` dopo un «non capito» di HA | `casa/parole.py:333`; `tools/casa.py:128` | B | 0 | — | 1 dubbio su 9 («camera di Matteo» → luce camera) | tenere, **restringere**: niente parole del nome lasciate fuori |
| 22 | Casa: `_DELICATE` sul «non capito» → frase di sicurezza | `tools/casa.py:39`, `:161` | D | 0 | — | 3 su 5 a sproposito («luce del garage») | tenere, **restringere** ai verbi apri/chiudi/sblocca/disattiva |
| 23 | Casa: `_DOMANDA` sul «non capito» → lettura degli stati | `tools/casa.py:36`, `:164` | C | 0 | — | innocua | tenere |
| 24 | Nome reale dopo Primo/Prima (frase intera come nome; «no/non» in testa = rifiuto) | `main.py:369–376` | A | 0 | — | «Mi chiamo Dario» → «Mi Chiamo Dario» | **sostituire con il modello** (`rinomina_interlocutore`) o togliere «mi chiamo/sono» |
| 25 | Arruolamento: annulla/basta/stop in testa; uscite | `main.py:326`, `:333` | A | 0 | — | — | tenere (modalità guidata); caso perso: «Calliope, raccontami…» preso come frase di registrazione 3 volte il 26/09 |
| 26 | `HALLUCINATIONS` e eco del prompt | `config.py:444`; `stt.py:63`, `:67` | E | 2 | 2/0/0 | — | tenere; togliere le 4 voci con il punto, mai confrontate |
| 27 | Secondo stadio della wake word (nome a tolleranza 0,5 o punteggio ≥ 0,9) | `main.py:406–418` | E | 5 ignorate | — | — | tenere |
| 28 | Permessi (`ToolRegistry.call`, proprietari del PC, regole della casa, numero e non percorso in `pc_apri_file`, formule ammesse, frasi fisse di rifiuto) | `tools/registry.py`, `tools/pc.py:465–476`, `casa/regole.py`, `documenti/formato.py` | D | — | — | — | **tenere** deterministici |
| 29 | Conversioni (`tempi.py`, `calcola`, sinonimi di alza/abbassa, ordinali, «ieri/scorso» rifiutati, etichette dei timer) | `tempi.py`, `tools/builtin.py`, `tools/pc.py:152–176` | B (forma) | — | — | — | tenere |

Escluse: le euristiche di ricerca della biblioteca (scelgono passaggi, non decidono cosa fare) e
la pulizia per la voce (`clean_for_speech`, emoji, divisione in frasi).

## Dettagli

### 1. Uscita (regole 1 e 2)

Ogni regola d'uscita è nata da un caso vero: «Addio pesci!» (24/09), «Calliopeici» (26/09),
«Calliope, è sci.» (27/09), «Eschì» (01/10). Il beneficio è reale: **9 uscite su 24 nei dati
sono storpiate** e il modello non le capirebbe mai (con un tool d'uscita: «Eschì» e «È sci» 0
su 6, risponde «non ho capito» o parla del meteo).

Il rischio è cresciuto con la casa e il PC, che hanno portato verbi come «chiudi» e «spegni»:

| Frase | Oggi | Modello con un tool d'uscita |
|---|---|---|
| «Calliope, chiudi le tapparelle» | **esce** | `casa_comando` 2/2 |
| «Chiudi la finestra della cucina» | **esce** | `casa_comando` 2/2 |
| «Chiudi Excel» | **esce** | dice che non può 4/4 |
| «Spegnila» (dopo «in cucina è accesa la luce») | **esce** | `casa_comando` 2/2 |
| «Quando esci dal lavoro ricordami il pane» | **esce** | `promemoria_imposta` 2/2 |
| «Metti nella lista: regalo per l'addio al nubilato» | **esce** | `lista_aggiungi` 2/2 |
| «Ci riesci?», «Alza audio», «Togli audio» | **esce** | 0 uscite (`pc_volume` 4/4 sull'audio) |
| «Senti.», «Spegni tutto», «Spento» | **esce** | non provate |
| «Calliope. Chiore sono.» (dati del 21/09) | **esce** | `chi_parla` (sbagliato ma innocuo) |

La gravità è alta: `break` chiude il processo, e Calliope non si riaccende a voce.

Il modello da solo non basta: senza contesto anche lui esce su «Spegnilo», «Chiudila», «Esco»,
«Uscita» e su «Calliope, basta» (2/2 ciascuna). La strada è la regola ristretta più il modello:

- **regola**: la richiesta (dopo il nome e dopo riempitivi come «allora», «ok», «puoi») deve
  *cominciare* con esci, uscire, arrivederci, addio, spegniti, «vai a dormire»; somiglianza
  solo con «esci», solo per 1–2 parole, escludendo esco, esce, riesci, pesce. Misura: **24 su
  24 uscite reali conservate**, «Chiore sono» non esce più, frasi costruite 68 su 72 (i 4
  restanti: 2 sono la regola 5, 2 sono «Chiudi.» e «Silenzio per favore» lasciate al modello).
- **tool d'uscita per il modello** (facoltativo) per «Calliope, puoi andare», «vai a dormire»:
  2/2 nella prova, ~0,15 s.
- **effetto**: per un server di casa «esci» dovrebbe voler dire *torna a dormire*, non
  *termina*. Un falso diventa allora reversibile.

### 2. Stop (regole 3 e 4) e «grazie»

Lo stop evita un turno del modello e un «Prego, sono qui per aiutarti.» (~0,2 s). Su
«Grazie mille» o «Va bene» il modello non sbaglia: dice una frase inutile, niente di più.
La regola invece sbaglia dove la frase continua dopo la prima parola:

- da sveglia (≤ 3 parole): «Ok, aprilo», «Va bene, aprilo», «Grazie, sì», «Ok, continua»,
  «Va bene, ripeti», «Ferma la musica», «Basta musica», «Stop alla musica», «Ferma il timer»
  → ignorate. Il modello: `pc_media(pausa)` 6/6 sulla musica, ripete la risposta 2/2;
- dopo un'interruzione (nessun limite): 6 frasi su 7 con una richiesta dopo «grazie», «ok»,
  «va bene», «basta», «niente» → perse;
- persi: «Calliope, stop.» e «Calliope, basta.» da sveglia vanno al modello, perché la frase
  comincia con il nome (09-26: «Ho smesso di parlare.»).

Il 01/10 «Grazie.» dopo «Lo apro?» è stato zittito; il turno dopo Dario ha chiesto di aprire.
Dopo una domanda di Calliope, «grazie» è ambiguo: nella prova il modello lo prende per un no
(0/8 aperture), ma almeno risponde.

**Proposta**: stop solo se *tutte* le parole stanno in un lessico di chiusura (ok, va bene,
grazie, mille, basta, così, stop, niente, lascia stare, perfetto, zitta, silenzio, fermati…),
il nome escluso; mai se la risposta precedente finiva con una domanda. Sui dati reali cambia
un solo turno, in meglio («Calliope. Stop.» → stop).

### 3. Nome in mezzo e «grazie» in fondo (regola 5)

Da addormentata vale ciò che segue il nome. Con il nome in mezzo la richiesta si perde:
«Che ore sono, Calliope? Grazie.» → arriva solo «Grazie» → stop; «Che ore sono, Calliope, per
favore?» → al modello arriva «per favore». Nei dati: 3 frasi su 292 con il nome non in testa.
**Proposta**: se dopo il nome ci sono solo parole di cortesia (grazie, per favore, dai), vale
la frase prima del nome, come già succede con il nome in fondo.

### 4. Approfondisci (regola 7)

Nessuno scatto nei dati reali dopo il 26/09. Le prove dicono che serve: con il turno «Il
Tevere è lungo 405 chilometri» e poi «Approfondisci» o «Dimmi di più», senza ricerca il modello
inventa 4 volte su 4; con la ricerca risponde con i dati della voce 4 su 4. Su «Sei sicura?»
senza ricerca dice «ho cercato nella biblioteca» (falso) 2 su 2.

I falsi vengono da «controlla» e «verifica»: «Controlla il volume», «Controlla la batteria»,
«Verifica se la luce è accesa», «Controlla l'agenda di domani», «Controlla se ci sono finestre
aperte», «Dimmi di più sul timer». Con il contesto della biblioteca iniettato il modello chiama
comunque il tool giusto 7 volte su 8 (perde una volta `appuntamenti_elenca`), ma Calliope dice
prima «Controllo nella biblioteca.». **Restringere** è sufficiente.

### 5. «Lo apro?»: regola contro azione in sospeso

Riprodotta la sessione del 01/10 (lettera di disdetta creata con `TextCallGuard`, risultato
del tool con `cosa_fare` che già dice «se chiede di aprirlo chiama pc_apri_file con risultato
1»), più il messaggio dei ricordi che `Brain._memory_message` mette subito prima della domanda.

| Variante | Sì → apre | No → non apre | «Ho aperto» falso |
|---|---|---|---|
| senza messaggio dei ricordi, senza contesto | 15/15 | — | 0 |
| **con i ricordi, senza contesto (com'è oggi)** | **12/24** | 27/27 | **3** (tutti su «Sì.») |
| con i ricordi + «azione in sospeso» subito prima della domanda | **24/24** | **27/27** | 0 |
| regola «sì/ok/certo/aprila in testa → apri» | 8/8 | 6/9 | — |

Il messaggio dei ricordi tra «La apro?» e «Sì» rompe il legame: il modello prende il «sì» per
un ringraziamento o dichiara di aver aperto. È la causa più probabile del difetto del 01/10.
Il contesto lo ripara senza toccare le risposte negative («Dopo», «No grazie», «Non adesso»;
nella prima prova, senza ricordi, «Sì, ma prima aggiungi…» → `documento_modifica` 6/6 e
«Grazie, che ore sono?» → `ora_attuale` 6/6, con e senza contesto).

**Raccomandazione**: azione in sospeso come contesto del solo turno dopo, messa **dopo** i
ricordi (ultima prima della domanda), scritta dal tool che fa la domanda (documenti, ricerca
dei file, guida della casa). La regola resta solo come rete: se la risposta dichiara un'azione
(«ho aperto», «apro») senza tool nel turno, una spinta come `ACTION_PROMISE`. Non eseguire mai
l'azione dalla sola regola.

### 6. Spinte (regole 8, 9, 10)

`ACTION_PROMISE` e `TOOL_REQUEST` sono scattate 2 volte nei dati (27/09: «Per aprire il file
"chiavi" devo prima cercarlo», «Per cercare il file ho bisogno del nome»), entrambe a ragione.
Il costo di un falso è un giro in più del modello. Un caso però è pericoloso: `ACTION_PROMISE`
riconosce «Lo apro?» e «La apro?»; in un turno senza tool la spinta «chiama adesso il tool
giusto» farebbe aprire il file senza consenso. Nella prova «Come si chiama il file?» il modello
non ha fatto la domanda (0 su 4), quindi non è successo; ma va escluso: niente spinta su una
frase che finisce con «?».

`SEARCH_PROMISE` fa la ricerca dal codice e scrive nella storia un «Cerca pure.» che la persona
non ha detto. Riconosce anche le offerte («Posso fare una ricerca, se vuoi.»): lì la decisione
spetta alla persona. Meglio la stessa spinta di `ACTION_PROMISE`, con `biblioteca_cerca` tra i
tool, e niente messaggi finti nella storia.

### 7. Guardia delle chiamate scritte e nomi dei tool (regole 11, 13)

`TextCallGuard` corregge la *forma*, non il significato: esegue la chiamata che il modello ha
scritto. Nelle prove di oggi, con ~36 tool, **75 passate con tool su 88 erano scritte come
testo** (come nella ricerca del 26/09: le chiamate scritte crescono con il numero di tool).
Nessun falso su frasi che cominciano con parole come «Calcola tu…», «Ricorda che…», «Chi parla
è…», «Round 2…». Unico effetto collaterale visto: il 26/09 il modello ha scritto `chi_parla` a
una domanda sul dizionario, e la risposta dopo cominciava con «Chi ti sta parlando è Dario».
Non è colpa della guardia.

`mentions_tool` è codice morto: `clean_for_speech` toglie «_» prima del controllo
(`main.py:531–534`). Va spostato prima della pulizia.

### 8. Correzioni degli argomenti (regole 15, 16, 17, 21, 22)

- **Agenda, «tutti»**: è il falso più grave fra questi, perché cancella dati. La regola guarda
  l'argomento del modello, che riporta le parole della persona. `liste.remove` fa già la cosa
  giusta (forma intera: «tutto», «tutti»); `agenda.cancel` deve fare lo stesso («tutto»,
  «tutti i timer», «tutti i promemoria»).
- **Formato del documento**: nei dati il formato detto coincideva sempre con quello del modello
  (2 su 2). I falsi vengono da «foglio» (foglio intestato, foglio rosa, foglio di calcolo
  della banca) e dalle negazioni. Tenere solo «pdf», «excel», «word» espliciti e non negati.
- **`parse_amount`**: il caso del 27/09 («alza il volume a 50» con azione=alza, valore=50) è
  reale. Il falso realistico è una frase con due comandi e lo stesso numero. Usare l'indizio
  solo se nella frase c'è un numero solo.
- **Casa, `riscrivi`**: parte solo dopo un «non capito» di Home Assistant, e il comando
  riscritto ripassa dalle regole. Il rischio è una stanza sbagliata («la luce della camera di
  Matteo» → `luce camera`). Rischio basso, reversibile.
- **Casa, `_DELICATE`**: fa dire la frase delle serrature a «accendi la luce del garage». Non è
  pericoloso (rifiuta), è solo una spiegazione sbagliata.

## Criteri proposti

Da aggiungere ai principi di progetto in `CLAUDE.md`:

> **Regole deterministiche sul testo.** Il significato di ciò che dice la persona lo decide il
> modello. Una regola sul testo è ammessa solo se:
> 1. è un vincolo di **sicurezza o di permesso** (deve restare deterministica);
> 2. è una **conversione** di un valore già scelto dal modello (durate, date, numeri, ordinali,
>    sinonimi di un enum), oppure ne corregge la **forma** (chiamata scritta come testo);
> 3. riguarda ciò che il modello **non può vedere** (audio, allucinazioni di Whisper, eco del
>    prompt, storpiature note del nome e di «esci»);
> 4. riconosce una **forma chiusa per intero** (tutta la frase, non una parola dentro), breve,
>    misurata sui dati, con un effetto reversibile.
>
> Tutto il resto è una **spinta** (il modello riceve un'indicazione e decide) o un **contesto**
> del turno (azione in sospeso, passaggi della biblioteca). Una regola non scavalca il modello
> per indovinare un'intenzione.

Requisiti per ogni regola nuova o modificata:

- **Casi contrari nelle prove**: almeno 5 frasi naturali che *non* devono farla scattare,
  insieme ai casi veri che l'hanno fatta nascere (in `prove/prova_testo.py`).
- **Forma intera o ancorata**: `fullmatch` o inizio della richiesta dopo il nome, mai `search`
  su tutta la frase, salvo vincoli di sicurezza.
- **Scatto registrato**: ogni regola che decide o corregge scrive il proprio nome nel registro
  dei turni (es. `rec["regole"] = ["stop", "formato_detto"]`). Oggi lo fanno solo `esito`,
  `approfondimento`, `ricerca_promessa` e `da_testo`; le spinte, le correzioni degli argomenti e
  le citazioni tolte compaiono solo in console e non si possono misurare.
- **Effetto reversibile**: se la regola sbaglia, la persona deve poter rimediare a voce (dormire
  e non terminare; chiedere e non cancellare tutto).
- **Confronto con il modello**: prima di aggiungere una regola di tipo A o B, provare la stessa
  frase su Ollama con il prompt vero; se il modello sbaglia meno di 1 volta su 10, niente regola.
- **Origine scritta**: data e frase vera che l'ha fatta nascere, nel commento (lo si fa già).

## Ordine consigliato delle modifiche

| # | Modifica | Guadagno atteso | Costo |
|---|---|---|---|
| 1 | Uscita ristretta (regole 1–2) e uscita = dormire | toglie tutti i falsi trovati (12 costruiti, 1 reale) senza perdere nessuna delle 24 uscite vere; un falso non spegne più il processo | piccolo |
| 2 | Stop ristretto (regole 3–4), mai dopo una domanda di Calliope, nome escluso | recupera «ok, aprilo», «ferma la musica», le richieste dopo un'interruzione; risolve il «Grazie.» del 01/10 | piccolo |
| 3 | Azione in sospeso come contesto dopo i ricordi | «sì» dopo «Lo apro?» da 12/24 a 24/24, niente «ho aperto» falsi; vale anche per «Ho trovato 2 file: quale apro?» | medio (i tool che chiedono devono scrivere la riga) |
| 4 | `agenda.cancel` con «tutti» solo in forma intera | evita la cancellazione di tutti i promemoria | minimo |
| 5 | Nome in mezzo con cortesia in fondo (regola 5) | «Che ore sono, Calliope? Grazie.» non si perde | piccolo |
| 6 | Registro degli scatti di ogni regola | rende misurabile tutto il resto | piccolo |
| 7 | `mentions_tool` prima di `clean_for_speech`; `ACTION_PROMISE` senza domande; `SEARCH_PROMISE` come spinta | niente nomi di tool letti; niente aperture senza consenso | piccolo |
| 8 | Approfondisci, formato detto, `parse_amount`, `_DELICATE`, `riscrivi` ristretti | falsi rari, ma oggi tutti trovati a mano in pochi minuti | piccolo |
| 9 | Nome reale dopo Primo/Prima con il modello | «Mi chiamo Dario» non diventa il nome | piccolo |

## Casi contrari da portare in `prove/prova_testo.py`

Uscita, non deve scattare: «Calliope, chiudi le tapparelle», «Chiudi Excel», «Spegnila»,
«Spegni tutto», «Senti.», «Ci riesci?», «Alza audio», «Calliope. Chiore sono.», «Quando esci dal
lavoro ricordami il pane». Deve scattare: tutte le 24 uscite delle registrazioni (con «Eshi»,
«è sci», «Eschì», «Addio pesci!», «Puoi uscire Calliope»).

Stop, non deve scattare: «Ok, aprilo», «Va bene, ripeti», «Ferma la musica», «Basta musica»,
«Ferma il timer», e dopo un'interruzione «Calliope, grazie, e domani che tempo fa?». Deve
scattare: «Grazie mille», «Va bene», «Basta così», «Calliope, stop», «Calliope, ok grazie».

Approfondisci, non deve scattare: «Controlla il volume», «Verifica se la luce è accesa»,
«Dimmi di più sul timer». Agenda: «annulla il promemoria di salutare tutti» annulla una voce
sola. Formato: «scrivi una lettera su un foglio intestato» resta Word.
