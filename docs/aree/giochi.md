# Giochi sugli schermi

*Schede interattive delle estensioni in un iframe isolato. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 11/10.** I giochi sono estensioni con una scheda. Dal 08/10 quelli chiesti da chi amministra seguono la modalità sviluppo come le altre estensioni (`sviluppo_apri` con `gioco`, prima `estensione_crea`; vedi [agenti-estensioni](agenti-estensioni.md)), ma il collaudo prima dell'approvazione non li eseguiva («Un gioco si prova sullo schermo dopo l'approvazione»; storico: dall'11/10 si aprono in prova, vedi sotto) e il ricollaudo alla consegna li salta; quelli chiesti da un familiare adulto restano come prima. Il giro dell'agente vero col `require` in gioco.js è ancora da rifare. Dal 10/10 pomeriggio un gioco chiesto come programma («Vorrei sviluppare un gioco all'interno di Calliope», prima «impossibile») diventa un gioco sugli schermi e la proposta lo dice (`sviluppo_gioco_schermi`, vedi [agenti-estensioni](agenti-estensioni.md)); dal 10/10 sera anche quando il modello lo chiede come estensione senza `gioco` (prima andava all'analisi delle estensioni, che lo dichiarava impossibile perché «la richiesta non specifica la scheda»).

**11/10.** Il collaudo di un gioco è vederlo: alla consegna Calliope dice che è un gioco e chiede «Lo apro in prova?»; `sviluppo_collauda` apre la versione candidata sullo schermo da cui si parla in una **partita di prova** (`Giochi.avvia_prova`, scheda con `"prova": true`, cornice «PROVA» disegnata dalla pagina), nello stesso riquadro e con la stessa CSP dei giochi approvati e senza ponte verso Calliope (dal riquadro solo pronto, battito, fine, errore, guasto). Non diventa attiva né chiedibile. Perché è sicuro e i casi veri: [agenti-estensioni](agenti-estensioni.md) (sezione dell'11/10). Dal 11/10 un gioco si apre nella **modalità gioco**: a tutta la finestra (schermo intero vero dove il browser lo permette), con ✕, il pallino della voce e la variante «collaudo» per un gioco in prova; vedi la sezione in fondo.

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Giochi e schede interattive delle estensioni (05/10) | JavaScript nel browser degli schermi in un `<iframe sandbox="allow-scripts">` (origine opaca, CSP senza rete, script con l'impronta), ponte `postMessage` controllato dalla pagina e dal server; test della logica con Node in un container (`Dockerfile.node`) | `calliope/estensioni/scheda.py` (sezione «scheda» del manifesto, gioco puro, `documento`, `RUNTIME_JS`, `analizza_js`); `calliope/schermi/giochi.py` → `Giochi` (partite, `GET /gioco/<gettone>`, `POST /api/gioco`), `AzioneGioco`; cane da guardia in `schermo.js`; `minori.TempoGioco`, `minori.Richieste`, tool `richiesta_tutore`; `calliope/agenti/test_js.mjs`, prova di fumo `calliope/agenti/fumo_js.mjs`; rapporto [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md) |

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
