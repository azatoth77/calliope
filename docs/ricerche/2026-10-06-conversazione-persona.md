# Una conversazione per persona e più satelliti insieme (06/10/2026)

*Fase 3 del progetto «Contesto di Calliope» (decisioni di Dario del 05/10). Ramo
`conversazione-persona`. Prove a secco sul portatile (`prove/prova_corsie.py`,
`prove/prova_corsie_satelliti.py`) e una misura sulla DGX (~4 minuti di GPU: una seconda
Calliope con la voce di produzione, gemma4 26B su Ollama 0.35 con la stessa finestra, senza
toccare il servizio né la configurazione di Ollama; `prove/misura_corsie.py`).*

*Legenda: **[M]** misurato · **[D]** deduzione.*

## In breve

- **Una conversazione per persona riconosciuta**, ripresa da qualunque satellite: Dario dice
  «il mio gatto si chiama Micio» al portatile e chiede «come si chiama il mio gatto?» dalla
  cucina → «Si chiama Micio.» [M]. Storia, azione in sospeso, riferimenti, foto, allegati,
  riassunto e numero dei turni viaggiano con lei (`calliope/corsie.py`,
  `RegistroConversazioni`).
- **Regole** (approvate il 05/10): si apre o si riprende solo con la voce sopra la soglia
  normale; frase breve e zona grigia continuano solo la conversazione di chi ha parlato
  **su quel satellite** nella sua finestra di ascolto; un «sì» breve su un altro satellite
  non raccoglie un'azione in sospeso nata altrove (regola `sospeso_altro_satellite`, la
  proposta resta); ospiti e voci incerte hanno una conversazione anonima per satellite, mai
  condivisa; lo scritto dallo schermo personale continua la conversazione della persona solo
  se c'è (cominciata a voce). La finestra di ascolto è del satellite.
- **Tutti i satelliti ascoltano insieme** (`satelliti_insieme: true`): ogni satellite ha una
  **corsia** (un thread con il ciclo di main.py, il suo ascolto, la sua voce, il suo
  `SpeakerContext`, il suo Brain). `prendi`/`lascia` non tolgono più il posto a nessuno.
- **Risposte in parallelo fino a `conversazioni_parallele`**, oltre una frase già pronta
  («Sto rispondendo anche a un'altra persona: dammi un attimo.») e la coda in ordine
  d'arrivo; una risposta cominciata non si interrompe. **Predefinito 1**: sulla DGX Ollama
  risponde comunque a una richiesta alla volta [M] (§2), e con 1 chi aspetta sente la frase
  della coda dopo 0,5–1,1 s invece del silenzio, con gli stessi tempi di risposta.
- **Doppioni**: la stessa frase della stessa voce sentita da due satelliti nella stessa stanza
  ha una risposta sola (`conversazione_doppione_s` 2 s, regola `doppione_altro_satellite`) [M].
- Annunci (timer, documenti, lavori) e frasi scritte vanno alla corsia del satellite giusto
  (`Smistatore`), non più con il «prestito» dell'attivo.

## 1. Come è fatto

| Pezzo | Dove |
|---|---|
| Corsie | `calliope/corsie.py` → `Corsia` (`turno`, `fine_turno`, `annuncio_per`, `entra_llm`/`esci_llm`), `corrente()`/`entra`/`in_corsia`/`per_corsia` (la corsia del thread) |
| Conversazioni per persona | `RegistroConversazioni` (`scegli`, `occupa`/`libera`: una corsia alla volta per conversazione, `sostituita`, `doppione`, `pulisci`: chiude le ferme da `storia_inattiva_s`, `riprendi`: tutte quelle salvate, anche la «casa» di prima che va alla sua persona) |
| Risposte insieme | `Varco` (limite, coda in ordine d'arrivo, frase d'attesa una volta) |
| Pezzi condivisi | `condivisa` (arbitro degli agenti e compressione: la voce è libera quando nessuna corsia la tiene), `STTCondiviso` (una trascrizione alla volta, confidenza per corsia), `Smistatore`/`VistaCoda` (annunci e scritti per corsia) |
| Il ciclo | `main.giro` resta com'era: `corsie.clona` lo copia per ogni corsia con celle nuove per gli oggetti e lo stato della corsia (listener, speaker, speaker_ctx, brain, tool_ctx, rec, awake_until…). Così il ciclo, lungo e modificato da più rami, non si riscrive. `main.esegui_corsie` crea la corsia quando un satellite si collega la prima volta (resta ad aspettarlo se cade) |
| Server dei satelliti | `insieme`: eventi nella coda di ogni `Collegamento`, `attivo` = il satellite della corsia del thread (stanza per gli schermi, origine, PC), `prendi` dice solo «attivo», `lascia` e i prestiti non fanno niente; `AscoltoRemoto`/`UscitaRemota` con `sat_id` |
| Brain | `turn_number` e `uso_precedente` della conversazione; `conversazioni` (il registro) e `satellite`; `end_conversation` avvisa il registro e continua il numero dei turni; `chiudi_conversazione`; la ripresa «l'ultima volta…» segue la persona ovunque; `_tool_re` si rilegge alla versione nuova del registro dei tool |
| Altro | `Speaker.gemello` (voci di Piper e frasi pronte condivise; fonemi di espeak-ng sotto un lucchetto, la voce onnxruntime in parallelo), `Compressore` con una compressione per conversazione, `Instradamento` con lo stato del turno per thread, registro dei turni con `satellite` e `conversazione` (`tipo`, `come`: persona, ripresa, continua, schermo, anonima; `n`) |
| Configurazione | `conversazioni_parallele` 1, `conversazione_doppione_s` 2.0 (sezione conversazioni), `satelliti_insieme` true (sezione server_satelliti) |

Con l'audio di questo computer la corsia è una sola (il thread principale) e il registro c'è
lo stesso: quando parla un'altra persona la conversazione di prima **resta da parte** invece
di chiudersi, e chi torna la ritrova (prima del 06/10 si chiudeva). Si chiude con «esci»,
«ricominciamo» o dopo `storia_inattiva_s` senza turni.

## 2. Misure

### 2.1 A secco (portatile)

`prova_corsie_satelliti.py`: Calliope vera, due satelliti finti a livello di protocollo
(`prove/satellite_finto.py`), Whisper e Ollama finti, CAM++ vero sulle voci di Piper (Dario
0,70–0,88, Bianca 0,79–0,86, l'ospite 0,29–0,33 contro Dario) [M]:

- Dario dallo studio, poi dalla cucina: la storia lo segue; Bianca in cucina e l'ospite nello
  studio no (registro: `ripresa`, `persona`, `anonima`);
- Dario e Bianca insieme con limite 2: le due richieste al modello partono a 0,06 s l'una
  dall'altra; con limite 1 la seconda parte 2,05 s dopo (alla fine della prima), e in cucina
  arriva prima la frase della coda (già sintetizzata) e poi la risposta, mentre la storia
  nello studio non si interrompe;
- la stessa frase ai due satelliti: una risposta sola, regola nel registro.

`prova_corsie.py` (nel processo, ~1 s): scelta della conversazione nei 10 casi delle regole,
Brain con il registro, «sì» breve altrove, una corsia alla volta per conversazione, doppioni
(stesso satellite, fuori finestra, frasi diverse: no), varco, voce occupata contata per
corsia, smistatore, clona, pulizia e ripresa, compressione per conversazione, server.

### 2.2 DGX: 1, 2, 3 persone insieme (`misura_corsie.py`)

Una seconda Calliope (questo codice) in una cartella temporanea con `llm_profilo`
gemma4-26b-ollama, `llm_num_ctx` 28 672 come la produzione (Ollama non ha ricaricato: stessa
finestra prima e dopo in `/api/ps`), whisper.cpp della DGX, senza casa, schermi, agenti,
biblioteca (prefisso ~3,4 k token contro ~10,5 k della produzione), tre satelliti finti con
tre voci di Piper riconosciute da CAM++ (18/18 «voce»). A ogni giro 1, 2 o 3 persone dicono
insieme una domanda diversa (consigli, curiosità: risposte di 2 frasi lunghe). Tempo dalla fine
della frase alla prima frase di Calliope **sul satellite** (Whisper, modello e Piper compresi),
3 giri:

| Persone insieme | `conversazioni_parallele` 3 (nessuna attesa) | `conversazioni_parallele` 1 | Frase della coda (limite 1) |
|---|---|---|---|
| 1 | 2,09 s (max 2,36) | 1,55 s (max 2,37) | — |
| 2 | 2,70 s (max 4,03) | 3,02 s (max 4,18) | 0,49 s |
| 3 | 5,05 s (max 5,85) | 4,17 s (max 5,68) | 0,77 s (max 1,10) |

Dentro Calliope (dallo STT, `prima_frase_s`) con limite 3, i tre insieme: 0,83 / 2,50 /
3,72 s, 1,49 / 2,85 / 4,10 s, 1,06 / 2,81 / 4,15 s; due insieme 1,05 / 2,43, 0,88 / 1,85,
1,08 / 2,57 s; da sola 0,60–1,13 s [M]. **Ollama 0.35 sulla DGX risponde a una richiesta alla
volta**: la seconda prima frase arriva quando la prima risposta è finita, la terza dopo le
altre due [M] (il servizio di Ollama non ha `OLLAMA_NUM_PARALLEL`; non l'ho toccato). Con il
limite i tempi restano gli stessi (rumore di ±0,5 s tra le due serie) [M], ma chi aspetta
sente la frase della coda dopo 0,5–1,1 s invece di 2–4 s di silenzio. **Scelto 1.** Con vLLM
per la voce (`gemma4-26b-vllm`, batch continuo) o con `OLLAMA_NUM_PARALLEL` le richieste
andrebbero davvero insieme, e allora 2 avrebbe senso [D]: da rimisurare con lo stesso script
(`--parallele 3`) prima di alzarlo.

Whisper sulla DGX: `stt_s` 0,36 s di mediana, 0,93 al p90 con 3 frasi insieme (le
trascrizioni sono in fila) [M]. Piper (serena-high) sintetizza in parallelo nelle corsie (solo i
fonemi di espeak-ng sono in fila).

## 3. Limiti e cose da fare

- **Lo stato della voce sugli schermi** («ascolta», «pensa», «parla») è ancora uno solo per
  la casa: con due satelliti attivi la fascia salta tra i due stati.
- **Doppioni**: testo quasi uguale entro 2 s **e** la stessa voce (impronte CAM++ della frase
  ≥ 0,6 tra loro). La prima versione guardava solo il testo, e nella prova a secco l'ospite che
  nello studio chiedeva la stessa cosa di Bianca in cucina, un secondo dopo, restava senza
  risposta: ora due persone diverse che dicono la stessa frase da due stanze hanno due
  risposte. La soglia 0,6 sui due microfoni veri della stessa stanza è da misurare.
- Una persona che parla a due satelliti nello stesso momento con frasi diverse: la seconda
  corsia aspetta la fine del turno della prima (`occupa`, al più 60 s), poi risponde.
- Fuori per ora (roadmap): conversazione di stanza (più persone note allo stesso satellite) e
  interfono.
- Il prefisso della misura è più corto di quello vero: con 10,5 k token la prima risposta da
  sola è più lenta solo a cache persa (con più conversazioni insieme Ollama tiene più
  posti nella cache del prefisso, report del 05/10, §2.3). Da rifare con la configurazione
  completa quando la voce passa a vLLM.
- Il ciclo copiato con `corsie.clona` vuole che lo stato della corsia sia nelle variabili
  elencate in `main.esegui_corsie`: una variabile nuova di `giro` che deve essere per
  satellite va aggiunta lì (le altre restano condivise).
