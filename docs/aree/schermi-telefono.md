# Schermi e telefono

*Schede sugli schermi, abbinamento, visibilità, scrivere invece di parlare, telefono come satellite (PWA), rispondi dove ti ho chiesto. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Schermi (schede su PC, tablet, TV) | Starlette + uvicorn senza extra (puro Python) in un thread, SSE verso una pagina kiosk locale; abbinamento a codice in SQLite (stesso file della memoria) | `calliope/schermi/` → `Schermi` (`hub.py`: destinatari, visibilità, consegna), `ArchivioSchermi` (`archivio.py`), `schede.py`, `ServerSchermi` (`server.py`), `pagina/`, `load_schermi`; tool in `calliope/tools/schermi.py`; terminale `python -m calliope.schermi` |
| Telefono (satellite nel browser, PWA, dal 03/10) | stessa porta degli schermi: WebSocket di uvicorn con `websockets` sans-I/O e lo stesso protocollo dei satelliti; nel browser onnxruntime-web 1.30 in WebAssembly (Silero VAD e wake word), AudioWorklet, Web Audio, Screen Wake Lock API; CA di casa con `openssl` | `calliope/schermi/telefono.py` → `rotte`, `PonteWs`, `stato`; «Prova il microfono» `telefono_diagnostica.py`; `calliope/schermi/pagina/telefono/` (`telefono.js`, `voce.js`, `microfono.js`, `schermo-acceso.js` (`SchermoAcceso`, `diagnosi`: schermo acceso, dal 04/10), `sw.js`, manifest; una vista sola col carosello delle schede, dal 04/10: `sincronizza`, `disponi`, `vaiA`, strati menu/modulo/scrivi e, dal 06/10, la scheda a schermo intero (`apriIntera`, `disegnaIntera`, `chiudiIntera`); schede da `schermo.js` con `data-carosello` ed eventi `calliope:*`); `ServerSatelliti.prendi` / `lascia` / `per_pc`; `tls.certificato_telefono`; terminale `python -m calliope.schermi --certificato` |
| Scrivere invece di parlare (moduli e casella sugli schermi personali, dal 03/10) | POST `/api/scrivi` e `/api/modulo` del server degli schermi (sessione in un'intestazione, JSON, solo HTTPS in rete); controlli dei codici in Python e in JS (`schermo.js`, condiviso col telefono); dal 05/10 solo durante una conversazione a voce | `calliope/schermi/moduli.py` → `Moduli`, `Ingresso`, `controlla_campo`, `offri`, `completa`, `oscura`; `Ufficio.completa_modulo` / `rubrica_da_modulo`; `tools/spec.serve_la_voce`; ciclo in `main.py` (`scritto`); `calliope/schermi/conversazione.py` → `scrittura_consentita`, `Conversazioni`; `Schermi.scrittura_consentita` (il punto unico, anche per le foto) |
| Cruscotto di chi amministra (fase 1, sola lettura, dal 06/10) | — (solo libreria standard: registro dei turni, SQLite in sola lettura, `indice.json` delle estensioni) | `calliope/schermi/cruscotto.py` → `Cruscotto` (`amministra`, `dati`), `LettoreTurni`, `versione_in_uso`, `tipo_errore`; GET `/api/cruscotto` (`server.py`); `Schermi.cruscotto`; scheda locale `cruscotto` in `schermo.js` (`apriCruscotto`, `impostaAmministra`), voce del menu del telefono; `latenza.leggi_file` |
| Lettore Markdown e «Scarica» nella scheda del documento (07/10) | scritto in proprio in `schermo.js` (createElement e textContent, mai innerHTML); conversione con fpdf2 e python-docx sul server | `schermo.js` → `leggiMarkdown`, `mdBlocchi`, `mdInLinea`, `pulsantiScarica`; `calliope/schermi/scarica.py` → `Scaricamenti` (`registra`, `gettone`, `prendi`), `converti`; POST `/api/scarica` e GET `/scarica/<gettone>` (`server.py`); `Schermi.scaricamenti`, `hub.pubblica`; `schede.documento_markdown`; `schermi_scarica_s` |
| Rispondi dove ti ho chiesto | — (prestito del satellite attivo, origine del turno) | `calliope/rispondi.py` → `Instradamento`; `ServerSatelliti.presta` / `restituisci` / `per_schermo`; `Schermi.origine_corrente`, `invia_a`, `Mittente.schermo`; `Speaker.muto` |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

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

  - **Telefono come satellite** (03/10, `calliope/schermi/telefono.py`): web app servita dal
    server degli schermi, stesso protocollo dei satelliti, wake word e VAD nel browser con gli
    stessi numeri del Python, schede come uno schermo personale. Più satelliti collegati, uno
    attivo (`prendi` / `lascia`). Provato in Edge senza finestra con il microfono finto
    (`prova_telefono_pagina.py`): i telefoni veri e l'auto no.

  - **Schermi** (02/10, `calliope/schermi/`, fase 1 di
    [`docs/ricerche/2026-10-01-mappe-e-schermi.md`](../ricerche/2026-10-01-mappe-e-schermi.md)):
    una pagina kiosk su PC, tablet o TV, abbinata con un codice detto a voce, mostra le schede
    dei tool (lista della spesa, timer con il conto alla rovescia, voce della biblioteca,
    anteprima dei documenti, stato della casa, calcoli) mentre Calliope risponde. Le schede
    personali vanno solo sugli schermi personali. Mappe, luoghi e percorsi (fasi 2–3) no.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Schermi** (02/10, `calliope/schermi/`, `calliope/tools/schermi.py`; prove
  `prova_schermi.py` a secco e `prova_schermi_ollama.py`; prova manuale in `prove/LEGGIMI.md`).
  Fase 1 del rapporto sulle mappe e gli schermi; le fasi 2–4 no.
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
  - Registro delle capacità: 12 capacità *[storico, 02/10: oggi 18]*; «schermi» conta come presente nel prompt se i tool
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

- **Telefono (web app)** (03/10, [`docs/ricerche/2026-10-03-webapp-telefono.md`](../ricerche/2026-10-03-webapp-telefono.md)):
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
  «alla WebKit»; sull'iPhone vero no (passi in `prove/LEGGIMI.md`, «Prova manuale del telefono» 9).

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
- **Pagina degli schermi** (tablet, portatile, TV): valutato e non cambiato. Lì la scheda
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
- **Niente azioni**: solo «Aggiorna» (rilegge) e «Chiudi» (toglie la scheda); revoche e
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
- **Zona grigia** (regola `risultato_schermo_proprio`, la stessa di `risultato_lavoro`): il
  documento o il risultato della persona della conversazione (proprietario uguale a
  `mittente.persona`) **appena consegnato** (il suo titolo è in una risposta recente della
  conversazione, `ToolContext.storia`: l'annuncio, la conferma) va sui suoi schermi personali
  anche dalla zona grigia; senza «Scarica»; mai sugli schermi d'altri. Contrari in
  `prova_risultati.py`: un documento non consegnato in questa conversazione (rifiutato come
  prima), un'altra persona (niente scheda di chi ha chiesto il lavoro); con la voce riconosciuta il
  risultato più recente, senza la regola.
