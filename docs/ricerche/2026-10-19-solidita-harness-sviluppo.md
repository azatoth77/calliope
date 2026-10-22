# La solidità dell'harness dello sviluppo (19/10/2026)

Analisi in sola lettura dell'harness intorno all'agente della modalità sviluppo (Qwen3.6-35B-A3B
su vLLM, ragionamento acceso), con un solo obiettivo: renderlo più **solido**. Cinque letture
parallele: il ciclo e gli strumenti (`agenti/ciclo.py`, `sandbox.py`, `remoto_openai.py`,
`tools/dialogo.py`), il contesto e la memoria (`contesto_lavoro.py`, `ripresa.py`,
`servizio.py`), le fasi e la verifica (`sviluppo.py`, `tools/sviluppo.py`, `accettazione.py`,
`riproduzione.py`, `sonde.py`, `estensioni/servizio.py`), il contratto e gli scheletri
(`estensioni/prompt.py`, `contratto.py`, `manifesto.py`, `motore_gioco.js`, `scheletri.py`,
`fumo_js.mjs`, `test_js.mjs`) e il catalogo dei 44 fallimenti veri dal 02/10 al 18/10
(`docs/aree/agenti-estensioni.md`, `giochi.md`, ricerche, issue). Le righe sono quelle di main
a `9609d72a`. I punti segnati **(verificato)** li ho riletti nel codice; quelli segnati
**(probabile)** vanno confermati con una prova prima di correggerli.

## 1. La tesi

L'harness è **forte alla fine** (la consegna: test rifatti due volte, esempi in sola lettura,
prova di fumo, riproduzione, ricollaudo) e **debole durante il giro**: il codice calcola molto
(impronte dei file, firme degli errori, conti dei test, giri uguali) ma quasi nulla di questo
arriva all'agente; ciò che gli arriva è prosa, che si accumula e a volte si contraddice.

Il catalogo dei casi veri lo conferma con i numeri: su ~93 contromisure introdotte dal 04/10,
quelle **per costruzione** (il codice che rende impossibile l'errore) hanno chiuso la loro
famiglia (il `require` in gioco.js, la doppia codifica degli URL, i falsi «fatto» del
convertitore); quelle **in prosa** (spinte e istruzioni) si sono ripresentate in forma nuova
(il giro a vuoto il 04, 08, 11, 12, 14 e 18/10; la consegna mancata 32 → 36 → 37 → 39). L'unica
istruzione misurata efficace è una regola netta data all'inizio (`DATI_PROPRI`, 5/5). Il punto
debole che torna sempre sono **i test scritti dall'agente**: confermano i suoi errori (codice
fiscale, CalliopeFinta permissiva, test senza seme) o lo bloccano quando sono sbagliati (porte
del 14/10, tris del 18/10, #174).

Ci sono poi **porte che si aprono da sole**: punti in cui un modello piccolo, senza volerlo,
supera un controllo senza aver fatto il lavoro. Sono le prime da chiudere, perché costano poco
e oggi rendono falsi i numeri del banco.

## 2. Principi di un harness solido (il metro di questa analisi)

1. **Il codice possiede la verità, il modello propone.** Lo stato del lavoro (file, impronte,
   esito dei test, tentativi) si calcola dal mondo, non dalla trascrizione né dal diario del
   modello.
2. **Ogni segnale che il codice calcola arriva all'agente**, nel risultato dello strumento che
   l'ha prodotto, in forma fattuale («questo stato è identico a quello del passo 7, che dava
   E»), non in un messaggio di rimprovero a parte.
3. **Vocabolari chiusi e un solo predicato.** Gli esiti fuori dall'elenco sono un errore;
   «consegnabile» è una funzione sola, usata da `esegui_test`, dalla consegna, dal tetto e
   dalla tappa.
4. **Strumenti onesti e idempotenti.** Un'uscita troncata si dice; rifare un test senza aver
   cambiato nulla restituisce «niente è cambiato»; un errore dice cosa fare.
5. **La verifica non è modificabile da chi è verificato.** I test che decidono la consegna non
   li scrive né li cambia lo sviluppatore.
6. **Meno testo, file di partenza invece di prosa.** Una regola per argomento, un prompt per tipo
   di lavoro; ciò che si può dare come file già verde non si descrive.
7. **Una scala di escalation deterministica**: nota nel risultato → restrizione degli strumenti
   → ripartenza da stato → revisore a contesto pulito → tappa alla persona. Ogni gradino ha la
   sua soglia e il suo nome di regola nel registro.
8. **Anche i rilevatori sono codice da provare**, con casi contrari presi dai registri veri: tre
   volte (11/10, 13/10, 18/10) i conti dell'harness erano falsi e hanno detto cose sbagliate
   all'agente o alla persona.

## 3. I buchi, per area

Gravità: **C** critico (una porta che si apre da sola o un giro senza uscita), **A** alto, **M**
medio. Tipo della correzione: **P** per costruzione, **R** retroazione all'agente, **S** prosa.

### 3.1 Integrità delle porte

| # | G | Buco | Dove | Correzione | T |
|---|---|---|---|---|---|
| 1 | C | `consegna(esito="completato")` salta piano, `controlla`, test e riproduzione e diventa «fatto»: `_forma` lascia passare i valori fuori dall'enum («decide il tool») e il ciclo controlla solo `== "fatto"` **(verificato)** | `tools/dialogo.py:146`, `ciclo.py:1390-1435`, `1566` | Per gli strumenti dell'agente un valore fuori dall'enum è un errore con l'elenco; nel ciclo «fatto» è tutto ciò che non è `mancano_dati` o `impossibile` | P |
| 2 | C | Dopo una spinta, una passata di sola prosa con `scritti > 0` vale come consegna «fatto» (le scuse «Hai ragione, correggo il test» chiudono il lavoro) | `ciclo.py:1315-1327` | Una passata senza chiamate non è mai una consegna: risposta fattuale («nessuno strumento chiamato; file invariati dall'ultimo test»), tappa dopo N di fila | P |
| 3 | C | Dopo `RIMANDI_MAX` = 2 la consegna con i test rossi è accettata, e lo sviluppo passa al collaudo; dopo 3 rifiuti di `controlla` l'errore è ignorato, e `rifiuti_consegna` si perde a ogni ripresa | `ciclo.py:768`, `1404-1416`, `1544`, `1694` | Consegna rossa = tappa con il verdetto (test o codice), mai «fatto»; i contatori nel contesto salvato | P |
| 4 | A | La riproduzione di una correzione vale con **qualunque** fallimento sulla versione di prima, anche un `ImportError` di una funzione nuova **(verificato)** | `riproduzione.py:120-155` | Richiedere un fallimento di asserzione (o di un test che importa solo ciò che c'era prima) | P |
| 5 | A | Il ricollaudo `va()` accetta qualunque esito diverso da prima senza errore («non trovato» nuovo = va) | `sonde.py:591` | Esito pieno e coerente col caso della persona. **Fatto il 22/10 (#223)**: risultati vuoti senza nessuna frase, per un caso che prima dava un dato o un errore, non vanno (`ricollaudo_esito_vuoto`); una frase negativa è un dato (seconda revisione della PR #232). Scelta di principio (principio 10, terza revisione): il caso originale, prima un errore e poi «Non ho trovato la fiera di Borgo Alto.», adesso va, perché è un dato detto e lo giudicano il modello e la persona; «vuoto» con una regola stretta (quarta revisione): una raccolta vuota o un None e nient'altro, salvo l'eco sulla stessa chiave e, accanto alla raccolta, contatori a zero e metadati | P |
| 6 | A | «Tutto verde» non vuol dire consegnabile: `manifesto_non_valido` non è `controlla_consegna` (nome preso, file della scheda, `require` in logica.js) | `ciclo.py:445-476`, `estensioni/prompt.py:125-149` | Il predicato unico «consegnabile» dentro `esegui_test` | P |
| 7 | A | Test indeboliti o sostituiti invisibili: `test_tolti` confronta solo con l'ultima tappa e per Python verde non ha i nomi; asserzioni tolte o `skipTest` non si vedono | `ciclo.py:2617-2653` | Fotografia dei test alla prima esecuzione; conto delle asserzioni; avviso nel risultato di `scrivi_file` su un file di test. **Fatto il 22/10 (#223)**: `agenti/fotografia_test.py`, la fotografia dai test scritti dall'agente, il fatto in `esegui_test`, la nota in `scrivi_file`/`modifica_file`, la riga sulla scheda; a voce solo il fatto neutro su uno stesso test | P+R |
| 8 | A | Nelle correzioni di un gioco `accettazione.test.js` torna nei file della versione senza sola lettura; per i programmi gli esempi si perdono (`copia_in` esclude i file in sola lettura) **(probabile)** | `estensioni/servizio.py:1070`, `sandbox.py:762`, `servizio.py:1452-1455` | La suite di accettazione fuori dai file della versione, rimessa in sola lettura a ogni lavoro | P |
| 9 | M | Tutti gli esempi di accettazione sono visibili: `esegui` può restituire valori scritti a mano per quei dati | `accettazione.py` | Una parte degli esempi tenuta da parte ed eseguita solo alla consegna | P |
| 10 | M | Revisione e attivazione anche con zero collaudi ed esempi «non_fatta» | `tools/sviluppo.py:1652`, `servizio.py:1412` | Almeno una prova eseguita, o la ragione detta e confermata. **Fatto il 22/10 (#223)**: «Vado avanti lo stesso?» in sospeso verso `sviluppo_passo` avanti, per la revisione e l'attivazione | P |

### 3.2 Retroazione: ciò che il codice sa e l'agente no

| # | G | Buco | Dove | Correzione | T |
|---|---|---|---|---|---|
| 11 | C | Il ritorno a uno stato già visto (A-B-A-B) è rilevato da `novita_file` e la firma dell'errore già vista da `errori_test`, ma alimentano solo `senza_novita` per la voce alla tappa | `ciclo.py:1460`, `2598-2611`, `servizio.py:366-368` | Nel risultato di `scrivi_file`/`modifica_file`: «identico al passo N, che dava E»; impronta dell'**intera cartella** → esito dei test | R |
| 12 | A | JSON degli argomenti rotto o troncato diventa `{}` in silenzio; l'agente riceve «manca percorso, contenuto» e riprova uguale; `finish_reason` non si legge; `thinking_token_budget` rifiutato si toglie senza dirlo | `remoto_openai.py:228`, `324-331` | «La tua uscita è stata troncata a max_tokens: scrivi in pezzi o usa modifica_file»; log quando il budget cade | R |
| 13 | A | `esegui_test` rifatto senza cambiare nulla si riesegue sempre, senza nota | `ciclo.py:62`, `2037` | Idempotente sull'impronta della cartella: «nessun file è cambiato dal passo N, l'esito è quello» | P |
| 14 | M | Letture in tondo non contate: la deduplica vale solo nella passata; `leggi_file` con `riga` esce prima del conto; `da_carattere` nell'impronta azzera il conto | `ciclo.py:1361`, `2217-2240` | Conto per file e impronta del contenuto, non per argomenti | P |
| 15 | M | `modifica_file`: «vecchio non trovato» non mostra cosa c'è davvero lì; ambiguo non dice dove; `vecchio == nuovo` riesce e azzera `test_verde` | `ciclo.py:1952-1976` | Le righe vere intorno, le posizioni delle occorrenze, rifiuto della modifica nulla e della modifica inversa di una precedente | P+R |
| 16 | M | Il test rifatto alla tappa e i segnali non arrivano all'agente nel giro dopo | `ciclo.py:1704-1730` | Nel blocco di stato (§4) | R |
| 17 | M | Uno strumento sconosciuto non ha `ok: False` né l'elenco dei veri; le chiamate dopo `consegna` nella stessa passata restano senza risposta (storia malformata alla ripresa) | `ciclo.py:1347`, `2047` | Errore con l'elenco; risposta «non eseguita: il lavoro era già consegnato» | P |

### 3.3 Memoria e contesto

| # | G | Buco | Dove | Correzione | T |
|---|---|---|---|---|---|
| 18 | A | Il diario lo scrive il modello e vale come verità («già fatto e già trovato: non rifarlo»); è solo additivo, quindi una decisione e la sua contraria restano entrambe; l'estrattivo mette tra le «decisioni» il testo del modello (scuse e promesse) | `contesto_lavoro.py:495-514`, `531`, `576-580` | Dividere «verificato dal codice» (test, file, impronte, sostituiti a ogni passata) da «note del modello» | P |
| 19 | A | Nessun registro dei tentativi: il ragionamento si butta a ogni passata (giusto per Qwen) e di una modifica sbagliata non resta né il diff né l'errore che ne è seguito; dopo 3 passi il «perché» è perso | `ciclo.py:1295`, `contesto_lavoro.py:548-550` | Registro scritto dal codice: file, impronta prima/dopo, diff breve, errore prima → dopo, ipotesi se data | P+R |
| 20 | A | Tra i giri la conversazione continua: al giro 3 l'agente rivede i passi del giro 1 e un messaggio «Hai un altro giro» per giro; il diario scatta solo al 75 % di 114k token, quindi quasi mai | `ciclo.py:1135-1154`, `servizio.py:676-711` | Ripartenza alla tappa da stato: sistema, compito, blocco di stato, nota della persona, ultimo passo | P |
| 21 | M | Dopo un riavvio un lavoro in corso riparte senza `segnali` (strade escluse, impronte, errori visti) e sovrascrive i `.calliope/passo-N.txt` | `ripresa.py:103-104`, `228-249` | `segnali` e registro dei tentativi in `in_corso.json` per tutti gli stati | P |
| 22 | M | La cache dei prefissi cade col diario (riscrive `messages[1]`), con l'alleggerimento dei messaggi oltre il 50 % (a ogni passata) e con la lista degli strumenti ricalcolata | `contesto_lavoro.py:357-359`, `449-451`, `ciclo.py:1237-1246` | Il blocco di stato in coda, non in testa; strumenti fissi per lavoro | P |

### 3.4 I messaggi dell'harness

| # | G | Buco | Dove | Correzione | T |
|---|---|---|---|---|---|
| 23 | A | Contraddizioni: la nota della terza lettura dice «scrivi la versione corretta con scrivi_file», le altre «usa modifica_file, non riscrivere»; `spinta_riscritture` («correggi solo quel punto») e l'avviso di fine («chiudi») nello stesso messaggio | `ciclo.py:2242`, `ripetizioni.py:149`, `ciclo.py:1047` | Un'unica sorgente delle spinte, al più una attiva, le superate tolte dalla storia. **Fatto il 22/10 (#224)**: `agenti/spinte.py` con i gradini e la `Scala` (al più una spinta per passata, le lasciate contate e non dette, nessuna coppia incompatibile fra i testi; le superate non si tolgono dalla storia, per la cache dei prefissi) | S→P |
| 24 | M | Tono di rimprovero («Ti ho fermato… Non ripensarci», «riscriverlo non serve», «Smetti di pensare»): invita alle scuse; le spinte delle ripetizioni si sommano nello stesso messaggio user | `ripetizioni.py:135`, `ciclo.py:523` | Fatto + passi ammessi, senza giudizio. **Fatto il 22/10 (#224)**: ogni testo «il fatto, poi Passi possibili: …», le parole di rimprovero in un elenco controllato dalla prova; da misurare sul banco le passate di scuse | S |
| 25 | M | `_vuoto_spinta` nomina `piano` e `scarica_esempio` anche dove non esistono | `ciclo.py:523-527` | Generata dagli strumenti del lavoro | P |
| 26 | M | `a_vuoto` e il Limite «ragionato senza strumenti» chiudono uno sviluppo invece di farne una tappa; la finestra dei 5 minuti conta anche l'attesa dell'arbitro per la voce | `ciclo.py:1276`, `1304-1309`, `1598` | Tipo `vuoto` e tappa; tempo senza le attese. **Fatto il 22/10 (#224)**: in uno sviluppo le tappe «vuoto» e «ragionamento» (fuori il «limite» di prima), l'attesa della voce (`attesa_voce_s`) fuori dalla guardia dei minuti; resta dentro il tetto dei minuti del giro | P |
| 27 | M | `senza_novita` è un totale ma è detto come «di fila»; `senza_novita` e `senza_progressi` non agiscono mai nel giro | `ciclo.py:1510`, `2738` | Conti di fila, con un gradino della scala. **Fatto il 22/10 (#224)** per `senza_novita`: di fila (un file mai letto è una novità), gradino `agente_senza_novita` a 6, a voce «di fila»; `senza_progressi` resta un conto delle esecuzioni dei test senza un verde in più, solo per la voce | P |

### 3.5 Contratto e ambiente

| # | G | Buco | Dove | Correzione | T |
|---|---|---|---|---|---|
| 28 | C | Il gioco parte da una cartella vuota: manifesto, logica.js e i due test si ricopiano dal prompt, proprio la parte rotta in #174 | `servizio.py:1397` | File di partenza **già verdi** generati dal codice, coerenti con min e max | P |
| 29 | A | Il prompt promette `g.stato()` con «vincitore», che non esiste; `comandi` è un oggetto, non una lista, e il contratto non lo dice **(verificato)** | `estensioni/prompt.py:90`, `contratto.py:175`, `motore_gioco.js:905-907` | Forma esatta nel contratto (o `vincitore` nell'istantanea) | P |
| 30 | A | `{esito, fase: "fine"}` perde l'esito senza errore (`meta = ris.fase \|\| …`); `dopo` senza esito è ignorato, e la prova di fumo consiglia «fase o dopo: "fine"» **(verificato)** | `motore_gioco.js:812`, `fumo_js.mjs:541` | Errori del motore per le due forme; messaggio di fumo «esito + dopo: "fine", oppure fase: "fine"» | P |
| 31 | A | «Inizia» c'è anche con min < max e parte con gmin giocatori; il caso (Math.random) in logica.js non è detto; `turni` vero di serie non detto | `motore_gioco.js:577`, `745`, `contratto.py:177-190` | Contratto esatto; `caso` passato a nuovaPartita | P+S |
| 32 | A | Il prompt di un gioco è per il 45 % (~12 000 caratteri) roba delle estensioni Python, con contraddizioni («tre file… test_estensione.py c'è già» poi «se è un gioco no»; `urllib` vietato e insieme obbligatorio) | `estensioni/prompt.py:26-83`, `contratto.py:285`, `353-358` | Un prompt per tipo, una regola per argomento, sezioni in ordine | P |
| 33 | M | CalliopeFinta: un'azione senza risposta preparata dà `{"ok": True}` e il KeyError esce in estensione.py; nessun confronto tra le chiamate `calliope.*` e i permessi del manifesto | `_ospite.py:274` | Finta costruita dal manifesto, che nega il non dichiarato con un errore che dice «è il test» **(fatto il 22/10, #228: `ErroreDelTest`, anche per una lettura senza risposta preparata; la regola della porta copiata e confrontata dalla prova)** | P |
| 34 | M | `valida` si ferma al primo errore (tre difetti = tre giri); parole vietate non dette (`_VIETATE`); il consiglio su «cosa_fa» a ogni errore di testo | `manifesto.py:45-51`, `515-517` | Tutti gli errori in una volta; l'elenco nel contratto **(fatto il 22/10, #228: `errori` e un messaggio solo; `PAROLE_VIETATE` nel controllo e nel §3 del contratto; il consiglio su «cosa_fa» solo per la descrizione)** | P |
| 35 | M | `ANTI_INIEZIONE` non è nel prompt delle estensioni, che però ha `scarica_esempio` (HTML qualunque nel contesto) | `estensioni/prompt.py:109-117` | Aggiungerla (anche questione di sicurezza) | S |
| 36 | M | `chiama` del test di partenza è modificabile: riscriverlo con `esegui(dati)` riporta il bug del 13/10 | `scheletri.py:143-171` | Spostarlo in `calliope_estensione.py`, in sola lettura **(fatto il 22/10, #228)** | P |

### 3.6 Ruoli: chi verifica chi

Oggi la separazione esiste già a metà: l'analizzatore della richiesta, il progettista degli
esempi a contesto pulito (`accettazione.py`, il file lo scrive il codice), il revisore dei
requisiti che legge i file e non il riassunto (`requisiti.py:729`). Ma:

- i **test unitari** restano dell'agente, scrivibili sempre, e sono l'unica rete sul
  comportamento oltre agli esempi (casi 5, 17, 18, 24, 27, 41, 42 del catalogo);
- **nessun canale per contestare** un esempio sbagliato: l'agente non può cambiarlo, la consegna
  è rifiutata, dopo 2 rimandi passa rossa, la persona è chiamata a vuoto, e la correzione
  rigenera gli esempi dagli stessi requisiti (stesso errore probabile);
- il giudizio «è il test o è il codice?» lo dà **l'agente su sé stesso** (`CONSEGNA_DOPO_GIRI`),
  oppure la persona alla tappa, quando il codice e un revisore pulito potrebbero darlo prima.

### 3.7 La misura

Il banco (`banco_temperatura.py`) ha 5 ripetizioni per caso: 2/5 contro 3/5 è rumore. Il motivo
di un «limite» sta solo nel log (#9); `tolti`, valori nominati e `calcolo` non sono nella riga.
Il banco dopo `agente-valori` (14/10 sera) non è mai stato girato sulla DGX, e i rimedi di #174
sono provati solo a secco. Ogni correzione qui sotto ha bisogno di un criterio prima di
cominciare, altrimenti si ripete la caccia caso per caso.

## 4. L'architettura a cui tendere

Le idee della conversazione del 19/10 (stato compresso, separazione dei ruoli) entrano qui come
strumenti della solidità, non come fini.

**Lo stato del lavoro**, calcolato dal codice a ogni passata e messo **in coda** all'ultimo
messaggio (la cache del prefisso resta):

- requisiti e file (impronta, righe, cambiati dall'inizio);
- esito vero dei test adesso (conto, firma del primo errore, quali di accettazione e quali
  dell'agente), e se è **consegnabile** (il predicato unico) o cosa manca;
- registro dei tentativi, le ultime 5–6 righe: file toccati, errore prima → dopo;
- strade escluse: stati della cartella già visti con il loro esito;
- note del modello, a parte, dichiarate come tali.

**La ripartenza da stato** alla tappa, dopo due gradini della scala o alla soglia morbida: la
conversazione si butta, restano sistema, compito, stato, ultimo passo e nota della persona.

**La scala** (deterministica, ogni gradino con la sua regola nel registro):

1. nota fattuale nel risultato dello strumento (stato già visto, niente è cambiato, uscita
   troncata);
2. restrizione degli strumenti per una passata (niente `leggi_file` dopo N letture senza
   scritture; `modifica_file` con il campo `ipotesi` dopo un'oscillazione) e, in fase di
   codice, `tool_choice: "required"` (da verificare con la versione di vLLM e il parser del
   ragionamento della DGX);
3. ripartenza da stato;
4. revisore a contesto pulito (lo stesso qwen3.6, schema in uscita: diagnosi, `file:riga`, una
   azione, «il test è sbagliato?»), il cui verdetto apre la conversazione nuova;
5. tappa alla persona, con la sola scelta che resta.

**I ruoli**: un collaudatore che scrive la suite dai requisiti prima del codice (allargando gli
esempi di oggi), tenuta tra le versioni e in sola lettura, con una parte nascosta; lo
sviluppatore che scrive codice e test suoi in più, e contesta un test con `contesta_test(nome,
motivo)`; la contestazione decisa dal codice dove può (contratto, prova di fumo), poi dal
revisore, poi dalla persona; al più 2 contestazioni per giro.

**Deterministico o no.** Il processo esterno sì, e lo è già (fasi, porte, tetti, transizioni in
`sviluppo.py`); questa analisi chiede di renderlo deterministico anche *dentro* il giro (scala,
predicato unico, strumenti idempotenti). La generazione no: con il ragionamento acceso la
decodifica greedy porta proprio alle ripetizioni; la stocasticità serve, e un ricampionamento
della passata fermata è un gradino possibile da misurare.

## 5. Il piano, a passi

Ogni passo è una issue e una PR, con il suo criterio sul banco. L'ordine segue valore / rischio.

0. **La misura prima** (dentro #9, punto 1 allargato il 19/10): nel banco i motivi del limite, i
   test tolti e i gradini scattati; i casi fissi presi dai fallimenti veri (porte, tris2,
   convertitore); 10 ripetizioni per i casi decisivi. Criterio: il banco di main rigirato come
   riferimento.
1. **Porte oneste** (#180; §3.1: 1, 2, 3, 4, 6 e la prova del n. 8 per i giochi; i programmi in
   #10). Piccolo, tutto per costruzione. Criterio: zero
   consegne «fatto» con i test rossi o con l'esito fuori dall'enum; i falsi «fatto» del banco
   restano 0.
2. **Strumenti onesti** (§3.2: 11–15, 17). Criterio: nel banco calano le passate senza novità e
   le riletture; nessun lavoro torna allo stesso stato della cartella più di una volta senza
   la nota.
3. **Il contratto dei giochi** (§3.5: 28–32, 35). File di partenza verdi, errori del motore,
   prompt per tipo. Criterio: `tris2` e porte in ≤ 2 giri (il criterio di #174).
4. **Stato e ripartenza** (§3.3: 18–21, §4). Criterio: token per lavoro riuscito e giri uguali in
   calo, a parità di riuscite.
5. **Le spinte e la scala** (§3.4: 23–27). Le spinte in prosa diventano gradini con nome.
6. **I ruoli** (§3.1: 7–9; §3.6). Il passo più grande, dopo che 1–5 hanno reso leggibili i numeri.
7. **I tetti per profilo dell'agente** (aggiunto il 19/10, prima di #175). Oggi tempo, token al
   minuto, budget del ragionamento per passata e guardia dei minuti senza strumenti sono numeri
   fissi tarati sulla velocità dell'A3B (`agenti_tempo_max_min` 30, `agenti_token_minuto` 5 000,
   `agenti_ragionamento_passata` 8 192, `agenti_minuti_senza_strumenti` 5). Un modello denso da
   27B sulla Spark genera, a stima dalla banda (~273 GB/s, ~15 GB di pesi in NVFP4), 12–15 token/s
   contro i 23–74 dell'A3B: 30 minuti valgono ~23 000 token, una passata di ragionamento pieno
   ~10 minuti, e la guardia dei 5 minuti scatterebbe dentro una passata normale. Senza tetti
   relativi al modello il confronto di #175 misurerebbe il tempo, non la qualità. Proposta: i
   tetti nel profilo dell'agente (come `llm_profilo` per la voce, una riga per cambiare modello)
   o calcolati dalla velocità misurata delle prime passate; le guardie a tempo diventano a token.
   Criterio: lo stesso lavoro con due profili ha lo stesso budget in token, e il banco riporta
   tempo e token per lavoro riuscito.

Da verificare sulla DGX prima del passo 2: quali `top_p` e `top_k` usa davvero vLLM (Calliope
manda solo temperatura e `presence_penalty`); se `tool_choice: "required"` convive con il parser
del ragionamento; se il template di Qwen3.6 ha un'opzione per tenere il ragionamento nella
storia (non verificato, da misurare contro il contesto).

## 6. Cosa non è in questa analisi

La scelta del modello dell'agente (#175): un harness più solido rende quella misura più pulita,
e conviene farla dopo i passi 0–3 e il 7. Un modello più capace non toglie i passi 1, 3 e 6: le
porte, il contratto e la verifica indipendente non dipendono dal modello, e un modello più
capace sa anche aggirare meglio i controlli (casi speciali per gli esempi visibili, test
indeboliti). Rende invece meno necessari i rilevatori che compensano la memoria corta. Il lato voce dello sviluppo (#172).
