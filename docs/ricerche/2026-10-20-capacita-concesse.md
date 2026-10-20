# Capacità delle estensioni concesse e revocabili: analisi e piano (20/10/2026)

*Issue #193, decisione [0033](../decisioni/0033-capacita-concesse-e-revocabili.md). Solo documenti:
nessun codice cambia con questo lavoro. I riferimenti `file:riga` sono verificati su main al commit
`d2f0cc93` (20/10). Area: [agenti-estensioni](../aree/agenti-estensioni.md),
[sicurezza-politica](../aree/sicurezza-politica.md).*

## 1. Il principio, in breve

Oggi la sicurezza delle estensioni poggia su un'**assenza**: dodici capacità che la porta stretta non
ha, decise una volta il 05/10 e scritte nel contratto. Dal 20/10 poggia su un **controllo** e su una
**revoca**: tutto si può chiedere, niente è dato per costruzione, ogni uso passa da una concessione
che Calliope controlla a ogni chiamata e che si toglie a voce o dal cruscotto.

Tre idee reggono il resto:

- **l'estensione resta senza poteri**: il potere lo esercita Calliope per lei, quindi lo può anche
  smettere di esercitare (la revoca vale subito, senza fidarsi del codice dell'estensione);
- **revocabile non è reversibile**: quello che non si disfa (un messaggio partito, un pagamento, una
  cancellazione fuori casa) non si concede in anticipo, si concede di prepararlo;
- **il peso segue l'effetto**: più l'effetto è forte, più l'approvazione pesa, con la stessa scala
  E0–E4 della politica per valore.

Il caso vero del 20/10 (un'estensione per la posta di una persona, con login, partenza a orario e
risposte) compare solo al § 8, come una delle verifiche del piano.

## 2. Dove vivono oggi gli impossibili

La lista è una sola (`calliope/estensioni/contratto.py:90-114`, `IMPOSSIBILI`), con la versione per
i giochi (`_IMPOSSIBILI_GIOCO`, `:79-86`; `impossibili()`, `:318-323`). La usano quattro posti, e
tutti e quattro vanno cambiati insieme, o si contraddicono:

| Dove | Cosa fa con la lista | Riferimento |
|---|---|---|
| Contratto delle capacità (prompt dell'agente e `CAPACITA.md`) | sezione «Impossibile (dillo subito con piano(fattibile=false), con l'alternativa)» | `contratto.py:334-341`, `:426`, `:364` |
| Strumento `piano` dell'agente | una voce impossibile in `capacita_necessarie`, o `fattibile=false`, **chiude il lavoro** con «Non si può fare: … In alternativa: …» | `agenti/ciclo.py:2118-2139` |
| Analisi della richiesta, prima di partire | la lista va nel prompt dell'analista come «Impossibile: …», e un motivo scritto diventa l'esito `impossibile` | `agenti/richiesta.py:176-177`, `:405-406` |
| Requisiti dello sviluppo | `si_puo: false` per ciò che è «Impossibile»; se tutto il nucleo è così lo sviluppo non parte (regola `sviluppo_nucleo_impossibile`) | `requisiti.py:97`, `:115`; `sviluppo.py:1350-1362`; `tools/agenti.py:347` |

E sotto la lista, il vero confine: la porta accetta solo le azioni di `guardrail.AZIONI`
(`calliope/guardrail.py:61-64`); ogni altra è vietata con la regola `estensione_azione_sconosciuta`
(`:176-178`).

## 3. I dodici impossibili, uno per uno

Sintesi (il dettaglio nei paragrafi):

| Voce | Tipo | Classe proposta | Cosa è irreversibile | Da costruire |
|---|---|---|---|---|
| `email` | divieto di politica | E3 (esce) | l'invio | coda delle azioni preparate, connettore di un canale, deposito |
| `telefono` | limite dell'infrastruttura | (E3 se esistesse) | chiamare, mandare SMS | un canale verso il telefono vero (app nativa o modem): fuori portata |
| `file_persona` | divieto di politica | E2 leggere, E3 sovrascrivere | cancellare o sovrascrivere senza copia | un metodo della porta verso il satellite PC |
| `rete_locale` | divieto di politica | E1–E3 per dispositivo | comandi che cancellano o cambiano la rete | una rete privata ad host precisi dentro la porta |
| `orari_fissi` | divieto di politica | la classe delle operazioni, approvata come E3 | niente in autonomia | il pianificatore di #53 |
| `pacchetti` | limite dell'infrastruttura | — (si decide quando si costruisce la versione) | — | un catalogo di pacchetti verificati nella versione |
| `memoria` | divieto di politica | E0 (lettura), con la categoria del dato | — | metodi della porta verso i tool di lettura |
| `microfono_camera` | limite dell'infrastruttura, con un divieto forte sopra | E4 | — | uno scatto alla volta dal satellite PC |
| `altri_tool` | divieto di politica | quella del tool (`valore.effetto`) | quella del tool | la porta li sa già chiamare |
| `credenziali` | divieto di politica | quella delle operazioni dell'account | ciò che l'account permette di inviare, pagare, cancellare | deposito, login delegato, connettori |
| `javascript` | limite dell'infrastruttura | E0 | — | un browser senza testa dietro `RetePubblica` |
| `modello` | limite dell'infrastruttura | E0, l'uscita resta un dato non fidato | — | un metodo della porta verso un modello locale, con l'arbitro |

Sette divieti di politica e cinque limiti dell'infrastruttura. Diversi divieti di politica sono
**anche** un pezzo mancante (un divieto che oggi coincide con l'assenza di un metodo): toglierne il
divieto non basta, serve la strada. Per questo il piano (§ 7) separa la concessione (il modello e il
controllo, uguali per tutti) dalle capacità nuove (una alla volta).

### 3.1 `email`: mandare email, SMS, messaggi o notifiche fuori casa

- **Tipo**: divieto di politica. Un'osservazione onesta: un invio verso un'API esiste già, con
  `rete_invia` (POST JSON verso un host del manifesto, in https, **con la frase di sfida a ogni
  invio**: `guardrail.py:291-302`). Quello che manca davvero è l'accesso (un account: § 3.10) e il
  protocollo (la posta non è HTTP: `RetePubblica` esce solo sulle porte 80 e 443,
  `calliope/web/rete.py:9-13`).
- **Capacità concessa**: «preparare messaggi» su un canale (l'account di posta di una persona, la
  notifica alla web app di casa); ambito: i destinatari (un elenco chiuso, oppure «chi ha scritto il
  messaggio a cui si risponde»), le operazioni (preparare; l'invio è un atto a parte), quando (a voce
  o a orario), quante bozze al giorno.
- **Classe**: E3 (esce di casa). La notifica alla web app di casa **non esce di casa**: E2,
  concedibile in anticipo come la scheda personale di oggi (è la prima cosa che chiedeva la risposta
  S10 del 12/10).
- **Revoca**: la concessione; le bozze in coda si tolgono con lei.
- **Irreversibile**: l'invio. Si concede di preparare; l'invio lo conferma la persona al momento,
  con destinatario e testo letti dalla bozza che tiene Calliope (§ 5.6), mai dalla frase
  dell'estensione.

### 3.2 `telefono`: telefonare, leggere chiamate o messaggi del telefono

- **Tipo**: limite dell'infrastruttura. Il telefono di casa è un satellite nel browser (una PWA:
  `calliope/schermi/telefono.py`), e una pagina web non legge le chiamate né gli SMS né telefona.
- **Cosa servirebbe**: un'app nativa sul telefono, o un modem GSM sul server (citato nella visione
  per l'allarme e rimandato). Nessuno dei due è in roadmap. Se arrivasse: leggere chiamate e
  messaggi è un dato della persona (collegato solo con lei presente); chiamare e mandare un SMS sono
  invii (irreversibili, preparati come al § 3.1).
- **Oggi**: resta «serve una capacità nuova», detto come tale.

### 3.3 `file_persona`: leggere o scrivere i file del PC o i documenti della persona

- **Tipo**: divieto di politica, più una strada da costruire. A voce i file del PC ci sono già
  (`pc_cerca_file`, `pc_apri_file`, anche dal satellite: `calliope/pc/`), e ci sono gli allegati e il
  cassetto dei file per persona; la porta non ha un metodo per arrivarci.
- **Capacità concessa**: «leggere i file di una cartella» del PC di una persona (il satellite PC di
  quella persona, una cartella precisa, i tipi di file, una dimensione massima); «scrivere» solo in
  una cartella dell'estensione; quando: a voce, oppure a orario se concesso a parte.
- **Classe**: E2 per leggere (dato della persona: contamina l'esecuzione con la sua categoria, come
  oggi l'agenda); E3 per scrivere fuori dalla cartella dell'estensione.
- **Revoca**: la concessione, oppure tutte quelle di quel PC.
- **Irreversibile**: cancellare o sovrascrivere un file senza una copia. Si concede di preparare
  («sostituisco questi tre file?»), l'atto si conferma al momento.
- **Presenza**: la cartella di una persona si collega solo con lei presente (scelta del 20/10); quella
  di un minore solo con un tutore presente (§ 10, decisione 8).

### 3.4 `rete_locale`: dispositivi della rete di casa o dell'ufficio

- **Tipo**: divieto di politica, il più difeso oggi. `pagina.scarica` e `RetePubblica` rifiutano
  nomi locali, indirizzi privati, rebinding, e dal 08/10 anche i nomi pubblici della casa
  (`calliope/web/rete.py:8-22`, regola `rete_casa_pubblica`); il banco d'attacco
  (`prove/prova_estensioni_attacchi.py`) ha **0 passaggi su 76**.
- **Capacità concessa**: «parlare con un dispositivo» preciso (un host o un indirizzo con la porta,
  i metodi, un elenco chiuso di percorsi o comandi), mai una rete intera. Per i dispositivi che Home
  Assistant conosce già resta la strada di oggi (`casa_stato`, `casa_comando`).
- **Classe**: per dispositivo, con la tabella della casa come guida (`valore._casa`,
  `calliope/valore.py:170-188`: luci E1, clima E2, nomi delicati E4, con la conferma per sessione d'uso del § 10, decisione 1); il resto E3. Una **telecamera**
  è un'immagine delle persone di casa: va col § 3.8, non qui.
- **Revoca**: la concessione; il dispositivo esce dall'elenco della rete privata della porta.
- **Irreversibile**: i comandi che cancellano (un NAS) o che cambiano la rete (il router): preparati.
- **Da costruire**: una «rete privata» nella porta, con l'elenco degli host concessi e gli stessi
  controlli di `RetePubblica` per tutto il resto. Il banco d'attacco va esteso: per ciò che non è
  concesso deve restare 0.

### 3.5 `orari_fissi`: partire da sola a orari fissi o restare accesa in secondo piano

- **Tipo**: divieto di politica (l'autonomia) e pezzo mancante (nessuna pianificazione esiste per le
  estensioni). Il progetto breve è la issue #53.
- **Capacità concessa**: «autonomia»: quando (una ricorrenza, oppure «in secondo piano» con un
  intervallo minimo), a nome di chi l'ha chiesta e con i suoi permessi **del momento** (riletti dai
  profili a ogni corsa: un familiare tolto o un minore in pausa e la corsa salta), il risultato solo
  a quella persona (#53, punto 3).
- **Classe**: quella delle operazioni che l'estensione fa, ma l'approvazione dell'autonomia pesa
  come una E3 anche per un'estensione che legge soltanto: nessuno è lì a guardare.
- **Revoca**: «togli la pianificazione», o tutta l'estensione.
- **E4**: mai in autonomia, perché valgono solo per una sessione aperta da una persona (§ 10,
  decisione 1).
- **Irreversibile**: niente in autonomia. Una pericolosa senza la persona presente è vietata, come
  già nel ricollaudo (`calliope/estensioni/porta.py:92-104`, regola `ricollaudo_senza_conferme`); una
  preparazione resta in coda per la persona.

### 3.6 `pacchetti`: installare pacchetti (pip) o programmi

- **Tipo**: limite dell'infrastruttura. Il container è in sola lettura e senza rete
  (`esecuzione.py:132-142`), l'immagine è fissa (`setup/linux/sandbox/Dockerfile`).
- **Cosa servirebbe**: un **catalogo** di pacchetti in puro Python con versione e impronta, copiati
  nella versione dell'estensione e contati nella sua impronta (`archivio.impronta`), così che una
  versione nuova li riapprova; oppure un'immagine con più librerie. Rischi: la catena di fornitura e
  le librerie con codice nativo (principio 4, Windows su ARM).
- **Non è una concessione d'uso**: si decide quando si costruisce e si approva la versione. Resta
  «serve una capacità nuova» finché il catalogo non c'è.

### 3.7 `memoria`: ricordi, rubrica, archivio dei documenti, biblioteca

- **Tipo**: divieto di politica. La porta sa già chiamare i tool veri (`porta.py:158-176`); mancano
  solo i metodi.
- **Capacità concessa**: lettura di una fonte precisa, con un ambito (la biblioteca; l'archivio dei
  documenti di casa per un tipo di documento; la rubrica dell'ufficio; i ricordi **di una persona**,
  collegati solo con lei presente).
- **Classe**: E0 per l'effetto. Il rischio qui è la riservatezza, non l'effetto: per questo la
  lettura **contamina** l'esecuzione con la categoria del dato (come oggi `casa`, `agenda`,
  `liste:<nome>`: `guardrail.categoria_lettura`, `:140-143`), e i dati letti escono solo lungo un
  flusso approvato. La biblioteca è pubblica: non contamina.
- **Revoca**: la concessione. **Irreversibile**: niente (sola lettura; scrivere un ricordo è E2 e
  va chiesto a parte).

### 3.8 `microfono_camera`: microfono, webcam, schermo o tastiera del PC

- **Tipo**: limite dell'infrastruttura con un divieto forte sopra. Lo scatto della webcam e dello
  schermo esiste per la voce, col PC di chi parla (`calliope/pc/cattura.py`, dal 16/10, #100);
  l'audio lo ascolta solo Calliope, con le sue regole (half-duplex, la stanza della
  [0029](../decisioni/0029-conversazione-di-stanza.md)).
- **Capacità concessa**: al più **uno scatto alla volta**, con la persona presente e davanti al suo
  PC; mai un flusso continuo, mai il microfono (che resta di Calliope). Classe E4 (riguarda la
  fiducia e le persone di casa): vale la **conferma per sessione d'uso** (§ 10, decisione 1), quindi
  mai a orario.
- *[storico fino al 20/10 sera: «chiede a chi amministra se vuole tenerla fra i "mai"»]*: deciso il
  20/10, la webcam non è fra i «mai» (§ 10, decisione 2); resta l'ultima del passo 7, perché è la
  voce più vicina a «sorveglianza».

### 3.9 `altri_tool`: chiamare altre estensioni o altri tool di Calliope

- **Tipo**: divieto di politica (le catene e il «confused deputy» del § 9 del progetto del 04/10).
  La strada c'è: la porta esegue già con `ToolRegistry.call` e con il livello di chi ha usato
  l'estensione, al più familiare (`porta.py:143-176`; `servizio.py:440-442`).
- **Capacità concessa**: un tool **per nome**, con gli argomenti vincolati (valori fissi o un elenco)
  e le quote; un'altra estensione per nome e **versione** (la sua impronta), a un livello solo (niente
  catene oltre la prima, niente cicli).
- **Classe**: quella del tool, da `valore.effetto` (`calliope/valore.py:254-268`, tabella `EFFETTI`
  a `:222-251`). Le E0 (`meteo_leggi`, `calcola`, `data_calcola`, `biblioteca_cerca`, `notizie`) si
  concedono come una lettura; i tool che cambiano la fiducia (E4: `registra_utente`,
  `minore_gestisci`, `schermo_gestisci`) e quelli che gestiscono le estensioni o le installazioni
  (E3: `estensione_gestisci`, `installa_*`) **non si concedono** a un'estensione: sarebbe il codice
  non fidato che si allarga da sé.
- **Revoca** e **irreversibile**: quelli del tool chiamato.

### 3.10 `credenziali`: accedere a siti con utente e password, token, chiavi o cookie

- **Tipo**: divieto di politica, più tre pezzi mancanti (deposito, login delegato, connettori).
  Oggi la porta dice di sé «Nessun segreto passa da qui» (`porta.py:22`), e il container non ha
  segreti né variabili dell'host.
- **Capacità concessa**: «un account» di un servizio, **di una persona** (o della casa), collegato
  con lei presente; ambito: le operazioni (leggere, cercare, preparare), gli oggetti (una cartella
  della posta, un calendario), la frequenza.
- **Classe**: quella delle operazioni. Leggere è E0 per l'effetto, ma il dato è della persona: la
  lettura contamina con la categoria `account:<nome>` e i dati escono solo lungo un flusso
  approvato. Preparare è E2; gli atti (inviare, pagare, cancellare) E3 e irreversibili.
- **Revoca**: Calliope dimentica il segreto (il deposito lo cancella) e, dove il fornitore ha
  un'API per farlo, lo revoca anche presso di lui; dove non c'è, Calliope lo dice («revocalo anche
  dal sito»).
- **Irreversibile**: ciò che l'account permette di inviare, pagare o cancellare: solo preparato.
- **Un limite da dire**: il token può quasi sempre più di quanto la concessione permette. La porta
  stringe davvero solo se capisce l'operazione: vedi § 5.3 (connettori tipizzati contro un token in
  intestazione).

### 3.11 `javascript`: dati che una pagina mostra solo con JavaScript

- **Tipo**: limite dell'infrastruttura. `rete_leggi` restituisce il testo grezzo della risposta
  (`porta.py:267-311`); nessuno esegue il JavaScript della pagina.
- **Cosa servirebbe**: un browser senza testa in un container a parte, con `RetePubblica` come unica
  uscita (stesse regole, stesso registro), che restituisce solo il testo della pagina. Costi:
  centinaia di MB d'immagine, memoria e CPU a ogni pagina, un codice nativo da verificare su ARM
  (principio 4). Classe E0 (lettura pubblica).
- **Oggi**: resta «serve una capacità nuova»; l'alternativa di oggi (un'API pubblica, una pagina con
  i dati nell'HTML) resta la prima proposta.

### 3.12 `modello`: usare un modello linguistico dentro l'estensione

- **Tipo**: limite dell'infrastruttura. Un precedente c'è: il secondo parere chiama il modello
  dell'agente dalla parte di Calliope, con un tempo massimo (`guardrail.py:348-398`).
- **Cosa servirebbe**: un metodo della porta («riassumi», «estrai», «classifica») verso un modello
  locale, con l'arbitro della GPU (la contesa con la voce, #53), quote al giorno, e l'uscita trattata
  come dato non fidato che torna all'estensione. Il modello non chiama tool: ogni azione resta una
  chiamata alla porta, controllata.
- **Classe**: E0; il testo dato al modello resta in casa (il modello è locale), ma conserva la sua
  categoria (contaminazione).
- **Profilo ridotto da 8 GB** ([0028](../decisioni/0028-decisioni-roadmap-12-10.md)): lì la memoria
  della GPU non basta per un modello in più; la capacità c'è solo dove il piano della memoria la
  permette.

## 4. Cosa c'è già da riusare

Il principio nuovo non parte da zero: una buona metà delle sue parti esiste, con un nome diverso.

| Pezzo | Cosa fa oggi | Dove | Come si riusa |
|---|---|---|---|
| Container senza poteri | `--network none`, sola lettura, utente non root, `--cap-drop ALL`, niente variabili dell'host | `estensioni/esecuzione.py:132-142` | non cambia: è il punto 1 della decisione |
| Porta stretta | ogni richiesta → guardrail → tool veri → registro; vietata, pericolosa (si ferma e chiede), sicura | `estensioni/porta.py:78-114`, `:189-206` | diventa il punto del controllo della concessione |
| Tool veri col livello di chi usa | `ToolRegistry.call` con un contesto della porta, livello al più familiare, politica dei tool spenta per la porta | `porta.py:143-176`; `servizio.py:440-442` | strada per `altri_tool` e `memoria` |
| Guardrail della porta | scope del manifesto, filtri (stanze, liste), quote per esecuzione (50 richieste, 3 comandi, 10 di rete), sfida per casa e invii | `guardrail.py:61-75`, `:171-310` | le quote diventano quote della concessione; le regole restano |
| Flussi e contaminazione | una lettura personale contamina l'esecuzione; la rete solo lungo un flusso approvato, in https; i dati propri restano contaminati | `guardrail.py:146-168`, `:279-290`; `porta.py:193-203`; `archivio.py:317-338` | la categoria di un account o della memoria di una persona è una categoria in più |
| Dati riservati nel traffico | ricordi e dati privati mai nel traffico, anche a pezzi; argomenti riservati = niente rete | `web/riservati.py` (`Riservati.trova`); `servizio.py:453-458` | anche i segreti del deposito vanno tra i riservati |
| Secondo parere | il modello dell'agente può solo alzare una sicura a pericolosa | `guardrail.py:348-398` | stesso ruolo sugli usi delle concessioni con testo libero |
| `piano` e `chiedi_permesso` | il piano dichiara capacità e scope; i permessi sensibili (flussi, POST, comandi della casa) l'agente non se li dà, li chiede alla persona; un permesso fuori dal piano rifiuta la consegna | `agenti/ciclo.py:349-368`, `:375-407`, `:2084-2210`, risposta a `:1265-1279` | è già il gesto «chiedere invece di prendere»: va esteso dalle voci della porta a tutte le capacità |
| Scope e permessi in parole | il manifesto a scope, gli atomi dei permessi, i permessi in parole e quelli nuovi rispetto alla versione approvata | `estensioni/manifesto.py` (`normalizza_permessi`, `atomi`, `permessi_in_parole`, `permessi_nuovi`) | la concessione si dichiara nel manifesto con la stessa forma |
| Scheda di revisione | permessi in parole, chi la usa, analisi del codice, test, differenze | `servizio.py:1190-1252` | dice anche le concessioni, con la classe e cosa resta preparato |
| Chi approva | un gioco puro anche un familiare; il resto solo chi amministra, con la sfida | `servizio.py:890-971` (`approvabile_da_familiare` a `:913`, sfida a `:924-930`) | è la scelta del 20/10: concede chi amministra |
| Frase di sfida e conferme | tre parole e un numero; il «sì» breve di chi amministra; la proposta valida per più turni | `conferme.py` (`chiedi_conferma` `:263`, `e_admin` `:131`, `admin_confermato` `:136`) | per l'approvazione e per gli atti finali |
| Conferma di un'azione della porta | solo chi ha usato l'estensione, mai nella stessa risposta della domanda, sfida se la regola la vuole, scadenza `estensioni_conferma_s` (120 s) | `servizio.py:1026-1061`; `config.py:1513` | è l'atto finale di una preparazione (§ 5.6) |
| «Sì, sempre» | concessione per persona, regola, bersaglio e versione; decade con una versione nuova; revoca per estensione | `archivio.py:293-314`, decadenza a `:227-228` | il germe del modello dati: va generalizzato |
| Host concessi alle sonde | il «sì» a `chiedi_permesso` per un host lo rende noto alle sonde | `sonde.py:189` (`concedi`), `:159` (`host_noti`) | un'altra concessione, oggi a parte |
| Registro delle decisioni | ogni decisione della porta con regola, classe, esito e chi | `porta.py:130-141`; `archivio.py:341-347` (`decisioni.jsonl`) | registro degli usi (ma va ridotto: § 5.8) |
| Registro delle uscite | una riga per richiesta di rete, fatta o bloccata; solo l'host, mai percorso né query | `web/rete.py:23-26`, `:303-320` (`uscite.jsonl`) | il modello per «cosa e quando, mai il contenuto» |
| Disattiva, riattiva, indietro, revoca, rimuovi | a voce con `estensione_gestisci`; la sfida per chi non è riconosciuto come amministra | `servizio.py:582-676` (sfida `:636-639`, disattiva `:646`, indietro `:657`, revoca `:669`, rimuovi `:673`); `archivio.py:241-279` | la revoca a più livelli parte da qui |
| Impronta a ogni esecuzione | file cambiati = non parte e si disattiva | `servizio.py:286-305`; `archivio.py:281-290` | lega la concessione alla versione |
| Classi per effetto | E0–E4 per ogni chiamata, E3 senza effetto dichiarato | `valore.py:167`, `:222-268` | la classe di una concessione |
| Le estensioni che leggono soltanto | una lettura per la politica dei tool | `servizio.py:1522-1564` (`_agisce`, `_classe`) | stessa distinzione per le concessioni |
| Scheda solo personale con dati personali | un'esecuzione contaminata mostra solo sugli schermi personali di chi l'ha usata | `servizio.py:565-580` | il risultato di un account va solo alla sua persona |
| Pericolose senza la persona | nel ricollaudo niente domande: la pericolosa diventa vietata | `porta.py:92-104` | la regola dell'autonomia |
| File dei segreti | il token di Home Assistant fuori da git, in `segreti.yaml` o in una variabile d'ambiente | `config.py:1715-1718`; `casa/__init__.py:16-40` | il precedente del deposito |
| Promemoria periodico | gli sviluppi sospesi detti una volta al giorno a chi amministra | `sviluppo.py:2137` (`promemoria_giorno`) | il promemoria delle concessioni attive |
| Cruscotto | estensioni da approvare in sola lettura; due azioni con gettone a due tocchi, 60 s, 6 al minuto | `schermi/cruscotto.py:52-54`, `:282-319`, `:475-494` | l'elenco delle concessioni; la revoca è un'azione che restringe (#124) |
| Secondo fattore | progetto del 06/10, non realizzato; il gradino proposto deriva dalla classe d'effetto | #52; `docs/ricerche/2026-10-06-secondo-fattore.md` | le E3–E4 lo chiederanno quando c'è |
| Estensioni a orario | progetto breve (risultato solo alla persona, notte, `quiete()`) | #53; `arbitro_memoria.py:582` (`quiete`); `minori.py:173` (orari) | è il passo dell'autonomia |

## 5. Cosa manca

### 5.1 Il modello dati della concessione

Una concessione, proposta (accanto a `indice.json`, in `concessioni.json`, scritta in modo atomico
come l'indice con `persistenza.scrivi_json`):

- `id`, `estensione`, `versione` e la sua `impronta` (una versione nuova la invalida);
- `capacita`: la voce del catalogo (§ 5.7), per esempio `account`, `rete_casa`, `tool`, `autonomia`;
- `ambito`: `oggetto` (host, account, cartella, lista, tool, dispositivo), `operazioni` (un elenco
  chiuso per capacità), `quando` (`voce`, `orario` con la ricorrenza, `secondo_piano`), `quote` (per
  esecuzione e al giorno);
- `classe` (E0–E4, calcolata dal codice, mai dal manifesto) e `preparate`: le operazioni
  irreversibili, che si concedono solo come preparazione;
- `a_nome_di` (la persona dei dati o dell'account, o «casa»), `chiesta_da`, `concessa_da` (chi
  amministra), `presente` (la persona dei dati era presente al collegamento), `quando`;
- `stato`: `attiva`, `sospesa` (con il motivo e il momento), `revocata`;
- `segreto`: un riferimento al deposito, **mai il valore**;
- `usi`: i contatori per le quote e l'ultimo uso.

Il «sì, sempre» di oggi (`archivio.py:300-306`) diventa una concessione con `capacita` uguale alla
regola del guardrail e `oggetto` uguale al bersaglio: così il passo 0 si prova in ombra su ciò che
c'è.

### 5.2 Il controllo a ogni chiamata

Oggi la porta guarda i `permessi` del manifesto approvato (`porta.py:80-81`). Domani guarda prima la
concessione: c'è, è attiva, la versione e l'impronta sono quelle, l'operazione è nell'ambito, il
«quando» è quello di adesso (a voce o a orario), le quote non sono superate. Poi il guardrail di oggi
decide come prima (sicura, pericolosa, vietata). Il controllo è deterministico, nel codice, con un
nome di regola per ogni esito (`concessione_assente`, `concessione_fuori_ambito`,
`concessione_quota`, `concessione_sospesa`…), sotto il millisecondo come la politica.

### 5.3 Il deposito dei segreti, il login delegato e i connettori

- **Deposito**: un file per installazione fuori da git, con i permessi privati (600), un segreto per
  account e persona; mai nel registro, mai nel risultato, mai nel container; i valori vanno anche tra
  i riservati (`Riservati`), così non escono nemmeno a pezzi.
- **Login delegato**: il collegamento si fa sullo **schermo personale della persona** (non a voce:
  un token non si detta), con lei presente; i modi dipendono dal servizio (una password per le app,
  un token personale, un flusso a codice del dispositivo). Non so ancora quali servizi offrono cosa:
  va visto servizio per servizio, quando si costruisce il connettore.
- **Connettori tipizzati, non un token in intestazione**. Due strade: (a) la porta aggiunge il token
  a ogni richiesta HTTP verso l'host concesso; (b) un connettore per tipo di servizio, scritto e
  provato da Calliope (non dall'agente), con operazioni tipizzate (`elenca`, `leggi`, `prepara`).
  Con (a) la porta non sa se una richiesta legge o invia, e l'ambito «solo lettura» vale solo se il
  token stesso è di sola lettura. Proposta: (b) come strada principale; (a) solo per GET verso un
  host e un prefisso di percorso, con un token di sola lettura, detto nella scheda come «forma
  debole».
- **Revoca presso il fornitore**: dove c'è un'API, il connettore la chiama; dove non c'è, Calliope
  lo dice e il deposito dimentica comunque.

### 5.4 La revoca a più livelli

Oggi c'è la revoca dei «sempre» di un'estensione (`servizio.py:669-672`), la disattivazione e
l'eliminazione. Mancano: una concessione sola; tutte quelle di un account o di una persona
(attraversando le estensioni); «tutto» (tutte le concessioni, tutte le estensioni ferme). A voce si
fa con azioni nuove di `estensione_gestisci` (nessun tool nuovo: il conto di 75 schemi e la
[0009](../decisioni/0009-tool-uguali-per-ogni-livello.md) restano); dal cruscotto con le azioni che
restringono di #124. Revocare è una restrizione: deciso il 20/10 (§ 10, decisione 5), **revocare
non chiede la frase di sfida** (togliere potere è facile, darlo no), e un familiare può sospendere
le concessioni sui propri dati.

### 5.5 La sospensione per anomalia

Un uso fuori ambito o oltre le quote oggi è una richiesta vietata e registrata, e l'esecuzione va
avanti. Domani, oltre a vietarla, sospende (deciso il 20/10, § 10, decisione 4): **oltre le quote
la sola concessione**, **fuori dall'ambito tutta l'estensione** (è il segno di un codice che cerca
di allargarsi); e lo dice: alla persona della concessione al suo
primo turno riconosciuto, sul suo schermo personale e nel cruscotto. Si riattiva solo a voce, da chi
amministra. Le soglie si misurano prima in ombra (§ 7, passo 2).

### 5.6 La coda delle azioni preparate

Per le irreversibili serve un posto dove l'estensione **lascia** l'azione invece di farla: Calliope
tiene l'azione strutturata (cosa, verso chi, il contenuto), la mostra sullo schermo personale della
persona e la dice in breve; l'atto parte solo con la conferma della persona proprietaria
dell'account (per un account della casa, di chi amministra: § 10, decisione 3), con la frase di sfida
per le E3–E4, con le regole di oggi (solo lei, mai nella stessa risposta della domanda, scadenza). Il
testo della conferma lo compone Calliope dai campi dell'azione, mai dalla frase dell'estensione:
così un dato ostile letto dall'estensione non sceglie le parole della domanda. In autonomia le
preparazioni restano in coda, con un tetto e una scadenza.

### 5.7 Contratto, prompt, analisi e requisiti che chiedono

- **Contratto**: le sezioni diventano «da sola», «da concedere» (con l'ambito da dichiarare e la
  classe, generata dal codice come oggi con `classe_detta`, `contratto.py:131-158`) e «serve una
  capacità nuova» (con l'alternativa di oggi). La lista `IMPOSSIBILI` diventa un **catalogo** con lo
  stato di ogni voce: `offerta` (la porta la sa esercitare), `da_costruire` (divieto tolto, strada
  mancante, o limite dell'infrastruttura), `mai` (un'altra decisione: § 10).
- **Piano**: una voce `offerta` va in `chiedi_permesso` con l'ambito, e il lavoro continua; una voce
  `da_costruire` chiude ancora il lavoro, ma con «serve una capacità nuova: …» e una riga per chi
  amministra (il cruscotto, o una issue); una voce `mai` chiude con il rimando.
- **Analisi della richiesta**: le capacità da concedere si dicono alla persona **prima** del codice,
  nella proposta («le servirà l'accesso in lettura alla tua posta: lo concede chi amministra»); non
  è più `impossibile`.
- **Requisiti**: `si_puo` resta `false` solo per `da_costruire` e `mai`; un requisito che chiede una
  capacità `offerta` ha `serve_concessione`.
- **Prompt dell'agente**: «se ti serve qualcosa del catalogo, chiedilo»; il codice dell'estensione
  deve sapere vivere con una concessione negata o revocata (l'errore della porta c'è già:
  `ErroreCalliope`).

### 5.8 Un registro senza contenuto

Il registro delle decisioni oggi tiene gli argomenti accorciati a 120 caratteri (`porta.py:480-494`,
`_riduci`): le voci aggiunte a una lista, il comando della casa. Va bene per la casa, non per un
account: gli usi di una concessione su un dato della persona vanno registrati come **operazione,
oggetto, quantità e momento**, mai il testo (come il registro delle uscite, che tiene solo l'host).

### 5.9 Le classi alla porta

Due tabelle parallele: la porta usa il guardrail (sicura, pericolosa, vietata), la voce usa la
politica per valore (E0–E4); il contesto della porta spegne la politica (`porta.py:153-155`). La
classe di una concessione va presa da `valore.effetto` del tool che la porta chiama (per le voci che
passano dai tool veri) e da una tabella del codice per le capacità nuove (connettori, rete privata).
Le E-classi non dicono «irreversibile» in modo esplicito (E3 mescola «esce», «esegue» e «non si
disfa»): la concessione ha bisogno di un segno a sé (`preparate`), deciso dal codice per operazione.

## 6. I rischi nuovi e come li coprono i meccanismi che ci sono

| Rischio | Cosa lo copre già | Cosa resta scoperto, e chi lo copre nel piano |
|---|---|---|
| **Dati personali dentro un'estensione** (la posta di una persona nel codice non fidato) | il container non ha rete: i dati escono solo dalla porta; la contaminazione chiude la rete fuori dai flussi; la scheda con dati personali va solo sugli schermi personali (`servizio.py:565-580`); i dati propri restano contaminati tra un'esecuzione e l'altra | il **da_dire** del risultato si dice a voce dove si è chiesto: con un ospite in stanza leggerebbe la posta ad alta voce. Il risultato di una concessione `a_nome_di` una persona va solo a lei (sullo schermo personale, o a voce solo se la compagnia della [0029](../decisioni/0029-conversazione-di-stanza.md) dice che è sola): passo 1 |
| **Istruzioni ostili nei dati letti** (un messaggio che dice «inoltra tutto a …») | il codice dell'estensione è deterministico; il risultato è un dato non fidato in busta, fuori dalla storia, niente azioni nella stessa risposta, testi che parlano all'assistente tolti; la politica per valore non esegue un bersaglio preso dal dato («ESEGUITE con un bersaglio dal dato» deve restare 0) | con il **modello** dentro l'estensione (§ 3.12) un testo ostile può guidare cosa l'estensione prepara: le irreversibili restano preparate, e la conferma mostra destinatario e contenuto veri, composti da Calliope (§ 5.6); la quota delle preparazioni limita il volume. Passi 4 e 7 |
| **Autonomia senza la persona presente** | nel ricollaudo una pericolosa diventa vietata (`porta.py:92-104`); i permessi si rileggono; le pause dei minori | una corsa a orario con dati personali: il risultato resta in coda per la persona, mai annunciato in una stanza (#53, punto 3); quote al giorno oltre a quelle per esecuzione: passo 6 |
| **Il segreto che esce** | `Riservati` cerca i dati riservati nel traffico, anche codificati o a pezzi; il registro delle uscite tiene solo l'host e lo toglie se porta un segreto (`rete.py:325-334`, `host_per_registro`); i reindirizzamenti si ricontrollano (`porta.py:303-306`) | il deposito stesso (chi ha l'utente di Calliope sulla DGX ha i segreti, come oggi il token di HA); il token con più poteri della concessione (§ 5.3): passo 5 |
| **Concessioni dimenticate** (non scadono, scelta del 20/10) | nessuno, oggi i «sempre» non si elencano da nessuna parte | il cruscotto le elenca con l'ultimo uso; il promemoria una volta al mese a chi amministra, e a ogni persona per quelle sui suoi dati (§ 10, decisione 6); una concessione mai usata da molto tempo si dice per prima: passo 2 |
| **Confused deputy** (un familiare fa concedere a nome di un altro) | approvare solo chi amministra con la sfida; la conferma solo da chi ha usato l'estensione | i dati di una persona si collegano solo con lei presente (scelta del 20/10): il collegamento avviene sul suo schermo personale, con la sua voce riconosciuta: passo 5 |
| **Una versione nuova con lo stesso nome** | la versione nuova si riapprova; i «sempre» decadono | le concessioni decadono con la versione e si richiedono; la scheda dice quali sono nuove (come `permessi_nuovi`): passo 1 |
| **Voce clonata di chi amministra** | la frase di sfida ferma registrazioni e TV, non una voce in tempo reale | le concessioni E3–E4 chiederanno il secondo fattore quando c'è (#52); fino ad allora il problema aperto «Voce unico fattore» di CLAUDE.md vale anche qui |

## 7. Piano a passi

Ogni passo ha il suo interruttore, **spento di serie**, e un criterio scritto prima di accenderlo
([0019](../decisioni/0019-ombra-prima-di-accendere.md)). Chi lo accende sulla DGX aggiorna la tabella
«Interruttori sulla DGX» di [setup-dgx](../aree/setup-dgx.md#interruttori-sulla-dgx). Una issue per
passo, aperta dopo l'approvazione del piano. I nomi delle chiavi sono proposte.

**Passo 0 — Il registro delle concessioni, in ombra.** Il modello dati (§ 5.1) e la traduzione di ciò
che c'è: i permessi del manifesto approvato e i «sempre» diventano concessioni; la porta calcola anche
la decisione con le concessioni e la scrive in `decisioni.jsonl` (`concessione_ombra`: decisione
vera, decisione nuova, regola), senza cambiare niente. `calliope stato --concessioni` le elenca.
- Interruttore: `estensioni_concessioni: ombra` (di serie `spento`).
- Criterio: due giorni d'uso sulla DGX con le estensioni attive, **0 differenze** tra la decisione
  vera e quella nuova; la prova a secco con tutte le regole del guardrail.

**Passo 1 — Il controllo a ogni chiamata, la scheda e l'approvazione per classe.** La porta decide con
le concessioni (§ 5.2); la scheda di revisione le dice in parole, con la classe e cosa resta preparato;
le concessioni decadono con la versione, e anche tornando a una versione di prima si richiedono
(§ 10, decisione 7); il risultato di una concessione a nome di una persona va solo a lei. Le
concessioni **E4** valgono per **sessione d'uso** (§ 10, decisione 1): all'apertura dell'estensione,
prima di partire, Calliope chiede la conferma dei suoi permessi E4; col sì valgono per quella sessione
(la scheda aperta, per un'estensione con scheda o un gioco; la conversazione, per una usata solo a
voce) e alla chiusura decadono. Nessuna concessione a nome di un ospite; un minore non chiede
concessioni (§ 10, decisione 8).
- Interruttore: `estensioni_concessioni: attivo`.
- Criterio: il passo 0 con 0 differenze; il banco d'attacco (`prova_estensioni_attacchi.py`) a **0
  passaggi** con i casi nuovi (fuori ambito, oltre quota, versione nuova o versione di prima con le
  concessioni dell'altra, concessione sospesa, un permesso E4 dopo la chiusura della sessione); nessun «sì» in più per le estensioni di oggi (l'attrito delle
  estensioni in `calliope stato --turni` non cresce).

**Passo 2 — Revoca a più livelli, sospensione per anomalia, promemoria.** La revoca di una
concessione, di un account o persona, di tutto (§ 5.4), a voce e dal cruscotto (con #124); la
sospensione (§ 5.5: oltre le quote la concessione, fuori dall'ambito l'estensione); l'elenco nel
cruscotto e il promemoria delle concessioni attive, una volta al mese (§ 10, decisione 6). Revocare
non chiede la frase di sfida; un familiare sospende le concessioni sui propri dati.
- Interruttore: le revoche sono restrizioni e valgono appena il passo 1 è attivo; la sospensione
  automatica ha `estensioni_sospensione: ombra | attiva` (di serie spenta): in ombra scrive solo
  «avrebbe sospeso».
- Criterio per `attiva`: una settimana d'ombra con **al più una sospensione falsa** (riletta a mano)
  su tutte le estensioni attive; ogni revoca provata a secco su tutti e quattro i livelli.

**Passo 3 — Il piano che chiede invece di chiudere.** Il catalogo con lo stato delle voci, il
contratto, il prompt, l'analisi della richiesta e i requisiti (§ 5.7).
- Interruttore: `estensioni_piano_chiede: ombra | attivo` (di serie spento). In ombra l'analisi e il
  piano calcolano anche l'esito nuovo e lo scrivono nel registro del lavoro, senza cambiare quello
  detto.
- Criterio: il banco delle richieste (`prove/banco_richieste.py`) con i casi nuovi: ogni richiesta che
  tocca solo voci `offerta` diventa «da concedere» e nessuna voce `da_costruire` diventa «da
  concedere»; nessun caso di oggi (estensioni, giochi, programmi) cambia esito; un giro vero
  dell'agente sulla DGX che arriva alla consegna dopo un `chiedi_permesso` di una concessione.

**Passo 4 — Preparare senza compiere, e le prime capacità nuove dalla porta.** La coda delle azioni
preparate (§ 5.6) e le capacità che non chiedono infrastruttura nuova: i tool di Calliope per nome
(E0–E2, § 3.9), la memoria con la categoria del dato (§ 3.7), le notifiche alla web app di casa
(§ 3.1).
- Interruttore: `estensioni_preparate` (di serie spento); ogni capacità nuova entra nel catalogo come
  `offerta` solo con il suo passo acceso.
- Criterio: nel registro, **0 atti irreversibili senza la riga della conferma** (chi, quando, sfida);
  le prove a secco del ciclo «prepara, mostra, conferma, scade»; un caso vero a voce per capacità.

**Passo 5 — Il deposito dei segreti e il login delegato.** Il deposito (§ 5.3), il collegamento sullo
schermo personale con la persona presente, il primo connettore tipizzato, la revoca presso il
fornitore dove c'è.
- Interruttore: `estensioni_segreti` (di serie spento).
- Criterio: il banco d'attacco esteso ai segreti a **0 passaggi** (il segreto non esce mai: né nel
  risultato, né nei registri, né verso un host fuori ambito, né dopo un reindirizzamento, né a pezzi);
  la revoca provata dall'inizio alla fine su un servizio di prova di fantasia; un collegamento rifiutato
  se la persona non è riconosciuta dalla voce sul suo schermo.

**Passo 6 — L'autonomia** (il progetto di #53 come concessione). Le corse a orario e in secondo piano,
a nome di chi l'ha chiesta, con i permessi del momento, risultato solo a lei, preparazioni in coda.
Una corsa a orario non ha un'apertura da parte di una persona, quindi **non usa capacità E4** (§ 10,
decisione 1).
- Interruttore: `estensioni_orari: ombra | attivo` (di serie spento); in ombra la corsa si registra
  («sarebbe partita») senza girare.
- Criterio: i criteri di #53 (tetto al giorno, coda dei risultati con tetto e scadenza, notte a voce
  ferma con `quiete()`); in ombra, una settimana senza corse previste in una pausa di un minore o con
  un livello cambiato; nessuna estensione con concessioni E4 pianificabile.

**Passo 7 — Le capacità dell'infrastruttura, una issue ciascuna**, nell'ordine scelto da chi
amministra il 20/10 (§ 10, decisione 9): connettori di posta con le loro porte (§ 3.1), file della
persona (§ 3.3), rete di casa ad host precisi (§ 3.4), browser senza testa (§ 3.11), catalogo dei
pacchetti (§ 3.6), modello dalla porta (§ 3.12), telefono (§ 3.2), scatto della webcam (§ 3.8).
Ognuna con la sua analisi breve, il suo interruttore e il suo criterio.

**Profilo ridotto da 8 GB**: i passi 0–6 sono solo codice (niente modelli, niente GPU) e valgono anche
lì; al passo 7 il modello dalla porta e il browser senza testa dipendono dalla memoria disponibile e
lì restano «da costruire».

## 8. Caso di verifica generale

Un'estensione che **legge i dati personali di un servizio esterno con login, prepara un'azione senza
compierla e gira a orario**. Per esempio (nomi di fantasia): ogni mattina alle 7 legge la posta di Ada,
le prepara un riassunto e, per un messaggio che chiede una risposta, una bozza. Il caso vero del 20/10
era di questa forma; lo stesso percorso vale per un calendario condiviso, un portale della scuola, un
conto in sola lettura.

1. **Richiesta** (passo 3): l'analisi dice ad Ada, prima del codice, che serviranno l'account della
   posta in lettura, la preparazione di risposte e l'orario, e che li concede chi amministra.
2. **Piano** (passo 3): l'agente dichiara `account` (lettura e preparazione), `autonomia` (ogni giorno
   alle 7) e chiama `chiedi_permesso` con l'ambito; il lavoro **non si chiude**.
3. **Revisione e approvazione** (passo 1): la scheda dice le tre concessioni in parole, con la classe;
   dice che l'invio **non** è concesso e resterà una bozza. Chi amministra approva con la frase di
   sfida.
4. **Collegamento** (passo 5): Ada, presente, collega il suo account sul suo schermo personale; il
   segreto va nel deposito; l'estensione non lo vede mai.
5. **Ogni corsa** (passi 1 e 6): la porta controlla la concessione, l'orario, i permessi di Ada di
   quel momento; le letture contaminano con `account:posta di Ada`; il riassunto va solo sul suo
   schermo personale, o a voce quando è sola.
6. **La bozza** (passo 4): resta in coda; Ada la vede, la conferma al momento (con la sfida, è E3), e
   solo allora parte. Se il messaggio letto conteneva istruzioni ostili, la domanda dice comunque il
   destinatario e il testo veri della bozza.
7. **Anomalia** (passo 2): cento messaggi in un minuto (oltre le quote) sospendono da soli la
   concessione dell'account; un tentativo di leggere un'altra cartella (fuori dall'ambito) sospende
   tutta l'estensione. Calliope lo dice ad Ada e a chi amministra.
8. **Revoca** (passi 2 e 5): «dimentica l'account della posta di Ada» toglie il segreto dal deposito,
   lo revoca presso il fornitore se si può, sospende le concessioni di quell'account in tutte le
   estensioni.
9. **Versione nuova**: le concessioni si richiedono; la scheda dice cosa cambia.

Il caso attraversa tutti i passi; ogni passo ha comunque i suoi casi, che non dipendono da questo.

## 9. Cosa non so

- **I servizi esterni**: quali offrono un token di sola lettura, un flusso a codice del dispositivo,
  un'API di revoca. Si vede servizio per servizio al passo 5; il piano non dipende dalla risposta, il
  connettore sì.
- **Il browser senza testa su ARM** (Windows su ARM e la DGX): esistono build arm64 di Chromium per
  Linux, ma peso, memoria e manutenzione nella sandbox non li ho misurati.
- **Le soglie della sospensione**: «oltre le quote» è chiaro; «fuori norma» per un'estensione che a
  volte legge molto no. Per questo il passo 2 parte in ombra.
- **Quante concessioni userà davvero una famiglia**: il cruscotto e il promemoria funzionano con
  poche; con molte servirà un raggruppamento per persona o per account, da vedere nell'uso.
- **Il secondo fattore** (#52) non è deciso: fino ad allora le E3–E4 si approvano con la sola voce e la
  sfida, come oggi le estensioni.

## 10. Decisioni del 20/10

*[storico fino al 20/10 sera: «Domande per chi amministra», dieci domande aperte nella prima versione
della PR #195; le risposte di chi amministra sono queste, e il piano del § 7 è aggiornato.]*

1. **E4 a un'estensione** (comandi delicati della casa, lo scatto della webcam): concedibili con la
   **conferma per sessione d'uso**. All'apertura dell'estensione, prima di partire, Calliope chiede la
   conferma dei suoi permessi E4; col sì valgono per tutta quella sessione; alla chiusura decadono e la
   volta dopo si riconcedono. La sessione è il tempo in cui la scheda è aperta, per un'estensione con
   scheda o un gioco; la conversazione, per un'estensione usata solo a voce. Una corsa a orario non ha
   un'apertura da parte di una persona, quindi non usa capacità E4. Le irreversibili restano diverse:
   conferma al momento di ogni atto.
2. **I «mai» delle altre decisioni** (disinserire l'allarme, la frase di sfida e i codici, un livello
   oltre familiare alla porta) restano non concedibili, con il rimando alla decisione. La webcam non è
   fra questi: vale il punto 1.
3. **L'atto finale** di una preparazione lo conferma la persona proprietaria dell'account; per un
   account della casa, chi amministra.
4. **La sospensione**: oltre le quote si ferma la sola concessione; fuori dall'ambito tutta
   l'estensione.
5. **Revocare non chiede la frase di sfida** (togliere potere è facile, darlo no); un familiare può
   sospendere le concessioni sui propri dati.
6. **Il promemoria delle concessioni attive**: una volta al mese a chi amministra, e a ogni persona per
   quelle sui suoi dati.
7. **Tornando a una versione di prima** le concessioni si richiedono, come per una versione nuova.
8. **Minori e ospiti**: un minore non chiede concessioni; i dati di un minore si collegano solo con un
   tutore presente; nessuna concessione a nome di un ospite.
9. **L'ordine delle capacità del passo 7**: posta, file della persona, rete di casa verso host precisi,
   browser senza testa, pacchetti, modello, telefono, webcam.
10. **I messaggi fuori casa** diventano chiedibili, sempre preparati e inviati solo con la conferma al
    momento: cambia la risposta S10 del 12/10 (roadmap 4.9).
