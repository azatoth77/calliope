# Schermi e telefono

*Schede sugli schermi, abbinamento, visibilità, scrivere invece di parlare, telefono come satellite (PWA), rispondi dove ti ho chiesto. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 27/10.** Il telefono è **a sezioni** (passo 1 del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md), sezione in fondo): Adesso, Conversazione, Le mie cose, Casa e Io con la barra in basso, la voce sopra la barra, ogni scheda nella sua sezione e quelle vive anche in Adesso; il menu è diventato Io, la vista da guida del 04/10 la modalità «In auto», a mano. Dal 27/10 (passo 1c) l'accento è **lilla di serie** su tutto, con l'accento personale in Io › Aspetto, e sul telefono di un minore Casa è nascosta sotto i 13 anni. Dal 27/10 sera (passo 1b) anche lo **schermo personale del PC** è a sezioni, in colonne, con «Parla»; gli schermi di stanza restano com'erano. Restano i passi 2–10 del progetto (Le mie cose con le pagine per tipo, Conversazione con le schede dentro, Studio). *Stato al 18/10 (storico):* come al 14/10 (sotto), più: chi è quale giocatore e «Gira il telefono» sugli schermi (15/10, [giochi](giochi.md)); la foto mandata dallo schermo che aspetta la domanda anche se in mezzo parla un'altra voce (16/10, #96, [immagini-allegati](immagini-allegati.md)); l'inoltro del satellite tolto (16/10, #61): fuori casa il telefono raggiunge la DGX con la sua VPN ([satelliti](satelliti.md), [`prove/manuali/telefono.md`](../../prove/manuali/telefono.md)). Le prove manuali stanno in `prove/manuali/` dal 06/10. *Stato al 14/10 (storico):* come al 09/10 (sotto), più: la **modalità gioco** a tutta la finestra con il pallino della voce e la variante «collaudo» (11/10), il palco fisso dei giochi (14/10, [giochi](giochi.md)); la **stanza** sugli schermi (13/10): il segno «Ascolto la stanza» o la pausa, l'interruttore «Ascolto la stanza» del telefono (acceso di serie), la sezione «Stanza (in ombra)» del cruscotto con soli numeri; dal 14/10 la scheda «avviso» del tutore con «Leggi cosa si è detto» e «Scarica l'audio», solo sul suo schermo personale ([minori](minori.md)). Restano da provare sul vero l'iPhone e lo scaricamento dalla PWA.

*Stato al 09/10 (storico): schermi e telefono come dal 06/10 (scheda a schermo intero, cruscotto in sola lettura), più il lettore Markdown e «Scarica» (07/10), la scheda degli esercizi e del cassetto, la vista dello sviluppo con il flusso dell'agente e la cronologia delle schede per persona con la scheda «Conversazione» (08/10), il segno della compagnia (09/10). Restano da provare sul vero l'iPhone (audio, schermo acceso, auto) e lo scaricamento dalla PWA.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Schermi (schede su PC, tablet, TV) | Starlette + uvicorn senza extra (puro Python) in un thread, SSE verso una pagina kiosk locale; abbinamento a codice in SQLite (stesso file della memoria) | `calliope/schermi/` → `Schermi` (`hub.py`: destinatari, visibilità, consegna), `ArchivioSchermi` (`archivio.py`), `schede.py`, `ServerSchermi` (`server.py`), `pagina/`, `load_schermi`; HTTPS in rete `tls.py`, ponte TLS del satellite `ponte.py`; scheda del cassetto (POST `/api/cassetto`, area [immagini-allegati](immagini-allegati.md)), dall'08/10 (*storico: fino al 28/10 anche le schede degli esercizi, POST «/api/esercizio», tolte con la #279*); segno della compagnia `Schermi.voce(compagnia=…)` (09/10); segno della stanza `Schermi.stanza_segno`, `stanza_per` (13/10); porte occupate dopo un riavvio `calliope/porte.py` → `socket_in_ascolto` (02/10); tool in `calliope/tools/schermi.py`; terminale `python -m calliope.schermi` |
| Telefono (satellite nel browser, PWA, dal 03/10) | stessa porta degli schermi: WebSocket di uvicorn con `websockets` sans-I/O e lo stesso protocollo dei satelliti; nel browser onnxruntime-web 1.30 in WebAssembly (Silero VAD e wake word), AudioWorklet, Web Audio, Screen Wake Lock API; CA di casa con `openssl` | `calliope/schermi/telefono.py` → `rotte`, `PonteWs`, `stato`; «Prova il microfono» `telefono_diagnostica.py`; `calliope/schermi/pagina/telefono/` (`telefono.js`, `voce.js`, `microfono.js`, `schermo-acceso.js` (`SchermoAcceso`, `diagnosi`: schermo acceso, dal 04/10), `sw.js`, manifest; dal 27/10 cinque sezioni con la barra (`sincronizza` smista per sezione, `disponi`, `vaiA`, router `vai`/`applicaPercorso`, `impostaAuto`; *storico: dal 04/10 una vista sola col carosello*), strati modulo/scrivi (il menu è la sezione Io dal 27/10) e, dal 06/10, la scheda a schermo intero (`apriIntera`, `disegnaIntera`, `chiudiIntera`); schede da `schermo.js` con `data-carosello` ed eventi `calliope:*`); `ServerSatelliti.prendi` / `lascia` / `per_pc`; `tls.certificato_telefono`; terminale `python -m calliope.schermi --certificato` |
| Scrivere invece di parlare (moduli e casella sugli schermi personali, dal 03/10) | POST `/api/scrivi` e `/api/modulo` del server degli schermi (sessione in un'intestazione, JSON, solo HTTPS in rete); controlli dei codici in Python e in JS (`schermo.js`, condiviso col telefono); dal 05/10 solo durante una conversazione a voce; dal 28/10 (#301) dallo schermo personale casella, foto e file sempre, i moduli ancora in conversazione | `calliope/schermi/moduli.py` → `Moduli`, `Ingresso`, `controlla_campo`, `offri`, `completa`, `oscura`; `Ufficio.completa_modulo` / `rubrica_da_modulo`; `tools/spec.serve_la_voce`; ciclo in `main.py` (`scritto`); `calliope/schermi/conversazione.py` → `scrittura_consentita`, `Conversazioni`; `Schermi.scrittura_consentita` (il punto unico, anche per le foto) |
| Cruscotto di chi amministra (fase 1, sola lettura, dal 06/10) | — (solo libreria standard: registro dei turni, SQLite in sola lettura, `indice.json` delle estensioni) | `calliope/schermi/cruscotto.py` → `Cruscotto` (`amministra`, `dati`), `LettoreTurni`, `versione_in_uso`, `tipo_errore`; GET `/api/cruscotto` (`server.py`); `Schermi.cruscotto`; scheda locale `cruscotto` in `schermo.js` (`apriCruscotto`, `impostaAmministra`), voce di Io del telefono (dal 27/10; prima del menu); `latenza.leggi_file` |
| Lettore Markdown e «Scarica» nella scheda del documento (07/10) | scritto in proprio in `schermo.js` (createElement e textContent, mai innerHTML); conversione con fpdf2 e python-docx sul server | `schermo.js` → `leggiMarkdown`, `mdBlocchi`, `mdInLinea`, `pulsantiScarica`; `calliope/schermi/scarica.py` → `Scaricamenti` (`registra`, `gettone`, `prendi`), `converti`; POST `/api/scarica` e GET `/scarica/<gettone>` (`server.py`); `Schermi.scaricamenti`, `hub.pubblica`; `schede.documento_markdown`; `schermi_scarica_s` |
| Vista dello sviluppo, lavoro in diretta a schermo intero, flusso dell'agente (08/10) | scritto in proprio in `schermo.js` (createElement e textContent); niente librerie | `schermo.js` → `assorbiFlusso`, `chatFlusso`, `colonnaFlusso`, `disegnaAvanzamento`, `misuraSegui`, `ripristinaSegui`, `vistaSviluppo`, `disegnaVista`, `comandiSviluppo`, `apriInteroPC`, `disegnaInteroPC`; `telefono.js` → `sincronizza` (apre e chiude la vista); `hub.per_storia`, `hub.registra_scaricabili`; `scarica.converti` (`markdown_file`); `calliope/agenti/avanzamento.py` → `Avanzamento`, `_Argomenti`, `esito_breve`, `chiamata_breve`; `calliope/sviluppo.py` → `Sviluppi.dati_vista`, `agli_schermi`, `riepilogo_lavoro`, `totali` |
| Cronologia delle schede per persona e scheda «Conversazione» (08/10) | solo libreria standard: un file JSON per persona (scrittura atomica da un thread), l'archivio delle conversazioni in SQLite | `calliope/schermi/cronologia.py` → `CronologiaSchede` (`aggiungi`, `ultime`, `pulisci`), `rivedi`, `lavoro_finale`; `hub.py` → `Schermi.ripresa`, `collega(ripresa=…)`, `pulisci_schede`, `chat_per`, `chat_nuovi`, `chat_dimenticata`, `registra_chat`, `ricostruttori`; `carica_cronologia`, `cartella_cronologia` (`schermi/__init__.py`); POST `/api/schede` (`server.py`); `conversazioni.py` → `ArchivioConversazioni.chat`, `chat_markdown`, `su_turni`, `su_dimentica`, `voce_chat`; `conversazione.turni` (`_turno`, `senza_sfida`); `Ciclo._archivia_turno`, `_luogo_turno`; `Brain.archivia_turni`; tool `schede_pulisci`; `schermo.js` → `DISEGNA.chat`, `impostaChat`, `chatDalServer`, `apriChat`, `pulisciSchede`, `pulisciLocale`; telefono: «La nostra conversazione» in Conversazione e «Pulisci le mie schede» in Io (dal 27/10; prima nel menu) |
| Rispondi dove ti ho chiesto | — (prestito del satellite attivo, origine del turno) | `calliope/rispondi.py` → `Instradamento`; `ServerSatelliti.presta` / `restituisci` / `per_schermo`; `Schermi.origine_corrente`, `invia_a`, `Mittente.schermo`; `Speaker.muto` |

## Problemi noti

*Fuse il 09/10 le due sezioni nate dalla divisione di CLAUDE.md (stato e problemi fino al
06/10): ogni voce una volta sola, le superate segnate come storiche.*

- **Scrivere solo in conversazione** (05/10, `calliope/schermi/conversazione.py`, prove
  `prova_scritto_conversazione.py` e quelle dello scritto e delle foto adattate): casella,
  moduli e foto (`/api/immagine`, «Foto» con trascina e Ctrl+V; una foto in attesa della
  domanda decade a conversazione finita, `InAttesa.togli`) valgono solo durante una conversazione cominciata a voce, così chi ha in mano
  lo schermo personale non scrive a nome del proprietario. Personale: il proprietario
  riconosciuto **dalla voce** (non breve, zona grigia né scritto), da **qualunque** satellite
  (i moduli vanno a tutti i suoi schermi: si parla al portatile e si scrive sul telefono),
  nessun altro ha parlato dopo (altra persona o voce non riconosciuta chiudono), niente
  «esci», ultima frase della sua voce entro `storia_inattiva_s` (breve e scritto non
  allungano; la finestra di follow-up no). Di stanza (`schermi_scritto_stanza`): una
  conversazione a voce di chiunque in quella stanza. Senza: 403 `senza_conversazione`, niente
  al ciclo (ricontrollato in `main.py` prima del turno), regola `scritto_senza_conversazione`
  nel registro senza il testo; la pagina (schermi e telefono) spegne casella e «Invia» con
  «Di' «Calliope» per scrivermi» e si riaccende all'evento SSE `scrittura` (anche in
  benvenuto e accesso). Un modulo aperto si chiude con una nota quando la conversazione
  finisce; la domanda di un lavoro annunciata a conversazione chiusa dice «oppure chiamarmi e
  scrivere». Funzione pura con la conversazione come argomento, `Conversazioni` per chiave
  (oggi una, fase 3 una per satellite). Con lo speaker id spento non si scrive mai.
  *[storico dal 28/10 per lo schermo personale: casella, foto e file valgono anche senza aver parlato,
  al più «familiare» (#301, «Scrivere nella Conversazione», più sotto); la regola resta per i moduli e
  per gli schermi di stanza]*

- **Scrivere invece di parlare** (03/10, `calliope/schermi/moduli.py`, prove
  `prova_scritto*.py`): quando un tool chiede dati tipizzati (campi mancanti di
  `modello_compila`, contatto nuovo di `anagrafica_salva` con un codice che non torna, domanda
  di un lavoro dell'agente) lo schermo personale di chi parla mostra un modulo (codice fiscale,
  partita IVA, IBAN mod 97, CAP, provincia, data, importo, email, righe…) con i controlli
  mentre si scrive e di nuovo sul server; i valori vanno **dritti al tool** (né Whisper né il
  modello, nella storia solo «ho scritto i dati per …»), e la voce dice «… o li scrivi sullo
  schermo?» solo se una pagina l'ha ricevuto. Chi risponde prima vince: richiamare il tool a
  voce chiude il modulo. La casella «scrivi a Calliope» (schermi personali e telefono; di stanza
  solo con `schermi_scritto_stanza`, come ospite) entra nel ciclo dopo lo STT, nome tolto,
  `identified_by = "schermo"`, `canale: scritto`. Permessi nel codice: lo scritto vale come il
  proprietario dello schermo ma al più familiare; installazioni, fatture
  (`ufficio_livello_fiscale`), schermo personale e codice all'agente chiedono la voce
  (`serve_la_voce`, azione in sospeso; un «sì» breve subito dopo resta «schermo»). Codici, IBAN
  ed email non vanno nel registro dei turni né nel terminale (`oscura`); dal modulo solo i nomi
  dei campi. Misura con gemma4 (3 giri): con la pagina collegata la voce offre lo schermo 4/4
  quando il tool chiede i dati; per «fammi un preventivo» senza prezzi gemma4 chiede da sé
  (0/6 chiamate) e il modulo non compare. Non provato con un telefono vero.

- **Schermi** (02/10, `calliope/schermi/`, `calliope/tools/schermi.py`; prove
  `prova_schermi.py` a secco e `prova_schermi_ollama.py`; prova manuale in `prove/manuali/schermi.md`, dal 06/10; *[storico: «in `prove/LEGGIMI.md`», fino al 06/10]*).
  Fase 1 di [`docs/ricerche/2026-10-01-mappe-e-schermi.md`](../ricerche/2026-10-01-mappe-e-schermi.md);
  le fasi 2–4 (mappe, luoghi, percorsi) no. Una pagina kiosk su PC, tablet o TV, abbinata con
  un codice detto a voce, mostra le schede dei tool (lista della spesa, timer con il conto alla
  rovescia, voce della biblioteca, anteprima dei documenti, stato della casa, calcoli) mentre
  Calliope risponde; le schede personali vanno solo sugli schermi personali.
  - **Server**: Starlette 1.7.0 + uvicorn 0.54.0 senza extra in un thread daemon, sul socket
    aperto da Calliope (porta occupata = capacità «guasta», non un `sys.exit` nel thread),
    `log_config=None`, log degli accessi spento, `ws="none"`, `http="h11"`. Il ciclo asyncio è
    di Calliope (`asyncio.run` nel thread) con un gestore che ignora i `ConnectionResetError`
    del ciclo Proactor di Windows: senza, ogni tablet che chiude la connessione stampava una
    traccia. All'arresto ogni flusso SSE riceve «fine» e si chiude da sé (0,2 s invece di 1,2 s
    e una traccia di `CancelledError`).
  - **Predefinito: acceso, solo su 127.0.0.1:8770.** La pagina è in http e il token viaggerebbe
    in chiaro sul Wi-Fi: di predefinito non esce dal PC (fase 1 del rapporto: il kiosk è il
    portatile stesso, dove 127.0.0.1 è un contesto sicuro). Per tablet e TV
    `schermi_indirizzo: 0.0.0.0` in `calliope.locale.yaml`. **In rete HTTPS** (02/10,
    `schermi/tls.py`): certificato dei satelliti (o `schermi_tls_cert`/`schermi_tls_chiave`);
    senza, il server non parte («da configurare» con il passo), salvo `schermi_senza_tls:
    true` con un avviso a ogni avvio; su 127.0.0.1 resta http. Il satellite apre la pagina
    dal suo **ponte TLS** su 127.0.0.1 (`schermi/ponte.py`, impronta SHA-256 ricevuta sulla
    connessione verificata); `--ignore-certificate-errors-spki-list` Edge 154 lo ignora. Un
    tablet vede l'avviso del certificato la prima volta. Il certificato di DuckDNS è la fase 4.
    Solo Host con un IP, «localhost» o il nome del PC (`schermi_nomi` per gli altri): difesa
    dal DNS rebinding. CSP `default-src 'self'`, niente CDN né font esterni (prova).
  - **SSE, non WebSocket**: una direzione, riconnessione del browser, nessuna libreria. Latenza
    misurata dalla consegna alla riga ricevuta dal client: mediana 0,4–0,5 ms, massimo ~1 ms su
    30 invii; `Schermi.invia` costa 0,1–0,4 ms al thread dei tool. EventSource non manda
    intestazioni: la pagina scambia il token con una **sessione** (`/api/accedi`) e apre
    `/eventi?sessione=…`; il token non finisce mai in un URL (tranne `#t=` del kiosk, che resta
    nel browser). Niente cookie: due schede dello stesso browser possono essere due schermi.
  - **Abbinamento**: la pagina chiede un codice (6 cifre, 10 minuti, al massimo 20 in attesa) e
    riceve una «richiesta» lunga e segreta che, ad abbinamento fatto, **diventa il suo token**
    (device flow): sul disco solo lo SHA-256. 5 codici sbagliati in 10 minuti annullano tutti
    i codici in attesa. Il codice detto si prende dagli argomenti; se il modello ne perde le
    cifre, dalla frase se lì sono esattamente 6 (regola `codice_dalla_frase`). Il codice è un
    argomento segreto (`ToolSpec.segreti`): `[TOOL]` e il registro dei turni scrivono
    `******`, e `Brain.redact` lo toglie da testo, richiesta e risposta del registro (anche
    «123 456»). Resta in chiaro solo nella riga «Tu: …» della console (e in
    `CALLIOPE_DEBUG_AUDIO` se acceso). Revoca a voce o da terminale: la pagina torna al codice
    (da terminale al ping successivo, 15 s).
  - **Visibilità**: `pubblica` (timer, calcoli, biblioteca) su ogni schermo della stanza;
    `casa` (liste, stato della casa) solo per chi è riconosciuto; `personale` (promemoria,
    appuntamenti, documenti, risposte che hanno usato tool personali) solo sugli schermi
    personali di chi parla, mai nella zona grigia. Limite noto: «fammelo leggere» dopo una
    risposta data con i **ricordi** della persona (messaggio di sistema, nessun tool) vale
    `casa`, non `personale`.
  - **Schede dai tool**: il risultato ha `scheda` (o `schede`), che `Brain._run_tool` toglie
    prima del modello e manda subito (prima della seconda passata: prova). Il documento la
    manda anche a file pronto in secondo piano, con chi l'aveva chiesto (`job.on_scheda`).
    Senza schermi le schede non si costruiscono. Nel registro dei turni `schede` con tipo,
    visibilità, schermi raggiunti e motivo; i rifiuti per visibilità come regole
    (`schermo_personale`, `schermo_ospite`, `schermo_zona_grigia`).
  - **Tool**: `schermo_mostra(cosa)` per tutti, `schermo_gestisci` solo chi amministra; frasi
    pronte (`risposta_finale`) che dicono cosa è successo davvero («è sullo schermo dello
    studio», «sembra spento: lo vedrai appena si riaccende», «è una cosa tua…»). Con l'enum
    `agenda` il modello sceglieva `timer` per «fammi vedere i miei promemoria sullo schermo»:
    ora si chiama `promemoria`. «Fammelo vedere sullo schermo» dopo un calcolo, senza
    l'esempio nel prompt, 1 volta su 2 era «cosa vuoi che mostri?». Prova su Ollama, 2 giri:
    38/38, prima frase mediana 0,55 s; i distrattori «abbassa la luminosità dello schermo» e
    «blocca lo schermo» restano a `pc_luminosita` e `pc_blocca`. Un familiare che dice
    «abbina lo schermo…» fa chiamare `schermo_gestisci` (il modello lo vede nominato nel
    prompt) e il registro lo rifiuta con «NON è stata eseguita».
  - **Latenza della voce con il server acceso**: stesse 5 richieste, 20 risposte per parte,
    schermi spenti (nessun tool, nessun server) 0,48 s di mediana, accesi (2 tool in più,
    server e una pagina collegata) 0,50–0,51 s: nel rumore.
  - Con `schermo_mostra` e `schermo_gestisci` registrati le prove esistenti restano uguali,
    2 giri: `prova_pc_ollama` 62/62 (prima frase mediana 0,48 s), `prova_casa` 42/42 (0,52),
    `prova_documenti_ollama` 34/34 (1,35), `prova_casa_ha_ollama` 58/58 (0,43),
    `prova_stato_ollama` 34/34 (0,49).
  - Registro delle capacità: 12 capacità *[storico, 02/10: poi 18; 19 dal 13/10, `len(capacita.DEFINIZIONI)`]*; «schermi» conta come presente nel prompt se i tool
    ci sono, anche senza schermi abbinati (si abbinano proprio a voce). Pagina provata in Edge
    headless via DevTools: abbinamento, tutte le schede, revoca, nessun errore JS.
  - **Riavvii e schede aggiornate** (02/10, dopo la prima sera sulla DGX): la porta si riapre
    dopo un riavvio veloce (`calliope/porte.py`: SO_REUSEADDR fuori da Windows,
    SO_EXCLUSIVEADDRUSE su Windows, 10 s di tentativi; anche per i satelliti); la pagina si
    ricollega sempre da sola (ogni errore del flusso rifà `/api/accedi` con il token, attese
    1–15 s per sempre, evento `ping` ogni 15 s e flusso muto da 40 s rifatto, «riconnessione…»
    nello stato; prova nel browser vero `prove/prova_schermi_pagina.py`). Le schede legate a
    un oggetto hanno una **chiave** (`timer:<id>-<fine>`, `agenda:<persona>`,
    `documento:<id>`, `lista:<chiave>`, `lavoro:<id>`): la stessa cosa cambiata (annullo,
    modifica, scadenza) sostituisce la sua scheda e la porta in cima, senza doppioni nemmeno
    al riaggancio; `sposta: false` (aggiornamenti automatici) la lascia al suo posto. Un
    timer per scheda; annullato o scaduto resta con «annullato alle 23:05» / «scaduto alle
    23:07» per 60 s e poi va nella cronologia (non sparisce: si vede cosa è successo). La
    scadenza la manda l'agenda (`Agenda.on_scaduta`). Calcoli e biblioteca: ogni volta nuove.
  - **Stato della voce sullo schermo** (02/10, `Schermi.voce`, fascia `#voce` della pagina):
    addormentata («Dormo · di' «Calliope»», luna), in ascolto («Ti ascolto», anello, con i
    secondi che restano della finestra di follow-up e una barra che scende), sta pensando (tre
    puntini), sta parlando (tre barre): colore **e** forma, testo grande, `role="status"`; la
    fascia sta sopra la scheda e non la copre. Lo manda il ciclo principale (prima di
    `listen`: ascolta o dorme; frase arrivata: pensa), il VAD (`on_speech_start`: ascolta,
    `on_speech_end`: lo stato di prima) e `Speaker.on_parla` (frase che parte, anche dal
    satellite). Va solo agli schermi del microfono che ascolta: con un satellite quelli della
    sua stanza (`stanza_corrente`), con l'audio locale quelli di `schermi_stanza` o, se è
    vuota, le pagine aperte su questo PC (127.0.0.1). Pubblico: solo `stato` e `fino`. Alla
    scadenza della finestra un thread dell'hub manda «dorme» (e la pagina lo fa da sé con
    l'orologio del server); al riaggancio il `benvenuto` porta lo stato di adesso.
    `Schermi.voce` costa < 1 ms e non blocca. Provato in Edge headless: i quattro stati sopra
    una lista, nessun errore JS.
  - **Stato della voce per corsia e per stanza** (06/10, P9 dell'analisi complessiva; prove
    `prova_schermi.prova_voce_stanze`, `prova_corsie.prova_voce_per_corsia`): con i satelliti
    insieme lo studio che pensa e la cucina che dorme si sovrascrivevano (un solo stato
    nell'hub, e i callback del VAD e della riproduzione erano quelli della corsia locale,
    mandati alla stanza del satellite «attivo»). Ora `Schermi._voce` è per stanza
    (`voce(stato, fino, stanza=None)`, `_conn_voce(chiave)`, "" = le pagine di questo PC),
    con finestra di follow-up e riaggancio per stanza; senza stanza vale come prima il
    microfono che ascolta. Ogni `Ciclo` manda il suo stato alla stanza del suo satellite
    (`Ciclo.stanza_voce`; satellite scollegato: niente) e lega a sé `on_parla` della sua voce
    e `on_speech_start`/`on_speech_end` del suo ascolto (`Ciclo._collega_voce`, sopra i
    callback dell'arbitro e della compressione).
    **Più satelliti nella stessa stanza** (06/10, Q9 della seconda analisi; prove
    `prova_schermi.prova_voce_stessa_stanza` con l'hub vero e due `Ciclo`,
    `prova_corsie.prova_voce_per_corsia`): prima vinceva chi scriveva per ultimo, e la corsia
    che scartava una frase riportava «dorme» mentre l'altra parlava. Ora ogni corsia è una
    sorgente (`voce(…, sorgente="sat:<id>")`, `Schermi._voce_src`) e la stanza mostra l'unione
    (`_unione`: parla > pensa > ascolta > dorme; in ascolto la finestra più lunga); un
    satellite spostato lascia la stanza di prima. Un satellite che se ne va toglie il suo
    stato (`Schermi.voce_via`, da `main.Corsie._voce_di_chi_va`): la stanza mostra gli altri,
    o esce da `_voce` e le pagine (anche al riaggancio) dormono invece di restare su «pensa».

- **Rispondi dove ti ho chiesto** (04/10, `calliope/rispondi.py`, prova `prova_rispondi.py`):
  una domanda scritta dal telefono aveva la risposta dalle casse dello studio (satellite attivo).
  Ora una frase scritta da uno schermo di un satellite rende quel satellite attivo **in prestito**
  per il turno e la finestra di follow-up (poi torna com'era; un `prendi`/`lascia` del satellite
  chiude il prestito); da uno schermo senza audio la voce resta muta se il satellite attivo è in
  un'altra stanza, e la risposta a una frase scritta arriva sempre anche come scheda «risposta»
  sullo schermo da cui è stata scritta. Le schede vanno prima allo schermo dell'origine
  (`Mittente.schermo`), poi agli altri come prima. Gli annunci di timer e promemoria (per id
  dell'agenda) e di documenti e lavori (per persona) si dicono dal satellite da cui erano stati
  chiesti, se è collegato; in memoria, dopo un riavvio vale l'attivo.

- **Telefono (web app)** (03/10, `calliope/schermi/telefono.py`, [`docs/ricerche/2026-10-03-webapp-telefono.md`](../ricerche/2026-10-03-webapp-telefono.md)):
  web app servita dal server degli schermi, stesso protocollo dei satelliti, wake word e VAD nel
  browser con gli stessi numeri del Python, schede come uno schermo personale. Provato in Edge
  senza finestra con il microfono finto (`prova_telefono_pagina.py`): i telefoni veri e l'auto
  no. Più satelliti collegati, uno attivo (`prendi` / `lascia`):
  prima un satellite nuovo toglieva il posto (4409) a quello collegato: portatile e telefono si
  sarebbero sostituiti all'infinito. Ora ne è attivo uno, il telefono lo prende con «Parla» o
  il microfono acceso e lo restituisce spegnendolo o andando in secondo piano; `pc_*` e
  documenti vanno al satellite con l'esecutore (`per_pc`). Con un certificato autofirmato
  Chrome non registra il service worker e iOS può dimenticare l'eccezione nella web app: per
  questo la CA di casa (foglia ≤ 825 giorni, limite di iOS). Un programma di sicurezza del
  portatile decomprime le risposte prima del browser (`x-content-encoding-over-network: gzip`):
  il peso con gzip si misura senza proxy. Sul portatile in Edge: inferenza ~10–12 % di un core
  con il microfono acceso (embedding della wake word ~3,5 ms ogni 80 ms), pagina ~92 kB,
  modelli e WebAssembly ~8 MB la prima volta (poi dalla cache), preparazione ~1,2 s.

- **Schermo acceso col microfono, vista da guida** (04/10, `schermo-acceso.js`, prova
  `prova_telefono_schermo.py`): in auto con «Microfono acceso» lo schermo dell'iPhone si
  spegneva, iOS sospendeva la pagina e Calliope smetteva di ascoltare (a schermo spento una
  pagina web non ascolta, su nessun browser). Il wake lock c'era già, ma partiva dopo l'apertura
  del microfono: WebKit vuole il **gesto in corso** per la prima richiesta (dopo una riuscita
  no, 263382@main), quindi ora si chiede subito nel tocco, si riprende da solo se il sistema lo
  toglie e con un tocco qualsiasi se il browser l'aveva negato, si lascia col microfono spento.
  Versioni (WebKit, MDN): Safari da iOS 16.4; Edge e Chrome per iOS (WKWebView) da **18.4**;
  web app sulla schermata Home da **18.4** (da 16.4 a 18.3 la richiesta riesce ma lo schermo si
  spegne lo stesso, bug 254545: la pagina lo riconosce dalla versione e lo dice). Indicatore
  sotto l'interruttore («Schermo acceso», oppure «Lo schermo può spegnersi, e allora Calliope
  smetterà di ascoltare: <perché e rimedio>», anche Blocco automatico «Mai»), opzione per
  spegnerlo. **Vista da guida** (pulsante, o da sola dopo 90 s di microfono acceso senza tocchi):
  fondo nero, colori smorzati ma AA, ultima risposta, «Parla», «Microfono», «Esci», nessuna
  animazione; rifatta la sera (sull'iPhone il cerchio dello stato usciva dai bordi e «Parla» stava
  sotto la piega): tutto in uno schermo (100dvh, anche 320×568 e in orizzontale), fascia di stato
  di **questo** telefono («Microfono spento», con «Il microfono attivo è su «studio»» sotto),
  risposta tagliata con una dissolvenza; misure e screenshot in `prova_telefono_schermo`.
  **Dal 04/10 (sera) la pagina è sempre quella vista** (richiesta dell'utente: più pulita e
  coerente): niente vista normale, «Vista da guida» né «Esci». In alto lo stato e l'icona delle
  impostazioni; un **carosello** (scroll-snap, puntini) con la risposta e le schede (al più 6,
  da `schermo.js` in modo `data-carosello`: eventi `calliope:schede`/`mostra`/`scrivi`/`scritto`,
  `costruisci` e `allinea` esposti), la più recente per prima; una scheda aggiornata resta al suo
  posto (stesso elemento), una nuova si mostra, la risposta subito dopo una scheda (12 s) non la
  copre, chi scorre a mano non viene spostato per 10 s; «Parla» più basso (17dvh) e col
  microfono acceso ancora di più (72 px: si risponde a «Calliope»), lo spazio al carosello;
  «Microfono» e «Scrivi» in fondo. Menu (impostazioni, «Prova il microfono», schermo acceso,
  certificato, «dimentica», stato del collegamento), modulo da compilare (si apre da solo,
  «Compila» nel carosello) e casella per scrivere sono strati sopra. Misure a 375×812, 320×568,
  812×375 con 0 e 6 schede, ogni scheda in vista, e i tre strati. Il trucco del video muto in loop (NoSleep) non c'è: senza un
  iPhone con iOS < 18.4 non si misura se serve. Provato in Edge headless con un wake lock finto
  «alla WebKit»; sull'iPhone vero no (passi in `prove/manuali/telefono.md`, «Prova manuale del telefono» 9; *[storico: «in `prove/LEGGIMI.md`», fino al 06/10]*).

- **Abbinamento del telefono che riprende** (03/10, iPhone 13 mini con Edge): per dire il codice
  la persona esce dal browser, iOS sospende la pagina e chiude il WebSocket, e il token mandato
  a una connessione morta si perdeva (sulla DGX restavano abbinamenti orfani). Ora la pagina
  chiede l'abbinamento con `ripresa: true` e tiene in localStorage codice e **ripresa** (un
  secondo segreto); tornando in primo piano (`visibilitychange`, `pageshow`) o riaperta manda
  `riprendi` e ritrova lo stesso codice o il token (una volta sola; «ricevuto» lo conferma).
  Sul disco solo lo SHA-256 della ripresa e il token cifrato con una chiave ricavata da lei
  (`ArchivioSatelliti.ritira`, schema `satelliti` versione 2). Un abbinamento il cui token
  non arriva (né sessione né «ricevuto») si toglie da solo dopo `codice_s` (colonna
  `consegna`), anche per il portatile. Dopo più di 3 s in background la sessione si riapre
  subito, senza le attese crescenti. Prova `prova_telefono_abbina.py` (anche in Edge headless).

- **Audio rovinato dall'iPhone** (03/10, prova vera con iPhone 13 mini ed Edge, cioè WebKit):
  Whisper scriveva parole in islandese, l'impronta dava 0,11–0,24. Causa: il microfono usava il
  contesto audio della riproduzione, nato al primo tocco prima che la cattura (VoiceProcessingIO,
  sessione «play-and-record») cambiasse la frequenza dell'hardware; WebKit legge allora il
  microfono al ritmo sbagliato. Prova: le registrazioni di Dario accelerate ×1,5–×2 danno con
  CAM++ 0,16–0,22 di mediana (0 % sopra soglia), quelle con banda 100–7000 Hz, guadagno e
  soppressione del rumore 0,64–0,69 (97 %); la frase di Piper ×2 diventa per Whisper
  giapponese (auto) o «Alli uppe, chi ho il solo?» (it). Ora il microfono ha un contesto suo,
  creato **dopo** getUserMedia (su iOS senza frequenza imposta = quella dell'hardware, altrove
  quella della traccia; se non coincidono si rifà), la riproduzione si rifà alla frequenza nuova,
  la sessione resta «play-and-record», e la pagina confronta l'orologio del contesto con quello
  vero (avviso e contesto rifatto oltre ±6 %). «Prova il microfono» nella pagina
  (`calliope/schermi/telefono_diagnostica.py`, `POST /telefono/api/diagnostica`, solo telefoni
  personali) registra due volte 5 s (con e senza le correzioni del browser), salva i WAV in
  `diagnostica/telefono/` (7 giorni) e risponde con frequenze, ritmo, livelli, tono, voce per il
  VAD e impronta del proprietario. Prova `prova_telefono_audio.py`. Da verificare sull'iPhone.
  Seconda impronta per canale: non serve se il canale è a banda larga (0,64–0,69); con il
  Bluetooth a banda telefonica (300–3400 Hz) l'impronta scende a 0,45 (33 % sopra soglia).

## Una scheda a schermo intero sul telefono (06/10)

Difetto segnalato da Dario dall'iPhone 13 mini: il cruscotto, il codice di un lavoro, un
documento, l'uscita di un programma si aprivano solo nel riquadro del carosello (con la
dissolvenza in fondo e le tabelle tagliate di lato), e non c'era modo di vederli più grandi.
Correzione d'uso, solo nella pagina (`telefono.js`, `telefono.css`, `index.html`), niente al
server né al modello. Prova `prova_scheda_intera.py` (livello 3, Edge headless).

- **Come si apre**: un tocco sulla scheda (non sui suoi pulsanti, né su modulo e gioco, che
  hanno il loro strato e il loro riquadro) oppure «Espandi», in fondo a destra della scheda
  (≥ 44 px, colore d'accento), visibile sulle schede lunghe: per tipo (cruscotto, lavoro,
  documento, esecuzione, biblioteca, web, allegato) o quando il contenuto non ci sta, in alto o
  di lato (`segnaTagli`, classe `lunga`). La risposta ha «Espandi» solo quando non ci sta (un
  tocco sulla risposta non apre niente: è breve, al più ~300 caratteri). Il cruscotto dalla voce del menu si apre **direttamente** a schermo intero e resta
  anche nel carosello.
- **Lo strato** (`#strato-scheda`, come menu, modulo e scrivi): testa ferma con il titolo e
  «Chiudi» grande (≥ 64 px) in alto, contenuto che scorre in verticale (`#intera-posto`), testo
  ≥ 16 px (la pagina ha 17 px di base; etichette, badge, righe tenui del cruscotto e codice
  portati a 1rem), tabelle e codice che scorrono di lato nel loro riquadro (la tabella con
  `display: block` e le parole che non si spezzano: con `overflow-wrap: anywhere` della scheda
  si stringeva a una lettera per riga), mai la pagina. Il «Chiudi» del cruscotto (che toglie
  la scheda) nello strato è nascosto: vale quello dello strato; «Aggiorna» resta.
- **Aggiornamenti**: la scheda aperta si allinea al suo posto a ogni aggiornamento con la
  stessa chiave (`sch().allinea`, come il carosello: il cruscotto ogni 30 s o con «Aggiorna»,
  un lavoro in diretta, un programma che scrive), senza perdere lo scorrimento; l'uscita di un
  programma resta in fondo solo se chi guarda era in fondo. Una scheda nuova va nel carosello
  e lo strato resta. Se la scheda esce dalla cronologia (più di 6) resta aperta con l'ultimo
  contenuto; si chiude da sola solo se la toglie chi guarda (il «Chiudi» del cruscotto), se il
  cruscotto non è più permesso o se lo schermo è revocato.
- **Chiusura**: «Chiudi», Esc, il gesto indietro (all'apertura una voce nella cronologia del
  browser con `history.pushState`; «Chiudi» ed Esc la tolgono con `history.back()`), e
  l'apertura di un altro strato. Col microfono acceso «Parla» resta sotto lo strato: un tocco su
  «Chiudi» e c'è (vincolo della vista da guida). Niente animazioni (come tutta la pagina),
  contrasto AA, strato alto quanto lo schermo, a 375×812, 320×568 e 812×375.
- **Pagina degli schermi** (tablet, portatile, TV) — *storico, superato l'08/10: anche lì c'è lo
  schermo intero, vedi «La scheda dello sviluppo e del lavoro in diretta»*: valutato e non cambiato. Lì la scheda
  prende già tutta l'area tra la testa e la cronologia, il corpo scorre in verticale e le
  tabelle e il codice scorrono di lato dentro di lui; uno strato in più toglierebbe solo la
  fascia della voce e la cronologia.
- Cache del service worker `calliope-telefono-pagina-v6` (era v5): la pagina si prende comunque
  prima dalla rete.

## Cruscotto di chi amministra (06/10, fase 1: solo lettura)

Decisione di Dario del 06/10: un pannello per **misurare**, ammesso durante il congelamento
perché non cambia la voce. Prove `prova_cruscotto.py` (a secco) e `prova_cruscotto_pagina.py`
(Edge headless: schermo e telefono).

- **Dove**: una scheda della pagina (mai mandata dal server, mai nella sua cronologia), solo
  sugli **schermi personali di chi amministra**: pulsante «Cruscotto» nella testa della pagina
  degli schermi, voce «Stato di Calliope (cruscotto)» nel menu del telefono, che la apre nel
  carosello. Mai sugli schermi di stanza, mai a un familiare. `/api/accedi` dice `amministra`
  solo per decidere se mostrare il pulsante; `GET /api/cruscotto` (sessione in
  `X-Calliope-Sessione`, solo HTTPS fuori da 127.0.0.1) **ricontrolla a ogni richiesta**
  schermo personale + proprietario con `admin` in speakers.json (un amministratore tolto non
  vede più niente alla richiesta dopo; speakers.json illeggibile: nessuno). 403 altrimenti,
  404 senza cruscotto.
- **Cosa**: versione in uso (VERSIONE.json del gestore sulla DGX, il commit sul portatile);
  capacità con stato, motivo e prossimo passo (senza i `dettagli`); latenza per giorno degli
  ultimi 7 file del registro (mediana, p90, base, dalla fine del parlato, cause, avviso oltre
  `latenza_avviso_s`, giudizi mancati del guardiano, **attesa delle schede trattenute**
  `schede_attesa_ms`, aggiunta anche a `latenza.giorno` e a `calliope stato --turni`);
  satelliti e schermi abbinati (stanza, personale di chi, ruolo, collegato o ultimo
  collegamento, **inattivi** da `schermi_inattivi_giorni` con il comando di revoca come testo);
  regole scattate per nome e per profilo o modello; errori del ciclo **solo per tipo**
  (`tipo_errore`: un nome di classe d'eccezione in testa, altrimenti «errore»: il messaggio
  può contenere ciò che è stato detto); richieste in attesa: avvisi ai tutori non ancora detti
  (solo quanti), estensioni da approvare (nome e versione), lavori in attesa di risposta e in
  corso (solo quanti, mai i titoli).
- **Niente azioni** (storico: dal 09/10 la ricerca web ha «Controlla» e «Aggiorna», sezione sotto): solo «Aggiorna» (rilegge) e «Chiudi» (toglie la scheda); revoche e
  approvazioni restano a voce o da terminale, qui il comando come testo. Niente dati personali
  di altri: niente testi delle conversazioni, ricordi, documenti, titoli; gli ospiti nel
  registro non hanno testi comunque.
- **Costo**: calcolo nel thread pool del server (`asyncio.to_thread`), mai nel thread della
  voce; cache di 25 s (la pagina chiede ogni 30 s finché la scheda c'è e la pagina è visibile;
  «Aggiorna» ricalcola al più ogni 5 s); i file del registro si rileggono solo se cambiano
  (dimensione e data), di solito solo quello di oggi. Misura del 06/10 sul portatile: registro
  di 7 giorni × 4000 turni (~9 MB) primo calcolo 0,2–0,4 s, poi 0,07–0,11 s con il solo file di
  oggi riletto, dalla cache < 1 ms; 3 giorni × 300 turni ~0,1 s.
- **Prefisso del modello invariato**: nessun tool, niente nel prompt né negli schemi (prova
  nel `prova_cruscotto` e `prova_brain.prova_prefisso_uguale`; sha256 del prefisso uguale a
  main).
- **Fase 2** (non fatta): azioni dal pannello (revoche, approvazioni) con la conferma a voce.

## Lettore Markdown e «Scarica» nella scheda del documento (07/10)

Decisioni di Dario del 07/10: i testi dell'agente arrivano in Markdown (area
documenti-ufficio); la scheda del documento li legge, sugli schermi e sul telefono (anche nel
carosello a schermo intero), e ha «Scarica».

- **Il lettore** (`schermo.js`, `leggiMarkdown`): lo stesso sottoinsieme di
  `documenti/markdown.py`, costruito con `createElement` e `textContent`, **mai innerHTML** (il
  testo dell'agente non è fidato). I collegamenti restano testo non cliccabile con l'indirizzo
  tra parentesi (`md-link`, `md-indirizzo`: niente `<a>`, niente navigazione), le immagini un
  segnaposto (niente rete); un HTML scritto nel testo si legge com'è. CSP invariata. Limiti:
  120 000 caratteri, 1500 blocchi, tabelle di 200 righe (la nota «… e altre N righe») e 20
  colonne, 6 livelli di elenco, 4 citazioni annidate, enfasi annidate al più 3 volte e di 400
  caratteri. Con due titoli o più il **sommario** in alto: un tocco porta al titolo
  (`data-md-vai` → `scrollIntoView` dentro la stessa scheda). Le tabelle scorrono di lato nel
  loro riquadro (`tabella-md`); sul telefono a schermo intero valgono le misure del 06/10 (testo
  ≥ 16 px, niente di lato, contrasto AA), provate a 375×812, 320×568 e 812×375.
- **La scheda**: `schede.documento_markdown` (tipo `documento`, `formato` «md», `markdown`
  tagliato a 60 000 caratteri con la nota, `riassunto`, file e cartella); per un lavoro la chiave
  `lavoro:<id>`, che sostituisce la scheda in diretta. Anche le schede dei documenti a blocchi
  (lettere, documenti dell'agente, fogli) hanno «Scarica».
- **«Scarica»** (`schermi/scarica.py`): pulsanti MD, PDF, Word (Excel e MD per un foglio). La
  sorgente intera sta nella chiave `_scarica` della scheda, che **resta sul server**: `hub.pubblica`
  toglie le chiavi con «_» prima dell'SSE e della cronologia. Quando la scheda arriva a uno
  schermo personale del suo proprietario, con l'identità decisa dalla voce (`Mittente.certo`), lo
  schermo la registra (`Scaricamenti.registra`, le ultime 64); con `invia_a` (la risposta allo
  schermo da cui si è scritto) vale il proprietario di quello schermo. La pagina chiede un
  gettone (POST `/api/scarica`, sessione nell'intestazione come lo scritto, JSON, solo HTTPS in
  rete, 20 al minuto per schermo): solo uno schermo personale a cui la scheda è arrivata, e il
  cui proprietario è la persona della scheda o amministra; **mai dalla zona grigia** (lì la
  scheda personale non parte; il risultato del proprio lavoro mostrato nella zona grigia,
  regola `risultato_schermo_proprio`, arriva senza «Scarica»), mai da uno schermo di stanza.
  Poi `a.download` su GET `/scarica/<gettone>`: 24 byte a caso, valido `schermi_scarica_s`
  (180 s) e 3 richieste (un download che riprova, l'anteprima di iOS), legato allo schermo
  (revocato: 404); niente sessione nell'URL. La conversione la fa il primo GET in un thread
  (`asyncio.to_thread`), poi resta nel gettone. Tipi solo nostri (md, pdf, docx, xlsx: niente
  eseguibili), `Content-Disposition: attachment` con il nome in UTF-8 (RFC 6266), nosniff, CSP
  `default-src 'none'; sandbox` (un file aperto invece che salvato non esegue niente). Sul
  telefono il file va negli scaricamenti del browser (provato nel browser headless: PDF, Word e
  MD arrivano).
- **Prove**: `prova_markdown.py` (a secco: hub e server veri, gettoni, permessi, intestazioni),
  `prova_markdown_pagina.py` (browser vero: testo ostile con `<script>`, `onerror`,
  `javascript:`, immagini, 300 righe, 20 annidamenti; nulla eseguito, nessun elemento
  pericoloso, solo gli attributi del lettore, «Scarica» davvero, schermo intero leggibile).
- **Da provare sul vero**: lo scaricamento dalla PWA su iPhone (Safari apre l'anteprima del
  file, «Condividi» → «Salva su File») e su Android.

## La voce che si sente sul telefono (07/10)

- La pagina non mandava `suona` (06/10, protocollo dei satelliti): sul telefono `prima_voce_s`
  mancava in tutti i turni del 05–07/10. Ora `Riproduttore.onSuona` (`voce.js`) scatta al
  primo pezzo di ogni frase messo in coda su Web Audio, con `uscita_s` = quanto manca
  all'inizio programmato più `outputLatency` (o `baseLatency`) del contesto; `telefono.js` lo
  manda come il satellite in Python e il server scrive `prima_voce_s`. Nel browser non c'è
  silenzio iniziale (`tts_lead_s` è solo di `UscitaLocale`) e la riproduzione comincia 30 ms
  dopo il primo pezzo arrivato.
- La prima frase lunga arriva in due pezzi (`tts_spezza_prima`, vedi
  [contesto-conversazione](contesto-conversazione.md)): la scheda della risposta li unisce con
  uno spazio come le frasi (`ricordaFrase`).
- Prova a secco in `prova_latenza.prova_voce_a_pezzi` (il codice della pagina); nel browser
  vero da rimisurare col registro dopo l'aggiornamento (`calliope stato --turni`, per satellite).

## Pause dentro la frase dal telefono (07/10, solo misura)

`voce.js` misura le pause dentro la frase come `calliope/pause.py` (`MisuraPause`: silenzi tra
120 ms e `silence_ms` sugli stessi frame del VAD che chiude il turno; dopo un tocco su «Parla»
si conta dalla prima voce) e `listen` restituisce anche `pause`, `parlato` e `chiusura`
(«silenzio», «lunga», «rilascio» del tasto); `telefono.js` li manda in `frase_finita`
(`pause_ms`, `parlato_ms`, `chiusura`). Nessun comportamento cambiato. La ripresa dopo la frase
(taglio probabile) sul telefono non si misura: il microfono si ferma a fine frase. Riassunto per
persona e canale in `calliope stato --turni --pause` ([stt-tts](stt-tts.md)). Prova
`prove/prova_pause.py` (il modulo vero eseguito con node, se c'è).

## «Mostramelo.» breve dopo un lavoro consegnato (07/10 pomeriggio, DGX, ramo `correzioni-giro7`)

Caso vero (qui con nomi di fantasia): lavoro finito e annunciato («ho finito «…». Lo apro?»),
«Sì, aprilo.» breve (aperto), poi «Mostramenob.» (breve, zona grigia) → `schermo_mostra(cosa=
documento)` rifiutato «Non ho riconosciuto bene la tua voce: le cose personali non le mostro…»,
subito dopo che la stessa persona l'aveva chiesto e ricevuto. Con il nome, «Mostralo.» funzionava,
ma mostrava l'ultimo **documento di Calliope** della persona (l'archivio dei documenti), non il
risultato del lavoro appena annunciato (che non sta in quell'archivio).
- **Quale documento** (`tools/schermi._documento`): il più recente tra l'ultimo documento della
  persona e il risultato del suo ultimo lavoro riuscito (`agenti.risultato.recenti`, per `fine`),
  con la scheda del risultato (`risultato.scheda`, testo intero in Markdown).
- **Zona grigia** (regola `risultato_schermo_proprio`, la stessa di `risultato_lavoro`, dall'08/10 `lavoro_risultato`): il
  documento o il risultato della persona della conversazione (proprietario uguale a
  `mittente.persona`) **appena consegnato** (il suo titolo è in una risposta recente della
  conversazione, `ToolContext.storia`: l'annuncio, la conferma) va sui suoi schermi personali
  anche dalla zona grigia; senza «Scarica»; mai sugli schermi d'altri. Contrari in
  `prova_risultati.py`: un documento non consegnato in questa conversazione (rifiutato come
  prima), un'altra persona (niente scheda di chi ha chiesto il lavoro); con la voce riconosciuta il
  risultato più recente, senza la regola.

## Scheda degli esercizi (08/10, ramo `esercizi-pilota`)

*[storico: le schede `esercizio` ed `esercizi_riepilogo`, il loro disegno e `POST /api/esercizio` sono
tolti il 28/10 con gli esercizi (#279, decisione [0035](../decisioni/0035-studio.md)); la tessera Studio di Le mie cose resta e dice
«arriva presto», senza conto, fino al passo 4.5 (#284).]*

Tipo `esercizio` (personale, chiave `esercizi:<persona>`) e `esercizi_riepilogo` (per i tutori),
disegnati in `schermo.js` (`DISEGNA.esercizio`, `DISEGNA.esercizi_riepilogo`): domanda grande,
campo per scrivere o pulsanti delle scelte, esito, «Un indizio», «Salta», «Secondo me è
sbagliato», «Basta così». `POST /api/esercizio` (sessione in un'intestazione, JSON, HTTPS fuori
da questo computer, 30 al minuto per schermo) risponde senza passare dal modello: solo da uno
schermo personale il cui proprietario ha una sessione aperta (cominciata a voce), fuori dagli
orari di pausa. La scheda si ricostruisce intera a ogni aggiornamento (niente `allinea`: i
gestori leggerebbero l'esercizio di prima; anche nel carosello del telefono) e il campo riprende
il fuoco. La risposta attesa non arriva mai alla pagina. Prove `prova_esercizi` (server vero) e
`prova_esercizi_pagina` (Edge senza finestra, schermo e telefono). Area e misure in
[minori](minori.md).

- **Scheda del cassetto dei file** (08/10, [immagini-allegati](immagini-allegati.md)): tipo
  `cassetto`, personale, chiave `cassetto:<persona>`, costruita da `Cassetto.scheda` e mandata
  con `invia_a` a ogni schermo personale della persona; un carosello orizzontale dentro la scheda
  (miniatura in data URL o sigla, nome come testo, quando e da dove, scadenza) con «Tieni»,
  «Elimina», «Tieni ancora 7 giorni» e in alto «Elimina tutti» (secondo tocco entro 4 s) e
  «Tieni tutti». I pulsanti vanno a POST `/api/cassetto` (sessione in un'intestazione, JSON,
  HTTPS, solo schermo personale e solo i file del proprietario, 30 al minuto); la scheda
  aggiornata torna dal server con la stessa chiave. Prova `prova_cassetto_pagina.py`.

## La scheda dello sviluppo (08/10, ramo `modalita-sviluppo`)

La modalità sviluppo ([agenti-estensioni](agenti-estensioni.md#modalità-sviluppo-0810-ramo-modalita-sviluppo))
ha una scheda per sviluppo sugli schermi personali di chi amministra, chiave `sviluppo:<id>` (si
aggiorna al suo posto): nessun JavaScript nuovo nella pagina *[superato lo stesso giorno: dal ramo `scheda-sviluppo` la scheda ha `tipo: "sviluppo"` e una vista sua, due sezioni sotto; il Markdown resta per il lettore e «Scarica»]*, è `schede.documento_markdown` con il
lettore Markdown e «Scarica» che ci sono già (`Sviluppi.scheda`, `testo_scheda`). Dentro: le fasi
(fatta, **adesso**, manca), la specifica, i collaudi con dati, esito e ora, la revisione (permessi,
analisi, test, prove, e il diff in un blocco `diff`), cosa si può dire. Si manda a ogni passo dei
tool `sviluppo` e `sviluppo_prova` *[dall'08/10, versione 2: `sviluppo_passo` e `sviluppo_collauda`]* (`hub.mittente`) e a lavoro finito (`lav.on_scheda`); durante lo
sviluppo resta anche la scheda del lavoro in diretta. Il testo dei collaudi viene dall'estensione:
il lettore usa `textContent`, mai `innerHTML`.

## La prova del telefono nel browser gira sempre (08/10, ramo `prova-telefono-pagina`)

Fino al 07/10 `prova_telefono_pagina.py` si saltava in ogni `--completo` (anche nel repository
principale): onnxruntime-web non era installato da nessuna parte sul portatile, e nei worktree
mancavano anche i modelli della wake word e le voci. Ora:

- onnxruntime-web 1.30.0 è installato una volta nel principale con l'installatore del catalogo
  (`python -m calliope.stato --installa telefono`, 14 MB da jsDelivr, SHA-256 verificati) in
  `models/web/`, ignorata da git; i due modelli generici della wake word c'erano già;
- la prova cerca ogni cartella (`risorsa`) in quest'ordine: `CALLIOPE_TELEFONO_MODELLI` (solo
  onnxruntime-web), la sua radice, `PROVE_ORIGINE` (la copia dell'indice dell'hook) e il
  repository principale (`git rev-parse --git-common-dir`). Si sceglie la prima che ha tutti i
  file; niente link né copie. Il messaggio del salto dice dove ha cercato.

Misure dal worktree senza file locali (08/10): 27 controlli superati, preparazione dei modelli
1,3 s, pagina 283 kB, modelli e onnxruntime 8,0 MB trasferiti (gzip), CPU dell'inferenza nel
browser 7,6 %.

## La scheda dello sviluppo, versione 2 (08/10, ramo `modalita-sviluppo-2`)

*Le tre sezioni sulla scheda dello sviluppo (questa, quella sopra e quella sotto) sono tre passi successivi dello stesso giorno, non copie: lo stato attuale è quello della sezione `scheda-sviluppo` qui sotto.*

La scheda `sviluppo:<id>` mostra anche le domande fatte a chi ha scritto il codice
(`sviluppo_chiedi`) con i dettagli della risposta (la voce ne dice una o due frasi), i collaudi
che non vanno («non riuscito», con l'esito per intero), e tra le frasi d'esempio «perché…?»,
«correggilo» e «chiudi lo sviluppo». Si manda anche a ogni domanda all'agente e a ogni
correzione; a una tappa del lavoro resta la scheda del lavoro in diretta.

## La scheda dello sviluppo e del lavoro in diretta, la vista dello sviluppo (08/10, ramo `scheda-sviluppo`)

Richieste di Dario dopo il giro vero della DGX delle 14:36–15:30 («Meteo città», S1: cinque
lavori, due correzioni, una tappa), più l'aggiunta della vista dello sviluppo. Server in
[agenti-estensioni](agenti-estensioni.md#la-scheda-del-lavoro-in-diretta-e-i-conti-dello-sviluppo-0810-ramo-scheda-sviluppo).
Prove `prova_scheda_sviluppo.py` (a secco, ~1 s) e `prova_vista_sviluppo_pagina.py` (Edge senza
finestra, computer e telefono, ~40 s).

- **Schermo intero sulla pagina degli schermi** (satellite PC, tablet, TV): «Schermo intero»
  nell'etichetta del lavoro, del documento e dell'uscita di un programma apre uno strato alto
  quanto la finestra (`#strato-intero`, «Chiudi» ed Esc), che si aggiorna al suo posto con la
  stessa chiave. Sul telefono c'era dal 06/10: stessa costruzione (`costruisci(c, {intera: true})`),
  carosello invariato.
- **Due colonne a schermo intero** (≥ 900 px; sotto, una colonna): a destra sempre «il codice
  che gira» (il flusso dell'agente, con «Scarica il registro»), a sinistra in alto il riepilogo
  (stato e giro, passo, test, tetti, sviluppo: fase, «Correzione N, riparte dalla versione
  provata», numeri dello sviluppo intero), sotto i file scritti e gli ultimi passi. **Nella scheda
  normale il flusso non c'è** (e nemmeno l'anteprima del codice).
- **Il flusso come una chat in sola lettura** (`assorbiFlusso`): prima ogni aggiornamento
  mandava gli ultimi 600 caratteri e la pagina li riscriveva da zero. Ora i pezzi nuovi arrivano
  numerati (`n`) con la sezione (`s`); la pagina li accumula per chiave del lavoro, scarta quelli
  già visti e, se manca un pezzo (un invio perso), chiede la finestra ricollegandosi (al più due
  volte di fila, poi segna il taglio). La cronologia del server tiene la scheda con l'ultima
  finestra intera (`_storia`, `hub.per_storia`): chi si ricollega riprende senza buchi né
  doppioni (provato con pezzi arrivati a pagina giù). Sezioni: «Ragiona» (corsivo, tenue),
  «Scrive», «Scrive il codice · file» (in un riquadro che scorre di lato), → chiamata in breve
  (mai il contenuto del file), ← esito in breve («2 test su 3 passano», «scritto»), separatore
  «passata N» (o «giro 2 · passata 25»). Tetto nella pagina 40 000 caratteri, come la finestra:
  oltre, «L'inizio non è qui: è nel registro completo». Testo dell'agente sempre con textContent,
  CSP invariata.
- **Scorrimento**: segue la coda; chi torna indietro a leggere resta lì e compare «In fondo»
  (≥ 44 px), che riprende la coda. Girando il telefono o cambiando la finestra chi seguiva resta
  in fondo. Le aree che seguono la coda ora sono `[data-segui]` (`misuraSegui`/`ripristinaSegui`,
  anche per il telefono).
- **CSP**: `allinea` copiava l'attributo `style` delle barre dei tetti con `setAttribute`, che
  con `style-src 'self'` è una violazione (la prova nuova l'ha trovata: le barre in diretta
  non erano mai state allineate in una prova nel browser); ora `style.cssText` (CSSOM).
- **La vista dello sviluppo** (aggiunta di Dario): con uno sviluppo aperto gli schermi
  personali di chi sviluppa (computer e telefono) passano a una vista fatta apposta; gli altri
  schermi di casa non cambiano. La scheda `sviluppo:<id>` ha ora `tipo: "sviluppo"` con i dati
  strutturati (`Sviluppi.dati_vista`; il Markdown di prima resta per il lettore e «Scarica») e la
  manda `Sviluppi.agli_schermi` a ogni cambio di fase o di stato (apertura, collaudo, domanda,
  sospensione, ripresa, chiusura). Nella vista: la barra delle fasi (fatta, adesso, manca), il
  titolo con nome dell'estensione, versione, giro e correzioni; al centro le due colonne
  (riepilogo del lavoro e flusso); le sezioni del collaudo (prove con dati, esito, versione e il
  giudizio della persona), delle domande a chi l'ha scritto (con i dettagli), della revisione
  (permessi e analisi, col lettore Markdown) e dell'analisi (richiesta e specifica), quella della
  fase di adesso per prima; in fondo i comandi a tocco. Sul computer la vista prende l'area
  delle schede (la cronologia si nasconde; «Vista normale» torna alle schede e «Torna allo
  sviluppo» nella testa riporta qui); un modulo, un gioco o un esercizio la interrompono (vogliono
  una risposta). Sul telefono si apre da sola a schermo intero (se non c'è un altro strato
  aperto), in una colonna: riepilogo, flusso, sezioni, comandi; «Chiudi» torna al carosello, un
  tocco sulla scheda la riapre. Sviluppo chiuso o sospeso: si esce dalla vista.
- **Comandi a tocco** solo innocui, come frasi scritte (`/api/scrivi`, quindi solo durante una
  conversazione cominciata a voce, e con la politica di sempre; *[storico: dal 28/10, #301, dallo schermo
  personale anche senza aver parlato]*): «A che punto siamo?», «Prova
  con…» e «Chiedi all'agente…» (la frase da finire nella casella dello scritto), «Riprendi lo
  sviluppo» (sospeso), «Vista normale». Testi fissi della pagina, mai testo della scheda.
  Approvare e attivare restano a voce con la frase di sfida: nessun pulsante, e la vista lo dice.
- **Chiaro e scuro**: la pagina degli schermi e il telefono hanno un tema solo (scuro, `color-scheme:
  dark`); la vista usa gli stessi colori (variabili di `schermo.css`), e con lo schema chiaro del
  sistema resta scura e leggibile (screenshot). Un tema chiaro vero sarebbe un lavoro a sé.
- Cache del service worker `calliope-telefono-pagina-v7` (era v6).

Costo: un aggiornamento del flusso costa alla pagina
un'allineata del sotto-albero della colonna (qualche centinaio di nodi al tetto); al server,
un pezzo dello stream per chi lavora resta nei microsecondi (`prova_avanzamento`, 20 000 pezzi →
1–2 schede con un pezzo per sezione). Rete: un invio porta solo il testo nuovo (prima la coda
intera di 600 caratteri a ogni invio); la finestra (≤ 40 000 caratteri) va solo a una pagina che
si ricollega.

## Cronologia delle schede per persona e scheda «Conversazione» (08/10 sera, ramo `cronologia-persona`)

Richiesta di Dario: la cronologia stava solo in memoria per schermo (`_storia`, ultime
`schermi_cronologia`), si perdeva a ogni riavvio e uno schermo personale nuovo partiva vuoto.

- **Su disco, per persona** (`calliope/schermi/cronologia.py`): ogni scheda **personale** mandata
  da `invia` con l'identità certa (`Mittente.certo`, familiare o chi amministra: mai ospiti né
  zona grigia) o da `invia_a` a uno schermo personale va nella cronologia del proprietario,
  anche se in quel momento non ha uno schermo collegato. Mai le schede pubbliche o della casa
  (di stanza), mai «vuota», le partite e le schede solo della pagina (cruscotto, conversazione).
  Un file JSON per persona in `schermi_cronologia_cartella` (vuota = `schede/` accanto a
  `conversazioni.db`), 700/600 fuori da Windows come il cassetto, scritto in modo atomico da un
  thread suo un attimo dopo (la voce e i tool non aspettano il disco). Tenuta
  `schermi_cronologia_giorni` (7), tetto `schermi_cronologia_max` (40) e `schermi_cronologia_mb`
  (4 MB) per persona; una scheda oltre 512 kB si salva senza la sorgente di «Scarica», poi niente.
  Chiavi uniche come la cronologia degli schermi (al loro posto con `sposta: false`); le chiavi
  legate a un oggetto in memoria (`foto:`, `allegato:`, `risposta:`, fatte con `id()`) valgono
  solo nello stesso avvio.
- **Ripresa** (`Schermi.ripresa`, in un thread del server prima di `collega`): uno schermo
  personale che si collega (nuovo, ricollegato, dopo un riavvio) riceve le ultime
  `schermi_cronologia` (6) schede del **suo proprietario**, in ordine, prima di quelle che ha già;
  mai di un'altra persona (un tutore non vede quelle del ragazzo, e viceversa), mai uno schermo
  di stanza. Ogni scheda passa da `rivedi`: modulo chiuso e timer finito si saltano;
  l'avanzamento di un lavoro che non lavora più (interrotto dal riavvio, o finito) diventa la
  scheda finale («interrotto», «Finito: chiedimi il risultato»), senza flusso né anteprima; in
  attesa di una risposta resta; gli esercizi chiusi diventano il riepilogo senza la domanda
  (aperti: la scheda vera della sessione); un programma che girava prima di un riavvio è
  «fermato»; il cassetto tiene solo i file che ci sono ancora; lo sviluppo si ricostruisce da
  `Sviluppi` (`ricostruttori`, da `main.py`: quello aperto va in fondo anche se non era tra le
  ultime, così lo schermo rientra subito nella vista dello sviluppo). Il flusso di un lavoro
  arriva con l'ultima finestra (`per_storia`). «Scarica»: la sorgente resta sul server e si
  registra di nuovo per lo schermo nuovo; il gettone lo chiede la pagina al tocco (sempre nuovo),
  quello di prima del riavvio non vale più.
- **Pulire**: «Calliope, pulisci le mie schede» (tool `schede_pulisci`, familiari e chi
  amministra, solo con la voce riconosciuta, senza conferma) o il tasto «Pulisci» in fondo alla
  cronologia degli schermi personali (due tocchi) e «Pulisci le mie schede» nel menu del
  telefono (`POST /api/schede`, solo da uno schermo personale e solo per le sue schede, 10 al
  minuto). Via dal disco e dai suoi schermi personali (evento SSE «pulisci»); gli schermi d'altri
  e di stanza non cambiano; lo sviluppo aperto resta (è uno stato: la scheda torna subito); la
  conversazione no (per quella c'è «dimentica le nostre conversazioni»).
- **Scheda «Conversazione»** (solo schermi personali, `schermi_chat_turni` = 80, 0 = spenta): le
  frasi della persona come trascritte o scritte e le risposte di Calliope, con l'ora, il
  satellite o lo schermo e «scritto». Riusa l'archivio delle conversazioni (niente doppioni: ne
  è una vista; [contesto-conversazione](contesto-conversazione.md)): nel benvenuto gli ultimi
  turni della persona (`chat_per`), poi l'evento «chat» con i soli turni nuovi a ogni turno
  archiviato (`chat_nuovi`, da `ArchivioConversazioni.su_turni`), in fondo, senza riscrivere
  quelli di prima (la pagina scarta i doppioni per id). Mai i turni degli ospiti né di altre
  persone, mai la frase di sfida né i codici (le pulizie dell'archivio); le risposte riservate
  restano «(risposta con dati riservati: non archiviata)»; «dimentica le nostre conversazioni» la
  svuota anche qui (`chat_dimenticata`); tenuta come l'archivio. Sul computer il pulsante
  «Conversazione» nella testa (e «Schermo intero»), sul telefono «La nostra conversazione» nel
  menu, a schermo intero e nel carosello, in una colonna. «Scarica Markdown» della trascrizione
  intera, fatta al tocco dall'archivio (`scarica.converti` con `markdown_fn`), solo dagli schermi
  personali. Tutto con createElement e textContent; CSP invariata. Riusa il riquadro del flusso
  dell'agente (`flusso-chat`: «In fondo», segue la coda solo se si era in fondo).
- Prove: `prova_cronologia_schede` (a secco, ~2 s) e `prova_cronologia_pagina` (Edge headless,
  ~35 s: riavvio del server vero, schermo nuovo, telefono). Screenshot controllati (1280×800 e
  390×844): bolle «Tu» a destra e «Calliope» a sinistra, una barra di scorrimento sola nella
  scheda normale (la prima versione ne aveva due e non arrivava in fondo); sul telefono la
  scheda a schermo intero ora va in fondo all'apertura (anche il flusso dell'agente: prima lo
  scorrimento si chiedeva con lo strato ancora nascosto). Dal 13/10 «Scarica» salva nella
  cartella di download del profilo temporaneo (preferenza `download.default_directory` scritta
  prima di avviare Edge) e la prova controlla lì il file con la trascrizione: prima finiva nei
  Download veri di chi lanciava la prova (e `Page.setDownloadBehavior` sulla scheda qui non
  bastava).
- Cache del service worker `calliope-telefono-pagina-v8` (era v7).
- Da fare o da provare sul vero: molti lavori in diretta insieme (una scrittura su disco al più
  ogni 0,8 s per persona); «mostramelo» dopo un riavvio (oggi `Schermi.ultima` è solo in memoria).

## Il segno della compagnia (09/10, ramo `compagnia`)

In compagnia con una voce sconosciuta ([stt-tts](stt-tts.md)) serve il nome a ogni frase, e lo
schermo lo dice in modo discreto: lo stato della voce porta `compagnia: true`
(`Schermi.voce(..., compagnia=True)`, mandato da `Ciclo.voce` quando serve il nome; con più
satelliti nella stessa stanza vale se lo è una sorgente). La pagina degli schermi mostra sotto lo
stato la riga piccola «In compagnia: chiamami per nome» (`.voce-compagnia`), anche quando si
riaddormenta; il telefono la aggiunge alla riga sotto lo stato (evento `calliope:compagnia` dalla
pagina incorporata). Sparisce con una voce sola. Prova `prove/prova_compagnia_pagina.py` (livello 3).

## Le prime azioni del cruscotto: «Controlla» e «Aggiorna» di SearXNG (09/10, ramo `searxng-aggiornamento`)

Decisione di Dario del 09/10 (meccanismo in [biblioteca](biblioteca.md), `calliope/web/motore.py`).
Con il motore della ricerca web il cruscotto ha una sezione **«Ricerca web (SearXNG)»**:
immagine in uso, giudizio dell'ultimo controllo (va bene, degradata, non risponde) con il
motivo, le prove (categoria, domanda fissa, risultati, motori che non rispondono e perché),
il tag più recente nel registro, il modo (automatico o manuale, o «non disponibile qui:
…»), la fase di un controllo o aggiornamento in corso, l'ultimo esito e le ultime decisioni
(chi e cosa). Due pulsanti, **«Controlla»** e **«Aggiorna»** (questo solo dove il container
c'è).

- **Chi**: le stesse regole di `/api/cruscotto` (sessione in un'intestazione, HTTPS fuori da
  127.0.0.1, schermo personale il cui proprietario amministra, ricontrollato a ogni richiesta):
  mai uno schermo di stanza, mai un familiare; nessuna voce di mezzo, quindi nemmeno la zona
  grigia. `POST /api/motore` con corpo JSON.
- **Due tocchi con un gettone**: il primo tocco chiede un gettone (`{azione}`), legato allo
  schermo e all'azione, che vale **una volta** e scade in 60 s (`GETTONE_S`); il pulsante
  diventa «Tocca ancora: controlla». Il secondo manda `{azione, gettone}` e l'azione parte in un
  thread del motore. Un gettone di un'altra azione, di un altro schermo, già usato o scaduto:
  «conferma scaduta: tocca di nuovo». Al più 6 richieste al minuto per schermo
  (`AZIONI_MINUTO`, 429). Ogni azione nel log (`[CRUSCOTTO] … da «schermo» (id)`) e nella
  storia del motore (`cruscotto:<id>`).
- **Esito**: mentre l'azione gira la pagina rilegge il cruscotto ogni 2 s (al più 20 minuti) e
  mostra la fase; la sezione del motore non passa dalla cache di 25 s del cruscotto (è un
  file piccolo). Il resto del cruscotto resta in sola lettura e la nota lo dice.
- **CSP invariata**: pulsanti fatti con il DOM, delega dei clic come gli altri, niente HTML
  dal server.
- **Avvisi**: l'esito di un aggiornamento automatico e il passaggio a «degradata» come scheda
  «Da leggere» personale (`Cruscotto.avvisa` → `invia_a`) solo sugli schermi personali di chi
  amministra.
- Prove: `prova_searxng_aggiorna` (endpoint, gettoni, limite, avviso) e
  `prova_cruscotto_pagina` (Edge headless: sezione e pulsanti, primo tocco che chiede la
  conferma senza far partire niente, secondo che fa il controllo, esito sulla scheda, un
  familiare senza pulsanti, nessun errore JS né CSP).

## Il documento rimasto sul server va sulla scheda (09/10 sera, ramo `sera-politica-strumenti`)

`Schermi.personale_collegato(mittente)`: una scheda personale arriverebbe adesso, con «Scarica»,
a uno schermo personale di chi parla con la pagina aperta (identità dalla voce, schede
automatiche accese). La usa `documento_crea`: un documento rimasto sul server perché il telefono
non riceve file si dice «sulla scheda del tuo schermo: tocca «Scarica»». `documento_leggi`
«mostra» manda la scheda del documento con «Scarica». Dettagli in
[documenti-ufficio](documenti-ufficio.md).

## La modalità gioco (11/10, ramo `gioco-schermo-intero`)

Un gioco nel riquadro della scheda era troppo piccolo per giocarci (Dario, 11/10). Ora la scheda
di un gioco che arriva occupa tutta la finestra, sulla pagina degli schermi e nel carosello del
telefono, con ✕ per chiudere, ⛶ per lo schermo intero vero dove il browser lo permette e un
pallino colorato con lo stato della voce; c'è anche la variante «collaudo» con la cornice arancio
per un gioco in prova (`"prova": true` nella scheda). Dettagli, contratto e prove in
[giochi](giochi.md) («La modalità gioco»). Per gli schermi:

- è tutto in `schermo.js` (sezione «la modalità gioco»: `GIOCO`, `comandiGioco`,
  `aggiornaModoGioco`) e nei CSS; la scheda non si sposta nel DOM (diventa `position: fixed`) e
  sul telefono sta **sotto** gli strati (z-index 9 contro 10): un modulo che arriva, il menu o la
  vista dello sviluppo si aprono sopra il gioco. Uscendo, il carosello torna sulla scheda che si
  guardava (evento `calliope:gioco`);
- il pallino della pagina degli schermi usa l'evento `voce` che c'era già (dorme, ascolta, pensa,
  parla): nessun cambiamento nell'hub; sul telefono lo stato è quello del telefono e il pallino fa
  anche da «Parla»;
- «Calliope, chiudi il gioco» passa da `schermo_mostra` con `niente` (la scheda vuota), che ora
  chiude la modalità gioco anche nel carosello del telefono (prima lì la scheda vuota non toglieva
  il gioco);
- la voce non si ferma: lo schermo intero non cambia la visibilità della pagina, il microfono del
  telefono resta acceso (verificato in `prova_telefono_schermo`).

## La finestra del gioco e il pallino (11/10 sera, ramo `gioco-voce`)

Con un gioco che ascolta la voce ([giochi](giochi.md), «I comandi a voce di un gioco») il
pallino della modalità gioco resta verde («ascolto») finché il gioco aspetta una mossa, per
`giochi_ascolto_s` dall'ultima mossa: è lo stesso stato `ascolta` con il suo `fino` che il ciclo
manda già (evento `voce`), con la fine della finestra del gioco. Sul telefono è il
`sveglia_per_s` del suo ascolto (stesso protocollo dei satelliti): «Ti ascolto», «N s senza
nome». Niente di nuovo nella pagina per il pallino; schermo.js passa al riquadro la mossa
(evento «gioco» di tipo «comando», solo un nome di comando valido e al più il nome di chi gioca)
e, quando il gioco si chiude con ✕, Esc o la scheda vuota, manda `chiuso` al server, così
l'ascolto senza nome finisce. Prove in `prova_giochi_pagina` (la mossa nel riquadro, il
sottoinsieme a runtime, niente fuori elenco, ✕).

## `prova_telefono_schermo` sotto carico: l'errore era della prova (12/10 sera, ramo `correzioni-12-10`)

Nella suite completa, con altre attività sul portatile, la prova falliva su «nessun errore
JavaScript» con `SecurityError: Failed to read the 'localStorage' property from 'Window': The
document is sandboxed and lacks the 'allow-same-origin' flag`; da sola passava. La causa vera:
la Screen Wake Lock finta della prova (`FINTA`) si mette con `Page.addScriptToEvaluateOnNewDocument`,
che la esegue in **ogni riquadro dello stesso processo**, compreso quello del gioco
(`<iframe sandbox="allow-scripts">`, origine opaca), e la sua prima riga leggeva `localStorage`
senza protezione. Chromium di solito mette i riquadri sandbox in un processo a parte (lì lo
script non arriva); sotto carico li tiene nello stesso. Riprodotto ogni volta con
`--disable-features=IsolateSandboxedIframes --disable-site-isolation-trials` (eccezione
`at <anonymous>:31:3`, la riga di `FINTA`). Il codice della pagina era già a posto
(`schermo.js` e `telefono.js` leggono `localStorage` dentro try/catch, il gioco non lo vede).
Correzione nella prova: `FINTA` solo nella pagina in cima (`window.top !== window` → esce) e la
lettura protetta; con le due opzioni sopra ora passa.

`prova_scritto_calliope` (timeout a 300 s una volta sotto carico): misurata da sola 68 s, con
ogni attesa strumentata. Nessuna attesa fissa che scade (una sola `time.sleep(0.5)`), tutte a
condizione: le più lunghe sono Calliope che parte (6 s), il saluto (4 s) e la voce che finisce
di dire la risposta della rubrica (10 s) e il turno del modulo scritto a frase finita (5 s),
cioè l'audio in tempo reale di Piper. È solo carico: con il portatile occupato il tempo cresce
con l'avvio di Calliope e la sintesi; niente da correggere nel codice.

## La stanza ascolta: segno, interruttore del telefono, cruscotto (13/10, ramo `stanza-passo-1`)

Passo 1 della conversazione di stanza ([stt-tts](stt-tts.md), decisione
[0029](../decisioni/0029-conversazione-di-stanza.md): «stato sempre visibile»).

- **Schermi della stanza**: in alto, accanto allo stato del collegamento, «● Ascolto la stanza» o
  «❚❚ Stanza in pausa: ospiti, fino alle 22:15» (`#stanza-segno`, evento SSE `stanza` e campo
  `stanza` del benvenuto). Lo manda `Stanza` con `Schermi.stanza_segno(stanza, "sat:<id>", testo)`;
  con più satelliti nella stessa stanza la pausa si vede prima dell'ascolto; si toglie quando il
  satellite se ne va (non a una sua riconnessione).
- **Telefono** (protocollo 3, `telefono.js`/`voce.js`): un secondo Silero VAD con la sua sessione
  ONNX sugli stessi blocchi del microfono (`AscoltoStanza`), solo con la stanza accesa dal server,
  **l'interruttore** «Ascolto la stanza» nel menu (**acceso di serie** anche sui dati mobili,
  risposta 5 di chi amministra; `localStorage` `calliope.telefono.stanza`) e il microfono acceso;
  mai mentre Calliope parla. La riga sotto lo stato dice «Ascolto la stanza», «Ascolto della stanza
  spento su questo telefono» o la pausa con l'ora. L'interruttore compare solo se il server fa la
  stanza per quel telefono. Banda misurata nel browser a secco: ~52 kB per secondo di parlato
  (PCM 16 kHz non compresso, pre-roll e silenzio di chiusura compresi).
- **Cruscotto di chi amministra**: sezione «Stanza (in ombra)» con **solo numeri** (per satellite:
  ascolta o in pausa, righe in memoria, quante persone presenti; oggi: ore di parlato, coda p90,
  banda; segmenti in coda), come il resto del cruscotto, che non mostra testi delle conversazioni.
  Il «campione di righe riletto da chi amministra» del piano (§ 6, passo 1) **non** è nel cruscotto
  per questo motivo: resta da decidere come darlo (un comando da terminale sulla DGX, o una scheda
  personale di chi amministra con le righe degli adulti) prima del passo 2.

Prove: `prove/prova_stanza.py` (il segno dal server) e `prove/prova_stanza_voce.py` (livello 3: il
telefono nel browser vero con il microfono finto: righe senza byte ai comandi, segno, interruttore
spento).

## Il telefono a sezioni (27/10, ramo `telefono-sezioni-passo1`)

Passo 1 del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(capitoli 3 e 7, decisioni del capitolo 8; tavole nel canvas privato di chi amministra). Le schede
(`DISEGNA.*`) non cambiano; nel server cambia solo la sezione nelle schede.

- **Cinque sezioni** con la barra in basso (`#barra`): Adesso, Conversazione, Le mie cose, Casa, Io.
  Ogni sezione è un elenco verticale che scorre da sé (la pagina no); il carosello, i pallini e il
  menu delle impostazioni non ci sono più.
- **Dove va ogni scheda**: `SEZIONE_DI_TIPO` in `schermo.js` (accanto a `NOMI_TIPO`) e in
  `schede.py`, uguali (`prova_sezioni` le confronta): «sezione» o «sezione/raccolta» (`cose/liste`,
  `cose/agenda`, `cose/lavori`, `cose/documenti`, `cose/cassetto`, `cose/giochi`, `cose/studio`; il
  modulo in `cose`, sotto «Da scrivere»). `schede.nuova` la scrive nella scheda (`sezione`), e vale
  quella del server; le schede che non passano da `nuova` (chat, cruscotto) prendono quella della
  tabella. La scheda dello sviluppo nasce come documento in Markdown e cambia tipo: la sezione si
  riscrive lì (`sviluppo.py`), se no finiva in Documenti.
- **Adesso**: «Aspetta te» (modulo da compilare, voce nuova, avviso del tutore finché non si guarda
  Casa, lavoro che aspetta una risposta), «In corso» (le altre schede vive), «Ultima risposta» (il
  testo del turno e l'ultima scheda della conversazione se ha meno di 10 minuti). Una scheda è viva
  per la regola `viva(c)` di `schermo.js`: timer che corre, promemoria entro un'ora, lavoro in coda,
  in corso o in attesa, programma in corso, sviluppo aperto, modulo aperto, gioco non chiuso (né qui
  con ✕), esercizi
  aperti o in pausa, voce nuova aperta; lista, documento e casa per due minuti dopo un cambiamento. Si
  ricontrolla ogni 5 s (il timer che finisce esce da Adesso e resta in Agenda). Gioco, esercizi,
  sviluppo, cassetto, chat e voce nuova in Adesso sono un **rimando** con «Apri» (due copie di un
  gioco o di un esercizio avrebbero due stati, quelle della voce nuova due moduli con gli stessi
  id); le altre sono la stessa scheda, allineata al suo posto in tutti e due gli elenchi.
- **Gioco ed esercizi** che Calliope mostra aprono la loro raccolta da soli (`TIPI_APRONO`): il gioco
  entra nella modalità a tutta la finestra solo se la sua scheda è visibile. Una volta sola per
  scheda: una mossa o una risposta nuova non riporta lì chi è andato altrove. Il gesto indietro
  durante un gioco lo chiude, come ✕; in auto un gioco che arriva si chiude subito (il riquadro
  nascosto ascolterebbe i comandi a voce senza il nome).
- **Novità**: il pallino col numero sulla sezione per una scheda arrivata mentre si guarda altrove
  (non se si vede già in Adesso); guardando la sezione si toglie. Solo in memoria. La cronologia
  rimandata dal server a ogni (ri)collegamento non conta (`ripresa` nell'evento «schede»: la
  revisione della PR #252 aveva trovato le novità accese a ogni ricaricamento).
- **Router sul frammento**: `#/adesso`, `#/conversazione`, `#/cose/liste`, `#/casa`, `#/io`; un
  indirizzo sconosciuto è Adesso; il gesto indietro torna alla sezione di prima (`hashchange`); la
  scheda a schermo intero tiene la sua voce nella cronologia con lo stesso indirizzo (`popstate`).
  `#/cose/liste/<chiave>` porta in vista la scheda.
- **La voce sopra la barra**: in Adesso e in Conversazione stato, «Microfono», «Parla» largo,
  «Scrivi» e «Allega»; nelle altre sezioni più bassa: lo stato piccolo su una riga sua, sopra
  «Microfono» e «Parla» (dal 27/10 sera, dopo la prova sull'iPhone; *storico: fino ad allora una
  riga sola, stato, «Microfono», «Parla», e lo stato andava a capo a ogni sillaba*). Gli stessi
  `statoVista`, `impostaMic`, `tocca` di prima. Sotto i 360 px «Allega» resta nella casella di
  «Scrivi» e la barra è più fitta («Conversazione» in grassetto a 320 px non ci stava). Le voci
  della barra sono larghe quanto il loro nome (dal 27/10 sera: in colonne uguali, col font di
  sistema dell'iPhone, più largo di Segoe UI, «Conversazione» usciva dalla sua); le misure di
  `prova_telefono_schermo` si ripetono con un font largo (Verdana).
- **Io** al posto del menu: collegamento, schermo acceso, ascolto della stanza, «In auto», aiuto e
  prova del microfono, cruscotto (sotto «Amministra», solo a chi amministra), «Pulisci le mie
  schede», certificato, «Dimentica il telefono». «La nostra conversazione» è in Conversazione
  *[storico: fino al 28/10 sera un pulsante che la apriva a schermo intero; dal 28/10 sera, #242, la
  conversazione è dentro la sezione]*.
- **In auto** (decisione 1 del 27/10: a mano): «In auto» in Adesso e in Io; niente barra né schede,
  stato grande, l'ultima risposta in caratteri grandi, «Parla» alto un quinto dello schermo
  (`clamp(4.75rem, 20dvh, 10.5rem)`, più basso col microfono acceso), «Microfono» con la parola,
  tocchi ≥ 64 px; «Esci» torna ad Adesso. Resta dopo un ricaricamento (`localStorage`
  `calliope.telefono.auto`). Fuori dall'auto i tocchi sono ≥ 44 px (come nelle tavole).

Prove: `prova_sezioni` (nuova, livello 1: tabelle, sezione dal server, regola «viva» e router con
node); `prova_telefono_schermo` riscritta per le sezioni (smistamento, schede vive, timer scaduto,
ultima risposta, novità, router, Io, In auto; misure di ogni sezione e di «In auto» a 375×812,
320×568 e 812×375); adattate `prova_cronologia_pagina`, `prova_cruscotto_pagina`,
`prova_esercizi_pagina`, `prova_markdown_pagina`, `prova_scheda_intera`,
`prova_vista_sviluppo_pagina`. Da provare sul vero: l'iPhone (barra e zona sicura in basso, gesto
indietro nella PWA), «In auto» guidando.

## Accento lilla, accento personale e sezioni per età (27/10, issue #240, ramo `issue-240-aspetto`)

Passo 1c del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 2.1 e § 3.1, decisioni 2 e 8 del 27/10).

- **Lilla di serie** su telefono, PC e schermi condivisi: `--accento` `#b9a3e3` e la sua famiglia
  in `schermo.css` (`--accento-chiaro`, `--accento-bordo`, `--accento-selezione`,
  `--accento-fondo`, `--su-accento`, `--accento-rgb` per `--accento-tenue`); «ci penso»
  (`--v-pensa`) segue l'accento. I colori scritti a mano che seguivano l'oro (testo sopra
  l'accento, fondo di «Aspetta te», numero delle novità) sono diventati variabili. *Storico: fino
  al 27/10 oro, `#e2b45a` sugli schermi e `#cfa760` sul telefono.*
- **Accento personale** (`calliope/schermi/aspetto.py`): le scelte sono in `ACCENTI` (lilla, oro,
  rosa), ognuna controllata per il contrasto AA in `prova_aspetto`; la pagina riceve i colori dal
  server e li mette nelle variabili solo se hanno la forma `#rrggbb` (`applicaAspetto` in
  `schermo.js`). La scelta si fa in **Io › Aspetto** del telefono (`POST /api/aspetto`, solo da
  uno schermo personale), si salva per persona in `memoria.db` (`aspetto_preferenze`) e arriva
  subito a tutte le pagine aperte della persona (evento SSE «aspetto»), PC personale compreso;
  gli schermi condivisi restano lilla. Non scade col tempo; va via con i dati della persona
  (`conserva.TABELLE_PREFERENZE`, «svuota»).
- **Sezioni per età**: `/api/accedi` dà `nascoste` dal profilo del proprietario, riletto a ogni
  accesso (`Schermi.profilo`, da `main.py`): a un minore la raccolta Ufficio sempre (nasce col
  passo 2), Casa sotto i 13 anni; senza data di nascita vale la fascia scritta a mano (Casa solo per
  «adolescenti», 14–17; per «ragazzi», 11–13, nel dubbio no). Il telefono toglie la voce dalla barra,
  `#/casa` porta ad Adesso e una scheda di una sezione nascosta va in Conversazione: niente
  sparisce. Nascondere non toglie e non aggiunge permessi (restano in `ToolRegistry.call`).

Prove: `prova_aspetto` (nuova, livello 1); `prova_sezioni` (router con una sezione nascosta);
`prova_telefono_schermo` (Io › Aspetto: le scelte, un tocco su «Rosa» cambia l'accento e la barra
e lo salva; le sezioni nascoste e tolte). Le misure di contrasto di tutte le prove nella pagina
vera girano con il lilla. Da provare sul vero: il lilla sull'iPhone e sulla TV.

## Lo schermo personale del PC a sezioni, con «Parla» (27/10 sera, issue #239, ramo `issue-239-pc`)

Passo 1b del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 3.6). Decisioni di chi amministra del 27/10 sera: **le sezioni solo sugli schermi personali**
(TV e tablet di stanza restano con la scheda grande, l'orologio e la fila; la decisione 6 del
progetto vale per tablet e TV personali) e **«Parla» sul PC subito**.

- **Un modulo solo per le sezioni**: `pagina/sezioni.js` (`CalliopeSezioni.crea`) con lo
  smistamento, la regola delle schede vive in Adesso, i rimandi, le novità, il router sul frammento
  e le sezioni nascoste. Lo usano il telefono (`telefono.js` passa le sue parti: la scheda con
  «Espandi», gli strati, la vista dello sviluppo) e il PC (`pc.js`). Anche Io › Aspetto
  (`disegnaAccenti`, `suAccento`) è lì, e i suoi stili in `schermo.css`.
- **Solo sullo schermo personale**: `schermo.js` accende `S.sezioni` dopo `/api/accedi` se lo
  schermo è personale e la pagina le ha (`data-sezioni` sul body di `index.html`); allora emette gli
  stessi eventi del carosello del telefono (`calliope:schede`, `mostra`, `pc`…), non disegna la
  scheda grande né la fila, e `pc.js` mostra la struttura nascosta in `index.html`. Le viste di
  prima restano: la scheda a schermo intero (strato sopra la pagina), la vista dello sviluppo (in
  `#principale`, sopra la sezione), la modalità gioco.
- **Disposizione**: a sinistra le sezioni e in fondo la voce (lo stato `#voce` e «Parla»), al
  centro la sezione con le schede affiancate quando c'è posto, a destra la conversazione (la scheda
  «chat», fuori dalle sezioni con `escludi`) con la casella per scrivere (`#scrivi-posto`). Sotto i
  1100 px la conversazione è dietro il suo pulsante e si apre sopra la pagina (Esc la chiude);
  sotto i 760 px la barra va in basso, come sul telefono. Sullo schermo personale il testo ha la
  misura di una pagina da leggere da vicino (16 px), non quella della TV (2,4vmin).
- **«Parla»** (`POST /api/parla`): solo da uno schermo personale legato a un satellite
  (`ArchivioSchermi.lega_satellite`); `ServerSatelliti.tocca` fa prendere il posto al satellite
  (come il telefono che tocca «Parla») e gli manda «tocco» coi secondi di `schermi_parla_s` (8 di
  serie); il satellite allunga `Listener.sveglio_fino` e suona l'inizio, e il Listener ascolta
  senza il nome fino alla più lontana tra `awake_until` e `sveglio_fino`. Al più 20 al minuto; 409
  se il satellite è scollegato. Un satellite vecchio ignora «tocco». Il tasto da tenere premuto
  (Ctrl+Spazio) resta un'issue a parte.
- **Trascinare un file** sulla pagina c'era già (05/10) e vale su tutta la pagina: il file arriva
  nella casella sotto la conversazione.
- **Dalla revisione della PR #255**:
  - la frase cominciata nella finestra di «Parla» vale come il nome (`woke`, punteggio 1, come il
    tocco del telefono): prima il server la scartava come «risveglio scartato»;
  - mentre Calliope parla, «Parla» la ferma: il satellite chiude la veglia con «interruzione»
    (motivo «tocco»);
  - la conversazione a destra viene dalla pagina (`schedaChat`, evento «chatturni»), non dalla
    cronologia, che tiene al più 6 schede: prima si svuotava alla settima;
  - il «Cruscotto» della testa porta in Io, dove sta la sua scheda;
  - «Pulisci le mie schede» è in Io (c'era solo nella fila, che con le sezioni non c'è);
  - una scheda nuova lascia la vista dello sviluppo come faceva la scheda grande (timer, lavori,
    «Torna allo sviluppo»);
  - il gioco a tutta la finestra non prende le regole della scheda nell'elenco;
  - sotto i 1100 px la conversazione aperta sopra la pagina è un dialogo, e chiusa rende il fuoco
    al suo pulsante.
- **Si torna indietro** con `schermi_sezioni: false` (nel file locale): lo schermo personale del PC
  riprende la scheda grande e la fila, come gli schermi di stanza; il telefono resta a sezioni. Le
  prove del contenuto delle schede sulla pagina del PC (Markdown, cassetto, esercizi, moduli,
  cruscotto, cronologia, vista dello sviluppo) girano con la chiave spenta; la disposizione a
  sezioni la prova `prova_pc_pagina`.

Prove: `prova_parla_pc` (nuova, livello 1), `prova_pc_pagina` (nuova, livello 3), `prova_sezioni`
(il router in `sezioni.js`, il telefono che lo usa); le prove del telefono invariate. Da provare sul
vero: il portatile come satellite (la pagina in Edge, «Parla» con il microfono vero).

## Le mie cose: le tessere, la pagina Liste e il canale «tocco» (28/10, issue #256, ramo `issue-256-raccolte`)

Passo 2a del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 4.3–4.4), parte di #241 (analisi e decisioni lì), epic #251. Decisioni di chi amministra del 28/10:
**i tocchi che cambiano qualcosa si fanno sempre dallo schermo personale**, anche fuori da una
conversazione a voce (a differenza dello scritto), e **l'Ufficio solo a chi amministra**.

- **Le tessere** (`calliope/schermi/raccolte.py`, `POST /api/raccolte` con `{}`): otto, in cima a Le mie
  cose (Liste, Agenda, Lavori e programmi, Cassetto, Documenti, Giochi, Studio, Ufficio), con il conto,
  lo stato in una riga e l'ora dell'ultimo cambiamento. Si leggono **dai servizi**, non dalla cronologia
  delle schede (che tiene solo le schede personali: la lista è di casa, il timer è pubblico): le liste,
  l'agenda (timer di casa e promemoria e appuntamenti della persona per oggi), i lavori, il cassetto, i
  documenti fatti da Calliope, i giochi di casa, la sessione degli esercizi, i numeri dell'ufficio
  dell'anno. Un servizio che manca o che solleva dà la tessera senza conto («non disponibile», nel
  registro una riga `[SCHERMI] raccolta «…» non letta`), mai un errore alla pagina. L'Ufficio solo a chi
  amministra e mai a un minore (anche le raccolte nascoste di `aspetto.nascoste`). I servizi arrivano
  agli schermi da `main.py` (`Schermi.servizi`, `Schermi.tool_ctx` della corsia principale). La pagina le
  chiede all'ingresso in Le mie cose e ogni 60 s mentre è aperta, e poco dopo una scheda di Le mie cose
  arrivata; due colonne sul telefono, di più sul PC.
- **Il pallino** sulla tessera se l'«ultimo» del server è più recente di quello visto all'ultima visita
  (in `localStorage`, `calliope.raccolte.viste`, protetto da try): l'ora del server, niente orologi
  diversi. Scelta: una tessera mai vista prende l'«ultimo» di adesso, così alla prima apertura non ci
  sono pallini ovunque. Le voci tolte dalla lista non lasciano traccia nel database: `Liste.ultimo_cambio`
  tiene in memoria l'ora dell'ultima tolta (dopo un riavvio vale solo l'ultima aggiunta).
- **La pagina Liste** (`#/cose/liste`, `POST /api/raccolte` con `{raccolta: "liste"}`): tutte le liste di
  casa con le schede `lista` che esistono già, disegnate da `calliopeSchermo.costruisci`; prende il posto
  delle tessere e dei gruppi (`#sez-cose[data-vista="pagina"]`); il gesto indietro e «‹ Le mie cose»
  tornano alle tessere. Una scheda della lista aperta da Adesso (`vaiA`) porta alla pagina con la scheda
  in vista (`#/cose/liste/lista:spesa`). Le altre tessere dicono «pagina presto» e portano, come prima, al
  gruppo delle schede di quella raccolta (lì restano il gioco e gli esercizi che si aprono da soli); le
  loro pagine arrivano con i passi 2b–2e.
- **Il canale «tocco»** (`calliope/schermi/tocchi.py`, `POST /api/tocco`): l'elenco dei tocchi è chiuso
  (`TOCCHI`); la pagina manda solo il tipo e i dati che servono, controllati contro lo stato vero
  (la voce deve esserci adesso: 409; una voce che `lista_togli` dividerebbe, «pane e burro», o che
  svuoterebbe la lista, «tutto», 422 con «si toglie a voce»). Poi `hub.ingresso` → il ciclo
  (`Ciclo._tocco_dallo_schermo`): `ToolRegistry.call` col livello del proprietario dello schermo e
  `identified_by` «schermo» (i tool che vogliono la voce restano rifiutati), senza la politica del
  turno; la descrizione («(Ho tolto «latte» dalla lista della spesa toccando lo schermo.)») nella storia
  del modello con la chiamata del tool e il suo esito, il registro dei turni con `esito` e `canale` «tocco», l'evento
  `detto_persona` col canale «tocco». Niente frase detta né suoni (chi tocca può essere al supermercato);
  la lista aggiornata arriva come scheda solo allo schermo del tocco. Un rifiuto (permesso, minore,
  voce sparita) va solo allo schermo (evento SSE «tocco», `esito` «rifiutato» nel registro), e niente
  nella storia. Sullo schermo di stanza non c'è (403).
- **La spunta** (`DISEGNA.lista` in `schermo.js`, solo sugli schermi personali con le sezioni: telefono e
  PC personale): ogni voce è un `<button role="checkbox">` alto almeno 44 px; dopo il tocco resta
  segnata in attesa (`aria-busy`, «Tolgo «latte»…» nella regione `role="status"` della scheda) finché
  arriva la lista aggiornata; un errore (risposta HTTP o evento «tocco») la rimette com'era e si dice
  accanto, nel colore dell'allarme. Tutto in `textContent`. Sulle TV e i tablet di stanza la lista resta
  com'era.
- Cache del service worker `calliope-telefono-pagina-v10` (era v9).
- **Dalla revisione della PR #261**:
  - nella storia il tocco ha la sua chiamata: `Brain.record_tocco` scrive la frase, la chiamata del
    tool e il suo esito, chiude prima la conversazione scaduta, segna l'ultimo turno e salva su disco.
    Prima la riga si perdeva se la conversazione era ferma o dopo un riavvio, e con la frase dopo c'erano
    due messaggi della persona di fila ([contesto-conversazione](contesto-conversazione.md));
  - fuori dagli orari dei tutori il tocco di un minore è rifiutato, e la pagina mostra la frase degli
    orari (`minori.fuori_orario`, come per la voce e lo scritto);
  - la lista aggiornata va solo allo schermo del tocco (`invia_a`), anche con le schede automatiche
    spente; la TV di casa non mostra la spesa spuntata al supermercato;
  - riuscita senza la lista nuova, la voce resta spuntata e non si ritocca (`aria-disabled`), finché una
    lista più recente non la toglie o la rimette («rimettilo» a voce: si tocca di nuovo). Senza un esito
    entro 30 s (`calliopeSchermo.spunta.attesaMs`) un timer vero lo dice com'è: «Calliope è occupata: la
    spunta arriva appena finisce» (il tocco è ancora nella coda del ciclo), e un altro tocco della stessa
    voce non rimanda niente. Un'eccezione nel ciclo manda comunque l'esito d'errore (seconda revisione);
  - nella storia il turno del tocco chiude con la conferma di Calliope, non detta (`detto_calliope`
    «muta» negli eventi);
  - limite noto: `Liste.ultimo_cambio` tiene in memoria l'ora dell'ultima voce tolta, quindi dopo un
    riavvio il pallino si accende solo per le aggiunte.

Prove: `prova_raccolte` (nuova, livello 1: tessere con servizi finti, pagina, `tocchi.prepara`, il
server vero, il ciclo con un `ToolRegistry` vero e le `Liste` su disco, rifiuti per voce, livello e
minore, gli eventi in ombra); `prova_telefono_schermo` e `prova_pc_pagina` (tessere coi conti, pallino,
pagina Liste, la spunta fino all'ingresso, attesa, aggiornamento, rifiuto, 409; tessere, spunte e
«‹ Le mie cose» nelle misure dei tocchi e del contrasto). Da provare sul vero: la spunta sull'iPhone al
supermercato (la rete lenta: l'attesa dura quanto il giro del ciclo, che aspetta la fine del turno a voce
in corso), il PC personale in Edge.

## Le mie cose: la pagina Agenda e i tasti del timer (28/10, issue #257, ramo `issue-257-agenda`)

Passo 2b del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 4.1 e § 4.6), parte di #241, epic #251, insieme alla #262 (il vincolo dei tocchi:
[sicurezza-politica](sicurezza-politica.md)). Analisi con file e righe nell'issue #257.

- **La pagina Agenda** (`#/cose/agenda`, `POST /api/raccolte` con `{raccolta: "agenda"}`,
  `raccolte._pagina_agenda`): una scheda `timer` per ogni timer di casa ancora da suonare, in ordine di
  scadenza, poi tre schede `promemoria` «Oggi», «Domani», «In settimana» con i promemoria e gli
  appuntamenti della persona (chiavi `agenda:<persona>:<giorno>`, così non sostituiscono la scheda di tutta
  l'agenda). La vista per giorno è lato server, `agenda.per_giorno` ([memoria-agenda-liste](memoria-agenda-liste.md));
  la tessera usa la stessa. Le schede sono quelle che esistono: `DISEGNA.promemoria` impara la frase del
  vuoto («Niente oggi.») e «e altre N più avanti», `schede.timer` porta chi l'ha messo (`chi`, da
  `owner_name`; un timer di un ospite non ce l'ha), che la pagina scrive («messo da Bianca») solo sugli
  schermi personali. Tutto in `textContent`.
- **I tasti del timer** («+1 minuto» e «Ferma»): nella scheda del timer, solo sugli schermi personali con
  le sezioni (telefono e PC personale), in Adesso e nella pagina Agenda, su una scheda con un timer solo e
  ancora attivo. Alti e larghi almeno 44 px, con il nome del timer nell'etichetta per chi non vede
  («+1 minuto al timer per la pasta»: comincia col testo visibile, WCAG 2.5.3). La pagina manda `{tocco: "timer_piu" | "timer_ferma",
  chiave}` con la chiave della scheda (`timer:<id>-<creazione>`); `tocchi.prepara` controlla che il timer
  ci sia ancora, sia un timer (di casa: gli altri tipi dell'agenda sono personali) e abbia la stessa
  identità (409 «Questo timer non c'è più: è già suonato o è stato fermato.»). Nel ciclo diventano
  `timer_imposta` con `cambia` «aggiungi» e «1 minuto», e `agenda_annulla`, con il **bersaglio** nel
  contesto dei tool (`ToolContext.tocco_bersaglio`, lo imposta solo il ciclo): i due tool cambiano quel
  timer invece di sceglierlo dal testo. Senza, con due timer senza nome («di 5 minuti», «di 10 minuti»)
  `Agenda.find` ripiega sull'ultimo messo, e «+1 minuto» toccato sul primo cambiava il secondo. Se il
  timer suona mentre il tocco aspetta nella coda del ciclo, il tool risponde «non c'è più» e non avvia un
  timer nuovo al suo posto (a voce, con `cambia` e nessun timer da cambiare, lo avvia e lo dice).
- **Attesa ed errori** come nella spunta: `aria-busy` sui due tasti, quello toccato col bordo
  dell'accento, «Aggiungo un minuto…» o «Fermo il timer…» nella regione `role="status"` della scheda; la
  scheda aggiornata (stessa chiave: «+1 minuto» allunga il conto, «Ferma» la fa diventare «annullato
  alle …») arriva allo schermo del tocco prima dell'esito, che chiude l'attesa; un rifiuto o un errore
  HTTP libera i tasti e dice il motivo accanto; senza esito entro 30 s «Calliope è occupata: il timer
  cambia appena finisce», e un altro tocco su quel timer non parte.
- Scelta: una raccolta con la pagina mostra ciò che dà il server. Un timer finito (o una scheda che il
  server non ha più) non è nella pagina Agenda, e «Apri» da Adesso porta alla pagina senza quella scheda;
  prima il timer scaduto restava nel gruppo Agenda di Le mie cose, ora nascosto sotto la pagina.
- Cache del service worker `calliope-telefono-pagina-v11` (era v10).
- **Dalla revisione della PR #265**:
  - la scheda pubblica del risultato di un tocco (il timer dopo «+1 minuto» o «Ferma») va dove va
    quando lo stesso tool parte dalla voce (`hub.invia` dalla stanza dello schermo del tocco), più allo
    schermo del tocco e agli altri schermi personali della persona anche con le schede automatiche
    spente (`Ciclo._scheda_pubblica_del_tocco`). Prima solo lo schermo del tocco: la TV della cucina
    continuava il conto di un timer fermato e diceva «Finito» un minuto prima. Le schede di casa e
    personali (la lista) restano solo allo schermo del tocco, come deciso nella PR #261 *[storico
    per «dove va quando lo stesso tool parte dalla voce» fino al 28/10 sera: ora `Schermi.aggiorna`,
    sezione «Le schede del tocco»]*;
  - una corsia nuova nasce col contesto dei tool pulito (`main.contesto_corsia`): niente bersaglio,
    proposta in sospeso, «sì» già dato o gioco della corsia principale;
  - un tocco del timer senza bersaglio è rifiutato (`Tocco.bersaglio`, regola `tocco_senza_bersaglio`).

Prove: `prova_agenda_pagina` (nuova, livello 1: il vincolo, la vista per giorno ai bordi, i tasti in
`prepara`, il ciclo con un `ToolRegistry` vero e l'`Agenda` su disco, il server vero);
`prova_telefono_schermo` e `prova_pc_pagina` (la pagina Agenda dalla tessera, i tasti che mandano il tocco
giusto col bersaglio, attesa, aggiornamento, rifiuto, 409, i tasti in Adesso; i tasti nelle misure di clic
e contrasto); `prova_raccolte` adattata (la tessera Agenda ha la pagina; i rifiuti del registro provati col
vincolo spento, come seconda linea). Da provare sul vero: i tasti sull'iPhone in cucina mentre Calliope
parla (il tocco aspetta la fine del turno), il PC personale in Edge.

## Le mie cose: le pagine Lavori e programmi, Cassetto e Giochi (28/10, issue #258, ramo `issue-258-lavori-cassetto-giochi`)

Passo 2c del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 4.5, 4.7, 4.10), parte di #241, epic #251. Le tre pagine leggono soltanto, dai servizi e con i permessi
della voce; nessun tocco nuovo (prima va risolta la #266): le azioni sono quelle che le schede hanno già,
con le loro API (i tasti del cassetto a `POST /api/cassetto`, i giochi a voce e con `/api/gioco`).

- **Lavori e programmi** (`#/cose/lavori`, `raccolte._pagina_lavori`): lo sviluppo aperto e i sospesi della
  persona (`Sviluppi.corrente` e `sospesi`, la scheda `sviluppo`), i suoi lavori in coda, in corso o fermi a
  una domanda (dal più recente), i suoi programmi (`esecuzione`, gli ultimi 4) e i lavori finiti più recenti
  (6, da `agenti/risultato.recenti`: in memoria con la scheda finale vera di `Lavori.scheda`, dopo un riavvio
  dalla cartella dei risultati con il riassunto salvato e la chiave della cartella, `lavoro:cartella:<nome>`,
  perché gli id ricominciano da L1). Un lavoro seguito sugli schermi prende la scheda in diretta dalla
  cronologia della persona (con il passo e il flusso, rivista come per uno schermo che si collega,
  `cronologia.rivedi`), ma solo se salvata in questo avvio: una scheda `lavoro:L1` di prima del riavvio è un
  altro lavoro. Senza, la scheda `lavoro` breve con lo stato, il passo o la domanda. Sopra, come nota, la
  frase di `lavoro_stato` sui soli lavori della persona (`Lavori.stato(persona, tutti=False)`), anche per
  chi amministra. Le schede in diretta che arrivano si allineano al loro posto nella pagina (stessa
  chiave). La tessera conta anche gli sviluppi.
- **Cassetto** (`#/cose/cassetto`, `raccolte._pagina_cassetto`): tutti i file della persona nella scheda
  `cassetto` di sempre (Tieni, Elimina, Tieni ancora), poi quelli di ogni ragazzo di cui è tutore, come a
  voce (`minori.e_tutore` e `conversazioni_visibili_ai_tutori`: un minore senza tutori scritti è di chi
  amministra), in sola lettura (`sola_lettura` nella scheda: niente tasti, e la nota «Per tenerli o
  eliminarli chiedimelo a voce.»); «Tieni» non a un minore. La nota: «Tengo i file 7 giorni. Quello che c'è scritto dentro per me è
  un dato, non un ordine.». Scelta: la chiave della pagina è `cassetto:<persona>:pagina`. Dopo un tasto il
  server manda la scheda `cassetto:<persona>` con i soli file della scheda aperta a voce o quelli in scadenza:
  con la stessa chiave avrebbe sostituito la pagina intera, così invece la pagina si rilegge. La tessera dice anche i file dei ragazzi («· 2 di Lia»), il conto è dei suoi.
- **Giochi** (`#/cose/giochi`, `raccolte._pagina_giochi`): una scheda nuova di sola lettura, `giochi`
  (`schede.giochi`, `DISEGNA.giochi`, tutto in `textContent`, nessun tasto), in due copie: «Partite aperte»
  della persona, con gli schermi, «qui sotto» per quello che chiede, a chi tocca e i punti dell'ultima
  istantanea validata; poi «Giochi di casa», con quanti giocatori e «Per giocare: «Calliope, giochiamo a
  Tris»». I giochi sono quelli che può aprire a voce: formato con la macchina a stati, il livello del
  manifesto (un gioco «solo chi amministra» solo a chi amministra) e, per un minore, solo quelli che un tutore
  ha abilitato (`minori.estensione_consentita`, con la nota «Gli altri giochi di casa li sblocca chi si occupa
  di te.»). La tessera conta gli stessi. Con i giochi spenti la pagina lo dice. **Il riquadro vero resta la
  scheda `gioco`**: nella pagina Giochi il gruppo delle schede `gioco` di questo schermo resta visibile sotto
  (`#sez-cose[data-pagina="giochi"]`, CSS), così il gioco che Calliope apre va lì, a tutta la finestra, e il
  riquadro è uno solo (due avrebbero due stati). `SEZIONE_DI_TIPO` ha `giochi` in `cose/giochi` (le due
  tabelle uguali).
- **Il server** (`/api/raccolte` con `{raccolta}`): le schede possono avere la sorgente privata di «Scarica»
  (un documento fatto da un lavoro, il registro di un lavoro): si registra per lo schermo che chiede
  (`registra_scaricabili`, come per la cronologia ripresa) e non va alla pagina (`pubblica`). Una pagina il cui
  servizio solleva dà 503 «Non riesco a leggere questa pagina» e una riga `[SCHERMI] pagina «…» non letta`.
  `raccolte.pagina` riceve lo schermo (per «qui sotto»).
- Cache del service worker `calliope-telefono-pagina-v12` (era v11).
- **Dalla revisione della PR #267**:
  - la nota della pagina Lavori dava a chi amministra (`tutti=prof.admin`) il titolo, il nome e la domanda
    dell'agente dell'ultimo lavoro in attesa di tutta la casa, minori compresi, e copriva la domanda del suo
    lavoro. Ora è `tutti=False` sempre (questo resta vero). *[storico, fino al 28/10 sera: «dallo schermo lo
    scritto vale al più familiare, e il cruscotto non dà i titoli degli altri. Vedere i lavori di tutti
    vorrebbe una decisione scritta, e semmai solo conti e stati come nel cruscotto». La decisione c'è (Dario,
    28/10): chi amministra vede i lavori degli altri in una sezione a parte, vedi «La pagina Documenti» qui
    sotto]*;
  - le schede finali dei lavori finiti si costruiscono una volta (`raccolte._FINITI`, per lavoro, stato,
    fine e data della cartella): `Lavori.scheda` rilegge dal disco fino a 8 file interi, e la pagina si
    rilegge ogni 60 s;
  - nelle partite «a chi tocca» e i punti vengono dal posto della persona (quello di questo schermo, se c'è)
    o da quello che tiene la partita: con la tela ogni riquadro ha il suo motore;
  - i file del figlio in sola lettura (i tasti davano sempre 403 dallo schermo);
  - un lavoro di estensione finito ha la scheda di revisione «Estensione da approvare» solo se la sua
    versione è ancora la candidata da approvare; poi la scheda breve;
  - una raffica di schede di Le mie cose dà una rilettura sola delle tessere e della pagina aperta, 1,5 s
    dopo la prima e al più una ogni 10 s (`raccolteDopoSchede` in `sezioni.js`); la scheda che la pagina ha
    già si allinea subito. Prima una scheda che la pagina non aveva la rileggeva ogni volta, e le schede in
    diretta di un lavoro (ogni pochi secondi) rileggevano tessere e pagina a ogni raffica: si arrivava al
    limite di 30 letture al minuto;
  - la tessera e la pagina chiamano `Sviluppi.corrente`, che dopo `sviluppo_sospendi_min` senza parlarne
    sospende lo sviluppo, salva e manda la scheda (come il ricostruttore della ripresa): con Le mie cose
    aperta, quindi, lo sviluppo si sospende allo scadere del tempo e non alla frase dopo. Non provato con lo
    `Sviluppi` vero (la prova ne usa uno finto).
- Da guardare: i finiti annullati o interrotti da un riavvio non sono nella pagina (solo nella frase della
  nota, come a voce); il cassetto mostra al più 12 file per scheda («e altri N»), come la scheda della voce.

Prove: `prova_pagine_cose` (nuova, livello 1: le tre pagine con i servizi veri o finti, permessi, servizi che
mancano, il server vero); `prova_telefono_schermo` e `prova_pc_pagina` (le tre pagine dalle tessere, il lavoro
in diretta che si allinea, «Tieni ancora» con la pagina che resta intera, i giochi di casa, il gioco uno solo
e visibile sotto la pagina Giochi; contrasto e niente fuori a 1440×900 e 700×900); `prova_raccolte` adattata
(le tessere con la pagina, una pagina guasta 503). Da provare sul vero: la pagina Lavori sulla DGX con un lavoro
in corso (il flusso nella scheda della pagina), il cassetto della tutrice sull'iPhone.

## Le mie cose: la pagina Documenti, i documenti sul telefono e chi amministra (28/10, issue #259, ramo `issue-259-documenti`)

Passo 2d del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 4.8), parte di #241, epic #251. Nessun tocco nuovo (#266): la pagina legge e scarica soltanto.

**Decisioni di Dario (28/10, chi amministra).**
1. *Il telefono deve poter ricevere i documenti*: con la pagina ogni documento si ritrova e si scarica in
   ogni momento, non solo se lo schermo era aperto quando è arrivata la scheda.
2. *Chi amministra vede anche i documenti e i lavori degli altri*, nelle pagine Documenti e Lavori e
   programmi: i documenti fatti da Calliope per ogni persona di casa (minori compresi), l'archivio di casa
   senza il filtro dei personali altrui, i lavori, gli sviluppi e i programmi degli altri. Ognuno dice di chi
   è. Gli altri continuano a vedere solo i propri, coi permessi della voce; gli ospiti e i conoscenti mai
   niente. **A voce non cambia nulla**: `documento_leggi`, `lavoro_stato` e i permessi di `puo_vedere`
   restano com'erano (dallo schermo lo scritto vale al più «familiare»). Dario ha confermato in modo
   esplicito (commento sulla #259, 28/10) che dalla pagina chi amministra vede **tutto, anche i documenti
   sensibili degli altri** (referti, documenti d'identità).

- **La pagina** (`#/cose/documenti`, `raccolte._pagina_documenti`), a gruppi (`gruppo` nella scheda: la
  pagina scrive il titolo sopra la prima scheda del gruppo, `h3.gruppo-pagina`, solo testo):
  - «Fatti da Calliope per te»: gli ultimi 8 di `documenti/servizio.Archive.recenti`, nella scheda
    `documento` di sempre rifatta dal JSON dell'archivio (anteprima da leggere, «Scarica» in MD, PDF, Word o
    Excel col meccanismo `_scarica`): si scarica anche se il file è finito sul portatile o è rimasto sul
    server. Un minore li vede come a voce (`documento_leggi`): con il preset «documenti: no» (fino a 10 anni)
    no;
  - per chi amministra, «Fatti da Calliope per Bianca» e così per ogni persona (`Archive.recenti_di_tutti`,
    gli ultimi 8 per persona), con `di` («Di Bianca» nella scheda);
  - «Archivio di casa»: una scheda nuova, `archivio` (`schede.archivio`, `DISEGNA.archivio`), una per tipo
    (Bollette, Ricevute e fatture, Contratti, Polizze, Garanzie, Referti, Documenti d'identità, Manuali, Altri
    documenti), una riga per documento con nome, data, importo, di chi è (la cartella della persona, gli
    intestatari, o «Di casa») e «Scarica» del file originale; al più 20 righe per tipo («E altri N:
    chiedimeli a voce.»). I permessi sono quelli della voce: `Chi("familiare", …)` con
    `Archivio.documenti` (`puo_vedere`), mai la zona grigia (lo schermo personale è suo); per chi amministra
    `Chi("amministra")`, cioè tutto (decisione 2); per un minore niente (i tool dell'archivio sono in
    `minori._UFFICIO`), con la nota «L'archivio dei documenti di casa per te no.». `SEZIONE_DI_TIPO` ha
    `archivio` in `cose/documenti` in tutti e due i posti, `NOMI_TIPO` «Archivio di casa»;
  - il nome di un documento dell'archivio viene dai dati estratti (l'oggetto di una ricevuta entra nel
    nome): è un dato non fidato, scritto con `textContent`, mai HTML (provato con un `<img onerror>`).
- **La ricerca**: una casella nella pagina (`#pagina-cerca`, solo nelle pagine che la hanno, oggi i
  Documenti) e `POST /api/raccolte/cerca` `{raccolta, testo}` → `{schede, nota}`, in sola lettura
  (`raccolte.cerca`): i documenti fatti da Calliope per parole del titolo (della persona, di tutti per chi
  amministra) e l'archivio con `Archivio.cerca` e lo stesso `Chi` della pagina. Solo da uno schermo
  personale, 20 al minuto per schermo, al più 120 caratteri; il testo cercato non va nel registro (i
  documenti di casa sono dati personali, come i tool `riservati`). La pagina tiene la ricerca finché la si
  cambia o si tocca «Tutti»; le riletture rifanno la ricerca.
- **«Scarica» per i file dell'archivio** (prima non c'era): il formato `originale` di `scarica.py`, solo
  delle estensioni che l'archivio legge (`ORIGINALI`: PDF, immagini, docx, txt; un'altra diventerebbe
  `.bin` con `application/octet-stream` e non si offre), con la sorgente `file_fn` che al clic rifà i
  permessi sul profilo com'è adesso (`Archivio.documento_visibile`) e legge il file dentro
  `archivio_cartella` (`Archivio.file_di`: mai fuori dalla cartella, mai oltre `archivio_max_mb`). Le
  sorgenti per riga stanno in `_scarica_voci` (`registra_scaricabili`), una chiave per riga
  (`archivio:file:<id>`); le voci ricordate per «Scarica» passano da 64 a 400, **per schermo** (vedi la
  revisione della PR #268 qui sotto).
- **Lavori e programmi per chi amministra** (`raccolte._lavori_degli_altri`): in coda alla pagina, per ogni
  altra persona di casa (minori compresi) gli sviluppi, i lavori in coda, in corso o fermi a una domanda, i
  programmi (2) e gli ultimi 3 finiti, in schede `lavoro` brevi con titolo, stato, domanda («aspetta la
  risposta di Bianca») e `di`, sotto «Lavori di Bianca». Chiavi `altrui:…`: le schede in diretta degli altri
  non arrivano allo schermo di chi amministra, e nessuna scheda mandata dopo le sostituisce; la pagina si
  rilegge. La nota resta `Lavori.stato(persona, tutti=False)`, così la sua domanda non viene coperta.
- **La tessera Documenti col servizio vero**: chiamava `recenti` sul servizio `Documenti`, che non l'ha (è
  di `Documenti.archive`), quindi sulla DGX diceva sempre «non disponibile» (le prove usavano un servizio
  finto); e `modificato` è un tempo in secondi, non una data ISO, quindi l'ultimo cambiamento non si leggeva.
- **Dalla seconda revisione della PR #267** (primo commit del passo): la pagina Cassetto si rilegge subito
  dopo un tasto riuscito (evento `calliope:cassetto`: prima aspettava la raffica o i 60 s); un lock su
  `_FINITI`; la chiave delle schede finite guarda data e dimensione dei file del risultato, non solo la
  cartella (un file riscritto con lo stesso nome non la cambiava); il cassetto vuoto di un figlio dice «Il
  cassetto è vuoto.» (la nota «chiedimelo a voce» solo con dei file).
- Cache del service worker `calliope-telefono-pagina-v13` (era v12).
- **iPhone, a secco** (#59 resta aperta): `Content-Disposition: attachment` con `filename*` in UTF-8 e un
  nome di riserva ASCII senza accenti («referto citta.pdf», prima «referto citt_.pdf»), il nome in forma NFC,
  i tipi giusti per Safari (`application/pdf`, `image/jpeg`, i tipi Office), `nosniff` e CSP `sandbox` come
  prima; la pagina scarica con un `<a download>` sullo stesso indirizzo, e il gettone vale 3 richieste (il
  download che riprova, l'anteprima di iOS). Da provare sull'iPhone vero nella PWA: che il file si salvi in
  File e non apra una vista senza «indietro», il nome con gli accenti, il Markdown (`text/markdown`, che
  Safari potrebbe mostrare invece di salvare).

Prove: `prova_pagina_documenti` (nuova, livello 1: chi vede cosa per chi amministra, un familiare, un minore
di 15 e uno di 10 anni; l'archivio coi permessi; la ricerca con testo ostile; servizi che mancano o
sollevano; «Scarica» con nomi, tipi e permessi al clic; il server vero con la ricerca a 20 al minuto e lo
scaricamento vero; l'annuncio col telefono abbinato ma chiuso); `prova_pagine_cose` (i lavori degli altri
per chi amministra, minori compresi, mai a un familiare; la cache delle schede finite col lock e i file
riscritti; il cassetto vuoto del figlio); `prova_documenti` (le frasi col telefono abbinato ma chiuso);
`prova_telefono_schermo` e `prova_pc_pagina` (la pagina vera: gruppi, nome ostile come testo, «Scarica» di
una riga, ricerca e «Tutti», contrasto e clic a 1440×900 e 700×900; la rilettura subito dopo un tasto del
cassetto); `prova_raccolte` adattata (la tessera Documenti ha la pagina; «presto» è lo Studio). Da provare
sul vero: lo scaricamento nella PWA dell'iPhone (#59), la pagina con l'archivio vero della DGX (quanti
documenti per tipo, il tempo della pagina).
- **Dalla revisione della PR #268** (da unire, con note; tutte sistemate prima di unire):
  - *La frase deve essere vera.* La pagina mostra gli ultimi 8 documenti della persona e, se ce ne sono di
    più, lo dice («gli altri li trovi con «Cerca»»); la ricerca guarda tutti i documenti fatti da Calliope
    della persona (di tutti per chi amministra; tetto `CERCA_TRA`, 5000), non più gli ultimi 50.
    `documento_leggi` «mostra» con lo schermo chiuso dice «cercando «titolo»» se il documento non è fra gli
    ultimi 8.
  - *Né «telefono» né «PC»*: la frase dice «in Le mie cose, alla voce Documenti». Gli schermi abbinati non
    hanno un tipo affidabile (nome e stanza li sceglie chi abbina), quindi niente deduzioni.
  - *Voci di «Scarica» per schermo* (`Scaricamenti._voci`: schermo → voci, `MAX_VOCI` 400 ciascuno): prima il
    tetto era unico, e la pagina riletta su uno schermo (fino a ~180 righe dell'archivio) toglieva le voci
    dell'altro, che al clic davano 404.
  - *Ricerca con sole parole vuote* («di», «è», una lettera): «Non c'è niente da cercare: scrivi una parola
    più lunga.», non i 20 più recenti come «trovati».
  - *Tessera Documenti*: il conto vero (`Archive.conta`, non al più 50); per chi amministra lo stato dice
    «N documenti tuoi · M degli altri», e il conto resta dei suoi.
  - *File originale*: nome e tipo dal file letto davvero (`file_fn` dà byte ed estensione), non
    dall'attributo del documento (con più copie il primo file buono può essere un altro); riletto dal disco
    a ogni uso del gettone, che non tiene più fino a `archivio_max_mb` in memoria per 180 s.
  - *Peso della pagina*: i nomi delle persone (`_nomi_nodi`) solo per le righe mostrate.
  - **Limiti noti** che restano: per costruire la pagina `Archivio.documenti(chi)` legge e filtra tutto
    l'archivio a ogni lettura (i permessi si decidono in Python, quindi niente `LIMIT` in SQL per tipo), e chi
    amministra riceve fino a 8 schede `documento` complete per persona; con un archivio di migliaia di
    documenti va misurato sulla DGX. *[storico, fino al 28/10 sera (passo 2e, #260): «Le voci di «Scarica»
    di uno schermo revocato restano in memoria fino al riavvio»: ora se ne vanno, vedi la sezione qui sotto]*
  - Prove nuove in `prova_pagina_documenti`: 61 documenti (la nota, la ricerca che trova il più vecchio, la
    tessera che li conta tutti), sole parole vuote, la tessera di chi amministra, le voci di due schermi,
    l'originale riletto col tipo vero, `Archivio.file_di` mai fuori dalla cartella (`..`, `..\`, percorso
    assoluto, giunzione NTFS creata con `mklink /J`) né oltre `archivio_max_mb`; in `prova_documenti`
    «mostramelo» di un documento più vecchio degli ultimi 8.

## Le mie cose: la pagina Ufficio, solo a chi amministra (28/10 sera, issue #260, ramo `issue-260-ufficio`)

Passo 2e del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 4.9), parte di #241, epic #251. Decisione del 28/10: **solo sugli schermi personali di chi amministra**.
Nessun tocco nuovo (#266): la pagina legge e scarica soltanto; emettere, annullare e cambiare la rubrica si
fa a voce, e l'invio allo SdI resta a mano.

- **Primo commit, dalla seconda revisione della PR #268** (commento sulla #260):
  - *La ricerca per titolo* dei documenti fatti da Calliope confrontava solo le parole di 4 lettere o più
    (`provenienza.parole`) e si fermava ai primi 20 dal più recente: un titolo di parole corte («CV», «Tre
    re») non si trovava mai, e con una parola comune il documento più vecchio restava fuori. Ora le parole
    sono quelle che non sono vuote (`_parole_utili`: niente `_VUOTE` né lettere sole; una cifra sola sì,
    «fattura 3»), e i risultati vanno per pertinenza (`_punti_titolo`: una parola uguale 1, l'inizio di una
    parola di almeno 3 lettere 0,5), poi dal più recente.
  - *Il nome in «Scaricato: …»* veniva dall'estensione registrata del documento, il file salvato da quella
    del file letto davvero: con più copie potevano essere diversi. La sorgente ha ora `estensione_fn`, che
    guarda il file che `file_fn` leggerà senza leggerlo, già alla richiesta del gettone (404 subito se non
    c'è più o non è più visibile).
  - *Gli schermi revocati*: `Scaricamenti.dimentica` (da `Schermi.avvisa_revoca`) e `tieni_solo` (a ogni
    rilettura di `Schermi.abbinati`, anche dopo una revoca da terminale, cioè da un altro processo) tolgono le
    voci di «Scarica», i gettoni e il conto delle richieste.
- **La pagina** (`#/cose/ufficio`, `raccolte._pagina_ufficio`): 404 a tutti tranne chi amministra (come le
  raccolte non visibili; mai a un minore, anche col segno di chi amministra), ricontrollato dentro la pagina
  e la ricerca e non solo da `visibili`. A gruppi:
  - «Documenti dell'ufficio»: una scheda nuova, `ufficio` (`schede.ufficio`, `DISEGNA.ufficio`), per serie
    (Fatture, Note di credito, Preventivi, DDT, poi le serie dei modelli Word e PowerPoint), da
    `Numeratore.elenco(con_dati=True)`, dalla più recente, al più 20 per serie («E altri N: cercali con
    «Cerca».»). Per riga il numero («Fattura 12/2026»), data, cliente (il contatto della rubrica salvato nei
    dati all'emissione), importo, lo stato («Emessa», «Annullata: motivo», «In preparazione») e «Scarica»
    di ogni file generato (PDF di cortesia, XML della FatturaPA, Word, PowerPoint);
  - «Rubrica»: `Rubrica.visibili` di chi guarda (quelli di casa e i suoi personali, non quelli personali
    degli altri), per nome, al più 60, con tipo, partita IVA o codice fiscale, luogo, email, PEC, telefono e
    «Di casa» o «Solo tua»;
  - la nota «L'invio allo SdI lo fai tu, a mano: io preparo i file.»
- **L'importo** è quello del programma: dal 28/10 `Ufficio._scrivi` salva nei dati del numero `_totale` (e
  `_da_pagare` con la ritenuta). I numeri emessi prima non l'hanno e la pagina non lo rifà (i conti
  dipendono dall'emittente e dalle aliquote di quel giorno): la riga resta senza importo. I DDT non ne hanno.
- **I dati dei clienti sono dati non fidati** (detti a voce o scritti in un modulo, e il motivo
  dell'annullo): solo testo, `textContent`, mai HTML (provato con un `<img onerror>` nel nome e nel motivo).
- **«Scarica»** col formato `originale` del passo 2d; `ORIGINALI` ha anche `xml` (`application/xml`, come
  allegato, con `nosniff` e la CSP `sandbox`) e `pptx`. Al clic, e già alla richiesta del gettone, la
  sorgente rifà i controlli sul profilo com'è adesso (chi amministra ancora, non minore), rilegge il registro
  dei numeri e serve solo un percorso che è ancora fra i file di quel numero, un file vero sotto i 50 MB. Il
  percorso viene dal registro scritto da Calliope, mai da chi chiede. Chiavi
  `ufficio:file:<serie>:<anno>:<numero>:<i>`.
- **La ricerca** (`POST /api/raccolte/cerca` con `raccolta: "ufficio"`, `raccolte._cerca_ufficio`), con le
  regole di quella dei Documenti: i documenti per tipo e numero (che contano il doppio: «fattura 1» è la
  numero 1, non quella di un cliente con un «1» nel nome), cliente e titolo; i contatti per nome, comune,
  partita IVA e codice fiscale; al più 20 per gruppo, per pertinenza e poi dal più recente. La casella ha il
  suggerimento della pagina (`SUGGERIMENTO_RICERCA` in `sezioni.js`: «Cerca: cliente, numero, comune…»).
- `SEZIONE_DI_TIPO` ha `ufficio` in `cose/ufficio` nei due posti, con il suo `data-posto` nelle due pagine;
  `NOMI_TIPO` «Ufficio». Cache del service worker `calliope-telefono-pagina-v14` (era v13).
- **Servizi**: senza l'ufficio la pagina dice «L'ufficio non è attivo qui» (come le altre pagine senza il
  loro servizio); il registro dei numeri o la rubrica che sollevano danno 503, la tessera «non disponibile»,
  e il testo cercato non va nel registro.

Prove: `prova_pagina_ufficio` (nuova, livello 1: la pagina coi `Numeratore` e `Rubrica` veri, gli stati,
l'importo e i numeri senza, più di 20 per serie, la rubrica di chi guarda; un familiare, un minore anche col
segno di chi amministra e un ospite 404 su pagina e ricerca; la ricerca con parole corte, vuote e ostili;
servizi che mancano o sollevano; «Scarica» di PDF e XML con nomi uguali, permessi al clic, file tolto o fuori
dal registro; il server vero); in `prova_pagina_documenti` i tre punti della revisione; in `prova_ufficio` il
totale nei dati del numero; `prova_telefono_schermo` e `prova_pc_pagina` (la pagina vera: gruppi, nome ostile
e motivo come testo, l'annullata segnata, «Scarica XML» col nome del file salvato, niente fuori, ricerca,
contrasto e clic a 1440×900 e 700×900); `prova_raccolte` adattata; `prova_sezioni` vuole il posto `cose/ufficio` nella pagina. Da provare sul
vero: la pagina con le fatture vere della DGX e lo scaricamento dell'XML nella PWA dell'iPhone (#59).
*[storico, fino alla revisione della PR #269: «Sul telefono «Tutti» non si prova nella pagina Ufficio: la
prova arriva alle 30 letture al minuto»]*
- **Dalla revisione della PR #269** (da correggere; tutto sistemato sullo stesso ramo):
  - *Bloccante: la cifra sola.* «3» o «di 3» passavano `_parole_utili` (dal primo commit una cifra vale), ma
    `Archivio.cerca` tiene solo le parole di 2 lettere o più: senza parole non filtrava, e la pagina
    Documenti diceva «Trovati 20» coi documenti più recenti dell'archivio. Ora l'archivio si interroga solo
    se c'è una parola che usa davvero; i documenti fatti da Calliope confrontano la cifra intera («3» trova
    «Verbale 3», non «Verbale 13»).
  - *Le letture di `/api/raccolte`* passano da 30 a 60 al minuto per schermo (`LETTURE_AL_MINUTO`): con 30
    chi sfoglia le raccolte, più le riletture delle tessere (due per `aggiornaRaccolte`), arrivava al 429 e
    la pagina restava vuota. La ricerca resta a 20 e i tocchi a 30.
  - *Una frase per limite*: le letture «Troppe richieste in poco tempo: riprovo fra qualche secondo.», la
    ricerca «Troppe ricerche in poco tempo…», i tocchi come prima; ogni 429 ha `Retry-After` e `riprova_s`
    (i secondi finché si libera un posto).
  - *La pagina riprova da sola*, una volta, dopo `Retry-After` (al più 60 s), e intanto resta com'era: una
    rilettura della stessa pagina non tocca le schede; aprendo un'altra pagina quelle di prima restano nel
    contenitore, nascoste e con `aria-busy`, finché arriva la prima risposta.
  - *La chiave di «Scarica»* dei file dell'ufficio mai oltre gli 80 caratteri a cui `schede.ufficio` la
    taglia (oltre, la serie diventa un'impronta): tagliata non era più quella registrata, e dava 404.
  - *Precedenza in «Scarica»*: `hub.registra_pagina` registra le voci di una pagina dall'ultima scheda alla
    prima e dall'ultima riga alla prima, così oltre `MAX_VOCI` le prime della pagina (le fatture, i documenti
    più recenti) sono le ultime a perdere «Scarica».
  - *La cache di `Schermi.abbinati`* legge la versione prima dell'elenco: letta dopo, un abbinamento fatto
    nel mezzo lasciava per 5 s le righe vecchie con la versione nuova.
  - Prove: in `prova_pagina_documenti` «3», «di 3» e «7 e» (niente dall'archivio) e «3» che trova i titoli
    con la cifra; in `prova_raccolte` 60 letture, la frase e `Retry-After`; in `prova_pagina_ufficio` la
    chiave di una serie lunghissima e la precedenza oltre il tetto; in `prova_telefono_schermo` «Tutti» nella
    pagina Ufficio e un 429 finto che la pagina dice, senza svuotarsi, e riprova da sola.

## La Conversazione con le schede dentro, i filtri e la ricerca (28/10 sera, issue #242, ramo `issue-242-conversazione`)

Passo 3 del progetto [`2026-10-27-telefono-sezioni-e-studio`](../ricerche/2026-10-27-telefono-sezioni-e-studio.md)
(§ 4.2), epic #251. Analisi sul codice e alternative nel commento della #242. Nessun tocco nuovo (#266).

- **Le schede restano col turno** (alternativa B dell'analisi): `Brain._invia_schede` lega ogni scheda
  mandata in una risposta al messaggio della persona del turno (`_schede`, accanto a `_turno`), solo con
  l'identità certa (mai la zona grigia né un ospite); la stessa scheda di nuovo nello stesso turno sostituisce
  quella di prima, al più quattro. Anche la lista aggiornata da un tocco (`Brain.record_tocco`) e le schede
  del risultato di un modulo. `conversazione.turni` le porta nel `meta` del turno archiviato: stessa tenuta,
  stessa «dimentica», stessi permessi dell'archivio ([contesto-conversazione](contesto-conversazione.md)).
  Scartata l'unione per tempo con la cronologia delle schede: lì ci sono solo le personali (biblioteca,
  internet e calcolo sono pubbliche, la lista è di casa), e dopo 40 schede non resta niente.
- **Cosa resta** (`schede.per_conversazione`): una copia `storica` per i tipi di contenuto (biblioteca,
  internet, calcolo, testo, lista, timer, agenda, casa, documento), senza le chiavi «_», «Scarica» e
  scadenza, sotto i 16 kB (`CONV_SCHEDA_MAX`); un rimando (tipo, titolo, chiave, sezione) per i tipi vivi o
  pesanti (lavoro, programma, sviluppo, gioco, esercizi, cassetto, foto, file, modulo, avviso) e per una copia
  oltre il tetto; niente per la risposta scritta (è il testo del turno), la chat, il cruscotto, la voce nuova
  (parole di un ospite), archivio e ufficio (riservati). I testi passano da `oscura` come quelli del turno,
  le chiavi no (quella di un timer ha l'istante di creazione); un turno riservato non tiene le sue schede.
- **Il canale**: «a voce», «scritto», «con un tocco», «modulo» (`voce_chat`, `CANALI_CHAT`; uno sconosciuto
  vale «voce»). Il modulo inviato entra nella storia con il suo `_turno` (canale «modulo», lo schermo), prima
  si archiviava come detto a voce. Per il tocco e il modulo il luogo della conversazione (il satellite della
  voce) non vale. Nella pagina il tocco e il modulo sono un gesto al centro, senza le parentesi della
  storia, non una bolla «Tu». La trascrizione in Markdown ha il canale e, per turno, «*Scheda: Lista · …*».
- **La scheda piccola** dentro la risposta (`costruisciPiccola` in `schermo.js`): un `<button>` con il tipo e
  il titolo, sopra un'anteprima `inert` disegnata da `DISEGNA` del suo tipo con `compatta`, tagliata dal CSS.
  Un tocco apre la copia del turno a schermo intero (sul telefono nel suo strato, sul PC in quello di
  `apriInteroPC`, con una chiave sua: la lista di adesso resta un'altra scheda), segnata «com'era alle …»;
  le copie `storica` non hanno la spunta né i tasti del timer (manderebbero un tocco sullo stato di oggi), e
  il timer dice l'ora di fine invece del conto. Un rimando porta alla scheda nella sua sezione (`vaiA`) o, se
  non c'è più, alla sezione (`#/cose/lavori`).
- **Filtri e ricerca** dentro `DISEGNA.chat`, quindi uguali sul telefono, nella colonna del PC e a schermo
  intero: «Oggi» e «Ieri» (si escludono; un secondo tocco toglie il filtro), «Solo schede» (si somma),
  «Cerca» che apre la casella, «Tutto» che toglie filtri e ricerca, e una riga `role="status"` con l'esito
  («Ieri: 2 turni», «Nessun turno con queste parole.»). Senza filtri la vista è quella viva di prima; con un
  filtro i turni vengono da **`POST /api/conversazione`** (`Schermi.chat_filtrata` →
  `ArchivioConversazioni.chat_filtra`), e un turno nuovo entra solo se passa il filtro (oggi, solo schede;
  mai in una ricerca). Il server ha le regole delle raccolte: sessione, HTTPS fuori da questo computer, solo
  uno schermo personale, **solo i turni del suo proprietario** (il tutore non vede quelli del ragazzo, il
  ragazzo quelli del tutore, come la conversazione di prima), 60 letture e 20 ricerche al minuto con
  `Retry-After`. I giorni secondo l'ora di questo computer; la ricerca solo per parole (FTS5, ogni parola tra
  virgolette e per prefisso, tutte insieme): niente vettori, niente modello in più. Il testo cercato non va
  nel registro.
- **Sul telefono** la sezione Conversazione mostra la conversazione al posto del pulsante «La nostra
  conversazione» (`#conv-tel`, `disegnaChatTel` in `telefono.js`; l'evento «chatturni» ora anche lì): prende
  lo spazio che resta e scorre da sé, «Scarica Markdown» sotto i turni. L'elenco sotto («Altre schede») tiene
  solo le schede di conversazione che i turni non mostrano già (non le risposte scritte, non le schede dentro
  un turno: `fuoriDaCasa` di `sezioni.js`); in Adesso restano come prima. Sul PC la colonna a destra è la
  stessa scheda. La casella per scrivere resta quella di prima (`scrittura_consentita`): spenta fuori da una
  conversazione cominciata a voce. *[storico: dal 28/10, #301, la casella sta nella Conversazione al posto
  della riga della voce ed è sempre accesa sullo schermo personale]*
- Tutto in `textContent` (provato con `<img onerror>`, `<script>` e `<b>` nei turni e nella ricerca); CSP
  invariata. Cache del service worker `calliope-telefono-pagina-v15` (era v14).
- **Limiti**: con `eventi: attivo` (passo 3, acceso a mano; sulla DGX è in ombra) l'archivio lo scrive l'ombra
  dalla proiezione, e lì le schede non ci sono ancora (l'evento `scheda_mandata` ha solo tipo, chiave e
  titolo); i turni archiviati prima di oggi non hanno schede; «Oggi» senza ricerca legge al più 200 turni.

Prove: `prova_conversazione_schede` (nuova, livello 1: la copia per tipo e il tetto, Brain che lega la scheda
solo con l'identità certa e nel tocco, `turni` con oscura, riservato e `non_conservare`, i canali, il modulo,
`chat_filtra` con nove testi ostili, `/api/conversazione` con persona sbagliata, tutore e ragazzo, stanza,
401, 400, 413 e 429); `prova_cronologia_pagina` (il telefono: canali, gesto, schede piccole, copia a schermo
intero e gesto indietro, rimando, filtri, ricerca ostile, misure a 375×812 e 320×568, Scrivi spento);
`prova_pc_pagina` (la colonna a destra: schede piccole, copia nello strato, Ieri, ricerca, clic ≥ 44 px).
Da provare sul vero: lo spazio della conversazione sull'iPhone con la tastiera aperta nella ricerca, e i
filtri con la conversazione vera della DGX (molti turni con schede).
- **Dalla revisione della PR #271** (sullo stesso ramo):
  - *Bloccante: il riservato passava dalla scheda del turno dopo.* «Cosa dice il contratto?»
    (`archivio_cerca`, riservato) e poi «scrivimelo sullo schermo» (`schermo_mostra` con `cosa` risposta)
    mettevano il canone nel `meta` del secondo turno per 60 giorni. Ora una scheda si lega solo se il suo
    contenuto è conservabile quanto il turno: `Brain._invia_schede` segna `_riservata` (resta sul server)
    ogni scheda mandata in una risposta con un tool riservato (`last_private`: archivio, rubrica, ufficio,
    `stanza_cerca`, `conversazione_cerca`), e `hub.ultima` la ricorda col segno (`cosa` ultima);
    `schermo_mostra` segna le schede che ripetono la risposta di prima quando quella era riservata (`cosa`
    risposta e testo, da `risposta_precedente["riservata"]`); `per_conversazione` le scarta.
  - *Bloccante: la stima dei token.* `_tokens` non conta più `_schede` (le copie non arrivano al modello):
    un turno con un documento passava da 27 a 5 849 token stimati e la storia si tagliava prima.
  - *Foto e file del turno* non si legano (`manda_schede` segna `_conv` False): partono prima che la frase
    entri nella storia, e finivano sul turno di prima, magari d'un'altra persona.
  - *Peso verso le pagine*: copie al più 8 kB (erano 16), e intere solo negli ultimi 12 turni con schede
    (`alleggerisci`, nel benvenuto e in `/api/conversazione`); prima arrivano leggere (tipo, titolo, chiave,
    sezione), senza anteprima, e il dettaglio si chiede al tocco (`POST /api/conversazione` con
    `{turno, indice}`, solo dai turni del proprietario).
  - «com'era il 3 novembre alle …» quando la copia non è di oggi; il calcolo non passa da `oscura` (un
    risultato di dieci cifre diventava «******»), solo dai segreti del turno; `avviso` non è fra i rimandi
    (gli avvisi ai tutori non si legano mai); un turno arrivato dal vivo mentre si aspettava un filtro entra
    se lo passa.
  - *Dati d'altri nelle copie*: la lista e la casa sono dati della famiglia e restano 60 giorni
    nell'archivio di chi ha fatto la domanda; la «dimentica» di un altro familiare non le tocca (è la scelta
    dell'analisi della #242: la persona ha visto quella scheda nella sua conversazione). Dalla copia del
    timer si toglie chi l'ha messo (`chi`).
- **Dalla seconda revisione della PR #271**:
  - *Bloccante: il modulo.* Un tool riservato completato col modulo («prepara la fattura per Rossi» →
    `modello_compila`, o `anagrafica_salva`) legava al turno del modulo l'anteprima `documento` con cliente,
    voci e totali. Ora `moduli.completa` guarda lo spec del tool (`_tool_riservato`, nel dubbio sì): le
    schede del risultato prendono `_riservata` prima di partire e non si legano, e il turno del modulo ha
    `riservato` nel `_turno`, così nell'archivio la frase («Ho preparato la fattura… totale…») diventa
    «(risposta con dati riservati: non archiviata)» come per la voce. *Storico: prima di questo la frase del
    modulo si archiviava in chiaro, anche senza le schede.*
  - *Limite*: una scheda di un altro tool che riporta il testo di un turno riservato qualche turno dopo
    («fammi un documento con questi dati» due turni dopo, o `cosa` testo con un turno non riservato in
    mezzo) non è segnata, e la sua copia resta. È lo stesso limite della risposta del modello in quel turno,
    che si archivia in chiaro: il segno vale per il turno riservato e per quello subito dopo.

## Le schede del tocco: livello, stanza, conversazione (28/10 sera, issue #266, ramo `issue-266-toccabili`)

Le note della revisione della PR #265 (commento della #258), insieme all'elenco dei tool toccabili
([sicurezza-politica](sicurezza-politica.md)):

- **Livello del mittente**: la scheda pubblica del timer dopo «+1 minuto» o «Ferma» parte da `hub.invia`
  con il mittente del tocco, che aveva sempre «familiare» scritto nel codice. Ora ha il livello con cui il
  tool è stato chiamato: quello vero del proprietario, limitato come lo scritto da uno schermo personale
  (`current_level`: chi amministra vale «familiare»). Oggi il valore è lo stesso; cambia se cambia il
  tetto dello scritto.
- **Dove va la scheda aggiornata** (`Schermi.aggiorna`, dalla revisione della PR #270), provato con
  l'hub vero (`Schermi` con l'archivio su disco) e due stanze, cucina e salotto. Una scheda che c'è già
  (stessa `chiave`) si aggiorna sugli schermi a cui era andata, più quelli personali di chi tocca e lo
  schermo del tocco, anche con le schede automatiche spente. Il caso vero: il timer messo a voce in
  cucina e fermato dal telefono, abbinato con `--stanza telefono`. Prima l'aggiornamento seguiva la
  «stanza» telefono: la TV della cucina restava indietro e poi diceva «Finito», e la scheda arrivava
  anche al telefono di un altro familiare abbinato con la stessa «stanza». L'hub tiene una traccia
  leggera in memoria (`_dove`: chiave → schermi, al più 512 chiavi). Una scheda mai vista, per esempio
  dopo un riavvio, va come a voce: senza la stanza dello schermo va alla predefinita (`schermi_stanza`),
  senza quella a tutti, con la sua stanza va a quella. Uno schermo personale di un'altra persona la
  riceve solo se è lo stesso schermo che l'aveva già.
- **Il numero degli schermi si riusa** (seconda revisione della PR #270). La tabella ha `id INTEGER
  PRIMARY KEY` senza AUTOINCREMENT, e la revoca cancella la riga: dopo una revoca il prossimo schermo
  abbinato prende il numero più alto appena tolto. Una revoca fatta da terminale (`python -m
  calliope.schermi --revoca`, un altro processo) lasciava nell'hub la traccia `_dove`, la cronologia
  `_storia` e le pagine collegate col numero vecchio. Così «Ferma» dal telefono di Dario arrivava al PC
  nuovo di Bianca, e al collegamento il telefono nuovo di Bianca riceveva la scheda personale di Dario
  (questo secondo difetto c'era già prima della PR). Ora lo schermo si riconosce dal numero e
  dall'istante dell'abbinamento (`creato`); lo schema della tabella non cambia, quindi gli schermi già
  abbinati sulla DGX valgono.
  - **Rilettura dell'elenco.** Ogni volta che `abbinati()` lo rilegge, per i numeri che non ci sono più
    o il cui `creato` è cambiato toglie la cronologia, la traccia, le voci di «Scarica» e i posti nelle
    partite. Le pagine collegate dello schermo di prima ricevono «revocato».
  - **Sessioni.** Le sessioni del server tengono (numero, `creato`): la sessione di una pagina vecchia
    non vale per lo schermo nuovo. Se l'elenco in memoria non torna, il server lo rilegge una volta
    (`_schermo_sessione`). Anche il flusso controlla `creato` (`valido(sid, creato)`).
  - **Limite.** Come prima, una revoca da terminale arriva al processo di Calliope al più dopo i 5 s
    della cache dell'elenco, o subito al primo accesso dello schermo nuovo. In quei secondi lo schermo
    revocato vale ancora per sé, ma mai come lo schermo nuovo.
  - **Non toccati.** I contatori delle richieste per schermo del cruscotto e dello scritto (`_richieste`,
    `invii`): un numero riusato eredita al più il conteggio di un minuto.
- **`conv_archivio`** segue la conversazione del tocco: `Brain.contesto_conversazione` (lo stesso codice
  dell'inizio di una risposta) dopo `Corsia.turno` e dopo `record_tocco`, e anche per il modulo dallo
  schermo (`_modulo_dallo_schermo`). Prima restava quello della conversazione di prima fino alla risposta
  dopo.
- **Le schede della pagina Agenda sul telefono piccolo**: `una_per_una` misurava le schede delle sezioni.
  Ora porta in vista una per una, a 375×812 e 320×568, anche quelle che il server dà alla pagina (il
  promemoria di domani compreso). Per ognuna controlla che stia dentro la sezione, che non ci sia testo
  di lato né tagliato in basso, e il contrasto AA.
- Dalla revisione della PR #270, anche:
  - «+1 minuto» su un timer già finito ma non ancora suonato non lo allunga («Questo timer è già finito:
    suona fra un attimo, non lo allungo.»);
  - la spunta di «tutto.» (o «Tutti!») vale come «tutto» per `lista_togli`, quindi è 422 e non svuota
    la lista;
  - `TOCCHI` e `TOCCABILI` non si cambiano a runtime (`MappingProxyType`).

Prove: `prova_agenda_pagina` (l'hub vero con due stanze; il timer della cucina fermato dal telefono; le
schede mai viste; la traccia col tetto e gli schermi revocati; il livello del mittente; `conv_archivio`
per tocco e modulo; il timer finito; `TOCCHI` immutabile; il numero riusato dopo una revoca da un secondo `ArchivioSchermi`: «Ferma», il collegamento, la pagina vecchia e la sessione del server); `prova_raccolte` («tutto.»);
`prova_telefono_schermo` (la pagina Agenda a due dimensioni, col contrasto e il testo tagliato per
scheda).

## La miniatura della foto accanto alla frase nella Conversazione (28/10, issue #272, ramo `issue-272-miniatura-foto`)

Decisione di Dario del 28/10, dopo la revisione della PR #271 (che le aveva tolte: `_conv` False).

- **Legatura al turno giusto**: le miniature di foto e file partono (`Brain.manda_schede`, da
  `Ciclo._rispondi`) prima che la frase della persona entri nella storia. Restano in attesa (`_attesa`) e
  `Brain._lega_in_attesa`, chiamata quando il messaggio della persona entra in `_reply`, le lega a quel
  messaggio. Scelta invece del legame per id della foto: nessun cambio in `ciclo.py`, e la regola è la stessa
  per foto, file e pagine scansionate.
- **Quando non si legano**: con l'identità incerta (zona grigia, ospite) non entrano nemmeno in attesa; se
  quando entra la frase parla un'altra persona (`hub.mittente` di adesso, solo certo) si buttano; dopo
  `ATTESA_SCHEDE_S` (30 s) senza la frase (un errore, un'altra corsia ha risposto: ogni corsia ha il suo
  Brain) pure; un turno riservato le perde in `conversazione.turni` come le altre schede. Il segno
  `_riservata` di `last_private` non vale per loro (è ancora quello della risposta di prima). Una miniatura
  che parte dopo la frase (le trattenute di un minore) va alla frase di questo turno.
- **Le catture** chieste a voce (webcam, schermo: `pc_guarda`, `immagine_guarda`) sono schede del tool,
  dentro la risposta, e si legano come le altre al messaggio di chi le ha chieste.
- **Dati**: la copia della foto ha una miniatura sua, più piccola di quella dello schermo (`_mini`, lato
  144 px, JPEG qualità 55, fatta in `schede.foto` e tenuta sul server), mai la miniatura dello schermo né il
  file; oltre gli 8 kB di `CONV_SCHEDA_MAX` resta il solo rimando, senza i byte. Il file ha nome, tipo e
  dimensione, mai l'anteprima del testo né le note. Stessa tenuta (60 giorni) e stessa «dimentica» del turno.
  Vale anche per le catture di webcam e schermo, e dal 28/10 la foto intera si tiene 60 giorni nel
  cassetto: decisione [0034](../decisioni/0034-miniature-nella-conversazione.md) (*storico: fino al 28/10
  nessuna foto né miniatura andava su disco*).
- **La pagina**: la foto è una scheda piccola come le altre, con la miniatura nell'anteprima e a schermo
  intero (`DISEGNA.foto`, solo un data URL JPEG). Quello che vede il modello (`immagini_storia`) non cambia:
  le copie non arrivano al modello e non contano nella stima dei token.

Prove: in `prova_conversazione_schede` la copia della foto dentro il tetto e senza la miniatura dello
schermo, la miniatura troppo grande che diventa rimando, il file senza anteprima; la foto mandata con la
frase e quella mandata prima (in attesa), una miniatura che parte dopo la frase, la cattura della webcam
chiesta a voce, il cambio di persona in mezzo, la frase di molto dopo, l'identità incerta, il turno
riservato, una risposta riservata prima; in `prova_cronologia_pagina` la miniatura caricata nella
risposta del suo turno e aperta a schermo intero. Da provare sul vero: lo scontrino dal telefono.
- **Dalla revisione della PR #273**:
  - *Bloccante*: le catture di webcam e schermo finivano su disco contro la regola scritta. Chi amministra
    ha deciso (28/10) che restano, e la sera che si tiene la foto intera 60 giorni, per sempre con
    «archiviala»: decisione [0034](../decisioni/0034-miniature-nella-conversazione.md); le frasi vecchie
    di `immagini.py`, `tools/immagini.py` e `schede.foto` sono segnate come storiche.
  - *Lo stato si vede*: il dettaglio di una miniatura di foto chiede al server (`POST /api/conversazione`
    con `{foto}`, solo il proprietario dal suo schermo personale) lo stato e, finché c'è, la foto intera:
    «La tengo fino al …: di' «archiviala» per tenerla sempre.», «Archiviata.» con «Apri i tuoi
    documenti», «Non c'è più: non era stata archiviata.» (`rigaFoto` in `schermo.js`). Cache del
    service worker `calliope-telefono-pagina-v16` (era v15). Dettagli in
    [immagini-allegati](immagini-allegati.md).
  - *Il tetto dell'attesa* sale da 30 a 300 s (`ATTESA_SCHEDE_S`): fra la miniatura e la frase c'è la coda
    delle risposte (`corsia.entra_llm`). Una miniatura buttata (scaduta, un'altra persona, identità
    incerta, più di otto) scrive una riga nel registro, `[SCHERMI] … non legata alla Conversazione:
    <motivo>`, senza dati.
  - `_attesa` vale per un invio solo: si toglie dalla scheda dopo l'uso, così «mostrami l'ultima» (`hub.ricorda`
    tiene lo stesso dizionario) non la rimette in attesa per il turno dopo; `_sfida_reply` lega le
    miniature come `_reply`.
  - La miniatura piccola resta calcolata in `schede.foto`: la scheda passa dal JSON dei risultati dei tool,
    dove non può portare i byte né una funzione per calcolarla dopo (pochi millisecondi per foto).
  - «Elimina» del cassetto toglie la foto, non la miniatura nel turno: resta fino ai 60 giorni o a
    «dimentica», e il dettaglio dice «Non c'è più: è stata eliminata dal cassetto.».

## Il layout compatto per gli schermi piccoli (28/10, issue #277, ramo `issue-277-telefono-compatto`)

Caso vero del 28/10, 12:54, iPhone 13 mini nella PWA, epic #251. Dalle schermate la pagina era larga
**320 px**, non 375: Allega mancava (sotto i 360 px resta nella casella di «Scrivi») e le misure delle parti
tornano solo a 320. È quasi certamente lo **«Zoom schermo»** di iOS (Impostazioni › Schermo e luminosità), che sul mini dà una
finestra di 320×693 e ingrandisce tutto del 17 %: da qui il «testo grande». Non è il testo dinamico di iOS
(la pagina usa px sulla radice, 17 px, e iOS nella PWA non lo applica) né `text-size-adjust`, che ora è
comunque fermato al 100 % (in orizzontale Safari ingrandiva il testo da solo).

- **Quando**: in verticale sotto i 390 px di larghezza o i 720 di altezza (media query in `telefono.css`):
  iPhone mini, SE, mini con lo zoom, Android piccoli. Non a 390×844 né più grandi, non in orizzontale, mai
  in auto (lì contano i bersagli grandi).
- **La voce su una riga.** Scelta: lo stato entra in «Parla», che diventa a due righe piccole (la parola
  breve, «Parla», «Tocca per finire», «Interrompi», e sotto lo stato, «Microfono spento», «di' «Calliope»»,
  «Penso…», «Parlo», «Ti ascolto»); bordo e icona di «Parla» restano quelli di sempre. La riga grande dello
  stato resta nel DOM come `role="status"` ritagliata a 1 px: VoiceOver legge i cambi come prima, e lo stato
  piccolo in «Parla» è `aria-hidden` (non lo legge due volte). Il suggerimento «Tocca «Parla» per parlare»
  (`data-ovvio`) non si mostra ed è la descrizione di «Parla» (`aria-describedby`); le altre righe piccole (il
  microfono su un altro satellite, la compagnia, la stanza) restano sopra i pulsanti, perché dicono qualcosa
  che non si vede. **Scartato** il ritorno alla voce grande quando ascolta, pensa o parla: la sezione sopra
  salterebbe di 50–70 px a ogni turno, proprio mentre si legge la risposta; il colore del bordo e lo stato
  in «Parla» bastano. Microfono, Scrivi e Allega 2,75rem (46,75 px); in flex, così un pulsante nascosto non
  lascia una colonna vuota.
- **La barra** più bassa (2,9rem, icone 1,2rem, etichette 0,62rem), la zona sicura in fondo come prima.
- **Titolo della sezione** 1,2rem (era 1,55rem); spazi tra le parti e padding delle schede più stretti.
- **I filtri della Conversazione** in una riga sola che scorre di lato (non va mai a capo), «Cerca» come lente
  (il testo resta per i lettori); solo sul telefono, il PC non cambia.
- **Le tessere di Le mie cose** più fitte: il conto accanto al nome quando c'è posto, se no sotto (in flex che
  va a capo: in griglia, col testo ingrandito, il nome si spezzava a metà parola, «Agend a»).
- *Trovato nella prova*: a 375 px nella Conversazione, con quattro pulsanti, «Parla» andava a capo a metà
  parola («Parl a»). Nel compatto non succede più.
- **Misure** (Chromium, senza zona sicura; voce e barra insieme sull'altezza, con la riga piccola del
  microfono su un altro satellite al posto del suggerimento, come nelle schermate):

  | | prima | dopo | dopo, senza riga piccola |
  |---|---|---|---|
  | 375×812 (13 mini) | 27,5 % | 15,7 % | 12,9 % |
  | 375×667 (SE) | 33,5 % | 19,2 % | 15,7 % |
  | 320×693 (13 mini con lo zoom) | 32,2 % | 18,4 % | 15,1 % |
  | 320×568 | 39,3 % | 22,5 % | 18,4 % |

  La conversazione nella sua sezione da 311 a 464 px a 375×812, da 223 a 279 a 320×568. Col testo ingrandito
  del 20 % (radice a 20 px) voce e barra restano sotto il 30 %, nulla esce né si taglia, i filtri scorrono di
  lato a 320 px.
- **La tessera Cassetto** dice «file 7 giorni · foto 60» (decisione [0034](../decisioni/0034-miniature-nella-conversazione.md),
  `immagini_tenuta_giorni`; con `immagini_tenuta` spenta «tengo 7 giorni» come prima), la nota della pagina
  «Tengo i file 7 giorni e le foto 60.» (`raccolte._tenuta`, `_nota_cassetto`). *Storico: fino al 28/10
  «tengo 7 giorni» anche per le foto.*
- **La frase del PDF** nella stessa schermata («Ti ho preparato la guida in PDF sul server, perché il satellite
  collegato non riceve documenti») non era un turno di prima del passo 2d: veniva dalla guida della casa
  (`casa_integrazione` con `per_iscritto`, `Documenti.scrivi_fisso`), una strada che il 2d non aveva toccato,
  e la guida non entrava nell'archivio, quindi non si ritrovava nemmeno in Documenti. Ora, rimasta sul
  server, entra nell'archivio di chi l'ha chiesta e la frase è come quella di `documento_crea` (scheda con
  «Scarica», pagina Documenti, o quella di sempre senza schermo personale): [casa](casa.md). `documento_crea`,
  `frase_pagina` e `personale_abbinato` erano già giusti.
- Cache del service worker `calliope-telefono-pagina-v17` (era v16).

Prove: `prova_telefono_schermo` (anche 375×667 e 320×693; in verticale il compatto, la voce su una riga coi
pulsanti allineati e lo stato in «Parla» su al più due righe, voce e barra sotto il 25 %, col testo
ingrandito sotto il 30 %, in auto niente compatto, le tessere senza parole spezzate né testo che trabocca);
`prova_cronologia_pagina` (i filtri su una riga e «Cerca» come lente a 375×812, 375×667, 320×568, 320×693 e
col testo ingrandito, il titolo più piccolo); `prova_sezioni` (la media query a secco: dove vale e dove no,
niente regole per l'auto, tocchi ≥ 44 px, la riga dello stato per i lettori); `prova_raccolte` (la tessera
Cassetto); `prova_casa_ha` (la guida rimasta sul server con le tre frasi e nell'archivio). Da provare sul
vero: l'iPhone 13 mini con e senza lo «Zoom schermo», e VoiceOver su «Parla».

## Tolte le schede degli esercizi; la tessera Studio «arriva presto» (28/10, issue #279, ramo `issue-279-via-esercizi`)

Con il vecchio processo degli esercizi (decisione [0035](../decisioni/0035-studio.md), area
[minori](minori.md)) escono dagli schermi `POST /api/esercizio`, `hub.esercizi`, i tipi
`esercizio` ed `esercizi_riepilogo` (`DISEGNA`, `NOMI_TIPO`, `SEZIONE_DI_TIPO` in `schede.py` e in
`schermo.js`, la regola «viva», `TIPI_RIMANDO` e `TIPI_APRONO` di `sezioni.js`, gli stili in
`schermo.css` e `telefono.css`), la ripresa degli esercizi chiusi nella cronologia e «esercizio» di
`schermo_mostra`. La tessera Studio di Le mie cose resta al suo posto, senza conto («—») e con lo
stato «arriva presto»; la pagina dice «presto» come le altre non ancora fatte, fino al passo 4.5
(#284). Cache del service worker `calliope-telefono-pagina-v18` (era v17). Prove: `prova_raccolte`,
`prova_sezioni`, `prova_cronologia_schede`, `prova_telefono_schermo` (la tessera nella pagina vera).

## Il modello sa del telefono a sezioni (28/10, issue #288, #289, #290 e #291, ramo `issue-288-telefono-consapevole`)

Casi veri della DGX del 28/10 (versione 0fbda07), dal telefono, epic #251: alle **13:53** «Apri lo schermo
dei documenti su questo dispositivo.» → «non posso aprire uno schermo perché non è un computer», con l'offerta
del portatile, che non era collegato; alle **13:54** «la scheda documenti del tab Le mie cose» → «non ho una
scheda Le mie cose su questo dispositivo». **Cause**: la nota del dispositivo diceva «il telefono, non un
computer» e «niente webcam né schermo del computer», e il modello ne deduceva che il telefono non ha uno
schermo; «Le mie cose» compariva solo dentro le frasi dei tool; `schermo_mostra` parlava di «uno schermo di
casa» e non sapeva aprire una pagina. Lo scopo comune delle quattro issue: allineare quello che Calliope dice
con quello che il telefono e lo schermo personale fanno davvero.

- **#288, dove va il pezzo fisso.** Scelta: nel **prompt di sistema** (`Config._frase_sezioni`, con
  `prompt_for(…, sezioni=True)` quando ci sono `schermo_mostra` e il telefono o `schermi_sezioni`), uguale per
  tutti e fra i turni, così la cache del prefisso (#95) non si perde: cambia solo con la configurazione o con
  l'Ufficio installato, e allora `_scalda_se_cambiato` scalda il prefisso nuovo una volta. Dice le sezioni
  (Adesso, Conversazione, Le mie cose, Casa, Io), le pagine di Le mie cose (Liste, Agenda, Lavori e programmi,
  Cassetto, Documenti, Giochi; «e, solo per chi amministra, Ufficio» solo con l'ufficio; Studio no, la pagina
  non c'è ancora), Casa nascosta sotto i 13 anni (`aspetto.ETA_CASA`), cosa si fa dallo schermo (scrivere e
  allegare dentro una conversazione cominciata a voce *[storico: dal 28/10, #301, «anche senza aver
  parlato»]*, la spunta delle liste, «+1 minuto» e «Ferma» dei timer),
  la tenuta delle foto (60 giorni, gli altri file 7, per sempre con «archiviala», decisione
  [0034](../decisioni/0034-miniature-nella-conversazione.md); con `immagini_tenuta` spenta i giorni del cassetto)
  e quando chiamare `schermo_mostra` con `cosa=pagina`. **Scartato** nei dati del turno: lì si rilegge a ogni
  turno (220 token in più per ogni richiesta), e nella storia come i dati fissi sarebbe da rifare a ogni
  cambio di persona. Ciò che dipende da chi parla resta nella **nota del dispositivo** (dati del turno).
- **La nota del dispositivo** (`dispositivo.schermo_di`, `nota`): lo schermo personale di chi parla «aperto
  adesso», «chiuso adesso» o «chi parla non ha uno schermo personale» (ospiti e zona grigia mai, come
  `personale_abbinato`) *[storico: così fino alla revisione della PR #294, sotto]*, e «e lì non c'è Casa» o «Ufficio» (sotto i 13 anni, per chi non amministra, solo con
  l'ufficio installato). Il «niente» vale per la webcam e la **schermata del computer**, non per lo schermo.
  Lo scritto dallo schermo personale (il telefono o il PC: `Ciclo._dispositivo_turno` guarda il proprietario
  dello schermo) è «lo schermo personale a sezioni di chi parla, per scritto». Testo del caso delle 13:53:
  «dispositivo: il telefono, non un computer; lo schermo personale di chi parla è aperto adesso; nessun
  computer collegato, quindi niente webcam né schermata del computer.» *[storico: fino al 28/10 «…; nessun
  computer collegato, quindi niente webcam né schermo del computer.»]*
- **Il registro dei turni** ha il campo `dispositivo` (`{"canale": "telefono", "schermo": "aperto"}`, da
  `Brain.last_dispositivo`): fino al 28/10 i turni a voce dal telefono non dicevano da dove venivano. Il campo
  `canale` resta com'era (scritto, tocco).
- **Token** (stima a 3,5 caratteri per token, come `Brain`): il paragrafo del prompt 757 caratteri, ~216 token
  con l'Ufficio (721 e ~206 senza), una volta nel prefisso; lo schema di `schermo_mostra` +293 caratteri
  (~85 token), nel prefisso anche lui; `documento_crea` +8 caratteri; la nota del dispositivo +~15 token per
  turno (aperto o chiuso, ~12 senza schermo personale), +~6 con una sezione nascosta. In tutto ~300 token nel
  prefisso, letti una volta per conversazione (poi in cache), e ~15 per turno. Il prefisso resta uguale fra lo schermo aperto e chiuso, fra chi amministra, un familiare e una
  bambina (`prova_telefono_consapevole`). Da misurare sulla DGX: i token veri del 26B e la prima frase.
- **#289, `schermo_mostra` con `cosa=pagina`** (`pagina`: documenti, liste, agenda, lavori, cassetto, giochi,
  ufficio; le forme «lavori e programmi», «lista», «gioco»… si riconducono, principio 10). Lo schermo personale
  aperto di chi parla riceve l'evento SSE «pagina» col solo nome (`Schermi.apri_pagina`, che rifiuta ciò che
  non è un nome di lettere) e va su `#/cose/<pagina>` (`telefono.js` e `pc.js`, «calliope:pagina», un nome di
  1–20 lettere minuscole, mai un indirizzo). Frasi: «Ecco, sul tuo schermo c'è Le mie cose, alla voce
  Documenti.» (regola `schermo_pagina`); chiuso «Lo trovi in Le mie cose, alla voce Documenti, quando apri il
  tuo schermo.» (`schermo_pagina_chiuso`); senza schermo personale, ospite e zona grigia un rifiuto. Le pagine
  come `raccolte.visibili`: l'Ufficio solo per chi amministra e mai a un minore. La descrizione dice «su uno
  schermo, anche il telefono di chi parla». **Politica**: `schermo_mostra` era già di classe sicura e resta tale
  (cambia solo la vista, è reversibile); non è un tocco della pagina, quindi niente in `TOCCABILI`.
- **#290, le frasi.** Senza «server» né «satellite», che a chi ascolta non dicono niente: la consegna rimasta in
  casa dice «tra i miei documenti, perché il portatile non è collegato» o «… perché il portatile non
  riceve file» *[storico: fino alla revisione della PR #294 «… perché il dispositivo da cui mi parli
  non riceve file», falso dal telefono, che riceve i file con «Scarica»]* (`RemoteDelivery._sul_server`); la guida della casa senza schermo personale ripiega su
  quella. I **lavori dell'agente** rimasti in casa (`Lavori._dove_in_casa`) usano la stessa scelta dei
  documenti: con uno schermo personale abbinato di chi l'ha chiesto (aperto o chiuso, `Lavoro.ha_pagina`, presa
  alla delega in `tools/agenti._schermo` *[storico: dalla revisione della PR #294 decisa alla consegna, sotto]*) «in Le mie cose, alla voce Lavori e programmi», dove il risultato ha
  «Scarica»; senza, «tra i miei file, nella cartella Lavori, perché …». `documento_crea` «lo consegna a chi
  parla» invece di «lo salva sul PC». *[storico: fino al 28/10 «sul server, perché il satellite collegato non
  riceve documenti» e «sul server, nella cartella Lavori, perché …»]*
- **#291, le versioni nei log.** La riga «[SATELLITE] collegato» dice «protocollo N» (dal «ciao») e, per il
  telefono, «pagina calliope-telefono-pagina-v19»: la pagina legge il nome della cache del service worker in
  uso (`caches.keys()`) e lo manda nel «ciao»; il server lo tiene solo se ha quella forma. Prima apertura o
  certificato non fidato: niente pagina nella riga. *[storico: così fino alla revisione della PR #294; da allora
  la costante `PAGINA_VERSIONE` di `telefono.js`, sotto]*
- Cache del service worker `calliope-telefono-pagina-v19` (era v18: la v18 era della #279 e di questo ramo insieme, unite nello stesso giorno).

Prove: `prova_telefono_consapevole` (nuova, livello 1: la nota, il prompt e la stima, i due casi del 28/10 nel
Brain con il modello finto, il prefisso, `cosa=pagina` con permessi ed età, le frasi in tre casi, le versioni
sul server vero); `prova_telefono_schermo` (l'evento «pagina» porta il telefono vero su `#/cose/documenti` e poi
`#/cose/liste`, un nome fuori forma o il JSON rotto no, la pagina d'altri no); adattate `prova_documenti`,
`prova_pagina_documenti`, `prova_casa_ha`, `prova_esecutore`, `prova_markdown` per le frasi nuove. Col modello,
sulla DGX: `prova_schermi_ollama`, `prova_documenti_ollama`, `prova_immagini_ollama` (la nota del dispositivo)
e il banco di regressione; i due casi del 28/10 detti dal telefono sono da provare sul vero (la prova a secco
controlla cosa arriva al modello, non cosa sceglie).

**Dalla revisione della PR #294** (28/10 sera, esito «da correggere»):

- **Zona grigia.** `schermo_di` dava «nessuno» con `mittente.certo` falso, e dal suo telefono aperto la nota
  diceva «chi parla non ha uno schermo personale»: la zona grigia (frase breve, conferma dentro la
  conversazione, continuità, minore vicino) al telefono, in auto, è frequente. Ora il dispositivo porta
  «di» (`descrivi(…, di=)`: il proprietario del satellite personale, o dello schermo da cui si scrive;
  `Ciclo._dispositivo_turno`), il Brain lo mette in `tool_ctx.dispositivo`, e `dispositivo.proprio` dice se
  il dispositivo è della persona della conversazione. Dal suo telefono vale come riconosciuto (aperto o
  chiuso, come `_proprio_grigio` e `risultato_schermo_proprio`); da un altro dispositivo la nota dice «non
  sono sicura di chi parla, quindi non uso uno schermo personale da qui»; a un ospite «chi parla non è
  riconosciuto dalla voce, quindi niente schermo personale». «chi parla non ha uno schermo personale»
  resta solo per chi è riconosciuto e non ne ha. `cosa=pagina` dalla zona grigia si apre dal proprio
  telefono (regola `schermo_pagina_proprio`); altrimenti «Non sono sicura di chi parla, quindi da qui non
  apro uno schermo personale: chiedimelo dal tuo telefono, o con una frase più lunga.», senza «chiamami per
  nome». Il documento della zona grigia dal proprio telefono dice la pagina Documenti (`_su_pagina`).
- **Il motivo detto sul PC.** «il dispositivo da cui mi parli non riceve file» era falso dal telefono e, per
  i lavori, indicava il satellite attivo quando il lavoro finisce: ora «il portatile non è collegato» o «il
  portatile non riceve file» (`RemoteDelivery`, `Lavori._consegna_risultato`).
- **Lavori dopo un riavvio.** `ha_pagina` si prendeva alla delega, e mancava ai lavori rifatti insieme
  (`_rifai_interrotti`, `insieme[1:]`) e a quelli ripresi da disco (`ripresa.ricostruisci`). Ora
  `Lavori._ha_pagina` decide alla consegna da `lav.persona` con gli abbinati (`Lavori.schermi`, messo da
  `main.py`); `Lavoro.ha_pagina` resta solo per le prove. **Lavori e programmi mostra gli ultimi
  `LAVORI_FINITI_PAGINA` (6)**: `ris["dove_cartella"]` tiene la cartella e `Lavori.dove_detto` la dice al posto
  di «in Le mie cose…» se il lavoro non è più fra quelli (`frase_finale`, «fammene un PDF»). Scartato «Mostra
  altri» nella pagina: la frase si dice quasi sempre a lavoro appena finito, quando è il primo.
- **Il prompt segue gli interruttori**: il telefono con `telefono_enabled`, il PC con `schermi_sezioni`, lo
  scritto con `schermi_scritto`, foto e file con `immagini_enabled` e `allegati_enabled`, il Cassetto e la
  tenuta con `cassetto_enabled`, «archiviala» con `archivio_enabled`; senza telefono né PC a sezioni nessun
  paragrafo. Resta uguale fra i turni: cambia solo con la configurazione.
- **Ufficio e Cassetto coerenti col prompt**: `cosa=pagina` non apre l'Ufficio senza l'ufficio installato
  (`ctx.ufficio`), né il Cassetto con `cassetto_enabled` spento.
- **`cosa` fuori elenco con `pagina` piena**: un errore («per una pagina di Le mie cose serve cosa=pagina»),
  non la pagina.
- **La versione della pagina** è una costante di `telefono.js` (`PAGINA_VERSIONE`), uguale alla cache di
  `sw.js` (la prova le confronta), mandata già nel primo «ciao». *[storico: fino alla revisione il nome
  della cache più alta da `caches.keys()`, che durante un aggiornamento è quella nuova, e il primo «ciao»
  poteva partire senza]*
- **Lo scritto dallo schermo personale** dice anche le sezioni nascoste («lì non c'è Casa»).
- **Politica**: `prova_politica` fissa `cosa=pagina` come sicura, anche dopo un dato non fidato
  (`DOPO_DATO`) e alla porta stretta con lo scope `schermi`; un'estensione comunque non apre pagine (la
  porta passa solo titolo e testo).
- **Col modello**: `prova_schermi_ollama` ha i due casi del 28/10 dal telefono di Dario e i contrari, da
  lanciare sulla DGX.
- Unita l'epic con la #292 (`2fb73694`): il service worker passa alla **v19** (le due PR portavano la stessa
  riga alla v18, e git non lo segnala).

**Dalla seconda revisione della PR #294** (28/10 sera):

- **Un minore possibile dal telefono di chi amministra.** Nel caso `voce_proprietario` (voce incerta fra
  Dario e Ada sul telefono di Dario, vale Dario dalla conversazione) `dispositivo.proprio` diceva sì: la nota
  «aperto» e `cosa=pagina` apriva anche `#/cose/ufficio`. Ora `proprio` è falso con `speaker_ctx.minore_incerto`,
  `incerta` o `minore_vicino`: anche col minore vicino, dove la voce è di Dario, vince la prudenza (chi tiene
  il telefono può essere il minore). La nota dice «non sono sicura di chi parla» e nessuna pagina si apre.
- **L'Ufficio col livello del turno**: solo con «amministra», non con `prof.admin`. Dallo schermo e dalla zona
  grigia il livello è al più «familiare»: dal suo telefono Dario apre l'Ufficio solo con la voce riconosciuta
  in quella frase e il livello di chi amministra; con una frase breve, o col minore vicino, no (la frase lo
  dice: «Sul tuo schermo la pagina Ufficio non c'è.», o «non sono sicura di chi parla»).
- **Il tocco** azzera `tool_ctx.dispositivo` (`Ciclo._tocco`): i tool del canale «tocco» non vedono il
  dispositivo dell'ultimo turno a voce.
- **Lo schermo revocato dopo la consegna**: `Lavori.dove_detto` ricontrolla gli abbinati di chi ha chiesto il
  lavoro; senza, la cartella.

## Due resti dopo la PR #294: la frase dell'Ufficio e la frase breve dal telefono (28/10, issue #299, ramo `issue-299-frase-ufficio`)

Note della terza revisione della PR #294, decise da chi amministra il 28/10.

- **La frase dell'Ufficio rifiutato per il livello** (`tools/schermi._apri_pagina`). A chi amministra, con il
  livello del turno più basso di «amministra» (frase breve, zona grigia), ora: «L'Ufficio lo apro solo quando
  riconosco bene la tua voce: chiedimelo con una frase intera.» (regola `schermo_ufficio_voce`). *[storico: fino
  al 28/10 sera «Sul tuo schermo la pagina Ufficio non c'è.», falso, e il modello poteva ripetere «non hai
  l'Ufficio»]* «Sul tuo schermo la pagina Ufficio non c'è.» resta solo per chi davvero non ce l'ha: i
  familiari, i minori, e senza l'ufficio installato.
- **Decisione di chi amministra (28/10): la frase breve dal suo telefono apre le pagine, l'Ufficio escluso.** Il
  caso è quello di un minore che dice una frase breve subito dopo chi amministra, sul telefono di chi amministra
  (anche per continuità, `minori.py`): vale chi amministra, senza nessun segno di minore, e le pagine diverse
  dall'Ufficio si aprono. Il danno è solo spostare la vista del telefono che il minore ha già in mano, e
  l'Ufficio resta chiuso perché vuole il livello «amministra» del turno. **Scartato**: `dispositivo.proprio`
  solo con `identified_by == "voce"` quando in casa c'è un minore, che avrebbe tolto a chi amministra tutte le
  pagine con una frase breve dal suo telefono. Restano chiusi i casi con un segno di minore (`minore_incerto`,
  `incerta`, `minore_vicino`), come dalla seconda revisione della PR #294.

Prove: `prova_telefono_consapevole` (la frase della voce a chi amministra nella zona grigia e con la voce certa
ma il livello «familiare», e la regola; i contrari con «non c'è» per un familiare, una bambina e senza
l'ufficio installato).

## Scrivere nella Conversazione, anche senza aver parlato (28/10, issue #301, ramo `issue-301-scrivere-in-conversazione`)

Decisioni di chi amministra del 28/10 nella #301 (epic #251); tavole del canvas del telefono, riga «Scrivere
nella Conversazione (28/10)»: ScriviVoce, ScriviTastiera, ScriviMentre, ScriviInviato, ScriviRitorno,
ScriviMiniVoce, ScriviMiniTastiera e PcConversazione.

- **La pagina apposta non c'è più** (`#strato-scrivi` tolto, con «Allega» nella riga della voce). Il tocco
  sulla tastiera porta alla **Conversazione in modalità scrittura**, nella stessa schermata (`entraScrittura`
  in `telefono.js`: la sezione, la casella e il cursore nello stesso tocco, perché iOS apre la tastiera solo
  dentro il gesto). La riga della voce diventa la casella di `schermo.js` (`#scrivi` dentro `#scrivi-posto`):
  «Torna alla voce» (il microfono) a sinistra, Allega (solo qui: risposta 3), il testo su più righe
  (`textarea` che cresce fino a cinque righe, a `max(16px, 0,95rem)` perché iOS non ingrandisca la pagina) e
  Invia, spento con la casella vuota; sopra, l'anteprima di ciò che si allega (la miniatura, «Foto allegata ·
  1,2 MB», ✕ per toglierla). Invio manda, Maiusc+Invio va a capo. Nel layout compatto (#277) Invia è
  un'icona e il segnaposto lungo, se non ci sta su una riga, diventa breve («Scrivi…»). L'esito («Inviato: ti
  rispondo qui.») resta per i lettori; si vede solo un errore.
- **Torna alla voce** fa partire subito l'ascolto (`tocca`, come «Parla»: risposta 1). La modalità resta
  finché non si tocca il microfono; uscendo dalla Conversazione si chiude (`dopoPercorso`, un'opzione nuova
  di `sezioni.js`: risposta 4); la wake word resta accesa (risposta 2: la modalità non tocca il microfono).
  **In auto** la tastiera non c'è: niente tasto, niente casella.
- **La tastiera di sistema** (anche il punto 1 della #287). `interactive-widget=resizes-visual` nel viewport:
  Chrome su Android, come Safari su iOS, non ridimensiona più la pagina quando si apre la tastiera, quindi la
  media query del compatto (sull'altezza della finestra) non scatta. La parte visibile la dice
  `visualViewport`: con un campo di testo col fuoco e la parte visibile più bassa di 120 px della finestra, la
  vista si stringe a quella parte (`--alto-visibile`, `--su-visibile`, classe `tastiera`) e **la barra delle
  sezioni si nasconde, solo finché la tastiera è aperta**. Vale per ogni campo (anche le ricerche della
  Conversazione e di Le mie cose). *Limite*: Chrome per Android prima della 108 ignora `interactive-widget`, e
  lì il compatto può ancora accendersi con la tastiera.
- **La Conversazione come una chat**, a voce e scrivendo (le tavole ScriviVoce e ScriviRitorno la disegnano
  così anche a voce, e passare da un modo all'altro non sposta niente): le bolle sul nero, «Tu» e «Calliope»
  solo per i lettori, sotto la bolla della persona l'ora e il canale («10:47 · scritto», «10:46 · a voce»: il
  posto solo se non è questo schermo o il satellite che lo porta, `nomiPropri` di `schermo.js`, risposta 6),
  le schede come un **rimando di una riga** (44 px) dentro la bolla di Calliope che apre il dettaglio (la foto
  resta con la sua miniatura, #272), i **filtri dietro la lente** in alto (`#conv-lente`; un filtro acceso
  resta detto nella riga sotto, con «Tutto»). Scrivendo, in più, niente «Altre schede» né «Scarica Markdown»:
  solo chat. Solo nella sezione del telefono: a schermo intero e sul PC la conversazione resta quella del
  #242. *[storico: fino al 28/10 nella sezione «Tu» e «Calliope» sopra le bolle, l'anteprima delle schede
  piccole e i filtri sempre in vista]*
- **«ti ascolto…»** in fondo alla chat mentre si parla (risposta 5: poi il turno arriva come bolla «a voce»),
  «Calliope sta scrivendo…» dopo un invio finché non arriva il turno (al più 30 s), «Calliope sta
  rispondendo…» mentre pensa (`#conv-ora`; è `role="status"` solo scrivendo: a voce lo dice già la riga della
  voce).
- **Si scrive sempre dallo schermo personale** (opzione 2 della #301, come il tocco):
  `conversazione.scritto_libero` e `Schermi.scritto_consentito(schermo, canale)` lasciano passare casella,
  foto e file (`CANALI_LIBERI`) dello schermo personale senza aver parlato, in `/api/scrivi`, `/api/immagine`
  e `/api/allegato`, e di nuovo nel ciclo (`_prendi_scritto`). Il livello è quello di sempre per lo scritto
  (`identified_by` «schermo»: al più «familiare»); un minore ha il suo livello, il suo preset e i suoi orari
  (`_fuori_orario`); ciò che vuole la voce resta rifiutato (`serve_la_voce`); niente Ufficio, che vuole
  «amministra» ([sicurezza-politica](sicurezza-politica.md)). **Restano legati alla conversazione a voce** i
  moduli (nascono da una richiesta a voce e si chiudono quando la conversazione finisce: lo stato `scrittura`
  ha ora `moduli` e `testo_moduli` accanto ad `attiva`, e l'invio di un modulo si spegne da solo), gli schermi
  di stanza (`schermi_scritto_stanza`) e i file di un ragazzo toccati dal tutore. *Storico: dal 05/10 al 28/10
  anche la casella, le foto e i file dello schermo personale valevano solo dentro una conversazione cominciata
  a voce («Scrivere solo in conversazione», in cima).*
- **Il modello**: il paragrafo delle sezioni (`Config._frase_sezioni`) dice «si scrive e si allegano foto e
  file anche senza aver parlato (ciò che vuole la voce si chiede a voce)», la nota del dispositivo (#288)
  «lo schermo personale a sezioni di chi parla, per scritto, anche senza aver parlato». *[storico: fino al
  28/10 «in una conversazione cominciata a voce» nel prompt, e la nota senza la coda]*
- **Sul PC** la casella è sempre in fondo alla colonna della Conversazione (risposta 7), ora accesa anche
  senza aver parlato e disegnata come nella tavola PcConversazione: il testo su più righe sopra, poi Allega,
  «Invio per mandare, Maiusc+Invio per andare a capo · trascina qui un file» e Invia. Il resto della colonna
  non cambia.
- Cache del service worker `calliope-telefono-pagina-v20` (era v19), uguale a `PAGINA_VERSIONE`.

Prove: `prova_cronologia_pagina` (nuova parte «scrivere» sul telefono: il tocco sulla tastiera, la riga
nell'ordine giusto, Invia spento e acceso, solo chat e la lente, l'invio senza conversazione a voce in coda
a nome del proprietario, «Calliope sta scrivendo…», l'invio con una foto e l'anteprima; a 390×844 e 320×693,
anche col testo ingrandito, il testo a 16 px, niente fuori di lato, contrasto AA anche del segnaposto, tocchi
≥ 44 px, Invia icona solo nel compatto; la tastiera simulata con un `visualViewport` finto che nasconde la
barra, tiene la casella sopra la tastiera e non fa scattare il compatto, e il contrario senza un campo col
fuoco; «Torna alla voce» con l'ascolto che parte e «ti ascolto…»; l'uscita dalla sezione e l'auto; i filtri
dietro la lente nella parte del #242); `prova_sezioni` (a secco: `interactive-widget`, la pagina apposta
tolta, la barra solo con la tastiera, i 16 px, niente casella in auto, il compatto che non guarda la
tastiera); `prova_scritto_senza_voce` (nuova, il ciclo vero: [sicurezza-politica](sicurezza-politica.md));
adattate `prova_telefono_schermo`, `prova_pc_pagina` (la casella accesa senza aver parlato e Invio che manda), `prova_scritto_pagina` (anche Invio e Maiusc+Invio), `prova_immagini_pagina`, `prova_vista_sviluppo_pagina` (i comandi dello sviluppo accesi senza conversazione),
`prova_scritto_conversazione`, `prova_scritto`, `prova_immagini`, `prova_allegati`, `prova_scritto_calliope`,
`prova_telefono_consapevole`. Da provare sul vero: l'iPhone 13 mini con e senza lo «Zoom schermo» (la
tastiera vera, la barra che si nasconde, il gesto per chiudere la tastiera), un Android con Chrome recente e
uno vecchio, VoiceOver sulla casella e su «ti ascolto…».
- **Dalla revisione della PR #304** (e decisioni di chi amministra del 28/10 dopo la revisione):
  - *In modalità scrittura la risposta è solo scritta.* La pagina manda `solo_scritto` (`/api/scrivi`,
    `/api/immagine`, l'intestazione `X-Calliope-Solo-Scritto` di `/api/allegato`) e
    `Instradamento.inizio_scritto` risponde «muta»: la risposta compare nella chat, Calliope non la dice e non
    si apre la finestra d'ascolto. Torna a parlare con «Torna alla voce» o quando si dice «Calliope»; gli
    avvisi (il timer che suona, il pericolo) suonano come sempre. Dal PC la risposta resta quella di prima.
  - *Le irreversibili si confermano a voce*: «Questa la confermo solo a voce: dimmelo.», anche al «sì»
    scritto ([sicurezza-politica](sicurezza-politica.md)).
  - *La conversazione della persona* anche senza averne una aperta (prima lo scritto e il tocco finivano
    nell'anonima degli ospiti della corsia) e *foto e file di un minore fuori orario* rifiutati:
    [sicurezza-politica](sicurezza-politica.md).
  - *«Torna alla voce» non interrompe Calliope mentre parla*: scrivendo le risposte sono solo scritte, quindi
    ciò che suona è un avviso, che un tocco per cambiare modo non deve zittire; cambia modo e basta, e per
    interromperla c'è «Parla» («Interrompi e parla»). Se Calliope non parla, l'ascolto parte subito come prima.
  - *`#conv-ora` è sempre `role="status"`* (nell'HTML); scrivendo cade solo l'`aria-hidden`, prima del testo,
    così la prima frase («Calliope sta scrivendo…») si legge.
  - *Il segnaposto breve* si sceglie misurando la larghezza del testo col font della casella
    (`canvas.measureText`), non più l'altezza col segnaposto, che WebKit può non contare.
  - Il limite di Chrome per Android prima della 108 è scritto nella guida
    ([installazione](../installazione.md#e-telefono)).

## Telefono compatto e cassetto: le note delle revisioni (29/10, issue #287 e #307, ramo `issue-307-287-pulizie`)

Note non bloccanti della revisione della PR #286 (#287) e della PR #306 (#307), chiuse.

- **La tastiera che accendeva il compatto** (punto 1 della #287): già fatto dalla PR #304 (#301) con
  `interactive-widget=resizes-visual` nel viewport e la parte visibile misurata con `visualViewport`
  (`misuraTastiera`): verificato nel codice e nelle prove (`prova_sezioni`, `prova_cronologia_pagina` con la
  tastiera simulata che non fa scattare il compatto). Resta il limite di Chrome per Android prima della 108.
- **Il suggerimento letto due volte.** `aria-describedby="tel-dove"` non è più fisso in `index.html`: lo mette
  `descriviParla` (`telefono.js`) solo quando la riga piccola ha un testo ma non si vede (nel compatto, il
  suggerimento di sempre segnato `data-ovvio`), e lo toglie altrimenti; si rifà a ogni disegno, al cambio del
  compatto (`matchMedia` con la stessa media query del CSS, controllata da `prova_sezioni`) e al cambio di modo.
  Fuori dal compatto, o quando la riga piccola si vede (il microfono su un altro satellite, la compagnia),
  VoiceOver la legge una volta sola, nel suo posto. *[storico: dal 28/10 al 29/10 la descrizione era fissa]*
- **Le etichette della barra a 0,62rem** (10,54 px) restano: è la misura delle etichette della barra di iOS
  (10 pt), e a 320 px «Conversazione» ci sta col font largo e col testo ingrandito. La prova misura ora che non
  scendano sotto i 10 px; resta da guardarle sull'iPhone 13 mini vero.
- **Android e `text-size-adjust`.** Il testo fermo al 100 % vale solo su iOS (`@supports
  (-webkit-touch-callout: none)`, che c'è solo in WebKit su iOS): lì serve perché Safari in orizzontale
  ingrandiva il testo da solo; i Chrome per Android di prima, con `text-size-adjust`, perdevano il
  «Ridimensionamento testo» delle impostazioni di accessibilità. *[storico: dal 28/10 al 29/10 per tutti]*
- **Prove.** `prova_telefono_schermo` misura anche due telefoni grandi in verticale (390×844 e 412×915) dove
  il compatto **non** deve scattare, col suggerimento visibile e «Parla» senza descrizione; nel compatto il
  suggerimento nascosto è la descrizione. `prova_casa_ha` controlla di chi è la guida rimasta sul server
  (l'id di chi l'ha chiesta), la pagina Documenti (c'è per Dario, non per un familiare) e la sorgente di
  «Scarica» (`_scarica`: la guida intera, nel suo formato).
- **Il proprietario di ripiego «amministra»** della guida scritta non c'è più: senza una persona riconosciuta
  la guida non si scrive ([casa](casa.md)).
- **Il cassetto** (#307): `bottoneCassetto` disegna solo «tieni» e «ancora», e il tocco su un pulsante d'altra
  azione non chiama `/api/cassetto` e scrive «Per eliminare un file dimmelo a voce.»; tolto il secondo tocco
  di «Elimina tutti», codice morto dal 28/10 sera, e la sua regola CSS. Tolto anche `emetti("cassetto")` dal gestore dei pulsanti dei conoscenti, copiato per sbaglio (revisione della PR #309). Il resto in
  [sicurezza-politica](sicurezza-politica.md).
- Cache del service worker `calliope-telefono-pagina-v21` (era v20), uguale a `PAGINA_VERSIONE`.

## La pagina dello Studio e la fotocamera del telefono (29/10, issue #281, ramo `issue-281-studio-pagine`)

Il passo 4.2 dello Studio aggiunge al telefono la sua prima pagina che non è fatta di schede del
server: Le mie cose › Studio, con lo Studio attivo (in ombra solo per chi amministra, «prova»),
apre `schermi/pagina/studio.js` nel riquadro della pagina; `sezioni.js` la conosce come pagina che
si disegna da sé (`window.CalliopePagine`, `apri` e `chiudi`) e non chiede schede né ricerca.
`schermo.js` ha solo `calliopeSchermo.studio(blob, meta)` per le due API nuove, `POST
/api/studio/verifiche` e `POST /api/studio/pagina`. La pagina del telefono chiede ora anche la
fotocamera: `Permissions-Policy` con `camera=(self)` (prima `camera=()`), solo per `/telefono/`;
service worker `calliope-telefono-pagina-v22` (la v21 era già della #309) con `/bordi.js` e `/studio.js`. Le miniature sono
canvas, non URL blob (la CSP del telefono li vieta per le immagini). Il resto, coi controlli del
server e le misure, nell'area [studio](studio.md).
