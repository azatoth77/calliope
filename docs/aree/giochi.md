# Giochi sugli schermi

*Schede interattive delle estensioni in un iframe isolato. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 11/10.** I giochi sono estensioni con una scheda. Dal 08/10 quelli chiesti da chi amministra seguono la modalità sviluppo come le altre estensioni (`sviluppo_apri` con `gioco`, prima `estensione_crea`; vedi [agenti-estensioni](agenti-estensioni.md)), ma il collaudo prima dell'approvazione non li eseguiva («Un gioco si prova sullo schermo dopo l'approvazione»; storico: dall'11/10 si aprono in prova, vedi sotto) e il ricollaudo alla consegna li salta; quelli chiesti da un familiare adulto restano come prima. Il giro dell'agente vero col `require` in gioco.js è ancora da rifare. Dal 10/10 pomeriggio un gioco chiesto come programma («Vorrei sviluppare un gioco all'interno di Calliope», prima «impossibile») diventa un gioco sugli schermi e la proposta lo dice (`sviluppo_gioco_schermi`, vedi [agenti-estensioni](agenti-estensioni.md)); dal 10/10 sera anche quando il modello lo chiede come estensione senza `gioco` (prima andava all'analisi delle estensioni, che lo dichiarava impossibile perché «la richiesta non specifica la scheda»).

**11/10.** Il collaudo di un gioco è vederlo: alla consegna Calliope dice che è un gioco e chiede «Lo apro in prova?»; `sviluppo_collauda` apre la versione candidata sullo schermo da cui si parla in una **partita di prova** (`Giochi.avvia_prova`, scheda con `"prova": true`, cornice «PROVA» disegnata dalla pagina), nello stesso riquadro e con la stessa CSP dei giochi approvati e senza ponte verso Calliope (dal riquadro solo pronto, battito, fine, errore, guasto). Non diventa attiva né chiedibile. Perché è sicuro e i casi veri: [agenti-estensioni](agenti-estensioni.md) (sezione dell'11/10). Dal 11/10 un gioco si apre nella **modalità gioco**: a tutta la finestra (schermo intero vero dove il browser lo permette), con ✕, il pallino della voce e la variante «collaudo» per un gioco in prova; vedi la sezione in fondo. Dall'11/10 sera un gioco può anche **ascoltare la voce**: dichiara un elenco chiuso di comandi (`scheda.ascolta`), le frasi che corrispondono per intero vanno dritte al gioco senza il modello (regola `gioco_comando`) e, finché il gioco aspetta una mossa, anche senza il nome (vedi «I comandi a voce di un gioco»).

**12/10.** Un gioco ha l'analisi della richiesta, con la sua lista di controllo (giocatori, regole, come si vince, voce); la versione nuova di un gioco chiesta senza `gioco=true` è un gioco (il tipo viene dalla scheda del manifesto); le modifiche, anche quelle dette al collaudo con «correggi» («metti sette porte»), cambiano i requisiti, e a voce si dice solo cosa è cambiato. Vedi «La specifica viva» in [agenti-estensioni](agenti-estensioni.md).

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Giochi e schede interattive delle estensioni (05/10) | JavaScript nel browser degli schermi in un `<iframe sandbox="allow-scripts">` (origine opaca, CSP senza rete, script con l'impronta), ponte `postMessage` controllato dalla pagina e dal server; test della logica con Node in un container (`Dockerfile.node`) | `calliope/estensioni/scheda.py` (sezione «scheda» del manifesto, gioco puro, `documento`, `RUNTIME_JS`, `analizza_js`); `calliope/schermi/giochi.py` → `Giochi` (partite, `GET /gioco/<gettone>`, `POST /api/gioco`), `AzioneGioco`; cane da guardia in `schermo.js`; `minori.TempoGioco`, `minori.Richieste`, tool `richiesta_tutore`; `calliope/agenti/test_js.mjs`, prova di fumo `calliope/agenti/fumo_js.mjs`; comandi a voce (11/10) `calliope/gioco_voce.py` (forme e regola `gioco_comando`), `Giochi.ascolto`, `Giochi.comando`, `Giochi.schermi_voce`, `Ciclo._comando_gioco`, tool `gioco_comando` in `tools/schermi.py`; rapporto [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md) |

## Problemi noti

*Dalla divisione di CLAUDE.md (note fino al 06/10); dal 09/10 una sola sezione per area.*

- **Giochi sugli schermi** (05/10, [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md)):
  un'estensione può avere una scheda interattiva (un gioco) che gira nel browser in un riquadro
  isolato (iframe sandbox senza `allow-same-origin`, CSP `connect-src 'none'`, runtime che toglie
  fetch/WebRTC/Worker, `frame-src 'self'` sulla pagina madre); messaggi solo con `calliope.*`
  (salva, leggi, manda, chat, di, azione), ricontrollati dal server; cane da guardia (ping,
  troppi messaggi, navigazione; dopo un ciclo infinito la pagina si ricarica: Edge riusava il
  processo bloccato). Gioco puro (niente permessi né azioni) → anche ospiti e schermi di
  stanza, approvato da un familiare adulto con la voce; partita condivisa tra schermi (con un
  minore o un ospite valori brevi e chat dal guardiano). Minori: tempo di gioco al giorno per
  fascia (`minori_gioco_minuti`), tempo in più da un adulto (scritto chi), richieste in attesa
  ai tutori («Intanto: Bianca ti ha chiesto…», `minore_gestisci approva_richiesta`, scadenza in
  3 giorni). Test dei giochi con Node nel container (`calliope motore sandbox costruisci
  javascript`). Prove: `prova_giochi` (banco d'attacco 17/17), `prova_giochi_pagina` (Edge:
  16 vie d'uscita bloccate, nessuna richiesta al server cattivo, tris tra due pagine).
  Agente vero sulla DGX (2 giri, 19 min): un memory puro pronto da approvare al primo giro, ma
  con un tocco che non funzionava → **prova di fumo** dei giochi (`agenti/fumo_js.mjs`: DOM
  finto e 300 tocchi a caso nei test); al secondo giro la prova ha trovato un `require` in
  gioco.js che l'agente non ha corretto in 24 passate (consegna e contratto ora lo spiegano;
  giro da rifare).

## La modalità gioco (11/10, ramo `gioco-schermo-intero`)

Dario, dopo un gioco vero: «aperto il gioco in una scheda non è grande a sufficienza per poterci
giocare davvero». Ora un gioco che arriva su uno schermo si apre nella **modalità gioco**: la sua
scheda occupa tutta la finestra, sulla pagina degli schermi (PC, tablet, TV) come sul telefono.
È una **vista della pagina**, non uno stato di Calliope: niente cambia nel ciclo, in
`modalita.py` o nella macchina a stati del dialogo.

- **A tutta la finestra senza spostare il riquadro.** La scheda resta dov'è nel documento e
  diventa `position: fixed` (classe `modo-gioco`, `body.in-modo-gioco`): un iframe spostato nel
  DOM si ricarica e la partita ripartirebbe (succede già nel carosello). Il riquadro, la sua
  sandbox (`allow-scripts` senza `allow-same-origin`), l'`allow` con `fullscreen 'none'` e le CSP
  non cambiano: lo schermo intero è della **pagina madre** (`document.documentElement`).
- **Schermo intero vero dove si può.** `requestFullscreen` vuole un gesto: si chiede subito se
  c'è un'attivazione recente (`navigator.userActivation`, per esempio «Parla» appena toccato),
  altrimenti il pulsante ⛶ in alto lo fa con un tocco. Un tocco sul gioco no: arriva al riquadro
  (altra origine) e la pagina non lo vede; un velo che prende il primo tocco avrebbe mangiato una
  mossa. Su iPhone l'API non c'è: ⛶ non compare e basta la finestra piena. Se il browser lascia
  lo schermo intero (Esc, gesto indietro) la modalità gioco resta, a finestra piena, e ⛶ torna.
- **Chiudere.** ✕ in alto a destra (≥ 44 px, sopra il gioco, niente lo copre: verificato con
  `elementFromPoint`), Esc quando il tasto arriva alla pagina (dentro il riquadro lo tiene il
  gioco; prima si chiude uno strato aperto sopra), e a voce «Calliope, chiudi il gioco»: è la
  scheda vuota di `schermo_mostra` (`cosa: niente`; la descrizione del tool ora nomina «chiudi il
  gioco»), che chiude la modalità anche sul telefono. Chiudere toglie il riquadro (il codice del
  gioco non gira più, il tempo di gioco dei minori non conta) e lascia sulla scheda «Riapri», che
  lo rimette a tutto schermo con un riquadro nuovo (il server riceve un altro «pronto», come per
  un riquadro spostato). Anche il cane da guardia e la fine del tempo di gioco chiudono la
  modalità.
- **Il pallino della voce.** In alto a sinistra un pallino colorato con una parola minima
  (colore e parola insieme, come la fascia della voce): «ascolto» verde, «dormo» grigio (a
  disposizione, serve il nome), «penso» ambra, «parlo» azzurro; sul telefono anche «spento»
  (microfono spento, pallino vuoto). Sulla pagina degli schermi è lo stato della voce della stanza
  che il server già manda (evento SSE `voce`, `Schermi.voce`: i quattro stati c'erano già, niente
  di nuovo nell'hub); una pagina che non riceve lo stato non mostra il pallino. Sul telefono è lo
  stato di quel telefono (`voceLocale`/`statoVista` di telefono.js, passato con
  `calliopeSchermo.voceGioco`), e il pallino fa anche da **«Parla»** (tocca e parla, tieni premuto
  per parlare a lungo): sopra il gioco il pulsante grande non si vede.
- **La voce continua.** Microfono, wake word, riproduzione e satellite non sanno niente della
  modalità: lo schermo intero non cambia `visibilityState` (che resta l'unico motivo per cui il
  telefono spegne il microfono) né sospende l'AudioContext; i tasti presi dal riquadro non
  servono alla voce. Le prove lo verificano entrando, chiudendo e riaprendo col microfono acceso.
- **Variante «collaudo»** (richiesta di Dario dello stesso giorno): un gioco non ancora
  approvato, aperto per provarlo, ha la stessa vista con una **cornice arancio** piena attorno al
  gioco (`--prova: #f39a2e`, classe `gioco-prova`) e l'etichetta «PROVA» in alto, con lo stesso ✕
  e lo stesso pallino. **Contratto**: la scheda del gioco (tipo `gioco`) porta il campo
  `"prova": true`; con quel campo, e solo con il valore `true`, la pagina mostra la variante.
  Lato server c'è soltanto l'argomento `Giochi.avvia(..., prova=True)`, che lo mette nella
  scheda (il campo passa com'è da `schede.nuova` all'hub e alla pagina). Aprire al collaudo una
  versione non ancora attiva (oggi `Giochi.documento` serve solo la versione attiva) è del lato
  sviluppo, non di questo ramo.
- **In futuro** la modalità gioco potrebbe diventare uno stato della macchina a stati del dialogo
  (`stato_dialogo.py`), con i tool del gioco (mosse a voce, «ricomincia») al posto di quelli
  generali mentre si gioca. Oggi no: resta una vista degli schermi.

Prove: `prova_giochi_pagina` (pagina degli schermi, Edge senza finestra: il tris si gioca già a
tutta la finestra; geometria, pallino nei quattro stati della stanza, ⛶ porta allo schermo intero
vero, ✕, «Riapri» con il riquadro che riparte, Esc, scheda vuota, collaudo con la cornice e il
riquadro pronto) e `prova_telefono_schermo` (telefono a 390×844: gioco a tutta la finestra, ✕
libero e ≥ 44 px, microfono acceso dall'inizio alla fine, pallino «penso» e «dormo», il pallino
come «Parla», ✕, «Riapri», scheda vuota, collaudo). Le foto con `CALLIOPE_FOTO=<cartella>`.

Per vederla: ricaricare la pagina degli schermi e quella del telefono dopo l'aggiornamento della
DGX (sono file statici serviti da Calliope: niente da installare sul portatile o sul telefono);
poi chiedere un gioco a voce.
## Il gioco di Halloween: la prova di fumo dice dove (11/10, ramo `agente-guida`)

Giro vero della DGX dell'11/10: qwen3.6 sviluppa «Halloween - Apri le porte» e gira a vuoto 45
minuti. Prima le stesse costanti dichiarate in logica.js e gioco.js («Identifier
'TIPI_SORPRESA' has already been declared»), poi la prova di fumo con «tocco (click): Error:
Devi inserire da 1 a 4 giocatori», un'eccezione della logica uscita dal gestore di «Inizia» (i
nomi vuoti). Senza elemento né riga, l'agente ha riscritto gioco.js intero nove volte e ha
creduto che nella prova mancassero `calliope` o il contenitore. Storia completa e correzioni
(valgono per tutti gli sviluppi) in [agenti-estensioni](agenti-estensioni.md), «Dove e perché,
scheletri di partenza, spinta concreta»; per i giochi:

- la prova di fumo dice l'elemento toccato, `[in logica.js:4 (creaStato) ← gioco.js:8
  (avvia)]`, «Un gestore di evento ha lanciato un'eccezione: ogni gestore deve catturare gli
  errori della logica…» e i tocchi prima; le dichiarazioni doppie dicono le due righe; il
  messaggio spiega che la prova dà `document` con `<div id="gioco">`, `calliope` e i timer;
- lo scheletro del gioco nel prompt: logica.js e gioco.js senza nomi doppi, i gestori passati
  da `sicuro()` che cattura e mostra l'errore nel gioco, il test con node:test (591 token);
- `modifica_file` e `leggi_file` con `riga` per correggere un punto senza riscrivere il file.

## I comandi a voce di un gioco (11/10 sera, ramo `gioco-voce`)

Richiesta approvata da Dario: un gioco può usare la voce come modalità di interazione. Prima un
gioco poteva solo far parlare Calliope (`voce: true`, poche frasi al minuto), ma non sentiva
niente. Ora:

- **Il gioco dichiara cosa ascolta.** Nel manifesto della scheda, `"ascolta": {"comandi":
  {"uno": ["uno", "la porta uno"], "ricomincia": ["ricomincia"]}, "giocatore": false}`: al più
  24 comandi (nome `[a-z0-9_]`, al più 24 caratteri), ognuno con 1–6 forme di 1–5 parole e al
  più 40 caratteri. Rifiutate: le forme che coprirebbero l'uscita («esci», «spegniti») o lo
  stop («basta», «stop»), quelle che dopo la normalizzazione valgono per due comandi, il solo
  nome. «Ricomincia» si può: dentro il gioco riavvia il gioco, non la conversazione (la fase del
  gioco viene prima delle uscite). Validazione in `calliope/gioco_voce.py` (`valida_elenco`) da
  `scheda.normalizza`; chi approva sente «si gioca anche a voce, con N comandi» (e «il nome di
  chi gioca»), e una versione nuova che li aggiunge lo dice come un permesso nuovo.
- **Il sottoinsieme a runtime.** Nel riquadro `calliope.comandiAttivi(["uno", "tre"])` dice quali
  valgono adesso (le porte ancora chiuse; `[]` durante un'animazione o a gioco finito): il
  server accetta solo nomi dichiarati (`_t_comandi`, regola `gioco_comando_non_dichiarato`),
  mai comandi nuovi. All'avvio (`pronto`, anche «Riapri») valgono tutti.
- **La mossa arriva al riquadro** con `calliope.quandoComando(f)`: f riceve `{comando,
  giocatore?}` come oggi riceve i tocchi. Dal server è l'evento SSE «gioco» di tipo «comando»;
  la pagina (schermo.js, anche sul telefono) lo passa al riquadro solo se il nome è un nome di
  comando valido, con al più `giocatore` (testo fino a 40 caratteri), nient'altro.

### Senza il modello: la regola `gioco_comando`

Una frase che corrisponde **per intero** a una forma di un comando attivo del gioco aperto sullo
schermo del satellite che l'ha sentita diventa una mossa (`Ciclo._comando_gioco`, subito dopo
Whisper). Ammesse solo le normalizzazioni della forma: maiuscole, accenti, punteggiatura, numeri
in parole o in cifre («la porta tre» = «la porta 3»), il nome davanti («Calliope, tre», anche
storpiato come per la wake word testuale). È il caso ammesso dal principio 10: forma chiusa e
breve, per intero, effetto reversibile (una mossa). Calliope non parla dopo una mossa (il gioco
mostra la mossa; se ha `voce` può farla dire lui). Nel registro dei turni `esito:
gioco_comando`, regola `gioco_comando`, `gioco: {partita, comando, ms}` e **nessun testo**.

Contrari (provati in `prove/prova_testo.py` e `prove/prova_gioco_voce.py`): il comando dentro una
frase più lunga («apri la porta tre per favore», «tre gatti», «ok, uno»), nessun gioco aperto,
il gioco sullo schermo di un altro satellite, un comando dichiarato ma non attivo adesso, una
domanda di Calliope in sospeso (la frase va al modello), il gioco chiuso (✕, Esc, «chiudi il
gioco»: la pagina manda `chiuso`), una pagina senza segni da oltre 40 s (`VIVO_S`: schermo
spento, gioco nascosto, il battito non arriva), una frase scritta o durante una registrazione
della voce.

Quale schermo è «del satellite» (`Giochi.schermi_voce`): lo schermo del satellite se ne ha uno
(la pagina del PC, il telefono); un satellite senza schermo (in futuro gli XMOS accanto alla TV)
vale per gli schermi della sua stanza che non sono di un altro satellite; l'audio di questo
computer per quelli della stanza predefinita.

Ciò che non è nell'elenco va al modello come sempre. Se il gioco aspetta un comando, il modello
riceve nel contesto del turno una riga con i comandi («Sullo schermo c'è il gioco «Apri le
porte», che aspetta un comando a voce tra: uno, due, tre, ricomincia…») e ha il tool
`gioco_comando(comando)` («apri la terza» → «tre»): il codice accetta solo un comando attivo
dell'elenco (o una sua forma), mai testo libero, e la mossa parte come quella diretta. Qui
Calliope dice la forma del comando («Tre.»): è un'interpretazione delle parole, e chi parla deve
sentire cosa ha capito. Il tool è sicuro (`ToolSpec.classe`), per tutti i livelli, registrato
solo con i giochi accesi (main.py); lo schema costa circa 106 token in più nel prompt della voce
(stima su 367 caratteri), in cache come gli altri.

**Latenza.** La mossa non passa dal modello: dalla fine dell'ascolto alla mossa conta solo
Whisper (sulla DGX ~0,18 s di STT) più il confronto e l'evento SSE, sotto il millisecondo a
secco (`gioco.ms` nel registro dei turni, nella prova 0 ms con lo STT finto). Da misurare sulla
DGX con `calliope stato --turni` (esito `gioco_comando`).

### Il nome non serve a ogni mossa: la finestra del gioco

Finché il gioco aperto sullo schermo di quel satellite aspetta una mossa (comandi attivi non
vuoti), l'ascolto resta aperto senza il nome per `giochi_ascolto_s` (60 s, `calliope.yaml`,
sezione estensioni) dall'ultima mossa, dall'apertura del gioco o dall'ultima risposta. Come la
finestra verde di oggi dopo una risposta (`awake_until`, `followup_s`), ma senza il nome valgono
**solo** le forme dell'elenco: tutto il resto si ignora come a Calliope addormentata (regola
`gioco_finestra_ignorata`, `esito: ignorato`, testo non conservato). Una frase con il nome (o
sentita dalla wake word acustica) va avanti come sempre. Oltre il tetto senza mosse torna
«dormo»; con 0 il nome serve sempre (i comandi detti dopo il nome vanno comunque al gioco).

- Come funziona: `Ciclo._ascolta` chiede `Giochi.ascolto(schermi)` e passa al `listen` la fine
  più lontana tra la finestra di sempre e quella del gioco; il satellite (e il telefono) la
  ricevono come sempre in `sveglia_per_s`, quindi la wake word del satellite lascia passare le
  frasi senza nome. Il gioco che apre o cambia i suoi comandi suona `sveglia_gioco` del ciclo
  (`Giochi.sveglia_voce`), e l'ascolto riparte con la finestra giusta.
- **Il pallino verde** della modalità gioco riflette questa finestra: sulla pagina degli schermi
  è lo stato `ascolta` con il suo `fino` (evento `voce`), sul telefono è `sveglia_per_s` del suo
  ascolto (telefono.js: «Ti ascolto», «N s senza nome»). Nessun cambiamento nella pagina.
- **Half-duplex (principio 8)**: invariato. La finestra vale solo mentre si ascolta: mentre
  Calliope parla (anche una frase del gioco con `voce`) non si trascrive, resta solo la wake word
  acustica per «Calliope, basta». Le frasi del gioco si dicono tra un giro e l'altro come gli
  annunci, e la finestra riparte dopo.
- Costo: per tutta la finestra le frasi della stanza vanno a Whisper (il testo non resta: o è
  un comando o si butta). Per questo il tetto, e per questo la finestra vale solo con un gioco
  che aspetta una mossa.
- Vale anche per il telefono come satellite: è lo stesso `listen` remoto, e il suo schermo è
  quello del satellite.

### Chi parla

Con `"giocatore": true` la mossa porta il nome della persona **riconosciuta dalla voce in quella
frase** (sopra soglia, con il margine sul secondo profilo, lunga almeno `speaker_min_voice_s`):
mai per continuità né dalla zona grigia, e per gli ospiti niente nome. Un comando di una parola
è spesso più corto di quanto serve all'impronta: allora la mossa arriva senza `giocatore`, e il
gioco deve saperlo gestire (chiedere di toccare, alternare i turni da sé). Con il modello
(`gioco_comando`) vale lo stesso criterio (`identified_by == "voce"`). Per i minori va il nome
di casa: in [minori](minori.md) non ci sono vincoli contrari (i dati dei minori non escono da
Calliope, e qui non escono: vedi sotto). Un gioco con `rete_leggi` non può chiedere il nome di
chi gioca (manifesto rifiutato).

### Perché è sicuro

- Al riquadro arrivano solo il nome di un comando del suo elenco (controllato dal server, poi di
  nuovo dalla pagina con un'espressione chiusa) e al più il nome di chi gioca: **mai audio né
  testo libero**. Il riquadro resta quello di prima (sandbox senza `allow-same-origin`, CSP
  senza rete, runtime che toglie fetch e WebRTC): niente esce dal riquadro se non con
  `calliope.*`, controllati come prima.
- Il gioco non può allargare ciò che sente: `comandiAttivi` restringe soltanto, l'elenco è nel
  manifesto approvato (e chi approva lo sente).
- La regola decide solo una mossa nel gioco aperto su quello schermo: reversibile, nessun tool,
  nessun permesso. Le forme che fermerebbero la voce o la farebbero uscire non si possono
  dichiarare; «basta» ed «esci» restano di Calliope anche nella finestra del gioco.
- Il nome di chi gioca resta dentro Calliope: il riquadro non ha rete; con `manda` arriva solo
  agli altri schermi della partita (in casa) e con `di` passa dai controlli delle frasi; un
  gioco con `rete_leggi` non lo riceve.
- Il limite di frasi al minuto della `voce` resta (`giochi_frasi_minuto`).
- **Partita di prova** (`"prova": true`, `Giochi.avvia_prova`, senza ponte): i comandi a voce
  arrivano comunque (`comandi` e `chiuso` sono in `TIPI_PROVA`). Decisione: sono un ingresso
  come i tocchi, non un ponte verso Calliope (non leggono dati, non salvano, non parlano, non
  chiamano tool), e senza di loro il collaudo di un gioco a voce non proverebbe la cosa che
  conta. `salva`, `leggi`, `manda`, `chat`, `di` e `azione` restano vietati in prova.

### Per l'agente

Lo scheletro del gioco (`agenti/scheletri.py`) mostra `"ascolta"` nella scheda e
`calliope.quandoComando(sicuro(...))`: 231 caratteri, circa 67 token in più (591 → ~658; stima
con il rapporto caratteri/token della misura di Qwen3.6, 3,47; la misura esatta si rifà sulla
DGX con lo script dell'11/10). Il contratto (§ 5, «Scheda interattiva») ha una riga: comandi a
voce solo se la richiesta chiede di giocare a voce, i limiti, `quandoComando`, `comandiAttivi`,
e il gioco che si gioca anche con i tocchi (circa 177 token). La prova di fumo
(`agenti/fumo_js.mjs`) manda anche comandi a voce a caso tra quelli attivi (una volta ogni
quattro tocchi, dopo il tocco), con il nome finto «Ada» se il manifesto chiede il giocatore; un
gestore che lancia dice quale comando («comando «tre»: Error: …» con file e riga), e
`comandiAttivi` con un nome non dichiarato (o senza `ascolta` nel manifesto) è un errore della
prova.

### La macchina a stati

È il primo pezzo dello stato «gioco» della macchina a stati del dialogo (`stato_dialogo.py`,
progetto in [voce-e-regole](voce-e-regole.md)): mentre si gioca, alcune frasi brevi hanno un
significato chiuso che non passa dal modello. La macchina a stati qui non si tocca: la regola
sta nel ciclo come le altre forme chiuse, e la finestra è una finestra d'ascolto.

### Prove

`prova_gioco_voce` (a secco, ~2 s: manifesto, server, ciclo con tutti i contrari, il tool,
chi gioca, la prova di fumo con i comandi), `prova_testo` (le forme e i contrari della regola),
`prova_giochi_pagina` (Edge: la mossa arriva nel riquadro con il solo comando e il nome, il
sottoinsieme a runtime, la pagina non passa nomi non validi né testo libero, ✕ chiude anche
l'ascolto, i comandi nella partita di prova), `prova_agente_guida` (lo scheletro passa i suoi
test). Il gioco delle prove è `prove/giochi/porte`.

### Da fare sulla DGX

Il giro vero: chiedere a voce una modifica al gioco di Halloween perché si giochi anche a voce
(«Calliope, nel gioco di Halloween voglio aprire le porte a voce, dicendo il numero della
porta»), guardare che lo sviluppo aggiunga `ascolta` e `quandoComando`, aprirlo in prova
(i comandi arrivano anche lì), poi giocare dal satellite e dal telefono dicendo «la porta
due», «tre», «ricomincia» senza il nome; misurare con `calliope stato --turni` la latenza
delle mosse e quante frasi la finestra del gioco ignora.
