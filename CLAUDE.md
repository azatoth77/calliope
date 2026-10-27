# Calliope — assistente vocale locale

> **Prima sessione?** Le scelte di fondo sono nate in una sessione di progettazione del
> 21/09/2026 (trascrizione privata, fuori dal repository): qui sotto ce n'è il riassunto, e il
> perché di ogni scelta è nei documenti d'area (`docs/aree/`) e nelle ricerche (`docs/ricerche/`).

## Cos'è

Calliope è un'assistente vocale che gira **interamente in locale**: nessun servizio
cloud, tutto offline dopo il download dei modelli. L'utente parla, Calliope trascrive,
ragiona con un LLM locale e risponde a voce.

Il nome viene dalla musa dell'eloquenza ("colei che ha una bella voce"). È anche la
**wake word**: Calliope risponde solo quando sente il suo nome. Ha una **voce
femminile** e parla di sé al femminile.

## Lingua

- Comunica con l'utente **in italiano**.
- Commenti nel codice, log e testi rivolti all'utente: in italiano.
- Nomi di variabili, funzioni e classi: in inglese (come nel codice esistente).

## Hardware

| | Sviluppo (oggi) | Obiettivo (futuro) |
|---|---|---|
| Macchina | Dell Alienware Aurora 16X (portatile) | PC con NVIDIA RTX Spark |
| OS | Windows 11 x86-64 | Windows 11 **su ARM** |
| GPU | RTX 5070 Laptop, **8 GB VRAM** (Blackwell) | GPU Blackwell integrata |
| Memoria | 32 GB RAM | fino a 128 GB unificati CPU/GPU (LPDDR5X) |
| Disco | 1 TB (~524 GB liberi) | — |

Implicazioni:
- **Oggi**: il budget di VRAM è stretto. Oltre all'LLM (~3–5 GB) deve starci Whisper.
- **RTX Spark**: tanta memoria, ma la generazione è limitata dalla banda di memoria.
  Per la latenza vocale conviene usare modelli **MoE**. L'architettura è ARM: ogni
  dipendenza con codice nativo va verificata.

## Architettura

```
microfono → VAD → STT → [wake word] → LLM (streaming) → divisione in frasi → TTS → altoparlanti
```

Il codice è il package `calliope/` (dal 26/09/2026; prima tutto stava in `calliope.py`). Una riga
per stadio, solo i moduli principali: librerie, classi e dettagli sono nei documenti d'area
(`docs/aree/`), con le misure e le decisioni. Diagramma completo:
[`docs/ricerche/2026-10-06-architettura.svg`](docs/ricerche/2026-10-06-architettura.svg).

| Stadio | Dove | Area |
|---|---|---|
| Ciclo principale, robustezza | `main.py` (`Avvio`, `Corsie`), `ciclo.py` (`Ciclo`, `Servizi`: dal 06/10, P8), `persistenza.py`, `turnlog.py` | [voce-e-regole](docs/aree/voce-e-regole.md) |
| Cattura, VAD, wake word acustica, barge-in; pause e fine del turno (solo misura, dal 07/10); frase al tetto di 120 s unita al seguito (dal 10/10); fine del turno System 1 con Smart Turn sull'audio, ombra e attiva (dal 14/10, spenta di serie) | `audio.py` (`Listener`), `vad.py`, `wakeword.py` (`WakeWordDetector`), `pause.py`, `system1/` (`fine_turno.py`) | [stt-tts](docs/aree/stt-tts.md) |
| Chi parla (CAM++ in ONNX); più voci vicino a un satellite e «rivolta a Calliope» (dal 09/10); conversazione di stanza decisa (0029, 13/10), passo 0 fatto: in compagnia niente azioni senza il nome, conversazione anonima condivisa, rilevatore solo sulle frasi rivolte; conoscenti (0030, 14/10, spenti di serie): voci di fuori casa col nome dedotto, salvate col sì di chi amministra, livello ospite, conservati come gli adulti (14/10 sera); impronte della voce per satellite per tutti, imparate dalle frasi sicure (15/10, spente di serie, da misurare); la compagnia conta anche le voci sentite dalla stanza, in ombra di serie (18/10, #147) | `speaker_id.py`, `arruola.py`, `compagnia.py`, `rivolta.py`, `stanza/conoscenti.py`, `impronte_satellite.py` | [stt-tts](docs/aree/stt-tts.md) |
| Speech-to-Text (faster-whisper o whisper.cpp sulla DGX, ripiego su CPU); nomi incerti negli argomenti dei tool, misura e «forse intendeva» dopo un esito vuoto (dal 08/10); sigle storpiate riscritte nella trascrizione («PG-16» → «PEGI 16», dal 15/10) | `stt.py`, `stt_correzione.py`, `argomenti_incerti.py`, `sigle.py` | [stt-tts](docs/aree/stt-tts.md) |
| Text-to-Speech (Piper, sulla GPU secondo la macchina), pronuncia degli inglesismi, taratura della voce (dal 07/10) | `tts.py` (`Speaker`), `pronuncia.py`, `taratura_voce.py` | [stt-tts](docs/aree/stt-tts.md) |
| Regole sul testo: wake word testuale, uscita, stop, cortesia; forme chiuse storpiate da Whisper (dal 10/10); «Grazie.» sul rumore senza voce, `cortesia_senza_voce` in ombra (dal 16/10, #97) | `wakeword.py`, `cortesia.py`, `storpiature.py` | [voce-e-regole](docs/aree/voce-e-regole.md) |
| LLM e tool calling (Ollama nativo o API OpenAI), reti e spinte; errori dei tool in parole e giri di correzione (dal 09/10); la risposta che gira in tondo fermata nello streaming (dal 14/10 notte); preselezione dei tool System 1, «nucleo» o «tutti» (dal 15/10; misurata sulla DGX senza vantaggio, dal 16/10 l'ombra è tolta e resta il decisore come misura, #25); la domanda insistita non ripete la risposta (dal 15/10); scatti delle reti per rete e per profilo, `calliope stato --reti` (dal 15/10, E11); frase dopo il tool System 1, la frase pronta del tool senza la seconda passata per gli esiti chiusi, ombra e attivo (dal 15/10, spenta di serie) | `brain.py` (`Brain`), `ciclo_ripetuto.py`, `ripetizione.py`, `reti_scatti.py`, `tools/` (`spec`, `registry`, `builtin`, `dialogo`), `system1/preselezione.py`, `system1/dopo_tool.py` | [voce-e-regole](docs/aree/voce-e-regole.md) |
| Stato del dialogo come macchina a stati, passo 1 in ombra (dal 10/10): proposta aperta, corsia veloce, `proposta_rispondi`, confronto nel registro | `stato_dialogo.py`, `risposte.py`, `tools/proposta.py` | [voce-e-regole](docs/aree/voce-e-regole.md) |
| Registro degli eventi in ombra (decisione 0027, passi 0–1 dal 10/10): un registro per persona, proiezione del contesto confrontata con la storia, «dimentica» vera; uscita unica verso la voce con atto e autore (passo 2, dal 10/10); con `eventi: attivo` (passo 3, acceso a mano) il contesto dalla proiezione e gli argomenti al posto della conversazione nuova | `eventi/` (`tipi`, `registro`, `proiezioni`, `misura`, `ombra`, `uscita`), `tools/argomento.py` | [voce-e-regole](docs/aree/voce-e-regole.md), [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Conversazione di stanza, passo 1 in ombra (dal 13/10 sera, di serie spenta): il satellite e il telefono mandano anche il parlato della stanza (protocollo 3), trascritto a bassa precedenza, registro in memoria con chi parla e le presenze, «abbiamo ospiti», niente al modello; passo 2 (14/10, `stanza_contesto`, di serie spento): le righe della stanza nei dati del turno in busta, copertura all'interpellazione, giudizio «rivolta» con la stanza; passo 4 (14/10, `stanza_cerca`, di serie spento): il tool `stanza_cerca` (dove si era presenti; le parole del minore solo ai tutori) e la frase d'attesa; passo 5 (14/10, `stanza_durante_voce`, di serie spento): la stanza si ascolta anche mentre Calliope parla, con il filtro dell'eco sul testo; taglio morbido dei segmenti al tetto; tenuta su disco (14/10, `stanza_tenuta`, di serie spenta): testo della stanza 60 giorni per la famiglia, minori compresi, cercato con gli stessi permessi; passo 6 (14/10, `stanza_guardia`, di serie spento): il guardiano a posteriori sulle chiacchiere con un minore, in ombra solo misure senza parole (`calliope stato --guardia`), «attiva» solo l'avviso al tutore sullo schermo; dal 14/10 sera ripresa dal disco dopo un riavvio e gioco aperto dichiarato; passo 3 (14/10 sera, `stanza_lenta`, di serie spento): corsia lenta a DGX libera (ritrascrizione, chi parla sullo scambio, TV, allucinazioni, riassunto), righe v2 in sola aggiunta, e l'audio del banco su disco a tempo (`stanza_audio_banco_giorni`, eccezione della 0029) | `stanza/` (`ascolto`, `registro`, `coda`, `misure`, `contesto`, `cerca`, `eco`, `tenuta`, `guardia`, `lenta`, `banco`), `satellite/stanza.py`, `tools/stanza.py` | [stt-tts](docs/aree/stt-tts.md), [contesto-conversazione](docs/aree/contesto-conversazione.md), [minori](docs/aree/minori.md) |
| Configurazione (dataclass + YAML), profili del modello | `config.py` (`Config`, `PROFILI_LLM`, `TONI`) | [voce-e-regole](docs/aree/voce-e-regole.md) |
| Latenza come metrica | `latenza.py` (`calliope stato --turni`, avviso oltre 1,2 s, `scalda_ripresa`) | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Conservazione per le misure (dal 12/10: turni, eventi, archivio e voce 60 giorni, voce col consenso, `calliope conserva --svuota`; dal 16/10, decisione 0031, i minori come gli adulti, la loro voce col sì dei tutori, ospiti mai; dal 18/10, decisione 0032, `conserva_valutazione_fino`: fino a una data testo e audio di tutti, ospiti compresi, spento di serie) e scelta dei tool come metrica | `conserva.py`, `tools/conserva.py`, `scelta_tool.py` | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Personalità: toni, modalità startrek, suoni; frasi pronte con varianti per tono e forma breve, misura delle ripetizioni (in ombra, dal 12/10) | `config.py`, `personalita.py`, `modalita.py` (a voce, senza riavvio), `suoni.py`, `frasi.py` | [personalita](docs/aree/personalita.md) |
| Memoria, agenda, liste, tempi | `memory.py`, `agenda.py`, `tempi.py`, `liste.py` | [memoria-agenda-liste](docs/aree/memoria-agenda-liste.md) |
| Finestra di contesto, conversazione, compressione, archivio (su disco per 60 giorni delle persone di casa, dal 12/10; minori compresi dal 16/10, decisione 0031; ospiti in memoria); ricordi, avvisi e riassunto della stanza nella storia solo quando cambiano, dati del turno sotto un tetto (cache del prefisso con Gemma 4, dal 16/10, #95) | `contesto.py`, `conversazione.py`, `compressione.py`, `conversazioni.py`, `dati_turno.py` | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Una conversazione per persona, satelliti insieme | `corsie.py` | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Politica dei tool, provenienza, quarantena, ciò che dice; sicurezza per valore (attrito, memoria dell'intento, matrice in ombra: dall'08/10); il «sì» breve per le azioni importanti misurato in ombra (dal 15/10) | `politica.py`, `provenienza.py`, `valore.py`, `attrito.py`, `quarantena.py`, `riferire.py`, `si_breve.py` | [sicurezza-politica](docs/aree/sicurezza-politica.md) |
| Conferme e frase di sfida, sicurezza | `conferme.py`, `sicurezza.py`, `guardrail.py` | [sicurezza-politica](docs/aree/sicurezza-politica.md) |
| Minori e guardiano, segnali di pericolo poco chiari a due cancelli (dal 09/10); esercizi generati da Calliope (matematica e italiano, dal 08/10; logica, fisica e chimica con le unità di misura dette e lette, dal 12/10; indice del programma ministeriale, Indicazioni 2025 e 2012, dal 12/10 sera: limite stretto per classe e periodo, «a che punto siete», interrogazioni); l'ospite con la voce vicina a quella di un minore che ha parlato da poco riceve nei dati del turno la nota e il modo di parlare della sua fascia, mentre livello e permessi restano da ospite (`minori_ospite_vicino`, acceso di serie, dal 16/10, #102) | `minori.py`, `guardiano.py`, `cancelli.py`, `esercizi/` (`programma/`), `tools/esercizi.py`, `unita.py` | [minori](docs/aree/minori.md) |
| Biblioteca offline (ZIM in puro Python, FTS5) | `biblioteca.py`, `zim.py`, `biblioteca_indice.py` | [biblioteca](docs/aree/biblioteca.md) |
| Ricerca su internet (SearXNG sulla DGX, tenuto aggiornato: controllo quotidiano e «Aggiorna» nel cruscotto, dal 09/10); notizie dai feed RSS scaricati in casa, tool `notizie`, i fatti detti restano nel contesto (dal 13/10); pertinenza dei risultati verso la conversazione, in ombra di serie (dal 16/10) | `web/` (`motore.py`), `notizie/`, `tools/notizie.py`, `pertinenza.py` | [biblioteca](docs/aree/biblioteca.md) |
| PC a voce (locale o del satellite) | `pc/` (`PCExecutor`, `windows.py`, `remoto.py`), `tools/pc.py` | [pc](docs/aree/pc.md) |
| Documenti Word, Excel, PDF | `documenti/`, `tools/documenti.py` | [documenti-ufficio](docs/aree/documenti-ufficio.md) |
| Ufficio: modelli, rubrica, fatture, DDT | `ufficio/`, `tools/ufficio.py` | [documenti-ufficio](docs/aree/documenti-ufficio.md) |
| Archivio dei documenti di casa (grafo) | `archivio/`, `tools/archivio.py` | [documenti-ufficio](docs/aree/documenti-ufficio.md) |
| Casa via Home Assistant | `casa/`, `tools/casa.py` | [casa](docs/aree/casa.md) |
| Registro delle capacità, macchina; piano dei modelli in sola lettura (`calliope stato --piano`, dal 08/10); conto della memoria e classi delle attività in sola lettura (`calliope stato --memoria`, passo 1 dell'arbitro della memoria, dal 14/10); arbitro in ombra con la «voce ferma» unica `quiete()` confrontata, nessun carico vero (`arbitro_memoria: ombra`, spento di serie, `calliope stato --memoria --storia`: passo 2, dal 15/10) | `capacita.py`, `stato.py`, `macchina.py`, `modelli.py`, `piano.py`, `arbitro_memoria.py`, `arbitro_ombra.py`, `tools/stato.py` | [capacita-installazioni](docs/aree/capacita-installazioni.md) |
| Installazioni dal catalogo | `installa/` | [capacita-installazioni](docs/aree/capacita-installazioni.md) |
| Schermi (schede, SSE, abbinamento), scrivere invece di parlare, cruscotto di chi amministra (sola lettura, dal 06/10), testi dell'agente in Markdown con «Scarica» (dal 07/10), cronologia delle schede per persona su disco e scheda «Conversazione» (dal 08/10) | `schermi/` (`hub.py`, `server.py`, `moduli.py`, `conversazione.py`, `cruscotto.py`, `scarica.py`, `cronologia.py`), `documenti/markdown.py` | [schermi-telefono](docs/aree/schermi-telefono.md) |
| Telefono (satellite nel browser, PWA; schede a schermo intero dal 06/10; a sezioni con la barra, Io al posto del menu e la modalità «In auto» a mano, dal 27/10) | `schermi/telefono.py`, `schermi/pagina/telefono/` | [schermi-telefono](docs/aree/schermi-telefono.md) |
| Rispondi dove ti ho chiesto | `rispondi.py` | [schermi-telefono](docs/aree/schermi-telefono.md) |
| Foto e allegati in ingresso; cassetto dei file per persona (7 giorni, dal 08/10); il dispositivo da cui si parla nei dati del turno, spinta di webcam e schermo solo col PC per chi parla, niente nomi ai volti (dal 16/10, #100) | `immagini.py`, `allegati.py`, `cassetto.py`, `pc/cattura.py`, `dispositivo.py` | [immagini-allegati](docs/aree/immagini-allegati.md) |
| Satelliti (WebSocket, TLS, installazione) | `satellite/`, `tls_sicuro.py` | [satelliti](docs/aree/satelliti.md) |
| Agenti in secondo piano (vLLM sulla DGX, sandbox Docker, arbitro), analisi della richiesta prima di partire (dal 06/10), modalità sviluppo a fasi con il collaudo prima dell'approvazione e la sua vista sugli schermi (dal 08/10), ricollaudo alla consegna e sonde verso i soli host noti (dal 08/10 notte), revisione onesta requisito per requisito e tappe per le richieste ricche (dal 11/10), voce onesta: esito vero del collaudo e dell'agente detto dal codice, meno parole e meno conferme (dal 12/10), la specifica viva: una modifica cambia i requisiti e a voce si dice solo il cambiamento (dal 12/10), comandi del flusso e ripresa: la modifica ferma il lavoro solo al «sì», «rifallo» dai file del giro, il programma chiuso si riapre (dal 12/10), la correzione che parte da un test rosso e i test del disegno dei giochi (dal 12/10 sera), l'analisi prima del codice con gli esempi di accettazione in sola lettura e «da guardare tu» (dal 13/10); harness più solido (ricerca del 19/10, epic #86): porte oneste della consegna, strumenti che dicono lo stato già visto e l'uscita troncata, partenza dei giochi già verde, banco del revisore a contesto pulito (dal 19–20/10) | `agenti/` (`richiesta.py`, `riproduzione.py`, `accettazione.py`), `tools/agenti.py`, `sviluppo.py`, `tools/sviluppo.py`, `sonde.py`, `requisiti.py` | [agenti-estensioni](docs/aree/agenti-estensioni.md) |
| Estensioni permanenti e guardrail | `estensioni/`, `tools/estensioni.py` | [agenti-estensioni](docs/aree/agenti-estensioni.md) |
| Giochi sugli schermi; modalità gioco a tutta la finestra con pallino della voce e variante «collaudo» (dal 11/10); comandi a voce dichiarati dal gioco, senza il modello e senza il nome mentre aspetta una mossa (dal 11/10 sera); macchina a stati di Calliope: fasi, turni, punti ed esito del motore, l'agente scrive solo la logica, prova di fumo per fasi ed esempi di accettazione (dal 13/10); palco fisso 1280×720 e 720×1280 con i sei modelli di pagina, la misura «fuori dal palco» nella prova di fumo e sullo schermo, unico formato (giochi vecchi tolti, dal 14/10); istantanea validata dal server, «a chi tocca?» senza il modello, giudice di fase, «gioco anch'io» e nomi scritti, ripresa dopo «Riapri», partite condivise con un motore solo (dal 14/10 sera); chi è quale giocatore (schermo e voce, «Tocca ad Ada.») e «Gira il telefono» per una tela (dal 15/10) | estensioni con scheda, `gioco_voce.py`, `gioco_stato.py`, `gioco_giudice.py`, `estensioni/macchina.py`, `estensioni/motore_gioco.js`, `agenti/fumo_js.mjs`, `schermi/pagina/schermo.js` | [giochi](docs/aree/giochi.md) |
| Installazione e aggiornamento su Linux | `pyproject.toml`, `uv.lock`, `setup/linux/` (`gestore.py`) | [setup-dgx](docs/aree/setup-dgx.md) |
| Prova end-to-end sulla DGX (istanza di prova, satelliti finti, voce vera) | `prove/e2e/` (`python -m prove.e2e.lancia`, `calliope prova-e2e`) | [setup-dgx](docs/aree/setup-dgx.md), [manuale](prove/manuali/e2e-dgx.md) |

Tool e livelli di permesso (ospite / familiare / amministra) sono descritti in
[`docs/architettura-tool.md`](docs/architettura-tool.md).
Il perché delle scelte, per chi arriva da GitHub: [`docs/architettura.md`](docs/architettura.md), decisioni in [`docs/decisioni/`](docs/decisioni/) (una nuova decisione di fondo vi aggiunge un file), metodo in [`docs/analisi.md`](docs/analisi.md).

## Principi di progetto (da rispettare)

1. **LLM dietro un'API standard e intercambiabile.** Passare allo Spark deve voler dire
   cambiare solo il nome del modello o l'URL. Dal 24/09/2026 il backend predefinito è
   l'API nativa di Ollama (`llm_backend = "ollama"`): è l'unica che rispetta `num_ctx`.
   Il backend compatibile OpenAI (`"openai"`) resta come ripiego e va tenuto funzionante.
   Dal 03/10 il modello della voce si sceglie con **una riga**, `llm_profilo` (backend,
   indirizzo, modello, thinking e reti insieme); si torna indietro cambiando quella riga.
2. **Moduli sostituibili.** STT, TTS, VAD e wake word sono dietro interfacce semplici
   (`transcribe(audio) → str`, `say(text)`…). Se una libreria non gira su ARM si
   sostituisce solo quel modulo.
3. **Configurazione fuori dal codice.** Dal 26/09/2026 sta in `calliope.yaml`, a
   sezioni. I valori predefiniti, con i commenti che li motivano, restano nella dataclass
   `Config` di `calliope/config.py`. Il file si rigenera dai commenti con
   `python -m calliope.config --esempio > calliope.yaml`, e non va scritto a mano quando
   si aggiunge un campo. I valori di **questa installazione** (indirizzo di casa,
   cartelle, dispositivi) vanno in `calliope.locale.yaml` accanto, fuori da git (dal
   01/10): così `calliope.yaml` resta uguale al file d'esempio e `prova_config` passa. Le
   prove non leggono il file locale (`CALLIOPE_CONFIG_LOCALE` puntato altrove dal runner).
   Priorità: predefinito < `calliope.yaml` < `calliope.locale.yaml` < variabili d'ambiente
   `CALLIOPE_*`; `CALLIOPE_CONFIG` sceglie un altro file. Chiavi sconosciute e tipi
   sbagliati vengono segnalati, e non fermano l'avvio. Niente percorsi scritti nel codice.
4. **Dipendenze native minime**, in vista di Windows su ARM.
5. **Output pensato per la voce.** Niente markdown, elenchi, emoji o URL nelle
   risposte; risposte brevi (1–3 frasi di default).
6. **Latenza prima di tutto.** Streaming ovunque: ogni frase completa va subito al TTS,
   e si sintetizza la frase successiva mentre si riproduce quella corrente. Il
   programma stampa i tempi di STT e della prima frase: usali per misurare le modifiche.
7. **Fallback su CPU** per Whisper, da non rimuovere.
8. **Half-duplex, con un'eccezione per il nome.** Mentre Calliope parla non si trascrive
   nulla, perché su un portatile senza cuffie sentirebbe sé stessa. Resta accesa solo la
   wake word acustica: «Calliope, basta» la interrompe (barge-in di livello A, dal
   26/09), ignorando i momenti in cui è lei a dire il proprio nome. Livello B leggero:
   se durante il saluto iniziale il VAD non sente la sua voce (microfono interno del
   portatile, che in MME ha la cancellazione dell'eco di Windows, oppure cuffie), anche
   qualunque frase di una persona registrata la interrompe. Il livello B completo (AEC
   software DTLN per microfoni senza cancellazione) è rimandato: i satelliti XMOS lo
   fanno in hardware.
9. **Niente cloud.** Nessuna dipendenza da servizi remoti in esecuzione.
10. **Regole deterministiche sul testo** (dal 01/10, criterio e misure in
    [`docs/ricerche/2026-10-01-regole-deterministiche.md`](docs/ricerche/2026-10-01-regole-deterministiche.md)).
    Il significato di ciò che dice la persona lo decide il modello. Una regola sul testo è
    ammessa solo se è un vincolo di sicurezza o di permesso, una conversione o una
    correzione della forma di una scelta già fatta dal modello, riguarda ciò che il modello
    non vede (audio, trascrizione, storpiature del nome e di «esci»), oppure riconosce una
    forma chiusa e breve **per intero** (mai una parola dentro la frase), con un effetto
    reversibile. Tutto il resto è una spinta o un contesto del turno. Ogni regola ha i suoi
    casi contrari nelle prove (`prove/prova_testo.py`) e scrive il suo nome nel registro dei
    turni (campo `regole`).

## Setup

- **Windows** (portatile, Calliope completa o satellite; casa, biblioteca, schermi, agenti,
  telefono): [`docs/aree/setup-windows.md`](docs/aree/setup-windows.md). Avvio:
  `python -m calliope`; stato: `python -m calliope.stato`; configurazione rigenerata con
  `python -m calliope.config --esempio > calliope.yaml`, valori locali in `calliope.locale.yaml`.
- **DGX Linux** (target principale dal 02/10, servizio systemd utente, `calliope aggiorna` con
  ritorno automatico): [`docs/aree/setup-dgx.md`](docs/aree/setup-dgx.md).

## Stato attuale (18/10/2026)

Calliope gira sulla **DGX Spark** dal 02/10 come servizio (voce gemma4 su Ollama, profilo in
`llm_profilo`; Whisper con whisper.cpp; agente qwen3.6 su vLLM); portatile e telefono sono
satelliti. Cronologia e primi test in [`docs/aree/cronologia.md`](docs/aree/cronologia.md). Cosa è
acceso davvero sulla DGX, chiave per chiave: tabella «Interruttori sulla DGX» di
[setup-dgx](docs/aree/setup-dgx.md#interruttori-sulla-dgx) (dal 18/10, #84).

- **Voce**: wake word acustica, barge-in col nome, chi parla con CAM++, half-duplex, risposte in streaming ([stt-tts](docs/aree/stt-tts.md), [voce-e-regole](docs/aree/voce-e-regole.md)).
- **Tool**: 75 schemi uguali per ogni livello in un'installazione con tutti i servizi (contati sul registro il 14/10, ricontrollati il 18/10: nessun tool aggiunto o tolto dopo; un PC, schermi, agenti e modalità sviluppo, estensioni e giochi, ufficio, archivio, web e `notizie`, foto come messaggio; *[storico: «78» fino al 13/10]*); dipendono dall'installazione `meteo_leggi` (entità meteo in Home Assistant), `immagine_guarda` (`immagini_storia: descrizione`), `compiti_aiuto`, `esercizi`, `minore_gestisci` e `richiesta_tutore` (un minore in casa), `stanza_pausa` e `stanza_cerca` (stanza accesa), `conoscenti` e `conoscente_livello` (`stanza_conoscenti`); `argomento` al posto di `conversazione_nuova` con `eventi: attivo`; nomi nuovi dall'08/10, i vecchi validi nel registro; permessi decisi in `ToolRegistry.call` ([voce-e-regole](docs/aree/voce-e-regole.md), [`architettura-tool.md`](docs/architettura-tool.md)).
- **Capacità**: 19 nel registro (`capacita.DEFINIZIONI`, contate il 18/10), installazioni a voce dal catalogo ([capacita-installazioni](docs/aree/capacita-installazioni.md)).
- **Politica unica dei tool** con dati non fidati in busta, conferme e frase di sfida ([sicurezza-politica](docs/aree/sicurezza-politica.md)).
- **Contesto**: finestra dal setup, compressione, archivio delle conversazioni, una conversazione per persona ([contesto-conversazione](docs/aree/contesto-conversazione.md)).
- **Memoria, agenda, liste, calcoli e date** ([memoria-agenda-liste](docs/aree/memoria-agenda-liste.md)).
- **Casa** via Home Assistant, provata con l'HA vero dal 01/10 ([casa](docs/aree/casa.md)); **PC a voce**, anche remoto dal satellite ([pc](docs/aree/pc.md)).
- **Documenti, ufficio** (docxtpl e python-pptx dal 03/10, FatturaPA) e **archivio** dei documenti di casa ([documenti-ufficio](docs/aree/documenti-ufficio.md)).
- **Biblioteca offline** senza libzim, **ricerca web** con SearXNG e **notizie** dai feed RSS scaricati in casa (13/10) ([biblioteca](docs/aree/biblioteca.md)).
- **Schermi, telefono (PWA), scrivere invece di parlare** ([schermi-telefono](docs/aree/schermi-telefono.md)); **foto e allegati** ([immagini-allegati](docs/aree/immagini-allegati.md)).
- **Satelliti** con TLS, installazione con un comando e aggiornamenti ([satelliti](docs/aree/satelliti.md)).
- **Agenti** sulla DGX (sandbox Docker, arbitro e pausa di vLLM, programmi in diretta, C# e, dal 17/10, JavaScript acceso a mano) ed **estensioni** con guardrail ([agenti-estensioni](docs/aree/agenti-estensioni.md)); **giochi** con la macchina a stati di Calliope e il palco fisso (13–14/10) ([giochi](docs/aree/giochi.md)).
- **Minori** con guardiano, esercizi sul programma ministeriale, avvisi ai tutori con data, trascrizione e (se acceso) audio (14/10) ([minori](docs/aree/minori.md)); **personalità** e modalità startrek ([personalita](docs/aree/personalita.md)).
- **Conversazione di stanza** (decisione [0029](docs/decisioni/0029-conversazione-di-stanza.md), 13–14/10): passi 0–6 fatti (il 3, corsia lenta, il 14/10 sera), ognuno col suo interruttore e spento di serie (cosa è acceso sulla DGX: tabella «Interruttori sulla DGX» di [setup-dgx](docs/aree/setup-dgx.md#interruttori-sulla-dgx)); restano il filtro della TV (#34), i passi 7–8 e le misure di ciò che è acceso senza un criterio scritto (#37, #38) (*[storico: «restano la corsia lenta (passo 3)» fino al 14/10 sera]*) ([contesto-conversazione](docs/aree/contesto-conversazione.md), [stt-tts](docs/aree/stt-tts.md), [minori](docs/aree/minori.md)).
- **Conoscenti** (decisione [0030](docs/decisioni/0030-conoscenti.md), 14/10, `stanza_conoscenti` spento di serie; sulla DGX acceso senza criterio scritto, #38): voci di fuori casa col nome dedotto dalla conversazione, salvate solo col sì di chi amministra, livello ospite ([stt-tts](docs/aree/stt-tts.md)).
- Analisi del 06/10: P1–P11 e Q2–Q11 fatte, Q1 chiusa il 09/10, Q12–Q14 diventate E10, E11 ed E4 della coda del 12/10 ([`docs/ricerche/2026-10-06-analisi-complessiva.md`](docs/ricerche/2026-10-06-analisi-complessiva.md)); congelamento delle funzionalità nuove finito l'08/10; tappe in [`CHANGELOG.md`](CHANGELOG.md); coda del 12/10, con la prontezza di ogni voce, in [`docs/roadmap.md`](docs/roadmap.md) e scelte trasversali (dati degli adulti per 60 giorni, piano della memoria, taglia ridotta da 8 GB come vincolo, musica sì, allarme senza data) nella decisione [0028](docs/decisioni/0028-decisioni-roadmap-12-10.md).
- **Pubblicazione** (07/10): repository pubblico con licenza AGPL-3.0-or-later ([`LICENSE`](LICENSE), [`TERZE-PARTI.md`](TERZE-PARTI.md)); nel repository solo nomi, indirizzi e dati **di fantasia**, i documenti privati in `privato/` (ignorata da git), `prova_dati_privati` nell'hook: [`docs/pubblicazione.md`](docs/pubblicazione.md).
- La **visione** (server di casa con satelliti, famiglia, ospiti, musica, agenti) è in [`docs/visione.md`](docs/visione.md): leggerla prima di toccare l'architettura.

## Problemi aperti

Solo ciò che è ancora vero il 18/10; storia e misure nei documenti d'area.

- **Latenza**: accettata da Dario il 09/10 (prima frase mediana 1,42 s l'08/10 con molti tool, 1,28 s il 09/10, base senza tool 1,18 s; testo→voce 0,35 s, STT 0,18 s) *[storico: «si guarda solo l'avviso» fino al 15/10]*; con la stanza accesa la prima frase mediana è salita a 2,31 s (prova in auto del 14/10 sera, criterio in #41) e a 2,58 s il 15/10 sulla DGX, con la cache del prefisso persa in 62 turni su 93; la correzione (#95, 16/10) è da misurare sulla DGX. Storia e misure in [contesto-conversazione](docs/aree/contesto-conversazione.md)
- **Prove**: sotto un carico più forte (3 corsie, 16 processi, macchina condivisa) `prova_satellite` cade circa 1 giro su 2 su «si ricollega attraverso la «VPN»» (oltre i 15 s, #155; «TLS: 120 aperture» chiuso il 18/10, #146: il pacchetto nel processo del server teneva il GIL); le attese fisse sono tolte il 17/10 (#5), le corsie sotto carico si lanciano con `prove/manuali/carico.py`; `prova_stanza_cerca` cade fra mezzanotte e le 3, quando le righe della scena diventano «ieri» (difetto della prova, #151, in sviluppo). [`prove/LEGGIMI.md`](prove/LEGGIMI.md)
- **Corsia lenta della stanza** (14/10 sera): col whisper-server dei turni la ritrascrizione peggiorava (WER 4,8 % contro 3,0 % sulle 95 registrazioni conservate): con `stanza_lenta_ritrascrivi: auto` si fa solo con un Whisper suo; il secondo Whisper (large-v3 q5_0, `whisper-lento.sh`) è preparato, da misurare col banco `--conservati … --ritrascrivi` prima di accenderlo (#35). Dal 15/10 la **ritrascrizione a blocchi** (`stanza_lenta_blocchi`, spenta di serie, in ombra sulla DGX dal 15/10: i segmenti consecutivi della stessa persona uniti, senza prompt; una frase spezzata in tre tornava giusta), pausa lunga e pagina di revisione da scegliere sul banco con `prove/manuali/blocchi_stanza.py` (#33). [stt-tts](docs/aree/stt-tts.md)
- **Voci di famiglia al telefono**: in auto la voce di chi amministra vale come quella di un minore (canale, non voci simili); dal 07/10 margine, chi amministra solo familiare col minore vicino e «chi parla?» solo per un'azione, dal 09/10 è compagnia vera (più sfide nella zona grigia); resta da registrare di nuovo per canale e ritarare. [stt-tts](docs/aree/stt-tts.md)
- **Compagnia** (09/10): la falsa compagnia di una persona sola è misurata bassa ma il punto debole è il telefono, da osservare nell'uso; le voci sconosciute sentite solo dall'ascolto della stanza non fanno compagnia (sera del 17/10, quattro voci nuove e «in compagnia 0»: #147, in sviluppo); il giudizio «rivolta a Calliope?» (F2) è in ombra, da rileggere prima di accenderlo. **Parole incerte**: soglie di F0 da tarare sulla voce vera, F2–F3 da decidere. [stt-tts](docs/aree/stt-tts.md)
- **Stanza** (14/10): l'ascolto durante la voce è acceso sulla DGX senza criterio scritto, dopo la sola misura dell'eco sul portatile; il telefono in auto non è misurato (#37, [`prove/manuali/misura-eco-stanza.md`](prove/manuali/misura-eco-stanza.md)); l'audio del banco su disco ha l'eccezione della 0029 che scade il 05/11 (prorogata il 18/10, #32) *[storico: «scade il 21/10» fino al 18/10]*; il guardiano a posteriori in ombra da rileggere (`calliope stato --guardia`, meno di un acuto falso a settimana) prima di `attiva`; senza il filtro della TV un comando detto dalla TV resta una riga in busta («ESEGUITE con un bersaglio dal dato» deve restare 0). **Conoscenti**: accesi sulla DGX senza criterio scritto; un gruppo può mescolare due voci simili, conferme e rifiuti da misurare (#38). [contesto-conversazione](docs/aree/contesto-conversazione.md), [stt-tts](docs/aree/stt-tts.md), [minori](docs/aree/minori.md)
- **Cuffie Bluetooth** che restano collegate ma mute: spegnerle e riaccenderle. [stt-tts](docs/aree/stt-tts.md)
- **Attrito della politica**: il 07/10 15,8 domande ogni 100 turni (68 % falsi positivi); dal 09/10 sera la politica per valore è **accesa** (fase 4: ombra dell'08–09/10 con 0 esecuzioni da un bersaglio del dato, attrito simulato 0,0 e 1,6) e le estensioni che leggono soltanto sono letture; da guardare sulla DGX «ESEGUITE con un bersaglio dal dato» (deve restare 0) e l'attrito con la politica di prima in `calliope stato --turni`; si spegne con `politica_per_valore: false` nel locale. [sicurezza-politica](docs/aree/sicurezza-politica.md)
- **Voce unico fattore**: la frase di sfida ferma registrazioni e TV, non una voce clonata in tempo reale. Progetto del secondo fattore (telefono obbligatorio per chi amministra, chiave vocale), in roadmap: [`docs/ricerche/2026-10-06-secondo-fattore.md`](docs/ricerche/2026-10-06-secondo-fattore.md). [sicurezza-politica](docs/aree/sicurezza-politica.md)
- **Sandbox**: kernel condiviso, utente di Calliope nel gruppo `docker`; su Windows il codice dell'agente non si esegue. **Pausa di vLLM** in modalità sviluppo (endpoint senza chiave su 127.0.0.1; dopo un SIGKILL `calliope motore vllm agente riprendi`). [agenti-estensioni](docs/aree/agenti-estensioni.md)
- **Wake word**: feature ACAV100M (CC-BY-NC-SA), non distribuibile; il modello di «computer» c'è sul portatile e sulla DGX, non nel repository. [stt-tts](docs/aree/stt-tts.md), [personalita](docs/aree/personalita.md)
- **Modello** (#70, 17/10 col 26B: ricordi, pizza ed età giusti): `chi_garbato` 0/12 (cerca la forma storpiata in biblioteca; dal 17/10 vale anche una domanda di chiarimento, la ricerca no), `ruolo4` 2/12 e `chi_garbato2` 1/12 sbagliati; chi parla in stanza giusto sul banco ma da rileggere sul vero. [voce-e-regole](docs/aree/voce-e-regole.md)
- **Non provati sul vero**: sull'iPhone (usato dal 03/10, in auto dal 06/10) la correzione dell'audio, lo schermo acceso e lo scaricamento dalla PWA (#59), PC Windows pulito come satellite, installazioni con internet vero, misure su Windows ARM. [roadmap](docs/roadmap.md)
- **Biblioteca**: tabelle delle voci non lette; «perché piove?» trova titoli omonimi. [biblioteca](docs/aree/biblioteca.md)
- **Agente**: il codice fiscale (qwen3.6 non conosce il carattere di controllo); il giro vero di un gioco col palco fisso sulla DGX da fare (i giochi del formato di prima non si aprono più dal 14/10); una ricerca dell'agente lenta da guardare; il presence_penalty è misurato per estensioni e giochi (0,5, dall'11/10), resta da misurare per il codice (0, `prove/manuali/misura_presence_penalty.py`). [agenti-estensioni](docs/aree/agenti-estensioni.md), [giochi](docs/aree/giochi.md)
- **Estensioni, capacità concesse invece degli impossibili** (decisione [0033](docs/decisioni/0033-capacita-concesse-e-revocabili.md), 20/10, #193): deciso il principio (tutto chiedibile, controllo a ogni uso e revoca, irreversibili mai in anticipo), ma nel codice i 12 impossibili di `contratto.py` chiudono ancora il lavoro; il piano a passi (analisi in [`docs/ricerche/2026-10-20-capacita-concesse.md`](docs/ricerche/2026-10-20-capacita-concesse.md)) è approvato il 21/10, una issue per passo (#203–#217, il 6 in #53) *[storico: «da approvare» fino al 21/10]*. [agenti-estensioni](docs/aree/agenti-estensioni.md)

**Trappole note** (vere ancora oggi): usare sempre `127.0.0.1` e mai `localhost` su Windows
(~2 s persi in IPv6); non riaprire il flusso del microfono a ogni turno; `ollama ps`
sottostima la VRAM (misurare con `nvidia-smi`); cambiare `num_ctx` ricarica il modello;
non allungare il prompt di Whisper; mai `uvicorn[standard]` (niente wheel `win_arm64`);
FTS5 con `detail=full`; la costruzione dell'indice con più processi va lanciata da un main
protetto; primo download di Whisper su Windows con `WinError 1314` → riavviare.

## Come lavorare (per gli agenti)

- **Leggi questo file e il documento della tua area** in `docs/aree/` (link nella tabella
  dell'architettura). Per il contesto delle scelte, il rapporto in `docs/ricerche/`.
- **Aggiorna il documento della tua area** con misure, decisioni e casi veri (sono la memoria
  del progetto): una voce datata, nello stile di quelle che ci sono. In CLAUDE.md **al più
  una riga** (la tabella, lo stato o un problema aperto); i problemi risolti escono da qui.
- Un'affermazione superata non si cancella: si segna come storica, con la data.
- Chi accende, spegne o cambia una chiave del file locale sulla DGX aggiorna la tabella
  «Interruttori sulla DGX» di [setup-dgx](docs/aree/setup-dgx.md#interruttori-sulla-dgx) (valore e
  data), e i documenti rimandano lì invece di ripetere lo stato (dal 18/10, #84).
- Prove: una prova nuova va in `prove/__main__.py` e in [`prove/elenco.md`](prove/elenco.md)
  nella sua area (poi `python -m prove --leggimi`: l'elenco di `LEGGIMI.md` si genera, dal 16/10);
  i passi manuali in `prove/manuali/`. Comandi del runner: vedi la sezione
  «Runner» di [`prove/LEGGIMI.md`](prove/LEGGIMI.md).
- **Rami delle epic** (dal 22/10): ogni issue ha il suo ramo e la sua PR verso il ramo dell'epic
  (`epic-<N>-<nome>`, «Refs #N»), con le revisioni e le sole prove relative; l'epic va su main a
  tappe, con una PR che chiude le issue che contiene («Closes #N»), quando un gruppo è pronto o
  prima di installare sulla DGX; dopo ogni tappa main si unisce nei rami delle epic aperte.
- L'hook lancia `python -m prove --hook --staged` (livelli 1 e 2, ~15–60 s). **Prima
  dell'unione su main** (la PR di tappa) `python -m prove --completo` (~8 min, con `voices/`, `models/speaker/`,
  `wakeword/modelli/`, `biblioteca/` presenti) e, per la tua area, le prove col modello.
  Mai `--no-verify`. Una prova saltata esce con 77 e il riepilogo la conta a parte.
- Mai chiudere processi per nome o per pezzi di riga di comando: sullo stesso portatile
  girano altri agenti e Calliope. Solo i processi avviati da te.
- **Mai dati veri nel repository** (è pubblico): nelle prove e nei documenti nomi e indirizzi di fantasia;
  ciò che descrive la casa vera, l'ufficio o test con persone vere va in `privato/` (fuori da git).
  `prova_dati_privati` lo controlla a ogni commit ([`docs/pubblicazione.md`](docs/pubblicazione.md)).
- Repository git dal 26/09 (autore 2598296+azatoth77@users.noreply.github.com): un commit per ogni passo.

## Convenzioni di lavoro

- L'ecosistema (modelli Ollama, faster-whisper, Piper, openWakeWord) cambia in
  fretta: **verifica le versioni attuali** prima di cambiare modelli o librerie.
- I file dei modelli (`*.onnx`, `*.onnx.json`, cache di Whisper) **non vanno nel
  repository**: aggiungili a `.gitignore`.
- Ogni modifica alla pipeline deve preservare lo streaming frase per frase.
