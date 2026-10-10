# Calliope — visione del progetto

*Bozza del 21 settembre 2026, da confermare. Nasce dalla seconda sessione di lavoro (in
Claude Code), dopo il primo test reale del prototipo v0.2. Le "Decisioni aperte"
aspettano l'esito di ricerche in corso.*

## In una frase

Calliope è **l'assistente vocale di casa**: un server locale sempre acceso a cui tutta
la famiglia parla da ogni stanza. Conversa, agisce (sui PC e sulla casa), consulta una
biblioteca offline e i documenti personali e, per i lavori complessi, orchestra altri
agenti AI. **Funziona anche senza internet.**

## Requisiti

| # | Tema | Decisione |
|---|---|---|
| 1 | **Scopo** | Conversazione e domande · azioni sui PC · domotica · conoscenza personale (documenti, note) · **conoscenza generale offline**: accesso a "tutto lo scibile umano oggi disponibile", scaricato in locale per quando internet manca. |
| 2 | **Forma** | **Server di casa** sull'RTX Spark, con microfoni e altoparlanti "satellite" nelle stanze. Finché lo Spark non c'è, il portatile fa da server e da primo satellite. |
| 3 | **Rete** | **Prima di tutto offline.** Tutto deve funzionare senza internet. Se la rete c'è, alcuni tool possono usarla, soprattutto per informazioni in tempo reale (meteo, notizie…). Voce, trascrizione e LLM non vanno mai in cloud. |
| 4 | **Destinatari** | **La casa**: più persone. Serve riconoscere chi parla, con preferenze, memoria e permessi per persona. |
| 5 | **Agenti** | Calliope lavora **orchestrando più agenti AI**. Gli agenti possono essere LLM diversi oppure lo stesso LLM con configurazioni specifiche. |
| 6 | **Musica** | Requisito irrinunciabile. Riproduzione nelle stanze comandata a voce: **offline** da una raccolta di MP3 sul server **divisa per persona** («metti la mia musica» dipende da chi parla), **online** quando c'è internet. |
| 7 | **Ospiti** | Chi non viene riconosciuto è un **ospite**: accesso limitato, può fare relativamente poco. Si parte dal minimo e si sale solo per chi è riconosciuto. |
| 8 | **Sicurezza** | Con **sensori di presenza** e un **sistema di allarme** integrati, Calliope diventa anche la sentinella di casa: ad allarme inserito **registra in silenzio la voce degli intrusi**, fa partire un **allarme sonoro su tutte le casse** e soprattutto **avvisa i proprietari**, anche senza internet, con **SMS da un modem GSM** collegato al server. |
| 9 | **Identità personalizzabile** | Oggi nome, wake word e voce sono "Calliope" con voce femminile; domani potrebbero essere altri. Nome, wake word, voce (femminile o maschile) e carattere sono **configurazione**, mai scritti nel codice. Personalizzare la voce è importante. |

## Conseguenze sull'architettura

```
 SATELLITE (stanza o PC)                        SERVER CALLIOPE (portatile oggi, Spark domani)

 microfono → wake word → audio ─ rete locale ─▶ STT → chi parla? → CALLIOPE, agente vocale (veloce)
 altoparlante ◀─ audio ◀────────────────────── TTS ◀── frasi ◀────┘      │ delega
 [sui PC: esecutore di azioni]                                           ▼
                                                 ORCHESTRATORE → agenti in secondo piano
                                                 (bibliotecaria · casa · PC · ricerca · ragionatore…)
                                                                          │
                                                 TOOL: biblioteca offline · documenti personali ·
                                                       Home Assistant · PC di casa · web (se c'è)
```

1. **Da processo unico a server + satelliti.** La wake word si sposta sul satellite;
   STT, LLM, TTS e tool stanno sul server. Il prototipo attuale è "server e satellite
   nella stessa scatola": i moduli restano gli stessi, cambia il trasporto dell'audio.
2. **Un agente è una configurazione**: modello, prompt di sistema, thinking acceso o
   spento, temperatura, tool, contesto. Con 8 GB di VRAM più agenti condividono gli
   stessi pesi con configurazioni diverse; sullo Spark possono essere modelli diversi
   caricati insieme (MoE grandi per ragionare, modello piccolo per la voce).
3. **Primo piano veloce, secondo piano profondo.** Misurato il 21/09/2026 su
   `qwen3:8b`: senza thinking la prima frase arriva in 0,57 s, con il thinking in
   4,96 s (fino a 9,75 s). Quindi l'agente vocale non ragiona mai "a lungo": risponde
   subito oppure delega e dice «ci penso, ti faccio sapere».
4. **Ciclo a eventi, non più bloccante.** Oggi il programma fa ascolta → rispondi →
   ascolta. Con gli agenti Calliope deve poter parlare *di sua iniziativa* quando un
   lavoro finisce, gestire più lavori in coda, essere interrotta.
5. **Tutto è un tool.** Biblioteca, documenti, domotica, azioni sui PC e web sono tool
   con la stessa interfaccia. Ogni tool dichiara se richiede internet: senza rete
   sparisce dall'elenco e Calliope lo dice con semplicità, il resto continua a funzionare.
6. **Il modello deve saper usare i tool.** Diventa un criterio di scelta dell'LLM accanto
   a italiano, latenza e VRAM.
7. **La conoscenza sta nella biblioteca, non nel modello.** I modelli piccoli sbagliano
   i fatti (nel test: «Lorenzo e Lucia», la Luna «composta da un ghiaccio»). Le risposte
   sui fatti vanno fondate su passaggi recuperati da fonti locali (Wikipedia offline e
   simili), con il modello che li riassume a voce.
8. **Azioni sui PC = un piccolo esecutore su ogni PC.** Il server non può aprire un
   programma su un'altra macchina: serve un agente locale che riceve comandi dalla rete
   di casa. Sui PC il satellite audio e l'esecutore possono essere lo stesso programma.
9. **Famiglia = identità e permessi, ospite come punto di partenza.** Ogni richiesta
   nasce con i permessi dell'ospite e sale di livello solo se la voce è riconosciuta
   (ospite → familiare → chi amministra). L'errore pericoloso è scambiare un estraneo per
   un familiare, non il contrario: nel dubbio si resta ospiti. I permessi si applicano
   **ai tool, nel codice**, non nel prompt: all'ospite i tool vietati non vengono
   nemmeno mostrati al modello, così nessuna frase furba può farglieli usare. La voce
   da sola si può imitare o registrare: per le azioni sensibili (porta, allarme,
   documenti di un altro) servirà un secondo fattore, da definire con la sicurezza.
10. **La musica cambia i satelliti.** Per la sola voce basta un altoparlantino; per la
    musica servono casse vere, e bisogna sentire la wake word *con la musica accesa*
    (cancellazione dell'eco con riferimento al segnale riprodotto). La raccolta per
    persona si appoggia all'identità di chi parla; la musica è un tool come gli altri
    (e senza internet resta la raccolta locale).

### Sicurezza e allarme (proposta)

- **La catena di allarme non passa dall'LLM.** Sensore → regola → sirena, registrazione,
  SMS: è codice deterministico, provabile e sempre uguale. Un modello da 4B che ogni
  tanto sbaglia non deve mai decidere se suonare un allarme. L'LLM serve prima (inserire
  l'allarme a voce) e dopo (farsi raccontare cos'è successo), mai in mezzo.
- **Inserire a voce sì, disinserire a voce no.** Inserire è un'azione a basso rischio;
  disinserire con la sola voce no, perché una voce si registra o si clona: serve un
  secondo fattore (codice su tastierino o telefono, presenza del telefono di casa, SMS
  con PIN). Coerente con "chi parla ≠ autorizzazione".
- **L'errore da evitare cambia verso.** In conversazione il rischio è scambiare un
  estraneo per un familiare; ad allarme inserito il rischio è il contrario (un familiare
  non riconosciuto → falso allarme): servono ritardo di entrata, preavviso e un modo
  rapido per dichiararsi.
- **La centrale fa l'allarme, Calliope fa il resto.** Una casa ha spesso già una
  **centrale d'allarme certificata**, magari con rete LAN e **modulo cellulare**, usata
  tramite il cloud del produttore. Se ha la rete, un'integrazione locale con Home
  Assistant è plausibile (da verificare: API, chiave, ruolo dell'installatore). L'avviso ai proprietari senza internet
  è quindi già coperto dalla parte certificata, e il modem di Calliope diventa un canale
  in più, non quello principale. Resta lei il sistema d'allarme: sensori,
  sirena, batteria tampone, eventuale comunicatore cellulare certificato. Home Assistant
  ne legge lo stato (inserito, aree, allarme in corso) ed eventualmente attiva scenari,
  **preferibilmente con un'integrazione locale** e non tramite il cloud, per restare
  fedeli a "prima di tutto offline". Calliope legge lo stato da Home Assistant e aggiunge
  ciò che manca: comandi a voce, ascolto e registrazione dai satelliti, allarme su tutte
  le casse, SMS dal proprio modem come canale in più, racconto dell'accaduto. Così se
  Calliope è spenta o sbaglia, l'allarme funziona lo stesso.
- **Più canali di avviso, con escalation.** SMS dal modem (funziona senza internet),
  notifica via internet se c'è, eventuale chiamata; se il primo proprietario non conferma
  entro pochi minuti si passa al secondo. Gli SMS di comando in ingresso valgono solo
  con PIN: il numero del mittente si può falsificare.
- **Continuità.** Chi entra può staccare corrente e rete: gruppo di continuità per
  server, Raspberry, router e modem; il modem GSM è l'unico canale che non dipende
  dalla linea di casa (ma si può disturbare con un jammer: un segnale periodico di
  "tutto bene" rende sospetto anche il silenzio).
- **Registrare solo ad allarme inserito, e dirlo.** I microfoni di casa devono restare
  degni di fiducia: nessuna registrazione continua in condizioni normali, stato sempre
  visibile, registro di quando e perché si è registrato, conservazione limitata,
  archivio protetto. Aspetti legali (ospiti, collaboratori domestici) da verificare.
- **I sensori di presenza servono anche tutti i giorni**: rispondere nella stanza in
  cui c'è qualcuno, far seguire la musica, ignorare la TV accesa in una stanza vuota.
- **Non è un impianto certificato.** Va pensato come complemento di un allarme vero,
  non come sostituto (assicurazione, vigilanza).

### Come si delega (proposta)

Più agenti servono a due cose: tenere **minimo il contesto della conversazione** (meno
VRAM, prima frase più veloce, e i modelli piccoli rendono meglio con poco contesto) e
**gestire le richieste complesse** con agenti stretti, ognuno con pochi tool e la sua
configurazione. Per non pagare il prezzo in errori e latenza:

- **Tre livelli, sempre il più basso che basta**: (1) risposta diretta; (2) una sola
  chiamata a un tool, senza agente; (3) delega a un agente, solo per lavori a più passi.
- **Un agente è un tool con un LLM dentro.** Calliope vede
  `chiedi_alla_bibliotecaria(domanda)` accanto a `accendi_luce(stanza)` e sceglie con il
  normale tool calling: nessun router separato, nessuna chiamata in più.
- **A raggiera, non a chiacchiera.** Calliope al centro, agenti che non si parlano tra
  loro. L'orchestrazione è codice deterministico; consegne e risultati sono strutturati
  (obiettivo, vincoli, per chi → esito, fonti, cosa dire a voce).
- **La memoria sta fuori dal contesto**: un registro dei lavori (in corso, finiti, per
  chi) e una memoria strutturata per persona, consultati quando servono.

### Auto-miglioramento (proposta del 24/09/2026)

Oggi il ciclo si fa a mano: test vocale → registrazioni → analisi → correzioni → nuovo
test. L'idea è che Calliope lo faccia in parte da sola, di notte, quando la GPU è libera,
come agente in secondo piano. Il ciclo è **misura, proposta, approvazione**: non si
corregge da sola alla cieca.

- **Il segnale c'è già, gratis.** Quando una frase viene ripetuta entro pochi secondi con
  un testo simile ma diverso, la prima era quasi certamente una trascrizione sbagliata e
  la seconda ne è il riferimento. Nel test del 24/09 è successo quattro volte, per esempio
  «Equale rospaniac» → «E quella della Spagna?». Lo stesso vale per «no, ho detto…», per
  un «non ho capito» dell'LLM e per un'uscita non riconosciuta. Il **registro dei turni**
  (JSONL, un file al giorno) raccoglie tutto questo, insieme a punteggio della voce, tool,
  interventi della guardia e tempi.
- **Cosa può migliorare quasi da sola** (basso rischio, verificabile): il vocabolario di
  Whisper (nomi di famiglia, luoghi, nomi delle voci → prompt iniziale e `hotwords`), le
  allucinazioni da filtrare, le varianti delle parole di comando, l'aggiornamento
  dell'impronta vocale **solo** con campioni sopra soglia e conservando quella di partenza.
- **Cosa può solo proporre**: prompt di sistema, codice e permessi. Un modello che riscrive
  le proprie regole non è verificabile, e basta un ospite furbo per avvelenarlo.
- **Ogni proposta passa un esame**: un set di regressione fatto di registrazioni con il
  testo giusto (il primo è nato con la taratura di Whisper del 24/09) più le prove di
  conversazione di `prove/`. Si accetta solo ciò che migliora le misure. Il rapporto
  notturno dice cosa propone e con quale effetto misurato, per esempio «aggiungere
  "Lipari" alle hotwords: errore sulle parole dal 9 al 6 %». Chi amministra approva.
- **Giudice debole**: un modello da 4B che valuta sé stesso è poco affidabile. Dove si può
  si usano controlli deterministici (regex per il «lei» e il markdown, tool chiamati,
  tempi), e l'LLM solo per classificare, per esempio «queste due frasi sono la stessa
  richiesta?». Sullo Spark la revisione notturna può usare un modello più grande.
- **Privacy**: la voce degli ospiti non si salva e il loro testo non si registra; registro
  e registrazioni si cancellano dopo un numero di giorni stabilito in configurazione.
  Serve anche un comando per svuotarli.
- Più avanti, con qualche ora di dati: adattamento fine di Whisper sulle voci di casa,
  da valutare sullo Spark.

## Principi: cosa cambia rispetto a `CLAUDE.md`

I nove principi restano validi. In più:

- **9 — Niente cloud** diventa **"prima di tutto offline"**: l'IA è sempre locale;
  internet è un extra facoltativo per i dati in tempo reale, mai un requisito.
- **8 — Half-duplex** vale per satellite: dipende dall'hardware audio di ogni stanza.
- **10 (nuovo) — Una voce sola, molti agenti.** Chi parla ha a che fare solo con
  Calliope; gli agenti sono un fatto interno e non hanno voce né nome propri.
- **11 (nuovo) — Primo piano veloce, secondo piano profondo.** Niente che superi circa
  un secondo può stare sul percorso della risposta vocale.
- **12 (nuovo) — Degradare con grazia.** Senza internet, senza un satellite, senza un
  tool o senza GPU, Calliope continua a fare tutto il resto.
- **13 (nuovo) — Stessa architettura, taglia diversa.** I limiti di oggi (8 GB di VRAM,
  modelli da 4B) non devono diventare limiti del progetto. Tool e interfacce sono gli
  stessi su portatile e Spark; cambia un **profilo** in configurazione: quale LLM, quanta
  biblioteca, quanto grafo. Sul portatile: sottoinsieme italiano di Wikidata, Wikipedia
  italiana, tool a campi vincolati. Sullo Spark: Wikidata intero, fonti in inglese rese
  in italiano da un modello che traduce bene, interrogazioni libere scritte da un agente
  ragionatore in secondo piano. Si sviluppa oggi in piccolo ciò che non dipende dalla
  taglia; domani si cambia profilo senza riscrivere.
- **14 (nuovo) — Integrazioni a moduli: capacità al centro, marche ai bordi.** Ogni
  sistema esterno (allarme, musica, domotica, SMS, biblioteca, PC di casa) entra in
  Calliope attraverso un'**interfaccia di capacità** («allarme», «riproduttore musicale»,
  «invio messaggi»…) e un **adattatore** specifico per marca o prodotto, scelto in
  configurazione. Il nucleo, i tool mostrati all'LLM e i prompt parlano solo di capacità
  (`stato_allarme`, mai il nome di una marca): se domani arriva un'altra marca si scrive un
  adattatore e non si tocca altro.
  - **Primo livello di indipendenza: Home Assistant.** Dove esiste, si passa dalle sue
    entità generiche (`alarm_control_panel`, `binary_sensor`, `media_player`…): cambiare
    marca diventa un problema di Home Assistant e Calliope non se ne accorge.
  - **Secondo livello: adattatori propri**, solo per ciò a cui Calliope parla
    direttamente (modem, Music Assistant, biblioteca, esecutore sui PC, satelliti).
  - Ogni adattatore **dichiara** cosa sa fare, se richiede internet, quale livello di
    permesso serve e la classe di rischio di ogni azione (sola lettura, reversibile,
    irreversibile): sono gli stessi dati che servono a ospiti, conferme e modalità offline.
  - Senza esagerare: l'interfaccia nasce piccola insieme al primo adattatore e si
    generalizza quando arriva il secondo; i nomi di marca, però, restano fuori dal
    nucleo fin dal primo giorno.

## Decisioni aperte

| # | Decisione | Stato |
|---|---|---|
| A | **Home Assistant e satelliti**: costruire tutto da zero (C), lasciare a Home Assistant audio e satelliti con Calliope come cervello (A), oppure parlare direttamente con i satelliti e usare Home Assistant solo per i dispositivi (B). Ricerca conclusa, vedi [`ricerche/2026-09-21-home-assistant-e-satelliti.md`](ricerche/2026-09-21-home-assistant-e-satelliti.md). Raccomandazione: **"A+" subito, B come evoluzione, mai C** — Home Assistant su un dispositivo dedicato; Calliope espone un endpoint compatibile OpenAI (HA 2026.8 lo accetta come agente di conversazione senza codice dentro HA), più STT e TTS come servizi Wyoming; se la latenza misurata non convince si passa a B con gli stessi satelliti. **Home Assistant c'è già, su un Raspberry Pi**, quindi A+ è il passo naturale. | *storica fino al 10/10: «orientata verso A+»*. **Decisa B il 10/10**: i satelliti di oggi parlano l'API di ESPHome, non Wyoming; Calliope parla loro direttamente, Home Assistant solo per i dispositivi ([`decisioni/0026`](decisioni/0026-satelliti-esphome-senza-home-assistant.md), [`ricerche/2026-10-10-wyoming.md`](ricerche/2026-10-10-wyoming.md)) |
| B | **Biblioteca offline**. Ricerca conclusa, con prototipo misurato: [`ricerche/2026-09-21-biblioteca-offline.md`](ricerche/2026-09-21-biblioteca-offline.md). Raccomandazione: file **Kiwix/ZIM** + ricerca **ibrida** (parole chiave → indice full-text già dentro gli ZIM, 2–7 ms → rerank di ~20 paragrafi con `bge-m3`): **0,41–0,51 s** end-to-end, 5 risposte buone su 7. Primo scarico ~11 GB (Wikipedia it senza immagini 8,4 GB + versione "mini" 2,3 GB come corsia veloce + Wikizionario + WikiMed); tutta la biblioteca italiana ≈ 16 GB; livelli da 33 GB, 211 GB, 1,4 TB. Niente aggiornamenti incrementali: si riscarica ogni 3–6 mesi. Vincolo: `bge-m3` (0,66 GB) deve restare in VRAM → con 8 GB spinge verso un LLM da 4B. `libzim` non ha wheel Windows ARM64 (piano B: estrazione in SQLite FTS5). **Fatto il 26/09** ([`ricerche/2026-09-26-biblioteca-prova.md`](ricerche/2026-09-26-biblioteca-prova.md)): mini + nopic di Wikipedia italiana (11,4 GB), ricerca lessicale su CPU in ~30 ms; il rerank con `bge-m3` non migliorava e non serve, quindi niente vincolo di VRAM. Tool `biblioteca_cerca`. | fatto |
| B-bis | **Grafo di conoscenza**, non considerato nella prima ricerca (la consegna confrontava solo strategie di ricerca nei testi). Tre usi distinti da valutare: (1) un **sottoinsieme di Wikidata** come tool `fatto(entità, proprietà)` per le domande "chi, cosa, quando, quanto", a più passi o con confronti, dove un modello piccolo inventa i numeri e la ricerca nei testi è debole: complementare alla biblioteca, non alternativo; (2) **grafo estratto da un LLM (GraphRAG)**: improponibile su scala Wikipedia, plausibile sui documenti personali come lavoro notturno di un agente; (3) il **grafo di casa come memoria** di Calliope (persone, stanze, dispositivi, abitudini, con provenienza, data e visibilità per persona), in SQLite. | ricerca in corso |
| C | **Orchestrazione**. Ricerca conclusa: [`ricerche/2026-09-21-orchestrazione-agenti.md`](ricerche/2026-09-21-orchestrazione-agenti.md). Raccomandazione: **strato proprio (~500 righe) sopra il client `openai`**, nessun framework sul percorso vocale; MCP come confine dei tool, con parsimonia (5–10 tool per agente). Motivo decisivo: far passare la voce davanti a un lavoro in secondo piano sulla stessa GPU non lo risolve nessun framework né Ollama (coda FIFO, nessuna priorità): l'**arbitro della GPU** va scritto comunque. Con 8 GB: un solo modello residente condiviso da tutti gli agenti (prompt, thinking e temperatura non provocano ricaricamenti; `num_ctx` sì). | da confermare |
| D | **LLM vocale**: 4B contro 8B su italiano, latenza, VRAM e ora anche tool calling. Misurato il 21/09/2026: `gemma3:4b` ha l'italiano migliore (2,9 GB, prima frase ~0,3 s) ma **in Ollama non supporta i tool**; `qwen3.5:4b` usa i tool (3/4) ma il suo italiano è scadente e inventa fatti; `qwen3:8b` senza thinking sceglie bene i tool (4/4) con un italiano discreto, ma occupa 5,6 GB; `llama3.1:8b` 4/4 sui tool, italiano e fatti deboli. **Esito** ([`ricerche/2026-09-21-confronto-llm.md`](ricerche/2026-09-21-confronto-llm.md)): **`gemma4:e4b-it-qat` a temperatura 0,3** — tool 4/4 in tre ripetizioni, è quello che inventa meno (ammette sempre di non sapere l'ora, mai nomi o date sbagliati), rispetta il prompt, prima frase 0,25–0,55 s, ~4,1 GiB reali di VRAM (con Whisper restano ~1,8 GiB, abbastanza per `bge-m3`). Difetti: ogni tanto una parola malformata ("meteomologia", "museI": forse la quantizzazione QAT) e contenuti un po' generici. Riserva: `gemma4:e2b-it-qat` (2,7 GiB, 0,25 s) come instradatore di tool se la VRAM stringe; da solo ragiona male. La temperatura 0,3 conviene con tutti i modelli. `ollama ps` sottostima i Gemma di ~1 GiB: fidarsi di `nvidia-smi`. | scelto, è il predefinito in `Config`; da confermare a voce |
| E | **Chi parla**: quale riconoscimento del parlante, con poche dipendenze native. | da studiare |
| F | **Hardware per le stanze**. Ricerca conclusa: [`ricerche/2026-09-21-musica-e-hardware-audio.md`](ricerche/2026-09-21-musica-e-hardware-audio.md). Regola: **le casse vanno collegate via cavo al satellite**, perché solo così il chip XMOS conosce il segnale riprodotto, sente la wake word sopra la musica e abbassa subito il volume; con casse di rete (Sonos, WiiM, AirPlay, TV) la musica è solo rumore. Per iniziare, una stanza: **Voice PE (~65 €) + alimentatore (~8 €) + casse attive Edifier R1280DB (~100–110 €) ≈ 175–185 €**. Stanze grandi o rumorose: ReSpeaker XVF3800 + casse ≈ 205 €. Cinque stanze ≈ 535–1.060 € secondo la fascia; si compra una stanza alla volta. Postazione PC: cuffie + app desktop di Music Assistant, costo zero. Non verificata la resa della wake word con musica alta. **Satelliti costruiti in casa con ESPHome**: possibili; ciò che conta è il chip audio (cancellazione dell'eco, più microfoni), non l'ESP32. Un ESP32-S3 con microfono I2S (15–25 €) va bene come banco di prova, per stanze senza musica e come microfono a firmware proprio per la registrazione ad allarme inserito; per le stanze con musica serve un chip audio vero (kit ReSpeaker XVF3800, che è il fai-da-te che vale, oppure Voice PE/Satellite1). Proposta: comprarne due di tipo diverso e confrontarli con il copione di `test-vocale.md` a più distanze e con la musica accesa. Altoparlanti intelligenti commerciali già in casa non servono come microfoni di Calliope. | da confermare |
| G | **Musica**. Stessa ricerca. Raccomandazione: **Music Assistant** come add-on sul Raspberry Pi che ospita già Home Assistant (serve un Pi 4/5 con almeno 4 GB; su Windows la scoperta dei player in rete è problematica). La raccolta resta sul server Calliope come condivisione di rete: una cartella per persona più una comune, un utente per persona che vede "la sua + comune", l'ospite solo la comune. Calliope lo comanda come tool (client Python o server MCP integrato) con un token per persona. Limite: a server spento la musica locale non c'è. Da verificare: uso prolungato senza internet, filtri per utente via API. | da confermare |
| H | **Sicurezza e allarme**: livelli di permesso, secondo fattore per le azioni sensibili, registri di ciò che è stato fatto e da chi; sensori di presenza, allarme, registrazione degli intrusi, sirena sulle casse, SMS da modem GSM (vedi "Sicurezza e allarme" sopra). Ricerca conclusa il 21/09 (rapporto privato: descrive un impianto vero). **La catena critica (sensore → sirena → SMS/chiamata) esiste già nella centrale d'allarme** (certificata, con batteria e comunicatore cellulare): né Alarmo né il modem di Calliope servono come canale principale. Integrazione con Home Assistant: via cloud subito (dipende da internet), in locale con API ufficiale a chiave (da verificare con il modello di centrale), con protocollo nativo o SIA-IP in sola lettura; piano B sempre valido: due uscite programmabili → ESP32/ESPHome (~20 €, serve l'installatore). **Regola: le credenziali date a Home Assistant non devono poter disinserire, e Calliope non ha alcun tool di disinserimento.** Registrazione degli intrusi: possibile ma non con il firmware di serie dei satelliti (da prototipare; alternative: Raspberry con linux-voice-assistant, telecamere con audio); per legge conviene registrare **solo in "inserito totale"** (casa vuota), informare colf e babysitter, tenere le impronte vocali dei soli familiari in locale. "Sirena" sulle casse = deterrente vocale, la sirena vera resta quella della centrale. Sensori di presenza: servono a Calliope, non a far scattare l'allarme. Gruppo di continuità per Raspberry, router e server, altrimenti al taglio della corrente lo strato intelligente sparisce. 2G ancora acceso in Italia (orizzonte fine 2029): da verificare se il comunicatore installato è solo 2G. | da confermare; primi passi possibili |
| I | **Voce e personalizzazione**. Ricerca conclusa: [`ricerche/2026-09-21-voci-e-tts.md`](ricerche/2026-09-21-voci-e-tts.md). Il catalogo ufficiale di Piper ha solo 4 voci italiane (3 femminili, 1 maschile di qualità bassa), ma **esistono voci maschili della community** (Leonardo, Giorgio, UGO, Miro) e altre femminili (Aurora, Dii): si installano copiando due file, stessa latenza; tutte in `voices/` con campioni in `voices/campioni/` e licenze in `voices/LEGGIMI.md`. **Strada per una voce su misura**: la voce ufficiale "serena" è nata proprio così — un TTS lento ma espressivo (Qwen3-TTS) genera un dataset sintetico, con cui si addestra una voce Piper veloce; strumento, dataset e checkpoint italiano sono pubblici, e l'addestramento gira sulla RTX 5070 (via WSL2, con LLM e Whisper spenti). Partendo da una voce "progettata" e non clonata non c'è alcun problema di consenso. Da tenere d'occhio: **Pocket TTS** (Kyutai: CPU, ~200 ms, italiano, voce maschile, clonazione); Supertonic 3 è buono ma archiviato; Kokoro in italiano ha accento inglese. **Windows ARM**: `sherpa-onnx` (wheel ARM64 da agosto 2026) esegue le stesse voci Piper: chiude il rischio segnalato sopra per il TTS. Nel codice, genere e personaggio sono ora campi di `Config` e la wake word può avere più parole. | da confermare |

## Rischi emersi dalle ricerche

- **Windows su ARM (Spark)**: al 21/09/2026 `ctranslate2` (quindi faster-whisper) e
  `piper-tts` **non hanno wheel `win_arm64`**; `onnxruntime` sì (Silero VAD, wake word e
  riconoscimento del parlante in ONNX sono a posto). STT e TTS sullo Spark dovranno
  girare in WSL2 o in container (i wheel Linux aarch64 esistono) dietro un protocollo di
  rete, oppure essere sostituiti (whisper.cpp…). È la conferma del principio 2, e un
  motivo per fare di **Wyoming il confine tra i moduli**.
- **I satelliti non parlano più Wyoming**: `wyoming-satellite` è archiviato (gennaio
  2026); i satelliti vivi (Voice PE, Satellite1, ESP32-S3, Raspberry con
  linux-voice-assistant) parlano l'API nativa ESPHome, che non è un contratto pubblico
  per server di terze parti. L'architettura B è quindi più costosa e fragile del previsto.
- **Piper è passato a GPL-3.0** (`piper1-gpl`): irrilevante per un uso in casa, da
  ricordare se un giorno Calliope venisse distribuita.
- **Chi parla ≠ autorizzazione**: il riconoscimento vocale serve per preferenze e
  memoria; non va usato da solo per autorizzare azioni sensibili.

## Fasi proposte

| Fase | Contenuto | Dove |
|---|---|---|
| 0 | Prototipo vocale v0.2, provato sull'hardware reale | fatto |
| 1 | **Nucleo**: package, configurazione esterna, ciclo a eventi, tool calling con i primi tool offline (ora, timer, promemoria), scelta dell'LLM | portatile |
| 2 | **Agenti**: orchestratore, agenti come configurazioni, lavori in secondo piano con thinking, annunci a voce a lavoro finito | portatile |
| 3 | **Conoscenza**: biblioteca offline e documenti personali come tool | portatile |
| 4 | **Casa**: separazione server/satellite, wake word dedicata, Home Assistant | portatile + primo satellite |
| 5 | **Famiglia**: riconoscimento di chi parla, memoria e permessi per persona | — |
| 5-bis | **Auto-miglioramento**: registro dei turni (avviato il 24/09), rilevamento delle ripetizioni, set di regressione, revisione notturna con proposte misurate | portatile, poi Spark |
| 6 | **PC**: esecutore di azioni sui PC di casa | — |
| 7 | **Spark**: migrazione, modelli MoE, più modelli in parallelo, verifica di ogni dipendenza su Windows ARM | Spark |

L'ordine mette i tool e gli agenti prima di tutto perché biblioteca, casa e PC sono,
per Calliope, "solo" altri tool e altri agenti: una volta pronto il nucleo si
aggiungono senza toccare la pipeline vocale.
