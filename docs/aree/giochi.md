# Giochi sugli schermi

*Schede interattive delle estensioni in un iframe isolato. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 18/10.** Il codice dei giochi è quello del 15/10: macchina a stati di Calliope come unico formato (13–14/10), palco fisso 1280×720 e 720×1280 con la misura «fuori dal palco» (14/10), istantanea validata, giudice di fase, «gioco anch'io», ripresa dopo «Riapri» e partite condivise (14/10 sera), chi è quale giocatore e «Gira il telefono» (15/10). Resta il giro vero dell'agente con un gioco col palco fisso sulla DGX. Le righe datate qui sotto dicono i passi.

**11/10, la base** *[la testa «Stato al 11/10» fino al 18/10]*. I giochi sono estensioni con una scheda. Dal 08/10 quelli chiesti da chi amministra seguono la modalità sviluppo come le altre estensioni (`sviluppo_apri` con `gioco`, prima `estensione_crea`; vedi [agenti-estensioni](agenti-estensioni.md)), ma il collaudo prima dell'approvazione non li eseguiva («Un gioco si prova sullo schermo dopo l'approvazione»; storico: dall'11/10 si aprono in prova, vedi sotto) e il ricollaudo alla consegna li salta; quelli chiesti da un familiare adulto restano come prima. Il giro dell'agente vero col `require` in gioco.js è ancora da rifare *(storico: dal 14/10 gioco.js libero non c'è più, la macchina a stati è l'unico formato; vedi «14/10» qui sotto)*. Dal 10/10 pomeriggio un gioco chiesto come programma («Vorrei sviluppare un gioco all'interno di Calliope», prima «impossibile») diventa un gioco sugli schermi e la proposta lo dice (`sviluppo_gioco_schermi`, vedi [agenti-estensioni](agenti-estensioni.md)); dal 10/10 sera anche quando il modello lo chiede come estensione senza `gioco` (prima andava all'analisi delle estensioni, che lo dichiarava impossibile perché «la richiesta non specifica la scheda»).

**11/10.** Il collaudo di un gioco è vederlo: alla consegna Calliope dice che è un gioco e chiede «Lo apro in prova?»; `sviluppo_collauda` apre la versione candidata sullo schermo da cui si parla in una **partita di prova** (`Giochi.avvia_prova`, scheda con `"prova": true`, cornice «PROVA» disegnata dalla pagina), nello stesso riquadro e con la stessa CSP dei giochi approvati e senza ponte verso Calliope (dal riquadro solo pronto, battito, fine, errore, guasto). Non diventa attiva né chiedibile. Perché è sicuro e i casi veri: [agenti-estensioni](agenti-estensioni.md) (sezione dell'11/10). Dal 11/10 un gioco si apre nella **modalità gioco**: a tutta la finestra (schermo intero vero dove il browser lo permette), con ✕, il pallino della voce e la variante «collaudo» per un gioco in prova; vedi la sezione in fondo. Dall'11/10 sera un gioco può anche **ascoltare la voce**: dichiara un elenco chiuso di comandi (`scheda.ascolta`), le frasi che corrispondono per intero vanno dritte al gioco senza il modello (regola `gioco_comando`) e, finché il gioco aspetta una mossa, anche senza il nome (vedi «I comandi a voce di un gioco»).

**12/10.** Un gioco ha l'analisi della richiesta, con la sua lista di controllo (giocatori, regole, come si vince, voce); la versione nuova di un gioco chiesta senza `gioco=true` è un gioco (il tipo viene dalla scheda del manifesto); le modifiche, anche quelle dette al collaudo con «correggi» («metti sette porte»), cambiano i requisiti, e a voce si dice solo cosa è cambiato. Vedi «La specifica viva» in [agenti-estensioni](agenti-estensioni.md).

**13/10.** Un gioco nuovo usa la **macchina a stati di Calliope**: dichiara fasi e comandi nel manifesto (`scheda.macchina`, comandi con uno slot «porta {n}») e scrive in logica.js solo la logica pura (`GIOCO`); preparazione, turni, punti, esito, fine con la classifica, disegno, pulsanti e voce sono del motore (`motore_gioco.js`), che gira nel riquadro e, lo stesso file, nella prova di fumo per fasi e nei test. Gli esempi di accettazione dei giochi (stato → mosse → stato atteso) li scrive il codice e l'agente non li può cambiare. Vedi «La macchina a stati di Calliope» in fondo.

**14/10 sera.** Il progetto della macchina a stati è finito (tranne «Gira il telefono» per una
tela e la prova del palco nel browser della DGX, scartata dalla decisione 4): Calliope tiene
l'**istantanea validata** della partita e ogni comando a voce porta il suo numero; risponde da
sé a «a chi tocca?», «quanti punti ho?», «chi sta vincendo?», «cosa posso dire?»; un **giudice di
fase** capisce le mosse dette con altre parole («apri la terza»); «**gioco anch'io**» e i **nomi
scritti** sostituiscono «Giocatore N»; dopo «**Riapri**» la partita riprende; le **partite
condivise** tra schermi hanno un motore solo. Vedi «Lo stato della partita» in fondo.

**15/10.** **Chi è quale giocatore**: «gioco anch'io» lega un giocatore allo schermo da cui è
detto o toccato e alla voce riconosciuta (un segno opaco, «v1»); in una fase a turni la mossa vale
solo per chi è di turno (la sua voce, o il suo schermo), e Calliope dice «Tocca ad Ada.» a chi
prova a muovere per un altro; «che giocatore sono?»; chi dice «gioco anch'io» a metà entra
subito (con `GIOCO.entra`) o dalla prossima partita. **«Gira il telefono»**: una tela può
dichiarare un orientamento solo; sul telefono girato dall'altra parte una fascia lo dice e
Calliope una volta a voce, senza fermare il gioco. Vedi «Chi è quale giocatore» in fondo.

**14/10.** Ogni pagina si disegna su un **palco fisso** (1280×720, 720×1280 sul telefono in verticale) scalato alla finestra, con sei modelli di pagina più la tela; la prova di fumo **misura il palco** di ogni pagina e lo dice all'agente come un errore da correggere, e il motore misura anche lo schermo vero. La macchina a stati è l'**unico formato**: i giochi vecchi (gioco.js libero, `ascolta` piatto) non si approvano né si aprono più. Vedi «Il palco fisso» in fondo.

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Giochi e schede interattive delle estensioni (05/10) | JavaScript nel browser degli schermi in un `<iframe sandbox="allow-scripts">` (origine opaca, CSP senza rete, script con l'impronta), ponte `postMessage` controllato dalla pagina e dal server; test della logica con Node in un container (`Dockerfile.node`) | `calliope/estensioni/scheda.py` (sezione «scheda» del manifesto, gioco puro, `documento`, `RUNTIME_JS`, `analizza_js`); `calliope/schermi/giochi.py` → `Giochi` (partite, `GET /gioco/<gettone>`, `POST /api/gioco`), `AzioneGioco`; cane da guardia in `schermo.js`; `minori.TempoGioco`, `minori.Richieste`, tool `richiesta_tutore`; `calliope/agenti/test_js.mjs`, prova di fumo `calliope/agenti/fumo_js.mjs`; comandi a voce (11/10) `calliope/gioco_voce.py` (forme e regola `gioco_comando`), `Giochi.ascolto`, `Giochi.comando`, `Giochi.schermi_voce`, `Ciclo._comando_gioco`, tool `gioco_comando` in `tools/schermi.py`; rapporto [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md) |
| Macchina a stati dei giochi (13/10) | JavaScript senza dipendenze, lo stesso file nel riquadro e in Node | `calliope/estensioni/macchina.py` (validazione di `scheda.macchina`, comandi piatti `ascolta`, `in_parole`); `calliope/estensioni/motore_gioco.js` (CalliopeMotore.crea: il nucleo puro; CalliopeMotore.avvia: disegno, pulsanti, voce); `scheda.documento` (motore e avvio nel riquadro, `STILE_MOTORE`); `calliope/agenti/fumo_js.mjs` (esplora, tuttiPiatti, apriGioco con g.stato()); esempi di accettazione `agenti/accettazione.py` (`test_js`, `FILE_GIOCO`); progetto [`2026-10-12-giochi-macchina-stati.md`](../ricerche/2026-10-12-giochi-macchina-stati.md) |
| Stato della partita, domande, giudice, nomi, ripresa, partite condivise (14/10 sera) | Python e JavaScript senza dipendenze; il giudice sul modello del giudizio «rivolta» (Ollama, uscita vincolata) | `estensioni/macchina.py` (`valida_istantanea`, `per_fase`, `da_piatto`, `nome_chiuso`); `schermi/giochi.py` (`_t_stato`, `_t_rifiutato`, `_t_mossa`, `_nomi_detti`, `Posto.istantanea`, `Posto.ripresa`, `Partita.tiene`, `motore_condiviso`); `calliope/gioco_stato.py` (domande standard, `anchio_nome`, la riga dei dati del turno); `calliope/gioco_giudice.py`; `Ciclo._comando_gioco`, `Ciclo._giudice_di_fase`; `motore_gioco.js` (`perCalliope`, `rinomina`, `riprendi`, autorevole e specchio); `scheda.RUNTIME_JS` (canale del motore); `schermo.js` (i tipi nuovi) |
| Chi è quale giocatore, «Gira il telefono» (15/10) | Python e JavaScript senza dipendenze | `motore_gioco.js` (`chiMuove`, `legame`, `iscritti`/`entrano`, `GIOCO.entra`, il posto dello schermo e la fascia «Gira il telefono»); `macchina.py` (`chi_muove`, i legami nell'istantanea, `orientamento` di una tela, «anchio» a partita cominciata in `per_fase`); `schermi/giochi.py` (`Partita.voci`/`voce_di`, `turno_altrui`, `_t_gira`, lo schermo nelle mosse); `gioco_stato.py` (domanda «io», `_dove`); `Ciclo._turno_altrui`; `schermo.js` (`gira`, `schermo` e `voce` verso il riquadro, il tocco all'avvio, `alDito`) |
| Palco fisso e modelli di pagina (14/10) | JavaScript senza dipendenze: l'impaginazione è una funzione pura, la stessa nel riquadro e in Node | `motore_gioco.js`: `impagina` (contenuto della pagina → scatole sul palco), `controllaPalco`, `difettiPalco`, il nucleo `pagina(S)`, la misura vera nel riquadro (`misuraVera` → canale `palco`); `macchina.PAGINE`; `scheda.RUNTIME_JS` (il canale riservato al motore), `STILE_MOTORE` (il palco, niente scroll); `calliope/agenti/fumo_js.mjs` (il palco nell'esploratore, `g.palco()`); `schermi/giochi.py` (`_t_palco`, `Posto.palco`); `prove/giochi/pagine` |

## Problemi noti

*Dalla divisione di CLAUDE.md (note fino al 06/10); dal 09/10 una sola sezione per area.*

- **Giochi sugli schermi** (05/10, [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md)):
  un'estensione può avere una scheda interattiva (un gioco) che gira nel browser in un riquadro
  isolato (iframe sandbox senza `allow-same-origin`, CSP `connect-src 'none'`, runtime che toglie
  fetch/WebRTC/Worker, `frame-src 'self'` sulla pagina madre); messaggi solo con `calliope.*`
  (salva, leggi, manda, chat, di, azione), ricontrollati dal server; cane da guardia (ping,
  troppi messaggi, navigazione; dopo un ciclo infinito la pagina si ricarica: Edge riusava il
  processo bloccato; dal 14/10 il limite `giochi_watchdog_s` conta dal primo ping rimasto
  senza risposta e non più dall'ultimo pong, che con i ping ogni 2–3 s chiudeva a volte un
  gioco sano, e una scheda nascosta, con un giro al minuto, senza averlo interrogato:
  [prove instabili](../../prove/LEGGIMI.md)). Gioco puro (niente permessi né azioni) → anche ospiti e schermi di
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

*Storico in parte dal 14/10: l'elenco piatto `scheda.ascolta` scritto dall'agente,
`calliope.quandoComando` e `calliope.comandiAttivi` non ci sono più (i giochi vecchi sono tolti);
i comandi a voce li ricava Calliope dalla macchina a stati e li riceve il motore, da un canale
riservato. Il riconoscimento, la regola `gioco_comando`, la finestra senza nome, chi parla e la
sicurezza qui sotto valgono come prima; il nome di chi gioca si chiede con
`macchina.giocatore`. Vedi «Il palco fisso» in fondo.*

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

**12/10, progetto** (*storico: fatto in parte il 13/10, vedi «La macchina a stati di Calliope» in fondo*): la macchina a stati **del gioco** fornita da Calliope (fasi standard, comandi
per fase con uno slot, istantanea, giudice di fase, palco fisso, prova di fumo per fasi; nessuna
compatibilità con i giochi di oggi) è in
[`2026-10-12-giochi-macchina-stati.md`](../ricerche/2026-10-12-giochi-macchina-stati.md), in
attesa delle decisioni di chi amministra.

### Correzioni dai log del 12/10 sera

Il giro del gioco delle porte del 12/10 (dettagli e casi in
[agenti-estensioni](agenti-estensioni.md), «Correzioni dai log del 12/10»), per ciò che riguarda
i giochi:
- una modifica dello stesso gioco con «un giocatore» non è più «un'altra estensione»; in uno
  sviluppo che è un gioco «un gioco» vale come cosa nuova solo con altro/nuovo/secondo;
- la correzione di un gioco dice «quando è pronto rifacciamo la prova sullo schermo» (prima «…con
  «in prova sullo schermo»», il dato del collaudo di un gioco); la revisione dice «è un gioco
  sullo schermo, da 2 a 4 giocatori» e «con un comando» (prima «per da 2 a 4», «con 1 comandi»);
- nei vincoli della correzione di un gioco: la causa può essere in `gioco.js` (ciò che si vede),
  un test in `logica.test.js` che giochi le mosse dette e controlli punti, esito e vincitore, e,
  se la versione provata era già una correzione, che quella non ha funzionato
  (`VINCOLO_CORREZIONE_GIOCO`, `_correzione_di_prima`);
- l'avviso vicino al tetto del giro non dice più «il lavoro sta per finire, consegna»: in uno
  sviluppo è un'azione («il passo concreto più utile»), senza numeri;
- una correzione che consegna lo stesso codice non è «pronto» («il codice è uguale a prima: lo
  rimando all'agente?»), e la prova di fumo segnala «undefined», «NaN», «[object Object]» nel
  testo visibile dopo un tocco (la causa vera del 12/10, l'esito annidato in `logica.js` letto al
  primo livello da `gioco.js`, è nella ricerca
  [`2026-10-12-flusso-agente-fasi`](../ricerche/2026-10-12-flusso-agente-fasi.md)).

### Test del disegno (12/10 sera, flusso a fasi parte 1)

Il difetto vero del 12/10 (l'esito annidato in `logica.js` letto al primo livello da `gioco.js`: niente mostro, sempre «Nessun punto!») passava la logica e la prova di fumo. Dal 12/10 sera i test del gioco possono guidare il gioco vero nel DOM finto: in `gioco.test.js` c'è `apriGioco({ giocatori, seme })` (`agenti/fumo_js.mjs`), che tocca per testo o selettore, manda i comandi a voce attivi, fa passare il tempo e legge il testo visibile (`g.testo()`). Lo scheletro del gioco lo mostra; una correzione di un gioco parte da un test in `gioco.test.js` che fallisce sulla versione di prima (sennò «non sono riuscita a riprodurre il problema: me lo descrivi in un altro modo?»). Il caso del gioco ha un seme fisso nella prova di fumo e in `apriGioco`; `creaCaso(seme)` per i test della logica; `esegui_js` per provare un pezzo di `logica.js` con `console.log`. Dettagli in [agenti-estensioni](agenti-estensioni.md), «Flusso dell'agente a fasi, parte 1».

### Prove

`prova_gioco_voce` (a secco, ~2 s: manifesto, server, ciclo con tutti i contrari, il tool,
chi gioca, la prova di fumo con i comandi), `prova_testo` (le forme e i contrari della regola),
`prova_giochi_pagina` (Edge: la mossa arriva nel riquadro con il solo comando e il nome, il
sottoinsieme a runtime, la pagina non passa nomi non validi né testo libero, ✕ chiude anche
l'ascolto, i comandi nella partita di prova), `prova_agente_guida` (lo scheletro passa i suoi test, anche `gioco.test.js`), `prova_fasi_agente` (il difetto del 12/10 preso dal test del disegno, l'API di `apriGioco`, la riproduzione di una correzione di gioco). Il gioco delle prove è `prove/giochi/porte`.

### Da fare sulla DGX

Il giro vero: chiedere a voce una modifica al gioco di Halloween perché si giochi anche a voce
(«Calliope, nel gioco di Halloween voglio aprire le porte a voce, dicendo il numero della
porta»), guardare che lo sviluppo aggiunga `ascolta` e `quandoComando`, aprirlo in prova
(i comandi arrivano anche lì), poi giocare dal satellite e dal telefono dicendo «la porta
due», «tre», «ricomincia» senza il nome; misurare con `calliope stato --turni` la latenza
delle mosse e quante frasi la finestra del gioco ignora.

## La macchina a stati di Calliope (13/10, ramo `giochi-stati`)

Punto 4 della modalità sviluppo nella [roadmap](../roadmap.md), sul progetto
[`2026-10-12-giochi-macchina-stati.md`](../ricerche/2026-10-12-giochi-macchina-stati.md) con le
risposte di chi amministra del 12/10 (nomi «Giocatore N», l'esito che va avanti da solo dopo circa
4 s, niente Chromium nella sandbox, giochi vecchi tolti al passo 4). Il caso che la motiva è
quello del 12/10: logica.js restituiva l'esito annidato e gioco.js lo leggeva al primo livello,
con i test della logica e la prova di fumo verdi.

**Com'è fatto un gioco nuovo.** Il manifesto dichiara la macchina; logica.js solo la logica pura:

    "scheda": {"tipo": "gioco", "file": ["logica.js"], "giocatori": {"min": 1, "max": 4},
      "macchina": {"inizio": "turno", "fasi": {"turno": {"verso": ["esito", "fine"],
        "comandi": {"porta": {"forme": ["porta {n}", "la porta {n}", "{n}"],
                              "n": {"da": 1, "a": 6}, "etichetta": "Porta {n}"}}}}}}

    const GIOCO = {
      nuovaPartita({ giocatori }) { … return dati; },
      attivi: { turno: (dati, ctx) => ({ porta: [1, 3, 4] }) },     // restringe, mai allarga
      mosse: { turno: { porta(dati, { valore, chi }) {
        return { dati, punti: 1, esito: "Una zucca!", dopo: "turno" }; } } },
      vista: { turno: (dati, ctx) => ({ titolo: "Quale porta apri?" }) },
    };

- **Il motore** (`calliope/estensioni/motore_gioco.js`) è **un solo scrittore** dello stato: le
  fasi standard (preparazione con il numero dei giocatori, «esito» dopo una mossa che va avanti da
  solo dopo `esito_s` secondi o con «avanti», «fine» con la classifica e «ancora»), i turni (il
  turno passa all'uscita dall'esito; `ancora: true` lo tiene), i punti (un numero a chi ha mosso o
  un elenco per tutti), l'istantanea (fase, a chi tocca, giocatori e punti, esito, comandi
  attivi). Il nucleo (`CalliopeMotore.crea`) è puro e senza DOM; `CalliopeMotore.avvia` disegna la
  pagina (titolo, testo, un pulsante per comando e valore, la fascia dei punti), manda a Calliope
  i comandi a voce attivi a ogni fase (`calliope.comandiAttivi`) e riceve le mosse a voce
  (`calliope.quandoComando`); un comando arrivato dopo un tocco che ha già cambiato la fase si
  ignora.
- **La forma dei risultati la controlla il motore** (punto a del compito): una mossa restituisce
  solo `{ dati, punti, esito, fase, dopo, ancora }`. L'esito annidato del 12/10 diventa
  «GIOCO.mosse.turno.porta (valore 1) restituisce campi che il motore non conosce: porte, dietro,
  aperte, risultato. Una mossa restituisce { dati, … }: lo stato del gioco va tutto dentro
  «dati»…»; così anche `dati` mancante, una fase fuori da `verso`, `attivi` che allarga ai comandi
  o ai valori non dichiarati, `vista` con campi o tipi sbagliati (niente più «undefined» o
  «[object Object]» sullo schermo: la vista dà solo testi, il disegno è del motore).
- **Lo slot è un'abbreviazione di un elenco** (`macchina.ascolta`): «porta {n}» con n da 1 a 6
  diventa i comandi a voce piatti `porta_1` … `porta_6`, ognuno con le sue forme intere, più gli
  standard `giocatori_N` («2 giocatori», «siamo in 2»), `inizia`, `avanti`, `ancora` (e
  `fine_partita` con una tela). La voce resta quella dell'11/10 (`gioco_voce.trova`, regola
  `gioco_comando`, finestra senza nome): il principio 10 vale alla lettera, un insieme finito di
  frasi brevi riconosciute per intero, e il server non cambia. Validazione: doppioni con le forme
  di Calliope, forme riservate, {n} da solo solo con al più 12 valori, al più 64 comandi piatti
  (`MAX_ATTIVI` del server). Il motore in JavaScript ricava gli stessi nomi (`tuttiPiatti`, la
  prova lo confronta con Python). Con la macchina il manifesto non ha `ascolta`; chi approva
  sente «si gioca a voce o toccando, con una fase e un comando».
- **La tela** (la via libera per eccezione): una fase con `"pagina": "tela"` e
  `GIOCO.tela[fase](area, dati, tela)`, da cui si esce con `tela.esci({ dati, punti, fase })`,
  controllata come una mossa; «fine partita» vale sempre.
- **Il riquadro** non cambia: `scheda.documento` mette runtime, motore, script del gioco e lo
  script d'avvio, ognuno con la sua impronta nella CSP (`STILE_MOTORE` con le variabili del tema:
  `--sfondo`, `--testo`, `--primario`, `--accento`, `--carattere`, `--raggio`). Un gioco senza
  `macchina` resta com'era.
- **La prova di fumo per fasi** (`fumo_js.mjs`, `esplora`, con lo stesso motore): visita in
  ampiezza gli stati da ogni numero di giocatori, ogni comando attivo con ogni valore (al più 5000
  stati), poi 20 partite a caso con il seme fisso fino alla fine entro 500 passi (300 in più se la
  visita si è fermata al tetto), poi i tocchi a caso sui pulsanti del motore. Dice: mossa che
  lancia (con `logica.js:riga`), forma sbagliata, fase senza uscita («nessun comando attivo
  (strada: porta_2 → avanti → porta_3 → avanti)»), fase dichiarata e mai raggiunta, comando mai
  attivo, partita che non finisce, valori fuori dal dominio. Il gioco delle prove in circa 85 ms
  sul portatile.
- **apriGioco** con la macchina: `g.tocca("2 giocatori")`, `g.tocca("Porta 1")`,
  `g.comando("porta", 3)` (la stessa strada della voce), `g.avanza(4500)` (l'esito che va
  avanti), `g.stato()` (l'istantanea).
- **Gli esempi di accettazione** (punto b): in uno sviluppo di un gioco nuovo la passata del
  progettista dei test (agenti/accettazione.py, la stessa delle estensioni) dichiara i comandi che
  la macchina deve avere e gli esempi in forma chiusa (giocatori, mosse, stato atteso: fase, a chi
  tocca, punti, comandi che valgono o non più, una parola sullo schermo). Il codice li valida e
  scrive `accettazione.test.js` **in sola lettura**, che gioca la partita vera con il motore; i
  vincoli dicono all'agente i comandi (««porta» (fase «turno», da 1 a 6)»); alla consegna l'esito
  va nel risultato e sui requisiti come per le estensioni. Dettagli in
  [agenti-estensioni](agenti-estensioni.md).
- **L'agente** ha lo scheletro nuovo (manifesto con la macchina, `GIOCO`, i due test, niente
  gioco.js: 2 923 caratteri, come prima) e il §5 del contratto riscritto (circa 1 100 caratteri in
  più, ~320 token, da rimisurare sulla DGX); un gioco nuovo consegnato senza la macchina torna
  all'agente. Una versione nuova di un gioco vecchio passa ancora (i giochi vecchi si tolgono al
  passo 4 del progetto, il palco). *Storico dal 14/10: anche la versione nuova di un gioco
  vecchio torna all'agente; vedi «Il palco fisso».*

**Profilo ridotto da 8 GB.** Motore, fasi, pulsanti e voce sono nel browser degli schermi e nel
confronto delle forme: 0 VRAM. La prova di fumo per fasi e gli esempi girano in Node dove gira
l'agente (oggi solo sulla DGX); la passata del progettista è la stessa delle estensioni.

**Cosa resta del progetto** (e perché; *storico dal 14/10: il palco e la rimozione dei giochi
vecchi sono fatti, vedi «Il palco fisso» qui sotto; dal 14/10 sera anche il resto, vedi «Lo
stato della partita» in fondo; il caso «porte» del banco era già stato riscritto con il palco*): il **palco fisso** 1280×720 e 720×1280 con i sei modelli
di pagina e la misura «fuori dal palco» (passo 4: oggi `scelte`, `messaggio` e `tela` con un
disegno semplice che va a capo; è il passo più grande e cambia l'aspetto, da provare sugli
schermi veri), e con lui la **rimozione dei giochi vecchi** (decisione 9); l'**istantanea
validata dal server** con i comandi numerati (passo 2 lato server: oggi il server vede solo i
comandi attivi, come l'11/10); le **domande standard** («a chi tocca?», passo 5) e l'istantanea
nei dati del turno; il **giudice di fase** (passo 6); «**gioco anch'io**» e i **nomi scritti**
(oggi «Giocatore N»); la **ripresa dopo «Riapri»** (decisione 7); le **partite condivise** con il
motore (rimandate dalla decisione 6); il caso «porte» del banco della temperatura è ancora un
gioco del formato di prima (una correzione).

**Da fare sulla DGX**: il giro vero di un gioco nuovo («Calliope, fammi un gioco delle porte per
due giocatori, a voce con il numero della porta»): guardare nel log l'analisi prima del codice
(esempi e comandi), che l'agente scriva la macchina e non gioca.js, la prova di fumo per fasi,
gli esempi alla consegna; poi aprirlo in prova e giocarlo a voce («siamo in due», «porta tre»).
*(dal 14/10 lo stesso giro guarda anche il palco: sotto, «Il palco fisso»)*

## Il palco fisso (14/10, ramo `giochi-palco`)

Passo 4 del progetto [`2026-10-12-giochi-macchina-stati.md`](../ricerche/2026-10-12-giochi-macchina-stati.md)
(§ 5), richiesto esplicitamente da Dario il 14/10, con le risposte di chi amministra del 12/10
(decisione 3: i modelli di Calliope nei due orientamenti; decisione 4: niente Chromium nella
sandbox della DGX; decisione 9: i giochi vecchi si tolgono qui).

**Il palco.** Ogni pagina del gioco si disegna su un palco di misura fissa: **1280×720** in
orizzontale, **720×1280** in verticale (il telefono in piedi), scelto dal rapporto della finestra
(più alta che larga → verticale) e scalato e centrato con `transform: scale(s)`,
`s = min(larghezza / W, altezza / H)`. Mai scroll: il riquadro ha `overflow: hidden`. Cambiando
orientamento (il telefono che si gira) la pagina si ridisegna; cambiando solo la misura si
riscala. Sulla TV 1920×1080 la scala è 1,5; sul telefono 390×844 in verticale ~0,54, e per questo
un pulsante è alto almeno 80 px sul palco (~44 px veri).

**I modelli di pagina** (`macchina.PAGINE`; ogni fase dichiara il suo con `"pagina"`, il disegno
è di Calliope, la vista della logica dà solo dati):

| Modello | Cosa mostra | Usato da Calliope per |
|---|---|---|
| `titolo` | un titolo grande al centro, sottotitolo, testo; i pulsanti in fondo | la preparazione con un numero fisso di giocatori |
| `scelte` | titolo, sottotitolo («Tocca a …»), testo, una griglia di pulsanti (uno per comando e valore, la disposizione con il corpo più grande), la fascia dei punti | la preparazione con il numero dei giocatori |
| `griglia` | una scacchiera fino a 12×12 dalla vista (`caselle`: un elenco di righe uguali, ogni casella un testo o `{ testo, colore, risorsa, comando, valore }`); una casella con un comando attivo è il pulsante della mossa, gli altri comandi attivi vanno in fondo | — |
| `messaggio` | un testo grande (l'esito, o il testo della vista), la riga dei punti presi, i pulsanti in fondo | l'esito di una mossa |
| `punteggi` | una riga per giocatore con i punti, chi tocca evidenziato | — |
| `classifica` | il podio (il primo più grande) e «Ancora» | la fine |
| `tela` | un'area libera (`tela.larghezza` × `tela.altezza` px del palco) per il tempo reale; «Fine partita» in fondo | — |

Testi: il titolo da 60 a 30 px in al più ~150 px d'altezza (230 in verticale), il testo da 38 a
22, il messaggio grande da 84 a 36; il corpo si sceglie a passi di 2 px, il più grande che ci
sta. I colori delle caselle sono un elenco chiuso di nomi o `#rrggbb`, le risorse un `.svg` di
`scheda.risorse`. Il tema (`tema.css`) cambia solo le variabili (`--sfondo`, `--testo`,
`--primario`, `--accento`, `--carattere`, `--raggio`, `--casella`, `--bordo`): posizione,
misura e corpo di ogni scatola il motore li mette in linea con `!important`.

**L'impaginazione è una funzione pura.** `CalliopeMotore.impagina(contenuto, orientamento)` →
le scatole (tipo, posizione, misura, corpo, testo) in ordine di lettura; il nucleo dà il
contenuto della pagina di adesso (`pagina(S)`: modello, testi con la loro fonte, pulsanti,
caselle, giocatori). Lo stesso codice gira nel riquadro (che crea un elemento per scatola) e in
Node: così la misura si fa **senza browser**, dove gira l'agente (decisione 4). La larghezza del
testo è stimata per carattere, un po' più larga del vero (strette, larghe, maiuscole, cifre; il
grassetto +8 %), così ciò che «sta» nel calcolo sta anche sullo schermo.

**La misura «fuori dal palco»** (`controllaPalco`, `difettiPalco`): scatole fuori dal palco, scatole
che si sovrappongono, testo che non ci sta neanche al corpo minimo, e le cause (troppi pulsanti
per la pagina, una griglia con caselle sotto i 32 px, una tela schiacciata). Detti in parole per
l'agente, prima la causa poi gli effetti raggruppati, al più tre per pagina:

    40 pulsanti non ci stanno nella pagina «scelte» (orizzontale 1280×720): al più 28 di almeno
    150×80 px. Restringi i comandi attivi (GIOCO.attivi), accorcia le etichette o usa la pagina
    «griglia»
    il titolo «Quale delle centoventi porte …» non ci sta nella pagina «scelte» (verticale
    720×1280) neanche a 30 px (18 righe dove ne stanno 6): accorcialo, al più circa 202
    caratteri (GIOCO.vista.domanda.titolo)

- **Nella prova di fumo** (`fumo_js.mjs`, `esplora`): ogni pagina diversa raggiunta dalla visita
  delle fasi e dalle partite a caso, nei due orientamenti, una volta sola. Un difetto è un
  `FALLITO prova di fumo del gioco` con la fase e la strada («palco: fase «domanda» (strada:
  giocatori_2 → parti): …. La pagina la disegna Calliope: cambia i testi, i comandi attivi o il
  modello di pagina, non il disegno»): l'agente lo corregge come gli altri errori. Il gioco delle
  prove passa test e prova di fumo in ~0,3 s sul portatile, Node compreso.
- **Nei test** `g.palco()` dà i difetti della pagina di adesso (`[]` se ci sta); lo scheletro
  lo mostra.
- **Nel browser vero** il motore misura anche il disegno (dopo due fotogrammi:
  `getBoundingClientRect` contro il palco, `scrollHeight`/`scrollWidth` contro la scatola con un
  margine di 0,3 em per i caratteri che sporgono dalla riga) e lo manda a Calliope con il tipo
  `palco` (al più tre frasi, solo quando cambia, anche `[]`). Il server lo tiene sul posto
  (`Posto.palco`) e, se c'è un difetto nuovo, nel registro (regola `gioco_fuori_dal_palco`) e nel
  log; vale anche in una partita di prova (è una diagnosi, come i comandi: `TIPI_PROVA`). Prende
  ciò che il calcolo non prevede: un tema che allarga il testo, un carattere diverso, il disegno
  dentro una tela. *Non ancora detto a voce al collaudo* (resta nel log e nel registro).

**Giochi vecchi tolti** (decisione 9; Calliope non è in produzione, niente migrazioni):
- `scheda.normalizza` vuole `macchina`: un gioco senza («un gioco si scrive con la macchina a
  stati di Calliope…», `SENZA_MACCHINA`) non si approva, anche come versione nuova di un gioco
  che c'era; `ascolta` nel manifesto è rifiutato («non c'è più»). Nella scheda normalizzata
  `ascolta` resta, scritto da Calliope dalla macchina.
- Un gioco del formato di prima già approvato (sulla DGX ce ne sono) non si apre più: «è un gioco
  del formato di prima: va rifatto con lo sviluppo, chiedimelo come modifica» (regola
  `gioco_formato_vecchio`), e `Giochi.documento` non lo compone.
- Il runtime non dà più al gioco `calliope.quandoComando` né `calliope.comandiAttivi`: li mette
  in un canale riservato (`__calliopeMotore`, con `palco`) che il motore prende e toglie prima
  del codice del gioco. Non è un confine (il confine resta la pagina e il server), ma l'agente
  non ha più due modi di fare la stessa cosa.
- `macchina.giocatore: true` porta alla mossa il nome di chi è riconosciuto dalla voce
  (`ctx.giocatore`, come l'`ascolta.giocatore` dell'11/10), con lo stesso divieto con
  `rete_leggi`; chi approva sente «… e il nome di chi gioca».
- I giochi delle prove rifatti: `porte` (la voce, con il nome), `tris` (la `griglia`, contro il
  computer da solo), `ostile` (gli attacchi, in una `tela`), `segnali` (una `tela` condivisa tra
  due schermi: le partite condivise del motore restano rimandate, decisione 6), `pagine` (tutti
  i modelli).

**Per l'agente.** Lo scheletro del gioco dichiara `"pagina": "scelte"`, una riga dice i modelli e
il test del disegno controlla `g.palco()` (3 347 caratteri, prima 2 923: ~120 token in più); il
§5 del contratto descrive il palco, i modelli, le caselle, il tema solo a variabili, la tela con
la sua misura e `macchina.giocatore` (6 294 caratteri, prima 4 973: ~380 token); il prompt del
gioco dice di scegliere la pagina per ogni fase. Il prompt intero del gioco passa da 22 902 a
24 900 caratteri (~575 token con il rapporto 3,47 di Qwen3.6, da rimisurare sulla DGX). Il
vincolo della correzione di un gioco non parla più di gioco.js ma di vista, esito, pagina e
`g.palco()`; `CAPACITA_GIOCO` dice che ogni fase sta in una pagina senza scorrere.

**Un difetto trovato strada facendo**: la prova di fumo sceglieva i tocchi a caso con un
generatore lineare e `seme % n`, che con due elementi li alternava sempre (in una tela con «Fine
partita» il pulsante della tela non si toccava mai due volte di fila); ora usa `creaCaso`.

**Profilo ridotto da 8 GB.** Palco, modelli e misura sono nel browser degli schermi e in Node
dove gira l'agente: 0 VRAM, niente di nuovo sulla GPU.

**Prove.** `prova_gioco_palco` (a secco, ~3 s: l'impaginazione pura dei sette modelli nei due
orientamenti, otto giocatori, tris e porte; i difetti messi apposta; la prova di fumo con il
palco e i suoi contrari; `g.palco()`; la diagnosi in prova), `prova_giochi_pagina` (Edge: ogni
modello misurato sullo schermo vero a 900×800 e a 390×844 senza difetti, un tema che allarga il
titolo → «testo tagliato» a Calliope, un tocco vero sulla casella del tris nel punto che
l'impaginazione pura calcola), e le prove dei giochi rifatte (`prova_giochi`, `prova_gioco_voce`,
`prova_gioco_macchina`, `prova_agente_guida`, `prova_fasi_agente`, `prova_giro_porte`,
`prova_giro_halloween`).

**Cosa resta del progetto** (*storico dal 14/10 sera: istantanea, domande standard, giudice,
nomi, ripresa e partite condivise sono fatti, vedi «Lo stato della partita» qui sotto*):
l'**istantanea validata dal server** con i comandi numerati (passo 2
lato server); le **domande standard** («a chi tocca?», passo 5); il **giudice di fase** (passo 6);
«**gioco anch'io**» e i **nomi scritti**; la **ripresa dopo «Riapri»**; le **partite condivise**
con il motore; una tela che dichiara un solo orientamento e fa dire «Gira il telefono»
(decisione 3, non fatto); la diagnosi del palco detta a voce al collaudo; la misura del disegno
dentro una tela fuori dal browser (in Node il DOM finto non ha impaginazione); provare sugli
schermi veri (TV, tablet, telefono) l'aspetto dei modelli.

**Da fare sulla DGX** (dopo `calliope aggiorna`): i giochi già approvati del formato di prima non
si aprono più: chiederli come modifica («Calliope, rifai il gioco di Halloween») e guardare il
giro dell'agente; nel giro vero di un gioco nuovo guardare nel log se la prova di fumo dice
qualcosa del palco e se l'agente lo corregge cambiando testi o pagina; aprirlo in prova sul
telefono in piedi e girato, e guardare nel registro (`gioco_fuori_dal_palco`) se lo schermo vero
ha trovato qualcosa che il calcolo non prevede.

## Lo stato della partita (14/10 sera, ramo `giochi-passi-finali`)

I passi che restavano del progetto
[`2026-10-12-giochi-macchina-stati.md`](../ricerche/2026-10-12-giochi-macchina-stati.md), chiesti
da Dario il 14/10 sera, con le risposte di chi amministra del 12/10 (decisione 1: «Giocatore N»,
poi «gioco anch'io» con la voce o il nome scritto, detto da Calliope solo dopo i controlli;
2: giudice senza il nome spento; 5: dopo una mossa capita dal giudice Calliope dice l'etichetta
breve; 6: partite condivise rimandate; 7: ripresa dopo «Riapri» sì).

### L'istantanea validata dal server (passo 2 lato server)

Prima il server sapeva solo quali comandi a voce valevano (`comandi`, mandato dal motore); il
resto della partita (fase, a chi tocca, punti) lo sapeva solo il riquadro.

- **Il motore manda l'istantanea** dopo ogni disegno (all'avvio, dopo ogni mossa, dopo l'esito
  che va avanti da solo, dopo «Riapri»), con il tipo `stato` al posto di `comandi`:
  `{n, fase, tocca, turno, giocatori: [{nome, punti}], esito, comandi}` (`nucleo.perCalliope`;
  `tocca` è la posizione, `comandi` i comandi a voce piatti attivi). `g.stato()` dei test resta
  com'era (a chi tocca per nome, i comandi per comando e valore): è l'interfaccia dell'agente.
- **Il server la valida** contro il manifesto approvato (`macchina.valida_istantanea`): `n` che
  non cala (la stessa mandata di nuovo, per un ridisegno, passa), fase dichiarata o standard,
  comandi solo tra quelli che quella fase può avere (`macchina.per_fase`: mai comandi nuovi né di
  un'altra fase), al più `giocatori.max` giocatori, punti numeri limitati, `tocca` dentro i
  giocatori, esito al più 160 caratteri, nessun campo in più. Un nome fuori dalla forma chiusa
  (lettere, spazi, apostrofo, al più 20 caratteri e due parole) resta sullo schermo ma per
  Calliope è «Giocatore N». La tiene sul posto (`Posto.istantanea`): i comandi a voce attivi
  vengono **solo** da lì. Una non valida si scarta (regola `gioco_stato_non_valido`, nel
  registro dell'estensione con il motivo) e il gioco non ascolta finché non ne arriva una buona;
  dopo «pronto» (anche «Riapri») non ascolta finché il motore non manda la prima: il server non
  deduce mai lo stato.
- **Il comando a voce porta `n`**, il numero dell'istantanea su cui è stato riconosciuto. Il
  motore lo rifiuta se nel frattempo la partita è andata avanti (un tocco arrivato prima,
  l'esito che è passato da solo) o se il comando non vale più, e lo dice con `rifiutato`
  (regola `gioco_comando_vecchio` o `gioco_comando_rifiutato`, nel registro): la partita non
  cambia. Così lo stato del gioco e quello di Calliope non divergono per costruzione.
- La pagina (schermo.js, anche sul telefono) passa `stato` (`istantanea`, `ripresa`) e
  `rifiutato` (`comando`, `motivo`, `n`) e niente altro; `n` verso il riquadro solo se è un
  intero. Il messaggio `stato` ha un tetto più alto (porta anche la ripresa, sotto). Valgono
  anche in una partita di prova (`TIPI_PROVA`): sono un ingresso, non un ponte.
- Il runtime del riquadro dà al motore `stato` e `rifiutato` sul canale riservato
  (`__calliopeMotore`) al posto di `comandiAttivi`; il codice del gioco non li vede.

Prove: `prova_gioco_stato` (a secco, ~1 s: la validazione con 21 istantanee cattive, il server,
il motore nel DOM finto con il comando vecchio rifiutato e l'andata e ritorno di tutte le
istantanee del motore nella validazione Python), `prova_gioco_voce` rifatta sull'istantanea.

### Calliope sa a che punto è il gioco (passo 5)

- **Le domande standard** (`calliope/gioco_stato.py`, regola `gioco_stato_detto` del ciclo):
  «a chi tocca?», «di chi è il turno?», «quanti punti ho?», «il punteggio?», «chi sta
  vincendo?», «come siamo messi?», «cosa posso dire?» e poche altre forme, riconosciute **per
  intero** (il nome davanti, maiuscole e punteggiatura non contano), in ogni fase e anche nella
  finestra del gioco senza il nome. È il caso ammesso dal principio 10: forma chiusa e breve,
  per intero, effetto reversibile (una frase detta). La risposta la compone il codice
  dall'istantanea validata: «Tocca a Giocatore 2.» (durante l'esito «Ha appena giocato …»),
  «Hai 3 punti.» se la voce di chi chiede è riconosciuta in quella frase e ha il nome di un
  giocatore, altrimenti i punti di tutti, «Sta vincendo Bianca, con 5 punti.» (pari, fine,
  da solo), «Puoi dire: porta 1, 3 o 4, oppure ricomincia.» (i valori degli slot insieme). Nel
  registro esito `gioco_stato`, la domanda e i millisecondi, **nessun testo**; l'atto della voce
  è `gioco_stato` (fuori dalla storia). Niente modello: testo→voce ~0,35 s sulla DGX.
- **Contrari** (`prova_testo`, `prova_gioco_stato`): dentro una frase più lunga («a chi tocca
  adesso secondo te?», «quanti punti ha Bianca?») non vale (senza il nome nella finestra si
  ignora, con il nome va al modello); senza un gioco aperto sullo schermo di quel satellite,
  con il gioco di un altro satellite, con una domanda di Calliope in sospeso la frase va al
  modello. Un gioco non può dichiarare una di queste forme come comando (manifesto rifiutato:
  «è una domanda di Calliope sul gioco»).
- **L'istantanea nei dati del turno** per le altre domande («chi sta perdendo?», «quante porte
  restano?»): al posto della riga dei soli comandi, «Sullo schermo c'è il gioco «Le porte del
  castello», fase turno. Tocca a Giocatore 2. Punti: Ada 3, Giocatore 2 5. Comandi a voce
  adesso: porta 1, 3 o 4.» (circa 60 token), più la riga su `gioco_comando` se il tool c'è. Il
  testo dell'esito della mossa **non** c'è mai (è del gioco: si mostra sullo schermo). Con un
  nome scritto sullo schermo (testo del gioco, passo 4 qui sotto) la riga va **in busta**, fonte
  `gioco` (`provenienza.FONTI`, dalla porta unica `Brain.dato_non_fidato`; regola
  `gioco_stato_in_busta`).
- **Profilo da 8 GB**: confronto delle forme e frase composta dal codice, 0 VRAM; la riga dei
  dati del turno ~60 token.

### Il giudice di fase (passo 6)

Quando una frase **rivolta a Calliope** (con il nome, o nella finestra di sempre dopo una
risposta) non è una forma chiusa del gioco aperto né una domanda standard («apri la terza»,
«proviamo con la prima», «uno, no aspetta, la cinque»), il significato lo decide il modello
(principio 10), ma con una **chiamata breve e separata** (`calliope/gioco_giudice.py`), non il
turno intero del modello della voce con `gioco_comando`.

- **Uscita vincolata**: lo schema JSON di Ollama (`format`) con un `enum` delle etichette dei
  comandi attivi adesso (dall'istantanea validata) più «nessuno». Non può inventare un comando
  né un valore fuori dominio. Vede solo il titolo, i comandi della fase e la frase: né la
  conversazione né dati di casa.
- **Il prompt lo scrive Calliope** dai comandi della macchina, nella forma B misurata dal
  prototipo del 12/10: comandi con il loro significato (le forme dichiarate, per i comandi di
  Calliope una frase fissa: «va avanti dopo l'esito della mossa»), i valori che adesso non
  valgono («adesso non valgono 2»), l'ordinale («la prima = 1», «l'ultima» è il massimo del
  dominio), «nessuno» in testa con i casi (domande, chiacchiere, un valore che non c'è, più
  comandi insieme), esempi, «se la persona cambia idea vale l'ultima scelta». Mai l'agente.
- **Modello**: quello del giudizio «rivolta» (`rivolta.dove`: il rilevatore e4b già residente
  sulla DGX, altrimenti il modello della voce su Ollama, con lo stesso `num_ctx`: niente
  ricaricamento, cache della voce intatta), o `giochi_giudice_modello`; `temperature` 0,
  `think` spento, al più `giochi_giudice_timeout_s` (2 s). Un giudizio guasto o scaduto vale
  «nessuno».
- **Nel ciclo** (`Ciclo._giudice_di_fase`, dopo le forme chiuse e le domande standard): una
  mossa capita parte come quella diretta (con il numero dell'istantanea e, con
  `macchina.giocatore`, il nome di chi è riconosciuto dalla voce) e Calliope dice l'**etichetta
  breve** («Porta 3.», decisione 5: è un'interpretazione delle parole, chi parla deve sentire
  cosa ha capito; atto `gioco_mossa`). Registro: esito `gioco_giudice`, regola `gioco_giudice`,
  `gioco: {comando, ms, giudice_ms}`, niente testo. Con «nessuno» la frase va al modello della
  voce con l'istantanea nei dati del turno, e il giudizio resta nel registro
  (`gioco_giudice: {comando: null, ms}`).
- **Senza il nome** nella finestra del gioco il giudice resta **spento**
  (`giochi_giudice_senza_nome: false`, decisione 2): lì valgono solo le forme chiuse e le
  domande standard, il resto si ignora come prima. Da decidere dopo aver misurato sulla DGX
  quante frasi la finestra ignora (`gioco_finestra_ignorata` in `calliope stato --turni`).
- **`gioco_comando`** (il tool dell'11/10 per il modello della voce) si registra solo con il
  giudice spento (`giochi_giudice: false`): stessa cosa, un turno intero e ~106 token di schema
  in meno nel prompt della voce quando il giudice è acceso. La riga dei dati del turno lo nomina
  solo se c'è.
- **Misura** (`prove/prova_gioco_giudice_ollama.py`, portatile RTX 5070 Laptop, gemma4
  e4b-it-qat, le 22 frasi del prototipo sulle porte da 1 a 5 con la 2 aperta, prompt scritto
  dal codice): **21/22 in due giri**, nessuna mossa su «a chi tocca?» e «quanti punti ho?»,
  **mediana 313–323 ms, p90 336–340 ms** (il prototipo con il prompt scritto a mano: 21/22, 357
  ms). Sbagliata, come nel prototipo, «apri la tre e poi la quattro» → porta 4 («vale l'ultima»
  batte «più comandi insieme»): reversibile, una mossa.
- **Profilo da 8 GB**: sul modello della voce già in memoria, nessuna VRAM in più;
  `giochi_giudice: false` lo spegne. Sulla DGX sul rilevatore e4b (stima 0,2–0,35 s), da misurare
  con `calliope stato --turni` (esito `gioco_giudice`, `giudice_ms`).

### «Gioco anch'io» e i nomi scritti (passo 4, nomi)

Decisione 1 di chi amministra (12/10): «Giocatore N» subito, poi «gioco anch'io» con la voce
riconosciuta o il nome scritto sullo schermo, detto da Calliope solo dopo i controlli; niente
nome libero passato dal modello.

- **«Gioco anch'io»** è un comando standard di Calliope della preparazione (`anchio`: «gioco
  anch'io», «anch'io», «anche io», «ci sono anch'io»; pulsante «Gioco anch'io»), attivo finché
  c'è posto. Prende un posto con il nome di chi l'ha detto se la voce è riconosciuta in quella
  frase (con `macchina.giocatore`: true, come le mosse), altrimenti «Giocatore N»; la stessa voce
  due volte non prende due posti. «Inizia» parte con quei giocatori (almeno `giocatori.min`),
  «N giocatori» con i primi N; la preparazione mostra «Giocano: Ada, Giocatore 2». I nomi
  restano ad «ancora» e arrivano alla logica in `nuovaPartita({ nomi })` e in `ctx.giocatori`.
- **Un ospite** (o chi non è riconosciuto) si dà un nome a voce con la forma chiusa intera
  «(gioco) anch'io, sono / mi chiamo <nome>» (regola `gioco_anchio_nome`,
  `gioco_stato.anchio_nome`: una o due parole di sole lettere, non «pronto», «qui», «stanco»…);
  il nome detto vale come uno scritto (sotto). Contrari in `prova_testo`.
- **Il nome scritto**: chi gioca tocca il suo nome nella fascia dei punti (un pulsante, «Cambia
  il nome: …») e lo scrive in un campo sopra la fascia (Invio o uscita dal campo confermano, Esc
  annulla). Il motore accetta solo la forma chiusa (lettere, spazi e apostrofo, al più 20
  caratteri e due parole) e un nome diverso dagli altri; se no un avviso sul palco e la partita
  non cambia (non è un errore del gioco). Nell'istantanea il giocatore è segnato `scritto`.
- **Cosa dice Calliope** (`Giochi._nomi_detti`): «Giocatore N» e i nomi che Calliope stessa ha
  mandato dalla voce riconosciuta (`Partita.nomi_voce`) si dicono; ogni altro nome (scritto,
  detto «sono Pippo», o un nome che il motore dichiara senza che Calliope l'abbia mandato: il
  server non si fida del motore) è **testo del gioco**: si dice solo se passa i controlli delle
  frasi dei giochi (`riferire.controlla_testo`; con un minore o un ospite nella partita il
  guardiano, che se manca o è guasto per un minore blocca), mai in una partita di prova; se no
  resta sullo schermo e a voce è «Giocatore N» (regola `gioco_nome_fermato`). Giudizio in cache
  per partita. Con un nome scritto detto, l'istantanea nei dati del turno va in busta.
- «Tocca ad Ada» con la d eufonica, sullo schermo e a voce.

Prove: `prova_gioco_stato` (sezione 7: motore, server, ciclo), `prova_testo` (le forme di
«anch'io, sono …» e i contrari), `prova_giochi_pagina` (la preparazione dice «gioco anch'io»).

### La ripresa dopo «Riapri» (decisione 7)

Prima «Riapri» (dopo ✕, Esc, «chiudi il gioco») o una pagina ricaricata facevano ripartire la
partita da capo. Ora riparte **dall'ultima istantanea valida**:

- Il motore manda con ogni istantanea anche lo **stato intero** della partita (`ripresa`: fase,
  giocatori, punti, a chi tocca, i dati della logica), se sta in 16 000 caratteri (come `salva`;
  oltre non si manda e quella partita non si riprende).
- Il server lo tiene sul posto (`Posto.ripresa`) **solo** se accompagna un'istantanea valida, con
  lo stesso numero e la stessa fase; un'istantanea non valida non lo cambia (resta l'ultima
  buona), una valida senza ripresa lo toglie (mai una partita vecchia). Non lo legge: è opaco,
  come i dati di `salva`, e torna solo al riquadro dello stesso posto (schermo) della stessa
  partita.
- Al «pronto» di un riquadro nuovo dello stesso posto l'avvio lo porta (`avvio.ripresa`); il
  motore lo controlla (`nucleo.riprendi`: forma, fase dichiarata, giocatori e punti, dati,
  comandi attivi e pagina calcolabili) e riparte da lì, con lo stesso numero (il server dopo
  «pronto» accetta di nuovo da capo); se non va, partita nuova. Ripreso nell'esito, l'esito va
  avanti da solo come prima. Una partita nuova (un'altra richiesta del gioco) parte da capo.
- Profilo da 8 GB: niente (browser e server).

Prove: `prova_gioco_stato` (sezione 8), `prova_gioco_stato_pagina` (Edge: ✕ e «Riapri» nella
pagina vera, con il nome scritto e la porta già aperta).

### Le partite condivise con il motore (decisione 6, rimandata e fatta qui)

Prima, in una partita condivisa tra schermi (`scheda.condivisa`) ogni riquadro aveva il suo
motore: due partite diverse (sorteggi, turni, punti), sincronizzate solo se il gioco lo faceva da
sé con `manda` (com'è ancora la tela dei «segnali»). Il progetto (§ 2.4) diceva: «il primo posto
sarebbe l'autorevole e gli altri riceverebbero istantanee e vista». Fatto così:

- **Chi tiene la partita**: per una partita condivisa con la macchina **e senza tela**
  (`Partita.motore_condiviso`), il primo riquadro che dice «pronto» è l'**autorevole**
  (`Partita.autorevole`): il suo motore è l'unico che scrive lo stato e manda istantanee. Gli
  altri schermi sono **specchi** (`avvio.ruolo`).
- **Gli specchi disegnano lo stato**: a ogni istantanea valida dell'autorevole il server manda
  lo stato intero (lo stesso della ripresa) agli altri schermi (evento «gioco» di tipo
  `partita`), e il loro motore lo disegna (`nucleo.riprendi`, poi la pagina: la vista è una
  funzione pura dei dati, quindi uguale). Uno specchio che si apre o riapre lo riceve all'avvio.
  Uno specchio non manda istantanee (se ci prova: 403, regola `gioco_stato_non_autorevole`, e
  torna specchio con l'evento `specchio`), non fa andare avanti l'esito da solo, non manda la
  fine.
- **Le mosse degli specchi**: un tocco su uno specchio diventa un messaggio `mossa` (comando
  piatto e numero dell'istantanea su cui è stato toccato) che il server controlla contro
  l'ultima istantanea valida dell'autorevole (solo comandi attivi, numero intero; regola
  `gioco_mossa_rifiutata`) e manda al suo motore come un comando a voce: lo stesso controllo del
  numero (una mossa vecchia è rifiutata). Un nome scritto su uno specchio va all'autorevole
  (`mossa` con `rinomina` e `nome`, forma chiusa) che lo scrive.
- **La voce**: un comando sentito dal satellite dello schermo di uno specchio vale con i comandi
  dell'autorevole e la mossa va al suo motore (`Partita.tiene`); le domande standard leggono la
  sua istantanea.
- **Chi tiene la partita se ne va** (✕, cane da guardia, o la sua pagina tace da `VIVO_S` quando
  uno specchio muove o si riapre): la partita passa a un altro schermo aperto (evento
  `autorevole` con l'ultimo stato, regola `gioco_partita_passata`), che riparte da lì. Chi la
  teneva, riaperto, è uno specchio.
- **Protezioni** come per `manda`: con dati personali letti dalla partita lo stato non va agli
  altri schermi (`gioco_dati_personali`); con un minore o un ospite nella partita non ci va se
  un nome scritto non passa i controlli (`gioco_nome_fermato`). Il giudizio di un nome vale per
  chi c'è nella partita: se arriva un minore o un ospite si rigiudica (una prova l'ha trovato).
- **Pagina e runtime**: `mossa` dal riquadro (campi `comando`, `n`, `rinomina`, `nome`); verso il
  riquadro `partita`, `autorevole`, `specchio` (lo stato, un oggetto entro il tetto di `stato`) e
  `nome` (`i` intero, `nome` al più 20 caratteri); il canale riservato al motore ha
  `quandoPartita`, `quandoAutorevole`, `quandoSpecchio`, `quandoNome` e `mossa` (il codice del
  gioco non li vede). L'agente non scrive niente in più (una riga nel contratto: con
  `"condivisa": true` la partita la tiene un motore solo).
- **Cosa non fa** (da decidere se serve; *storico dal 15/10: fatto, vedi «Chi è quale
  giocatore» qui sotto*): chi è quale giocatore. I turni restano quelli del
  motore (`tocca`), e ogni schermo può muovere quando tocca a qualcuno: va bene per giocare
  insieme da due stanze, non impedisce a uno schermo di muovere per l'altro. Una tela condivisa
  resta com'era (ogni schermo il suo motore, i messaggi con `manda`).

Prove: `prova_gioco_stato` (sezione 9: due motori nel DOM finto, autorevole e specchio, e il
server con i contrari), `prova_gioco_stato_pagina` (Edge, due pagine: tocchi veri sullo
specchio, la stessa pagina sulle due).

### Il caso «porte» del banco della temperatura

Verificato il 14/10 sera: il caso «porte» di `prove/manuali/banco_temperatura.py` è già nel
formato nuovo (la macchina a stati, niente `gioco.js`: riscritto con il palco fisso, vedi
[agenti-estensioni](agenti-estensioni.md), «Il banco del 14/10»). `banco_temperatura.py --secco`:
tutto ok (porte rosse alla partenza e verdi sul riferimento, i vincoli della correzione con il
test che riproduce in `gioco.test.js`, il tetto con e senza la riproduzione). Niente da cambiare.

### Cosa resta, e il giro sulla DGX

**Resta del progetto** (*storico dal 15/10: «Gira il telefono» e chi è quale giocatore sono
fatti, vedi «Chi è quale giocatore» qui sotto*): «Gira il telefono» per una tela che dichiara un
orientamento solo (decisione 3, non fatto); la diagnosi del palco detta a voce al collaudo; nelle
partite condivise, chi è quale giocatore (oggi ogni schermo muove quando tocca a qualcuno); il giudice
senza il nome (decisione 2: da decidere dopo la misura); la partita come attività della macchina
a stati del dialogo (§ 4 del progetto, «in futuro»). La prova del palco nel browser della DGX
(passo 8) resta scartata (decisione 4).

**Da fare sulla DGX** (dopo `calliope aggiorna`; ricaricare la pagina degli schermi e del
telefono, sono file statici):
- il giro vero dell'agente su un gioco nuovo, a voce: «Calliope, fammi un gioco delle porte da 2
  a 4 giocatori, a voce con il numero della porta» → guardare nel log l'analisi prima del codice
  (comandi ed esempi), la macchina e la prova di fumo per fasi con il palco, gli esempi alla
  consegna; poi «aprilo in prova» e giocarlo dal satellite e dal telefono: «gioco anch'io» (il
  nome di chi parla), «Calliope, inizia», «porta tre», «Calliope, apri la terza» (il giudice:
  «Porta 3.»), «a chi tocca?» e «quanti punti ho?» anche senza il nome, un nome scritto toccando
  la fascia, ✕ e «Riapri» (riprende), e la stessa partita da due schermi (con `"condivisa":
  true`: «Calliope, voglio giocarci anche dalla cucina»);
- misurare con `calliope stato --turni`: esito `gioco_comando`, `gioco_stato`, `gioco_giudice`
  (`giudice_ms` sul rilevatore e4b, stima 0,2–0,35 s), e quante frasi la finestra del gioco
  ignora (`gioco_finestra_ignorata`) per decidere `giochi_giudice_senza_nome`;
- nel registro dell'estensione: `gioco_stato_non_valido` (deve restare 0 con un gioco sano),
  `gioco_comando_vecchio`, `gioco_nome_fermato`, `gioco_partita_passata`.

## Chi è quale giocatore e «Gira il telefono» (15/10, ramo `giochi-giocatori`)

Roadmap 1.4, ciò che restava del progetto
[`2026-10-12-giochi-macchina-stati.md`](../ricerche/2026-10-12-giochi-macchina-stati.md) dopo il
14/10 sera (decisione 3 di chi amministra: «Gira il telefono» per una tela). Prima ogni schermo
di una partita condivisa poteva muovere quando toccava a qualcuno, e su uno schermo solo la voce
di Bruno muoveva per Ada; la tela orizzontale sul telefono in verticale si vedeva piccola senza
che nessuno lo dicesse.

### Il legame: schermo e voce

- **Lo schermo** è il numero del posto nella partita (`Posto.giocatore`, 1, 2…: lo dà il server al
  «pronto» e lo manda all'avvio). Conta solo in una partita **tra più schermi** (`avvio.condivisa`):
  su uno schermo solo nessun giocatore è legato a uno schermo e le mosse non lo portano. I tocchi
  dello schermo che tiene la partita portano il suo numero; quelli di uno specchio arrivano al
  motore con il numero **messo dal server** (`_t_mossa`), mai dallo specchio; le mosse a voce, tra
  più schermi, con il numero dello schermo del satellite che le ha sentite (`Giochi.comando`).
- **La voce** è un **segno opaco** per partita («v1», «v2»…, `Partita.voci`, `voce_di`): Calliope
  lo dà a ogni persona riconosciuta dalla voce in quella frase (lo stesso criterio di sempre:
  sopra soglia, margine, lunghezza; mai la zona grigia né gli ospiti). Al riquadro arriva solo il
  segno (in un gioco per più giocatori), mai il nome se il manifesto non chiede
  `macchina.giocatore`: il gioco non sa chi è. Un segno che Calliope non ha dato non lega nessuno
  (il server lo toglie dall'istantanea).
- **Il legame nasce con «gioco anch'io»** (detto o toccato): il motore tiene gli iscritti della
  preparazione con nome, schermo e voce (`S.iscritti`) e li porta nei giocatori (`schermo`,
  `voce` nell'istantanea, validati da `macchina.valida_istantanea`: numero da 1 a 99, segno
  `v1`–`v99`). La stessa voce due volte non prende due posti. Con «N giocatori» o «Inizia» senza
  «gioco anch'io» i giocatori restano **liberi**: chiunque muove quando tocca a loro, come prima.

### Chi muove (`chiMuove` nel motore, `macchina.chi_muove` sul server)

Solo per le mosse del gioco in una fase **a turni** con più di un giocatore (i comandi di Calliope,
«avanti», «ancora», «inizia», valgono per tutti):
- la **voce** di un altro giocatore → rifiutata (`turno`); la voce di chi è di turno → vale anche
  da un altro schermo; una voce che non gioca (qualcuno che aiuta) passa allo schermo;
- lo **schermo** di un altro giocatore, quando la voce non è riconosciuta → rifiutata (`schermo`);
- una mossa senza voce riconosciuta da uno schermo con più giocatori (uno schermo, due persone)
  vale per chi è di turno: un comando di una parola è spesso troppo corto per l'impronta, e il
  tocco non dice chi tocca. È il limite noto: lì decide il turno.

Nelle fasi **senza turni** non si rifiuta niente, ma i punti (e `ctx.chi`) vanno a **chi ha
mosso** se si sa (la sua voce, o il suo schermo con un giocatore solo), non a «chi tocca».

Dove: il motore è il solo che decide (un tocco sullo schermo sbagliato non parte e lo dice un
avviso sul palco, «Tocca a Giocatore 1, sull'altro schermo.»; una mossa a voce o di uno specchio
che non vale torna a Calliope come `rifiutato` con il motivo). Il server fa lo stesso controllo
sull'ultima istantanea valida **prima** di mandare una mossa a voce (`Giochi.turno_altrui`), così
Calliope può dire «Tocca ad Ada.», «Tocca ad Ada, sullo schermo «Cucina».» o «Sei già nella
partita: sei Ada.» invece di tacere (`Ciclo._turno_altrui`, anche per il giudice di fase e il tool
`gioco_comando`; regola `gioco_turno_altrui`, esito `gioco_turno_altrui`, niente testo nel
registro). È un vincolo sullo stato della partita, non una regola sul testo (principio 10).

### Le domande

«A chi tocca?» risponde «Tocca a te.» a chi è riconosciuto dalla voce **legata** al giocatore di
turno (prima solo se il nome del giocatore era il suo), e aggiunge lo schermo quando il giocatore
gioca da un altro («Tocca a Bruno, sullo schermo «Cucina».»); «quanti punti ho?» dalla voce
legata. Nuova domanda standard (regola `gioco_stato_detto`, per intero; contrari in
`prova_testo`): «che giocatore sono?», «quale giocatore sono (io)?», «chi sono nel gioco?» →
«Sei Ada.» dalla voce, «Su questo schermo gioca Ada.» dallo schermo, oppure come entrare. «Chi
sono?» da solo resta al modello. `Giochi.ascolto` porta per questo il numero dello schermo, i nomi
degli schermi della partita e i segni (restano dentro Calliope).

### Chi entra a metà

«Gioco anch'io» vale anche a partita cominciata (nelle fasi del gioco che non sono una tela, e
nella fine), finché c'è posto: **solo a voce** (la pagina del gioco non cambia: niente pulsante in
più che sposti il palco; `g.stato()` dei test dell'agente non lo mostra). Senza altro, chi entra
**gioca dalla prossima partita** (un avviso «Si gioca in più dalla prossima partita.», poi «ancora»
lo mette in fondo): la logica ha già preparato i dati per chi c'era. Se la logica dichiara
`GIOCO.entra(dati, ctx)` (`ctx.nuovo`: la posizione del nuovo) entra **subito**, a zero punti, e
gioca quando arriva il suo turno; la forma dei dati si controlla come per `nuovaPartita`. La stessa
voce due volte, o chi gioca già, no («Sei già nella partita…»). Il contratto lo dice in una riga.

### «Gira il telefono»

- Una fase con la pagina `tela` può dichiarare `"orientamento": "orizzontale"` (o `"verticale"`);
  `macchina.normalizza` lo rifiuta su un'altra pagina (le pagine di Calliope stanno nei due
  orientamenti) e con un altro valore. Il palco di quella tela è **sempre** quello dichiarato
  (1280×720 scalato su un telefono in piedi resta giocabile, solo piccolo: niente blocco).
- Sul telefono (o un tablet) girato dall'altra parte una **fascia** in alto, sopra il gioco e
  senza prendere i tocchi (`.gira-telefono`, `pointer-events: none`), dice «Gira il telefono in
  orizzontale»; girato, sparisce (il motore ridisegna al cambio d'orientamento). Su un PC o una TV
  la finestra non si gira: niente fascia. Il «telefono» lo dice la pagina degli schermi
  all'avvio (`avvio.tocco`, `pointer: coarse` della pagina) o il riquadro stesso: il riquadro gira
  in un processo suo e in Edge non vede l'emulazione del tocco della pagina (trovato dalla prova).
- **Calliope lo dice a voce una volta**: il motore manda `gira` (canale riservato, una volta per
  riquadro), la pagina lo passa (`TIPI_DAL_RIQUADRO`), il server (`_t_gira`) mette una frase sua
  («Per questo gioco gira il telefono in orizzontale.») tra le frasi dei giochi una volta per
  schermo e partita (`Posto.gira_detto`, anche dopo «Riapri»), regola `gioco_gira_telefono`. Vale
  anche in una partita di prova (`TIPI_PROVA`): è una frase di Calliope, non un ponte.
- La prova di fumo e `g.palco()` misurano una tela orientata solo nel suo orientamento.

**Profilo da 8 GB**: niente (browser, confronti e frasi dal codice). **Latenza**: il controllo di
chi muove è sull'istantanea già in memoria; la voce di chi parla si aspetta (l'impronta corre già
con Whisper) anche nei giochi per più giocatori senza `giocatore`, come per «a chi tocca?».

**Per l'agente**: due righe in più nel §5 del contratto (`GIOCO.entra`, `orientamento` di una
tela), da 6 964 a 7 378 caratteri (~120 token con il rapporto 3,47 di Qwen3.6); niente da
scrivere per i legami.

**Prove**: `prova_gioco_giocatori` (a secco, ~2 s: i quattro casi nel motore, il server, le
domande, il ciclo, «Gira il telefono»), `prova_gioco_stato_pagina` (Edge: «Gioco anch'io» toccato
sulle due pagine di una partita condivisa e il tocco sulla pagina dell'altro che non muove; un
telefono finto 390×844 con una tela orizzontale, la fascia nel riquadro vero e la frase detta una
volta), le attese aggiornate di `prova_gioco_stato`, `prova_giochi_pagina` e `prova_testo`.

**Da fare sulla DGX** (dopo `calliope aggiorna`, ricaricando le pagine): una partita condivisa da
due schermi con «gioco anch'io» toccato su ognuno, poi provare a muovere dallo schermo sbagliato;
su uno schermo con due persone «gioco anch'io» detto da tutte e due e «porta tre» detto da chi
non è di turno (Calliope: «Tocca a …»); «che giocatore sono?»; quanto spesso la voce di una mossa
è riconosciuta (se quasi mai, su uno schermo solo decide sempre il turno): `calliope stato
--turni`, esito `gioco_turno_altrui`. Un gioco con una tela orizzontale sul telefono in piedi.

## La preparazione detta all'agente e `apriGioco({ inizia: true })` (18/10, issue #174)

Il tris per due della DGX (18/10): l'agente ha girato a vuoto cinque giri perché i suoi test di
`gioco.test.js` facevano la prima mossa senza uscire dalla fase «preparazione» (con giocatori
min = max se ne esce solo con «Inizia»). Ora il contratto lo dice (ogni partita comincia nella
preparazione: «Inizia» con min = max, «N giocatori» con min < max), `apriGioco({ inizia: true })`
parte dalla fase d'inizio del gioco, e l'errore di un comando o di un tocco nella preparazione
dice la via d'uscita («prima delle mosse tocca «Inizia»… correggi il test, non il manifesto»).
Il banco della temperatura ha il caso fisso `tris2`. Il resto (firme degli errori, novità, giri
uguali, specifica) in [agenti-estensioni](agenti-estensioni.md), voce del 18/10 su #174.

## Il contratto del gioco e la partenza già verde (19/10, issue #186, ramo `issue-186-contratto-giochi`)

**Il caso** (analisi del 19/10, `docs/ricerche/2026-10-19-solidita-harness-sviluppo.md` § 3.5,
n. 28–32): i casi peggiori del catalogo (Halloween dell'11/10, le porte del 12–14/10, il tris per
due del 18/10, #174) sono giochi. Un gioco partiva da una cartella vuota e l'agente ricopiava dal
prompt manifesto, logica e test, proprio la parte rotta in #174; il prompt prometteva cose che il
motore non fa; il 45 % del testo di un gioco riguardava le estensioni Python.

**Cosa cambia.**
1. **La partenza già verde** (`agenti/scheletri.file_gioco`, `prepara_gioco`; nel servizio
   `Lavori._prepara_cartella_gioco`, dopo l'analisi prima del codice): un gioco nuovo trova nella
   cartella `manifesto.json`, `logica.js`, `logica.test.js` e `gioco.test.js`, scritti dal codice
   con giocatori min e max della richiesta. È il gioco delle porte dello scheletro di prima (una
   fase «turno», «porta {n}», le porte due in più dei giocatori, un punto a porta, la fine quando
   sono aperte tutte); `gioco.test.js` comincia dalla preparazione con «Inizia» (min = max) o «N
   giocatori» (min < max, il primo N da 2), controlla l'esito, il turno, i punti, i comandi come
   oggetto, il palco e la fine. Passa i test e la prova di fumo per fasi per costruzione
   (`prova_partenza_gioco` per 1–1, 2–2, 1–4, 2–4, 3–8). Min e max li dice l'analisi prima del
   codice (`accettazione.py`, campo nuovo `giocatori` dello schema del gioco: «per due» → 2 e 2;
   un esempio fuori da quel numero si toglie); senza l'analisi (spenta, o un gioco fuori da uno
   sviluppo) restano 1–4, quelli dello scheletro di prima. Il nome e il titolo
   vengono dal titolo del lavoro, se fanno un manifesto valido; altrimenti il segnaposto
   `gioco_nuovo`, che la consegna rifiuta («dai al gioco un nome suo»). Una modifica, una
   correzione o una ripresa hanno già un manifesto e non ricevono niente. Nel prompt al posto dei
   quattro file c'è un paragrafo che dice cosa c'è nella cartella (prima 3 347 caratteri, ora
   831).
2. **`g.stato()` esatto**: `{ n, fase, tocca, turno, giocatori: [{ nome, punti }], esito,
   comandi }`, con `comandi` un oggetto (`g.stato().comandi.porta`), non una lista. Il prompt non
   promette più il «vincitore» (prima «punti, esito e vincitore»), che l'istantanea non ha: chi
   vince si legge dai punti. Non l'ho aggiunto: con i pareggi e le partite senza punti
   «vincitore» va deciso dal gioco, e i punti dicono già tutto. *[storico: «perché la valida
   anche il server, sarebbe un cambio del protocollo» fino al 20/10, non esatto: g.stato() è
   `istantanea()` del motore, solo per i test; il server valida `perCalliope()`
   (`macchina.CHIAVI_ISTANTANEA`), e aggiungerlo a `istantanea()` non cambierebbe il
   protocollo (revisione della PR #188)]*
3. **Gli errori nuovi del motore** (`motore_gioco.js`, `controlla`): `{ esito, fase: "fine" }`
   perdeva l'esito senza dirlo (il motore andava subito alla fase), e `{ dopo }` senza esito era
   ignorato. Ora sono errori con fase e comando e con cosa fare («Per mostrare il testo e poi
   andare a «fine»: { esito: "…", dopo: "fine" }; per andarci subito senza testo: { fase: "fine"
   }»). Un esito vuoto conta come nessun esito. Restano validi `{ esito, dopo }`, `{ fase }`,
   `{ esito, fase: "esito" }` e `{ dati }`. La prova di fumo non consiglia più «fase o dopo:
   "fine"» ma «esito con dopo: "fine", oppure fase: "fine" senza esito», prima della strada (il
   messaggio si taglia a 200 caratteri e il consiglio in fondo si perdeva). Le prove dei giochi
   esistenti e i giochi delle prove (`prove/giochi/*`) non usavano le due forme: verdi senza
   cambiare niente. **I giochi già installati** che le usano si rompono alla mossa, nel
   riquadro vero e non solo nei test (l'errore del motore ferma la partita): niente migrazioni
   (Calliope non è in produzione), ma prima di aggiornare la DGX vanno cercati nei `logica.js`
   installati (`esito` non vuoto insieme a `fase` diversa da «esito»; `dopo` senza `esito`, con
   `fase` diversa da «esito»; anche `esito: ""` vale come senza esito) e rifatti con una
   correzione. Come cercarli: un grep da solo non basta (l'oggetto può essere costruito su più
   righe o con variabili). Il modo sicuro è far girare la prova di fumo (`agenti/fumo_js.mjs`,
   quella di esegui_test) su ogni gioco installato prima di `calliope aggiorna`, sapendo che
   trova solo le strade che percorre; per partire, un grep come `rg -n
   "esito\s*:.*fase\s*:|fase\s*:.*esito\s*:|dopo\s*:"` sui `logica.js` delle estensioni
   installate (la cartella è da verificare sulla DGX), poi i casi letti a mano.
4. **Il contratto esatto** (`contratto.scheda_testo`, ora il §2 del contratto del gioco): «Inizia»
   c'è sempre, anche con min < max, e parte con min giocatori (o con quanti hanno detto «gioco
   anch'io»); `turni` è vero di serie (false: muove chiunque); il caso: Math.random va bene, in
   apriGioco e nella prova di fumo ha un seme fisso, in `logica.test.js` un risultato che dipende
   dal caso si prova con i dati fatti a mano. Le tre forme di una mossa in una riga sola. Per il
   caso ho scelto il seme detto, non un `caso` passato a `nuovaPartita`: il motore lo fa già
   (`creaCaso` su Math.random nel contesto), e un parametro nuovo sarebbe stato un'altra cosa da
   copiare.
5. **Un prompt per tipo** (in [agenti-estensioni](agenti-estensioni.md), voce del 19/10 su #186):
   il gioco ha il suo prompt (`SISTEMA_GIOCO`) e il suo contratto, senza Python, porta stretta,
   codifica degli indirizzi; per un gioco niente `esegui_python` né `scarica_esempio` tra gli
   strumenti. Il prompt di un gioco è passato da 26 437 a 16 330 caratteri.

**Il banco della temperatura**: il caso `tris2` ora parte dai file di partenza (2–2, «Inizia»):
il banco, che non apre uno sviluppo, mette nel lavoro i giocatori del caso come li direbbe
l'analisi (`lav.accettazione = {"stato": "saltata", "giocatori": …}`), e il controllo a secco
verifica che la partenza sia verde e che l'accettazione nascosta su di lei sia rossa. Il criterio
di #174 (il tris in al più 2 giri, `--casi tris2,porte --giri 2`) va misurato sulla DGX dopo
l'unione.

**Dopo la revisione della PR #188 (20/10).**
- La consegna rifiuta un `logica.js` uguale a quello della partenza («è un esempio da sostituire
  con il gioco chiesto»). Prima, con un nome dal titolo del lavoro, le porte d'esempio si
  consegnavano così com'erano: in uno sviluppo le fermano gli esempi di accettazione e la
  revisione, fuori da uno sviluppo (`estensione_gestisci`) niente. Il manifesto con la sola
  fase d'esempio non si controlla a parte: le regole nuove passano da `logica.js`, e una
  modifica (nome atteso) non è toccata dal controllo.
- Le correzioni dei giochi non hanno più `g.tocca("2 giocatori")` fisso (con min = max non
  c'è: la trappola del tris per due) né «il vincitore»: `VINCOLO_CORREZIONE_GIOCO`
  (`tools/sviluppo.py`) e il rimando della riproduzione (`agenti/riproduzione.py`) dicono
  `apriGioco({ seme: 1, inizia: true })` (con min < max anche `giocatori: N`) e rimandano al §2
  del contratto.
- Nome e titolo della partenza sono tagliati all'ultima parola intera, tengono le cifre e
  l'apostrofo, e niente × né ÷ («Tic-tac-toe 3x3» → `tic_tac_toe_3x3`, «Tic tac toe 3x3»).
- Gli esempi d'accettazione tolti perché fuori da min e max si contano in `tolti` e nel
  registro. Se sarebbero tolti tutti, si tengono gli esempi e non si tiene min e max (la
  partenza va con 1–4).
- Il contratto del gioco non ha più le voci scritte per Python negli impossibili (pip, la
  libreria standard, la porta stretta, «dentro l'estensione», le pagine fatte in JavaScript).
- Il piano di un gioco non dice più «scarica_esempio… estensione.py» come prossimo passo:
  dice di leggere e cambiare i file di partenza.

**Dopo la seconda revisione della PR #188 (20/10).** Nel piano di un gioco la voce «javascript»
(il gioco è JavaScript) chiudeva il lavoro come impossibile, con la frase delle estensioni
(«un'estensione non può leggere dati che una pagina mostra solo con JavaScript»). Ora per un gioco le voci senza senso
(`_IMPOSSIBILI_GIOCO` a None) non sono tra le voci del piano e, se arrivano, si ignorano; gli
impossibili e le frasi vengono dal contratto del gioco («un gioco non può installare librerie o
programmi»), con `contratto.impossibili(gioco)` e `voci_piano(gioco)` usati dal contratto e dallo
strumento piano. Il titolo della partenza non finisce più con una preposizione o un articolo
(«…con le carte», non «…con le carte di»).

**apriGioco nelle correzioni e la pagina già «griglia» (20/10, issue #192, ramo
`issue-192-apri-gioco-tappa`).** Nel banco del 20/10 a due giri (porte L4 e L6) l'agente di una
correzione scriveva in gioco.test.js un `apriGioco` suo, un motore finto che copre quello vero, e
passava i giri a correggerlo con logica.js già giusto: dopo #186 la frase «ci sono già» stava solo
nel gioco.test.js di partenza, che una correzione non riceve. Ora la dicono il contratto del gioco,
i vincoli della correzione e il rimando della riproduzione, ed esegui_test ha il fatto del motore
finto (regola `agente_motore_finto`). Il suggerimento del palco con troppi pulsanti in una pagina
già «griglia» dice di mettere comando e valore nelle caselle (tris2 L3), non «usa la pagina
«griglia»». Il resto (la tappa consegnabile, il segnaposto, il banco) è in
[agenti-estensioni](agenti-estensioni.md), voce del 20/10 su #192.

## Il copione delle prove dal vero e i giochi nella prova end-to-end (20/10, #7 e #75)

Le prove dal vero di tutte le capacità dei giochi (macchina a stati, i sette modelli di pagina e i
due formati, tela e «Gira il telefono», comandi a voce, giudice, domande, «gioco anch'io», nomi
scritti, chi è quale giocatore, «Riapri», partite condivise, collaudo a tutta la finestra,
partenza già verde) sono le serie D ed E di
[`prove/manuali/copione-estensioni-giochi.md`](../../prove/manuali/copione-estensioni-giochi.md),
con la tabella di copertura. Nella prova end-to-end l'area `giochi` crea dieci giochi con l'agente
vero (porte 2–4, tris 2–2, memory, quiz, sette e mezzo, oca in quattro, lucciole su tela, la spesa
con un'azione, forza quattro condiviso, il quiz che vuole internet) e controlla dal log la partenza
con i giocatori dell'analisi; le **partite** (`partita-porte`) chiedono la pagina vera dello schermo
in Edge, che la prova non ha ancora: si saltano finché non c'è (il punto aperto di #75).

## La macchina a stati serve ancora? Analisi delle opzioni (20/10, issue #198, parte 1)

Il 20/10 sera, con tutto l'harness del 19–20/10 installato, la correzione delle porte fa 8/8 e il
tris per due da zero fa 0/3. Chi amministra ritiene Qwen3.6-35B-A3B adatto a un tris e chiede di
cercare il problema nell'harness o nelle specifiche. La macchina (13/10) è nata prima di
quell'harness. L'analisi in sola lettura è in
[`2026-10-20-giochi-macchina-o-interfaccia.md`](../ricerche/2026-10-20-giochi-macchina-o-interfaccia.md).
In breve:
- **le garanzie di Calliope non dipendono dalle fasi dichiarate dal gioco**: comandi a voce,
  giudice, domande, istantanea validata, partite condivise, ripresa, chi è quale giocatore e palco
  usano un elenco chiuso di comandi nel manifesto, un'istantanea numerata, uno stato
  serializzabile con una vista pura, e preparazione, fine e disegno di Calliope;
- **il costo per l'agente**:
  - circa 3 300–3 500 caratteri su 9 141 del §2 del contratto (36–38 %) parlano soltanto della
    macchina;
  - `tocca` è un nome in `g.stato()` e una posizione nel contesto della mossa;
  - `turno` nel contesto è il numero del giro, e il contratto non lo dice;
  - senza turni, se non si sa chi ha mosso, i punti vanno al Giocatore 1;
  - contratto, prompt dell'analisi («dopo ogni mossa di solito c'è la fase «esito»») e gioco
    della partenza suggeriscono l'esito a ogni mossa;
- **il catalogo dal 14/10**: 14 lavori di gioco falliti, e un'interfaccia senza fasi ne
  toglierebbe 5–6: 4 certi e 1 probabile con un concetto della macchina come causa principale,
  più il «dopo» di un lavoro della transizione, contato fra i 3 qui sotto. Gli altri:
  - 3 vengono dalla transizione dai giochi di prima;
  - 2 dalla regressione dell'harness chiusa da #192;
  - 3 dalla logica e dalla forma della vista, che resta;
  - 1 non ha la causa scritta.

  La correzione di un gioco che c'è già fa 14/16 dal 19/10, e 8/8 dopo #192;
- **le opzioni**: A, la macchina con il contratto semplificato; A′, la macchina con l'agente che
  scrive solo i test della logica; B, una macchina più piccola; C, quattro funzioni pure su uno
  stato del gioco con `tocca`, `punti` e `fine`, anche come **facciata** sopra il motore di oggi
  (2–3 giorni di prototipo). C perde la validazione dei comandi per fase, pagina e turni per fase,
  e turni e punti coerenti per costruzione; D, JavaScript libero;
- **la raccomandazione**: prima #197; poi il banco della parte 2 con `tris2`, `tris2-solo-logica`
  e `tris-nudo`, a 10 ripetizioni per caso;
  - le soglie si scrivono prima: alto ≥ 8/10, basso ≤ 3/10, applicate in ordine, con il caso
    intermedio. Il rilancio si somma ai primi 10;
  - 8/10 contro 3/10 è una soglia di decisione, non una prova (p = 0,070 a due code);
  - il prototipo di C si fa solo con un margine più forte: 9/10 contro ≤ 3/10, oppure 8/10
    contro ≤ 2/10.

  La scelta la fa il banco, non un parere.

## L'esito solo quando una mano finisce, e gli esempi del tris (20/10, issue #197, ramo `issue-197-esito-giochi`)

**Il caso** (banco sulla DGX del 20/10 sera, `~/banchi/giri2-1020-1753`, versione
`20261020-1750-0437d490` con #192, `--casi tris2 --giri 2 --ripetizioni 3`): **tris2 0/3**, le
porte 3/3. In L3 i test dell'agente si aspettavano un esito a ogni mossa («FALLITO mossa valida:
casella vuota riceve X: + 'Mossa effettuata' - null») e la logica dava `esito: "Mossa effettuata"`
a ogni casella, che per il motore vuol dire «la mano è finita»; l'analisi prima del codice aveva
dato 0 esempi (`esempi: 0`, `tolti: {}`, stato «pronta»). In L1 e L5 l'accettazione degli esempi
restava rossa (requisiti 3, 4, 5).

**Gli esempi di L1 e L5 erano sbagliati, non il codice.** Giocati sul tris di riferimento
(`prove/giochi/tris` con giocatori 2–2, `banco_temperatura.riferimento_tris2`) cadevano **tutti,
11 su 11**: «fase esito» dopo una mossa normale (5 esempi); parole sullo schermo scelte dal modello
(«ok» tre volte, «Vittoria», «Nuova») dove il tris giusto scrive «Ha vinto X!»; il pareggio
«1, 2, 3, …, 9» (quattro esempi), che fa vincere il primo alla 7ª mossa (3, 5, 7), così l'8ª non
vale più; «1, 2, 3, 4, 5, 6 → fine con un punto», dove il primo ha 1, 3 e 5 (le mosse non sono a
turno nella testa del modello). La causa principale era il prompt del progettista dei test
(`accettazione.SISTEMA_GIOCO`): «dopo ogni mossa di solito c'è la fase «esito»». La stessa idea
era nel contratto («turni, punti, **esito di ogni mossa**») e in `CAPACITA_GIOCO`: il modello
dell'agente e quello degli esempi la prendevano alla lettera, e gli esempi la imponevano al codice.

**Cosa cambia.**
1. **I testi**: il contratto del gioco dice «il testo dell'esito quando una mano finisce» e, nella
   forma delle mosse, «L'ESITO C'È SOLO QUANDO UNA MANO FINISCE (una vittoria, un pareggio, un
   punto fatto): una mossa normale (una casella segnata, una carta girata) restituisce { dati } (e
   i punti, se ci sono) e resta nella fase, senza esito». Lo stesso in `CAPACITA_GIOCO`
   (requisiti.py), nel prompt del progettista dei test (in più: le mosse sono a turno, «nel tris
   1, 4, 2, 5, 3 il primo vince alla 5ª; 1, 2, 3 non fa vincere nessuno», fermarsi alla mossa che
   finisce, al più 7 mosse, il testo solo con parole della richiesta, «esito» solo con i punti *[storico: dalla revisione della PR #201 «esito» quando la mano finisce, anche il pareggio, mai dopo la prima mossa]*),
   in `VINCOLO_CORREZIONE_GIOCO` («l'esito di una mano finita») e nel commento della logica di
   partenza (lì ogni porta aperta è un punto fatto: per questo c'è l'esito).
2. **L'avviso della prova di fumo** (`fumo_js.avvisoEsito`, nelle partite a caso di `esplora`):
   si contano le mosse del gioco e quelle con un esito che non chiude niente (senza punti e senza
   `dopo: "fine"`). Scatta quando ce l'ha più della metà delle mosse o la prima mossa di **ogni**
   partita; test_js.mjs scrive «AVVISO prova di fumo del gioco: N mosse su M hanno un esito senza
   punti né fine, anche la prima di ogni partita (GIOCO.mosse.turno.casella → esito «Mossa
   effettuata»): l'esito vuol dire che la mano è finita (una vittoria, un pareggio, un punto
   fatto): per una mossa normale restituisci { dati } (e i punti, se ci sono) e resta nella fase.
   Se ogni mossa chiude davvero una mano (una domanda di un quiz), lascialo così». È un avviso, non
   un fallimento (un quiz ha davvero un esito a ogni risposta). Nel ciclo dell'agente la riga
   accende la regola `gioco_esito_ogni_mossa`, una volta per lavoro. Niente avviso sul tris giusto,
   sulle porte delle prove (`prove/giochi/porte_fasi`: la ragnatela dà un esito a zero punti una
   volta su quattro) e sulla partenza delle porte (un punto a ogni porta). Il punto di distinzione
   è il punto: con i soli esiti contati («più della metà con un esito») la partenza, che dà un
   esito a ogni porta, avrebbe avuto l'avviso.
3. **Gli esempi filtrati** (`accettazione._esempi_gioco`, con la richiesta): il testo atteso si
   tiene solo se le sue parole sono nella richiesta, di seguito, al singolare o al plurale *[storico: dalla revisione della PR #201 in una forma vicina, sotto]* (i
   numeri giocati nelle mosse non contano: «porta 2» dopo la porta 2); la fase «esito» attesa
   senza i punti si toglie (non dice cosa è finito) *[storico: dalla revisione della PR #201 solo dopo una mossa sola]*; un esempio con più di 7 mosse del gioco si
   toglie (`MAX_MOSSE_SICURE`: sul banco erano sbagliati tutti quelli con 9 mosse); due esempi che
   si contraddicono (uno finisce la partita, l'altro con le stesse mosse in testa continua) si
   tolgono tutti e due. Senza la richiesta (le prove di prima) il testo resta.
4. **Il contesto della mossa nel contratto** (analisi della macchina a stati, PR #200): il
   `TypeError: Cannot read properties of undefined (reading 'punti') [in logica.js:62]` di tris2
   L5 non veniva da `turno`: i test dell'agente chiamavano `nuovaPartita({ giocatori: ["G1",
   "G2"] })`, un elenco, dove il motore passa il numero (`{ giocatori: 2, nomi }`), e la logica
   (`for (i < dati.giocatori)`) restava senza giocatori; la stessa logica teneva poi un suo indice
   del turno (`d.turno`, sempre 0: metteva sempre X) invece di usare la posizione che il motore
   le dà. Lo stesso nome con due tipi (`giocatori` numero in `nuovaPartita`, elenco nel contesto)
   e `tocca` posizione nel contesto ma nome in `g.stato()` non erano spiegati. Ora il contratto
   dice: in `nuovaPartita` giocatori è il NUMERO; nel contesto della mossa `{ valore, tocca, chi,
   giocatori, turno }` tocca è la POSIZIONE di chi muove («nel tris il segno è ["X",
   "O"][tocca]»), giocatori l'ELENCO `[{ nome, punti }]`, turno il GIRO (1, 1, 2, 2… con due
   giocatori, non chi muove); in `g.stato()` tocca è il NOME; chi muove lo tiene Calliope, non
   anche i dati. La prova controlla anche il motore vero (tocca 0, 1, 0, 1 e turno 1, 1, 2, 2).
5. **I punti senza turni** (revisione dell'analisi della PR #200): in una fase con `"turni":
   false`, con più giocatori e senza sapere chi ha mosso (la voce non riconosciuta, lo stesso
   schermo per tutti, la tela), il motore dava `chi` e un numero di punti al giocatore di
   `tocca`, che senza turni resta il primo: **i punti di chiunque andavano al Giocatore 1**. Era
   un difetto, non una scelta: il contratto diceva «i punti vanno a chi ha mosso, se si sa». Ora
   lì un numero di punti non va a nessuno e `chi` è null (l'elenco dei punti, uno per giocatore,
   vale come prima); il contratto lo dice *[storico: «lì i punti si danno con l'elenco» fino alla revisione della PR #201: senza sapere chi ha mosso non si può; ora «usa i turni» e l'avviso, sotto]*. Contrari nella prova: con la voce riconosciuta i punti
   vanno a chi ha mosso, con un giocatore solo sono suoi, con i turni vanno a chi è di turno.

**I numeri** *[storico: del primo giro della PR; quelli dopo la revisione sono sotto]*. Gli esempi di L1 (6) e L5 (5) col codice nuovo: 1 e 3 tenuti; L5 tutto verde sul
tris giusto, di L1 resta «1, …, 6 → fine con un punto», sbagliato e che nessuna regola sul testo
vede senza giocare la partita. Otto analisi nuove sulla DGX col prompt nuovo (qwen3.6 su vLLM,
temperatura 0, in sola lettura): 26 esempi, col filtro di prima 24 tenuti e 5 verdi sul
riferimento; col filtro nuovo 10 tenuti e 2 verdi. Gli 8 rossi che restano: mosse non a turno
(«1, 5, 9» o «1, 2, 3» come se muovesse uno solo), una casella già presa che «deve valere ancora»,
un testo della richiesta nel momento sbagliato («ancora» a partita aperta) e due volte la fase
del gioco chiamata «gioco» (contro il riferimento è un errore; in uno sviluppo l'agente riceve
quel nome nei vincoli, quindi non lo è). **Il progettista dei test non sa giocare a tris**: i
filtri tolgono la maggior parte degli esempi sbagliati, e con loro quasi tutti; un esempio che
resta può ancora far fallire il codice giusto, e il tetto non chiude d'ufficio con un esempio
rosso. Da decidere: giocare gli esempi su un riferimento non c'è in generale (un gioco nuovo non
ne ha); restano un modello più capace per l'analisi (#175) o esempi che non bloccano la chiusura.

**I 0 esempi di L3.** Il JSON grezzo del modello non è salvato, quindi la causa non si legge più;
in 20 analisi rifatte sulla DGX col prompt di allora (stessa richiesta, stessi requisiti,
temperatura 0, in sola lettura) il modello ne ha scritti sempre 4 o 5 e il codice ne ha tolti al
più 1 (un doppione). Il difetto vero era che `_esempi_gioco` toglieva in silenzio (atteso o
giocatori che non si leggono, comandi o valori che non ci sono, niente da controllare, doppioni)
e `tolti` restava `{}`: «0 esempi» non diceva se li aveva tolti il codice o se il modello non ne
aveva scritti. Ora ogni causa è contata in `tolti` (`forma`, `mosse`, `lunghi`, `niente`,
`doppioni`, `testo`, `esito_prima_mossa`, `dopo_la_fine`; *[storico: `esito_senza_punti` fino alla revisione della PR #201]*), il lavoro ha `esempi_modello` (anche
nella riga del banco), il log dice le cause, e con esempi scritti dal modello e tutti tolti c'è la
regola `accettazione_esempi_tutti_tolti` con il conto e le cause. Nel banco
`SviluppoBanco.segna_accettazione` non fa niente: prima il log diceva «requisiti al collaudo non
segnati: 'SviluppoBanco' object has no attribute …» (L3, L5).

**Dopo la revisione della PR #201 (20/10).**
1. **`turno` con un giocatore solo resta 1** (il turno passa solo con più giocatori): il
   contratto lo dice, «per contare le mosse tienile nei dati», così un solitario non conta i giri
   con `turno` e non resta senza fine.
2. **Punti senza turni**: il consiglio «lì i punti si danno con l'elenco» non si poteva seguire
   (senza sapere chi ha mosso la logica non sa a chi darli). Il contratto dice «se i punti vanno a
   chi muove, usa una fase con i turni»; il motore conta i punti che non vanno a nessuno
   (`puntiPersi`, solo per la prova: nel riquadro non cambia niente) e la prova di fumo lo avvisa
   («… dà un numero di punti in una fase senza turni: … quei punti non vanno a nessuno. Se i punti
   vanno a chi muove, usa una fase con i turni»), così il test dell'agente non vede 0 punti senza
   capire. Contrari: i turni, l'elenco, un giocatore solo.
3. **Il pareggio è un esito senza punti**: il prompt del progettista dice «esito» quando la mano
   finisce (una vittoria, un pareggio, un punto fatto), mai dopo la prima mossa del gioco; il
   filtro toglie il controllo della fase «esito» senza punti solo dopo una mossa sola
   (`esito_prima_mossa` nei tolti, la stessa idea dell'avviso della prova di fumo). «1, 4, 2, 5, 3
   → esito» del tris giusto resta.
4. Il residuo «l'«esito» delle mosse» nel messaggio del disegno della prova di fumo è diventato
   «l'«esito» di una mano finita».
5. L'avviso dell'esito dice anche dove va il messaggio di una mossa normale («troppo alto»,
   «casella già presa»: nei testi di GIOCO.vista). Il testo atteso si confronta in una forma
   vicina (`accettazione.simili`: uguali, oppure almeno 4 lettere con l'inizio in comune per
   max(3, la più corta − 2) lettere), sia nel filtro con la richiesta sia sullo schermo in
   accettazione.test.js: «vinto» non si toglie più e «vince» atteso passa con «Ha vinto X!»;
   «Vittoria» resta fuori. Contrari: «pareggio» atteso dopo una vittoria resta rosso; un esempio
   di 7 mosse resta, di 8 si toglie.

**I numeri dopo la revisione** (gli stessi esempi, sul tris di riferimento): L1 da 6 a 3 tenuti,
rossi i requisiti 2 e 3 («1, 2 → esito» e «1, 2, 3 → esito» con le mosse non a turno, e «1…6
finisce»); L5 da 5 a 3, rosso solo «5, 1 → esito». Le otto analisi nuove: 26 esempi, 15 tenuti,
5 verdi (col filtro del primo giro 10 e 2). Il filtro più largo tiene più esempi giusti e più
sbagliati: lo scambio è voluto, perché un esempio giusto tolto non torna, e gli esempi non
bloccano più la chiusura (#190).

**Dopo la seconda revisione della PR #201 (20/10).** Sullo schermo le parole attese si
confrontano di seguito, in una finestra di parole consecutive del testo visibile, ognuna in una
forma vicina: con le parole sciolte la «X» di una casella faceva passare «Mette X» dove il tris
giusto scrive «Mette O», e un esempio verde falso alla tappa chiude il lavoro. Contrari sul tris
giusto: `[1] → «Mette O»` verde e «Mette X» rosso, il contrario con `[1, 4]`; «vince» con «Ha vinto
X!» resta verde. Il filtro in Python resta con le parole sciolte (tiene un controllo, non lo dà
per buono). L'avviso dei punti persi ha la sua regola, `gioco_punti_persi`: il ciclo riconosce
ogni avviso dal prefisso e da una frase sua (`ciclo.regole_avvisi`), mentre prima dal solo
prefisso contava come `gioco_esito_ogni_mossa`. `puntiPersi` tiene solo il primo.

**Le prove**: `prove/prova_esito_giochi.py` (nuova, livello 2, ~10 s).
