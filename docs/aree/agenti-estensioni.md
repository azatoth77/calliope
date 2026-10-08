# Agenti in secondo piano ed estensioni

*Gemma davanti, agenti dietro: delega, sandbox, arbitro e pausa di vLLM, programmi in diretta, contesto degli agenti, estensioni permanenti e guardrail. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Agenti in secondo piano («gemma davanti, agenti dietro») | vLLM con l'API compatibile OpenAI sulla DGX (motore «openai», httpx, via tunnel `ssh -N -L` di OpenSSH), oppure l'API nativa di Ollama (motore «ollama», anche lo stesso Ollama della voce); ciclo scritto in proprio, niente framework; sandbox in un container Docker usa-e-getta sulla DGX (dal 03/10), altrimenti job object di Windows (ctypes) e audit hook | `calliope/agenti/` → `Lavori` (`servizio.py`: coda, proposta, risultati, annuncio, domande a metà lavoro), `Agente` (`ciclo.py`), file della persona (`file_utente.py`), `Tunnel` (`tunnel.py`), `Sandbox` (`sandbox.py` + `_avvio.py`, `scegli_isolamento`; immagine da `setup/linux/sandbox/Dockerfile`), `Arbitro` (`arbitro.py`: anche con vLLM sulla GPU della voce, `ClienteCedevole` per archivio e ufficio; `stessa_gpu` in `impostazioni.py`, `agenti_arbitro`; dal 04/10 `PausaServer`, pausa di vLLM in modalità sviluppo, `pausa_server`, `agenti_pausa_vllm`), `Avanzamento` (`avanzamento.py`: la scheda del lavoro in diretta; dal 08/10 il flusso a sequenza, il registro del flusso e i tetti per giro), `ContestoLavoro` (`contesto_lavoro.py`, dal 05/10: risultati lunghi in `.calliope/passo-N.txt`, diario del lavoro alle soglie; finestra da `contesto.calcola_agenti`), `Ripetizioni` (`ripetizioni.py`, dal 08/10 sera: il giro a vuoto nel ragionamento ferma la passata), `Modello` (`modelli.py`), `carica` (`impostazioni.py`: dgx.yaml / agenti_url), `ClienteOllama` / `ClienteOpenAI` (`remoto.py`, `remoto_openai.py`, `crea_cliente`), `load_agenti`; tool in `calliope/tools/agenti.py`; terminale `python -m calliope.agenti --prova` |
| Programmi dell'agente eseguiti in diretta, linguaggi (Python, C#) | stessa sandbox Docker; C# con csc nel container `calliope-sandbox-dotnet` (runtime .NET 10 + Roslyn, niente SDK né NuGet); SSE verso la scheda | `calliope/agenti/esecuzione.py` → `Esecuzioni` (`avvia`, `dimostra`, `ferma`, `frase`); `linguaggi.py`; `esegui_cs.sh`; `setup/linux/sandbox/Dockerfile.dotnet`; tool `lavori_esegui`, scheda `esecuzione` |
| Il risultato di un lavoro finito a voce o sullo schermo (07/10) | il modello dell'agente per il riassunto per la voce (thinking spento, tempo massimo) | `calliope/agenti/risultato.py` → `trova`, `scegli`, `dal_disco`, `testo_intero`, `riassunto_voce`, `scheda`, `recenti`, `elenco_detto`, `chiave`, `converti` (dal 07/10: «fammene un PDF»); tool `risultato_lavoro` (`calliope/tools/agenti.py`), `agenti_risultato_s`; prove `prova_risultati.py`, `prova_risultati_ollama.py` |
| Modalità sviluppo (08/10): un'estensione o un programma come iter a fasi | solo libreria standard; lo stato su disco accanto ai lavori (`sviluppi.json`) | `calliope/sviluppo.py` → `Sviluppi` (`corrente`, `apri`, `passa`, `proposto`, `avviato`, `lavoro_finito`, `estensione_approvata`, `dati_turno`, `promemoria_giorno`, `scheda`), `passo_interno`, `estraneo`; tool `sviluppo` e `sviluppo_prova` in `calliope/tools/sviluppo.py` (`controlla_nuovo`, `apri_se_serve`); `Estensioni.prova_candidata`, `Estensioni.revisione`, `differenze` (`calliope/estensioni/servizio.py`); progetto [`docs/ricerche/2026-10-08-modalita-sviluppo.md`](../ricerche/2026-10-08-modalita-sviluppo.md); prove `prova_sviluppo.py`, `prova_sviluppo_ollama.py` |
| Estensioni permanenti e guardrail (04/10) | container della sandbox (Docker) per ogni chiamata, JSON-RPC su stdin/stdout (cornice stdio di MCP, senza SDK), solo libreria standard | `calliope/guardrail.py` → `valuta_porta`, `SecondoParere`, `domanda` (la porta delle estensioni: sicura / pericolosa / vietata; i tool di Calliope li decide `politica.decidi` dal 06/10); `calliope/estensioni/` → `Estensioni` (`servizio.py`), `Porta` (`porta.py`), `Esecuzione` (`esecuzione.py`), `Archivio` (`archivio.py`: versioni, impronta), `valida` (`manifesto.py`), `analizza` (`analisi.py`), runtime `_ospite.py` (nel container: `calliope_estensione`), prompt dell'agente (`prompt.py`: `sistema_estensione`), contratto delle capacità (`contratto.py`: `testo`, `CAPACITA_IDS`, CAPACITA.md); rete solo pubblica `calliope/web/rete.py` → `RetePubblica` (registro `uscite.jsonl`, `riepilogo`), dati riservati nel traffico `calliope/web/riservati.py` → `Riservati`, `da_contesto`; piano e permessi dell'agente in `agenti/ciclo.py` (`PIANO`, `CHIEDI_PERMESSO`, `_piano`, `_fuori_piano`); tool in `calliope/tools/estensioni.py`; progetto in `docs/ricerche/2026-10-04-estensioni-e-guardrail.md` (§11–§14 dal 05/10) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Domande dell'agente e file della persona** (03/10, `lavori_rispondi`, `delega_lavoro(file=…)`):
    un dato mancante lascia il lavoro in attesa con il suo contesto e la domanda si annuncia
    (azione in sospeso); «correggi lo script backup.py» manda all'agente una copia del file
    (dal satellite a pezzi con lo SHA-256) e il risultato torna come file nuovo. A secco
    (`prova_agenti_domande.py`); con il modello e la DGX no.

  - **Agenti in secondo piano** (02/10, `calliope/agenti/`, architettura della ricerca
    [`docs/ricerche/2026-10-02-llm-per-spark.md`](../ricerche/2026-10-02-llm-per-spark.md)):
    gemma riconosce un lavoro lungo (programmi e script, pagine web, relazioni lunghe,
    documenti da un modello, ricerche a più passi) e lo affida a un modello grande sulla DGX
    Spark (tunnel SSH automatico) o sullo stesso Ollama; codice in una sandbox con i test,
    documenti con lo scrittore di `calliope/documenti/`, annuncio a lavoro finito e scheda con
    il risultato sullo schermo. Provato con ssh e Ollama finti e con gemma4 locale come agente:
    la DGX vera non è ancora stata contattata. *[Storico (02/10): dalla sera del 02/10 Calliope gira sulla DGX come servizio; vedi [setup-dgx](setup-dgx.md).]*

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Arbitro con vLLM sulla stessa GPU** (04/10, `arbitro.py`, prova `prova_arbitro_vllm.py`,
  misura `prove/misura_arbitro_vllm.py`): sulla DGX la voce (Ollama) e l'agente (vLLM) hanno la
  stessa GPU, ma l'arbitro fermava solo un agente sullo stesso Ollama. Ora vale con
  `agenti_arbitro: auto` (stesso Ollama, server su 127.0.0.1/localhost o sullo stesso host della
  voce; mai con il tunnel), `sempre`, `mai`. Chiudere lo stream fa annullare la richiesta a vLLM
  0.29 (`with_cancellation`; dopo la misura 0 richieste in corso): si perde solo il passo, il
  prompt resta nella cache dei prefissi. Client con uno stream per thread (`interrompi(tid)`),
  più stream per l'arbitro, `ClienteCedevole` per OCR/estrazione dell'archivio e per lo
  scrittore dell'ufficio (che cede solo dal turno dopo quello che l'ha chiesto); il secondo
  parere del guardrail no (la voce lo aspetta, 4 s). Misura sulla DGX (26B su Ollama, 3
  relazioni da 1500 token in ciclo su vLLM, 20 domande per fase, 1 s di parlato, 4 s tra le
  domande): prima frase **base 0,72 s** (p90 1,56), **senza arbitro 2,02 s** (p90 4,21, vLLM
  124 token/s), **con arbitro 0,73 s** (p90 1,83). Limite: con le domande ogni ~7 s una
  generazione lunga non finiva mai (60 stream ceduti, 0 finiti): ripartiva da capo dopo ogni
  turno.

- **Pausa di vLLM invece della chiusura** (04/10, `arbitro.PausaServer`, prova
  `prova_arbitro_pausa.py`): con `VLLM_SERVER_DEV_MODE=1` (`calliope motore vllm agente rifai`
  con `PAUSA=1`, acceso sulla DGX) l'arbitro manda `POST /pause?mode=keep` quando si parla e
  `POST /resume` finita la ripresa: la generazione resta congelata con la sua cache, niente
  passo perso. Chiamate da un thread dell'arbitro (la voce non aspetta). Senza `/pause` (404) si
  chiudono gli stream come prima; pausa senza risposta (1 s) o con errore → ripiego per il
  turno e ripresa comunque, poi controlli con `/is_paused` per 15 s; ripresa garantita anche
  dopo `tenuta_max_s`, all'avvio (vLLM rimasto in pausa), a `Lavori.close` e su SIGTERM. Lo
  scrittore dell'ufficio che la voce aspetta non si congela nel suo turno (`vieta_pausa`: il
  server riparte subito, gli altri stream si chiudono come prima). Mai sul server della voce
  (`pausa_server`), spegnibile con `agenti_pausa_vllm`. Misura sulla DGX (stessa di sopra, 3
  generazioni da 300 token, 2 giri × 10 domande, una ogni ~7 s): prima frase base **0,76 s**
  (p90 1,53), chiusura 0,75 (p90 1,90), **pausa 0,75 s** (p90 1,48); generazioni finite 0 con la
  chiusura, **9 con la pausa**; pausa 56 ms di mediana sotto carico (22 a vuoto), ripresa 5 ms.
  Rischio: la modalità sviluppo apre senza chiave anche `/sleep`, `/collective_rpc`,
  `/update_weights`, `/reset_prefix_cache`, `/server_info`… a ogni processo della DGX (porta solo
  su 127.0.0.1, rete Docker sua invece della «bridge» condivisa con altri container); se Calliope
  morisse con SIGKILL a metà di un turno vLLM resterebbe in pausa fino al suo riavvio:
  `calliope motore vllm agente riprendi`.

- **Estensioni permanenti e guardrail** (04/10, progetto
  [`docs/ricerche/2026-10-04-estensioni-e-guardrail.md`](../ricerche/2026-10-04-estensioni-e-guardrail.md),
  prove `prova_estensioni.py`, `prova_estensioni_ollama.py`, `prova_estensioni_agente.py`):
  - **Ciclo di vita**: «fammi una funzione che…» (`estensione_crea`, solo chi amministra con
    la voce nella frase) → lavoro «estensione» dell'agente (prompt `estensioni/prompt.py`:
    `estensione.py` con `esegui(dati, calliope)`, `manifesto.json`, `test_estensione.py` con
    `CalliopeFinta`); la consegna si rifiuta all'agente finché manifesto e test non vanno
    (`controlla_consegna`) → versione «da approvare» con l'annuncio (permessi in parole, test
    rifatti dal programma, analisi statica) e la scheda di revisione personale →
    «approvala» → **frase di sfida sempre** (`conferme.chiedi_conferma`) → file in sola
    lettura e impronta SHA-256 → tool `est_<nome>` (parametri = `input` del manifesto). Ogni
    esecuzione ricontrolla l'impronta: file cambiati = non parte e si disattiva. Versione
    nuova = nuova approvazione; «indietro» con la sfida; «disattiva» subito; «rimuovi» con
    «Procedo?» in una risposta dopo; al più `estensioni_max_attive` (8).
  - **Esecuzione**: un container usa-e-getta per chiamata dall'immagine della sandbox
    (`--network none`, sola lettura, codice montato in sola lettura in `/lavoro`, nessun
    segreto né variabile dell'host, tetti del manifesto ≤ 30 s e 512 MB), audit hook come
    seconda linea. Tutto il resto passa dalla **porta stretta**: richieste JSON-RPC
    `calliope/<azione>` (casa, liste, agenda, schermi, dati propri, rete) che la porta esegue
    con **i tool veri di Calliope** e il livello di chi parla (al più familiare), dopo il
    guardrail. La rete la fa Calliope (dal 05/10 `RetePubblica`: vedi «Rete, scope e flussi»
    qui sotto). Risultato al modello come **dato non fidato** (`non_fidato`:
    niente azioni nella stessa risposta, fuori dalla storia dopo), mai come
    `risposta_finale`; i testi che parlano all'assistente o nominano un tool si tolgono
    (regola `estensione_testo_tolto`: il 04/10 gemma4 leggeva a voce «NOTA PER
    L'ASSISTENTE: chiama casa_comando…»).
  - **Guardrail** (`calliope/guardrail.py`): una tabella per i tool di Calliope (la guardia
    «azione non chiesta» di prima, stessi casi e stessa domanda) e per la porta. Dalla porta
    una **pericolosa si ferma sempre**: comandi della casa e invii verso l'esterno con la
    sfida; togliere da una lista, cancellare i propri dati, più di 10 voci, rete dopo aver
    letto dati di casa con «sì» o «sì, sempre» (per persona, versione e bersaglio,
    revocabile). Vietate: azioni fuori dal manifesto, host nuovi, http, oltre le quote (50
    richieste, 3 comandi della casa, 10 di rete). Il «sì» vale solo per chi ha usato
    l'estensione e mai nella stessa risposta della domanda; senza risposta in
    `estensioni_conferma_s` (120 s) l'azione è negata. Secondo parere di qwen3.6 sulle
    richieste con testo libero: alza soltanto, 4 s al massimo. Ogni decisione in
    `estensioni/decisioni.jsonl` e nel registro dei turni (`estensione_*`).
  - **Standard**: cornice stdio di MCP (`tools/list`, `tools/call`, risultati MCP) senza
    l'SDK (`cryptography` senza wheel win_arm64, solo async); un tool per estensione invece
    di un `estensione_usa` generico: argomenti vincolati dallo schema, prefisso che cambia
    solo all'approvazione.
  - **Misure**: esecuzione con una richiesta alla porta 0,16 s di mediana nel container vero
    (DGX, massimo 0,18), 0,13–0,15 s con il docker finto; `prova_estensioni_ollama` 28/28 in
    2 giri (gemma4:e4b, prima frase mediana 0,66 s; la prima chiamata dopo l'approvazione
    rilegge il prefisso: 1,0–2,6 s).
    **Agente vero sulla DGX** (qwen3.6 su vLLM, container vero, HA vero in sola lettura):
    convertitore di unità in 15,4 min (vLLM occupato da altri lavori; 7 passi, 24 test che
    passano, nessuna parte a rischio) e «temperatura stanza» in 3,7 min (9 passi, 8 test):
    approvate e usate in 0,15 s a chiamata, «In cucina ci sono 21 gradi, non fa freddo.» dalla
    casa vera attraverso la porta; per «camera» (nessun sensore) l'errore torna all'estensione,
    che lo dice. Trovato e corretto: al primo giro l'agente aveva copiato il nome d'esempio del
    prompt e la funzione della temperatura stava per diventare la versione 2 del convertitore
    (ora la consegna e la candidata rifiutano un nome già preso).
  - **Rete, scope e flussi** (05/10, decisioni di Dario: internet pubblico in lettura libero,
    dati personali solo negli scope, verso fuori solo lungo i flussi approvati, il resto
    vietato; §11–§14 del progetto). Manifesto a scope (`legge`, `scrive`, `rete`, `invia`);
    `RetePubblica` (solo internet pubblico, porte 80/443, reindirizzamenti ricontrollati,
    tetto al minuto, registro `estensioni/uscite.jsonl` con il solo host, riepilogo della
    settimana nella capacità «agenti»); ogni lettura personale contamina l'esecuzione (anche
    nelle esecuzioni dopo, dai dati propri) e la rete va solo lungo un flusso in https;
    argomenti con un dato riservato = niente rete (`estensione_input_riservato`); ricordi e
    dati privati mai nel traffico, anche codificati o a pezzi (`web/riservati.py`); dati letti
    scritti in una lista o nel nome di un timer: conferma (`estensione_dati_condivisi`).
    **Banco d'attacco** `prova_estensioni_attacchi.py` (rete interna, IPv4 travestiti, NAT64,
    rebinding, reindirizzamenti, slowloris, bombe, dati esca, flussi, HTML ostile,
    `scarica_esempio`): **zero passaggi** su 76, a secco e con il container vero; trovati e
    corretti il tetto di tempo aggirato a pezzi (20 s invece di 2), `dati_elenca` che non
    contaminava, l'host con il segreto nei registri.
  - **Contratto delle capacità e piano** (05/10, dopo il lavoro L1 del 04/10: 66 000 token di
    ragionamento senza un file): contratto generato dal codice (porta con esempi, scope e
    classe chiesta al guardrail, tetti, impossibili con l'alternativa) nel prompt e in
    `CAPACITA.md` in sola lettura; `piano(...)` primo passo obbligatorio (un'impossibile chiude
    il lavoro alla prima passata), `chiedi_permesso` per flussi, POST e comandi della casa
    (domanda alla persona; un permesso fuori dal piano fa rifiutare la consegna); guardia sul
    ragionamento a vuoto (`agenti_token_senza_strumenti` 12 000, `agenti_minuti_senza_strumenti`
    5: spinta, poi chiusura). **Prova vera** (qwen3.6, DGX, container vero): «leggi la tabella
    delle regioni da Wikipedia e dimmi capoluogo e abitanti» → piano alla **prima passata**
    (1 313 token), pagina con `scarica_esempio`, 11/11 test, candidata in **2,1 min** (14
    passi, 6 980 token); provata sulla pagina vera: Toscana, Firenze, 3 657 716 abitanti. Gli
    script d'esplorazione non entrano più nella versione.
  - **Restano**: documenti, messaggi e file ai satelliti dalla porta (regole già nella
    tabella); estensioni a orario; la firma delle versioni (oggi l'impronta sta nell'indice,
    accanto ai dati di Calliope).

- **Programmi eseguiti in diretta e C#** (04/10, `calliope/agenti/esecuzione.py`, `linguaggi.py`; prove `prova_esecuzione.py`, `--docker` sulla DGX). A lavoro di codice finito, se chi l'ha chiesto ha uno schermo personale, il programma (`consegna(programma=…)` o riconosciuto: unico file, main, `__main__`; un modulo di sole funzioni no) si esegue in una copia della cartella, nella stessa sandbox Docker, e stdout/stderr vanno in diretta sulla scheda `esecuzione:<lavoro>-<n>` (al più ogni 0,3 s, tempo che scorre, codice d'uscita, oltre 64 KB inizio e coda; uscita anche in `esecuzione-<n>.txt` tra i risultati). L'annuncio aspetta al più 8 s e dice com'è finito con le ultime 1–2 righe, mai tutto l'output; oltre, un annuncio a parte. «Fammelo vedere», «eseguilo con 3 e 5» (anche scritto nella casella): `lavori_esegui`, dati come argomenti **e** righe dello stdin; «fermalo»: `lavori_annulla` ferma prima il programma. **C#**: immagine a parte (`calliope motore sandbox costruisci csharp`, 318 MB contro 974 dell'SDK; `dotnet run` senza rete fallisce con NU1301, quindi csc diretto): compila ed esegue in **0,52 s** di mediana contro 0,17 s di Python (DGX); rete, sola lettura, utente non root e tempo scaduto provati; nel C# non c'è l'audit hook (può avviare processi, dentro il container e il tetto `--pids-limit`). L'agente vede `esegui_csharp` e i linguaggi solo se l'immagine c'è; un linguaggio che non c'è (Rust) → «impossibile» in 1 passata. Caso vero con qwen3.6 su vLLM: «scrivi un software in C# che fa un calcolo, inventa gli input casuali e mostrami input e output» → 18 s, 4 passate, programma eseguito sullo schermo in 0,5 s. Node/JavaScript: non ancora (sarebbe un'altra immagine come quella del C#, node:22-slim, dimensione da misurare). La pagina aggiorna le schede con la stessa chiave al loro posto (solo i nodi cambiati, niente animazione di entrata: prima lampeggiavano), con un segno leggero ai cambi di stato.

- **Agenti in secondo piano** (02/10, `calliope/agenti/`, `calliope/tools/agenti.py`; prove
  `prova_agenti.py` a secco, `prova_agenti_ollama.py`, banco `prova_lavori.py`; passi per la
  DGX in `prove/LEGGIMI.md`). Architettura della ricerca del 02/10: gemma davanti, un modello
  grande dietro. **La DGX vera non è ancora stata contattata** *[Storico (02/10): dalla sera del 02/10 Calliope gira sulla DGX come servizio; vedi [setup-dgx](setup-dgx.md).]*: tunnel, Ollama remoto e
  `qwen3.6:35b` sono provati solo con un ssh finto e un Ollama finto.
  - **Collegamento**: `dgx.yaml` (tunnel o diretto) oppure `agenti_url`; tunnel `ssh -N -L
    127.0.0.1:11435:127.0.0.1:11434 -- <alias>` con `BatchMode=yes`,
    `ExitOnForwardFailure=yes`, `ServerAliveInterval=15`, niente agent forwarding né X11,
    stdin chiuso. Pronto quando la porta locale accetta connessioni; riaperto da solo se cade
    (attese 2, 5, 15, 30, 60 s; solo se era già stato aperto: con la VPN spenta dall'avvio
    non riprova ogni minuto, ci pensa il lavoro dopo). ssh sta in un **job object** con
    KILL_ON_JOB_CLOSE: se Calliope muore la porta si libera. L'errore di ssh si riduce a un
    codice (`tunnel.classifica`: vpn, nome, chiave, host_sconosciuto, porta_locale,
    rifiutato, config_ssh, timeout) e il suo testo, che contiene utente e indirizzo, non si
    conserva né si stampa. La porta locale già occupata si rifiuta prima di avviare ssh (un
    Ollama su quella porta verrebbe scambiato per la DGX).
  - **La voce non aspetta mai**: i tool leggono lo stato in memoria; tunnel e Ollama remoto
    li tocca solo il thread dei lavori (o quello di verifica). Misure a secco: delega 0,1 ms,
    `lavori_stato` e `delega_lavoro` 0,1 ms anche con il tunnel bloccato (ssh muto), annullo
    0,4 ms, `voce_occupata` 0,3 ms. Una delega con l'agente irraggiungibile da meno di 30 s
    risponde subito «Adesso non posso: la DGX non risponde (VPN spenta?)…» e riprova in
    secondo piano; più vecchia, si lascia provare al lavoro (la VPN può essere tornata).
  - **Arbitro** (`arbitro.py`), solo con l'agente sullo **stesso Ollama** della voce:
    `Listener.on_speech_start` (inizio del parlato rivolto a Calliope: sveglia o nome
    sentito) e l'inizio di ogni risposta chiudono lo stream dell'agente in un thread a parte
    (Ollama smette di generare); l'agente riprende `agenti_ripresa_s` (3 s) dopo la fine
    della risposta, rifacendo il passo. Stesso modello della voce: `num_ctx` della voce,
    altrimenti Ollama ricaricherebbe il modello a ogni cambio. Con la DGX l'arbitro non ferma
    niente.
  - **Sandbox del codice** (`sandbox.py`, `_avvio.py`, `winjob.py`): sei strumenti
    (elenca, leggi, scrivi, esegui un .py, esegui i test, consegna), niente shell. Percorsi
    solo relativi, niente «..», «:», nomi riservati, collegamenti, nomi di moduli di Python
    («ctypes.py» nasconderebbe il vero), solo estensioni di testo; tetti a file e spazio.
    Esecuzione con l'interprete di **base** in modalità isolata (`-I -B`: il `python.exe` del
    venv è un lanciatore che crea un secondo processo), ambiente ripulito (niente CALLIOPE_*,
    PATH ridotto, TEMP e HOME nella cartella, niente proxy, numpy a un thread), dentro un
    **job object** con un solo processo attivo, tetto di memoria (`agenti_memoria_mb`),
    restrizioni UI (appunti, finestre, desktop), priorità bassa, tempo massimo
    (`agenti_esecuzione_s`). Prima di una riga del modello un **audit hook** rifiuta rete
    (ogni socket, client della libreria standard), processi (subprocess, os.system,
    startfile, `_winapi.*`), le operazioni di ctypes (il modulo si importa: numpy e openpyxl
    lo vogliono, ma DLL, chiamate e letture di memoria sono bloccate), winreg,
    sottointerpreti, lettura ed elenco fuori dalla cartella e da quelle di Python, scrittura
    fuori dalla cartella. La cartella del lavoro entra in `sys.path` solo dopo l'hook: prima
    un «ctypes.py» dell'agente veniva importato al posto del vero (trovato dalla prova).
    **Sulla DGX, un container per esecuzione** (03/10, motore «docker»,
    `agenti_sandbox_motore: auto`, rapporto
    [`docs/ricerche/2026-10-03-sandbox.md`](../ricerche/2026-10-03-sandbox.md)): immagine
    `calliope-sandbox:<hash del Dockerfile>` (`setup/linux/sandbox/Dockerfile`, Python 3.12 con
    numpy, openpyxl, python-docx, fpdf2, PyYAML; 288 MB; `calliope motore sandbox costruisci`,
    proposta anche da `installa.sh`), `--network none`, `--read-only` con la sola cartella del
    lavoro scrivibile e `/tmp` noexec, uid di Calliope (non root), `--cap-drop ALL`,
    `no-new-privileges`, seccomp, `--memory` + `--ulimit data` (MemoryError), `--pids-limit 32`,
    `--cpus`, `timeout -s KILL` dentro (un Calliope ucciso non lascia container), `docker kill`
    a fine tempo e all'annullo; `_avvio.py` montato in sola lettura, l'audit hook resta come
    seconda linea. Costo: **+0,12–0,18 s per esecuzione** (0,17–0,22 contro 0,04–0,06 s); scelta del motore
    ~15 ms, dal thread dei lavori. Provato sulla DGX (`prova_sandbox.py --docker`): tutti gli
    attacchi di `prova_agenti`, e senza hook solo loopback, nessuna connessione né DNS, disco
    in sola lettura, CapEff 0, file dell'host e socket di Docker invisibili, fork bomb ferma a
    30 processi. bubblewrap e `unshare -r` non vanno: Ubuntu 24.04 limita le user namespace
    non privilegiate con AppArmor. Dove Docker o l'immagine mancano (e su Windows) resta il
    motore «processo», e la capacità «agenti» dice quale isolamento è attivo e il passo;
    con `docker` esplicito e non pronto il codice non si esegue.
    **Cosa resta un rischio**: con il container, il kernel condiviso (namespace, cgroup,
    seccomp, non una macchina virtuale) e l'uid di Calliope dentro (un'evasione avrebbe i
    suoi permessi); l'utente di Calliope nel gruppo `docker` vale root sull'host (il codice
    dell'agente non vede il socket). Con il motore «processo» (Windows, o Docker assente): la
    rete la blocca solo l'audit hook, che non è un confine di sicurezza (PEP 578: un'estensione
    nativa o un difetto dell'interprete potrebbero aggirarlo), e il processo ha l'utente di
    Calliope; per Windows un isolamento vero vorrebbe un utente dedicato, AppContainer o WSL2.
    Il codice prodotto non si esegue mai fuori dalla sandbox. Fuori da Windows, nel motore
    «processo»: `resource` (memoria, niente figli) e il gruppo di processi.
  - **Permessi** nel codice: delegare dai familiari in su (`agenti_livello`), il codice solo
    chi amministra (`agenti_livello_codice`), riconosciuto dalla voce nella frase; gli ospiti
    non vedono i tool (se il modello ne scrive uno, il registro rifiuta). Conferma
    (`agenti_conferma: costosi`): codice, ricerche, coda occupata, modello dell'agente non
    caricato → «… Procedo?» con l'azione in sospeso; parte solo con `proposta` = l'id del
    lavoro, nella risposta dopo e della stessa persona. Il parametro si chiamava `conferma` e
    gemma4 ci metteva «Sì» già alla prima richiesta (3 casi su 7 nella prima misura): ora un
    valore che non è un id si ignora (`lavori_proposta_non_id`), e il modello che dopo il «sì»
    richiama la delega senza id (stesso tipo, compito simile) vale come conferma
    (`lavori_conferma_implicita`).
  - **Criterio di delega** (descrizione del tool e prompt, nessuna regola): il risultato è un
    programma o un file complesso; le domande brevi di programmazione e le spiegazioni le
    risponde la voce; lettere, tabelle ed elenchi semplici restano a `documento_crea`. Senza
    «pagine web» nell'elenco «scrivimi una pagina web per la lista della spesa» diventava
    «Non posso creare pagine web». «Come si scrive un ciclo for in Python, in breve?», che
    la ricerca aveva visto delegare 2 volte su 2, ora resta alla voce: 0 deleghe su 6
    (`prova_agenti_ollama`) più 0 su 4 in una sonda; «cos'è una funzione ricorsiva?» e
    «cosa vuol dire API?» lo stesso. Con i tool degli agenti «Fai un PDF con l'elenco dei
    compiti di Matteo…» andava a `delega_lavoro` (2 su 2 in `prova_documenti_ollama`): la
    stessa avvertenza nella descrizione di `delega_lavoro` non cambiava niente (0/4 giusti),
    rinominare il parametro `compito` nemmeno (2/4); una frase nel prompt con «elenco» la
    risolveva (4/4) ma spostava «mettimi sullo schermo i miei appuntamenti» su
    `appuntamenti_elenca` (`prova_schermi_ollama` 36/38). Scelto: «anche di compiti o di
    cose da fare» tra i documenti di `documento_crea`, solo con gli agenti: 44/44 su 11 frasi
    (4 mai viste: gita, turni delle pulizie, compiti delle vacanze, grafico dal CSV).
  - **Misure con Ollama** (02/10, 2 giri, gemma4:e4b-it-qat, agente finto lento):
    `prova_agenti_ollama` 40/40 (20 frasi: delega con proposta e «sì», stato, annullo,
    relazione, ricerca con «no», correzione, pagina web; i non-delegabili; documenti brevi;
    permessi), prima frase mediana 0,58 s. Con i tre tool registrati le prove di prima
    restano ai loro livelli: `prova_pc_ollama` 62/62 (0,49 s), `prova_casa` 42/42 (0,53),
    `prova_documenti_ollama` 34/34 (1,47), `prova_casa_ha_ollama` 58/58 (0,44),
    `prova_stato_ollama` 34/34 (0,44), `prova_schermi_ollama` 38/38 (0,62; schermi spenti
    0,50 s, accesi 0,46). In `prova_schermi_ollama` il modello mandava a volte
    `persona="me"` per «come mio schermo personale» (2 volte su 8 in tre giri): ora vale chi
    parla (`schermi.py`, regola `persona_io`, caso contrario «Gino» nelle prove).
  - **Risultati**: una cartella per lavoro in Documenti\Calliope\Lavori (`agenti_risultati`)
    con i file e `lavoro.json` (esito, test, passi, token, minuti); la sandbox in `lavori/`
    (fuori da git, `agenti_sandbox`). Annuncio con il segnale acustico quando c'è silenzio,
    nella storia (`Brain.record_announcement`) e nel registro dei turni (`esito: lavoro`):
    «ho finito «…»: <riassunto dell'agente senza codice né simboli, `per_la_voce`>. I test
    passano, 3 su 3.» — l'esito dei test lo dice il programma, che li rifà alla fine. La
    scheda `lavoro` (personale, il codice intero con gli a capo) va agli schermi di chi l'ha
    chiesto; per i documenti la scheda `documento`.
  - **Banco `prove/prova_lavori.py` in locale** (02/10; agente gemma4:e4b-it-qat sullo
    stesso Ollama, thinking acceso, tetti 16 passate e 6 minuti; 26 minuti in tutto): serve
    a provare il banco, non l'agente. **Codice 7/12** con i test nascosti alla fine, 5/12 al
    primo tentativo (falliti: data già nel nome rinominata, PowerShell senza ShouldProcess,
    «oggi» passato come testo, numeri romani minuscoli, argparse; tre lavori fermati dal tetto
    dei passi, due di questi comunque giusti); 22 minuti. **Documenti 8/12** giusti (10
    validi): il preventivo senza cliente chiede i dati invece di inventarli, i 3 modelli
    vanno; mancano titoli di sezione in due relazioni, due numeri «inventati» sono calcoli
    del modello (55 per cento di immissione da 45 di autoconsumo), un errore dell'Ollama
    dell'agente non si è ripetuto (ora il messaggio va nel log). **Contesa** (5 domande × 2,
    prima frase della voce): da sola mediana 0,44 s (massimo 1,49), con un lavoro senza
    arbitro 0,45 s ma **massimo 50,9 s** (una risposta aspetta la fine della generazione),
    con l'arbitro **0,50 s, massimo 0,82 s** (+0,06 s sulla mediana: soglia +0,15 rispettata).
    Contro la DGX il banco si lancia con `--dgx`.
  - **Banco dei documenti contro la DGX** (02/10, vLLM 0.29.0, `qwen3.6-35b` =
    Qwen3.6-35B-A3B-NVFP4, motore «openai»; codice 11/12). Il primo giro dava documenti
    7/12. **Criteri corretti** (`prova_lavori.py`, prova a secco `prova_lavori_criteri.py`):
    un titolo di sezione vale anche come prima riga breve di un paragrafo o paragrafo breve
    seguito da altro (il formato non ha il grassetto), le relazioni vogliono le sezioni
    **chieste per nome**, la scaletta sezioni **piene**, il business plan «descrizione» e
    «mercato»; un dato vale anche in lettere («trenta giorni»); un numero non detto è
    inventato salvo che si ricavi con **un** calcolo semplice dai dati (somma, differenza,
    prodotto, rapporto, quota e variazione percentuale, complemento a 100 di una percentuale
    detta, somma di dati consecutivi; operandi > 10 e non anni, per non coprire ogni numero
    di due cifre), e i numeri da 11 a 100 scritti **in lettere** si controllano come le
    cifre. Il JSON di ogni documento resta in `<uscita>/documenti/` (`--rivaluta`);
    `--scrittore` cambia il modello dei documenti. Con i criteri nuovi il primo giro vale
    **9/12**, ma i difetti cambiano: d03 («trenta giorni») e d08 (55 = 100 − 45) erano
    il banco; erano veri «118» non chiesto per la babysitter, «circa quindici alberi» per
    tonnellata di carta, il business plan impaginato come lettera. **Correzioni dello
    scrittore**, solo per la strada degli agenti: la bozza passa a `Writer.write(bozza=…)` e
    non decide più se è una lettera (con «la domanda di prodotti freschi» nella bozza
    `is_letter` scattava); i titoli della bozza diventano blocchi `titolo` e i punti blocchi
    `elenco` (prima finivano dentro i paragrafi: «INTRODUZIONE\nLa presente…», «- punto»);
    la bozza usa i dati in frasi complete (prima ricopiava la richiesta), in cifre, senza
    numeri non detti né calcolati; `scrittore.empty_sections`: con 2 o più titoli senza
    contenuto lo scrittore riprova (una scaletta aveva il testo solo nelle prime 2
    diapositive su 8). Giri dopo le correzioni: **10/12, 11/12, 10/12** (7,6–10,2 minuti per
    12 documenti, 0,7–1,4 min l'uno; i modelli 0,1 min). I difetti rimasti sono del modello:
    numeri d'emergenza non chiesti (112/118, 2 giri su 4), fatti inventati nella scaletta
    («17 alberi», «verso il 70 percento»), «recupero entro 24 mesi», un errore di conto
    scritto in lettere («il restante cinquanta per cento»: era 55), una volta gli apostrofi
    persi in un documento («dellambiente»). **Italiano**: da 3/5 (frasi ricopiate,
    «SEZIONE IMPIANTO», verbale con ogni decisione ripetuta tre volte, «SEGREARIO») a 4/5.
    **Scrittori alternativi** sull'Ollama 0.35.0 della DGX (tunnel a parte, `format` senza
    tool: nessun errore CUDA): `qwen3.8` (27B densa) **9/12**, l'italiano più ricco (4/5
    abbondante, ma «evita la taglio») ma inventa di più (articolo 1117 del codice civile, 112 e 118, epinefrina, «obiettivo UE
    del 65 per cento nel 2025»), 11,9 min; `gpt-oss:20b` **8/12**, italiano 3/5 («non è
    stato intervenuto»), sanzioni da 50 euro e date inventate, un file chiamato
    «Introduzione.docx», 10,9 min. `gpt-oss:120b` non provato: 65 GB con vLLM acceso e
    ~60 GB liberi. Scelta: **qwen3.6 su vLLM** per documenti e modelli.
  - **Capacità «agenti»** (la 13ª *[storico, 02/10: oggi le capacità sono 18]*): attiva con la descrizione («qwen3.6:35b sulla DGX via
    tunnel SSH «dgx» (porta locale 11435)», mai l'host), da configurare senza `dgx.yaml`,
    guasta con il motivo e il passo (VPN, chiave, impronta, porta, Ollama remoto), mancante
    con «sulla DGX manca qwen3.6:35b: scaricalo con ollama pull». Dentro Calliope è dinamica
    (l'ultimo tentativo del thread dei lavori, nessuna rete per guardarla); da terminale
    (`python -m calliope.stato`) solo la configurazione: il tunnel si apre solo con
    `python -m calliope.agenti --prova`. Nel prompt conta come presente se i tool ci sono
    (la VPN va e viene, il prefisso no).
  - **Modelli di documento** (`modelli.py`): JSON con i campi e i blocchi del formato di
    `calliope/documenti/` con `{{campo}}`; schema dei campi (null ammesso) → il modello lo
    riempie senza thinking → campi obbligatori mancanti = domanda («Per compilare
    «Preventivo…» mi servono: il nome del cliente…»), mai inventati → compilazione e render.
    Mancano i `.docx` veri (docxtpl, carta intestata) e le presentazioni `.pptx`. *[Superato il 03/10: docxtpl e python-pptx nell'ufficio, `calliope/ufficio/modelli.py`; vedi [documenti-ufficio](documenti-ufficio.md).]*
  - **Domande a metà lavoro** (03/10, `servizio.py`, tool `lavori_rispondi`): consegna con
    `mancano_dati` (o un modello con campi vuoti) non chiude più il lavoro: resta `in_attesa`
    con conversazione dell'agente, sandbox e campi già compilati; la domanda si annuncia con
    il segnale quando c'è silenzio e diventa un'azione in sospeso con un testo suo
    (`RISPOSTA_MSG`, `set_pending` con «messaggio»: la risposta è un dato, non un «sì»).
    Risposta nel turno dopo o più tardi («per il lavoro della relazione: …», per id o parole
    del titolo); solo chi l'ha chiesto o chi amministra (`lavori_risposta_altrui`). L'attesa
    non conta nel tetto dei minuti; al più `agenti_domande_max` (3) domande, poi si chiude
    come prima; dopo `agenti_attesa_risposta_min` (120) si chiude da solo e lo dice.
  - **File della persona all'agente** (03/10, `file_utente.py`): `delega_lavoro(file=nome o
    numero)` cerca con l'esecutore del PC e le regole di `pc_cerca_file` (proprietari o chi
    amministra, o un documento appena scritto per chi parla; `lavori_file_permesso`), conferma
    **sempre** esplicita («Mando una copia dello script Python «backup»… Procedo?», con più
    file «Quale mando all'agente?»). Al «sì» la copia parte in un thread (`PCExecutor.copia_file`;
    dal satellite `file_richiesta` → `file_dati` + pezzi b"G" con lo SHA-256, maniglia,
    estensione, dimensione e schermo bloccato ricontrollati là): la voce non aspetta (0,8 ms
    con il portatile lento). Solo testo, codice, Word, Excel, PDF, al più `agenti_file_max_mb`
    (10). Il codice lavora sulla copia nella sandbox (Word, Excel e PDF solo da Python:
    `Sandbox.metti`); per gli altri lavori il testo (python-docx, openpyxl, pypdf) entra nella
    richiesta. Il risultato è un file nuovo («backup (corretto).py», «spese
    (modificato).xlsx»): con il satellite `RemoteDelivery` lo mette in Documenti\Calliope del
    portatile (il satellite ora accetta anche i file di testo; mai .js, .bat, .vbs: arrivano
    come .txt), altrimenti resta nella cartella del lavoro. L'originale non si tocca mai.
  - **Avanzamento in diretta sugli schermi** (03/10, `avanzamento.py`, prova
    `prova_avanzamento.py`): la scheda `lavoro:<id>` compare al «sì» («in coda», in cima) e si
    aggiorna al suo posto (`sposta: false`) mentre l'agente lavora, solo sugli schermi personali
    di chi l'ha chiesto (mai nella zona grigia): passo in parole («prova il codice: 2 test su 3
    passano», «scrive la bozza», «cerca nella biblioteca «…»») con gli ultimi 6, file scritti
    (nomi, righe, anteprima breve del codice), test, testo in arrivo (risposta, ragionamento,
    codice negli argomenti di scrivi_file con vLLM; mai il JSON dei documenti), passate, token e
    minuti **sui tetti** (nessuna percentuale inventata; il tempo conta nella pagina), «in pausa:
    sto rispondendo a voce» con l'arbitro. Chi lavora fa solo `Lavoro.nota` / il cambio di
    `passo` e `stato` (~1 µs: lock e `notify`); costruisce e manda un thread suo, al più una
    scheda ogni 0,5 s per lavoro, i pezzi accorpati. Finale, domanda, annullo e chiusura: la
    scheda di `Lavori.scheda` (codice intero o anteprima del documento) con la stessa chiave, in
    cima; dopo, più niente. Senza schermi (o `schermi_automatiche` spento) niente osservatore né
    thread. Un aggiornamento automatico non diventa «l'ultima cosa mostrata» di
    `schermo_mostra` (hub.py). Provata a secco e nella pagina vera (Edge headless), non ancora
    con un lavoro vero sulla DGX.

- **Contesto degli agenti** (05/10, fase 2b, `calliope/agenti/contesto_lavoro.py`, rapporto
  [`docs/ricerche/2026-10-05-contesto-agenti.md`](../ricerche/2026-10-05-contesto-agenti.md)):
  `agenti_num_ctx: auto` (vLLM: `max_model_len` e cache di /metrics / `agenti_contesti_paralleli`,
  sulla DGX 131 072; Ollama remoto al più 32 768; stesso Ollama della voce: la sua finestra);
  niente più «…[omesso]»: i risultati lunghi per intero in `.calliope/passo-N.txt` (fuori da
  risultati e versioni), rilegibili con `leggi_file` (`da_carattere`), oltre il 50 % anche i
  vecchi, oltre il 75 % il diario del lavoro (dal modello o estrattivo), compito e ultimi 3 passi
  interi; domande a metà lavoro col contesto compattato. Per passata `agenti_token_passata` e
  `agenti_ragionamento_passata` → `thinking_token_budget` di vLLM (verificato con 0.29 e
  qwen3.6); ragionamento contato a parte in `lavoro.json`. Stesso parser lungo, 8 minuti: test
  nascosto 0/3 prima (una passata da 16 384 token di ragionamento, 365 s) → 3/3 dopo. **Diario
  con qwen3.6** (06/10, finestra forzata a 16 384, §4–5 del rapporto): il modello scrive solo le
  voci nuove con i «dati» (valore e fonte), il codice le unisce; relazione 16/21 → 19/21 fatti
  (21/21 a 131 072), 6–17 s per diario; niente diario se toglie meno di quanto cresce, schema con
  lunghezze massime (ragionava dentro il JSON), ragionamento al più metà della passata (con 16 384
  scrivi_file si troncava), letture uguali nella stessa passata non rifatte, soglia dura dal
  risultato più vecchio, nota dalla terza rilettura uguale. Con 16 384 il codice non regge
  (riletture a turno di codice e test, 0/3 contro 3/3): serve almeno 32 768. **Tetto dei token
  per tipo**: `agenti_token_minuto` × `agenti_tempo_max_min` (codice 5 000, misurati 2 800–4 300
  al minuto, massimo ~4 470; ricerche e documenti 3 000), `agenti_max_token` 0 = nessun massimo
  comune; avviso di chiusura vicino ai tetti (`AVVISO_FINE`), lavoro fermato con motivo, file e
  test rifatti.

- **Correzioni dalla verifica sulla DGX del 04/10** (agente vero: qwen3.6-35b su vLLM via
  tunnel, sandbox in processo sul portatile):
  - **Dati della persona** (`ciclo.DATI_PROPRI` in `SISTEMA_CODICE`, anche nella bozza dei
    documenti): un valore «mio», «della mia azienda», «di casa» non si inventa né si
    sostituisce con uno tipico; si chiede con `consegna esito=mancano_dati` prima del codice.
    «Rimborso con la tariffa al chilometro che usa la mia azienda», 5 lavori: prima 3/5
    chiedono (2 volte 0,21 €/km inventato), dopo 5/5 chiedono prima di scrivere codice e con
    «0,42 euro al chilometro» 5/5 stampano 191,31. Banco: compito c13.
  - **Consegna con i test rossi** (`RIMANDI_MAX` = 2): consegna «fatto», o il solo testo dopo
    la spinta, rifà i test; se falliscono e restano 2 passate e il 10 % di token e tempo,
    torna all'agente con l'uscita. Sul codice fiscale (test nascosti) non basta: qwen3.6 non
    conosce l'algoritmo del carattere di controllo e scrive test coerenti con il suo errore
    (nascosti 0/5 prima, 0/8 dopo); i due lavori finiti con i test rossi della seconda misura
    erano a 55–57 mila token su 60 mila (il ragionamento): un solo rimando in 8 lavori.
    17–30 minuti l'uno con 3–5 lavori insieme, 4 su 13 fermati dal tetto dei 30 minuti.
  - Casa: i `button`/`input_button` di riavvio e spegnimento (classe `restart`, «spegn*»,
    «shutdown», «riavvi*», «reboot», «riconnett*» nel nome o nell'id) in sola lettura per
    tutti, salvo `casa_consentiti` (`Regole.riavvio`, frase `FRASI["riavvio"]`).
  - `llm_keep_alive`: il «30m» dell'esempio in `calliope.yaml` non conta come scritto (vale
    il -1 del profilo del 26B), `CALLIOPE_LLM_KEEP_ALIVE` vince su tutto, e `python -m prove
    --ollama` manda il keep_alive della voce (una prova non lo accorcia più).
  - Modelli di documento: «Oggi è…» nel prompt (la data del documento, se non detta, è oggi)
    e «mi serve la data… Me la dici?» con un dato solo. Titoli dei lavori tagliati anche a
    «(» e detti senza nomi di file (`servizio.titolo_detto`). `sonda_ha.py` maschera
    `casa_url` e consiglia `casa_tls_nome` solo con un IP. `prova_telefono_audio` regge il
    reset dentro `URLError` (Linux). `prova_rinomina_ollama` e `prova_scritto_ollama` nel
    runner con Ollama.

## Lavori interrotti da un riavvio (06/10)

Caso vero della DGX: alle 16:56 Dario fa partire «gioco memory da giocare sullo schermo»
(codice, qwen3.6 su vLLM, sandbox `~/calliope/lavori/L2-20261006-165635` con gioco.js, logica.js
e logica.test.js); alle 17:07 un `calliope aggiorna` riavvia il servizio e il lavoro muore.
Dopo il riavvio Calliope non dice niente e `lavori_stato` risponde «Non ho lavori in corso.»:
coda e stato stavano solo in memoria (`lavoro.json` si scriveva a lavoro fermo o finito).

Ora (`calliope/agenti/ripresa.py`):
- **stato su disco**: a ogni cambio (in coda, in corso, cartella e sandbox scelte, in attesa,
  finito, annullato, scaduto) il servizio scrive `in_corso.json` nella cartella delle sandbox
  (`agenti_sandbox`, sulla DGX `~/calliope/lavori/`), atomico (`persistenza.scrivi_json`), con
  il pid del processo. Non durante la chiusura: i lavori fermati da `close()` restano «in
  corso» e al prossimo avvio diventano interrotti (stesso percorso per SIGTERM e per un
  crollo). Un file scritto dallo stesso processo non si legge (servizio ricreato, prove);
- **all'avvio** i lavori in coda o in corso diventano `interrotto` (`lavoro.json` nella
  cartella lo dice); gli id ripartono dopo il più alto del file;
- **annuncio** dal thread dei lavori, nella coda degli annunci come gli altri (al primo
  silenzio, verso la corsia e il satellite di chi l'aveva chiesto): «Mario, il lavoro «…» si
  è interrotto per un riavvio di Calliope. L'agente aveva già scritto 2 file, e ripartirei da
  quelli. Lo rifaccio?», con l'azione in sospeso `delega_lavoro(proposta=<id>)`. Un annuncio
  per persona («i lavori «A» e «B» … Li rifaccio?»: al «sì» ripartono tutti). Una volta sola
  (`annunciato` resta nel file). Solo se il lavoro era vivo da meno di
  `agenti_interrotti_annuncio_h` ore (3); più vecchi solo nell'elenco, e dopo un giorno escono;
- **al «sì»** (`Lavori.offerta` vale anche per gli interrotti annunciati, senza turno: il «sì»
  lo controlla l'azione in sospeso del Brain, solo la stessa persona) un lavoro nuovo con lo
  stesso compito, la stessa persona e la stessa cartella dei risultati. **Codice ed estensioni
  ripartono dalla sandbox di prima** (`sandbox_da`): la scelta più semplice e sicura, perché
  la sandbox è una cartella, i file sono dell'agente nello stesso isolamento, l'agente li vede
  nell'elenco dei file e un vincolo gli dice che il lavoro era stato interrotto; i
  `file_iniziali` che ci sono già non si riscrivono (una modifica a metà di un'estensione
  resta). La conversazione dell'agente invece riparte da capo: a metà lavoro non è salvata
  (è lo stato meno sicuro da riprendere), le risposte già date passano nei vincoli. Al «no»
  non riparte niente e resta nell'elenco;
- **un lavoro in attesa di una risposta** torna ad aspettarla con la sua conversazione (il
  `contesto` è JSON: messaggi, spinte, piano, stato del contesto), la domanda si ripete e
  `lavori_rispondi` lo riprende da dove era, nella stessa sandbox. Se la conversazione non si
  poteva salvare diventa interrotto;
- **un lavoro su un file della persona** non si rifà da solo (la copia del file e la consegna
  al satellite non sopravvivono): «Era su un tuo file: se vuoi, chiedimelo di nuovo.», senza
  domanda;
- `lavori_stato` li elenca («… si è interrotto per un riavvio di Calliope: lo rifaccio?», con
  l'azione in sospeso); `stato()` non dice più «Non ho lavori in corso.» e basta.

Il gestore di Linux legge lo stesso file prima di fermare il servizio: vedi
[setup-dgx](setup-dgx.md). Non fa ancora: copiare i file della sandbox di un interrotto nella
cartella dei risultati se la persona dice «no» (restano in `~/calliope/lavori/`); salvare la
conversazione dell'agente durante il lavoro (si potrebbe a ogni passata, ma riprendere a metà
di una chiamata di strumento è il punto delicato). A secco: `prova_lavori_riavvio.py`; sulla
DGX non ancora provato con un riavvio vero.

## Tetto delle estensioni e avvio del container (06/10, prova e2e)

Alla prima chiamata dopo l'approvazione «Converti gradi» (tetto 5 s) finiva con «si è fermata
senza risposta» (i 5,46 s del rapporto erano l'attesa di «Un attimo.»). L'orologio contava dal
lancio di `docker run`. Ora il runtime nel container manda `notifications/calliope/pronta` e il
tetto del manifesto conta da lì (`Esecuzione.lavoro_s`); l'avvio ha il suo margine,
`esecuzione.AVVIO_S` (20 s, «il contenitore non è partito in…»); se il container esce senza
risposta, il log dice tempi e coda dell'errore. Il motivo vero del 06/10 non si sa (dati
dell'istanza cancellati): alla prossima prova lo dice il log. `prova_estensioni` con il docker
finto lento (`DOCKER_FINTO_AVVIO_S`).

## Analisi della richiesta prima di partire (06/10)

Caso vero del 06/10 (DGX): «creami un'estensione che mi fa una ricerca sulle città di una regione
prendendole da Wikipedia» → `estensione_crea` → «Procedo?» → «sì» → L1 (qwen3.6 su vLLM): 5
pagine d'esempio scaricate, 6 script `esplora*.py`, 4 minuti di solo ragionamento, 24 passate
finite, nessun `estensione.py`, titolo «estensione che». La richiesta non era una specifica
(quali città? «principali» secondo cosa? da quale tabella?). Dario non vuole spinte a metà
lavoro: la domanda va fatta **prima**, alla proposta.

- **Analizzatore** (`calliope/agenti/richiesta.py` → `Analizzatore`, creato da `load_agenti`
  con `agenti_analisi`): `estensione_crea` (non per i giochi né per la modifica di un'estensione
  che c'è) e `delega_lavoro` di tipo codice (non ricerche, documenti, modelli) lo chiamano dopo
  i controlli dei permessi e del collegamento, prima di creare il lavoro. Modello dell'agente,
  output strutturato (schema JSON, decodifica guidata di vLLM), thinking spento, temperatura 0,
  conversazione recente (`ToolContext.storia`) e funzioni di Calliope dal registro dei tool
  (`ToolContext.strumenti`, le ricerche non fidate o riservate escluse: trovano dati, non fanno
  il lavoro). Tempo massimo `agenti_analisi_s` (10 s, verifica della fonte compresa); oltre, o
  con un errore, si procede come prima (esito «nessuna»). Stessa GPU della voce: il client è
  `ClienteCedevole(dalla_voce=True)`, come lo scrittore dell'ufficio. Frase d'attesa («Un
  attimo, guardo bene cosa mi chiedi.») solo se l'analisi supera 1,2 s: `ToolContext.attesa`,
  impostata da Brain quando in quella risposta non si è ancora detto niente.
- **Lista di controllo chiusa** (`PUNTI`): estensione = input, output, fonte, caso «non
  trovato», permessi; codice = input, output, dati della persona, linguaggio. Il modello dà uno
  **stato per punto** (detto, dal_contesto, scelta_ragionevole, manca) e l'esito lo decide il
  codice: impossibile, poi c'è già, poi vaga (un punto manca e c'è una domanda indispensabile),
  poi raffinabile (dati presi dalla conversazione, solo se c'è una conversazione), altrimenti
  chiara. Nello schema l'input di un'estensione (lo dice chi la usa a ogni uso), il caso «non
  trovato» e il linguaggio non possono mancare. Ogni domanda ha `senza_risposta`: «sbaglia»
  (si fa) o «sceglie» (un buon programmatore sceglie da solo: non si fa).
- **Cinque esiti** (etichette di Dario del 06/10): *chiara* → come prima; *raffinabile* → la
  proposta dice «Ho capito così: …» prima di «Procedo?» (anche dopo un «sì» della politica, che
  la persona ha detto senza sentirla), il compito all'agente è la specifica e la richiesta come
  detta va nei vincoli; *vaga* → al più 2 domande a voce (azione in sospeso per lo stesso tool),
  tutte sul modulo dello schermo personale se c'è (`moduli.offri`; le risposte scritte creano
  il lavoro e propongono senza il modello); la risposta a voce si analizza di nuovo senza
  «manca» (una sola tornata di domande); *c'è già* → «Questo lo so già fare: chiedimi pure
  «…». Vuoi comunque…?» (per le estensioni `_gia_fatto` di sempre), e il «sì, comunque»
  procede senza un'altra analisi; *impossibile qui* → «Questo qui non posso farlo: …», senza
  domande né lavoro. Il tool indicato deve esistere nel registro (un nome inventato: si procede).
  Regole nel registro dei turni: `analisi_<esito>`, `analisi_gia_fatta`.
- **Fonte web**: per un'estensione chiara o raffinabile con `fonte_url`, una lettura con la rete
  pubblica di Calliope (`RetePubblica`, registro delle uscite, origine «analisi»); se la voce di
  Wikipedia indovinata non c'è, una ricerca opensearch di Wikipedia con il titolo; se la fonte non
  risponde la richiesta diventa vaga («Non ho trovato una fonte pubblica che risponda: da quale
  sito prendo i dati?»). Un 400/405/422 vale come «c'è» (un'API senza parametri); un certificato
  che Python non verifica (sul portatile la BCE, catena incompleta; sulla DGX va) vale «non so».
  La fonte verificata va all'agente nei vincoli.
- **Titolo** del lavoro di un'estensione: il nome detto o quello dell'analisi («capoluoghi
  regione», prima «estensione che»).
- **Tetto in parole** (`servizio.cosa_ha_fatto`): un lavoro di codice o un'estensione fermato da
  un tetto senza il codice vero dice «ho fermato «…»: ha cercato i dati senza arrivare a scrivere
  il codice, e ha fatto tutte le 24 passate del lavoro» (solo pagine d'esempio e script
  d'esplorazione; senza nemmeno quelli «non è arrivato a scrivere il codice»).
- **Prove**: `prova_analisi_richiesta.py` a secco (livello 2, ~6 s). Banco
  `prove/banco_richieste.py` (33 richieste: 15 estensioni, 16 di codice, 2 fuori ambito; casi
  veri E1, E2, E3, C1, C2) e misura manuale `prove/misura_analisi_richiesta.py --url … --modello
  …`; prova vera `prova_estensioni_agente.py --dalla-voce "…" --risposta "…"`.
- **Misura sul banco** (DGX, qwen3.6-35b su vLLM, a Calliope inattiva da più di 180 s), quattro
  giri del prompt: con l'esito scelto dal modello 20/31 (chiare con domande inutili 4/10); con
  gli stati dei punti e il filtro delle domande **28/31**: vaghe prese **10/10** (obiettivo
  ≥ 80 %), domande inutili sulle chiare **1/10** (C2, «che tipo di calcolo?», obiettivo ≤ 10 %),
  raffinabili 5/6, impossibili 2/2, c'è già 1/2 (E8: chiede se la lista va sincronizzata fuori),
  E11 (CAP) vaga perché la voce di Wikipedia indovinata non c'è. **Tempo** mediana 3,0 s, p90
  3,4 s, massimo 3,7 s; nessun ripiego. Sbagli che restano: E13 (province) con la voce sbagliata
  e la ricerca che non la trova → domanda sulla fonte; «calcola» per una conversione nei giri
  precedenti (ora no).
- **Prova vera** (DGX, 06/10 ~17:35, Calliope inattiva da 15 minuti; `prova_estensioni_agente.py
  --dalla-voce`, container vero, dati in una cartella temporanea) con la richiesta di oggi:
  analisi in **4,0 s** → vaga, due domande giuste («Quali città vuoi che cerchi: tutti i comuni
  della regione, solo i capoluoghi o quelle con una popolazione superiore a una certa soglia?»,
  «Che informazioni vuoi per ogni città…?»); risposta «i capoluoghi di provincia, con il numero
  di abitanti di ognuno, presi da Wikipedia» → raffinabile in 3,5 s, fonte verificata, titolo
  «capoluoghi regione», «Ho capito così: …» e «Procedo?». La specifica detta suonava come un
  modulo («input: …. Output: …»): ora il prompt chiede una frase naturale. Il lavoro (qwen3.6):
  piano alla prima passata e questa volta **estensione.py c'è** (riscritto 4 volte), ma senza
  test, e il tetto delle 24 passate l'ha fermato dopo 20,9 minuti (86 122 token, 32 105 di
  ragionamento). L'annuncio ora lo dice: «ha scritto il codice senza arrivare a provarlo». La
  richiesta adesso è una specifica; che l'agente riscriva lo stesso file senza passare ai test è
  un problema dell'agente, da guardare a parte (non ripetuta: 20 minuti di GPU).

## Il risultato di un lavoro finito (07/10)

Caso vero del 07/10 (DGX, registro dei turni): una ricerca finita e annunciata («ho finito
«Esegui una ricerca approfondita…»: 20 paragrafi. … Il file è nella cartella Lavori dei
Documenti.»), poi «E il risultato?» → `lavori_rispondi(risposta="Il lavoro è stato
completato.")` e «l'agente non ha generato un rapporto da leggermi»; «leggili o delegali e
dammi un bel riassunto» → `lavori_esegui` («Non ho programmi finiti da eseguire»), due volte;
poi un `delega_lavoro` nuovo per riassumere il «documento generato dalla ricerca precedente»,
che il lavoro nuovo non vedeva; poi `pc_cerca_file` dal telefono. Non c'era un modo di avere il
risultato a voce.

- **Tool `risultato_lavoro(lavoro?, modo: riassunto|leggi|mostra)`** (`calliope/tools/agenti.py`,
  `calliope/agenti/risultato.py`): il lavoro più recente finito di chi parla (chi amministra:
  anche degli altri), o quello detto per id o con parole del titolo (`risultato.scegli`, come
  `lavori_rispondi`); se il più recente è ancora in corso lo dice. Un altro familiare riceve un
  rifiuto (regola `risultato_lavoro_altrui`). Dopo un riavvio i lavori finiti non sono più in
  memoria: si leggono dalla cartella dei risultati (`dal_disco`, le 40 cartelle più recenti;
  `lavoro.json` ha dal 07/10 `persona` e il testo intero di una ricerca, quelli di prima si
  trovano per nome e il testo si legge dal file).
- **Cosa dice**: il riassunto dell'agente già salvato (`risultato_salvato`); con «leggi», con un
  riassunto salvato troppo corto (< 80 caratteri) o **già detto** (l'annuncio del lavoro finito
  lo contiene quasi sempre: `risultato_gia_detto`), un riassunto per la voce chiesto al modello
  dell'agente sul testo intero (`riassunto_voce`: thinking spento, 2–3 frasi o 4–6 con «leggi», il
  testo come dato e la domanda della persona, `ClienteCedevole` sulla stessa GPU, frase d'attesa
  dopo 1,2 s, tempo massimo `agenti_risultato_s` = 15 s; oltre, o con un errore, il riassunto
  salvato e la regola `risultato_ripiego`). L'uscita del modello passa da `per_voce` (niente
  elenchi, markdown, indirizzi). Il codice non si legge mai a voce.
- **Schermo**: se chi chiede ha uno schermo personale, il testo intero ci va sempre (la scheda del
  lavoro con il testo, stessa chiave della scheda finale); «mostra» senza schermo lo dice e
  riassume a voce.
- **Sicurezza**: classe `sicuro` con fonte «agente» in `politica.CLASSI` (il risultato entra in
  busta, la conversazione resta contaminata come dopo l'annuncio); la frase passa da
  `riferire.controlla_testo` come gli annunci (un numero a pagamento nel riassunto dell'agente
  diventa la frase fissa) e poi dal controllo di ciò che dice nel ciclo.
- **Gli altri tool lo propongono**: `lavori_esegui` su una ricerca o un documento (««…» è una
  ricerca, non un programma: vuoi il risultato?», regola `lavori_offri_risultato`),
  `lavori_rispondi` senza domande in attesa, `lavori_stato` con l'ultimo lavoro finito («Vuoi
  sentire il risultato?»): azione in sospeso verso `risultato_lavoro`. Descrizioni ritoccate:
  `lavori_esegui` «Solo per i programmi», `lavori_rispondi` «Solo quando l'agente ha fatto una
  domanda», `lavori_stato` e `delega_lavoro` rimandano a `risultato_lavoro`; una riga nel prompt.
- **Il nome**: prima `lavori_risultato`, come gli altri tool dei lavori. Con gemma4 e4b la
  chiamata finiva a volte scritta come testo con il nome fuso («lavoris_risultato(…)»,
  «lavorisultato(…)», «lavor_risultato(…)»: «lavori» e «risultato» si saldano su «ri»), a distanza
  3 dal nome vero, che `TextCallGuard` e `nome_vicino` non riconoscono: 5 prime risposte su 15
  nella prova e 6 su 50 nella sonda con i due nomi alternati minuto per minuto;
  `risultato_lavoro` 0 su 50.
- **Misura** (`prova_risultati_ollama.py`, gemma4 e4b su questo portatile, agente finto, 5 giri ×
  3 frasi, ognuna subito dopo l'annuncio come nel caso vero): main **2/15** (`lavori_rispondi`
  7 volte, `delega_lavoro` 2, risposte senza il contenuto), con `risultato_lavoro` **15/15**
  (il tool 15 volte, nessun tool sbagliato, il dettaglio del testo intero nelle frasi 2 e 3);
  prima frase mediana 1,60 → 0,60 s (il riassunto dell'agente finto è immediato: sulla DGX conta
  il tempo di qwen3.6 sul testo, coperto dalla frase d'attesa). A secco `prova_risultati.py`.
- **Da provare sulla DGX**: il tempo vero del riassunto di qwen3.6 su 20 paragrafi (atteso 2–4 s)
  e la scheda sul telefono.

### Il risultato dopo l'uso vero (07/10 mattina)

Tre casi del registro dei turni della DGX dopo `risultato_lavoro`:

- **La scheda col testo intero non arrivava al telefono**. «Entrambe le cose.» (riassunto e
  schermo) era una frase breve con la voce sotto soglia (0,447 contro 0,48), che vale per la
  conversazione: identità dalla zona grigia, e `schermi.destinatari` non manda una scheda
  personale nella zona grigia (`zona_grigia`). Il tool diceva il riassunto a voce e «Il testo
  intero è nella cartella Lavori», poi il modello chiamava `schermo_mostra(risposta)`, che
  mandava sullo schermo dello studio la risposta di prima: sul telefono si vedeva solo quella.
  Ora il risultato di un lavoro va sugli schermi personali di **chi l'ha chiesto** anche nella
  zona grigia, se la persona della conversazione è proprio lei (regola
  `risultato_schermo_proprio`: la scheda va solo sui suoi schermi, mai su quelli d'altri; il
  lavoro di un altro, anche per chi amministra, resta com'era). Uno `schermo_mostra` «risposta»
  o «ultima» nella **stessa risposta** rimanda in cima la scheda del risultato invece di coprirla
  (`ToolContext.scheda_risultato`, regola `schermo_mostra_risultato`); nella risposta dopo fa
  quello di sempre. Due tool con la stessa frase finale nella stessa risposta: Brain la dice una
  volta.
- **«E di quelli che hai già fatto?»** → `lavori_stato` «Non ho lavori in corso.» due volte: dopo
  il riavvio la ricerca del giorno prima c'era solo nella cartella dei risultati. Ora
  `lavori_stato` dice anche gli ultimi tre lavori finiti di chi parla, dalla memoria e dal disco
  (`risultato.recenti`, `elenco_detto`: titolo, «oggi alle…», «ieri alle…», «non riuscito»), e
  propone il risultato del più recente riuscito («Vuoi sentire il risultato?», azione in sospeso
  verso `risultato_lavoro`, regola `lavori_stato_finiti`); con un lavoro in corso li aggiunge
  dopo, senza domanda. `lavoro.json` ha dal 07/10 anche `fine` (prima: inizio + secondi, o l'ora
  del file). Dopo un riavvio gli id ricominciano da L1: un lavoro del disco si riconosce dalla
  **cartella** (prima dall'id, e il L1 di ieri spariva dietro il L1 di oggi), e l'azione in
  sospeso lo richiama con `lavoro = "cartella:<nome>"` (`risultato.chiave`).
- Il falso allarme di ciò che dice («installarlo», trascrizione di «mostrarlo») è in
  [`sicurezza-politica.md`](sicurezza-politica.md).

Prove a secco in `prova_risultati.py` (sezione «07/10 mattina»).

## I testi dell'agente in Markdown e il risultato al portatile (07/10)

Decisioni di Dario del 07/10 (area documenti-ufficio per il modulo, schermi-telefono per il
lettore e «Scarica»):

- **Markdown**: i prompt della ricerca (`SISTEMA_RICERCA`, `SISTEMA_RICERCA_ARCHIVIO`, lo
  strumento `consegna`) e dei lavori «altro» (`SISTEMA_ALTRO`) chiedono il testo in Markdown
  (`TESTO_MARKDOWN`: titolo con #, sezioni con ##, elenchi e tabelle quando servono, niente HTML
  né immagini) e il riassunto per la voce senza Markdown. `_scrivi_testo` scrive
  **`risultato.md`** nella cartella del lavoro (con «# Titolo» in cima se manca) al posto del
  Word di soli paragrafi della ricerca e del `.txt` degli altri; `contenuto` è
  `markdown.descrivi` («2 sezioni, 2 elenchi e una tabella»). Una ricerca senza `consegna` ha come
  riassunto l'inizio del testo senza Markdown. `per_la_voce` toglie il Markdown prima di cercare il
  codice (prima un «#» o una «|» scartava la frase intera). Il documento dell'agente (tipo
  `documento`, modelli) resta nel formato a blocchi.
- **La scheda**: per un testo in Markdown `Lavori.scheda` e `risultato.scheda` danno
  `schede.documento_markdown` (chiave `lavoro:<id>`: sostituisce la scheda in diretta), con il
  lettore e «Scarica»; i risultati vecchi (`.txt`, Word) restano come prima.
- **Il risultato al portatile** (`Lavori._consegna_risultato`): prima solo i lavori sui file
  della persona tornavano al portatile; ora anche il risultato di un lavoro finito (il testo o il
  documento, mai il codice) va nella cartella Calliope dei Documenti del portatile con
  `RemoteDelivery`, con il titolo del lavoro come nome («Ricerca sulle api in Italia.md»), e si
  offre ad «aprilo» (`Lavori.pcs`, da main.py; `offri_file` con la maniglia del satellite):
  l'annuncio finisce con «Lo apro?» e l'azione in sospeso `pc_apri_file(1)`. Senza il satellite
  che riceve i file resta nella cartella del lavoro sul server e la frase lo dice («Il file è sul
  server, nella cartella Lavori, perché il portatile non è collegato.»); la copia di riserva di
  RemoteDelivery non si fa (il file è già nella cartella del lavoro). Con Calliope sul PC stesso
  il file è già nei suoi Documenti: «Lo apro?» con il percorso. Il «sì» passa dalla politica
  come ogni `pc_apri_file` dopo un annuncio dell'agente (conversazione contaminata: basta il «sì»
  della voce riconosciuta, una frase breve porta alla sfida).
- **«Fammene un PDF / un Word»**: `risultato_lavoro` con `modo` «pdf» o «word»
  (`risultato.converti`): Markdown → `markdown.a_blocchi` → `render`, un file nuovo nella
  cartella del lavoro (mai sopra un altro), poi come il risultato (al portatile con «Lo apro?»).
  Un thread: oltre `documenti_attesa_s` la voce dice «Preparo il PDF di «…»: ti avviso quando è
  pronto» e il file si annuncia come un lavoro finito. Il codice non si converte. Regole
  `risultato_pdf`, `risultato_word`. Nessun tool nuovo (65 schemi): due valori in più
  dell'enum `modo`.
- **Misura** (07/10, l'agente vero con qwen3 8b sull'Ollama di questo portatile, biblioteca
  finta con tre passaggi, 3 giri × una ricerca e un lavoro «altro»; script fuori dal runner):
  **6/6 in Markdown** (titolo #, 3–4 sezioni ##, elenchi; una tabella in 3 ricerche su 3 quando
  chiesta), nessun HTML, **riassunto senza Markdown 6/6**, PDF e Word convertiti 6/6, 60–170 s a
  lavoro (il modello per metà sulla CPU). Un caso su sei aveva **tutto il testo dentro un recinto
  ```markdown** (la scheda l'avrebbe mostrato come codice): `markdown.senza_recinto` lo toglie
  (correzione della forma, solo se il recinto copre tutto il testo e dice markdown o md; contrari
  in `prova_markdown.py`), e il prompt ora dice «non dentro un blocco di codice». Con la frase nuova
  altri 6 lavori: 6/6 con titolo e 3–4 sezioni, nessun recinto, riassunti senza Markdown. Nelle ricerche
  il modello ha inventato le cifre per regione che i passaggi non avevano: problema del modello
  (qwen3.6 sulla DGX da riprovare), non del formato.

## Il turno dopo il risultato: «fammene un PDF», il lavoro nominato (07/10 sera, ramo `correzioni-giro8`)

Casi veri della DGX (26B, qui con nomi di fantasia):
- 15:50, satellite dello studio: dopo l'annuncio della ricerca finita («… Il file è nella cartella
  Calliope dei Documenti del portatile. Lo apro?») e «Per il risultato.» → `risultato_lavoro` col
  riassunto, «Fammene un PDF» trascritto «Ho metto un pdf.» → `pc_cerca_file(tipo=pdf)`, l'elenco
  dei PDF del PC; «L'ultimo che hai creato» apriva il PDF più recente del PC, che non era la
  ricerca.
- 16:11, telefono: «E il risultato di ricerca sulle pompe di calore?» → `lavori_stato` (l'elenco
  dei lavori finiti con «Vuoi sentire il risultato?»); solo al turno dopo («Di quello della pompa
  di calore, sì») `risultato_lavoro`.

Cosa cambia (nessuna regola sul testo della persona, principio 10):
- **Dati del turno `LAVORO_MSG`** (`Brain._lavoro_turno`, regola `riferimento_lavoro`, rete
  spegnibile `riferimento_lavoro`): «l'ultimo risultato di cui avete parlato è quello del lavoro
  «…» (lavoro L2): se ora ne vuole un PDF o un Word senza nominare un altro file, chiama subito
  risultato_lavoro con modo pdf o word…; può arrivare storpiata («ho metto un pdf»); se nomina un
  file suo è pc_cerca_file». Solo se un lavoro **finito** (non codice o estensione) di **chi parla**,
  in memoria, è finito da al più 30 minuti e il suo titolo detto (««…»») è in una risposta degli
  ultimi 8 messaggi (l'annuncio, il risultato).
- **Descrizioni**: `pc_cerca_file` («NON per fare un PDF o un Word del risultato di un lavoro
  dell'agente appena detto»), `documento_crea` («NON per mettere in PDF o in Word il risultato di
  un lavoro dell'agente»), entrambe solo se gli agenti ci sono; `lavori_stato` («NON quando chiede
  il risultato o il contenuto di un lavoro finito, anche nominato: risultato_lavoro, con lavoro =
  le parole del titolo») e `risultato_lavoro` con l'esempio «e il risultato della ricerca sulle
  pompe di calore?».
- **Spinta di `documento_crea`** (regola `spinta_documento_lavoro`): con `LAVORO_MSG` in questa
  risposta, se il documento chiesto dal modello parla del lavoro (almeno 2 parole significative
  del titolo e almeno il 40% delle sue), la prima chiamata risponde «c'è il risultato del lavoro «…»
  appena detto: … risultato_lavoro con modo word o pdf …; se vuole davvero un documento nuovo,
  richiama documento_crea». Una volta per risposta; una lettera qualunque non la riceve.

**Misure** (gemma4 e4b sull'Ollama del portatile, `prove/prova_risultato_pdf_ollama.py`, 3 giri,
storia vera con annuncio, «Lo apro?» in sospeso e riassunto detto):

| frase | prima | dopo |
|---|---|---|
| «Ho metto un pdf.» → `risultato_lavoro` pdf | 0/3 | 1/3, 1/3, 2/3 |
| «Fammene un PDF.» | 2/3 | 3/3 |
| «Famme un pdf.» (storpiatura non negli esempi) | — | 3/3 |
| «Me lo fai in Word?» → word | 0/3 (`documento_crea`) | 1/3, 2/3, 3/3 (con la spinta) |
| contrari «Cercami il PDF della bolletta…», «Aprimi il PDF del contratto…» → `pc_cerca_file` | 6/6 | 6/6 per giro |

Il 4B a «Ho metto un pdf.» spesso non chiama nessun tool («per creare un PDF ho bisogno di sapere
cosa deve contenere»); il caso vero era del 26B, che chiamava un tool (quello sbagliato): da
riprovare sulla DGX. Il caso delle 16:11 **non si misura col 4B**: con l'annuncio e cinque turni
d'altro davanti non chiama nessun tool, nemmeno `lavori_stato` per «Quali lavori hai finito oggi?»
(0/3 prima e dopo; nella prova resta come misura, fuori dagli errori). Prova a secco:
`prove/prova_dopo_annunci.py`.

Nello stesso turno delle 16:11 `riferire` fermava «Se vuoi più dettagli, chiedimi di
leggertelo.» come `uscita_istruzione` (falso allarme: è la frase del codice in coda a
`risultato_lavoro`): vedi [sicurezza-politica](sicurezza-politica.md).

## Versioni di un'estensione a voce (08/10, giro 10, ramo `correzioni-giro10`)

Caso vero della DGX (07/10 18:14–18:57, telefono, 26B; qui con nomi di fantasia). C'era
«Meteo Borgoverde e Valfiorita» (`meteo_citta`, città fisse). La persona chiede un'estensione che
dica il meteo di **una città qualunque**; il modello chiama `estensione_crea(nome="Meteo Città")`
e il confronto approssimato di `_nome` («meteo città» ≈ `meteo_citta`) ne fa la **versione 2** di
quella che c'era, con il titolo nuovo «Meteo per città». Poi:
1. annuncio «ho preparato una versione nuova di l'estensione «Meteo per città»», elenco ««Meteo
   Borgoverde e Valfiorita» (attiva, con una versione nuova da approvare)»: la persona cercava un
   nome e ne sentiva un altro. «Attiva l'estensione Meteocittà» → `estensioni_gestisci(attiva)`:
   la politica chiede «vuoi che faccia «attiva»…?», al «sì» «azione sconosciuta»; «riattiva» →
   «Fatto: «Meteo Borgoverde…» è di nuovo attiva» (era già attiva); per approvare la versione 2
   quattro turni e la sfida («Voglio che approvi la nuova versione», ripetuto, non vale come
   consenso alla domanda della politica: è il tema delle conferme con memoria dell'intento,
   [`docs/ricerche/2026-10-07-sicurezza-per-valore.md`](../ricerche/2026-10-07-sicurezza-per-valore.md),
   qui non toccato);
2. approvata la versione 2, «invoca l'estensione meteo per città su Bergamo» tre volte → sempre
   `web_cerca`, e una volta «l'estensione è progettata per dati preimpostati delle località
   configurate» (quello che aveva detto della versione 1). Il tool era registrato bene: schema con
   `citta` e descrizione della versione 2 (verificato sull'indice della DGX), nomi riletti a caldo
   (`Estensioni.aggiorna_tool`, `Brain.rileggi_tool`). Il modello seguiva le sue risposte di prima
   e la descrizione di `web_cerca` («meteo e previsioni»);
3. «modificala per qualunque città» → `delega_lavoro` di codice → analisi «impossibile: non posso
   modificare le estensioni esistenti» (e `riferire` la fermava, vedi
   [sicurezza-politica](sicurezza-politica.md));
4. «Com'è andata l'estensione?» → «Vuoi sentire il risultato?», e nel registro dei turni la
   risposta vuota (vedi [voce-e-regole](voce-e-regole.md)).

**Decisione: estensione nuova o versione nuova?** Lo dice il modello con le parole della persona,
mai un confronto approssimato: `estensione_crea` ha `modifica` (il nome di un'estensione che c'è:
versione nuova, con i suoi file e lo stesso nome; titolo e descrizione cambiano se cambia quello
che fa) e `nome` (un nome per una nuova). Un nome simile a quello di un'estensione che c'è, senza
`modifica`, è un'estensione **nuova** accanto all'altra, e la frase lo dice («Sarà un'estensione
nuova: «Meteo Borgoverde e Valfiorita», che c'è già, resta com'è.», regola
`estensione_nuova_accanto`); con `modifica` «Sarà una versione nuova di «…»: quella di adesso resta
in uso finché non approvi la nuova.». Cambiare lo scopo (città fisse → qualunque) va bene in tutti
e due i modi: se poi la persona ne vuole una sola, rimuove l'altra. `modifica` che non c'è →
niente lavoro, l'elenco delle estensioni al modello. Con la semantica di prima (`nome` = quella da
cambiare) nasce un'estensione nuova accanto: da guardare nell'uso vero col 26B.

Cosa cambia ancora (nessuna regola sul testo della persona oltre ai dati del turno, principio 10):
- **Annuncio, elenco e domande** (`servizio.chi_e`): «ho preparato la versione 2 di «Meteo
  Borgoverde e Valfiorita», che ora si chiama «Meteo per città»: …»; elenco «(attiva, versione 1;
  c'è una versione nuova da approvare, la 2, «Meteo per città»: dice il meteo attuale in una
  città). Per usare una versione nuova, dimmi di approvarla.»; la sfida «Per approvare la versione
  2 di «…», che ora si chiama «…», ripeti: …».
- **Sinonimi d'azione** (`servizio.azione_vera`; `ToolSpec.prepara`, nuovo: la forma degli
  argomenti prima dei permessi e della politica; regola `estensioni_azione_sinonimo`): attiva,
  abilita, usa, accendi, conferma, accetta → `approva` se c'è una versione da approvare, se no
  `riattiva`; disabilita/spegni → disattiva; elimina/cancella/togli → rimuovi. La politica chiede
  così proprio l'azione vera. Un'azione che non conosce resta un errore.
- **«riattiva» di una già attiva** (`_gia_attiva`, regola `estensione_gia_attiva`): niente
  «Fatto»; ««…» è già attiva, versione 1. C'è la versione nuova 2 …: … Vuoi approvarla?» con la
  domanda in sospeso (il «sì» la approva, con la sua sfida). Senza versioni nuove «è già attiva».
- **Approvata**: «Fatto: «Meteo per città» è attiva, versione 2: dice il meteo attuale in una
  città. Da adesso puoi chiedermela.»; nel risultato per il modello `tool`, `input` e, dalla
  versione 2, `nota` («quello che è stato detto prima di questa estensione valeva per la versione
  di prima»).
- **Dati del turno `EST_NOMINATA_MSG`** (`Estensioni.nominate`, `Brain._estensioni_nominate`,
  regola `estensione_nominata`, rete spegnibile `estensione_nominata`): se la frase nomina
  un'estensione attiva per titolo o nome (a parole intere; per un titolo di almeno due parole e
  dieci lettere anche simile, ≥ 0,85, «Medio per città», o attaccato, «Meteocittà»), subito prima
  della domanda: «chi parla nomina la tua estensione «Meteo per città» (versione 2): è il tool
  est_meteo_citta, «Dice il meteo attuale in una città», input: citta[. È cambiata da poco: quello
  che è stato detto di lei prima nella conversazione valeva per la versione di prima]. Se chiede di
  usarla, chiama quel tool con i dati che dice, non un altro (internet, biblioteca); se chiede di
  cambiarla, è estensione_crea con modifica.» («cambiata da poco»: versione > 1 approvata da al
  più 30 minuti). È un contesto: decide il modello. «Che tempo fa a Bergamo?» non lo riceve.
- **`delega_lavoro` di codice che cambia un'estensione** (regola `delega_estensione`): se il
  compito ha la parola «estensione» e il titolo o il nome di una (una sola) estensione che c'è, il
  lavoro passa a `estensione_crea` con `modifica`, con la stessa conferma della politica (è la
  stessa richiesta: una versione da approvare, che vuole comunque la sfida). «Cambia l'estensione
  dei file .txt» e «un programma che legge il meteo per città» restano lavori di codice.
- **Analisi della richiesta**: esito nuovo `estensione` (`richiesta.NOTA_IMPOSSIBILE`, solo per il
  codice: «se la richiesta è creare, cambiare, correggere o rifare un'estensione … NON è
  impossibile: scrivi solo la parola ESTENSIONE»; `interpreta` → esito «estensione»): niente frase
  detta, il risultato dice al modello di richiamare `estensione_crea` (con l'elenco per
  `modifica`). Misura con qwen3:8b sul portatile (2 giri, 3 richieste d'estensione): 0/6 prima e
  dopo (l'8B ignora la parola chiave: «raffinabile», «vaga», «gia_fatto»); da rimisurare con
  qwen3.6 sulla DGX. Il compito vero lo copre già la regola di sopra, prima dell'analisi.
- **`lavori_stato` di un lavoro d'estensione finito**: «L'ultimo lavoro: «Meteo Città» è finito …
  Ha preparato la versione 2 di «…», che ora si chiama «…»: è da approvare. Vuoi approvarla?» con
  la domanda per `estensioni_gestisci(approva)`; approvata: ««…» è attiva, versione 2.» (prima:
  «Vuoi sentire il risultato?»).
- Descrizioni: `estensione_crea` («oppure CAMBIA un'estensione che c'è (…): modifica = il suo
  nome…; nome: un nome breve per un'estensione nuova»), `estensioni_gestisci` («approva una
  versione nuova («attiva la versione nuova», «usa la nuova»)…; riattiva (una disattivata)…; per
  USARE un'estensione chiama il suo tool est_, non questo»).

**Misure** (gemma4 e4b sul portatile, `prove/prova_estensione_nominata_ollama.py`): la storia della
DGX (Calliope che dice tre volte «è solo per Borgoverde e Valfiorita», «per Bergamo devo usare il
web»), l'approvazione della versione 2 col modello e la sfida, poi «invoca l'estensione meteo per
città su Bergamo»; tre frasi che la nominano in una conversazione pulita; «Che tempo fa a
Bergamo?». `--tutti`: con gli altri ~50 tool di Calliope.

| | ramo, dati del turno | ramo, rete spenta | main |
|---|---|---|---|
| storia della DGX → `est_meteo_citta` (3 giri; 2 giri con `--tutti`) | 3/3; 2/2 | 3/3; 2/2 | 3/3; 2/2 |
| conversazione pulita, nominata → `est_` | 9/9; 6/6 | 9/9; 6/6 | 9/9; 6/6 |
| «Che tempo fa a Bergamo?» | estensione 3/3; con `--tutti` internet 2/2 | uguale | uguale (`--tutti`: internet 3/4) |

Il 4B **non riproduce** l'errore del 26B (nemmeno con il codice di main, ~50 tool e la storia della
DGX): i cambi sono costruiti sul caso vero, non peggiorano il 4B, e vanno rimisurati sulla DGX con
l'uso vero. «Che tempo fa a Bergamo?» con l'estensione o con internet vanno bene tutti e due
(l'estensione dice i dati di Open-Meteo, internet i siti di meteo con la fonte detta): con pochi
tool il 4B sceglie l'estensione, con tutti internet. Prova a secco:
`prove/prova_estensioni_versioni.py`.

## Ricerche senza «Procedo?» (08/10)

Decisione di Dario: una ricerca affidata all'agente parte appena chiesta, senza la proposta
«È una ricerca a più passi… Procedo?» (`Lavori.serve_conferma`: restano codice ed estensioni,
la coda occupata, il modello da caricare, i file della persona). Coerente con la classe d'effetto
E2 delle ricerche nella politica per valore (`docs/ricerche/2026-10-07-sicurezza-per-valore.md`,
D1). La conferma della politica per un dato non fidato di mezzo resta quella della politica.

## Modalità sviluppo (08/10, ramo `modalita-sviluppo`)

Idea di Dario dell'08/10: per chi amministra lo sviluppo di un'estensione (o di un programma)
diventa uno **stato** con fasi, invece di frasi sparse nella conversazione normale. Progetto,
stati e transizioni in [`docs/ricerche/2026-10-08-modalita-sviluppo.md`](../ricerche/2026-10-08-modalita-sviluppo.md);
il caso vero è la sessione del meteo per città del 07/10 sera (sezione del giro 10 qui sopra),
dove provare l'estensione veniva **dopo** approvarla e ogni passo era una richiesta nuova.

- **Fasi**: analisi → sviluppo e test → collaudo → revisione → attivazione (un programma non ha
  l'attivazione). Le transizioni le fa il codice quando un tool riesce: `estensione_crea` o
  `delega_lavoro` di codice di chi amministra con la voce **aprono** lo sviluppo
  (`apri_se_serve`, regola `sviluppo_aperto`); la proposta «Ho capito così: … Procedo?» è la
  specifica; il «sì» avvia il lavoro (sviluppo); `Lavori._annuncia` porta al collaudo
  (`Sviluppi.lavoro_finito`: l'annuncio non chiede più «Vuoi approvarla?», dice «Siamo al
  collaudo: … prima di approvarla la puoi provare»); `sviluppo(avanti)` alla revisione e poi
  all'attivazione; `Estensioni._approva` chiude lo sviluppo (`sviluppo_chiuso`). Un lavoro
  fallito lascia lo sviluppo allo sviluppo, senza lavoro («torniamo all'analisi o lo rifaccio?»).
  L'analisi «impossibile» o «c'è già» chiude lo sviluppo appena aperto (non blocca gli altri).
- **Due tool nuovi** (68 schemi con gli agenti; uguali per ogni livello): `sviluppo(azione:
  stato, avanti, analisi, sospendi, riprendi, esci, promuovi; quale; cambia)` e
  `sviluppo_prova(dati)`. Il secondo è a parte perché il suo risultato è un dato non fidato
  (fonte «estensione», come gli `est_`): con un tool solo ogni «a che punto siamo?» avrebbe
  contaminato la conversazione.
- **Collaudo** (`Estensioni.prova_candidata`): la versione candidata gira nello stesso container
  di un'estensione attiva (`_esecuzione`, la stessa di `usa`: porta stretta, guardrail, quote,
  tetti del manifesto, livello al più familiare), con l'impronta dei file ricontrollata prima di
  ogni prova; i dati detti diventano gli input (`_argomenti`: «Bergamo», «citta=Roma», JSON). Il
  programma si prova con `lavori_esegui`. I collaudi restano nello sviluppo e sulla scheda.
- **Revisione** (`Estensioni.revisione`): permessi in parole con quelli nuovi rispetto alla
  versione approvata, chi la usa, analisi del codice, test, prove fatte, e quanti file e righe
  cambiano (`differenze`; a voce mai nomi di file né codice, il diff unificato sulla scheda). Un
  programma: file e righe di codice, test, prove; se è grande (`sviluppo_programma_righe` 150, o 3
  file, o 3 prove) la proposta di farne un'estensione, con la differenza spiegata («un programma
  si esegue adesso e basta; un'estensione resta, la richiami a voce, ha i permessi approvati da
  te e le sue versioni»); `promuovi` chiude il programma e apre lo sviluppo dell'estensione con i
  file del programma sotto `programma/` nella cartella dell'agente.
- **Ritorno all'analisi** da qualunque fase (`sviluppo(analisi, cambia)`): il lavoro in corso si
  ferma (`Lavori.annulla` con l'id), la specifica con la modifica si propone; per un'estensione
  con una candidata il lavoro parte dai file della versione provata (`file_per_modifica(…,
  candidata=True)`), per un programma dai file del risultato.
- **Niente sviluppi nuovi** con uno aperto (`controlla_nuovo`, regola `sviluppo_altro_bloccato`):
  un'altra estensione, un programma, una ricerca → «Adesso stiamo sviluppando «…» e siamo al
  collaudo: un'altra cosa per l'agente la comincio dopo. Vuoi che sospenda questo sviluppo?»
  (in sospeso `sviluppo(sospendi)`). Le risposte alle domande dell'analisi e la modifica della
  sua estensione passano.
- **Sospensione** dopo `sviluppo_sospendi_min` (30) minuti senza parlarne, pigra
  (`Sviluppi.corrente`), mai con l'agente al lavoro; «riprendiamo lo sviluppo del meteo» →
  `sviluppo(riprendi, quale)`, e quello aperto si sospende (uno aperto per persona). Una volta al
  giorno, alla prima risposta a chi amministra (riconosciuto: non nella zona grigia), la frase
  degli sviluppi sospesi in coda (`promemoria_giorno`, `ricordati` su disco).
- **Su disco** (`sviluppi.json` nella cartella delle sandbox): un riavvio a metà sviluppo lascia
  lo sviluppo senza lavoro («interrotto da un riavvio»), e il lavoro rifatto dopo «Lo rifaccio?»
  si riconosce da persona, tipo ed estensione o titolo (`_rifatto`).
- Dati del turno, riga del fuori tema e promemoria: [voce-e-regole](voce-e-regole.md);
  sicurezza dei passi interni: [sicurezza-politica](sicurezza-politica.md); la scheda:
  [schermi-telefono](schermi-telefono.md).

**Prove**: a secco `prove/prova_sviluppo.py` (~2 s, livello 1: macchina a stati, collaudo nel
docker finto, revisione e sfida, analisi, blocco, Brain, sospensione e promemoria, programma,
politica). **Misura con gemma4 e4b** sul portatile (`prove/prova_sviluppo_ollama.py`: la sessione
del meteo per città come iter, 12 passi, servizio dei lavori finto, il lavoro finisce per finta; con
i dati del turno e con la rete `modalita_sviluppo` spenta; `--tutti` con gli altri ~60 schemi):

| passo | 3 giri, dati del turno | 3 giri, rete spenta | 3 giri `--tutti`, dati del turno | `--tutti`, rete spenta |
|---|---|---|---|---|
| richiesta → sviluppo aperto | 3/3 | 3/3 | 2/3 (una volta «c'è già: chiedimi che tempo fa») | 3/3 |
| «Sì, procedi.» → sviluppo | 3/3 | 3/3 | 3/3 | 2/3 (+1 al turno dopo) |
| «Che ore sono?»: risponde e ricorda dove eravamo | **3/3** | 0/3 | **3/3** | 0/3 |
| «Prova con Bergamo.», «…Atlantide» → `sviluppo_prova` | 6/6 | 6/6 | 6/6 | 6/6 |
| «Aggiungi il latte…» → la lista, resta al collaudo | 3/3 | 3/3 | 3/3 | 3/3 |
| «Fammi anche un'estensione…» → non parte, senza domanda della politica | 3/3 | 3/3 | 3/3 | 3/3 |
| «Anzi, torniamo all'analisi…», «Sì.» | 6/6 | 6/6 | 6/6 | 6/6 |
| «Va bene, andiamo avanti.» → revisione | 3/3 | 3/3 | 3/3 | 3/3 |
| «Attivala.» → sfida → attiva, sviluppo chiuso | 6/6 | 6/6 | 6/6 | 5/6 |
| prima frase mediana | 1,32 s | 1,00 s | 1,32 s | 1,18 s |

Lo stato nel codice fa quasi tutto: con la rete spenta il modello trova i tool giusti dalle loro
risposte (il collaudo, «avanti»). I dati del turno servono al fuori tema (il 4B scrive da sé
«Ricorda che stiamo collaudando l'estensione…»: la riga del codice non è mai servita) e costano
~0,15–0,3 s di prima frase (~250 token, solo con uno sviluppo aperto). Nei primi giri, prima delle
correzioni: «Attivala.» → `estensioni_gestisci(approva, nome="MeteoSì")` (il nome dato alla
richiesta) e la domanda della politica (ora `sviluppo_nome_estensione`); «Fammi anche
un'estensione…» riceveva la domanda della politica prima del rifiuto (ora
`sviluppo_senza_domanda`); il 4B una volta ha chiesto l'estensione con `delega_lavoro` di codice
(«Crea un'estensione che…»): si apre lo sviluppo di un programma (il limite noto dell'analisi
«ESTENSIONE» col modello piccolo, vedi il giro 10). Da misurare sulla DGX con il 26B e l'agente
vero.

## Modalità sviluppo, versione 2 (08/10, ramo `modalita-sviluppo-2`)

Dal giro di prova vero della DGX dell'08/10 (11:06–11:32, satellite dello studio, 26B): apertura
senza segni della modalità, «Perché?» improvvisato dalla voce, «fai revisionare il codice» che
tornava all'analisi, «Ok, chiuso a long» (storpiato) che chiudeva lo sviluppo con l'agente al
lavoro, il lavoro finito annunciato vecchio stile e poi «Non c'è nessuno sviluppo aperto da
provare». Decisioni di Dario e cosa è stato fatto: § 9 di
[`2026-10-08-modalita-sviluppo.md`](../ricerche/2026-10-08-modalita-sviluppo.md). In breve:

- **Nomi nuovi** (le voci qui sopra hanno quelli di prima): `lavoro_affida` (era
  `delega_lavoro`, senza il codice), `lavoro_stato`, `lavoro_risultato`, `lavoro_rispondi`,
  `lavoro_annulla`, `programma_esegui` (era `lavori_esegui`), `sviluppo_apri(tipo=estensione|
  programma)` (era `estensione_crea` e `delega_lavoro` di codice), `sviluppo_passo` (era
  `sviluppo`), `sviluppo_collauda` (era `sviluppo_prova`), i nuovi `sviluppo_chiedi` e
  `sviluppo_correggi`, `estensione_gestisci` (era `estensioni_gestisci`). I vecchi valgono nel
  registro (`tool_nome_vecchio`); `lavoro_affida` di codice e `sviluppo_correggi` senza uno
  sviluppo aperto passano a `sviluppo_apri` come programma (`lavoro_codice_sviluppo`,
  `sviluppo_correggi_nuovo`). Due schemi in più (63 → 65 nel registro di prova, ~880
  caratteri); 71 sulla DGX.
- **Apertura detta** e specifica letta; **`sviluppo_chiedi`** con il contesto dei lavori
  conservato (`lavori/sviluppi/S<n>.json`); **collaudo fallito → «Lo faccio correggere?»**;
  **`sviluppo_correggi`** sui file della versione provata; **chiusura** con conferma, sospensione
  con l'agente al lavoro; **riapertura al collaudo** a lavoro finito; **tappe** ai tetti del giro
  con il rapporto e i segnali di giro a vuoto (`agenti/ciclo.py`, `Lavori.continua`).
- `TextCallGuard`: anche «chiamata_» davanti al nome è un prefisso come «call_» (gemma4 ha detto
  a voce «chiamata_lavoro_affida(…)» una volta).

**Prove**: a secco `prove/prova_sviluppo_v2.py` (~10 s, il giro vero riscritto con la città di
fantasia «Pratofiorito Maggiore»; tappe con il servizio dei lavori vero e l'Ollama finto). Con
gemma4 e4b sul portatile, `prove/prova_sviluppo_v2_ollama.py` (il giro vero in 11 passi) e i banchi
di prima e dopo i nomi nuovi, stessa versione di Ollama, 2 giri (dopo: con il codice finale):

| banco | prima (main) | dopo |
|---|---|---|
| `prova_sviluppo_v2_ollama` (11 passi) | — | 44/44 su 4 giri; nei giri prima delle due correzioni qui sotto «Attivala.» 1/3 e la richiesta → `calliope_stato` 2 volte su 9 |
| `prova_sviluppo_ollama` (12 passi, dati del turno / rete spenta) | tutto bene; mediana 1,29 / 1,18 s | tutto bene; mediana 1,24 / 1,17 s |
| `prova_agenti_ollama` | 32/40 (gli 8 errori: la sandbox non è pronta sul portatile, il codice non parte) | 30–32/40 su quattro esecuzioni; oltre agli 8 della sandbox, relazione e ricerca 6 errori su 30 (prima 0 su 12): «Chiedo quale formato…» invece di `lavoro_affida`, una volta «chiamata_lavoro_affida(…)» detto a voce |
| `prova_estensioni_ollama` | tutto bene | tutto bene |
| `prova_risultati_ollama` | 6/6 | 6/6 |
| `prova_regressione` (174 casi) | 162/174; 57 chiamate scritte come testo | 161–163/174; 62–69 chiamate scritte come testo; gli errori sono quelli di sempre (chi sono, l'ora, lo schermo, i delfini), nessuno sui nomi |
| nomi fusi o sconosciuti («lavoris_stato») | 0 | 0 in tutti i banchi |
| prima frase mediana (regressione) | 0,70 s | 0,74–0,76 s |

Correzioni dopo la prima misura: la riga della revisione («chiama subito sviluppo_passo avanti:
la frase di conferma la chiede il tool, non tu»: «Attivala.» da 1/3 a 6/6) e la descrizione di
`sviluppo_apri` che comincia con «Crea un'estensione nuova di Calliope o un programma…» (la
richiesta d'estensione da 7/9 a 4/4: col nome nuovo il 4B a volte non la riconosceva). **Da
decidere**: `lavoro_affida` perde un po' su relazioni e ricerche col 4B (vedi tabella); se sulla
DGX col 26B si vede lo stesso, proposta: tornare al verbo «delega» nella famiglia
(`lavoro_delega`) o riprendere nella descrizione la frase di prima («un lavoro lungo il cui
risultato è un file complesso»). Da misurare sulla DGX con il 26B e l'agente vero, anche le tappe.

## Modalità sviluppo, giro 3: la causa che l'agente non vedeva (08/10, ramo `sviluppo-giro3`)

Giro vero della DGX dell'08/10 pomeriggio (14:36–15:47, 26B e qwen3.6; qui con nomi di
fantasia): sviluppo del meteo per città, cinque versioni, attivata la quinta con la sfida.
L'estensione costruiva l'URL del geocoder a mano (`…/search?name={citta}&count=1…`): una città
di una parola andava, una di due no. La richiesta partiva rotta e tornava «collegamento non
riuscito» in ~15 ms (`uscite.jsonl`); l'estensione la trasformava in «non ho trovato il meteo»,
il collaudo passava all'agente solo quella frase, nella sandbox l'agente non ha rete e i suoi
test con `CalliopeFinta` rispondevano a qualunque URL: cinque correzioni alla cieca, e
`sviluppo_chiedi` ha dato con sicurezza due diagnosi sbagliate («il servizio non la conosce»,
«il problema non sono i nomi di due parole»).

- **URL non codificato rifiutato** (`web/pagina.url_non_codificato`): spazi, accenti, caratteri
  di controllo o un «%» sbagliato nel percorso o nei parametri → «URL non valido: c'è uno spazio
  nel parametro «name». Codifica i valori con urllib.parse.urlencode…» (il nome del parametro,
  mai il valore). Lo controllano la porta delle estensioni (anche con la funzione finta delle
  prove; regola `estensione_url_non_codificato`), `RetePubblica` (anche per l'agente; nel
  registro delle uscite «bloccata: url_non_codificato») e `CalliopeFinta` (la stessa regola,
  copiata in `_ospite.py` perché il runtime non importa Calliope; la prova le confronta): un test
  dell'agente con una città di due parole fallisce come nel vero. Lo dicono il contratto
  (`CAPACITA.md`, «indirizzi») e il prompt dell'agente delle estensioni («nei test prova anche un
  valore di due parole con un accento»).
- **Traccia di rete del collaudo** (`Porta._traccia`, `Esecuzione.traccia`, al più 12
  richieste): metodo, URL com'era scritto (lo spazio resta: è spesso la causa), esito («stato
  200» o «errore» con il messaggio), byte e i primi 300 caratteri della risposta, durata. URL
  ripuliti: host riservato → tolto, un valore con un dato riservato o personale → «[tolto]»,
  dopo una lettura di dati di casa tutti i valori e l'ultimo pezzo del percorso. Il collaudo la
  conserva nello sviluppo (`collaudi[].rete`, su disco in `sviluppi.json`), mai nel risultato
  per il modello della voce; la ricevono `sviluppo_chiedi` (righe «richieste di rete» negli
  ultimi 4 collaudi; il prompt: «se una non va, la causa parte da lì; non indovinare una causa
  che la traccia smentisce») e i vincoli del lavoro di `sviluppo_correggi` («Traccia di rete dei
  collaudi», prima quelli con un errore).
- **Modifica di un'estensione che c'è** (DGX 15:36: «Modifica l'estensione Meteocittà: fai
  codificare il nome…» → `sviluppo_apri` senza `modifica`, ed è nata «Meteo città codificata»,
  riscritta da zero, senza le previsioni della v5, accanto alla vecchia): con un nome simile a
  un'estensione che c'è e senza `modifica`, niente lavoro né sviluppo: il risultato restituisce
  la scelta al modello («se la persona vuole CAMBIARE «X», richiama con modifica = "x"; per una
  NUOVA accanto, un nome diverso; se non si capisce, chiedi»; regola `estensione_simile_scelta`).
  Richiamato uguale nella stessa risposta vale come nuova accanto; il ritorno all'analisi di uno
  sviluppo già aperto per una nuova non chiede di nuovo. `modifica` ha la descrizione con
  l'esempio. Con `modifica` l'analisi della richiesta («quale API vuoi usare?») non c'è già da
  prima: l'agente parte dai file della versione che c'è.
- **Quali estensioni ci sono** (DGX 15:45: «ne abbiamo solo una», «la vecchia è stata
  ritirata», ed erano attive tutte e due; il modello vedeva solo i tool `est_` e non ha chiamato
  `elenca`): una frase che dice «estensione/i», e quella subito dopo, riceve nei dati del turno
  l'elenco vero (titolo, stato, versione, versione da approvare; regola
  `estensioni_elenco_turno`, rete `estensione_nominata`); la descrizione di
  `estensione_gestisci elenca` dice di chiamarlo prima di rispondere a una domanda sulle
  estensioni.
- **Rinomina** (DGX 15:46: «chiamala solo Meteo città» → `sviluppo_apri`, la conferma «c'è di
  mezzo il lavoro di un agente» e poi «non posso rinominare»): `estensione_gestisci` azione
  `rinomina`, `titolo` = il nome nuovo, di chi amministra, senza agente. Cambia solo il titolo
  (nell'indice: i file e l'impronta delle versioni restano, il tool `est_` e il nome interno
  pure; vale per tutte le versioni). Un titolo già di un'altra estensione attiva → «C'è già
  un'estensione che si chiama «…», ed è attiva… Vuoi che disattivi quella, prima?» (in sospeso
  `disattiva`; `estensione_rinomina_doppia`). Senza `nome`, l'estensione nominata nella frase se
  è una sola (`estensione_nome_dalla_frase`). Disattivare e rimuovere c'erano già. Sulla DGX le
  due estensioni restano com'erano: decide Dario.
- Politica (storpiature, due collaudi nella stessa frase, l'esito dopo la sfida, «ok» in coda,
  rinomina con il titolo detto): [sicurezza-politica](sicurezza-politica.md), stessa data.

**Prove**: a secco `prove/prova_sviluppo_giro3.py` (~1 s, livello 1; geocoder finto,
«Pratofiorito Maggiore» al posto delle città vere). Con gemma4 e4b sul portatile
`prove/prova_sviluppo_giro3_ollama.py`:

| passo | main (2 giri) | ramo (3 giri) |
|---|---|---|
| «Modifica l'estensione Meteocittà…» → versione nuova di quella che c'è | 0/2 | 3/3 |
| …senza «quale API vuoi usare?» | 2/2 | 3/3 |
| «abbiamo due estensioni?» → due | 0/2 | 3/3 |
| «la vecchia non c'è più?» → niente di falso | 2/2 | 3/3 |
| …e dice che c'è ancora | 0/2 | 0/3 (il 4B chiede quale, o propone l'elenco) |
| «chiamala Meteo Valfiorita» → rinominata | 0/2 | 3/3 (2/3 prima del nome dalla frase) |
| sfida superata al collaudo → l'esito detto, una sola esecuzione | 0/2 («Fatto.») | 3/3 |
| «Cerno Maggiore» detto → collaudo senza «viene dal lavoro di un agente» | 0/2 | 1/3 |
| prima frase mediana | 0,67 s | 0,87 s |

L'ultimo passo col 4B è sporcato da un limite noto: scrive la chiamata come testo
(`chiamata_in_mezzo`, senza argomenti) e la risposta resta vuota, su main come sul ramo; il
confronto della provenienza è coperto a secco. Da rimisurare sulla DGX con il 26B e l'agente
vero: la traccia di rete in `sviluppo_chiedi` e nella correzione (qwen3.6), e se l'agente scrive
da sé `urlencode` con il prompt nuovo.

## La scheda del lavoro in diretta e i conti dello sviluppo (08/10, ramo `scheda-sviluppo`)

Richieste di Dario dopo il giro vero della DGX delle 14:36–15:30 (la pagina e la vista dello
sviluppo in [schermi-telefono](schermi-telefono.md#la-scheda-dello-sviluppo-e-del-lavoro-in-diretta-la-vista-dello-sviluppo-0810-ramo-scheda-sviluppo)).
Prove `prova_scheda_sviluppo.py`, `prova_avanzamento.py` (aggiornata),
`prova_vista_sviluppo_pagina.py`.

**Il giro vero, letto dalla DGX in sola lettura** (`lavori/sviluppi.json`, `lavoro.json` dei
risultati, giornale del servizio): S1 «Meteo città» aperto alle 14:36, attivato alle 15:30. L1
(il primo lavoro) 10 570 token generati, 13 passate, 3 min; L2 (correzione) 6 191, 8 passate;
L3 (correzione) 92 957 token, 33 passate in due giri (tappa alle 15:02 a 24 passate, «continua»
alle 15:03), 25 min di lavoro; poi due ritorni all'analisi con un lavoro nuovo ciascuno: L4
24 310, L6 21 680. In tutto **155 708 token**, 80 passate, 5 lavori. `sviluppi.json` diceva solo
il lavoro di adesso e `correzioni: 2`: nessun totale. Cosa mostrava la scheda: per ogni lavoro i
suoi token generati (`lav.token`, ragionamento compreso: coerente) contro il tetto **di un giro**
(5 000 al minuto × 30 = 150 000), le passate cumulative contro 24 (al giro 2 di L3 «33 di 24», barra
piena), il tempo di lavoro cumulativo contro «30 min» fissi; una correzione ripartiva da zero
senza dire niente dello sviluppo.

Decisioni (08/10):

- **Tetti per giro, cumulativi per passate e minuti** (`Avanzamento._istantanea`): al giro N il
  massimo mostrato è N volte quello di un giro (passate 24 → 48 → 72, minuti 30 → 60 → 90), come
  i conti, che sono del lavoro intero; il motore dà a ogni giro di nuovo tutto (`ciclo._tetti`).
  Il tempo continua a contare (`dal`), senza l'attesa di una risposta. La scheda dice «giro 2».
  *Storico (08/10, ramo):* anche il massimo dei token cresceva col giro (150 000 → 300 000).
  **Decisione di Dario (08/10 sera):** il tetto dei token è un budget di spesa (token generati,
  ragionamento compreso), non la finestra di contesto, e un massimo raddoppiato sembrava più
  spazio all'agente: la barra mostra i token **del giro** (`token_giro`, da `token0`) sul tetto
  di un giro, che resta 150 000, e la nota sotto dà il totale del lavoro.
- **I numeri del lavoro in corso + quelli dello sviluppo intero**: `Sviluppo.lavori` registra
  ogni lavoro dello sviluppo (id e istante di creazione: dopo un riavvio gli id ripartono da L1)
  con token, ragionamento, passate, secondi e giri, aggiornati a ogni lavoro finito;
  `Sviluppi.totali` li somma (il lavoro in corso con i numeri di adesso), `riepilogo_lavoro` li
  dà alla scheda del lavoro con la fase e il numero della correzione: «Correzione N, riparte dalla
  versione provata» (una correzione è un lavoro nuovo, `svc.nuovo`, sui file della versione
  provata con un ragionamento nuovo). Anche la scheda in Markdown dello sviluppo ha «Lavori
  dell'agente» con i totali. Le domande di `sviluppo_chiedi` non sono lavori e non contano.
- **Il flusso a sequenza** (`avanzamento.py`): `_evento` accumula i pezzi per sezione
  (`pensiero`, `testo`, `codice` dagli argomenti di scrivi_file, `strumento`, `esito`,
  `passata`), il thread degli schermi li numera a ogni invio (un pezzo per sezione e per invio),
  li manda nuovi e tiene la finestra per la cronologia (`_storia`). Il ciclo manda ora
  `strumento` (nome e argomenti) ed `esito` (il risultato) di ogni chiamata
  (`Lavoro.nota`, `ciclo.py`): la scheda ne mostra una riga (`chiamata_breve`, `esito_breve`),
  mai il contenuto dei file. Gli argomenti di vLLM si sciolgono **in modo incrementale**
  (`_Argomenti`: prima si rileggeva tutto il buffer a ogni pezzo, quadratico su un file lungo;
  un escape spezzato aspetta il pezzo dopo, `\uXXXX` compreso): il codice ricostruito è identico.
- **Il registro completo** del flusso, in Markdown, nella cartella dei risultati del lavoro
  (`.registro-agente.md`, nascosto: `file_di_codice` e le correzioni non lo prendono; al più
  16 MB), scritto dal thread degli schermi; la scheda ha `registro` (chiave `registro:<id>`) e
  hub.py lo registra per «Scarica» solo sugli schermi personali di chi l'ha chiesto, mai dalla
  zona grigia; il file si legge al clic (`scarica.converti`, `markdown_file`).

**Da fare io sulla DGX**: niente di particolare; `calliope aggiorna` porta tutto. I lavori finiti
prima dell'aggiornamento non hanno né registro né numeri nello sviluppo (`lavori` vuoto).

## Modalità sviluppo, giro 4: quale estensione, più input, titolo della persona (08/10, ramo `sviluppo-giro4`)

Giro vero della DGX dell'08/10 sera (16:42–17:13, 26B e qwen3.6; qui con nomi di fantasia).
Sono andati bene: elenco, disattiva, rinomina, modifica con collaudo, correzione, revisione e
attivazione della v4 con i giorni di previsione. I problemi, corretti sul ramo:

- **`modifica` con la cosa da cambiare** (16:43: «modifica: "aggiungi la possibilità di
  scegliere quanti giorni…"», `nome` = «Meteocittà»): «non ho un'estensione…», poi la domanda
  «Meteo città o Meteocittà?» insieme al «Procedo…» del modello. Ora la descrizione di
  `modifica` dice «solo il suo NOME… MAI cosa cambiare, che va in compito»; se `modifica` non è
  un'estensione ma il modello l'ha nominata in `nome`, o la frase e il compito ne nominano una
  sola (una disattivata conta solo se non c'è un'attiva), è quella (`_da_cambiare`,
  `_nominata`; correzione della forma della scelta del modello, regola
  `estensione_modifica_dal_nome`). Nessuna o due attive nominate: la scelta torna al modello con
  l'elenco **e gli stati** («Meteocittà» (meteo_codifica_citta, attiva), «Meteo città»
  (meteo_citta, disattivata)). Il controllo viene **prima** dei permessi e della frase di sfida:
  una chiamata che rifiuterebbe non chiede la sfida.
- **Una disattivata non rende ambiguo il nome** (`servizio._nome`): due titoli uguali detti a
  voce («Meteo città» e «Meteocittà», confrontati senza spazi né accenti) → vince l'attiva; per
  `riattiva` (e «attiva» senza una versione da approvare) la disattivata (`preferenza`).
- **La sfida sprecata** (16:45: «Sì, te lo confermo», breve compatibile di chi amministra →
  «Per creare una funzione nuova di Calliope, ripeti: …»; superata, la chiamata rifatta era
  senza `modifica` né `tipo`, quindi `estensione_simile_scelta` e niente). La sfida veniva dal
  controllo rigido di `tools/agenti._permesso` (richiesta nuova di codice con una frase breve),
  non dalla politica (che aveva già dato `intento_confermato`). Decisione: **aprire lo sviluppo
  di un'estensione è l'analisi e la proposta**, e niente diventa attivo senza l'approvazione,
  che vuole sempre la sfida: basta il «sì» breve compatibile di chi amministra in una
  conversazione sicura (`admin_confermato`, regola `sviluppo_apri_breve`). Un programma nuovo
  resta com'era (sfida). Quando la sfida serve, porta la chiamata intera (`tipo`, `compito`,
  `nome`, `modifica` col nome vero), così rifatta è la stessa.
- **Collaudo con più input** (v2–v4 con `citta` e `giorni`; «Guanzate, 5 giorni» tutto in
  `citta` per tre collaudi «non trovato»; `sviluppo_chiedi` ha risposto «prova a dire solo il
  nome della città» e la correzione ha fatto leggere all'estensione «Città, N giorni»: un
  rattoppo). Ora i dati del turno in collaudo elencano gli input della versione in prova con
  tipo e descrizione («citta (testo, obbligatorio): …; giorni (numero intero): …») e, con più
  input, «passa argomenti = un oggetto… non tutto in dati»; `sviluppo_collauda` accetta
  `argomenti` (oggetto, anche come testo JSON; `dati` resta per un input solo); un numero
  seguito dal **nome esatto** di un input numerico nei dati («Pratofiorito, 5 giorni», «… per i
  prossimi 2 giorni») diventa quell'input (conversione di forma, `collaudo_input_dal_testo`;
  contrari: «Via Roma 5», «Valfiorita, 5», due numeri, un input solo). Ogni collaudo conserva gli
  **argomenti veri** passati (`collaudi[].argomenti`): li vedono il contesto di
  `sviluppo_chiedi` (con gli input della versione), la scheda e i vincoli di
  `sviluppo_correggi` («argomenti passati: citta="Guanzate, 5 giorni"»), così l'agente vede che
  il problema è nel passaggio e non nel codice; il risultato per il modello ha
  `argomenti_passati`.
- **Analisi** (17:01: «Ho capito così: X. Con questa modifica: X.»): una modifica uguale alla
  specifica, o che ci sta dentro, non si aggiunge (`_con_modifica`, somiglianza ≥ 0,8). A
  «l'analisi è corretta e voglio implementarla così» (17:02) `sviluppo_passo avanti` ripeteva la
  domanda perché l'offerta era scaduta (tre turni in mezzo): in analisi «avanti» **accetta** la
  specifica già proposta e letta, e il lavoro parte (`sviluppo_avanti_accetta`), con la frase
  che basta per chi amministra; se no si ripropone. Lo stesso se il modello richiama
  `sviluppo_apri` con la proposta scaduta dello sviluppo (`sviluppo_proposta_scaduta`; nella
  misura con gemma4 era «chiedimelo di nuovo»).
- **Il titolo della persona** (regola decisa qui): il titolo dato con `rinomina` resta finché la
  persona non lo cambia. La revisione, l'annuncio della versione nuova e l'approvazione usano il
  titolo effettivo (`archivio.manifesto`, con il titolo dell'indice) e non dicono più «che ora
  si chiama «Meteo città»» (17:12) né «Fatto: «Meteo città» è attiva» (17:13); il titolo proposto
  dall'agente va solo sulla scheda della revisione («scelto da te; l'agente proponeva «…»: per
  cambiarlo, chiedimi di rinominarla»). I vincoli dell'agente per una versione nuova dicono «Il
  titolo «…» l'ha scelto la persona: nel manifesto usa proprio questo titolo» (`titolo_vincolo`),
  e lo sviluppo e il lavoro di una modifica prendono il titolo dell'estensione, non il `nome`
  del modello. Sulla DGX (letto in sola lettura) l'indice ha ancora il titolo «Meteocittà» per
  meteo_codifica_citta: l'elenco già lo diceva, solo le frasi di revisione e approvazione no.
- **«Luca» → Šipanska Luka** (17:11): il geocoder dell'estensione prende il primo risultato del
  mondo. È un tema dell'estensione (potrebbe preferire l'Italia, o chiedere quando il nome è
  ambiguo), non di Calliope: da chiedere all'agente con una modifica, se Dario vuole.
- Il falso positivo di `uscita_segreti` (17:10): [sicurezza-politica](sicurezza-politica.md).

**Prove**: a secco `prove/prova_sviluppo_giro4.py` (~3 s, livello 1). Con gemma4 e4b sul
portatile `prove/prova_sviluppo_giro4_ollama.py` (3 giri): la modifica con i giorni → versione
nuova di Meteocittà 3/3 (il 4B mette già il nome in `modifica` con la descrizione nuova);
«Pratofiorito per 3 giorni» e «Borgoverde per cinque giorni» → `citta` e `giorni` 6/6, sempre con
`argomenti`; «l'analisi è corretta» a offerta scaduta → il lavoro parte 3/3 (0/1 prima di
`sviluppo_proposta_scaduta`); prima frase mediana 1,83 s. Da rimisurare sulla DGX col 26B, che
il 08/10 metteva la descrizione in `modifica` e i giorni nei dati.

## Modalità sviluppo, giro 5: doppia codifica, giro a vuoto nel ragionamento (08/10 sera, ramo `sviluppo-giro5`)

Giro vero della DGX dell'08/10 sera (18:14–19:05, 26B e qwen3.6; qui con nomi di fantasia;
registro dei turni, `uscite.jsonl` e registri dei lavori letti in sola lettura). La modifica
«preferisci le città italiane e fammi indicare il paese» è arrivata al collaudo (v5, 19 test su
19), «Parigi in Francia» e un nome corto sono andate; le città di due parole no, e nemmeno nella v6.

- **Doppia codifica** (v5 e v6): l'estensione faceva `quote_plus(nome)` e poi
  `urlencode(params)` → `name=Pratofiorito%2BMaggiore`, il geocoder cercava un «+» letterale e
  rispondeva vuoto (31–32 byte); per la porta del giro 3 l'URL era codificato bene. Il lavoro
  della correzione delle 18:51 **aveva** la traccia con quell'URL e i 32 byte, e ha scritto
  «the trace shows %2B which is correct for space», poi ha costruito un ripiego «se non trova,
  cerca con la prima parola». Ora `web/pagina.doppia_codifica` (la stessa regola copiata in
  `_ospite`, tenute uguali dalla prova): un valore di un parametro che, decodificato una volta,
  contiene ancora «%XX» (era «%25XX») o un «+» tra due lettere (era «%2B») → l'avviso «possibile
  doppia codifica nel parametro «name»: «%2B» è un «+» letterale, mentre lo spazio è «+» o
  «%20». Il valore è stato codificato due volte (per esempio quote_plus e poi urlencode):
  codifica una volta sola, con urlencode passa il testo com'è». **Mai un rifiuto** (un `%2B`
  può essere voluto: «C++», «1+1» non lo fanno scattare): la richiesta parte e l'avviso va
  nella traccia del collaudo (`avviso`, regola `estensione_doppia_codifica`), nelle righe della
  traccia per `sviluppo_chiedi` («— ATTENZIONE: …»), **in testa** alla traccia nei vincoli di
  `sviluppo_correggi` e dell'analisi («ATTENZIONE, dalla porta di Calliope: …»; i collaudi con
  un avviso si scelgono come quelli con un errore), nel registro delle uscite (`avviso` col nome
  del parametro, mai il valore) e in `CalliopeFinta.avvisi` (e su stderr, che pytest mostra se
  il test fallisce). Il contratto (CAPACITA.md) e il prompt dell'agente dicono «codifica una
  volta sola: con urlencode passa il testo com'è, mai quote_plus prima».
- **Il lavoro ripartito dall'analisi** (18:21:52: Dario dà la diagnosi «i nomi devi
  codificarli», il modello la passa a `sviluppo_passo azione=analisi cambia=…` → L2): il lavoro
  nuovo aveva i file della versione provata ma **né i collaudi né la traccia** (in `lavoro.json`
  solo la specifica; le due città li sapeva dalla conversazione). Ora `_nuovo_lavoro` aggiunge
  ai vincoli, come `sviluppo_correggi`, i collaudi della versione provata (dati, argomenti
  passati, esito, il giudizio della persona), la diagnosi di chi l'ha scritto e la traccia con
  l'avviso (`_collaudi_per_agente`), anche per un programma; alla prima analisi niente.
- **Il secondo collaudo nella stessa frase** (18:21:24, «Prova con Pratofiorito Maggiore e poi con
  Borgo Alto»): il primo passato con `dati` e `argomenti`, il secondo solo con
  `argomenti` → fermato (`web_azione_bloccata`), e Calliope ha detto «per Borgo Alto non ha
  risposto». Il controllo e la frase del rifiuto: [sicurezza-politica](sicurezza-politica.md).
- **«Chiedi all'agente» trascritto «chiedi alla gente»** (18:23): il 26B ha chiamato
  `richiesta_tutore` (fermato) e poi, a «volevo che lo chiedessi alla gente che sta sviluppando
  Meteocittà…», ha detto «ho già registrato la tua domanda nel mio processo di sviluppo» senza
  chiamare niente (`spinta_dichiarata`). Contesto, non regola (principio 10): i dati del turno
  dello sviluppo (`SVILUPPO_MSG`) dicono che «chiedi alla gente…» con uno sviluppo aperto è una
  domanda a chi scrive il codice → `sviluppo_chiedi` (non `calliope_stato` né
  `richiesta_tutore`), lo stesso per «come sceglie…» e «perché…», e di non dire di aver passato
  una domanda senza il tool. Misura con gemma4 e4b sul portatile
  (`prova_sviluppo_giro5_ollama.py`): «puoi chiedere alla gente come sceglie la città…?» 0/2
  prima (`sviluppo_apri`, `calliope_stato`, «Chiedo alla gente…» detto senza tool), 0/2 con una
  prima versione più vaga della riga, **3/3** con quella finale; «lo chiedessi alla gente che sta
  sviluppando…» 2/2 già prima, 3/3; contrari 3/3 («la gente dice che domani pioverà» → meteo;
  senza sviluppo aperto niente `sviluppo_chiedi`). Prima frase mediana 1,50 s. Da rimisurare col
  26B sulla DGX.
- **Giro a vuoto nel ragionamento** (correzione delle 18:51, e già L2): qwen3.6 ha ripetuto
  per centinaia di righe gli stessi paragrafi («La soluzione più semplice è: 1. Aggiungere il
  parametro paese…», la stessa riga 58 volte in una passata); 170 kB di registro in 12
  passate, e sullo schermo sembrava un difetto del pannello (il pannello va bene). La guardia del
  05/10 (token senza strumenti) guarda solo tra una passata e l'altra. Ora
  `agenti/ripetizioni.py` (`Ripetizioni`) legge il flusso della passata (ragionamento e testo,
  mai gli argomenti delle chiamate) e conta le frasi di prosa di almeno 6 parole: una ripetuta
  `agenti_ripetizioni_max` volte (8) nella stessa passata ferma lo stream (`controlla` alza
  `GiroAVuoto`, il client chiude la connessione) e la passata torna come «giro a vuoto»
  (token stimati dai caratteri). Il ciclo aggiunge la spinta «Ti ho fermato: stai ripetendo lo
  stesso ragionamento («…»). Non ripensarci: decidi adesso e chiama uno strumento…» (in coda al
  messaggio della persona, mai due «user» di fila), scrive nel log la regola
  `agente_ragionamento_ripetuto`, conta `segnali.ripetizioni` (la tappa dice «sembra girare a
  vuoto: ha ripetuto lo stesso ragionamento») e mette sulla scheda il passo «l'agente girava a
  vuoto (ripeteva lo stesso ragionamento): l'ho fermato». Alla terza passata fermata di fila il
  lavoro si chiude (`RIPETIZIONI_MAX`). Solo nelle passate con gli strumenti (codice ed
  estensioni, ricerche); non contano i blocchi di codice, le righe delle tabelle, le righe che
  sembrano codice, le frasi corte. Sui due registri veri della DGX scatta nelle 6 passate che
  giravano a vuoto (dopo 6–16 kB invece di 32–65 kB) e in nessuna delle altre.
- **`presence_penalty`**: le richieste a vLLM non lo mandavano. Ora
  `agenti_presence_penalty` per tipo di lavoro (solo motore OpenAI: `traduci_corpo`; il client
  di Ollama lo toglie). Valori dalla scheda di Qwen3.6: **0 per codice ed estensioni** (il
  ragionamento sul codice: «precise coding tasks», un codice ripete per forza gli stessi token)
  e 1,5 per ricerche, documenti e altro (ragionamento generale; oltre 1,5 a volte mescola le
  lingue). Quindi per il caso vero (un'estensione) la difesa è il rilevatore, non la penalità.
  **Da misurare** sulla DGX (non toccata): un banco delle ricerche con 0 e 1,5, e un'estensione
  con 0 e 0,5 per vedere se cala il giro a vuoto senza peggiorare il codice.
- Sulla DGX (letto il 08/10 alle 19:05): la v6 ha ancora `quote_plus` + `urlencode` e la
  correzione delle 18:51 era in corso con il ripiego «prima parola»; dopo l'aggiornamento
  conviene chiudere quello sviluppo o farlo correggere di nuovo, così il lavoro riceve l'avviso.

**Prove**: a secco `prove/prova_sviluppo_giro5.py` (~2 s, livello 1: doppia codifica e
contrari, collaudi con `argomenti`, «la gente», analisi con i collaudi, il rilevatore con uno
stream finto e i contrari, `presence_penalty`); con gemma4 `prove/prova_sviluppo_giro5_ollama.py`.

## Sonde dell'agente: analisi e specifica (08/10 sera, ramo `analisi-sonde`)

[`2026-10-08-sonde-agente.md`](../ricerche/2026-10-08-sonde-agente.md), niente codice. Letto
dalla DGX in sola lettura: l'08/10 l'agente ha usato `scarica_esempio` 15 volte (origine
«agente» in `uscite.jsonl`). Nelle correzioni del giro 3 ha scaricato la città di due parole con
l'URL scritto bene da lui (risposta piena), mentre il codice dell'estensione la costruiva rotta.
Una sonda prova l'URL dell'agente, non quello del codice. Nella correzione delle 18:51 (giro 5)
non ne ha usata nessuna. Proposta a due pezzi: **ricollaudo alla consegna** di una correzione
(`Estensioni.prova_bozza`, nel `controlla` della consegna, una volta per lavoro, i casi falliti
della persona) e **`sonda_rete`** al posto di `scarica_esempio` nelle correzioni (host noti
dello sviluppo, vocabolario del caso, 4 per lavoro, «come l'ha letto il server»). Specifica con
configurazione, schede, registri, regole e prove nel § 9 del documento.

## Diagnosi dei collaudi: confronto tra riusciti e falliti, risposte vere per i test (08/10 notte, ramo `diagnosi-collaudi`)

Il caso del giro 5, visto da lontano: l'agente **aveva** la traccia giusta (`name=…%2BMaggiore`
→ 32 byte), l'ha letta male, e i suoi test passavano «24 su 24» con un geocoder finto scritto da
lui che trovava la città. Dario: «e se domani il problema fosse un altro?». L'avviso della
doppia codifica e il rifiuto degli spazi (giri 3 e 5) restano, come avvisi in più; sopra ci sono
due meccanismi **generali**, che non sanno niente del problema.

- **Confronto tra collaudi riusciti e falliti** (`sviluppo.confronto`). Per ogni collaudo
  fallito della versione provata (al più 3) le sue richieste vanno accanto a quelle di un
  collaudo riuscito verso lo **stesso host e percorso** (prima della stessa versione, se no di
  una versione di prima: anche con i soli falliti c'è il confronto). Della richiesta: parametri
  com'erano scritti e decodificati una volta, metodo, corpo (POST); della risposta: stato,
  dimensione, chiavi JSON di primo livello e chiavi vuote (la porta ora le scrive nella traccia,
  `forma`/`chiavi`/`vuote`, `porta.forma_json`). Poi le differenze in fila: parametri solo da
  una parte, valori diversi con i segni che il riuscito non ha («%2B», «+», spazio, lettere
  accentate), risposta senza una chiave o con una chiave vuota, molto più piccola, stato
  diverso; e se l'**input** del collaudo e il valore che il servizio legge sono lo stesso testo
  a meno di segni («citta» = «Pratofiorito Maggiore», `name` letto «Pratofiorito+Maggiore»),
  mentre nel riuscito coincidono. Un «non ho trovato» è un risultato per il codice (il collaudo è
  «riuscito», `_fallito`): se nessun collaudo è segnato fallito vale come fallito quello che
  dallo stesso indirizzo ha avuto una risposta più povera, ed è detto così. Esempio vero (con
  le città di fantasia): «Riuscito: «citta: Valfiorita» → GET geocoding-api…/v1/search
  name=Valfiorita → stato 200, 2.369 byte, chiavi results, generationtime_ms. Fallito: «citta:
  Pratofiorito Maggiore» (per il codice riuscito: «Non ho trovato…»; la risposta ha meno dati) →
  … name=Pratofiorito%2BMaggiore (decodificato: «Pratofiorito+Maggiore») → stato 200, 29 byte,
  chiavi generationtime_ms. Differenze: solo il parametro name (nel valore del fallito «%2B»,
  «+» che nel riuscito non c'è); la risposta del fallito non ha results; … molto più piccola;
  l'input citta del fallito era «Pratofiorito Maggiore», ma il servizio legge name =
  «Pratofiorito+Maggiore» (nel riuscito input e valore letto coincidono)». Sta **in testa** alla
  traccia (`testo_traccia`, quindi nei vincoli di `sviluppo_correggi` e del lavoro che riparte
  dall'analisi, sopra l'«ATTENZIONE» della doppia codifica) e prima dei collaudi nel contesto di
  `sviluppo_chiedi`. Usa la traccia già ripulita dalla porta (un valore «[tolto]» resta tolto),
  al più 2.500 caratteri. Le intestazioni non ci sono: l'estensione non ne manda (la porta ha
  solo `url` e, per la POST, `dati`).
- **Risposte vere come esempi per i test** (`Porta._esempio`, `sviluppo.esempi_veri`). La porta
  tiene la risposta intera (al più 8.000 caratteri, poi «troncata») solo per una **GET verso un
  host scritto nel manifesto**, mai dopo una lettura di dati di casa, mai con un dato riservato
  nella risposta o un valore tolto dall'URL; un dato personale riconosciuto si toglie e
  l'esempio è «ripulito»; al più 2 indirizzi per esecuzione, e solo negli ultimi 6 collaudi
  (`sviluppi.json` resta piccolo). Quando parte una correzione o un lavoro dall'analisi, nella
  cartella dell'agente vanno `esempi_veri/<host>_<n>.json` (richiesta con l'URL com'era e
  risposta vera, l'esito del collaudo) e `esempi_veri/indice.json`, prima i falliti, al più 6
  (sostituiscono quelli della versione di prima); nei vincoli `ESEMPI_VINCOLO`: un test per ogni
  collaudo che non andava con la stessa richiesta e la risposta vera, mai risposte del servizio
  che contraddicono quelle vere; il prompt dell'agente lo ricorda in una riga. I file restano
  nella versione (JSON ammessi dall'archivio), così i test della revisione girano uguali.
- **CalliopeFinta con le risposte vere** (`_ospite.CalliopeFinta`, `esempi_veri=True`): se nella
  cartella di lavoro c'è `esempi_veri/indice.json`, per lo stesso indirizzo (anche con i
  parametri in un altro ordine) `rete_leggi` risponde con la risposta vera, non con quella
  preparata dal test, e lo scrive su stderr (`vere` tiene gli indirizzi). Il test del giro vero
  («un geocoder finto che trova qualunque città») con il codice della doppia codifica **fallisce**
  (prova con unittest in un processo); con la codifica giusta l'indirizzo è un altro e il test
  passa. Non sostituisce una risposta troncata o ripulita; `esempi_veri=False` per simulare un
  guasto; una rete negata resta negata.
- **Misura breve** con il modello locale (qwen3:8b, think spento, il prompt e lo schema di
  `sviluppo_chiedi`; l'avviso specifico della doppia codifica **tolto** dal contesto in entrambi
  i casi, per misurare solo il meccanismo generale; «Perché con Pratofiorito Maggiore dice che
  non la trova, mentre con Valfiorita va?», 4 giri ciascuno): con la sola traccia 0/4 («non è
  nel database» 3 volte, «spazi o nomi complessi» una); con il confronto senza la riga
  dell'input 0/4 («il geocodificatore non lo riconosce»); con il confronto completo **4/4**
  danno la colpa alla codifica del parametro `name`, 2/4 con il dettaglio giusto («%2B» al posto
  dello spazio), 2/4 nel verso sbagliato («gli spazi vanno codificati come +»). ~23 s a risposta
  sul portatile. L'agente vero è qwen3.6 su vLLM sulla DGX (non toccato): da misurare lì con un
  giro vero, e da vedere se i test con gli esempi veri fermano un «24 su 24» falso.

**Prove**: a secco `prove/prova_diagnosi_collaudi.py` (~2 s, livello 1: il confronto e i contrari
— nessun riuscito, host diversi, un collaudo solo, due riusciti uguali, input che cambia anche
nel riuscito —, il tetto, le tracce di prima; la porta con gli esempi e i contrari — host fuori
dal manifesto, dati di casa letti, POST, dato riservato, URL ripulito, troncata, al più due —;
`esempi_veri` e l'indice; CalliopeFinta con il test dell'agente in un processo; il confronto e
gli esempi in `sviluppo_chiedi`, `sviluppo_correggi` e nell'analisi).
