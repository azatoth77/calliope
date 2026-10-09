# Il dialogo tra tool, modello della voce e agente (09/10/2026)

*Ramo `dialogo-tool`. Aree: [voce-e-regole](../aree/voce-e-regole.md),
[agenti-estensioni](../aree/agenti-estensioni.md). Progetto breve scritto prima del codice; le
misure sono in fondo (§ 7).*

## 1. Il caso vero e la decisione

DGX, 09/10 08:19–08:20: «Raccontami le ultime novità della giornata» → `web_cerca({'tipo':
'notizie'})` → `{"errore": "argomenti non validi: _web_cerca() missing 1 required positional
argument: 'domanda'"}` → «ho avuto un piccolo intoppo, riprovo subito», e nessun nuovo
tentativo (regola `fallito_senza_dato`); quattro volte di fila, anche con «vai sul sito
dell'Ansa e prendi la prima notizia».

Tre difetti, nessuno del caso specifico:
- l'errore era una traccia Python, scritta per un programmatore: diceva il nome della funzione
  interna, non quale argomento serve, che cosa deve contenere, un esempio;
- `ToolRegistry.mancanti` (06/10) fermava solo la chiamata **senza nessun** argomento: con
  `tipo` presente la chiamata arrivava alla funzione e il `TypeError` diventava «argomenti non
  validi»;
- dopo un tool fallito la risposta «riprovo subito» senza chiamata passava: le spinte sulle
  promesse (`spinta_promessa`) valgono solo **senza nessun tool** nella risposta.

Decisione di Dario: niente regola per «notizie senza domanda». Un protocollo generale, in cui
tool, modello della voce e agente si parlano in modo chiaro e i giri fra le AI risolvono da
sé; al più una frase intercalata alla persona per tenerla aggiornata.

## 2. Errori dei tool come messaggi per il modello

Un modulo nuovo, `calliope/tools/dialogo.py`, usato da `ToolRegistry.call` per **tutti** i tool
(anche le estensioni `est_*`, registrate a runtime) e dagli strumenti dell'agente:

- **Validazione prima della chiamata**, contro lo schema e la firma della funzione:
  obbligatorio assente o vuoto che la funzione non sa completare da sola (niente valore
  predefinito: `lavoro_affida` e `compiti_aiuto` completano dalla proposta in sospeso, e
  restano come prima); valore fuori da `enum`; numero o vero/falso non convertibili;
  argomento che la funzione non conosce (sarebbe un `TypeError`).
- **Conversioni di forma** prima di decidere (principio 10, regola `tool_argomento_forma`):
  maiuscole, accenti e spazi («Età» → `eta`), un inizio che individua un solo valore
  ammesso, numeri e vero/falso scritti come testo.
- **Forma comune dell'errore**: `{ok: false, fatto: NIENTE, errore: <frase chiara>, campo,
  argomenti: {nome: {tipo, obbligatorio, valori_ammessi, cosa}}, esempio: {tool, argomenti},
  correggibile: true, cosa_fare}`. `cosa` è la descrizione dell'argomento dallo schema o, se
  manca (quasi sempre), il pezzo «nome: …» della descrizione del tool. `esempio` è la chiamata
  del modello con i pezzi mancanti al loro posto (`<domanda>`, `<web|notizie>`). `cosa_fare`:
  richiamare subito, ricavando il dato dalla frase e dalla conversazione; chiedere alla
  persona solo se non si ricava; «non dire che riprovi: richiamalo».
- **Eccezioni del tool**: mai la traccia. Un errore di programmazione (`TypeError`,
  `KeyError`…) è «X si è fermato per un errore interno», `correggibile: false`, «non
  richiamarlo con gli stessi argomenti, dillo in breve»; un `ValueError` o un guasto tiene la
  sua prima riga breve (il `ValueError` è correggibile). La traccia va nel terminale.
- **Forma vecchia** `{errore}` senza `ok` → `{ok: false, errore}` (`dialogo.uniforma`).
- Un errore scritto dal registro non porta dati: Brain non lo mette nella busta dei dati non
  fidati (`ToolContext.errore_registro`), come già `fallito_senza_dato`.

Regole nel registro dei turni: `tool_argomenti_mancanti` (come dal 06/10),
`tool_argomenti_non_validi`, `tool_argomento_forma`, `tool_errore_interno`.

## 3. Giri di correzione nella stessa risposta

Il ciclo dei tool di Brain già permette `max_tool_turns` (4) passate: un errore non chiude il
turno, il modello rilegge il risultato e può richiamare. Quello che mancava è la rete per il
modello che **dice** che riprova invece di riprovare.

- `last_tools` segna `correggibile` (dal risultato). Finché l'ultimo tool fallito è
  correggibile e non c'è stato un successo dopo, il testo della passata successiva **aspetta la
  fine** (come `hold_request`): se arriva una chiamata si dice; altrimenti non si dice e il
  modello riceve `CORREZIONE_NUDGE` (rilegge l'errore, richiama o chiede), regola
  `correzione_tool`. Una **domanda** alla persona («Di quale argomento vuoi le notizie?») si
  dice dal secondo giro: al primo aspetta anche lei, perché il 4B chiedeva il dato appena detto
  («Potresti dirmi la durata?» dopo «un timer di cinque minuti», § 7).
- L'errore e la spinta riportano la frase della persona («ricavando domanda da quello che ha
  detto la persona («Raccontami le ultime novità della giornata»)… va bene anche una forma
  generale, con le sue stesse parole»): è il dato che il modello ha già, e senza il 4B
  chiedeva l'argomento invece di cercare (§ 7).
- Tetto: `tool_correzioni_max` (2) passate dopo un errore correggibile per risposta; poi il
  testo si dice com'è (anche «non ci sono riuscita»). Un errore **non** correggibile non
  trattiene niente: lo si dice onestamente, niente giri.
- Rete del modello `correzione_tool` (spegnibile da un profilo, come le altre spinte).

## 4. Aggiornare la persona mentre le AI si parlano

Se si entra in un giro di correzione e non si è ancora detto niente, e dall'inizio della
risposta sono passati più di `tool_correzione_avviso_s` (2,0 s), una
frase breve (`dialogo.FRASI_CORREZIONE`: «Un attimo, sistemo la richiesta.», «Un momento, ci
riprovo.») con lo stesso canale delle frasi d'attesa dei tool (`on_tool_start`), una volta per
risposta, fuori dalla storia, sintetizzata all'avvio con gli annunci (`announcements`). Non
blocca lo streaming. La frase d'attesa del tool («Cerco su internet.») non parte più per una
chiamata che non partirà (`mancanti` ora dice tutti gli argomenti che la fermano): parte con la
chiamata corretta.

## 5. Voce e agente

Dove passano i messaggi fra il modello della voce e l'agente (§ 7 per l'inventario):
- **Strumenti dell'agente** (ciclo del codice e della ricerca): stessa validazione degli
  obbligatori e stessa forma degli errori (`dialogo.controlla` sugli schemi dell'agente,
  `dialogo.errore_interno` per le eccezioni, che però per l'agente tengono tipo e messaggio:
  l'agente scrive codice e il messaggio gli serve).
- **Esiti dei lavori verso la voce** (`lavoro_stato`, `lavoro_risultato`, annunci): sono già
  frasi (`motivo`, `riassunto`, `cosa_fare`); la parte tecnica (`errore` con il tipo
  dell'eccezione) resta nei dati del lavoro e nel log.

## 6. Cosa non si fa

- Nessun esempio scritto a mano per tool (sarebbe pilotare i casi): l'esempio nasce dallo
  schema e dalla chiamata del modello.
- Nessuna validazione degli elenchi e degli oggetti: i tool li completano o li leggono già
  in forme diverse; si convertono solo enum, numeri e vero/falso.
- Il contratto unico dei risultati riusciti (docs/architettura-tool.md § 6.1) resta un lavoro
  a parte: qui solo gli errori.

## 7. Misure e inventario

**Banco** (`scratchpad`, non nel repository: la prima passata è forzata con la chiamata
sbagliata, come quella vista sulla DGX, poi il modello vero; gemma4 e4b locale su questo
portatile, SearXNG finto delle prove, 3 giri per caso). «Prima» = main (traccia del
`TypeError`, nessun giro di correzione); «dopo» = questo ramo.

| Caso (frase → chiamata sbagliata) | Prima | Dopo | Dopo, secondi totali |
|---|---|---|---|
| «Raccontami le ultime novità della giornata» → `web_cerca({tipo: notizie})` | 0/3 | **3/3** | 2,3–2,4 |
| «Vai sul sito dell'Ansa e prendi la prima notizia» → idem | 0/3 | **3/3** | 2,2–2,4 |
| «Che tempo fa domani a Milano?» → `web_cerca({query: …})` (argomento sconosciuto) | 0/3 | **3/3** | 2,6 |
| «Metti un timer di cinque minuti» → `timer_imposta({cambia: imposta})` | 0/3 | **3/3** | 1,4–1,6 |
| «Ricordami alle diciotto di chiamare la mamma» → `promemoria_imposta({testo})` | 0/3 | **3/3** | 1,6–1,8 |
| «Aggiungi il latte alla lista della spesa» → `lista_aggiungi({lista: spesa})` | 0/3 | 0/3 | 1,0–2,3 |
| «Quanto fa dodici per sette?» → `calcola({expr: …})` | 2/3 | **3/3** | 1,1–1,5 |
| *Contrario*: «Aggiungi una cosa alla lista della spesa» (dato non deducibile) | chiede 3/3 | chiede 3/3 | 0,7–0,9 |
| *Contrario*: `web_cerca` con un errore interno (non correggibile) | detto 3/3 | detto 3/3, nessun giro | 0,4–0,5 |

- Corrette **18/21** contro 2/21. Prima il modello chiedeva l'argomento («ho bisogno di sapere
  su quale argomento vuoi…») o diceva «Aggiungo latte alla lista» senza farlo. La lista resta
  0/3 col 4B: il modello chiede «Cosa vuoi aggiungere?», una volta scrive la chiamata come
  testo («Chiami lista_aggiungi con cose="latte"…?»), una volta arriva al tetto e alla frase
  di ripiego; da riprovare col 26B della DGX.
- Le prime versioni: con il solo errore strutturato (senza la frase della persona e con la
  domanda detta subito) notizie 1/1 ma timer, lista, ansa e meteo con una domanda alla persona;
  con la frase della persona e la domanda trattenuta al primo giro i numeri sopra.
- **Latenza aggiunta** (4B locale): ogni passata di correzione 0,4–0,7 s; il caso riuscito
  costa la passata della chiamata giusta più quella della risposta (prima finiva subito, ma con
  una risposta sbagliata). Il contrario con il dato non deducibile paga una passata in più
  (0,67–0,91 s contro 0,30–0,47 s di prima) perché la domanda al primo giro aspetta; l'errore
  non correggibile niente. La frase d'attesa dei giri non è scattata (passate sotto i 2 s).
  Sulla DGX col 26B ogni passata vale ~1 s: con la frase della persona il caso vero dovrebbe
  risolversi in un giro (da misurare sul registro dei turni: regole `correzione_tool`,
  `correzione_avviso`).
- **A secco**: `prove/prova_dialogo_tool.py`, tra l'altro la chiamata vuota a ognuno dei 42
  tool con argomenti obbligatori del registro completo (errore strutturato, mai eseguito).

**Inventario voce ↔ agente** (§ 5):

| Dove | Prima | Ora |
|---|---|---|
| Strumenti dell'agente di codice e della ricerca: argomenti | nessun controllo; un obbligatorio assente arrivava allo strumento | `dialogo.controlla_strumento` contro lo schema dello strumento (obbligatori assenti, forme di enum e numeri), errore con esempio e `cosa_fare` |
| `_strumento` (eccezioni) | `{"errore": "TypeError: …"}` | `dialogo.errore_strumento`: `{ok: false, errore: "<strumento> non è riuscito: Tipo: messaggio"}` in una riga, con `cosa_fare` |
| Ricerca e grafo (eccezioni) | `{"errore": "KeyError"}` (solo il tipo) | come sopra, con il messaggio |
| Strumento sconosciuto (ricerca) | `{"errore": "strumento sconosciuto: x"}` | con `ok: false` e l'elenco degli strumenti in `cosa_fare` |
| Estensioni (`est_*`) verso la voce | argomenti mancanti → eccezione nell'estensione, «non è riuscita: KeyError: 'citta'» | lo schema del manifesto è il contratto: errore strutturato prima del container |
| Esiti dei lavori verso la voce (`lavoro_stato`, `lavoro_risultato`, annunci) | `motivo` già in parole; `errore` con il tipo dell'eccezione nei dati del lavoro | invariato: la voce legge `motivo`/`riassunto`; il tipo resta nel log e nei dati |
| Domande dell'agente a metà lavoro (`lavoro_rispondi`) | testo dell'agente in busta | invariato |

Restano (non semplici, da un lavoro a parte): il contratto unico dei risultati riusciti
(`docs/architettura-tool.md` § 6.1); un `cosa_fare` uniforme per gli errori scritti dai tool
stessi (oggi molti hanno solo `errore`); gli errori dell'estensione nel container
(`es.errore`, «TypeError: …» dalla sandbox) verso la voce, che restano la riga dell'eccezione.
