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
| Cattura, VAD, wake word acustica, barge-in; pause e fine del turno (solo misura, dal 07/10) | `audio.py` (`Listener`), `vad.py`, `wakeword.py` (`WakeWordDetector`), `pause.py` | [stt-tts](docs/aree/stt-tts.md) |
| Chi parla (CAM++ in ONNX); più voci vicino a un satellite e «rivolta a Calliope» (dal 09/10) | `speaker_id.py`, `arruola.py`, `compagnia.py`, `rivolta.py` | [stt-tts](docs/aree/stt-tts.md) |
| Speech-to-Text (faster-whisper o whisper.cpp sulla DGX, ripiego su CPU); nomi incerti negli argomenti dei tool, misura e «forse intendeva» dopo un esito vuoto (dal 08/10) | `stt.py`, `stt_correzione.py`, `argomenti_incerti.py` | [stt-tts](docs/aree/stt-tts.md) |
| Text-to-Speech (Piper), pronuncia degli inglesismi | `tts.py` (`Speaker`), `pronuncia.py` | [stt-tts](docs/aree/stt-tts.md) |
| Regole sul testo: wake word testuale, uscita, stop, cortesia | `wakeword.py`, `cortesia.py` | [voce-e-regole](docs/aree/voce-e-regole.md) |
| LLM e tool calling (Ollama nativo o API OpenAI), reti e spinte; errori dei tool in parole e giri di correzione (dal 09/10) | `brain.py` (`Brain`), `tools/` (`spec`, `registry`, `builtin`, `dialogo`) | [voce-e-regole](docs/aree/voce-e-regole.md) |
| Configurazione (dataclass + YAML), profili del modello | `config.py` (`Config`, `PROFILI_LLM`, `TONI`) | [voce-e-regole](docs/aree/voce-e-regole.md) |
| Latenza come metrica | `latenza.py` (`calliope stato --turni`, avviso oltre 1,2 s, `scalda_ripresa`) | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Personalità: toni, modalità startrek, suoni | `config.py`, `personalita.py`, `modalita.py` (a voce, senza riavvio), `suoni.py` | [personalita](docs/aree/personalita.md) |
| Memoria, agenda, liste, tempi | `memory.py`, `agenda.py`, `tempi.py`, `liste.py` | [memoria-agenda-liste](docs/aree/memoria-agenda-liste.md) |
| Finestra di contesto, conversazione, compressione, archivio | `contesto.py`, `conversazione.py`, `compressione.py`, `conversazioni.py` | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Una conversazione per persona, satelliti insieme | `corsie.py` | [contesto-conversazione](docs/aree/contesto-conversazione.md) |
| Politica dei tool, provenienza, quarantena, ciò che dice; sicurezza per valore (attrito, memoria dell'intento, matrice in ombra: dall'08/10) | `politica.py`, `provenienza.py`, `valore.py`, `attrito.py`, `quarantena.py`, `riferire.py` | [sicurezza-politica](docs/aree/sicurezza-politica.md) |
| Conferme e frase di sfida, sicurezza | `conferme.py`, `sicurezza.py`, `guardrail.py` | [sicurezza-politica](docs/aree/sicurezza-politica.md) |
| Minori e guardiano, segnali di pericolo poco chiari a due cancelli (dal 09/10); esercizi generati da Calliope (matematica e italiano, dal 08/10) | `minori.py`, `guardiano.py`, `cancelli.py`, `esercizi/`, `tools/esercizi.py` | [minori](docs/aree/minori.md) |
| Biblioteca offline (ZIM in puro Python, FTS5) | `biblioteca.py`, `zim.py`, `biblioteca_indice.py` | [biblioteca](docs/aree/biblioteca.md) |
| Ricerca su internet (SearXNG sulla DGX) | `web/` | [biblioteca](docs/aree/biblioteca.md) |
| PC a voce (locale o del satellite) | `pc/` (`PCExecutor`, `windows.py`, `remoto.py`), `tools/pc.py` | [pc](docs/aree/pc.md) |
| Documenti Word, Excel, PDF | `documenti/`, `tools/documenti.py` | [documenti-ufficio](docs/aree/documenti-ufficio.md) |
| Ufficio: modelli, rubrica, fatture, DDT | `ufficio/`, `tools/ufficio.py` | [documenti-ufficio](docs/aree/documenti-ufficio.md) |
| Archivio dei documenti di casa (grafo) | `archivio/`, `tools/archivio.py` | [documenti-ufficio](docs/aree/documenti-ufficio.md) |
| Casa via Home Assistant | `casa/`, `tools/casa.py` | [casa](docs/aree/casa.md) |
| Registro delle capacità, macchina; piano dei modelli in sola lettura (`calliope stato --piano`, dal 08/10) | `capacita.py`, `stato.py`, `macchina.py`, `modelli.py`, `piano.py`, `tools/stato.py` | [capacita-installazioni](docs/aree/capacita-installazioni.md) |
| Installazioni dal catalogo | `installa/` | [capacita-installazioni](docs/aree/capacita-installazioni.md) |
| Schermi (schede, SSE, abbinamento), scrivere invece di parlare, cruscotto di chi amministra (sola lettura, dal 06/10), testi dell'agente in Markdown con «Scarica» (dal 07/10), cronologia delle schede per persona su disco e scheda «Conversazione» (dal 08/10) | `schermi/` (`hub.py`, `server.py`, `moduli.py`, `conversazione.py`, `cruscotto.py`, `scarica.py`, `cronologia.py`), `documenti/markdown.py` | [schermi-telefono](docs/aree/schermi-telefono.md) |
| Telefono (satellite nel browser, PWA; schede a schermo intero dal 06/10) | `schermi/telefono.py`, `schermi/pagina/telefono/` | [schermi-telefono](docs/aree/schermi-telefono.md) |
| Rispondi dove ti ho chiesto | `rispondi.py` | [schermi-telefono](docs/aree/schermi-telefono.md) |
| Foto e allegati in ingresso; cassetto dei file per persona (7 giorni, dal 08/10) | `immagini.py`, `allegati.py`, `cassetto.py`, `pc/cattura.py` | [immagini-allegati](docs/aree/immagini-allegati.md) |
| Satelliti (WebSocket, TLS, inoltro, installazione) | `satellite/`, `tls_sicuro.py` | [satelliti](docs/aree/satelliti.md) |
| Agenti in secondo piano (vLLM sulla DGX, sandbox Docker, arbitro), analisi della richiesta prima di partire (dal 06/10), modalità sviluppo a fasi con il collaudo prima dell'approvazione e la sua vista sugli schermi (dal 08/10), ricollaudo alla consegna e sonde verso i soli host noti (dal 08/10 notte) | `agenti/` (`richiesta.py`), `tools/agenti.py`, `sviluppo.py`, `tools/sviluppo.py`, `sonde.py` | [agenti-estensioni](docs/aree/agenti-estensioni.md) |
| Estensioni permanenti e guardrail | `estensioni/`, `tools/estensioni.py` | [agenti-estensioni](docs/aree/agenti-estensioni.md) |
| Giochi sugli schermi | estensioni con scheda, `agenti/fumo_js.mjs` | [giochi](docs/aree/giochi.md) |
| Installazione e aggiornamento su Linux | `pyproject.toml`, `uv.lock`, `setup/linux/` (`gestore.py`) | [setup-dgx](docs/aree/setup-dgx.md) |
| Prova end-to-end sulla DGX (istanza di prova, satelliti finti, voce vera) | `prove/e2e/` (`python -m prove.e2e.lancia`, `calliope prova-e2e`) | [setup-dgx](docs/aree/setup-dgx.md), [manuale](prove/manuali/e2e-dgx.md) |

Tool e livelli di permesso (ospite / familiare / amministra) sono descritti in
[`docs/architettura-tool.md`](docs/architettura-tool.md).

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

## Stato attuale (06/10/2026)

Calliope gira sulla **DGX Spark** dal 02/10 come servizio (voce gemma4 su Ollama, profilo in
`llm_profilo`; Whisper con whisper.cpp; agente qwen3.6 su vLLM); portatile e telefono sono
satelliti. Cronologia e primi test in [`docs/aree/cronologia.md`](docs/aree/cronologia.md).

- **Voce**: wake word acustica, barge-in col nome, chi parla con CAM++, half-duplex, risposte in streaming ([stt-tts](docs/aree/stt-tts.md), [voce-e-regole](docs/aree/voce-e-regole.md)).
- **Tool**: 72 schemi uguali per ogni livello (66 del 07/10, poi `cassetto_gestisci`, i quattro della modalità sviluppo e `schede_pulisci`; dal 08/10 nomi nuovi `lavoro_*`, `sviluppo_*`, `programma_esegui`, `estensione_gestisci`, i vecchi validi nel registro; `esercizi` solo con un minore in casa), permessi decisi in `ToolRegistry.call` ([voce-e-regole](docs/aree/voce-e-regole.md)).
- **Capacità**: 18 nel registro (`capacita.DEFINIZIONI`), installazioni a voce dal catalogo ([capacita-installazioni](docs/aree/capacita-installazioni.md)).
- **Politica unica dei tool** con dati non fidati in busta, conferme e frase di sfida ([sicurezza-politica](docs/aree/sicurezza-politica.md)).
- **Contesto**: finestra dal setup, compressione, archivio delle conversazioni, una conversazione per persona ([contesto-conversazione](docs/aree/contesto-conversazione.md)).
- **Memoria, agenda, liste, calcoli e date** ([memoria-agenda-liste](docs/aree/memoria-agenda-liste.md)).
- **Casa** via Home Assistant, provata con l'HA vero dal 01/10 ([casa](docs/aree/casa.md)); **PC a voce**, anche remoto dal satellite ([pc](docs/aree/pc.md)).
- **Documenti, ufficio** (docxtpl e python-pptx dal 03/10, FatturaPA) e **archivio** dei documenti di casa ([documenti-ufficio](docs/aree/documenti-ufficio.md)).
- **Biblioteca offline** senza libzim e **ricerca web** con SearXNG ([biblioteca](docs/aree/biblioteca.md)).
- **Schermi, telefono (PWA), scrivere invece di parlare** ([schermi-telefono](docs/aree/schermi-telefono.md)); **foto e allegati** ([immagini-allegati](docs/aree/immagini-allegati.md)).
- **Satelliti** con TLS, inoltro, installazione con un comando e aggiornamenti ([satelliti](docs/aree/satelliti.md)).
- **Agenti** sulla DGX (sandbox Docker, arbitro e pausa di vLLM, programmi in diretta, C#) ed **estensioni** con guardrail ([agenti-estensioni](docs/aree/agenti-estensioni.md)); **giochi** ([giochi](docs/aree/giochi.md)).
- **Minori** con guardiano ([minori](docs/aree/minori.md)); **personalità** e modalità startrek ([personalita](docs/aree/personalita.md)).
- Analisi complessiva del 06/10 e proposte P1–P11: [`docs/ricerche/2026-10-06-analisi-complessiva.md`](docs/ricerche/2026-10-06-analisi-complessiva.md); cosa resta: [`docs/roadmap.md`](docs/roadmap.md).
- **Pubblicazione** (06/10): repository pubblico con licenza AGPL-3.0-or-later ([`LICENSE`](LICENSE), [`TERZE-PARTI.md`](TERZE-PARTI.md)); nel repository solo nomi, indirizzi e dati **di fantasia**, i documenti privati in `privato/` (ignorata da git), `prova_dati_privati` nell'hook: [`docs/pubblicazione.md`](docs/pubblicazione.md).
- La **visione** (server di casa con satelliti, famiglia, ospiti, musica, agenti) è in [`docs/visione.md`](docs/visione.md): leggerla prima di toccare l'architettura.

## Problemi aperti

Solo ciò che è ancora vero il 06/10; storia e misure nei documenti d'area.

- **Latenza vera sulla DGX**: il 05/10 prima frase mediana 2,05 s, p90 4,1 s, contro 0,7 s dei banchi. P1–P4 fatti (`calliope stato --turni`), da rimisurare con un giorno d'uso vero (Q1 della [seconda analisi](docs/ricerche/2026-10-06-analisi-2.md)). Ollama della DGX con 4 modelli (26B, guardiano, rilevatore, embedding): dal 06/10 gli embedding aspettano Calliope inattiva (`calliope/ollama_carico.py`) e sulla DGX ci sono `OLLAMA_MAX_LOADED_MODELS=4` e `OLLAMA_NUM_PARALLEL=2` (verificato il 07/10). Dal testo alla voce (07/10): 0,89 s sullo studio, quasi tutto Piper sulla prima frase intera; ora prima frase a pezzi e 8 thread (banco DGX 0,66 → 0,19 s), da rimisurare. Dopo un cambio di modalità il prefisso nuovo si scalda in secondo piano (07/10, locale 2,44 → 0,08 s di lettura), da rimisurare sulla DGX. [contesto-conversazione](docs/aree/contesto-conversazione.md)
- **Prove**: attese fisse di `prova_satellite` (dal 08/10 `prova_telefono_pagina` gira anche nei worktree: onnxruntime-web dal repository principale). [`prove/LEGGIMI.md`](prove/LEGGIMI.md)
- **whisper.cpp senza hotwords**: «Che ore sono» detto subito dopo il nome diventa «Chiori sono». [stt-tts](docs/aree/stt-tts.md)
- **Voci di famiglia al telefono**: in auto la voce di chi amministra vale come quella di un minore (canale, non voci simili); dal 07/10 margine, chi amministra solo familiare col minore vicino e «chi parla?» solo per un'azione; resta da registrare di nuovo per canale e ritarare. [stt-tts](docs/aree/stt-tts.md)
- **Cuffie Bluetooth** che restano collegate ma mute: spegnerle e riaccenderle. [stt-tts](docs/aree/stt-tts.md)
- **Attrito della politica**: con un dato di mezzo (agente, foto, meteo) ogni azione «pericolosa» chiede conferma; il 07/10 15,8 domande ogni 100 turni, 68 % falsi positivi. Progetto per valore ed effetto, dopo il 10/10: [`docs/ricerche/2026-10-07-sicurezza-per-valore.md`](docs/ricerche/2026-10-07-sicurezza-per-valore.md). [sicurezza-politica](docs/aree/sicurezza-politica.md)
- **Voce unico fattore**: la frase di sfida ferma registrazioni e TV, non una voce clonata in tempo reale. Progetto del secondo fattore (telefono obbligatorio per chi amministra, chiave vocale), da fare dopo il congelamento: [`docs/ricerche/2026-10-06-secondo-fattore.md`](docs/ricerche/2026-10-06-secondo-fattore.md). [sicurezza-politica](docs/aree/sicurezza-politica.md)
- **Sandbox**: kernel condiviso, utente di Calliope nel gruppo `docker`; su Windows il codice dell'agente non si esegue. **Pausa di vLLM** in modalità sviluppo (endpoint senza chiave su 127.0.0.1; dopo un SIGKILL `calliope motore vllm agente riprendi`). [agenti-estensioni](docs/aree/agenti-estensioni.md)
- **Wake word**: feature ACAV100M (CC-BY-NC-SA), non distribuibile; il modello di «computer» c'è sul portatile e sulla DGX, non nel repository. [stt-tts](docs/aree/stt-tts.md), [personalita](docs/aree/personalita.md)
- **Modello**: «Calliope, chi sono?» → «Calliope.» dopo le 20:30; «Ricorda che a Dario piace la pizza» scritto come testo; ricordi fuori tema e correzioni del 04/10 da riprovare col 26B. [voce-e-regole](docs/aree/voce-e-regole.md)
- **Foto**: con una foto nella conversazione «cosa vedi sul mio schermo?» riceve «Non me l'hai chiesto». [immagini-allegati](docs/aree/immagini-allegati.md)
- **Non provati sul vero**: iPhone (audio, schermo acceso, auto), PC Windows pulito come satellite, installazioni con internet vero, misure su Windows ARM. [roadmap](docs/roadmap.md)
- **Biblioteca**: tabelle delle voci non lette; «perché piove?» trova titoli omonimi. [biblioteca](docs/aree/biblioteca.md)
- **Agente**: il codice fiscale (qwen3.6 non conosce il carattere di controllo); il giro del gioco con `require` da rifare. [agenti-estensioni](docs/aree/agenti-estensioni.md), [giochi](docs/aree/giochi.md)

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
- Prove: una prova nuova va in `prove/__main__.py` e in [`prove/elenco.md`](prove/elenco.md)
  nella sua area; i passi manuali in `prove/manuali/`. Comandi del runner: vedi la sezione
  «Runner» di [`prove/LEGGIMI.md`](prove/LEGGIMI.md).
- L'hook lancia `python -m prove --hook --staged` (livelli 1 e 2, ~15–60 s). **Prima
  dell'unione** `python -m prove --completo` (~8 min, con `voices/`, `models/speaker/`,
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
