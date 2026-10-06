# Agenti in secondo piano ed estensioni

*Gemma davanti, agenti dietro: delega, sandbox, arbitro e pausa di vLLM, programmi in diretta, contesto degli agenti, estensioni permanenti e guardrail. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Agenti in secondo piano («gemma davanti, agenti dietro») | vLLM con l'API compatibile OpenAI sulla DGX (motore «openai», httpx, via tunnel `ssh -N -L` di OpenSSH), oppure l'API nativa di Ollama (motore «ollama», anche lo stesso Ollama della voce); ciclo scritto in proprio, niente framework; sandbox in un container Docker usa-e-getta sulla DGX (dal 03/10), altrimenti job object di Windows (ctypes) e audit hook | `calliope/agenti/` → `Lavori` (`servizio.py`: coda, proposta, risultati, annuncio, domande a metà lavoro), `Agente` (`ciclo.py`), file della persona (`file_utente.py`), `Tunnel` (`tunnel.py`), `Sandbox` (`sandbox.py` + `_avvio.py`, `scegli_isolamento`; immagine da `setup/linux/sandbox/Dockerfile`), `Arbitro` (`arbitro.py`: anche con vLLM sulla GPU della voce, `ClienteCedevole` per archivio e ufficio; `stessa_gpu` in `impostazioni.py`, `agenti_arbitro`; dal 04/10 `PausaServer`, pausa di vLLM in modalità sviluppo, `pausa_server`, `agenti_pausa_vllm`), `Avanzamento` (`avanzamento.py`: la scheda del lavoro in diretta), `ContestoLavoro` (`contesto_lavoro.py`, dal 05/10: risultati lunghi in `.calliope/passo-N.txt`, diario del lavoro alle soglie; finestra da `contesto.calcola_agenti`), `Modello` (`modelli.py`), `carica` (`impostazioni.py`: dgx.yaml / agenti_url), `ClienteOllama` / `ClienteOpenAI` (`remoto.py`, `remoto_openai.py`, `crea_cliente`), `load_agenti`; tool in `calliope/tools/agenti.py`; terminale `python -m calliope.agenti --prova` |
| Programmi dell'agente eseguiti in diretta, linguaggi (Python, C#) | stessa sandbox Docker; C# con csc nel container `calliope-sandbox-dotnet` (runtime .NET 10 + Roslyn, niente SDK né NuGet); SSE verso la scheda | `calliope/agenti/esecuzione.py` → `Esecuzioni` (`avvia`, `dimostra`, `ferma`, `frase`); `linguaggi.py`; `esegui_cs.sh`; `setup/linux/sandbox/Dockerfile.dotnet`; tool `lavori_esegui`, scheda `esecuzione` |
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

## Tetto delle estensioni e avvio del container (06/10, prova e2e)

Alla prima chiamata dopo l'approvazione «Converti gradi» (tetto 5 s) finiva con «si è fermata
senza risposta» (i 5,46 s del rapporto erano l'attesa di «Un attimo.»). L'orologio contava dal
lancio di `docker run`. Ora il runtime nel container manda `notifications/calliope/pronta` e il
tetto del manifesto conta da lì (`Esecuzione.lavoro_s`); l'avvio ha il suo margine,
`esecuzione.AVVIO_S` (20 s, «il contenitore non è partito in…»); se il container esce senza
risposta, il log dice tempi e coda dell'errore. Il motivo vero del 06/10 non si sa (dati
dell'istanza cancellati): alla prossima prova lo dice il log. `prova_estensioni` con il docker
finto lento (`DOCKER_FINTO_AVVIO_S`).
