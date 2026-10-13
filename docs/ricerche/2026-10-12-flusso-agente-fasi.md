# Il flusso di lavoro dell'agente di sviluppo a fasi: ricerca (12/10/2026)

*Ricerca scritta, chiesta da chi amministra il 12/10. Nessuna modifica al codice. Fatta sul codice
di `main` a 10b2219. Fonti interne: [agenti-estensioni](../aree/agenti-estensioni.md),
[giochi](../aree/giochi.md), [`2026-10-08-modalita-sviluppo.md`](2026-10-08-modalita-sviluppo.md),
[`2026-10-12-giochi-macchina-stati.md`](2026-10-12-giochi-macchina-stati.md). Dati: i 12 lavori veri
del 12/10 sul gioco «Halloween, le porte magiche» (cartelle di lavoro, consegne con il
`.registro-agente.md`, turni della voce), copiati fuori dal repository perché contengono nomi veri.
Qui si citano solo il codice del gioco e le frasi di chi amministra.*

> **Stato (13/10).** Parte 1 fatta il 12/10 sera (§ 5.1 passi 1, 2 e 5: la correzione da un
> test rosso, `apriGioco`, `esegui_js`, i semi). Parte 2 fatta il 13/10 per le estensioni
> (§ 5.1 passi 3, 4 e 6 in parte): l'analisi prima del codice in una passata a sé, gli esempi
> dato → risultato trasformati dal codice in test di accettazione in sola lettura, al più due
> domande prima di cominciare, «da guardare tu» alla revisione; e la temperatura a 0,6
> (domanda 6). Restano gli esempi per i programmi, i test di accettazione dei giochi (dopo
> la macchina a stati) e la passata con il ragionamento acceso. Dettagli e misure in
> [agenti-estensioni](../aree/agenti-estensioni.md), «Flusso dell'agente a fasi, parte 2».

## La richiesta

Parole di chi amministra: «La logica con cui un LLM raggiunge un risultato dipende soprattutto dalla
qualità del prompt. Le fasi devono essere gestite dall'agente, che deve prima sviscerare la
richiesta e chiudere eventuali buchi d'analisi, poi, deciso che può iniziare lo sviluppo, valutare
che tutto sia ok e che i test coprano le feature e l'analisi. Collaudo e attivazione vengono da sé.
Un loop che si corregge con la macchina a stati domani torna perché non si fa un gioco.» Vale per
programmi, estensioni e giochi.

La proposta da valutare, in cinque passi: (1) analisi dell'agente con le domande sui buchi, fatte a
voce, e sviluppo bloccato finché non sono chiuse; (2) piano dei test di accettazione prima del
codice, almeno uno per requisito, controllato per copertura; (3) sviluppo finché quei test
passano, e nelle correzioni la segnalazione diventa prima un test che fallisce; (4) verifica
requisito per requisito prima della consegna (test presente e verde), altrimenti si continua;
(5) collaudo e attivazione come oggi. Le fasi le guida l'agente con i suoi prompt; il codice
controlla solo gli artefatti di ogni fase.

## In breve

**Cosa è andato storto il 12/10.** Il guasto principale non è stato il prompt dell'agente. È stato
**l'assenza di un controllo esterno sul comportamento visibile**. Dalle 11:05 alle 12:06 il gioco
aveva lo stesso difetto in sei versioni di fila:
- `logica.js` restituiva lo stato con l'esito annidato (`{ ...stato, risultato }`), mentre
  `gioco.js` leggeva `risultato.emoji` e `risultato.punti` al primo livello;
- quindi niente mostro e sempre «Nessun punto!»;
- i test di `logica.test.js` controllavano la forma giusta (`risultato.risultato.emoji`) ed erano
  verdi;
- la prova di fumo non guarda cosa compare;
- la revisione onesta, che legge il codice, diceva «le altre 6 ci sono».

Due correzioni sono state «fatte» senza riprodurre il difetto: una riga cambiata e 20 test di
logica verdi, poi `gioco.js` riscritto da capo con lo stesso errore. Il resto viene da:
- **informazione persa tra la voce e l'agente**: in quattro punti su dodici lavori;
- **requisiti in contraddizione** che nessuno ha segnalato;
- **giri a vuoto** nati dal debug «a mente» dei test, che dipendono dal caso, in JavaScript, senza
  uno strumento per provare un pezzo di codice.

**La proposta regge nella direzione**, ma il suo punto debole è proprio quello che il 12/10 ha
rotto. Se i test di accettazione li scrive lo stesso modello che scrive il codice, nello stesso
contesto, sbagliano allo stesso modo. È il risultato più solido della letteratura: in AgentCoder i
test dello stesso agente sono giusti al 51–61 %, quelli di un agente separato all'88–90 %. Per un
gioco, poi, i test «di logica» non toccano il disegno, cioè dove stava il difetto.

**Raccomandazione**, in ordine (§ 5):
1. **La segnalazione diventa un test rosso prima della correzione**, e il codice rifiuta una
   «correzione» senza un test che prima falliva e dopo passa, o con i file identici. Costa poco ed è
   la parte meglio provata.
2. **Test di accettazione scritti in un contesto separato**, dai soli requisiti, prima del codice,
   e controllati dal codice: ogni requisito ha un test, e ogni test fallisce sullo scheletro.
   - Per i giochi i test guidano **il gioco vero nel DOM finto della prova di fumo**: si tocca una
     porta e si legge cosa compare.
   - La macchina a stati dei giochi rende questi test molto più facili.
3. **Analisi dell'agente con le domande**, ma solo sui buchi che cambiano il risultato:
   contraddizioni tra requisiti e punti «manca». Al più due domande a voce, il resto in «scelte
   fatte» dette nella proposta. In secondo piano, non nel turno della voce.
4. **Uno strumento per provare il JavaScript** (`esegui_js`), semi fissi per il caso nei test, e il
   conto delle passate tenuto fuori dal ragionamento.
5. Fasi e passaggi li tiene **il codice**, come oggi la modalità sviluppo; i prompt dell'agente
   cambiano per fase.

Si misura su un banco di tre casi veri (§ 5.3). Nel profilo da 8 GB oggi l'agente non c'è; se ci
sarà, con un modello piccolo, il flusso deve essere ancora più rigido (§ 5.4).

## 1. Com'è oggi

### 1.1 Chi fa cosa

| Passo | Chi | Dove | Cosa riceve | Cosa produce |
|---|---|---|---|---|
| Richiesta a voce → `compito` | modello della voce (gemma4 26B MoE) | tool `sviluppo_apri` / `sviluppo_passo` (calliope/tools/sviluppo.py) | la frase trascritta e la conversazione | una frase libera, il `compito` |
| Analisi della richiesta | modello dell'agente, **senza ragionamento**, schema chiuso, 10 s | `Analizzatore.analizza` (calliope/agenti/richiesta.py:479, prompt `SISTEMA` a :196) | compito, conversazione recente, lista di controllo per tipo (`PUNTI`, :62: per un gioco giocatori, regole, come si vince, voce) | esito (chiara/vaga/…), al più 2 domande a voce (`MAX_DOMANDE_VOCE`, :96), la specifica in una frase |
| Requisiti | modello dell'agente, senza ragionamento, temperatura 0 | `requisiti.estrai` (calliope/requisiti.py:331, prompt `SISTEMA_ESTRAI` a :84; `chiama` a :232) | la specifica approvata | fino a 12 requisiti con nucleo, `si_puo`, stima |
| Modifiche | idem | `chiedi_modifica`/`applica` (requisiti.py:371, :439) | requisiti numerati e la frase | operazioni sui requisiti; la specifica si rigenera (`specifica_da_requisiti`, :503) |
| Sviluppo | agente (qwen3.6 35B-A3B su vLLM, thinking acceso, temperatura 0,4, presence_penalty 0,5 per le estensioni: calliope/config.py:1053, :1093) | `Agente.codice` (calliope/agenti/ciclo.py:988) | prompt di sistema (`SISTEMA_CODICE`, ciclo.py:486, o `SISTEMA_ESTENSIONE`, calliope/estensioni/prompt.py:9, con contratto e scheletro) e un messaggio «Compito: … Vincoli: …» (ciclo.py:1039) | codice **e** test, nello stesso giro e nello stesso contesto |
| Controllo alla consegna | codice | `controlla_consegna` (estensioni/prompt.py), `_test_falliti` (ciclo.py:1513), ricollaudo | i file | rimanda all'agente se i test falliscono (al più `RIMANDI_MAX` = 2) |
| Revisione onesta | modello dell'agente, passata nuova, senza ragionamento | `requisiti.confronta` (requisiti.py:710, prompt `SISTEMA_CONFRONTO` a :117) | requisiti e **testo** dei file (60 000 caratteri) | fatto / parziale / manca per requisito |
| Correzione | modello della voce sceglie `sviluppo_correggi`; codice compone i vincoli | tools/sviluppo.py:2336, vincoli a :2426–2438 | specifica intera, collaudi falliti, diagnosi, `problema` detto dalla voce | un lavoro nuovo con «Trova la causa, correggi il codice, aggiungi un test con ogni caso che non andava» |

Per un gioco il prompt dice «scrivi logica.js (le regole, funzioni pure), gioco.js (disegno e
tocchi), logica.test.js (node:test)» (estensioni/prompt.py:81–87). I test, quindi, sono **solo
sulla logica**. Il disegno lo prova la prova di fumo (calliope/agenti/fumo_js.mjs, righe 1–7): un
DOM finto, centinaia di tocchi a caso, e un errore JavaScript diventa un test fallito. Non controlla
cosa compare sullo schermo. Lo dice anche a voce: «dice solo che il gioco parte e regge dei tocchi a
caso, non che le regole siano quelle chieste» (`FUMO_TRA`, requisiti.py:841).

L'agente ha questi strumenti: `elenca_file`, `leggi_file`, `scrivi_file`, `modifica_file`,
`esegui_python`, `esegui_test` e `consegna` (ciclo.py:230). Per il JavaScript **non c'è niente per
eseguire un pezzo di codice**: c'è solo `esegui_test` (calliope/agenti/linguaggi.py:97: «niente
esegui_javascript»).

### 1.2 Dove si perde l'informazione

1. **Tra la voce e il `compito`.** Il compito è una frase che gemma riscrive a ogni giro, e il
   codice non la confronta con ciò che la persona ha detto.
2. **Tra la segnalazione e il lavoro di correzione.** Al lavoro arriva il `problema` riassunto dalla
   voce. Non arrivano «è uguale a prima» né la correzione precedente che non ha funzionato.
3. **Dentro il lavoro.** Il diario e i risultati lunghi vanno in `.calliope/passo-N.txt`, cosa
   sensata. Ma l'avviso di chiusura (`AVVISO_FINE`, ciclo.py:81, `_avviso_fine` a :919) entra nella
   conversazione e da lì nel diario e nelle risposte a `sviluppo_chiedi`.
4. **Tra codice e comportamento.** Nessuno esegue il gioco e guarda cosa succede. La revisione
   onesta legge il testo, e un difetto di collegamento tra due file non si vede leggendo.

### 1.3 I dodici lavori del 12/10, ricostruiti

Tempi dell'agente da `lavoro.json`; versioni dei file confrontate con un hash e con `diff`.

| Ora | Tipo | Passate | Test (detto / ricontrollato) | Esito vero | Dove è andata storta |
|---|---|---|---|---|---|
| 04:22 | modifica (porte e punti «li decide il gioco») | 23 | 26/26 | consegnato; la revisione segna «porte a caso, non scelte» come difetto | **specifica**: tre «Con questa modifica: …» accodati, in contraddizione con la prima frase (prima del 12/10 era così; ora la specifica viva lo evita) |
| 07:39 | modifica (porte fisse, sempre le stesse a ogni turno) | 21 | 28/28 detto; **27/28** ricontrollato dal codice | le porte fisse **non sono mai arrivate** all'agente: il compito era la lista di 9 requisiti di prima, con «Scegli punteggio per vincere» accanto a «porte decise dal gioco» | **contesto** (la variante detta a voce, «con le varianti che ti ho detto», non è entrata nel compito) e **test** (un test che dipende da `Math.random` senza seme: verde per l'agente, rosso al controllo) |
| 08:39 | «correzione» | 24 | 28/28 | chi amministra voleva modificare; la voce ha fatto correggere un difetto che l'agente si era diagnosticato da solo (`resettaPorte`) | **contesto**: la richiesta vera (le porte non spariscono) non è arrivata |
| 08:46 | correzione | 9 | 28/28 | `gioco.js` e `logica.js` **identici** al lavoro prima; cambiato solo il manifesto | **nessun controllo** che una correzione cambi qualcosa |
| 11:05 | modifica (sviluppo «nuovo» sull'estensione vecchia) | 23 | 16/16 | il difetto del collegamento nasce qui: `mossa` restituisce lo stato, `gioco.js` legge `risultato.emoji` → «Nessun punto!» sempre | **specifica**: gemma riscrive «scelta dei giocatori, 2, 3 o 4» in «scelta iniziale tra 2, 3 o 4 **porte**», e i requisiti diventano «Scegli 2, 3 o 4 porte» e «Numero porte randomico», in contraddizione. **Test**: solo sulla logica |
| 11:13 | completa | 16 | 17/19 → fermato | giro a vuoto: 4 passate fermate | **modello**: debug a mente di un test con il caso («punti mostro randomici 1–15: Cannot read properties of undefined») |
| 11:21 | rifai | 12 | 28/28 | il difetto resta | test solo sulla logica |
| 11:30 | modifica (nome e «riparti») | 17 | 20/20 | il difetto resta | idem |
| 11:37 | correzione «nessun mostro, nessun punto, vince V» | 9 | 20/20 | **una riga** cambiata in `gioco.js` (`giocatoreCorrente = partita.turno`), ipotesi senza riprova; `logica.js` identico | **prompt e strumenti**: la correzione non chiede di riprodurre; nessun test può toccare `gioco.js`; il «test con ogni caso che non andava» chiesto dai vincoli non è stato scritto |
| 11:42 | correzione «è sempre esattamente uguale a prima» | 8 | 25/25 | `gioco.js` **riscritto per intero** (461 righe) con lo stesso errore; il riassunto dice «ora i mostri si vedono» | **contesto**: il `problema` passato è identico a quello delle 11:37, parola per parola, e «uguale a prima» si perde. **Revisione**: dichiarazione non verificata |
| 11:52 | modifica (animazione e punteggi) | 16 | 22/26 → fermato | giro a vuoto su un test di turno (`1 !== 2`), con `mossa` che cambia lo stato in place | **modello e strumenti**: 4 passate di ragionamento circolare sull'aliasing, che un `console.log` avrebbe chiuso |
| 12:06 | rifai, poi un altro giro | 26 | 21/21 | `gioco.js` riscritto (668 righe) con `mostraRisultato(res.risultato)`: il difetto sparisce, **per caso**; «15 passate senza file né test nuovi», 4 passate fermate | **modello**: tre volte «dato che il lavoro sta per finire, devo fare qualcosa di pratico» nel ragionamento (registro, righe 2397–2466) |

In tutto, 78 minuti di agente: 28 nei quattro lavori del mattino e 56 negli otto dalle 11:05.
Nessun `logica.test.js` dei dodici lavori nomina `gioco.js` o `document`.

**L'avviso «sta per finire» è uscito dal lavoro.** A «Scegliere la prima porta mi sembra che non
porti a nulla» (11:11) e a «Secondo te perché è bloccato?» (12:06) la voce ha risposto, citando
l'agente: «si è fermato perché il sistema ha rilevato che il lavoro stava per finire le sue
passate». La diagnosi era falsa: la causa vera era il campo annidato.

**Le cause, in sintesi:**

| Causa | Lavori | Peso |
|---|---|---|
| Nessun controllo del comportamento visibile; test solo sulla logica | 11:05–12:06 (6 versioni) | **principale** |
| Correzione senza riprodurre e senza un test rosso; nessun controllo che i file cambino | 08:46, 11:37, 11:42 | alto |
| Informazione persa tra voce e agente | 07:39, 08:39, 11:05, 11:42 | alto |
| Requisiti in contraddizione non segnalati | 07:39, 11:05 (poi 11:30–12:06) | medio |
| Giri a vuoto nel debug a mente; test dipendenti dal caso | 07:39, 11:13, 11:52, 12:06 | medio (tempo perso, non risultato sbagliato) |
| Prompt dell'agente | — | basso: il prompt chiedeva già i test e, nelle correzioni, «un test con ogni caso che non andava». Il modello non poteva scriverlo per il disegno, e il codice non lo controllava |

Quindi la frase «dipende soprattutto dalla qualità del prompt» il 12/10 vale solo in parte.
Il prompt c'era; mancava **un segnale esterno** che dicesse all'agente, e al codice, che il gioco
non faceva la cosa. È la stessa conclusione della letteratura sull'auto-correzione (§ 4.2).

## 2. La proposta: regge?

### 2.1 Cosa regge

- **Analisi prima dello sviluppo.** Il 12/10 due contraddizioni sono passate:
  - 07:39: «Scegli punteggio per vincere» insieme a «porte decise dal gioco»;
  - 11:05: «Scegli 2, 3 o 4 porte» insieme a «Numero porte randomico».

  Una lettura dell'agente che cerca i buchi le avrebbe trovate. Le domande prima di cominciare
  alzano il pass@1 di circa 8–10 punti sui problemi ambigui (ClarifyGPT, HumanEvalComm, § 4.4).
- **Test di accettazione prima del codice.** Dare i test al modello insieme al problema aumenta le
  soluzioni corrette di 9–30 punti (Mathews & Nagappan 2024). Tenere solo le patch che fanno passare
  un test prima rosso raddoppia la precisione (SWT-bench).
- **La segnalazione che diventa un test rosso.** È lo schema di Agentless e di TDD-Bench: localizza,
  riproduci, ripara, valida. Il 12/10 avrebbe chiuso il difetto alle 11:37 invece che alle 12:06.
- **Il codice che controlla gli artefatti e non il ragionamento.** È coerente con il principio 10 e
  con quello che la modalità sviluppo fa già: le transizioni le fa il codice quando un tool riesce.

### 2.2 Dove è debole

1. **Test e codice dallo stesso modello, nello stesso contesto.** Con lo stesso agente che scrive
   prima i test e poi il codice, i test ereditano le sue ipotesi. Le misure:
   - AgentCoder: accuratezza dei test 51–61 % con l'agente che scrive anche il codice, 88–90 % con
     un agente separato;
   - Konstantinou et al.: gli oracoli generati descrivono il comportamento *effettivo* del codice,
     non quello atteso.

   Il 12/10 i test di logica erano **giusti**; mancava il test del collegamento. La separazione dei
   ruoli quindi serve, ma serve di più **cosa** si testa.
2. **I test di un gioco non toccano il disegno.** Con `logica.js` e `gioco.js` liberi, un test
   «per requisito» scritto in `logica.test.js` passa anche se il disegno non mostra niente. Senza un
   modo di guidare il gioco vero (DOM finto con lettura del testo, o browser), il passo 2 della
   proposta per i giochi rifà il 12/10 con più test verdi.
3. **«Le fasi le guida l'agente con i suoi prompt».** Un modello di taglia media in un ciclo lungo
   non tiene bene le fasi. Con 16–26 passate e il contesto compresso dal diario, «prima i test,
   poi il codice» si perde come si è perso «aggiungi un test con ogni caso che non andava».
   - Funziona se la fase **è un lavoro a sé**, con il suo prompt, i suoi strumenti e un artefatto
     d'uscita che il codice controlla prima del lavoro successivo.
   - Funziona meno come capitolo dentro lo stesso ciclo.

   Questo è il «loop che si corregge con la macchina a stati»: la macchina a stati delle fasi la
   tiene il codice. Dentro ogni fase guida l'agente.
4. **Domande a voce.** Una buona analisi trova tanti buchi; a voce se ne reggono due. HumanEvalComm
   mostra il rischio opposto: un agente che domanda sempre scende da 65,6 a 27,5 sui problemi già
   completi. Servono un filtro (solo ciò che cambia il risultato, solo le contraddizioni) e il resto
   detto come «scelte fatte».
5. **«Verifica requisito per requisito: test presente e verde».** Un test può essere presente,
   verde e vuoto: `assert.ok(true)`, oppure un test che passa già sullo scheletro. Va controllato
   che ogni test **fallisca prima** (sullo scheletro o sulla versione precedente) e che sia legato
   a un requisito.

### 2.3 Costi stimati

Base delle stime: qwen3.6 su vLLM genera 2 800–4 300 token al minuto in un lavoro di codice (misure
del 05/10 in config.py:1062). Sono stime e vanno misurate.

| Fase in più | Token (stima) | Tempo sulla DGX | Sulla voce |
|---|---|---|---|
| Analisi dell'agente con ragionamento (domande, contraddizioni, scelte) | 3–8 mila | 1–3 min | **non nel turno**: la proposta diventa «ci penso, ti dico se ho dubbi» e le domande arrivano come oggi quelle di un lavoro (`mancano_dati`); con 0 domande parte da sé |
| Piano dei test (lavoro a sé, senza codice) | 4–10 mila | 1–3 min | niente |
| Controllo del piano (codice: un test per requisito, rosso sullo scheletro) | 0 | secondi (Node) | niente |
| Sviluppo | come oggi, forse meno (obiettivo chiaro) | come oggi | — |
| Correzione: test rosso prima | 2–5 mila | 1–2 min | niente |

Per uno sviluppo nuovo sono **3–6 minuti in più**. Il 12/10 le versioni sbagliate hanno fatto
perdere circa 45 minuti di agente (dalle 11:05 alle 12:06, sei lavori) più i collaudi di chi
amministra. La latenza della voce non cambia, se le fasi in più girano in secondo piano.

### 2.4 Rischi

- **Domande troppe o inutili a voce.** Tetto di 2 e filtro (§ 5.1); misurare quante domande a
  sviluppo e quante risposte «fai tu».
- **Test sbagliati allo stesso modo.** Contesto separato, test dai soli requisiti, rossi prima; e un
  controllo che non dipende dal modello: la riproduzione della segnalazione.
- **Test non scrivibili per la parte visiva.** Il DOM finto c'è già. Basta un'API per i test
  (tocca, leggi il testo, aspetta), e la macchina a stati dei giochi rende stabile ciò che si
  legge (pagine standard, istantanea).
- **Fasi che si allungano in loop.** Ogni fase ha il suo tetto di passate e il suo artefatto. Oltre
  il tetto si ferma e lo dice, senza «continua finché».
- **Requisiti non testabili** («musica spaventosa ma per bambini»). Si dichiarano **non
  verificabili da codice** già nel piano, e restano al collaudo della persona. Così il conto non li
  dà per fatti.

## 3. Strade alternative

### A. Ruoli separati: chi scrive i test non scrive il codice (AgentCoder)

Un lavoro «progettista dei test» riceve solo i requisiti, il contratto del tipo (API del gioco,
`esegui(dati, calliope)` per un'estensione) e lo scheletro; non vede il codice. Scrive
`accettazione.test.js` o `test_accettazione.py`. Il programmatore riceve i test in sola lettura e
non può modificarli: se un test gli sembra sbagliato lo segnala, non lo cambia.
- **Pro:** è la misura più solida che c'è (test giusti dal 51–61 % all'88–90 %). Lo stesso modello va
  bene: conta il contesto separato. Toglie il «correggo il test perché passi» visto il 12/10 (11:13
  e 11:52: l'agente modificava `logica.test.js` per farlo tornare).
- **Contro:** una passata in più. Il progettista deve conoscere l'API prima che esista: per i giochi
  serve un contratto stabile, che oggi non c'è e che la macchina a stati darebbe. Per le estensioni
  c'è già (`esegui`, `CalliopeFinta`).

### B. Architetto ed esecutore (Aider architect/editor)

Un modello pianifica (cosa cambiare, in quali file, con quale forma dei dati tra i file) e un altro,
o lo stesso senza ragionamento, applica le modifiche.
- **Pro:** nel benchmark di aider da +3 a +10 punti, di più per i modelli che ragionano bene ma
  sbagliano le modifiche. Il 12/10 un piano scritto con «`mossa` restituisce `{stato, risultato}`;
  `gioco.js` legge `res.risultato`» avrebbe reso esplicito proprio il contratto rotto.
- **Contro:** non dà un segnale esterno, quindi non avrebbe fermato «26/26 ma niente mostri». Con
  un solo modello sulla DGX, i due ruoli sono due prompt dello stesso qwen3.6. Utile come **forma**
  del passo di sviluppo, non come rimedio.

### C. Il modello della voce o un giudice che scrive i test dai requisiti

gemma (26B MoE, già in memoria) o qwen3.6 senza ragionamento scrivono gli esempi o i test dai
requisiti, al momento dell'analisi.
- **Pro:** è un modello diverso da quello che scriverà il codice, quindi gli errori sono meno
  correlati. Il modello della voce ha sentito la persona.
- **Contro:** gemma è occupata con la conversazione: i test scritti nel turno costano latenza, e in
  secondo piano contendono la GPU. Il modello della voce scrive codice di test peggio dell'agente.
  Meglio fargli scrivere **esempi in parole** (strada E) che codice.

### D. Il controllo del gioco vero (DOM finto potenziato o browser senza finestra)

Due livelli:
- **D1, DOM finto con lettura** (Node, già in `fumo_js.mjs`). Si aggiunge un'API per i test di
  accettazione: `tocca("porta 1")`, `testo()`, `aspetta(ms)`. Un test dice «toccando una porta
  compare un mostro o un oggetto con il suo nome; con un mostro il punteggio del giocatore cresce».
  Il 12/10 l'avrebbe preso alla prima versione, dalle 11:05. Costo quasi nullo (millisecondi), gira
  nel container Node che c'è.
- **D2, browser senza finestra** (Chromium nel container, o Edge sul portatile come in
  `prove/cdp.py`). Serve a impaginazione, canvas, animazioni e screenshot, più un giudice visivo con
  una lista per requisito (ArtifactsBench). È più costoso e fragile, e i giudici visivi trovano meno
  della metà dei difetti (CATTest, WebGen-Bench). Va tenuto come segnale in più, non come cancello.

**Pro:** è l'unica strada che guarda ciò che vede la persona. **Contro:** D1 non vede impaginazione
né canvas. Con `gioco.js` libero i selettori cambiano a ogni versione: la macchina a stati (pagine
standard, pulsanti con il nome del comando, istantanea) risolve questo punto.

### E. Specifica eseguibile: esempi dato → risultato

All'analisi i requisiti verificabili diventano **esempi** in una forma chiusa, scritti
dall'analista, confermati dalla persona solo se sono ambigui e trasformati in test dal codice. Per
esempio: «con 2 giocatori, dopo la mossa del primo tocca al secondo»; «convertire 10 miglia → 16,09
km»; «la città che non esiste → "non l'ho trovata"».
- **Pro:** gli esempi sono anche la domanda a voce migliore. TiCoder (+46 punti di pass@1 in 5
  interazioni) mostra che confermare esempi chiarisce l'intento meglio delle domande aperte. Il test
  lo genera il codice, non il modello, quindi niente oracoli copiati dall'implementazione. Funziona
  bene per programmi ed estensioni, dove `CalliopeFinta` e `argomenti_esempio` ci sono già.
- **Contro:** per un gioco il casuale va fissato (semi), e gli esempi descrivono la logica, non il
  disegno, a meno di D1. Il property-based testing generato dai modelli è difficile: solo il 21 %
  delle proprietà ricavabili esce corretto (Vikram et al.). Meglio esempi concreti che proprietà.

### F. Iterazioni brevi: un requisito per giro

Ogni lavoro affronta uno o due requisiti, con il loro test, e consegna. Il successivo parte dai file.
- **Pro:** contesto piccolo, meno giri a vuoto (i loop crescono con la difficoltà: 51 % contro
  13 %, Pipis et al.). Il conto di ciò che è fatto è naturale. Le tappe di oggi sono già un passo in
  questa direzione.
- **Contro:** più lavori e più avvii (prompt di 5 500 token a ogni lavoro: cache di vLLM da
  verificare). Su un gioco piccolo i requisiti si toccano tutti, e il collaudo della persona a ogni
  giro è troppo. Va bene come **regola interna** («un test rosso alla volta»), non come un collaudo
  per requisito.

### Confronto

| Strada | Avrebbe preso il difetto del 12/10? | Costo | Rischio | Funziona nel profilo 8 GB |
|---|---|---|---|---|
| Proposta così com'è (stesso agente, fasi nei prompt) | solo se i test toccano il disegno | medio | fasi perse in un ciclo lungo | poco |
| A. ruoli separati | sì, con un contratto del gioco | +1 passata | serve un'API stabile | sì (stesso modello, due prompt) |
| B. architetto/esecutore | forse (contratto scritto) | +1 passata | nessun segnale esterno | sì |
| C. test dalla voce | dipende da cosa testa | latenza o GPU | codice di test debole | no (contende la GPU) |
| D1. DOM finto con lettura | **sì, alla prima versione** | quasi zero | selettori instabili senza macchina a stati | sì (Node, nessun modello) |
| D2. browser e giudice visivo | sì | alto | giudice inaffidabile | no |
| E. esempi dato → risultato | per la logica sì | basso | gioco: serve D1 | **sì, il più adatto** |
| F. un requisito per giro | indiretto | più avvii | troppi collaudi | sì |

## 4. Cosa dice la letteratura (e cosa è solo opinione)

**[P]** = provato (benchmark, articolo con numeri, documentazione ufficiale); **[O]** = opinione o
numero dichiarato dal produttore. Fonti raccolte il 12/10; i due articoli del 2026 (CATTest,
WebTestBench) sono citati dal riassunto e non li ho riletti per intero.

### 4.1 Il modello: campionamento, ripetizioni, ragionamento

- **[P]** Scheda di Qwen3.6-35B-A3B ([HF](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)):
  - thinking per **coding preciso**: temperatura **0,6**, top_p 0,95, top_k 20, presence_penalty
    **0**;
  - thinking generale: temperatura 1,0, presence_penalty 1,5;
  - presence_penalty tra 0 e 2 «to reduce endless repetitions», ma «a higher value may
    occasionally result in language mixing and a slight decrease in model performance»;
  - uscita fino a 32 768 token, 81 920 per i compiti difficili;
  - Qwen3.6 è addestrato a usare il ragionamento dei turni precedenti (`preserve_thinking`).

  **Da noi:** `agenti_temperatura` è **0,4** (config.py:1053), sotto il consigliato; presence_penalty
  0,5 per le estensioni (misurato l'11/10 su 6 passate). Da rimisurare con 0,6 sul banco.
- **[P]** Scheda di Qwen3 ([HF](https://huggingface.co/Qwen/Qwen3-30B-A3B)): «DO NOT use greedy
  decoding, as it can lead to performance degradation and endless repetitions». **Da noi**
  analisi, requisiti, modifiche e confronto girano a **temperatura 0 senza ragionamento**
  (requisiti.py:232). Con l'uscita vincolata da uno schema il rischio di loop è basso, ma per
  un'analisi che deve *trovare buchi* conviene il ragionamento con il campionamento consigliato.
- **[P]** Pipis et al. 2025, [«Wait, Wait, Wait… Why Do Reasoning Models Loop?»](https://arxiv.org/html/2512.12895):
  - tutti i modelli di ragionamento open vanno in loop a bassa temperatura;
  - a temperatura 0: distillato 1,5B 76 %, 32B 37 %;
  - i loop sono molto più frequenti nei problemi difficili (51 % contro 13 %);
  - la temperatura alta è solo un tampone;
  - un rilevatore semplice: un n-gramma di 30 token ripetuto 20 volte.

  **Da noi** `ripetizioni.py` fa già una cosa simile sulle frasi di prosa.
- **[P]** TALE ([arXiv 2412.18547](https://arxiv.org/abs/2412.18547)): un budget scritto nel prompt,
  se è piccolo, non viene rispettato. BATS ([arXiv 2511.17006](https://arxiv.org/abs/2511.17006)):
  mostrare il budget per «regimi», ognuno con un'azione, aiuta gli agenti di ricerca. **[O]** Non
  c'è uno studio sull'effetto di «restano 2 passate» nel ragionamento: il 12/10 l'abbiamo visto
  entrare nel ragionamento e nella diagnosi detta a voce. È un'osservazione nostra, ma basta per
  toglierlo.
- **[P]** Cuadron et al. 2025, [«The Danger of Overthinking»](https://arxiv.org/abs/2502.08235): su
  4 018 traiettorie di SWE-bench, scegliere la soluzione meno «rimuginata» dà circa +30 % e costa
  circa il 43 % in meno. Ragionare a lungo senza agire è un difetto noto e misurabile.

### 4.2 Auto-correzione: serve un segnale esterno

- **[P]** Huang et al., ICLR 2024 ([arXiv 2310.01798](https://arxiv.org/abs/2310.01798)):
  l'auto-correzione senza feedback esterno non migliora e a volte peggiora (CommonSenseQA da 75,8 a
  38,1).
- **[P]** Kamoi et al., TACL 2024 ([arXiv 2406.01297](https://arxiv.org/abs/2406.01297)):
  l'auto-correzione funziona con un feedback esterno affidabile (esecuzione, test, strumenti).
- **[P]** Olausson et al., ICLR 2024 ([arXiv 2306.09896](https://arxiv.org/abs/2306.09896)): a pari
  costo il self-repair rende poco; il collo di bottiglia è la qualità del feedback.
- **[P]** Self-Debugging ([arXiv 2304.05128](https://arxiv.org/abs/2304.05128)) e Reflexion
  ([arXiv 2303.11366](https://arxiv.org/abs/2303.11366)): i guadagni vengono dall'esecuzione dei
  test.

**Per noi:** le due correzioni delle 11:37 e delle 11:42 sono autocritica senza segnale esterno: i
test verdi non riguardavano il difetto. È il caso che la letteratura dice non funzionare.

### 4.3 Test generati dai modelli e TDD

- **[P]** Mathews & Nagappan, ASE 2024 ([arXiv 2402.13521](https://arxiv.org/abs/2402.13521)):
  - con i test dati insieme al problema, +9–13 punti per GPT-4 e +13–30 per Llama 3;
  - il ciclo di correzione con l'esito dei test aggiunge 5–9 punti;
  - dopo 3–4 giri il guadagno sparisce, e i casi arrivati al quinto non si sono mai risolti.
- **[P]** AgentCoder ([arXiv 2312.13010](https://arxiv.org/abs/2312.13010)): accuratezza dei test
  scritti dall'agente che scrive anche il codice 61,0 % e 51,8 %, con un agente separato 87,8 % e
  89,9 %; copertura dal 72–76 % all'87–90 %.
- **[P]** Konstantinou, Degiovanni, Papadakis 2024 ([arXiv 2410.21136](https://arxiv.org/abs/2410.21136)):
  gli oracoli generati tendono a descrivere il comportamento effettivo e non quello atteso.
  Mathews & Nagappan 2024 ([arXiv 2412.14137](https://arxiv.org/abs/2412.14137)): tenere solo i test
  che passano significa convalidare i difetti.
- **[P]** SWT-bench ([arXiv 2406.12952](https://arxiv.org/abs/2406.12952)): riprodurre un problema
  con un test che prima fallisce è difficile, ma filtrare le patch con quel test raddoppia la
  precisione. TDD-Bench Verified ([arXiv 2412.02883](https://arxiv.org/abs/2412.02883)): test scritti
  *prima* della correzione, misurati per fail-to-pass e copertura.
- **[P]** CodeT ([arXiv 2207.10397](https://arxiv.org/abs/2207.10397)): molti test generati e
  l'accordo tra test e codice per scegliere; da 47,0 a 65,8 di pass@1. Utile se si campionano più
  soluzioni, cosa che con un solo modello lento non facciamo.

### 4.4 Chiarire prima di agire

- **[P]** ClarifyGPT, FSE 2024 ([arXiv 2310.10996](https://arxiv.org/abs/2310.10996)):
  - decide se domandare con un controllo di coerenza: più soluzioni che danno uscite diverse sugli
    stessi input indicano un requisito ambiguo;
  - con persone vere, GPT-4 da 70,96 a 80,80 su MBPP.
- **[P]** HumanEvalComm ([arXiv 2406.00215](https://arxiv.org/html/2406.00215v3)):
  - sui problemi resi ambigui il pass@1 crolla (da 65,6 a 31,3);
  - i modelli domandano poco;
  - un agente che domanda molto passa da 31,3 a 39,6 sugli ambigui ma scende da 65,6 a 27,5 sui
    completi.
- **[P]** TiCoder, TSE 2024 ([arXiv 2404.10100](https://arxiv.org/abs/2404.10100)): far approvare
  test o esempi alla persona chiarisce l'intento; +46 punti in 5 interazioni con un utente simulato.
- **[O]** Per la voce: al più 1–2 domande per sviluppo, meglio se in forma di esempio da confermare
  («Quindi con due giocatori le porte restano le stesse per tutti e due?»).

### 4.5 Piano ed esecuzione, scaffold

- **[P]** Aider architect/editor ([aider.chat](https://aider.chat/2024/09/26/architect.html)): da +3
  a +10 punti nel loro benchmark; per esempio o1-mini da 61,1 a 71,4.
- **[P]** Agentless ([arXiv 2407.01489](https://arxiv.org/abs/2407.01489)): una pipeline fissa
  (localizza, ripara, valida con test di riproduzione) batteva gli agenti liberi dell'epoca a costo
  minore.
- **[P]** SWE-agent ([arXiv 2405.15793](https://arxiv.org/abs/2405.15793)): l'interfaccia
  agente-computer (strumenti progettati per il modello) pesa quanto il modello. CodeAct
  ([arXiv 2402.01030](https://arxiv.org/abs/2402.01030)): azioni come codice eseguibile, fino a +20 %.
- **[O]** Numeri di SWE-bench Verified per modelli di taglia media, dai produttori o da aggregatori:
  Qwen3.6-35B-A3B 73,4 (scaffold interno, contesto 200K); Devstral Small 2 68,0; Qwen3-Coder-30B-A3B
  49–60 a seconda dello scaffold. **Lo scaffold conta quanto il modello.**

### 4.6 Giochi e interfacce

- **[P]** ArtifactsBench ([arXiv 2507.04952](https://arxiv.org/abs/2507.04952)): rende l'artefatto,
  fa tre screenshot nel tempo, e un giudice multimodale valuta con una lista per compito; accordo con
  gli esperti oltre il 90 %.
- **[P]** WebGen-Bench ([arXiv 2505.03733](https://arxiv.org/abs/2505.03733)): test funzionali eseguiti
  da un agente di navigazione; la migliore combinazione arriva al 27,8 %.
- **[P, non riletto]** CATTest (2026): un modello visivo che scrive Playwright trova meno della metà
  dei difetti; i modelli leggeri sono «barely usable».
- **[O]** Per un gioco su canvas senza DOM servono agganci di stato esposti dal gioco, oppure gli
  screenshot.

### 4.7 Specifiche eseguibili

- **[P]** Vikram et al. ([arXiv 2307.04346](https://arxiv.org/abs/2307.04346)): solo il 21 % delle
  proprietà ricavabili dalla documentazione esce corretto come property-based test.
- **[P]** PGS ([arXiv 2506.18315](https://arxiv.org/abs/2506.18315)): un tester separato basato su
  proprietà, con il controesempio minimo come feedback, migliora del 23–37 % rispetto al TDD, anche
  con modelli open da 32B.
- **[P]** Li & Ellis, NeurIPS 2024 ([arXiv 2406.08316](https://arxiv.org/abs/2406.08316)): gli
  esempi da soli non bastano fuori distribuzione; servono insieme alla descrizione.

### 4.8 In sintesi, per un modello come il nostro

| Pratica | Stato | Da noi oggi |
|---|---|---|
| Segnale esterno (esecuzione) per ogni correzione | **[P]** | parziale: i test sì, ma non sul difetto segnalato |
| Test da un contesto separato, dai requisiti | **[P]** | no |
| Test che falliscono prima della correzione | **[P]** | no |
| 3–4 giri di correzione al più, poi si riparte con un piano nuovo | **[P]** | `RIMANDI_MAX` 2, ma i lavori si ripetono senza piano nuovo |
| Temperatura 0,6 e presence_penalty 0 per il codice (Qwen3.6) | **[P]** | 0,4 e 0,5 |
| Mai greedy per il ragionamento | **[P]** | analisi e requisiti a 0, senza ragionamento |
| Rilevare i loop nel codice | **[P]** | sì (`ripetizioni.py`, passate senza novità) |
| Il budget al modello come azione, non come conto alla rovescia | **[O]** con appoggio parziale | conto alla rovescia (`AVVISO_FINE`) |
| Domande solo sull'ambiguità vera, poche | **[P]** | sì nell'analisi, ma solo dai punti della lista e senza contraddizioni tra requisiti |
| Pipeline rigida per modelli piccoli | **[O]** con appoggio (Agentless) | — |

## 5. Raccomandazione

**Le fasi le tiene il codice, il contenuto di ogni fase lo fa l'agente, e ogni passaggio tra fasi
richiede un artefatto controllato da un segnale esterno.** È la proposta, con due correzioni: test
da un contesto separato e test che guidano il comportamento vero. In ordine di valore per costo:

### 5.1 I passi

1. **La correzione comincia da un test rosso** (per programmi, estensioni e giochi). Prima fase del
   lavoro di correzione: «riproduci la segnalazione con un test». Il codice controlla due cose:
   - il test nuovo **fallisce** sui file attuali, altrimenti lo rimanda («il test passa già: non
     riproduce il problema»);
   - alla consegna quel test **passa** e i file del programma sono **cambiati**.

   Con i file identici la correzione si rifiuta (il caso delle 08:46). Nel lavoro va anche la
   cronologia delle correzioni precedenti dello stesso difetto («è la seconda volta: la correzione di
   prima, una riga in gioco.js, non ha funzionato»), oltre al `problema` detto dalla voce.
   *Costo: basso. Avrebbe chiuso il 12/10 alle 11:37, a patto di poter scrivere quel test (passo 2).*
2. **I giochi si provano dal disegno (D1).** `fumo_js.mjs` ha già il DOM finto. Gli si aggiunge
   un'API per i test: toccare un elemento per testo o ruolo, leggere il testo visibile, far passare
   il tempo. Lo scheletro del gioco e il prompt dicono di scrivere `gioco.test.js` accanto a
   `logica.test.js`. Con la macchina a stati dei giochi i test toccano i pulsanti dei comandi e
   leggono l'istantanea, e diventano stabili.

   In più, un controllo generico nella prova di fumo: dopo un tocco che chiama la logica, «undefined»
   o «NaN» nel testo visibile è un errore. Non avrebbe preso il 12/10, dove il campo vuoto mostrava
   «Nessun punto!», ma prende una classe vicina.
3. **I test di accettazione in un lavoro a sé, prima del codice** (strade A ed E).
   - Un lavoro breve, «progettista dei test», riceve i requisiti numerati, il contratto del tipo e lo
     scheletro, e non vede il codice. Scrive un test per ogni requisito verificabile, con il numero
     del requisito nel nome (`R3: …`). Dichiara gli altri «solo al collaudo» (musica, «ben
     visibile»).
   - Il codice controlla: ogni requisito ha un test o è dichiarato «al collaudo»; ogni test fallisce
     sullo scheletro.
   - Il programmatore riceve i test **in sola lettura**: se uno gli sembra sbagliato, lo dice nella
     consegna. La revisione onesta legge anche quella nota.
   - Per programmi ed estensioni il progettista scrive soprattutto **esempi dato → risultato**, che il
     codice trasforma in test (con `CalliopeFinta` per le estensioni).
4. **L'analisi dell'agente con le domande**, in secondo piano, con il ragionamento acceso:
   - rilegge la richiesta detta (le parole della persona, non solo il compito di gemma) e i
     requisiti;
   - restituisce in uno schema chiuso le **contraddizioni** tra requisiti, i punti che cambiano il
     risultato, le scelte che farebbe da solo e, per ciascuno, una domanda breve o un esempio da
     confermare.

   Il codice ne fa dire **al più due**, le contraddizioni prima, e le scelte le dice la proposta in
   una frase («Le porte le decide il gioco, da 3 a 5»). Con zero domande lo sviluppo parte senza
   chiedere. Si allarga l'analizzatore di oggi (richiesta.py), che ha già il tetto di due domande e
   le «scelte», con il ragionamento e con il confronto tra i requisiti. Anche il compito riscritto
   da gemma si confronta con le parole della persona: il 12/10 «giocatori» è diventato «porte».
5. **Strumenti e campionamento dell'agente.**
   - `esegui_js` (un file .js in Node, senza rete, come `esegui_python`): il 12/10 due giri a vuoto
     su quattro erano debug a mente di un comportamento che una stampa avrebbe mostrato.
   - Nello scheletro, il caso con un seme (`creaCaso(seme)` passato a `nuovaPartita`) e i test con
     un seme fisso. Così non c'è il «28/28 per l'agente, 27/28 per il codice» delle 07:39.
   - L'avviso di chiusura senza numeri e senza «sta per finire»: un'azione («consegna adesso ciò che
     funziona e scrivi cosa manca»). Una riga di `sviluppo_chiedi` che dice che il lavoro «si è
     fermato perché stava per finire le passate» si rilegge contro il motivo vero
     (`motivo_arresto`).
   - Temperatura dell'agente 0,6 sul banco, contro lo 0,4 di oggi; presence_penalty da rimisurare
     insieme.
6. **La verifica prima della consegna** diventa codice, non un prompt: tutti i test di
   accettazione verdi (quelli del progettista, non quelli che l'agente ha riscritto), più la prova
   di fumo. La revisione onesta resta, con un compito più piccolo: i requisiti «al collaudo» e la
   coerenza generale. Dice «provato da un test» o «letto nel codice», e a voce si distinguono.

Collaudo e attivazione restano come oggi. Il collaudo della persona conta come ultimo test di
accettazione: un collaudo «non va» con una frase diventa il passo 1.

### 5.2 Cosa non fare

- **Non** mettere le fasi in un solo ciclo lungo dell'agente governato dal prompt: le fasi sono
  lavori distinti, ciascuno con il suo tetto.
- **Non** contare «test presenti e verdi» senza controllare che fossero rossi prima.
- **Non** far scrivere codice di test alla voce (gemma): al più esempi in parole.
- **Non** usare un giudice visivo (D2) come cancello: al più come segnale al collaudo, più avanti.

### 5.3 Come si misura

Un banco nuovo, sul modello di `prove/banco_richieste.py`. Gira **sulla DGX** con i lavori veri,
lanciato a mano (decine di minuti), con tre casi veri e i loro difetti:

| Caso | Richiesta (dalle frasi vere, con i dati di fantasia) | Cosa deve risultare |
|---|---|---|
| Le porte magiche | la richiesta delle 11:03 e le tre modifiche, con la segnalazione «nessun mostro, nessun punto» | contraddizione porte/giocatori trovata all'analisi; test di disegno che fallisce sulla versione delle 11:05; correzione che lo fa passare al primo giro |
| Il convertitore (estensione) | il convertitore delle prove dell'08/10, con un valore di due parole con l'accento | esempi dato → risultato, test rossi sullo scheletro, consegna al primo giro |
| Un programma | uno script con un file della persona («rinomina le foto per data») | domanda sul formato solo se manca; test sul file d'esempio |

Si misura per caso e per variante (oggi / con i passi 1–2 / con 1–5), su 3 ripetizioni:
- requisiti coperti da un test che prima falliva;
- difetti seminati trovati;
- lavori fino al primo collaudo giusto;
- passate e minuti per lavoro;
- passate fermate per giro a vuoto;
- domande a voce e loro utilità (la risposta ha cambiato un requisito?);
- dichiarazioni false nella consegna («ora i mostri si vedono» con il difetto ancora lì).

Funziona se il caso delle porte arriva al collaudo giusto in **un lavoro più una correzione**
(oggi: sei), con **zero** consegne «fatto» a file identici e i giri a vuoto almeno dimezzati.

### 5.4 Nel profilo ridotto da 8 GB

Oggi nel profilo da 8 GB l'agente non c'è: su Windows il codice dell'agente non si esegue, e il
piano della macchina lo segna «da configurare» (si veda la ricerca sulla macchina a stati, § 9).
Si comporta così:
- **Uguale, senza modelli:** il controllo degli artefatti (test rossi e poi verdi, file cambiati,
  un test per requisito), il DOM finto e i semi. Sono codice e Node e non usano VRAM.
- **Con un agente piccolo** (4–9B, se un giorno girerà lì o su un altro computer): il flusso a fasi
  rigide gli serve **di più**. I modelli piccoli vanno in loop molto più spesso (§ 4.1) e
  tengono peggio le istruzioni lunghe. Quindi:
  - un requisito per giro (strada F come regola);
  - esempi dato → risultato invece di test liberi (strada E);
  - temperatura sopra lo 0 e rilevatore dei loop acceso;
  - tetti di passate più bassi per fase.
- **L'analisi con domande** usa il modello che c'è: con un agente remoto la fa l'agente; senza
  agente non c'è sviluppo, e quindi non c'è analisi.

## 6. Domande aperte per chi amministra

1. **Le domande dell'analisi arrivano dopo la proposta, in secondo piano** (1–3 minuti), invece che
   subito a voce? *Proposta:* sì. «Ci penso un attimo» alla proposta, poi le domande come quelle di
   oggi a metà lavoro (al più due, anche sullo schermo); con zero domande lo sviluppo parte da sé.
2. **Il programmatore non può modificare i test di accettazione?** Se un test è sbagliato, lo
   segnala e il lavoro torna al progettista. *Proposta:* sì, sola lettura. Il 12/10 l'agente
   cambiava i test per farli tornare (11:13, 11:52).
3. **Una correzione con i file identici o senza un test rosso si rifiuta, anche se l'agente dice
   «era già a posto»?** *Proposta:* sì. Si rimanda una volta all'agente; alla seconda il lavoro si
   chiude dicendo «non ho trovato il difetto: me lo descrivi in un altro modo?».
4. **Requisiti «solo al collaudo»** (musica, «ben visibile», «per bambini): la revisione li dice
   come «da guardare tu», non come fatti o mancanti? *Proposta:* sì. Così il conto «le altre 6 ci
   sono» diventa «4 provate da un test, 2 da guardare tu».
5. **Ordine rispetto alla macchina a stati dei giochi:** i passi 1, 2 e 5 prima (utili a tutti i
   tipi e piccoli), la macchina a stati poi, e i test di disegno si rifanno sopra le sue pagine
   standard? *Proposta:* sì, i passi 1, 2 e 5 subito; il passo 3 dopo la macchina a stati per i
   giochi, subito per programmi ed estensioni.
6. **Temperatura dell'agente a 0,6** (scheda di Qwen3.6 per il codice) contro lo 0,4 di oggi:
   provarla sul banco prima di cambiarla? *Proposta:* sì, sul banco del § 5.3, insieme al
   presence_penalty.
