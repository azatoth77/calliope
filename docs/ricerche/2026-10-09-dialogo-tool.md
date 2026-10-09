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
  fine** (come `hold_request`): se arriva una chiamata si dice; se è una **domanda** alla
  persona («Di quale argomento vuoi le notizie?») si dice; altrimenti non si dice e il modello
  riceve `CORREZIONE_NUDGE` (rilegge l'errore, richiama o chiede), regola `correzione_tool`.
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

(Compilato a lavoro finito.)
