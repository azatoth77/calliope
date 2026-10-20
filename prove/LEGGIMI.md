# Prove

Script di prova e diagnostica, fuori dal percorso principale di Calliope.
Ogni file aggiunge la cartella del progetto a `sys.path` con un piccolo shim in
testa, così si può lanciare dalla radice. Dal 26/09/2026 importano dal package
(`from calliope.brain import Brain`, `from calliope.config import Config`…):

```powershell
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe -u prove\prova_tool.py
```

## Runner

**Tutte le prove in un comando** (dal 26/09/2026; a livelli dal 06/10, P5 di
`docs/ricerche/2026-10-06-analisi-complessiva.md`), dalla radice del progetto:

```powershell
.\.venv\Scripts\python.exe -m prove              # livelli 1 e 2: ~15–60 s
.\.venv\Scripts\python.exe -m prove --completo   # tutte le prove a secco (~8–9 min): PRIMA DELL'UNIONE SU MAIN
.\.venv\Scripts\python.exe -m prove --ollama     # anche quelle con il modello (qualche minuto)
.\.venv\Scripts\python.exe -m prove --help       # le altre opzioni
.\.venv\Scripts\python.exe -m prove --leggimi    # rigenera l'elenco per area in fondo da elenco.md (16/10)
```

I **livelli** (in `prove/__main__.py`):

- **1** — le prove veloci (< 5 s da sole, 41 la sera del 06/10; 24 al livello 2, 11 al 3,
  27 con Ollama, 22 manuali; il 09/10 71 al livello 1, 31 al 2, 19 al 3, 40 con Ollama, 22
  manuali): sempre, in parallelo (6 alla volta),
  ~13–15 s. Una prova nuova senza livello è del livello 1; se il riepilogo la segnala come
  lenta va spostata in `LIVELLO_2` o `LIVELLO_3`.
- **2** — le prove legate ai file cambiati (`LIVELLO_2` e la mappa `LEGAMI` dai prefissi dei
  percorsi: `calliope/schermi/` → schermi, scritto, giochi, telefono_abbina…;
  `calliope/agenti/` → agenti, sandbox, arbitro, esecuzione…; `setup/linux/` → linux,
  gestore), in parallelo. Un file di `prove/` sceglie sé stesso e le prove che lo importano.
  I tool d'area (`tools/casa.py` → casa_ha, `tools/agenti.py` → agenti…, `tools/stato.py` →
  capacita, installa) scelgono le prove della loro area (Q7, 06/10). `brain.py`, `ciclo.py`,
  `main.py` e `config.py` scelgono `prova_linux_import` (gli import di tutto il pacchetto su
  Linux simulato, ~5 s: un import solo-Windows prima passava l'hook). Gli altri file
  trasversali (`politica.py`, `tools/registry.py`, `tools/spec.py`, `tools/builtin.py`…) non
  scelgono niente in più: li coprono il livello 1 e il 3.
- **3** — browser, Calliope vera, tempo reale (`LIVELLO_3`): solo con `--completo`, **in
  serie**, da sole sulla macchina (anche le prove del livello 2 con il browser, `SERIALI`).
  **Obbligatorio prima dell'unione di un ramo su main.** Va lanciato dove ci sono i file
  fuori da git (`voices/`, `models/speaker/`, `wakeword/modelli/`, `biblioteca/`): in un
  worktree come hard link (non junction); senza, quelle prove si saltano e il riepilogo le
  elenca. Eccezione (08/10): `prova_telefono_pagina` trova da sé onnxruntime-web
  (`models/web/`), i modelli della wake word e le voci nel **repository principale** (`git
  rev-parse --git-common-dir`, anche dalla copia dell'hook via `PROVE_ORIGINE`), o nella
  cartella di onnxruntime-web indicata da `CALLIOPE_TELEFONO_MODELLI`: si installano una volta
  sola nel principale con `python -m calliope.stato --installa telefono` (14 MB, ignorati da
  git) e in un worktree non serve nessun link.

L'**hook** (`.githooks/pre-commit`, attivato con `git config core.hooksPath .githooks`)
lancia `python -m prove --hook --staged`: livelli 1 e 2 con i file del commit, sulla **copia
dell'indice** (`git checkout-index` in una cartella temporanea, con i modelli come hard
link): si prova quello che si committa, non l'albero di lavoro, e indice, albero e stash
non si toccano. Misure del 06/10 nel worktree: commit su `brain.py` 14 s, su
`calliope/casa/` 17 s, su `calliope/satellite/` 46 s, su `calliope/schermi/` 52 s, su
`calliope/agenti/` 59 s (prima, tutte in serie: ~775 s nel worktree, ~880 nel principale).

Opzioni: `--ramo` (livello 2 con tutti i file cambiati dal punto in cui il ramo si è staccato
da main), `--staged`, `--seriale` o `-j N`, `--timeout S` (predefinito 300 s per prova; con
`--ollama` 3600), `prova_x.py …` (solo quelle, con il loro livello e il parallelo).

Il **riepilogo** conta a parte le prove **saltate**: una prova che si salta per intero (manca
il browser, una voce, un modello, il file della biblioteca) esce con **77**; una che salta
una sua parte stampa una riga che **comincia** con `SALTATA IN PARTE: <motivo>`. Prima il
«70/70» nascondeva i salti. Dal 06/10 (Q7) `prova_runner` controlla che ogni prova registrata
che stampa un salto lo segnali così (o esca con 77), che ogni `prova_*.py` sia nel runner o in
`MANUALI` (con il perché) e che i tool d'area scelgano le loro prove. Lanciate da sole, le prove saltate escono quindi con 77 anche nella shell.

Ogni prova ha un **tempo massimo** (300 s): oltre, il runner chiude lei e i suoi processi e
la segna fallita («tempo scaduto»). Su Windows ogni prova gira in un **job object** (dal
03/10): se a prova finita resta vivo un suo processo figlio (Calliope vera, Edge, un server
finto) la prova fallisce con «processi lasciati vivi» e il runner lo chiude, così non tiene
porte, file o CPU durante le prove dopo. Di una prova fallita il runner mostra le righe
`ERR`/`NO` e l'ultima riga di ogni traceback (l'eccezione), e salva l'output intero in
`%TEMP%\calliope-prove\` (lì anche `durate.json`: le durate dell'ultima volta, per far
partire prima le prove lunghe). Con `--ollama` (04/10) il runner manda alle prove il
`keep_alive` del modello della voce (`CALLIOPE_LLM_KEEP_ALIVE`, letto da `calliope.yaml`, dal
file locale e dal profilo): una prova non accorcia mai la permanenza in memoria del modello
condiviso con la voce. `python -m prove prova_satellite.py prova_agenti.py` lancia solo
quelle (stesso ambiente dell'hook): serve a ripetere una prova instabile. Le soglie «la voce
non aspetta» delle prove degli agenti valgono 0,15 s (`SUBITO_S`): ciò che non va aspettato
dura da 0,2 s in su, e sotto carico il solo avvio di un thread superava i 50 ms.

Una prova che cade a caso si cerca **in più corsie sotto carico** (dal 17/10 nel repository, #5):
`.\.venv\Scripts\python.exe prove\manuali\carico.py prova_satellite.py --corsie 3 --giri 20
--carico 16` la lancia come il runner (`lancia`, stesso ambiente e job object) in 3 corsie
insieme, 20 giri ciascuna, con 16 processi Python pieni (`--porte N`: anche N thread che aprono e
chiudono porte effimere, come le altre prove di un `--completo`). Stampa ogni giro (verde o
caduto, secondi, frasi ripetute perché la wake word non è scattata, contate a parte) e il
riepilogo; le uscite dei giri vanno in una cartella temporanea (`--uscita` per sceglierla). Il
carico finisce con lo script. In una prova nuova: niente attese fisse «perché nel frattempo»
succeda qualcosa (si aspetta la condizione, con un tempo massimo e la traccia se scade), niente
attese negative senza un segno positivo dopo, e per un sottoprocesso una porta fuori dalle
effimere (`prove/porte.py`, `porta_fuori_effimere`).

Le prove con il **browser** (Edge o Chromium senza finestra) usano `prove/cdp.py` (06/10): la
porta di DevTools la sceglie il browser (`--remote-debugging-port=0`, letta da
`DevToolsActivePort`) e la chiusura passa da `Browser.close`, poi dall'albero dei processi
(prima restavano vivi crashpad e le utility di Edge). Dal 08/10 il browser parte sempre con `--mute-audio`: la voce
che la pagina del telefono riproduce con Web Audio non esce più dalle casse o dalle cuffie
vere del portatile (Web Audio gira lo stesso). Le prove con un satellite in Python usano casse
finte (`apri_uscita`, `apri_flusso`). Dal 14/10 `cdp.Browser` avvia il browser in un **job
object della prova** (`calliope/agenti/winjob`, KILL_ON_JOB_CLOSE): una prova lanciata fuori
dal runner e fermata da un tempo massimo o da Ctrl+C non lascia più 14–15 processi msedge con il
suo profilo temporaneo (nel runner li chiudeva già il job della prova). `prova_cdp_orfani` lo
prova, con il contrario senza job.

**Prove instabili sotto carico: cosa si è trovato il 14/10** (cadute nei `--completo` con altri
agenti sullo stesso portatile; le cause e le misure):

- **La voce di Piper cambia a ogni corsa.** Piper sintetizza con un rumore (`noise_scale`,
  `noise_w_scale`): con la stessa frase l'audio è diverso ogni volta. `prova_frase_lunga_voce`
  cadeva circa una volta su sei (Whisper storpiava una parola sulla cucitura delle sue finestre
  di 30 s: «cassifica», «un aperturono»; una volta su otto una pausa dopo una virgola chiudeva il
  secondo pezzo), `prova_stanza_voce` una volta su dieci («Calliope, che ore sono?» sotto la
  soglia della wake word), `prova_telefono_audio` di rado (una sintesi così storpiata che Whisper
  sbagliava «Calliope» e «Oggi» a tutte le frequenze: 6 parole su 9, sotto il 70 %, visto nel
  secondo `--completo` della verifica del 14/10). Non era il carico. Ora la dettatura e la frase col nome sono
  **senza rumore** (`SynthesisConfig(noise_scale=0, noise_w_scale=0)`, con
  `sintetizza(deterministica=True)` di `prova_satellite` e di `prova_telefono_pagina`), e il testo di Whisper si confronta con una tolleranza sulle
  lettere (`contiene`), mentre l'unione dei pezzi si controlla esatta, campione per campione.
  Regola: una prova che non ripete la frase usa una sintesi deterministica; chi la ripete (come
  `prova_satellite`) usa le varianti con il rumore.
- **`time.monotonic()` piccolo dopo l'avvio.** Scrivere 0.0 per «tanto tempo fa» vale solo
  se il computer è acceso da più della soglia: `prova_esercizi_programma` (10 minuti),
  `prova_contesto_agenti` (10 minuti) e `prova_meteo_casa` (5 minuti) cadevano nella prima suite
  dopo un riavvio. Si scrive `prove.orologio.fa(secondi)`, e il contrario gira con
  `appena_acceso(modulo)` (il `time` di quel modulo vede un computer acceso da 5 s). Il codice
  era giusto: le sentinelle sono `None` o `-1e9`.
- **L'ora del giorno** (18/10, #151). Una scena scritta «ore prima di adesso» e controllata
  con un formato fisso cade a certe ore. `prova_stanza_cerca` voleva «HH:MM», e fra mezzanotte
  e le 3 le righe di tre ore prima diventavano «ieri 23:42»: l'hook fermava ogni commit di
  notte. `prova_esercizi` usava la pausa «00:00-23:59» per dire «sempre fuori orario», ma la
  fine non è compresa e nel minuto 23:59 non lo era. Regola: la scena gira a un'ora nota con
  `prove.orologio.ora_del_giorno(12, 0)`, che sposta `time.time()` del processo, e le ore della
  notte si provano apposta, ognuna con la sua forma attesa. Una fascia «sempre» si scrive con
  due fasce che coprono il giorno. Ricognizione del 18/10: le 186 prove dei livelli 1 e 2 con
  l'orologio del processo spostato alle 00:30, 02:59, 06:14, 08:00, 12:00, 18:30, 21:30 e
  23:59 (un `sitecustomize` fuori dal repository). Le cadute vere erano solo queste due. Le
  altre venivano dallo spostamento stesso: date vere dei file contro l'orologio spostato
  (`prova_personalita`, `prova_modalita`, `prova_installa`, `prova_searxng_aggiorna`), un
  sottoprocesso con l'ora vera (`prova_schermi`) e il carico, perché rilanciate da sole
  all'ora che le aveva fatte cadere passavano.
- **`prova_agenti`**: la caduta del 14/10 («VPN accesa»: `ollama_giu` con il tunnel finto e 1 s
  di tempo massimo) non si è ripetuta in ~110 giri sotto carico (prova intera con il runner che
  gira altre 12 prove degli agenti, e il solo passo del tunnel 60 volte). Da allora la diagnosi
  dice anche l'errore di httpx (`errore`: ConnectError, ReadTimeout…), così la prossima caduta
  spiega sé stessa. `lavoro_stato` «senza aspettare» rifà la misura una volta se supera
  `SUBITO_S` (sola lettura: un'attesa vera sul lavoro, che dura ~2 s, si ripeterebbe; un processo
  fermo un attimo no; misurato 0,41 s e 5,2 s con due runner insieme).
- **`prova_giochi_pagina`: due cause, una nel codice.** (1) «la porta 3 → l'esito, che va avanti
  da solo» restava su `['avanti']`: il timer dell'esito del motore era giusto, il gioco l'aveva
  **chiuso il cane da guardia** di `schermo.js` («non risponde»). Il limite contava dall'ultimo
  «pong», ma i ping partono ogni 2 s con un giro da 1 s, cioè fino a 3 s: con il limite di 3 s
  della prova (stretto per le prove del cane) bastava un giro in ritardo di pochi millisecondi
  per chiudere un gioco sano, anche senza carico. Ora il limite conta dal primo ping rimasto
  senza risposta ([giochi](../docs/aree/giochi.md)). (2) «la seconda pagina l'ha ricevuto e
  risponde» aspettava `da == 2`, ma il numero del giocatore lo dà il «pronto» in ordine
  d'arrivo e sotto carico la seconda pagina arriva a volte prima; le attese fisse (0,8 e 0,5 s)
  prima dei tocchi sono ora attese di una condizione: la tela disegnata (il motore manda i
  comandi della fase nuova) e il segnale ricevuto dentro il riquadro della seconda pagina,
  letto con DevTools (`nel_riquadro`: il riquadro sandbox è un processo a sé, fuori
  dall'albero dei frame, ci si attacca al suo bersaglio). La prova controlla anche che dopo le
  prove del cane nessun gioco sano venga chiuso e, se cade, stampa il diario dei messaggi dei
  riquadri. Misure con 5 corsie in parallelo: prima 5 giri caduti su 25 (3 esiti, 2 risposte),
  dopo 25 su 25 verdi; la prova nuova con lo `schermo.js` di prima cade 11 volte su 15.
- **`prova_stanza_voce`: frame persi all'inizio dell'ascolto, nel codice.** Le quattro cadute
  («la frase arriva intera», «nessun frame perso», «segmento legato al turno», «1 in più» di
  Whisper) erano una sola: «Calliope» non svegliava il satellite (punteggio massimo 0,01–0,15)
  e la frase finiva nella stanza. La pronuncia senza rumore fa scattare la wake word in 40 casi
  su 40 (5 allineamenti ai blocchi da 80 ms × 8 rumori): la voce non c'entrava. `Listener.listen`
  azzerava la wake word (il suo reset fa ~2 s di riscaldamento sui modelli: ~50 ms, sotto carico
  oltre i 300 ms del pre-roll) **prima** di aprire la coda dei frame, e la frase cominciata
  intanto perdeva l'attacco. Ora la coda si apre prima e i rilevatori si azzerano dopo
  (`calliope/audio.py`; caso nuovo in `prova_frase_lunga` con un reset di 0,6 s, che col codice di
  prima perde frame). La prova inoltre parla solo quando il satellite ha ricevuto l'«ascolta» e
  ha aperto la coda (`in_ascolto`), e se cade stampa il diario di satellite e server. Misure con
  3 corsie e 20 processi di carico: prima 6 giri su 12 con la caduta, dopo 0 su 12 (con quel
  carico Edge ci mette a volte più di 10 s a uscire dopo il kill: `cdp.Browser.chiudi` non lo
  tratta più come un errore della prova, ci pensa il job object).

**Prove instabili sotto carico: le cause trovate il 15/10** (ramo `correzioni-15-10`). Misure con
`carico.py` (allora fuori dal repository; dal 17/10 `prove/manuali/carico.py`): la prova lanciata dal runner in più corsie insieme, con 12–20
processi Python pieni su 24 core e, per il tunnel, 32 thread che aprono e chiudono porte effimere in
ascolto (come le altre prove di un `--completo`).

- **`prova_agenti`, il tunnel: la porta, non la VPN.** `LP` era una porta effimera presa all'inizio
  con `bind(0)` e rilasciata: il tunnel la riapre e la chiude più volte in ~50 s, e intanto un altro
  processo poteva riceverla. La sonda del tunnel trovava in ascolto il processo d'altri («ok»), che poi
  spariva: `ollama_giu` con **ConnectTimeout** (su Windows una porta chiusa di 127.0.0.1 non rifiuta
  subito, ritenta: col tempo massimo di 1 s è un timeout), già nel passo «ssh muto» e poi in «VPN
  accesa» (14/10 04:36, 11:00, 18:27), e «porta locale occupata» al `--prova` (08/10, 14/10 10:17).
  Ora la porta è a caso tra 20000 e 31999, **fuori dalle effimere** (Windows da 49152, Linux da
  32768: `porta_tunnel`), e i passi che devono riuscire hanno 5 s invece di 1–2 (14/10 09:10:
  «timeout», ssh finto ancora in partenza). Con le porte che girano: prima **3 su 5** (le stesse
  cadute), dopo **10 su 10**.
- **`prova_agenti`, «tempo massimo: processo fermato» (8,5 e 9,6 s il 14/10): nel codice.** La
  sandbox parte a priorità «sotto il normale», e per uscire un processo deve ancora girare: con 30
  processi pieni un `while True` fermato a 3 s moriva dopo altri **4–9 s** (e oltre i 5 s di
  `proc.wait` la sandbox aspettava anche i lettori: 10,4 s). `winjob.JobObject.termina` porta ora i
  processi del job a priorità alta prima di `TerminateJobObject`: 0,02 s, esecuzione scaduta in
  **3,2 s** invece di 5,9–10,4 (il limite di priorità del job non bastava). Caso nuovo in
  `prova_agenti` (la priorità vista al momento di terminare).
- **`prova_telefono_audio`, «tempo scaduto: più di 300 s» (13/10, 14/10 09:44 e 09:52).** Tre
  trascrizioni «per confronto» (la frase accelerata ×2 e rallentata, come su iOS) non verificavano
  niente, e sull'audio accelerato con `-l it` Whisper ripete fino alla fine della finestra: con 20
  processi di carico quella sola trascrizione durava **122 s**, la prova 290 s. Ora solo con
  `--misure`: 290 → **172 s** con lo stesso carico, 182–230 → 116–126 s con tre corsie e 16 processi
  (6 su 6 verdi prima e dopo). «Durata giusta» (14/10 14:54 e 15:02): il microfono finto a 44,1 kHz
  di Chromium perde audio sotto carico (ritmo 0,923 e 0,942) mentre la catena di Calliope (16 kHz
  contro contesto) torna al centesimo: l'orologio ora con 0,15 (i guasti cercati sono ×1,5 e ×2).
- **`prova_esercizi_voce` (7 cadute del 14/10): la prova, né il codice né il carico.** «Quanto fa
  443 più 353?» contiene «3 più 3», e la verifica «la domanda inventata (3 più 3) non si dice»
  cercava il pezzo di testo: con i numeri a caso cadeva una volta su ~45 (3 su 130 nelle misure di
  prima). Ora il numero intero (`(?<!\d)3 più 3(?!\d)`, lo stesso per «125 più 87»): **90 su 90**
  con sei corsie e 16 processi.
- Non ripetute nelle misure: «la delega risponde subito» oltre i 150 ms (14/10 mattina, 315 e 352
  ms) e `lavoro_stato` (già rimisurato dal 14/10).

**`prova_satellite`: le attese fisse e una riconnessione lenta nel codice (17/10, #5).** Delle 22
`time.sleep` restano le 6 legittime, commentate; le 11 di assestamento aspettano una condizione
(il satellite riaddormentato, da `Satellite.ascolti`; il thread dentro la lettura; il messaggio
ricevuto; il record del keepalive) e le 5 negative hanno un segno positivo dopo; porte di Calliope
fuori dalle effimere (`prove/porte.py`). Sotto carico (3 corsie, 16 processi) la prima versione è
caduta in 2 giri su 3 su «il satellite si ricollega attraverso la «VPN»»: **nel codice**, il
satellite dopo una sessione collegata e caduta ripartiva dai tentativi falliti di prima (dopo il
riavvio lento di Calliope, 15 s invece di 1; [satelliti](../docs/aree/satelliti.md)). Corretto:
**59 giri su 60 verdi** con 3 corsie e 16 processi (durata mediana 131 s, massima 155; 6 frasi
ripetute dalla wake word in tutto). La caduta rimasta è un'altra: «TLS: 120 aperture», 118/120
con `InvalidMessage` e la più lenta a 4,8 s, cioè il server che chiude una stretta di mano oltre
il suo `open_timeout` di 3 s mentre 8 thread aprono insieme nello stesso processo della CPU
piena; non è un'attesa della prova e non si distingue, dalla prova, dal difetto del 03/10 che
quel controllo cerca: è un problema aperto, [#146](https://github.com/azatoth77/calliope/issues/146). *(Storico, 18/10: la causa era il pacchetto dei satelliti costruito nel processo del server, `ast.parse` che tiene il GIL fino a 0,3–0,6 s per file, proprio durante le aperture; ora in un processo a parte, [satelliti](../docs/aree/satelliti.md). Con lo stesso carico «TLS: 120 aperture» 60/60 prima e dopo, la più lenta per giro da 0,51 a 0,23 s di mediana; il controllo resta e cade ancora col difetto del 03/10 rimesso.)* Senza carico la prova dura
90–95 s contro 103–107 di prima. Contrario (la stessa prova che non aspetta il riaddormentarsi, 3 corsie × 4 giri con lo stesso
carico): 10 su 12, una caduta sul follow-up («ascolta» arrivato 0,33 s dopo l'inizio della
frase, attacco perso) e una sul rifiuto per l'Origin con 3 s di tempo massimo (ora 10 s, come i
rifiuti per il token: sono attese di una risposta).

**`prova_agenti_openai`: i tetti di 15 s e la sandbox affamata (18/10, #142).** Il lavoro di
codice finto esegue i test quattro volte nella sandbox «processo», a priorità «sotto il normale»:
con la CPU piena di processi a priorità normale (un `--completo`) ogni esecuzione prendeva fino a
27 s invece di 0,2–0,4, e il lavoro sforava i 15 s; poi gli errori a cascata. Ora le attese di un
evento sono larghe con la traccia (60 s per esecuzione, il lavoro 4 × 60 + 10 s) e ogni attesa
prende la fine del suo lavoro; resta il tetto di 1 s di «interrompi chiude lo stream subito», che è
la misura. Durante un `--completo` in un altro worktree main 0 su 10, il ramo 10 su 10. Con 32
processi pieni cade ancora (esecuzioni oltre i 60 s, dette nella traccia).
[agenti-estensioni](../docs/aree/agenti-estensioni.md)

**`prova_agenti`, `prova_sandbox`, `prova_esecuzione`: lo stesso criterio (18/10, #156).** `prova_agenti` aveva gli stessi tetti di 15 s e la stessa sandbox: ora 60 s per esecuzione, il
lavoro 4 × 60 + 10 s con la traccia, la fine di quel lavoro, lo stream partito al posto delle
attese fisse di 0,4 s; `prova_sandbox` dava 4 s di tempo massimo anche alle esecuzioni che devono
finire (ora 60, i 4 s solo dove sono la misura); in `prova_esecuzione` «avvia non aspetta Docker»
si prova con il thread dell'esecuzione fermo (nessun `docker run` prima del ritorno), e le attese
di fine sono di 60 s. Le misure nel documento d'area.
[agenti-estensioni](../docs/aree/agenti-estensioni.md)

**Problemi aperti delle prove** (18/10): con un carico più forte di quello del 17/10 (3 corsie, 16 processi e la macchina condivisa) `prova_satellite` cade circa 1 giro su 2, quasi sempre su «il satellite si ricollega attraverso la «VPN»» (si ricollega, ma oltre i 15 s), su main come sul ramo di #146 ([#155](https://github.com/azatoth77/calliope/issues/155)). *(Storico, 17/10: «TLS: 120 aperture» che cadeva 1 giro su 60: chiuso il 18/10, #146, sopra.)* *(Storico, 15/10: «le attese fisse di
`prova_satellite`», chiuso il 17/10, sopra.)* *(Storico, 14/10:
«la caduta rara di `prova_agenti` sul tunnel, da leggere con l'`errore` della diagnosi se torna»:
trovata il 15/10, sopra.)* *(Storico:
`prova_cronologia_pagina` con «Scarica Markdown» salvava il file nella cartella Download vera di
chi la lancia; dal 13/10 ogni profilo temporaneo ha la sua cartella di download nelle preferenze,
`download.default_directory`, e la prova controlla il file lì. `Page.setDownloadBehavior` sulla
scheda, che `prova_markdown_pagina` usa, in questa prova Edge lo ignorava.)*


## Le prove per area

Ogni prova con la sua descrizione è in [`elenco.md`](elenco.md), raggruppata per area. Una prova
nuova va in `elenco.md` (nella sua area) e in `prove/__main__.py`. L'elenco qui sotto è la prima
colonna delle tabelle di `elenco.md` e **si genera** (16/10, #82): dopo aver toccato `elenco.md`,
`python -m prove --leggimi`. `prova_runner` è rossa se l'elenco non è quello generato e se una
prova registrata in `prove/__main__.py` (o uno script di `manuali/`) manca da `elenco.md`.
*(Storico: fino al 15/10 l'elenco era scritto a mano, «rifatto il 09/10», e ne mancavano 126
voci.)*

<!-- elenco generato da elenco.md con `python -m prove --leggimi`: non scriverlo a mano -->
- **Voce, modello e regole sul testo** ([elenco](elenco.md#voce-modello-e-regole-sul-testo), [area](../docs/aree/voce-e-regole.md)): `prova_config.py`, `prova_config_modi.py`, `prova_reti_scatti.py`, `prova_dialogo_tool.py`, `prova_testo.py`, `prova_storpiature.py`, `prova_runner.py`, `manuali/carico.py`, `prova_docs_aree.py`, `prova_conflitti.py`, `prova_dati_privati.py`, `prova_tool.py`, `prova_rinomina_ollama.py`, `prova_robustezza.py`, `prova_ciclo_ripetuto.py`, `prova_preselezione.py`, `manuali/preselezione_dgx.py`, `prova_dopo_tool.py`, `manuali/dopo_tool_dgx.py`, `prova_brain.py`, `prova_risposta_sospeso.py`, `prova_sfida_esito.py`, `prova_sfida_esito_ollama.py`, `prova_brain_ollama.py`, `prova_gioco_giudice_ollama.py`, `prova_rivolta_ollama.py`, `prova_controlli_regressione.py`, `prova_regressione.py`, `ora_giusta.py`, `prova_llm.py`, `prova_native.py`, `prova_confronto.py`, `prova_ollama_tool.py`, `prova_debug.py`, `prova_prompt.py`, `prova_prompt2.py`, `prova_native2.py`, `prova_native3.py`, `prova_prompt3.py`, `prova_prompt4.py`, `prova_latency.py`, `prova_tool_scala.py`
- **Audio: wake word, STT, TTS, chi parla** ([elenco](elenco.md#audio-wake-word-stt-tts-chi-parla), [area](../docs/aree/stt-tts.md)): `prova_pronuncia.py`, `prova_stt_correzione.py`, `prova_argomenti_incerti.py`, `misura_argomenti_forse.py`, `prova_latenza.py`, `prova_pause.py`, `prova_frase_lunga.py`, `prova_frase_lunga_voce.py`, `prova_fine_turno.py`, `prova_fine_turno_voce.py`, `manuali/fine_turno_dgx.py`, `prova_whisper.py`, `prova_speaker.py`, `prova_voci_famiglia.py`, `prova_impronte_satellite.py`, `misura_stt.py`, `sintetizza_dominio.py`, `misura_parole_incerte.py`, `misura_pronuncia.py`, `manuali/misura_whistle.py`, `manuali/registra_whistle.py`, `prova_wakeword.py`, `prova_aec.py`, `misura_voci_compagnia.py`, `misura_rivolta.py`, `prova_compagnia.py`, `prova_stanza.py`, `prova_stanza_voce.py`, `prova_compagnia_stanza.py`, `prova_stanza_contesto.py`, `prova_stanza_storia.py`, `prova_stanza_attesa.py`, `prova_stanza_ricorda.py`, `prova_stanza_storpiata.py`, `manuali/banco_stanza_storpiata.py`, `prova_stanza_cerca.py`, `prova_stanza_eco.py`, `manuali/misura_eco_stanza.py`, `prova_stanza_tenuta.py`, `prova_stanza_conoscenti.py`, `prova_conoscenti_conserva.py`, `prova_stanza_guardia.py`, `prova_stanza_lenta.py`, `prova_stanza_lenta_blocchi.py`, `manuali/banco_stanza_guardia.py`, `manuali/banco_stanza_lenta.py`, `manuali/blocchi_stanza.py`, `manuali/ritrascrivi_conservati.py`, `manuali/misura_impronte_satellite.py`, `prova_compagnia_passo0.py`
- **Memoria, agenda, liste, calcoli** ([elenco](elenco.md#memoria-agenda-liste-calcoli), [area](../docs/aree/memoria-agenda-liste.md)): `prova_tempi.py`, `prova_agenda.py`, `prova_agenda_tutto.py`, `prova_liste.py`, `prova_casa.py`, `prova_date_ricordi_ollama.py`, `prova_calcola.py`, `prova_memoria.py`
- **Contesto e conversazione** ([elenco](elenco.md#contesto-e-conversazione), [area](../docs/aree/contesto-conversazione.md)): `prova_contesto.py`, `prova_conversazioni.py`, `prova_ricominciamo_ollama.py`, `prova_argomenti_ollama.py`, `misura_argomenti.py`, `prova_conversazioni_ollama.py`, `prova_ollama_carico.py`, `prova_eventi.py`, `prova_eventi_ciclo.py`, `prova_eventi_disco.py`, `prova_eventi_attivo.py`, `prova_dati_fissi.py`, `manuali/banco_cache_swa.py`, `manuali/banco_dati_fissi.py`, `manuali/misura_cache_prefisso.py`, `prova_eventi_guardia.py`, `prova_uscita_unica.py`, `prova_conserva.py`, `prova_conserva_valutazione.py`, `prova_banco_rotazione.py`, `prova_mulaw.py`, `prova_scelta_tool.py`, `prova_ciclo.py`, `prova_stati_buchi.py`, `prova_nome_da_solo.py`, `prova_corsie.py`, `prova_ctx.py`, `prova_numctx.py`, `prova_prompt_conversazione.py`, `misura_contesto.py`, `misura_conversazioni.py`, `misura_corsie.py`, `manuali/banco_stanza_contesto.py`, `manuali/banco_stanza_storia.py`, `manuali/banco_stanza_cerca.py`
- **Sicurezza, politica, conferme** ([elenco](elenco.md#sicurezza-politica-conferme), [area](../docs/aree/sicurezza-politica.md)): `prova_sicurezza.py`, `prova_politica.py`, `prova_conferma_unica.py`, `prova_dopo_annunci.py`, `prova_risultati.py`, `prova_conferme.py`, `prova_valore.py`, `prova_valore_dettato.py`, `prova_intento_no.py`, `prova_stato_dialogo.py`, `prova_attrito.py`, `prova_si_breve.py`, `prova_documento_proprio.py`, `misura_quarantena.py`, `misura_riferire.py`, `prova_risultato_pdf_ollama.py`, `misura_scalda_modalita.py`, `prova_risultati_ollama.py`, `prova_intento_no_ollama.py`, `prova_dialogo_ollama.py`, `prova_conferma_unica_ollama.py`, `prova_politica_ollama.py`, `misura_conferma_breve.py`, `misura_sfida.py`
- **Minori** ([elenco](elenco.md#minori), [area](../docs/aree/minori.md)): `prova_eta_utenti.py`, `prova_minori.py`, `prova_esercizi.py`, `prova_esercizi_pagina.py`, `prova_esercizi_ollama.py`, `prova_esercizi_programma_ollama.py`, `prova_materie.py`, `prova_esercizi_voce.py`, `prova_programma.py`, `prova_esercizi_programma.py`, `prova_minori_pericolo.py`, `prova_console_minori.py`, `prova_minori_cancelli.py`, `prova_minore_ospite.py`, `prova_avvisi_data.py`, `prova_avvisi_audio.py`, `misura_cancelli.py`, `prova_minori_ollama.py`, `misura_guardiano.py`
- **Casa (Home Assistant)** ([elenco](elenco.md#casa-home-assistant), [area](../docs/aree/casa.md)): `prova_casa_ha.py`, `prova_meteo_casa.py`, `prova_meteo_casa_ollama.py`, `prova_citta_casa_ollama.py`, `prova_casa_nomi.py`, `prova_casa_ha_ollama.py`, `sonda_ha.py`
- **PC a voce** ([elenco](elenco.md#pc-a-voce), [area](../docs/aree/pc.md)): `prova_pc.py`, `prova_pc_ollama.py`
- **Documenti, ufficio, archivio** ([elenco](elenco.md#documenti-ufficio-archivio), [area](../docs/aree/documenti-ufficio.md)): `prova_documenti.py`, `prova_documenti_ollama.py`, `prova_markdown.py`, `prova_ufficio.py`, `prova_ufficio_ollama.py`, `prova_archivio.py`, `archivio_misura_ocr.py`, `archivio_misura.py`, `prova_archivio_ollama.py`
- **Biblioteca e ricerca web** ([elenco](elenco.md#biblioteca-e-ricerca-web), [area](../docs/aree/biblioteca.md)): `prova_web.py`, `prova_notizie.py`, `prova_notizie_attesa.py`, `prova_ricerca_fuori_tema.py`, `manuali/banco_ricerca_fuori_tema.py`, `prova_searxng_aggiorna.py`, `prova_web_ollama.py`, `prova_notizie_ollama.py`, `prova_ricerche_distanza_ollama.py`, `prova_ricerca_seguito_ollama.py`, `misura_ricerche_fonte.py`, `prova_biblioteca.py`, `prova_zim.py`, `prova_biblioteca_indice.py`, `prova_arm_comune.py`, `arm/confronta_lettore.py`, `arm/bench_query.py`
- **Schermi e telefono** ([elenco](elenco.md#schermi-e-telefono), [area](../docs/aree/schermi-telefono.md)): `prova_schermi.py`, `prova_cruscotto.py`, `prova_cruscotto_pagina.py`, `cdp.py`, `prova_cronologia_schede.py`, `prova_cronologia_pagina.py`, `prova_scheda_intera.py`, `prova_vista_sviluppo_pagina.py`, `prova_markdown_pagina.py`, `prova_schermi_pagina.py`, `prova_cdp_orfani.py`, `prova_scritto.py`, `prova_rispondi.py`, `prova_scritto_conversazione.py`, `prova_scritto_pagina.py`, `prova_scritto_calliope.py`, `prova_telefono.py`, `prova_telefono_pagina.py`, `prova_telefono_abbina.py`, `prova_telefono_schermo.py`, `prova_telefono_audio.py`, `prova_schermi_ollama.py`, `prova_scritto_ollama.py`, `prova_compagnia_pagina.py`
- **Foto e allegati** ([elenco](elenco.md#foto-e-allegati), [area](../docs/aree/immagini-allegati.md)): `prova_immagini.py`, `prova_dispositivo.py`, `prova_immagini_attesa.py`, `prova_immagini_pagina.py`, `prova_immagini_ollama.py`, `prova_allegati.py`, `prova_allegati_ollama.py`, `prova_cassetto_ollama.py`, `prova_cassetto.py`, `prova_cassetto_pagina.py`, `misura_immagini.py`, `manuali/banco_dispositivo.py`
- **Satelliti** ([elenco](elenco.md#satelliti), [area](../docs/aree/satelliti.md)): `prova_config_satellite.py`, `prova_schermi_satellite.py`, `prova_satellite.py`, `prova_corsie_satelliti.py`, `prova_esecutore.py`, `prova_installa_satellite.py`, `misura_wyoming.py`
- **Agenti ed estensioni** ([elenco](elenco.md#agenti-ed-estensioni), [area](../docs/aree/agenti-estensioni.md)): `prova_agente_guida.py`, `prova_fasi_agente.py`, `prova_fasi_agente_2.py`, `manuali/banco_temperatura.py`, `manuali/banco_analisi_ragionamento.py`, `manuali/banco_revisore.py`, `manuali/misura_presence_penalty.py`, `misura_analisi_richiesta.py`, `banco_richieste.py`, `prova_estensioni.py`, `prova_estensioni_versioni.py`, `prova_sviluppo_giro3.py`, `prova_sviluppo_giro4.py`, `prova_estensione_rimuovi.py`, `prova_sviluppo_giro6.py`, `prova_giro_ombra.py`, `prova_giro_chiusura.py`, `prova_giro3.py`, `prova_giro4.py`, `prova_giro_pomeriggio.py`, `prova_giro_sera_gioco.py`, `prova_giro_halloween.py`, `prova_agente_giri_uguali.py`, `prova_porte_consegna.py`, `prova_partenza_gioco.py`, `prova_strumenti_onesti.py`, `prova_esito_giochi.py`, `prova_apri_gioco_tappa.py`, `prova_revisione_onesta.py`, `prova_specifica_viva.py`, `prova_voce_onesta.py`, `prova_flusso_ripresa.py`, `prova_giro_porte.py`, `prova_giro_porte_ollama.py`, `prova_sviluppo_giro5.py`, `prova_diagnosi_collaudi.py`, `prova_sonde.py`, `prova_scheda_sviluppo.py`, `prova_sviluppo_v2.py`, `prova_sviluppo.py`, `prova_estensione_nominata_ollama.py`, `prova_sviluppo_giro3_ollama.py`, `prova_sviluppo_giro6_ollama.py`, `prova_flusso_ripresa_ollama.py`, `prova_sviluppo_giro4_ollama.py`, `prova_estensione_rimuovi_ollama.py`, `prova_sviluppo_giro5_ollama.py`, `prova_sviluppo_v2_ollama.py`, `prova_sviluppo_ollama.py`, `prova_estensioni_attacchi.py`, `prova_sonde_attacchi.py`, `prova_contesto_agenti.py`, `prova_estensioni_piano.py`, `prova_estensioni_ollama.py`, `prova_estensioni_agente.py`, `prova_agenti.py`, `prova_sandbox.py`, `prova_agenti_domande.py`, `prova_analisi_richiesta.py`, `prova_avanzamento.py`, `prova_esecuzione.py`, `prova_agenti_openai.py`, `prova_arbitro_vllm.py`, `prova_arbitro_pausa.py`, `prova_lavori_riavvio.py`, `prova_agenti_ollama.py`, `prova_lavori_criteri.py`, `prova_lavori.py`, `misura_contesto_agenti.py`, `misura_arbitro_vllm.py`
- **Giochi** ([elenco](elenco.md#giochi), [area](../docs/aree/giochi.md)): `prova_giochi.py`, `prova_giochi_pagina.py`, `prova_gioco_stato_pagina.py`, `prova_gioco_voce.py`, `prova_gioco_macchina.py`, `prova_gioco_palco.py`, `prova_gioco_stato.py`, `prova_gioco_giocatori.py`
- **Capacità e installazioni** ([elenco](elenco.md#capacità-e-installazioni), [area](../docs/aree/capacita-installazioni.md)): `prova_capacita.py`, `prova_novita.py`, `prova_chi_sei_ollama.py`, `prova_piano.py`, `prova_arbitro_memoria.py`, `prova_arbitro_quiete.py`, `manuali/misura_memoria_dgx.py`, `prova_installa.py`, `prova_stato_ollama.py`
- **Personalità** ([elenco](elenco.md#personalità), [area](../docs/aree/personalita.md)): `prova_personalita.py`, `prova_modalita.py`, `prova_modalita_ollama.py`, `prova_frasi.py`, `prova_frasi_rotazione.py`, `prova_personalita_ollama.py`, `misura_tono.py`, `misura_frasi_pronte.py`
- **Linux e DGX** ([elenco](elenco.md#linux-e-dgx), [area](../docs/aree/setup-dgx.md)): `prova_linux.py`, `prova_linux_import.py`, `prova_gestore.py`, `prova_e2e_copioni.py`
<!-- fine dell'elenco generato -->

## Passi manuali

- [`manuali/schermi.md`](manuali/schermi.md): «Prova manuale degli schermi (da fare a voce)»; «Prova manuale di «scrivere invece di parlare» (03/10)»
- [`manuali/immagini-allegati.md`](manuali/immagini-allegati.md): «Prova manuale delle foto (05/10)»; «Prova manuale degli allegati (05/10)»
- [`manuali/satelliti.md`](manuali/satelliti.md): «Prova manuale del satellite sul portatile»; «Un PC nuovo come satellite con un comando (03/10)»; «Prima prova end-to-end con la DGX (satellite in VPN)»
- [`manuali/telefono.md`](manuali/telefono.md): «Prova manuale del telefono (web app, 03/10)»; «Telefono da fuori casa (03/10; inoltro tolto il 16/10, #61)»
- `manuali/risultati-2026-09-23.md` (privato, fuori dal repository): risultati dei test del 23–24/09
- [`manuali/dgx-agenti.md`](manuali/dgx-agenti.md): «Prima prova sulla DGX Spark (agenti, 02/10/2026)»
- [`manuali/dgx-web-estensioni-giochi.md`](manuali/dgx-web-estensioni-giochi.md): «Ricerca su internet sulla DGX (SearXNG, 03/10)»; «Estensioni sulla DGX (04/10)»; «Giochi sulla DGX (05/10)»
- [`manuali/e2e-dgx.md`](manuali/e2e-dgx.md): «Prova end-to-end sulla DGX, senza nessuno che parli (06/10)»: istanza di prova separata, satelliti finti con VAD e wake word veri, voce vera di chi amministra, `python -m prove.e2e.lancia`
