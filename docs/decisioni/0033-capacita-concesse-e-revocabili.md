# 0033. Le capacità delle estensioni si concedono e si revocano, invece di essere impossibili

- **Stato**: accettata (20/10/2026: il principio e le tre scelte di chi amministra, issue #193; la
  sera le risposte alle dieci domande dell'analisi);
  il **piano a passi** è una proposta, nell'analisi, da approvare. Nel codice non c'è ancora niente:
  fino al primo passo valgono il contratto e il piano di oggi, con i 12 impossibili. Cambia una
  parte della [0013](0013-estensioni-porta-stretta.md) (vedi «Cosa cambia nelle decisioni di prima»)
  e la risposta S10 del 12/10 sui messaggi verso l'esterno (roadmap 4.9).
- **Area**: [agenti-estensioni](../aree/agenti-estensioni.md),
  [sicurezza-politica](../aree/sicurezza-politica.md); codice da toccare (nei passi):
  `calliope/estensioni/contratto.py`, `porta.py`, `archivio.py`, `servizio.py`, `prompt.py`,
  `calliope/guardrail.py`, `calliope/agenti/ciclo.py` (`_piano`), `calliope/agenti/richiesta.py`,
  `calliope/requisiti.py`
- **Analisi e piano**: [`2026-10-20-capacita-concesse.md`](../ricerche/2026-10-20-capacita-concesse.md)

## Contesto

Il contratto delle capacità (`calliope/estensioni/contratto.py:90-114`, `IMPOSSIBILI`) elenca dodici
cose che un'estensione non può fare «per costruzione»: mandare messaggi fuori casa, il telefono, i
file della persona, la rete di casa, partire a orario, i pacchetti, la memoria di Calliope,
microfono e webcam, gli altri tool, i login, le pagine fatte in JavaScript, un modello. Se l'agente
ne nomina uno nel piano, il lavoro si chiude alla prima passata (`calliope/agenti/ciclo.py:2126-2139`);
la stessa lista fa dire «impossibile» all'analisi della richiesta (`calliope/agenti/richiesta.py:176`,
`:405-406`) e ferma uno sviluppo con il cuore «non si può» (`calliope/sviluppo.py:1350-1362`).

La certezza di non avere violazioni viene quindi dall'**assenza**: la porta stretta non ha un metodo
per farlo. La lista mescola due cose diverse: **divieti di politica** (credenziali, orari, invii,
file della persona, rete di casa, memoria di Calliope, altri tool), che la porta potrebbe esercitare
sotto controllo, e **limiti dell'infrastruttura** (JavaScript nel browser, un modello dentro
l'estensione, microfono e webcam, pacchetti, telefono), che nessuna concessione basta a superare.

Il 20/10 chi amministra ha chiesto un'estensione che usava capacità della lista (un login con un
token, una partenza a orario, un messaggio fuori casa), e il lavoro è stato negato. La sua richiesta:
«vorrei che si potesse fare tutto ma che sia tutto revocabile alla bisogna». Il caso è l'occasione;
la decisione riguarda il principio, non quell'estensione.

## Decisione

**La certezza viene dal controllo a ogni uso e dalla revoca: tutto è chiedibile, niente è dato per
costruzione.**

1. **L'estensione non ha poteri suoi.** Il container resta senza rete né segreti
   (`calliope/estensioni/esecuzione.py:132-142`); ogni capacità la esercita Calliope attraverso la
   porta stretta, che controlla la concessione **a ogni chiamata**.
2. **«Non concesso» non chiude il lavoro.** Un divieto di politica diventa una **richiesta
   dichiarata** nel piano e detta nell'analisi, prima del codice. Ciò che manca all'infrastruttura
   diventa «serve una capacità nuova», detto come tale e registrato, non «impossibile».
3. **Ogni concessione ha un ambito**: su cosa (un host, un account, una lista, una cartella, un
   tool), quali operazioni, quando (a voce, a orario, in secondo piano), quanto spesso (quote). È
   dichiarato nel manifesto e detto in parole nella scheda di revisione.
4. **Il peso dell'approvazione segue la classe di rischio**, cioè le classi per effetto della
   politica per valore (E0–E4, [0015](0015-sicurezza-per-valore.md)). **Leggere dati personali**
   (un account, i file di una persona, i suoi ricordi) vale **almeno E2**, anche se per l'effetto
   sarebbe una lettura: la riservatezza pesa come un effetto che resta (revisione della PR #195).
5. **Revocabile non vuol dire reversibile.** È **irreversibile** ciò che Calliope non sa riportare
   com'era: inviare fuori casa, pagare, cancellare fuori casa, cancellare o sovrascrivere senza copia
   i file della persona o un NAS di casa. Le irreversibili **non si concedono mai in anticipo**: si
   concede di **prepararle**, e l'atto finale chiede sempre la conferma al momento, con quello che sta
   per succedere detto da Calliope e non dall'estensione. Le cancellazioni dei **dati di Calliope**
   (`lista_togli`, `dati_cancella` e simili) diventano reversibili con un **cestino a tempo**, e quindi
   concedibili. La tabella di ciò che è irreversibile sta nel codice, per operazione, mai nel
   manifesto.
6. **I segreti li tiene Calliope** (un deposito), e la porta li usa per conto dell'estensione, che
   non li vede mai. Revocare vuol dire che Calliope li dimentica e, dove il fornitore lo permette, li
   revoca anche presso di lui.
7. **Anche l'autonomia è una concessione** (a orario, in secondo piano): a nome di chi l'ha chiesta,
   con i suoi permessi **del momento** (#53). Senza la persona presente nessuna domanda è possibile,
   quindi in autonomia si fa solo ciò che è concesso senza conferma.
8. **Ogni uso va nel registro** (cosa e quando, mai il contenuto) e nel cruscotto. Un uso fuori
   ambito o oltre le quote **sospende da solo** (la concessione o l'estensione: risposta 4) e lo
   dice. **I dati letti** da un account o dai file di una persona, quando Calliope li dice o li
   mostra, seguono le regole della conversazione in cui arrivano
   ([0028](0028-decisioni-roadmap-12-10.md), [0031](0031-conservazione-dei-minori.md),
   [0032](0032-valutazione-conserva-tutto.md)): si conservano come il resto di quel turno, per la
   stessa persona e per lo stesso tempo, e «dimentica» e `calliope conserva --svuota` valgono anche
   per loro. Alla revoca di un account Calliope chiede alla persona se vuole dimenticare anche ciò che
   le ha già letto.
9. **La revoca è a più livelli**: una concessione, un'estensione, un account, tutto; a voce e dal
   cruscotto. Una **versione nuova** dell'estensione richiede di nuovo le concessioni, come oggi i
   permessi «sempre» (`calliope/estensioni/archivio.py:227-228`).

**Le tre scelte di chi amministra (20/10)**:

- **Le irreversibili mai in anticipo** (punto 5).
- **Concede chi amministra**, con la frase di sfida; un familiare può chiedere. I dati o gli account
  di una persona si collegano **solo con lei presente**.
- **Le concessioni non scadono** fino alla revoca o a una versione nuova; il cruscotto le elenca e
  Calliope ricorda di tanto in tanto quelle attive.

**Concessione e attivazione.** La **concessione** è durevole: la dà chi amministra, non scade, si
toglie con la revoca o con una versione nuova. Per le capacità E4 serve in più l'**attivazione per
sessione d'uso** (risposta 1): la concessione resta, ma ogni sessione va attivata da capo. Non è una
scadenza della concessione.

**Le risposte di chi amministra alle dieci domande dell'analisi (20/10 sera)**:

1. **E4**: *[storico, prima versione della sera del 20/10: «comandi delicati della casa e scatto
   della webcam concedibili con la conferma per sessione d'uso»; corretta la stessa sera dopo la
   revisione della PR #195, perché contraddiceva le regole della casa e la visione]*. Decisione:
   - **i delicati della casa** (serrature, cancello, portone, porta, garage, basculante, gas, valvole, acqua, allarme e antifurto: gli E4 della casa, `valore._DELICATI`,
     `calliope/valore.py:176-177`, e `casa_sola_lettura_domini`, `casa_sola_lettura_classi` e
     `casa_nomi_delicati` della configurazione; per `calliope/casa/regole.py:9-10` «si leggono, non si comandano») **restano fra
     i «mai»** per le estensioni come per la voce, **finché non c'è il secondo fattore** (#52).
     **Disinserire l'allarme resta «mai» anche dopo** il secondo fattore
     ([0028](0028-decisioni-roadmap-12-10.md));
   - la **conferma per sessione d'uso** vale per la webcam e per le altre capacità E4 (oggi
     l'unica capacità E4 concedibile è la webcam): all'apertura
     dell'estensione, prima di partire, Calliope chiede di attivare i suoi permessi E4; col sì valgono
     per quella sessione, alla chiusura si spengono e la volta dopo si riattivano. La sessione è il
     tempo in cui la scheda è aperta (un'estensione con scheda, un gioco) o la conversazione
     (un'estensione usata solo a voce);
   - la conferma all'apertura la dà **chi usa l'estensione**, se ha il livello per quella capacità
     (altrimenti l'estensione parte senza le capacità E4, o non parte se senza non serve);
   - **ogni comando della casa** continua a chiedere la frase di sfida anche dentro la sessione, come
     oggi (`calliope/guardrail.py:243-249`): l'attivazione non la sostituisce;
   - una corsa a orario non ha un'apertura da parte di una persona, quindi **non usa capacità E4**;
   - le irreversibili restano diverse: conferma al momento di ogni atto.
2. **I «mai» delle altre decisioni** restano non concedibili, con il rimando (sotto, «Cosa cambia»).
   La webcam non è fra questi: vale il punto 1.
3. **L'atto finale** di una preparazione lo conferma la persona proprietaria dell'account; per un
   account della casa, chi amministra.
4. **Sospensione**: oltre le quote si ferma la sola concessione; fuori dall'ambito tutta
   l'estensione.
5. **Revocare non chiede la frase di sfida** (togliere potere è facile, darlo no); un familiare può
   sospendere le concessioni sui propri dati.
6. **Promemoria** delle concessioni attive: una volta al mese a chi amministra, e a ogni persona per
   quelle sui suoi dati.
7. **Tornando a una versione di prima** le concessioni si richiedono, come per una versione nuova.
8. **Minori e ospiti**: un minore non chiede concessioni; i dati di un minore si collegano solo con un
   tutore presente; nessuna concessione a nome di un ospite.
9. **Ordine delle capacità** (passi 7a e 7c del piano): posta, file della persona, rete di casa
   verso host precisi, browser senza testa, pacchetti, modello, telefono, webcam.
10. **I messaggi fuori casa** diventano chiedibili, sempre preparati e inviati solo con la conferma al
    momento (cambia la risposta S10 del 12/10, sotto).

## Cosa cambia nelle decisioni di prima

- **[0013](0013-estensioni-porta-stretta.md)** (porta stretta): restano il container senza rete né
  segreti, la porta come unica strada, i tool veri di Calliope con al più il livello familiare,
  l'impronta, l'approvazione con la sfida e il secondo parere che può solo alzare. Cambia il senso
  della porta: non è più un elenco chiuso di metodi che definisce cosa esiste, ma il punto in cui si
  controlla una concessione. Il file e la riga del README della 0013 lo segnano («in parte cambiata
  dalla 0033»). Il **tetto di 30 s** per chiamata della 0013 resta per le chiamate a voce e a
  orario; «restare accesa in secondo piano» lo contraddice ed è infrastruttura (un'esecuzione lunga,
  o una serie di chiamate brevi a intervalli): si decide nel passo dell'autonomia, non qui.
- **Il «sì, sempre» di oggi** (`calliope/estensioni/servizio.py:1031-1045`, `porta.py:125-126`) lo
  dà chi ha usato l'estensione, anche un familiare. Con la 0033 il «sempre» **diventa una concessione,
  e la dà solo chi amministra**; un familiare può dire «sì» **per quella volta**.
- **La revoca e la sospensione**: oggi la revoca dei «sempre» chiede la frase di sfida a chi non è
  riconosciuto come chi amministra (`servizio.py:636-639`), e un familiare non usa
  `estensione_gestisci` (`:599-601`). Con la 0033 **revocare non chiede la sfida**, e un
  **familiare può sospendere** le concessioni sui propri dati (risposta 5).
- **Le cancellazioni con «sì, sempre»**: oggi `lista_togli` e `dati_cancella` ammettono il «sempre»
  (`calliope/guardrail.py:258-269`). Con la 0033 (seconda revisione della PR #195): dal passo 1 **nessuno, nemmeno chi amministra, dà «sì, sempre»** su `lista_togli` e `dati_cancella` finché non c'è il cestino a tempo, e i «sempre» di oggi su queste regole **decadono al passo 1** (si conferma a ogni volta); con il cestino (passo 4) diventano concedibili
  (punto 5).
- **Le regole della casa** (`calliope/casa/regole.py`) e la **visione** (punto 9, il secondo fattore
  per porta e allarme): non cambiano. I delicati restano in sola lettura anche per le estensioni
  (risposta 1).
- **[0015](0015-sicurezza-per-valore.md)** (classi per effetto): non cambia; ne diventa l'uso per le
  estensioni. Oggi la porta ha una tabella sua (sicura, pericolosa, vietata: `calliope/guardrail.py`)
  e la politica per valore non la guarda (`calliope/estensioni/porta.py:153-155`). La classe di una
  concessione si prende da `valore.effetto` del tool che la porta chiama, o da una tabella del codice
  per le capacità nuove.
- **Risposta S10 del 12/10** (roadmap 4.9, «messaggi verso l'esterno dalle estensioni: nessuno per
  ora; più avanti solo notifiche alla web app»): i messaggi fuori casa diventano chiedibili, sempre
  preparati e mai inviati senza la conferma al momento. Le notifiche alla web app di casa non escono
  di casa e restano la prima cosa da fare.
- **Restano non concedibili** le cose che un'altra decisione dice «mai»: disinserire l'allarme
  ([0028](0028-decisioni-roadmap-12-10.md), visione), comandare i delicati della casa
  (serrature, cancello, portone, porta, garage, basculante, gas, valvole, acqua, allarme e antifurto (`valore._DELICATI`, `casa_sola_lettura_domini`, `casa_sola_lettura_classi`), più i nomi di `casa_nomi_delicati` (`calliope/config.py:830-832`: anche box, portoncino, sirene, idrico, caldaia)) finché non c'è il secondo fattore (regole della casa, risposta 1). Il «mai» lo decide `casa/regole.py` (`Regole.delicata`), non la classe: si leggono e non si comandano i domini di `casa_sola_lettura_domini`, le tapparelle, i sensori e le valvole con una classe di `casa_sola_lettura_classi`, e gli interruttori, i pulsanti, le valvole, le sirene e le tapparelle senza classe (o con classe door, gate o garage) il cui nome, stanza o alias contiene una parola di `casa_nomi_delicati`. `valore._DELICATI` dà solo la classe E4 alla domanda. Per esempio uno switch «caldaia» non si comanda anche se `_CLIMA` lo conta E2, mentre il termostato della caldaia (`climate`) si comanda. Restano «mai» anche la frase di sfida e i
  codici detti, un livello più alto di familiare alla porta. Si possono **chiedere** (la richiesta resta scritta), ma la
  risposta è quella decisione; cambiarla vuol dire cambiare quella decisione.

## Alternative considerate

- **Un'eccezione per il caso** (togliere «credenziali» dalla lista, o un'estensione speciale): scartata
  da chi amministra; la lista resterebbe un elenco deciso una volta per tutte, da riaprire a ogni caso.
- **Dare i poteri all'estensione** (un token nel container, la rete diretta verso un host) e contare
  sulla revoca: scartata. Un segreto dato al codice non fidato può essere copiato, e la revoca non si
  controlla più; la porta perderebbe il controllo per chiamata.
- **Concessioni a tempo** (scadenza automatica): scartata da chi amministra; al suo posto il
  cruscotto e il promemoria. Il rischio di concessioni dimenticate è nelle conseguenze.
- **Concedere anche le irreversibili, con un tetto** («al più un invio al giorno»): scartata. Una
  revoca arriva dopo il danno; il tetto limita quanti, non se.
- **Un modello che decide le concessioni**: no, per la stessa regola della 0015 (un giudice può solo
  stringere); il secondo parere resta un controllo che alza.

## Conseguenze

- **Il contratto e il piano cambiano linguaggio**: «da sola», «da concedere» (con l'ambito) e «serve
  una capacità nuova». L'agente chiede invece di chiudere; l'analisi lo dice alla persona prima del
  codice. È il passo che toglie il «negato» del caso vero.
- **Il codice nuovo è soprattutto della porta**: il modello dati della concessione, il controllo a
  ogni chiamata, la sospensione per anomalia, la revoca a più livelli, la coda delle azioni preparate,
  il deposito dei segreti e il login delegato. L'analisi elenca cosa c'è già da riusare.
- **Rischi nuovi**: dati personali dentro un'estensione, istruzioni ostili nei dati letti, autonomia
  senza la persona presente, segreti, concessioni dimenticate. L'analisi dice come li coprono i
  meccanismi che ci sono e cosa resta scoperto.
- **Principio 9** (niente cloud): un'estensione collegata a un servizio esterno dipende da internet
  per quel servizio; Calliope no. Come la ricerca web, è una scelta della persona, non una dipendenza
  del funzionamento.
- **Metodo** ([0019](0019-ombra-prima-di-accendere.md)): ogni passo ha un interruttore spento di
  serie e un criterio scritto prima di accenderlo; dove si può, prima in ombra.
- **Chiusura**: la decisione e l'analisi su main dopo la revisione; il piano approvato da chi
  amministra; una issue per passo aperta dopo l'approvazione. Collegate: #53 (estensioni a orario),
  #52 (secondo fattore), #124 (azioni del cruscotto), epic #89.

## Fonti

- Issue #193 (il principio e le scelte del 20/10).
- [`2026-10-20-capacita-concesse.md`](../ricerche/2026-10-20-capacita-concesse.md): i 12 impossibili
  uno per uno, cosa c'è da riusare, cosa manca, rischi, piano a passi, caso di verifica.
- [`2026-10-04-estensioni-e-guardrail.md`](../ricerche/2026-10-04-estensioni-e-guardrail.md) § 5, 9,
  10, 13; [0013](0013-estensioni-porta-stretta.md), [0015](0015-sicurezza-per-valore.md),
  [0019](0019-ombra-prima-di-accendere.md), [0028](0028-decisioni-roadmap-12-10.md).
